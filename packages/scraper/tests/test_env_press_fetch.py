from email.message import Message
import unittest
from unittest.mock import Mock, call, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from press_watch_scraper.env_press import (
    InvalidFetchUrlError,
    UNSAFE_REDIRECT_REASON,
    USER_AGENT,
    _RateLimitedHTTPHandler,
    _RateLimitedHTTPSHandler,
    _RequestRateLimiter,
    _SameOriginRedirectHandler,
    _open_same_origin_url,
    fetch_press_page_html,
)


EXPECTED_HTML_TEXT = '環境省'
FETCH_URL = 'https://example.com/press/index.html'
TIMEOUT_SECONDS = 3.5
INVALID_UTF8_BYTES = b'\xff'
DECODE_REPLACEMENT_CHARACTER = '�'
FETCH_ERROR_REASON = 'network unavailable'


class _FakeClock:
    """rate limiterテスト用の単調増加時計"""

    def __init__(self, initial: float = 0.0) -> None:
        self.current = initial
        self.slept_seconds: list[float] = []

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds

    def sleep(self, seconds: float) -> None:
        self.slept_seconds.append(seconds)
        self.advance(seconds)


class RequestRateLimiterTest(unittest.TestCase):
    """HTTP要求開始間隔を制御するrate limiterのテスト"""

    def test_waits_only_remaining_time_between_request_starts(self) -> None:
        """前回開始から既に経過した時間を待機時間から差し引くこと"""

        fake_clock = _FakeClock(initial=10.0)
        limiter = _RequestRateLimiter(
            interval_seconds=3.0,
            clock=fake_clock,
            sleeper=fake_clock.sleep,
        )

        limiter.wait()
        fake_clock.advance(1.0)
        limiter.wait()

        self.assertEqual(fake_clock.slept_seconds, [2.0])

    def test_rechecks_elapsed_time_after_sleeper_returns_early(self) -> None:
        """sleeperが早期復帰しても最小間隔を満たすまで待つこと"""

        fake_clock = _FakeClock()

        def early_sleeper(seconds: float) -> None:
            fake_clock.slept_seconds.append(seconds)
            fake_clock.advance(min(seconds, 1.0))

        limiter = _RequestRateLimiter(
            interval_seconds=3.0,
            clock=fake_clock,
            sleeper=early_sleeper,
        )

        limiter.wait()
        limiter.wait()

        self.assertEqual(fake_clock.current, 3.0)
        self.assertEqual(fake_clock.slept_seconds, [3.0, 2.0, 1.0])

    def test_rejects_non_positive_interval(self) -> None:
        """0秒以下の要求間隔を拒否すること"""

        for interval_seconds in (0.0, -1.0):
            with self.subTest(interval_seconds=interval_seconds):
                with self.assertRaises(ValueError):
                    _RequestRateLimiter(interval_seconds=interval_seconds)

    def test_reports_wait_and_request_start_with_elapsed_time(self) -> None:
        """待機と要求開始を対象・番号・経過時間付きで通知すること"""

        second_url = 'https://example.com/press/202605.html'
        fake_clock = _FakeClock()
        progress_messages: list[str] = []
        limiter = _RequestRateLimiter(
            interval_seconds=3.0,
            clock=fake_clock,
            sleeper=fake_clock.sleep,
            progress=progress_messages.append,
        )

        limiter.wait(FETCH_URL)
        fake_clock.advance(1.0)
        limiter.wait(second_url)

        self.assertEqual(
            progress_messages,
            [
                f'request 1 started at +0.000s: {FETCH_URL}',
                f'waiting 2s before request 2: {second_url}',
                f'request 2 started at +3.000s: {second_url}',
            ],
        )

    def test_progress_output_delay_does_not_reduce_request_interval(
        self,
    ) -> None:
        """進捗出力に時間がかかっても送信開始間隔を短縮しないこと"""

        fake_clock = _FakeClock()

        def slow_first_progress(message: str) -> None:
            if message.startswith('request 1 started'):
                fake_clock.advance(2.0)

        limiter = _RequestRateLimiter(
            interval_seconds=3.0,
            clock=fake_clock,
            sleeper=fake_clock.sleep,
            progress=slow_first_progress,
        )

        limiter.wait(FETCH_URL)
        first_request_returned_at = fake_clock.current
        fake_clock.advance(1.0)
        limiter.wait(FETCH_URL)

        self.assertEqual(fake_clock.slept_seconds, [2.0])
        self.assertEqual(
            fake_clock.current - first_request_returned_at,
            3.0,
        )


class RateLimitedTransportTest(unittest.TestCase):
    """HTTP transportで共有rate limiterを使うテスト"""

    def test_failed_request_start_delays_next_attempt(self) -> None:
        """HTTP失敗後の再試行も前回開始から間隔を空けること"""

        fake_clock = _FakeClock()
        rate_limiter = _RequestRateLimiter(
            interval_seconds=3.0,
            clock=fake_clock,
            sleeper=fake_clock.sleep,
        )
        https_handler = _RateLimitedHTTPSHandler(rate_limiter)
        success_response = Mock(code=200, msg='OK')

        with patch.object(
            https_handler,
            'do_open',
            side_effect=(URLError(FETCH_ERROR_REASON), success_response),
        ):
            with self.assertRaises(URLError):
                https_handler.https_open(Request(FETCH_URL))
            fake_clock.advance(1.0)
            response = https_handler.https_open(Request(FETCH_URL))

        self.assertIs(response, success_response)
        self.assertEqual(fake_clock.slept_seconds, [2.0])

    def test_same_origin_redirect_uses_limiter_for_both_requests(self) -> None:
        """初回要求と同一オリジンredirect先の両方を制御すること"""

        redirected_url = 'https://example.com/press/redirected.html'
        redirect_headers = Message()
        redirect_headers['Location'] = redirected_url
        redirect_response = Mock(
            code=302,
            msg='Found',
        )
        redirect_response.info.return_value = redirect_headers
        redirect_response.read.return_value = b''
        success_response = Mock(code=200, msg='OK')
        success_response.info.return_value = Message()
        rate_limiter = Mock(spec=_RequestRateLimiter)
        https_handler = _RateLimitedHTTPSHandler(rate_limiter)

        with patch.object(
            https_handler,
            'do_open',
            side_effect=(redirect_response, success_response),
        ):
            opener = build_opener(
                _SameOriginRedirectHandler(),
                https_handler,
            )
            response = opener.open(FETCH_URL)

        self.assertIs(response, success_response)
        self.assertEqual(
            rate_limiter.wait.call_args_list,
            [call(FETCH_URL), call(redirected_url)],
        )

    def test_open_uses_same_limiter_for_http_and_https_handlers(self) -> None:
        """製品のopen経路でHTTPとHTTPSの両handlerを組み込むこと"""

        rate_limiter = Mock(spec=_RequestRateLimiter)
        opener = Mock()

        request = Request(FETCH_URL)
        with patch(
            'press_watch_scraper.env_press.build_opener',
            return_value=opener,
        ) as mock_build_opener:
            _open_same_origin_url(
                request,
                TIMEOUT_SECONDS,
                rate_limiter=rate_limiter,
            )

        handlers = mock_build_opener.call_args.args
        http_handlers = [
            handler
            for handler in handlers
            if isinstance(handler, _RateLimitedHTTPHandler)
        ]
        https_handlers = [
            handler
            for handler in handlers
            if isinstance(handler, _RateLimitedHTTPSHandler)
        ]
        self.assertEqual(len(http_handlers), 1)
        self.assertEqual(len(https_handlers), 1)
        http_handler = http_handlers[0]
        https_handler = https_handlers[0]
        self.assertIs(http_handler._rate_limiter, rate_limiter)
        self.assertIs(https_handler._rate_limiter, rate_limiter)
        opener.open.assert_called_once_with(request, timeout=TIMEOUT_SECONDS)


class _Headers:
    """テスト用レスポンスヘッダー"""

    def __init__(self, charset: str | None) -> None:
        self._charset = charset

    def get_content_charset(self) -> str | None:
        return self._charset


class _Response:
    """HTTP取得関数の戻り値として使うテスト用レスポンス"""

    def __init__(self, body: bytes, charset: str | None = None) -> None:
        self.headers = _Headers(charset)
        self._body = body

    def __enter__(self) -> '_Response':
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class EnvPressFetchTest(unittest.TestCase):
    """報道発表ページHTML取得処理のテスト"""

    # HTTP取得時のリクエスト条件とデコード方針を確認する。
    def test_fetch_press_page_html_sends_user_agent_and_timeout(self) -> None:
        """User-Agentとtimeoutを指定してHTTP取得すること"""

        # 実HTTP通信を避け、取得関数に渡したRequestとtimeoutを確認する。
        with patch(
            'press_watch_scraper.env_press._open_same_origin_url'
        ) as mock_open_url:
            mock_open_url.return_value = _Response(
                EXPECTED_HTML_TEXT.encode('utf-8'),
                charset='utf-8',
            )

            html = fetch_press_page_html(
                FETCH_URL,
                timeout=TIMEOUT_SECONDS,
            )

        request = mock_open_url.call_args.args[0]
        headers = {
            name.lower(): value
            for name, value in request.header_items()
        }

        self.assertEqual(html, EXPECTED_HTML_TEXT)
        self.assertEqual(request.full_url, FETCH_URL)
        self.assertEqual(headers['user-agent'], USER_AGENT)
        self.assertEqual(
            mock_open_url.call_args.args[1],
            TIMEOUT_SECONDS,
        )

    def test_fetch_press_page_html_uses_response_charset(self) -> None:
        """レスポンスのcharsetを優先すること"""

        body = EXPECTED_HTML_TEXT.encode('cp932')

        with patch(
            'press_watch_scraper.env_press._open_same_origin_url'
        ) as mock_open_url:
            mock_open_url.return_value = _Response(body, charset='cp932')

            html = fetch_press_page_html()

        self.assertEqual(html, EXPECTED_HTML_TEXT)

    def test_fetch_press_page_html_falls_back_to_utf8_charset(self) -> None:
        """charsetがない場合にUTF-8でデコードすること"""

        body = EXPECTED_HTML_TEXT.encode('utf-8')

        with patch(
            'press_watch_scraper.env_press._open_same_origin_url'
        ) as mock_open_url:
            mock_open_url.return_value = _Response(body)

            html = fetch_press_page_html()

        self.assertEqual(html, EXPECTED_HTML_TEXT)

    def test_fetch_press_page_html_replaces_decode_errors(self) -> None:
        """デコード不能なバイト列を置換すること"""

        with patch(
            'press_watch_scraper.env_press._open_same_origin_url'
        ) as mock_open_url:
            mock_open_url.return_value = _Response(
                INVALID_UTF8_BYTES,
                charset='utf-8',
            )

            html = fetch_press_page_html()

        self.assertEqual(html, DECODE_REPLACEMENT_CHARACTER)

    def test_fetch_press_page_html_rejects_unsafe_urls(self) -> None:
        """HTTPまたはHTTPS以外のURLや認証情報付きURLを取得しないこと"""

        cases = (
            ('file:///private/etc/hosts', 'unsupported_scheme'),
            ('data:text/html,invalid', 'unsupported_scheme'),
            (
                'https://user:password@example.com/press/index.html',
                'credentials_not_allowed',
            ),
            (
                'https://example.com/press/invalid path.html',
                'unsafe_character',
            ),
            (
                'https://example.com/press/invalid\npath.html',
                'unsafe_character',
            ),
            (
                'https://example.com/press/invalid<path.html',
                'unsafe_character',
            ),
            (
                'https://example.com/press/invalid%ZZpath.html',
                'invalid_percent_escape',
            ),
            (
                'https://example.com/press/日本語.html',
                'non_ascii_character',
            ),
            (
                'https://exa%20mple.com/press/index.html',
                'invalid_host_or_port',
            ),
        )

        for url, reason in cases:
            with self.subTest(url=url):
                with patch(
                    'press_watch_scraper.env_press._open_same_origin_url'
                ) as mock_open_url:
                    with self.assertRaises(
                        InvalidFetchUrlError
                    ) as raised:
                        fetch_press_page_html(url)

                message = str(raised.exception)
                self.assertIn(f'validation={reason}', message)
                self.assertIn('url=', message)
                self.assertNotIn('user:password', message)
                mock_open_url.assert_not_called()

    def test_redirect_handler_allows_same_origin_redirect(self) -> None:
        """同一オリジンへのHTTPリダイレクトを許可すること"""

        redirected = _SameOriginRedirectHandler().redirect_request(
            Request(FETCH_URL),
            None,
            302,
            'Found',
            Message(),
            'https://example.com/press/redirected.html',
        )

        self.assertIsNotNone(redirected)
        self.assertEqual(
            redirected.full_url,
            'https://example.com/press/redirected.html',
        )

    def test_redirect_handler_rejects_cross_origin_redirect(self) -> None:
        """外部オリジンへのHTTPリダイレクトを拒否すること"""

        response = Mock()
        with self.assertRaisesRegex(
            HTTPError,
            UNSAFE_REDIRECT_REASON,
        ) as raised:
            _SameOriginRedirectHandler().redirect_request(
                Request(FETCH_URL),
                response,
                302,
                'Found',
                Message(),
                'http://127.0.0.1/internal',
            )
        response.close.assert_called_once_with()
        self.assertIn(
            'validation=cross_origin',
            str(raised.exception),
        )
        raised.exception.close()

    # 通信エラーは取得関数側で握りつぶさない。
    def test_fetch_press_page_html_propagates_fetch_error(self) -> None:
        """HTTP取得時の例外を呼び出し元へ伝播すること"""

        with patch(
            'press_watch_scraper.env_press._open_same_origin_url'
        ) as mock_open_url:
            mock_open_url.side_effect = URLError(FETCH_ERROR_REASON)

            with self.assertRaises(URLError):
                fetch_press_page_html()


if __name__ == '__main__':
    unittest.main()

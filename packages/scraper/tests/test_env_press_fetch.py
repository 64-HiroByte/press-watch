import unittest
from unittest.mock import patch
from urllib.error import URLError

from press_watch_scraper.env_press import USER_AGENT, fetch_press_index_html


EXPECTED_HTML_TEXT = '環境省'
FETCH_URL = 'https://example.com/press/index.html'
TIMEOUT_SECONDS = 3.5
INVALID_UTF8_BYTES = b'\xff'
DECODE_REPLACEMENT_CHARACTER = '�'
FETCH_ERROR_REASON = 'network unavailable'


class _Headers:
    """テスト用レスポンスヘッダー"""

    def __init__(self, charset: str | None) -> None:
        self._charset = charset

    def get_content_charset(self) -> str | None:
        return self._charset


class _Response:
    """urlopenの戻り値として使うテスト用レスポンス"""

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
    """報道発表一覧HTML取得処理のテスト"""

    # HTTP取得時のリクエスト条件とデコード方針を確認する。
    def test_fetch_press_index_html_sends_user_agent_and_timeout(self) -> None:
        """User-Agentとtimeoutを指定してHTTP取得すること"""

        # 実HTTP通信を避け、urlopenに渡したRequestとtimeoutを確認する。
        with patch('press_watch_scraper.env_press.urlopen') as mock_urlopen:
            mock_urlopen.return_value = _Response(
                EXPECTED_HTML_TEXT.encode('utf-8'),
                charset='utf-8',
            )

            html = fetch_press_index_html(
                FETCH_URL,
                timeout=TIMEOUT_SECONDS,
            )

        request = mock_urlopen.call_args.args[0]
        headers = {
            name.lower(): value
            for name, value in request.header_items()
        }

        self.assertEqual(html, EXPECTED_HTML_TEXT)
        self.assertEqual(request.full_url, FETCH_URL)
        self.assertEqual(headers['user-agent'], USER_AGENT)
        self.assertEqual(
            mock_urlopen.call_args.kwargs['timeout'],
            TIMEOUT_SECONDS,
        )

    def test_fetch_press_index_html_uses_response_charset(self) -> None:
        """レスポンスのcharsetを優先すること"""

        body = EXPECTED_HTML_TEXT.encode('cp932')

        with patch('press_watch_scraper.env_press.urlopen') as mock_urlopen:
            mock_urlopen.return_value = _Response(body, charset='cp932')

            html = fetch_press_index_html()

        self.assertEqual(html, EXPECTED_HTML_TEXT)

    def test_fetch_press_index_html_falls_back_to_utf8_charset(self) -> None:
        """charsetがない場合にUTF-8でデコードすること"""

        body = EXPECTED_HTML_TEXT.encode('utf-8')

        with patch('press_watch_scraper.env_press.urlopen') as mock_urlopen:
            mock_urlopen.return_value = _Response(body)

            html = fetch_press_index_html()

        self.assertEqual(html, EXPECTED_HTML_TEXT)

    def test_fetch_press_index_html_replaces_decode_errors(self) -> None:
        """デコード不能なバイト列を置換すること"""

        with patch('press_watch_scraper.env_press.urlopen') as mock_urlopen:
            mock_urlopen.return_value = _Response(
                INVALID_UTF8_BYTES,
                charset='utf-8',
            )

            html = fetch_press_index_html()

        self.assertEqual(html, DECODE_REPLACEMENT_CHARACTER)

    # 通信エラーは取得関数側で握りつぶさない。
    def test_fetch_press_index_html_propagates_urlopen_error(self) -> None:
        """urlopenの例外を呼び出し元へ伝播すること"""

        with patch('press_watch_scraper.env_press.urlopen') as mock_urlopen:
            mock_urlopen.side_effect = URLError(FETCH_ERROR_REASON)

            with self.assertRaises(URLError):
                fetch_press_index_html()


if __name__ == '__main__':
    unittest.main()

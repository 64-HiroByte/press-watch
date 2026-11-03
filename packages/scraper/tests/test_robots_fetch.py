"""robots確認と対象ページ未送信を合成応答で検証"""

from email.message import Message
from functools import partial
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request
from unittest.mock import patch

from press_watch_scraper import env_press as env
from cli_test_support import _FakeClock, _archive_html_by_url, _run_cli_raw


class Response(BytesIO):
    """合成HTTP応答"""

    def __init__(self, body: bytes, content_type: str = 'text/plain') -> None:
        """本文とメディア型を保持

        Args:
            body: 応答本文
            content_type: 応答のメディア型
        """
        super().__init__(body)
        self.headers = Message()
        self.headers['Content-Type'] = content_type
        self.code, self.msg = 200, 'OK'

    def getcode(self) -> int:
        """応答ステータスを返却

        Returns:
            この合成応答のHTTPステータス
        """
        return self.code

    def info(self) -> Message:
        """実openerが参照する応答ヘッダーを返却

        Returns:
            この合成応答のヘッダー
        """
        return self.headers


class RobotsFetchTest(unittest.TestCase):
    """robots失敗時の未送信と共有を確認"""

    def setUp(self) -> None:
        """既定のlimiterだけ仮想時計へ差し替え、実際の送信前制御を待機なしで確認"""
        clock = _FakeClock()
        self.enterContext(
            patch.object(
                env, '_RequestRateLimiter',
                partial(env._RequestRateLimiter, clock=clock, sleeper=clock.sleep),
            ),
        )

    def _assert_page_not_sent(
        self,
        response: Response | Exception,
        url: str = 'https://example.com/press/',
    ) -> None:
        """robotsの禁止・確認失敗時に対象ページがtransportへ届かないことを確認

        Args:
            response: robots取得に返す合成応答または送出する例外
            url: 取得を試みる対象URL
        """
        parts = urlsplit(url)
        robots_url = f'{parts.scheme}://{parts.netloc}/robots.txt'
        with patch.object(
            env._RateLimitedHTTPSHandler, 'do_open',
            side_effect=(response, Response(b'page')),
        ) as sent:
            with self.assertRaises(env.RobotsCheckError):
                env.fetch_press_page_html(url)
            self.assertLessEqual(sent.call_count, 1)
            for call in sent.call_args_list:
                self.assertEqual(call.args[1].full_url, robots_url)

    def test_request_target_variants_do_not_bypass_disallow(self) -> None:
        """空パス・fragment・空query・先頭二重slashでも禁止対象を送信しないこと"""
        for rule, url in (
            ('/', 'https://example.com?foo=1'),
            ('/', 'https://example.com#part'),
            ('/?', 'https://example.com?'),
            ('/?', 'https://example.com/?#part'),
            ('//blocked', 'https://example.com//blocked'),
        ):
            with self.subTest(url=url):
                self._assert_page_not_sent(
                    Response(f'User-agent: *\nDisallow: {rule}'.encode()), url,
                )

    def test_disallow_prevents_page_request(self) -> None:
        """空行や空Disallowがあっても禁止ページを送信しないこと"""
        for rules in (
            'User-agent: *\nDisallow: /press/',
            'User-agent: *\nDisallow:\nDisallow: /press/',
            'User-agent: *\n\nDisallow: /press/',
        ):
            with self.subTest(rules=rules):
                self._assert_page_not_sent(Response(rules.encode()))

    def test_failures_prevent_page_request(self) -> None:
        """不正・未対応・不正応答・通信失敗ではページを開かないこと"""
        bodies = (
            b'User-agent: *\nAllow: /',
            b'User-agent: *\nDisallow: /*',
            b'User-agent: *\nDisallow: /x$',
            b'User-agent: *\nDisallow: /x\nUser-agent: *',
            b'<html>error</html>', b'\xff',
        )
        responses = [Response(body) for body in bodies]
        responses.extend((
            Response(b'', 'text/html'),
            Response(b'x' * (512 * 1024 + 1)),
        ))
        for response in responses:
            with self.subTest(response=response):
                self._assert_page_not_sent(response)
        for error in (
            URLError('offline'),
            HTTPError('https://example.com/robots.txt', 404, 'missing', {}, None),
        ):
            with self.subTest(error=type(error)):
                self._assert_page_not_sent(error)

    def test_cache_is_per_execution_and_url_is_checked_each_time(self) -> None:
        """同じlimiterでrobotsを再利用しても別URLの禁止を確認すること"""
        limiter = env._RequestRateLimiter()
        with patch.object(
            env._RateLimitedHTTPSHandler, 'do_open',
            side_effect=(
                Response(b'User-agent: *\nDisallow: /private'),
                Response(b'page'),
            ),
        ) as opened:
            self.assertEqual(
                env.fetch_press_page_html(
                    'https://example.com/press/', rate_limiter=limiter,
                ),
                'page',
            )
            with self.assertRaises(RuntimeError):
                env.fetch_press_page_html(
                    'https://example.com/private', rate_limiter=limiter,
                )
            self.assertEqual(opened.call_count, 2)
        with patch.object(
            env._RateLimitedHTTPSHandler, 'do_open',
            side_effect=(Response(b''), Response(b'new')),
        ) as opened:
            self.assertEqual(
                env.fetch_press_page_html('https://example.com/private'), 'new',
            )
            self.assertEqual(opened.call_count, 2)

    def test_transport_checks_redirect_and_shares_request_interval(self) -> None:
        """実openerでrobots・ページ・redirectに同じ間隔を適用し禁止先を送信しないこと"""
        for target, allowed in (
            ('/press/next', True),
            ('/private', False),
            ('https://example.com?foo=1', False),
            ('https://example.com//blocked', False),
        ):
            with self.subTest(target=target):
                clock = _FakeClock()
                starts = []

                def respond(
                    _handler: object,
                    connection: object,
                    request: Request,
                    **kwargs: object,
                ) -> Response:
                    """送信要求を記録して合成HTTP応答を返却

                    Args:
                        _handler: transport handler
                        connection: 接続クラス
                        request: 実openerが送信する要求
                        kwargs: transportの追加引数

                    Returns:
                        robotsまたはページの合成応答
                    """
                    starts.append((
                        request.full_url, clock(), request.get_header('User-agent'),
                    ))
                    body = (
                        b'User-agent: *\nDisallow: /private\nDisallow: /?'
                        if request.full_url.endswith('/robots.txt')
                        else b'page'
                    )
                    response = Response(body)
                    if request.full_url.endswith('/press/'):
                        response.code, response.msg = 302, 'Found'
                        response.headers['Location'] = target
                    return response

                limiter = env._RequestRateLimiter(
                    clock=clock, sleeper=clock.sleep,
                )
                with patch.object(env._RateLimitedHTTPSHandler, 'do_open', respond):
                    if allowed:
                        self.assertEqual(
                            env.fetch_press_page_html(
                                'https://example.com/press/', rate_limiter=limiter,
                            ),
                            'page',
                        )
                    else:
                        with self.assertRaises(RuntimeError):
                            env.fetch_press_page_html(
                                'https://example.com/press/', rate_limiter=limiter,
                            )
                self.assertEqual(
                    [item[1] for item in starts],
                    [0, 3, 6] if allowed else [0, 3],
                )
                self.assertTrue(all(item[2] == env.USER_AGENT for item in starts))

    def test_robots_redirect_does_not_follow_location(self) -> None:
        """robotsの転送応答を閉じて転送先を送信しないこと"""
        response = Response(b'')
        response.code, response.msg = 302, 'Found'
        response.headers['Location'] = '/press/'
        with patch.object(
            env._RateLimitedHTTPSHandler, 'do_open', return_value=response,
        ) as opened:
            with self.assertRaises(RuntimeError):
                env.fetch_press_page_html('https://example.com/press/')
            self.assertEqual(opened.call_count, 1)
            self.assertTrue(response.closed)

    def test_incomplete_or_missing_content_type_is_rejected(self) -> None:
        """本文不足やメディア型不明を空の許可ルールとして扱わないこと"""
        short = Response(b'User-agent: *')
        short.headers['Content-Length'] = '100'
        missing_type = Response(b'')
        del missing_type.headers['Content-Type']
        for response in (short, missing_type):
            with self.subTest(response=response):
                self._assert_page_not_sent(response)

    def test_invalid_content_type_prevents_page_request(self) -> None:
        """不正なメディア型の既定値を許可として扱わずページを送信しないこと"""
        for content_type in ('garbage', 'text'):
            with self.subTest(content_type=content_type):
                self._assert_page_not_sent(Response(b'', content_type))

    def test_cli_crawl_resume_and_file_do_not_bypass_robots(self) -> None:
        """巡回でrobotsを共有し、保存済み再開・from-fileでは通信しないこと"""
        pages = _archive_html_by_url()
        index = next(iter(pages))
        requests = []

        def respond(
            connection: object,
            request: Request,
            **kwargs: object,
        ) -> Response:
            """取得URLを記録してrobotsまたは合成HTMLを返却

            Args:
                connection: 接続クラス
                request: 取得要求
                kwargs: 取得の追加設定

            Returns:
                合成のrobotsまたはページ応答
            """
            requests.append(request.full_url)
            body = (
                b'User-agent: *\nDisallow: /private'
                if request.full_url.endswith('/robots.txt')
                else pages[request.full_url].encode()
            )
            return Response(body)

        with tempfile.TemporaryDirectory(prefix='presswatch-robots.') as temp_dir:
            state = str(Path(temp_dir) / 'state')
            args = ('--url', index, '--all-archive-months', '--crawl-state-dir', state)
            with patch.object(
                env._RateLimitedHTTPSHandler, 'do_open', side_effect=respond,
            ):
                self.assertEqual(_run_cli_raw(*args)[0], 0)
            self.assertEqual(sum(url.endswith('/robots.txt') for url in requests), 1)
            self.assertEqual(set(requests[1:]), set(pages))
            with patch.object(
                env._RateLimitedHTTPSHandler, 'do_open',
                side_effect=AssertionError('unexpected network'),
            ) as opened:
                self.assertEqual(_run_cli_raw(*args, '--resume')[0], 0)
                self.assertEqual(
                    _run_cli_raw(
                        '--from-file', str(Path(state) / 'pages/index.html'),
                    )[0],
                    0,
                )
                opened.assert_not_called()

    def test_resume_refetch_checks_current_robots(self) -> None:
        """未取得ページの再開時は新しいrobotsの禁止で停止すること"""
        pages = _archive_html_by_url()
        index = next(iter(pages))
        with tempfile.TemporaryDirectory(prefix='presswatch-robots.') as temp_dir:
            args = (
                '--url', index, '--all-archive-months',
                '--crawl-state-dir', str(Path(temp_dir) / 'state'),
            )
            with patch.object(
                env._RateLimitedHTTPSHandler, 'do_open',
                side_effect=(
                    Response(b''), Response(pages[index].encode()),
                    URLError('offline'),
                ),
            ):
                self.assertEqual(_run_cli_raw(*args)[0], 1)
            with patch.object(
                env._RateLimitedHTTPSHandler, 'do_open',
                return_value=Response(b'User-agent: *\nDisallow: /'),
            ) as opened:
                code, stdout, stderr = _run_cli_raw(*args, '--resume')
                self.assertEqual(code, 1)
                self.assertEqual(stdout, '')
                self.assertIn('disallowed', stderr)
                self.assertEqual(opened.call_count, 1)
                self.assertTrue(
                    opened.call_args.args[1].full_url.endswith('/robots.txt'),
                )

    def test_empty_and_comment_only_rules_allow_page(self) -> None:
        """空本文・コメント・空Disallowを制限なしとして取得すること"""
        for rules in (
            b'', b'# comment', b'User-agent: *\nDisallow:',
            b'\xef\xbb\xbfUser-agent: *\nDisallow: /private',
            b'#' + b'x' * (512 * 1024 - 1),
        ):
            with self.subTest(size=len(rules)), patch.object(
                env._RateLimitedHTTPSHandler, 'do_open',
                side_effect=(Response(rules), Response(b'page')),
            ) as opened:
                self.assertEqual(
                    env.fetch_press_page_html('https://example.com/press/'), 'page',
                )
                self.assertEqual(opened.call_count, 2)
                self.assertEqual(
                    opened.call_args_list[0].args[1].get_header('User-agent'),
                    env.USER_AGENT,
                )

    def test_allowed_root_and_plain_text_parameters_are_preserved(self) -> None:
        """query禁止だけならqueryなしのrootは取得でき、text/plainのパラメーターも受理すること"""
        with patch.object(
            env._RateLimitedHTTPSHandler, 'do_open',
            side_effect=(
                Response(b'User-agent: *\nDisallow: /?', 'Text/Plain; charset=UTF-8'),
                Response(b'page'),
            ),
        ) as opened:
            self.assertEqual(
                env.fetch_press_page_html('https://example.com#part'), 'page',
            )
            self.assertEqual(opened.call_count, 2)

    def test_normal_cli_failure_has_no_success_json(self) -> None:
        """通常取得で禁止時に失敗を返し成功JSONを出力しないこと"""
        with patch.object(
            env._RateLimitedHTTPSHandler, 'do_open',
            return_value=Response(b'User-agent: *\nDisallow: /'),
        ) as opened:
            code, stdout, stderr = _run_cli_raw('--url', 'https://example.com/press/')
            self.assertEqual(code, 1)
            self.assertEqual(stdout, '')
            self.assertIn('RobotsCheckError', stderr)
            self.assertEqual(opened.call_count, 1)

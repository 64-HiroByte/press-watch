"""scraper CLIの結果・進捗出力と、失敗時の出力ファイル保全を検証"""

from collections.abc import Callable
from contextlib import redirect_stderr
from html import escape
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

from press_watch_scraper import __main__ as cli

from cli_test_support import (
    EXAMPLE_APRIL_ARCHIVE_URL,
    EXAMPLE_INDEX_URL,
    EXAMPLE_MAY_ARCHIVE_URL,
    EXISTING_OUTPUT_JSON,
    FETCH_ERROR_REASON,
    FETCH_PRESS_PAGE_HTML_ATTR,
    _archive_html_by_url,
    _archive_month_limit_args,
    _archive_page_html,
    _cli_argv,
    _from_file_args,
    _no_stdout_json_args,
    _output_args,
    _press_index_html,
    _run_cli_raw,
    _url_args,
    _verbose_args,
)

from scraper_test_constants import (
    DIAGNOSTIC_CREDENTIAL_URL,
    DIAGNOSTIC_HTML_URL_PREFIX_CASES,
    DIAGNOSTIC_PASSWORD,
    DIAGNOSTIC_REDACTED_URL,
    DIAGNOSTIC_SAFE_URL,
    DIAGNOSTIC_USERNAME,
    DIAGNOSTIC_URL_PREFIX_CASES,
    ENV_ORIGIN_URL,
    EXAMPLE_BASE_URL,
)


OUTPUT_PARENT_NOT_FOUND_ERROR = 'output parent directory does not exist'


def _rate_limited_html_fetcher(
    html_by_url: dict[str, str],
) -> Callable[..., str]:
    """要求間隔の待機を再現し、用意したHTMLを返す取得関数を生成

    HTTP要求は行わず、CLIから渡されたrate limiterの待機だけを実行

    Args:
        html_by_url: 取得URLごとに返すHTMLの辞書

    Returns:
        URLとrate_limiterを受け取り、待機後に対応するHTMLを返す関数
    """

    def fetcher(url: str, *, rate_limiter: object) -> str:
        rate_limiter.wait(url)
        return html_by_url[url]

    return fetcher


class ScraperOutputCliTest(unittest.TestCase):
    """スクレイパーCLIの出力とエラー処理のテスト"""

    def test_main_writes_same_json_to_output_file(self) -> None:
        """指定されたパスへstdoutと同じJSONを保存すること"""

        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / 'index.html'
            output_path = Path(temp_dir) / 'snapshot.json'
            html_path.write_text(_press_index_html(), encoding='utf-8')

            exit_code, stdout, stderr = _run_cli_raw(
                *_from_file_args(html_path),
                *_output_args(output_path),
            )

            saved_json = output_path.read_text(
                encoding=cli.JSON_OUTPUT_ENCODING,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, '')
        self.assertEqual(saved_json, stdout)
        self.assertEqual(json.loads(saved_json), json.loads(stdout))

    def test_main_outputs_progress_to_stderr_when_verbose(self) -> None:
        """verbose指定時に月別巡回の進捗をstderrへ出すこと"""

        html_by_url = _archive_html_by_url()

        with patch.object(
            cli,
            FETCH_PRESS_PAGE_HTML_ATTR,
            side_effect=_rate_limited_html_fetcher(html_by_url),
        ):
            exit_code, stdout, stderr = _run_cli_raw(
                *_url_args(),
                *_archive_month_limit_args(limit=2),
                *_verbose_args(),
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout)['count'], 2)
        self.assertIn(
            f'request 1 started at +0.000s: {EXAMPLE_INDEX_URL}',
            stderr,
        )
        self.assertIn(
            f'waiting {cli.REQUEST_INTERVAL_SECONDS:g}s before request 2: '
            f'{EXAMPLE_MAY_ARCHIVE_URL}',
            stderr,
        )
        self.assertIn(
            f'archive page 1/2: {EXAMPLE_MAY_ARCHIVE_URL}',
            stderr,
        )
        self.assertIn(
            f'archive page 2/2: {EXAMPLE_APRIL_ARCHIVE_URL}',
            stderr,
        )
        self.assertIn(
            f'request 3 started at '
            f'+{cli.REQUEST_INTERVAL_SECONDS * 2:.3f}s: '
            f'{EXAMPLE_APRIL_ARCHIVE_URL}',
            stderr,
        )

    def test_main_can_show_progress_without_stdout_json(self) -> None:
        """stdout JSONを出さずにstderrの進捗だけ確認できること"""

        html_by_url = _archive_html_by_url(include_april=False)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / 'snapshot.json'

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=_rate_limited_html_fetcher(html_by_url),
            ):
                exit_code, stdout, stderr = _run_cli_raw(
                    *_url_args(),
                    *_archive_month_limit_args(limit=1),
                    *_verbose_args(),
                    *_no_stdout_json_args(),
                    *_output_args(output_path),
                )

            saved_payload = json.loads(
                output_path.read_text(encoding=cli.JSON_OUTPUT_ENCODING)
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, '')
        self.assertEqual(saved_payload['count'], 1)
        self.assertIn(
            f'request 1 started at +0.000s: {EXAMPLE_INDEX_URL}',
            stderr,
        )
        self.assertIn(
            f'waiting {cli.REQUEST_INTERVAL_SECONDS:g}s before request 2: '
            f'{EXAMPLE_MAY_ARCHIVE_URL}',
            stderr,
        )
        self.assertIn(
            f'archive page 1/1: {EXAMPLE_MAY_ARCHIVE_URL}',
            stderr,
        )

    # 実行時エラーでは、stderr、終了コード、途中JSONを出さないことを確認する。
    def test_main_outputs_runtime_error_to_stderr_on_fetch_error(
        self,
    ) -> None:
        """HTML取得時の例外をstderrへ出して終了コード1を返すこと"""

        # URL取得だけを失敗させ、CLIの失敗時出力を確認する。
        with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
            mock_fetch.side_effect = URLError(FETCH_ERROR_REASON)

            exit_code, stdout, stderr = _run_cli_raw(
                *_url_args()
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertIn(
            f'target={EXAMPLE_INDEX_URL}',
            stderr,
        )
        self.assertIn('exception=URLError', stderr)
        self.assertIn(FETCH_ERROR_REASON, stderr)
        self.assertNotIn('Traceback', stderr)

    def test_main_reports_invalid_release_url_without_partial_json(
        self,
    ) -> None:
        """不正な発表URLの理由と対象をstderrへ出しJSONを返さないこと"""

        invalid_title = 'URL形式が不正な発表'
        html = _archive_page_html(
            invalid_title,
            '/press/日本語.html',
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / 'index.html'
            html_path.write_text(html, encoding='utf-8')

            exit_code, stdout, stderr = _run_cli_raw(
                *_from_file_args(html_path)
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertEqual(len(stderr.splitlines()), 1)
        self.assertIn(
            'exception=InvalidPressReleaseUrlError',
            stderr,
        )
        self.assertIn('validation=non_ascii_character', stderr)
        self.assertIn(invalid_title, stderr)
        self.assertIn("href='/press/日本語.html'", stderr)

    def test_print_runtime_error_normalizes_target_to_one_line(self) -> None:
        """エラー対象の改行をstderrへ持ち込まないこと"""

        stderr = io.StringIO()

        with redirect_stderr(stderr):
            cli._print_runtime_error(
                f'{EXAMPLE_INDEX_URL}\ninjected=true',
                RuntimeError(FETCH_ERROR_REASON),
            )

        self.assertEqual(len(stderr.getvalue().splitlines()), 1)
        self.assertIn(
            f'target={EXAMPLE_INDEX_URL} injected=true',
            stderr.getvalue(),
        )

    def test_main_redacts_split_url_prefix_in_rejected_release(self) -> None:
        """分断された発表URLを拒否し、認証情報を伏せてタイトルと診断項目を保持すること"""

        title = 'review@example.org の調査'
        for prefix, expected_prefix in DIAGNOSTIC_HTML_URL_PREFIX_CASES:
            if prefix == expected_prefix:
                continue
            href = prefix + DIAGNOSTIC_CREDENTIAL_URL.removeprefix('//')
            expected_href = expected_prefix + DIAGNOSTIC_REDACTED_URL.removeprefix('//')
            with self.subTest(prefix=prefix), patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                return_value=_archive_page_html(title, escape(href, quote=True)),
            ):
                exit_code, stdout, stderr = _run_cli_raw(*_url_args(ENV_ORIGIN_URL))

                self.assertEqual(exit_code, 1)
                self.assertEqual(stdout, '')
                self.assertEqual(len(stderr.splitlines()), 1)
                self.assertIn('validation=unsafe_character', stderr)
                self.assertIn(f'page_url={ENV_ORIGIN_URL!r}', stderr)
                self.assertIn(f'title={title!r}', stderr)
                self.assertIn(f"href='{expected_href}'", stderr)
                self.assertNotIn(DIAGNOSTIC_USERNAME, stderr)
                self.assertNotIn(DIAGNOSTIC_PASSWORD, stderr)

    def test_rejected_url_details_survive_parser_cli_and_manifest(self) -> None:
        """発表・月別URLを拒否し、CLIとmanifestの両方でパスと項目を保ち認証情報を伏せること"""

        title = 'review@example.org の調査'
        suffix = 'host/path=//tag@item?email=a@b.test#tag@item'
        for prefix, expected_prefix in DIAGNOSTIC_HTML_URL_PREFIX_CASES:
            if prefix == expected_prefix:
                continue
            for credentials in ('', f'{DIAGNOSTIC_USERNAME}:{DIAGNOSTIC_PASSWORD}@'):
                href = f'{prefix}{credentials}{suffix}'
                expected_credentials = '[redacted]@' if credentials else ''
                expected_href = f'{expected_prefix}{expected_credentials}{suffix}'
                for kind in ('release', 'archive'):
                    with self.subTest(
                        prefix=prefix, credentials=bool(credentials), kind=kind,
                    ):
                        archive_href = EXAMPLE_MAY_ARCHIVE_URL if kind == 'release' else href
                        link = (
                            '<a class="c-table-month__col__link" aria-label="2026年5月" '
                            f'href="{escape(archive_href, quote=True)}">5月</a>'
                        )
                        if kind == 'release':
                            html_by_url = {
                                EXAMPLE_INDEX_URL: link,
                                EXAMPLE_MAY_ARCHIVE_URL: _archive_page_html(
                                    title, escape(href, quote=True),
                                ),
                            }
                            page_url = EXAMPLE_MAY_ARCHIVE_URL
                            field = f'title={title!r}'
                            exception = 'InvalidPressReleaseUrlError'
                        else:
                            html_by_url = {EXAMPLE_INDEX_URL: link}
                            page_url = EXAMPLE_INDEX_URL
                            field = 'archive_month=2026-05'
                            exception = 'InvalidArchiveMonthUrlError'
                        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
                            cli, FETCH_PRESS_PAGE_HTML_ATTR,
                            side_effect=lambda url, **_kwargs: html_by_url[url],
                        ) as fetch:
                            root = Path(temp_dir) / 'state'
                            exit_code, stdout, stderr = _run_cli_raw(
                                *_url_args(), '--all-archive-months',
                                '--crawl-state-dir', str(root),
                            )
                            manifest = json.loads(
                                (root / 'manifest.json').read_text(encoding='utf-8')
                            )

                        self.assertEqual(exit_code, 1)
                        self.assertEqual(stdout, '')
                        self.assertEqual(manifest['status'], 'failed')
                        self.assertEqual(manifest['pages'][-1]['status'], 'parse_failed')
                        failure = manifest['pages'][-1]['failure']
                        self.assertEqual(failure['stage'], 'parse')
                        self.assertEqual(failure['exception'], exception)
                        self.assertEqual(
                            [call.args[0] for call in fetch.call_args_list], list(html_by_url),
                        )
                        for message in (stderr.strip(), failure['reason']):
                            self.assertEqual(len(message.splitlines()), 1)
                            self.assertIn('validation=unsafe_character', message)
                            self.assertIn(f'page_url={page_url!r}', message)
                            self.assertIn(field, message)
                            self.assertIn(f"href='{expected_href}'", message)
                            self.assertEqual(
                                message.count('[redacted]'), int(bool(credentials)),
                            )
                            self.assertNotIn(DIAGNOSTIC_USERNAME, message)
                            self.assertNotIn(DIAGNOSTIC_PASSWORD, message)

    def test_print_runtime_error_keeps_split_prefix_and_separate_urls(self) -> None:
        """認証なしの分断URLと、改行で分かれた正常URLを診断へ保持すること"""

        for prefix, expected_prefix in DIAGNOSTIC_URL_PREFIX_CASES:
            with self.subTest(prefix=prefix):
                safe_url = f'{prefix}host/path=//tag@item?email=a@b.test#tag@item'
                expected_safe_url = f'{expected_prefix}host/path=//tag@item?email=a@b.test#tag@item'
                credential_url = prefix + DIAGNOSTIC_CREDENTIAL_URL.removeprefix('//')
                expected_url = expected_prefix + DIAGNOSTIC_REDACTED_URL.removeprefix('//')
                reason = f'{DIAGNOSTIC_SAFE_URL}\n{credential_url}'
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    cli._print_runtime_error(safe_url, RuntimeError(reason))

                message = stderr.getvalue()
                self.assertIn(f'target={expected_safe_url} ', message)
                self.assertIn(f'reason={DIAGNOSTIC_SAFE_URL} {expected_url}', message)
                self.assertEqual(message.count('[redacted]'), 1)
                self.assertNotIn(DIAGNOSTIC_USERNAME, message)
                self.assertNotIn(DIAGNOSTIC_PASSWORD, message)

    def test_print_runtime_error_redacts_escaped_url_without_changing_fields(self) -> None:
        """引用や入れ子でエスケープされたURLも認証部分だけを伏せ、他の項目を保持すること"""

        for prefix, _ in DIAGNOSTIC_URL_PREFIX_CASES:
            fields = {
                'url': f'{prefix}{DIAGNOSTIC_USERNAME}:{DIAGNOSTIC_PASSWORD}\ntail@host/path=//tag@item',
                'reference': DIAGNOSTIC_SAFE_URL,
                'email': 'person@example.org',
            }
            expected_fields = {
                'url': f'{prefix}[redacted]@host/path=//tag@item',
                'reference': DIAGNOSTIC_SAFE_URL,
                'email': 'person@example.org',
            }
            for reason, expected in (
                (repr(fields), repr(expected_fields)),
                (json.dumps(fields), json.dumps(expected_fields)),
                (json.dumps(json.dumps(fields)), json.dumps(json.dumps(expected_fields))),
            ):
                with self.subTest(prefix=prefix, reason=reason):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        cli._print_runtime_error(DIAGNOSTIC_SAFE_URL, RuntimeError(reason))

                    message = stderr.getvalue()
                    self.assertIn(f'reason={expected}', message)
                    self.assertEqual(len(message.splitlines()), 1)
                    self.assertNotIn(DIAGNOSTIC_USERNAME, message)
                    self.assertNotIn(DIAGNOSTIC_PASSWORD, message)

    def test_main_keeps_quoted_diagnostic_fields_after_root_url(self) -> None:
        """パスなし取得元と@を含むタイトルをURL拒否時の診断へ保持すること"""

        source_url = ENV_ORIGIN_URL
        title = "review@example.org の '調査' 結果"
        for href, expected_href in (
            ('/press/invalid path', '/press/invalid path'),
            (
                "https://user:password' title='credential-tail tail@www.env.go.jp/press/1",
                'https://[redacted]@www.env.go.jp/press/1',
            ),
        ):
            with self.subTest(href=href), patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                return_value=_archive_page_html(title, escape(href, quote=True)),
            ):
                exit_code, stdout, stderr = _run_cli_raw(
                    *_url_args(source_url)
                )

                self.assertEqual(exit_code, 1)
                self.assertEqual(stdout, '')
                self.assertIn('validation=unsafe_character', stderr)
                self.assertIn(f'page_url={source_url!r}', stderr)
                self.assertIn(f'title={title!r}', stderr)
                self.assertIn(f'href={expected_href!r}', stderr)
                self.assertNotIn('user:', stderr)
                self.assertNotIn('password', stderr)
                self.assertNotIn('credential-tail', stderr)

    def test_main_redacts_credentials_in_title_with_multiple_urls(self) -> None:
        """タイトル内の複数URLを個別に伏せ、URL拒否の診断項目を保持すること"""

        for title in (
            f"url='{DIAGNOSTIC_SAFE_URL}' href='{DIAGNOSTIC_CREDENTIAL_URL}'",
            f'{DIAGNOSTIC_SAFE_URL} href={DIAGNOSTIC_CREDENTIAL_URL}',
            f'url=\'{DIAGNOSTIC_SAFE_URL}\' href="{DIAGNOSTIC_CREDENTIAL_URL}"',
            f'{DIAGNOSTIC_SAFE_URL} リンク={DIAGNOSTIC_CREDENTIAL_URL}',
            f'{DIAGNOSTIC_SAFE_URL} ({DIAGNOSTIC_CREDENTIAL_URL})',
            f'{DIAGNOSTIC_SAFE_URL} [{DIAGNOSTIC_CREDENTIAL_URL}]',
            f'{DIAGNOSTIC_SAFE_URL} {{{DIAGNOSTIC_CREDENTIAL_URL}}}',
            f'{DIAGNOSTIC_SAFE_URL} :{DIAGNOSTIC_CREDENTIAL_URL}',
            f"{DIAGNOSTIC_SAFE_URL} links[0]=[('{DIAGNOSTIC_CREDENTIAL_URL}')]",
            f"{DIAGNOSTIC_SAFE_URL} href:'{DIAGNOSTIC_CREDENTIAL_URL}'",
            f'{DIAGNOSTIC_SAFE_URL} 参照:({DIAGNOSTIC_CREDENTIAL_URL})',
            f'{DIAGNOSTIC_SAFE_URL} {{"href":"{DIAGNOSTIC_CREDENTIAL_URL}"}}',
            f'{DIAGNOSTIC_SAFE_URL} links[0]:="{DIAGNOSTIC_CREDENTIAL_URL}"',
            f'{{"url":"{DIAGNOSTIC_SAFE_URL}","href":"{DIAGNOSTIC_CREDENTIAL_URL}"}}',
            f"['{DIAGNOSTIC_SAFE_URL}','{DIAGNOSTIC_CREDENTIAL_URL}']",
            (
                f'{{"url":"{DIAGNOSTIC_SAFE_URL}/press/item",'
                f'"nested":{{"href":"{DIAGNOSTIC_CREDENTIAL_URL}"}}}}'
            ),
            f'["{DIAGNOSTIC_SAFE_URL}?ref=item",["{DIAGNOSTIC_CREDENTIAL_URL}"]]',
            f'{{"{DIAGNOSTIC_SAFE_URL}":"{DIAGNOSTIC_CREDENTIAL_URL}"}}',
            f'{{"msg":"failed {DIAGNOSTIC_SAFE_URL}","href":"{DIAGNOSTIC_CREDENTIAL_URL}"}}',
            f'''['{{"url":"{DIAGNOSTIC_SAFE_URL}","href":"{DIAGNOSTIC_CREDENTIAL_URL}"}}']''',
            f'''['{{"msg":"failed {DIAGNOSTIC_SAFE_URL}","href":"{DIAGNOSTIC_CREDENTIAL_URL}"}}']''',
            fr'{{"payload":"{{\"url\":\"{DIAGNOSTIC_SAFE_URL}\",\"href\":\"{DIAGNOSTIC_CREDENTIAL_URL}\"}}"}}',
            fr'["{{\"msg\":\"failed {DIAGNOSTIC_SAFE_URL}\",\"href\":\"{DIAGNOSTIC_CREDENTIAL_URL}\"}}"]',
            fr'"{{\"msg\":\"failed {DIAGNOSTIC_SAFE_URL}\",\"href\":\"{DIAGNOSTIC_CREDENTIAL_URL}\"}}"',
            f'["failed {DIAGNOSTIC_SAFE_URL}","{DIAGNOSTIC_CREDENTIAL_URL}"]',
            f"('failed {DIAGNOSTIC_SAFE_URL}','{DIAGNOSTIC_CREDENTIAL_URL}')",
            f"('{DIAGNOSTIC_SAFE_URL}','{DIAGNOSTIC_CREDENTIAL_URL}')",
            (
                f'{{"msg":"失敗 {DIAGNOSTIC_SAFE_URL}/press/item",'
                f'"nested":{{"href":"{DIAGNOSTIC_CREDENTIAL_URL}"}}}}'
            ),
            f'["failed {DIAGNOSTIC_SAFE_URL}?ref=item",["{DIAGNOSTIC_CREDENTIAL_URL}"]]',
            f'{{"failed {DIAGNOSTIC_SAFE_URL}#tag":"{DIAGNOSTIC_CREDENTIAL_URL}"}}',
        ):
            with self.subTest(title=title), patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                return_value=_archive_page_html(escape(title), '/press/invalid path'),
            ):
                exit_code, stdout, stderr = _run_cli_raw(*_url_args())

                self.assertEqual(exit_code, 1)
                self.assertEqual(stdout, '')
                self.assertNotIn(DIAGNOSTIC_USERNAME, stderr)
                self.assertNotIn(DIAGNOSTIC_PASSWORD, stderr)
                self.assertIn(DIAGNOSTIC_SAFE_URL, stderr)
                self.assertIn(DIAGNOSTIC_REDACTED_URL, stderr)
                self.assertIn('validation=unsafe_character', stderr)
                self.assertIn(f'page_url={EXAMPLE_INDEX_URL!r}', stderr)
                self.assertIn('title=', stderr)
                self.assertIn("href='/press/invalid path'", stderr)

    def test_print_runtime_error_redacts_url_credentials(self) -> None:
        """制御文字で分断された接頭辞も認識し、エラー対象と理由の認証情報を伏せること"""

        for prefix, expected_prefix in DIAGNOSTIC_URL_PREFIX_CASES:
            for password in (
                'password',
                'password@credential-tail',
                'password tail',
                'password\ttail',
                'password\ntail',
                'password\r\ntail',
                'password\x1btail',
                'password@credential-tail tail',
                "password' title='credential-tail",
                'password" tail',
            ):
                with self.subTest(prefix=prefix, password=password):
                    credential_url = f'{prefix}user:{password}@example.com/press/index.html'
                    stderr = io.StringIO()

                    with redirect_stderr(stderr):
                        cli._print_runtime_error(
                            credential_url,
                            RuntimeError(f"invalid URL: href='{credential_url}'"),
                        )

                    self.assertNotIn('user:', stderr.getvalue())
                    self.assertNotIn('password', stderr.getvalue())
                    self.assertNotIn('credential-tail', stderr.getvalue())
                    self.assertEqual(
                        stderr.getvalue().count(f'{expected_prefix}[redacted]@example.com'),
                        2,
                    )

    def test_print_runtime_error_escapes_terminal_control_characters(
        self,
    ) -> None:
        """端末制御文字をstderrへそのまま出さないこと"""

        stderr = io.StringIO()

        with redirect_stderr(stderr):
            cli._print_runtime_error(
                f'{EXAMPLE_INDEX_URL}\x1b[31m',
                RuntimeError(f'{FETCH_ERROR_REASON}\x1b[0m'),
            )

        self.assertNotIn('\x1b', stderr.getvalue())
        self.assertIn(r'\x1b[31m', stderr.getvalue())
        self.assertIn(r'\x1b[0m', stderr.getvalue())

    def test_print_runtime_error_keeps_url_boundaries(self) -> None:
        """複数URLを個別に伏せ、非認証URLのパス・クエリ・fragmentを保持すること"""

        safe_url = f'{EXAMPLE_BASE_URL}/path=//tag@item?email=a@b.test#tag@item'
        reason = (
            'failed https://first:secret tail@first.test '
            'and //second:secret\ttail@second.test/path; '
            f'reference={safe_url}'
        )
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            cli._print_runtime_error(safe_url, RuntimeError(reason))

        message = stderr.getvalue()
        self.assertNotIn('secret', message)
        self.assertIn('https://[redacted]@first.test and ', message)
        self.assertIn('//[redacted]@second.test/path;', message)
        self.assertEqual(message.count(safe_url), 2)

    def test_print_runtime_error_keeps_at_in_url_query_and_fragment(self) -> None:
        """非認証URLの二重スラッシュのパス・クエリ・fragmentを保持すること"""

        for url in (
            f'{EXAMPLE_BASE_URL}//value=//tag@item',
            f'{EXAMPLE_BASE_URL}?email=a@b.test',
            '//example.com#tag@item',
            f'{EXAMPLE_BASE_URL}?value=//tag@item',
            '//example.com#value=//tag@item',
            f"{EXAMPLE_BASE_URL}/press/a'//tag@item",
            f"{EXAMPLE_BASE_URL}?ref=a'//tag@item",
            f"{EXAMPLE_BASE_URL}#a'//tag@item",
            f'{EXAMPLE_BASE_URL}/press/(//tag@item)',
            f'{EXAMPLE_BASE_URL}?ref=(//tag@item)',
            f'{EXAMPLE_BASE_URL}#(//tag@item)',
            f"{EXAMPLE_BASE_URL}/press/href:'//tag@item",
            f'{EXAMPLE_BASE_URL}?ref={{"href":"//tag@item"}}',
            f'{EXAMPLE_BASE_URL}#参照:(//tag@item)',
            f"{EXAMPLE_BASE_URL}/press/a','//tag@item",
            f'{EXAMPLE_BASE_URL}?ref="value","href":"//tag@item"',
            f"{EXAMPLE_BASE_URL}#value','//tag@item",
        ):
            with self.subTest(url=url):
                stderr = io.StringIO()

                with redirect_stderr(stderr):
                    cli._print_runtime_error(url, RuntimeError(f'failed {url}'))

                self.assertEqual(stderr.getvalue().count(url), 2)
                self.assertNotIn('[redacted]', stderr.getvalue())

    def test_print_runtime_error_keeps_noncredential_urls_in_quoted_structures(
        self,
    ) -> None:
        """引用付き文字列内の正常URL・メールアドレス・エスケープを診断へ保持すること"""

        inner_value = json.dumps(
            {
                'msg': f'failed {DIAGNOSTIC_SAFE_URL}?ref={{"href":"//tag@item"}}',
                'email': 'person@example.org',
            },
            separators=(',', ':'),
        )
        for reason in (
            repr([inner_value]),
            repr(inner_value),
            json.dumps(inner_value),
            json.dumps({'payload': inner_value}),
            json.dumps([json.dumps({'payload': inner_value})]),
        ):
            with self.subTest(reason=reason):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    cli._print_runtime_error(EXAMPLE_INDEX_URL, RuntimeError(reason))

                self.assertIn(reason, stderr.getvalue())
                self.assertNotIn('[redacted]', stderr.getvalue())

    def test_print_progress_sanitizes_message(self) -> None:
        """接頭辞の制御文字も認識して秘密を伏せ、端末制御文字を進捗へ直接出さないこと"""

        for prefix, expected_prefix in DIAGNOSTIC_URL_PREFIX_CASES:
            for password in ('password', 'password tail', 'password\tcredential-tail'):
                with self.subTest(prefix=prefix, password=password):
                    credential_url = f'{prefix}user:{password}@example.com/press/index.html'
                    stderr = io.StringIO()

                    with redirect_stderr(stderr):
                        cli._print_progress(
                            True,
                            f'fetching index: {credential_url}\ninjected=true\x1b[31m',
                        )

                    self.assertEqual(len(stderr.getvalue().splitlines()), 1)
                    self.assertNotIn('user:', stderr.getvalue())
                    self.assertNotIn('password', stderr.getvalue())
                    self.assertNotIn('credential-tail', stderr.getvalue())
                    self.assertNotIn('\x1b', stderr.getvalue())
                    self.assertIn(
                        (
                            'fetching index: '
                            f'{expected_prefix}[redacted]@example.com/press/index.html '
                            r'injected=true\x1b[31m'
                        ),
                        stderr.getvalue(),
                    )

    def test_main_does_not_create_output_file_on_fetch_error(self) -> None:
        """HTML取得失敗時にJSONスナップショットを作成しないこと"""

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / 'snapshot.json'

            with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
                mock_fetch.side_effect = URLError(FETCH_ERROR_REASON)

                exit_code, stdout, stderr = _run_cli_raw(
                    *_url_args(),
                    *_output_args(output_path),
                )

            output_exists = output_path.exists()

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertIn('exception=URLError', stderr)
        self.assertFalse(output_exists)

    def test_main_keeps_existing_output_file_on_fetch_error(self) -> None:
        """HTML取得失敗時に既存スナップショットを変更しないこと"""

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / 'snapshot.json'
            output_path.write_text(
                EXISTING_OUTPUT_JSON,
                encoding=cli.JSON_OUTPUT_ENCODING,
            )

            with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
                mock_fetch.side_effect = URLError(FETCH_ERROR_REASON)

                exit_code, stdout, stderr = _run_cli_raw(
                    *_url_args(),
                    *_output_args(output_path),
                )

            saved_json = output_path.read_text(
                encoding=cli.JSON_OUTPUT_ENCODING,
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertIn('exception=URLError', stderr)
        self.assertEqual(saved_json, EXISTING_OUTPUT_JSON)

    def test_main_rejects_output_path_with_missing_parent(self) -> None:
        """存在しない親ディレクトリの出力先を取得前に拒否すること"""

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = (
                Path(temp_dir) / 'missing-parent' / 'snapshot.json'
            )

            with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
                exit_code, stdout, stderr = _run_cli_raw(
                    *_url_args(),
                    *_output_args(output_path),
                )

            output_exists = output_path.exists()

        mock_fetch.assert_not_called()
        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertFalse(output_exists)
        self.assertIn(f'target={output_path}', stderr)
        self.assertIn('exception=FileNotFoundError', stderr)
        self.assertIn(OUTPUT_PARENT_NOT_FOUND_ERROR, stderr)

    def test_main_outputs_from_file_error_to_stderr(self) -> None:
        """保存済みHTML読み込み時の例外に対象パスを含めること"""

        # 存在しないパスを安全に作るため、一時ディレクトリ内の名前を使う。
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / 'missing-index.html'

            exit_code, stdout, stderr = _run_cli_raw(
                *_from_file_args(missing_path)
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertIn(f'target={missing_path}', stderr)
        self.assertIn('exception=FileNotFoundError', stderr)
        self.assertNotIn('Traceback', stderr)

    def test_main_uses_no_detail_for_empty_exception_reason(self) -> None:
        """例外理由が空ならno detailを出力すること"""

        # 空メッセージの例外で、reasonの補完だけを確認する。
        with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
            mock_fetch.side_effect = RuntimeError()

            exit_code, stdout, stderr = _run_cli_raw(
                *_url_args()
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertIn('exception=RuntimeError', stderr)
        self.assertIn('reason=no detail', stderr)

    def test_main_stops_when_archive_month_page_fetch_fails(self) -> None:
        """月別ページ取得時の例外で途中結果をJSON出力しないこと"""

        def fetcher(url: str, **_kwargs: object) -> str:
            # 最初のindex.html取得だけ成功させ、月別ページ取得で失敗させる。
            if url == EXAMPLE_INDEX_URL:
                return _press_index_html()
            raise URLError(FETCH_ERROR_REASON)

        # 失敗した月別ページURLがstderrのtargetになることも確認する。
        with patch.object(
            cli,
            FETCH_PRESS_PAGE_HTML_ATTR,
            side_effect=fetcher,
        ):
            exit_code, stdout, stderr = _run_cli_raw(
                *_url_args(),
                *_archive_month_limit_args(limit=1),
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertIn(
            f'target={EXAMPLE_MAY_ARCHIVE_URL}',
            stderr,
        )
        self.assertIn('exception=URLError', stderr)
        self.assertIn(FETCH_ERROR_REASON, stderr)
        self.assertNotIn('stop_reason', stderr)

    def test_main_outputs_runtime_error_when_json_output_fails(self) -> None:
        """JSON生成時の例外もstderrへ出して終了コード1を返すこと"""

        with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
            mock_fetch.return_value = _press_index_html()

            # 取得後のJSON出力で失敗しても、同じエラー形式に揃える。
            with patch.object(cli.json, 'dumps') as mock_json_dumps:
                mock_json_dumps.side_effect = RuntimeError(
                    'json output\nfailed'
                )

                exit_code, stdout, stderr = _run_cli_raw(
                    *_url_args()
                )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertIn(
            f'target={EXAMPLE_INDEX_URL}',
            stderr,
        )
        self.assertIn('exception=RuntimeError', stderr)
        self.assertIn('reason=json output failed', stderr)
        self.assertEqual(stderr.count('\n'), 1)
        self.assertNotIn('Traceback', stderr)

    def test_main_keeps_output_file_when_stdout_flush_fails(self) -> None:
        """stdout flush失敗時も書き込み済みスナップショットを残すこと"""

        stdout = Mock()
        # argparseの色表示判定から実際のstdoutと同様に整数のfdを返す。
        stdout.fileno.return_value = 1
        stdout.flush.side_effect = BrokenPipeError('flush failed')
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / 'snapshot.json'

            with (
                patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch,
                patch(
                    'sys.argv',
                    _cli_argv(
                        *_url_args(),
                        *_output_args(output_path),
                    ),
                ),
                patch.object(cli.sys, 'stdout', stdout),
                patch.object(
                    cli,
                    '_redirect_stdout_after_broken_pipe',
                ) as mock_redirect,
                redirect_stderr(stderr),
            ):
                mock_fetch.return_value = _press_index_html()
                exit_code = cli.main()

            saved_payload = json.loads(
                output_path.read_text(encoding=cli.JSON_OUTPUT_ENCODING)
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(saved_payload['count'], 2)
        self.assertIn('target=stdout', stderr.getvalue())
        self.assertIn('exception=BrokenPipeError', stderr.getvalue())
        self.assertIn('reason=flush failed', stderr.getvalue())
        self.assertEqual(stderr.getvalue().count('\n'), 1)
        self.assertNotIn('Traceback', stderr.getvalue())
        stdout.write.assert_called_once()
        stdout.flush.assert_called_once_with()
        mock_redirect.assert_called_once_with(stdout)

    def test_redirect_stdout_after_broken_pipe_replaces_stdout_fd(
        self,
    ) -> None:
        """BrokenPipeError後のstdoutを破棄先へ切り替えること"""

        stdout = Mock()
        stdout.fileno.return_value = 42

        with (
            patch.object(cli.sys, 'stdout', stdout),
            patch.object(cli.os, 'open', return_value=99) as mock_open,
            patch.object(cli.os, 'dup2') as mock_dup2,
            patch.object(cli.os, 'close') as mock_close,
        ):
            cli._redirect_stdout_after_broken_pipe(stdout)

        stdout.fileno.assert_called_once_with()
        mock_open.assert_called_once_with(cli.os.devnull, cli.os.O_WRONLY)
        mock_dup2.assert_called_once_with(99, 42)
        mock_close.assert_called_once_with(99)

    def test_redirect_stdout_after_broken_pipe_closes_fd_when_dup2_fails(
        self,
    ) -> None:
        """stdoutの切り替え失敗時も破棄先のfdを閉じること"""

        stdout = Mock()
        stdout.fileno.return_value = 42

        with (
            patch.object(cli.sys, 'stdout', stdout),
            patch.object(cli.os, 'open', return_value=99),
            patch.object(
                cli.os,
                'dup2',
                side_effect=OSError('redirect failed'),
            ) as mock_dup2,
            patch.object(cli.os, 'close') as mock_close,
        ):
            cli._redirect_stdout_after_broken_pipe(stdout)

        mock_dup2.assert_called_once_with(99, 42)
        mock_close.assert_called_once_with(99)

    # ユーザー中断や明示終了は通常の実行時エラーにしない。
    def test_main_does_not_catch_keyboard_interrupt(self) -> None:
        """KeyboardInterruptは捕捉しないこと"""

        with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
            mock_fetch.side_effect = KeyboardInterrupt()

            with self.assertRaises(KeyboardInterrupt):
                _run_cli_raw(*_url_args())

    def test_main_does_not_catch_system_exit(self) -> None:
        """SystemExitは捕捉しないこと"""

        with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
            mock_fetch.side_effect = SystemExit(99)

            with self.assertRaises(SystemExit) as raised:
                _run_cli_raw(*_url_args())

        self.assertEqual(raised.exception.code, 99)


if __name__ == '__main__':
    unittest.main()

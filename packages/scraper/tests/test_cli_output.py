"""scraper CLIの結果・進捗出力と、失敗時の出力ファイル保全を検証"""

from collections.abc import Callable
from contextlib import redirect_stderr
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

    def test_print_runtime_error_redacts_url_credentials(self) -> None:
        """エラー対象と理由に含まれるURL認証情報を伏せること"""

        credential_url = (
            'https://user:password@example.com/press/index.html'
        )
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            cli._print_runtime_error(
                credential_url,
                RuntimeError(f'invalid URL: {credential_url}'),
            )

        self.assertNotIn('user:password', stderr.getvalue())
        self.assertEqual(
            stderr.getvalue().count('https://[redacted]@example.com'),
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

    def test_print_progress_sanitizes_message(self) -> None:
        """verbose進捗の認証情報と制御文字をstderrへ出さないこと"""

        credential_url = (
            'https://user:password@example.com/press/index.html'
        )
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            cli._print_progress(
                True,
                f'fetching index: {credential_url}\ninjected=true\x1b[31m',
            )

        self.assertEqual(len(stderr.getvalue().splitlines()), 1)
        self.assertNotIn('user:password', stderr.getvalue())
        self.assertNotIn('\x1b', stderr.getvalue())
        self.assertIn(
            (
                'fetching index: '
                'https://[redacted]@example.com/press/index.html '
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

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from press_watch_scraper import __main__ as cli


FETCH_ERROR_REASON = 'network unavailable'


def _press_index_html() -> str:
    """CLIテスト用の報道発表一覧HTMLを生成"""

    return '''
    <details class='p-press-release-list__block'>
        <summary>
            <span class='p-press-release-list__heading'>
                2026年05月01日発表
            </span>
        </summary>
        <ul>
            <li>
                <span class='p-news-link__tag'>総合政策</span>
                <a href='/press/press_00001.html' class='c-news-link__link'>
                    1件目の発表
                </a>
            </li>
            <li>
                <a href='/press/press_00002.html' class='c-news-link__link'>
                    2件目の発表
                </a>
            </li>
        </ul>
    </details>
    <a href='/press/202605.html' class='c-table-month__col__link' aria-label='2026年5月'>
        5月
    </a>
    <a href='/press/202604.html' class='c-table-month__col__link' aria-label='2026年4月'>
        4月
    </a>
    '''


def _archive_page_html(title: str, href: str) -> str:
    """CLIテスト用の月別ページHTMLを生成"""

    return f'''
    <details class='p-press-release-list__block'>
        <summary>
            <span class='p-press-release-list__heading'>
                2026年05月01日発表
            </span>
        </summary>
        <a href='{href}' class='c-news-link__link'>
            {title}
        </a>
    </details>
    '''


def _run_cli(args: list[str]) -> dict[str, object]:
    """CLIを実行してJSON出力と終了コードを取得"""

    exit_code, stdout, _stderr = _run_cli_raw(args)

    payload = json.loads(stdout)
    payload['exit_code'] = exit_code
    return payload


def _run_cli_raw(args: list[str]) -> tuple[int, str, str]:
    """CLIを実行して終了コード、stdout、stderrを取得"""

    stdout = io.StringIO()
    stderr = io.StringIO()

    # main()を直接呼ぶため、CLI引数と標準出力をテスト内で差し替える。
    with patch('sys.argv', ['press-watch-scraper', *args]):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli.main()

    return exit_code, stdout.getvalue(), stderr.getvalue()


class ScraperCliTest(unittest.TestCase):
    """スクレイパーCLIのテスト"""

    # 入力元ごとのJSON出力と月別巡回の結果を確認する。
    def test_main_reads_html_from_file_and_outputs_json(self) -> None:
        """保存済みHTMLを読み込んでJSONを出力すること"""

        # --from-fileで読み込ませるHTMLを、一時ディレクトリ内に用意する。
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / 'index.html'
            html_path.write_text(_press_index_html(), encoding='utf-8')

            payload = _run_cli(['--from-file', str(html_path)])

        self.assertEqual(payload['exit_code'], 0)
        self.assertEqual(payload['source_url'], str(html_path))
        self.assertEqual(payload['count'], 2)
        self.assertEqual(payload['fetched_page_urls'], [])
        self.assertIsNone(payload['stop_reason'])
        self.assertEqual(payload['archive_month_link_count'], 2)
        self.assertEqual(
            payload['archive_month_link_count'],
            len(payload['archive_month_links']),
        )
        self.assertEqual(
            payload['archive_month_links'],
            [
                {
                    'year': 2026,
                    'month': 5,
                    'url': 'https://www.env.go.jp/press/202605.html',
                },
                {
                    'year': 2026,
                    'month': 4,
                    'url': 'https://www.env.go.jp/press/202604.html',
                },
            ],
        )
        self.assertEqual(len(payload['items']), 2)
        self.assertEqual(
            payload['items'][0],
            {
                'title': '1件目の発表',
                'published_at': '2026-05-01',
                'url': 'https://www.env.go.jp/press/press_00001.html',
                'source_categories': ['総合政策'],
            },
        )
        self.assertEqual(
            payload['items'][1],
            {
                'title': '2件目の発表',
                'published_at': '2026-05-01',
                'url': 'https://www.env.go.jp/press/press_00002.html',
                'source_categories': [],
            },
        )

    def test_main_uses_url_fetch_when_from_file_is_not_given(self) -> None:
        """HTMLファイル未指定時にURLから取得すること"""

        # 実HTTP取得を避け、CLIの引数解釈とJSON出力を確認する。
        with patch.object(cli, 'fetch_press_index_html') as mock_fetch:
            mock_fetch.return_value = _press_index_html()

            payload = _run_cli(
                ['--url', 'https://example.com/press/index.html']
            )

        mock_fetch.assert_called_once_with(
            'https://example.com/press/index.html'
        )
        self.assertEqual(payload['exit_code'], 0)
        self.assertEqual(
            payload['source_url'],
            'https://example.com/press/index.html',
        )
        self.assertEqual(payload['count'], 2)
        self.assertEqual(
            payload['fetched_page_urls'],
            ['https://example.com/press/index.html'],
        )
        self.assertIsNone(payload['stop_reason'])
        self.assertEqual(
            payload['items'][0]['url'],
            'https://example.com/press/press_00001.html',
        )
        self.assertEqual(
            payload['archive_month_links'][0]['url'],
            'https://example.com/press/202605.html',
        )

    def test_main_fetches_archive_month_pages_when_limit_is_given(
        self,
    ) -> None:
        """月別ページ数指定時に月別ページ由来のJSONを出力すること"""

        html_by_url = {
            'https://example.com/press/index.html': _press_index_html(),
            'https://example.com/press/202605.html': _archive_page_html(
                '5月の発表',
                '/press/may.html',
            ),
            'https://example.com/press/202604.html': _archive_page_html(
                '4月の発表',
                '/press/april.html',
            ),
        }
        fetched_urls: list[str] = []

        def fetcher(url: str) -> str:
            # どの順番でURL取得されたかも確認できるように記録する。
            fetched_urls.append(url)
            return html_by_url[url]

        # URLごとに用意したHTMLを返し、実HTTP取得を避ける。
        with patch.object(cli, 'fetch_press_index_html', side_effect=fetcher):
            payload = _run_cli(
                [
                    '--url',
                    'https://example.com/press/index.html',
                    '--archive-month-limit',
                    '2',
                ]
            )

        self.assertEqual(payload['exit_code'], 0)
        self.assertEqual(
            fetched_urls,
            [
                'https://example.com/press/index.html',
                'https://example.com/press/202605.html',
                'https://example.com/press/202604.html',
            ],
        )
        self.assertEqual(
            payload['source_url'],
            'https://example.com/press/index.html',
        )
        self.assertEqual(payload['count'], 2)
        self.assertEqual(
            payload['fetched_page_urls'],
            [
                'https://example.com/press/202605.html',
                'https://example.com/press/202604.html',
            ],
        )
        self.assertEqual(
            payload['stop_reason'],
            'archive_month_links_exhausted',
        )
        self.assertEqual(
            [item['title'] for item in payload['items']],
            ['5月の発表', '4月の発表'],
        )

    def test_main_outputs_stop_reason_when_archive_month_limit_is_reached(
        self,
    ) -> None:
        """月別ページ数上限で止まった理由をJSONに出力すること"""

        html_by_url = {
            'https://example.com/press/index.html': _press_index_html(),
            'https://example.com/press/202605.html': _archive_page_html(
                '5月の発表',
                '/press/may.html',
            ),
        }

        def fetcher(url: str) -> str:
            return html_by_url[url]

        # 月別リンクが複数ある状態で、limit=1の停止理由を確認する。
        with patch.object(cli, 'fetch_press_index_html', side_effect=fetcher):
            payload = _run_cli(
                [
                    '--url',
                    'https://example.com/press/index.html',
                    '--archive-month-limit',
                    '1',
                ]
            )

        self.assertEqual(payload['count'], 1)
        self.assertEqual(
            payload['fetched_page_urls'],
            ['https://example.com/press/202605.html'],
        )
        self.assertEqual(
            payload['stop_reason'],
            'archive_month_limit_reached',
        )

    # argparseが終了コード2で拒否するケースを確認する。
    def test_main_rejects_from_file_with_archive_month_limit(self) -> None:
        """保存済みHTMLと月別ページ巡回指定の併用を拒否すること"""

        stderr = io.StringIO()

        # 存在するHTMLファイルを渡し、エラー理由が引数の組み合わせに絞られるようにする。
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / 'index.html'
            html_path.write_text(_press_index_html(), encoding='utf-8')

            # argparseのエラー経路を見るため、sys.argvを直接差し替える。
            with patch(
                'sys.argv',
                [
                    'press-watch-scraper',
                    '--from-file',
                    str(html_path),
                    '--archive-month-limit',
                    '1',
                ],
            ):
                with redirect_stderr(stderr):
                    # parser.errorはSystemExitを送出するため、ここで捕まえる。
                    with self.assertRaises(SystemExit) as raised:
                        cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            '--from-file cannot be used with --archive-month-limit',
            stderr.getvalue(),
        )

    def test_main_rejects_negative_archive_month_limit(self) -> None:
        """負の月別ページ数指定を拒否すること"""

        stderr = io.StringIO()

        # argparseのエラー経路を見るため、sys.argvを直接差し替える。
        with patch(
            'sys.argv',
            [
                'press-watch-scraper',
                '--archive-month-limit',
                '-1',
            ],
        ):
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            '--archive-month-limit must be greater than or equal to 0',
            stderr.getvalue(),
        )

    # 実行時エラーでは、stderr、終了コード、途中JSONを出さないことを確認する。
    def test_main_outputs_runtime_error_to_stderr_on_fetch_error(
        self,
    ) -> None:
        """HTML取得時の例外をstderrへ出して終了コード1を返すこと"""

        # URL取得だけを失敗させ、CLIの失敗時出力を確認する。
        with patch.object(cli, 'fetch_press_index_html') as mock_fetch:
            mock_fetch.side_effect = URLError(FETCH_ERROR_REASON)

            exit_code, stdout, stderr = _run_cli_raw(
                ['--url', 'https://example.com/press/index.html']
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertIn(
            'target=https://example.com/press/index.html',
            stderr,
        )
        self.assertIn('exception=URLError', stderr)
        self.assertIn(FETCH_ERROR_REASON, stderr)
        self.assertNotIn('Traceback', stderr)

    def test_main_outputs_from_file_error_to_stderr(self) -> None:
        """保存済みHTML読み込み時の例外に対象パスを含めること"""

        # 存在しないパスを安全に作るため、一時ディレクトリ内の名前を使う。
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / 'missing-index.html'

            exit_code, stdout, stderr = _run_cli_raw(
                ['--from-file', str(missing_path)]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertIn(f'target={missing_path}', stderr)
        self.assertIn('exception=FileNotFoundError', stderr)
        self.assertNotIn('Traceback', stderr)

    def test_main_uses_no_detail_for_empty_exception_reason(self) -> None:
        """例外理由が空ならno detailを出力すること"""

        # 空メッセージの例外で、reasonの補完だけを確認する。
        with patch.object(cli, 'fetch_press_index_html') as mock_fetch:
            mock_fetch.side_effect = RuntimeError()

            exit_code, stdout, stderr = _run_cli_raw(
                ['--url', 'https://example.com/press/index.html']
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertIn('exception=RuntimeError', stderr)
        self.assertIn('reason=no detail', stderr)

    def test_main_stops_when_archive_month_page_fetch_fails(self) -> None:
        """月別ページ取得時の例外で途中結果をJSON出力しないこと"""

        def fetcher(url: str) -> str:
            # 最初のindex.html取得だけ成功させ、月別ページ取得で失敗させる。
            if url == 'https://example.com/press/index.html':
                return _press_index_html()
            raise URLError(FETCH_ERROR_REASON)

        # 失敗した月別ページURLがstderrのtargetになることも確認する。
        with patch.object(cli, 'fetch_press_index_html', side_effect=fetcher):
            exit_code, stdout, stderr = _run_cli_raw(
                [
                    '--url',
                    'https://example.com/press/index.html',
                    '--archive-month-limit',
                    '1',
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertIn(
            'target=https://example.com/press/202605.html',
            stderr,
        )
        self.assertIn('exception=URLError', stderr)
        self.assertIn(FETCH_ERROR_REASON, stderr)
        self.assertNotIn('stop_reason', stderr)

    def test_main_outputs_runtime_error_when_json_output_fails(self) -> None:
        """JSON生成時の例外もstderrへ出して終了コード1を返すこと"""

        with patch.object(cli, 'fetch_press_index_html') as mock_fetch:
            mock_fetch.return_value = _press_index_html()

            # 取得後のJSON出力で失敗しても、同じエラー形式に揃える。
            with patch.object(cli.json, 'dumps') as mock_json_dumps:
                mock_json_dumps.side_effect = RuntimeError(
                    'json output\nfailed'
                )

                exit_code, stdout, stderr = _run_cli_raw(
                    ['--url', 'https://example.com/press/index.html']
                )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertIn(
            'target=https://example.com/press/index.html',
            stderr,
        )
        self.assertIn('exception=RuntimeError', stderr)
        self.assertIn('reason=json output failed', stderr)
        self.assertEqual(stderr.count('\n'), 1)
        self.assertNotIn('Traceback', stderr)

    # ユーザー中断や明示終了は通常の実行時エラーにしない。
    def test_main_does_not_catch_keyboard_interrupt(self) -> None:
        """KeyboardInterruptは捕捉しないこと"""

        with patch.object(cli, 'fetch_press_index_html') as mock_fetch:
            mock_fetch.side_effect = KeyboardInterrupt()

            with self.assertRaises(KeyboardInterrupt):
                _run_cli_raw(['--url', 'https://example.com/press/index.html'])

    def test_main_does_not_catch_system_exit(self) -> None:
        """SystemExitは捕捉しないこと"""

        with patch.object(cli, 'fetch_press_index_html') as mock_fetch:
            mock_fetch.side_effect = SystemExit(99)

            with self.assertRaises(SystemExit) as raised:
                _run_cli_raw(['--url', 'https://example.com/press/index.html'])

        self.assertEqual(raised.exception.code, 99)


if __name__ == '__main__':
    unittest.main()

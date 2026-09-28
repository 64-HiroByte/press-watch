"""scraper CLIの基本実行と引数の組み合わせを検証"""

from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from press_watch_scraper import __main__ as cli

from cli_test_support import (
    EXAMPLE_INDEX_URL,
    EXAMPLE_MAY_ARCHIVE_URL,
    EXAMPLE_MAY_RELEASE_URL,
    FETCH_PRESS_PAGE_HTML_ATTR,
    _all_archive_months_args,
    _archive_month_limit_args,
    _cli_argv,
    _from_file_args,
    _known_release_urls_file_args,
    _no_stdout_json_args,
    _press_index_html,
    _run_cli,
    _url_args,
)


# テスト用URL
EXAMPLE_FIRST_RELEASE_URL = 'https://example.com/press/press_00001.html'
ENV_MAY_ARCHIVE_URL = 'https://www.env.go.jp/press/202605.html'
ENV_APRIL_ARCHIVE_URL = 'https://www.env.go.jp/press/202604.html'
FIRST_RELEASE_URL = 'https://www.env.go.jp/press/press_00001.html'
SECOND_RELEASE_URL = 'https://www.env.go.jp/press/press_00002.html'

# argparseのエラーメッセージ
FROM_FILE_WITH_ARCHIVE_MONTH_LIMIT_ERROR = (
    '--from-file cannot be used with --archive-month-limit'
)
FROM_FILE_WITH_ALL_ARCHIVE_MONTHS_ERROR = (
    '--from-file cannot be used with --all-archive-months'
)
NO_STDOUT_JSON_WITHOUT_OUTPUT_ERROR = (
    '--no-stdout-json requires --output'
)
ARCHIVE_MONTH_LIMIT_WITH_ALL_ARCHIVE_MONTHS_ERROR = (
    '--archive-month-limit cannot be used with --all-archive-months'
)
NEGATIVE_ARCHIVE_MONTH_LIMIT_ERROR = (
    '--archive-month-limit must be greater than or equal to 0'
)
KNOWN_RELEASE_URLS_FILE_WITHOUT_ARCHIVE_CRAWL_ERROR = (
    '--known-release-urls-file requires '
    '--archive-month-limit greater than 0 or --all-archive-months'
)


class ScraperCliTest(unittest.TestCase):
    """スクレイパーCLIの基本実行と引数検証のテスト"""

    def test_main_reads_html_from_file_and_outputs_json(self) -> None:
        """保存済みHTMLを読み込んでJSONを出力すること"""

        # --from-fileで読み込ませるHTMLを、一時ディレクトリ内に用意する。
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / 'index.html'
            html_path.write_text(_press_index_html(), encoding='utf-8')

            payload = _run_cli(*_from_file_args(html_path))

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
                    'url': ENV_MAY_ARCHIVE_URL,
                },
                {
                    'year': 2026,
                    'month': 4,
                    'url': ENV_APRIL_ARCHIVE_URL,
                },
            ],
        )
        self.assertEqual(len(payload['items']), 2)
        self.assertEqual(
            payload['items'][0],
            {
                'title': '1件目の発表',
                'published_at': '2026-05-01',
                'url': FIRST_RELEASE_URL,
                'source_categories': ['総合政策'],
            },
        )
        self.assertEqual(
            payload['items'][1],
            {
                'title': '2件目の発表',
                'published_at': '2026-05-01',
                'url': SECOND_RELEASE_URL,
                'source_categories': [],
            },
        )

    def test_main_uses_url_fetch_when_from_file_is_not_given(self) -> None:
        """HTMLファイル未指定時にURLから取得すること"""

        # 実HTTP取得を避け、CLIの引数解釈とJSON出力を確認する。
        with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
            mock_fetch.return_value = _press_index_html()

            payload = _run_cli(*_url_args())

        mock_fetch.assert_called_once()
        self.assertEqual(mock_fetch.call_args.args, (EXAMPLE_INDEX_URL,))
        self.assertIsNotNone(mock_fetch.call_args.kwargs['rate_limiter'])
        self.assertEqual(payload['exit_code'], 0)
        self.assertEqual(
            payload['source_url'],
            EXAMPLE_INDEX_URL,
        )
        self.assertEqual(payload['count'], 2)
        self.assertEqual(
            payload['fetched_page_urls'],
            [EXAMPLE_INDEX_URL],
        )
        self.assertIsNone(payload['stop_reason'])
        self.assertEqual(
            payload['items'][0]['url'],
            EXAMPLE_FIRST_RELEASE_URL,
        )
        self.assertEqual(
            payload['archive_month_links'][0]['url'],
            EXAMPLE_MAY_ARCHIVE_URL,
        )

    def test_main_keeps_single_page_mode_when_archive_month_limit_is_zero(
        self,
    ) -> None:
        """月別ページ数0指定時は単一ページ解析のままにすること"""

        with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
            mock_fetch.return_value = _press_index_html()

            payload = _run_cli(
                *_url_args(),
                *_archive_month_limit_args(limit=0),
            )

        mock_fetch.assert_called_once()
        self.assertEqual(mock_fetch.call_args.args, (EXAMPLE_INDEX_URL,))
        self.assertIsNotNone(mock_fetch.call_args.kwargs['rate_limiter'])
        self.assertEqual(payload['exit_code'], 0)
        self.assertEqual(payload['count'], 2)
        self.assertEqual(
            payload['fetched_page_urls'],
            [EXAMPLE_INDEX_URL],
        )
        self.assertIsNone(payload['stop_reason'])

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
                _cli_argv(
                    *_from_file_args(html_path),
                    *_archive_month_limit_args(limit=1),
                ),
            ):
                with redirect_stderr(stderr):
                    # parser.errorはSystemExitを送出するため、ここで捕まえる。
                    with self.assertRaises(SystemExit) as raised:
                        cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            FROM_FILE_WITH_ARCHIVE_MONTH_LIMIT_ERROR,
            stderr.getvalue(),
        )

    def test_main_keeps_from_file_mode_when_archive_month_limit_is_zero(
        self,
    ) -> None:
        """保存済みHTMLと月別ページ数0指定なら単一ページ解析にすること"""

        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / 'index.html'
            html_path.write_text(_press_index_html(), encoding='utf-8')

            payload = _run_cli(
                *_from_file_args(html_path),
                *_archive_month_limit_args(limit=0),
            )

        self.assertEqual(payload['exit_code'], 0)
        self.assertEqual(payload['source_url'], str(html_path))
        self.assertEqual(payload['count'], 2)
        self.assertEqual(payload['fetched_page_urls'], [])
        self.assertIsNone(payload['stop_reason'])

    def test_main_rejects_from_file_with_all_archive_months(self) -> None:
        """保存済みHTMLと全件巡回フラグの併用を拒否すること"""

        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / 'index.html'
            html_path.write_text(_press_index_html(), encoding='utf-8')

            with patch(
                'sys.argv',
                _cli_argv(
                    *_from_file_args(html_path),
                    *_all_archive_months_args(),
                ),
            ):
                with redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            FROM_FILE_WITH_ALL_ARCHIVE_MONTHS_ERROR,
            stderr.getvalue(),
        )

    def test_main_rejects_archive_month_limit_with_all_archive_months(
        self,
    ) -> None:
        """月別ページ数指定と全件巡回フラグの併用を拒否すること"""

        stderr = io.StringIO()

        with patch(
            'sys.argv',
            _cli_argv(
                *_archive_month_limit_args(limit=0),
                *_all_archive_months_args(),
            ),
        ):
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            ARCHIVE_MONTH_LIMIT_WITH_ALL_ARCHIVE_MONTHS_ERROR,
            stderr.getvalue(),
        )

    def test_main_rejects_negative_archive_month_limit(self) -> None:
        """負の月別ページ数指定を拒否すること"""

        stderr = io.StringIO()

        # argparseのエラー経路を見るため、sys.argvを直接差し替える。
        with patch(
            'sys.argv',
            _cli_argv(*_archive_month_limit_args(limit=-1)),
        ):
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            NEGATIVE_ARCHIVE_MONTH_LIMIT_ERROR,
            stderr.getvalue(),
        )

    def test_main_rejects_known_release_urls_file_without_archive_crawl(
        self,
    ) -> None:
        """既知URLファイル指定だけでは月別巡回を始めないこと"""

        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            known_urls_path = Path(temp_dir) / 'known-release-urls.txt'
            known_urls_path.write_text(
                EXAMPLE_MAY_RELEASE_URL,
                encoding=cli.JSON_OUTPUT_ENCODING,
            )

            with patch(
                'sys.argv',
                _cli_argv(
                    *_known_release_urls_file_args(known_urls_path),
                ),
            ):
                with redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            KNOWN_RELEASE_URLS_FILE_WITHOUT_ARCHIVE_CRAWL_ERROR,
            stderr.getvalue(),
        )

    def test_main_rejects_no_stdout_json_without_output(self) -> None:
        """stdout JSON抑止はoutput指定なしでは拒否すること"""

        stderr = io.StringIO()

        with patch(
            'sys.argv',
            _cli_argv(*_no_stdout_json_args()),
        ):
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            NO_STDOUT_JSON_WITHOUT_OUTPUT_ERROR,
            stderr.getvalue(),
        )


if __name__ == '__main__':
    unittest.main()

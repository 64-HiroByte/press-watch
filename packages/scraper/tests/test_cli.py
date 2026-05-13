from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from press_watch_scraper import __main__ as cli


PROGRAM_NAME = 'press-watch-scraper'
FETCH_PRESS_INDEX_HTML_ATTR = 'fetch_press_index_html'

# エラー理由と既存ファイル内容
FETCH_ERROR_REASON = 'network unavailable'
EXISTING_OUTPUT_JSON = '{"status": "existing"}\n'
OUTPUT_PARENT_NOT_FOUND_ERROR = 'output parent directory does not exist'

# テスト用URL
EXAMPLE_INDEX_URL = 'https://example.com/press/index.html'
EXAMPLE_MAY_ARCHIVE_URL = 'https://example.com/press/202605.html'
EXAMPLE_APRIL_ARCHIVE_URL = 'https://example.com/press/202604.html'
EXAMPLE_FIRST_RELEASE_URL = 'https://example.com/press/press_00001.html'
ENV_MAY_ARCHIVE_URL = 'https://www.env.go.jp/press/202605.html'
ENV_APRIL_ARCHIVE_URL = 'https://www.env.go.jp/press/202604.html'
FIRST_RELEASE_URL = 'https://www.env.go.jp/press/press_00001.html'
SECOND_RELEASE_URL = 'https://www.env.go.jp/press/press_00002.html'

# 月別巡回の期待値
MAY_RELEASE_TITLE = '5月の発表'
APRIL_RELEASE_TITLE = '4月の発表'
MAY_RELEASE_PATH = '/press/may.html'
APRIL_RELEASE_PATH = '/press/april.html'
ARCHIVE_MONTH_LINKS_EXHAUSTED = 'archive_month_links_exhausted'
ARCHIVE_MONTH_LIMIT_REACHED = 'archive_month_limit_reached'

# CLI引数
ALL_ARCHIVE_MONTHS_ARG = '--all-archive-months'
ARCHIVE_MONTH_LIMIT_ARG = '--archive-month-limit'
FROM_FILE_ARG = '--from-file'
NO_STDOUT_JSON_ARG = '--no-stdout-json'
OUTPUT_ARG = '--output'
URL_ARG = '--url'
VERBOSE_ARG = '--verbose'

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


def _press_index_html() -> str:
    """CLIテスト用の報道発表一覧HTMLを生成

    Returns:
        報道発表2件と月別リンク2件を含むHTML
    """

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
    """CLIテスト用の月別ページHTMLを生成

    Args:
        title: 月別ページに含める報道発表タイトル
        href: 報道発表リンクのhref属性値

    Returns:
        報道発表1件を含む月別ページHTML
    """

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


def _archive_html_by_url(
    *,
    include_april: bool = True,
) -> dict[str, str]:
    """CLIテスト用の月別巡回HTMLをURLごとに用意

    Args:
        include_april: 4月の月別ページHTMLも含めるかどうか

    Returns:
        取得URLをキー、返却するHTMLを値にした辞書
    """

    html_by_url = {
        EXAMPLE_INDEX_URL: _press_index_html(),
        EXAMPLE_MAY_ARCHIVE_URL: _archive_page_html(
            MAY_RELEASE_TITLE,
            MAY_RELEASE_PATH,
        ),
    }
    if include_april:
        html_by_url[EXAMPLE_APRIL_ARCHIVE_URL] = _archive_page_html(
            APRIL_RELEASE_TITLE,
            APRIL_RELEASE_PATH,
        )
    return html_by_url


def _recording_html_fetcher(
    html_by_url: dict[str, str],
    fetched_urls: list[str],
) -> Callable[[str], str]:
    """取得URLを記録するCLIテスト用fetcherを生成

    Args:
        html_by_url: 取得URLごとに返すHTMLの辞書
        fetched_urls: fetcherが呼ばれたURLの記録先リスト

    Returns:
        URLを受け取り、記録後に対応するHTMLを返す関数
    """

    def fetcher(url: str) -> str:
        fetched_urls.append(url)
        return html_by_url[url]

    return fetcher


def _url_args(url: str = EXAMPLE_INDEX_URL) -> tuple[str, str]:
    """URL取得モードのCLI引数を生成

    Args:
        url: `--url` に渡す取得対象URL

    Returns:
        `--url` とURL値の引数列
    """

    return (URL_ARG, url)


def _from_file_args(path: Path) -> tuple[str, str]:
    """保存済みHTML読み込みモードのCLI引数を生成

    Args:
        path: `--from-file` に渡すHTMLファイルパス

    Returns:
        `--from-file` とファイルパス値の引数列
    """

    return (FROM_FILE_ARG, str(path))


def _output_args(path: Path) -> tuple[str, str]:
    """JSONスナップショット出力先のCLI引数を生成

    Args:
        path: `--output` に渡す出力先パス

    Returns:
        `--output` と出力先パス値の引数列
    """

    return (OUTPUT_ARG, str(path))


def _no_stdout_json_args() -> tuple[str]:
    """stdout JSON抑止のCLI引数を生成

    Returns:
        `--no-stdout-json` の引数列
    """

    return (NO_STDOUT_JSON_ARG,)


def _verbose_args() -> tuple[str]:
    """進捗表示のCLI引数を生成

    Returns:
        `--verbose` の引数列
    """

    return (VERBOSE_ARG,)


def _archive_month_limit_args(limit: int) -> tuple[str, str]:
    """月別ページ数指定のCLI引数を生成

    Args:
        limit: `--archive-month-limit` に渡す月別ページ数

    Returns:
        `--archive-month-limit` と件数値の引数列
    """

    return (ARCHIVE_MONTH_LIMIT_ARG, str(limit))


def _all_archive_months_args() -> tuple[str]:
    """全月別ページ巡回のCLI引数を生成

    Returns:
        `--all-archive-months` の引数列
    """

    return (ALL_ARCHIVE_MONTHS_ARG,)


def _cli_argv(*args: str) -> list[str]:
    """sys.argv用にプログラム名付きのCLI引数列を生成

    Args:
        args: プログラム名を除くCLI引数

    Returns:
        先頭にプログラム名を付けた `sys.argv` 用の引数列
    """

    return [PROGRAM_NAME, *args]


def _run_cli(*args: str) -> dict[str, object]:
    """CLIを実行してJSON出力と終了コードを取得

    Args:
        args: プログラム名を除くCLI引数。`_url_args()` や
            `_archive_month_limit_args()` などで生成した値を展開して渡す。
            例: `*_url_args(), *_archive_month_limit_args(limit=1)`

    Returns:
        stdoutのJSONへ終了コードを加えた辞書
    """

    exit_code, stdout, _stderr = _run_cli_raw(*args)

    payload = json.loads(stdout)
    payload['exit_code'] = exit_code
    return payload


def _run_cli_raw(
    *args: str,
    request_interval_seconds: float = 3.0,
) -> tuple[int, str, str]:
    """CLIを実行して終了コード、stdout、stderrを取得

    Args:
        args: プログラム名を除くCLI引数。stderrを検証したい失敗系で使う。
            例: `*_from_file_args(path), *_all_archive_months_args()`
        request_interval_seconds: テスト時に差し替える巡回待機秒数

    Returns:
        終了コード、stdout、stderr
    """

    stdout = io.StringIO()
    stderr = io.StringIO()

    # main()を直接呼ぶため、CLI引数・標準出力・巡回待機をテスト内で差し替える。
    with patch('sys.argv', _cli_argv(*args)):
        with patch.object(
            cli,
            'REQUEST_INTERVAL_SECONDS',
            request_interval_seconds,
        ):
            with patch.object(cli, 'sleep', create=True) as mock_sleep:
                mock_sleep.return_value = None
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

    def test_main_uses_url_fetch_when_from_file_is_not_given(self) -> None:
        """HTMLファイル未指定時にURLから取得すること"""

        # 実HTTP取得を避け、CLIの引数解釈とJSON出力を確認する。
        with patch.object(cli, FETCH_PRESS_INDEX_HTML_ATTR) as mock_fetch:
            mock_fetch.return_value = _press_index_html()

            payload = _run_cli(*_url_args())

        mock_fetch.assert_called_once_with(EXAMPLE_INDEX_URL)
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

    def test_main_fetches_archive_month_pages_when_limit_is_given(
        self,
    ) -> None:
        """月別ページ数指定時に月別ページ由来のJSONを出力すること"""

        html_by_url = _archive_html_by_url()
        fetched_urls: list[str] = []

        # URLごとに用意したHTMLを返し、実HTTP取得を避ける。
        with patch.object(
            cli,
            FETCH_PRESS_INDEX_HTML_ATTR,
            side_effect=_recording_html_fetcher(html_by_url, fetched_urls),
        ):
            payload = _run_cli(
                *_url_args(),
                *_archive_month_limit_args(limit=2),
            )

        self.assertEqual(payload['exit_code'], 0)
        self.assertEqual(
            fetched_urls,
            [
                EXAMPLE_INDEX_URL,
                EXAMPLE_MAY_ARCHIVE_URL,
                EXAMPLE_APRIL_ARCHIVE_URL,
            ],
        )
        self.assertEqual(
            payload['source_url'],
            EXAMPLE_INDEX_URL,
        )
        self.assertEqual(payload['count'], 2)
        self.assertEqual(
            payload['fetched_page_urls'],
            [
                EXAMPLE_MAY_ARCHIVE_URL,
                EXAMPLE_APRIL_ARCHIVE_URL,
            ],
        )
        self.assertEqual(
            payload['stop_reason'],
            ARCHIVE_MONTH_LINKS_EXHAUSTED,
        )
        self.assertEqual(
            [item['title'] for item in payload['items']],
            [MAY_RELEASE_TITLE, APRIL_RELEASE_TITLE],
        )

    def test_main_outputs_progress_to_stderr_when_verbose(self) -> None:
        """verbose指定時に月別巡回の進捗をstderrへ出すこと"""

        html_by_url = _archive_html_by_url()

        with patch.object(
            cli,
            FETCH_PRESS_INDEX_HTML_ATTR,
            side_effect=html_by_url.__getitem__,
        ):
            exit_code, stdout, stderr = _run_cli_raw(
                *_url_args(),
                *_archive_month_limit_args(limit=2),
                *_verbose_args(),
                request_interval_seconds=3.0,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout)['count'], 2)
        self.assertIn(f'fetching index: {EXAMPLE_INDEX_URL}', stderr)
        self.assertIn(
            'waiting 3s before fetching archive page',
            stderr,
        )
        self.assertIn(
            f'fetching archive page: {EXAMPLE_MAY_ARCHIVE_URL}',
            stderr,
        )
        self.assertIn(
            f'fetching archive page: {EXAMPLE_APRIL_ARCHIVE_URL}',
            stderr,
        )

    def test_main_can_show_progress_without_stdout_json(self) -> None:
        """stdout JSONを出さずにstderrの進捗だけ確認できること"""

        html_by_url = _archive_html_by_url(include_april=False)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / 'snapshot.json'

            with patch.object(
                cli,
                FETCH_PRESS_INDEX_HTML_ATTR,
                side_effect=html_by_url.__getitem__,
            ):
                exit_code, stdout, stderr = _run_cli_raw(
                    *_url_args(),
                    *_archive_month_limit_args(limit=1),
                    *_verbose_args(),
                    *_no_stdout_json_args(),
                    *_output_args(output_path),
                    request_interval_seconds=3.0,
                )

            saved_payload = json.loads(
                output_path.read_text(encoding=cli.JSON_OUTPUT_ENCODING)
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, '')
        self.assertEqual(saved_payload['count'], 1)
        self.assertIn(f'fetching index: {EXAMPLE_INDEX_URL}', stderr)
        self.assertIn(
            'waiting 3s before fetching archive page',
            stderr,
        )
        self.assertIn(
            f'fetching archive page: {EXAMPLE_MAY_ARCHIVE_URL}',
            stderr,
        )

    def test_main_outputs_stop_reason_when_archive_month_limit_is_reached(
        self,
    ) -> None:
        """月別ページ数上限で止まった理由をJSONに出力すること"""

        html_by_url = _archive_html_by_url(include_april=False)

        # 月別リンクが複数ある状態で、limit=1の停止理由を確認する。
        with patch.object(
            cli,
            FETCH_PRESS_INDEX_HTML_ATTR,
            side_effect=html_by_url.__getitem__,
        ):
            payload = _run_cli(
                *_url_args(),
                *_archive_month_limit_args(limit=1),
            )

        self.assertEqual(payload['count'], 1)
        self.assertEqual(
            payload['fetched_page_urls'],
            [EXAMPLE_MAY_ARCHIVE_URL],
        )
        self.assertEqual(
            payload['stop_reason'],
            ARCHIVE_MONTH_LIMIT_REACHED,
        )

    def test_main_fetches_all_archive_month_pages_when_flag_is_given(
        self,
    ) -> None:
        """全件巡回フラグ指定時に月別ページ候補をすべて取得すること"""

        html_by_url = _archive_html_by_url()
        fetched_urls: list[str] = []

        with patch.object(
            cli,
            FETCH_PRESS_INDEX_HTML_ATTR,
            side_effect=_recording_html_fetcher(html_by_url, fetched_urls),
        ):
            payload = _run_cli(
                *_url_args(),
                *_all_archive_months_args(),
            )

        self.assertEqual(payload['exit_code'], 0)
        self.assertEqual(
            fetched_urls,
            [
                EXAMPLE_INDEX_URL,
                EXAMPLE_MAY_ARCHIVE_URL,
                EXAMPLE_APRIL_ARCHIVE_URL,
            ],
        )
        self.assertEqual(payload['count'], 2)
        self.assertEqual(
            payload['fetched_page_urls'],
            [
                EXAMPLE_MAY_ARCHIVE_URL,
                EXAMPLE_APRIL_ARCHIVE_URL,
            ],
        )
        self.assertEqual(
            payload['stop_reason'],
            ARCHIVE_MONTH_LINKS_EXHAUSTED,
        )
        self.assertEqual(
            [item['title'] for item in payload['items']],
            [MAY_RELEASE_TITLE, APRIL_RELEASE_TITLE],
        )

    def test_main_keeps_single_page_mode_when_archive_month_limit_is_zero(
        self,
    ) -> None:
        """月別ページ数0指定時は単一ページ解析のままにすること"""

        with patch.object(cli, FETCH_PRESS_INDEX_HTML_ATTR) as mock_fetch:
            mock_fetch.return_value = _press_index_html()

            payload = _run_cli(
                *_url_args(),
                *_archive_month_limit_args(limit=0),
            )

        mock_fetch.assert_called_once_with(EXAMPLE_INDEX_URL)
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

    # 実行時エラーでは、stderr、終了コード、途中JSONを出さないことを確認する。
    def test_main_outputs_runtime_error_to_stderr_on_fetch_error(
        self,
    ) -> None:
        """HTML取得時の例外をstderrへ出して終了コード1を返すこと"""

        # URL取得だけを失敗させ、CLIの失敗時出力を確認する。
        with patch.object(cli, FETCH_PRESS_INDEX_HTML_ATTR) as mock_fetch:
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

    def test_main_does_not_create_output_file_on_fetch_error(self) -> None:
        """HTML取得失敗時にJSONスナップショットを作成しないこと"""

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / 'snapshot.json'

            with patch.object(cli, FETCH_PRESS_INDEX_HTML_ATTR) as mock_fetch:
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

            with patch.object(cli, FETCH_PRESS_INDEX_HTML_ATTR) as mock_fetch:
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

            with patch.object(cli, FETCH_PRESS_INDEX_HTML_ATTR) as mock_fetch:
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
        with patch.object(cli, FETCH_PRESS_INDEX_HTML_ATTR) as mock_fetch:
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

        def fetcher(url: str) -> str:
            # 最初のindex.html取得だけ成功させ、月別ページ取得で失敗させる。
            if url == EXAMPLE_INDEX_URL:
                return _press_index_html()
            raise URLError(FETCH_ERROR_REASON)

        # 失敗した月別ページURLがstderrのtargetになることも確認する。
        with patch.object(
            cli,
            FETCH_PRESS_INDEX_HTML_ATTR,
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

        with patch.object(cli, FETCH_PRESS_INDEX_HTML_ATTR) as mock_fetch:
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

    # ユーザー中断や明示終了は通常の実行時エラーにしない。
    def test_main_does_not_catch_keyboard_interrupt(self) -> None:
        """KeyboardInterruptは捕捉しないこと"""

        with patch.object(cli, FETCH_PRESS_INDEX_HTML_ATTR) as mock_fetch:
            mock_fetch.side_effect = KeyboardInterrupt()

            with self.assertRaises(KeyboardInterrupt):
                _run_cli_raw(*_url_args())

    def test_main_does_not_catch_system_exit(self) -> None:
        """SystemExitは捕捉しないこと"""

        with patch.object(cli, FETCH_PRESS_INDEX_HTML_ATTR) as mock_fetch:
            mock_fetch.side_effect = SystemExit(99)

            with self.assertRaises(SystemExit) as raised:
                _run_cli_raw(*_url_args())

        self.assertEqual(raised.exception.code, 99)


if __name__ == '__main__':
    unittest.main()

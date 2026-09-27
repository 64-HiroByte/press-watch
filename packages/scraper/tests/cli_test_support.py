"""scraper CLIテストで共有するHTML、引数生成、出力取得の補助処理"""

from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
from unittest.mock import patch

from press_watch_scraper import __main__ as cli


PROGRAM_NAME = 'press-watch-scraper'
FETCH_PRESS_PAGE_HTML_ATTR = 'fetch_press_page_html'

# エラー理由と既存ファイル内容
FETCH_ERROR_REASON = 'network unavailable'
EXISTING_OUTPUT_JSON = '{"status": "existing"}\n'

# テスト用URL
EXAMPLE_INDEX_URL = 'https://example.com/press/index.html'
EXAMPLE_MAY_ARCHIVE_URL = 'https://example.com/press/202605.html'
EXAMPLE_APRIL_ARCHIVE_URL = 'https://example.com/press/202604.html'
EXAMPLE_MAY_RELEASE_URL = 'https://example.com/press/may.html'

# 月別巡回の期待値
MAY_RELEASE_TITLE = '5月の発表'
APRIL_RELEASE_TITLE = '4月の発表'
MAY_RELEASE_PATH = '/press/may.html'
APRIL_RELEASE_PATH = '/press/april.html'

# CLI引数
ALL_ARCHIVE_MONTHS_ARG = '--all-archive-months'
ARCHIVE_MONTH_LIMIT_ARG = '--archive-month-limit'
FROM_FILE_ARG = '--from-file'
KNOWN_RELEASE_URLS_FILE_ARG = '--known-release-urls-file'
NO_STDOUT_JSON_ARG = '--no-stdout-json'
OUTPUT_ARG = '--output'
URL_ARG = '--url'
VERBOSE_ARG = '--verbose'


class _FakeClock:
    """sleepの呼び出しでのみ時刻を進める、要求間隔テスト用の時計

    sleepは待機せず内部時刻へ秒数を加算し、時計を呼び出すとその時刻を返却
    """

    def __init__(self) -> None:
        self.current = 0.0

    def __call__(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += seconds


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
    """HTTP要求を行わず、取得URLを記録して用意したHTMLを返す関数を生成

    Args:
        html_by_url: 取得URLごとに返すHTMLの辞書
        fetched_urls: 呼び出されたURLを順に追記するリスト

    Returns:
        URLを受け取り、記録後に対応するHTMLを返す関数
    """

    def fetcher(url: str, **_kwargs: object) -> str:
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


def _known_release_urls_file_args(path: Path) -> tuple[str, str]:
    """既知URLファイル指定のCLI引数を生成

    Args:
        path: `--known-release-urls-file` に渡すファイルパス

    Returns:
        `--known-release-urls-file` とファイルパス値の引数列
    """

    return (KNOWN_RELEASE_URLS_FILE_ARG, str(path))


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
    """CLIのstdoutをJSONとして読み込み、終了コードを加えて取得

    stdoutにJSONが出るケース用。JSONが出ない場合やstderrも検証する場合は
    _run_cli_rawを利用。HTML取得の差し替えは呼び出し元で実施

    Args:
        args: プログラム名を除くCLI引数。`_url_args()` や
            `_archive_month_limit_args()` などで生成した値を展開して渡す
            例: `*_url_args(), *_archive_month_limit_args(limit=1)`

    Returns:
        stdoutのJSONへ終了コードを加えた辞書
    """

    exit_code, stdout, _stderr = _run_cli_raw(*args)

    payload = json.loads(stdout)
    payload['exit_code'] = exit_code
    return payload


def _run_cli_raw(*args: str) -> tuple[int, str, str]:
    """CLIを実行して終了コード、stdout、stderrを取得

    呼び出しごとに出力バッファと仮想時計を生成し、巡回待機を置換
    HTML取得は差し替えないため、URLから取得するケースでは呼び出し元でMockを用意
    mainが送出した例外は捕捉せず、引数・時計・標準出力のpatchは終了時に復元

    Args:
        args: プログラム名を除くCLI引数
            例: `*_from_file_args(path), *_output_args(output_path)`

    Returns:
        終了コード、stdoutの内容、stderrの内容をこの順に格納したタプル
    """

    stdout = io.StringIO()
    stderr = io.StringIO()
    fake_clock = _FakeClock()

    # main()を直接呼ぶため、CLI引数・標準出力・巡回待機をテスト内で差し替える。
    with patch('sys.argv', _cli_argv(*args)):
        with patch.object(cli, 'monotonic', fake_clock):
            with patch.object(cli, 'sleep', fake_clock.sleep):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = cli.main()

    return exit_code, stdout.getvalue(), stderr.getvalue()

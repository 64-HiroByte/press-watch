from collections.abc import Callable, Collection
import unittest
from urllib.error import URLError

from press_watch_scraper.env_press import (
    REQUEST_INTERVAL_SECONDS,
    PressReleaseCrawlResult,
    crawl_press_releases,
)


START_URL = 'https://example.com/press/index.html'
MAY_ARCHIVE_PATH = '/press/202605.html'
APRIL_ARCHIVE_PATH = '/press/202604.html'
MAY_ARCHIVE_URL = 'https://example.com/press/202605.html'
APRIL_ARCHIVE_URL = 'https://example.com/press/202604.html'
KNOWN_RELEASE_URL = 'https://example.com/press/known.html'
MAY_RELEASE_TITLE = '5月の発表'
APRIL_RELEASE_TITLE = '4月の発表'
DUPLICATED_RELEASE_TITLE = '重複する発表'
KNOWN_RELEASE_TITLE = '既知の発表'
INDEX_ONLY_RELEASE_TITLE = 'トップページだけの発表'
MAY_RELEASE_PATH = '/press/may.html'
APRIL_RELEASE_PATH = '/press/april.html'
DUPLICATED_RELEASE_PATH = '/press/duplicated.html'
KNOWN_RELEASE_PATH = '/press/known.html'
INDEX_ONLY_RELEASE_PATH = '/press/index_only.html'
MAY_HEADING = '2026年05月01日発表'
APRIL_HEADING = '2026年04月30日発表'
MAY_ARIA_LABEL = '2026年5月'
MAY_ARIA_LABEL_ZERO_PADDED = '2026年05月'
APRIL_ARIA_LABEL = '2026年4月'
ARCHIVE_MONTH_LINKS_EXHAUSTED = 'archive_month_links_exhausted'
ARCHIVE_MONTH_LIMIT_REACHED = 'archive_month_limit_reached'
DUPLICATE_RELEASE_DETECTED = 'duplicate_release_detected'
FETCH_ERROR_REASON = 'network unavailable'


def _no_sleep(_seconds: float) -> None:
    """巡回テストで実時間待機を避けるためのsleeper"""

    return None


def _press_release_block(
    heading: str,
    href: str,
    title: str,
) -> str:
    """クロールテスト用の報道発表HTML断片を生成

    Args:
        heading: 報道発表日の見出し文字列
        href: 報道発表リンクのhref属性値
        title: 報道発表タイトル

    Returns:
        報道発表1件を含むHTML断片
    """

    return f'''
    <details class='p-press-release-list__block'>
        <summary>
            <span class='p-press-release-list__heading'>
                {heading}
            </span>
        </summary>
        <a href='{href}' class='c-news-link__link'>
            {title}
        </a>
    </details>
    '''


def _archive_month_link(
    aria_label: str,
    href: str,
) -> str:
    """クロールテスト用の月別アーカイブリンクHTML断片を生成

    Args:
        aria_label: 月別リンクのaria-label属性値
        href: 月別リンクのhref属性値

    Returns:
        月別リンク1件分のHTML断片
    """

    return f'''
    <a href='{href}' class='c-table-month__col__link' aria-label='{aria_label}'>
        月別リンク
    </a>
    '''


def _press_index_with_archive_links() -> str:
    """月別巡回テスト用のトップページHTMLを生成

    Returns:
        通常の月別リンク候補を含むトップページHTML
    """

    return ''.join(
        [
            _press_release_block(
                MAY_HEADING,
                INDEX_ONLY_RELEASE_PATH,
                INDEX_ONLY_RELEASE_TITLE,
            ),
            _archive_month_link(MAY_ARIA_LABEL, MAY_ARCHIVE_PATH),
            _archive_month_link(APRIL_ARIA_LABEL, APRIL_ARCHIVE_PATH),
        ]
    )


def _press_index_with_duplicated_archive_links() -> str:
    """重複する月別リンクを含むトップページHTMLを生成

    Returns:
        同じ月別URLが複数回出るトップページHTML
    """

    return ''.join(
        [
            _archive_month_link(MAY_ARIA_LABEL, MAY_ARCHIVE_PATH),
            _archive_month_link(MAY_ARIA_LABEL_ZERO_PADDED, MAY_ARCHIVE_PATH),
            _archive_month_link(APRIL_ARIA_LABEL, APRIL_ARCHIVE_PATH),
        ]
    )


def _press_index_with_unsorted_archive_links() -> str:
    """古い月が先に表示されるトップページHTMLを生成

    Returns:
        HTML表示順が年月降順ではないトップページHTML
    """

    return ''.join(
        [
            _archive_month_link(APRIL_ARIA_LABEL, APRIL_ARCHIVE_PATH),
            _archive_month_link(MAY_ARIA_LABEL, MAY_ARCHIVE_PATH),
        ]
    )


def _may_archive_page() -> str:
    """5月アーカイブページHTMLを生成

    Returns:
        5月の報道発表1件を含む月別ページHTML
    """

    return _press_release_block(
        MAY_HEADING,
        MAY_RELEASE_PATH,
        MAY_RELEASE_TITLE,
    )


def _april_archive_page() -> str:
    """4月アーカイブページHTMLを生成

    Returns:
        4月の報道発表1件を含む月別ページHTML
    """

    return _press_release_block(
        APRIL_HEADING,
        APRIL_RELEASE_PATH,
        APRIL_RELEASE_TITLE,
    )


def _duplicated_release_archive_page() -> str:
    """重複発表を含むアーカイブページHTMLを生成

    Returns:
        複数月で同じ発表URLを返すための月別ページHTML
    """

    return _press_release_block(
        MAY_HEADING,
        DUPLICATED_RELEASE_PATH,
        DUPLICATED_RELEASE_TITLE,
    )


def _known_release_archive_page() -> str:
    """既知URLだけを含むアーカイブページHTMLを生成

    Returns:
        既知URLの報道発表だけを含む月別ページHTML
    """

    return _press_release_block(
        MAY_HEADING,
        KNOWN_RELEASE_PATH,
        KNOWN_RELEASE_TITLE,
    )


def _archive_html_by_url(
    *,
    index_html: str | None = None,
    may_html: str | None = None,
    april_html: str | None = None,
    include_april: bool = True,
) -> dict[str, str]:
    """月別巡回テスト用のHTMLをURLごとに用意

    Args:
        index_html: トップページURLで返すHTML
        may_html: 202605の月別ページURLで返すHTML
        april_html: 202604の月別ページURLで返すHTML
        include_april: 4月ページURLのHTMLも含めるかどうか

    Returns:
        取得URLをキー、返却するHTMLを値にした辞書
    """

    html_by_url = {
        START_URL: index_html or _press_index_with_archive_links(),
        MAY_ARCHIVE_URL: may_html or _may_archive_page(),
    }
    if include_april:
        html_by_url[APRIL_ARCHIVE_URL] = april_html or _april_archive_page()
    return html_by_url


def _recording_fetcher(
    html_by_url: dict[str, str],
    fetched_urls: list[str],
) -> Callable[[str], str]:
    """取得URLを記録するテスト用fetcherを生成

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


def _crawl_press_releases_for_test(
    *,
    start_url: str = START_URL,
    archive_month_limit: int = 0,
    all_archive_months: bool = False,
    fetcher: Callable[[str], str] | None = None,
    known_release_urls: Collection[str] | None = None,
    request_interval_seconds: float = REQUEST_INTERVAL_SECONDS,
    sleeper: Callable[[float], None] = _no_sleep,
) -> PressReleaseCrawlResult:
    """テスト用に実時間待機を無効化して巡回処理を実行

    Args:
        start_url: 月別リンクを抽出する報道発表一覧ページURL
        archive_month_limit: 取得する月別アーカイブページ数
        all_archive_months: 月別リンク候補をすべて巡回するかどうか
        fetcher: URLを受け取りHTMLを返す取得関数
        known_release_urls: 取得済みとして扱う報道発表詳細ページURL
        request_interval_seconds: ページ取得の間に空ける秒数
        sleeper: 待機処理を行う関数

    Returns:
        月別アーカイブページから取得した報道発表と巡回情報
    """

    if fetcher is not None:
        return crawl_press_releases(
            start_url=start_url,
            archive_month_limit=archive_month_limit,
            all_archive_months=all_archive_months,
            fetcher=fetcher,
            known_release_urls=known_release_urls,
            request_interval_seconds=request_interval_seconds,
            sleeper=sleeper,
        )

    return crawl_press_releases(
        start_url=start_url,
        archive_month_limit=archive_month_limit,
        all_archive_months=all_archive_months,
        known_release_urls=known_release_urls,
        request_interval_seconds=request_interval_seconds,
        sleeper=sleeper,
    )


class EnvPressCrawlerTest(unittest.TestCase):
    """環境省報道発表の月別ページ巡回処理のテスト"""

    # 月別リンクを選び、月別ページから発表を取得する。
    def test_crawl_press_releases_fetches_archive_month_pages(self) -> None:
        """月別ページを指定件数だけ巡回して発表を取得すること"""

        html_by_url = _archive_html_by_url()
        fetched_urls: list[str] = []

        result = _crawl_press_releases_for_test(
            start_url=START_URL,
            archive_month_limit=2,
            fetcher=_recording_fetcher(html_by_url, fetched_urls),
        )

        self.assertEqual(
            fetched_urls,
            [
                START_URL,
                MAY_ARCHIVE_URL,
                APRIL_ARCHIVE_URL,
            ],
        )
        self.assertEqual(
            result.fetched_page_urls,
            (
                MAY_ARCHIVE_URL,
                APRIL_ARCHIVE_URL,
            ),
        )
        self.assertEqual(len(result.archive_month_links), 2)
        self.assertEqual(
            [release.title for release in result.releases],
            [MAY_RELEASE_TITLE, APRIL_RELEASE_TITLE],
        )
        self.assertEqual(
            result.stop_reason,
            ARCHIVE_MONTH_LINKS_EXHAUSTED,
        )

    def test_crawl_press_releases_respects_archive_month_limit(self) -> None:
        """指定した月別ページ数だけを取得すること"""

        html_by_url = _archive_html_by_url(include_april=False)
        fetched_urls: list[str] = []

        result = _crawl_press_releases_for_test(
            start_url=START_URL,
            archive_month_limit=1,
            fetcher=_recording_fetcher(html_by_url, fetched_urls),
        )

        self.assertEqual(
            fetched_urls,
            [
                START_URL,
                MAY_ARCHIVE_URL,
            ],
        )
        self.assertEqual(
            [release.title for release in result.releases],
            [MAY_RELEASE_TITLE],
        )
        self.assertEqual(
            result.stop_reason,
            ARCHIVE_MONTH_LIMIT_REACHED,
        )

    def test_crawl_press_releases_fetches_all_archive_month_pages(
        self,
    ) -> None:
        """全件巡回指定時に月別リンク候補をすべて取得すること"""

        html_by_url = _archive_html_by_url()
        fetched_urls: list[str] = []

        result = _crawl_press_releases_for_test(
            start_url=START_URL,
            all_archive_months=True,
            fetcher=_recording_fetcher(html_by_url, fetched_urls),
        )

        self.assertEqual(
            fetched_urls,
            [
                START_URL,
                MAY_ARCHIVE_URL,
                APRIL_ARCHIVE_URL,
            ],
        )
        self.assertEqual(
            result.fetched_page_urls,
            (
                MAY_ARCHIVE_URL,
                APRIL_ARCHIVE_URL,
            ),
        )
        self.assertEqual(
            [release.title for release in result.releases],
            [MAY_RELEASE_TITLE, APRIL_RELEASE_TITLE],
        )
        self.assertEqual(
            result.stop_reason,
            ARCHIVE_MONTH_LINKS_EXHAUSTED,
        )

    def test_crawl_press_releases_waits_between_page_fetches(self) -> None:
        """月別ページ取得の前に既定秒数だけ待機すること"""

        html_by_url = _archive_html_by_url()
        events: list[str] = []

        def fetcher(url: str) -> str:
            events.append(f'fetch:{url}')
            return html_by_url[url]

        def sleeper(seconds: float) -> None:
            events.append(f'sleep:{seconds}')

        _crawl_press_releases_for_test(
            start_url=START_URL,
            archive_month_limit=2,
            fetcher=fetcher,
            request_interval_seconds=REQUEST_INTERVAL_SECONDS,
            sleeper=sleeper,
        )

        self.assertEqual(
            events,
            [
                f'fetch:{START_URL}',
                f'sleep:{REQUEST_INTERVAL_SECONDS}',
                f'fetch:{MAY_ARCHIVE_URL}',
                f'sleep:{REQUEST_INTERVAL_SECONDS}',
                f'fetch:{APRIL_ARCHIVE_URL}',
            ],
        )

    # HTML上の並びや重複リンクに左右されないことを確認する。
    def test_crawl_press_releases_fetches_latest_month_first(self) -> None:
        """HTML表示順に依存せず最新年月の月別ページから取得すること"""

        html_by_url = _archive_html_by_url(
            index_html=_press_index_with_unsorted_archive_links(),
            include_april=False,
        )
        fetched_urls: list[str] = []

        result = _crawl_press_releases_for_test(
            start_url=START_URL,
            archive_month_limit=1,
            fetcher=_recording_fetcher(html_by_url, fetched_urls),
        )

        self.assertEqual(
            fetched_urls,
            [
                START_URL,
                MAY_ARCHIVE_URL,
            ],
        )
        self.assertEqual(
            [release.title for release in result.releases],
            [MAY_RELEASE_TITLE],
        )
        self.assertEqual(
            result.stop_reason,
            ARCHIVE_MONTH_LIMIT_REACHED,
        )

    def test_crawl_press_releases_deduplicates_page_and_release_urls(
        self,
    ) -> None:
        """月別ページURLと発表URLの重複を除外すること"""

        duplicated_release_html = _duplicated_release_archive_page()
        html_by_url = _archive_html_by_url(
            index_html=_press_index_with_duplicated_archive_links(),
            may_html=duplicated_release_html,
            april_html=duplicated_release_html,
        )
        fetched_urls: list[str] = []

        result = _crawl_press_releases_for_test(
            start_url=START_URL,
            archive_month_limit=2,
            fetcher=_recording_fetcher(html_by_url, fetched_urls),
        )

        self.assertEqual(
            fetched_urls,
            [
                START_URL,
                MAY_ARCHIVE_URL,
                APRIL_ARCHIVE_URL,
            ],
        )
        self.assertEqual(len(result.releases), 1)
        self.assertEqual(result.releases[0].title, DUPLICATED_RELEASE_TITLE)
        self.assertEqual(
            result.stop_reason,
            ARCHIVE_MONTH_LINKS_EXHAUSTED,
        )

    # 既知URLだけの月に到達したら古い月へ進まない。
    def test_crawl_press_releases_stops_when_page_is_all_known(
        self,
    ) -> None:
        """月別ページの発表がすべて既知URLなら巡回を停止すること"""

        html_by_url = _archive_html_by_url(
            may_html=_known_release_archive_page(),
        )
        fetched_urls: list[str] = []

        result = _crawl_press_releases_for_test(
            start_url=START_URL,
            archive_month_limit=2,
            fetcher=_recording_fetcher(html_by_url, fetched_urls),
            known_release_urls={KNOWN_RELEASE_URL},
        )

        self.assertEqual(
            fetched_urls,
            [
                START_URL,
                MAY_ARCHIVE_URL,
            ],
        )
        self.assertEqual(result.fetched_page_urls, (MAY_ARCHIVE_URL,))
        self.assertEqual(result.releases, ())
        self.assertEqual(result.stop_reason, DUPLICATE_RELEASE_DETECTED)

    # 呼び出し元がset以外を渡しても既知URLとして扱える。
    def test_crawl_press_releases_accepts_known_release_url_collection(
        self,
    ) -> None:
        """既知URLをset以外のコレクションでも扱えること"""

        html_by_url = _archive_html_by_url(
            may_html=_known_release_archive_page(),
        )
        fetched_urls: list[str] = []

        result = _crawl_press_releases_for_test(
            start_url=START_URL,
            archive_month_limit=2,
            fetcher=_recording_fetcher(html_by_url, fetched_urls),
            known_release_urls=(KNOWN_RELEASE_URL,),
        )

        self.assertEqual(
            fetched_urls,
            [
                START_URL,
                MAY_ARCHIVE_URL,
            ],
        )
        self.assertEqual(result.releases, ())
        self.assertEqual(result.stop_reason, DUPLICATE_RELEASE_DETECTED)

    # 取得失敗や不正な指定は呼び出し元へ明確に返す。
    def test_crawl_press_releases_propagates_fetch_error(self) -> None:
        """月別ページ取得時の例外を呼び出し元へ伝播すること"""

        def fetcher(url: str) -> str:
            # index.html取得後の月別ページ取得だけを失敗させる。
            if url == START_URL:
                return _press_index_with_archive_links()
            raise URLError(FETCH_ERROR_REASON)

        with self.assertRaises(URLError):
            _crawl_press_releases_for_test(
                start_url=START_URL,
                archive_month_limit=1,
                fetcher=fetcher,
            )

    def test_crawl_press_releases_rejects_negative_limit(self) -> None:
        """負の月別ページ数を拒否すること"""

        with self.assertRaises(ValueError):
            _crawl_press_releases_for_test(archive_month_limit=-1)

    def test_crawl_press_releases_rejects_limit_with_all_archive_months(
        self,
    ) -> None:
        """件数指定と全件巡回指定の併用を拒否すること"""

        with self.assertRaises(ValueError):
            _crawl_press_releases_for_test(
                archive_month_limit=1,
                all_archive_months=True,
            )

    def test_crawl_press_releases_rejects_zero_request_interval(
        self,
    ) -> None:
        """0秒の待機秒数を拒否すること"""

        with self.assertRaises(ValueError):
            _crawl_press_releases_for_test(request_interval_seconds=0.0)

    def test_crawl_press_releases_rejects_negative_request_interval(
        self,
    ) -> None:
        """負の待機秒数を拒否すること"""

        with self.assertRaises(ValueError):
            _crawl_press_releases_for_test(request_interval_seconds=-1.0)


if __name__ == '__main__':
    unittest.main()

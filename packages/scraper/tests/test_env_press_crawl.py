import unittest
from urllib.error import URLError

from press_watch_scraper.env_press import crawl_press_releases


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


def _press_release_block(
    heading: str,
    href: str,
    title: str,
) -> str:
    """クロールテスト用の報道発表HTML断片を生成"""

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
    """クロールテスト用の月別アーカイブリンクHTML断片を生成"""

    return f'''
    <a href='{href}' class='c-table-month__col__link' aria-label='{aria_label}'>
        月別リンク
    </a>
    '''


def _press_index_with_archive_links() -> str:
    """月別巡回テスト用のトップページHTMLを生成"""

    return ''.join(
        [
            _press_release_block(
                '2026年05月01日発表',
                '/press/index_only.html',
                'トップページだけの発表',
            ),
            _archive_month_link('2026年5月', MAY_ARCHIVE_PATH),
            _archive_month_link('2026年4月', APRIL_ARCHIVE_PATH),
        ]
    )


def _press_index_with_duplicated_archive_links() -> str:
    """重複する月別リンクを含むトップページHTMLを生成"""

    return ''.join(
        [
            _archive_month_link('2026年5月', MAY_ARCHIVE_PATH),
            _archive_month_link('2026年05月', MAY_ARCHIVE_PATH),
            _archive_month_link('2026年4月', APRIL_ARCHIVE_PATH),
        ]
    )


def _press_index_with_unsorted_archive_links() -> str:
    """古い月が先に表示されるトップページHTMLを生成"""

    return ''.join(
        [
            _archive_month_link('2026年4月', APRIL_ARCHIVE_PATH),
            _archive_month_link('2026年5月', MAY_ARCHIVE_PATH),
        ]
    )


def _may_archive_page() -> str:
    """5月アーカイブページHTMLを生成"""

    return _press_release_block(
        '2026年05月01日発表',
        '/press/may.html',
        MAY_RELEASE_TITLE,
    )


def _april_archive_page() -> str:
    """4月アーカイブページHTMLを生成"""

    return _press_release_block(
        '2026年04月30日発表',
        '/press/april.html',
        APRIL_RELEASE_TITLE,
    )


def _duplicated_release_archive_page() -> str:
    """重複発表を含むアーカイブページHTMLを生成"""

    return _press_release_block(
        '2026年05月01日発表',
        '/press/duplicated.html',
        DUPLICATED_RELEASE_TITLE,
    )


def _known_release_archive_page() -> str:
    """既知URLだけを含むアーカイブページHTMLを生成"""

    return _press_release_block(
        '2026年05月01日発表',
        '/press/known.html',
        KNOWN_RELEASE_TITLE,
    )


class EnvPressCrawlerTest(unittest.TestCase):
    """環境省報道発表の月別ページ巡回処理のテスト"""

    def test_crawl_press_releases_fetches_archive_month_pages(self) -> None:
        """月別ページを指定件数だけ巡回して発表を取得すること"""

        html_by_url = {
            START_URL: _press_index_with_archive_links(),
            MAY_ARCHIVE_URL: _may_archive_page(),
            APRIL_ARCHIVE_URL: _april_archive_page(),
        }
        fetched_urls: list[str] = []

        def fetcher(url: str) -> str:
            fetched_urls.append(url)
            return html_by_url[url]

        result = crawl_press_releases(
            start_url=START_URL,
            archive_month_limit=2,
            fetcher=fetcher,
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
            'archive_month_links_exhausted',
        )

    def test_crawl_press_releases_respects_archive_month_limit(self) -> None:
        """指定した月別ページ数だけを取得すること"""

        html_by_url = {
            START_URL: _press_index_with_archive_links(),
            MAY_ARCHIVE_URL: _may_archive_page(),
        }
        fetched_urls: list[str] = []

        def fetcher(url: str) -> str:
            fetched_urls.append(url)
            return html_by_url[url]

        result = crawl_press_releases(
            start_url=START_URL,
            archive_month_limit=1,
            fetcher=fetcher,
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
            'archive_month_limit_reached',
        )

    def test_crawl_press_releases_fetches_latest_month_first(self) -> None:
        """HTML表示順に依存せず最新年月の月別ページから取得すること"""

        html_by_url = {
            START_URL: _press_index_with_unsorted_archive_links(),
            MAY_ARCHIVE_URL: _may_archive_page(),
        }
        fetched_urls: list[str] = []

        def fetcher(url: str) -> str:
            fetched_urls.append(url)
            return html_by_url[url]

        result = crawl_press_releases(
            start_url=START_URL,
            archive_month_limit=1,
            fetcher=fetcher,
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
            'archive_month_limit_reached',
        )

    def test_crawl_press_releases_deduplicates_page_and_release_urls(
        self,
    ) -> None:
        """月別ページURLと発表URLの重複を除外すること"""

        duplicated_release_html = _duplicated_release_archive_page()
        html_by_url = {
            START_URL: _press_index_with_duplicated_archive_links(),
            MAY_ARCHIVE_URL: duplicated_release_html,
            APRIL_ARCHIVE_URL: duplicated_release_html,
        }
        fetched_urls: list[str] = []

        def fetcher(url: str) -> str:
            fetched_urls.append(url)
            return html_by_url[url]

        result = crawl_press_releases(
            start_url=START_URL,
            archive_month_limit=2,
            fetcher=fetcher,
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
            'archive_month_links_exhausted',
        )

    def test_crawl_press_releases_stops_when_page_is_all_known(
        self,
    ) -> None:
        """月別ページの発表がすべて既知URLなら巡回を停止すること"""

        html_by_url = {
            START_URL: _press_index_with_archive_links(),
            MAY_ARCHIVE_URL: _known_release_archive_page(),
            APRIL_ARCHIVE_URL: _april_archive_page(),
        }
        fetched_urls: list[str] = []

        def fetcher(url: str) -> str:
            fetched_urls.append(url)
            return html_by_url[url]

        result = crawl_press_releases(
            start_url=START_URL,
            archive_month_limit=2,
            fetcher=fetcher,
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
        self.assertEqual(result.stop_reason, 'duplicate_release_detected')

    def test_crawl_press_releases_accepts_known_release_url_collection(
        self,
    ) -> None:
        """既知URLをset以外のコレクションでも扱えること"""

        html_by_url = {
            START_URL: _press_index_with_archive_links(),
            MAY_ARCHIVE_URL: _known_release_archive_page(),
            APRIL_ARCHIVE_URL: _april_archive_page(),
        }
        fetched_urls: list[str] = []

        def fetcher(url: str) -> str:
            fetched_urls.append(url)
            return html_by_url[url]

        result = crawl_press_releases(
            start_url=START_URL,
            archive_month_limit=2,
            fetcher=fetcher,
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
        self.assertEqual(result.stop_reason, 'duplicate_release_detected')

    def test_crawl_press_releases_propagates_fetch_error(self) -> None:
        """月別ページ取得時の例外を呼び出し元へ伝播すること"""

        def fetcher(url: str) -> str:
            if url == START_URL:
                return _press_index_with_archive_links()
            raise URLError('network unavailable')

        with self.assertRaises(URLError):
            crawl_press_releases(
                start_url=START_URL,
                archive_month_limit=1,
                fetcher=fetcher,
            )

    def test_crawl_press_releases_rejects_negative_limit(self) -> None:
        """負の月別ページ数を拒否すること"""

        with self.assertRaises(ValueError):
            crawl_press_releases(archive_month_limit=-1)


if __name__ == '__main__':
    unittest.main()

import unittest
from urllib.error import URLError

from press_watch_scraper.env_press import crawl_press_releases


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
            _archive_month_link('2026年5月', '/press/202605.html'),
            _archive_month_link('2026年4月', '/press/202604.html'),
        ]
    )


class EnvPressCrawlerTest(unittest.TestCase):
    """環境省報道発表の月別ページ巡回処理のテスト"""

    def test_crawl_press_releases_fetches_archive_month_pages(self) -> None:
        """月別ページを指定件数だけ巡回して発表を取得すること"""

        html_by_url = {
            'https://example.com/press/index.html': (
                _press_index_with_archive_links()
            ),
            'https://example.com/press/202605.html': _press_release_block(
                '2026年05月01日発表',
                '/press/may.html',
                '5月の発表',
            ),
            'https://example.com/press/202604.html': _press_release_block(
                '2026年04月30日発表',
                '/press/april.html',
                '4月の発表',
            ),
        }
        fetched_urls: list[str] = []

        def fetcher(url: str) -> str:
            fetched_urls.append(url)
            return html_by_url[url]

        result = crawl_press_releases(
            start_url='https://example.com/press/index.html',
            archive_month_limit=2,
            fetcher=fetcher,
        )

        self.assertEqual(
            fetched_urls,
            [
                'https://example.com/press/index.html',
                'https://example.com/press/202605.html',
                'https://example.com/press/202604.html',
            ],
        )
        self.assertEqual(
            result.fetched_page_urls,
            (
                'https://example.com/press/202605.html',
                'https://example.com/press/202604.html',
            ),
        )
        self.assertEqual(len(result.archive_month_links), 2)
        self.assertEqual(
            [release.title for release in result.releases],
            ['5月の発表', '4月の発表'],
        )

    def test_crawl_press_releases_respects_archive_month_limit(self) -> None:
        """指定した月別ページ数だけを取得すること"""

        html_by_url = {
            'https://example.com/press/index.html': (
                _press_index_with_archive_links()
            ),
            'https://example.com/press/202605.html': _press_release_block(
                '2026年05月01日発表',
                '/press/may.html',
                '5月の発表',
            ),
        }
        fetched_urls: list[str] = []

        def fetcher(url: str) -> str:
            fetched_urls.append(url)
            return html_by_url[url]

        result = crawl_press_releases(
            start_url='https://example.com/press/index.html',
            archive_month_limit=1,
            fetcher=fetcher,
        )

        self.assertEqual(
            fetched_urls,
            [
                'https://example.com/press/index.html',
                'https://example.com/press/202605.html',
            ],
        )
        self.assertEqual(
            [release.title for release in result.releases],
            ['5月の発表'],
        )

    def test_crawl_press_releases_deduplicates_page_and_release_urls(
        self,
    ) -> None:
        """月別ページURLと発表URLの重複を除外すること"""

        index_html = ''.join(
            [
                _archive_month_link('2026年5月', '/press/202605.html'),
                _archive_month_link('2026年05月', '/press/202605.html'),
                _archive_month_link('2026年4月', '/press/202604.html'),
            ]
        )
        duplicated_release_html = _press_release_block(
            '2026年05月01日発表',
            '/press/duplicated.html',
            '重複する発表',
        )
        html_by_url = {
            'https://example.com/press/index.html': index_html,
            'https://example.com/press/202605.html': duplicated_release_html,
            'https://example.com/press/202604.html': duplicated_release_html,
        }
        fetched_urls: list[str] = []

        def fetcher(url: str) -> str:
            fetched_urls.append(url)
            return html_by_url[url]

        result = crawl_press_releases(
            start_url='https://example.com/press/index.html',
            archive_month_limit=2,
            fetcher=fetcher,
        )

        self.assertEqual(
            fetched_urls,
            [
                'https://example.com/press/index.html',
                'https://example.com/press/202605.html',
                'https://example.com/press/202604.html',
            ],
        )
        self.assertEqual(len(result.releases), 1)
        self.assertEqual(result.releases[0].title, '重複する発表')

    def test_crawl_press_releases_propagates_fetch_error(self) -> None:
        """月別ページ取得時の例外を呼び出し元へ伝播すること"""

        def fetcher(url: str) -> str:
            if url == 'https://example.com/press/index.html':
                return _press_index_with_archive_links()
            raise URLError('network unavailable')

        with self.assertRaises(URLError):
            crawl_press_releases(
                start_url='https://example.com/press/index.html',
                archive_month_limit=1,
                fetcher=fetcher,
            )

    def test_crawl_press_releases_rejects_negative_limit(self) -> None:
        """負の月別ページ数を拒否すること"""

        with self.assertRaises(ValueError):
            crawl_press_releases(archive_month_limit=-1)


if __name__ == '__main__':
    unittest.main()

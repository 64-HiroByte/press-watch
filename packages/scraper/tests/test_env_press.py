from datetime import date
from pathlib import Path
import unittest

from press_watch_scraper.env_press import (
    parse_archive_month_links,
    parse_press_releases,
)


EXPECTED_PRESS_URL = 'https://www.env.go.jp/press/press_00001.html'
EXPECTED_OLD_STYLE_PRESS_URL = 'https://www.env.go.jp/press/111111_00001.html'
EXPECTED_ABSOLUTE_PRESS_URL = 'https://example.com/press/external.html'
EXPECTED_CUSTOM_BASE_PRESS_URL = 'https://example.com/press/press_00001.html'
EXPECTED_MONTH_URL = 'https://www.env.go.jp/press/202605.html'
EXPECTED_TITLE = '令和８年度テスト事業の公募について'
MANY_LINK_COUNT = 10
FIXTURE_DIR = Path(__file__).parent / 'fixtures'


def _press_release_block(
    heading: str,
    href: str = '/press/press_00001.html',
) -> str:
    """報道発表1件分のHTML断片を生成"""

    return f'''
    <details class='p-press-release-list__block'>
        <summary>
            <span class='p-press-release-list__heading'>
                {heading}
            </span>
        </summary>
        <a href='{href}' class='c-news-link__link'>
            {EXPECTED_TITLE}
        </a>
    </details>
    '''


def _archive_month_link(
    aria_label: str,
    href: str = '/press/202605.html',
) -> str:
    """月別アーカイブリンク1件分のHTML断片を生成"""

    return f'''
    <a href='{href}' class='c-table-month__col__link' aria-label='{aria_label}'>
        月別リンク
    </a>
    '''


def _read_fixture(name: str) -> str:
    """fixture HTMLを読み込む"""

    return (FIXTURE_DIR / name).read_text(encoding='utf-8')


class EnvPressParserTest(unittest.TestCase):
    """環境省報道発表HTMLのパース処理のテスト"""

    def test_parse_press_releases_returns_empty_for_empty_html(
        self,
    ) -> None:
        """空HTMLから報道発表を抽出しないこと"""

        items = parse_press_releases('')

        self.assertEqual(items, [])

    def test_parse_archive_month_links_returns_empty_list_for_empty_html(
        self,
    ) -> None:
        """空HTMLから月別リンクを抽出しないこと"""

        links = parse_archive_month_links('')

        self.assertEqual(links, [])

    def test_parse_env_press_sample_fixture(self) -> None:
        """実HTMLに近いfixtureから必要項目を抽出すること"""

        html = _read_fixture('env_press_index_sample.html')

        releases = parse_press_releases(html)
        archive_month_links = parse_archive_month_links(html)

        self.assertEqual(len(releases), 3)
        self.assertEqual(releases[0].title, EXPECTED_TITLE)
        self.assertEqual(releases[0].published_at, date(2026, 5, 1))
        self.assertEqual(releases[0].url, EXPECTED_PRESS_URL)
        self.assertEqual(
            releases[1].title,
            'テスト会議の開催について',
        )
        self.assertEqual(releases[1].published_at, date(2026, 5, 1))
        self.assertEqual(
            releases[1].url,
            'https://www.env.go.jp/press/press_00002.html',
        )
        self.assertEqual(releases[2].title, '別形式URLの発表')
        self.assertEqual(releases[2].published_at, date(2026, 4, 30))
        self.assertEqual(releases[2].url, EXPECTED_OLD_STYLE_PRESS_URL)
        self.assertEqual(len(archive_month_links), 1)
        self.assertEqual(archive_month_links[0].year, 2026)
        self.assertEqual(archive_month_links[0].month, 5)
        self.assertEqual(archive_month_links[0].url, EXPECTED_MONTH_URL)

    def test_parse_press_releases_with_grouped_date(self) -> None:
        """日付ごとにまとまった報道発表を抽出すること"""

        html = '''
        <div class='p-press-release-list'>
            <details class='p-press-release-list__block'>
                <summary>
                    <span class='p-press-release-list__heading'>
                        2026年05月01日発表
                    </span>
                </summary>
                <ul>
                    <li>
                        <a href='/press/press_00001.html' class='c-news-link__link'>
                            令和８年度テスト事業の公募について
                        </a>
                    </li>
                </ul>
            </details>
            <details class='p-press-release-list__block'>
                <summary>
                    <span class='p-press-release-list__heading'>
                        2026年04月30日発表
                    </span>
                </summary>
                <ul>
                    <li>
                        <a href='/press/111111_00001.html' class='c-news-link__link'>
                            別形式URLの発表
                        </a>
                    </li>
                </ul>
            </details>
        </div>
        '''

        items = parse_press_releases(html)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, EXPECTED_TITLE)
        self.assertEqual(items[0].published_at, date(2026, 5, 1))
        self.assertEqual(items[0].url, EXPECTED_PRESS_URL)
        self.assertEqual(items[1].published_at, date(2026, 4, 30))
        self.assertEqual(items[1].url, EXPECTED_OLD_STYLE_PRESS_URL)

    def test_parse_press_releases_accepts_valid_date_values(self) -> None:
        """有効な報道発表日を日付として扱うこと"""

        cases = [
            ('2026年1月1日発表', date(2026, 1, 1)),
            ('2026年01月01日発表', date(2026, 1, 1)),
            ('2024年02月29日発表', date(2024, 2, 29)),
            ('2026年12月31日発表', date(2026, 12, 31)),
        ]

        for heading, expected_date in cases:
            with self.subTest(heading=heading):
                items = parse_press_releases(_press_release_block(heading))

                self.assertEqual(len(items), 1)
                self.assertEqual(items[0].published_at, expected_date)

    def test_parse_press_releases_skips_incomplete_entries(self) -> None:
        """情報が欠けた発表をスキップすること"""

        html = '''
        <details class='p-press-release-list__block'>
            <a href='/press/no_heading.html' class='c-news-link__link'>
                見出しがない発表
            </a>
        </details>
        <details class='p-press-release-list__block'>
            <summary>
                <span class='p-press-release-list__heading'>
                    2026年05月01日発表
                </span>
            </summary>
            <a class='c-news-link__link'>
                hrefがない発表
            </a>
            <a href='/press/empty_title.html' class='c-news-link__link'>
            </a>
            <a href='/press/press_00001.html' class='c-news-link__link'>
                令和８年度テスト事業の公募について
            </a>
        </details>
        '''

        items = parse_press_releases(html)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, EXPECTED_TITLE)
        self.assertEqual(items[0].url, EXPECTED_PRESS_URL)

    def test_parse_press_releases_normalizes_title_text(self) -> None:
        """タイトルの空白とタグ境界を正規化すること"""

        html = '''
        <details class='p-press-release-list__block'>
            <summary>
                <span class='p-press-release-list__heading'>
                    2026年05月01日発表
                </span>
            </summary>
            <a href='/press/press_00001.html' class='c-news-link__link'>
                令和８年度
                <span>テスト事業</span>
                の   公募について
            </a>
        </details>
        '''

        items = parse_press_releases(html)

        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0].title,
            '令和８年度 テスト事業 の 公募について',
        )

    def test_parse_press_releases_with_multiple_links_in_same_date_block(
        self,
    ) -> None:
        """同じ日付ブロック内の複数発表を抽出すること"""

        html = '''
        <details class='p-press-release-list__block'>
            <summary>
                <span class='p-press-release-list__heading'>
                    2026年05月01日発表
                </span>
            </summary>
            <a href='/press/press_00001.html' class='c-news-link__link'>
                1件目の発表
            </a>
            <a href='/press/press_00002.html' class='c-news-link__link'>
                2件目の発表
            </a>
        </details>
        '''

        items = parse_press_releases(html)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, '1件目の発表')
        self.assertEqual(items[0].published_at, date(2026, 5, 1))
        self.assertEqual(items[0].url, EXPECTED_PRESS_URL)
        self.assertEqual(items[1].title, '2件目の発表')
        self.assertEqual(items[1].published_at, date(2026, 5, 1))
        self.assertEqual(
            items[1].url,
            'https://www.env.go.jp/press/press_00002.html',
        )

    def test_parse_press_releases_with_many_links_in_same_date_block(
        self,
    ) -> None:
        """同じ日付ブロック内の多数発表を抽出すること"""

        links = '\n'.join(
            f'''
            <a href='/press/press_{index:05}.html' class='c-news-link__link'>
                {index}件目の発表
            </a>
            '''
            for index in range(1, MANY_LINK_COUNT + 1)
        )
        html = f'''
        <details class='p-press-release-list__block'>
            <summary>
                <span class='p-press-release-list__heading'>
                    2026年05月01日発表
                </span>
            </summary>
            {links}
        </details>
        '''

        items = parse_press_releases(html)

        self.assertEqual(len(items), MANY_LINK_COUNT)
        self.assertEqual(
            [item.title for item in items],
            [
                f'{index}件目の発表'
                for index in range(1, MANY_LINK_COUNT + 1)
            ],
        )
        self.assertTrue(
            all(item.published_at == date(2026, 5, 1) for item in items)
        )
        self.assertEqual(
            items[-1].url,
            f'https://www.env.go.jp/press/press_{MANY_LINK_COUNT:05}.html',
        )

    def test_parse_press_releases_preserves_html_order(self) -> None:
        """HTML上の表示順を保って報道発表を返すこと"""

        html = '''
        <details class='p-press-release-list__block'>
            <summary>
                <span class='p-press-release-list__heading'>
                    2026年05月02日発表
                </span>
            </summary>
            <a href='/press/press_00002.html' class='c-news-link__link'>
                先に表示される発表
            </a>
        </details>
        <details class='p-press-release-list__block'>
            <summary>
                <span class='p-press-release-list__heading'>
                    2026年05月01日発表
                </span>
            </summary>
            <a href='/press/press_00001.html' class='c-news-link__link'>
                後に表示される発表
            </a>
        </details>
        '''

        items = parse_press_releases(html)

        self.assertEqual(
            [item.title for item in items],
            ['先に表示される発表', '後に表示される発表'],
        )

    def test_parse_press_releases_resolves_urls_with_base_url(self) -> None:
        """報道発表の相対URLを絶対URLに変換すること"""

        html = _press_release_block(
            '2026年05月01日発表',
            './press_00001.html',
        )

        items = parse_press_releases(
            html,
            base_url='https://example.com/press/index.html',
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, EXPECTED_CUSTOM_BASE_PRESS_URL)

    def test_parse_press_releases_keeps_absolute_url(self) -> None:
        """報道発表の絶対URLをそのまま扱うこと"""

        html = _press_release_block(
            '2026年05月01日発表',
            EXPECTED_ABSOLUTE_PRESS_URL,
        )

        items = parse_press_releases(html)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, EXPECTED_ABSOLUTE_PRESS_URL)

    def test_parse_archive_month_links(self) -> None:
        """月別アーカイブリンクを抽出すること"""

        html = f'''
        {_archive_month_link('2026年5月')}
        <li class='c-table-month__col__item'>6月</li>
        '''

        links = parse_archive_month_links(html)

        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].year, 2026)
        self.assertEqual(links[0].month, 5)
        self.assertEqual(links[0].url, EXPECTED_MONTH_URL)

    def test_parse_archive_month_links_accepts_valid_month_values(
        self,
    ) -> None:
        """有効な月表記を月別アーカイブとして扱うこと"""

        cases = [
            ('2026年1月', 1),
            ('2026年01月', 1),
            ('2026年12月', 12),
        ]

        for aria_label, expected_month in cases:
            with self.subTest(aria_label=aria_label):
                links = parse_archive_month_links(
                    _archive_month_link(aria_label)
                )

                self.assertEqual(len(links), 1)
                self.assertEqual(links[0].year, 2026)
                self.assertEqual(links[0].month, expected_month)

    def test_parse_archive_month_links_resolves_urls_with_base_url(
        self,
    ) -> None:
        """月別リンクの相対URLを絶対URLに変換すること"""

        html = _archive_month_link('2026年5月', './202605.html')

        links = parse_archive_month_links(
            html,
            base_url='https://example.com/press/index.html',
        )

        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].url, 'https://example.com/press/202605.html')

    def test_parse_archive_month_links_keeps_absolute_url(self) -> None:
        """月別アーカイブの絶対URLをそのまま扱うこと"""

        html = _archive_month_link(
            '2026年5月',
            'https://example.com/press/202605.html',
        )

        links = parse_archive_month_links(html)

        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].url, 'https://example.com/press/202605.html')

    def test_parse_press_releases_skips_invalid_date(self) -> None:
        """無効な日付を含む発表をスキップすること"""

        invalid_headings = [
            'お知らせ 2026年05月01日発表',
            '2026年00月01日発表',
            '2026年13月01日発表',
            '2026年01月00日発表',
            '2026年01月32日発表',
            '2026年02月29日発表',
            '2026年02月31日発表',
            '2026年04月31日発表',
            '2026年05月01日発表 追加情報',
            '2026年05月01日公開',
        ]
        html = ''.join(
            _press_release_block(heading, f'/press/press_{index:05}.html')
            for index, heading in enumerate(invalid_headings, start=1)
        )

        items = parse_press_releases(html)

        self.assertEqual(items, [])

    def test_parse_archive_month_links_skips_invalid_month(self) -> None:
        """無効な月表記の月別リンクをスキップすること"""

        html = ''.join(
            [
                _archive_month_link(
                    'アーカイブ 2026年5月',
                    '/press/202605.html',
                ),
                _archive_month_link('2026年0月', '/press/202600.html'),
                _archive_month_link('2026年00月', '/press/202600.html'),
                _archive_month_link('2026年13月', '/press/202613.html'),
                _archive_month_link('2026年5月分', '/press/202605.html'),
                _archive_month_link('2026年5ヶ月', '/press/202605.html'),
            ]
        )

        links = parse_archive_month_links(html)

        self.assertEqual(links, [])

    def test_parse_archive_month_links_skips_incomplete_links(self) -> None:
        """情報が欠けた月別リンクをスキップすること"""

        html = '''
        <a class='c-table-month__col__link' aria-label='2026年5月'>
            hrefがないリンク
        </a>
        <a href='/press/202605.html' class='c-table-month__col__link'>
            aria-labelがないリンク
        </a>
        '''

        links = parse_archive_month_links(html)

        self.assertEqual(links, [])


if __name__ == '__main__':
    unittest.main()

from datetime import date
import unittest

from press_watch_scraper.env_press import (
    parse_archive_month_links,
    parse_press_releases,
)


EXPECTED_PRESS_URL = 'https://www.env.go.jp/press/press_00001.html'
EXPECTED_OLD_STYLE_PRESS_URL = 'https://www.env.go.jp/press/111111_00001.html'
EXPECTED_MONTH_URL = 'https://www.env.go.jp/press/202605.html'
EXPECTED_TITLE = '令和８年度テスト事業の公募について'


class EnvPressParserTest(unittest.TestCase):
    def test_parse_press_releases_with_grouped_date(self) -> None:
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
                <a href='/press/press_00001.html'
                  class='c-news-link__link'>
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
                <a href='/press/111111_00001.html'
                  class='c-news-link__link'>
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

    def test_parse_archive_month_links(self) -> None:
        html = '''
        <a
          href='/press/202605.html'
          class='c-table-month__col__link'
          aria-label='2026年5月'
        >
          5月
        </a>
        <li class='c-table-month__col__item'>6月</li>
        '''

        links = parse_archive_month_links(html)

        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].year, 2026)
        self.assertEqual(links[0].month, 5)
        self.assertEqual(links[0].url, EXPECTED_MONTH_URL)

    def test_parse_press_releases_skips_invalid_date(self) -> None:
        html = '''
        <details class='p-press-release-list__block'>
          <summary>
            <span class='p-press-release-list__heading'>
              2026年02月31日発表
            </span>
          </summary>
          <a href='/press/press_00001.html' class='c-news-link__link'>
            実在しない日付の発表
          </a>
        </details>
        <details class='p-press-release-list__block'>
          <summary>
            <span class='p-press-release-list__heading'>
              2026年13月01日発表
            </span>
          </summary>
          <a href='/press/press_00002.html' class='c-news-link__link'>
            範囲外の月の発表
          </a>
        </details>
        '''

        items = parse_press_releases(html)

        self.assertEqual(items, [])

    def test_parse_archive_month_links_skips_invalid_month(self) -> None:
        html = '''
        <a
          href='/press/202613.html'
          class='c-table-month__col__link'
          aria-label='2026年13月'
        >
          13月
        </a>
        '''

        links = parse_archive_month_links(html)

        self.assertEqual(links, [])


if __name__ == '__main__':
    unittest.main()

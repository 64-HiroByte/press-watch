from contextlib import redirect_stdout
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


def _run_cli(args: list[str]) -> dict[str, object]:
    """CLIを実行してJSON出力と終了コードを取得"""

    stdout = io.StringIO()

    with patch('sys.argv', ['press-watch-scraper', *args]):
        with redirect_stdout(stdout):
            exit_code = cli.main()

    payload = json.loads(stdout.getvalue())
    payload['exit_code'] = exit_code
    return payload


class ScraperCliTest(unittest.TestCase):
    """スクレイパーCLIのテスト"""

    def test_main_reads_html_from_file_and_outputs_json(self) -> None:
        """保存済みHTMLを読み込んでJSONを出力すること"""

        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / 'index.html'
            html_path.write_text(_press_index_html(), encoding='utf-8')

            payload = _run_cli(['--from-file', str(html_path)])

        self.assertEqual(payload['exit_code'], 0)
        self.assertEqual(payload['source_url'], str(html_path))
        self.assertEqual(payload['count'], 2)
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
            payload['items'][0]['url'],
            'https://example.com/press/press_00001.html',
        )
        self.assertEqual(
            payload['archive_month_links'][0]['url'],
            'https://example.com/press/202605.html',
        )

    def test_main_propagates_fetch_error(self) -> None:
        """HTML取得時の例外を呼び出し元へ伝播すること"""

        with patch.object(cli, 'fetch_press_index_html') as mock_fetch:
            mock_fetch.side_effect = URLError(FETCH_ERROR_REASON)

            with self.assertRaises(URLError):
                _run_cli(['--url', 'https://example.com/press/index.html'])


if __name__ == '__main__':
    unittest.main()

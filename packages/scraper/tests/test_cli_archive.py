"""scraper CLIの月別巡回範囲、停止条件、rate limiterの共有を検証"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from press_watch_scraper import __main__ as cli

from cli_test_support import (
    APRIL_RELEASE_TITLE,
    EXAMPLE_APRIL_ARCHIVE_URL,
    EXAMPLE_INDEX_URL,
    EXAMPLE_MAY_ARCHIVE_URL,
    EXAMPLE_MAY_RELEASE_URL,
    FETCH_PRESS_PAGE_HTML_ATTR,
    MAY_RELEASE_TITLE,
    _all_archive_months_args,
    _archive_html_by_url,
    _archive_month_limit_args,
    _known_release_urls_file_args,
    _recording_html_fetcher,
    _run_cli,
    _url_args,
)


# 月別巡回の停止理由
ARCHIVE_MONTH_LINKS_EXHAUSTED = 'archive_month_links_exhausted'
ARCHIVE_MONTH_LIMIT_REACHED = 'archive_month_limit_reached'
DUPLICATE_RELEASE_DETECTED = 'duplicate_release_detected'


class ScraperArchiveCliTest(unittest.TestCase):
    """スクレイパーCLIの月別巡回のテスト"""

    def test_main_fetches_archive_month_pages_when_limit_is_given(
        self,
    ) -> None:
        """月別ページ数指定時に月別ページ由来のJSONを出力すること"""

        html_by_url = _archive_html_by_url()
        fetched_urls: list[str] = []

        # URLごとに用意したHTMLを返し、実HTTP取得を避ける。
        with patch.object(
            cli,
            FETCH_PRESS_PAGE_HTML_ATTR,
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

    def test_main_shares_rate_limiter_across_archive_crawl(self) -> None:
        """起点・月別ページの取得処理へ同じrate limiterを渡すこと"""

        html_by_url = _archive_html_by_url()
        rate_limiters: list[object | None] = []

        def fetch_page(
            url: str,
            *,
            rate_limiter: object | None = None,
        ) -> str:
            rate_limiters.append(rate_limiter)
            return html_by_url[url]

        with patch.object(
            cli,
            FETCH_PRESS_PAGE_HTML_ATTR,
            side_effect=fetch_page,
        ):
            payload = _run_cli(
                *_url_args(),
                *_archive_month_limit_args(limit=2),
            )

        self.assertEqual(payload['exit_code'], 0)
        self.assertEqual(len(rate_limiters), 3)
        self.assertIsNotNone(rate_limiters[0])
        self.assertTrue(
            all(
                limiter is rate_limiters[0]
                for limiter in rate_limiters[1:]
            )
        )

    def test_main_outputs_stop_reason_when_archive_month_limit_is_reached(
        self,
    ) -> None:
        """月別ページ数上限で止まった理由をJSONに出力すること"""

        html_by_url = _archive_html_by_url(include_april=False)

        # 月別リンクが複数ある状態で、limit=1の停止理由を確認する。
        with patch.object(
            cli,
            FETCH_PRESS_PAGE_HTML_ATTR,
            side_effect=lambda url, **_kwargs: html_by_url[url],
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
            FETCH_PRESS_PAGE_HTML_ATTR,
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

    def test_main_uses_known_release_urls_for_archive_crawl(self) -> None:
        """既知URLだけの月に到達した停止理由をJSONへ出すこと"""

        html_by_url = _archive_html_by_url()
        fetched_urls: list[str] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            known_urls_path = Path(temp_dir) / 'known-release-urls.txt'
            known_urls_path.write_text(
                f'\n{EXAMPLE_MAY_RELEASE_URL}\n\n',
                encoding=cli.JSON_OUTPUT_ENCODING,
            )

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=_recording_html_fetcher(
                    html_by_url,
                    fetched_urls,
                ),
            ):
                payload = _run_cli(
                    *_url_args(),
                    *_archive_month_limit_args(limit=2),
                    *_known_release_urls_file_args(known_urls_path),
                )

        self.assertEqual(payload['exit_code'], 0)
        self.assertEqual(
            fetched_urls,
            [
                EXAMPLE_INDEX_URL,
                EXAMPLE_MAY_ARCHIVE_URL,
            ],
        )
        self.assertEqual(payload['count'], 0)
        self.assertEqual(
            payload['fetched_page_urls'],
            [EXAMPLE_MAY_ARCHIVE_URL],
        )
        self.assertEqual(
            payload['stop_reason'],
            DUPLICATE_RELEASE_DETECTED,
        )


if __name__ == '__main__':
    unittest.main()

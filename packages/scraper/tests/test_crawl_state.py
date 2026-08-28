from datetime import UTC, datetime
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from press_watch_scraper import crawl_state
from press_watch_scraper.crawl_state import (
    CrawlState,
    CrawlStateError,
)
from press_watch_scraper.env_press import ArchiveMonthLink


INDEX_URL = 'https://example.com/press/index.html'
ARCHIVE_URL = 'https://example.com/press/202605.html'
INDEX_HTML = '<html>index</html>'
ARCHIVE_HTML = '<html>archive</html>'
COMPLETED_REASON = 'archive_month_links_exhausted'


def _create_state(root: Path) -> CrawlState:
    """テスト用の新規stateを作成"""

    return CrawlState.create(
        root,
        start_url=INDEX_URL,
        archive_month_limit=0,
        all_archive_months=True,
    )


def _complete_index_only_state(root: Path) -> CrawlState:
    """indexページだけを持つ完了stateを作成"""

    state = _create_state(root)
    state.load_or_fetch(INDEX_URL, lambda _url: INDEX_HTML)
    state.mark_parsing(INDEX_URL)
    state.mark_parsed(INDEX_URL)
    state.mark_complete(COMPLETED_REASON)
    return state


class CrawlStateTest(unittest.TestCase):
    """ローカル巡回stateの安全性と永続化契約のテスト"""

    def test_create_uses_private_permissions_and_utc_timestamps(self) -> None:
        """stateを0700、ファイルを0600、日時をUTCで保存すること"""

        fixed_now = datetime(2026, 8, 28, 1, 2, 3, tzinfo=UTC)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            state = CrawlState.create(
                root,
                start_url=INDEX_URL,
                archive_month_limit=0,
                all_archive_months=True,
                clock=lambda: fixed_now,
            )
            state.load_or_fetch(INDEX_URL, lambda _url: INDEX_HTML)

            manifest = json.loads(
                (root / 'manifest.json').read_text(encoding='utf-8')
            )
            root_mode = stat.S_IMODE(root.stat().st_mode)
            pages_mode = stat.S_IMODE((root / 'pages').stat().st_mode)
            manifest_mode = stat.S_IMODE(
                (root / 'manifest.json').stat().st_mode
            )
            html_mode = stat.S_IMODE(
                (root / 'pages' / 'index.html').stat().st_mode
            )

        self.assertEqual(root_mode, 0o700)
        self.assertEqual(pages_mode, 0o700)
        self.assertEqual(manifest_mode, 0o600)
        self.assertEqual(html_mode, 0o600)
        self.assertEqual(manifest['created_at'], '2026-08-28T01:02:03Z')
        self.assertEqual(manifest['updated_at'], '2026-08-28T01:02:03Z')
        self.assertEqual(
            manifest['pages'][0]['updated_at'],
            '2026-08-28T01:02:03Z',
        )





    def test_create_rejects_url_with_credentials(self) -> None:
        """認証情報を含む起点URLを拒否すること"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'

            with self.assertRaisesRegex(CrawlStateError, 'URL is invalid'):
                CrawlState.create(
                    root,
                    start_url=(
                        'https://user:password@example.com/press/index.html'
                    ),
                    archive_month_limit=0,
                    all_archive_months=True,
                )

            state_was_created = root.exists()

        self.assertFalse(state_was_created)

    def test_register_archive_pages_rejects_different_origin(self) -> None:
        """起点と異なるオリジンの月別URLを登録しないこと"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            state = _create_state(root)

            with self.assertRaisesRegex(
                CrawlStateError,
                'must use the crawl start origin',
            ):
                state.register_archive_pages(
                    (
                        ArchiveMonthLink(
                            year=2026,
                            month=5,
                            url='https://other.example/press/202605.html',
                        ),
                    )
                )

    def test_failed_page_replace_leaves_no_partial_html(self) -> None:
        """HTMLの原子的置換失敗時に最終ファイルと一時ファイルを残さないこと"""

        real_replace = os.replace

        def failing_page_replace(source: object, destination: object) -> None:
            if Path(destination).name == 'index.html':
                raise OSError('replace failed')
            real_replace(source, destination)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            state = _create_state(root)

            with patch.object(
                crawl_state.os,
                'replace',
                side_effect=failing_page_replace,
            ):
                with self.assertRaisesRegex(OSError, 'replace failed'):
                    state.load_or_fetch(INDEX_URL, lambda _url: INDEX_HTML)

            manifest = json.loads(
                (root / 'manifest.json').read_text(encoding='utf-8')
            )
            page_entries = list((root / 'pages').iterdir())

        self.assertEqual(page_entries, [])
        self.assertEqual(manifest['status'], 'failed')
        self.assertEqual(manifest['pages'][0]['status'], 'save_failed')
        self.assertEqual(manifest['pages'][0]['failure']['stage'], 'save')

    def test_failure_reason_is_redacted_and_written_on_one_line(self) -> None:
        """失敗理由からURL認証情報と改行を除いてmanifestへ記録すること"""

        def failing_fetcher(_url: str) -> str:
            raise RuntimeError(
                'failed https://user:secret@example.com/path\nnext line'
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            state = _create_state(root)

            with self.assertRaises(RuntimeError):
                state.load_or_fetch(INDEX_URL, failing_fetcher)

            manifest = json.loads(
                (root / 'manifest.json').read_text(encoding='utf-8')
            )
            failure = manifest['pages'][0]['failure']

        self.assertEqual(failure['exception'], 'RuntimeError')
        self.assertNotIn('secret', failure['reason'])
        self.assertNotIn('\n', failure['reason'])
        self.assertIn('https://[redacted]@example.com/path', failure['reason'])





if __name__ == '__main__':
    unittest.main()

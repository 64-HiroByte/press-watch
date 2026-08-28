from datetime import UTC, datetime
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch

from press_watch_scraper import _crawl_state_storage
from press_watch_scraper.crawl_state import (
    CrawlState,
    CrawlStateError,
    cleanup_crawl_state,
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

    def test_create_rejects_invalid_crawl_conditions(self) -> None:
        """CLI契約外の巡回条件ではstateを作成しないこと"""

        cases = (
            (0, False),
            (-1, False),
            (True, False),
            (1, True),
        )
        for archive_month_limit, all_archive_months in cases:
            with self.subTest(
                archive_month_limit=archive_month_limit,
                all_archive_months=all_archive_months,
            ):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir) / 'state'

                    with self.assertRaisesRegex(
                        CrawlStateError,
                        'crawl conditions are invalid',
                    ):
                        CrawlState.create(
                            root,
                            start_url=INDEX_URL,
                            archive_month_limit=archive_month_limit,
                            all_archive_months=all_archive_months,
                        )

                    self.assertFalse(root.exists())

    def test_resume_rejects_manifest_page_path_traversal(self) -> None:
        """manifestの相対パス逸脱をHTML読込前に拒否すること"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            _complete_index_only_state(root)
            manifest_path = root / 'manifest.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest['pages'][0]['file'] = '../outside.html'
            manifest_path.write_text(
                json.dumps(manifest),
                encoding='utf-8',
            )

            with self.assertRaisesRegex(
                CrawlStateError,
                'page path is invalid',
            ):
                CrawlState.resume(
                    root,
                    start_url=INDEX_URL,
                    archive_month_limit=0,
                    all_archive_months=True,
                    refetch_invalid_pages=True,
                )

    def test_resume_rejects_symlinked_saved_page(self) -> None:
        """保存HTMLがsymlinkならstateを再利用しないこと"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            _complete_index_only_state(root)
            outside_path = Path(temp_dir) / 'outside.html'
            outside_path.write_text(INDEX_HTML, encoding='utf-8')
            page_path = root / 'pages' / 'index.html'
            page_path.unlink()
            page_path.symlink_to(outside_path)

            with self.assertRaisesRegex(
                CrawlStateError,
                'must not be a symlink',
            ):
                CrawlState.resume(
                    root,
                    start_url=INDEX_URL,
                    archive_month_limit=0,
                    all_archive_months=True,
                    refetch_invalid_pages=True,
                )

    def test_resume_rejects_saved_page_hash_mismatch(self) -> None:
        """サイズが同じでもSHA-256が異なる保存HTMLを拒否すること"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            _complete_index_only_state(root)
            page_path = root / 'pages' / 'index.html'
            original_bytes = page_path.read_bytes()
            page_path.write_bytes(original_bytes[:-1] + b'X')

            with self.assertRaisesRegex(
                CrawlStateError,
                'cannot be reused',
            ):
                CrawlState.resume(
                    root,
                    start_url=INDEX_URL,
                    archive_month_limit=0,
                    all_archive_months=True,
                )

            manifest = json.loads(
                (root / 'manifest.json').read_text(encoding='utf-8')
            )

        self.assertEqual(manifest['pages'][0]['status'], 'invalid')
        self.assertIn(
            'hash does not match',
            manifest['pages'][0]['failure']['reason'],
        )

    def test_resume_moves_completed_state_back_to_in_progress(self) -> None:
        """完了stateの再解析前に全体状態を実行中へ戻すこと"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            _complete_index_only_state(root)

            CrawlState.resume(
                root,
                start_url=INDEX_URL,
                archive_month_limit=0,
                all_archive_months=True,
            )

            manifest = json.loads(
                (root / 'manifest.json').read_text(encoding='utf-8')
            )

        self.assertEqual(manifest['status'], 'in_progress')
        self.assertIsNone(manifest['stop_reason'])
        self.assertIsNone(manifest['completed_at'])

    def test_resume_refetches_page_interrupted_during_fetch(self) -> None:
        """取得中断ページは通常再開で未取得として再取得すること"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            _complete_index_only_state(root)
            manifest_path = root / 'manifest.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            page = manifest['pages'][0]
            page['status'] = 'fetching'
            page['size_bytes'] = None
            page['sha256'] = None
            manifest['status'] = 'in_progress'
            manifest['stop_reason'] = None
            manifest['completed_at'] = None
            manifest_path.write_text(
                json.dumps(manifest),
                encoding='utf-8',
            )
            (root / 'pages' / 'index.html').unlink()

            state = CrawlState.resume(
                root,
                start_url=INDEX_URL,
                archive_month_limit=0,
                all_archive_months=True,
            )
            fetcher = Mock(return_value=INDEX_HTML)

            html = state.load_or_fetch(INDEX_URL, fetcher)

        self.assertEqual(html, INDEX_HTML)
        fetcher.assert_called_once_with(INDEX_URL)

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

    def test_register_archive_pages_rejects_url_with_credentials(self) -> None:
        """認証情報を含む月別URLをmanifestへ保存しないこと"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            state = _create_state(root)

            with self.assertRaisesRegex(CrawlStateError, 'URL is invalid'):
                state.register_archive_pages(
                    (
                        ArchiveMonthLink(
                            year=2026,
                            month=5,
                            url=(
                                'https://user:password@example.com/'
                                'press/202605.html'
                            ),
                        ),
                    )
                )

            manifest_text = (root / 'manifest.json').read_text(
                encoding='utf-8'
            )

        self.assertNotIn('user:password', manifest_text)

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
                _crawl_state_storage.os,
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

    def test_failed_manifest_replace_keeps_previous_manifest(self) -> None:
        """manifest置換失敗時は旧内容を保持して一時ファイルを消すこと"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            state = _create_state(root)
            manifest_path = root / 'manifest.json'
            original_manifest = manifest_path.read_bytes()
            fetcher = Mock(return_value=INDEX_HTML)

            with patch.object(
                _crawl_state_storage.os,
                'replace',
                side_effect=OSError('replace failed'),
            ):
                with self.assertRaisesRegex(OSError, 'replace failed'):
                    state.load_or_fetch(INDEX_URL, fetcher)

            manifest_after_failure = manifest_path.read_bytes()
            root_entries = {path.name for path in root.iterdir()}

        self.assertEqual(manifest_after_failure, original_manifest)
        self.assertEqual(root_entries, {'manifest.json', 'pages'})
        fetcher.assert_not_called()

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

    def test_resume_rejects_invalid_manifest_schema_values(self) -> None:
        """version、列挙値、必須型が不正なmanifestを拒否すること"""

        cases = (
            ('version', 2, 'version is unsupported'),
            ('version', True, 'version is invalid'),
            ('status', 'unknown', 'status is invalid'),
            ('status', [], 'status is invalid'),
            ('pages', {}, 'pages are invalid'),
        )
        for field, invalid_value, expected_reason in cases:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir) / 'state'
                    _complete_index_only_state(root)
                    manifest_path = root / 'manifest.json'
                    manifest = json.loads(
                        manifest_path.read_text(encoding='utf-8')
                    )
                    manifest[field] = invalid_value
                    manifest_path.write_text(
                        json.dumps(manifest),
                        encoding='utf-8',
                    )

                    with self.assertRaisesRegex(
                        CrawlStateError,
                        expected_reason,
                    ):
                        CrawlState.resume(
                            root,
                            start_url=INDEX_URL,
                            archive_month_limit=0,
                            all_archive_months=True,
                        )

    def test_resume_rejects_malformed_manifest_json(self) -> None:
        """JSONとして壊れたmanifestを再開前に拒否すること"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            _complete_index_only_state(root)
            (root / 'manifest.json').write_text(
                '{invalid',
                encoding='utf-8',
            )

            with self.assertRaisesRegex(
                CrawlStateError,
                'manifest is invalid',
            ):
                CrawlState.resume(
                    root,
                    start_url=INDEX_URL,
                    archive_month_limit=0,
                    all_archive_months=True,
                )

    def test_resume_rejects_failure_stage_mismatched_with_status(self) -> None:
        """ページ状態と失敗段階が矛盾するmanifestを拒否すること"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            _complete_index_only_state(root)
            manifest_path = root / 'manifest.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            page = manifest['pages'][0]
            page['status'] = 'fetch_failed'
            page['size_bytes'] = None
            page['sha256'] = None
            page['failure'] = {
                'stage': 'parse',
                'exception': 'RuntimeError',
                'reason': 'parser failed',
                'occurred_at': page['updated_at'],
            }
            manifest['status'] = 'failed'
            manifest['stop_reason'] = None
            manifest['completed_at'] = None
            manifest_path.write_text(
                json.dumps(manifest),
                encoding='utf-8',
            )

            with self.assertRaisesRegex(
                CrawlStateError,
                'failure stage does not match page status',
            ):
                CrawlState.resume(
                    root,
                    start_url=INDEX_URL,
                    archive_month_limit=0,
                    all_archive_months=True,
                )

    def test_resume_rejects_failed_state_without_failed_page(self) -> None:
        """失敗ページがないfailed manifestを拒否すること"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            _complete_index_only_state(root)
            manifest_path = root / 'manifest.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest['status'] = 'failed'
            manifest['stop_reason'] = None
            manifest['completed_at'] = None
            manifest_path.write_text(
                json.dumps(manifest),
                encoding='utf-8',
            )

            with self.assertRaisesRegex(
                CrawlStateError,
                'failed crawl state requires a failed page',
            ):
                CrawlState.resume(
                    root,
                    start_url=INDEX_URL,
                    archive_month_limit=0,
                    all_archive_months=True,
                )

    def test_resume_rejects_manifest_with_public_permissions(self) -> None:
        """所有者以外が読めるmanifestを再利用しないこと"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            _complete_index_only_state(root)
            (root / 'manifest.json').chmod(0o644)

            with self.assertRaisesRegex(
                CrawlStateError,
                'permissions must be 0600',
            ):
                CrawlState.resume(
                    root,
                    start_url=INDEX_URL,
                    archive_month_limit=0,
                    all_archive_months=True,
                )

    def test_cleanup_removes_recognized_internal_temporary_files(self) -> None:
        """完了stateの内部一時ファイルは管理対象として削除すること"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            _complete_index_only_state(root)
            manifest_temp = root / '.manifest.json.interrupted.tmp'
            page_temp = root / 'pages' / '.index.html.interrupted.tmp'
            manifest_temp.write_text('temporary', encoding='utf-8')
            page_temp.write_text('temporary', encoding='utf-8')
            manifest_temp.chmod(0o600)
            page_temp.chmod(0o600)

            cleanup_crawl_state(root)
            root_exists = root.exists()

        self.assertFalse(root_exists)

    def test_cleanup_rejects_symlinked_page_without_deleting_files(
        self,
    ) -> None:
        """symlinkを検出したcleanupはstateとリンク先を削除しないこと"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'state'
            _complete_index_only_state(root)
            outside_path = Path(temp_dir) / 'outside.html'
            outside_path.write_text(INDEX_HTML, encoding='utf-8')
            page_path = root / 'pages' / 'index.html'
            page_path.unlink()
            page_path.symlink_to(outside_path)

            with self.assertRaisesRegex(
                CrawlStateError,
                'missing or invalid',
            ):
                cleanup_crawl_state(root)

            root_still_exists = root.exists()
            outside_still_exists = outside_path.exists()

        self.assertTrue(root_still_exists)
        self.assertTrue(outside_still_exists)


if __name__ == '__main__':
    unittest.main()

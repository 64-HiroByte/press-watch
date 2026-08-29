from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from press_watch_scraper import __main__ as cli
from press_watch_scraper import env_press

from test_cli import (
    EXISTING_OUTPUT_JSON,
    EXAMPLE_APRIL_ARCHIVE_URL,
    EXAMPLE_INDEX_URL,
    EXAMPLE_MAY_ARCHIVE_URL,
    EXAMPLE_MAY_RELEASE_URL,
    FETCH_ERROR_REASON,
    FETCH_PRESS_PAGE_HTML_ATTR,
    _all_archive_months_args,
    _archive_month_limit_args,
    _archive_html_by_url,
    _cli_argv,
    _from_file_args,
    _known_release_urls_file_args,
    _output_args,
    _press_index_html,
    _recording_html_fetcher,
    _run_cli,
    _run_cli_raw,
    _url_args,
    _verbose_args,
)


CLEANUP_CRAWL_STATE_ARG = '--cleanup-crawl-state'
CRAWL_STATE_DIR_ARG = '--crawl-state-dir'
REFETCH_INVALID_PAGES_ARG = '--refetch-invalid-pages'
RESUME_ARG = '--resume'


def _crawl_state_dir_args(path: Path) -> tuple[str, str]:
    """巡回stateディレクトリ指定のCLI引数を生成

    Args:
        path: `--crawl-state-dir` に渡すディレクトリパス

    Returns:
        `--crawl-state-dir` とディレクトリパス値の引数列
    """

    return (CRAWL_STATE_DIR_ARG, str(path))


def _resume_args() -> tuple[str]:
    """巡回再開指定のCLI引数を生成

    Returns:
        `--resume` の引数列
    """

    return (RESUME_ARG,)


def _refetch_invalid_pages_args() -> tuple[str]:
    """検証不能ページ再取得指定のCLI引数を生成

    Returns:
        `--refetch-invalid-pages` の引数列
    """

    return (REFETCH_INVALID_PAGES_ARG,)


def _cleanup_crawl_state_args(path: Path) -> tuple[str, str]:
    """完了巡回state削除指定のCLI引数を生成

    Args:
        path: `--cleanup-crawl-state` に渡すディレクトリパス

    Returns:
        `--cleanup-crawl-state` とディレクトリパス値の引数列
    """

    return (CLEANUP_CRAWL_STATE_ARG, str(path))


class ScraperCrawlStateCliTest(unittest.TestCase):
    """巡回stateを利用するscraper CLIのテスト"""

    def test_main_saves_pages_and_manifest_in_crawl_state(self) -> None:
        """新規巡回で解析前HTMLと完了manifestを保存すること"""

        html_by_url = _archive_html_by_url()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=lambda url, **_kwargs: html_by_url[url],
            ):
                payload = _run_cli(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                )

            manifest = json.loads(
                (state_dir / 'manifest.json').read_text(encoding='utf-8')
            )
            index_html = (state_dir / 'pages' / 'index.html').read_text(
                encoding='utf-8'
            )
            may_html = (
                state_dir / 'pages' / 'archive-0001.html'
            ).read_text(encoding='utf-8')
            april_html = (
                state_dir / 'pages' / 'archive-0002.html'
            ).read_text(encoding='utf-8')

        self.assertEqual(payload['exit_code'], 0)
        self.assertEqual(index_html, html_by_url[EXAMPLE_INDEX_URL])
        self.assertEqual(may_html, html_by_url[EXAMPLE_MAY_ARCHIVE_URL])
        self.assertEqual(april_html, html_by_url[EXAMPLE_APRIL_ARCHIVE_URL])
        self.assertEqual(manifest['version'], 1)
        self.assertIs(manifest['archive_plan_registered'], True)
        self.assertEqual(manifest['status'], 'complete')
        self.assertEqual(
            [page['status'] for page in manifest['pages']],
            ['parsed', 'parsed', 'parsed'],
        )
        self.assertEqual(
            [page['url'] for page in manifest['pages']],
            [
                EXAMPLE_INDEX_URL,
                EXAMPLE_MAY_ARCHIVE_URL,
                EXAMPLE_APRIL_ARCHIVE_URL,
            ],
        )
        self.assertIsNotNone(manifest['created_at'])
        self.assertIsNotNone(manifest['updated_at'])
        self.assertIsNotNone(manifest['completed_at'])

    def test_main_saves_limited_archive_crawl_in_state(self) -> None:
        """正の月別件数指定でも対象ページだけをstateへ保存すること"""

        html_by_url = _archive_html_by_url()
        fetched_urls: list[str] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

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
                    *_archive_month_limit_args(limit=1),
                    *_crawl_state_dir_args(state_dir),
                )

            manifest = json.loads(
                (state_dir / 'manifest.json').read_text(encoding='utf-8')
            )

        self.assertEqual(payload['exit_code'], 0)
        self.assertEqual(
            fetched_urls,
            [EXAMPLE_INDEX_URL, EXAMPLE_MAY_ARCHIVE_URL],
        )
        self.assertEqual(manifest['crawl_mode'], 'archive_month_limit')
        self.assertEqual(manifest['archive_month_limit'], 1)
        self.assertEqual(manifest['status'], 'complete')
        self.assertEqual(len(manifest['pages']), 2)

    def test_main_resumes_after_archive_page_fetch_failure(self) -> None:
        """取得失敗後に保存済みHTMLを再利用して失敗ページだけ取得すること"""

        html_by_url = _archive_html_by_url()
        first_fetched_urls: list[str] = []
        resumed_fetched_urls: list[str] = []

        def failing_fetcher(url: str, **_kwargs: object) -> str:
            first_fetched_urls.append(url)
            if url == EXAMPLE_APRIL_ARCHIVE_URL:
                raise URLError(FETCH_ERROR_REASON)
            return html_by_url[url]

        def resumed_fetcher(url: str, **_kwargs: object) -> str:
            resumed_fetched_urls.append(url)
            return html_by_url[url]

        with patch.object(
            cli,
            FETCH_PRESS_PAGE_HTML_ATTR,
            side_effect=lambda url, **_kwargs: html_by_url[url],
        ):
            uninterrupted_payload = _run_cli(
                *_url_args(),
                *_all_archive_months_args(),
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'
            output_path = Path(temp_dir) / 'snapshot.json'
            output_path.write_text(
                EXISTING_OUTPUT_JSON,
                encoding=cli.JSON_OUTPUT_ENCODING,
            )

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=failing_fetcher,
            ):
                first_exit_code, first_stdout, _first_stderr = _run_cli_raw(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                    *_output_args(output_path),
                )

            failed_manifest = json.loads(
                (state_dir / 'manifest.json').read_text(encoding='utf-8')
            )
            output_after_failure = output_path.read_text(
                encoding=cli.JSON_OUTPUT_ENCODING
            )

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=resumed_fetcher,
            ):
                resumed_payload = _run_cli(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                    *_resume_args(),
                    *_output_args(output_path),
                )

            completed_manifest = json.loads(
                (state_dir / 'manifest.json').read_text(encoding='utf-8')
            )

        self.assertEqual(first_exit_code, 1)
        self.assertEqual(first_stdout, '')
        self.assertEqual(output_after_failure, EXISTING_OUTPUT_JSON)
        self.assertEqual(
            first_fetched_urls,
            [
                EXAMPLE_INDEX_URL,
                EXAMPLE_MAY_ARCHIVE_URL,
                EXAMPLE_APRIL_ARCHIVE_URL,
            ],
        )
        self.assertEqual(failed_manifest['status'], 'failed')
        self.assertEqual(
            [page['status'] for page in failed_manifest['pages']],
            ['parsed', 'parsed', 'fetch_failed'],
        )
        self.assertEqual(
            failed_manifest['pages'][2]['failure']['stage'],
            'fetch',
        )
        self.assertEqual(
            resumed_fetched_urls,
            [EXAMPLE_APRIL_ARCHIVE_URL],
        )
        self.assertEqual(resumed_payload['exit_code'], 0)
        self.assertEqual(resumed_payload, uninterrupted_payload)
        self.assertEqual(completed_manifest['status'], 'complete')
        self.assertEqual(
            [page['status'] for page in completed_manifest['pages']],
            ['parsed', 'parsed', 'parsed'],
        )

    def test_main_verbose_distinguishes_reused_and_fetched_pages(self) -> None:
        """再開時の保存HTML再利用と実HTTP取得を別の進捗で示すこと"""

        html_by_url = _archive_html_by_url()

        def failing_fetcher(url: str, **_kwargs: object) -> str:
            if url == EXAMPLE_APRIL_ARCHIVE_URL:
                raise URLError(FETCH_ERROR_REASON)
            return html_by_url[url]

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=failing_fetcher,
            ):
                first_exit_code, _first_stdout, _first_stderr = _run_cli_raw(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                )

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=lambda url, **_kwargs: html_by_url[url],
            ):
                resumed_exit_code, _resumed_stdout, resumed_stderr = (
                    _run_cli_raw(
                        *_url_args(),
                        *_all_archive_months_args(),
                        *_crawl_state_dir_args(state_dir),
                        *_resume_args(),
                        *_verbose_args(),
                    )
                )

        self.assertEqual(first_exit_code, 1)
        self.assertEqual(resumed_exit_code, 0)
        self.assertIn(
            f'reusing saved crawl page: {EXAMPLE_INDEX_URL}',
            resumed_stderr,
        )
        self.assertIn(
            f'reusing saved crawl page: {EXAMPLE_MAY_ARCHIVE_URL}',
            resumed_stderr,
        )
        self.assertIn(
            f'fetching crawl page: {EXAMPLE_APRIL_ARCHIVE_URL}',
            resumed_stderr,
        )

    def test_main_reparses_saved_html_after_parse_failure(self) -> None:
        """解析失敗後に実HTTPなしで保存済みHTMLを再解析すること"""

        html_by_url = _archive_html_by_url()
        first_fetched_urls: list[str] = []
        resumed_fetched_urls: list[str] = []
        parse_press_releases = env_press.parse_press_releases

        def failing_parser(html: str, base_url: str) -> object:
            if base_url == EXAMPLE_APRIL_ARCHIVE_URL:
                raise RuntimeError('archive parser failed')
            return parse_press_releases(html, base_url=base_url)

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

            with (
                patch.object(
                    cli,
                    FETCH_PRESS_PAGE_HTML_ATTR,
                    side_effect=_recording_html_fetcher(
                        html_by_url,
                        first_fetched_urls,
                    ),
                ),
                patch.object(
                    env_press,
                    'parse_press_releases',
                    side_effect=failing_parser,
                ),
            ):
                first_exit_code, first_stdout, _first_stderr = _run_cli_raw(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                )

            failed_manifest = json.loads(
                (state_dir / 'manifest.json').read_text(encoding='utf-8')
            )

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=_recording_html_fetcher(
                    html_by_url,
                    resumed_fetched_urls,
                ),
            ):
                resumed_payload = _run_cli(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                    *_resume_args(),
                )

        self.assertEqual(first_exit_code, 1)
        self.assertEqual(first_stdout, '')
        self.assertEqual(
            [page['status'] for page in failed_manifest['pages']],
            ['parsed', 'parsed', 'parse_failed'],
        )
        self.assertEqual(
            failed_manifest['pages'][2]['failure']['stage'],
            'parse',
        )
        self.assertEqual(resumed_fetched_urls, [])
        self.assertEqual(resumed_payload['exit_code'], 0)
        self.assertEqual(resumed_payload['count'], 2)

    def test_main_reports_reused_page_url_when_reparse_fails(self) -> None:
        """保存HTMLの再解析失敗時に対象ページURLをstderrへ出すこと"""

        html_by_url = _archive_html_by_url()
        parse_press_releases = env_press.parse_press_releases

        def failing_parser(html: str, base_url: str) -> object:
            if base_url == EXAMPLE_APRIL_ARCHIVE_URL:
                raise RuntimeError('archive parser failed again')
            return parse_press_releases(html, base_url=base_url)

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

            with (
                patch.object(
                    cli,
                    FETCH_PRESS_PAGE_HTML_ATTR,
                    side_effect=lambda url, **_kwargs: html_by_url[url],
                ),
                patch.object(
                    env_press,
                    'parse_press_releases',
                    side_effect=failing_parser,
                ),
            ):
                first_exit_code, _first_stdout, _first_stderr = _run_cli_raw(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                )

            with (
                patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as resumed_fetch,
                patch.object(
                    env_press,
                    'parse_press_releases',
                    side_effect=failing_parser,
                ),
            ):
                resumed_exit_code, resumed_stdout, resumed_stderr = (
                    _run_cli_raw(
                        *_url_args(),
                        *_all_archive_months_args(),
                        *_crawl_state_dir_args(state_dir),
                        *_resume_args(),
                    )
                )

        self.assertEqual(first_exit_code, 1)
        self.assertEqual(resumed_exit_code, 1)
        self.assertEqual(resumed_stdout, '')
        self.assertIn(
            f'target={EXAMPLE_APRIL_ARCHIVE_URL}',
            resumed_stderr,
        )
        resumed_fetch.assert_not_called()

    def test_main_refetches_invalid_page_only_when_explicitly_requested(
        self,
    ) -> None:
        """破損HTMLは通常再開で拒否し、明示指定時だけ再取得すること"""

        html_by_url = _archive_html_by_url()
        refetched_urls: list[str] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=lambda url, **_kwargs: html_by_url[url],
            ):
                initial_payload = _run_cli(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                )

            invalid_page_path = (
                state_dir / 'pages' / 'archive-0002.html'
            )
            invalid_page_path.write_text('damaged', encoding='utf-8')

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
            ) as rejected_fetch:
                rejected_exit_code, rejected_stdout, rejected_stderr = (
                    _run_cli_raw(
                        *_url_args(),
                        *_all_archive_months_args(),
                        *_crawl_state_dir_args(state_dir),
                        *_resume_args(),
                    )
                )

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=_recording_html_fetcher(
                    html_by_url,
                    refetched_urls,
                ),
            ):
                resumed_exit_code, resumed_stdout, resumed_stderr = (
                    _run_cli_raw(
                        *_url_args(),
                        *_all_archive_months_args(),
                        *_crawl_state_dir_args(state_dir),
                        *_resume_args(),
                        *_refetch_invalid_pages_args(),
                    )
                )

            repaired_html = invalid_page_path.read_text(encoding='utf-8')

        self.assertEqual(initial_payload['exit_code'], 0)
        self.assertEqual(rejected_exit_code, 1)
        self.assertEqual(rejected_stdout, '')
        self.assertIn('crawl page cannot be reused', rejected_stderr)
        rejected_fetch.assert_not_called()
        self.assertEqual(resumed_exit_code, 0, resumed_stderr)
        self.assertNotEqual(resumed_stdout, '')
        self.assertEqual(refetched_urls, [EXAMPLE_APRIL_ARCHIVE_URL])
        self.assertEqual(repaired_html, html_by_url[EXAMPLE_APRIL_ARCHIVE_URL])

    def test_main_recreates_final_json_from_completed_state(self) -> None:
        """完了stateから実HTTPなしで同じ最終JSONを再生成すること"""

        html_by_url = _archive_html_by_url()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=lambda url, **_kwargs: html_by_url[url],
            ):
                first_exit_code, first_stdout, _first_stderr = _run_cli_raw(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                )

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
            ) as resumed_fetch:
                resumed_exit_code, resumed_stdout, _resumed_stderr = (
                    _run_cli_raw(
                        *_url_args(),
                        *_all_archive_months_args(),
                        *_crawl_state_dir_args(state_dir),
                        *_resume_args(),
                    )
                )

        self.assertEqual(first_exit_code, 0)
        self.assertEqual(resumed_exit_code, 0)
        self.assertEqual(resumed_stdout, first_stdout)
        resumed_fetch.assert_not_called()

    def test_main_rejects_changed_archive_plan_after_index_refetch(
        self,
    ) -> None:
        """起点再取得後の月別対象がmanifestと異なる場合は続行しないこと"""

        html_by_url = _archive_html_by_url()
        changed_index_html = _press_index_html().replace(
            '202604.html',
            '202603.html',
        ).replace(
            '2026年4月',
            '2026年3月',
        )
        refetched_urls: list[str] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=lambda url, **_kwargs: html_by_url[url],
            ):
                _run_cli(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                )

            (state_dir / 'pages' / 'index.html').write_text(
                'damaged',
                encoding='utf-8',
            )

            def changed_index_fetcher(url: str, **_kwargs: object) -> str:
                refetched_urls.append(url)
                return changed_index_html

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=changed_index_fetcher,
            ):
                exit_code, stdout, stderr = _run_cli_raw(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                    *_resume_args(),
                    *_refetch_invalid_pages_args(),
                )

            failed_manifest = json.loads(
                (state_dir / 'manifest.json').read_text(encoding='utf-8')
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertIn(
            'archive page plan does not match crawl state manifest',
            stderr,
        )
        self.assertEqual(refetched_urls, [EXAMPLE_INDEX_URL])
        self.assertEqual(failed_manifest['status'], 'failed')
        self.assertEqual(
            failed_manifest['pages'][0]['status'],
            'invalid',
        )
        self.assertEqual(
            failed_manifest['pages'][0]['failure']['stage'],
            'validate',
        )

    def test_main_rejects_new_archive_plan_after_refetching_empty_plan(
        self,
    ) -> None:
        """確定済み対象0件から月別対象が増えた場合も続行しないこと"""

        html_by_url = _archive_html_by_url()
        refetched_urls: list[str] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                return_value='<html></html>',
            ):
                initial_payload = _run_cli(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                )

            (state_dir / 'pages' / 'index.html').write_text(
                'damaged',
                encoding='utf-8',
            )

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=_recording_html_fetcher(
                    html_by_url,
                    refetched_urls,
                ),
            ):
                exit_code, stdout, stderr = _run_cli_raw(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                    *_resume_args(),
                    *_refetch_invalid_pages_args(),
                )

            failed_manifest = json.loads(
                (state_dir / 'manifest.json').read_text(encoding='utf-8')
            )

        self.assertEqual(initial_payload['exit_code'], 0)
        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, '')
        self.assertIn(
            'archive page plan does not match crawl state manifest',
            stderr,
        )
        self.assertEqual(refetched_urls, [EXAMPLE_INDEX_URL])
        self.assertEqual(failed_manifest['status'], 'failed')
        self.assertEqual(len(failed_manifest['pages']), 1)
        self.assertEqual(
            failed_manifest['pages'][0]['status'],
            'invalid',
        )

    def test_main_cleans_up_valid_completed_crawl_state(self) -> None:
        """検証済み完了stateだけを専用操作で削除すること"""

        html_by_url = _archive_html_by_url()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=lambda url, **_kwargs: html_by_url[url],
            ):
                initial_payload = _run_cli(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                )

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
            ) as cleanup_fetch:
                cleanup_exit_code, cleanup_stdout, cleanup_stderr = (
                    _run_cli_raw(*_cleanup_crawl_state_args(state_dir))
                )

            state_exists_after_cleanup = state_dir.exists()

        self.assertEqual(initial_payload['exit_code'], 0)
        self.assertEqual(cleanup_exit_code, 0)
        self.assertEqual(cleanup_stdout, '')
        self.assertIn('deleted crawl state', cleanup_stderr)
        self.assertFalse(state_exists_after_cleanup)
        cleanup_fetch.assert_not_called()

    def test_main_refuses_cleanup_of_incomplete_crawl_state(self) -> None:
        """未完了stateのcleanupは何も削除せず失敗すること"""

        html_by_url = _archive_html_by_url()

        def failing_fetcher(url: str, **_kwargs: object) -> str:
            if url == EXAMPLE_APRIL_ARCHIVE_URL:
                raise URLError(FETCH_ERROR_REASON)
            return html_by_url[url]

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=failing_fetcher,
            ):
                crawl_exit_code, _crawl_stdout, _crawl_stderr = _run_cli_raw(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                )

            cleanup_exit_code, cleanup_stdout, cleanup_stderr = _run_cli_raw(
                *_cleanup_crawl_state_args(state_dir)
            )
            manifest_still_exists = (state_dir / 'manifest.json').is_file()

        self.assertEqual(crawl_exit_code, 1)
        self.assertEqual(cleanup_exit_code, 1)
        self.assertEqual(cleanup_stdout, '')
        self.assertIn('crawl state is not complete', cleanup_stderr)
        self.assertTrue(manifest_still_exists)

    def test_main_refuses_cleanup_when_state_has_unmanaged_file(self) -> None:
        """管理外ファイルがある完了stateは何も削除しないこと"""

        html_by_url = _archive_html_by_url()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

            with patch.object(
                cli,
                FETCH_PRESS_PAGE_HTML_ATTR,
                side_effect=lambda url, **_kwargs: html_by_url[url],
            ):
                _run_cli(
                    *_url_args(),
                    *_all_archive_months_args(),
                    *_crawl_state_dir_args(state_dir),
                )

            unmanaged_path = state_dir / 'keep.txt'
            unmanaged_path.write_text('keep', encoding='utf-8')
            cleanup_exit_code, cleanup_stdout, cleanup_stderr = _run_cli_raw(
                *_cleanup_crawl_state_args(state_dir)
            )
            manifest_still_exists = (state_dir / 'manifest.json').is_file()
            unmanaged_still_exists = unmanaged_path.is_file()

        self.assertEqual(cleanup_exit_code, 1)
        self.assertEqual(cleanup_stdout, '')
        self.assertIn('unmanaged crawl state entry', cleanup_stderr)
        self.assertTrue(manifest_still_exists)
        self.assertTrue(unmanaged_still_exists)

    def test_main_rejects_resume_without_crawl_state_dir(self) -> None:
        """stateディレクトリなしの再開指定を取得前に拒否すること"""

        stderr = io.StringIO()

        with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
            with patch('sys.argv', _cli_argv(*_resume_args())):
                with redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            '--resume requires --crawl-state-dir',
            stderr.getvalue(),
        )
        mock_fetch.assert_not_called()

    def test_main_rejects_cleanup_with_explicit_crawl_url(self) -> None:
        """cleanupと明示的な巡回URLの併用を処理開始前に拒否すること"""

        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

            with patch.object(cli, 'cleanup_crawl_state') as mock_cleanup:
                with patch(
                    'sys.argv',
                    _cli_argv(
                        *_cleanup_crawl_state_args(state_dir),
                        *_url_args(),
                    ),
                ):
                    with redirect_stderr(stderr):
                        with self.assertRaises(SystemExit) as raised:
                            cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            '--cleanup-crawl-state cannot be combined with crawl or output '
            'options',
            stderr.getvalue(),
        )
        mock_cleanup.assert_not_called()

    def test_main_rejects_crawl_state_without_archive_crawl(self) -> None:
        """月別巡回指定なしのstate利用を取得前に拒否すること"""

        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

            with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
                with patch(
                    'sys.argv',
                    _cli_argv(*_crawl_state_dir_args(state_dir)),
                ):
                    with redirect_stderr(stderr):
                        with self.assertRaises(SystemExit) as raised:
                            cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            '--crawl-state-dir requires --archive-month-limit greater than 0 '
            'or --all-archive-months',
            stderr.getvalue(),
        )
        mock_fetch.assert_not_called()

    def test_main_rejects_refetch_without_resume(self) -> None:
        """通常再開なしの検証不能ページ再取得を拒否すること"""

        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'

            with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
                with patch(
                    'sys.argv',
                    _cli_argv(
                        *_crawl_state_dir_args(state_dir),
                        *_all_archive_months_args(),
                        *_refetch_invalid_pages_args(),
                    ),
                ):
                    with redirect_stderr(stderr):
                        with self.assertRaises(SystemExit) as raised:
                            cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            '--refetch-invalid-pages requires --resume',
            stderr.getvalue(),
        )
        mock_fetch.assert_not_called()

    def test_main_rejects_output_inside_crawl_state(self) -> None:
        """完成スナップショットをstate配下へ保存する指定を拒否すること"""

        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'
            state_dir.mkdir()
            output_path = state_dir / 'snapshot.json'

            with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
                with patch(
                    'sys.argv',
                    _cli_argv(
                        *_all_archive_months_args(),
                        *_crawl_state_dir_args(state_dir),
                        *_output_args(output_path),
                    ),
                ):
                    with redirect_stderr(stderr):
                        with self.assertRaises(SystemExit) as raised:
                            cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            '--output must be outside --crawl-state-dir',
            stderr.getvalue(),
        )
        mock_fetch.assert_not_called()

    def test_main_rejects_known_release_urls_with_crawl_state(self) -> None:
        """既知URLによる差分取得とローカルstateの併用を拒否すること"""

        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'
            known_urls_path = Path(temp_dir) / 'known-release-urls.txt'
            known_urls_path.write_text(
                EXAMPLE_MAY_RELEASE_URL,
                encoding=cli.JSON_OUTPUT_ENCODING,
            )

            with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
                with patch(
                    'sys.argv',
                    _cli_argv(
                        *_all_archive_months_args(),
                        *_crawl_state_dir_args(state_dir),
                        *_known_release_urls_file_args(known_urls_path),
                    ),
                ):
                    with redirect_stderr(stderr):
                        with self.assertRaises(SystemExit) as raised:
                            cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            '--known-release-urls-file cannot be used with '
            '--crawl-state-dir',
            stderr.getvalue(),
        )
        mock_fetch.assert_not_called()

    def test_main_rejects_from_file_with_crawl_state(self) -> None:
        """保存HTML入力とローカルstateの併用を拒否すること"""

        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / 'crawl-state'
            html_path = Path(temp_dir) / 'index.html'
            html_path.write_text(_press_index_html(), encoding='utf-8')

            with patch.object(cli, FETCH_PRESS_PAGE_HTML_ATTR) as mock_fetch:
                with patch(
                    'sys.argv',
                    _cli_argv(
                        *_from_file_args(html_path),
                        *_all_archive_months_args(),
                        *_crawl_state_dir_args(state_dir),
                    ),
                ):
                    with redirect_stderr(stderr):
                        with self.assertRaises(SystemExit) as raised:
                            cli.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn(
            '--from-file cannot be used with --all-archive-months',
            stderr.getvalue(),
        )
        mock_fetch.assert_not_called()

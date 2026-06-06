from __future__ import annotations

from datetime import date
import io
import json
import unittest
from unittest.mock import Mock, patch

from sqlalchemy.orm import Session

from press_watch_api.commands.import_env_press import (
    CollectedPressReleases,
    ScraperCliRelease,
    _parse_scraper_snapshot,
    _scraper_command,
    main,
)

from api_test_constants import (
    ENV_PRESS_INDEX_URL as INDEX_URL,
    ENV_PRESS_RELEASE_URL_1 as SOURCE_URL_1,
    ENV_PRESS_RELEASE_URL_2 as SOURCE_URL_2,
)


class ManualImportCommandTest(unittest.TestCase):
    """手動importコマンドのテスト"""

    def test_main_imports_scraper_releases_and_commits(self) -> None:
        """取得結果を保存serviceへ渡し、成功時にcommitすること"""

        session = Mock(spec=Session)
        session.scalar.return_value = None
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = main(
            ["--url", INDEX_URL],
            session_factory=lambda: session,
            collect_releases=lambda _args, _stderr: _collected_releases(),
            stdout=stdout,
            stderr=stderr,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(payload["source_url"], INDEX_URL)
        self.assertEqual(payload["fetched_count"], 2)
        self.assertEqual(payload["saved_count"], 2)
        self.assertEqual(payload["skipped_count"], 0)
        self.assertEqual(payload["fetched_page_urls"], [INDEX_URL])
        self.assertIsNone(payload["stop_reason"])
        session.commit.assert_called_once_with()
        session.rollback.assert_not_called()
        session.close.assert_called_once_with()
        self.assertEqual(
            [
                press_release.source_url
                for press_release in (
                    session.add.call_args_list[0].args[0],
                    session.add.call_args_list[1].args[0],
                )
            ],
            [SOURCE_URL_1, SOURCE_URL_2],
        )

    def test_main_reports_skipped_count(self) -> None:
        """既存URLをskip件数としてstdout JSONへ出すこと"""

        session = Mock(spec=Session)
        session.scalar.side_effect = [None, 1]
        stdout = io.StringIO()

        exit_code = main(
            [],
            session_factory=lambda: session,
            collect_releases=lambda _args, _stderr: _collected_releases(),
            stdout=stdout,
            stderr=io.StringIO(),
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["fetched_count"], 2)
        self.assertEqual(payload["saved_count"], 1)
        self.assertEqual(payload["skipped_count"], 1)
        session.commit.assert_called_once_with()
        session.rollback.assert_not_called()

    def test_main_rolls_back_and_writes_stderr_on_failure(self) -> None:
        """失敗時にrollbackし、stderrと終了コードで失敗を伝えること"""

        session = Mock(spec=Session)
        stdout = io.StringIO()
        stderr = io.StringIO()

        def collect_releases(
            _args: object,
            _stderr: object,
        ) -> CollectedPressReleases:
            raise RuntimeError("database\nunavailable")

        exit_code = main(
            ["--url", INDEX_URL],
            session_factory=lambda: session,
            collect_releases=collect_releases,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            stderr.getvalue(),
            (
                "error: "
                f"target={INDEX_URL} "
                "exception=RuntimeError "
                "reason=database unavailable\n"
            ),
        )
        session.commit.assert_not_called()
        session.rollback.assert_called_once_with()
        session.close.assert_called_once_with()

    def test_parse_scraper_snapshot_restores_releases(self) -> None:
        """scraper CLI JSONを保存serviceへ渡せる取得結果へ復元すること"""

        snapshot_json = json.dumps(
            {
                "source_url": INDEX_URL,
                "items": [
                    {
                        "title": "報道発表1",
                        "published_at": "2026-05-01",
                        "url": SOURCE_URL_1,
                        "source_categories": ["総合政策"],
                    },
                    {
                        "title": "報道発表2",
                        "published_at": "2026-05-02",
                        "url": SOURCE_URL_2,
                        "source_categories": [],
                    },
                ],
                "fetched_page_urls": [INDEX_URL],
                "stop_reason": None,
            },
            ensure_ascii=False,
        )

        collected = _parse_scraper_snapshot(snapshot_json)

        self.assertEqual(collected.source_url, INDEX_URL)
        self.assertEqual(collected.fetched_count, 2)
        self.assertEqual(collected.fetched_page_urls, (INDEX_URL,))
        self.assertIsNone(collected.stop_reason)
        self.assertEqual(collected.releases[0].published_at, date(2026, 5, 1))
        self.assertEqual(collected.releases[0].source_categories, ("総合政策",))
        self.assertEqual(collected.releases[1].source_categories, ())

    def test_scraper_command_uses_locked_scraper_cli(self) -> None:
        """scraper側のlockfileに沿って既存CLIを実行すること"""

        args = Mock(
            url=INDEX_URL,
            from_file=None,
            archive_month_limit=2,
            verbose=True,
        )

        command = _scraper_command(args)

        self.assertEqual(
            command,
            [
                "uv",
                "run",
                "--locked",
                "python",
                "-m",
                "press_watch_scraper",
                "--url",
                INDEX_URL,
                "--archive-month-limit",
                "2",
                "--verbose",
            ],
        )

    def test_collect_releases_from_scraper_cli_reports_subprocess_error(
        self,
    ) -> None:
        """scraper CLI失敗時の理由を上位のstderrへ渡せること"""

        from press_watch_api.commands import import_env_press

        completed = Mock(
            returncode=1,
            stdout="",
            stderr="error: target=fixture exception=ValueError reason=broken\n",
        )
        args = Mock(
            url=INDEX_URL,
            from_file=None,
            archive_month_limit=None,
            verbose=False,
        )

        with patch.object(import_env_press.subprocess, "run") as mock_run:
            mock_run.return_value = completed
            with self.assertRaisesRegex(
                RuntimeError,
                "scraper command failed: exit_code=1",
            ):
                import_env_press._collect_releases_from_scraper_cli(
                    args,
                    io.StringIO(),
                )

    def test_collect_releases_forwards_verbose_stderr_on_success(self) -> None:
        """verbose時はscraper CLIの進捗をstderrへ流すこと"""

        from press_watch_api.commands import import_env_press

        completed = Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "source_url": INDEX_URL,
                    "items": [],
                    "fetched_page_urls": [],
                    "stop_reason": None,
                }
            ),
            stderr=f"fetching page: {INDEX_URL}\n",
        )
        args = Mock(
            url=INDEX_URL,
            from_file=None,
            archive_month_limit=None,
            verbose=True,
        )
        stderr = io.StringIO()

        with patch.object(import_env_press.subprocess, "run") as mock_run:
            mock_run.return_value = completed

            import_env_press._collect_releases_from_scraper_cli(args, stderr)

        self.assertEqual(stderr.getvalue(), completed.stderr)


def _collected_releases() -> CollectedPressReleases:
    """手動importテスト用の取得結果を生成する"""

    return CollectedPressReleases(
        source_url=INDEX_URL,
        releases=(
            ScraperCliRelease(
                title="報道発表1",
                published_at=date(2026, 5, 1),
                url=SOURCE_URL_1,
                source_categories=("総合政策",),
            ),
            ScraperCliRelease(
                title="報道発表2",
                published_at=date(2026, 5, 2),
                url=SOURCE_URL_2,
                source_categories=(),
            ),
        ),
        fetched_page_urls=(INDEX_URL,),
        stop_reason=None,
    )


if __name__ == "__main__":
    unittest.main()

from collections.abc import Iterator
from datetime import datetime
import json
import os
from pathlib import Path
from time import perf_counter
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from integration_tests.database import prepare_test_database
from integration_tests.real_snapshot_validation import load_validated_snapshot
from integration_tests.run_real_snapshot import (
    EXPECTED_SNAPSHOT_COUNT,
    EXPECTED_SNAPSHOT_SHA256,
    REAL_SNAPSHOT_PATH_ENV,
    SNAPSHOT_FETCHED_AT_TEXT,
)
from press_watch_api.commands.fetch_and_save_env_press import ScraperCliRelease
from press_watch_api.dependencies import get_db_session
from press_watch_api.main import app
from press_watch_api.services.press_release_save import (
    PressReleaseSaveResult,
    save_press_releases,
)


_DEFAULT_PAGE_SIZE = 50
_EXPECTED_TOTAL_PAGES = 689
_LAST_PAGE = 689
_PAGE_AFTER_LAST = 690
_SEARCH_QUERY = "気候変動"


@unittest.skipUnless(
    os.getenv(REAL_SNAPSHOT_PATH_ENV),
    "実データスナップショット検証runnerでだけ実行します。",
)
class RealSnapshotPostgreSQLIntegrationTest(unittest.TestCase):
    """実スナップショットの保存・一覧API・再投入の統合テスト"""

    @classmethod
    def setUpClass(cls) -> None:
        snapshot_path = os.environ[REAL_SNAPSHOT_PATH_ENV]
        cls.snapshot = load_validated_snapshot(
            Path(snapshot_path),
            expected_count=EXPECTED_SNAPSHOT_COUNT,
            expected_sha256=EXPECTED_SNAPSHOT_SHA256,
            fetched_at_text=SNAPSHOT_FETCHED_AT_TEXT,
        )
        cls.engine = prepare_test_database()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def test_save_api_and_duplicate_prevention_with_real_snapshot(self) -> None:
        """全件保存、一覧API、同一データ再投入を実データ規模で検証すること"""

        timings: dict[str, float] = {}

        with Session(self.engine) as session:
            self.assertEqual(_row_count(session), 0)
            started_at = perf_counter()
            first_save_result = _save_and_commit_without_exposing_snapshot(
                session,
                self.snapshot.releases,
                fetched_at=self.snapshot.fetched_at,
                phase="初回投入",
            )
            timings["initial_save"] = perf_counter() - started_at

            self.assertEqual(first_save_result.saved_count, 34_421)
            self.assertEqual(first_save_result.skipped_count, 0)
            self.assertEqual(_row_count(session), 34_421)
            mismatched_fetched_at_count = session.scalar(
                text(
                    "select count(*) from press_releases "
                    "where fetched_at != :expected_fetched_at"
                ),
                {"expected_fetched_at": self.snapshot.fetched_at},
            )
            self.assertEqual(mismatched_fetched_at_count, 0)

        ordered_releases = tuple(
            release
            for _, release in sorted(
                enumerate(self.snapshot.releases),
                key=lambda indexed_release: (
                    indexed_release[1].published_at,
                    indexed_release[0],
                ),
                reverse=True,
            )
        )

        def override_get_db_session() -> Iterator[Session]:
            with Session(self.engine) as session:
                yield session

        app.dependency_overrides[get_db_session] = override_get_db_session
        self.addCleanup(app.dependency_overrides.clear)

        with TestClient(app) as client:
            first_page, timings["first_page"] = _timed_get(
                client,
                "/press-releases",
                context="先頭ページ取得",
            )
            self.assertEqual(first_page.status_code, 200)
            first_page_payload = first_page.json()
            self.assertEqual(
                first_page_payload["pagination"],
                {
                    "page": 1,
                    "page_size": _DEFAULT_PAGE_SIZE,
                    "total_items": 34_421,
                    "total_pages": _EXPECTED_TOTAL_PAGES,
                },
            )
            _assert_item_count(
                first_page_payload["items"],
                50,
                context="先頭ページ",
            )
            _assert_source_url_order(
                [item["source_url"] for item in first_page_payload["items"]],
                [release.url for release in ordered_releases[:50]],
                context="先頭ページ",
            )

            last_page, timings["last_page"] = _timed_get(
                client,
                "/press-releases",
                params={"page": _LAST_PAGE},
                context="最終ページ取得",
            )
            self.assertEqual(last_page.status_code, 200)
            last_page_payload = last_page.json()
            self.assertEqual(
                last_page_payload["pagination"],
                {
                    "page": _LAST_PAGE,
                    "page_size": _DEFAULT_PAGE_SIZE,
                    "total_items": 34_421,
                    "total_pages": _EXPECTED_TOTAL_PAGES,
                },
            )
            _assert_item_count(
                last_page_payload["items"],
                21,
                context="最終ページ",
            )
            _assert_source_url_order(
                [item["source_url"] for item in last_page_payload["items"]],
                [release.url for release in ordered_releases[34_400:]],
                context="最終ページ",
            )

            after_last_page, _ = _timed_get(
                client,
                "/press-releases",
                params={"page": _PAGE_AFTER_LAST},
                context="最終ページ超過取得",
            )
            self.assertEqual(after_last_page.status_code, 200)
            after_last_page_payload = after_last_page.json()
            self.assertEqual(
                after_last_page_payload["pagination"],
                {
                    "page": _PAGE_AFTER_LAST,
                    "page_size": _DEFAULT_PAGE_SIZE,
                    "total_items": 34_421,
                    "total_pages": _EXPECTED_TOTAL_PAGES,
                },
            )
            _assert_item_count(
                after_last_page_payload["items"],
                0,
                context="最終ページ超過",
            )

            matching_releases = tuple(
                release
                for release in ordered_releases
                if _SEARCH_QUERY.casefold() in release.title.casefold()
            )
            search_response, timings["title_search"] = _timed_get(
                client,
                "/press-releases",
                params={"q": _SEARCH_QUERY},
                context="タイトル検索",
            )
            self.assertEqual(search_response.status_code, 200)
            search_payload = search_response.json()
            self.assertEqual(
                search_payload["pagination"]["total_items"],
                len(matching_releases),
            )
            _assert_source_url_order(
                [item["source_url"] for item in search_payload["items"]],
                [release.url for release in matching_releases[:50]],
                context="タイトル検索",
            )

        with Session(self.engine) as session:
            started_at = perf_counter()
            second_save_result = _save_and_commit_without_exposing_snapshot(
                session,
                self.snapshot.releases,
                fetched_at=self.snapshot.fetched_at,
                phase="再投入",
            )
            timings["duplicate_save"] = perf_counter() - started_at

            self.assertEqual(second_save_result.saved_count, 0)
            self.assertEqual(second_save_result.skipped_count, 34_421)
            self.assertEqual(_row_count(session), 34_421)

        print(
            json.dumps(
                {
                    "fetched_count": self.snapshot.fetched_count,
                    "initial_saved_count": first_save_result.saved_count,
                    "duplicate_skipped_count": second_save_result.skipped_count,
                    "database_total_count": 34_421,
                    "search_query": _SEARCH_QUERY,
                    "search_total_items": len(matching_releases),
                    "timings_seconds": {
                        name: round(seconds, 6)
                        for name, seconds in timings.items()
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )


def _row_count(session: Session) -> int:
    return int(session.scalar(text("select count(*) from press_releases")) or 0)


def _save_and_commit_without_exposing_snapshot(
    session: Session,
    releases: tuple[ScraperCliRelease, ...],
    *,
    fetched_at: datetime,
    phase: str,
) -> PressReleaseSaveResult:
    """失敗時にスナップショットの値を表示せず保存する"""

    try:
        result = save_press_releases(
            session,
            releases,
            fetched_at=fetched_at,
        )
        session.commit()
    except Exception as error:
        raise AssertionError(
            f"{phase}に失敗しました: {type(error).__name__}"
        ) from None

    return result


def _assert_source_url_order(
    actual: list[str],
    expected: list[str],
    *,
    context: str,
) -> None:
    """不一致時にURLを表示せず順序を検証する"""

    if actual != expected:
        raise AssertionError(
            f"{context}のsource_url順が一致しません。"
        )


def _assert_item_count(
    items: list[object],
    expected_count: int,
    *,
    context: str,
) -> None:
    """不一致時にitem本文を表示せず件数を検証する"""

    if len(items) != expected_count:
        raise AssertionError(
            f"{context}のitems件数が一致しません。"
        )


def _timed_get(
    client: TestClient,
    path: str,
    *,
    params: dict[str, object] | None = None,
    context: str,
):
    started_at = perf_counter()
    try:
        response = client.get(path, params=params)
    except Exception as error:
        raise AssertionError(
            f"{context}に失敗しました: {type(error).__name__}"
        ) from None
    return response, perf_counter() - started_at


if __name__ == "__main__":
    unittest.main()

from datetime import UTC, date, datetime
import unittest
from unittest.mock import Mock, patch

from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from integration_tests import test_real_snapshot as real_snapshot_test
from press_watch_api.commands.fetch_and_save_env_press import ScraperCliRelease
from press_watch_api.services.press_release_save import PressReleaseSaveResult


class RealSnapshotExecutionSafetyTest(unittest.TestCase):
    """実データ検証失敗時にスナップショット内容を表示しないこと"""

    def test_api_request_failure_does_not_expose_response_values(self) -> None:
        response_value = "snapshot-secret-response-value"
        client = Mock()
        client.get.side_effect = RuntimeError(
            f"response validation failed: {response_value}"
        )

        with self.assertRaises(AssertionError) as raised:
            real_snapshot_test._timed_get(
                client,
                "/press-releases",
                context="先頭ページ取得",
            )

        message = str(raised.exception)
        self.assertEqual(
            message,
            "先頭ページ取得に失敗しました: RuntimeError",
        )
        self.assertNotIn(response_value, message)
        self.assertTrue(raised.exception.__suppress_context__)

    def test_item_count_failure_does_not_expose_items(self) -> None:
        assert_item_count = getattr(
            real_snapshot_test,
            "_assert_item_count",
            None,
        )
        if assert_item_count is None:
            self.fail("安全なitem件数比較ヘルパーが未実装です。")

        item_value = "snapshot-secret-item-value"

        with self.assertRaises(AssertionError) as raised:
            assert_item_count(
                [{"title": item_value}],
                0,
                context="最終ページ超過",
            )

        message = str(raised.exception)
        self.assertEqual(
            message,
            "最終ページ超過のitems件数が一致しません。",
        )
        self.assertNotIn(item_value, message)

    def test_save_failure_does_not_expose_snapshot_values(self) -> None:
        save_and_commit = getattr(
            real_snapshot_test,
            "_save_and_commit_without_exposing_snapshot",
            None,
        )
        if save_and_commit is None:
            self.fail("安全な保存ヘルパーが未実装です。")

        title = "snapshot-secret-title"
        source_url = "https://example.test/snapshot-secret-url"
        releases = (
            ScraperCliRelease(
                title=title,
                published_at=date(2026, 8, 29),
                url=source_url,
                source_categories=("環境",),
            ),
        )
        session = Mock(spec=Session)
        error = StatementError(
            "insert failed",
            "insert into press_releases (title, source_url) values (:title, :source_url)",
            {"title": title, "source_url": source_url},
            RuntimeError("database rejected snapshot row"),
        )

        with patch.object(
            real_snapshot_test,
            "save_press_releases",
            side_effect=error,
        ):
            with self.assertRaises(AssertionError) as raised:
                save_and_commit(
                    session,
                    releases,
                    fetched_at=datetime(2026, 8, 29, tzinfo=UTC),
                    phase="初回投入",
                )

        message = str(raised.exception)
        self.assertEqual(message, "初回投入に失敗しました: StatementError")
        self.assertNotIn(title, message)
        self.assertNotIn(source_url, message)
        self.assertTrue(raised.exception.__suppress_context__)

    def test_successful_save_commits_and_returns_result(self) -> None:
        save_and_commit = getattr(
            real_snapshot_test,
            "_save_and_commit_without_exposing_snapshot",
            None,
        )
        if save_and_commit is None:
            self.fail("安全な保存ヘルパーが未実装です。")

        releases = (
            ScraperCliRelease(
                title="公開可能なテスト値",
                published_at=date(2026, 8, 29),
                url="https://example.test/release",
                source_categories=("環境",),
            ),
        )
        fetched_at = datetime(2026, 8, 29, tzinfo=UTC)
        session = Mock(spec=Session)
        expected = PressReleaseSaveResult(
            saved_press_releases=(),
            skipped_count=1,
        )

        with patch.object(
            real_snapshot_test,
            "save_press_releases",
            return_value=expected,
        ) as save:
            actual = save_and_commit(
                session,
                releases,
                fetched_at=fetched_at,
                phase="再投入",
            )

        self.assertIs(actual, expected)
        save.assert_called_once_with(
            session,
            releases,
            fetched_at=fetched_at,
        )
        session.commit.assert_called_once_with()

    def test_source_url_order_failure_does_not_expose_urls(self) -> None:
        assert_source_url_order = getattr(
            real_snapshot_test,
            "_assert_source_url_order",
            None,
        )
        if assert_source_url_order is None:
            self.fail("安全な順序比較ヘルパーが未実装です。")

        actual_url = "https://example.test/actual-secret-url"
        expected_url = "https://example.test/expected-secret-url"

        with self.assertRaises(AssertionError) as raised:
            assert_source_url_order(
                [actual_url],
                [expected_url],
                context="先頭ページ",
            )

        message = str(raised.exception)
        self.assertEqual(message, "先頭ページのsource_url順が一致しません。")
        self.assertNotIn(actual_url, message)
        self.assertNotIn(expected_url, message)


if __name__ == "__main__":
    unittest.main()

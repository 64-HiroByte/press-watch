from datetime import UTC, date, datetime
import unittest

from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from integration_tests.database import (
    get_current_migration_head,
    prepare_test_database,
)
from press_watch_api.repositories.press_release import (
    count_press_releases,
    create_press_release,
    list_press_releases,
)
from press_watch_api.schemas.press_release import PressReleaseCreate


class PostgreSQLFoundationIntegrationTest(unittest.TestCase):
    """PostgreSQL 17と現行Alembic migrationのDB統合テスト"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = prepare_test_database()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.session = Session(bind=self.connection)
        row_count = self.connection.scalar(
            text("select count(*) from press_releases")
        )
        self.assertEqual(row_count, 0)

    def tearDown(self) -> None:
        self.session.close()
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()

    def test_migrations_create_current_postgresql_schema(self) -> None:
        """空DBから現行headとpress_releasesスキーマを作成できること"""

        inspector = inspect(self.connection)
        self.assertEqual(
            set(inspector.get_table_names(schema="public")),
            {"alembic_version", "press_releases"},
        )
        self.assertEqual(
            self.connection.scalar(
                text("select version_num from alembic_version")
            ),
            get_current_migration_head(),
        )
        server_version_num = int(
            self.connection.scalar(text("show server_version_num"))
        )
        self.assertEqual(server_version_num // 10_000, 17)

        columns = {
            column["name"]: column
            for column in inspector.get_columns("press_releases", schema="public")
        }
        self.assertEqual(
            set(columns),
            {
                "id",
                "title",
                "source_url",
                "published_at",
                "source_categories",
                "fetched_at",
                "created_at",
                "updated_at",
            },
        )
        self.assertIsInstance(columns["source_categories"]["type"], ARRAY)
        self.assertTrue(columns["source_categories"]["nullable"])

        unique_constraints = inspector.get_unique_constraints(
            "press_releases",
            schema="public",
        )
        self.assertTrue(
            any(
                constraint["name"] == "uq_press_releases_source_url"
                and constraint["column_names"] == ["source_url"]
                for constraint in unique_constraints
            )
        )
        indexes = inspector.get_indexes("press_releases", schema="public")
        self.assertTrue(
            any(
                index["name"] == "ix_press_releases_published_at"
                and index["column_names"] == ["published_at"]
                and not index["unique"]
                for index in indexes
            )
        )

    def test_repository_executes_array_round_trip_and_literal_ilike(self) -> None:
        """配列型とILIKEの文字列エスケープが実DBで機能すること"""

        create_press_release(
            self.session,
            _press_release_create(
                title="Climate 50%_/ report",
                source_url="https://example.test/press/1",
                source_categories=["総合政策", "水環境"],
            ),
        )
        create_press_release(
            self.session,
            _press_release_create(
                title="Climate 500X/ report",
                source_url="https://example.test/press/2",
                source_categories=None,
            ),
        )
        self.session.expire_all()

        self.assertEqual(
            count_press_releases(
                self.session,
                title_query="climate 50%_/",
            ),
            1,
        )
        matches = list_press_releases(
            self.session,
            limit=20,
            offset=0,
            title_query="climate 50%_/",
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].title, "Climate 50%_/ report")
        self.assertEqual(matches[0].source_categories, ["総合政策", "水環境"])

    def test_source_url_unique_constraint_is_enforced(self) -> None:
        """source_urlの重複を実DBの一意制約が拒否すること"""

        source_url = "https://example.test/press/duplicate"
        create_press_release(
            self.session,
            _press_release_create(source_url=source_url),
        )

        with self.assertRaises(IntegrityError):
            create_press_release(
                self.session,
                _press_release_create(source_url=source_url),
            )


class PostgreSQLMigrationCycleIntegrationTest(unittest.TestCase):
    """適用済みmigrationをbaseから再適用する統合テスト"""

    def test_reapplying_migrations_resets_database_to_current_head(self) -> None:
        """既存データを消去して空の現行headへ再構築できること"""

        initial_engine = prepare_test_database()
        try:
            with Session(initial_engine) as session:
                create_press_release(
                    session,
                    _press_release_create(
                        source_url="https://example.test/press/migration-cycle"
                    ),
                )
                session.commit()
        finally:
            initial_engine.dispose()

        rebuilt_engine = prepare_test_database()
        try:
            with rebuilt_engine.connect() as connection:
                self.assertEqual(
                    connection.scalar(
                        text("select count(*) from press_releases")
                    ),
                    0,
                )
                self.assertEqual(
                    connection.scalar(
                        text("select version_num from alembic_version")
                    ),
                    get_current_migration_head(),
                )
        finally:
            rebuilt_engine.dispose()


def _press_release_create(
    *,
    title: str = "報道発表",
    source_url: str,
    source_categories: list[str] | None = None,
) -> PressReleaseCreate:
    """DB統合テスト用の報道発表保存DTOを生成

    Args:
        title: 報道発表タイトル
        source_url: 一意制約を確認できるテスト用URL
        source_categories: PostgreSQL配列へ保存する取得元カテゴリ

    Returns:
        repositoryへ渡す報道発表保存DTO
    """

    return PressReleaseCreate(
        title=title,
        source_url=source_url,
        published_at=date(2026, 8, 27),
        source_categories=source_categories,
        fetched_at=datetime(2026, 8, 27, 10, 0, tzinfo=UTC),
    )


if __name__ == "__main__":
    unittest.main()

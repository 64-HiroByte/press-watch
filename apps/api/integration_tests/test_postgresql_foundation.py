from datetime import UTC, date, datetime
import json
import unittest

from alembic import command
from sqlalchemy import BigInteger, Text, event, inspect, text
from sqlalchemy.dialects.postgresql import ARRAY, INTEGER
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from integration_tests import database as test_database
from integration_tests.database import (
    get_current_migration_head,
    prepare_test_database,
)
from integration_tests.sql_statement_counter import count_save_sql_statements
from press_watch_api.commands.fetch_and_save_env_press import ScraperCliRelease
from press_watch_api.repositories.press_release import (
    count_press_releases,
    create_press_release,
    list_press_releases,
)
from press_watch_api.schemas.press_release import PressReleaseCreate
from press_watch_api.services.press_release_save import save_press_releases


_PREVIOUS_MIGRATION_HEAD = "9f2c7a4e1d63"


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
        """空DBから現行headの5テーブルを作成できること"""

        inspector = inspect(self.connection)
        self.assertEqual(
            set(inspector.get_table_names(schema="public")),
            {
                "alembic_version",
                "fixed_categories",
                "fixed_category_keywords",
                "press_releases",
                "press_release_fixed_categories",
            },
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

    def test_fixed_category_schema_matches_contract(self) -> None:
        """固定カテゴリ3テーブルの列と制約がモデル契約に一致すること"""

        inspector = inspect(self.connection)
        fixed_category_columns = {
            column["name"]: column
            for column in inspector.get_columns(
                "fixed_categories",
                schema="public",
            )
        }
        self.assertEqual(
            set(fixed_category_columns),
            {"id", "slug", "name", "display_order"},
        )
        self.assertIsInstance(fixed_category_columns["id"]["type"], BigInteger)
        self.assertIsInstance(fixed_category_columns["slug"]["type"], Text)
        self.assertIsInstance(fixed_category_columns["name"]["type"], Text)
        self.assertIsInstance(
            fixed_category_columns["display_order"]["type"],
            INTEGER,
        )
        self.assertTrue(
            all(
                not column["nullable"]
                for column in fixed_category_columns.values()
            )
        )
        self.assertEqual(
            inspector.get_pk_constraint(
                "fixed_categories",
                schema="public",
            )["constrained_columns"],
            ["id"],
        )

        unique_constraints = {
            constraint["name"]: constraint["column_names"]
            for constraint in inspector.get_unique_constraints(
                "fixed_categories",
                schema="public",
            )
        }
        self.assertEqual(
            unique_constraints,
            {
                "uq_fixed_categories_slug": ["slug"],
                "uq_fixed_categories_name": ["name"],
                "uq_fixed_categories_display_order": ["display_order"],
            },
        )
        check_constraints = {
            constraint["name"]: constraint["sqltext"]
            for constraint in inspector.get_check_constraints(
                "fixed_categories",
                schema="public",
            )
        }
        self.assertIn(
            "display_order > 0",
            check_constraints["ck_fixed_categories_display_order_positive"],
        )

        keyword_columns = {
            column["name"]: column
            for column in inspector.get_columns(
                "fixed_category_keywords",
                schema="public",
            )
        }
        self.assertEqual(
            set(keyword_columns),
            {"fixed_category_id", "keyword"},
        )
        self.assertIsInstance(
            keyword_columns["fixed_category_id"]["type"],
            BigInteger,
        )
        self.assertIsInstance(keyword_columns["keyword"]["type"], Text)
        self.assertTrue(
            all(not column["nullable"] for column in keyword_columns.values())
        )
        self.assertEqual(
            inspector.get_pk_constraint(
                "fixed_category_keywords",
                schema="public",
            )["constrained_columns"],
            ["fixed_category_id", "keyword"],
        )
        keyword_foreign_key = inspector.get_foreign_keys(
            "fixed_category_keywords",
            schema="public",
        )[0]
        self.assertEqual(
            (
                keyword_foreign_key["constrained_columns"],
                keyword_foreign_key["referred_table"],
                keyword_foreign_key["referred_columns"],
                keyword_foreign_key["options"].get("ondelete"),
            ),
            (["fixed_category_id"], "fixed_categories", ["id"], "CASCADE"),
        )

        assignment_columns = {
            column["name"]: column
            for column in inspector.get_columns(
                "press_release_fixed_categories",
                schema="public",
            )
        }
        self.assertEqual(
            set(assignment_columns),
            {"press_release_id", "fixed_category_id"},
        )
        self.assertTrue(
            all(
                isinstance(column["type"], BigInteger)
                and not column["nullable"]
                for column in assignment_columns.values()
            )
        )
        self.assertEqual(
            inspector.get_pk_constraint(
                "press_release_fixed_categories",
                schema="public",
            )["constrained_columns"],
            ["press_release_id", "fixed_category_id"],
        )
        assignment_foreign_keys = {
            foreign_key["constrained_columns"][0]: (
                foreign_key["referred_table"],
                foreign_key["referred_columns"],
                foreign_key["options"].get("ondelete"),
            )
            for foreign_key in inspector.get_foreign_keys(
                "press_release_fixed_categories",
                schema="public",
            )
        }
        self.assertEqual(
            assignment_foreign_keys,
            {
                "press_release_id": ("press_releases", ["id"], "CASCADE"),
                "fixed_category_id": ("fixed_categories", ["id"], "RESTRICT"),
            },
        )
        assignment_indexes = {
            index["name"]: (index["column_names"], index["unique"])
            for index in inspector.get_indexes(
                "press_release_fixed_categories",
                schema="public",
            )
        }
        self.assertEqual(
            assignment_indexes,
            {
                "ix_press_release_fixed_categories_fixed_category_id": (
                    ["fixed_category_id"],
                    False,
                )
            },
        )

    def test_fixed_category_representative_constraints_are_enforced(self) -> None:
        """表示順、一意制約、複合主キーの代表的な違反を拒否すること"""

        savepoint = self.connection.begin_nested()
        try:
            with self.assertRaises(IntegrityError):
                self.connection.execute(
                    text(
                        "insert into fixed_categories "
                        "(slug, name, display_order) "
                        "values (:slug, :name, :display_order)"
                    ),
                    {
                        "slug": "invalid-order",
                        "name": "不正表示順",
                        "display_order": 0,
                    },
                )
        finally:
            if savepoint.is_active:
                savepoint.rollback()

        fixed_category_id = self.connection.scalar(
            text(
                "insert into fixed_categories (slug, name, display_order) "
                "values (:slug, :name, :display_order) returning id"
            ),
            {"slug": "climate", "name": "気候", "display_order": 1},
        )
        duplicate_statements = [
            (
                "slug unique",
                text(
                    "insert into fixed_categories (slug, name, display_order) "
                    "values (:slug, :name, :display_order)"
                ),
                {"slug": "climate", "name": "気候政策", "display_order": 2},
            ),
            (
                "keyword composite primary key",
                text(
                    "insert into fixed_category_keywords "
                    "(fixed_category_id, keyword) values (:category_id, :keyword)"
                ),
                {"category_id": fixed_category_id, "keyword": "気候変動"},
            ),
        ]
        self.connection.execute(
            duplicate_statements[1][1],
            duplicate_statements[1][2],
        )
        for test_name, statement, parameters in duplicate_statements:
            with self.subTest(test_name=test_name):
                savepoint = self.connection.begin_nested()
                try:
                    with self.assertRaises(IntegrityError):
                        self.connection.execute(statement, parameters)
                finally:
                    if savepoint.is_active:
                        savepoint.rollback()

    def test_fixed_category_delete_rules_support_multiple_categories(
        self,
    ) -> None:
        """複数カテゴリ付与と3種類の削除規則が機能すること"""

        press_release_id = self.connection.scalar(
            text(
                "insert into press_releases "
                "(title, source_url, published_at, fetched_at) "
                "values (:title, :source_url, :published_at, :fetched_at) "
                "returning id"
            ),
            {
                "title": "固定カテゴリ削除規則テスト",
                "source_url": "https://example.test/press/fixed-category-delete",
                "published_at": date(2026, 9, 2),
                "fetched_at": datetime(2026, 9, 2, 10, 0, tzinfo=UTC),
            },
        )
        category_ids = [
            self.connection.scalar(
                text(
                    "insert into fixed_categories (slug, name, display_order) "
                    "values (:slug, :name, :display_order) returning id"
                ),
                {"slug": slug, "name": name, "display_order": display_order},
            )
            for slug, name, display_order in (
                ("climate", "気候", 1),
                ("water", "水環境", 2),
            )
        ]
        self.connection.execute(
            text(
                "insert into fixed_category_keywords "
                "(fixed_category_id, keyword) values (:category_id, :keyword)"
            ),
            {"category_id": category_ids[1], "keyword": "水質"},
        )
        for category_id in category_ids:
            self.connection.execute(
                text(
                    "insert into press_release_fixed_categories "
                    "(press_release_id, fixed_category_id) "
                    "values (:press_release_id, :fixed_category_id)"
                ),
                {
                    "press_release_id": press_release_id,
                    "fixed_category_id": category_id,
                },
            )
        self.assertEqual(
            self.connection.scalar(
                text(
                    "select count(*) from press_release_fixed_categories "
                    "where press_release_id = :press_release_id"
                ),
                {"press_release_id": press_release_id},
            ),
            2,
        )

        savepoint = self.connection.begin_nested()
        try:
            with self.assertRaises(IntegrityError):
                self.connection.execute(
                    text("delete from fixed_categories where id = :category_id"),
                    {"category_id": category_ids[0]},
                )
        finally:
            if savepoint.is_active:
                savepoint.rollback()

        self.connection.execute(
            text("delete from press_releases where id = :press_release_id"),
            {"press_release_id": press_release_id},
        )
        self.assertEqual(
            self.connection.scalar(
                text(
                    "select count(*) from press_release_fixed_categories "
                    "where press_release_id = :press_release_id"
                ),
                {"press_release_id": press_release_id},
            ),
            0,
        )
        self.connection.execute(
            text("delete from fixed_categories where id = :category_id"),
            {"category_id": category_ids[1]},
        )
        self.assertEqual(
            self.connection.scalar(
                text(
                    "select count(*) from fixed_category_keywords "
                    "where fixed_category_id = :category_id"
                ),
                {"category_id": category_ids[1]},
            ),
            0,
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

    def test_save_service_handles_database_and_input_duplicates(self) -> None:
        """DB既存と入力内重複をskipし保存結果を入力順で返すこと"""

        existing_url = "https://example.test/press/existing"
        first_new_url = "https://example.test/press/new-first"
        later_new_url = "https://example.test/press/new-later"
        create_press_release(
            self.session,
            _press_release_create(source_url=existing_url),
        )
        releases = (
            _scraper_release(1, source_url=first_new_url),
            _scraper_release(2, source_url=existing_url),
            _scraper_release(3, source_url=first_new_url),
            _scraper_release(4, source_url=later_new_url),
        )

        result = save_press_releases(self.session, releases)

        self.assertEqual(result.saved_count, 2)
        self.assertEqual(result.skipped_count, 2)
        self.assertTrue(
            [release.source_url for release in result.saved_press_releases]
            == [first_new_url, later_new_url],
            "保存結果のsource_url順が一致しません。",
        )
        self.assertEqual(
            self.connection.scalar(
                text("select count(*) from press_releases")
            ),
            3,
        )

    def test_bulk_save_preserves_all_five_values_in_database(self) -> None:
        """一括INSERTの5列をDBから読み直し、カテゴリのNULLも維持すること"""

        releases = (
            ScraperCliRelease(
                title="カテゴリありの報道発表",
                published_at=date(2026, 8, 27),
                url="https://example.test/press/bulk-values-first",
                source_categories=("総合政策", "水環境"),
            ),
            ScraperCliRelease(
                title="カテゴリなしの報道発表",
                published_at=date(2026, 8, 28),
                url="https://example.test/press/bulk-values-second",
                source_categories=(),
            ),
        )
        fetched_at = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)

        result = save_press_releases(
            self.session, releases, fetched_at=fetched_at,
        )

        self.assertEqual(result.saved_count, 2)
        self.assertEqual(result.skipped_count, 0)
        rows = self.connection.execute(
            text(
                "select title, source_url, published_at, source_categories, fetched_at "
                "from press_releases"
            )
        ).mappings().all()
        self.assertEqual(len(rows), 2)
        rows_by_url = {row["source_url"]: row for row in rows}
        for index, release in enumerate(releases):
            row = rows_by_url.get(release.url)
            if row is None:
                self.fail("一括保存した行がDBに見つかりません。")
            expected_values = {
                "title": release.title,
                "source_url": release.url,
                "published_at": release.published_at,
                "source_categories": list(release.source_categories) or None,
                "fetched_at": fetched_at,
            }
            for column_name, expected_value in expected_values.items():
                self.assertTrue(
                    row[column_name] == expected_value,
                    f"DBの{index}行目の{column_name}が入力と一致しません。",
                )

    def test_save_service_uses_two_inserts_for_1001_releases(
        self,
    ) -> None:
        """1,001件の初回と再投入を2回のINSERTだけで処理すること"""

        releases = tuple(_scraper_release(index) for index in range(1_001))

        with count_save_sql_statements(self.engine) as initial_counts:
            initial_result = save_press_releases(self.session, releases)

        self.assertEqual(initial_result.saved_count, 1_001)
        self.assertEqual(initial_result.skipped_count, 0)
        self.assertTrue(
            all(
                actual.source_url == expected.url
                for actual, expected in zip(
                    initial_result.saved_press_releases,
                    releases,
                    strict=True,
                )
            ),
            "初回保存結果のsource_url順が一致しません。",
        )
        first_saved = initial_result.saved_press_releases[0]
        self.assertTrue(inspect(first_saved).persistent)
        self.assertIsNotNone(first_saved.created_at)
        self.assertIsNotNone(first_saved.updated_at)
        self.session.commit()

        with count_save_sql_statements(self.engine) as duplicate_counts:
            duplicate_result = save_press_releases(self.session, releases)

        self.assertEqual(duplicate_result.saved_count, 0)
        self.assertEqual(duplicate_result.skipped_count, 1_001)
        self.session.commit()
        self.assertEqual(
            self.connection.scalar(
                text("select count(*) from press_releases")
            ),
            1_001,
        )
        print(
            json.dumps(
                {
                    "sql_statement_counts_1001": {
                        "initial": initial_counts.to_json_dict(),
                        "duplicate": duplicate_counts.to_json_dict(),
                    }
                },
                sort_keys=True,
            ),
            flush=True,
        )

        self.assertEqual(initial_counts.select, 0)
        self.assertEqual(initial_counts.insert, 2)
        self.assertEqual(duplicate_counts.select, 0)
        self.assertEqual(duplicate_counts.insert, 2)

    def test_caller_rollback_removes_first_batch_after_second_insert_fails(
        self,
    ) -> None:
        """2回目のINSERT失敗後にcaller rollbackで全件を取り消せること"""

        releases = tuple(_scraper_release(index) for index in range(1_001))
        insert_count = 0

        def fail_before_second_insert(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            nonlocal insert_count
            if statement.lstrip().upper().startswith("INSERT"):
                insert_count += 1
                if insert_count == 2:
                    raise RuntimeError("fixed second insert failure")

        try:
            event.listen(
                self.engine,
                "before_cursor_execute",
                fail_before_second_insert,
            )
            try:
                # 外側のtransactionに参加させず、誤った中間commitもDBへ反映させる。
                with Session(self.engine) as save_session:
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "fixed second insert failure",
                    ):
                        try:
                            save_press_releases(save_session, releases)
                        except RuntimeError:
                            save_session.rollback()
                            raise
                    # 自動closeの取消に頼らず、明示rollbackの直後に確認する。
                    self.assertFalse(save_session.in_transaction())
                    self.assertEqual(
                        save_session.scalar(
                            text("select count(*) from press_releases")
                        ),
                        0,
                    )
            finally:
                event.remove(
                    self.engine,
                    "before_cursor_execute",
                    fail_before_second_insert,
                )

            self.assertEqual(insert_count, 2)
            with self.engine.connect() as verification_connection:
                row_count = verification_connection.scalar(
                    text("select count(*) from press_releases")
                )
            self.assertEqual(row_count, 0)
        finally:
            # 回帰で中間commitされた場合も、専用テストDBへ行を残さない。
            with self.engine.begin() as cleanup_connection:
                cleanup_connection.execute(text("delete from press_releases"))


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

    def test_downgrade_to_previous_head_preserves_press_release(self) -> None:
        """旧headへのdowngradeと再upgradeで既存報道発表を維持すること"""

        source_url = "https://example.test/press/partial-migration-cycle"
        initial_engine = prepare_test_database()
        database_url = initial_engine.url
        try:
            with Session(initial_engine) as session:
                create_press_release(
                    session,
                    _press_release_create(source_url=source_url),
                )
                session.commit()
        finally:
            initial_engine.dispose()

        try:
            test_database._run_migration_command(
                database_url,
                command.downgrade,
                _PREVIOUS_MIGRATION_HEAD,
            )
            downgraded_engine = test_database._create_test_engine(database_url)
            try:
                with downgraded_engine.connect() as connection:
                    self.assertEqual(
                        connection.scalar(
                            text("select version_num from alembic_version")
                        ),
                        _PREVIOUS_MIGRATION_HEAD,
                    )
                    self.assertEqual(
                        set(inspect(connection).get_table_names(schema="public")),
                        {"alembic_version", "press_releases"},
                    )
                    self.assertEqual(
                        connection.scalar(
                            text(
                                "select count(*) from press_releases "
                                "where source_url = :source_url"
                            ),
                            {"source_url": source_url},
                        ),
                        1,
                    )
            finally:
                downgraded_engine.dispose()
        finally:
            test_database._run_migration_command(
                database_url,
                command.upgrade,
                "head",
            )

        upgraded_engine = test_database._create_test_engine(database_url)
        try:
            with upgraded_engine.connect() as connection:
                self.assertEqual(
                    connection.scalar(
                        text("select version_num from alembic_version")
                    ),
                    get_current_migration_head(),
                )
                self.assertEqual(
                    set(inspect(connection).get_table_names(schema="public")),
                    {
                        "alembic_version",
                        "fixed_categories",
                        "fixed_category_keywords",
                        "press_releases",
                        "press_release_fixed_categories",
                    },
                )
                self.assertEqual(
                    connection.scalar(
                        text(
                            "select count(*) from press_releases "
                            "where source_url = :source_url"
                        ),
                        {"source_url": source_url},
                    ),
                    1,
                )
        finally:
            upgraded_engine.dispose()


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


def _scraper_release(
    index: int,
    *,
    source_url: str | None = None,
) -> ScraperCliRelease:
    """一括保存統合テスト用の報道発表を生成"""

    return ScraperCliRelease(
        title=f"報道発表{index}",
        published_at=date(2026, 8, 27),
        url=source_url or f"https://example.test/press/{index}",
        source_categories=("総合政策",),
    )


if __name__ == "__main__":
    unittest.main()

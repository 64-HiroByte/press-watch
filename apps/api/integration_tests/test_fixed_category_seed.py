from datetime import UTC, date, datetime
import io
import json
import unittest

from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from integration_tests.database import prepare_test_database
from press_watch_api.commands.seed_fixed_categories import main
from press_watch_api.models.fixed_category import (
    FixedCategory,
    FixedCategoryKeyword,
    PressReleaseFixedCategory,
)
from press_watch_api.models.press_release import PressRelease
from press_watch_api.services.fixed_category_seed import load_fixed_category_seed


_DATA_MODELS = (
    PressReleaseFixedCategory, FixedCategoryKeyword, FixedCategory, PressRelease,
)


class FixedCategorySeedIntegrationTest(unittest.TestCase):
    """安全確認済みPostgreSQLでCLIの確定結果と取消結果を確認"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = prepare_test_database()
        cls.addClassCleanup(cls.engine.dispose)

    def setUp(self) -> None:
        self.sessions: list[Session] = []
        # setUpやfixture作成の途中で失敗しても、生成済みSessionとテストデータを片付ける。
        self.addCleanup(self._clear_test_data)
        self.data = load_fixed_category_seed()

    def _session(self) -> Session:
        # 外側のtransactionを使わず、CLIのcommitを実際のDBへ反映する。
        session = Session(bind=self.engine, autoflush=False)
        self.sessions.append(session)
        return session

    def _clear_test_data(self) -> None:
        """安全確認済みの専用DBで、参照元から順にテスト対象テーブルの全行を削除"""

        for session in self.sessions:
            session.close()
        with self.engine.begin() as connection:
            for model in _DATA_MODELS:
                connection.execute(delete(model))

    def _run(self) -> tuple[int, str, str]:
        """CLI自身のcommit・rollbackを通し、終了コード・stdout・stderrを返す"""

        stdout, stderr = io.StringIO(), io.StringIO()
        code = main([], session_factory=self._session, stdout=stdout, stderr=stderr)
        return code, stdout.getvalue(), stderr.getvalue()

    def _snapshot(self) -> dict[str, tuple[tuple[object, ...], ...]]:
        """別接続から確定済みの全列を主キー順で取得し、後始末前のDB状態を比較可能にする"""

        with self.engine.connect() as connection:
            return {
                model.__tablename__: tuple(
                    tuple(row) for row in connection.execute(
                        select(model.__table__).order_by(*model.__table__.primary_key.columns)
                    )
                )
                for model in _DATA_MODELS
            }

    def _create_existing_data(self, *, keywords: bool = True) -> int:
        """seedで維持すべき既存カテゴリ・報道発表原本・分類結果をcommitして準備

        Args:
            keywords: Falseならキーワードを未登録とし、不足補完や登録失敗の検証に使用

        Returns:
            表示順とは異なる値に設定した既存カテゴリID
        """

        definition = self.data.categories[0]
        with Session(self.engine) as session:
            category = FixedCategory(
                id=1009, slug=definition.slug, name=definition.name,
                display_order=definition.display_order,
            )
            release = PressRelease(
                title="原本を保持するためのテスト", source_url="https://example.test/seed/original",
                published_at=date(2026, 1, 1), source_categories=["取得元カテゴリ"],
                fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
            )
            session.add_all([category, release])
            session.flush()
            session.add(PressReleaseFixedCategory(
                press_release_id=release.id, fixed_category_id=category.id,
            ))
            if keywords:
                session.add_all([
                    FixedCategoryKeyword(fixed_category_id=category.id, keyword=keyword)
                    for slug, keyword in self.data.keywords if slug == definition.slug
                ])
            session.commit()
        return 1009

    def _assert_matches_csv(self) -> None:
        """CLIとは別のSessionから、確定済みのカテゴリ・キーワードがCSVと一致することを確認"""

        with Session(self.engine) as session:
            categories = session.scalars(select(FixedCategory)).all()
            self.assertEqual(
                {(item.slug, item.name, item.display_order) for item in categories},
                {(item.slug, item.name, item.display_order) for item in self.data.categories},
            )
            slugs = {item.id: item.slug for item in categories}
            self.assertEqual(
                {(slugs[item.fixed_category_id], item.keyword)
                 for item in session.scalars(select(FixedCategoryKeyword))},
                set(self.data.keywords),
            )

    def test_initial_seed_commits_both_tables(self) -> None:
        code, stdout, stderr = self._run()
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout), {"categories_added": 10, "keywords_added": 57})
        self._assert_matches_csv()

    def test_repeated_seed_has_no_insert_update_or_delete(self) -> None:
        """結果の行比較に加え、SQLも監視して同じ値を書き直す処理がないことを確認"""

        self._create_existing_data()
        self.assertEqual(self._run()[0], 0)
        before = self._snapshot()
        writes: list[str] = []

        def count_writes(_conn, _cursor, statement, _params, _context, _many) -> None:
            operation = statement.lstrip().split(None, 1)[0].upper()
            if operation in {"INSERT", "UPDATE", "DELETE"}:
                writes.append(operation)

        event.listen(self.engine, "before_cursor_execute", count_writes)
        try:
            code, stdout, stderr = self._run()
        finally:
            event.remove(self.engine, "before_cursor_execute", count_writes)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout), {"categories_added": 0, "keywords_added": 0})
        self.assertEqual(writes, [])
        self.assertEqual(self._snapshot(), before)

    def test_partial_seed_preserves_ids_original_data_and_classifications(self) -> None:
        existing_id = self._create_existing_data()
        before = self._snapshot()
        code, stdout, stderr = self._run()
        self.assertEqual((code, stderr), (0, ""))
        existing_keyword_count = len(before["fixed_category_keywords"])
        self.assertEqual(json.loads(stdout), {
            "categories_added": 9, "keywords_added": 57 - existing_keyword_count,
        })
        self._assert_matches_csv()
        after = self._snapshot()
        for table in ("press_releases", "press_release_fixed_categories"):
            self.assertEqual(after[table], before[table])
        self.assertIn(before["fixed_categories"][0], after["fixed_categories"])
        self.assertEqual(before["fixed_categories"][0][0], existing_id)

    def test_adds_only_missing_keyword_rows(self) -> None:
        self._create_existing_data()
        self.assertEqual(self._run()[0], 0)
        with self.engine.begin() as connection:
            connection.execute(delete(FixedCategoryKeyword).where(
                FixedCategoryKeyword.fixed_category_id == 1009,
            ))
        before = self._snapshot()
        missing_count = 57 - len(before["fixed_category_keywords"])
        code, stdout, stderr = self._run()
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout), {"categories_added": 0, "keywords_added": missing_count})
        self._assert_matches_csv()
        after = self._snapshot()
        for table in ("fixed_categories", "press_releases", "press_release_fixed_categories"):
            self.assertEqual(after[table], before[table])

    def test_rejects_each_kind_of_conflict_without_changing_existing_rows(self) -> None:
        for conflict in ("name", "display_order", "extra_category", "extra_keyword"):
            with self.subTest(conflict=conflict):
                self._create_existing_data()
                with Session(self.engine) as session:
                    if conflict in {"name", "display_order"}:
                        category = session.get(FixedCategory, 1009)
                        if conflict == "name":
                            category.name = "既存の異なる表示名"
                        else:
                            category.display_order = 500
                    elif conflict == "extra_category":
                        session.add(FixedCategory(slug="extra", name="追加カテゴリ", display_order=500))
                    else:
                        session.add(FixedCategoryKeyword(fixed_category_id=1009, keyword="余分な語句"))
                    session.commit()
                before = self._snapshot()
                code, stdout, stderr = self._run()
                self.assertEqual((code, stdout), (1, ""))
                self.assertIn("database definitions differ", stderr)
                self.assertEqual(self._snapshot(), before)
                self._clear_test_data()

    def test_keyword_insert_failure_rolls_back_new_categories_and_preserves_existing_rows(self) -> None:
        """カテゴリのflush後にキーワードINSERTを失敗させ、先行した登録も取り消されることを確認"""

        self._create_existing_data(keywords=False)
        before = self._snapshot()
        category_inserts = 0
        keyword_inserts = 0

        def fail_keywords(_conn, _cursor, _statement, _params, context, _many) -> None:
            nonlocal category_inserts, keyword_inserts
            if not context.isinsert:
                return
            table_name = context.compiled.statement.table.name
            if table_name == "fixed_categories":
                category_inserts += 1
            if table_name == "fixed_category_keywords":
                keyword_inserts += 1
                raise RuntimeError("PRIVATE_DATABASE_FAILURE")

        event.listen(self.engine, "before_cursor_execute", fail_keywords)
        try:
            code, stdout, stderr = self._run()
        finally:
            event.remove(self.engine, "before_cursor_execute", fail_keywords)
        self.assertGreater(category_inserts, 0)
        self.assertEqual(keyword_inserts, 1)
        self.assertEqual((code, stdout), (1, ""))
        self.assertNotIn("PRIVATE_DATABASE_FAILURE", stderr)
        self.assertTrue(all(not session.in_transaction() for session in self.sessions))
        self.assertEqual(self._snapshot(), before)


if __name__ == "__main__":
    unittest.main()

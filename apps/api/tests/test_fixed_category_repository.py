import unittest
from unittest.mock import Mock

from sqlalchemy.orm import Session
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError

from press_watch_api.models.fixed_category import (
    FixedCategory,
    FixedCategoryKeyword,
)
from press_watch_api.repositories import fixed_category as repository


class FixedCategoryRepositoryTest(unittest.TestCase):
    """MockのSessionでモデル生成・flushの呼出しを確認（実SQLは統合テストで検証）"""

    def setUp(self) -> None:
        self.session = Mock(spec=Session)

    def tearDown(self) -> None:
        """全ケースで、repositoryがトランザクションの確定・取消やSession終了をしないことを確認"""

        self.session.commit.assert_not_called()
        self.session.rollback.assert_not_called()
        self.session.close.assert_not_called()

    def test_reads_existing_categories_and_keywords(self) -> None:
        category = FixedCategory(
            id=51, slug="air", name="Air", display_order=10
        )
        keyword = FixedCategoryKeyword(fixed_category_id=51, keyword="PCB")
        self.session.scalars.side_effect = [(category,), (keyword,)]
        self.assertEqual(
            repository.list_fixed_categories(self.session), (category,)
        )
        self.assertEqual(
            repository.list_fixed_category_keywords(self.session), (keyword,)
        )
        self.session.add_all.assert_not_called()
        self.session.flush.assert_not_called()

    def test_returns_categories_after_flush_assigns_ids(self) -> None:
        def assign_ids() -> None:
            """flushによる採番を模擬し、返却時点のID確認に使用"""

            for index, category in enumerate(
                self.session.add_all.call_args.args[0], start=51
            ):
                category.id = index

        self.session.flush.side_effect = assign_ids
        categories = repository.create_fixed_categories(
            self.session,
            [("air", "Air", 10), ("soil", "Soil", 30)],
        )
        self.assertEqual(len(categories), 2)
        self.assertEqual(
            [
                (
                    category.id,
                    category.slug,
                    category.name,
                    category.display_order,
                )
                for category in categories
            ],
            [(51, "air", "Air", 10), (52, "soil", "Soil", 30)],
        )
        self.session.flush.assert_called_once_with()

    def test_adds_keywords_with_supplied_ids_and_flushes(self) -> None:
        repository.create_fixed_category_keywords(
            self.session, [(51, "PCB"), (92, "PCB")]
        )
        self.session.add_all.assert_called_once()
        self.assertEqual(
            [
                (item.fixed_category_id, item.keyword)
                for item in self.session.add_all.call_args.args[0]
            ],
            [(51, "PCB"), (92, "PCB")],
        )
        self.session.flush.assert_called_once_with()

    def test_empty_additions_do_not_flush_unrelated_pending_objects(
        self,
    ) -> None:
        self.assertEqual(
            repository.create_fixed_categories(self.session, []), ()
        )
        repository.create_fixed_category_keywords(self.session, [])
        self.session.add_all.assert_not_called()
        self.session.flush.assert_not_called()

    def test_bulk_inserts_classifications_without_skipping_conflicts(
        self,
    ) -> None:
        repository.create_press_release_fixed_categories(
            self.session, [(1009, 51), (1009, 92)]
        )
        self.session.execute.assert_called_once()
        compiled = self.session.execute.call_args.args[0].compile(
            dialect=postgresql.dialect()
        )
        self.assertEqual(
            compiled.params,
            {
                "press_release_id_m0": 1009,
                "fixed_category_id_m0": 51,
                "press_release_id_m1": 1009,
                "fixed_category_id_m1": 92,
            },
        )
        self.assertNotIn("ON CONFLICT", str(compiled))

    def test_splits_classification_rows_at_1000(self) -> None:
        repository.create_press_release_fixed_categories(
            self.session, [(index, 51) for index in range(1_001)]
        )
        self.assertEqual(self.session.execute.call_count, 2)
        self.assertEqual(
            [
                len(call.args[0].compile(dialect=postgresql.dialect()).params)
                for call in self.session.execute.call_args_list
            ],
            [2_000, 2],
        )

    def test_empty_classifications_do_not_execute_sql(self) -> None:
        repository.create_press_release_fixed_categories(self.session, [])
        self.session.execute.assert_not_called()
        self.session.flush.assert_not_called()

    def test_classification_insert_failure_propagates(self) -> None:
        error = SQLAlchemyError("fixed insert failure")
        self.session.execute.side_effect = error
        with self.assertRaises(SQLAlchemyError) as caught:
            repository.create_press_release_fixed_categories(
                self.session, [(1009, 51)]
            )
        self.assertIs(caught.exception, error)

    def test_deletes_only_requested_release_classifications(self) -> None:
        """削除条件が渡した報道発表IDだけに限定されることを確認"""

        repository.delete_press_release_fixed_categories(
            self.session, [1009, 2027]
        )
        self.session.execute.assert_called_once()
        statement = self.session.execute.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        self.assertEqual(
            statement.table.name, "press_release_fixed_categories"
        )
        self.assertTrue(statement.is_delete)
        self.assertIn(
            "WHERE press_release_fixed_categories.press_release_id IN",
            str(compiled),
        )
        self.assertEqual(list(compiled.params.values()), [[1009, 2027]])

    def test_empty_deletion_does_not_execute_sql(self) -> None:
        """空のID指定では、無条件DELETEを発行しないことを確認"""

        repository.delete_press_release_fixed_categories(self.session, [])
        self.session.execute.assert_not_called()

    def test_deletion_failure_propagates(self) -> None:
        """DELETE例外を握りつぶさず、全体rollbackを担当する呼び出し元へ伝播"""

        error = SQLAlchemyError("fixed delete failure")
        self.session.execute.side_effect = error
        with self.assertRaises(SQLAlchemyError) as caught:
            repository.delete_press_release_fixed_categories(
                self.session, [1009]
            )
        self.assertIs(caught.exception, error)


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import Mock

from sqlalchemy.orm import Session

from press_watch_api.models.fixed_category import FixedCategory, FixedCategoryKeyword
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
        category = FixedCategory(id=51, slug="air", name="Air", display_order=10)
        keyword = FixedCategoryKeyword(fixed_category_id=51, keyword="PCB")
        self.session.scalars.side_effect = [(category,), (keyword,)]
        self.assertEqual(repository.list_fixed_categories(self.session), (category,))
        self.assertEqual(repository.list_fixed_category_keywords(self.session), (keyword,))
        self.session.add_all.assert_not_called()
        self.session.flush.assert_not_called()

    def test_returns_categories_after_flush_assigns_ids(self) -> None:
        def assign_ids() -> None:
            """flushによる採番を模擬し、返却時点のID確認に使用"""

            for index, category in enumerate(self.session.add_all.call_args.args[0], start=51):
                category.id = index

        self.session.flush.side_effect = assign_ids
        categories = repository.create_fixed_categories(
            self.session, [("air", "Air", 10), ("soil", "Soil", 30)],
        )
        self.assertEqual(len(categories), 2)
        self.assertEqual(
            [(category.id, category.slug, category.name, category.display_order) for category in categories],
            [(51, "air", "Air", 10), (52, "soil", "Soil", 30)],
        )
        self.session.flush.assert_called_once_with()

    def test_adds_keywords_with_supplied_ids_and_flushes(self) -> None:
        repository.create_fixed_category_keywords(self.session, [(51, "PCB"), (92, "PCB")])
        self.session.add_all.assert_called_once()
        self.assertEqual(
            [(item.fixed_category_id, item.keyword) for item in self.session.add_all.call_args.args[0]],
            [(51, "PCB"), (92, "PCB")],
        )
        self.session.flush.assert_called_once_with()

    def test_empty_additions_do_not_flush_unrelated_pending_objects(self) -> None:
        self.assertEqual(repository.create_fixed_categories(self.session, []), ())
        repository.create_fixed_category_keywords(self.session, [])
        self.session.add_all.assert_not_called()
        self.session.flush.assert_not_called()


if __name__ == "__main__":
    unittest.main()

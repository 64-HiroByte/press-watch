import unittest
from unittest.mock import Mock, patch

from sqlalchemy.orm import Session

from press_watch_api.models.fixed_category import FixedCategory, FixedCategoryKeyword
from press_watch_api.services import fixed_category_seed as service


class FixedCategorySeedTest(unittest.TestCase):
    """repositoryをMockに置き換え、照合結果に応じた追加要求を確認"""

    def setUp(self) -> None:
        self.session = Mock(spec=Session)
        self.data = service.parse_fixed_category_csv(
            b"slug,name,display_order\nair,Air,10\nsoil,Soil,20\n",
            b"category_slug,keyword\nair,shared\nsoil,shared\n",
        )
        # 表示順やCSV行番号をIDとして流用する実装を検出できる値にする。
        self.air = FixedCategory(id=51, slug="air", name="Air", display_order=10)
        self.soil = FixedCategory(id=92, slug="soil", name="Soil", display_order=20)
        self.repository = self.enterContext(patch.object(service, "repository"))
        self.repository.list_fixed_categories.return_value = ()
        self.repository.list_fixed_category_keywords.return_value = ()
        self.repository.create_fixed_categories.return_value = (self.air, self.soil)

    def tearDown(self) -> None:
        """全ケースで、serviceが呼び出し元のSession管理を引き受けないことを確認"""

        self.session.commit.assert_not_called()
        self.session.rollback.assert_not_called()
        self.session.close.assert_not_called()

    def test_adds_categories_and_keywords_using_generated_ids(self) -> None:
        result = service.seed_fixed_categories(self.session, self.data)
        self.assertEqual(result, service.FixedCategorySeedResult(2, 2))
        self.repository.create_fixed_categories.assert_called_once_with(
            self.session, [("air", "Air", 10), ("soil", "Soil", 20)],
        )
        self.repository.create_fixed_category_keywords.assert_called_once_with(
            self.session, [(51, "shared"), (92, "shared")],
        )

    def test_identical_data_does_not_request_any_inserts(self) -> None:
        self.repository.list_fixed_categories.return_value = (self.soil, self.air)
        self.repository.list_fixed_category_keywords.return_value = (
            FixedCategoryKeyword(fixed_category_id=51, keyword="shared"),
            FixedCategoryKeyword(fixed_category_id=92, keyword="shared"),
        )
        self.assertEqual(
            service.seed_fixed_categories(self.session, self.data),
            service.FixedCategorySeedResult(0, 0),
        )
        self.repository.list_fixed_categories.assert_called_once_with(self.session)
        self.repository.list_fixed_category_keywords.assert_called_once_with(self.session)
        self.repository.create_fixed_categories.assert_not_called()
        self.repository.create_fixed_category_keywords.assert_not_called()

    def test_adds_only_missing_category_and_keyword_assignments(self) -> None:
        self.repository.list_fixed_categories.return_value = (self.air,)
        self.repository.list_fixed_category_keywords.return_value = (
            FixedCategoryKeyword(fixed_category_id=51, keyword="shared"),
        )
        self.repository.create_fixed_categories.return_value = (self.soil,)
        self.assertEqual(
            service.seed_fixed_categories(self.session, self.data),
            service.FixedCategorySeedResult(1, 1),
        )
        self.repository.create_fixed_categories.assert_called_once_with(
            self.session, [("soil", "Soil", 20)],
        )
        self.repository.create_fixed_category_keywords.assert_called_once_with(
            self.session, [(92, "shared")],
        )

    def test_adds_missing_keywords_without_recreating_categories(self) -> None:
        self.repository.list_fixed_categories.return_value = (self.air, self.soil)
        self.assertEqual(
            service.seed_fixed_categories(self.session, self.data),
            service.FixedCategorySeedResult(0, 2),
        )
        self.repository.create_fixed_categories.assert_not_called()
        self.repository.create_fixed_category_keywords.assert_called_once_with(
            self.session, [(51, "shared"), (92, "shared")],
        )

    def test_rejects_category_conflicts_before_any_insert(self) -> None:
        for category in (
            FixedCategory(id=51, slug="extra", name="Extra", display_order=30),
            FixedCategory(id=51, slug="air", name="Different", display_order=10),
            FixedCategory(id=51, slug="air", name="Air", display_order=30),
        ):
            with self.subTest(slug=category.slug, name=category.name, order=category.display_order):
                self.repository.list_fixed_categories.return_value = (category,)
                with self.assertRaises(service.FixedCategorySeedConflictError):
                    service.seed_fixed_categories(self.session, self.data)
                self.repository.create_fixed_categories.assert_not_called()
                self.repository.create_fixed_category_keywords.assert_not_called()

    def test_rejects_extra_keywords_before_adding_missing_categories(self) -> None:
        self.repository.list_fixed_categories.return_value = (self.air,)
        for keyword in (
            FixedCategoryKeyword(fixed_category_id=51, keyword="extra"),
            FixedCategoryKeyword(fixed_category_id=999, keyword="shared"),
        ):
            with self.subTest(category_id=keyword.fixed_category_id, keyword=keyword.keyword):
                self.repository.list_fixed_category_keywords.return_value = (keyword,)
                with self.assertRaises(service.FixedCategorySeedConflictError):
                    service.seed_fixed_categories(self.session, self.data)
                self.repository.create_fixed_categories.assert_not_called()
                self.repository.create_fixed_category_keywords.assert_not_called()


if __name__ == "__main__":
    unittest.main()

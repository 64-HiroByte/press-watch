import unittest
from unittest.mock import Mock, patch

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from press_watch_api.models.fixed_category import FixedCategory, FixedCategoryKeyword
from press_watch_api.services import fixed_category_classification as service
from press_watch_api.services.fixed_category_seed import (
    FixedCategoryCsvError,
    parse_fixed_category_csv,
    load_fixed_category_seed,
)


class FixedCategoryRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Mock(spec=Session)
        self.data = parse_fixed_category_csv(
            b"slug,name,display_order\nair,Air,10\nsoil,Soil,30\n",
            b"category_slug,keyword\nair,shared\nsoil,PCB\n",
        )
        self.loader = self.enterContext(patch.object(service, "load_fixed_category_seed", return_value=self.data))
        self.repository = self.enterContext(patch.object(service, "repository"))
        self.categories = (
            FixedCategory(id=51, slug="air", name="Air", display_order=10),
            FixedCategory(id=92, slug="soil", name="Soil", display_order=30),
        )
        self.keywords = (
            FixedCategoryKeyword(fixed_category_id=51, keyword="shared"),
            FixedCategoryKeyword(fixed_category_id=92, keyword="PCB"),
        )
        self.repository.list_fixed_categories.return_value = self.categories
        self.repository.list_fixed_category_keywords.return_value = self.keywords

    def tearDown(self) -> None:
        self.session.commit.assert_not_called()
        self.session.rollback.assert_not_called()
        self.session.close.assert_not_called()
        self.repository.create_fixed_categories.assert_not_called()
        self.repository.create_fixed_category_keywords.assert_not_called()

    def test_loads_complete_definitions_with_actual_ids_and_normalized_keywords(self) -> None:
        self.repository.list_fixed_categories.return_value = tuple(reversed(self.categories))
        self.repository.list_fixed_category_keywords.return_value = tuple(reversed(self.keywords))
        self.assertEqual(service.load_fixed_category_rules(self.session), ((51, "shared"), (92, "pcb")))
        self.loader.assert_called_once_with()
        self.repository.list_fixed_categories.assert_called_once_with(self.session)
        self.repository.list_fixed_category_keywords.assert_called_once_with(self.session)

    def test_rejects_missing_extra_and_changed_categories(self) -> None:
        variants = (
            (), self.categories[:1],
            (*self.categories, FixedCategory(id=999, slug="extra", name="Extra", display_order=50)),
            (FixedCategory(id=51, slug="air", name="Different", display_order=10), self.categories[1]),
            (FixedCategory(id=51, slug="air", name="Air", display_order=20), self.categories[1]),
        )
        for categories in variants:
            with self.subTest(categories=[(item.slug, item.name, item.display_order) for item in categories]):
                self.repository.list_fixed_categories.return_value = categories
                with self.assertRaises(service.FixedCategoryClassificationError):
                    service.load_fixed_category_rules(self.session)

    def test_rejects_missing_extra_changed_and_unreferenced_keywords(self) -> None:
        variants = (
            (), self.keywords[:1],
            (*self.keywords, FixedCategoryKeyword(fixed_category_id=51, keyword="extra")),
            (self.keywords[0], FixedCategoryKeyword(fixed_category_id=92, keyword="pcb")),
            (self.keywords[0], FixedCategoryKeyword(fixed_category_id=92, keyword="ＰＣＢ")),
            (self.keywords[0], FixedCategoryKeyword(fixed_category_id=999, keyword="PCB")),
        )
        for keywords in variants:
            with self.subTest(keywords=[(item.fixed_category_id, item.keyword) for item in keywords]):
                self.repository.list_fixed_category_keywords.return_value = keywords
                with self.assertRaises(service.FixedCategoryClassificationError):
                    service.load_fixed_category_rules(self.session)

    def test_wraps_csv_read_and_validation_errors_without_original_details(self) -> None:
        for error in (OSError("private path sentinel"), FixedCategoryCsvError("fixed_categories.csv", "invalid value")):
            with self.subTest(error=type(error).__name__):
                self.loader.side_effect = error
                with self.assertRaisesRegex(service.FixedCategoryClassificationError, "^fixed category CSV could not be loaded$"):
                    service.load_fixed_category_rules(self.session)
                self.repository.list_fixed_categories.assert_not_called()
                self.repository.list_fixed_category_keywords.assert_not_called()

    def test_propagates_database_errors_to_existing_cli_diagnostics(self) -> None:
        error = SQLAlchemyError("fixed database failure")
        self.repository.list_fixed_category_keywords.side_effect = error
        with self.assertRaises(SQLAlchemyError) as caught:
            service.load_fixed_category_rules(self.session)
        self.assertIs(caught.exception, error)


class FixedCategoryClassificationTest(unittest.TestCase):
    def test_normalizes_both_title_and_keywords_before_substring_matching(self) -> None:
        rules = service.prepare_fixed_category_rules(((92, "ＰＣＢ"), (51, "STRASSE")))
        self.assertEqual(service.classify_title("前文 ｐＣＢとStraße に関する公表", rules), (51, 92))

    def test_matches_all_categories_once_even_with_shared_and_overlapping_keywords(self) -> None:
        rules = service.prepare_fixed_category_rules(((92, "大気"), (92, "大気汚染"), (51, "大気"), (77, "土壌")))
        self.assertEqual(service.classify_title("大気汚染と土壌の調査", rules), (51, 77, 92))

    def test_unmatched_title_has_no_category(self) -> None:
        rules = service.prepare_fixed_category_rules(((92, "PCB"),))
        self.assertEqual(service.classify_title("新しいお知らせ", rules), ())

    def test_common_and_other_require_their_own_bundled_keywords(self) -> None:
        data = load_fixed_category_seed()
        ids_by_slug = {item.slug: index for index, item in enumerate(data.categories, start=51)}
        rules = service.prepare_fixed_category_rules((ids_by_slug[slug], keyword) for slug, keyword in data.keywords)
        for title, slugs in (
            ("精度管理調査について", {"common"}),
            ("ｐｃｂについて", {"other"}),
            ("水道水と公共用水域の調査", {"tap_water", "environmental_water"}),
            ("新しいお知らせ", set()),
        ):
            with self.subTest(title=title):
                self.assertEqual(set(service.classify_title(title, rules)), {ids_by_slug[slug] for slug in slugs})


if __name__ == "__main__":
    unittest.main()

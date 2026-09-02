import unittest

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Integer,
    Text,
    UniqueConstraint,
)

import press_watch_api.models
from press_watch_api.models.base import Base


class FixedCategoryModelTest(unittest.TestCase):
    """固定カテゴリDBモデルのテーブル定義テスト"""

    def test_fixed_categories_table_has_expected_contract(self) -> None:
        """カテゴリ定義テーブルが合意済みの列と制約を持つこと"""

        self.assertIn("fixed_categories", Base.metadata.tables)
        table = Base.metadata.tables["fixed_categories"]

        self.assertEqual(
            set(table.columns.keys()),
            {"id", "slug", "name", "display_order"},
        )
        self.assertIsInstance(table.c.id.type, BigInteger)
        self.assertIsInstance(table.c.slug.type, Text)
        self.assertIsInstance(table.c.name.type, Text)
        self.assertIsInstance(table.c.display_order.type, Integer)
        self.assertEqual(
            [column.name for column in table.primary_key.columns],
            ["id"],
        )
        self.assertIs(table.c.id.autoincrement, True)
        for column in table.columns:
            with self.subTest(column_name=column.name):
                self.assertFalse(column.nullable)

        unique_constraints = {
            constraint.name: [column.name for column in constraint.columns]
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
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
            constraint.name: str(constraint.sqltext)
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        self.assertEqual(
            check_constraints,
            {"ck_fixed_categories_display_order_positive": "display_order > 0"},
        )

    def test_fixed_category_keywords_table_has_expected_contract(self) -> None:
        """カテゴリ判定用キーワードテーブルが合意済みの契約を持つこと"""

        self.assertIn("fixed_category_keywords", Base.metadata.tables)
        table = Base.metadata.tables["fixed_category_keywords"]

        self.assertEqual(
            set(table.columns.keys()),
            {"fixed_category_id", "keyword"},
        )
        self.assertIsInstance(table.c.fixed_category_id.type, BigInteger)
        self.assertIsInstance(table.c.keyword.type, Text)
        self.assertEqual(
            [column.name for column in table.primary_key.columns],
            ["fixed_category_id", "keyword"],
        )
        for column in table.columns:
            with self.subTest(column_name=column.name):
                self.assertFalse(column.nullable)

        foreign_key = next(iter(table.c.fixed_category_id.foreign_keys))
        self.assertEqual(foreign_key.target_fullname, "fixed_categories.id")
        self.assertEqual(foreign_key.ondelete, "CASCADE")

    def test_press_release_fixed_categories_table_has_expected_contract(
        self,
    ) -> None:
        """報道発表への固定カテゴリ付与テーブルが合意済みの契約を持つこと"""

        self.assertIn("press_release_fixed_categories", Base.metadata.tables)
        table = Base.metadata.tables["press_release_fixed_categories"]

        self.assertEqual(
            set(table.columns.keys()),
            {"press_release_id", "fixed_category_id"},
        )
        self.assertIsInstance(table.c.press_release_id.type, BigInteger)
        self.assertIsInstance(table.c.fixed_category_id.type, BigInteger)
        self.assertEqual(
            [column.name for column in table.primary_key.columns],
            ["press_release_id", "fixed_category_id"],
        )
        for column in table.columns:
            with self.subTest(column_name=column.name):
                self.assertFalse(column.nullable)

        foreign_keys = {
            foreign_key.parent.name: foreign_key for foreign_key in table.foreign_keys
        }
        self.assertEqual(
            {
                column_name: (
                    foreign_key.target_fullname,
                    foreign_key.ondelete,
                )
                for column_name, foreign_key in foreign_keys.items()
            },
            {
                "press_release_id": ("press_releases.id", "CASCADE"),
                "fixed_category_id": ("fixed_categories.id", "RESTRICT"),
            },
        )

        indexes = {
            index.name: [column.name for column in index.columns]
            for index in table.indexes
        }
        self.assertEqual(
            indexes,
            {
                "ix_press_release_fixed_categories_fixed_category_id": [
                    "fixed_category_id"
                ]
            },
        )


if __name__ == "__main__":
    unittest.main()

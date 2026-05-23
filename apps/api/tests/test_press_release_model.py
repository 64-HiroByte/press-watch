import unittest

from sqlalchemy import BigInteger, Date, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY

from press_watch_api.models import Base, PressRelease


class PressReleaseModelTest(unittest.TestCase):
    def test_press_releases_table_has_expected_columns(self) -> None:
        table = PressRelease.__table__

        self.assertEqual(table.name, "press_releases")
        self.assertEqual(
            set(table.columns.keys()),
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
        self.assertNotIn("category", table.columns)

    def test_press_releases_table_uses_expected_column_types(self) -> None:
        table = PressRelease.__table__

        self.assertIsInstance(table.c.id.type, BigInteger)
        self.assertIsInstance(table.c.title.type, Text)
        self.assertIsInstance(table.c.source_url.type, Text)
        self.assertIsInstance(table.c.published_at.type, Date)
        self.assertIsInstance(table.c.source_categories.type, ARRAY)
        self.assertIsInstance(table.c.source_categories.type.item_type, Text)
        self.assertIsInstance(table.c.fetched_at.type, DateTime)
        self.assertIsInstance(table.c.created_at.type, DateTime)
        self.assertIsInstance(table.c.updated_at.type, DateTime)

    def test_required_columns_are_not_nullable(self) -> None:
        table = PressRelease.__table__

        for column_name in table.columns.keys():
            with self.subTest(column_name=column_name):
                self.assertFalse(table.c[column_name].nullable)

    def test_source_url_has_named_unique_constraint(self) -> None:
        table = PressRelease.__table__
        unique_constraints = [
            constraint
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        ]

        self.assertTrue(
            any(
                constraint.name == "uq_press_releases_source_url"
                and [column.name for column in constraint.columns] == ["source_url"]
                for constraint in unique_constraints
            )
        )

    def test_source_categories_defaults_to_empty_list(self) -> None:
        default = PressRelease.__table__.c.source_categories.default

        self.assertIsNotNone(default)
        self.assertTrue(default.is_callable)
        self.assertEqual(default.arg(None), [])

    def test_timestamp_columns_use_timezone_aware_type(self) -> None:
        table = PressRelease.__table__

        self.assertTrue(table.c.fetched_at.type.timezone)
        self.assertTrue(table.c.created_at.type.timezone)
        self.assertTrue(table.c.updated_at.type.timezone)

    def test_model_metadata_contains_press_releases_table(self) -> None:
        self.assertIs(Base.metadata.tables["press_releases"], PressRelease.__table__)


if __name__ == "__main__":
    unittest.main()

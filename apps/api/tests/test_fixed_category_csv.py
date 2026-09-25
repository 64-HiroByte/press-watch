from contextlib import chdir
import tempfile
import unittest

from press_watch_api.services.fixed_category_seed import (
    FixedCategoryCsvError,
    load_fixed_category_seed,
    parse_fixed_category_csv,
)


class FixedCategoryCsvTest(unittest.TestCase):
    def test_loads_bundled_data_independently_of_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            data = load_fixed_category_seed()
        self.assertEqual(len(data.categories), 10)
        self.assertEqual(len(data.keywords), 57)
        self.assertEqual(
            [item.slug for item in data.categories],
            ["air", "soil", "tap_water", "environmental_water", "effluent",
             "odor", "noise", "vibration", "common", "other"],
        )
        self.assertIn(("other", "PCB"), data.keywords)

    def test_rejects_category_header_mismatch(self) -> None:
        categories = b"slug,label,display_order\nair,Air,1\n"
        keywords = b"category_slug,keyword\nair,air\n"

        with self.assertRaises(FixedCategoryCsvError):
            parse_fixed_category_csv(categories, keywords)

    def test_parses_categories_and_keyword_assignments(self) -> None:
        data = parse_fixed_category_csv(
            "slug,name,display_order\nair,大気,10\nsoil,土壌,30\n".encode(),
            "category_slug,keyword\nair,PCB\nsoil,PCB\n".encode(),
        )

        self.assertIsNotNone(data)
        self.assertEqual(
            [(item.slug, item.name, item.display_order) for item in data.categories],
            [("air", "大気", 10), ("soil", "土壌", 30)],
        )
        self.assertEqual(data.keywords, (("air", "PCB"), ("soil", "PCB")))

    def test_rejects_invalid_csv_structure_in_either_file(self) -> None:
        valid_categories = b"slug,name,display_order\nair,Air,1\n"
        valid_keywords = b"category_slug,keyword\nair,air\n"
        cases = (
            (b"slug,name\nair,Air\n", valid_keywords),
            (b"slug,name,display_order\nair,Air\n", valid_keywords),
            (b"slug,name,display_order\nair,Air,1,extra\n", valid_keywords),
            (b"slug,name,display_order\n\nair,Air,1\n", valid_keywords),
            (b"slug,name,display_order\n", valid_keywords),
            (valid_categories, b"category,keyword\nair,air\n"),
            (valid_categories, b"category_slug,keyword\nair\n"),
            (valid_categories, b"category_slug,keyword\nair,air,extra\n"),
            (valid_categories, b"category_slug,keyword\n\nair,air\n"),
            (valid_categories, b"category_slug,keyword\n"),
            (valid_categories, b'category_slug,keyword\nair,"unterminated\n'),
            (valid_categories, b'category_slug,keyword\nair,"quoted"tail\n'),
            (b'slug,name,display_order\nair,"Air"tail,1\n', valid_keywords),
        )
        for categories, keywords in cases:
            with self.subTest(categories=categories, keywords=keywords):
                with self.assertRaises(FixedCategoryCsvError):
                    parse_fixed_category_csv(categories, keywords)

    def test_rejects_invalid_encoding_and_line_endings_before_csv_parsing(self) -> None:
        originals = (
            b"slug,name,display_order\nair,Air,1\n",
            b"category_slug,keyword\nair,air\n",
        )
        for index in (0, 1):
            for invalid in (
                b"\xef\xbb\xbf" + originals[index],
                originals[index].replace(b"\n", b"\r\n"),
                originals[index].replace(b"\n", b"\r"),
                originals[index].rstrip(b"\n"),
                originals[index] + b"\xff\n",
                b"",
            ):
                inputs = list(originals)
                inputs[index] = invalid
                with self.subTest(index=index, invalid=invalid):
                    with self.assertRaises(FixedCategoryCsvError):
                        parse_fixed_category_csv(*inputs)

    def test_rejects_quotes_inside_unquoted_fields_in_either_file(self) -> None:
        categories = b"slug,name,display_order\nair,Air,1\n"
        keywords = b"category_slug,keyword\nair,air\n"
        for name in ('A"ir', 'A"ir"', 'A""ir'):
            with self.subTest(file="categories", name=name):
                with self.assertRaises(FixedCategoryCsvError) as caught:
                    parse_fixed_category_csv(
                        f"slug,name,display_order\nair,{name},1\n".encode(), keywords,
                    )
                self.assertEqual(caught.exception.file_name, "fixed_categories.csv")
                self.assertEqual(caught.exception.line, 2)
                self.assertEqual(caught.exception.reason, "invalid CSV syntax")
        for keyword in ('a"b', 'a"b"', 'a""b'):
            with self.subTest(file="keywords", keyword=keyword):
                with self.assertRaises(FixedCategoryCsvError) as caught:
                    parse_fixed_category_csv(
                        categories, f"category_slug,keyword\nair,valid\nair,{keyword}\n".encode(),
                    )
                self.assertEqual(caught.exception.file_name, "fixed_category_keywords.csv")
                self.assertEqual(caught.exception.line, 3)
                self.assertEqual(caught.exception.reason, "invalid CSV syntax")

    def test_accepts_quoted_fields_with_commas_and_escaped_quotes(self) -> None:
        data = parse_fixed_category_csv(
            b'"slug","name","display_order"\n"air","Air, ""quoted""","1"\n',
            b'"category_slug","keyword"\n"air","a,b""c"\nair,""""\n',
        )
        self.assertEqual(data.categories[0].name, 'Air, "quoted"')
        self.assertEqual(data.keywords, (("air", 'a,b"c'), ("air", '"')))

    def test_rejects_invalid_category_values(self) -> None:
        for column, values in {
            "slug": ("", " air", "air ", "Air", "1air", "air-2", "_air", "air_", "air__two", "ａｉｒ"),
            "name": ("", " 大気", "大気 ", "\tAir", "A\x00ir", "A\x7fir", "Ａｉｒ"),
            "display_order": ("", "0", "-1", "+1", "1.0", " 1", "1 ", "１", "2147483648", "9" * 5000),
        }.items():
            for value in values:
                row = {"slug": "air", "name": "大気", "display_order": "1"}
                row[column] = value
                categories = ("slug,name,display_order\n" + ",".join(row.values()) + "\n").encode()
                with self.subTest(column=column, value=value[:30]):
                    with self.assertRaises(FixedCategoryCsvError):
                        parse_fixed_category_csv(categories, b"category_slug,keyword\nair,air\n")

    def test_rejects_invalid_keyword_values_and_unknown_category(self) -> None:
        categories = b"slug,name,display_order\nair,Air,1\n"
        for row in (
            ",air", "unknown,air", " air,air", "air,", "air, air", "air,air ",
            "air,ＡＩＲ", "air,a\x00ir", "air,a\x85ir", 'air,"line\nbreak"',
        ):
            with self.subTest(row=row):
                with self.assertRaises(FixedCategoryCsvError):
                    parse_fixed_category_csv(categories, ("category_slug,keyword\n" + row + "\n").encode())

    def test_rejects_duplicate_category_fields_and_keyword_pairs(self) -> None:
        for second in ("air,Other,2", "soil,Air,2", "soil,Soil,01"):
            with self.subTest(second=second):
                with self.assertRaises(FixedCategoryCsvError):
                    parse_fixed_category_csv(
                        ("slug,name,display_order\nair,Air,1\n" + second + "\n").encode(),
                        b"category_slug,keyword\nair,air\n",
                    )
        with self.assertRaises(FixedCategoryCsvError):
            parse_fixed_category_csv(
                b"slug,name,display_order\nair,Air,1\n",
                b"category_slug,keyword\nair,air\nair,air\n",
            )

    def test_preserves_row_order_and_accepts_integer_upper_bound(self) -> None:
        data = parse_fixed_category_csv(
            b"slug,name,display_order\nsoil2,Soil,2147483647\nair_2,Air,0010\n",
            b"category_slug,keyword\nair_2,PCB\n",
        )
        self.assertEqual([item.display_order for item in data.categories], [2147483647, 10])

    def test_error_identifies_field_without_echoing_input(self) -> None:
        invalid_value = " PRIVATE_CSV_VALUE"
        with self.assertRaises(FixedCategoryCsvError) as caught:
            parse_fixed_category_csv(
                ("slug,name,display_order\nair," + invalid_value + ",1\n").encode(),
                b"category_slug,keyword\nair,air\n",
            )
        self.assertEqual(caught.exception.file_name, "fixed_categories.csv")
        self.assertEqual(caught.exception.line, 2)
        self.assertEqual(caught.exception.column, "name")
        self.assertNotIn("PRIVATE_CSV_VALUE", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

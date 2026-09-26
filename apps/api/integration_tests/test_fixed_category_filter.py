"""保存済み分類を使う一覧APIを、専用PostgreSQLと合成データで検証"""

from collections import Counter
from datetime import UTC, date, datetime
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from integration_tests.database import prepare_test_database
from press_watch_api.main import app
from press_watch_api.models.fixed_category import (
    FixedCategory,
    FixedCategoryKeyword,
    PressReleaseFixedCategory,
)
from press_watch_api.models.press_release import PressRelease


_MODELS = (
    PressReleaseFixedCategory,
    FixedCategoryKeyword,
    FixedCategory,
    PressRelease,
)
_CATEGORY_IDS = {"air": 703, "soil": 1109, "other": 2003}
_FETCHED_AT = datetime(2026, 9, 27, tzinfo=UTC)


class FixedCategoryFilterIntegrationTest(unittest.TestCase):
    """HTTPからrepositoryを通し、件数・一覧・DB非更新を確認"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = prepare_test_database()
        cls.addClassCleanup(cls.engine.dispose)

    def setUp(self) -> None:
        self.addCleanup(self._clear_test_data)
        self.enterContext(patch(
            "press_watch_api.dependencies.get_session_factory",
            return_value=lambda: Session(self.engine, autoflush=False),
        ))
        self.client = self.enterContext(TestClient(app))
        self._populate()

    def _clear_test_data(self) -> None:
        with self.engine.begin() as connection:
            for model in _MODELS:
                connection.execute(delete(model))

    def _populate(self) -> None:
        with Session(self.engine) as session:
            for order, (slug, category_id) in enumerate(
                _CATEGORY_IDS.items(), start=1
            ):
                session.add(FixedCategory(
                    id=category_id,
                    slug=slug,
                    name=f"合成カテゴリ{order}",
                    display_order=order,
                ))
            session.flush()
            session.add(FixedCategoryKeyword(
                fixed_category_id=_CATEGORY_IDS["air"],
                keyword="どの合成タイトルにも含まれない語句",
            ))
            rows = (
                (101, "Climate 50%_/ report", 1, ("air",)),
                (205, "Climate 500X/ report", 3, ("soil",)),
                (307, "Climate 50%_/ combined", 3, ("air", "soil")),
                (409, "Ordinary notice", 4, ("other",)),
                (503, "Climate 50%_/ unclassified", 5, ()),
                (607, "ＣＬＩＭＡＴＥ 50%_/ report", 2, ("air",)),
            )
            for release_id, title, day, slugs in rows:
                self._add_release(session, release_id, title, day, slugs)
            session.commit()

    @staticmethod
    def _add_release(
        session: Session,
        release_id: int,
        title: str,
        day: int,
        slugs: tuple[str, ...],
    ) -> None:
        session.add(PressRelease(
            id=release_id,
            title=title,
            source_url=f"https://example.test/press/{release_id}",
            published_at=date(2026, 1, day),
            # 取得元カテゴリから絞り込む誤実装を検出する。
            source_categories=None if slugs else ["air", "大気"],
            fetched_at=_FETCHED_AT,
        ))
        session.flush()
        session.add_all([
            PressReleaseFixedCategory(
                press_release_id=release_id,
                fixed_category_id=_CATEGORY_IDS[slug],
            )
            for slug in slugs
        ])

    def _snapshot(self) -> dict[str, tuple[dict[str, object], ...]]:
        with self.engine.connect() as connection:
            return {
                model.__tablename__: tuple(
                    dict(row) for row in connection.execute(
                        select(model.__table__).order_by(
                            *model.__table__.primary_key.columns
                        )
                    ).mappings()
                )
                for model in _MODELS
            }

    def _assert_page(
        self,
        params: dict[str, str | int | list[str]],
        expected_ids: list[int],
        *,
        total: int,
        total_pages: int = 1,
    ) -> None:
        """要求中の照会数・書込みの不在と、応答・全データの保持を確認"""

        before = self._snapshot()
        operations: Counter[str] = Counter()

        def count_operation(
            _connection, _cursor, statement, _parameters, _context, _many
        ) -> None:
            # SQL本文とパラメーターは記録せず、種別ごとの回数だけ保持する。
            operation = statement.lstrip().partition(" ")[0].upper()
            operations[operation] += 1

        event.listen(self.engine, "before_cursor_execute", count_operation)
        try:
            response = self.client.get("/press-releases", params=params)
        finally:
            event.remove(
                self.engine, "before_cursor_execute", count_operation
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(set(payload), {"items", "pagination"})
        self.assertEqual(
            [item["source_url"] for item in payload["items"]],
            [f"https://example.test/press/{item}" for item in expected_ids],
        )
        originals = {
            row["id"]: row
            for row in before[PressRelease.__tablename__]
        }
        for item, release_id in zip(payload["items"], expected_ids):
            original = originals[release_id]
            self.assertEqual(item, {
                "title": original["title"],
                "source_url": original["source_url"],
                "published_at": original["published_at"].isoformat(),
                "source_categories": original["source_categories"],
            })
        self.assertEqual(payload["pagination"], {
            "page": params.get("page", 1),
            "page_size": params.get("page_size", 50),
            "total_items": total,
            "total_pages": total_pages,
        })
        self.assertEqual(operations, {"SELECT": 2 if expected_ids else 1})
        self.assertEqual(self._snapshot(), before)

    def test_single_and_multiple_categories_use_saved_classifications(
        self,
    ) -> None:
        cases = (
            (["air"], [307, 607, 101]),
            (["soil"], [307, 205]),
            (["air", "soil"], [307, 205, 607, 101]),
            (["soil", "air", "air"], [307, 205, 607, 101]),
            (["other"], [409]),
        )
        for slugs, expected in cases:
            with self.subTest(slugs=slugs):
                self._assert_page(
                    {"fixed_category": slugs}, expected, total=len(expected)
                )

    def test_title_search_and_categories_use_and_with_literal_matching(
        self,
    ) -> None:
        cases = (
            ("climate", [307, 205, 101]),
            (" climate 50%_/ ", [307, 101]),
            ("ＣＬＩＭＡＴＥ", [607]),
            (" ", [307, 205, 607, 101]),
            ("no_match", []),
        )
        for query, expected in cases:
            with self.subTest(query=query):
                self._assert_page(
                    {"fixed_category": ["air", "soil"], "q": query},
                    expected,
                    total=len(expected),
                    total_pages=1 if expected else 0,
                )

    def test_unspecified_and_empty_categories_include_unclassified(
        self,
    ) -> None:
        for params in ({}, {"fixed_category": ["", "　", " "]}):
            with self.subTest(params=params):
                self._assert_page(
                    params, [503, 409, 307, 205, 607, 101], total=6
                )
        self._assert_page(
            {"q": "climate 50%_/"}, [503, 307, 101], total=3
        )

    def test_unknown_categories_return_only_known_matches(self) -> None:
        self._assert_page(
            {"fixed_category": ["unknown", "air"]},
            [307, 607, 101],
            total=3,
        )
        self._assert_page(
            {"fixed_category": ["unknown", "missing"]},
            [],
            total=0,
            total_pages=0,
        )

    def test_empty_definitions_keep_unfiltered_list_available(self) -> None:
        with self.engine.begin() as connection:
            for model in _MODELS[:-1]:
                connection.execute(delete(model))
        self._assert_page(
            {"fixed_category": "air"}, [], total=0, total_pages=0
        )
        self._assert_page({}, [503, 409, 307, 205, 607, 101], total=6)
        self._assert_page(
            {"q": "climate 50%_/"}, [503, 307, 101], total=3
        )

    def test_missing_keywords_do_not_affect_saved_category_filter(
        self,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(delete(FixedCategoryKeyword))
        self._assert_page(
            {"fixed_category": "air"}, [307, 607, 101], total=3
        )

    def test_filtered_pagination_has_no_duplicate_or_missing_releases(
        self,
    ) -> None:
        for total, pages in ((20, 2), (21, 3), (23, 3)):
            with self.subTest(total=total):
                with Session(self.engine) as session:
                    session.execute(delete(PressRelease))
                    for index in range(total):
                        self._add_release(
                            session,
                            1000 + index,
                            "対象の合成報道発表",
                            index // 5 + 1,
                            ("air", "soil") if index % 2 else ("air",),
                        )
                    self._add_release(
                        session, 9999, "対象の未分類の報道発表", 30, ()
                    )
                    self._add_release(
                        session, 10000, "検索語を含まない発表", 31, ("air",)
                    )
                    session.commit()
                expected = list(reversed(range(1000, 1000 + total)))
                for page in range(1, pages + 2):
                    self._assert_page(
                        {
                            "fixed_category": ["air", "soil"],
                            "q": "対象の",
                            "page": page,
                            "page_size": 10,
                        },
                        expected[(page - 1) * 10:page * 10],
                        total=total,
                        total_pages=pages,
                    )


if __name__ == "__main__":
    unittest.main()

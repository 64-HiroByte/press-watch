"""公開日と保存済み分類で絞り込む一覧APIを、専用PostgreSQLと合成データで検証"""

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


_CATEGORY_MODELS = (
    PressReleaseFixedCategory,
    FixedCategoryKeyword,
    FixedCategory,
)
_DATA_MODELS = (*_CATEGORY_MODELS, PressRelease)
_CATEGORY_IDS = {"air": 703, "soil": 1109, "other": 2003}
_CATEGORY_DISPLAY_ORDERS = {"air": 30, "soil": 10, "other": 20}
_FETCHED_AT = datetime(2026, 9, 27, tzinfo=UTC)
_SOURCE_URL_PREFIX = "https://example.test/press/"


class FixedCategoryFilterIntegrationTest(unittest.TestCase):
    """HTTPからrepositoryを通し、日付境界・全所属・表示順・照会数・DB非更新を確認"""

    def test_publication_range_includes_boundaries_and_supports_optional_sides(
        self,
    ) -> None:
        """実DBで公開日の両端・片側・未指定・同日・0件の一覧契約を確認

        _assert_pageを通して、期待する記事・件数・所属・照会数とDB非更新を確認する。
        """

        cases = (
            (
                {"published_from": "2026-01-02", "published_to": "2026-01-04"},
                [409, 307, 205, 607],
            ),
            ({"published_from": "2026-01-02"}, [503, 409, 307, 205, 607]),
            ({"published_to": "2026-01-04"}, [409, 307, 205, 607, 101]),
            (
                {"published_from": "2026-01-03", "published_to": "2026-01-03"},
                [307, 205],
            ),
            ({}, [503, 409, 307, 205, 607, 101]),
            ({"published_from": "2026-01-06", "published_to": "2026-01-07"}, []),
        )
        for params, expected in cases:
            with self.subTest(params=params):
                self._assert_page(
                    params, expected, total=len(expected),
                    total_pages=1 if expected else 0,
                )

    def test_publication_range_combines_title_and_category_or_with_and(self) -> None:
        """日付・タイトル・所属のいずれかだけ不一致の行を除外し、全所属を保持"""

        self._assert_page({
            "published_from": "2026-01-02", "published_to": "2026-01-05",
            "q": "50%_/", "fixed_category": ["air", "soil"],
        }, [307, 607], total=2)

    def test_publication_range_filters_before_count_and_pagination(self) -> None:
        """範囲外の同じタイトル・所属を除外して、同日ID順と全ページを確認"""

        with Session(self.engine) as session:
            for index in range(21):
                self._add_release(
                    session, 1000 + index, "Date page 50%_/", 2 + index // 7,
                    ("air", "soil") if index % 2 == 0 else ("air",),
                )
            for release_id, day in ((2000, 1), (2001, 5)):
                self._add_release(
                    session, release_id, "Date page 50%_/", day, ("air",)
                )
            session.commit()
        expected_pages = (
            list(range(1020, 1010, -1)), list(range(1010, 1000, -1)), [1000], [],
        )
        for page, expected in enumerate(expected_pages, start=1):
            with self.subTest(page=page):
                self._assert_page({
                    "published_from": "2026-01-02", "published_to": "2026-01-04",
                    "q": "Date page 50%_/", "fixed_category": ["air", "soil"],
                    "page_size": 10, "page": page,
                }, expected, total=21, total_pages=3)

    @classmethod
    def setUpClass(cls) -> None:
        """安全ガードを通る専用PostgreSQLを準備"""

        cls.engine = prepare_test_database()
        cls.addClassCleanup(cls.engine.dispose)

    def setUp(self) -> None:
        """実dependencyの接続先だけを専用DBへ差し替え、合成データを投入

        Sessionの生成・終了は実dependencyを通し、factoryだけをpatchする。
        データ削除とpatch・TestClientの解除は、登録したunittestのcleanupに委ねる。
        """

        self.addCleanup(self._clear_test_data)
        self.enterContext(patch(
            "press_watch_api.dependencies.get_session_factory",
            return_value=lambda: Session(self.engine, autoflush=False),
        ))
        self.client = self.enterContext(TestClient(app))
        self._populate()

    def _clear_test_data(self) -> None:
        """外部キーの参照順に従い、専用DBの検証用データを削除"""

        with self.engine.begin() as connection:
            for model in _DATA_MODELS:
                connection.execute(delete(model))

    def _populate(self) -> None:
        """保存済み分類だけを使うことを検証する合成データを投入

        タイトルに一致しない分類キーワードと、固定カテゴリに似た
        取得元カテゴリを持つ未分類データを含める。
        投入結果はHTTP要求用のSessionから参照できるようcommitする。
        """

        with Session(self.engine) as session:
            for order, (slug, category_id) in enumerate(
                _CATEGORY_IDS.items(), start=1
            ):
                session.add(FixedCategory(
                    id=category_id,
                    slug=slug,
                    name=f"合成カテゴリ{order}",
                    display_order=_CATEGORY_DISPLAY_ORDERS[slug],
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
        """報道発表と指定された分類結果をテスト用Sessionへ追加

        原本をflushしてから分類結果を保存待ちにし、commitは呼び出し側に委ねる。
        未分類データには取得元カテゴリを付け、両者の混同を検出する。

        Args:
            session: 専用テストDBのデータ投入用Session
            release_id: 合成報道発表のIDとURL末尾に使う識別子
            title: 検索条件との一致を検証するタイトル
            day: 合成データの公開日である2026年1月の日にち
            slugs: 合成カテゴリ定義に存在するslug、空の場合は未分類
        """

        session.add(PressRelease(
            id=release_id,
            title=title,
            source_url=f"{_SOURCE_URL_PREFIX}{release_id}",
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
        """HTTP要求前後のDB非更新を比較するため全対象テーブルを取得

        Returns:
            テーブル名をキー、主キー順に並べた全行を値とする辞書
            各行は全列の名前と値を保持する辞書
        """

        with self.engine.connect() as connection:
            return {
                model.__tablename__: tuple(
                    dict(row) for row in connection.execute(
                        select(model.__table__).order_by(
                            *model.__table__.primary_key.columns
                        )
                    ).mappings()
                )
                for model in _DATA_MODELS
            }

    def _assert_page(
        self,
        params: dict[str, str | int | list[str]],
        expected_ids: list[int],
        *,
        total: int,
        total_pages: int = 1,
    ) -> None:
        """要求中の照会数・書込みの不在と、応答・全データの保持を確認

        HTTP要求中のSQLだけを数え、要求前後の全対象テーブルを比較する。
        同時更新のない合成データを前提とする。
        件数で判定できる空ページは1 SELECT、記事のあるページは3 SELECT。
        公開する所属は要求前の保存済みデータと表示順から確認する。

        Args:
            params: 一覧APIへ渡すクエリ、リスト値は同名クエリの繰り返し
            expected_ids: 期待するページ内の記事IDを公開日・IDの降順に並べた一覧
            total: ページ分割前の絞り込み済み総件数
            total_pages: 期待する総ページ数、0件の場合は0を指定
        """

        before = self._snapshot()
        operations: Counter[str] = Counter()

        def count_operation(
            _connection, _cursor, statement, _parameters, _context, _many
        ) -> None:
            """HTTP要求区間の実行通知からSQLの操作種別だけを集計

            回数は外側のoperationsへ加算し、SQL本文やパラメーターは保存しない。
            listenerの登録・解除は呼出し元の_assert_pageが担当する。

            Args:
                _connection: 実行に使われる接続。未使用
                _cursor: 実行に使われるDBAPIカーソル。未使用
                statement: 操作種別を判定するSQL本文
                _parameters: SQLの実行パラメーター。参照・記録しない
                _context: SQLAlchemyの実行コンテキスト。未使用
                _many: executemanyによる実行かを表すフラグ。未使用
            """

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
            [f"{_SOURCE_URL_PREFIX}{item}" for item in expected_ids],
        )
        originals = {
            row["id"]: row
            for row in before[PressRelease.__tablename__]
        }
        categories = {
            row["id"]: row for row in before[FixedCategory.__tablename__]
        }
        for item, release_id in zip(payload["items"], expected_ids):
            original = originals[release_id]
            saved_categories = sorted(
                (
                    categories[row["fixed_category_id"]]
                    for row in before[PressReleaseFixedCategory.__tablename__]
                    if row["press_release_id"] == release_id
                ),
                key=lambda category: category["display_order"],
            )
            self.assertEqual(item, {
                "title": original["title"],
                "source_url": original["source_url"],
                "published_at": original["published_at"].isoformat(),
                "source_categories": original["source_categories"],
                "fixed_categories": [
                    {"slug": category["slug"], "name": category["name"]}
                    for category in saved_categories
                ],
            })
        self.assertEqual(payload["pagination"], {
            "page": params.get("page", 1),
            "page_size": params.get("page_size", 50),
            "total_items": total,
            "total_pages": total_pages,
        })
        self.assertEqual(operations, {"SELECT": 3 if expected_ids else 1})
        self.assertEqual(self._snapshot(), before)

    def test_single_and_multiple_categories_use_saved_classifications(
        self,
    ) -> None:
        """保存済み分類のOR条件で絞り込み、複数所属や重複指定でも一意"""

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
        """カテゴリとのAND条件でもタイトルの記号一致と全角の区別を維持"""

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
        """未指定・空カテゴリの一覧とタイトル検索では未分類も対象"""

        for params in ({}, {"fixed_category": ["", "　", " "]}):
            with self.subTest(params=params):
                self._assert_page(
                    params, [503, 409, 307, 205, 607, 101], total=6
                )
        self._assert_page(
            {"q": "climate 50%_/"}, [503, 307, 101], total=3
        )

    def test_unknown_categories_return_only_known_matches(self) -> None:
        """未定義slugは一致せず、既知slugとの混在では既知の結果だけ取得"""

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
        """カテゴリ定義が空でも絞り込みなしの一覧とタイトル検索は利用可能"""

        with self.engine.begin() as connection:
            for model in _CATEGORY_MODELS:
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
        """分類キーワードが空でも保存済み分類で絞り込み可能"""

        with self.engine.begin() as connection:
            connection.execute(delete(FixedCategoryKeyword))
        self._assert_page(
            {"fixed_category": "air"}, [307, 607, 101], total=3
        )

    def test_missing_memberships_return_empty_arrays_with_definitions_present(
        self,
    ) -> None:
        """定義があっても所属のない記事は、未絞り込み・タイトル検索とも空の所属配列"""

        with self.engine.begin() as connection:
            connection.execute(delete(PressReleaseFixedCategory))
        self._assert_page({}, [503, 409, 307, 205, 607, 101], total=6)
        self._assert_page({"q": "climate 50%_/"}, [503, 307, 101], total=3)

    def test_membership_select_count_is_constant_for_1_10_50_100_articles(
        self,
    ) -> None:
        """ページ内記事数によらず3 SELECTで全所属を返し、DBを更新しないこと"""

        with Session(self.engine) as session:
            session.execute(delete(PressRelease))
            for index in range(101):
                self._add_release(
                    session, 1000 + index, "N+1検証の合成記事", index // 5 + 1,
                    ("air", "soil") if index % 2 else ("air",),
                )
            session.commit()
        expected = list(reversed(range(1000, 1101)))
        for page_size, page in ((10, 1), (50, 1), (100, 1), (100, 2)):
            with self.subTest(
                article_count=min(page_size, 101 - (page - 1) * page_size)
            ):
                self._assert_page(
                    {
                        "fixed_category": "air", "page_size": page_size,
                        "page": page,
                    },
                    expected[(page - 1) * page_size:page * page_size],
                    total=101,
                    total_pages=(101 + page_size - 1) // page_size,
                )

    def test_filtered_pagination_has_no_duplicate_or_missing_releases(
        self,
    ) -> None:
        """絞り込み後の同日データをID降順で分割し、最終・超過ページを確認"""

        first_release_id = 1000
        releases_per_day = 5
        page_size = 10
        for total, pages in ((20, 2), (21, 3), (23, 3)):
            with self.subTest(total=total):
                with Session(self.engine) as session:
                    session.execute(delete(PressRelease))
                    for index in range(total):
                        self._add_release(
                            session,
                            first_release_id + index,
                            "対象の合成報道発表",
                            index // releases_per_day + 1,
                            ("air", "soil") if index % 2 else ("air",),
                        )
                    self._add_release(
                        session, 9999, "対象の未分類の報道発表", 30, ()
                    )
                    self._add_release(
                        session, 10000, "検索語を含まない発表", 31, ("air",)
                    )
                    session.commit()
                expected = list(reversed(range(
                    first_release_id, first_release_id + total
                )))
                for page in range(1, pages + 2):
                    self._assert_page(
                        {
                            "fixed_category": ["air", "soil"],
                            "q": "対象の",
                            "page": page,
                            "page_size": page_size,
                        },
                        expected[(page - 1) * page_size:page * page_size],
                        total=total,
                        total_pages=pages,
                    )


if __name__ == "__main__":
    unittest.main()

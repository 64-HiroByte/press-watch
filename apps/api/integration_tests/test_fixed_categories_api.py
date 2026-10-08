"""固定カテゴリ選択肢APIを専用PostgreSQLと合成データで検証"""

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


_DATA_MODELS = (
    PressReleaseFixedCategory,
    FixedCategoryKeyword,
    FixedCategory,
    PressRelease,
)
_CATEGORY_DATA = (
    (903, "soil", "保存済み土壌", 30),
    (151, "other", "保存済みその他", 70),
    (407, "air", "保存済み大気", 10),
)
_EXPECTED_ITEMS = [
    {"slug": "air", "name": "保存済み大気", "display_order": 10},
    {"slug": "soil", "name": "保存済み土壌", "display_order": 30},
    {"slug": "other", "name": "保存済みその他", "display_order": 70},
]


class FixedCategoryListIntegrationTest(unittest.TestCase):
    """HTTPから実repositoryを通し、順序・1 SELECT・DB非更新を確認"""

    @classmethod
    def setUpClass(cls) -> None:
        """安全ガードを通る専用DBを再構築し、クラス終了時のEngine解放を登録"""

        cls.engine = prepare_test_database()
        cls.addClassCleanup(cls.engine.dispose)

    def setUp(self) -> None:
        """Sessionの接続先だけを差し替え、合成定義をcommitしてHTTP要求へ公開

        実dependencyの終了処理を維持し、テスト後に外部キーの参照順で合成データを削除する。
        挿入順・ID順・slug順を表示順と異ならせ、順序指定の不足を検出する。
        """

        self.addCleanup(self._clear_test_data)
        self.enterContext(patch(
            "press_watch_api.dependencies.get_session_factory",
            return_value=lambda: Session(self.engine, autoflush=False),
        ))
        self.client = self.enterContext(TestClient(app))
        with Session(self.engine) as session:
            for category_id, slug, name, order in _CATEGORY_DATA:
                session.add(FixedCategory(
                    id=category_id, slug=slug, name=name, display_order=order,
                ))
            session.commit()

    def _clear_test_data(self) -> None:
        """外部キーの参照順で専用DBの合成データを削除"""

        with self.engine.begin() as connection:
            for model in _DATA_MODELS:
                connection.execute(delete(model))

    def _snapshot(self) -> dict[str, tuple[dict[str, object], ...]]:
        """要求前後の非更新確認用に4テーブルの全列を主キー順で取得

        Returns:
            テーブル名をキー、全列の名前と値を持つ行のtupleを値とする辞書
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

    def _assert_options(self, expected: list[dict[str, object]]) -> None:
        """HTTP要求区間のSQL種別だけを集計し、応答と全データの保持を確認

        snapshotの取得・合成データの投入と削除はSQL集計に含めない。
        listenerはHTTP要求の成功・失敗にかかわらず解除する。

        Args:
            expected: 公開3項目を持つ選択肢の期待値。表示順に並べ、0件なら空のlist
        """

        before = self._snapshot()
        operations: Counter[str] = Counter()

        def count_operation(
            _connection, _cursor, statement, _parameters, _context, _many,
        ) -> None:
            # SQL本文やパラメーターを保存せず、要求区間の種別と回数だけ保持する。
            operations[statement.lstrip().partition(" ")[0].upper()] += 1

        event.listen(self.engine, "before_cursor_execute", count_operation)
        try:
            response = self.client.get("/fixed-categories")
        finally:
            event.remove(self.engine, "before_cursor_execute", count_operation)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": expected})
        self.assertEqual(operations, {"SELECT": 1})
        self.assertEqual(self._snapshot(), before)

    def test_definitions_alone_use_display_order_not_insertion_id_or_slug(self) -> None:
        self._assert_options(_EXPECTED_ITEMS)

    def test_keywords_and_articles_do_not_limit_options_or_change_data(self) -> None:
        with Session(self.engine) as session:
            session.add(FixedCategoryKeyword(
                fixed_category_id=903, keyword="選択肢表示には使わない語句",
            ))
            session.add(PressRelease(
                id=1009, title="合成報道発表", source_url="https://example.test/press/1009",
                published_at=date(2026, 1, 1), source_categories=["取得元カテゴリ"],
                fetched_at=datetime(2026, 1, 2, tzinfo=UTC),
            ))
            session.flush()
            session.add(PressReleaseFixedCategory(
                press_release_id=1009, fixed_category_id=903,
            ))
            session.commit()

        self._assert_options(_EXPECTED_ITEMS)

    def test_empty_definitions_return_empty_items_with_one_select_and_no_seed(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(delete(FixedCategory))

        self._assert_options([])


if __name__ == "__main__":
    unittest.main()

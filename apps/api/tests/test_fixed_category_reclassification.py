"""固定カテゴリ再分類serviceのバッチ処理と責務境界のテスト"""

import unittest
from unittest.mock import Mock, call, patch

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from press_watch_api.services import fixed_category_reclassification as service
from press_watch_api.services.fixed_category_classification import (
    FixedCategoryClassificationError,
)


class FixedCategoryReclassificationTest(unittest.TestCase):
    """DB操作をMockへ置換し、実際のタイトル判定とバッチ処理を確認"""

    def setUp(self) -> None:
        self.session = Mock(spec=Session)
        self.load = self.enterContext(
            patch.object(service.classification, "load_fixed_category_rules")
        )
        self.load.return_value = ((51, "大気"), (92, "pcb"))
        self.read = self.enterContext(
            patch.object(
                service.release_repository,
                "list_press_release_titles_after_id",
                return_value=(),
            )
        )
        self.delete = self.enterContext(
            patch.object(
                service.category_repository,
                "delete_press_release_fixed_categories",
            )
        )
        self.insert = self.enterContext(
            patch.object(
                service.category_repository,
                "create_press_release_fixed_categories",
            )
        )

    def tearDown(self) -> None:
        """すべてのケースで、確定・取消・Session終了を呼び出し元へ委ねることを確認"""

        self.session.commit.assert_not_called()
        self.session.rollback.assert_not_called()
        self.session.close.assert_not_called()

    def test_validates_rules_even_when_no_releases_exist(self) -> None:
        """対象0件でもルール読込みを要求し、削除・追加なしで件数0を返すことを確認"""

        self.assertEqual(
            service.reclassify_press_releases(self.session),
            service.PressReleaseReclassificationResult(0, 0, 0),
        )
        self.load.assert_called_once_with(self.session)
        self.read.assert_called_once_with(
            self.session, after_id=None, limit=1000
        )
        self.delete.assert_not_called()
        self.insert.assert_not_called()

    def test_rule_failure_propagates_before_any_release_operation(
        self,
    ) -> None:
        """ルール不備・DB例外を伝播し、対象取得や結果変更へ進まないことを確認"""

        for error in (
            FixedCategoryClassificationError("fixed rule failure"),
            SQLAlchemyError("fixed database failure"),
        ):
            with self.subTest(error=type(error).__name__):
                self.load.side_effect = error
                with self.assertRaises(type(error)) as caught:
                    service.reclassify_press_releases(self.session)
                self.assertIs(caught.exception, error)
                self.session.execute.assert_not_called()
                self.read.assert_not_called()
                self.delete.assert_not_called()
                self.insert.assert_not_called()

    def test_replaces_all_batch_ids_with_only_matching_pairs(self) -> None:
        """未一致の旧結果も削除し、正規化・重複排除した一致結果だけを保存"""

        rows = ((-6, "ＰＣＢと大気汚染"), (0, "お知らせ"), (7, "大気と大気"))
        self.read.return_value = rows
        operations = Mock()
        for name, method in (
            ("load", self.load),
            ("read", self.read),
            ("delete", self.delete),
            ("insert", self.insert),
        ):
            operations.attach_mock(method, name)
        result = service.reclassify_press_releases(self.session)
        self.assertEqual(
            result, service.PressReleaseReclassificationResult(3, 2, 3)
        )
        self.assertEqual(
            operations.mock_calls,
            [
                call.load(self.session),
                call.read(self.session, after_id=None, limit=1000),
                call.delete(self.session, (-6, 0, 7)),
                call.insert(self.session, [(-6, 51), (-6, 92), (7, 51)]),
            ],
        )

    def test_batch_boundaries_visit_each_nonconsecutive_id_once(self) -> None:
        """空・端数・満杯のバッチで、非連番の全対象を重複や欠落なく処理"""

        for count in (0, 1, 999, 1000, 1001, 2000):
            with self.subTest(count=count):
                for method in (self.load, self.read, self.delete, self.insert):
                    method.reset_mock()
                rows = tuple((index * 3 - 6, "大気") for index in range(count))
                self.read.side_effect = (
                    lambda _session, *, after_id, limit: tuple(
                        row
                        for row in rows
                        if after_id is None or row[0] > after_id
                    )[:limit]
                )
                result = service.reclassify_press_releases(self.session)
                self.assertEqual(
                    result,
                    service.PressReleaseReclassificationResult(
                        count, count, count
                    ),
                )
                self.load.assert_called_once_with(self.session)
                self.assertEqual(self.read.call_count, count // 1000 + 1)
                self.assertEqual(self.delete.call_count, (count + 999) // 1000)
                self.assertEqual(
                    [
                        release_id
                        for invocation in self.delete.call_args_list
                        for release_id in invocation.args[1]
                    ],
                    [row[0] for row in rows],
                )
                self.assertEqual(
                    [
                        pair
                        for invocation in self.insert.call_args_list
                        for pair in invocation.args[1]
                    ],
                    [(row[0], 51) for row in rows],
                )

    def test_classifier_failure_does_not_delete_the_incomplete_batch(
        self,
    ) -> None:
        """判定途中の失敗・中断では、そのバッチの旧分類を削除しないことを確認"""

        self.read.return_value = ((1, "大気"), (2, "失敗対象"))
        for error in (
            RuntimeError("fixed classifier failure"),
            KeyboardInterrupt(),
        ):
            with self.subTest(error=type(error).__name__):
                with patch.object(
                    service.classification,
                    "classify_title",
                    side_effect=[(51,), error],
                ):
                    with self.assertRaises(type(error)) as caught:
                        service.reclassify_press_releases(self.session)
                self.assertIs(caught.exception, error)
                self.delete.assert_not_called()
                self.insert.assert_not_called()

    def test_repository_failures_propagate(self) -> None:
        """取得・削除・追加の失敗を、rollbackを担当する呼び出し元へ伝播"""

        for method in (self.read, self.delete, self.insert):
            with self.subTest(operation=method._mock_name):
                error = SQLAlchemyError("fixed repository failure")
                self.read.return_value = ((1, "大気"),)
                method.side_effect = error
                with self.assertRaises(SQLAlchemyError) as caught:
                    service.reclassify_press_releases(self.session)
                self.assertIs(caught.exception, error)
                method.side_effect = None


if __name__ == "__main__":
    unittest.main()

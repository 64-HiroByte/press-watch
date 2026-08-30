from datetime import UTC, date, datetime
import unittest
from unittest.mock import Mock, call

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from press_watch_api.models.press_release import PressRelease
from press_watch_api.repositories import press_release as press_release_repository
from press_watch_api.repositories.press_release import (
    count_press_releases,
    create_press_release,
    get_latest_press_release_published_at,
    has_press_release_with_source_url,
    list_press_releases,
    list_press_release_source_urls_published_from,
)
from press_watch_api.schemas.press_release import PressReleaseCreate
from api_test_constants import ENV_PRESS_RELEASE_URL_1 as SOURCE_URL_1


class PressReleaseRepositoryTest(unittest.TestCase):
    """報道発表repositoryのテスト"""

    def test_create_press_release_builds_model_from_create_dto(self) -> None:
        """保存DTOの値からPressReleaseモデルを組み立てること"""

        session = Mock(spec=Session)
        dto = _press_release_create(
            source_categories=["総合政策", "自然環境"],
        )

        press_release = create_press_release(session, dto)

        self.assertIsInstance(press_release, PressRelease)
        self.assertEqual(press_release.title, dto.title)
        self.assertEqual(press_release.source_url, dto.source_url)
        self.assertEqual(press_release.published_at, dto.published_at)
        self.assertEqual(
            press_release.source_categories,
            ["総合政策", "自然環境"],
        )
        self.assertIsNot(press_release.source_categories, dto.source_categories)
        self.assertEqual(press_release.fetched_at, dto.fetched_at)

    def test_create_press_release_allows_null_source_categories(self) -> None:
        """取得元カテゴリがないDTOをNoneのままモデルへ写すこと"""

        session = Mock(spec=Session)
        dto = _press_release_create(source_categories=None)

        press_release = create_press_release(session, dto)

        self.assertIsNone(press_release.source_categories)

    def test_create_press_release_adds_and_flushes_model(self) -> None:
        """作成したモデルをセッションへ追加してflushすること"""

        session = Mock(spec=Session)
        dto = _press_release_create()

        press_release = create_press_release(session, dto)

        session.add.assert_called_once_with(press_release)
        session.flush.assert_called_once_with()
        session.assert_has_calls(
            [
                call.add(press_release),
                call.flush(),
            ]
        )

    def test_create_press_release_leaves_transaction_control_to_caller(
        self,
    ) -> None:
        """トランザクションの確定や取消を呼び出し元へ任せること"""

        session = Mock(spec=Session)
        dto = _press_release_create()

        create_press_release(session, dto)

        session.commit.assert_not_called()
        session.rollback.assert_not_called()

    def test_create_press_releases_builds_explicit_postgresql_insert(
        self,
    ) -> None:
        """明示5列とURL競合回避、モデル全列RETURNINGを組み立てること"""

        session = Mock(spec=Session)
        returned_first = Mock(spec=PressRelease)
        returned_second = Mock(spec=PressRelease)
        session.scalars.return_value = (returned_first, returned_second)
        first_dto = _press_release_create(
            source_url=SOURCE_URL_1,
            source_categories=["総合政策", "自然環境"],
        )
        second_dto = _press_release_create(
            source_url="https://example.test/press/2",
            source_categories=None,
        )
        create_press_releases = getattr(
            press_release_repository,
            "create_press_releases",
            None,
        )
        if create_press_releases is None:
            self.fail("複数行保存repositoryが未実装です。")

        result = create_press_releases(
            session,
            (first_dto, second_dto),
        )

        self.assertEqual(result, (returned_first, returned_second))
        session.scalars.assert_called_once()
        statement = session.scalars.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        compiled_sql = str(compiled)
        self.assertIn(
            "INSERT INTO press_releases "
            "(title, source_url, published_at, source_categories, fetched_at)",
            compiled_sql,
        )
        self.assertIn(
            "ON CONFLICT (source_url) DO NOTHING",
            compiled_sql,
        )
        for column_name in (
            "id",
            "title",
            "source_url",
            "published_at",
            "source_categories",
            "fetched_at",
            "created_at",
            "updated_at",
        ):
            self.assertIn(
                f"press_releases.{column_name}",
                compiled_sql.partition("RETURNING")[2],
            )
        self.assertEqual(len(compiled.params), 10)
        copied_categories = compiled.params["source_categories_m0"]
        self.assertEqual(copied_categories, first_dto.source_categories)
        self.assertIsNot(copied_categories, first_dto.source_categories)
        session.add.assert_not_called()
        session.flush.assert_not_called()
        session.commit.assert_not_called()
        session.rollback.assert_not_called()

    def test_create_press_releases_does_not_execute_sql_for_empty_input(
        self,
    ) -> None:
        """空のDTO列ではSQLを実行せず空タプルを返すこと"""

        session = Mock(spec=Session)
        create_press_releases = getattr(
            press_release_repository,
            "create_press_releases",
            None,
        )
        if create_press_releases is None:
            self.fail("複数行保存repositoryが未実装です。")

        result = create_press_releases(session, ())

        self.assertEqual(result, ())
        session.scalars.assert_not_called()
        session.add.assert_not_called()
        session.flush.assert_not_called()
        session.commit.assert_not_called()
        session.rollback.assert_not_called()

    def test_has_press_release_with_source_url_returns_true_when_found(
        self,
    ) -> None:
        """指定URLの既存行がある場合はTrueを返すこと"""

        session = Mock(spec=Session)
        session.scalar.return_value = 1

        exists = has_press_release_with_source_url(
            session,
            SOURCE_URL_1,
        )

        self.assertTrue(exists)
        session.scalar.assert_called_once()

    def test_has_press_release_with_source_url_returns_false_when_missing(
        self,
    ) -> None:
        """指定URLの既存行がない場合はFalseを返すこと"""

        session = Mock(spec=Session)
        session.scalar.return_value = None

        exists = has_press_release_with_source_url(
            session,
            SOURCE_URL_1,
        )

        self.assertFalse(exists)
        session.scalar.assert_called_once()

    def test_has_press_release_with_source_url_leaves_transaction_control_to_caller(
        self,
    ) -> None:
        """既存確認でもトランザクションの確定や取消を呼び出し元へ任せること"""

        session = Mock(spec=Session)
        session.scalar.return_value = None

        has_press_release_with_source_url(
            session,
            SOURCE_URL_1,
        )

        session.commit.assert_not_called()
        session.rollback.assert_not_called()

    def test_get_latest_press_release_published_at_returns_latest_date(
        self,
    ) -> None:
        """保存済み報道発表の最新公開日を返すこと"""

        session = Mock(spec=Session)
        session.scalar.return_value = date(2026, 7, 25)

        latest_published_at = get_latest_press_release_published_at(session)

        self.assertEqual(latest_published_at, date(2026, 7, 25))
        session.scalar.assert_called_once()
        statement = session.scalar.call_args.args[0]
        self.assertIn(
            "max(press_releases.published_at)",
            str(statement),
        )

    def test_list_press_release_source_urls_published_from_filters_by_date(
        self,
    ) -> None:
        """指定公開日以降のsource_urlを返すこと"""

        session = Mock(spec=Session)
        session.scalars.return_value = [SOURCE_URL_1]
        published_from = date(2026, 5, 1)

        source_urls = list_press_release_source_urls_published_from(
            session,
            published_from,
        )

        self.assertEqual(source_urls, (SOURCE_URL_1,))
        session.scalars.assert_called_once()
        statement = session.scalars.call_args.args[0]
        self.assertIn(
            "press_releases.published_at >=",
            str(statement),
        )
        self.assertIn(published_from, statement.compile().params.values())

    def test_count_press_releases_returns_total_items(self) -> None:
        """保存済み報道発表の総件数を返すこと"""

        session = Mock(spec=Session)
        session.scalar.return_value = 25

        total_items = count_press_releases(session)

        self.assertEqual(total_items, 25)
        session.scalar.assert_called_once()
        statement = session.scalar.call_args.args[0]
        self.assertIn("count(*)", str(statement))
        self.assertIn("FROM press_releases", str(statement))
        self.assertNotIn("WHERE", str(statement))

    def test_count_press_releases_filters_by_title_query(self) -> None:
        """タイトル検索をILIKEの部分一致条件として組み立てること"""

        session = Mock(spec=Session)
        session.scalar.return_value = 1

        total_items = count_press_releases(
            session,
            title_query="水質50%_/",
        )

        self.assertEqual(total_items, 1)
        statement = session.scalar.call_args.args[0]
        compiled_statement = statement.compile(dialect=postgresql.dialect())
        compiled_sql = str(compiled_statement)
        self.assertIn("ILIKE '%%' ||", compiled_sql)
        self.assertIn("|| '%%' ESCAPE '/'", compiled_sql)
        self.assertNotIn("水質50%_/", compiled_sql)
        self.assertIn("水質50/%/_//", compiled_statement.params.values())
        session.commit.assert_not_called()
        session.rollback.assert_not_called()

    def test_list_press_releases_applies_stable_order_limit_and_offset(
        self,
    ) -> None:
        """公開日とIDの降順、取得件数、読み飛ばし件数をSQLへ反映すること"""

        session = Mock(spec=Session)
        press_release = Mock(spec=PressRelease)
        session.scalars.return_value = [press_release]

        press_releases = list_press_releases(
            session,
            limit=20,
            offset=40,
        )

        self.assertEqual(press_releases, (press_release,))
        session.scalars.assert_called_once()
        statement = session.scalars.call_args.args[0]
        compiled_statement = str(
            statement.compile(compile_kwargs={"literal_binds": True})
        )
        self.assertIn(
            "ORDER BY press_releases.published_at DESC, "
            "press_releases.id DESC",
            compiled_statement,
        )
        self.assertIn("LIMIT 20", compiled_statement)
        self.assertIn("OFFSET 40", compiled_statement)
        self.assertNotIn("WHERE", compiled_statement)
        session.commit.assert_not_called()
        session.rollback.assert_not_called()

    def test_list_press_releases_filters_by_title_query(self) -> None:
        """タイトルのILIKE条件を新着順とページ条件へ組み合わせること"""

        session = Mock(spec=Session)
        press_release = Mock(spec=PressRelease)
        session.scalars.return_value = [press_release]

        press_releases = list_press_releases(
            session,
            limit=20,
            offset=40,
            title_query="水質50%_/",
        )

        self.assertEqual(press_releases, (press_release,))
        statement = session.scalars.call_args.args[0]
        compiled_statement = statement.compile(dialect=postgresql.dialect())
        compiled_sql = str(compiled_statement)
        self.assertIn("ILIKE '%%' ||", compiled_sql)
        self.assertIn("|| '%%' ESCAPE '/'", compiled_sql)
        self.assertNotIn("水質50%_/", compiled_sql)
        self.assertIn("水質50/%/_//", compiled_statement.params.values())
        self.assertIn(
            "ORDER BY press_releases.published_at DESC, "
            "press_releases.id DESC",
            compiled_sql,
        )
        compiled_literal_sql = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn("LIMIT 20", compiled_literal_sql)
        self.assertIn("OFFSET 40", compiled_literal_sql)
        session.commit.assert_not_called()
        session.rollback.assert_not_called()


def _press_release_create(
    title: str = "報道発表",
    source_url: str = SOURCE_URL_1,
    published_at: date = date(2026, 5, 26),
    source_categories: list[str] | None = None,
    fetched_at: datetime = datetime(2026, 5, 26, 10, 0, tzinfo=UTC),
) -> PressReleaseCreate:
    """報道発表保存DTOのテストデータを生成

    Args:
        title: 報道発表タイトル
        source_url: 報道発表詳細ページURL
        published_at: 報道発表日
        source_categories: 取得元カテゴリ
        fetched_at: 取得日時

    Returns:
        repositoryへ渡す報道発表保存DTO
    """

    return PressReleaseCreate(
        title=title,
        source_url=source_url,
        published_at=published_at,
        source_categories=source_categories,
        fetched_at=fetched_at,
    )


if __name__ == "__main__":
    unittest.main()

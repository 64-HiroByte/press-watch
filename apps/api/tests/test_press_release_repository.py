from __future__ import annotations

from datetime import UTC, date, datetime
import unittest
from unittest.mock import Mock

from press_watch_api.models.press_release import PressRelease
from press_watch_api.repositories.press_release import create_press_release
from press_watch_api.schemas.press_release import PressReleaseCreate


class PressReleaseRepositoryTest(unittest.TestCase):
    """報道発表repositoryの保存処理テスト"""

    def test_create_press_release_builds_model_from_create_dto(self) -> None:
        """保存DTOの値からPressReleaseモデルを組み立てること"""

        session = Mock()
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
        self.assertEqual(press_release.fetched_at, dto.fetched_at)

    def test_create_press_release_allows_null_source_categories(self) -> None:
        """取得元カテゴリがないDTOをNoneのままモデルへ写すこと"""

        session = Mock()
        dto = _press_release_create(source_categories=None)

        press_release = create_press_release(session, dto)

        self.assertIsNone(press_release.source_categories)

    def test_create_press_release_adds_and_flushes_model(self) -> None:
        """作成したモデルをセッションへ追加してflushすること"""

        session = Mock()
        dto = _press_release_create()

        press_release = create_press_release(session, dto)

        session.add.assert_called_once_with(press_release)
        session.flush.assert_called_once_with()


def _press_release_create(
    title: str = "報道発表",
    source_url: str = "https://www.env.go.jp/press/press_00001.html",
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

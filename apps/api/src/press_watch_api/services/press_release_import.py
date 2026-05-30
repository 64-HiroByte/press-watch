from __future__ import annotations

from collections.abc import Collection, Iterable
from datetime import UTC, date, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from press_watch_api.models.press_release import PressRelease as PressReleaseModel
from press_watch_api.repositories.press_release import create_press_release
from press_watch_api.schemas.press_release import PressReleaseCreate


class ScrapedPressRelease(Protocol):
    """scraper 取得結果として保存変換に必要な属性"""

    title: str
    published_at: date
    url: str
    source_categories: Collection[str]


def to_press_release_create(
    release: ScrapedPressRelease,
    fetched_at: datetime | None = None,
) -> PressReleaseCreate:
    """scraper 取得結果をDB保存用DTOへ変換

    Args:
        release: scraper が取得した報道発表
        fetched_at: 環境省ページからデータを取得した日時

    Returns:
        DB新規保存用の報道発表DTO
    """

    return PressReleaseCreate(
        title=release.title,
        source_url=release.url,
        published_at=release.published_at,
        source_categories=_source_categories_or_none(
            release.source_categories,
        ),
        fetched_at=fetched_at or datetime.now(UTC),
    )


def to_press_release_creates(
    releases: Iterable[ScrapedPressRelease],
    fetched_at: datetime | None = None,
) -> list[PressReleaseCreate]:
    """複数の scraper 取得結果をDB保存用DTOへ変換

    Args:
        releases: scraper が取得した報道発表の反復可能オブジェクト
        fetched_at: 環境省ページからデータを取得した日時

    Returns:
        DB新規保存用の報道発表DTOリスト
    """

    resolved_fetched_at = fetched_at or datetime.now(UTC)
    return [
        to_press_release_create(
            release,
            fetched_at=resolved_fetched_at,
        )
        for release in releases
    ]


def import_press_releases(
    session: Session,
    releases: Iterable[ScrapedPressRelease],
    fetched_at: datetime | None = None,
) -> list[PressReleaseModel]:
    """scraper 取得結果をDTO経由でrepositoryへ保存依頼

    repository と同じく commit / rollback は呼び出さず、
    呼び出し元のトランザクションに参加する。

    Args:
        session: 保存に使うSQLAlchemyセッション
        releases: scraper が取得した報道発表の反復可能オブジェクト
        fetched_at: 環境省ページからデータを取得した日時

    Returns:
        セッションへ追加してflush済みの報道発表DBモデルリスト
    """

    create_dtos = to_press_release_creates(
        releases,
        fetched_at=fetched_at,
    )

    return [
        create_press_release(
            session,
            create_dto,
        )
        for create_dto in create_dtos
    ]


def _source_categories_or_none(
    source_categories: Collection[str],
) -> list[str] | None:
    """保存方針に合わせて空カテゴリをNoneへ正規化

    Args:
        source_categories: scraper が取得した取得元カテゴリ

    Returns:
        カテゴリが1件以上ある場合は文字列リスト、空の場合はNone
    """

    if not source_categories:
        return None
    return list(source_categories)

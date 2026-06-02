from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from press_watch_api.models.press_release import PressRelease
from press_watch_api.schemas.press_release import PressReleaseCreate


def create_press_release(
    session: Session,
    data: PressReleaseCreate,
) -> PressRelease:
    """報道発表保存DTOからDBモデルを作成して保存待ちにする

    Args:
        session: 保存に使うSQLAlchemyセッション
        data: 報道発表の新規保存DTO

    Returns:
        セッションへ追加してflush済みの報道発表DBモデル
    """

    press_release = PressRelease(
        title=data.title,
        source_url=data.source_url,
        published_at=data.published_at,
        source_categories=(
            list(data.source_categories)
            if data.source_categories is not None
            else None
        ),
        fetched_at=data.fetched_at,
    )

    session.add(press_release)
    session.flush()

    return press_release


def has_press_release_with_source_url(
    session: Session,
    source_url: str,
) -> bool:
    """指定した取得元URLの報道発表が既に保存されているか確認する

    Args:
        session: 取得に使うSQLAlchemyセッション
        source_url: 報道発表詳細ページURL

    Returns:
        既存行がある場合はTrue、ない場合はFalse
    """

    statement = (
        select(PressRelease.id)
        .where(PressRelease.source_url == source_url)
        .limit(1)
    )

    return session.scalar(statement) is not None

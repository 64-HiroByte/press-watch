from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from press_watch_api.models.press_release import PressRelease
from press_watch_api.schemas.press_release import PressReleaseCreate


def count_press_releases(
    session: Session,
    *,
    title_query: str | None = None,
) -> int:
    """任意のタイトル検索条件に一致する報道発表の件数を取得

    Args:
        session: 件数取得に使うSQLAlchemyセッション
        title_query: タイトルの部分一致検索に使う文字列

    Returns:
        検索条件に一致する報道発表の総件数
    """

    statement = select(func.count()).select_from(PressRelease)
    if title_query is not None:
        statement = statement.where(
            PressRelease.title.icontains(title_query, autoescape=True)
        )
    return session.scalar(statement) or 0


def list_press_releases(
    session: Session,
    *,
    limit: int,
    offset: int,
    title_query: str | None = None,
) -> tuple[PressRelease, ...]:
    """任意のタイトル検索条件に一致する報道発表を新着順で一覧取得

    Args:
        session: 一覧取得に使うSQLAlchemyセッション
        limit: 取得する最大件数
        offset: 先頭から読み飛ばす件数
        title_query: タイトルの部分一致検索に使う文字列

    Returns:
        公開日とIDの降順で取得した報道発表
    """

    statement = select(PressRelease)
    if title_query is not None:
        statement = statement.where(
            PressRelease.title.icontains(title_query, autoescape=True)
        )

    statement = (
        statement.order_by(
            PressRelease.published_at.desc(),
            PressRelease.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return tuple(session.scalars(statement))


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


def get_latest_press_release_published_at(
    session: Session,
) -> date | None:
    """保存済み報道発表の最新公開日を取得

    Args:
        session: 取得に使うSQLAlchemyセッション

    Returns:
        最新の公開日、保存済み報道発表がない場合はNone
    """

    statement = select(func.max(PressRelease.published_at))
    return session.scalar(statement)


def list_press_release_source_urls_published_from(
    session: Session,
    published_from: date,
) -> tuple[str, ...]:
    """指定公開日以降の報道発表URLを一覧取得

    Args:
        session: 取得に使うSQLAlchemyセッション
        published_from: 取得対象に含める公開日の下限

    Returns:
        公開日が下限以降の `source_url` のタプル
    """

    statement = (
        select(PressRelease.source_url)
        .where(PressRelease.published_at >= published_from)
        .order_by(PressRelease.id)
    )
    return tuple(session.scalars(statement))

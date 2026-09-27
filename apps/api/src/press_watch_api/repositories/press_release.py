from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from press_watch_api.models.fixed_category import (
    FixedCategory,
    PressReleaseFixedCategory,
)
from press_watch_api.models.press_release import PressRelease
from press_watch_api.schemas.press_release import PressReleaseCreate


def list_press_release_titles_after_id(
    session: Session,
    *,
    after_id: int | None,
    limit: int,
) -> tuple[tuple[int, str], ...]:
    """再分類用のIDとタイトルを、前回の最終IDに続けて取得

    Args:
        session: 呼び出し元が管理するSession
        after_id: 前回取得した最終ID。初回はNone
        limit: 取得する最大件数

    Returns:
        ID昇順の（報道発表ID, 原本タイトル）の組
    """

    statement = (
        select(PressRelease.id, PressRelease.title)
        .order_by(PressRelease.id)
        .limit(limit)
    )
    if after_id is not None:
        statement = statement.where(PressRelease.id > after_id)
    return tuple(
        (release_id, title) for release_id, title in session.execute(statement)
    )


def count_press_releases(
    session: Session,
    *,
    title_query: str | None = None,
    fixed_category_slugs: tuple[str, ...] = (),
) -> int:
    """タイトルと固定カテゴリの条件に一致する報道発表の件数を取得

    カテゴリは保存済み分類へOR条件で照合し、タイトル条件とはANDで組み合わせる。
    入力の検証・空白処理は呼び出し元に委ね、DB例外はそのまま伝える。

    Args:
        session: 件数取得に使うSQLAlchemyセッション
        title_query: 前処理済みのタイトル検索語。Noneの場合は検索しない
        fixed_category_slugs: OR条件で照合するslug。空の場合は絞り込まない

    Returns:
        複数カテゴリに一致した行も1件として数えた総件数。一致なしは0
    """

    statement = (
        select(func.count())
        .select_from(PressRelease)
        .where(
            *_press_release_filter_conditions(
                title_query, fixed_category_slugs
            )
        )
    )
    return session.scalar(statement) or 0


def list_press_releases(
    session: Session,
    *,
    limit: int,
    offset: int,
    title_query: str | None = None,
    fixed_category_slugs: tuple[str, ...] = (),
) -> tuple[PressRelease, ...]:
    """タイトルと固定カテゴリの条件に一致する報道発表を新着順で一覧取得

    カテゴリは保存済み分類へOR条件で照合し、タイトル条件とはANDで組み合わせる。
    入力の検証・空白処理は呼び出し元に委ね、DB例外はそのまま伝える。

    Args:
        session: 一覧取得に使うSQLAlchemyセッション
        limit: 取得する最大件数
        offset: 先頭から読み飛ばす件数
        title_query: 前処理済みのタイトル検索語。Noneの場合は検索しない
        fixed_category_slugs: OR条件で照合するslug。空の場合は絞り込まない

    Returns:
        公開日とIDの降順に並ぶ、重複のない報道発表
        一致なし、またはoffsetが一致件数以上の場合は空のタプル
    """

    statement = (
        select(PressRelease)
        .where(
            *_press_release_filter_conditions(
                title_query, fixed_category_slugs
            )
        )
        .order_by(
            PressRelease.published_at.desc(),
            PressRelease.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return tuple(session.scalars(statement))


def _press_release_filter_conditions(
    title_query: str | None,
    fixed_category_slugs: tuple[str, ...],
) -> tuple[ColumnElement[bool], ...]:
    """件数と一覧に共通する、報道発表単位の絞り込み条件を生成

    Args:
        title_query: Noneでない場合に文字として部分一致させる検索語
        fixed_category_slugs: 保存済み分類へOR条件で照合するslug列

    Returns:
        呼び出し元のwhereへAND条件として渡すSQL式のタプル
        両条件が未指定の場合は空のタプル
    """

    conditions: list[ColumnElement[bool]] = []
    if title_query is not None:
        conditions.append(
            PressRelease.title.icontains(title_query, autoescape=True)
        )
    if fixed_category_slugs:
        # 複数カテゴリに一致しても、外側の報道発表行を増やさない。
        conditions.append(
            select(1)
            .select_from(PressReleaseFixedCategory)
            .join(
                FixedCategory,
                (
                    FixedCategory.id
                    == PressReleaseFixedCategory.fixed_category_id
                ),
            )
            .where(
                PressReleaseFixedCategory.press_release_id == PressRelease.id,
                FixedCategory.slug.in_(fixed_category_slugs),
            )
            .exists()
        )
    return tuple(conditions)


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


def create_press_releases(
    session: Session,
    data: Sequence[PressReleaseCreate],
) -> tuple[PressRelease, ...]:
    """複数の報道発表DTOを重複時にskipして一括保存

    Args:
        session: 保存に使うSQLAlchemyセッション
        data: 報道発表の新規保存DTO列

    Returns:
        実際にINSERTされた報道発表DBモデル
    """

    if not data:
        return ()

    values = [
        {
            "title": create_data.title,
            "source_url": create_data.source_url,
            "published_at": create_data.published_at,
            "source_categories": (
                list(create_data.source_categories)
                if create_data.source_categories is not None
                else None
            ),
            "fetched_at": create_data.fetched_at,
        }
        for create_data in data
    ]
    statement = (
        insert(PressRelease)
        .values(values)
        .on_conflict_do_nothing(
            index_elements=[PressRelease.source_url],
        )
        .returning(PressRelease)
    )

    return tuple(session.scalars(statement))


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

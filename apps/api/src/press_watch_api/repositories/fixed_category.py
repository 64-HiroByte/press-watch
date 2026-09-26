"""固定カテゴリ定義と分類結果のDB操作

commit・rollback・Sessionのcloseは呼び出し元に委ねる。
"""

from collections.abc import Sequence
from itertools import batched

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from press_watch_api.models.fixed_category import (
    FixedCategory,
    FixedCategoryKeyword,
    PressReleaseFixedCategory,
)


_CLASSIFICATION_BATCH_SIZE = 1_000


def delete_press_release_fixed_categories(
    session: Session,
    release_ids: Sequence[int],
) -> None:
    """指定した報道発表IDの分類結果だけを削除

    Args:
        session: 呼び出し元が管理するSession
        release_ids: 分類結果を削除する報道発表ID
    """

    if not release_ids:
        return
    session.execute(
        delete(PressReleaseFixedCategory.__table__).where(
            PressReleaseFixedCategory.press_release_id.in_(release_ids)
        )
    )


def list_fixed_categories(session: Session) -> tuple[FixedCategory, ...]:
    """既存の固定カテゴリをすべて取得"""

    return tuple(session.scalars(select(FixedCategory)))


def create_press_release_fixed_categories(
    session: Session,
    values: Sequence[tuple[int, int]],
) -> None:
    """報道発表IDと固定カテゴリIDの対応を1,000組ずつ一括保存

    Args:
        session: 呼び出し元が管理するSession
        values: 重複のない（報道発表ID, 固定カテゴリID）の組
    """

    for batch in batched(values, _CLASSIFICATION_BATCH_SIZE):
        session.execute(
            insert(PressReleaseFixedCategory).values(
                [
                    {
                        "press_release_id": release_id,
                        "fixed_category_id": category_id,
                    }
                    for release_id, category_id in batch
                ]
            )
        )


def list_fixed_category_keywords(
    session: Session,
) -> tuple[FixedCategoryKeyword, ...]:
    """既存のカテゴリ別キーワードをすべて取得"""

    return tuple(session.scalars(select(FixedCategoryKeyword)))


def create_fixed_categories(
    session: Session,
    values: Sequence[tuple[str, str, int]],
) -> tuple[FixedCategory, ...]:
    """slug・表示名・表示順からカテゴリを追加し、採番済みモデルを返す

    Args:
        session: 呼び出し元が管理するSession
        values: （slug, 表示名, 表示順）の組

    Returns:
        入力順のカテゴリモデル。IDはflushで取得済みだが、登録は未commit
    """

    categories = tuple(
        FixedCategory(slug=slug, name=name, display_order=order)
        for slug, name, order in values
    )
    if categories:
        session.add_all(categories)
        session.flush()
    return categories


def create_fixed_category_keywords(
    session: Session,
    values: Sequence[tuple[int, str]],
) -> None:
    """カテゴリIDとキーワードの対応を追加

    Args:
        session: 呼び出し元が管理するSession
        values: （採番済みカテゴリID, キーワード）の組
    """

    if values:
        session.add_all(
            [
                FixedCategoryKeyword(
                    fixed_category_id=category_id, keyword=keyword
                )
                for category_id, keyword in values
            ]
        )
        session.flush()

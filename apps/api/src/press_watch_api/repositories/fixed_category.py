"""固定カテゴリ初期データのDB操作"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from press_watch_api.models.fixed_category import FixedCategory, FixedCategoryKeyword


def list_fixed_categories(session: Session) -> tuple[FixedCategory, ...]:
    """既存の固定カテゴリをすべて取得"""

    return tuple(session.scalars(select(FixedCategory)))


def list_fixed_category_keywords(session: Session) -> tuple[FixedCategoryKeyword, ...]:
    """既存のカテゴリ別キーワードをすべて取得"""

    return tuple(session.scalars(select(FixedCategoryKeyword)))


def create_fixed_categories(
    session: Session,
    values: Sequence[tuple[str, str, int]],
) -> tuple[FixedCategory, ...]:
    """slug・表示名・表示順からカテゴリを追加し、採番済みモデルを返す"""

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
    """カテゴリIDとキーワードの対応を追加"""

    if values:
        session.add_all([
            FixedCategoryKeyword(fixed_category_id=category_id, keyword=keyword)
            for category_id, keyword in values
        ])
        session.flush()

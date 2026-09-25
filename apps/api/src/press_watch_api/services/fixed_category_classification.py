"""固定カテゴリのルール検証とタイトル分類"""

from collections.abc import Iterable
import unicodedata

from sqlalchemy.orm import Session

from press_watch_api.repositories import fixed_category as repository
from press_watch_api.services.fixed_category_seed import (
    FixedCategoryCsvError,
    load_fixed_category_seed,
)


type FixedCategoryRules = tuple[tuple[int, str], ...]


class FixedCategoryClassificationError(ValueError):
    """固定文言だけで分類ルールの不備を伝える例外"""


def load_fixed_category_rules(session: Session) -> FixedCategoryRules:
    """同梱CSVとDBの完全一致を確認し、実IDと正規化済みキーワードを取得

    Args:
        session: 呼び出し元がcommit・rollback・closeを管理するSession

    Returns:
        DBのカテゴリIDと分類専用キーワードの組

    Raises:
        FixedCategoryClassificationError: CSVが読めない、またはDBの定義が一致しない場合
    """

    try:
        expected = load_fixed_category_seed()
    except (OSError, FixedCategoryCsvError):
        raise FixedCategoryClassificationError("fixed category CSV could not be loaded") from None
    categories = repository.list_fixed_categories(session)
    keywords = repository.list_fixed_category_keywords(session)
    if not categories or not keywords:
        raise FixedCategoryClassificationError("fixed category definitions are not ready")
    actual_categories = {(item.slug, item.name, item.display_order) for item in categories}
    expected_categories = {
        (item.slug, item.name, item.display_order) for item in expected.categories
    }
    if actual_categories != expected_categories:
        raise FixedCategoryClassificationError("fixed category definitions do not match bundled CSV")
    slugs_by_id = {item.id: item.slug for item in categories}
    actual_keywords = {
        (slugs_by_id.get(item.fixed_category_id), item.keyword) for item in keywords
    }
    if actual_keywords != set(expected.keywords):
        raise FixedCategoryClassificationError("fixed category definitions do not match bundled CSV")
    return prepare_fixed_category_rules((item.fixed_category_id, item.keyword) for item in keywords)


def prepare_fixed_category_rules(values: Iterable[tuple[int, str]]) -> FixedCategoryRules:
    """検証済みのカテゴリID・キーワードから、分類専用の正規化値を準備

    Args:
        values: 定義検証を終えた（DBのカテゴリID, キーワード）の組

    Returns:
        NFKCとcasefoldを適用済みのキーワードと実IDの組
    """

    return tuple(sorted(
        (category_id, unicodedata.normalize("NFKC", keyword).casefold())
        for category_id, keyword in values
    ))


def classify_title(title: str, rules: FixedCategoryRules) -> tuple[int, ...]:
    """準備済みルールにタイトルが一致するカテゴリIDを重複なく返す

    Args:
        title: 原本タイトル。分類用の正規化はこの関数内だけで使用
        rules: prepare_fixed_category_rulesで準備したルール

    Returns:
        一致したカテゴリIDの昇順タプル。一致なしの場合は空タプル
    """

    normalized_title = unicodedata.normalize("NFKC", title).casefold()
    return tuple(sorted({
        category_id for category_id, keyword in rules if keyword in normalized_title
    }))

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from press_watch_api.dependencies import get_db_session
from press_watch_api.http_errors import database_error_responses
from press_watch_api.repositories.fixed_category import list_fixed_categories
from press_watch_api.schemas.fixed_category import (
    FixedCategoryListItem,
    FixedCategoryListResponse,
)


router = APIRouter(prefix="/fixed-categories", tags=["fixed-categories"])


@router.get(
    "",
    responses=database_error_responses(),
)
def read_fixed_categories(
    session: Annotated[Session, Depends(get_db_session, scope="function")],
) -> FixedCategoryListResponse:
    """保存済み固定カテゴリの選択肢を表示順で取得

    Sessionの生成・終了とDBエラー応答は既存の共通処理に委ねる。

    Args:
        session: 定義取得に使うリクエスト単位のDB Session

    Returns:
        slug・表示名・表示順の一覧。定義が未登録の場合は空のitems
    """

    return FixedCategoryListResponse(
        items=[
            FixedCategoryListItem.model_validate(category)
            for category in list_fixed_categories(session)
        ],
    )

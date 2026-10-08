from pydantic import BaseModel, ConfigDict


class FixedCategoryListItem(BaseModel):
    """固定カテゴリの選択肢として公開する保存済み定義"""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    slug: str
    name: str
    display_order: int


class FixedCategoryListResponse(BaseModel):
    """固定カテゴリ選択肢APIのレスポンス"""

    model_config = ConfigDict(frozen=True)

    items: list[FixedCategoryListItem]

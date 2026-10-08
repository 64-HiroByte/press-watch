from pydantic import BaseModel, ConfigDict


class FixedCategoryMembershipItem(BaseModel):
    """記事の保存済み所属として公開する固定カテゴリの識別子と表示名

    Attributes:
        slug: 数値IDに代わるカテゴリの公開識別子
        name: 保存済みカテゴリ定義の表示名
    """

    model_config = ConfigDict(from_attributes=True, frozen=True)

    slug: str
    name: str


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

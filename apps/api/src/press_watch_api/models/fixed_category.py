from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from press_watch_api.models.base import Base


class FixedCategory(Base):
    """PressWatch独自の固定カテゴリ定義を保存するDBモデル"""

    __tablename__ = "fixed_categories"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_fixed_categories_slug"),
        UniqueConstraint("name", name="uq_fixed_categories_name"),
        UniqueConstraint(
            "display_order",
            name="uq_fixed_categories_display_order",
        ),
        CheckConstraint(
            "display_order > 0",
            name="ck_fixed_categories_display_order_positive",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class FixedCategoryKeyword(Base):
    """固定カテゴリごとの判定キーワードを保存するDBモデル"""

    __tablename__ = "fixed_category_keywords"

    fixed_category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixed_categories.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    keyword: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        nullable=False,
    )


class PressReleaseFixedCategory(Base):
    """報道発表へ付与した固定カテゴリを保存するDBモデル"""

    __tablename__ = "press_release_fixed_categories"
    __table_args__ = (
        Index(
            "ix_press_release_fixed_categories_fixed_category_id",
            "fixed_category_id",
        ),
    )

    press_release_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("press_releases.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    fixed_category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixed_categories.id", ondelete="RESTRICT"),
        primary_key=True,
        nullable=False,
    )

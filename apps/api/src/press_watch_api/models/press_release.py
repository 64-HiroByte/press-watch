from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from press_watch_api.models.base import Base


class PressRelease(Base):
    """環境省の報道発表を原本に近い形で保存するDBモデル"""

    __tablename__ = "press_releases"
    __table_args__ = (
        UniqueConstraint("source_url", name="uq_press_releases_source_url"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[date] = mapped_column(Date, nullable=False)
    source_categories: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text),
        nullable=True,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

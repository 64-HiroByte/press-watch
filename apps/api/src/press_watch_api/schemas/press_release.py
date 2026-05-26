from __future__ import annotations

from datetime import UTC, date, datetime

from pydantic import BaseModel, ConfigDict, field_validator


class PressReleaseCreate(BaseModel):
    """報道発表をDBへ新規保存するためのDTO"""

    model_config = ConfigDict(frozen=True)

    title: str
    source_url: str
    published_at: date
    source_categories: list[str] | None
    fetched_at: datetime

    @field_validator("title", "source_url")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        """必須文字列の前後空白を除去

        Args:
            value: 検証対象の文字列

        Returns:
            前後空白を除去した文字列

        Raises:
            ValueError: 空文字列の場合
        """

        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError("must not be empty")
        return stripped_value

    @field_validator("source_categories")
    @classmethod
    def _normalize_source_categories(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        """取得元カテゴリの空配列をNULL相当に正規化

        Args:
            value: 取得元ページに表示されたカテゴリ一覧

        Returns:
            カテゴリが1件以上ある場合は文字列リスト、空の場合はNone
        """

        if not value:
            return None
        return value

    @field_validator("fetched_at")
    @classmethod
    def _normalize_fetched_at_to_utc(cls, value: datetime) -> datetime:
        """取得日時をtimezone awareなUTCへ正規化

        Args:
            value: 環境省ページからデータを取得した日時

        Returns:
            UTCへ変換した取得日時

        Raises:
            ValueError: timezone naiveな日時の場合
        """

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("fetched_at must be timezone aware")
        return value.astimezone(UTC)

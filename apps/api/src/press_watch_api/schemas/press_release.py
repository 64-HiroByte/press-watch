from __future__ import annotations

from datetime import UTC, date, datetime
import re
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, field_validator


HTTP_URL_SCHEMES = frozenset({"http", "https"})
UNSAFE_ASCII_URL_CHARACTERS = frozenset('<>"\\^`{|}')
INVALID_PERCENT_ESCAPE_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


class PressReleaseCreate(BaseModel):
    """報道発表をDBへ新規保存するためのDTO"""

    model_config = ConfigDict(frozen=True)

    title: str
    source_url: str
    published_at: date
    source_categories: list[str] | None
    fetched_at: datetime

    @field_validator("title")
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

    @field_validator("source_url")
    @classmethod
    def _validate_source_url(cls, value: str) -> str:
        """取得元URLをDB保存可能なASCII URIとして検証

        Args:
            value: 検証対象の取得元URL

        Returns:
            前後空白を除去したHTTPまたはHTTPS URL

        Raises:
            ValueError: URLが空または保存対象のURI形式でない場合
        """

        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError("must not be empty")
        invalid_reason = _invalid_http_url_reason(stripped_value)
        if invalid_reason is not None:
            raise ValueError(
                f"source_url validation failed: {invalid_reason}"
            )
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


def _invalid_http_url_reason(value: str) -> str | None:
    """DB保存可能なASCII HTTP(S) URLでない理由を判定

    Args:
        value: 検証対象のURL

    Returns:
        保存条件を満たさない固定理由コード、有効な場合はNone
    """

    if not value.isascii():
        return "non_ascii_character"
    if any(
        character.isspace()
        or ord(character) < 0x20
        or ord(character) == 0x7F
        or character in UNSAFE_ASCII_URL_CHARACTERS
        for character in value
    ):
        return "unsafe_character"
    if INVALID_PERCENT_ESCAPE_RE.search(value) is not None:
        return "invalid_percent_escape"

    try:
        parsed_url = urlsplit(value)
        _ = parsed_url.port
    except ValueError:
        return "invalid_host_or_port"

    if parsed_url.scheme.lower() not in HTTP_URL_SCHEMES:
        return "unsupported_scheme"
    if parsed_url.username is not None or parsed_url.password is not None:
        return "credentials_not_allowed"
    if parsed_url.hostname is None or "%" in parsed_url.netloc:
        return "invalid_host_or_port"
    return None

"""固定カテゴリのCSV検証と初期データ取込"""

import csv
from dataclasses import dataclass
import io
from pathlib import Path
import re
import unicodedata

from sqlalchemy.orm import Session

from press_watch_api.repositories import fixed_category as repository

_CATEGORIES_FILE = "fixed_categories.csv"
_KEYWORDS_FILE = "fixed_category_keywords.csv"


class FixedCategoryCsvError(ValueError):
    """固定カテゴリCSVの規約違反

    CLI診断へ渡すため、入力値や元例外の詳細を各属性へ含めない前提。

    Attributes:
        file_name: 同梱CSVの固定ファイル名
        reason: 検証処理が選んだ固定の理由
        line: 1始まりの物理行番号。位置を特定しない場合はNone
        column: 規約で定義した列名。列を特定しない場合はNone
    """

    def __init__(
        self,
        file_name: str,
        reason: str,
        *,
        line: int | None = None,
        column: str | None = None,
    ) -> None:
        self.file_name = file_name
        self.line = line
        self.column = column
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class FixedCategoryDefinition:
    """CSVから読み取った固定カテゴリ定義"""

    slug: str
    name: str
    display_order: int


@dataclass(frozen=True)
class FixedCategorySeedData:
    """取込対象のカテゴリ定義とslug単位のキーワード対応

    Attributes:
        categories: CSV行順のカテゴリ定義
        keywords: CSV行順の（カテゴリslug, キーワード）組。DBのカテゴリIDは保持しない
    """

    categories: tuple[FixedCategoryDefinition, ...]
    keywords: tuple[tuple[str, str], ...]


class FixedCategorySeedConflictError(ValueError):
    """既存DBとCSVの定義不一致"""


@dataclass(frozen=True)
class FixedCategorySeedResult:
    """初期データ取込で追加した行数"""

    categories_added: int
    keywords_added: int


def seed_fixed_categories(
    session: Session,
    data: FixedCategorySeedData,
) -> FixedCategorySeedResult:
    """既存データを照合し、呼び出し元のトランザクションへ不足分を追加

    Args:
        session: 呼び出し元がcommit・rollback・closeを管理するSession
        data: 両CSVの検証を完了した取込データ

    Returns:
        commit前のカテゴリ・キーワード追加件数

    Raises:
        FixedCategorySeedConflictError: CSVにないデータや同一slugの定義相違がある場合
    """

    expected_categories = {category.slug: category for category in data.categories}
    existing_categories = repository.list_fixed_categories(session)
    existing_keywords = repository.list_fixed_category_keywords(session)
    # 後半のキーワードに不整合があっても書き込まないよう、両テーブルを先に照合する。
    for category in existing_categories:
        expected = expected_categories.get(category.slug)
        if expected is None or (category.name, category.display_order) != (
            expected.name, expected.display_order,
        ):
            raise FixedCategorySeedConflictError("category definition mismatch")

    slugs_by_id = {category.id: category.slug for category in existing_categories}
    expected_keywords = set(data.keywords)
    known_keywords: set[tuple[str, str]] = set()
    for keyword in existing_keywords:
        slug = slugs_by_id.get(keyword.fixed_category_id)
        if slug is None or (slug, keyword.keyword) not in expected_keywords:
            raise FixedCategorySeedConflictError("keyword definition mismatch")
        known_keywords.add((slug, keyword.keyword))

    ids_by_slug = {category.slug: category.id for category in existing_categories}
    missing_categories = [
        (category.slug, category.name, category.display_order)
        for category in data.categories
        if category.slug not in ids_by_slug
    ]
    if missing_categories:
        created = repository.create_fixed_categories(session, missing_categories)
        ids_by_slug.update((category.slug, category.id) for category in created)
    missing_keywords = [
        (ids_by_slug[slug], keyword)
        for slug, keyword in data.keywords
        if (slug, keyword) not in known_keywords
    ]
    if missing_keywords:
        repository.create_fixed_category_keywords(session, missing_keywords)
    return FixedCategorySeedResult(len(missing_categories), len(missing_keywords))


def load_fixed_category_seed() -> FixedCategorySeedData:
    """パッケージ位置を基準に同梱CSVを読み込み、検証済みの初期データを返す

    カレントディレクトリに依存せず、DB設定の読込みやSession生成も行わない。
    """

    data_directory = Path(__file__).resolve().parents[1] / "data"
    return parse_fixed_category_csv(
        (data_directory / _CATEGORIES_FILE).read_bytes(),
        (data_directory / _KEYWORDS_FILE).read_bytes(),
    )


def parse_fixed_category_csv(
    categories_csv: bytes,
    keywords_csv: bytes,
) -> FixedCategorySeedData:
    """両CSVを検証し、DBに依存しない取込データへ変換

    Args:
        categories_csv: カテゴリ定義CSVのバイト列
        keywords_csv: キーワードCSVのバイト列

    Returns:
        検証済みのカテゴリ定義とキーワード対応

    Raises:
        FixedCategoryCsvError: CSVが取込規約を満たさない場合
    """

    category_rows = _read_rows(
        categories_csv, _CATEGORIES_FILE, ("slug", "name", "display_order"),
    )
    keyword_rows = _read_rows(
        keywords_csv, _KEYWORDS_FILE, ("category_slug", "keyword"),
    )
    categories: list[FixedCategoryDefinition] = []
    slugs: set[str] = set()
    names: set[str] = set()
    orders: set[int] = set()
    for line, (slug, name, raw_order) in category_rows:
        if re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", slug) is None:
            raise FixedCategoryCsvError(
                _CATEGORIES_FILE, "invalid slug", line=line, column="slug",
            )
        # 先頭の0を除いた桁数を先に調べ、巨大な値でint変換自体が失敗するのを防ぐ。
        digits = raw_order.lstrip("0")
        if (
            re.fullmatch(r"[0-9]+", raw_order) is None
            or not digits
            or len(digits) > 10
            or int(digits) > 2_147_483_647
        ):
            raise FixedCategoryCsvError(
                _CATEGORIES_FILE, "invalid positive integer", line=line,
                column="display_order",
            )
        order = int(digits)
        for duplicate, column in (
            (slug in slugs, "slug"), (name in names, "name"),
            (order in orders, "display_order"),
        ):
            if duplicate:
                raise FixedCategoryCsvError(
                    _CATEGORIES_FILE, "duplicate value", line=line, column=column,
                )
        slugs.add(slug)
        names.add(name)
        orders.add(order)
        categories.append(FixedCategoryDefinition(slug, name, order))

    keywords: list[tuple[str, str]] = []
    seen_keywords: set[tuple[str, str]] = set()
    for line, (slug, keyword) in keyword_rows:
        if slug not in slugs:
            raise FixedCategoryCsvError(
                _KEYWORDS_FILE, "undefined category", line=line, column="category_slug",
            )
        pair = (slug, keyword)
        if pair in seen_keywords:
            raise FixedCategoryCsvError(
                _KEYWORDS_FILE, "duplicate keyword assignment", line=line, column="keyword",
            )
        seen_keywords.add(pair)
        keywords.append(pair)
    return FixedCategorySeedData(tuple(categories), tuple(keywords))


def _read_rows(
    raw: bytes,
    file_name: str,
    header: tuple[str, ...],
) -> list[tuple[int, list[str]]]:
    """列固有の検証に先立ち、バイト列・CSV構造・文字列の共通規約を検証

    Args:
        raw: 改行変換をしていないCSVのバイト列
        file_name: 診断に使う同梱CSVの固定ファイル名
        header: 列順も含めた期待するヘッダー

    Returns:
        ヘッダーを除く各レコードの（開始物理行番号, 列値一覧）。行番号は1始まり
    """

    if raw.startswith(b"\xef\xbb\xbf"):
        raise FixedCategoryCsvError(file_name, "UTF-8 BOM is not allowed")
    if b"\r" in raw:
        raise FixedCategoryCsvError(file_name, "only LF line endings are allowed")
    if not raw.endswith(b"\n"):
        raise FixedCategoryCsvError(file_name, "final LF is required")
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise FixedCategoryCsvError(file_name, "invalid UTF-8") from None
    _validate_csv_quotes(decoded, file_name)
    reader = csv.reader(io.StringIO(decoded), strict=True)
    rows: list[tuple[int, list[str]]] = []
    try:
        if next(reader, None) != list(header):
            raise FixedCategoryCsvError(file_name, "header mismatch", line=1)
        while True:
            line = reader.line_num + 1
            row = next(reader, None)
            if row is None:
                break
            if len(row) != len(header):
                raise FixedCategoryCsvError(file_name, "column count mismatch", line=line)
            for column, value in zip(header, row, strict=True):
                _validate_text(value, file_name, line, column)
            rows.append((line, row))
    except csv.Error:
        raise FixedCategoryCsvError(
            file_name, "invalid CSV syntax", line=reader.line_num,
        ) from None
    if not rows:
        raise FixedCategoryCsvError(file_name, "no data rows")
    return rows


def _validate_csv_quotes(decoded: str, file_name: str) -> None:
    """csv.readerのstrict指定だけでは拒否できない引用符配置を検証

    未引用フィールド内の引用符や、閉じ引用符の直後に続く通常文字を拒否する。
    閉じ忘れは後続のcsv.reader、引用内の改行は値の文字列検証で拒否する。
    """

    state = "start"
    line = 1
    for character in decoded:
        if state == "quoted":
            if character == '"':
                state = "after_quote"
        elif character in ",\n":
            state = "start"
        elif character == '"':
            if state == "unquoted":
                raise FixedCategoryCsvError(file_name, "invalid CSV syntax", line=line)
            # after_quoteで再び引用符が来た場合は、二重引用符によるエスケープ。
            state = "quoted"
        else:
            if state == "after_quote":
                raise FixedCategoryCsvError(file_name, "invalid CSV syntax", line=line)
            state = "unquoted"
        if character == "\n":
            line += 1


def _validate_text(value: str, file_name: str, line: int, column: str) -> None:
    """全列共通の文字列規約を、入力値を補正せずに検証

    stripやNFKC変換は適合判定にだけ使い、違反時は位置と固定の理由で例外を送出する。
    """

    reason: str | None = None
    if not value:
        reason = "empty value"
    elif value != value.strip():
        reason = "surrounding whitespace is not allowed"
    elif any(unicodedata.category(character) == "Cc" for character in value):
        reason = "control character is not allowed"
    elif unicodedata.normalize("NFKC", value) != value:
        reason = "NFKC normal form is required"
    if reason is not None:
        raise FixedCategoryCsvError(file_name, reason, line=line, column=column)

"""スクレイパーの診断値に含まれるURL認証情報の伏字処理"""

import re


# URL拒否診断の引用付き項目を分離し、タイトルの@を認証情報へ巻き込まない。
# 任意の引用符では区切らず、引用符を含む不正な認証部分も保護する。
_QUOTED_VALUE_PATTERN = r'''(?:'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")'''
_QUOTED_URL_PATTERN = (
    r'''(?:'(?:https?://|//)(?:\\.|[^'\\])*'|"(?:https?://|//)(?:\\.|[^"\\])*")'''
)
_VALIDATION_PREFIX_PATTERN = (
    r'invalid (?:press release|archive month) URL: validation=[a-z_]+ '
)
_VALIDATION_DIAGNOSTIC_PATTERN = (
    rf'{_VALIDATION_PREFIX_PATTERN}page_url={_QUOTED_URL_PATTERN} '
    rf'(?:title={_QUOTED_VALUE_PATTERN}|archive_month=[0-9]{{4}}-[0-9]{{2}}) '
    rf'href={_QUOTED_VALUE_PATTERN}'
)
_DIAGNOSTIC_FIELD_RE = re.compile(
    rf'(?:page_url|title|href)={_QUOTED_VALUE_PATTERN}', re.IGNORECASE
)
# URL候補の開始と後続URLの境界で、同じ開始条件を使う。
_RELATIVE_URL_START_DELIMITERS = r"""'"=:(\[{"""
_RELATIVE_URL_START_PATTERN = rf'(?<![^\s{_RELATIVE_URL_START_DELIMITERS}])//'
# 項目名の書式を限定せず、空白後の値から始まるURLを先行URLのパスへ取り込まない。
# 空白とURLの各部分の区切りを越えず、開始条件を満たす//までを調べる。
# 空白列の先頭だけで調べ、長い空白や複数の単語を繰り返し走査しない。
_RELATIVE_URL_BOUNDARY_PATTERN = (
    rf'(?<!\s)\s+[^\s/?#]*{_RELATIVE_URL_START_PATTERN}'
)
# authorityは空白でも打ち切らず、パス・クエリ・fragment・次のURLで区切る。
# スキーム相対URLは値の先頭か区切りに続くものだけとし、パス中の//と区別する。
# パス以降は引用符でも打ち切らず保持し、その中の//を認証部分として読み直さない。
_URL_AUTHORITY_RE = re.compile(
    rf'(https?://|{_RELATIVE_URL_START_PATTERN})'
    rf'((?:(?!https?://|{_VALIDATION_DIAGNOSTIC_PATTERN}'
    rf'|{_RELATIVE_URL_BOUNDARY_PATTERN})[^/?#])*)'
    r'((?:(?<!\s)/|[?#])(?:(?!https?://)\S)*|)',
    re.IGNORECASE,
)
# JSON・配列・タプルの引用付き値を、説明文の有無によらず先に分離する。
# URL自身のパスに含まれる引用符は、先に始まるURL候補へ保持する。
# 終端も値の境界とし、配列や項目に包まれない引用付き文字列も分離する。
_QUOTED_VALUE_TOKEN_PATTERN = (
    rf'(?<![^\s\[\({{,:]){_QUOTED_VALUE_PATTERN}(?=\s*(?:[:,}}\]\)]|$))'
)
_URL_TOKEN_PATTERN = (
    f'{_URL_AUTHORITY_RE.pattern}|(?P<quoted_value>{_QUOTED_VALUE_TOKEN_PATTERN})'
)
_DIAGNOSTIC_TOKEN_RE = re.compile(
    f'{_VALIDATION_DIAGNOSTIC_PATTERN}|{_URL_TOKEN_PATTERN}',
    re.IGNORECASE,
)


def _unquote_diagnostic_value(
    value: str, positions: list[int]
) -> tuple[str, list[int]]:
    """引用付きの値を一段読み、元の文字列への対応位置を保持

    引用符とバックスラッシュのエスケープだけを解釈する。
    置換時は元の表記を使うため、認証部分以外のエスケープを変更しない。

    Args:
        value: 正規表現で切り出した、外側の引用符を含む項目値
        positions: 各文字に対応する元の診断文字列の開始位置

    Returns:
        外側の引用符を除いた値と、読み取った各文字に対応する元の位置
    """

    characters: list[str] = []
    decoded_positions: list[int] = []
    index = 1
    while index < len(value) - 1:
        decoded_positions.append(positions[index])
        if value[index] == "\\" and value[index + 1] in ("\\", '"', "'"):
            characters.append(value[index + 1])
            index += 2
        else:
            characters.append(value[index])
            index += 1
    return ''.join(characters), decoded_positions


def redact_url_credentials(value: str) -> str:
    """診断文字列内の絶対URL・スキーム相対URLの認証部分を伏字へ置換

    空白・制御文字・@を含む拒否対象の認証部分も、最後の@まで置換する。
    パス・クエリ・fragment内の@と、別のURL候補は認証部分へ含めない。
    URL拒否診断は引用付きの値ごとに処理し、取得元とタイトルなどを分離する。
    JSON・配列・タプルの引用付き値は、説明文付きの値や内側の構造も順に処理する。
    引用符とバックスラッシュのエスケープを読み、元の認証部分だけを置き換える。
    再帰呼び出しは使わず、正常URL・診断項目・引用符の表記を保持する。

    Args:
        value: エラー理由や進捗として表示・保存する文字列

    Returns:
        URLの認証部分を[redacted]へ置き換えた文字列
    """

    pending = [(value, list(range(len(value))))]
    replacements: list[tuple[int, int]] = []
    while pending:
        current_value, positions = pending.pop()
        for match in _DIAGNOSTIC_TOKEN_RE.finditer(current_value):
            if match.group(1) is not None:
                separator = match.group(2).rfind('@')
                if separator >= 0:
                    start = match.start(2)
                    # 最後の@は保持し、その前の認証部分だけを元の位置で置き換える。
                    replacements.append(
                        (positions[start], positions[start + separator])
                    )
                continue

            if match.group('quoted_value') is not None:
                start, end = match.span('quoted_value')
                pending.append(
                    _unquote_diagnostic_value(
                        current_value[start:end], positions[start:end]
                    )
                )
                continue

            for field in _DIAGNOSTIC_FIELD_RE.finditer(match.group(0)):
                start = match.start() + field.start() + field.group(0).index('=') + 1
                end = match.start() + field.end()
                pending.append(
                    _unquote_diagnostic_value(
                        current_value[start:end], positions[start:end]
                    )
                )

    # 内側の構造を読み直しても、出力には元の文字列の認証部分以外をそのまま使う。
    parts: list[str] = []
    previous_end = 0
    for start, end in sorted(replacements):
        parts.extend((value[previous_end:start], '[redacted]'))
        previous_end = end
    parts.append(value[previous_end:])
    return ''.join(parts)

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
# JSON・配列の独立した引用付きURLを、次の値や項目名と分けて処理する。
# URL自身のパスに含まれる引用符は、先に始まるURL候補へ保持する。
_QUOTED_URL_TOKEN_PATTERN = (
    rf'(?<![^\s\[{{,:]){_QUOTED_URL_PATTERN}(?=\s*[:,}}\]])'
)
_URL_TOKEN_PATTERN = (
    f'{_URL_AUTHORITY_RE.pattern}|(?P<quoted_url>{_QUOTED_URL_TOKEN_PATTERN})'
)
_URL_TOKEN_RE = re.compile(_URL_TOKEN_PATTERN, re.IGNORECASE)
_DIAGNOSTIC_TOKEN_RE = re.compile(
    f'{_VALIDATION_DIAGNOSTIC_PATTERN}|{_URL_TOKEN_PATTERN}',
    re.IGNORECASE,
)


def redact_url_credentials(value: str) -> str:
    """診断文字列内の絶対URL・スキーム相対URLの認証部分を伏字へ置換

    空白・制御文字・@を含む拒否対象の認証部分も、最後の@まで置換する。
    パス・クエリ・fragment内の@と、別のURL候補は認証部分へ含めない。
    URL拒否診断は引用付きの値ごとに処理し、取得元とタイトルなどを分離する。
    =や:を使う項目名・引用符・括弧を挟んだスキーム相対URLも分離し、パス以降は保持する。
    JSON・配列の引用付きURLは、値・キーを空白の有無や入れ子に関わらず個別に処理する。

    Args:
        value: エラー理由や進捗として表示・保存する文字列

    Returns:
        URLの認証部分を[redacted]へ置き換えた文字列
    """

    def redact_authority(match: re.Match[str]) -> str:
        """URL候補・引用付きURL・URL拒否診断の認証部分を伏字へ置換

        Args:
            match: URLの各部分、引用付きURL、またはURL拒否診断全体のマッチ結果

        Returns:
            項目の境界を保持して認証部分を伏せた文字列、認証区切りがなければ元の文字列
        """

        if match.group(1) is not None:
            _, separator, host = match.group(2).rpartition('@')
            if not separator:
                return match.group(0)
            return f'{match.group(1)}[redacted]@{host}{match.group(3)}'

        quoted_url = match.group('quoted_url')
        if quoted_url is not None:
            redacted = _URL_AUTHORITY_RE.sub(redact_authority, quoted_url[1:-1])
            return f'{quoted_url[0]}{redacted}{quoted_url[-1]}'
        return _DIAGNOSTIC_FIELD_RE.sub(redact_field, match.group(0))

    def redact_field(match: re.Match[str]) -> str:
        """引用付き診断項目の値だけを伏字処理へ渡す変換

        Args:
            match: 項目名と引用符付きの値を保持したマッチ結果

        Returns:
            項目名と引用符を保持し、値内の認証部分を伏せた文字列
        """

        name, _, quoted_value = match.group(0).partition('=')
        redacted = _URL_TOKEN_RE.sub(redact_authority, quoted_value[1:-1])
        return f'{name}={quoted_value[0]}{redacted}{quoted_value[-1]}'

    return _DIAGNOSTIC_TOKEN_RE.sub(redact_authority, value)

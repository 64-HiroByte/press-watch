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
# 空白後の別の値（href=や引用符付きも含む）から始まる//をパスへ取り込まない。
# reprでエスケープされた引用符も値の境界として扱う。
# 空白列の先頭だけで判定し、長い空白を文字ごとに再走査しない。
_RELATIVE_URL_BOUNDARY_PATTERN = (
    r"""(?<!\s)\s+(?:[^\s/?#='"]+\s*=\s*)?(?:\\*['"])?//"""
)
# authorityは空白でも打ち切らず、パス・クエリ・fragment・次のURLで区切る。
# スキーム相対URLは値の先頭か区切りに続くものだけとし、パス中の//と区別する。
# パス以降は引用符でも打ち切らず保持し、その中の//を認証部分として読み直さない。
_URL_AUTHORITY_RE = re.compile(
    r"""(https?://|(?<![^\s'"=:(\[{])//)"""
    rf'((?:(?!https?://|{_VALIDATION_DIAGNOSTIC_PATTERN}'
    rf'|{_RELATIVE_URL_BOUNDARY_PATTERN})[^/?#])*)'
    r'((?:(?<!\s)/|[?#])(?:(?!https?://)\S)*|)',
    re.IGNORECASE,
)
_DIAGNOSTIC_TOKEN_RE = re.compile(
    f'{_VALIDATION_DIAGNOSTIC_PATTERN}|{_URL_AUTHORITY_RE.pattern}',
    re.IGNORECASE,
)


def redact_url_credentials(value: str) -> str:
    """診断文字列内の絶対URL・スキーム相対URLの認証部分を伏字へ置換

    空白・制御文字・@を含む拒否対象の認証部分も、最後の@まで置換する。
    パス・クエリ・fragment内の@と、別のURL候補は認証部分へ含めない。
    URL拒否診断は引用付きの値ごとに処理し、取得元とタイトルなどを分離する。
    項目名を挟んだスキーム相対URLも分離し、パス以降の引用符は保持する。

    Args:
        value: エラー理由や進捗として表示・保存する文字列

    Returns:
        URLの認証部分を[redacted]へ置き換えた文字列
    """

    def redact_authority(match: re.Match[str]) -> str:
        """URL候補またはURL拒否診断の認証部分を伏字へ置換

        Args:
            match: URLの各部分、またはURL拒否診断全体のマッチ結果

        Returns:
            項目の境界を保持して認証部分を伏せた文字列、認証区切りがなければ元の文字列
        """

        if match.group(1) is None:
            return _DIAGNOSTIC_FIELD_RE.sub(redact_field, match.group(0))

        _, separator, host = match.group(2).rpartition('@')
        if not separator:
            return match.group(0)
        return f'{match.group(1)}[redacted]@{host}{match.group(3)}'

    def redact_field(match: re.Match[str]) -> str:
        """引用付き診断項目の値だけを伏字処理へ渡す変換

        Args:
            match: 項目名と引用符付きの値を保持したマッチ結果

        Returns:
            項目名と引用符を保持し、値内の認証部分を伏せた文字列
        """

        name, _, quoted_value = match.group(0).partition('=')
        redacted = _URL_AUTHORITY_RE.sub(redact_authority, quoted_value[1:-1])
        return f'{name}={quoted_value[0]}{redacted}{quoted_value[-1]}'

    return _DIAGNOSTIC_TOKEN_RE.sub(redact_authority, value)

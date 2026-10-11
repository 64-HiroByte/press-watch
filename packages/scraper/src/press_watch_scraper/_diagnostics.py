"""スクレイパーの診断値に含まれるURL認証情報の伏字処理"""

import re


# authorityは空白でも打ち切らず、パス・クエリ・fragment・次のURLで区切る。
# スキーム相対URLは値の先頭か区切りに続くものだけとし、パス中の//と区別する。
# URLの後半も保持して消費し、そこにある//を認証部分として読み直さない。
_URL_AUTHORITY_RE = re.compile(
    r"""(?i)(https?://|(?<![^\s'"=:(\[{])//)"""
    r'((?:(?!https?://)[^/?#])*)'
    r"""((?:/(?!/)|[?#])(?:(?!https?://)[^\s'"])*|)"""
)


def redact_url_credentials(value: str) -> str:
    """診断文字列内の絶対URL・スキーム相対URLの認証部分を伏字へ置換

    空白・制御文字・@を含む拒否対象の認証部分も、最後の@まで置換する。
    パス・クエリ・fragment内の@と、別のURL候補は認証部分へ含めない。

    Args:
        value: エラー理由や進捗として表示・保存する文字列

    Returns:
        URLの認証部分を[redacted]へ置き換えた文字列
    """

    def redact_authority(match: re.Match[str]) -> str:
        """URL候補のauthorityに認証区切りがあれば認証部分全体を伏字へ置換"""

        _, separator, host = match.group(2).rpartition('@')
        if not separator:
            return match.group(0)
        return f'{match.group(1)}[redacted]@{host}{match.group(3)}'

    return _URL_AUTHORITY_RE.sub(redact_authority, value)

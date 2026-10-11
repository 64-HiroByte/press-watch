"""スクレイパーの診断値に含まれるURL認証情報の伏字処理"""

import re


# 拒否されたURLでも、userinfo内の@を含めて認証部分を伏せる。
_CREDENTIALS_IN_URL_RE = re.compile(r'(?i)((?:https?:)?//)[^/\s]+@')


def redact_url_credentials(value: str) -> str:
    """診断文字列内の絶対URL・スキーム相対URLの認証部分を伏字へ置換

    認証部分に@が含まれる場合も、その全体を置換する。

    Args:
        value: エラー理由や進捗として表示・保存する文字列

    Returns:
        URLの認証部分を[redacted]へ置き換えた文字列
    """

    return _CREDENTIALS_IN_URL_RE.sub(r'\1[redacted]@', value)

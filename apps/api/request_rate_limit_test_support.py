"""APIの単体テストとDB統合テストで共有する制限の差し替え"""

from press_watch_api.request_rate_limit import enforce_request_rate_limit


def _allow_request() -> None:
    """制限以外のHTTP契約を調べるテストで要求を許可"""


RATE_LIMIT_DEPENDENCY_OVERRIDE = {enforce_request_rate_limit: _allow_request}

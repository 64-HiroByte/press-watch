from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    """DB関連エラーで公開する固定メッセージ"""

    model_config = ConfigDict(frozen=True)

    detail: str

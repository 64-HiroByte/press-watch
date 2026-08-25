from fastapi import FastAPI

from press_watch_api.routers.press_releases import router as press_releases_router

app = FastAPI(title="PressWatch API")
app.include_router(press_releases_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "service": "press-watch-api",
        "status": "ready",
    }


@app.get("/health")
def read_health() -> dict[str, str]:
    """APIプロセスのlivenessステータスを返す"""

    return {"status": "ok"}

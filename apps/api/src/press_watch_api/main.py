from fastapi import FastAPI

app = FastAPI(title="PressWatch API")


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "service": "press-watch-api",
        "status": "ready",
    }

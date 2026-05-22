from dataclasses import dataclass
import os


DATABASE_URL_ENV = "DATABASE_URL"


@dataclass(frozen=True)
class Settings:
    database_url: str


def load_settings() -> Settings:
    database_url = os.getenv(DATABASE_URL_ENV)
    if not database_url:
        raise RuntimeError(f"{DATABASE_URL_ENV} is not set.")

    return Settings(database_url=database_url)

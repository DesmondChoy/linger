"""Application settings, loaded from the repository-root `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_api_key: str
    linger_model: str = "google:gemini-2.5-flash"
    linger_allowed_origins: str = "http://localhost:5173"

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.linger_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Read settings once per process, failing loudly if the key is absent."""
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:  # pragma: no cover - startup guard
        raise RuntimeError(
            "Configuration error. Copy `.env.example` to `.env` and set GOOGLE_API_KEY "
            "(get one at https://aistudio.google.com/apikey)."
        ) from exc

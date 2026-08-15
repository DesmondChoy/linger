"""Application settings, loaded from the repository-root `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    linger_model: str = "google:gemini-2.5-flash"
    linger_allowed_origins: str = "http://localhost:5173"
    linger_account_id: str = "local-prototype-user"
    allowed_book_version_ids: tuple[str, ...] = ("pg11-v01b38ea4",)
    linger_web_search_enabled: bool = False

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.linger_allowed_origins.split(",") if o.strip()]

    def api_key_for(self, provider_name: str) -> str:
        """Return the selected provider's key or fail with a useful message."""
        keys = {
            "google": self.google_api_key,
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
        }
        key = keys.get(provider_name)
        value = key.get_secret_value().strip() if key is not None else ""
        if not value:
            variable = f"{provider_name.upper()}_API_KEY"
            raise RuntimeError(f"{variable} is required for {provider_name!r} models.")
        return value


@lru_cache
def get_settings() -> Settings:
    """Read settings once per process."""
    return Settings()

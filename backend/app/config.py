"""Application settings.

Everything here can be overridden with environment variables (or a .env file
at the repo root) using the FINANCE_ prefix, e.g. FINANCE_BASE_CURRENCY=USD.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FINANCE_",
        env_file=REPO_ROOT / ".env",
        extra="ignore",
    )

    # All reporting happens in this currency; holdings priced in anything else
    # are converted with the daily FX rate.
    base_currency: str = "EUR"

    data_dir: Path = REPO_ROOT / "data"
    db_filename: str = "finance.db"

    # Local hour (24h) for the daily price fetch. Default is after the US
    # close so the latest daily close is actually available.
    price_fetch_hour: int = 23
    price_fetch_minute: int = 0

    # Turning this off is useful in tests and when running one-off scripts.
    enable_scheduler: bool = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"


settings = Settings()

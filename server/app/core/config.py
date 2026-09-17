"""Server configuration and environment variable loading via Pydantic Settings."""

from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://noinsta_user:noinsta_password@localhost:5432/noinsta"
    )

    # JWT / Security (Indefinite lifespan / no token expiry timeout)
    JWT_SECRET: str = Field(
        default="noinsta_super_secret_jwt_key_change_in_production_min_32_bytes"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=52560000)  # ~100 years (no timeout)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=36500)  # ~100 years (no timeout)

    # Pairing (Indefinite lifespan / no pairing code expiration timeout)
    PAIRING_CODE_EXPIRE_MINUTES: int = Field(default=52560000)  # ~100 years (no timeout)
    PAIRING_CODE_MAX_ATTEMPTS: int = Field(default=500)

    # Cooldown & Presence (Zero cooldown timeout, no laptop offline timeout)
    INSTAGRAM_COOLDOWN_SECONDS: int = Field(default=0)  # 0s cooldown (triggers immediately every time)
    LAPTOP_HEARTBEAT_SECONDS: int = Field(default=120)
    LAPTOP_OFFLINE_SECONDS: int = Field(default=0)  # 0s = disabled / no offline timeout

    # App Environment & Security
    APP_ENV: str = Field(default="development")
    ALLOWED_ORIGINS: str = Field(default="https://noinsta.platesight.in")
    RATE_LIMIT_PER_MINUTE: int = Field(default=60)
    ENABLE_DOCS: bool = Field(default=True)

    @property
    def cors_origins(self) -> List[str]:
        """Return list of allowed CORS origins."""
        if not self.ALLOWED_ORIGINS:
            return []
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


settings = Settings()

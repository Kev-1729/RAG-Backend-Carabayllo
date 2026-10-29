from typing import Any, cast

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    cors_allow_origins: str = ""
    anthropic_api_key: SecretStr
    llm_model: str
    database_url: SecretStr
    voyage_api_key: SecretStr
    embedding_model: str = "voyage-4"
    chunk_size: int = Field(default=1000, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


settings: Settings = cast(Any, Settings)()

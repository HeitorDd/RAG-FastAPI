"""Configuracao da aplicacao, lida exclusivamente do ambiente."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracao tipada. Nenhum segredo tem valor padrao."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["dev", "prod"] = "dev"
    log_level: str = "INFO"

    # Banco da aplicacao (Postgres + pgvector).
    database_url: str
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    migrations_dir: Path = Path("migrations")

    # Provedores externos: opcionais na Fase 1, obrigatorios a partir da Fase 2.
    openai_api_key: str | None = None
    cohere_api_key: str | None = None

    # Observabilidade.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "http://localhost:3000"

    @property
    def langfuse_enabled(self) -> bool:
        """Langfuse so e ativado quando o par de chaves esta presente."""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instancia unica de configuracao, resolvida na primeira chamada."""
    return Settings()

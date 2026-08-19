"""Ambiente minimo para os testes rodarem sem banco nem chaves reais."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://rag:rag@localhost:5432/rag_test")
os.environ.setdefault("APP_ENV", "dev")

from rag_docs.config import Settings, get_settings

# O .env local existe na maquina do dev e nao pode vazar para os testes: eles
# descrevem o comportamento a partir do ambiente explicito, nada mais.
Settings.model_config["env_file"] = None


@pytest.fixture(autouse=True)
def _limpa_cache_de_settings() -> Iterator[None]:
    """Evita que um teste veja a configuracao memoizada por outro."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

"""Testes da configuracao."""

from __future__ import annotations

import pytest

from rag_docs.config import get_settings


def test_database_url_vem_do_ambiente() -> None:
    assert get_settings().database_url.startswith("postgresql://")


def test_langfuse_desativado_sem_chaves(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    get_settings.cache_clear()
    assert get_settings().langfuse_enabled is False


def test_langfuse_exige_o_par_de_chaves(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-teste")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    get_settings.cache_clear()
    assert get_settings().langfuse_enabled is False

    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-teste")
    get_settings.cache_clear()
    assert get_settings().langfuse_enabled is True

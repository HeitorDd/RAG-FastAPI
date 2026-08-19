"""Testes do healthcheck sem banco: o endpoint precisa degradar, nao explodir."""

from __future__ import annotations

import httpx
import pytest

from rag_docs.main import app, state


@pytest.fixture(autouse=True)
def _sem_pool() -> None:
    state.pool = None


async def test_health_degradado_sem_banco() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://teste") as cliente:
        resposta = await cliente.get("/health")

    assert resposta.status_code == 503
    corpo = resposta.json()
    assert corpo["status"] == "degradado"
    assert corpo["banco"] == "erro"
    assert corpo["pgvector"] is None
    assert corpo["detalhe"]

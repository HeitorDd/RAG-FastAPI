"""Testes do modulo de embeddings, com cliente falso -- nao chama a API."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from rag_docs import embeddings


@dataclass
class _Item:
    index: int
    embedding: list[float]


@dataclass
class _Resposta:
    data: list[_Item]


class _EmbeddingsFalso:
    def __init__(self) -> None:
        self.lotes: list[list[str]] = []

    async def create(self, *, model: str, input: list[str]) -> _Resposta:
        self.lotes.append(list(input))
        # Devolve fora de ordem de proposito: a ordem correta vem de `index`.
        itens = [_Item(index=i, embedding=[float(i)]) for i in range(len(input))]
        return _Resposta(data=list(reversed(itens)))


class _ClienteFalso:
    def __init__(self) -> None:
        self.embeddings = _EmbeddingsFalso()


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> _ClienteFalso:
    falso = _ClienteFalso()
    monkeypatch.setattr(embeddings, "get_cliente", lambda: falso)
    return falso


async def test_lista_vazia_nao_chama_a_api(cliente: _ClienteFalso) -> None:
    assert await embeddings.embed_textos([]) == []
    assert cliente.embeddings.lotes == []


async def test_quebra_em_lotes_de_cem(cliente: _ClienteFalso) -> None:
    await embeddings.embed_textos([f"t{i}" for i in range(250)])
    assert [len(lote) for lote in cliente.embeddings.lotes] == [100, 100, 50]


async def test_preserva_a_ordem_de_entrada(cliente: _ClienteFalso) -> None:
    """A API nao garante ordem de resposta; quem garante e o campo `index`."""
    vetores = await embeddings.embed_textos(["a", "b", "c"])
    assert vetores == [[0.0], [1.0], [2.0]]


async def test_pergunta_passa_pela_mesma_funcao(
    cliente: _ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pergunta e documento precisam do mesmo modelo, ou os vetores nao comparam."""
    chamadas: list[list[str]] = []
    original = embeddings.embed_textos

    async def espiao(textos: Sequence[str]) -> list[list[float]]:
        chamadas.append(list(textos))
        return await original(textos)

    monkeypatch.setattr(embeddings, "embed_textos", espiao)
    vetor = await embeddings.embed_pergunta("como uso StreamingResponse?")

    assert chamadas == [["como uso StreamingResponse?"]]
    assert vetor == [0.0]


async def test_usa_o_modelo_unico_do_modulo(cliente: _ClienteFalso) -> None:
    assert embeddings.MODELO == "text-embedding-3-small"
    assert embeddings.DIMENSOES == 1536

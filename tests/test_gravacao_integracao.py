"""Teste de integracao da gravacao. Exige Postgres com as migracoes aplicadas.

Roda com RAG_TEST_DATABASE_URL apontando para um banco de teste; sem a
variavel, e pulado. E o unico lugar que prova de verdade a promessa da fase:
rodar duas vezes nao duplica, e um documento que encolheu nao deixa lixo.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

from rag_docs.config import Settings
from rag_docs.db import Pool, create_pool
from rag_docs.embeddings import DIMENSOES
from rag_docs.ingest.chunking import Chunk
from rag_docs.ingest.gravacao import gravar_documento

DSN = os.environ.get("RAG_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DSN, reason="defina RAG_TEST_DATABASE_URL para rodar os testes de integracao"
)

DOC = "https://exemplo.teste/pagina/"


def _chunk(posicao: int, texto: str = "conteudo") -> Chunk:
    return Chunk(
        texto=f"Trilha > Secao\n\n{texto} {posicao}",
        url=f"{DOC}#secao-{posicao}",
        documento_url=DOC,
        secao="Trilha > Secao",
        posicao=posicao,
    )


def _vetor(semente: int) -> list[float]:
    vetor = [0.0] * DIMENSOES
    vetor[semente % DIMENSOES] = 1.0
    return vetor


@pytest.fixture
async def pool() -> AsyncIterator[Pool]:
    assert DSN is not None
    settings = Settings(database_url=DSN)
    pool = await create_pool(settings)
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM chunks WHERE documento_url = $1", DOC)
    try:
        yield pool
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM chunks WHERE documento_url = $1", DOC)
        await pool.close()


async def _total(pool: Pool) -> int:
    async with pool.acquire() as conn:
        return int(await conn.fetchval("SELECT count(*) FROM chunks WHERE documento_url = $1", DOC))


async def _ids(pool: Pool) -> list[int]:
    async with pool.acquire() as conn:
        linhas = await conn.fetch(
            "SELECT id FROM chunks WHERE documento_url = $1 ORDER BY posicao", DOC
        )
    return [int(linha["id"]) for linha in linhas]


async def test_grava_e_conta(pool: Pool) -> None:
    chunks = [_chunk(i) for i in range(3)]
    gravados, orfaos = await gravar_documento(pool, DOC, chunks, [_vetor(i) for i in range(3)])

    assert (gravados, orfaos) == (3, 0)
    assert await _total(pool) == 3


async def test_rodar_duas_vezes_nao_duplica(pool: Pool) -> None:
    chunks = [_chunk(i) for i in range(3)]
    vetores = [_vetor(i) for i in range(3)]

    await gravar_documento(pool, DOC, chunks, vetores)
    ids_primeira = await _ids(pool)
    await gravar_documento(pool, DOC, chunks, vetores)

    assert await _total(pool) == 3
    # Os ids sobrevivem: os evals da Fase 4 apontam para eles.
    assert await _ids(pool) == ids_primeira


async def test_upsert_atualiza_o_texto(pool: Pool) -> None:
    await gravar_documento(pool, DOC, [_chunk(0, "antigo")], [_vetor(0)])
    await gravar_documento(pool, DOC, [_chunk(0, "novo")], [_vetor(0)])

    async with pool.acquire() as conn:
        texto = await conn.fetchval(
            "SELECT texto FROM chunks WHERE documento_url = $1 AND posicao = 0", DOC
        )
    assert "novo" in str(texto)


async def test_documento_que_encolheu_nao_deixa_orfao(pool: Pool) -> None:
    """Sem isso, chunks de uma versao anterior ficam recuperaveis para sempre."""
    await gravar_documento(pool, DOC, [_chunk(i) for i in range(5)], [_vetor(i) for i in range(5)])
    assert await _total(pool) == 5

    _, orfaos = await gravar_documento(
        pool, DOC, [_chunk(i) for i in range(2)], [_vetor(i) for i in range(2)]
    )

    assert orfaos == 3
    assert await _total(pool) == 2


async def test_recusa_contagem_incompativel(pool: Pool) -> None:
    with pytest.raises(ValueError):
        await gravar_documento(pool, DOC, [_chunk(0), _chunk(1)], [_vetor(0)])


async def test_tsv_e_gerado_pelo_banco(pool: Pool) -> None:
    """A coluna gerada torna impossivel gravar texto sem indice lexical em dia."""
    await gravar_documento(pool, DOC, [_chunk(0, "StreamingResponse envia bytes")], [_vetor(0)])

    async with pool.acquire() as conn:
        casou = await conn.fetchval(
            "SELECT count(*) FROM chunks WHERE documento_url = $1 "
            "AND tsv @@ plainto_tsquery('english', 'bytes')",
            DOC,
        )
    assert int(casou) == 1

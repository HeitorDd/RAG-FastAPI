"""Gravacao idempotente dos chunks.

Duas coisas garantem que rodar duas vezes nao duplique nem deixe lixo:

1. Upsert na chave natural (documento_url, posicao) -- o mesmo chunk do mesmo
   documento sobrescreve a si mesmo, e o `id` sobrevive, o que os evals da
   Fase 4 dependem.
2. Limpeza de orfaos. Se um documento encolheu entre duas ingestoes, as
   posicoes que sobraram da versao anterior continuariam no acervo e seriam
   recuperaveis para sempre. E o furo silencioso mais comum desse tipo de
   pipeline: nada falha, o acervo so vai apodrecendo.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from pgvector import Vector

from rag_docs.db import Pool
from rag_docs.ingest.chunking import Chunk

logger = logging.getLogger(__name__)

_UPSERT = """
INSERT INTO chunks (texto, url, documento_url, secao, posicao, embedding)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (documento_url, posicao) DO UPDATE
SET texto = EXCLUDED.texto,
    url = EXCLUDED.url,
    secao = EXCLUDED.secao,
    embedding = EXCLUDED.embedding
"""

_LIMPAR_ORFAOS = "DELETE FROM chunks WHERE documento_url = $1 AND posicao >= $2"


@dataclass(slots=True)
class ResultadoGravacao:
    """Contagem do que a ingestao fez, para o relatorio final."""

    documentos: int = 0
    chunks_gravados: int = 0
    orfaos_removidos: int = 0


async def gravar_documento(
    pool: Pool,
    documento_url: str,
    chunks: Sequence[Chunk],
    embeddings: Sequence[Sequence[float]],
) -> tuple[int, int]:
    """Grava os chunks de um documento numa transacao. Devolve (gravados, orfaos)."""
    if len(chunks) != len(embeddings):
        raise ValueError(f"{len(chunks)} chunks para {len(embeddings)} embeddings")

    async with pool.acquire() as conn, conn.transaction():
        for chunk, vetor in zip(chunks, embeddings, strict=True):
            await conn.execute(
                _UPSERT,
                chunk.texto,
                chunk.url,
                chunk.documento_url,
                chunk.secao,
                chunk.posicao,
                Vector(list(vetor)),
            )
        removidos_raw = await conn.execute(_LIMPAR_ORFAOS, documento_url, len(chunks))

    # asyncpg devolve a tag do comando, ex.: "DELETE 3".
    removidos = int(removidos_raw.split()[-1]) if removidos_raw else 0
    if removidos:
        logger.info("%s: %d chunks orfaos removidos", documento_url, removidos)
    return len(chunks), removidos


async def contar_chunks(pool: Pool) -> int:
    """Total de chunks no acervo."""
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT count(*) FROM chunks")
    return int(total or 0)

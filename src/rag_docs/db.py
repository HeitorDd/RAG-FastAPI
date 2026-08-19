"""Pool de conexoes com o Postgres e registro do tipo `vector`."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import asyncpg
from pgvector.asyncpg import register_vector

from rag_docs.config import Settings

logger = logging.getLogger(__name__)

# Aliases PEP 695: avaliados sob demanda, entao os genericos do asyncpg-stubs
# nao sao resolvidos em tempo de execucao (asyncpg.Pool nao e subscriptable).
type Pool = asyncpg.Pool[asyncpg.Record]
type Connection = asyncpg.Connection[asyncpg.Record]

_ERRO_SEM_EXTENSAO = (
    "A extensao pgvector nao esta instalada no banco. "
    "Rode as migracoes antes de subir a API: `uv run python -m rag_docs.migrate`."
)


async def _init_connection(conn: Connection) -> None:
    """Ensina o asyncpg a codificar/decodificar o tipo `vector`."""
    await register_vector(conn)


async def create_pool(settings: Settings) -> Pool:
    """Cria o pool ja com o codec de `vector` registrado.

    Falha cedo e com mensagem explicita quando as migracoes ainda nao rodaram,
    porque sem a extensao o registro do codec nao tem tipo para resolver.
    """
    try:
        pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            init=_init_connection,
        )
    except asyncpg.UndefinedObjectError as exc:  # pragma: no cover - depende do banco
        raise RuntimeError(_ERRO_SEM_EXTENSAO) from exc
    if pool is None:  # pragma: no cover - contrato do asyncpg
        raise RuntimeError("asyncpg.create_pool retornou None")
    logger.info("pool de conexoes criado")
    return pool


@dataclass(slots=True)
class DatabaseHealth:
    """Resultado da sondagem de saude do banco."""

    ok: bool
    pgvector_version: str | None
    detalhe: str | None = None


async def check_health(pool: Pool) -> DatabaseHealth:
    """Confirma que o banco responde e que a extensao pgvector esta ativa."""
    try:
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
            versao = await conn.fetchval(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )
    except (OSError, asyncpg.PostgresError) as exc:
        return DatabaseHealth(ok=False, pgvector_version=None, detalhe=str(exc))

    if versao is None:
        return DatabaseHealth(ok=False, pgvector_version=None, detalhe=_ERRO_SEM_EXTENSAO)
    return DatabaseHealth(ok=True, pgvector_version=str(versao))

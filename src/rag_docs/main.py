"""Aplicacao FastAPI. Na Fase 1 expoe apenas o healthcheck."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Response, status

from rag_docs import __version__
from rag_docs.config import get_settings
from rag_docs.db import Pool, check_health, create_pool
from rag_docs.models import HealthResponse
from rag_docs.observability import init_langfuse, shutdown_langfuse

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppState:
    """Recursos de processo. Guardado em modulo para permanecer tipado."""

    pool: Pool | None = None


state = AppState()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Abre o pool e o cliente Langfuse na subida; fecha os dois na descida."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")
    init_langfuse(settings)
    state.pool = await create_pool(settings)
    try:
        yield
    finally:
        if state.pool is not None:
            await state.pool.close()
            state.pool = None
        shutdown_langfuse()


app = FastAPI(
    title="Assistente de documentacao (RAG)",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse, summary="Healthcheck")
async def health(response: Response) -> HealthResponse:
    """Retorna 200 so quando banco e pgvector respondem; 503 caso contrario."""
    langfuse = "configurado" if get_settings().langfuse_enabled else "desativado"

    if state.pool is None:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="degradado",
            versao=__version__,
            banco="erro",
            langfuse=langfuse,
            detalhe="pool de conexoes indisponivel",
        )

    saude = await check_health(state.pool)
    if not saude.ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="degradado",
            versao=__version__,
            banco="erro",
            langfuse=langfuse,
            detalhe=saude.detalhe,
        )

    return HealthResponse(
        status="ok",
        versao=__version__,
        banco="ok",
        pgvector=saude.pgvector_version,
        langfuse=langfuse,
    )

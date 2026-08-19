"""Cliente Langfuse. Vira no-op quando as chaves nao estao configuradas.

Na Fase 1 existe apenas o encanamento: as Fases 3 e 5 penduram um span por
etapa do pipeline (busca densa, BM25, RRF, rerank, geracao) para que um trace
diga se a falha foi de recuperacao ou de geracao.
"""

from __future__ import annotations

import logging

from langfuse import Langfuse

from rag_docs.config import Settings

logger = logging.getLogger(__name__)

_client: Langfuse | None = None


def init_langfuse(settings: Settings) -> Langfuse | None:
    """Inicializa o cliente uma unica vez. Retorna None se estiver desativado."""
    global _client
    if not settings.langfuse_enabled:
        logger.warning("langfuse desativado: chaves ausentes no ambiente")
        _client = None
        return None
    if _client is None:
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("langfuse inicializado em %s", settings.langfuse_host)
    return _client


def get_langfuse() -> Langfuse | None:
    """Cliente corrente, ou None quando a observabilidade esta desativada."""
    return _client


def shutdown_langfuse() -> None:
    """Descarrega eventos pendentes antes do processo morrer."""
    global _client
    if _client is not None:
        _client.flush()
        _client = None

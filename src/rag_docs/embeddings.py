"""Embeddings. Este modulo e o unico lugar do projeto que fala com o modelo.

Pergunta e documento precisam ser embedados pelo MESMO modelo, senao os vetores
vivem em espacos diferentes e a busca por similaridade compara coisas que nao
sao comparaveis -- uma falha silenciosa, que nao levanta excecao e so aparece
como recall ruim. Centralizar aqui torna impossivel divergir: tanto a ingestao
(Fase 2) quanto a consulta (Fase 3) passam por `embed_textos`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from openai import AsyncOpenAI

from rag_docs.config import get_settings

logger = logging.getLogger(__name__)

MODELO = "text-embedding-3-small"
DIMENSOES = 1536
TAMANHO_LOTE = 100
"""Lotes de 100: equilibra numero de chamadas contra o limite de payload."""

_cliente: AsyncOpenAI | None = None


def get_cliente() -> AsyncOpenAI:
    """Cliente OpenAI unico, com retry/backoff nativo do SDK."""
    global _cliente
    if _cliente is None:
        chave = get_settings().openai_api_key
        if not chave:
            raise RuntimeError("OPENAI_API_KEY ausente. Preencha o .env antes de rodar a ingestao.")
        _cliente = AsyncOpenAI(api_key=chave, max_retries=5)
    return _cliente


async def embed_textos(textos: Sequence[str]) -> list[list[float]]:
    """Embeda uma sequencia de textos, em lotes, preservando a ordem de entrada.

    Unico ponto de contato com o modelo de embedding em todo o projeto.
    """
    if not textos:
        return []

    vetores: list[list[float]] = []
    cliente = get_cliente()
    for inicio in range(0, len(textos), TAMANHO_LOTE):
        lote = list(textos[inicio : inicio + TAMANHO_LOTE])
        resposta = await cliente.embeddings.create(model=MODELO, input=lote)
        # A API nao garante ordem; o campo `index` e quem garante.
        for item in sorted(resposta.data, key=lambda d: d.index):
            vetores.append(item.embedding)
        logger.info("embeddings: %d/%d", len(vetores), len(textos))

    if len(vetores) != len(textos):
        raise RuntimeError(f"esperava {len(textos)} embeddings, recebi {len(vetores)}")
    return vetores


async def embed_pergunta(pergunta: str) -> list[float]:
    """Embeda a pergunta do usuario. Passa pela mesma funcao que os documentos."""
    vetores = await embed_textos([pergunta])
    return vetores[0]

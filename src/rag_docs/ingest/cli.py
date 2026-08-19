"""CLI da ingestao: `uv run python -m rag_docs.ingest`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from rag_docs.config import get_settings
from rag_docs.db import create_pool
from rag_docs.embeddings import embed_textos
from rag_docs.ingest.chunking import Chunk, chunk_documento
from rag_docs.ingest.coleta import (
    DIR_BASE_INCLUDES,
    REPO_PADRAO,
    URL_BASE_PADRAO,
    clonar_ou_atualizar,
    coletar,
)
from rag_docs.ingest.gravacao import ResultadoGravacao, contar_chunks, gravar_documento

logger = logging.getLogger(__name__)

DESTINO_PADRAO = Path("data/fastapi")


def montar_parser() -> argparse.ArgumentParser:
    """Interface de linha de comando da ingestao."""
    parser = argparse.ArgumentParser(
        prog="python -m rag_docs.ingest",
        description="Coleta, fatia e indexa a documentacao do FastAPI.",
    )
    parser.add_argument("--repo", default=REPO_PADRAO, help="repositorio das docs")
    parser.add_argument("--ref", default=None, help="branch ou tag (padrao: HEAD do remoto)")
    parser.add_argument("--dest", type=Path, default=DESTINO_PADRAO, help="onde clonar")
    parser.add_argument("--url-base", default=URL_BASE_PADRAO, help="base das URLs publicas")
    parser.add_argument("--limit", type=int, default=None, help="processa so os N primeiros docs")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="coleta e fatia sem embedar nem gravar (nao gasta credito)",
    )
    parser.add_argument(
        "--incluir-tudo",
        action="store_true",
        help="nao filtra release-notes nem paginas auxiliares",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log em DEBUG")
    return parser


def _relatorio_chunks(chunks: list[Chunk]) -> str:
    if not chunks:
        return "nenhum chunk gerado"
    tamanhos = sorted(len(c.texto) for c in chunks)
    mediana = tamanhos[len(tamanhos) // 2]
    com_anchor = sum(1 for c in chunks if "#" in c.url)
    return (
        f"{len(chunks)} chunks | tamanho min/mediana/max: "
        f"{tamanhos[0]}/{mediana}/{tamanhos[-1]} caracteres | "
        f"{com_anchor} ({com_anchor * 100 // len(chunks)}%) com anchor de secao"
    )


async def executar(args: argparse.Namespace) -> int:
    """Roda o pipeline inteiro e devolve o codigo de saida."""
    destino: Path = args.dest
    sha = clonar_ou_atualizar(destino, repo=args.repo, ref=args.ref)

    documentos = coletar(destino, url_base=args.url_base, incluir_tudo=args.incluir_tudo)
    if args.limit is not None:
        documentos = documentos[: args.limit]

    base_includes = destino / DIR_BASE_INCLUDES
    por_documento: list[tuple[str, list[Chunk]]] = []
    todos: list[Chunk] = []
    for documento in documentos:
        chunks = chunk_documento(documento, base_includes)
        if not chunks:
            logger.warning("documento sem chunks: %s", documento.caminho_relativo)
            continue
        por_documento.append((documento.url, chunks))
        todos.extend(chunks)

    print(f"commit das docs: {sha}")
    print(f"documentos: {len(por_documento)}")
    print(_relatorio_chunks(todos))

    if args.dry_run:
        print("--dry-run: nada foi embedado nem gravado")
        return 0

    print(f"embedando {len(todos)} chunks...")
    vetores = await embed_textos([c.texto for c in todos])

    settings = get_settings()
    pool = await create_pool(settings)
    resultado = ResultadoGravacao()
    try:
        deslocamento = 0
        for documento_url, chunks in por_documento:
            fatia = vetores[deslocamento : deslocamento + len(chunks)]
            deslocamento += len(chunks)
            gravados, orfaos = await gravar_documento(pool, documento_url, chunks, fatia)
            resultado.documentos += 1
            resultado.chunks_gravados += gravados
            resultado.orfaos_removidos += orfaos
        total = await contar_chunks(pool)
    finally:
        await pool.close()

    print(
        f"gravado: {resultado.chunks_gravados} chunks de {resultado.documentos} documentos"
        f" | orfaos removidos: {resultado.orfaos_removidos}"
        f" | total no acervo: {total}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada."""
    args = montar_parser().parse_args(argv)
    settings = get_settings()
    logging.basicConfig(
        level="DEBUG" if args.verbose else settings.log_level,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(executar(args))


if __name__ == "__main__":
    sys.exit(main())

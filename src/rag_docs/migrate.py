"""Executor de migracoes SQL.

Aplica em ordem os arquivos `NNN_*.sql` de `migrations/`, cada um dentro de uma
transacao, e registra o que ja rodou em `schema_migrations`. Rodar duas vezes
nao reaplica nada. Nao usa o pool da aplicacao porque na primeira execucao a
extensao `vector` ainda nao existe.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import asyncpg

from rag_docs.config import Settings, get_settings

logger = logging.getLogger(__name__)

_TABELA_CONTROLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    versao      text        PRIMARY KEY,
    aplicada_em timestamptz NOT NULL DEFAULT now()
)
"""


def listar_migracoes(diretorio: Path) -> list[Path]:
    """Migracoes disponiveis, em ordem lexicografica (que e a ordem numerica)."""
    if not diretorio.is_dir():
        raise FileNotFoundError(f"diretorio de migracoes nao encontrado: {diretorio}")
    return sorted(diretorio.glob("*.sql"))


async def aplicar_migracoes(settings: Settings) -> list[str]:
    """Aplica as migracoes pendentes e devolve os nomes das que rodaram."""
    arquivos = listar_migracoes(settings.migrations_dir)
    conn = await asyncpg.connect(dsn=settings.database_url)
    aplicadas: list[str] = []
    try:
        await conn.execute(_TABELA_CONTROLE)
        ja_aplicadas = {
            str(registro["versao"])
            for registro in await conn.fetch("SELECT versao FROM schema_migrations")
        }
        for arquivo in arquivos:
            versao = arquivo.stem
            if versao in ja_aplicadas:
                logger.info("migracao ja aplicada, pulando: %s", versao)
                continue
            sql = arquivo.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute("INSERT INTO schema_migrations (versao) VALUES ($1)", versao)
            aplicadas.append(versao)
            logger.info("migracao aplicada: %s", versao)
    finally:
        await conn.close()
    return aplicadas


def main() -> int:
    """Ponto de entrada CLI: `python -m rag_docs.migrate`."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")
    aplicadas = asyncio.run(aplicar_migracoes(settings))
    if aplicadas:
        print(f"migracoes aplicadas: {', '.join(aplicadas)}")
    else:
        print("nenhuma migracao pendente")
    return 0


if __name__ == "__main__":
    sys.exit(main())

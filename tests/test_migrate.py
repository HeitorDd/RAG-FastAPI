"""Testes do executor de migracoes."""

from __future__ import annotations

from pathlib import Path

import pytest

from rag_docs.migrate import listar_migracoes


def test_lista_migracoes_em_ordem() -> None:
    arquivos = listar_migracoes(Path("migrations"))
    assert [a.name for a in arquivos] == sorted(a.name for a in arquivos)
    assert arquivos[0].name == "001_init.sql"


def test_diretorio_inexistente_falha_alto(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        listar_migracoes(tmp_path / "nao-existe")


def test_migracao_inicial_cria_tabela_e_indices() -> None:
    sql = Path("migrations/001_init.sql").read_text(encoding="utf-8")
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "vector(1536)" in sql
    assert "USING hnsw (embedding vector_cosine_ops)" in sql
    assert "USING gin (tsv)" in sql

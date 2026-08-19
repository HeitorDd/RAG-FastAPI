"""Testes do chunking: trilha, anchors, codigo intacto e tamanho minimo."""

from __future__ import annotations

from pathlib import Path

import pytest

from rag_docs.ingest.chunking import TAMANHO_MINIMO_CONTEUDO, Chunk, chunk_documento
from rag_docs.ingest.coleta import Documento


def _documento(texto: str, caminho: str = "advanced/custom-response.md") -> Documento:
    return Documento(
        caminho=Path(caminho),
        caminho_relativo=caminho,
        url=f"https://fastapi.tiangolo.com/{caminho.removesuffix('.md')}/",
        texto=texto,
    )


def _chunks(
    texto: str, tmp_path: Path, caminho: str = "advanced/custom-response.md"
) -> list[Chunk]:
    base = tmp_path / "docs" / "en"
    base.mkdir(parents=True, exist_ok=True)
    return chunk_documento(_documento(texto, caminho), base)


MD = """# Custom Response { #custom-response }

Corpo introdutorio com texto suficiente para passar do tamanho minimo exigido.

## HTML Response { #html-response }

Para devolver HTML diretamente, use HTMLResponse conforme o exemplo a seguir.

```python
@app.get("/")
async def read_items():
    return {"ok": True}
```
"""


def test_trilha_completa_vem_prefixada(tmp_path: Path) -> None:
    """Isolado, o trecho usa pronomes sem referente; a trilha da o contexto."""
    chunks = _chunks(MD, tmp_path)
    primeiro = chunks[0]
    assert primeiro.texto.startswith(primeiro.secao)
    assert primeiro.secao.startswith("FastAPI > Advanced > Custom Response")


def test_secao_profunda_entra_na_trilha(tmp_path: Path) -> None:
    chunks = _chunks(MD, tmp_path)
    assert any(c.secao.endswith("HTML Response") for c in chunks)


def test_url_carrega_o_anchor_da_secao(tmp_path: Path) -> None:
    chunks = _chunks(MD, tmp_path)
    html = next(c for c in chunks if c.secao.endswith("HTML Response"))
    assert html.url.endswith("/advanced/custom-response/#html-response")
    assert html.documento_url == "https://fastapi.tiangolo.com/advanced/custom-response/"


def test_indentacao_do_codigo_sobrevive_ao_divisor(tmp_path: Path) -> None:
    """O MarkdownHeaderTextSplitter remove recuo de toda linha; blindamos o codigo."""
    chunks = _chunks(MD, tmp_path)
    com_codigo = next(c for c in chunks if "```python" in c.texto)
    assert '    return {"ok": True}' in com_codigo.texto


def test_comentario_python_nao_vira_cabecalho(tmp_path: Path) -> None:
    md = """# Titulo { #titulo }

Texto de abertura com tamanho suficiente para sobreviver ao corte minimo.

```python
# Isto e um comentario, nao um cabecalho
app = FastAPI()
```
"""
    chunks = _chunks(md, tmp_path)
    assert all("Isto E Um Comentario" not in c.secao for c in chunks)


def test_posicao_e_sequencial_no_documento(tmp_path: Path) -> None:
    chunks = _chunks(MD, tmp_path)
    assert [c.posicao for c in chunks] == list(range(len(chunks)))


def test_descarta_fragmento_curto_demais(tmp_path: Path) -> None:
    md = "# Titulo { #t }\n\nTest:\n"
    assert _chunks(md, tmp_path) == []


def test_anchor_ausente_mantem_url_da_pagina(tmp_path: Path) -> None:
    md = "# Sem Anchor\n\n" + "conteudo suficiente para passar do minimo. " * 3
    chunks = _chunks(md, tmp_path)
    assert all("#" not in c.url for c in chunks)


@pytest.mark.parametrize("caminho", ["index.md", "tutorial/security/first-steps.md"])
def test_trilha_deriva_dos_diretorios(caminho: str, tmp_path: Path) -> None:
    md = "# Titulo { #t }\n\n" + "texto com corpo suficiente para o corte minimo. " * 3
    chunks = _chunks(md, tmp_path, caminho)
    assert chunks[0].secao.startswith("FastAPI > ")
    if "/" in caminho:
        assert "Tutorial > Security" in chunks[0].secao


def test_todo_chunk_passa_do_tamanho_minimo(tmp_path: Path) -> None:
    for chunk in _chunks(MD, tmp_path):
        conteudo = chunk.texto.split("\n\n", 1)[1]
        assert len(conteudo) >= TAMANHO_MINIMO_CONTEUDO

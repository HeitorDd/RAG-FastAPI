"""Testes da coleta: mapeamento de URL e filtro do que nao e documentacao."""

from __future__ import annotations

import pytest

from rag_docs.ingest.coleta import _e_documentacao, caminho_para_url


@pytest.mark.parametrize(
    ("caminho", "esperado"),
    [
        ("index.md", "https://fastapi.tiangolo.com/"),
        ("advanced/custom-response.md", "https://fastapi.tiangolo.com/advanced/custom-response/"),
        ("about/index.md", "https://fastapi.tiangolo.com/about/"),
        (
            "tutorial/security/first-steps.md",
            "https://fastapi.tiangolo.com/tutorial/security/first-steps/",
        ),
    ],
)
def test_caminho_vira_url_do_mkdocs(caminho: str, esperado: str) -> None:
    """MkDocs roda com use_directory_urls: pagina vira diretorio, index colapsa."""
    assert caminho_para_url(caminho) == esperado


def test_url_respeita_base_customizada() -> None:
    assert caminho_para_url("async.md", "http://localhost:8008") == "http://localhost:8008/async/"


@pytest.mark.parametrize(
    ("caminho", "e_doc"),
    [
        ("advanced/custom-response.md", True),
        ("index.md", True),
        ("_llm-test.md", False),
        ("release-notes.md", False),
        ("translation-banner.md", False),
    ],
)
def test_filtra_o_que_nao_e_documentacao(caminho: str, e_doc: bool) -> None:
    assert _e_documentacao(caminho) is e_doc

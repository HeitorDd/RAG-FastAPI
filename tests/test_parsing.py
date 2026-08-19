"""Testes da normalizacao do markdown do FastAPI."""

from __future__ import annotations

from pathlib import Path

from rag_docs.ingest.parsing import (
    limpar_anchors,
    normalizar_blocos,
    preparar,
    remover_frontmatter,
    resolver_includes,
    separar_anchor,
)


def test_remove_frontmatter() -> None:
    texto = "---\nhide:\n  - navigation\n---\n# Titulo\n"
    assert remover_frontmatter(texto) == "# Titulo\n"


def test_resolve_include_inteiro(tmp_path: Path) -> None:
    base = tmp_path / "docs" / "en"
    base.mkdir(parents=True)
    alvo = tmp_path / "docs_src" / "app.py"
    alvo.parent.mkdir(parents=True)
    alvo.write_text("app = FastAPI()\n", encoding="utf-8")

    texto, resolvidos, perdidos = resolver_includes("{* ../../docs_src/app.py *}", base)

    assert resolvidos == 1
    assert perdidos == 0
    assert texto == "```python\napp = FastAPI()\n```"


def test_resolve_include_com_intervalo_de_linhas(tmp_path: Path) -> None:
    base = tmp_path / "docs" / "en"
    base.mkdir(parents=True)
    alvo = tmp_path / "docs_src" / "app.py"
    alvo.parent.mkdir(parents=True)
    alvo.write_text("um\ndois\ntres\nquatro\n", encoding="utf-8")

    texto, _, _ = resolver_includes("{* ../../docs_src/app.py ln[2:3] hl[2] *}", base)

    assert texto == "```python\ndois\ntres\n```"


def test_include_perdido_nao_derruba_a_ingestao(tmp_path: Path) -> None:
    base = tmp_path / "docs" / "en"
    base.mkdir(parents=True)

    texto, resolvidos, perdidos = resolver_includes("antes {* ../../nao/existe.py *} depois", base)

    assert (resolvidos, perdidos) == (0, 1)
    assert texto == "antes  depois"


def test_include_preserva_indentacao(tmp_path: Path) -> None:
    """Codigo Python sem indentacao e codigo invalido."""
    base = tmp_path / "docs" / "en"
    base.mkdir(parents=True)
    alvo = tmp_path / "docs_src" / "app.py"
    alvo.parent.mkdir(parents=True)
    alvo.write_text('def f():\n    return {"ok": True}\n', encoding="utf-8")

    texto, _, _ = resolver_includes("{* ../../docs_src/app.py *}", base)

    assert '    return {"ok": True}' in texto


def test_normaliza_blocos_em_prosa() -> None:
    texto = "/// note\n\nCuidado.\n\n///\n"
    assert "Note:" in normalizar_blocos(texto)


def test_bloco_com_titulo_mantem_o_titulo() -> None:
    assert "Note (Technical Details):" in normalizar_blocos("/// note | Technical Details\n")


def test_aba_vira_so_o_titulo() -> None:
    """A palavra "tab" e layout, nao conteudo."""
    saida = normalizar_blocos("//// tab | Python 3.10+\n")
    assert saida.strip() == "Python 3.10+:"


def test_separa_anchor_do_titulo() -> None:
    assert separar_anchor("HTML Response { #html-response }") == ("HTML Response", "html-response")


def test_titulo_sem_anchor() -> None:
    assert separar_anchor("Sem Anchor") == ("Sem Anchor", None)


def test_limpa_anchors_residuais() -> None:
    assert limpar_anchors("#### Sub { #sub-slug }") == "#### Sub"


def test_preparar_remove_comentario_html(tmp_path: Path) -> None:
    base = tmp_path / "docs" / "en"
    base.mkdir(parents=True)
    resultado = preparar("antes <!-- sponsors --> depois", base)
    assert "sponsors" not in resultado.texto

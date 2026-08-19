"""Coleta das docs do FastAPI a partir do repositorio oficial.

A URL de origem e resolvida aqui, na coleta, e nao depois: todo chunk carrega a
URL do documento pai desde o nascimento. Reconstruir isso a jusante seria
adivinhacao.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_PADRAO = "https://github.com/fastapi/fastapi.git"
URL_BASE_PADRAO = "https://fastapi.tiangolo.com"

# Subarvores necessarias. `docs/en` traz o markdown; `docs_src` e `fastapi`
# sao alvos dos includes de codigo -- sem eles 440 exemplos entram vazios.
SUBARVORES = ("docs/en", "docs_src", "fastapi")

# Paginas que estao no site mas nao sao documentacao consultavel:
#
# - release-notes.md: 710 KB de changelog ("Fix typo. PR #123 by "), 47%
#   de todo o corpus em bytes. Dominaria a recuperacao com ruido de PR para
#   qualquer pergunta que mencione o nome de uma feature.
# - translation-banner.md: fragmento incluido em outras paginas, nao e pagina.
# - Arquivos com prefixo "_" sao excluidos pelo proprio MkDocs (_llm-test.md e
#   fixture do pipeline de traducao, nao documentacao).
ARQUIVOS_IGNORADOS = frozenset({"release-notes.md", "translation-banner.md"})

# Onde o markdown mora dentro do repositorio.
DIR_DOCS = Path("docs/en/docs")

# Base de resolucao dos includes: o diretorio do mkdocs.yml. Um include escrito
# como "../../docs_src/x.py" sobe dois niveis a partir daqui e cai na raiz do
# repositorio -- por isso o prefixo e sempre o mesmo, independente da
# profundidade do arquivo .md que o contem.
DIR_BASE_INCLUDES = Path("docs/en")


@dataclass(frozen=True, slots=True)
class Documento:
    """Um arquivo de documentacao, ja com a URL publica resolvida."""

    caminho: Path
    """Caminho absoluto do .md no clone local."""

    caminho_relativo: str
    """Caminho relativo a DIR_DOCS, ex.: "advanced/custom-response.md"."""

    url: str
    """URL publica da pagina, ex.: "https://fastapi.tiangolo.com/advanced/custom-response/"."""

    texto: str
    """Conteudo bruto do arquivo."""


def _git(*args: str, cwd: Path | None = None) -> str:
    """Roda git e devolve a saida, estourando com a mensagem real se falhar."""
    resultado = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        # Sem encoding explicito, o Python decodifica na codepage do sistema
        # (cp1252 no Windows) e a saida do git com qualquer byte UTF-8 estoura
        # na thread leitora, silenciosamente perdendo stdout.
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} falhou: {resultado.stderr.strip()}")
    return resultado.stdout.strip()


def clonar_ou_atualizar(destino: Path, repo: str = REPO_PADRAO, ref: str | None = None) -> str:
    """Garante um clone raso e esparso em `destino` e devolve o SHA coletado.

    Clone raso com sparse checkout: o repositorio inteiro passa de 200 MB e nao
    precisamos de nada alem das docs e dos exemplos referenciados por elas.
    """
    if (destino / ".git").is_dir():
        logger.info("clone existente em %s, atualizando", destino)
        _git("fetch", "--depth", "1", "origin", ref or "HEAD", cwd=destino)
        _git("checkout", "--force", "FETCH_HEAD", cwd=destino)
    else:
        logger.info("clonando %s em %s", repo, destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        args = ["clone", "--depth", "1", "--filter=blob:none", "--sparse"]
        if ref:
            args += ["--branch", ref]
        _git(*args, repo, str(destino))
        _git("sparse-checkout", "set", *SUBARVORES, cwd=destino)

    sha = _git("rev-parse", "HEAD", cwd=destino)
    logger.info("docs coletadas no commit %s", sha)
    return sha


def caminho_para_url(caminho_relativo: str, url_base: str = URL_BASE_PADRAO) -> str:
    """Traduz o caminho do markdown para a URL publica do MkDocs.

    O MkDocs roda com `use_directory_urls`, entao a pagina vira um diretorio e
    `index.md` colapsa no diretorio que o contem.
    """
    caminho = caminho_relativo.removesuffix(".md").replace("\\", "/")
    if caminho == "index":
        return f"{url_base}/"
    caminho = caminho.removesuffix("/index")
    return f"{url_base}/{caminho}/"


def _e_documentacao(caminho_relativo: str) -> bool:
    """Filtra o que esta no site mas nao responde pergunta de usuario."""
    nome = caminho_relativo.rsplit("/", 1)[-1]
    return not nome.startswith("_") and caminho_relativo not in ARQUIVOS_IGNORADOS


def coletar(
    raiz: Path,
    url_base: str = URL_BASE_PADRAO,
    incluir_tudo: bool = False,
) -> list[Documento]:
    """Le os .md das docs, em ordem estavel, com a URL ja resolvida."""
    dir_docs = raiz / DIR_DOCS
    if not dir_docs.is_dir():
        raise FileNotFoundError(f"diretorio de docs nao encontrado: {dir_docs}")

    documentos: list[Documento] = []
    for caminho in sorted(dir_docs.rglob("*.md")):
        relativo = caminho.relative_to(dir_docs).as_posix()
        if not incluir_tudo and not _e_documentacao(relativo):
            logger.debug("ignorando (nao e documentacao): %s", relativo)
            continue
        documentos.append(
            Documento(
                caminho=caminho,
                caminho_relativo=relativo,
                url=caminho_para_url(relativo, url_base),
                texto=caminho.read_text(encoding="utf-8"),
            )
        )
    logger.info("%d documentos coletados", len(documentos))
    return documentos

"""Normalizacao do markdown das docs do FastAPI.

O markdown do FastAPI usa tres construcoes proprias que precisam ser resolvidas
antes do chunking, senao o trecho recuperado nao sustenta resposta nenhuma:

1. `{* ../../docs_src/x.py ln[15:17] *}` -- o codigo nao esta no markdown, mora
   em arquivo separado. Sao 440 ocorrencias. Sem resolver, o chunk que fala
   "use StreamingResponse assim" nao contem nenhum "assim".
2. `/// note` ... `///` -- blocos do pymdownx. Crus, entram como ruido.
3. `## Titulo { #slug }` -- anchor explicito do header, que vira o fragmento da
   URL de citacao. Preservado aqui e consumido no chunking.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_RE_COMENTARIO_HTML = re.compile(r"<!--.*?-->", re.DOTALL)

_RE_FRONTMATTER = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)

# {* caminho [ln[a:b]] [hl[...]] *}
_RE_INCLUDE = re.compile(r"\{\*\s*(?P<caminho>\S+)(?P<opcoes>[^*]*?)\*\}")
_RE_INTERVALO = re.compile(r"ln\[(?P<inicio>\d+):(?P<fim>\d+)\]")

# Abertura de bloco: "/// note", "/// note | Titulo", "//// tab | Python 3.10+".
_RE_ABRE_BLOCO = re.compile(
    r"^(?P<barras>/{3,})\s+(?P<tipo>[a-z-]+)\s*(?:\|\s*(?P<titulo>.+?))?\s*$"
)
_RE_FECHA_BLOCO = re.compile(r"^/{3,}\s*$")

# "## Titulo { #slug }"
_RE_HEADER_ANCHOR = re.compile(
    r"^(?P<hashes>#{1,6})\s+(?P<titulo>.*?)\s*\{\s*#(?P<slug>[\w-]+)\s*\}\s*$"
)
_RE_ANCHOR_SOLTO = re.compile(r"\s*\{\s*#[\w-]+\s*\}\s*$", re.MULTILINE)

_LINGUAGEM_POR_EXTENSAO = {
    ".py": "python",
    ".sh": "bash",
    ".console": "console",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".html": "html",
    ".md": "markdown",
    ".txt": "text",
}

_ROTULOS = {
    "note": "Note",
    "tip": "Tip",
    "warning": "Warning",
    "danger": "Danger",
    "info": "Info",
    "check": "Check",
    "details": "Details",
    "abstract": "Abstract",
    "example": "Example",
    "quote": "Quote",
}


@dataclass(slots=True)
class ResultadoParsing:
    """Markdown normalizado e o que aconteceu no caminho."""

    texto: str
    includes_resolvidos: int = 0
    includes_perdidos: int = 0


def remover_frontmatter(texto: str) -> str:
    """Tira o bloco YAML do topo, que e metadado de build e nao conteudo."""
    return _RE_FRONTMATTER.sub("", texto)


def _linguagem(caminho: Path) -> str:
    return _LINGUAGEM_POR_EXTENSAO.get(caminho.suffix, "")


def _recortar(conteudo: str, opcoes: str) -> str:
    """Aplica `ln[a:b]` quando presente. Sem intervalo, o arquivo inteiro entra."""
    intervalo = _RE_INTERVALO.search(opcoes)
    if intervalo is None:
        return conteudo.rstrip()
    inicio = int(intervalo.group("inicio"))
    fim = int(intervalo.group("fim"))
    linhas = conteudo.splitlines()
    return "\n".join(linhas[inicio - 1 : fim]).rstrip()


def resolver_includes(texto: str, base: Path) -> tuple[str, int, int]:
    """Substitui cada `{* ... *}` pelo codigo real, cercado em bloco.

    `base` e o diretorio do mkdocs.yml (docs/en): os caminhos dos includes sao
    relativos a ele, e nao ao arquivo .md que os contem -- por isso o prefixo
    "../../" aparece igual em documentos de profundidades diferentes.
    """
    resolvidos = 0
    perdidos = 0

    def _substituir(casamento: re.Match[str]) -> str:
        nonlocal resolvidos, perdidos
        caminho = (base / casamento.group("caminho")).resolve()
        if not caminho.is_file():
            perdidos += 1
            logger.warning("include nao resolvido: %s", casamento.group("caminho"))
            return ""
        trecho = _recortar(caminho.read_text(encoding="utf-8"), casamento.group("opcoes"))
        resolvidos += 1
        return f"```{_linguagem(caminho)}\n{trecho}\n```"

    return _RE_INCLUDE.sub(_substituir, texto), resolvidos, perdidos


def normalizar_blocos(texto: str) -> str:
    """Converte os blocos `///` em prosa, preservando o sentido do rotulo.

    "/// note | Technical Details" vira "Note (Technical Details):", e as abas
    "//// tab | Python 3.10+" viram so o titulo -- a palavra "tab" e layout,
    nao conteudo.
    """
    saida: list[str] = []
    for linha in texto.splitlines():
        abertura = _RE_ABRE_BLOCO.match(linha)
        if abertura is not None:
            tipo = abertura.group("tipo")
            titulo = abertura.group("titulo")
            if tipo == "tab":
                saida.append(f"{titulo}:" if titulo else "")
            else:
                rotulo = _ROTULOS.get(tipo, tipo.capitalize())
                saida.append(f"{rotulo} ({titulo}):" if titulo else f"{rotulo}:")
            continue
        if _RE_FECHA_BLOCO.match(linha):
            saida.append("")
            continue
        saida.append(linha)
    return "\n".join(saida)


def separar_anchor(titulo: str) -> tuple[str, str | None]:
    """Separa "Titulo { #slug }" em ("Titulo", "slug")."""
    casamento = _RE_HEADER_ANCHOR.match(f"# {titulo}")
    if casamento is None:
        return titulo.strip(), None
    return casamento.group("titulo"), casamento.group("slug")


def limpar_anchors(texto: str) -> str:
    """Remove anchors residuais de headers que nao viraram ponto de corte."""
    return _RE_ANCHOR_SOLTO.sub("", texto)


def preparar(texto: str, base_includes: Path) -> ResultadoParsing:
    """Normaliza um documento inteiro, mantendo os anchors para o chunking."""
    limpo = remover_frontmatter(texto)
    limpo = _RE_COMENTARIO_HTML.sub("", limpo)
    limpo, resolvidos, perdidos = resolver_includes(limpo, base_includes)
    limpo = normalizar_blocos(limpo)
    return ResultadoParsing(
        texto=limpo,
        includes_resolvidos=resolvidos,
        includes_perdidos=perdidos,
    )

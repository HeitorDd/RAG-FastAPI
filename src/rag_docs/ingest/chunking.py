"""Chunking nos cabecalhos, com a trilha de titulos prefixada.

O corte e nos headers porque e onde a documentacao ja separa assunto. E cada
chunk recebe prefixada a trilha completa ("FastAPI > Advanced > Custom Response
> HTML Response") porque, isolado, o texto usa pronomes sem referente: "voce
pode passar isso como parametro" nao diz nada sobre o que e "isso".
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from langchain_text_splitters import (
    Language,
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from rag_docs.ingest.coleta import Documento
from rag_docs.ingest.parsing import limpar_anchors, preparar, separar_anchor

logger = logging.getLogger(__name__)

TAMANHO_CHUNK = 1200
SOBREPOSICAO = 120
"""~10% de sobreposicao: o bastante para uma frase cortada na fronteira
sobreviver inteira em um dos dois lados."""

TAMANHO_MINIMO_CONTEUDO = 50
"""Abaixo disso o trecho e residuo de formatacao ("Test:", "image_base64 ="):
nao sustenta resposta e so ocupa espaco no funil de recuperacao."""

RAIZ_TRILHA = "FastAPI"
SEPARADOR_TRILHA = " > "

_NIVEIS = [("#", "h1"), ("##", "h2"), ("###", "h3")]

_RE_BLOCO_CODIGO = re.compile(r"```[^\n]*\n.*?```", re.DOTALL)
_SENTINELA = "@@CODIGO-{}@@"


def _proteger_codigo(texto: str) -> tuple[str, list[str]]:
    """Troca cada bloco de codigo por uma sentinela de uma linha.

    O MarkdownHeaderTextSplitter remove o espaco a esquerda de toda linha que
    processa, inclusive dentro de blocos cercados -- e exemplo de Python sem
    indentacao e codigo invalido, que e o pior defeito possivel num RAG de
    documentacao de Python. Como a sentinela e uma unica linha sem recuo, ela
    atravessa o divisor intacta e o codigo volta byte a byte depois. A sentinela
    e ASCII de proposito: bytes de controle como \x00 sao engolidos pelo divisor.

    Efeito colateral util: com o codigo fora do caminho, um "#" de comentario
    Python tambem nao tem como ser confundido com cabecalho.
    """
    blocos: list[str] = []

    def _guardar(casamento: re.Match[str]) -> str:
        blocos.append(casamento.group(0))
        return _SENTINELA.format(len(blocos) - 1)

    return _RE_BLOCO_CODIGO.sub(_guardar, texto), blocos


def _restaurar_codigo(texto: str, blocos: list[str]) -> str:
    """Devolve os blocos guardados por _proteger_codigo aos seus lugares."""
    for indice, bloco in enumerate(blocos):
        texto = texto.replace(_SENTINELA.format(indice), bloco)
    return texto


@dataclass(frozen=True, slots=True)
class Chunk:
    """Trecho pronto para embedding e gravacao."""

    texto: str
    """Ja com a trilha de titulos prefixada."""

    url: str
    """URL de citacao, com o anchor da secao quando existe."""

    documento_url: str
    """URL da pagina, sem anchor. Identidade do documento pai."""

    secao: str
    """Trilha de titulos."""

    posicao: int
    """Ordem dentro do documento pai."""


def _titulos_do_caminho(caminho_relativo: str) -> list[str]:
    """Deriva a secao a partir dos diretorios: "advanced/x.md" -> ["Advanced"]."""
    partes = caminho_relativo.split("/")[:-1]
    return [parte.replace("-", " ").replace("_", " ").title() for parte in partes]


def _montar_trilha(partes: list[str]) -> str:
    """Junta a trilha removendo repeticoes consecutivas e vazios."""
    trilha: list[str] = []
    for parte in partes:
        limpo = parte.strip()
        if limpo and (not trilha or trilha[-1].lower() != limpo.lower()):
            trilha.append(limpo)
    return SEPARADOR_TRILHA.join(trilha)


def chunk_documento(documento: Documento, base_includes: Path) -> list[Chunk]:
    """Normaliza, corta nos headers e devolve os chunks do documento."""
    resultado = preparar(documento.texto, base_includes)
    if resultado.includes_perdidos:
        logger.warning(
            "%s: %d includes nao resolvidos",
            documento.caminho_relativo,
            resultado.includes_perdidos,
        )

    divisor_headers = MarkdownHeaderTextSplitter(_NIVEIS, strip_headers=True)
    divisor_tamanho = RecursiveCharacterTextSplitter.from_language(
        Language.MARKDOWN,
        chunk_size=TAMANHO_CHUNK,
        chunk_overlap=SOBREPOSICAO,
    )

    prefixo_caminho = _titulos_do_caminho(documento.caminho_relativo)
    protegido, blocos = _proteger_codigo(resultado.texto)

    chunks: list[Chunk] = []
    posicao = 0

    for secao in divisor_headers.split_text(protegido):
        titulos: list[str] = []
        slug: str | None = None
        for _, chave in _NIVEIS:
            bruto = secao.metadata.get(chave)
            if not bruto:
                continue
            titulo, slug_nivel = separar_anchor(str(bruto))
            titulos.append(titulo)
            # O anchor da citacao e o do header mais profundo da secao.
            if slug_nivel:
                slug = slug_nivel

        trilha = _montar_trilha([RAIZ_TRILHA, *prefixo_caminho, *titulos])
        url = f"{documento.url}#{slug}" if slug else documento.url

        corpo = _restaurar_codigo(limpar_anchors(secao.page_content), blocos).strip()
        if not corpo:
            continue

        for pedaco in divisor_tamanho.split_text(corpo):
            texto = pedaco.strip()
            if len(texto) < TAMANHO_MINIMO_CONTEUDO:
                continue
            chunks.append(
                Chunk(
                    texto=f"{trilha}\n\n{texto}",
                    url=url,
                    documento_url=documento.url,
                    secao=trilha,
                    posicao=posicao,
                )
            )
            posicao += 1

    return chunks

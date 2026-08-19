# Assistente de documentacao com RAG

Chat que responde perguntas sobre a documentacao do FastAPI sem inventar: toda
afirmacao da resposta vem de um trecho recuperado e cita a fonte. Quando o
acervo nao sustenta a resposta, o sistema diz que nao encontrou.

> Em construcao. **Fases 1 (fundacao) e 2 (ingestao) concluidas.** O README completo — diagrama
> de arquitetura, metricas antes/depois e a secao "onde ele falha" — sai na
> Fase 7.

## Stack

Python 3.12 (`uv`) · FastAPI + Pydantic v2 · Postgres 17 + pgvector ·
LangChain (apenas os text splitters) · OpenAI `text-embedding-3-small` ·
Cohere Rerank · Langfuse self-hosted · ruff + mypy `--strict` + pytest.

Sem banco vetorial separado: vetor denso e indice lexical moram na mesma linha
da mesma tabela do Postgres.

## Subir tudo

```bash
cp .env.example .env   # preencha OPENAI_API_KEY e COHERE_API_KEY quando chegar a Fase 2
docker compose up --build
```

| Servico       | URL                          |
| ------------- | ---------------------------- |
| API           | http://localhost:8000/health |
| Docs da API   | http://localhost:8000/docs   |
| Langfuse      | http://localhost:3000        |

O Langfuse ja sobe com organizacao, projeto, usuario e chaves provisionados a
partir do `.env` — nao ha passo manual na UI. Login com
`LANGFUSE_INIT_USER_EMAIL` / `LANGFUSE_INIT_USER_PASSWORD`.

A ordem de subida e garantida pelo compose: `db` saudavel → `migrate` roda ate
o fim → `api` sobe. O `/health` so retorna `200` com banco **e** pgvector
respondendo; caso contrario, `503` com a causa em `detalhe`.

## Desenvolvimento local

```bash
uv sync                              # cria o .venv a partir do uv.lock
docker compose up -d db              # so o Postgres
uv run python -m rag_docs.migrate    # aplica as migracoes (idempotente)
uv run uvicorn rag_docs.main:app --reload
```

## Ingestao

```bash
uv run python -m rag_docs.ingest --dry-run   # inspeciona o corpus sem gastar credito
uv run python -m rag_docs.ingest             # coleta, fatia, embeda e grava
```

Rodar duas vezes nao duplica: o upsert usa a chave natural
`(documento_url, posicao)` e os `id` sobrevivem. Se um documento encolheu entre
duas ingestoes, os chunks excedentes da versao anterior sao removidos na mesma
transacao -- sem isso eles ficariam recuperaveis para sempre.

Flags uteis: `--limit N` (processa so os N primeiros documentos), `--ref`
(branch ou tag das docs), `--incluir-tudo` (nao filtra release-notes nem
paginas auxiliares).

### O que o pipeline faz com o markdown

As docs do FastAPI tem tres construcoes que precisam de tratamento antes do
chunking:

| Construcao | Ocorrencias | Tratamento |
| --- | --- | --- |
| `{* ../../docs_src/x.py ln[15:17] *}` | 440 | codigo real inserido como bloco cercado |
| `/// note`, `//// tab` | 480 | convertidos em prosa |
| `## Titulo { #slug }` | 1102 | anchor vira o fragmento da URL de citacao |

O caminho do include e relativo ao diretorio do `mkdocs.yml` (`docs/en`), nao ao
arquivo que o contem.

Nao entram no acervo: `release-notes.md` (710 KB de changelog, 47% do corpus em
bytes), `translation-banner.md` (fragmento, nao pagina) e arquivos com prefixo
`_` (excluidos pelo proprio MkDocs).

Corpus resultante: **151 documentos, 1435 chunks**, mediana de 707 caracteres,
95% com anchor de secao.

Qualidade:

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest

# Testes de integracao contra Postgres real (pulados sem a variavel):
RAG_TEST_DATABASE_URL=postgresql://rag:...@localhost:5432/rag uv run pytest
```

## Estrutura

```
src/rag_docs/
  config.py          configuracao tipada, lida so do ambiente
  db.py              pool asyncpg + codec do tipo vector
  migrate.py         executor de migracoes (CLI)
  main.py            app FastAPI + /health
  models.py          schemas Pydantic v2
  observability.py   cliente Langfuse (no-op sem chaves)
  embeddings.py      UNICO ponto de contato com o modelo de embedding
  ingest/
    coleta.py        clone das docs + resolucao da URL publica
    parsing.py       includes de codigo, blocos ///, anchors
    chunking.py      corte nos cabecalhos + trilha de titulos
    gravacao.py      upsert idempotente + limpeza de orfaos
    cli.py           python -m rag_docs.ingest
migrations/
  001_init.sql       tabela chunks, indice HNSW e indice GIN
  002_documento_url.sql  chave natural (documento_url, posicao)
```

## Esquema

Uma tabela, `chunks`:

| coluna      | tipo           | papel                                                       |
| ----------- | -------------- | ----------------------------------------------------------- |
| `id`        | `bigint`       | identidade; estavel entre re-ingestoes                       |
| `texto`     | `text`         | trecho com a trilha de titulos prefixada                     |
| `url`       | `text`         | URL do documento pai, capturada na coleta                    |
| `secao`     | `text`         | trilha de titulos (`FastAPI > Advanced > StreamingResponse`) |
| `posicao`   | `integer`      | ordem do chunk no documento                                  |
| `embedding` | `vector(1536)` | `text-embedding-3-small`                                     |
| `tsv`       | `tsvector`     | coluna **gerada** a partir de `texto`                        |
| `documento_url` | `text`     | URL da pagina sem anchor; identidade do documento pai         |

Indices: HNSW `vector_cosine_ops` sobre `embedding`, GIN sobre `tsv`.
Chave natural `UNIQUE (documento_url, posicao)` — e o que sustenta a ingestao
idempotente e mantem os `id` estaveis para os evals da Fase 4. `url` carrega o
anchor da secao (`.../custom-response/#html-response`) para a citacao apontar o
ponto exato.

## Fases

- [x] **1 — Fundacao.** Projeto, compose, migracoes, `/health`, Dockerfile.
- [x] **2 — Ingestao.** CLI: coleta → parsing → chunking → embeddings → gravacao.
- [ ] **3 — Consulta ingenua.** Densa, top-5, instrumentada no Langfuse.
- [ ] **4 — Avaliacao.** `evals/golden.jsonl`, recall@5 e MRR via pytest.
- [ ] **5 — Recuperacao hibrida.** BM25 + RRF + rerank, comparado com a Fase 3.
- [ ] **6 — Interface.** Streaming token a token e fontes como cartoes.
- [ ] **7 — Deploy.** Railway/Fly.io e README final.

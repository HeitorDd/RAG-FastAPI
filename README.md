# Assistente de documentacao com RAG

Chat que responde perguntas sobre a documentacao do FastAPI sem inventar: toda
afirmacao da resposta vem de um trecho recuperado e cita a fonte. Quando o
acervo nao sustenta a resposta, o sistema diz que nao encontrou.

> Em construcao. **Fase 1 (fundacao) concluida.** O README completo — diagrama
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

Qualidade:

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
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
migrations/
  001_init.sql       tabela chunks, indice HNSW e indice GIN
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

Indices: HNSW `vector_cosine_ops` sobre `embedding`, GIN sobre `tsv`.
Chave natural `UNIQUE (url, posicao)` — e o que sustenta a ingestao idempotente
da Fase 2 e mantem os `id` estaveis para os evals da Fase 4.

## Fases

- [x] **1 — Fundacao.** Projeto, compose, migracoes, `/health`, Dockerfile.
- [ ] **2 — Ingestao.** CLI: coleta → parsing → chunking → embeddings → gravacao.
- [ ] **3 — Consulta ingenua.** Densa, top-5, instrumentada no Langfuse.
- [ ] **4 — Avaliacao.** `evals/golden.jsonl`, recall@5 e MRR via pytest.
- [ ] **5 — Recuperacao hibrida.** BM25 + RRF + rerank, comparado com a Fase 3.
- [ ] **6 — Interface.** Streaming token a token e fontes como cartoes.
- [ ] **7 — Deploy.** Railway/Fly.io e README final.

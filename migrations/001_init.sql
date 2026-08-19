-- Fase 1: esquema base do acervo.
-- Uma unica tabela guarda texto, metadados, vetor denso e indice lexical.
-- Nada de banco vetorial separado: densa e BM25 leem da mesma linha.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Texto ja com a trilha de titulos prefixada
    -- ("FastAPI > Advanced > StreamingResponse"), porque isolado o trecho usa
    -- pronomes sem referente.
    texto      text         NOT NULL,

    -- URL do documento pai, capturada na coleta e carregada desde o nascimento
    -- do chunk. E o que a citacao numerada da resposta vai apontar.
    url        text         NOT NULL,

    -- Trilha de titulos em si, preservada a parte para exibir na fonte citada.
    secao      text         NOT NULL,

    -- Ordem do chunk dentro do documento pai.
    posicao    integer      NOT NULL,

    -- text-embedding-3-small: 1536 dimensoes.
    embedding  vector(1536) NOT NULL,

    -- Coluna gerada: e impossivel gravar texto sem o indice lexical
    -- correspondente ficar em dia. Docs do FastAPI sao em ingles.
    tsv        tsvector     GENERATED ALWAYS AS (to_tsvector('english', texto)) STORED,

    criado_em  timestamptz  NOT NULL DEFAULT now(),

    -- Chave natural do chunk. Sustenta o upsert idempotente da ingestao
    -- (Fase 2) e mantem os ids estaveis entre re-execucoes, o que os evals
    -- da Fase 4 dependem. Tambem serve as buscas por url.
    CONSTRAINT chunks_url_posicao_key UNIQUE (url, posicao),
    CONSTRAINT chunks_posicao_nao_negativa CHECK (posicao >= 0)
);

-- Busca densa: cosseno, casando com a metrica em que o modelo foi treinado.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Busca lexical (BM25 via ts_rank_cd na Fase 5).
CREATE INDEX IF NOT EXISTS chunks_tsv_gin_idx
    ON chunks USING gin (tsv);

-- Fase 2: a URL do chunk passa a carregar o anchor da secao
-- (".../advanced/custom-response/#html-response"), para a citacao levar o
-- leitor ao ponto exato em vez do topo de uma pagina longa.
--
-- Consequencia: `url` deixa de identificar o documento -- uma pagina vira
-- varias urls. A identidade do chunk passa a ser (documento_url, posicao), e a
-- limpeza de orfaos precisa da url da pagina para saber o que sobrou de uma
-- ingestao anterior.

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS documento_url text;

UPDATE chunks SET documento_url = split_part(url, '#', 1) WHERE documento_url IS NULL;

ALTER TABLE chunks ALTER COLUMN documento_url SET NOT NULL;

ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_url_posicao_key;

ALTER TABLE chunks
    ADD CONSTRAINT chunks_documento_posicao_key UNIQUE (documento_url, posicao);

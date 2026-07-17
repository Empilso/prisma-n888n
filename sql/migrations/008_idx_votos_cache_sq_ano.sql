-- 008: índice por candidato em tse_votos_cache
--
-- Suporta o modo performance do mapa territorial de deputado
-- (Forbes: GET /api/campaign/{id}/territory/polling-places, que agrega
-- SUM(qt_votos) por município filtrando sq_candidato + ano_eleicao) e os
-- joins por sq_candidato já existentes em politicos.py. Sem ele, a
-- agregação varre a fatia inteira da UF/ano (~5M linhas em SP/2022):
-- minutos em HD → 0,35s com o índice.
--
-- Aplicada no Postgres local em 2026-07-17. Rodar também na VPS
-- (CONCURRENTLY não pode rodar dentro de transação — aplicar via psql direto).

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_votos_cache_sq_ano
    ON tse_votos_cache (sq_candidato, ano_eleicao);

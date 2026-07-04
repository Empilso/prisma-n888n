-- ============================================================
-- VERIFICACAO COMPLETA — receitas_campanha
-- ============================================================

-- 1. Totais por ano
SELECT '--- 1. TOTAIS POR ANO ---' as secao;
SELECT
    ano_eleicao,
    COUNT(*)                                              AS total,
    COUNT(politico_id)                                    AS com_politico_id,
    ROUND(COUNT(politico_id)::numeric/COUNT(*)*100, 1)    AS pct_linkados,
    COUNT(DISTINCT doador_cnpj_cpf)                       AS doadores_unicos,
    SUM(valor)::bigint                                    AS total_R$,
    ROUND(AVG(valor), 2)                                  AS media_doacao
FROM receitas_campanha
GROUP BY ano_eleicao
ORDER BY ano_eleicao;

-- 2. Registros sem politico_id por ano/UF
SELECT '--- 2. SEM POLITICO_ID (TOP 10) ---' as secao;
SELECT ano_eleicao, uf, COUNT(*) AS sem_id
FROM receitas_campanha
WHERE politico_id IS NULL
GROUP BY ano_eleicao, uf
ORDER BY sem_id DESC
LIMIT 10;

-- 3. Duplicatas de prisma_id
SELECT '--- 3. DUPLICATAS PRISMA_ID ---' as secao;
SELECT COUNT(*) AS duplicatas
FROM (
    SELECT prisma_id, COUNT(*) c
    FROM receitas_campanha
    WHERE prisma_id IS NOT NULL
    GROUP BY prisma_id HAVING COUNT(*) > 1
) x;

-- 4. Valores suspeitos
SELECT '--- 4. VALORES SUSPEITOS ---' as secao;
SELECT
    COUNT(*) FILTER (WHERE valor = 0)         AS valor_zero,
    COUNT(*) FILTER (WHERE valor > 10000000)  AS acima_10M,
    COUNT(*) FILTER (WHERE valor IS NULL)     AS valor_nulo,
    COUNT(*) FILTER (WHERE data_receita < '2000-01-01') AS data_antiga,
    COUNT(*) FILTER (WHERE data_receita > NOW())        AS data_futura
FROM receitas_campanha;

-- 5. Maiores doadores (Top 10 por valor total)
SELECT '--- 5. MAIORES DOADORES ---' as secao;
SELECT doador_nome, doador_cnpj_cpf,
    COUNT(*) AS num_doacoes,
    SUM(valor)::bigint AS total_doado,
    COUNT(DISTINCT politico_id) AS politicos_financiados
FROM receitas_campanha
WHERE doador_cnpj_cpf IS NOT NULL
GROUP BY doador_nome, doador_cnpj_cpf
ORDER BY total_doado DESC
LIMIT 10;

-- 6. Cobertura por UF (anos carregados)
SELECT '--- 6. UFs COM DADOS ---' as secao;
SELECT uf, array_agg(ano_eleicao ORDER BY ano_eleicao) AS anos, SUM(total)::bigint AS registros
FROM (
    SELECT uf, ano_eleicao, COUNT(*) AS total
    FROM receitas_campanha
    GROUP BY uf, ano_eleicao
) x
GROUP BY uf
ORDER BY uf;

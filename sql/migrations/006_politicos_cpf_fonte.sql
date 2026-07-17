-- Migration 006: proveniência do CPF em politicos
--
-- A partir de 2024 o TSE mascara NR_CPF_CANDIDATO no arquivo de candidatura
-- (valor literal "-4" = dado restrito, confirmado em SP/RJ/BA/MG/AC — 100%
-- das linhas). Isso deixou 463.590 registros de 2024 sem CPF.
--
-- Recuperamos parte via cross-reference com receitas_campanha (prestação de
-- contas, NÃO mascarada — exigência legal de transparência de doador é
-- diferente da de candidatura): quando o candidato doou para a própria
-- campanha, doador_nome bate exato com nome_completo OU seve o padrão
-- "ELEICAO {ano} {nome} {cargo}" que o TSE usa para a conta do próprio
-- candidato. Regra rígida (nome idêntico, não similaridade), validada por
-- amostra manual — 20/20 corretos. 138.471 registros recuperados desse jeito.
--
-- cpf_fonte deixa explícito a proveniência para nunca tratar os dois grupos
-- como igualmente "oficiais" sem ressalva — ver .context/MASTER_CONTEXT.md
-- sessão 2026-07-08.

ALTER TABLE politicos
    ADD COLUMN IF NOT EXISTS cpf_fonte TEXT;

-- Marca os já existentes (candidatura TSE, mascarado só a partir de 2024)
UPDATE politicos SET cpf_fonte = 'tse_candidatura' WHERE cpf IS NOT NULL AND cpf_fonte IS NULL;

COMMENT ON COLUMN politicos.cpf_fonte IS
    'Proveniência do CPF: tse_candidatura (arquivo oficial de candidatura) '
    'ou receitas_campanha_autofinanciamento (recuperado via prestação de '
    'contas quando o candidato doou para a própria campanha, nome idêntico '
    'confirmado — usado só para 2024, onde a candidatura vem mascarada).';

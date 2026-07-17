#!/usr/bin/env python3
"""Agent C — Loader TSE: Prata → tabela politicos"""
import json, argparse, psycopg2
from pathlib import Path
from datetime import datetime, timezone
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")


BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
PRATA_DIR = BASE_DIR / "data/raw/tse/candidatos/prata"

DB = dict(host='localhost', port=5432, dbname='prisma_data', user='postgres', password=DB_PASSWORD)

UPSERT_SQL = """
INSERT INTO politicos (
    id_tse, politico_id, cpf, nome_urna, nome_completo, partido, sigla_partido,
    uf, cargo, cd_cargo, municipio_ibge, nm_ue, status_eleicao,
    nr_candidato, sq_candidato, ano_eleicao, turno,
    genero, grau_instrucao, estado_civil, cor_raca, ocupacao,
    data_nascimento, uf_nascimento, nr_titulo,
    tipo_eleicao, ds_eleicao, dt_eleicao, abrangencia,
    nr_federacao, nm_federacao, sg_federacao,
    nm_coligacao, tp_agremiacao, email
) VALUES (
    %(id_tse)s, %(politico_id)s, %(cpf)s, %(nome_urna)s, %(nome_completo)s, %(partido)s, %(sigla_partido)s,
    %(uf)s, %(cargo)s, %(cd_cargo)s, %(municipio_ibge)s, %(nm_ue)s, %(status_eleicao)s,
    %(nr_candidato)s, %(sq_candidato)s, %(ano_eleicao)s, %(turno)s,
    %(genero)s, %(grau_instrucao)s, %(estado_civil)s, %(cor_raca)s, %(ocupacao)s,
    %(data_nascimento)s, %(uf_nascimento)s, %(nr_titulo)s,
    %(tipo_eleicao)s, %(ds_eleicao)s, %(dt_eleicao)s, %(abrangencia)s,
    %(nr_federacao)s, %(nm_federacao)s, %(sg_federacao)s,
    %(nm_coligacao)s, %(tp_agremiacao)s, %(email)s
)
ON CONFLICT (id_tse, ano_eleicao, uf) DO UPDATE SET
    politico_id     = CASE 
                        WHEN politicos.cpf IS NOT NULL THEN politicos.politico_id
                        ELSE EXCLUDED.politico_id 
                      END,
    nome_urna       = EXCLUDED.nome_urna,
    nome_completo   = EXCLUDED.nome_completo,
    partido         = EXCLUDED.partido,
    sigla_partido   = EXCLUDED.sigla_partido,
    status_eleicao  = EXCLUDED.status_eleicao,
    genero          = EXCLUDED.genero,
    grau_instrucao  = EXCLUDED.grau_instrucao,
    estado_civil    = EXCLUDED.estado_civil,
    cor_raca        = EXCLUDED.cor_raca,
    ocupacao        = EXCLUDED.ocupacao,
    data_nascimento = EXCLUDED.data_nascimento,
    updated_at      = now();
"""

ETL_LOG = """
INSERT INTO etl_log (portal, fase, status, total_registros, registros_novos,
                     erro_mensagem, duracao_seg, iniciado_em, finalizado_em)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s);
"""

# Fase 4 da migração de identidade (RELATORIO_MIGRACAO_IDENTIDADE_20260413.md):
# toda carga resolve pessoa_id dos registros novos. Idempotente — só toca
# linhas com pessoa_id IS NULL. Mesma cadeia da Fase 3: cpf_hash → alias →
# nome+data → criar pessoa nova (OK / VEREADOR_TSE_BUG / SEM_CPF).
RESOLVER_PESSOAS_SQL = [
    # (cpf_hash é coluna GENERATED — o banco calcula sozinho a partir do cpf)
    # 1. link por CPF limpo
    """UPDATE politicos p SET pessoa_id = pe.id
       FROM pessoas pe
       WHERE p.pessoa_id IS NULL AND pe.cpf_hash IS NOT NULL
         AND p.cpf_hash = pe.cpf_hash AND pe.status = 'OK';""",
    # 2. link por alias de CPF
    """UPDATE politicos p SET pessoa_id = a.pessoa_id
       FROM pessoas_cpf_aliases a
       WHERE p.pessoa_id IS NULL AND p.cpf_hash = a.cpf_hash;""",
    # 3. link por nome+data
    """UPDATE politicos p SET pessoa_id = pe.id
       FROM pessoas pe
       WHERE p.pessoa_id IS NULL
         AND lower(trim(unaccent(p.nome_completo))) = pe.nome_canonical
         AND p.data_nascimento = pe.data_nascimento;""",
    # 4a. criar pessoas: cpf_hash limpo (1 identidade por hash)
    """INSERT INTO pessoas (cpf_hash, nome_canonical, data_nascimento, confianca, status, fonte)
       SELECT cpf_hash, min(lower(trim(unaccent(nome_completo)))), min(data_nascimento),
              2, 'OK', 'etl_tse_candidatos'
       FROM politicos
       WHERE pessoa_id IS NULL AND cpf_hash IS NOT NULL
       GROUP BY cpf_hash
       HAVING count(DISTINCT (lower(trim(unaccent(nome_completo))), data_nascimento)) = 1
       ON CONFLICT DO NOTHING;""",
    """UPDATE politicos p SET pessoa_id = pe.id
       FROM pessoas pe
       WHERE p.pessoa_id IS NULL AND pe.cpf_hash IS NOT NULL
         AND p.cpf_hash = pe.cpf_hash AND pe.fonte = 'etl_tse_candidatos';""",
    # 4b. cpf em colisão (bug TSE) → pessoa por nome+data, sem hash
    """INSERT INTO pessoas (cpf_hash, nome_canonical, data_nascimento, confianca, status, fonte)
       SELECT NULL, lower(trim(unaccent(nome_completo))), data_nascimento,
              1, 'VEREADOR_TSE_BUG', 'etl_tse_candidatos'
       FROM politicos
       WHERE pessoa_id IS NULL AND cpf_hash IS NOT NULL
       GROUP BY 2, 3
       ON CONFLICT DO NOTHING;""",
    # 4c. sem CPF → pessoa por nome+data
    """INSERT INTO pessoas (cpf_hash, nome_canonical, data_nascimento, confianca, status, fonte)
       SELECT NULL, lower(trim(unaccent(nome_completo))), data_nascimento,
              1, 'SEM_CPF', 'etl_tse_candidatos'
       FROM politicos
       WHERE pessoa_id IS NULL AND cpf_hash IS NULL
       GROUP BY 2, 3
       ON CONFLICT DO NOTHING;""",
    # 5. passada final por nome+data (qualquer status/fonte)
    """UPDATE politicos p SET pessoa_id = pe.id
       FROM pessoas pe
       WHERE p.pessoa_id IS NULL
         AND lower(trim(unaccent(p.nome_completo))) = pe.nome_canonical
         AND (p.data_nascimento = pe.data_nascimento
           OR (p.data_nascimento IS NULL AND pe.data_nascimento IS NULL));""",
]


def resolver_pessoas(conn) -> int:
    """Preenche pessoa_id dos registros recém-carregados. Retorna quantos ficaram sem."""
    cur = conn.cursor()
    for sql in RESOLVER_PESSOAS_SQL:
        cur.execute(sql)
    conn.commit()
    cur.execute("SELECT count(*) FROM politicos WHERE pessoa_id IS NULL;")
    restantes = cur.fetchone()[0]
    cur.close()
    return restantes

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--prata', help='Arquivo prata específico (opcional)')
    args = parser.parse_args()

    if args.prata:
        prata_path = Path(args.prata)
    else:
        pratas = sorted(PRATA_DIR.glob("*_prata.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not pratas:
            print("❌ Nenhum Prata encontrado"); return
        prata_path = pratas[0]

    print(f"📂 Prata: {prata_path.name}")
    with open(prata_path, encoding='utf-8') as f:
        prata = json.load(f)

    records = prata.get('records', [])
    print(f"📊 Registros: {len(records)}")

    if args.dry_run:
        print("🔍 DRY-RUN — nenhum dado gravado")
        print(f"✅ Simulação OK: {len(records)} registros prontos")
        return

    inicio = datetime.now(timezone.utc)
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()
    novos = erros = 0

    for i in range(0, len(records), 500):
        lote = records[i:i+500]
        try:
            cur.executemany(UPSERT_SQL, lote)
            conn.commit()
            novos += len(lote)
            print(f"  ✅ Lote {i//500+1}: {len(lote)} registros")
        except Exception as e:
            conn.rollback()
            erros += len(lote)
            print(f"  ❌ Lote {i//500+1} falhou: {e}")

    sem_pessoa = resolver_pessoas(conn)
    if sem_pessoa:
        print(f"  ⚠️ {sem_pessoa} registros ficaram sem pessoa_id (verificar)")
    else:
        print("  ✅ pessoa_id resolvido para 100% dos registros")

    fim = datetime.now(timezone.utc)
    dur = (fim - inicio).total_seconds()

    cur.execute(ETL_LOG, (
        'tse_candidatos', 'fase_0',
        'sucesso' if erros == 0 else 'parcial',
        len(records), novos,
        None if erros == 0 else f'{erros} erros',
        round(dur, 2), inicio, fim
    ))
    conn.commit()
    cur.close(); conn.close()

    print(f"\n✅ Carga concluída em {dur:.1f}s")
    print(f"   Inseridos/atualizados: {novos} | Erros: {erros}")

if __name__ == '__main__':
    main()

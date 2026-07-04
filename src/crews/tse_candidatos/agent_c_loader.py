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
ON CONFLICT (id_tse) DO UPDATE SET
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

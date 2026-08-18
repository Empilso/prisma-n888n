#!/usr/bin/env python3
"""Loader dos 4 datasets TSE orfaos (complementar, redes sociais, coligacoes,
vagas) -- le CSVs extraidos do ZIP oficial e carrega via COPY/INSERT.
Idempotente (UNIQUE + ON CONFLICT DO NOTHING)."""
import csv, os, sys, psycopg2, psycopg2.extras
from pathlib import Path

STAGE = Path(sys.argv[1])
ANO = int(sys.argv[2])

DB = dict(
    host=os.environ.get("DB_HOST", "127.0.0.1"),
    port=os.environ.get("DB_PORT", "5432"),
    dbname=os.environ.get("DB_NAME", "prisma_data"),
    user=os.environ.get("DB_USER", "postgres"),
    password=os.environ["DB_PASSWORD"],
)

def ler_csv(path):
    # TSE Dados Abertos publica sempre em ISO-8859-1 (latin-1) -- confirmado
    # hoje em todos os 7 datasets baixados. errors="replace" protege contra
    # qualquer byte fora do esperado sem derrubar a carga inteira.
    with open(path, encoding="latin-1", errors="replace") as f:
        return list(csv.DictReader(f, delimiter=";"))

def bool_sn(v):
    if v is None: return None
    v = v.strip().upper()
    if v in ("S", "SIM", "1"): return True
    if v in ("N", "NAO", "NÃO", "0"): return False
    return None

def num(v):
    if not v or v.strip() in ("", "#NULO#", "#NULO", "#NE#"): return None
    try: return float(v.replace(",", "."))
    except ValueError: return None

def intval(v):
    if not v or v.strip() in ("", "#NULO#", "#NULO", "#NE#"): return None
    try: return int(v)
    except ValueError: return None

def skip(v):
    if v is None: return None
    v = v.strip()
    return None if v in ("", "#NULO#", "#NULO", "#NE#", "#NE") else v

def load(nome_pasta, prefixo, processa, insert_sql):
    pasta = STAGE / "extraido" / nome_pasta
    arquivos = sorted(pasta.glob(f"{prefixo}_{ANO}_*.csv"))
    arquivos = [a for a in arquivos if "BRASIL" not in a.name and not a.name.endswith("_BR.csv")]
    total = 0
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    for arq in arquivos:
        rows = ler_csv(arq)
        for r in rows:
            params = processa(r)
            if params is None:
                continue
            cur.execute(insert_sql, params)
            total += 1
        conn.commit()
    cur.close(); conn.close()
    return total

# ---- complementar ----
def proc_complementar(r):
    return dict(
        ano_eleicao=ANO, cd_eleicao=skip(r.get("CD_ELEICAO")), sq_candidato=r["SQ_CANDIDATO"],
        situacao_detalhe=skip(r.get("DS_DETALHE_SITUACAO_CAND")), nacionalidade=skip(r.get("DS_NACIONALIDADE")),
        municipio_nascimento=skip(r.get("NM_MUNICIPIO_NASCIMENTO")), idade_data_posse=intval(r.get("NR_IDADE_DATA_POSSE")),
        quilombola=bool_sn(r.get("ST_QUILOMBOLA")), etnia_indigena=skip(r.get("DS_ETNIA_INDIGENA")),
        despesa_max_campanha=num(r.get("VR_DESPESA_MAX_CAMPANHA")), reeleicao=bool_sn(r.get("ST_REELEICAO")),
        declarar_bens=bool_sn(r.get("ST_DECLARAR_BENS")), protocolo_candidatura=skip(r.get("NR_PROTOCOLO_CANDIDATURA")),
        numero_processo=skip(r.get("NR_PROCESSO")), situacao_candidato_pleito=skip(r.get("DS_SITUACAO_CANDIDATO_PLEITO")),
        situacao_candidato_urna=skip(r.get("DS_SITUACAO_CANDIDATO_URNA")), situacao_candidato_tot=skip(r.get("DS_SITUACAO_CANDIDATO_TOT")),
        prestacao_contas=skip(r.get("ST_PREST_CONTAS")), substituido=bool_sn(r.get("ST_SUBSTITUIDO")),
        sq_substituido=skip(r.get("SQ_SUBSTITUIDO")), ordem_suplencia=intval(r.get("SQ_ORDEM_SUPLENCIA")),
        situacao_julgamento=skip(r.get("DS_SITUACAO_JULGAMENTO")), situacao_cassacao=skip(r.get("DS_SITUACAO_CASSACAO")),
        situacao_diploma=skip(r.get("DS_SITUACAO_DIPLOMA")),
    )
SQL_COMPLEMENTAR = """
INSERT INTO tse_candidatos_complementar
(ano_eleicao, cd_eleicao, sq_candidato, situacao_detalhe, nacionalidade, municipio_nascimento,
 idade_data_posse, quilombola, etnia_indigena, despesa_max_campanha, reeleicao, declarar_bens,
 protocolo_candidatura, numero_processo, situacao_candidato_pleito, situacao_candidato_urna,
 situacao_candidato_tot, prestacao_contas, substituido, sq_substituido, ordem_suplencia,
 situacao_julgamento, situacao_cassacao, situacao_diploma)
VALUES (%(ano_eleicao)s,%(cd_eleicao)s,%(sq_candidato)s,%(situacao_detalhe)s,%(nacionalidade)s,
 %(municipio_nascimento)s,%(idade_data_posse)s,%(quilombola)s,%(etnia_indigena)s,%(despesa_max_campanha)s,
 %(reeleicao)s,%(declarar_bens)s,%(protocolo_candidatura)s,%(numero_processo)s,%(situacao_candidato_pleito)s,
 %(situacao_candidato_urna)s,%(situacao_candidato_tot)s,%(prestacao_contas)s,%(substituido)s,%(sq_substituido)s,
 %(ordem_suplencia)s,%(situacao_julgamento)s,%(situacao_cassacao)s,%(situacao_diploma)s)
ON CONFLICT (ano_eleicao, sq_candidato) DO NOTHING
"""

# ---- redes sociais ----
def proc_redes(r):
    url = skip(r.get("DS_URL"))
    if not url: return None
    return dict(ano_eleicao=ANO, sq_candidato=r["SQ_CANDIDATO"], ordem=intval(r.get("NR_ORDEM_REDE_SOCIAL")), url=url)
SQL_REDES = """
INSERT INTO tse_candidatos_redes_sociais (ano_eleicao, sq_candidato, ordem, url)
VALUES (%(ano_eleicao)s,%(sq_candidato)s,%(ordem)s,%(url)s)
ON CONFLICT (ano_eleicao, sq_candidato, url) DO NOTHING
"""

# ---- coligacoes ----
def proc_coligacao(r):
    return dict(
        ano_eleicao=ANO, uf=skip(r.get("SG_UF")), ue=skip(r.get("SG_UE")), nm_ue=skip(r.get("NM_UE")),
        cargo=skip(r.get("DS_CARGO")), tipo_agremiacao=skip(r.get("TP_AGREMIACAO")),
        sq_coligacao=r["SQ_COLIGACAO"], nm_coligacao=skip(r.get("NM_COLIGACAO")),
        composicao_coligacao=skip(r.get("DS_COMPOSICAO_COLIGACAO")), composicao_federacao=skip(r.get("DS_COMPOSICAO_FEDERACAO")),
        situacao_legenda=skip(r.get("DS_SITUACAO")),
    )
SQL_COLIGACAO = """
INSERT INTO tse_coligacoes
(ano_eleicao, uf, ue, nm_ue, cargo, tipo_agremiacao, sq_coligacao, nm_coligacao,
 composicao_coligacao, composicao_federacao, situacao_legenda)
VALUES (%(ano_eleicao)s,%(uf)s,%(ue)s,%(nm_ue)s,%(cargo)s,%(tipo_agremiacao)s,%(sq_coligacao)s,
 %(nm_coligacao)s,%(composicao_coligacao)s,%(composicao_federacao)s,%(situacao_legenda)s)
ON CONFLICT (ano_eleicao, sq_coligacao, uf, ue, cargo) DO NOTHING
"""

# ---- vagas ----
def proc_vagas(r):
    return dict(
        ano_eleicao=ANO, uf=skip(r.get("SG_UF")), ue=skip(r.get("SG_UE")), nm_ue=skip(r.get("NM_UE")),
        cargo=skip(r.get("DS_CARGO")), qtd_vagas=intval(r.get("QT_VAGA")),
    )
SQL_VAGAS = """
INSERT INTO tse_vagas (ano_eleicao, uf, ue, nm_ue, cargo, qtd_vagas)
VALUES (%(ano_eleicao)s,%(uf)s,%(ue)s,%(nm_ue)s,%(cargo)s,%(qtd_vagas)s)
ON CONFLICT (ano_eleicao, uf, ue, cargo) DO NOTHING
"""

if __name__ == "__main__":
    n1 = load("info_complementar_2026", "consulta_cand_complementar", proc_complementar, SQL_COMPLEMENTAR)
    print("complementar:", n1)
    n2 = load("rede_social_2026", "rede_social_candidato", proc_redes, SQL_REDES)
    print("redes_sociais:", n2)
    n3 = load("coligacao_2026", "consulta_coligacao", proc_coligacao, SQL_COLIGACAO)
    print("coligacoes:", n3)
    n4 = load("vagas_2026", "consulta_vagas", proc_vagas, SQL_VAGAS)
    print("vagas:", n4)

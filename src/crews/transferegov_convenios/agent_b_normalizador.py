#!/usr/bin/env python3
# Agent B - Normalizador TransfereGov Convenios
import argparse, json, re
from datetime import datetime, date, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import psycopg2
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/transferegov_convenios"
BRONZE_DIR = DATA_DIR / "bronze"
PRATA_DIR  = DATA_DIR / "prata"
REJEIT_DIR = DATA_DIR / "rejeitados"
for d in (PRATA_DIR, REJEIT_DIR):
    d.mkdir(parents=True, exist_ok=True)

DB = dict(host="localhost", port=5432, dbname="prisma_data", user="postgres", password=DB_PASSWORD)

def limpa_str(v):
    if v is None: return None
    s = str(v).strip()
    return s or None

def limpa_cnpj(v):
    s = limpa_str(v)
    if not s: return None
    only = re.sub(r"\D", "", s)
    if len(only) == 14: return only
    if len(only) == 13: return only.zfill(14)
    return None

def parse_decimal(v):
    if v is None: return None
    try:
        d = Decimal(str(v))
        return d if d != 0 else None
    except (InvalidOperation, ValueError):
        return None

_CODIGO_DATA_RE = re.compile(r"^(\d{2})(\d{2})(\d{4})-")

def extrai_data_codigo(codigo):
    if not codigo: return None
    m = _CODIGO_DATA_RE.match(codigo.strip())
    if not m: return None
    dd, mm, yyyy = m.groups()
    try:
        return date(int(yyyy), int(mm), int(dd))
    except ValueError:
        return None

def carrega_programas_orgao():
    p = BRONZE_DIR / "programas_especial_bronze.json"
    if not p.exists(): return {}
    bronze = json.loads(p.read_text())
    out = {}
    for r in bronze.get("records", []):
        pid = r.get("id_programa")
        orgao = r.get("nome_orgao_superior_programa") or r.get("nome_orgao_programa")
        if pid is not None and orgao:
            out[int(pid)] = orgao
    return out

def _nome_chave(nome):
    n = nome.upper().strip()
    for pfx in ("MUNICIPIO DE ", "PREFEITURA MUNICIPAL DE ", "PREFEITURA DE ", "CAMARA MUNICIPAL DE "):
        if n.startswith(pfx):
            n = n[len(pfx):]
    return n

def carrega_municipios_index():
    conn = psycopg2.connect(**DB); cur = conn.cursor()
    cur.execute("SELECT id_ibge, upper(nome), uf FROM municipios")
    idx = {}
    for ibge, nome, uf in cur.fetchall():
        if nome and uf:
            idx[(_nome_chave(nome), uf)] = ibge
    cur.close(); conn.close()
    return idx

def carrega_politicos_por_nome():
    sql = ("SELECT DISTINCT ON (upper(nome_urna)) upper(nome_urna), id_tse "
           "FROM politicos WHERE cargo IN ('DEPUTADO FEDERAL','SENADOR','SENADORA') "
           "ORDER BY upper(nome_urna), ano_eleicao DESC NULLS LAST")
    conn = psycopg2.connect(**DB); cur = conn.cursor()
    cur.execute(sql)
    idx = {nome: id_tse for nome, id_tse in cur.fetchall() if nome}
    cur.close(); conn.close()
    return idx

def normaliza(r, programas, municipios, politicos):
    codigo = limpa_str(r.get("codigo_plano_acao"))
    if not codigo:
        out = {"_motivo": "sem_codigo_plano_acao"}
        out.update(r)
        return out
    ano = r.get("ano_plano_acao")
    try:
        ano = int(ano) if ano is not None else None
    except (TypeError, ValueError):
        ano = None
    uf = limpa_str(r.get("uf_beneficiario_plano_acao"))
    if uf: uf = uf.upper()[:2]
    nome_prop = limpa_str(r.get("nome_beneficiario_plano_acao"))
    municipio_ibge = None
    if nome_prop and uf:
        municipio_ibge = municipios.get((_nome_chave(nome_prop), uf))
    parlamentar = limpa_str(r.get("nome_parlamentar_emenda_plano_acao"))
    politico_id = None
    if parlamentar:
        politico_id = politicos.get(parlamentar.upper())
    custeio  = parse_decimal(r.get("valor_custeio_plano_acao"))    or Decimal(0)
    investim = parse_decimal(r.get("valor_investimento_plano_acao")) or Decimal(0)
    valor_repasse = custeio + investim
    if valor_repasse == 0: valor_repasse = None
    id_programa = r.get("id_programa")
    orgao_concedente = programas.get(int(id_programa)) if id_programa is not None else None
    vigencia_inicio = extrai_data_codigo(codigo)
    return {
        "nr_convenio":              codigo,
        "ano":                      ano,
        "situacao":                 limpa_str(r.get("situacao_plano_acao")),
        "vigencia_inicio":          vigencia_inicio.isoformat() if vigencia_inicio else None,
        "vigencia_fim":             None,
        "orgao_concedente":         orgao_concedente,
        "cnpj_proponente":          limpa_cnpj(r.get("cnpj_beneficiario_plano_acao")),
        "nome_proponente":          nome_prop,
        "municipio_ibge":           municipio_ibge,
        "uf":                       uf,
        "valor_global":             str(valor_repasse) if valor_repasse else None,
        "valor_repasse":            str(valor_repasse) if valor_repasse else None,
        "valor_contrapartida":      "0",
        "modalidade":               limpa_str(r.get("modalidade_plano_acao")),
        "justificativa_resumo":     (limpa_str(r.get("descricao_programacao_orcamentaria_plano_acao")) or limpa_str(r.get("codigo_descricao_areas_politicas_publicas_plano_acao"))),
        "emenda_codigo_associada":  limpa_str(r.get("numero_emenda_parlamentar_plano_acao")),
        "politico_id":              politico_id,
        "parlamentar_nome":         parlamentar,
        "origem_fonte":             "TransfereGov:plano_acao_especial",
        "executor_cnpj":            limpa_cnpj(r.get("cnpj_beneficiario_plano_acao")),
        "executor_nome":            nome_prop,
        "data_assinatura":          vigencia_inicio.isoformat() if vigencia_inicio else None,
        "objeto":                   limpa_str(r.get("descricao_programacao_orcamentaria_plano_acao")),
    }

def processar(bronze_path, programas, municipios, politicos):
    print("[bronze] " + bronze_path.name)
    bronze = json.loads(bronze_path.read_text())
    records = bronze.get("records", [])
    print("  " + str(len(records)) + " registros brutos")
    validos, rejeitados = [], []
    vistos = set()
    for r in records:
        out = normaliza(r, programas, municipios, politicos)
        if out is None: continue
        if "_motivo" in out:
            rejeitados.append(out); continue
        if out["nr_convenio"] in vistos: continue
        vistos.add(out["nr_convenio"])
        validos.append(out)
    stem = bronze_path.stem.replace("_bronze", "")
    prata_path = PRATA_DIR / (stem + "_prata.json")
    prata_path.write_text(json.dumps({
        "meta": {
            "data_processamento": datetime.now(timezone.utc).isoformat(),
            "fonte_bronze":       bronze_path.name,
            "total_validos":      len(validos),
            "total_rejeitados":   len(rejeitados),
            "matched_politico":   sum(1 for v in validos if v["politico_id"]),
            "matched_municipio":  sum(1 for v in validos if v["municipio_ibge"]),
        },
        "records": validos,
    }, ensure_ascii=False))
    if rejeitados:
        rj = REJEIT_DIR / (stem + "_rejeitados.json")
        rj.write_text(json.dumps(rejeitados, ensure_ascii=False))
    print("  [ok] prata: " + str(len(validos)) + " validos (" + str(len(rejeitados)) + " rejeitados) -> " + prata_path.name)

def main():
    ap = argparse.ArgumentParser(description="Agent B - Normalizador TransfereGov Convenios")
    ap.add_argument("--bronze")
    ap.add_argument("--todos", action="store_true")
    args = ap.parse_args()
    print("TransfereGov Convenios - Agent B (Normalizador)")
    print("  carregando catalogos auxiliares...")
    programas  = carrega_programas_orgao()
    municipios = carrega_municipios_index()
    politicos  = carrega_politicos_por_nome()
    print("  programas=" + str(len(programas)) + " municipios=" + str(len(municipios)) + " politicos=" + str(len(politicos)))
    if args.bronze:
        path = Path(args.bronze)
        if not path.is_absolute(): path = BRONZE_DIR / path
        processar(path, programas, municipios, politicos)
    elif args.todos:
        for b in sorted(BRONZE_DIR.glob("planos_acao_especial_*_bronze.json")):
            processar(b, programas, municipios, politicos); print()
    else:
        bs = sorted(BRONZE_DIR.glob("planos_acao_especial_*_bronze.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not bs:
            print("[erro] nenhum bronze encontrado"); return
        processar(bs[0], programas, municipios, politicos)
    print("[ok] Agent B concluido.")

if __name__ == "__main__":
    main()

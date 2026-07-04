#!/usr/bin/env python3
"""Agent B — Normalizador Senado Votações: Bronze → Prata

Lê Bronze (lista + detalhe de cada votação com Votos[]) e produz:

  - senado_votacoes:        1 registro por votação (cabeçalho)
  - senado_votos_nominais:  N registros por votação (1 por senador votante)

Resolução de politico_id por senador:
  1) Por coluna `politicos.id_legislativo_senado` (match exato CodigoParlamentar).
  2) Fallback fuzzy por nome + UF + partido.

Regras de rejeição da votação:
  - Sem CodigoSessaoVotacao
  - Sem qualquer voto registrado (votação secreta ou simbólica) — mantém votação
    mas zera lista de votos

Saída:
    data/senado_votacoes/prata/senado_vot_{ANO}_prata.json
    data/senado_votacoes/rejeitados/senado_vot_{ANO}_rejeitados.json
"""
import json, re, argparse, hashlib, os
import logging
from pathlib import Path
from datetime import datetime, date, timezone

try:
    import psycopg2
    HAS_PG = True
except ImportError:
    HAS_PG = False

logger = logging.getLogger(__name__)

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/senado_votacoes"
BRONZE_DIR = DATA_DIR / "bronze"
PRATA_DIR  = DATA_DIR / "prata"
REJEIT_DIR = DATA_DIR / "rejeitados"
for d in (PRATA_DIR, REJEIT_DIR):
    d.mkdir(parents=True, exist_ok=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_get(d, *keys):
    cur = d
    for k in keys:
        if cur is None:
            return None
        if isinstance(cur, list):
            if not cur:
                return None
            cur = cur[0]
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _str(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def parse_date(v):
    v = _str(v)
    if not v:
        return None
    v = v.split("T")[0].strip()[:10]
    try:
        if "/" in v:
            d, m, a = v.split("/")
            d, m, a = int(d), int(m), int(a)
        else:
            a, m, d = int(v[:4]), int(v[5:7]), int(v[8:10])
        if 1900 <= a <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
            return date(a, m, d).isoformat()
    except Exception:
        logger.warning("parse_date: valor de data inválido, ignorando: %r", v)
        return None
    return None


def normalize_name(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"[^A-Za-zÀ-ÿ ]+", " ", s.upper()).strip()
    s = re.sub(r"\s+", " ", s)
    for pref in ("SENADOR ", "SENADORA "):
        if s.startswith(pref):
            s = s[len(pref):]
    return s.strip()


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# Mapeamento de SiglaVoto → tipo_voto canônico
VOTO_MAP = {
    "S":    "SIM",
    "SIM":  "SIM",
    "N":    "NAO",
    "NÃO":  "NAO",
    "NAO":  "NAO",
    "O":    "OBSTRUCAO",
    "OBSTRUÇÃO": "OBSTRUCAO",
    "OBSTRUCAO": "OBSTRUCAO",
    "A":    "ABSTENCAO",
    "ABS":  "ABSTENCAO",
    "ABSTENÇÃO": "ABSTENCAO",
    "ABSTENCAO": "ABSTENCAO",
    "P":    "PRESIDENTE",
    "AUS":  "AUSENTE",
    "NV":   "NAO_VOTOU",
}


def canon_voto(sigla: str | None, descricao: str | None) -> str:
    if sigla:
        v = VOTO_MAP.get(sigla.strip().upper())
        if v:
            return v
    if descricao:
        v = VOTO_MAP.get(descricao.strip().upper())
        if v:
            return v
    return (sigla or descricao or "DESCONHECIDO").strip().upper()


# ── Resolução politico_id ────────────────────────────────────────────────────

class PoliticoResolver:
    def __init__(self):
        self.by_senado_id: dict[str, str] = {}
        self.by_name_uf_partido: dict[str, str] = {}
        self.by_name_uf: dict[str, str] = {}
        self.has_id_legislativo_col = False
        self.loaded = False

    def load(self):
        if self.loaded:
            return
        if not HAS_PG:
            print("  ⚠️  psycopg2 não disponível — politico_id ficará NULL")
            self.loaded = True
            return
        try:
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", 5432)),
                dbname=os.getenv("DB_NAME", "prisma_data"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD"),
            )
        except Exception as e:
            print(f"  ⚠️  Sem conexão Postgres ({e}) — politico_id ficará NULL")
            self.loaded = True
            return

        cur = conn.cursor()
        cur.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name='politicos' AND column_name='id_legislativo_senado'
        """)
        self.has_id_legislativo_col = cur.fetchone() is not None

        if self.has_id_legislativo_col:
            cur.execute("""
                SELECT id_legislativo_senado, politico_id FROM politicos
                 WHERE id_legislativo_senado IS NOT NULL AND politico_id IS NOT NULL
            """)
            for legid, pid in cur.fetchall():
                self.by_senado_id[str(legid)] = pid

        cur.execute("""
            SELECT politico_id, COALESCE(nome_completo, nome_urna), uf, sigla_partido
            FROM politicos WHERE nome_completo IS NOT NULL AND politico_id IS NOT NULL
        """)
        for pid, nome, uf, partido in cur.fetchall():
            nm = normalize_name(nome or "")
            uf = (uf or "").upper().strip()
            partido = (partido or "").upper().strip()
            if nm and uf:
                self.by_name_uf.setdefault(f"{nm}|{uf}", pid)
                if partido:
                    self.by_name_uf_partido.setdefault(f"{nm}|{uf}|{partido}", pid)

        cur.close()
        conn.close()
        self.loaded = True
        print(f"  📚 Resolver: {len(self.by_senado_id)} por id_senado, "
              f"{len(self.by_name_uf)} por nome+UF")

    def resolve(self, codigo_parlamentar, nome, uf, partido):
        if codigo_parlamentar:
            pid = self.by_senado_id.get(str(codigo_parlamentar))
            if pid:
                return pid
        nm = normalize_name(nome or "")
        uf = (uf or "").upper().strip()
        partido = (partido or "").upper().strip()
        if nm and uf and partido:
            pid = self.by_name_uf_partido.get(f"{nm}|{uf}|{partido}")
            if pid:
                return pid
        if nm and uf:
            return self.by_name_uf.get(f"{nm}|{uf}")
        return None


# ── Normalização ─────────────────────────────────────────────────────────────

def extrair_cabecalho(reg: dict) -> dict:
    detalhe = reg.get("detalhe") or {}
    lista   = reg.get("lista") or {}

    codigo = (detalhe.get("CodigoSessaoVotacao")
              or detalhe.get("CodigoVotacao")
              or lista.get("CodigoSessaoVotacao")
              or lista.get("CodigoVotacao")
              or reg.get("_codigo"))
    try:
        codigo = int(codigo) if codigo else None
    except (TypeError, ValueError):
        codigo = None

    data_v = (detalhe.get("DataSessao") or lista.get("DataSessao")
              or detalhe.get("DataVotacao"))
    descricao = (detalhe.get("DescricaoVotacao") or lista.get("DescricaoVotacao")
                 or detalhe.get("ObjetoVotacao") or lista.get("ObjetoVotacao"))
    resultado = (detalhe.get("Resultado") or lista.get("Resultado")
                 or detalhe.get("DescricaoResultado"))
    sessao_codigo = (detalhe.get("CodigoSessao") or lista.get("CodigoSessao")
                     or _safe_get(detalhe, "Sessao", "CodigoSessao"))
    materia_codigo = (_safe_get(detalhe, "Materia", "CodigoMateria")
                      or _safe_get(detalhe, "MateriaPrincipal", "CodigoMateria")
                      or detalhe.get("CodigoMateria") or lista.get("CodigoMateria"))

    try:
        sessao_codigo = int(sessao_codigo) if sessao_codigo else None
    except (TypeError, ValueError):
        sessao_codigo = None
    try:
        materia_codigo = int(materia_codigo) if materia_codigo else None
    except (TypeError, ValueError):
        materia_codigo = None

    return {
        "codigo":         codigo,
        "data":           parse_date(data_v),
        "descricao":      _str(descricao),
        "materia_codigo": materia_codigo,
        "resultado":      _str(resultado),
        "sessao_codigo":  sessao_codigo,
    }


def extrair_votos(reg: dict, resolver: PoliticoResolver) -> list[dict]:
    detalhe = reg.get("detalhe") or {}
    votos = (_safe_get(detalhe, "Votos", "VotoParlamentar")
             or _safe_get(detalhe, "Votos", "Voto")
             or _safe_get(detalhe, "Votacao", "Votos", "VotoParlamentar"))
    if not votos:
        return []
    if isinstance(votos, dict):
        votos = [votos]

    saida = []
    for v in votos:
        identif = v.get("IdentificacaoParlamentar") or {}
        codigo_parl = _str(identif.get("CodigoParlamentar") or v.get("CodigoParlamentar"))
        nome = _str(identif.get("NomeParlamentar") or v.get("NomeParlamentar"))
        partido = _str(identif.get("SiglaPartidoParlamentar") or v.get("SiglaPartido"))
        uf = _str(identif.get("UfParlamentar") or v.get("SiglaUf") or v.get("UF"))
        sigla = _str(v.get("SiglaVoto") or v.get("DescricaoVoto"))
        desc  = _str(v.get("DescricaoVoto") or v.get("Voto"))

        if not codigo_parl:
            continue
        try:
            codigo_parl_int = int(codigo_parl)
        except (TypeError, ValueError):
            continue

        pid = resolver.resolve(codigo_parl, nome, uf, partido)

        saida.append({
            "senador_codigo": codigo_parl_int,
            "politico_id":    pid,
            "nome":           nome,
            "sigla_partido":  partido,
            "sigla_uf":       uf,
            "tipo_voto":      canon_voto(sigla, desc),
        })
    return saida


def normalizar_registro(reg: dict, resolver: PoliticoResolver) -> dict | None:
    cab = extrair_cabecalho(reg)
    if not cab["codigo"]:
        return {"_motivo": "codigo ausente", **reg}

    votos = extrair_votos(reg, resolver)

    # Totais (algumas votações têm campos prontos; caso contrário derivamos)
    detalhe = reg.get("detalhe") or {}
    try:
        total_sim = int(detalhe.get("TotalVotosSim") or 0)
    except (TypeError, ValueError):
        total_sim = 0
    try:
        total_nao = int(detalhe.get("TotalVotosNao") or 0)
    except (TypeError, ValueError):
        total_nao = 0
    try:
        total_abs = int(detalhe.get("TotalVotosAbstencao") or 0)
    except (TypeError, ValueError):
        total_abs = 0

    if (total_sim, total_nao, total_abs) == (0, 0, 0) and votos:
        total_sim = sum(1 for v in votos if v["tipo_voto"] == "SIM")
        total_nao = sum(1 for v in votos if v["tipo_voto"] == "NAO")
        total_abs = sum(1 for v in votos if v["tipo_voto"] == "ABSTENCAO")

    raw_payload = json.dumps({
        "lista":   reg.get("lista"),
        "detalhe": reg.get("detalhe"),
    }, sort_keys=True, ensure_ascii=False)
    raw_hash = sha256(raw_payload)

    return {
        "votacao": {
            "codigo":         cab["codigo"],
            "data":           cab["data"],
            "descricao":      cab["descricao"],
            "materia_codigo": cab["materia_codigo"],
            "resultado":      cab["resultado"],
            "total_sim":      total_sim,
            "total_nao":      total_nao,
            "total_abstencao": total_abs,
            "sessao_codigo":  cab["sessao_codigo"],
            "raw_hash":       raw_hash,
        },
        "votos": votos,
    }


def processar_bronze(bronze_path: Path, resolver: PoliticoResolver) -> None:
    print(f"📂 Bronze: {bronze_path.name}")
    with open(bronze_path, encoding="utf-8") as f:
        bronze = json.load(f)

    meta = bronze.get("meta", {})
    ano  = meta.get("ano", 0)
    records = bronze.get("records", [])
    print(f"📊 Total bruto: {len(records):,}")

    resolver.load()

    validos, rejeitados, vistos = [], [], set()
    total_votos = 0
    com_pid = 0
    for r in records:
        norm = normalizar_registro(r, resolver)
        if not norm:
            continue
        if "_motivo" in norm:
            rejeitados.append(norm)
            continue
        codigo = norm["votacao"]["codigo"]
        if codigo in vistos:
            continue
        vistos.add(codigo)
        validos.append(norm)
        total_votos += len(norm["votos"])
        com_pid += sum(1 for v in norm["votos"] if v["politico_id"])

    stem = bronze_path.stem.replace("_bronze", "")
    prata_path = PRATA_DIR / f"{stem}_prata.json"
    with open(prata_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "data_processamento": datetime.now(timezone.utc).isoformat(),
                "fonte_bronze":       bronze_path.name,
                "ano":                ano,
                "total_votacoes":     len(validos),
                "total_votos":        total_votos,
                "votos_com_politico_id": com_pid,
                "total_rejeitados":   len(rejeitados),
            },
            "records": validos,
        }, f, ensure_ascii=False)

    if rejeitados:
        rj = REJEIT_DIR / f"{stem}_rejeitados.json"
        with open(rj, "w", encoding="utf-8") as f:
            json.dump(rejeitados, f, ensure_ascii=False)

    taxa = len(rejeitados) / max(len(records), 1) * 100
    print(f"✅ Prata: {len(validos):>4,} votações, {total_votos:>6,} votos → {prata_path.name}")
    print(f"   politico_id resolvido: {com_pid}/{total_votos} "
          f"({(com_pid/max(total_votos,1))*100:.1f}%)")
    print(f"⚠️  Rejeitados: {len(rejeitados):,} ({taxa:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Agent B — Normalizador Senado Votações")
    parser.add_argument("--bronze", help="Arquivo bronze específico")
    parser.add_argument("--todos",  action="store_true", help="Todos os bronzes")
    args = parser.parse_args()

    resolver = PoliticoResolver()

    if args.bronze:
        processar_bronze(Path(args.bronze), resolver)
    elif args.todos:
        bronzes = sorted(BRONZE_DIR.glob("senado_vot_*_bronze.json"))
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        for b in bronzes:
            processar_bronze(b, resolver)
            print()
    else:
        bronzes = sorted(BRONZE_DIR.glob("senado_vot_*_bronze.json"),
                         key=lambda f: f.stat().st_mtime, reverse=True)
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        processar_bronze(bronzes[0], resolver)

    print("\n✅ Agent B concluído.")


if __name__ == "__main__":
    main()

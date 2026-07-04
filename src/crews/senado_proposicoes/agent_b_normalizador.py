#!/usr/bin/env python3
"""Agent B — Normalizador Senado Proposições: Bronze → Prata

Lê Bronze (lista+detalhe+autoria por proposição) e produz registros prontos
para senado_proposicoes.

Resolução de politico_id (autores):
  1) Por coluna `politicos.id_legislativo_senado` (se existir) — match exato pelo
     CodigoParlamentar do Senado.
  2) Fallback fuzzy por nome + UF + partido contra `politicos`.

Regras de rejeição:
  - Sem CodigoMateria
  - Sem ano

Saída:
    data/senado_proposicoes/prata/senado_prop_{ANO}_prata.json
    data/senado_proposicoes/rejeitados/senado_prop_{ANO}_rejeitados.json
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
DATA_DIR   = BASE_DIR / "data/senado_proposicoes"
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
    # Remove prefixos comuns
    for pref in ("SENADOR ", "SENADORA ", "DEPUTADO ", "DEPUTADA "):
        if s.startswith(pref):
            s = s[len(pref):]
    return s.strip()


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# ── Resolução politico_id ────────────────────────────────────────────────────

class PoliticoResolver:
    """Cache em memória: (id_legislativo_senado → politico_id) e (nome_uf_partido → politico_id)."""

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
        # Verifica se coluna existe
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
        print(f"  📚 Resolver carregado: {len(self.by_senado_id)} por id_senado, "
              f"{len(self.by_name_uf)} por nome+UF")

    def resolve(self, codigo_parlamentar: str | None, nome: str | None,
                uf: str | None, partido: str | None) -> str | None:
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

def extrair_metadados(reg: dict) -> dict:
    detalhe = reg.get("detalhe") or {}
    lista   = reg.get("lista") or {}

    identif = _safe_get(detalhe, "IdentificacaoMateria") or _safe_get(lista, "IdentificacaoMateria") or {}
    dados   = _safe_get(detalhe, "DadosBasicosMateria") or {}

    codigo  = identif.get("CodigoMateria") or reg.get("_codigo")
    tipo    = identif.get("SiglaSubtipoMateria") or reg.get("_sigla")
    numero  = identif.get("NumeroMateria")
    ano     = identif.get("AnoMateria") or reg.get("_ano")
    ementa  = (dados.get("EmentaMateria") or _safe_get(lista, "EmentaMateria"))
    data_apresentacao = dados.get("DataApresentacao") or _safe_get(lista, "DataApresentacao")
    situacao_atual = (_safe_get(detalhe, "SituacaoAtual", "Autuacoes", "Autuacao", "Situacao", "DescricaoSituacao")
                      or _safe_get(detalhe, "SituacaoAtual", "DescricaoSituacao"))

    try:
        codigo = int(codigo) if codigo else None
    except (TypeError, ValueError):
        codigo = None
    try:
        numero = int(numero) if numero else None
    except (TypeError, ValueError):
        numero = None
    try:
        ano = int(ano) if ano else None
    except (TypeError, ValueError):
        ano = None

    return {
        "codigo":  codigo,
        "tipo":    _str(tipo),
        "numero":  numero,
        "ano":     ano,
        "ementa":  _str(ementa),
        "data_apresentacao": parse_date(data_apresentacao),
        "situacao_atual":    _str(situacao_atual),
    }


def extrair_autores(reg: dict, resolver: PoliticoResolver) -> tuple[list[str], list[dict], str | None]:
    autores_raw = reg.get("autoria") or []
    politico_ids: list[str] = []
    detalhes: list[dict] = []
    textos: list[str] = []

    for a in autores_raw:
        nome = _str(a.get("NomeAutor")) or _str(_safe_get(a, "IdentificacaoParlamentar", "NomeParlamentar"))
        codigo_parl = _str(a.get("CodigoParlamentar") or _safe_get(a, "IdentificacaoParlamentar", "CodigoParlamentar"))
        partido = _str(a.get("SiglaPartidoAutor") or _safe_get(a, "IdentificacaoParlamentar", "SiglaPartidoParlamentar"))
        uf = _str(a.get("UfAutor") or _safe_get(a, "IdentificacaoParlamentar", "UfParlamentar"))

        pid = resolver.resolve(codigo_parl, nome, uf, partido)

        detalhes.append({
            "codigo_parlamentar": codigo_parl,
            "nome":               nome,
            "partido":            partido,
            "uf":                 uf,
            "politico_id":        pid,
        })
        if pid and pid not in politico_ids:
            politico_ids.append(pid)
        if nome:
            label = f"{nome}"
            if partido or uf:
                label += f" ({partido or '?'}/{uf or '?'})"
            textos.append(label)

    autoria_txt = "; ".join(textos) if textos else None
    return politico_ids, detalhes, autoria_txt


def normalizar_registro(reg: dict, resolver: PoliticoResolver) -> dict | None:
    meta = extrair_metadados(reg)
    if not meta["codigo"]:
        return {"_motivo": "codigo ausente", **reg}
    if not meta["ano"]:
        return {"_motivo": "ano ausente", **reg}

    politico_ids, detalhes, autoria_txt = extrair_autores(reg, resolver)

    # Hash de auditoria do payload bruto (lista+detalhe+autoria)
    raw_payload = json.dumps({
        "lista":   reg.get("lista"),
        "detalhe": reg.get("detalhe"),
        "autoria": reg.get("autoria"),
    }, sort_keys=True, ensure_ascii=False)
    raw_hash = sha256(raw_payload)

    return {
        "codigo":             meta["codigo"],
        "tipo":               meta["tipo"] or "DESCONHECIDO",
        "numero":             meta["numero"],
        "ano":                meta["ano"],
        "ementa":             meta["ementa"],
        "data_apresentacao":  meta["data_apresentacao"],
        "autoria":            autoria_txt,
        "autores_politico_ids": politico_ids,
        "autores_detalhes":   detalhes,
        "situacao_atual":     meta["situacao_atual"],
        "casa":               "SF",
        "raw_hash":           raw_hash,
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
    for r in records:
        norm = normalizar_registro(r, resolver)
        if not norm:
            continue
        if "_motivo" in norm:
            rejeitados.append(norm)
            continue
        if norm["codigo"] in vistos:
            # Duplicata dentro do mesmo Bronze — ignora a 2ª
            continue
        vistos.add(norm["codigo"])
        validos.append(norm)

    stem = bronze_path.stem.replace("_bronze", "")
    prata_path = PRATA_DIR / f"{stem}_prata.json"
    with open(prata_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "data_processamento": datetime.now(timezone.utc).isoformat(),
                "fonte_bronze":       bronze_path.name,
                "ano":                ano,
                "total_validos":      len(validos),
                "total_rejeitados":   len(rejeitados),
                "com_politico_id":    sum(1 for v in validos if v["autores_politico_ids"]),
            },
            "records": validos,
        }, f, ensure_ascii=False)

    if rejeitados:
        rj = REJEIT_DIR / f"{stem}_rejeitados.json"
        with open(rj, "w", encoding="utf-8") as f:
            json.dump(rejeitados, f, ensure_ascii=False)

    taxa = len(rejeitados) / max(len(records), 1) * 100
    print(f"✅ Prata: {len(validos):>5,} válidos → {prata_path.name}")
    print(f"⚠️  Rejeitados: {len(rejeitados):,} ({taxa:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Agent B — Normalizador Senado Proposições")
    parser.add_argument("--bronze", help="Arquivo bronze específico")
    parser.add_argument("--todos",  action="store_true", help="Todos os bronzes")
    args = parser.parse_args()

    resolver = PoliticoResolver()

    if args.bronze:
        processar_bronze(Path(args.bronze), resolver)
    elif args.todos:
        bronzes = sorted(BRONZE_DIR.glob("senado_prop_*_bronze.json"))
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        for b in bronzes:
            processar_bronze(b, resolver)
            print()
    else:
        bronzes = sorted(BRONZE_DIR.glob("senado_prop_*_bronze.json"),
                         key=lambda f: f.stat().st_mtime, reverse=True)
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        processar_bronze(bronzes[0], resolver)

    print("\n✅ Agent B concluído.")


if __name__ == "__main__":
    main()

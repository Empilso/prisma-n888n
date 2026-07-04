#!/usr/bin/env python3
"""Agent B — Normalizador TSE Locais de Votação

Bronze: CSV raw latin-1 (517k linhas / seções)
Prata:  JSON de locais únicos deduplicados (~96k locais Brasil)

Deduplica por (sg_uf, cd_municipio, nr_local) — agrupa seções do mesmo prédio.
Coordenadas: vírgula → ponto, converte para float.
Sem coords (4.7%): latitude/longitude ficam null para geocoding posterior.

Execução:
    python agent_b_normalizador.py
    python agent_b_normalizador.py --uf SP    # só SP (11k locais)
    python agent_b_normalizador.py --force
"""
import csv, json, argparse
from pathlib import Path
from collections import defaultdict

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
RAW_DIR    = BASE_DIR / "data/tse_locais/raw"
BRONZE_DIR = BASE_DIR / "data/tse_locais/bronze"
BRONZE_DIR.mkdir(parents=True, exist_ok=True)

CSV_PATH   = RAW_DIR / "eleitorado_local_votacao_ATUAL.csv"


def parse_coord(val: str) -> float | None:
    v = val.replace(",", ".").strip()
    if v in ("", "-1", "#NULO"):
        return None
    try:
        f = float(v)
        return None if f == -1.0 else f
    except ValueError:
        return None


def parse_int(val: str) -> int:
    try:
        return int(val.strip())
    except (ValueError, AttributeError):
        return 0


def normalizar(uf_filter: str | None = None, force: bool = False) -> Path:
    sufixo = f"_{uf_filter}" if uf_filter else "_BR"
    bronze_path = BRONZE_DIR / f"locais{sufixo}_bronze.json"

    if bronze_path.exists() and not force:
        with open(bronze_path) as f:
            existente = json.load(f)
        print(f"✅ Bronze já existe — {len(existente):,} locais ({bronze_path.name})")
        return bronze_path

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV não encontrado: {CSV_PATH}\nExecute agent_a_coletor.py primeiro.")

    print(f"📖 Lendo CSV {CSV_PATH.stat().st_size / 1_048_576:.0f} MB ...")

    # Deduplicação: chave = (sg_uf, cd_municipio, nr_local)
    locais: dict[tuple, dict] = {}
    total_linhas = 0

    with open(CSV_PATH, encoding="latin-1", newline="") as f:
        reader = csv.DictReader(f, delimiter=";", quotechar='"')
        for row in reader:
            total_linhas += 1
            sg_uf = row["SG_UF"].strip()

            if uf_filter and sg_uf != uf_filter.upper():
                continue

            try:
                cd_municipio = int(row["CD_MUNICIPIO"].strip())
                nr_local     = int(row["NR_LOCAL_VOTACAO"].strip())
            except ValueError:
                continue

            key = (sg_uf, cd_municipio, nr_local)
            if key in locais:
                locais[key]["qt_eleitores"] += parse_int(row.get("QT_ELEITOR_SECAO", "0"))
                continue

            lat = parse_coord(row.get("NR_LATITUDE", ""))
            lon = parse_coord(row.get("NR_LONGITUDE", ""))

            locais[key] = {
                "sg_uf":        sg_uf,
                "cd_municipio": cd_municipio,
                "nm_municipio": row["NM_MUNICIPIO"].strip().title(),
                "nr_local":     nr_local,
                "nm_local":     row["NM_LOCAL_VOTACAO"].strip(),
                "ds_endereco":  row.get("DS_ENDERECO", "").strip() or None,
                "nm_bairro":    row.get("NM_BAIRRO", "").strip() or None,
                "nr_cep":       row.get("NR_CEP", "").strip()[:8] or None,
                "latitude":     lat,
                "longitude":    lon,
                "qt_eleitores": parse_int(row.get("QT_ELEITOR_SECAO", "0")),
                "ds_situacao":  row.get("DS_SITU_LOCAL_VOTACAO", "ATIVO").strip(),
            }

    result = list(locais.values())
    sem_coords = sum(1 for r in result if r["latitude"] is None)

    print(f"✅ Linhas lidas:       {total_linhas:,}")
    print(f"✅ Locais únicos:      {len(result):,}")
    print(f"⚠️  Sem coordenadas:   {sem_coords:,} ({100*sem_coords/max(len(result),1):.1f}%)")

    with open(bronze_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=None)

    print(f"✅ Bronze salvo: {bronze_path}")
    return bronze_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf",    default=None, help="Filtrar por UF (ex: SP). Padrão: Brasil todo")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    print("=" * 60)
    print("TSE LOCAIS DE VOTAÇÃO — Agent B: Normalizador")
    print("=" * 60)
    normalizar(args.uf, args.force)


if __name__ == "__main__":
    main()

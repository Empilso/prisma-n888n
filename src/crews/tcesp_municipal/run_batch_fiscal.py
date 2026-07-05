"""
Orquestrador de lote — Fase 2 em escala: receitas+despesas de TODOS os municípios
fiscalizados pelo TCE-SP para um ano.

Encadeia por município: agent_d (bronze) → agent_e (prata) → agent_f (banco).
- Checkpoint em data/raw/tcesp/batch_checkpoint_{ano}.json — retomável após queda.
- Erros não interrompem o lote: município com falha é logado e o lote segue.
- Throttle entre municípios pra não sobrecarregar a API do TCE-SP.

Rodar:
    cd n888n-prisma
    python src/crews/tcesp_municipal/run_batch_fiscal.py --ano 2025
    python src/crews/tcesp_municipal/run_batch_fiscal.py --ano 2025 --limite 10   # teste
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psycopg2

BASE_DIR = Path(__file__).resolve().parents[3]
CREW_DIR = Path(__file__).resolve().parent
CHECKPOINT_DIR = BASE_DIR / "data/raw/tcesp"


def _slugs_ativos() -> list[str]:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        dbname=os.getenv("DB_NAME", "prisma_data"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.environ["DB_PASSWORD"],
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT slug_tcesp FROM tcesp_municipios
        WHERE ativo AND match_status IN ('exato', 'fuzzy', 'manual') AND id_ibge IS NOT NULL
        ORDER BY slug_tcesp
    """)
    slugs = [r[0] for r in cur.fetchall()]
    conn.close()
    return slugs


def _run_agent(script: str, slug: str, ano: int) -> bool:
    r = subprocess.run(
        [sys.executable, str(CREW_DIR / script), "--municipio", slug, "--ano", str(ano)],
        capture_output=True, text=True, timeout=1800, cwd=str(BASE_DIR),
    )
    if r.returncode != 0:
        print(f"    ✗ {script}: {(r.stderr or r.stdout)[-300:]}", flush=True)
        return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ano", type=int, required=True)
    parser.add_argument("--limite", type=int, default=0, help="processar só N municípios (teste)")
    parser.add_argument("--pausa", type=float, default=2.0, help="segundos entre municípios")
    args = parser.parse_args()

    ckpt_path = CHECKPOINT_DIR / f"batch_checkpoint_{args.ano}.json"
    ckpt = {"ok": [], "erro": []}
    if ckpt_path.exists():
        ckpt = json.loads(ckpt_path.read_text())
        print(f"Checkpoint: {len(ckpt['ok'])} ok, {len(ckpt['erro'])} com erro — retomando", flush=True)

    feitos = set(ckpt["ok"])
    slugs = [s for s in _slugs_ativos() if s not in feitos]
    if args.limite:
        slugs = slugs[: args.limite]
    print(f"Lote {args.ano}: {len(slugs)} municípios a processar ({len(feitos)} já feitos)", flush=True)

    for n, slug in enumerate(slugs, 1):
        t0 = time.time()
        print(f"[{n}/{len(slugs)}] {slug} …", flush=True)
        ok = (
            _run_agent("agent_d_coletor_fiscal.py", slug, args.ano)
            and _run_agent("agent_e_normalizador_fiscal.py", slug, args.ano)
            and _run_agent("agent_f_loader_fiscal.py", slug, args.ano)
        )
        if ok:
            ckpt["ok"].append(slug)
            print(f"    ✓ {time.time()-t0:.0f}s", flush=True)
        else:
            ckpt["erro"] = [e for e in ckpt["erro"] if e != slug] + [slug]
        ckpt_path.write_text(json.dumps(ckpt, ensure_ascii=False))
        time.sleep(args.pausa)

    print(f"\nFIM {datetime.now():%H:%M}: {len(ckpt['ok'])} ok | {len(ckpt['erro'])} erro")
    if ckpt["erro"]:
        print("Com erro (re-rodar depois):", ", ".join(ckpt["erro"][:30]))


if __name__ == "__main__":
    main()

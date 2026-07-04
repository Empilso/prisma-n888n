#!/usr/bin/env python3
"""TSE Locais de Votação — Crew completa

Execução padrão (Brasil inteiro):
    cd /path/to/n888n-prisma
    python src/crews/tse_locais_votacao/main.py

Só SP (mais rápido para testes):
    python src/crews/tse_locais_votacao/main.py --uf SP

Forçar re-download:
    python src/crews/tse_locais_votacao/main.py --force
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.crews.tse_locais_votacao.agent_a_coletor   import main as coletar
from src.crews.tse_locais_votacao.agent_b_normalizador import normalizar
from src.crews.tse_locais_votacao.agent_c_loader    import carregar


def main():
    ap = argparse.ArgumentParser(description="ETL: TSE Locais de Votação → PostgreSQL")
    ap.add_argument("--uf",      default=None, help="Filtrar UF (ex: SP). Padrão: Brasil todo")
    ap.add_argument("--force",   action="store_true", help="Re-baixa e reprocessa mesmo se já existe")
    ap.add_argument("--dry-run", action="store_true", help="Não grava no banco")
    args = ap.parse_args()

    print("=" * 60)
    print("TSE LOCAIS DE VOTAÇÃO — Pipeline completo")
    print(f"  UF: {args.uf or 'Brasil todo'}")
    print(f"  Dry-run: {args.dry_run}")
    print("=" * 60)

    # A — Coletar
    print("\n[1/3] Agent A — Coletor")
    coletar(args.force)

    # B — Normalizar
    print("\n[2/3] Agent B — Normalizador")
    normalizar(args.uf, args.force)

    # C — Loader
    print("\n[3/3] Agent C — Loader")
    carregar(args.uf, args.dry_run)

    print("\n" + "=" * 60)
    print("✅ Pipeline concluído!")
    print("=" * 60)


if __name__ == "__main__":
    main()

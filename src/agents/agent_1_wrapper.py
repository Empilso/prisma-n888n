import argparse
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.scraper_alba import scrape_lista_completa

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    env_ano = int(os.environ.get("ANO_ALVO", 2015))
    parser.add_argument("--ano", type=int, default=env_ano)
    parser.add_argument("--max_pages", type=int, default=0)
    args = parser.parse_args()

    print(f"============================================================")
    print(f"🕵️ [AGENT 1] Inicializando Scraper Autônomo para o Ano {args.ano}")
    print(f"============================================================")
    
    try:
        records = scrape_lista_completa(ano=args.ano, max_pages=args.max_pages)
        print(f"\n🏁 [AGENT 1] Processo finalizado com SUCESSO. {len(records)} registros coletados.\n")
    except Exception as e:
        print(f"\n❌ [CRITICAL ERROR] Falha no Sourcing: {e}\n")
        sys.exit(1)

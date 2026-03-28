import argparse
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.scraper_alba import scrape_lista_completa
from agents.agent_1_audit import audit_extraction

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Scraping robusto das despesas de gabinete da ALBA.",
        "especialidade": "Extração Web / HTML",
        "protocolo_tecnico": "Requests + BeautifulSoup4",
        "camada_dados": "Bronze (Dados Brutos)",
        "seguranca": "Rate Limiting Adaptativo"
    },
    "diretrizes": [
        "1. Navega no portal da transparência ALBA.",
        "2. Identifica depesas por deputado, categoria e credor.",
        "3. Lida com paginação infinita e bloqueios automáticos.",
        "4. Salva os dados brutos no Datalake (Camada Bronze).",
        "5. Audita discrepâncias de valores mensais (Smart Sync)."
    ],
    "apuracao": {
        "safras_suportadas": [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
        "saida_esperada": "data/saida/bronze/alba_{ano}_bronze.json"
    }
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    env_ano = int(os.environ.get("ANO_ALVO", 2015))
    parser.add_argument("--ano", type=int, default=env_ano)
    parser.add_argument("--max_pages", type=int, default=0)
    parser.add_argument("--smart", action="store_true", help="Faz verificação smart dos JSONs e só baixa o que falta")
    args = parser.parse_args()

    print(f"============================================================")
    print(f"🕵️ [AGENT 1] Inicializando Scraper Autônomo para o Ano {args.ano} {'(SMART SYNC ativado)' if args.smart else ''}")
    print(f"============================================================")
    
    try:
        records = scrape_lista_completa(ano=args.ano, max_pages=args.max_pages, smart=args.smart)
        print(f"\n🏁 [AGENT 1] Processo finalizado com SUCESSO. {len(records)} registros coletados.\n")
        
        # O auditor roda no final para atualizar o dashboard visual se existirem gaps
        print(f"\n🔍 [AGENT 1] Rodando auditoria final na safra...")
        audit_extraction(args.ano)
    except Exception as e:
        print(f"\n❌ [CRITICAL ERROR] Falha no Sourcing/Auditoria: {e}\n")
        sys.exit(1)

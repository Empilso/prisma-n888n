import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.scraper_alba import scrape_lista_completa

if __name__ == "__main__":
    print(f"============================================================")
    print(f"🕵️ [AGENT 1 BATCH] Inicializando Fila Mestra de Todas as Safras")
    print(f"============================================================")
    
    # Anos a processar
    anos = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
    
    checkpoint_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "saida", "bronze")
    
    processados = 0
    pulos = 0
    
    for ano in anos:
        final_file = os.path.join(checkpoint_dir, f"alba_{ano}.json")
        checkpoint_file = os.path.join(checkpoint_dir, f"alba_{ano}_checkpoint.json")
        
        # Ignora se já tem o arquivo final limpo (ouro puro)
        if os.path.exists(final_file) and not os.path.exists(checkpoint_file):
            print(f"⏩ [PULO] Safra {ano} já está completa. Pulando...")
            pulos += 1
            continue
            
        print(f"\n============================================================")
        print(f"🚀 [AGENT 1 BATCH] INICIANDO SAFRA {ano}")
        print(f"============================================================")
        try:
            records = scrape_lista_completa(ano=ano, max_pages=0)
            print(f"✅ Safra {ano} concluída! {len(records)} registros.")
            processados += 1
            time.sleep(5) # Pausa de segurança entre safras
        except Exception as e:
            print(f"❌ Erro na safra {ano}: {e}")
            sys.exit(1)
            
    print(f"\n============================================================")
    print(f"🎉🏁 [BINGO!] FILA MESTRA CONCLUÍDA. Processados: {processados} | Pulados: {pulos}")
    print(f"============================================================")

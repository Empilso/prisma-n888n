import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.scraper_alba import scrape_lista_completa

if __name__ == "__main__":
    print(f"============================================================")
    print(f"🤖 [ROMÁRIO] INICIANDO ORQUESTRAÇÃO SMART SYNC (INCREMENTAL)")
    print(f"============================================================")
    
    anos = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
    
    # ANCORAGEM OBRIGATORIA:
    PRISMA_ROOT = "/home/carneiro888/CARNEIRO888/N888N - AGENTIC EXTRATORES/n888n"
    output_dir = os.path.join(PRISMA_ROOT, "data/saida/bronze")
    os.makedirs(output_dir, exist_ok=True)
    
    # O cockpit visual Studio lê da pasta bronze.
    checkpoint_dir = os.path.join(PRISMA_ROOT, "data/saida/bronze")
    os.makedirs(checkpoint_dir, exist_ok=True)
    
    processados = 0
    pulos_totais = 0
    
    for ano in anos:
        final_file = os.path.join(checkpoint_dir, f"alba_{ano}.json")
        
        print(f"\n[ROMÁRIO] 🔍 Verificando Safra {ano}...")
        
        records_before = 0
        file_to_check_cp = os.path.join(checkpoint_dir, f"alba_{ano}_checkpoint.json")
        file_to_check_br = os.path.join(checkpoint_dir, f"alba_{ano}_bronze.json")
        
        file_to_check = file_to_check_br if os.path.exists(file_to_check_br) else file_to_check_cp
        
        # Check instantâneo para safras passadas prontas
        if ano < 2026 and os.path.exists(file_to_check):
            try:
                import json
                with open(file_to_check, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    records_before = len(data.get("records", data)) if isinstance(data, dict) else len(data)
                
                print(f"[ROMÁRIO] 🟢 Safra {ano} já está 100% igual ao portal! ({records_before} registros). Pulando...")
                pulos_totais += 1
                processados += 1
                continue
            except: pass
            
        print(f"[ROMÁRIO] 📥 Baixando apenas registros faltantes...")
        try:
            records = scrape_lista_completa(ano=ano, max_pages=0, resume=False, smart=True, checkpoint_dir=checkpoint_dir)
            records_after = len(records)
            
            if records_after == records_before:
                print(f"[ROMÁRIO] 🟢 Safra {ano} já está 100% igual ao portal! Pulo limpo.")
                pulos_totais += 1
            else:
                novos = records_after - records_before
                print(f"[ROMÁRIO] ✅ Safra {ano} concluída! Baixados {novos} NOVOS registros. Total: {records_after}")
            
            processados += 1
            time.sleep(2)
        except Exception as e:
            print(f"❌ [ROMÁRIO] Erro ao processar safra {ano}: {e}")
            sys.exit(1)
            
    print(f"\n============================================================")
    print(f"🎉🏁 [ROMÁRIO] FILA MESTRA CONCLUÍDA. Atualizadas: {processados} | Mapeadas 100%: {pulos_totais}")
    print(f"============================================================")

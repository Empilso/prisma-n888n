import os
import json
import argparse
import sys
import datetime

def audit_extraction(ano):
    print(f"============================================================")
    print(f"🔍 [AUDITOR FORENSE] Analisando Safra {ano} - Zorg-Romário")
    print(f"============================================================")
    
    # Paths
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    bronze_dir = os.path.join(base_dir, "data", "saida", "bronze")
    
    # O arquivo pode chamar alba_{ano}_bronze.json ou alba_{ano}.json dependendo de como o pipeline salvou
    verbas_file_1 = os.path.join(bronze_dir, f"alba_{ano}_bronze.json")
    verbas_file_2 = os.path.join(bronze_dir, f"alba_{ano}.json")
    
    verbas_file = verbas_file_1 if os.path.exists(verbas_file_1) else verbas_file_2
    parlamentares_file = os.path.join(base_dir, "data", "saida", "parlamentares", "parlamentares_hub_normalized.json")
    
    if not os.path.exists(parlamentares_file):
        print(f"❌ Erro: hub de parlamentares não encontrado ({parlamentares_file})")
        
        # Fallback para Zidan IDs local se existir
        parl_csv = os.path.join(base_dir, "data", "prisma_lista.csv")
        if not os.path.exists(parl_csv):
             sys.exit(1)
        import csv
        with open(parl_csv, "r", encoding="utf-8") as f:
             reader = csv.DictReader(f)
             deputados = list(reader)
    else:
        with open(parlamentares_file, "r", encoding="utf-8") as f:
            hub = json.load(f)
            if isinstance(hub, dict):
                deputados = hub.get("parlamentares", hub.get("records", []))
            else:
                deputados = hub
    
    todos_nomes = set(str(d.get("nome", d.get("nome_urna", ""))).strip().upper() for d in deputados)
    todos_nomes = set(n for n in todos_nomes if n)
    total_hub = len(todos_nomes)
    
    if not os.path.exists(verbas_file):
        print(f"❌ ALERTA MÁXIMO: Arquivo {'bronze' if 'bronze' in verbas_file else 'bruto'} para o ano {ano} não encontrado!")
        
        # Registra o audit indicando ZERO dados
        log_dir = os.path.join(base_dir, "data", "logs")
        os.makedirs(log_dir, exist_ok=True)
        report_file = os.path.join(log_dir, f"audit_verbas_{ano}.json")
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump({
                "ano": ano, "total_registros": 0, "deputados_com_dados": 0, "total_hub": total_hub, 
                "ausentes": list(todos_nomes), "contagem_detalhada": {}, "timestamp": datetime.datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        sys.exit(1)
        
    with open(verbas_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        records = data.get("records", []) if isinstance(data, dict) else data
        
    print(f"📊 Total de registros na safra: {len(records)}\n")
    
    # Contagem por Deputado
    contagem_deps = {}
    meses_deps = {}
    for r in records:
        nome = str(r.get("deputado", "")).strip().upper()
        if nome:
             contagem_deps[nome] = contagem_deps.get(nome, 0) + 1
             mes = r.get("mes", r.get("competencia", ""))
             if mes:
                 if nome not in meses_deps:
                     meses_deps[nome] = set()
                 meses_deps[nome].add(mes)
             
    nomes_em_verbas = set(contagem_deps.keys())
    
    ausentes = []
    # Tentativa de Match Aproximado (Contém parte do Nome)
    for n_hub in todos_nomes:
        parts = n_hub.split()
        primeiro_ultimo = f"{parts[0]} {parts[-1]}" if len(parts) > 1 else parts[0]
        
        encontrou = False
        for n_verba in nomes_em_verbas:
            if n_hub in n_verba or n_verba in n_hub or primeiro_ultimo in n_verba:
                encontrou = True
                break
        
        if not encontrou:
            ausentes.append(n_hub)
            
    print(f"🎯 Resumo de Parlamentares ({len(contagem_deps)} com verbas cadastradas):")
    
    if ausentes and len(ausentes) < total_hub: # Se a margem for quase todos, os matches podem ser incompatíveis
        print(f"\n⚠️ [ALERTA] {len(ausentes)}/{total_hub} Deputados SEM MENSURAÇÃO detectada:")
        display_limit = 10
        for i, a in enumerate(ausentes[:display_limit]):
            print(f"   - {a}")
        if len(ausentes) > display_limit:
            print(f"   ... e outros {len(ausentes) - display_limit}")
        print("\n=> RECOMENDA-SE RE/EXTRAÇÃO DESTES NOMES ESPECÍFICOS.\n")
    else:
        if not ausentes:
             print(f"✅ [OK] Excelente! Alto grau de compatibilidade (Zero Ausentes visíveis).\n")
        else:
             print(f"⚠️ [ATENÇÃO] Nomeclatura radicalmente diferente ou extração de ano eleitoral incompleto.\n")
         
    # Persist Report
    log_dir = os.path.join(base_dir, "data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    report_file = os.path.join(log_dir, f"audit_verbas_{ano}.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "ano": ano,
            "total_registros": len(records),
            "deputados_com_dados": len(contagem_deps),
            "total_hub": total_hub,
            "ausentes": ausentes,
            "contagem_detalhada": contagem_deps,
            "timestamp": datetime.datetime.now().isoformat()
        }, f, indent=2, ensure_ascii=False)
        
    print(f"💾 Relatório JSON persistido em: data/logs/audit_verbas_{ano}.json\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ano", type=int, required=True, help="Ano da safra a ser auditada")
    args = parser.parse_args()
    audit_extraction(args.ano)

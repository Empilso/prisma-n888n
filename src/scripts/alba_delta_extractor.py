"""
@dev *aiox-agentic-extractor*
Agente: extração alba de verbas de gabinete
Orquestrador: N888N Elite
Origem: Ingestão de Dados Históricos (/organizar)
Destino: Padrão PRISMA (Medallion: Bronze -> Prata -> Quarentena)
"""

import datetime
import hashlib
import json
import os
import re
from typing import List, Dict, Any

# =====================================================================
# CONFIGURAÇÃO DE DIRETÓRIOS (MEDALLION ARCHITECTURE)
# =====================================================================
BASE_RIVER = "n888n/data/saida"
PATHS = {
    "bronze": os.path.join(BASE_RIVER, "bronze"),
    "prata": os.path.join(BASE_RIVER, "prata"),
    "ouro": os.path.join(BASE_RIVER, "ouro"),
    "quarentena": os.path.join(BASE_RIVER, "quarentena"),
    "sys_logs": os.path.join(BASE_RIVER, "sys_logs")
}

for p in PATHS.values():
    os.makedirs(p, exist_ok=True)

def current_date_str():
    return datetime.datetime.now().strftime("%Y%m%d")

def timestamp_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

# =====================================================================
# AGENT 1: SOURCING (Ingestão do Tesouro Local)
# =====================================================================
class SourcingAgent:
    def __init__(self, raw_file_path: str):
        self.raw_file_path = raw_file_path
        self.run_date = current_date_str()

    def extract_data(self) -> List[Dict[str, Any]]:
        print(f"🕵️‍♂️ [1. Sourcing] Lendo base histórica bruta em: {self.raw_file_path}")
        
        if not os.path.exists(self.raw_file_path):
            print(f"❌ Erro: Arquivo {self.raw_file_path} não encontrado.")
            return []
            
        with open(self.raw_file_path, 'r', encoding='utf-8') as f:
            bronze_raw_data = json.load(f)
            
        # Pega uma amostra de 100 registros para não estourar a memória no primeiro teste
        limit = min(100, len(bronze_raw_data))
        sample_data = bronze_raw_data[:limit]
        
        # SALVANDO NA CAMADA BRONZE (Carimbo oficial do N888N)
        bronze_path = os.path.join(PATHS["bronze"], f"alba_verbas_ingestion_{self.run_date}.json")
        with open(bronze_path, 'w', encoding='utf-8') as f:
            json.dump(sample_data, f, ensure_ascii=False, indent=4)
            
        print(f"📦 [Bronze] Extração concluída. {limit} notas raw carimbadas em: {bronze_path}")
        return sample_data

# =====================================================================
# AGENT 2: VALIDATION (TRATAMENTO DE CHOQUE -> SCHEMA PRATA)
# =====================================================================
class ValidationAgent:
    
    def _clean_currency(self, val) -> float:
        if isinstance(val, (int, float)):
            return float(val)
        clean_str = str(val).replace('R$', '').replace('.', '').replace(',', '.').strip()
        try:
            return float(clean_str)
        except ValueError:
            return 0.0

    def _clean_cnpj(self, cnpj_str: str) -> str:
        clean = re.sub(r'[^0-9]', '', str(cnpj_str))
        return clean.zfill(14) if clean else ""
        
    def apply_universal_schema(self, raw_data: List[Dict[str, Any]]):
        print("🛡️ [2. Validation] Aplicando Tratamento de Choque e Mapeando para o Schema Universal Prisma...")
        silver_data = []
        quarantine_data = []
        
        for row in raw_data:
            # 1. Puxar campos do JSON Brutal
            num_processo = str(row.get('num_processo', ''))
            num_nf = str(row.get('num_nf', ''))
            
            # Id Origem composto para garantir clareza (Processo + NF se tiver)
            id_origem = f"{num_processo}-{num_nf}" if num_nf else num_processo
            hash_unico = hashlib.md5(id_origem.encode('utf-8')).hexdigest()
            
            valor_bruto = self._clean_currency(row.get('valor', 0))
            valor_glosado = self._clean_currency(row.get('valor_glosado', 0))
            valor_liquido = valor_bruto - valor_glosado
            
            cnpj_clean = self._clean_cnpj(row.get('cnpj_fornecedor', ''))
            
            # 2. Regras de Quarentena (CNPJ Vazio ou Inválido, Valor Zerado)
            if len(cnpj_clean) != 14 or valor_bruto <= 0:
                row['motivo_falha'] = "CNPJ inválido ou Valor zerado/negativo"
                quarantine_data.append(row)
                continue

            # 3. Construção do Schema Universal
            silver_record = {
                "id_origem": id_origem,
                "hash_unico": hash_unico,
                "politico_nome": str(row.get('deputado', '')).upper().strip(),
                "politico_id_tse": "", 
                "fornecedor_nome": str(row.get('nome_fornecedor', '')).upper().strip(),
                "fornecedor_cnpj": cnpj_clean,
                "valor_bruto": valor_bruto,
                "valor_liquido": round(valor_liquido, 2),
                "data_emissao": row.get('coletado_em', '')[:10], # Format YYYY-MM-DD
                "competencia": str(row.get('competencia', '')).strip(),
                "categoria_origem": str(row.get('categoria', '')).strip(),
                "link_documento": str(row.get('link_pdf_nf', '')).strip(),
                "link_portal": str(row.get('link_detalhe', '')).strip(),
                "extrator_nome": "agente_alba_sourcing_local",
                "extrator_data": timestamp_iso()
            }
            silver_data.append(silver_record)
        
        return silver_data, quarantine_data

# =====================================================================
# AGENT 3: LOADER (DATALAKE UPSERT)
# =====================================================================
class LoaderAgent:
    def __init__(self):
        self.run_date = current_date_str()
        
    def save_quarantine(self, quarantine_data: List[Dict]):
        if not quarantine_data: return
        q_path = os.path.join(PATHS["quarentena"], f"alba_verbas_falhas_{self.run_date}.json")
        with open(q_path, 'w', encoding='utf-8') as f:
            json.dump(quarantine_data, f, ensure_ascii=False, indent=4)
        print(f"⚠️ [Quarentena] Salvos {len(quarantine_data)} registros rejeitados em: {q_path}")

    def upsert_silver_lake(self, silver_data: List[Dict[str, Any]]):
        if not silver_data:
            print("💽 [3. Loader] Nenhuma nota limpa para salvar na Prata.")
            return
            
        silver_path = os.path.join(PATHS["prata"], f"alba_verbas_clean_{self.run_date}.json")
        
        print(f"💽 [3. Loader] Gravando Camada Prata: {silver_path}")
        with open(silver_path, 'w', encoding='utf-8') as f:
            json.dump(silver_data, f, ensure_ascii=False, indent=4)
            
        print(f"🎉 [Sucesso] {len(silver_data)} notas perfeitas, no Schema Universal, prontas para a Camada Ouro (AIOX).")

# =====================================================================
# ORQUESTRAÇÃO DA MISSÃO ALBA
# =====================================================================
def run_alba_ingestion_crew():
    print("\n" + "="*60)
    print("🚀 N888N CREW: INGESTÃO DE BASE HISTÓRICA (PRISMA STANDARD)")
    print("="*60 + "\n")
    
    # 1. Sourcing
    tesouro_path = "/home/carneiro888/CARNEIRO888/N888N - AGENTIC EXTRATORES/organizar/alba_TODOS_2026_checkpoint.json"
    sourcing = SourcingAgent(raw_file_path=tesouro_path)
    raw_data = sourcing.extract_data()
    
    if raw_data:
        # 2. Validation & Schema
        validation = ValidationAgent()
        silver_data, quarantine_data = validation.apply_universal_schema(raw_data)
        
        # 3. Load
        loader = LoaderAgent()
        loader.save_quarantine(quarantine_data)
        loader.upsert_silver_lake(silver_data)
    
    print("\n" + "="*60)
    print("🏁 Fluxo de Ingestão Finalizado.")
    print("="*60 + "\n")

if __name__ == "__main__":
    run_alba_ingestion_crew()

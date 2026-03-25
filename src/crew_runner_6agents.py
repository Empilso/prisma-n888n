import os
import pandas as pd
from datetime import date
from decimal import Decimal
from typing import List

# Importando nossos novos módulos
from utils.scraper_alba import scrape_lista_completa, scrape_detalhes, download_pdf
from utils.pdf_extractor import extract_pdf_native
from models.prisma_schema import VerbaIndenizatoria

# Configurações de Diretório
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data", "saida")
ANEXOS_DIR = os.path.join(DATA_DIR, "anexos")

def run_prisma_6agents_pipeline(anos_range: List[int] = [2023], limit_per_year: int = 5):
    """
    Orquestrador Retroativo para o modo de 6 Agentes.
    Percorre o range de anos (ex: desde 2015) consolidando o Datalake.
    """
    print(f"\n🚀 [PRISMA 6 AGENTS] Iniciando Ciclo Retroativo (Anos: {anos_range})...")
    
    records_globais = []
    
    for ano in anos_range:
        # --- AGENT 1: Web Data Engineer ---
        print(f"\n🕵️ Agent 1: Scraping {ano} (Lista + Detalhes + PDFs)...")
        lista_ano = scrape_lista_completa(ano=ano)
        
        for i, item in enumerate(lista_ano[:limit_per_year]):
            id_alba = item["id_alba"]
            print(f"  🔍 [{ano}] Processando Registro {i+1}/{limit_per_year} (ID: {id_alba})...")
            
            # Detalhes da Web
            info_detalhe = scrape_detalhes(id_alba)
            item.update(info_detalhe)
            
            # Download do PDF (se existir)
            link_pdf = item.get("link_pdf")
            if link_pdf:
                path_pdf = download_pdf(link_pdf, ANEXOS_DIR, id_alba)
                
                # --- AGENT 5: PDF Forensic ---
                if path_pdf and os.path.exists(path_pdf):
                    print(f"    📄 Agent 5: Extraindo dados do PDF histórico...")
                    pdf_data = extract_pdf_native(path_pdf)
                    item.update({f"pdf_{k}": v for k, v in pdf_data.items()})
                    item["fonte_pdf"] = f"PyMuPDF Native ({ano})"
            
            records_globais.append(item)

    # --- AGENT 2: Chunker & Validator ---
    print(f"\n🧹 Agent 2: Validando {len(records_globais)} registros no total...")
    validated_records = []
    for r in records_globais:
        try:
            obj = VerbaIndenizatoria(
                id_alba=r['id_alba'],
                processo=r['processo'],
                numero_nf=r['numero_nf'],
                competencia=r['competencia'],
                deputado=r['deputado'],
                categoria_html=r['categoria_html'],
                valor_html=r['valor_html'],
                categoria_detalhe=r.get('categoria_detalhe'),
                numero_recibo=r.get('numero_recibo'),
                cpf_cnpj=r.get('cpf_cnpj'),
                fornecedor=r.get('fornecedor'),
                valor_pdf=r.get('pdf_valor_pdf_extraido') or r.get('valor_pdf'),
                glosa=r.get('glosa', Decimal('0')),
                link_pdf=r.get('link_pdf'),
                risco_nivel="BAIXO", 
                comentario_aguia=f"Auditado via Retroatividade PRISMA - Competência {r['competencia']}."
            )
            validated_records.append(obj.model_dump())
        except Exception as e:
            print(f"    ❌ Falha na validação {r.get('id_alba')}: {e}")

    # --- AGENT 6: Prisma Merge Final ---
    print("\n💎 Agent 6: Gerando Prisma Base Consolidado (Parquet)...")
    if validated_records:
        df = pd.DataFrame(validated_records)
        output_path = os.path.join(DATA_DIR, "ouro", "prisma_completo.parquet")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        df.to_parquet(output_path, index=False)
        df.to_json(output_path.replace(".parquet", ".json"), orient="records", indent=2)
        
        print(f"✅ CICLO RETROATIVO COMPLETO! {len(validated_records)} registros salvos.")
        return output_path
    else:
        print("⚠️ Nenhum registro processado com sucesso.")
        return None

if __name__ == "__main__":
    # Teste de Arqueologia: Pegando os 3 primeiros de 2015 para validar a estrutura antiga
    run_prisma_6agents_pipeline(anos_range=[2015], limit_per_year=3)


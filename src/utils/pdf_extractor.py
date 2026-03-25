import fitz # PyMuPDF
import re
import os
from decimal import Decimal
from typing import Optional

def extract_pdf_native(pdf_path: str) -> dict:
    """Extração nativa PyMuPDF com Regex para despesas ALBA."""
    extracted = {}
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        
        # Padrões comuns em NF-e / Danfe / Recibos
        patterns = {
            "numero_nfse": r"Nº\s*(?:NFSe|Nota Fiscal|Recibo)\s*:?\s*(\d+)",
            "data_emissao": r"Data\s+de\s*(?:Emissão|Competência)\s*:?\s*(\d{2}/\d{2}/\d{4})",
            "valor_total_pdf": r"(?:Total\s+a\s*Pagar|Valor\s*Total|Valor\s*da\s*Nota)\s*:?\s*R\$\s*([\d.,]+)",
            "cnpj_emitente": r"(?:CNPJ|CPF|Inscrição)\s*:?\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2})",
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                extracted[key] = match.group(1).strip()
        
        if "valor_total_pdf" in extracted:
            raw_val = extracted["valor_total_pdf"].replace(".", "").replace(",", ".")
            try:
                extracted["valor_pdf_extraido"] = Decimal(raw_val)
            except:
                pass
            
        extracted["texto_bruto_pdf"] = text # Texto completo para o Agent 5 (DeepSeek) analisar se faltar campos
        
    except Exception as e:
        print(f"  ⚠️ Erro na extração nativa do PDF {pdf_path}: {e}")
        
    return extracted

def analyze_pdf_text_with_llm(text: str) -> dict:
    """
    Fallback Econômico: Envia o texto extraído para DeepSeek-V3 
    para estruturar campos que o Regex falhou.
    (Simulação de chamada que será feita pelo Agent 5 da CrewAI)
    """
    # Em produção, o Agent 5 usaria este texto como input.
    return {"status": "ready_for_llm_agent", "text_length": len(text)}

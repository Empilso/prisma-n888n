import requests
from bs4 import BeautifulSoup
import os
import re
import json
import time
import random
from decimal import Decimal
from typing import Optional, Union
from datetime import datetime
import argparse

def parse_valor(texto: str) -> float:
    """'R$ 27.840,00' → 27840.00 — NUNCA aplica replace('.','') em floats."""
    # Remove tudo exceto dígitos e vírgula, depois troca vírgula por ponto
    s = re.sub(r"[^\d,]", "", str(texto)).replace(",", ".")
    try:
        return float(s)
    except:
        return 0.0

def detectar_tipo_doc(doc: str) -> str:
    digits = re.sub(r"\D", "", doc)
    if len(digits) == 14:
        return "CNPJ"
    elif len(digits) == 11:
        return "CPF"
    return "DESCONHECIDO"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

BASE_URL = "https://www.al.ba.gov.br/transparencia/verbas-idenizatorias"

def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def _save_checkpoint(records, ano, checkpoint_dir, current_page):
    """Salva checkpoint incremental com metadados de página."""
    filepath = os.path.join(checkpoint_dir, f"alba_{ano}_checkpoint.json")
    checkpoint_data = {
        "ano": ano,
        "last_page": current_page,
        "total_records": len(records),
        "updated_at": datetime.now().isoformat(),
        "records": records
    }
    with open(filepath, "w", encoding='utf-8') as f:
        json.dump(checkpoint_data, f, indent=2, default=_decimal_default, ensure_ascii=False)

def _defaults_detalhe() -> dict:
    return {
        "cnpj_fornecedor": "",
        "nome_fornecedor": "",
        "valor_glosado": 0.0,
        "valor_detalhe": 0.0,
        "link_pdf_nf": "SEM_PDF_ANEXO",
        "tipo_documento": "",
        "categoria_detalhe": "",
        "numero_nf_recibo": "",
    }

def scrape_detalhes(id_alba: str, session=None) -> dict:
    url = f"{BASE_URL}/{id_alba}/"
    result = _defaults_detalhe()
    if session is None: session = requests.Session()
    
    max_retries = 2
    for attempt in range(max_retries):
        try:
            resp = session.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            tabelas = soup.find_all("table")
            tabela = tabelas[1] if len(tabelas) > 1 else (tabelas[0] if tabelas else None)
            if tabela:
                linhas = tabela.find_all("tr")[1:]
                for linha in linhas:
                    celulas = linha.find_all(["td", "th"])
                    if len(celulas) < 4: continue
                    result["categoria_detalhe"] = celulas[0].get_text(strip=True)
                    result["numero_nf_recibo"] = celulas[1].get_text(strip=True)
                    cnpj_raw = celulas[2].get_text(strip=True)
                    result["cnpj_fornecedor"] = cnpj_raw
                    result["tipo_documento"] = detectar_tipo_doc(cnpj_raw)
                    result["nome_fornecedor"] = celulas[3].get_text(strip=True)
                    result["valor_detalhe"] = parse_valor(celulas[4].get_text(strip=True))
                    result["valor_glosado"] = parse_valor(celulas[5].get_text(strip=True))
                    link_a = celulas[6].find("a", href=True)
                    if link_a: result["link_pdf_nf"] = link_a["href"]
            return result
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            print(f"    ⚠️ Falha Detalhes {id_alba} após {max_retries} tentativas: {e}")
    return result

def scrape_lista_completa(ano: int = 2024, mes: Optional[int] = None, checkpoint_dir: Optional[str] = None, max_pages: int = 0, resume: bool = False) -> list[dict]:
    if not checkpoint_dir:
        checkpoint_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "saida", "bronze")
    os.makedirs(checkpoint_dir, exist_ok=True)
    checkpoint_file = os.path.join(checkpoint_dir, f"alba_{ano}_checkpoint.json")
    final_file = os.path.join(checkpoint_dir, f"alba_{ano}_bronze.json")
    all_records = []
    page = 1
    if resume and os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, "r", encoding='utf-8') as f:
                cp = json.load(f)
                all_records = cp.get("records", [])
                page = cp.get("last_page", 0) + 1
            print(f"\n🔄 [AGENT 1] RETOMADA ATIVA! Página atual: {page}")
        except: pass
    print(f"\n🕵️ [AGENT 1] ALBA — Ano: {ano} | Pág Inicial: {page}")
    while True:
        try:
            params = {"ano": ano, "page": page}
            if mes: params["mes"] = mes
            
            resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30, verify=False)
            
            if resp.status_code != 200:
                if resp.status_code == 404: break
                # Pequena pausa e retenta UMA VEZ se não for 404
                time.sleep(2)
                resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30, verify=False)
                if resp.status_code != 200: break
            
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = [r for r in soup.find_all("tr") if len(r.find_all("td")) >= 6 and r.find("a", href=True)]
            
            if not rows:
                print(f"  🏁 Fim das linhas na Página {page}.")
                break
                
            for row in rows:
                cells = [c.get_text(strip=True) for c in row.find_all("td")]
                link = row.find("a", href=True)
                id_alba = [p for p in link["href"].split("/") if p.isdigit()][-1]
                record = {
                    "num_processo": cells[0], "num_nf": cells[1], "competencia": cells[2],
                    "deputado": " ".join(cells[3].split()), "categoria": cells[4],
                    "valor": parse_valor(cells[5]), "link_detalhe": f"{BASE_URL}/{id_alba}/",
                    "ano": ano, "coletado_em": datetime.now().isoformat()
                }
                record.update(scrape_detalhes(id_alba))
                all_records.append(record)
            
            print(f"  📄 Pág {page:>3} | Total: {len(all_records):>5} | {datetime.now().strftime('%H:%M:%S')}")
            if page % 5 == 0: _save_checkpoint(all_records, ano, checkpoint_dir, page)
            page += 1
            if max_pages > 0 and page > max_pages: break
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  ❌ Erro na Página {page}: {e}")
            break
    if all_records:
        _save_checkpoint(all_records, ano, checkpoint_dir, page - 1)
        with open(final_file, "w", encoding='utf-8') as f:
            json.dump(all_records, f, indent=2, default=_decimal_default, ensure_ascii=False)
    return all_records

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ano", type=int, default=2022)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max_pages", type=int, default=0)
    args = parser.parse_args()
    scrape_lista_completa(ano=args.ano, resume=args.resume, max_pages=args.max_pages)

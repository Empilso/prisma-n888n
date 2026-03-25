"""
scraper_alba_proxy.py — ALBA Verbas com Proxy ScrapingBee
Supera bloqueio de IP via tunnel premium ScrapingBee.
Uso: python3 scraper_alba_proxy.py --ano 2025
"""
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from bs4 import BeautifulSoup
import os
import re
import json
import time
import random
from decimal import Decimal
from typing import Optional
from datetime import datetime
import argparse

# ── CONFIG ────────────────────────────────────────────────────────────────────
API_KEY = "LZXJT6XUTY444K9GKB5YPJT86ANZKTBY2KOKS2W6MDHO1GNOEBSCUN75DHM1M3I5KE48MQJB68EYECY0"
# ScrapingBee: API_KEY como usuário, senha em branco, porta 8886
PROXIES = {
    "http":  f"http://{API_KEY}:@proxy.scrapingbee.com:8886",
    "https": f"http://{API_KEY}:@proxy.scrapingbee.com:8886",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

BASE_URL = "https://www.al.ba.gov.br/transparencia/verbas-idenizatorias"
# ─────────────────────────────────────────────────────────────────────────────


def _get(url, params=None, timeout=40):
    """Requisição via ScrapingBee Proxy."""
    return requests.get(url, params=params, headers=HEADERS,
                        proxies=PROXIES, verify=False, timeout=timeout)


def parse_valor(texto: str) -> float:
    s = re.sub(r"[^\d,]", "", str(texto)).replace(",", ".")
    try: return float(s)
    except: return 0.0


def detectar_tipo_doc(doc: str) -> str:
    digits = re.sub(r"\D", "", doc)
    if len(digits) == 14: return "CNPJ"
    if len(digits) == 11: return "CPF"
    return "DESCONHECIDO"


def _decimal_default(obj):
    if isinstance(obj, Decimal): return float(obj)
    raise TypeError


def _defaults_detalhe() -> dict:
    return {
        "cnpj_fornecedor": "", "nome_fornecedor": "",
        "valor_glosado": 0.0, "valor_detalhe": 0.0,
        "link_pdf_nf": "SEM_PDF_ANEXO", "tipo_documento": "",
        "categoria_detalhe": "", "numero_nf_recibo": "",
    }


def _save_checkpoint(records, ano, checkpoint_dir, current_page):
    filepath = os.path.join(checkpoint_dir, f"alba_{ano}_checkpoint.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "ano": ano, "last_page": current_page,
            "total_records": len(records),
            "updated_at": datetime.now().isoformat(),
            "records": records
        }, f, indent=2, default=_decimal_default, ensure_ascii=False)


def scrape_detalhes(id_alba: str) -> dict:
    url = f"{BASE_URL}/{id_alba}/"
    result = _defaults_detalhe()
    for attempt in range(2):
        try:
            resp = _get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            tabelas = soup.find_all("table")
            tabela = tabelas[1] if len(tabelas) > 1 else (tabelas[0] if tabelas else None)
            if tabela:
                for linha in tabela.find_all("tr")[1:]:
                    celulas = linha.find_all(["td", "th"])
                    if len(celulas) < 4: continue
                    result["categoria_detalhe"] = celulas[0].get_text(strip=True)
                    result["numero_nf_recibo"]   = celulas[1].get_text(strip=True)
                    cnpj_raw = celulas[2].get_text(strip=True)
                    result["cnpj_fornecedor"]    = cnpj_raw
                    result["tipo_documento"]     = detectar_tipo_doc(cnpj_raw)
                    result["nome_fornecedor"]    = celulas[3].get_text(strip=True)
                    result["valor_detalhe"]      = parse_valor(celulas[4].get_text(strip=True))
                    result["valor_glosado"]      = parse_valor(celulas[5].get_text(strip=True))
                    link_a = celulas[6].find("a", href=True)
                    if link_a: result["link_pdf_nf"] = link_a["href"]
            return result
        except Exception as e:
            if attempt == 0: time.sleep(2)
            else: print(f"    ⚠️ Detalhes {id_alba}: {e}")
    return result


def scrape_lista_completa(ano: int = 2025, mes: Optional[int] = None,
                           max_pages: int = 0, resume: bool = False) -> list:
    checkpoint_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "saida", "bronze")
    os.makedirs(checkpoint_dir, exist_ok=True)

    checkpoint_file = os.path.join(checkpoint_dir, f"alba_{ano}_checkpoint.json")
    final_file      = os.path.join(checkpoint_dir, f"alba_{ano}_bronze.json")
    all_records = []
    page = 1

    if resume and os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                cp = json.load(f)
                all_records = cp.get("records", [])
                page = cp.get("last_page", 0) + 1
            print(f"\n🔄 [PROXY] RETOMADA ATIVA! Página: {page}")
        except: pass

    print(f"\n🕵️ [PROXY] ALBA via ScrapingBee — Ano: {ano} | Pág: {page}")

    while True:
        try:
            params = {"ano": ano, "page": page}
            if mes: params["mes"] = mes

            resp = _get(BASE_URL, params=params)

            # ScrapingBee retorna 200 mesmo em erros — checa tamanho/conteúdo
            if resp.status_code != 200:
                print(f"  ⚠️ HTTP {resp.status_code} na pág {page}, finalizando.")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            rows = [r for r in soup.find_all("tr")
                    if len(r.find_all("td")) >= 6 and r.find("a", href=True)]

            if not rows:
                print(f"  🏁 Sem linhas na Pág {page}. Fim.")
                break

            for row in rows:
                cells = [c.get_text(strip=True) for c in row.find_all("td")]
                link  = row.find("a", href=True)
                id_alba = [p for p in link["href"].split("/") if p.isdigit()][-1]
                record = {
                    "num_processo": cells[0], "num_nf": cells[1],
                    "competencia":  cells[2],
                    "deputado":     " ".join(cells[3].split()),
                    "categoria":    cells[4],
                    "valor":        parse_valor(cells[5]),
                    "link_detalhe": f"{BASE_URL}/{id_alba}/",
                    "ano":          ano,
                    "coletado_em":  datetime.now().isoformat(),
                }
                record.update(scrape_detalhes(id_alba))
                all_records.append(record)

            print(f"  📄 Pág {page:>3} | Total: {len(all_records):>5} | {datetime.now().strftime('%H:%M:%S')}")
            if page % 5 == 0:
                _save_checkpoint(all_records, ano, checkpoint_dir, page)

            page += 1
            if max_pages > 0 and page > max_pages: break
            time.sleep(0.8)

        except Exception as e:
            print(f"  ❌ Erro Pág {page}: {e}")
            break

    if all_records:
        _save_checkpoint(all_records, ano, checkpoint_dir, page - 1)
        with open(final_file, "w", encoding="utf-8") as f:
            json.dump(all_records, f, indent=2, default=_decimal_default, ensure_ascii=False)
        print(f"\n✅ {len(all_records)} registros salvos em {final_file}")
    else:
        print("\n⚠️ Nenhum registro extraído.")

    return all_records


# ── TESTE DE CONECTIVIDADE ────────────────────────────────────────────────────
def test_conectividade():
    urls = [
        ("homepage",  "https://www.al.ba.gov.br/"),
        ("atividades","https://www.al.ba.gov.br/atividade-legislativa"),
        ("verbas",    BASE_URL),
    ]
    print("\n🧪 === TESTE DE CONECTIVIDADE (ScrapingBee) ===")
    for nome, url in urls:
        try:
            r = _get(url)
            print(f"  [{nome}] HTTP {r.status_code} | {len(r.content)} bytes ✅")
        except Exception as e:
            print(f"  [{nome}] ERRO: {e} ❌")
    print("===============================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ano",       type=int, default=2025)
    parser.add_argument("--resume",    action="store_true")
    parser.add_argument("--max_pages", type=int, default=0)
    parser.add_argument("--test",      action="store_true", help="Apenas testa conectividade")
    args = parser.parse_args()

    test_conectividade()

    if not args.test:
        scrape_lista_completa(ano=args.ano, resume=args.resume, max_pages=args.max_pages)

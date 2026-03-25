"""
Teste de Conectividade ALBA — 3 URLs estratégicas
"""
import requests
import json
import os
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

URLS = [
    ("homepage",     "https://www.al.ba.gov.br/"),
    ("atividades",   "https://www.al.ba.gov.br/atividade-legislativa"),
    ("verbas",       "https://www.al.ba.gov.br/transparencia/verbas-idenizatorias"),
]

out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "raw", "alba")
os.makedirs(out_dir, exist_ok=True)

resultados = []

for nome, url in URLS:
    print(f"\n🔍 Testando [{nome}]: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, verify=False)
        status  = r.status_code
        tamanho = len(r.content)
        print(f"  ✅ HTTP {status} | {tamanho} bytes")

        html_path = os.path.join(out_dir, f"test_{nome}_2026.html")
        with open(html_path, "wb") as f:
            f.write(r.content)
        print(f"  💾 Salvo: {html_path}")

        resultados.append({"url": url, "nome": nome, "status": status, "bytes": tamanho, "erro": None})
    except Exception as e:
        erro = str(e)
        print(f"  ❌ ERRO: {erro}")
        resultados.append({"url": url, "nome": nome, "status": None, "bytes": 0, "erro": erro})

# Salva relatório JSON
relatorio = {"ts": datetime.now().isoformat(), "resultados": resultados}
json_path = os.path.join(out_dir, "test_conect_2026.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(relatorio, f, ensure_ascii=False, indent=2)

print(f"\n📊 Relatório salvo em: {json_path}")

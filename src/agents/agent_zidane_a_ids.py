"""
Agent Zidane-A: O Coletor de IDs (Híbrido)
Fase 1 — Coleta de parlamentares com Fallback: API -> Selenium.
"""
import os, sys, json, re, time, argparse
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

try:
    from selenium import webdriver
    from bs4 import BeautifulSoup
except ImportError:
    pass

VERSION = "zidane_v3.0_hybrid"
BASE_URL = "https://albalegis.nopapercloud.com.br"

def extrair_via_api(status_id: int = 1) -> List[Dict]:
    """Tenta extrair via API de Dados Abertos (Rápido)."""
    api_url = f"{BASE_URL}/api/publico/parlamentar/"
    params = {"parlamentarSituacao": status_id, "qtd": 100, "pag": 1}
    print(f"📡 [ZIDANE-A] Tentando API Dados Abertos (Timeout 30s)...")
    try:
        resp = requests.get(api_url, params=params, verify=False, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        deputados = []
        for info in data:
            pid = info.get("parlamentarID")
            if not pid: continue
            deputados.append({
                "parlamentar_id": pid,
                "autor_id": info.get("autorID"),
                "nome_parlamentar": info.get("parlamentarNome"),
                "partido_atual": info.get("parlamentarSiglaPartido"),
                "status": "ativo" if status_id == 1 else "inativo",
                "foto_url": f"{BASE_URL}{info.get('parlamentarFoto')}" if info.get('parlamentarFoto') else None,
                "url_perfil": f"{BASE_URL}/spl/parlamentar.aspx?id={pid}"
            })
        return deputados
    except Exception as e:
        print(f"⚠️ [ZIDANE-A] API falhou ou Timeout: {e}")
        return []

def extrair_via_selenium(status: str = "ativo") -> List[Dict]:
    """Fallback: Extração via Selenium Headless (Lento mas Seguro)."""
    url = f"{BASE_URL}/spl/parlamentares.aspx"
    print(f"🕵️ [ZIDANE-A] Iniciando Fallback Selenium: {url}")
    
    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'eager'
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(45)
        driver.get(url)
        time.sleep(5)
        html = driver.page_source
        driver.quit()
        
        soup = BeautifulSoup(html, "lxml")
        deputados = []
        vistos = set()
        for card in soup.find_all("div", class_="custom-user-profile"):
            link = card.find("a", href=re.compile(r"parlamentar\.aspx\?id=\d+"))
            if not link: continue
            pid = int(re.search(r"id=(\d+)", link["href"]).group(1))
            if pid in vistos: continue
            vistos.add(pid)
            
            nome = card.find("a", class_="kt-widget__username")
            partido = card.find("small")
            img = card.find("img", class_="kt-widget__img")
            producao = card.find("a", href=re.compile(r"consulta-producao\.aspx\?autor=\d+"))
            
            deputados.append({
                "parlamentar_id": pid,
                "autor_id": int(re.search(r"autor=(\d+)", producao["href"]).group(1)) if producao else None,
                "nome_parlamentar": nome.get_text(strip=True) if nome else "Desconhecido",
                "partido_atual": partido.get_text(strip=True).strip("()") if partido else "S/P",
                "status": status,
                "foto_url": f"{BASE_URL}{img['src']}" if img and img.get('src') else None,
                "url_perfil": f"{BASE_URL}/spl/parlamentar.aspx?id={pid}"
            })
        return deputados
    except Exception as e:
        print(f"❌ [ZIDANE-A] Falha crítica no Selenium: {e}")
        return []

def main():
    base_dir = Path(__file__).resolve().parent.parent.parent
    output_dir = base_dir / "data" / "parlamentares"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Tenta API
    ativos = extrair_via_api(1)
    
    # 2. Se falhar, tenta Selenium
    if not ativos:
        print("🔄 [ZIDANE-A] API sem resposta ou vazia. Ativando Resgate via Selenium...")
        ativos = extrair_via_selenium("ativo")

    if not ativos:
        print("💀 [ZIDANE-A] Ambos os métodos falharam. Portal Offline?")
        return

    print(f"\n✅ [ZIDANE-A] Sucesso! Coletados {len(ativos)} parlamentares.")
    
    output = {
        "total": len(ativos),
        "coletado_em": datetime.utcnow().isoformat() + "Z",
        "metodo": "api" if len(ativos) > 0 and "metodo" not in locals() else "selenium",
        "records": ativos
    }

    with open(output_dir / "parlamentares_ids.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"💾 [ZIDANE-A] JSON salvo em data/parlamentares/")

if __name__ == "__main__":
    main()

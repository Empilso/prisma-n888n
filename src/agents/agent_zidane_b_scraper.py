#!/usr/bin/env python3
"""
⚽ AGENT ZIDANE-B v4.0 — HUB PARLAMENTAR PRISMA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FONTE:  https://www.al.ba.gov.br/deputados/deputados-estaduais
OUTPUT: data/saida/parlamentares/raw/parlamentar_{id}_oficial.json
CAMPOS: prisma_id, nome_limpo, partido, bio, contatos, metadados PRISMA
"""

import os, sys, json, re, time, hashlib, argparse
import requests
import urllib3
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from typing import Dict, List, Optional

# Silencia avisos de SSL (InsecureRequestWarning) para um terminal mais limpo
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://www.al.ba.gov.br"
URL_LISTA = f"{BASE_URL}/deputados/deputados-estaduais"
VERSAO = "v4.0-prisma-hub"

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Deep Scrape dos perfis de deputados estaduais da ALBA.",
        "especialidade": "Extração Textual Complexa (Regex + DOM Traversal)",
        "protocolo_tecnico": "Requests + BeautifulSoup4 + LXML + RegEx",
        "camada_dados": "Raw (Bronze Detalhado)",
        "seguranca": "Timeout 30s + Sleep entre requests (0.8s) + Checkpoints"
    },
    "diretrizes": [
        "1. Acessa a página individual (perfil) de cada deputado coletada no Zidane-A.",
        "2. Varre blocos de texto não-estruturados na div .fe-dep-dados-ajsut-mobile.",
        "3. Usa Expressões Regulares (Regex) para garimpar emails e telefones ocultos.",
        "4. Segmenta e estrutura a biografia por tópicos (Formação, Obras, etc.).",
        "5. Salva um arquivo JSON individualizado por deputado na camada raw."
    ],
    "apuracao": {
        "safras_suportadas": ["Atual (Tempo Real)"],
        "saida_esperada": "data/saida/parlamentares/raw/parlamentar_{id}_oficial.json"
    }
}



def gerar_prisma_id(nome: str, partido: str, url: str) -> str:
    """Gera hash MD5 único para o parlamentar com base em nome + partido + slug da URL."""
    payload = f"{nome.lower().strip()}{partido.lower().strip()}{url.rstrip('/').split('/')[-1]}"
    return hashlib.md5(payload.encode()).hexdigest()

# ── Estética Premium Terminal ─────────────────────────────────────────
C_PURPLE = "\033[95m"
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_WHITE = "\033[97m"
C_BOLD = "\033[1m"
C_END = "\033[0m"

def print_header(title: str):
    width = 70
    print(f"\n{C_PURPLE}╔" + "═"*(width-2) + f"╗{C_END}")
    print(f"{C_PURPLE}║{C_BOLD}{C_CYAN} {title.center(width-4)} {C_END}{C_PURPLE}║{C_END}")
    print(f"{C_PURPLE}╚" + "═"*(width-2) + f"╝{C_END}\n")

def print_status(msg: str, status="info"):
    icons = {"info": "🔹", "success": "✅", "error": "❌", "warn": "⚠️", "process": "⚙️", "user": "👤"}
    colors = {"info": C_CYAN, "success": C_GREEN, "error": C_RED, "warn": C_YELLOW, "process": C_PURPLE, "user": C_BOLD}
    icon = icons.get(status, "🔹")
    color = colors.get(status, C_CYAN)
    print(f"{color}{icon} {msg}{C_END}")


def get_soup(url: str) -> Optional[BeautifulSoup]:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    try:
        resp = requests.get(url, headers=headers, verify=False, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.content, "lxml")
    except Exception as e:
        print(f"    ❌ Erro ao acessar: {url} → {e}")
        return None


def scrape_perfil(url_perfil: str) -> Dict:
    """Deep scrape do perfil: bio, dados pessoais, mandatos, contatos."""
    soup = get_soup(url_perfil)
    if not soup:
        return {"biografia_completa": None, "dados_pessoais": {}, "formacao": None,
                "atividade_profissional": None, "contatos": {"email": None, "telefones": []},
                "mandatos": [], "foto_url": None}

    dados = {"biografia_completa": None, "dados_pessoais": {}, "formacao": None,
             "atividade_profissional": None, "contatos": {"email": None, "telefones": []},
             "mandatos": [], "foto_url": None}

    # ── Foto ────────────────────────────────────────────────────────────
    foto = soup.select_one(".deputado-img, .foto-deputado img")
    if foto and foto.get("src"):
        src = foto["src"].split("/static:")[0]  # remove fallback avatar
        dados["foto_url"] = BASE_URL + src if src.startswith("/") else src

    # ── Dados Pessoais (.dados-deputado) ────────────────────────────────
    dados_div = soup.select_one(".dados-deputado")
    if dados_div:
        texto = dados_div.get_text(separator="|", strip=True)
        partes = [p.strip() for p in texto.split("|") if p.strip()]
        for i in range(0, len(partes) - 1, 2):
            chave = partes[i].rstrip(":").strip()
            valor = partes[i + 1].strip() if (i + 1) < len(partes) else ""
            if chave and valor:
                dados["dados_pessoais"][chave] = valor

    # ── Formação, Atividade e Mandatos (.fe-dep-dados-ajsut-mobile) ─────
    bio_div = soup.select_one(".fe-dep-dados-ajsut-mobile")
    if bio_div:
        texto_completo = bio_div.get_text(separator="\n", strip=True)
        dados["biografia_completa"] = texto_completo

        secoes = re.split(r'\n(Formação Educacional|Atividade Profissional|Mandato Eletivo|Condecorações|Obras)\n', texto_completo)
        secao_atual = "geral"
        buffer: Dict[str, list] = {"geral": []}
        for parte in secoes:
            if parte in ["Formação Educacional", "Atividade Profissional", "Mandato Eletivo", "Condecorações", "Obras"]:
                secao_atual = parte
                buffer[secao_atual] = []
            else:
                buffer.setdefault(secao_atual, []).append(parte.strip())

        dados["formacao"] = "\n".join(buffer.get("Formação Educacional", [])).strip() or None
        dados["atividade_profissional"] = "\n".join(buffer.get("Atividade Profissional", [])).strip() or None
        mandatos_txt = "\n".join(buffer.get("Mandato Eletivo", [])).strip()
        if mandatos_txt:
            dados["mandatos"] = [m.strip() for m in mandatos_txt.split("\n") if m.strip()]

    # ── FIX 1: Email (tenta mailto, depois regex fallback) ────────────
    email_link = soup.select_one("a[href^='mailto:']")
    if email_link:
        dados["contatos"]["email"] = email_link["href"].replace("mailto:", "").strip()
    
    if not dados["contatos"]["email"] and dados.get("biografia_completa"):
        match = re.search(r'[\w\.\-]+@(?:alba\.ba\.gov\.br|[a-z]{2,}\.gov\.br)', dados["biografia_completa"])
        if match:
            dados["contatos"]["email"] = match.group(0).strip()

    # ── FIX 2: Telefones (extrai do texto da bio) ─────────────────────
    if dados.get("biografia_completa"):
        fones = re.findall(r'\b3\d{3}-\d{4}\b', dados["biografia_completa"])
        dados["contatos"]["telefones"] = list(dict.fromkeys(fones))

    # ── FIX 3: Endereço do Gabinete ───────────────────────────────────
    dados["gabinete_endereco"] = None
    if dados.get("biografia_completa"):
        match = re.search(
            r'(Prédio\s+\w+,\s*gab\.\s*[\d]+,\s*[\w\s]+(?:Lins|Ribeiro|Costa|Filho))',
            dados["biografia_completa"],
            re.IGNORECASE
        )
        if match:
            dados["gabinete_endereco"] = match.group(1).strip()

    return dados

def scrape_lista() -> List[Dict]:

    """Extrai lista de deputados com Nome, Partido e URL do perfil."""
    print(f"📡 Acessando lista: {URL_LISTA}")
    soup = get_soup(URL_LISTA)
    if not soup:
        return []

    perfis = []
    # Seletores identificados via inspeção real do HTML do portal ALBA:
    # Card raiz: div.col-md-3 que contenha .campo-dados
    # Nome: .deputado-nome a span
    # Partido: .partido-nome (texto solto)
    cards = [c for c in soup.select(".col-md-3") if c.select_one(".campo-dados")]
    print(f"   ✅ Cards de deputados encontrados: {len(cards)}")

    for card in cards:
        # Nome
        nome_tag = card.select_one(".deputado-nome a span")
        if not nome_tag:
            nome_tag = card.select_one(".deputado-nome a")
        if not nome_tag:
            continue
        nome = nome_tag.get_text(strip=True)

        # URL do perfil
        link_tag = card.select_one(".deputado-nome a")
        if not link_tag:
            continue
        href = link_tag.get("href", "")
        url = BASE_URL + href if href.startswith("/") else href

        # Partido
        partido_tag = card.select_one(".partido-nome")
        partido = partido_tag.get_text(strip=True) if partido_tag else "N/D"
        partido = re.sub(r'\s+', ' ', partido).strip()  # normaliza espaços

        if nome and url:
            perfis.append({"nome": nome, "url": url, "partido": partido})

    if not perfis:
        # Fallback: links diretos (caso o HTML mude)
        print("   ⚠️ Fallback: buscando links diretos de deputado-estadual...")
        for a in soup.select("a[href*='/deputados/deputado-estadual/']"):
            nome = a.get_text(strip=True)
            if nome and len(nome) > 3:
                url = BASE_URL + a["href"] if a["href"].startswith("/") else a["href"]
                perfis.append({"nome": nome, "url": url, "partido": "N/D"})

    # ── Captura bloco Observações (suplentes/substituições) ─────────────
    # O bloco "Observações" fica no rodapé da listagem com parágrafos
    # tipo: "Nome do Deputado\nAssumiu o mandato..."
    mapa_observacoes: Dict[str, str] = {}
    obs_header = soup.find(lambda t: t.name in ["h2","h3","h4","b","strong","p"] 
                           and t.get_text(strip=True).lower() in ["observações", "observacoes"])
    if obs_header:
        bloco = obs_header.find_next_sibling()
        while bloco:
            txt = bloco.get_text(separator="\n", strip=True)
            # Cada observação começa com o nome do parlamentar em uma linha isolada
            linhas = [l.strip() for l in txt.split("\n") if l.strip()]
            if len(linhas) >= 2:
                nome_obs = linhas[0]
                texto_obs = " ".join(linhas[1:])
                mapa_observacoes[nome_obs.lower()] = texto_obs
            bloco = bloco.find_next_sibling()
            if not bloco or bloco.get_text(strip=True).lower().startswith("atualização"):
                break

    # Associa as observações aos parlamentares pelo nome
    for p in perfis:
        p["observacao_mandato"] = mapa_observacoes.get(p["nome"].lower(), None)

    print(f"   📋 {len(perfis)} parlamentares detectados. | Obs. capturadas: {len(mapa_observacoes)}")
    return perfis



def dump_checkpoint(dados: list, out_dir: Path):
    """Salva checkpoint de progresso."""
    cp = out_dir / "_checkpoint_zidane.json"
    with open(cp, "w", encoding="utf-8") as f:
        json.dump({"total": len(dados), "registros": dados}, f, ensure_ascii=False, indent=2)


def run(limit: int = 0):
    print_header(f"ZIDANE-B {VERSAO} | HUB PARLAMENTAR PRISMA")
    print_status("Iniciando varredura profunda de perfis...", "process")

    base_dir = Path("/home/carneiro888/CARNEIRO888/N888N - AGENTIC EXTRATORES/n888n")
    out_dir = base_dir / "data" / "saida" / "parlamentares" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_a_path = out_dir / "parlamentares_ids.json"
    fotos_map = {}
    if checkpoint_a_path.exists():
        with open(checkpoint_a_path, "r", encoding="utf-8") as f:
            data_a = json.load(f)
            for rec in data_a.get("records", []):
                fotos_map[rec["parlamentar_id"]] = rec.get("foto_url")

    lista = scrape_lista()
    if not lista:
        print("💀 Falha crítica: nenhum deputado detectado.")
        return

    alvos = lista[:limit] if limit > 0 else lista
    print(f"\n🚀 Processando {len(alvos)} de {len(lista)} parlamentares...\n")

    todos = []
    for i, item in enumerate(alvos):
        nome_raw = item["nome"]
        url = item["url"]
        partido = item["partido"]
        p_id = url.rstrip("/").split("/")[-1]

        foto_do_a = fotos_map.get(p_id)

        # Normalização Prata
        nome_limpo = nome_raw.title().strip()
        sigla_partido = re.sub(r'[^A-Z]', '', partido.upper())[:10]

        prisma_id = gerar_prisma_id(nome_raw, partido, url)
        processado_em = datetime.utcnow().isoformat() + "Z"

        label = f"[{i+1:02d}/{len(alvos)}] {nome_limpo}"
        print(f"{C_BOLD}👤 {label:<45} {C_END}{C_CYAN}|{C_END} {C_YELLOW}🚩 {sigla_partido:<10} {C_END}{C_CYAN}|{C_END} {C_PURPLE}🔑 {prisma_id[:8]}...{C_END}")

        # Deep Scrape
        bio = scrape_perfil(url)

        record = {
            # ── Identidade ──────────────────────────────────────
            "prisma_id": prisma_id,
            "parlamentar_id": p_id,
            "nome_eleitoral": nome_raw,
            "nome_limpo": nome_limpo,
            "partido": partido,
            "sigla_partido": sigla_partido,
            "url_oficial": url,
            "foto_url": foto_do_a or bio.get("foto_url"),
            # ── Dados Biográficos ────────────────────────────────
            "biografia_completa": bio.get("biografia_completa"),
            "dados_pessoais": bio.get("dados_pessoais"),
            "mandatos": bio.get("mandatos"),
            "contatos": bio.get("contatos"),
            "gabinete_endereco": bio.get("gabinete_endereco"),
            # ── Metadados PRISMA ─────────────────────────────────
            "fonte_portal": "al_ba_gov_br",
            "fonte_url": url,
            "versao_zidane": VERSAO,
            "qualidade_score": 0.98 if bio.get("biografia_completa") else 0.60,
            "processado_em": processado_em,
        }

        todos.append(record)

        # Salva arquivo individual
        filename = out_dir / f"parlamentar_{p_id}_oficial.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        # Checkpoint a cada 10
        if (i + 1) % 10 == 0:
            dump_checkpoint(todos, out_dir)
            print(f"  💾 Checkpoint salvo ({i+1} deputados).")

        time.sleep(0.8)

    # Checkpoint final
    dump_checkpoint(todos, out_dir)
    
    print(f"\n{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}")
    print_status(f"CONCLUÍDO! {C_BOLD}{len(todos)}{C_END} perfis extraídos com metadados PRISMA.", "success")
    print_status(f"Datalake: {C_WHITE}{out_dir}{C_END}", "info")
    print(f"{C_PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_END}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Limita nº de parlamentares (0=todos)")
    args = parser.parse_args()
    run(limit=args.limit)

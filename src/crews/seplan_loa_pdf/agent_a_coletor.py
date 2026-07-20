#!/usr/bin/env python3
"""
SEPLAN LOA — Agent A (Coletor)

Fonte: PDFs oficiais da Lei Orçamentária Anual (LOA) da Bahia, "Quadro I -
Emendas Parlamentares Individuais por Autor e Área Temática" — publicados em
ba.gov.br/seplan (ano corrente) e no histórico de LOAs (anos anteriores).

Recon 2026-07-20: PDF com texto extraível (não é imagem escaneada), padrão
estável 2023-2026: cada seção começa com "NOME DO DEPUTADO - CÓDIGO" (código
interno da SEPLAN, não é autor_id da ALBA nem CPF — resolvido por nome no
Agent B) seguida das emendas dele: nº da emenda, órgão, ação, descrição,
município, valor autorizado.

IMPORTANTE (decisão do usuário 2026-07-20): este dado é a AUTORIZAÇÃO
orçamentária, não a execução/pagamento. O nº da emenda daqui NÃO bate com o
`numero_emenda` de `emendas_estaduais` (que, na verdade, é nº de PAGAMENTO do
CKAN — achado do recon, tabela mal nomeada). Não existe cruzamento automático
seguro entre os dois hoje — carregamos como registro PRÓPRIO e independente.

Bronze: data/seplan_loa_pdf/bronze/loa_{ano}.pdf
"""
import re
import time
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "seplan_loa_pdf"
BRONZE = DATA_DIR / "bronze"
BRONZE.mkdir(parents=True, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PRISMA888/1.0 (dados abertos SEPLAN-BA)"
HEADERS = {"User-Agent": UA}

PAGINAS_FONTE = [
    "https://www.ba.gov.br/seplan/orcamento/orcamento-anual",
    "https://www.ba.gov.br/seplan/orcamento/historico-de-loa/",
]

RE_ANEXO_I = re.compile(r'href="([^"]*LOA[^"]*Anexo-I-Emendas[^"]*\.pdf)"', re.IGNORECASE)
RE_ANO = re.compile(r'LOA[-_](\d{4})', re.IGNORECASE)


def log(msg: str) -> None:
    from datetime import datetime
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def descobrir_urls() -> dict[str, str]:
    """ano -> url do PDF 'Anexo I - Emendas por Autor' daquele ano."""
    achados: dict[str, str] = {}
    for pagina in PAGINAS_FONTE:
        try:
            r = requests.get(pagina, headers=HEADERS, timeout=30, verify=False)
            r.raise_for_status()
        except Exception as e:
            log(f"  ⚠️ falha ao ler {pagina}: {e}")
            continue
        for href in RE_ANEXO_I.findall(r.text):
            m_ano = RE_ANO.search(href)
            if not m_ano:
                continue
            ano = m_ano.group(1)
            url = href if href.startswith("http") else f"https://www.ba.gov.br{href}"
            # se já achou esse ano numa página anterior, mantém a 1ª (orçamento-anual tem prioridade)
            achados.setdefault(ano, url)
    return achados


def baixar(ano: str, url: str, force: bool) -> bool:
    destino = BRONZE / f"loa_{ano}.pdf"
    if destino.exists() and not force:
        log(f"  loa_{ano}.pdf já existe (--force pra rebaixar)")
        return False
    try:
        r = requests.get(url, headers=HEADERS, timeout=60, verify=False)
        r.raise_for_status()
    except Exception as e:
        log(f"  ❌ {ano}: falha no download ({e})")
        return False
    destino.write_bytes(r.content)
    log(f"  ✅ {ano}: {len(r.content):,} bytes → {destino.name}")
    return True


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="SEPLAN LOA — Coletor dos PDFs 'Emendas por Autor'")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    urls = descobrir_urls()
    log(f"📊 {len(urls)} ano(s) de LOA encontrados com Anexo I: {sorted(urls.keys())}")
    for ano, url in sorted(urls.items()):
        baixar(ano, url, args.force)
        time.sleep(0.5)


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    main()

#!/usr/bin/env python3
"""Agent A — Coletor Sorocaba Verba de Gabinete: Portal municipal → Bronze

Portal: camarasorocaba.sp.gov.br/arquivos_publicos.html — pasta pública
"Prestação de Contas - Vereadores". Estrutura em árvore, HTML server-side
renderizado (SEM necessidade de JS/browser — confirmado via curl com headers
realistas de navegador em 26/07/2026; um fetch ingênuo sem esses headers
pode retornar uma casca genérica sem os links, então HEADERS abaixo não é
cosmético, é requisito):

    /arquivos_publicos.html?id=<id_pasta_raiz>   -> linhas de PASTAS (1 por
                                                     ano), <span class=
                                                     "glyphicon-folder-open">
    /arquivos_publicos.html?id=<id_pasta_ano>    -> linhas de ARQUIVOS (1 por
                                                     mês), <span class=
                                                     "glyphicon-open">, href
                                                     aponta direto pro arquivo
                                                     final em
                                                     https://...:3115/publicFiles/file/<id>

Cada mês é 1 ARQUIVO ÚNICO consolidado (não 1 por vereador): tabela
"Despesas dos Gabinetes dos Senhores Vereadores" com 1 linha por vereador ×
4 categorias (Aluguel de Máquina Reprográfica, Combustível, Material de
Escritório, Postagem) + Total + Reembolso. SEM CNPJ/fornecedor — fonte bem
mais agregada que camara_sp_verba_gabinete (SP capital), que tem nota fiscal
item a item. Reembolso fica FORA de escopo do v1 (é dinheiro devolvido pelo
vereador, não despesa — mesmo princípio de escopo do crew de SP capital, que
também deixou crédito/reembolso de fora).

Formato do arquivo varia por época (confirmado nas duas pontas do histórico,
26/07/2026):
  - Anos mais antigos (ex.: 2016): a extensão do link sugere um formato, mas
    o conteúdo real é um Excel exportado como HTML ("Content-Type:
    Excel.Sheet" no <meta> do próprio HTML).
  - Anos recentes (ex.: 2025): PDF de texto real, extraível via pdfplumber
    (tabela com grade, não é imagem escaneada).
Detecção é SEMPRE por magic bytes (%PDF no início do arquivo baixado), nunca
pela extensão do link ou pelo header Content-Type do servidor (que mente).

Cobertura confirmada por navegação real: pasta raiz tem 11 pastas-ano
(2016→2026), cada ano com até 12 arquivos-mês. Ano corrente pode ter menos
de 12 (meses futuros não publicados ainda).

Execução:
    python agent_a_coletor.py                # descobre tudo, baixa o que faltar
    python agent_a_coletor.py --force         # rebaixa tudo

Saída:
    data/sorocaba_verba_gabinete/bronze/<ano>-<mes:02d>.raw   (arquivo cru)
    data/sorocaba_verba_gabinete/bronze/sorocaba_verba_bronze_index.json
"""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data/sorocaba_verba_gabinete"
BRONZE_DIR = DATA_DIR / "bronze"
BRONZE_DIR.mkdir(parents=True, exist_ok=True)

PORTAL_BASE = "https://www.camarasorocaba.sp.gov.br"
ARQUIVOS_PUBLICOS_URL = f"{PORTAL_BASE}/arquivos_publicos.html"
PASTA_RAIZ_ID = "5e3f0dc905d7040f28b44e0e"  # "Prestação de Contas - Vereadores"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
HEADERS_HTML = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": ARQUIVOS_PUBLICOS_URL,
}
HEADERS_FILE = {"User-Agent": UA, "Referer": ARQUIVOS_PUBLICOS_URL}

RE_PASTA = re.compile(
    r'<a href="\?id=([a-f0-9]+)">\s*'
    r'<span class="glyphicon glyphicon-folder-open"[^>]*></span>\s*&nbsp;\s*'
    r'([^<]+?)\s*</a>'
)
RE_ARQUIVO = re.compile(
    r'<a href="(https://www\.camarasorocaba\.sp\.gov\.br:3115/publicFiles/file/[a-f0-9]+)"[^>]*>\s*'
    r'<span class="glyphicon glyphicon-open"[^>]*></span>\s*&nbsp;\s*'
    r'([^<]+?)\s*</a>'
)

MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}

INDEX_PATH = BRONZE_DIR / "sorocaba_verba_bronze_index.json"


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _get_html(id_pasta: str) -> str:
    resp = requests.get(ARQUIVOS_PUBLICOS_URL, params={"id": id_pasta}, headers=HEADERS_HTML, timeout=30)
    resp.raise_for_status()
    return resp.text


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
def _get_arquivo(url: str) -> bytes:
    resp = requests.get(url, headers=HEADERS_FILE, timeout=60)
    resp.raise_for_status()
    return resp.content


def descobrir_anos() -> list[tuple[str, str]]:
    """[(id_pasta_ano, ano_texto), ...] a partir da pasta raiz."""
    html = _get_html(PASTA_RAIZ_ID)
    anos = RE_PASTA.findall(html)
    return anos


def descobrir_meses(id_pasta_ano: str) -> list[tuple[str, str, str]]:
    """[(url_arquivo, mes_texto, file_id), ...] dentro de uma pasta-ano."""
    html = _get_html(id_pasta_ano)
    achados = []
    for url, mes_texto in RE_ARQUIVO.findall(html):
        file_id = url.rsplit("/", 1)[-1]
        achados.append((url, mes_texto.strip(), file_id))
    return achados


def detectar_formato(conteudo: bytes) -> str:
    if conteudo[:4] == b"%PDF":
        return "pdf"
    if conteudo[:6].lower() in (b"<html>", b"<!doct") or b"<html" in conteudo[:200].lower():
        return "excel_html"
    return "desconhecido"


def main():
    parser = argparse.ArgumentParser(description="Agent A — Coletor Sorocaba Verba de Gabinete")
    parser.add_argument("--force", action="store_true", help="Rebaixa mesmo se já existe")
    args = parser.parse_args()

    log("🔎 Descobrindo pastas-ano na raiz 'Prestação de Contas - Vereadores'...")
    anos = descobrir_anos()
    if not anos:
        log("❌ Nenhuma pasta-ano encontrada — layout do portal pode ter mudado, parando (não adivinhar).")
        return
    log(f"📂 {len(anos)} pasta(s)-ano encontrada(s): {sorted(a[1] for a in anos)}")

    index: list[dict] = []
    baixados = pulados = erros = 0

    for id_pasta_ano, ano_texto in sorted(anos, key=lambda x: x[1]):
        try:
            ano = int(ano_texto.strip())
        except ValueError:
            log(f"  ⚠️  pasta com nome de ano inválido, pulando: {ano_texto!r}")
            continue

        try:
            meses = descobrir_meses(id_pasta_ano)
        except Exception as e:
            log(f"  ❌ {ano}: falha ao listar meses ({e})")
            erros += 1
            continue

        log(f"  📅 {ano}: {len(meses)} mês(es) publicado(s)")
        for url, mes_texto, file_id in meses:
            mes_norm = mes_texto.strip().lower()
            mes = MESES.get(mes_norm)
            if mes is None:
                log(f"    ⚠️  mês não reconhecido: {mes_texto!r} ({url}) — pulando, não adivinhar")
                continue

            competencia = f"{ano:04d}-{mes:02d}"
            destino = BRONZE_DIR / f"{competencia}.raw"

            if destino.exists() and not args.force:
                pulados += 1
                conteudo = destino.read_bytes()
                formato = detectar_formato(conteudo)
            else:
                try:
                    conteudo = _get_arquivo(url)
                except Exception as e:
                    log(f"    ❌ {competencia}: falha no download ({e})")
                    erros += 1
                    continue
                destino.write_bytes(conteudo)
                formato = detectar_formato(conteudo)
                baixados += 1
                log(f"    ✅ {competencia}: {len(conteudo):,} bytes ({formato}) → {destino.name}")
                time.sleep(0.3)  # gentil com o servidor da fonte

            if formato == "desconhecido":
                log(f"    ⚠️  {competencia}: formato não reconhecido (nem PDF nem Excel-HTML) — mantendo no bronze, Agent B vai rejeitar")

            index.append({
                "ano": ano,
                "mes": mes,
                "competencia": competencia,
                "file_id": file_id,
                "url_fonte": url,
                "arquivo_bronze": destino.name,
                "formato": formato,
                "hash_sha256": hashlib.sha256(conteudo).hexdigest(),
                "tamanho_bytes": len(conteudo),
            })

    if not index:
        log("❌ Nenhum arquivo coletado")
        return

    payload = {
        "meta": {
            "portal": "Câmara Municipal de Sorocaba — Arquivos Públicos / Prestação de Contas - Vereadores",
            "entidade": "sorocaba_verba_gabinete",
            "camada": "bronze",
            "data_extracao": datetime.now(timezone.utc).isoformat(),
            "url_raiz": f"{ARQUIVOS_PUBLICOS_URL}?id={PASTA_RAIZ_ID}",
            "total_competencias": len(index),
            "baixados_agora": baixados,
            "pulados_ja_existentes": pulados,
            "erros": erros,
        },
        "arquivos": index,
    }
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    log(f"\n✅ Bronze: {len(index):,} competência(s) → {INDEX_PATH.name}")
    log(f"   Baixados agora: {baixados} | já existiam: {pulados} | erros: {erros}")
    log("\n✅ Agent A concluído.")


if __name__ == "__main__":
    main()

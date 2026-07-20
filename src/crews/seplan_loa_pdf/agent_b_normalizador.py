#!/usr/bin/env python3
"""
SEPLAN LOA — Agent B (Normalizador)

Bronze (PDF) → Prata (emendas de autorização orçamentária estruturadas).

Extração POSICIONAL via pdfplumber (não regex sobre texto corrido — o PDF é
uma tabela sem grade, texto alinhado por coordenada X). Colunas descobertas
no recon 2026-07-20 (x0 em pontos):
  Nº Emenda [0,65) · Órgão [65,130) · Unidade Orç. [130,210) · Ação [210,270)
  Descritor [270,470) · Objeto [470,650) · Município [650,745) · Valor [745,∞)

Cada seção do documento começa com uma linha "NOME - CÓDIGO VALOR_TOTAL"
(código interno SEPLAN, não é autor_id ALBA — resolvido por nome contra
`alba_parlamentares.nome_parlamentar`, mesma técnica do crew doe_ba).
Município puro tem 1 linha; nomes longos podem vir com continuação —
concatenamos qualquer fragmento na coluna Município nas linhas seguintes até
a próxima emenda.

Linhas de cabeçalho repetido (a cada nova página) e de subtotal ("Total da
Área de...") são descartadas — nunca tratadas como dado.
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "seplan_loa_pdf"
BRONZE = DATA_DIR / "bronze"
PRATA = DATA_DIR / "prata"
PRATA.mkdir(parents=True, exist_ok=True)

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido")
DB = dict(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", 5432)),
          dbname=os.getenv("DB_NAME", "prisma_data"), user=os.getenv("DB_USER", "postgres"),
          password=DB_PASSWORD)

COLS = [
    ("emenda", 0, 65), ("orgao", 65, 130), ("unidade", 130, 210),
    ("acao", 210, 270), ("descritor", 270, 470), ("objeto", 470, 650),
    ("municipio", 650, 745), ("valor", 745, 900),
]
RE_AUTOR = re.compile(r'^([A-ZÀ-Úa-zà-ú][A-ZÀ-Úa-zà-ú .\'-]+?)\s*-\s*(\d{5,7})\b')
HEADER_MARKERS = ("Unidade Orçamentária", "Descritor da", "Objeto da Emenda", "Governo do Estado", "Lei Orçamentária", "Quadro I")


def log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _col_for(x0: float) -> str:
    for name, lo, hi in COLS:
        if lo <= x0 < hi:
            return name
    return "valor"


def _valor_para_centavos(txt: str) -> int | None:
    """'350.000' (colunas 'em R$1,00') -> 35000000 centavos. Nunca estima."""
    digitos = re.sub(r'[^\d]', '', txt or "")
    if not digitos:
        return None
    return int(digitos) * 100


def extrair_pdf(caminho: Path) -> list[dict]:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber ausente — necessário pra extrair a LOA")
    rows: list[dict] = []
    autor_atual, atual = None, None
    with pdfplumber.open(str(caminho)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            linhas_raw: dict[int, list] = {}
            linhas_col: dict[int, dict[str, list]] = {}
            for w in words:
                top = round(w["top"])
                linhas_raw.setdefault(top, []).append((w["x0"], w["text"]))
                linhas_col.setdefault(top, {}).setdefault(_col_for(w["x0"]), []).append(w["text"])
            for top in sorted(linhas_raw.keys()):
                texto = " ".join(t for _, t in sorted(linhas_raw[top]))
                if any(h in texto for h in HEADER_MARKERS):
                    continue
                primeiro_x0 = min(x for x, _ in linhas_raw[top])
                # cabeçalho "NOME - CÓDIGO" só ocorre encostado na margem
                # esquerda (mesma coluna do nº da emenda); um " - NNNNN" no
                # meio de texto de descrição (ex. "CNES - 4021460") aparece
                # bem mais à direita — sem esse filtro, casava como autor.
                m_autor = RE_AUTOR.match(texto.strip()) if primeiro_x0 < 45 else None
                if m_autor:
                    autor_atual = (m_autor.group(1).strip(), m_autor.group(2))
                    continue
                if texto.strip().startswith("Total d"):
                    continue
                l = linhas_col[top]
                emenda_txt = " ".join(l.get("emenda", []))
                municipio_frag = " ".join(l.get("municipio", []))
                if emenda_txt.strip().isdigit():
                    if atual:
                        rows.append(atual)
                    atual = {
                        "autor_nome": autor_atual[0] if autor_atual else None,
                        "autor_codigo_seplan": autor_atual[1] if autor_atual else None,
                        "numero_emenda_loa": emenda_txt.strip(),
                        "municipio_nome": municipio_frag.strip(),
                        "valor_centavos": _valor_para_centavos(" ".join(l.get("valor", []))),
                    }
                elif atual and municipio_frag.strip():
                    atual["municipio_nome"] += " " + municipio_frag.strip()
    if atual:
        rows.append(atual)
    return rows


def carregar_mapas(cur):
    cur.execute("SELECT nome_parlamentar, politico_id FROM alba_parlamentares WHERE politico_id IS NOT NULL")
    por_nome = {}
    for r in cur.fetchall():
        nome = r["nome_parlamentar"] or ""
        for pref in ("Deputado ", "Deputada "):
            if nome.startswith(pref):
                nome = nome[len(pref):]
                break
        por_nome[nome.strip().lower()] = r["politico_id"]

    cur.execute("SELECT id_ibge, nome FROM municipios WHERE uf = 'BA'")
    por_municipio = {r["nome"].strip().lower(): r["id_ibge"] for r in cur.fetchall()}
    return por_nome, por_municipio


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ano", default=None, help="processa só um ano (ex.: 2026); default = todos os PDFs em bronze")
    args = ap.parse_args()

    conn = psycopg2.connect(**DB)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    por_nome, por_municipio = carregar_mapas(cur)
    log(f"mapas: {len(por_nome)} deputados (nome→politico_id), {len(por_municipio)} municípios BA")
    conn.close()

    pdfs = sorted(BRONZE.glob(f"loa_{args.ano}.pdf" if args.ano else "loa_*.pdf"))
    log(f"processando {len(pdfs)} PDF(s): {[p.name for p in pdfs]}")

    saida, sem_politico, sem_municipio = [], 0, 0
    for pdf_path in pdfs:
        m_ano = re.search(r'loa_(\d{4})', pdf_path.stem)
        ano = int(m_ano.group(1)) if m_ano else None
        linhas = extrair_pdf(pdf_path)
        log(f"  {pdf_path.name}: {len(linhas)} linhas extraídas")
        for r in linhas:
            nome_norm = (r["autor_nome"] or "").strip().lower()
            politico_id = por_nome.get(nome_norm)
            if not politico_id:
                sem_politico += 1
            mun_norm = (r["municipio_nome"] or "").strip().lower()
            municipio_ibge = por_municipio.get(mun_norm)
            if not municipio_ibge:
                sem_municipio += 1
            saida.append({
                "numero_emenda": f"LOA{ano}-{r['numero_emenda_loa']}",
                "politico_id": politico_id,
                "autor_nome_bruto": r["autor_nome"],
                "municipio_ibge": municipio_ibge,
                "municipio_nome_bruto": r["municipio_nome"],
                "valor_aprovado": (r["valor_centavos"] / 100) if r["valor_centavos"] is not None else None,
                "ano_loa": ano,
            })

    (PRATA / "loa.json").write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
    log(f"✅ prata: {len(saida):,} emendas de autorização orçamentária "
        f"({sem_politico:,} sem politico_id resolvido, {sem_municipio:,} sem municipio_ibge resolvido)")


if __name__ == "__main__":
    main()

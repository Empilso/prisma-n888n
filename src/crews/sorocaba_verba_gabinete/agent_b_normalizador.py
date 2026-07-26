#!/usr/bin/env python3
"""Agent B — Normalizador Sorocaba Verba de Gabinete: Bronze → Prata

Parseia cada arquivo bronze (PDF ou Excel-HTML, ver detecção em Agent A) e
extrai a tabela "Despesas dos Gabinetes dos Senhores Vereadores": 1 linha
por vereador, colunas de categoria de despesa + TOTAL (+ REEMBOLSO em anos
mais recentes, fora de escopo do v1).

Categorias mapeadas (nomes de coluna variam um pouco entre épocas, ex.:
"ALUGUEL DE MÁQUINA REPROGRÁFICA" com ou sem quebra de linha — normalização
por prefixo, nunca por igualdade exata de string):
  aluguel_maquina_reprografica | combustivel | material_escritorio | postagem

id (PK) = SHA256(vereador_nome|competencia|categoria)[:32]

Cross-check de qualidade (não bloqueia carga, só loga aviso): soma das 4
categorias por vereador deveria bater com a coluna TOTAL publicada — quando
não bate, o registro ainda é carregado (a fonte é a autoridade), mas o
desvio fica registrado em `_delta_total` no prata para auditoria futura.

Fuzzy match contra politicos (município=Sorocaba, cargo=VEREADOR) — mesma
técnica do crew camara_sp_verba_gabinete (rapidfuzz, threshold 80%), MAS
contra `nome_completo` (nome civil), não `nome_urna` (apelido de campanha).
Achado real ao testar com amostra: a Câmara de Sorocaba publica nome civil
completo neste documento ("ANTÔNIO CARLOS SILVANO JÚNIOR"), enquanto
nome_urna é o apelido de campanha ("Silvano Jr", "Tonão Silvano") — quase
sempre irreconhecível por fuzzy contra o nome civil. Confirmado no banco:
nome_completo="Antonio Carlos Silvano Junior" bate exato (100% cobertura de
nome_completo entre os 2.296 registros de vereador de Sorocaba com
politico_id). Primeiro teste local usando nome_urna deu 4,9% de match;
trocando pra nome_completo isso precisa ser revalidado antes de rodar de
verdade — ver nota no manifest.

Rejeições:
  - Linha sem nome de vereador reconhecível (cabeçalho/rodapé/total geral)
  - Valor de categoria vazio ou <= 0 (não gera linha — célula "-" é
    ausência de gasto naquela categoria, não um registro de valor zero)
  - Ano/mês fora de faixa plausível

Saída:
    data/sorocaba_verba_gabinete/prata/sorocaba_verba_prata.json
    data/sorocaba_verba_gabinete/rejeitados/sorocaba_verba_rejeitados.json
"""
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    from rapidfuzz import process, fuzz
    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data/sorocaba_verba_gabinete"
BRONZE_DIR = DATA_DIR / "bronze"
PRATA_DIR = DATA_DIR / "prata"
REJEIT_DIR = DATA_DIR / "rejeitados"
for d in (PRATA_DIR, REJEIT_DIR):
    d.mkdir(parents=True, exist_ok=True)

INDEX_PATH = BRONZE_DIR / "sorocaba_verba_bronze_index.json"
PRATA_PATH = PRATA_DIR / "sorocaba_verba_prata.json"
REJEIT_PATH = REJEIT_DIR / "sorocaba_verba_rejeitados.json"

DB = dict(host="localhost", port=5432, dbname="prisma_data", user="postgres", password=DB_PASSWORD)
MUNICIPIO_IBGE_SOROCABA = "3552205"

# Prefixo (já normalizado: upper, sem acento, sem quebra de linha) -> categoria canônica.
# NUNCA usar igualdade exata — os nomes de coluna variam entre épocas (quebra de
# linha do PDF, "MAQUINA" vs "MÁQUINA" etc).
CATEGORIAS_PREFIXO = [
    ("ALUGUEL", "aluguel_maquina_reprografica"),
    ("COMBUSTIVEL", "combustivel"),
    ("MATERIAL DE ESCRITORIO", "material_escritorio"),
    ("MATERIAL ESCRITORIO", "material_escritorio"),
    ("POSTAGEM", "postagem"),
]
COLUNAS_IGNORADAS_PREFIXO = ("VEREADOR", "TOTAL", "REEMBOLSO")


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _strip_acentos(txt: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode("ascii")


def _normalizar_header(txt: str) -> str:
    s = _strip_acentos(txt)
    return re.sub(r"\s+", " ", s).strip().upper()


def _normalizar_nome(txt: str) -> str:
    """Upper + sem acento. Achado real testando amostra: nome_completo no
    banco vem sem acento ('Antonio Carlos Silvano Junior'), mas o documento
    da Câmara vem acentuado ('ANTÔNIO CARLOS SILVANO JÚNIOR') — comparação
    sem normalizar acento perdia ~15% dos matches mesmo sendo o MESMO nome."""
    s = _strip_acentos(txt)
    return re.sub(r"\s+", " ", s).strip().upper()


def parse_valor_br(txt: str) -> Decimal | None:
    """'1.362,97' -> Decimal('1362.97'). '-' ou vazio -> None (ausência, não zero)."""
    if txt is None:
        return None
    s = re.sub(r"\s+", "", str(txt)).strip()
    if not s or s == "-":
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        d = Decimal(s)
        return d if d > 0 else None
    except InvalidOperation:
        return None


def _mapear_categoria(header: str) -> str | None:
    h = _normalizar_header(header)
    for prefixo, categoria in CATEGORIAS_PREFIXO:
        if h.startswith(prefixo):
            return categoria
    return None


def _eh_linha_ignoravel(nome: str) -> bool:
    n = _normalizar_header(nome)
    if not n:
        return True
    return any(n.startswith(p) for p in COLUNAS_IGNORADAS_PREFIXO) or n in ("", "-")


def extrair_tabela_pdf(caminho: Path) -> tuple[list[str], list[list[str]]] | None:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber não instalado")
    with pdfplumber.open(caminho) as pdf:
        for page in pdf.pages:
            tabelas = page.extract_tables()
            for t in tabelas:
                # a linha de header tem "VEREADORES" na 1ª célula
                for i, row in enumerate(t):
                    if row and row[0] and _normalizar_header(row[0]).startswith("VEREADOR"):
                        header = [_normalizar_header((c or "").replace("\n", " ")) for c in row]
                        dados = t[i + 1:]
                        return header, dados
    return None


def extrair_tabela_excel_html(caminho: Path) -> tuple[list[str], list[list[str]]] | None:
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 não instalado")
    conteudo = caminho.read_bytes()
    for encoding in ("windows-1252", "utf-8", "latin-1"):
        try:
            html = conteudo.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        return None
    soup = BeautifulSoup(html, "lxml")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for i, row in enumerate(rows):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if cells and _normalizar_header(cells[0]).startswith("VEREADOR"):
                header = [_normalizar_header(c) for c in cells]
                dados_rows = rows[i + 1:]
                dados = [[c.get_text(" ", strip=True) for c in r.find_all(["td", "th"])] for r in dados_rows]
                return header, dados
    return None


def carregar_indice_vereadores() -> dict:
    try:
        conn = psycopg2.connect(**DB)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT ON (nome_completo) nome_completo, politico_id
            FROM politicos
            WHERE municipio_ibge = %s AND cargo = 'VEREADOR'
              AND politico_id IS NOT NULL AND nome_completo IS NOT NULL
            ORDER BY nome_completo, ano_eleicao DESC
            """,
            (MUNICIPIO_IBGE_SOROCABA,),
        )
        idx = {_normalizar_nome(r[0]): r[1] for r in cur.fetchall()}
        cur.close()
        conn.close()
        log(f"🔗 Índice vereadores Sorocaba: {len(idx)} nomes")
        return idx
    except Exception as e:
        log(f"⚠️  Banco indisponível, politico_id será None: {e}")
        return {}


def resolver_politico_id(nome_vereador: str, idx: dict) -> tuple[str | None, str]:
    nome = _normalizar_nome(nome_vereador)
    if nome in idx:
        return idx[nome], "exact"
    if HAS_FUZZ and idx:
        match = process.extractOne(nome, list(idx.keys()), scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 80:
            return idx[match[0]], f"fuzzy:{match[1]}"
    return None, "sem_match"


def processar_arquivo(meta_arquivo: dict, idx: dict) -> tuple[list[dict], list[dict]]:
    caminho = BRONZE_DIR / meta_arquivo["arquivo_bronze"]
    ano, mes, competencia = meta_arquivo["ano"], meta_arquivo["mes"], meta_arquivo["competencia"]
    formato = meta_arquivo["formato"]

    if not (2000 <= ano <= 2030 and 1 <= mes <= 12):
        return [], [{"_motivo": f"ano/mes fora de faixa: {ano}/{mes}", **meta_arquivo}]

    try:
        if formato == "pdf":
            extraido = extrair_tabela_pdf(caminho)
        elif formato == "excel_html":
            extraido = extrair_tabela_excel_html(caminho)
        else:
            return [], [{"_motivo": f"formato desconhecido: {formato}", **meta_arquivo}]
    except Exception as e:
        return [], [{"_motivo": f"falha ao parsear ({e})", **meta_arquivo}]

    if not extraido:
        return [], [{"_motivo": "tabela 'VEREADORES' não encontrada no arquivo", **meta_arquivo}]

    header, dados = extraido
    col_categoria = {}
    for i, h in enumerate(header):
        if i == 0:
            continue
        cat = _mapear_categoria(h)
        if cat:
            col_categoria[i] = cat
    idx_total = next((i for i, h in enumerate(header) if h.startswith("TOTAL")), None)

    if not col_categoria:
        return [], [{"_motivo": f"nenhuma coluna de categoria reconhecida no header: {header}", **meta_arquivo}]

    validos, rejeitados = [], []
    for row in dados:
        if not row or not row[0]:
            continue
        vereador = re.sub(r"\s+", " ", row[0]).strip()
        if _eh_linha_ignoravel(vereador):
            continue

        soma_categorias = Decimal("0")
        linhas_vereador = []
        for i, categoria in col_categoria.items():
            if i >= len(row):
                continue
            valor = parse_valor_br(row[i])
            if valor is None:
                continue
            soma_categorias += valor
            chave = f"{vereador.upper()}|{competencia}|{categoria}"
            politico_id, metodo = resolver_politico_id(vereador, idx)
            linhas_vereador.append({
                "id": sha256(chave)[:32],
                "politico_id": politico_id,
                "vereador_nome": vereador,
                "categoria": categoria,
                "valor": str(valor),
                "mes": mes,
                "ano": ano,
                "competencia": competencia,
                "status_lneg": None,
                "fonte_arquivo": meta_arquivo["file_id"],
                "_match_metodo": metodo,
            })

        if not linhas_vereador:
            continue

        if idx_total is not None and idx_total < len(row):
            total_publicado = parse_valor_br(row[idx_total])
            if total_publicado is not None:
                delta = abs(soma_categorias - total_publicado)
                if delta > Decimal("0.05"):
                    for linha in linhas_vereador:
                        linha["_delta_total"] = str(delta)

        validos.extend(linhas_vereador)

    return validos, rejeitados


def main():
    parser = argparse.ArgumentParser(description="Agent B — Normalizador Sorocaba Verba de Gabinete")
    parser.add_argument("--index", default=str(INDEX_PATH))
    args = parser.parse_args()

    index_path = Path(args.index)
    if not index_path.exists():
        log(f"❌ Índice bronze não encontrado: {index_path}")
        return

    with open(index_path, encoding="utf-8") as f:
        bronze = json.load(f)
    arquivos = bronze.get("arquivos", [])
    log(f"📂 {len(arquivos)} arquivo(s) bronze a processar")

    log("🔗 Carregando índice de vereadores Sorocaba...")
    idx = carregar_indice_vereadores()

    todos_validos, todos_rejeitados = [], []
    com_delta = 0
    for meta_arquivo in arquivos:
        validos, rejeitados = processar_arquivo(meta_arquivo, idx)
        todos_validos.extend(validos)
        todos_rejeitados.extend(rejeitados)
        com_delta += sum(1 for v in validos if "_delta_total" in v)
        if rejeitados:
            log(f"  ⚠️  {meta_arquivo['competencia']}: {rejeitados[0]['_motivo']}")
        elif validos:
            log(f"  ✅ {meta_arquivo['competencia']}: {len(validos)} linha(s)")

    sem_pid = sum(1 for v in todos_validos if not v["politico_id"])

    with open(PRATA_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "meta": {
                    "data_processamento": datetime.now(timezone.utc).isoformat(),
                    "fonte_bronze": index_path.name,
                    "total_validos": len(todos_validos),
                    "total_rejeitados": len(todos_rejeitados),
                    "sem_politico_id": sem_pid,
                    "com_delta_total_suspeito": com_delta,
                },
                "records": todos_validos,
            },
            f,
            ensure_ascii=False,
        )

    if todos_rejeitados:
        with open(REJEIT_PATH, "w", encoding="utf-8") as f:
            json.dump(todos_rejeitados, f, ensure_ascii=False, indent=2)

    pct_pid = (len(todos_validos) - sem_pid) / max(len(todos_validos), 1) * 100
    log(f"\n✅ Prata: {len(todos_validos):>7,} válidos → {PRATA_PATH.name}")
    log(f"⚠️  Arquivos rejeitados/com erro: {len(todos_rejeitados)}")
    log(f"🔗 Com politico_id: {len(todos_validos) - sem_pid:,} ({pct_pid:.1f}%)")
    if com_delta:
        log(f"🔎 Linhas com soma≠total publicado (>R$0,05): {com_delta} — carregadas mesmo assim, fonte é autoridade")
    log("\n✅ Agent B concluído.")


if __name__ == "__main__":
    main()

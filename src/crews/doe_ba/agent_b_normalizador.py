#!/usr/bin/env python3
"""
DOE-BA — Agent B (Normalizador)

Bronze (JSON bruto da busca) → Prata (atos de pessoal estruturados).

Escopo desta etapa (decisão do usuário, 2026-07-20): só atos de NOMEAÇÃO /
DESIGNAÇÃO / EXONERAÇÃO / DISPENSA / PROMOÇÃO / CONCESSÃO / REVERSÃO /
RETIFICAÇÃO de cargo/função em texto no formato oficial da seção SRH da ALBA:

    "Nº. 12.693/2021 - Nomear RAISSA MARINHO BENVINDO, para a função
    comissionada de Secretário Parlamentar (Gab. Dep. Ângelo Almeida)
    Nível SP-18, a partir de 01/05/2021."

SEM heurística de nepotismo nesta etapa — `alerta_nepotismo` sempre grava
`false`. Fica pra uma fase futura, só em ambiente de teste (pedido explícito
do usuário 2026-07-20): comparar sobrenome do nomeado com sobrenome de
deputados é indício fraco (homônimo é comum), exige selo "não é prova de
parentesco" na UI antes de ligar em produção — ver protocolo de dado sensível.

Regra "zero tolerância a dado errado": só extrai o que casa no padrão
"VERBO NOME ... a partir de DATA." — nunca infere nome ou data ausente. Atos
fora desse padrão (portarias de licença, contratos, "autorizar mudança de
nível" sem nome direto) são ignorados nesta etapa, não é bug.
"""
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "doe_ba"
BRONZE = DATA_DIR / "bronze"
PRATA = DATA_DIR / "prata"
PRATA.mkdir(parents=True, exist_ok=True)

HEADER = re.compile(r'(?:ATO\s+)?N[ºO]\.?\s*([\d.]+)\s*/\s*(\d{4})\s*-\s*')
VERBO_NOME = re.compile(
    r'^(Nomear|Designar|Exonerar|Dispensar|Promover|Conceder|Reverter|Retificar)\s+'
    r'((?:[A-ZÀ-Ü][A-ZÀ-Ü\.\'\-]*\s*){2,10}?)\s*,?\s+'
    r'(?:para|do cargo|da fun[çc][ãa]o)\s+'
    r'(.+?),?\s*a partir de\s*(\d{2}/\d{2}/\d{4})\.'
)
GAB = re.compile(r'\(Gab\.?\s*Dep\.?\s*([^)]{3,60})\)')

TIPO_ATO = {
    "Nomear": "Nomeação",
    "Designar": "Designação",
    "Exonerar": "Exoneração",
    "Dispensar": "Dispensa",
    "Promover": "Promoção",
    "Conceder": "Concessão",
    "Reverter": "Reversão",
    "Retificar": "Retificação",
}

URL_VER_TMPL = 'https://www.doe.ba.gov.br/alba/ver/{diario_id}/{pagina}/%22%22'


def log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _data_iso(v) -> str | None:
    try:
        datetime.strptime(v, "%Y-%m-%d")
        return v
    except (TypeError, ValueError):
        return None


def _extrair_atos(fonte: dict) -> list[dict]:
    texto = fonte.get("conteudo") or ""
    data_pub = _data_iso(fonte.get("data"))
    diario_id = fonte.get("diario_id")
    pagina = fonte.get("pagina")
    if not data_pub or not diario_id:
        return []

    heads = list(HEADER.finditer(texto))
    saida = []
    for i, m in enumerate(heads):
        start = m.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else min(len(texto), start + 500)
        chunk = texto[start:end].strip()
        vm = VERBO_NOME.match(chunk)
        if not vm:
            continue
        verbo, nome, resto, data_ato = vm.groups()
        nome = " ".join(nome.split()).strip(" ,")
        if len(nome) < 5:
            continue  # nome curto demais pra ser confiável (evita capturar lixo de regex)
        gab = GAB.search(resto)
        ato_numero = m.group(1)
        ato_ano = int(m.group(2))
        tipo_ato = TIPO_ATO.get(verbo, verbo)
        orgao = f"Gabinete Dep. {gab.group(1).strip()}" if gab else None
        texto_resumido = f"{verbo} {nome}, para {resto.strip()}, a partir de {data_ato}."[:600]

        chave = f"{data_pub}|{ato_numero}|{ato_ano}|{nome}|{verbo}"
        ato_hash = hashlib.sha256(chave.encode("utf-8")).hexdigest()

        saida.append({
            "data_publicacao": data_pub,
            "tipo_ato": tipo_ato,
            "texto_resumido": texto_resumido,
            "cpf_cnpj_referencia": None,  # não presente neste padrão de texto — nunca inferir
            "nome_referencia": nome,
            "secao": "SRH",
            "orgao": orgao,
            "ato_numero": ato_numero,
            "ato_ano": ato_ano,
            "diario_id": str(diario_id),
            "pagina": int(pagina) if pagina is not None else None,
            "url_fonte": URL_VER_TMPL.format(diario_id=diario_id, pagina=pagina or 1),
            "ato_hash": ato_hash,
            "alerta_nepotismo": False,  # decisão 2026-07-20: MVP sem nepotismo
        })
    return saida


def main() -> None:
    arquivos = sorted(BRONZE.glob("page_*.json"))
    log(f"normalizando {len(arquivos)} páginas de resultado bronze")

    vistos, saida = set(), []
    total_paginas_diario = 0
    for arq in arquivos:
        payload = json.loads(arq.read_text(encoding="utf-8"))
        hits = ((payload.get("hits") or {}).get("hits")) or []
        for h in hits:
            total_paginas_diario += 1
            for ato in _extrair_atos(h.get("_source") or {}):
                if ato["ato_hash"] in vistos:
                    continue
                vistos.add(ato["ato_hash"])
                saida.append(ato)
        # páginas do diário sem nenhum ato extraído não são erro — a maioria do
        # conteúdo da seção SRH é licença/aposentadoria/contrato, fora do escopo

    (PRATA / "atos.json").write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
    log(f"✅ prata: {len(saida):,} atos de pessoal extraídos de {total_paginas_diario:,} páginas do diário lidas")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Agent A — Extrator ALMT/SIGCON Emendas Estaduais MT: HTML → Bronze JSON

Fonte: SIGCON (Sistema Gerenciamento de Convênios), Secretaria de Estado
da Fazenda de MT — https://transp.sigcon.seplan.mt.gov.br/index_.php
Achado via link "Clique aqui... execução orçamentária" NÃO — na verdade
via botão "EMENDAS PARLAMENTARES" do Portal Transparência MT
(https://www.transparencia.mt.gov.br/?c=79521669), que aponta pro SIGCON.

Diferente da Bahia (view CKAN só publica pagamento, sem autor): aqui cada
convênio (Repasse) tem uma sub-tabela real "Nm.Emenda / Parlamentar /
Val.Utilizada Emenda" — um convênio pode ser financiado por mais de uma
emenda de mais de um deputado (split real, não fabricado).

Confirmado por sondagem manual (2026-07-23):
  - Filtro por ano (`ano_ass`) funciona: 2009→977 convênios, 2018→346,
    2026(padrão)→949.
  - Filtro por parlamentar (`par_id`) funciona de verdade — testado
    Júlio Campos (par_id=35): 2022→0, 2024→36, 2025→43, todos-anos→97.
  - `par_id` só existe de 1 a 39 (a lista do dropdown é exaustiva) — o
    vínculo parlamentar↔convênio deste sistema NÃO alcança deputados de
    legislaturas antigas (ex.: Otaviano Pivetta, dep. estadual MT só em
    2006-2010, não está no dropdown). Cobertura real começa por volta de
    2015-2018 — a medir de verdade pelo Agent Verify, nunca assumir.
  - `pag_tela=500` funciona (testado, retorna as 500 linhas em ~13s) —
    usar isso em vez do default 10 pra reduzir nº de requisições.
  - O "Dicionário de Dados" oficial (CSV diário) do portal NÃO documenta
    "Parlamentar"/"Emenda" como campo exportável — só existem na tela de
    busca. Por isso a extração é via scraping de HTML autenticado por
    sessão (PHPSESSID obtido no GET inicial), não há endpoint JSON/CSV.

Execução:
    python agent_a_extrator.py --ano 2024
    python agent_a_extrator.py --todos              # 2007-2026
    python agent_a_extrator.py --todos --force
"""
import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data/almt_sigcon_emendas"
BRONZE_DIR = DATA_DIR / "bronze"
BRONZE_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://transp.sigcon.seplan.mt.gov.br"
INDEX_URL = f"{BASE_URL}/index_.php"
LIST_URL = (
    f"{BASE_URL}/index_.php?operacao=Manut&serv=convenio&pag={{pag}}&pag_tela=500"
    "&session_tipo_convenio=Repasse&entidade=&conv_numero=&situacao=&elabora=&parecer="
    "&favoravel=&desfavoravel=&devolvido=&numr_processo=&conv_objeto_filtro="
    "&par_id=&numr_emenda=&ano_ass={ano}"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 PRISMA888-ETL/1.0",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# a UI só oferece "Exercício" a partir de 2000, mas confirmar cobertura real
# fica a cargo do Agent Verify — aqui só definimos o range de tentativa
ANOS = list(range(2007, 2027))

# encontra cada bloco de <tr> "principal" (8 <td> rowspan=2/normal) seguido
# do <tr> com a sub-tabela de emendas. Regex tolerante a atributos variáveis.
ROW_RE = re.compile(
    r'conv_id=(\d+)#menu"[^>]*>([^<]*)</a>\s*</td>\s*'
    r'<td\s+rowspan="2"\s*>\s*<a[^>]*conv_id=\d+#menu"[^>]*>([^<]*)</a>\s*</td>\s*'
    r'<td\s+rowspan="2"\s*>\s*<a[^>]*conv_id=\d+#menu"[^>]*>([^<]*)</a>',
    re.IGNORECASE,
)


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _get(session: requests.Session, url: str, timeout: int = 60) -> str:
    r = session.get(url, headers=HEADERS, verify=False, timeout=timeout)
    r.raise_for_status()
    return r.text


def nova_sessao() -> requests.Session:
    s = requests.Session()
    _get(s, INDEX_URL)  # estabelece PHPSESSID — sem isso o filtro não aplica
    return s


def _parse_valor(txt: str) -> float | None:
    txt = (txt or "").strip()
    if not txt:
        return None
    try:
        return float(txt.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def extrair_convenios(html: str) -> list[dict]:
    """Parseia a tabela de resultados: cada <tr> principal (8 colunas) pode
    ser seguido de um <tr> com sub-tabela Nm.Emenda/Parlamentar/Val.

    Estratégia: separa o HTML em blocos por conv_id (cada bloco principal +
    sua sub-tabela, se houver), extrai os campos com regex direcionadas —
    mais robusto que tentar casar a linha inteira de uma vez (o HTML desse
    sistema legado tem espaçamento/atributos inconsistentes linha a linha).
    """
    convenios: dict[str, dict] = {}

    # cada <a href=".../conv_id=NNNN#menu" title="Lançado em: DATA por AUTOR">TEXTO</a>
    link_re = re.compile(
        r'conv_id=(\d+)#menu"[^>]*>\s*([^<]*?)\s*(?:<br>)?\s*</a>',
        re.IGNORECASE,
    )

    # quebra o documento em blocos por MUDANÇA de conv_id — não por <tr>, porque
    # a sub-tabela de emendas usa a mesma tag <tr style="cursor:hand"> da linha
    # principal e um split ingênuo por tag separava a emenda do seu convênio.
    posicoes = []
    ultimo_id = None
    for m in re.finditer(r'conv_id=(\d+)', html):
        if m.group(1) != ultimo_id:
            posicoes.append(m.start())
            ultimo_id = m.group(1)
    posicoes.append(len(html))
    blocos = [html[posicoes[i]:posicoes[i + 1]] for i in range(len(posicoes) - 1)]

    for bloco in blocos:
        if "conv_id=" not in bloco:
            continue
        campos = link_re.findall(bloco)
        if not campos:
            continue
        conv_id = campos[0][0]
        textos = [c[1].strip() for c in campos]
        # ordem esperada: concedente, proponente, objeto, processo(x2 possível),
        # numero, acao, valor, vigencia — como o nº de <a> varia (processo às
        # vezes tem 2 códigos), pega os campos pela POSIÇÃO a partir do fim
        # (valor e vigência são estáveis) e do início (concedente/proponente/objeto)
        if conv_id not in convenios:
            if len(textos) < 6:
                continue
            convenios[conv_id] = {
                "conv_id": conv_id,
                "concedente": textos[0],
                "proponente": textos[1],
                "objeto": textos[2],
                "campos_brutos": textos,
                "emendas": [],
            }

        # sub-tabela de emendas: <td>NUM</td><td>PARLAMENTAR</td><td align="right">VALOR</td>
        emenda_re = re.compile(
            r'<td>(\d+)</td>\s*<td>([^<]+)</td>\s*<td align="right">([\d.,]+)</td>',
        )
        for num, parlamentar, valor in emenda_re.findall(bloco):
            convenios[conv_id]["emendas"].append({
                "numero_emenda": num.strip(),
                "parlamentar_nome": parlamentar.strip(),
                "valor_utilizado": _parse_valor(valor),
            })

        # valor do convênio e vigência: últimos campos numéricos/data do bloco
        val_m = re.search(r'align="right">\s*<a[^>]*>([\d.,]+)</a>', bloco)
        if val_m and "valor_convenio" not in convenios[conv_id]:
            convenios[conv_id]["valor_convenio"] = _parse_valor(val_m.group(1))
        vig_m = re.search(r'>(\d{2}/\d{2}/\d{4}\s+a\s+\d{2}/\d{2}/\d{4})<', bloco)
        if vig_m and "vigencia" not in convenios[conv_id]:
            convenios[conv_id]["vigencia"] = vig_m.group(1)
        proc_m = re.search(r'>([A-Z]{3,10}-PRO-\d{4}/\d+)<', bloco)
        if proc_m and "processo" not in convenios[conv_id]:
            convenios[conv_id]["processo"] = proc_m.group(1)
        num_conv_m = re.search(r'>(\d+-20\d{2})<', bloco)
        if num_conv_m and "numero_convenio" not in convenios[conv_id]:
            convenios[conv_id]["numero_convenio"] = num_conv_m.group(1)

    return list(convenios.values())


def coletar_ano(session: requests.Session, ano: int, force: bool) -> Path | None:
    out = BRONZE_DIR / f"almt_sigcon_{ano}_bronze.json"
    if out.exists() and not force:
        log(f"♻️  {ano}: bronze já existe (--force para refazer)")
        return out

    todos: list[dict] = []
    pag = 1
    while True:
        url = LIST_URL.format(pag=pag, ano=ano)
        html = _get(session, url)
        pagina = extrair_convenios(html)
        if not pagina:
            break
        todos.extend(pagina)
        log(f"  {ano} pág {pag}: +{len(pagina)} convênios (total {len(todos)})")
        if len(pagina) < 400:  # heurística: página não cheia = última página
            break
        pag += 1
        time.sleep(1)  # cortesia — fonte de terceiro, sem paralelismo agressivo

    if not todos:
        log(f"⚠️  {ano}: 0 convênios (fonte pode não cobrir este ano)")
        return None

    payload = {
        "meta": {
            "portal": "SIGCON — SEPLAN/SEFAZ MT",
            "fonte_url": LIST_URL.format(pag=1, ano=ano),
            "ano_ass": ano,
            "data_extracao": datetime.now(timezone.utc).isoformat(),
            "total_convenios": len(todos),
            "total_com_emenda": sum(1 for c in todos if c["emendas"]),
        },
        "records": todos,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    log(f"✅ {ano}: {len(todos)} convênios ({payload['meta']['total_com_emenda']} com emenda vinculada) → {out.name}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Agent A — Extrator ALMT/SIGCON Emendas MT")
    ap.add_argument("--ano", type=int)
    ap.add_argument("--todos", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not args.ano and not args.todos:
        ap.error("passe --ano AAAA (teste) ou --todos")

    session = nova_sessao()
    anos = [args.ano] if args.ano else ANOS
    for ano in anos:
        try:
            coletar_ano(session, ano, args.force)
        except Exception as e:
            log(f"❌ {ano}: {e}")
        print()

    log("✅ Agent A concluído.")


if __name__ == "__main__":
    main()

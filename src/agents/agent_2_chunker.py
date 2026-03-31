import os, sys, json, hashlib, re, argparse
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote
from typing import List, Optional, Dict, Any, Tuple

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Higienização e Padronização Estrutural (Pipeline Silver).",
        "especialidade": "Normalização Regexp / Algoritmo",
        "protocolo_tecnico": "Regex + Mapeamento Semântico + Hash",
        "camada_dados": "Prata (Dados Limpos)",
        "seguranca": "Validação de Checksum/Tipagem"
    },
    "diretrizes": [
        "1. Limpa strings (espaços extras, N/A, Null).",
        "2. Normaliza Textos para Title Case inteligente.",
        "3. Extrai CNPJ/CPF embutidos em QUALQUER posição do nome (início, meio, fim) — inclusive fragmentos parciais.",
        "4. Repara URLs de PDF truncadas ou relativas + decodifica %20.",
        "5. Converte Valores Monetários BR (1.234,56 -> 1234.56).",
        "6. Unifica Meses e Anos em ISO-8601 (YYYY-MM-01).",
        "7. Gera `prisma_id` único baseado em Hash da despesa."
    ],
    "apuracao": {
        "safras_suportadas": [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026],
        "saida_esperada": "data/saida/prata/alba_{ano}_prata.json"
    }
}

# ── Padrões de documentos ────────────────────────────────────────────────────
# CNPJ completo mascarado:  33.139.754/0001-86
_RE_CNPJ_MASK = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')
# CNPJ puro 14 dígitos:     33139754000186
_RE_CNPJ_RAW  = re.compile(r'(?<![\d])\d{14}(?![\d])')
# CPF mascarado:            054.187.305-92
_RE_CPF_MASK  = re.compile(r'\d{3}\.\d{3}\.\d{3}-\d{2}')
# CPF puro 11 dígitos:      05418730592
_RE_CPF_RAW   = re.compile(r'(?<![\d])\d{11}(?![\d])')
# CNPJ fragmento inicial:   33.139.754  (sem /XXXX-XX — CNPJ incompleto no campo)
_RE_CNPJ_FRAG = re.compile(r'(?<![\d\.])\d{2}\.\d{3}\.\d{3}(?![/\d])')
# Fragmento numérico solto no início/fim do nome (ex: "33139754 Vinicius")
_RE_NUM_SOLTO = re.compile(r'^[\d\.\-/]+\s+|\s+[\d\.\-/]+$')


class PurificadorBebeto:
    VERSION = "bebeto_v2.5"

    def __init__(self):
        self.flags = []
        self.errors = 0
        self.processed_count = 0

    def clean_string(self, text: Any) -> Optional[str]:
        """Diretriz 1: String Vazia -> None + Normalização base."""
        if text is None: return None
        s = str(text).strip()
        if s.lower() in ["", "-", "n/a", "null", "none", "."]:
            return None
        s = re.sub(r'\s+', ' ', s)
        return s

    def normalizar_texto(self, text: Any, mode: str = "title") -> Optional[str]:
        """Diretriz 2: Normalização de Texto (Title Case ou UPPER)."""
        s = self.clean_string(text)
        if not s: return None

        if mode == "upper":
            return s.upper()

        stopwords = {"de", "da", "do", "das", "dos", "e", "a", "o", "del", "la"}
        palavras = s.split()
        resultado = " ".join(
            w.capitalize() if w.lower() not in stopwords else w.lower()
            for w in palavras
        )

        siglas = ["S.A.", "S/A", "LTDA", "EPP", "ME", "EIRELI", "S.A"]
        for sigla in siglas:
            resultado = re.sub(re.escape(sigla.title()), sigla, resultado, flags=re.IGNORECASE)

        return resultado

    def extrair_documento_do_nome(
        self, nome: str
    ) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Diretriz 3: Detecta e remove CPF ou CNPJ embutido em QUALQUER posição do nome.
        Passagens (ordem de prioridade):
          1. CNPJ mascarado completo:  33.139.754/0001-86
          2. CPF  mascarado completo:  054.187.305-92
          3. CNPJ puro 14 dígitos:     33139754000186
          4. CPF  puro 11 dígitos:     05418730592
          5. CNPJ fragmento inicial:   33.139.754  (CNPJ incompleto — limpa e sinaliza)
          6. Número solto no início/fim do nome
        Retorna: (nome_limpo, numero_doc, tipo_doc)  — tipo_doc: 'CPF' | 'CNPJ' | None
        """
        if not nome:
            return nome, None, None

        s = nome.strip()
        doc  = None
        tipo = None

        # 1º — CNPJ mascarado completo
        m = _RE_CNPJ_MASK.search(s)
        if m:
            doc  = re.sub(r'\D', '', m.group())
            s    = (s[:m.start()] + s[m.end():]).strip()
            tipo = "CNPJ"

        # 2º — CPF mascarado completo
        if not doc:
            m = _RE_CPF_MASK.search(s)
            if m:
                doc  = re.sub(r'\D', '', m.group())
                s    = (s[:m.start()] + s[m.end():]).strip()
                tipo = "CPF"

        # 3º — CNPJ puro 14 dígitos
        if not doc:
            m = _RE_CNPJ_RAW.search(s)
            if m:
                doc  = m.group()
                s    = (s[:m.start()] + s[m.end():]).strip()
                tipo = "CNPJ"

        # 4º — CPF puro 11 dígitos
        if not doc:
            m = _RE_CPF_RAW.search(s)
            if m:
                doc  = m.group()
                s    = (s[:m.start()] + s[m.end():]).strip()
                tipo = "CPF"

        # 5º — CNPJ fragmento inicial (ex: "33.139.754 Vinicius...")
        if not doc:
            m = _RE_CNPJ_FRAG.search(s)
            if m:
                doc  = re.sub(r'\D', '', m.group())  # guarda os 8 dígitos disponíveis
                s    = (s[:m.start()] + s[m.end():]).strip()
                tipo = "CNPJ_FRAGMENTO"

        # 6º — Número solto remanescente no início ou fim
        s = _RE_NUM_SOLTO.sub('', s).strip()

        # Limpa sobras de pontuação após remoção
        s = re.sub(r'^[\s,;\-/]+|[\s,;\-/]+$', '', s)
        s = re.sub(r'\s{2,}', ' ', s).strip()

        return s, doc, tipo

    def validar_pdf(self, url: Any) -> Tuple[Optional[str], List[str]]:
        """Diretriz 4: Flags de PDF, URL Correction e decodificação %20."""
        flags = []
        u = self.clean_string(url)
        if not u:
            flags.append("pdf_ausente")
            return None, flags

        u = unquote(u)

        BASE_ALBA = "https://www.al.ba.gov.br"
        if u.startswith("/"):
            u = BASE_ALBA + u
            flags.append("pdf_url_relativa_corrigida")

        if u.endswith(":anexo:") or u.endswith(":anexo") or u.endswith("/"):
            flags.append("pdf_url_sem_arquivo")
            return None, flags

        if not u.startswith("http"):
            flags.append("pdf_url_invalida")
        if not u.lower().endswith(".pdf"):
            flags.append("pdf_extensao_estranha")

        return u, flags

    def normalizar_nf(self, nf: Any) -> Tuple[Optional[str], str, List[str]]:
        """Diretriz 5: Normalização de NF."""
        flags = []
        s = self.clean_string(nf)
        if not s: return None, "ausente", ["nf_ausente"]

        limpo = re.sub(r'^0+', '', s)
        if not limpo: limpo = "0"

        nf_tipo = "normal"
        if "/" in limpo:
            flags.append("nf_com_barra")
            nf_tipo = "barra"
        elif len(limpo) > 10:
            flags.append("nf_longa")
            nf_tipo = "longa"
        elif len(limpo) <= 6:
            nf_tipo = "curta"

        return limpo, nf_tipo, flags

    def mapear_categoria(self, cat: Any) -> str:
        """Diretriz 6: Categoria Slug."""
        s = self.clean_string(cat)
        if not s: return "outros"
        s = s.lower()
        mapping = {
            "divulga": "divulgacao",
            "locomoc": "locomocao",
            "combust": "combustivel",
            "telef": "telefonia",
            "correio": "correios",
            "consult": "consultoria",
            "assessor": "consultoria",
            "hosped": "hospedagem",
            "aliment": "alimentacao",
            "passag": "passagens",
            "aluguel": "aluguel",
            "imovel": "aluguel",
            "material": "material",
            "aquisi": "aquisicao",
            "tecnolog": "tecnologia",
            "software": "tecnologia",
            "locaç": "locacao_veiculo",
            "locac": "locacao_veiculo",
            "carro": "locacao_veiculo",
            "veicu": "locacao_veiculo",
        }
        for key, val in mapping.items():
            if key in s: return val
        return "outros"

    def converter_competencia(self, comp: Any) -> Dict[str, Any]:
        """Diretriz 6: Competência -> Date, Ano, Mes."""
        s = self.clean_string(comp)
        res = {"date": None, "ano": None, "mes": None}
        if not s: return res
        match = re.search(r'(\d{1,2})/(\d{4})', s)
        if match:
            mes, ano = int(match.group(1)), int(match.group(2))
            if 1 <= mes <= 12:
                res["date"] = f"{ano}-{mes:02d}-01"
                res["ano"] = ano
                res["mes"] = mes
        return res

    def validar_cnpj(self, cnpj: Any) -> Tuple[Optional[str], List[str]]:
        """Diretriz 8: Validação matemática de CNPJ."""
        s = str(cnpj)
        digits = re.sub(r'\D', '', s)

        if not digits or len(digits) != 14:
            return digits if digits else None, ["cnpj_tamanho_invalido"]
        if digits == digits[0] * 14:
            return digits, ["cnpj_falso_sequencial"]

        def calc_digito(s, pesos):
            soma = sum(int(a) * b for a, b in zip(s, pesos))
            resto = soma % 11
            return 0 if resto < 2 else 11 - resto

        p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        p2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        d1 = calc_digito(digits[:12], p1)
        d2 = calc_digito(digits[:13], p2)

        if int(digits[12]) != d1 or int(digits[13]) != d2:
            return digits, ["cnpj_digito_invalido"]
        return digits, []

    def normalizar_valor(self, valor: Any) -> Tuple[Optional[float], List[str]]:
        """Diretriz 5: Valor Monetário Robusto."""
        if valor is None: return None, []
        if isinstance(valor, (int, float)):
            return float(valor), []
        s = str(valor).strip().replace("R$", "").replace(" ", "")
        if not s: return None, []
        try:
            if re.search(r'\d\.\d{3},', s) or ("," in s and "." not in s) or ("," in s and s.find(".") < s.find(",")):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
            return float(re.sub(r'[^\d.-]', '', s)), []
        except:
            return None, ["valor_invalido"]

    def purificar_registro(self, r: Dict[str, Any]) -> Dict[str, Any]:
        """Orquestra todas as diretrizes para um único registro."""
        flags = []
        p = {}

        # Fonte
        p["fonte_portal"] = "ALBA"
        p["fonte_url"] = "https://www.al.ba.gov.br/transparencia/verbas-idenizatorias"

        # Deputado / Partido
        p["deputado"] = self.normalizar_texto(r.get("deputado"))
        p["partido"] = self.normalizar_texto(r.get("partido"), mode="upper")

        # Diretriz 3: Fornecedor — extrai CPF/CNPJ de QUALQUER posição do nome
        nome_forn_cru = r.get("nome_fornecedor") or ""
        nome_limpo, doc_extraido, tipo_doc_extraido = self.extrair_documento_do_nome(nome_forn_cru)
        p["nome_fornecedor"] = self.normalizar_texto(nome_limpo)
        p["nome_fornecedor_limpo"] = nome_limpo.upper() if nome_limpo else None

        # CPF: pode vir do campo tipo_documento=CPF ou extraído do nome
        tipo_documento = self.clean_string(r.get("tipo_documento"))

        if tipo_documento == "CPF":
            cpf_digits = re.sub(r'\D', '', str(r.get("cnpj_fornecedor", "")))
            p["cpf_fornecedor"] = cpf_digits if len(cpf_digits) == 11 else doc_extraido
            p["cnpj_fornecedor"] = None
            p["cnpj_valido"] = None
        else:
            if tipo_doc_extraido == "CPF":
                p["cpf_fornecedor"] = doc_extraido
                flags.append("cpf_extraido_do_nome")
            elif tipo_doc_extraido == "CNPJ":
                p["cpf_fornecedor"] = None
                flags.append("cnpj_extraido_do_nome")
            elif tipo_doc_extraido == "CNPJ_FRAGMENTO":
                p["cpf_fornecedor"] = None
                flags.append("cnpj_fragmento_extraido_do_nome")
            else:
                p["cpf_fornecedor"] = None

            cnpj_norm, cnpj_flags = self.validar_cnpj(r.get("cnpj_fornecedor"))
            p["cnpj_fornecedor"] = cnpj_norm
            p["cnpj_valido"] = len(cnpj_flags) == 0
            flags.extend(cnpj_flags)

        # Fix 2: CPF e CNPJ presentes ao mesmo tempo → sinaliza para Ronaldo Gold
        if p.get("cpf_fornecedor") and p.get("cnpj_fornecedor"):
            flags.append("fornecedor_pf_e_pj")

        # Valor
        valor_norm, valor_flags = self.normalizar_valor(r.get("valor"))
        p["valor_raw"] = self.clean_string(r.get("valor"))
        p["valor"] = valor_norm
        flags.extend(valor_flags)

        # NF
        nf_original = r.get("num_nf")
        nf_norm, nf_tipo, nf_flags = self.normalizar_nf(nf_original)
        p["num_nf"] = self.clean_string(nf_original)
        p["num_nf_normalizado"] = nf_norm
        p["nf_tipo"] = nf_tipo
        flags.extend(nf_flags)

        # Competência
        comp_info = self.converter_competencia(r.get("competencia"))
        p["competencia_raw"] = self.clean_string(r.get("competencia"))
        p["competencia_date"] = comp_info["date"]
        p["competencia_ano"] = comp_info["ano"]
        p["competencia_mes"] = comp_info["mes"]
        if not comp_info["date"]: flags.append("competencia_invalida")

        # Categoria
        p["categoria_original"] = self.clean_string(r.get("categoria"))
        p["categoria_detalhe_raw"] = self.clean_string(r.get("categoria_detalhe"))
        p["categoria_slug"] = self.mapear_categoria(r.get("categoria"))

        # PDF
        link_orig = self.clean_string(r.get("link_pdf_nf"))
        p["link_pdf_nf_raw"] = link_orig
        u_corrigida, pdf_flags = self.validar_pdf(r.get("link_pdf_nf"))
        p["url_pdf_nf"] = u_corrigida
        p["link_pdf_valido"] = len([f for f in pdf_flags if f != "pdf_url_relativa_corrigida"]) == 0
        flags.extend(pdf_flags)

        # Pass Through — todos os campos do Bronze preservados
        p["num_processo"] = self.clean_string(r.get("num_processo"))
        p["ano"] = r.get("ano")
        valor_glosado, _ = self.normalizar_valor(r.get("valor_glosado"))
        p["valor_glosado"] = valor_glosado
        valor_detalhe, _ = self.normalizar_valor(r.get("valor_detalhe"))
        p["valor_detalhe"] = valor_detalhe
        p["tipo_documento"] = tipo_documento
        p["link_detalhe"] = self.clean_string(r.get("link_detalhe"))
        p["romario_coletado_em"] = self.clean_string(r.get("coletado_em"))
        p["numero_nf_recibo_raw"] = self.clean_string(r.get("numero_nf_recibo"))

        # Score de Qualidade
        mandatory = ["num_processo", "num_nf", "competencia_date", "deputado", "valor", "cnpj_fornecedor"]
        filled = sum(1 for f in mandatory if p.get(f) is not None)
        p["qualidade_score"] = round(filled / len(mandatory), 2)

        p["flags"] = sorted(list(set(flags)))
        p["processado_em"] = datetime.utcnow().isoformat() + "Z"
        p["versao_bebeto"] = self.VERSION

        chave = f"{p['num_processo']}|{p['num_nf']}|{p['cnpj_fornecedor']}|{p['valor']}|{p['competencia_date']}"
        p["prisma_id"] = hashlib.md5(chave.encode()).hexdigest()

        return p


def main():
    parser = argparse.ArgumentParser(description="Xylos-Bebeto v2.5: O Purificador de Plasma")
    env_ano = os.environ.get("ANO_ALVO")
    parser.add_argument("--year", type=str, default=env_ano, help="Ano para processar")
    parser.add_argument("--file", type=str, help="Arquivo específico para processar")
    args = parser.parse_args()

    print(f"[AGENT 2] 🛡️ Bebeto v2.5: Iniciando Purificação...")
    sys.stdout.flush()

    base_dir = Path(__file__).resolve().parent.parent.parent
    data_dir = base_dir / "data"

    bronze_path = None
    if args.file:
        bronze_path = Path(args.file)
        if not bronze_path.exists():
            bronze_path = data_dir / "saida" / "bronze" / args.file
        if not bronze_path.exists():
            bronze_path = data_dir / "saida" / "checkpoints" / args.file
    elif args.year:
        final_path = data_dir / "saida" / "bronze" / f"alba_{args.year}_bronze.json"
        checkpoint_path = data_dir / "saida" / "bronze" / f"alba_{args.year}_checkpoint.json"
        if final_path.exists():
            bronze_path = final_path
        elif checkpoint_path.exists():
            bronze_path = checkpoint_path
    else:
        bronze_files = sorted(
            list((data_dir / "saida" / "bronze").rglob("*alba*checkpoint*.json")) +
            list((data_dir / "saida" / "bronze").rglob("*alba*bronze*.json")),
            key=os.path.getmtime, reverse=True
        )
        bronze_path = bronze_files[0] if bronze_files else None

    if not bronze_path or not bronze_path.exists():
        print(f"[AGENT 2] ❌ Arquivo Bronze não encontrado.")
        sys.stdout.flush()
        sys.exit(1)

    print(f"[AGENT 2] 📂 Carregando: {bronze_path.name}")
    sys.stdout.flush()

    with open(bronze_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        registros = data.get("records", data) if isinstance(data, dict) else data

    purificador = PurificadorBebeto()
    prata = []
    vistos = set()

    print(f"[AGENT 2] ⚙️ Purificando {len(registros)} registros...")
    sys.stdout.flush()

    for i, r in enumerate(registros):
        p = purificador.purificar_registro(r)
        if p["prisma_id"] not in vistos:
            vistos.add(p["prisma_id"])
            prata.append(p)
        if (i + 1) % 500 == 0:
            print(f"[AGENT 2] ⚙️ Purificado: {i+1}/{len(registros)}...")
            sys.stdout.flush()

    ano_final = prata[0].get("competencia_ano") if prata else None
    if not ano_final:
        match = re.search(r'20\d{2}', bronze_path.name)
        ano_final = match.group(0) if match else (args.year or "undefined")

    output_path = data_dir / "saida" / "prata" / f"alba_{ano_final}_prata.json"
    os.makedirs(output_path.parent, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(prata, f, ensure_ascii=False, indent=2)

    print(f"[AGENT 2] 💾 Purificação Concluída: {output_path.name}")
    print(f"[AGENT 2] 💎 Registros Úteis: {len(prata)}")
    print(f"[AGENT 2] [AGENT DONE] ✅ Bebeto v2.5 encerra com sucesso!")
    sys.stdout.flush()


if __name__ == "__main__":
    main()

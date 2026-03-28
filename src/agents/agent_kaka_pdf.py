#!/usr/bin/env python3
"""
🦅 KAKÁ v4.1 ENTERPRISE — TEMPLATES & CLASSIFICAÇÃO
"""
import os, json, time, re, argparse, asyncio, io
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import aiohttp
import fitz  # PyMuPDF
from pdf2image import convert_from_path
from PIL import Image
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from dotenv import load_dotenv

try:
    from pyzbar.pyzbar import decode as qr_decode
    HAS_QR = True
except ImportError:
    HAS_QR = False

try:
    import pytesseract
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_CLIENT = None
GEMINI_SDK = "none"

try:
    from google import genai as google_genai
    if GEMINI_API_KEY:
        GEMINI_CLIENT = google_genai.Client(api_key=GEMINI_API_KEY)
    GEMINI_SDK = "new"
except ImportError:
    try:
        import google.generativeai as genai_legacy
        if GEMINI_API_KEY:
            genai_legacy.configure(api_key=GEMINI_API_KEY)
        GEMINI_SDK = "legacy"
    except ImportError: pass

MAX_CONCURRENT = 2
BATCH_SIZE = 10
AI_COOLDOWN = 10.0
MAX_GEMINI_DIA = 100

__PRISMA_MANIFEST__ = {
    "visao_geral": {
        "missao": "Auditoria Forense de PDFs (NFS-e, DANFE).",
        "especialidade": "Extração Híbrida (Regex + IA Visual)",
        "protocolo_tecnico": "PyMuPDF + Pytesseract + Gemini 1.5 Pro",
        "camada_dados": "Kaka (Auditoria Premium)",
        "seguranca": "Fallbacks Sucessivos, Quota Diária Gemini Limitada"
    },
    "diretrizes": [
        "1. Faz download assíncrono blindado contra timeouts de 20s.",
        "2. Classifica arquivo como 'NF Digital', 'Imagem' ou 'Erro'.",
        "3. Luta Livre 1: Tenta Templates Clássicos (Regex).",
        "4. Luta Livre 2: Submete visão à IA Vision (Gemini) se ilegível.",
        "5. Audita discrepâncias e emite Score de Confiança (0.0 a 1.0).",
        "6. Emite alertas de fraude (ex: CNPJ portal vs CNPJ rodapé da nota)."
    ],
    "apuracao": {
        "safras_suportadas": [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
        "saida_esperada": "data/saida/kaka/alba_{ano}_kaka.json"
    }
}

class KakaV41:
    TEMPLATES = {
        "salvador_nfse": {
            "valor": r"VALOR TOTAL DA NOTA\s*=\s*R\$\s*([\d\.]+,\d{2})",
            "cnpj":  r"Inscrição no CNPJ:\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})",
            "num_nf": r"Número da Nota\s*[:\s]*(\d+)"
        },
        "feira_nfse": {
            "valor": r"Valor Líquido da Nota Fiscal \(R\$\):\s*([\d\.]+,\d{2})",
            "cnpj":  r"CNPJ[:\s]*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})",
        },
        "danfe_nfe": {
            "valor": r"VALOR TOTAL DA NOTA\s*([\d\.]+,\d{2})",
            "cnpj":  r"CNPJ[:\s]*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})",
        }
    }

    def __init__(self, ano: str):
        self.ano = str(ano)
        self.base_dir = Path("/home/carneiro888/CARNEIRO888/N888N - AGENTIC EXTRATORES/n888n")
        self.prata_path = self.base_dir / "data" / "saida" / "prata" / f"alba_{ano}_prata.json"
        self.kaka_dir   = self.base_dir / "data" / "saida" / "kaka"
        self.pdf_dir    = self.base_dir / "data" / "raw" / "alba" / "pdfs" / str(ano)
        self.kaka_out   = self.kaka_dir / f"alba_{ano}_kaka.json"
        for d in [self.kaka_dir, self.pdf_dir]: d.mkdir(parents=True, exist_ok=True)
        self.gemini_calls_hoje = 0
        self.last_ai_time = 0.0
        self.global_pause_until = 0.0
        self.ai_limiter = asyncio.Semaphore(1)

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        await self.session.close()

    async def download_pdf(self, url: str, num_proc: str) -> Tuple[Optional[Path], str]:
        if not url or not url.startswith("http"): return None, "sem_url"
        caminho = self.pdf_dir / f"{num_proc}.pdf"
        if caminho.exists() and caminho.stat().st_size > 500: return caminho, "cache"
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    if len(content) > 500:
                        caminho.write_bytes(content)
                        return caminho, "download"
        except: pass
        return None, "falha"

    def classificar_tipo(self, pdf_path: Path) -> str:
        try:
            doc = fitz.open(str(pdf_path))
            texto = "".join(p.get_text() for p in doc)
            doc.close()
            return "nf_digital" if len(texto.strip()) > 800 else "imagem"
        except: return "erro"

    def detectar_modelo(self, texto: str) -> str:
        if "SALVADOR" in texto: return "salvador_nfse"
        if "FEIRA DE SANTANA" in texto: return "feira_nfse"
        if "DANFE" in texto: return "danfe_nfe"
        return "generico"

    def extrair_por_template(self, texto: str, modelo: str) -> Dict[str, Any]:
        res = {"valor_total": None, "emitente_cnpj": None}
        if modelo not in self.TEMPLATES: return res
        tmpl = self.TEMPLATES[modelo]
        for campo, regex in tmpl.items():
            m = re.search(regex, texto, re.I)
            if m:
                if campo == "valor": res["valor_total"] = float(m.group(1).replace(".", "").replace(",", "."))
                elif campo == "cnpj": res["emitente_cnpj"] = re.sub(r"\D", "", m.group(1))
        return res

    async def extrair_completo(self, pdf_path: Path, reg: dict) -> Dict[str, Any]:
        tipo = self.classificar_tipo(pdf_path)
        doc = fitz.open(str(pdf_path))
        texto = "".join(p.get_text() for p in doc)
        doc.close()
        modelo = self.detectar_modelo(texto)
        ext = self.extrair_por_template(texto, modelo)
        v_portal = float(reg.get("valor") or 0)
        v_nf = ext.get("valor_total") or 0
        conf = 0.99 if abs(v_nf - v_portal) < 0.10 else 0.5
        return {"tipo": tipo, "modelo": modelo, "confianca": conf, "extraido": ext}

    async def processar_item(self, reg: dict, idx: int, total: int) -> dict:
        num_proc = str(reg.get("num_processo", f"idx_{idx}"))
        pdf_path, _ = await self.download_pdf(reg.get("url_pdf_nf"), num_proc)
        res = await self.extrair_completo(pdf_path, reg) if pdf_path else {"tipo": "erro", "modelo": "generico", "confianca": 0.0, "extraido": {}}
        ext = res.get("extraido", {})
        resultado = {
            **reg,
            "kaka_tipo_documento": res["tipo"],
            "kaka_modelo_detectado": res["modelo"],
            "kaka_confianca": res["confianca"],
            "kaka_valor_nf": ext.get("valor_total"),
            "kaka_emitente_cnpj": ext.get("emitente_cnpj"),
            "kaka_processado_em": datetime.utcnow().isoformat() + "Z",
            "kaka_versao": "v4.1-templates"
        }
        print(f"[{self.ano}] 📦 {idx+1:04d}/{total:04d} | 📄 {num_proc:<8} | 🧩 {res['modelo']:<15} | ⭐ {res['confianca']:.2f}")
        return resultado

    async def run(self, limit: int = 0):
        print(f"🦅 KAKÁ v4.1 ENTERPRISE | SAFRA: {self.ano}")
        with open(self.prata_path, "r") as f: registros = json.load(f)
        alvos = registros[:limit] if limit > 0 else registros
        processados = {}
        if self.kaka_out.exists():
            try:
                with open(self.kaka_out, "r") as f:
                    for r in json.load(f): processados[r["prisma_id"]] = r
            except: pass
        pendentes = [(i, r) for i, r in enumerate(alvos) if r["prisma_id"] not in processados]
        async with self:
            for i in range(0, len(pendentes), BATCH_SIZE):
                lote = pendentes[i:i+BATCH_SIZE]
                for idx, r in lote:
                    res = await self.processar_item(r, idx, len(alvos))
                    processados[res["prisma_id"]] = res
                final = [processados.get(reg["prisma_id"], reg) for reg in alvos]
                self.kaka_out.write_text(json.dumps(final, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ano", required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    asyncio.run(KakaV41(ano=args.ano).run(limit=args.limit))

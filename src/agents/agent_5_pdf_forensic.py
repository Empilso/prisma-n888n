import os, sys, json, re, glob
from pathlib import Path

def main():
    print("[AGENT 5] 📄 Iniciando PDF Forensic Analyst...")
    sys.stdout.flush()

    base_dir = Path(__file__).resolve().parent.parent.parent
    data_dir = base_dir / "data"
    anexos_dir = base_dir / "data" / "anexos" # Fix: anexos are usually in data/anexos

    pdfs = list(anexos_dir.glob("*.pdf")) if anexos_dir.exists() else []
    print(f"[AGENT 5] 📁 {len(pdfs)} PDFs encontrados em {anexos_dir}")
    sys.stdout.flush()

    if not pdfs:
        print("[AGENT 5] ⚠️ Nenhum PDF encontrado. Pulando extração.")
        print("[AGENT 5] [AGENT DONE] ✅ Concluído (sem PDFs para processar).")
        sys.stdout.flush()
        return

    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("[AGENT 5] ❌ PyMuPDF não instalado. Rode: pip install PyMuPDF")
        sys.exit(1)

    resultados = []
    for i, pdf_path in enumerate(pdfs):
        try:
            doc = fitz.open(str(pdf_path))
            text = "".join(page.get_text() for page in doc)
            doc.close()

            result = {"arquivo": pdf_path.name, "texto_extraido": text[:500]}

            # Regex básico NFSe
            for key, pattern in [
                ("numero_nfse", r"Nº\s*(?:NFSe|Nota Fiscal)\s*:?\s*(\d+)"),
                ("cnpj", r"CNPJ\s*:?\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})"),
                ("valor", r"(?:Total|Valor)\s*:?\s*R\$\s*([\d.,]+)"),
            ]:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    result[key] = m.group(1).strip()

            resultados.append(result)
            print(f"[AGENT 5] ✅ {pdf_path.name} extraído ({len(text)} chars)")
        except Exception as e:
            print(f"[AGENT 5] ⚠️ Erro em {pdf_path.name}: {e}")
        sys.stdout.flush()

    output_path = data_dir / "saida" / "prisma_pdfs.json"
    os.makedirs(output_path.parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    print(f"[AGENT 5] 💾 {len(resultados)} PDFs processados → {output_path.name}")
    print("[AGENT 5] [AGENT DONE] ✅ Concluído com sucesso!")
    sys.stdout.flush()

if __name__ == "__main__":
    main()

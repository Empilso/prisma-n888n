import os, sys, json
from pathlib import Path
from datetime import datetime

def main():
    print("[AGENT 6] 🔗 Iniciando Prisma Merge Final...")
    sys.stdout.flush()

    base_dir = Path(__file__).resolve().parent.parent.parent
    data_dir = base_dir / "data"

    ano_alvo = os.environ.get("ANO_ALVO", "2015")
    # Tenta buscar especificamente o arquivo Ouro da safra alvo
    ouro_regex = f"alba_{ano_alvo}_ouro.json"
    ouro_files = list((data_dir / "saida" / "ouro").glob(ouro_regex))
    
    if not ouro_files:
        # Fallback para o mais recente se nada for achado para o ano específico
        ouro_files = sorted(data_dir.rglob("*ouro*.json"), key=os.path.getmtime, reverse=True)

    if not ouro_files:
        print(f"[AGENT 6] ❌ Nenhum arquivo Ouro encontrado para o ano {ano_alvo}.")
        sys.exit(1)

    with open(ouro_files[0], "r", encoding="utf-8") as f:
        ouro = json.load(f)
    print(f"[AGENT 6] 📂 Ouro: {len(ouro)} registros")
    sys.stdout.flush()

    # Carrega PDFs (opcional)
    pdfs = {}
    pdf_file = data_dir / "saida" / "prisma_pdfs.json"
    if pdf_file.exists():
        with open(pdf_file, "r", encoding="utf-8") as f:
            pdf_list = json.load(f)
        pdfs = {p["arquivo"].replace(".pdf", ""): p for p in pdf_list}
        print(f"[AGENT 6] 📄 PDFs: {len(pdfs)} registros para merge")
        sys.stdout.flush()

    # Merge por id_alba (nome do arquivo PDF = id_alba)
    merged = 0
    for r in ouro:
        id_alba = str(r.get("num_processo", ""))
        if id_alba in pdfs:
            r["pdf_cnpj"] = pdfs[id_alba].get("cnpj", "")
            r["pdf_valor"] = pdfs[id_alba].get("valor", "")
            r["pdf_nfse"] = pdfs[id_alba].get("numero_nfse", "")
            merged += 1

    print(f"[AGENT 6] 🔗 Merge concluído: {merged} registros enriquecidos com PDF")
    sys.stdout.flush()

    ano = ouro[0].get("ano", "0000") if ouro else "0000"
    output_path = data_dir / "saida" / "ouro" / f"prisma_completo_{ano}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    os.makedirs(output_path.parent, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(ouro, f, ensure_ascii=False, indent=2)

    print(f"[AGENT 6] 💾 PRISMA COMPLETO: {output_path.name}")
    print(f"[AGENT 6] 📊 Total final: {len(ouro)} registros prontos para análise")
    print("[AGENT 6] [AGENT DONE] ✅ Pipeline completa! Dados prontos.")
    sys.stdout.flush()

if __name__ == "__main__":
    main()

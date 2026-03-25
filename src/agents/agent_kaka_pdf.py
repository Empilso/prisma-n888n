import os
import sys
import json
import time
import argparse
import requests
import datetime
import re
from pathlib import Path
import traceback

try:
    import fitz  # PyMuPDF
except ImportError:
    print("⚠️ [AGENT KAKÁ] PyMuPDF (fitz) não instalado. Rode: pip install pymupdf")
    sys.exit(1)

try:
    import numpy as np
    import cv2
except ImportError:
    print("⚠️ [AGENT KAKÁ] OpenCV/Numpy não instalado. Rode: pip install opencv-python numpy")
    sys.exit(1)

try:
    from PIL import Image
    import pytesseract
    from pytesseract import Output
except ImportError:
    print("⚠️ [AGENT KAKÁ] Pillow ou pytesseract não instalado. Rode: pip install Pillow pytesseract")
    sys.exit(1)

try:
    import google.generativeai as genai
except ImportError:
    print("⚠️ [AGENT KAKÁ] Google GenerativeAI não instalado. Rode: pip install google-generativeai")
    sys.exit(1)

try:
    from litellm import completion
except ImportError:
    print("⚠️ [AGENT KAKÁ] LiteLLM não instalado.")
    sys.exit(1)

if "GEMINI_API_KEY" in os.environ:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])


def calcular_entropia(array):
    hist = np.bincount(array.ravel(), minlength=256)
    p = hist / np.sum(hist)
    p = p[p > 0]
    return -np.sum(p * np.log2(p))

def classificar_pdf(path):
    try:
        doc = fitz.open(path)
        if len(doc) == 0:
            return "PDF_IMAGEM"
            
        texto = "".join(p.get_text() for p in doc)
        if len(texto.strip()) > 100:
            return "PDF_TEXTO"
            
        pagina = doc[0]
        pixmap = pagina.get_pixmap(dpi=150)
        array = np.frombuffer(pixmap.samples, dtype=np.uint8)
        entropia = calcular_entropia(array)
        
        if entropia > 7.2:
            return "MANUSCRITO"
        else:
            return "PDF_IMAGEM"
    except Exception as e:
        print(f"Erro ao classificar PDF: {str(e)}")
        return "PDF_IMAGEM"

def ocr_tesseract(caminho_img):
    try:
        img_cv = cv2.imread(caminho_img)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        texto = pytesseract.image_to_string(binary, lang='por')
        dados_ocr = pytesseract.image_to_data(binary, output_type=Output.DICT)
        confs = [int(c) for c in dados_ocr['conf'] if isinstance(c, (int, str)) and str(c).isdigit() and int(c) > 0]
        media_confianca = sum(confs) / len(confs) if confs else 0
        return texto, media_confianca
    except Exception as e:
        print(f"Erro Tesseract: {str(e)}")
        return "", 0

def ocr_gemini_flash(caminho_img):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = "Leia este documento e transcreva TODO o texto visível. Preserve números, datas e valores exatamente como estão."
        img = Image.open(caminho_img)
        response = model.generate_content([prompt, img])
        return response.text, 95.0
    except Exception as e:
        print(f"Erro Gemini Flash: {str(e)}")
        return "", 0

def preprocess_and_extract(path, tipo):
    caminho_temp = None
    texto = ""
    metodo = ""
    confianca = 100.0
    tentativas = 1
    
    if tipo == "PDF_TEXTO":
        try:
            texto = "".join(p.get_text() for p in fitz.open(path))
            metodo = "pymupdf"
        except:
            texto = ""
    else:
        try:
            pixmap = fitz.open(path)[0].get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            img.thumbnail((1024, 1024), Image.LANCZOS)
            caminho_temp = path.replace(".pdf", "_resized.jpg")
            img.save(caminho_temp, dpi=(300, 300), quality=95)
        except Exception as e:
             print(f"Erro redimensionamento: {e}")
             return "", "erro_pre_processamento", 0.0, 1

        if tipo == "PDF_IMAGEM":
            texto, confianca = ocr_tesseract(caminho_temp)
            metodo = "tesseract"
            if len(texto.strip()) < 50 or confianca < 60:
                print("[AGENT KAKÁ] 🔁 Tentativa 2/3 — Tesseract falhou, acionando Gemini Flash...")
                tentativas = 2
                texto, confianca = ocr_gemini_flash(caminho_temp)
                metodo = "gemini_flash_fallback"
        elif tipo == "MANUSCRITO":
            print("[AGENT KAKÁ] 🔁 Tentativa 1/3 — Direto para Gemini Flash Vision...")
            texto, confianca = ocr_gemini_flash(caminho_temp)
            metodo = "gemini_flash_fallback"
            
        if caminho_temp and os.path.exists(caminho_temp):
            os.remove(caminho_temp)
            
    return texto, metodo, confianca, tentativas

def extract_metadata_llm(texto, provider="groq", model_name="llama3-8b-8192"):
    if "DANFE" in texto or "NF-e" in texto or "CHAVE DE ACESSO" in texto:
        doc_tipo = "DANFE"
        prompt = f"""Extraia APENAS estes campos do DANFE abaixo:
emitente_cnpj, emitente_razao_social, nfe_numero, nfe_serie, nfe_chave_acesso,
nfe_protocolo_autorizacao, nfe_natureza_operacao, data_emissao, valor_total_documento,
valor_produtos, valor_icms, destinatario_nome, destinatario_cpf_cnpj, municipio, uf,
itens_resumo (max 15 palavras). Se não achar campo mande null. Só JSON e mais nada.
TEXTO: {texto[:3000]}"""
    elif any(p in texto for p in ["Fatura", "Mês de referência", "Vencimento", "Recibo"]):
        doc_tipo = "FATURA_SERVICO"
        prompt = f"""Extraia APENAS estes campos da fatura/recibo abaixo:
emitente_cnpj, emitente_razao_social, fatura_numero, fatura_periodo_referencia,
data_emissao, fatura_vencimento, valor_total_documento, servico_descricao (max 10 pal),
destinatario_nome, municipio, uf. Se não achar campo mande null. Só JSON e mais nada.
TEXTO: {texto[:3000]}"""
    else:
        doc_tipo = "OUTRO"
        prompt = f"""Extraia APENAS estes campos deste documento:
emitente_nome_ou_cnpj, data_documento, valor_total, descricao_servico (max 15 pal), destinatario_nome.
Se não achar campo mande null. Só JSON e mais nada.
TEXTO: {texto[:3000]}"""

    try:
        model_str = f"{provider}/{model_name}" if provider else model_name
        response = completion(
            model=model_str,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        dados = json.loads(content)
        dados['doc_tipo'] = doc_tipo
        return dados
    except Exception as e:
        return {"doc_tipo": doc_tipo, "llm_error": str(e)}

def validar_link(link):
    if not link or type(link) is not str or len(link) < 5: return False
    if link.endswith(":anexo:"): return False
    ext = link.split('.')[-1].lower()
    if ext not in ["pdf", "png", "jpg", "jpeg"]:
        # Na ALBA as vezes nao tem extensao no link. Mas vou deixar passar se nao for extensao obvia invalida
        if link.endswith(('/', '#')): return False
    return True

def run_kaka():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ano", required=True)
    args = parser.parse_args()
    ano = args.ano

    print(f"\n{'='*60}")
    print(f"🦅 [AGENT KAKÁ] O Arquivista Forense INICIADO — Safra: {ano}")
    print(f"{'='*60}")
    print(f"⏱️  Início: {datetime.datetime.now().strftime('%H:%M:%S')}")
    print(f"📋 Missão: Download, Classificação e Extração OCR Forense\n")
    
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    # MUDANÇA: Agora lê do BEBETO (Camada Prata)
    data_in = BASE_DIR / "data" / "saida" / "silver" / f"alba_{ano}.json"
    pdf_dir = BASE_DIR / "data" / "pdfs" / ano
    # MUDANÇA: Agora gera para o DUNGA (Camada Silver Analisada)
    data_out_dir = BASE_DIR / "data" / "saida" / "silver_analisada"
    
    pdf_dir.mkdir(parents=True, exist_ok=True)
    data_out_dir.mkdir(parents=True, exist_ok=True)
    
    data_out = data_out_dir / f"alba_{ano}.json"

    if not data_in.exists():
        print(f"❌ [AGENT KAKÁ] Erro: Arquivo {data_in} não encontrado!")
        print(f"O Bebeto (Xylos) precisa purificar a safra {ano} primeiro.")
        return

    with open(data_in, "r", encoding="utf-8") as f:
        records = json.load(f)
        
    out_records = []
    if data_out.exists():
        with open(data_out, "r", encoding="utf-8") as f:
            out_records = json.load(f)
            
    # Cria um set de processados pelo num_processo + num_nf para não fazer duas vezes o MESMO registro.
    processados = {r.get("num_processo", "") + "_" + str(r.get("num_nf", "")) for r in out_records}
    
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; Prisma/1.0)"})
    
    total = len(records)
    for i, rec in enumerate(records):
        pid = str(rec.get("num_processo", ""))
        nid = str(rec.get("numero_nf_recibo", "") or rec.get("num_nf", ""))
        uid = f"{pid}_{nid}"
        link = rec.get("link_pdf_nf")
        
        reg_kaka = rec.copy()
        
        if uid in processados:
            continue
            
        print(f"\n[AGENT KAKÁ] 🔗 Verificando link {pid}_{nid} [{i+1}/{total}]")
        
        if not validar_link(link):
            reg_kaka["pdf_baixado"] = False
            reg_kaka["pdf_status"] = "link_invalido"
            reg_kaka["requer_revisao_manual"] = False
            print(f"[AGENT KAKÁ] 📄 Link inválido — pulando...")
            out_records.append(reg_kaka)
            processados.add(uid)
            continue
            
        caminho_local = pdf_dir / f"{uid}.pdf"
        baixou_sucesso = False
        
        if not caminho_local.exists():
            print(f"[AGENT KAKÁ] ⬇️  Baixando PDF {i+1} de {total}...")
            for attempt in range(3):
                try:
                    time.sleep(1.5)
                    resp = session.get(link, timeout=30)
                    resp.raise_for_status()
                    with open(caminho_local, "wb") as f:
                        f.write(resp.content)
                    baixou_sucesso = True
                    break
                except Exception as e:
                    print(f"    Tentativa {attempt+1}/3 falhou: {str(e)}")
                    time.sleep(2)
        else:
            baixou_sucesso = True
            
        if not baixou_sucesso:
            reg_kaka["pdf_baixado"] = False
            reg_kaka["pdf_status"] = "erro_download"
            reg_kaka["requer_revisao_manual"] = True
            print(f"[AGENT KAKÁ] ❌ Erro definitivo ao baixar PDF.")
            out_records.append(reg_kaka)
            processados.add(uid)
            continue
            
        # Classificação e OCR
        tipo = classificar_pdf(str(caminho_local))
        print(f"[AGENT KAKÁ] 🔍 Tipo detectado: {tipo}")
        
        texto, metodo, confianca, tentativas = preprocess_and_extract(str(caminho_local), tipo)
        
        if len(texto.strip()) < 50 or confianca < 60:
            reg_kaka["requer_revisao_manual"] = True
            print(f"[AGENT KAKÁ] 🚨 Revisão manual: Extração falhou (confs={confianca:.1f} | len={len(texto.strip())})")
            dados_llm = {}
        else:
            print(f"[AGENT KAKÁ] ✅ Extraído via {metodo} — Confiança: {confianca:.1f}")
            prov = os.environ.get("LLM_PROVIDER", "groq")
            mod = os.environ.get("LLM_MODEL", "llama-3.1-8b-instant")
            dados_llm = extract_metadata_llm(texto, provider=prov, model_name=mod)
            reg_kaka.update(dados_llm)
            
            val_original = rec.get("valor", 0)
            val_extraido = dados_llm.get("valor_total_documento", val_original)
            try:
                if isinstance(val_extraido, str):
                    val_extraido = float(val_extraido.replace("R$","").replace(".","").replace(",", ".").strip() or 0)
                else:
                    val_extraido = float(val_extraido or 0)
                diff = abs(float(val_extraido) - float(val_original or 0))
                reg_kaka["divergencia_valor"] = bool(diff > 0.10)
            except:
                reg_kaka["divergencia_valor"] = True
                
            if reg_kaka["divergencia_valor"]:
                print(f"[AGENT KAKÁ] ⚠️  Divergência de valor! Ext: {val_extraido} | Ori: {val_original}")
                
            cnpj_ori = re.sub(r'\D', '', str(rec.get("cnpj_fornecedor", "") or ""))
            cnpj_ext = re.sub(r'\D', '', str(dados_llm.get("emitente_cnpj", "") or ""))
            reg_kaka["divergencia_cnpj"] = bool(cnpj_ori and cnpj_ext and cnpj_ori != cnpj_ext)
            
            campos = ["emitente_cnpj", "emitente_razao_social", "valor_total_documento", "data_emissao", "doc_tipo"]
            preenchidos = sum(1 for c in campos if dados_llm.get(c))
            score = round(preenchidos / len(campos), 2)
            if score >= 0.85: reg_kaka["confianca_extracao"] = "ALTO"
            elif score >= 0.60: reg_kaka["confianca_extracao"] = "MEDIO"
            else: reg_kaka["confianca_extracao"] = "BAIXO"
            
        reg_kaka["pdf_baixado"] = True
        reg_kaka["pdf_status"] = "ok"
        reg_kaka["caminho_local"] = str(caminho_local)
        reg_kaka["pdf_tipo"] = tipo
        reg_kaka["pdf_paginas"] = fitz.open(str(caminho_local)).page_count if caminho_local.exists() and tipo != "erro" else 0
        reg_kaka["extracao_metodo"] = metodo
        reg_kaka["extracao_tentativas"] = tentativas
        reg_kaka["processado_kaka_em"] = datetime.datetime.now().isoformat()
        reg_kaka["versao_kaka"] = "kaka_v1.1"
        if "requer_revisao_manual" not in reg_kaka:
            reg_kaka["requer_revisao_manual"] = False
            
        out_records.append(reg_kaka)
        processados.add(uid)
        
        # Checkpoint gracefully
        if (i + 1) % 5 == 0:
            with open(data_out, "w", encoding="utf-8") as f:
                json.dump(out_records, f, indent=2, ensure_ascii=False)
            print(f"[AGENT KAKÁ] 💾 CHECKPOINT SALVO ({i+1} de {total})")

    with open(data_out, "w", encoding="utf-8") as f:
        json.dump(out_records, f, indent=2, ensure_ascii=False)
    print(f"\n[AGENT KAKÁ] 🎉 Safra {ano} processada! Ponte Prata -> Prata Analisada concluída.")

if __name__ == "__main__":
    run_kaka()

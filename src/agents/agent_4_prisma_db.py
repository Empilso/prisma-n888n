import os, sys, json, hashlib, difflib
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal

DEPUTADOS_ATUAIS = [
    "Adolfo Menezes", "Alan Sanches", "Alex da Piatã", "Angelo Almeida", 
    "Angelo Coronel Filho", "Antônio Henrique Júnior", "Binho Galinha", "Bobô", 
    "Cafu Barreto", "Cláudia Oliveira", "Dr. Diego Castro", "Eduardo Alencar", 
    "Eduardo Salles", "Euclides Fernandes", "Eures Ribeiro", "Fabíola Mansur", 
    "Fabrício Falcão", "Fátima Nunes", "Felipe Duarte", "Hassan", "Hilton Coelho", 
    "Ivana Bastos", "Jordávio Ramos", "José de Arimateia", "Júnior Muniz", 
    "Júnior Nascimento", "Jurailton Santos", "Jusmari Oliveira", "Kátia Oliveira", 
    "Laerte do Vando", "Leandro de Jesus", "Luciano Araújo", "Luciano Ribeiro", 
    "Luciano Simões Filho", "Lucinha do MST", "Ludmilla Fiscina", "Manuel Rocha", 
    "Marcelinho Veiga", "Marcelino Galo", "Marcinho Oliveira", "Marcone Amaral", 
    "Maria del Carmen", "Marquinho Viana", "Matheus Ferreira", "Nelson Leal", 
    "Neusa Cadore", "Niltinho", "Olivia Santana", "Osni Cardoso", "Pablo Roberto", 
    "Pancadinha", "Patrick Lopes", "Paulo Câmara", "Paulo Rangel", "Pedro Tavares", 
    "Penalva", "Radiovaldo Costa", "Raimundinho da JR", "Ricardo Rodrigues", 
    "Roberto Carlos", "Robinho", "Robinson Almeida", "Rogério Andrade"
]

def normalizar_nome_deputado(nome_bruto: str) -> str:
    """Limpa e tenta padronizar o nome usando fuzzy matching com a tabela mestre."""
    if not nome_bruto:
        return ""
    
    # 1. Limpeza básica
    nome_limpo = nome_bruto.strip().title()
    
    # 2. Fuzzy Matching com TheFuzz / difflib
    #    cutoff=0.7 indica que precisa ser pelo menos 70% parecido para "dar match"
    matches = difflib.get_close_matches(nome_limpo, DEPUTADOS_ATUAIS, n=1, cutoff=0.7)
    
    if matches:
        return matches[0]  # O melhor match (Nome Oficial da Tabela de 63)
    
    # 3. Fallback: Retorna histórico limpo se não achar nos atuais 63
    return nome_limpo

class VerbaOuro(BaseModel):
    num_processo: str
    num_nf: str
    competencia: str
    deputado: str
    categoria: str
    valor: float
    hash_id: str
    risco_nivel: str = "Indeterminado"
    comentario_aguia: str = ""
    link_detalhe: Optional[str] = ""
    ano: Optional[int] = None
    processado_em: Optional[str] = None

def main():
    print("[AGENT 4] 🏛️ Iniciando Prisma DB — Validador Pydantic + Camada Ouro...")
    sys.stdout.flush()

    base_dir = Path(__file__).resolve().parent.parent.parent
    data_dir = base_dir / "data"

    ano_alvo = os.environ.get("ANO_ALVO", "2015")
    # Tenta buscar especificamente o arquivo da safra alvo
    prata_analisada = data_dir / "saida" / "prata" / f"alba_{ano_alvo}_prata_analisada.json"
    prata_simples = data_dir / "saida" / "prata" / f"alba_{ano_alvo}_prata.json"
    
    if prata_analisada.exists():
        prata_path = prata_analisada
    elif prata_simples.exists():
        prata_path = prata_simples
    else:
        # Fallback para o mais recente se nada for achado para o ano específico
        f_analisadas = sorted(data_dir.rglob("*prata_analisada*.json"), key=os.path.getmtime, reverse=True)
        f_simples = sorted(data_dir.rglob("*prata*.json"), key=os.path.getmtime, reverse=True)
        prata_path = f_analisadas[0] if f_analisadas else (f_simples[0] if f_simples else None)

    if not prata_path:
        print(f"[AGENT 4] ❌ Nenhuma Prata encontrada para o ano {ano_alvo}.")
        sys.exit(1)
    print(f"[AGENT 4] 📂 Validando: {prata_path.name}")
    sys.stdout.flush()

    with open(prata_path, "r", encoding="utf-8") as f:
        registros = json.load(f)

    print(f"[AGENT 4] 🔒 Validando {len(registros)} registros com Pydantic...")
    sys.stdout.flush()

    ouro = []
    rejeitados = []

    for i, r in enumerate(registros):
        try:
            # ---> NORMALIZAÇÃO DO NOME <---
            if "deputado" in r:
                r["deputado"] = normalizar_nome_deputado(r["deputado"])
                
            validado = VerbaOuro(**r)
            ouro.append(validado.dict())
        except Exception as e:
            rejeitados.append({"registro": r, "erro": str(e)})

        if (i + 1) % 300 == 0:
            print(f"[AGENT 4] ⚙️ Validados: {i+1}/{len(registros)}...")
            sys.stdout.flush()

    print(f"[AGENT 4] ✅ Aprovados: {len(ouro)} | ❌ Rejeitados: {len(rejeitados)}")
    sys.stdout.flush()

    ano = ouro[0].get("ano", "0000") if ouro else "0000"
    ouro_path = data_dir / "saida" / "ouro" / f"alba_{ano}_ouro.json"
    os.makedirs(ouro_path.parent, exist_ok=True)
    
    with open(ouro_path, "w", encoding="utf-8") as f:
        json.dump(ouro, f, ensure_ascii=False, indent=2)

    if rejeitados:
        rej_path = data_dir / "saida" / "ouro" / f"alba_{ano}_rejeitados.json"
        with open(rej_path, "w", encoding="utf-8") as f:
            json.dump(rejeitados, f, ensure_ascii=False, indent=2)
        print(f"[AGENT 4] ⚠️ Rejeitados salvos: {rej_path.name}")

    print(f"[AGENT 4] 💾 OURO salvo: {ouro_path.name}")
    print("[AGENT 4] [AGENT DONE] ✅ Concluído com sucesso!")
    sys.stdout.flush()

if __name__ == "__main__":
    main()

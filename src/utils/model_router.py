import time
from utils.token_governor import TokenGovernor

# Cadeia de fallback: tenta na ordem, pula se rate limited
FALLBACK_CHAIN = [
    "groq/llama-3.3-70b-versatile",    # preferido (mais capaz)
    "groq/llama-3.1-8b-instant",        # fallback rápido e barato
    "groq/gemma2-9b-it",                # fallback secundário
]

governors = {model: TokenGovernor(model) for model in FALLBACK_CHAIN}

def get_available_model(text: str) -> tuple:
    """
    Retorna o primeiro modelo disponível na chain que tenha tokens livres.
    Se nenhum estiver disponível, aguarda o mais rápido de resetar.
    """
    for model in FALLBACK_CHAIN:
        gov = governors[model]
        can, tokens, wait = gov.can_send(text)
        if can:
            print(f"[MODEL ROUTER] ✅ Usando: {model} ({tokens} tokens estimados)")
            return model, gov
    
    # Nenhum disponível — aguarda o primeiro da chain
    print("[MODEL ROUTER] ⚠️ Todos os modelos em rate limit. Aguardando a rota principal de recarregar...")
    gov = governors[FALLBACK_CHAIN[0]]
    gov.wait_if_needed(text)
    return FALLBACK_CHAIN[0], gov

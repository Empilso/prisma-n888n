import time
from typing import Optional

# Limites por modelo (TPM = tokens per minute)
MODEL_LIMITS = {
    "groq/llama-3.3-70b-versatile": {"tpm": 12000, "provider": "groq"},
    "groq/llama-3.1-8b-instant":    {"tpm": 20000, "provider": "groq"},
    "groq/deepseek-r1-distill-llama-70b": {"tpm": 6000, "provider": "groq"},
    "groq/gemma2-9b-it":            {"tpm": 15000, "provider": "groq"},
}

class TokenGovernor:
    def __init__(self, model: str, safety_buffer: float = 0.80):
        """
        safety_buffer: usa apenas 80% do limite para nunca chegar na borda.
        """
        self.model = model
        self.limit = MODEL_LIMITS.get(model, {}).get("tpm", 10000)
        self.safe_limit = int(self.limit * safety_buffer)
        self.used_this_minute = 0
        self.window_start = time.time()

    def _reset_window_if_needed(self):
        elapsed = time.time() - self.window_start
        if elapsed >= 60:
            self.used_this_minute = 0
            self.window_start = time.time()

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4  # estimativa conservadora

    def can_send(self, text: str) -> tuple[bool, int, float]:
        """
        Retorna: (pode_enviar, tokens_estimados, segundos_para_aguardar)
        """
        self._reset_window_if_needed()
        tokens = self.estimate_tokens(text)
        
        if self.used_this_minute + tokens <= self.safe_limit:
            return True, tokens, 0.0
        
        # Calcula quanto tempo falta para a janela resetar
        elapsed = time.time() - self.window_start
        wait_time = max(0, 61 - elapsed)
        return False, tokens, wait_time

    def register_usage(self, tokens: int):
        self._reset_window_if_needed()
        self.used_this_minute += tokens
        print(f"[TOKEN GOV] Uso atual na LLM {self.model}: {self.used_this_minute}/{self.safe_limit} tokens nesta janela.")

    def wait_if_needed(self, text: str) -> int:
        """Bloqueia automaticamente se necessário. Retorna tokens usados."""
        can, tokens, wait = self.can_send(text)
        if not can:
            print(f"[TOKEN GOV] ⏳ Rate limit iminente. Aguardando {wait:.1f}s na LLM {self.model}...")
            time.sleep(wait + 1)  # +1s de margem
        self.register_usage(tokens)
        return tokens

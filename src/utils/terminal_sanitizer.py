import re

# [AIOX-SANITIZER] Camada 2 — Regex enterprise pré-compilado para performance máxima
_ANSI_ESCAPE_RE = re.compile(
    r'(?:'
    r'\x1B[@-Z\\-_]'           # ESC + byte de controle
    r'|\x1B\[[0-?]*[ -/]*[@-~]' # CSI sequences (cores, cursores)
    r'|\x1B\][^\x07]*\x07'      # OSC sequences
    r'|\x1B[PX^_][^\x1B]*\x1B\\'# DCS/SOS/PM/APC
    r'|\x0F|\x0E'               # Shift In/Out
    r'|\x1B[()][A-Z0-9]'        # Charset selection
    r')'
)

def strip_ansi(text: str) -> str:
    """
    Remove todos os códigos de escape ANSI de uma string, transformando-a 
    em texto limpo, ideal para streaming SSE ou logs puros.
    """
    return _ANSI_ESCAPE_RE.sub('', text)

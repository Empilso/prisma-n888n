import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from utils.terminal_sanitizer import strip_ansi

class TestTerminalSanitizer(unittest.TestCase):
    def test_strip_ansi_basic_colors(self):
        dirty_text = "\u001b[36mTexto em Cyan\u001b[0m"
        clean_text = strip_ansi(dirty_text)
        self.assertEqual(clean_text, "Texto em Cyan")

    def test_strip_ansi_cursor_movement(self):
        dirty_text = "Processando...\u001b[?25l invisible"
        clean_text = strip_ansi(dirty_text)
        self.assertEqual(clean_text, "Processando... invisible")

    def test_strip_ansi_multiple_codes(self):
        dirty_text = "\033[1;31mErro Crítico!\033[0m \x1b[32mSucesso.\x1b[0m"
        clean_text = strip_ansi(dirty_text)
        self.assertEqual(clean_text, "Erro Crítico! Sucesso.")

    def test_clean_text_remains_intact(self):
        clean_text_in = "Nenhum codigo ANSI aqui."
        clean_text_out = strip_ansi(clean_text_in)
        self.assertEqual(clean_text_in, clean_text_out)

if __name__ == '__main__':
    unittest.main()

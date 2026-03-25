import re

def extract_table_only(raw_text: str) -> str:
    """
    Extrai apenas as linhas que são registros da tabela de verbas.
    Descarta menus, rodapés, navegação, links soltos.
    Formato esperado: 'NUMERO | NUMERO | MM/YYYY | NOME | CATEGORIA | R$ X'
    """
    lines = raw_text.split('\n')
    table_lines = []
    in_table = False
    
    for line in lines:
        stripped = line.strip()
        
        # Detecta início da tabela pelos headers
        if 'N° PROCESSO' in stripped or '---|---|---' in stripped:
            in_table = True
            continue
        
        # Detecta fim da tabela (paginação)
        if in_table and ('* Primeiro' in stripped or '* Anterior' in stripped):
            break
        
        # Captura apenas linhas que parecem registros (têm | separando campos)
        if in_table and '|' in stripped and 'R$' in stripped:
            # Limpa o link DETALHES, mantém só os dados
            clean = re.sub(r'\[?\s*DETALHES\s*\]?\(https?://[^\)]+\)', '', stripped)
            clean = re.sub(r'\s+', ' ', clean).strip()
            if clean:
                table_lines.append(clean)
    
    return '\n'.join(table_lines)


def count_tokens_estimate(text: str) -> int:
    """Estimativa rápida: ~4 chars = 1 token (regra geral)"""
    return len(text) // 4

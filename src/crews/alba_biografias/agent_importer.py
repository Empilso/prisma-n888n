#!/usr/bin/env python3
"""
Importador de Biografias ALBA
Importa 149 biografias completas e enriquece tabela politicos
"""
import json
import psycopg2
import psycopg2.extras
from rapidfuzz import fuzz, process
import argparse
from datetime import datetime
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")


DB = dict(host='localhost', port=5432, dbname='prisma_data',
          user='postgres', password=DB_PASSWORD)

def limpar_nome(nome):
    """Remove prefixos e normaliza"""
    nome = nome.upper().strip()
    for prefixo in ['DEPUTADO ', 'DEPUTADA ', 'DEPUTADO(A) ', 'DR. ', 'DRA. ']:
        if nome.startswith(prefixo):
            nome = nome[len(prefixo):]
    return nome

# Mapeamento manual para nomes diferentes
MAPA_NOMES_BIOGRAFIAS = {
    'BIRA CORÔA LULA': 'BIRA COROA',
    'GIKA LOPES LULA': 'GIKA',
    'HASSAN': 'HASSAN DE ZÉ COCÁ',
    'MARCELL DOS ANIMAIS': 'MARCELL MORAES',
    'PASTOR ISIDÓRIO FILHO': 'PASTOR SARGENTO ISIDORIO',
    'TOM É MEU AMIGO': 'PASTOR TOM',
    'VANDO': 'LAERTE DO VANDO',
    'ZÉ NETO LULA': 'ZÉ NETO',
    'JACÓ LULA DA SILVA': 'JACÓ',
    'CARLOS UBALDINO': 'PASTOR UBALDINO',
    'ÂNGELO CORONEL': 'ANGELO CORONEL FILHO',
}

# Mapeamento manual para nomes diferentes
MAPA_NOMES_BIOGRAFIAS = {
    'BIRA CORÔA LULA': 'BIRA COROA',
    'GIKA LOPES LULA': 'GIKA',
    'HASSAN': 'HASSAN DE ZÉ COCÁ',
    'MARCELL DOS ANIMAIS': 'MARCELL MORAES',
    'PASTOR ISIDÓRIO FILHO': 'PASTOR SARGENTO ISIDORIO',
    'TOM É MEU AMIGO': 'PASTOR TOM',
    'VANDO': 'LAERTE DO VANDO',
    'ZÉ NETO LULA': 'ZÉ NETO',
    'JACÓ LULA DA SILVA': 'JACÓ',
    'CARLOS UBALDINO': 'PASTOR UBALDINO',
    'ÂNGELO CORONEL': 'ANGELO CORONEL FILHO',
}

def extrair_formacao(biografia):
    """Extrai formação acadêmica da biografia"""
    if not biografia:
        return []
    
    # Procurar seção de formação
    import re
    match = re.search(r'Formação.*?(?=Atividade|Mandato|$)', biografia, re.IGNORECASE | re.DOTALL)
    if match:
        texto = match.group(0)
        # Extrair cursos
        cursos = []
        for linha in texto.split('\n'):
            if any(x in linha.lower() for x in ['formou', 'graduação', 'pós-graduação', 'mestrado', 'doutorado', 'cursou']):
                cursos.append(linha.strip())
        return cursos
    return []

def extrair_carreira(biografia):
    """Extrai carreira política da biografia"""
    if not biografia:
        return []
    
    import re
    match = re.search(r'Atividade Parlamentar.*?(?=Condecorações|$)', biografia, re.IGNORECASE | re.DOTALL)
    if match:
        texto = match.group(0)
        return [linha.strip() for linha in texto.split('\n') if linha.strip() and len(linha) > 20]
    return []

def buscar_politico_id(nome, parlamentar_id, conn):
    """Busca politico_id por alba_parlamentar_id ou nome"""
    cur = conn.cursor()
    
    # 1. Tentar por alba_parlamentar_id
    cur.execute("""
        SELECT DISTINCT politico_id 
        FROM politicos 
        WHERE alba_parlamentar_id = %s 
        LIMIT 1
    """, (int(parlamentar_id),))
    
    result = cur.fetchone()
    if result:
        return result[0], 100, 'alba_id'
    
    # 2. Buscar todos deputados BA
    cur.execute("""
        SELECT DISTINCT ON (politico_id)
            politico_id, nome_urna, sigla_partido
        FROM politicos
        WHERE uf = 'BA' 
          AND cargo = 'DEPUTADO ESTADUAL'
          AND politico_id IS NOT NULL
        ORDER BY politico_id, ano_eleicao DESC
    """)
    
    deputados = cur.fetchall()
    nomes_bd = {limpar_nome(d[1]): d[0] for d in deputados}
    
    # 3. Aplicar mapeamento manual
    nome_limpo = limpar_nome(nome)
    if nome_limpo in MAPA_NOMES_BIOGRAFIAS:
        nome_mapeado = MAPA_NOMES_BIOGRAFIAS[nome_limpo]
        if nome_mapeado in nomes_bd:
            return nomes_bd[nome_mapeado], 100, 'manual'
    
    # 4. Match exato
    if nome_limpo in nomes_bd:
        return nomes_bd[nome_limpo], 100, 'exato'
    
    # 5. Fuzzy match (threshold 80%)
    resultado = process.extractOne(
        nome_limpo,
        list(nomes_bd.keys()),
        scorer=fuzz.token_sort_ratio
    )
    
    if resultado and resultado[1] >= 80:
        return nomes_bd[resultado[0]], resultado[1], 'fuzzy'
    
    return None, resultado[1] if resultado else 0, 'sem_match'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    
    print("📚 IMPORTADOR DE BIOGRAFIAS ALBA")
    print("=" * 70)
    
    # Carregar dados
    # Fonte unificada em 2026-08-19: era caminho absoluto de pasta de BACKUP
    # pessoal na maquina local (quebrava em qualquer outra maquina).
    arq = BASE_DIR / "data/alba_biografias/dados_brutos/parlamentares_hub_normalized.json"
    data = json.load(open(arq, encoding="utf-8"))
    parlamentares = data['parlamentares']
    
    print(f"\n📂 Carregados {len(parlamentares)} parlamentares")
    print(f"   Qualidade média: {data['estatisticas']['media_qualidade_score']}")
    
    # Conectar
    conn = psycopg2.connect(**DB)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Processar cada parlamentar
    matches = []
    sem_match = []
    
    for p in parlamentares:
        politico_id, score, metodo = buscar_politico_id(
            p['nome_eleitoral'],
            p['parlamentar_id'],
            conn
        )
        
        # Extrair formação e carreira
        formacao = extrair_formacao(p.get('biografia_completa', ''))
        carreira = extrair_carreira(p.get('biografia_completa', ''))
        
        registro = {
            'prisma_id': p['prisma_id'],
            'parlamentar_id': p['parlamentar_id'],
            'politico_id': politico_id,
            'nome_eleitoral': p['nome_eleitoral'],
            'nome_civil': p.get('nome_civil'),
            'biografia_completa': p.get('biografia_completa'),
            'dados_pessoais': json.dumps(p.get('dados_pessoais', {})),
            'mandatos': json.dumps(p.get('mandatos', [])),
            'filiacao_partidaria': json.dumps(p.get('filiacao_partidaria', [])),
            'profissao': p.get('profissao'),
            'data_nascimento': p.get('data_nascimento'),
            'municipio_nascimento': p.get('municipio_nascimento'),
            'uf_nascimento': p.get('uf_nascimento'),
            'sexo': p.get('sexo'),
            'conjuge': p.get('conjuge'),
            'filhos': p.get('filhos'),
            'foto_url': p.get('foto_url'),
            'url_oficial': p.get('url_oficial'),
            'resumo_executivo': p.get('resumo_executivo'),
            'qualidade_score': p.get('qualidade_score'),
            'match_score': score,
            'match_metodo': metodo,
            'formacao_academica': json.dumps(formacao),
            'carreira_politica': json.dumps(carreira)
        }
        
        if politico_id:
            matches.append(registro)
        else:
            sem_match.append(registro)
    
    print(f"\n✅ Matches encontrados: {len(matches)}")
    print(f"❌ Sem match: {len(sem_match)}")
    print(f"📊 Taxa de sucesso: {len(matches)/len(parlamentares)*100:.1f}%")
    
    if args.dry_run:
        print(f"\n[DRY-RUN] Exemplos de matches:")
        for m in matches[:5]:
            print(f"  • {m['nome_eleitoral']:30} → {m['match_metodo']:10} ({m['match_score']:.0f}%)")
        
        if sem_match:
            print(f"\nSem match:")
            for sm in sem_match[:5]:
                print(f"  • {sm['nome_eleitoral']:30} ({sm['match_metodo']})")
        
        conn.close()
        return
    
    # Inserir em alba_biografias
    print(f"\n💾 Inserindo {len(parlamentares)} biografias...")
    
    cur.execute("DELETE FROM alba_biografias")
    
    insert_sql = """
        INSERT INTO alba_biografias (
            prisma_id, parlamentar_id, politico_id, nome_eleitoral, nome_civil,
            biografia_completa, dados_pessoais, mandatos, filiacao_partidaria,
            profissao, data_nascimento, municipio_nascimento, uf_nascimento,
            sexo, conjuge, filhos, foto_url, url_oficial, resumo_executivo,
            qualidade_score, match_score, match_metodo
        ) VALUES (
            %(prisma_id)s, %(parlamentar_id)s, %(politico_id)s, %(nome_eleitoral)s, %(nome_civil)s,
            %(biografia_completa)s, %(dados_pessoais)s::jsonb, %(mandatos)s::jsonb, %(filiacao_partidaria)s::jsonb,
            %(profissao)s, %(data_nascimento)s, %(municipio_nascimento)s, %(uf_nascimento)s,
            %(sexo)s, %(conjuge)s, %(filhos)s, %(foto_url)s, %(url_oficial)s, %(resumo_executivo)s,
            %(qualidade_score)s, %(match_score)s, %(match_metodo)s
        )
    """
    
    cur.executemany(insert_sql, matches + sem_match)
    conn.commit()
    
    print(f"✅ {len(parlamentares)} biografias inseridas")
    
    # Atualizar politicos
    print(f"\n📝 Atualizando politicos...")
    
    cur.execute("""
        UPDATE politicos p
        SET 
            biografia_completa = b.biografia_completa,
            biografia_resumo = b.resumo_executivo,
            dados_pessoais = b.dados_pessoais,
            mandatos_historico = b.mandatos,
            filiacao_partidaria = b.filiacao_partidaria,
            profissao = b.profissao,
            municipio_nascimento = b.municipio_nascimento,
            conjuge = b.conjuge,
            filhos = b.filhos,
            url_oficial_alba = b.url_oficial,
            foto_url = COALESCE(p.foto_url, b.foto_url),
            formacao_academica = %(formacao)s::jsonb,
            carreira_politica = %(carreira)s::jsonb
        FROM alba_biografias b
        WHERE p.politico_id = b.politico_id
          AND b.politico_id IS NOT NULL
    """, {'formacao': json.dumps([]), 'carreira': json.dumps([])})
    
    # Atualizar formação e carreira individualmente
    for m in matches:
        if m['politico_id']:
            cur.execute("""
                UPDATE politicos
                SET 
                    formacao_academica = %s::jsonb,
                    carreira_politica = %s::jsonb
                WHERE politico_id = %s
            """, (m['formacao_academica'], m['carreira_politica'], m['politico_id']))
    
    atualizados = cur.rowcount
    conn.commit()
    
    print(f"✅ {atualizados} deputados enriquecidos")
    
    # Estatísticas
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(biografia_completa) as com_bio,
            COUNT(profissao) as com_profissao,
            COUNT(mandatos_historico) as com_mandatos
        FROM politicos
        WHERE uf = 'BA' AND cargo = 'DEPUTADO ESTADUAL'
          AND politico_id IN (SELECT politico_id FROM alba_biografias WHERE politico_id IS NOT NULL)
    """)
    stats = cur.fetchone()
    
    print(f"\n📊 ESTATÍSTICAS FINAIS")
    print(f"=" * 70)
    print(f"Deputados BA enriquecidos: {stats['total']}")
    print(f"Com biografia completa: {stats['com_bio']}")
    print(f"Com profissão: {stats['com_profissao']}")
    print(f"Com histórico de mandatos: {stats['com_mandatos']}")
    
    conn.close()
    print(f"\n✅ Importação concluída!")

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Importador ALBA Parlamentares
Importa dados dos 72 deputados ALBA e atualiza fotos na tabela politicos
"""
import json
import psycopg2
import psycopg2.extras
from rapidfuzz import fuzz, process
import argparse
from datetime import datetime, timezone
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")


# Mapeamento manual para os 8 que não bateram automaticamente
MAPA_MANUAL = {
    'FABÍOLA MANSUR': 'DRA FABIOLA MANSUR',
    'FABRÍCIO FALCÃO': 'FABRÍCIO',
    'HASSAN': 'HASSAN DE ZÉ COCÁ',
    'LUCIANO SIMÕES FILHO': 'LUCIANO SIMÕES',
    'MATHEUS FERREIRA': 'MATHEUS FIRMATO',
    'RADIOVALDO COSTA': 'RADIOVALDO',
    'ROSEMBERG PINTO': 'ROSEMBERG FREITAS',
    'OSNI CARDOSO': None,  # Não encontrado - verificar manualmente
}

DB = dict(host='localhost', port=5432, dbname='prisma_data',
          user='postgres', password=DB_PASSWORD)

def limpar_nome_alba(nome):
    """Remove prefixos de nome ALBA"""
    nome = nome.upper().strip()
    for prefixo in ['DEPUTADA ', 'DEPUTADO ', 'DEPUTADO(A) ']:
        if nome.startswith(prefixo):
            nome = nome[len(prefixo):]
    return nome

def corrigir_url_foto(url):
    """Corrige URL duplicada da foto ALBA"""
    if url and 'https://albalegis.nopapercloud.com.brhttps://' in url:
        return url.replace('https://albalegis.nopapercloud.com.brhttps://', 'https://')
    return url

def buscar_politico_id(nome_alba, nomes_bd):
    """Busca politico_id por nome com fuzzy matching"""
    nome_limpo = limpar_nome_alba(nome_alba)
    
    # 1. Verificar mapa manual
    if nome_limpo in MAPA_MANUAL:
        nome_mapeado = MAPA_MANUAL[nome_limpo]
        if nome_mapeado is None:
            return None, 0, 'manual_nao_encontrado'
        if nome_mapeado in nomes_bd:
            return nomes_bd[nome_mapeado]['politico_id'], 100, 'manual'
    
    # 2. Match exato
    if nome_limpo in nomes_bd:
        return nomes_bd[nome_limpo]['politico_id'], 100, 'exato'
    
    # 3. Fuzzy match
    resultado = process.extractOne(
        nome_limpo,
        list(nomes_bd.keys()),
        scorer=fuzz.token_sort_ratio
    )
    
    if resultado and resultado[1] >= 85:
        nome_match = resultado[0]
        return nomes_bd[nome_match]['politico_id'], resultado[1], 'fuzzy'
    
    return None, resultado[1] if resultado else 0, 'sem_match'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Simula sem gravar')
    args = parser.parse_args()
    
    print("🏛️  IMPORTADOR ALBA PARLAMENTARES")
    print("=" * 70)
    
    # Carregar dados ALBA
    alba_file = "/home/carneiro888/Documentos/zikualdo/Prisma888/BACK UP/n888n-prisma (copiar 1)/data/parlamentares/parlamentares_ids.json"
    alba_data = json.load(open(alba_file))
    deputados_alba = alba_data['records']
    
    print(f"\n📂 Carregados {len(deputados_alba)} deputados ALBA")
    
    # Conectar ao banco
    conn = psycopg2.connect(**DB)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Buscar deputados BA no banco
    cur.execute("""
        SELECT DISTINCT ON (politico_id)
            politico_id, nome_urna, sigla_partido, ano_eleicao
        FROM politicos
        WHERE uf = 'BA' 
          AND cargo = 'DEPUTADO ESTADUAL'
          AND politico_id IS NOT NULL
        ORDER BY politico_id, ano_eleicao DESC
    """)
    deputados_bd = cur.fetchall()
    
    # Criar índice de nomes
    nomes_bd = {}
    for row in deputados_bd:
        nome_limpo = row['nome_urna'].upper().strip()
        nomes_bd[nome_limpo] = {
            'politico_id': row['politico_id'],
            'nome_urna': row['nome_urna'],
            'partido': row['sigla_partido'],
            'ano': row['ano_eleicao']
        }
    
    print(f"📊 Índice criado com {len(nomes_bd)} deputados BA")
    
    # Processar cada deputado ALBA
    matches = []
    sem_match = []
    
    for dep in deputados_alba:
        politico_id, score, metodo = buscar_politico_id(dep['nome_parlamentar'], nomes_bd)
        
        foto_url = corrigir_url_foto(dep['foto_url'])
        
        registro = {
            'parlamentar_id': dep['parlamentar_id'],
            'autor_id': dep.get('autor_id'),
            'nome_parlamentar': dep['nome_parlamentar'],
            'partido_atual': dep['partido_atual'],
            'status': dep['status'],
            'foto_url': foto_url,
            'url_perfil': dep['url_perfil'],
            'politico_id': politico_id,
            'match_score': score,
            'match_metodo': metodo
        }
        
        if politico_id:
            matches.append(registro)
        else:
            sem_match.append(registro)
    
    print(f"\n✅ Matches encontrados: {len(matches)}")
    print(f"❌ Sem match: {len(sem_match)}")
    
    if args.dry_run:
        print(f"\n[DRY-RUN] Simulação - nada será gravado")
        print(f"\nExemplos de matches:")
        for m in matches[:5]:
            print(f"  • {m['nome_parlamentar']:40} → {m['match_metodo']:10} ({m['match_score']:.0f}%)")
        
        if sem_match:
            print(f"\nSem match:")
            for sm in sem_match:
                print(f"  • {sm['nome_parlamentar']:40} ({sm['match_metodo']})")
        
        conn.close()
        return
    
    # Inserir na tabela alba_parlamentares
    print(f"\n💾 Inserindo {len(deputados_alba)} registros em alba_parlamentares...")
    
    cur.execute("DELETE FROM alba_parlamentares")  # Limpar antes
    
    insert_sql = """
        INSERT INTO alba_parlamentares (
            parlamentar_id, autor_id, nome_parlamentar, partido_atual, status,
            foto_url, url_perfil, politico_id, match_score, match_metodo
        ) VALUES (
            %(parlamentar_id)s, %(autor_id)s, %(nome_parlamentar)s, %(partido_atual)s, %(status)s,
            %(foto_url)s, %(url_perfil)s, %(politico_id)s, %(match_score)s, %(match_metodo)s
        )
    """
    
    cur.executemany(insert_sql, matches + sem_match)
    conn.commit()
    
    print(f"✅ {len(deputados_alba)} registros inseridos")
    
    # Atualizar foto_url em politicos
    print(f"\n📸 Atualizando fotos em politicos...")
    
    cur.execute("""
        UPDATE politicos p
        SET 
            foto_url = a.foto_url,
            alba_parlamentar_id = a.parlamentar_id,
            alba_perfil_url = a.url_perfil
        FROM alba_parlamentares a
        WHERE p.politico_id = a.politico_id
          AND a.politico_id IS NOT NULL
          AND a.match_score >= 85
    """)
    
    atualizados = cur.rowcount
    conn.commit()
    
    print(f"✅ {atualizados} deputados atualizados com foto")
    
    # Relatório final
    cur.execute("""
        SELECT COUNT(*) as total, COUNT(foto_url) as com_foto
        FROM politicos
        WHERE uf = 'BA' AND cargo = 'DEPUTADO ESTADUAL'
          AND politico_id IN (SELECT politico_id FROM alba_parlamentares WHERE politico_id IS NOT NULL)
    """)
    stats = cur.fetchone()
    
    print(f"\n📊 ESTATÍSTICAS FINAIS")
    print(f"=" * 70)
    print(f"Deputados BA com match ALBA: {stats['total']}")
    print(f"Com foto atualizada: {stats['com_foto']}")
    print(f"Taxa de sucesso: {stats['com_foto']/len(matches)*100:.1f}%")
    
    conn.close()
    print(f"\n✅ Importação concluída!")

if __name__ == '__main__':
    main()

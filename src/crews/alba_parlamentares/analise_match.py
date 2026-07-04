#!/usr/bin/env python3
"""
Script de Análise: Match entre ALBA e Politicos
Verifica quantos dos 72 deputados ALBA batem com o banco
"""
import json
import psycopg2
from rapidfuzz import fuzz, process
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD não definido — defina DB_PASSWORD no ambiente ou no .env da raiz do projeto")


# Conexão
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="prisma_data",
    user="postgres",
    password=DB_PASSWORD
)

# Carregar dados ALBA
alba_file = "/home/carneiro888/Documentos/zikualdo/Prisma888/BACK UP/n888n-prisma (copiar 1)/data/parlamentares/parlamentares_ids.json"
alba_data = json.load(open(alba_file))
deputados_alba = alba_data['records']

print(f"📊 ANÁLISE DE MATCH: ALBA vs Banco de Dados")
print(f"=" * 70)
print(f"\n✅ Deputados ALBA: {len(deputados_alba)}")

# Buscar deputados BA no banco (mais recentes)
cur = conn.cursor()
cur.execute("""
    SELECT DISTINCT ON (politico_id)
        politico_id,
        nome_urna,
        nome_completo,
        partido,
        sigla_partido,
        ano_eleicao,
        foto_url
    FROM politicos
    WHERE uf = 'BA' 
      AND cargo = 'DEPUTADO ESTADUAL'
      AND politico_id IS NOT NULL
    ORDER BY politico_id, ano_eleicao DESC
""")
deputados_bd = cur.fetchall()

print(f"✅ Deputados BA no banco: {len(deputados_bd)}")

# Criar índice de nomes do banco
nomes_bd = {}
for row in deputados_bd:
    politico_id, nome_urna, nome_completo, partido, sigla, ano, foto = row
    nome_limpo = nome_urna.upper().strip()
    nomes_bd[nome_limpo] = {
        'politico_id': politico_id,
        'nome_urna': nome_urna,
        'nome_completo': nome_completo,
        'partido': sigla or partido,
        'ano': ano,
        'foto_url': foto
    }

# Função para limpar nome ALBA
def limpar_nome_alba(nome):
    nome = nome.upper().strip()
    # Remover prefixos
    for prefixo in ['DEPUTADA ', 'DEPUTADO ', 'DEPUTADO(A) ']:
        if nome.startswith(prefixo):
            nome = nome[len(prefixo):]
    return nome

# Fazer matching
matches = []
sem_match = []

print(f"\n🔍 ANÁLISE DE MATCHING")
print(f"=" * 70)

for dep_alba in deputados_alba:
    nome_alba = limpar_nome_alba(dep_alba['nome_parlamentar'])
    partido_alba = dep_alba['partido_atual']
    
    # Tentar match exato
    if nome_alba in nomes_bd:
        dep_bd = nomes_bd[nome_alba]
        matches.append({
            'alba': dep_alba,
            'bd': dep_bd,
            'score': 100,
            'metodo': 'exato'
        })
    else:
        # Fuzzy match
        resultado = process.extractOne(
            nome_alba,
            list(nomes_bd.keys()),
            scorer=fuzz.token_sort_ratio
        )
        
        if resultado and resultado[1] >= 85:
            nome_match = resultado[0]
            dep_bd = nomes_bd[nome_match]
            matches.append({
                'alba': dep_alba,
                'bd': dep_bd,
                'score': resultado[1],
                'metodo': 'fuzzy'
            })
        else:
            sem_match.append({
                'alba': dep_alba,
                'melhor_match': resultado[0] if resultado else None,
                'score': resultado[1] if resultado else 0
            })

# Relatório
print(f"\n✅ MATCHES ENCONTRADOS: {len(matches)}")
print(f"❌ SEM MATCH: {len(sem_match)}")
print(f"📊 Taxa de sucesso: {len(matches)/len(deputados_alba)*100:.1f}%")

# Mostrar matches
print(f"\n{'='*70}")
print(f"MATCHES CONFIRMADOS ({len(matches)})")
print(f"{'='*70}")
for i, m in enumerate(matches[:10], 1):
    alba = m['alba']['nome_parlamentar']
    bd = m['bd']['nome_urna']
    partido_alba = m['alba']['partido_atual']
    partido_bd = m['bd']['partido']
    score = m['score']
    metodo = m['metodo']
    tem_foto = '📸' if m['bd']['foto_url'] else '❌'
    
    print(f"{i:2}. {alba:35} → {bd:25} | {partido_alba:10} vs {partido_bd:10} | {score:3.0f}% | {metodo:5} | {tem_foto}")

if len(matches) > 10:
    print(f"... e mais {len(matches)-10} matches")

# Mostrar sem match
if sem_match:
    print(f"\n{'='*70}")
    print(f"SEM MATCH ({len(sem_match)})")
    print(f"{'='*70}")
    for i, sm in enumerate(sem_match, 1):
        alba = sm['alba']['nome_parlamentar']
        melhor = sm['melhor_match'] or '—'
        score = sm['score']
        print(f"{i:2}. {alba:40} | Melhor: {melhor:25} ({score:.0f}%)")

# Estatísticas de fotos
com_foto = sum(1 for m in matches if m['bd']['foto_url'])
print(f"\n{'='*70}")
print(f"ESTATÍSTICAS")
print(f"{'='*70}")
print(f"Matches com foto no BD: {com_foto}/{len(matches)}")
print(f"Matches sem foto no BD: {len(matches)-com_foto}/{len(matches)}")
print(f"Fotos ALBA disponíveis: {len(deputados_alba)}/72")

conn.close()
print(f"\n✅ Análise concluída!")

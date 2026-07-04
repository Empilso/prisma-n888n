#!/bin/bash
# Pipeline completo: espera 2022_BR terminar, carrega 2014, 2018, 2016
set -e
PROJ=/home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma
CREWS=$PROJ/src/crews/tse_receitas_campanha
PRATA=$PROJ/data/tse_receitas_campanha/prata
VENV=/home/carneiro888/Documentos/zikualdo/Prisma888/PRISMA-DADOS2/.venv/bin/python3
LOG=$PROJ/data/tse_receitas_campanha/pipeline.log

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# -------------------------------------------------------
# FASE 1 — aguarda Agent C 2022_BR (processo em background)
# -------------------------------------------------------
log "Aguardando Agent C 2022_BR terminar..."
AGENT_C_OUT=/tmp/claude-1000/-home-carneiro888-Documentos-zikualdo-Prisma888-PRISMA-DADOS2/3d32394e-e018-4344-9844-b921a8d5613e/tasks/bb35jyh1n.output
until grep -qE "concluída|ERRO|Error|falhou" "$AGENT_C_OUT" 2>/dev/null; do
    N=$(PGPASSWORD="${DB_PASSWORD:?defina DB_PASSWORD no ambiente ou .env}" psql -h localhost -U postgres -d prisma_data -t -c "SELECT COUNT(*) FROM receitas_campanha WHERE ano_eleicao=2022;" 2>&1 | tr -d ' \n')
    log "  2022: $N registros no banco..."
    sleep 20
done
log "2022_BR pronto!"

# -------------------------------------------------------
# FASE 2 — carregar 2014
# -------------------------------------------------------
log "=== CARREGANDO 2014 ==="
for f in $(ls "$PRATA"/receitas_2014_*_prata.json | sort); do
    log "  $f"
    $VENV "$CREWS/agent_c_loader.py" --prata "$f" 2>&1 | tee -a "$LOG"
done
log "2014 concluído."

# -------------------------------------------------------
# FASE 3 — carregar 2018
# -------------------------------------------------------
log "=== CARREGANDO 2018 ==="
for f in $(ls "$PRATA"/receitas_2018_*_prata.json | sort); do
    log "  $f"
    $VENV "$CREWS/agent_c_loader.py" --prata "$f" 2>&1 | tee -a "$LOG"
done
log "2018 concluído."

# -------------------------------------------------------
# FASE 4 — 2016: Agent A (bronze dos ZIPs por UF)
# -------------------------------------------------------
log "=== 2016 AGENT A — extraindo bronze dos ZIPs ==="
$VENV "$CREWS/agent_a_coletor.py" --ano 2016 2>&1 | tee -a "$LOG"
log "2016 bronze concluído."

# -------------------------------------------------------
# FASE 5 — 2016: Agent B (bronze → prata)
# -------------------------------------------------------
log "=== 2016 AGENT B — normalizando ==="
for f in $(ls "$PROJ/data/tse_receitas_campanha/bronze/receitas_2016_"*"_bronze.json" | sort); do
    log "  $f"
    $VENV "$CREWS/agent_b_normalizador.py" --bronze "$f" 2>&1 | tee -a "$LOG"
done
log "2016 prata concluído."

# -------------------------------------------------------
# FASE 6 — 2016: Agent C (prata → DB)
# -------------------------------------------------------
log "=== 2016 AGENT C — carregando no banco ==="
for f in $(ls "$PRATA"/receitas_2016_*_prata.json | sort); do
    log "  $f"
    $VENV "$CREWS/agent_c_loader.py" --prata "$f" 2>&1 | tee -a "$LOG"
done
log "2016 concluído."

# -------------------------------------------------------
# VERIFICAÇÃO FINAL
# -------------------------------------------------------
log "=== VERIFICAÇÃO FINAL ==="
PGPASSWORD="${DB_PASSWORD:?defina DB_PASSWORD no ambiente ou .env}" psql -h localhost -U postgres -d prisma_data -c "
SELECT ano_eleicao,
       COUNT(*)                                           AS total,
       COUNT(politico_id)                                 AS linkados,
       ROUND(COUNT(politico_id)::numeric/COUNT(*)*100,1)  AS pct,
       SUM(valor)::bigint                                 AS total_RS
FROM receitas_campanha
GROUP BY ano_eleicao ORDER BY ano_eleicao;
" 2>&1 | tee -a "$LOG"

log "=== PIPELINE CONCLUÍDO ==="

#!/bin/bash
set -e
PROJ=/home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma
CREWS=$PROJ/src/crews/tse_receitas_campanha
DATA=$PROJ/data/tse_receitas_campanha
PY=/home/carneiro888/Documentos/zikualdo/Prisma888/PRISMA888FORBES/backend/.venv/bin/python3
LOG=$DATA/pipeline_2016_2018.log
export DB_PASSWORD=$(grep "^DB_PASSWORD=" "$PROJ/.env" | cut -d= -f2- | tr -d '"' | tr -d "'")

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

cd "$PROJ"

for ANO in 2016 2018; do
    log "=== ANO $ANO — Agent A (coleta) ==="
    $PY "$CREWS/agent_a_coletor.py" --ano $ANO 2>&1 | tee -a "$LOG"

    log "=== ANO $ANO — Agent B (normaliza) ==="
    for f in "$DATA"/bronze/receitas_${ANO}_*_bronze.json; do
        [ -f "$f" ] || continue
        $PY "$CREWS/agent_b_normalizador.py" --bronze "$f" 2>&1 | tee -a "$LOG"
    done

    log "=== ANO $ANO — Agent C (carga) ==="
    for f in "$DATA"/prata/receitas_${ANO}_*_prata.json; do
        [ -f "$f" ] || continue
        $PY "$CREWS/agent_c_loader.py" --prata "$f" 2>&1 | tee -a "$LOG"
    done

    log "=== ANO $ANO CONCLUÍDO ==="
done

log "=== VERIFICAÇÃO FINAL ==="
PGPASSWORD="$DB_PASSWORD" psql -h localhost -U postgres -d prisma_data -c "
SELECT ano_eleicao,
       COUNT(*)                                           AS total,
       COUNT(politico_id)                                 AS linkados,
       ROUND(COUNT(politico_id)::numeric/COUNT(*)*100,1)  AS pct
FROM receitas_campanha
GROUP BY ano_eleicao ORDER BY ano_eleicao;
" 2>&1 | tee -a "$LOG"

log "=== PIPELINE 2016/2018 CONCLUÍDO ==="

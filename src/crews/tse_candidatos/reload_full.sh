#!/bin/bash
set -e
PROJ=/home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma
CREWS=$PROJ/src/crews/tse_candidatos
DATA=$PROJ/data/raw/tse/candidatos
PY=/home/carneiro888/.pyenv/shims/python3
LOG=$DATA/reload_full.log
export DB_PASSWORD=$(grep "^DB_PASSWORD=" "$PROJ/.env" | cut -d= -f2- | tr -d '"' | tr -d "'")

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

cd "$PROJ"

for ANO in 2008 2010 2012 2016; do
    log "=== ANO $ANO — Agent A (coleta TODOS as UFs) ==="
    $PY "$CREWS/agent_a_coletor.py" --ano $ANO --todos-ufs 2>&1 | tee -a "$LOG"

    log "=== ANO $ANO — Agent B (normaliza) ==="
    f="$DATA/bronze/candidatos_${ANO}_TODOS_bronze.json"
    if [ -f "$f" ]; then
        $PY "$CREWS/agent_b_normalizador.py" --bronze "$f" 2>&1 | tee -a "$LOG"
    else
        log "AVISO: bronze TODOS nao encontrado pra $ANO"
    fi

    log "=== ANO $ANO — Agent C (carga) ==="
    pf="$DATA/prata/candidatos_${ANO}_TODOS_prata.json"
    if [ -f "$pf" ]; then
        $PY "$CREWS/agent_c_loader.py" --prata "$pf" 2>&1 | tee -a "$LOG"
    else
        log "AVISO: prata TODOS nao encontrado pra $ANO"
    fi

    log "=== ANO $ANO CONCLUÍDO ==="
done

log "=== RECARGA COMPLETA CONCLUÍDA ==="

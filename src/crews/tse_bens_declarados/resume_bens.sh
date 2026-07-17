#!/bin/bash
set -e
PROJ=/home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma
CREWS=$PROJ/src/crews/tse_bens_declarados
DATA=$PROJ/data/tse_bens_declarados
PY=/home/carneiro888/Documentos/zikualdo/Prisma888/PRISMA888FORBES/backend/.venv/bin/python3
LOG=$DATA/resume.log
export DB_PASSWORD=$(grep "^DB_PASSWORD=" "$PROJ/.env" | cut -d= -f2- | tr -d '"' | tr -d "'")

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

cd "$PROJ"

log "=== RETOMADA 2020 — recarregar SC/SE/SP/TO (Agent C) ==="
for UF in SC SE SP TO; do
    f="$DATA/prata/bens_2020_${UF}_prata.json"
    if [ -f "$f" ]; then
        $PY "$CREWS/agent_c_loader.py" --prata "$f" 2>&1 | tee -a "$LOG"
    else
        log "AVISO: prata não encontrado para 2020 $UF"
    fi
done

log "=== ANO 2022 — Agent A (coleta, do zero) ==="
$PY "$CREWS/agent_a_coletor.py" --ano 2022 2>&1 | tee -a "$LOG"

log "=== ANO 2022 — Agent B (normaliza) ==="
for f in "$DATA"/bronze/bens_2022_*_bronze.json; do
    [ -f "$f" ] || continue
    $PY "$CREWS/agent_b_normalizador.py" --bronze "$f" 2>&1 | tee -a "$LOG"
done

log "=== ANO 2022 — Agent C (carga) ==="
for f in "$DATA"/prata/bens_2022_*_prata.json; do
    [ -f "$f" ] || continue
    $PY "$CREWS/agent_c_loader.py" --prata "$f" 2>&1 | tee -a "$LOG"
done

log "=== ANO 2022 CONCLUÍDO ==="

log "=== RESOLVENDO IDENTIDADE FINAL (todas as linhas pendentes) ==="
PGPASSWORD="$DB_PASSWORD" psql -h localhost -U postgres -d prisma_data -c "
UPDATE bens_declarados b SET politico_id = p.politico_id, pessoa_id = p.pessoa_id
FROM politicos p
WHERE p.sq_candidato = b.sq_candidato AND p.ano_eleicao = b.ano_eleicao
  AND b.politico_id IS NULL;
" 2>&1 | tee -a "$LOG"

log "=== VERIFICAÇÃO FINAL (Agent V) ==="
$PY "$CREWS/agent_v_verificador.py" 2>&1 | tee -a "$LOG"

log "=== RETOMADA CONCLUÍDA ==="

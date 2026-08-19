#!/bin/bash
# run_crew.sh <crew_id> — roda os estagios configurados em crews_config.json
# pra <crew_id>, em sequencia, parando no primeiro erro. Log estruturado,
# falha registrada em arquivo separado pra digest diario nunca passar batido.
#
# v2 (2026-08-19): alem do exit code, verifica o CONTEUDO de cada etapa.
# Achado real no mesmo dia: senado_votacoes e tse_bens_declarados devolveram
# exit 0 mesmo com TODAS as chamadas externas falhando (fonte descontinuada
# / CDN bloqueado) -- "sucesso" mascarando falha total. Exit code sozinho
# NAO basta pra confiar numa crew de terceiro. Isso e generico pra TODAS as
# crews, nao um patch por crew.
set -uo pipefail

PROJ=/opt/prisma-n888n
CONFIG="$PROJ/automacao/crews_config.json"
LOGDIR=/var/log/prisma-etl
FAILLOG=/var/log/prisma-etl/crew_failures.log
SUSPEITALOG=/var/log/prisma-etl/crew_suspeitas.log
PY=/opt/prisma-n888n/.venv/bin/python3
CREW="${1:?uso: run_crew.sh <crew_id>}"
TS=$(date '+%Y%m%d_%H%M%S')
LOG="$LOGDIR/${CREW}_auto_${TS}.log"

mkdir -p "$LOGDIR"
export DB_PASSWORD=$(grep '^DB_PASSWORD=' /opt/prisma888/backend/.env 2>/dev/null | cut -d= -f2-)

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "=== INICIO crew=$CREW ==="

STAGES=$($PY -c "
import json, sys
cfg = json.load(open('$CONFIG'))
c = cfg.get('$CREW')
if not c:
    sys.exit(1)
for stage in c['stages']:
    print(stage['script'] + '|' + ' '.join(stage.get('args', [])))
" 2>>"$LOG")

if [ -z "$STAGES" ]; then
    log "ERRO: crew '$CREW' nao encontrada em $CONFIG"
    echo "$(date -Iseconds) | $CREW | CONFIG_NAO_ENCONTRADA" >> "$FAILLOG"
    exit 1
fi

CREWDIR="$PROJ/src/crews/$CREW"
FALHOU=0
SUSPEITA=0
while IFS='|' read -r script args; do
    log "--- rodando $script $args ---"
    STAGE_OUT=$(mktemp)
    timeout 5400 $PY "$CREWDIR/$script" $args >"$STAGE_OUT" 2>&1
    rc=$?
    cat "$STAGE_OUT" >> "$LOG"

    if [ $rc -ne 0 ]; then
        log "FALHOU: $script (exit=$rc)"
        echo "$(date -Iseconds) | $CREW | $script | exit=$rc | log=$LOG" >> "$FAILLOG"
        FALHOU=1
        rm -f "$STAGE_OUT"
        break
    fi

    # Checagem de conteudo: exit 0 nao significa que funcionou de verdade.
    N_FALHAS=$(grep -c "❌" "$STAGE_OUT" 2>/dev/null)
    VAZIO=$(grep -ciE "Nenhum (Bronze|Prata|arquivo) encontrado|\\[VAZIO\\]|Total bronze: 0|0 upserts|0 registros" "$STAGE_OUT" 2>/dev/null)
    if [ "$VAZIO" -gt 0 ] || [ "$N_FALHAS" -ge 3 ]; then
        log "⚠️  SUSPEITA em $script: exit=0 mas $N_FALHAS marcador(es) de falha / vazio=$VAZIO — ver $SUSPEITALOG"
        echo "$(date -Iseconds) | $CREW | $script | falhas_no_conteudo=$N_FALHAS | vazio=$VAZIO | log=$LOG" >> "$SUSPEITALOG"
        SUSPEITA=1
    fi
    rm -f "$STAGE_OUT"
    log "OK: $script"
done <<< "$STAGES"

if [ $FALHOU -eq 0 ] && [ $SUSPEITA -eq 0 ]; then
    log "=== FIM crew=$CREW — SUCESSO ==="
elif [ $FALHOU -eq 0 ] && [ $SUSPEITA -eq 1 ]; then
    log "=== FIM crew=$CREW — SUCESSO COM SUSPEITA, conferir $SUSPEITALOG ==="
else
    log "=== FIM crew=$CREW — FALHOU, ver $FAILLOG ==="
fi
exit $FALHOU

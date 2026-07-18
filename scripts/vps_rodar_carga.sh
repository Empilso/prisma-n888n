#!/bin/bash
# Runner de cargas n888n na VPS — prioridade baixa pra não atrapalhar o app.
# Uso: bash rodar_carga.sh <crew> [entry.py] <args...>
#   ex: bash rodar_carga.sh tse_votos_municipio --ano 2018 --uf 7ufs
#   ex: bash rodar_carga.sh tse_despesas_campanha agent_a_coletor.py --ano 2020 --ufs SP BA
# Sem entry explícito usa main.py. O venv do Forbes entra no PATH, então
# scripts que chamam `python` pelado também funcionam.
#
# Vigia (2026-07-18): cada execução vira uma linha em data_pipeline_runs —
# início, heartbeat por minuto e fechamento com rc + erros contados no log.
# Motivo: a fila SICONFI de 18/07 falhou 100% silenciosa (33k erros, rc=0);
# com o contrato, o painel mostra isso em vermelho em minutos. Toda escrita
# do Vigia é best-effort (|| true) — vigia caído NUNCA derruba carga.
set -u
CREW="$1"; shift
ENTRY=main.py
case "${1:-}" in
  *.py|*.sh) ENTRY="$1"; shift ;;
esac
PY=/opt/prisma888/backend/.venv/bin/python
export PATH="$(dirname "$PY"):$PATH"
LOG="/var/log/prisma-etl/${CREW}_$(date +%Y%m%d_%H%M).log"
sudo -n mkdir -p /var/log/prisma-etl && sudo -n chown prisma:prisma /var/log/prisma-etl
exec 9>"/tmp/etl_${CREW}.lock"
flock -n 9 || { echo "carga de $CREW já rodando"; exit 0; }
set -a; source /opt/prisma888/backend/.env; set +a
cd "/opt/prisma-n888n/src/crews/$CREW"

# ── Vigia: abertura do run ──────────────────────────────────────────────────
RUN_ID="${CREW}_$(date +%Y%m%d_%H%M%S)_$$"
ARGS_STR="$*"
vigia(){ PGPASSWORD="${DB_PASSWORD:-}" psql -h localhost -U postgres -d prisma_data -qtA -c "$1" >/dev/null 2>&1 || true; }
vigia "INSERT INTO data_pipeline_runs (run_id, source_id, crew_id, status, rule_version, metadata)
       VALUES ('$RUN_ID', '$CREW', '$CREW', 'EXTRAINDO', 'runner-v1',
               jsonb_build_object('entry', '$ENTRY', 'args', \$vg\$$ARGS_STR\$vg\$, 'log', '$LOG', 'host', 'vps'))"
LOG_OFFSET=$(stat -c%s "$LOG" 2>/dev/null || echo 0)
( while kill -0 $$ 2>/dev/null; do
    vigia "UPDATE data_pipeline_runs SET heartbeat_at=clock_timestamp(), updated_at=clock_timestamp() WHERE run_id='$RUN_ID' AND finished_at IS NULL"
    sleep 60
  done ) & HB_PID=$!

echo "[$(date "+%F %T")] ▶ $CREW $ENTRY $* (run=$RUN_ID)" >> "$LOG"
case "$ENTRY" in
  *.sh) ionice -c3 nice -n19 bash "$ENTRY" "$@" >> "$LOG" 2>&1 ;;
  *)    ionice -c3 nice -n19 "$PY" "$ENTRY" "$@" >> "$LOG" 2>&1 ;;
esac
RC=$?
echo "[$(date "+%F %T")] ■ fim rc=$RC" >> "$LOG"
kill "$HB_PID" 2>/dev/null || true

# ── Vigia: fechamento — conta erros SÓ do trecho desta execução ─────────────
ERROS=$(tail -c +"$((LOG_OFFSET + 1))" "$LOG" 2>/dev/null | tr '\r' '\n' | grep -c "❌\|Traceback\|ERROR" || true)
REGISTROS=$(tail -c +"$((LOG_OFFSET + 1))" "$LOG" 2>/dev/null | tr '\r' '\n' | grep -oP 'registros[= ]+\K[0-9]+' | tail -1 || true)
if [ "$RC" -ne 0 ]; then STATUS=ERRO
elif [ "${ERROS:-0}" -gt 0 ]; then STATUS=PARCIAL
else STATUS=CERTIFICADO   # determinístico: rc=0 E zero linhas de erro no log
fi
vigia "UPDATE data_pipeline_runs SET
         status='$STATUS',
         records_extracted=$( [ -n "${REGISTROS:-}" ] && echo "$REGISTROS" || echo NULL ),
         error_message=$( [ "${ERROS:-0}" -gt 0 ] && echo "'$ERROS linhas de erro no log'" || echo NULL ),
         finished_at=clock_timestamp(), updated_at=clock_timestamp()
       WHERE run_id='$RUN_ID'"
exit "$RC"

#!/bin/bash
# Runner de cargas n888n na VPS — prioridade baixa pra não atrapalhar o app.
# Uso: bash rodar_carga.sh <crew> <args...>   ex: bash rodar_carga.sh tse_votos_municipio --ano 2018 --uf 7ufs
set -u
CREW="$1"; shift
PY=/opt/prisma888/backend/.venv/bin/python
LOG="/var/log/prisma-etl/${CREW}_$(date +%Y%m%d_%H%M).log"
sudo -n mkdir -p /var/log/prisma-etl && sudo -n chown prisma:prisma /var/log/prisma-etl
exec 9>"/tmp/etl_${CREW}.lock"
flock -n 9 || { echo "carga de $CREW já rodando"; exit 0; }
set -a; source /opt/prisma888/backend/.env; set +a
cd "/opt/prisma-n888n/src/crews/$CREW"
echo "[$(date "+%F %T")] ▶ $CREW $*" >> "$LOG"
ionice -c3 nice -n19 "$PY" main.py "$@" >> "$LOG" 2>&1
echo "[$(date "+%F %T")] ■ fim rc=$?" >> "$LOG"

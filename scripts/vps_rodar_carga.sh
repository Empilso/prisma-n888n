#!/bin/bash
# Runner de cargas n888n na VPS — prioridade baixa pra não atrapalhar o app.
# Uso: bash rodar_carga.sh <crew> [entry.py] <args...>
#   ex: bash rodar_carga.sh tse_votos_municipio --ano 2018 --uf 7ufs
#   ex: bash rodar_carga.sh tse_despesas_campanha agent_a_coletor.py --ano 2020 --ufs SP BA
# Sem entry explícito usa main.py. O venv do Forbes entra no PATH, então
# scripts que chamam `python` pelado também funcionam.
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
echo "[$(date "+%F %T")] ▶ $CREW $ENTRY $*" >> "$LOG"
case "$ENTRY" in
  *.sh) ionice -c3 nice -n19 bash "$ENTRY" "$@" >> "$LOG" 2>&1 ;;
  *)    ionice -c3 nice -n19 "$PY" "$ENTRY" "$@" >> "$LOG" 2>&1 ;;
esac
echo "[$(date "+%F %T")] ■ fim rc=$?" >> "$LOG"

#!/bin/bash
# Carga TSE 2018 (7 UFs) em modo madrugada — prioridade mínima de CPU e disco.
# Agendada via cron (02:30). Idempotente: retoma de onde parou (upsert).
# Quando as 7 UFs estiverem completas, remove a própria entrada do cron e para.
# Log: /tmp/tse_votos_2018_7ufs.log | Lock: /tmp/tse_votos_2018.lock

set -u
CREW_DIR="/home/carneiro888/Documentos/zikualdo/Prisma888/n888n-prisma/src/crews/tse_votos_municipio"
ENV_FILE="/home/carneiro888/Documentos/zikualdo/Prisma888/PRISMA888FORBES/backend/.env"
LOG="/tmp/tse_votos_2018_7ufs.log"
LOCK="/tmp/tse_votos_2018.lock"
UFS_ESPERADAS=7

# --- lock: nunca rodar duas cargas ao mesmo tempo ---
exec 9>"$LOCK"
if ! flock -n 9; then
    echo "[$(date '+%F %T')] já existe carga rodando — abortando esta instância" >> "$LOG"
    exit 0
fi

set -a; source "$ENV_FILE"; set +a

ufs_completas() {
    PGPASSWORD="$DB_PASSWORD" psql -h localhost -U postgres -d prisma_data -tAc \
        "SELECT COUNT(*) FROM tse_votos_cache_status WHERE ano_eleicao=2018 AND status='pronto';" 2>/dev/null | tr -d ' '
}

remover_do_cron() {
    crontab -l 2>/dev/null | grep -v "carga_2018_madrugada.sh" | crontab -
    echo "[$(date '+%F %T')] 🏁 2018 COMPLETO (7 UFs) — agendamento removido do cron" >> "$LOG"
}

# Já terminou numa noite anterior? Só desagenda e sai.
if [ "$(ufs_completas)" = "$UFS_ESPERADAS" ]; then
    remover_do_cron
    exit 0
fi

echo "[$(date '+%F %T')] ▶ iniciando/retomando carga 2018 (modo madrugada, ionice idle + nice 19)" >> "$LOG"
cd "$CREW_DIR"
ionice -c3 nice -n19 python3 main.py --ano 2018 --uf 7ufs >> "$LOG" 2>&1
RC=$?
echo "[$(date '+%F %T')] ■ carga encerrou com código $RC" >> "$LOG"

# Terminou tudo? Desagenda.
if [ "$(ufs_completas)" = "$UFS_ESPERADAS" ]; then
    remover_do_cron
fi

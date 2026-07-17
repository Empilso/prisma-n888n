#!/bin/bash
# Painel de status das cargas ETL na VPS. Uso: bash /opt/prisma-n888n/status_cargas.sh
set -a; source /opt/prisma888/backend/.env; set +a
echo "════════ CARGAS RODANDO AGORA ════════"
pgrep -af "main.py --ano" | sed "s|/opt/prisma888/backend/.venv/bin/python ||" || echo "(nenhuma)"
echo
echo "════════ STATUS POR UF (tse_votos_cache_status) ════════"
PGPASSWORD="$DB_PASSWORD" psql -h localhost -U postgres -d prisma_data -c \
  "SELECT ano_eleicao AS ano, sg_uf AS uf, status, to_char(total_linhas, 'FM999G999G999') AS registros,
          to_char(iniciado_em, 'DD/MM HH24:MI') AS inicio, to_char(concluido_em, 'DD/MM HH24:MI') AS fim
   FROM tse_votos_cache_status ORDER BY ano_eleicao DESC, sg_uf;" 2>/dev/null
echo "════════ ÚLTIMAS LINHAS DO LOG ════════"
tail -8 $(ls -t /var/log/prisma-etl/*.log 2>/dev/null | head -1) 2>/dev/null || echo "(sem logs)"

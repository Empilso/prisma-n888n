#!/bin/bash
# Expansão PNCP: coleta anos 2022 e 2023 para todos os municípios.
# 2024 e 2025 já coletados (BA). Este script busca anos anteriores.
# Rode: bash scripts/expand_pncp.sh > /tmp/pncp_expand.log 2>&1 &

set -euo pipefail

CREW_DIR="$(cd "$(dirname "$0")/.." && pwd)/src/crews/pncp_contratos"
LOG="/tmp/pncp_expand.log"

export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=prisma_data
export DB_USER=postgres
: "${DB_PASSWORD:?defina DB_PASSWORD no ambiente ou .env}"
export DB_PASSWORD

echo "[$(date '+%H:%M:%S')] === PNCP EXPANSÃO 2021-2023 ===" | tee -a "$LOG"

run_abc() {
    local ano="$1"
    echo "[$(date '+%H:%M:%S')] --- PNCP $ano ---" | tee -a "$LOG"

    python "$CREW_DIR/agent_a_coletor.py" --ano "$ano" 2>&1 | tee -a "$LOG"
    python "$CREW_DIR/agent_b_normalizador.py" --todos 2>&1 | tee -a "$LOG"
    python "$CREW_DIR/agent_c_loader.py" --todos 2>&1 | tee -a "$LOG"

    echo "[$(date '+%H:%M:%S')] ✅ PNCP $ano carregado." | tee -a "$LOG"
}

run_abc 2023
run_abc 2022
run_abc 2021

echo "[$(date '+%H:%M:%S')] === PNCP CONCLUÍDO ===" | tee -a "$LOG"

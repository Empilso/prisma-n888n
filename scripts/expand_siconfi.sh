#!/bin/bash
# Expansão SICONFI: RREO capitais + UFs para 2019-2023
# 2024 já está no banco — skip automático (bronze existe).
# Rode em background: bash scripts/expand_siconfi.sh > /tmp/siconfi_expand.log 2>&1 &

set -euo pipefail

CREW_DIR="$(cd "$(dirname "$0")/.." && pwd)/src/crews/siconfi_universal"
LOG="/tmp/siconfi_expand.log"

export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=prisma_data
export DB_USER=postgres
: "${DB_PASSWORD:?defina DB_PASSWORD no ambiente ou .env}"
export DB_PASSWORD

echo "[$(date '+%H:%M:%S')] === SICONFI EXPANSÃO 2019-2023 ===" | tee -a "$LOG"

run_abc() {
    local doc="$1"
    local ano="$2"
    local tipo="$3"
    local extra="${4:-}"

    echo "[$(date '+%H:%M:%S')] --- $doc $ano $tipo $extra ---" | tee -a "$LOG"

    python "$CREW_DIR/agent_a_coletor.py" \
        --documento "$doc" --ano "$ano" --entes-tipo "$tipo" $extra \
        --workers 4 2>&1 | tee -a "$LOG"

    python "$CREW_DIR/agent_b_normalizador.py" \
        --documento "$doc" --todos 2>&1 | tee -a "$LOG"

    python "$CREW_DIR/agent_c_loader.py" \
        --documento "$doc" --todos 2>&1 | tee -a "$LOG"

    echo "[$(date '+%H:%M:%S')] ✅ $doc $ano $tipo carregado." | tee -a "$LOG"
}

# ── 1. RREO capitais 2019-2023 ───────────────────────────────────────────────
for ano in 2023 2022 2021 2020 2019; do
    run_abc RREO "$ano" municipio "--capitais-only"
done

# ── 2. RREO UFs 2019-2023 ────────────────────────────────────────────────────
for ano in 2023 2022 2021 2020 2019; do
    run_abc RREO "$ano" uf
done

# ── 3. RGF UFs 2019-2023 (pessoal/endividamento para governadores) ───────────
for ano in 2023 2022 2021 2020 2019; do
    run_abc RGF "$ano" uf
done

echo "[$(date '+%H:%M:%S')] === CONCLUÍDO ===" | tee -a "$LOG"

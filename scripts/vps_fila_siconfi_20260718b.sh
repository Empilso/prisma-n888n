#!/bin/bash
# Retomada SICONFI municípios — 2026-07-18b.
# A fila vps_fila_prefeito_20260718.sh falhou 100% no SICONFI por bug de tipo
# no --anexo (string × {anexo:02d}) — corrigido em agent_a_coletor.py.
# Votos 2020/2016 daquela fila JÁ concluíram — aqui é só o SICONFI.
set -u
R=/opt/prisma-n888n/rodar_carga.sh
LOG=/var/log/prisma-etl/fila_siconfi_$(date +%Y%m%d_%H%M).log
say(){ echo "[$(date "+%F %T")] $*" >> "$LOG"; }
ANEXOS="1 2 3 6"
ANOS="2025 2026 2024 2023 2022 2021"

say "fila siconfi retomada iniciada"
for ano in $ANOS; do
  tipo=municipio
  case "$ano" in 2025|2026) tipo=todos ;; esac
  flock /tmp/etl_siconfi_universal.lock true
  for anexo in $ANEXOS; do
    say "siconfi: RREO $ano anexo $anexo entes=$tipo (coleta)"
    bash "$R" siconfi_universal agent_a_coletor.py \
      --documento RREO --ano "$ano" --entes-tipo "$tipo" --anexo "$anexo" --workers 4
  done
  say "siconfi: RREO $ano normalizar + carregar"
  bash "$R" siconfi_universal agent_b_normalizador.py --documento RREO --todos
  bash "$R" siconfi_universal agent_c_loader.py --documento RREO --todos
  say "siconfi: RREO $ano ok — disco: $(df -h /opt | tail -1 | awk '{print $4" livres"}')"
done
say "fila siconfi retomada concluida"

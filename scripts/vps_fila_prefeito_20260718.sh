#!/bin/bash
# Fila "template prefeito 100%" — 2026-07-18.
# Contexto: auditoria QI220 do dossiê PREFEITO (Forbes,
# .context/AUDITORIA_TEMPLATE_PREFEITO_2026-07-18.md) achou 2 gaps de cobertura:
#   V1 Gestão Fiscal — siconfi_rreo só tem UFs+capitais; municípios comuns vazios.
#   V2 Mapa Eleitoral — votos 2018/2022/2024 já fecharam nas 27 UFs (fila de
#      17/07); faltam os anos MUNICIPAIS 2020 e 2016 nas 20 UFs restantes.
# Ordem pensada por valor: votos 2020 (rápido, fecha o seletor multi-ano do mapa)
# → SICONFI RREO municípios nos anexos que o backend consome (1,2,3,6 — ver
# execucao_municipal.py), ano mais recente primeiro → votos 2016 por último.
# Lições da fila de 17/07 aplicadas: flock BLOQUEANTE antes de cada crew que
# pode estar com lock ocupado; nada de flock -n em fila.
set -u
R=/opt/prisma-n888n/rodar_carga.sh
LOG=/var/log/prisma-etl/fila_prefeito_$(date +%Y%m%d_%H%M).log
say(){ echo "[$(date "+%F %T")] $*" >> "$LOG"; }
VINTE="AC AL AM AP CE DF ES GO MA MS MT PA PB PI RN RO RR SC SE TO"
# Anexos RREO que o Forbes lê hoje (execucao_municipal.py): 1 (balanço),
# 2 (função), 3 (RCL), 6 (LRF pessoal). Carregar os 14 custaria 3,5x mais.
ANEXOS="1 2 3 6"
# Ano mais recente completo primeiro (valor imediato), depois o corrente
# (parcial), depois retrocede cobrindo a gestão 2021-2024.
ANOS_SICONFI="2025 2026 2024 2023 2022 2021"

say "fila prefeito iniciada"

# ── V2 complemento: votos 2020 (eleição municipal) nas 20 UFs ───────────────
say "votos: 2020 — 20 UFs (aguardando lock livre)"
flock /tmp/etl_tse_votos_municipio.lock true
bash "$R" tse_votos_municipio --ano 2020 --uf $VINTE

# ── V1: SICONFI RREO municípios (todos os 5.570) ────────────────────────────
for ano in $ANOS_SICONFI; do
  # 2025/2026 também não têm UFs/capitais na VPS → 'todos'; demais anos já
  # têm UF+capital carregados (skip idempotente por raw_hash no loader).
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

# ── V2 histórico: votos 2016 nas 20 UFs ─────────────────────────────────────
say "votos: 2016 — 20 UFs (aguardando lock livre)"
flock /tmp/etl_tse_votos_municipio.lock true
bash "$R" tse_votos_municipio --ano 2016 --uf $VINTE

say "fila prefeito concluida"

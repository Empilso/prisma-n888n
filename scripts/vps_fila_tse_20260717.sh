#!/bin/bash
# Fila noturna TSE na VPS — GO do usuário em 2026-07-17.
# Ordem aprovada: despesas 2018/2020/2024 (7 UFs) → receitas 2014/2018 (todas
# UFs) → votos das 20 UFs restantes (2022, 2024, 2018).
# Espera a carga de votos em curso terminar antes de começar.
# Disparo: nohup bash /opt/prisma-n888n/scripts/vps_fila_tse_20260717.sh &
set -u
R=/opt/prisma-n888n/rodar_carga.sh
SETE="BA MG PE PR RJ RS SP"
VINTE="AC AL AM AP CE DF ES GO MA MS MT PA PB PI RN RO RR SC SE TO"
FLOG="/var/log/prisma-etl/fila_noturna_$(date +%Y%m%d_%H%M).log"
say() { echo "[$(date '+%F %T')] $*" >> "$FLOG"; }

say "fila iniciada — aguardando carga de votos em curso liberar o lock"
flock /tmp/etl_tse_votos_municipio.lock true
say "lock livre — começando"

# 1) Despesas de campanha — 2018/2020/2024, 7 UFs prioritárias
for ano in 2018 2020 2024; do
  say "despesas: coleta $ano"
  bash "$R" tse_despesas_campanha agent_a_coletor.py --ano "$ano" --ufs $SETE
done
say "despesas: normalizar + carregar + verificar + publicar"
bash "$R" tse_despesas_campanha agent_b_normalizador.py --todos
bash "$R" tse_despesas_campanha agent_c_loader.py --todos
bash "$R" tse_despesas_campanha agent_v_verificador.py --todos
bash "$R" tse_despesas_campanha agent_p_publicador.py --todos

# 2) Receitas de campanha — completar 2014 e 2018 (coletor default = todas UFs)
for ano in 2014 2018; do
  say "receitas: coleta $ano"
  bash "$R" tse_receitas_campanha agent_a_coletor.py --ano "$ano"
done
say "receitas: normalizar + carregar"
bash "$R" tse_receitas_campanha agent_b_normalizador.py --todos
bash "$R" tse_receitas_campanha agent_c_loader.py --todos

# 3) Votos — 20 UFs restantes, por relevância de ano
for ano in 2022 2024 2018; do
  say "votos: $ano — 20 UFs restantes"
  bash "$R" tse_votos_municipio --ano "$ano" --uf $VINTE
done
say "fila concluída"

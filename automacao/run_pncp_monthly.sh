#!/bin/bash
# run_pncp_monthly.sh — roda pncp_contratos com janela dinamica dos ultimos
# 35 dias (cobre o mes anterior inteiro + folga, evita buraco entre ciclos
# mensais). crews_config.json nao suporta valor dinamico, por isso este
# script proprio em vez de mexer no run_crew.sh generico.
PROJ=/opt/prisma-n888n
CONFIG="$PROJ/automacao/crews_config.json"
PY=/opt/prisma-n888n/.venv/bin/python3
DATA_FIM=$(date '+%Y%m%d')
DATA_INI=$(date -d '35 days ago' '+%Y%m%d')

$PY -c "
import json
p = '$CONFIG'
cfg = json.load(open(p))
cfg['pncp_contratos'] = {'stages': [
    {'script':'agent_a_coletor.py','args':['--data-inicio','$DATA_INI','--data-fim','$DATA_FIM']},
    {'script':'agent_b_normalizador.py','args':['--todos']},
    {'script':'agent_c_loader.py','args':['--todos']}]}
json.dump(cfg, open(p,'w'), ensure_ascii=False, indent=2)
"
bash "$PROJ/automacao/run_crew.sh" pncp_contratos

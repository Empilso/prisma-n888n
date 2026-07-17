#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ANOS=(2014 2016 2018 2020 2022 2024)

for ano in "${ANOS[@]}"; do
  python "$DIR/agent_a_coletor.py" --ano "$ano" "$@"
done
python "$DIR/agent_b_normalizador.py" --todos
python "$DIR/agent_c_loader.py" --todos
python "$DIR/agent_v_verificador.py" --todos
python "$DIR/agent_p_publicador.py" --todos

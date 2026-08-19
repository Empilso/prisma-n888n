#!/bin/bash
# digest_diario.sh — le crew_failures.log e crew_suspeitas.log das ultimas
# 24h e grava um resumo legivel. Existe porque descobrimos em 2026-08-19
# que uma crew pode devolver exit 0 com falha total (ver crew_suspeitas.log)
# -- sem isso, ninguem saberia.
FAILLOG=/var/log/prisma-etl/crew_failures.log
SUSPLOG=/var/log/prisma-etl/crew_suspeitas.log
OUT=/var/log/prisma-etl/digest_$(date '+%Y%m%d').log
DESDE=$(date -d '24 hours ago' -Iseconds)

{
  echo "=== Digest diario $(date '+%F %T') — janela: ultimas 24h ==="
  echo ""
  echo "--- Falhas reais (exit != 0) ---"
  awk -F' \\| ' -v desde="$DESDE" '$1 >= desde' "$FAILLOG" 2>/dev/null || echo "(nenhuma)"
  echo ""
  echo "--- Suspeitas (exit 0 mas conteudo indica falha) ---"
  awk -F' \\| ' -v desde="$DESDE" '$1 >= desde' "$SUSPLOG" 2>/dev/null || echo "(nenhuma)"
} > "$OUT"

# Mantem so os ultimos 30 dias de digest
find /var/log/prisma-etl -name 'digest_*.log' -mtime +30 -delete 2>/dev/null

cat "$OUT"

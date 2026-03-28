#!/bin/bash

# N888N Enterprise Launch Script
# Limpeza e Inicialização Unificada com Health-Check

echo "🧹 [1/4] Limpando processos antigos (Ghost Processes)..."
pkill -9 -f api_server.py || true
pkill -9 -f vite || true
sleep 2

echo "🚀 [2/4] Iniciando Backend (Port 8003)..."
nohup python3 src/api_server.py > backend.log 2>&1 &
BACKEND_PID=$!

echo "🩺 [3/4] Aguardando Backend ficar online..."
for i in {1..15}; do
    sleep 1
    if curl -s http://localhost:8003/api/status > /dev/null 2>&1; then
        echo "✅ Backend ONLINE em ${i}s (PID: $BACKEND_PID)"
        break
    fi
    if [ $i -eq 15 ]; then
        echo "❌ Backend FALHOU ao iniciar. Verifique backend.log"
        tail -n 20 backend.log
        exit 1
    fi
    echo "   ... aguardando ($i/15)"
done

echo "🎨 [4/4] Iniciando Frontend (Port 5175)..."
cd ui && npm run dev -- --port 5175

import json, os

path = '/home/carneiro888/CARNEIRO888/N888N - AGENTIC EXTRATORES/n888n/data/saida/kaka/alba_2022_kaka.json'
try:
    with open(path, 'r') as f:
        text = f.read()

    # Procura ']{' ou '][{' inserido por erro e recorta
    if ']{' in text:
        text = text.split(']{')[0] + ']'
    
    with open(path, 'w') as f:
        f.write(text)
    
    # Testa se carrega agora
    with open(path, 'r') as f:
        json.load(f)
    print("JSON FIXED SUCCESSFULLY")
except Exception as e:
    print("ERRO:",e)

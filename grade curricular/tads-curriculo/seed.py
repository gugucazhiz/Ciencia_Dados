"""Uso: python seed.py [caminho.json]  — carrega o currículo nos 3 bancos."""
import json
import sys

from app.repos import carregar_tudo

caminho = sys.argv[1] if len(sys.argv) > 1 else "data/tads_2019.json"
with open(caminho, encoding="utf-8") as f:
    print(carregar_tudo(json.load(f)))

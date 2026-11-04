#!/usr/bin/env bash
# Configura o Graphify (grafo do código para o Claude gastar menos tokens).
# Rode uma vez, na raiz do projeto:  bash scripts/setup-graphify.sh
set -euo pipefail

# Atenção: o pacote oficial é "graphifyy" (com dois y). Outros "graphify*" no PyPI não são do projeto.
python -m pip install --upgrade graphifyy
graphify install        # registra a skill /graphify no Claude Code
graphify hook install   # reconstrói o grafo a cada commit

echo
echo "Pronto. Abra o Claude Code nesta pasta e rode:  /graphify ."
echo "Depois de um git pull, rode:  /graphify . --update"

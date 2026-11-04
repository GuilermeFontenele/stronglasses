# Configura o Graphify (grafo do código para o Claude gastar menos tokens).
# Rode uma vez, na raiz do projeto, no PowerShell:  .\scripts\setup-graphify.ps1
$ErrorActionPreference = "Stop"

# Atenção: o pacote oficial é "graphifyy" (com dois y). Outros "graphify*" no PyPI não são do projeto.
python -m pip install --upgrade graphifyy
graphify install        # registra a skill /graphify no Claude Code
graphify hook install   # reconstrói o grafo a cada commit

Write-Host ""
Write-Host "Pronto. Abra o Claude Code nesta pasta e rode:  /graphify ."
Write-Host "Depois de um git pull, rode:  /graphify . --update"

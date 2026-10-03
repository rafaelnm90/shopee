#!/bin/bash
# Prepara a sessão do Claude Code na nuvem: cria o venv/ (o mesmo nome do
# servidor, já no .gitignore), instala as dependências dos robôs e as
# ferramentas de checagem (pytest, pyflakes, time-machine), para os testes rodarem logo de
# cara. Os testes não precisam de .env: o tests/conftest.py monta um ambiente falso.
# O venv evita brigar com os pacotes que o Debian instalou no Python do sistema.
set -euo pipefail

# No computador do usuário e no servidor o ambiente já existe; só roda na nuvem.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}"

if [ ! -x venv/bin/python3 ]; then
  python3 -m venv venv
fi

venv/bin/python3 -m pip install --quiet --disable-pip-version-check \
  -r requirements.txt pytest pyflakes "time-machine>=3,<4"

# Deixa o venv ativo nos comandos da sessão (python3, pytest, pyflakes).
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export VIRTUAL_ENV=\"$PWD/venv\"" >> "$CLAUDE_ENV_FILE"
  echo "export PATH=\"$PWD/venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

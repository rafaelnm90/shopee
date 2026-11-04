#!/bin/bash
# Monta um servidor novo para os robôs, do zero: os pacotes do sistema, o código, o venv e os
# serviços do systemd, ainda desligados (o mudar_servidor.py liga depois de levar os dados).
# Pensado para o Ubuntu da Oracle, com o usuário ubuntu e sudo sem senha, como o de agora.
# Rodar de novo só faz o que falta. Pedido do Rafael (P147 1): DECISOES.md, Monitor, deploy e
# servidor. Os pacotes vêm do mudar_servidor.py (PACOTES); sem eles, a lista de sempre.
# O log é público: só estados, versões e números.
set -euo pipefail

REPO="https://github.com/rafaelnm90/shopee.git"
PASTA="$HOME/shopee"
read -r -a LISTA <<< "${PACOTES:-python3 python3-venv python3-pip git ffmpeg adb sqlite3 curl}"

echo "== Pacotes do sistema"
sudo -n apt-get update -qq
sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${LISTA[@]}" >/dev/null
echo "pacotes: ${#LISTA[@]} instalados"

echo "== Código"
if [ -d "$PASTA/.git" ]; then
  git -C "$PASTA" pull -q --ff-only
else
  git clone -q "$REPO" "$PASTA"
fi
echo "versão: $(git -C "$PASTA" log -1 --format='%h %ad' --date=format:'%d/%m %H:%M')"

echo "== Ambiente do Python"
[ -x "$PASTA/venv/bin/python3" ] || python3 -m venv "$PASTA/venv"
"$PASTA/venv/bin/pip" install -q --no-cache-dir -r "$PASTA/requirements.txt"
echo "venv: $("$PASTA/venv/bin/python3" --version)"

echo "== Serviços"
for arquivo in "$PASTA"/servicos_linux/*.service; do
  nome="$(basename "$arquivo")"
  sudo -n ln -sfn "$arquivo" "/etc/systemd/system/$nome"
done
sudo -n systemctl daemon-reload
echo "serviços: $(ls "$PASTA"/servicos_linux/*.service | wc -l) vinculados, ainda desligados"

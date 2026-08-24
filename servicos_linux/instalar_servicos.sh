#!/bin/bash
# 🛠️ Gerenciador dos serviços systemd do ecossistema Shopee.
# Uso: ./instalar_servicos.sh [instalar|reiniciar|status|logs]
# Nada aqui roda sozinho: todo comando é disparado por você, na mão.

set -euo pipefail

PASTA_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASTA_PROJETO="$(dirname "$PASTA_SCRIPT")"

SERVICOS=(
  bot_mestre_bot
  espelhador_videos_autorais_bot
  motor_userbot_bot
  divulgacao_canal_bot
  downloader_bot
)

ACAO="${1:-status}"

case "$ACAO" in
  instalar)
    # 🛡️ Nunca instala em cima de código quebrado.
    echo "🛡️  Validando o código antes de mexer nos serviços..."
    ( cd "$PASTA_PROJETO" && python3 validar_deploy.py ) || {
      echo "❌ Validação falhou. Nada foi alterado."; exit 1;
    }

    for s in "${SERVICOS[@]}"; do
      arquivo="$PASTA_SCRIPT/$s.service"
      [ -f "$arquivo" ] || { echo "⚠️  $s.service não encontrado, pulando."; continue; }
      sudo cp "$arquivo" "/etc/systemd/system/$s.service"
      echo "📄 $s.service copiado."
    done

    sudo systemctl daemon-reload
    for s in "${SERVICOS[@]}"; do
      sudo systemctl enable "$s" >/dev/null 2>&1 || true
    done
    echo "✅ Units instalados e habilitados no boot. Rode 'reiniciar' para aplicar."
    ;;

  reiniciar)
    echo "🛡️  Validando o código antes de reiniciar..."
    ( cd "$PASTA_PROJETO" && python3 validar_deploy.py ) || {
      echo "❌ Validação falhou. Serviços continuam como estavam."; exit 1;
    }

    for s in "${SERVICOS[@]}"; do
      sudo systemctl restart "$s"
      echo "🔄 $s reiniciado."
    done
    sleep 3
    echo ""
    for s in "${SERVICOS[@]}"; do
      estado="$(systemctl is-active "$s" || true)"
      if [ "$estado" = "active" ]; then
        echo "✅ $s: $estado"
      else
        echo "❌ $s: $estado  → journalctl -u $s -n 40 --no-pager"
      fi
    done
    ;;

  status)
    for s in "${SERVICOS[@]}"; do
      printf "%-38s %s (desde %s)\n" "$s" \
        "$(systemctl is-active "$s" || true)" \
        "$(systemctl show "$s" -p ActiveEnterTimestamp --value)"
    done
    ;;

  logs)
    args=()
    for s in "${SERVICOS[@]}"; do args+=(-u "$s"); done
    journalctl "${args[@]}" -f
    ;;

  *)
    echo "Uso: $0 [instalar|reiniciar|status|logs]"
    exit 1
    ;;
esac

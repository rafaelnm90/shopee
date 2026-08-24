#!/bin/bash
# 🛠️ Gerenciador dos serviços systemd do ecossistema Shopee.
# Uso: ./instalar_servicos.sh [status|reiniciar|vincular|logs]
# Nada roda sozinho: todo comando é disparado por você, na mão.

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

validar() {
  echo "🛡️  Validando o código antes de mexer nos serviços..."
  ( cd "$PASTA_PROJETO" && python3 validar_deploy.py ) || {
    echo "❌ Validação falhou. Nada foi alterado."; exit 1;
  }
}

ACAO="${1:-status}"

case "$ACAO" in
  status)
    for s in "${SERVICOS[@]}"; do
      alvo="$(readlink -f "/etc/systemd/system/$s.service" 2>/dev/null || echo '—')"
      case "$alvo" in
        "$PASTA_SCRIPT"/*) vinculo="🔗 versionado" ;;
        —)                 vinculo="❓ ausente" ;;
        *)                 vinculo="📄 cópia solta" ;;
      esac
      printf "%-38s %-10s %-16s %s\n" "$s" \
        "$(systemctl is-active "$s" || true)" "$vinculo" \
        "$(systemctl show "$s" -p ActiveEnterTimestamp --value)"
    done
    ;;

  vincular)
    # 🔗 Transforma cópias soltas em links para a pasta versionada.
    for s in "${SERVICOS[@]}"; do
      arquivo="$PASTA_SCRIPT/$s.service"
      instalado="/etc/systemd/system/$s.service"
      [ -f "$arquivo" ] || { echo "⚠️  $s.service não está na pasta, pulando."; continue; }
      if [ "$(readlink -f "$instalado" 2>/dev/null || true)" = "$arquivo" ]; then
        echo "✅ $s já vinculado."
        continue
      fi
      sudo ln -sfn "$arquivo" "$instalado"
      echo "🔗 $s vinculado à pasta versionada."
    done
    sudo systemctl daemon-reload
    echo "♻️  daemon-reload feito. Rode 'reiniciar' para aplicar."
    ;;

  reiniciar)
    validar
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

  logs)
    args=()
    for s in "${SERVICOS[@]}"; do args+=(-u "$s"); done
    journalctl "${args[@]}" -f
    ;;

  *)
    echo "Uso: $0 [status|reiniciar|vincular|logs]"
    exit 1
    ;;
esac

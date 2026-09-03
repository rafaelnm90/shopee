#!/bin/bash
# 🛠️ Gerenciador dos serviços systemd do ecossistema Shopee.
# Uso: ./instalar_servicos.sh [status|reiniciar|vincular|logs]
# Nada roda sozinho: todo comando é disparado por você, na mão.

set -euo pipefail

PASTA_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASTA_PROJETO="$(dirname "$PASTA_SCRIPT")"

# 🔧 Autocura de permissão: o GitHub Web Editor não marca arquivo como
# executável, então todo 'git pull' devolve o modo 644. Aqui volta sozinho.
chmod +x "$PASTA_SCRIPT"/*.sh "$PASTA_PROJETO"/*.sh 2>/dev/null || true

# 🔎 A lista sai dos .service da própria pasta. Robô novo entra sozinho:
# basta o .service estar no repositório. Nada de lista fixa aqui.
mapfile -t SERVICOS < <(
  find "$PASTA_SCRIPT" -maxdepth 1 -name '*.service' -printf '%f\n' \
    | sed 's/\.service$//' | sort
)

if [ ${#SERVICOS[@]} -eq 0 ]; then
  echo "❌ Nenhum .service encontrado em $PASTA_SCRIPT. Abortando."
  exit 1
fi

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

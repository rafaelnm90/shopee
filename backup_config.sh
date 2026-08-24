#!/bin/bash
# 💾 Backup do que o git NÃO guarda: banco de dados e configurações locais.
# Uso: bash backup_config.sh
# Guarda em ~/backups (fora do repositório) e mantém os 7 mais recentes.

set -euo pipefail

PASTA_PROJETO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINO="$HOME/backups"
CARIMBO="$(date +%Y-%m-%d_%H%M)"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

mkdir -p "$DESTINO"

# 🔒 Cópia consistente do SQLite: o .backup do próprio sqlite3 respeita as
# transações em curso. Um "cp" simples pode capturar o banco pela metade.
if [ -f "$PASTA_PROJETO/banco_dados.db" ]; then
  sqlite3 "$PASTA_PROJETO/banco_dados.db" ".backup '$TEMP/banco_dados.db'"
  echo "🗄️  banco_dados.db copiado."
else
  echo "⚠️  banco_dados.db não encontrado."
fi

# 📄 Configurações locais que o .gitignore exclui do repositório.
for arquivo in espelhos_config.json .env; do
  if [ -f "$PASTA_PROJETO/$arquivo" ]; then
    cp "$PASTA_PROJETO/$arquivo" "$TEMP/"
    echo "📄 $arquivo copiado."
  fi
done

PACOTE="$DESTINO/shopee_backup_$CARIMBO.tar.gz"
tar -czf "$PACOTE" -C "$TEMP" .
chmod 600 "$PACOTE"

# 🧹 Mantém só os 7 mais recentes.
ls -1t "$DESTINO"/shopee_backup_*.tar.gz 2>/dev/null | tail -n +8 | while read -r velho; do
  rm -f "$velho"
  echo "🧹 Backup antigo removido: $(basename "$velho")"
done

echo ""
echo "✅ Backup criado: $PACOTE ($(du -h "$PACOTE" | cut -f1))"
echo "   Para baixar no seu computador:"
echo "   scp ubuntu@<ip-do-servidor>:$PACOTE ."

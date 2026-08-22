# 🤖 Shopee Video Bot

Ecossistema de automação para afiliados Shopee no Telegram.
Cinco serviços independentes rodando num servidor Oracle ARM (Ubuntu).

---

## ⚡ Comandos do dia a dia

### Publicar mudanças no servidor
```bash
deploybot     # robôs principais (bot_mestre, espelhador, userbot, divulgação)
deploydown    # apenas o downloader
```

Se os atalhos não existirem, crie uma vez:
```bash
cat >> ~/.bashrc <<'EOF'
alias deploybot='cd ~/shopee && git pull && python3 validar_deploy.py && sudo systemctl restart bot_mestre_bot espelhador_videos_autorais_bot motor_userbot_bot divulgacao_canal_bot && journalctl -u bot_mestre_bot -f -n 20'
alias deploydown='cd ~/shopee && git pull && python3 validar_deploy.py downloader_bot.py && sudo systemctl restart downloader_bot && journalctl -u downloader_bot -f -n 20'
EOF
source ~/.bashrc
```

### Ver o que está acontecendo
```bash
journalctl -u bot_mestre_bot -f          # log ao vivo
journalctl -u downloader_bot -f
systemctl status bot_mestre_bot          # está no ar?
```

### Validar sem publicar
```bash
cd ~/shopee && python3 validar_deploy.py
```

---

## 🧩 Os cinco serviços

| Serviço | Arquivo | O que faz |
|---|---|---|
| `bot_mestre_bot` | `bot_mestre.py` | Painéis, filas, publicação, financeiro, parceiros |
| `espelhador_videos_autorais_bot` | `espelhador_videos_autorais.py` | Captura dos Autorais e do Grupo Público |
| `motor_userbot_bot` | `motor_userbot.py` | Espião e Espelhador (conta Telethon) |
| `divulgacao_canal_bot` | `divulgacao_canal.py` | Divulgação em grupos externos |
| `downloader_bot` | `downloader_bot.py` | Baixa vídeos a pedido dos membros |

**Regra:** mexeu num arquivo → reinicie o serviço correspondente. O Python só lê o arquivo na inicialização.

---

## 📺 Canais

| Canal | ID | Papel |
|---|---|---|
| Acervo Afiliados Shopee | `-1003909405581` | Canal Principal — vídeos editados |
| Acervo Viral Shopee | `-1003932482573` | Destino do Espião — volume 24h |
| Grupo Público | `-1003892378604` | Comunidade: submissões e downloader |
| Vídeos Autorais Afiliados | `-1004454448955` | Reserva intermediária |

---

## 🔄 As cinco filas

Todas usam o mesmo motor (`motor_filas.py`), com regras próprias:

| Fila | Janela | Atraso | Espaçamento mínimo |
|---|---|---|---|
| Espião → Viral | 0h–24h | D+1 | 10 ± 5 min |
| Espelhador | 8h–22h | por rota | 20 ± 8 min |
| Autorais | 10h–20h | D+15 | 15 ± 6 min |
| Grupo Público | 10h–20h | D+30 | 15 ± 6 min |
| Parceiros | 0h–24h | por parceiro | 10 ± 5 min |

**Como o espaçamento funciona:** o motor divide a janela pela quantidade de vídeos.
O valor configurado é **piso**, não intervalo fixo — 5 vídeos ficam ~2h de distância,
100 vídeos ficam no mínimo. O que não couber no dia transborda para o seguinte;
o que passar de 5 dias desde a captura é descartado.

---

## 🛡️ Proteções automáticas

| Proteção | Quando age |
|---|---|
| Validador + CI | A cada commit no GitHub |
| 18 testes do motor de filas | A cada commit |
| Monitor de saúde | De hora em hora, avisa no privado |
| Faxina de arquivos órfãos | 03h, cruzando com as filas |
| Coleta de métricas | 23h50 |
| Anti-duplicata | Por arquivo e por produto |
| Cache de análises da IA | Evita analisar o mesmo vídeo 2x |

---

## 🔥 Quando algo quebra

### O bot não responde
```bash
systemctl status bot_mestre_bot
journalctl -u bot_mestre_bot -n 50
```

### Erro de indentação depois de colar código
```bash
cd ~/shopee && python3 validar_deploy.py
```
Ele mostra arquivo, linha e o código em volta. Corrija no GitHub e rode `deploybot`.

### Serviço em loop de reinício
```bash
sudo systemctl stop bot_mestre_bot     # para o loop primeiro
# corrija o código, então:
deploybot
```

### Disco enchendo
```bash
df -h /
du -sh ~/shopee/temp ~/shopee/archive
sudo journalctl --vacuum-time=7d
```
⚠️ **Nunca apague `temp/` por idade** — os vídeos agendados do Espião ficam lá.
A faxina das 03h já remove só o que não está em fila nenhuma.

### O downloader parou de baixar
Normal: TikTok e Instagram quebram o `yt-dlp` com frequência.
```bash
cd ~/shopee && ./venv/bin/pip install -U yt-dlp
sudo systemctl restart downloader_bot
```

---

## 📁 Arquivos importantes

| Arquivo | Conteúdo |
|---|---|
| `.env` | Tokens e chaves — **nunca vai para o GitHub** |
| `banco_dados.db` | Configurações, filas e histórico |
| `validar_deploy.py` | Checagem antes do deploy |
| `test_motor_filas.py` | 18 testes do motor |
| `motor_filas.py` | Cálculo de horários de todas as filas |
| `utils.py` | Funções compartilhadas |

---

## ⚙️ Detalhes do ambiente

- **Python:** use sempre `./venv/bin/python3`, nunca o do sistema
- **Fuso:** travado em `America/Sao_Paulo` dentro de cada serviço
- **Servidor:** Oracle ARM, 45 GB de disco, cota de 10 TB/mês de saída

---

## 🧪 Rodando os testes localmente
```bash
cd ~/shopee && python3 -m pytest test_motor_filas.py -v
```

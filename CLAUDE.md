# CLAUDE.md

Mapa curto do projeto e as regras combinadas com o Rafael. Leia antes de mexer
no código: diz onde fica cada coisa e como validar uma mudança.

## O projeto

Afiliados Shopee no Telegram. Cinco serviços systemd num servidor Oracle ARM
(Ubuntu), Python 3.12, `venv/` dentro da pasta do projeto (`servicos_linux/`).

| Serviço | Arquivo | O que faz |
|---|---|---|
| `bot_mestre_bot` | `bot_mestre.py` | Bot do admin (aiogram): painéis, filas, publicação nos canais, Grupo Público, parceiros, financeiro, monitor, `/status` |
| `espelhador_videos_autorais_bot` | `espelhador_videos_autorais.py` | Userbot dos Autorais: captura do grupo de origem para o canal; contas de repostagem devolvem os vídeos ao grupo |
| `motor_userbot_bot` | `motor_userbot.py` | Userbot do Espião (alimenta a fila do Viral) e do Espelhador de canais |
| `divulgacao_canal_bot` | `divulgacao_canal.py` | Userbot que posta convites nos grupos-alvo |
| `downloader_bot` | `downloader_bot.py` | Bot separado que baixa vídeos a pedido dos membros |

Módulos de apoio (não são serviços):

- `db.py`: todo acesso ao banco. Detalhes em "Dados".
- `motor_filas.py`: decide quando cada vídeo vai ao ar e quantos por dia. Não publica.
- `pool_contas.py`: cadastro das contas Telethon e quem ocupa cada posto.
  - `espelho` (captura): uma conta só.
  - `repostagem`: rodízio entre todas as aptas, menos a da captura.
  - O ✅/❌ de cada conta sai de `avaliar_saude`.
  - Login em etapas (`iniciar_login` → `confirmar_codigo` → `confirmar_senha` → `finalizar_cadastro`), usado pelo botão ➕ Nova conta.
- `blacklist_captura.py`: autores que o espelhador nunca captura, incluindo as próprias contas do pool, para não haver laço de recaptura.
- `painel_espelhos.py` e `painel_notas.py`: routers aiogram incluídos no bot_mestre.
- `utils.py` (`erros_logs`, caches, validação de IDs) e `fuso.py` (horário de Brasília e formato de log).
- `api_gemini.py` (IA, com cascata de modelos) e `api_shopee.py` (links de afiliado).
- Ferramentas: `validar_deploy.py`, `testar_chaves.py`, `backup_config.sh`.

O README tem os IDs dos canais, as cinco filas e os comandos do servidor.

## Onde fica cada coisa no bot_mestre.py

São 17 mil linhas. Navegue pelos marcadores de seção, que não mudam quando o
arquivo cresce: `grep -n "^# --- " bot_mestre.py`. Os blocos grandes usam
`# ===` com o título na linha seguinte. Exemplos:

- `--- Estados (FSM) ---` e `--- Teclados ---`: estados e teclados de todos os fluxos.
- `--- Fila do canal principal ---`, `--- Pausa programada ---` e `--- Gerenciar Fila de Postagens ---`.
- `--- Painel do Espião ---` e `--- Motor do Espião (fila de clonagem) ---`.
- Painéis de SPAM:
  - `--- SPAM Viral ---`;
  - `--- SPAM em Grupos ---`;
  - `--- SPAM por escopo ---`: Grupo Público e Achadinhos.
- Grupo Público e parceiros:
  - Painel do Grupo Público: bloco `===`.
  - `--- Submissão pública ---` e `--- Buscador de produtos ---`.
  - Parceiros: blocos `===` e `--- Cadastro de parceiro ---`.
- Contas: bloco `=== Painel de Contas e Postos`, `--- Nova conta pelo bot ---` e o painel de autores bloqueados.
- Fim do arquivo:
  - `--- Monitor de saúde ---`;
  - `--- /status ---`;
  - `--- main() ---`: agenda todos os jobs.

## Dados

- `banco_dados.db` (SQLite), sempre pelo `db.py`:
  - `db.conexao()` num `with`: grava no fim, desfaz se der erro e fecha sempre. Use em código novo.
  - `db.conectar()`: conexão solta, quem abre fecha.
  - Nunca `sqlite3.connect` direto: o `tests/test_db.py` barra.
  - O banco fica em modo WAL: leitura e gravação não se bloqueiam. Os arquivos `banco_dados.db-wal` e `-shm` fazem parte do banco.
  - `configuracoes` (chave → JSON): `db.ler_config` e `db.salvar_config`, os mesmos em todos os robôs.
  - Filas em tabelas: `fila_postagens` (canal principal), `fila_autorais`, `fila_publico`, `fila_parceiros` e `fila_notas`.
  - A fila do Espião (`fila_clonagem`) é uma chave de `configuracoes`.
  - `erros_logs`.
  - Pool: `contas_telegram`, `funcoes_contas` e `atividade_contas`.
- O Espelhador de canais ainda usa arquivos: `espelhos_config.json` e `fila_espelhador.json`.
- Nada disso está no git: o `.gitignore` cobre `*.db`, `*.json`, `*.session` e `.env`. No servidor, o `backup_config.sh` guarda essas coisas.

## Armadilhas conhecidas

- Importar `db` (o `utils` importa) troca o `sqlite3.connect` do processo inteiro, para as sessões do Telethon também esperarem 30 s pelo lock. Importar `fuso` trava o fuso no horário de Brasília.
- Os jobs do APScheduler e o FSM do aiogram ficam em memória.
  - Um restart (todo deploy) refaz a grade do dia em `main()`.
  - Também derruba os fluxos de painel que estavam abertos.
- aiogram: ganha o primeiro handler registrado que casar. Num fluxo FSM, o handler de "Cancelar ❌" tem de vir antes do handler que lê texto livre.
- `validar_deploy.py` exige que o 1º parâmetro de um handler se chame `message`, `callback`, `event`, `query`, `msg` ou `callback_query`.
- Uma sessão Telethon não pode ser usada por dois processos ao mesmo tempo.
- `ADMIN_ID` e os IDs dos canais estão fixos no código.

## Testes e checagens

Na nuvem, o hook `.claude/hooks/session-start.sh` cria o `venv/` e instala as
dependências. O venv já vem ativo nos comandos. Para conferir uma mudança, use
os mesmos comandos do CI:

```bash
python3 validar_deploy.py *.py
python3 -m pyflakes *.py tests/
python3 pool_contas.py autoteste
python3 blacklist_captura.py autoteste
python3 -m pytest tests -q        # ~1 min; sem .env e sem rede
```

- `tests/conftest.py` dá a base dos testes:
  - monta um `.env` falso e roda cada teste numa pasta vazia, com banco novo;
  - fixtures dos módulos: `bm` (bot_mestre), `pc` (pool_contas) e `esp` (espelhador dos Autorais);
  - fakes: `Msg` (mensagem do Telegram) e `Est` (estado do FSM);
  - helpers: `rodar`, `inserir` e `consultar`.
- Toda correção de bug ganha um teste que falha sem a correção.
- O teste do fim da pausa só roda entre 10h e 20h (horário de Brasília); fora disso, aparece como pulado.
- CI:
  - `validar.yml` roda em todo PR para a `main`.
  - `deploy.yml` roda no merge na `main`. Ele repete a validação e, por SSH, faz `git pull` e `pip install` no servidor e reinicia os 5 serviços. 25 s depois, confere com `systemctl is-active` se todos subiram.
  - Não há acesso direto ao servidor. Para saber o que está no ar, peça ao Rafael o `/status` do bot: serviços, versão, disco, contas e últimos erros.

## Como trabalhamos

- O Rafael pede em português. Responda em português, de forma simples.
- Dúvida sobre a intenção de uma regra (ex.: "era para apagar depois de processar?") → pergunte antes de mudar. Ofereça opções, com a recomendada primeiro.
- Comentários em português explicam o porquê e a regra de negócio.
  - Sem histórico ("antes era…", "corrigido em…"): isso fica no git.
  - Sem emoji nos comentários. Nos textos que o bot mostra, pode.
  - Cada módulo começa com uma docstring que diz o que ele é e quem o usa.
- Um assunto por commit. O título do commit fica em português, no formato `arquivo ou área: o que mudou`.
- PR, rodadas e merge: merge na `main` é deploy em produção.
  - Mudança pronta e validada: abrir o PR, acompanhar e fazer o merge sem perguntar.
  - Antes do merge, o CI do PR precisa passar 5 vezes seguidas no mesmo commit, rodando de novo o workflow "Validar código".
  - Entre o fim de uma rodada e o início da próxima, esperar 5 minutos.
  - Se uma rodada falhar, investigar e corrigir; a contagem volta a zero.
  - Depois do merge, acompanhar o deploy até os 5 serviços aparecerem ativos e avisar o Rafael.
  - Se o Rafael disser para não fazer o merge, não fazer.
  - Se o Rafael mandar fazer o merge direto, sem as rodadas, obedecer.
- O repositório é público:
  - nunca commitar credencial, `.env`, sessão ou banco;
  - nos testes, nada com cara de token (o GitGuardian acusa).

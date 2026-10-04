# CLAUDE.md

Mapa curto do projeto e as regras combinadas com o Rafael. Leia antes de mexer
no código: diz onde fica cada coisa e como validar uma mudança.

O `DECISOES.md` é o diário dos pedidos do Rafael: como cada robô deve se
comportar e as exceções que o código não explica. Leia a área do que for mudar.

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
- `alvos_sem_acesso.py`: alvos da divulgação a que a conta perdeu o acesso. O `divulgacao_canal` marca e para de enviar; o bot_mestre avisa e reativa.
- `painel_espelhos.py` e `painel_notas.py`: routers aiogram incluídos no bot_mestre.
- `utils.py` (`erros_logs`, caches, validação de IDs) e `fuso.py` (horário de Brasília e formato de log).
- `api_gemini.py` (IA, com cascata de modelos) e `api_shopee.py` (links de afiliado).
- `backup_dados.py`: backup diário (03:40, pelo bot_mestre) do banco, das sessões, dos JSON e do `.env` em `~/backups`, ficam 7. O `/status` mostra a idade do último.
- Ferramentas: `validar_deploy.py`, `testar_chaves.py`, `inventario.py` e `servicos_afetados.py` (o deploy pergunta a ele quem reiniciar).

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
  - `configuracoes` (chave → JSON): `db.ler_config` e `db.salvar_config`, os mesmos em todos os robôs. Chave que dois robôs gravam: `db.atualizar_config` (lê, altera e grava sem perder a gravação do outro).
  - Filas em tabelas: `fila_postagens` (canal principal), `fila_autorais`, `fila_publico`, `fila_parceiros` e `fila_notas`.
  - A fila do Espião (`fila_clonagem`) é uma chave de `configuracoes`.
  - `erros_logs`.
  - Pool: `contas_telegram`, `funcoes_contas` e `atividade_contas`.
- O Espelhador de canais ainda usa arquivos: `espelhos_config.json` e `fila_espelhador.json`.
- Nada disso está no git: o `.gitignore` cobre `*.db`, `*.json`, `*.session` e `.env`. No servidor, o backup diário (`backup_dados.py`) guarda essas coisas em `~/backups`.

## Armadilhas conhecidas

- Importar `db` (o `utils` importa) troca o `sqlite3.connect` do processo inteiro, para as sessões do Telethon também esperarem 30 s pelo lock. Importar `fuso` trava o fuso no horário de Brasília.
- Os jobs do APScheduler e o FSM do aiogram ficam em memória.
  - Um restart refaz a grade do dia em `main()`. O deploy só reinicia o robô cujo código mudou.
  - Também derruba os fluxos de painel que estavam abertos.
- aiogram: ganha o primeiro handler registrado que casar. Num fluxo FSM, o handler de "Cancelar ❌" tem de vir antes do handler que lê texto livre.
- `validar_deploy.py` exige que o 1º parâmetro de um handler se chame `message`, `callback`, `event`, `query`, `msg` ou `callback_query`.
- Uma sessão Telethon não pode ser usada por dois processos ao mesmo tempo.
- `ADMIN_ID` e os IDs dos canais estão fixos no código.
- Log: `logger.info/warning/error` direto, sem chave na frente (o `tests/test_logs.py` barra `EXIBIR_LOGS`). O nível de cada robô vem do `NIVEL_LOG` no `.env` (`DEBUG`, `INFO`, `WARNING`, `ERROR`; padrão `INFO`).

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
python3 -m pytest tests -q --ordem aleatoria --relogio 23:59:30   # como o CI
```

- `tests/conftest.py` dá a base dos testes:
  - monta um `.env` falso e roda cada teste numa pasta vazia, com banco novo;
  - fixtures dos módulos: `bm` (bot_mestre), `pc` (pool_contas) e `esp` (espelhador dos Autorais);
  - fakes: `Msg` (mensagem do Telegram) e `Est` (estado do FSM);
  - helpers: `rodar`, `inserir` e `consultar`.
- Toda correção de bug ganha um teste que falha sem a correção.
- `--relogio HH:MM` põe todos os testes naquela hora de Brasília; `relogio("15:00")` (fixture) fixa a hora de um teste só. Teste que só faz sentido numa certa hora usa `relogio(...)`, nunca `pytest.skip`.
- `--ordem aleatoria` embaralha os testes. Um teste não pode depender de outro ter rodado antes.
- CI:
  - `validar.yml` roda em todo PR para a `main`, com a suíte em 4 horários e ordem aleatória.
  - `deploy.yml` roda no merge na `main`. Ele repete a validação e, por SSH, faz `git pull` e `pip install` no servidor. Reinicia só os serviços cujo código mudou (o arquivo do robô ou um módulo que ele importa; `requirements.txt` ou dúvida = todos; só docs, testes ou workflows = nenhum). Confere os 5 aos 25 s e de novo 3 min depois (processo e contador de reinícios). Robô que cai mostra só o tipo do erro no log.
  - `diagnostico.yml` olha o servidor de hora em hora, só lendo: robôs (estado, desde quando, reinícios), máquina (carga, memória, disco), banco e volume de log. Fica vermelho com robô fora do ar ou disco acima de 90% (o GitHub manda e-mail). Para ver o servidor agora, dispare-o (`run_workflow` em `diagnostico.yml`) e leia o log do job.
  - `inventario.yml` (só à mão) roda o `inventario.py` no servidor. Ele mostra:
    - tamanho e idade de cada pasta, os arquivos soltos e as linhas por tabela;
    - os erros do `erros_logs` por origem e tipo de exceção (sem o texto) e as versões das bibliotecas;
    - as configurações mais pesadas e o histórico da fila do Espelhador;
    - o espaço do journal e as linhas de log que mais se repetem, com arquivo:linha do código;
    - os caches e a memória de cada robô.
    Use para achar o que acumula.
  - O repositório é público e os logs do Actions também: nos workflows, só estados e números; nunca conteúdo de log dos robôs ou dados do banco.
  - Não há acesso direto ao servidor por SSH a partir da sessão. Os detalhes dos erros ficam no `/status` do bot, no privado do Rafael.

## Como trabalhamos

- O Rafael pede em português. Responda em português, de forma simples.
- Vídeo do Rafael: ver e ouvir o vídeo inteiro antes de responder ou agir.
  - `.claude/scripts/ver_video.sh VIDEO PASTA` gera as folhas de quadros (ler todas, em ordem) e a fala transcrita (`fala.txt`).
  - Sem transcrição (a rede do ambiente bloqueia o modelo de voz no huggingface.co), dizer isso logo e pedir a transcrição antes de mudar qualquer coisa. Nunca agir só pelos quadros quando o vídeo tem fala.
- Diário de decisões (`DECISOES.md`):
  - Antes de mudar um comportamento, ler a área dele no diário.
  - Todo pedido do Rafael que define comportamento entra no diário, na mesma mudança que o implementa. Isso inclui as respostas dele às perguntas de intenção.
  - Pedido novo que contradiz um antigo: riscar o antigo com "substituída em DD/MM/AAAA" e registrar o novo logo abaixo, sem apagar. Na dúvida se contradiz, perguntar.
  - Não contrariar uma decisão do diário por conta própria, nem para "corrigir" algo que parece bug. Se parecer errado, perguntar.
  - Exceção a um padrão no código: comentário curto no lugar apontando para a entrada (ex.: `# Decisão do Rafael: DECISOES.md, Canal Viral`).
- Dúvida sobre a intenção de uma regra (ex.: "era para apagar depois de processar?") → pergunte antes de mudar. Ofereça opções, com a recomendada primeiro.
- Comentários em português explicam o porquê e a regra de negócio.
  - Sem histórico ("antes era…", "corrigido em…"): isso fica no git.
  - Sem emoji nos comentários. Nos textos que o bot mostra, pode.
  - Cada módulo começa com uma docstring que diz o que ele é e quem o usa.
- Um assunto por commit. O título do commit fica em português, no formato `arquivo ou área: o que mudou`.
- PR, CI e merge: merge na `main` é deploy em produção.
  - Mudança pronta e validada: abrir o PR, acompanhar e fazer o merge sem perguntar.
  - Antes do merge, o CI do PR ("Validar código") precisa ficar verde no commit final.
    - Ele já é a rodada reforçada: a suíte roda 4 vezes, cada uma num horário (00:00:30, 08:00, 12:30, 23:59:30) e numa ordem sorteada.
    - Não repetir o CI no mesmo commit só para conferir: o resultado seria o mesmo.
  - Se o CI falhar, investigar e corrigir. "Instável" não é causa: a semente impressa (`--ordem <semente> --relogio <hora>`) repete a falha.
  - Depois do merge, acompanhar o deploy até ficar verde. O deploy confere os 5 robôs aos 25 s e de novo 3 min depois (robô que caiu e voltou sozinho deixa o deploy vermelho).
  - Avisos ao Rafael, numa tabela curta, só em três momentos:
    - ao abrir o PR, com a previsão do merge e do fim do deploy;
    - se algo falhar, com o que falhou e o que vou fazer;
    - no fim, com o merge feito e os robôs no ar.
    - No meio, só se ele pedir o status.
  - Se o Rafael disser para não fazer o merge, não fazer.
  - Se o Rafael mandar fazer o merge direto, sem esperar o CI, obedecer.
  - Se o Rafael pedir rodadas extras (ex.: "faz 5 rodadas"), repetir o CI quantas vezes ele pedir, com o intervalo que ele disser (padrão: 5 min), avisando posição e horário da próxima.
- O repositório é público:
  - nunca commitar credencial, `.env`, sessão ou banco;
  - nos testes, nada com cara de token (o GitGuardian acusa).

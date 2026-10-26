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
  - Login em etapas (`iniciar_login` → `confirmar_codigo` → `confirmar_senha` → `finalizar_cadastro`), usado pelo botão Cadastrar Conta ➕.
- `blacklist_captura.py`: autores que o espelhador nunca captura, incluindo as próprias contas do pool, para não haver laço de recaptura.
- `alvos_sem_acesso.py`: alvos da divulgação a que a conta perdeu o acesso. O `divulgacao_canal` marca e para de enviar; o bot_mestre avisa e reativa.
- `painel_espelhos.py`, `painel_notas.py` e `painel_shopee_video.py` (Outros Canais → Shopee Vídeo 🎬, separado por robô, cada tela explicando os botões: a inicial diz quem posta agora, com Rascunhos do Robô 📝, Fonte dos Vídeos e Como Funciona ❓; Modo Assistente 📲 com pausa, vídeos por dia, horário dos envios e Enviar 1 Agora; Robô Automático 🤖 com pausa, Fila de Rascunhos 🗂️ (os que esperam aprovação e os aprovados, com a hora prevista de cada post e por que um aprovado atrasado ainda não saiu), Preparar 1 Agora ⚡, Histórico do Robô 📋 (as tentativas das últimas 24 h e em que passo pararam; às 22h chega o resumo do dia no privado), Edição dos Vídeos ✂️ (o exemplo no privado, a cada toque o próximo vídeo que o robô pegaria; ligar ou desligar; `edicao_video.py`), rascunhos por dia, Horário do Robô (preparar e postar), Horário das Interações 💬 (responder os comentários e o feed, separado do de postar), Testar Caminho 🧭 e Celular do Robô 📱, com o Passo a Passo 📖 para refazer tudo depois de resetar o celular e o Ver Tela do Celular 🖥️, que manda no privado o link da tela do celular; config na chave `shopee_video`): routers aiogram incluídos no bot_mestre. O `painel_acessos.py` (Opções do Servidor → Acessos do Servidor 🔐) também: mostra onde entrar no Tailscale e na Oracle, com os dados que o Rafael cadastra pelo bot (chave `acessos_servidor`; nunca no código nem no log). O `painel_ia.py` (Opções do Servidor → IA 🤖) também: o Claude IA 🧠 manda o link desta conversa (`LINK_CLAUDE`; se a conversa mudar, trocar ali).
- `robo_shopee_video.py`: o robô automático da Shopee Vídeo, no celular guardado do Rafael. O painel o chama a cada 15 min numa unidade própria do systemd (`sudo systemd-run`, log no journal como `robo_shopee_video`; o reinício do bot não a mata, e a trava do celular segura a próxima; sem o sudo, vira processo do bot) (`--rodada`; `--treino` no botão Testar Caminho 🧭; `--preparar` no Preparar 1 Agora ⚡, um rascunho a mais na hora): prepara rascunhos sozinho (faixa por dia e Horário do Robô, chaves `robo_*` de `shopee_video`; no vídeo de link de produto, troca o produto pelo mesmo de outra loja que paga mais comissão, achado na API e conferido pela IA com o vídeo, P33), e o Rafael aprova um por um em Rascunhos do Robô 📝 (vídeo, print da tela final, título, produto e link, origem do vídeo e o que a IA conferiu); só então ele posta, espalhado no horário. Tabelas `shopee_video_rascunhos` e `shopee_video_tentativas` (o histórico: cada tentativa, o resultado, o passo em que parou, o motivo e o produto, por 3 dias; o rascunho do plano que não dá certo tenta 3 vezes o mesmo vídeo e passa a outro, até 3 vídeos por horário, e cada tentativa que não sai gera aviso no privado; no fim de cada rascunho, salvo ou não, descurte os produtos que curtiu para ele, e às 4h, numa hora só disso, descurte tudo em Meus favoritos de afiliado: Eu → Criadores & Afiliados → Meus favoritos → marcar → Like); o mapa das telas fica nos `CAMINHO_*` dele e no roteiro. Um cobre o outro: com o robô ativo, o assistente fica em espera; sem o celular (o `celular_robo.reconectar_sozinho` acha a porta nova da Depuração por Wi-Fi, mas não liga a depuração), o robô pausa sozinho e o assistente volta. Com a conta de Shopee Vídeo suspensa pela Shopee (o robô lê a data nas Notificações do app quando o Postar vídeo não abre e antes de postar; chave `robo_suspenso_ate`), o robô não prepara, não posta e não treina até o fim (o resto segue no horário de sempre, e com o celular fora só pula), o assistente espera, e os dois voltam sozinhos, com aviso no privado (o treino da segunda que caiu na suspensão roda logo no fim, P41). O robô também lê a Saúde do Vídeo (`--saude`, pelo botão Gerar Apelação ⚖️; e uma vez por dia, na suspensão e no aviso de penalidade): as punições vão para o `apelacoes_shopee_video.py`.
- `edicao_video.py`: a edição dos vídeos da Shopee Vídeo como o Rafael faz à mão (a foto do anúncio do produto nos primeiros 2 s e, até o fim do vídeo, uma miniatura dela no canto de cima à direita e a seta vermelha do arquivo dele embaixo à esquerda, sem o fundo, do começo do vídeo, logo depois da foto, pulsando até o fim (`midia/seta_da_shopee.apng`), nas posições que ele usa no LumaFusion; montada no `videos.py`), nos vídeos de todas as fontes do robô (`FONTES_COM_EDICAO`; o Rafael confirmou que todos os grupos e vídeos dele são autorais); nos de Ver Produtos, com a foto do 1º produto anexado, achada na API pelo nome (`foto_do_ver_produtos` do robô, P39). Começa desligada (chave `edicao_ligada` de `shopee_video`); o robô a aplica na cópia que vai ao rascunho e, com ela ligada, só vai vídeo editado: o que não sai editado fica de lado (`MOTIVO_SEM_EDICAO`) e o robô pega o próximo.
- `casos_robo.py`: o caso completo de cada tentativa do robô da Shopee Vídeo que não deu certo, para o Claude analisar: o motivo inteiro e o passo, o vídeo em quadros (`videos.quadros`), o título e o comentário da IA, os produtos e o que a IA conferiu, o print e a forma da tela do celular (só lendo, e só depois que o rascunho usou o celular). Fica em `~/shopee_video/casos` no servidor, no máximo 30 casos e 3 dias. O `casos_robo.yml` (`exportar`) leva os casos cifrados (a chave do `registro_privado`) ao ramo `casos-robo`, um commit só; para ler: `git fetch origin casos-robo`, `git show origin/casos-robo:casos.zip.cifrado > ARQUIVO` (no scratchpad) e `python3 casos_robo.py ler ARQUIVO PASTA` (no scratchpad, nunca no repositório). Depois de analisado e resolvido, `casos_robo.yml` com `apagar` tira tudo, do servidor e do ramo. O conteúdo aberto nunca vai para commit, PR, comentário ou log.
- `interacoes_shopee_video.py`: o que o robô da Shopee Vídeo lê e escreve para responder os comentários dos vídeos do Rafael (uma vez por dia, pelas Notificações, só os novos, conferindo que a resposta ficou embaixo do comentário certo) e curtir e comentar 3 vídeos de outros criadores por dia no feed Live e Vídeo → Para você (pula lives e os vídeos dele). Os toques ficam no `robo_shopee_video`; as marcas do que já foi feito (tabela `shopee_video_interacoes`, só SHA-1, nunca nome nem texto) impedem responder ou comentar duas vezes; o checkup aponta resposta no lugar errado, comentário sem resposta, resposta duplicada e a meta do feed.
- `apelacoes_shopee_video.py`: as punições da Shopee Vídeo (tabela `shopee_video_punicoes`, lida pelo robô na Saúde do Vídeo) e o texto do recurso de cada uma (IA, até 200 caracteres, só fatos). O bot_mestre manda no privado e lembra de hora em hora, a qualquer hora, até Já recorri ou Não vou recorrer (botões na mensagem); Relatório Geral 📊 → Saúde da Shopee Vídeo 🩺 mostra a suspensão, os pontos de penalidade e as punições, o texto de cada uma ainda sem recurso para copiar e o Gerar Apelação ⚖️.
- `assistente_shopee_video.py`: o modo assistente da Shopee Vídeo. Prepara cada postagem (vídeo da fonte escolhida: Autorais, Viral, Canal Afiliados ou Grupo Público; título e comentário pela IA com o prompt do Gem do Rafael e as diretrizes (recusado pelo Google pelo conteúdo, pede de novo com as mesmas regras em palavras leves, `TROCAS_LEVES`, e o vídeo recusado chega no privado do Rafael com o que o Google disse, `texto_da_recusa`), produtos pela API) e manda no privado do Rafael, que posta pelo celular. Com a edição ligada (`edicao_video`), manda o vídeo já editado e deixa de lado o que não sai editado, tentando o próximo (até `VIDEOS_POR_ENVIO`; P40). O painel agenda a cada 5 min; o plano do dia fica na chave `shopee_video_dia`, e o que já foi mandado na tabela `shopee_video_enviados`.
- `utils.py` (`erros_logs`, caches, validação de IDs) e `fuso.py` (horário de Brasília e formato de log).
- `api_gemini.py` (IA, com cascata de modelos) e `api_shopee.py` (links de afiliado; cada robô marca os seus com a própria etiqueta, as `ETIQUETA_*`).
- `vendas.py`: a comissão por canal (a etiqueta do link) e por produto, pelo relatório de vendas que o bot puxa de hora em hora; toda segunda às 09:13 o relatório da semana chega no privado do Rafael. Valores e nomes de produto só no banco e no privado.
- `links_shopee.py`: acha link da Shopee em texto e mensagem (`primeiro_link`, `extrair_link_shopee`, `codigo_do_link_curto`) e dá a identidade do produto (`chave_produto`), igual em todos os robôs e no checkup. Nunca escrever outra receita de link: o `tests/test_links_shopee.py` barra cópia. O que se repete entre robôs vai para um módulo assim (DECISOES.md, Código e manutenção).
- `legendas.py`: a legenda dos posts de vídeo (`legenda_da_ia`, `legenda_so_link`, `legenda_sem_nome`, com o nome escapado no HTML; e o padrão do Grupo Público, `legenda_grupo_publico`: quem postou, nome, blocos SHOPEE e TIKTOK e hashtags), o pedido de nome e hashtags à IA (`PROMPT_NOME_E_HASHTAGS`, com o emoji no fim do nome em todos os robôs) e a leitura do nome de volta (`nome_da_legenda`, usada pelo assistente da Shopee Vídeo). O `tests/test_legendas.py` barra cópia da lista de hashtags ou do prompt.
- `videos.py`: arquivo de vídeo tratado igual em todos os robôs: `dimensoes` (ffprobe), `verificar_e_otimizar_video` (vídeo abaixo de 720 px re-renderizado em 720x1280 no mesmo caminho) `calcular_hash_video` (SHA-256 que reconhece o mesmo vídeo) e `com_foto_e_miniatura` (a edição do `edicao_video`). O `tests/test_videos.py` barra cópia.
- `teclados.py`: o teclado fixo embaixo da conversa (`montar_teclado`) e os teclados que vários painéis usam iguais, para o bot_mestre e os painéis em arquivo próprio. O `tests/test_teclados.py` barra teclado montado à mão e cópia dos repetidos.
- `exemplos.py`: os exemplos das perguntas de configuração dos painéis com o que está valendo agora (`faixa_e_fixo`, `janela`, `exemplo`; do outro jeito, o último que o Rafael mandou, na chave `exemplos_dos_paineis`). Pergunta nova com exemplo de configuração sai por ele.
- `links_grupos.py`: o nome de grupo ou canal nos painéis como atalho para abri-lo (`nome_clicavel(nome, alvo)`). Os userbots guardam o @, a última mensagem e o convite de cada grupo (tabela `links_grupos`) ao ler as conversas da conta; o bot guarda o @ ao validar um alvo. Nome de grupo novo em painel sai sempre por ele. `arroba(alvo)` dá o @ público do grupo ou canal (usado no crédito do parceiro sem @ cadastrado).
- `repetidos_publico.py`: vídeos que já foram ao Grupo Público (tabela `videos_no_publico`, pelo arquivo do Telegram e pelo SHA-256), para o mesmo vídeo não ir de novo quando a origem dos Autorais o posta outra vez. Usado pelo sorteio do Público (espelhador dos Autorais) e pelo botão Disparar Repost Autoral (bot_mestre).
- `fila_espelhador.py`: a fila do Espelhador no banco, gravada sem um robô apagar o que o outro gravou (detalhes em "Dados"). O `motor_userbot` passa o antigo `fila_espelhador.json` para o banco ao ligar; o `tests/test_fila_espelhador.py` barra quem voltar a usar o arquivo.
- `rotas_espelhador.py`: as rotas do Espelhador no banco, do mesmo jeito (detalhes em "Dados"); o `tests/test_rotas_espelhador.py` barra quem voltar a usar o `espelhos_config.json`.
- `registro_admins.py` (coleta pela conta principal no `divulgacao_canal`, todo dia às 04:20) e `painel_admins.py` (Opções do Servidor → Administradores 🛡️; o bot_mestre avisa no privado quando muda): quem administra cada grupo e canal em que o Rafael é dono ou admin, com as permissões. Nomes ficam só no banco e, cifrados, no ramo `registro-admins`.
- `registro_privado.py`: a cópia cifrada do registro dos administradores no ramo `registro-admins` deste repositório (arquivo `administradores.md.cifrado`), para o Claude ler quando precisar. O workflow `registro_admins.yml` roda `registro_privado.py cifrado` no servidor todo dia às 05:47 e grava no ramo só quando mudou. A chave fica só no servidor (`~/.config/registro_admins.chave`), no privado do Rafael (o bot manda uma vez por chave) e no ambiente do Claude (`REGISTRO_ADMINS_CHAVE`). Para ler: `git fetch origin registro-admins`, `git show origin/registro-admins:administradores.md.cifrado > ARQUIVO` (no scratchpad, nunca no repositório) e `python3 registro_privado.py ler ARQUIVO`; para uma cópia de agora, disparar o `registro_admins.yml` antes. O texto aberto nunca vai para commit, PR, comentário ou log.
- `faxina_viral.py`: a faxina do Acervo Viral, que roda no `divulgacao_canal` com a conta principal (dona do canal), como a faxina do Baixador: vídeo com mais de 7 dias ou com o produto fora da Shopee (duas conferências na API) sai. O resumo fica na chave `faxina_viral`, que o `/status` e o monitor de saúde do bot_mestre leem.
- `registro_processos.py`: o registro de cada processo dos robôs (robô, processo, resultado e motivo fixo do código; nunca link, nome ou quem pediu), 3 dias no banco (tabela `registro_processos`) e depois sai sozinho. O checkup e o diagnóstico contam esse registro. Processo novo de robô anota por ele (`registrar(robo, processo, resultado, detalhe, ok)`); anotam: o Baixador (cada pedido), as postagens do canal principal, Viral, Grupo Público e Parceiros, as rotinas de texto (canal, assunto e tópico), o backup, os Autorais (captura, repostagem, captura dos parceiros e Correio Público), o Espião (captura), o Espelhador (envio), a divulgação (cada envio, com o grupo como apelido), as notas fiscais e o assistente da Shopee Vídeo; os jobs de manutenção anotam cada execução pelo decorador `anotar`. `origem` guarda o grupo, alvo ou tópico só como apelido (8 caracteres do SHA-1). O `tests/test_registro_processos.py` barra robô que não anota.
- `rotinas.py`: em que canal sai cada rotina de texto (`canal_da_rotina`) e quais o código conhece (`conhecida`: chave antiga no banco, sem texto, não é agendada nem disparada), usado pelo bot_mestre e pelo checkup. Rotina nova entra na lista dela e ganha o texto no `disparar_mensagem` (o `tests/test_rotinas.py` confere).
- `conferencia_espiao.py`: depois que o clone sai no Viral, o bot_mestre compara o nome que a IA do Espião deu com o nome do produto na API de afiliado e anota no registro se confere (não muda o post).
- `moderacao_publico.py`: a verificação semanal das mensagens dos membros no Grupo Público (segunda 07:47, pela conta principal no `divulgacao_canal`): links que não são da Shopee, convites de outros grupos e flood sem IA; ofensa, golpe e conteúdo adulto ou ilegal pela IA. Só avisa no privado do Rafael (quem, link da mensagem, regra, motivo); nada é apagado. No banco (chave `moderacao_publico`) e no checkup, só números.
- `perguntas_rafael.py`: as perguntas do Claude ao Rafael no privado do bot, lembradas de hora em hora até ele responder (tabela `perguntas_rafael`, código P1, P2...). Cada aviso traz a pergunta, as opções, o texto para copiar com um toque e o link da conversa. O Claude cifra o JSON (`perguntas_rafael.py cifrar ARQUIVO`, com a `REGISTRO_ADMINS_CHAVE`) e manda pelo `avisar.yml` (`acao=pergunta`); o bot_mestre lembra a cada hora (`lembrar_perguntas_do_claude`) até o `avisar.yml` com `acao=respondida`, que apaga do privado a pergunta e os lembretes dela (os ids ficam na coluna `mensagens`).
- `alertas.py`: os erros graves avisados na hora no privado do Rafael (robô fora do ar, disco acima de 90%, backup atrasado, erros demais na última hora, robô da Shopee Vídeo sem rodar), uma vez e de novo depois de 6 h se continuar, com o "voltou ao normal". Roda pelo `diagnostico.yml` de hora em hora (seção "Graves agora", só rótulos); os robôs avisam os graves que eles mesmos veem.
- `backup_dados.py`: backup diário (03:40, pelo bot_mestre) do banco, das sessões, dos JSON e do `.env` em `~/backups`, ficam 7. O `/status` mostra a idade do último.
- Ferramentas: `validar_deploy.py`, `testar_chaves.py`, `inventario.py`, `checkup.py` (o checkup do dia, pelo `checkup.yml`), `avisar_rafael.py` (aviso no privado pelo bot, usado pelo `avisar.yml`), `servicos_afetados.py` (o deploy pergunta a ele quem reiniciar), `faxina_servidor.py` (tira tabelas, chaves e arquivos sem uso, guardando cópia antes) `android_virtual.py` (o Android virtual do robô da Shopee Vídeo: Redroid em Docker, adb só em 127.0.0.1), `tela_android.py` (a tela desse Android no navegador, por 30 min, com o link só no privado do Rafael; o botão "Enviar app" instala um app baixado no celular dele, e há botões, com confirmação, para fechar os apps, reiniciar o Android e resetar de fábrica; com `--celular`, a tela é a do celular guardado, só com toques, texto e teclas, aberta pelo bot ou quando o explorar no celular para numa verificação, e o explorar não mexe no celular enquanto ela está aberta) e `postador_shopee_video.py` (explora as telas do app da Shopee nesse Android, ou no celular guardado com `--celular`, mostrando a forma delas no log; Postar só pelo passo `postar`, na tela final conferida e depois do OK do Rafael no print; o passo `print` manda a tela só no privado do Rafael, pelo `avisar_rafael.mandar_foto`; os passos `ia`, `produto` e `conferir` conferem que o produto anexado é o do vídeo, e o toque em Rascunhos só sai com a tela final conferida). O `celular_robo.py` liga o servidor ao celular guardado do Rafael pela rede privada (Tailscale + adb da Depuração por Wi-Fi): acha o celular na rede, pareia com o código que o Rafael manda no bot (Shopee Vídeo 🎬 → Celular do Robô 📱; o código nunca vai para log nem banco) e conecta; os dados ficam na chave `celular_robo`. O Android virtual está apagado e desligado desde 05/10/2026; o explorar e o robô automático usam o celular guardado (`--celular`), com uma trava para nunca tocarem juntos. O `roteiro_robo_shopee_video.md` diz o que se sabe do app e o que falta mapear.
- `diretrizes_shopee_video.md`: resumo das diretrizes da Shopee Vídeo que o robô dela sempre segue; a IA recebe o resumo com cada vídeo.

O README tem os IDs dos canais, as cinco filas e os comandos do servidor.

## Onde fica cada coisa no bot_mestre.py

São 17 mil linhas. Navegue pelos marcadores de seção, que não mudam quando o
arquivo cresce: `grep -n "^# --- " bot_mestre.py`. Os blocos grandes usam
`# ===` com o título na linha seguinte. Exemplos:

- `--- Estados (FSM) ---` e `--- Teclados ---`: estados e teclados de todos os fluxos. Teclado novo sai do `teclados.py` (`montar_teclado(linhas)`, `teclado_com_cancelar`, e os repetidos `teclado_cancelar`, `teclado_aprovar_cancelar` e `teclado_janela_dia_todo`), no `bot_mestre` e nos painéis em arquivo próprio: todos ficam fixos embaixo da conversa. O `tests/test_teclados.py` barra `ReplyKeyboardMarkup` escrito à mão.
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
- Contas (dentro do menu Vídeos Autorais): bloco `=== Painel de Contas`, `--- Nova conta pelo bot ---` e o painel de pessoas bloqueadas.
- Fim do arquivo:
  - `--- Monitor de saúde ---`;
  - `--- /status ---`;
  - `--- main() ---`: agenda todos os jobs.

## Dados

- `banco_dados.db` (SQLite), sempre pelo `db.py`:
  - Sempre `with db.conexao() as conexao:` (`linhas_por_nome=True` para `linha["coluna"]`): grava no fim, desfaz se der erro e fecha sempre.
  - Gravou dentro do `with` e vai esperar um `await` (envio ao Telegram, download)? `conexao.commit()` antes: gravação pendente segura o lock dos outros robôs.
  - Nunca `sqlite3.connect` nem `db.conectar()` fora do `db.py`: o `tests/test_db.py` barra.
  - O banco fica em modo WAL: leitura e gravação não se bloqueiam. Os arquivos `banco_dados.db-wal` e `-shm` fazem parte do banco.
  - `configuracoes` (chave → JSON): `db.ler_config` e `db.salvar_config`, os mesmos em todos os robôs. Chave que dois robôs gravam: `db.atualizar_config` (lê, altera e grava sem perder a gravação do outro).
  - Filas em tabelas: `fila_postagens` (canal principal), `fila_autorais`, `fila_publico`, `fila_parceiros` e `fila_notas`.
  - A fila do Espião (`fila_clonagem`) é uma chave de `configuracoes`.
  - `erros_logs`.
  - Pool: `contas_telegram`, `funcoes_contas` e `atividade_contas`.
- A fila do Espelhador de canais é a chave `espelhador_fila` de `configuracoes`, sempre pelo `fila_espelhador.py` (`ler`, `atualizar`, e `fotografar` + `gravar_mudancas` para quem mexe nela por muito tempo).
- As rotas do Espelhador são a chave `espelhador_rotas`, sempre pelo `rotas_espelhador.py`: `ler`, `salvar` (o painel, que lê e grava sem esperar nada no meio) e `atualizar` (quem passa tempo com as rotas na mão, como o motor_userbot, grava só o que mudou). O `motor_userbot` passa o antigo `espelhos_config.json` para o banco ao ligar.
- Nada disso está no git: o `.gitignore` cobre `*.db`, `*.json`, `*.session` e `.env`. No servidor, o backup diário (`backup_dados.py`) guarda essas coisas em `~/backups`.

## Armadilhas conhecidas

- Importar `db` (o `utils` importa) troca o `sqlite3.connect` do processo inteiro, para as sessões do Telethon também esperarem 30 s pelo lock. Importar `fuso` trava o fuso no horário de Brasília.
- Os jobs do APScheduler e o FSM do aiogram ficam em memória.
  - Um restart refaz a grade do dia em `main()`. O deploy só reinicia o robô cujo código mudou.
  - Também derruba os fluxos de painel que estavam abertos.
  - A contagem dos 15 min que devolve o Painel Inicial fica também no banco (chave `inatividade_painel_admin`), e o `main()` a rearma ao ligar.
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
  - `deploy.yml` roda no merge na `main`. Ele repete a validação e, por SSH, faz `git pull` e `pip install` no servidor. Reinicia só os serviços cujo código mudou (o arquivo do robô ou um módulo que ele importa; `requirements.txt` ou dúvida = todos; só docs, testes, workflows, comentários ou a mídia de `midia/` = nenhum). Confere os 5 aos 25 s e de novo 3 min depois (processo e contador de reinícios). Robô que cai mostra só o tipo do erro no log.
  - `diagnostico.yml` olha o servidor de hora em hora, só lendo: robôs (estado, desde quando, reinícios), máquina (carga, memória, disco), banco, volume de log, links que saíram sem a marcação de afiliado (contagem por robô e motivo), as tentativas do robô da Shopee Vídeo nas últimas 24 h por resultado e por passo em que pararam (sem produto nem motivo), e as linhas "Robô agora" para a retomada (`checkup.py robo-agora`: paradas, erros e pulados nas últimas 3 h e 12 h, com a hora, e os aprovados que passaram da hora de ir ao ar), se a Shopee ainda bloqueia o download da Shopee Vídeo no Baixador (situação e conferência semanal, às segundas às 7h17) e os números da faxina do Acervo Viral e do registro dos administradores (sem nomes). No fim, os "Graves agora" (`alertas.py`, que avisa o Rafael na hora; o único passo que grava: o que já foi avisado). Fica vermelho com robô fora do ar ou disco acima de 90% (o GitHub manda e-mail). Para ver o servidor agora, dispare-o (`run_workflow` em `diagnostico.yml`) e leia o log do job.
  - `inventario.yml` (só à mão) roda o `inventario.py` no servidor. Ele mostra:
    - tamanho e idade de cada pasta, os arquivos soltos e as linhas por tabela;
    - os erros do `erros_logs` por origem e tipo de exceção (sem o texto) e as versões das bibliotecas;
    - as configurações mais pesadas e o histórico da fila do Espelhador;
    - o espaço do journal e as linhas de log que mais se repetem, com arquivo:linha do código;
    - os caches e a memória de cada robô.
    Use para achar o que acumula.
  - `checkup.yml` (todo dia às 22:20 e à mão) roda o `checkup.py` no servidor: erros das últimas 24 h com o lugar do código que os gravou (e se são novos), quedas, rastros (quantos depois do último início, para saber se o deploy corrigiu), avisos e erros no log de cada robô por lugar do código, processos dos robôs (o `registro_processos`: acertos, falhas e motivos), rotinas de texto por canal e divulgação por grupo (espaçamento, mesmo assunto em seguida, o que saiu contra o configurado, com a linha do tempo do registro, rajadas; chave antiga do banco não conta), captura por grupo de origem pela posição na lista do painel (Espião, Espelhador, parceiros: quem não mandou vídeo e quem parou), produto repetido entre parceiros ou com a conta principal (3 dias), a conferência do nome da IA do Espião (no registro), a verificação semanal do Grupo Público (só números; cobra se passar de 8 dias sem rodar), postagens de hoje por fila (atrasos e média dos 7 dias), robô da Shopee Vídeo (horários vencidos, rascunhos salvos e pulados, onde parou, aprovados que passaram da hora de ir ao ar), sobreposições (o robô fazendo outra coisa na hora do descurtir, interação fora do Horário das Interações e preparo dentro dele antes do feed, contados só depois da hora em que o Rafael escolheu a janela, rotinas de texto coladas no mesmo canal e os envios do modo assistente), Baixador e backup. Os rastros de erro saem pelo tipo e pelo lugar do código. Mostra a meta de cada job (esperado × feito em 24 h, a lista `METAS`; o que acontece só quando há o que fazer fica em `SEM_META`, e o `tests/test_checkup.py` barra processo novo de robô fora das duas). Termina com os "Pontos de atenção", cada um marcado como novo, repetido há N dias ou que voltou (a correção não funcionou; memória na tabela `checkup_pontos`), e os resolvidos desde o checkup anterior; a rotina do checkup diário investiga.
  - `registro_admins.yml` (todo dia às 05:47 e à mão): guarda o registro dos administradores cifrado no ramo `registro-admins` (detalhes no `registro_privado.py`); o log diz só se mudou.
  - `avisar.yml` (só à mão): fala com o Rafael no privado do bot. `acao=aviso`: o lembrete diário das pendências (`assunto` curto e sem dado privado, `avisar_rafael.py`). `acao=pergunta`: uma pergunta do Claude, cifrada em `dados` (`perguntas_rafael.py`); o log mostra só o código (P…). `acao=respondida`: `dados` = o código; os lembretes param.
  - `investigar_baixador.yml` (só à mão, entrada: o código do vídeo, o que vem depois de `share-video/`, `curto:CÓDIGO` do link `br.shp.ee/CÓDIGO`, como o membro cola, `ultimo`, o último vídeo pedido ao Baixador, lido no servidor sem aparecer no log, ou `apify`, o caminho pela Apify) roda o `investigar_baixador.py` no servidor: abre a página da Shopee Vídeo como o Baixador abre, mostra só a forma dela (status, tamanhos, caminhos das chaves de vídeo no JSON) e roda o download de verdade, com o tamanho ou o erro. Nunca links, nomes ou textos.
  - `chave_apify.yml` (só à mão): grava no `.env` do servidor a chave da Apify (segredo `APIFY_TOKEN`), que o Baixador usa para pedir ao serviço da Apify os vídeos da Shopee Vídeo quando a Shopee bloqueia, e testa com o `investigar_baixador.py apify` (a chave, o crédito do mês e o último vídeo pela Apify). Rodar de novo troca a chave.
  - `investigar_robo.yml` (só à mão, entrada: quantos vídeos da fonte conferir) roda o `investigar_robo.py` no servidor: segue o link dos vídeos que o robô da Shopee Vídeo pulou e dos próximos da fonte do painel, como o robô segue, e mostra por que tipos de página ele passou, se chegou a um produto ou a um vídeo (Ver Produtos), se a API de afiliado devolve a oferta e, nos próximos, se a busca acha o mesmo produto pagando mais (P33, só números). Antes, cada tentativa das últimas 24 h que não deu certo, com a hora, o passo e a forma do motivo (o texto fixo do código, com "…" no que muda). Só tipos, contagens e o passo em que cada pulado parou, com o motivo quando ele é um texto fixo do código; nunca links, nomes ou motivo com dado do vídeo.
  - `video_ia.yml` (só à mão) roda o `video_ia.py` no servidor: `modelos` mostra os modelos de vídeo (Veo) que a chave do Google enxerga, sem custo; `testar` gera 1 vídeo de uns 8 s, feito por IA a partir da foto do anúncio do próximo produto da fonte, e manda só no privado do Rafael (teste da P34; nada é postado, custa menos de US$ 1). O log tem só nomes de modelo, estados e números.
  - `casos_robo.yml` (só à mão): `exportar` leva cifrados ao ramo `casos-robo` os casos das falhas do robô da Shopee Vídeo (`casos_robo.py`); `apagar` tira tudo, do servidor e do ramo, depois de analisado e resolvido. O log diz só quantos casos.
  - `faxina.yml` (só à mão) roda o `faxina_servidor.py` no servidor: sem marcar "executar", só mostra; marcado, guarda em `~/backups/antigos` e tira. Para tirar outra coisa sem uso, acrescentar na lista do `faxina_servidor.py` depois de conferir que nenhum código usa.
  - `modelos_ia.yml` (só à mão): quais modelos do Gemini a chave do servidor enxerga e, com "testar", se cada um responde (uma chamada curta); compara com a cascata do `api_gemini.py` e mostra à parte os descontinuados que a chave ainda enxerga (lista `DESCONTINUADOS`, que não voltam). Só nomes de modelo e motivos fixos. Rodar antes de mexer na cascata; a rotina "Modelos do Gemini" roda toda segunda.
  - `android.yml` (só à mão) roda o `android_virtual.py` no servidor, com a ação escolhida: `estado` (só mostra), `preparar` (instala o Docker e o adb, carrega o binder e liga o Android, só o que falta), `instalar-loja` (instala a Aurora Store, pela qual o Rafael instala a Shopee do Google Play na tela), `instalar-shopee` (tenta baixar o app de sites de APK, que recusam o servidor), `tela` (abre a tela no navegador; o link vai no privado do Rafael, nunca no log), `explorar` (roda o `postador_shopee_video.py --explorar` com os `passos` do campo de texto, ex.: `abrir; tocar:Eu`, e descreve cada tela sem os textos da conta), `explorar-celular` (o mesmo, no celular guardado, conectado pelo bot), `desligar` (desliga o Android sem apagar o app nem o login; o `preparar` religa), `apagar` (desliga e apaga apps e login, como reset de fábrica) ou `tailscale` (liga o servidor à rede privada do celular de verdade do plano B, com a chave do segredo `TAILSCALE_AUTHKEY`; não mexe no DNS nem nas rotas).
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
- Opções oferecidas ao Rafael ficam abertas até ele escolher, mesmo que ele demore:
  - oferecer pelo seletor de opções (`AskUserQuestion`), não só em texto;
  - se o seletor sumir sem resposta (ex.: uma chamada agendada chegou antes), mostrar as mesmas opções de novo na próxima resposta;
  - nunca escolher por ele por causa da demora. Até ele responder, fica valendo o que já estava.
- Nunca presumir como um robô deve se comportar:
  - toda escolha que mudaria o que um robô faz, mesmo pequena (ex.: o texto pedido à IA, o formato de um post), vira pergunta ao Rafael no fim do trabalho, pelo seletor de opções;
  - a parte que depende da resposta não vai ao ar antes dela (o PR espera); o resto segue;
  - pergunta sem resposta entra na lista do "Lembrete diário: tudo o que o Rafael tem pendente" (`update_trigger`) e sai quando ele responder.
- Investigação que depende de esperar o servidor (contagem, log, diagnóstico novo, correção que só se confirma com o uso):
  - o Rafael não precisa lembrar de conferir. Ao subir a mudança, agendar eu mesmo a conferência (`send_later`) para quando o resultado já deve existir (ex.: na manhã seguinte, se o canal posta de dia);
  - na conferência: ler o resultado (inventário, diagnóstico, `/status`) e concluir a causa;
  - resultado claro = corrigir e subir sozinho, do começo ao fim (PR, CI, merge, deploy), sem pedir aprovação. Esperar o Rafael só em dúvida de verdade (intenção, regra do diário). Se a solução depende de algo que só ele faz (ex.: pôr uma conta num canal), dizer exatamente o quê;
  - dizer ao Rafael quando será a conferência. Sem resultado ainda, reagendar e avisar o novo horário. No fim, avisar o que foi achado e feito.
- Retomada automática (o crédito pode acabar no meio de um pedido, e eu não volto sozinho):
  - a rotina "Retomar trabalho pela metade (a cada 3 h, 8h–20h)" chama esta conversa às 8h, 11h, 14h, 17h e 20h de Brasília;
  - em cada chamada, conferir se algo ficou pela metade: pedido sem "✅ Concluído", mudança sem commit ou push, PR aberto, CI ou deploy não acompanhado até o verde, conferência que não rodou, tarefa pendente, opções oferecidas sem resposta (mostrar de novo);
  - em cada chamada, ler também a seção "Links sem conversão" do último `diagnostico.yml` (às 8h, a janela de 12 h; nas outras, a de 3 h). Havendo link que saiu sem a marcação de afiliado, investigar o motivo pelo robô e pelo tipo/código, consertar e subir sozinho quando o conserto é de código; quando depende do Rafael (ex.: chaves da Shopee recusadas), dizer exatamente o quê. Falha passageira que as 3 tentativas do robô não venceram e não se repete não pede conserto;
  - em cada chamada, ler também a seção "Graves agora" do último `diagnostico.yml` (o `alertas.py` já avisou o Rafael na hora): cada grave é investigado e corrigido nessa retomada, sem esperar o checkup da noite;
  - em cada chamada, ler também as linhas "Robô agora" do último `diagnostico.yml` (pedido do Rafael em 25/10: reconhecer as falhas e corrigir sem ele pedir; às 8h, a janela de 12 h; nas outras, a de 3 h): cada parada ou erro do robô da Shopee Vídeo, o pulado que se repete no mesmo passo e o aprovado que passou da hora de ir ao ar (com a Postagem ativa) são investigados como no checkup diário (caso completo pelo `casos_robo.yml`, causa, correção do PR ao deploy, `apagar`), nessa retomada;
  - havendo algo, continuar de onde parou, seguindo as regras daqui; não havendo, só responder "Nada pendente." (sem aviso no Telegram);
  - chamada que cai sem crédito não roda; a próxima, com crédito, retoma.
- Checkup diário (rotina "Checkup diário", 22:43, nesta conversa):
  - ler o último `checkup.yml` (disparar um se o das 22:20 não rodou), o `diagnostico.yml` e os deploys do dia;
  - cada ponto de atenção: achar a causa com dados verificáveis e corrigir sozinho (PR, CI, merge, deploy), como na conferência agendada. Comportamento de robô continua indo ao Rafael pelo seletor;
  - falha do robô da Shopee Vídeo (pulado, parou, erro): ler o caso completo (`casos_robo.yml` exportar, abrir no scratchpad), achar a causa e corrigir; resolvido, `casos_robo.yml` apagar (pedido do Rafael: nada acumula);
  - o que não deu para conferir pelos números (falta contagem, estado ou lugar do código): mudar o `checkup.py`, o robô ou o diagnóstico para a próxima rodada mostrar, sempre só números, estados e trechos fixos do código;
  - no fim, uma tabela curta ao Rafael: o que foi conferido, o que deu errado, o que foi corrigido e o que ficou com ele. Dia sem nada: uma linha só.
- Modelos do Gemini (rotina "Modelos do Gemini (toda segunda)", 10:17, nesta conversa; P36):
  - pesquisar nas páginas do Google (descontinuação, notas de versão, modelos) e rodar o `modelos_ia.yml` com "testar";
  - tirar da cascata todo modelo descontinuado, mesmo o que ainda responde redirecionado, e pô-lo em `DESCONTINUADOS`;
  - pôr os modelos novos de texto que a chave enxerga e respondem, o melhor primeiro (modelo de vídeo, imagem ou voz não entra: `FORA_DOS_ROBOS`);
  - subir do PR ao deploy sem perguntar e avisar numa tabela curta, com as fontes; semana sem mudança: uma linha só.
- Toda pergunta ao Rafael tem de ser respondida: nunca passa despercebida nem expira.
  - Toda pergunta do seletor vai também, na hora, para o privado do bot: um JSON no scratchpad (`pergunta`, `opcoes` com `rotulo` e `descricao`, a recomendada primeiro, e `link` = link da sessão), `python3 perguntas_rafael.py cifrar ARQUIVO`, e o `avisar.yml` com `acao=pergunta` e `dados` = o texto cifrado. Ler no log o código (P…).
  - O bot lembra de hora em hora, a qualquer hora (de dia e de noite), sozinho no servidor, mesmo sem crédito do Claude.
  - O Rafael responde pelo seletor ou colando aqui o texto do aviso (começa com "[P…] Vc me enviou anteriormente a pergunta"). Respondida: `avisar.yml` com `acao=respondida` e `dados` = o código, e ela sai da lista do lembrete diário.
  - Seletor que some sem resposta: mostrar a mesma pergunta de novo na resposta seguinte. Pergunta aberta fica na lista do lembrete diário.
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
  - Pedido concluído (incluir, editar ou excluir algo nos robôs): no fim da resposta, um bloco "✅ Concluído", mesmo que outras ações ainda estejam em andamento. Ele diz que aquele pedido terminou e traz:
    - o que foi feito;
    - o impacto para o Rafael (o que muda no uso dos robôs);
    - onde achar no bot (caminho do menu, ex.: Outros Canais → Vídeos Autorais 🎥 → Contas 👥).
  - Se o Rafael disser para não fazer o merge, não fazer.
  - Se o Rafael mandar fazer o merge direto, sem esperar o CI, obedecer.
  - Se o Rafael pedir rodadas extras (ex.: "faz 5 rodadas"), repetir o CI quantas vezes ele pedir, com o intervalo que ele disser (padrão: 5 min), avisando posição e horário da próxima.
- O repositório é público:
  - nunca commitar credencial, `.env`, sessão ou banco;
  - nos testes, nada com cara de token (o GitGuardian acusa).

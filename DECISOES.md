# Diário de decisões

Os pedidos do Rafael que definem como os robôs se comportam, inclusive as
exceções que o código sozinho não explica ("parece bug, mas é de propósito").
Leia a área antes de mudar qualquer comportamento dela.

## Como usar

- Cada decisão fica na área dela, com a data: o que foi pedido e, quando houver, o porquê.
- **Exceção** marca o que foge de um padrão que vale para os outros robôs.
- Pedido novo que contradiz um antigo: o antigo fica ~~riscado~~ com "substituída em DD/MM/AAAA", e o novo entra logo abaixo. Nunca apagar, porque o histórico mostra que o desejo mudou.
- Contrariar uma decisão daqui só com pedido explícito do Rafael. Na dúvida se um pedido novo contradiz um antigo, perguntar antes.
- Quando a decisão é uma exceção no código, um comentário curto no lugar aponta para cá (ex.: `# Decisão do Rafael: DECISOES.md, Canal Viral`). Um teste confere se a área existe.

## Trabalho com o Claude

As regras de PR, CI, merge e avisos estão no `CLAUDE.md`, em "Como trabalhamos".

- **03/10/2026:** comentários em português, explicando a intenção e a regra de negócio, sem emoji. Na dúvida sobre a intenção do código, perguntar antes de reescrever ou corrigir.
- **03/10/2026:** PR e merge sem perguntar. Antes do merge, o CI reforçado tem de estar verde; depois, conferir o deploy.
  - Avisos só ao abrir o PR, se algo falhar e no fim.
  - O Rafael pode barrar o merge, mandar fazer direto ou pedir rodadas extras.
- ~~**03/10/2026:** 5 rodadas do CI no mesmo commit, com 5 min entre elas, antes do merge.~~ Substituída em 03/10/2026 pela rodada reforçada (testes em 4 horários e ordem aleatória), porque repetir o mesmo commit não testava nada novo.
- **03/10/2026:** todo pedido que define comportamento entra neste diário.
- **03/10/2026:** vídeo que o Rafael mandar é visto e ouvido por inteiro antes de seguir a instrução: todos os quadros e a fala transcrita. Sem conseguir ouvir, dizer isso logo e pedir a transcrição antes de mudar qualquer coisa.
- **04/10/2026:** quando uma mudança serve para descobrir por que algo dá errado, o Claude agenda sozinho a conferência do resultado, no horário em que ele já deve existir. O Rafael não precisa lembrar: na hora marcada, o Claude lê o resultado, corrige ou orienta e avisa.
- **04/10/2026:** na conferência, com o resultado claro, o Claude corrige e sobe sozinho (PR, CI, merge, deploy), sem ação do Rafael. Só espera o Rafael quando houver dúvida de verdade.
- **04/10/2026:** pergunta do Claude ao Rafael que fica sem resposta (1 h) vira aviso no privado do Telegram, pelo bot principal, para ele abrir a conversa com o Claude. Só entre 8h e 22h, no máximo um por dia por pergunta.
- **04/10/2026:** pedido terminado (incluir, editar ou excluir algo nos robôs) fecha com um bloco "✅ Concluído": o que foi feito, o impacto para o Rafael e onde achar no bot. Vale mesmo com outras ações ainda em andamento.
- **04/10/2026:** uma rotina chama a conversa às 8h, 11h, 14h, 17h e 20h para retomar o que ficou pela metade quando o crédito acaba. Sem pendência, só responde "Nada pendente.". A cada 3 h, e não de hora em hora, para gastar menos crédito.
- **04/10/2026:** opções oferecidas ao Rafael ficam abertas até ele escolher, mesmo que demore. Se o seletor sumir, as mesmas opções aparecem de novo. A demora nunca vira escolha: até ele responder, fica valendo o que já estava.

## Canal principal

- **03/10/2026:** se o envio de um vídeo falha (rede, Telegram fora), tenta de novo 10 min depois, até 3 vezes. Depois disso vira ERRO, vai para o log de erros e sai da fila na faxina da madrugada.
- **03/10/2026:** "Publicar Agora" de um vídeo guardado só pelo file_id não pode sair de novo no horário agendado.

## Pausa programada

- **03/10/2026:** a pausa para também os vídeos do canal principal, e não só o SPAM e as rotinas. Os vídeos ficam pendentes e voltam a ser agendados quando a pausa acaba.
- **03/10/2026:** se a pausa acaba no meio do dia (pelo botão ou na data marcada), o canal volta no mesmo dia.
  - O robô recalcula a grade como o "Retomar Rotinas".
  - Se o Bom Dia de hoje não saiu, ele sai uns 5 min depois e abre o expediente.

## Canal Viral (Espião)

- **03/10/2026:** a intercalação (não postar dois textos seguidos enquanto há vídeo) conta só os clones com horário até hoje, não os de amanhã (D+1). É o mesmo critério do Grupo Público.
- **03/10/2026:** o link só é registrado como "já capturado" depois de confirmar que o post tem vídeo.
- **03/10/2026:** post feito como resposta dentro de um tópico é lido pelo tópico certo (`reply_to_top_id`).
- **03/10/2026, exceção:** Espião e Espelhador ignoram posts do próprio sistema, para não recapturar o que publicaram. No @shopee_video_afiliado é o contrário: capturam até os posts do sistema, de propósito. O bot posta no grupo principal, e esses posts devem ser espelhados para outros canais.
- **03/10/2026:** a trava de silêncio vale para todas as rotinas do Viral, e não para as do Grupo Público.
- **03/10/2026:** o "esvaziar/forçar" a fila de clones solta tudo a partir de agora, um a cada 15 s, a qualquer hora, ignorando a janela. Forçar é publicar já.

## Espelhador de canais

- **03/10/2026:** "Dois Dias (D+2)" espera os 2 dias: vídeo capturado na segunda sai na quarta, como nas outras filas.
- **03/10/2026:** se o envio falha por causa temporária, o vídeo volta para a fila e tenta no ciclo seguinte, até 3 vezes. Vídeo apagado ou sem vídeo na origem é descartado na hora.
- **03/10/2026:** rotas criadas pelo assistente "Criar Rota" gravam as origens no formato que o motor lê, e as rotas antigas foram convertidas. As origens da criação passaram a capturar.
- **03/10/2026:** `espelhos_config.json` e `fila_espelhador.json` são gravados em arquivo temporário e trocados de uma vez, para ninguém ler o arquivo pela metade.
- **03/10/2026:** o que já foi publicado fica na fila como histórico só por 3 dias.
  - Antes ficava para sempre: eram 1.099 itens desde 14/09, e o arquivo de 1 MB era regravado a cada minuto.
  - Os pendentes nunca são podados.

## Vídeos Autorais e contas do pool

- ~~**03/10/2026:** integração do pool de contas ao robô dos Autorais fica pendente.~~ Substituída em 03/10/2026: o Rafael pediu para integrar, separando as funções (abaixo).
- **03/10/2026:** uma conta só captura os vídeos (posto "espelho"), e outras contas só repostam no grupo de origem. Se uma conta for expulsa, não é preciso reprogramar as outras.
  - **Repostagem:** as contas aptas revezam; cada vídeo de retorno sai por uma conta diferente.
  - **Captura protegida:** a conta da captura nunca reposta, nem se todas as de repostagem caírem. Nesse caso a repostagem para e o Rafael recebe um aviso.
  - **Relatório:** ✅/❌ por conta e função no painel "Contas e Postos".
  - **Aviso no privado:** quando uma conta para de funcionar ou outra assume, só quando muda.
- **03/10/2026:** conta nova do pool é cadastrada pelo próprio bot ("➕ Nova conta"), sem terminal.
- **04/10/2026:** no fim do "➕ Nova conta", o bot pergunta "Para que serve esta conta?" e já configura tudo com um toque. A tela de cada conta usa os mesmos botões, no lugar de ligar e desligar funções.
  - 🎯 **Captura e publicação no seu canal:** uma conta só; se já houver outra na captura, ela assume e a outra vai repostar.
  - 🔁 **Repostagem no grupo de origem:** reveza com as outras e nunca assume a captura.
  - ~~🔀 **As duas:** reposta e assume a captura se a da captura cair. É o comportamento que as contas já tinham.~~ Substituída em 04/10/2026: o Rafael preferiu só dois botões (abaixo).
  - **04/10/2026:** ficam só 🎯 Captura e 🔁 Repostagem. Várias contas na repostagem já são reserva umas das outras (revezam e, se uma cair, as outras seguem). Se a conta da captura cair, o Rafael recebe o aviso e escolhe outra com um toque. Conta antiga com as duas funções continua valendo até ele escolher.
- **04/10/2026:** o robô confere se a conta da captura consegue publicar no seu canal: admin com "publicar mensagens" (ou dono). Se não consegue, a captura fica ❌ no painel, com aviso no privado, e o cadastro já avisa.
- **04/10/2026:** o botão "Contas 👥" fica dentro de "Vídeos Autorais 🎥", e não solto em "Outros Canais": as contas e as pessoas bloqueadas só servem a esse robô (captura dos Autorais e dos parceiros). Telas em palavras:
  - "Pessoas bloqueadas" (era "Autores Bloqueados") explica que bloquear alguém faz o robô não copiar para o seu canal o que essa pessoa posta no grupo de origem, e por isso também não repostar. As suas próprias contas entram ali sozinhas, para o robô não recapturar o que elas repostam.
  - O "Cancelar" do "Bloquear alguém" volta para a lista de bloqueados.
- **04/10/2026:** o menu de Contas segue o padrão dos outros painéis (como o de Parceiros), porque o Rafael achou o anterior confuso: nada de botões dentro da mensagem nem de abas.
  - **Painel:** lista numerada das contas no texto e, no teclado de baixo, Cadastrar Conta ➕, Gerenciar Conta 🔧, Remover Conta 🗑️, Pessoas Bloqueadas 🚫 e Voltar ao Menu Autorais 🔙.
  - **Escolha pelo número**, como nos Parceiros: com uma conta só, Gerenciar abre direto. Excluir pede Aprovar ✅.
  - **Na conta:** Usar na Captura 🎯, Usar na Repostagem 🔁, Colocar no Grupo 🚪 (usa o link guardado ou pede um), Pausar/Reativar, Excluir e Voltar às Contas 🔙.
  - **Pessoas Bloqueadas 🚫:** lista numerada, Bloquear Pessoa ➕ (pergunta onde vale: só nos Autorais ou Autorais e parceiros) e Desbloquear Pessoa 🗑️ pelo número.
- **04/10/2026:** toda conta aparece do mesmo jeito em todas as telas: nome e telefone do chip. O telefone fica sempre, porque é o que identifica o chip.
  - **Nome automático:** o @ da conta ou, sem @, o nome do Telegram. Ele acompanha as mudanças no Telegram.
  - **Editar Nome ✏️** (na tela da conta): o nome dado pelo Rafael tem preferência sobre o automático.
  - **Usar Nome Automático 🔄:** volta ao automático, que fica sempre guardado.
- **04/10/2026:** o "Colocar no Grupo 🚪" explica o que é antes de pedir o link: o nome do grupo de origem, que a conta precisa ser membro dele e onde achar o link de convite (no grupo → Convidar via link, só para admin).
- **04/10/2026:** a tela da conta fica enxuta, a pedido do Rafael. O nome aparece sem explicação do automático e o grupo de origem numa palavra: ✅ dentro, 🚪 saiu, ⚪ fora, ⛔ banida.
  - O robô descobre sozinho se a conta saiu ou foi banida: guarda o acesso ao grupo quando a conta está nele (para as contas antigas, lê o da sessão antiga) e, quando o grupo some, pergunta ao Telegram.
  - Para o que aconteceu antes (ou se ele errar), "Situação no Grupo 📝" deixa marcar à mão: Foi Banida, Saiu do Grupo ou Deixar Automático. A marcação some quando a conta volta ao grupo.
- **04/10/2026:** nas telas de Contas, "seu canal" passa a ser "canal de destino" (o canal onde a conta da captura publica).
- **03/10/2026:** com cota em faixa (ex.: 6–10), o teto de saída do dia é o mesmo número sorteado na captura para aquela data.
- **03/10/2026:** cada mensagem da origem é processada uma vez só, venha pelo evento ou pela varredura (trava pelo ID, gravada no banco).
- **03/10/2026:** o log de diagnóstico "🔬 [Evento]", que registrava toda mensagem de todo chat, foi removido.

## Grupo Público e Achadinhos

- **03/10/2026:** "Zerar Filas e Tarefas" apaga de `temp/` só o que não está em fila nenhuma, para não quebrar as filas que não foram limpas.

## Buscador de produtos

- **03/10/2026:** o `/painelbusca` publica o mesmo painel automático: um painel só, rastreado, e o antigo é apagado ao recriar. O texto diz "a faixa de preço das opções que separei".

## Parceiros

- **03/10/2026:** excluir um parceiro apaga também a pasta `parceiros/<id>/`, para os vídeos dele não ocuparem o teto de 10 GB dos outros.
- **03/10/2026:** nos Relatórios de Filas fica um botão só, "Fila dos Parceiros 🔍". Ele mostra no topo o resumo do parceiro (disco, cota, acesso à origem, descarte do fechamento e próxima publicação) e, embaixo, a lista vídeo a vídeo. Com um parceiro só, abre direto, sem perguntar o número.
- **04/10/2026:** na fila do parceiro, os vídeos aparecem no mesmo card das outras filas (status do dia, nome, captura ➡️ previsão, links de origem e destino), todos, em quantas mensagens forem precisas. O resumo do parceiro continua numa mensagem antes da lista.
- **04/10/2026:** o acesso à origem de um parceiro só vale quando a conta da captura é membro do canal, e não só quando o encontra. Causa provável da captura parada desde 15/09: a conta achava o canal, mas não estava dentro, e o Telegram só entrega as mensagens a quem é membro. O robô reconfere a cada 6 h e entra de novo sozinho quando a origem é @ ou link. Parceiro sem acesso gera aviso no privado (monitor de saúde), e a fila mostra o motivo e a data da última captura.
- **04/10/2026:** a fila do parceiro mostra o que chegou hoje do canal de origem: mensagens, vídeos, com link, capturados e o motivo de cada recusa. Com a captura parada desde 15/09, o acesso confirmado e a conta da Rafaela fora do caso (ela não posta no canal), o robô passou a contar onde o vídeo para.
- **04/10/2026:** os links da fila do parceiro seguem o padrão da fila do Grupo Público.
  - **Origem:** "Ver Post no Telegram", o post de onde o vídeo foi capturado. O link da Shopee não aparece; ele fica guardado só para gerar o link de afiliado do parceiro.
  - **Destino:** depois de publicado, vira "Ver Post no Telegram (Destino)", com o link do post.
  - Os publicados de hoje aparecem no topo, como no Público. O vídeo sai do disco na hora, mas o registro fica 3 dias.
  - Os vídeos capturados antes desta mudança não têm o post de origem guardado e aparecem "Sem link de origem".
- **04/10/2026:** quando nenhuma conta está na captura dos Autorais, a fila e o painel de Parceiros dizem "❌ nenhuma conta está capturando", e não "✅" com o acesso velho. É a mesma conta que captura dos parceiros.

## Financeiro

- **03/10/2026:** na confirmação de um pedido, o saldo soma só a comissão final. O ajuste de valor só entra para pedido que já estava confirmado. Os erros antigos que já estavam no saldo gravado não foram recalculados.

## Notas fiscais

- **03/10/2026:** abortar na tela de aprovação descarta o lote; rascunhos antigos não saem com o próximo.
- **03/10/2026:** se o PDF sumiu do disco, a nota não é enviada: vira ERRO "PDF não encontrado" e aparece no resumo.
- **03/10/2026:** a retomada depois do limite de 290 por dia fica gravada no banco e acontece mesmo depois de um deploy.
- **03/10/2026:** os nomes dos PDFs mudam todo mês, então o filtro anti-duplicidade continua olhando todos os envios anteriores.
- **03/10/2026:** um envio por vez. Lote aprovado durante um envio espera; durante a pausa de 26 h, fica pendente e sai na retomada, sem furar o limite.

## Divulgação (SPAM em grupos)

- **03/10/2026:** se o robô reinicia no meio da hora, completa só os envios que faltam naquela hora, sempre respeitando os 15 min entre envios.
- **03/10/2026:** o "Adicionar Alvo" do SPAM do canal principal valida o alvo como os outros painéis (link t.me, Telegram Web ou @ viram ID).
- **03/10/2026:** quando a conta perde o acesso a um alvo (foi removida, banida ou o grupo ficou privado), o robô pausa o alvo e avisa: para de enviar para ele em todos os escopos, marca "sem acesso" nos painéis de SPAM e manda um aviso só no privado, com o botão 🔓 para reativar (que também aparece nos painéis). Isso não vai mais para o registro de erros. Alvo excluído de todos os painéis perde a marca: se voltar, volta ativo.

## Baixador

- ~~**03/10/2026, exceção:** o painel do tópico desce para ser sempre a última mensagem, mas não é fixado. Cada fixação deixava uma mensagem "fixou uma mensagem" acumulando no tópico.~~ Substituída em 03/10/2026: o mais novo fica fixado, e os antigos somem (abaixo).
- **03/10/2026:** a função que expirava o cache de file_id foi removida. A falha de um file_id já é tratada: o vídeo é baixado de novo.
- **03/10/2026:** no tópico ficam os vídeos entregues aos usuários, para sempre, e um painel só, o mais recente.
  - O painel desce para o fim do tópico depois das entregas, e o mais novo fica fixado.
  - Os painéis antigos e as mensagens "fixou uma mensagem" são apagados sozinhos pela conta principal (userbot, no `divulgacao_canal`), a cada 10 min. O Telegram só deixa bot apagar mensagem com menos de 48 h, por isso o bot não dava conta.
  - A faxina de 3 dias do bot, que tentava apagar tudo (inclusive os vídeos) e nunca conseguia, saiu.
- **04/10/2026:** quem já usou os downloads de cortesia e não está nos canais obrigatórios recebe o aviso para entrar, que some em 3 min. Se a pessoa não entrar, o link dela some junto, como no aviso de limite diário: no tópico não fica link que parece ignorado.

## Shopee Vídeo

- **04/10/2026:** robô novo que posta sozinho na Shopee Vídeo pelo app, num Android virtual no servidor. A Shopee não tem forma oficial de postar por programa: a Shopee Vídeo só aceita postagem pelo app. O Rafael escolheu sabendo dos riscos: vai contra os termos da Shopee, ela pode perceber o emulador, e uma atualização do app pode quebrar a automação.
- **04/10/2026:** posta na conta principal de afiliado do Rafael, ciente de que um bloqueio atinge essa conta.
- **04/10/2026:** os vídeos vêm dos Autorais (feitos para afiliados repostarem), com o produto vinculado no próprio vídeo: a comissão só conta assim, e link na descrição não vale.
- ~~**04/10/2026:** 10 vídeos por dia.~~ Substituída em 04/10/2026 pela faixa sorteada e pela janela de horário (abaixo).
- **04/10/2026:** a quantidade por dia é uma faixa escolhida pelo Rafael (ex.: de 5 a 10). Cada dia sorteia um número dentro dela, e os vídeos se espalham por uma janela de horário que ele também escolhe (ex.: das 13h às 22h), como nas outras filas (`motor_filas`). No painel, ele pausa e retoma as postagens quando quiser e muda a faixa e a janela.
- **04/10/2026:** o Rafael perguntou como reduzir o risco de punição. Disfarçar o Android virtual para a Shopee (localização falsa, imitar aparelho real, esconder o emulador) não se faz: é driblar o antifraude dela. Ele escolheu seguir no automático, ciente do risco.
- **04/10/2026:** o Android virtual é um Redroid (Android 13, 64 bits) em Docker no próprio servidor, limitado a 4 GB de memória e 2 CPUs para não atrapalhar os robôs. O adb fica aberto só para a própria máquina, nunca para a internet. Os dados do Android (app e login) ficam fora do contêiner, em `~/android_shopee`.
- ~~**04/10/2026:** o app da Shopee vem do Google Play, pela Aurora Store (código aberto, instalada do F-Droid), assinado pela própria Shopee. Os sites de APK recusam o servidor. O Rafael instala a Shopee pela loja na tela do Android, junto com o login.~~ Substituída em 04/10/2026: no servidor, a Aurora só funciona com uma conta Google (o modo anônimo é bloqueado), e o Rafael preferiu não usar conta Google (abaixo).
- **04/10/2026:** o Rafael baixa o app da Shopee no celular dele (os sites de APK recusam o servidor, não o celular) e envia pelo botão "Enviar app 📦" da tela do Android; o servidor instala e apaga o arquivo.
- **04/10/2026:** o login da Shopee (e o que mais precisar de mão humana, como código ou quebra-cabeça de segurança) é feito pelo Rafael na tela do Android aberta no navegador do celular. O link leva uma chave aleatória e vai só no privado dele, por um túnel temporário do Cloudflare (sem abrir porta no servidor), e fecha em 30 min ou no botão Terminei.
- **04/10/2026:** a tela do Android tem os botões "🧹 Fechar apps" (fecha todos os apps instalados e volta à tela inicial) e "🔄 Reiniciar Android". Reiniciar é só religar, como num celular: os apps e o login da Shopee continuam.
- **04/10/2026:** também o botão "🗑️ Resetar de fábrica": desliga o Android, apaga os apps e o login e liga do zero. Os três botões pedem confirmação antes; o de fábrica pede duas vezes, porque não dá para desfazer.

## Monitor, deploy e servidor

- **03/10/2026:** o alerta "Nenhuma publicação hoje" do Espião conta só os clones com horário até hoje.
- **03/10/2026:** o deploy reinicia também o `downloader_bot`, como os outros quatro.
- **03/10/2026:** o deploy confere os robôs aos 25 s e de novo 3 min depois.
- **03/10/2026:** o deploy reinicia só os robôs cujo código mudou (o arquivo do robô ou um módulo que ele importa). Mudança só em documentação, testes ou workflows não reinicia ninguém; `requirements.txt` ou dúvida reinicia todos. Robô parado reinicia sempre.
- **03/10/2026:** um diagnóstico de hora em hora olha o servidor só lendo, e fica vermelho (e-mail do GitHub) com robô fora do ar ou disco acima de 90%.
  - Nos logs do Actions saem só estados e números, porque o repositório é público.
  - Nada de acesso SSH direto pela sessão do Claude.
- **03/10/2026:** backup automático todo dia às 03:40 do banco, das sessões, dos JSON e do `.env` em `~/backups`, ficando os 7 mais novos. Se falhar, aviso no privado. O monitor de saúde avisa se o último passar de 30 h, e o `/status` mostra a idade dele.

## Código e manutenção

- **03/10/2026:** o `database.py` foi apagado; cada robô cria as próprias tabelas ao iniciar.
- **03/10/2026:** scripts de investigação apagados (`teste_config`, `checar_topicos`, `diag_shopee`, `probe_shopee`, `simular_reajuste`). O `testar_chaves.py` fica, porque diagnostica a chave de um parceiro.
- **03/10/2026:** sem valor máximo, o teto diário de uma fila é o próprio mínimo.
- **03/10/2026:** removidas as sobras sem efeito e os handlers que nenhum botão alcançava no `bot_mestre`. O "Cancelar" das rotinas passou a usar as listas de rotinas do Viral e do Público.
- **03/10/2026, exceção:** o handler "Disparar Repost Autoral ♻️" fica, mesmo sem botão em nenhum teclado: o Rafael não pediu para tirar (pode ser usado digitando o texto). Não remover como código morto.
- **03/10/2026:** todo acesso ao banco passa pelo `db.py`, em modo WAL.
- **03/10/2026:** log direto (`logger.info/warning/error`), com o nível pelo `NIVEL_LOG` do `.env`.
- **03/10/2026:** log enxuto: as bibliotecas (agendador, aiogram, Telethon, HTTP) só mostram avisos e erros, e com `NIVEL_LOG=DEBUG` voltam a mostrar tudo. Mensagem que se repetia a cada volta (pausa do motor dos Autorais, nomes de tópicos, passo a passo do Auditor, leitura das rotinas) só sai quando algo muda ou fica no DEBUG.
- **03/10/2026:** a IA pula o modelo que respondeu sem cota (até a cota voltar: o prazo que o Google informa, ou a virada do dia no horário do Pacífico) e o modelo que não existe (por 6 h). Se todos estiverem de fora, tenta todos, como antes.
- **03/10/2026:** bibliotecas com versão fixa, a mesma do servidor (Telethon, pandas, matplotlib e google-genai estavam soltas). Saíram 13 que nenhum código usa (o SDK antigo do Gemini e as dependências dele), do requirements e do servidor.
- **03/10/2026:** o que a auditoria achou sem uso sai do servidor, sempre com cópia em `~/backups/antigos`: as tabelas mortas (fila_espelhador, fila_espiao, financeiro_despesas, financeiro_saques, historico_financeiro, pedidos_financeiro, mensagens_topico), a chave velha `fila_espelhador` e os arquivos velhos (cópias antigas do banco, backup_dados.tar.gz, conferir.png, registro_hashes.json, variantes/). Arquivos são movidos, não apagados.

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
- **06/10/2026:** o Claude não presume como um robô deve se comportar. Toda escolha que mudaria o que um robô faz, mesmo pequena, vira pergunta ao Rafael no fim do trabalho, e a mudança espera a resposta. A pergunta sem resposta entra na lista do lembrete diário e é lembrada todo dia até ele responder.

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
- **06/10/2026:** o link de afiliado abre o mesmo tipo de página que o link do post de origem, em todo robô que troca link (Espião, Autorais, Espelhador, Grupo Público):
  - origem que abre um vídeo da Shopee Vídeo: o link novo abre o vídeo, com o produto;
  - origem que abre um produto: o link novo abre o produto, e nunca uma busca ou categoria. Vídeo do Rafael de 05/10: a Mochila abria o produto na origem e a busca "Mochilas" no Acervo Viral.
  - quem guarda o link numa fila gera de novo na hora de postar, para o conserto valer também para o que já estava na fila. O Espelhador guardava o link da captura, e vídeos capturados antes do conserto saíam abrindo a busca (pedido do Rafael em 06/10: corrigir em todos os robôs que trocam link, não só no Espião). O Espião e os parceiros já geravam o link na hora; os Autorais postam logo depois da captura.
- **06/10/2026:** link que sai sem a marcação de afiliado (a API da Shopee falhou na hora) continua postando com o link original, mas o Rafael fica sabendo:
  - cada um entra no registro de erros, com o robô, o subId e o motivo, sem o link;
  - o `/status` mostra quantos houve nas últimas 24 h;
  - o monitor de saúde avisa no privado quando houve algum na última hora (no máximo um aviso a cada 6 h);
  - antes de desistir, o robô tenta converter 3 vezes (esperas de 2 s e 5 s);
  - o Claude confere nas retomadas de sempre (8h, 11h, 14h, 17h e 20h), pelo diagnóstico de hora em hora: investiga o motivo e conserta sozinho quando dá; o que depender do Rafael, ele diz o quê. O Rafael escolheu essas conferências, sem gasto extra, em vez de uma de hora em hora.

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
- **06/10/2026:** na legenda dos Autorais, o emoji vai no fim do nome do produto, igual aos outros robôs (ex.: "Tênis Casual Feminino 👟"). Antes ia no começo.

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

- ~~**04/10/2026:** robô novo que posta sozinho na Shopee Vídeo pelo app, num Android virtual no servidor. A Shopee não tem forma oficial de postar por programa: a Shopee Vídeo só aceita postagem pelo app. O Rafael escolheu sabendo dos riscos: vai contra os termos da Shopee, ela pode perceber o emulador, e uma atualização do app pode quebrar a automação.~~ Substituída em 05/10/2026 pelo modo assistente (abaixo).
- ~~**04/10/2026:** posta na conta principal de afiliado do Rafael, ciente de que um bloqueio atinge essa conta.~~ Substituída em 05/10/2026: a conta principal não fica mais num robô (modo assistente, abaixo).
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
- **04/10/2026:** "Fechar apps" funciona como o "Limpar tudo" do celular: além de fechar os apps, tira todos da lista de recentes (a do botão quadrado). O Rafael mostrou em vídeo que os apps continuavam nessa lista e pareciam abertos.
- ~~**04/10/2026:** o Rafael abre a tela do Android sozinho pelo bot, no botão "Tela do Android 📱" das Opções do Servidor.~~ Substituída em 05/10/2026: o botão fica só no painel da Shopee Vídeo (abaixo). O link chega no mesmo privado, e uma tela nova substitui a anterior. Se o painel reiniciar (deploy do bot_mestre), a tela aberta por ele fecha junto e basta tocar de novo.
- ~~**04/10/2026:** ao lado dele, o botão "Tutorial do Android 📖" manda o passo a passo completo, para quando ele precisar daqui a muito tempo: instalar a Shopee no celular, fazer o backup `.apks` pelo SAI (Play Store, `com.mtv.sai`; pasta nova "Backups"; o backup pode pedir o PRO, e depois é bom cancelar a assinatura), enviar pela tela, entrar na conta e os problemas comuns.~~ Substituída em 04/10/2026: o tutorial fica no painel do robô (abaixo).
- ~~**04/10/2026:** o robô da Shopee Vídeo tem painel próprio em Outros Canais → "Shopee Vídeo 🎬", onde o Rafael controla tudo dele: pausar e retomar, "Vídeos por Dia 📦" (faixa, ex.: 5-10, ou número fixo; até 50), "Horário de Postagem ⏰" (ex.: 13-22, ou o dia todo), "Tela do Android 📱" e o "Tutorial do Android 📖" com o passo a passo completo da instalação pelo SAI (Play Store, `com.mtv.sai`; pasta nova "Backups"; o backup pode pedir o PRO, e depois é bom cancelar a assinatura), o envio pela tela, o login e os problemas comuns. ~~A Tela do Android continua também nas Opções do Servidor.~~ O robô começa pausado, com 5 a 10 vídeos por dia das 13h às 22h, e só posta quando ele retomar.~~ Substituída em 05/10/2026: no modo assistente, o painel não tem mais a Tela nem o Tutorial do Android (abaixo).
- ~~**05/10/2026:** a "Tela do Android 📱" fica só no painel da Shopee Vídeo e saiu das Opções do Servidor: para o Rafael, o servidor dos robôs (Linux) e o Android são coisas diferentes.~~ Substituída em 05/10/2026: o Android saiu de uso (modo assistente).
- **05/10/2026:** o SAI PRO foi comprado vitalício (04/10/2026): não há assinatura a cancelar, e o tutorial diz isso para quando ele precisar de novo.
- **05/10/2026:** o caminho da postagem, do tutorial em vídeo do Rafael:
  - abrir o link do post na Shopee e, em "Ver Produtos", curtir só os produtos que o criador vinculou ao vídeo, nunca os de "Você Também Pode Gostar". Link de um produto só: só ele;
  - Eu → Criadores e Afiliados → Perfil em Shopee Vídeo → Postar vídeo → o vídeo na galeria → Próximo;
  - efeito de giro é opcional: o robô começa sem;
  - Adicionar Produto → Minhas Curtidas: primeiro o de menor preço; no empate, o de maior comissão;
  - o título vai no campo da legenda, e as chaves da última tela ficam como vêm (reutilização ligada; salvar no aparelho e rótulo de IA desligados).
- **05/10/2026:** o Rafael confirmou que os vídeos vêm dos Autorais (o tutorial usou um vídeo do Acervo Viral).
- **05/10/2026:** o texto vem do prompt do Gem "Shopee Vídeo" do Rafael, adaptado ao robô. Do que o Gem gera, o robô usa só o "título do vídeo": nome do produto sem frase de gancho, emojis e hashtags, de 130 a 150 caracteres, sem marca. A headline fica de fora, como o Rafael já faz.
- **05/10/2026:** as diretrizes da Shopee Vídeo (PDF do Rafael) ficam resumidas em `diretrizes_shopee_video.md` e valem sempre ("isso é importante"). A IA recebe o resumo com cada vídeo e, se achar violação (o ❌ do Gem), o robô não posta aquele vídeo.
- **05/10/2026:** curtir o vídeo, comentar e curtir o próprio comentário (o fim do tutorial) não é automático: a diretriz 9.1.1 proíbe curtidas e comentários automáticos. Depois de cada postagem, o texto do comentário do Gem (400 a 450 caracteres, com 5 a 10 hashtags no fim) vai no privado do Rafael, que comenta à mão se quiser.
- ~~**05/10/2026:** o primeiro teste termina em Rascunhos, não em Postar: o Rafael confere na Tela do Android e posta. Depois que ele aprovar, o robô passa a postar sozinho.~~ Substituída em 05/10/2026: no modo assistente quem posta é o Rafael.
- **05/10/2026:** para aprender as telas do app, a exploração (`postador_shopee_video.py --explorar`, ação "explorar" do android.yml) nunca toca em Postar, e o log mostra só a forma da tela, porque a tela mostra a conta do Rafael.
- ~~**05/10/2026:** robô da Shopee Vídeo **em pausa**. Depois das primeiras explorações (o app fechado e reaberto várias vezes em meia hora), a Shopee passou a abrir sozinha uma página de "Verificação" de segurança, que dava erro ao carregar. O Rafael pausou para não arriscar a conta principal:~~ Substituída em 05/10/2026 pelo modo assistente (abaixo).
  - ~~o Android virtual fica desligado durante a pausa (ação "desligar" do android.yml), para a conta não ficar conectada pelo servidor de nuvem; o app e o login continuam lá;~~
  - ~~lembrete diário no privado dele até retomarmos;~~
  - ~~na volta: religar o Android, o Rafael resolve a verificação pela Tela do Android 📱 e eu testo devagar (uma rodada, poucos toques, sem fechar e reabrir o app). Se a verificação voltar mesmo assim, decidimos juntos; disfarçar o Android continua fora.~~
- **05/10/2026:** **modo assistente** no lugar do robô que posta sozinho. O Rafael teve receio de perder a conta principal: a Shopee vê que é servidor de nuvem e Android virtual, e já tinha pedido verificação. O robô prepara tudo e manda no privado dele: o vídeo dos Autorais, o título pelo prompt do Gem (conferido com as diretrizes), os produtos na ordem (menor preço primeiro; no empate, maior comissão) e o texto do comentário. Ele posta pelo próprio celular. Quantidade por dia, janela de horário e pausa continuam no painel.
- **05/10/2026:** o Android virtual foi apagado (apps e login da Shopee, ação "apagar" do android.yml) e fica desligado. O Rafael troca a senha da Shopee pelo celular, para desconectar aquele aparelho de vez.
- **05/10/2026:** para depois do modo assistente: o Rafael quer testar a postagem automática num celular de verdade dele, que está parado em casa e ficaria ligado o tempo todo (internet de casa e aparelho real, em vez de servidor de nuvem e Android virtual). Como ligar esse celular ao robô com segurança fica para quando ele quiser testar.
- **05/10/2026:** o painel do modo assistente (Outros Canais → Shopee Vídeo 🎬): pausar e retomar, "Vídeos por Dia 📦" (faixa), "Horário de Postagem ⏰" (janela) e "Enviar 1 Agora 📤" (manda uma postagem na hora, mesmo pausado, para testar ou postar mais uma). Começa pausado. Os botões Tela do Android e Tutorial do Android saíram.
- **05/10/2026:** como o assistente manda, a cada dia:
  - a quantidade é sorteada dentro da faixa, e os horários também: a janela é dividida em partes iguais e cada envio cai num minuto sorteado da sua parte. Nunca no mesmo horário todo dia nem na mesma quantidade (pedido do Rafael: "faixas de horário, e não um horário específico");
  - no máximo um envio por vez; horários que passaram com o robô fora do ar contam como um só, e os que passam pausado são pulados (retomar não solta tudo de uma vez);
  - ~~o vídeo é o Autoral mais novo que ainda tem o arquivo e não foi mandado;~~ Substituída em 05/10/2026: o vídeo é o mais novo da fonte escolhida no painel (abaixo) que ainda tem o arquivo e não foi mandado;
  - a mensagem traz o vídeo, o título (toque para copiar), o produto (link de produto: nome, preço e comissão pela API; link de vídeo: o Rafael vê os produtos do criador no link) e o comentário (toque para copiar);
  - vídeo que a IA marca como violação das diretrizes não é mandado, e o Rafael recebe o motivo; se a IA não responder, o vídeo é pulado.
- **05/10/2026:** para o teste futuro no celular de verdade do Rafael: devagar e com pouco volume no começo (toques rápidos e perfeitos e horário de máquina denunciam robô), e com as mesmas regras do painel: faixa de horário e quantidade variada por dia.
- **05/10/2026:** o projeto do robô no servidor fica **guardado**, parado, com o roteiro em `roteiro_robo_shopee_video.md` (onde paramos e o que fazer na volta). O Rafael pode conseguir um perfil reserva para testar: a volta é com ele, nunca com a conta principal, devagar, sem toques rápidos e sem ficar saindo e entrando no app.
- **05/10/2026:** o Rafael pediu para o roteiro usar qualquer artifício contra a detecção de robô (localização de acordo com o usuário, dados de sensores). Não se faz, como em 04/10: é driblar o antifraude da Shopee, e a diretriz 9.2 proíbe. A alternativa honesta é o celular de verdade dele.
- **05/10/2026:** botão "Fonte dos Vídeos 🎞️" no painel: o Rafael escolhe de onde o assistente puxa os vídeos, entre Autorais 🎥 (continua o padrão e o recomendado), Viral (Espião) 🕵️, Canal Afiliados 📺 e Grupo Público 📬. Vale para os envios do horário e para o Enviar 1 Agora. Os Parceiros ficam de fora, porque os vídeos são deles. A tela da escolha avisa que a Shopee não recomenda conteúdo copiado (diretriz 7.2.1), o que pesa no Viral e no Grupo Público.
- **05/10/2026:** plano do celular de verdade (no `roteiro_robo_shopee_video.md`): o robô continua no servidor e toca num celular guardado do Rafael, ligado por uma rede privada (Tailscale, sem porta aberta), com o perfil reserva. O modo assistente continua. A preparação começa já; a parte que precisa do celular fica em espera até o Rafael ter acesso a ele.
- **05/10/2026:** um lembrete diário único (8h47, no privado) com tudo o que o Rafael tem pendente, no lugar dos lembretes separados: "pode acontecer de eu esquecer". Cada item sai da lista quando ele resolve.

## Monitor, deploy e servidor

- **03/10/2026:** o alerta "Nenhuma publicação hoje" do Espião conta só os clones com horário até hoje.
- **03/10/2026:** o deploy reinicia também o `downloader_bot`, como os outros quatro.
- **03/10/2026:** o deploy confere os robôs aos 25 s e de novo 3 min depois.
- **03/10/2026:** o deploy reinicia só os robôs cujo código mudou (o arquivo do robô ou um módulo que ele importa). Mudança só em documentação, testes ou workflows não reinicia ninguém; `requirements.txt` ou dúvida reinicia todos. Robô parado reinicia sempre.
- **03/10/2026:** um diagnóstico de hora em hora olha o servidor só lendo, e fica vermelho (e-mail do GitHub) com robô fora do ar ou disco acima de 90%.
  - Nos logs do Actions saem só estados e números, porque o repositório é público.
  - Nada de acesso SSH direto pela sessão do Claude.
- **03/10/2026:** backup automático todo dia às 03:40 do banco, das sessões, dos JSON e do `.env` em `~/backups`, ficando os 7 mais novos. Se falhar, aviso no privado. O monitor de saúde avisa se o último passar de 30 h, e o `/status` mostra a idade dele.
- **05/10/2026:** nas Opções do Servidor há o botão "Acessos do Servidor 🔐", no mesmo formato das Informações de Acesso das notas (link, login para copiar e senha escondida), para o Rafael lembrar onde entrar:
  - Tailscale (rede privada do celular): login.tailscale.com, entrando pelo Google. Guarda só qual conta Google; a senha é a do Google e não fica no bot.
  - Oracle Cloud (servidor dos robôs): cloud.oracle.com, com nome da conta na nuvem, e-mail e senha.
  - O Rafael cadastra e troca os dados pelo próprio bot (Editar Tailscale ✏️ e Editar Oracle ✏️). Ficam no banco do servidor, nunca no código (o repositório é público) nem no log; a mensagem com a senha é apagada da conversa logo depois de guardada.

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
- **06/10/2026:** padronização do código, no plano que o Rafael escolheu: o que se repete entre os robôs vai para um módulo só, um PR por vez, sem mudar o que os robôs fazem.
  - Ordem: 1) links da Shopee (`links_shopee.py`); 2) legendas e o pedido de nome e hashtags à IA; 3) vídeos (720p e hash); 4) fila do Espelhador no banco, porque dois robôs gravam o mesmo arquivo; 5) trava única de admin, teclados, logs repetidos e o teste lento.
  - O `bot_mestre.py` é dividido aos poucos: um painel sai para o próprio arquivo quando precisar de outra mudança, nunca tudo de uma vez.
  - Motivo: o conserto do link de produto valeu para o Espião e não para o Espelhador, que tinha a própria cópia. Um teste barra cópia nova da receita de link.
  - Etapa 2 (`legendas.py`): uma legenda e um pedido de nome e hashtags à IA para Espião, Espelhador, Autorais e Parceiros. O nome que vem da IA passa a ser escapado no HTML: um "<" no nome não derruba mais o post.
  - Respostas do Rafael (06/10/2026): o pedido à IA é a versão completa em todos os robôs (assistir o vídeo inteiro, o exemplo do organizador de sacos e a proibição de texto de venda), inclusive Parceiros e Espião no disparo, que usavam uma versão curta. Ficam também o escape do nome no HTML e, no repost do Grupo Público, o `https://` e a pontuação tirada do fim do link, como nos outros robôs.
  - Etapa 3 (`videos.py`): a medição da resolução e o 720p num lugar só para Espião, Espelhador, Autorais e Baixador, sem mudar o que fazem. O hash do vídeo (anti-duplicata) ficou no `motor_userbot`: só ele usa, não havia cópia para juntar.
  - Etapa 4 (`fila_espelhador.py`): a fila do Espelhador sai do arquivo e vai para o banco. Cada gravação mexe só no que mudou: o vídeo capturado enquanto o robô posta e a mudança feita pelo painel nesse meio tempo não somem mais. O `motor_userbot` passa o arquivo para o banco ao ligar, depois do deploy, quando a versão velha dele já parou. As rotas continuam no `espelhos_config.json`.

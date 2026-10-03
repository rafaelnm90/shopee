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
- **03/10/2026:** com cota em faixa (ex.: 6–10), o teto de saída do dia é o mesmo número sorteado na captura para aquela data.
- **03/10/2026:** cada mensagem da origem é processada uma vez só, venha pelo evento ou pela varredura (trava pelo ID, gravada no banco).
- **03/10/2026:** o log de diagnóstico "🔬 [Evento]", que registrava toda mensagem de todo chat, foi removido.

## Grupo Público e Achadinhos

- **03/10/2026:** "Zerar Filas e Tarefas" apaga de `temp/` só o que não está em fila nenhuma, para não quebrar as filas que não foram limpas.

## Buscador de produtos

- **03/10/2026:** o `/painelbusca` publica o mesmo painel automático: um painel só, rastreado, e o antigo é apagado ao recriar. O texto diz "a faixa de preço das opções que separei".

## Parceiros

- **03/10/2026:** excluir um parceiro apaga também a pasta `parceiros/<id>/`, para os vídeos dele não ocuparem o teto de 10 GB dos outros.

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

## Baixador

- ~~**03/10/2026, exceção:** o painel do tópico desce para ser sempre a última mensagem, mas não é fixado. Cada fixação deixava uma mensagem "fixou uma mensagem" acumulando no tópico.~~ Substituída em 03/10/2026: o mais novo fica fixado, e os antigos somem (abaixo).
- **03/10/2026:** a função que expirava o cache de file_id foi removida. A falha de um file_id já é tratada: o vídeo é baixado de novo.
- **03/10/2026:** no tópico ficam os vídeos entregues aos usuários, para sempre, e um painel só, o mais recente.
  - O painel desce para o fim do tópico depois das entregas, e o mais novo fica fixado.
  - Os painéis antigos e as mensagens "fixou uma mensagem" são apagados sozinhos pela conta principal (userbot, no `divulgacao_canal`), a cada 10 min. O Telegram só deixa bot apagar mensagem com menos de 48 h, por isso o bot não dava conta.
  - A faxina de 3 dias do bot, que tentava apagar tudo (inclusive os vídeos) e nunca conseguia, saiu.

## Monitor, deploy e servidor

- **03/10/2026:** o alerta "Nenhuma publicação hoje" do Espião conta só os clones com horário até hoje.
- **03/10/2026:** o deploy reinicia também o `downloader_bot`, como os outros quatro.
- **03/10/2026:** o deploy confere os robôs aos 25 s e de novo 3 min depois.
- **03/10/2026:** um diagnóstico de hora em hora olha o servidor só lendo, e fica vermelho (e-mail do GitHub) com robô fora do ar ou disco acima de 90%.
  - Nos logs do Actions saem só estados e números, porque o repositório é público.
  - Nada de acesso SSH direto pela sessão do Claude.

## Código e manutenção

- **03/10/2026:** o `database.py` foi apagado; cada robô cria as próprias tabelas ao iniciar.
- **03/10/2026:** scripts de investigação apagados (`teste_config`, `checar_topicos`, `diag_shopee`, `probe_shopee`, `simular_reajuste`). O `testar_chaves.py` fica, porque diagnostica a chave de um parceiro.
- **03/10/2026:** sem valor máximo, o teto diário de uma fila é o próprio mínimo.
- **03/10/2026:** removidas as sobras sem efeito e os handlers que nenhum botão alcançava no `bot_mestre`. O "Cancelar" das rotinas passou a usar as listas de rotinas do Viral e do Público.
- **03/10/2026, exceção:** o handler "Disparar Repost Autoral ♻️" fica, mesmo sem botão em nenhum teclado: o Rafael não pediu para tirar (pode ser usado digitando o texto). Não remover como código morto.
- **03/10/2026:** todo acesso ao banco passa pelo `db.py`, em modo WAL.
- **03/10/2026:** log direto (`logger.info/warning/error`), com o nível pelo `NIVEL_LOG` do `.env`.

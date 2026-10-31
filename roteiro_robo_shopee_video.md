# Robô da Shopee Vídeo no celular guardado (roteiro)

Desde 22/10/2026 há dois robôs, cada um com o seu botão de pausar: o **modo
assistente** (`assistente_shopee_video.py`: prepara a postagem e o Rafael posta pelo
celular) e o **robô automático** (`robo_shopee_video.py`: prepara rascunhos sozinho no
celular guardado e posta os que o Rafael aprova no bot). Este roteiro diz o que já se
sabe do app, o que falta mapear e como o robô trabalha. As decisões ficam no
`DECISOES.md`, área Shopee Vídeo.

## Robô automático (22/10/2026)

- **Rodada:** o bot_mestre chama `robo_shopee_video.py --rodada` a cada 15 min, num
  processo à parte. Cada rodada faz no máximo uma coisa: treino (1ª rodada de segunda),
  apagar um recusado, postar um aprovado cuja hora chegou ou preparar um rascunho (plano
  do dia: Rascunhos por Dia 📦 sorteado e espalhado pelo Horário do Robô 🕗). Pausado,
  fora do horário, com o celular desconectado ou com a tela dele aberta, não toca em nada.
  O explorar e o robô pegam a mesma trava (`celular_robo.trava()`): nunca os dois juntos.
- **Celular desconectado:** antes de cada rodada, `celular_robo.reconectar_sozinho()` tenta
  a porta guardada e, se não der, procura a porta nova da Depuração por Wi-Fi (portas
  32768 a 60999 do IP do celular na rede privada) e conecta. Sem conseguir (depuração
  desligada, celular fora do Tailscale), a Postagem pausa sozinha e o assistente assume;
  Retomar Postagem ▶️ procura de novo antes de retomar.
- **Conta suspensa pela Shopee (mapeado no Motorola em 23/10/2026):** com a conta de
  Shopee Vídeo suspensa, tocar em **Postar vídeo** não abre nada (a tela fica no Perfil).
  O aviso fica em **Notificações** (aba de baixo, `title` "Notificações") → filtro
  **"Lives, Vídeos e ..."** (na fileira de filtros, ~540,947): um texto "Sua conta foi
  banida temporariamente até DD-MM-AAAA HH:MM:SS ... Você não poderá publicar ... em
  Shopee Vídeo durante o período de suspensão". O robô (`ler_suspensao`) só toca na aba
  e no filtro e rola a lista 2 vezes; não abre a notificação. Ele olha quando a
  Biblioteca não aparece depois do Postar vídeo (`abrir_galeria`) e antes de postar um
  aprovado. Até o fim (chave `robo_suspenso_ate` de `shopee_video`, mais 15 min), nada
  toca no celular, e o assistente espera junto.
- **Saúde do Vídeo (mapeada no Motorola em 24/10/2026, com o vídeo do Rafael):** Perfil em
  Shopee Vídeo → **Centro do criador** (`ReactActivity_`, a tela "Live e Vídeo", aba Vídeo) →
  o quadro **Saúde do Vídeo** (o nome não aceita toque; o robô toca no "Melhoria Necessária"
  da mesma linha, ~805,1357). Abre uma página web (`WebPageActivity_`): "Banido
  Temporariamente" com "Seu acesso para postar vídeos foi banido até DD/MM/AAAA HH:MM:SS",
  "Ponto de Penalidade" e o número (escala de 0 a 15), Diretrizes da Comunidade (Aprender) e
  **Vídeos de Violação** (últimos 30 dias): cada punição em três textos, o tipo ("Produto
  Irrelevante", "Contrafeito", "Violação de Propriedade Intelectual"), "Data de Punição:
  DD/MM/AAAA HH:MM:SS" e "Status da Apelação: Não Recorrido" (ou "Bem-sucedido"...). Tocar no
  tipo abre a tela **Removido** (`ReactActivity_`): o título (com ".." no lugar dos emojis),
  "Postado em: HH:MM:SS AAAA-MM-DD.", a explicação da Shopee e **Apelar aqui.** (abre o
  **Recurso**: "Razão para apelar *", contador 0/200, o campo e **Enviar**; o robô nunca
  abre). O voltar da Removido volta para a lista no mesmo ponto da rolagem. Falta ver:
  se a punição antiga (05/10) ainda tem o Apelar aqui (o celular desconectou no meio).
  Recurso aceito (Rafael, 24/10/2026): a punição some da lista (ou fica "Bem-sucedido"),
  os pontos baixam e, abaixo de 6, o bloqueio some da Saúde antes do prazo; o aviso
  "banida até" continua nas Notificações, por isso o robô confere sempre na Saúde.
  O Centro do criador e a Saúde carregam pela rede: o robô relê a tela por até 24 s.
  Se a Saúde não abre antes de postar, o teste é o Postar vídeo: abrindo a Biblioteca,
  a conta não está bloqueada e o aviso antigo não vale (em 23/10 a Saúde não abriu uma
  vez, e o aviso antigo sozinho teria pausado o robô até 26/10).
- **Mapa:** os caminhos ficam nas listas `CAMINHO_PERFIL`, `CAMINHO_POSTAR` e
  `CAMINHO_PRODUTO` do `robo_shopee_video.py` (o que tocar, a espera e o que tem de
  aparecer depois). O treino confere cada passo contra elas; quando a Shopee mudar uma
  tela, remapear com o explorar e mudar ali.
- **Comentários dos vídeos (mapeado no Motorola em 24/10/2026, com o vídeo do Rafael):**
  Notificações → filtro **Lives, Vídeos e …**: cada linha é um quadro com um texto (o aviso;
  o de comentário traz o nome da pessoa, "comentou no seu vídeo:" e o comentário entre
  aspas) e a hora embaixo. Tocar no texto abre o vídeo (`HomeActivity_`) e, às vezes, uns
  8 s depois, o painel de comentários por cima; outras vezes só o vídeo (na 2ª vez que a
  mesma notificação foi aberta), e o robô toca no balão da coluna da direita. O
  **painel de comentários** (`ReactTransparentActivity_`) tem o cartão do produto no
  alto (nome, preço, "com cupom"), **"# Comentários"** (no vídeo sem nenhum comentário, o
  painel abre com "0 Comentário" e já com o campo "Adicionar um comentário..." em foco e o
  teclado aberto: o robô escreve direto, sem tocar no "add a comment"), e cada comentário com a foto (x≈84;
  a resposta fica recuada, x≈178), o nome (e o selo **"Criador"** quando é o Rafael), o
  texto, o coração (desc "… comment like", x≈1014), a data ("há # …" ou "# de …"),
  **Responder** e "Curtido pelo criador". O primeiro da lista é a legenda do vídeo, com o
  selo Criador. Embaixo, os emojis rápidos e o campo "add a comment" com o botão de enviar
  ao lado (x≈1007). O toque em **Responder** abre o teclado e o campo vira "… a …" (a
  resposta àquela pessoa); o voltar fecha o teclado e o segundo voltar sai da resposta.
- **Feed Live e Vídeo (mapeado no Motorola em 24/10/2026):** a aba de baixo **Live e
  Vídeo** abre o player em tela cheia, com as abas Vídeos, Lives e **Para você** no alto;
  o rolar passa ao seguinte. **Live:** ids `live_room_in_video_feed_…`,
  `tv_audience_viewer_num` (espectadores), `tv_send_message` (Diga alguma coisa) e o
  "Compre Agora" do produto (proibido). **Vídeo:** player `rn_vod_player_view_…`, o cartão
  do produto com "Comprar com cupom" (proibido), o nome do criador e a legenda embaixo e, na
  coluna da direita (x≈1002), a foto ("… profile avatar icon"), o **coração** (~1645, desc
  "like …" sem curtir e "unlike …" curtido, com o número), o **balão de comentários**
  (~1806, com o número), compartilhar ("… video share icon", ~1982) e mais. O nome do
  criador fica no "video caption user" e a legenda no "video caption …".
- **Rascunhos:** tabela `shopee_video_rascunhos` (estados preparando → rascunho →
  aprovado → postado, ou recusado → apagado; pulado quando o problema é do vídeo). O
  vídeo e o print ficam em `~/shopee_video/rascunhos` (ID.mp4 e ID.png). Na galeria do
  celular, o vídeo de cada rascunho tem nome próprio (`robo_shopee_video_ID.mp4`), para
  ser o mais novo, e sai de lá depois de postado ou apagado.
- **Mapeado no Motorola (22/10/2026, à noite, 13 rodadas do explorar, sem verificação):**
  - **curtir:** o link abre a página curta (`ReactActivity_`); o toque no nome abre a
    página completa, com o coração (`buttonItemLike`; curtido: `buttonItemLiked`). Testado
    com o nome que tem selo ou número antes (`nome_na_pagina`);
  - **sair da tela final sem salvar:** o voltar abre o aviso "Se você voltar, ... serão
    ..." (`content`), com Cancelar (`buttonDefaultNegative`) e o confirmar
    (`buttonDefaultPositive`). Confirmar volta para a edição do vídeo; um segundo voltar
    no aviso só fecha o aviso. Num **rascunho aberto**, confirmar e voltar de novo leva
    à lista, e **o rascunho continua salvo** (o robô pode abrir um rascunho para
    conferir e desistir sem perder nada);
  - **Perfil em Shopee Vídeo:** o 1º quadro da grade é "Rascunhos: N", que **só aparece
    com algum rascunho salvo**; depois vêm os vídeos **Fixados** (rótulo "Fixado" no
    canto) e só então o mais novo. A grade carrega pela rede depois do Postar vídeo: o
    robô espera até 18 s o quadro aparecer (24/10/2026, a postagem parou sem esperar);
  - **grade do Perfil, os números (mapeada no Motorola em 29/10/2026):** 3 quadros por
    linha, de ~359x476 (centros em x 179, 540 e 901; a 1ª linha em y ~1443, a 2ª em ~1921;
    a 3ª fica cortada pela beirada). Cada vídeo é um quadro com a descrição "... video N";
    dentro dele, o número de visualizações embaixo (um texto, ~92% da altura do quadro: "123"
    ou, nos maiores, com letra, como "1,2 mil") e, nos fixados, o texto "Fixado" em cima à
    esquerda (~9% da altura). A grade não diz qual vídeo é qual: o robô reconhece os dele
    pela marca da capa (`visualizacoes_shopee_video`), guardada no post, e lê os números uma
    vez por dia, rolando a grade (medição da capa com chamada, P76);
  - **lista de rascunhos:** o texto de aviso no alto, os quadros (o 1º em ~179,658, com a
    data embaixo) e Selecionar (~933,173). Em Selecionar, o alto vira Cancelar e embaixo
    aparece **"Excluir (N)"** (~539,2312); o toque no quadro o marca. Excluir abre
    **"Excluir vídeos selecionados?"** com Cancelar (~329,1312) e **Confirmar**
    (~751,1312). Depois de confirmar, a lista fica vazia e o quadro some do Perfil. O
    robô só confirma com "Excluir (1)";
  - **link do post:** o vídeo no Perfil abre o player (`NativePlayerActivity`); o ícone de
    compartilhar fica na coluna da direita (~1001,1985, sem texto, só a descrição) e abre
    a folha com os apps e, embaixo, **Copiar link** (~360,2251), Salvar e Fixar. O app
    mostra "Link copiado". O robô lê o link copiado (testado com o passo `copiado`: um
    link curto da Shopee, sem nunca mostrá-lo no log). O ícone tem a descrição "... video
    share icon" e só vale no player (o Perfil tem um compartilhar do perfil, no alto).
  - **voltar da edição de um vídeo novo** (23/10/2026, ao descartar a postagem de teste):
    depois do aviso de sair da tela final, a edição (`SSZMultipleEditActivity`) pergunta
    "Deseja sair da página de edição?", com Salvar Rascunho (`tv_save`), **Descartar**
    (`tv_no_save`) e Cancelar (`tv_cancel`). O robô descarta; depois, mais dois voltar
    chegam ao Perfil.
  - **voltar que sai da Shopee** (23/10/2026, o Rafael via o Telegram na frente no
    Motorola): um voltar a mais sai do app e mostra o que estava embaixo. O robô confere o
    pacote dos elementos da tela antes de cada voltar; fora da Shopee, traz a Shopee de volta
    (`app_start`, sem fechar o app) e nunca aperta voltar no outro app.
  - **conferir o título na legenda** (23/10/2026, passo `legenda`): a leitura pela acessibilidade
    (o retrato da tela e o `get_text`) devolve cada emoji de fora do plano básico (💡, 👗) como ".."
    (138 caracteres na tela contra 137 no título); os simples (✨) passam. A bio e as legendas
    postadas à mão no Perfil também aparecem com "..". A cópia do campo (Ctrl+A e Ctrl+C) trouxe o
    texto certo, com os emojis, escrito pelo `set_text` ou colado (`colar`): o app guarda o emoji, só
    a leitura troca. O robô escreve pelo `set_text` do campo em foco e confere pela cópia, com a
    edição da legenda aberta; sem a cópia, para. Na tela final, o Ctrl+A abre a edição do texto e
    tira o Postar e o Rascunhos da tela (o voltar fecha): ao reabrir um rascunho, o robô só lê pela
    acessibilidade e aceita ".." no lugar do emoji.
  - **link de vídeo, o Ver Produtos** (23/10/2026, explorar com `video:link-de-video`): o link
    abre o player do vídeo (`HomeActivity_`, aba Live e Vídeo) com **"Ver Produtos (N)"** e, ao
    lado, um cartão com **"Comprar com cupom"** (proibido, como todo texto que começa com
    "comprar" ou "compre"). Vídeo apagado: a página "… do Vídeo" com **"Este vídeo foi
    removido"**. O toque em Ver Produtos abre por cima (`ReactTransparentActivity_`) os cupons
    da loja, os **cartões dos produtos que o criador vinculou** (nome, preço, avaliação e o
    Comprar com cupom), **"Ver Mais (N)"** e **"Você Também Pode Gostar"** (recomendações da
    Shopee, que não são do vídeo). O toque no nome abre a página do produto
    (`HalfPdpActivity`), com o coração (`buttonItemLike`/`buttonItemLiked`) e o nome no id
    **`labelProductPageProductName`**; o voltar volta à lista. O selo da loja (Full, Oficial,
    Indicado) antes do nome é uma imagem dentro do texto e chega como um **"0" colado na 1ª
    palavra** ("0Tênis ...", 29/10/2026, na lista do Ver Produtos); o robô tira esse "0" ao ler
    e comparar nomes (`sem_o_selo_colado`), também ao achar os nomes dos cartões da lista (sem
    isso, o nome parecia um número e a lista ficava vazia), e a busca pela foto conta os
    cartões que vieram assim ("N com o selo colado"). **Vídeo com um produto só**
    (24/10/2026): o player não mostra o "Ver Produtos (N)"; no lugar dele, embaixo do cartão,
    fica a **barra dos produtos** (descrição terminada em "video product icon") com o desconto
    e o nome. O toque na barra abre a mesma lista, com "Ver Produtos (1)", o cartão do produto
    do criador e o "Você Também Pode Gostar" logo abaixo (sem o "Ver Mais").
  - **mais de um produto na tela final** (23/10/2026): com um produto anexado, a tela mostra
    **"Adicionar Mais"** (`tv_add_more`), que abre a mesma lista (o anexado aparece como
    "Adicionado"; cada item mostra a taxa de comissão); Adicionar → "Editar nome do produto" →
    Feito, e a tela final mostra os produtos lado a lado (`rv_product`, um `tv_product_title`
    e um X `iv_close` cada). Sem legenda escrita, o voltar da tela final vai direto à edição,
    sem o aviso de sair.
  - **o robô com link de vídeo:** abre o vídeo, toca em Ver Produtos e, em cada produto
    vinculado (até 6, nunca os recomendados), lê o nome na página, a IA confere vídeo × nome 2
    vezes, e o confirmado é curtido. Anexa todos os confirmados (o 1º pelo Adicionar produto,
    os outros pelo Adicionar Mais) e confere a tela final um a um. Nenhum confirmado, ou vídeo
    removido: o vídeo fica de lado. Os produtos de "Ver Mais" ainda não entram.
  - **link de vídeo sem o Ver Produtos** (23/10/2026: 3 vídeos pulados assim no dia): o robô
    olha de novo depois de mais 8 s e, se ainda não há, diz qual tela viu, em texto fixo que
    o `investigar_robo.yml` mostra: o link não abriu o player (`rn_vod_player_view_with_surface`),
    o player tem o cartão de um produto (com o botão de comprar) sem o Ver Produtos, ou nem
    isso. O cartão de um produto só ainda não foi mapeado no celular.
- **Busca pela foto (o Rafael mostrou em vídeo em 28/10/2026; mapeada no Motorola na mesma noite):** é
  como ele acha o mesmo produto em outras lojas, para os espaços livres até 6 (P59, P66) e a
  troca de loja (P57). O caminho, como ele faz no celular dele:
  1. a foto: ele abre o produto do post, passa para a 2ª foto do anúncio (a 1ª costuma ser
     vídeo) e tira print. O robô usa a foto do anúncio que a API de afiliado dá: o passo
     `foto` do explorar a põe na galeria, como a mais nova, e o `foto:apagar` tira (o
     `video:apagar` tira o vídeo do teste que o passo `video` pôs);
  2. Eu → Criadores & Afiliados → a barra **"Pesquisar produtos e lojas"**, no alto da área
     de afiliado (aba Oferta), tem uma **câmera** à direita, antes do ícone de chat;
  3. a câmera abre com "Clique no botão para buscar" (o botão de tirar foto, que o robô não
     usa) e, embaixo, **"Pesquisar na galeria"** (com "Ver tudo"): o toque na foto faz a busca;
  4. abre por cima **"Resultados da busca por imagem"** (X para fechar). No alto, os
     **recortes** que o app achou na foto (cada parte da foto, um produto) e uma câmera para
     outra foto: o recorte escolhido muda os resultados, e às vezes é preciso passar de um a
     outro até chegar ao produto. Embaixo dos recortes, as ordens **Comissão (%)**,
     **Vendas Populares**, **Preço** (com setas) e uma quarta, cortada na borda
     ("Comissão…"). Trocar de recorte desfaz a ordem;
  5. cada resultado (grade de 2 colunas): o selo da loja (Oficial, Indicado, Full), o nome em
     2 linhas, o selo **COMISSÃO EXTRA** quando tem, o preço, a nota com "N vendas" (na ordem
     Vendas Populares, "N vendas/mês") e "Taxa de comissão N%" (cortada quando não cabe), com
     um ícone vermelho de compartilhar (nunca tocar);
  6. o toque no resultado abre a **página de afiliado** do produto: foto, preço, **COMISSÃO
     EXTRA N%** (quando tem), o nome com a seta ">", "N Afiliados promoveram", a nota e "N
     Vendido", "Aprenda Com Outros Criadores", a loja ("Comissão de até N%", Visitar) e, na
     barra de baixo, Chat, **Favoritar** e **Compartilhe para Ganhar** (nunca tocar: o
     explorar recusa, como o Compre Agora);
  7. o toque no nome abre a página completa do produto (a mesma do curtir, com o coração e o
     "Compre com cupom", que nunca se toca); o coração curte ("Adicionado aos Meus Favoritos
     com sucesso!") e o voltar volta aos resultados.
  - **Como o Rafael escolhe:** na ordem Comissão (%) vêm os de comissão alta, mas muito caros;
    por isso ele prefere **Vendas Populares** e, ali, pega os que têm **COMISSÃO EXTRA**, que
    vendem mais. No robô (escolhas dele em 28/10, P67 e P68): só o mesmo item (mesma marca,
    modelo e cor, conferido pela IA); ordena por Vendas Populares e, entre os primeiros (uns
    20), fica com os que pagam mais reais por venda, até 20% mais caros que o do post (P58).
  - **No Motorola (28/10/2026, 5 explorações, sem Verificação, nada curtido):** tudo é a mesma
    `ReactActivity_`, com ids `AN_…`:
    - área de afiliado: a câmera da barra é `AN_ImageSearchIconEntry_IcCameraOutline_Img`
      (~896,189), ao lado do chat `AN_ChatEntry_IcChatMulti_Img` (~1014,189);
    - câmera: "Clique no botão para buscar", o botão de tirar foto (~541,1570; nunca tocar:
      tiraria foto com a câmera do Motorola), "Pesquisar na galeria" e "Ver tudo" (~982,1842),
      e a faixa da galeria com a foto mais nova em 1º (~158,2037). O X (~63,169) fecha a câmera
      e volta à área de afiliado; dali, o voltar volta à aba Eu;
    - resultados: título "Resultados da busca por imagem" e o X
      `AN_component_IcCloseShape_Img` (~1018,274), que volta à câmera. Os recortes são
      `AN_CandidateImg_Uri_Img` (a foto do anúncio deu um só), seguidos da câmera
      (~236,415) para outra foto. As ordens: "Comissão (%)" (~137,578), "Vendas Populares"
      (~420,578; a escolhida ganha `AN_FilterItem_SelectionTick_Img`), "Preço" (~651,578,
      com `AN_FilterItem_Image_Img`) e uma quarta que começa com "Comissão da" (~938,578);
    - cada resultado (2 colunas): a foto, o selo da loja `AN_component_Source_Img`, o selo de
      Comissão Extra como imagem (`AN_Labels_Content_Img`, sem texto), o nome em texto, "R$"
      e o preço em textos separados, as estrelas (`imagefullFilledStar_undefined`), "N
      vendas" e **"Taxa de comissão N,N%" em texto inteiro** (o corte é só na tela), com o
      compartilhar `AN_CommRate_ShareIconWithBg_Img` ao lado (nunca tocar). O `rolar:baixo`
      rola os resultados; aparece `AN_ScrollToTopIcon_ToTopIcon_Img`;
    - o toque no resultado (no nome ou no preço) abre a página de afiliado do produto: fotos
      `AN_ProductImages_Image_Img`, a faixa de preço "R$#-R$#", o selo de Comissão Extra
      (imagem) e a porcentagem "N,N%" em texto, o nome com a seta
      `AN_component_RightArrow_Img_2` (abre a página completa), "N Afiliados promoveram", a
      nota, "Aprenda Com Outros Criadores" e a loja `AN_ShopHeader_Image_Img`. No alto, o
      voltar `AN_FullScreenTitleBar_CircleBack_Img_1` e o compartilhar
      `AN_FullScreenTitleBar_CircleShare_Img` (nunca tocar); embaixo, o chat
      `AN_ChatButton_IcChatSingleOrange_Img` (nunca), o **Favoritar**
      `AN_LikeButton_IcLikeSolidIconLike_Img` (~405,2309) e o Compartilhe para Ganhar
      (~810,2325; o explorar recusa). O voltar volta aos resultados, na mesma ordem e rolagem.
  - **No Motorola (29/10/2026, 4 explorações, sem Verificação, nada salvo):**
    - na ordem **Vendas Populares** (o toque em "Vendas Populares" marca a ordem), os
      cartões vêm logo abaixo das ordens; cada `rolar:baixo` sobe uns 1.150 px (um pouco mais
      que uma linha da grade, que tem uns 936 px), e o alto (o título e o X) fica parado. O
      robô lê só o cartão inteiro (o nome, o preço e a taxa de comissão na tela);
    - uma foto que o app não reconhece dá **"Nenhum produto encontrado"**, com "Tirar uma nova
      foto", "Pesquisar por texto" e **"Você também pode gostar"** (recomendações, não a
      busca), sem os recortes; na ordem Vendas Populares, essa tela mostra cartões sem o
      aviso, que são as recomendações: o robô não ordena nem lê nada e segue sem os produtos a
      mais;
    - o **Adicionar Produto** (Minhas Curtidas → Mais Recente) mostra uns 6 produtos por tela,
      cada um com o Adicionar à direita (~924); o já anexado fica como "Adicionado", e o
      próximo "Adicionar" é o do produto seguinte;
    - a **tela final com 6 produtos** mostra só o 1º inteiro e o começo do 2º: a fileira
      `rv_product` rola para o lado, e a ordem é a do anexar. Sem legenda escrita, o voltar da
      tela final vai para a edição do vídeo (`SSZMultipleEditActivity`) sem aviso.
  - **O robô (P59, 29/10/2026), nos vídeos de link de produto:** a foto do anúncio do produto
    do rascunho na galeria → Eu → Criadores & Afiliados → a câmera → a foto mais nova →
    Vendas Populares → os primeiros 20 cartões → o X e o voltar até a aba Eu; a foto sai da
    galeria. Cada cartão é achado na API pelo nome e pelo preço, a IA confere com o vídeo os
    do preço parecido, e os confirmados são curtidos pela **página completa** (o link curto de
    cada um, como o do link: o Favoritar da página de afiliado não é usado) e anexados do que
    paga mais para o que paga menos. A tela final é conferida produto a produto, rolando a
    fileira devagar (uns 40% da largura por vez, sem embalo) até o fim e voltando ao começo.
  - **Falta:** o "Ver Mais (N)" do Ver Produtos (P66), quando a fonte trouxer um vídeo com
    ele, e os espaços livres dos vídeos de vários produtos (P57).

## Onde paramos

- **Android virtual:** Redroid (Android 13) em Docker no servidor (`android_virtual.py`).
  Em 05/10/2026 foi apagado (apps e login, ação `apagar` do `android.yml`) e ficou
  desligado. O Docker, a imagem e as ferramentas continuam no servidor.
- **App da Shopee:** vem do celular do Rafael pelo SAI (backup `.apks`) e entra pelo
  botão "Enviar app" da tela (`tela_android.py`). Os sites de APK e a Play Store
  recusam o servidor.
- **Tela no navegador:** `tela_android.py` funciona. Ela é aberta pelo `android.yml`
  (ação `tela`); o botão do painel saiu no modo assistente.
- **Exploração:** `postador_shopee_video.py --explorar` (ação `explorar` do
  `android.yml`) toca na tela e descreve cada uma sem os dados da conta. Nunca toca
  em Postar.
- **O que já se sabe do app:**
  - a aba **Eu** é nativa: o robô lê e toca nela sem problema;
  - **Criadores & Afiliados** abre uma página web (WebView). Ali apareceu a página
    "**Verificação**" de segurança, com erro ao carregar;
  - abrir o app pelo **ícone** funciona. O comando direto (monkey) não abriu depois de
    o app ser fechado à força;
  - uns 20 s depois de abrir, o app foi sozinho para a Verificação;
  - a Verificação começou depois de várias explorações em meia hora, com o app
    fechado e reaberto muitas vezes.
  - travamento (Motorola, 24/10/2026): o Android mostra "Shopee não está respondendo",
    com `@aerr_close` (Fechar app) e `@aerr_wait` (Aguardar). Travada, a tela da Shopee
    (`HomeActivity_`) fica sem nenhum elemento e cada leitura demora cerca de 1 min. O
    robô toca em Aguardar 3 vezes e, se não voltar, em Fechar app e reabre (P15).
  - loja de férias (24/10/2026): a página do produto mostra "Esse vendedor está de
    férias." por alguns segundos, embaixo, por cima do Compre Agora. O produto curtido
    entra em Meus Favoritos, mas não aparece no Adicionar Produto do vídeo. O robô lê o
    aviso ao abrir a página e pula o vídeo.
- **No celular de verdade (17 e 18/10/2026), o caminho até Rascunhos:**
  1. abrir → **Eu** → **Criadores & Afiliados** (quase sempre tela nativa; às vezes abre
     como página web) → aba **Conta** → **Perfil em Shopee Vídeo** → **Postar vídeo**
     (embaixo, à direita);
  2. a câmera da Shopee abre (abas Vídeo e Modelos, Efeito, Adicionar Música) →
     **Biblioteca** → Galeria (abas Tudo, Vídeo e Foto) → marcar o vídeo (o círculo no
     canto da miniatura, `@ll_check`) → **Próximo (1)** (depois de marcar, ele sobe para o
     alto: `@tv_pick_top_next`, ~919,2103; o `@tv_pick_next` some). No alto da Galeria,
     à direita, fica **Rascunhos** (`@ll_draft`, ~914,193): a lista dos rascunhos;
  3. na primeira vez aparece a janela **Dicas de Upload** → **Ok** → **Próximo**; nas
     outras, a prévia do vídeo → **Próximo** no alto (`@tv_pick_top_next`);
  4. edição do vídeo (Adicionar Música, Efeito de giro, Filtro, Efeitos; Cortar, Texto,
     Captions, Figurinha) → **Próximo** (`@tv_compress`);
  5. tela final (`PublishVideoActivity`): **Adicionar legenda** (onde vai o título),
     Selecionar Capa, Hashtag, **Adicionar produto** (abre a lista com busca, abas
     **Minhas Curtidas** e **Todos** (em 24/10/2026, no Motorola, vieram também **Minha
     Loja**, antes de Minhas Curtidas, e **Afiliados**, no fim; o app abre em Minhas
     Curtidas → Mais Recente), ordem Relevância/Mais Recente/Em Destaque/Preço e,
     em cada produto, taxa de comissão, preço e **Adicionar**; o voltar devolve a tela
     final sem perder o vídeo), as chaves Permitir a reutilização, Salvar no dispositivo,
     Rótulo de IA e Compartilhar automaticamente, e embaixo **Rascunhos** e **Postar**.
     O Rótulo de conteúdo gerado por IA tem a explicação embaixo do nome e a chave à
     direita, na mesma linha; o robô acha a chave pela linha do nome e confere o
     `checked` depois do toque (a classe e o id dela ainda não foram vistos no Motorola).
     Com produto anexado, a linha pode ficar abaixo da tela (24/10/2026, de madrugada, o
     rascunho parou sem achá-la): o robô rola até 3 vezes atrás dela e depois volta ao
     alto; sem achar, o motivo diz se a linha do nome estava e quantas chaves viu;
  6. **Rascunhos** salva (barra de progresso "carregando, aguarde") e volta para a aba
     Live e Vídeo, sem pedir confirmação.

  **Selecionar Capa (mapeado no Motorola em 30/10/2026, à noite, num vídeo de teste):**
  1. na tela final, **Selecionar Capa** (`@tv_select_cover`, ~173,597) abre **Selecione sua
     capa** (`SSZMediaCoverEditActivity`): a capa no meio (`@player_container`, de 0,267 a
     1080,1969; o quadro do vídeo vai de 61,267 a 1018,1969), a fileira de quadros embaixo
     (`@iv_thumbnail`, em y ~2116; o 1º, o do começo, vem marcado), **Adicionar Texto**
     (`@fl_add_text`, ~280,2313) e **Adicionar figurinha** (`@fl_add_sticker`, ~799,2313); no
     alto, **X** (`@cancel_btn`, ~79,194) e **✓** (`@save_btn`, ~1001,194). O Rafael escolhe
     a capa por último, depois do título e dos produtos: o vídeo precisa terminar de processar;
  2. **Adicionar figurinha** abre as abas (em y ~1306): a 1ª, só um ícone (`@image`, ~65,1306),
     é a da **foto**; depois vêm Texto, outras e Shopee. Sem foto usada antes, a aba da foto
     mostra **Enviar** (`@btn_upload`, ~540,1918); depois do 1º uso, mostra a lista
     (`@local_sticker_frame_layout`) com o **+** em 1º (~146,1507) e as fotos já usadas
     ("toque e segure para excluir");
  3. **Enviar** (ou o **+**) abre **Fotos** (`SSZMediaAlbumSingleChoiceActivity`), com a mais
     nova em 1º (`@iv_picture`, ~133,403);
  4. a foto abre no recorte (`SSZMediaStickerCropActivity`), com a foto inteira marcada e o
     **Remover fundo** desligado (`@cb_full`) → **Próximo** (`@tv_next_full`, ~937,2268);
  5. de volta à capa, a figurinha entra no meio da capa (~540,1118) com 540 px de altura (a
     caixa: 304x540 numa imagem 9:16, 539x540 numa quadrada; a imagem ocupa uns 88,6% dela);
  6. dois dedos (o passo `aumentar`) aumentam a figurinha em volta do meio deles, só até 3
     vezes o tamanho com que ela entrou (mais que isso, nada muda): a capa inteira (9:16) para
     em 84% da largura; uma imagem 2:3 ou mais larga cobre a largura toda, e em cima e embaixo
     sobra o quadro do vídeo (por isso vai à galeria o miolo 2:3 da capa,
     `edicao_video.recorte_da_figurinha`);
  7. o **X** com alguma mudança pergunta **Descartar Alterações na Capa?** (`@tv_cancel`
     Cancelar, `@tv_discard` Confirmar); depois, a saída da tela final é a de sempre (voltar,
     voltar, `@tv_no_save`). Falta testar o **✓** e como a capa aparece na tela final e no
     rascunho.

  **Teste completo (18/10/2026)**, da tela final em diante:
  1. legenda: `tocar:@et_caption` → `titulo` (o título da IA; no log, só o tamanho) →
     **OK** no alto à direita (`@tv_right`, ~1012,178), que fecha o teclado;
  2. `tocar:@ll_add_product_symbol` (Adicionar produto, ~728,738) → a lista
     (`ReactActivity_`) → **Minhas Curtidas** → **Mais Recente**;
  3. **Adicionar** do produto do vídeo (coluna x=924; o do 1º produto em ~924,977). A
     bolinha de dicas da Motorola (`com.motorola.mototour`, em ~1001,1024) pode ficar
     em cima e pegar o toque: fecha em **Agora não** (~538,1718), e o toque se repete.
     Neste teste o toque foi pela posição e pegou o produto errado: o vestido estava em
     1º, mas o "Agora não" da bolinha fica na altura do 4º produto (uma Fibra de cabelo)
     e quase certamente caiu na lista; a janela seguinte veio com o preço da Fibra. O
     Rafael publicou o rascunho e viu. Agora é o passo `produto`: acha o produto do vídeo
     pelo nome (o da API, pelo link), toca no Adicionar dele fora da bolinha e confere o
     nome na janela que abre; sem achar ou com outro produto, para e avisa no privado;
  4. abre a janela **Editar nome do produto** (`ReactTransparentActivity_`) → **Feito**
     (~540,2315), sem mudar o nome;
  5. de volta à tela final, o produto aparece com "Sem Cupom" e o botão "Adicionar Mais"
     (~888,731) → `print` (a tela no privado do Rafael) → `tocar:@tv_drafts_box`
     (Rascunhos, ~112,2308). **Postar** (`btn_post`, ~631,2303) só pelo passo `postar`,
     depois do OK do Rafael no `print:postar`.

  **Segundo teste completo (18/10/2026, à tarde)**, com as conferências: `video:novo` →
  `ia` (confirmou) → `link` → curtir → … → `produto` (achou pelo nome, o 1º de Mais
  Recente; a janela conferiu) → Feito → `conferir` → `comentario` → `print` → o Rafael
  liberou → Rascunhos (a conferência da tela final passou e o app voltou para Live e
  Vídeo). Nenhuma verificação da Shopee nas 11 rodadas. Escolha do Rafael para esse
  rascunho: o robô publica, com o OK dele (Galeria → Rascunhos → abrir → tela final →
  `conferir; print:postar` → OK → `postar` → achar o link do post).

  **Publicar um rascunho (18/10/2026, mapeado e feito):** Eu → Criadores & Afiliados →
  Conta → Perfil em Shopee Vídeo (`ReactActivity_`): o 1º quadro da grade Vídeos é
  **"Rascunhos: N"** (`tocar:Rascunhos`) → a lista (rascunhos lado a lado, ~179,658 e
  ~540,658, data embaixo; "Selecionar" no alto, ~933,173) → o rascunho abre na edição
  (`SSZDraftMultipleEditActivity`) → `tocar:@tv_compress` → a tela final com produto e
  legenda guardados → `conferir; print:postar` → OK do Rafael → `postar` → o app volta
  para Live e Vídeo. O post saiu às 20:20 e foi removido em 1 min por propriedade
  intelectual (vídeo copiado; a fonte do painel está fora dos Autorais, escolha do
  Rafael mantê-la). Falta mapear: o link do post (Perfil → o vídeo → compartilhar →
  copiar link) e apagar um rascunho (Selecionar na lista). O rascunho só-vídeo antigo
  ainda está na lista. **Rascunho com vários produtos (30/10/2026):** às 07:10, com o
  celular lento, um rascunho de 3 produtos reaberto para postar mostrou a tela final sem a
  linha dos produtos (nem "Adicionar produto"); às 08:12 o mesmo rascunho abriu com a linha
  e os produtos na hora (`rv_product`, 2 nomes à vista): os produtos ficam salvos no
  rascunho, a linha só demora. A conferência espera até 15 s por ela.

  **Retomada (quinta, 22/10/2026, 15h):** o robô automático foi montado (seção Robô
  automático, no alto). O celular estava desconectado nessa hora (a porta da Depuração
  por Wi-Fi mudou): o mapeamento que falta espera o Rafael reconectar.

  **Teste de 19/10/2026 (08:15):** parou na curtida. O link de produto abre a página
  curta (ReactActivity_: foto, preço, nome com a seta ">", Compre Agora, "Escolhas
  Populares para Você"), sem o coração; tocar no nome do produto abre a página completa
  (passo `curtir`).

  Ainda não testado: link que, em vez da página do produto, abre um **vídeo com o
  produto anexado** (alguns links são assim). Quando aparecer, mapear onde fica o
  produto do vídeo para curtir.

  Permissões que o Rafael deu com a mão, uma vez: câmera ("Durante o uso do app") no
  primeiro Postar vídeo, e fotos e mídia na primeira Biblioteca. O vídeo do passo `video`
  sai da Fonte dos Vídeos do painel. Verificação (CAPTCHA): na 1ª rodada (20 s depois de
  abrir o app) e na 16ª (18/10, 04:27, ao tocar em Criadores & Afiliados, que abriu como
  página web); nas 14 rodadas entre elas, com uns 15 min de espera, nenhuma.
- **Por que parou:** o Rafael não quer arriscar a conta principal. A Shopee vê que é
  servidor de nuvem e Android virtual.

## O caminho da postagem (tutorial do Rafael)

1. Abrir o link do post e, em "Ver Produtos", curtir só os produtos que o criador
   vinculou (nunca os de "Você Também Pode Gostar").
2. Eu → Criadores e Afiliados → Perfil em Shopee Vídeo → Postar vídeo → o vídeo na
   galeria → Próximo. Efeito de giro é opcional.
3. Adicionar Produto → Minhas Curtidas → Mais Recente: os curtidos agora ficam em
   cima (curtiu 2, são os 2 primeiros). Entre eles, o de menor preço primeiro; no
   empate, o de maior comissão. O app pode mostrar o nome de outro jeito que a API (em
   24/10/2026, o curtido estava em 1º sem nenhuma palavra do nome da API): o robô pega
   entre os curtidos agora no topo o de nome parecido (80% das palavras), depois o nome
   igual mais embaixo e, em última chance, o 1º se a IA conferir a foto dele com o vídeo
   (escolha do Rafael, P18); a janela, a tela final e o postar conferem o nome da lista. Na
   janela "Editar nome do produto", só **Feito**. O produto que já estava curtido de
   outro dia fica mais embaixo: o curtir o descurte e curte de novo (pedido do Rafael,
   24/10/2026), e ele sobe ao 1º lugar. O anexar espera a lista carregar e rola até 8
   vezes, parando no fim da lista (para o toque de descurtir que não pegou); o registro
   anota "já estava curtido" no curtir e, no anexar que não acha, quantas vezes rolou.
4. Título no campo da legenda; as chaves da última tela como vêm.
5. Postar. Curtir e comentar nunca é automático (diretriz 9.1.1).

Caminho alternativo, ainda não testado: a aba **Live e Vídeo** tem um ícone de
postar no alto da tela, com telas nativas, que o robô lê melhor que a WebView.

## Para voltar

1. **Conta:** testar com um **perfil reserva**, nunca com a conta principal, até
   provar que funciona por semanas sem verificação nem bloqueio.
2. **Ligar:** `android.yml` → `preparar` (liga do zero). Mandar a Shopee pelo SAI na
   `tela`, entrar com o perfil reserva e resolver a verificação na mão.
3. **Explorar devagar:**
   - uma rodada por vez, com poucos toques;
   - espera de vários segundos entre toques, e tempos que variam;
   - não fechar e reabrir o app em seguida;
   - no celular, só das 8h às 22h de Brasília (escolha do Rafael em 18/10/2026, depois
     que a verificação das 04:27 expirou com ele dormindo); o `explorar` recusa fora disso;
   - a verificação para a exploração na hora (o `explorar` não toca nela), e o Rafael
     resolve com a mão; no celular de verdade a exploração continua depois (escolha
     dele em 17/10/2026).
4. **Mapear até Rascunhos:** Postar vídeo → galeria (o vídeo entra pelo passo
   `video` do explorar) → Próximo → Adicionar Produto → legenda. O primeiro teste
   termina em Rascunhos.
   - Teste completo (escolha do Rafael em 18/10/2026): `video` escolhe e guarda o
     vídeo do teste; `link` abre o produto dele para curtir; `titulo` escreve o título
     da IA na legenda; o produto sai de "Minhas Curtidas"; `print` manda a tela no
     privado do Rafael antes de tocar em Rascunhos; `produto` toca em Adicionar só no
     produto do vídeo, achado pelo nome na lista.
   - Conferências do produto (escolha do Rafael em 18/10/2026, depois de um ponto de
     punição da Shopee pelo produto errado): `ia` (a IA confere se o produto do link é o
     do vídeo), `produto` (pelo nome, na lista e na janela "Editar nome do produto") e
     `conferir` (na tela final, o único produto anexado é o do vídeo; o toque em
     Rascunhos confere sozinho). Qualquer uma que não bate para a rodada e avisa no
     privado.
   - O `link` abre o link do vídeo como veio (o app segue o link curto sozinho), como
     o Rafael faz com o link do modo assistente. Aberto pelo endereço final do produto
     (/product/loja/item), o app ficou preso no esqueleto da página, carregando
     (3 rodadas em 18/10/2026; foto do Rafael).
   - O link de vídeo de outro afiliado abre a página de entrada da Shopee: busca da
     categoria em cima, o produto do vídeo no alto (bloco do preço em 540,1271) e
     "Escolhas Populares para Você" embaixo. Tocar no bloco do produto abre a página
     do produto. Nela, o coração de curtir é `buttonItemLike` (ponta direita da linha
     do preço, ~1028,1233); embaixo ficam `buttonProductChatNow`,
     `buttonProductAddCart` e `buttonProductBuyNow`, que o explorar recusa tocar.
   - Curtir (7ª rodada de 18/10/2026): `tocar:@buttonItemLike`; depois do toque o id vira
     `buttonItemLiked` e aparece "Adicionado aos Meus Favoritos com sucesso!". Se o
     produto já está curtido, `@buttonItemLike` não existe e o passo falha sem
     descurtir. O vídeo do teste fica o mesmo em todos os passos; `video:novo` troca.
   - Descurtir (pedido do Rafael, 24/10/2026): na mesma página, tocar em
     `buttonItemLiked` volta o id para `buttonItemLike`. No fim de cada rascunho, o robô
     descurte assim os produtos que curtiu para ele (pelo link ou pelo Ver Produtos).
   - Meus favoritos de afiliado (o Rafael ensinou em vídeo, 25/10/2026): aba **Eu** →
     **Criadores & Afiliados** (no bloco "Mais atividades") → área de afiliado (abas Oferta,
     Conversão e Conta embaixo) → **Meus favoritos** (o coração, ~746,722). É a lista
     `AN_MyLikesListPage`, a mesma do Minhas Curtidas do Adicionar Produto. O título diz
     quantos há ("Meus favoritos(1000)", até 1000), com os filtros Ordenar e Melhor Oferta e,
     às vezes, um aviso com **Substituir Tudo** (nunca tocar). Cada produto tem uma caixa de
     marcar à esquerda (`AN_Checkbox_CheckedIconUnCheckIcon_Img`, ~84) e os ícones de mais e
     compartilhar à direita. Na barra de baixo: a mesma caixa (~63,2323), o "Selecionado
     N/50" (até 50 de cada vez), o **Like** (~675,2323), que tira os marcados ("Removido das
     Minhas Curtidas com sucesso!"), e o **Compartilhar** (nunca tocar). A rotina das 4h marca
     (pela caixa de baixo; sem ela, um por um, rolando), toca em Like e repete até a lista
     acabar. Falta ver no celular se a caixa de baixo marca tudo de uma vez: o robô confere
     pelo "Selecionado N/50".
     O produto que saiu da loja fica na lista com o selo **Inválido** embaixo da foto (e a
     linha dos filtros tem um filtro Inválido, que não é selo); marcado, o Like não o tira, e
     ele continua marcado ("Selecionado 1/1", Motorola, 04:48 de 29/10/2026). Cada produto tem
     também o ícone de mais (`AN_component_OfferCard_Control_Icon_Img_more_N`), ainda não
     mapeado. Sobrando só inválidos, a rotina das 4h dá a lista por acabada.
   - Meus Favoritos de comprador (aba **Eu** → **Meus Favoritos**, Motorola, 24/10/2026): outra
     lista, com Editar, Todos, Status e Categoria e o Remover dos Favoritos; o app guarda a
     edição aberta. Não é a do Minhas Curtidas: o robô não mexe nela.
   - Página do produto presa no esqueleto (ícone de presente e barras cinzas, ids
     `ll_head_root` e `iv_head_image`), até abrindo à mão: era a verificação das 04:27
     de 18/10/2026, que expirou sem resposta. Forçar a parada da Shopee faz a
     verificação aparecer de novo; resolvida pelo Rafael, a página volta ao normal.
5. **Postar só com o OK do Rafael** (escolha dele em 18/10/2026): o robô pronto manda o
   print da tela final no privado e só toca em Postar depois da aprovação dele, pelo
   menos nas primeiras semanas; antes disso, as conferências `ia`, `produto` e `conferir`.
   Depois de postar, manda no privado o link do post, o comentário pronto e o aviso
   para curtir e comentar à mão (pedido dele em 18/10/2026). Falta mapear onde o app dá
   o link do post (compartilhar → copiar link); o comentário já sai no teste (passo
   `comentario`).
   Como aprovar (ideia e escolhas do Rafael em 18/10/2026): o robô deixa cada vídeo em
   Rascunhos e manda no privado o vídeo, o título, o link do produto anexado e o print
   da tela final, com Aprovar e Recusar. Aprovou: o robô abre o rascunho, confere a
   tela final de novo e posta. Recusou: apaga o rascunho. Falta mapear abrir e apagar
   um rascunho (Perfil em Shopee Vídeo → Rascunhos).
6. **Ritmo do robô pronto:**
   - poucos vídeos por dia no começo (1 ou 2);
   - faixa de horário e quantidade sorteada por dia, como no painel;
   - nenhum toque rápido demais;
   - o app fica aberto entre um vídeo e outro, sem sair e entrar direto.
7. **Conteúdo:** as mesmas regras do modo assistente: vídeo dos Autorais, só os
   produtos do criador, título pelo prompt do Gem, diretrizes sempre, vídeo com
   violação não sai.

## Plano do celular de verdade (em preparação desde 05/10/2026)

O robô continua no servidor, mas toca num celular de verdade do Rafael, guardado em
casa, em vez do Android virtual. A ligação é por uma rede privada (Tailscale), sem
porta aberta na internet. Para a Shopee, quem posta é um celular de verdade, na
internet de casa, com localização e sensores reais: nada é disfarçado.

```
Servidor (prepara vídeo, título, produtos)
        │  rede privada (Tailscale)
        ▼
Celular guardado (perfil pessoal do Rafael, carregador, Wi-Fi)
```

| Fase | Quem | O quê | Situação |
|---|---|---|---|
| 0 | Rafael | Celular só para isso: no carregador e no Wi-Fi, sem economia de bateria para a Shopee; Shopee pela Play Store com o **perfil pessoal** do Rafael (sem perfil reserva: escolha dele em 09/10/2026); modo desenvolvedor com "depuração sem fio" (no Motorola, "Depuração por Wi-Fi") e "Manter ativado"; app Tailscale com VPN sempre ativa | feita em 17/10/2026 (Motorola) |
| 1a | Rafael | Conta no Tailscale e uma chave de acesso (auth key) salva no GitHub como segredo `TAILSCALE_AUTHKEY`; nunca colar a chave na conversa. A chave do servidor não expira (Disable key expiry em Machines → shopee-servidor) | feita em 05/10/2026 |
| 1b | Claude | `android.yml` → `tailscale`: o servidor entra na rede privada (sem mexer no DNS nem nas rotas), com o nome `shopee-servidor` | feita em 05/10/2026: conectado |
| 1c | Claude + Rafael | Parear o adb com o celular pelo bot (Shopee Vídeo 🎬 → Celular do Robô 📱, `celular_robo.py`): o código vai só no privado e o bot apaga a mensagem; Reconectar quando a porta muda. O explorar aceita o celular (`android.yml` → `explorar-celular`) | feita em 17/10/2026: pareado e conectado (moto g(100)). Depois de um reset, o Rafael refaz as fases 0 e 1c pelo botão Passo a Passo 📖 do Celular do Robô 📱 |
| 2 | Claude | Explorar devagar até Rascunhos, com as regras de "Para voltar" | caminho mapeado até Rascunhos em 18/10/2026 (16 rodadas; o 1º rascunho só com o vídeo, sem título nem produto). Duas verificações (1ª e 16ª rodadas; a da 16ª, às 04:27, expirou com o Rafael dormindo); o Rafael escolheu continuar e resolve cada uma com a mão, com rodadas só das 8h às 22h. Teste completo feito em 18/10/2026: produto curtido pelo link, título da IA na legenda, produto por Minhas Curtidas → Mais Recente, print no privado e Rascunhos. O Rafael publicou o rascunho e viu o produto errado (o toque que fechou a bolinha da Motorola caiu no 4º produto); o passo `produto` acha o produto pelo nome e confere na janela antes do Feito. Falta repetir o teste com o passo `produto` e testar o link que abre um vídeo com produto anexado |
| 3 | os dois | Um rascunho por dia que o Rafael confere; depois 1 ou 2 postagens reais por dia, na janela e com quantidade variada; observar 2 a 4 semanas | a fazer |
| 4 | os dois | Só com semanas sem verificação nem bloqueio: pensar em aumentar o volume | a fazer |

Riscos que continuam: robô vai contra os termos da Shopee, e o ritmo calmo diminui o
risco, mas não zera. O modo desenvolvedor ligado é um sinal que alguns apps olham,
e não vamos escondê-lo. O robô posta na conta pessoal do Rafael, a principal de
afiliado: um bloqueio por automação atinge essa conta e as comissões dela. Por isso o
ritmo calmo, o teste em Rascunhos e a parada a cada verificação (o Rafael resolve com a
mão) valem desde o primeiro dia. Na 1ª rodada no celular (17/10/2026), a Shopee pediu a
verificação 20 s depois de o robô abrir o app, como no Android virtual. Se a depuração sem fio
ficar instável, a troca é um computador velho ligado em casa, com o celular no cabo
USB; o resto do plano não muda.

## O que não se faz

Disfarçar o Android para a Shopee não se faz: localização falsa, dados de sensor
falsos, imitar um aparelho real ou esconder o emulador. É driblar o antifraude dela;
a diretriz 9.2 proíbe, e o castigo tende a ser o banimento definitivo. Se o Android
virtual não passar honestamente, a alternativa é um **celular de verdade** do Rafael,
ligado em casa, que já tem localização e sensores reais (anotado no `DECISOES.md`).

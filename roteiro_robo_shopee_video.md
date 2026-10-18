# Robô da Shopee Vídeo no servidor: guardado (roteiro para a volta)

Parado desde 05/10/2026. A Shopee Vídeo é feita hoje pelo **modo assistente**
(`assistente_shopee_video.py`): o robô prepara a postagem e o Rafael posta pelo
celular. Este roteiro diz onde o robô que posta sozinho parou e o que fazer se
voltarmos a ele. As decisões ficam no `DECISOES.md`, área Shopee Vídeo.

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
- **No celular de verdade (17 e 18/10/2026), o caminho até Rascunhos:**
  1. abrir → **Eu** → **Criadores & Afiliados** (quase sempre tela nativa; às vezes abre
     como página web) → aba **Conta** → **Perfil em Shopee Vídeo** → **Postar vídeo**
     (embaixo, à direita);
  2. a câmera da Shopee abre (abas Vídeo e Modelos, Efeito, Adicionar Música) →
     **Biblioteca** → Galeria (abas Tudo, Vídeo e Foto) → marcar o vídeo (o círculo no
     canto da miniatura, `@ll_check`) → **Próximo (1)** (`@tv_pick_next`);
  3. na primeira vez aparece a janela **Dicas de Upload** → **Ok** → **Próximo**; nas
     outras, a prévia do vídeo → **Próximo** no alto (`@tv_pick_top_next`);
  4. edição do vídeo (Adicionar Música, Efeito de giro, Filtro, Efeitos; Cortar, Texto,
     Captions, Figurinha) → **Próximo** (`@tv_compress`);
  5. tela final (`PublishVideoActivity`): **Adicionar legenda** (onde vai o título),
     Selecionar Capa, Hashtag, **Adicionar produto** (abre a lista com busca, abas
     **Minhas Curtidas** e **Todos**, ordem Relevância/Mais Recente/Em Destaque/Preço e,
     em cada produto, taxa de comissão, preço e **Adicionar**; o voltar devolve a tela
     final sem perder o vídeo), as chaves Permitir a reutilização, Salvar no dispositivo,
     Rótulo de IA e Compartilhar automaticamente, e embaixo **Rascunhos** e **Postar**;
  6. **Rascunhos** salva (barra de progresso "carregando, aguarde") e volta para a aba
     Live e Vídeo, sem pedir confirmação.

  **Teste completo (18/10/2026)**, da tela final em diante:
  1. legenda: `tocar:@et_caption` → `titulo` (o título da IA; no log, só o tamanho) →
     **OK** no alto à direita (`@tv_right`, ~1012,178), que fecha o teclado;
  2. `tocar:@ll_add_product_symbol` (Adicionar produto, ~728,738) → a lista
     (`ReactActivity_`) → **Minhas Curtidas** → **Mais Recente**: o curtido por último
     fica em cima;
  3. **Adicionar** do produto escolhido (coluna x=924; o do 1º produto em ~924,977). A
     bolinha de dicas da Motorola (`com.motorola.mototour`, em ~1001,1024) pode ficar
     em cima e pegar o toque: fecha em **Agora não** (~538,1718), e o toque se repete;
  4. abre a janela **Editar nome do produto** (`ReactTransparentActivity_`) → **Feito**
     (~540,2315), sem mudar o nome;
  5. de volta à tela final, o produto aparece com "Sem Cupom" e o botão "Adicionar Mais"
     (~888,731) → `print` (a tela no privado do Rafael) → `tocar:@tv_drafts_box`
     (Rascunhos, ~112,2308). **Postar** (`btn_post`, ~631,2303) nunca.

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
   empate, o de maior comissão. Na janela "Editar nome do produto", só **Feito**.
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
     privado do Rafael antes de tocar em Rascunhos.
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
   - Página do produto presa no esqueleto (ícone de presente e barras cinzas, ids
     `ll_head_root` e `iv_head_image`), até abrindo à mão: era a verificação das 04:27
     de 18/10/2026, que expirou sem resposta. Forçar a parada da Shopee faz a
     verificação aparecer de novo; resolvida pelo Rafael, a página volta ao normal.
5. **Ritmo do robô pronto:**
   - poucos vídeos por dia no começo (1 ou 2);
   - faixa de horário e quantidade sorteada por dia, como no painel;
   - nenhum toque rápido demais;
   - o app fica aberto entre um vídeo e outro, sem sair e entrar direto.
6. **Conteúdo:** as mesmas regras do modo assistente: vídeo dos Autorais, só os
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
| 2 | Claude | Explorar devagar até Rascunhos, com as regras de "Para voltar" | caminho mapeado até Rascunhos em 18/10/2026 (16 rodadas; o 1º rascunho só com o vídeo, sem título nem produto). Duas verificações (1ª e 16ª rodadas; a da 16ª, às 04:27, expirou com o Rafael dormindo); o Rafael escolheu continuar e resolve cada uma com a mão, com rodadas só das 8h às 22h. Teste completo feito em 18/10/2026: produto curtido pelo link, título da IA na legenda, produto por Minhas Curtidas → Mais Recente, print no privado e Rascunhos. Falta o Rafael conferir o rascunho no Motorola e testar o link que abre um vídeo com produto anexado |
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

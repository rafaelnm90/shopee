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
- **Por que parou:** o Rafael não quer arriscar a conta principal. A Shopee vê que é
  servidor de nuvem e Android virtual.

## O caminho da postagem (tutorial do Rafael)

1. Abrir o link do post e, em "Ver Produtos", curtir só os produtos que o criador
   vinculou (nunca os de "Você Também Pode Gostar").
2. Eu → Criadores e Afiliados → Perfil em Shopee Vídeo → Postar vídeo → o vídeo na
   galeria → Próximo. Efeito de giro é opcional.
3. Adicionar Produto → Minhas Curtidas: o de menor preço primeiro; no empate, o de
   maior comissão.
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
   - parar no primeiro sinal de verificação.
4. **Mapear até Rascunhos:** Postar vídeo → galeria (o vídeo entra pelo passo
   `video` do explorar) → Próximo → Adicionar Produto → legenda. O primeiro teste
   termina em Rascunhos.
5. **Ritmo do robô pronto:**
   - poucos vídeos por dia no começo (1 ou 2);
   - faixa de horário e quantidade sorteada por dia, como no painel;
   - nenhum toque rápido demais;
   - o app fica aberto entre um vídeo e outro, sem sair e entrar direto.
6. **Conteúdo:** as mesmas regras do modo assistente: vídeo dos Autorais, só os
   produtos do criador, título pelo prompt do Gem, diretrizes sempre, vídeo com
   violação não sai.

## O que não se faz

Disfarçar o Android para a Shopee não se faz: localização falsa, dados de sensor
falsos, imitar um aparelho real ou esconder o emulador. É driblar o antifraude dela;
a diretriz 9.2 proíbe, e o castigo tende a ser o banimento definitivo. Se o Android
virtual não passar honestamente, a alternativa é um **celular de verdade** do Rafael,
ligado em casa, que já tem localização e sensores reais (anotado no `DECISOES.md`).

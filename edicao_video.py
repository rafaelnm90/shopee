#!/usr/bin/env python3
"""
A edição dos vídeos da Shopee Vídeo como o Rafael faz à mão no LumaFusion: a foto do
anúncio do produto nos primeiros segundos e, no vídeo inteiro, uma miniatura dela no canto
de cima à direita e as setinhas vermelhas em cascata embaixo à esquerda (a montagem fica no
videos.com_foto_e_miniatura, com o resto do tratamento de vídeo).

Vale para os vídeos de todas as fontes do robô (FONTES_COM_EDICAO): o Rafael confirmou que
todos os grupos e vídeos dele são autorais. Fica desligada até ele ver um exemplo no
privado e ligar no painel (Shopee Vídeo 🎬 → Robô Automático 🤖 → Edição dos Vídeos ✂️;
chave edicao_ligada de shopee_video). Escolhas do Rafael (25/10/2026, P37 e depois da
P38): DECISOES.md, Shopee Vídeo.

O Editor 2 (editar_2, "com legendas") é esta edição com os textos da tela (nome, vantagem e
uma chamada para o produto) no vídeo original, sem cortar nada nem mudar a velocidade. É o que
vai ao ar (editar_para_postar): o Rafael escolheu o Editor 2 nos rascunhos do robô e no modo
assistente, e o vídeo em que ele não sai vai com o Editor 1 (28/10/2026, P50 e P51). O
exemplo de cada editor (exemplo_editor_1 e exemplo_editor_2) entrega primeiro esse vídeo
original e depois até 2 versões modificadas, diferentes de verdade, cada uma abrindo com um
momento diferente e seguindo dali, cada uma de um tamanho; no Editor 2, remontadas (sem as
partes paradas, com trechos acelerados e uma câmera lenta curta), com outra vantagem na tela
e outra chamada no fim. As versões ficam só no exemplo: nada delas vai ao ar (pedidos de 27 e
28/10/2026: DECISOES.md, Shopee Vídeo).

Usado pelo robô automático (robo_shopee_video, na cópia do vídeo que vai ao rascunho), pelo
modo assistente (assistente_shopee_video, no vídeo que vai ao privado do Rafael) e pelo
painel da Shopee Vídeo (os exemplos).
"""
import functools
import math
import os

import assistente_shopee_video as assistente
import db
import postador_shopee_video as ps
import registro_processos
import videos

# Todas as fontes do robô, na ordem em que o exemplo procura um vídeo.
FONTES_COM_EDICAO = tuple(assistente.FONTES)
# A foto do produto sozinha antes do vídeo, em segundos.
SEGUNDOS_DA_FOTO = 2
# Nos rascunhos com produtos a mais, a miniatura troca entre as fotos diferentes dos produtos do
# post, uma volta só, com o vídeo dividido igual entre elas e pelo menos este tanto de segundos
# para cada: as que não cabem ficam de fora. Escolha do Rafael (30/10, P103): DECISOES.md, Shopee Vídeo.
MINIMO_POR_FOTO = 3
# A miniatura e a seta no vídeo de 720x1280, do começo do vídeo até o fim. A miniatura fica no
# alto à direita, fora do ícone da barra de busca do app e longe do canto da tela (pedido do
# Rafael, 01/11, P120: DECISOES.md, Shopee Vídeo): a ponta de cima à direita logo abaixo da barra
# de busca (FIM_DA_BARRA_DE_BUSCA) e um pouco para dentro da borda que o app mostra
# (VISIVEL_NO_APP), o que o tests/test_edicao_video.py confere. O tamanho é o de sempre, 25% da
# largura do vídeo (escolha do Rafael, 02/11, P121: DECISOES.md, Shopee Vídeo).
LARGURA_DA_MINIATURA = 180
# O canto de cima à direita da miniatura fica sempre no mesmo lugar: menor, ela encolhe para
# dentro dele. Escolha do Rafael (29/10, P97): DECISOES.md, Shopee Vídeo.
CANTO_DA_MINIATURA = (657, 150)
CENTRO_DA_MINIATURA = (CANTO_DA_MINIATURA[0] - LARGURA_DA_MINIATURA // 2,
                       CANTO_DA_MINIATURA[1] + LARGURA_DA_MINIATURA // 2)
# As setinhas em cascata (escolha do Rafael, 02/11, P130: no lugar da seta do arquivo dele, a do
# LumaFusion, que ele pediu em 25/10): três setinhas para baixo, uma embaixo da outra, no vermelho
# do destaque (VERMELHO_DO_DESTAQUE, P140 2), com um contorno branco e uma sombra leve (P127),
# acendendo de cima para baixo, uma volta por segundo, perto do canto de baixo à esquerda, logo
# acima do cartão do produto que o app mostra e apontando para ele (inteiras acima do cartão,
# P71). Elas começam logo depois da foto e vão até o fim do vídeo: o arquivo guarda uma volta, que
# se repete (PULSO_DA_SETA). O setas_em_cascata.apng sai do .claude/scripts/gerar_seta.py, com
# MARGEM_DA_SETA px transparentes de cada lado para o contorno e a sombra. DECISOES.md, Shopee Vídeo.
SETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "midia", "setas_em_cascata.apng")
MARGEM_DA_SETA = 10
CENTRO_DA_SETA = (142, 796)
# O que o app da Shopee mostra do vídeo de 720x1280 num celular de tela 20:9, medido no
# celular do Rafael (vídeo de 28/10, P71): ele enche a tela e corta uns 47 px de cada lado
# (fica visível de x 47 a 673), a barra de busca do alto vai até y 140 e o cartão do produto
# embaixo começa em y 870. A seta e os textos ficam dentro disso (o tests/test_edicao_video.py
# confere).
VISIVEL_NO_APP = (47, 673)
FIM_DA_BARRA_DE_BUSCA = 140
COMECO_DO_CARTAO_DO_PRODUTO = 870
# A moldura vermelha (VERMELHO_DO_DESTAQUE, P140 2) em volta do cartão do produto que o app mostra
# embaixo (o cartão é do app, por cima do vídeo; a moldura vai no vídeo, por baixo dele), no lugar
# em que o cartão aparece no celular do Rafael (medido no vídeo dele de 02/11, 12:36, com o nome em
# 2 linhas e uma linha de estrelas ou de desconto), de ESPERA_DA_MOLDURA segundos depois do fim da
# abertura até o fim do vídeo: o cartão do app aparece uns 0,5 s depois da abertura, e a moldura
# vazia ficava solta antes dele (vídeos do Rafael das 00:32 e 00:36 de 03/11, P140 2). Em teste: o cartão
# só aparece uns segundos depois do começo, pode ser fechado no X e muda de tamanho e de lugar com
# o celular e o nome do produto; o Rafael confere em outros celulares e decide se fica (02/11,
# P128: DECISOES.md, Shopee Vídeo). Para tirar, MOLDURA_DO_CARTAO = False.
MOLDURA_DO_CARTAO = True
ESPERA_DA_MOLDURA = 1.5                         # depois da abertura, com o cartão do app já na tela
# Com o Rótulo de IA ligado, o app põe embaixo a linha "Identificado como conteúdo gerado por IA",
# e o cartão do produto sobe a altura dela (medido no print do Rafael de 03/11, 07:08: o cartão 40
# px mais alto no vídeo de 720x1280). A moldura, as setinhas e a legenda da fala sobem junto, para
# ficarem no mesmo lugar em relação ao cartão. Pedido do Rafael (vídeo das 07:10 de 03/11):
# DECISOES.md, Shopee Vídeo.
SUBIDA_COM_O_ROTULO_DE_IA = 40
CARTAO_DO_PRODUTO = (68, 911, 550, 1096)        # x1, y1, x2, y2 no vídeo de 720x1280
FOLGA_DO_CARTAO = 8                             # entre o cartão e a moldura
GROSSURA_DA_MOLDURA_DO_CARTAO = 7               # a da moldura da miniatura
RAIO_DO_CARTAO = 17                             # o arredondado dos cantos do cartão
PULSO_DA_SETA = (0, 25)                         # a volta inteira da cascata, em laço
# As legendas da fala: o que as pessoas falam no vídeo, escrito pela IA vendo o vídeo e posto por
# nós na edição (não o Captions do app: assim o Rafael vê a legenda no rascunho antes de aprovar).
# O pé da legenda fica na altura do pé da seta, porque logo abaixo vem o cartão do produto que o app
# mostra; ela vai à direita da seta, sem cobri-la, até antes da coluna dos ícones do app à direita
# (o perfil, o coração e os comentários, que começam em COLUNA_DOS_ICONES, medido no celular do
# Rafael no vídeo de 02/11, 12:36: pedido dele, a legenda passava por cima dos ícones), em letra
# pequena, branca com contorno preto. O vídeo sem fala (só música ou canto) e o que já tem a fala
# escrita na tela vão sem ela. Escolha do Rafael (01/11, P118): DECISOES.md, Shopee Vídeo.
TAMANHO_DA_SETA = (202, 160)        # o arquivo da seta, com a margem (o tests/test_edicao_video.py confere)
# O pé e o lado da seta são os do pedaço com ela, sem a margem do contorno e da sombra.
PE_DA_LEGENDA = CENTRO_DA_SETA[1] + TAMANHO_DA_SETA[1] // 2 - MARGEM_DA_SETA
ESQUERDA_DA_LEGENDA = CENTRO_DA_SETA[0] + TAMANHO_DA_SETA[0] // 2 - MARGEM_DA_SETA + 12
COLUNA_DOS_ICONES = 586
DIREITA_DA_LEGENDA = COLUNA_DOS_ICONES - 12
LETRA_DA_LEGENDA = (26, 22)         # a maior e a menor
LINHAS_DA_LEGENDA = 2
CONTORNO_DA_LEGENDA = 3
# A IA escreve a fala inteira, palavra por palavra, um trecho por frase dita e sem limite de tamanho
# (com um limite, ela resume e pula frases); o trecho que não cabe em LINHAS_DA_LEGENDA linhas é
# dividido aqui, com o tempo repartido pelo tamanho de cada parte. Pedido do Rafael (02/11):
# DECISOES.md, Shopee Vídeo.
# Um trecho mais curto que isto passa rápido demais para ler e sai.
MINIMO_NA_TELA = 0.4
PROCESSO_DAS_LEGENDAS = "edição do vídeo: legendas da fala"
# Uns minutos bastam para um vídeo curto; depois disso a edição desiste (e o vídeo fica para depois).
ESPERA_MAXIMA = 300
# Quantos vídeos de cada fonte o exemplo tenta até achar um com a foto do anúncio na API:
# a fonte do robô pode ter só vídeos de Ver Produtos na frente, e as outras também contam.
VIDEOS_POR_FONTE = 6
# Os vídeos já mostrados no exemplo (os ids da fonte, em "ids"): cada toque mostra um vídeo
# novo; sem vídeo novo com foto, recomeça pelos já mostrados. Em "sem_foto", os que não têm a
# foto do anúncio (os de Ver Produtos e os sem oferta), para não gastar tempo com eles de
# novo. Pedido do Rafael (25/10): DECISOES.md, Shopee Vídeo.
CHAVE_EXEMPLOS = "edicao_exemplos_mostrados"
EXEMPLOS_LEMBRADOS = 100
SEM_FOTO_LEMBRADOS = 300


# A música de fundo do vídeo sem som: 3 músicas instrumentais feitas pelo Claude do zero, por
# síntese (.claude/scripts/gerar_musicas.py), sem pedaço de música de ninguém, porque a regra 7
# da Shopee pune música de terceiros sem licença. Cada vídeo mudo leva a próxima, em rodízio
# (a vez fica em MUSICA_DA_VEZ, na chave shopee_video), e no exemplo cada versão modificada
# leva outra. Escolha do Rafael (28/10, P55): DECISOES.md, Shopee Vídeo.
MUSICAS = (("animada", "musica_animada.m4a"), ("calma", "musica_calma.m4a"),
           ("divertida", "musica_divertida.m4a"))
PASTA_DA_MIDIA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "midia")
MUSICA_DA_VEZ = "musica_de_fundo_da_vez"


def ligada():
    return bool((db.ler_config("shopee_video", {}) or {}).get("edicao_ligada"))


def musicas_de_fundo(video, quantas=1):
    """
    A música (nome, caminho) de cada um dos `quantas` vídeos que saem deste (o original e as
    versões), a partir da da vez, que anda uma casa; [None] * quantas quando o vídeo tem som.
    """
    if not videos.mudo(video):
        return [None] * quantas

    def andar(dados):
        vez = int(dados.get(MUSICA_DA_VEZ) or 0) % len(MUSICAS)
        dados[MUSICA_DA_VEZ] = (vez + 1) % len(MUSICAS)
        return vez

    vez = db.atualizar_config("shopee_video", andar) or 0
    escolhidas = [MUSICAS[(vez + n) % len(MUSICAS)] for n in range(quantas)]
    return [(nome, os.path.join(PASTA_DA_MIDIA, arquivo)) for nome, arquivo in escolhidas]


def _caminho(musica):
    return musica[1] if musica else None


def vale_para(fonte):
    """A edição entra no vídeo desta fonte agora? Ligada, em qualquer fonte do robô."""
    return fonte in FONTES_COM_EDICAO and ligada()


# A capa da bebida alcoólica: a tela de 720x1280 que abre o vídeo (o app usa o primeiro
# quadro como capa) com a foto do anúncio em cima e, logo embaixo, os três avisos da Shopee
# em letras brancas, no fundo preto da foto do começo (onde o número de visualizações da
# grade se lê, P72). Fica no meio da tela, longe das bordas que a grade da Shopee corta na
# miniatura. Escolhas do Rafael (26/10, P43; 29/10, P72): DECISOES.md, Shopee Vídeo.
TELA = (720, 1280)
AREA_DA_FOTO = (60, 740)        # de cima a baixo, em y
AREA_DOS_AVISOS = (790, 1090)
MARGEM_DOS_AVISOS = 40
MAIOR_LETRA = 44


def capa_com_avisos(foto):
    """A capa da bebida alcoólica (PNG, bytes) com a foto do anúncio (bytes); None se a foto não abre."""
    import io

    import matplotlib
    from PIL import Image, ImageDraw, ImageFont
    try:
        imagem = Image.open(io.BytesIO(foto)).convert("RGB")
    except Exception:
        return None
    largura, altura = TELA
    capa = Image.new("RGB", TELA, "black")
    topo, base = AREA_DA_FOTO
    escala = min(largura / imagem.width, (base - topo) / imagem.height)
    imagem = imagem.resize((max(1, round(imagem.width * escala)), max(1, round(imagem.height * escala))))
    capa.paste(imagem, ((largura - imagem.width) // 2, topo + (base - topo - imagem.height) // 2))

    desenho = ImageDraw.Draw(capa)
    fonte_ttf = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")
    cima, baixo = AREA_DOS_AVISOS
    # A maior letra em que o aviso mais comprido cabe na largura, com a margem.
    for tamanho in range(MAIOR_LETRA, 12, -2):
        fonte = ImageFont.truetype(fonte_ttf, tamanho)
        if max(desenho.textlength(aviso, font=fonte) for aviso in assistente.AVISOS_DE_ALCOOL) \
                <= largura - 2 * MARGEM_DOS_AVISOS:
            break
    passo = (baixo - cima) / len(assistente.AVISOS_DE_ALCOOL)
    for i, aviso in enumerate(assistente.AVISOS_DE_ALCOOL):
        desenho.text((largura / 2, cima + passo * (i + 0.5)), aviso, font=fonte, fill="white", anchor="mm")
    saida = io.BytesIO()
    capa.save(saida, format="PNG")
    return saida.getvalue()


# A capa com chamada: a foto do anúncio do mesmo tamanho da capa sem texto (a foto quadrada
# ocupa a largura toda, no meio da tela, como no FILTRO_720P do começo do vídeo) e, por cima do
# pé da foto, uma faixa com a frase da capa (no laranja da Shopee com letras brancas, ou na cor do
# produto, P159 2; a frase curta que a IA escreve para ela, P106; sem marca, sem preço e sem
# promoção, regras 9, 13 e 14).
# Tudo dentro do que a grade do perfil mostra da capa (o corte do meio, medido no print do
# Rafael de 29/10: de y 196 a 1116 da tela de 720x1280; na largura, a grade mostra o quadro em
# 3:4, os 690 px do meio, de x 15 a 705, e o que fica na borda da tela some: vídeo do Rafael de
# 02/11, 12:36) e longe do que a grade põe por cima: o número de visualizações, embaixo à
# esquerda (NUMERO_DA_GRADE), fica logo abaixo da faixa, no preto, e a sacolinha da Shopee, em
# cima à direita (SACOLINHA_DA_GRADE), logo acima da foto; o selo "Fixado" dos vídeos fixados no
# perfil, em cima à esquerda (FIXADO_DA_GRADE, medido no Motorola em 29/10), pega só a ponta de
# cima da foto: pedido do Rafael, não atrapalhar os números. Começa desligada (chave capa_com_chamada de
# shopee_video): ele vê o exemplo no privado e liga no painel. A bebida alcoólica fica com a
# capa dos avisos. Escolhas do Rafael (29/10, P76; 30/10, P107): DECISOES.md, Shopee Vídeo.
CHAVE_DA_CAPA = "capa_com_chamada"
VISIVEL_NA_GRADE = (196, 1116)                  # de cima a baixo, em y
LARGURA_NA_GRADE = (VISIVEL_NA_GRADE[1] - VISIVEL_NA_GRADE[0]) * 3 // 4
LADOS_NA_GRADE = ((TELA[0] - LARGURA_NA_GRADE) // 2, (TELA[0] + LARGURA_NA_GRADE) // 2)   # em x
NUMERO_DA_GRADE = (52, 1005, 228, 1055)         # x1, y1, x2, y2
SACOLINHA_DA_GRADE = (587, 210, 667, 278)
FIXADO_DA_GRADE = (36, 200, 252, 305)
FOTO_DA_CAPA = (0, 280, 720, 1000)              # entre a sacolinha e o número: a foto quadrada, 720x720
LARANJA_DA_SHOPEE = (238, 77, 45)
# O vermelho do destaque: a caixa da última mensagem (a chamada para o produto), as setinhas e a
# moldura do cartão do produto, para chamar mais a atenção que o laranja, que se mistura nos vídeos
# de tons quentes. A miniatura e a capa ficam na cor do produto (CORES_DO_PRODUTO), ou no laranja da
# Shopee. Escolha do Rafael (03/11, P140 2): DECISOES.md, Shopee Vídeo.
VERMELHO_DO_DESTAQUE = (214, 24, 38)
# A cor de cada vídeo: a cor principal do produto, que a IA diz junto com os textos da tela, no
# lugar do laranja do fio e da faixa da capa e da moldura da miniatura, e do preto da caixa do nome
# e da vantagem, com a letra branca ou preta, a de mais contraste (CONTRASTE_DA_LETRA_BRANCA: com o
# laranja da Shopee, a branca de sempre). As setinhas, a moldura do cartão e a chamada final
# continuam no vermelho do destaque. O produto vermelho (para a chamada final continuar se
# destacando) ou de várias cores, e o vídeo sem a cor da IA, ficam com as cores de sempre. Cada
# nome tem um tom fixo, para o vídeo não sair com um tom estranho; o preto é um grafite, para a
# faixa aparecer no fundo preto da capa. Escolha do Rafael (06/11, P159 2): DECISOES.md, Shopee Vídeo.
CORES_DO_PRODUTO = {
    "preto": (45, 45, 45), "branco": (245, 245, 245), "cinza": (120, 120, 120), "prata": (180, 184, 190),
    "azul": (30, 90, 210), "azul-claro": (80, 170, 235), "azul-marinho": (25, 45, 105), "verde": (35, 150, 75),
    "verde-claro": (130, 205, 95), "amarelo": (250, 205, 35), "dourado": (205, 165, 65),
    "laranja": LARANJA_DA_SHOPEE, "rosa": (230, 90, 150), "roxo": (125, 65, 175), "lilás": (185, 145, 225),
    "marrom": (115, 75, 45), "bege": (220, 195, 155),
}
CORES_DE_SEMPRE = ("vermelho", "colorido")
CONTRASTE_DA_LETRA_BRANCA = 3.0
LETRA_BRANCA, LETRA_PRETA = (255, 255, 255), (0, 0, 0)
ALFA_DA_CAIXA_DA_COR = 230
PROCESSO_DA_COR = "edição do vídeo: cor do produto"
COM_AS_CORES_DE_SEMPRE = "as cores de sempre"


def cor_do_produto(nome):
    """
    O tom (RGB) da cor do produto pelo nome que a IA deu; None com as cores de sempre (vermelho,
    colorido, sem a cor).
    """
    return CORES_DO_PRODUTO.get(" ".join(str(nome or "").lower().split()))


def letra_que_contrasta(cor):
    """
    A letra (RGB) em cima da cor: a branca quando o contraste dela com a cor chega a
    CONTRASTE_DA_LETRA_BRANCA (a conta da luminância do W3C), senão a preta.
    """
    def linear(canal):
        canal /= 255
        return canal / 12.92 if canal <= 0.03928 else ((canal + 0.055) / 1.055) ** 2.4
    luminancia = sum(peso * linear(canal) for peso, canal in zip((0.2126, 0.7152, 0.0722), cor[:3]))
    return LETRA_BRANCA if 1.05 / (luminancia + 0.05) >= CONTRASTE_DA_LETRA_BRANCA else LETRA_PRETA


def caixa_dos_textos(cor=None):
    """O fundo (RGBA) da caixa do nome e da vantagem: na cor do produto, ou o preto de sempre (FUNDO_DOS_TEXTOS)."""
    return tuple(cor[:3]) + (ALFA_DA_CAIXA_DA_COR,) if cor else FUNDO_DOS_TEXTOS


FAIXA_DA_CHAMADA = 104                          # a altura da faixa com uma linha
FOLGA_DA_FAIXA = 9                              # entre as letras e a borda da faixa, com duas linhas
# O app, com o vídeo aberto, corta os lados do quadro (VISIVEL_NO_APP): a frase fica dentro
# do que ele mostra, com esta folga de cada lado, para as pontas não sumirem. Pedido do Rafael
# (vídeo de 31/10, 08:38): DECISOES.md, Shopee Vídeo.
MARGEM_DA_FAIXA = 12
LETRAS_DA_CHAMADA = (72, 40)                    # a maior e a menor numa linha
# Quando não cabe numa linha: duas, na mesma faixa (a maior cabe com a folga em FAIXA_DA_CHAMADA).
LETRAS_EM_DUAS_LINHAS = (36, 28)
# A moldura da miniatura, de cantos arredondados, no laranja ou na cor do produto (pedidos do
# Rafael, P115, P117, P119 e P159 2: DECISOES.md, Shopee Vídeo). As camadas vão de fora para dentro,
# (cor, grossura em px na foto do tamanho da capa); na miniatura, cada uma tem a metade da grossura
# (ESCALA_NA_MINIATURA), dentro do lugar dela. A foto do começo do vídeo, sem a frase, vai sem
# moldura (P119).
CAMADAS_DA_MOLDURA = ((LARANJA_DA_SHOPEE, 14),)
GROSSURA_DA_MOLDURA = sum(grossura for _cor, grossura in CAMADAS_DA_MOLDURA)
RAIO_DA_FOTO = 34                               # o arredondado dos cantos da foto da miniatura, dentro da moldura
ESCALA_NA_MINIATURA = 0.5
# A capa com a frase (vídeo do Rafael das 20:14 de 02/11, no lugar da moldura em volta da foto e
# das laterais laranja encostadas nos lados da grade): a foto inteira, sem moldura dos lados; um
# fio (FIO_DA_CAPA) logo acima da beirada de cima dela e, logo abaixo do pé dela, a faixa com a
# frase (os dois no laranja ou na cor do produto, P159 2), sempre da altura de uma linha
# (FAIXA_DA_CHAMADA), e a sacolinha da grade fica por cima do canto de cima da foto (P139 2). A
# frase que não cabe numa linha vai em duas, com a letra menor. Na capa da grade (o 1º quadro do vídeo), a faixa fica logo acima do número
# de visualizações (PE_DA_FAIXA_NA_GRADE) e a foto entra inteira, sem corte, no maior tamanho que
# cabe no que a grade mostra (LADOS_NA_GRADE e VISIVEL_NA_GRADE) acima da faixa; o fio e a faixa
# vão de uma beirada à outra (a tela final do app mostra o vídeo de lado a lado). No resto da
# abertura (o vídeo aberto, que corta mais dos lados, VISIVEL_NO_APP, P129), a faixa fica acima do
# cartão do produto que o app põe por cima do vídeo (CARTAO_NO_VIDEO_ABERTO) e a foto, inteira
# entre a barra de pesquisa do app (TOPO_NO_VIDEO_ABERTO) e a faixa; o fio e a faixa vão de um
# lado ao outro do que o app mostra. Pedidos do Rafael (P139 2 e P160 2): DECISOES.md, Shopee Vídeo.
FIO_DA_CAPA = 8
PE_DA_FAIXA_NA_GRADE = FOTO_DA_CAPA[3]           # logo acima do número de visualizações (NUMERO_DA_GRADE)
# Medidos no vídeo do Rafael de 06/11 (09:56, o Motorola com o vídeo aberto pelo Perfil): o
# cartão "Comprar com cupom" cobre o vídeo de y 920 a 1094, e a barra de pesquisa, até y 140.
CARTAO_NO_VIDEO_ABERTO = 920
PE_DA_FAIXA_NO_VIDEO = CARTAO_NO_VIDEO_ABERTO - MARGEM_DA_FAIXA
TOPO_NO_VIDEO_ABERTO = 140
# No vídeo aberto, a coluna de ícones do app (o perfil, o coração, os comentários) fica do lado
# direito, a partir deste x do quadro, e o coração cai na altura da faixa (medido no mesmo vídeo):
# a frase da capa do vídeo aberto acaba antes dela, um pouco à esquerda e com a letra um pouco
# menor; a faixa continua de um lado ao outro, e a capa da grade fica igual. Escolha do Rafael
# (06/11, P165 1): DECISOES.md, Shopee Vídeo.
ICONES_NO_VIDEO_ABERTO = 586
# As letras da frase ficam dentro do que o app mostra do vídeo aberto (no modo assistente, a capa
# vai no começo do vídeo), com a margem da faixa de cada lado.
LETRAS_DA_FAIXA = VISIVEL_NO_APP[1] - VISIVEL_NO_APP[0] - 2 * MARGEM_DA_FAIXA


def capa_ligada():
    return bool((db.ler_config("shopee_video", {}) or {}).get(CHAVE_DA_CAPA))


# A linha que termina numa palavra de ligação ("Acaba com a / bagunça") vale como uma letra
# PENALIDADE_DA_QUEBRA px menor: a quebra boa ganha, se a letra não ficar muito menor.
PENALIDADE_DA_QUEBRA = 8


def _quebra_da_chamada(texto, desenho, fonte_ttf, largura=LETRAS_DA_FAIXA):
    """
    (fonte, linhas) da chamada na faixa: numa linha só, na maior letra de LETRAS_DA_CHAMADA em
    que ela cabe na largura das letras (dentro da faixa e do que o app mostra, com a margem: a
    faixa fina do exemplo que o Rafael escolheu, P107); quando não cabe, em duas, na maior letra de
    LETRAS_EM_DUAS_LINHAS, equilibradas e, se der, sem a 1ª terminar numa palavra de ligação. None
    quando não cabe nem assim.
    """
    from PIL import ImageFont
    maior, menor = LETRAS_DA_CHAMADA
    for tamanho in range(maior, menor - 1, -2):
        fonte = ImageFont.truetype(fonte_ttf, tamanho)
        if desenho.textlength(texto, font=fonte) <= largura:
            return fonte, [texto]
    palavras = texto.split(" ")
    melhor = None
    maior, menor = LETRAS_EM_DUAS_LINHAS
    for tamanho in range(maior, menor - 1, -2):
        fonte = ImageFont.truetype(fonte_ttf, tamanho)
        for k in range(1, len(palavras)):
            linhas = [" ".join(palavras[:k]), " ".join(palavras[k:])]
            larguras = [desenho.textlength(linha, font=fonte) for linha in linhas]
            if max(larguras) > largura:
                continue
            ligacao = linhas[0].split(" ")[-1].lower().strip(",.-:") in PALAVRAS_DE_LIGACAO
            # As duas linhas de tamanho parecido.
            nota = (tamanho - (PENALIDADE_DA_QUEBRA if ligacao else 0), -max(larguras))
            if melhor is None or nota > melhor[0]:
                melhor = (nota, fonte, linhas)
    return (melhor[1], melhor[2]) if melhor else None


def com_moldura(imagem, escala=1.0, cor=None):
    """
    A imagem do PIL com a moldura em volta (CAMADAS_DA_MOLDURA, cada grossura vezes a escala; com a
    cor do produto, P159 2, nela): RGBA, maior que ela duas vezes a grossura, com os cantos da foto e
    da moldura arredondados e o transparente fora deles (a miniatura).
    """
    from PIL import Image, ImageDraw
    camadas = [(tuple(cor) if cor else da_camada, max(1, round(grossura * escala)))
               for da_camada, grossura in CAMADAS_DA_MOLDURA]
    total = sum(grossura for _cor, grossura in camadas)
    raio = max(2, round(RAIO_DA_FOTO * escala))
    largura, altura = imagem.size
    saida = Image.new("RGBA", (largura + 2 * total, altura + 2 * total), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(saida)
    fora = total
    for cor, grossura in camadas:
        desenho.rounded_rectangle((total - fora, total - fora, total + largura + fora - 1, total + altura + fora - 1),
                                  raio + fora, fill=cor)
        fora -= grossura
    mascara = Image.new("L", imagem.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, largura - 1, altura - 1), raio, fill=255)
    saida.paste(imagem.convert("RGB"), (total, total), mascara)
    return saida


def _foto_que_cabe(foto, lado, altura=None):
    """
    A foto (bytes) no PIL, em RGB, no maior tamanho que cabe num quadrado de lado px (ou num
    retângulo de lado x altura px), sem esticar; None se não abre.
    """
    import io

    from PIL import Image
    try:
        imagem = Image.open(io.BytesIO(foto or b"")).convert("RGB")
    except Exception:
        return None
    escala = min(lado / imagem.width, (altura or lado) / imagem.height)
    return imagem.resize((max(1, round(imagem.width * escala)), max(1, round(imagem.height * escala))))


def miniatura_com_moldura(foto, largura=LARGURA_DA_MINIATURA, cor=None):
    """
    A foto (bytes) da miniatura com a moldura (ESCALA_NA_MINIATURA da grossura da foto do
    começo; na cor do produto, quando vem, P159 2), num quadrado de largura px com o fundo
    transparente (PNG, bytes): a moldura fica dentro do lugar de sempre da miniatura. None com a
    foto que não abre.
    """
    from PIL import Image
    escala = ESCALA_NA_MINIATURA * largura / LARGURA_DA_MINIATURA
    total = sum(max(1, round(grossura * escala)) for _cor, grossura in CAMADAS_DA_MOLDURA)
    imagem = _foto_que_cabe(foto, max(1, largura - 2 * total))
    if not imagem:
        return None
    emoldurada = com_moldura(imagem, escala, cor)
    quadro = Image.new("RGBA", (largura, largura), (0, 0, 0, 0))
    quadro.paste(emoldurada, ((largura - emoldurada.width) // 2, (largura - emoldurada.height) // 2), emoldurada)
    return _png(quadro)


def _png(imagem):
    import io
    saida = io.BytesIO()
    imagem.save(saida, format="PNG")
    return saida.getvalue()


@functools.lru_cache(maxsize=2)
def moldura_do_cartao(rotulo_de_ia=False):
    """
    A moldura vermelha em volta do cartão do produto (PNG, bytes, 720x1280, transparente fora dela), ou
    None com ela desligada (MOLDURA_DO_CARTAO). Com rotulo_de_ia=True, SUBIDA_COM_O_ROTULO_DE_IA
    mais alta, como o cartão do app. Os cantos são arredondados como os do cartão, desenhados 4
    vezes maiores e reduzidos, para a borda não ficar serrilhada.
    """
    if not MOLDURA_DO_CARTAO:
        return None
    from PIL import Image, ImageDraw
    x1, y1, x2, y2 = CARTAO_DO_PRODUTO
    subida = SUBIDA_COM_O_ROTULO_DE_IA if rotulo_de_ia else 0
    y1, y2 = y1 - subida, y2 - subida
    fora = FOLGA_DO_CARTAO + GROSSURA_DA_MOLDURA_DO_CARTAO
    caixa = (x1 - fora, y1 - fora, x2 + fora, y2 + fora)
    vezes = 4
    largura, altura = (caixa[2] - caixa[0]) * vezes, (caixa[3] - caixa[1]) * vezes
    mascara = Image.new("L", (largura, altura), 0)
    desenho = ImageDraw.Draw(mascara)
    desenho.rounded_rectangle((0, 0, largura - 1, altura - 1), (RAIO_DO_CARTAO + fora) * vezes, fill=255)
    dentro = GROSSURA_DA_MOLDURA_DO_CARTAO * vezes
    desenho.rounded_rectangle((dentro, dentro, largura - 1 - dentro, altura - 1 - dentro),
                              (RAIO_DO_CARTAO + FOLGA_DO_CARTAO) * vezes, fill=0)
    anel = Image.new("RGBA", (caixa[2] - caixa[0], caixa[3] - caixa[1]), VERMELHO_DO_DESTAQUE + (255,))
    anel.putalpha(mascara.resize(anel.size, Image.LANCZOS))
    tela = Image.new("RGBA", TELA, (0, 0, 0, 0))
    tela.paste(anel, caixa[:2])
    return _png(tela)


def foto_em_tela_cheia(foto):
    """
    A abertura do vídeo sem capa (PNG, bytes, 720x1280): a foto do anúncio (bytes) no maior
    tamanho que cabe na tela, no meio, no fundo preto, sem moldura, como o FILTRO_720P do
    videos.py faz com a foto (escolha do Rafael, P119). Ela vai montada à parte porque o ffmpeg
    recebe a foto da miniatura já com a moldura (P115). None com a foto que não abre.
    """
    import io

    from PIL import Image
    try:
        imagem = Image.open(io.BytesIO(foto or b"")).convert("RGB")
    except Exception:
        return None
    largura, altura = TELA
    escala = min(largura / imagem.width, altura / imagem.height)
    imagem = imagem.resize((max(1, round(imagem.width * escala)), max(1, round(imagem.height * escala))))
    tela = Image.new("RGB", TELA, "black")
    tela.paste(imagem, ((largura - imagem.width) // 2, (altura - imagem.height) // 2))
    return _png(tela)


def lados_da_capa(no_video=False):
    """De onde a onde (em x) vão o fio e a faixa da capa com a frase: o vídeo todo na da grade, o que o app mostra no vídeo aberto."""
    return VISIVEL_NO_APP if no_video else (0, TELA[0])


def lugar_da_foto(no_video=False):
    """
    (esquerda, cima, direita, pé da faixa) da capa com a frase: entre esquerda e direita, e entre
    cima (com o fio) e a faixa, a foto entra inteira. Na da grade, o que a grade mostra, com a faixa
    logo acima do número de visualizações; no vídeo aberto (P129), o que o app mostra, com a faixa
    acima do cartão do produto (P160 2).
    """
    if no_video:
        return VISIVEL_NO_APP[0], TOPO_NO_VIDEO_ABERTO, VISIVEL_NO_APP[1], PE_DA_FAIXA_NO_VIDEO
    return LADOS_NA_GRADE[0], VISIVEL_NA_GRADE[0], LADOS_NA_GRADE[1], PE_DA_FAIXA_NA_GRADE


def capa_com_chamada(foto, chamada, no_video=False, cor=None):
    """
    A capa com chamada (PNG, bytes, 720x1280): a foto do anúncio (bytes) inteira, sem corte, no
    maior tamanho que cabe no lugar dela (lugar_da_foto), no fundo preto, com o fio logo acima da
    beirada de cima dela e, logo abaixo dela, a chamada numa faixa sempre da mesma altura, de um
    lado ao outro (lados_da_capa): na da grade, logo acima do número de visualizações; com
    no_video=True, a do resto da abertura (P129), acima do cartão do produto que o app põe por cima
    do vídeo aberto (P160 2), com a frase acabando antes dos ícones do app (P165 1). O fio e a faixa
    vão na cor do produto (P159 2; sem ela, o laranja da Shopee), com a letra que contrasta. Nada da
    foto fica coberto (P139 2). None sem a chamada, com
    a foto que não abre ou com a chamada que não cabe nem na menor letra.
    """
    import matplotlib
    from PIL import Image, ImageDraw
    chamada = " ".join((chamada or "").split())
    if not chamada:
        return None
    esquerda, direita = lados_da_capa(no_video)
    x1, cima, x2, pe = lugar_da_foto(no_video)
    imagem = _foto_que_cabe(foto, x2 - x1, pe - FAIXA_DA_CHAMADA - cima - FIO_DA_CAPA)
    if not imagem:
        return None
    capa = Image.new("RGB", TELA, "black")
    # A foto fica inteira logo acima da faixa, no meio do lugar dela.
    x, y = x1 + (x2 - x1 - imagem.width) // 2, pe - FAIXA_DA_CHAMADA - imagem.height
    capa.paste(imagem, (x, y))

    desenho = ImageDraw.Draw(capa)
    fonte_ttf = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")
    # No vídeo aberto, a frase acaba antes dos ícones do app (P165 1).
    fim_da_frase = min(direita, ICONES_NO_VIDEO_ABERTO) if no_video else direita
    quebra = _quebra_da_chamada(chamada, desenho, fonte_ttf,
                                min(fim_da_frase - esquerda - 2 * MARGEM_DA_FAIXA, LETRAS_DA_FAIXA))
    if not quebra:
        return None
    fonte, linhas = quebra
    cor = tuple(cor) if cor else LARANJA_DA_SHOPEE
    desenho.rectangle((esquerda, y - FIO_DA_CAPA, direita - 1, y - 1), fill=cor)
    desenho.rectangle((esquerda, pe - FAIXA_DA_CHAMADA, direita - 1, pe - 1), fill=cor)
    altura_da_linha = round(fonte.size * 1.2)
    meio = pe - FAIXA_DA_CHAMADA / 2
    for i, linha in enumerate(linhas):
        desenho.text(((esquerda + fim_da_frase) / 2, meio + altura_da_linha * (i - (len(linhas) - 1) / 2)), linha,
                     font=fonte, fill=letra_que_contrasta(cor), anchor="mm")
    return _png(capa)


# A faixa da capa com chamada num print (o quadro da grade do perfil): por ela o robô confere a capa
# do post (marcar_o_post). Aqui, laranja é a cor da faixa (a de sempre, ou a do produto, P159 2), e
# branco, a das letras (letra_que_contrasta). Laranja: até TOLERANCIA_DO_LARANJA da cor da faixa
# (a soma das diferenças das três cores). A faixa são linhas seguidas com o laranja nas mesmas pontas (a
# faixa é um retângulo), cheias (pelo menos LINHA_CHEIA entre as pontas) ou com as letras
# brancas (pelo menos LINHA_COM_LETRAS), de pelo menos LARGURA_MINIMA_DA_FAIXA da caixa.
# Nas linhas do meio das letras, o branco pode passar do laranja (letra grossa, o print em JPEG
# borrando a borda delas) e, com a faixa maior que a caixa, as letras chegam às pontas: entre as
# pontas da faixa, essas linhas são só laranja, branco e a mistura dos dois (a borda das letras),
# pelo menos LINHA_DA_FAIXA delas, com um pouco de laranja (LARANJA_COM_LETRAS: o branco da foto,
# sem laranja nenhum, não é faixa). Sem isso, a medida pegaria só o pedaço da faixa acima das
# letras.
TOLERANCIA_DO_LARANJA = 60
LINHA_CHEIA = 0.9
LINHA_COM_LETRAS = 0.4
LINHA_DA_FAIXA = 0.95
LARANJA_COM_LETRAS = 0.1
LARGURA_MINIMA_DA_FAIXA = 0.15
PONTAS_DA_FAIXA = 4                             # em px: quanto as pontas variam de uma linha para a outra
LINHAS_CHEIAS_DA_FAIXA = 2
# A borda de cima e a de baixo da moldura laranja (P115) também são linhas laranja cheias, mas
# finas: a faixa da chamada tem pelo menos esta fração da altura da caixa (no quadro da grade, ela
# fica em uns 11%; a borda da moldura, em uns 1%).
ALTURA_MINIMA_DA_FAIXA = 0.02
# Na mesma linha da faixa, o laranja de fora dela (a moldura laranja da miniatura, P115, um
# produto laranja na foto) fica separado dela por outras cores: as pontas da faixa saem só do
# pedaço da linha nas cores dela, com fendas de até FENDA_NA_FAIXA px (o borrado do JPEG em volta
# das letras).
FENDA_NA_FAIXA = 3
# As linhas do meio das letras entre dois pedaços da mesma faixa (_juntar_os_pedacos).
LINHA_ENTRE_PEDACOS = 0.75


def cores_da_faixa(pontos, cor=LARANJA_DA_SHOPEE):
    """
    Os pontos (numpy, altura x largura x 3) na cor da faixa (o laranja, ou a cor do produto, P159
    2), na cor das letras (letra_que_contrasta) ou na mistura das duas (a borda das letras), até
    TOLERANCIA_DO_LARANJA do caminho entre as duas cores.
    """
    import numpy
    laranja = numpy.array(cor, dtype=numpy.float32)
    rumo = numpy.array(letra_que_contrasta(cor), dtype=numpy.float32) - laranja
    pontos = pontos.astype(numpy.float32)
    passo = numpy.clip(((pontos - laranja) @ rumo) / float(rumo @ rumo), 0, 1)
    return numpy.abs(pontos - (laranja + passo[..., None] * rumo)).sum(axis=2) <= TOLERANCIA_DO_LARANJA


def _laranja_do_pedaco(laranja, cores):
    """
    As colunas laranja (numpy) do pedaço da linha que tem a faixa: a linha é cortada onde passa
    uma cor que não é da faixa (cores: o laranja, o branco das letras e a mistura dos dois), com
    fendas de até FENDA_NA_FAIXA px, e fica o pedaço de mais laranja.
    """
    import numpy
    colunas = numpy.flatnonzero(laranja)
    if not len(colunas):
        return colunas
    pontos = numpy.flatnonzero(cores | laranja)
    cortes = numpy.flatnonzero(numpy.diff(pontos) > FENDA_NA_FAIXA + 1)
    inicios = numpy.concatenate(([pontos[0]], pontos[cortes + 1]))
    fins = numpy.concatenate((pontos[cortes], [pontos[-1]]))
    soma = numpy.concatenate(([0], numpy.cumsum(laranja)))
    melhor = int(numpy.argmax(soma[fins + 1] - soma[inicios]))
    return colunas[(colunas >= inicios[melhor]) & (colunas <= fins[melhor])]


def _juntar_os_pedacos(blocos, laranja, da_faixa):
    """
    Os blocos (na ordem, de cima para baixo) com os pedaços da mesma faixa juntos: na faixa
    pequena do print em JPEG do celular, as linhas do meio das letras ficam com menos de
    LINHA_DA_FAIXA nas cores da faixa e cortam a faixa em dois, cada um mais baixo que
    ALTURA_MINIMA_DA_FAIXA. Dois pedaços com as mesmas pontas, separados só por linhas com
    pelo menos LINHA_ENTRE_PEDACOS nas cores da faixa e LARANJA_COM_LETRAS de laranja entre
    elas, são a mesma faixa.
    """
    juntos = []
    for bloco in blocos:
        antes = juntos[-1] if juntos else None
        if antes and abs(bloco["esquerda"] - antes["esquerda"]) <= PONTAS_DA_FAIXA and abs(
                bloco["direita"] - antes["direita"]) <= PONTAS_DA_FAIXA:
            trecho, meio = slice(antes["esquerda"], antes["direita"] + 1), slice(antes["baixo"], bloco["cima"])
            if ((da_faixa[meio, trecho].mean(axis=1) >= LINHA_ENTRE_PEDACOS).all()
                    and (laranja[meio, trecho].mean(axis=1) >= LARANJA_COM_LETRAS).all()):
                antes.update(baixo=bloco["baixo"], cheias=antes["cheias"] + bloco["cheias"])
                continue
        juntos.append(dict(bloco))
    return juntos


def faixa_laranja(imagem, caixa=None, cor=None):
    """
    A faixa laranja (ou na cor do produto, P159 2) dentro da caixa (x1, y1, x2, y2; sem ela, a
    imagem inteira) da imagem do PIL: (cima, baixo, esquerda, direita), em pontos da imagem, a de
    mais linhas entre as achadas (com pelo menos LINHAS_CHEIAS_DA_FAIXA linhas cheias). None sem ela.
    """
    import numpy
    cor = tuple(cor) if cor else LARANJA_DA_SHOPEE
    x1, y1, x2, y2 = caixa or (0, 0, imagem.width, imagem.height)
    pontos = numpy.asarray(imagem.convert("RGB").crop((x1, y1, x2, y2)), dtype=numpy.int16)
    laranja = numpy.abs(pontos - numpy.array(cor, dtype=numpy.int16)).sum(axis=2) <= TOLERANCIA_DO_LARANJA
    da_faixa = cores_da_faixa(pontos, cor)
    minimo = max(2, int(laranja.shape[1] * LARGURA_MINIMA_DA_FAIXA))
    blocos, atual = [], None
    for y, linha in enumerate(laranja):
        colunas = _laranja_do_pedaco(linha, da_faixa[y])
        faixa = None
        if len(colunas) and colunas[-1] - colunas[0] + 1 >= minimo:
            esquerda, direita = int(colunas[0]), int(colunas[-1])
            cheio = len(colunas) / (direita - esquerda + 1)
            if cheio >= LINHA_COM_LETRAS:
                faixa = (esquerda, direita, cheio >= LINHA_CHEIA)
        mesma = (atual is not None and faixa is not None and abs(faixa[0] - atual["esquerda"]) <= PONTAS_DA_FAIXA
                 and abs(faixa[1] - atual["direita"]) <= PONTAS_DA_FAIXA)
        if not mesma and atual is not None and not (faixa and faixa[2]):
            # A linha do meio das letras: entre as pontas da faixa, só as cores dela. (Uma linha
            # cheia com outras pontas é outra faixa.)
            trecho = slice(atual["esquerda"], atual["direita"] + 1)
            if da_faixa[y, trecho].mean() >= LINHA_DA_FAIXA and linha[trecho].mean() >= LARANJA_COM_LETRAS:
                atual["baixo"] = y + 1
                continue
        if mesma:
            atual["baixo"] = y + 1
            atual["cheias"] += faixa[2]
            if faixa[2]:
                atual["esquerda"], atual["direita"] = faixa[0], faixa[1]
            continue
        if atual is not None:
            blocos.append(atual)
        atual = ({"cima": y, "baixo": y + 1, "esquerda": faixa[0], "direita": faixa[1], "cheias": int(faixa[2])}
                 if faixa else None)
    if atual is not None:
        blocos.append(atual)
    blocos = _juntar_os_pedacos([b for b in blocos if b["cheias"] >= LINHAS_CHEIAS_DA_FAIXA], laranja, da_faixa)
    blocos = [b for b in blocos if b["baixo"] - b["cima"] >= ALTURA_MINIMA_DA_FAIXA * laranja.shape[0]]
    if not blocos:
        return None
    melhor = max(blocos, key=lambda b: b["baixo"] - b["cima"])
    return (y1 + melhor["cima"], y1 + melhor["baixo"], x1 + melhor["esquerda"], x1 + melhor["direita"] + 1)


def _capa_da_vez(foto, vantagem, no_video=False, cor=None):
    """A capa com chamada do vídeo que vai ao ar, ou None (a capa de sempre) quando ela não sai: o vídeo não para por ela."""
    try:
        return capa_com_chamada(foto, vantagem, no_video, cor)
    except Exception:
        return None


# A foto da capa sem letras: na foto da capa não pode ter letra nenhuma, de outra língua nem em
# português, para não se misturar com a frase da faixa. A IA diz se a foto do anúncio tem letras
# (fora as impressas no próprio produto ou na embalagem) e o maior pedaço dela com o produto
# inteiro e sem elas; com as letras fora do produto, a capa usa esse pedaço. Com as letras em cima
# do produto, a foto vai como está, até a resposta da P164. Pedido do Rafael (06/11, P160 2):
# DECISOES.md, Shopee Vídeo.
PROMPT_DAS_LETRAS_DA_FOTO = """Esta é a foto do anúncio de um produto. Veja se há letras escritas na foto: legendas, frases, preços, selos ou etiquetas com texto, marcas-d'água, em qualquer língua (português também). Não conte as letras impressas no próprio produto ou na embalagem dele (a marca, o rótulo).

Responda só com um JSON, sem mais nada:
{"letras": true ou false, "sobre_o_produto": true ou false, "caixa": [y1, x1, y2, x2]}

"sobre_o_produto": alguma dessas letras fica em cima do produto.
"caixa": o maior retângulo da foto com o produto inteiro e sem nenhuma dessas letras, em milésimos da altura (y) e da largura (x) da foto. Sem letras, a foto toda: [0, 0, 1000, 1000]."""
PROCESSO_DAS_LETRAS_DA_FOTO = "edição do vídeo: letras na foto da capa"
# O que aconteceu com as letras da foto (textos fixos: o registro e o checkup contam por eles).
SEM_LETRAS = "sem letras"
LETRAS_CORTADAS = "letras cortadas"
LETRAS_NO_PRODUTO = "letras em cima do produto"
SEM_RESPOSTA_DAS_LETRAS = "a IA não respondeu"
CAIXA_QUE_NAO_SERVE = "a caixa da IA não serve"
# O pedaço sem letras fica com pelo menos esta parte da foto (na área) e tira pelo menos a outra:
# menor, a IA errou a caixa (ou ela cortaria o produto); quase a foto toda, ela não tira as letras.
MENOR_PEDACO_SEM_LETRAS = 0.4
MAIOR_PEDACO_SEM_LETRAS = 0.98


def foto_sem_letras(foto):
    """
    (foto, resultado): a foto do anúncio (bytes) sem o pedaço com as letras (PNG) quando elas
    ficam fora do produto, ou a mesma foto (sem letras, com as letras em cima do produto, com a IA
    sem resposta ou com a caixa dela que não serve); resultado é um dos textos fixos acima.
    """
    import asyncio
    import io
    import json
    import re

    import api_gemini
    from PIL import Image
    try:
        imagem = Image.open(io.BytesIO(foto or b"")).convert("RGB")
    except Exception:
        return foto, SEM_RESPOSTA_DAS_LETRAS
    tipo = "image/png" if (foto or b"").startswith(b"\x89PNG") else "image/jpeg"
    try:
        resposta = asyncio.run(api_gemini.gerar_texto_gemini(PROMPT_DAS_LETRAS_DA_FOTO, imagens=[(foto, tipo)]))
    except Exception:
        resposta = None
    achado = re.search(r"\{.*\}", resposta or "", re.S)
    try:
        dados = json.loads(achado.group(0)) if achado else None
    except ValueError:
        dados = None
    if not isinstance(dados, dict):
        return foto, SEM_RESPOSTA_DAS_LETRAS
    if not dados.get("letras"):
        return foto, SEM_LETRAS
    if dados.get("sobre_o_produto"):
        return foto, LETRAS_NO_PRODUTO
    try:
        y1, x1, y2, x2 = (max(0, min(1000, int(valor))) for valor in dados.get("caixa"))
    except (TypeError, ValueError):
        return foto, CAIXA_QUE_NAO_SERVE
    parte = max(0, y2 - y1) * max(0, x2 - x1) / 1_000_000
    if not MENOR_PEDACO_SEM_LETRAS <= parte <= MAIOR_PEDACO_SEM_LETRAS:
        return foto, CAIXA_QUE_NAO_SERVE
    largura, altura = imagem.size
    corte = imagem.crop((x1 * largura // 1000, y1 * altura // 1000, x2 * largura // 1000, y2 * altura // 1000))
    return _png(corte), LETRAS_CORTADAS


def recorte_do_video_aberto(capa):
    """O pedaço da capa (PNG, bytes) que o app mostra com o vídeo aberto (VISIVEL_NO_APP, na altura toda), em PNG: o exemplo do painel."""
    return _faixa_da_capa(capa, (0, TELA[1]), VISIVEL_NO_APP)


# Na grade do perfil, a capa do post é o 1º quadro do vídeo quando a faixa da frase chega aos dois
# lados do quadro (a capa da grade vai de uma beirada à outra); com a faixa só no meio e os lados
# sem a cor dela, a grade pegou outro quadro da abertura (o do vídeo aberto, P129). Olha uma
# tira fina de cada lado, perto da borda do quadro, e a do meio, de cima a baixo.
TIRA_DOS_LADOS = 0.008                          # da largura do quadro, a partir de cada borda
PARTE_DOS_LADOS = 0.8                           # da altura da faixa, na cor dela, para dizer que ela está ali


def faixa_nos_lados(imagem, caixa, cor=None):
    """
    No print da grade (PIL), com o quadro da capa do post em caixa (x1, y1, x2, y2): True quando a
    faixa da frase (laranja, ou na cor do produto, P159 2) chega aos dois lados do quadro (o 1º
    quadro do vídeo), False quando ela está no meio e não chega a nenhum dos lados (outro quadro
    da abertura) e None quando não dá para dizer (sem a faixa, ou num lado só).
    """
    cor = tuple(cor) if cor else LARANJA_DA_SHOPEE
    x1, y1, x2, y2 = caixa
    largura, altura = x2 - x1, y2 - y1
    if largura < 50 or altura < 50:
        return None
    imagem = imagem.convert("RGB")
    # A faixa, na escala do quadro: a parte dela que tem de aparecer em laranja numa coluna.
    minimo = PARTE_DOS_LADOS * FAIXA_DA_CHAMADA * altura / (VISIVEL_NA_GRADE[1] - VISIVEL_NA_GRADE[0])

    def laranjas(x):
        return sum(1 for y in range(y1, y2)
                   if sum(abs(a - b) for a, b in zip(imagem.getpixel((x, y)), cor)) <= TOLERANCIA_DO_LARANJA)

    lados = [laranjas(x) for x in (x1 + round(largura * TIRA_DOS_LADOS), x2 - 1 - round(largura * TIRA_DOS_LADOS))]
    if all(n >= minimo for n in lados):
        return True
    if not any(lados) and laranjas((x1 + x2) // 2) >= minimo:
        return False
    return None


def recorte_da_grade(capa):
    """O pedaço da capa (PNG, bytes) que a grade do perfil mostra (VISIVEL_NA_GRADE e LADOS_NA_GRADE), em PNG: o exemplo do painel."""
    return _faixa_da_capa(capa, VISIVEL_NA_GRADE, LADOS_NA_GRADE)


def _faixa_da_capa(capa, faixa, lados=None):
    """A faixa da capa (PNG, bytes) de y cima a baixo, entre os lados (em x; sem eles, na largura toda), em PNG."""
    import io

    from PIL import Image
    with Image.open(io.BytesIO(capa)) as imagem:
        cima, baixo = faixa
        esquerda, direita = lados or (0, imagem.width)
        saida = io.BytesIO()
        imagem.crop((esquerda, cima, direita, baixo)).save(saida, format="PNG")
    return saida.getvalue()


def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outras_fotos=(),
           rotulo_de_ia=False, cor=None):
    """
    O vídeo editado com a foto (bytes) em destino: "" quando deu certo, ou o motivo fixo.
    Com avisos=True (bebida alcoólica), a capa com os avisos abre o vídeo no lugar da foto;
    sem eles, a capa (bytes de uma imagem, como a capa com chamada; ou o par (a do 1º quadro,
    a do resto da abertura), P129), quando vem. Com a musica
    (caminho), ela é o som do vídeo inteiro (o vídeo sem som, P55). Com miniatura=False (ou 0),
    o vídeo vai sem a nossa miniatura (o canto dela tem coisa do criador, P81); com uma largura
    menor (miniatura_no_video), ela vai desse tamanho, no mesmo canto (P97). Com as outras_fotos
    (bytes de outras fotos do mesmo produto, na ordem, as que cabem: fotos_que_cabem), a
    miniatura troca entre a foto e cada uma delas, uma volta só, o mesmo tempo para cada (P103).
    Com rotulo_de_ia=True (o vídeo vai com o Rótulo de IA ligado), as setinhas e a moldura do
    cartão sobem SUBIDA_COM_O_ROTULO_DE_IA, como o cartão do app. Com a cor do produto (RGB, P159
    2), a moldura da miniatura vai nela.
    """
    if avisos and foto:
        capa = capa_com_avisos(foto)
        if not capa:
            return "a capa com os avisos da bebida alcoólica não saiu"
    # A miniatura vai com a moldura (P115); a foto do começo, sem a capa, vai em tela cheia no
    # fundo preto, sem a moldura (P119). A foto que não abre segue como veio, e o ffmpeg diz o
    # motivo.
    if not capa:
        capa = foto_em_tela_cheia(foto)
    largura = largura_da_miniatura(miniatura)
    if largura:
        foto = miniatura_com_moldura(foto, largura, cor) or foto
        outras_fotos = [miniatura_com_moldura(outra, largura, cor) or outra for outra in outras_fotos]
    subida = SUBIDA_COM_O_ROTULO_DE_IA if rotulo_de_ia else 0
    return videos.com_foto_e_miniatura(video, foto, destino, SEGUNDOS_DA_FOTO, largura, centro_da_miniatura(largura),
                                       SETA, (CENTRO_DA_SETA[0], CENTRO_DA_SETA[1] - subida), ESPERA_MAXIMA,
                                       PULSO_DA_SETA, capa, musica, outras=outras_fotos,
                                       moldura=moldura_do_cartao(rotulo_de_ia), espera_da_moldura=ESPERA_DA_MOLDURA)


def largura_da_miniatura(miniatura):
    """A largura da miniatura pedida, em px: True é a de sempre; False ou 0, sem ela; um número, essa (P97)."""
    if miniatura is True:
        return LARGURA_DA_MINIATURA
    return int(miniatura or 0)


def centro_da_miniatura(largura):
    """O centro da miniatura desta largura, com o canto de cima à direita no lugar de sempre (P97)."""
    return CANTO_DA_MINIATURA[0] - largura // 2, CANTO_DA_MINIATURA[1] + largura // 2


def fotos_que_cabem(duracao, quantas):
    """
    Quantas das fotos da miniatura que troca (contando a do 1º produto) cabem num vídeo de duracao
    segundos com pelo menos MINIMO_POR_FOTO segundos cada, uma volta só: as primeiras, as que
    pagam mais por venda. 1 é a miniatura de uma foto só (P103).
    """
    return max(1, min(quantas, int(duracao // MINIMO_POR_FOTO)))


# --- Editor 2 ---
# O Editor 1 (sem legendas) é a edição de cima. O Editor 2 (com legendas) é o Editor 1 com os
# textos da tela (nome, vantagem e uma chamada para o produto) por cima do vídeo original, sem
# cortar nada nem mudar a velocidade, e é o que vai ao ar (editar_para_postar; escolhas do
# Rafael de 28/10/2026: DECISOES.md, Shopee Vídeo). A remontagem daqui (as partes paradas saem, os trechos calmos
# ficam mais rápidos, o de mais ação ganha uma câmera lenta curta) vale só nas versões
# modificadas do exemplo (editar_2_e_versoes).

# O vídeo é olhado em janelas de meio segundo.
JANELA = 0.5
QUADROS_DO_MOVIMENTO = 10           # por segundo, na medição
# Diferença média entre quadros (0 a 255) abaixo disto é imagem parada; abaixo da fração
# do movimento típico do vídeo também (um vídeo agitado tem o "parado" mais alto).
PARADO = 0.8
PARADO_DO_TIPICO = 0.15
# Abaixo desta fração do típico, o trecho é calmo: vai acelerado.
CALMO_DO_TIPICO = 0.6
ACELERADO = 1.5
# O segundo de mais ação vai em câmera lenta (só em vídeo de 6 s ou mais).
CAMERA_LENTA = 0.75
SEGUNDOS_EM_CAMERA_LENTA = 1.0
VIDEO_COM_CAMERA_LENTA = 6
# Parado por 1 s ou mais sai; parado mais curto só acelera.
PARADO_QUE_SAI = 1.0
# Um trecho acelerado ou normal dura pelo menos isto: mais curto, segue a velocidade do
# vizinho (trocar a cada meio segundo deixa o vídeo soluçando).
TRECHO_MINIMO = 1.5
# O vídeo remontado não fica com menos que isto, nem com menos da metade do original:
# perto disso, ele corta e acelera menos.
MINIMO_DO_REMONTADO = 8

# Os textos da tela: um de cada vez, longe da seta e dos botões do app, em letra que se lê
# bem (a regra 13 da Shopee pune texto pequeno ou sobreposto), mas sem tampar o produto: a
# caixa ocupa uns 7% da tela, e em cada vídeo a IA escolhe o lugar em que ela não cobre o
# produto nem o rosto de alguém (escolha do Rafael, P46: a letra grande, logo abaixo da
# miniatura, cobria o alto do móvel e o decote do vestido). Todos longe das bordas que o app
# corta (VISIVEL_NO_APP) e abaixo da barra de busca, com a letra um pouco menor (escolha do
# Rafael, P71: a caixa do alto encostava na borda e ficava embaixo da busca). Os lugares, em
# (x, topo, largura máxima das linhas, quantas linhas; a caixa tem mais 56 px de margem) no
# vídeo de 720x1280; x None = centralizado, x negativo = encostado na direita, a -x px da borda:
# - "alto": no topo, à esquerda, ao lado da miniatura (que vai de x 477 a 657);
# - "meio": logo abaixo da miniatura (que vai até y 330), centralizado;
# - "esquerda" e "direita": nos lados, numa caixa estreita de até 3 linhas, no meio da
#   altura: acima da seta (que começa em y 726) e da coluna de botões do app à direita.
# Nenhum lugar livre do rosto e do produto (SEM_LUGAR), o vídeo vai sem os textos (escolha
# do Rafael, P47: no vídeo do conjunto, o alto cobriu o rosto da modelo e o meio cobriria o
# conjunto).
LUGARES_DOS_TEXTOS = {"alto": (68, 150, 340, 2), "meio": (None, 340, 480, 2),
                      "esquerda": (64, 400, 170, 3), "direita": (-64, 400, 170, 3)}
LUGAR_PADRAO = "alto"
SEM_LUGAR = "nenhum"
TOPO_DOS_TEXTOS = LUGARES_DOS_TEXTOS["meio"][1]
LARGURA_DOS_TEXTOS = LUGARES_DOS_TEXTOS["meio"][2]
LETRA_DOS_TEXTOS = (36, 28)         # a maior e a menor
SEGUNDOS_DE_CADA_TEXTO = 3.0
FUNDO_DOS_TEXTOS = (20, 20, 20, 200)
FUNDO_DA_CHAMADA = VERMELHO_DO_DESTAQUE + (230,)
# A chamada vai em CAIXA ALTA (P140 2), mais larga que em minúsculas: a letra dela pode descer até
# esta, para caber nas mesmas linhas (a maiúscula desta letra tem a altura da minúscula da menor
# dos outros textos).
LETRA_MENOR_DA_CHAMADA = 24
MAXIMO_DO_NOME = 28
MAXIMO_DA_VANTAGEM = 36
MAXIMO_DA_CHAMADA = 32
# A frase da capa com chamada: o que é o produto e a vantagem em poucas palavras, que cabe em
# letra grande numa linha da capa (a frase longa encolhia a letra até ficar difícil de ler na
# grade do perfil, P106; só a vantagem não dizia o que é o produto, P122). Sem ela, vai o nome
# do produto (P131). Escolhas do Rafael (30/10 e 02/11): DECISOES.md, Shopee Vídeo.
MAXIMO_DA_CAPA = 20
PROCESSO_DA_FRASE_DA_CAPA = "edição do vídeo: frase da capa"
# A frase segue a P122 com de 2 a 4 palavras, até MAXIMO_DA_CAPA caracteres (com os espaços,
# como a IA conta) e começando pelo que é o produto: a 1ª palavra dela, sem artigo nem número na
# frente, tem o mesmo começo de uma das palavras do nome genérico que a IA deu ("Travessas" e
# "Travessa", "Sapatinho" e "Sapato"); sem o nome, não há com o que conferir. A que não segue
# volta à IA uma vez, só a frase, com o que estava errado; ainda errada, vai o nome do produto (P131).
# No print da grade de 02/11 (16:06), a capa "Remove bolinhas de tecido" era a vantagem: a
# frase da IA passou do tamanho. Pedido do Rafael: DECISOES.md, Shopee Vídeo.
PALAVRAS_DA_CAPA = (2, 4)
COMECO_IGUAL = 3                    # letras do começo, pelo menos, iguais às de uma palavra do nome
SEM_FRASE = "sem frase"
LONGA_DEMAIS = f"mais de {MAXIMO_DA_CAPA} letras"
FORA_DAS_PALAVRAS = f"fora de {PALAVRAS_DA_CAPA[0]} a {PALAVRAS_DA_CAPA[1]} palavras"
SEM_O_PRODUTO = "sem dizer o que é o produto"
LETRA_FORA = "letra fora do português"
PROMPT_DA_FRASE_DA_CAPA = (
    "Escreva a frase da capa de um vídeo de produto da Shopee: uma frase curta que começa pelo que é o "
    "produto e traz a vantagem que o vídeo mostra, para quem vê só a capa saber o que é e querer ver, de "
    "{minimo} a {maximo_de_palavras} palavras e até {maximo} caracteres contando os espaços (ex.: \"Calça que "
    "modela\", \"Travessas 3 tamanhos\", \"Copo sempre gelado\").\n"
    "O produto: {nome}\nA vantagem que o vídeo mostra: {vantagem}\n"
    "A frase de antes não serviu: {porque}.\n"
    "Nada de nome, logo ou slogan de marca; sem preço, desconto, promoção, emoji ou hashtag. Escreva com a "
    "ortografia e a acentuação certas do português do Brasil. Responda só com a frase, sem aspas.")

# A IA escreve o nome, a vantagem e a chamada vendo o vídeo, com as regras da Shopee Vídeo
# que mais pegam texto na tela (regras 7, 13 e 14 das diretrizes): sem marca, sem prometer o
# que o vídeo não mostra, sem preço ou promoção. O preço e o desconto ficam só no cartão do
# produto, que o app mostra sempre atualizado (com o desconto do Pix): no vídeo eles ficariam
# parados no dia do post e podiam não bater com o cartão. No lugar deles, a chamada para o
# produto anexado embaixo, onde a seta aponta. Escolha do Rafael (29/10, P80): DECISOES.md,
# Shopee Vídeo.
_NOME_NO_PROMPT = ("- \"nome\": o nome genérico do produto, como o comprador procura (ex.: \"Copo Térmico\"), "
                   f"até {MAXIMO_DO_NOME} caracteres;\n")
_CAPA_NO_PROMPT = ("- \"capa\": para a capa do vídeo, uma frase curta que começa pelo que é o produto e traz a "
                   "vantagem que o vídeo mostra, para quem vê só a capa saber o que é e querer ver, de 2 a 4 "
                   f"palavras e até {MAXIMO_DA_CAPA} caracteres (ex.: \"Calça que modela\", \"Travessas 3 "
                   "tamanhos\", \"Copo sempre gelado\");\n")
_CHAMADA_NO_PROMPT = ("- \"chamada\": uma frase curta para o fim do vídeo, com palavras suas, chamando para o "
                      f"produto anexado aqui embaixo, até {MAXIMO_DA_CHAMADA} caracteres, sem mandar para fora da "
                      "Shopee;\n")
# A cor principal do produto (P159 2), de uma lista fixa: cada nome tem um tom no CORES_DO_PRODUTO.
_COR_NO_PROMPT = ("Diga também \"cor\", a cor principal do produto que o vídeo mostra, uma destas: "
                  + ", ".join(list(CORES_DO_PRODUTO) + list(CORES_DE_SEMPRE[:1]))
                  + "; ou \"colorido\", quando ele tem várias cores e nenhuma é a principal.\n")
_REGRAS_NO_PROMPT = ("Regras da Shopee Vídeo: nada de nome, logo ou slogan de marca; nada que o vídeo não mostre; "
                     "sem preço, desconto, promoção, emoji ou hashtag. Escreva com a ortografia e a acentuação "
                     "certas do português do Brasil e confira cada palavra antes de responder.\n")
_FALAS_NO_PROMPT = (
    "Diga também onde alguém fala no vídeo (voz de gente, não música): \"falas\", a lista dos trechos em "
    "segundos desde o começo do vídeo, como [[início, fim], ...]; [] se ninguém fala.\n"
)
# O que o criador pôs por cima do vídeo é só o que ele acrescentou na edição, nunca o que foi
# filmado: no rascunho dos fones de 02/11, a IA contou como coisa do criador no canto da nossa
# miniatura o nome escrito na capa de uma revista em cima da mesa, e a miniatura saiu (P81).
_O_QUE_FOI_FILMADO_NAO_CONTA = (
    "Nas perguntas abaixo sobre o que o próprio vídeo pôs por cima da imagem, só conta o que foi acrescentado "
    "por cima na edição do vídeo (legenda, título, frase, figurinha, foto ou quadro); as coisas filmadas, que "
    "fazem parte da cena, como o produto, a embalagem, uma caixa, um livro, uma revista ou a tela de um celular, "
    "e o que está escrito nelas, nunca contam.\n"
)
# O lugar não cobre as fotos, quadros e textos que o criador pôs por cima do vídeo em nenhum
# momento, mesmo os que ficam pouco na tela: eles não tiram as nossas legendas (escolha do
# Rafael, 29/10, P82), nem o texto dele que fica só em parte do tempo (P52). DECISOES.md,
# Shopee Vídeo.
_LUGAR_NO_PROMPT = (
    "Diga onde os textos podem ficar sem cobrir o produto nem o rosto de alguém, na maior parte do vídeo, e sem "
    "cobrir, em nenhum momento, as fotos, quadros ou textos que o próprio vídeo pôs por cima da imagem: "
    "\"lugar\", \"alto\" (no topo, à esquerda, entre uns 12% e 22% da altura e até uns 65% da largura), "
    "\"meio\" (centralizado, entre uns 27% e 36% da altura), \"esquerda\" (perto da borda esquerda, até "
    "uns 40% da largura, entre uns 31% e 45% da altura) ou \"direita\" (o mesmo, perto da borda direita); "
    f"\"{SEM_LUGAR}\" se todos esses cobrem alguma dessas coisas.\n"
)
# Vídeo que já tem texto próprio na tela na maior parte do tempo vai sem as nossas legendas
# (escolha do Rafael, P52). A IA diz os trechos em que o texto do criador aparece, e a conta do
# tempo é feita aqui (parte_com_texto_proprio): no rascunho dos fones de 02/11, ela tinha dito
# que o texto ficava na maior parte do tempo, e as duas frases do criador só apareciam nos
# últimos 5 s de 26. O texto dentro das fotos e quadros do produto que o criador pôs por cima
# (as cores, a quantidade) não conta: é a miniatura dele, como a nossa (escolha do Rafael,
# 29/10, P82). DECISOES.md, Shopee Vídeo.
_TEXTO_NO_VIDEO_NO_PROMPT = (
    "Diga também em que trechos o próprio vídeo mostra texto escrito por cima da imagem, como legenda, título ou "
    "frase (não contam marca d'água, nome do perfil, o que está escrito no produto ou na embalagem, nem o texto "
    "dentro das fotos e quadros do produto que o vídeo pôs por cima, como as cores ou a quantidade): "
    "\"textos_do_video\", a lista dos trechos em que algum desses textos está na tela, cada um com o começo e o "
    "fim em segundos desde o começo do vídeo, como [{{\"inicio\": 0.0, \"fim\": 3.0}}]; [] se não há nenhum.\n"
)
# A nossa miniatura só entra quando o canto de cima à direita, onde ela fica, está livre do
# que o criador pôs por cima do vídeo: foto, quadro, texto ou figura (no vídeo da cortina de
# 29/10, ela cobriu a ponta da colagem das cores do criador). Marca d'água, logo e nome do
# perfil não contam. Ela fica lá o vídeo inteiro: o que passa por ela em qualquer momento
# conta. Escolha do Rafael (29/10, P81): DECISOES.md, Shopee Vídeo.
# A IA também diz onde fica cada coisa que o criador pôs no alto da tela, e a conta de cruzar
# com a miniatura é feita aqui (miniatura_no_video): no print de 29/10, a legenda do criador,
# centralizada logo abaixo da barra de busca, passava por baixo da ponta da miniatura, e a IA
# tinha dito que o canto estava livre. Com o lugar dito, a coisa do criador logo abaixo do
# canto faz a miniatura diminuir em vez de sair (escolha do Rafael, 29/10, P97).
_CANTO_NO_PROMPT = (
    "Diga também se o canto de cima à direita do vídeo (de uns 62% a 95% da largura e de uns 9% a 29% da altura) "
    "tem, em qualquer parte, foto, quadro, texto ou figura que o próprio vídeo pôs por cima da imagem, em "
    "qualquer momento (não contam marca d'água, logo nem nome do perfil; as coisas filmadas também não): "
    "\"canto_ocupado\", true ou false.\n"
    "Diga também onde ficam, em qualquer momento do vídeo, as legendas, títulos, frases, fotos, quadros e "
    "figuras que o próprio vídeo pôs por cima da imagem no alto da tela, até uns 30% da altura (sem marca "
    "d'água, logo, nome do perfil nem as coisas filmadas): \"por_cima_no_alto\", a lista com a parte da tela "
    "que cada um ocupa, em porcentagem da largura e da altura do vídeo, contando da borda esquerda e da borda "
    "de cima, como "
    "[{{\"esquerda\": 30, \"direita\": 70, \"topo\": 14, \"base\": 19}}]; [] se não há nenhum.\n"
)
# As legendas da fala (P118): só a voz de gente falando em português, como foi dita; sem fala, só
# música ou canto, ou com a fala em outra língua, nenhuma.
_LEGENDAS_NO_PROMPT = (
    "Escreva também as legendas do que as pessoas falam no vídeo (voz de gente falando, não música nem canto), "
    "em português do Brasil, com a ortografia e a acentuação certas: \"legendas\", a lista dos trechos na ordem, "
    "cada um com o começo e o fim em segundos desde o começo do vídeo e o texto falado. O texto é exatamente o "
    "que foi dito, palavra por palavra, do começo ao fim da fala: sem resumir, sem encurtar, sem trocar palavras "
    "e sem pular nenhuma frase. Siga o áudio, não a imagem: cada frase dita entra uma vez, na ordem e no tempo "
    "em que foi dita, mesmo quando a imagem se repete. Um trecho por frase (ou pedaço de frase) dita de uma vez, "
    "do tamanho que for: as longas são divididas na tela. Como "
    "[{{\"inicio\": 0.0, \"fim\": 2.0, \"texto\": \"...\"}}]; [] se ninguém fala, se só tem música ou "
    "canto, ou se a fala não é em português. Diga também se o próprio vídeo já mostra o que as pessoas falam "
    "escrito na tela (legenda da fala): \"legenda_no_video\", true ou false.\n"
)
_FALAS_E_LUGAR_NO_PROMPT = (_FALAS_NO_PROMPT + _O_QUE_FOI_FILMADO_NAO_CONTA + _LUGAR_NO_PROMPT
                            + _TEXTO_NO_VIDEO_NO_PROMPT + _CANTO_NO_PROMPT + _LEGENDAS_NO_PROMPT)
# Os textos do vídeo que vai ao ar: o original, sem cortes (as falas só importam nas versões).
PROMPT_DOS_TEXTOS = (
    "Você vai ver um vídeo curto de um produto vendido na Shopee: {nome}.\n"
    "Escreva quatro textos curtos para a tela e a capa do vídeo, em português do Brasil:\n"
    + _NOME_NO_PROMPT
    + "- \"vantagem\": uma vantagem do produto que o próprio vídeo mostra (ex.: \"Mantém gelado o dia todo\"), "
    f"até {MAXIMO_DA_VANTAGEM} caracteres;\n"
    + _CAPA_NO_PROMPT
    + _CHAMADA_NO_PROMPT
    + _REGRAS_NO_PROMPT + _COR_NO_PROMPT + _O_QUE_FOI_FILMADO_NAO_CONTA + _LUGAR_NO_PROMPT + _TEXTO_NO_VIDEO_NO_PROMPT
    + _CANTO_NO_PROMPT + _LEGENDAS_NO_PROMPT
    + "Responda só com o JSON: {{\"nome\": \"...\", \"vantagem\": \"...\", \"capa\": \"...\", \"chamada\": \"...\", "
    "\"cor\": \"...\", \"lugar\": \"alto\", \"textos_do_video\": [], \"canto_ocupado\": false, "
    "\"por_cima_no_alto\": [], \"legendas\": [], \"legenda_no_video\": false}}"
)

# Onde alguém fala, o vídeo fica inteiro e na velocidade normal: nada de corte, aceleração
# ou câmera lenta (escolha do Rafael, P45: o 1º exemplo cortou o começo da fala junto com a
# parte parada). Os trechos com fala vêm da IA, com esta folga de cada lado; sem a resposta
# dela, vale todo trecho com som acima de SILENCIO (pode ser música: na dúvida, não mexe).
FOLGA_DA_FALA = 0.3
SILENCIO = -40.0                    # dBFS


def janelas_com_fala(falas, duracao, volumes=()):
    """
    As janelas (de JANELA segundos) em que alguém fala: pelos trechos da IA (falas, [(início,
    fim)]) ou, sem eles (None), pelas janelas com som (volumes, dBFS por janela).
    """
    janelas = max(1, int(-(-duracao // JANELA))) if duracao > 0 else 0
    if falas is None:
        return frozenset(i for i, volume in enumerate(volumes) if i < janelas and volume > SILENCIO)
    protegidas = set()
    for inicio, fim in falas:
        for i in range(janelas):
            if i * JANELA < fim + FOLGA_DA_FALA and (i + 1) * JANELA > inicio - FOLGA_DA_FALA:
                protegidas.add(i)
    return frozenset(protegidas)


def ritmo(movimentos, duracao, por_segundo=QUADROS_DO_MOVIMENTO, com_fala=frozenset()):
    """
    [(início, fim, velocidade)] do vídeo remontado, pelo movimento de cada janela: parado
    de PARADO_QUE_SAI ou mais sai, calmo vai a ACELERADO, o resto a 1, e o segundo de mais
    ação em CAMERA_LENTA. As janelas com_fala ficam inteiras, a 1. Sem medição, o vídeo fica
    inteiro como está.
    """
    if duracao <= 0:
        return []
    if not movimentos:
        return [(0.0, duracao, 1.0)]
    janelas = max(1, int(-(-duracao // JANELA)))
    por_janela = round(por_segundo * JANELA)
    medidas, quietude = [], []
    for i in range(janelas):
        # A diferença j é a mudança que chega no quadro j+1: a janela i junta as que chegam
        # dentro dela.
        pedaco = sorted(movimentos[max(0, i * por_janela - 1):(i + 1) * por_janela - 1])
        if not pedaco:
            medidas.append(medidas[-1] if medidas else 0.0)
            quietude.append(quietude[-1] if quietude else 0.0)
            continue
        medidas.append(sum(pedaco) / len(pedaco))
        # A mediana não conta o salto de uma troca de cena: a janela que começa parada é parada.
        quietude.append(pedaco[len(pedaco) // 2])
    # Calmo ou ação pela média com as vizinhas (sem isso o ritmo troca a cada meio segundo);
    # parado pela janela mesmo, para o corte pegar o parado inteiro, até a borda.
    suave = [sum(medidas[max(0, i - 1):i + 2]) / len(medidas[max(0, i - 1):i + 2]) for i in range(janelas)]
    tipico = sorted(suave)[len(suave) // 2]
    parado, calmo = max(PARADO, PARADO_DO_TIPICO * tipico), CALMO_DO_TIPICO * tipico

    def tamanho(i):
        return min(JANELA, duracao - i * JANELA)

    tipo = ["fala" if i in com_fala else "parado" if quietude[i] < parado else "calmo" if suave[i] < calmo
            else "acao" for i in range(janelas)]
    # Parado curto não sai: fica como calmo.
    i = 0
    while i < janelas:
        fim = i
        while fim < janelas and tipo[fim] == "parado":
            fim += 1
        if fim > i and sum(tamanho(j) for j in range(i, fim)) < PARADO_QUE_SAI:
            tipo[i:fim] = ["calmo"] * (fim - i)
        i = max(fim, i + 1)
    lenta = set()
    if duracao >= VIDEO_COM_CAMERA_LENTA:
        quantas = max(1, round(SEGUNDOS_EM_CAMERA_LENTA / JANELA))
        acao = [i for i in range(janelas - quantas + 1) if all(tipo[j] == "acao" for j in range(i, i + quantas))]
        if acao:
            # Pela mediana: o salto de uma emenda não puxa a câmera lenta para ela.
            pico = max(acao, key=lambda i: sum(quietude[i:i + quantas]))
            lenta = set(range(pico, pico + quantas))

    def velocidades(cortar, acelerar):
        return [CAMERA_LENTA if i in lenta
                else (0.0 if cortar else ACELERADO if acelerar else 1.0) if tipo[i] == "parado"
                else ACELERADO if tipo[i] == "calmo" and acelerar else 1.0 for i in range(janelas)]

    def sem_trechos_curtos(vel):
        vel = list(vel)
        for _ in range(janelas):
            corridas, i = [], 0
            while i < janelas:
                fim = i
                while fim < janelas and vel[fim] == vel[i]:
                    fim += 1
                corridas.append((i, fim, vel[i]))
                i = fim
            mudou = False
            for n, (inicio, fim, v) in enumerate(corridas):
                if (v not in (1.0, ACELERADO) or sum(tamanho(j) for j in range(inicio, fim)) >= TRECHO_MINIMO
                        or any(tipo[j] == "fala" for j in range(inicio, fim))):
                    continue
                vizinhos = [corridas[k][2] for k in (n - 1, n + 1)
                            if 0 <= k < len(corridas) and corridas[k][2] in (1.0, ACELERADO)]
                if vizinhos:
                    vel[inicio:fim] = [vizinhos[0]] * (fim - inicio)
                    mudou = True
                    break
            if not mudou:
                return vel
        return vel

    def remontado(vel):
        return sum(tamanho(i) / v for i, v in enumerate(vel) if v)

    limite = min(duracao, max(MINIMO_DO_REMONTADO, duracao / 2))
    for cortar, acelerar in ((True, True), (False, True), (False, False)):
        vel = sem_trechos_curtos(velocidades(cortar, acelerar))
        if remontado(vel) >= limite - 1e-6:
            break
    trechos = []
    for i, v in enumerate(vel):
        inicio, fim = i * JANELA, i * JANELA + tamanho(i)
        if not v:
            continue
        if trechos and trechos[-1][2] == v and abs(trechos[-1][1] - inicio) < 1e-6:
            trechos[-1] = (trechos[-1][0], fim, v)
        else:
            trechos.append((inicio, fim, v))
    return trechos


def letreiro(texto, fundo=FUNDO_DOS_TEXTOS, largura_maxima=None, linhas_maximas=2, menor=None):
    """
    O texto da tela (PNG com fundo transparente, bytes): as letras numa caixa de cantos redondos,
    brancas ou pretas, as de mais contraste com o fundo (letra_que_contrasta: na caixa na cor do
    produto, P159 2), em até linhas_maximas linhas de até largura_maxima (padrão:
    LARGURA_DOS_TEXTOS), com a letra de LETRA_DOS_TEXTOS, que desce até a `menor` (padrão: a menor
    de LETRA_DOS_TEXTOS).
    """
    import io

    import matplotlib
    from PIL import Image, ImageDraw, ImageFont
    fonte_ttf = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")
    rascunho = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    maior, menor = LETRA_DOS_TEXTOS[0], menor or LETRA_DOS_TEXTOS[1]
    limite = largura_maxima or LARGURA_DOS_TEXTOS
    for tamanho in range(maior, menor - 1, -2):
        fonte = ImageFont.truetype(fonte_ttf, tamanho)
        linhas, linha = [], ""
        # Só o espaço comum separa as linhas: o espaço fixo não quebra.
        for palavra in [p for p in texto.split(" ") if p]:
            tentativa = f"{linha} {palavra}".strip()
            if not linha or rascunho.textlength(tentativa, font=fonte) <= limite:
                linha = tentativa
            else:
                linhas.append(linha)
                linha = palavra
        linhas.append(linha)
        if len(linhas) <= linhas_maximas and all(rascunho.textlength(t, font=fonte) <= limite for t in linhas):
            break
    altura_da_linha = round(tamanho * 1.25)
    largura = round(max(rascunho.textlength(t, font=fonte) for t in linhas)) + 2 * 28
    altura = altura_da_linha * len(linhas) + 2 * 18
    imagem = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(imagem)
    desenho.rounded_rectangle((0, 0, largura - 1, altura - 1), radius=22, fill=fundo)
    for i, texto_da_linha in enumerate(linhas):
        desenho.text((largura / 2, 18 + altura_da_linha * (i + 0.5)), texto_da_linha, font=fonte,
                     fill=letra_que_contrasta(fundo), anchor="mm")
    saida = io.BytesIO()
    imagem.save(saida, format="PNG")
    return saida.getvalue()


def letreiro_da_chamada(texto, largura_maxima=None, linhas_maximas=2):
    """
    A caixa da chamada para o produto (a última mensagem): vermelha, com o texto em CAIXA ALTA e a
    letra que desce até LETRA_MENOR_DA_CHAMADA. Escolha do Rafael (03/11, P140 2): DECISOES.md,
    Shopee Vídeo.
    """
    return letreiro(texto.upper(), FUNDO_DA_CHAMADA, largura_maxima, linhas_maximas, LETRA_MENOR_DA_CHAMADA)


# Palavra que não pode fechar o texto cortado: "amarração na" fica "amarração".
PALAVRAS_DE_LIGACAO = {"a", "o", "as", "os", "ao", "aos", "à", "às", "e", "ou", "de", "da", "do", "das", "dos",
                       "em", "na", "no", "nas", "nos", "com", "sem", "para", "pra", "por", "um", "uma", "que"}


def _so_letras(texto, maximo):
    """
    O texto da IA só com letras, números e pontuação simples (a fonte não tem emoji), até
    `maximo` caracteres. Maior que isso, é cortado na última palavra inteira, sem terminar
    numa palavra de ligação.
    """
    import re
    limpo = " ".join(re.sub(r"[^\w\s.,!?%/+\-:()]", " ", texto or "").split())
    if len(limpo) <= maximo:
        return limpo
    palavras = limpo[:maximo].rsplit(" ", 1)[0].rstrip(" ,.-:").split()
    while palavras and palavras[-1].lower().strip(",.-:") in PALAVRAS_DE_LIGACAO:
        palavras.pop()
    return " ".join(palavras).rstrip(" ,.-:")


# As letras do português, com os acentos que ele tem: letra fora delas (um "ü", um "ñ") é palavra
# que a IA escreveu errado, e o texto não vai assim para a tela nem para a capa. Pedido do Rafael
# em 30/10: DECISOES.md, Shopee Vídeo.
LETRAS_DO_PORTUGUES = frozenset("abcdefghijklmnopqrstuvwxyzáàâãçéêíóôõúªº")
PROMPT_DA_ORTOGRAFIA = ("Corrija a ortografia e a acentuação deste texto curto em português do Brasil, sem mudar o "
                        "sentido nem acrescentar nada. Responda só com o texto corrigido, sem aspas:\n{texto}")
PROCESSO_DA_ORTOGRAFIA = "edição do vídeo: ortografia da IA"


def letras_fora_do_portugues(texto):
    """As letras do texto que não existem no português (ex.: ["ü"]), em ordem; [] quando todas existem."""
    return sorted({letra for letra in (texto or "").lower() if letra.isalpha() and letra not in LETRAS_DO_PORTUGUES})


def _texto_certo(texto, maximo):
    """
    O texto da IA limpo (_so_letras) e com as letras do português. Com letra que não existe
    nele, a IA reescreve só o texto, uma vez, com a ortografia certa; ainda errado, ou sem
    resposta, "": o texto sai, como quando a IA não o dá (a capa de sempre, uma legenda a menos).
    """
    import asyncio

    import api_gemini
    limpo = _so_letras(texto, maximo)
    if not limpo or not letras_fora_do_portugues(limpo):
        return limpo
    try:
        resposta = asyncio.run(api_gemini.gerar_texto_gemini(PROMPT_DA_ORTOGRAFIA.format(texto=limpo)))
    except Exception:
        resposta = ""
    corrigido = _so_letras(str(resposta or "").strip().strip('"\''), maximo)
    if corrigido and not letras_fora_do_portugues(corrigido):
        registro_processos.registrar("shopee_video", PROCESSO_DA_ORTOGRAFIA, "corrigida", "letra fora do português",
                                     ok=True)
        return corrigido
    registro_processos.registrar("shopee_video", PROCESSO_DA_ORTOGRAFIA, "texto tirado",
                                 "letra fora do português, sem a correção", ok=False)
    return ""


# A revisão de todos os textos de um vídeo, numa chamada só de texto, pega o erro feito só com
# letras do português (o acento que falta, a letra trocada), que a conferência das letras não vê.
# Pedido do Rafael em 30/10: DECISOES.md, Shopee Vídeo.
PROMPT_DA_REVISAO = (
    "Revise a ortografia e a acentuação destes textos curtos em português do Brasil, que vão na tela de um "
    "vídeo. Corrija só letras, acentos e palavras escritas errado: não mude o sentido, não troque palavra "
    "certa, não acrescente nem tire nada. Responda só com o mesmo JSON, as mesmas chaves e os textos "
    "revisados:\n{textos}")
# A revisão que muda mais que a ortografia (outra frase, palavra a mais ou a menos, texto cortado)
# não vale: fica o texto como a IA o deu.
PARECIDO_NA_REVISAO = 0.8
MAXIMOS_DOS_TEXTOS = {"nome": MAXIMO_DO_NOME, "vantagem": MAXIMO_DA_VANTAGEM, "chamada": MAXIMO_DA_CHAMADA,
                      "capa": MAXIMO_DA_CAPA}


def _so_ortografia(antes, depois, maximo):
    """O texto revisado (depois) quando a revisão mexeu só na ortografia de antes; "" quando não."""
    import difflib
    revisado = _so_letras(depois, 10 ** 6)
    if (not revisado or revisado == antes or letras_fora_do_portugues(revisado) or len(revisado) > maximo
            or abs(len(revisado.split()) - len(antes.split())) > 1
            or difflib.SequenceMatcher(None, antes.lower(), revisado.lower()).ratio() < PARECIDO_NA_REVISAO):
        return ""
    return revisado


def _revisar_ortografia(textos):
    """
    Revisa pela IA, numa chamada só, os textos da tela (o nome, a vantagem e a chamada, também os
    das versões) e troca cada um pelo revisado quando a revisão mexeu só na ortografia. Sem
    resposta, os textos ficam como vieram. Muda textos e o devolve.
    """
    import asyncio
    import json
    import re

    import api_gemini
    lugares = [(textos, chave) for chave in MAXIMOS_DOS_TEXTOS if textos.get(chave)]
    lugares += [(versao, chave) for versao in textos.get("versoes") or [] for chave in ("vantagem", "chamada")
                if versao.get(chave)]
    if not lugares:
        return textos
    pedido = json.dumps({f"t{i}": lugar[chave] for i, (lugar, chave) in enumerate(lugares)}, ensure_ascii=False)
    try:
        resposta = asyncio.run(api_gemini.gerar_texto_gemini(PROMPT_DA_REVISAO.format(textos=pedido)))
        achado = re.search(r"\{.*\}", resposta or "", re.S)
        revisados = json.loads(achado.group(0)) if achado else {}
    except Exception:
        revisados = {}
    if not isinstance(revisados, dict) or not revisados:
        registro_processos.registrar("shopee_video", PROCESSO_DA_ORTOGRAFIA, "sem a revisão", "a IA não respondeu")
        return textos
    corrigidos = 0
    for i, (lugar, chave) in enumerate(lugares):
        revisado = _so_ortografia(lugar[chave], str(revisados.get(f"t{i}") or ""), MAXIMOS_DOS_TEXTOS[chave])
        if revisado:
            lugar[chave] = revisado
            corrigidos += 1
    registro_processos.registrar("shopee_video", PROCESSO_DA_ORTOGRAFIA, "revisada",
                                 f"{corrigidos} corrigido(s)" if corrigidos else "nada a corrigir", ok=True)
    return textos


def _resposta_da_ia(video, prompt):
    """O JSON que a IA respondeu vendo o vídeo (dict); {} quando ela não respondeu."""
    import asyncio
    import json
    import re

    import api_gemini
    try:
        resposta = asyncio.run(api_gemini.analisar_video_gemini(video, prompt))
    except Exception:
        return {}
    achado = re.search(r"\{.*\}", resposta or "", re.S)
    try:
        dados = json.loads(achado.group(0)) if achado else {}
    except ValueError:
        return {}
    return dados if isinstance(dados, dict) else {}


def _nome_lugar_e_falas(dados, duracao=0.0):
    """
    O nome, o lugar, a cor do produto (P159 2), as falas, se o vídeo já tem texto próprio na tela
    na maior parte do tempo (pelos trechos que a IA deu e a duracao do vídeo, em segundos; com a
    parte do tempo em "parte_com_texto") e se o canto da nossa miniatura tem coisa do criador, da
    resposta da IA, só os que vieram certos.
    """
    textos = {}
    nome = _texto_certo(str(dados.get("nome") or ""), MAXIMO_DO_NOME)
    if nome:
        textos["nome"] = nome
    if dados.get("lugar") in LUGARES_DOS_TEXTOS or dados.get("lugar") == SEM_LUGAR:
        textos["lugar"] = dados["lugar"]
    cor = " ".join(str(dados.get("cor") or "").lower().split())
    if cor in CORES_DO_PRODUTO or cor in CORES_DE_SEMPRE:
        textos["cor"] = cor
    if isinstance(dados.get("canto_ocupado"), bool):
        textos["canto_ocupado"] = dados["canto_ocupado"]
    trechos = _trechos_com_texto(dados.get("textos_do_video"))
    parte = parte_com_texto_proprio(trechos, duracao) if trechos is not None else None
    if parte is not None:
        textos["texto_no_video"] = parte > PARTE_COM_TEXTO_PROPRIO
        textos["parte_com_texto"] = round(parte, 2)
    por_cima = _por_cima_no_alto(dados.get("por_cima_no_alto"))
    if por_cima:
        textos["por_cima"] = por_cima
    falas = _falas(dados.get("falas"))
    if falas is not None:
        textos["falas"] = falas
    legendas = _legendas(dados.get("legendas"))
    if legendas is not None:
        textos["legendas"] = legendas
    if isinstance(dados.get("legenda_no_video"), bool):
        textos["legenda_no_video"] = dados["legenda_no_video"]
    return textos


def lugar_dos_textos(textos):
    """O lugar das nossas legendas pela resposta da IA: nenhum quando o vídeo já tem texto na tela (P52)."""
    return SEM_LUGAR if textos.get("texto_no_video") else textos.get("lugar")


# "Na maior parte do tempo" (P52): o texto próprio do vídeo na tela em mais da metade dele.
PARTE_COM_TEXTO_PROPRIO = 0.5


def _trechos_com_texto(bruto):
    """
    Os trechos em que o vídeo mostra texto próprio na tela, como a IA deu ([(início, fim)], em
    segundos), só os certos; None quando a lista não veio.
    """
    if not isinstance(bruto, list):
        return None
    trechos = []
    for trecho in bruto:
        if not isinstance(trecho, dict):
            continue
        try:
            inicio, fim = float(trecho.get("inicio")), float(trecho.get("fim"))
        except (TypeError, ValueError):
            continue
        if fim > inicio >= 0:
            trechos.append((inicio, fim))
    return trechos


def parte_com_texto_proprio(trechos, duracao):
    """
    A parte do vídeo (de 0 a 1) com texto próprio na tela: os trechos somados, o que se cruza
    contando uma vez e só dentro da duração do vídeo (em segundos). None sem a duração.
    """
    if not duracao or duracao <= 0:
        return None
    total, ate = 0.0, 0.0
    for inicio, fim in sorted(trechos):
        inicio, fim = max(inicio, ate), min(fim, duracao)
        if fim > inicio:
            total += fim - inicio
            ate = fim
    return total / duracao


def _duracao_para_os_trechos(video, dados):
    """A duração do vídeo, lida só quando a IA deu trechos com texto próprio (0 sem eles)."""
    return videos.duracao(video) if dados.get("textos_do_video") else 0.0


def _por_cima_no_alto(lista):
    """
    [(esquerda, direita, topo, base)], em % do vídeo, do que a IA diz que o criador pôs no
    alto da tela; só os que vieram com os quatro números. Resposta em fração (0,3) vira %.
    """
    caixas = []
    for item in lista if isinstance(lista, list) else []:
        try:
            valores = [float(item[chave]) for chave in ("esquerda", "direita", "topo", "base")]
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(valor) for valor in valores):
            continue
        if max(valores) <= 1 and any(valor != int(valor) for valor in valores):
            valores = [round(valor * 100, 1) for valor in valores]
        valores = [min(max(valor, 0.0), 100.0) for valor in valores]
        caixas.append(tuple(sorted(valores[:2]) + sorted(valores[2:])))
    return caixas


# A IA acerta o lugar das coisas na tela só mais ou menos: o que ela diz que o criador pôs no
# alto conta como em cima da miniatura também quando passa a esta folga dela (px do vídeo de
# 720x1280). A miniatura é tomada como quadrada, como a foto do anúncio quase sempre é.
FOLGA_DA_MINIATURA = 30
# Com a coisa do criador logo abaixo do canto, a miniatura diminui, no mesmo canto, só o
# necessário para ficar acima dela, com a folga (sem encostar); se precisar ficar menor que
# 2/3 do tamanho de sempre, fica de fora. Escolha do Rafael (29/10, P97): DECISOES.md, Shopee Vídeo.
MENOR_MINIATURA = LARGURA_DA_MINIATURA * 2 // 3
# O canto que a IA olha para dizer se está ocupado (_CANTO_NO_PROMPT), em % do vídeo: da
# esquerda à direita e de cima a baixo, o lugar da miniatura com a folga (ela fica logo abaixo da
# barra de busca, P120).
CANTO_OLHADO_PELA_IA = (62, 95, 9, 29)


def _cruza_a_miniatura(caixa, largura=LARGURA_DA_MINIATURA):
    """A caixa (em % do vídeo) passa pela miniatura desta largura, com a folga?"""
    esquerda, direita, topo, base = caixa
    largura_da_tela, altura = TELA
    meia = largura / 2 + FOLGA_DA_MINIATURA
    x, y = centro_da_miniatura(largura)
    return (esquerda * largura_da_tela / 100 < x + meia and direita * largura_da_tela / 100 > x - meia
            and topo * altura / 100 < y + meia and base * altura / 100 > y - meia)


def _no_canto_olhado(caixa):
    """A caixa (em % do vídeo) entra no canto que a IA olha para o canto_ocupado?"""
    esquerda, direita, topo, base = caixa
    comeco, fim, desde, ate = CANTO_OLHADO_PELA_IA
    return esquerda < fim and direita > comeco and topo < ate and base > desde


def miniatura_no_video(textos):
    """
    A largura da nossa miniatura neste vídeo, em px: a de sempre com o canto livre ou sem a
    resposta da IA. Quando alguma das coisas que ela diz que o criador pôs no alto passa pela
    miniatura, a miniatura diminui no mesmo canto até ficar acima dela, com a folga, e fica de
    fora (0) se precisar ficar menor que MENOR_MINIATURA (P81 e P97). Com o canto ocupado sem
    nenhuma coisa no canto dizendo onde, também fica de fora (P81).
    """
    caixas = list(textos.get("por_cima", ()))
    if textos.get("canto_ocupado") and not any(map(_no_canto_olhado, caixas)):
        return 0
    largura = LARGURA_DA_MINIATURA
    for caixa in caixas:
        if _cruza_a_miniatura(caixa, largura):
            # A base da miniatura sobe até ficar a folga acima do topo da caixa. Menor, ela
            # só encolhe para dentro do canto: a caixa que não passava não passa a passar.
            cabe = caixa[2] * TELA[1] / 100 - FOLGA_DA_MINIATURA - CANTO_DA_MINIATURA[1]
            largura = min(largura, int(cabe) // 2 * 2)
    return largura if largura >= MENOR_MINIATURA else 0


# Por que a nossa miniatura não vai inteira num vídeo: o canto ocupado sem a IA dizer onde (P81)
# ou a coisa do criador no alto que passa por ela (P97). O registro separa os dois, para o
# checkup mostrar qual tira a miniatura dos rascunhos.
PROCESSO_DO_CANTO = "edição do vídeo: canto da miniatura"
CANTO_SEM_DIZER_ONDE = "o canto ocupado, sem dizer onde"


def por_que_a_miniatura(textos):
    """
    O porquê fixo da miniatura menor ou de fora neste vídeo, pela resposta da IA: o canto
    ocupado sem dizer onde, ou a altura (em % do vídeo) em que começa a coisa mais alta do
    criador que passa por ela; "" quando nada a tira.
    """
    caixas = list(textos.get("por_cima", ()))
    if textos.get("canto_ocupado") and not any(map(_no_canto_olhado, caixas)):
        return CANTO_SEM_DIZER_ONDE
    topos = [caixa[2] for caixa in caixas if _cruza_a_miniatura(caixa)]
    return f"a coisa do criador no alto começa a {min(topos):.0f}% da altura" if topos else ""


# A IA às vezes conta como coisa do criador o que foi filmado no canto da miniatura (uma revista em
# cima da mesa no rascunho dos fones de 02/11; no vídeo do Rafael das 22:38 de 02/11, a caixa do
# produto atrás do brinquedo, com as letras impressas), e a miniatura saía sem precisar (P81).
# Quando a resposta tira ou diminui a miniatura, uma pergunta só sobre o canto confere se o que está
# lá foi posto por cima na edição: só filmado, a miniatura fica do tamanho de sempre; sem
# resposta, vale a 1ª. Pedido do Rafael ("Pq não veio a miniatura?"): DECISOES.md, Shopee Vídeo.
PROMPT_DO_CANTO = (
    "Você confere um vídeo de afiliado da Shopee antes de ele ir para a Shopee Vídeo.\n"
    "Olhe só o canto de cima à direita do vídeo (de uns 55% a 100% da largura e do topo até uns 35% da altura), "
    "do começo ao fim. Diga se, em algum momento, há nesse canto algo que o próprio vídeo pôs por cima da imagem "
    "na edição: legenda, título, frase, figurinha, foto, quadro ou seta, que fica parado na tela enquanto a cena "
    "se mexe atrás. As coisas filmadas, que fazem parte da cena e se mexem com ela, nunca contam: o produto, a "
    "embalagem, uma caixa, um livro, uma revista, uma tela, um cartaz, e o que está escrito ou desenhado nelas. "
    "Marca d'água, logo e nome do perfil também não contam.\n"
    "Responda só com um JSON, nesta ordem: {\"o_que_ha_no_canto\": \"o que se vê ali\", "
    "\"por_cima_na_edicao\": true ou false}"
)
CANTO_FILMADO = "mantida - no canto, só o que foi filmado"


def _conferir_o_canto(video, textos):
    """
    Confere, numa pergunta só sobre o canto, a resposta da IA que tira ou diminui a nossa
    miniatura (miniatura_no_video): com o canto só filmado, o canto fica livre e saem as coisas que
    passavam pela miniatura; com algo posto por cima, ou sem resposta, fica a 1ª. textos["canto_filmado"]
    guarda o porquê da 1ª, para o registro. Muda textos e o devolve.
    """
    if miniatura_no_video(textos) >= LARGURA_DA_MINIATURA:
        return textos
    if _resposta_da_ia(video, PROMPT_DO_CANTO).get("por_cima_na_edicao") is False:
        textos["canto_filmado"] = por_que_a_miniatura(textos)
        textos["canto_ocupado"] = False
        textos["por_cima"] = [caixa for caixa in textos.get("por_cima", ()) if not _cruza_a_miniatura(caixa)]
    return textos


def _vantagem_e_chamada(dados, textos):
    """Põe em textos a vantagem e a chamada da resposta da IA, só as que vieram certas."""
    for chave, maximo in (("vantagem", MAXIMO_DA_VANTAGEM), ("chamada", MAXIMO_DA_CHAMADA)):
        limpo = _texto_certo(str(dados.get(chave) or ""), maximo)
        if limpo:
            textos[chave] = limpo
    return textos


def _sem_acento(texto):
    """As palavras do texto em minúsculas e sem acento, só as letras e os números."""
    import re
    import unicodedata
    simples = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", simples)


def _mesmo_comeco(palavra, outra):
    """As duas palavras começam igual, pelo menos COMECO_IGUAL letras e todas menos uma da menor."""
    comum = len(os.path.commonprefix([palavra, outra]))
    return comum >= COMECO_IGUAL and comum >= min(len(palavra), len(outra)) - 1


def comeca_pelo_produto(frase, nome):
    """
    A frase começa pelo que é o produto (P122)? A 1ª palavra dela, sem artigo nem número na
    frente, tem o mesmo começo de uma palavra do nome (_mesmo_comeco). Sem o nome, sim.
    """
    do_nome = [p for p in _sem_acento(nome) if len(p) >= COMECO_IGUAL and p not in PALAVRAS_DE_LIGACAO]
    if not do_nome:
        return True
    primeira = next((p for p in _sem_acento(frase) if p not in PALAVRAS_DE_LIGACAO and not p.isdigit()), "")
    return any(_mesmo_comeco(primeira, palavra) for palavra in do_nome)


def por_que_a_frase_nao_serve(frase, nome):
    """O porquê fixo da frase da capa (já limpa) não seguir a P122; "" quando ela segue."""
    if not frase:
        return SEM_FRASE
    if len(frase) > MAXIMO_DA_CAPA:
        return LONGA_DEMAIS
    if not PALAVRAS_DA_CAPA[0] <= len(frase.split()) <= PALAVRAS_DA_CAPA[1]:
        return FORA_DAS_PALAVRAS
    if not comeca_pelo_produto(frase, nome):
        return SEM_O_PRODUTO
    return ""


def _frase_que_serve(bruto, nome):
    """
    (frase, porquê) da frase da capa que veio da IA: a frase limpa e "" quando ela segue a P122;
    senão, o porquê fixo. Com letra que não existe no português, a IA corrige uma vez
    (_texto_certo); a frase maior que o limite não é cortada (cortada, perderia o sentido).
    """
    frase = _so_letras(bruto, 10 ** 6)
    porque = por_que_a_frase_nao_serve(frase, nome)
    if porque:
        return frase, porque
    certa = _texto_certo(frase, MAXIMO_DA_CAPA)
    if not certa:
        return frase, LETRA_FORA
    return certa, por_que_a_frase_nao_serve(certa, nome)


def _explicacao_para_a_ia(frase, porque):
    """O que estava errado na frase de antes, para o pedido de novo à IA."""
    if porque == LONGA_DEMAIS:
        return f"\"{frase}\" tem {len(frase)} caracteres, mais que {MAXIMO_DA_CAPA}"
    if porque == FORA_DAS_PALAVRAS:
        return f"\"{frase}\" tem {len(frase.split())} palavra(s)"
    if porque == SEM_O_PRODUTO:
        return f"\"{frase}\" não começa pelo que é o produto"
    if porque == LETRA_FORA:
        return f"\"{frase}\" tem letra que não existe no português"
    return "a frase não veio"


def _pedir_a_frase_de_novo(textos, frase, porque):
    """A frase da capa que a IA reescreveu, numa chamada só de texto; "" sem resposta."""
    import asyncio

    import api_gemini
    pedido = PROMPT_DA_FRASE_DA_CAPA.format(
        minimo=PALAVRAS_DA_CAPA[0], maximo_de_palavras=PALAVRAS_DA_CAPA[1], maximo=MAXIMO_DA_CAPA,
        nome=textos.get("nome") or "o do vídeo", vantagem=textos.get("vantagem") or "a que o vídeo mostra",
        porque=_explicacao_para_a_ia(frase, porque))
    try:
        resposta = asyncio.run(api_gemini.gerar_texto_gemini(pedido))
    except Exception:
        resposta = ""
    linhas = [linha.strip() for linha in str(resposta or "").splitlines() if linha.strip()]
    return linhas[0].strip("\"'“”").rstrip(".") if linhas else ""


def _com_a_frase_da_capa(bruto, textos):
    """
    Põe em textos["capa"] a frase da capa (P122) que a IA escreveu, quando ela segue a regra
    (por_que_a_frase_nao_serve). A que não segue volta à IA uma vez, só a frase, com o que estava
    errado, e textos["capa_de_novo"] guarda o porquê da 1ª. Sem nenhuma certa, textos["sem_a_capa"]
    guarda o porquê da 2ª, e a capa vai com a vantagem (frase_da_capa). Muda textos e o devolve.
    """
    nome = textos.get("nome", "")
    frase, porque = _frase_que_serve(bruto, nome)
    if not porque:
        textos["capa"] = frase
        return textos
    textos["capa_de_novo"] = porque
    # Sem o nome nem a vantagem, a IA não teria de onde tirar a frase: sem pedir de novo.
    pedida = _pedir_a_frase_de_novo(textos, frase, porque) if nome or textos.get("vantagem") else ""
    nova, porque_da_nova = _frase_que_serve(pedida, nome)
    if porque_da_nova:
        textos["sem_a_capa"] = porque_da_nova
    else:
        textos["capa"] = nova
    return textos


def registro_da_frase(textos, frase):
    """
    (resultado, detalhe, ok) da frase da capa para o registro: "curta", "curta na 2ª vez" (com o
    porquê da 1ª), "o nome (sem a curta)" ou "a vantagem (sem a curta nem o nome)" (com o porquê
    das duas), e as letras da frase.
    """
    letras = f"{len(frase)} letras"
    primeira = textos.get("capa_de_novo", "")
    if textos.get("capa"):
        if primeira:
            return "curta na 2ª vez", f"a 1ª: {primeira}; {letras}", True
        return "curta", letras, True
    resultado = "o nome (sem a curta)" if textos.get("nome") else "a vantagem (sem a curta nem o nome)"
    if primeira:
        return resultado, f"a 1ª: {primeira}; a 2ª: {textos.get('sem_a_capa', SEM_FRASE)}; {letras}", None
    return resultado, letras, None


def frase_da_capa(textos):
    """
    A frase da capa com chamada: a curta da IA (P122); sem ela nem na 2ª vez, o nome genérico do
    produto, que diz o que ele é (o que não cabe numa linha vai em duas); sem o nome, a vantagem.
    Escolha do Rafael (02/11, P131): DECISOES.md, Shopee Vídeo.
    """
    return textos.get("capa") or textos.get("nome") or textos.get("vantagem", "")


def textos_da_tela(video, nome):
    """
    {"nome", "vantagem", "capa", "chamada", "lugar", "texto_no_video", "parte_com_texto",
    "canto_ocupado", "por_cima"} que a IA escreveu vendo o vídeo, só o que veio certo; {} sem
    resposta. Com a frase da capa pedida de novo, "capa_de_novo" (e, sem ela, "sem_a_capa") diz
    por quê (_com_a_frase_da_capa).
    """
    dados = _resposta_da_ia(video, PROMPT_DOS_TEXTOS.format(nome=nome))
    textos = _vantagem_e_chamada(dados, _nome_lugar_e_falas(dados, _duracao_para_os_trechos(video, dados)))
    # Só este pedido traz a frase da capa; sem resposta da IA, não há o que pedir de novo.
    if dados:
        textos = _conferir_o_canto(video, _com_a_frase_da_capa(str(dados.get("capa") or ""), textos))
    return _revisar_ortografia(textos)


def _falas(bruto):
    """Os trechos com fala que a IA deu ([(início, fim)], em segundos); None quando não vieram certos."""
    if not isinstance(bruto, list):
        return None
    falas = []
    for trecho in bruto:
        try:
            inicio, fim = float(trecho[0]), float(trecho[1])
        except (TypeError, ValueError, IndexError):
            return None
        if fim > inicio >= 0:
            falas.append((inicio, fim))
    return falas


def _legendas(bruto):
    """
    As legendas da fala que a IA deu ([(início, fim, texto)], em ordem), só os trechos certos: com o
    começo antes do fim e o texto com as letras do português (o trecho com letra de outra língua sai);
    None quando a lista não veio.
    """
    if not isinstance(bruto, list):
        return None
    legendas = []
    for trecho in bruto:
        if not isinstance(trecho, dict):
            continue
        try:
            inicio, fim = float(trecho.get("inicio")), float(trecho.get("fim"))
        except (TypeError, ValueError):
            continue
        texto = _so_letras(str(trecho.get("texto") or ""), 10 ** 6)
        if texto and fim > inicio >= 0 and not letras_fora_do_portugues(texto):
            legendas.append((inicio, fim, texto))
    return sorted(legendas)


# Por que o vídeo vai sem as legendas da fala (textos fixos: o registro e o checkup contam por eles).
SEM_FALA = "ninguém fala em português no vídeo"
LEGENDA_JA_NO_VIDEO = "o vídeo já tem a fala escrita na tela"
SEM_AS_LEGENDAS_DA_IA = "a IA não deu as legendas"


def legendas_da_fala(textos):
    """
    ([(início, fim, texto)], porquê): as legendas da fala que vão no vídeo, e o porquê fixo quando não
    vai nenhuma. Escolha do Rafael (01/11, P118): DECISOES.md, Shopee Vídeo.
    """
    if textos.get("legenda_no_video"):
        return [], LEGENDA_JA_NO_VIDEO
    if "legendas" not in textos:
        return [], SEM_AS_LEGENDAS_DA_IA
    if not textos["legendas"]:
        return [], SEM_FALA
    return list(textos["legendas"]), ""


# O tempo das legendas da fala vem do som do vídeo (videos.palavras_faladas), palavra por palavra: a IA
# escreve o texto (P118), e cada palavra dela fica no tempo da mesma palavra no áudio; a que o áudio não
# reconheceu fica entre as vizinhas. No vídeo do Rafael das 19:29 de 02/11, o tempo que a IA estima
# vendo o vídeo adiantava as legendas até 2 s da fala. Com menos de PARTE_ACHADA_NO_AUDIO das palavras
# da IA achadas no áudio, ou sem o reconhecimento de voz, as legendas ficam com o tempo da IA, e o
# registro diz por quê. Cada legenda fica na tela até DEPOIS_DA_FALA depois da última palavra dela, ou
# até a seguinte começar. Pedido do Rafael: DECISOES.md, Shopee Vídeo.
PARTE_ACHADA_NO_AUDIO = 0.5
DEPOIS_DA_FALA = 0.3
SEGUNDOS_POR_PALAVRA = 0.3       # a palavra da IA antes da 1ª ou depois da última achada no áudio
PROCESSO_DO_TEMPO_DAS_LEGENDAS = "edição do vídeo: tempo das legendas"
PELO_AUDIO = "pelo áudio"
PELO_TEMPO_DA_IA = "pelo tempo da IA"
SEM_O_RECONHECIMENTO = "sem o reconhecimento de voz"
FALA_NAO_BATEU = "a fala do áudio não bateu com a da IA"


def _pedacos_da_palavra(palavra):
    """A palavra sem acento, em minúsculas e só com letras e números, em pedaços pelo hífen ("mesa-posta": mesa, posta)."""
    import unicodedata
    simples = unicodedata.normalize("NFKD", palavra.casefold()).encode("ascii", "ignore").decode()
    return [p for p in ("".join(c for c in parte if c.isalnum()) for parte in simples.split("-")) if p]


def _preencher_os_tempos(tempos):
    """
    Dá tempo às palavras que o áudio não reconheceu (None em tempos, [(início, fim)] na ordem): entre as
    vizinhas achadas, repartido igual; antes da 1ª e depois da última, SEGUNDOS_POR_PALAVRA cada uma.
    """
    n = 0
    while n < len(tempos):
        if tempos[n] is not None:
            n += 1
            continue
        fim_da_falta = n
        while fim_da_falta < len(tempos) and tempos[fim_da_falta] is None:
            fim_da_falta += 1
        quantas = fim_da_falta - n
        antes = tempos[n - 1][1] if n else None
        depois = tempos[fim_da_falta][0] if fim_da_falta < len(tempos) else None
        if antes is None:
            antes = max(0.0, depois - quantas * SEGUNDOS_POR_PALAVRA)
        if depois is None or depois < antes:
            depois = antes + quantas * SEGUNDOS_POR_PALAVRA
        passo = (depois - antes) / quantas
        for j in range(quantas):
            tempos[n + j] = (antes + j * passo, antes + (j + 1) * passo)
        n = fim_da_falta


def legendas_no_tempo_da_fala(legendas, palavras):
    """
    (legendas no tempo do áudio, palavras da IA achadas, palavras da IA): as legendas da IA ([(início,
    fim, texto)]) no tempo das palavras do áudio ([(início, fim, palavra)], do reconhecimento de voz),
    como [(início, fim, texto, tempos)], com tempos = [(início, fim)] de cada palavra do texto, para a
    legenda longa ser dividida no tempo certo (pedacos_da_legenda). As legendas vêm None quando o áudio
    não acha PARTE_ACHADA_NO_AUDIO das palavras da IA.
    """
    import difflib
    da_ia = [(i, palavra) for i, (_inicio, _fim, texto) in enumerate(legendas) for palavra in texto.split()]
    pedacos_da_ia = [(k, pedaco) for k, (_i, palavra) in enumerate(da_ia) for pedaco in _pedacos_da_palavra(palavra)]
    pedacos_do_audio = [(inicio, fim, pedaco) for inicio, fim, palavra in palavras or ()
                        for pedaco in _pedacos_da_palavra(palavra)]
    comparacao = difflib.SequenceMatcher(None, [pedaco for _k, pedaco in pedacos_da_ia],
                                         [pedaco for *_tempo, pedaco in pedacos_do_audio], autojunk=False)
    tempos = [None] * len(da_ia)
    for bloco in comparacao.get_matching_blocks():
        for n in range(bloco.size):
            k = pedacos_da_ia[bloco.a + n][0]
            inicio, fim, _pedaco = pedacos_do_audio[bloco.b + n]
            tempos[k] = (inicio, fim) if tempos[k] is None else (min(tempos[k][0], inicio), max(tempos[k][1], fim))
    achadas = sum(1 for tempo in tempos if tempo is not None)
    if not da_ia or achadas < PARTE_ACHADA_NO_AUDIO * len(da_ia):
        return None, achadas, len(da_ia)
    _preencher_os_tempos(tempos)
    no_tempo, k = [], 0
    for _inicio, _fim, texto in legendas:
        deste = tempos[k:k + len(texto.split())]
        k += len(deste)
        if deste:
            no_tempo.append((round(deste[0][0], 2), round(deste[-1][1] + DEPOIS_DA_FALA, 2), texto,
                             [(round(a, 2), round(b, 2)) for a, b in deste]))
    return sorted(no_tempo, key=lambda legenda: legenda[:2]), achadas, len(da_ia)


def legendas_no_tempo(video, legendas):
    """
    (legendas, resultado, detalhe): as legendas da IA no tempo do áudio do vídeo (legendas_no_tempo_da_fala),
    ou como vieram, com o tempo da IA, e o porquê fixo, para o registro. Sem legendas, (legendas, "", "").
    """
    if not legendas:
        return legendas, "", ""
    palavras = videos.palavras_faladas(video)
    if palavras is None:
        return legendas, PELO_TEMPO_DA_IA, SEM_O_RECONHECIMENTO
    no_tempo, achadas, total = legendas_no_tempo_da_fala(legendas, palavras)
    if no_tempo is None:
        return legendas, PELO_TEMPO_DA_IA, f"{FALA_NAO_BATEU} ({achadas} de {total} palavras no áudio)"
    return no_tempo, PELO_AUDIO, f"{achadas} de {total} palavras no áudio"


def _linhas_da_legenda(texto, fonte, rascunho):
    """As linhas do texto quebradas na largura da legenda (só no espaço comum)."""
    limite = DIREITA_DA_LEGENDA - ESQUERDA_DA_LEGENDA - 2 * CONTORNO_DA_LEGENDA
    linhas, linha = [], ""
    for palavra in texto.split():
        tentativa = f"{linha} {palavra}".strip()
        if not linha or rascunho.textlength(tentativa, font=fonte) <= limite:
            linha = tentativa
        else:
            linhas.append(linha)
            linha = palavra
    if linha:
        linhas.append(linha)
    return linhas, all(rascunho.textlength(t, font=fonte) <= limite for t in linhas)


def legenda_da_fala(texto):
    """
    A legenda (PNG com fundo transparente, bytes): letras brancas com contorno preto, sem caixa,
    centralizadas, na maior letra de LETRA_DA_LEGENDA em que o texto cabe em LINHAS_DA_LEGENDA linhas
    da largura dela. None quando nem a menor letra cabe (o trecho é dividido antes).
    """
    import io

    import matplotlib
    from PIL import Image, ImageDraw, ImageFont
    fonte_ttf = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")
    rascunho = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    maior, menor = LETRA_DA_LEGENDA
    for tamanho in range(maior, menor - 1, -2):
        fonte = ImageFont.truetype(fonte_ttf, tamanho)
        linhas, cabe = _linhas_da_legenda(texto, fonte, rascunho)
        if cabe and len(linhas) <= LINHAS_DA_LEGENDA:
            break
    else:
        return None
    altura_da_linha = round(tamanho * 1.25)
    borda = CONTORNO_DA_LEGENDA + 2
    largura = round(max(rascunho.textlength(t, font=fonte) for t in linhas)) + 2 * borda
    altura = altura_da_linha * len(linhas) + 2 * borda
    imagem = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(imagem)
    for i, linha in enumerate(linhas):
        desenho.text((largura / 2, borda + altura_da_linha * (i + 0.5)), linha, font=fonte, fill="white",
                     anchor="mm", stroke_width=CONTORNO_DA_LEGENDA, stroke_fill="black")
    saida = io.BytesIO()
    imagem.save(saida, format="PNG")
    return saida.getvalue()


# Ao dividir um trecho em dois, o corte depois de uma vírgula ou de um ponto vale esta parte do tamanho
# do trecho a mais perto do meio: a legenda fica com a frase inteira quando dá.
PREFERENCIA_DA_PONTUACAO = 0.25


def _ponto_de_corte(palavras):
    """Onde dividir as palavras em duas partes: perto do meio (em letras), de preferência depois de uma pontuação."""
    total = len(" ".join(palavras))
    melhor, nota_melhor = len(palavras) // 2, None
    for i in range(1, len(palavras)):
        nota = abs(total - 2 * len(" ".join(palavras[:i]))) / total
        if palavras[i - 1][-1:] in ",;:.!?":
            nota -= PREFERENCIA_DA_PONTUACAO
        if nota_melhor is None or nota < nota_melhor:
            melhor, nota_melhor = i, nota
    return melhor


def pedacos_da_legenda(inicio, fim, texto, tempos=None):
    """
    [(início, fim, texto, imagem)] do trecho: o que não cabe numa legenda (LINHAS_DA_LEGENDA linhas) é
    dividido em dois pelas palavras (_ponto_de_corte), até caber; nenhuma palavra fica de fora (só a
    palavra sozinha que nem a menor letra cabe). Com os tempos de cada palavra no áudio ([(início, fim)],
    legendas_no_tempo_da_fala), a 2ª parte começa quando a 1ª palavra dela é dita; sem eles, o tempo é
    repartido pelo tamanho de cada parte.
    """
    imagem = legenda_da_fala(texto)
    palavras = texto.split()
    if imagem or len(palavras) < 2:
        return [(inicio, fim, texto, imagem)] if imagem else []
    meio = _ponto_de_corte(palavras)
    primeira, segunda = " ".join(palavras[:meio]), " ".join(palavras[meio:])
    if tempos and len(tempos) == len(palavras):
        corte = min(max(tempos[meio][0], inicio), fim)
        return (pedacos_da_legenda(inicio, corte, primeira, tempos[:meio])
                + pedacos_da_legenda(corte, fim, segunda, tempos[meio:]))
    corte = inicio + (fim - inicio) * len(primeira) / (len(primeira) + len(segunda))
    return pedacos_da_legenda(inicio, corte, primeira) + pedacos_da_legenda(corte, fim, segunda)


def _trechos_que_cabem(inicio, fim, texto, tempos=None):
    """[(início, fim, imagem)] do trecho, já dividido em legendas que cabem (pedacos_da_legenda)."""
    return [(comeco, final, imagem) for comeco, final, _texto, imagem in pedacos_da_legenda(inicio, fim, texto, tempos)]


def letreiros_da_fala(legendas, duracao, subida=0):
    """
    [(imagem, início, fim, x, y)]: as legendas da fala no vídeo, cada uma até a seguinte começar,
    dentro da duração do vídeo; o trecho curto demais para ler (MINIMO_NA_TELA) sai. O pé de cada uma
    fica em PE_DA_LEGENDA (subida px mais alto: o vídeo com o Rótulo de IA, SUBIDA_COM_O_ROTULO_DE_IA),
    e ela vai centralizada entre ESQUERDA_DA_LEGENDA e DIREITA_DA_LEGENDA.
    legendas: [(início, fim, texto)], ou com os tempos de cada palavra no áudio no 4º lugar
    (legendas_no_tempo_da_fala).
    """
    pedacos = []
    for inicio, fim, texto, *tempos in sorted(legendas, key=lambda legenda: legenda[:2]):
        pedacos += _trechos_que_cabem(max(0.0, inicio), min(duracao, fim), texto, tempos[0] if tempos else None)
    letreiros = []
    for i, (inicio, fim, imagem) in enumerate(pedacos):
        if i + 1 < len(pedacos):
            fim = min(fim, pedacos[i + 1][0])
        if fim - inicio < MINIMO_NA_TELA:
            continue
        # A largura e a altura estão no cabeçalho do PNG (bytes 16 a 24).
        largura, altura = int.from_bytes(imagem[16:20], "big"), int.from_bytes(imagem[20:24], "big")
        x = ESQUERDA_DA_LEGENDA + (DIREITA_DA_LEGENDA - ESQUERDA_DA_LEGENDA - largura) // 2
        letreiros.append((imagem, round(inicio, 2), round(fim, 2), x, PE_DA_LEGENDA - subida - altura))
    return letreiros


def horarios_dos_textos(textos, duracao):
    """[(texto, início, fim)]: um de cada vez, cada um na sua parte do vídeo remontado; o que não cabe sai."""
    while textos and duracao / len(textos) < 1.5:
        textos = textos[:-1]
    if not textos:
        return []
    parte = duracao / len(textos)
    return [(texto, round(parte * i + 0.3, 2), round(min(parte * (i + 1) - 0.2, parte * i + 0.3 + SEGUNDOS_DE_CADA_TEXTO), 2))
            for i, texto in enumerate(textos)]


def _remontagem(video, original, falas):
    """(janelas com fala, trechos do vídeo remontado) pelo movimento do vídeo e pelas falas da IA."""
    com_fala = janelas_com_fala(falas, original, videos.som_por_janela(video, JANELA) if falas is None else ())
    return com_fala, ritmo(videos.movimento(video, QUADROS_DO_MOVIMENTO), original, com_fala=com_fala)


def _segundos_remontados(trechos):
    return sum((fim - inicio) / vel for inicio, fim, vel in trechos)


def _segundos_com_fala(com_fala, original):
    return sum(min(JANELA, original - i * JANELA) for i in com_fala)


def _lugar(lugar):
    """O lugar da IA, se é um que existe; sem ele, LUGAR_PADRAO."""
    return lugar if lugar in LUGARES_DOS_TEXTOS or lugar == SEM_LUGAR else LUGAR_PADRAO


def _letreiros(textos, lugar, duracao):
    """
    ([(imagem, início, fim, x, y)], textos que entraram): os textos ([(texto, fundo)], na
    ordem; vazios e repetidos saem) um de cada vez no vídeo remontado, no lugar escolhido.
    """
    fundos = {}
    for texto, fundo in textos:
        if texto and texto not in fundos:
            fundos[texto] = fundo
    if lugar == SEM_LUGAR:
        return [], []
    x_do_lugar, topo, largura_maxima, linhas_maximas = LUGARES_DOS_TEXTOS[lugar]
    letreiros, horarios = [], horarios_dos_textos(list(fundos), duracao)
    for texto, inicio, fim in horarios:
        if fundos[texto] == FUNDO_DA_CHAMADA:
            imagem = letreiro_da_chamada(texto, largura_maxima, linhas_maximas)
        else:
            imagem = letreiro(texto, fundos[texto], largura_maxima, linhas_maximas)
        # A largura está no cabeçalho do PNG (bytes 16 a 20).
        largura = int.from_bytes(imagem[16:20], "big")
        if x_do_lugar is None:
            x = (TELA[0] - largura) // 2
        else:
            x = TELA[0] + x_do_lugar - largura if x_do_lugar < 0 else x_do_lugar
        letreiros.append((imagem, inicio, fim, x, topo))
    return letreiros, [texto for texto, *_ in horarios]


def editar_2(video, foto, destino, nome="", vantagem="", chamada="", lugar=None, avisos=False, musica=None,
             capa=None, miniatura=True, outras_fotos=(), legendas=(), rotulo_de_ia=False, cor=None):
    """
    O Editor 2 em destino: o vídeo original, inteiro, na ordem e na velocidade dele, com os
    textos da tela por cima, e depois o Editor 1 (com avisos=True, a capa dos avisos da bebida
    alcoólica no lugar da foto; sem eles, a capa, quando vem). Nada é cortado nem acelerado:
    isso fica para as versões modificadas do exemplo (pedido do Rafael de 28/10/2026:
    DECISOES.md, Shopee Vídeo). lugar: onde vão os textos (um de LUGARES_DOS_TEXTOS, da IA;
    SEM_LUGAR = sem os textos; sem ela, LUGAR_PADRAO). Com a musica (caminho), ela é o som do
    vídeo inteiro. As legendas da fala ([(início, fim, texto)], P118) vão embaixo, à direita da seta.
    Com rotulo_de_ia=True, a legenda da fala, as setinhas e a moldura sobem com o cartão do app.
    Com a cor do produto (RGB, P159 2), a caixa do nome e da vantagem e a moldura da miniatura vão nela.
    Devolve (motivo, resumo {original, lugar, textos, legendas}): motivo "" quando deu certo.
    """
    original = videos.duracao(video)
    if not original:
        return "o vídeo não abre", {}
    return _editor_2_no_original(video, foto, destino, original, nome, vantagem, chamada, _lugar(lugar), avisos,
                                 musica, capa, miniatura, outras_fotos, legendas, rotulo_de_ia, cor)


def _editor_2_no_original(video, foto, destino, original, nome, vantagem, chamada, lugar, avisos=False,
                          musica=None, capa=None, miniatura=True, outras_fotos=(), legendas=(), rotulo_de_ia=False,
                          cor=None):
    """
    O Editor 2 em destino, com a duração do vídeo já medida (editar_2_e_versoes usa no 1º vídeo).
    Com as legendas da fala ([(início, fim, texto)], P118), elas vão embaixo, à direita da seta.
    """
    import tempfile
    caixa = caixa_dos_textos(cor)
    letreiros, textos = _letreiros([(nome, caixa), (vantagem, caixa), (chamada, FUNDO_DA_CHAMADA)], lugar, original)
    subida = SUBIDA_COM_O_ROTULO_DE_IA if rotulo_de_ia else 0
    da_fala = letreiros_da_fala(legendas, original, subida) if legendas else []
    letreiros += da_fala
    resumo = {"original": original, "lugar": lugar, "textos": textos, "miniatura": miniatura,
              "legendas": len(da_fala)}
    if not letreiros:
        return editar(video, foto, destino, avisos, musica, capa, miniatura, outras_fotos, rotulo_de_ia, cor=cor), resumo
    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(destino))) as pasta:
        corpo = os.path.join(pasta, "com_textos.mp4")
        # O vídeo inteiro numa parte só, na velocidade dele: só os textos entram por cima.
        motivo = videos.com_cortes_e_ritmo(video, [(0.0, original, 1.0)], corpo, letreiros, ESPERA_MAXIMA)
        if motivo:
            return motivo, resumo
        return editar(corpo, foto, destino, avisos, musica, capa, miniatura, outras_fotos, rotulo_de_ia, cor=cor), resumo


# Como saiu o vídeo que vai ao ar, para o registro (textos fixos: o checkup conta por eles).
COM_LEGENDAS = "editado com legendas (Editor 2)"
SEM_LEGENDAS_NA_TELA = "editado com o Editor 2, sem legendas na tela"
SO_COM_O_EDITOR_1 = "editado sem legendas (Editor 1)"
COM_OS_AVISOS = ", com os avisos"
COM_A_CHAMADA = ", com a chamada na capa"
COM_MUSICA = ", com música de fundo"
SEM_A_MINIATURA = ", sem a nossa miniatura"
COM_A_MINIATURA_MENOR = ", com a miniatura menor"
COM_A_MINIATURA_ALTERNADA = ", com a miniatura alternada"
COM_AS_LEGENDAS_DA_FALA = ", com as legendas da fala"
# O porquê, no detalhe do registro, quando o Editor 2 saiu sem algum texto.
SEM_LUGAR_LIVRE = "a IA não viu lugar livre do produto e do rosto para os textos"
TEXTO_JA_NO_VIDEO = "o vídeo já tem texto próprio na tela"
SEM_OS_TEXTOS_DA_IA = "a IA não deu o nome, a vantagem e a chamada"


def editar_para_postar(video, foto, destino, produto="", avisos=False, outras_fotos=(), rotulo_de_ia=False,
                       anotar=None):
    """
    O vídeo que vai ao ar (o rascunho do robô e o vídeo do modo assistente) em destino: o
    vídeo original, sem cortes, com o Editor 2: o nome, a vantagem e a chamada para o produto
    que a IA escreve vendo o vídeo (produto: o nome do produto para ela; sem ele, o vídeo vai
    sem os textos), sem o preço (P80). As versões modificadas ficam só no exemplo. Se o Editor
    2 não sai, o vídeo vai com o Editor 1 (foto, miniatura e seta, sem legendas). Escolhas do
    Rafael (28/10/2026, P50 e P51): DECISOES.md, Shopee Vídeo. Com avisos=True (bebida
    alcoólica), a capa dos avisos abre o vídeo nos dois.
    Devolve (motivo, como, detalhe): motivo "" quando o vídeo saiu editado; como, o jeito
    (COM_LEGENDAS, SEM_LEGENDAS_NA_TELA ou SO_COM_O_EDITOR_1, mais COM_OS_AVISOS); detalhe,
    o porquê fixo de faltar algum texto ou o Editor 2 ("" quando não falta nada). O vídeo sem
    som ganha a música de fundo da vez (P55), e o jeito termina com COM_MUSICA. Com a capa com
    chamada ligada (P76), a frase curta da IA para a capa (P106; sem ela, a vantagem) vai na capa
    de todos os vídeos (P100), e o jeito leva COM_A_CHAMADA. Com as outras_fotos (bytes das
    outras fotos diferentes dos produtos do post, as que cabem: fotos_que_cabem), a miniatura
    troca entre a foto e cada uma delas (P103), e o jeito leva COM_A_MINIATURA_ALTERNADA.
    A capa com a frase abre o vídeo, no rascunho do robô e no modo assistente (P125). Com
    rotulo_de_ia=True (o vídeo vai com o Rótulo de IA ligado), a moldura do cartão, as setinhas e a legenda da fala sobem com o
    cartão do app (SUBIDA_COM_O_ROTULO_DE_IA). Com a cor principal do produto, que a IA diz com os
    textos (P159 2), o fio e a faixa da capa, a caixa do nome e da vantagem e a moldura da
    miniatura vão nela; anotar (dict) recebe em "cor" o nome dela ("" com as cores de sempre), que
    o robô guarda no rascunho para conferir a faixa no post. Escolhas do Rafael: DECISOES.md,
    Shopee Vídeo.
    """
    if not foto:
        # Sem a foto do anúncio nenhum dos dois sai: o motivo é o do Editor 1, sem gastar a IA.
        return editar(video, foto, destino, avisos), SO_COM_O_EDITOR_1 + (COM_OS_AVISOS if avisos else ""), ""
    musica = _caminho(musicas_de_fundo(video)[0])
    textos = textos_da_tela(video, produto) if produto else {}
    # A cor do produto no lugar do laranja e do preto (P159 2); o registro conta cada uma.
    cor = cor_do_produto(textos.get("cor"))
    if textos:
        registro_processos.registrar("shopee_video", PROCESSO_DA_COR, textos.get("cor") if cor else COM_AS_CORES_DE_SEMPRE,
                                     "" if cor else (textos.get("cor") or "a IA não disse a cor"), ok=None)
    if anotar is not None:
        anotar["cor"] = textos.get("cor", "") if cor else ""
    # Sem a frase da capa, o nome e a vantagem da IA, a capa fica a de antes; a bebida alcoólica, com a
    # dos avisos. A capa com chamada vai em todos os vídeos, menos na bebida alcoólica, que abre
    # com a capa dos avisos. Escolha do Rafael (30/10, P100): DECISOES.md, Shopee Vídeo.
    frase = frase_da_capa(textos)
    capa, foto_da_capa = None, foto
    if capa_ligada() and not avisos and frase:
        # Quantas capas saem com a frase curta (P122), quantas só na 2ª vez e quantas com o
        # nome (P131) ou a vantagem, por falta dela, e por quê.
        resultado, detalhe, ok = registro_da_frase(textos, frase)
        registro_processos.registrar("shopee_video", PROCESSO_DA_FRASE_DA_CAPA, resultado, detalhe, ok=ok)
        # A foto da capa sem as letras do anúncio (P160 2).
        foto_da_capa, letras = foto_sem_letras(foto)
        registro_processos.registrar("shopee_video", PROCESSO_DAS_LETRAS_DA_FOTO, letras,
                                     ok={SEM_LETRAS: True, LETRAS_CORTADAS: True, LETRAS_NO_PRODUTO: None}.get(letras, False))
        capa = _capa_da_vez(foto_da_capa, frase, cor=cor)
    abertura = capa
    if capa:
        # O 1º quadro, que o app usa como capa da grade, vai com a capa da grade; o resto da
        # abertura, com a do vídeo aberto (P129). Sem esta, a da grade fica na abertura toda.
        no_video = _capa_da_vez(foto_da_capa, frase, no_video=True, cor=cor)
        if no_video:
            abertura = (capa, no_video)
    chamada = COM_A_CHAMADA if capa else ""
    # Sem a nossa miniatura quando o criador já pôs coisa no canto dela (P81); menor quando a
    # coisa dele fica logo abaixo do canto (P97).
    miniatura = miniatura_no_video(textos)
    if textos.get("canto_filmado"):
        registro_processos.registrar("shopee_video", PROCESSO_DO_CANTO, CANTO_FILMADO,
                                     f"a 1ª resposta: {textos['canto_filmado']}", ok=True)
    if miniatura < LARGURA_DA_MINIATURA:
        registro_processos.registrar("shopee_video", PROCESSO_DO_CANTO, "menor" if miniatura else "de fora",
                                     por_que_a_miniatura(textos))
    avisado = ((COM_OS_AVISOS if avisos else "") + chamada + (COM_MUSICA if musica else "")
               + (SEM_A_MINIATURA if not miniatura
                  else COM_A_MINIATURA_MENOR if miniatura < LARGURA_DA_MINIATURA else "")
               + (COM_A_MINIATURA_ALTERNADA if outras_fotos and miniatura else ""))
    # As legendas da fala (P118): só o que alguém fala, num vídeo que ainda não a tem escrita na tela,
    # no tempo do áudio, palavra por palavra.
    legendas, sem_legendas = legendas_da_fala(textos) if produto else ([], SEM_AS_LEGENDAS_DA_IA)
    legendas, tempo_das_legendas, detalhe_do_tempo = legendas_no_tempo(video, legendas)
    if tempo_das_legendas:
        registro_processos.registrar("shopee_video", PROCESSO_DO_TEMPO_DAS_LEGENDAS, tempo_das_legendas,
                                     detalhe_do_tempo, ok=tempo_das_legendas == PELO_AUDIO)
    try:
        motivo_2, resumo = editar_2(video, foto, destino, textos.get("nome", ""), textos.get("vantagem", ""),
                                    textos.get("chamada", ""), lugar_dos_textos(textos), avisos, musica, abertura,
                                    miniatura, outras_fotos, legendas, rotulo_de_ia, cor=cor)
    except Exception as e:
        # O erro no meio do Editor 2 também deixa o vídeo ir com o Editor 1.
        motivo_2, resumo = f"erro ({type(e).__name__})", {}
    if not motivo_2:
        postas = resumo.get("legendas", 0)
        # Com as palavras e os segundos de fala, o checkup vê se a IA resume a fala (poucas palavras
        # por segundo): a legenda é a fala inteira (pedido do Rafael, 02/11).
        palavras = sum(len(texto.split()) for _inicio, _fim, texto, *_tempos in legendas)
        segundos = sum(max(0.0, fim - inicio) for inicio, fim, *_resto in legendas)
        registro_processos.registrar("shopee_video", PROCESSO_DAS_LEGENDAS, "postas" if postas else "sem as legendas",
                                     f"{postas} trecho(s), {palavras} palavra(s) em {segundos:.0f} s de fala"
                                     if postas else sem_legendas or "nenhum trecho cabe", ok=True if postas else None)
        avisado += COM_AS_LEGENDAS_DA_FALA if postas else ""
        detalhe = ""
        if textos.get("texto_no_video"):
            # Com a parte do tempo em que o texto do criador fica na tela (P52: mais da metade).
            detalhe = TEXTO_JA_NO_VIDEO + (f" ({textos['parte_com_texto']:.0%} do tempo)"
                                           if "parte_com_texto" in textos else "")
        elif resumo.get("lugar") == SEM_LUGAR:
            detalhe = SEM_LUGAR_LIVRE
        elif not (textos.get("nome") or textos.get("vantagem") or textos.get("chamada")):
            detalhe = SEM_OS_TEXTOS_DA_IA
        return "", (COM_LEGENDAS if resumo.get("textos") else SEM_LEGENDAS_NA_TELA) + avisado, detalhe
    return (editar(video, foto, destino, avisos, musica, abertura, miniatura, outras_fotos, rotulo_de_ia, cor=cor),
            SO_COM_O_EDITOR_1 + avisado, f"o Editor 2 não saiu: {motivo_2}")


def _fontes_do_exemplo():
    """A fonte que o robô usa para postar primeiro, depois as outras."""
    fonte = (db.ler_config("shopee_video", {}) or {}).get("fonte", assistente.FONTE_PADRAO)
    return (fonte,) + tuple(f for f in FONTES_COM_EDICAO if f != fonte)


def _videos_do_exemplo(pular):
    """
    (id, arquivo, link) dos próximos vídeos que o robô pegaria para postar (os ainda não
    usados, do mais novo para o mais velho), até VIDEOS_POR_FONTE de cada fonte, sem os de
    pular.
    """
    achados = []
    for fonte in _fontes_do_exemplo():
        da_fonte = 0
        for id_video, arquivo, link, _ in assistente.candidatos_nao_usados(fonte):
            if da_fonte >= VIDEOS_POR_FONTE:
                break
            if (id_video not in pular and arquivo and link and os.path.exists(arquivo)
                    and not arquivo.lower().endswith(assistente.EXTENSOES_DE_IMAGEM)):
                achados.append((id_video, arquivo, link))
                da_fonte += 1
    return achados


def _lembrar(lista, id_video, limite, recomecar=False):
    """Põe o vídeo na lista (ids ou sem_foto) da chave dos exemplos; recomecar zera a lista antes."""
    def alterar(dados):
        anteriores = [] if recomecar else dados.get(lista, [])
        dados[lista] = (anteriores + [id_video])[-limite:]
    db.atualizar_config(CHAVE_EXEMPLOS, alterar)


def _exemplo(lista, editar_um):
    """
    O próximo vídeo que o robô pegaria para postar, editado por editar_um(arquivo, link,
    foto) → (motivo, extra), sem postar e sem gastar o vídeo. Cada chamada pega um vídeo que
    o exemplo deste editor (a `lista` da chave dos exemplos) ainda não mostrou; sem nenhum
    novo com a foto do anúncio, recomeça pelos já mostrados. Devolve (nome do produto, "",
    extra) quando deu certo, ou (None, motivo, extra).
    """
    dados = db.ler_config(CHAVE_EXEMPLOS, {}) or {}
    mostrados, sem_foto = set(dados.get(lista, [])), set(dados.get("sem_foto", []))
    algum_sem_foto = False
    for recomecar in (False, True):
        pular = sem_foto if recomecar else mostrados | sem_foto
        for id_video, arquivo, link in _videos_do_exemplo(pular):
            foto = ps.foto_do_produto({"link": link})
            if not foto:
                algum_sem_foto = True
                sem_foto.add(id_video)
                _lembrar("sem_foto", id_video, SEM_FOTO_LEMBRADOS)
                continue
            motivo, extra = editar_um(arquivo, link, foto)
            if motivo:
                return None, motivo, extra
            _lembrar(lista, id_video, EXEMPLOS_LEMBRADOS, recomecar=recomecar)
            return ps.nome_do_produto({"link": link}) or "produto do link", "", extra
        if not mostrados:
            break
    if algum_sem_foto or _videos_do_exemplo(set()):
        return None, ("nenhum dos próximos vídeos tem a foto do anúncio na API agora (os de Ver Produtos, "
                      "com vários produtos, não têm uma foto só)"), None
    return None, "nenhum vídeo com o arquivo e o link no servidor agora", None


def _produto_do_link(link):
    """O produto do link pela API de afiliado ({nome, preco, ...}); {} quando ela não diz."""
    import asyncio
    try:
        produtos, _ = asyncio.run(assistente.produtos_do_link(link))
    except Exception:
        return {}
    return produtos[0] if produtos else {}


# --- Os exemplos dos Editores 1 e 2: o vídeo completo e as versões ---
# O exemplo de cada editor entrega, de um vídeo, o vídeo completo e até 2 versões diferentes
# de verdade (pedido do Rafael de 27/10/2026, depois do que a Rafaela contou no grupo sobre as
# ferramentas que "multiplicam" um vídeo: DECISOES.md, Shopee Vídeo). O 1º é o vídeo original,
# inteiro e sem cortes, só com as edições do Editor 1 (sem legendas) ou do Editor 2 (com
# legendas), como vai ao ar; depois vêm as versões modificadas. Cada versão abre com um
# momento diferente do vídeo (o gancho), que a IA aponta com a vantagem que ele mostra, e
# segue dali; o que vinha antes do gancho vai para o fim. E cada uma tem um tamanho: a 1ª uns
# 3/4 do completo e a 2ª a mais curta (escolha do Rafael, P49: nas versões do conjunto de
# jardim, todas voltavam ao começo do vídeo depois do gancho e terminavam iguais, com o mesmo
# tamanho). Assim, em nenhum segundo dois vídeos mostram a mesma parte. As versões dos dois
# editores são remontadas (sem as partes paradas, com o ritmo; o Editor 1 no mesmo padrão do
# Editor 2, só sem legendas, pedido do Rafael de 28/10); as do Editor 2 têm os textos na tela
# (a vantagem do gancho e uma chamada diferente no fim). Não são cópias quase iguais para
# a Shopee não reconhecer o mesmo vídeo (a regra 9 pune mensagens repetitivas): versão só sai
# com um gancho longe do começo do vídeo e dos das outras, e o vídeo curto, ou com fala do
# começo ao fim, rende menos versões.
VERSOES_POR_VIDEO = 3
# O tamanho de cada vídeo entregue, em fração do completo, na ordem (o completo e as versões);
# nenhum fica com menos de MINIMO_DO_REMONTADO. O que sai é o fim da versão, nunca o meio de
# uma fala (P45).
TAMANHO_DAS_VERSOES = (1.0, 0.75, 0.5)
# O gancho tem pelo menos isto do vídeo original e não tem fala: a fala fica inteira e na
# ordem (P45). O começo de uma versão fica a pelo menos ENTRE_VERSOES do começo do vídeo (onde
# o completo começa) e das outras versões, no vídeo original, contando a volta do fim ao
# começo: mais perto, os dois mostram quase a mesma coisa o tempo todo.
GANCHO_MINIMO = 1.0
ENTRE_VERSOES = 3.0
# Pedaço que sobra menor que isto, ao dividir um trecho no começo do gancho ou no corte do fim,
# sai (emenda curta demais só soluça).
PEDACO_MINIMO = 0.2

PROMPT_DAS_VERSOES = (
    "Você vai ver um vídeo curto de um produto vendido na Shopee: {nome}.\n"
    "Vamos entregar o vídeo completo e versões diferentes dele: cada versão abre com um momento diferente e "
    "destaca uma vantagem diferente do produto. Em português do Brasil, escreva:\n"
    + _NOME_NO_PROMPT
    + "- \"vantagem\": uma vantagem do produto que o próprio vídeo mostra, para o vídeo completo, diferente das "
    f"vantagens das versões, até {MAXIMO_DA_VANTAGEM} caracteres;\n"
    + _CHAMADA_NO_PROMPT.replace("o fim do vídeo,", "o fim do vídeo completo, diferente das chamadas das versões,")
    + "- \"versoes\": até 3, cada uma com \"vantagem\" (uma vantagem do produto que o vídeo mostra naquele "
    f"momento, até {MAXIMO_DA_VANTAGEM} caracteres), \"inicio\" e \"fim\" (os segundos do vídeo em que ela "
    "aparece melhor, de 1 a 4 segundos, sem ninguém falando, com pelo menos "
    f"{ENTRE_VERSOES:.0f} segundos entre o começo do vídeo e o começo de um momento, e entre o começo de um "
    "momento e o de outro) e \"chamada\" (uma frase curta para o fim do "
    f"vídeo, chamando para o produto anexado aqui embaixo, até {MAXIMO_DA_CHAMADA} caracteres, diferente em cada "
    "versão, sem mandar para fora da Shopee). Só ponha uma versão com um momento e uma vantagem que as outras "
    "não têm: se o vídeo mostra uma coisa só, uma versão só.\n"
    + _REGRAS_NO_PROMPT + _COR_NO_PROMPT + _FALAS_E_LUGAR_NO_PROMPT
    + "Responda só com o JSON: {{\"nome\": \"...\", \"vantagem\": \"...\", \"chamada\": \"...\", \"cor\": \"...\", "
    "\"versoes\": [{{\"vantagem\": \"...\", "
    "\"inicio\": 0.0, \"fim\": 0.0, \"chamada\": \"...\"}}], \"falas\": [[0.0, 0.0]], \"lugar\": \"alto\", "
    "\"textos_do_video\": [], \"canto_ocupado\": false, \"por_cima_no_alto\": [], \"legendas\": [], "
    "\"legenda_no_video\": false}}"
)


def textos_das_versoes(video, nome):
    """
    {"nome", "vantagem" e "chamada" (as do vídeo completo), "lugar", "falas", "versoes":
    [{"vantagem", "chamada", "inicio", "fim"}]} que a IA escreveu vendo o vídeo, só o que veio
    certo; {} quando ela não respondeu.
    """
    dados = _resposta_da_ia(video, PROMPT_DAS_VERSOES.format(nome=nome))
    textos = _vantagem_e_chamada(dados, _nome_lugar_e_falas(dados, _duracao_para_os_trechos(video, dados)))
    versoes = []
    for bruta in dados.get("versoes") if isinstance(dados.get("versoes"), list) else []:
        if not isinstance(bruta, dict):
            continue
        try:
            inicio, fim = float(bruta.get("inicio")), float(bruta.get("fim"))
        except (TypeError, ValueError):
            continue
        vantagem = _texto_certo(str(bruta.get("vantagem") or ""), MAXIMO_DA_VANTAGEM)
        if vantagem and fim > inicio >= 0:
            versoes.append({"vantagem": vantagem, "inicio": inicio, "fim": fim,
                            "chamada": _texto_certo(str(bruta.get("chamada") or ""), MAXIMO_DA_CHAMADA)})
    if versoes:
        textos["versoes"] = versoes[:VERSOES_POR_VIDEO]
    return _revisar_ortografia(textos)


def planejar_versoes(trechos, ganchos, com_fala, inteira=None):
    """
    As versões do vídeo, além do completo, [{"gancho": n do gancho em ganchos, "trechos",
    "curta"}], no máximo VERSOES_POR_VIDEO - 1: cada uma abre no seu gancho ((início, fim) no
    vídeo original) e segue dali até o fim dos trechos, e o que vinha antes do gancho vai para
    o fim. A n-ésima tem até uns TAMANHO_DAS_VERSOES[n] do completo (inteira, em segundos;
    sem ela, os trechos inteiros), nunca menos que MINIMO_DO_REMONTADO ("curta" quando saiu o
    fim dela). Gancho com fala, menor que
    GANCHO_MINIMO dentro dos trechos ou que começa a menos de ENTRE_VERSOES do começo do vídeo
    ou de outra versão fica de fora; sem nenhum, [] (só o completo).
    """
    guardado = sum(b - a for a, b, _ in trechos)
    inteira = inteira or _segundos_remontados(trechos)
    # O completo começa no começo do vídeo.
    versoes, comecos = [], [0.0]
    for n, (inicio, fim) in enumerate(ganchos):
        if len(versoes) >= VERSOES_POR_VIDEO - 1:
            break
        if any(i * JANELA < fim and (i + 1) * JANELA > inicio for i in com_fala):
            continue
        if sum(max(0.0, min(b, fim) - max(a, inicio)) for a, b, _ in trechos) < GANCHO_MINIMO:
            continue
        # Onde a versão começa, em segundos do vídeo original que ficaram nos trechos; a
        # distância conta a volta do fim ao começo, porque cada versão segue até o fim e
        # recomeça do começo.
        comeco = sum(max(0.0, min(b, inicio) - a) for a, b, _ in trechos)
        if any(min(abs(comeco - outro), guardado - abs(comeco - outro)) < ENTRE_VERSOES for outro in comecos):
            continue
        depois, antes = [], []
        for a, b, v in trechos:
            if inicio <= a:
                depois.append((a, b, v))
            elif inicio >= b:
                antes.append((a, b, v))
            else:
                if b - inicio >= PEDACO_MINIMO:
                    depois.append((inicio, b, v))
                if inicio - a >= PEDACO_MINIMO:
                    antes.append((a, inicio, v))
        girada = depois + antes
        alvo = max(MINIMO_DO_REMONTADO, inteira * TAMANHO_DAS_VERSOES[len(versoes) + 1])
        encurtada = _sem_o_fim(girada, alvo, com_fala)
        curta = _segundos_remontados(encurtada) < _segundos_remontados(girada) - 0.5
        comecos.append(comeco)
        versoes.append({"gancho": n, "trechos": encurtada if curta else girada, "curta": curta})
    return versoes


def _sem_o_fim(trechos, alvo, com_fala):
    """Os trechos do começo até dar alvo segundos remontados; o corte não cai no meio de uma fala."""
    ficam, tempo = [], 0.0
    for a, b, v in trechos:
        if tempo + (b - a) / v <= alvo + 1e-6:
            ficam.append((a, b, v))
            tempo += (b - a) / v
            continue
        corte = a + (alvo - tempo) * v
        # A fala que o corte pegaria no meio fica inteira: o corte vai para o fim dela.
        while corte < b and int(corte // JANELA) in com_fala:
            corte = (int(corte // JANELA) + 1) * JANELA
        if b - corte < PEDACO_MINIMO:
            corte = b
        if corte - a >= PEDACO_MINIMO:
            ficam.append((a, corte, v))
        break
    return ficam


def arquivo_da_versao(destino, numero):
    """O arquivo do vídeo entregue (1 o completo; 2 e 3 as versões) ao lado de destino: exemplo.mp4 → exemplo_2.mp4."""
    raiz, extensao = os.path.splitext(destino)
    return f"{raiz}_{numero}{extensao}"


def _resumo_do_completo(arquivo, remontado, textos=(), vantagem="", musica=None):
    return {"arquivo": arquivo, "remontado": remontado, "curta": False, "textos": list(textos),
            "vantagem": vantagem, "gancho": None, "musica": musica[0] if musica else ""}


def _resumo_da_remontagem(trechos, original, com_fala):
    """O que a remontagem das versões muda no vídeo original (números, para a legenda)."""
    return {"cortado": original - sum(fim - inicio for inicio, fim, _ in trechos),
            "acelerados": sum(1 for *_, v in trechos if v > 1),
            "camera_lenta": sum(1 for *_, v in trechos if v < 1),
            "com_fala": _segundos_com_fala(com_fala, original)}


def _resumo_da_versao(arquivo, plano, da_ia, textos=(), musica=None):
    return {"arquivo": arquivo, "remontado": _segundos_remontados(plano["trechos"]), "curta": plano["curta"],
            "textos": list(textos), "vantagem": da_ia.get("vantagem", ""), "gancho": (da_ia["inicio"], da_ia["fim"]),
            "musica": musica[0] if musica else ""}


def _versoes_modificadas(video, foto, destino, planos, versoes_da_ia, resumo, textos_da_versao, musicas,
                         miniatura=True, cor=None):
    """
    As versões modificadas (planos de planejar_versoes) em arquivo_da_versao(destino, 2, 3...):
    cada uma remontada com os trechos dela, com os letreiros de textos_da_versao(plano, da_ia)
    → (letreiros, textos), e o Editor 1 por cima (com a miniatura ou sem ela, como o original),
    com a sua música (musicas, uma por versão, None no vídeo com som); cada uma entra em
    resumo["versoes"]. Devolve (motivo, resumo): motivo "" quando todas saíram.
    """
    import tempfile
    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(destino))) as pasta:
        for numero, (plano, musica) in enumerate(zip(planos, musicas), 2):
            da_ia = versoes_da_ia[plano["gancho"]]
            letreiros, textos = textos_da_versao(plano, da_ia)
            arquivo = arquivo_da_versao(destino, numero)
            resumo["versoes"].append(_resumo_da_versao(arquivo, plano, da_ia, textos, musica))
            corpo = os.path.join(pasta, f"remontado_{numero}.mp4")
            motivo = videos.com_cortes_e_ritmo(video, plano["trechos"], corpo, letreiros, ESPERA_MAXIMA)
            if not motivo:
                motivo = editar(corpo, foto, arquivo, musica=_caminho(musica), miniatura=miniatura, cor=cor)
            if motivo:
                return motivo, resumo
    return "", resumo


def editar_1_e_versoes(video, foto, destino, versoes_da_ia=(), falas=None, miniatura=True):
    """
    O Editor 1 e as versões em arquivo_da_versao(destino, n): o 1º é o vídeo original, sem
    cortes, com o Editor 1; os seguintes são as versões modificadas, remontadas como as do
    Editor 2 (sem as partes paradas, com o ritmo), mas sem textos (pedido do Rafael, 28/10:
    DECISOES.md, Shopee Vídeo). versoes_da_ia = [{"vantagem", "inicio", "fim", ...}].
    Devolve (motivo, resumo): motivo "" quando todos saíram; o que a remontagem muda nas
    versões fica em resumo["remontagem"].
    """
    original = videos.duracao(video)
    if not original:
        return "o vídeo não abre", {}
    com_fala, trechos = _remontagem(video, original, falas)
    planos = planejar_versoes(trechos, [(v["inicio"], v["fim"]) for v in versoes_da_ia], com_fala, original)
    musicas = musicas_de_fundo(video, 1 + len(planos))
    completo = arquivo_da_versao(destino, 1)
    resumo = {"original": original, "inteiro": original, "com_fala": _segundos_com_fala(com_fala, original),
              "remontagem": _resumo_da_remontagem(trechos, original, com_fala), "miniatura": miniatura,
              "versoes": [_resumo_do_completo(completo, original, musica=musicas[0])]}
    motivo = editar(video, foto, completo, musica=_caminho(musicas[0]), miniatura=miniatura)
    if motivo:
        return motivo, resumo
    return _versoes_modificadas(video, foto, destino, planos, versoes_da_ia, resumo, lambda plano, da_ia: ((), []),
                                musicas[1:], miniatura)


def editar_2_e_versoes(video, foto, destino, nome="", vantagem="", versoes_da_ia=(), chamada="", falas=None,
                       lugar=None, miniatura=True, legendas=(), cor=None):
    """
    O Editor 2 e as versões em arquivo_da_versao(destino, n): o 1º é o vídeo original, sem
    cortes, com o Editor 2 (o nome, a vantagem e a chamada), como vai ao ar; os seguintes são as
    versões modificadas (planejar_versoes), cada uma remontada (sem as partes paradas, com o
    ritmo), com os seus textos (a vantagem do gancho, o nome e a chamada da versão, nessa ordem)
    e com o Editor 1 por cima. versoes_da_ia = [{"vantagem", "chamada", "inicio", "fim"}]. Com a cor
    do produto (RGB, P159 2), a caixa do nome e da vantagem e a moldura da miniatura vão nela, como
    no vídeo que vai ao ar. Devolve (motivo, resumo): motivo "" quando todos saíram; o que a
    remontagem muda nas versões fica em resumo["remontagem"].
    """
    original = videos.duracao(video)
    if not original:
        return "o vídeo não abre", {}
    com_fala, trechos = _remontagem(video, original, falas)
    lugar = _lugar(lugar)
    caixa = caixa_dos_textos(cor)
    planos = planejar_versoes(trechos, [(v["inicio"], v["fim"]) for v in versoes_da_ia], com_fala, original)
    musicas = musicas_de_fundo(video, 1 + len(planos))
    completo = arquivo_da_versao(destino, 1)
    motivo, do_completo = _editor_2_no_original(video, foto, completo, original, nome, vantagem, chamada, lugar,
                                                musica=_caminho(musicas[0]), miniatura=miniatura, legendas=legendas,
                                                cor=cor)
    resumo = {"original": original, "inteiro": original, "lugar": lugar, "miniatura": miniatura,
              "com_fala": _segundos_com_fala(com_fala, original),
              "remontagem": _resumo_da_remontagem(trechos, original, com_fala),
              "versoes": [_resumo_do_completo(completo, original, do_completo["textos"], vantagem, musicas[0])]}
    if motivo:
        return motivo, resumo
    return _versoes_modificadas(video, foto, destino, planos, versoes_da_ia, resumo, lambda plano, da_ia: _letreiros(
        [(da_ia.get("vantagem", ""), caixa), (nome, caixa), (da_ia.get("chamada", ""), FUNDO_DA_CHAMADA)],
        lugar, _segundos_remontados(plano["trechos"])), musicas[1:], miniatura, cor)


def _exemplo_das_versoes(destino, lista, editar_versoes):
    """
    O exemplo de um editor de versões: o próximo vídeo que o robô pegaria, com os textos que
    a IA escreveu vendo o vídeo e o produto da API, editado por editar_versoes(arquivo, foto,
    textos, produto) → (motivo, resumo).
    """
    def editar_um(arquivo, link, foto):
        produto = _produto_do_link(link)
        textos = textos_das_versoes(arquivo, produto["nome"]) if produto.get("nome") else {}
        motivo, resumo = editar_versoes(arquivo, foto, textos, produto)
        resumo["lugar_da_ia"] = "lugar" in textos
        resumo["texto_no_video"] = bool(textos.get("texto_no_video"))
        resumo["miniatura"] = miniatura_no_video(textos)
        resumo["textos_da_ia"] = bool(textos.get("nome") or textos.get("vantagem") or textos.get("chamada"))
        resumo["versoes_da_ia"] = len(textos.get("versoes", []))
        return motivo, resumo

    return _exemplo(lista, editar_um)


def exemplo_editor_1(destino):
    """
    O exemplo do Editor 1 (sem legendas): o completo e as versões em arquivo_da_versao(destino,
    n) (a lista em resumo["versoes"]). Tem a lista própria dos já mostrados. Devolve (nome do
    produto, "", resumo) quando deu certo, ou (None, motivo, resumo ou None).
    """
    return _exemplo_das_versoes(destino, "ids", lambda arquivo, foto, textos, produto: editar_1_e_versoes(
        arquivo, foto, destino, textos.get("versoes", []), textos.get("falas"), miniatura_no_video(textos)))


def exemplo_editor_2(destino):
    """
    O exemplo do Editor 2 (com legendas), como o do Editor 1, com os textos na tela (o nome, a
    vantagem e a chamada) e, no vídeo completo, as legendas da fala, como vai ao ar (P118).
    """
    return _exemplo_das_versoes(destino, "ids_2", lambda arquivo, foto, textos, produto: editar_2_e_versoes(
        arquivo, foto, destino, textos.get("nome", ""), textos.get("vantagem", ""), textos.get("versoes", []),
        textos.get("chamada", ""), textos.get("falas"), lugar_dos_textos(textos), miniatura_no_video(textos),
        legendas_no_tempo(arquivo, legendas_da_fala(textos)[0])[0], cor=cor_do_produto(textos.get("cor"))))


def exemplo_capa():
    """
    O exemplo da capa com chamada (P76), com o próximo vídeo que o robô pegaria: a frase curta
    que a IA escreve vendo o vídeo (P106; sem ela, a vantagem), na capa. Tem a lista própria dos
    já mostrados. Devolve (nome do produto, "", {"capa", "grade", "video", "chamada"}) quando deu
    certo (as imagens em PNG: a capa inteira do 1º quadro, o pedaço que a grade do perfil mostra e
    o que o app mostra do vídeo aberto no resto da abertura, P129), ou (None, motivo, None).
    """
    def editar_um(arquivo, link, foto):
        produto = _produto_do_link(link)
        textos = textos_da_tela(arquivo, produto["nome"]) if produto.get("nome") else {}
        frase = frase_da_capa(textos)
        if not frase:
            return "a IA não escreveu a frase da capa, o nome nem a vantagem do produto deste vídeo", None
        # A foto sem as letras do anúncio e a cor do produto, como no vídeo que vai ao ar (P160 2 e P159 2).
        foto = foto_sem_letras(foto)[0]
        cor = cor_do_produto(textos.get("cor"))
        capa = capa_com_chamada(foto, frase, cor=cor)
        if not capa:
            return "a capa com a chamada não saiu", None
        exemplo = {"capa": capa, "grade": recorte_da_grade(capa), "chamada": frase}
        no_video = capa_com_chamada(foto, frase, no_video=True, cor=cor)
        if no_video:
            exemplo["video"] = recorte_do_video_aberto(no_video)
        return "", exemplo

    return _exemplo("ids_capa", editar_um)

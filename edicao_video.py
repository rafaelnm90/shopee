#!/usr/bin/env python3
"""
A edição dos vídeos da Shopee Vídeo como o Rafael faz à mão no LumaFusion: a foto do
anúncio do produto nos primeiros segundos e, no vídeo inteiro, uma miniatura dela no canto
de cima à direita e a seta vermelha dele embaixo à esquerda (a montagem fica no
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
# Quando a foto do 1º produto mostra o produto de outro jeito que o vídeo, a miniatura troca entre
# ela e a do produto do post mais parecida com o vídeo, cada uma este tanto de segundos.
# Escolha do Rafael (30/10, P101): DECISOES.md, Shopee Vídeo.
SEGUNDOS_DE_CADA_FOTO = 3
# A miniatura e a seta onde o Rafael as põe no LumaFusion (vídeo de 25/10), no vídeo de
# 720x1280. A miniatura: 25% da largura, com o centro a 80% da largura e 10% da altura
# (posição X 60 e Y -80 no LumaFusion), do começo do vídeo até o fim.
LARGURA_DA_MINIATURA = 180
CENTRO_DA_MINIATURA = (576, 128)
# O canto de cima à direita da miniatura (x 666, y 38) fica sempre no mesmo lugar: menor, ela
# encolhe para dentro dele. Escolha do Rafael (29/10, P97): DECISOES.md, Shopee Vídeo.
CANTO_DA_MINIATURA = (CENTRO_DA_MINIATURA[0] + LARGURA_DA_MINIATURA // 2,
                      CENTRO_DA_MINIATURA[1] - LARGURA_DA_MINIATURA // 2)
# A seta é a do Rafael (o arquivo Seta_da_Shopee que ele usa no LumaFusion), com o fundo
# preto tirado: só o pedaço com a seta, já no tamanho dele (62,9%, posição X -23), perto do
# canto de baixo à esquerda, inteira logo acima do cartão do produto que o app mostra e
# apontando para ele (escolha do Rafael, P71: na posição do LumaFusion, o cartão tampava a
# ponta). Ela começa logo depois da foto, já se desenhando quando o vídeo começa, e pulsa: o
# arquivo guarda a entrada e um pulso (quadros 72 a 101, 1,2 s), que se repete até o fim do
# vídeo. Pedido do Rafael (25/10): DECISOES.md, Shopee Vídeo.
SETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "midia", "seta_da_shopee.apng")
CENTRO_DA_SETA = (142, 796)
# O que o app da Shopee mostra do vídeo de 720x1280 num celular de tela 20:9, medido no
# celular do Rafael (vídeo de 28/10, P71): ele enche a tela e corta uns 47 px de cada lado
# (fica visível de x 47 a 673), a barra de busca do alto vai até y 140 e o cartão do produto
# embaixo começa em y 870. A seta e os textos ficam dentro disso (o tests/test_edicao_video.py
# confere).
VISIVEL_NO_APP = (47, 673)
FIM_DA_BARRA_DE_BUSCA = 140
COMECO_DO_CARTAO_DO_PRODUTO = 870
PULSO_DA_SETA = (72, 30)
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


# A capa com chamada: a foto do anúncio no fundo preto, um pouco menor, e acima dela a
# vantagem que o vídeo mostra, em letras grandes (a frase que a IA escreve para as legendas
# do Editor 2: sem marca, sem preço e sem promoção, regras 9, 13 e 14). Tudo dentro do que a
# grade do perfil mostra da capa (o corte do meio, medido no print do Rafael de 29/10: de y
# 196 a 1116 da tela de 720x1280) e longe do que a grade põe por cima: o número de
# visualizações, embaixo à esquerda (NUMERO_DA_GRADE), a sacolinha da Shopee, em cima à
# direita (SACOLINHA_DA_GRADE), e o selo "Fixado" dos vídeos fixados no perfil, em cima à
# esquerda (FIXADO_DA_GRADE, medido no Motorola em 29/10): pedido do Rafael, não atrapalhar os
# números. Começa desligada (chave capa_com_chamada de shopee_video): ele vê o exemplo no
# privado e liga no painel. A bebida alcoólica fica com a capa dos avisos. Escolha do Rafael
# (29/10, P76): DECISOES.md, Shopee Vídeo.
CHAVE_DA_CAPA = "capa_com_chamada"
VISIVEL_NA_GRADE = (196, 1116)                  # de cima a baixo, em y
NUMERO_DA_GRADE = (52, 1005, 228, 1055)         # x1, y1, x2, y2
SACOLINHA_DA_GRADE = (587, 210, 667, 278)
FIXADO_DA_GRADE = (36, 200, 252, 305)
AREA_DA_CHAMADA = (52, 312, 668, 452)           # abaixo do selo e da sacolinha, acima da foto
AREA_DA_FOTO_COM_CHAMADA = (466, 995)           # de cima a baixo, em y: acaba antes do número
LETRAS_DA_CHAMADA = (64, 36)                    # a maior e a menor
LINHAS_DA_CHAMADA = 2


def capa_ligada():
    return bool((db.ler_config("shopee_video", {}) or {}).get(CHAVE_DA_CAPA))


# A linha que termina numa palavra de ligação ("Acaba com a / bagunça") vale como uma letra
# PENALIDADE_DA_QUEBRA px menor: a quebra boa ganha, se a letra não ficar muito menor.
PENALIDADE_DA_QUEBRA = 8


def _quebra_da_chamada(texto, desenho, fonte_ttf):
    """
    (fonte, linhas) da chamada: a maior letra em que ela cabe em até LINHAS_DA_CHAMADA linhas
    na AREA_DA_CHAMADA, com as duas linhas equilibradas e, se der, sem a 1ª terminar numa
    palavra de ligação. None quando não cabe nem na menor letra.
    """
    from PIL import ImageFont
    x1, y1, x2, y2 = AREA_DA_CHAMADA
    palavras = texto.split(" ")
    melhor = None
    maior, menor = LETRAS_DA_CHAMADA
    for tamanho in range(maior, menor - 1, -2):
        fonte = ImageFont.truetype(fonte_ttf, tamanho)
        opcoes = [[texto]]
        if LINHAS_DA_CHAMADA >= 2:
            opcoes += [[" ".join(palavras[:k]), " ".join(palavras[k:])] for k in range(1, len(palavras))]
        cabem = [linhas for linhas in opcoes if round(tamanho * 1.2) * len(linhas) <= y2 - y1
                 and all(desenho.textlength(l, font=fonte) <= x2 - x1 for l in linhas)]
        for linhas in cabem:
            ligacao = len(linhas) > 1 and linhas[0].split(" ")[-1].lower().strip(",.-:") in PALAVRAS_DE_LIGACAO
            # Uma linha só é a melhor; em duas, as de tamanho parecido.
            nota = (tamanho - (PENALIDADE_DA_QUEBRA if ligacao else 0), len(linhas) == 1,
                    -max(desenho.textlength(l, font=fonte) for l in linhas))
            if melhor is None or nota > melhor[0]:
                melhor = (nota, fonte, linhas)
    return (melhor[1], melhor[2]) if melhor else None


def capa_com_chamada(foto, chamada):
    """
    A capa com chamada (PNG, bytes, 720x1280): a foto do anúncio (bytes) no fundo preto e a
    chamada em cima, em até LINHAS_DA_CHAMADA linhas, na maior letra que cabe. None sem a
    chamada, com a foto que não abre ou com a chamada que não cabe nem na menor letra.
    """
    import io

    import matplotlib
    from PIL import Image, ImageDraw
    chamada = " ".join((chamada or "").split())
    if not chamada:
        return None
    try:
        imagem = Image.open(io.BytesIO(foto)).convert("RGB")
    except Exception:
        return None
    largura, _altura = TELA
    capa = Image.new("RGB", TELA, "black")
    topo, base = AREA_DA_FOTO_COM_CHAMADA
    escala = min(largura / imagem.width, (base - topo) / imagem.height)
    imagem = imagem.resize((max(1, round(imagem.width * escala)), max(1, round(imagem.height * escala))))
    capa.paste(imagem, ((largura - imagem.width) // 2, topo + (base - topo - imagem.height) // 2))

    desenho = ImageDraw.Draw(capa)
    fonte_ttf = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")
    quebra = _quebra_da_chamada(chamada, desenho, fonte_ttf)
    if not quebra:
        return None
    fonte, linhas = quebra
    x1, y1, x2, y2 = AREA_DA_CHAMADA
    altura_da_linha = round(fonte.size * 1.2)
    # Alinhada à esquerda, na mesma coluna do número de visualizações, e no meio da faixa.
    cima = y1 + (y2 - y1 - altura_da_linha * len(linhas)) / 2
    for i, linha in enumerate(linhas):
        desenho.text((x1, cima + altura_da_linha * (i + 0.5)), linha, font=fonte, fill="white", anchor="lm")
    saida = io.BytesIO()
    capa.save(saida, format="PNG")
    return saida.getvalue()


def _capa_da_vez(foto, vantagem):
    """A capa com chamada do vídeo que vai ao ar, ou None (a capa de sempre) quando ela não sai: o vídeo não para por ela."""
    try:
        return capa_com_chamada(foto, vantagem)
    except Exception:
        return None


def recorte_da_grade(capa):
    """O pedaço da capa (PNG, bytes) que a grade do perfil mostra (VISIVEL_NA_GRADE), em PNG: o exemplo do painel."""
    import io

    from PIL import Image
    with Image.open(io.BytesIO(capa)) as imagem:
        cima, baixo = VISIVEL_NA_GRADE
        saida = io.BytesIO()
        imagem.crop((0, cima, imagem.width, baixo)).save(saida, format="PNG")
    return saida.getvalue()


def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outra_foto=None):
    """
    O vídeo editado com a foto (bytes) em destino: "" quando deu certo, ou o motivo fixo.
    Com avisos=True (bebida alcoólica), a capa com os avisos abre o vídeo no lugar da foto;
    sem eles, a capa (bytes de uma imagem, como a capa com chamada), quando vem. Com a musica
    (caminho), ela é o som do vídeo inteiro (o vídeo sem som, P55). Com miniatura=False (ou 0),
    o vídeo vai sem a nossa miniatura (o canto dela tem coisa do criador, P81); com uma largura
    menor (miniatura_no_video), ela vai desse tamanho, no mesmo canto (P97). Com a outra_foto
    (bytes de outra foto do mesmo produto), a miniatura troca entre as duas (P101).
    """
    if avisos and foto:
        capa = capa_com_avisos(foto)
        if not capa:
            return "a capa com os avisos da bebida alcoólica não saiu"
    largura = largura_da_miniatura(miniatura)
    return videos.com_foto_e_miniatura(video, foto, destino, SEGUNDOS_DA_FOTO, largura, centro_da_miniatura(largura),
                                       SETA, CENTRO_DA_SETA, ESPERA_MAXIMA, PULSO_DA_SETA, capa, musica,
                                       outra=outra_foto, troca=SEGUNDOS_DE_CADA_FOTO)


def largura_da_miniatura(miniatura):
    """A largura da miniatura pedida, em px: True é a de sempre; False ou 0, sem ela; um número, essa (P97)."""
    if miniatura is True:
        return LARGURA_DA_MINIATURA
    return int(miniatura or 0)


def centro_da_miniatura(largura):
    """O centro da miniatura desta largura, com o canto de cima à direita no lugar de sempre (P97)."""
    return CANTO_DA_MINIATURA[0] - largura // 2, CANTO_DA_MINIATURA[1] + largura // 2


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
# - "alto": no topo, à esquerda, ao lado da miniatura (que vai de x 486 a 666);
# - "meio": logo abaixo da miniatura (que vai até uns 250 px), centralizado;
# - "esquerda" e "direita": nos lados, numa caixa estreita de até 3 linhas, no meio da
#   altura: acima da seta (que começa em y 726) e da coluna de botões do app à direita.
# Nenhum lugar livre do rosto e do produto (SEM_LUGAR), o vídeo vai sem os textos (escolha
# do Rafael, P47: no vídeo do conjunto, o alto cobriu o rosto da modelo e o meio cobriria o
# conjunto).
LUGARES_DOS_TEXTOS = {"alto": (68, 150, 340, 2), "meio": (None, 280, 480, 2),
                      "esquerda": (64, 400, 170, 3), "direita": (-64, 400, 170, 3)}
LUGAR_PADRAO = "alto"
SEM_LUGAR = "nenhum"
TOPO_DOS_TEXTOS = LUGARES_DOS_TEXTOS["meio"][1]
LARGURA_DOS_TEXTOS = LUGARES_DOS_TEXTOS["meio"][2]
LETRA_DOS_TEXTOS = (36, 28)         # a maior e a menor
SEGUNDOS_DE_CADA_TEXTO = 3.0
FUNDO_DOS_TEXTOS = (20, 20, 20, 200)
FUNDO_DA_CHAMADA = (238, 77, 45, 230)  # o laranja da Shopee
MAXIMO_DO_NOME = 28
MAXIMO_DA_VANTAGEM = 36
MAXIMO_DA_CHAMADA = 32

# A IA escreve o nome, a vantagem e a chamada vendo o vídeo, com as regras da Shopee Vídeo
# que mais pegam texto na tela (regras 7, 13 e 14 das diretrizes): sem marca, sem prometer o
# que o vídeo não mostra, sem preço ou promoção. O preço e o desconto ficam só no cartão do
# produto, que o app mostra sempre atualizado (com o desconto do Pix): no vídeo eles ficariam
# parados no dia do post e podiam não bater com o cartão. No lugar deles, a chamada para o
# produto anexado embaixo, onde a seta aponta. Escolha do Rafael (29/10, P80): DECISOES.md,
# Shopee Vídeo.
_NOME_NO_PROMPT = ("- \"nome\": o nome genérico do produto, como o comprador procura (ex.: \"Copo Térmico\"), "
                   f"até {MAXIMO_DO_NOME} caracteres;\n")
_CHAMADA_NO_PROMPT = ("- \"chamada\": uma frase curta para o fim do vídeo, com palavras suas, chamando para o "
                      f"produto anexado aqui embaixo, até {MAXIMO_DA_CHAMADA} caracteres, sem mandar para fora da "
                      "Shopee;\n")
_REGRAS_NO_PROMPT = ("Regras da Shopee Vídeo: nada de nome, logo ou slogan de marca; nada que o vídeo não mostre; "
                     "sem preço, desconto, promoção, emoji ou hashtag. Escreva com a ortografia e a acentuação "
                     "certas do português do Brasil e confira cada palavra antes de responder.\n")
_FALAS_NO_PROMPT = (
    "Diga também onde alguém fala no vídeo (voz de gente, não música): \"falas\", a lista dos trechos em "
    "segundos desde o começo do vídeo, como [[início, fim], ...]; [] se ninguém fala.\n"
)
# O lugar também não cobre as fotos, quadros e textos que o criador pôs por cima do vídeo,
# agora que eles não tiram as nossas legendas (escolha do Rafael, 29/10, P82: DECISOES.md,
# Shopee Vídeo).
_LUGAR_NO_PROMPT = (
    "Diga onde os textos podem ficar sem cobrir o produto, o rosto de alguém nem as fotos, quadros ou textos "
    "que o próprio vídeo pôs por cima da imagem, na maior parte do vídeo: "
    "\"lugar\", \"alto\" (no topo, à esquerda, entre uns 12% e 22% da altura e até uns 65% da largura), "
    "\"meio\" (centralizado, entre uns 22% e 33% da altura), \"esquerda\" (perto da borda esquerda, até "
    "uns 40% da largura, entre uns 31% e 45% da altura) ou \"direita\" (o mesmo, perto da borda direita); "
    f"\"{SEM_LUGAR}\" se todos esses cobrem alguma dessas coisas.\n"
)
# Vídeo que já tem texto próprio na tela vai sem as nossas legendas, que cobririam o dele
# (escolha do Rafael, P52). O texto dentro das fotos e quadros do produto que o criador pôs
# por cima (as cores, a quantidade) não conta: é a miniatura dele, como a nossa (escolha do
# Rafael, 29/10, P82). DECISOES.md, Shopee Vídeo.
_TEXTO_NO_VIDEO_NO_PROMPT = (
    "Diga também se o próprio vídeo já tem texto escrito na tela, como legenda, título ou frase por cima da "
    "imagem, na maior parte do tempo (não contam marca d'água, nome do perfil, o que está escrito no "
    "produto ou na embalagem, nem o texto dentro das fotos e quadros do produto que o vídeo pôs por cima, "
    "como as cores ou a quantidade): \"texto_no_video\", true ou false.\n"
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
    "Diga também se o canto de cima à direita do vídeo (de uns 65% a 95% da largura e até uns 20% da altura) "
    "tem, em qualquer parte, foto, quadro, texto ou figura que o próprio vídeo pôs por cima da imagem, em "
    "qualquer momento (não contam marca d'água, logo nem nome do perfil): \"canto_ocupado\", true ou false.\n"
    "Diga também onde ficam, em qualquer momento do vídeo, as legendas, títulos, frases, fotos, quadros e "
    "figuras que o próprio vídeo pôs por cima da imagem no alto da tela, até uns 30% da altura (sem marca "
    "d'água, logo nem nome do perfil): \"por_cima_no_alto\", a lista com a parte da tela que cada um ocupa, em "
    "porcentagem da largura e da altura do vídeo, contando da borda esquerda e da borda de cima, como "
    "[{{\"esquerda\": 30, \"direita\": 70, \"topo\": 14, \"base\": 19}}]; [] se não há nenhum.\n"
)
_FALAS_E_LUGAR_NO_PROMPT = _FALAS_NO_PROMPT + _LUGAR_NO_PROMPT + _TEXTO_NO_VIDEO_NO_PROMPT + _CANTO_NO_PROMPT
# Os textos do vídeo que vai ao ar: o original, sem cortes (as falas só importam nas versões).
PROMPT_DOS_TEXTOS = (
    "Você vai ver um vídeo curto de um produto vendido na Shopee: {nome}.\n"
    "Escreva três textos curtos para aparecer na tela do vídeo, em português do Brasil:\n"
    + _NOME_NO_PROMPT
    + "- \"vantagem\": uma vantagem do produto que o próprio vídeo mostra (ex.: \"Mantém gelado o dia todo\"), "
    f"até {MAXIMO_DA_VANTAGEM} caracteres;\n"
    + _CHAMADA_NO_PROMPT
    + _REGRAS_NO_PROMPT + _LUGAR_NO_PROMPT + _TEXTO_NO_VIDEO_NO_PROMPT + _CANTO_NO_PROMPT
    + "Responda só com o JSON: {{\"nome\": \"...\", \"vantagem\": \"...\", \"chamada\": \"...\", "
    "\"lugar\": \"alto\", \"texto_no_video\": false, \"canto_ocupado\": false, \"por_cima_no_alto\": []}}"
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


def letreiro(texto, fundo=FUNDO_DOS_TEXTOS, largura_maxima=None, linhas_maximas=2):
    """
    O texto da tela (PNG com fundo transparente, bytes): letras brancas numa caixa de cantos
    redondos, em até linhas_maximas linhas de até largura_maxima (padrão: LARGURA_DOS_TEXTOS).
    """
    import io

    import matplotlib
    from PIL import Image, ImageDraw, ImageFont
    fonte_ttf = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")
    rascunho = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    maior, menor = LETRA_DOS_TEXTOS
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
                     fill="white", anchor="mm")
    saida = io.BytesIO()
    imagem.save(saida, format="PNG")
    return saida.getvalue()


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
MAXIMOS_DOS_TEXTOS = {"nome": MAXIMO_DO_NOME, "vantagem": MAXIMO_DA_VANTAGEM, "chamada": MAXIMO_DA_CHAMADA}


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


def _nome_lugar_e_falas(dados):
    """
    O nome, o lugar, as falas, se o vídeo já tem texto e se o canto da nossa miniatura tem
    coisa do criador, da resposta da IA, só os que vieram certos.
    """
    textos = {}
    nome = _texto_certo(str(dados.get("nome") or ""), MAXIMO_DO_NOME)
    if nome:
        textos["nome"] = nome
    if dados.get("lugar") in LUGARES_DOS_TEXTOS or dados.get("lugar") == SEM_LUGAR:
        textos["lugar"] = dados["lugar"]
    for chave in ("texto_no_video", "canto_ocupado"):
        if isinstance(dados.get(chave), bool):
            textos[chave] = dados[chave]
    por_cima = _por_cima_no_alto(dados.get("por_cima_no_alto"))
    if por_cima:
        textos["por_cima"] = por_cima
    falas = _falas(dados.get("falas"))
    if falas is not None:
        textos["falas"] = falas
    return textos


def lugar_dos_textos(textos):
    """O lugar das nossas legendas pela resposta da IA: nenhum quando o vídeo já tem texto na tela (P52)."""
    return SEM_LUGAR if textos.get("texto_no_video") else textos.get("lugar")


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
# esquerda à direita e até a altura.
CANTO_OLHADO_PELA_IA = (65, 95, 20)


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
    esquerda, direita, topo, _base = caixa
    comeco, fim, ate = CANTO_OLHADO_PELA_IA
    return esquerda < fim and direita > comeco and topo < ate


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


def _vantagem_e_chamada(dados, textos):
    """Põe em textos a vantagem e a chamada da resposta da IA, só as que vieram certas."""
    for chave, maximo in (("vantagem", MAXIMO_DA_VANTAGEM), ("chamada", MAXIMO_DA_CHAMADA)):
        limpo = _texto_certo(str(dados.get(chave) or ""), maximo)
        if limpo:
            textos[chave] = limpo
    return textos


def textos_da_tela(video, nome):
    """
    {"nome", "vantagem", "chamada", "lugar", "texto_no_video", "canto_ocupado", "por_cima"} que
    a IA escreveu vendo o vídeo, só o que veio certo; {} sem resposta.
    """
    dados = _resposta_da_ia(video, PROMPT_DOS_TEXTOS.format(nome=nome))
    return _revisar_ortografia(_vantagem_e_chamada(dados, _nome_lugar_e_falas(dados)))


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
             capa=None, miniatura=True, outra_foto=None):
    """
    O Editor 2 em destino: o vídeo original, inteiro, na ordem e na velocidade dele, com os
    textos da tela por cima, e depois o Editor 1 (com avisos=True, a capa dos avisos da bebida
    alcoólica no lugar da foto; sem eles, a capa, quando vem). Nada é cortado nem acelerado:
    isso fica para as versões modificadas do exemplo (pedido do Rafael de 28/10/2026:
    DECISOES.md, Shopee Vídeo). lugar: onde vão os textos (um de LUGARES_DOS_TEXTOS, da IA;
    SEM_LUGAR = sem os textos; sem ela, LUGAR_PADRAO). Com a musica (caminho), ela é o som do
    vídeo inteiro. Devolve (motivo, resumo {original, lugar, textos}): motivo "" quando deu certo.
    """
    original = videos.duracao(video)
    if not original:
        return "o vídeo não abre", {}
    return _editor_2_no_original(video, foto, destino, original, nome, vantagem, chamada, _lugar(lugar), avisos,
                                 musica, capa, miniatura, outra_foto)


def _editor_2_no_original(video, foto, destino, original, nome, vantagem, chamada, lugar, avisos=False,
                          musica=None, capa=None, miniatura=True, outra_foto=None):
    """O Editor 2 em destino, com a duração do vídeo já medida (editar_2_e_versoes usa no 1º vídeo)."""
    import tempfile
    letreiros, textos = _letreiros([(nome, FUNDO_DOS_TEXTOS), (vantagem, FUNDO_DOS_TEXTOS),
                                    (chamada, FUNDO_DA_CHAMADA)], lugar, original)
    resumo = {"original": original, "lugar": lugar, "textos": textos, "miniatura": miniatura}
    if not letreiros:
        return editar(video, foto, destino, avisos, musica, capa, miniatura, outra_foto), resumo
    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(destino))) as pasta:
        corpo = os.path.join(pasta, "com_textos.mp4")
        # O vídeo inteiro numa parte só, na velocidade dele: só os textos entram por cima.
        motivo = videos.com_cortes_e_ritmo(video, [(0.0, original, 1.0)], corpo, letreiros, ESPERA_MAXIMA)
        if motivo:
            return motivo, resumo
        return editar(corpo, foto, destino, avisos, musica, capa, miniatura, outra_foto), resumo


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
# O porquê, no detalhe do registro, quando o Editor 2 saiu sem algum texto.
SEM_LUGAR_LIVRE = "a IA não viu lugar livre do produto e do rosto para os textos"
TEXTO_JA_NO_VIDEO = "o vídeo já tem texto próprio na tela"
SEM_OS_TEXTOS_DA_IA = "a IA não deu o nome, a vantagem e a chamada"


def editar_para_postar(video, foto, destino, produto="", avisos=False, outra_foto=None):
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
    chamada ligada (P76), a vantagem da IA vai na capa de todos os vídeos (P100), e o jeito leva
    COM_A_CHAMADA. Com a outra_foto (bytes de outra foto do mesmo produto, a mais parecida com o
    vídeo), a miniatura troca entre ela e a foto (P101), e o jeito leva COM_A_MINIATURA_ALTERNADA.
    """
    if not foto:
        # Sem a foto do anúncio nenhum dos dois sai: o motivo é o do Editor 1, sem gastar a IA.
        return editar(video, foto, destino, avisos), SO_COM_O_EDITOR_1 + (COM_OS_AVISOS if avisos else ""), ""
    musica = _caminho(musicas_de_fundo(video)[0])
    textos = textos_da_tela(video, produto) if produto else {}
    # Sem a vantagem da IA, a capa fica a de antes; a bebida alcoólica, com a dos avisos.
    # A capa com chamada vai em todos os vídeos, menos na bebida alcoólica, que abre com a capa dos
    # avisos. Escolha do Rafael (30/10, P100): DECISOES.md, Shopee Vídeo.
    capa = _capa_da_vez(foto, textos.get("vantagem", "")) if capa_ligada() and not avisos else None
    # Sem a nossa miniatura quando o criador já pôs coisa no canto dela (P81); menor quando a
    # coisa dele fica logo abaixo do canto (P97).
    miniatura = miniatura_no_video(textos)
    avisado = ((COM_OS_AVISOS if avisos else "") + (COM_A_CHAMADA if capa else "") + (COM_MUSICA if musica else "")
               + (SEM_A_MINIATURA if not miniatura
                  else COM_A_MINIATURA_MENOR if miniatura < LARGURA_DA_MINIATURA else "")
               + (COM_A_MINIATURA_ALTERNADA if outra_foto and miniatura else ""))
    try:
        motivo_2, resumo = editar_2(video, foto, destino, textos.get("nome", ""), textos.get("vantagem", ""),
                                    textos.get("chamada", ""), lugar_dos_textos(textos), avisos, musica, capa,
                                    miniatura, outra_foto)
    except Exception as e:
        # O erro no meio do Editor 2 também deixa o vídeo ir com o Editor 1.
        motivo_2, resumo = f"erro ({type(e).__name__})", {}
    if not motivo_2:
        detalhe = ""
        if textos.get("texto_no_video"):
            detalhe = TEXTO_JA_NO_VIDEO
        elif resumo.get("lugar") == SEM_LUGAR:
            detalhe = SEM_LUGAR_LIVRE
        elif not (textos.get("nome") or textos.get("vantagem") or textos.get("chamada")):
            detalhe = SEM_OS_TEXTOS_DA_IA
        return "", (COM_LEGENDAS if resumo.get("textos") else SEM_LEGENDAS_NA_TELA) + avisado, detalhe
    return (editar(video, foto, destino, avisos, musica, capa, miniatura, outra_foto), SO_COM_O_EDITOR_1 + avisado,
            f"o Editor 2 não saiu: {motivo_2}")


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
    + _REGRAS_NO_PROMPT + _FALAS_E_LUGAR_NO_PROMPT
    + "Responda só com o JSON: {{\"nome\": \"...\", \"vantagem\": \"...\", \"chamada\": \"...\", "
    "\"versoes\": [{{\"vantagem\": \"...\", "
    "\"inicio\": 0.0, \"fim\": 0.0, \"chamada\": \"...\"}}], \"falas\": [[0.0, 0.0]], \"lugar\": \"alto\", "
    "\"texto_no_video\": false, \"canto_ocupado\": false, \"por_cima_no_alto\": []}}"
)


def textos_das_versoes(video, nome):
    """
    {"nome", "vantagem" e "chamada" (as do vídeo completo), "lugar", "falas", "versoes":
    [{"vantagem", "chamada", "inicio", "fim"}]} que a IA escreveu vendo o vídeo, só o que veio
    certo; {} quando ela não respondeu.
    """
    dados = _resposta_da_ia(video, PROMPT_DAS_VERSOES.format(nome=nome))
    textos = _vantagem_e_chamada(dados, _nome_lugar_e_falas(dados))
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
                         miniatura=True):
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
                motivo = editar(corpo, foto, arquivo, musica=_caminho(musica), miniatura=miniatura)
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
                       lugar=None, miniatura=True):
    """
    O Editor 2 e as versões em arquivo_da_versao(destino, n): o 1º é o vídeo original, sem
    cortes, com o Editor 2 (o nome, a vantagem e a chamada), como vai ao ar; os seguintes são as
    versões modificadas (planejar_versoes), cada uma remontada (sem as partes paradas, com o
    ritmo), com os seus textos (a vantagem do gancho, o nome e a chamada da versão, nessa ordem)
    e com o Editor 1 por cima. versoes_da_ia = [{"vantagem", "chamada", "inicio", "fim"}].
    Devolve (motivo, resumo): motivo "" quando todos saíram; o que a remontagem muda nas versões
    fica em resumo["remontagem"].
    """
    original = videos.duracao(video)
    if not original:
        return "o vídeo não abre", {}
    com_fala, trechos = _remontagem(video, original, falas)
    lugar = _lugar(lugar)
    planos = planejar_versoes(trechos, [(v["inicio"], v["fim"]) for v in versoes_da_ia], com_fala, original)
    musicas = musicas_de_fundo(video, 1 + len(planos))
    completo = arquivo_da_versao(destino, 1)
    motivo, do_completo = _editor_2_no_original(video, foto, completo, original, nome, vantagem, chamada, lugar,
                                                musica=_caminho(musicas[0]), miniatura=miniatura)
    resumo = {"original": original, "inteiro": original, "lugar": lugar, "miniatura": miniatura,
              "com_fala": _segundos_com_fala(com_fala, original),
              "remontagem": _resumo_da_remontagem(trechos, original, com_fala),
              "versoes": [_resumo_do_completo(completo, original, do_completo["textos"], vantagem, musicas[0])]}
    if motivo:
        return motivo, resumo
    return _versoes_modificadas(video, foto, destino, planos, versoes_da_ia, resumo, lambda plano, da_ia: _letreiros(
        [(da_ia.get("vantagem", ""), FUNDO_DOS_TEXTOS), (nome, FUNDO_DOS_TEXTOS),
         (da_ia.get("chamada", ""), FUNDO_DA_CHAMADA)],
        lugar, _segundos_remontados(plano["trechos"])), musicas[1:], miniatura)


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
    vantagem e a chamada).
    """
    return _exemplo_das_versoes(destino, "ids_2", lambda arquivo, foto, textos, produto: editar_2_e_versoes(
        arquivo, foto, destino, textos.get("nome", ""), textos.get("vantagem", ""), textos.get("versoes", []),
        textos.get("chamada", ""), textos.get("falas"), lugar_dos_textos(textos), miniatura_no_video(textos)))


def exemplo_capa():
    """
    O exemplo da capa com chamada (P76), com o próximo vídeo que o robô pegaria: a vantagem que
    a IA escreve vendo o vídeo, na capa. Tem a lista própria dos já mostrados. Devolve (nome do
    produto, "", {"capa", "grade", "chamada"}) quando deu certo (as duas imagens em PNG: a capa
    inteira e o pedaço que a grade do perfil mostra), ou (None, motivo, None).
    """
    def editar_um(arquivo, link, foto):
        produto = _produto_do_link(link)
        textos = textos_da_tela(arquivo, produto["nome"]) if produto.get("nome") else {}
        if not textos.get("vantagem"):
            return "a IA não escreveu a vantagem do produto deste vídeo", None
        capa = capa_com_chamada(foto, textos["vantagem"])
        if not capa:
            return "a capa com a chamada não saiu", None
        return "", {"capa": capa, "grade": recorte_da_grade(capa), "chamada": textos["vantagem"]}

    return _exemplo("ids_capa", editar_um)

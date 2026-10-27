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

O Editor 2 (editar_2) é esta edição com três acréscimos, em teste só no exemplo do painel:
o vídeo remontado sem as partes paradas, com trechos acelerados e uma câmera lenta curta,
e os textos da tela (nome, vantagem e preço). O Rafael compara os dois exemplos e escolhe
qual fica (pedido de 27/10/2026: DECISOES.md, Shopee Vídeo).

Usado pelo robô automático (robo_shopee_video, na cópia do vídeo que vai ao rascunho) e
pelo painel da Shopee Vídeo (os exemplos).
"""
import os

import assistente_shopee_video as assistente
import db
import postador_shopee_video as ps
import videos

# Todas as fontes do robô, na ordem em que o exemplo procura um vídeo.
FONTES_COM_EDICAO = tuple(assistente.FONTES)
# A foto do produto sozinha antes do vídeo, em segundos.
SEGUNDOS_DA_FOTO = 2
# A miniatura e a seta onde o Rafael as põe no LumaFusion (vídeo de 25/10), no vídeo de
# 720x1280. A miniatura: 25% da largura, com o centro a 80% da largura e 10% da altura
# (posição X 60 e Y -80 no LumaFusion), do começo do vídeo até o fim.
LARGURA_DA_MINIATURA = 180
CENTRO_DA_MINIATURA = (576, 128)
# A seta é a do Rafael (o arquivo Seta_da_Shopee que ele usa no LumaFusion), com o fundo
# preto tirado: só o pedaço com a seta, já no tamanho dele (62,9%, posição X -23 e Y 16), com
# o centro perto do canto de baixo à esquerda, apontando para onde a Shopee mostra o produto.
# Ela começa logo depois da foto, já se desenhando quando o vídeo começa, e pulsa: o arquivo
# guarda a entrada e um pulso (quadros 72 a 101, 1,2 s), que se repete até o fim do vídeo.
# Pedido do Rafael (25/10): DECISOES.md, Shopee Vídeo.
SETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "midia", "seta_da_shopee.apng")
CENTRO_DA_SETA = (142, 846)
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


def ligada():
    return bool((db.ler_config("shopee_video", {}) or {}).get("edicao_ligada"))


def vale_para(fonte):
    """A edição entra no vídeo desta fonte agora? Ligada, em qualquer fonte do robô."""
    return fonte in FONTES_COM_EDICAO and ligada()


# A capa da bebida alcoólica: a tela de 720x1280 que abre o vídeo (o app usa o primeiro
# quadro como capa) com a foto do anúncio em cima e, logo embaixo, os três avisos da Shopee
# em letras brancas sobre faixa preta. Fica no meio da tela, longe das bordas que a grade da
# Shopee corta na miniatura. Escolha do Rafael (26/10, P43): DECISOES.md, Shopee Vídeo.
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
    capa = Image.new("RGB", TELA, "white")
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
    desenho.rectangle((0, cima, largura, baixo), fill="black")
    passo = (baixo - cima) / len(assistente.AVISOS_DE_ALCOOL)
    for i, aviso in enumerate(assistente.AVISOS_DE_ALCOOL):
        desenho.text((largura / 2, cima + passo * (i + 0.5)), aviso, font=fonte, fill="white", anchor="mm")
    saida = io.BytesIO()
    capa.save(saida, format="PNG")
    return saida.getvalue()


def editar(video, foto, destino, avisos=False):
    """
    O vídeo editado com a foto (bytes) em destino: "" quando deu certo, ou o motivo fixo.
    Com avisos=True (bebida alcoólica), a capa com os avisos abre o vídeo no lugar da foto.
    """
    capa = None
    if avisos and foto:
        capa = capa_com_avisos(foto)
        if not capa:
            return "a capa com os avisos da bebida alcoólica não saiu"
    return videos.com_foto_e_miniatura(video, foto, destino, SEGUNDOS_DA_FOTO, LARGURA_DA_MINIATURA,
                                       CENTRO_DA_MINIATURA, SETA, CENTRO_DA_SETA, ESPERA_MAXIMA, PULSO_DA_SETA,
                                       capa)


# --- Editor 2 ---
# O Editor 1 é a edição de cima, a que vale nos rascunhos. O Editor 2 é o Editor 1 com três
# acréscimos, em teste: o Rafael vê os dois exemplos no painel e decide qual fica (pedido
# de 27/10/2026: DECISOES.md, Shopee Vídeo). Antes da foto, da miniatura e da seta, o vídeo
# é remontado: as partes paradas saem, os trechos calmos ficam mais rápidos, o de mais ação
# ganha uma câmera lenta curta, e os textos da tela (nome, vantagem e preço) entram por cima.

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
# miniatura, cobria o alto do móvel e o decote do vestido). Os lugares, em (x, topo, largura
# máxima das linhas; a caixa tem mais 56 px de margem) no vídeo de 720x1280; x None =
# centralizado:
# - "alto": no topo, à esquerda, ao lado da miniatura (que vai de x 486 a 666);
# - "meio": logo abaixo da miniatura (que vai até uns 250 px), centralizado.
LUGARES_DOS_TEXTOS = {"alto": (24, 110, 390), "meio": (None, 280, 480)}
LUGAR_PADRAO = "alto"
TOPO_DOS_TEXTOS = LUGARES_DOS_TEXTOS["meio"][1]
LARGURA_DOS_TEXTOS = LUGARES_DOS_TEXTOS["meio"][2]
LETRA_DOS_TEXTOS = (40, 28)         # a maior e a menor
SEGUNDOS_DE_CADA_TEXTO = 3.0
FUNDO_DOS_TEXTOS = (20, 20, 20, 200)
FUNDO_DO_PRECO = (238, 77, 45, 230)  # o laranja da Shopee
MAXIMO_DO_NOME = 28
MAXIMO_DA_VANTAGEM = 36

# A IA escreve o nome e a vantagem vendo o vídeo, com as regras da Shopee Vídeo que mais
# pegam texto na tela (regras 7, 13 e 14 das diretrizes): sem marca, sem prometer o que o
# vídeo não mostra, sem preço ou promoção (o preço vem da API, com "a partir de").
PROMPT_DOS_TEXTOS = (
    "Você vai ver um vídeo curto de um produto vendido na Shopee: {nome}.\n"
    "Escreva dois textos curtos para aparecer na tela do vídeo, em português do Brasil:\n"
    "- \"nome\": o nome genérico do produto, como o comprador procura (ex.: \"Copo Térmico\"), "
    f"até {MAXIMO_DO_NOME} caracteres;\n"
    "- \"vantagem\": uma vantagem do produto que o próprio vídeo mostra (ex.: \"Mantém gelado o dia todo\"), "
    f"até {MAXIMO_DA_VANTAGEM} caracteres.\n"
    "Regras da Shopee Vídeo: nada de nome, logo ou slogan de marca; nada que o vídeo não mostre; sem preço, "
    "desconto, promoção, emoji ou hashtag.\n"
    "Diga também onde alguém fala no vídeo (voz de gente, não música): \"falas\", a lista dos trechos em "
    "segundos desde o começo do vídeo, como [[início, fim], ...]; [] se ninguém fala.\n"
    "E onde os textos podem ficar sem cobrir o produto nem o rosto de alguém, na maior parte do vídeo: "
    "\"lugar\", \"alto\" (no topo, à esquerda, entre uns 8% e 18% da altura) ou \"meio\" (centralizado, "
    "entre uns 22% e 33% da altura).\n"
    "Responda só com o JSON: {{\"nome\": \"...\", \"vantagem\": \"...\", \"falas\": [[0.0, 0.0]], "
    "\"lugar\": \"alto\"}}"
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


def letreiro(texto, fundo=FUNDO_DOS_TEXTOS, largura_maxima=None):
    """
    O texto da tela (PNG com fundo transparente, bytes): letras brancas numa caixa de cantos
    redondos, com as linhas até largura_maxima (padrão: LARGURA_DOS_TEXTOS).
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
        # Só o espaço comum separa as linhas: o espaço fixo ("R$ 39,90") não quebra.
        for palavra in [p for p in texto.split(" ") if p]:
            tentativa = f"{linha} {palavra}".strip()
            if not linha or rascunho.textlength(tentativa, font=fonte) <= limite:
                linha = tentativa
            else:
                linhas.append(linha)
                linha = palavra
        linhas.append(linha)
        if len(linhas) <= 2 and all(rascunho.textlength(t, font=fonte) <= limite for t in linhas):
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


def _so_letras(texto, maximo):
    """O texto da IA só com letras, números e pontuação simples (a fonte não tem emoji), até `maximo` caracteres."""
    import re
    limpo = " ".join(re.sub(r"[^\w\s.,!?%/+\-:()]", " ", texto or "").split())
    if len(limpo) <= maximo:
        return limpo
    return limpo[:maximo].rsplit(" ", 1)[0].rstrip(" ,.-:")


def textos_da_tela(video, nome):
    """{"nome", "vantagem"} que a IA escreveu vendo o vídeo; {} quando ela não respondeu."""
    import asyncio
    import json
    import re

    import api_gemini
    try:
        resposta = asyncio.run(api_gemini.analisar_video_gemini(video, PROMPT_DOS_TEXTOS.format(nome=nome)))
    except Exception:
        return {}
    achado = re.search(r"\{.*\}", resposta or "", re.S)
    try:
        dados = json.loads(achado.group(0)) if achado else {}
    except ValueError:
        return {}
    textos = {"nome": _so_letras(str(dados.get("nome") or ""), MAXIMO_DO_NOME),
              "vantagem": _so_letras(str(dados.get("vantagem") or ""), MAXIMO_DA_VANTAGEM)}
    textos = {chave: valor for chave, valor in textos.items() if valor}
    if dados.get("lugar") in LUGARES_DOS_TEXTOS:
        textos["lugar"] = dados["lugar"]
    falas = _falas(dados.get("falas"))
    if falas is not None:
        textos["falas"] = falas
    return textos


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


# Entre o "R$" e o número, para os dois não ficarem em linhas diferentes.
ESPACO_FIXO = "\u00a0"


def texto_do_preco(preco):
    """O preço da tela, do jeito que fica certo mesmo com variações de preço no anúncio."""
    return f"A partir de {assistente._reais(preco).replace(' ', ESPACO_FIXO)}" if preco and preco > 0 else ""


def horarios_dos_textos(textos, duracao):
    """[(texto, início, fim)]: um de cada vez, cada um na sua parte do vídeo remontado; o que não cabe sai."""
    while textos and duracao / len(textos) < 1.5:
        textos = textos[:-1]
    if not textos:
        return []
    parte = duracao / len(textos)
    return [(texto, round(parte * i + 0.3, 2), round(min(parte * (i + 1) - 0.2, parte * i + 0.3 + SEGUNDOS_DE_CADA_TEXTO), 2))
            for i, texto in enumerate(textos)]


def editar_2(video, foto, destino, nome="", vantagem="", preco=None, falas=None, lugar=None):
    """
    O Editor 2 em destino: o vídeo remontado (ritmo), com os textos da tela, e depois o
    Editor 1 por cima. falas: os trechos com fala da IA ([(início, fim)]); None = sem a
    resposta dela (aí vale o som). lugar: onde vão os textos ("alto" ou "meio", da IA; sem
    ela, LUGAR_PADRAO). Devolve (motivo, resumo): motivo "" quando deu certo; resumo diz o
    que mudou, para o Rafael comparar.
    """
    import tempfile
    original = videos.duracao(video)
    if not original:
        return "o vídeo não abre", {}
    com_fala = janelas_com_fala(falas, original, videos.som_por_janela(video, JANELA) if falas is None else ())
    trechos = ritmo(videos.movimento(video, QUADROS_DO_MOVIMENTO), original, com_fala=com_fala)
    remontado = sum((fim - inicio) / vel for inicio, fim, vel in trechos)
    fundos = {texto: FUNDO_DOS_TEXTOS for texto in (nome, vantagem) if texto}
    if texto_do_preco(preco):
        fundos[texto_do_preco(preco)] = FUNDO_DO_PRECO
    lugar = lugar if lugar in LUGARES_DOS_TEXTOS else LUGAR_PADRAO
    x_do_lugar, topo, largura_maxima = LUGARES_DOS_TEXTOS[lugar]
    letreiros = []
    for texto, inicio, fim in horarios_dos_textos(list(fundos), remontado):
        imagem = letreiro(texto, fundos[texto], largura_maxima)
        # A largura está no cabeçalho do PNG (bytes 16 a 20).
        largura = int.from_bytes(imagem[16:20], "big")
        x = (TELA[0] - largura) // 2 if x_do_lugar is None else x_do_lugar
        letreiros.append((imagem, inicio, fim, x, topo))
    resumo = {"original": original, "remontado": remontado,
              "cortado": original - sum(fim - inicio for inicio, fim, _ in trechos),
              "acelerados": sum(1 for *_, v in trechos if v > 1),
              "camera_lenta": sum(1 for *_, v in trechos if v < 1),
              "com_fala": sum(min(JANELA, original - i * JANELA) for i in com_fala), "lugar": lugar,
              "textos": [texto for texto, *_ in horarios_dos_textos(list(fundos), remontado)]}
    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(destino))) as pasta:
        corpo = os.path.join(pasta, "remontado.mp4")
        motivo = videos.com_cortes_e_ritmo(video, trechos, corpo, letreiros, ESPERA_MAXIMA)
        if motivo:
            return motivo, resumo
        return editar(corpo, foto, destino), resumo


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


def exemplo(destino):
    """
    O exemplo do Editor 1 (a edição que vale nos rascunhos) em destino. Devolve (nome do
    produto, "") quando deu certo, ou (None, motivo).
    """
    nome, motivo, _ = _exemplo("ids", lambda arquivo, link, foto: (editar(arquivo, foto, destino), None))
    return nome, motivo


def _produto_do_link(link):
    """O produto do link pela API de afiliado ({nome, preco, ...}); {} quando ela não diz."""
    import asyncio
    try:
        produtos, _ = asyncio.run(assistente.produtos_do_link(link))
    except Exception:
        return {}
    return produtos[0] if produtos else {}


def exemplo_editor_2(destino):
    """
    O exemplo do Editor 2 em destino, com os textos da tela que a IA escreveu vendo o
    vídeo e o preço da API. Tem a lista própria dos já mostrados. Devolve (nome do produto,
    "", resumo) quando deu certo, ou (None, motivo, resumo ou None).
    """
    def editar_um(arquivo, link, foto):
        produto = _produto_do_link(link)
        textos = textos_da_tela(arquivo, produto["nome"]) if produto.get("nome") else {}
        motivo, resumo = editar_2(arquivo, foto, destino, textos.get("nome", ""), textos.get("vantagem", ""),
                                  produto.get("preco"), textos.get("falas"), textos.get("lugar"))
        resumo["lugar_da_ia"] = "lugar" in textos
        resumo["textos_da_ia"] = bool(textos.get("nome") or textos.get("vantagem"))
        return motivo, resumo

    return _exemplo("ids_2", editar_um)

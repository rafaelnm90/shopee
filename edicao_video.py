#!/usr/bin/env python3
"""
A edição dos vídeos da Shopee Vídeo como o Rafael faz à mão no LumaFusion: a foto do
anúncio do produto nos primeiros segundos e, no vídeo inteiro, uma miniatura dela no canto
de cima à direita e uma seta vermelha embaixo à esquerda (a montagem fica no
videos.com_foto_e_miniatura, com o resto do tratamento de vídeo).

Vale para os vídeos de todas as fontes do robô (FONTES_COM_EDICAO): o Rafael confirmou que
todos os grupos e vídeos dele são autorais. Fica desligada até ele ver um exemplo no
privado e ligar no painel (Shopee Vídeo 🎬 → Robô Automático 🤖 → Edição dos Vídeos ✂️;
chave edicao_ligada de shopee_video). Escolhas do Rafael (25/10/2026, P37 e depois da
P38): DECISOES.md, Shopee Vídeo.

Usado pelo robô automático (robo_shopee_video, na cópia do vídeo que vai ao rascunho) e
pelo painel da Shopee Vídeo (o exemplo).
"""
import math
import os
import tempfile

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
# (posição X 60 e Y -80 no LumaFusion). A seta: vermelha e curva, perto do canto de baixo à
# esquerda, apontando para onde a Shopee mostra o produto; as duas vão até o fim do vídeo.
LARGURA_DA_MINIATURA = 180
CENTRO_DA_MINIATURA = (576, 128)
CENTRO_DA_SETA = (143, 842)
TAMANHO_DA_SETA = (200, 157)
COR_DA_SETA = (230, 0, 0, 255)
# Uns minutos bastam para um vídeo curto; depois disso o rascunho segue sem a edição.
ESPERA_MAXIMA = 300
# Quantos vídeos o exemplo tenta até achar um com a foto do anúncio na API.
VIDEOS_TENTADOS = 10


def ligada():
    return bool((db.ler_config("shopee_video", {}) or {}).get("edicao_ligada"))


def vale_para(fonte):
    """A edição entra no vídeo desta fonte agora? Ligada, em qualquer fonte do robô."""
    return fonte in FONTES_COM_EDICAO and ligada()


def desenhar_seta(destino):
    """
    Grava em destino (PNG com fundo transparente) a seta vermelha curva: um arco que sobe
    da esquerda e desce à direita, com a ponta para baixo. Desenhada 4 vezes maior e
    reduzida, para a borda sair lisa.
    """
    from PIL import Image, ImageDraw
    # O desenho é feito numa grade de 140x110 (4 vezes maior) e reduzido ao TAMANHO_DA_SETA.
    escala = 4
    largura, altura = 140 * escala, 110 * escala
    imagem = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(imagem)
    cx, cy, raio = 62 * escala, 70 * escala, 45 * escala
    inicio, fim = 200, 352
    desenho.arc((cx - raio, cy - raio, cx + raio, cy + raio), inicio, fim, fill=COR_DA_SETA, width=14 * escala)
    # A ponta segue a direção do arco no fim (sentido horário, com o y para baixo).
    angulo = math.radians(fim)
    ponta_x, ponta_y = cx + raio * math.cos(angulo), cy + raio * math.sin(angulo)
    direcao = (-math.sin(angulo), math.cos(angulo))
    lado = (-direcao[1], direcao[0])
    comprimento, meia_base = 34 * escala, 21 * escala
    desenho.polygon([
        (ponta_x + direcao[0] * comprimento, ponta_y + direcao[1] * comprimento),
        (ponta_x - direcao[0] * 4 * escala + lado[0] * meia_base, ponta_y - direcao[1] * 4 * escala + lado[1] * meia_base),
        (ponta_x - direcao[0] * 4 * escala - lado[0] * meia_base, ponta_y - direcao[1] * 4 * escala - lado[1] * meia_base),
    ], fill=COR_DA_SETA)
    imagem.resize(TAMANHO_DA_SETA, Image.LANCZOS).save(destino)


def editar(video, foto, destino):
    """O vídeo editado com a foto (bytes) em destino: "" quando deu certo, ou o motivo fixo."""
    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(destino))) as pasta:
        seta = os.path.join(pasta, "seta.png")
        desenhar_seta(seta)
        return videos.com_foto_e_miniatura(video, foto, destino, SEGUNDOS_DA_FOTO, LARGURA_DA_MINIATURA,
                                           CENTRO_DA_MINIATURA, seta, CENTRO_DA_SETA, ESPERA_MAXIMA)


def _videos_com_link():
    """(arquivo, link) dos vídeos das fontes que ainda têm o arquivo no servidor, os Autorais primeiro."""
    achados = []
    for fonte in FONTES_COM_EDICAO:
        for _, arquivo, link, _ in assistente._candidatos(fonte):
            if (arquivo and link and os.path.exists(arquivo)
                    and not arquivo.lower().endswith(assistente.EXTENSOES_DE_IMAGEM)):
                achados.append((arquivo, link))
            if len(achados) >= VIDEOS_TENTADOS:
                return achados
    return achados


def exemplo(destino):
    """
    O exemplo para o Rafael aprovar antes de ligar: o vídeo mais novo (dos Autorais, depois
    das outras fontes) que ainda tem o arquivo e o link no servidor (usado ou não), editado
    em destino. Devolve (nome do produto, "") quando deu certo, ou (None, motivo).
    """
    sem_foto = False
    for arquivo, link in _videos_com_link():
        foto = ps.foto_do_produto({"link": link})
        if not foto:
            sem_foto = True
            continue
        motivo = editar(arquivo, foto, destino)
        if motivo:
            return None, motivo
        return ps.nome_do_produto({"link": link}) or "produto do link", ""
    if sem_foto:
        return None, "nenhum vídeo no servidor tem a foto do anúncio na API agora"
    return None, "nenhum vídeo com o arquivo e o link no servidor agora"

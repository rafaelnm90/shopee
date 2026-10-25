#!/usr/bin/env python3
"""
A edição dos vídeos da Shopee Vídeo como o Rafael faz à mão no LumaFusion: a foto do
anúncio do produto nos primeiros segundos e uma miniatura dela no topo do vídeo inteiro
(a montagem fica no videos.com_foto_e_miniatura, com o resto do tratamento de vídeo).

Vale para os vídeos de todas as fontes do robô (FONTES_COM_EDICAO): o Rafael confirmou que
todos os grupos e vídeos dele são autorais. Fica desligada até ele ver um exemplo no
privado e ligar no painel (Shopee Vídeo 🎬 → Robô Automático 🤖 → Edição dos Vídeos ✂️;
chave edicao_ligada de shopee_video). Escolhas do Rafael (25/10/2026, P37 e depois da
P38): DECISOES.md, Shopee Vídeo.

Usado pelo robô automático (robo_shopee_video, na cópia do vídeo que vai ao rascunho) e
pelo painel da Shopee Vídeo (o exemplo).
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
# A miniatura no topo: largura em pixels no vídeo de 720 e a distância do alto.
LARGURA_DA_MINIATURA = 220
DISTANCIA_DO_ALTO = 60
# Uns minutos bastam para um vídeo curto; depois disso o rascunho segue sem a edição.
ESPERA_MAXIMA = 300
# Quantos vídeos o exemplo tenta até achar um com a foto do anúncio na API.
VIDEOS_TENTADOS = 10


def ligada():
    return bool((db.ler_config("shopee_video", {}) or {}).get("edicao_ligada"))


def vale_para(fonte):
    """A edição entra no vídeo desta fonte agora? Ligada, em qualquer fonte do robô."""
    return fonte in FONTES_COM_EDICAO and ligada()


def editar(video, foto, destino):
    """O vídeo editado com a foto (bytes) em destino: "" quando deu certo, ou o motivo fixo."""
    return videos.com_foto_e_miniatura(video, foto, destino, SEGUNDOS_DA_FOTO, LARGURA_DA_MINIATURA,
                                       DISTANCIA_DO_ALTO, ESPERA_MAXIMA)


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

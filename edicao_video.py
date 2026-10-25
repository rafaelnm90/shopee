#!/usr/bin/env python3
"""
A edição dos vídeos da Shopee Vídeo como o Rafael faz à mão no LumaFusion: a foto do
anúncio do produto nos primeiros segundos e uma miniatura dela no topo do vídeo inteiro
(a montagem fica no videos.com_foto_e_miniatura, com o resto do tratamento de vídeo).

Só nos vídeos do próprio Rafael (Autorais) e de fontes que liberam o uso para afiliados
(FONTES_COM_EDICAO); nunca nos vídeos de outras pessoas, como os do Viral. Fica desligada
até o Rafael ver um exemplo no privado e ligar no painel (Shopee Vídeo 🎬 → Robô
Automático 🤖 → Edição dos Vídeos ✂️; chave edicao_ligada de shopee_video). Escolha do
Rafael (25/10/2026, P37): DECISOES.md, Shopee Vídeo.

Usado pelo robô automático (robo_shopee_video, na cópia do vídeo que vai ao rascunho) e
pelo painel (o exemplo).
"""
import os

import assistente_shopee_video as assistente
import db
import postador_shopee_video as ps
import videos

# As fontes cujos vídeos são do Rafael ou liberados para afiliados. Fonte liberada nova
# (grupo ou criador que o Rafael disser) entra aqui.
FONTES_COM_EDICAO = ("autorais",)
# A foto do produto sozinha antes do vídeo, em segundos.
SEGUNDOS_DA_FOTO = 2
# A miniatura no topo: largura em pixels no vídeo de 720 e a distância do alto.
LARGURA_DA_MINIATURA = 220
DISTANCIA_DO_ALTO = 60
# Uns minutos bastam para um vídeo curto; depois disso o rascunho segue sem a edição.
ESPERA_MAXIMA = 300
# Quantos vídeos dos Autorais o exemplo tenta até achar um com a foto do anúncio na API.
VIDEOS_TENTADOS = 10


def ligada():
    return bool((db.ler_config("shopee_video", {}) or {}).get("edicao_ligada"))


def vale_para(fonte):
    """A edição entra no vídeo desta fonte agora? Só ligada e nas fontes do Rafael ou liberadas."""
    return fonte in FONTES_COM_EDICAO and ligada()


def editar(video, foto, destino):
    """O vídeo editado com a foto (bytes) em destino: "" quando deu certo, ou o motivo fixo."""
    return videos.com_foto_e_miniatura(video, foto, destino, SEGUNDOS_DA_FOTO, LARGURA_DA_MINIATURA,
                                       DISTANCIA_DO_ALTO, ESPERA_MAXIMA)


def exemplo(destino):
    """
    O exemplo para o Rafael aprovar antes de ligar: o vídeo mais novo dos Autorais que ainda
    tem o arquivo e o link no servidor (usado ou não), editado em destino. Devolve
    (nome do produto, "") quando deu certo, ou (None, motivo).
    """
    sem_foto = False
    for fonte in FONTES_COM_EDICAO:
        com_arquivo = [(arquivo, link) for _, arquivo, link, _ in assistente._candidatos(fonte)
                       if arquivo and link and os.path.exists(arquivo)
                       and not arquivo.lower().endswith(assistente.EXTENSOES_DE_IMAGEM)]
        for arquivo, link in com_arquivo[:VIDEOS_TENTADOS]:
            foto = ps.foto_do_produto({"link": link})
            if not foto:
                sem_foto = True
                continue
            motivo = editar(arquivo, foto, destino)
            if motivo:
                return None, motivo
            return ps.nome_do_produto({"link": link}) or "produto do link", ""
    if sem_foto:
        return None, "nenhum vídeo dos Autorais no servidor tem a foto do anúncio na API agora"
    return None, "nenhum vídeo dos Autorais com o arquivo e o link no servidor agora (os Autorais voltam com o chip novo)"

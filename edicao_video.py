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


def editar(video, foto, destino):
    """O vídeo editado com a foto (bytes) em destino: "" quando deu certo, ou o motivo fixo."""
    return videos.com_foto_e_miniatura(video, foto, destino, SEGUNDOS_DA_FOTO, LARGURA_DA_MINIATURA,
                                       CENTRO_DA_MINIATURA, SETA, CENTRO_DA_SETA, ESPERA_MAXIMA, PULSO_DA_SETA)


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


def exemplo(destino):
    """
    O exemplo para o Rafael ver a edição: o próximo vídeo que o robô pegaria para postar,
    editado em destino, sem postar e sem gastar o vídeo. Cada chamada pega um vídeo que o
    exemplo ainda não mostrou; sem nenhum novo com a foto do anúncio, recomeça pelos já
    mostrados. Devolve (nome do produto, "") quando deu certo, ou (None, motivo).
    """
    dados = db.ler_config(CHAVE_EXEMPLOS, {}) or {}
    mostrados, sem_foto = set(dados.get("ids", [])), set(dados.get("sem_foto", []))
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
            motivo = editar(arquivo, foto, destino)
            if motivo:
                return None, motivo
            _lembrar("ids", id_video, EXEMPLOS_LEMBRADOS, recomecar=recomecar)
            return ps.nome_do_produto({"link": link}) or "produto do link", ""
        if not mostrados:
            break
    if algum_sem_foto or _videos_do_exemplo(set()):
        return None, ("nenhum dos próximos vídeos tem a foto do anúncio na API agora (os de Ver Produtos, "
                      "com vários produtos, não têm uma foto só)")
    return None, "nenhum vídeo com o arquivo e o link no servidor agora"

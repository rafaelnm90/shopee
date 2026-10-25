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
# Ela começa com o vídeo, aparece se desenhando aos 1,6 s (por cima da foto, como na linha do
# tempo dele) e pulsa: o arquivo guarda a entrada e um pulso (quadros 111 a 140, 1,2 s), que
# se repete até o fim. Pedido do Rafael (25/10): DECISOES.md, Shopee Vídeo.
SETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "midia", "seta_da_shopee.apng")
CENTRO_DA_SETA = (142, 846)
PULSO_DA_SETA = (111, 30)
# Uns minutos bastam para um vídeo curto; depois disso o rascunho segue sem a edição.
ESPERA_MAXIMA = 300
# Quantos vídeos o exemplo tenta até achar um com a foto do anúncio na API.
VIDEOS_TENTADOS = 10
# Os vídeos já mostrados no exemplo (os ids da fonte): cada toque mostra um vídeo novo, e
# quando todos já foram mostrados a lista recomeça. Pedido do Rafael (25/10): DECISOES.md.
CHAVE_EXEMPLOS = "edicao_exemplos_mostrados"
EXEMPLOS_LEMBRADOS = 100


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


def _videos_do_exemplo(mostrados):
    """
    (id, arquivo, link) dos próximos vídeos que o robô pegaria para postar (os ainda não
    usados, do mais novo para o mais velho), sem os que o exemplo já mostrou.
    """
    achados = []
    for fonte in _fontes_do_exemplo():
        for id_video, arquivo, link, _ in assistente.candidatos_nao_usados(fonte):
            if (id_video not in mostrados and arquivo and link and os.path.exists(arquivo)
                    and not arquivo.lower().endswith(assistente.EXTENSOES_DE_IMAGEM)):
                achados.append((id_video, arquivo, link))
            if len(achados) >= VIDEOS_TENTADOS:
                return achados
    return achados


def _lembrar_mostrado(id_video):
    def alterar(dados):
        dados["ids"] = (dados.get("ids", []) + [id_video])[-EXEMPLOS_LEMBRADOS:]
    db.atualizar_config(CHAVE_EXEMPLOS, alterar)


def exemplo(destino):
    """
    O exemplo para o Rafael ver a edição: o próximo vídeo que o robô pegaria para postar,
    editado em destino, sem postar e sem gastar o vídeo. Cada chamada pega um vídeo que o
    exemplo ainda não mostrou; mostrados todos, recomeça. Devolve (nome do produto, "")
    quando deu certo, ou (None, motivo).
    """
    mostrados = set((db.ler_config(CHAVE_EXEMPLOS, {}) or {}).get("ids", []))
    videos_do_exemplo = _videos_do_exemplo(mostrados)
    if not videos_do_exemplo and mostrados:
        db.salvar_config(CHAVE_EXEMPLOS, {"ids": []})
        videos_do_exemplo = _videos_do_exemplo(set())
    sem_foto = False
    for id_video, arquivo, link in videos_do_exemplo:
        foto = ps.foto_do_produto({"link": link})
        if not foto:
            sem_foto = True
            continue
        motivo = editar(arquivo, foto, destino)
        if motivo:
            return None, motivo
        _lembrar_mostrado(id_video)
        return ps.nome_do_produto({"link": link}) or "produto do link", ""
    if sem_foto:
        return None, "nenhum dos próximos vídeos tem a foto do anúncio na API agora"
    return None, "nenhum vídeo com o arquivo e o link no servidor agora"

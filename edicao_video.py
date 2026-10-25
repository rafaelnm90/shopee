#!/usr/bin/env python3
"""
A edição dos vídeos da Shopee Vídeo como o Rafael faz à mão no LumaFusion: a foto do
anúncio do produto nos primeiros segundos e uma miniatura dela no topo do vídeo inteiro
(a montagem fica no videos.com_foto_e_miniatura, com o resto do tratamento de vídeo).

Só nos vídeos autorais: os do Rafael (Autorais, FONTES_COM_EDICAO) e os do Viral que
vêm de um grupo que ele marcou como autoral no Espião (quem grava libera os vídeos para
afiliados postarem; chave grupos_autorais). Vídeo de grupo não marcado não é editado. Fica
desligada até o Rafael ver um exemplo no privado e ligar no painel (Shopee Vídeo 🎬 →
Robô Automático 🤖 → Edição dos Vídeos ✂️; chave edicao_ligada de shopee_video). Escolhas
do Rafael (25/10/2026, P37 e P38): DECISOES.md, Shopee Vídeo.

Usado pelo robô automático (robo_shopee_video, na cópia do vídeo que vai ao rascunho), pelo
painel da Shopee Vídeo (o exemplo) e pelo painel do Espião (marcar os grupos autorais).
"""
import os

import assistente_shopee_video as assistente
import db
import links_grupos
import postador_shopee_video as ps
import videos

# As fontes cujos vídeos são todos do Rafael. Os do Viral entram um grupo de cada vez,
# pela marca de grupo autoral do Espião (CHAVE_GRUPOS).
FONTES_COM_EDICAO = ("autorais",)
CHAVE_GRUPOS = "grupos_autorais"
# A foto do produto sozinha antes do vídeo, em segundos.
SEGUNDOS_DA_FOTO = 2
# A miniatura no topo: largura em pixels no vídeo de 720 e a distância do alto.
LARGURA_DA_MINIATURA = 220
DISTANCIA_DO_ALTO = 60
# Uns minutos bastam para um vídeo curto; depois disso o rascunho segue sem a edição.
ESPERA_MAXIMA = 300
# Quantos vídeos autorais o exemplo tenta até achar um com a foto do anúncio na API.
VIDEOS_TENTADOS = 10


def ligada():
    return bool((db.ler_config("shopee_video", {}) or {}).get("edicao_ligada"))


def grupos_autorais():
    """Os grupos do Espião marcados como autorais, como estão na lista do Espião (minúsculas)."""
    return list((db.ler_config(CHAVE_GRUPOS, {}) or {}).get("espiao", []))


def alternar_grupos(alvos):
    """Marca os grupos que não estavam marcados e desmarca os que estavam: (marcados, desmarcados)."""
    def alterar(dados):
        atuais = [str(a).lower() for a in dados.get("espiao", [])]
        marcados, desmarcados = [], []
        for alvo in alvos:
            chave = str(alvo).lower()
            if chave in atuais:
                atuais.remove(chave)
                desmarcados.append(alvo)
            else:
                atuais.append(chave)
                marcados.append(alvo)
        dados["espiao"] = atuais
        return marcados, desmarcados
    return db.atualizar_config(CHAVE_GRUPOS, alterar) or ([], [])


def _numero(texto):
    """O número do grupo sem o -100 e sem sinal: o Espião guarda "-100123", a lista pode ter "123"."""
    texto = str(texto or "").lower()
    return (texto[4:] if texto.startswith("-100") else texto).lstrip("-")


def do_grupo_autoral(chat_origem, marcados=None):
    """
    O grupo de onde o Espião pegou o vídeo (chat_origem, "-100123") está marcado como
    autoral? Vale o grupo inteiro: o vídeo não guarda o tópico.
    """
    if not chat_origem:
        return False
    marcados = grupos_autorais() if marcados is None else marcados
    numero = _numero(chat_origem)
    arroba = None
    for alvo in marcados:
        base = str(alvo).lower().split(":")[0]
        if base.startswith("@"):
            if arroba is None:
                arroba = (links_grupos.arroba(chat_origem) or "").lower()
            if base == arroba:
                return True
        elif _numero(base) == numero:
            return True
    return False


def grupo_do_viral(id_video):
    """O grupo de origem (chat_origem) de um vídeo do Viral ("viral:clone_..."), ou "" se ele saiu da fila."""
    clone = str(id_video or "").split(":", 1)[-1]
    for item in (db.ler_config("fila_clonagem", {"fila": []}) or {}).get("fila", []):
        if str(item.get("id")) == clone:
            return str(item.get("chat_origem") or "")
    return ""


def vale_para(fonte, video=None):
    """
    A edição entra neste vídeo agora? Só ligada, nos Autorais e nos vídeos do Viral que
    vêm de um grupo marcado como autoral.
    """
    if not ligada():
        return False
    if fonte in FONTES_COM_EDICAO:
        return True
    return fonte == "viral" and bool(video) and do_grupo_autoral(grupo_do_viral(video.get("id")))


def editar(video, foto, destino):
    """O vídeo editado com a foto (bytes) em destino: "" quando deu certo, ou o motivo fixo."""
    return videos.com_foto_e_miniatura(video, foto, destino, SEGUNDOS_DA_FOTO, LARGURA_DA_MINIATURA,
                                       DISTANCIA_DO_ALTO, ESPERA_MAXIMA)


def _videos_autorais():
    """(arquivo, link) dos vídeos que a edição pode usar: os Autorais e, depois, os do Viral dos grupos marcados."""
    marcados = grupos_autorais()
    origens = {str(item.get("id")): str(item.get("chat_origem") or "")
               for item in (db.ler_config("fila_clonagem", {"fila": []}) or {}).get("fila", [])}
    videos_bons = []
    for fonte in FONTES_COM_EDICAO + (("viral",) if marcados else ()):
        for id_video, arquivo, link, _ in assistente._candidatos(fonte):
            if fonte == "viral" and not do_grupo_autoral(origens.get(id_video.split(":", 1)[-1]), marcados):
                continue
            if (arquivo and link and os.path.exists(arquivo)
                    and not arquivo.lower().endswith(assistente.EXTENSOES_DE_IMAGEM)):
                videos_bons.append((arquivo, link))
    return videos_bons


def exemplo(destino):
    """
    O exemplo para o Rafael aprovar antes de ligar: o vídeo autoral mais novo (dos Autorais,
    depois dos grupos autorais do Viral) que ainda tem o arquivo e o link no servidor (usado
    ou não), editado em destino. Devolve (nome do produto, "") quando deu certo, ou (None, motivo).
    """
    sem_foto = False
    for arquivo, link in _videos_autorais()[:VIDEOS_TENTADOS]:
        foto = ps.foto_do_produto({"link": link})
        if not foto:
            sem_foto = True
            continue
        motivo = editar(arquivo, foto, destino)
        if motivo:
            return None, motivo
        return ps.nome_do_produto({"link": link}) or "produto do link", ""
    if sem_foto:
        return None, "nenhum vídeo autoral no servidor tem a foto do anúncio na API agora"
    return None, ("nenhum vídeo autoral com o arquivo e o link no servidor agora (os Autorais voltam com o chip "
                  "novo; os do Viral entram quando você marcar os grupos autorais no Espião)")

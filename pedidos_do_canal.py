"""
Os vídeos do robô da Shopee Vídeo que vão ao Canal Afiliados (o canal principal) depois
de postados: o robô (robo_shopee_video, que roda à parte do bot) deixa aqui o pedido,
com uma cópia do vídeo, o link do post e os links dos produtos, e o bot_mestre, que
cuida da fila do canal, põe o vídeo na fila no padrão do canal
(levar_videos_do_robo_ao_canal). Os pedidos ficam na chave canal_afiliados_do_robo de
configuracoes, gravada sem um processo apagar o que o outro gravou (db.atualizar_config).
A cópia que sobra sai na faxina do disco do bot_mestre (faxina), e o checkup cobra o
pedido que demora a entrar na fila (parados).
Decisões do Rafael (28/10, P62 a P64): DECISOES.md, Canal principal.

Contra o loop (pedido do Rafael, 30/10): o Espião traz o canal para a fila do Viral, e o
robô e o modo assistente pegam os vídeos do Viral. Eles deixam de fora o que veio do canal
(CANAL) e o arquivo que o robô já levou ao canal (ja_foi_ao_canal, pela marca guardada no
pedido), venha de onde vier.

O mesmo vídeo vai também ao Grupo Público (P320 2), na janela dos reposts do grupo (P322 1): o
bot_mestre guarda aqui, junto do pedido do canal, a cópia, o nome e o link do post de cada um
(guardar_para_o_publico, na lista "publico" da mesma chave) e o leva ao grupo quando a janela
abre (para_o_publico, tirar_do_publico). Decisões do Rafael: DECISOES.md, Canal principal.
"""
import os
import shutil
import time
from datetime import datetime, time as hora_do_dia, timedelta

import db
import videos
from fuso import fuso_horario

CHAVE = "canal_afiliados_do_robo"
# O Canal Afiliados (@shopee_video_afiliado), pelo id com que o Espião guarda a origem do que
# pega dele (chat_origem da fila do Viral).
CANAL = "-1003909405581"
# As marcas (SHA-256) dos arquivos que o robô levou ao canal: o mesmo vídeo que volta por outro
# caminho (o canal espelhado num grupo que o Espião vigia) é reconhecido pelo arquivo. Ficam as
# MARCAS_GUARDADAS mais novas.
MARCAS_GUARDADAS = 500
# A cópia do vídeo fica aqui até ir ao ar: a fila do canal a apaga depois do post, e a do
# rascunho o robô apaga sozinho depois de usada.
PASTA = os.path.expanduser("~/shopee_video/canal")
# A cópia que saiu da fila sem ir ao ar (o Rafael a excluiu, ou o envio deu erro) sai na
# faxina do disco do bot_mestre depois deste prazo: antes dele, a cópia pode estar entre o
# robô copiar o vídeo e guardar o pedido.
HORAS_PROTEGIDAS = 24


def pedir(ident, arquivo, link_post, links, produto="", agora=None):
    """
    Guarda o pedido do rascunho ident, com uma cópia do vídeo. O mesmo rascunho pedido de
    novo troca o pedido, não dobra. Devolve o caminho da cópia.
    """
    os.makedirs(PASTA, exist_ok=True)
    copia = os.path.join(PASTA, f"{ident}.mp4")
    shutil.copyfile(arquivo, copia)
    marca = videos.calcular_hash_video(copia)
    pedido = {"id": ident, "arquivo": copia, "link_post": link_post, "links": list(links or []),
              "produto": produto or "", "tentativas": 0,
              "pedido_em": (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d %H:%M:%S")}

    def trocar(dados):
        dados["pedidos"] = [p for p in dados.get("pedidos", []) if p.get("id") != ident] + [pedido]
        marcas = dados.get("marcas", [])
        if marca and marca not in marcas:
            dados["marcas"] = (marcas + [marca])[-MARCAS_GUARDADAS:]
    db.atualizar_config(CHAVE, trocar)
    return copia


def ja_foi_ao_canal(arquivo):
    """True se o arquivo é o de um vídeo que o robô levou ao canal (pela marca do pedido)."""
    marcas = db.ler_config(CHAVE, {}).get("marcas", [])
    return bool(marcas) and videos.calcular_hash_video(arquivo) in marcas


def pendentes():
    """Os pedidos que ainda não entraram na fila do canal, do mais velho para o mais novo."""
    return list(db.ler_config(CHAVE, {}).get("pedidos", []))


def atualizar(ident, **campos):
    """Muda campos do pedido (o número reservado, as tentativas)."""
    def mudar(dados):
        for pedido in dados.get("pedidos", []):
            if pedido.get("id") == ident:
                pedido.update(campos)
    db.atualizar_config(CHAVE, mudar)


def concluir(ident):
    """Tira o pedido da lista: entrou na fila do canal ou ficou de fora de vez."""
    def tirar(dados):
        dados["pedidos"] = [p for p in dados.get("pedidos", []) if p.get("id") != ident]
    db.atualizar_config(CHAVE, tirar)


def parados(minutos, agora=None):
    """Quantos pedidos esperam há mais de `minutos` para entrar na fila do canal (o checkup cobra)."""
    limite = ((agora or datetime.now(fuso_horario)) - timedelta(minutes=minutos)).strftime("%Y-%m-%d %H:%M:%S")
    return sum(1 for pedido in pendentes() if (pedido.get("pedido_em") or "") <= limite)


def guardar_para_o_publico(ident, arquivo, nome, link, agora=None):
    """
    Guarda o vídeo do rascunho ident para o Grupo Público (P320 2): uma cópia própria (a da fila do canal sai depois
    do post no canal), o nome do produto, o link do post e quando ficou pronto para o grupo (guardado_em), de onde
    sai o prazo dele (fim_da_primeira_janela). O mesmo rascunho guardado de novo troca, não dobra. Devolve o caminho
    da cópia.
    """
    os.makedirs(PASTA, exist_ok=True)
    copia = os.path.join(PASTA, f"{ident}_publico.mp4")
    shutil.copyfile(arquivo, copia)
    entrada = {"id": ident, "arquivo": copia, "nome": nome or "", "link": link or "", "tentativas": 0,
               "guardado_em": (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d %H:%M:%S")}

    def trocar(dados):
        dados["publico"] = [p for p in dados.get("publico", []) if p.get("id") != ident] + [entrada]
    db.atualizar_config(CHAVE, trocar)
    return copia


def para_o_publico():
    """Os vídeos do robô que esperam a vez de ir ao Grupo Público, do mais velho para o mais novo."""
    return list(db.ler_config(CHAVE, {}).get("publico", []))


def atualizar_no_publico(ident, **campos):
    """Muda campos do vídeo que espera o Grupo Público (as tentativas)."""
    def mudar(dados):
        for entrada in dados.get("publico", []):
            if entrada.get("id") == ident:
                entrada.update(campos)
    db.atualizar_config(CHAVE, mudar)


def tirar_do_publico(ident, enviado_em=None):
    """
    Tira o vídeo da espera do Grupo Público e apaga a cópia dele: foi ao grupo (enviado_em, "AAAA-MM-DD HH:MM:SS",
    que ultimo_envio_ao_publico devolve depois) ou ficou de fora de vez.
    """
    arquivos = []

    def tirar(dados):
        arquivos.extend(p.get("arquivo") for p in dados.get("publico", []) if p.get("id") == ident)
        dados["publico"] = [p for p in dados.get("publico", []) if p.get("id") != ident]
        if enviado_em:
            dados["publico_ultimo_envio"] = enviado_em
    db.atualizar_config(CHAVE, tirar)
    for arquivo in arquivos:
        try:
            os.remove(arquivo)
        except (OSError, TypeError):
            pass


def ultimo_envio_ao_publico():
    """Quando o último vídeo do robô foi ao Grupo Público ("AAAA-MM-DD HH:MM:SS"), ou "" se nenhum foi."""
    return db.ler_config(CHAVE, {}).get("publico_ultimo_envio", "")


def fim_da_primeira_janela(desde, fim):
    """
    O fim (a hora fim) da 1ª janela dos reposts do Grupo Público que ainda não fechou em desde (datetime, quando o
    vídeo ficou pronto para o grupo): o pronto antes do fim da janela do dia vai nela; o pronto depois, na do dia
    seguinte (P322 1). O vídeo que passa dela sem ir ao grupo (a Repostagem pausada ou o painel desligado o tempo
    todo) fica de fora.
    """
    dia = desde.date() if desde.hour < fim else desde.date() + timedelta(days=1)
    return datetime.combine(dia, hora_do_dia(0), tzinfo=desde.tzinfo) + timedelta(hours=fim)


def faxina():
    """
    Apaga da PASTA as cópias que nem um pedido, nem um vídeo que espera o Grupo Público, nem um vídeo pendente da
    fila do canal usam mais, passadas HORAS_PROTEGIDAS. Devolve (quantas, bytes).
    """
    if not os.path.isdir(PASTA):
        return 0, 0
    em_uso = {os.path.abspath(pedido["arquivo"]) for pedido in pendentes() + para_o_publico() if pedido.get("arquivo")}
    with db.conexao() as conexao:
        em_uso |= {os.path.abspath(caminho) for (caminho,) in conexao.execute(
            "SELECT caminho_video FROM fila_postagens WHERE status = 'PENDENTE' AND caminho_video IS NOT NULL")}
    limite = time.time() - HORAS_PROTEGIDAS * 3600
    removidos = liberados = 0
    for nome in os.listdir(PASTA):
        caminho = os.path.abspath(os.path.join(PASTA, nome))
        try:
            if caminho in em_uso or os.path.getmtime(caminho) > limite:
                continue
            tamanho = os.path.getsize(caminho)
            os.remove(caminho)
        except OSError:
            continue
        removidos += 1
        liberados += tamanho
    return removidos, liberados

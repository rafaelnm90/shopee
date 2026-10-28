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
"""
import os
import shutil
import time
from datetime import datetime, timedelta

import db
from fuso import fuso_horario

CHAVE = "canal_afiliados_do_robo"
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
    pedido = {"id": ident, "arquivo": copia, "link_post": link_post, "links": list(links or []),
              "produto": produto or "", "tentativas": 0,
              "pedido_em": (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d %H:%M:%S")}

    def trocar(dados):
        dados["pedidos"] = [p for p in dados.get("pedidos", []) if p.get("id") != ident] + [pedido]
    db.atualizar_config(CHAVE, trocar)
    return copia


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


def faxina():
    """
    Apaga da PASTA as cópias que nem um pedido nem um vídeo pendente da fila do canal
    usam mais, passadas HORAS_PROTEGIDAS. Devolve (quantas, bytes).
    """
    if not os.path.isdir(PASTA):
        return 0, 0
    em_uso = {os.path.abspath(pedido["arquivo"]) for pedido in pendentes() if pedido.get("arquivo")}
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

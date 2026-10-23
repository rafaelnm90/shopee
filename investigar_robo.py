#!/usr/bin/env python3
"""
Investiga no servidor por que o robô automático da Shopee Vídeo não acha o produto de um
vídeo ("o link não diz o produto do vídeo"). Para os vídeos que o robô pulou e para os
próximos da Fonte dos Vídeos do painel, segue o link como o robô segue e mostra só a
forma: por que tipos de página ele passou, se chegou a um produto ou a um vídeo (Ver
Produtos) e se a API de afiliado devolve a oferta do produto. No fim, as contagens.

Usado pelo workflow investigar_robo.yml (só à mão). O log do Actions é público: nunca
imprime links, nomes de produto, motivos ou textos; só tipos de página e contagens.

    python3 investigar_robo.py [QUANTOS]   # os pulados e os QUANTOS próximos (padrão 15)
"""
import asyncio
import logging
import re
import sys
from collections import Counter

import api_shopee
import assistente_shopee_video as assistente
import db

PADRAO_PROXIMOS = 15


async def classificar(link):
    """(resultado em poucas palavras, tipos de página por onde o link passou)."""
    caminho = await api_shopee.seguir_link(link)
    tipos = [api_shopee.tipo_de_link(endereco) for endereco in caminho]
    destino = await api_shopee.link_para_converter(link)
    if api_shopee.eh_video(destino):
        return "link de vídeo (Ver Produtos)", tipos
    produto = api_shopee.produto_do_link(destino)
    if not produto:
        return f"não chega a um produto (parou em: {api_shopee.tipo_de_link(destino)})", tipos
    loja, item = re.search(r"/product/(\d+)/(\d+)", produto).groups()
    if await assistente._consultar_produto(loja, item):
        return "produto com oferta na API de afiliado", tipos
    return "produto SEM oferta na API de afiliado", tipos


def links_das_fontes():
    """id do vídeo → link, de todas as fontes (os pulados podem ser de uma fonte antiga)."""
    links = {}
    for fonte in assistente.FONTES:
        try:
            for id_video, _, link, _ in assistente._candidatos(fonte):
                links[id_video] = link
        except Exception as e:
            print(f"   fonte {fonte}: não deu para ler ({type(e).__name__})")
    return links


def pulados():
    """
    (id do vídeo, passo em que parou) dos vídeos que o robô pulou. O passo é o rótulo fixo
    do histórico do robô (robo_shopee_video.passo_do_motivo), nunca o motivo, que pode ter
    o nome do produto.
    """
    import robo_shopee_video as robo   # aqui dentro: o robô traz a IA e o celular junto
    with db.conexao() as con:
        try:
            linhas = con.execute("SELECT id_video, motivo FROM shopee_video_rascunhos WHERE estado = 'pulado' "
                                 "ORDER BY id DESC").fetchall()
        except Exception:
            return []
    return [(id_video, robo.passo_do_motivo(motivo) or "sem motivo") for id_video, motivo in linhas]


def proximos(quantos):
    """Os próximos vídeos da fonte do painel que nem o assistente mandou nem o robô usou."""
    fonte = (db.ler_config("shopee_video", {}) or {}).get("fonte", assistente.FONTE_PADRAO)
    escolhidos = [link for _, arquivo, link, _ in assistente.candidatos_nao_usados(fonte) if link and arquivo]
    return fonte, escolhidos[:quantos]


async def investigar(quantos):
    contagem = Counter()
    links = links_das_fontes()
    lista = pulados()
    print(f"== Vídeos que o robô pulou: {len(lista)}")
    for i, (id_video, passo) in enumerate(lista, 1):
        motivo = f"parou em {passo}"
        link = links.get(id_video)
        if not link:
            print(f"   {i}. motivo: {motivo} | o vídeo já saiu da fonte")
            continue
        resultado, tipos = await classificar(link)
        contagem[f"pulado ({motivo}): {resultado}"] += 1
        print(f"   {i}. motivo: {motivo} | caminho: {' → '.join(tipos)} | {resultado}")

    fonte, links_proximos = proximos(quantos)
    print(f"== Próximos {len(links_proximos)} vídeos da fonte ({fonte})")
    for i, link in enumerate(links_proximos, 1):
        resultado, tipos = await classificar(link)
        contagem[f"próximo: {resultado}"] += 1
        print(f"   {i}. caminho: {' → '.join(tipos)} | {resultado}")

    print("== Contagem")
    for resultado, n in sorted(contagem.items()):
        print(f"   {n} × {resultado}")


def main(argumentos):
    if len(argumentos) > 1 or (argumentos and not argumentos[0].isdigit()):
        print(__doc__)
        return 2
    # Os módulos logam links e nomes; aqui o log é público, e o resultado sai pelos prints.
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(investigar(int(argumentos[0]) if argumentos else PADRAO_PROXIMOS))
    finally:
        logging.disable(logging.NOTSET)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

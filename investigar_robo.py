#!/usr/bin/env python3
"""
Investiga no servidor por que o robô automático da Shopee Vídeo não acha o produto de um
vídeo ("o link não diz o produto do vídeo"). Para os vídeos que o robô pulou e para os
próximos da Fonte dos Vídeos do painel, segue o link como o robô segue e mostra só a
forma: por que tipos de página ele passou, se chegou a um produto ou a um vídeo (Ver
Produtos), se a API de afiliado devolve a oferta do produto e, nos próximos, se a busca
acha o mesmo produto pagando mais comissão (P33, sem a IA). No fim, as contagens. Antes,
cada tentativa das últimas 24 h que não deu certo, com a hora, o passo e a forma do
motivo (o texto fixo do código, com "…" no que muda de um vídeo para outro).

Usado pelo workflow investigar_robo.yml (só à mão). O log do Actions é público: nunca
imprime links, nomes de produto ou textos; só tipos de página, contagens e o motivo do
pulo quando ele é um texto fixo do código (sem nada do vídeo ou do produto).

    python3 investigar_robo.py [QUANTOS]   # os pulados e os QUANTOS próximos (padrão 15)
"""
import ast
import asyncio
import logging
import os
import re
import sys
from collections import Counter
from datetime import timedelta

import api_shopee
import assistente_shopee_video as assistente
import db

PADRAO_PROXIMOS = 15
PASTA = os.path.dirname(os.path.abspath(__file__))
# Onde nascem os motivos do robô (as Paradas dele e as respostas do postador).
ARQUIVOS_DOS_MOTIVOS = ("robo_shopee_video.py", "postador_shopee_video.py")


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


async def comissao(link):
    """
    O que a troca pelo mesmo produto que paga mais (P33) acharia, sem a IA e sem o celular:
    quantos vieram na busca por maior comissão, quantos de nome parecido pagam mais que o do
    link e quantos pontos a mais paga o melhor. Só números.
    """
    import robo_shopee_video as robo
    produtos, _ = await assistente.produtos_do_link(link)
    if not produtos:
        return "comissão: a API não diz o produto", False
    original = produtos[0]
    ofertas = await api_shopee.buscar_ofertas_shopee(robo.termo_da_busca(original["nome"]),
                                                     limite=robo.OFERTAS_NA_BUSCA, sort_type=5)
    sem_taxa = sum(1 for oferta in ofertas if not oferta.get("commissionRate"))
    candidatos = robo.candidatos_de_mais_comissao(original, ofertas)
    texto = f"comissão: {len(ofertas)} na busca ({sem_taxa} sem a taxa)"
    if not candidatos:
        return f"{texto}, nenhum parecido pagando mais", False
    return (f"{texto}, {len(candidatos)} parecido(s) pagando mais (o melhor: "
            f"+{candidatos[0]['comissao'] - original['comissao']:.1f} ponto(s))"), True


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


def textos_fixos():
    """
    Os textos escritos inteiros no código do robô e do postador (fora os pedaços de
    f-string, que levam o nome do produto). Motivo igual a um deles é texto público do
    repositório e pode sair no log.
    """
    textos = set()
    for arquivo in ARQUIVOS_DOS_MOTIVOS:
        with open(os.path.join(PASTA, arquivo), encoding="utf-8") as f:
            arvore = ast.parse(f.read())
        de_f_string = {id(parte) for no in ast.walk(arvore) if isinstance(no, ast.JoinedStr) for parte in no.values}
        textos |= {no.value for no in ast.walk(arvore)
                   if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in de_f_string}
    return textos


def moldes_fixos():
    """
    As frases montadas no código do robô e do postador (f-strings), como (regex, molde): o
    molde é o texto fixo com "…" no lugar do que muda, e a regex reconhece um motivo
    montado por ela. As de texto fixo mais longo primeiro: dizem mais do motivo.
    """
    moldes = []
    for arquivo in ARQUIVOS_DOS_MOTIVOS:
        with open(os.path.join(PASTA, arquivo), encoding="utf-8") as f:
            arvore = ast.parse(f.read())
        for no in ast.walk(arvore):
            if not isinstance(no, ast.JoinedStr):
                continue
            partes = [parte.value if isinstance(parte, ast.Constant) else None for parte in no.values]
            fixo = "".join(parte for parte in partes if parte)
            if len(fixo) < 12:
                continue
            regex = "".join(re.escape(parte) if parte is not None else ".+?" for parte in partes)
            moldes.append((len(fixo), re.compile(regex + "$", re.S),
                           "".join(parte if parte is not None else "…" for parte in partes)))
    return [(regex, molde) for _, regex, molde in sorted(moldes, key=lambda m: -m[0])]


def forma_do_motivo(motivo, fixos, moldes):
    """O motivo como pode sair no log: inteiro se é texto fixo do código; senão o molde que o montou; senão ""."""
    if not motivo or motivo in fixos:
        return motivo or ""
    return next((molde for regex, molde in moldes if regex.match(motivo)), "")


# Os resultados que deram certo (o resto entra na lista do que não deu).
DERAM_CERTO = ("salvo", "postado", "apagado", "treino ok", "saúde lida", "respondido", "comentado", "descurtido")


def tentativas_que_nao_deram_certo():
    """(hora, ação, resultado, passo, forma do motivo) das últimas 24 h, da mais velha para a mais nova."""
    import robo_shopee_video as robo   # aqui dentro: o robô traz a IA e o celular junto
    desde = robo._momento(robo.agora_br() - timedelta(hours=24))
    with db.conexao() as con:
        try:
            linhas = con.execute(
                "SELECT momento, acao, resultado, passo, motivo FROM shopee_video_tentativas WHERE momento >= ? "
                f"AND resultado NOT IN ({','.join('?' * len(DERAM_CERTO))}) ORDER BY momento",
                (desde, *DERAM_CERTO)).fetchall()
        except Exception:
            return []
    fixos, moldes = textos_fixos(), moldes_fixos()
    return [(momento[5:16], acao, resultado, passo or "outro", forma_do_motivo(motivo, fixos, moldes))
            for momento, acao, resultado, passo, motivo in linhas]


def pulados():
    """
    (id do vídeo, passo em que parou, motivo) dos vídeos que o robô pulou. O passo é o
    rótulo fixo do histórico do robô (robo_shopee_video.passo_do_motivo); o motivo vem só
    quando é um texto fixo do código (textos_fixos), senão "", porque pode ter o nome do
    produto.
    """
    import robo_shopee_video as robo   # aqui dentro: o robô traz a IA e o celular junto
    with db.conexao() as con:
        try:
            linhas = con.execute("SELECT id_video, motivo FROM shopee_video_rascunhos WHERE estado = 'pulado' "
                                 "ORDER BY id DESC").fetchall()
        except Exception:
            return []
    fixos = textos_fixos()
    return [(id_video, robo.passo_do_motivo(motivo) or "sem motivo", motivo if motivo in fixos else "")
            for id_video, motivo in linhas]


def proximos(quantos):
    """Os próximos vídeos da fonte do painel que nem o assistente mandou nem o robô usou."""
    fonte = (db.ler_config("shopee_video", {}) or {}).get("fonte", assistente.FONTE_PADRAO)
    escolhidos = [link for _, arquivo, link, _ in assistente.candidatos_nao_usados(fonte) if link and arquivo]
    return fonte, escolhidos[:quantos]


async def investigar(quantos):
    contagem = Counter()
    ruins = tentativas_que_nao_deram_certo()
    print(f"== Tentativas das últimas 24 h que não deram certo: {len(ruins)}")
    for quando, acao, resultado, passo, forma in ruins:
        print(f"   {quando} {acao} → {resultado} em {passo}" + (f": {forma}" if forma else ""))
    links = links_das_fontes()
    lista = pulados()
    print(f"== Vídeos que o robô pulou: {len(lista)}")
    for i, (id_video, passo, fixo) in enumerate(lista, 1):
        motivo = f"parou em {passo}" + (f" ({fixo})" if fixo else "")
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
        extra = ""
        if resultado == "produto com oferta na API de afiliado":
            extra, achou = await comissao(link)
            contagem["próximo: há o mesmo produto pagando mais" if achou else "próximo: nenhum pagando mais"] += 1
            extra = f" | {extra}"
        print(f"   {i}. caminho: {' → '.join(tipos)} | {resultado}{extra}")

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

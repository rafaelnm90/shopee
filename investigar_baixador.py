#!/usr/bin/env python3
"""
Investiga no servidor por que o Baixador (downloader_bot) não acha o vídeo de um link da
Shopee Vídeo. Abre a página como o Baixador abre e mostra só a forma dela: status, hosts,
tamanhos e onde há vídeo no JSON da página. Depois roda o próprio baixar_video_shopee e
diz se deu certo (tamanho e dimensões do arquivo) ou o erro.

Usado pelo workflow investigar_baixador.yml (só à mão). O log do Actions é público:
nunca imprime links, nomes, textos da página nem valores do JSON, só caminhos de chave
(com números e códigos trocados por # e …) e contagens.

    python3 investigar_baixador.py ID_DO_VIDEO   # o que vem depois de share-video/ no link
"""
import asyncio
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import urllib.parse

import downloader_bot as dl
import videos

URL_DO_VIDEO = "https://sv.shopee.com.br/share-video/{id}"
MAXIMO_CAMINHOS = 40


def chave_segura(chave):
    """Nome de chave do JSON como está; número vira #; código ou texto longo vira …"""
    chave = str(chave)
    if re.fullmatch(r"\d+", chave):
        return "#"
    return chave if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,39}", chave) else "…"


def tipo_de_video(valor):
    """mp4, m3u8 ou None: o tipo do endereço, sem o endereço."""
    baixo = valor.lower()
    if ".m3u8" in baixo:
        return "m3u8"
    if ".mp4" in baixo:
        return "mp4"
    return None


def caminhos_de_video(dados, caminho="$"):
    """(caminho da chave, tipo) de cada valor do JSON que é um endereço de vídeo."""
    if isinstance(dados, dict):
        for chave, valor in dados.items():
            yield from caminhos_de_video(valor, f"{caminho}.{chave_segura(chave)}")
    elif isinstance(dados, list):
        for i, item in enumerate(dados):
            yield from caminhos_de_video(item, f"{caminho}[{i}]")
    elif isinstance(dados, str) and dados.startswith("http"):
        tipo = tipo_de_video(dados)
        if tipo:
            yield caminho, tipo


def forma_do_endereco(url):
    """host e caminho com os pedaços longos (ids) trocados por …, sem a consulta."""
    partes = urllib.parse.urlparse(str(url))
    pedacos = ["…" if len(p) > 12 else p for p in partes.path.split("/")]
    return f"{partes.netloc}{'/'.join(pedacos)}"


def blocos_json(html):
    """Os JSON embutidos que o Baixador lê: __INITIAL_STATE__ e __NEXT_DATA__."""
    blocos = {}
    achado = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});\s*</script>', html, re.DOTALL)
    if achado:
        blocos["__INITIAL_STATE__"] = achado.group(1)
    achado = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if achado:
        blocos["__NEXT_DATA__"] = achado.group(1)
    return blocos


def descrever_pagina(html):
    linhas = [f"página: {len(html)} caracteres; .mp4 no HTML: {html.lower().count('.mp4')}; "
              f".m3u8: {html.lower().count('.m3u8')}; 'watermark': {html.lower().count('watermark')}; "
              f"scripts: {html.lower().count('<script')}"]
    blocos = blocos_json(html)
    if not blocos:
        linhas.append("nenhum JSON embutido (__INITIAL_STATE__ ou __NEXT_DATA__)")
    for nome, bruto in blocos.items():
        try:
            dados = json.loads(bruto)
        except ValueError:
            linhas.append(f"{nome}: não decodificou")
            continue
        achados = list(caminhos_de_video(dados))
        linhas.append(f"{nome}: {len(bruto)} caracteres, {len(achados)} endereço(s) de vídeo")
        linhas += [f"   {caminho} ({tipo})" for caminho, tipo in achados[:MAXIMO_CAMINHOS]]
    return linhas


async def investigar(id_video):
    import aiohttp
    url = URL_DO_VIDEO.format(id=id_video)
    print("== A página, como o Baixador abre")
    async with aiohttp.ClientSession(headers=dl.CABECALHO_NAVEGADOR) as sessao:
        async with sessao.get(url, allow_redirects=True, timeout=25) as resposta:
            for passo in resposta.history:
                print(f"redirecionou: HTTP {passo.status} {forma_do_endereco(passo.url)}")
            print(f"chegou em: HTTP {resposta.status} {forma_do_endereco(resposta.url)}")
            html = await resposta.text()
    for linha in descrever_pagina(html):
        print(linha)

    print("== O Baixador com este link")
    pasta = tempfile.mkdtemp()
    try:
        caminho, erro = await dl.baixar_video_shopee(url, pasta)
        if erro:
            print(f"erro: {erro}")
        else:
            largura, altura = await videos.dimensoes(caminho, timeout=30)
            marca = os.path.exists(os.path.join(pasta, "COM_MARCA"))
            print(f"baixou: {os.path.getsize(caminho) / 1e6:.2f} MB, {largura}x{altura}, "
                  f"{'versão com marca' if marca else 'versão sem marca'}")
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def main(argumentos):
    if len(argumentos) != 1 or not re.fullmatch(r"[A-Za-z0-9_\-=%]+", argumentos[0]):
        print(__doc__)
        return 2
    # O Baixador loga endereços (e erros que podem trazer endereços); aqui o log é
    # público, e o resultado sai pelos prints acima.
    logging.getLogger(dl.logger.name).setLevel(logging.CRITICAL + 1)
    asyncio.run(investigar(urllib.parse.unquote(argumentos[0])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""
Investiga no servidor por que o Baixador (downloader_bot) não acha o vídeo de um link da
Shopee Vídeo. Abre a página como o Baixador abre e mostra só a forma dela: status, hosts,
tamanhos e onde há vídeo no JSON da página. Depois roda o próprio baixar_video_shopee e
diz se deu certo (tamanho e dimensões do arquivo) ou o erro.

Quando a página não traz o vídeo (ela o busca depois, por outra chamada), mostra também
as chaves do JSON da página e os caminhos de API que aparecem nos scripts públicos dela,
para achar a chamada que traz o vídeo.

Usado pelo workflow investigar_baixador.yml (só à mão). O log do Actions é público:
nunca imprime links de vídeo, nomes, textos da página nem valores do JSON; só caminhos de
chave (com números e códigos trocados por # e …), contagens, e endereços de scripts e de
APIs da própria Shopee, que são públicos.

    python3 investigar_baixador.py ID_DO_VIDEO   # o que vem depois de share-video/ no link
    python3 investigar_baixador.py curto:CODIGO  # o link curto br.shp.ee/CODIGO, como o membro cola
    python3 investigar_baixador.py ultimo        # o último vídeo da Shopee Vídeo pedido ao Baixador
    python3 investigar_baixador.py apify         # a chave e o crédito da Apify, e o último vídeo por ela

O "ultimo" é o da conferência semanal do Claude: o link fica no banco do servidor
(chave baixador_shopee_video) e nunca é impresso.
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
URL_CURTA = "https://br.shp.ee/{id}"
MAXIMO_CAMINHOS = 40
MAXIMO_SCRIPTS = 30
MAXIMO_APIS = 80
TRECHO = 300
# Depois da chamada vêm os parâmetros e os cabeçalhos que ela manda: mais código.
TRECHO_DEPOIS = 1500
# Marcas, nos scripts públicos da página, de cabeçalhos e verificações contra robôs da
# Shopee e de cabeçalhos comuns da API. Só a contagem sai no log: diz se a chamada do
# vídeo depende de uma assinatura contra robôs (que o Baixador não fura) ou só de
# parâmetros comuns.
MARCAS_DE_SEGURANCA = ("af-ac-enc-dat", "af-ac-enc-sz-token", "x-sap-ri", "x-sap-sec", "x-sap-access",
                       "x-csrftoken", "csrftoken", "x-api-source", "x-shopee-language", "x-requested-with",
                       "withCredentials", "SPC_", "captcha", "antifraud", "anti_fraud", "risk_token")
# A API que a página de compartilhamento chama para buscar o vídeo (achada em 23/10/2026).
API_DO_VIDEO = "https://sv.shopee.com.br/api/v2/timeline/single"
CAMINHO_DA_API_DO_VIDEO = "/api/v2/timeline/single"
# A página manda a chamada do vídeo para um endereço-base guardado numa variável
# (baseURL): os endereços da Shopee que aparecem nos scripts são os candidatos.
HOST_DA_SHOPEE = re.compile(r"https?://((?:[a-z0-9-]+\.)*shopee\.com\.br)\b")
MAXIMO_HOSTS = 8
# Caminho de API dentro de um script: "/api/..." ou "https://.../api/...", com letras,
# números, _, -, / e . (sem consulta).
CAMINHO_DE_API = re.compile(r"""["'`]((?:https?://[a-z0-9.-]+)?/api/[A-Za-z0-9_./-]{2,120})["'`]""")


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


def todas_as_chaves(dados, caminho="$"):
    """Cada chave do JSON com o tipo do valor (texto e tamanho, número, lista), nunca o valor."""
    if isinstance(dados, dict):
        for chave, valor in dados.items():
            yield from todas_as_chaves(valor, f"{caminho}.{chave_segura(chave)}")
    elif isinstance(dados, list):
        yield f"{caminho} (lista de {len(dados)})"
        for i, item in enumerate(dados[:3]):
            yield from todas_as_chaves(item, f"{caminho}[{i}]")
    elif isinstance(dados, str):
        yield f"{caminho} (texto de {len(dados)})"
    else:
        yield f"{caminho} ({type(dados).__name__})"


def scripts_da_pagina(html, base):
    """Os endereços dos scripts que a página carrega (arquivos públicos do site)."""
    return [urllib.parse.urljoin(base, src) for src in re.findall(r'<script[^>]+src="([^"]+)"', html)]


def apis_no_script(codigo):
    """Os caminhos de API que aparecem num script."""
    return {achado for achado in CAMINHO_DE_API.findall(codigo or "")}


def forma_do_endereco(url):
    """
    host e caminho com os pedaços longos (ids) trocados por …, sem a consulta; no
    universal-link, também a forma do destino que vem no parâmetro redir.
    """
    partes = urllib.parse.urlparse(str(url))
    pedacos = ["…" if len(p) > 12 else p for p in partes.path.split("/")]
    forma = f"{partes.netloc}{'/'.join(pedacos)}"
    redir = urllib.parse.parse_qs(partes.query).get("redir", [""])[0]
    return f"{forma} (redir: {forma_do_endereco(urllib.parse.unquote(redir))})" if redir else forma


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


def tem_video(html):
    """Algum JSON embutido da página tem endereço de vídeo?"""
    for bruto in blocos_json(html).values():
        try:
            if next(caminhos_de_video(json.loads(bruto)), None):
                return True
        except ValueError:
            continue
    return False


def descrever_pagina(html):
    linhas = [f"página: {len(html)} caracteres; .mp4 no HTML: {html.lower().count('.mp4')}; "
              f".m3u8: {html.lower().count('.m3u8')}; 'watermark': {html.lower().count('watermark')}; "
              f"scripts: {html.lower().count('<script')}"]
    globais = sorted(set(re.findall(r"window\.([A-Za-z_]\w{2,40})\s*=", html)))
    if globais:
        linhas.append(f"variáveis da página: {', '.join(globais[:20])}")
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
        if not achados:
            linhas.append(f"   chaves do {nome}:")
            linhas += [f"      {chave}" for chave in list(todas_as_chaves(dados))[:MAXIMO_CAMINHOS]]
    return linhas


def trechos_da_api(codigo, api):
    """Os pedaços do script em volta de cada chamada da API: mostram os parâmetros."""
    return [codigo[max(0, i - TRECHO):i + len(api) + TRECHO_DEPOIS]
            for i in [m.start() for m in re.finditer(re.escape(api), codigo or "")][:3]]


def hosts_da_shopee(codigos):
    """Os endereços (host) da Shopee Brasil que aparecem nos scripts, sem repetir."""
    return sorted({host for codigo in codigos.values() for host in HOST_DA_SHOPEE.findall(codigo or "")})


def marcas_de_seguranca(codigos):
    """marca → (vezes, scripts em que aparece), só das marcas que aparecem."""
    achadas = {}
    for nome, codigo in codigos.items():
        for marca in MARCAS_DE_SEGURANCA:
            vezes = (codigo or "").count(marca)
            if vezes:
                total, onde = achadas.get(marca, (0, []))
                achadas[marca] = (total + vezes, onde + [nome])
    return achadas


async def procurar_apis(sessao, html, base):
    """Lê os scripts públicos da página e lista os caminhos de API que eles chamam."""
    print("== Scripts da página e as APIs que eles chamam")
    apis, codigos, todos = set(), [], {}
    scripts = scripts_da_pagina(html, base)
    print(f"scripts com endereço: {len(scripts)}")
    for endereco in scripts[:MAXIMO_SCRIPTS]:
        try:
            async with sessao.get(endereco, timeout=20) as resposta:
                codigo = await resposta.text() if resposta.status == 200 else ""
        except Exception as e:
            print(f"   {forma_do_endereco(endereco)}: não abriu ({type(e).__name__})")
            continue
        encontrados = apis_no_script(codigo)
        todos[urllib.parse.urlparse(endereco).path.rsplit("/", 1)[-1]] = codigo
        print(f"   {urllib.parse.urlparse(endereco).netloc}{urllib.parse.urlparse(endereco).path}: "
              f"{len(codigo)} caracteres, {len(encontrados)} API(s)")
        apis |= encontrados
        if encontrados:
            codigos.append(codigo)
    print(f"APIs nos scripts ({len(apis)}):")
    for api in sorted(apis)[:MAXIMO_APIS]:
        print(f"   {api}")
        # O código em volta da chamada (script público da Shopee) mostra os parâmetros.
        for codigo in codigos:
            for trecho in trechos_da_api(codigo, api):
                print(f"      trecho: {trecho}")
    print("== Cabeçalhos e verificações contra robôs nos scripts")
    achadas = marcas_de_seguranca(todos)
    if not achadas:
        print("   nenhuma marca")
    for marca, (vezes, onde) in sorted(achadas.items()):
        print(f"   {marca}: {vezes} vez(es) em {', '.join(onde[:4])}")
    hosts = hosts_da_shopee(todos)
    print(f"== Endereços da Shopee nos scripts ({len(hosts)}): {', '.join(hosts[:20])}")
    return hosts


async def testar_api(sessao, id_video, hosts=()):
    """
    Chama a API do vídeo com os nomes de parâmetro prováveis e, com o post_id (o que o
    script da página manda), em cada endereço da Shopee dos scripts, que pode ser o
    baseURL da chamada. Mostra só a forma da resposta.
    """
    print("== A API do vídeo")
    tentativas = [(API_DO_VIDEO, {nome: id_video}, nome) for nome in ("post_id", "postId", "id")]
    tentativas += [(f"https://{host}{CAMINHO_DA_API_DO_VIDEO}", {"post_id": id_video}, f"{host}, post_id")
                   for host in [h for h in hosts if h != "sv.shopee.com.br"][:MAXIMO_HOSTS]]
    for endereco, parametros, rotulo in tentativas:
        try:
            async with sessao.get(endereco, params=parametros, timeout=20) as resposta:
                corpo = await resposta.text()
        except Exception as e:
            print(f"   {rotulo}: não respondeu ({type(e).__name__})")
            continue
        try:
            dados = json.loads(corpo)
        except ValueError:
            print(f"   {rotulo}: HTTP {resposta.status}, {len(corpo)} caracteres, não é JSON")
            continue
        videos_achados = list(caminhos_de_video(dados))
        print(f"   {rotulo}: HTTP {resposta.status}, {len(corpo)} caracteres, "
              f"{len(videos_achados)} endereço(s) de vídeo")
        for caminho, tipo in videos_achados[:MAXIMO_CAMINHOS]:
            print(f"      {caminho} ({tipo})")
        if not videos_achados:
            for chave in list(todas_as_chaves(dados))[:MAXIMO_CAMINHOS]:
                print(f"      {chave}")


def id_do_video(endereco):
    """O código do vídeo (o que vem depois de share-video/), mesmo dentro do redir; "" sem ele."""
    achado = re.search(r"/share-video/([A-Za-z0-9_\-=]+)", urllib.parse.unquote(str(endereco or "")))
    return achado.group(1) if achado else ""


async def investigar(id_video="", curto=False, url=None):
    import aiohttp
    url = url or (URL_CURTA if curto else URL_DO_VIDEO).format(id=id_video)
    print("== A página, como o Baixador abre")
    async with aiohttp.ClientSession(headers=dl.CABECALHO_NAVEGADOR) as sessao:
        async with sessao.get(url, allow_redirects=True, timeout=25) as resposta:
            for passo in resposta.history:
                print(f"redirecionou: HTTP {passo.status} {forma_do_endereco(passo.url)}")
            print(f"chegou em: HTTP {resposta.status} {forma_do_endereco(resposta.url)}")
            final = str(resposta.url)
            html = await resposta.text()
        redir = urllib.parse.parse_qs(urllib.parse.urlparse(final).query).get("redir", [""])[0]
        print(f"o Baixador reconhece como vídeo da Shopee Vídeo: "
              f"{'sim' if dl.eh_video_da_shopee(urllib.parse.unquote(redir) or final) or dl.eh_link_curto_de_video(final) else 'não'}")
        for linha in descrever_pagina(html):
            print(linha)
        # No link curto, o código é o do encurtador, não o do vídeo: a API não serve.
        alvo = "" if curto else (id_video or id_do_video(final))
        if not tem_video(html) and alvo:
            hosts = await procurar_apis(sessao, html, str(resposta.url))
            await testar_api(sessao, alvo, hosts)

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


async def investigar_apify():
    """
    O caminho da Apify (o serviço de fora que o Baixador usa quando a Shopee bloqueia):
    se a chave está no servidor, o crédito do mês e, com o último vídeo pedido, o
    download de verdade por ela. Só estados e números.
    """
    print("== A Apify")
    if not dl.chave_apify():
        print("chave: não está no servidor (rodar o chave_apify.yml depois de cadastrar o segredo APIFY_TOKEN)")
        return
    print("chave: está no servidor")
    uso = await dl.uso_da_apify()
    print(f"crédito do mês: US$ {uso[0]:.2f} usados de US$ {uso[1]:.2f}" if uso else "crédito do mês: a Apify não respondeu")
    link = (dl.db.ler_config(dl.CHAVE_CONFERENCIA, {}) or {}).get("ultimo_link")
    if not link:
        print("nenhum vídeo da Shopee Vídeo pedido ao Baixador ainda: o download pela Apify fica para o primeiro")
        return
    pasta = tempfile.mkdtemp()
    try:
        caminho, motivo = await dl.baixar_pela_apify(link, pasta)
        if motivo:
            print(f"download pela Apify: não deu ({motivo})")
        else:
            largura, altura = await videos.dimensoes(caminho, timeout=30)
            marca = os.path.exists(os.path.join(pasta, "COM_MARCA"))
            print(f"download pela Apify: {os.path.getsize(caminho) / 1e6:.2f} MB, {largura}x{altura}, "
                  f"{'versão com marca' if marca else 'versão sem marca'}")
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def main(argumentos):
    if argumentos == ["apify"]:
        logging.getLogger(dl.logger.name).setLevel(logging.CRITICAL + 1)
        asyncio.run(investigar_apify())
        return 0
    if len(argumentos) != 1 or not re.fullmatch(r"(curto:)?[A-Za-z0-9_\-=%]+", argumentos[0]):
        print(__doc__)
        return 2
    # O Baixador loga endereços (e erros que podem trazer endereços); aqui o log é
    # público, e o resultado sai pelos prints acima.
    logging.getLogger(dl.logger.name).setLevel(logging.CRITICAL + 1)
    if argumentos[0] == "ultimo":
        link = (dl.db.ler_config(dl.CHAVE_CONFERENCIA, {}) or {}).get("ultimo_link")
        if not link:
            print("nenhum vídeo da Shopee Vídeo pedido ao Baixador ainda")
            return 0
        asyncio.run(investigar(url=link))
        return 0
    curto = argumentos[0].startswith("curto:")
    asyncio.run(investigar(urllib.parse.unquote(argumentos[0].removeprefix("curto:")), curto))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

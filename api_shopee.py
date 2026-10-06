"""
Cliente da API de afiliados da Shopee (GraphQL): converte links em links de
afiliado, busca ofertas e testa chaves.

As credenciais padrão vêm do .env (SHOPEE_APP_ID e SHOPEE_APP_SECRET). As
funções aceitam app_id/app_secret de outro afiliado: é assim que os links dos
parceiros saem no nome deles.
"""
import asyncio
import os
import json
import time
import hashlib
import re
import sys
import unicodedata
import urllib.parse
import aiohttp
import logging

import links_shopee
from dotenv import load_dotenv

load_dotenv()
SHOPEE_APP_ID = os.getenv('SHOPEE_APP_ID')
SHOPEE_APP_SECRET = os.getenv('SHOPEE_APP_SECRET')

logger = logging.getLogger("API_Shopee")

def gerar_headers_e_payload(payload_dict, app_id=None, app_secret=None):
    """
    Monta os headers assinados que a API exige: SHA256 de app_id + timestamp +
    payload + secret. Devolve (headers, payload_json); envie exatamente esse
    payload_json, porque a assinatura vale só para ele.

    Sem app_id/app_secret usa as chaves do .env; com eles, assina em nome de
    outro afiliado (parceiros).
    """
    app_id = app_id or SHOPEE_APP_ID
    app_secret = app_secret or SHOPEE_APP_SECRET

    timestamp = int(time.time())
    payload_json = json.dumps(payload_dict, separators=(',', ':'))
    
    fator_base = f"{app_id}{timestamp}{payload_json}{app_secret}"
    assinatura = hashlib.sha256(fator_base.encode('utf-8')).hexdigest()
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={app_id}, Timestamp={timestamp}, Signature={assinatura}"
    }
    return headers, payload_json

def limpar_sub_id(valor, padrao="geral"):
    """
    Deixa o subId só com letras e números (sem acento), até 40 caracteres.

    A Shopee recusa subId com underscore ou outros símbolos (erro 11001 -
    invalid sub id), e a conversão falharia calada, devolvendo o link sem
    rastreio de afiliado. Se não sobrar nada, usa `padrao`.
    """
    texto = unicodedata.normalize("NFKD", str(valor).strip())
    texto = texto.encode("ascii", "ignore").decode("ascii")
    limpo = re.sub(r"[^a-zA-Z0-9]", "", texto)[:40]
    return limpo or padrao

# Onde um link da Shopee diz qual é o produto: no caminho da página do produto
# (Nome-do-produto-i.<loja>.<item> ou product/<loja>/<item>, que cobre também o
# universal-link/product/...), no caminho da página de afiliado por onde passa o link de
# afiliado de outra pessoa (opaanlp/<loja>/<item>) ou num link guardado dentro dos parâmetros
# (an_redir?origin_link=...), por isso a busca vai no texto já decodificado.
PADROES_PAGINA_DO_PRODUTO = (re.compile(r"-i\.(\d+)\.(\d+)"), re.compile(r"/product/(\d+)/(\d+)"))
PADROES_PRODUTO = PADROES_PAGINA_DO_PRODUTO + (re.compile(r"/opaanlp/(\d+)/(\d+)"),)
HOSTS_CURTOS = links_shopee.ENCURTADORES
NAVEGADOR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}


def produto_do_link(url):
    """
    Link canônico do produto (https://shopee.com.br/product/<loja>/<item>) que o link
    aponta, ou None se ele não leva a um produto (busca, categoria, login...).
    """
    texto = urllib.parse.unquote(urllib.parse.unquote(url or ""))
    for padrao in PADROES_PRODUTO:
        achado = padrao.search(texto)
        if achado:
            return f"https://shopee.com.br/product/{achado.group(1)}/{achado.group(2)}"
    parametros = urllib.parse.parse_qs(urllib.parse.urlsplit(texto).query)
    loja, item = parametros.get("shopid", [""])[0], parametros.get("itemid", [""])[0]
    if loja.isdigit() and item.isdigit():
        return f"https://shopee.com.br/product/{loja}/{item}"
    return None


def tipo_de_link(url):
    """Que página o link abre, numa palavra: serve para o log e o inventário, que não mostram links."""
    if produto_do_link(url):
        return "produto"
    caminho = urllib.parse.urlsplit(url or "").path.lower()
    if _eh_link_curto(url):
        return "link curto"
    if eh_video(url):
        return "vídeo da Shopee Vídeo"
    if "an_redir" in caminho:
        return "redirecionador de afiliado"
    if caminho.startswith("/search"):
        return "busca"
    if "-cat." in caminho or caminho.startswith("/cat"):
        return "categoria"
    if any(trecho in caminho for trecho in ("login", "verify", "captcha")):
        return "login ou verificação"
    if caminho in ("", "/"):
        return "página inicial"
    return "outra página"


async def seguir_link(link, saltos=10):
    """
    Cada endereço por onde o link passa até parar, a começar pelo próprio link. Segue
    um redirecionamento de cada vez para não perder os do meio: a Shopee às vezes manda
    o servidor do produto para outra página (categoria, busca), e o produto só aparece
    num dos saltos.
    """
    caminho = [link]
    try:
        async with aiohttp.ClientSession(headers=NAVEGADOR) as session:
            for _ in range(saltos):
                async with session.get(caminho[-1], allow_redirects=False) as resp:
                    destino = resp.headers.get("Location")
                    if resp.status not in (301, 302, 303, 307, 308) or not destino:
                        break
                caminho.append(urllib.parse.urljoin(caminho[-1], destino))
    except Exception as e:
        logger.error(f"❌ [API Shopee] Erro ao expandir URL: {type(e).__name__}")
    return caminho


def eh_video(link):
    """Link de um vídeo da Shopee Vídeo (sv.shopee.com.br)."""
    host = urllib.parse.urlsplit(link or "").netloc.lower()
    return host.startswith("sv.") and host.endswith("shopee.com.br")


def _eh_link_curto(link):
    host = urllib.parse.urlsplit(link or "").netloc.lower()
    return any(host == h or host.endswith("." + h) for h in HOSTS_CURTOS)


async def link_para_converter(link_original):
    """
    O endereço que vai para a API de afiliado. Link curto: o produto, achado em
    qualquer salto dos redirecionamentos (a própria página do produto, sem os
    parâmetros, ou o link padrão do produto, quando ele aparece na página de afiliado
    de outra pessoa ou guardado num parâmetro). Link de vídeo da Shopee Vídeo:
    o endereço do vídeo inteiro (ver abaixo). Sem produto em lugar nenhum, fica o
    último endereço sem os parâmetros, e o log diz onde o link parou. Link que não é
    curto vai como veio.
    """
    if not _eh_link_curto(link_original):
        return link_original
    caminho = await seguir_link(link_original)
    for endereco in caminho[1:]:
        if any(padrao.search(urllib.parse.urlsplit(endereco).path) for padrao in PADROES_PAGINA_DO_PRODUTO):
            return endereco.split('?')[0]
        # A página de afiliado (opaanlp) é do link de quem postou na origem: convertida como
        # veio, o link novo abre no app uma busca pelo tipo do produto. O link padrão do
        # produto abre o produto.
        produto = produto_do_link(endereco)
        if produto:
            return produto
    if eh_video(caminho[-1]):
        # O link do vídeo não diz qual é o produto: o app descobre pelo vídeo, guiado pelos
        # parâmetros dele (jumpType e companhia). Cortados, o app abre a categoria do
        # produto em vez do produto; por isso o endereço vai inteiro para a API.
        return caminho[-1]
    logger.warning(f"⚠️ [API Shopee] Link sem produto: termina em {tipo_de_link(caminho[-1])}.")
    return caminho[-1].split('?')[0]


# Origem no erros_logs dos links que saíram sem a marcação de afiliado: o /status, o
# monitor de saúde do bot_mestre e o diagnostico.yml contam por ela.
ORIGEM_SEM_CONVERSAO = "Link sem conversão"
# Esperas antes da 2ª e da 3ª tentativa: a API da Shopee às vezes cai por um instante, e
# desistir na primeira falha mandaria o post com o link de outra pessoa.
PAUSAS_ENTRE_TENTATIVAS = (2, 5)


def _registrar_sem_conversao(motivo, sub_id, parceiro):
    """
    Grava no erros_logs que um link saiu sem a marcação de afiliado, com o robô, o
    subId e o motivo, sem o link. motivo = (frase, tipo, detalhe): o tipo
    (sem_chaves, recusa, sem_resposta) e o detalhe (código da API ou tipo do erro) vão
    também no contexto, que o diagnostico.yml conta sem mostrar o texto.
    Decisão do Rafael: DECISOES.md, Canal Viral.
    """
    frase, tipo, detalhe = motivo
    robo = os.path.splitext(os.path.basename(sys.argv[0] or ""))[0] or "?"
    sem_marca = "sem a marcação do parceiro" if parceiro else "sem a sua marcação"
    try:
        # Importado aqui: o utils mexe no logging e no sqlite3 do processo, e as
        # ferramentas que só testam chaves não precisam dele.
        from utils import registrar_erro_json
        registrar_erro_json(f"link saiu {sem_marca} ({robo}, subId {sub_id}): {frase}",
                            origem=ORIGEM_SEM_CONVERSAO,
                            contexto_extra={"robo": robo, "tipo": tipo, "detalhe": str(detalhe)[:40]})
    except Exception as e:
        logger.error(f"❌ [API Shopee] Não registrou o link sem conversão: {type(e).__name__}")


def _motivo_da_recusa(status, resposta):
    """A recusa da API: (frase curta com o código e a mensagem do primeiro erro, "recusa", código)."""
    erros = (resposta or {}).get("errors") if isinstance(resposta, dict) else None
    if erros and isinstance(erros, list) and isinstance(erros[0], dict):
        extra = erros[0].get("extensions") or {}
        codigo = extra.get("code", "")
        mensagem = str(extra.get("message") or erros[0].get("message") or "")[:80]
        return f"a API recusou ({codigo} {mensagem})".replace("( ", "(").strip(), "recusa", codigo or status
    return f"a API recusou (status {status})", "recusa", status


async def converter_link_shopee(link_original, sub_id_nicho="geral", app_id=None, app_secret=None,
                                avisar_falha=True):
    """
    Converte um link da Shopee em link curto de afiliado, marcado com o subId
    do nicho para rastrear de onde veio a venda.

    Erro de rede ou recusa da API: tenta de novo duas vezes (PAUSAS_ENTRE_TENTATIVAS).
    Em QUALQUER falha que sobrar (sem chaves, erro de rede, recusa da API) devolve o link
    original: a postagem segue, mas sem rastreio de afiliado. A falha vai para o
    erros_logs (o /status e o monitor de saúde mostram), menos com
    avisar_falha=False, usado pelas ferramentas de diagnóstico. Para saber o
    motivo de uma recusa, use testar_chaves_afiliado.

    Com app_id/app_secret, o link sai no nome do parceiro.
    """
    cred_id = app_id or SHOPEE_APP_ID
    cred_secret = app_secret or SHOPEE_APP_SECRET
    sub_id_limpo = limpar_sub_id(sub_id_nicho)

    def falhou(motivo):
        if avisar_falha:
            _registrar_sem_conversao(motivo, sub_id_limpo, parceiro=bool(app_id))
        return link_original

    if not cred_id or not cred_secret:
        logger.warning("⏳ [API Shopee] Chaves ausentes. Ignorando conversão.")
        return falhou(("sem as chaves de afiliado", "sem_chaves", "-"))

    # O link de afiliado sai para o produto, e não para a página onde o redirecionamento
    # parou: se a Shopee manda o servidor para a categoria, o link levaria o cliente para
    # a categoria em vez do produto.
    link_processar = await link_para_converter(link_original)

    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"

    payload = {
        "query": "mutation generateShortLink($originUrl: String!, $subIds: [String!]) { generateShortLink(input: {originUrl: $originUrl, subIds: $subIds}) { shortLink } }",
        "variables": {
            "originUrl": link_processar,
            "subIds": [sub_id_limpo]
        }
    }

    for tentativa, pausa in enumerate((0,) + tuple(PAUSAS_ENTRE_TENTATIVAS)):
        if pausa:
            await asyncio.sleep(pausa)
        # A assinatura leva a hora: cada tentativa assina de novo.
        headers, payload_json = gerar_headers_e_payload(payload, app_id, app_secret)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, headers=headers, data=payload_json) as response:
                    resposta_dados = await response.json()
                    if response.status == 200 and "data" in resposta_dados and resposta_dados["data"].get("generateShortLink"):
                        return resposta_dados["data"]["generateShortLink"]["shortLink"]
                    logger.error(f"❌ [API Shopee] Falha na conversão (tentativa {tentativa + 1}): {resposta_dados}")
                    motivo = _motivo_da_recusa(response.status, resposta_dados)
        except Exception as e:
            logger.error(f"❌ [API Shopee] Erro de comunicação com o servidor (tentativa {tentativa + 1}): {e}")
            motivo = (f"sem resposta da API ({type(e).__name__})", "sem_resposta", type(e).__name__)
    return falhou(motivo)

async def buscar_ofertas_shopee(keyword, limite=10, app_id=None, app_secret=None, sort_type=2):
    """
    Busca produtos na Shopee por palavra-chave. Devolve a lista de produtos
    (nodes da API) ou lista vazia em qualquer erro.

    sort_type: 1=relevância, 2=mais vendidos, 3=preço maior, 4=preço menor,
    5=maior comissão. O padrão 2 é o do garimpo de ofertas. O buscador usa 1,
    porque ordenar por preço num conjunto pouco relevante traz acessório
    barato em vez do produto (sort_type=4 traz capinha de fone, não fone).
    """
    cred_id = app_id or SHOPEE_APP_ID
    cred_secret = app_secret or SHOPEE_APP_SECRET

    if not cred_id or not cred_secret:
        logger.warning("⏳ [API Shopee] Chaves financeiras ausentes.")
        return []

    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"
    payload = {
        "query": """query getProductOffer($keyword: String!, $limit: Int!, $sortType: Int) {
            productOfferV2(keyword: $keyword, limit: $limit, sortType: $sortType) {
                nodes {
                    itemId
                    productName
                    price
                    priceMin
                    priceMax
                    priceDiscountRate
                    ratingStar
                    sales
                    shopName
                    imageUrl
                    productLink
                }
            }
        }""",
        "variables": {
            "keyword": keyword,
            "limit": limite,
            "sortType": sort_type
        }
    }

    headers, payload_json = gerar_headers_e_payload(payload, app_id, app_secret)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, data=payload_json) as response:
                if response.status == 200:
                    dados = await response.json()
                    erros = dados.get("errors")
                    if erros:
                        logger.error(f"❌ [API Shopee] A API negou o rastreio: {erros[0].get('message')}")
                        return []
                    return dados.get("data", {}).get("productOfferV2", {}).get("nodes", [])
    except Exception as e:
        logger.error(f"❌ [API Shopee] Erro crítico na prospecção de ofertas: {e}")
    return []

async def testar_chaves_afiliado(link_teste, app_id, app_secret):
    """
    Testa um par App ID + Secret convertendo `link_teste` e devolve (ok, motivo).

    Separada de converter_link_shopee porque aquela esconde a falha devolvendo
    o link original; aqui o motivo da recusa chega a quem chamou (cadastro de
    parceiro).
    """
    if not app_id or not app_secret:
        return False, "Chaves ausentes."

    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"
    payload = {
        "query": "mutation generateShortLink($originUrl: String!, $subIds: [String!]) { generateShortLink(input: {originUrl: $originUrl, subIds: $subIds}) { shortLink } }",
        # subId só com letras e números; com underscore a Shopee recusa (11001).
        "variables": {"originUrl": link_teste, "subIds": [limpar_sub_id("teste cadastro")]}
    }
    headers, payload_json = gerar_headers_e_payload(payload, app_id, app_secret)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, data=payload_json) as response:
                dados = await response.json()

                if response.status == 200 and dados.get("data", {}).get("generateShortLink"):
                    return True, "OK"

                erros = dados.get("errors") or []
                if erros:
                    motivo = erros[0].get("message", "Erro sem descrição.")
                    logger.error(f"❌ [API Shopee] Teste de chaves recusado: {motivo}")
                    return False, motivo

                logger.error(f"❌ [API Shopee] Resposta inesperada no teste: {dados}")
                return False, f"Resposta inesperada (HTTP {response.status})."
    except Exception as e:
        logger.error(f"❌ [API Shopee] Erro de rede no teste de chaves: {e}")
        return False, f"Não consegui falar com a Shopee: {e}"

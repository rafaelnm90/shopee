import os
import json
import time
import hashlib
import aiohttp
import logging
from dotenv import load_dotenv

# Carrega as chaves do .env
load_dotenv()
SHOPEE_APP_ID = os.getenv('SHOPEE_APP_ID')
SHOPEE_APP_SECRET = os.getenv('SHOPEE_APP_SECRET')

logger = logging.getLogger("API_Shopee")

def gerar_headers_e_payload(payload_dict, app_id=None, app_secret=None):
    """
    Gera a assinatura criptografada e os headers exigidos pela API da Shopee.
    Sem app_id/app_secret usa as chaves do .env (comportamento de sempre).
    Com eles, assina em nome de outro afiliado — base do modo multiparceiro.
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

async def converter_link_shopee(link_original, sub_id_nicho="geral", exibir_logs=True, app_id=None, app_secret=None):
    """
    Encurta o link da Shopee gerando a URL de afiliado com rastreio.
    app_id/app_secret opcionais: quando informados, o link sai no nome do parceiro.
    """
    cred_id = app_id or SHOPEE_APP_ID
    cred_secret = app_secret or SHOPEE_APP_SECRET

    if not cred_id or not cred_secret:
        if exibir_logs: logger.warning("⏳ [API Shopee] Chaves ausentes. Ignorando conversão.")
        return link_original

    link_processar = link_original
    
    # Expansão de links curtos
    if "shp.ee" in link_original or "shope.ee" in link_original or "s.shopee.com.br" in link_original:
        try:
            headers_redirect = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            async with aiohttp.ClientSession() as session:
                async with session.get(link_original, allow_redirects=True, headers=headers_redirect) as resp:
                    link_processar = str(resp.url).split('?')[0]
        except Exception as e:
            if exibir_logs: logger.error(f"❌ [API Shopee] Erro ao expandir URL: {e}")

    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"
    import re
    sub_id_limpo = re.sub(r'[^a-zA-Z0-9_]', '_', str(sub_id_nicho).strip())[:40]

    payload = {
        "query": "mutation generateShortLink($originUrl: String!, $subIds: [String!]) { generateShortLink(input: {originUrl: $originUrl, subIds: $subIds}) { shortLink } }",
        "variables": {
            "originUrl": link_processar,
            "subIds": [sub_id_limpo]
        }
    }

    headers, payload_json = gerar_headers_e_payload(payload, app_id, app_secret)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, headers=headers, data=payload_json) as response:
                resposta_dados = await response.json()
                if response.status == 200 and "data" in resposta_dados and resposta_dados["data"].get("generateShortLink"):
                    novo_link = resposta_dados["data"]["generateShortLink"]["shortLink"]
                    return novo_link
                else:
                    if exibir_logs: logger.error(f"❌ [API Shopee] Falha na conversão: {resposta_dados}")
    except Exception as e:
        if exibir_logs: logger.error(f"❌ [API Shopee] Erro de comunicação com o servidor: {e}")
        
    return link_original

async def buscar_ofertas_shopee(keyword, limite=10, exibir_logs=True, app_id=None, app_secret=None, sort_type=2):
    """Rastreia ofertas e produtos baseados em palavras-chave na Shopee.

    sort_type: 1=relevância · 2=mais vendidos · 3=preço↓ · 4=preço↑ · 5=comissão↓
    O default 2 preserva o comportamento do garimpo. O buscador usa 1, porque
    ordenar por preço num conjunto não-relevante devolve acessório barato em
    vez do produto (o sortType=4 traz capinha de fone, não fone)."""
    cred_id = app_id or SHOPEE_APP_ID
    cred_secret = app_secret or SHOPEE_APP_SECRET

    if not cred_id or not cred_secret:
        if exibir_logs: logger.warning("⏳ [API Shopee] Chaves financeiras ausentes.")
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
                        if exibir_logs: logger.error(f"❌ [API Shopee] A API negou o rastreio: {erros[0].get('message')}")
                        return []
                    return dados.get("data", {}).get("productOfferV2", {}).get("nodes", [])
    except Exception as e:
        if exibir_logs: logger.error(f"❌ [API Shopee] Erro crítico na prospecção de ofertas: {e}")
    return []

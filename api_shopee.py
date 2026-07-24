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

def gerar_headers_e_payload(payload_dict):
    """Gera a assinatura criptografada e os headers exigidos pela API da Shopee."""
    timestamp = int(time.time())
    payload_json = json.dumps(payload_dict, separators=(',', ':'))
    
    fator_base = f"{SHOPEE_APP_ID}{timestamp}{payload_json}{SHOPEE_APP_SECRET}"
    assinatura = hashlib.sha256(fator_base.encode('utf-8')).hexdigest()
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={SHOPEE_APP_ID}, Timestamp={timestamp}, Signature={assinatura}"
    }
    return headers, payload_json

async def converter_link_shopee(link_original, sub_id_nicho="geral", exibir_logs=True):
    """Encurta o link da Shopee gerando a sua URL de afiliado com rastreio."""
    if not SHOPEE_APP_ID or not SHOPEE_APP_SECRET:
        if exibir_logs: logger.warning("⏳ [API Shopee] Chaves ausentes no .env. Ignorando conversão.")
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
        "query": "mutation generateShortLink($originUrl: String!, $subIds: [String]) { generateShortLink(input: {originUrl: $originUrl, subIds: $subIds}) { shortLink } }",
        "variables": {
            "originUrl": link_processar,
            "subIds": [sub_id_limpo] if sub_id_nicho != "geral" else []
        }
    }

    headers, payload_json = gerar_headers_e_payload(payload)

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

async def buscar_ofertas_shopee(keyword, limite=10, exibir_logs=True):
    """Rastreia ofertas e produtos baseados em palavras-chave na Shopee."""
    if not SHOPEE_APP_ID or not SHOPEE_APP_SECRET:
        if exibir_logs: logger.warning("⏳ [API Shopee] Chaves financeiras ausentes no .env.")
        return []

    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"
    payload = {
        "query": """query getProductOffer($keyword: String!, $limit: Int!, $sortType: Int) {
            productOfferV2(keyword: $keyword, limit: $limit, sortType: $sortType) {
                nodes {
                    itemId
                    productName
                    price
                    priceDiscountRate
                    ratingStar
                    imageUrl
                    productLink
                }
            }
        }""",
        "variables": {
            "keyword": keyword,
            "limit": limite,
            "sortType": 2
        }
    }

    headers, payload_json = gerar_headers_e_payload(payload)

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

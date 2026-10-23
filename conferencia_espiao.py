"""
A conferência do nome que a IA do Espião dá ao produto do vídeo, para o checkup do
dia saber se a análise está certa: depois que o clone sai no Viral, o bot_mestre
compara o nome da IA com o nome do produto na API de afiliado da Shopee (o do link
do post) e anota no registro dos processos se confere. Não muda o post.

Confere quando os dois nomes têm uma palavra de verdade em comum (4 letras ou mais,
sem acento, fora as palavras vazias): o nome da IA é curto ("Garrafa Térmica 🧴") e
o da Shopee é longo, com marca e medidas. Link de vídeo da Shopee Vídeo não tem um
produto só na API e fica como "sem produto na API".
"""
import re
import unicodedata

import assistente_shopee_video
import registro_processos

# Palavras que aparecem em quase todo nome de produto e não dizem qual é.
PALAVRAS_VAZIAS = {
    "para", "com", "sem", "kit", "novo", "nova", "promocao", "oferta", "original", "unidade", "unidades",
    "peca", "pecas", "tamanho", "cores", "frete", "gratis", "envio", "pronta", "entrega", "premium",
}


def palavras(texto):
    """As palavras de verdade do nome: sem acento, minúsculas, 4 letras ou mais, fora as vazias."""
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return {p for p in re.findall(r"[a-z0-9]+", sem_acento.lower()) if len(p) >= 4 and p not in PALAVRAS_VAZIAS}


def confere(nome_da_ia, nomes_da_api):
    """O nome da IA tem uma palavra de verdade em comum com o nome de algum produto da API?"""
    da_ia = palavras(nome_da_ia)
    return any(da_ia & palavras(nome) for nome in nomes_da_api)


async def anotar(nome_da_ia, link):
    """Anota no registro se o nome da IA confere com o produto do link. Nunca levanta erro."""
    processo = "IA: nome do produto"
    try:
        produtos, _destino = await assistente_shopee_video.produtos_do_link(link)
    except Exception as e:
        registro_processos.registrar("espiao", processo, "API não respondeu", type(e).__name__)
        return
    nomes = [p.get("nome") for p in produtos if p.get("nome")]
    if not nomes:
        registro_processos.registrar("espiao", processo, "sem produto na API")
    elif confere(nome_da_ia, nomes):
        registro_processos.registrar("espiao", processo, "confere", ok=True)
    else:
        registro_processos.registrar("espiao", processo, "não confere", ok=False)

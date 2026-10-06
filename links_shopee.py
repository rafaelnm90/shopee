"""
Links da Shopee em textos e mensagens do Telegram, achados do mesmo jeito em todos
os robôs: Espião e Espelhador (motor_userbot), Autorais (espelhador_videos_autorais),
Grupo Público e painel de submissão (bot_mestre) e Baixador (downloader_bot).
A troca pelo link de afiliado fica no api_shopee.

Um lugar só para que um conserto valha para todos: cada robô com a sua cópia foi o
que deixou o Espelhador de fora do conserto dos links de produto (DECISOES.md,
Código e manutenção).
"""
import re

# Encurtadores da Shopee.
ENCURTADORES = ("s.shopee.com.br", "shope.ee", "br.shp.ee", "shp.ee")
_HOSTS = "|".join(re.escape(host) for host in ENCURTADORES)

# Link curto, com ou sem http, em maiúsculas ou não. Para no espaço e no "<", que numa
# legenda em HTML é o começo da próxima tag.
PADRAO_LINK_CURTO = re.compile(rf"(?:https?://)?(?:{_HOSTS})/[^\s<]+", re.IGNORECASE)
# Curto ou do próprio site (shopee.com.br/...), para quem cola o link do produto.
PADRAO_LINK_SHOPEE = re.compile(rf"(?:https?://)?(?:{_HOSTS}|shopee\.com\.br)/[^\s<]+", re.IGNORECASE)
# O código do link curto (s.shopee.com.br/<código>), que serve de identidade do link.
_PADRAO_CODIGO = re.compile(rf"(?:{_HOSTS})/([A-Za-z0-9]+)", re.IGNORECASE)


def primeiro_link(texto, padrao=PADRAO_LINK_CURTO):
    """
    Primeiro link do padrão no texto, com https e sem a pontuação grudada no fim
    ("veja: s.shopee.com.br/abc)." → "https://s.shopee.com.br/abc"). None se não houver.
    """
    achado = padrao.search(texto or "")
    if not achado:
        return None
    link = achado.group(0).rstrip(").,;!?")
    if not link.lower().startswith("http"):
        link = "https://" + link
    return link


def extrair_link_shopee(mensagem):
    """
    Primeiro link curto da Shopee de uma mensagem do Telethon: no texto visível ou
    escondido atrás de um texto (entidade com url). None se não houver.
    """
    link = primeiro_link(getattr(mensagem, "raw_text", None))
    if link:
        return link
    for entidade in getattr(mensagem, "entities", None) or []:
        url = getattr(entidade, "url", None)
        if url and PADRAO_LINK_CURTO.search(url):
            return url
    return None


def codigo_do_link_curto(link):
    """O código do link curto, em minúsculas ('S.SHOPEE.COM.BR/AbC1' → 'abc1'), ou None."""
    achado = _PADRAO_CODIGO.search(str(link or ""))
    return achado.group(1).lower() if achado else None

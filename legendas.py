"""
Legenda dos posts de vídeo com link de afiliado e o pedido à IA de nome e hashtags do
produto, iguais em todos os robôs que postam: Espião (motor_userbot na análise
antecipada e bot_mestre no disparo), Espelhador (motor_userbot), Autorais
(espelhador_videos_autorais) e Parceiros (bot_mestre). O assistente da Shopee Vídeo lê
o nome do produto de volta da legenda (nome_da_legenda).

Um lugar só para que mudar o formato ou uma categoria valha para todos os canais
(DECISOES.md, Código e manutenção).
"""
import html
import re

# As categorias que a IA pode usar nas hashtags. Fora desta lista, nenhuma.
HASHTAGS = (
    "#RoupasFemininas", "#SapatosFemininos", "#CelularesEDispositivos", "#AcessoriosParaVeiculos", "#Relogios",
    "#AlimentosEBebidas", "#CasaEDecoracao", "#SapatosMasculinos", "#EsportesELazer", "#BolsasMasculinas",
    "#BolsasFemininas", "#RoupasPlusSize", "#ModaInfantil", "#Eletrodomesticos", "#Motocicletas",
    "#AnimaisDomesticos", "#CamerasEDrones", "#Beleza", "#AcessoriosDeModa", "#BrinquedosEHobbies", "#Papelaria",
    "#LivrosERevistas", "#RoupasMasculinas", "#Automoveis", "#MaeEBebe", "#ComputadoresEAcessorios", "#Saude",
    "#ViagensEBagagens", "#JogosEConsoles", "#Audio",
)


# Duas linhas: o nome do produto com um emoji no fim (em todos os robôs, Autorais
# inclusive: DECISOES.md, Vídeos Autorais e contas do pool) e as hashtags da lista. O
# exemplo do organizador de sacos evita a categoria pela palavra ("saco" virar bolsa).
PROMPT_NOME_E_HASHTAGS = (
    "Assista ao vídeo INTEIRO e identifique qual é o produto demonstrado. "
    "Sua resposta deve conter EXATAMENTE duas linhas.\n"
    "Na primeira linha, escreva APENAS o nome do produto acompanhado de um emoji correspondente no final "
    "(Exemplo: Tênis Casual Feminino 👟).\n"
    "Na segunda linha, inclua as hashtags correspondentes aos setores do produto. IMPORTANTE: Se utilizar mais "
    "de uma hashtag, separe-as APENAS com espaços em branco, NUNCA utilize vírgulas.\n"
    "REGRA DE CONTEXTO: Categorize o produto baseando-se estritamente na sua utilidade prática e ambiente de uso. "
    "É terminantemente proibido utilizar atalhos semânticos ou associações literais de palavras (exemplo prático: "
    "um organizador de sacos plásticos de cozinha pertence a #CasaEDecoracao e NUNCA a #BolsasFemininas, pois não "
    "é um acessório de moda).\n"
    "REGRA ABSOLUTA: Você só pode escolher as hashtags desta lista exata, podendo combinar mais de uma se "
    f"aplicável: {', '.join(HASHTAGS)}.\n"
    "É estritamente proibido criar textos de vendas, descrições, inventar novas hashtags, usar gatilhos mentais "
    "ou adicionar frases de encerramento."
)


def separar_nome_e_hashtags(texto_ia):
    """(nome, hashtags) da resposta da IA: a 1ª linha e o resto. Hashtags vazias se vier uma linha só."""
    linhas = (texto_ia or "").split("\n")
    nome = linhas[0].strip()
    hashtags = "\n".join(linhas[1:]).strip() if len(linhas) > 1 else ""
    return nome, hashtags


def montar_legenda(nome, link, hashtags=""):
    """
    A legenda em HTML: nome em negrito, o link de afiliado e as hashtags em itálico.
    Nome e hashtags vão escapados: um "&" ou "<" vindo da IA quebraria o HTML e o post.
    """
    legenda = f"<b>{html.escape(nome)}</b>\n\n🔗 <b>Link do Produto:</b>\n{link}"
    if hashtags:
        legenda += f"\n\n<i>{html.escape(hashtags)}</i>"
    return legenda


def legenda_da_ia(texto_ia, link):
    """A legenda a partir da resposta da IA (nome na 1ª linha, hashtags no resto)."""
    nome, hashtags = separar_nome_e_hashtags(texto_ia)
    return montar_legenda(nome, link, hashtags)


def legenda_so_link(link):
    """Sem o nome da IA: só o link de afiliado, com o rótulo."""
    return f"🔗 <b>Link do Produto:</b>\n{link}"


# O nome que vai no lugar do produto quando a IA não responde (Autorais). Quem lê a
# legenda depois (o assistente da Shopee Vídeo) trata esse nome como "sem nome".
NOME_SEM_IA = "Vídeo do Produto"


def legenda_sem_nome(link):
    """Sem a IA, nos Autorais: o nome genérico em negrito e o link."""
    return f"<b>{NOME_SEM_IA}</b> 🛍️\n\n🔗 <b>Link do Produto:</b>\n{link}"


def nome_da_legenda(legenda):
    """
    O nome do produto em texto puro, lido do negrito da legenda ("&amp;" volta a ser "&").
    Vazio se não houver negrito ou se for o nome genérico de quando a IA não respondeu.
    """
    achado = re.search(r"<b>(.*?)</b>", legenda or "")
    nome = html.unescape(re.sub(r"<[^>]+>", "", achado.group(1))).strip() if achado else ""
    return "" if nome in ("", NOME_SEM_IA) else nome


def hashtags_da_legenda(legenda):
    """
    As hashtags que a legenda já leva (o itálico de montar_legenda), em texto puro e
    separadas por espaço; vazio se não houver. O repost dos Autorais no Grupo Público
    repete as categorias que a IA escolheu para o vídeo (DECISOES.md, Grupo Público e Achadinhos).
    """
    for trecho in reversed(re.findall(r"<i>(.*?)</i>", legenda or "", re.S)):
        tags = [p for p in html.unescape(re.sub(r"<[^>]+>", "", trecho)).split() if p.startswith("#")]
        if tags:
            return " ".join(tags)
    return ""

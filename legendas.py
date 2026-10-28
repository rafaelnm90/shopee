"""
Legenda dos posts de vídeo com link de afiliado e o pedido à IA de nome e hashtags do
produto, iguais em todos os robôs que postam: Espião (motor_userbot na análise
antecipada e bot_mestre no disparo), Espelhador (motor_userbot), Autorais
(espelhador_videos_autorais) e Parceiros (bot_mestre). O Grupo Público tem o padrão
próprio (legenda_grupo_publico), usado pelo bot_mestre em todo vídeo que vai para lá, e o
Canal Afiliados também (legenda_do_canal), usado pelo Criar Postagem 📝 e pelos vídeos do
robô da Shopee Vídeo que vão ao canal depois de postados (bot_mestre).
O assistente da Shopee Vídeo lê o nome do produto de volta da legenda (nome_da_legenda).

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


def legenda_grupo_publico(credito, nome, link_shopee=None, link_tiktok=None, hashtags=""):
    """
    O padrão dos vídeos do Grupo Público, igual para quem posta (o membro pelo painel, o
    Rafael nos reposts dos Autorais e o parceiro): o crédito de quem postou, o nome do
    produto, um bloco por plataforma com o rótulo (Shopee primeiro, TikTok depois) e as
    hashtags. A parte que falta (sem crédito, sem nome, sem um dos links) não aparece.
    O crédito já vem em HTML (o @ ou o nome clicável); nome e hashtags são escapados.
    Decisão do Rafael: DECISOES.md, Grupo Público e Achadinhos.
    """
    partes = []
    if credito:
        partes.append(f"👤 Vídeo enviado por: {credito}")
    if nome:
        partes.append(f"<b>{html.escape(nome)}</b>")
    if link_shopee:
        partes.append(f"🔶 <b>SHOPEE</b> 🔶\n🔗 Link do Produto:\n{link_shopee}")
    if link_tiktok:
        partes.append(f"⬛ <b>TIKTOK</b> ⬛\n🔗 Link do Produto:\n{link_tiktok}")
    if hashtags:
        partes.append(f"<i>{html.escape(hashtags)}</i>")
    return "\n\n".join(partes)


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


# --- O padrão do Canal Afiliados ---

# Os posts do Canal Afiliados (o canal principal, Acervo Afiliados Shopee): o título "Vídeo
# N | 📦 Item: ..." numa linha, uma linha divisória e o bloco de cada plataforma (o link do
# vídeo, o texto de apoio e os links dos produtos numerados). O mesmo no Criar Postagem 📝
# e nos vídeos do robô da Shopee Vídeo. Decisão do Rafael (28/10, P64, com o vídeo das
# postagens do canal): DECISOES.md, Canal principal.
LINHA_DO_CANAL = "━━━━━━━━━━━━━━━"
APOIO_LONGO = ("<i>(💡 O nosso grupo é 100% gratuito. Para nos ajudar a continuar trazendo conteúdos, por "
               "favor, clique no link do vídeo acima, assista, curta, comente e siga o perfil! Isso nos ajuda "
               "muito!)</i>\n\n")
APOIO_CURTO = "<i>(💡 Grupo 100% gratuito. Curta e comente nos vídeos para ajudar!)</i>\n\n"
APOIO_RODAPE = "\n<i>(💡 Grupo 100% gratuito. Curta e comente nos vídeos para ajudar!)</i>"
# O limite da legenda de um vídeo no Telegram.
LIMITE_DA_LEGENDA = 1024
# O item que vem do nome do produto (sem a resposta da IA) fica até este tamanho.
TAMANHO_DO_ITEM = 60


def prompt_do_item(numero):
    """O pedido à IA do título do post do canal, vendo o vídeo: "Vídeo N" e "📦 Item: ..."."""
    return (
        f"Assista ao vídeo INTEIRO para identificar o produto ou kit principal. "
        f"Sua resposta deve conter EXATAMENTE duas linhas. "
        f"Na primeira linha, escreva estritamente: 'Vídeo {numero}'. "
        f"Na segunda linha, escreva '📦 Item: ' seguido do nome do produto ou kit identificado. "
        f"Exemplo de saída esperada:\n"
        f"Vídeo {numero}\n"
        f"📦 Item: Kit Dove Reconstrução\n"
        f"Não adicione nenhuma outra palavra, ponto final extra ou descrição."
    )


def titulo_do_item(resposta_ia, numero, produto=""):
    """
    O título do post do canal ("Vídeo N" e "📦 Item: ..." em duas linhas), com o item da
    resposta da IA. Sem ela, ou fora do formato, o item é o nome do produto, até
    TAMANHO_DO_ITEM caracteres sem cortar palavra (sem nome, o genérico NOME_SEM_IA).
    """
    achado = re.search(r"📦\s*Item:\s*(.+)", resposta_ia or "")
    item = achado.group(1).strip() if achado else ""
    if not item:
        palavras, item = (produto or "").split(), ""
        for palavra in palavras:
            if len(f"{item} {palavra}".strip()) > TAMANHO_DO_ITEM:
                break
            item = f"{item} {palavra}".strip()
        item = item or NOME_SEM_IA
    return f"Vídeo {numero}\n📦 Item: {item}"


def legenda_do_canal(titulo, shopee=None, tiktok=None, apoio=APOIO_LONGO, rodape=False):
    """
    A legenda de um post do Canal Afiliados. shopee e tiktok: (link do vídeo, [links dos
    produtos]) de cada plataforma, ou None. O título vai numa linha só (as quebras viram
    " | ") e escapado; com rodape=True, o texto de apoio vai uma vez só, no fim.
    """
    titulo_limpo = html.escape((titulo or "").replace("\n", " | "), quote=False)
    legenda = f"<b>{titulo_limpo}</b>\n\n{LINHA_DO_CANAL}\n\n"
    if shopee:
        legenda += _bloco_do_canal("🔶 <b>SHOPEE VÍDEO</b> 🔶", shopee, apoio, rodape)
        legenda += f"\n{LINHA_DO_CANAL}\n\n" if tiktok else "\n"
    if tiktok:
        legenda += _bloco_do_canal("⬛ <b>TIKTOK</b> ⬛", tiktok, apoio, rodape) + "\n"
    if rodape:
        legenda += apoio
    return legenda


def _bloco_do_canal(cabecalho, plataforma, apoio, rodape):
    # Os links também escapados: o link copiado de um post pode trazer "&" nos parâmetros.
    link_do_video, links = plataforma
    bloco = f"{cabecalho}\n\n🎬 Link do Vídeo:\n{html.escape(link_do_video or '', quote=False)}\n"
    if not rodape:
        bloco += apoio
    if links:
        bloco += "🔗 Links dos Produtos:\n" + "".join(f"👉 {n}º: {html.escape(link, quote=False)}\n"
                                                   for n, link in enumerate(links, 1))
    return bloco


def legenda_do_canal_que_cabe(titulo, shopee=None, tiktok=None):
    """
    A legenda do canal que cabe nos LIMITE_DA_LEGENDA caracteres do Telegram, nos níveis do
    canal: o texto de apoio longo, o curto e só um rodapé. Devolve (legenda, coube); sem
    caber nem com o rodapé, vem a do rodapé (com as duas plataformas, o Criar Postagem
    divide em dois posts).
    """
    for apoio, rodape in ((APOIO_LONGO, False), (APOIO_CURTO, False), (APOIO_RODAPE, True)):
        legenda = legenda_do_canal(titulo, shopee, tiktok, apoio, rodape)
        if len(legenda) <= LIMITE_DA_LEGENDA:
            return legenda, True
    return legenda, False

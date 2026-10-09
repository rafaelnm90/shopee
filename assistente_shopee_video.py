"""
Modo assistente da Shopee Vídeo: prepara cada postagem e manda no privado do Rafael,
que posta pelo próprio celular. Usado pelo painel_shopee_video (bot_mestre).

Para cada vídeo:
- o vídeo vem da fonte escolhida no painel (padrão: os Autorais), o mais novo que
  ainda tem o arquivo e não foi mandado;
- a IA (Gemini) assiste ao vídeo com o prompt do Gem "Shopee Vídeo" do Rafael,
  adaptado, e com o resumo das diretrizes (diretrizes_shopee_video.md): devolve o
  título (130 a 150 caracteres, sem marca; curto, é pedido mais uma vez), o texto do
  comentário e se viu violação. Vídeo com violação não é mandado; o Rafael recebe o motivo;
- os produtos saem do link do post: link de produto vira nome, preço e comissão pela
  API de afiliado; link de vídeo da Shopee Vídeo não diz os produtos, e o Rafael os
  vê no próprio vídeo.

Quando mandar: cada dia sorteia quantos vídeos (a faixa do painel) e espalha os
horários pela janela do painel, com um sorteio fixo por dia. A cada volta do agendador,
manda no máximo um vídeo, e só se um horário já passou. Pausado, os horários que
passam são pulados, para não sair tudo de uma vez ao retomar.

O robô nunca posta, curte nem comenta na Shopee (diretriz 9.1.1).
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import html
import json
import logging
import os
import random
import re
from datetime import datetime

import aiohttp

import api_gemini
import api_shopee
import db
import legendas
from fuso import fuso_horario
from motor_filas import sortear_teto_do_dia

logger = logging.getLogger("ShopeeVideo")

CHAVE_DIA = "shopee_video_dia"
ARQUIVO_DIRETRIZES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diretrizes_shopee_video.md")
TITULO_MIN, TITULO_MAX = 130, 150
URL_API = "https://open-api.affiliate.shopee.com.br/graphql"
LINK_DO_POST = re.compile(r"https?://[^\s<>\"]*shopee[^\s<>\"]*")
EXTENSOES_DE_IMAGEM = (".jpg", ".jpeg", ".png", ".webp", ".gif")

# De onde o assistente pode puxar os vídeos: filas que guardam o arquivo e o link do
# produto. Os Parceiros ficam de fora: os vídeos são deles.
FONTES = {
    "autorais": "Autorais 🎥",
    "viral": "Viral (Espião) 🕵️",
    "principal": "Canal Afiliados 📺",
    "publico": "Grupo Público 📬",
}
FONTE_PADRAO = "autorais"

PROMPT = """Atue como um especialista em Growth Hacking e Marketing para Shopee. Analise \
detalhadamente o vídeo (produto, estilo e público-alvo) e gere o texto para postar na Shopee Vídeo.

Responda SOMENTE com um JSON, sem nada antes ou depois, neste formato:
{{"violacao": false, "motivo": "", "titulo": "...", "comentario": "..."}}

"titulo": o Título do Vídeo, com apenas o nome do produto (sem frase de gancho nem texto \
criativo), seguido de emojis e do máximo possível de hashtags de alta performance e grande \
volume de busca, escolhidas para a visibilidade e a venda deste produto (ex.: Varal de Chão \
Dobrável #varal #varaldechao #organizacao #roupas). O total (título + emojis + hashtags) deve \
ter obrigatoriamente entre {titulo_min} e {titulo_max} caracteres, preenchendo o espaço ao \
máximo sem passar do limite.

"comentario": uma Descrição Estratégica para o comentário, para persuadir o cliente e \
impulsionar o vídeo (SEO e copy de vendas), com obrigatoriamente entre 400 e 450 caracteres \
no total (texto + hashtags), terminando com um rodapé de 5 a 10 hashtags complementares \
(cauda longa e sinônimos que não estão no título).

É proibido usar, promover ou associar marcas registradas: nada de logotipos, nomes de \
marcas (ex.: Stanley, Apple) ou identidades visuais em nenhuma parte (título, comentário, \
hashtags). Para produto de marca famosa, use termos genéricos (ex.: "Copo Térmico de Inox" \
e #copotermico em vez da marca).

Antes de responder, analise com rigor o vídeo e o texto que você gerou contra as diretrizes \
da Shopee Vídeo abaixo. Se algo violar uma diretriz, responda "violacao": true e diga em \
"motivo", em uma frase curta, qual regra. Se não, "violacao": false e "motivo": "".

{produto}Diretrizes da Shopee Vídeo:
{diretrizes}"""


# --- Quando mandar ---

def hoje(agora=None):
    return (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d")


def quantos_hoje(config, dia):
    return sortear_teto_do_dia("shopee_video", dia, config["limite_min"], config["limite_max"])


def planejar(config, dia):
    """
    Horários ("HH:MM") dos envios do dia: a janela dividida em partes iguais, um
    horário sorteado dentro de cada parte. Mesmo dia, mesma lista (sorteio fixo).
    """
    quantos = quantos_hoje(config, dia)
    if quantos <= 0:
        return []
    inicio, fim = config["inicio"] * 60, min(config["fim"] * 60, 24 * 60 - 1)
    parte = (fim - inicio) / quantos
    sorteio = random.Random(f"shopee_video:{dia}")
    horarios = []
    for i in range(quantos):
        comeco = inicio + i * parte
        minuto = int(comeco + sorteio.uniform(min(5, parte / 3), max(parte - 5, parte * 2 / 3)))
        horarios.append(f"{minuto // 60:02d}:{minuto % 60:02d}")
    return sorted(horarios)


def estado_do_dia(config, agora=None):
    """O plano de hoje ({data, horarios, feitos}), refeito quando o dia muda."""
    dia = hoje(agora)
    estado = db.ler_config(CHAVE_DIA, {}) or {}
    if estado.get("data") != dia:
        estado = {"data": dia, "horarios": planejar(config, dia), "feitos": 0}
        db.salvar_config(CHAVE_DIA, estado)
    return estado


def vencidos(estado, agora=None):
    """Quantos horários do plano já passaram."""
    hora = (agora or datetime.now(fuso_horario)).strftime("%H:%M")
    return sum(1 for h in estado["horarios"] if h <= hora)


def decidir_envio(config, agora=None):
    """
    True se é hora de mandar um vídeo agora. Marca o horário como feito antes de
    mandar: se o envio falhar, aquele horário fica perdido em vez de repetir em laço.
    Vários horários vencidos de uma vez (robô fora do ar) contam como um só.
    """
    estado = estado_do_dia(config, agora)
    passados = vencidos(estado, agora)
    if passados <= estado["feitos"]:
        return False
    estado["feitos"] = passados
    db.salvar_config(CHAVE_DIA, estado)
    return not config["pausado"]


# --- Qual vídeo ---

def _criar_tabela(con):
    con.execute("CREATE TABLE IF NOT EXISTS shopee_video_enviados ("
                "id_unico TEXT PRIMARY KEY, enviado_em TEXT, status TEXT, motivo TEXT)")


# Consulta de cada fila em tabela: (SQL, prefixo do id). Os Autorais ficam sem prefixo,
# que foi como os primeiros envios foram registrados; as outras levam o nome da fonte
# para um id não colidir com o de outra fila.
CONSULTAS = {
    "autorais": ("SELECT id_unico, caminho_arquivo, legenda FROM fila_autorais ORDER BY data_captura DESC", ""),
    "principal": ("SELECT id_unico, caminho_video, legenda FROM fila_postagens ORDER BY id DESC", "principal:"),
    "publico": ("SELECT id_unico, caminho_arquivo, legenda FROM fila_publico ORDER BY data_captura DESC", "publico:"),
}


def _candidatos(fonte):
    """(id, arquivo, link, legenda) dos vídeos da fonte, do mais novo para o mais velho."""
    if fonte == "viral":
        fila = (db.ler_config("fila_clonagem", {"fila": []}) or {}).get("fila", [])
        fila = sorted(fila, key=lambda item: item.get("data_captura") or "", reverse=True)
        return [(f"viral:{item.get('id')}", item.get("caminho_video"), item.get("link_original"), "")
                for item in fila]
    sql, prefixo = CONSULTAS[fonte]
    with db.conexao() as con:
        linhas = con.execute(sql).fetchall()
    candidatos = []
    for id_unico, arquivo, legenda in linhas:
        link = LINK_DO_POST.search(legenda or "")
        candidatos.append((f"{prefixo}{id_unico}", arquivo, link.group(0) if link else None, legenda))
    return candidatos


def proximo_video(fonte=FONTE_PADRAO):
    """
    {"id", "arquivo", "link", "nome"} do vídeo mais novo da fonte que ainda tem o
    arquivo e o link e não foi mandado; None se não há nenhum.
    """
    try:
        candidatos = _candidatos(fonte if fonte in FONTES else FONTE_PADRAO)
        with db.conexao() as con:
            _criar_tabela(con)
            mandados = {linha[0] for linha in con.execute("SELECT id_unico FROM shopee_video_enviados")}
    except Exception as e:
        logger.warning(f"⚠️ [Shopee Vídeo] Não deu para ler a fila ({fonte}): {type(e).__name__}")
        return None
    for id_unico, arquivo, link, legenda in candidatos:
        if (id_unico in mandados or not arquivo or not link or not os.path.exists(arquivo)
                or arquivo.lower().endswith(EXTENSOES_DE_IMAGEM)):
            continue
        return {"id": id_unico, "arquivo": arquivo, "link": link, "nome": legendas.nome_da_legenda(legenda)}
    return None


def registrar(id_unico, status, motivo="", agora=None):
    momento = (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d %H:%M:%S")
    with db.conexao() as con:
        _criar_tabela(con)
        con.execute("INSERT OR REPLACE INTO shopee_video_enviados VALUES (?, ?, ?, ?)",
                    (id_unico, momento, status, motivo))


def enviados_hoje(agora=None):
    with db.conexao() as con:
        _criar_tabela(con)
        return con.execute("SELECT COUNT(*) FROM shopee_video_enviados WHERE status = 'enviado' "
                           "AND enviado_em LIKE ?", (hoje(agora) + "%",)).fetchone()[0]


# --- Produtos ---

async def produtos_do_link(link):
    """
    (produtos, destino): produtos = lista de {nome, preco, comissao, link} na ordem de
    adicionar (menor preço; no empate, maior comissão), vazia quando o link é de um
    vídeo da Shopee Vídeo (os produtos ficam no próprio vídeo) ou a API não respondeu.
    destino = o endereço para o Rafael abrir.
    """
    destino = await api_shopee.link_para_converter(link)
    produto = api_shopee.produto_do_link(destino)
    if api_shopee.eh_video(destino) or not produto:
        return [], link
    loja, item = re.search(r"/product/(\d+)/(\d+)", produto).groups()
    dados = await _consultar_produto(loja, item)
    if not dados:
        return [], link
    return ordenar_produtos([dados]), link


async def _consultar_produto(loja, item):
    # Números direto na consulta: declarar a variável como Int64 dá "wrong type".
    consulta = (f"query {{ productOfferV2(shopId: {int(loja)}, itemId: {int(item)}, limit: 1) "
                "{ nodes { productName priceMin priceMax commissionRate } } }")
    headers, corpo = api_shopee.gerar_headers_e_payload({"query": consulta})
    try:
        async with aiohttp.ClientSession() as sessao:
            async with sessao.post(URL_API, headers=headers, data=corpo) as resp:
                dados = await resp.json(content_type=None)
    except Exception as e:
        logger.warning(f"⚠️ [Shopee Vídeo] A API de afiliado não respondeu: {type(e).__name__}")
        return None
    nos = (((dados or {}).get("data") or {}).get("productOfferV2") or {}).get("nodes") or []
    if not nos:
        return None
    no = nos[0]
    return {"nome": no.get("productName") or "", "preco": _numero(no.get("priceMin")),
            "comissao": _numero(no.get("commissionRate")) * 100}


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def ordenar_produtos(produtos):
    """Menor preço primeiro; no empate, a maior comissão (regra do Rafael)."""
    return sorted(produtos, key=lambda p: (p["preco"], -p["comissao"]))


# --- Texto da IA ---

def ler_diretrizes():
    try:
        with open(ARQUIVO_DIRETRIZES, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def montar_prompt(nome_produto=""):
    produto = f"Nome do produto, segundo o post (pode ajudar a identificar): {nome_produto}\n\n" if nome_produto else ""
    return PROMPT.format(titulo_min=TITULO_MIN, titulo_max=TITULO_MAX, produto=produto, diretrizes=ler_diretrizes())


def ler_resposta(texto):
    """O JSON da IA como dict ({violacao, motivo, titulo, comentario}); None se não veio um JSON."""
    achado = re.search(r"\{.*\}", texto or "", re.S)
    if not achado:
        return None
    try:
        dados = json.loads(achado.group(0))
    except ValueError:
        return None
    if not isinstance(dados, dict):
        return None
    return {"violacao": bool(dados.get("violacao")), "motivo": str(dados.get("motivo") or "").strip(),
            "titulo": encaixar_titulo(str(dados.get("titulo") or "")),
            "comentario": str(dados.get("comentario") or "").strip()}


def encaixar_titulo(titulo):
    """O título dentro dos 150 caracteres da Shopee: tira palavras do fim, nunca corta uma no meio."""
    titulo = " ".join(titulo.split())
    while len(titulo) > TITULO_MAX and " " in titulo:
        titulo = titulo.rsplit(" ", 1)[0]
    return titulo[:TITULO_MAX]


async def gerar_textos(arquivo, nome_produto=""):
    return ler_resposta(await api_gemini.analisar_video_gemini(arquivo, montar_prompt(nome_produto)))


async def textos_do_video(arquivo, nome_produto=""):
    """
    O texto da IA para o vídeo. Título abaixo de TITULO_MIN: pede mais uma vez e fica com
    o título mais longo; se continuar curto, vai assim mesmo, e a mensagem mostra o
    tamanho para o Rafael completar se quiser. Violação na segunda resposta também vale.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    textos = await gerar_textos(arquivo, nome_produto)
    if not textos or textos["violacao"] or not textos["titulo"] or len(textos["titulo"]) >= TITULO_MIN:
        return textos
    logger.info(f"🔁 [Shopee Vídeo] Título com {len(textos['titulo'])} caracteres "
                f"(mínimo {TITULO_MIN}); pedindo de novo à IA.")
    outra = await gerar_textos(arquivo, nome_produto)
    if outra and outra["titulo"] and (outra["violacao"] or len(outra["titulo"]) > len(textos["titulo"])):
        return outra
    return textos


# --- Mensagem ---

def _reais(valor):
    return f"R$ {valor:.2f}".replace(".", ",")


def _linha_do_produto(produto):
    return (f"{html.escape(produto['nome'])}: {_reais(produto['preco'])}, "
            f"comissão {produto['comissao']:.1f}%").replace(".0%", "%")


def montar_mensagem(textos, produtos, link):
    """
    A mensagem do privado, em passos na ordem de fazer, com título e comentário para
    copiar com um toque: salvar o vídeo, favoritar o produto, postar e comentar.
    Favoritar vem antes de postar: abrir o link do produto no meio da postagem tira o
    Rafael da tela de postar, e ele perde o que já fez.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if len(produtos) == 1:
        favoritar = (f"2️⃣ <b>Favorite o produto</b> ❤️\n{_linha_do_produto(produtos[0])}\n"
                     f"🔗 {html.escape(link)}\nAbra, toque no coração e volte aqui.")
        adicionar = "Adicionar Produto → Minhas Curtidas → o produto → Postar."
    elif produtos:
        linhas = [f"{i}. {_linha_do_produto(p)}" for i, p in enumerate(produtos, 1)]
        favoritar = ("2️⃣ <b>Favorite os produtos</b> ❤️\n" + "\n".join(linhas)
                     + f"\n🔗 {html.escape(link)}\nAbra, toque no coração e volte aqui.")
        adicionar = "Adicionar Produto → Minhas Curtidas → os produtos, na ordem da lista → Postar."
    else:
        favoritar = ("2️⃣ <b>Favorite os produtos</b> ❤️\n"
                     "Abra o link e, em Ver Produtos, favorite só os que o criador vinculou ao vídeo "
                     "(nunca os de Você Também Pode Gostar). Depois volte aqui.\n"
                     f"🔗 {html.escape(link)}")
        adicionar = ("Adicionar Produto → Minhas Curtidas → os produtos: o de menor preço primeiro; "
                     "no empate, o de maior comissão → Postar.")

    tamanho = len(textos["titulo"])
    curto = f", abaixo de {TITULO_MIN} ⚠️" if tamanho < TITULO_MIN else ""
    return (
        "🎬 <b>Postagem pronta para a Shopee Vídeo</b>\n"
        "Siga na ordem: abrir o link no meio da postagem faz a Shopee perder o que você já fez.\n\n"
        "1️⃣ <b>Salve o vídeo</b> acima na galeria.\n\n"
        f"{favoritar}\n\n"
        "3️⃣ <b>Poste:</b> Shopee → Eu → Criadores e Afiliados → Perfil em Shopee Vídeo → "
        "Postar vídeo → escolha o vídeo → Próximo.\n"
        f"📝 <b>Título</b> ({tamanho} caracteres{curto}; toque para copiar):\n"
        f"<code>{html.escape(textos['titulo'])}</code>\n"
        f"{adicionar}\n\n"
        "4️⃣ <b>Depois de postar, comente</b> no vídeo (toque para copiar):\n"
        f"<code>{html.escape(textos['comentario'])}</code>"
    )


# --- Envio ---

async def preparar_e_enviar(bot, admin_id, agora=None, fonte=FONTE_PADRAO):
    """
    Prepara o próximo vídeo e manda no privado. Devolve o que aconteceu, numa frase,
    para o log e para o botão Enviar 1 Agora.
    """
    video = proximo_video(fonte)
    if not video:
        return f"não há vídeo em {FONTES.get(fonte, fonte)} para mandar (a fila está vazia ou sem arquivos)"
    try:
        return await _preparar_e_enviar(bot, admin_id, video, agora)
    except Exception as e:
        # Vídeo que dá erro (ex.: o Telegram recusa o arquivo) é pulado: sem isso, ele
        # voltaria em todo horário e travaria a fila.
        registrar(video["id"], "erro", type(e).__name__, agora)
        raise


async def _preparar_e_enviar(bot, admin_id, video, agora):
    from aiogram.types import FSInputFile

    textos = await textos_do_video(video["arquivo"], video["nome"])
    if not textos or not textos["titulo"]:
        registrar(video["id"], "erro", "a IA não respondeu", agora)
        return "a IA não gerou o texto; o vídeo foi pulado"
    if textos["violacao"]:
        registrar(video["id"], "violacao", textos["motivo"], agora)
        await bot.send_message(admin_id, "⚠️ <b>Shopee Vídeo:</b> pulei um vídeo. A IA viu "
                               f"possível violação das diretrizes: {html.escape(textos['motivo'] or 'sem motivo')}",
                               parse_mode="HTML")
        return "vídeo pulado por possível violação das diretrizes"
    produtos, link = await produtos_do_link(video["link"])
    await bot.send_video(admin_id, video=FSInputFile(video["arquivo"]), supports_streaming=True,
                         caption="🎬 Vídeo para a Shopee Vídeo: siga os passos da mensagem abaixo.")
    await bot.send_message(admin_id, montar_mensagem(textos, produtos, link), parse_mode="HTML",
                           disable_web_page_preview=True)
    registrar(video["id"], "enviado", "", agora)
    return "postagem mandada no seu privado"

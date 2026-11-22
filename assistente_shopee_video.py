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

Com a edição dos vídeos ligada no painel do robô (edicao_video), o vídeo vai já editado,
com o Editor 2, como nos rascunhos do robô (o vídeo original, sem cortes, com a foto do
anúncio no começo, a miniatura, a seta e as legendas; se ele não sai, com o Editor 1, sem
legendas), e o que não dá para editar (link de vídeo, sem uma foto só, ou sem a foto na
API) fica de lado: o assistente tenta o próximo na mesma hora, até VIDEOS_POR_ENVIO.
Pedidos do Rafael (25/10, P40): só vídeo editado; (28/10, P50): o Editor 2 aqui também.

Quando mandar: cada dia sorteia quantos vídeos (a faixa do painel) e espalha os
horários pela janela do painel, com um sorteio fixo por dia. A cada volta do agendador,
manda no máximo um vídeo, e só se um horário já passou. Pausado, os horários que
passam são pulados, para não sair tudo de uma vez ao retomar.

Cada mensagem traz o botão Postei ✅, que o Rafael toca depois de postar. O vídeo mandado com
o robô pausado sozinho, sem o celular (cobrindo), conta no plano do dia do robô: na volta,
ele prepara só o que falta para fechá-lo (P156 1).

O robô nunca posta, curte nem comenta na Shopee (diretriz 9.1.1).
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import asyncio
import hashlib
import html
import json
import logging
import os
import random
import re
import tempfile
import unicodedata
from datetime import datetime

import aiohttp

import api_gemini
import api_shopee
import apelacoes_shopee_video as apelacoes
import db
import legendas
import pedidos_do_canal
import registro_processos
import videos
from fuso import fuso_horario

logger = logging.getLogger("ShopeeVideo")

CHAVE_DIA = "shopee_video_dia"
ARQUIVO_DIRETRIZES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diretrizes_shopee_video.md")
TITULO_MIN, TITULO_MAX = 130, 150
# Os avisos que a Shopee exige em vídeo de bebida alcoólica (e-mail de 26/10/2026): na capa,
# que é a foto do produto no começo do vídeo editado (edicao_video), e no fim do título, que
# no app é a legenda. O aviso falado fica faltando. Escolha do Rafael (P43): DECISOES.md,
# Shopee Vídeo.
AVISOS_DE_ALCOOL = ("Produto destinado a adultos", "Consumo proibido para menores de 18 anos", "Beba com moderação")
TEXTO_DOS_AVISOS = ". ".join(AVISOS_DE_ALCOOL) + "."
SEM_AVISOS = "vídeo de lado: bebida alcoólica só vai com os avisos na capa, e a edição não saiu"
# A bebida alcoólica fica em espera: a página oficial das Diretrizes da Comunidade Shopee Vídeo
# (Central de Ajuda, lida em 31/10/2026) ainda proíbe vendê-la ou divulgá-la, e só o e-mail de
# 26/10 a liberou com os avisos. Enquanto a página não trouxer a regra nova, o robô e o modo
# assistente deixam de lado todo vídeo de bebida alcoólica; o Claude confere a página toda
# segunda e, quando ela mudar, volta isto a False (os avisos da P43 seguem prontos). Escolha
# do Rafael (31/10, P111): DECISOES.md, Shopee Vídeo.
BEBIDA_EM_ESPERA = True
MOTIVO_BEBIDA_EM_ESPERA = ("bebida alcoólica em espera: a página oficial das diretrizes da Shopee Vídeo ainda "
                           "proíbe divulgá-la (P111)")
SEM_BEBIDA = "vídeo de lado: bebida alcoólica em espera (a página oficial ainda proíbe)"


def bebida_em_espera(textos):
    """Se o vídeo é de bebida alcoólica (a IA disse) e a bebida está em espera (BEBIDA_EM_ESPERA)."""
    return bool(BEBIDA_EM_ESPERA and textos and textos.get("bebida_alcoolica") is True)
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
# Com a edição ligada, quantos vídeos o assistente tenta numa vez até achar um que sai
# editado; e a frase do resultado do que fica de lado por isso.
VIDEOS_POR_ENVIO = 5
SEM_EDICAO = "vídeo de lado: a edição não saiu (só vídeo editado vai)"
# O link que não diz o produto (link de vídeo do Ver Produtos, ou produto sem oferta): sem o
# celular, o assistente não tem a foto do anúncio para a edição. Fica de lado, como o que não
# sai editado, mas não é falha: o robô, com o celular, acha os produtos do Ver Produtos.
SEM_PRODUTO_NO_LINK = "vídeo de lado: o link não diz o produto (link de vídeo ou sem oferta), sem a foto para a edição"
# O produto que já foi ao ar não se repete: o do vídeo, pelo número do anúncio, conferido como o
# robô confere (os rascunhos dele que esperam a aprovação, os aprovados e os postados, e os vídeos
# daqui marcados com Postei ✅). Fica de lado, sem gastar a edição nem a IA, e vai o próximo da
# fonte. Escolha do Rafael (06/11, P167 1): DECISOES.md, Shopee Vídeo.
JA_POSTADO = "vídeo de lado: o produto já foi postado (pelo robô ou marcado com Postei ✅)"
SEM_TEXTO_DA_IA = "a IA não gerou o texto; o vídeo foi pulado"
VIOLACAO = "vídeo pulado por possível violação das diretrizes"

PROMPT = """Atue como um especialista em Growth Hacking e Marketing para Shopee. Analise \
detalhadamente o vídeo (produto, estilo e público-alvo) e gere o texto para postar na Shopee Vídeo.

Responda SOMENTE com um JSON, sem nada antes ou depois, neste formato:
{{"violacao": false, "motivo": "", "feito_por_ia": false, "sinal_ia": "", "bebida_alcoolica": false, \
"titulo": "...", "comentario": "..."}}

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

"feito_por_ia": true só se o vídeo for claramente gerado por IA (imagens geradas por IA, \
avatar ou apresentador artificial, voz sintética narrando). Vídeo filmado de verdade, mesmo \
com cortes, filtros, legendas, música ou imagens do anúncio, é false; na dúvida, false. Julgue \
só o vídeo, nunca o nome do produto: produto artificial (planta, flor ou cabelo artificial) num \
vídeo filmado não é conteúdo gerado por IA. Quando for true, diga em "sinal_ia", em uma frase \
curta, o que no vídeo mostra que é IA; senão, "sinal_ia": "".

"bebida_alcoolica": true se o produto vendido no vídeo for bebida alcoólica (cerveja, vinho, \
destilado, licor, drink pronto com álcool); copo, taça, balde de gelo, abridor e outros \
acessórios são false. Bebida alcoólica sozinha não é violação: os avisos obrigatórios da capa e \
da legenda são postos depois, fora do seu texto; é violação só o que continua proibido nas \
diretrizes (menor de idade bebendo, incentivo ao consumo excessivo, glorificar a bebida).

{produto}Diretrizes da Shopee Vídeo:
{diretrizes}"""


# --- Quando mandar ---

def hoje(agora=None):
    return (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d")


def quantos_hoje(config, dia):
    """
    Quantos envios o dia faz: o sorteio na faixa do painel e, com 4 pontos de penalidade ou mais
    na Saúde do Vídeo, a parte dela com o teto da escada, como no robô (P145). Decisão do Rafael:
    DECISOES.md, Shopee Vídeo.
    """
    momento = datetime.strptime(dia, "%Y-%m-%d").replace(hour=12, tzinfo=fuso_horario)
    return apelacoes.quantos_pelos_pontos("shopee_video", dia, config["limite_min"], config["limite_max"],
                                          apelacoes.pontos_de_agora(agora=momento))


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

# As colunas que vieram depois entram na tabela que já existe no servidor. cobrindo: "1" no vídeo
# mandado enquanto o robô estava pausado sozinho, sem o celular (o assistente cobrindo o robô);
# postado_em: quando o Rafael tocou em Postei ✅ nele (P156 1). item: o número (itemId) do produto do
# vídeo mandado: o robô não repete o produto que o Rafael postou (P166 1). amigo: o id do Telegram do amigo que
# recebeu o vídeo no grupo dos amigos (P271 2): o produto não volta para ele (amigos_shopee_video).
COLUNAS_NOVAS = ("cobrindo", "postado_em", "item", "amigo")


def _criar_tabela(con):
    con.execute("CREATE TABLE IF NOT EXISTS shopee_video_enviados ("
                "id_unico TEXT PRIMARY KEY, enviado_em TEXT, status TEXT, motivo TEXT)")
    existentes = {linha[1] for linha in con.execute("PRAGMA table_info(shopee_video_enviados)")}
    for coluna in COLUNAS_NOVAS:
        if coluna not in existentes:
            con.execute(f"ALTER TABLE shopee_video_enviados ADD COLUMN {coluna} TEXT")


# Consulta de cada fila em tabela: (SQL, prefixo do id). Os Autorais ficam sem prefixo,
# que foi como os primeiros envios foram registrados; as outras levam o nome da fonte
# para um id não colidir com o de outra fila.
CONSULTAS = {
    "autorais": ("SELECT id_unico, caminho_arquivo, legenda FROM fila_autorais ORDER BY data_captura DESC", ""),
    "principal": ("SELECT id_unico, caminho_video, legenda FROM fila_postagens ORDER BY id DESC", "principal:"),
    "publico": ("SELECT id_unico, caminho_arquivo, legenda FROM fila_publico ORDER BY data_captura DESC", "publico:"),
}


# O arquivo escrito mais que isto depois da captura do clone (os segundos no id dele) é de outro clone.
FOLGA_DO_ARQUIVO_DO_CLONE = 10 * 60


def arquivo_do_proprio_clone(item):
    """
    Se o arquivo do item da fila do Espião é o vídeo dele. O arquivo com o id do clone no nome é
    dele. O de nome antigo ("temp_clone_ (N)", o primeiro nome livre que o Telethon dava) pode ser de
    outro clone: depois que o vídeo de um clone já postado no Viral sai do disco, o próximo baixado
    pegava o nome, e o item antigo, que fica na fila até o fim do dia, apontava para o vídeo novo (o
    robô juntava o link de um vídeo com o arquivo de outro; 07/11, 15:57 e 16:11). O id guarda a hora
    da captura, depois do download: o arquivo escrito bem depois dela é de outro clone.
    """
    caminho, ident = str(item.get("caminho_video") or ""), str(item.get("id") or "")
    if ident and ident in os.path.basename(caminho):
        return True
    try:
        capturado = int(ident.split("_")[1])
        return os.path.getmtime(caminho) <= capturado + FOLGA_DO_ARQUIVO_DO_CLONE
    except (IndexError, ValueError, OSError):
        # Sem a hora no id ou sem o arquivo, não há o que comparar (o que não existe já fica de fora).
        return True


def _candidatos(fonte):
    """(id, arquivo, link, legenda) dos vídeos da fonte, do mais novo para o mais velho."""
    if fonte == "viral":
        fila = (db.ler_config("fila_clonagem", {"fila": []}) or {}).get("fila", [])
        # O que o Espião trouxe do Canal Afiliados é nosso (o vídeo que o robô postou, os posts
        # do Rafael): pegar de volta daria loop. Pedido do Rafael (30/10): DECISOES.md, Shopee Vídeo.
        fila = [item for item in fila if str(item.get("chat_origem")) != pedidos_do_canal.CANAL
                and arquivo_do_proprio_clone(item)]
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


def candidatos_nao_usados(fonte):
    """
    (id, arquivo, link, legenda) dos vídeos da fonte que nem o assistente mandou nem o robô
    automático usou, do mais novo para o mais velho (para o explorar e o investigar_robo).
    """
    with db.conexao() as con:
        _criar_tabela(con)
        usados = {linha[0] for linha in con.execute("SELECT id_unico FROM shopee_video_enviados")}
        try:
            usados |= {linha[0] for linha in con.execute("SELECT id_video FROM shopee_video_rascunhos")}
        except Exception:
            pass    # o robô automático ainda não criou a tabela dele
    return [candidato for candidato in _candidatos(fonte if fonte in FONTES else FONTE_PADRAO)
            if candidato[0] not in usados]


def proximo_video(fonte=FONTE_PADRAO, pular=()):
    """
    {"id", "arquivo", "link", "nome"} do vídeo mais novo da fonte que ainda tem o
    arquivo e o link e não foi mandado, fora o arquivo que o robô já levou ao Canal
    Afiliados (o loop); None se não há nenhum. pular: os ids que quem chama já olhou e deixou
    para outra pessoa (o produto que o amigo já recebeu, amigos_shopee_video).
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
        if (id_unico in mandados or id_unico in pular or not arquivo or not link or not os.path.exists(arquivo)
                or arquivo.lower().endswith(EXTENSOES_DE_IMAGEM) or pedidos_do_canal.ja_foi_ao_canal(arquivo)):
            continue
        return {"id": id_unico, "arquivo": arquivo, "link": link, "nome": legendas.nome_da_legenda(legenda)}
    return None


def registrar(id_unico, status, motivo="", agora=None, cobrindo=False, item="", amigo=""):
    momento = (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d %H:%M:%S")
    with db.conexao() as con:
        _criar_tabela(con)
        con.execute("INSERT OR REPLACE INTO shopee_video_enviados (id_unico, enviado_em, status, motivo, cobrindo, "
                    "item, amigo) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (id_unico, momento, status, motivo, "1" if cobrindo else "", item, str(amigo or "")))


def itens_do_amigo(amigo):
    """Os números (itemId) dos produtos dos vídeos que o amigo já recebeu no grupo dos amigos (P271 2)."""
    with db.conexao() as con:
        _criar_tabela(con)
        return {linha[0] for linha in con.execute(
            "SELECT item FROM shopee_video_enviados WHERE status = 'enviado' AND amigo = ? "
            "AND COALESCE(item, '') != ''", (str(amigo),))}


def produtos_ja_postados():
    """Os números (itemId) dos produtos que já foram ao ar, os mesmos que o robô confere (P166 1 e P167 1)."""
    # O robô importa este módulo: o import fica aqui dentro.
    import robo_shopee_video
    return robo_shopee_video.produtos_ja_postados()


def _anotar_onde_ja_foi(item):
    """O registro diz onde estava o produto do vídeo deixado de lado, como no robô (P167 1)."""
    import robo_shopee_video
    robo_shopee_video.anotar_onde_ja_foi(item, "assistente")


def itens_postados():
    """Os números (itemId) dos produtos dos vídeos mandados que o Rafael marcou com Postei ✅ (P166 1)."""
    with db.conexao() as con:
        _criar_tabela(con)
        return [linha[0] for linha in con.execute(
            "SELECT item FROM shopee_video_enviados WHERE status = 'enviado' AND COALESCE(postado_em, '') != '' "
            "AND COALESCE(item, '') != ''")]


# O botão Postei ✅ de cada vídeo mandado: o Rafael toca depois de postar. O vídeo mandado com o
# robô sem o celular (cobrindo) conta no plano do dia do robô, que na volta prepara só o que falta
# para fechá-lo (robo_shopee_video.consumir_horarios). Escolha do Rafael (05/11, P156 1):
# DECISOES.md, Shopee Vídeo.
CALLBACK_POSTEI = "sv_postei:"
BOTAO_POSTEI = "Postei ✅"
MARCADO, JA_MARCADO, NAO_ACHADO = "marcado", "já marcado", "não achado"


def chave_do_envio(id_unico):
    """O id do vídeo em poucos caracteres, para o botão: o Telegram aceita até 64 bytes no callback."""
    return hashlib.sha1(id_unico.encode()).hexdigest()[:16]


def botao_postei(id_unico):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=BOTAO_POSTEI, callback_data=f"{CALLBACK_POSTEI}{chave_do_envio(id_unico)}")]])


def marcar_postado(chave, agora=None):
    """
    O Rafael tocou em Postei ✅: guarda a hora no vídeo mandado (o de chave_do_envio). Devolve
    (MARCADO, JA_MARCADO ou NAO_ACHADO, se ele saiu cobrindo o robô).
    """
    momento = (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d %H:%M:%S")
    with db.conexao() as con:
        _criar_tabela(con)
        linhas = con.execute("SELECT id_unico, postado_em, cobrindo FROM shopee_video_enviados "
                             "WHERE status = 'enviado'").fetchall()
        for id_unico, postado_em, cobrindo in linhas:
            if chave_do_envio(id_unico) != chave:
                continue
            if postado_em:
                return JA_MARCADO, cobrindo == "1"
            con.execute("UPDATE shopee_video_enviados SET postado_em = ? WHERE id_unico = ?", (momento, id_unico))
            return MARCADO, cobrindo == "1"
    return NAO_ACHADO, False


def postados_cobrindo_o_robo(dia):
    """
    Os ids dos vídeos que saíram com o robô sem o celular e que o Rafael marcou como postados no dia
    (AAAA-MM-DD), na ordem em que ele marcou (P156 1).
    """
    with db.conexao() as con:
        _criar_tabela(con)
        return [linha[0] for linha in con.execute(
            "SELECT id_unico FROM shopee_video_enviados WHERE status = 'enviado' AND cobrindo = '1' "
            "AND postado_em LIKE ? ORDER BY postado_em, id_unico", (dia + "%",))]


def sem_postei_cobrindo_o_robo(dia):
    """Quantos vídeos mandados no dia (AAAA-MM-DD) com o robô sem o celular ainda estão sem o Postei ✅."""
    with db.conexao() as con:
        _criar_tabela(con)
        return con.execute("SELECT COUNT(*) FROM shopee_video_enviados WHERE status = 'enviado' AND cobrindo = '1' "
                           "AND enviado_em LIKE ? AND COALESCE(postado_em, '') = ''", (dia + "%",)).fetchone()[0]


def enviados_hoje(agora=None):
    """Os vídeos que o assistente mandou hoje no privado (os do grupo dos amigos não contam no plano do dia)."""
    with db.conexao() as con:
        _criar_tabela(con)
        return con.execute("SELECT COUNT(*) FROM shopee_video_enviados WHERE status = 'enviado' "
                           "AND enviado_em LIKE ? AND COALESCE(amigo, '') = ''", (hoje(agora) + "%",)).fetchone()[0]


def enviados_aos_amigos(agora=None):
    """(hoje, no total): os vídeos mandados no grupo dos amigos (amigos_shopee_video), para o painel dele."""
    with db.conexao() as con:
        _criar_tabela(con)
        hoje_, total = con.execute(
            "SELECT COALESCE(SUM(enviado_em LIKE ?), 0), COUNT(*) FROM shopee_video_enviados WHERE status = 'enviado' "
            "AND COALESCE(amigo, '') != ''", (hoje(agora) + "%",)).fetchone()
    return int(hoje_), int(total)


# --- Produtos ---

async def produtos_do_link(link):
    """
    (produtos, destino): produtos = lista de {nome, preco, comissao, imagem, item} na ordem de
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
    return ordenar_produtos([{**dados, "item": item}]), link


async def _consultar_produto(loja, item):
    # Números direto na consulta: declarar a variável como Int64 dá "wrong type".
    consulta = (f"query {{ productOfferV2(shopId: {int(loja)}, itemId: {int(item)}, limit: 1) "
                "{ nodes { productName priceMin priceMax commissionRate imageUrl } } }")
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
            "comissao": _numero(no.get("commissionRate")) * 100, "imagem": no.get("imageUrl") or ""}


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def ordenar_produtos(produtos):
    """Menor preço primeiro; no empate, a maior comissão (regra do Rafael)."""
    return sorted(produtos, key=lambda p: (p["preco"], -p["comissao"]))


# --- Texto da IA ---

# As mesmas regras das diretrizes em palavras leves. O filtro do Google recusa o pedido
# (PROHIBITED_CONTENT) quando o texto com nudez, exploração infantil e menores vai junto com
# um vídeo comum que mostra uma pessoa (máscara de cílios, folha depilatória, 25/10/2026).
# Da mais longa para a mais curta; o espaço casa também com a quebra de linha do arquivo.
# Escolha do Rafael (P28): DECISOES.md, Shopee Vídeo.
TROCAS_LEVES = [
    ("Qualquer sexualização, nudez ou roupa reveladora", "Qualquer conteúdo impróprio ou roupa inadequada"),
    ("Suicídio, automutilação e atos perigosos", "Saúde e atos perigosos"),
    ("qualquer coisa sexual com animais", "qualquer coisa imprópria com animais"),
    ("Violência e imagens chocantes", "Agressão e imagens chocantes"),
    ("Nudez, imitação de nudez", "Pouca roupa ou aparência de pouca roupa"),
    ("sexo sem consentimento", "conteúdo adulto"),
    ("exploração infantil", "conteúdo impróprio com crianças"),
    ("Menores de idade", "Crianças e adolescentes"),
    ("menores de idade", "crianças e adolescentes"),
    ("menores de 18 anos", "pessoas abaixo de 18 anos"),
    ("Nudez e sexo", "Conteúdo adulto"),
    ("menor em atividade", "criança em atividade"),
    ("linguagem sexual", "linguagem adulta"),
    ("beijo erótico", "beijo provocante"),
    ("ambiente íntimo", "ambiente particular"),
    ("partes íntimas", "partes do corpo"),
    ("violência realista", "cenas fortes"),
    ("mortos, feridas", "cenas tristes"),
    ("sexualizar", "provocar"),
    ("sexualização", "conteúdo impróprio"),
    ("fetiche", "conteúdo adulto"),
    ("Terrorismo", "Grupos extremistas"),
    ("se ferir", "se machucar"),
    ("violência", "agressão"),
    ("sexual", "adulto"),
    ("nudez", "pouca roupa"),
    ("abuso", "maus-tratos"),
]


def ler_diretrizes(leves=False):
    """O resumo das diretrizes; leves=True: as mesmas regras com TROCAS_LEVES."""
    try:
        with open(ARQUIVO_DIRETRIZES, encoding="utf-8") as f:
            texto = f.read()
    except OSError:
        return ""
    if leves:
        for forte, leve in TROCAS_LEVES:
            texto = re.sub(r"\s+".join(map(re.escape, forte.split())), leve, texto)
    return texto


def montar_prompt(nome_produto="", leves=False):
    produto = f"Nome do produto, segundo o post (pode ajudar a identificar): {nome_produto}\n\n" if nome_produto else ""
    return PROMPT.format(titulo_min=TITULO_MIN, titulo_max=TITULO_MAX, produto=produto,
                         diretrizes=ler_diretrizes(leves))


# A recusa do Google no último textos_do_video, para o aviso ao Rafael (escolha dele, P29):
# o que o Google disse (api_gemini.ULTIMA_RECUSA) e "leves" = o que deu o pedido refeito
# com as regras em palavras leves ("passou", "recusado de novo" ou "sem resposta"). None
# se o Google não recusou.
ULTIMA_RECUSA = None

# O que cada código e cada categoria do Google quer dizer, em palavras simples.
CODIGOS_DO_GOOGLE = {
    "PROHIBITED_CONTENT": "conteúdo proibido (o Google não diz qual parte)",
    "BLOCKLIST": "palavra da lista proibida do Google",
    "SPII": "dado pessoal sensível",
    "SAFETY": "segurança",
    "IMAGE_SAFETY": "imagem imprópria",
}
CATEGORIAS_DO_GOOGLE = {
    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "sexual",
    "HARM_CATEGORY_DANGEROUS_CONTENT": "perigoso",
    "HARM_CATEGORY_HARASSMENT": "assédio",
    "HARM_CATEGORY_HATE_SPEECH": "ódio",
    "HARM_CATEGORY_CIVIC_INTEGRITY": "política",
}
NIVEIS_DO_GOOGLE = {"HIGH": "alto", "MEDIUM": "médio", "LOW": "baixo", "NEGLIGIBLE": "mínimo"}


def texto_da_recusa(recusa, produto=""):
    """O aviso do vídeo recusado pelo Google: o produto, o que o Google disse e o pedido refeito."""
    codigos = ", ".join(f"{CODIGOS_DO_GOOGLE.get(c, c)} ({c})" for c in recusa.get("codigos") or []) or "sem código"
    categorias = ", ".join(f"{CATEGORIAS_DO_GOOGLE.get(c, c)} ({NIVEIS_DO_GOOGLE.get(n, n)})"
                           for c, n in recusa.get("categorias") or [])
    leves = {
        "passou": "passou ✅: a causa era o texto das diretrizes no pedido, não o vídeo. O vídeo segue normalmente.",
        "recusado de novo": "recusado de novo ❌: o problema parece ser o próprio vídeo. Ele foi pulado.",
    }.get(recusa.get("leves"), "a IA não respondeu ⚠️ (tenta de novo mais tarde ou pula o vídeo).")
    return (f"🚫 Shopee Vídeo: o Google recusou o pedido do título deste vídeo.\n\n"
            f"Produto: {produto or 'não identificado'}\n"
            f"O que o Google disse: {codigos}\n"
            + (f"Categorias marcadas: {categorias}\n" if categorias else "")
            + f"\nPedido de novo com as regras em palavras leves: {leves}")


def recusado_pelo_conteudo():
    """A última análise de vídeo foi recusada pelo Google pelo conteúdo do pedido?"""
    return bool(api_gemini.BLOQUEIOS_DO_CONTEUDO & api_gemini.codigos_do_google(api_gemini.ULTIMO_ERRO_IA))


def ler_resposta(texto):
    """
    O JSON da IA como dict ({violacao, motivo, feito_por_ia, sinal_ia, bebida_alcoolica,
    titulo, comentario}); None se não veio um JSON. feito_por_ia e bebida_alcoolica só valem
    com true de verdade. Na bebida alcoólica, o título já leva os avisos no fim.
    """
    achado = re.search(r"\{.*\}", texto or "", re.S)
    if not achado:
        return None
    try:
        dados = json.loads(achado.group(0))
    except ValueError:
        return None
    if not isinstance(dados, dict):
        return None
    alcool = dados.get("bebida_alcoolica") is True
    titulo = str(dados.get("titulo") or "")
    return {"violacao": bool(dados.get("violacao")), "motivo": str(dados.get("motivo") or "").strip(),
            "feito_por_ia": dados.get("feito_por_ia") is True, "sinal_ia": str(dados.get("sinal_ia") or "").strip(),
            "bebida_alcoolica": alcool,
            "titulo": titulo_com_avisos(titulo) if alcool and titulo.strip() else encaixar_titulo(titulo),
            "comentario": str(dados.get("comentario") or "").strip()}


def tamanho_no_app(texto):
    """
    O tamanho como o contador da Shopee conta (o "x/150" da legenda): cada emoji de fora
    do plano básico (💡, 👗) vale 2, como no Motorola em 23/10/2026 ("Teste 💡 ok 👗 fim ✨",
    18 caracteres, apareceu como 20/150).
    """
    return len((texto or "").encode("utf-16-le")) // 2


def encaixar_titulo(titulo, limite=TITULO_MAX):
    """O título dentro dos 150 do contador da Shopee: tira palavras do fim, nunca corta uma no meio."""
    titulo = " ".join(titulo.split())
    while tamanho_no_app(titulo) > limite and " " in titulo:
        titulo = titulo.rsplit(" ", 1)[0]
    while tamanho_no_app(titulo) > limite:
        titulo = titulo[:-1]
    return titulo


def titulo_com_avisos(titulo):
    """
    O título da bebida alcoólica, com os avisos no fim e tudo dentro dos 150: o título perde
    palavras do fim (as hashtags primeiro), os avisos nunca.
    """
    espaco = TITULO_MAX - tamanho_no_app(TEXTO_DOS_AVISOS) - 1
    return f"{encaixar_titulo(titulo, espaco)} {TEXTO_DOS_AVISOS}".strip()


async def gerar_textos(arquivo, nome_produto="", leves=False):
    return ler_resposta(await api_gemini.analisar_video_gemini(arquivo, montar_prompt(nome_produto, leves)))


async def textos_do_video(arquivo, nome_produto=""):
    """
    O texto da IA para o vídeo. Recusado pelo Google pelo conteúdo do pedido: pede mais uma
    vez com as regras em palavras leves (TROCAS_LEVES), e os textos dizem "regras_leves".
    Título abaixo de TITULO_MIN: pede mais uma vez e fica com o título mais longo; se
    continuar curto, vai assim mesmo, e a mensagem mostra o tamanho para o Rafael completar
    se quiser. Violação na segunda resposta também vale.
    Decisões do Rafael (P28 e o título curto): DECISOES.md, Shopee Vídeo.
    """
    global ULTIMA_RECUSA
    api_gemini.ULTIMO_ERRO_IA = None
    ULTIMA_RECUSA, leves = None, False
    textos = await gerar_textos(arquivo, nome_produto)
    if textos is None and recusado_pelo_conteudo():
        logger.info("🔁 [Shopee Vídeo] O Google recusou o pedido pelo conteúdo; pedindo de novo com as "
                    "regras em palavras leves.")
        recusa, leves = dict(api_gemini.ULTIMA_RECUSA or {}), True
        textos = await gerar_textos(arquivo, nome_produto, leves=True)
        if textos:
            textos["regras_leves"] = True
        recusa["leves"] = "passou" if textos else "recusado de novo" if recusado_pelo_conteudo() else "sem resposta"
        ULTIMA_RECUSA = recusa
    if not textos or textos["violacao"] or not textos["titulo"] or tamanho_no_app(textos["titulo"]) >= TITULO_MIN:
        return textos
    logger.info(f"🔁 [Shopee Vídeo] Título com {tamanho_no_app(textos['titulo'])} caracteres "
                f"(mínimo {TITULO_MIN}); pedindo de novo à IA.")
    outra = await gerar_textos(arquivo, nome_produto, leves=leves)
    if outra and leves:
        outra["regras_leves"] = True
    if outra and outra["titulo"] and (outra["violacao"]
                                      or tamanho_no_app(outra["titulo"]) > tamanho_no_app(textos["titulo"])):
        return outra
    return textos


# --- O nome de cada produto no vídeo (P265 1) ---
# Na janela "Editar informações do produto" que o Adicionar abre, o app deixa trocar o nome que o vídeo mostra no
# cartão do produto (de 10 a 255 letras; com o campo vazio, vai o nome do anúncio). Escolha do Rafael (21/11, P265 1):
# cada produto do post ganha um nome curto da IA, que destaca o produto e ajuda a vender, fiel ao anúncio, sem marca
# nem personagem (diretriz 7: o nome genérico) e sem promoção inventada (diretriz 14); o modo assistente manda o nome
# junto, para ele colar. DECISOES.md, Shopee Vídeo.
LETRAS_DO_NOME_NO_VIDEO = (20, 40)
# A régua de quem confere o nome na tela (o robô, na tela final e no Tirar Produto): sem os sinais e os emojis, pelo
# menos LETRAS_MINIMAS_DO_NOME (a do nome cortado, postador_shopee_video.TAMANHO_MINIMO_DO_NOME); e no máximo
# LETRAS_MAXIMAS_DO_NOME no contador da Shopee (cada emoji vale 2), para caber no cartão do vídeo.
LETRAS_MINIMAS_DO_NOME = 15
LETRAS_MAXIMAS_DO_NOME = 45
# Preço, promoção e frete nunca vão no nome (diretriz 14): a IA é avisada, e o nome com um deles fica de fora.
PALAVRAS_DE_PROMOCAO = ("desconto", "promoç", "promoc", "frete", "grátis", "gratis", "oferta", "cupom", "barat",
                        "liquida", "queima", "imperdível", "imperdivel", "black friday", "r$", "%")
PROMPT_DOS_NOMES = """Você escreve o nome que aparece no cartão do produto de um vídeo da Shopee Vídeo. \
Para cada nome de anúncio da lista abaixo, escreva um nome novo que destaque o produto e ajude a vender, \
seguindo todas as regras:
1. De {minimo} a {maximo} letras, contando os espaços, terminado com um emoji que combine com o produto \
(ex.: o anúncio "Caneca Personagem X Presente Geek Nerd Colecionável Pronta Entrega" vira "Caneca Geek \
Colecionável para Presente ☕").
2. Primeiro o que o produto é; depois a vantagem principal que o nome do anúncio diz.
3. Fiel ao anúncio: só o que o nome do anúncio diz. Não invente material, tamanho, quantidade, cor, função, \
garantia nem resultado.
4. Sem marca, logo, slogan, personagem, time, filme, desenho, artista ou nome de loja: use o nome genérico \
(diretriz 7 da Shopee Vídeo; ex.: "Copo Térmico", não a marca do copo).
5. Sem preço, desconto, promoção, frete, cupom, porcentagem ou urgência (diretriz 14: nada de promoção \
inventada nem informação falsa).
6. Português do Brasil, com a ortografia certa, sem hashtag e sem o nome inteiro em CAIXA ALTA.
7. Cada produto com um nome diferente dos outros da lista, mesmo quando são o mesmo item de lojas diferentes.

Responda SOMENTE com um JSON, sem nada antes ou depois: uma lista com um objeto por produto, na ordem da lista, \
cada um com "n" (o número do produto), "nome" (o nome novo) e "tirados" (as marcas, os personagens e os nomes de \
loja que estavam no nome do anúncio e ficaram de fora; [] sem nenhum).

Produtos:
{produtos}"""


def letras_do_nome(texto):
    """O nome como o robô o compara na tela: sem caixa, sem os sinais e sem os emojis (ps._nome_normal)."""
    texto = unicodedata.normalize("NFKC", str(texto or "")).casefold()
    return " ".join("".join(c if c.isalnum() else " " for c in texto).split())


def nome_valido(nome, tirados=()):
    """
    O nome da IA pode ir ao cartão do produto? Do tamanho da régua (LETRAS_MINIMAS_DO_NOME e LETRAS_MAXIMAS_DO_NOME),
    sem preço, promoção nem frete (PALAVRAS_DE_PROMOCAO), sem hashtag e sem as marcas e os personagens que a própria IA
    disse ter tirado (tirados).
    """
    nome = " ".join(str(nome or "").split())
    if len(letras_do_nome(nome)) < LETRAS_MINIMAS_DO_NOME or tamanho_no_app(nome) > LETRAS_MAXIMAS_DO_NOME:
        return False
    if "#" in nome or any(palavra in nome.casefold() for palavra in PALAVRAS_DE_PROMOCAO):
        return False
    palavras = f" {letras_do_nome(nome)} "
    return not any(f" {tirado} " in palavras for tirado in (letras_do_nome(t) for t in tirados or ()) if tirado)


def ler_os_nomes(resposta, nomes):
    """
    {nome do anúncio: nome da IA} da resposta (a lista em JSON), na ordem de nomes: só os que passam na régua
    (nome_valido) e sem repetir um nome (o 2º produto com o mesmo nome fica com o do anúncio). {} sem a lista.
    """
    achado = re.search(r"\[.*\]", resposta or "", re.S)
    try:
        itens = json.loads(achado.group(0)) if achado else []
    except ValueError:
        return {}
    novos, vistos = {}, set()
    for item in itens if isinstance(itens, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            n = int(item.get("n"))
        except (TypeError, ValueError):
            continue
        nome = " ".join(str(item.get("nome") or "").split()).strip("\"'“”")
        tirados = [str(t) for t in item.get("tirados") or [] if isinstance(t, str)] \
            if isinstance(item.get("tirados"), list) else []
        if not 1 <= n <= len(nomes) or nomes[n - 1] in novos or not nome_valido(nome, tirados):
            continue
        if letras_do_nome(nome) in vistos:
            continue
        vistos.add(letras_do_nome(nome))
        novos[nomes[n - 1]] = nome
    return novos


async def nomes_no_video(nomes):
    """
    O nome que cada produto leva no cartão do vídeo (P265 1): {nome do anúncio: nome da IA}, num pedido só para a lista
    toda, só com os que passam na régua (ler_os_nomes); {} sem a resposta da IA. O que fica de fora vai com o nome do
    anúncio, como antes.
    """
    nomes = [nome for nome in dict.fromkeys(str(n or "").strip() for n in nomes or ()) if nome]
    if not nomes:
        return {}
    lista = "\n".join(f"{n}. {nome}" for n, nome in enumerate(nomes, 1))
    resposta = await api_gemini.gerar_texto_gemini(PROMPT_DOS_NOMES.format(
        minimo=LETRAS_DO_NOME_NO_VIDEO[0], maximo=LETRAS_DO_NOME_NO_VIDEO[1], produtos=lista))
    return ler_os_nomes(resposta, nomes)


# --- Mensagem ---

def _reais(valor):
    return f"R$ {valor:.2f}".replace(".", ",")


def _linha_do_produto(produto):
    return (f"{html.escape(produto['nome'])}: {_reais(produto['preco'])}, "
            f"comissão {produto['comissao']:.1f}%").replace(".0%", "%")


def _passo_do_nome(produtos, nomes):
    """
    O nome da IA de cada produto, para o Rafael colar em Nome do produto, na janela que o Adicionar abre, antes do
    Feito (P265 1); "" sem nenhum. O produto sem o nome da IA fica com o do anúncio (o campo vazio).
    """
    no_video = [nomes.get(p["nome"], "") for p in produtos]
    if not any(no_video):
        return ""
    if len(no_video) == 1:
        lista = f"<code>{html.escape(no_video[0])}</code>"
    else:
        lista = "\n".join(f"{n}. " + (f"<code>{html.escape(nome)}</code>" if nome
                                      else "fica o nome do anúncio (deixe o campo vazio)")
                          for n, nome in enumerate(no_video, 1))
    return ("🏷️ <b>Nome no vídeo:</b> na janela que abre no Adicionar, toque em Nome do produto, cole o nome "
            f"(toque para copiar) e depois em Feito.\n{lista}\n")


def montar_mensagem(textos, produtos, link, mudo=False, cobrindo=False, nomes=None, amigo=""):
    """
    A mensagem do privado, em passos na ordem de fazer, com título e comentário para
    copiar com um toque: salvar o vídeo, favoritar o produto, postar, comentar e tocar em
    Postei ✅ (o botão da mensagem; com cobrindo=True, o robô está sem o celular, e o passo diz
    que o vídeo conta no plano do dia dele, P156 1). nomes ({nome do anúncio: nome da IA}): o nome de
    cada produto no vídeo, para copiar no Adicionar (P265 1). amigo (a menção, em HTML): a mensagem vai ao
    grupo dos amigos, chamando o amigo, sem o Postei ✅, que é do plano do Rafael (P277 1).
    Favoritar vem antes de postar: abrir o link do produto no meio da postagem tira o
    Rafael da tela de postar, e ele perde o que já fez. Com mudo=True (o vídeo que vai não
    tem som: o editado já leva a música de fundo, P55), o passo de postar lembra de pôr uma
    música da Shopee (P48).
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

    tamanho = tamanho_no_app(textos["titulo"])
    curto = f", abaixo de {TITULO_MIN} ⚠️" if tamanho < TITULO_MIN else ""
    alcool = ("🔞 <b>Bebida alcoólica:</b> os 3 avisos da Shopee já estão na capa (a foto do começo do vídeo) e "
              "no fim do título. Deixe a capa no 1º quadro e não tire os avisos do título.\n"
              if textos.get("bebida_alcoolica") else "")
    musica = ("🔇 <b>Vídeo sem som:</b> na tela de edição, a que vem depois do Próximo, toque em Adicionar "
              "Música, escolha uma música da Shopee e toque em Próximo.\n" if mudo else "")
    postei = ("" if amigo else f"\n\n5️⃣ <b>Postou?</b> Toque em <b>{BOTAO_POSTEI}</b> aqui embaixo."
              + (" O robô está sem o celular, e este vídeo conta no plano de hoje dele: na volta, ele prepara só o "
                 "que falta para fechar o dia." if cobrindo else ""))
    return (
        (f"🎬 {amigo}, a sua postagem para a Shopee Vídeo está pronta\n" if amigo
         else "🎬 <b>Postagem pronta para a Shopee Vídeo</b>\n")
        + "Siga na ordem: abrir o link no meio da postagem faz a Shopee perder o que você já fez.\n\n"
        "1️⃣ <b>Salve o vídeo</b> acima na galeria.\n\n"
        f"{favoritar}\n\n"
        "3️⃣ <b>Poste:</b> Shopee → Eu → Criadores e Afiliados → Perfil em Shopee Vídeo → "
        "Postar vídeo → escolha o vídeo → Próximo.\n"
        f"{musica}"
        f"{alcool}"
        f"📝 <b>Título</b> ({tamanho} caracteres{curto}; toque para copiar):\n"
        f"<code>{html.escape(textos['titulo'])}</code>\n"
        f"{adicionar}\n"
        f"{_passo_do_nome(produtos, nomes or {})}\n"
        "4️⃣ <b>Depois de postar, comente</b> no vídeo (toque para copiar):\n"
        f"<code>{html.escape(textos['comentario'])}</code>"
        f"{postei}"
    )


# --- Envio ---

async def preparar_e_enviar(bot, admin_id, agora=None, fonte=FONTE_PADRAO, cobrindo=False):
    """
    Prepara o próximo vídeo e manda no privado. Devolve o que aconteceu, numa frase,
    para o log e para o botão Enviar 1 Agora. cobrindo=True: o robô está pausado sozinho, sem o
    celular, e o vídeo postado conta no plano do dia dele (P156 1).
    """
    for _ in range(VIDEOS_POR_ENVIO):
        video = proximo_video(fonte)
        if not video:
            registro_processos.registrar("shopee_video", "assistente: envio", "sem vídeo na fonte", ok=False)
            return f"não há vídeo em {FONTES.get(fonte, fonte)} para mandar (a fila está vazia ou sem arquivos)"
        try:
            with tempfile.TemporaryDirectory() as pasta:
                resultado = await _preparar_e_enviar(bot, admin_id, video, agora, fonte, pasta, cobrindo)
        except Exception as e:
            # Vídeo que dá erro (ex.: o Telegram recusa o arquivo) é pulado: sem isso, ele
            # voltaria em todo horário e travaria a fila.
            registrar(video["id"], "erro", type(e).__name__, agora)
            registro_processos.registrar("shopee_video", "assistente: envio", "erro", type(e).__name__, ok=False)
            raise
        # As frases do resultado são fixas (_preparar_e_enviar).
        registro_processos.registrar("shopee_video", "assistente: envio", resultado,
                                     ok=None if resultado in (SEM_PRODUTO_NO_LINK, SEM_BEBIDA, JA_POSTADO)
                                     else resultado == "postagem mandada no seu privado")
        if resultado not in (SEM_EDICAO, SEM_AVISOS, SEM_PRODUTO_NO_LINK, SEM_BEBIDA, JA_POSTADO):
            return resultado
    return (f"nenhum dos {VIDEOS_POR_ENVIO} próximos vídeos deu para mandar (só vai o vídeo editado e de produto que "
            "ainda não foi ao ar); tento de novo no próximo horário")


# O grupo dos amigos (amigos_shopee_video.py): cada vídeo vai a uma pessoa só, no grupo, em resposta ao pedido dela,
# e fica no mesmo registro dos vídeos mandados (nem o assistente nem o robô o pegam de novo). O produto que o amigo já
# recebeu não volta para ele: o vídeo fica na fonte para os outros, e o produto pode ir a outra pessoa (P271 2).
# Escolhas do Rafael (21 e 22/11, P271 2 a P277 1): DECISOES.md, Shopee Vídeo.
PROCESSO_DO_AMIGO = "grupo dos amigos: envio"
JA_RECEBIDO = "vídeo deixado para os outros: o amigo já recebeu este produto"
MANDADO_AO_AMIGO = "vídeo mandado no grupo dos amigos"
SEM_VIDEO_PARA_O_AMIGO = "sem vídeo na fonte para o amigo"
JA_COM_OUTRO = "vídeo de lado: o robô pegou este vídeo enquanto ele era preparado"
NENHUM_PARA_O_AMIGO = "nenhum dos próximos vídeos deu para mandar ao amigo"
# Os vídeos de produto que o amigo já recebeu que um pedido passa, antes de desistir: não gastam a IA nem a edição.
JA_RECEBIDOS_POR_PEDIDO = 30
# O que fica de lado pelo próprio vídeo: o próximo vai no lugar, no mesmo pedido. A IA sem resposta para o pedido
# (o próximo vídeo também ficaria sem o texto, e cada um que passa sai da fonte).
DE_LADO = (SEM_EDICAO, SEM_AVISOS, SEM_PRODUTO_NO_LINK, SEM_BEBIDA, VIOLACAO, JA_COM_OUTRO)


async def preparar_para_o_amigo(bot, admin_id, amigo, agora=None, fonte=FONTE_PADRAO):
    """
    Prepara o próximo vídeo da fonte para um amigo do grupo dos amigos e manda no grupo, como no privado do Rafael,
    sem o Postei ✅ (amigo: {"id", "mencao", "grupo", "responder_a"}: o id do Telegram, a menção em HTML, o grupo e a
    mensagem a que o vídeo responde). O vídeo recusado pelo Google e a violação continuam avisados no privado do
    Rafael (admin_id). Devolve a frase do que aconteceu.
    """
    pular, tentativas = set(), 0
    while tentativas < VIDEOS_POR_ENVIO and len(pular) < JA_RECEBIDOS_POR_PEDIDO:
        video = proximo_video(fonte, pular)
        if not video:
            registro_processos.registrar("shopee_video", PROCESSO_DO_AMIGO, SEM_VIDEO_PARA_O_AMIGO, ok=False)
            return SEM_VIDEO_PARA_O_AMIGO
        try:
            with tempfile.TemporaryDirectory() as pasta:
                resultado = await _preparar_e_enviar(bot, admin_id, video, agora, fonte, pasta, amigo=amigo)
        except Exception as e:
            registrar(video["id"], "erro", type(e).__name__, agora, amigo=amigo["id"])
            registro_processos.registrar("shopee_video", PROCESSO_DO_AMIGO, "erro", type(e).__name__, ok=False)
            raise
        if resultado == JA_RECEBIDO:
            pular.add(video["id"])
            continue
        tentativas += 1
        registro_processos.registrar("shopee_video", PROCESSO_DO_AMIGO, resultado,
                                     ok=None if resultado in (SEM_PRODUTO_NO_LINK, SEM_BEBIDA)
                                     else resultado == MANDADO_AO_AMIGO)
        if resultado not in DE_LADO:
            return resultado
    registro_processos.registrar("shopee_video", PROCESSO_DO_AMIGO, NENHUM_PARA_O_AMIGO, ok=False)
    return NENHUM_PARA_O_AMIGO


def _editar(video, produtos, destino, avisos=False):
    """
    O vídeo editado em destino, com o Editor 2 (ou o Editor 1, se ele não sai) e a foto do
    anúncio do produto do link; com avisos=True, a capa dos avisos da bebida alcoólica no
    lugar da foto. Anota no registro como saiu e devolve "" quando deu certo, ou o motivo
    fixo. O edicao_video importa este módulo: o import fica aqui dentro.
    """
    import edicao_video
    import postador_shopee_video as ps
    try:
        foto = ps.baixar_foto(produtos[0].get("imagem")) if produtos else None
    except Exception as e:
        logger.warning(f"⚠️ [Shopee Vídeo] A foto do anúncio não veio: {type(e).__name__}")
        foto = None
    produto = produtos[0] if produtos else {}
    motivo, como, detalhe = edicao_video.editar_para_postar(video["arquivo"], foto, destino, produto.get("nome", ""),
                                                            avisos=avisos)
    # Com o Editor 1 o vídeo vai, mas conta como falha: o checkup mostra por que o Editor 2 não saiu.
    so_com_o_editor_1 = como.startswith(edicao_video.SO_COM_O_EDITOR_1)
    registro_processos.registrar("shopee_video", "edição do vídeo: assistente", "vídeo de lado" if motivo else como,
                                 motivo or detalhe, ok=not motivo and not so_com_o_editor_1)
    return motivo


def _edicao_ligada(fonte):
    import edicao_video
    return edicao_video.vale_para(fonte)


async def _preparar_e_enviar(bot, admin_id, video, agora, fonte=FONTE_PADRAO, pasta=None, cobrindo=False, amigo=None):
    """
    Prepara o vídeo e manda no privado do Rafael (admin_id) ou, com amigo (preparar_para_o_amigo), no grupo dos
    amigos. Devolve a frase fixa do que aconteceu.
    """
    from aiogram.types import FSInputFile

    # O amigo de cada vídeo anotado no registro dos mandados (o "" é o Rafael).
    dono = str(amigo["id"]) if amigo else ""
    # Com a edição ligada, o vídeo que não sai editado fica de lado antes de gastar a IA.
    produtos, link = await produtos_do_link(video["link"])
    item = str(produtos[0].get("item") or "") if produtos else ""
    if amigo:
        # O produto que o amigo já recebeu fica para os outros: o vídeo não é anotado e continua na fonte (P271 2).
        if item and item in itens_do_amigo(dono):
            return JA_RECEBIDO
    elif item and item in produtos_ja_postados():
        # O produto já postado fica de lado antes da edição e da IA (P167 1).
        registrar(video["id"], "ja_postado", JA_POSTADO, agora, item=item)
        _anotar_onde_ja_foi(item)
        return JA_POSTADO
    arquivo = video["arquivo"]
    if pasta and _edicao_ligada(fonte):
        if not produtos:
            registrar(video["id"], "sem_edicao", SEM_PRODUTO_NO_LINK, agora, amigo=dono)
            return SEM_PRODUTO_NO_LINK
        arquivo = os.path.join(pasta, os.path.basename(video["arquivo"]))
        motivo = await asyncio.to_thread(_editar, video, produtos, arquivo)
        if motivo:
            registrar(video["id"], "sem_edicao", motivo, agora, amigo=dono)
            return SEM_EDICAO
    textos = await textos_do_video(video["arquivo"], video["nome"])
    if ULTIMA_RECUSA:
        # Escolha do Rafael (P29): cada vídeo recusado pelo Google chega no privado na hora.
        await bot.send_video(admin_id, video=FSInputFile(video["arquivo"]), supports_streaming=True,
                             caption=texto_da_recusa(ULTIMA_RECUSA, video["nome"])[:1000])
    if not textos or not textos["titulo"]:
        registrar(video["id"], "erro", "a IA não respondeu", agora, amigo=dono)
        return SEM_TEXTO_DA_IA
    if textos["violacao"]:
        registrar(video["id"], "violacao", textos["motivo"], agora, amigo=dono)
        await bot.send_message(admin_id, "⚠️ <b>Shopee Vídeo:</b> pulei um vídeo. A IA viu "
                               f"possível violação das diretrizes: {html.escape(textos['motivo'] or 'sem motivo')}",
                               parse_mode="HTML")
        return VIOLACAO
    # Bebida alcoólica em espera (P111): fica de lado, e vai o próximo vídeo.
    if bebida_em_espera(textos):
        registrar(video["id"], "bebida_em_espera", MOTIVO_BEBIDA_EM_ESPERA, agora, amigo=dono)
        return SEM_BEBIDA
    # Bebida alcoólica vai com os avisos da Shopee na capa: o vídeo editado é refeito com
    # eles; sem a edição, fica de lado. Escolha do Rafael (P43): DECISOES.md, Shopee Vídeo.
    if textos.get("bebida_alcoolica"):
        motivo = SEM_AVISOS
        if pasta and _edicao_ligada(fonte):
            motivo = await asyncio.to_thread(_editar, video, produtos, arquivo, True)
        if motivo:
            registrar(video["id"], "sem_edicao", motivo, agora, amigo=dono)
            return SEM_AVISOS
    # O vídeo que vai sem som ganha uma música da Shopee na hora de postar (escolha do Rafael,
    # P48). O editado já leva a música de fundo (P55); só o que vai sem a edição chega mudo.
    mudo = await asyncio.to_thread(videos.mudo, arquivo)
    # O nome de cada produto no vídeo, para o Rafael colar no Adicionar (P265 1).
    nomes = await nomes_no_video([p["nome"] for p in produtos]) if produtos else {}
    if amigo:
        if _ja_mandado(video["id"]):
            # O robô roda em outro processo e pode pegar o vídeo no meio do preparo: ele não vai a duas pessoas.
            return JA_COM_OUTRO
        await _mandar_ao_amigo(bot, amigo, arquivo, montar_mensagem(textos, produtos, link, mudo, nomes=nomes,
                                                                    amigo=amigo["mencao"]))
        registrar(video["id"], "enviado", "", agora, item=item, amigo=dono)
        return MANDADO_AO_AMIGO
    await bot.send_video(admin_id, video=FSInputFile(arquivo), supports_streaming=True,
                         caption="🎬 Vídeo para a Shopee Vídeo: siga os passos da mensagem abaixo.")
    await bot.send_message(admin_id, montar_mensagem(textos, produtos, link, mudo, cobrindo, nomes), parse_mode="HTML",
                           disable_web_page_preview=True, reply_markup=botao_postei(video["id"]))
    registrar(video["id"], "enviado", "", agora, cobrindo=cobrindo, item=item)
    return "postagem mandada no seu privado"


def _ja_mandado(id_unico):
    """Se o vídeo já está no registro dos mandados (de outra pessoa ou do robô)."""
    with db.conexao() as con:
        _criar_tabela(con)
        return con.execute("SELECT 1 FROM shopee_video_enviados WHERE id_unico = ?", (id_unico,)).fetchone() is not None


def _em_resposta_a(mensagem_id):
    """A resposta a uma mensagem do grupo que vai mesmo se a mensagem tiver sido apagada."""
    from aiogram.types import ReplyParameters
    return ReplyParameters(message_id=mensagem_id, allow_sending_without_reply=True) if mensagem_id else None


async def _mandar_ao_amigo(bot, amigo, arquivo, passos):
    """
    O vídeo no grupo dos amigos, em resposta à mensagem do pedido (P272 2), e os passos em resposta ao vídeo: com
    outros pedidos na fila, cada um fica junto do seu.
    """
    from aiogram.types import FSInputFile
    enviado = await bot.send_video(amigo["grupo"], video=FSInputFile(arquivo), supports_streaming=True,
                                   caption=f"🎬 {amigo['mencao']}, o seu vídeo para a Shopee Vídeo. Os passos vêm em "
                                           "resposta a ele, logo abaixo.", parse_mode="HTML",
                                   reply_parameters=_em_resposta_a(amigo.get("responder_a")))
    await bot.send_message(amigo["grupo"], passos, parse_mode="HTML", disable_web_page_preview=True,
                           reply_parameters=_em_resposta_a(getattr(enviado, "message_id", None)))

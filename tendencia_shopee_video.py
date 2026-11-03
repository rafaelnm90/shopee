"""
A medição da P135 (02/11/2026): por uma semana, o robô da Shopee Vídeo continua escolhendo os
vídeos como sempre (o mais novo da fonte, com a troca pelo mesmo item que paga mais por venda), e
uma vez por dia o bot_mestre anota aqui os sinais de tendência dos produtos dos vídeos mais novos
da fonte do robô, junto da comissão: as vendas do produto na API de afiliado (o total, para a
conta de quanto cresceu de um dia para o outro), a nota, a comissão e o preço (o valor por venda),
em quantos desses vídeos o produto está e em quantos canais diferentes o Espião o viu nos últimos
dias (o que está viralizando entre os afiliados). Depois dos 7 dias, o Claude compara com o que
vendeu (vendas.py) e leva os números ao Rafael, que decide se a escolha passa a ser por tendência e
comissão juntas. Nada aqui muda a escolha do robô.

Só ids e números no banco (tabelas shopee_video_tendencia e shopee_video_tendencia_links, por
DIAS_GUARDADOS dias); no registro, só contagens. Usado pelo bot_mestre (anotar, todo dia).
Escolha do Rafael (P135): DECISOES.md, Shopee Vídeo.
"""
import logging
import re
from datetime import datetime, timedelta

import aiohttp

import api_shopee
import assistente_shopee_video as assistente
import db
import pedidos_do_canal
import registro_processos
from fuso import fuso_horario

logger = logging.getLogger(__name__)

PROCESSO = "tendência dos vídeos da fonte"
# Os vídeos mais novos da fonte do robô: os que ele pegaria nos próximos dias.
VIDEOS_DA_FONTE = 30
# O Espião nestes últimos dias: em quantos canais diferentes o mesmo produto apareceu.
DIAS_DO_ESPIAO = 3
# Links novos seguidos numa vez (cada um é uma ida à Shopee); o resto fica para o dia seguinte.
LINKS_POR_VEZ = 100
DIAS_GUARDADOS = 14
PRODUTO = re.compile(r"/product/(\d+)/(\d+)")
# O que cada link é: o produto, o vídeo da Shopee Vídeo (os produtos ficam no Ver Produtos, que
# só o celular lê) ou outra página.
TIPOS = ("produto", "vídeo", "sem produto")


def _criar_tabelas(con):
    con.execute("CREATE TABLE IF NOT EXISTS shopee_video_tendencia_links ("
                "origem TEXT PRIMARY KEY, loja TEXT, item TEXT, tipo TEXT, visto_em TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS shopee_video_tendencia ("
                "dia TEXT, loja TEXT, item TEXT, vendas INTEGER, nota REAL, comissao REAL, preco REAL, "
                "videos INTEGER, canais INTEGER, PRIMARY KEY (dia, loja, item))")


async def _produto_do_link(link):
    """(loja, item, tipo) do produto para onde o link leva (TIPOS); loja e item vazios fora do produto."""
    destino = await api_shopee.link_para_converter(link)
    if api_shopee.eh_video(destino):
        return "", "", "vídeo"
    achado = PRODUTO.search(api_shopee.produto_do_link(destino) or "")
    if not achado:
        return "", "", "sem produto"
    return achado.group(1), achado.group(2), "produto"


async def _produtos(origens, momento):
    """
    {origem: (loja, item, tipo)} das origens [(origem, link)]: o que já foi seguido fica guardado;
    os novos, até LINKS_POR_VEZ, seguem o link. O link que não deu para seguir fica de fora e é
    seguido no dia seguinte.
    """
    with db.conexao() as con:
        _criar_tabelas(con)
        guardados = {linha[0]: tuple(linha[1:]) for linha in
                     con.execute("SELECT origem, loja, item, tipo FROM shopee_video_tendencia_links")}
    novos = [(origem, link) for origem, link in dict(origens).items() if origem not in guardados and link]
    achados = {}
    for origem, link in novos[:LINKS_POR_VEZ]:
        try:
            achados[origem] = await _produto_do_link(link)
        except Exception as e:
            logger.warning(f"⚠️ [Tendência] Um link não deu para seguir: {type(e).__name__}")
    if achados:
        with db.conexao() as con:
            _criar_tabelas(con)
            con.executemany("INSERT OR REPLACE INTO shopee_video_tendencia_links VALUES (?, ?, ?, ?, ?)",
                            [(origem, *dados, momento) for origem, dados in achados.items()])
    return {**guardados, **achados}


async def _oferta(loja, item):
    """{vendas, nota, comissao, preco} do produto pela API de afiliado, ou None sem a oferta ou sem resposta."""
    # Números direto na consulta: declarar a variável como Int64 dá "wrong type".
    consulta = (f"query {{ productOfferV2(shopId: {int(loja)}, itemId: {int(item)}, limit: 1) "
                "{ nodes { sales ratingStar commissionRate priceMin } } }")
    headers, corpo = api_shopee.gerar_headers_e_payload({"query": consulta})
    try:
        async with aiohttp.ClientSession() as sessao:
            async with sessao.post(assistente.URL_API, headers=headers, data=corpo) as resp:
                dados = await resp.json(content_type=None)
    except Exception as e:
        logger.warning(f"⚠️ [Tendência] A API de afiliado não respondeu: {type(e).__name__}")
        return None
    nos = (((dados or {}).get("data") or {}).get("productOfferV2") or {}).get("nodes") or []
    if not nos:
        return None
    no = nos[0]
    return {"vendas": int(assistente._numero(no.get("sales"))), "nota": assistente._numero(no.get("ratingStar")),
            "comissao": assistente._numero(no.get("commissionRate")), "preco": assistente._numero(no.get("priceMin"))}


def ja_anotou(agora=None):
    """O dia já tem a anotação? (o bot_mestre anota na subida o dia que ficou sem)"""
    dia = (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d")
    with db.conexao() as con:
        _criar_tabelas(con)
        return con.execute("SELECT 1 FROM shopee_video_tendencia WHERE dia = ? LIMIT 1", (dia,)).fetchone() is not None


async def anotar(agora=None):
    """
    A anotação do dia: os produtos dos VIDEOS_DA_FONTE vídeos mais novos da fonte do robô, cada um
    com as vendas, a nota, a comissão e o preço pela API, em quantos desses vídeos ele está e em
    quantos canais diferentes o Espião o viu nos últimos DIAS_DO_ESPIAO dias. Devolve o resumo,
    só números, que vai também ao registro.
    """
    try:
        resumo, ok = await _anotar(agora or datetime.now(fuso_horario))
    except Exception as e:
        logger.warning(f"⚠️ [Tendência] A anotação do dia não saiu: {type(e).__name__}")
        registro_processos.registrar("bot_mestre", PROCESSO, "falhou", type(e).__name__, ok=False)
        return f"falhou ({type(e).__name__})"
    registro_processos.registrar("bot_mestre", PROCESSO, "anotado" if ok else "sem vídeos na fonte", resumo,
                                 ok=True if ok else None)
    return resumo


async def _anotar(agora):
    dia, momento = agora.strftime("%Y-%m-%d"), agora.strftime("%Y-%m-%d %H:%M:%S")
    fonte = (db.ler_config("shopee_video", {}) or {}).get("fonte") or assistente.FONTE_PADRAO
    candidatos = assistente._candidatos(fonte if fonte in assistente.FONTES else assistente.FONTE_PADRAO)
    candidatos = [(origem, link) for origem, _arquivo, link, _legenda in candidatos if link][:VIDEOS_DA_FONTE]
    if not candidatos:
        return "0 vídeo(s) na fonte", False
    corte = (agora - timedelta(days=DIAS_DO_ESPIAO)).strftime("%Y-%m-%d %H:%M:%S")
    # O que o Espião trouxe do Canal Afiliados é nosso (os posts do robô e do Rafael): não conta
    # como outro canal. O id é o mesmo da fonte Viral do assistente, para o link ser seguido uma vez.
    espiao = [item for item in (db.ler_config("fila_clonagem", {"fila": []}) or {}).get("fila", [])
              if (item.get("data_captura") or "") >= corte and item.get("link_original")
              and str(item.get("chat_origem")) != pedidos_do_canal.CANAL]
    no_espiao = [(f"viral:{item.get('id')}", item.get("link_original"), str(item.get("chat_origem")))
                 for item in espiao]
    produtos = await _produtos(candidatos + [(origem, link) for origem, link, _canal in no_espiao], momento)

    videos, tipos = {}, dict.fromkeys(TIPOS + ("link não seguido",), 0)
    for origem, _link in candidatos:
        loja, item, tipo = produtos.get(origem, ("", "", "link não seguido"))
        tipos[tipo] = tipos.get(tipo, 0) + 1
        if tipo == "produto":
            videos[(loja, item)] = videos.get((loja, item), 0) + 1
    canais = {}
    for origem, _link, canal in no_espiao:
        loja, item, tipo = produtos.get(origem, ("", "", ""))
        if tipo == "produto":
            canais.setdefault((loja, item), set()).add(canal)

    linhas, sem_oferta = [], 0
    for (loja, item), quantos in videos.items():
        oferta = await _oferta(loja, item)
        if not oferta:
            sem_oferta += 1
            continue
        linhas.append((dia, loja, item, oferta["vendas"], oferta["nota"], oferta["comissao"], oferta["preco"],
                       quantos, len(canais.get((loja, item), ()))))
    velho = (agora - timedelta(days=DIAS_GUARDADOS)).strftime("%Y-%m-%d")
    with db.conexao() as con:
        _criar_tabelas(con)
        con.executemany("INSERT OR REPLACE INTO shopee_video_tendencia VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", linhas)
        con.execute("DELETE FROM shopee_video_tendencia WHERE dia < ?", (velho,))
        con.execute("DELETE FROM shopee_video_tendencia_links WHERE visto_em < ?", (velho,))
    vistos_no_espiao = sum(1 for chave in videos if canais.get(chave))
    return (f"{len(linhas)} produto(s) anotado(s) de {len(candidatos)} vídeo(s); {tipos['vídeo']} de vídeo; "
            f"{tipos['sem produto']} sem produto; {tipos['link não seguido']} link(s) não seguido(s); "
            f"{sem_oferta} sem oferta; {vistos_no_espiao} visto(s) também no Espião"), True

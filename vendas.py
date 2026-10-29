"""
O que vende: a comissão de afiliado separada por canal (a etiqueta, subId, que cada robô
põe nos links) e por produto. Pedido do Rafael (P13): DECISOES.md, Financeiro.

O bot_mestre puxa o relatório de vendas da API de afiliado de hora em hora (consulta de
conversoes) e guarda em cada pedido a etiqueta e os produtos (etiqueta_do_utm e
itens_do_pedido); toda segunda o relatório semanal (texto_semanal) chega no privado do
Rafael. Nomes de produto e valores ficam só no banco e no privado, nunca no log.
"""
from datetime import datetime, timedelta

# Os campos do relatório de vendas. A etiqueta (utmContent) e os produtos são o que diz
# de onde veio cada venda; sem eles (completa=False), o relatório de antes.
_CAMPOS_DO_PEDIDO = "orderId orderStatus"
_CAMPOS_COMPLETOS = ("orderId orderStatus items { itemId itemName itemPrice qty itemTotalCommission "
                     "channelType }")


def consulta_de_conversoes(completa=True):
    """A consulta GraphQL do relatório de conversões."""
    pedido = _CAMPOS_COMPLETOS if completa else _CAMPOS_DO_PEDIDO
    utm = "utmContent" if completa else ""
    return ("query getConversionReport($purchaseTimeStart: Int64!, $purchaseTimeEnd: Int64!, $limit: Int!) {"
            " conversionReport(purchaseTimeStart: $purchaseTimeStart, purchaseTimeEnd: $purchaseTimeEnd, "
            "limit: $limit) { nodes { purchaseTime shopeeCommissionCapped sellerCommission totalCommission "
            f"{utm} orders {{ {pedido} }} }} }} }}")


# O nome de cada etiqueta no relatório do Rafael (as etiquetas ficam no api_shopee).
NOMES_DOS_CANAIS = {
    "viral": "Viral (Espião)",
    "autorais": "Autorais",
    "espelhador": "Espelhador de canais",
    "achadinhos": "Achadinhos (garimpo de ofertas)",
    "busca": "Buscador do Grupo Público",
    "shopeevideo": "Shopee Vídeo (link aberto no celular do robô)",
    "canalafiliados": "Canal Afiliados (vídeos do robô da Shopee Vídeo)",
    "geral": "Links de antes das etiquetas",
    "": "Sem etiqueta (Shopee Vídeo e compras fora dos links dos robôs)",
}
# Pedido cancelado não conta na comissão.
CANCELADOS = ("CANCEL", "INVALID", "UNPAID")
PRODUTOS_NO_RELATORIO = 5


def etiqueta_do_utm(utm):
    """
    A etiqueta da venda: os subIds que vieram no utmContent ("achadinhos-casa----"),
    sem os vazios, juntos por "-". "" quando a venda não veio de um link com etiqueta.
    """
    return "-".join(parte for parte in str(utm or "").split("-") if parte.strip())


def canal(etiqueta):
    """O canal é a primeira etiqueta (a mais geral): "achadinhos-casa" → "achadinhos"."""
    return (etiqueta or "").split("-")[0]


def itens_do_pedido(pedido):
    """Os produtos de um pedido do relatório: nome, id, quantidade e comissão de cada um."""
    itens = []
    for item in pedido.get("items") or []:
        try:
            comissao = float(item.get("itemTotalCommission") or 0)
        except (TypeError, ValueError):
            comissao = 0.0
        itens.append({"id": str(item.get("itemId") or ""), "nome": str(item.get("itemName") or "")[:120],
                      "qtd": int(item.get("qty") or 1), "comissao": round(comissao, 2),
                      "tipo": str(item.get("channelType") or "")})
    return itens


def _vale(pedido):
    return not any(c in str(pedido.get("status") or "").upper() for c in CANCELADOS)


def resumo(pedidos, desde, ate=None):
    """
    Os pedidos de desde a ate (datas "AAAA-MM-DD"), sem os cancelados: por canal
    ({canal: {"pedidos", "comissao", "confirmada"}}) e os produtos que mais renderam
    [(nome, pedidos, comissao)]. Pedido de antes das etiquetas (sem o campo) fica fora
    dos canais e é contado à parte em "sem_dados".
    """
    canais, produtos, sem_dados = {}, {}, 0
    for p in pedidos.values():
        data = p.get("data") or ""
        if data < desde or (ate and data > ate) or not _vale(p):
            continue
        if "etiqueta" not in p:
            sem_dados += 1
            continue
        c = canais.setdefault(canal(p["etiqueta"]), {"pedidos": 0, "comissao": 0.0, "confirmada": 0.0})
        valor = float(p.get("comissao_total") or 0)
        c["pedidos"] += 1
        c["comissao"] += valor
        if str(p.get("status") or "").upper() == "COMPLETED":
            c["confirmada"] += valor
        for item in p.get("itens") or []:
            nome = item.get("nome") or item.get("id") or "?"
            atual = produtos.setdefault(nome, [0, 0.0])
            atual[0] += 1
            atual[1] += float(item.get("comissao") or 0)
    ranking = sorted(((nome, n, v) for nome, (n, v) in produtos.items()), key=lambda x: (-x[2], -x[1], x[0]))
    return {"canais": canais, "produtos": ranking, "sem_dados": sem_dados}


def vendas_dos_produtos_a_mais(pedidos, postados, desde, ate=None):
    """
    A medição dos produtos a mais da Shopee Vídeo (P73): dos vídeos de link de produto que o
    robô postou (postados: [(dia do post AAAA-MM-DD, [{item, a_mais}])], o itens_postados do
    robo_shopee_video), as vendas de desde a ate do produto do vídeo e dos produtos a mais
    (o mesmo item de outras lojas, P59), cada produto contado só a partir do dia do post dele.
    Sem os cancelados. {"do_video": [vendas, comissão], "a_mais": [vendas, comissão]}.
    Escolha do Rafael (29/10, P73): DECISOES.md, Shopee Vídeo.
    """
    # O item que entrou em mais de um post vale do primeiro post em diante, com o papel dele ali.
    inicio = {}
    for dia, itens in postados:
        for item in itens or []:
            numero = str(item.get("item") or "")
            if numero and (numero not in inicio or dia < inicio[numero][0]):
                inicio[numero] = (dia, bool(item.get("a_mais")))
    contas = {"do_video": [0, 0.0], "a_mais": [0, 0.0]}
    for p in pedidos.values():
        data = p.get("data") or ""
        if data < desde or (ate and data > ate) or not _vale(p):
            continue
        for item in p.get("itens") or []:
            achado = inicio.get(str(item.get("id") or ""))
            if achado and data >= achado[0]:
                conta = contas["a_mais" if achado[1] else "do_video"]
                conta[0] += int(item.get("qtd") or 1)
                conta[1] += float(item.get("comissao") or 0)
    return contas


def _reais(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def texto_semanal(pedidos, agora, postados=()):
    """
    O relatório da semana (os 7 dias antes de hoje) no privado do Rafael, em HTML. postados:
    os produtos dos vídeos do robô da Shopee Vídeo (vendas_dos_produtos_a_mais).
    """
    import html
    ate = (agora - timedelta(days=1)).strftime("%Y-%m-%d")
    desde = (agora - timedelta(days=7)).strftime("%Y-%m-%d")
    r = resumo(pedidos, desde, ate)
    a_mais = _linhas_dos_produtos_a_mais(pedidos, postados, desde, ate)
    titulo = (f"💰 <b>Vendas da semana por canal</b> ({datetime.strptime(desde, '%Y-%m-%d'):%d/%m} a "
              f"{datetime.strptime(ate, '%Y-%m-%d'):%d/%m})")
    if not r["canais"]:
        aviso = ("Ainda sem vendas com etiqueta nesta semana: as etiquetas começaram em 24/10, e os pedidos "
                 "aparecem aqui conforme a Shopee manda o relatório.")
        return f"{titulo}\n\n{aviso}" + "".join(f"\n{linha}" for linha in a_mais)
    linhas = [titulo, ""]
    total = sum(c["comissao"] for c in r["canais"].values())
    for nome, c in sorted(r["canais"].items(), key=lambda x: -x[1]["comissao"]):
        parte = f" ({c['comissao'] * 100 / total:.0f}%)" if total else ""
        linhas.append(f"• <b>{html.escape(NOMES_DOS_CANAIS.get(nome, nome))}</b>: {c['pedidos']} pedido(s), "
                      f"{_reais(c['comissao'])}{parte}; confirmada {_reais(c['confirmada'])}")
    linhas += ["", f"Total: <b>{_reais(total)}</b>"]
    if r["produtos"]:
        linhas += ["", "🏆 <b>Produtos que mais renderam</b>"]
        for nome, n, valor in r["produtos"][:PRODUTOS_NO_RELATORIO]:
            linhas.append(f"• {html.escape(nome[:70])}: {n} pedido(s), {_reais(valor)}")
    linhas += a_mais
    if r["sem_dados"]:
        linhas += ["", f"(+{r['sem_dados']} pedido(s) de antes das etiquetas, fora da conta por canal.)"]
    return "\n".join(linhas)


def _linhas_dos_produtos_a_mais(pedidos, postados, desde, ate):
    """As linhas da medição dos produtos a mais no relatório da semana; nenhuma sem vídeo com eles."""
    if not any(item.get("a_mais") for _dia, itens in postados for item in itens or []):
        return []
    contas = vendas_dos_produtos_a_mais(pedidos, postados, desde, ate)
    (n_video, v_video), (n_mais, v_mais) = contas["do_video"], contas["a_mais"]
    return ["", "🛍️ <b>Produtos a mais da Shopee Vídeo</b> (o mesmo item de outras lojas, nos vídeos do robô)",
            f"• Dos produtos a mais: {n_mais} venda(s), {_reais(v_mais)}",
            f"• Do produto do vídeo: {n_video} venda(s), {_reais(v_video)}"]

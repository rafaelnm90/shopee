"""
O que vende: a comissão de afiliado separada por canal (a etiqueta, subId, que cada robô
põe nos links) e por produto. Pedido do Rafael (P13): DECISOES.md, Financeiro.

O bot_mestre puxa o relatório de vendas da API de afiliado de hora em hora (consulta de
conversoes) e guarda em cada pedido a etiqueta e os produtos (etiqueta_do_utm e
itens_do_pedido); toda segunda o relatório semanal (texto_semanal) chega no privado do
Rafael. Nomes de produto e valores ficam só no banco e no privado, nunca no log.

Para o Claude (P13 e P135), o relatório privado (relatorio_privado, com a comparação da
tendência dos vídeos da fonte) sai só cifrado com a chave do registro_privado: "python3
vendas.py cifrado" no servidor, que o workflow vendas.yml grava no ramo vendas-cifradas.
"""
import sys
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


# O relatório privado (P13): os produtos que mais renderam e os dias da semana.
PRODUTOS_NO_RELATORIO_PRIVADO = 25
DIAS_DA_SEMANA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def _celula(texto):
    return ("" if texto is None else str(texto)).replace("|", "/").replace("\n", " ")


def _tabela(cabecalho, linhas):
    """Uma tabela em Markdown; sem linhas, só o aviso."""
    if not linhas:
        return ["(nenhum)"]
    return (["| " + " | ".join(cabecalho) + " |", "|" + "---|" * len(cabecalho)]
            + ["| " + " | ".join(_celula(c) for c in linha) + " |" for linha in linhas])


def _somar(grupos, chave, pedido):
    conta = grupos.setdefault(chave, {"pedidos": 0, "comissao": 0.0})
    conta["pedidos"] += 1
    conta["comissao"] += float(pedido.get("comissao_total") or 0)


def _ordenados(grupos):
    return sorted(grupos.items(), key=lambda x: (-x[1]["comissao"], -x[1]["pedidos"], str(x[0])))


def relatorio_privado(pedidos, agora):
    """
    As vendas para o Claude propor o que cada robô prioriza (P13), em Markdown: dos pedidos com
    etiqueta até ontem, sem os cancelados (contados à parte), a comissão por canal, por etiqueta,
    por semana, por dia da semana, por hora da compra (só os pedidos com a hora guardada) e por
    dia, e os produtos que mais renderam, com os canais de cada um. Tem nomes e valores: só sai
    cifrado (cifrado()).
    """
    ate = (agora - timedelta(days=1)).strftime("%Y-%m-%d")
    com_etiqueta = {sn: p for sn, p in pedidos.items() if "etiqueta" in p and (p.get("data") or "") <= ate}
    validos = {sn: p for sn, p in com_etiqueta.items() if _vale(p)}
    linhas = ["# Vendas por canal (P13)", "",
              f"Montado em {agora:%d/%m/%Y %H:%M}, com os pedidos que têm a etiqueta do link até {ate[8:10]}/{ate[5:7]} "
              f"(sem os de hoje). Pedidos de antes das etiquetas, fora da conta: "
              f"{sum(1 for p in pedidos.values() if 'etiqueta' not in p)}."]
    if not com_etiqueta:
        return "\n".join(linhas + ["", "Nenhum pedido com etiqueta ainda."]) + "\n"
    dias = sorted(p["data"] for p in com_etiqueta.values())
    total = sum(float(p.get("comissao_total") or 0) for p in validos.values())
    confirmada = sum(float(p.get("comissao_total") or 0) for p in validos.values()
                     if str(p.get("status") or "").upper() == "COMPLETED")
    cancelados = len(com_etiqueta) - len(validos)
    linhas += [f"De {dias[0][8:10]}/{dias[0][5:7]} a {dias[-1][8:10]}/{dias[-1][5:7]}: {len(validos)} pedido(s) "
               f"valendo, {_reais(total)} de comissão ({_reais(confirmada)} confirmada); {cancelados} cancelado(s) "
               "ou sem pagamento.", ""]

    canais, etiquetas, semanas, dias_da_semana, horas, por_dia = {}, {}, {}, {}, {}, {}
    cancelados_por_canal, confirmada_por_canal, canais_da_semana = {}, {}, {}
    for p in com_etiqueta.values():
        nome = canal(p["etiqueta"])
        if not _vale(p):
            cancelados_por_canal[nome] = cancelados_por_canal.get(nome, 0) + 1
            por_dia.setdefault(p["data"], {"pedidos": 0, "comissao": 0.0, "cancelados": 0})["cancelados"] += 1
            continue
        data = datetime.strptime(p["data"], "%Y-%m-%d")
        valor = float(p.get("comissao_total") or 0)
        _somar(canais, nome, p)
        _somar(etiquetas, p["etiqueta"] or "(sem etiqueta)", p)
        semana = (data - timedelta(days=data.weekday())).strftime("%Y-%m-%d")
        _somar(semanas, semana, p)
        canais_da_semana.setdefault(semana, {}).setdefault(nome, 0.0)
        canais_da_semana[semana][nome] += valor
        _somar(dias_da_semana, data.weekday(), p)
        if p.get("hora"):
            _somar(horas, int(str(p["hora"])[:2]), p)
        dia = por_dia.setdefault(p["data"], {"pedidos": 0, "comissao": 0.0, "cancelados": 0})
        dia["pedidos"] += 1
        dia["comissao"] += valor
        if str(p.get("status") or "").upper() == "COMPLETED":
            confirmada_por_canal[nome] = confirmada_por_canal.get(nome, 0.0) + valor

    linhas += ["## Por canal (a 1ª etiqueta)", ""] + _tabela(
        ("canal", "pedidos", "comissão", "% da comissão", "confirmada", "cancelados"),
        [(NOMES_DOS_CANAIS.get(nome, nome), c["pedidos"], _reais(c["comissao"]),
          f"{c['comissao'] * 100 / total:.0f}%" if total else "-", _reais(confirmada_por_canal.get(nome, 0.0)),
          cancelados_por_canal.get(nome, 0)) for nome, c in _ordenados(canais)]
        + [(NOMES_DOS_CANAIS.get(nome, nome), 0, _reais(0), "0%", _reais(0), n)
           for nome, n in sorted(cancelados_por_canal.items()) if nome not in canais])
    linhas += ["", "## Por etiqueta completa", ""] + _tabela(
        ("etiqueta", "pedidos", "comissão"), [(nome, c["pedidos"], _reais(c["comissao"]))
                                               for nome, c in _ordenados(etiquetas)])
    linhas += ["", "## Por semana (de segunda)", ""] + _tabela(
        ("semana", "pedidos", "comissão", "por canal"),
        [(f"{semana[8:10]}/{semana[5:7]}", c["pedidos"], _reais(c["comissao"]),
          ", ".join(f"{NOMES_DOS_CANAIS.get(nome, nome)} {_reais(valor)}" for nome, valor in
                    sorted(canais_da_semana[semana].items(), key=lambda x: -x[1])))
         for semana, c in sorted(semanas.items())])
    linhas += ["", "## Por dia da semana (do pedido)", ""] + _tabela(
        ("dia", "pedidos", "comissão"),
        [(DIAS_DA_SEMANA[d], dias_da_semana[d]["pedidos"], _reais(dias_da_semana[d]["comissao"]))
         for d in sorted(dias_da_semana)])
    com_hora = sum(c["pedidos"] for c in horas.values())
    linhas += ["", f"## Por hora da compra ({com_hora} de {len(validos)} pedido(s) com a hora guardada)", ""]
    linhas += _tabela(("hora", "pedidos", "comissão"),
                      [(f"{h:02d}h", horas[h]["pedidos"], _reais(horas[h]["comissao"])) for h in sorted(horas)])

    produtos = {}
    for p in validos.values():
        for item in p.get("itens") or []:
            nome = (item.get("nome") or item.get("id") or "?")[:80]
            conta = produtos.setdefault(nome, {"pedidos": 0, "qtd": 0, "comissao": 0.0, "canais": set()})
            conta["pedidos"] += 1
            conta["qtd"] += int(item.get("qtd") or 1)
            conta["comissao"] += float(item.get("comissao") or 0)
            conta["canais"].add(NOMES_DOS_CANAIS.get(canal(p["etiqueta"]), canal(p["etiqueta"])))
    mais = sorted(produtos.items(), key=lambda x: (-x[1]["comissao"], -x[1]["pedidos"], x[0]))
    linhas += ["", f"## Produtos que mais renderam ({min(len(mais), PRODUTOS_NO_RELATORIO_PRIVADO)} de {len(mais)})",
               ""] + _tabela(("produto", "pedidos", "unidades", "comissão", "canais"),
                             [(nome, c["pedidos"], c["qtd"], _reais(c["comissao"]), ", ".join(sorted(c["canais"])))
                              for nome, c in mais[:PRODUTOS_NO_RELATORIO_PRIVADO]])
    linhas += ["", "## Por dia", ""] + _tabela(
        ("dia", "pedidos", "comissão", "cancelados"),
        [(f"{dia[8:10]}/{dia[5:7]}", c["pedidos"], _reais(c["comissao"]), c["cancelados"])
         for dia, c in sorted(por_dia.items())])
    return "\n".join(linhas) + "\n"


def cifrado():
    """
    O relatório privado (as vendas e a comparação da tendência da P135), cifrado com a chave do
    registro_privado, a que o Claude tem no ambiente. Só o texto cifrado sai do servidor.
    """
    from cryptography.fernet import Fernet

    import db
    import registro_privado
    import tendencia_shopee_video
    from fuso import fuso_horario
    pedidos = db.ler_config("banco_pedidos", {}) or {}
    agora = datetime.now(fuso_horario)
    texto = relatorio_privado(pedidos, agora) + "\n" + tendencia_shopee_video.comparacao(pedidos)
    return Fernet(registro_privado.chave()).encrypt(texto.encode("utf-8")).decode("ascii")


if __name__ == "__main__":
    if sys.argv[1:2] == ["cifrado"]:
        print(cifrado())
    else:
        print("Uso: vendas.py cifrado (o relatório privado, cifrado; para ler: registro_privado.py ler ARQUIVO)")
        sys.exit(2)

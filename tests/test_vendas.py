"""vendas.py e a etiqueta de cada robô nos links: a comissão por canal e por produto."""
import json
from datetime import datetime

import api_shopee
import vendas
from conftest import rodar
from fuso import fuso_horario

AGORA = datetime(2026, 11, 2, 9, 13, tzinfo=fuso_horario)   # segunda


def test_etiquetas_limpas_ate_5_e_juntas_no_registro():
    assert api_shopee.etiquetas("viral") == ["viral"]
    assert api_shopee.etiquetas(["achadinhos", "Casa & Cozinha", "", "a", "b", "c", "d"]) == \
        ["achadinhos", "CasaCozinha", "a", "b", "c"]
    assert api_shopee.etiquetas(None) == ["geral"]


def test_link_sai_com_as_etiquetas_pedidas(monkeypatch):
    pedidos = []

    class Resposta:
        status = 200

        async def json(self):
            return {"data": {"generateShortLink": {"shortLink": "https://s.shopee.com.br/x"}}}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class Sessao:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def post(self, url, headers=None, data=None):
            pedidos.append(json.loads(data)["variables"]["subIds"])
            return Resposta()

    async def mesmo(link):
        return link

    monkeypatch.setattr(api_shopee.aiohttp, "ClientSession", Sessao)
    monkeypatch.setattr(api_shopee, "link_para_converter", mesmo)
    monkeypatch.setattr(api_shopee, "SHOPEE_APP_ID", "1")
    monkeypatch.setattr(api_shopee, "SHOPEE_APP_SECRET", "2")
    rodar(api_shopee.converter_link_shopee("https://shopee.com.br/p-i.1.2", [api_shopee.ETIQUETA_ACHADINHOS, "casa"]))
    rodar(api_shopee.converter_link_shopee("https://shopee.com.br/p-i.1.2", api_shopee.ETIQUETA_VIRAL))
    assert pedidos == [["achadinhos", "casa"], ["viral"]]


def test_etiqueta_e_produtos_do_relatorio():
    assert vendas.etiqueta_do_utm("achadinhos-casa---") == "achadinhos-casa"
    assert vendas.etiqueta_do_utm("") == "" and vendas.etiqueta_do_utm(None) == ""
    assert vendas.canal("achadinhos-casa") == "achadinhos"
    itens = vendas.itens_do_pedido({"items": [{"itemId": 9, "itemName": "Copo Térmico", "qty": 2,
                                               "itemTotalCommission": "3.5", "channelType": "x"}]})
    assert itens == [{"id": "9", "nome": "Copo Térmico", "qtd": 2, "comissao": 3.5, "tipo": "x"}]
    consulta = vendas.consulta_de_conversoes()
    assert "utmContent" in consulta and "itemName" in consulta and consulta.count("{") == consulta.count("}")
    antiga = vendas.consulta_de_conversoes(completa=False)
    assert "utmContent" not in antiga and antiga.count("{") == antiga.count("}")


def test_relatorio_semanal_por_canal_e_produto_sem_os_cancelados():
    pedidos = {
        "1": {"data": "2026-10-27", "status": "COMPLETED", "comissao_total": 4.0, "etiqueta": "viral",
              "itens": [{"nome": "Copo Térmico", "comissao": 4.0}]},
        "2": {"data": "2026-10-28", "status": "PENDING", "comissao_total": 2.0, "etiqueta": "achadinhos-casa",
              "itens": [{"nome": "Panela", "comissao": 2.0}]},
        "3": {"data": "2026-10-29", "status": "CANCELLED", "comissao_total": 9.0, "etiqueta": "viral", "itens": []},
        "4": {"data": "2026-10-29", "status": "PENDING", "comissao_total": 1.0, "etiqueta": "", "itens": []},
        "5": {"data": "2026-10-30", "status": "COMPLETED", "comissao_total": 5.0},      # de antes das etiquetas
        "6": {"data": "2026-11-02", "status": "COMPLETED", "comissao_total": 7.0, "etiqueta": "viral"},  # hoje
    }
    r = vendas.resumo(pedidos, "2026-10-26", "2026-11-01")
    assert r["canais"] == {"viral": {"pedidos": 1, "comissao": 4.0, "confirmada": 4.0},
                           "achadinhos": {"pedidos": 1, "comissao": 2.0, "confirmada": 0.0},
                           "": {"pedidos": 1, "comissao": 1.0, "confirmada": 0.0}}
    assert r["produtos"][0] == ("Copo Térmico", 1, 4.0) and r["sem_dados"] == 1
    texto = vendas.texto_semanal(pedidos, AGORA)
    assert "26/10 a 01/11" in texto and "Viral (Espião)" in texto and "R$ 4,00 (57%)" in texto
    assert "Total: <b>R$ 7,00</b>" in texto and "Copo Térmico" in texto and "+1 pedido(s) de antes" in texto
    assert "ainda sem vendas" in vendas.texto_semanal({}, AGORA).casefold()


def test_pedido_novo_guarda_a_etiqueta_e_os_produtos(bm):
    conversoes = [{"purchaseTime": 1761300000, "totalCommission": "4", "shopeeCommissionCapped": "3",
                   "sellerCommission": "1", "utmContent": "viral----",
                   "orders": [{"orderId": "A1", "orderStatus": "PENDING",
                               "items": [{"itemId": 5, "itemName": "Copo", "qty": 1, "itemTotalCommission": "4"}]}]}]
    bm.processar_e_salvar_pedidos_api(conversoes)
    pedido = bm.ler_banco_pedidos()["A1"]
    assert pedido["etiqueta"] == "viral" and pedido["itens"][0]["nome"] == "Copo"
    # O relatório antigo (sem utmContent) não apaga a etiqueta já guardada.
    sem = [dict(conversoes[0], orders=[{"orderId": "A1", "orderStatus": "COMPLETED"}])]
    del sem[0]["utmContent"]
    bm.processar_e_salvar_pedidos_api(sem)
    pedido = bm.ler_banco_pedidos()["A1"]
    assert pedido["etiqueta"] == "viral" and pedido["status"] == "COMPLETED"


def test_relatorio_recusado_volta_ao_de_antes_sem_parar_o_financeiro(bm, monkeypatch):
    consultas = []

    class Resposta:
        status = 200

        def __init__(self, corpo):
            self.corpo = corpo

        async def text(self):
            return json.dumps(self.corpo)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class Sessao:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def post(self, url, headers=None, data=None):
            consulta = json.loads(data)["query"]
            consultas.append("utmContent" in consulta)
            if "utmContent" in consulta:
                return Resposta({"errors": [{"message": "Cannot query field utmContent"}]})
            return Resposta({"data": {"conversionReport": {"nodes": [{"purchaseTime": 1, "orders": []}]}}})

    async def sem_espera(s):
        return None

    monkeypatch.setattr(bm, "SHOPEE_APP_ID", "1")
    monkeypatch.setattr(bm, "SHOPEE_APP_SECRET", "2")
    monkeypatch.setattr(bm.aiohttp, "ClientSession", Sessao)
    monkeypatch.setattr(bm.asyncio, "sleep", sem_espera)
    monkeypatch.setattr(bm, "_relatorio_completo", True)
    nos = rodar(bm.buscar_dados_financeiros_shopee(3))
    assert consultas == [True, False] and len(nos) == 1


def _pedido(data, *itens, status="COMPLETED"):
    return {"data": data, "status": status, "etiqueta": "", "comissao_total": 0,
            "itens": [{"id": item, "nome": "Produto", "qtd": 1, "comissao": comissao} for item, comissao in itens]}


def test_vendas_dos_produtos_a_mais_contam_do_dia_do_post_em_diante():
    # A medição da P73: as vendas do produto do vídeo e dos produtos a mais (o mesmo item de
    # outras lojas), cada um só a partir do dia do post dele, sem os cancelados.
    postados = [("2026-10-30", [{"item": "1", "a_mais": False}, {"item": "2", "a_mais": True}]),
                ("2026-10-31", [{"item": "3", "a_mais": False}, {"item": "2", "a_mais": True}])]
    pedidos = {"a": _pedido("2026-10-29", ("2", 5.0)),            # antes do post: não conta
               "b": _pedido("2026-10-30", ("1", 2.0)),
               "c": _pedido("2026-10-31", ("2", 3.0), ("9", 7.0)),  # o 9 não é de vídeo do robô
               "d": _pedido("2026-11-01", ("2", 4.0), status="CANCELLED"),
               "e": _pedido("2026-11-01", ("3", 1.5))}
    contas = vendas.vendas_dos_produtos_a_mais(pedidos, postados, "2026-10-29")
    assert contas == {"do_video": [2, 3.5], "a_mais": [1, 3.0]}
    assert vendas.vendas_dos_produtos_a_mais(pedidos, postados, "2026-10-29", "2026-10-30") == \
        {"do_video": [1, 2.0], "a_mais": [0, 0.0]}


def test_relatorio_da_semana_mostra_os_produtos_a_mais_so_quando_ha():
    pedidos = {"b": dict(_pedido("2026-10-30", ("1", 2.0)), comissao_total=2.0, etiqueta="canalafiliados"),
               "c": dict(_pedido("2026-10-31", ("2", 3.0)), comissao_total=3.0)}
    com = [("2026-10-30", [{"item": "1", "a_mais": False}, {"item": "2", "a_mais": True}])]
    texto = vendas.texto_semanal(pedidos, AGORA, com)
    assert "Produtos a mais da Shopee Vídeo" in texto
    assert "Dos produtos a mais: 1 venda(s), R$ 3,00" in texto and "Do produto do vídeo: 1 venda(s), R$ 2,00" in texto
    sem = [("2026-10-30", [{"item": "1", "a_mais": False}])]
    assert "Produtos a mais" not in vendas.texto_semanal(pedidos, AGORA, sem)
    assert "Produtos a mais" not in vendas.texto_semanal(pedidos, AGORA)

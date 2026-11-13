"""vendas.py e a etiqueta de cada robô nos links: a comissão por canal e por produto."""
import json
import string
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


def test_relatorio_privado_por_canal_etiqueta_semana_dia_hora_e_produto():
    # P13: o Claude propõe o que cada robô prioriza com a comissão por canal, etiqueta, semana,
    # dia da semana, hora e produto, desde as etiquetas e até ontem, sem os cancelados (contados
    # à parte). O relatório tem nomes e valores: só sai cifrado.
    pedidos = {
        "1": {"data": "2026-10-27", "hora": "20:15", "status": "COMPLETED", "comissao_total": 4.0, "etiqueta": "viral",
              "itens": [{"id": "9", "nome": "Copo Térmico", "qtd": 2, "comissao": 4.0}]},
        "2": {"data": "2026-10-28", "status": "PENDING", "comissao_total": 2.0, "etiqueta": "achadinhos-casa",
              "itens": [{"id": "8", "nome": "Panela", "qtd": 1, "comissao": 2.0}]},
        "3": {"data": "2026-10-29", "status": "CANCELLED", "comissao_total": 9.0, "etiqueta": "viral", "itens": []},
        "4": {"data": "2026-11-01", "hora": "20:50", "status": "PENDING", "comissao_total": 1.0, "etiqueta": "viral",
              "itens": [{"id": "9", "nome": "Copo Térmico", "qtd": 1, "comissao": 1.0}]},
        "5": {"data": "2026-10-30", "status": "COMPLETED", "comissao_total": 5.0},      # de antes das etiquetas
        "6": {"data": "2026-11-02", "status": "COMPLETED", "comissao_total": 7.0, "etiqueta": "viral"},  # hoje
    }
    texto = vendas.relatorio_privado(pedidos, AGORA)
    assert "até 01/11 (sem os de hoje). Pedidos de antes das etiquetas, fora da conta: 1." in texto
    assert "De 27/10 a 01/11: 3 pedido(s) valendo, R$ 7,00 de comissão (R$ 4,00 confirmada); 1 cancelado(s)" in texto
    assert "| Viral (Espião) | 2 | R$ 5,00 | 71% | R$ 4,00 | 1 |" in texto
    assert "| Achadinhos (garimpo de ofertas) | 1 | R$ 2,00 | 29% | R$ 0,00 | 0 |" in texto
    assert "| achadinhos-casa | 1 | R$ 2,00 |" in texto
    assert "| 26/10 | 3 | R$ 7,00 | Viral (Espião) R$ 5,00, Achadinhos (garimpo de ofertas) R$ 2,00 |" in texto
    assert "| terça | 1 | R$ 4,00 |" in texto and "| domingo | 1 | R$ 1,00 |" in texto
    assert "## Por hora da compra (2 de 3 pedido(s) com a hora guardada)" in texto and "| 20h | 2 | R$ 5,00 |" in texto
    assert "| Copo Térmico | 2 | 3 | R$ 5,00 | Viral (Espião) |" in texto
    assert "| 29/10 | 0 | R$ 0,00 | 1 |" in texto
    assert "Nenhum pedido com etiqueta ainda." in vendas.relatorio_privado({}, AGORA)


def test_relatorio_privado_separa_as_vendas_pela_origem_que_a_shopee_informa():
    # P223 (13/11): para saber se o que vende vem da Shopee Vídeo e de quais produtos, o relatório
    # privado soma cada produto vendido pela origem (o channelType de cada item), sem os cancelados; o
    # pedido guardado antes de o bot ler o campo fica como não informada.
    pedidos = {
        "1": {"data": "2026-10-27", "status": "COMPLETED", "comissao_total": 6.0, "etiqueta": "",
              "itens": [{"id": "1", "nome": "Copo Térmico", "qtd": 2, "comissao": 4.0, "tipo": "Shopee Video"},
                        {"id": "2", "nome": "Panela", "qtd": 1, "comissao": 2.0, "tipo": "Social Media"}]},
        "2": {"data": "2026-10-28", "status": "PENDING", "comissao_total": 3.0, "etiqueta": "viral",
              "itens": [{"id": "3", "nome": "Garrafa", "qtd": 1, "comissao": 3.0, "tipo": "Shopee Video"}]},
        "3": {"data": "2026-10-29", "status": "CANCELLED", "comissao_total": 9.0, "etiqueta": "",
              "itens": [{"id": "1", "nome": "Copo Térmico", "qtd": 1, "comissao": 9.0, "tipo": "Shopee Video"}]},
        "4": {"data": "2026-10-30", "status": "COMPLETED", "comissao_total": 1.0, "etiqueta": "",
              "itens": [{"id": "4", "nome": "Toalha", "qtd": 1, "comissao": 1.0}]},
    }
    texto = vendas.relatorio_privado(pedidos, AGORA)
    assert "## Por origem da venda (o tipo de canal que a Shopee informa em cada produto)" in texto
    assert "| Shopee Video | 3 | R$ 7,00 | Copo Térmico R$ 4,00; Garrafa R$ 3,00 |" in texto
    assert "| Social Media | 1 | R$ 2,00 | Panela R$ 2,00 |" in texto
    assert f"| {vendas.SEM_ORIGEM} | 1 | R$ 1,00 | Toalha R$ 1,00 |" in texto
    assert texto.index("| Shopee Video |") < texto.index("| Social Media |") < texto.index(f"| {vendas.SEM_ORIGEM} |")


def test_pedido_guarda_a_hora_da_compra(bm):
    # P13: a conta por hora precisa da hora da compra, que a API manda (purchaseTime). O pedido
    # novo a guarda, e o que já estava no banco sem ela ganha a hora quando a Shopee o manda de novo.
    quando = int(datetime(2026, 11, 3, 21, 7, tzinfo=fuso_horario).timestamp())
    conversoes = [{"purchaseTime": quando, "totalCommission": "4", "shopeeCommissionCapped": "3",
                   "sellerCommission": "1", "utmContent": "viral----",
                   "orders": [{"orderId": "H1", "orderStatus": "PENDING", "items": []}]}]
    bm.processar_e_salvar_pedidos_api(conversoes)
    assert bm.ler_banco_pedidos()["H1"]["hora"] == "21:07"
    banco = bm.ler_banco_pedidos()
    del banco["H1"]["hora"]
    bm.salvar_banco_pedidos(banco)
    bm.processar_e_salvar_pedidos_api(conversoes)
    assert bm.ler_banco_pedidos()["H1"]["hora"] == "21:07"


def test_relatorio_cifrado_so_abre_com_a_chave_do_registro_privado(monkeypatch, tmp_path):
    # O relatório privado sai do servidor só cifrado (vendas.yml), com a chave que o Claude tem.
    import db
    import registro_privado
    from conftest import inserir
    monkeypatch.setattr(registro_privado, "CHAVE_ARQUIVO", str(tmp_path / "chave"))
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    db.salvar_config("banco_pedidos", {"1": {"data": "2026-10-27", "status": "COMPLETED", "comissao_total": 4.0,
                                             "etiqueta": "viral", "itens": [{"nome": "Copo Térmico", "comissao": 4.0}]}})
    texto = vendas.cifrado()
    # O cifrado tem só as letras do base64, sorteadas a cada vez: um pedaço curto do nome pode aparecer
    # nele por acaso. O nome inteiro, com o espaço e o acento que o base64 não tem, nunca.
    assert texto.startswith("gAAAAA") and set(texto) <= set(string.ascii_letters + string.digits + "-_=")
    assert "Copo Térmico" not in texto
    aberto = registro_privado.abrir(texto, registro_privado.chave().decode("ascii"))
    assert "# Vendas por canal (P13)" in aberto and "Copo Térmico" in aberto
    assert "# Tendência dos vídeos da fonte (P135)" in aberto

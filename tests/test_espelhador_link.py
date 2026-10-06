"""Espelhador: o link de afiliado é gerado de novo na hora de postar, não fica o da captura."""
import motor_userbot as mu
from conftest import rodar

ORIGINAL = "https://s.shopee.com.br/original_do_grupo"
GUARDADO = "https://s.shopee.com.br/convertido_na_captura"
NOVO = "https://s.shopee.com.br/convertido_no_disparo"


def _conversor(monkeypatch, resposta=None):
    pedidos = []

    async def converter(link, sub_id="geral", **k):
        pedidos.append((link, sub_id, k.get("avisar_falha")))
        return resposta if resposta is not None else NOVO

    monkeypatch.setattr(mu, "converter_link_shopee", converter)
    return pedidos


def test_disparo_gera_o_link_de_novo_a_partir_do_original(monkeypatch):
    # Vídeo do Rafael de 06/10: posts do Espelhador abriam a busca porque o link da fila
    # tinha sido convertido antes do conserto do link de produto.
    pedidos = _conversor(monkeypatch)
    item = {"link_original": ORIGINAL, "link_convertido": GUARDADO,
            "texto_processado": f"<b>Mochila</b>\n\n🔗 <b>Link do Produto:</b>\n{GUARDADO}"}
    texto = rodar(mu.renovar_link_no_disparo(item, item["texto_processado"]))
    assert pedidos == [(ORIGINAL, "geral", False)]
    assert NOVO in texto and GUARDADO not in texto
    assert item["link_convertido"] == NOVO and NOVO in item["texto_processado"]


def test_item_antigo_sem_original_reconverte_o_link_guardado(monkeypatch):
    pedidos = _conversor(monkeypatch)
    item = {"link_convertido": GUARDADO, "texto_processado": f"🔗 <b>Link do Produto:</b>\n{GUARDADO}"}
    texto = rodar(mu.renovar_link_no_disparo(item, item["texto_processado"]))
    assert pedidos[0][0] == GUARDADO and NOVO in texto


def test_api_fora_fica_o_link_da_captura(monkeypatch):
    _conversor(monkeypatch, resposta=ORIGINAL)                 # a API falhou: devolve o que recebeu
    item = {"link_original": ORIGINAL, "link_convertido": GUARDADO,
            "texto_processado": f"🔗 <b>Link do Produto:</b>\n{GUARDADO}"}
    texto = rodar(mu.renovar_link_no_disparo(item, item["texto_processado"]))
    assert GUARDADO in texto and ORIGINAL not in texto and item["link_convertido"] == GUARDADO


def test_disparo_renova_o_link_antes_da_legenda_da_ia():
    # A legenda da IA usa item["link_convertido"]: o link tem de ser renovado antes dela.
    import inspect
    fonte = inspect.getsource(mu)
    assert fonte.index("texto = await renovar_link_no_disparo(item, texto)") < \
        fonte.index("texto = await montar_legenda_no_disparo(")
    assert '"link_original": link_capturado' in fonte                       # a captura guarda o original

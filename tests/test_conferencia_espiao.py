"""conferencia_espiao.py: o nome que a IA do Espião deu confere com o produto do link?"""
import conferencia_espiao as ce
import registro_processos as rp
from conftest import consultar, rodar


def test_palavra_de_verdade_em_comum_confere():
    assert ce.confere("Garrafa Térmica 🧴", ["Garrafa Termica Inox 1L com Tampa"])
    assert ce.confere("Fone Bluetooth 🎧", ["Kit Fone de Ouvido Bluetooth TWS"])
    assert not ce.confere("Vestido Floral 👗", ["Kit 3 Panelas Antiaderentes"])
    # Palavra vazia ("kit", "para") ou curta não conta como produto em comum.
    assert not ce.confere("Kit para Casa", ["Kit para Carro Aspirador"])


def test_anota_o_resultado_no_registro(monkeypatch):
    respostas = iter([
        ([{"nome": "Garrafa Termica Inox"}], "x"),
        ([{"nome": "Panela de Pressao"}], "x"),
        ([], "x"),
    ])

    async def produtos(link):
        return next(respostas)

    monkeypatch.setattr(ce.assistente_shopee_video, "produtos_do_link", produtos)
    for _ in range(3):
        rodar(ce.anotar("Garrafa Térmica 🧴", "https://s.shopee.com.br/abc"))

    async def quebrada(link):
        raise TimeoutError("api")
    monkeypatch.setattr(ce.assistente_shopee_video, "produtos_do_link", quebrada)
    rodar(ce.anotar("Garrafa", "https://s.shopee.com.br/abc"))

    linhas = {(r[2], r[3], r[4]) for r in rp.contagem("2000-01-01 00:00:00")}
    assert linhas == {("confere", "", 1), ("não confere", "", 0), ("sem produto na API", "", None),
                      ("API não respondeu", "TimeoutError", None)}
    assert consultar("SELECT COUNT(*) FROM registro_processos WHERE detalhe LIKE '%Garrafa%'")[0] == 0

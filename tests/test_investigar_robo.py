"""investigar_robo: por que o robô não acha o produto, só com tipos de página e contagens (o log é público)."""

import investigar_robo as ir
from conftest import inserir, rodar

LINK = "https://s.shopee.com.br/abc"
PRODUTO = "https://shopee.com.br/Copo-Termico-i.123.456"


def _rede(monkeypatch, destino, oferta=True):
    async def seguir_link(link, saltos=10):
        return [link, destino]

    async def link_para_converter(link):
        return destino

    async def consultar(loja, item):
        return {"nome": "Copo Térmico", "preco": 10.0, "comissao": 5.0} if oferta else None

    monkeypatch.setattr(ir.api_shopee, "seguir_link", seguir_link)
    monkeypatch.setattr(ir.api_shopee, "link_para_converter", link_para_converter)
    monkeypatch.setattr(ir.assistente, "_consultar_produto", consultar)


def test_classifica_produto_com_e_sem_oferta(monkeypatch):
    _rede(monkeypatch, PRODUTO)
    assert rodar(ir.classificar(LINK)) == ("produto com oferta na API de afiliado", ["link curto", "produto"])
    _rede(monkeypatch, PRODUTO, oferta=False)
    assert rodar(ir.classificar(LINK))[0] == "produto SEM oferta na API de afiliado"


def test_classifica_link_de_video_e_pagina_sem_produto(monkeypatch):
    _rede(monkeypatch, "https://sv.shopee.com.br/share-video/AAAA")
    assert rodar(ir.classificar(LINK))[0] == "link de vídeo (Ver Produtos)"
    _rede(monkeypatch, "https://shopee.com.br/search?keyword=copo")
    assert rodar(ir.classificar(LINK))[0] == "não chega a um produto (parou em: busca)"


def test_relatorio_nunca_mostra_link_nome_ou_motivo(monkeypatch, capsys):
    _rede(monkeypatch, PRODUTO, oferta=False)
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    ir.db.salvar_config("fila_clonagem", {"fila": [
        {"id": 1, "caminho_video": "archive/a.mp4", "link_original": LINK, "data_captura": "2026-10-23 05:00"}]})
    ir.db.salvar_config("shopee_video", {"fonte": "viral"})
    inserir("CREATE TABLE shopee_video_rascunhos (id INTEGER PRIMARY KEY, id_video TEXT, estado TEXT, motivo TEXT)")
    inserir("INSERT INTO shopee_video_rascunhos (id_video, estado, motivo) VALUES (?, ?, ?)",
            "viral:1", "pulado", "o link não diz o produto do vídeo")
    inserir("INSERT INTO shopee_video_rascunhos (id_video, estado, motivo) VALUES (?, ?, ?)",
            "viral:9", "pulado", "a IA viu o Copo Térmico")
    assert ir.main(["5"]) == 0
    saida = capsys.readouterr().out
    assert "2. motivo: o link não diz o produto | caminho: link curto → produto | produto SEM oferta" in saida
    assert "1. motivo: outro motivo | o vídeo já saiu da fonte" in saida
    assert "1 × pulado (o link não diz o produto): produto SEM oferta na API de afiliado" in saida
    assert "shopee.com.br" not in saida and "Copo" not in saida
    assert ir.main(["x"]) == 2

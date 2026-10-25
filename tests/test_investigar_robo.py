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
    inserir("INSERT INTO shopee_video_rascunhos (id_video, estado, motivo) VALUES (?, ?, ?)",
            "viral:8", "pulado", "o link de vídeo não mostrou o Ver Produtos")
    assert ir.main(["5"]) == 0
    saida = capsys.readouterr().out
    # O passo em que parou, pelo rótulo fixo do histórico do robô; o motivo só quando é
    # um texto fixo do código, nunca o que leva o nome do produto.
    assert "1. motivo: parou em Ver Produtos (o link de vídeo não mostrou o Ver Produtos) |" in saida
    assert "Copo" not in saida
    assert "3. motivo: parou em achar o produto do link (o link não diz o produto do vídeo) | caminho: link curto → produto | produto SEM oferta" in saida
    assert "2. motivo: parou em conferência da IA | o vídeo já saiu da fonte" in saida
    assert "1 × pulado (parou em achar o produto do link (o link não diz o produto do vídeo)): produto SEM oferta na API de afiliado" in saida
    assert "shopee.com.br" not in saida and "Copo" not in saida
    assert ir.main(["x"]) == 2


def test_tentativas_que_nao_deram_certo_com_a_hora_o_passo_e_so_a_forma_do_motivo(capsys):
    # Pedido do Rafael (25/10): corrigir o que impediu de postar. A lista diz a hora (antes ou
    # depois de uma correção) e a forma do motivo, nunca o nome do produto (o log é público).
    import robo_shopee_video as robo
    from datetime import timedelta
    agora = robo.agora_br()
    robo.registrar_tentativa("rascunho", "pulado", "o produto do vídeo não está na lista, nem pela foto do 1º "
                             "(a foto do 1º da lista não é o produto do vídeo (1ª vez)): nada adicionado (aviso no privado)",
                             "Copo Térmico",
                             agora=agora - timedelta(hours=2))
    robo.registrar_tentativa("rascunho", "parou", "não achei Editar na tela", agora=agora - timedelta(hours=1))
    robo.registrar_tentativa("rascunho", "salvo", produto="Copo Térmico", agora=agora - timedelta(minutes=30))
    robo.registrar_tentativa("rascunho", "parou", "Copo Térmico sumiu", agora=agora - timedelta(minutes=10))
    robo.registrar_tentativa("rascunho", "pulado", "o link não diz o produto do vídeo", agora=agora - timedelta(hours=30))
    linhas = ir.tentativas_que_nao_deram_certo()
    assert [linha[1:4] for linha in linhas] == [("rascunho", "pulado", "anexar o produto"),
                                               ("rascunho", "parou", "navegar no app"),
                                               ("rascunho", "parou", "outro")]
    assert linhas[0][4] == "o produto do vídeo não está na lista, nem pela foto do 1º (…): nada adicionado (aviso no privado)"
    assert linhas[1][4] == "não achei … na tela" and linhas[2][4] == ""
    assert linhas[0][0] == (agora - timedelta(hours=2)).strftime("%m-%d %H:%M")
    assert "Copo" not in str(linhas)


def test_comissao_mostra_so_numeros(monkeypatch):
    # P33: a investigação diz se a busca acha o mesmo produto pagando mais, sem nome nem link.
    async def produtos_do_link(link):
        return [{"nome": "Copo Térmico Inox 500ml Tampa", "preco": 10.0, "comissao": 5.0}], link

    async def buscar(termo, limite=10, sort_type=2):
        assert sort_type == 5
        return [{"productName": "Copo Térmico Inox 500ml Tampa Rosa", "commissionRate": "0.085",
                 "productLink": "https://shopee.com.br/product/1/2", "sales": 3},
                {"productName": "Garrafa de Vidro", "commissionRate": "0.2", "productLink": "https://shopee.com.br/product/1/3"},
                {"productName": "Copo Térmico Inox 500ml", "productLink": "https://shopee.com.br/product/1/4"}]

    monkeypatch.setattr(ir.assistente, "produtos_do_link", produtos_do_link)
    monkeypatch.setattr(ir.api_shopee, "buscar_ofertas_shopee", buscar)
    texto, achou = rodar(ir.comissao(LINK))
    assert achou and texto == "comissão: 3 na busca (1 sem a taxa), 1 parecido(s) pagando mais (o melhor: +3.5 ponto(s))"
    assert "Copo" not in texto and "shopee.com" not in texto

"""A medição da P135: os sinais de tendência dos produtos dos vídeos da fonte do robô da Shopee Vídeo."""
from datetime import datetime, timedelta

import pytest

import db
import pedidos_do_canal
import registro_processos
import tendencia_shopee_video as tv
from conftest import inserir, rodar
from fuso import fuso_horario

AGORA = datetime(2026, 11, 3, 6, 41, tzinfo=fuso_horario)
DO_PRODUTO = "https://s.shopee.com.br/produto"
DO_OUTRO = "https://s.shopee.com.br/outro"
DE_VIDEO = "https://sv.shopee.com.br/share-video/abc"
DESTINOS = {DO_PRODUTO: "https://shopee.com.br/product/1/2", DO_OUTRO: "https://shopee.com.br/product/1/2?x=1",
            DE_VIDEO: DE_VIDEO}
OFERTA = {"vendas": 1500, "nota": 4.8, "comissao": 0.12, "preco": 59.9}


@pytest.fixture(autouse=True)
def tabelas():
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    inserir("CREATE TABLE IF NOT EXISTS fila_autorais (id_unico TEXT, caminho_arquivo TEXT, legenda TEXT, "
            "data_captura TEXT)")


def _fonte(*links):
    for i, link in enumerate(links):
        inserir("INSERT INTO fila_autorais VALUES (?, ?, ?, ?)", f"a{i}", f"archive/{i}.mp4", f"Produto 🛍️\n{link}",
                f"2026-11-02 1{i}:00:00")


def _espiao(*itens):
    db.salvar_config("fila_clonagem", {"fila": [
        {"id": f"c{i}", "chat_origem": canal, "link_original": link, "data_captura": quando}
        for i, (canal, link, quando) in enumerate(itens)]})


def _links(monkeypatch, falhar=()):
    seguidos = []

    async def converter(link):
        seguidos.append(link)
        if link in falhar:
            raise TimeoutError("rede")
        return DESTINOS.get(link, link)
    monkeypatch.setattr(tv.api_shopee, "link_para_converter", converter)
    return seguidos


def _ofertas(monkeypatch, oferta=OFERTA):
    pedidas = []

    async def consultar(loja, item):
        pedidas.append((loja, item))
        return dict(oferta) if oferta else None
    monkeypatch.setattr(tv, "_oferta", consultar)
    return pedidas


def _linhas():
    with db.conexao() as con:
        return con.execute("SELECT dia, loja, item, vendas, nota, comissao, preco, videos, canais "
                           "FROM shopee_video_tendencia ORDER BY dia").fetchall()


def _registro():
    return [(l[2], l[3], l[4]) for l in registro_processos.contagem("2000-01-01 00:00:00")
            if l[1] == tv.PROCESSO]


def test_anota_os_sinais_de_cada_produto_da_fonte_sem_mudar_a_escolha(monkeypatch):
    # Escolha do Rafael (P135 1): por uma semana, só anotar, para cada vídeo da fonte, as vendas, a
    # nota, a comissão e o preço do produto, em quantos vídeos ele está e em quantos canais do
    # Espião ele apareceu nos últimos dias; o robô continua escolhendo como hoje.
    db.salvar_config("shopee_video", {"fonte": "autorais"})
    _fonte(DO_PRODUTO, DO_OUTRO, DE_VIDEO)
    recente, velho = "2026-11-02 20:00:00", "2026-10-29 20:00:00"
    _espiao(("-100A", DO_PRODUTO, recente), ("-100B", DO_OUTRO, recente), ("-100A", DO_OUTRO, recente),
            (pedidos_do_canal.CANAL, DO_PRODUTO, recente), ("-100C", DO_PRODUTO, velho))
    seguidos, pedidas = _links(monkeypatch), _ofertas(monkeypatch)
    resumo = rodar(tv.anotar(AGORA))
    # Os dois vídeos do mesmo produto contam juntos; o do Canal Afiliados (nosso) e o de mais de 3
    # dias não contam como canais.
    assert _linhas() == [("2026-11-03", "1", "2", 1500, 4.8, 0.12, 59.9, 2, 2)]
    assert pedidas == [("1", "2")]
    assert resumo == ("1 produto(s) anotado(s) de 3 vídeo(s); 1 de vídeo; 0 sem produto; 0 link(s) não "
                      "seguido(s); 0 sem oferta; 1 visto(s) também no Espião")
    assert _registro() == [("anotado", resumo, 1)]
    assert tv.ja_anotou(AGORA) and not tv.ja_anotou(AGORA + timedelta(days=1))
    # No dia seguinte, os links já seguidos não vão de novo à Shopee; só a API das vendas.
    antes = len(seguidos)
    rodar(tv.anotar(AGORA + timedelta(days=1)))
    assert len(seguidos) == antes and pedidas == [("1", "2"), ("1", "2")]
    assert [linha[0] for linha in _linhas()] == ["2026-11-03", "2026-11-04"]
    # Só ids e números no banco: nada do link, do nome ou da legenda.
    with db.conexao() as con:
        guardado = repr(con.execute("SELECT * FROM shopee_video_tendencia_links").fetchall())
    assert "shopee.com.br" not in guardado and "Produto" not in guardado


def test_o_que_passa_dos_dias_guardados_sai(monkeypatch):
    _fonte(DO_PRODUTO)
    _links(monkeypatch), _ofertas(monkeypatch)
    rodar(tv.anotar(AGORA))
    rodar(tv.anotar(AGORA + timedelta(days=tv.DIAS_GUARDADOS + 1)))
    assert [linha[0] for linha in _linhas()] == [(AGORA + timedelta(days=tv.DIAS_GUARDADOS + 1)).strftime("%Y-%m-%d")]


def test_link_que_nao_da_para_seguir_e_produto_sem_oferta_ficam_no_resumo(monkeypatch):
    _fonte(DO_PRODUTO, DE_VIDEO)
    seguidos = _links(monkeypatch, falhar=(DO_PRODUTO,))
    _ofertas(monkeypatch)
    resumo = rodar(tv.anotar(AGORA))
    assert sorted(seguidos) == sorted([DO_PRODUTO, DE_VIDEO])
    assert "0 produto(s) anotado(s) de 2 vídeo(s); 1 de vídeo" in resumo and "1 link(s) não seguido(s)" in resumo
    # O link que não deu para seguir vai de novo no dia seguinte; o da Shopee Vídeo, não.
    seguidos = _links(monkeypatch)
    _ofertas(monkeypatch, oferta=None)
    resumo = rodar(tv.anotar(AGORA + timedelta(days=1)))
    assert seguidos == [DO_PRODUTO] and "0 link(s) não seguido(s); 1 sem oferta" in resumo
    assert _linhas() == []


def test_sem_videos_na_fonte_o_registro_diz_e_erro_nao_derruba_o_bot(monkeypatch):
    _links(monkeypatch), _ofertas(monkeypatch)
    assert rodar(tv.anotar(AGORA)) == "0 vídeo(s) na fonte"
    _fonte(DO_PRODUTO)

    def quebrado(fonte):
        raise RuntimeError("fila")
    monkeypatch.setattr(tv.assistente, "_candidatos", quebrado)
    assert rodar(tv.anotar(AGORA)) == "falhou (RuntimeError)"
    assert _registro() == [("falhou", "RuntimeError", 0), ("sem vídeos na fonte", "0 vídeo(s) na fonte", None)]


def test_bot_sobe_sem_a_anotacao_do_dia_e_agenda_uma(bm, monkeypatch):
    bm.agendar_tendencia_atrasada()
    assert bm.scheduler.get_job("tendencia_atrasada") is not None
    bm.scheduler.remove_job("tendencia_atrasada")
    monkeypatch.setattr(bm.tendencia_shopee_video, "ja_anotou", lambda agora=None: True)
    bm.agendar_tendencia_atrasada()
    assert bm.scheduler.get_job("tendencia_atrasada") is None

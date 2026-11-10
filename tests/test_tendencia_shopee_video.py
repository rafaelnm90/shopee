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


def test_bot_sobe_sem_a_anotacao_do_dia_e_agenda_uma(bm, monkeypatch, relogio):
    relogio("10:00")
    bm.agendar_tendencia_atrasada()
    assert bm.scheduler.get_job("tendencia_atrasada") is not None
    bm.scheduler.remove_job("tendencia_atrasada")
    monkeypatch.setattr(bm.tendencia_shopee_video, "ja_anotou", lambda agora=None: True)
    bm.agendar_tendencia_atrasada()
    assert bm.scheduler.get_job("tendencia_atrasada") is None


def test_bot_que_sobe_de_madrugada_espera_o_job_da_manha(bm, relogio):
    # O deploy depois da meia-noite não anota o dia: o job das 06:41 ainda vem, e o dia ficaria
    # com duas anotações misturadas.
    relogio("01:23")
    bm.agendar_tendencia_atrasada()
    assert bm.scheduler.get_job("tendencia_atrasada") is None
    relogio("06:45")
    bm.agendar_tendencia_atrasada()
    assert bm.scheduler.get_job("tendencia_atrasada") is not None
    bm.scheduler.remove_job("tendencia_atrasada")


def _anotacao(dia, item, total, canais=0, videos=1, comissao=0.06, preco=50.0):
    tv.comparacao({})          # cria as tabelas
    inserir("INSERT INTO shopee_video_tendencia VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", dia, "1", item, total, 4.8,
            comissao, preco, videos, canais)


def test_comparacao_mostra_o_crescimento_por_faixa_e_o_que_vendeu_pelos_nossos_links():
    # P135: depois dos 7 dias, o Claude compara os sinais de tendência com o que vendeu. A
    # comparação (no relatório cifrado do vendas.py) diz quanto as vendas de cada produto
    # cresceram por dia na Shopee, por faixa dos sinais, e quais venderam pelos nossos links.
    assert "Nenhuma anotação ainda." in tv.comparacao({})
    _anotacao("2026-11-02", "10", 100, canais=2, videos=2, comissao=0.12, preco=60.0)
    _anotacao("2026-11-06", "10", 180, canais=1, videos=1, comissao=0.12, preco=60.0)
    _anotacao("2026-11-02", "20", 50)
    _anotacao("2026-11-04", "20", 50)
    _anotacao("2026-11-05", "30", 7)                                       # um dia só: sem o crescimento
    pedidos = {
        "A": {"data": "2026-11-03", "status": "COMPLETED", "comissao_total": 7.2, "etiqueta": "viral",
              "itens": [{"id": "10", "nome": "x", "qtd": 1, "comissao": 7.2}]},
        "B": {"data": "2026-11-01", "status": "COMPLETED", "comissao_total": 7.2, "etiqueta": "viral",
              "itens": [{"id": "10", "nome": "x", "qtd": 1, "comissao": 7.2}]},   # antes do 1º dia anotado
        "C": {"data": "2026-11-04", "status": "CANCELLED", "comissao_total": 5.0, "etiqueta": "achadinhos",
              "itens": [{"id": "20", "nome": "y", "qtd": 1, "comissao": 5.0}]},   # cancelado
    }
    texto = tv.comparacao(pedidos)
    assert "Anotações de 02/11 a 06/11 (4 dia(s)); 3 produto(s), 2 anotado(s) em 2 dias ou mais" in texto
    assert "Venderam pelos nossos links desde o 1º dia anotado: 1 produto(s), 1 venda(s), R$ 7,20." in texto
    # O 10 cresceu 20 por dia (de 100 a 180 em 4 dias), esteve em 2 canais e em 2 vídeos; o 20, 0.
    assert "| 2 canais ou mais | 1 | 20.0 | 20.0 | 100% | 1 |" in texto
    assert "| 0 canal | 1 | 0.0 | 0.0 | 0% | 0 |" in texto
    assert "| 2 vídeos ou mais | 1 | 20.0 | 20.0 | 100% | 1 |" in texto
    assert "| 10% ou mais | 1 | 20.0 |" in texto and "| 5% a 10% | 1 | 0.0 |" in texto
    assert "| R$ 5 ou mais por venda | 1 | 20.0 |" in texto and "| R$ 2 a R$ 5 por venda | 1 | 0.0 |" in texto
    assert "| 1/10 | 2 | 20.0 | 180 | 2 | 2 | 12.0% | R$ 60,00 | R$ 7,20 | 1 (R$ 7,20; viral) |" in texto
    assert "## Os que venderam pelos nossos links" in texto and "| 1/10 | 1 | R$ 7,20 | viral | 20.0 | 2 | 2 |" in texto

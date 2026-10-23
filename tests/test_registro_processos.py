"""registro_processos.py: cada processo dos robôs fica anotado 3 dias, só com rótulos fixos."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import downloader_bot as dl
import registro_processos as rp
from conftest import Mensagem, consultar, rodar
from fuso import fuso_horario

AGORA = datetime(2026, 10, 23, 14, 0, tzinfo=fuso_horario)


def test_anota_conta_e_apaga_depois_de_3_dias():
    rp.registrar("baixador", "pedido Shopee (vídeo)", "não entregue", "a Shopee demorou", ok=False,
                 agora=AGORA - timedelta(days=4))
    rp.registrar("baixador", "pedido Shopee (vídeo)", "não entregue", "a Shopee demorou", ok=False, agora=AGORA)
    rp.registrar("baixador", "pedido Shopee (vídeo)", "entregue", ok=True, agora=AGORA)
    rp.registrar("baixador", "pedido TikTok", "trava de canais", agora=AGORA)

    assert consultar("SELECT COUNT(*) FROM registro_processos")[0] == 3   # o de 4 dias atrás saiu
    contagem = rp.contagem((AGORA - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S"))
    assert ("baixador", "pedido Shopee (vídeo)", "não entregue", "a Shopee demorou", 0, 1) in contagem
    assert ("baixador", "pedido TikTok", "trava de canais", "", None, 1) in contagem


def test_numero_longo_vira_cerquilha_e_erro_no_banco_nao_derruba(monkeypatch):
    rp.registrar("divulgacao", "envio", "erro", "chat -1001234567890 fechado", ok=False, agora=AGORA)
    assert consultar("SELECT detalhe FROM registro_processos")[0] == "chat # fechado"

    def quebrado(*a, **k):
        raise RuntimeError("banco fora")
    monkeypatch.setattr(rp.db, "conexao", quebrado)
    rp.registrar("x", "y", "z")                     # não levanta
    assert rp.contagem("2026-01-01 00:00:00") == []


def test_forma_do_link_da_shopee():
    assert dl.forma_do_link_shopee("https://sv.shopee.com.br/share-video/AAAA") == "vídeo"
    assert dl.forma_do_link_shopee("https://br.shp.ee/abc") == "link curto"
    assert dl.forma_do_link_shopee("https://shopee.com.br/universal-link?redir=x") == "universal-link"
    assert dl.forma_do_link_shopee("https://shopee.com.br/produto-i.1.2") == "produto ou outro"
    assert dl.processo_do_pedido("TikTok", "https://www.tiktok.com/@a/video/1") == "pedido TikTok"


def _pedido(texto):
    msg = Mensagem(texto, user_id=555)
    msg.pinned_message, msg.caption = None, None
    msg.from_user = SimpleNamespace(id=555, username=None, first_name="Ana", is_bot=False)
    return msg


def test_pedido_que_nao_sai_fica_no_registro_com_o_motivo(monkeypatch, tmp_path):
    async def falha(url, url_pedido, pasta):
        return None, "a Shopee demorou demais para responder"

    async def mesmo(url):
        return url

    monkeypatch.setattr(dl, "downloads_totais", lambda _id: 0)
    monkeypatch.setattr(dl, "downloads_hoje", lambda _id: 0)
    monkeypatch.setattr(dl, "buscar_cache_video", lambda _url: None)
    monkeypatch.setattr(dl, "expandir_encurtador", mesmo)
    monkeypatch.setattr(dl, "baixar_da_shopee", falha)
    monkeypatch.setattr(dl, "PASTA_TEMP_DOWNLOAD", str(tmp_path))

    msg = _pedido("https://sv.shopee.com.br/share-video/AAAAcopos==")
    rodar(dl.receber_link(msg))
    assert "não deu certo" in msg.saidas[-1]
    linha = consultar("SELECT robo, processo, resultado, detalhe, ok FROM registro_processos")
    assert linha == ("baixador", "pedido Shopee (vídeo)", "não entregue", "a Shopee demorou demais para responder", 0)

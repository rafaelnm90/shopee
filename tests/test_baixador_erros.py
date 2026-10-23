"""downloader_bot: a resposta de erro some 5 min depois, junto com o link do membro (escolha do Rafael, 23/10)."""
from types import SimpleNamespace

import downloader_bot as dl
from conftest import Mensagem, rodar


def _pedido(texto):
    msg = Mensagem(texto, user_id=555)
    msg.pinned_message, msg.caption = None, None
    msg.from_user = SimpleNamespace(id=555, username=None, first_name="Ana", is_bot=False)
    return msg


def test_erro_agenda_a_saida_do_erro_e_do_link(monkeypatch, tmp_path):
    async def falha(url, url_pedido, pasta):
        return None, "não achei nenhum arquivo de vídeo nesta página da Shopee"

    async def mesmo(url):
        return url
    agendados = []

    async def expirar(resposta, link_original):
        agendados.append((resposta, link_original))
    monkeypatch.setattr(dl, "downloads_totais", lambda _id: 0)
    monkeypatch.setattr(dl, "downloads_hoje", lambda _id: 0)
    monkeypatch.setattr(dl, "buscar_cache_video", lambda _url: None)
    monkeypatch.setattr(dl, "expandir_encurtador", mesmo)
    monkeypatch.setattr(dl, "baixar_da_shopee", falha)
    monkeypatch.setattr(dl, "expirar_erro", expirar)
    monkeypatch.setattr(dl, "PASTA_TEMP_DOWNLOAD", str(tmp_path))

    msg = _pedido("https://sv.shopee.com.br/share-video/AAAAcopos==")

    async def cenario():
        await dl.receber_link(msg)
        await dl.asyncio.sleep(0)       # deixa a tarefa agendada rodar
    rodar(cenario())
    assert "não deu certo" in msg.saidas[-1]
    assert len(agendados) == 1 and agendados[0][1] is msg


def test_expirar_erro_apaga_os_dois_depois_de_5_min(monkeypatch):
    esperas = []

    async def dormir(segundos):
        esperas.append(segundos)
    monkeypatch.setattr(dl.asyncio, "sleep", dormir)
    resposta, link = Mensagem("❌ erro"), Mensagem("https://br.shp.ee/x")
    rodar(dl.expirar_erro(resposta, link))
    assert esperas == [300] and resposta.apagada and link.apagada

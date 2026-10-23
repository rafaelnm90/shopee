"""downloader_bot: vídeo da Shopee Vídeo que a Shopee não deixa baixar explica e ensina a salvar pelo app."""

import aiohttp
import pytest

import downloader_bot as dl
from conftest import rodar

UNIVERSAL = ("https://shopee.com.br/universal-link?redir=https%3A%2F%2Fsv.shopee.com.br%2Fshare-video%2FAAAAcopos"
             "%3D%3D%3FfromSource%3Dcopy_link&fromShareLink=share-marker")
# A página da Shopee Vídeo como ela vem hoje: só o postId e o perfil, sem o vídeo.
PAGINA_SEM_VIDEO = ('<html><script id="__NEXT_DATA__" type="application/json">'
                    '{"props": {"pageProps": {"userDetail": {"nome": "x"}}}, "query": {"postId": "AAAAcopos"}}'
                    '</script></html>')


class Resposta:
    def __init__(self, url, html):
        self.url, self.html, self.status = url, html, 200

    async def text(self):
        return self.html

    async def __aenter__(self):
        return self

    async def __aexit__(self, *erro):
        return False


class Sessao:
    """O aiohttp de mentira: o link curto leva ao destino dado; toda página vem sem vídeo."""
    destino = UNIVERSAL

    def __init__(self, *args, **kwargs):
        pass

    def get(self, url, **kwargs):
        return Resposta(self.destino if "shp.ee" in url else url, PAGINA_SEM_VIDEO)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *erro):
        return False


@pytest.fixture
def shopee(monkeypatch):
    monkeypatch.setattr(aiohttp, "ClientSession", Sessao)
    return Sessao


@pytest.mark.parametrize("destino", [UNIVERSAL, "https://sv.shopee.com.br/share-video/AAAAcopos"])
def test_video_da_shopee_sem_o_arquivo_diz_que_a_shopee_bloqueou(shopee, destino, tmp_path):
    # Vídeo do Rafael (23/10): o link curto dos copos dizia "não achei nenhum arquivo ...
    # talvez o link seja de produto", e a Shopee é que não deixa mais baixar.
    shopee.destino = destino
    caminho, erro = rodar(dl.baixar_video_shopee("https://br.shp.ee/abc123", str(tmp_path)))
    assert caminho is None and erro == dl.ERRO_SHOPEE_BLOQUEOU


def test_pagina_de_produto_sem_video_continua_com_a_mensagem_de_antes(shopee, tmp_path):
    shopee.destino = "https://shopee.com.br/Copo-Termico-i.123.456"
    caminho, erro = rodar(dl.baixar_video_shopee("https://br.shp.ee/abc123", str(tmp_path)))
    assert caminho is None and "Talvez o link seja de produto" in erro


def test_mensagem_ensina_a_salvar_pelo_app_so_no_bloqueio_da_shopee():
    texto = dl.texto_do_erro("@ana", dl.ERRO_SHOPEE_BLOQUEOU)
    assert texto.startswith("❌ @ana, não deu certo: <b>a Shopee está bloqueando downloads automáticos")
    assert "Compartilhar" in texto and "Salvar" in texto and "Confira se o link" not in texto
    outro = dl.texto_do_erro("@ana", "o vídeo passa de 48 MB")
    assert "Confira se o link está certo" in outro and "Compartilhar" not in outro


def test_eh_video_da_shopee():
    assert dl.eh_video_da_shopee("https://sv.shopee.com.br/share-video/AAAA")
    assert dl.eh_video_da_shopee("https://shopee.com.br/share-video/AAAA?x=1")
    assert not dl.eh_video_da_shopee("https://shopee.com.br/produto-i.1.2")
    assert not dl.eh_video_da_shopee(None)


def test_link_curto_da_shopee_video_que_nao_redireciona_tambem_ensina_a_salvar(monkeypatch, tmp_path):
    # Vídeo do Rafael (23/10, 09:00): no servidor, br.shp.ee responde 200 com uma página que
    # só redireciona por script; o Baixador nunca chegava ao vídeo e dizia "talvez o link
    # seja de produto".
    class SemRedirecionar(Sessao):
        def get(self, url, **kwargs):
            return Resposta(url, "<html><script>var ULS = {};</script></html>")

    monkeypatch.setattr(aiohttp, "ClientSession", SemRedirecionar)
    caminho, erro = rodar(dl.baixar_video_shopee("https://br.shp.ee/03xe6k5k?fromSource=copy_link", str(tmp_path)))
    assert caminho is None and erro == dl.ERRO_SHOPEE_BLOQUEOU
    assert dl.eh_link_curto_de_video("https://br.shp.ee/x") and not dl.eh_link_curto_de_video("https://s.shopee.com.br/x")

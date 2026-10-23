"""downloader_bot: quando a Shopee bloqueia, o vídeo da Shopee Vídeo vem pelo serviço da Apify (escolha do Rafael, 23/10)."""

import json
import os
from datetime import datetime, timedelta

import aiohttp
import pytest

import downloader_bot as dl
from conftest import inserir, rodar

UNIVERSAL = ("https://shopee.com.br/universal-link?redir=https%3A%2F%2Fsv.shopee.com.br%2Fshare-video%2FAAAAcopos"
             "%3D%3D&fromShareLink=share-marker")
VIDEO = "https://sv.shopee.com.br/share-video/AAAAcopos=="
SEM_MARCA = "https://cdn.exemplo/video.mp4"
COM_MARCA = "https://cdn.exemplo/video.123.456.mp4"
AGORA = datetime(2026, 10, 23, 12, 0)


class Conteudo:
    async def iter_chunked(self, tamanho):
        yield b"video"


class Resposta:
    def __init__(self, status=200, corpo=""):
        self.status, self.corpo, self.content = status, corpo, Conteudo()

    async def text(self):
        return self.corpo

    async def json(self):
        return json.loads(self.corpo)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *erro):
        return False


class Apify:
    """O aiohttp de mentira: o POST é a Apify; o GET é o CDN da Shopee."""
    status, itens, pedidos, baixados = 201, [], [], []

    def __init__(self, *args, **kwargs):
        pass

    def post(self, url, json=None, headers=None, **kwargs):
        Apify.pedidos.append((url, json, headers))
        return Resposta(Apify.status, __import__("json").dumps(Apify.itens) if Apify.status < 400 else
                        '{"error": {"type": "not-enough-usage-to-run-paid-actor"}}')

    def get(self, url, **kwargs):
        Apify.baixados.append(url)
        return Resposta(200)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *erro):
        return False


@pytest.fixture
def apify(monkeypatch):
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    monkeypatch.setenv("APIFY_TOKEN", "chave-de-teste")
    monkeypatch.setattr(aiohttp, "ClientSession", Apify)
    Apify.status, Apify.itens, Apify.pedidos, Apify.baixados = 201, [], [], []
    avisos = []
    import avisar_rafael
    monkeypatch.setattr(avisar_rafael, "mandar_texto", lambda texto: avisos.append(texto) or True)
    return avisos


def test_sem_a_chave_nao_chama_a_apify(monkeypatch, tmp_path):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: pytest.fail("chamou a Apify sem a chave"))
    assert rodar(dl.baixar_pela_apify(VIDEO, str(tmp_path))) == (None, "sem a chave da Apify")


def test_baixa_a_versao_sem_marca_e_manda_o_link_do_video(apify, tmp_path):
    Apify.itens = [{"watermarkUrl": COM_MARCA, "noWatermarkUrl": SEM_MARCA, "duration": 15000}]
    caminho, motivo = rodar(dl.baixar_pela_apify(UNIVERSAL, str(tmp_path), AGORA))
    assert motivo is None and os.path.exists(caminho) and not os.path.exists(tmp_path / "COM_MARCA")
    url, corpo, cabecalhos = Apify.pedidos[0]
    # Do universal-link vai só o vídeo do redir; a chave vai no cabeçalho, nunca no endereço.
    assert corpo == {"startUrls": [{"url": VIDEO}]} and "chave-de-teste" not in url
    assert cabecalhos["Authorization"] == "Bearer chave-de-teste" and Apify.baixados == [SEM_MARCA]
    assert dl.db.ler_config(dl.CHAVE_CONFERENCIA)["apify_entregues"] == 1


def test_so_com_a_versao_marcada_a_limpeza_borra_a_marca(apify, tmp_path):
    Apify.itens = [{"watermarkUrl": COM_MARCA}]
    caminho, motivo = rodar(dl.baixar_pela_apify(VIDEO, str(tmp_path), AGORA))
    assert motivo is None and os.path.exists(tmp_path / "COM_MARCA") and Apify.baixados == [COM_MARCA]


def test_sem_video_na_resposta_conta_falha(apify, tmp_path):
    Apify.itens = [{"likeCount": 3}]
    assert rodar(dl.baixar_pela_apify(VIDEO, str(tmp_path), AGORA)) == (None, "a Apify não achou o vídeo")
    assert dl.db.ler_config(dl.CHAVE_CONFERENCIA)["apify_falhas"] == 1 and Apify.baixados == []


def test_sem_credito_avisa_uma_vez_e_espera_um_dia(apify, tmp_path):
    # Escolha do Rafael: só o crédito grátis do mês. Acabou, avisa e volta a ensinar a salvar pelo app.
    Apify.status = 402
    assert rodar(dl.baixar_pela_apify(VIDEO, str(tmp_path), AGORA)) == (None, "sem crédito na Apify")
    assert apify == [dl.AVISO_SEM_CREDITO]
    # No mesmo dia, nem chama a Apify.
    assert rodar(dl.baixar_pela_apify(VIDEO, str(tmp_path), AGORA + timedelta(hours=5)))[1] == "sem crédito na Apify"
    assert len(Apify.pedidos) == 1
    # Um dia depois tenta de novo; recusou de novo, mas o aviso não se repete no mesmo mês.
    rodar(dl.baixar_pela_apify(VIDEO, str(tmp_path), AGORA + timedelta(days=1, minutes=1)))
    assert len(Apify.pedidos) == 2 and apify == [dl.AVISO_SEM_CREDITO]


def test_a_apify_entra_so_quando_a_shopee_bloqueia(monkeypatch, tmp_path):
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    pedidos = []

    async def apify_de_mentira(url, pasta, agora=None):
        pedidos.append(url)
        return (os.path.join(pasta, "video.mp4"), None) if "ok" in url else (None, "a Apify não achou o vídeo")

    async def direto(url, pasta):
        return (None, dl.ERRO_SHOPEE_BLOQUEOU) if "share-video" in url else (None, "o vídeo passa de 48 MB")

    monkeypatch.setattr(dl, "baixar_pela_apify", apify_de_mentira)
    monkeypatch.setattr(dl, "baixar_video_shopee", direto)
    assert rodar(dl.baixar_da_shopee(VIDEO, "https://br.shp.ee/ok", str(tmp_path)))[1] is None
    # Sem o vídeo pela Apify, o membro recebe a explicação de sempre (salvar pelo app).
    assert rodar(dl.baixar_da_shopee(VIDEO, "https://br.shp.ee/x", str(tmp_path))) == (None, dl.ERRO_SHOPEE_BLOQUEOU)
    # Outro erro (não é o bloqueio) não gasta crédito da Apify.
    assert rodar(dl.baixar_da_shopee("https://shopee.com.br/p-i.1.2", "x", str(tmp_path)))[1] == "o vídeo passa de 48 MB"
    assert pedidos == ["https://br.shp.ee/ok", "https://br.shp.ee/x"]


def test_link_para_a_apify_e_endereco_do_video():
    assert dl.link_para_a_apify(UNIVERSAL) == VIDEO
    assert dl.link_para_a_apify("https://br.shp.ee/abc") == "https://br.shp.ee/abc"
    assert dl.endereco_do_video([{"noWatermarkUrl": SEM_MARCA}]) == (SEM_MARCA, False)
    assert dl.endereco_do_video({"erro": 1}) == (None, False)


def test_muitos_pedidos_nao_conta_como_falta_de_credito():
    assert dl._recusa_por_credito(402, "")
    assert dl._recusa_por_credito(403, '{"error": {"type": "not-enough-usage-to-run-paid-actor"}}')
    assert not dl._recusa_por_credito(429, '{"error": {"type": "rate-limit-exceeded"}}')
    assert not dl._recusa_por_credito(403, '{"error": {"type": "insufficient-permissions"}}')

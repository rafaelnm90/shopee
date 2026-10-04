"""tela_android.py: só responde com a chave, e cada ação da página vira um comando adb seguro."""
import asyncio

import pytest
from aiohttp import web

import tela_android as tela
from conftest import rodar


class Pedido:
    def __init__(self, chave="", corpo=None):
        self.query = {"k": chave} if chave else {}
        self._corpo = corpo or {}

    async def json(self):
        return self._corpo


def test_sem_a_chave_nada_responde():
    for handler in (tela.pagina, tela.tela):
        with pytest.raises(web.HTTPNotFound):
            rodar(handler(Pedido("chave-errada")))
    with pytest.raises(web.HTTPNotFound):
        rodar(tela.acao(Pedido("", {"tipo": "toque", "x": 1, "y": 1})))


def test_pagina_com_a_chave(monkeypatch):
    resposta = rodar(tela.pagina(Pedido(tela.CHAVE)))
    assert resposta.status == 200 and tela.CHAVE in resposta.text


def test_acoes_viram_comandos_adb():
    assert tela.comando_da_acao({"tipo": "toque", "x": 100.6, "y": 200}) == \
        ["shell", "input", "tap", "100", "200"]
    assert tela.comando_da_acao({"tipo": "arrastar", "x1": 10, "y1": 20, "x2": 300, "y2": 20, "ms": 50}) == \
        ["shell", "input", "swipe", "10", "20", "300", "20", "100"]       # duração mínima de 100 ms
    assert tela.comando_da_acao({"tipo": "tecla", "tecla": "voltar"}) == ["shell", "input", "keyevent", "4"]


def test_texto_vai_protegido_do_shell_do_android():
    comando = tela.comando_da_acao({"tipo": "texto", "texto": "minha senha; rm -rf /"})
    assert comando[:3] == ["shell", "input", "text"]
    assert comando[3] == "'minha%ssenha;%srm%s-rf%s/'"                 # um argumento só, entre aspas


def test_acoes_invalidas_sao_recusadas():
    for dados in ({"tipo": "toque", "x": -5, "y": 1}, {"tipo": "toque", "x": "1;reboot", "y": 1},
                  {"tipo": "tecla", "tecla": "desligar"}, {"tipo": "texto", "texto": ""},
                  {"tipo": "toque"}, {"tipo": "outra"}):
        assert tela.comando_da_acao(dados) is None
    with pytest.raises(web.HTTPBadRequest):
        rodar(tela.acao(Pedido(tela.CHAVE, {"tipo": "tecla", "tecla": "desligar"})))


def test_acao_valida_chama_o_adb(monkeypatch):
    chamados = []

    async def adb(*partes, timeout=20):
        chamados.append(partes)
        return b""

    monkeypatch.setattr(tela, "adb", adb)
    rodar(tela.acao(Pedido(tela.CHAVE, {"tipo": "toque", "x": 5, "y": 6})))
    assert chamados == [("shell", "input", "tap", "5", "6")]


def test_terminei_fecha_a_tela(monkeypatch):
    monkeypatch.setattr(tela, "FIM", asyncio.Event())
    rodar(tela.acao(Pedido(tela.CHAVE, {"tipo": "fim"})))
    assert tela.FIM.is_set()


def _zip(caminho, nomes):
    import zipfile
    with zipfile.ZipFile(caminho, "w") as z:
        for nome in nomes:
            z.writestr(nome, "x")
    return open(caminho, "rb").read()


def _enviar(conteudo, chave=None, nome="shopee.xapk"):
    """Sobe o servidor da tela de verdade e envia o arquivo pelo botão Enviar app."""
    from aiohttp import FormData
    from aiohttp.test_utils import TestClient, TestServer

    async def cenario():
        async with TestClient(TestServer(tela.montar_app())) as cliente:
            dados = FormData()
            dados.add_field("arquivo", conteudo, filename=nome)
            resposta = await cliente.post(f"/app?k={tela.CHAVE if chave is None else chave}", data=dados)
            corpo = await resposta.json() if resposta.status == 200 else None
            return resposta.status, corpo
    return rodar(cenario())


def _android_falso(monkeypatch, tmp_path):
    instalados = []
    monkeypatch.setattr(tela.av, "PASTA_APP", str(tmp_path / "app"))
    monkeypatch.setattr(tela.av, "_adb", lambda *p, timeout=30: instalados.append(p) or (0, ""))
    monkeypatch.setattr(tela.av, "versao_shopee", lambda pacote=None: "instalado, versão 3.40.21")
    return instalados


def test_enviar_app_xapk_instala_as_partes(monkeypatch, tmp_path):
    instalados = _android_falso(monkeypatch, tmp_path)
    conteudo = _zip(tmp_path / "s.xapk", ["manifest.json", "com.shopee.br.apk", "config.arm64_v8a.apk",
                                         "config.x86_64.apk"])
    status, corpo = _enviar(conteudo)
    assert status == 200 and corpo == {"ok": True, "mensagem": "app da Shopee: instalado, versão 3.40.21"}
    comando = instalados[0]
    assert comando[0] == "install-multiple" and len(comando) == 5          # -r -g e as 2 partes do ARM 64
    assert not (tmp_path / "app").exists()                                # nada fica no servidor


def test_enviar_algo_que_nao_e_app(monkeypatch, tmp_path):
    instalados = _android_falso(monkeypatch, tmp_path)
    status, corpo = _enviar(b"isto nao e um zip", nome="foto.jpg")
    assert status == 200 and corpo["ok"] is False and "não é um app" in corpo["mensagem"]
    assert instalados == []


def test_enviar_app_sem_a_chave(monkeypatch, tmp_path):
    instalados = _android_falso(monkeypatch, tmp_path)
    status, _ = _enviar(b"x", chave="errada")
    assert status == 404 and instalados == []


def test_enviar_app_grande_demais(monkeypatch, tmp_path):
    instalados = _android_falso(monkeypatch, tmp_path)
    monkeypatch.setattr(tela, "LIMITE_APP_MB", 1)
    status, corpo = _enviar(b"x" * (2 * 1024 * 1024))
    assert corpo == {"ok": False, "mensagem": "arquivo maior que 1 MB"} and instalados == []


def test_endereco_do_tunel_na_saida_do_cloudflared():
    class Saida:
        def __init__(self, linhas):
            self.linhas = [l.encode() for l in linhas]

        async def readline(self):
            return self.linhas.pop(0) if self.linhas else b""

    processo = type("P", (), {})()
    processo.stdout = Saida(["INF Requesting new quick Tunnel", "|  https://palavras-soltas-aqui.trycloudflare.com  |"])
    assert rodar(tela.achar_url(processo, 5)) == "https://palavras-soltas-aqui.trycloudflare.com"
    processo.stdout = Saida(["INF erro qualquer"])
    assert rodar(tela.achar_url(processo, 5)) is None

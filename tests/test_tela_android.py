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

"""Diagnóstico da captura dos parceiros: o que chega da origem e por que um vídeo é recusado."""
from datetime import datetime
from types import SimpleNamespace

import pytest
from telethon.tl.types import MessageMediaDocument

from conftest import rodar

ORIGEM = "-1001234567890"


@pytest.fixture
def diag(bm, esp, monkeypatch):
    """Robô dos Autorais com o diagnóstico zerado, gravando no banco a cada anotação."""
    monkeypatch.setattr(esp, "_diagnostico_parceiros", {})
    monkeypatch.setattr(esp, "_origens_parceiros", {"ids": {}, "quando": None})
    monkeypatch.setattr(esp, "INTERVALO_GRAVAR_DIAGNOSTICO", 0)
    pid = bm.salvar_parceiro({"nome": "Rafaela", "app_id": "123456", "app_secret": "x" * 20,
                              "canal_origem": ORIGEM, "canal_destino": "-1001"})
    return pid


def _evento(texto=""):
    async def get_chat():
        return SimpleNamespace(id=1234567890, title="Canal da origem", username=None)
    return SimpleNamespace(out=False, chat_id=int(ORIGEM), sender_id=int(ORIGEM), raw_text=texto,
                           entities=None, media=MessageMediaDocument(), get_chat=get_chat,
                           message=SimpleNamespace(reply_to=None))


def test_video_sem_link_da_origem_aparece_como_recusado(bm, esp, diag):
    rodar(esp.interceptar_e_espelhar(_evento("vídeo sem link nenhum")))

    texto = bm.diagnostico_origem_parceiro(diag, datetime.now().strftime("%Y-%m-%d"))
    assert "1 mensagem(ns) · 1 vídeo(s) · 0 com link" in texto
    assert "vídeo sem link da Shopee (1)" in texto and "Última mensagem" in texto


def test_contagem_continua_depois_de_reiniciar(esp, diag, monkeypatch):
    esp.anotar_parceiro(diag, "mensagens")
    monkeypatch.setattr(esp, "_diagnostico_parceiros", {})      # robô reiniciou
    esp.anotar_parceiro(diag, "mensagens")
    assert esp.db.ler_config("diagnostico_parceiros")[str(diag)]["mensagens"] == 2


def test_sem_nada_da_origem_diz_que_nao_chegou(bm, diag):
    texto = bm.diagnostico_origem_parceiro(diag, datetime.now().strftime("%Y-%m-%d"))
    assert "nada recebido do canal" in texto

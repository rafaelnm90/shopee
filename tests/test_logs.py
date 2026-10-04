"""Log dos robôs: um controle só (NIVEL_LOG no .env), sem chave espalhada pelo código."""
import glob
import logging
import os
import re

import pytest

import fuso

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def log_do_zero(monkeypatch):
    """configurar_logs como na subida do robô; devolve o nível que o processo tinha antes."""
    raiz = logging.getLogger()
    nivel_antes, handlers_antes = raiz.level, list(raiz.handlers)
    bibliotecas_antes = {b: logging.getLogger(b).level for b in fuso.BIBLIOTECAS_SO_AVISOS}
    monkeypatch.setattr(fuso, "_LOGS_CONFIGURADOS", False)
    yield
    raiz.handlers[:] = handlers_antes
    raiz.setLevel(nivel_antes)
    for biblioteca, nivel in bibliotecas_antes.items():
        logging.getLogger(biblioteca).setLevel(nivel)


@pytest.mark.parametrize("valor, esperado", [
    (None, logging.INFO),
    ("WARNING", logging.WARNING),
    ("debug", logging.DEBUG),
    (" error ", logging.ERROR),
    ("qualquer coisa", logging.INFO),
])
def test_nivel_do_log_vem_do_env(log_do_zero, monkeypatch, valor, esperado):
    if valor is None:
        monkeypatch.delenv("NIVEL_LOG", raising=False)
    else:
        monkeypatch.setenv("NIVEL_LOG", valor)
    fuso.configurar_logs("teste")
    assert logging.getLogger().level == esperado


@pytest.mark.parametrize("valor, esperado", [
    ("INFO", logging.WARNING),
    ("ERROR", logging.ERROR),
    ("DEBUG", logging.DEBUG),
])
def test_bibliotecas_falam_so_avisos_fora_do_debug(log_do_zero, monkeypatch, valor, esperado):
    monkeypatch.setenv("NIVEL_LOG", valor)
    fuso.configurar_logs("teste")
    for biblioteca in ("apscheduler.executors.default", "aiogram.event", "telethon.network", "httpx"):
        assert logging.getLogger(biblioteca).getEffectiveLevel() == esperado, biblioteca
    # O resto do aiogram (início do polling, falhas de conexão) continua no nível do robô.
    assert logging.getLogger("aiogram.dispatcher").getEffectiveLevel() == logging.getLogger().level


def test_nenhum_arquivo_volta_a_usar_chave_de_log():
    # O nível do log se ajusta no NIVEL_LOG; um "if EXIBIR_LOGS:" por linha não volta.
    padrao = re.compile(r"\b(EXIBIR_LOGS|exibir_logs)\b")
    culpados = []
    for caminho in glob.glob(os.path.join(RAIZ, "*.py")):
        with open(caminho, encoding="utf-8") as f:
            culpados += [f"{os.path.basename(caminho)}:{n}" for n, linha in enumerate(f, 1) if padrao.search(linha)]
    assert culpados == [], "use o NIVEL_LOG: " + ", ".join(culpados)

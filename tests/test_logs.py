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
    monkeypatch.setattr(fuso, "_LOGS_CONFIGURADOS", False)
    yield
    raiz.handlers[:] = handlers_antes
    raiz.setLevel(nivel_antes)


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


def test_nenhum_arquivo_volta_a_usar_chave_de_log():
    # O nível do log se ajusta no NIVEL_LOG; um "if EXIBIR_LOGS:" por linha não volta.
    padrao = re.compile(r"\b(EXIBIR_LOGS|exibir_logs)\b")
    culpados = []
    for caminho in glob.glob(os.path.join(RAIZ, "*.py")):
        with open(caminho, encoding="utf-8") as f:
            culpados += [f"{os.path.basename(caminho)}:{n}" for n, linha in enumerate(f, 1) if padrao.search(linha)]
    assert culpados == [], "use o NIVEL_LOG: " + ", ".join(culpados)

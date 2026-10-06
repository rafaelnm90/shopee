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


def test_video_publico_sem_arquivo_avisa_uma_vez_a_cada_6_horas(bm, relogio, caplog, monkeypatch):
    # O motor do Grupo Público volta a cada 2 min; enquanto o Correio não baixa o vídeo,
    # o aviso não pode encher o log (era a linha mais repetida do bot_mestre).
    from datetime import datetime, timedelta
    import espelhador_videos_autorais
    from conftest import inserir, rodar
    relogio("15:00")
    espelhador_videos_autorais.ler_fila_publico()   # cria a tabela fila_publico
    monkeypatch.setattr(bm, "_avisos_sem_arquivo_publico", {})
    bm.salvar_submissao_config({"ativo": True, "grupo_id": "-100123", "repost_inicio": 0, "repost_fim": 24})
    agora = datetime.now(bm.fuso_horario)

    def vencido():
        inserir("UPDATE fila_publico SET horario_disparo = ? WHERE id_unico = 'v1'",
                (agora - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"))

    inserir("INSERT INTO fila_publico (id_unico, legenda, data_alvo, horario_disparo, processado, caminho_arquivo) "
            "VALUES ('v1', '', ?, ?, 0, 'sumiu.mp4')", agora.strftime("%Y-%m-%d"),
            (agora - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"))
    with caplog.at_level(logging.DEBUG):
        rodar(bm.motor_repost_publico_step())
        vencido()
        rodar(bm.motor_repost_publico_step())
    avisos = [r for r in caplog.records if "ainda sem arquivo no disco" in r.getMessage()]
    assert len(avisos) == 1 and avisos[0].levelno == logging.WARNING
    assert any("continua sem arquivo no disco" in r.getMessage() and r.levelno == logging.DEBUG
               for r in caplog.records)

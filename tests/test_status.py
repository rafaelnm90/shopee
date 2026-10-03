"""/status e o alerta de erros do monitor de saúde."""
from types import SimpleNamespace

from conftest import rodar


def registrar_erros(n):
    from utils import registrar_erro_json
    for i in range(n):
        registrar_erro_json(f"falha de teste {i} <b>", origem="teste")


def test_monitor_avisa_muitos_erros_na_ultima_hora(bm, monkeypatch):
    alertas = []

    async def send_message(chat, texto, **k):
        alertas.append(texto)
    monkeypatch.setattr(bm.bot, "send_message", send_message)
    registrar_erros(12)
    rodar(bm.monitor_saude())
    assert any("12 erros na última hora" in a for a in alertas)


def test_status_mostra_servicos_versao_e_erros(bm, Msg, monkeypatch):
    def run(cmd, **k):
        if cmd[0] == "git":
            return SimpleNamespace(stdout="abc1234 03/10 15:40\n")
        if "downloader_bot.service" in cmd:
            saida = "ActiveState=activating\nActiveEnterTimestamp=\nNRestarts=7\n"
        else:
            saida = "ActiveState=active\nActiveEnterTimestamp=Sat 2026-10-03 18:40:00 -03\nNRestarts=0\n"
        return SimpleNamespace(stdout=saida)
    monkeypatch.setattr(bm.subprocess, "run", run)
    registrar_erros(2)
    msg = Msg("/status")
    rodar(bm.comando_status(msg, None))
    texto = msg.saidas[-1]
    assert "abc1234" in texto
    assert "✅ Bot Mestre: <b>active</b> · desde 03/10 18:40" in texto
    assert "❌ Baixador: <b>activating</b> · 7 reinício(s)" in texto
    assert "Erros na última hora: <b>2</b>" in texto
    assert "&lt;b&gt;" in texto                       # erro com HTML não quebra a mensagem


def test_status_so_para_o_admin(bm, Msg):
    msg = Msg("/status", user_id=999)
    rodar(bm.comando_status(msg, None))
    assert msg.saidas == []

"""Logs que se repetiam a cada volta dos laços: agora saem uma vez, quando algo muda."""
from utils import salvar_nome_grupo


def test_pausa_do_motor_autorais_avisa_uma_vez(esp, monkeypatch):
    avisos = []
    monkeypatch.setattr(esp.logger, "info", avisos.append)
    monkeypatch.setattr(esp, "_pausa_avisada", None)
    for _ in range(3):
        esp.avisar_pausa(("janela", "2026-10-03", 8, 22), "fora da janela")
    esp.avisar_pausa(("teto", "2026-10-03"), "teto do dia")
    esp.avisar_pausa(("teto", "2026-10-03"), "teto do dia")
    esp.fim_da_pausa()
    esp.avisar_pausa(("janela", "2026-10-03", 8, 22), "fora da janela")
    assert avisos == ["fora da janela", "teto do dia", "fora da janela"]


def test_nome_de_grupo_so_conta_quando_muda():
    assert salvar_nome_grupo("-1001_5", "Tópico") is True
    assert salvar_nome_grupo("-1001_5", "Tópico") is False
    assert salvar_nome_grupo("-1001_5", "Tópico renomeado") is True
    assert salvar_nome_grupo("-1001_5", "-1001_5") is False

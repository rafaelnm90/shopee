"""alertas.py: os erros graves avisados na hora, uma vez, e o voltou ao normal."""
from datetime import datetime, timedelta

import pytest

import alertas
import db
from conftest import inserir
from fuso import fuso_horario

AGORA = datetime(2026, 10, 24, 15, 0, tzinfo=fuso_horario)


@pytest.fixture(autouse=True)
def base(monkeypatch):
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    monkeypatch.setattr(alertas, "_disco_em_uso", lambda: 40)
    monkeypatch.setattr(alertas.backup_dados, "ultimo_backup", lambda: ("x", 10.0, 1))


def test_chaves_do_robo_sao_as_mesmas():
    import robo_shopee_video as robo
    assert alertas.CHAVE_CONFIG_SV == robo.CHAVE_CONFIG and alertas.CHAVE_ESTADO_SV == robo.CHAVE_ESTADO


def test_grave_avisado_uma_vez_de_novo_em_6_h_e_o_voltou_ao_normal(monkeypatch):
    mandados = []

    def mandar(texto):
        mandados.append(texto)
        return True

    assert alertas.verificar(["downloader_bot"], AGORA, mandar) == ["fora:downloader_bot"]
    assert len(mandados) == 1 and "Baixador está fora do ar" in mandados[0]
    alertas.verificar(["downloader_bot"], AGORA + timedelta(hours=1), mandar)
    assert len(mandados) == 1                                  # não repete na hora seguinte
    alertas.verificar(["downloader_bot"], AGORA + timedelta(hours=6), mandar)
    assert len(mandados) == 2                                  # continua: lembra depois de 6 h
    alertas.verificar([], AGORA + timedelta(hours=7), mandar)
    assert mandados[-1] == "✅ Voltou ao normal: downloader_bot fora do ar."
    assert db.ler_config(alertas.CHAVE, {}) == {}


def test_disco_backup_erros_e_robo_da_shopee_video_parado(monkeypatch):
    monkeypatch.setattr(alertas, "_disco_em_uso", lambda: 93)
    monkeypatch.setattr(alertas.backup_dados, "ultimo_backup", lambda: ("x", 30.0, 1))
    from utils import registrar_erro_json
    for _ in range(10):
        registrar_erro_json("falhou", origem="teste")
    inserir("UPDATE erros_logs SET timestamp = ?", (AGORA - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"))
    db.salvar_config("shopee_video", {"robo_pausado": False, "robo_inicio": 9, "robo_fim": 21})
    db.salvar_config("shopee_video_robo", {"ultima_rodada_em": "2026-10-24 13:30:00"})
    graves = alertas.graves([], AGORA)
    assert sorted(graves) == ["backup", "disco", "erros", "robo_sv"]
    assert "93%" in graves["disco"] and "30 h" in graves["backup"] and "90 min" in graves["robo_sv"]
    # Pausado ou fora do horário, o robô parado não é grave.
    db.salvar_config("shopee_video", {"robo_pausado": True, "robo_inicio": 9, "robo_fim": 21})
    assert "robo_sv" not in alertas.graves([], AGORA)
    db.salvar_config("shopee_video", {"robo_pausado": False, "robo_inicio": 9, "robo_fim": 21})
    assert "robo_sv" not in alertas.graves([], AGORA.replace(hour=22))


def test_saida_so_com_rotulos(monkeypatch, capsys):
    monkeypatch.setattr(alertas.avisar_rafael, "mandar_texto", lambda texto: True)
    alertas.main(["verificar", "motor_userbot_bot"])
    assert capsys.readouterr().out.strip() == "Graves agora: 1 | motor_userbot_bot fora do ar"

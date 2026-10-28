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
    # Retomado há pouco depois de uma pausa longa: conta da retomada, não da rodada de antes.
    db.salvar_config("shopee_video", {"robo_pausado": False, "robo_inicio": 9, "robo_fim": 21,
                                      "robo_retomado_em": "2026-10-24 14:50:00"})
    assert "robo_sv" not in alertas.graves([], AGORA)
    assert "70 min" in alertas.graves([], AGORA + timedelta(minutes=60))["robo_sv"]


def test_saida_so_com_rotulos(monkeypatch, capsys):
    monkeypatch.setattr(alertas.avisar_rafael, "mandar_texto", lambda texto: True)
    alertas.main(["verificar", "motor_userbot_bot"])
    assert capsys.readouterr().out.strip() == "Graves agora: 1 | motor_userbot_bot fora do ar"


def test_o_bot_confere_so_os_graves_do_servidor_sem_mexer_nos_outros():
    # O GitHub pula boa parte das rodadas do diagnóstico: o bot_mestre confere de hora em hora
    # os robôs fora do ar e o robô da Shopee Vídeo, sem apagar os outros graves já avisados.
    mandados = []

    def mandar(texto):
        mandados.append(texto)
        return True

    db.salvar_config(alertas.CHAVE, {"disco": "2026-10-24 14:00:00"})
    assert alertas.verificar(["downloader_bot"], AGORA, mandar, alertas.GRAVES_DO_SERVIDOR) == ["fora:downloader_bot"]
    assert set(db.ler_config(alertas.CHAVE, {})) == {"disco", "fora:downloader_bot"}
    alertas.verificar([], AGORA + timedelta(hours=1), mandar, alertas.GRAVES_DO_SERVIDOR)
    # O Baixador voltou; o disco, que esta conferência não olha, continua como estava.
    assert mandados[-1] == "✅ Voltou ao normal: downloader_bot fora do ar."
    assert db.ler_config(alertas.CHAVE, {}) == {"disco": "2026-10-24 14:00:00"}


def test_servicos_fora_confere_duas_vezes_e_sem_systemctl_nao_sabe(monkeypatch):
    from types import SimpleNamespace
    parados, esperas = [{"downloader_bot", "motor_userbot_bot"}, {"motor_userbot_bot"}], []

    def run(comando, timeout=30):
        servico = comando[-1].removesuffix(".service")
        return SimpleNamespace(returncode=3 if servico in parados[0] else 0)

    def sleep(segundos):
        esperas.append(segundos)
        parados.pop(0)

    monkeypatch.setattr(alertas.subprocess, "run", run)
    monkeypatch.setattr(alertas.time, "sleep", sleep)
    # O Baixador voltou sozinho na 2ª conferência (o systemd o religou): só o outro está fora.
    assert alertas.servicos_fora() == ["motor_userbot_bot"] and esperas == [alertas.ESPERA_PARA_CONFIRMAR]

    def sem_systemctl(comando, timeout=30):
        raise FileNotFoundError("systemctl")
    monkeypatch.setattr(alertas.subprocess, "run", sem_systemctl)
    assert alertas.servicos_fora() is None


def test_bot_mestre_confere_os_graves_do_servidor_de_hora_em_hora(bm, monkeypatch):
    from conftest import rodar
    chamadas = []
    monkeypatch.setattr(bm.alertas, "servicos_fora", lambda: ["downloader_bot"])
    monkeypatch.setattr(bm.alertas, "verificar", lambda caidos, agora, mandar, so: chamadas.append((caidos, so)) or [])
    rodar(bm.conferir_graves_do_servidor())
    assert chamadas == [(["downloader_bot"], alertas.GRAVES_DO_SERVIDOR)]
    # Sem resposta do systemctl, confere só o robô da Shopee Vídeo: os robôs fora do ar ficam
    # para o diagnóstico (nada de "voltou ao normal" falso).
    monkeypatch.setattr(bm.alertas, "servicos_fora", lambda: None)
    rodar(bm.conferir_graves_do_servidor())
    assert chamadas[-1] == ([], ("robo_sv",))

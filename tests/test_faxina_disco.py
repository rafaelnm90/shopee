"""Faxina do disco do bot_mestre (a cada 6 h): os logs do sistema guardam só os últimos dias."""
import subprocess

from conftest import rodar


def test_faxina_do_disco_apara_o_journal_em_7_dias(bm, monkeypatch):
    # Escolha do Rafael (P42): o journal crescia até o limite do Ubuntu (uns 4 GB).
    chamados = []

    def run(comando, **kw):
        chamados.append(comando)
        return subprocess.CompletedProcess(comando, 0, b"", b"")
    monkeypatch.setattr(bm.subprocess, "run", run)
    monkeypatch.setattr(bm, "limpar_arquivos_orfaos", lambda: (0, 0))
    rodar(bm.faxina_disco_periodica())
    assert chamados == [["sudo", "-n", "journalctl", "--vacuum-time=7d"]]


def test_journal_que_nao_apara_avisa_sem_parar_a_faxina(bm, monkeypatch):
    monkeypatch.setattr(bm.subprocess, "run", lambda comando, **kw: subprocess.CompletedProcess(comando, 1, b"", b""))
    assert bm.aparar_journal() is False

    def sem_sudo(comando, **kw):
        raise FileNotFoundError("sudo")
    monkeypatch.setattr(bm.subprocess, "run", sem_sudo)
    assert bm.aparar_journal() is False

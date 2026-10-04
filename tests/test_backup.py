"""Backup diário: retrato consistente do banco e das sessões, só os 7 mais novos e aviso se falhar."""
import os
import sqlite3
import tarfile

import backup_dados
import db
from conftest import consultar, rodar


def _projeto(pasta):
    """Pasta de projeto com banco em WAL (dado ainda no -wal), sessão, .env e JSON."""
    banco = os.path.join(pasta, "banco_dados.db")
    with db.conexao(banco) as con:
        con.execute("CREATE TABLE t (v TEXT)")
        con.execute("INSERT INTO t VALUES ('gravado agora')")
    sessao = sqlite3.connect(os.path.join(pasta, "conta.session"))
    sessao.execute("CREATE TABLE sessions (dc INTEGER)")
    sessao.execute("INSERT INTO sessions VALUES (2)")
    sessao.commit()
    sessao.close()
    for nome, texto in ((".env", "CHAVE=x\n"), ("espelhos_config.json", "{}")):
        with open(os.path.join(pasta, nome), "w") as f:
            f.write(texto)


def test_pacote_tem_tudo_e_so_o_dono_le(tmp_path):
    projeto, destino = tmp_path / "projeto", tmp_path / "backups"
    projeto.mkdir()
    _projeto(str(projeto))

    caminho, tamanho, removidos = backup_dados.fazer_backup(str(projeto), str(destino))

    assert tamanho > 0 and removidos == 0 and oct(os.stat(caminho).st_mode & 0o777) == "0o600"
    with tarfile.open(caminho) as tar:
        assert sorted(tar.getnames()) == [".env", "banco_dados.db", "conta.session", "espelhos_config.json"]
        tar.extractall(tmp_path / "volta", filter="data")
    banco = sqlite3.connect(tmp_path / "volta" / "banco_dados.db")
    assert banco.execute("SELECT v FROM t").fetchall() == [("gravado agora",)]
    banco.close()
    # A sessão do Telethon continua no modo dela: o backup não a põe em WAL.
    sessao = sqlite3.connect(projeto / "conta.session")
    assert sessao.execute("PRAGMA journal_mode").fetchone()[0] != "wal"
    sessao.close()


def test_ficam_so_os_7_mais_novos(tmp_path):
    projeto, destino = tmp_path / "projeto", tmp_path / "backups"
    projeto.mkdir()
    destino.mkdir()
    _projeto(str(projeto))
    for dia in range(1, 10):
        (destino / f"shopee_backup_2026-09-{dia:02d}_0340.tar.gz").write_bytes(b"velho")

    caminho, _t, removidos = backup_dados.fazer_backup(str(projeto), str(destino))

    restantes = sorted(os.listdir(destino))   # nenhuma sobra da montagem
    assert removidos == 3 and len(restantes) == 7 and restantes[-1] == os.path.basename(caminho)
    assert restantes[0] == "shopee_backup_2026-09-04_0340.tar.gz"
    assert backup_dados.ultimo_backup(str(destino))[0] == caminho


def test_falha_registra_e_avisa_no_privado(bm, monkeypatch):
    avisos = []

    async def send_message(chat, texto, **k):
        avisos.append(texto)
    monkeypatch.setattr(bm.bot, "send_message", send_message)

    def falhar():
        raise OSError("disco cheio")
    monkeypatch.setattr(bm.backup_dados, "fazer_backup", falhar)

    rodar(bm.backup_diario())
    assert len(avisos) == 1 and "backup diário falhou" in avisos[0]
    assert "backup_diario: OSError" in consultar("SELECT erro FROM erros_logs")[0]


def test_robo_sobe_sem_backup_recente_e_agenda_um(bm, monkeypatch, tmp_path):
    monkeypatch.setattr(bm.backup_dados, "DESTINO", str(tmp_path / "backups"))
    bm.agendar_backup_atrasado()
    assert bm.scheduler.get_job("backup_atrasado") is not None

    bm.scheduler.remove_job("backup_atrasado")
    os.makedirs(tmp_path / "backups")
    (tmp_path / "backups" / "shopee_backup_2026-10-03_0340.tar.gz").write_bytes(b"recente")
    bm.agendar_backup_atrasado()
    assert bm.scheduler.get_job("backup_atrasado") is None


def test_sobra_de_backup_interrompido_sai(tmp_path):
    projeto, destino = tmp_path / "projeto", tmp_path / "backups"
    projeto.mkdir()
    _projeto(str(projeto))
    sobra = destino / ".montando_abc"
    sobra.mkdir(parents=True)
    os.utime(sobra, (0, 0))
    backup_dados.fazer_backup(str(projeto), str(destino))
    assert not sobra.exists()

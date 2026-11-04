"""
Backup diário: retrato consistente do banco e das sessões, só os 7 mais novos e aviso se
falhar; e a cópia cifrada no privado do Rafael (P146 1), que só abre com a senha dela.
"""
import glob
import io
import os
import sqlite3
import tarfile
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet, InvalidToken

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

    caminho, tamanho, removidos = backup_dados.fazer_backup(str(projeto), str(destino), casa=str(tmp_path / "casa"))

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

    caminho, _t, removidos = backup_dados.fazer_backup(str(projeto), str(destino), casa=str(tmp_path / "casa"))

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
    assert consultar("SELECT processo, resultado, detalhe, ok FROM registro_processos") == (
        "backup diário", "falhou", "OSError", 0)


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
    backup_dados.fazer_backup(str(projeto), str(destino), casa=str(tmp_path / "casa"))
    assert not sobra.exists()


def _senha_no_tmp(monkeypatch, tmp_path):
    """A senha da cópia numa pasta do teste, nunca no ~/.config de quem roda."""
    monkeypatch.setattr(backup_dados, "CHAVE_DA_COPIA", str(tmp_path / "config" / "backup_fora.chave"))


def test_copia_cifrada_so_abre_com_a_senha_dela(tmp_path, monkeypatch):
    _senha_no_tmp(monkeypatch, tmp_path)
    projeto, destino = tmp_path / "projeto", tmp_path / "backups"
    projeto.mkdir()
    _projeto(str(projeto))
    pacote, _t, _r = backup_dados.fazer_backup(str(projeto), str(destino), casa=str(tmp_path / "casa"))

    senha = backup_dados.chave_da_copia()
    assert backup_dados.chave_da_copia() == senha                 # criada uma vez só
    assert oct(os.stat(backup_dados.CHAVE_DA_COPIA).st_mode & 0o777) == "0o600"
    cifrado = backup_dados.cifrar_copia(pacote)
    assert oct(os.stat(cifrado).st_mode & 0o777) == "0o600"
    with open(cifrado, "rb") as f, open(pacote, "rb") as g:
        conteudo, original = f.read(), g.read()
    assert conteudo != original and Fernet(senha).decrypt(conteudo) == original
    # O pacote cifrado não entra na contagem dos 7 nem passa por backup na idade.
    assert backup_dados.ultimo_backup(str(destino))[0] == pacote

    with pytest.raises(InvalidToken):
        backup_dados.abrir_copia(cifrado, str(tmp_path / "errada"), Fernet.generate_key().decode())
    assert not (tmp_path / "errada").exists()
    nomes = backup_dados.abrir_copia(cifrado, str(tmp_path / "volta"), senha.decode())
    assert nomes == [".env", "banco_dados.db", "conta.session", "espelhos_config.json"]
    banco = sqlite3.connect(tmp_path / "volta" / "banco_dados.db")
    assert banco.execute("SELECT v FROM t").fetchall() == [("gravado agora",)]
    banco.close()


def _bot_falso(bm, monkeypatch, falhar_documento=False):
    """O bot do teste: guarda as mensagens, os arquivos (lidos na hora do envio) e o que apagou."""
    enviados = {"mensagens": [], "documentos": [], "apagados": []}
    ids = iter(range(100, 200))

    async def send_message(chat, texto, **k):
        enviados["mensagens"].append((texto, k.get("reply_markup")))
        return SimpleNamespace(message_id=next(ids))

    async def send_document(chat, documento, **k):
        if falhar_documento:
            raise ConnectionError("rede")
        with open(documento.path, "rb") as f:
            enviados["documentos"].append((f.read(), documento.filename, k))
        return SimpleNamespace(message_id=next(ids))

    async def delete_message(chat, ident):
        enviados["apagados"].append(ident)

    monkeypatch.setattr(bm.bot, "send_message", send_message)
    monkeypatch.setattr(bm.bot, "send_document", send_document)
    monkeypatch.setattr(bm.bot, "delete_message", delete_message)
    return enviados


def _backup_de_teste(bm, monkeypatch, tmp_path):
    projeto, destino = tmp_path / "projeto", tmp_path / "backups"
    projeto.mkdir()
    _projeto(str(projeto))
    original = backup_dados.fazer_backup          # o mesmo módulo: guardar antes de trocar
    monkeypatch.setattr(bm.backup_dados, "fazer_backup",
                        lambda: original(str(projeto), str(destino), casa=str(tmp_path / "casa")))
    return destino


def test_backup_vai_cifrado_ao_privado_e_fica_so_a_copia_mais_nova(bm, monkeypatch, tmp_path):
    _senha_no_tmp(monkeypatch, tmp_path)
    destino = _backup_de_teste(bm, monkeypatch, tmp_path)
    enviados = _bot_falso(bm, monkeypatch)

    rodar(bm.backup_diario())
    rodar(bm.backup_diario())

    # A senha vai uma vez só, com o botão de apagar; cada backup manda a sua cópia, sem som.
    senha = backup_dados.chave_da_copia()
    assert [t for t, _m in enviados["mensagens"] if "Senha da cópia do backup" in t] == [enviados["mensagens"][0][0]]
    assert senha.decode() in enviados["mensagens"][0][0] and len(enviados["mensagens"]) == 1
    assert enviados["mensagens"][0][1].inline_keyboard[0][0].callback_data == "backup_senha_guardada"
    assert len(enviados["documentos"]) == 2
    for conteudo, nome, k in enviados["documentos"]:
        assert nome.endswith(".cifrado") and k["disable_notification"]
        with tarfile.open(fileobj=io.BytesIO(Fernet(senha).decrypt(conteudo))) as tar:
            assert "banco_dados.db" in tar.getnames()
    # A 2ª cópia apaga a 1ª (id 101; o 100 é a senha), e o arquivo cifrado não fica no disco.
    assert enviados["apagados"] == [101]
    estado = db.ler_config(backup_dados.CHAVE_STATUS, {})
    assert estado["mensagem"] == 102 and estado["mensagem_da_chave"] == 100 and estado["tamanho"] > 0
    assert not glob.glob(str(destino / f"*{backup_dados.SUFIXO_CIFRADO}"))
    assert consultar("SELECT COUNT(*) FROM registro_processos WHERE processo = ? AND resultado = 'enviada' AND ok = 1",
                     bm.PROCESSO_DA_COPIA)[0] == 2
    # Na senha não vai nada para o banco além da marca dela.
    assert senha.decode() not in str(estado)


def test_copia_que_nao_sai_avisa_e_nao_deixa_o_arquivo(bm, monkeypatch, tmp_path):
    _senha_no_tmp(monkeypatch, tmp_path)
    destino = _backup_de_teste(bm, monkeypatch, tmp_path)
    enviados = _bot_falso(bm, monkeypatch, falhar_documento=True)

    rodar(bm.backup_diario())

    assert any("cópia do backup não foi" in t for t, _m in enviados["mensagens"])
    assert consultar("SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = ?",
                     bm.PROCESSO_DA_COPIA) == ("falhou", "ConnectionError", 0)
    assert not glob.glob(str(destino / f"*{backup_dados.SUFIXO_CIFRADO}"))
    # O backup do servidor ficou feito.
    assert consultar("SELECT resultado FROM registro_processos WHERE processo = 'backup diário'") == ("feito",)


def test_guardei_a_senha_apaga_a_mensagem_dela(bm):
    apagadas, respostas = [], []

    class Mensagem:
        async def delete(self):
            apagadas.append(True)

    class Clique:
        data = "backup_senha_guardada"
        from_user = SimpleNamespace(id=bm.ADMIN_ID)
        message = Mensagem()

        async def answer(self, texto, **k):
            respostas.append(texto)

    db.salvar_config(backup_dados.CHAVE_STATUS, {"avisado_chave": "x", "mensagem_da_chave": 100})
    rodar(bm.senha_da_copia_guardada(Clique()))
    estado = db.ler_config(backup_dados.CHAVE_STATUS, {})
    assert apagadas and "apagada" in respostas[0]
    assert estado["mensagem_da_chave"] is None and estado["senha_guardada_em"] and estado["avisado_chave"] == "x"


def test_robo_sobe_sem_copia_recente_e_manda_a_do_ultimo_backup(bm, monkeypatch, tmp_path):
    monkeypatch.setattr(bm.backup_dados, "DESTINO", str(tmp_path / "backups"))
    os.makedirs(tmp_path / "backups")
    (tmp_path / "backups" / f"shopee_backup_{datetime.now():%Y-%m-%d_%H%M}.tar.gz").write_bytes(b"recente")

    bm.agendar_copia_atrasada()
    assert bm.scheduler.get_job("copia_do_backup_atrasada") is not None
    bm.scheduler.remove_job("copia_do_backup_atrasada")

    # Com cópia nas últimas 24 h, nada; o /status mostra a idade dela.
    db.salvar_config(backup_dados.CHAVE_STATUS, {"enviada_em": (datetime.now(bm.fuso_horario) - timedelta(hours=3))
                                                 .strftime("%Y-%m-%d %H:%M:%S")})
    bm.agendar_copia_atrasada()
    assert bm.scheduler.get_job("copia_do_backup_atrasada") is None
    assert bm.linha_da_copia_fora() == "🔐 Cópia do backup no seu privado: há 3 h"


def test_sem_copia_ainda_o_status_avisa(bm):
    assert bm.linha_da_copia_fora() == "⚠️ Cópia do backup no seu privado: ainda não saiu"


def test_chaves_de_fora_do_projeto_vao_no_pacote_e_voltam_ao_lugar(tmp_path, monkeypatch):
    # P147 1: a chave das cópias cifradas e a do adb (o celular do robô já a reconhece) vão no
    # pacote e voltam à casa do usuário no servidor novo, só o dono lendo.
    _senha_no_tmp(monkeypatch, tmp_path)
    projeto, destino, casa = tmp_path / "projeto", tmp_path / "backups", tmp_path / "casa"
    projeto.mkdir()
    _projeto(str(projeto))
    for relativo, conteudo in ((".config/registro_admins.chave", b"chave do registro"),
                               (".android/adbkey", b"chave do adb"), (".android/adbkey.pub", b"publica")):
        (casa / relativo).parent.mkdir(parents=True, exist_ok=True)
        (casa / relativo).write_bytes(conteudo)
    (casa / ".config" / "outra_coisa").write_bytes(b"fica de fora")

    pacote, _t, _r = backup_dados.fazer_backup(str(projeto), str(destino), casa=str(casa))
    with tarfile.open(pacote) as tar:
        nomes = tar.getnames()
    assert "fora_do_projeto/.config/registro_admins.chave" in nomes and "fora_do_projeto/.android/adbkey" in nomes
    assert not any("outra_coisa" in n or "backup_fora" in n for n in nomes)   # a senha da cópia não vai

    cifrado = backup_dados.cifrar_copia(pacote)
    nova_casa = tmp_path / "servidor_novo"
    backup_dados.abrir_copia(cifrado, str(tmp_path / "volta"), backup_dados.chave_da_copia().decode(),
                             casa=str(nova_casa))
    assert (nova_casa / ".android" / "adbkey").read_bytes() == b"chave do adb"
    assert (nova_casa / ".config" / "registro_admins.chave").read_bytes() == b"chave do registro"
    assert oct(os.stat(nova_casa / ".android" / "adbkey").st_mode & 0o777) == "0o600"
    assert not (tmp_path / "volta" / "fora_do_projeto").exists()   # nada disso fica na pasta do projeto
    assert (tmp_path / "volta" / "banco_dados.db").exists()


def test_pacote_com_nome_estranho_em_fora_do_projeto_nao_escreve_na_casa(tmp_path):
    # Só os nomes da lista voltam à casa: um pacote com outro caminho não escreve fora dela.
    pacote = tmp_path / "pacote.tar.gz"
    origem = tmp_path / "estranho"
    origem.write_bytes(b"x")
    with tarfile.open(pacote, "w:gz") as tar:
        tar.add(origem, arcname="fora_do_projeto/.bashrc")
        tar.add(origem, arcname="fora_do_projeto/../../fora.txt")
    casa = tmp_path / "casa"
    with open(pacote, "rb") as arquivo:
        backup_dados.abrir_pacote(arquivo, str(tmp_path / "projeto"), casa=str(casa))
    assert not (casa / ".bashrc").exists() and not (tmp_path / "fora.txt").exists()

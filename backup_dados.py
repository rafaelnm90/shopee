"""
Backup diário do que o git não guarda: o banco_dados.db, as sessões do Telethon
(*.session), as configurações em JSON da pasta do projeto e o .env.

O bot_mestre roda todo dia às 03:40 e avisa no privado se falhar. À mão:
python3 backup_dados.py.

Cada backup vira ~/backups/shopee_backup_AAAA-MM-DD_HHMM.tar.gz, fora do
repositório e com permissão só do dono (tem o .env e as sessões). Ficam os 7
mais recentes.

Banco e sessões são SQLite: a cópia sai pelo backup do próprio SQLite
(db.copiar_sqlite), que pega um retrato consistente mesmo com os robôs gravando.
No modo WAL, o retrato já inclui o que ainda está no -wal.

Para restaurar: parar os robôs, extrair o pacote na pasta do projeto e subir de
novo. Banco e .env bastam para as contas do pool (a sessão delas fica cifrada no
banco); os *.session são as contas principais dos userbots.
"""
import glob
import os
import shutil
import sys
import tarfile
import tempfile
import time
from datetime import datetime

import db

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
DESTINO = os.path.expanduser("~/backups")
MANTER = 7
PREFIXO = "shopee_backup_"
MONTAGEM = ".montando_"


def _arquivos(pasta):
    """(arquivos SQLite, arquivos comuns) a guardar, só os que existem."""
    sqlite = [os.path.join(pasta, "banco_dados.db")] + sorted(glob.glob(os.path.join(pasta, "*.session")))
    comuns = [os.path.join(pasta, ".env")] + sorted(glob.glob(os.path.join(pasta, "*.json")))
    return [a for a in sqlite if os.path.isfile(a)], [a for a in comuns if os.path.isfile(a)]


def _limpar_sobras(destino):
    """Pastas de montagem largadas por um backup interrompido (robô morto no meio)."""
    for sobra in glob.glob(os.path.join(destino, f"{MONTAGEM}*")):
        if time.time() - os.path.getmtime(sobra) > 3600:
            shutil.rmtree(sobra, ignore_errors=True)


def fazer_backup(pasta=None, destino=None, manter=MANTER):
    """
    Cria o pacote e apaga os mais antigos que os `manter` mais recentes.
    Devolve (caminho do pacote, tamanho em bytes, quantos antigos saíram).
    """
    pasta, destino = pasta or PASTA_PROJETO, destino or DESTINO
    sqlite, comuns = _arquivos(pasta)
    if not sqlite and not comuns:
        raise FileNotFoundError(f"nada para guardar em {pasta}")

    os.makedirs(destino, mode=0o700, exist_ok=True)
    _limpar_sobras(destino)
    pacote = os.path.join(destino, f"{PREFIXO}{datetime.now():%Y-%m-%d_%H%M}.tar.gz")
    # Tudo é montado numa pasta temporária ao lado (mesmo disco) e o pacote só
    # aparece com o nome final quando está inteiro: um backup cortado no meio
    # (disco cheio, robô reiniciado) nunca ocupa o lugar de um bom na contagem dos 7.
    with tempfile.TemporaryDirectory(dir=destino, prefix=MONTAGEM) as temp:
        copias = os.path.join(temp, "arquivos")
        os.makedirs(copias)
        for arquivo in sqlite:
            db.copiar_sqlite(arquivo, os.path.join(copias, os.path.basename(arquivo)))
        for arquivo in comuns:
            shutil.copy2(arquivo, copias)
        parcial = os.path.join(temp, "pacote.tar.gz")
        with tarfile.open(parcial, "w:gz") as tar:
            for nome in sorted(os.listdir(copias)):
                tar.add(os.path.join(copias, nome), arcname=nome)
        os.chmod(parcial, 0o600)
        os.replace(parcial, pacote)

    # O nome tem a data em ordem de calendário: ordem alfabética = ordem de idade.
    antigos = sorted(glob.glob(os.path.join(destino, f"{PREFIXO}*.tar.gz")))[:-manter]
    for velho in antigos:
        os.remove(velho)
    return pacote, os.path.getsize(pacote), len(antigos)


def ultimo_backup(destino=None):
    """(caminho, idade em horas, tamanho em bytes) do backup mais novo, ou None."""
    pacotes = sorted(glob.glob(os.path.join(destino or DESTINO, f"{PREFIXO}*.tar.gz")))
    if not pacotes:
        return None
    caminho = pacotes[-1]
    idade_h = (datetime.now().timestamp() - os.path.getmtime(caminho)) / 3600
    return caminho, idade_h, os.path.getsize(caminho)


if __name__ == "__main__":
    try:
        caminho, tamanho, removidos = fazer_backup()
    except Exception as e:
        print(f"❌ Backup falhou: {type(e).__name__}: {e}")
        sys.exit(1)
    print(f"✅ Backup criado: {caminho} ({tamanho / 1024 / 1024:.1f} MB)")
    if removidos:
        print(f"🧹 {removidos} backup(s) antigo(s) removido(s); ficam os {MANTER} mais recentes.")

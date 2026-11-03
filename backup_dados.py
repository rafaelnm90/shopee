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

Cópia fora do servidor, pedido do Rafael (P146 1): DECISOES.md, Monitor, deploy e servidor.
O pacote fica no mesmo servidor e se perderia junto com ele. Depois de
cada backup, o bot_mestre manda o pacote cifrado (cifrar_copia) no privado do
Rafael; lá fica só a mais nova. A senha da cópia (CHAVE_DA_COPIA) é própria: o
servidor a cria na primeira vez, o bot a manda uma vez ao Rafael, que a guarda fora
do Telegram, e ela nunca vai para o banco, o log ou o git. Para restaurar num
servidor novo: baixar o arquivo do privado, parar os robôs e rodar

    python3 backup_dados.py abrir ARQUIVO PASTA_DO_PROJETO

que pede a senha (ou a lê da variável BACKUP_CHAVE, ou do arquivo da senha, se o
servidor ainda o tem).
"""
import getpass
import glob
import io
import os
import shutil
import sys
import tarfile
import tempfile
import time
from datetime import datetime

from cryptography.fernet import Fernet

import db
import registro_privado

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
DESTINO = os.path.expanduser("~/backups")
MANTER = 7
PREFIXO = "shopee_backup_"
MONTAGEM = ".montando_"

# A cópia fora do servidor: a senha, o estado no banco (só ids, datas e tamanhos) e o
# limite do Telegram para arquivo mandado por bot (50 MB; a cifra cresce o pacote em 1/3).
CHAVE_DA_COPIA = os.path.expanduser("~/.config/backup_fora.chave")
VARIAVEL_DA_CHAVE = "BACKUP_CHAVE"
CHAVE_STATUS = "backup_fora_do_servidor"
SUFIXO_CIFRADO = ".cifrado"
LIMITE_DA_COPIA = 49 * 1024 * 1024


def _arquivos(pasta):
    """(arquivos SQLite, arquivos comuns) a guardar, só os que existem."""
    sqlite = [os.path.join(pasta, "banco_dados.db")] + sorted(glob.glob(os.path.join(pasta, "*.session")))
    comuns = [os.path.join(pasta, ".env")] + sorted(glob.glob(os.path.join(pasta, "*.json")))
    return [a for a in sqlite if os.path.isfile(a)], [a for a in comuns if os.path.isfile(a)]


def _limpar_sobras(destino):
    """
    Pastas de montagem largadas por um backup interrompido (robô morto no meio) e a cópia
    cifrada que ficou para trás (o bot apaga a dele depois de mandar).
    """
    for sobra in glob.glob(os.path.join(destino, f"{MONTAGEM}*")):
        if time.time() - os.path.getmtime(sobra) > 3600:
            shutil.rmtree(sobra, ignore_errors=True)
    for sobra in glob.glob(os.path.join(destino, f"{PREFIXO}*{SUFIXO_CIFRADO}")):
        if time.time() - os.path.getmtime(sobra) > 3600:
            os.remove(sobra)


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


def chave_da_copia():
    """A senha da cópia fora do servidor, criada na primeira vez (só o dono lê o arquivo)."""
    return registro_privado.chave(CHAVE_DA_COPIA)


def cifrar_copia(pacote, valor_chave=None):
    """
    O pacote cifrado com a senha da cópia, ao lado dele (pacote + .cifrado, só o dono lê).
    Devolve o caminho; quem manda apaga depois do envio.
    """
    with open(pacote, "rb") as arquivo:
        cifrado = Fernet(valor_chave or chave_da_copia()).encrypt(arquivo.read())
    caminho = pacote + SUFIXO_CIFRADO
    descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descritor, "wb") as arquivo:
        arquivo.write(cifrado)
    return caminho


def abrir_copia(arquivo_cifrado, pasta, valor_chave):
    """
    Restaura a cópia: decifra e extrai os arquivos em `pasta` (a do projeto, com os robôs
    parados). Senha errada = InvalidToken, sem tocar na pasta. Devolve os nomes extraídos.
    """
    with open(arquivo_cifrado, "rb") as arquivo:
        pacote = Fernet(valor_chave.strip()).decrypt(arquivo.read().strip())
    os.makedirs(pasta, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(pacote), mode="r:gz") as tar:
        nomes = sorted(tar.getnames())
        tar.extractall(pasta, filter="data")
    return nomes


def _senha_para_abrir():
    """A senha para abrir a cópia: a variável BACKUP_CHAVE, o arquivo do servidor ou digitada."""
    if os.environ.get(VARIAVEL_DA_CHAVE):
        return os.environ[VARIAVEL_DA_CHAVE]
    if os.path.isfile(CHAVE_DA_COPIA):
        with open(CHAVE_DA_COPIA, "rb") as arquivo:
            return arquivo.read().decode("ascii")
    return getpass.getpass("Senha da cópia do backup: ")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "abrir":
        try:
            extraidos = abrir_copia(sys.argv[2], sys.argv[3], _senha_para_abrir())
        except Exception as e:
            print(f"❌ A cópia não abriu: {type(e).__name__} (senha errada ou arquivo incompleto)")
            sys.exit(1)
        print(f"✅ {len(extraidos)} arquivo(s) em {sys.argv[3]}: {', '.join(extraidos)}")
        sys.exit(0)
    try:
        caminho, tamanho, removidos = fazer_backup()
    except Exception as e:
        print(f"❌ Backup falhou: {type(e).__name__}: {e}")
        sys.exit(1)
    print(f"✅ Backup criado: {caminho} ({tamanho / 1024 / 1024:.1f} MB)")
    if removidos:
        print(f"🧹 {removidos} backup(s) antigo(s) removido(s); ficam os {MANTER} mais recentes.")

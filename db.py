"""
Acesso ao banco_dados.db, o SQLite que os cinco robôs dividem. Toda conexão do
projeto sai daqui; o tests/test_db.py barra sqlite3.connect em outro arquivo.

- conectar(): conexão pronta (espera até 30 s pelo lock, banco em modo WAL).
  Quem abre fecha.
- conexao(): a mesma conexão num with, que grava (commit) no fim, desfaz
  (rollback) se der erro e fecha sempre, com ou sem erro. Prefira esta em código novo.
- ler_config() e salvar_config(): a tabela configuracoes (chave -> JSON).
- atualizar_config(): lê, altera e grava uma chave sem perder a gravação de
  outro robô que mexa na mesma chave ao mesmo tempo.
- copiar_sqlite(): cópia consistente de um arquivo SQLite, para o backup.

Por que WAL: no modo padrão do SQLite, quem está lendo impede quem quer gravar
de concluir a gravação. Os robôs leem um item da fila e seguram essa leitura
enquanto mandam o vídeo ao Telegram, o que pode levar minutos. Nesse tempo, a
gravação de outro robô esperava, estourava o prazo e dava "database is locked".
No WAL, leitura e gravação não se bloqueiam; só duas gravações ao mesmo tempo
esperam uma pela outra (até os 30 s).

O modo WAL fica gravado no próprio arquivo do banco, e o banco passa a ter dois
arquivos ao lado (banco_dados.db-wal e banco_dados.db-shm). Eles fazem parte do
banco: não apague com os robôs rodando. O backup diário (backup_dados.py) copia
pelo backup do próprio SQLite, que já inclui o que está no -wal.
"""
import json
import logging
import os
import sqlite3
from contextlib import contextmanager

ARQUIVO_BANCO = "banco_dados.db"

# Quanto uma gravação espera a outra terminar antes de desistir com "database is
# locked". O padrão do Python é 5 s, curto para cinco robôs no mesmo banco.
ESPERA_LOCK_S = 30

logger = logging.getLogger(__name__)

_connect_original = sqlite3.connect


def _connect_com_espera(*args, **kwargs):
    kwargs.setdefault("timeout", float(ESPERA_LOCK_S))
    conexao = _connect_original(*args, **kwargs)
    try:
        conexao.execute(f"PRAGMA busy_timeout = {ESPERA_LOCK_S * 1000}")
    except Exception:
        pass
    return conexao


# O que abre SQLite por conta própria, como as sessões .session do Telethon,
# também espera os 30 s. Vale para todo processo que importa este módulo.
sqlite3.connect = _connect_com_espera

# Arquivos já postos em WAL neste processo: o modo fica gravado no banco, basta
# pedir uma vez. Caminho absoluto, porque os testes trocam de pasta a cada teste.
_arquivos_em_wal = set()


def _garantir_wal(conexao, arquivo):
    caminho = os.path.abspath(arquivo)
    if caminho in _arquivos_em_wal:
        return
    try:
        modo = conexao.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        _arquivos_em_wal.add(caminho)
        if modo.lower() != "wal":
            logger.warning(f"⚠️ [Banco] {arquivo} ficou em modo {modo}, não WAL.")
    except sqlite3.Error as e:
        # Sem WAL o banco funciona como antes; tenta de novo na próxima conexão.
        logger.warning(f"⚠️ [Banco] Não foi possível ativar o WAL em {arquivo}: {e}")


def conectar(arquivo=None, linhas_por_nome=False):
    """
    Conexão ao banco (por padrão o banco_dados.db). Quem chama fecha.

    linhas_por_nome=True devolve linhas que aceitam linha["coluna"] (sqlite3.Row).
    """
    arquivo = arquivo or ARQUIVO_BANCO
    conexao = _connect_com_espera(arquivo)
    _garantir_wal(conexao, arquivo)
    if linhas_por_nome:
        conexao.row_factory = sqlite3.Row
    return conexao


@contextmanager
def conexao(arquivo=None, linhas_por_nome=False):
    """
    Conexão que grava no fim, desfaz se der erro e fecha sempre:

        with db.conexao() as conexao:
            conexao.execute("UPDATE ...", (...))

    Fechar só no fim do try deixa a conexão aberta quando algo estoura no meio, e
    uma gravação já feita segura o lock até o coletor de lixo passar.
    """
    con = conectar(arquivo, linhas_por_nome)
    try:
        yield con
        con.commit()
    except BaseException:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            con.close()
        except Exception:
            pass


def ler_config(chave, padrao=None, arquivo_legado=None):
    """
    Valor (JSON) da chave na tabela configuracoes; padrao se não houver ou der erro.

    Com arquivo_legado e sem a chave no banco, migra o JSON antigo: grava no banco e
    renomeia o arquivo para .bkp. Não usar com arquivo que outro serviço ainda grava:
    a gravação que chegar depois da migração fica no arquivo e se perde (a fila do
    Espelhador fez a passagem pelo fila_espelhador.passar_arquivo_para_o_banco).
    """
    if padrao is None:
        padrao = {}
    try:
        with conexao() as con:
            linha = con.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,)).fetchone()
        if linha:
            return json.loads(linha[0])

        if arquivo_legado and os.path.exists(arquivo_legado):
            with open(arquivo_legado, "r", encoding="utf-8") as f:
                dados_antigos = json.load(f)
            salvar_config(chave, dados_antigos)
            os.rename(arquivo_legado, arquivo_legado + ".bkp")
            logger.info(f"📦 [Banco] '{arquivo_legado}' migrado para a chave '{chave}'.")
            return dados_antigos

        return padrao
    except Exception as e:
        logger.error(f"❌ [Banco] Erro ao ler a configuração '{chave}': {e}")
        return padrao


def salvar_config(chave, dados):
    """Grava dados como JSON na chave da tabela configuracoes. True se gravou."""
    try:
        with conexao() as con:
            con.execute(
                "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
                (chave, json.dumps(dados, ensure_ascii=False)),
            )
        return True
    except Exception as e:
        logger.error(f"❌ [Banco] Erro ao salvar a configuração '{chave}': {e}")
        return False


def atualizar_config(chave, alterar, padrao=None):
    """
    Lê a chave, chama alterar(dados) e grava, tudo numa transação só.

    O BEGIN IMMEDIATE pega o lock de gravação antes da leitura: se outro robô
    grava a mesma chave no meio, ele espera, em vez de uma gravação apagar a
    outra. alterar muda os dados no lugar e devolve o que quiser repassar a
    quem chamou. Devolve esse retorno, ou None se der erro.
    """
    try:
        with conexao() as con:
            con.execute("BEGIN IMMEDIATE")
            linha = con.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,)).fetchone()
            dados = json.loads(linha[0]) if linha else ({} if padrao is None else padrao)
            resultado = alterar(dados)
            con.execute(
                "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
                (chave, json.dumps(dados, ensure_ascii=False)),
            )
        return resultado
    except Exception as e:
        logger.error(f"❌ [Banco] Erro ao atualizar a configuração '{chave}': {e}")
        return None


def ler_sqlite(arquivo, sql, parametros=()):
    """
    Consulta só de leitura num SQLite que não é o banco (ex.: um .session antigo do
    Telethon). Abre em modo ro: não muda o modo de diário nem grava nada no arquivo.
    """
    conexao = _connect_com_espera(f"file:{os.path.abspath(arquivo)}?mode=ro", uri=True)
    try:
        return conexao.execute(sql, parametros).fetchall()
    finally:
        conexao.close()


def copiar_sqlite(origem, destino):
    """
    Copia um arquivo SQLite (o banco ou uma sessão do Telethon) para destino pelo
    backup do próprio SQLite: um retrato consistente mesmo com outro robô
    gravando, ao contrário de um cp. Abre a origem só para leitura e sem mudar o
    modo dela (as sessões do Telethon não ficam em WAL).
    """
    fonte = _connect_com_espera(f"file:{os.path.abspath(origem)}?mode=ro", uri=True)
    try:
        alvo = _connect_original(destino)
        try:
            fonte.backup(alvo)
        finally:
            alvo.close()
    finally:
        fonte.close()

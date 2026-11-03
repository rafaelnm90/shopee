"""
O passo de cada fluxo dos painéis do bot_mestre (o FSM do aiogram) guardado também no
banco. O bot reinicia a cada atualização que mexe no código dele (uns 20 por dia), e no
MemoryStorage o passo em que o Rafael estava (digitando uma configuração, cadastrando algo)
se perdia: depois do reinício, o bot continua de onde ele parou. Pedido do Rafael (P146 3):
DECISOES.md, Código e manutenção.

Enquanto o bot roda, tudo funciona como no MemoryStorage (a mesma memória, os mesmos
objetos); cada mudança de passo ou de dados é gravada também na tabela fsm_passos, e uma
chave que não está na memória (o bot acabou de subir) é lida de lá. Só as chaves que o
bot pede (guardar: o privado do Rafael) vão ao banco; as outras, como as sessões da
submissão pública nos grupos, que o bot encerra ao subir, ficam só na memória. Os dados vão em
pickle, que guarda os tipos como estão (tupla, número como chave, data); o valor que não
vira pickle (um objeto ligado ao bot) fica só na memória, como antes. O pickle só lê o
que o próprio bot gravou no banco do servidor. Passo parado há mais de HORAS_GUARDADO
não volta.

Usado pelo bot_mestre (Dispatcher(storage=ArmazemNoBanco())), que chama a faxina ao subir.
"""
import logging
import pickle
from datetime import datetime, timedelta

from aiogram.fsm.storage.memory import MemoryStorage, MemoryStorageRecord

import db
from fuso import fuso_horario

logger = logging.getLogger(__name__)

TABELA = "fsm_passos"
HORAS_GUARDADO = 24


def _agora(agora=None):
    return (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d %H:%M:%S")


def _chave(key):
    """A chave do aiogram (bot, chat, usuário, tópico, conta comercial e destino) em texto."""
    return ":".join(str(parte) for parte in (key.bot_id, key.chat_id, key.user_id, key.thread_id,
                                             key.business_connection_id, key.destiny))


def _criar_tabela(con):
    con.execute(f"CREATE TABLE IF NOT EXISTS {TABELA} (chave TEXT PRIMARY KEY, estado TEXT, dados BLOB, "
                "atualizado TEXT)")


def _dados_que_guardam(chave, dados):
    """Os dados em pickle; o valor que não vira pickle fica de fora (só na memória)."""
    try:
        return pickle.dumps(dict(dados))
    except Exception:
        pass
    guardaveis, fora = {}, []
    for nome, valor in dados.items():
        try:
            pickle.dumps(valor)
            guardaveis[nome] = valor
        except Exception:
            fora.append(str(nome))
    logger.warning(f"⚠️ [FSM] Dados que não vão ao banco (ficam só na memória): {', '.join(fora)}")
    return pickle.dumps(guardaveis)


def faxina(agora=None):
    """Tira os passos parados há mais de HORAS_GUARDADO (o bot chama ao subir)."""
    corte = _agora((agora or datetime.now(fuso_horario)) - timedelta(hours=HORAS_GUARDADO))
    with db.conexao() as con:
        _criar_tabela(con)
        return con.execute(f"DELETE FROM {TABELA} WHERE atualizado < ?", (corte,)).rowcount


class ArmazemNoBanco(MemoryStorage):
    """
    O MemoryStorage do aiogram com cada passo gravado também no banco (fsm_passos).
    guardar(key) diz quais chaves vão ao banco (sem ele, todas).
    """

    def __init__(self, guardar=None):
        super().__init__()
        self._guardar = guardar or (lambda key: True)
        self._lidas = set()

    def _carregar(self, key, agora=None):
        """A chave que não está na memória (o bot acabou de subir) vem do banco, uma vez."""
        if key in self.storage or key in self._lidas or not self._guardar(key):
            return
        self._lidas.add(key)
        corte = _agora((agora or datetime.now(fuso_horario)) - timedelta(hours=HORAS_GUARDADO))
        try:
            with db.conexao() as con:
                _criar_tabela(con)
                linha = con.execute(f"SELECT estado, dados FROM {TABELA} WHERE chave = ? AND atualizado >= ?",
                                    (_chave(key), corte)).fetchone()
            if not linha:
                return
            dados = pickle.loads(linha[1]) if linha[1] else {}
            self.storage[key] = MemoryStorageRecord(data=dados if isinstance(dados, dict) else {}, state=linha[0])
        except Exception as e:
            # Banco ocupado ou dado de uma versão velha do código: segue sem o passo, como antes.
            logger.warning(f"⚠️ [FSM] Passo guardado não voltou ({type(e).__name__}).")

    def _gravar(self, key, agora=None):
        """Grava o passo da chave como está na memória; sem passo nem dados, apaga."""
        if not self._guardar(key):
            return
        registro = self.storage.get(key)
        chave = _chave(key)
        try:
            with db.conexao() as con:
                _criar_tabela(con)
                if registro is None or (registro.state is None and not registro.data):
                    con.execute(f"DELETE FROM {TABELA} WHERE chave = ?", (chave,))
                    return
                con.execute(f"INSERT INTO {TABELA} (chave, estado, dados, atualizado) VALUES (?, ?, ?, ?) "
                            "ON CONFLICT(chave) DO UPDATE SET estado = excluded.estado, dados = excluded.dados, "
                            "atualizado = excluded.atualizado",
                            (chave, registro.state, _dados_que_guardam(chave, registro.data), _agora(agora)))
        except Exception as e:
            # O passo continua na memória: só um reinício agora o perderia, como antes.
            logger.warning(f"⚠️ [FSM] Passo não foi gravado no banco ({type(e).__name__}).")

    async def set_state(self, key, state=None):
        self._carregar(key)
        await super().set_state(key, state)
        self._gravar(key)

    async def get_state(self, key):
        self._carregar(key)
        return await super().get_state(key)

    async def set_data(self, key, data):
        self._carregar(key)
        await super().set_data(key, data)
        self._gravar(key)

    async def get_data(self, key):
        self._carregar(key)
        return await super().get_data(key)

    async def get_value(self, storage_key, dict_key, default=None):
        self._carregar(storage_key)
        return await super().get_value(storage_key, dict_key, default)

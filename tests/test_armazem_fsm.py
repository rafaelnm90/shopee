"""O passo dos fluxos do privado do Rafael também no banco (P146 3): volta depois do reinício do bot."""
import threading
from datetime import datetime, timedelta

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey

import armazem_fsm
from conftest import consultar, inserir, rodar
from fuso import fuso_horario

RAFAEL = StorageKey(bot_id=1, chat_id=10, user_id=10)
GRUPO = StorageKey(bot_id=1, chat_id=-100, user_id=20)


class Fluxo(StatesGroup):
    horario = State()


def _so_o_privado(key):
    return key.chat_id == key.user_id == 10


def _contexto(key, armazem=None):
    return FSMContext(storage=armazem or armazem_fsm.ArmazemNoBanco(guardar=_so_o_privado), key=key)


def test_passo_volta_depois_do_reinicio_com_os_tipos_de_antes():
    estado = _contexto(RAFAEL)
    quando = datetime(2026, 11, 3, 17, 0, tzinfo=fuso_horario)
    rodar(estado.set_state(Fluxo.horario))
    rodar(estado.update_data(faixa=(8, 12), mapa={5: "cinco"}, quando=quando, painel_atual="robo"))

    estado = _contexto(RAFAEL)                     # o bot subiu de novo: memória vazia
    assert rodar(estado.get_state()) == Fluxo.horario.state
    assert rodar(estado.get_data()) == {"faixa": (8, 12), "mapa": {5: "cinco"}, "quando": quando,
                                        "painel_atual": "robo"}
    assert rodar(estado.get_value("faixa")) == (8, 12)
    # Mudar o passo depois do reinício guarda os dados que voltaram.
    rodar(estado.set_state(None))
    assert rodar(_contexto(RAFAEL).get_data())["painel_atual"] == "robo"

    # Limpo (Cancelar, Painel Inicial), sai do banco.
    rodar(_contexto(RAFAEL).clear())
    assert consultar("SELECT COUNT(*) FROM fsm_passos")[0] == 0
    assert rodar(_contexto(RAFAEL).get_state()) is None


def test_sessao_da_submissao_no_grupo_fica_so_na_memoria():
    armazem_fsm.faxina()
    armazem = armazem_fsm.ArmazemNoBanco(guardar=_so_o_privado)
    rodar(_contexto(GRUPO, armazem).set_state(Fluxo.horario))
    assert rodar(_contexto(GRUPO, armazem).get_state()) == Fluxo.horario.state
    assert consultar("SELECT COUNT(*) FROM fsm_passos")[0] == 0
    assert rodar(_contexto(GRUPO).get_state()) is None


def test_valor_que_nao_vira_pickle_fica_so_na_memoria():
    armazem = armazem_fsm.ArmazemNoBanco(guardar=_so_o_privado)
    trava = threading.Lock()
    rodar(_contexto(RAFAEL, armazem).update_data(trava=trava, texto="ok"))
    assert rodar(_contexto(RAFAEL, armazem).get_data())["trava"] is trava   # como no MemoryStorage
    assert rodar(_contexto(RAFAEL).get_data()) == {"texto": "ok"}


def test_passo_parado_ha_mais_de_um_dia_nao_volta_e_sai_na_faxina():
    rodar(_contexto(RAFAEL).set_state(Fluxo.horario))
    velho = (datetime.now(fuso_horario) - timedelta(hours=armazem_fsm.HORAS_GUARDADO + 1)).strftime("%Y-%m-%d %H:%M:%S")
    inserir("UPDATE fsm_passos SET atualizado = ?", velho)
    assert rodar(_contexto(RAFAEL).get_state()) is None
    assert armazem_fsm.faxina() == 1
    assert consultar("SELECT COUNT(*) FROM fsm_passos")[0] == 0


def test_passo_estragado_no_banco_nao_derruba_o_bot():
    armazem_fsm.faxina()
    agora = datetime.now(fuso_horario).strftime("%Y-%m-%d %H:%M:%S")
    inserir("INSERT INTO fsm_passos VALUES (?, ?, ?, ?)", armazem_fsm._chave(RAFAEL), Fluxo.horario.state,
            b"isso nao e pickle", agora)
    estado = _contexto(RAFAEL)
    assert rodar(estado.get_state()) is None and rodar(estado.get_data()) == {}


def test_bot_guarda_no_banco_so_o_privado_do_rafael(bm):
    assert isinstance(bm.dp.storage, armazem_fsm.ArmazemNoBanco)
    guardar = bm.dp.storage._guardar
    assert guardar(StorageKey(bot_id=1, chat_id=bm.ADMIN_ID, user_id=bm.ADMIN_ID))
    assert not guardar(StorageKey(bot_id=1, chat_id=-100123, user_id=bm.ADMIN_ID))   # ele num grupo
    assert not guardar(StorageKey(bot_id=1, chat_id=555, user_id=555))                # outra pessoa

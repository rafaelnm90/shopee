"""motor_userbot.py: mensagem de canal a que a conta perdeu o acesso não vira erro no Espião nem no Espelhador."""
from telethon.errors import ChannelPrivateError

import motor_userbot as mu
from conftest import rodar


class EventoSemAcesso:
    async def get_chat(self):
        raise ChannelPrivateError(request=None)


def test_canal_sem_acesso_e_ignorado_sem_erro():
    # Checkup de 23/10: o ChannelPrivateError no get_chat virava rastro de erro no log,
    # 12 vezes num dia.
    assert rodar(mu.interceptar_mensagem(EventoSemAcesso())) is None
    assert rodar(mu.motor_espelhador_userbot(EventoSemAcesso())) is None

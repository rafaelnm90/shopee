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


def test_falha_no_disparo_do_espelhador_diz_em_que_passo_aconteceu():
    # Checkup de 26/10: "desistiu após 3 tentativas - ValueError" não dizia onde. Cada passo
    # do disparo tem um rótulo fixo, que vai ao registro junto com o tipo do erro.
    import inspect
    import re
    fonte = inspect.getsource(mu.processar_fila_espelhador_loop)
    assert re.findall(r'etapa = "([^"]+)"', fonte) == [
        "ler a origem", "baixar o vídeo", "renovar o link", "legenda da IA", "achar o destino", "enviar ao destino"]
    assert fonte.count('f"{type(erro_disparo).__name__} em {etapa}"') == 2

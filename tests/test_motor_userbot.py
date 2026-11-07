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


def test_ultima_mensagem_de_cada_grupo_vigiado_vai_ao_banco(monkeypatch):
    # Checkup de 06/11/2026: do grupo que parou de mandar vídeo, o checkup diz se ainda chega
    # mensagem dele. O motor anota na memória a última mensagem de cada grupo (pelo apelido do
    # registro) e grava no banco de tempos em tempos, juntando com o que já estava.
    import db
    import registro_processos as rp
    from conftest import inserir
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    mu._ultimas_mensagens["espiao"].clear()
    mu._ultimas_mensagens["espelhador"].clear()
    mu.anotar_mensagem_da_origem("espiao", "@GrupoA")
    mu.anotar_mensagem_da_origem("espelhador", "-1009:5")
    mu.gravar_ultimas_mensagens()
    dados = db.ler_config(mu.CHAVE_DAS_ULTIMAS_MENSAGENS, {})
    assert set(dados["espiao"]) == {rp.apelido("@grupoa")} and set(dados["espelhador"]) == {rp.apelido("-1009:5")}
    assert dados["desde"] and mu._ultimas_mensagens == {"espiao": {}, "espelhador": {}}
    mu.anotar_mensagem_da_origem("espiao", "@GrupoB")
    mu.gravar_ultimas_mensagens()
    dados_depois = db.ler_config(mu.CHAVE_DAS_ULTIMAS_MENSAGENS, {})
    assert set(dados_depois["espiao"]) == {rp.apelido("@grupoa"), rp.apelido("@grupob")}
    assert dados_depois["desde"] == dados["desde"]
    # Sem nada novo, nada muda; com o banco falhando, o anotado fica para a próxima.
    mu.gravar_ultimas_mensagens()
    mu.anotar_mensagem_da_origem("espiao", "@GrupoC")
    monkeypatch.setattr(mu.db, "atualizar_config", lambda chave, alterar, padrao=None: None)
    mu.gravar_ultimas_mensagens()
    assert set(mu._ultimas_mensagens["espiao"]) == {rp.apelido("@grupoc")}
    mu._ultimas_mensagens["espiao"].clear()

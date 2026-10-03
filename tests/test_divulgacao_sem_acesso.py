"""Divulgação: alvo a que a conta perdeu o acesso fica pausado, avisa uma vez e volta pelo botão."""
import asyncio
from types import SimpleNamespace

import pytest
from telethon.errors import ChannelPrivateError

import alvos_sem_acesso
import db
from conftest import consultar, rodar

ALVO = "-1001111"
OUTRO = "-1002222"


@pytest.fixture
def div(bm, monkeypatch):
    """divulgacao_canal com Telegram e IA falsos; guarda o que tentou enviar e agendar (bm cria as tabelas)."""
    import divulgacao_canal as modulo
    db.salvar_config("alvos_divulgacao", {"alvos": [ALVO, OUTRO], "frequencia_por_hora": 1})
    modulo.registro = SimpleNamespace(textos=0, enviados=[], agendados=[], sem_acesso={ALVO})

    async def gerar_texto(escopo, repeticoes=1):
        modulo.registro.textos += 1
        return "convite"

    async def get_entity(alvo):
        if str(alvo) in modulo.registro.sem_acesso:
            raise ChannelPrivateError(request=None)
        return alvo

    async def send_message(entidade, texto):
        modulo.registro.enviados.append(str(entidade))

    cliente = SimpleNamespace(is_connected=lambda: True, get_entity=get_entity, send_message=send_message)
    agendador = SimpleNamespace(add_job=lambda f, t, run_date, args, **k: modulo.registro.agendados.append(args))
    monkeypatch.setattr(modulo, "gerar_texto", gerar_texto)
    monkeypatch.setattr(modulo, "client", cliente)
    monkeypatch.setattr(modulo, "scheduler", agendador)
    monkeypatch.setattr(modulo, "telegram_lock", asyncio.Lock())
    monkeypatch.setattr(modulo, "bloqueio_flood_ate", None)
    monkeypatch.setattr(modulo, "ultimos_agendamentos_por_alvo", {})
    return modulo


def test_sem_acesso_pausa_o_alvo_sem_lotar_os_erros(div):
    rodar(div.enviar_mensagem("principal", ALVO))
    assert ALVO in alvos_sem_acesso.ler()
    assert consultar("SELECT COUNT(*) FROM erros_logs")[0] == 0

    # O envio seguinte nem pede texto à IA; o outro alvo segue normal.
    textos = div.registro.textos
    rodar(div.enviar_mensagem("principal", ALVO))
    rodar(div.enviar_mensagem("principal", OUTRO))
    assert div.registro.textos == textos + 1
    assert div.registro.enviados == [OUTRO]


def test_alvo_pausado_fica_fora_da_hora(div):
    alvos_sem_acesso.marcar(ALVO, "ChannelPrivateError")
    div.programar_envios_da_hora()
    assert [args[1] for args in div.registro.agendados] == [OUTRO]

    alvos_sem_acesso.reativar(ALVO)
    db.salvar_config("plano_divulgacao_hora", {})
    div.ultimos_agendamentos_por_alvo.clear()
    div.registro.agendados.clear()
    div.programar_envios_da_hora()
    assert sorted(args[1] for args in div.registro.agendados) == [ALVO, OUTRO]


@pytest.fixture
def privado(bm, monkeypatch):
    enviados = []

    async def send_message(chat, texto, **k):
        enviados.append((texto, k.get("reply_markup")))
    monkeypatch.setattr(bm.bot, "send_message", send_message)
    return enviados


def test_avisa_uma_vez_e_reativa_pelo_botao(bm, privado, Msg):
    db.salvar_config("alvos_divulgacao_viral", {"alvos": [ALVO]})
    alvos_sem_acesso.marcar(ALVO, "ChannelPrivateError")

    rodar(bm.avisar_alvos_sem_acesso())
    rodar(bm.avisar_alvos_sem_acesso())
    assert len(privado) == 1 and "perdeu o acesso" in privado[0][0]
    botao = privado[0][1].inline_keyboard[0][0]

    respostas, teclados = [], []
    mensagem = Msg()
    mensagem.reply_markup = privado[0][1]

    async def editar(reply_markup=None):
        teclados.append(reply_markup)
    mensagem.edit_reply_markup = editar

    async def responder(texto, **k):
        respostas.append(texto)
    clique = SimpleNamespace(data=botao.callback_data, from_user=SimpleNamespace(id=bm.ADMIN_ID),
                             message=mensagem, answer=responder)
    rodar(bm.reativar_alvo_divulgacao(clique))
    assert ALVO not in alvos_sem_acesso.ler()
    assert "Reativado" in respostas[0] and teclados == [None]

    rodar(bm.reativar_alvo_divulgacao(clique))
    assert "já está ativo" in respostas[1]


def test_painel_mostra_sem_acesso_e_oferece_o_botao(bm, Msg, Est):
    db.salvar_config("alvos_divulgacao", {"alvos": [ALVO, OUTRO], "frequencia_por_hora": 1})
    alvos_sem_acesso.marcar(ALVO, "ChannelPrivateError")
    msg = Msg("SPAM em Grupos 📢")
    rodar(bm.gerenciar_divulgacao(msg, Est()))
    assert msg.saidas[0].count("Sem acesso desde") == 1
    assert "toque para reativar" in msg.saidas[1]


def test_alvo_excluido_de_todos_os_paineis_sai_da_lista(bm, privado):
    db.salvar_config("alvos_divulgacao_publico", {"alvos": [OUTRO]})
    alvos_sem_acesso.marcar(ALVO, "ChannelPrivateError")
    alvos_sem_acesso.marcar(OUTRO, "ChannelPrivateError")
    rodar(bm.avisar_alvos_sem_acesso())
    assert list(alvos_sem_acesso.ler()) == [OUTRO]


def test_atualizar_config_le_altera_e_grava(bm):
    db.salvar_config("teste", {"a": 1})
    assert db.atualizar_config("teste", lambda d: d.setdefault("b", 2)) == 2
    assert db.ler_config("teste") == {"a": 1, "b": 2}
    assert db.atualizar_config("nova", lambda d: d.update(x=1)) is None
    assert db.ler_config("nova") == {"x": 1}

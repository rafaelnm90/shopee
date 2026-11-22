"""
Grupo dos amigos da Shopee Vídeo (P271 2 a P281 1): o /amigos (e o menu só do Rafael), quem pode pedir, o Liberar
Amigos ✅, a fila, o pedido do Rafael, a estimativa de tempo, o painel e a menção.
"""
import time
from datetime import datetime
from types import SimpleNamespace

import pytest

import db
from conftest import rodar

GRUPO = -1001


class BotFalso:
    """
    Guarda cada envio (destino, texto, a mensagem a que responde e os botões), o que foi fixado e apagado e o menu de
    comandos de cada grupo.
    """

    def __init__(self, fixar_falha=False, menu_falha=False):
        self.envios, self.fixadas, self.apagadas, self.proximo, self.fixar_falha = [], [], [], 100, fixar_falha
        self.menus, self.menu_falha = [], menu_falha

    async def send_message(self, chat_id, text, **kw):
        self.proximo += 1
        resposta = kw.get("reply_parameters")
        self.envios.append({"chat": chat_id, "texto": text, "id": self.proximo, "botoes": kw.get("reply_markup"),
                            "responde_a": getattr(resposta, "message_id", None)})
        return SimpleNamespace(message_id=self.proximo)

    async def pin_chat_message(self, chat_id, message_id, **kw):
        if self.fixar_falha:
            raise RuntimeError("sem permissão")
        self.fixadas.append((chat_id, message_id))

    async def delete_message(self, chat_id, message_id):
        self.apagadas.append((chat_id, message_id))

    async def set_my_commands(self, commands, scope=None, **kw):
        if self.menu_falha:
            raise RuntimeError("sem rede")
        self.menus.append(("pôr", [c.command for c in commands], scope.type, scope.chat_id, scope.user_id))

    async def delete_my_commands(self, scope=None, **kw):
        self.menus.append(("tirar", scope.type, scope.chat_id, scope.user_id))


class Toque:
    """O toque num botão de mensagem (callback), com a resposta no próprio botão."""

    def __init__(self, data, usuario, chat_id=GRUPO):
        self.data, self.from_user, self.respostas, self.editado = data, usuario, [], None

        async def editar(texto, **kw):
            self.editado = texto

        self.message = SimpleNamespace(chat=SimpleNamespace(id=chat_id), edit_text=editar)

    async def answer(self, texto=None, show_alert=False, **kw):
        self.respostas.append((texto, show_alert))


def _pessoa(ident, nome, arroba=None):
    return SimpleNamespace(id=ident, first_name=nome, last_name=None, username=arroba)


@pytest.fixture
def am(bm, monkeypatch):
    import amigos_shopee_video
    monkeypatch.setattr(amigos_shopee_video, "bot_instance", BotFalso())
    return amigos_shopee_video


def _grupo(am, **mudancas):
    db.salvar_config(am.CHAVE, {**am._padrao(), "grupo": GRUPO, "titulo": "Amigos", "ligado": True, **mudancas})


def _sem_atender_na_hora(am, monkeypatch):
    chamadas = []
    monkeypatch.setattr(am, "_atender_logo", lambda: chamadas.append(1))
    return chamadas


def test_amigos_fixa_o_botao_no_grupo_e_liga(am, bm, Msg):
    msg = Msg("/amigos")
    msg.chat = SimpleNamespace(id=GRUPO, title="Amigos", type="supergroup")
    rodar(am.comando_amigos(msg))
    bot = am.bot_instance
    botao = bot.envios[0]
    assert botao["chat"] == GRUPO and "Quero um vídeo 🎬" in botao["texto"]
    assert botao["botoes"].inline_keyboard[0][0].callback_data == am.CALLBACK_QUERO
    assert bot.fixadas == [(GRUPO, botao["id"])]
    assert bot.envios[1]["chat"] == bm.ADMIN_ID and "ligado neste grupo" in bot.envios[1]["texto"]
    config = am.ler()
    assert (config["grupo"], config["titulo"], config["ligado"], config["botao"]) == (GRUPO, "Amigos", True,
                                                                                      botao["id"])
    # Mandado de novo, o botão de antes sai; quem não é o Rafael não muda nada.
    rodar(am.comando_amigos(msg))
    assert bot.apagadas == [(GRUPO, botao["id"])] and am.ler()["botao"] == bot.envios[2]["id"]
    estranho = Msg("/amigos", user_id=99)
    estranho.chat = msg.chat
    antes = len(bot.envios)
    rodar(am.comando_amigos(estranho))
    assert len(bot.envios) == antes


def test_amigos_sem_permissao_de_fixar_avisa_o_rafael(am, bm, Msg, monkeypatch):
    monkeypatch.setattr(am, "bot_instance", BotFalso(fixar_falha=True))
    msg = Msg("/amigos")
    msg.chat = SimpleNamespace(id=GRUPO, title="Amigos", type="supergroup")
    rodar(am.comando_amigos(msg))
    aviso = am.bot_instance.envios[-1]
    assert aviso["chat"] == bm.ADMIN_ID and "permissão de fixar mensagens" in aviso["texto"]


def test_quem_nao_foi_liberado_e_avisado_e_o_rafael_libera(am, bm, monkeypatch):
    # P274 2: só pede quem o Rafael libera; quem não foi liberado recebe o aviso no grupo, e ele, o nome com o
    # Liberar ✅ (no máximo uma vez a cada 6 h por pessoa).
    _grupo(am)
    atender = _sem_atender_na_hora(am, monkeypatch)
    bot = am.bot_instance
    ana = _pessoa(7, "Ana & Cia")
    toque = Toque(am.CALLBACK_QUERO, ana)
    rodar(am.quero_um_video(toque))
    no_grupo, no_privado = bot.envios
    assert no_grupo["chat"] == GRUPO and "ainda não foi liberado" in no_grupo["texto"]
    assert no_privado["chat"] == bm.ADMIN_ID and "Ana &amp; Cia" in no_privado["texto"]
    assert no_privado["botoes"].inline_keyboard[0][0].callback_data == am.CALLBACK_LIBERAR + "7"
    assert am.ler()["fila"] == [] and atender == []
    # O 2º toque só responde no botão.
    toque = Toque(am.CALLBACK_QUERO, ana)
    rodar(am.quero_um_video(toque))
    assert len(bot.envios) == 2 and toque.respostas[0][1] is True and "ainda não foi liberado" in toque.respostas[0][0]
    # Só o Rafael libera.
    rodar(am.liberar_amigo(Toque(am.CALLBACK_LIBERAR + "7", _pessoa(99, "Outro"), chat_id=99)))
    assert am.ler()["liberados"] == {}
    liberar = Toque(am.CALLBACK_LIBERAR + "7", _pessoa(bm.ADMIN_ID, "Rafael"), chat_id=bm.ADMIN_ID)
    rodar(am.liberar_amigo(liberar))
    assert am.ler()["liberados"] == {"7": {"nome": "Ana & Cia"}} and "Ana &amp; Cia" in liberar.editado
    rodar(am.quero_um_video(Toque(am.CALLBACK_QUERO, ana)))
    assert len(am.ler()["fila"]) == 1 and atender == [1]


def test_liberado_o_aviso_de_nao_liberado_sai_do_grupo(am, bm, Msg, Est, monkeypatch):
    # P282 1: quando o Rafael libera (pelo Liberar ✅ do privado ou pelo Liberar Amigos ✅ do painel), o ⛔ da pessoa sai
    # do grupo. O Telegram só deixa o bot apagar até 48 h: o que não sai fica no registro.
    _grupo(am)
    _sem_atender_na_hora(am, monkeypatch)
    bot = am.bot_instance
    rodar(am.quero_um_video(Toque(am.CALLBACK_QUERO, _pessoa(7, "Ana"))))
    aviso = bot.envios[0]
    assert "ainda não foi liberado" in aviso["texto"] and am.avisos_no_grupo(7) == [aviso["id"]]
    # O aviso de novo, depois das 6 h, guarda os dois ⛔.
    assert am.avisar_agora(7, "Ana", agora=time.time() + am.ESPERA_DO_AVISO + 60)
    am.anotar_o_aviso(7, 999)
    assert am.avisos_no_grupo(7) == [aviso["id"], 999]
    rodar(am.liberar_amigo(Toque(am.CALLBACK_LIBERAR + "7", _pessoa(bm.ADMIN_ID, "Rafael"), chat_id=bm.ADMIN_ID)))
    assert bot.apagadas == [(GRUPO, aviso["id"]), (GRUPO, 999)] and "7" in am.ler()["liberados"]

    class BotQueNaoApaga(BotFalso):
        async def delete_message(self, chat_id, message_id):
            raise RuntimeError("message can't be deleted")

    monkeypatch.setattr(am, "bot_instance", BotQueNaoApaga())
    rodar(am.quero_um_video(Toque(am.CALLBACK_QUERO, _pessoa(8, "Bia"))))
    msg, est = Msg("1. Bia"), Est()
    rodar(est.set_state(am.AmigosFluxo.liberando))
    rodar(am.liberar_da_lista(msg, est))
    assert "8" in am.ler()["liberados"] and "Liberado" in msg.saidas[0]
    linhas = [(r[2], r[3]) for r in am.registro_processos.sequencia("shopee_video", am.PROCESSO_DO_PAINEL,
                                                                     "2000-01-01 00:00:00")
              if r[2] == "aviso de não liberado apagado"]
    assert linhas == [("aviso de não liberado apagado", "2 de 2"), ("aviso de não liberado apagado", "0 de 1")]


def test_cada_toque_e_um_pedido_e_o_video_responde_a_mensagem_do_pedido(am, monkeypatch):
    # P273 2 e P272 2: sem limite, cada toque um vídeo, um de cada vez; o vídeo responde à mensagem do pedido.
    _grupo(am, liberados={"7": {"nome": "Ana"}})
    _sem_atender_na_hora(am, monkeypatch)
    bot = am.bot_instance
    ana = _pessoa(7, "Ana", "ana_teste")
    rodar(am.quero_um_video(Toque(am.CALLBACK_QUERO, ana)))
    rodar(am.quero_um_video(Toque(am.CALLBACK_QUERO, ana)))
    assert "(1º da fila)" in bot.envios[0]["texto"] and "(2º da fila)" in bot.envios[1]["texto"]
    assert [p["mensagem"] for p in am.ler()["fila"]] == [bot.envios[0]["id"], bot.envios[1]["id"]]
    pedidos = []

    async def preparar(bot_, admin_id, amigo, agora=None, fonte="autorais"):
        pedidos.append(dict(amigo, fonte=fonte))
        return am.assistente.MANDADO_AO_AMIGO if len(pedidos) == 1 else am.assistente.SEM_VIDEO_PARA_O_AMIGO

    monkeypatch.setattr(am.assistente, "preparar_para_o_amigo", preparar)
    rodar(am.atender_a_fila())
    assert [(p["id"], p["mencao"], p["grupo"], p["responder_a"]) for p in pedidos] == [
        (7, "@ana_teste", GRUPO, bot.envios[0]["id"]), (7, "@ana_teste", GRUPO, bot.envios[1]["id"])]
    # A mesma Fonte dos Vídeos do Rafael (P276 2).
    assert pedidos[0]["fonte"] == am.painel.ler_config()["fonte"]
    assert am.ler()["fila"] == []
    resposta = bot.envios[-1]
    assert "não tenho vídeo novo" in resposta["texto"] and resposta["responde_a"] == bot.envios[1]["id"]


def test_o_rafael_pede_sem_se_liberar_e_o_pedido_vai_como_o_enviar_1_agora(am, bm, monkeypatch):
    # P281 1: o Rafael sempre pode pedir pelo botão do grupo; o vídeo dele é preparado como o Enviar 1 Agora 📤 (as
    # regras do assistente dele) e vai ao privado, com o Postei ✅, e ao grupo, em resposta ao pedido.
    _grupo(am)
    atender = _sem_atender_na_hora(am, monkeypatch)
    bot = am.bot_instance
    rafael = _pessoa(bm.ADMIN_ID, "Rafael", "rafa_teste")
    rodar(am.quero_um_video(Toque(am.CALLBACK_QUERO, rafael)))
    assert len(bot.envios) == 1 and "ainda não foi liberado" not in bot.envios[0]["texto"]
    assert "(1º da fila)" in bot.envios[0]["texto"] and atender == [1] and am.ler()["avisados"] == {}
    pedidos = []

    async def preparar(bot_, admin_id, agora=None, fonte="autorais", cobrindo=False, no_grupo=None):
        pedidos.append((admin_id, fonte, cobrindo, no_grupo))
        return am.assistente.MANDADO_NO_PRIVADO

    async def do_amigo(*a, **k):
        raise AssertionError("o pedido do Rafael não é preparado como o de um amigo")

    monkeypatch.setattr(am.assistente, "preparar_e_enviar", preparar)
    monkeypatch.setattr(am.assistente, "preparar_para_o_amigo", do_amigo)
    rodar(am.atender_a_fila())
    (admin_id, fonte, cobrindo, no_grupo), = pedidos
    assert admin_id == bm.ADMIN_ID and fonte == am.painel.ler_config()["fonte"] and cobrindo is False
    assert (no_grupo["grupo"], no_grupo["responder_a"], no_grupo["mencao"]) == (GRUPO, bot.envios[0]["id"],
                                                                               "@rafa_teste")
    assert am.ler()["fila"] == [] and len(am.ler()["preparos"]) == 1
    # Sem vídeo na fonte, o grupo responde que agora não tem vídeo novo, e o tempo não entra na estimativa.
    rodar(am.quero_um_video(Toque(am.CALLBACK_QUERO, rafael)))

    async def sem_video(*a, **k):
        return am.assistente.SEM_VIDEO_NO_ENVIO + "Vídeos Autorais para mandar (a fila está vazia ou sem arquivos)"

    monkeypatch.setattr(am.assistente, "preparar_e_enviar", sem_video)
    rodar(am.atender_a_fila())
    resposta = bot.envios[-1]
    assert "não tenho vídeo novo" in resposta["texto"] and resposta["responde_a"] == bot.envios[-2]["id"]
    assert len(am.ler()["preparos"]) == 1


def test_a_mensagem_do_pedido_diz_em_quanto_tempo_o_video_fica_pronto(am, monkeypatch):
    # Pedido do Rafael (22/11): a estimativa de tempo depois do toque, pela mediana do preparo dos últimos pedidos
    # feitos, vezes a posição na fila (sem nenhum feito ainda, 3 min por pedido).
    _grupo(am, liberados={"7": {"nome": "Ana"}})
    _sem_atender_na_hora(am, monkeypatch)
    bot = am.bot_instance
    ana = _pessoa(7, "Ana")
    rodar(am.quero_um_video(Toque(am.CALLBACK_QUERO, ana)))
    assert "(1º da fila). Fica pronto em cerca de 3 min." in bot.envios[-1]["texto"]
    for segundos in (100, 110, 600):
        am.anotar_preparo(segundos)
    rodar(am.quero_um_video(Toque(am.CALLBACK_QUERO, ana)))
    # 2º da fila, com a mediana de 110 s: 220 s, cerca de 4 min.
    assert "(2º da fila). Fica pronto em cerca de 4 min." in bot.envios[-1]["texto"]
    for _ in range(20):
        am.anotar_preparo(60)
    assert am.ler()["preparos"] == [60] * am.PREPAROS_GUARDADOS
    assert am.minutos_estimados(am.ler(), 1) == 1 and am.minutos_estimados({"preparos": []}, 2) == 6


def test_desligado_o_botao_avisa_e_a_fila_espera(am, monkeypatch):
    _grupo(am, ligado=False, liberados={"7": {"nome": "Ana"}},
           fila=[{"chave": "a", "id": 7, "mencao": "@ana", "mensagem": 5}])
    toque = Toque(am.CALLBACK_QUERO, _pessoa(7, "Ana"))
    rodar(am.quero_um_video(toque))
    assert "pausados" in toque.respostas[0][0] and am.bot_instance.envios == []

    async def preparar(*a, **k):
        raise AssertionError("não devia preparar com o grupo desligado")

    monkeypatch.setattr(am.assistente, "preparar_para_o_amigo", preparar)
    rodar(am.atender_a_fila())
    assert len(am.ler()["fila"]) == 1
    # O botão de outro grupo (um /amigos mandado em outro lugar) não vale mais.
    _grupo(am, liberados={"7": {"nome": "Ana"}})
    toque = Toque(am.CALLBACK_QUERO, _pessoa(7, "Ana"), chat_id=-2002)
    rodar(am.quero_um_video(toque))
    assert "não vale mais" in toque.respostas[0][0]


def test_erro_num_pedido_nao_trava_a_fila(am, monkeypatch):
    _grupo(am, liberados={"7": {"nome": "Ana"}},
           fila=[{"chave": "a", "id": 7, "mencao": "@ana", "mensagem": 5},
                 {"chave": "b", "id": 8, "mencao": "@tirado", "mensagem": 6}])

    async def preparar(*a, **k):
        raise RuntimeError("falhou")

    monkeypatch.setattr(am.assistente, "preparar_para_o_amigo", preparar)
    rodar(am.atender_a_fila())
    # O que deu erro responde no grupo; o pedido de quem não está mais liberado só sai da fila.
    assert am.ler()["fila"] == []
    assert [(e["texto"].split(",")[0], e["responde_a"]) for e in am.bot_instance.envios] == [("😕 @ana", 5)]


def test_tirar_amigo_tira_os_pedidos_dele(am, Msg, Est):
    _grupo(am, liberados={"7": {"nome": "Ana"}, "8": {"nome": "Bia"}},
           fila=[{"chave": "a", "id": 7, "mencao": "@ana", "mensagem": 5},
                 {"chave": "b", "id": 8, "mencao": "@bia", "mensagem": 6}])
    msg, est = Msg(am.BOTAO_TIRAR), Est()
    rodar(am.pedir_quem_tirar(msg, est))
    assert rodar(est.get_state()) == am.AmigosFluxo.tirando.state
    escolha = Msg("1. Ana")
    rodar(am.tirar_amigo(escolha, est))
    config = am.ler()
    assert config["liberados"] == {"8": {"nome": "Bia"}} and [p["chave"] for p in config["fila"]] == ["b"]
    assert "Ana não pode mais pedir" in escolha.saidas[0] and "Grupo dos Amigos 👥" in escolha.saidas[-1]


def test_cancelar_no_tirar_volta_a_tela_do_grupo(am, bm, Msg, Est):
    _grupo(am, liberados={"7": {"nome": "Ana"}})
    msg = Msg("Cancelar ❌")
    rodar(bm.cancelar_fluxo_global(msg, Est(estado=am.AmigosFluxo.tirando)))
    assert "Nada foi alterado" in msg.saidas[0] and "Grupo dos Amigos 👥" in msg.saidas[-1]
    assert am.ler()["liberados"] == {"7": {"nome": "Ana"}}


def test_painel_do_grupo_mostra_o_estado_os_liberados_e_os_mandados(am, Msg, Est):
    msg, est = Msg(am.painel.BOTAO_GRUPO_DOS_AMIGOS), Est()
    rodar(am.grupo_dos_amigos_handler(msg, est))
    assert "Sem grupo" in msg.saidas[-1] and "ninguém ainda" in msg.saidas[-1]
    ligar = Msg(am.BOTAO_LIGAR)
    rodar(am.ligar_ou_desligar(ligar, est))
    assert "Ainda não há grupo" in ligar.saidas[0] and am.ler()["ligado"] is False
    _grupo(am, liberados={"7": {"nome": "Ana <3"}})
    am.assistente.registrar("v1", "enviado", "", item="11", amigo="7")
    am.assistente.registrar("v2", "enviado", "", item="12")
    msg = Msg(am.painel.BOTAO_GRUPO_DOS_AMIGOS)
    rodar(am.grupo_dos_amigos_handler(msg, est))
    texto = msg.saidas[-1]
    assert "▶️ <b>Ligado</b>" in texto and "1. Ana &lt;3" in texto and "Amigos" in texto
    assert "hoje <b>1</b>, no total <b>1</b>" in texto and "Pedidos na fila: <b>0</b>" in texto
    assert [b.text for linha in am.teclado_do_painel(am.ler()).keyboard for b in linha] == [
        am.BOTAO_DESLIGAR, am.BOTAO_LIBERAR_AMIGOS, am.BOTAO_TIRAR, am.painel.BOTAO_VOLTAR]
    desligar = Msg(am.BOTAO_DESLIGAR)
    rodar(am.ligar_ou_desligar(desligar, est))
    assert am.ler()["ligado"] is False and "desligado" in desligar.saidas[0]


def test_a_fila_e_conferida_a_cada_minuto(am):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    agendador = AsyncIOScheduler()
    am.configurar_dependencias(am.bot_instance, agendador, am.ADMIN_ID)
    assert agendador.get_job("shopee_video_amigos").trigger.interval.total_seconds() == 60
    # Na subida, o grupo guardado ganha o /amigos no menu do Rafael (P279 1).
    assert agendador.get_job("shopee_video_amigos_menu").func is am.conferir_o_comando_no_menu


def test_o_amigos_passa_antes_das_mensagens_soltas_dos_grupos(bm):
    # O interceptar_envio_livre fica com toda mensagem solta nos grupos: o /amigos tem de vir antes dele.
    from aiogram import types
    callbacks = [h.callback for h in bm.dp.message.handlers]
    assert callbacks.index(bm.comando_grupo_dos_amigos) < callbacks.index(bm.interceptar_envio_livre)
    msg = types.Message(message_id=1, date=datetime.now(), chat=types.Chat(id=GRUPO, type="supergroup"),
                        from_user=types.User(id=bm.ADMIN_ID, is_bot=False, first_name="R"), text="/amigos")
    amigos = next(h for h in bm.dp.message.handlers if h.callback is bm.comando_grupo_dos_amigos)
    solto = next(h for h in bm.dp.message.handlers if h.callback is bm.interceptar_envio_livre)
    assert rodar(amigos.check(msg, bot=bm.bot, raw_state=None))[0]
    assert rodar(solto.check(msg, bot=bm.bot, raw_state=None))[0]


def test_o_amigos_e_o_toque_no_botao_passam_pela_trava_do_bot(am, bm, monkeypatch):
    # Em 22/11, o /amigos do Rafael no grupo não chegou ao comando: a trava do bot_mestre (BloqueioAdminMiddleware) só
    # deixa o Rafael usar o bot no privado e barra o toque de quem não é ele. Aqui, pelo dispatcher, com a trava.
    from aiogram import types
    chegaram = []

    async def comando(message):
        chegaram.append(("amigos", message.from_user.id))

    async def quero(callback):
        chegaram.append(("quero", callback.from_user.id))

    monkeypatch.setattr(am, "comando_amigos", comando)
    toque = next(h for h in am.router.callback_query.handlers if h.callback is am.quero_um_video)
    monkeypatch.setattr(toque, "callback", quero)
    grupo = types.Chat(id=GRUPO, type="supergroup", title="Amigos")
    rafael = types.User(id=bm.ADMIN_ID, is_bot=False, first_name="R")
    amigo = types.User(id=7, is_bot=False, first_name="Ana")
    botao = types.Message(message_id=99, date=datetime.now(), chat=grupo,
                          from_user=types.User(id=1, is_bot=True, first_name="Bot"), text="🎬")

    def mensagem(n, usuario, texto):
        return types.Update(update_id=n, message=types.Message(message_id=n, date=datetime.now(), chat=grupo,
                                                               from_user=usuario, text=texto))

    def clique(n, usuario, dados):
        return types.Update(update_id=n, callback_query=types.CallbackQuery(
            id=str(n), from_user=usuario, chat_instance="x", message=botao, data=dados))

    rodar(bm.dp.feed_update(bm.bot, mensagem(1, rafael, "/amigos")))
    rodar(bm.dp.feed_update(bm.bot, clique(2, amigo, am.CALLBACK_QUERO)))
    rodar(bm.dp.feed_update(bm.bot, clique(3, rafael, am.CALLBACK_QUERO)))
    assert chegaram == [("amigos", bm.ADMIN_ID), ("quero", 7), ("quero", bm.ADMIN_ID)]
    # O resto continua barrado no grupo: as outras mensagens do Rafael, o /amigos de outra pessoa e outros toques.
    trava, passou = bm.BloqueioAdminMiddleware(), []

    async def handler(evento, dados):
        passou.append(evento)

    no_grupo = SimpleNamespace(id=GRUPO, type="supergroup")
    for usuario, texto in ((rafael, "oi"), (amigo, "/amigos")):
        rodar(trava(handler, SimpleNamespace(from_user=usuario, chat=no_grupo, text=texto), {}))
    rodar(trava(handler, SimpleNamespace(from_user=amigo, data="outro:botao",
                                         message=SimpleNamespace(chat=no_grupo)), {}))
    rodar(trava(handler, SimpleNamespace(from_user=rafael, chat=no_grupo, text="/amigos@ShopeeVideoBot"), {}))
    assert len(passou) == 1 and passou[0].text == "/amigos@ShopeeVideoBot"


def test_mencao_do_usuario_igual_no_bot_mestre_e_no_grupo(bm):
    from utils import mencao_do_usuario
    assert mencao_do_usuario(_pessoa(7, "Ana", "ana_teste")) == "@ana_teste"
    assert mencao_do_usuario(_pessoa(7, "Ana & Cia")) == "<a href='tg://user?id=7'>Ana &amp; Cia</a>"
    assert bm.montar_mencao_usuario(_pessoa(7, "Ana & Cia")) == mencao_do_usuario(_pessoa(7, "Ana & Cia"))


def test_amigos_sem_poder_mandar_no_grupo_avisa_o_rafael(am, bm, Msg, monkeypatch):
    class BotSemGrupo(BotFalso):
        async def send_message(self, chat_id, text, **kw):
            if chat_id == GRUPO:
                raise RuntimeError("sem permissão")
            return await super().send_message(chat_id, text, **kw)

    monkeypatch.setattr(am, "bot_instance", BotSemGrupo())
    msg = Msg("/amigos")
    msg.chat = SimpleNamespace(id=GRUPO, title="Amigos", type="supergroup")
    rodar(am.comando_amigos(msg))
    assert [e["chat"] for e in am.bot_instance.envios] == [bm.ADMIN_ID]
    assert "Não consegui mandar o botão no grupo" in am.bot_instance.envios[0]["texto"]
    assert am.ler()["grupo"] is None


def test_amigos_vai_ao_menu_do_grupo_so_para_o_rafael(am, bm, Msg, monkeypatch):
    # P279 1: depois do 1º /amigos, o comando fica no menu (o /) do grupo, visível só para o Rafael; mandado em outro
    # grupo, o menu do de antes sai.
    msg = Msg("/amigos")
    msg.chat = SimpleNamespace(id=GRUPO, title="Amigos", type="supergroup")
    rodar(am.comando_amigos(msg))
    bot = am.bot_instance
    assert bot.menus == [("pôr", ["amigos"], "chat_member", GRUPO, bm.ADMIN_ID)]
    assert "visível só para você" in bot.envios[-1]["texto"]
    outro = Msg("/amigos")
    outro.chat = SimpleNamespace(id=-2002, title="Outro", type="supergroup")
    rodar(am.comando_amigos(outro))
    assert bot.menus[1:] == [("tirar", "chat_member", GRUPO, bm.ADMIN_ID),
                             ("pôr", ["amigos"], "chat_member", -2002, bm.ADMIN_ID)]
    # Na subida do bot, o grupo guardado tem o menu de novo; sem grupo, nada.
    rodar(am.conferir_o_comando_no_menu())
    assert bot.menus[-1] == ("pôr", ["amigos"], "chat_member", -2002, bm.ADMIN_ID)
    db.salvar_config(am.CHAVE, am._padrao())
    rodar(am.conferir_o_comando_no_menu())
    assert len(bot.menus) == 4
    # Sem o menu, o botão vai do mesmo jeito, e o aviso não fala do menu.
    monkeypatch.setattr(am, "bot_instance", BotFalso(menu_falha=True))
    rodar(am.comando_amigos(msg))
    assert am.ler()["grupo"] == GRUPO and "menu" not in am.bot_instance.envios[-1]["texto"]


def test_liberar_amigos_no_painel_mostra_quem_espera_e_o_liberado_sai(am, bm, monkeypatch):
    # P279 1: em Grupo dos Amigos 👥, o Liberar Amigos ✅ (N) mostra um botão com o nome de cada um que tocou e ainda
    # não foi liberado; o toque libera e o nome sai. Pelo dispatcher, como chega do Telegram.
    from aiogram import types
    _grupo(am, liberados={"9": {"nome": "Bia"}},
           avisados={"7": {"quando": 1, "nome": "Ana"}, "8": {"quando": 2, "nome": "João (@joao)"}})
    respostas = []

    async def responder(self, text, **kw):
        teclado = kw.get("reply_markup")
        botoes = [b.text for linha in teclado.keyboard for b in linha] if teclado is not None else None
        respostas.append((text, botoes))

    monkeypatch.setattr(types.Message, "answer", responder)
    privado = types.Chat(id=bm.ADMIN_ID, type="private")
    rafael = types.User(id=bm.ADMIN_ID, is_bot=False, first_name="R")
    numero = iter(range(1, 100))

    def tocar(texto):
        respostas.clear()
        n = next(numero)
        rodar(bm.dp.feed_update(bm.bot, types.Update(update_id=n, message=types.Message(
            message_id=n, date=datetime.now(), chat=privado, from_user=rafael, text=texto))))
        return respostas

    texto, botoes = tocar(am.painel.BOTAO_GRUPO_DOS_AMIGOS)[-1]
    assert "Esperando a liberação: <b>2</b>" in texto and "Liberar Amigos ✅ (2)" in botoes
    texto, botoes = tocar("Liberar Amigos ✅ (2)")[-1]
    assert botoes == ["1. Ana", "2. João (@joao)", am.BOTAO_VOLTAR_AMIGOS]
    saidas = tocar("1. Ana")
    config = am.ler()
    assert config["liberados"] == {"9": {"nome": "Bia"}, "7": {"nome": "Ana"}} and "7" not in config["avisados"]
    assert "Ana já pode pedir" in saidas[0][0] and saidas[-1][1] == ["1. João (@joao)", am.BOTAO_VOLTAR_AMIGOS]
    # O que não é um nome da lista não libera ninguém.
    saidas = tocar("2. Fulano")
    assert "Toque num dos nomes" in saidas[0][0] and set(am.ler()["liberados"]) == {"9", "7"}
    saidas = tocar("1. João (@joao)")
    assert set(am.ler()["liberados"]) == {"9", "7", "8"} and "Ninguém mais esperando" in saidas[1][0]
    assert am.BOTAO_LIBERAR_AMIGOS in saidas[-1][1] and "Liberar Amigos ✅ (" not in " ".join(saidas[-1][1])
    assert "Ninguém esperando" in tocar(am.BOTAO_LIBERAR_AMIGOS)[0][0]
    # O Voltar da lista volta à tela do grupo dos amigos.
    _grupo(am, avisados={"7": {"quando": 1, "nome": "Ana"}})
    tocar("Liberar Amigos ✅ (1)")
    texto, botoes = tocar(am.BOTAO_VOLTAR_AMIGOS)[-1]
    assert texto.startswith("👥 <b>Grupo dos Amigos 👥</b>") and am.ler()["liberados"] == {}

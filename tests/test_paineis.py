"""Painéis do bot: SPAM, Cancelar das rotinas, painel do buscador e painel de ofertas do Grupo Público."""
import asyncio
import logging
from types import SimpleNamespace

from conftest import rodar


def test_spam_principal_valida_o_alvo(bm, Msg, Est, monkeypatch):
    async def get_chat(var):
        if var == "@grupo1":
            return SimpleNamespace(id=-1001111, title="Grupo Um", type="supergroup", full_name=None)
        raise RuntimeError("chat not found")
    monkeypatch.setattr(bm.bot, "get_chat", get_chat)
    msg = Msg("https://web.telegram.org/a/#-1002856422690, https://t.me/grupo1, @canal_que_nao_existe")
    rodar(bm.salvar_alvo(msg, Est()))
    assert bm.ler_alvos_divulgacao()["alvos"] == ["-1002856422690", "-1001111"]
    assert any("Não consegui validar" in s for s in msg.saidas)

    dados = bm.ler_alvos_divulgacao()
    dados.setdefault("config_alvos", {})["-1002856422690"] = {"frequencia": 9}
    bm.salvar_alvos_divulgacao(dados)
    rodar(bm.processar_exclusao(Msg("1"), Est()))
    assert "-1002856422690" not in bm.ler_alvos_divulgacao().get("config_alvos", {})


def test_cancelar_na_rotina_do_publico_volta_ao_publico(bm, Msg, Est, monkeypatch):
    chamado = []

    async def submenu(m, s):
        chamado.append((await s.get_data()).get("menu_origem"))
    monkeypatch.setattr(bm, "submenu_editar_rotinas", submenu)
    rodar(bm.cancelar_fluxo_global(Msg("Cancelar ❌"),
                                   Est({"tipo_edicao": "promo_achadinhos_publico"},
                                       estado="ConfigRotina:aguardando_novo_horario")))
    assert chamado == ["publico"]


def test_painel_do_buscador_fica_um_so(bm, Msg, monkeypatch):
    publicados, apagados = [], []

    async def send_message(*a, **k):
        publicados.append(len(publicados) + 100)
        return SimpleNamespace(message_id=publicados[-1])

    async def delete_message(chat_id=None, message_id=None):
        apagados.append(message_id)

    async def pin(*a, **k):
        pass
    monkeypatch.setattr(bm.bot, "send_message", send_message)
    monkeypatch.setattr(bm.bot, "delete_message", delete_message)
    monkeypatch.setattr(bm.bot, "pin_chat_message", pin)
    rodar(bm.publicar_painel_busca(Msg("/painelbusca")))
    rodar(bm.reenviar_painel_busca())
    rodar(bm.publicar_painel_busca(Msg("/painelbusca")))
    assert len(publicados) - len(apagados) == 1


def _painel_ofertas(bm, monkeypatch, recusa_apagar=False):
    publicados, apagados = [], []

    async def send_message(*a, **k):
        publicados.append(len(publicados) + 100)
        return SimpleNamespace(message_id=publicados[-1])

    async def delete_message(chat_id=None, message_id=None):
        if recusa_apagar:
            raise RuntimeError("message can't be deleted")
        apagados.append(message_id)

    async def pin(*a, **k):
        pass
    monkeypatch.setattr(bm.bot, "send_message", send_message)
    monkeypatch.setattr(bm.bot, "delete_message", delete_message)
    monkeypatch.setattr(bm.bot, "pin_chat_message", pin)
    bm.salvar_submissao_config({**bm.ler_submissao_config(), "grupo_id": -1001, "topico_envio": 7})
    return publicados, apagados


def test_painel_de_ofertas_renova_com_24_h_para_o_anterior_poder_sair(bm, monkeypatch):
    # O Telegram só deixa o bot apagar mensagem com menos de 48 h.
    publicados, apagados = _painel_ofertas(bm, monkeypatch)
    rodar(bm.reenviar_botao_ofertas())
    criado = bm.datetime.strptime(bm.ler_submissao_config()["msg_botao_ofertas_em"], "%Y-%m-%d %H:%M:%S")
    criado = criado.replace(tzinfo=bm.fuso_horario)

    rodar(bm.renovar_botao_ofertas_velho(criado + bm.timedelta(hours=23)))
    assert publicados == [100]
    rodar(bm.renovar_botao_ofertas_velho(criado + bm.timedelta(hours=24)))
    assert publicados == [100, 101] and apagados == [100]
    assert bm.ler_submissao_config()["msg_botao_ofertas"] == 101


def test_painel_sem_hora_renova_e_sem_painel_nao_cria(bm, monkeypatch):
    publicados, _ = _painel_ofertas(bm, monkeypatch)
    rodar(bm.renovar_botao_ofertas_velho())
    assert publicados == []                                     # nenhum painel no tópico ainda
    bm.salvar_submissao_config({**bm.ler_submissao_config(), "msg_botao_ofertas": 55})
    rodar(bm.renovar_botao_ofertas_velho())                     # painel de antes da renovação
    assert publicados == [100]


def test_painel_antigo_que_nao_sai_fica_no_log(bm, monkeypatch, caplog):
    _painel_ofertas(bm, monkeypatch, recusa_apagar=True)
    bm.salvar_submissao_config({**bm.ler_submissao_config(), "msg_botao_ofertas": 55})
    with caplog.at_level(logging.WARNING):
        rodar(bm.reenviar_botao_ofertas())
    assert any("Não consegui apagar o painel anterior (ID 55)" in r.getMessage() for r in caplog.records)
    assert bm.ler_submissao_config()["msg_botao_ofertas"] == 100


def _admin_no_privado(bm, texto):
    return SimpleNamespace(text=texto, from_user=SimpleNamespace(id=bm.ADMIN_ID),
                           chat=SimpleNamespace(id=bm.ADMIN_ID, type="private"), message_thread_id=None)


def test_painel_inicial_volta_depois_de_15_min_em_qualquer_menu(bm, monkeypatch):
    # O Rafael notou em 10/10: o "Painel Inicial restaurado" vinha em alguns menus e em
    # outros não. A marca de "está no Painel Inicial" ficava ligada ao entrar num menu
    # sem fluxo (ex.: Outros Canais), e o fim dos 15 min achava que ele ainda estava lá.
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey

    enviadas = []

    async def send_message(chat_id, texto, **k):
        enviadas.append(texto)
        return SimpleNamespace(message_id=len(enviadas))

    async def delete_message(**k):
        return True

    monkeypatch.setattr(bm.bot, "send_message", send_message)
    monkeypatch.setattr(bm.bot, "delete_message", delete_message)
    dormir = asyncio.sleep
    monkeypatch.setattr(bm.asyncio, "sleep", lambda *_: dormir(0))
    estado = FSMContext(storage=bm.dp.storage, key=StorageKey(bot_id=bm.bot.id, chat_id=bm.ADMIN_ID,
                                                              user_id=bm.ADMIN_ID, thread_id=None))
    middleware = bm.InatividadeMiddleware()

    async def tocar(texto, handler):
        await middleware(handler, _admin_no_privado(bm, texto), {"state": estado})

    async def menu_sem_fluxo(evento, dados):
        return None

    async def mostra_o_painel_inicial(evento, dados):
        await dados["state"].update_data(painel_atual="raiz")

    async def cenario():
        await estado.clear()
        await tocar("Voltar ao Início 🔙", mostra_o_painel_inicial)
        await bm.resetar_sessao_inatividade(bm.ADMIN_ID, bm.ADMIN_ID)
        assert enviadas == []                                  # já estava no Painel Inicial
        await tocar("Outros Canais 🗂️", menu_sem_fluxo)
        await bm.resetar_sessao_inatividade(bm.ADMIN_ID, bm.ADMIN_ID)
        assert "🏠 Painel Inicial restaurado." in enviadas

    rodar(cenario())


def test_falha_ao_restaurar_o_painel_deixa_o_rastro_com_o_tipo_do_erro(bm, monkeypatch, caplog):
    # Checkup de 25/10: "Erro ao atualizar o teclado e limpar chat" saiu 1x sem dizer o tipo; com
    # o rastro, o checkup mostra o tipo do erro e a linha.
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey

    async def send_message(chat_id, texto, **k):
        raise TimeoutError("o Telegram não respondeu")

    monkeypatch.setattr(bm.bot, "send_message", send_message)
    estado = FSMContext(storage=bm.dp.storage, key=StorageKey(bot_id=bm.bot.id, chat_id=bm.ADMIN_ID,
                                                              user_id=bm.ADMIN_ID, thread_id=None))

    async def cenario():
        await estado.update_data(painel_atual="outros")
        with caplog.at_level("ERROR"):
            await bm.resetar_sessao_inatividade(bm.ADMIN_ID, bm.ADMIN_ID)

    rodar(cenario())
    erros = [r for r in caplog.records if "Erro ao atualizar o teclado" in r.getMessage()]
    assert erros and erros[0].exc_info and erros[0].exc_info[0] is TimeoutError


def test_painel_inicial_volta_mesmo_com_restart_no_meio_dos_15_min(bm, monkeypatch):
    # O Rafael notou em 11/10: o Espelhador aberto às 17:03 seguia na tela à meia-noite. O
    # deploy reiniciou o bot às 17:15, e o cronômetro, que só existia na memória, sumiu.
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey

    enviadas = []

    async def send_message(chat_id, texto, **k):
        enviadas.append(texto)
        return SimpleNamespace(message_id=len(enviadas))

    async def delete_message(**k):
        return True

    monkeypatch.setattr(bm.bot, "send_message", send_message)
    monkeypatch.setattr(bm.bot, "delete_message", delete_message)
    dormir = asyncio.sleep
    monkeypatch.setattr(bm.asyncio, "sleep", lambda *_: dormir(0))
    estado = FSMContext(storage=bm.dp.storage, key=StorageKey(bot_id=bm.bot.id, chat_id=bm.ADMIN_ID,
                                                              user_id=bm.ADMIN_ID, thread_id=None))
    middleware = bm.InatividadeMiddleware()
    job_id = f"job_inatividade_{bm.ADMIN_ID}"

    async def menu_sem_fluxo(evento, dados):
        return None

    async def mostra_o_painel_inicial(evento, dados):
        await dados["state"].update_data(painel_atual="raiz")

    async def tocar(texto, handler):
        await middleware(handler, _admin_no_privado(bm, texto), {"state": estado})

    async def reiniciar():
        # O que um restart apaga: o cronômetro e o estado do painel.
        while bm.scheduler.get_job(job_id):   # parado, o scheduler guarda cada add_job
            bm.scheduler.remove_job(job_id)
        await estado.clear()
        bm.rearmar_inatividade_apos_reinicio()
        return bm.scheduler.get_job(job_id)

    async def cenario():
        await estado.clear()
        await tocar("Espelhador de Canais 🔄", menu_sem_fluxo)
        limite = bm.scheduler.get_job(job_id).trigger.run_date
        job = await reiniciar()
        assert job is not None and job.trigger.run_date == limite   # os mesmos 15 min de antes
        await bm.resetar_sessao_inatividade(*job.args)
        assert enviadas[-1] == "🏠 Painel Inicial restaurado."

        # Robô parado além dos 15 min: volta logo depois de ligar, e só uma vez.
        enviadas.clear()
        await tocar("Outros Canais 🗂️", menu_sem_fluxo)
        contagem = bm.db.ler_config(bm.CHAVE_INATIVIDADE)
        bm.db.salvar_config(bm.CHAVE_INATIVIDADE, {**contagem, "limite": (limite - bm.timedelta(hours=1)).isoformat()})
        job = await reiniciar()
        assert job.trigger.run_date > bm.datetime.now(bm.fuso_horario)
        await bm.resetar_sessao_inatividade(*job.args)
        assert enviadas[-1] == "🏠 Painel Inicial restaurado."
        assert await reiniciar() is None

        # Já estava no Painel Inicial quando o robô parou: nada a devolver.
        await tocar("Voltar ao Início 🔙", mostra_o_painel_inicial)
        assert await reiniciar() is None

    rodar(cenario())

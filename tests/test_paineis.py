"""Painéis do bot: SPAM, Cancelar das rotinas, painel do buscador e painel de ofertas do Grupo Público."""
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

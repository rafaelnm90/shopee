"""Painéis do bot: SPAM, Cancelar das rotinas e painel do buscador."""
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

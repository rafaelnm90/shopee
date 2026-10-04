"""Papel de cada conta (captura, repostagem ou as duas), conferência do canal e o menu de Contas."""
from types import SimpleNamespace

import pytest
from telethon import errors as E

from conftest import rodar


def nova(pc, apelido, funcoes="espelho,repostagem", no_grupo=True):
    pc.salvar_conta(apelido, sessao="x", funcoes_permitidas=funcoes)
    if no_grupo:
        pc.atualizar_status(apelido, status_grupo=pc.STATUS_NO_GRUPO, status_sessao=pc.SESSAO_OK)
    return pc.obter_conta(apelido)


def repostando(pc):
    return [c["apelido"] for c in pc.obter_contas_repostagem()]


def test_papel_captura_assume_o_posto_e_a_outra_vai_repostar(pc):
    nova(pc, "A")
    nova(pc, "B")
    pc.aplicar_funcoes()
    titular = pc.obter_conta_da_funcao(pc.FUNCAO_ESPELHO)["apelido"]
    outra = "B" if titular == "A" else "A"

    ok, msg, _ = pc.definir_papel(outra, pc.PAPEL_CAPTURA)

    assert ok and msg == "assumiu a captura"
    assert pc.obter_conta_da_funcao(pc.FUNCAO_ESPELHO)["apelido"] == outra
    assert pc.obter_conta(outra)["funcoes_permitidas"] == "espelho"
    assert repostando(pc) == [titular]
    assert pc.papel_da_conta(pc.obter_conta(outra)) == pc.PAPEL_CAPTURA
    assert pc.papel_da_conta(pc.obter_conta(titular)) == pc.PAPEL_AMBAS


def test_papel_repostagem_tira_da_captura(pc):
    nova(pc, "A")
    nova(pc, "B")
    pc.aplicar_funcoes()
    titular = pc.obter_conta_da_funcao(pc.FUNCAO_ESPELHO)["apelido"]

    pc.definir_papel(titular, pc.PAPEL_REPOSTAGEM)

    assert pc.obter_conta_da_funcao(pc.FUNCAO_ESPELHO)["apelido"] != titular
    assert titular in repostando(pc)


def test_papel_captura_fora_do_grupo_espera_entrar(pc):
    nova(pc, "A", no_grupo=False)
    ok, msg, _ = pc.definir_papel("A", pc.PAPEL_CAPTURA)
    assert ok and "assim que puder" in msg
    assert pc.obter_conta_da_funcao(pc.FUNCAO_ESPELHO) is None
    assert pc.papel_da_conta(pc.obter_conta("A")) == pc.PAPEL_CAPTURA


def test_papel_desconhecido_nao_muda_nada(pc):
    nova(pc, "A")
    assert pc.definir_papel("A", "outro")[0] is False
    assert pc.obter_conta("A")["funcoes_permitidas"] == "espelho,repostagem"


def test_captura_que_nao_publica_no_canal_fica_com_x(pc):
    nova(pc, "A", "espelho")
    pc.aplicar_funcoes()
    pc.marcar_publicacao_no_destino("A", False)
    texto = pc.montar_relatorio_telegram()
    assert "❌ <b>A</b>" in texto and "não é admin do seu canal" in texto
    pc.marcar_publicacao_no_destino("A", True)
    assert "✅ <b>A</b>" in pc.montar_relatorio_telegram()


def test_relatorio_em_palavras(pc):
    nova(pc, "A", "espelho")
    nova(pc, "B", "", no_grupo=False)
    pc.salvar_conta("B", funcoes_permitidas="nenhuma")
    pc.aplicar_funcoes()
    texto = pc.montar_relatorio_telegram()
    assert "🎯 Captura e publicação no seu canal" in texto
    assert "papel não escolhido" in texto and "ainda não conferida" in texto
    assert "pode:" not in texto


class Cliente:
    """TelegramClient falso para a conferência do canal."""

    def __init__(self, entidade, permissoes=None, erro=None, cache=True):
        self.entidade, self.permissoes, self.erro, self.cache = entidade, permissoes, erro, cache

    async def get_entity(self, alvo):
        if not self.cache:
            raise ValueError("cache vazio")
        return self.entidade

    async def get_dialogs(self):
        self.cache = True

    async def get_permissions(self, entidade, quem):
        if self.erro:
            raise self.erro
        return self.permissoes


def perm(admin=False, criador=False, publicar=False, banida=False):
    direitos = SimpleNamespace(post_messages=publicar) if admin else None
    return SimpleNamespace(is_admin=admin or criador, is_creator=criador, is_banned=banida,
                           participant=SimpleNamespace(admin_rights=direitos))


CANAL, GRUPO = SimpleNamespace(broadcast=True), SimpleNamespace(broadcast=False)


@pytest.mark.parametrize("entidade, permissoes, erro, cache, esperado", [
    (CANAL, perm(criador=True), None, True, True),
    (CANAL, perm(admin=True, publicar=True), None, True, True),
    (CANAL, perm(admin=True, publicar=False), None, True, False),   # admin sem "publicar mensagens"
    (CANAL, perm(), None, True, False),                             # membro comum do canal
    (CANAL, None, E.UserNotParticipantError(request=None), True, False),
    (CANAL, perm(admin=True, publicar=True), None, False, True),    # StringSession nova: carrega as conversas
    (GRUPO, perm(), None, True, True),                              # destino grupo: membro publica
    (GRUPO, perm(banida=True), None, True, False),
    (CANAL, None, E.FloodWaitError(request=None, capture=30), True, None),   # não conclui nada
])
def test_conferir_destino(pc, monkeypatch, entidade, permissoes, erro, cache, esperado):
    monkeypatch.setattr(pc, "obter_destino_autorais", lambda: -100999)
    conta = nova(pc, "A", "espelho")
    resultado = rodar(pc.conferir_destino(Cliente(entidade, permissoes, erro, cache), conta))
    assert resultado is esperado
    assert pc.obter_conta("A")["publica_no_destino"] == (None if esperado is None else int(esperado))


def test_destino_dos_autorais_lido_da_config(bm, pc):
    bm.db.salvar_config("autorais_config", {"destino": "-1004454448955:3"})
    assert pc.obter_destino_autorais() == -1004454448955
    bm.db.salvar_config("autorais_config", {"destino": "@videos_autorais"})
    assert pc.obter_destino_autorais() == "@videos_autorais"


# --- Menu ---

def textos(teclado):
    return [b.text for linha in teclado.keyboard for b in linha]


def test_contas_fica_dentro_do_menu_dos_autorais(bm):
    assert "Contas 👥" in textos(bm.teclado_menu_autorais)
    assert "Contas 👥" not in textos(bm.teclado_outros_canais)


def test_abrir_contas_mantem_o_menu_dos_autorais(bm, pc, Msg, Est):
    st = Est(estado=bm.AutoraisFluxo.menu_principal)
    msg = Msg("Contas 👥")
    rodar(bm.painel_contas_postos(msg, st))
    assert st.estado == bm.AutoraisFluxo.menu_principal
    assert "Contas dos Autorais" in msg.saidas[-1]


def test_cancelar_bloqueio_volta_para_a_lista_de_bloqueados(bm, pc, Msg, Est):
    st = Est(estado=bm.AutoraisFluxo.aguardando_bloqueio)
    msg = Msg("Cancelar ❌")
    rodar(bm.bl_receber_arroba(msg, st))
    assert st.estado == bm.AutoraisFluxo.menu_principal
    assert "Pessoas bloqueadas" in msg.saidas[-1]
    assert "Painel do Bot Vídeos Autorais" not in "".join(msg.saidas)

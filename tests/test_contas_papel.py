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


def test_painel_de_contas_no_padrao_lista_numerada_e_teclado(bm, pc, Msg, Est):
    nova(pc, "A", "espelho")
    nova(pc, "B", "repostagem", no_grupo=False)
    st = Est(estado=bm.AutoraisFluxo.menu_principal)
    msg = Msg("Contas 👥")
    rodar(bm.painel_contas_postos(msg, st))
    assert st.estado == bm.ContasFluxo.painel
    assert "<b>1</b> — <b>A</b>" in msg.saidas[-1] and "<b>2</b> — <b>B</b>" in msg.saidas[-1]
    teclado = [b.text for linha in bm.teclado_painel_contas(True).keyboard for b in linha]
    assert teclado == ["Cadastrar Conta ➕", "Gerenciar Conta 🔧", "Remover Conta 🗑️",
                       "Pessoas Bloqueadas 🚫", "Voltar ao Menu Autorais 🔙"]


def test_gerenciar_pelo_numero_e_excluir_com_confirmacao(bm, pc, Msg, Est):
    nova(pc, "A")
    nova(pc, "B")
    st = Est()
    rodar(bm.contas_pedir_numero(Msg("Gerenciar Conta 🔧"), st))
    errado = Msg("9")
    rodar(bm.contas_receber_numero(errado, st))
    assert "de 1 a 2" in errado.saidas[-1]
    tela = Msg("2")
    rodar(bm.contas_receber_numero(tela, st))
    assert st.estado == bm.ContasFluxo.conta and "<b>B</b>" in tela.saidas[-1]

    rodar(bm.contas_excluir(Msg("Excluir Conta 🗑️"), st))
    assert st.estado == bm.ContasFluxo.confirmando_exclusao
    rodar(bm.contas_confirmar_exclusao(Msg("qualquer coisa"), st))
    assert pc.obter_conta("B") is not None                 # só exclui com Aprovar
    rodar(bm.contas_confirmar_exclusao(Msg("Aprovar ✅"), st))
    assert pc.obter_conta("B") is None and st.estado == bm.ContasFluxo.painel


def test_remover_pelo_painel_e_cancelar_nao_exclui(bm, pc, Msg, Est):
    nova(pc, "A")
    st = Est()
    rodar(bm.contas_pedir_numero(Msg("Remover Conta 🗑️"), st))
    rodar(bm.contas_receber_numero(Msg("1"), st))
    assert st.estado == bm.ContasFluxo.confirmando_exclusao
    rodar(bm.contas_cancelar(Msg("Cancelar ❌"), st))
    assert pc.obter_conta("A") is not None and st.estado == bm.ContasFluxo.painel


def test_pausar_e_reativar(bm, pc, Msg, Est):
    nova(pc, "A")
    st = Est()
    rodar(bm.mostrar_conta(Msg(), st, pc.obter_conta("A")["id"]))
    rodar(bm.contas_pausar(Msg("Pausar Conta ⏸️"), st))
    assert not pc.obter_conta("A")["habilitada"]
    assert "Reativar Conta ▶️" in [b.text for linha in bm.teclado_gerenciar_conta(pc.obter_conta("A")).keyboard
                                   for b in linha]
    rodar(bm.contas_pausar(Msg("Reativar Conta ▶️"), st))
    assert pc.obter_conta("A")["habilitada"]


def test_bloquear_pessoa_pergunta_onde_vale(bm, pc, Msg, Est, monkeypatch):
    async def adicionar(alvo, escopo, motivo=""):
        bm.blacklist_captura.adicionar(username=alvo.lstrip("@"), escopo=escopo, motivo=motivo)
        return True, f"{alvo} bloqueado"
    monkeypatch.setattr(bm.blacklist_captura, "adicionar_por_arroba", adicionar)
    st = Est()
    rodar(bm.bloqueados_pedir_pessoa(Msg("Bloquear Pessoa ➕"), st))
    rodar(bm.bloqueados_receber_pessoa(Msg("@fulano"), st))
    assert st.estado == bm.ContasFluxo.aguardando_alcance
    final = Msg(bm.BOTAO_AUTORAIS_PARCEIROS)
    rodar(bm.bloqueados_confirmar_alcance(final, st))
    assert "<b>1</b> — @fulano · 🌐 Autorais e parceiros" in final.saidas[-1]
    assert st.estado == bm.ContasFluxo.bloqueados

    rodar(bm.bloqueados_pedir_numero(Msg("Desbloquear Pessoa 🗑️"), st))
    rodar(bm.bloqueados_desbloquear(Msg("1"), st))
    assert bm.blacklist_captura.manuais() == []


def test_cancelar_bloqueio_volta_para_a_lista_de_bloqueados(bm, pc, Msg, Est):
    st = Est(estado=bm.ContasFluxo.aguardando_bloqueio)
    msg = Msg("Cancelar ❌")
    rodar(bm.contas_cancelar(msg, st))
    assert st.estado == bm.ContasFluxo.bloqueados
    assert "Pessoas bloqueadas" in msg.saidas[-1]
    assert "Painel do Bot Vídeos Autorais" not in "".join(msg.saidas)


def test_botao_antigo_do_painel_avisa_onde_esta_o_menu(bm, Msg, Est):
    respostas = []

    async def answer(texto=None, **k):
        respostas.append(texto)
    cb = SimpleNamespace(data="pc_ver:1", answer=answer)
    rodar(bm.contas_botao_antigo(cb, Est()))
    assert "Vídeos Autorais 🎥 → Contas 👥" in respostas[0]


def test_contas_aparecem_sempre_pelo_telefone(bm, pc):
    pc.salvar_conta("espelhador", sessao="x", user_id=8001, telefone="5532999990001")
    pc.salvar_conta("rafaelnm", sessao="x", user_id=8002, username="Rafaelnm", telefone="+5532988880002")
    painel = pc.montar_relatorio_telegram()
    assert "<b>espelhador</b> · 📱 +55 32 99999-0001" in painel
    assert "<b>rafaelnm</b> · 📱 +55 32 98888-0002" in painel
    assert "@Rafaelnm" not in painel and "id 8001" not in painel
    bm.blacklist_captura.sincronizar_contas_do_pool()
    bloqueados = bm.blacklist_captura.montar_relatorio_telegram()
    assert "<b>espelhador</b> · 📱 +55 32 99999-0001" in bloqueados


def test_telefone_legivel(pc):
    assert pc.telefone_legivel("+55 (32) 99999-0001") == "+55 32 99999-0001"
    assert pc.telefone_legivel("553288880002") == "+55 32 8888-0002"
    assert pc.telefone_legivel("14155550100") == "+14155550100"
    assert pc.telefone_legivel(None) == "telefone ainda não lido"

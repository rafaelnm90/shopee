"""Painel de contas do bot: avisos no privado e cadastro de conta nova (➕ Nova conta)."""
import asyncio
from types import SimpleNamespace

import pytest
import telethon
from telethon import errors as E

from conftest import inserir, rodar


@pytest.fixture
def avisos(bm, monkeypatch):
    enviados = []

    async def send_message(chat, texto, **k):
        enviados.append(texto)
    monkeypatch.setattr(bm.bot, "send_message", send_message)
    return enviados


def conta(pc, apelido, funcoes="espelho,repostagem"):
    pc.salvar_conta(apelido, sessao="x", funcoes_permitidas=funcoes)
    pc.atualizar_status(apelido, status_grupo=pc.STATUS_NO_GRUPO, status_sessao=pc.SESSAO_OK)
    return pc.obter_conta(apelido)["id"]


def checar(bm, avisos):
    avisos.clear()
    rodar(bm.verificar_saude_contas())
    return avisos[0] if avisos else ""


def test_avisos_so_quando_muda(bm, pc, avisos):
    conta(pc, "A", "espelho")
    b = conta(pc, "B")
    conta(pc, "C")
    pc.aplicar_funcoes()
    assert checar(bm, avisos) == ""                    # deploy: tudo ✅, nada a avisar
    assert checar(bm, avisos) == ""
    pc.registrar_atividade(b, pc.FUNCAO_REPOSTAGEM, False, "ChatWriteForbiddenError")
    assert "❌" in checar(bm, avisos)
    assert checar(bm, avisos) == ""                    # não repete
    pc.registrar_atividade(b, pc.FUNCAO_REPOSTAGEM, True)
    assert "voltou a funcionar" in checar(bm, avisos)
    pc.atualizar_status("C", status_grupo=pc.STATUS_BANIDA_GRUPO)
    pc.aplicar_funcoes()
    assert "C</b> saiu (banida" in checar(bm, avisos)
    inserir("UPDATE contas_telegram SET ultima_checagem = '2026-01-01 00:00:00'")
    assert "robô dos Autorais pode estar parado" in checar(bm, avisos)


def test_primeira_rodada_avisa_o_que_ja_comeca_com_x(bm, pc, avisos):
    conta(pc, "unica")
    pc.aplicar_funcoes()
    assert "repostagem está parada" in checar(bm, avisos)
    assert checar(bm, avisos) == ""


# --- ➕ Nova conta ---

CONTAS = {"+5532999990001": {"codigo": "12345", "senha": None, "id": 501, "user": "repost_um"},
          "+5532999990002": {"codigo": "67890", "senha": "segredo", "id": 502, "user": None}}


class FakeTG:
    conectados = []

    def __init__(self, sessao, *a):
        self.conectado, self.tel = False, None
        self.session = SimpleNamespace(save=lambda: f"sessao-{self.tel}")

    async def connect(self):
        self.conectado = True
        FakeTG.conectados.append(self)

    async def disconnect(self):
        self.conectado = False

    async def send_code_request(self, tel):
        if tel not in CONTAS:
            raise E.PhoneNumberInvalidError(request=None)
        self.tel = tel
        return SimpleNamespace(phone_code_hash="hash")

    async def sign_in(self, phone=None, code=None, *, password=None, phone_code_hash=None):
        c = CONTAS[self.tel]
        if password is not None:
            if password != c["senha"]:
                raise E.PasswordHashInvalidError(request=None)
            return
        if code == "00000":
            raise E.PhoneCodeExpiredError(request=None)
        if code != c["codigo"]:
            raise E.PhoneCodeInvalidError(request=None)
        if c["senha"]:
            raise E.SessionPasswordNeededError(request=None)

    async def get_me(self):
        c = CONTAS[self.tel]
        return SimpleNamespace(id=c["id"], username=c["user"], first_name="Conta", last_name=None, phone=self.tel)


@pytest.fixture
def telegram(bm, pc, monkeypatch):
    """Login falso; a checagem do grupo responde conforme o conjunto no_grupo."""
    no_grupo = set()
    FakeTG.conectados = []
    monkeypatch.setattr(telethon, "TelegramClient", FakeTG)

    class Checagem:
        def __init__(self, conta):
            self.conta = conta

        async def get_me(self):
            return SimpleNamespace(id=self.conta["user_id"], username=self.conta["username"],
                                   first_name="Conta", last_name=None, phone=None)

        async def get_entity(self, g):
            return SimpleNamespace(id=g)

        async def get_permissions(self, e, quem):
            if self.conta["apelido"] not in no_grupo:
                raise E.UserNotParticipantError(request=None)
            return SimpleNamespace(is_banned=False)

        async def __call__(self, pedido):
            no_grupo.add(self.conta["apelido"])

        async def disconnect(self):
            pass

    async def criar_cliente(conta, conectar=True):
        return Checagem(conta)

    monkeypatch.setattr(pc, "criar_cliente", criar_cliente)
    monkeypatch.setattr(pc, "obter_grupo_autorais", lambda: -100123)
    monkeypatch.setattr(bm.blacklist_captura, "sincronizar_contas_do_pool", lambda: (1, 0))
    return no_grupo


def callback(bm, Msg, dados):
    return SimpleNamespace(data=dados, from_user=SimpleNamespace(id=bm.ADMIN_ID), message=Msg(),
                           answer=lambda *a, **k: asyncio.sleep(0))


def cadastrar(bm, Msg, st, telefone="+5532999990001", codigo="1 2 3 4 5"):
    """Cadastrar Conta ➕ → telefone → código. Devolve a mensagem do código."""
    rodar(bm.pool_nova_conta(Msg("Cadastrar Conta ➕"), st))
    rodar(bm.pool_nova_conta_telefone(Msg(telefone), st))
    msg = Msg(codigo)
    rodar(bm.pool_nova_conta_codigo(msg, st))
    return msg


def test_cadastro_sem_duas_etapas(bm, pc, telegram, Msg, Est):
    st = Est()
    codigo = cadastrar(bm, Msg, st, "+55 32 99999-0001")
    assert pc.obter_conta("repost_um") is not None
    assert codigo.apagada and st.estado == bm.ContasFluxo.aguardando_papel
    assert not FakeTG.conectados[-1].conectado


def test_cadastro_com_duas_etapas_e_erros(bm, pc, telegram, Msg, Est):
    st = Est()
    rodar(bm.pool_nova_conta(Msg("Cadastrar Conta ➕"), st))
    rodar(bm.pool_nova_conta_telefone(Msg("+5532999990002"), st))
    errado = Msg("1 1 1 1 1")
    rodar(bm.pool_nova_conta_codigo(errado, st))
    assert "Código errado" in errado.saidas[-1]
    rodar(bm.pool_nova_conta_codigo(Msg("6 7 8 9 0"), st))
    senha_errada = Msg("errada")
    rodar(bm.pool_nova_conta_senha(senha_errada, st))
    assert "Senha errada" in senha_errada.saidas[-1]
    senha = Msg("segredo")
    rodar(bm.pool_nova_conta_senha(senha, st))
    salva = pc.obter_conta("conta502")
    assert senha.apagada and senha_errada.apagada
    assert pc.decifrar(salva["senha_2fa_cifrada"]) == "segredo"
    assert b"segredo" not in (salva["senha_2fa_cifrada"] or b"")


def test_codigo_expirado_e_cancelar_desconectam_e_voltam_ao_painel(bm, telegram, Msg, Est):
    st = Est()
    expirado = cadastrar(bm, Msg, st, codigo="0 0 0 0 0")
    assert "expirou" in "".join(expirado.saidas) and not FakeTG.conectados[-1].conectado
    assert st.estado == bm.ContasFluxo.painel and "Contas dos Autorais" in expirado.saidas[-1]

    rodar(bm.pool_nova_conta(Msg("Cadastrar Conta ➕"), st))
    rodar(bm.pool_nova_conta_telefone(Msg("+5532999990001"), st))
    login = FakeTG.conectados[-1]
    cancelar = Msg("Cancelar ❌")
    rodar(bm.pool_nova_conta_cancelar_texto(cancelar, st))
    assert not login.conectado and st.estado == bm.ContasFluxo.painel
    assert "Cadastro de conta cancelado" in cancelar.saidas[0]


def test_prazo_de_resposta_cancela(bm, telegram, Msg, Est, monkeypatch):
    monkeypatch.setattr(bm, "MINUTOS_LOGIN_CONTA", 0.002)
    st = Est()
    avisos = []

    async def send_message(chat, texto, **k):
        avisos.append(texto)
    monkeypatch.setattr(bm.bot, "send_message", send_message)

    async def cenario():
        await bm.pool_nova_conta(Msg("Cadastrar Conta ➕"), st)
        await bm.pool_nova_conta_telefone(Msg("+5532999990001"), st)
        await asyncio.sleep(0.4)
    rodar(cenario())
    assert not FakeTG.conectados[-1].conectado and st.estado == bm.ContasFluxo.painel
    assert avisos and "cancelado" in avisos[-1]


def test_telefone_invalido(bm, telegram, Msg, Est):
    st = Est()
    rodar(bm.pool_nova_conta(Msg("Cadastrar Conta ➕"), st))
    msg = Msg("+5532999990009")
    rodar(bm.pool_nova_conta_telefone(msg, st))
    assert "não reconhece este número" in "".join(msg.saidas)
    assert st.estado == bm.ContasFluxo.painel


def botoes(teclado):
    return [b.text for linha in teclado.keyboard for b in linha]


def test_cadastro_pergunta_para_que_serve_com_dois_botoes(bm, pc, telegram, Msg, Est, monkeypatch):
    monkeypatch.setattr(pc, "obter_destino_autorais", lambda: -100777)
    st = Est()
    codigo = cadastrar(bm, Msg, st)
    assert "Para que serve esta conta?" in codigo.saidas[-1]
    assert "❌ não é admin" in codigo.saidas[-1]          # a conta falsa não está no canal
    assert botoes(bm.teclado_papel_conta) == [bm.BOTAO_CAPTURA, bm.BOTAO_REPOSTAGEM]

    escolha = Msg(bm.BOTAO_CAPTURA)
    rodar(bm.contas_definir_papel(escolha, st))
    assert pc.papel_da_conta(pc.obter_conta("repost_um")) == pc.PAPEL_CAPTURA
    tela = escolha.saidas[-1]
    assert "não está no grupo de origem" in tela and "não é admin do seu canal" in tela
    assert st.estado == bm.ContasFluxo.conta

    escolha = Msg(bm.BOTAO_REPOSTAGEM)
    rodar(bm.contas_definir_papel(escolha, st))
    assert pc.obter_conta("repost_um")["funcoes_permitidas"] == "repostagem"
    assert "admin" not in escolha.saidas[-1]               # quem só reposta não publica no canal


def test_colocar_no_grupo_pede_o_link_e_entra(bm, pc, telegram, Msg, Est):
    st = Est()
    cadastrar(bm, Msg, st)
    rodar(bm.contas_definir_papel(Msg(bm.BOTAO_REPOSTAGEM), st))
    conta_nova = pc.obter_conta("repost_um")
    assert "Colocar no Grupo 🚪" in botoes(bm.teclado_gerenciar_conta(conta_nova))

    pedido = Msg("Colocar no Grupo 🚪")
    rodar(bm.contas_colocar_no_grupo(pedido, st))          # sem link guardado: pede um
    assert "link de convite" in pedido.saidas[-1] and st.estado == bm.ContasFluxo.aguardando_convite
    rodar(bm.contas_salvar_convite(Msg("https://t.me/+AbCdEf"), st))
    assert pc.ler_convite() == "https://t.me/+AbCdEf"
    conta_nova = pc.obter_conta("repost_um")
    assert conta_nova["status_grupo"] == pc.STATUS_NO_GRUPO
    assert "Colocar no Grupo 🚪" not in botoes(bm.teclado_gerenciar_conta(conta_nova))


def test_cancelar_o_link_de_convite_volta_para_a_conta(bm, pc, telegram, Msg, Est):
    pc.salvar_conta("A", sessao="x")
    st = Est()
    rodar(bm.mostrar_conta(Msg(), st, pc.obter_conta("A")["id"]))
    rodar(bm.contas_colocar_no_grupo(Msg("Colocar no Grupo 🚪"), st))
    cancelar = Msg("Cancelar ❌")
    rodar(bm.contas_cancelar(cancelar, st))
    assert cancelar.saidas[0] == "❌ Nada foi alterado."
    assert st.estado == bm.ContasFluxo.conta and "<b>A</b>" in cancelar.saidas[-1]

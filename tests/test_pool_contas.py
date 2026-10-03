"""Pool de contas: revezamento, rodízio da repostagem, saúde e checagem."""
from types import SimpleNamespace

from conftest import inserir, rodar


def test_autoteste_do_revezamento(pc):
    assert pc.autoteste() is True


def conta(pc, apelido, funcoes="espelho,repostagem", status=None):
    pc.salvar_conta(apelido, sessao="x", funcoes_permitidas=funcoes)
    pc.atualizar_status(apelido, status_grupo=status or pc.STATUS_NO_GRUPO, status_sessao=pc.SESSAO_OK)
    return pc.obter_conta(apelido)["id"]


def test_rodizio_gravado_e_lido(pc):
    a, b, c = conta(pc, "A", "espelho"), conta(pc, "B"), conta(pc, "C")
    pc.aplicar_funcoes()
    assert pc.ler_ocupacao() == {pc.FUNCAO_ESPELHO: a, pc.FUNCAO_REPOSTAGEM: [b, c]}
    assert [x["apelido"] for x in pc.obter_contas_repostagem()] == ["B", "C"]
    assert pc.postos_da_conta(a) == [pc.FUNCAO_ESPELHO]


def test_ocupacao_antiga_de_uma_conta_vira_lista(pc):
    b = conta(pc, "B")
    inserir("UPDATE funcoes_contas SET conta_id = ?, contas_ids = NULL WHERE funcao = 'repostagem'", b)
    assert pc.ler_ocupacao()[pc.FUNCAO_REPOSTAGEM] == [b]


def test_captura_nao_entra_na_repostagem(pc):
    conta(pc, "unica")
    pc.aplicar_funcoes()
    ok, motivo = pc.atribuir_funcao("unica", pc.FUNCAO_REPOSTAGEM)
    assert not ok and "captura" in motivo
    assert pc.ler_ocupacao()[pc.FUNCAO_REPOSTAGEM] == []


def test_relatorio_mostra_check_e_x(pc):
    conta(pc, "A", "espelho")
    b = conta(pc, "B")
    pc.aplicar_funcoes()
    pc.registrar_atividade(b, pc.FUNCAO_REPOSTAGEM, False, "ChatWriteForbiddenError")
    texto = pc.montar_relatorio_telegram()
    assert "✅ <b>A</b>" in texto
    assert "❌ <b>B</b>" in texto and "ChatWriteForbiddenError" in texto


def test_sincronizar_reaproveita_cliente_conectado(pc, monkeypatch):
    class Fake:
        def __init__(self, nome, banida=False):
            self.nome, self.banida, self.conectado = nome, banida, True

        async def get_me(self):
            return SimpleNamespace(first_name=self.nome, last_name=None, username=None, id=7, phone=None)

        async def get_entity(self, g):
            return SimpleNamespace(id=g)

        async def get_permissions(self, e, quem):
            return SimpleNamespace(is_banned=self.banida)

        async def disconnect(self):
            self.conectado = False

    criados = []

    async def criar_cliente(conta, conectar=True):
        criados.append(Fake(conta["apelido"]))
        return criados[-1]

    async def sem_espera(*a):
        pass

    monkeypatch.setattr(pc, "criar_cliente", criar_cliente)
    monkeypatch.setattr(pc, "obter_grupo_autorais", lambda: -100123)
    monkeypatch.setattr(pc.asyncio, "sleep", sem_espera)
    for apelido in ("A", "B", "R"):
        pc.salvar_conta(apelido, sessao="x")
    pc.aplicar_funcoes()
    ativo_a, ativo_b = Fake("A"), Fake("B", banida=True)
    rodar(pc.sincronizar_pool(clientes={pc.obter_conta("A")["id"]: ativo_a,
                                        pc.obter_conta("B")["id"]: ativo_b}))

    assert ativo_a.conectado and ativo_b.conectado          # emprestados continuam conectados
    assert [f.nome for f in criados] == ["R"]               # só a reserva abriu conexão
    assert not criados[0].conectado
    assert pc.obter_conta("B")["status_grupo"] == pc.STATUS_BANIDA_GRUPO

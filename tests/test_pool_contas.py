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


class SemCache:
    """Conta de StringSession nova: get_entity por ID falha; o grupo só aparece nas conversas."""

    def __init__(self, conversas=(), erro=None):
        self.conversas, self.erro = conversas, erro

    async def get_me(self):
        return SimpleNamespace(first_name="X", last_name=None, username=None, id=7, phone=None)

    async def get_entity(self, alvo):
        raise ValueError("Could not find the input entity")

    async def iter_dialogs(self):
        if self.erro:
            raise self.erro
        for id_, saiu in self.conversas:
            yield SimpleNamespace(id=id_, entity=SimpleNamespace(id=id_, left=saiu))

    async def get_permissions(self, entidade, quem):
        return SimpleNamespace(is_banned=False)


def checar_sem_cache(pc, monkeypatch, cliente):
    from telethon import errors
    monkeypatch.setattr(pc, "obter_grupo_autorais", lambda: -100123)
    monkeypatch.setattr(pc, "obter_destino_autorais", lambda: None)
    pc.salvar_conta("A", sessao="x")
    rodar(pc.checar_conta(pc.obter_conta("A"), cliente=cliente))
    return pc.obter_conta("A"), errors


def test_checagem_acha_o_grupo_nas_conversas_sem_cache(pc, monkeypatch):
    conta_a, _ = checar_sem_cache(pc, monkeypatch, SemCache([(-100999, False), (-100123, False)]))
    assert conta_a["status_grupo"] == pc.STATUS_NO_GRUPO and not conta_a["ultimo_erro"]


def test_checagem_sem_o_grupo_nas_conversas_ou_com_saida(pc, monkeypatch):
    conta_a, _ = checar_sem_cache(pc, monkeypatch, SemCache([(-100999, False)]))
    assert conta_a["status_grupo"] == pc.STATUS_NUNCA_ENTROU
    assert conta_a["ultimo_erro"] == "o grupo de origem não está nas conversas da conta"
    pc.atualizar_status("A", status_grupo=pc.STATUS_NO_GRUPO)
    rodar(pc.checar_conta(pc.obter_conta("A"), cliente=SemCache([(-100123, True)])))
    assert pc.obter_conta("A")["status_grupo"] == pc.STATUS_SAIU


def test_checagem_com_erro_guarda_o_motivo_e_nao_muda_o_estado(pc, monkeypatch):
    from telethon import errors
    conta_a, _ = checar_sem_cache(pc, monkeypatch, SemCache(erro=errors.FloodWaitError(request=None, capture=300)))
    assert conta_a["status_grupo"] == pc.STATUS_DESCONHECIDO and "FloodWait" in conta_a["ultimo_erro"]
    rodar(pc.checar_conta(pc.obter_conta("A"), cliente=SemCache(erro=RuntimeError("rede caiu"))))
    conta_a = pc.obter_conta("A")
    assert conta_a["status_grupo"] == pc.STATUS_DESCONHECIDO
    assert conta_a["ultimo_erro"] == "RuntimeError: rede caiu"


def test_conta_sem_papel_tambem_tem_o_canal_conferido(pc, monkeypatch):
    conferidas = []

    async def conferir(cliente, conta):
        conferidas.append(conta["apelido"])
    monkeypatch.setattr(pc, "conferir_destino", conferir)
    monkeypatch.setattr(pc, "obter_grupo_autorais", lambda: -100123)
    for apelido, funcoes in (("sem_papel", "nenhuma"), ("captura", "espelho"), ("repost", "repostagem")):
        pc.salvar_conta(apelido, sessao="x", funcoes_permitidas=funcoes)
        rodar(pc.checar_conta(pc.obter_conta(apelido), cliente=SemCache([(-100123, False)])))
    assert conferidas == ["sem_papel", "captura"]          # quem só reposta não publica no canal
    pc.marcar_publicacao_no_destino("sem_papel", True)
    assert "📣 canal: ✅ pode publicar" in pc.montar_relatorio_telegram().split("sem_papel")[1]


def test_grupo_proibido_nas_conversas_e_banimento(pc, monkeypatch):
    class Proibido(SemCache):
        async def iter_dialogs(self):
            yield SimpleNamespace(id=-100123, entity=type("ChannelForbidden", (), {"left": False})())
    conta_a, _ = checar_sem_cache(pc, monkeypatch, Proibido())
    assert conta_a["status_grupo"] == pc.STATUS_BANIDA_GRUPO
    assert conta_a["ultimo_erro"] == "banida do grupo de origem"


def test_entrar_no_grupo_banida_avisa_e_marca(pc, monkeypatch):
    from telethon import errors

    class Cliente:
        async def __call__(self, pedido):
            raise errors.ChannelPrivateError(request=None)

        async def disconnect(self):
            pass

    async def criar_cliente(conta, conectar=True):
        return Cliente()
    monkeypatch.setattr(pc, "criar_cliente", criar_cliente)
    pc.salvar_conta("A", sessao="x")
    pc.guardar_convite("https://t.me/+AbCdEf")
    ok, mensagem = rodar(pc.entrar_no_grupo("A"))
    assert not ok and "banida do grupo de origem" in mensagem
    assert pc.obter_conta("A")["status_grupo"] == pc.STATUS_BANIDA_GRUPO

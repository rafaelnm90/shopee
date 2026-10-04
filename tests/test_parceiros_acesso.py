"""Captura dos parceiros: a conta da captura precisa ser membro do canal de origem, não só achá-lo."""
from types import SimpleNamespace

import pytest

from conftest import consultar, inserir, rodar


class Cliente:
    """Cliente do Telethon falso: guarda os pedidos de entrada em canal."""

    def __init__(self):
        self.pedidos = []

    async def __call__(self, pedido):
        self.pedidos.append(type(pedido).__name__)


@pytest.fixture
def canais(esp, monkeypatch):
    """Canais vistos pela conta: alvo -> entidade (left=True = acha, mas não é membro)."""
    vistos = {}

    async def resolver(alvo):
        return vistos.get(str(alvo).strip())

    async def nada(*a, **k):
        pass
    monkeypatch.setattr(esp, "resolver_entidade", resolver)
    monkeypatch.setattr(esp, "client", Cliente())
    monkeypatch.setattr(esp.asyncio, "sleep", nada)
    return vistos


def test_achar_o_canal_publico_nao_basta_entra_nele(esp, canais):
    canais["@canal_parceiro"] = SimpleNamespace(id=10, left=True)
    assert rodar(esp.entrar_no_canal_parceiro("@canal_parceiro")) == (True, "entrou pelo @username")
    assert esp.client.pedidos == ["JoinChannelRequest"]


def test_ja_membro_nao_pede_entrada(esp, canais):
    canais["@canal_parceiro"] = SimpleNamespace(id=10, left=False)
    assert rodar(esp.entrar_no_canal_parceiro("@canal_parceiro"))[0] is True
    assert esp.client.pedidos == []


def test_id_numerico_sem_ser_membro_explica_o_que_fazer(esp, canais):
    ok, motivo = rodar(esp.entrar_no_canal_parceiro("-1001234567890"))
    assert not ok and "adicione a conta" in motivo


def _parceiro(bm, nome, origem):
    pid = bm.salvar_parceiro({"nome": nome, "app_id": "123456", "app_secret": "x" * 20,
                              "canal_origem": origem, "canal_destino": "-1001"})
    bm.atualizar_parceiro(pid, "origem_ok", 1)
    return pid


def test_reconferencia_tira_o_acesso_de_quem_nao_e_membro(bm, esp, canais):
    fora = _parceiro(bm, "Fora", "@fora")
    dentro = _parceiro(bm, "Dentro", "@dentro")
    sumiu = _parceiro(bm, "Sem rede", "@sem_rede")       # @ que não resolveu agora: fica como está
    canais["@fora"] = SimpleNamespace(id=1, left=True)
    canais["@dentro"] = SimpleNamespace(id=2, left=False)

    rodar(esp.reconferir_parceiros_com_acesso())

    estado = {pid: consultar("SELECT origem_ok FROM parceiros WHERE id = ?", pid)[0] for pid in (fora, dentro, sumiu)}
    assert estado == {fora: 0, dentro: 1, sumiu: 1}
    assert "não está no canal" in consultar("SELECT origem_erro FROM parceiros WHERE id = ?", fora)[0]


def test_parceiro_sem_acesso_aparece_no_resumo_e_no_alerta(bm, monkeypatch):
    pid = _parceiro(bm, "Loja", "@loja")
    bm.atualizar_parceiro(pid, "origem_ok", 0)
    bm.atualizar_parceiro(pid, "origem_erro", "a conta da captura não está no canal de origem")
    inserir("CREATE TABLE IF NOT EXISTS fila_parceiros (id_unico TEXT PRIMARY KEY, parceiro_id INTEGER, "
            "caminho_video TEXT, link_original TEXT, data_captura TEXT, data_alvo TEXT, "
            "horario_disparo TEXT DEFAULT '', processado INTEGER DEFAULT 0, data_postagem TEXT DEFAULT '')")
    inserir("INSERT INTO fila_parceiros (id_unico, parceiro_id, data_captura, data_alvo, processado) "
            "VALUES ('a', ?, '2026-09-15 10:30:00', '2026-10-15', 1)", pid)

    resumo = bm.resumo_fila_parceiro(bm.buscar_parceiro(pid), [], "2026-10-04", 0)
    assert "não está no canal de origem" in resumo and "15/09 às 10:30" in resumo

    avisos = []

    async def send_message(chat, texto, **k):
        avisos.append(texto)
    monkeypatch.setattr(bm.bot, "send_message", send_message)
    rodar(bm.monitor_saude())
    rodar(bm.monitor_saude())
    assert sum("Parceiro Loja sem captura" in a for a in avisos) == 1

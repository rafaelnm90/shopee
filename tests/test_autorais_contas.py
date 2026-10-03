"""Robô dos Autorais com as contas do pool: captura separada e rodízio da repostagem."""
import os
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from telethon import errors as E

from conftest import consultar, inserir, rodar


class FakeClient:
    def __init__(self, nome):
        self.nome, self.falha, self.handlers, self.conectado, self.enviados = nome, None, [], True, []

    def add_event_handler(self, f, ev):
        self.handlers.append(f)

    def remove_event_handler(self, f):
        self.handlers = [h for h in self.handlers if h is not f]

    async def disconnect(self):
        self.conectado = False

    async def get_dialogs(self):
        return []

    async def get_entity(self, x):
        return SimpleNamespace(title="g", username=None, id=1)

    async def get_me(self):
        return SimpleNamespace(first_name=self.nome, username=None, id=abs(hash(self.nome)) % 100000)

    async def start(self):
        pass

    async def send_file(self, destino, file=None, caption=None, parse_mode=None, **k):
        if self.falha:
            raise self.falha
        self.enviados.append(caption)
        return SimpleNamespace(id=len(self.enviados))


@pytest.fixture
def contas(pc, esp, monkeypatch):
    """A só captura; B e C podem as duas. Devolve o dicionário apelido → FakeClient."""
    fakes = {}

    async def criar_cliente(conta, conectar=True):
        fakes[conta["apelido"]] = FakeClient(conta["apelido"])
        return fakes[conta["apelido"]]

    monkeypatch.setattr(pc, "criar_cliente", criar_cliente)
    for apelido, funcoes in (("A", "espelho"), ("B", "espelho,repostagem"), ("C", "espelho,repostagem")):
        pc.salvar_conta(apelido, sessao="x", funcoes_permitidas=funcoes)
        pc.atualizar_status(apelido, status_grupo=pc.STATUS_NO_GRUPO, status_sessao=pc.SESSAO_OK)
    pc.aplicar_funcoes()
    return fakes


def quem(esp):
    captura = esp.conta_captura["apelido"] if esp.conta_captura else None
    return captura, [esp.clientes_repost[c][0]["apelido"] for c in esp.ordem_rodizio if c in esp.clientes_repost]


def test_sem_pool_usa_sessao_fixa(esp, monkeypatch):
    monkeypatch.setattr(esp, "TelegramClient", lambda *a: FakeClient("fixa"))
    rodar(esp.montar_contas())
    assert esp.modo_sessao_fixa and esp.client.handlers
    assert esp.proxima_conta_repost() == (None, esp.client)


def test_captura_e_rodizio_separados(esp, contas):
    rodar(esp.montar_contas())
    assert quem(esp) == ("A", ["B", "C"])
    assert contas["A"].handlers and not contas["B"].handlers and not contas["C"].handlers
    ordem = []
    for _ in range(4):
        conta, _cli = esp.proxima_conta_repost()
        ordem.append(conta["apelido"])
        esp.registrar_envio_repost(conta)
    assert ordem == ["B", "C", "B", "C"]


def test_conta_expulsa_sai_do_rodizio(esp, contas, pc):
    rodar(esp.montar_contas())
    conta_b = esp.proxima_conta_repost()[0]
    assert rodar(esp.registrar_falha_repost(conta_b, E.UserBannedInChannelError(request=None)))
    assert pc.obter_conta("B")["status_grupo"] == pc.STATUS_BANIDA_GRUPO
    assert quem(esp)[1] == ["C"] and not contas["B"].conectado


def test_sem_permissao_descansa(esp, contas):
    rodar(esp.montar_contas())
    for conta, _cli in list(esp.clientes_repost.values()):
        assert rodar(esp.registrar_falha_repost(conta, E.ChatWriteForbiddenError(request=None)))
    assert esp.proxima_conta_repost() is None


def test_captura_cai_e_conta_do_rodizio_assume(esp, contas, pc):
    rodar(esp.montar_contas())
    pc.atualizar_status("A", status_grupo=pc.STATUS_SAIU)
    pc.aplicar_funcoes()
    rodar(esp.montar_contas())
    assert quem(esp) == ("B", ["C"])
    assert esp.client.handlers and not contas["A"].conectado


@pytest.fixture
def fila_retorno(esp):
    agora = datetime.now()
    esp.salvar_config_autorais({"origem": -100123, "destino": -100456, "dias_retorno": 15,
                                "inicio": 0, "fim": 24, "limite_min": 10, "limite_max": 10})
    esp.ler_fila_retorno()
    captura = agora - timedelta(days=20)

    def item(i):
        caminho = f"archive/v{i}.mp4"
        open(caminho, "wb").write(b"v")
        os.utime(caminho, (captura.timestamp(), captura.timestamp()))
        inserir("INSERT INTO fila_autorais (id_unico, caminho_arquivo, legenda, data_alvo, horario_disparo, "
                "processado, data_captura) VALUES (?,?,?,?,?,0,?)",
                f"v{i}", caminho, f"legenda {i}", agora.strftime("%Y-%m-%d"),
                (agora - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"), captura.strftime("%Y-%m-%d %H:%M:%S"))
    return item


class FimCiclo(BaseException):
    pass


def um_ciclo(esp, monkeypatch):
    async def parar(*a, **k):
        raise FimCiclo()
    with monkeypatch.context() as m:
        m.setattr(esp.asyncio, "sleep", parar)
        try:
            rodar(esp.processar_fila_autorais_loop())
        except FimCiclo:
            pass


def estado(i):
    return consultar("SELECT processado, horario_disparo FROM fila_autorais WHERE id_unico = ?", f"v{i}")


def test_loop_de_repostagem_com_rodizio(esp, contas, pc, fila_retorno, monkeypatch):
    rodar(esp.montar_contas())
    fila_retorno(1)
    um_ciclo(esp, monkeypatch)
    fila_retorno(2)
    um_ciclo(esp, monkeypatch)
    assert estado(1)[0] == 1 and estado(2)[0] == 1
    assert (len(contas["B"].enviados), len(contas["C"].enviados), len(contas["A"].enviados)) == (1, 1, 0)

    # B expulsa: o vídeo não é adiado e sai pela C no ciclo seguinte.
    fila_retorno(3)
    contas["B"].falha = E.UserBannedInChannelError(request=None)
    horario = estado(3)[1]
    um_ciclo(esp, monkeypatch)
    assert estado(3) == (0, horario)
    um_ciclo(esp, monkeypatch)
    assert estado(3)[0] == 1 and len(contas["C"].enviados) == 2
    assert not contas["A"].enviados                       # a captura nunca posta na origem

    # Sem conta disponível: o vídeo espera mantendo o horário.
    fila_retorno(4)
    contas["C"].falha = E.ChatWriteForbiddenError(request=None)
    um_ciclo(esp, monkeypatch)
    um_ciclo(esp, monkeypatch)
    assert estado(4)[0] == 0 and estado(4)[1] <= datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    erros = sqlite3.connect("banco_dados.db").execute(
        "SELECT COUNT(*) FROM atividade_contas WHERE ultimo_erro IS NOT NULL").fetchone()[0]
    assert erros == 2

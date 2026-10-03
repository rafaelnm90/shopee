"""
Base dos testes: ambiente falso, pasta temporária e fakes do Telegram.

Os robôs leem o .env e gravam em caminhos relativos (banco_dados.db, temp/,
archive/). Aqui as variáveis são montadas na hora (nenhuma credencial real, nada
com cara de token para o GitGuardian) e cada teste roda numa pasta vazia, com
banco novo. Nada toca a rede: Telegram e IA são substituídos por fakes.

Rodar: python3 -m pytest tests -q
Opções (o CI usa as duas, em várias rodadas):
  --ordem aleatoria   embaralha a ordem dos testes; a semente sai no fim, e
                      --ordem <semente> repete a mesma ordem.
  --relogio HH:MM     cada teste começa nessa hora de Brasília (de hoje), com o
                      relógio andando a partir dali.
"""
import asyncio
import importlib
import logging
import os
import random
import sqlite3
import sys
import tempfile
from types import SimpleNamespace

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from cryptography.fernet import Fernet  # noqa: E402

os.environ.update({
    "TELEGRAM_TOKEN": "123456789:" + "A" * 35,
    "TELEGRAM_TOKEN_DOWNLOADER": "123456789:" + "B" * 35,
    "API_ID": "12345",
    "API_HASH": "0" * 32,
    "GEMINI_KEY": "teste",
    "SHOPEE_APP_ID": "1",
    "SHOPEE_APP_SECRET": "teste",
    "BREVO_API_KEY": "teste",
    "BREVO_SENHA": "teste",
    "GMAIL_SENHA": "teste",
    "EMAIL_REMETENTE_NOTAS": "teste@exemplo.com",
    "NOME_REMETENTE_NOTAS": "teste",
    "CHAVE_MESTRA_CONTAS": Fernet.generate_key().decode(),
})

# A importação dos robôs já cria pastas e arquivos (temp/notas_fiscais, sessões):
# que seja numa pasta descartável, uma vez, antes de qualquer teste. Importados só
# no primeiro teste que os usa, as sobras cairiam na pasta desse teste, e o
# resultado dependeria da ordem em que os testes rodam.
os.chdir(tempfile.mkdtemp(prefix="shopee_testes_"))
for _modulo in ("bot_mestre", "pool_contas", "espelhador_videos_autorais", "divulgacao_canal"):
    importlib.import_module(_modulo)

import pytest  # noqa: E402
import time_machine  # noqa: E402
from datetime import datetime  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

FUSO_TESTES = ZoneInfo("America/Sao_Paulo")


def pytest_addoption(parser):
    parser.addoption("--ordem", default=None, metavar="aleatoria|SEMENTE",
                     help="Embaralha a ordem dos testes; com um número, repete uma ordem anterior.")
    parser.addoption("--relogio", default=None, metavar="HH:MM[:SS]",
                     help="Cada teste começa nessa hora de Brasília; o relógio anda a partir dali.")


def _semente(config):
    ordem = config.getoption("--ordem")
    if not ordem:
        return None
    if not hasattr(config, "_semente_ordem"):
        config._semente_ordem = random.randrange(10**6) if ordem == "aleatoria" else int(ordem)
    return config._semente_ordem


def pytest_collection_modifyitems(config, items):
    # Teste que só passa numa certa ordem depende de sobra deixada por outro teste.
    semente = _semente(config)
    if semente is not None:
        random.Random(semente).shuffle(items)


def pytest_terminal_summary(terminalreporter, config):
    if config.getoption("--relogio"):
        terminalreporter.write_line(f"Relógio dos testes: {config.getoption('--relogio')} (Brasília)")
    semente = _semente(config)
    if semente is not None:
        terminalreporter.write_line(f"Ordem aleatória: semente {semente} (repita com --ordem {semente})")


def _instante(hora):
    h, m, *s = (int(x) for x in hora.split(":"))
    return datetime.now(FUSO_TESTES).replace(hour=h, minute=m, second=s[0] if s else 0, microsecond=0)


@pytest.fixture(autouse=True)
def relogio_da_rodada(request):
    """Com --relogio, todo teste roda naquela hora: o CI passa a suíte de madrugada, de dia e de noite."""
    hora = request.config.getoption("--relogio")
    if not hora:
        yield
        return
    with time_machine.travel(_instante(hora), tick=True):
        yield


@pytest.fixture
def relogio():
    """relogio("15:00"): o teste passa a acontecer nessa hora de Brasília, com o relógio andando."""
    viagens = []

    def fixar(hora):
        viagem = time_machine.travel(_instante(hora), tick=True)
        viagem.start()
        viagens.append(viagem)
    yield fixar
    for viagem in reversed(viagens):
        viagem.stop()


@pytest.fixture(autouse=True)
def pasta_limpa(tmp_path, monkeypatch):
    """Cada teste numa pasta vazia: banco, temp/ e archive/ novos."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("temp", exist_ok=True)
    os.makedirs("archive", exist_ok=True)
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture
def bm(monkeypatch):
    """bot_mestre com banco novo, agendador novo e sem esperas (asyncio.sleep instantâneo)."""
    import bot_mestre
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    bot_mestre.inicializar_banco_sqlite()
    monkeypatch.setattr(bot_mestre, "scheduler", AsyncIOScheduler(timezone=bot_mestre.FUSO_STR))
    bot_mestre._login_conta.clear()
    return bot_mestre


@pytest.fixture
def pc():
    import pool_contas
    pool_contas.inicializar_tabelas()
    return pool_contas


@pytest.fixture
def esp(monkeypatch):
    """espelhador_videos_autorais com as contas zeradas."""
    import espelhador_videos_autorais as modulo
    for nome, valor in (("client", None), ("conta_captura", None), ("modo_sessao_fixa", False),
                        ("clientes_repost", {}), ("ordem_rodizio", []), ("_espera_repost", {}),
                        ("_ultimo_repostador", None)):
        monkeypatch.setattr(modulo, nome, valor)
    return modulo


class Mensagem:
    """Mensagem do Telegram falsa: guarda o que o bot respondeu e se foi apagada."""

    def __init__(self, texto="", user_id=None, saidas=None):
        import bot_mestre
        self.text = texto
        self.html_text = texto
        self.from_user = SimpleNamespace(id=user_id or bot_mestre.ADMIN_ID, username=None, first_name="Admin")
        self.chat = SimpleNamespace(id=1)
        self.message_id = 1
        self.apagada = False
        self.saidas = saidas if saidas is not None else []

    async def answer(self, texto, **kwargs):
        self.saidas.append(texto)
        return Mensagem(texto, saidas=self.saidas)

    async def edit_text(self, texto, **kwargs):
        self.saidas.append(texto)
        return self

    async def delete(self):
        self.apagada = True


class Estado:
    """FSMContext falso."""

    def __init__(self, dados=None, estado=None):
        self.estado, self.dados = estado, dict(dados or {})

    async def get_state(self):
        return getattr(self.estado, "state", self.estado)

    async def set_state(self, estado):
        self.estado = estado

    async def clear(self):
        self.estado, self.dados = None, {}

    async def get_data(self):
        return dict(self.dados)

    async def update_data(self, **kwargs):
        self.dados.update(kwargs)


@pytest.fixture
def Msg():
    return Mensagem


@pytest.fixture
def Est():
    return Estado


def rodar(coro):
    """asyncio.run com nome curto."""
    return asyncio.run(coro)


def inserir(sql, *params):
    conexao = sqlite3.connect("banco_dados.db")
    conexao.execute(sql, params)
    conexao.commit()
    conexao.close()


def consultar(sql, *params):
    conexao = sqlite3.connect("banco_dados.db")
    linha = conexao.execute(sql, params).fetchone()
    conexao.close()
    return linha

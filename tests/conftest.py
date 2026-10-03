"""
Base dos testes: ambiente falso, pasta temporária e fakes do Telegram.

Os robôs leem o .env e gravam em caminhos relativos (banco_dados.db, temp/,
archive/). Aqui as variáveis são montadas na hora (nenhuma credencial real, nada
com cara de token para o GitGuardian) e cada teste roda numa pasta vazia, com
banco novo. Nada toca a rede: Telegram e IA são substituídos por fakes.

Rodar: python3 -m pytest tests -q
"""
import asyncio
import logging
import os
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

# A importação dos robôs já cria arquivos: que seja fora do repositório.
os.chdir(tempfile.mkdtemp(prefix="shopee_testes_"))

import pytest  # noqa: E402


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

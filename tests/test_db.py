"""db.py: conexão única, modo WAL e a tabela configuracoes."""
import glob
import json
import os
import re
import sqlite3
import time

import pytest

import db

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _criar_fila():
    with db.conexao() as conexao:
        conexao.execute("CREATE TABLE fila (id INTEGER PRIMARY KEY, status TEXT)")
        conexao.executemany("INSERT INTO fila (status) VALUES (?)", [("PENDENTE",)] * 5)


def _criar_configuracoes():
    with db.conexao() as conexao:
        conexao.execute("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")


def test_nenhum_robo_abre_o_banco_por_fora():
    # Conexão aberta direto no sqlite3 fica sem WAL e sem a espera pelo lock.
    padrao = re.compile(r"\bsqlite3\.connect\(")
    culpados = []
    for caminho in glob.glob(os.path.join(RAIZ, "*.py")):
        if os.path.basename(caminho) == "db.py":
            continue
        with open(caminho, encoding="utf-8") as f:
            for numero, linha in enumerate(f, 1):
                if padrao.search(linha):
                    culpados.append(f"{os.path.basename(caminho)}:{numero}")
    assert culpados == [], "use db.conectar() ou db.conexao(): " + ", ".join(culpados)


def test_conexao_sai_em_wal_e_espera_o_lock():
    conexao = db.conectar()
    assert conexao.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conexao.execute("PRAGMA busy_timeout").fetchone()[0] == db.ESPERA_LOCK_S * 1000
    conexao.close()


def test_leitura_aberta_nao_trava_gravacao_de_outro_robo():
    # Robô A lê um item da fila e segura a leitura enquanto envia o vídeo; o robô B
    # grava nesse meio-tempo. Sem WAL, B esperava os 30 s e dava "database is locked".
    _criar_fila()
    robo_a = db.conectar()
    cursor_a = robo_a.cursor()
    cursor_a.execute("SELECT * FROM fila WHERE status = 'PENDENTE'")
    cursor_a.fetchone()

    robo_b = db.conectar()
    inicio = time.monotonic()
    robo_b.execute("UPDATE fila SET status = 'OUTRO' WHERE id = 5")
    robo_b.commit()
    assert time.monotonic() - inicio < 2

    # A volta do envio e marca o item no mesmo cursor, como o canal principal faz.
    cursor_a.execute("UPDATE fila SET status = 'CONCLUIDO' WHERE id = 1")
    robo_a.commit()
    robo_a.close()
    robo_b.close()

    with db.conexao() as conexao:
        status = dict(conexao.execute("SELECT id, status FROM fila").fetchall())
    assert status[1] == "CONCLUIDO" and status[5] == "OUTRO"


def test_conexao_grava_no_fim_e_desfaz_no_erro():
    _criar_fila()
    with db.conexao() as conexao:
        conexao.execute("UPDATE fila SET status = 'OK' WHERE id = 1")

    with pytest.raises(RuntimeError):
        with db.conexao() as conexao:
            conexao.execute("UPDATE fila SET status = 'PELA_METADE' WHERE id = 2")
            raise RuntimeError("falhou no meio")

    with db.conexao(linhas_por_nome=True) as conexao:
        linhas = {linha["id"]: linha["status"] for linha in conexao.execute("SELECT id, status FROM fila")}
    assert linhas[1] == "OK"
    assert linhas[2] == "PENDENTE"


def test_conexao_fecha_mesmo_com_erro():
    with pytest.raises(RuntimeError):
        with db.conexao() as conexao:
            guardada = conexao
            raise RuntimeError("falhou")
    with pytest.raises(sqlite3.ProgrammingError):
        guardada.execute("SELECT 1")


def test_config_grava_le_e_devolve_padrao():
    _criar_configuracoes()
    assert db.ler_config("nao_existe") == {}
    assert db.ler_config("nao_existe", {"alvos": []}) == {"alvos": []}

    assert db.salvar_config("rotina", {"ativo": True, "texto": "Bom dia ☀️"}) is True
    assert db.ler_config("rotina") == {"ativo": True, "texto": "Bom dia ☀️"}

    db.salvar_config("rotina", {"ativo": False})
    assert db.ler_config("rotina") == {"ativo": False}


def test_config_sem_tabela_nao_quebra():
    # Banco recém-criado, antes de o bot_mestre criar as tabelas.
    assert db.ler_config("qualquer", {"x": 1}) == {"x": 1}
    assert db.salvar_config("qualquer", {"x": 2}) is False


def test_config_migra_arquivo_legado():
    _criar_configuracoes()
    with open("antiga.json", "w", encoding="utf-8") as f:
        json.dump({"alvos": ["@canal"]}, f)

    assert db.ler_config("alvos", {}, arquivo_legado="antiga.json") == {"alvos": ["@canal"]}
    assert not os.path.exists("antiga.json")
    assert os.path.exists("antiga.json.bkp")
    assert db.ler_config("alvos") == {"alvos": ["@canal"]}


def test_sqlite_de_terceiros_tambem_espera_o_lock():
    # As sessões .session do Telethon abrem o SQLite sozinhas, sem passar pelo db.
    conexao = sqlite3.connect("sessao_qualquer.session")
    assert conexao.execute("PRAGMA busy_timeout").fetchone()[0] == db.ESPERA_LOCK_S * 1000
    conexao.close()

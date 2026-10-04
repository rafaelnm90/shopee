"""Faxina do servidor: guarda antes de apagar, só mexe no que está na lista e não repete."""
import os
import sqlite3

import db
import faxina_servidor as fx


def _servidor(pasta):
    banco = os.path.join(pasta, "banco_dados.db")
    with db.conexao(banco) as con:
        con.execute("CREATE TABLE configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
        con.execute("INSERT INTO configuracoes VALUES ('fila_espelhador', '{\"fila\": []}'), ('banco_pedidos', '{}')")
        con.execute("CREATE TABLE financeiro_despesas (valor REAL)")
        con.execute("INSERT INTO financeiro_despesas VALUES (10.5), (3)")
        con.execute("CREATE TABLE mensagens_topico (msg_id INTEGER)")
        con.execute("CREATE TABLE fila_publico (id INTEGER)")
        con.execute("INSERT INTO fila_publico VALUES (1)")
    os.makedirs(os.path.join(pasta, "variantes"))
    for nome in ("conferir.png", "banco_dados.bak-2026-08-31.db", "contador.txt"):
        with open(os.path.join(pasta, nome), "w") as f:
            f.write("x")
    return banco


def test_sem_executar_so_mostra(tmp_path):
    banco = _servidor(str(tmp_path))
    relatorio = fx.faxinar(str(tmp_path), str(tmp_path / "antigos"))
    assert "tabela financeiro_despesas: 2 linha(s)" in relatorio and "arquivo variantes" in relatorio
    assert not (tmp_path / "antigos").exists() and (tmp_path / "conferir.png").exists()
    with db.conexao(banco) as con:
        assert con.execute("SELECT COUNT(*) FROM financeiro_despesas").fetchone()[0] == 2


def test_executar_guarda_apaga_e_move_so_o_da_lista(tmp_path):
    banco = _servidor(str(tmp_path))
    antigos = tmp_path / "antigos"

    fx.faxinar(str(tmp_path), str(antigos), executar=True)

    with db.conexao(banco) as con:
        tabelas = {linha[0] for linha in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        chaves = [linha[0] for linha in con.execute("SELECT chave FROM configuracoes")]
    assert tabelas == {"configuracoes", "fila_publico"} and chaves == ["banco_pedidos"]
    sobrou = set(os.listdir(tmp_path))
    assert "contador.txt" in sobrou and not sobrou & {"variantes", "conferir.png", "banco_dados.bak-2026-08-31.db"}
    guarda = [n for n in os.listdir(antigos) if n.startswith("tabelas_sem_uso_")][0]
    copia = sqlite3.connect(antigos / guarda)
    assert copia.execute("SELECT SUM(valor) FROM financeiro_despesas").fetchone()[0] == 13.5
    assert copia.execute("SELECT chave FROM configuracoes_sem_uso").fetchall() == [("fila_espelhador",)]
    copia.close()
    assert {"variantes", "conferir.png", "banco_dados.bak-2026-08-31.db"} <= set(os.listdir(antigos))

    assert fx.faxinar(str(tmp_path), str(antigos), executar=True) == ["Nada a fazer: tudo já saiu."]

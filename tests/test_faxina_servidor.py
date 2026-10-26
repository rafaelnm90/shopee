"""Faxina do servidor: guarda antes de apagar, só mexe no que está na lista e não repete."""
import os
import sqlite3

import pytest

import db
import faxina_servidor as fx

# A de verdade, guardada antes de a fixture abaixo trocá-la em cada teste.
SOBRAS = fx.sobras_do_android


@pytest.fixture(autouse=True)
def sem_docker_nem_pip(tmp_path, monkeypatch):
    # Os testes nunca tocam no Docker nem no cache do pip de quem roda os testes.
    monkeypatch.setattr(fx, "sobras_do_android", lambda: [])
    monkeypatch.setattr(fx, "CACHE_DO_PIP", str(tmp_path / "cache_pip_que_nao_existe"))


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


def test_android_virtual_e_cache_do_pip_saem_sem_copia(tmp_path, monkeypatch):
    # Escolha do Rafael (P42): a imagem do Android virtual (sem uso desde 05/10) e o cache
    # velho do pip saem; os dois se baixam de novo quando precisar.
    pasta = tmp_path / "servidor"
    pasta.mkdir()
    cache = tmp_path / "pip"
    (cache / "http").mkdir(parents=True)
    (cache / "http" / "pacote").write_bytes(b"x" * 2048)
    monkeypatch.setattr(fx, "CACHE_DO_PIP", str(cache))
    monkeypatch.setattr(fx.android_virtual, "estado_conteiner", lambda: "exited")
    comandos = []

    def docker(*partes):
        comandos.append(partes)
        return 0, ""
    monkeypatch.setattr(fx, "_docker", docker)
    monkeypatch.setattr(fx, "sobras_do_android", SOBRAS)
    relatorio = fx.faxinar(str(pasta), str(tmp_path / "antigos"))
    assert any("Android virtual no Docker: contêiner" in linha for linha in relatorio)
    assert any("Android virtual no Docker: imagem" in linha for linha in relatorio)
    assert any(linha.startswith("cache do pip:") for linha in relatorio)
    assert cache.exists() and not any(p[0] in ("rm", "rmi") for p in comandos)   # só mostrou

    relatorio = fx.faxinar(str(pasta), str(tmp_path / "antigos"), executar=True)
    assert [p[0] for p in comandos if p[0] in ("rm", "rmi")] == ["rm", "rmi"]    # o contêiner antes da imagem
    assert "imagem do Android virtual: apagada" in relatorio and not cache.exists()
    # Os .bkp das migrações para o banco saem como os outros arquivos velhos.
    assert {"fila_espelhador.json.bkp", "espelhos_config.json.bkp"} <= set(fx.ARQUIVOS_VELHOS)


def test_android_ligado_nao_sai(monkeypatch):
    # Se alguém voltou a usar o Android virtual, a faxina não mexe nele.
    monkeypatch.setattr(fx.android_virtual, "estado_conteiner", lambda: "running")
    monkeypatch.setattr(fx, "_docker", lambda *partes: (0, ""))
    assert SOBRAS() == []

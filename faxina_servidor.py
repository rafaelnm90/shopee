"""
Faxina pontual do servidor: tira o que a auditoria achou sem uso, sem apagar
nada que não tenha cópia. Roda à mão pelo workflow faxina.yml ou no servidor:

    python3 faxina_servidor.py              # só mostra o que faria
    python3 faxina_servidor.py --executar   # faz

- Tabelas que nenhum código usa e chaves mortas de configuracoes: copiadas
  para ~/backups/antigos/tabelas_sem_uso_AAAA-MM-DD_HHMM.db e só então apagadas
  do banco (a cópia é conferida linha a linha antes).
- Arquivos e pastas velhos da pasta do projeto: movidos para ~/backups/antigos.

As listas abaixo são fechadas e só têm o que foi conferido: nenhum código lê,
grava ou cria de novo. Imprime só nomes e números, porque o log do Actions é
público. Decisão do Rafael: DECISOES.md, Código e manutenção.
"""
import os
import shutil
import sys
from datetime import datetime

import db

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
DESTINO = os.path.expanduser("~/backups/antigos")

TABELAS_SEM_USO = (
    "fila_espelhador", "fila_espiao",                  # as duas filas moram em chaves de configuracoes
    "financeiro_despesas", "financeiro_saques", "historico_financeiro", "pedidos_financeiro",
    "mensagens_topico",                                # a faxina do Baixador não guarda mais mensagens
)
CHAVES_SEM_USO = ("fila_espelhador",)                  # cópia velha da fila; a de agora é fila_espelhador.CHAVE
ARQUIVOS_VELHOS = (
    "banco_dados.bak-2026-08-31.db", "banco_dados.bak-2026-08-31.dbsqlite3",
    "banco_dados.bak-2026-09-01-noite.db", "backup_dados.tar.gz",
    "conferir.png", "registro_hashes.json", "variantes",
)


def _levantar(banco):
    """(tabelas existentes com linhas, chaves existentes com tamanho) da lista."""
    with db.conexao(banco) as con:
        existentes = {linha[0] for linha in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        tabelas = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                   for t in TABELAS_SEM_USO if t in existentes}
        chaves = {}
        if "configuracoes" in existentes:
            for chave in CHAVES_SEM_USO:
                linha = con.execute("SELECT LENGTH(valor) FROM configuracoes WHERE chave = ?", (chave,)).fetchone()
                if linha:
                    chaves[chave] = linha[0] or 0
    return tabelas, chaves


def _guardar_e_apagar(banco, guarda, tabelas, chaves):
    """Copia tabelas e chaves para o arquivo de guarda, confere e só então apaga do banco."""
    with db.conexao(banco) as con:
        con.execute("ATTACH DATABASE ? AS guarda", (guarda,))
        for tabela in tabelas:
            con.execute(f'CREATE TABLE guarda."{tabela}" AS SELECT * FROM main."{tabela}"')
        if chaves:
            con.execute("CREATE TABLE guarda.configuracoes_sem_uso (chave TEXT PRIMARY KEY, valor TEXT)")
            for chave in chaves:
                con.execute("INSERT INTO guarda.configuracoes_sem_uso SELECT chave, valor FROM main.configuracoes "
                            "WHERE chave = ?", (chave,))
        con.commit()
        for tabela, linhas in tabelas.items():
            copiadas = con.execute(f'SELECT COUNT(*) FROM guarda."{tabela}"').fetchone()[0]
            if copiadas != linhas:
                raise RuntimeError(f"cópia de {tabela} com {copiadas} de {linhas} linha(s); nada foi apagado")
        con.execute("DETACH DATABASE guarda")
        for tabela in tabelas:
            con.execute(f'DROP TABLE main."{tabela}"')
        for chave in chaves:
            con.execute("DELETE FROM configuracoes WHERE chave = ?", (chave,))


def faxinar(pasta=None, destino=None, executar=False):
    """Mostra (e com executar=True faz) a faxina. Devolve as linhas do relatório."""
    pasta, destino = pasta or PASTA_PROJETO, destino or DESTINO
    banco = os.path.join(pasta, db.ARQUIVO_BANCO)
    relatorio = []
    tabelas, chaves = _levantar(banco) if os.path.exists(banco) else ({}, {})
    arquivos = [nome for nome in ARQUIVOS_VELHOS if os.path.exists(os.path.join(pasta, nome))]

    for tabela, linhas in tabelas.items():
        relatorio.append(f"tabela {tabela}: {linhas} linha(s)")
    for chave, tamanho in chaves.items():
        relatorio.append(f"chave {chave}: {tamanho / 1024:.1f} KB")
    for nome in arquivos:
        relatorio.append(f"arquivo {nome}")
    if not relatorio:
        return ["Nada a fazer: tudo já saiu."]
    if not executar:
        return relatorio + ["(só mostrando; com --executar, faz)"]

    os.makedirs(destino, mode=0o700, exist_ok=True)
    if tabelas or chaves:
        guarda = os.path.join(destino, f"tabelas_sem_uso_{datetime.now():%Y-%m-%d_%H%M}.db")
        _guardar_e_apagar(banco, guarda, tabelas, chaves)
        os.chmod(guarda, 0o600)
        relatorio.append(f"{len(tabelas)} tabela(s) e {len(chaves)} chave(s) guardadas em {guarda} e apagadas do banco")
    for nome in arquivos:
        alvo = os.path.join(destino, nome)
        if os.path.exists(alvo):
            alvo += f".{datetime.now():%Y%m%d%H%M%S}"
        shutil.move(os.path.join(pasta, nome), alvo)
    if arquivos:
        relatorio.append(f"{len(arquivos)} arquivo(s)/pasta(s) movidos para {destino}")
    return relatorio


if __name__ == "__main__":
    try:
        for linha in faxinar(executar="--executar" in sys.argv[1:]):
            print(linha)
    except Exception as e:
        print(f"❌ Faxina parou: {type(e).__name__}: {e}")
        sys.exit(1)

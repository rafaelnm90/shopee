"""
Faxina pontual do servidor: tira o que a auditoria achou sem uso, sem apagar
nada que não tenha cópia. Roda à mão pelo workflow faxina.yml ou no servidor:

    python3 faxina_servidor.py              # só mostra o que faria
    python3 faxina_servidor.py --executar   # faz

- Tabelas que nenhum código usa e chaves mortas de configuracoes: copiadas
  para ~/backups/antigos/tabelas_sem_uso_AAAA-MM-DD_HHMM.db e só então apagadas
  do banco (a cópia é conferida linha a linha antes).
- Arquivos e pastas velhos da pasta do projeto: movidos para ~/backups/antigos.
- O que se baixa de novo quando precisar sai sem cópia: o contêiner parado e a
  imagem do Android virtual no Docker (sem uso desde 05/10/2026; o android.yml
  preparar baixa e cria de novo) e o cache velho do pip (o deploy instala sem
  cache). Escolha do Rafael (P42): DECISOES.md, Monitor, deploy e servidor.

As listas abaixo são fechadas e só têm o que foi conferido: nenhum código lê,
grava ou cria de novo. Imprime só nomes e números, porque o log do Actions é
público. Decisão do Rafael: DECISOES.md, Código e manutenção.
"""
import os
import shutil
import sys
from datetime import datetime

import android_virtual
import db
import fila_espelhador
import rotas_espelhador

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
DESTINO = os.path.expanduser("~/backups/antigos")

TABELAS_SEM_USO = (
    "fila_espelhador", "fila_espiao",                  # as duas filas moram em chaves de configuracoes
    "financeiro_despesas", "financeiro_saques", "historico_financeiro", "pedidos_financeiro",
    "mensagens_topico",                                # a faxina do Baixador não guarda mais mensagens
)
CHAVES_SEM_USO = ("fila_espelhador",                   # cópia velha da fila; a de agora é fila_espelhador.CHAVE
                  "grupos_autorais")                   # a marca por grupo: todos os grupos são autorais
ARQUIVOS_VELHOS = (
    "banco_dados.bak-2026-08-31.db", "banco_dados.bak-2026-08-31.dbsqlite3",
    "banco_dados.bak-2026-09-01-noite.db", "backup_dados.tar.gz",
    "conferir.png", "registro_hashes.json", "variantes",
    fila_espelhador.ARQUIVO + ".bkp", rotas_espelhador.ARQUIVO + ".bkp",   # sobras das migrações para o banco
)
CACHE_DO_PIP = os.path.expanduser("~/.cache/pip")


def _docker(*partes):
    return android_virtual._rodar("sudo", "-n", "docker", *partes, timeout=300)


def sobras_do_android():
    """
    O que sobrou do Android virtual no Docker: "contêiner" (parado) e "imagem", os que
    existem. Com o contêiner ligado, nada: alguém voltou a usar o Android.
    """
    estado = android_virtual.estado_conteiner()
    if estado == "running":
        return []
    sobras = ["contêiner"] if estado else []
    r = _docker("image", "inspect", "--format", "{{.Size}}", android_virtual.IMAGEM)
    if r and r[0] == 0:
        sobras.append("imagem")
    return sobras


def _tamanho_da_pasta(caminho):
    total = 0
    for raiz, _pastas, arquivos in os.walk(caminho):
        for nome in arquivos:
            try:
                total += os.path.getsize(os.path.join(raiz, nome))
            except OSError:
                pass
    return total


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
    android = sobras_do_android()
    cache_pip = CACHE_DO_PIP if os.path.isdir(CACHE_DO_PIP) else None

    for tabela, linhas in tabelas.items():
        relatorio.append(f"tabela {tabela}: {linhas} linha(s)")
    for chave, tamanho in chaves.items():
        relatorio.append(f"chave {chave}: {tamanho / 1024:.1f} KB")
    for nome in arquivos:
        relatorio.append(f"arquivo {nome}")
    for sobra in android:
        relatorio.append(f"Android virtual no Docker: {sobra} (sem cópia; o android.yml preparar baixa de novo)")
    if cache_pip:
        relatorio.append(f"cache do pip: {_tamanho_da_pasta(cache_pip) / 1024 ** 2:.1f} MB (sem cópia; se baixa de novo)")
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
    # O contêiner sai antes da imagem: o Docker não apaga a imagem de um contêiner que existe.
    if "contêiner" in android:
        r = _docker("rm", android_virtual.CONTEINER)
        relatorio.append(f"contêiner do Android virtual: {'apagado' if r and r[0] == 0 else 'não saiu'}")
    if "imagem" in android:
        r = _docker("rmi", android_virtual.IMAGEM)
        relatorio.append(f"imagem do Android virtual: {'apagada' if r and r[0] == 0 else 'não saiu'}")
    if cache_pip:
        shutil.rmtree(cache_pip, ignore_errors=True)
        relatorio.append(f"cache do pip: {'apagado' if not os.path.exists(cache_pip) else 'não saiu todo'}")
    return relatorio


if __name__ == "__main__":
    try:
        for linha in faxinar(executar="--executar" in sys.argv[1:]):
            print(linha)
    except Exception as e:
        print(f"❌ Faxina parou: {type(e).__name__}: {e}")
        sys.exit(1)

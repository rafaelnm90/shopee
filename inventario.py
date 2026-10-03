#!/usr/bin/env python3
"""
Inventário do servidor: o que ocupa espaço e o que cresce. Roda no servidor pelo
workflow inventario.yml (disparo manual) ou à mão: venv/bin/python3 inventario.py

Só lê. Como o repositório é público e os logs do Actions também, imprime apenas
números e nomes que já estão no código (tabelas, chaves de configuração, pastas
do projeto, trechos fixos das mensagens de log). Nunca o conteúdo dos logs, das
filas ou do banco; ids de parceiro também não.

Seções: pastas do projeto, arquivos soltos, banco, filas em arquivo, journal (com
as linhas de log que mais se repetem e de onde vêm no código) e fora do projeto.
"""
import ast
import glob
import json
import os
import re
import subprocess
import time

import db

SERVICOS = ("bot_mestre_bot", "divulgacao_canal_bot", "motor_userbot_bot",
            "espelhador_videos_autorais_bot", "downloader_bot")
PASTA = os.path.dirname(os.path.abspath(__file__))


def tamanho_legivel(n):
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidade == "GB":
            return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}"
        n /= 1024


def medir(caminho):
    """(bytes, arquivos, idade em dias do arquivo mais antigo) de uma pasta."""
    total, qtd, mais_antigo = 0, 0, None
    for raiz, _dirs, arquivos in os.walk(caminho):
        for nome in arquivos:
            try:
                st = os.stat(os.path.join(raiz, nome))
            except OSError:
                continue
            total += st.st_size
            qtd += 1
            mais_antigo = st.st_mtime if mais_antigo is None else min(mais_antigo, st.st_mtime)
    idade = (time.time() - mais_antigo) / 86400 if mais_antigo else 0
    return total, qtd, idade


def secao(titulo):
    print(f"\n== {titulo}")


def pastas_do_projeto():
    secao("Pastas do projeto")
    for nome in sorted(os.listdir(PASTA)):
        caminho = os.path.join(PASTA, nome)
        if not os.path.isdir(caminho):
            continue
        total, qtd, idade = medir(caminho)
        extra = ""
        if nome == "parceiros":
            extra = f" | {len(os.listdir(caminho))} parceiro(s)"
        print(f"{nome + '/':24} {tamanho_legivel(total):>9} | {qtd:6} arquivo(s) | mais antigo: {idade:.0f} dia(s){extra}")


def arquivos_soltos():
    secao("Arquivos soltos na pasta do projeto (fora do git)")
    try:
        saida = subprocess.run(["git", "ls-files"], cwd=PASTA, capture_output=True, text=True).stdout
        do_git = set(saida.split())
    except Exception:
        do_git = set()
    por_tipo, grandes = {}, []
    for nome in os.listdir(PASTA):
        caminho = os.path.join(PASTA, nome)
        if not os.path.isfile(caminho) or nome in do_git:
            continue
        tamanho = os.path.getsize(caminho)
        tipo = os.path.splitext(nome)[1] or "(sem extensão)"
        qtd, soma = por_tipo.get(tipo, (0, 0))
        por_tipo[tipo] = (qtd + 1, soma + tamanho)
        if tamanho >= 100 * 1024:
            grandes.append((tamanho, nome))
    for tipo, (qtd, soma) in sorted(por_tipo.items(), key=lambda x: -x[1][1]):
        print(f"{tipo:16} {qtd:4} arquivo(s) {tamanho_legivel(soma):>9}")
    for tamanho, nome in sorted(grandes, reverse=True)[:15]:
        print(f"   {tamanho_legivel(tamanho):>9}  {nome}")


def banco():
    secao("Banco")
    for sufixo in ("", "-wal", "-shm"):
        caminho = os.path.join(PASTA, db.ARQUIVO_BANCO + sufixo)
        if os.path.exists(caminho):
            print(f"{db.ARQUIVO_BANCO + sufixo:24} {tamanho_legivel(os.path.getsize(caminho)):>9}")
    with db.conexao() as conexao:
        print(f"modo: {conexao.execute('PRAGMA journal_mode').fetchone()[0]}")
        tabelas = [t for (t,) in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for t in tabelas:
            linhas = conexao.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            print(f"   {t:28} {linhas:8} linha(s)")
        print("Configurações mais pesadas (tabela configuracoes):")
        for chave, tamanho in conexao.execute(
                "SELECT chave, LENGTH(valor) FROM configuracoes ORDER BY LENGTH(valor) DESC LIMIT 10"):
            print(f"   {chave:32} {tamanho_legivel(tamanho or 0):>9}")


def filas_em_arquivo():
    secao("Filas em arquivo")
    for nome in ("fila_espelhador.json", "espelhos_config.json"):
        caminho = os.path.join(PASTA, nome)
        if not os.path.exists(caminho):
            continue
        print(f"{nome:24} {tamanho_legivel(os.path.getsize(caminho)):>9}")
    try:
        with open(os.path.join(PASTA, "fila_espelhador.json"), encoding="utf-8") as f:
            fila = json.load(f).get("fila", [])
        with open(os.path.join(PASTA, "espelhos_config.json"), encoding="utf-8") as f:
            rotas = {r.get("nome") for r in json.load(f).get("rotas", [])}
        processados = [i for i in fila if i.get("processado")]
        orfaos = [i for i in fila if i.get("nome_rota") not in rotas]
        datas = sorted(i.get("data_postagem") or "" for i in processados if i.get("data_postagem"))
        print(f"   fila do Espelhador: {len(fila)} item(ns), {len(processados)} já processado(s), "
              f"{len(orfaos)} de rota que não existe mais")
        if datas:
            print(f"   processado mais antigo ainda na fila: {datas[0]}")
    except Exception as e:
        print(f"   (não deu para ler a fila do Espelhador: {type(e).__name__})")


def modelos_de_log():
    """
    Trechos fixos de cada logger.info/warning/error do código, com arquivo e linha.
    Um f-string vira o texto fixo com um coringa no lugar de cada variável.
    """
    modelos = []
    for arq in glob.glob(os.path.join(PASTA, "*.py")):
        try:
            arvore = ast.parse(open(arq, encoding="utf-8").read())
        except SyntaxError:
            continue
        for n in ast.walk(arvore):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("debug", "info", "warning", "error", "critical")
                    and getattr(n.func.value, "id", "") == "logger" and n.args):
                continue
            partes = []
            arg = n.args[0]
            for p in (arg.values if isinstance(arg, ast.JoinedStr) else [arg]):
                if isinstance(p, ast.Constant) and isinstance(p.value, str):
                    partes.append(re.escape(p.value))
                else:
                    partes.append(".*?")
            fixo = "".join(p for p in partes if p != ".*?")
            if len(fixo) < 6:
                continue
            pedacos = arg.values if isinstance(arg, ast.JoinedStr) else [arg]
            texto = "".join(p.value if isinstance(p, ast.Constant) and isinstance(p.value, str) else "{…}"
                            for p in pedacos)
            primeiro = pedacos[0]
            inicio = primeiro.value[:1] if isinstance(primeiro, ast.Constant) and isinstance(primeiro.value, str) else ""
            modelos.append((re.compile("^" + "".join(partes), re.S), f"{os.path.basename(arq)}:{n.lineno}",
                            texto.replace("\n", " ")[:70], len(fixo), inicio))
    # O mais específico primeiro: o de texto fixo maior ganha.
    modelos.sort(key=lambda m: -m[3])
    return modelos


def perfil_do_log(linhas, modelos):
    """Conta quantas linhas do journal saíram de cada chamada de log do código."""
    # Cada linha só é comparada com os modelos que começam pelo mesmo caractere
    # (quase sempre o emoji), mais os que começam por uma variável.
    por_inicio, genericos = {}, []
    for m in modelos:
        (por_inicio.setdefault(m[4], []) if m[4] else genericos).append(m)
    contagem, sem_modelo = {}, 0
    for linha in linhas:
        mensagem = linha.split(" - ", 1)[1] if " - " in linha else linha
        for regex, onde, texto, _, _inicio in por_inicio.get(mensagem[:1], []) + genericos:
            if regex.match(mensagem):
                contagem[(onde, texto)] = contagem.get((onde, texto), 0) + 1
                break
        else:
            sem_modelo += 1
    return sorted(contagem.items(), key=lambda x: -x[1]), sem_modelo


def journal():
    secao("Journal (logs do sistema)")
    try:
        uso = subprocess.run(["sudo", "-n", "journalctl", "--disk-usage"], capture_output=True, text=True, timeout=30)
        print((uso.stdout or uso.stderr).strip().splitlines()[-1])
    except Exception as e:
        print(f"(sem acesso ao journal: {type(e).__name__})")
        return
    modelos = modelos_de_log()
    for servico in SERVICOS:
        r = subprocess.run(["sudo", "-n", "journalctl", "-u", f"{servico}.service", "--since", "24 hours ago",
                            "-o", "cat", "-q"], capture_output=True, text=True, timeout=120)
        linhas = [l for l in r.stdout.splitlines() if l.strip()]
        print(f"\n{servico}: {len(linhas)} linha(s) nas últimas 24 h")
        if not linhas:
            continue
        ranking, sem_modelo = perfil_do_log(linhas, modelos)
        for (onde, texto), qtd in ranking[:8]:
            print(f"   {qtd:6} ({qtd * 100 / len(linhas):4.1f}%)  {onde:34} {texto}")
        if sem_modelo:
            print(f"   {sem_modelo:6} ({sem_modelo * 100 / len(linhas):4.1f}%)  sem modelo no código "
                  "(bibliotecas, rastros de erro, linhas quebradas)")


def fora_do_projeto():
    secao("Fora do projeto")
    casa = os.path.expanduser("~")
    for nome in ("backups", ".cache/pip", ".cache/yt-dlp", ".cache"):
        caminho = os.path.join(casa, nome)
        if os.path.isdir(caminho):
            total, qtd, idade = medir(caminho)
            print(f"~/{nome + '/':20} {tamanho_legivel(total):>9} | {qtd:6} arquivo(s) | mais antigo: {idade:.0f} dia(s)")
    total, qtd, _ = 0, 0, None
    for caminho in glob.glob("/tmp/*"):
        try:
            if os.stat(caminho).st_uid != os.getuid():
                continue
        except OSError:
            continue
        t, q, _i = medir(caminho) if os.path.isdir(caminho) else (os.path.getsize(caminho), 1, 0)
        total, qtd = total + t, qtd + q
    print(f"/tmp (do usuário)        {tamanho_legivel(total):>9} | {qtd:6} arquivo(s)")
    print("Memória de cada robô:")
    for servico in SERVICOS:
        r = subprocess.run(["systemctl", "show", "-p", "MemoryCurrent", "--value", f"{servico}.service"],
                           capture_output=True, text=True)
        valor = r.stdout.strip()
        print(f"   {servico:32} {tamanho_legivel(int(valor)) if valor.isdigit() else valor:>9}")


if __name__ == "__main__":
    os.chdir(PASTA)
    for parte in (pastas_do_projeto, arquivos_soltos, banco, filas_em_arquivo, journal, fora_do_projeto):
        try:
            parte()
        except Exception as e:
            print(f"(falhou: {type(e).__name__})")

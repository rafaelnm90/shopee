#!/usr/bin/env python3
"""
Inventário do servidor: o que ocupa espaço e o que cresce. Roda no servidor pelo
workflow inventario.yml (disparo manual) ou à mão: venv/bin/python3 inventario.py

Só lê. Como o repositório é público e os logs do Actions também, imprime apenas
números e nomes que já estão no código (tabelas, chaves de configuração, pastas
do projeto, trechos fixos das mensagens de log). Nunca o conteúdo dos logs, das
filas ou do banco; ids de parceiro também não.

Seções: pastas do projeto, arquivos soltos, banco, erros por origem e tipo, filas
em arquivo, captura dos parceiros, contas dos Autorais (só estados), onde os links do
Espião levam (só o tipo de cada página), journal (com as linhas de log que mais se repetem e de onde vêm no
código), o Baixador hora a hora (só contagens), versões das bibliotecas, fora do projeto e se o servidor aguenta um
Android virtual (para o robô da Shopee Vídeo).
"""
import ast
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import time
import urllib.parse

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


def erros_registrados():
    """
    O erros_logs por origem e tipo de exceção (a última linha do rastro). O texto
    do erro não sai: pode ter dados. Os detalhes ficam no /status do bot.
    """
    secao("Erros registrados (tabela erros_logs, os 50 mais recentes)")
    with db.conexao() as conexao:
        linhas = conexao.execute("SELECT timestamp, origem, erro, rastro_codigo FROM erros_logs").fetchall()
    if not linhas:
        print("nenhum")
        return
    corte = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 86400))
    grupos = {}
    for quando, origem, erro, rastro in linhas:
        tipo = "(sem rastro)"
        for linha in reversed((rastro or "").strip().splitlines()):
            m = re.match(r"^([A-Za-z_][\w.]*(?:Error|Exception|Wait|Invalid|Forbidden|Timeout)\w*)\b", linha.strip())
            if m:
                tipo = m.group(1)
                break
        else:
            m = re.search(r"\b([A-Z]\w+(?:Error|Exception|Wait|Invalid|Forbidden|Timeout)\w*)\b", erro or "")
            if m:
                tipo = m.group(1)
        # De onde: o começo fixo do erro ("enviar_mensagem (", "varredura_origem_loop:").
        onde = re.split(r"[ :(]", (erro or "").strip(), 1)[0][:40] or "?"
        chave = (origem or "?", onde, tipo)
        total, recentes, ultimo = grupos.get(chave, (0, 0, ""))
        grupos[chave] = (total + 1, recentes + (1 if (quando or "") >= corte else 0), max(ultimo, quando or ""))
    for (origem, onde, tipo), (total, recentes, ultimo) in sorted(grupos.items(), key=lambda x: -x[1][0]):
        print(f"{total:4}x ({recentes:3} nas últimas 24 h)  {origem:30} {onde:28} {tipo:32} último: {ultimo}")


def versoes():
    secao("Versões instaladas (bibliotecas sem versão fixa no requirements.txt)")
    from importlib import metadata
    for nome in ("telethon", "pandas", "matplotlib", "google-genai", "aiogram", "yt-dlp"):
        try:
            print(f"{nome:16} {metadata.version(nome)}")
        except metadata.PackageNotFoundError:
            print(f"{nome:16} (não instalado)")


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


def captura_dos_parceiros():
    """
    O que o robô dos Autorais contou hoje de cada origem de parceiro (chave
    diagnostico_parceiros). Só o número do parceiro, contagens e os motivos de
    recusa, que são textos fixos do código: nada de nome de canal ou de pessoa.
    """
    secao("Captura dos parceiros (contagem do robô dos Autorais)")
    try:
        dados = db.ler_config("diagnostico_parceiros", {}) or {}
    except Exception as e:
        print(f"   (não deu para ler: {type(e).__name__})")
        return
    if not dados:
        print("   nada contado ainda")
        return
    for pid, dia in sorted(dados.items()):
        print(f"parceiro #{pid} em {dia.get('data')}: {dia.get('mensagens', 0)} mensagem(ns), "
              f"{dia.get('videos', 0)} vídeo(s), {dia.get('com_link', 0)} com link, "
              f"{dia.get('capturados', 0)} capturado(s); última mensagem {dia.get('ultima_mensagem') or 'nenhuma'}")
        for motivo, qtd in sorted((dia.get("recusados") or {}).items(), key=lambda x: -x[1]):
            print(f"   recusado: {motivo} ({qtd})")


# Partes fixas de endereço da Shopee, que podem aparecer no desenho do link. Qualquer
# outra parte (nome de produto, de loja, códigos) vira um marcador.
ROTAS_CONHECIDAS = {
    "opaanlp", "product", "universal-link", "search", "an_redir", "m", "mall", "shop", "buyer",
    "login", "verify", "captcha", "find_similar_products", "collections", "list", "landing",
    "deep_link", "web", "affiliate", "event", "events", "promo", "flash_sale", "daily_discover",
    "user", "cart", "share", "api", "v4", "item", "items", "app", "download", "redirect",
}


# Nomes de parâmetro que podem aparecer no desenho; os outros só são contados.
PARAMETROS_CONHECIDOS = {
    "lp", "itemid", "shopid", "catid", "keyword", "origin_link", "affiliate_id", "sub_id", "next",
    "redir", "url", "publisher_id", "smtt", "xptdk", "deep_and_deferred", "share_channel_code",
    "scene", "from", "entrypoint", "is_from_login", "page", "ref",
}
PREFIXOS_CONHECIDOS = ("utm_", "gads_", "mmp_", "af_", "sp_", "uls_")


def forma_do_link(url):
    """
    O desenho do link, sem nada que identifique produto, loja ou pessoa: o host, as
    partes fixas do caminho (as de ROTAS_CONHECIDAS), números como #<quantos dígitos>,
    o resto como <texto>, e só os nomes dos parâmetros. Serve para o inventário mostrar
    por onde a Shopee manda o servidor sem pôr links no log público.
    """
    partes = urllib.parse.urlsplit(url or "")
    pedacos = []
    for parte in partes.path.split("/"):
        if not parte:
            continue
        if parte.lower() in ROTAS_CONHECIDAS:
            pedacos.append(parte.lower())
        elif parte.isdigit():
            pedacos.append(f"#{len(parte)}")
        elif re.search(r"-i\.\d+\.\d+$", parte):
            pedacos.append("<nome>-i.#.#")
        elif re.search(r"-cat\.[\d.]+$", parte):
            pedacos.append("<nome>-cat.#")
        else:
            pedacos.append("<texto>")
    nomes = {nome for nome, _ in urllib.parse.parse_qsl(partes.query, keep_blank_values=True)}
    conhecidos = sorted(n for n in nomes if n.lower() in PARAMETROS_CONHECIDOS
                        or n.lower().startswith(PREFIXOS_CONHECIDOS))
    outros = len(nomes) - len(conhecidos)
    desenho = f"{partes.netloc.lower()}/{'/'.join(pedacos)}"
    if conhecidos or outros:
        desenho += " ?" + ",".join(conhecidos) + (f" +{outros} outro(s)" if outros else "")
    return desenho


def links_do_espiao(quantos=10):
    """
    Onde os links mais recentes do Espião levam quando o servidor os abre, salto a
    salto, só com o tipo de cada página (produto, categoria, busca...) e o desenho de
    cada endereço (forma_do_link: partes fixas, números como #<dígitos>). Mostra se o
    link de afiliado sai para o produto: o conversor usa o produto achado em qualquer
    salto; sem produto no caminho, usaria a última página. Nenhum link aparece.
    """
    secao(f"Links do Espião: onde o servidor chega (os {quantos} mais recentes)")
    import asyncio
    import api_shopee
    fila = (db.ler_config("fila_clonagem", {"fila": []}) or {}).get("fila", [])
    links = [item.get("link_original") for item in fila if item.get("link_original")][-quantos:]
    if not links:
        print("   nenhum link na fila")
        return

    async def seguir_todos():
        return [await api_shopee.seguir_link(link) for link in links]

    sem_produto = parou_fora = 0
    for n, caminho in enumerate(asyncio.run(seguir_todos()), 1):
        com_produto = any(api_shopee.produto_do_link(endereco) for endereco in caminho[1:])
        sem_produto += not com_produto
        parou_fora += com_produto and api_shopee.tipo_de_link(caminho[-1]) != "produto"
        print(f"{n}. {' → '.join(api_shopee.tipo_de_link(e) for e in caminho)} | "
              f"produto no caminho: {'sim' if com_produto else 'NÃO'}")
        for endereco in caminho[1:]:
            print(f"      {forma_do_link(endereco)}")
    print(f"   {parou_fora} parou fora do produto, mas com o produto no meio do caminho; "
          f"{sem_produto} sem produto em lugar nenhum")


# Erros que o pool_contas grava com texto fixo; qualquer outro sai só com o tipo.
ERROS_FIXOS_DO_POOL = (
    "grupo dos Autorais não configurado", "restrita no grupo", "grupo inacessível para esta conta",
    "o grupo de origem não está nas conversas da conta", "conta banida/desativada pelo Telegram",
    "sessão revogada/expirada",
)


def contas_dos_autorais():
    """
    Estado de cada conta do pool (contas_telegram) e os últimos eventos
    (historico_contas). A conta aparece pelo número interno, nunca pelo apelido,
    telefone ou @; dos eventos, só o tipo, e a troca de estado quando é de grupo
    ou de sessão.
    """
    secao("Contas dos Autorais (pool)")
    with db.conexao(linhas_por_nome=True) as con:
        tabelas = {t[0] for t in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "contas_telegram" not in tabelas:
            print("   sem a tabela de contas")
            return
        contas = [dict(c) for c in con.execute("SELECT * FROM contas_telegram ORDER BY id")]
        numero = {c["apelido"]: c["id"] for c in contas}
        for c in contas:
            erro = (c.get("ultimo_erro") or "").strip()
            if erro and erro not in ERROS_FIXOS_DO_POOL:
                erro = erro.split(":")[0].split(" ")[0][:40]   # só o tipo (FloodWait, ValueError...)
            print(f"conta #{c['id']}: grupo {c.get('status_grupo')}, sessão {c.get('status_sessao')}, "
                  f"pode {c.get('funcoes_permitidas') or '-'}, habilitada {c.get('habilitada')}, "
                  f"já esteve no grupo {c.get('ja_esteve_no_grupo')}, cadastrada {c.get('criada_em')}, "
                  f"checada {c.get('ultima_checagem') or 'nunca'}" + (f", erro: {erro}" if erro else ""))
        if "funcoes_contas" in tabelas:
            for f in con.execute("SELECT * FROM funcoes_contas"):
                f = dict(f)
                print(f"posto {f.get('funcao')}: conta #{f.get('conta_id') or '-'}"
                      + (f" (rodízio {f.get('contas_ids')})" if f.get("contas_ids") else ""))
        if "historico_contas" in tabelas:
            print("Últimos eventos:")
            for ev in con.execute("SELECT * FROM historico_contas ORDER BY id DESC LIMIT 25"):
                ev = dict(ev)
                detalhe = f" ({ev['detalhe']})" if ev["evento"] in ("STATUS_GRUPO", "STATUS_SESSAO") else ""
                print(f"   {ev['data']}  conta #{numero.get(ev['apelido'], '?')}  {ev['evento']}{detalhe}")
    try:
        origem = db.ler_config("autorais_config", {}).get("origem")
        print(f"origem dos Autorais gravada como {type(origem).__name__}"
              + (" com tópico" if isinstance(origem, str) and ":" in origem else ""))
    except Exception as e:
        print(f"   (não deu para ler a origem: {type(e).__name__})")


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


# O que o Baixador faz com cada link, pelo começo fixo das linhas de log dele.
EVENTOS_BAIXADOR = (
    ("pedido(s) liberado(s)", re.compile(r"✅ \d+ liberado \(")),
    ("entregue(s)", re.compile(r"(📤 Vídeo entregue|♻️ Entregue do cache) ")),
    ("trava(s) de canais", re.compile(r"🔒 \d+ bloqueado: falta")),
    ("trava(s) expirada(s) sem entrar", re.compile(r"⏳ Aviso de trava de \d+ expirou")),
    ("limite(s) diário(s)", re.compile(r"📦 \d+ atingiu o limite")),
    ("falha(s) de download", re.compile(r"(❌ yt-dlp saiu|🎬 Sem formato|❌ Falha ao entregar)")),
    ("início(s) do robô", re.compile(r"📥 Downloader no ar")),
)


def contar_baixador(linhas):
    """{hora: {evento: quantidade}} pela hora de Brasília escrita na própria linha."""
    por_hora = {}
    for linha in linhas:
        achado = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}):\d{2}", linha)
        if not achado:
            continue
        mensagem = linha.split(" - ", 1)[1] if " - " in linha else linha
        for nome, regex in EVENTOS_BAIXADOR:
            if regex.match(mensagem):
                contagem = por_hora.setdefault(achado.group(1), {})
                contagem[nome] = contagem.get(nome, 0) + 1
                break
    return por_hora


def baixador_por_hora():
    """
    O que aconteceu com os links do tópico do Baixador nas últimas 24 h, hora a
    hora: liberados, entregues, travas de canais (e as que expiraram sem a pessoa
    entrar), limites, falhas e reinícios do robô. Só contagens, sem quem pediu.
    """
    secao("Baixador hora a hora (últimas 24 h, horário de Brasília)")
    r = subprocess.run(["sudo", "-n", "journalctl", "-u", "downloader_bot.service", "--since", "24 hours ago",
                        "-o", "cat", "-q"], capture_output=True, text=True, timeout=120)
    por_hora = contar_baixador(r.stdout.splitlines())
    if not por_hora:
        print("   nada registrado")
        return
    for hora in sorted(por_hora):
        print(f"   {hora}h: " + ", ".join(f"{qtd} {nome}" for nome, _ in EVENTOS_BAIXADOR
                                          if (qtd := por_hora[hora].get(nome))))


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


def _comando(*partes):
    """(código de saída, saída) de um comando, ou None se ele não existe na máquina."""
    try:
        r = subprocess.run(partes, capture_output=True, text=True, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return r.returncode, (r.stdout or "").strip()


def _sim_nao(valor):
    return "sim" if valor else "não"


def android_virtual():
    """
    Se o servidor aguenta um Android virtual (Redroid em Docker), que o robô da
    Shopee Vídeo usaria para postar pelo app. Só lê: arquitetura, memória, disco,
    o binder do kernel (sem ele o Android não sobe), Docker e se dá para instalar
    o que falta sem senha.
    """
    secao("Android virtual (Shopee Vídeo): o servidor aguenta?")
    kernel = platform.release()
    print(f"arquitetura: {platform.machine()} | kernel: {kernel} | CPUs: {os.cpu_count()}")

    memoria = {}
    try:
        with open("/proc/meminfo") as f:
            for linha in f:
                nome, valor = linha.split(":", 1)
                memoria[nome] = int(valor.split()[0]) * 1024
    except OSError:
        pass
    print(f"memória: {tamanho_legivel(memoria.get('MemTotal', 0))} no total, "
          f"{tamanho_legivel(memoria.get('MemAvailable', 0))} disponível | "
          f"swap: {tamanho_legivel(memoria.get('SwapTotal', 0))}")
    disco = shutil.disk_usage(os.path.expanduser("~"))
    print(f"disco: {tamanho_legivel(disco.free)} livre de {tamanho_legivel(disco.total)}")

    def ler(caminho):
        try:
            with open(caminho) as f:
                return f.read()
        except OSError:
            return ""

    config = ler(f"/boot/config-{kernel}")
    opcoes = {o: (re.search(rf"^{o}=(\w+)", config, re.M) or [None, "ausente"])[1]
              for o in ("CONFIG_ANDROID_BINDER_IPC", "CONFIG_ANDROID_BINDERFS")}
    print("binder no kernel: " + ", ".join(f"{o.replace('CONFIG_ANDROID_', '')}={v}" for o, v in opcoes.items())
          + ("" if config else " (sem o arquivo de configuração do kernel)"))
    modulo = _comando("modinfo", "-F", "filename", "binder_linux")
    print(f"módulo binder_linux: disponível {_sim_nao(modulo and modulo[0] == 0)}, "
          f"carregado {_sim_nao('binder_linux' in ler('/proc/modules'))} | "
          f"binderfs: {_sim_nao('binder' in ler('/proc/filesystems'))} | "
          f"/dev/binder: {_sim_nao(os.path.exists('/dev/binder'))}")
    extra = _comando("dpkg-query", "-W", "-f=${Status}", f"linux-modules-extra-{kernel}")
    print(f"pacote linux-modules-extra do kernel: "
          f"{_sim_nao(extra and extra[0] == 0 and 'installed' in extra[1].split())}")

    docker = _comando("docker", "--version")
    print(f"docker: {docker[1].split(',')[0] if docker and docker[0] == 0 else 'não instalado'}")
    sudo = _comando("sudo", "-n", "true")
    print(f"sudo sem senha: {_sim_nao(sudo and sudo[0] == 0)}")


if __name__ == "__main__":
    os.chdir(PASTA)
    for parte in (pastas_do_projeto, arquivos_soltos, banco, erros_registrados, filas_em_arquivo,
                  captura_dos_parceiros, contas_dos_autorais, links_do_espiao, journal, baixador_por_hora,
                  versoes, fora_do_projeto, android_virtual):
        try:
            parte()
        except Exception as e:
            print(f"(falhou: {type(e).__name__})")

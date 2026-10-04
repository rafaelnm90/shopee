#!/usr/bin/env python3
"""
Android virtual do robô da Shopee Vídeo: um Redroid (Android em Docker) no
servidor, onde o app da Shopee roda e é operado por programa. A Shopee Vídeo só
aceita postagem pelo app, por isso o Android.

Roda à mão pelo workflow android.yml ou no servidor:

    python3 android_virtual.py                    # só mostra o estado
    python3 android_virtual.py --preparar         # instala o que falta e liga o Android
    python3 android_virtual.py --instalar-shopee  # baixa e instala (ou atualiza) o app da Shopee
    python3 android_virtual.py --tela             # abre a tela no navegador (tela_android.py)

O --preparar faz só o que falta, e pode rodar de novo sem estragar nada:
1. instala o Docker e o adb do Ubuntu;
2. carrega o binder do kernel (sem ele o Android não liga) e deixa ele carregando
   a cada boot do servidor;
3. sobe o contêiner do Android, limitado em memória e CPU para não atrapalhar os
   robôs, com o adb aberto só para a própria máquina (127.0.0.1), nunca para a
   internet. Os dados do Android (app instalado, login) ficam numa pasta fora do
   contêiner e sobrevivem a ele ser recriado;
4. espera o Android terminar de ligar.

O --instalar-shopee baixa o app do APKPure ou, se ele recusar, do Aptoide (o
Android virtual não tem a Play Store) e instala. Quando o app vem em partes
(XAPK), sobem só as que servem para o processador ARM 64 do servidor.

O --tela deixa o tela_android.py rodando sozinho por 30 min e sai: o link vai
no privado do Rafael, nunca no log.

Imprime só estados e números, porque o log do Actions é público.
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import zipfile

PASTA = os.path.dirname(os.path.abspath(__file__))
CONTEINER = "android_shopee"
IMAGEM = "redroid/redroid:13.0.0_64only-latest"
PASTA_DADOS = os.path.expanduser("~/android_shopee/data")
ENDERECO_ADB = "127.0.0.1:5555"
MEMORIA = "4g"
CPUS = "2"
PACOTE_SHOPEE = "com.shopee.br"
SEGUNDOS_PARA_LIGAR = 240

# Tela de celular comum; sem placa de vídeo no servidor, o desenho é por software.
# Kernels novos não têm o ashmem: o Android usa o memfd no lugar.
PARAMETROS_BOOT = (
    "androidboot.redroid_width=720", "androidboot.redroid_height=1280",
    "androidboot.redroid_dpi=320", "androidboot.redroid_gpu_mode=guest",
    "androidboot.use_memfd=true",
)
DISPOSITIVOS_BINDER = "binder,hwbinder,vndbinder"

# Arquivos de trabalho das ferramentas, numa pasta do próprio usuário: a pasta dos
# dados do Android é criada pelo Docker como root, e o usuário não escreve nela.
PASTA_TRABALHO = os.path.expanduser("~/shopee_video")
PASTA_APP = os.path.join(PASTA_TRABALHO, "app")
# De onde baixar o app, em ordem. O Aptoide só vale quando a própria loja marca o
# arquivo como confiável (assinatura conferida com a do app original).
FONTES_APP = (
    ("APKPure XAPK", f"https://d.apkpure.com/b/XAPK/{PACOTE_SHOPEE}?version=latest"),
    ("APKPure APK", f"https://d.apkpure.com/b/APK/{PACOTE_SHOPEE}?version=latest"),
    ("APKPure .net", f"https://d.apkpure.net/b/XAPK/{PACOTE_SHOPEE}?version=latest"),
    ("Aptoide", None),
)
URL_APTOIDE = f"https://ws75.aptoide.com/api/7/app/getMeta/package_name={PACOTE_SHOPEE}"
NAVEGADOR = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/124.0 Mobile Safari/537.36")
# O servidor é ARM 64: as partes do app para armeabi_v7a, x86 e x86_64 sobram.
OUTRAS_ARQUITETURAS = ("armeabi", "x86")

ARQUIVO_TELA = os.path.join(PASTA_TRABALHO, "tela_estado")
LOG_TELA = os.path.join(PASTA_TRABALHO, "tela.log")
URL_CLOUDFLARED = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{}.deb"
SEGUNDOS_PARA_ABRIR_TELA = 120


def _rodar(*partes, timeout=120):
    """(código de saída, saída) de um comando; None se ele não existe ou travou."""
    try:
        r = subprocess.run(partes, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return r.returncode, (r.stdout or "").strip()


def _ok(resultado):
    return bool(resultado) and resultado[0] == 0


def _codigo(resultado):
    return "comando não encontrado ou travou" if resultado is None else f"código {resultado[0]}"


def docker_instalado():
    return shutil.which("docker") is not None


def binder_carregado():
    try:
        with open("/proc/modules") as f:
            return any(linha.startswith("binder_linux ") for linha in f)
    except OSError:
        return False


def estado_conteiner():
    """'running', 'exited'... ou None se o contêiner não existe (ou não há Docker)."""
    if not docker_instalado():
        return None
    r = _rodar("sudo", "-n", "docker", "inspect", "-f", "{{.State.Status}}", CONTEINER)
    return r[1] if _ok(r) and r[1] else None


def _adb(*partes, timeout=30):
    return _rodar("adb", "-s", ENDERECO_ADB, *partes, timeout=timeout)


def android_ligado():
    """O Android terminou de ligar (sys.boot_completed = 1)."""
    if shutil.which("adb") is None:
        return False
    _rodar("adb", "connect", ENDERECO_ADB, timeout=15)
    r = _adb("shell", "getprop", "sys.boot_completed")
    return _ok(r) and r[1] == "1"


def mostrar_estado():
    print("== Android virtual (Shopee Vídeo)")
    print(f"docker: {'instalado' if docker_instalado() else 'não instalado'} | "
          f"adb: {'instalado' if shutil.which('adb') else 'não instalado'} | "
          f"binder: {'carregado' if binder_carregado() else 'não carregado'}")
    estado = estado_conteiner()
    print(f"contêiner {CONTEINER}: {estado or 'não existe'}")
    if estado != "running":
        return
    uso = _rodar("sudo", "-n", "docker", "stats", "--no-stream", "--format", "{{.MemUsage}} | CPU {{.CPUPerc}}",
                 CONTEINER)
    if _ok(uso):
        print(f"uso: {uso[1]}")
    if not android_ligado():
        print("android: ainda ligando (ou o adb não conecta)")
        return
    versao = _adb("shell", "getprop", "ro.build.version.release")
    print(f"android: ligado, versão {versao[1] if _ok(versao) else '?'} | app da Shopee: {versao_shopee()}")
    try:
        with open(ARQUIVO_TELA) as f:
            print(f"tela no navegador: {f.read().strip()}")
    except OSError:
        pass


def versao_shopee():
    """'versão X' se o app da Shopee está instalado, ou 'não instalado'."""
    r = _adb("shell", "dumpsys", "package", PACOTE_SHOPEE)
    achado = re.search(r"versionName=(\S+)", r[1]) if _ok(r) else None
    return f"instalado, versão {achado.group(1)}" if achado else "não instalado"


def partes_do_app(arquivo, pasta):
    """
    Os .apk a instalar. Um APK comum vai inteiro; um XAPK (zip com o app em
    partes) é aberto, e só fica de fora a parte de outra arquitetura de processador.
    """
    with zipfile.ZipFile(arquivo) as z:
        nomes = z.namelist()
    if "AndroidManifest.xml" in nomes:
        # O adb só instala arquivo com final .apk.
        apk = os.path.join(pasta, "shopee.apk")
        os.makedirs(pasta, exist_ok=True)
        shutil.copyfile(arquivo, apk)
        return [apk]
    with zipfile.ZipFile(arquivo) as z:
        apks = sorted(n for n in nomes if n.endswith(".apk") and "/" not in n
                      and not any(a in n.lower() for a in OUTRAS_ARQUITETURAS))
        for nome in apks:
            z.extract(nome, pasta)
    return [os.path.join(pasta, nome) for nome in apks]


def _baixar(url, destino):
    """Código HTTP do download (o curl segue os redirecionamentos); 0 se nem respondeu."""
    r = _rodar("curl", "-sSL", "--retry", "2", "-A", NAVEGADOR, "-o", destino, "-w", "%{http_code}", url,
               timeout=900)
    if r is None:
        return 0
    codigo = r[1][-3:]
    return int(codigo) if codigo.isdigit() else 0


def _url_aptoide():
    """(endereço do APK, motivo). Só devolve endereço se o Aptoide marca o arquivo como TRUSTED."""
    r = _rodar("curl", "-sSL", "-A", NAVEGADOR, URL_APTOIDE, timeout=60)
    if not _ok(r):
        return None, "sem resposta"
    try:
        arquivo = json.loads(r[1])["data"]["file"]
    except (ValueError, KeyError, TypeError):
        return None, "resposta inesperada"
    if (arquivo.get("malware") or {}).get("rank") != "TRUSTED":
        return None, "arquivo não marcado como confiável"
    url = arquivo.get("path") or arquivo.get("path_alt")
    return (url, "ok") if url else (None, "sem endereço do arquivo")


def instalar_shopee():
    """Baixa o app da Shopee e instala (ou atualiza, mantendo o login)."""
    print("== App da Shopee")
    if not android_ligado():
        print("android: desligado; rode o preparar antes")
        return False
    shutil.rmtree(PASTA_APP, ignore_errors=True)
    os.makedirs(PASTA_APP)
    arquivo = os.path.join(PASTA_APP, "shopee.zip")
    try:
        for nome, url in FONTES_APP:
            if url is None:
                url, motivo = _url_aptoide()
                if url is None:
                    print(f"{nome}: {motivo}")
                    continue
            codigo = _baixar(url, arquivo)
            valido = codigo == 200 and zipfile.is_zipfile(arquivo)
            print(f"{nome}: HTTP {codigo}" + ("" if valido else ", sem o app"))
            if valido:
                break
        else:
            print("baixar o app: nenhuma fonte deu certo")
            return False
        tamanho = os.path.getsize(arquivo)
        partes = partes_do_app(arquivo, PASTA_APP)
        if not partes:
            print("baixar o app: o arquivo veio sem app dentro")
            return False
        print(f"baixado: {tamanho / 1024 / 1024:.0f} MB, {len(partes)} parte(s)")
        comando = "install" if len(partes) == 1 else "install-multiple"
        if not _passo("instalar no Android", _adb(comando, "-r", "-g", *partes, timeout=900)):
            return False
        print(f"app da Shopee: {versao_shopee()}")
        return True
    finally:
        shutil.rmtree(PASTA_APP, ignore_errors=True)


def _ler_estado_tela():
    try:
        with open(ARQUIVO_TELA) as f:
            return f.read().strip()
    except OSError:
        return ""


def abrir_tela():
    """
    Deixa o tela_android.py rodando sozinho (sobrevive ao fim desta conexão) e
    espera ele contar que mandou o link no privado do Rafael.
    """
    print("== Tela no navegador")
    if not android_ligado():
        print("android: desligado; rode o preparar antes")
        return False
    if shutil.which("cloudflared") is None:
        arquitetura = {"aarch64": "arm64", "x86_64": "amd64"}.get(platform.machine(), "arm64")
        deb = os.path.join(os.path.dirname(ARQUIVO_TELA), "cloudflared.deb")
        os.makedirs(os.path.dirname(deb), exist_ok=True)
        if not _passo("baixar o cloudflared", _rodar("curl", "-fsSL", "-o", deb,
                                                     URL_CLOUDFLARED.format(arquitetura), timeout=300)):
            return False
        if not _passo("instalar o cloudflared", _rodar("sudo", "-n", "dpkg", "-i", deb, timeout=300)):
            return False
    os.makedirs(PASTA_TRABALHO, exist_ok=True)
    try:
        os.remove(ARQUIVO_TELA)
    except FileNotFoundError:
        pass
    with open(LOG_TELA, "w") as log:
        subprocess.Popen([sys.executable, os.path.join(PASTA, "tela_android.py")], cwd=PASTA,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                         start_new_session=True)
    prazo = time.monotonic() + SEGUNDOS_PARA_ABRIR_TELA
    while time.monotonic() < prazo:
        estado = _ler_estado_tela()
        if estado == "enviado":
            print("tela: aberta; o link foi no privado do Rafael")
            return True
        if estado.startswith("erro"):
            print(f"tela: {estado}")
            return False
        time.sleep(3)
    print(f"tela: não abriu em {SEGUNDOS_PARA_ABRIR_TELA} s")
    return False


def _passo(nome, resultado):
    print(f"{nome}: {'ok' if _ok(resultado) else 'falhou (' + _codigo(resultado) + ')'}")
    return _ok(resultado)


def preparar():
    """Instala e liga só o que falta. Devolve True se o Android terminou ligado."""
    print("== Preparando o Android virtual")
    if not (docker_instalado() and shutil.which("adb")):
        if not _passo("lista de pacotes", _rodar("sudo", "-n", "apt-get", "update", "-qq", timeout=600)):
            return False
        if not _passo("instalar docker e adb", _rodar(
                "sudo", "-n", "env", "DEBIAN_FRONTEND=noninteractive",
                "apt-get", "install", "-y", "-qq", "docker.io", "adb", timeout=900)):
            return False

    if not binder_carregado():
        if not _passo("carregar o binder", _rodar(
                "sudo", "-n", "modprobe", "binder_linux", f"devices={DISPOSITIVOS_BINDER}")):
            return False
    # Para o binder voltar sozinho depois de um reboot do servidor.
    _passo("binder a cada boot", _rodar(
        "sudo", "-n", "sh", "-c",
        "echo binder_linux > /etc/modules-load.d/redroid.conf && "
        f"echo 'options binder_linux devices={DISPOSITIVOS_BINDER}' > /etc/modprobe.d/redroid.conf"))

    estado = estado_conteiner()
    if estado is None:
        if not _passo("criar o contêiner", _rodar(
                "sudo", "-n", "docker", "run", "-d", "--name", CONTEINER,
                "--restart", "unless-stopped", "--privileged",
                "--memory", MEMORIA, "--cpus", CPUS,
                "-v", f"{PASTA_DADOS}:/data",
                "-p", f"{ENDERECO_ADB}:5555",
                IMAGEM, *PARAMETROS_BOOT, timeout=1200)):
            return False
    elif estado != "running":
        if not _passo("ligar o contêiner", _rodar("sudo", "-n", "docker", "start", CONTEINER)):
            return False

    prazo = time.monotonic() + SEGUNDOS_PARA_LIGAR
    while time.monotonic() < prazo:
        if android_ligado():
            print("android: ligado")
            return True
        time.sleep(10)
    print(f"android: não terminou de ligar em {SEGUNDOS_PARA_LIGAR} s")
    return False


if __name__ == "__main__":
    pedidos = sys.argv[1:]
    ok = True
    if "--preparar" in pedidos:
        ok = preparar()
    if ok and "--instalar-shopee" in pedidos:
        ok = instalar_shopee()
    if ok and "--tela" in pedidos:
        ok = abrir_tela()
    mostrar_estado()
    sys.exit(0 if ok else 1)

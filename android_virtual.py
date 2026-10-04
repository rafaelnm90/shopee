#!/usr/bin/env python3
"""
Android virtual do robô da Shopee Vídeo: um Redroid (Android em Docker) no
servidor, onde o app da Shopee roda e é operado por programa. A Shopee Vídeo só
aceita postagem pelo app, por isso o Android.

Roda à mão pelo workflow android.yml ou no servidor:

    python3 android_virtual.py              # só mostra o estado
    python3 android_virtual.py --preparar   # instala o que falta e liga o Android

O --preparar faz só o que falta, e pode rodar de novo sem estragar nada:
1. instala o Docker e o adb do Ubuntu;
2. carrega o binder do kernel (sem ele o Android não liga) e deixa ele carregando
   a cada boot do servidor;
3. sobe o contêiner do Android, limitado em memória e CPU para não atrapalhar os
   robôs, com o adb aberto só para a própria máquina (127.0.0.1), nunca para a
   internet. Os dados do Android (app instalado, login) ficam numa pasta fora do
   contêiner e sobrevivem a ele ser recriado;
4. espera o Android terminar de ligar.

Imprime só estados e números, porque o log do Actions é público.
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import os
import shutil
import subprocess
import sys
import time

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
    shopee = _adb("shell", "pm", "list", "packages", PACOTE_SHOPEE)
    print(f"android: ligado, versão {versao[1] if _ok(versao) else '?'} | "
          f"app da Shopee: {'instalado' if _ok(shopee) and PACOTE_SHOPEE in shopee[1] else 'não instalado'}")


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
    ok = True
    if "--preparar" in sys.argv[1:]:
        ok = preparar()
    mostrar_estado()
    sys.exit(0 if ok else 1)

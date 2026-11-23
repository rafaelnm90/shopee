#!/usr/bin/env python3
"""
Aulas de um curso gravadas pelo celular do robô, para o Claude estudar (P288 3, 22/11/2026).

O Rafael escolheu que o Motorola do robô grave as aulas do curso: o celular toca a aula no
Chrome e o servidor grava a imagem e o som dele pela mesma ligação do adb, com o scrcpy, sem
arquivo no celular (a memória dele não enche) e sem tocar em nada nele (sem o controle do
scrcpy). Da gravação saem a fala, pelo reconhecimento de voz, e as folhas de quadros, que vão
cifradas ao Claude pelos casos (casos_robo); o vídeo é apagado logo depois. O conteúdo do curso
nunca vai ao log nem ao repositório: o log diz só números (duração, brilho, volume, palavras).
Gravação preta ou muda quer dizer que o player não deixa gravar, e aí a gravação para (P288 3).

Quem usa: o explorar (passo gravar:SEGUNDOS do postador_shopee_video, no celular) e o
android.yml (instalar-gravador, que roda o `instalar` daqui).
Decisão do Rafael: DECISOES.md, Trabalho com o Claude.
"""
import hashlib
import io
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta

from PIL import Image, ImageStat

import db
import videos
from fuso import fuso_horario

# O scrcpy numa versão fixa, compilado no servidor: o do apt do Ubuntu é antigo e não grava o som.
# A parte que vai ao celular vem pronta da página da versão, conferida pelo SHA-256 que a própria
# versão publica (no install_release.sh dela).
VERSAO_DO_GRAVADOR = "3.1"
REPOSITORIO_DO_GRAVADOR = "https://github.com/Genymobile/scrcpy"
URL_DA_PARTE_DO_CELULAR = (f"{REPOSITORIO_DO_GRAVADOR}/releases/download/v{VERSAO_DO_GRAVADOR}/"
                           f"scrcpy-server-v{VERSAO_DO_GRAVADOR}")
SHA256_DA_PARTE_DO_CELULAR = "958f0944a62f23b1f33a16e9eb14844c1a04b882ca175a738c16d23cb22b86c0"
PASTA_DO_GRAVADOR = os.path.expanduser("~/scrcpy")
PACOTES_DO_GRAVADOR = (
    "ffmpeg", "libsdl2-2.0-0", "gcc", "git", "pkg-config", "meson", "ninja-build", "libsdl2-dev",
    "libavcodec-dev", "libavdevice-dev", "libavformat-dev", "libavutil-dev", "libswresample-dev",
    "libusb-1.0-0-dev")

# A gravação: o bastante para ler os slides e ouvir a fala, sem encher o disco do servidor.
LADO_MAIOR = 1280
QUADROS_POR_SEGUNDO = 15
TAXA_DO_VIDEO = "2M"
TAXA_DO_SOM = "64K"
# Segundos a mais que a gravação, para o scrcpy abrir, fechar o arquivo e sair.
FOLGA_DO_GRAVADOR = 60
# O passo gravar do explorar é um teste curto, dentro do tempo do android.yml.
PADRAO_NO_EXPLORAR = 20
MAXIMO_NO_EXPLORAR = 180

# Para o Claude: até 40 quadros espalhados, em folhas de 5, como os vídeos do Rafael.
QUADROS_PARA_O_CLAUDE = 40
# Abaixo disto, na média de 0 a 255 de alguns quadros pequenos, a imagem saiu preta.
BRILHO_DO_PRETO = 8
QUADROS_DO_BRILHO = 6
LARGURA_DO_BRILHO = 160

# O curso abre no Chrome do celular, pelo link guardado no Acessos do Servidor 🔐, e o robô faz o login
# com o e-mail e a senha que o Rafael mandou ao Claude (pedido dele, 22/11). Nada disso vai ao log.
# O link abre sempre na mesma aba do Chrome (a marca do robô no pedido), sem juntar abas a cada vez.
PACOTE_DO_CHROME = "com.android.chrome"
ABA_DO_ROBO = "cursos_robo"
# O site leva alguns segundos para entrar: a página de login é conferida de 2 em 2 s, até 20 s.
ESPERA_DO_LOGIN = 20
PASSO_DA_ESPERA = 2

# O som chega ao servidor no volume de mídia do celular (P291 1): o robô o lê e o muda pelo adb, sem tocar
# na tela nem abrir o painel de volume, e o vídeo da aula é lido, pausado e tocado pela sessão de mídia do
# Chrome (o estado e o tempo; o título da aula, que a sessão também tem, nunca sai daqui).
FLUXO_DE_MIDIA = 3
ESTADOS_DA_MIDIA = {0: "sem vídeo", 1: "parado", 2: "pausado", 3: "tocando", 6: "carregando", 7: "com erro"}
TOCANDO = 3
CARREGANDO = 6
TECLAS_DA_MIDIA = {"pausar": "KEYCODE_MEDIA_PAUSE", "tocar": "KEYCODE_MEDIA_PLAY"}

# O que o scrcpy escreve no erro vira um motivo fixo: a saída dele traz o endereço do celular.
MOTIVOS_DO_GRAVADOR = (
    (re.compile(r"could not find|not found|offline|unauthorized|no devices", re.I),
     "o celular não respondeu ao gravador"),
    (re.compile(r"audio", re.I), "o som do celular não pôde ser gravado"),
    (re.compile(r"encod", re.I), "o celular não conseguiu codificar a imagem"),
)


def versao_instalada(rodar=subprocess.run):
    """A versão do scrcpy do servidor ("3.1"), ou "" sem ele."""
    caminho = shutil.which("scrcpy")
    if not caminho:
        return ""
    try:
        saida = rodar([caminho, "--version"], capture_output=True, text=True, timeout=30).stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""
    achado = re.search(r"scrcpy (\d+(?:\.\d+)+)", saida)
    return achado.group(1) if achado else ""


def _passo(nome, rodar, comando, timeout, pasta=None):
    """Um passo da instalação; o log diz se deu certo e, na falha, o código e o fim do erro da ferramenta."""
    try:
        feito = rodar(comando, capture_output=True, text=True, timeout=timeout, cwd=pasta)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"{nome}: falhou ({type(e).__name__})")
        return False
    if feito.returncode != 0:
        print(f"{nome}: falhou (código {feito.returncode})")
        for linha in (feito.stderr or "").strip().splitlines()[-5:]:
            print(f"  {linha[:200]}")
        return False
    print(f"{nome}: ok")
    return True


def baixar_a_parte_do_celular(destino, abrir=urllib.request.urlopen):
    """Baixa a parte do scrcpy que vai ao celular e confere o SHA-256 da versão. True se bateu."""
    try:
        with abrir(URL_DA_PARTE_DO_CELULAR, timeout=120) as resposta:
            dados = resposta.read()
    except Exception as e:
        print(f"parte do celular: não baixou ({type(e).__name__})")
        return False
    if hashlib.sha256(dados).hexdigest() != SHA256_DA_PARTE_DO_CELULAR:
        print("parte do celular: o SHA-256 não bate com o da versão; nada foi instalado")
        return False
    with open(destino, "wb") as arquivo:
        arquivo.write(dados)
    print("parte do celular: ok (SHA-256 conferido)")
    return True


def instalar(rodar=subprocess.run, abrir=urllib.request.urlopen):
    """
    Instala no servidor o scrcpy da VERSAO_DO_GRAVADOR, só se ainda não está: os pacotes do apt, o
    código da versão, a parte do celular conferida e o programa compilado. True se terminou instalado.
    """
    print("== Gravador das aulas (scrcpy)")
    if versao_instalada(rodar) == VERSAO_DO_GRAVADOR:
        print(f"gravador: já instalado (scrcpy {VERSAO_DO_GRAVADOR})")
        return True
    if not _passo("lista de pacotes", rodar, ["sudo", "-n", "apt-get", "update", "-qq"], 600):
        return False
    if not _passo("pacotes do gravador", rodar, ["sudo", "-n", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get",
                                                 "install", "-y", "-qq", *PACOTES_DO_GRAVADOR], 1800):
        return False
    shutil.rmtree(PASTA_DO_GRAVADOR, ignore_errors=True)
    if not _passo("código da versão", rodar, ["git", "clone", "-q", "--depth", "1", "--branch",
                                              f"v{VERSAO_DO_GRAVADOR}", REPOSITORIO_DO_GRAVADOR,
                                              PASTA_DO_GRAVADOR], 600):
        return False
    if not baixar_a_parte_do_celular(os.path.join(PASTA_DO_GRAVADOR, "scrcpy-server"), abrir):
        return False
    if not _passo("preparar a compilação", rodar, ["meson", "setup", "build-auto", "--buildtype=release", "--strip",
                                                   "-Db_lto=true", "-Dprebuilt_server=scrcpy-server"],
                  600, pasta=PASTA_DO_GRAVADOR):
        return False
    if not _passo("compilar", rodar, ["ninja", "-C", "build-auto"], 1800, pasta=PASTA_DO_GRAVADOR):
        return False
    if not _passo("instalar", rodar, ["sudo", "-n", "ninja", "-C", "build-auto", "install"], 600,
                  pasta=PASTA_DO_GRAVADOR):
        return False
    versao = versao_instalada(rodar)
    print(f"gravador: instalado (scrcpy {versao})" if versao else "gravador: não respondeu depois de instalado")
    return versao == VERSAO_DO_GRAVADOR


def comando_do_gravador(alvo, segundos, destino):
    """O scrcpy que grava sem janela, sem tocar no celular e sem passar do tempo."""
    # --require-audio: sem o som da gravação, o gravador para. Gravando o som, o alto-falante do celular fica
    # mudo; sem ele, a aula tocaria alto no quarto do Rafael (pedido dele, 22/11/2026).
    return ["scrcpy", "-s", alvo, "--no-window", "--no-playback", "--no-control", "--require-audio",
            f"--record={destino}", "--record-format=mkv", f"--time-limit={int(segundos)}",
            f"--max-size={LADO_MAIOR}", f"--max-fps={QUADROS_POR_SEGUNDO}",
            f"--video-bit-rate={TAXA_DO_VIDEO}", f"--audio-bit-rate={TAXA_DO_SOM}"]


def motivo_da_falha(saida):
    """O motivo fixo de uma gravação que não saiu, pela saída do scrcpy (que nunca vai ao log)."""
    for padrao, motivo in MOTIVOS_DO_GRAVADOR:
        if padrao.search(saida or ""):
            return motivo
    return "a gravação não saiu"


def gravar(alvo, segundos, destino, rodar=subprocess.run):
    """
    Grava a tela e o som do celular (alvo, o "ip:porta" do adb) por esses segundos em destino (.mkv),
    sem janela e sem tocar em nada nele. Devolve (ok, motivo fixo, sem nada do celular).
    """
    # Sem tela no servidor: o scrcpy não abre janela nem som, e o SDL não procura nenhum dos dois.
    ambiente = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    try:
        feito = rodar(comando_do_gravador(alvo, segundos, destino), capture_output=True, text=True,
                      timeout=segundos + FOLGA_DO_GRAVADOR, env=ambiente)
    except FileNotFoundError:
        return False, "o gravador não está instalado (android.yml, instalar-gravador)"
    except subprocess.TimeoutExpired:
        return False, "o gravador não terminou no prazo"
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"o gravador não abriu ({type(e).__name__})"
    if not os.path.exists(destino) or os.path.getsize(destino) == 0:
        return False, motivo_da_falha(getattr(feito, "stderr", ""))
    return True, "gravado"


def brilho(arquivo):
    """A média do brilho (0 a 255) de alguns quadros pequenos espalhados; None sem quadros."""
    medidas = []
    with tempfile.TemporaryDirectory() as pasta:
        for i in range(videos.quadros(arquivo, pasta, QUADROS_DO_BRILHO, LARGURA_DO_BRILHO)):
            caminho = os.path.join(pasta, f"quadro_{i + 1}.jpg")
            if os.path.exists(caminho):
                with Image.open(caminho) as imagem:
                    medidas.append(ImageStat.Stat(imagem.convert("L")).mean[0])
    return round(sum(medidas) / len(medidas)) if medidas else None


def numeros(arquivo):
    """Os números da gravação, nada do conteúdo: segundos, se tem a trilha de som, o volume (LUFS) e o brilho."""
    tem_som = videos.tem_audio(arquivo)
    volume = videos.volume_do_som(arquivo) if tem_som else None
    return {"segundos": round(videos.duracao(arquivo)), "tem_som": tem_som,
            "som": None if volume is None else round(volume, 1), "brilho": brilho(arquivo)}


def problema(medidos, palavras=None):
    """
    O que impede usar a gravação; "" quando ela serve. Preta ou muda: o player não deixa gravar (P288 3).
    O som baixo em que a fala foi reconhecida (palavras) serve: o player deixou gravar, e o que está baixo é o
    volume do celular (Motorola, 22/11/2026: uma aula a -61,5 LUFS, com 180 palavras reconhecidas em 60 s).
    """
    if not medidos.get("segundos"):
        return "a gravação saiu vazia"
    if medidos.get("brilho") is None or medidos["brilho"] < BRILHO_DO_PRETO:
        return "a imagem saiu preta"
    if not medidos.get("tem_som"):
        return "a gravação saiu sem o som"
    if (medidos.get("som") is None or medidos["som"] <= videos.VOLUME_DO_MUDO) and not palavras:
        return "o som saiu mudo"
    return ""


def para_o_claude(arquivo, pasta, quadros=QUADROS_PARA_O_CLAUDE):
    """
    Grava na pasta (a de um caso ou de uma aula, que vai cifrada ao Claude) as folhas de até `quadros`
    quadros e a fala (fala.txt, com o segundo de cada trecho). Devolve (folhas, palavras); palavras é None
    quando não deu para ouvir.
    """
    folhas = videos.folhas_de_quadros(arquivo, pasta, quadros)
    trechos = videos.fala_em_trechos(arquivo)
    if trechos is None:
        return folhas, None
    with open(os.path.join(pasta, "fala.txt"), "w", encoding="utf-8") as saida:
        for inicio, texto in trechos:
            saida.write(f"[{inicio:7.1f}s] {texto}\n")
    return folhas, sum(len(texto.split()) for _inicio, texto in trechos)


def linha_dos_numeros(medidos, folhas=None, palavras=None):
    """A linha do log de uma gravação: só números."""
    if medidos.get("som") is not None:
        som = f"som {medidos['som']} LUFS"
    else:
        som = "som mudo" if medidos.get("tem_som") else "sem a trilha de som"
    partes = [f"{medidos.get('segundos', 0)} s",
              f"brilho {medidos['brilho']}" if medidos.get("brilho") is not None else "sem quadros", som]
    if folhas is not None:
        partes.append(f"{folhas} folha(s) de quadros")
    if palavras is not None:
        partes.append(f"{palavras} palavra(s) na fala")
    return ", ".join(partes)


def _saida(d, partes):
    """O que um comando no celular escreveu; "" quando ele não respondeu."""
    try:
        return getattr(d.shell(partes), "output", "") or ""
    except Exception:
        return ""


def ler_o_volume(texto):
    """(atual, máximo) do volume na resposta do Android ("volume is 4 in range [0..15]"); None sem ela."""
    achado = re.search(r"volume is (\d+) in range \[(\d+)\.\.(\d+)\]", texto or "")
    return (int(achado.group(1)), int(achado.group(3))) if achado else None


def volume_de_midia(d):
    """(atual, máximo) do volume de mídia do celular, pelo adb; None quando o Android não disse."""
    return ler_o_volume(_saida(d, ["cmd", "media_session", "volume", "--stream", str(FLUXO_DE_MIDIA), "--get"]))


def mudar_o_volume(d, indice):
    """Põe o volume de mídia nesse ponto, sem o painel de volume na tela, e devolve o que ficou (atual, máximo)."""
    _saida(d, ["cmd", "media_session", "volume", "--stream", str(FLUXO_DE_MIDIA), "--set", str(int(indice))])
    return volume_de_midia(d)


def estado_da_midia(texto, agora_ms=None, pacote=PACOTE_DO_CHROME):
    """
    Na saída do dumpsys media_session, a sessão de mídia do Chrome: {"estado", "posicao"}; com mais de uma, a
    que está tocando. None sem sessão do Chrome. A posição, em segundos, é a que o Chrome anotou e, com o
    vídeo tocando e o relógio do celular (agora_ms, o tempo desde que ele ligou, o mesmo da sessão), a de
    agora. Só o estado e o tempo: o título da aula, que a sessão também tem, nunca sai daqui.
    """
    sessoes = []
    for linha in (texto or "").splitlines():
        achado = re.match(r"\s*package=(\S+)", linha)
        if achado:
            sessoes.append({"pacote": achado.group(1)})
            continue
        achado = re.search(r"state=PlaybackState \{state=(?:[A-Za-z_]+\()?(\d+)\)?, position=(-?\d+)", linha)
        if achado and sessoes and "codigo" not in sessoes[-1]:
            velocidade = re.search(r"speed=(-?[\d.]+)", linha)
            atualizado = re.search(r"updated=(\d+)", linha)
            sessoes[-1].update(codigo=int(achado.group(1)), posicao=max(0, int(achado.group(2))),
                               velocidade=float(velocidade.group(1)) if velocidade else 0.0,
                               atualizado=int(atualizado.group(1)) if atualizado else 0)
    do_pacote = [s for s in sessoes if s["pacote"] == pacote and "codigo" in s]
    if not do_pacote:
        return None
    escolhida = next((s for s in do_pacote if s["codigo"] == TOCANDO), do_pacote[0])
    posicao = escolhida["posicao"]
    if agora_ms and escolhida["codigo"] == TOCANDO and 0 < escolhida["atualizado"] < agora_ms:
        posicao += (agora_ms - escolhida["atualizado"]) * max(0.0, escolhida["velocidade"])
    return {"estado": ESTADOS_DA_MIDIA.get(escolhida["codigo"], "outro"), "posicao": int(posicao) // 1000}


def relogio_do_celular(d):
    """O tempo desde que o celular ligou, em ms (o relógio que a sessão de mídia usa); None sem ele."""
    achado = re.match(r"\s*(\d+(?:\.\d+)?)\s", _saida(d, ["cat", "/proc/uptime"]))
    return int(float(achado.group(1)) * 1000) if achado else None


def midia_do_chrome(d):
    """O estado do vídeo no Chrome do celular agora (estado_da_midia); None sem vídeo nele."""
    texto = _saida(d, ["dumpsys", "media_session"])
    return estado_da_midia(texto, relogio_do_celular(d)) if texto else None


def volume_no_explorar(d, argumento):
    """
    O passo volume do explorar (P291 1): sem número, lê o volume de mídia; com um, muda para ele e
    confere. O log diz só os números.
    """
    antes = volume_de_midia(d)
    if antes is None:
        return False, "o Android não disse o volume de mídia"
    if not argumento:
        return True, f"volume de mídia: {antes[0]} de {antes[1]}"
    try:
        indice = int(argumento)
    except ValueError:
        return False, "volume pede o número (ex.: volume:8)"
    if not 0 <= indice <= antes[1]:
        return False, f"volume vai de 0 a {antes[1]}"
    depois = mudar_o_volume(d, indice)
    if not depois or depois[0] != indice:
        return False, f"o volume de mídia não mudou (estava em {antes[0]} de {antes[1]})"
    return True, f"volume de mídia: de {antes[0]} para {depois[0]} de {depois[1]}"


def midia_no_explorar(d, argumento, pausa=time.sleep):
    """O passo midia do explorar: o estado do vídeo no Chrome e, com pausar ou tocar, a tecla de mídia antes."""
    if argumento:
        tecla = TECLAS_DA_MIDIA.get(argumento.lower())
        if not tecla:
            return False, "midia lê o vídeo do Chrome (midia), pausa (midia:pausar) ou toca (midia:tocar)"
        _saida(d, ["input", "keyevent", tecla])
        pausa(2)
    midia = midia_do_chrome(d)
    if not midia:
        return True, "sem vídeo no Chrome"
    return True, f"vídeo do Chrome: {midia['estado']}, em {midia['posicao']} s"


def acesso_do_curso():
    """{"link", "email", "senha"} do curso, do Acessos do Servidor 🔐; {} enquanto o Rafael não mandou."""
    import painel_acessos
    return painel_acessos.ler_acessos()["curso"]


def abrir_o_curso(d):
    """Abre o link do curso no Chrome do celular. (ok, o que dizer no log, sem o link)."""
    link = acesso_do_curso().get("link")
    if not link:
        return False, "sem o link do curso no Acessos do Servidor"
    d.shell(["am", "start", "-a", "android.intent.action.VIEW", "-d", link, "-p", PACOTE_DO_CHROME,
             "--es", "com.android.browser.application_id", ABA_DO_ROBO])
    return True, "curso aberto no Chrome"


def campos_do_login(xml):
    """Os centros (e-mail, senha) dos campos da página de login; None quando a tela não é a de login."""
    try:
        raiz = ET.fromstring(xml or "")
    except ET.ParseError:
        return None
    email = senha = None
    for no in raiz.iter("node"):
        caixa = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", no.get("bounds", ""))
        if not no.get("class", "").endswith("EditText") or not caixa:
            continue
        x1, y1, x2, y2 = map(int, caixa.groups())
        centro = ((x1 + x2) // 2, (y1 + y2) // 2)
        if no.get("password") == "true":
            senha = senha or centro
        else:
            email = email or centro
    return (email, senha) if email and senha else None


def campo_em_foco(xml):
    """Se o campo com o cursor é o de senha (True) ou outro (False); None sem campo com o cursor."""
    try:
        raiz = ET.fromstring(xml or "")
    except ET.ParseError:
        return None
    for no in raiz.iter("node"):
        if no.get("class", "").endswith("EditText") and no.get("focused") == "true":
            return no.get("password") == "true"
    return None


def _saiu_do_login(d, pausa):
    """Espera o site entrar, conferindo a página de 2 em 2 s. (saiu, a última tela lida)."""
    tela = ""
    for _ in range(ESPERA_DO_LOGIN // PASSO_DA_ESPERA):
        pausa(PASSO_DA_ESPERA)
        tela = d.dump_hierarchy()
        if not campos_do_login(tela):
            return True, tela
    return False, tela


def entrar_no_curso(d, escrever, achar, pausa=time.sleep):
    """
    Na página de login do curso, escreve o e-mail e a senha guardados e entra (o Enter do teclado e,
    se a página continuar, o botão Entrar). escrever e achar são os do explorar. (ok, o que dizer no log).
    O teclado aberto sobe a página: o lugar de cada campo é lido de novo antes do toque, e cada texto só
    vai ao campo dele, conferido pelo cursor (a senha nunca num campo que não é o de senha).
    """
    acesso = acesso_do_curso()
    if not acesso.get("email") or not acesso.get("senha"):
        return False, "sem o login do curso no Acessos do Servidor"
    if not campos_do_login(d.dump_hierarchy()):
        return False, "a tela não é a de login do curso"
    for indice, valor in enumerate((acesso["email"], acesso["senha"])):
        campos = campos_do_login(d.dump_hierarchy())
        if not campos:
            return False, "a página de login mudou no meio"
        d.click(*campos[indice])
        pausa(1)
        foco = campo_em_foco(d.dump_hierarchy())
        if foco is None or foco != (indice == 1):
            return False, "o cursor não ficou no campo certo do login"
        escrever(d, valor)
    d.press("enter")
    saiu, tela = _saiu_do_login(d, pausa)
    if not saiu:
        ponto = achar(tela, "Entrar")
        if ponto:
            d.click(*ponto)
            saiu, tela = _saiu_do_login(d, pausa)
    return (True, "login feito") if saiu else (False, "o login não passou (a página de login continua)")


# --- As páginas do curso no Chrome (mapeadas em 22/11/2026, com o celular mudo) ---
# Na aula, o player tem os botões pela descrição ("Tocar vídeo" no meio dele e na barra); embaixo, as abas Módulos,
# Comentários e Anotações. Na aba Módulos, cada módulo é um botão e, aberto, mostra uma linha por aula com o nome e a
# duração ("Nome 4:54"), numa lista que rola por dentro. A barra "Próximo: Nome" leva à aula seguinte do curso, e o
# endereço da aula fica na barra do Chrome (".../m/lessons/<código>"). Trocando de aula pela lista, a página continua
# rolada, e o player some da tela e da leitura dela: a página sobe antes do play. Os nomes das aulas e os endereços
# ficam só no banco do servidor, nunca no log nem no repositório.
LINHA_DA_AULA = re.compile(r"(?P<nome>.*\S)\s+(?P<tempo>\d{1,2}(?::\d{2}){1,2})")
CAMINHO_DA_AULA = re.compile(r"[\w.-]+/m/lessons/[\w-]+")
ROTULO_DO_PROXIMO = "Próximo:"
ROTULO_DO_PLAY = "Tocar vídeo"


def segundos_do_tempo(texto):
    """A duração escrita na linha da aula em segundos: "4:54" dá 294; "1:02:03", 3723."""
    total = 0
    for parte in texto.split(":"):
        total = total * 60 + int(parte)
    return total


def _nos(xml):
    """Os nós da tela com tamanho: texto, descrição, id, classe, caixa e se aceitam toque. [] sem a tela."""
    try:
        raiz = ET.fromstring(xml or "")
    except ET.ParseError:
        return []
    nos = []
    for no in raiz.iter("node"):
        caixa = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", no.get("bounds", ""))
        if not caixa:
            continue
        x1, y1, x2, y2 = map(int, caixa.groups())
        if x2 > x1 and y2 > y1:
            nos.append({"texto": no.get("text", ""), "descricao": no.get("content-desc", ""),
                        "id": no.get("resource-id", "").split(":id/")[-1],
                        "classe": no.get("class", "").rsplit(".", 1)[-1], "caixa": (x1, y1, x2, y2),
                        "clicavel": no.get("clickable") == "true"})
    return nos


def _centro(caixa):
    x1, y1, x2, y2 = caixa
    return (x1 + x2) // 2, (y1 + y2) // 2


def linhas_das_aulas(xml):
    """As linhas das aulas da aba Módulos que estão na tela, de cima para baixo: [(nome, segundos, centro)]."""
    linhas = []
    for no in _nos(xml):
        achado = LINHA_DA_AULA.fullmatch(" ".join(no["texto"].split()))
        if no["clicavel"] and no["classe"] == "Button" and achado:
            linhas.append((achado["nome"], segundos_do_tempo(achado["tempo"]), _centro(no["caixa"])))
    return sorted(linhas, key=lambda linha: linha[2][1])


def endereco_da_aula(xml):
    """O endereço da aula aberta no Chrome, pela barra de endereço; None fora de uma aula."""
    for no in _nos(xml):
        if no["id"] == "url_bar":
            texto = no["texto"].strip().removeprefix("https://")
            if CAMINHO_DA_AULA.fullmatch(texto):
                return "https://" + texto
    return None


def botao_do_proximo(xml):
    """O centro da barra "Próximo: Nome", que leva à aula seguinte do curso; None na última aula."""
    for no in _nos(xml):
        if no["clicavel"] and no["texto"].startswith(ROTULO_DO_PROXIMO):
            return _centro(no["caixa"])
    return None


def botao_do_play(xml):
    """O centro do play do player (o maior dos "Tocar vídeo"); None com o player fora da tela."""
    botoes = [no for no in _nos(xml) if no["clicavel"] and no["descricao"] == ROTULO_DO_PLAY]
    if not botoes:
        return None
    maior = max(botoes, key=lambda no: (no["caixa"][2] - no["caixa"][0]) * (no["caixa"][3] - no["caixa"][1]))
    return _centro(maior["caixa"])


# A aula abre pela barra de endereço da guia que está na frente (o link por fora abre uma guia nova a cada vez: de 8
# para 11 guias no mapa de 22/11/2026), e a página nova vem do alto, com o player na tela. O play é conferido pela
# sessão de mídia do Chrome.
ESPERA_DA_PAGINA = 20
ESPERA_DO_PLAY = 30


def ir_para_o_endereco(d, endereco, escrever, pausa=None):
    """
    Abre o endereço da aula na guia da frente do Chrome, escrito na barra de endereço (escrever é o do explorar), e
    espera a página nova mostrar o player. True com a aula aberta, do alto.
    """
    pausa = pausa or time.sleep
    barra = next((no for no in _nos(d.dump_hierarchy()) if no["id"] == "url_bar"), None)
    if not barra:
        return False
    d.click(*_centro(barra["caixa"]))
    pausa(1)
    escrever(d, endereco)
    d.press("enter")
    for _ in range(ESPERA_DA_PAGINA // PASSO_DA_ESPERA):
        pausa(PASSO_DA_ESPERA)
        tela = d.dump_hierarchy()
        if endereco_da_aula(tela) == endereco and botao_do_play(tela):
            return True
    return False


# --- O mapa das aulas (P293 1), só no banco do servidor ---
# Os 7 cursos da turma do Rafael pela posição na lista de Turmas do site (Continuar aprendendo → Turmas): primeiro os
# dois de Shopee Vídeo, depois os outros na ordem da lista e, por último, o dos encontros ao vivo (P293 1). Os nomes dos
# cursos não vão ao repositório. A 1ª aula de cada curso é guardada pelo Claude, com o passo curso:primeira:N do
# explorar na página dela; as outras vêm uma a uma pelo "Próximo" do site, com o endereço e o nome guardados aqui.
ORDEM_DOS_CURSOS = (4, 5, 1, 2, 6, 7, 3)
CHAVE_DO_MAPA = "curso_mapa"


def mapa_das_aulas():
    """{"cursos": {"posição": {"aulas": [{"endereco", "nome", "gravada_em"}], "fim": bool}}} do banco."""
    mapa = db.ler_config(CHAVE_DO_MAPA, {}) or {}
    mapa.setdefault("cursos", {})
    return mapa


def _mudar_o_curso(posicao, mudar):
    """Muda o curso dessa posição no mapa, numa transação só; devolve o que mudar(curso) devolver."""
    def mudar_o_mapa(mapa):
        return mudar(mapa.setdefault("cursos", {}).setdefault(str(int(posicao)), {"aulas": [], "fim": False}))
    return db.atualizar_config(CHAVE_DO_MAPA, mudar_o_mapa)


def guardar_a_primeira_aula(posicao, endereco):
    """
    A 1ª aula do curso nessa posição da lista de Turmas, guardada pelo Claude (passo curso:primeira:N). Antes de alguma
    aula do curso ser gravada, troca a que estava (o Claude pode corrigir); depois, o mapa do curso não muda. True se
    guardou.
    """
    if int(posicao) not in ORDEM_DOS_CURSOS or not CAMINHO_DA_AULA.fullmatch(endereco.removeprefix("https://")):
        return False

    def mudar(curso):
        if any(aula.get("gravada_em") for aula in curso["aulas"]):
            return False
        curso["aulas"] = [{"endereco": endereco, "nome": "", "gravada_em": ""}]
        return True
    return bool(_mudar_o_curso(posicao, mudar))


def proxima_aula(mapa=None):
    """
    A aula da vez, na ordem dos cursos: (posição, aula) com a 1ª aula ainda não gravada do curso (a que ficou pela
    metade volta inteira, do início: P295 1); (posição, None) quando todas as guardadas do curso foram gravadas e a
    seguinte vem pelo "Próximo" da última. Pula o curso terminado e o que ainda não tem a 1ª aula guardada. None sem
    nada a gravar.
    """
    mapa = mapa or mapa_das_aulas()
    for posicao in ORDEM_DOS_CURSOS:
        curso = mapa["cursos"].get(str(posicao)) or {}
        aulas = curso.get("aulas") or []
        if curso.get("fim") or not aulas:
            continue
        falta = next((aula for aula in aulas if not aula.get("gravada_em")), None)
        return posicao, falta
    return None


def anotar_a_aula_gravada(posicao, endereco, agora=None):
    """A aula do curso gravada inteira: a próxima vez segue para a seguinte."""
    def mudar(curso):
        for aula in curso["aulas"]:
            if aula["endereco"] == endereco:
                aula["gravada_em"] = _texto(_agora(agora))
    _mudar_o_curso(posicao, mudar)


def anotar_a_aula_seguinte(posicao, endereco, nome):
    """A aula que o "Próximo" abriu, no fim da lista do curso (sem repetir a que já está nela)."""
    def mudar(curso):
        if all(aula["endereco"] != endereco for aula in curso["aulas"]):
            curso["aulas"].append({"endereco": endereco, "nome": nome, "gravada_em": ""})
    _mudar_o_curso(posicao, mudar)


def anotar_o_fim_do_curso(posicao):
    """A última aula do curso (sem o "Próximo") gravada: o curso terminou."""
    _mudar_o_curso(posicao, lambda curso: curso.update(fim=True))


def tocar_pelo_play(d, pausa=None):
    """O play do player da aula, conferido pela sessão de mídia do Chrome: True com a aula tocando."""
    pausa = pausa or time.sleep
    ponto = botao_do_play(d.dump_hierarchy())
    if not ponto:
        return False
    d.click(*ponto)
    for _ in range(ESPERA_DO_PLAY // PASSO_DA_ESPERA):
        pausa(PASSO_DA_ESPERA)
        midia = midia_do_chrome(d)
        if midia and midia["estado"] == "tocando":
            return True
    return False


# --- A gravação da madrugada (P289 1 a P293 1, 22/11/2026) ---
# Depois do Horário do Robô, de madrugada, as aulas são gravadas uma a uma até um pouco antes da limpeza
# das 4h (P289 1), na velocidade normal (P292 1), com o volume de mídia no meio só durante a aula (P291 1)
# e só com o disco do servidor abaixo de 70% (P290 1). O robô da Shopee Vídeo tem a preferência (pedido do
# Rafael, 22/11): com o Horário do Robô o dia todo não há madrugada, e o robô que precisa do celular (um
# botão do painel, a limpeza das 4h) pede, e a aula para e solta o celular em segundos.
FIM_DA_NOITE = (3, 45)
LIMITE_DO_DISCO = 70
VOLUME_NA_AULA = 0.5
CHAVE_DA_NOITE = "curso_gravacao"
# A gravação renova o sinal a cada olhada; sem ele há mais que isto, ela não está com o celular.
SINAL_VALE = 120
# Quanto o robô espera a gravação soltar o celular, olhando a cada PASSO_DA_ESPERA_DO_ROBO.
ESPERA_PELO_CELULAR = 120
PASSO_DA_ESPERA_DO_ROBO = 3
# Enquanto o curso não termina, a madrugada é dele: a gravação das aulas e o explorar que mexe só no Chrome do
# curso, para o Claude mapear o site (P294 1). Terminado o curso, volta a False e tudo volta ao normal (pedido do
# Rafael, 22/11/2026: DECISOES.md, Trabalho com o Claude).
CURSO_EM_ANDAMENTO = True


def _agora(agora=None):
    return agora or datetime.now(fuso_horario)


def _texto(momento):
    return momento.strftime("%Y-%m-%d %H:%M:%S")


def na_madrugada(config, agora=None):
    """
    Agora é a madrugada da gravação: fora do Horário do Robô (config, a do painel) e antes do FIM_DA_NOITE
    (P289 1)? Com o Horário do Robô o dia todo, nunca.
    """
    momento = _agora(agora)
    inicio, fim = int(config.get("robo_inicio", 8)), int(config.get("robo_fim", 22))
    if inicio <= 0 and fim >= 24:
        return False
    minutos = momento.hour * 60 + momento.minute
    if minutos >= fim * 60:
        return True
    return minutos < min(inicio * 60, FIM_DA_NOITE[0] * 60 + FIM_DA_NOITE[1])


def disco_usado(caminho=None):
    """O quanto do disco do servidor está em uso, em %, como o df mostra (arredondado para cima)."""
    uso = shutil.disk_usage(caminho or os.path.expanduser("~"))
    return math.ceil(uso.used * 100 / max(1, uso.used + uso.free))


def estado_da_noite():
    """O que a gravação da madrugada anotou no banco (o sinal, o pedido do robô, o volume de antes)."""
    return db.ler_config(CHAVE_DA_NOITE, {}) or {}


def _anotar(**campos):
    db.atualizar_config(CHAVE_DA_NOITE, lambda estado: estado.update(campos))


def anotar_o_sinal(agora=None):
    """A gravação está com o celular: o sinal dela, renovado a cada olhada, diz isso ao robô."""
    _anotar(sinal_em=_texto(_agora(agora)))


def soltar_o_sinal():
    _anotar(sinal_em="")


def gravando(agora=None):
    """A gravação da madrugada está com o celular agora (o sinal dela tem menos de SINAL_VALE s)?"""
    sinal = estado_da_noite().get("sinal_em") or ""
    return bool(sinal) and sinal >= _texto(_agora(agora) - timedelta(seconds=SINAL_VALE))


def pedir_o_celular(quem, agora=None):
    """O robô (ou o explorar) precisa do celular: a gravação para a aula e solta o celular na hora."""
    _anotar(pedido_em=_texto(_agora(agora)), pedido_por=quem)


def pediram_o_celular(desde):
    """Alguém pediu o celular depois desse momento (o começo da aula, em texto)?"""
    return (estado_da_noite().get("pedido_em") or "") >= desde


def liberar_para_o_robo(quem="robô", espera=ESPERA_PELO_CELULAR, pausa=time.sleep, ocupado=None):
    """
    Com a gravação da madrugada no celular, pede o celular a ela e espera ela soltar (até espera s). True
    com o celular livre ou sem gravação nenhuma; False se ela não soltou a tempo.
    """
    if ocupado is None:
        import celular_robo   # aqui dentro: o celular_robo traz o adb, que o explorar já carrega
        ocupado = celular_robo.ocupado
    if not gravando():
        return True
    pedir_o_celular(quem)
    for _ in range(max(1, espera // PASSO_DA_ESPERA_DO_ROBO)):
        if not ocupado():
            return True
        pausa(PASSO_DA_ESPERA_DO_ROBO)
    return not ocupado()


def subir_o_volume(d):
    """
    O volume de mídia no meio para a aula (P291 1), guardando o de antes no banco: ele volta no fim da aula
    ou, se a gravação cair no meio, na próxima vez que o robô usar o celular (devolver_o_volume). Já acima
    do meio, fica como está. O de antes que ainda não voltou (a gravação caiu e começou de novo) fica: o de
    agora já é o da aula. (atual, máximo) depois, ou None sem o volume.
    """
    antes = volume_de_midia(d)
    if not antes:
        return None
    if estado_da_noite().get("volume_antes") is None:
        _anotar(volume_antes=antes[0])
    alvo = round(antes[1] * VOLUME_NA_AULA)
    return antes if antes[0] >= alvo else mudar_o_volume(d, alvo)


def calar_o_celular(d):
    """
    O volume de mídia em 0 para o explorar do curso de madrugada (P294 1): o celular não faz barulho à noite. O de
    antes fica guardado como o da aula e volta no fim (devolver_o_volume). (atual, máximo) depois, ou None sem o
    volume.
    """
    antes = volume_de_midia(d)
    if not antes:
        return None
    if estado_da_noite().get("volume_antes") is None:
        _anotar(volume_antes=antes[0])
    return antes if antes[0] == 0 else mudar_o_volume(d, 0)


def tocando_agora(texto):
    """Na saída do dumpsys media_session: algum app está tocando (ou carregando para tocar) um vídeo ou um som?"""
    estados = re.findall(r"state=PlaybackState \{state=(?:[A-Za-z_]+\()?(\d+)", texto or "")
    return any(int(estado) in (TOCANDO, CARREGANDO) for estado in estados)


def pausar_o_que_toca(d, pausa=None):
    """
    O que toca no celular, pausado pela tecla de mídia e conferido. True quando nada toca; False sem a leitura do
    Android ou com algo ainda tocando.
    """
    pausa = pausa or time.sleep
    for _ in range(3):
        texto = _saida(d, ["dumpsys", "media_session"])
        if not texto:
            return False
        if not tocando_agora(texto):
            return True
        _saida(d, ["input", "keyevent", TECLAS_DA_MIDIA["pausar"]])
        pausa(1)
    texto = _saida(d, ["dumpsys", "media_session"])
    return bool(texto) and not tocando_agora(texto)


def devolver_o_volume(d, pausa=None):
    """
    O volume de mídia de antes da aula, de volta; sem um guardado, nada. True se voltou. O celular fica no quarto
    do Rafael (pedido dele, 22/11/2026): o que toca nele é pausado antes, e, sem a certeza de que nada toca, o
    celular fica mudo, nunca alto, e o de antes volta na próxima vez que o robô usar o celular.
    """
    antes = estado_da_noite().get("volume_antes")
    if antes is None:
        return False
    if not pausar_o_que_toca(d, pausa):
        mudar_o_volume(d, 0)
        return False
    depois = mudar_o_volume(d, antes)
    if not depois or depois[0] != antes:
        return False
    _anotar(volume_antes=None)
    return True


class GravacaoEmFundo:
    """
    O scrcpy gravando enquanto a aula toca, sem janela e sem tocar no celular (comando_do_gravador). Para com
    o Ctrl+C dele, que fecha o arquivo direito; a saída dele, que traz o endereço do celular, vira só o
    motivo fixo da falha.
    """

    def __init__(self, alvo, destino, segundos, abrir=subprocess.Popen):
        ambiente = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
        self.destino = destino
        self._saida = open(destino + ".saida", "w+", encoding="utf-8", errors="replace")
        self.processo = abrir(comando_do_gravador(alvo, segundos, destino), stdout=subprocess.DEVNULL,
                              stderr=self._saida, env=ambiente)

    def rodando(self):
        return self.processo.poll() is None

    def parar(self, espera=30):
        """Para a gravação e fecha o arquivo. (ok, motivo fixo)."""
        if self.rodando():
            self.processo.send_signal(signal.SIGINT)
            try:
                self.processo.wait(timeout=espera)
            except subprocess.TimeoutExpired:
                self.processo.kill()
                self.processo.wait(timeout=10)
        self._saida.seek(0)
        saida = self._saida.read()
        self._saida.close()
        os.remove(self._saida.name)
        if not os.path.exists(self.destino) or os.path.getsize(self.destino) == 0:
            return False, motivo_da_falha(saida)
        return True, "gravado"


# O fim da aula, pela sessão de mídia do Chrome: o vídeo que tocava e ficou parado (pausado, parado ou
# sem sessão) por PARADO_NO_FIM s, carregando por CARREGANDO_DEMAIS s, ou que voltou mais que
# VOLTA_DE_OUTRO s (o site começou outro vídeo, a aula seguinte, sozinho).
PARADO_NO_FIM = 15
CARREGANDO_DEMAIS = 120
VOLTA_DE_OUTRO = 30


class OlhoNaAula:
    """O que a gravação vê do vídeo da aula, olhada a olhada: quanto já tocou e se ele acabou."""

    def __init__(self):
        self.tocou, self.maior, self.parado_desde = False, 0, None

    def olhar(self, midia, segundos):
        """
        Com o estado do vídeo (midia_do_chrome) e o relógio em segundos: None enquanto a aula segue, ou o
        motivo fixo do fim ("o vídeo parou", "carregando demais", "outro vídeo começou").
        """
        if midia and midia["estado"] == "tocando":
            if self.tocou and midia["posicao"] + VOLTA_DE_OUTRO < self.maior:
                return "outro vídeo começou"
            self.tocou, self.parado_desde = True, None
            self.maior = max(self.maior, midia["posicao"])
            return None
        if not self.tocou:
            return None
        if self.parado_desde is None:
            self.parado_desde = segundos
        carregando = bool(midia) and midia["estado"] == "carregando"
        if segundos - self.parado_desde >= (CARREGANDO_DEMAIS if carregando else PARADO_NO_FIM):
            return "carregando demais" if carregando else "o vídeo parou"
        return None

    def de_novo(self):
        """Depois de mandar tocar de novo o vídeo que parou: a espera do parado recomeça."""
        self.parado_desde = None


# A aula aberta no Chrome, gravada do começo ao fim. A cada OLHADA_DA_AULA s, a gravação renova o sinal ao robô e
# confere o gravador, o pedido do celular, a hora e o vídeo. O gravador grava até AULA_MAIS_LONGA de uma vez (a
# madrugada acaba antes); o que não está gravando ESPERA_DO_GRAVADOR s depois de ligar não grava (sem o som, o
# --require-audio o para logo).
OLHADA_DA_AULA = 3
AULA_MAIS_LONGA = 4 * 60 * 60
ESPERA_DO_GRAVADOR = 5


def _madrugada_agora():
    return na_madrugada(db.ler_config("shopee_video", {}) or {})


def gravar_a_aula_aberta(d, alvo, destino, tocar, pausa=None, relogio=None, abrir=subprocess.Popen,
                         madrugada=None):
    """
    A aula já aberta no Chrome do celular, gravada em destino. A ordem protege o quarto do Rafael (pedido dele,
    22/11/2026): o gravador liga antes e, gravando o som, deixa o alto-falante mudo; o volume sobe só com ele
    gravando; no fim, a aula pausa e o volume volta antes de o gravador parar. tocar(d) dá o play e diz se o vídeo
    tocou. O robô que pede o celular, a madrugada que acaba (3h45) e o gravador que cai param a aula, que fica pela
    metade (P295 1: ela volta depois, do início). Devolve (inteira, motivo fixo).
    """
    pausa = pausa or time.sleep
    relogio = relogio or time.monotonic
    madrugada = madrugada or _madrugada_agora
    inicio = _texto(_agora())
    anotar_o_sinal()
    gravacao = GravacaoEmFundo(alvo, destino, AULA_MAIS_LONGA, abrir=abrir)
    try:
        pausa(ESPERA_DO_GRAVADOR)
        if not gravacao.rodando():
            return False, "o gravador não ficou gravando"
        if not subir_o_volume(d):
            return False, "sem o volume de mídia"
        if not tocar(d):
            return False, "a aula não começou a tocar"
        olho, comeco = OlhoNaAula(), relogio()
        while True:
            pausa(OLHADA_DA_AULA)
            anotar_o_sinal()
            if not gravacao.rodando():
                return False, "o gravador parou no meio"
            if pediram_o_celular(inicio):
                return False, "o robô pediu o celular"
            if not madrugada():
                return False, "a madrugada acabou"
            fim = olho.olhar(midia_do_chrome(d), relogio() - comeco)
            if fim:
                return fim != "carregando demais", fim
    finally:
        # Primeiro a aula pausa e o volume volta (ou fica mudo), e só depois o gravador para: parado o gravador, o
        # alto-falante volta a tocar.
        try:
            pausar_o_que_toca(d, pausa)
            devolver_o_volume(d, pausa)
        finally:
            gravacao.parar()


# As aulas gravadas ficam no servidor só como a fala e as folhas de quadros (o vídeo sai logo depois),
# até o Claude ler: o cursos_robo.yml leva as mais velhas, cifradas, num pacote de até TAMANHO_DO_PACOTE
# (o GitHub não aceita arquivo de mais de 100 MB), e o apagar tira do servidor as que foram no pacote.
# Nas aulas, um quadro a cada QUADROS_A_CADA s, entre o mínimo dos casos e QUADROS_DA_AULA.
PASTA_DAS_AULAS = os.path.expanduser("~/shopee_video/aulas")
NOME_DA_AULA = re.compile(r"\d{8}-\d{6}-c\d{2}-a\d{3}")
TAMANHO_DO_PACOTE = 40 * 1024 * 1024
QUADROS_A_CADA = 20
QUADROS_DA_AULA = 120


def quadros_da_aula(segundos):
    """Quantos quadros da aula vão ao Claude: um a cada QUADROS_A_CADA s, de 40 a QUADROS_DA_AULA."""
    return min(QUADROS_DA_AULA, max(QUADROS_PARA_O_CLAUDE, int(segundos or 0) // QUADROS_A_CADA))


def aulas_guardadas():
    """Os nomes das pastas das aulas guardadas, das mais velhas às mais novas."""
    if not os.path.isdir(PASTA_DAS_AULAS):
        return []
    return sorted(nome for nome in os.listdir(PASTA_DAS_AULAS)
                  if NOME_DA_AULA.fullmatch(nome) and os.path.isdir(os.path.join(PASTA_DAS_AULAS, nome)))


def guardar_a_aula(arquivo, curso, aula, fim, agora=None):
    """
    A aula gravada vira, na pasta das aulas, a fala (fala.txt) e as folhas de quadros, com o aula.json só de
    números (o curso e a aula pela posição, nunca o nome); o vídeo sai logo depois (P290 1: o disco não
    enche). Devolve (pasta, aula.json).
    """
    medidos = numeros(arquivo)
    momento = _agora(agora)
    os.makedirs(PASTA_DAS_AULAS, exist_ok=True)
    pasta = os.path.join(PASTA_DAS_AULAS, f"{momento:%Y%m%d-%H%M%S}-c{int(curso):02d}-a{int(aula):03d}")
    os.makedirs(pasta, exist_ok=True)
    folhas, palavras = para_o_claude(arquivo, pasta, quadros_da_aula(medidos.get("segundos")))
    info = {"curso": int(curso), "aula": int(aula), "gravada_em": _texto(momento), "fim": fim,
            "segundos": medidos.get("segundos"), "som": medidos.get("som"), "brilho": medidos.get("brilho"),
            "folhas": folhas, "palavras": palavras, "problema": problema(medidos, palavras)}
    with open(os.path.join(pasta, "aula.json"), "w", encoding="utf-8") as saida:
        json.dump(info, saida, ensure_ascii=False, indent=1)
    if os.path.exists(arquivo):
        os.remove(arquivo)
    return pasta, info


def _tamanho(pasta):
    return sum(os.path.getsize(os.path.join(raiz, nome)) for raiz, _, nomes in os.walk(pasta) for nome in nomes)


def aulas_do_pacote(ate=None):
    """As aulas do próximo pacote para o Claude: das mais velhas, até TAMANHO_DO_PACOTE (ao menos uma) e `ate`."""
    escolhidas, tamanho = [], 0
    for nome in aulas_guardadas():
        if ate and nome > ate:
            break
        do_nome = _tamanho(os.path.join(PASTA_DAS_AULAS, nome))
        if escolhidas and tamanho + do_nome > TAMANHO_DO_PACOTE:
            break
        escolhidas.append(nome)
        tamanho += do_nome
    return escolhidas


def pacote_das_aulas(ate=None):
    """O zip das aulas do próximo pacote, em bytes."""
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as arquivo_zip:
        for nome in aulas_do_pacote(ate):
            for raiz, _, arquivos in os.walk(os.path.join(PASTA_DAS_AULAS, nome)):
                for arquivo in arquivos:
                    caminho = os.path.join(raiz, arquivo)
                    arquivo_zip.write(caminho, os.path.relpath(caminho, PASTA_DAS_AULAS))
    return memoria.getvalue()


def cifrado_das_aulas(ate=None):
    """O pacote das aulas cifrado com a chave do servidor (a do registro_privado)."""
    from cryptography.fernet import Fernet
    import registro_privado   # aqui dentro: só a exportação precisa da chave
    return Fernet(registro_privado.chave()).encrypt(pacote_das_aulas(ate)).decode("ascii")


def apagar_aulas(ate):
    """Tira do servidor as aulas até `ate` (a mais nova do pacote exportado). Devolve quantas saíram."""
    saem = [nome for nome in aulas_guardadas() if nome <= ate]
    for nome in saem:
        shutil.rmtree(os.path.join(PASTA_DAS_AULAS, nome), ignore_errors=True)
    return len(saem)


def abrir_aulas(texto_cifrado, valor_chave, destino):
    """Abre o pacote do ramo numa pasta (no scratchpad do Claude, nunca no repositório). Devolve as aulas."""
    from cryptography.fernet import Fernet
    dados = Fernet(valor_chave.strip().encode("ascii")).decrypt(texto_cifrado.strip().encode("ascii"))
    with zipfile.ZipFile(io.BytesIO(dados)) as arquivo_zip:
        arquivo_zip.extractall(destino)
    return sorted(nome for nome in os.listdir(destino) if os.path.isdir(os.path.join(destino, nome)))


def _ler_aulas(caminho, destino):
    """Abre no scratchpad do Claude o pacote baixado do ramo aulas-curso, com a chave do ambiente dele."""
    import registro_privado
    from cryptography.fernet import InvalidToken
    valor = os.environ.get(registro_privado.VARIAVEL_CHAVE, "")
    if not valor:
        print(f"Falta a variável {registro_privado.VARIAVEL_CHAVE} no ambiente do Claude.")
        return 1
    with open(caminho, encoding="ascii") as arquivo:
        texto_cifrado = arquivo.read()
    try:
        nomes = abrir_aulas(texto_cifrado, valor, destino)
    except (InvalidToken, ValueError):
        print("A chave do ambiente não abre este arquivo: o servidor pode ter gerado outra (o bot manda a nova).")
        return 1
    print(f"{len(nomes)} aula(s) em {destino}:")
    for nome in nomes:
        print(f"   {nome}")
    return 0


def _aulas(argumentos):
    """O que o cursos_robo.yml pede das aulas guardadas (só contagens e nomes de pasta no log)."""
    if argumentos == ["contar"]:
        print(len(aulas_guardadas()))
        return 0
    if argumentos == ["ultima"]:
        lista = aulas_do_pacote()
        print(lista[-1] if lista else "")
        return 0
    if argumentos[:1] == ["cifrado"] and len(argumentos) <= 2:
        print(cifrado_das_aulas(argumentos[1] if len(argumentos) == 2 else None))
        return 0
    if argumentos[:1] == ["apagar"] and len(argumentos) == 2 and NOME_DA_AULA.fullmatch(argumentos[1]):
        print(f"{apagar_aulas(argumentos[1])} aula(s) apagada(s) do servidor.")
        return 0
    if argumentos[:1] == ["ler"] and len(argumentos) == 3:
        return _ler_aulas(argumentos[1], argumentos[2])
    print("uso: cursos_robo.py aulas contar | ultima | cifrado [ATE] | apagar ATE | ler ARQUIVO PASTA")
    return 2


def main(argumentos):
    if argumentos == ["instalar"]:
        return 0 if instalar() else 1
    if argumentos == ["estado"]:
        versao = versao_instalada()
        print(f"gravador: {'scrcpy ' + versao if versao else 'não instalado'}")
        return 0
    if argumentos[:1] == ["aulas"]:
        return _aulas(argumentos[1:])
    print("uso: cursos_robo.py instalar | estado | aulas ...")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

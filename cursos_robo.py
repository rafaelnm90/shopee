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
import registro_processos
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
    return True, descrever_a_midia(midia_do_chrome(d))


def descrever_a_midia(midia):
    """O estado do vídeo no Chrome em palavras fixas e números (o log do explorar e o registro da aula)."""
    if not midia:
        return "sem vídeo no Chrome"
    return f"vídeo do Chrome: {midia['estado']}, em {midia['posicao']} s"


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
# Na aula, o player tem os botões pelo nome ("Tocar vídeo" no meio dele e na barra; o nome vem no texto do botão no
# Chrome do Motorola, como na tela das 03:45 de 23/11/2026, e na descrição em outros) e os ids "plyr-..."; embaixo,
# as abas Módulos, Comentários e Anotações. Na aba Módulos, cada módulo é um botão e, aberto, mostra uma linha por aula
# com o nome e a duração ("Nome 4:54"), numa lista que rola por dentro. A barra "Próximo: Nome" leva à aula seguinte
# do curso, e o endereço da aula fica na barra do Chrome (".../m/lessons/<código>"). Trocando de aula pela lista, a
# página continua rolada, e o player some da tela e da leitura dela: a página sobe antes do play. Há aulas sem vídeo,
# um documento ou um texto (o vídeo do Rafael das 08:22 de 23/11/2026): a página dela tem as abas, sem player nenhum.
# Os nomes das aulas e os endereços ficam só no banco do servidor, nunca no log nem no repositório.
LINHA_DA_AULA = re.compile(r"(?P<nome>.*\S)\s+(?P<tempo>\d{1,2}(?::\d{2}){1,2})")
CAMINHO_DA_AULA = re.compile(r"[\w.-]+/m/lessons/[\w-]+")
ROTULO_DO_PROXIMO = "Próximo:"
ROTULO_DO_PLAY = "Tocar vídeo"
ID_DO_PLAYER = "plyr-"
ID_DAS_ABAS = "trigger-modules"
CAIXA_DA_NOVA_GUIA = "search_box_text"


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
    """
    O centro do play do player (o maior dos "Tocar vídeo", pelo texto ou pela descrição do botão); None com o player
    fora da tela. Só o play: o mudo do player nunca é tocado (pedido do Rafael, 23/11/2026), e o som da aula é o volume
    de mídia do Android.
    """
    botoes = [no for no in _nos(xml) if no["clicavel"] and ROTULO_DO_PLAY in (no["texto"], no["descricao"])]
    if not botoes:
        return None
    maior = max(botoes, key=lambda no: (no["caixa"][2] - no["caixa"][0]) * (no["caixa"][3] - no["caixa"][1]))
    return _centro(maior["caixa"])


def tem_player(xml):
    """A página tem o player de vídeo (os ids "plyr-..." ou o "Tocar vídeo"), mesmo sem o play à vista?"""
    return any(no["id"].startswith(ID_DO_PLAYER) for no in _nos(xml)) or bool(botao_do_play(xml))


def pagina_da_aula_pronta(xml):
    """A página da aula já mostra as abas (Módulos, Comentários e Anotações), que vêm com ela, com vídeo ou sem?"""
    return any(no["id"].endswith(ID_DAS_ABAS) for no in _nos(xml))


def texto_da_barra(xml):
    """O que está escrito na barra de endereço do Chrome; None sem ela na tela."""
    return next((no["texto"] for no in _nos(xml) if no["id"] == "url_bar"), None)


def barra_na_tela(xml):
    """
    Onde escrever o endereço: a barra de endereço no alto do Chrome ou, na página de Nova guia (onde o Chrome abre
    depois de horas parado, como em 23/11/2026), a caixa de busca dela, que abre a barra. None sem nenhuma à vista (a
    barra some quando a página rola para baixo).
    """
    return next((no for no in _nos(xml) if no["id"] in ("url_bar", CAIXA_DA_NOVA_GUIA) and no["caixa"][1] >= 0),
                None)


def _sem_o_https(texto):
    return (texto or "").strip().removeprefix("https://").rstrip("/")


# A aula abre pela barra de endereço da guia que está na frente (o link por fora abre uma guia nova a cada vez: de 8
# para 11 guias no mapa de 22/11/2026), e a página nova vem do alto, com o player na tela. O endereço vai à barra
# tecla por tecla, pelo adb, como num teclado (escrever_na_barra), e só com ele conferido na barra vem o Enter. A página
# pode começar a tocar o vídeo sozinha, sem o play na tela: o vídeo tocando também diz que ela abriu. O play é
# conferido pela sessão de mídia do Chrome. A rodada do robô termina com a Shopee no Eu (deixar_sem_video), e a noite
# pode começar com ela na frente: o Chrome vem para a frente antes da barra.
ESPERA_DA_PAGINA = 20
ESPERA_SEM_O_PLAYER = 10
ESPERA_DO_PLAY = 30
ESPERA_DO_CHROME = 3
COM_VIDEO = "com vídeo"
SEM_VIDEO = "sem vídeo"
# Por que a aula não abriu, em palavras fixas (o registro de cada aula e o relatório da manhã).
SEM_O_CHROME = "o Chrome não veio para a frente"
SEM_A_BARRA = "sem a barra de endereço do Chrome"
SEM_A_ESCRITA = "o endereço não ficou escrito na barra"
SEM_O_ENDERECO = "o endereço da aula não ficou na barra"
SEM_O_PLAYER = "a página não mostrou o player"


def app_da_frente(d):
    """O pacote do app que está na frente do celular; "" sem a leitura."""
    try:
        return (d.app_current() or {}).get("package") or ""
    except Exception:
        return ""


def trazer_o_chrome(d, pausa=None):
    """O Chrome na frente do celular (o robô deixa a Shopee no Eu no fim de cada rodada que mexe no celular)."""
    if app_da_frente(d) == PACOTE_DO_CHROME:
        return
    d.app_start(PACOTE_DO_CHROME, wait=True)
    (pausa or time.sleep)(ESPERA_DO_CHROME)


def escrever_na_barra(d, endereco, pausa=None):
    """
    O endereço escrito na barra de endereço do Chrome (já tocada, com o de antes marcado) tecla por tecla, pelo adb,
    como num teclado. O texto posto pela acessibilidade, o jeito dos campos da Shopee, aparecia na barra, mas o Chrome
    não o tomava como escrito, e o Enter abria outra página (a do Gemini, às 03:00, 03:15 e 03:30 de 23/11/2026). O
    pedaço que o Chrome completa sozinho depois do escrito fica marcado e sai com a tecla de apagar à frente. True com
    a barra mostrando o endereço.
    """
    pausa = pausa or time.sleep
    _saida(d, ["input", "text", endereco])
    pausa(1)
    _saida(d, ["input", "keyevent", "KEYCODE_FORWARD_DEL"])
    pausa(1)
    return _sem_o_https(texto_da_barra(d.dump_hierarchy())) == _sem_o_https(endereco)


def _tocando_ou_carregando(midia):
    return bool(midia) and midia["estado"] in ("tocando", "carregando")


def ir_para_o_endereco(d, endereco, pausa=None):
    """
    Abre o endereço da aula na guia da frente do Chrome, escrito na barra de endereço, e espera a página nova:
    (COM_VIDEO, "") com o player na tela ou o vídeo tocando sozinho; (SEM_VIDEO, "") na aula sem vídeo (um documento
    ou um texto: a página pronta, sem player nenhum, nem depois de mais um tempo); (None, o porquê) quando não abriu.
    O que tocava antes é pausado, e o vídeo tocando depois do Enter é o da página nova.
    """
    pausa = pausa or time.sleep
    trazer_o_chrome(d, pausa)
    barra = barra_na_tela(d.dump_hierarchy())
    if not barra and app_da_frente(d) == PACOTE_DO_CHROME:
        # A barra some quando a página rola para baixo: rolando para cima, ela volta.
        d.swipe(540, 700, 540, 1500, 0.3)
        pausa(1)
        barra = barra_na_tela(d.dump_hierarchy())
    if not barra:
        return None, SEM_A_BARRA if app_da_frente(d) == PACOTE_DO_CHROME else SEM_O_CHROME
    pausar_o_que_toca(d, pausa)
    d.click(*_centro(barra["caixa"]))
    pausa(1)
    if not escrever_na_barra(d, endereco, pausa):
        # Sem o Enter: a barra sai da edição, e a página de antes fica como estava.
        d.press("back")
        return None, SEM_A_ESCRITA
    _saida(d, ["input", "keyevent", "KEYCODE_ENTER"])
    tela = ""
    for _ in range(ESPERA_DA_PAGINA // PASSO_DA_ESPERA):
        pausa(PASSO_DA_ESPERA)
        tela = d.dump_hierarchy()
        if endereco_da_aula(tela) == endereco and (botao_do_play(tela) or _tocando_ou_carregando(midia_do_chrome(d))):
            return COM_VIDEO, ""
    if endereco_da_aula(tela) != endereco:
        return None, SEM_O_ENDERECO
    if pagina_da_aula_pronta(tela) and not tem_player(tela):
        # A página pronta sem player: mais um tempo para o player que demora, e então é a aula sem vídeo.
        pausa(ESPERA_SEM_O_PLAYER)
        tela = d.dump_hierarchy()
        if endereco_da_aula(tela) == endereco and pagina_da_aula_pronta(tela) and not tem_player(tela):
            return (COM_VIDEO, "") if _tocando_ou_carregando(midia_do_chrome(d)) else (SEM_VIDEO, "")
        if endereco_da_aula(tela) == endereco and botao_do_play(tela):
            return COM_VIDEO, ""
    # A página da aula sem o play: o estado do vídeo vai junto.
    return None, f"{SEM_O_PLAYER}; {descrever_a_midia(midia_do_chrome(d))}"


# --- O mapa das aulas (P293 1), só no banco do servidor ---
# Os 7 cursos da turma do Rafael pela posição na lista de Turmas do site (Continuar aprendendo → Turmas): primeiro os
# dois de Shopee Vídeo, depois os outros na ordem da lista e, por último, o dos encontros ao vivo (P293 1). Os nomes dos
# cursos não vão ao repositório. A 1ª aula de cada curso é guardada pelo Claude, com o passo curso:primeira:N do
# explorar na página dela; as outras vêm uma a uma pelo "Próximo" do site, com o endereço e o nome guardados aqui.
ORDEM_DOS_CURSOS = (4, 5, 1, 2, 6, 7, 3)
CHAVE_DO_MAPA = "curso_mapa"


def mapa_das_aulas():
    """
    {"cursos": {"posição": {"aulas": [{"endereco", "nome", "gravada_em", "sem_video"?}], "fim": bool}}} do banco; a
    aula sem vídeo (um documento ou um texto) tem a hora em que foi vista em sem_video.
    """
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
        falta = next((aula for aula in aulas if not aula.get("gravada_em") and not aula.get("sem_video")), None)
        return posicao, falta
    return None


def anotar_a_aula_gravada(posicao, endereco, agora=None):
    """A aula do curso gravada inteira: a próxima vez segue para a seguinte."""
    def mudar(curso):
        for aula in curso["aulas"]:
            if aula["endereco"] == endereco:
                aula["gravada_em"] = _texto(_agora(agora))
    _mudar_o_curso(posicao, mudar)


def anotar_a_aula_sem_video(posicao, endereco, agora=None):
    """
    A aula sem vídeo (um documento ou um texto), que a noite ainda não sabe guardar: fica marcada no mapa e volta quando
    souber (o documento baixado pelo botão do site, o texto e os links da aula: nenhuma aula é pulada, pedidos do Rafael
    de 23/11/2026), e a seguinte vem pelo Próximo dela.
    """
    def mudar(curso):
        for aula in curso["aulas"]:
            if aula["endereco"] == endereco:
                aula["sem_video"] = _texto(_agora(agora))
    _mudar_o_curso(posicao, mudar)


def desmarcar_a_aula(posicao, endereco):
    """A aula gravada que não serviu (preta ou muda) volta a ficar por gravar."""
    def mudar(curso):
        for aula in curso["aulas"]:
            if aula["endereco"] == endereco:
                aula["gravada_em"] = ""
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


def resumo_do_mapa(mapa=None):
    """O mapa só em números, curso a curso na ordem: as aulas conhecidas, as gravadas e se o curso terminou."""
    mapa = mapa or mapa_das_aulas()
    partes = []
    for posicao in ORDEM_DOS_CURSOS:
        curso = mapa["cursos"].get(str(posicao)) or {}
        aulas = curso.get("aulas") or []
        gravadas = sum(1 for aula in aulas if aula.get("gravada_em"))
        sem_video = sum(1 for aula in aulas if aula.get("sem_video"))
        sem = f", {sem_video} sem vídeo" if sem_video else ""
        if curso.get("fim"):
            partes.append(f"curso {posicao}: terminado ({gravadas} aulas{sem})")
        elif aulas:
            partes.append(f"curso {posicao}: {gravadas} de {len(aulas)} aula(s) conhecida(s) gravada(s){sem}")
        else:
            partes.append(f"curso {posicao}: sem a 1ª aula")
    return "; ".join(partes)


def _aberta_no_explorar(d, tipo, porque):
    """O que o explorar diz da aula que tentou abrir: o tipo, o vídeo e o play, só em palavras fixas e números."""
    if not tipo:
        return False, f"a aula não abriu ({porque})"
    play = "o play na tela" if botao_do_play(d.dump_hierarchy()) else "sem o play na tela"
    return True, f"aula aberta, {tipo}: {descrever_a_midia(midia_do_chrome(d))}; {play}"


def _proxima_no_explorar(d, pausa):
    """O passo curso:proximo: toca no Próximo da aula aberta e abre a seguinte pela barra, do alto, sem mudar o mapa."""
    tela = d.dump_hierarchy()
    atual, ponto = endereco_da_aula(tela), botao_do_proximo(tela)
    if not atual or not ponto:
        return False, "a tela não é a de uma aula com o Próximo"
    d.click(*ponto)
    for _ in range(ESPERA_DA_PAGINA // PASSO_DA_ESPERA):
        pausa(PASSO_DA_ESPERA)
        nova = endereco_da_aula(d.dump_hierarchy())
        if nova and nova != atual:
            pausar_o_que_toca(d, pausa)
            tipo, porque = ir_para_o_endereco(d, nova, pausa)
            return _aberta_no_explorar(d, tipo, porque)
    return False, "o Próximo não abriu a aula seguinte"


def curso_no_explorar(d, argumento, pausa=time.sleep):
    """
    O passo curso do explorar: curso:primeira:N guarda a aula aberta no Chrome como a 1ª do curso na posição N da lista
    de Turmas (o Claude a abre com o mapa do site); curso:abrir:N abre a 1ª aula do curso N pela barra de endereço,
    como a noite abre, e curso:proximo, a seguinte à aberta (os dois sem mudar o mapa, com o celular mudo); curso
    sozinho diz o mapa em números. O endereço fica no banco, e o log diz só números e palavras fixas.
    """
    partes = [parte.strip() for parte in argumento.split(":")] if argumento else []
    if not partes:
        return True, resumo_do_mapa()
    if partes == ["proximo"]:
        return _proxima_no_explorar(d, pausa)
    if partes[0] not in ("primeira", "abrir") or len(partes) != 2 or not partes[1].isdigit():
        return False, ("curso:primeira:N guarda a aula aberta como a 1ª do curso N; curso:abrir:N abre a 1ª do curso "
                       "N; curso:proximo abre a seguinte; curso diz o mapa")
    posicao = int(partes[1])
    if posicao not in ORDEM_DOS_CURSOS:
        return False, f"o curso vai de 1 a {len(ORDEM_DOS_CURSOS)} (a posição na lista de Turmas)"
    if partes[0] == "abrir":
        aulas = (mapa_das_aulas()["cursos"].get(str(posicao)) or {}).get("aulas") or []
        if not aulas:
            return False, f"o curso {posicao} ainda não tem a 1ª aula no mapa"
        tipo, porque = ir_para_o_endereco(d, aulas[0]["endereco"], pausa)
        return _aberta_no_explorar(d, tipo, porque)
    endereco = endereco_da_aula(d.dump_hierarchy())
    if not endereco:
        return False, "a tela não é a de uma aula do curso"
    if not guardar_a_primeira_aula(posicao, endereco):
        return False, f"o curso {posicao} já tem aula gravada: a 1ª dele não muda"
    return True, f"1ª aula do curso {posicao} guardada"


def toca_aula(nome, argumento):
    """
    O passo do explorar pode fazer o vídeo de uma aula tocar (abrir uma aula ou tocar o vídeo do Chrome)? Com ele,
    também de dia, o celular fica mudo: ele fica no quarto do Rafael (pedido dele, 22/11/2026).
    """
    acao = (argumento or "").split(":")[0].strip().lower()
    return (nome == "curso" and acao in ("abrir", "proximo")) or (nome == "midia" and acao == "tocar")


def tocar_pelo_play(d, pausa=None):
    """
    A aula tocando, conferida pela sessão de mídia do Chrome: a que começou sozinha com a página segue sem toque (a
    que está carregando, também); a outra, pelo play do player, tocado uma vez só. True com a aula tocando.
    """
    pausa = pausa or time.sleep
    tocado = False
    for _ in range(ESPERA_DO_PLAY // PASSO_DA_ESPERA):
        midia = midia_do_chrome(d)
        if midia and midia["estado"] == "tocando":
            return True
        if not tocado and not _tocando_ou_carregando(midia):
            ponto = botao_do_play(d.dump_hierarchy())
            if not ponto:
                return False
            d.click(*ponto)
            tocado = True
        pausa(PASSO_DA_ESPERA)
    return False


# --- A gravação da madrugada (P289 1 a P293 1, 22/11/2026, e P296 1, 23/11/2026) ---
# Depois do Horário do Robô, de madrugada, as aulas são gravadas uma a uma até um pouco antes da limpeza
# das 4h (P289 1), na velocidade normal (P292 1), com o volume de mídia no meio só durante a aula (P291 1)
# e só com o disco do servidor abaixo de 70% (P290 1). O robô da Shopee Vídeo tem a preferência (pedido do
# Rafael, 22/11): o robô que precisa do celular (um botão do painel, a limpeza das 4h) pede, e a aula para e
# solta o celular em segundos. Com o Horário do Robô no Dia Todo, enquanto o curso não termina, o robô
# começa às 4h, e a madrugada da 0h às 3h45 é do curso (P296 1, horario_do_robo).
FIM_DA_NOITE = (3, 45)
HORA_DO_ROBO_NO_CURSO = 4
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


def horario_do_robo(inicio, fim):
    """
    (início, fim) do Horário do Robô que vale agora, em horas: o do painel e, enquanto o curso não termina, sem a
    madrugada, que é do curso (o robô começa às HORA_DO_ROBO_NO_CURSO). Terminado o curso, volta o do painel, como o
    Dia Todo. Escolha do Rafael (P296 1, 23/11/2026): DECISOES.md, Trabalho com o Claude.
    """
    inicio, fim = int(inicio), int(fim)
    if CURSO_EM_ANDAMENTO and inicio < HORA_DO_ROBO_NO_CURSO < fim:
        return HORA_DO_ROBO_NO_CURSO, fim
    return inicio, fim


def na_madrugada(config, agora=None):
    """
    Agora é a madrugada da gravação: fora do Horário do Robô (config, a do painel, sem a madrugada do curso:
    horario_do_robo) e antes do FIM_DA_NOITE (P289 1)? Com o Horário do Robô no Dia Todo, da 0h às 3h45 enquanto o
    curso não termina (P296 1); terminado, nunca.
    """
    momento = _agora(agora)
    inicio, fim = horario_do_robo(config.get("robo_inicio", 8), config.get("robo_fim", 22))
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
    O volume de mídia em 0 de madrugada, no explorar do curso (P294 1) e antes de cada aula abrir (o vídeo pode
    começar a tocar sozinho): o celular não faz barulho à noite. O de antes fica guardado como o da aula e volta no
    fim (devolver_o_volume). (atual, máximo) depois, ou None sem o volume.
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


def gravar_a_aula(d, alvo, destino, ir_para_a_aula, tocar, pausa=None, relogio=None, abrir=subprocess.Popen,
                  madrugada=None):
    """
    A aula aberta no Chrome do celular e gravada em destino, do começo ao fim. A ordem protege o quarto do Rafael
    (pedido dele, 22/11/2026): o gravador liga antes e, gravando o som, deixa o alto-falante mudo; o volume sobe só
    com ele gravando; a aula abre (ir_para_a_aula) já com o gravador ligado, porque o vídeo pode começar a tocar
    sozinho com a página (23/11/2026), e tocar(d) dá o play quando ele não começou; no fim, a aula pausa e o volume
    volta antes de o gravador parar. O robô que pede o celular, a madrugada que acaba (3h45) e o gravador que cai
    param a aula, que fica pela metade (P295 1: ela volta depois, do início). Devolve (aberta, inteira, motivo fixo):
    aberta diz se a página da aula abriu; na aula sem vídeo, (True, False, SEM_VIDEO).
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
            return False, False, "o gravador não ficou gravando"
        if not subir_o_volume(d):
            return False, False, "sem o volume de mídia"
        tipo, porque = ir_para_a_aula(d)
        if not tipo:
            return False, False, f"a aula não abriu ({porque})"
        if tipo == SEM_VIDEO:
            return True, False, SEM_VIDEO
        if not tocar(d):
            return True, False, "a aula não começou a tocar"
        olho, comeco = OlhoNaAula(), relogio()
        while True:
            pausa(OLHADA_DA_AULA)
            anotar_o_sinal()
            if not gravacao.rodando():
                return True, False, "o gravador parou no meio"
            if pediram_o_celular(inicio):
                return True, False, "o robô pediu o celular"
            if not madrugada():
                return True, False, "a madrugada acabou"
            fim = olho.olhar(midia_do_chrome(d), relogio() - comeco)
            if fim:
                return True, fim != "carregando demais", fim
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


# --- A noite da gravação (P289 1 a P295 1) ---
# A unidade do systemd que o painel liga de madrugada (cursos_robo.py noite) grava as aulas da vez, uma a uma, com o
# celular (a trava do robô) só para abrir e gravar a aula; a fala e as folhas de quadros saem num ajudante à parte,
# com o celular livre, enquanto a aula seguinte grava. Para quando a madrugada acaba (3h45), o disco passa de 70%, o
# robô pede o celular ou a gravação sai preta ou muda (P288 3); a aula que fica pela metade é apagada e volta depois,
# inteira, do início (P295 1). Nada vai ao privado do Rafael de madrugada: o celular dele faria barulho.
REGISTRO_DO_CURSO = "curso"
PROCESSO_DA_AULA = "aula do curso"
PROCESSO_DA_NOITE = "noite do curso"
PASTA_DAS_GRAVACOES = os.path.expanduser("~/shopee_video/aulas_brutas")
# Quantas aulas que não abrem, seguidas, fazem a noite parar (o site fora, o login que caiu): a seguinte tenta de novo.
FALHAS_SEGUIDAS = 2
# O que para a aula sem ser falha: ela volta depois, inteira (P295 1), e a noite acaba aqui.
PARADAS_DA_AULA = ("o robô pediu o celular", "a madrugada acabou")
SEM_O_MUDO = "o celular não ficou mudo antes de abrir a aula"


def guardar_o_caso(d, motivo, resultado="não abriu"):
    """
    A tela da 1ª aula da noite que não abriu (o print, a forma da tela e o log do Chrome), guardada para o Claude
    achar o porquê, e a da 1ª aula sem vídeo, para ele conferir que era mesmo um documento ou um texto (casos_robo:
    cifrada no exportar, nunca no repositório).
    """
    import casos_robo
    return casos_robo.guardar(d, "curso", resultado, motivo, passo="abrir a aula")


def nome_no_proximo(xml):
    """O nome da aula seguinte, escrito na barra "Próximo: Nome"; "" sem ela."""
    for no in _nos(xml):
        if no["clicavel"] and no["texto"].startswith(ROTULO_DO_PROXIMO):
            return no["texto"][len(ROTULO_DO_PROXIMO):].strip()
    return ""


def endereco_da_vez(d, posicao, aula, pausa=None):
    """
    O endereço da aula da vez, com o celular mudo, antes de o gravador ligar: (endereço, ""). Com a aula no mapa, o
    dela; sem ela (a seguinte vem pelo Próximo da última do curso), abre a última, toca no Próximo, anota a nova no
    mapa e pausa o que começar a tocar. (None, o porquê) sem o endereço; "o curso terminou" na última aula.
    """
    pausa = pausa or time.sleep
    if aula:
        return aula["endereco"], ""
    ultima = mapa_das_aulas()["cursos"][str(posicao)]["aulas"][-1]["endereco"]
    tipo, porque = ir_para_o_endereco(d, ultima, pausa)
    if not tipo:
        return None, f"a última aula do mapa não abriu ({porque})"
    tela = d.dump_hierarchy()
    ponto = botao_do_proximo(tela)
    if not ponto:
        anotar_o_fim_do_curso(posicao)
        return None, "o curso terminou"
    nome = nome_no_proximo(tela)
    d.click(*ponto)
    for _ in range(ESPERA_DA_PAGINA // PASSO_DA_ESPERA):
        pausa(PASSO_DA_ESPERA)
        nova = endereco_da_aula(d.dump_hierarchy())
        if nova and nova != ultima:
            # A seguinte pode começar a tocar sozinha (muda): pausada já, ela abre de novo pela barra, do alto, com o
            # gravador ligado.
            pausar_o_que_toca(d, pausa)
            anotar_a_aula_seguinte(posicao, nova, nome)
            return nova, ""
    return None, "o Próximo não abriu a aula seguinte"


def numero_da_aula(posicao, endereco, mapa=None):
    """A posição da aula na lista do curso (1, 2...), para o nome da pasta dela; 0 fora do mapa."""
    aulas = ((mapa or mapa_das_aulas())["cursos"].get(str(posicao)) or {}).get("aulas") or []
    return next((numero for numero, aula in enumerate(aulas, 1) if aula["endereco"] == endereco), 0)


def qual_aula(posicao, numero):
    """
    "curso N, aula M", só números, para o registro de cada aula: o relatório da manhã diz qual aula deu certo e qual
    não deu, e por quê (pedido do Rafael, 23/11/2026). A aula fora do mapa sai só com o curso.
    """
    return f"curso {posicao}, aula {numero}" if numero else f"curso {posicao}"


def pode_comecar_a_noite(agora=None):
    """
    O painel liga a unidade da noite? Só com o curso em andamento, na madrugada, com o disco abaixo do limite e alguma
    aula por gravar (a unidade confere tudo de novo).
    """
    return (CURSO_EM_ANDAMENTO and na_madrugada(db.ler_config("shopee_video", {}) or {}, agora)
            and disco_usado() < LIMITE_DO_DISCO and proxima_aula() is not None)


class Ajudante:
    """A fala e as folhas de quadros de cada aula gravada, uma de cada vez, à parte, com o celular livre."""

    def __init__(self, guardar=None):
        import queue
        import threading
        self.fila, self.problema, self.guardadas = queue.Queue(), "", 0
        self._guardar = guardar or guardar_a_aula
        self._linha = threading.Thread(target=self._trabalhar, daemon=True)
        self._linha.start()

    def _trabalhar(self):
        while True:
            item = self.fila.get()
            if item is None:
                return
            arquivo, posicao, numero, endereco, fim = item
            try:
                _pasta, info = self._guardar(arquivo, posicao, numero, fim)
            except Exception as e:
                info = {"problema": f"a aula não foi lida ({type(e).__name__})"}
            for resto in (arquivo, arquivo + ".json"):
                if os.path.exists(resto):
                    os.remove(resto)
            if info.get("problema"):
                # Preta ou muda: o player não deixa gravar (P288 3); a aula volta a ficar por gravar, e a noite para.
                self.problema = self.problema or info["problema"]
                desmarcar_a_aula(posicao, endereco)
                registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, "não serviu",
                                             f"{qual_aula(posicao, numero)}: {info['problema']}", ok=False)
            else:
                self.guardadas += 1
                registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, "guardada",
                                             qual_aula(posicao, numero), ok=True)

    def mandar(self, arquivo, posicao, numero, endereco, fim):
        """A aula gravada vai para a fila; o .json ao lado do vídeo deixa a noite seguinte ler a que ficou na fila."""
        with open(arquivo + ".json", "w", encoding="utf-8") as saida:
            json.dump({"posicao": posicao, "numero": numero, "endereco": endereco, "fim": fim}, saida)
        self.fila.put((arquivo, posicao, numero, endereco, fim))

    def mandar_as_que_ficaram(self):
        """As gravações de uma noite que acabou antes de lê-las (a unidade parada no meio) voltam para a fila."""
        if not os.path.isdir(PASTA_DAS_GRAVACOES):
            return 0
        voltaram = 0
        for nome in sorted(os.listdir(PASTA_DAS_GRAVACOES)):
            caminho = os.path.join(PASTA_DAS_GRAVACOES, nome)
            if not nome.endswith(".mkv") or not os.path.exists(caminho + ".json"):
                continue
            with open(caminho + ".json", encoding="utf-8") as entrada:
                dados = json.load(entrada)
            self.fila.put((caminho, dados["posicao"], dados["numero"], dados["endereco"], dados["fim"]))
            voltaram += 1
        return voltaram

    def acabar(self):
        """Espera as aulas da fila serem lidas."""
        self.fila.put(None)
        self._linha.join()


def noite(conectar=None, pausa=None, ajudante=None, trava=None, conectado=None):
    """
    A gravação de uma madrugada (P289 1 a P295 1): as aulas da vez, uma a uma, até a madrugada acabar, o disco encher,
    o robô pedir o celular ou acabarem as aulas. A aula sem vídeo (um documento ou um texto) não para a noite: fica
    marcada no mapa, e a seguinte vem pelo Próximo dela. Devolve o que aconteceu numa frase só com números (vai ao log).
    """
    import celular_robo
    pausa = pausa or time.sleep
    if conectar is None:
        import postador_shopee_video as ps
        conectar = (lambda: ps.conectar(celular=True))
    trava = trava or celular_robo.trava
    conectado = conectado or celular_robo.conectado
    if not CURSO_EM_ANDAMENTO:
        return "sem curso por gravar"
    os.makedirs(PASTA_DAS_GRAVACOES, exist_ok=True)
    ajudante = ajudante or Ajudante()
    ajudante.mandar_as_que_ficaram()
    gravadas = metade = falhas = sem_video = 0
    motivo = "nenhuma aula por gravar"
    try:
        while True:
            if ajudante.problema:
                motivo = ajudante.problema
                break
            if not _madrugada_agora():
                motivo = "a madrugada acabou"
                break
            if disco_usado() >= LIMITE_DO_DISCO:
                motivo = f"o disco passou de {LIMITE_DO_DISCO}%"
                break
            da_vez = proxima_aula()
            if not da_vez:
                motivo = "nenhuma aula por gravar"
                break
            if not conectado():
                motivo = "o celular desconectado"
                break
            posicao, aula = da_vez
            with trava() as livre:
                if not livre:
                    motivo = "o celular com o robô"
                    break
                anotar_o_sinal()
                d = conectar()
                # O vídeo da aula pode começar a tocar sozinho quando a página abre: o celular fica mudo até o gravador
                # ligar, e então o som vai só ao servidor (o celular fica no quarto do Rafael, pedido dele de
                # 22/11/2026: DECISOES.md, Trabalho com o Claude).
                if not calar_o_celular(d):
                    motivo = SEM_O_MUDO
                    break
                endereco, detalhe = endereco_da_vez(d, posicao, aula, pausa)
                aberta, inteira, fim, destino = False, False, detalhe, ""
                if endereco:
                    destino = os.path.join(PASTA_DAS_GRAVACOES, f"{_agora():%Y%m%d-%H%M%S}.mkv")
                    aberta, inteira, fim = gravar_a_aula(
                        d, getattr(d, "serial", ""), destino,
                        lambda celular: ir_para_o_endereco(celular, endereco, pausa),
                        lambda celular: tocar_pelo_play(celular, pausa), pausa=pausa)
                if fim == SEM_VIDEO and not sem_video:
                    guardar_o_caso(d, "a aula não tem vídeo", "sem vídeo")
                elif not aberta and fim != "o curso terminou" and not falhas:
                    guardar_o_caso(d, fim)
            if inteira:
                # Marcada já: a seguinte vem pelo Próximo dela, enquanto o ajudante lê esta.
                anotar_a_aula_gravada(posicao, endereco)
                gravadas += 1
                falhas = 0
                ajudante.mandar(destino, posicao, numero_da_aula(posicao, endereco), endereco, fim)
                continue
            if destino and os.path.exists(destino):
                os.remove(destino)
            if fim == "o curso terminou":
                continue
            numero = numero_da_aula(posicao, endereco or (aula or {}).get("endereco"))
            if fim == SEM_VIDEO:
                # Um documento ou um texto: fica marcada e volta, sem ser pulada (pedidos do Rafael de 23/11/2026:
                # DECISOES.md, Trabalho com o Claude).
                anotar_a_aula_sem_video(posicao, endereco)
                sem_video += 1
                falhas = 0
                registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, SEM_VIDEO,
                                             f"{qual_aula(posicao, numero)}: a aula não tem vídeo", ok=None)
                continue
            resultado = "pela metade" if aberta else "não abriu"
            registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, resultado,
                                         f"{qual_aula(posicao, numero)}: {fim}",
                                         ok=None if fim in PARADAS_DA_AULA else False)
            if aberta:
                metade += 1
            if fim in PARADAS_DA_AULA:
                motivo = fim
                break
            falhas += 1
            if falhas >= FALHAS_SEGUIDAS:
                motivo = fim
                break
    finally:
        soltar_o_sinal()
        ajudante.acabar()
    resumo = (f"{gravadas} aula(s) gravada(s), {ajudante.guardadas} guardada(s), {metade} pela metade, "
              f"{sem_video} sem vídeo; parou: {ajudante.problema or motivo}")
    registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_NOITE, "concluída", resumo, ok=not ajudante.problema)
    return resumo


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
    if argumentos == ["noite"]:
        print(noite())
        return 0
    print("uso: cursos_robo.py instalar | estado | aulas ... | noite")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

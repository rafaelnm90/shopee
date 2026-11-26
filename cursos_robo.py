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


# As janelas que o próprio Chrome abre embaixo da página: a do gerenciador de senhas ("touch to fill"), que oferece a
# senha salva quando um campo do login é tocado, e a de salvar a senha depois do login. Elas cobrem a página (a leitura
# da tela não mostra os campos com ela aberta, no Motorola, em 23/11/2026) e saem pela tecla voltar, sem escolher nada.
FOLHAS_DO_CHROME = ("com.android.chrome:id/touch_to_fill", "com.android.chrome:id/bottom_sheet")


def folha_do_chrome_na_tela(xml):
    """Uma janela do próprio Chrome (FOLHAS_DO_CHROME) está aberta embaixo da página?"""
    try:
        raiz = ET.fromstring(xml or "")
    except ET.ParseError:
        return False
    return any(no.get("resource-id", "").startswith(FOLHAS_DO_CHROME) for no in raiz.iter("node"))


def _fechar_a_folha_do_chrome(d, pausa):
    """Fecha a janela do Chrome pela tecla voltar, só com ela na tela (sem ela, voltar mudaria a página). A tela."""
    tela = d.dump_hierarchy()
    if folha_do_chrome_na_tela(tela):
        d.press("back")
        pausa(1)
        tela = d.dump_hierarchy()
    return tela


def _saiu_do_login(d, pausa):
    """Espera o site entrar, conferindo a página de 2 em 2 s. (saiu, a última tela lida)."""
    tela = ""
    for _ in range(ESPERA_DO_LOGIN // PASSO_DA_ESPERA):
        pausa(PASSO_DA_ESPERA)
        # A janela de salvar a senha cobre a página e esconde os campos: fechada antes, a leitura é a da página.
        tela = _fechar_a_folha_do_chrome(d, pausa)
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
    if not campos_do_login(_fechar_a_folha_do_chrome(d, pausa)):
        return False, "a tela não é a de login do curso"
    for indice, valor in enumerate((acesso["email"], acesso["senha"])):
        # O toque no campo pode abrir a janela do gerenciador de senhas do Chrome, que cobre a página: ela é fechada,
        # e o campo é tocado de novo quando o cursor não ficou nele (o robô escreve o login guardado, conferido).
        for _ in range(2):
            campos = campos_do_login(_fechar_a_folha_do_chrome(d, pausa))
            if not campos:
                return False, "a página de login mudou no meio"
            d.click(*campos[indice])
            pausa(1)
            foco = campo_em_foco(_fechar_a_folha_do_chrome(d, pausa))
            if foco is not None and foco == (indice == 1):
                break
        else:
            return False, "o cursor não ficou no campo certo do login"
        escrever(d, valor)
    d.press("enter")
    saiu, tela = _saiu_do_login(d, pausa)
    if not saiu:
        ponto = achar(tela, "Entrar")
        if ponto:
            d.click(*ponto)
            saiu, tela = _saiu_do_login(d, pausa)
    if not saiu:
        return False, "o login não passou (a página de login continua)"
    # A janela de salvar a senha, que o Chrome abre depois do login, sai sem escolher nada.
    _fechar_a_folha_do_chrome(d, pausa)
    return True, "login feito"


# --- As páginas do curso no Chrome (mapeadas em 22/11/2026, com o celular mudo) ---
# Na aula, o player tem os botões pelo nome ("Tocar vídeo" no meio dele e na barra; o nome vem no texto do botão no
# Chrome do Motorola, como na tela das 03:45 de 23/11/2026, e na descrição em outros) e os ids "plyr-..."; embaixo,
# as abas Módulos, Comentários e Anotações. Na aba Módulos, cada módulo é um botão e, aberto, mostra uma linha por aula
# com o nome e a duração ("Nome 4:54"), numa lista que rola por dentro. A barra "Próximo: Nome" leva à aula seguinte
# do curso, e o endereço da aula fica na barra do Chrome (".../m/lessons/<código>"). Trocando de aula pela lista, a
# página continua rolada, e o player some da tela e da leitura dela: a página sobe antes do play. Há aulas sem vídeo,
# um documento ou um texto (o vídeo do Rafael das 08:22 de 23/11/2026): a página dela tem as abas, sem player nenhum.
# Os nomes das aulas e os endereços ficam só no banco do servidor, nunca no log nem no repositório. Com o vídeo pausado,
# a barra do player mostra, da esquerda para a direita (24/11/2026): Reiniciar (volta o vídeo ao começo), Retroceder
# 10s, Tocar vídeo, Avançar 10s, a barra do tempo, Mutar (nunca tocado), o volume, Configurações (a Velocidade),
# picture-in-picture e tela cheia. O site guarda onde o vídeo de cada aula parou e o abre dali.
LINHA_DA_AULA = re.compile(r"(?P<nome>.*\S)\s+(?P<tempo>\d{1,2}(?::\d{2}){1,2})")
CAMINHO_DA_AULA = re.compile(r"[\w.-]+/m/lessons/[\w-]+")
ROTULO_DO_PROXIMO = "Próximo:"
ROTULO_DO_PLAY = "Tocar vídeo"
ROTULO_DO_REINICIAR = "Reiniciar"
ID_DO_PLAYER = "plyr-"
ID_DAS_ABAS = "trigger-modules"
CAIXA_DA_NOVA_GUIA = "search_box_text"


def segundos_do_tempo(texto):
    """A duração escrita na linha da aula em segundos: "4:54" dá 294; "1:02:03", 3723."""
    total = 0
    for parte in texto.split(":"):
        total = total * 60 + int(parte)
    return total


def _no(no):
    """Um nó da tela: texto, descrição, id, classe, caixa e se aceita toque; None sem tamanho."""
    caixa = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", no.get("bounds", ""))
    if not caixa:
        return None
    x1, y1, x2, y2 = map(int, caixa.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    return {"texto": no.get("text", ""), "descricao": no.get("content-desc", ""),
            "id": no.get("resource-id", "").split(":id/")[-1], "classe": no.get("class", "").rsplit(".", 1)[-1],
            "caixa": (x1, y1, x2, y2), "clicavel": no.get("clickable") == "true", "foco": no.get("focused") == "true"}


def _nos(xml):
    """Os nós da tela com tamanho: texto, descrição, id, classe, caixa e se aceitam toque. [] sem a tela."""
    try:
        raiz = ET.fromstring(xml or "")
    except ET.ParseError:
        return []
    return [dados for dados in map(_no, raiz.iter("node")) if dados]


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


def nome_no_proximo(xml):
    """
    O nome da aula seguinte, escrito na barra "Próximo: Nome" (o site põe "Próxima aula:" no fim do texto do botão, que
    sai); "" sem ela.
    """
    for no in _nos(xml):
        if no["clicavel"] and no["texto"].startswith(ROTULO_DO_PROXIMO):
            return re.sub(r"\s*Próxima aula:?\s*$", "", no["texto"][len(ROTULO_DO_PROXIMO):]).strip()
    return ""


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


def botao_do_reiniciar(xml):
    """
    O centro do Reiniciar da barra do player, que volta o vídeo ao começo (a barra aparece com o vídeo pausado); None
    sem ele à vista. Só ele: o Mutar, na mesma barra, nunca é tocado (pedido do Rafael, 23/11/2026).
    """
    botoes = [no for no in _nos(xml) if no["clicavel"] and ROTULO_DO_REINICIAR in (no["texto"], no["descricao"])]
    return _centro(botoes[0]["caixa"]) if botoes else None


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
SEM_A_EDICAO = "a barra de endereço não ficou em edição"
SEM_O_ENDERECO = "o endereço da aula não ficou na barra"
# Depois do toque na barra, o Chrome abre a edição dela (o foco nela, com o teclado) em até ESPERA_DA_EDICAO s. Fora da
# edição, o foco é da página, e as teclas iriam a ela: ao player, que tem teclas próprias (a do mudo, a de pular), ou a
# um campo da página (a caixa de comentário da aula, que nunca é tocada). A edição sai pela tecla voltar, uma vez para o
# teclado e outra para a edição (o teste de 25/11/2026, à 01:30), até VOLTAS_DA_EDICAO vezes e só com ela aberta: fora
# dela, voltar volta a página.
ESPERA_DA_EDICAO = 5
VOLTAS_DA_EDICAO = 2
SEM_O_PLAYER = "a página não mostrou o player"
EM_BRANCO = "a página da aula ficou em branco"
# Depois do Enter, a guia pode ficar sem nada da página, só com o quadro do Chrome, mesmo com o endereço da aula na
# barra: às 04:05, 04:16 e 04:25 de 24/11/2026, nos cursos 4, 6 e 7, por mais de 20 s, e a página só apareceu quando
# o Chrome saiu da frente e voltou (a rodada do robô no meio). Em branco, a espera vai até ESPERA_DA_PAGINA_EM_BRANCO,
# e o Chrome sai da frente e volta a cada ESPERA_DA_PAGINA, até VEZES_FORA_DA_FRENTE vezes, sem toque na página.
ESPERA_DA_PAGINA_EM_BRANCO = 90
VEZES_FORA_DA_FRENTE = 2


def app_da_frente(d):
    """O pacote do app que está na frente do celular; "" sem a leitura."""
    try:
        return (d.app_current() or {}).get("package") or ""
    except Exception:
        return ""


def trazer_o_chrome(d, pausa=None):
    """
    O Chrome na frente do celular (o robô deixa a Shopee no Eu no fim de cada rodada que mexe no celular), sempre com
    a tela em pé. Devolve o que o chrome_em_pe fez ("" com a tela já em pé).
    """
    pausa = pausa or time.sleep
    if app_da_frente(d) != PACOTE_DO_CHROME:
        d.app_start(PACOTE_DO_CHROME, wait=True)
        pausa(ESPERA_DO_CHROME)
    return chrome_em_pe(d, pausa)


# A tela em pé com o Chrome na frente (26/11/2026): a noite inteira e o teste da manhã tiveram o Chrome deitado (na
# horizontal), e a página da aula não mostrava a lista das aulas, mesmo com a rotação automática desligada e a tela
# posta em pé (P301 2). O registro do Android mostrou a tela girando a cada vez que o Chrome vinha para a frente: o
# pedido da tela deitada vinha do próprio Chrome (o app da Shopee sempre pede a tela em pé, por isso o robô de dia não
# sente). Deitada, a tela é travada em pé pelo comando do Android e, se o Chrome insistir, ele é fechado e aberto de
# novo: as guias voltam, e a aula é aberta pelo caminho de sempre. Cada vez vai ao registro com o que o Android diz (o
# que o app pede e as duas rotações), para o Claude achar quando e por que o Chrome pede a tela deitada.
TELA_DEITADA = (1, 3)
TRAVAR_EM_PE = ["cmd", "window", "user-rotation", "lock", "0"]
CHROME_POSTO_EM_PE = "chrome posto em pé"
CHROME_REABERTO = "chrome fechado e aberto de novo"
CHROME_DEITADO = "chrome continuou deitado"


def rotacao_da_tela(d):
    """A rotação da tela agora, pelo uiautomator2 (0 em pé; 1 e 3 deitada); None sem a leitura."""
    try:
        return int((d.info or {}).get("displayRotation"))
    except Exception:
        return None


def porque_deitada(d):
    """
    O que o Android diz da tela deitada, só em palavras fixas dele e números: a orientação que o app da frente pede
    (dumpsys window) e a rotação automática e a do usuário (as configurações da P301 2).
    """
    pedido = re.search(r"mCurrentAppOrientation=(?:SCREEN_ORIENTATION_)?([A-Z_]+|-?\d+)",
                       _saida(d, ["dumpsys", "window", "displays"]))
    rotacoes = [_saida(d, ["settings", "get", "system", nome]).strip()
                for nome in ("accelerometer_rotation", "user_rotation")]
    automatica, do_usuario = (valor if re.fullmatch(r"\d+", valor) else "?" for valor in rotacoes)
    return (f"o app pede {pedido.group(1).lower() if pedido else '? (sem a leitura)'}, "
            f"rotação automática {automatica}, rotação do usuário {do_usuario}")


def chrome_em_pe(d, pausa):
    """
    O Chrome da frente com a tela em pé. Em pé, sem a leitura da rotação ou com outro app na frente, nada muda e
    devolve "". Deitada, a tela é travada em pé (TRAVAR_EM_PE) e, ainda deitada, o Chrome é fechado e aberto de novo;
    devolve o que deu (CHROME_POSTO_EM_PE, CHROME_REABERTO ou CHROME_DEITADO), que também vai ao registro, e a tela do
    Chrome que continua deitado vai aos casos.
    """
    antes = rotacao_da_tela(d)
    if antes not in TELA_DEITADA or app_da_frente(d) != PACOTE_DO_CHROME:
        return ""
    porque = porque_deitada(d)
    _saida(d, TRAVAR_EM_PE)
    pausa(ESPERA_DA_TELA_EM_PE)
    if rotacao_da_tela(d) not in TELA_DEITADA:
        resultado = CHROME_POSTO_EM_PE
    else:
        d.app_stop(PACOTE_DO_CHROME)
        pausa(ESPERA_DO_CHROME)
        d.app_start(PACOTE_DO_CHROME, wait=True)
        pausa(ESPERA_DO_CHROME)
        resultado = CHROME_REABERTO if rotacao_da_tela(d) not in TELA_DEITADA else CHROME_DEITADO
    registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_TELA, resultado,
                                 f"a rotação da tela era {antes}; {porque}", ok=resultado != CHROME_DEITADO)
    if resultado == CHROME_DEITADO:
        guardar_o_caso(d, f"{CHROME_DEITADO} ({porque})", "tela deitada", passo="pôr o chrome em pé")
    return resultado


def barra_em_edicao(xml):
    """A barra de endereço do Chrome em edição (o foco nela, com o teclado): só nela o endereço pode ser escrito."""
    return any(no["id"] == "url_bar" and no["foco"] for no in _nos(xml))


def como_ficou_a_barra(texto, endereco):
    """
    O que a barra mostrava quando o endereço não ficou, só em números (o registro da noite é lido no checkup): as letras
    dela, o começo igual ao do endereço e as letras dele.
    """
    atual, alvo = _sem_o_https(texto), _sem_o_https(endereco)
    iguais = next((n for n, (a, b) in enumerate(zip(atual, alvo)) if a != b), min(len(atual), len(alvo)))
    return f"a barra com {len(atual)} letras, igual nas primeiras {iguais} de {len(alvo)}"


# Na noite de 25/11/2026, depois da 1ª aula, o endereço não ficou escrito na barra em 5 tentativas seguidas, com a barra
# lida uma vez só, 1 s depois da escrita: a barra é lida de novo, de segundo em segundo, por até ESPERA_DA_ESCRITA s, e
# o pedaço que o Chrome completa sozinho depois sai com a tecla de apagar à frente.
ESPERA_DA_ESCRITA = 5


def escrever_na_barra(d, endereco, pausa=None):
    """
    O endereço escrito na barra de endereço do Chrome (já tocada e em edição) tecla por tecla, pelo adb, como num
    teclado. O texto posto pela acessibilidade, o jeito dos campos da Shopee, aparecia na barra, mas o Chrome não o
    tomava como escrito, e o Enter abria outra página (a do Gemini, às 03:00, 03:15 e 03:30 de 23/11/2026). O pedaço
    que o Chrome completa sozinho depois do escrito fica marcado e sai com a tecla de apagar à frente. (True, "") com a
    barra mostrando o endereço; (False, como_ficou_a_barra) sem ele.
    """
    pausa = pausa or time.sleep
    _saida(d, ["input", "text", endereco])
    pausa(1)
    _saida(d, ["input", "keyevent", "KEYCODE_FORWARD_DEL"])
    texto = ""
    for _ in range(ESPERA_DA_ESCRITA):
        pausa(1)
        texto = texto_da_barra(d.dump_hierarchy()) or ""
        if _sem_o_https(texto) == _sem_o_https(endereco):
            return True, ""
        if _sem_o_https(texto).startswith(_sem_o_https(endereco)):
            _saida(d, ["input", "keyevent", "KEYCODE_FORWARD_DEL"])
    return False, como_ficou_a_barra(texto, endereco)


def _tocando_ou_carregando(midia):
    return bool(midia) and midia["estado"] in ("tocando", "carregando")


def pagina_em_branco(xml):
    """A guia do Chrome sem nada da página: a página (o WebView) fora da tela ou sem nenhum nó dentro dela."""
    try:
        raiz = ET.fromstring(xml or "")
    except ET.ParseError:
        return False
    pagina = next((no for no in raiz.iter("node") if no.get("class") == "android.webkit.WebView"), None)
    return pagina is None or len(_nos(ET.tostring(pagina, encoding="unicode"))) <= 1


def sair_da_edicao(d, pausa):
    """A barra de endereço fora da edição pela tecla voltar, só enquanto ela está em edição. True fora dela."""
    for _ in range(VOLTAS_DA_EDICAO):
        if not barra_em_edicao(d.dump_hierarchy()):
            return True
        d.press("back")
        pausa(1)
    return not barra_em_edicao(d.dump_hierarchy())


def _sair_e_voltar_ao_chrome(d, pausa):
    """O Chrome sai da frente (a tela inicial do Android) e volta, com a mesma guia: nada é tocado na página."""
    d.press("home")
    pausa(ESPERA_DO_CHROME)
    trazer_o_chrome(d, pausa)


def _abrir_pela_barra(d, endereco, pausa):
    """Uma vez: o endereço escrito na barra da guia da frente e a página nova esperada. (tipo, porque, a tela)."""
    if trazer_o_chrome(d, pausa) == CHROME_DEITADO:
        return None, CHROME_DEITADO, ""
    tela = _fechar_a_folha_do_chrome(d, pausa)
    barra = barra_na_tela(tela)
    if not barra and app_da_frente(d) == PACOTE_DO_CHROME:
        # A barra some quando a página rola para baixo: rolando para cima, ela volta.
        d.swipe(540, 700, 540, 1500, 0.3)
        pausa(1)
        tela = d.dump_hierarchy()
        barra = barra_na_tela(tela)
    if not barra:
        return None, SEM_A_BARRA if app_da_frente(d) == PACOTE_DO_CHROME else SEM_O_CHROME, tela
    pausar_o_que_toca(d, pausa)
    if barra_em_edicao(tela):
        # A edição que ficou aberta (com o que já estava escrito) sai antes: o toque abre uma nova, vazia.
        if not sair_da_edicao(d, pausa):
            return None, SEM_A_EDICAO, tela
        tela = d.dump_hierarchy()
        barra = barra_na_tela(tela)
        if not barra:
            return None, SEM_A_BARRA, tela
    d.click(*_centro(barra["caixa"]))
    # Só com a barra em edição o endereço vai pelo adb (ESPERA_DA_EDICAO). Sem a edição, nada é escrito nem voltado.
    for _ in range(ESPERA_DA_EDICAO):
        pausa(1)
        if barra_em_edicao(d.dump_hierarchy()):
            break
    else:
        return None, SEM_A_EDICAO, tela
    escrito, como_ficou = escrever_na_barra(d, endereco, pausa)
    if not escrito:
        # Sem o Enter: a barra sai da edição, e a página de antes fica como estava.
        sair_da_edicao(d, pausa)
        return None, f"{SEM_A_ESCRITA} ({como_ficou})", tela
    _saida(d, ["input", "keyevent", "KEYCODE_ENTER"])
    tela, fora_da_frente = "", 0
    for volta in range(1, ESPERA_DA_PAGINA_EM_BRANCO // PASSO_DA_ESPERA + 1):
        pausa(PASSO_DA_ESPERA)
        tela = _fechar_a_folha_do_chrome(d, pausa)
        if endereco_da_aula(tela) == endereco and (botao_do_play(tela) or _tocando_ou_carregando(midia_do_chrome(d))):
            return COM_VIDEO, "", tela
        em_branco = endereco_da_aula(tela) == endereco and pagina_em_branco(tela)
        if volta * PASSO_DA_ESPERA >= ESPERA_DA_PAGINA and not em_branco:
            break
        if em_branco and volta % (ESPERA_DA_PAGINA // PASSO_DA_ESPERA) == 0 and fora_da_frente < VEZES_FORA_DA_FRENTE:
            fora_da_frente += 1
            _sair_e_voltar_ao_chrome(d, pausa)
    if endereco_da_aula(tela) == endereco and pagina_em_branco(tela):
        return None, EM_BRANCO, tela
    if endereco_da_aula(tela) != endereco:
        return None, SEM_O_ENDERECO, tela
    if pagina_da_aula_pronta(tela) and not tem_player(tela):
        # A página pronta sem player: mais um tempo para o player que demora, e então é a aula sem vídeo.
        pausa(ESPERA_SEM_O_PLAYER)
        tela = d.dump_hierarchy()
        if endereco_da_aula(tela) == endereco and pagina_da_aula_pronta(tela) and not tem_player(tela):
            return ((COM_VIDEO, "", tela) if _tocando_ou_carregando(midia_do_chrome(d)) else (SEM_VIDEO, "", tela))
        if endereco_da_aula(tela) == endereco and botao_do_play(tela):
            return COM_VIDEO, "", tela
    # A página da aula sem o play: o estado do vídeo vai junto.
    return None, f"{SEM_O_PLAYER}; {descrever_a_midia(midia_do_chrome(d))}", tela


# A sessão do site vence depois de algumas horas (às 09:53 de 23/11/2026, o endereço da aula levou à página de login),
# e a guia nova (a Nova guia, onde o Chrome abre depois de horas parado) leva o endereço à página inicial do curso: o
# endereço é escrito de novo, até VEZES_NA_BARRA vezes, com o login feito no meio quando o site pede.
VEZES_NA_BARRA = 4
SEM_O_LOGIN = "o site pediu o login, e o login não passou"


def _entrar(d, pausa):
    """O login do curso com o acesso guardado (entrar_no_curso), com o escrever e o achar do explorar."""
    import postador_shopee_video as ps   # aqui dentro: o postador importa este módulo
    return entrar_no_curso(d, ps.escrever, ps.achar, pausa)


def _mesmo_site(barra, endereco):
    """A barra mostra uma página do site do curso (o mesmo do endereço da aula)?"""
    return bool(barra) and _sem_o_https(barra).split("/", 1)[0] == _sem_o_https(endereco).split("/", 1)[0]


def ir_para_o_endereco(d, endereco, pausa=None, entrar=None):
    """
    Abre o endereço da aula na guia da frente do Chrome, escrito na barra de endereço, e espera a página nova:
    (COM_VIDEO, "") com o player na tela ou o vídeo tocando sozinho; (SEM_VIDEO, "") na aula sem vídeo (um documento
    ou um texto: a página pronta, sem player nenhum, nem depois de mais um tempo); (None, o porquê) quando não abriu.
    O que tocava antes é pausado, e o vídeo tocando depois do Enter é o da página nova. Na página de login (a sessão
    do site vencida), o robô entra com o acesso guardado (pedido do Rafael de 22/11/2026:
    DECISOES.md, Trabalho com o Claude) e escreve o endereço de novo; noutra página do site, de novo (_mesmo_site).
    """
    pausa = pausa or time.sleep
    entrar = entrar or _entrar
    logado, porque = False, SEM_O_ENDERECO
    for _ in range(VEZES_NA_BARRA):
        tipo, porque, tela = _abrir_pela_barra(d, endereco, pausa)
        if tipo:
            return tipo, porque
        if porque == SEM_A_EDICAO or porque.startswith(SEM_A_ESCRITA):
            # A barra não abriu a edição ou não mostrou o endereço: com a página de antes como estava, de novo.
            continue
        if porque != SEM_O_ENDERECO:
            return tipo, porque
        if campos_do_login(tela):
            if logado or not entrar(d, pausa)[0]:
                return None, SEM_O_LOGIN
            logado = True
        elif not _mesmo_site(texto_da_barra(tela), endereco):
            return None, SEM_O_ENDERECO
    return None, porque


# O "Próximo" do site troca a aula na mesma página, sem trocar o endereço da barra (o teste de 23/11/2026, às 10:49): a
# aula seguinte é conferida pelo nome no Próximo, que passa a ser o da aula depois dela (ou some na última), e o tipo
# dela pela página, como na aberta pela barra. Só a 1ª aula de cada curso abre pelo endereço; a aula N, pelos N - 1
# Próximos.
FIM_DO_CURSO = "o curso terminou"
SEM_A_SEGUINTE = "o Próximo não abriu a aula seguinte"
AVISO_EM_CIMA = "um aviso do Chrome ficou em cima do Próximo"
SEM_A_PAGINA = "a página da aula não está na tela"
VOLTOU = "a página voltou para uma aula de antes"
VEZES_SEM_O_PROXIMO = 3


def _tipo_da_pagina(d, tela, pausa):
    """
    O tipo da aula que o Próximo abriu (a página nova vem do alto): (COM_VIDEO, "") com o play na tela ou o vídeo
    tocando sozinho; (SEM_VIDEO, "") com a página pronta sem player nenhum, nem depois de mais um tempo; (None, o
    porquê). A página nunca é arrastada para baixo aqui: no alto dela, o Chrome toma o arrasto por "puxar para
    atualizar" e recarrega o endereço da barra, que é o da 1ª aula aberta pela barra (o teste de 23/11/2026, às 12:00).
    """
    for _ in range(ESPERA_DA_PAGINA // PASSO_DA_ESPERA):
        if botao_do_play(tela) or _tocando_ou_carregando(midia_do_chrome(d)):
            return COM_VIDEO, ""
        if pagina_da_aula_pronta(tela) and not tem_player(tela):
            break
        pausa(PASSO_DA_ESPERA)
        tela = d.dump_hierarchy()
    if pagina_da_aula_pronta(tela) and not tem_player(tela):
        pausa(ESPERA_SEM_O_PLAYER)
        tela = d.dump_hierarchy()
        if botao_do_play(tela) or _tocando_ou_carregando(midia_do_chrome(d)):
            return COM_VIDEO, ""
        if pagina_da_aula_pronta(tela) and not tem_player(tela):
            return SEM_VIDEO, ""
    return None, f"{SEM_O_PLAYER}; {descrever_a_midia(midia_do_chrome(d))}"


def proximo_na_tela(d, pausa):
    """
    (a tela, o centro do Próximo ou None). Sem ele, a tela é lida mais VEZES_SEM_O_PROXIMO vezes: a página que ainda
    carrega não pode passar por a última aula do curso.
    """
    tela = esperar_o_aviso_sair(d, pausa)
    for _ in range(VEZES_SEM_O_PROXIMO):
        if botao_do_proximo(tela):
            break
        pausa(PASSO_DA_ESPERA)
        tela = d.dump_hierarchy()
    return tela, botao_do_proximo(tela)


def passar_para_a_seguinte(d, pausa=None):
    """
    A aula seguinte pelo Próximo da aberta: (tipo, porque, nome da aula que abriu). Sem o Próximo na página da aula (a
    última do curso), (None, FIM_DO_CURSO, ""); sem a página, (None, SEM_A_PAGINA, ""). O Próximo que some depois do
    toque (a última aula abriu) é conferido em duas leituras seguidas.
    """
    pausa = pausa or time.sleep
    tela, ponto = proximo_na_tela(d, pausa)
    if not ponto:
        return None, FIM_DO_CURSO if pagina_da_aula_pronta(tela) else SEM_A_PAGINA, ""
    nome = nome_no_proximo(tela)
    if aviso_do_chrome(tela):
        # O aviso do Chrome (o do download, com o Abrir) pode estar em cima do Próximo: nada é tocado.
        return None, AVISO_EM_CIMA, nome
    d.click(*ponto)
    sem_o_proximo = 0
    for _ in range(ESPERA_DA_PAGINA // PASSO_DA_ESPERA):
        pausa(PASSO_DA_ESPERA)
        tela = d.dump_hierarchy()
        novo = nome_no_proximo(tela)
        if novo == nome or not pagina_da_aula_pronta(tela):
            sem_o_proximo = 0
            continue
        if not novo:
            sem_o_proximo += 1
            if sem_o_proximo < 2:
                continue
        tipo, porque = _tipo_da_pagina(d, tela, pausa)
        if tipo and nome_no_proximo(d.dump_hierarchy()) == nome:
            # A página que recarregou (ou voltou) mostra de novo o Próximo da aula de antes.
            return None, VOLTOU, nome
        return tipo, porque, nome
    return None, SEM_A_SEGUINTE, nome


# --- O mapa das aulas (P293 1), só no banco do servidor ---
# Os 7 cursos da turma do Rafael pela posição na lista de Turmas do site (Continuar aprendendo → Turmas): primeiro os
# dois de Shopee Vídeo, depois os outros na ordem da lista e, por último, o dos encontros ao vivo (P293 1). Os nomes dos
# cursos não vão ao repositório. De cada curso, o mapa guarda o endereço de uma aula (passo curso:primeira:N do
# explorar), por onde a noite chega ao curso, e a lista de todas as aulas, lida da aba Módulos (curso:lista:N), com o
# que a noite já guardou de cada uma e o check do Claude (pedidos do Rafael de 24/11/2026).
ORDEM_DOS_CURSOS = (4, 5, 1, 2, 6, 7, 3)
CHAVE_DO_MAPA = "curso_mapa"


def mapa_das_aulas():
    """
    {"cursos": {"posição": {"aulas": [{"endereco"}], "lista": [{"modulo", "nome", "segundos", "gravada_em"?,
    "sem_video"?, "vista_em"?}], "lista_em"}}} do banco: a aula N é a lista[N - 1]; gravada_em, guardada pela noite
    (sem_video, a aula sem vídeo); vista_em, conferida pelo Claude (o check).
    """
    mapa = db.ler_config(CHAVE_DO_MAPA, {}) or {}
    mapa.setdefault("cursos", {})
    return mapa


def _mudar_o_curso(posicao, mudar):
    """Muda o curso dessa posição no mapa, numa transação só; devolve o que mudar(curso) devolver."""
    def mudar_o_mapa(mapa):
        return mudar(mapa.setdefault("cursos", {}).setdefault(str(int(posicao)), {"aulas": []}))
    return db.atualizar_config(CHAVE_DO_MAPA, mudar_o_mapa)


def guardar_a_primeira_aula(posicao, endereco):
    """
    O endereço de uma aula do curso nessa posição da lista de Turmas, guardado pelo Claude (passo curso:primeira:N):
    é por ele que a noite chega ao curso (o site abre nele a aula em que parou), e dali a aula da vez vem pela lista
    (abrir_pela_lista). Troca o que estava. True se guardou.
    """
    if int(posicao) not in ORDEM_DOS_CURSOS or not CAMINHO_DA_AULA.fullmatch(endereco.removeprefix("https://")):
        return False

    def mudar(curso):
        curso["aulas"] = [{"endereco": endereco}]
        return True
    return bool(_mudar_o_curso(posicao, mudar))


def proxima_aula(mapa=None, pular=()):
    """
    A aula da vez, na ordem dos cursos e na ordem da lista de cada um (pedido do Rafael de 24/11/2026: aula por aula,
    da 1ª à última, curso por curso): (posição, número) da 1ª aula da lista que a noite ainda não guardou nem o Claude
    conferiu. A guardada espera a conferência do Claude, que a marca como vista (o check) ou manda refazer (inteira, do
    início: P295 1). As de `pular` ((posição, número), as que não foram guardadas nesta noite) ficam para a noite
    seguinte: nenhuma aula é pulada. A noite para no curso da vez que ainda não tem a lista (curso:lista:N), sem passar
    ao seguinte (curso por curso, na ordem). None sem nada a gravar.
    """
    mapa = mapa or mapa_das_aulas()
    for posicao in ORDEM_DOS_CURSOS:
        lista = lista_do_curso(posicao, mapa)
        if not lista:
            return None
        for numero, aula in enumerate(lista, 1):
            if not aula.get("gravada_em") and not aula.get("vista_em") and (posicao, numero) not in pular:
                return posicao, numero
    return None


def curso_sem_a_lista(mapa=None):
    """O curso em que a noite para por não ter a lista das aulas (os de antes dele todos gravados), ou None."""
    mapa = mapa or mapa_das_aulas()
    for posicao in ORDEM_DOS_CURSOS:
        lista = lista_do_curso(posicao, mapa)
        if not lista:
            return posicao
        if any(not aula.get("gravada_em") and not aula.get("vista_em") for aula in lista):
            return None
    return None


def _a_aula(curso, numero, mudar):
    """Muda a aula `numero` da lista do curso (a lista[numero - 1]), se ela está na lista."""
    lista = curso.get("lista") or []
    if 1 <= int(numero) <= len(lista):
        mudar(lista[int(numero) - 1])


def anotar_a_aula_gravada(posicao, numero, agora=None, sem_video=False):
    """
    A aula da lista do curso guardada inteira (gravada ou, sem vídeo, com a página e o documento): espera a conferência
    do Claude, e a noite segue para a seguinte.
    """
    momento = _texto(_agora(agora))

    def marcar(aula):
        aula["gravada_em"] = momento
        if sem_video:
            aula["sem_video"] = momento
    _mudar_o_curso(posicao, lambda curso: _a_aula(curso, numero, marcar))


def desmarcar_a_aula(posicao, numero):
    """A aula gravada que não serviu (preta ou muda) volta a ficar por gravar."""
    _mudar_o_curso(posicao, lambda curso: _a_aula(curso, numero, lambda aula: aula.pop("gravada_em", None)))


def conferir_as_aulas(posicao, numeros, vistas=True, agora=None):
    """
    A conferência do Claude (pedidos do Rafael de 24/11/2026: o check só depois de ver que a aula certa foi vista
    inteira e que algo foi aprendido): vistas=True marca as aulas como vistas (o check); vistas=False manda refazer
    (a noite grava de novo, inteira, do início). Devolve quantas mudaram.
    """
    momento, numeros = _texto(_agora(agora)), {int(numero) for numero in numeros}

    def mudar(curso):
        mudadas = 0
        for numero, aula in enumerate(curso.get("lista") or [], 1):
            if numero not in numeros:
                continue
            if vistas:
                aula["vista_em"] = momento
            else:
                for chave in ("gravada_em", "sem_video", "vista_em"):
                    aula.pop(chave, None)
            mudadas += 1
        return mudadas
    return _mudar_o_curso(posicao, mudar) or 0


def numeros_das_aulas(texto):
    """
    As aulas da conferência em números, por curso: "4:15,16;5:2-35" dá {4: {15, 16}, 5: {2, ..., 35}}. ValueError no
    texto fora desse formato (só números vão ao log público do cursos_robo.yml).
    """
    cursos = {}
    for parte in filter(None, (pedaco.strip() for pedaco in (texto or "").split(";"))):
        achado = re.fullmatch(r"(\d+):([\d,\-\s]+)", parte)
        if not achado or int(achado.group(1)) not in ORDEM_DOS_CURSOS:
            raise ValueError(parte)
        numeros = cursos.setdefault(int(achado.group(1)), set())
        for faixa in filter(None, (pedaco.strip() for pedaco in achado.group(2).split(","))):
            ponta = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", faixa)
            if not ponta:
                raise ValueError(faixa)
            inicio, fim = int(ponta.group(1)), int(ponta.group(2) or ponta.group(1))
            if inicio < 1 or fim < inicio:
                raise ValueError(faixa)
            numeros.update(range(inicio, fim + 1))
    return cursos


def resumo_do_mapa(mapa=None):
    """O mapa só em números, curso a curso na ordem: as aulas da lista, as guardadas pela noite e as vistas (check)."""
    mapa = mapa or mapa_das_aulas()
    partes = []
    for posicao in ORDEM_DOS_CURSOS:
        lista = lista_do_curso(posicao, mapa)
        if not lista:
            partes.append(f"curso {posicao}: sem a lista das aulas")
            continue
        vistas = sum(1 for aula in lista if aula.get("vista_em"))
        guardadas = sum(1 for aula in lista if aula.get("gravada_em") and not aula.get("vista_em"))
        partes.append(f"curso {posicao}: {vistas} de {len(lista)} aula(s) vista(s), "
                      f"{guardadas} esperando a conferência")
    return "; ".join(partes)


# --- A lista das aulas, pela aba Módulos (pedido do Rafael de 24/11/2026, às 00:17) ---
# O endereço guardado de cada curso abre a aula em que o site parou (a 1ª ainda não vista), e não a 1ª do curso: na
# noite de 24/11/2026, o curso 4 abriu na 15ª aula (as de antes o Rafael viu à mão) e o 5 na 2ª (a 1ª, o teste de dia
# viu). A lista inteira, na ordem, vem da aba Módulos: cada módulo é um botão ("N% Nome do módulo", às vezes sem o
# andamento), e o aberto mostra embaixo uma linha por aula, mais à direita ("Nome 7:28"; a aula sem vídeo pode vir sem a
# duração). O Claude a lê de dia, com o celular mudo, pelo passo curso:lista:N do explorar, e ela fica no mapa (só no
# banco do servidor), com os módulos na ordem e as aulas na ordem de cada um: é a lista das aulas com o check de cada
# uma que o Rafael pediu. Só os botões dos módulos são tocados, e a página só rola para baixo (o dedo para cima): no
# alto dela, o arrasto para baixo recarregaria a página.
ID_DA_LISTA = "-content-modules"
# O módulo é o botão do acordeão, com o identificador que começa assim, e a aula, o botão sem identificador. O nome do
# módulo pode vir sem o andamento na frente: o 1º módulo do curso 5 (em 24/11/2026) vem sem o "0%", e só o botão com
# o andamento contava como módulo: ele nunca era aberto, e a aula dele ficava fora da lista.
ID_DO_MODULO = "radix-"
MODULO_DA_LISTA = re.compile(r"(?:\d{1,3}%\s+)?(?P<nome>.*\S)")
# O botão baixo demais está cortado pela beira da tela (ou embaixo da barra do Próximo): não é tocado.
ALTURA_DO_BOTAO = 60
# Embaixo do módulo aberto vem a 1ª aula dele: sem esse espaço à vista, a lista rola antes de saber se ele está aberto.
ESPACO_DA_AULA = 160
# O curso mais longo da turma tem centenas de aulas (402 no curso 7, pelo progresso da página em 24/11/2026): a lista
# inteira leva centenas de leituras da tela, entre rolagens, toques nos módulos e voltas da caixa (cerca de 410 num
# curso de mentira do mesmo tamanho).
VOLTAS_DA_LISTA = 1000
ESPERA_DO_MODULO = 1.5
# A duração da linha da aula só aparece com a linha dentro da caixa da lista: o site a põe quando a linha passa pela
# parte da caixa que se vê (às vezes um instante depois), e ela fica com o módulo aberto. A linha fora da caixa, por
# cima ou por baixo, vem sem a duração que tem (em 24/11/2026, aberto um módulo do curso 4, o site rolou a caixa até a
# aula aberta, e a 1ª aula do módulo, um vídeo, ficou por cima da caixa sem passar por dentro dela, e a lista a
# guardou sem a duração). Só a linha lida dentro da caixa diz que a aula não tem duração: a tela com uma dessas é lida
# de novo, com essas esperas (s), antes de a leitura seguir; nas primeiras aulas de um módulo que acabou de abrir, a
# duração demorou mais de 2 s (a 3ª leitura do mesmo dia, nos cursos 1, 3 e 4). A linha sem a duração por cima da
# caixa, que não passou por dentro dela, faz a caixa voltar, por dentro, até ela; sem avanço em VOLTAS_SEM_AVANCO
# voltas seguidas, a aula fica sem a duração conferida (sem_conferir), e o log do explorar diz quantas.
ESPERAS_DA_DURACAO = (1.0, 2.0, 3.0, 4.0)
RELEITURAS_DA_DURACAO = len(ESPERAS_DA_DURACAO)
VOLTAS_SEM_AVANCO = 3
POR_CIMA, POR_BAIXO = "por cima", "por baixo"
SEM_A_LISTA = "a aba Módulos não apareceu na tela"
LISTA_SEM_O_COMECO = "o começo da lista ficou fora da tela"
LISTA_PELA_METADE = "a lista das aulas não chegou ao fim"
MODULO_SEM_TOQUE = "o botão de um módulo ficou fora do alcance"
# A lista das aulas rola por dentro de uma caixa só dela (a altura tem limite). Na leitura da tela, as linhas que
# rolaram para fora da caixa continuam lá, com o lugar que teriam, por cima das abas e do player (o curso 4, em
# 24/11/2026): só a linha inteira dentro da caixa é tocada. Aberto um módulo, o site rola a caixa sozinho até a aula
# aberta na página, e o botão dele e as primeiras aulas saem por cima: a lista lia as aulas seguintes como do módulo de
# antes, sem as primeiras. A caixa volta arrastada para baixo por dentro dela (o dedo para baixo sem sair da caixa), só
# enquanto há linha escondida por cima dela, e a página não se mexe.
SUBIDA_NA_LISTA = 400
SUBIDAS_DA_LISTA = 200
MODULO_FORA_DA_TELA = "o módulo aberto saiu da lista e não voltou"


# O alto da página da aula diz o andamento do curso ("12% concluído · 3/28 aulas"): o total confere a lista lida.
TOTAL_DO_CURSO = re.compile(r"concluído\s*·\s*\d+\s*/\s*(?P<total>\d+)\s+aulas")


def total_de_aulas(xml):
    """O total de aulas do curso, pelo andamento no alto da página da aula; None sem ele na tela."""
    for no in _nos(xml):
        achado = TOTAL_DO_CURSO.search(" ".join(no["texto"].split()))
        if achado:
            return int(achado["total"])
    return None


def itens_da_lista(xml):
    """
    A aba Módulos à vista: (a caixa da lista na tela, [{"tipo": "módulo" ou "aula", "nome", "segundos", "caixa"}] de
    cima para baixo); None sem ela na tela. A aula sem a duração na linha tem segundos None.
    """
    try:
        raiz = ET.fromstring(xml or "")
    except ET.ParseError:
        return None
    lista = next((no for no in raiz.iter("node") if no.get("resource-id", "").endswith(ID_DA_LISTA)), None)
    caixa = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", lista.get("bounds", "")) if lista is not None \
        else None
    if not caixa:
        return None
    pais = {filho: pai for pai in lista.iter("node") for filho in pai}
    itens = []
    for elemento in lista.iter("node"):
        no = _no(elemento)
        texto = " ".join(no["texto"].split()) if no else ""
        if not texto or not no["clicavel"] or no["classe"] != "Button" or texto.startswith(ROTULO_DO_PROXIMO):
            continue
        if no["id"].startswith(ID_DO_MODULO):
            itens.append({"tipo": "módulo", "nome": MODULO_DA_LISTA.fullmatch(texto)["nome"], "segundos": None,
                          "caixa": no["caixa"]})
        elif not no["id"]:
            linha = LINHA_DA_AULA.fullmatch(texto)
            itens.append({"tipo": "aula", "nome": linha["nome"] if linha else texto,
                          "segundos": segundos_do_tempo(linha["tempo"]) if linha else None, "caixa": no["caixa"],
                          "aula": _numero_da_aula(elemento, pais)})
    return tuple(map(int, caixa.groups())), sorted(itens, key=lambda item: item["caixa"][1])


def _numero_da_aula(elemento, pais):
    """
    O número da aula no site, o do bloco em volta da linha dela na lista (o id só de algarismos, como "4981"); "" sem
    ele. É a identidade da linha em toda leitura, também quando o texto dela muda (a duração que aparece depois).
    """
    while elemento is not None:
        ident = elemento.get("resource-id", "").split(":id/")[-1]
        if ident.isdigit():
            return ident
        elemento = pais.get(elemento)
    return ""


def _tocavel(tela, caixa):
    """O botão está inteiro na tela, acima da barra do Próximo e longe da bolha do chat e da barra do Chrome?"""
    return (caixa[3] - caixa[1] >= ALTURA_DO_BOTAO and caixa[3] < _topo_do_proximo(tela)
            and _livre_para_tocar(tela, _centro(caixa)))


def _na_janela(janela, caixa):
    """A linha está inteira na parte da lista que se vê (janela: a caixa da lista na tela)?"""
    return janela[1] <= caixa[1] and caixa[3] <= janela[3]


def _escondida_por_cima(itens, janela):
    """Alguma linha rolou para fora da caixa da lista, por cima? Só então a caixa volta sem mexer na página."""
    return any(item["caixa"][1] < janela[1] for item in itens)


def _fora_da_caixa(itens, janela):
    """
    As linhas de aula à vista fora da caixa da lista (janela: a parte dela que se vê), pela chave de cada uma (o número
    da aula no site ou, sem ele, o nome, como em _chave_da_aula): POR_CIMA ou POR_BAIXO dela.
    """
    return {(item.get("aula") or item["nome"]): POR_CIMA if item["caixa"][1] < janela[1] else POR_BAIXO
            for item in itens if item["tipo"] == "aula" and not _na_janela(janela, item["caixa"])}


def _subir_na_lista(d, janela):
    """A lista um pedaço para cima: o dedo para baixo por dentro da caixa dela, longe do Próximo e da bolha do chat."""
    inicio = janela[1] + 60
    fim = max(inicio + 100, min(inicio + SUBIDA_NA_LISTA, janela[3] - 20, BOLHA_DO_CHAT[1] - 20))
    d.swipe(540, inicio, 540, fim, 0.4)


def _chave_da_aula(aula):
    """A identidade da linha lida, (nome, segundos[, número]): o número da aula no site, ou o nome sem ele."""
    return aula[2] if len(aula) > 2 and aula[2] else aula[0]


def _juntar_as_aulas(lidas, vistas):
    """
    As aulas do módulo vistas nesta tela depois das já lidas, sem repetir o pedaço que as duas leituras mostram,
    reconhecido pelo número da aula no site ou, sem ele, pelo nome: logo depois do toque no módulo, a linha da aula pode
    vir ainda sem a duração, que aparece na leitura seguinte (o curso 1, em 24/11/2026, ficou com 13 aulas repetidas).
    A linha nova vale quando traz a duração: o nome que termina como uma hora ("Mentoria 20:00"), sem a duração, é
    lido como "Mentoria" e 20 min. Sem ela, fica a de antes. Com a caixa da lista voltando atrás de uma aula sem a
    duração, a tela mostra um pedaço já lido (do meio, ou com linhas de antes das lidas): ele só traz a duração que
    faltava.
    """
    chaves, novas = [_chave_da_aula(aula) for aula in lidas], [_chave_da_aula(aula) for aula in vistas]

    def com_a_duracao(velhas, iguais):
        return [vista if vista[1] is not None else velha[:2] + vista[2:] for velha, vista in zip(velhas, iguais)]

    for tamanho in range(min(len(lidas), len(vistas)), 0, -1):
        if chaves[-tamanho:] == novas[:tamanho]:
            comeco = len(lidas) - tamanho
            return lidas[:comeco] + com_a_duracao(lidas[comeco:], vistas[:tamanho]) + vistas[tamanho:]
    for comeco in range(len(lidas) - len(vistas) + 1):
        if chaves[comeco:comeco + len(vistas)] == novas:
            fim = comeco + len(vistas)
            return lidas[:comeco] + com_a_duracao(lidas[comeco:fim], vistas) + lidas[fim:]
    for tamanho in range(min(len(lidas), len(vistas)), 0, -1):
        if novas[-tamanho:] == chaves[:tamanho]:
            antes = len(vistas) - tamanho
            return vistas[:antes] + com_a_duracao(lidas[:tamanho], vistas[antes:]) + lidas[tamanho:]
    return lidas + vistas


def _uma_olhada_na_lista(itens, modulos):
    """
    Uma tela da lista: as aulas do módulo que está sendo lido (o último de `modulos`) e o primeiro módulo novo depois
    dele, com o item logo abaixo deste. As aulas no alto da tela, antes de qualquer botão, são do módulo lido, se o
    botão dele já saiu da tela; as de um módulo já lido ficam de fora.
    """
    lido = modulos[-1] if modulos else None
    nomes = {modulo["nome"] for modulo in modulos}
    botao_do_lido = any(item["tipo"] == "módulo" and lido and item["nome"] == lido["nome"] for item in itens)
    dono, vistas = (lido if lido and not botao_do_lido else None), []
    for numero, item in enumerate(itens):
        if item["tipo"] == "aula":
            if dono is lido and lido is not None:
                vistas.append((item["nome"], item["segundos"], item.get("aula", "")))
            continue
        if lido and item["nome"] == lido["nome"]:
            dono = lido
        elif item["nome"] in nomes:
            dono = None
        else:
            abaixo = itens[numero + 1] if numero + 1 < len(itens) else None
            return vistas, item, abaixo
    return vistas, None, None


def _aula_da_lista(modulo, aula, conferida=True):
    """
    A aula lida (nome, segundos[, número]) como linha da lista: o número da aula no site só quando a linha o traz; a
    aula sem a duração cuja linha não foi lida dentro da caixa, marcada (sem_conferir).
    """
    entrada = {"modulo": modulo, "nome": aula[0], "segundos": aula[1]}
    if len(aula) > 2 and aula[2]:
        entrada["aula"] = aula[2]
    if not conferida:
        entrada["sem_conferir"] = True
    return entrada


def ler_a_lista(d, pausa=None, ao_comecar=None):
    """
    A lista das aulas do curso aberto no Chrome, pela aba Módulos: ([{"modulo", "nome", "segundos"}], "") com os
    módulos na ordem e as aulas na ordem de cada um, ou (None, o porquê). Cada módulo fechado é aberto pelo botão dele
    (um toque só: o que não mostra aula nenhuma fica vazio), e a página rola só para baixo, até o fim dela; só a caixa
    da lista volta para cima, por dentro, quando o site a rola sozinho (SUBIDA_NA_LISTA) e atrás da aula por cima dela
    sem a duração (RELEITURAS_DA_DURACAO): a falta da duração só vale lida com a linha dentro da caixa, e a aula sem ela
    cuja linha não passou por dentro vem marcada (sem_conferir). ao_comecar é chamado uma vez, com o começo da lista na
    tela (o explorar guarda essa tela para o Claude).
    """
    pausa = pausa or time.sleep
    modulos, tocados, antes, sem_a_lista, aba_tocada = [], set(), None, 0, False
    # esperado: o módulo tocado por último, até o botão dele voltar à leitura da tela.
    esperado, subidas = None, 0
    # relidas: as aulas lidas sem a duração dentro da caixa, que já tiveram as releituras da tela (a aula sem vídeo não
    # tem duração nenhuma); desistidas: as por cima da caixa que as voltas dela não trouxeram para dentro.
    relidas, releituras, desistidas = set(), 0, set()
    # faltavam: as aulas por cima da caixa na última volta dela; sem_avanco: as voltas seguidas sem trazer nenhuma.
    faltavam, sem_avanco = None, 0
    for _ in range(VOLTAS_DA_LISTA):
        tela = _fechar_a_folha_do_chrome(d, pausa)
        achado = itens_da_lista(tela)
        if not achado or not achado[1]:
            if not achado and not aba_tocada and _tocar_na_aba_modulos(d, tela, pausa):
                aba_tocada = True
                continue
            sem_a_lista += 1
            if sem_a_lista > TELAS_DA_AULA:
                return None, SEM_A_LISTA
            rolar_a_pagina(d)
            pausa(ESPERA_DA_ROLAGEM)
            continue
        caixa, itens = achado
        if (not modulos or esperado) and subidas < SUBIDAS_DA_LISTA and _escondida_por_cima(itens, caixa) and not any(
                item["tipo"] == "módulo" and item["nome"] == esperado for item in itens):
            # O começo da lista, ou o botão do módulo que acabou de abrir, rolou por cima da caixa dela: o site rola a
            # caixa sozinho até a aula aberta na página. As linhas à vista não entram antes de o botão voltar.
            subidas += 1
            _subir_na_lista(d, caixa)
            pausa(ESPERA_DA_ROLAGEM)
            antes = None
            continue
        if esperado and not any(item["tipo"] == "módulo" and item["nome"] == esperado for item in itens):
            return None, MODULO_FORA_DA_TELA
        esperado = None
        topo = next((no["caixa"][1] for no in _nos(tela) if no["classe"] == "WebView"), 0)
        if not modulos and (itens[0]["tipo"] != "módulo" or caixa[1] <= topo):
            # A lista que já começa cortada no alto da página: o começo dela passou, e a página não volta para cima.
            return None, LISTA_SEM_O_COMECO
        if ao_comecar:
            ao_comecar()
            ao_comecar = None
        vistas, novo, abaixo = _uma_olhada_na_lista(itens, modulos)
        if modulos:
            modulos[-1]["aulas"] = _juntar_as_aulas(modulos[-1]["aulas"], vistas)
            juntas = {_chave_da_aula(aula): aula[1] for aula in modulos[-1]["aulas"]}
            fora = _fora_da_caixa(itens, caixa)
            faltam = {_chave_da_aula(aula) for aula in vistas if juntas.get(_chave_da_aula(aula)) is None}
            sem_duracao = faltam - set(fora)
            if sem_duracao - relidas and releituras < RELEITURAS_DA_DURACAO:
                # A linha que acabou de entrar na caixa pode vir ainda sem a duração, que o site põe uns segundos
                # depois (sem ela, a noite não confere se gravou o vídeo inteiro): a mesma tela é lida de novo antes
                # de seguir. A linha fora da caixa vem sem ela de todo jeito, e ler de novo não muda nada.
                pausa(ESPERAS_DA_DURACAO[releituras])
                releituras += 1
                continue
            relidas |= sem_duracao
            por_cima = {chave for chave in faltam if fora.get(chave) == POR_CIMA} - relidas - desistidas
            if por_cima:
                # A linha sem a duração por cima da caixa, sem ter passado por dentro dela (o site rola a caixa
                # sozinho até a aula aberta, e a rolagem por dentro dela anda mais que o dedo): a caixa volta, por
                # dentro, até ela entrar, e a duração é lida.
                sem_avanco = 0 if faltavam is None or faltavam - por_cima else sem_avanco + 1
                if sem_avanco < VOLTAS_SEM_AVANCO:
                    faltavam, releituras, antes = por_cima, 0, None
                    _subir_na_lista(d, caixa)
                    pausa(ESPERA_DA_ROLAGEM)
                    continue
                desistidas |= por_cima
            faltavam, sem_avanco = None, 0
        releituras = 0
        if (novo and novo["caixa"][1] < caixa[1] and novo["nome"] not in tocados
                and not (abaixo and abaixo["tipo"] == "aula") and subidas < SUBIDAS_DA_LISTA):
            # O botão do módulo seguinte passou por cima da caixa da lista: a rolagem por dentro dela anda mais que o
            # dedo, e o que estava meio escondido embaixo da caixa pula por cima dela (o curso 7, em 24/11/2026). A
            # caixa volta um pedaço, por dentro, até ele aparecer inteiro nela.
            subidas += 1
            _subir_na_lista(d, caixa)
            pausa(ESPERA_DA_ROLAGEM)
            antes = None
            continue
        if novo:
            if abaixo and abaixo["tipo"] == "aula":
                # Aberto: as aulas dele estão logo embaixo (a próxima olhada, na mesma tela, as lê).
                modulos.append({"nome": novo["nome"], "aulas": []})
                continue
            espaco = abaixo is not None or novo["caixa"][3] + ESPACO_DA_AULA < _topo_do_proximo(tela)
            if espaco and novo["nome"] in tocados:
                # Tocado e sem aula nenhuma embaixo: um módulo vazio.
                modulos.append({"nome": novo["nome"], "aulas": []})
                continue
            if espaco and _tocavel(tela, novo["caixa"]) and _na_janela(caixa, novo["caixa"]):
                d.click(*_centro(novo["caixa"]))
                tocados.add(novo["nome"])
                esperado, subidas = novo["nome"], 0
                pausa(ESPERA_DO_MODULO)
                continue
        marca = [(item["tipo"], item["nome"], item["caixa"]) for item in itens]
        if marca == antes:
            # A página não rolou mais: o fim dela.
            if novo and novo["nome"] in tocados:
                # Tocado no fim da página e ainda sem aula embaixo: um módulo vazio.
                modulos.append({"nome": novo["nome"], "aulas": []})
                antes = None
                continue
            if novo and _tocavel(tela, novo["caixa"]) and _na_janela(caixa, novo["caixa"]):
                # O último módulo, no fim da página, sem lugar embaixo para as aulas (o curso 6, em 24/11/2026): sem
                # aula à vista, ele está fechado (aberto, as aulas dele alongariam a página) e é tocado uma vez.
                d.click(*_centro(novo["caixa"]))
                tocados.add(novo["nome"])
                esperado, subidas = novo["nome"], 0
                pausa(ESPERA_DO_MODULO)
                antes = None
                continue
            if novo:
                return None, MODULO_SEM_TOQUE
            aulas = [_aula_da_lista(modulo["nome"], aula, aula[1] is not None or _chave_da_aula(aula) in relidas)
                     for modulo in modulos for aula in modulo["aulas"]]
            return (aulas, "") if aulas else (None, LISTA_PELA_METADE)
        antes = marca
        rolar_a_pagina(d)
        pausa(ESPERA_DA_ROLAGEM)
    return None, LISTA_PELA_METADE


def _tocar_na_aba_modulos(d, tela, pausa):
    """
    A aba Módulos à vista, com lugar embaixo dela, e a lista nada: outra aba está aberta (o site lembra a última
    escolhida; na noite de 24/11/2026, a de Comentários). A aba Módulos é tocada. True se tocou.
    """
    aba = next((no for no in _nos(tela) if no["id"].endswith(ID_DAS_ABAS) and no["clicavel"]), None)
    if not aba or not _tocavel(tela, aba["caixa"]) or aba["caixa"][3] + ESPACO_DA_AULA >= _topo_do_proximo(tela):
        return False
    d.click(*_centro(aba["caixa"]))
    pausa(ESPERA_DO_MODULO)
    return True


MARCAS_DA_AULA = ("gravada_em", "sem_video", "vista_em")


def guardar_a_lista(posicao, lista, agora=None):
    """
    A lista das aulas do curso dessa posição, lida da aba Módulos, no mapa (só no banco do servidor). As marcas de cada
    aula (gravada, guardada sem vídeo, conferida pelo Claude) passam para a lista nova pelo módulo e pelo nome: ler a
    lista de novo não faz a noite gravar outra vez o que já foi gravado. A aula lida sem a duração fica com a da leitura
    anterior da mesma aula, pelo número dela no site (sem ele, pelo módulo e pelo nome): a duração só aparece na linha
    da aula com vídeo, e a leitura que não a viu (a linha fora da caixa da lista, ou a duração que demorou a aparecer)
    não diz que o vídeo saiu. O número de aulas que ficaram com a duração de antes, que o log do explorar mostra.
    """
    momento = _texto(_agora(agora))

    def mudar(curso):
        antigas, por_numero, de_antes = {}, {}, 0
        for aula in curso.get("lista") or []:
            antigas.setdefault((aula.get("modulo"), aula.get("nome")), []).append(aula)
            if aula.get("aula"):
                por_numero[aula["aula"]] = aula
        nova = []
        for aula in lista:
            entrada = {"modulo": aula["modulo"], "nome": aula["nome"], "segundos": aula["segundos"]}
            if aula.get("aula"):
                entrada["aula"] = aula["aula"]
            iguais = antigas.get((aula["modulo"], aula["nome"]))
            velha = iguais.pop(0) if iguais else None
            if velha:
                entrada.update({chave: velha[chave] for chave in MARCAS_DA_AULA if velha.get(chave)})
            anterior = por_numero.get(aula["aula"]) if aula.get("aula") else velha
            if entrada["segundos"] is None and anterior and anterior.get("segundos"):
                entrada["segundos"] = anterior["segundos"]
                de_antes += 1
            nova.append(entrada)
        curso["lista"] = nova
        curso["lista_em"] = momento
        curso.pop("lista_sem_bater", None)
        return de_antes
    return _mudar_o_curso(posicao, mudar) or 0


def guardar_a_lista_sem_bater(posicao, lista, total, agora=None):
    """
    A lista lida que não bate com o total do site fica à parte no mapa (só no banco), sem valer para a noite: vai ao
    Claude no pacote das aulas, para ele achar a linha que sobra ou falta (a do curso 7, em 24/11/2026, veio com 2
    aulas a mais). A lista que bate, guardada depois, a tira.
    """
    momento = _texto(_agora(agora))

    def mudar(curso):
        curso["lista_sem_bater"] = {"em": momento, "total": total, "lista": lista}
    _mudar_o_curso(posicao, mudar)


def descrever_a_lista(posicao, lista):
    """A lista lida, só em números (o log do explorar é público)."""
    modulos = len({aula["modulo"] for aula in lista})
    com = [aula["segundos"] for aula in lista if aula["segundos"]]
    sem_conferir = sum(1 for aula in lista if aula.get("sem_conferir"))
    return (f"lista do curso {posicao}: {modulos} módulo(s) com aula, {len(lista)} aula(s), {len(com)} com a duração "
            f"({sum(com) // 60} min de vídeo) e {len(lista) - len(com)} sem"
            + (f" ({sem_conferir} sem a linha lida dentro da caixa)" if sem_conferir else ""))


# A aula aberta pelo toque no nome dela na lista (o caminho que a noite vai seguir: pedido do Rafael de 24/11/2026, de
# ver as aulas em ordem, da 1ª à última de cada curso). O curso abre pelo endereço guardado (a aula em que o site
# parou), a página rola para baixo até a linha da aula, o módulo dela é aberto pelo botão, e a linha é tocada; a aula
# aberta é conferida pelo Próximo, que tem de mostrar a aula seguinte da lista (nenhuma, na última do curso).
SEM_A_AULA_NA_LISTA = "a aula não apareceu na lista"
FORA_DA_LISTA = "a aula não está na lista do curso"
OUTRA_AULA = "a página não é a da aula tocada na lista"
OUTRA_PAGINA = "a página não é a da aula da vez"


def lista_do_curso(posicao, mapa=None):
    """A lista das aulas do curso dessa posição, lida da aba Módulos ([] antes do curso:lista:N)."""
    return ((mapa or mapa_das_aulas())["cursos"].get(str(posicao)) or {}).get("lista") or []


def endereco_do_curso(posicao, mapa=None):
    """O endereço guardado do curso (curso:primeira:N), que abre a aula em que o site parou; "" sem ele."""
    aulas = ((mapa or mapa_das_aulas())["cursos"].get(str(posicao)) or {}).get("aulas") or []
    return aulas[0].get("endereco", "") if aulas else ""


def _linha_na_tela(itens, alvo, dentro):
    """
    Uma tela da lista: (a linha da aula alvo, se à vista; o botão do módulo dela, se à vista e fechado; se a tela
    termina dentro do módulo dela). As linhas no alto da tela, antes de qualquer botão, são do módulo em que a tela de
    antes terminou (dentro).
    """
    linha, fechado = None, None
    for numero, item in enumerate(itens):
        if item["tipo"] == "módulo":
            dentro = item["nome"] == alvo["modulo"]
            abaixo = itens[numero + 1] if numero + 1 < len(itens) else None
            if dentro and not (abaixo and abaixo["tipo"] == "aula"):
                fechado = item
        elif linha is None and (dentro or _pelo_numero(item, alvo)) and _a_mesma_aula(item, alvo):
            # Com o número da aula no site, a linha é dela também sem o botão do módulo à vista (o site rola a lista
            # sozinho quando o módulo abre, e o botão sai por cima).
            linha = item
    return linha, fechado, dentro


def _pelo_numero(item, alvo):
    """A linha da tela e a aula da lista trazem o número da aula no site (a identidade dela no curso)?"""
    return bool(item.get("aula") and alvo.get("aula"))


def _onde_esta_a_aula(itens, lista, numero, linha, janela):
    """
    Para que lado da caixa da lista está a aula `numero`: "acima", "abaixo" ou "" (à vista, ou sem como saber). A linha
    lida fora da caixa diz o lado; sem ela, as aulas à vista dizem, pela ordem da lista (pelo número da aula no site).
    """
    if linha:
        return "acima" if linha["caixa"][1] < janela[1] else "abaixo" if linha["caixa"][3] > janela[3] else ""
    lugares = {aula["aula"]: indice for indice, aula in enumerate(lista, 1) if aula.get("aula")}
    vistas = [lugares[item["aula"]] for item in itens if item["tipo"] == "aula" and item.get("aula") in lugares]
    if vistas and min(vistas) > numero:
        return "acima"
    if vistas and max(vistas) < numero:
        return "abaixo"
    return ""


def _a_mesma_aula(item, alvo):
    """A linha da tela é a aula da lista? Pelo número da aula no site, quando as duas o têm; senão, pelo nome."""
    if item.get("aula") and alvo.get("aula"):
        return item["aula"] == alvo["aula"]
    return item["nome"] == alvo["nome"]


def abrir_pela_lista(d, posicao, numero, pausa=None, no_curso=False, vigiar=None):
    """
    A aula `numero` da lista do curso aberta pelo toque no nome dela na aba Módulos: (True, "") com a aula conferida
    pelo Próximo, ou (False, o porquê). O curso abre antes pelo endereço guardado (a aula em que o site parou); com
    no_curso=True (a página já é de uma aula do mesmo curso), a lista é procurada antes na página como está e, sem a
    aula nela, pelo endereço. A página só rola para baixo, e o botão do módulo dela é tocado uma vez, se fechado.
    vigiar(), a cada tela da lista, renova o sinal ao robô e diz o porquê de parar ("" para seguir): a lista longa
    leva minutos, e o robô que pede o celular o tem logo.
    """
    pausa = pausa or time.sleep
    vigiar = vigiar or (lambda: "")
    lista = lista_do_curso(posicao)
    if not 1 <= int(numero) <= len(lista):
        return False, FORA_DA_LISTA
    if no_curso and chrome_em_pe(d, pausa) == CHROME_DEITADO:
        return False, CHROME_DEITADO
    ok, porque = False, SEM_A_AULA_NA_LISTA
    pausar_o_que_toca(d, pausa)
    for pelo_endereco in ((False, True) if no_curso else (True,)):
        if pelo_endereco:
            tipo, porque = ir_para_o_endereco(d, endereco_do_curso(posicao), pausa)
            if not tipo:
                return False, f"a aula não abriu ({porque})"
            pausar_o_que_toca(d, pausa)
        ok, porque = _tocar_na_lista(d, lista, int(numero), pausa, vigiar)
        if ok or porque not in (SEM_A_AULA_NA_LISTA, SEM_A_LISTA):
            break
    return ok, porque


def _tocar_na_lista(d, lista, numero, pausa, vigiar):
    """A linha da aula `numero` achada na aba Módulos, rolando a página para baixo, e tocada. (ok, porque)."""
    alvo = lista[numero - 1]
    dentro, tocado, antes, sem_a_lista, aba_tocada, subidas = False, False, None, 0, False, 0
    for _ in range(VOLTAS_DA_LISTA):
        parar = vigiar()
        if parar:
            return False, parar
        tela = _fechar_a_folha_do_chrome(d, pausa)
        achado = itens_da_lista(tela)
        if not achado or not achado[1]:
            if not achado and not aba_tocada and _tocar_na_aba_modulos(d, tela, pausa):
                aba_tocada = True
                continue
            sem_a_lista += 1
            if sem_a_lista > TELAS_DA_AULA:
                return False, SEM_A_LISTA
            rolar_a_pagina(d)
            pausa(ESPERA_DA_ROLAGEM)
            continue
        janela, itens = achado
        linha, fechado, fim_dentro = _linha_na_tela(itens, alvo, dentro)
        if linha and _tocavel(tela, linha["caixa"]) and _na_janela(janela, linha["caixa"]):
            d.click(*_centro(linha["caixa"]))
            return _conferir_a_aula_tocada(d, lista, numero, pausa)
        if _onde_esta_a_aula(itens, lista, numero, linha, janela) == "acima":
            # A aula rolou por cima da caixa da lista (o site rola a caixa sozinho até a aula aberta na página): a
            # caixa volta, por dentro, só enquanto há linha escondida por cima dela.
            if subidas >= SUBIDAS_DA_LISTA or not _escondida_por_cima(itens, janela):
                return False, SEM_A_AULA_NA_LISTA
            subidas += 1
            _subir_na_lista(d, janela)
            pausa(ESPERA_DA_ROLAGEM)
            antes = None
            continue
        if fechado and not tocado:
            espaco = fechado["caixa"][3] + ESPACO_DA_AULA < _topo_do_proximo(tela)
            if espaco and _tocavel(tela, fechado["caixa"]) and _na_janela(janela, fechado["caixa"]):
                d.click(*_centro(fechado["caixa"]))
                tocado = True
                pausa(ESPERA_DO_MODULO)
                continue
        marca = [(item["tipo"], item["nome"], item["caixa"]) for item in itens]
        if (marca == antes and fechado and not tocado and _tocavel(tela, fechado["caixa"])
                and _na_janela(janela, fechado["caixa"])):
            # O módulo da aula no fim da página, sem lugar embaixo para as aulas: fechado, é tocado uma vez.
            d.click(*_centro(fechado["caixa"]))
            tocado, antes = True, None
            pausa(ESPERA_DO_MODULO)
            continue
        if marca == antes:
            return False, SEM_A_AULA_NA_LISTA
        antes, dentro = marca, fim_dentro
        rolar_a_pagina(d)
        pausa(ESPERA_DA_ROLAGEM)
    return False, SEM_A_AULA_NA_LISTA


def _seguinte_na_lista(lista, numero):
    """O nome que o Próximo da aula `numero` mostra: o da aula seguinte da lista ("" na última do curso)."""
    return lista[numero]["nome"] if numero < len(lista) else ""


def _conferir_a_aula_tocada(d, lista, numero, pausa):
    """A aula tocada na lista abriu? O Próximo mostra a seguinte da lista (ou nenhuma, na última). (ok, porque)."""
    seguinte = _seguinte_na_lista(lista, numero)
    for _ in range(ESPERA_DA_PAGINA // PASSO_DA_ESPERA):
        pausa(PASSO_DA_ESPERA)
        tela, _ponto = proximo_na_tela(d, pausa)
        if _mostra_a_seguinte(tela, seguinte):
            return True, ""
    return False, OUTRA_AULA


def _mostra_a_seguinte(tela, seguinte):
    """
    O Próximo da tela mostra a aula `seguinte`; na última do curso (""), uma página de aula sem o Próximo (as abas, o
    player ou, com a página rolada, a lista das aulas).
    """
    if nome_no_proximo(tela) != seguinte:
        return False
    lista = itens_da_lista(tela)
    return bool(seguinte) or pagina_da_aula_pronta(tela) or tem_player(tela) or bool(lista and lista[1])


def na_aula(d, posicao, numero, pausa):
    """A página é a da aula `numero` da lista do curso? O Próximo dela mostra a seguinte da lista (ou nenhuma)."""
    lista = lista_do_curso(posicao)
    if not 1 <= int(numero) <= len(lista):
        return False
    tela, _ponto = proximo_na_tela(d, pausa)
    return _mostra_a_seguinte(tela, _seguinte_na_lista(lista, int(numero)))


# A aula aberta pela lista fica com a página rolada lá embaixo, na lista, e o player sai da tela e da leitura dela. Ela
# sobe meia tela por vez, com o dedo para baixo, e para assim que o alto da aula aparece: na videoaula (a da lista com a
# duração), o player inteiro, pelo play do meio dele (o vídeo pausado antes), a meia altura do player abaixo do alto da
# página; na aula sem vídeo, o leitor do documento, o carrossel ou o nome dela. O arrasto nunca começa com o alto à
# vista, porque no alto da página o Chrome o toma por "puxar para atualizar" e recarrega a página (o teste de
# 23/11/2026, às 12:00): com o player à vista sem o play (o vídeo tocando), a subida para ali.
# A 1ª aula do curso, tocada na lista da aula em que o site parou (a que o endereço guardado abre), abre do alto da
# página, e o lugar do player ("video-player-container") chega antes do play (os testes de 25/11/2026, à 01:23 e às
# 04:08). O arrasto no alto recarrega o endereço da barra, que volta à aula em que o site parou, e não à tocada: na
# noite de 25/11/2026, cada arrasto no alto, com o player ainda sem o play, voltou a ela, com o player em branco, e a
# subida acabou sem o alto. Com a página vindo (a barra de andamento do Chrome), a subida espera em vez de arrastar, e,
# na videoaula, o lugar do player inteiro na tela já é o alto.
SUBIDA_DA_PAGINA = (540, 900, 540, 1400)
VEZES_DA_SUBIDA = 16
# O player ocupa a largura da tela, em 16:9: o play do meio fica a meia altura dele (1080 * 9 / 16 / 2).
METADE_DO_PLAYER = 300
TOPO_DA_PAGINA = 267
SEM_O_ALTO = "o alto da aula não apareceu"
ID_DO_LUGAR_DO_PLAYER = "video-player-container"
IDS_DO_ANDAMENTO = ("toolbar_progress_bar", "progress_bar_animating_view")


def _topo_da_pagina(tela):
    """Onde a página começa na tela: o alto do WebView (a barra do Chrome some com a página rolada)."""
    return next((no["caixa"][1] for no in _nos(tela) if no["classe"] == "WebView"), TOPO_DA_PAGINA)


def lugar_do_player_na_tela(tela):
    """O lugar do player inteiro na tela, abaixo do alto da página, mesmo antes de o player chegar a ele?"""
    topo = _topo_da_pagina(tela)
    return any(no["id"] == ID_DO_LUGAR_DO_PLAYER and no["caixa"][1] >= topo and no["caixa"][3] <= BAIXO_DA_TELA
               and no["caixa"][3] - no["caixa"][1] >= 2 * METADE_DO_PLAYER - 20 for no in _nos(tela))


def pagina_vindo(tela):
    """A página ainda vem: a barra de andamento do Chrome no alto ou a guia sem nada da página (pagina_em_branco)."""
    return any(no["id"] in IDS_DO_ANDAMENTO for no in _nos(tela)) or pagina_em_branco(tela)


def player_inteiro_na_tela(tela):
    """
    O player inteiro à vista, abaixo do alto da página: pelo play do meio dele (o vídeo pausado) ou pelo lugar dele
    (o "video-player-container", com o vídeo tocando ou ainda vindo). Um pedaço do player no alto da tela não basta.
    """
    play = botao_do_play(tela)
    if play and play[1] - METADE_DO_PLAYER >= _topo_da_pagina(tela):
        return True
    return lugar_do_player_na_tela(tela)


def alto_da_aula(tela, nome="", com_video=True):
    """
    O alto da página da aula está à vista? Com o play do player, só com o player inteiro na tela; sem o play, o player
    (o vídeo tocando: dali a subida não passa), o leitor do documento, o carrossel, na videoaula o lugar do player
    inteiro na tela ou, na aula sem vídeo, o nome dela.
    """
    play = botao_do_play(tela)
    if play:
        return play[1] - METADE_DO_PLAYER >= _topo_da_pagina(tela)
    if tem_player(tela) or botao_de_baixar(tela) or carrossel_na_tela(tela)[0]:
        return True
    if com_video:
        return lugar_do_player_na_tela(tela)
    return bool(nome) and any(" ".join(no["texto"].split()) == nome for no in _nos_da_aula(tela))


def subir_ate_o_alto(d, aula, pausa):
    """
    A página da aula aberta pela lista (aula: a da lista) de volta ao alto (alto_da_aula). True com ele à vista. Com a
    página vindo (pagina_vindo), a subida espera, sem arrasto.
    """
    com_video = bool(aula.get("segundos"))
    for _ in range(VEZES_DA_SUBIDA):
        tela = _fechar_a_folha_do_chrome(d, pausa)
        if alto_da_aula(tela, aula["nome"], com_video):
            return True
        if pagina_vindo(tela):
            pausa(PASSO_DA_ESPERA)
            continue
        d.swipe(*SUBIDA_DA_PAGINA, 0.3)
        pausa(ESPERA_DA_ROLAGEM)
    return alto_da_aula(d.dump_hierarchy(), aula["nome"], com_video)


def _tipo_no_alto(d, pausa, com_video=False):
    """
    O tipo da aula aberta pela lista, com a página no alto: (COM_VIDEO, "") com o play à vista ou o vídeo tocando; sem
    player nenhum, nem depois de mais um tempo, (SEM_VIDEO, ""); o player sem o play, (None, o porquê). Na videoaula
    (com_video: a da lista com a duração), o play é esperado por até ESPERA_DO_PLAY s, e ela nunca é tomada por uma
    aula sem vídeo: sem ele, (None, o porquê).
    """
    espera = ESPERA_DO_PLAY if com_video else ESPERA_SEM_O_PLAYER
    tela = d.dump_hierarchy()
    for _ in range(espera // PASSO_DA_ESPERA + 1):
        if botao_do_play(tela) or _tocando_ou_carregando(midia_do_chrome(d)):
            return COM_VIDEO, ""
        pausa(PASSO_DA_ESPERA)
        tela = d.dump_hierarchy()
    if com_video or tem_player(tela):
        return None, f"{SEM_O_PLAYER}; {descrever_a_midia(midia_do_chrome(d))}"
    return SEM_VIDEO, ""


def abrir_a_aula_da_vez(d, posicao, numero, pausa, vigiar=None):
    """
    A aula da vez aberta já com o gravador gravando (o vídeo pode começar a tocar sozinho): da 2ª em diante, pelo
    Próximo da de antes, que tem de estar na tela, conferida pelo nome na lista; a 1ª do curso, sem aula antes dela,
    pelo toque no nome dela na lista, e a página sobe até o alto. A videoaula (a da lista com a duração) que o Próximo
    abre sem o player inteiro na tela também sobe até ele, e nunca é tomada por uma aula sem vídeo. (tipo, porque),
    como em _tipo_da_pagina; vigiar, como em abrir_pela_lista.
    """
    lista = lista_do_curso(posicao)
    aula = lista[int(numero) - 1]
    if int(numero) == 1:
        # A página de antes é uma aula do curso (_aula_de_antes_na_tela): a lista dela, sem o endereço.
        ok, porque = abrir_pela_lista(d, posicao, 1, pausa, no_curso=True, vigiar=vigiar)
        if not ok:
            return None, porque
        # O vídeo que começou sozinho pausa enquanto a página sobe (o play o retoma de onde parou, e o começo dele
        # já ficou na gravação): pausado, o play do meio do player mostra onde fica o alto.
        pausar_o_que_toca(d, pausa)
        if not subir_ate_o_alto(d, aula, pausa):
            return None, SEM_O_ALTO
        return _tipo_no_alto(d, pausa, com_video=bool(aula.get("segundos")))
    tela, _ponto = proximo_na_tela(d, pausa)
    if nome_no_proximo(tela) != aula["nome"]:
        return None, OUTRA_PAGINA
    tipo, porque, _nome = passar_para_a_seguinte(d, pausa)
    if tipo and aula.get("segundos") and not player_inteiro_na_tela(d.dump_hierarchy()):
        # A página nova pode vir rolada para baixo, com a descrição da aula aberta (a que tem um link) e as abas à
        # vista: na noite de 26/11/2026, as aulas 13 e 14 do curso 4 viraram aulas sem vídeo, e a 17 foi gravada com
        # o player fora da tela. Como na 1ª aula do curso, o vídeo que começou sozinho pausa, e a página sobe até o
        # player inteiro.
        pausar_o_que_toca(d, pausa)
        if not subir_ate_o_alto(d, aula, pausa):
            return None, SEM_O_ALTO
        tipo, porque = _tipo_no_alto(d, pausa, com_video=True)
    if tipo and not na_aula(d, posicao, numero, pausa):
        return None, OUTRA_PAGINA
    return tipo, porque


def _aberta_no_explorar(d, tipo, porque):
    """O que o explorar diz da aula que tentou abrir: o tipo, o vídeo e o play, só em palavras fixas e números."""
    if not tipo:
        return False, f"a aula não abriu ({porque})"
    play = "o play na tela" if botao_do_play(d.dump_hierarchy()) else "sem o play na tela"
    return True, f"aula aberta, {tipo}: {descrever_a_midia(midia_do_chrome(d))}; {play}"


def _proxima_no_explorar(d, pausa):
    """O passo curso:proximo: a aula seguinte à aberta pelo Próximo, como a noite, sem mudar o mapa."""
    if not botao_do_proximo(d.dump_hierarchy()):
        return False, "a tela não é a de uma aula com o Próximo"
    tipo, porque, _nome = passar_para_a_seguinte(d, pausa)
    return _aberta_no_explorar(d, tipo, porque)


def _guardar_no_explorar(d, pausa):
    """
    O passo curso:guardar: a aula sem vídeo aberta no Chrome guardada como a noite guarda, na pasta das aulas, como a
    aula 0 do curso 0 (o teste de dia vai ao Claude pelo cursos_robo.yml); na videoaula, só a página dela, sem tocar no
    play. O log diz só números.
    """
    tela = d.dump_hierarchy()
    if not pagina_da_aula_pronta(tela):
        return False, "a tela não é a de uma aula do curso"
    if tem_player(tela):
        # A videoaula: só a página dela (o texto, os links e o documento), como a noite guarda depois da gravação.
        pasta, info = guardar_a_aula_sem_video(d, 0, 0, pausa, tipo=PAGINA_DA_VIDEOAULA)
        if not pasta:
            return False, f"a página da videoaula não foi guardada ({info['problema']})"
        return True, f"página da videoaula guardada: {descrever_a_aula_guardada(info)}"
    pasta, info = guardar_a_aula_sem_video(d, 0, 0, pausa)
    if not pasta:
        return False, f"a aula não foi guardada ({info['problema']})"
    return True, f"aula sem vídeo guardada: {descrever_a_aula_guardada(info)}"


GRAVACAO_DO_TESTE = 10 * 60


def _gravar_no_explorar(d, posicao, numero, pausa):
    """
    O passo curso:gravar:N[:K], o teste de dia da gravação da noite: a aula K da lista do curso N (sem o K, a 1ª) aberta
    como a noite abre (_aula_de_antes_na_tela e abrir_a_aula_da_vez: da 2ª em diante, a de antes vem pela lista, muda
    e sem o gravador, e a da vez pelo Próximo dela, com o gravador já gravando; a 1ª, pela lista de uma aula do curso
    aberta antes pelo endereço, muda e sem o gravador, já com o gravador gravando) e gravada até o fim, no máximo
    GRAVACAO_DO_TESTE s, com o começo e o fim conferidos pela duração da lista; guardada como a aula 0 do curso 0, com
    a fala e as folhas de quadros. O som da aula vai só ao servidor, e antes e depois o celular fica mudo; o robô que
    pede o celular para o teste, como para a noite, e a gravação sai sem ser lida. A tela do teste que não gravou vai
    ao Claude pelos casos. De madrugada, quem grava é a noite. O log diz só números e palavras fixas.
    """
    if _madrugada_agora():
        return False, "de madrugada, quem grava as aulas é a noite"
    lista = lista_do_curso(posicao)
    if not lista:
        return False, f"o curso {posicao} ainda não tem a lista das aulas (curso:lista:{posicao})"
    if not 1 <= numero <= len(lista):
        return False, f"a lista do curso {posicao} tem {len(lista)} aula(s)"
    aberta, porque = _aula_de_antes_na_tela(d, posicao, numero, None, pausa)
    if not aberta:
        guardar_o_caso(d, porque, "teste da gravação", passo="abrir a aula de antes")
        return False, f"a aula de antes da {numero} do curso {posicao} não abriu ({porque})"
    os.makedirs(PASTA_DAS_GRAVACOES, exist_ok=True)
    destino = os.path.join(PASTA_DAS_GRAVACOES, f"{_agora():%Y%m%d-%H%M%S}.mkv")
    aberta, inteira, fim = gravar_a_aula(
        d, getattr(d, "serial", ""), destino, lambda celular: abrir_a_aula_da_vez(celular, posicao, numero, pausa),
        lambda celular: tocar_pelo_play(celular, pausa), pausa=pausa, madrugada=lambda: True,
        maximo=GRAVACAO_DO_TESTE, duracao=lista[numero - 1].get("segundos"),
        na_aula_certa=lambda celular: na_aula(celular, posicao, numero, pausa),
        reiniciar=lambda celular: voltar_ao_comeco(celular, pausa))
    calar_o_celular(d)
    tocou = aberta and fim not in PARADAS_DA_AULA + (SEM_VIDEO, NAO_TOCOU, OUTRA_PAGINA)
    if not tocou or not os.path.exists(destino) or not os.path.getsize(destino):
        # O robô que pede o celular o tem na hora (a leitura da fala o seguraria), e a aula que não tocou não tem o
        # que ler: a gravação sai sem ser lida, e o teste fica para depois.
        if os.path.exists(destino):
            os.remove(destino)
        if fim not in PARADAS_DA_AULA:
            guardar_o_caso(d, fim, "teste da gravação", passo="gravar a aula")
        if fim == SEM_VIDEO:
            return False, f"a aula {numero} do curso {posicao} não tem vídeo"
        return False, f"a gravação parou ({fim}) e saiu sem ser lida"
    _pasta, info = guardar_a_aula(destino, 0, 0, fim)
    return not info.get("problema"), (
        f"aula {numero} do curso {posicao} gravada {'inteira' if inteira else 'pela metade'} ({fim}): "
        f"{info.get('segundos')} s, som {info.get('som')} LUFS, {info.get('palavras')} palavra(s), "
        f"{info.get('folhas')} folha(s) de quadros, {info.get('problema') or 'sem problema'}; "
        f"para ler: cursos_robo.yml exportar")


def _lista_no_explorar(d, posicao, pausa):
    """
    O passo curso:lista:N: o curso N aberto pelo endereço guardado (a aula em que o site parou), o que tocar pausado, e
    a lista das aulas lida da aba Módulos e guardada no mapa, só com ela inteira. O log diz só números.
    """
    aulas = (mapa_das_aulas()["cursos"].get(str(posicao)) or {}).get("aulas") or []
    if not aulas:
        return False, f"o curso {posicao} ainda não tem a 1ª aula no mapa"
    tipo, porque = ir_para_o_endereco(d, aulas[0]["endereco"], pausa)
    if not tipo:
        # A tela de onde o curso não abriu (a guia em branco de 24/11/2026, por exemplo) vai ao Claude pelos casos.
        guardar_o_caso(d, porque, "curso não abriu", passo="abrir o curso pelo endereço")
        return False, f"a aula não abriu ({porque})"
    pausar_o_que_toca(d, pausa)
    total = total_de_aulas(d.dump_hierarchy())
    lista, porque = ler_a_lista(d, pausa, ao_comecar=lambda: guardar_o_caso(
        d, "o começo da lista", "lista das aulas", passo="ler a lista das aulas"))
    pausar_o_que_toca(d, pausa)
    if not lista:
        # A tela de onde a lista não passou vai ao Claude pelos casos (o print e a forma dela, cifrados).
        guardar_o_caso(d, porque, "lista não lida", passo="ler a lista das aulas")
        return False, f"a lista do curso {posicao} não foi lida ({porque})"
    if total and len(lista) != total:
        # A lista que não bate com o total do site (aula repetida ou que faltou) não vale para a noite: fica à parte,
        # para o Claude conferir, com a contagem dos números de aula diferentes que ela tem.
        guardar_a_lista_sem_bater(posicao, lista, total)
        guardar_o_caso(d, "a lista não bate com o total do site", "lista não bate", passo="ler a lista das aulas")
        numeros = len({aula["aula"] for aula in lista if aula.get("aula")})
        return False, (f"a lista do curso {posicao} tem {len(lista)} aula(s), {numeros} com o número da aula, e o site "
                       f"diz {total}: a lista não foi guardada, só a cópia para o Claude conferir")
    de_antes = guardar_a_lista(posicao, lista)
    return True, (descrever_a_lista(posicao, lista) + (", o mesmo total do site" if total else ", sem o total do site")
                  + (f"; {de_antes} aula(s) com a duração da leitura anterior" if de_antes else ""))


def _tocar_no_explorar(d, posicao, numero, pausa):
    """
    O passo curso:tocar:N:K, o teste de dia da abertura pela lista (com o celular mudo): a aula K da lista do curso N
    tocada pelo nome, o que tocar pausado, e a tela de depois guardada para o Claude pelos casos (o print e a forma
    dela, cifrados), para ele ver onde a página ficou. O log diz só se abriu, o player e o vídeo, em palavras fixas.
    """
    if posicao not in ORDEM_DOS_CURSOS:
        return False, f"o curso vai de 1 a {len(ORDEM_DOS_CURSOS)} (a posição na lista de Turmas)"
    if not lista_do_curso(posicao):
        return False, f"o curso {posicao} ainda não tem a lista das aulas (curso:lista:{posicao})"
    ok, porque = abrir_pela_lista(d, posicao, numero, pausa)
    pausar_o_que_toca(d, pausa)
    guardar_o_caso(d, "aula aberta pela lista" if ok else porque, "aula pela lista", passo="abrir a aula pela lista")
    if not ok:
        return False, f"a aula {numero} do curso {posicao} não abriu pela lista ({porque})"
    player = "o player à vista" if tem_player(d.dump_hierarchy()) else "sem o player à vista"
    return True, (f"aula {numero} do curso {posicao} aberta pela lista: {player}; "
                  f"{descrever_a_midia(midia_do_chrome(d))}")


def curso_no_explorar(d, argumento, pausa=time.sleep):
    """
    O passo curso do explorar: curso:primeira:N guarda o endereço da aula aberta no Chrome como o do curso na posição N
    da lista de Turmas (o Claude a abre com o mapa do site); curso:abrir:N abre o curso N por ele (a aula em que o site
    parou), e curso:proximo, a seguinte à aberta, pelo Próximo (os dois sem mudar o mapa, com o celular mudo);
    curso:guardar guarda a aula sem vídeo aberta (ou a página da videoaula), como a noite; curso:gravar:N[:K] grava de
    dia a aula K da lista do curso N (sem o K, a 1ª) como a noite grava (o teste); curso:lista:N lê da aba Módulos a
    lista das aulas do curso N, na ordem, e a guarda no mapa (com o celular mudo); curso:tocar:N:K abre a aula K dessa
    lista pelo toque no nome dela, como a noite abre, e guarda a tela para o Claude (casos); curso sozinho diz o mapa
    em números. O endereço e os nomes ficam no banco, e o log diz só números e palavras fixas. Antes de cada passo, o
    Chrome da frente fica em pé, como na noite (chrome_em_pe), e o que mudou vai no fim do log.
    """
    partes = [parte.strip() for parte in argumento.split(":")] if argumento else []
    if not partes:
        return True, resumo_do_mapa()
    em_pe = chrome_em_pe(d, pausa)
    if em_pe == CHROME_DEITADO:
        return False, CHROME_DEITADO
    ok, texto = _passo_do_curso(d, partes, pausa)
    return ok, (f"{texto} ({em_pe})" if em_pe else texto)


def _passo_do_curso(d, partes, pausa):
    """O passo curso:... do explorar (curso_no_explorar), já com o Chrome da frente em pé."""
    if partes == ["proximo"]:
        return _proxima_no_explorar(d, pausa)
    if partes == ["guardar"]:
        return _guardar_no_explorar(d, pausa)
    if partes[0] == "tocar" and len(partes) == 3 and partes[1].isdigit() and partes[2].isdigit():
        return _tocar_no_explorar(d, int(partes[1]), int(partes[2]), pausa)
    if partes[0] == "gravar" and len(partes) == 3 and partes[1].isdigit() and partes[2].isdigit():
        if int(partes[1]) not in ORDEM_DOS_CURSOS:
            return False, f"o curso vai de 1 a {len(ORDEM_DOS_CURSOS)} (a posição na lista de Turmas)"
        return _gravar_no_explorar(d, int(partes[1]), int(partes[2]), pausa)
    if partes[0] not in ("primeira", "abrir", "gravar", "lista") or len(partes) != 2 or not partes[1].isdigit():
        return False, ("curso:primeira:N guarda a aula aberta como a 1ª do curso N; curso:abrir:N abre a 1ª do curso "
                       "N; curso:proximo abre a seguinte; curso:guardar guarda a aula sem vídeo aberta (ou a página "
                       "da videoaula); curso:gravar:N[:K] grava a aula K (sem o K, a 1ª) do curso N como a noite; "
                       "curso:lista:N lê a lista das aulas do curso N; curso:tocar:N:K abre a aula K da lista pelo "
                       "nome; curso diz o mapa")
    posicao = int(partes[1])
    if posicao not in ORDEM_DOS_CURSOS:
        return False, f"o curso vai de 1 a {len(ORDEM_DOS_CURSOS)} (a posição na lista de Turmas)"
    if partes[0] == "gravar":
        return _gravar_no_explorar(d, posicao, 1, pausa)
    if partes[0] == "lista":
        return _lista_no_explorar(d, posicao, pausa)
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
        return False, "o endereço da tela não é o de uma aula do curso"
    return True, f"endereço do curso {posicao} guardado"


def toca_aula(nome, argumento):
    """
    O passo do explorar pode fazer o vídeo de uma aula tocar (abrir uma aula, tocar o vídeo do Chrome ou abrir os
    links da página, no guardar)? Com ele, também de dia, o celular fica mudo: ele fica no quarto do Rafael (pedido
    dele, 22/11/2026).
    """
    acao = (argumento or "").split(":")[0].strip().lower()
    return ((nome == "curso" and acao in ("abrir", "proximo", "gravar", "lista", "tocar", "guardar"))
            or (nome == "midia" and acao == "tocar"))


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


# Depois do Reiniciar, o vídeo pausado está no começo: a sessão de mídia diz até este segundo.
COMECO_DO_REINICIAR = 2


def voltar_ao_comeco(d, pausa=None):
    """
    O vídeo da aula que o site abriu adiantado (ele guarda onde a aula parou: a das 3h45, a que o robô interrompeu, a
    que o Rafael viu à mão) volta ao começo: pausado, pelo Reiniciar da barra do player (o teste de 24/11/2026 o levou
    dos 12 s aos 0 s). True com a sessão de mídia do Chrome no começo e o vídeo parado.
    """
    pausa = pausa or time.sleep
    if not pausar_o_que_toca(d, pausa):
        return False
    xml = d.dump_hierarchy()
    ponto = botao_do_reiniciar(xml)
    if not ponto or not _livre_para_tocar(xml, ponto):
        return False
    d.click(*ponto)
    pausa(PASSO_DA_ESPERA)
    midia = midia_do_chrome(d)
    return bool(midia) and midia["estado"] != "tocando" and midia["posicao"] <= COMECO_DO_REINICIAR


# --- O que a aula tem além do vídeo (pedidos do Rafael de 23/11/2026, às 08:44 e às 09:12) ---
# O Claude faz o papel de aluno do curso inteiro: além da videoaula, o texto da aula e os documentos, baixados pelo
# botão do próprio site (nunca por fora do player, P288 3). O Chrome guarda o baixado na pasta Download do celular; a
# marca, um arquivo vazio criado antes do toque, diz qual é o novo, e ele vem ao servidor quando para de crescer e sai
# do celular (a memória dele não enche). Tudo vai só à pasta da aula, cifrado ao Claude pelo cursos_robo.yml, nunca ao
# log nem ao repositório: o log diz só quantos. O documento maior que MAIOR_DOCUMENTO fica só anotado (o pacote ao
# Claude tem até 40 MB, e o servidor não pode lotar: P290 1).
PASTA_DOS_BAIXADOS = "/sdcard/Download"
MARCA_DO_CURSO = PASTA_DOS_BAIXADOS + "/.curso_antes_do_baixar"
ESPERA_DO_DOCUMENTO = 90
MAIOR_DOCUMENTO = 30 * 1024 * 1024
GRANDE_DEMAIS = "o documento é grande demais para o pacote"


def textos_da_pagina(xml):
    """
    Os textos da página aberta no Chrome, na ordem da página (a do leitor de tela), sem a barra e os botões do
    próprio Chrome: o título da aula, a descrição, os nomes dos módulos... [] sem a página na tela.
    """
    try:
        raiz = ET.fromstring(xml or "")
    except ET.ParseError:
        return []
    pagina = next((no for no in raiz.iter("node") if no.get("class") == "android.webkit.WebView"), None)
    if pagina is None:
        return []
    textos = []
    for no in pagina.iter("node"):
        for chave in ("text", "content-desc"):
            valor = " ".join((no.get(chave) or "").split())
            if valor and (not textos or textos[-1] != valor):
                textos.append(valor)
    return textos


def marcar_antes_de_baixar(d):
    """A marca no celular logo antes do toque no botão de baixar do site; a hora do baixado tem de passar a dela."""
    _saida(d, ["touch", MARCA_DO_CURSO])


def baixados_depois_da_marca(d):
    """
    Os arquivos que o Chrome baixou depois da marca, já inteiros: [(caminho no celular, bytes)], o mais novo primeiro.
    O que começa com ponto (o ".pending-…" do Android) e o ".crdownload" ainda estão sendo gravados.
    """
    comando = ["find", PASTA_DOS_BAIXADOS, "-maxdepth", "1", "-type", "f", "-newer", MARCA_DO_CURSO,
               "-exec", "stat", "-c", "%Y %s %n", "{}", "+"]
    achados = []
    for linha in _saida(d, comando).splitlines():
        partes = linha.strip().split(" ", 2)
        if len(partes) != 3 or not partes[0].isdigit() or not partes[1].isdigit():
            continue
        nome = os.path.basename(partes[2])
        if not nome.startswith(".") and not nome.endswith(".crdownload"):
            achados.append((int(partes[0]), int(partes[1]), partes[2]))
    return [(caminho, tamanho) for _, tamanho, caminho in sorted(achados, reverse=True)]


def nome_do_documento(caminho, numero):
    """O nome do documento na pasta da aula: documento_N com a extensão do baixado (o nome dele fica só no celular)."""
    extensao = os.path.splitext(caminho)[1].lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,5}", extensao):
        extensao = ""
    return f"documento_{numero}{extensao}"


def trazer_o_baixado(d, pasta, numero=1, pausa=None, espera=ESPERA_DO_DOCUMENTO):
    """
    O documento que o Chrome baixou depois da marca, trazido à pasta da aula quando para de crescer (duas leituras
    iguais seguidas) e tirado do celular. (nome na pasta, bytes, "") ou (None, bytes, o porquê em palavras fixas).
    """
    pausa = pausa or time.sleep
    anterior = None
    for _ in range(max(1, espera // PASSO_DA_ESPERA)):
        pausa(PASSO_DA_ESPERA)
        novos = baixados_depois_da_marca(d)
        atual = novos[0] if novos else None
        if atual and atual[1] > 0 and atual == anterior:
            break
        anterior = atual
    else:
        return None, 0, "o documento não apareceu no celular"
    remoto, tamanho = atual
    try:
        if tamanho > MAIOR_DOCUMENTO:
            return None, tamanho, GRANDE_DEMAIS
        os.makedirs(pasta, exist_ok=True)
        nome = nome_do_documento(remoto, numero)
        try:
            d.pull(remoto, os.path.join(pasta, nome))
        except Exception as e:
            return None, tamanho, f"o documento não veio do celular ({type(e).__name__})"
        if not os.path.exists(os.path.join(pasta, nome)) or not os.path.getsize(os.path.join(pasta, nome)):
            return None, tamanho, "o documento não veio do celular"
        return nome, tamanho, ""
    finally:
        _saida(d, ["rm", "-f", remoto, MARCA_DO_CURSO])
        _saida(d, ["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", "file://" + remoto])


# A aula sem vídeo guardada como as gravadas, na pasta das aulas (o Claude no papel de aluno: pedidos do Rafael de
# 23/11/2026, às 08:44 e às 09:12): as telas da página, do alto até as abas (tela_NN.jpg, para as imagens e a forma), o
# texto da aula até as abas (texto.txt, com o "Ver mais" aberto) e o documento pelo Baixar do leitor de PDF da própria
# página (documento_1.ext). Os links da aula são abertos e guardados (abrir_o_link), sem nada tocado nem escrito nas
# páginas deles. Nenhum toque cai no Próximo, na bolha do chat (BOLHA_DO_CHAT) ou na barra do Chrome
# (_livre_para_tocar), e o Próximo só é tocado sem um aviso do Chrome em cima dele (o do download, AVISOS_DO_CHROME).
ROTULO_DO_BAIXAR = "Baixar"
ROTULO_DO_VER_MAIS = "Ver mais"
TELAS_DA_AULA = 12
VEZES_DO_VER_MAIS = 3
LADO_DA_TELA = 1280
QUALIDADE_DA_TELA = 80
ESPERA_DA_ROLAGEM = 1.5
BAIXO_DA_TELA = 2394
BOLHA_DO_CHAT = (884, 1999, 1039, 2157)
AVISOS_DO_CHROME = ("message", "snackbar", "infobar")
ESPERA_DO_AVISO = 15


def _nos_da_aula(xml):
    """Os nós da página da aula no Chrome, do alto até as abas (Módulos, Comentários...), sem o resto do site."""
    try:
        raiz = ET.fromstring(xml or "")
    except ET.ParseError:
        return []
    pagina = next((no for no in raiz.iter("node") if no.get("class") == "android.webkit.WebView"), None)
    if pagina is None:
        return []
    nos = _nos(ET.tostring(pagina, encoding="unicode"))
    fim = next((numero for numero, no in enumerate(nos) if no["id"].endswith(ID_DAS_ABAS)), len(nos))
    return nos[:fim]


BOTOES_DA_PAGINA = ("Button", "ToggleButton", "Image")


def textos_da_aula(xml):
    """
    Os textos da aula, na ordem da página, do alto até as abas (sem os módulos, os comentários e o Próximo) e sem os
    nomes dos botões (o zoom, o Baixar e o Imprimir do leitor de PDF, o "Ver mais").
    """
    textos = []
    for no in _nos_da_aula(xml):
        if no["classe"] in BOTOES_DA_PAGINA:
            continue
        for valor in (no["texto"], no["descricao"]):
            valor = " ".join(valor.split())
            if valor and (not textos or textos[-1] != valor):
                textos.append(valor)
    return textos


def links_da_aula(xml):
    """Os links da aula à vista (o texto de cada um), como a página os mostra (o endereço fica no site)."""
    return [texto for texto, _ponto in links_na_tela(xml)]


def links_na_tela(xml):
    """Os links da aula à vista, [(texto, centro)], na ordem da página (o mesmo nome pode levar a outros endereços)."""
    return [(no["descricao"], _centro(no["caixa"])) for no in _nos_da_aula(xml)
            if no["clicavel"] and no["classe"] == "View" and no["descricao"] and not no["id"]]


# Os links das aulas (pedidos do Rafael de 23/11/2026, às 08:44, e de 26/11/2026, de manhã: "sempre analisar os
# links"): todo link da aula é aberto e a página dele guardada para o Claude ler, também o de compra ou de cadastro, só
# para ver do que se trata. Nas páginas dos links nada é tocado nem escrito (nunca dados de cartão ou pessoais, nunca a
# compra): só a tela é guardada e rolada. O endereço vem antes, sem abrir: o dedo segurado no link abre o menu do
# Chrome, e o "Copiar endereço do link" o põe na área de transferência. A página abre numa guia nova, pelo Android (o
# endereço nunca é escrito na barra da aula), e sai pela tecla voltar, que fecha a guia e devolve a aula.
ROTULOS_DA_COPIA = ("Copiar endereço do link", "Copiar link")
ROTULOS_DO_MENU_DO_LINK = ROTULOS_DA_COPIA + ("Abrir em nova guia", "Abrir em uma nova guia", "Abrir em guia anônima",
                                              "Copiar texto do link", "Compartilhar link", "Fazer o download do link")
ROTULOS_DA_SELECAO = ("Selecionar tudo",)
# O dedo segurado por 2 s: o menu abre também com o toque longo mais lento que a acessibilidade do Android deixa
# escolher (1,5 s).
DEDO_SEGURADO = 2.0
TOQUES_LONGOS_POR_AULA = 40
LINKS_POR_AULA = 20
TELAS_DO_LINK = 6
ESPERA_DO_LINK = 20
VOLTAS_DO_LINK = 3
ESQUEMAS_ABERTOS = ("http://", "https://")
SEM_O_MENU = "o menu do link não abriu"
NAO_E_PAGINA = "não é uma página da internet"
NAO_VOLTOU = "a aula não voltou depois do link"


def _rotulos_na_tela(xml):
    return {" ".join((no["texto"] or no["descricao"]).split()) for no in _nos(xml)}


def opcao_de_copiar(xml):
    """O centro do "Copiar endereço do link" do menu que o Chrome abre com o dedo segurado num link; None sem ele."""
    for no in _nos(xml):
        if " ".join((no["texto"] or no["descricao"]).split()) in ROTULOS_DA_COPIA:
            return _centro(no["caixa"])
    return None


def menu_do_link_aberto(xml):
    """O menu do link (ou a seleção de texto que o dedo segurado abre) está na tela? Só com ele a tecla voltar fecha
    algo; sem ele, ela voltaria a página."""
    rotulos = _rotulos_na_tela(xml)
    return any(rotulo in rotulos for rotulo in ROTULOS_DO_MENU_DO_LINK + ROTULOS_DA_SELECAO)


def endereco_do_link(d, ponto, pausa, ao_falhar=None):
    """
    O endereço do link no ponto, sem abrir a página: o dedo segurado nele, o "Copiar endereço do link" do menu do
    Chrome e a área de transferência, limpa antes. O menu que fica aberto sai pela tecla voltar, só com ele na tela.
    Sem a cópia no menu, ao_falhar() é chamado antes de o menu sair (para guardar a tela num caso). O endereço ou "".
    """
    try:
        d.set_clipboard("")
    except Exception:
        pass
    d.long_click(*ponto, DEDO_SEGURADO)
    pausa(1)
    tela = d.dump_hierarchy()
    copiar = opcao_de_copiar(tela)
    if not copiar:
        if ao_falhar:
            ao_falhar()
        if menu_do_link_aberto(tela):
            d.press("back")
            pausa(1)
        return ""
    d.click(*copiar)
    pausa(1)
    try:
        endereco = (d.clipboard or "").strip()
    except Exception:
        endereco = ""
    if menu_do_link_aberto(d.dump_hierarchy()):
        d.press("back")
        pausa(1)
    return endereco


def textos_da_tela(xml):
    """Todos os textos da tela, na ordem (a página de um link ou o app que ele abriu), sem repetir o vizinho igual."""
    textos = []
    for no in _nos(xml):
        for valor in (no["texto"], no["descricao"]):
            valor = " ".join(valor.split())
            if valor and (not textos or textos[-1] != valor):
                textos.append(valor)
    return textos


def _pagina_do_link_pronta(d, pausa):
    """
    Espera a página do link: o Chrome com uma página que não é a da aula (sem as abas do curso), já com algo dela, ou
    outro app na frente. (a tela, o app).
    """
    tela, app = "", PACOTE_DO_CHROME
    for _ in range(max(1, ESPERA_DO_LINK // PASSO_DA_ESPERA)):
        pausa(PASSO_DA_ESPERA)
        tela, app = d.dump_hierarchy(), app_da_frente(d)
        if app and app != PACOTE_DO_CHROME:
            break
        if not pagina_da_aula_pronta(tela) and not pagina_em_branco(tela):
            break
    return tela, app


def _voltar_da_pagina_do_link(d, pausa):
    """
    A aula de volta na frente: a tecla voltar fecha a guia do link (ou sai do app que ele abriu), até VOLTAS_DO_LINK
    vezes, conferindo a tela a cada uma, e o Chrome volta à frente. True com a página da aula (as abas do curso).
    """
    for _ in range(VOLTAS_DO_LINK):
        d.press("back")
        pausa(ESPERA_DO_CHROME)
        if app_da_frente(d) != PACOTE_DO_CHROME:
            trazer_o_chrome(d, pausa)
        if app_da_frente(d) == PACOTE_DO_CHROME and pagina_da_aula_pronta(d.dump_hierarchy()):
            return True
    return False


def abrir_o_link(d, endereco, pasta, numero, pausa, vigiar):
    """
    A página do link aberta numa guia nova do Chrome, pelo Android (o endereço nunca é escrito na barra da aula), e
    guardada para o Claude: as telas (link_NN_tela_MM.jpg) e os textos (link_NN.txt), rolando até TELAS_DO_LINK telas.
    Nada da página é tocado nem escrito (pedido do Rafael de 26/11/2026: nunca dados de cartão ou pessoais, nunca a
    compra). O link que abre outro app (o Telegram, o YouTube) fica com uma tela dele, sem rolar. O que tocar é
    pausado, e o arquivo que o link baixar vem ao servidor, como o documento da aula. {"telas", "linhas", "app",
    "documento", "voltou", "problema"}.
    """
    info = {"telas": 0, "linhas": 0, "app": "", "documento": None, "voltou": False, "problema": ""}
    marcar_antes_de_baixar(d)
    _saida(d, ["am", "start", "-a", "android.intent.action.VIEW", "-d", endereco, "-p", PACOTE_DO_CHROME])
    tela, app = _pagina_do_link_pronta(d, pausa)
    info["app"] = "chrome" if app == PACOTE_DO_CHROME else "outro app"
    textos, anterior = [], None
    for tela_numero in range(1, (TELAS_DO_LINK if app == PACOTE_DO_CHROME else 1) + 1):
        porque = vigiar()
        if porque:
            info["problema"] = porque
            break
        atuais = textos_da_tela(tela)
        if atuais == anterior:
            break
        textos = juntar_os_textos(textos, atuais)
        guardar_a_tela(d, os.path.join(pasta, f"link_{numero:02d}_tela_{tela_numero:02d}.jpg"))
        info["telas"] += 1
        anterior = atuais
        if app != PACOTE_DO_CHROME:
            break
        rolar_a_pagina(d)
        pausa(ESPERA_DA_ROLAGEM)
        tela = d.dump_hierarchy()
    pausar_o_que_toca(d, pausa)
    with open(os.path.join(pasta, f"link_{numero:02d}.txt"), "w", encoding="utf-8") as saida:
        saida.write(endereco + "\n\n" + "\n".join(textos) + "\n")
    info["linhas"] = len(textos)
    if baixados_depois_da_marca(d):
        nome, tamanho, _porque = trazer_o_baixado(d, pasta, f"link_{numero:02d}", pausa)
        info["documento"] = {"nome": nome or "", "bytes": tamanho}
    info["voltou"] = _voltar_da_pagina_do_link(d, pausa)
    if not info["voltou"] and not info["problema"]:
        info["problema"] = NAO_VOLTOU
    return info


def resumo_do_link(item):
    """O que o link deu, em palavras fixas e números (o texto da aula e o registro)."""
    if item.get("problema") in (SEM_O_MENU, NAO_E_PAGINA):
        return item["problema"]
    partes = [f"{item.get('telas', 0)} tela(s)", f"{item.get('linhas', 0)} linha(s)"]
    if item.get("app") == "outro app":
        partes.append("abriu outro app")
    if item.get("documento"):
        partes.append(f"arquivo de {item['documento'].get('bytes', 0) // 1024} KB")
    if item.get("problema"):
        partes.append(item["problema"])
    return ", ".join(partes)


def _abrir_os_links(d, pasta, achados, pausa, vigiar):
    """
    Cada endereço achado na aula aberto uma vez (abrir_o_link), na ordem da página, até LINKS_POR_AULA; o que não é
    uma página da internet (um e-mail, um telefone) só fica anotado. A aula que não volta depois de um link não para os
    outros (cada um abre pelo endereço; a noite abre a aula de novo pela lista). Para quando vigiar() diz o porquê. (os
    links com o que cada um deu, o porquê de parar ou "").
    """
    vistos, resultado = set(), []
    for texto, endereco in achados:
        if endereco in vistos or len(resultado) >= LINKS_POR_AULA:
            continue
        vistos.add(endereco)
        porque = vigiar()
        if porque:
            return resultado, porque
        item = {"texto": texto, "endereco": endereco}
        if not endereco:
            item["problema"] = SEM_O_MENU
        elif not endereco.lower().startswith(ESQUEMAS_ABERTOS):
            item["problema"] = NAO_E_PAGINA
        else:
            item.update(abrir_o_link(d, endereco, pasta, len(resultado) + 1, pausa, vigiar))
        resultado.append(item)
        if item.get("problema") in PARADAS_DA_AULA:
            return resultado, item["problema"]
    return resultado, ""


def _botao_da_aula(xml, rotulo):
    return next((_centro(no["caixa"]) for no in _nos_da_aula(xml)
                 if no["clicavel"] and rotulo in (no["texto"], no["descricao"])), None)


def botao_de_baixar(xml):
    """O centro do Baixar do leitor de PDF da aula, o botão do próprio site (P288 3); None sem ele na tela."""
    return _botao_da_aula(xml, ROTULO_DO_BAIXAR)


def botao_do_ver_mais(xml):
    """O centro do "Ver mais" do texto da aula; None sem ele na tela."""
    return _botao_da_aula(xml, ROTULO_DO_VER_MAIS)


def _topo_do_proximo(xml):
    return next((no["caixa"][1] for no in _nos(xml) if no["clicavel"] and no["texto"].startswith(ROTULO_DO_PROXIMO)),
                BAIXO_DA_TELA)


def _livre_para_tocar(xml, ponto):
    """O ponto está na página, longe do Próximo, da bolha do chat e da barra do Chrome?"""
    x, y = ponto
    topo = 300 if texto_da_barra(xml) is not None else 0
    x1, y1, x2, y2 = BOLHA_DO_CHAT
    return topo < y < _topo_do_proximo(xml) and not (x1 <= x <= x2 and y1 <= y <= y2)


def abas_na_tela(xml):
    """As abas (Módulos...) à vista, acima do Próximo: o texto da aula, acima delas, já passou pela tela."""
    limite = _topo_do_proximo(xml)
    return any(no["id"].endswith(ID_DAS_ABAS) and no["caixa"][1] < limite for no in _nos(xml))


def aviso_do_chrome(xml):
    """Um aviso do próprio Chrome na tela (o do download, com o Abrir), que pode estar em cima do Próximo?"""
    for no in _nos(xml):
        if no["texto"] or no["descricao"] or no["clicavel"]:
            if any(parte in no["id"] for parte in AVISOS_DO_CHROME) and "webkit" not in no["classe"].lower():
                return True
    return False


def esperar_o_aviso_sair(d, pausa):
    """Espera o aviso do Chrome sair sozinho (até ESPERA_DO_AVISO s), sem tocar nele. A tela, com ou sem ele."""
    tela = _fechar_a_folha_do_chrome(d, pausa)
    for _ in range(ESPERA_DO_AVISO // PASSO_DA_ESPERA):
        if not aviso_do_chrome(tela):
            break
        pausa(PASSO_DA_ESPERA)
        tela = _fechar_a_folha_do_chrome(d, pausa)
    return tela


# A tela seguinte da página da aula pode começar com o título dela, preso no alto (o teste de dia de 23/11/2026), e a
# parte em comum com a tela anterior só vem depois dele: até LINHAS_PRESAS_NO_ALTO linhas do começo da tela nova são
# puladas na procura, e, com alguma pulada, a parte em comum precisa de MINIMO_EM_COMUM linhas (um "•" solto, igual em
# muitos lugares da página, não vale como a parte em comum e não engole o texto novo).
LINHAS_PRESAS_NO_ALTO = 2
MINIMO_EM_COMUM = 3


def juntar_os_textos(textos, novos):
    """
    Os textos da tela seguinte depois dos da anterior, sem repetir o pedaço que as duas mostram nem as linhas presas no
    alto da página que a tela nova repete antes dele.
    """
    for pulados in range(min(LINHAS_PRESAS_NO_ALTO, len(novos)) + 1):
        resto = novos[pulados:]
        minimo = MINIMO_EM_COMUM if pulados else 1
        for tamanho in range(min(len(textos), len(resto)), minimo - 1, -1):
            if textos[-tamanho:] == resto[:tamanho]:
                return textos + resto[tamanho:]
    return textos + novos


def guardar_a_tela(d, caminho):
    """A tela do celular em JPEG, com o lado maior em LADO_DA_TELA (o pacote ao Claude tem até 40 MB)."""
    imagem = d.screenshot().convert("RGB")
    imagem.thumbnail((LADO_DA_TELA, LADO_DA_TELA))
    imagem.save(caminho, "JPEG", quality=QUALIDADE_DA_TELA)


def rolar_a_pagina(d):
    """A página da aula uma tela para baixo, pelo meio, longe do Próximo e da bolha do chat."""
    d.swipe(540, 1800, 540, 900, 0.4)


def _baixar_o_documento(d, ponto, pasta, pausa):
    """O documento pelo Baixar do site, trazido ao servidor: ({"nome", "bytes"} ou None, o porquê de não vir)."""
    marcar_antes_de_baixar(d)
    d.click(*ponto)
    nome, tamanho, porque = trazer_o_baixado(d, pasta, 1, pausa)
    if nome:
        return {"nome": nome, "bytes": tamanho}, ""
    if porque == GRANDE_DEMAIS:
        return {"nome": "", "bytes": tamanho, "grande_demais": True}, ""
    return None, porque


PAGINA_VAZIA = "a página da aula não mostrou texto nem documento"

# A aula de slides (o teste de dia de 23/11/2026, a 3ª aula do curso 5): um carrossel de imagens, com o Anterior e o
# Próximo dele (sem os dois pontos, que são da barra da aula seguinte) e as miniaturas embaixo. Cada imagem vai
# inteira, recortada da tela, como um aluno passando os slides (pedidos do Rafael de 23/11/2026, às 08:44 e às 09:12).
ROTULO_DA_IMAGEM = "Imagem da aula"
ROTULO_DO_PROXIMO_DO_CARROSSEL = "Próximo"
SLIDES_DA_AULA = 80
ESPERA_DO_SLIDE = 2
QUALIDADE_DO_SLIDE = 85
# Numa cópia pequena em cinza, o ponto que muda mais que DIFERENCA_DO_PONTO (de 0 a 255) mudou; a imagem com menos
# de PONTOS_DIFERENTES pontos mudados é a mesma (o fim do carrossel, ou a volta ao 1º slide). Uma palavra nova num
# slide muda dezenas de pontos; o ruído entre dois prints da mesma imagem, nenhum.
TAMANHO_DA_COMPARACAO = (96, 54)
DIFERENCA_DO_PONTO = 24
PONTOS_DIFERENTES = 12


def carrossel_na_tela(xml):
    """
    A caixa da imagem da aula à vista (a maior) e o centro do Próximo do carrossel; (None, None) sem um carrossel na
    tela. O Próximo do carrossel é só "Próximo": o da barra da aula seguinte tem os dois pontos e nunca é tocado aqui.
    """
    nos = _nos_da_aula(xml)
    imagens = [no["caixa"] for no in nos if no["descricao"] == ROTULO_DA_IMAGEM]
    botao = next((_centro(no["caixa"]) for no in nos
                  if no["clicavel"] and ROTULO_DO_PROXIMO_DO_CARROSSEL in (no["texto"], no["descricao"])), None)
    if not imagens or not botao:
        return None, None
    return max(imagens, key=lambda caixa: (caixa[2] - caixa[0]) * (caixa[3] - caixa[1])), botao


def mesma_imagem(uma, outra):
    """As duas imagens são o mesmo slide? Pelos pontos que mudam, numa cópia pequena em cinza."""
    from PIL import ImageChops
    uma = uma.convert("L").resize(TAMANHO_DA_COMPARACAO)
    outra = outra.convert("L").resize(TAMANHO_DA_COMPARACAO)
    diferenca = ImageChops.difference(uma, outra)
    return sum(diferenca.histogram()[DIFERENCA_DO_PONTO + 1:]) < PONTOS_DIFERENTES


def _passar_os_slides(d, pasta, pausa, vigiar, caixa):
    """
    Os slides do carrossel da aula, um a um pelo Próximo dele, cada um recortado da tela (slide_NN.jpg) no tamanho
    em que aparece, até o último: o que não muda depois do toque (conferido duas vezes, para o slide que ainda
    desliza) ou o que volta ao 1º. (quantos, o porquê de parar ou "").
    """
    primeiro = anterior = None
    slides = 0
    for _ in range(SLIDES_DA_AULA):
        porque = vigiar()
        if porque:
            return slides, porque
        imagem = d.screenshot().convert("RGB").crop(caixa)
        if anterior is not None and mesma_imagem(imagem, anterior):
            pausa(ESPERA_DO_SLIDE)
            imagem = d.screenshot().convert("RGB").crop(caixa)
        if anterior is not None and (mesma_imagem(imagem, anterior) or mesma_imagem(imagem, primeiro)):
            break
        slides += 1
        imagem.save(os.path.join(pasta, f"slide_{slides:02d}.jpg"), "JPEG", quality=QUALIDADE_DO_SLIDE)
        if primeiro is None:
            primeiro = imagem
        anterior = imagem
        tela = d.dump_hierarchy()
        _caixa, botao = carrossel_na_tela(tela)
        if not botao or not _livre_para_tocar(tela, botao):
            break
        d.click(*botao)
        pausa(ESPERA_DO_SLIDE)
    return slides, ""


def _ler_a_aula(d, pasta, pausa, vigiar):
    """
    As telas, os slides do carrossel, o texto e o documento da aula aberta, na pasta. (info só de números, o porquê de
    parar ou "").
    """
    textos, links, telas, ver_mais, documento, anterior, slides = [], [], 0, 0, None, None, None
    achados, toques, com_caso = [], 0, []

    def guardar_o_caso_do_menu():
        # Uma vez por aula: a tela com o que o dedo segurado abriu, para o Claude ver por que a cópia não veio.
        if not com_caso:
            com_caso.append(True)
            guardar_o_caso(d, SEM_O_MENU, "link sem o endereço", "ler o endereço do link")
    for numero in range(1, TELAS_DA_AULA + 1):
        porque = vigiar()
        if porque:
            return {}, porque
        tela = _fechar_a_folha_do_chrome(d, pausa)
        if not _nos_da_aula(tela):
            return {}, "a página da aula saiu da tela"
        caixa, _botao = carrossel_na_tela(tela) if slides is None else (None, None)
        if caixa:
            slides, porque = _passar_os_slides(d, pasta, pausa, vigiar, caixa)
            if porque:
                return {}, porque
            tela = d.dump_hierarchy()
        ponto = botao_do_ver_mais(tela)
        if ponto and ver_mais < VEZES_DO_VER_MAIS and _livre_para_tocar(tela, ponto):
            d.click(*ponto)
            ver_mais += 1
            pausa(1)
            tela = d.dump_hierarchy()
        ponto = botao_de_baixar(tela)
        if ponto and documento is None and _livre_para_tocar(tela, ponto):
            documento, porque = _baixar_o_documento(d, ponto, pasta, pausa)
            if porque:
                return {}, porque
            tela = esperar_o_aviso_sair(d, pausa)
            if not botao_de_baixar(tela) and not pagina_da_aula_pronta(tela):
                return {}, "a página da aula saiu da tela depois do Baixar"
        atuais = textos_da_aula(tela)
        if atuais == anterior:
            break
        textos = juntar_os_textos(textos, atuais)
        links += [link for link in links_da_aula(tela) if link not in links]
        guardar_a_tela(d, os.path.join(pasta, f"tela_{numero:02d}.jpg"))
        telas += 1
        # O endereço de cada link à vista, depois do print da tela (o menu do Chrome não fica nele). O mesmo link visto
        # em duas telas seguidas é lido de novo e sai depois, pelo endereço.
        for texto, ponto in links_na_tela(tela):
            if toques >= TOQUES_LONGOS_POR_AULA or not _livre_para_tocar(tela, ponto):
                continue
            toques += 1
            achados.append((texto, endereco_do_link(d, ponto, pausa, guardar_o_caso_do_menu)))
        if abas_na_tela(tela):
            break
        anterior = atuais
        rolar_a_pagina(d)
        pausa(ESPERA_DA_ROLAGEM)
    if not textos and not documento and not slides:
        return {}, PAGINA_VAZIA
    abertos, porque = _abrir_os_links(d, pasta, achados, pausa, vigiar)
    if porque:
        return {}, porque
    with open(os.path.join(pasta, "texto.txt"), "w", encoding="utf-8") as saida:
        saida.write("\n".join(textos) + "\n")
        if links:
            saida.write("\nLinks da aula:\n" + "".join(f"- {link}\n" for link in links))
        if abertos:
            saida.write("\nO que cada link abriu (as telas em link_NN_tela_MM.jpg, os textos em link_NN.txt):\n")
            saida.write("".join(f"- {item['texto']}: {item['endereco'] or '(sem o endereço)'}; {resumo_do_link(item)}\n"
                                for item in abertos))
    if abertos:
        with open(os.path.join(pasta, "links.json"), "w", encoding="utf-8") as saida:
            json.dump(abertos, saida, ensure_ascii=False, indent=1)
    return {"telas": telas, "slides": slides or 0, "linhas": len(textos), "links": len(links),
            "links_abertos": sum(1 for item in abertos if item.get("telas")),
            "links_sem_endereco": sum(1 for item in abertos if item.get("problema") == SEM_O_MENU),
            "documento": documento}, ""


PAGINA_DA_VIDEOAULA = "página da videoaula"


def guardar_a_aula_sem_video(d, curso, numero, pausa=None, vigiar=None, agora=None, tipo=SEM_VIDEO):
    """
    A aula sem vídeo aberta no Chrome guardada na pasta das aulas, como as gravadas: as telas, o texto e o documento
    (_ler_a_aula), com o aula.json só de números. vigiar() renova o sinal ao robô e diz o porquê de parar no meio (""
    para seguir). Com tipo=PAGINA_DA_VIDEOAULA, é a página da aula em vídeo já gravada (o texto dela, com as instruções
    e os links, e o documento que ela tiver). (pasta, aula.json) ou (None, {"problema": o porquê}): a pasta pela metade
    sai.
    """
    pausa = pausa or time.sleep
    vigiar = vigiar or (lambda: "")
    momento = _agora(agora)
    pasta = os.path.join(PASTA_DAS_AULAS, f"{momento:%Y%m%d-%H%M%S}-c{int(curso):02d}-a{int(numero):03d}")
    os.makedirs(pasta, exist_ok=True)
    try:
        info, problema = _ler_a_aula(d, pasta, pausa, vigiar)
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    if problema:
        shutil.rmtree(pasta, ignore_errors=True)
        return None, {"problema": problema}
    info.update(curso=int(curso), aula=int(numero), gravada_em=_texto(momento), tipo=tipo, problema="")
    with open(os.path.join(pasta, "aula.json"), "w", encoding="utf-8") as saida:
        json.dump(info, saida, ensure_ascii=False, indent=1)
    return pasta, info


def descrever_a_aula_guardada(info):
    """
    A aula sem vídeo guardada em números, para o registro e o explorar: telas, slides (só na aula que tem), linhas,
    links e o documento.
    """
    documento = info.get("documento")
    if not documento:
        doc = "sem documento"
    elif documento.get("grande_demais"):
        doc = f"documento de {documento['bytes'] // 1024} KB, grande demais, só anotado"
    else:
        doc = f"documento de {documento['bytes'] // 1024} KB"
    slides = f"{info['slides']} slide(s), " if info.get("slides") else ""
    abertos = f" ({info['links_abertos']} aberto(s))" if info.get("links") else ""
    return (f"{info.get('telas', 0)} tela(s), {slides}{info.get('linhas', 0)} linha(s), {info.get('links', 0)} "
            f"link(s){abertos}, {doc}")


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
# A aula da vez só começa se cabe no resto da madrugada, com a duração da lista e a FOLGA_DA_AULA (abrir a aula antes e
# guardar a página dela depois, em segundos): a que para às 3h45 fica pela metade (P295 1), e o site guarda onde ela
# parou.
FOLGA_DA_AULA = 5 * 60
NAO_CABE = "a aula da vez não cabe no resto da madrugada"
MAIOR_QUE_A_MADRUGADA = "a aula da vez é mais longa que a madrugada inteira"


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


def _fim_da_madrugada(inicio):
    """O fim da madrugada da gravação, em minutos depois da 0h: o FIM_DA_NOITE ou o começo do robô, o que vem antes."""
    return min(int(inicio) * 60, FIM_DA_NOITE[0] * 60 + FIM_DA_NOITE[1])


def janela_da_madrugada(config):
    """Os minutos da madrugada da gravação inteira (na_madrugada): do fim do Horário do Robô ao fim dela."""
    inicio, fim = horario_do_robo(config.get("robo_inicio", 8), config.get("robo_fim", 22))
    if inicio <= 0 and fim >= 24:
        return 0
    return (24 * 60 - fim * 60 if fim < 24 else 0) + _fim_da_madrugada(inicio)


def resto_da_madrugada(config, agora=None):
    """Os segundos que faltam para a madrugada da gravação acabar (na_madrugada); 0 fora dela."""
    momento = _agora(agora)
    if not na_madrugada(config, momento):
        return 0
    inicio, fim = horario_do_robo(config.get("robo_inicio", 8), config.get("robo_fim", 22))
    segundos = momento.hour * 3600 + momento.minute * 60 + momento.second
    if segundos >= fim * 3600:
        return 24 * 3600 - segundos + _fim_da_madrugada(inicio) * 60
    return max(0, _fim_da_madrugada(inicio) * 60 - segundos)


def aula_fora_da_madrugada(duracao, config=None, agora=None):
    """
    Por que a aula da vez não começa agora ("" quando ela cabe): com a duração da lista (em segundos) e a FOLGA_DA_AULA,
    ela precisa caber no resto da madrugada (NAO_CABE; ela fica para a noite seguinte, a 1ª dela). A sem duração (um
    documento ou um texto) cabe sempre; a mais longa que a madrugada inteira para a noite com o porquê dela
    (MAIOR_QUE_A_MADRUGADA), para o Claude ver no relatório da manhã.
    """
    if not duracao:
        return ""
    config = config if config is not None else (db.ler_config("shopee_video", {}) or {})
    precisa = int(duracao) + FOLGA_DA_AULA
    if precisa > janela_da_madrugada(config) * 60:
        return MAIOR_QUE_A_MADRUGADA
    return "" if precisa <= resto_da_madrugada(config, agora) else NAO_CABE


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


def agora_em_texto(agora=None):
    """O momento no formato do sinal e do pedido: o começo de quem fica com o celular, para pediram_o_celular."""
    return _texto(_agora(agora))


def pediram_o_celular(desde, menos_de=""):
    """
    Alguém pediu o celular depois desse momento (o começo da aula, em texto)? menos_de: quem pediu e não conta (o
    explorar não cede o celular ao pedido de outro explorar, que espera a vez dele).
    """
    estado = estado_da_noite()
    return (estado.get("pedido_em") or "") >= desde and not (menos_de and estado.get("pedido_por") == menos_de)


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
        """Para a gravação e fecha o arquivo. (ok, motivo fixo). Parada antes (a gravação começada de novo), nada."""
        if self._saida.closed:
            return False, "o gravador já tinha parado"
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
        self.tocou, self.maior, self.parado_desde, self.primeira = False, 0, None, None

    def olhar(self, midia, segundos):
        """
        Com o estado do vídeo (midia_do_chrome) e o relógio em segundos: None enquanto a aula segue, ou o
        motivo fixo do fim ("o vídeo parou", "carregando demais", "outro vídeo começou").
        """
        if midia and midia["estado"] == "tocando":
            if self.tocou and midia["posicao"] + VOLTA_DE_OUTRO < self.maior:
                return "outro vídeo começou"
            if self.primeira is None:
                self.primeira = midia["posicao"]
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
NAO_TOCOU = "a aula não começou a tocar"
# Com a duração da lista das aulas: o vídeo que já começou adiantado (o site lembra onde a pessoa parou) ou que parou
# antes do fim não fica inteiro na gravação, e a aula volta numa noite seguinte. Do início, a 1ª posição lida não passa
# do tempo desde que a página começou a abrir (mais COMECO_TOLERADO s); no fim, a maior chega a FOLGA_DO_FIM s da
# duração.
COMECO_TOLERADO = 10
FOLGA_DO_FIM = 20
NAO_DO_INICIO = "o vídeo não começou do início"
ANTES_DO_FIM = "o vídeo parou antes do fim"


def no_video_pela_metade(fim):
    """O vídeo da aula não tocou do início ao fim (NAO_DO_INICIO ou ANTES_DO_FIM, com os segundos)?"""
    return fim.startswith((NAO_DO_INICIO, ANTES_DO_FIM))


def _madrugada_agora():
    return na_madrugada(db.ler_config("shopee_video", {}) or {})


def _gravar_de_novo(d, gravacao, alvo, destino, maximo, abrir, pausa):
    """
    A gravação começada de novo, com o vídeo da aula pausado no começo (voltar_ao_comeco): o celular fica mudo enquanto
    o gravador para e liga (sem ele gravando, o alto-falante toca), e o volume da aula volta só com o novo gravando.
    (gravação, "" ou o motivo fixo de não ter dado).
    """
    calar_o_celular(d)
    gravacao.parar()
    if os.path.exists(destino):
        os.remove(destino)
    gravacao = GravacaoEmFundo(alvo, destino, maximo, abrir=abrir)
    pausa(ESPERA_DO_GRAVADOR)
    if not gravacao.rodando():
        return gravacao, "o gravador não ficou gravando"
    if not subir_o_volume(d):
        return gravacao, "sem o volume de mídia"
    return gravacao, ""


def gravar_a_aula(d, alvo, destino, ir_para_a_aula, tocar, pausa=None, relogio=None, abrir=subprocess.Popen,
                  madrugada=None, maximo=AULA_MAIS_LONGA, duracao=None, na_aula_certa=None, reiniciar=None):
    """
    A aula aberta no Chrome do celular e gravada em destino, do começo ao fim. A ordem protege o quarto do Rafael
    (pedido dele, 22/11/2026): o gravador liga antes e, gravando o som, deixa o alto-falante mudo; o volume sobe só
    com ele gravando; a aula abre (ir_para_a_aula) já com o gravador ligado, porque o vídeo pode começar a tocar
    sozinho com a página (23/11/2026), e tocar(d) dá o play quando ele não começou; no fim, a aula pausa e o volume
    volta antes de o gravador parar. O robô que pede o celular, a madrugada que acaba (3h45) e o gravador que cai
    param a aula, que fica pela metade (P295 1: ela volta depois, do início). Devolve (aberta, inteira, motivo fixo):
    aberta diz se a página da aula abriu; na aula sem vídeo, (True, False, SEM_VIDEO). maximo: o tempo máximo da
    gravação, em segundos (o teste de dia grava menos que a noite). duracao: a da lista das aulas, em segundos; com ela,
    o vídeo que parou antes do fim fica pela metade, e o que não começou do início (o site lembra onde a aula parou)
    volta ao começo por reiniciar(d) (voltar_ao_comeco), uma vez, com a gravação começada de novo (_gravar_de_novo);
    sem reiniciar, ou se ele não voltou, a gravação para logo e a aula fica pela metade. na_aula_certa(d): com o vídeo
    tocando, a página ainda é a da aula da vez? Sem ela, a gravação para: o vídeo que toca é o de outra aula (pedido do
    Rafael de 24/11/2026: nunca achar que viu a aula sem tê-la visto).
    """
    pausa = pausa or time.sleep
    relogio = relogio or time.monotonic
    madrugada = madrugada or _madrugada_agora
    inicio = _texto(_agora())
    anotar_o_sinal()
    gravacao = GravacaoEmFundo(alvo, destino, maximo, abrir=abrir)
    try:
        pausa(ESPERA_DO_GRAVADOR)
        if not gravacao.rodando():
            return False, False, "o gravador não ficou gravando"
        if not subir_o_volume(d):
            return False, False, "sem o volume de mídia"
        aberta_em = relogio()
        tipo, porque = ir_para_a_aula(d)
        if not tipo:
            return False, False, porque if porque in PARADAS_DA_AULA else f"a aula não abriu ({porque})"
        if tipo == SEM_VIDEO:
            return True, False, SEM_VIDEO
        if not tocar(d):
            return True, False, NAO_TOCOU
        if na_aula_certa and not na_aula_certa(d):
            return True, False, OUTRA_PAGINA
        olho, comeco, comeco_conferido, reiniciada = OlhoNaAula(), relogio(), False, False
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
            if duracao and olho.primeira is not None and not comeco_conferido:
                # Do início, o vídeo não pode ter tocado mais que o tempo desde que a página da aula começou a abrir.
                comeco_conferido = True
                if olho.primeira > relogio() - aberta_em + COMECO_TOLERADO:
                    adiantada = f"{NAO_DO_INICIO} (em {olho.primeira} s de {duracao} s)"
                    if reiniciada or not reiniciar or not reiniciar(d):
                        return True, False, adiantada
                    # O vídeo está pausado no começo: a gravação começa de novo, sem o pedaço adiantado.
                    reiniciada = True
                    gravacao, porque = _gravar_de_novo(d, gravacao, alvo, destino, maximo, abrir, pausa)
                    if porque:
                        return True, False, porque
                    aberta_em = relogio()
                    if not tocar(d):
                        return True, False, NAO_TOCOU
                    olho, comeco, comeco_conferido = OlhoNaAula(), relogio(), False
                    continue
            if fim and fim != "carregando demais" and duracao and olho.maior + FOLGA_DO_FIM < duracao:
                return True, False, f"{ANTES_DO_FIM} (em {olho.maior} s de {duracao} s)"
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


def mapa_para_o_claude(mapa=None):
    """
    O mapa sem os endereços, para o pacote do Claude (mapa.json): os cursos na ordem, com a lista das aulas lida da aba
    Módulos (os módulos, os nomes e as durações), o que a noite já guardou de cada uma e o check do Claude. É de onde
    sai a lista das aulas com o check de cada uma, no relatório da manhã (pedido do Rafael de 24/11/2026).
    """
    mapa = mapa or mapa_das_aulas()
    cursos = {}
    for posicao in ORDEM_DOS_CURSOS:
        curso = mapa["cursos"].get(str(posicao)) or {}
        cursos[str(posicao)] = {"lista": curso.get("lista") or [], "lista_em": curso.get("lista_em", "")}
        if curso.get("lista_sem_bater"):
            cursos[str(posicao)]["lista_sem_bater"] = curso["lista_sem_bater"]
    return {"ordem": list(ORDEM_DOS_CURSOS), "cursos": cursos}


def tem_lista(mapa=None):
    """
    Algum curso já tem a lista das aulas no mapa, ou a cópia da que não bateu com o site (o exportar leva o mapa ao
    Claude mesmo sem aula guardada)?
    """
    mapa = mapa or mapa_das_aulas()
    return any((curso or {}).get("lista") or (curso or {}).get("lista_sem_bater") for curso in mapa["cursos"].values())


def pacote_das_aulas(ate=None):
    """O zip das aulas do próximo pacote, em bytes, com o mapa sem os endereços (mapa.json)."""
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as arquivo_zip:
        arquivo_zip.writestr("mapa.json", json.dumps(mapa_para_o_claude(), ensure_ascii=False, indent=1))
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
VOLTAS_DA_NOITE = 200
# O que para a aula sem ser falha: ela volta depois, inteira (P295 1), e a noite acaba aqui.
PARADAS_DA_AULA = ("o robô pediu o celular", "a madrugada acabou")
SEM_O_MUDO = "o celular não ficou mudo antes de abrir a aula"
# A tela sempre em pé (P301 2, 26/11/2026; DECISOES.md, Trabalho com o Claude): deitada, a página da aula não mostra a
# lista de aulas. Posta em pé, o Chrome leva um instante para desenhar a página de novo.
PROCESSO_DA_TELA = "tela do celular"
SEM_A_TELA_EM_PE = "a tela do celular não ficou em pé"
ESPERA_DA_TELA_EM_PE = 2


def guardar_o_caso(d, motivo, resultado="não abriu", passo="abrir a aula"):
    """
    A tela da 1ª aula da noite que não abriu (o print, a forma da tela e o log do Chrome), guardada para o Claude
    achar o porquê, e a da 1ª aula sem vídeo, para ele conferir que era mesmo um documento ou um texto (casos_robo:
    cifrada no exportar, nunca no repositório); também a da lista das aulas que não foi lida (curso:lista:N).
    """
    import casos_robo
    return casos_robo.guardar(d, "curso", resultado, motivo, passo=passo)


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
            arquivo, posicao, numero, fim = item
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
                desmarcar_a_aula(posicao, numero)
                registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, "não serviu",
                                             f"{qual_aula(posicao, numero)}: {info['problema']}", ok=False)
            else:
                self.guardadas += 1
                registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, "guardada",
                                             qual_aula(posicao, numero), ok=True)

    def mandar(self, arquivo, posicao, numero, fim):
        """A aula gravada vai para a fila; o .json ao lado do vídeo deixa a noite seguinte ler a que ficou na fila."""
        with open(arquivo + ".json", "w", encoding="utf-8") as saida:
            json.dump({"posicao": posicao, "numero": numero, "fim": fim}, saida)
        self.fila.put((arquivo, posicao, numero, fim))

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
            self.fila.put((caminho, dados["posicao"], dados["numero"], dados["fim"]))
            voltaram += 1
        return voltaram

    def acabar(self):
        """Espera as aulas da fila serem lidas."""
        self.fila.put(None)
        self._linha.join()


# No fim do vídeo, o site pode passar sozinho para a aula seguinte (o teste de dia de 23/11/2026, às 23:06; na noite de
# 24/11/2026, em quase todas as videoaulas): a página da aula gravada só é guardada com ela na tela. Saída dela, a aula
# volta pela lista (o toque no nome dela, com a página subindo até o alto), muda e pausada, e a página é guardada.
SAIU_DA_AULA = "o site passou sozinho para outra aula no fim do vídeo"


def _voltar_para_a_aula(d, posicao, numero, pausa, vigiar=None):
    """A aula `numero`, que a página deixou, de novo na tela pela lista, no alto e pausada. (ok, porque)."""
    ok, porque = abrir_pela_lista(d, posicao, numero, pausa, no_curso=True, vigiar=vigiar)
    pausar_o_que_toca(d, pausa)
    if not ok:
        return False, porque
    if not subir_ate_o_alto(d, lista_do_curso(posicao)[int(numero) - 1], pausa):
        return False, SEM_O_ALTO
    pausar_o_que_toca(d, pausa)
    return True, ""


def _guardar_a_pagina_da_videoaula(d, posicao, numero, pausa, vigiar):
    """
    Depois da videoaula gravada inteira, a página dela também vai ao Claude: o texto com as instruções e os links, e o
    documento que ela tiver (pedidos do Rafael de 23/11/2026, às 08:44 e às 09:12). A página que o site deixou volta
    pela lista (_voltar_para_a_aula). Sem ela, a aula gravada vale do mesmo jeito, e o registro diz o porquê (a
    videoaula sem nada escrito embaixo do vídeo não vai ao registro). Devolve (o porquê de a noite parar, "o robô pediu
    o celular" ou "a madrugada acabou", ou "", a aula na tela agora ou None). O Chrome fica em pé antes (chrome_em_pe):
    o aberto de novo recarrega a guia, e a aula na tela é conferida do mesmo jeito.
    """
    chrome_em_pe(d, pausa)
    if not na_aula(d, posicao, numero, pausa):
        ok, porque = _voltar_para_a_aula(d, posicao, numero, pausa, vigiar)
        if porque in PARADAS_DA_AULA:
            return porque, None
        if not ok:
            registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, "página não guardada",
                                         f"{qual_aula(posicao, numero)}: {SAIU_DA_AULA} ({porque})", ok=None)
            return "", None
    pasta, info = guardar_a_aula_sem_video(d, posicao, numero, pausa, vigiar, tipo=PAGINA_DA_VIDEOAULA)
    if pasta:
        registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, "página guardada",
                                     f"{qual_aula(posicao, numero)}: {descrever_a_aula_guardada(info)}", ok=True)
        return "", (posicao, numero)
    if info["problema"] in PARADAS_DA_AULA:
        return info["problema"], None
    if info["problema"] != PAGINA_VAZIA:
        registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, "página não guardada",
                                     f"{qual_aula(posicao, numero)}: {info['problema']}", ok=None)
    return "", (posicao, numero) if na_aula(d, posicao, numero, pausa) else None


def _aula_de_antes_na_tela(d, posicao, numero, aberta, pausa, vigiar=None):
    """
    Antes da gravação, com o celular mudo e sem o gravador: a da vez (da 2ª em diante) abre pelo Próximo da de antes,
    que vem pela lista quando a página não é ela; a 1ª do curso, pela lista de uma aula do curso, que vem pelo endereço
    guardado (o login que a sessão vencida pede fica fora da gravação). aberta: a aula na tela, (posição, número), ou
    (posição, None) numa aula do curso de número que a noite não sabe. Devolve (a aula na tela ou None, o porquê).
    """
    if numero == 1:
        if aberta and aberta[0] == posicao:
            return aberta, ""
        tipo, porque = ir_para_o_endereco(d, endereco_do_curso(posicao), pausa)
        pausar_o_que_toca(d, pausa)
        return ((posicao, None), "") if tipo else (None, porque)
    if aberta == (posicao, numero - 1) and na_aula(d, posicao, numero - 1, pausa):
        return aberta, ""
    ok, porque = abrir_pela_lista(d, posicao, numero - 1, pausa, no_curso=bool(aberta) and aberta[0] == posicao,
                                  vigiar=vigiar)
    pausar_o_que_toca(d, pausa)
    return ((posicao, numero - 1), "") if ok else (None, porque)


def noite(conectar=None, pausa=None, ajudante=None, trava=None, conectado=None):
    """
    A gravação de uma madrugada (P289 1 a P295 1): as aulas da vez, uma a uma, na ordem da lista de cada curso, da 1ª à
    última, curso por curso (pedido do Rafael de 24/11/2026), até a madrugada acabar, o disco encher, o robô pedir o
    celular, a aula da vez não caber no resto da madrugada (aula_fora_da_madrugada: ela é a 1ª da noite seguinte) ou
    acabarem as aulas. A aula da vez abre já com o gravador gravando, para o vídeo que começa sozinho ficar
    inteiro (abrir_a_aula_da_vez): pelo Próximo da de antes, que vem antes pela lista, muda, quando não está na tela,
    ou, na 1ª do curso, pelo toque no nome dela na lista. A gravação que não chega ao fim da duração da lista fica pela
    metade. A aula sem vídeo (um documento ou um texto) é guardada com a página e o documento
    (guardar_a_aula_sem_video); da videoaula gravada inteira, a página também é guardada, com o celular mudo
    (_guardar_a_pagina_da_videoaula). A que não fica guardada volta na noite seguinte, e a noite segue para a próxima:
    nenhuma aula é pulada. Devolve o que aconteceu numa frase só com números (vai ao log).
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
    aberta, pular, com_caso, voltas = None, set(), False, 0
    try:
        while True:
            voltas += 1
            if voltas > VOLTAS_DA_NOITE:
                # Nenhuma noite grava tantas aulas: o site fez a noite girar sem sair do lugar.
                motivo = f"a noite passou de {VOLTAS_DA_NOITE} voltas"
                break
            if ajudante.problema:
                motivo = ajudante.problema
                break
            if not _madrugada_agora():
                motivo = "a madrugada acabou"
                break
            if disco_usado() >= LIMITE_DO_DISCO:
                motivo = f"o disco passou de {LIMITE_DO_DISCO}%"
                break
            da_vez = proxima_aula(pular=pular)
            if not da_vez:
                sem_lista = curso_sem_a_lista()
                motivo = f"o curso {sem_lista} sem a lista das aulas" if sem_lista else "nenhuma aula por gravar"
                break
            if not conectado():
                motivo = "o celular desconectado"
                break
            posicao, numero = da_vez
            fora = aula_fora_da_madrugada(lista_do_curso(posicao)[numero - 1].get("segundos"))
            if fora:
                motivo = fora
                break
            guardada, inteira, aberta_na_gravacao, fim, destino, info = False, False, False, "", "", {}
            parar_depois = ""
            with trava() as livre:
                if not livre:
                    motivo = "o celular com o robô"
                    break
                anotar_o_sinal()
                d = conectar()
                em_pe = celular_robo.deixar_a_tela_em_pe(d)
                if em_pe == celular_robo.NAO_FICOU_EM_PE:
                    motivo = SEM_A_TELA_EM_PE
                    break
                if em_pe == celular_robo.POSTA_EM_PE:
                    registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_TELA, "posta em pé",
                                                 "rotação automática desligada", ok=True)
                    pausa(ESPERA_DA_TELA_EM_PE)
                chrome = chrome_em_pe(d, pausa)
                if chrome == CHROME_DEITADO:
                    motivo = CHROME_DEITADO
                    break
                if chrome == CHROME_REABERTO:
                    # O Chrome aberto de novo recarrega a guia, e o site abre a aula em que parou: a aula na tela é
                    # conferida de novo, pelo caminho de sempre.
                    aberta = None
                # O vídeo da aula pode começar a tocar sozinho quando a página abre: o celular fica mudo até o gravador
                # ligar, e então o som vai só ao servidor (o celular fica no quarto do Rafael, pedido dele de
                # 22/11/2026: DECISOES.md, Trabalho com o Claude).
                if not calar_o_celular(d):
                    motivo = SEM_O_MUDO
                    break
                inicio = _texto(_agora())

                def vigiar():
                    anotar_o_sinal()
                    if pediram_o_celular(inicio):
                        return "o robô pediu o celular"
                    return "" if _madrugada_agora() else "a madrugada acabou"
                aberta, porque = _aula_de_antes_na_tela(d, posicao, numero, aberta, pausa, vigiar)
                if not aberta:
                    fim = porque if porque in PARADAS_DA_AULA else f"a aula não abriu ({porque})"
                else:
                    destino = os.path.join(PASTA_DAS_GRAVACOES, f"{_agora():%Y%m%d-%H%M%S}.mkv")
                    aberta_na_gravacao, inteira, fim = gravar_a_aula(
                        d, getattr(d, "serial", ""), destino,
                        lambda celular: abrir_a_aula_da_vez(celular, posicao, numero, pausa, vigiar),
                        lambda celular: tocar_pelo_play(celular, pausa), pausa=pausa,
                        duracao=lista_do_curso(posicao)[numero - 1].get("segundos"),
                        na_aula_certa=lambda celular: na_aula(celular, posicao, numero, pausa),
                        reiniciar=lambda celular: voltar_ao_comeco(celular, pausa))
                    aberta = (posicao, numero) if aberta_na_gravacao else None
                    if inteira and calar_o_celular(d):
                        # A página da videoaula (o texto, os links e o documento), com o vídeo já pausado e mudo.
                        parar_depois, aberta = _guardar_a_pagina_da_videoaula(d, posicao, numero, pausa, vigiar)
                    if fim == SEM_VIDEO and not calar_o_celular(d):
                        fim = SEM_O_MUDO
                    elif fim == SEM_VIDEO:
                        pasta, info = guardar_a_aula_sem_video(d, posicao, numero, pausa, vigiar)
                        guardada, fim = bool(pasta), (SEM_VIDEO if pasta else info["problema"])
                        if not pasta:
                            # A página pode ter saído da tela (o Baixar que abriu o documento): a próxima vez, a noite
                            # volta pela lista.
                            aberta = None
                if not inteira and not guardada and fim not in PARADAS_DA_AULA and not com_caso:
                    guardar_o_caso(d, fim, "não guardada" if aberta_na_gravacao else "não abriu")
                    com_caso = True
            if inteira:
                # Marcada já: a seguinte vem pelo Próximo dela, enquanto o ajudante lê esta.
                anotar_a_aula_gravada(posicao, numero)
                gravadas += 1
                falhas = 0
                ajudante.mandar(destino, posicao, numero, fim)
                if parar_depois:
                    motivo = parar_depois
                    break
                continue
            if destino and os.path.exists(destino):
                os.remove(destino)
            if guardada:
                # Um documento ou um texto, guardado com a página (pedidos do Rafael de 23/11/2026:
                # DECISOES.md, Trabalho com o Claude).
                anotar_a_aula_gravada(posicao, numero, sem_video=True)
                sem_video += 1
                falhas = 0
                registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, "guardada sem vídeo",
                                             f"{qual_aula(posicao, numero)}: {descrever_a_aula_guardada(info)}",
                                             ok=True)
                continue
            if fim == SEM_O_MUDO:
                motivo = fim
                break
            if aberta_na_gravacao and info:
                resultado = "não guardada"
                pular.add((posicao, numero))
            else:
                resultado = "pela metade" if aberta_na_gravacao else "não abriu"
                if fim == OUTRA_PAGINA or no_video_pela_metade(fim):
                    # O vídeo que não toca do início ao fim (ou que não é o da aula) fica para a noite seguinte, e a
                    # noite segue.
                    pular.add((posicao, numero))
            registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, resultado,
                                         f"{qual_aula(posicao, numero)}: {fim}",
                                         ok=None if fim in PARADAS_DA_AULA else False)
            if resultado == "pela metade":
                metade += 1
            if fim in PARADAS_DA_AULA:
                motivo = fim
                break
            if fim.startswith(NAO_DO_INICIO):
                # O site guarda onde a aula parou, e o Reiniciar do player não a voltou ao começo: não é falha do
                # caminho, e a noite segue (o registro diz em que segundo o vídeo começou).
                continue
            falhas += 1
            if falhas >= FALHAS_SEGUIDAS:
                motivo = fim
                break
    finally:
        soltar_o_sinal()
        ajudante.acabar()
    resumo = (f"{gravadas} aula(s) gravada(s), {ajudante.guardadas} guardada(s), {metade} pela metade, "
              f"{sem_video} sem vídeo guardada(s); parou: {ajudante.problema or motivo}")
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
    if os.path.exists(os.path.join(destino, "mapa.json")):
        print("   mapa.json (a lista das aulas de cada curso e o que a noite já guardou)")
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
    if argumentos == ["tem-lista"]:
        print(1 if tem_lista() else 0)
        return 0
    if argumentos[:1] == ["cifrado"] and len(argumentos) <= 2:
        print(cifrado_das_aulas(argumentos[1] if len(argumentos) == 2 else None))
        return 0
    if argumentos[:1] == ["apagar"] and len(argumentos) == 2 and NOME_DA_AULA.fullmatch(argumentos[1]):
        print(f"{apagar_aulas(argumentos[1])} aula(s) apagada(s) do servidor.")
        return 0
    if argumentos[:1] == ["ler"] and len(argumentos) == 3:
        return _ler_aulas(argumentos[1], argumentos[2])
    if argumentos[:1] in (["vistas"], ["refazer"]) and len(argumentos) == 2:
        return _conferir(argumentos[1], vistas=argumentos[0] == "vistas")
    print("uso: cursos_robo.py aulas contar | ultima | tem-lista | cifrado [ATE] | apagar ATE | ler ARQUIVO PASTA | "
          "vistas AULAS | refazer AULAS (AULAS: 4:15,16;5:2-35)")
    return 2


def _conferir(texto, vistas):
    """
    A conferência do Claude pelo cursos_robo.yml (conferir ou refazer): as aulas pelos números da lista de cada curso
    (numeros_das_aulas), marcadas como vistas (o check) ou para a noite gravar de novo. O log diz só números.
    """
    try:
        cursos = numeros_das_aulas(texto)
    except ValueError:
        print("As aulas vão como CURSO:AULAS, separados por ponto e vírgula (ex.: 4:15,16;5:2-35).")
        return 2
    if not cursos:
        print("Nenhuma aula pedida.")
        return 2
    mapa = mapa_das_aulas()
    for posicao in sorted(cursos):
        tamanho = len(lista_do_curso(posicao, mapa))
        fora = sorted(numero for numero in cursos[posicao] if numero > tamanho)
        if fora:
            print(f"O curso {posicao} tem {tamanho} aula(s) na lista: a {fora[0]} não existe. Nada mudou.")
            return 2
    for posicao in sorted(cursos):
        mudadas = conferir_as_aulas(posicao, cursos[posicao], vistas=vistas)
        feito = "marcada(s) como vista(s)" if vistas else "para a noite gravar de novo"
        print(f"curso {posicao}: {mudadas} aula(s) {feito}")
    print(resumo_do_mapa())
    return 0


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

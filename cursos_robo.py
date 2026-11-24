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


def _abrir_pela_barra(d, endereco, pausa):
    """Uma vez: o endereço escrito na barra da guia da frente e a página nova esperada. (tipo, porque, a tela)."""
    trazer_o_chrome(d, pausa)
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
    d.click(*_centro(barra["caixa"]))
    pausa(1)
    if not escrever_na_barra(d, endereco, pausa):
        # Sem o Enter: a barra sai da edição, e a página de antes fica como estava.
        d.press("back")
        return None, SEM_A_ESCRITA, tela
    _saida(d, ["input", "keyevent", "KEYCODE_ENTER"])
    tela = ""
    for _ in range(ESPERA_DA_PAGINA // PASSO_DA_ESPERA):
        pausa(PASSO_DA_ESPERA)
        tela = _fechar_a_folha_do_chrome(d, pausa)
        if endereco_da_aula(tela) == endereco and (botao_do_play(tela) or _tocando_ou_carregando(midia_do_chrome(d))):
            return COM_VIDEO, "", tela
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
    logado = False
    for _ in range(VEZES_NA_BARRA):
        tipo, porque, tela = _abrir_pela_barra(d, endereco, pausa)
        if tipo or porque != SEM_O_ENDERECO:
            return tipo, porque
        if campos_do_login(tela):
            if logado or not entrar(d, pausa)[0]:
                return None, SEM_O_LOGIN
            logado = True
        elif not _mesmo_site(texto_da_barra(tela), endereco):
            return None, SEM_O_ENDERECO
    return None, SEM_O_ENDERECO


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


def na_aula_certa(d, posicao, numero, nome):
    """
    A página é a aula `numero` do curso? O Próximo dela mostra o nome da aula seguinte: o nome de uma aula até a
    `numero` (a dela, `nome`, ou uma das de antes, do mapa) quer dizer que a página voltou para uma aula de antes, e a
    noite não pode gravar de novo uma aula como se fosse a seguinte.
    """
    aulas = (mapa_das_aulas()["cursos"].get(str(posicao)) or {}).get("aulas") or []
    conhecidos = {aula.get("nome") for aula in aulas[1:int(numero) - 1] if aula.get("nome")} | {nome}
    return nome_no_proximo(d.dump_hierarchy()) not in conhecidos


def chegar_na_aula(d, posicao, numero, pausa=None, vigiar=None):
    """
    A aula `numero` do curso aberta, muda e sem o gravador: a 1ª pelo endereço guardado (com o login que a sessão
    vencida pede) e as outras pelo Próximo, uma a uma, com o que começar a tocar pausado. Cada aula achada pelo Próximo
    fica no mapa, com o nome dela. vigiar(), a cada aula, renova o sinal ao robô e diz o porquê de parar ("" para
    seguir): o caminho até uma aula do fim do curso leva minutos, e o robô tem a preferência no celular (22/11/2026).
    (tipo da aula, "") ou (None, o porquê).
    """
    pausa = pausa or time.sleep
    vigiar = vigiar or (lambda: "")
    aulas = (mapa_das_aulas()["cursos"].get(str(posicao)) or {}).get("aulas") or []
    if not aulas:
        return None, f"o curso {posicao} ainda não tem a 1ª aula no mapa"
    tipo, porque = ir_para_o_endereco(d, aulas[0]["endereco"], pausa)
    for seguinte in range(2, int(numero) + 1):
        if not tipo:
            break
        parar = vigiar()
        if parar:
            return None, parar
        pausar_o_que_toca(d, pausa)
        tipo, porque, nome = passar_para_a_seguinte(d, pausa)
        if tipo and not na_aula_certa(d, posicao, seguinte, nome):
            tipo, porque = None, VOLTOU
        if tipo:
            anotar_a_aula_seguinte(posicao, seguinte, nome)
    pausar_o_que_toca(d, pausa)
    return tipo, porque


# --- O mapa das aulas (P293 1), só no banco do servidor ---
# Os 7 cursos da turma do Rafael pela posição na lista de Turmas do site (Continuar aprendendo → Turmas): primeiro os
# dois de Shopee Vídeo, depois os outros na ordem da lista e, por último, o dos encontros ao vivo (P293 1). Os nomes dos
# cursos não vão ao repositório. A 1ª aula de cada curso é guardada pelo Claude, com o passo curso:primeira:N do
# explorar na página dela, com o endereço; as outras vêm uma a uma pelo "Próximo" do site, que troca a aula sem trocar o
# endereço da barra (o teste de 23/11/2026): cada uma fica no mapa pelo número, na ordem do curso, com o nome que o
# Próximo mostra.
ORDEM_DOS_CURSOS = (4, 5, 1, 2, 6, 7, 3)
CHAVE_DO_MAPA = "curso_mapa"


def mapa_das_aulas():
    """
    {"cursos": {"posição": {"aulas": [{"endereco", "nome", "gravada_em", "sem_video"?}], "fim": bool}}} do banco: a
    aula N é a aulas[N - 1], e só a 1ª tem o endereço. A aula sem vídeo (um documento ou um texto) guardada tem a hora
    em sem_video.
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


def proxima_aula(mapa=None, pular=()):
    """
    A aula da vez, na ordem dos cursos: (posição, número) da 1ª aula ainda não guardada do curso (a que ficou pela
    metade volta inteira, do início: P295 1), ou o número depois da última conhecida, que vem pelo Próximo dela. As de
    `pular` ((posição, número), as que não foram guardadas nesta noite) ficam para a noite seguinte: nenhuma aula é
    pulada. Pula o curso terminado sem aula por guardar e o que ainda não tem a 1ª aula guardada. None sem nada a
    gravar.
    """
    mapa = mapa or mapa_das_aulas()
    for posicao in ORDEM_DOS_CURSOS:
        curso = mapa["cursos"].get(str(posicao)) or {}
        aulas = curso.get("aulas") or []
        if not aulas:
            continue
        falta = next((numero for numero, aula in enumerate(aulas, 1)
                      if not aula.get("gravada_em") and (posicao, numero) not in pular), None)
        if falta:
            return posicao, falta
        if not curso.get("fim"):
            return posicao, len(aulas) + 1
    return None


def _a_aula(curso, numero, mudar):
    """Muda a aula `numero` do curso (a aulas[numero - 1]), se ela está no mapa."""
    if 1 <= int(numero) <= len(curso["aulas"]):
        mudar(curso["aulas"][int(numero) - 1])


def anotar_a_aula_gravada(posicao, numero, agora=None, sem_video=False):
    """
    A aula do curso guardada inteira (gravada ou, sem vídeo, com a página e o documento): a próxima vez, a seguinte.
    """
    momento = _texto(_agora(agora))

    def marcar(aula):
        aula["gravada_em"] = momento
        if sem_video:
            aula["sem_video"] = momento
    _mudar_o_curso(posicao, lambda curso: _a_aula(curso, numero, marcar))


def desmarcar_a_aula(posicao, numero):
    """A aula gravada que não serviu (preta ou muda) volta a ficar por gravar."""
    _mudar_o_curso(posicao, lambda curso: _a_aula(curso, numero, lambda aula: aula.update(gravada_em="")))


def anotar_a_aula_seguinte(posicao, numero, nome):
    """
    A aula que o "Próximo" abriu, pelo número dela no curso: a que vem depois da última conhecida entra no fim da lista;
    a conhecida ganha o nome, se ainda não tinha.
    """
    def mudar(curso):
        if int(numero) == len(curso["aulas"]) + 1:
            curso["aulas"].append({"endereco": "", "nome": nome, "gravada_em": ""})
        else:
            _a_aula(curso, numero, lambda aula: aula.update(nome=aula.get("nome") or nome))
    _mudar_o_curso(posicao, mudar)


def anotar_o_fim_do_curso(posicao):
    """A última aula do curso (sem o "Próximo") chegou: o curso terminou."""
    _mudar_o_curso(posicao, lambda curso: curso.update(fim=True))


def resumo_do_mapa(mapa=None):
    """O mapa só em números, curso a curso na ordem: as aulas conhecidas, as guardadas e se o curso terminou."""
    mapa = mapa or mapa_das_aulas()
    partes = []
    for posicao in ORDEM_DOS_CURSOS:
        curso = mapa["cursos"].get(str(posicao)) or {}
        aulas = curso.get("aulas") or []
        gravadas = sum(1 for aula in aulas if aula.get("gravada_em"))
        sem_video = sum(1 for aula in aulas if aula.get("gravada_em") and aula.get("sem_video"))
        sem = f", {sem_video} sem vídeo" if sem_video else ""
        if curso.get("fim") and gravadas == len(aulas):
            partes.append(f"curso {posicao}: terminado ({gravadas} aulas{sem})")
        elif aulas:
            fim = ", sem mais aulas depois delas" if curso.get("fim") else ""
            partes.append(f"curso {posicao}: {gravadas} de {len(aulas)} aula(s) conhecida(s) gravada(s){sem}{fim}")
        else:
            partes.append(f"curso {posicao}: sem a 1ª aula")
    return "; ".join(partes)


# --- A lista das aulas, pela aba Módulos (pedido do Rafael de 24/11/2026, às 00:17) ---
# O endereço guardado de cada curso abre a aula em que o site parou (a 1ª ainda não vista), e não a 1ª do curso: na
# noite de 24/11/2026, o curso 4 abriu na 15ª aula (as de antes o Rafael viu à mão) e o 5 na 2ª (a 1ª, o teste de dia
# viu). A lista inteira, na ordem, vem da aba Módulos: cada módulo é um botão ("N% Nome do módulo"), e o aberto mostra
# embaixo uma linha por aula, mais à direita ("Nome 7:28"; a aula sem vídeo pode vir sem a duração). O Claude a lê de
# dia, com o celular mudo, pelo passo curso:lista:N do explorar, e ela fica no mapa (só no banco do servidor), com os
# módulos na ordem e as aulas na ordem de cada um: é a lista das aulas com o check de cada uma que o Rafael pediu. Só
# os botões dos módulos são tocados, e a página só rola para baixo (o dedo para cima): no alto dela, o arrasto para
# baixo recarregaria a página.
ID_DA_LISTA = "-content-modules"
MODULO_DA_LISTA = re.compile(r"\d{1,3}%\s+(?P<nome>.*\S)")
# O botão baixo demais está cortado pela beira da tela (ou embaixo da barra do Próximo): não é tocado.
ALTURA_DO_BOTAO = 60
# Embaixo do módulo aberto vem a 1ª aula dele: sem esse espaço à vista, a lista rola antes de saber se ele está aberto.
ESPACO_DA_AULA = 160
VOLTAS_DA_LISTA = 150
ESPERA_DO_MODULO = 1.5
SEM_A_LISTA = "a aba Módulos não apareceu na tela"
LISTA_SEM_O_COMECO = "o começo da lista ficou fora da tela"
LISTA_PELA_METADE = "a lista das aulas não chegou ao fim"
MODULO_SEM_TOQUE = "o botão de um módulo ficou fora do alcance"


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
    itens = []
    for no in _nos(ET.tostring(lista, encoding="unicode")):
        texto = " ".join(no["texto"].split())
        if not no["clicavel"] or no["classe"] != "Button" or not texto or texto.startswith(ROTULO_DO_PROXIMO):
            continue
        modulo = MODULO_DA_LISTA.fullmatch(texto)
        if no["id"] and modulo:
            itens.append({"tipo": "módulo", "nome": modulo["nome"], "segundos": None, "caixa": no["caixa"]})
        elif not no["id"] and not modulo:
            linha = LINHA_DA_AULA.fullmatch(texto)
            itens.append({"tipo": "aula", "nome": linha["nome"] if linha else texto,
                          "segundos": segundos_do_tempo(linha["tempo"]) if linha else None, "caixa": no["caixa"]})
    return tuple(map(int, caixa.groups())), sorted(itens, key=lambda item: item["caixa"][1])


def _tocavel(tela, caixa):
    """O botão está inteiro na tela, acima da barra do Próximo e longe da bolha do chat e da barra do Chrome?"""
    return (caixa[3] - caixa[1] >= ALTURA_DO_BOTAO and caixa[3] < _topo_do_proximo(tela)
            and _livre_para_tocar(tela, _centro(caixa)))


def _juntar_as_aulas(lidas, vistas):
    """As aulas do módulo vistas nesta tela depois das já lidas, sem repetir o pedaço que as duas leituras mostram."""
    for tamanho in range(min(len(lidas), len(vistas)), 0, -1):
        if lidas[-tamanho:] == vistas[:tamanho]:
            return lidas + vistas[tamanho:]
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
                vistas.append((item["nome"], item["segundos"]))
            continue
        if lido and item["nome"] == lido["nome"]:
            dono = lido
        elif item["nome"] in nomes:
            dono = None
        else:
            abaixo = itens[numero + 1] if numero + 1 < len(itens) else None
            return vistas, item, abaixo
    return vistas, None, None


def ler_a_lista(d, pausa=None):
    """
    A lista das aulas do curso aberto no Chrome, pela aba Módulos: ([{"modulo", "nome", "segundos"}], "") com os
    módulos na ordem e as aulas na ordem de cada um, ou (None, o porquê). Cada módulo fechado é aberto pelo botão dele
    (um toque só: o que não mostra aula nenhuma fica vazio), e a página rola só para baixo, até o fim dela.
    """
    pausa = pausa or time.sleep
    modulos, tocados, antes, sem_a_lista, aba_tocada = [], set(), None, 0, False
    for _ in range(VOLTAS_DA_LISTA):
        tela = _fechar_a_folha_do_chrome(d, pausa)
        achado = itens_da_lista(tela)
        if not achado or not achado[1]:
            aba = next((no for no in _nos(tela) if no["id"].endswith(ID_DAS_ABAS) and no["clicavel"]), None)
            if (not achado and not aba_tocada and aba and _tocavel(tela, aba["caixa"])
                    and aba["caixa"][3] + ESPACO_DA_AULA < _topo_do_proximo(tela)):
                # A aba Módulos à vista, com lugar embaixo dela, e a lista nada: outra aba está aberta.
                d.click(*_centro(aba["caixa"]))
                aba_tocada = True
                pausa(ESPERA_DO_MODULO)
                continue
            sem_a_lista += 1
            if sem_a_lista > TELAS_DA_AULA:
                return None, SEM_A_LISTA
            rolar_a_pagina(d)
            pausa(ESPERA_DA_ROLAGEM)
            continue
        caixa, itens = achado
        topo = next((no["caixa"][1] for no in _nos(tela) if no["classe"] == "WebView"), 0)
        if not modulos and (itens[0]["tipo"] != "módulo" or caixa[1] <= topo):
            # A lista que já começa cortada no alto da página: o começo dela passou, e a página não volta para cima.
            return None, LISTA_SEM_O_COMECO
        vistas, novo, abaixo = _uma_olhada_na_lista(itens, modulos)
        if modulos:
            modulos[-1]["aulas"] = _juntar_as_aulas(modulos[-1]["aulas"], vistas)
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
            if espaco and _tocavel(tela, novo["caixa"]):
                d.click(*_centro(novo["caixa"]))
                tocados.add(novo["nome"])
                pausa(ESPERA_DO_MODULO)
                continue
        marca = [(item["tipo"], item["nome"], item["caixa"]) for item in itens]
        if marca == antes:
            # A página não rolou mais: o fim dela.
            if novo:
                return None, MODULO_SEM_TOQUE
            aulas = [{"modulo": modulo["nome"], "nome": nome, "segundos": segundos}
                     for modulo in modulos for nome, segundos in modulo["aulas"]]
            return (aulas, "") if aulas else (None, LISTA_PELA_METADE)
        antes = marca
        rolar_a_pagina(d)
        pausa(ESPERA_DA_ROLAGEM)
    return None, LISTA_PELA_METADE


def guardar_a_lista(posicao, lista, agora=None):
    """A lista das aulas do curso dessa posição, lida da aba Módulos, no mapa (só no banco do servidor)."""
    momento = _texto(_agora(agora))

    def mudar(curso):
        curso["lista"] = [{"modulo": aula["modulo"], "nome": aula["nome"], "segundos": aula["segundos"]}
                          for aula in lista]
        curso["lista_em"] = momento
    _mudar_o_curso(posicao, mudar)


def descrever_a_lista(posicao, lista):
    """A lista lida, só em números (o log do explorar é público)."""
    modulos = len({aula["modulo"] for aula in lista})
    com = [aula["segundos"] for aula in lista if aula["segundos"]]
    return (f"lista do curso {posicao}: {modulos} módulo(s) com aula, {len(lista)} aula(s), {len(com)} com a duração "
            f"({sum(com) // 60} min de vídeo) e {len(lista) - len(com)} sem")


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


def _gravar_no_explorar(d, posicao, pausa):
    """
    O passo curso:gravar:N, o teste de dia da gravação da noite: a 1ª aula do curso N abre antes, muda e sem o
    gravador (o login que a sessão vencida pede fica fora da gravação), e de novo pelo endereço com o gravador já
    gravando, como a noite abre; gravada até o fim, no máximo GRAVACAO_DO_TESTE s, e guardada como a aula 0 do curso 0,
    com a fala e as folhas de quadros. O som da aula vai só ao servidor, e antes e depois o celular fica mudo; o robô
    que pede o celular para o teste, como para a noite, e a gravação sai sem ser lida. De madrugada, quem grava é a
    noite. O log diz só números e palavras fixas.
    """
    if _madrugada_agora():
        return False, "de madrugada, quem grava as aulas é a noite"
    aulas = (mapa_das_aulas()["cursos"].get(str(posicao)) or {}).get("aulas") or []
    if not aulas:
        return False, f"o curso {posicao} ainda não tem a 1ª aula no mapa"
    tipo, porque = chegar_na_aula(d, posicao, 1, pausa)
    if not tipo:
        return False, f"a aula não abriu ({porque})"
    if tipo == SEM_VIDEO:
        return False, f"a 1ª aula do curso {posicao} não tem vídeo"
    os.makedirs(PASTA_DAS_GRAVACOES, exist_ok=True)
    destino = os.path.join(PASTA_DAS_GRAVACOES, f"{_agora():%Y%m%d-%H%M%S}.mkv")
    endereco = aulas[0]["endereco"]
    aberta, inteira, fim = gravar_a_aula(
        d, getattr(d, "serial", ""), destino, lambda celular: ir_para_o_endereco(celular, endereco, pausa),
        lambda celular: tocar_pelo_play(celular, pausa), pausa=pausa, madrugada=lambda: True,
        maximo=GRAVACAO_DO_TESTE)
    calar_o_celular(d)
    tocou = aberta and fim not in PARADAS_DA_AULA + (SEM_VIDEO, NAO_TOCOU)
    if not tocou or not os.path.exists(destino) or not os.path.getsize(destino):
        # O robô que pede o celular o tem na hora (a leitura da fala o seguraria), e a aula que não tocou não tem o
        # que ler: a gravação sai sem ser lida, e o teste fica para depois.
        if os.path.exists(destino):
            os.remove(destino)
        return False, f"a gravação parou ({fim}) e saiu sem ser lida"
    _pasta, info = guardar_a_aula(destino, 0, 0, fim)
    return not info.get("problema"), (
        f"aula gravada {'inteira' if inteira else 'pela metade'} ({fim}): {info.get('segundos')} s, som "
        f"{info.get('som')} LUFS, {info.get('palavras')} palavra(s), {info.get('folhas')} folha(s) de quadros, "
        f"{info.get('problema') or 'sem problema'}; para ler: cursos_robo.yml exportar")


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
        return False, f"a aula não abriu ({porque})"
    pausar_o_que_toca(d, pausa)
    lista, porque = ler_a_lista(d, pausa)
    pausar_o_que_toca(d, pausa)
    if not lista:
        return False, f"a lista do curso {posicao} não foi lida ({porque})"
    guardar_a_lista(posicao, lista)
    return True, descrever_a_lista(posicao, lista)


def curso_no_explorar(d, argumento, pausa=time.sleep):
    """
    O passo curso do explorar: curso:primeira:N guarda a aula aberta no Chrome como a 1ª do curso na posição N da lista
    de Turmas (o Claude a abre com o mapa do site); curso:abrir:N abre a 1ª aula do curso N pela barra de endereço,
    como a noite abre, e curso:proximo, a seguinte à aberta, pelo Próximo (os dois sem mudar o mapa, com o celular
    mudo); curso:guardar guarda a aula sem vídeo aberta (ou a página da videoaula), como a noite; curso:gravar:N grava
    de dia a 1ª aula do curso N como a noite grava (o teste); curso:lista:N lê da aba Módulos a lista das aulas do curso
    N, na ordem, e a guarda no mapa (com o celular mudo); curso sozinho diz o mapa em números. O endereço e os nomes
    ficam no banco, e o log diz só números e palavras fixas.
    """
    partes = [parte.strip() for parte in argumento.split(":")] if argumento else []
    if not partes:
        return True, resumo_do_mapa()
    if partes == ["proximo"]:
        return _proxima_no_explorar(d, pausa)
    if partes == ["guardar"]:
        return _guardar_no_explorar(d, pausa)
    if partes[0] not in ("primeira", "abrir", "gravar", "lista") or len(partes) != 2 or not partes[1].isdigit():
        return False, ("curso:primeira:N guarda a aula aberta como a 1ª do curso N; curso:abrir:N abre a 1ª do curso "
                       "N; curso:proximo abre a seguinte; curso:guardar guarda a aula sem vídeo aberta (ou a página "
                       "da videoaula); curso:gravar:N grava a 1ª do curso N como a noite; curso:lista:N lê a lista "
                       "das aulas do curso N; curso diz o mapa")
    posicao = int(partes[1])
    if posicao not in ORDEM_DOS_CURSOS:
        return False, f"o curso vai de 1 a {len(ORDEM_DOS_CURSOS)} (a posição na lista de Turmas)"
    if partes[0] == "gravar":
        return _gravar_no_explorar(d, posicao, pausa)
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
        return False, f"o curso {posicao} já tem aula gravada: a 1ª dele não muda"
    return True, f"1ª aula do curso {posicao} guardada"


def toca_aula(nome, argumento):
    """
    O passo do explorar pode fazer o vídeo de uma aula tocar (abrir uma aula ou tocar o vídeo do Chrome)? Com ele,
    também de dia, o celular fica mudo: ele fica no quarto do Rafael (pedido dele, 22/11/2026).
    """
    acao = (argumento or "").split(":")[0].strip().lower()
    return ((nome == "curso" and acao in ("abrir", "proximo", "gravar", "lista"))
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
# página (documento_1.ext). Os links da aula ficam só anotados no texto, sem abrir: entrar num grupo ou preencher uma
# ficha é com o Rafael. Nenhum toque cai no Próximo, na bolha do chat (BOLHA_DO_CHAT) ou na barra do Chrome
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
    """Os links da aula (o texto de cada um), só anotados: o endereço fica no site, e nenhum é aberto."""
    return [no["descricao"] for no in _nos_da_aula(xml)
            if no["clicavel"] and no["classe"] == "View" and no["descricao"] and not no["id"]]


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


def juntar_os_textos(textos, novos):
    """Os textos da tela seguinte depois dos da anterior, sem repetir o pedaço que as duas mostram."""
    for tamanho in range(min(len(textos), len(novos)), 0, -1):
        if textos[-tamanho:] == novos[:tamanho]:
            return textos + novos[tamanho:]
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
        if abas_na_tela(tela):
            break
        anterior = atuais
        rolar_a_pagina(d)
        pausa(ESPERA_DA_ROLAGEM)
    if not textos and not documento and not slides:
        return {}, PAGINA_VAZIA
    with open(os.path.join(pasta, "texto.txt"), "w", encoding="utf-8") as saida:
        saida.write("\n".join(textos) + "\n")
        if links:
            saida.write("\nLinks da aula (anotados, sem abrir):\n" + "".join(f"- {link}\n" for link in links))
    return {"telas": telas, "slides": slides or 0, "linhas": len(textos), "links": len(links),
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
    return (f"{info.get('telas', 0)} tela(s), {slides}{info.get('linhas', 0)} linha(s), {info.get('links', 0)} "
            f"link(s), {doc}")


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
NAO_TOCOU = "a aula não começou a tocar"


def _madrugada_agora():
    return na_madrugada(db.ler_config("shopee_video", {}) or {})


def gravar_a_aula(d, alvo, destino, ir_para_a_aula, tocar, pausa=None, relogio=None, abrir=subprocess.Popen,
                  madrugada=None, maximo=AULA_MAIS_LONGA):
    """
    A aula aberta no Chrome do celular e gravada em destino, do começo ao fim. A ordem protege o quarto do Rafael
    (pedido dele, 22/11/2026): o gravador liga antes e, gravando o som, deixa o alto-falante mudo; o volume sobe só
    com ele gravando; a aula abre (ir_para_a_aula) já com o gravador ligado, porque o vídeo pode começar a tocar
    sozinho com a página (23/11/2026), e tocar(d) dá o play quando ele não começou; no fim, a aula pausa e o volume
    volta antes de o gravador parar. O robô que pede o celular, a madrugada que acaba (3h45) e o gravador que cai
    param a aula, que fica pela metade (P295 1: ela volta depois, do início). Devolve (aberta, inteira, motivo fixo):
    aberta diz se a página da aula abriu; na aula sem vídeo, (True, False, SEM_VIDEO). maximo: o tempo máximo da
    gravação, em segundos (o teste de dia grava menos que a noite).
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
        tipo, porque = ir_para_a_aula(d)
        if not tipo:
            return False, False, f"a aula não abriu ({porque})"
        if tipo == SEM_VIDEO:
            return True, False, SEM_VIDEO
        if not tocar(d):
            return True, False, NAO_TOCOU
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


def mapa_para_o_claude(mapa=None):
    """
    O mapa sem os endereços, para o pacote do Claude (mapa.json): os cursos na ordem, com a lista das aulas lida da aba
    Módulos (os módulos, os nomes e as durações) e o que a noite já guardou de cada uma. É de onde sai a lista das aulas
    com o check de cada uma, no relatório da manhã (pedido do Rafael de 24/11/2026).
    """
    mapa = mapa or mapa_das_aulas()
    cursos = {}
    for posicao in ORDEM_DOS_CURSOS:
        curso = mapa["cursos"].get(str(posicao)) or {}
        cursos[str(posicao)] = {
            "lista": curso.get("lista") or [], "lista_em": curso.get("lista_em", ""), "fim": bool(curso.get("fim")),
            "aulas": [{chave: valor for chave, valor in aula.items() if chave != "endereco"}
                      for aula in curso.get("aulas") or []]}
    return {"ordem": list(ORDEM_DOS_CURSOS), "cursos": cursos}


def tem_lista(mapa=None):
    """Algum curso já tem a lista das aulas no mapa (o exportar leva o mapa ao Claude mesmo sem aula guardada)?"""
    mapa = mapa or mapa_das_aulas()
    return any((curso or {}).get("lista") for curso in mapa["cursos"].values())


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


def guardar_o_caso(d, motivo, resultado="não abriu"):
    """
    A tela da 1ª aula da noite que não abriu (o print, a forma da tela e o log do Chrome), guardada para o Claude
    achar o porquê, e a da 1ª aula sem vídeo, para ele conferir que era mesmo um documento ou um texto (casos_robo:
    cifrada no exportar, nunca no repositório).
    """
    import casos_robo
    return casos_robo.guardar(d, "curso", resultado, motivo, passo="abrir a aula")


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


def _abrir_a_seguinte(d, posicao, numero, pausa):
    """
    A aula `numero` pelo Próximo da aberta (a de antes dela), conferida pelo nome (na_aula_certa) e anotada no mapa com
    ele: (tipo, porque).
    """
    tipo, porque, nome = passar_para_a_seguinte(d, pausa)
    if tipo and not na_aula_certa(d, posicao, numero, nome):
        return None, VOLTOU
    if tipo:
        anotar_a_aula_seguinte(posicao, numero, nome)
    return tipo, porque


# No fim do vídeo, o site pode passar sozinho para a aula seguinte (o teste de dia de 23/11/2026, às 23:06: acabada a 1ª
# aula do curso 5, a página já era a da 2ª). Sem conferir, a noite guardaria a página da seguinte como a da gravada e
# tocaria no Próximo dela, gravando a aula de depois com o número da seguinte: uma aula pulada e as outras com o número
# trocado. A aula aberta anota o nome no Próximo dela (o da aula seguinte), e a noite confere se ele é o mesmo depois
# do vídeo; não sendo, a página saiu da aula gravada, e a seguinte vem pelo começo do curso (nenhuma aula é pulada).
SAIU_DA_AULA = "o site passou sozinho para outra aula no fim do vídeo"


def _abrir_anotando_o_proximo(abrir, anotado, pausa):
    """abrir(d) que, com a aula aberta, anota em anotado["proximo"] o nome no Próximo dela ("" na última do curso)."""
    def abrir_e_anotar(d):
        tipo, porque = abrir(d)
        if tipo:
            tela, _ponto = proximo_na_tela(d, pausa)
            anotado["proximo"] = nome_no_proximo(tela)
        return tipo, porque
    return abrir_e_anotar


def ainda_na_aula(d, anotado, pausa):
    """A página ainda é a da aula aberta: o Próximo tem o mesmo nome de quando ela abriu (_abrir_anotando_o_proximo)?"""
    if "proximo" not in anotado:
        return False
    tela, _ponto = proximo_na_tela(d, pausa)
    return nome_no_proximo(tela) == anotado["proximo"]


OUTRA_PAGINA = "a página não é a da aula gravada"


def _guardar_a_pagina_da_videoaula(d, posicao, numero, pausa, vigiar):
    """
    Depois da videoaula gravada inteira, a página dela também vai ao Claude: o texto com as instruções e os links, e o
    documento que ela tiver (pedidos do Rafael de 23/11/2026, às 08:44 e às 09:12), conferida antes pelo nome no
    Próximo. Sem ela, a aula gravada vale do mesmo jeito, e o registro diz o porquê (a videoaula sem nada escrito
    embaixo do vídeo não vai ao registro). Devolve o porquê de a noite parar ("o robô pediu o celular", "a madrugada
    acabou") ou "".
    """
    aulas = (mapa_das_aulas()["cursos"].get(str(posicao)) or {}).get("aulas") or []
    nome = (aulas[int(numero) - 1].get("nome") or "") if len(aulas) >= int(numero) else ""
    if na_aula_certa(d, posicao, numero, nome):
        pasta, info = guardar_a_aula_sem_video(d, posicao, numero, pausa, vigiar, tipo=PAGINA_DA_VIDEOAULA)
    else:
        pasta, info = None, {"problema": OUTRA_PAGINA}
    if pasta:
        registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, "página guardada",
                                     f"{qual_aula(posicao, numero)}: {descrever_a_aula_guardada(info)}", ok=True)
        return ""
    if info["problema"] in PARADAS_DA_AULA:
        return info["problema"]
    if info["problema"] == PAGINA_VAZIA:
        return ""
    registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, "página não guardada",
                                 f"{qual_aula(posicao, numero)}: {info['problema']}", ok=None)
    return ""


def _antes_da_gravacao(d, posicao, numero, aberta, pausa, vigiar=None):
    """
    O celular pronto para gravar a aula `numero`, sem o gravador: a 1ª do curso aberta pelo endereço (o login que a
    sessão vencida pede fica fora da gravação), e a de antes da da vez na tela (a da vez abre pelo Próximo dela, já com
    o gravador gravando). (aberta agora, "") ou (None, o porquê); FIM_DO_CURSO sem o Próximo depois da última.
    """
    if numero == 1:
        tipo, porque = chegar_na_aula(d, posicao, 1, pausa, vigiar)
        return ((posicao, 1), "") if tipo else (None, porque)
    if aberta != (posicao, numero - 1):
        tipo, porque = chegar_na_aula(d, posicao, numero - 1, pausa, vigiar)
        if not tipo:
            return None, porque
    tela, ponto = proximo_na_tela(d, pausa)
    if not ponto:
        return ((posicao, numero - 1), FIM_DO_CURSO) if pagina_da_aula_pronta(tela) else (None, SEM_A_PAGINA)
    return (posicao, numero - 1), ""


def noite(conectar=None, pausa=None, ajudante=None, trava=None, conectado=None):
    """
    A gravação de uma madrugada (P289 1 a P295 1): as aulas da vez, uma a uma, até a madrugada acabar, o disco encher,
    o robô pedir o celular ou acabarem as aulas. O site troca a aula pelo Próximo sem trocar o endereço (23/11/2026): a
    1ª de cada curso abre pelo endereço, e cada uma das outras pelo Próximo da de antes, com o gravador já gravando,
    para o vídeo que começa sozinho ficar inteiro. A aula sem vídeo (um documento ou um texto) é guardada com a página
    e o documento (guardar_a_aula_sem_video); a que não fica guardada volta na noite seguinte, e a noite segue para a
    próxima: nenhuma aula é pulada. Da videoaula gravada inteira, a página também é guardada, com o celular mudo
    (_guardar_a_pagina_da_videoaula). Devolve o que aconteceu numa frase só com números (vai ao log).
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
                motivo = "nenhuma aula por gravar"
                break
            if not conectado():
                motivo = "o celular desconectado"
                break
            posicao, numero = da_vez
            guardada, inteira, aberta_na_gravacao, fim, destino, info = False, False, False, "", "", {}
            parar_depois = ""
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
                inicio = _texto(_agora())

                def vigiar():
                    anotar_o_sinal()
                    if pediram_o_celular(inicio):
                        return "o robô pediu o celular"
                    return "" if _madrugada_agora() else "a madrugada acabou"
                aberta, porque = _antes_da_gravacao(d, posicao, numero, aberta, pausa, vigiar)
                if porque == FIM_DO_CURSO:
                    if numero > len(mapa_das_aulas()["cursos"][str(posicao)]["aulas"]):
                        anotar_o_fim_do_curso(posicao)
                        continue
                    # A aula de antes de uma conhecida sem o Próximo: a página não é a que a noite pensa.
                    aberta, porque = None, "sem o Próximo na aula de antes"
                if not aberta:
                    fim = f"a aula não abriu ({porque})"
                else:
                    destino = os.path.join(PASTA_DAS_GRAVACOES, f"{_agora():%Y%m%d-%H%M%S}.mkv")
                    if numero == 1:
                        endereco = mapa_das_aulas()["cursos"][str(posicao)]["aulas"][0]["endereco"]
                        abrir = (lambda celular: ir_para_o_endereco(celular, endereco, pausa))
                    else:
                        abrir = (lambda celular: _abrir_a_seguinte(celular, posicao, numero, pausa))
                    na_abertura = {}
                    aberta_na_gravacao, inteira, fim = gravar_a_aula(
                        d, getattr(d, "serial", ""), destino, _abrir_anotando_o_proximo(abrir, na_abertura, pausa),
                        lambda celular: tocar_pelo_play(celular, pausa), pausa=pausa)
                    # O site que passa sozinho para a aula seguinte no fim do vídeo (e começa o vídeo dela ou não) deixa
                    # na tela outra aula: a próxima vez, a noite chega à da vez pelo começo do curso (SAIU_DA_AULA).
                    no_lugar = (aberta_na_gravacao and fim not in PARADAS_DA_AULA + ("outro vídeo começou",)
                                and ainda_na_aula(d, na_abertura, pausa))
                    aberta = (posicao, numero) if no_lugar else None
                    if inteira and aberta and calar_o_celular(d):
                        # A página da videoaula (o texto, os links e o documento), com o vídeo já pausado e mudo.
                        parar_depois = _guardar_a_pagina_da_videoaula(d, posicao, numero, pausa, vigiar)
                        if not parar_depois and not ainda_na_aula(d, na_abertura, pausa):
                            aberta = None
                    elif inteira and not aberta:
                        registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, "página não guardada",
                                                     f"{qual_aula(posicao, numero)}: {SAIU_DA_AULA}", ok=None)
                    if fim == SEM_VIDEO and not calar_o_celular(d):
                        fim = SEM_O_MUDO
                    elif fim == SEM_VIDEO:
                        pasta, info = guardar_a_aula_sem_video(d, posicao, numero, pausa, vigiar)
                        guardada, fim = bool(pasta), (SEM_VIDEO if pasta else info["problema"])
                        if not pasta:
                            # A página pode ter saído da tela (o Baixar que abriu o documento): a próxima vez, a noite
                            # chega à da vez pelo começo do curso.
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
            registro_processos.registrar(REGISTRO_DO_CURSO, PROCESSO_DA_AULA, resultado,
                                         f"{qual_aula(posicao, numero)}: {fim}",
                                         ok=None if fim in PARADAS_DA_AULA else False)
            if resultado == "pela metade":
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
    print("uso: cursos_robo.py aulas contar | ultima | tem-lista | cifrado [ATE] | apagar ATE | ler ARQUIVO PASTA")
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

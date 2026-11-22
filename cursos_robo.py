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
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET

from PIL import Image, ImageStat

import videos

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
    return ["scrcpy", "-s", alvo, "--no-window", "--no-playback", "--no-control",
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


def para_o_claude(arquivo, pasta):
    """
    Grava na pasta (a de um caso, que vai cifrado ao Claude) as folhas de quadros e a fala (fala.txt, com
    o segundo de cada trecho). Devolve (folhas, palavras); palavras é None quando não deu para ouvir.
    """
    folhas = videos.folhas_de_quadros(arquivo, pasta, QUADROS_PARA_O_CLAUDE)
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


def estado_da_midia(texto, pacote=PACOTE_DO_CHROME):
    """
    Na saída do dumpsys media_session, a sessão de mídia do Chrome: {"estado", "posicao"} (a posição em
    segundos, a da última vez que o Chrome a anotou); com mais de uma, a que está tocando. None sem
    sessão do Chrome. Só o estado e o tempo: o título da aula, que a sessão também tem, nunca sai daqui.
    """
    sessoes = []
    for linha in (texto or "").splitlines():
        achado = re.match(r"\s*package=(\S+)", linha)
        if achado:
            sessoes.append({"pacote": achado.group(1)})
            continue
        achado = re.search(r"state=PlaybackState \{state=(?:[A-Za-z_]+\()?(\d+)\)?, position=(-?\d+)", linha)
        if achado and sessoes and "codigo" not in sessoes[-1]:
            sessoes[-1].update(codigo=int(achado.group(1)), posicao=max(0, int(achado.group(2))) // 1000)
    do_pacote = [s for s in sessoes if s["pacote"] == pacote and "codigo" in s]
    if not do_pacote:
        return None
    escolhida = next((s for s in do_pacote if s["codigo"] == TOCANDO), do_pacote[0])
    return {"estado": ESTADOS_DA_MIDIA.get(escolhida["codigo"], "outro"), "posicao": escolhida["posicao"]}


def midia_do_chrome(d):
    """O estado do vídeo no Chrome do celular agora (estado_da_midia); None sem vídeo nele."""
    return estado_da_midia(_saida(d, ["dumpsys", "media_session"]))


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


def main(argumentos):
    if argumentos == ["instalar"]:
        return 0 if instalar() else 1
    if argumentos == ["estado"]:
        versao = versao_instalada()
        print(f"gravador: {'scrcpy ' + versao if versao else 'não instalado'}")
        return 0
    print("uso: cursos_robo.py instalar | estado")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

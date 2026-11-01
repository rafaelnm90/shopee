"""
O celular de verdade do Rafael, onde o robô da Shopee Vídeo vai postar (plano do
celular no roteiro_robo_shopee_video.md). O servidor fala com ele pelo adb, pela
rede privada (Tailscale): o celular fica em casa, com a "Depuração por Wi-Fi" ligada.

Quem usa:
- painel_shopee_video (botão Celular do Robô 📱): acha o celular na rede privada,
  pareia com o código que o Rafael manda no privado do bot e conecta;
- postador_shopee_video (--celular): explora o app da Shopee no celular;
- robo_shopee_video: o robô automático, que prepara os rascunhos e posta.
O explorar e o robô automático pegam a trava() antes de tocar no celular: os dois
juntos tocariam em cima um do outro.

A porta da Depuração por Wi-Fi muda cada vez que ela é ligada (o celular reiniciou,
trocou de Wi-Fi). Com ela ligada, reconectar_sozinho() acha a porta nova pela rede
privada, sem o Rafael mandar nada; só a depuração desligada pede a mão dele.

O Android corta o pareamento 7 dias depois de feito, a não ser que a opção OPCAO_DO_PRAZO
(Opções do desenvolvedor) esteja ligada: aí o celular abre a ligação, mas não reconhece
mais o servidor, e só parear de novo resolve. A opção fica sempre ligada (pedido do
Rafael); o robô a lê de hora em hora (anotar_prazo) e o alertas.py avisa se ela desligar.

O código de pareamento vale só enquanto a janela dele está aberta no celular e passa
só pelo bot: nunca vai para o log nem para o banco. No banco (chave CHAVE) ficam o
nome do celular na rede, o endereço e a porta da conexão, o modelo e as datas.
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import asyncio
import contextlib
import fcntl
import json
import os
import re
import shutil
from datetime import datetime, timedelta

import android_virtual as av
import db
import registro_processos
from fuso import fuso_horario

CHAVE = "celular_robo"
ARQUIVO_TRAVA = os.path.join(av.PASTA_TRABALHO, "celular.trava")
# A opção que impede o Android de cortar o pareamento (nome como aparece no Motorola). Ligada,
# a configuração CONFIG_DO_PRAZO vale 0; sem ela, vale o padrão de PRAZO_PADRAO_DIAS.
OPCAO_DO_PRAZO = "Desativar o tempo limite da autorização adb"
CONFIG_DO_PRAZO = "adb_allowed_connection_time"
PRAZO_PADRAO_DIAS = 7
LER_O_PRAZO_A_CADA = timedelta(hours=1)
# O celular abre a ligação e não reconhece mais o servidor: o pareamento venceu, e nem a
# porta nem o Reconectar resolvem. O botão é o BOTAO_PAREAR do painel_shopee_video.
MOTIVO_DO_PAREAMENTO = "o celular não reconhece mais este servidor (o pareamento venceu)"
COMO_PAREAR = ("pareie de novo em Celular do Robô 📱 → Parear Celular 🔗 e deixe ligada, nas Opções do "
               f"desenvolvedor do Motorola, a opção {OPCAO_DO_PRAZO}")
# Onde o Android abre a porta da Depuração por Wi-Fi: as portas "efêmeras" do Linux,
# sorteadas cada vez que a depuração é ligada.
PORTAS_DA_DEPURACAO = range(32768, 61000)

# Por que o celular saiu: o Android desliga a Depuração por Wi-Fi sozinho quando o Wi-Fi cai,
# quando o celular troca de ponto de Wi-Fi (outro roteador, um repetidor ou a outra frequência do
# mesmo roteador) e quando o celular reinicia. Na volta, o servidor lê no próprio celular qual
# foi (motivo_da_queda): reiniciou, se ele está ligado há menos tempo que desde a última vez em
# que o servidor o viu (visto_em); senão, a última linha do AdbDebuggingManager no registro do
# Android (logcat) que desliga a depuração. Só o motivo fixo vai ao registro e ao banco, nunca a
# linha crua. Pergunta do Rafael (31/10): por que desconectou. DECISOES.md, Trabalho com o Claude.
PROCESSO_DA_QUEDA = "celular: motivo da queda"
TAG_DA_DEPURACAO = "AdbDebuggingManager"
MOTIVOS_DA_QUEDA = (
    ("network disconnected", "o Wi-Fi caiu"),
    ("network change", "o celular trocou de ponto de Wi-Fi (outro roteador, repetidor ou a outra frequência)"),
    ("wifi disabled", "o Wi-Fi foi desligado"),
    ("bssid", "o Wi-Fi ficou sem o ponto de acesso"),
    ("not connected to any", "o celular ficou sem rede Wi-Fi"),
)
REINICIOU = "o celular reiniciou"
LIGACAO_PRESA = "a ligação do adb travou (a Depuração por Wi-Fi ficou ligada)"
SEM_O_MOTIVO = "o Android não guardou o motivo (desligada à mão, ou o registro dele já foi renovado)"
# O registro do Android se renova em poucas horas, e numa queda longa o motivo some. Para ainda dar
# uma pista, a volta e o estado contam quantos pontos de Wi-Fi o celular enxerga com o mesmo nome
# da rede dele (ler_wifi, pelo "dumpsys wifi"): com mais de um (repetidor, roteador em malha, ou
# o 2,4 GHz e o 5 GHz com o mesmo nome), ele pode trocar de ponto. Só a faixa e os números saem
# daqui, nunca o nome da rede nem o endereço do ponto. Pedido do Rafael (01/11): DECISOES.md,
# Trabalho com o Claude.
FAIXAS_DO_WIFI = ((3000, "2,4 GHz"), (5925, "5 GHz"), (7200, "6 GHz"))
CONEXAO_DO_WIFI = re.compile(r'mWifiInfo SSID: "(?P<nome>[^"\n]*)"[^\n]*?Frequency: (?P<mhz>\d+) ?MHz')
PONTO = re.compile(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}")
FREQUENCIA = re.compile(r"(?<![\d.:])(2[4-9]\d\d|[3-6]\d{3}|7[01]\d\d)(?![\d.])")
# A forma de uma linha da busca de redes quando nenhum ponto é achado (o formato do Android pode
# mudar): só o tipo de cada pedaço, nunca o nome da rede, o endereço ou os números.
TIPOS_DA_FORMA = ((re.compile(r"^(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2},?$"), "MAC"),
                  (re.compile(r"^-?\d+,?$"), "NUM"), (re.compile(r"^-?\d+\.\d+,?$"), "DEC"),
                  (re.compile(r"^-?\d+\("), "NUM(..)"), (re.compile(r"^-?\d+[A-Za-z]+,?$"), "NUM+unid"),
                  (re.compile(r"^\["), "[..]"))
# Só estes rótulos aparecem na forma como são ("SSID:", "level=…"): outro pedaço com ":" ou "="
# pode ser parte do nome da rede e vira TXT.
ROTULOS_DA_FORMA = {"ssid", "bssid", "freq", "frequency", "level", "rssi", "flags", "capabilities", "age",
                    "timestamp", "ts", "dist", "distsd", "channelwidth", "centerfreq0", "centerfreq1",
                    "standard", "wifistandard", "band", "security", "type"}


def ler():
    return db.ler_config(CHAVE, {}) or {}


def _gravar(**campos):
    with db.conexao() as conexao:
        conexao.execute("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    db.atualizar_config(CHAVE, lambda dados: dados.update(campos))


def _agora():
    return datetime.now(fuso_horario).strftime("%Y-%m-%d %H:%M:%S")


def celulares_na_rede():
    """Os aparelhos Android da rede privada: [{"nome", "ip", "online"}]; [] se a rede não responde."""
    if shutil.which("tailscale") is None:
        return []
    r = av._rodar("tailscale", "status", "--json", timeout=30)
    if not av._ok(r):
        return []
    try:
        pares = (json.loads(r[1]).get("Peer") or {}).values()
    except ValueError:
        return []
    celulares = []
    for par in pares:
        if (par.get("OS") or "").lower() != "android":
            continue
        ip = next((ip for ip in par.get("TailscaleIPs") or [] if ":" not in ip), None)
        if ip:
            celulares.append({"nome": par.get("HostName") or ip, "ip": ip, "online": bool(par.get("Online"))})
    return sorted(celulares, key=lambda c: (not c["online"], c["nome"].lower()))


def interpretar_pareamento(texto):
    """
    O código (6 dígitos) e a porta (4 ou 5) que o Rafael copia da janela de
    pareamento, em qualquer ordem e com o IP junto ou não: (codigo, porta) ou None.
    """
    texto = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}", " ", texto or "")
    numeros = re.findall(r"\d+", texto)
    codigos = [n for n in numeros if len(n) == 6]
    portas = [n for n in numeros if 4 <= len(n) <= 5 and 1024 <= int(n) <= 65535]
    if len(codigos) != 1 or len(portas) != 1 or len(numeros) != 2:
        return None
    return codigos[0], int(portas[0])


def interpretar_porta(texto):
    """A porta da conexão ("41235" ou "192.168.0.5:41235"); None se não serve."""
    texto = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}", " ", texto or "")
    numeros = re.findall(r"\d+", texto)
    if len(numeros) != 1 or not 1024 <= int(numeros[0]) <= 65535:
        return None
    return int(numeros[0])


def _motivo(resultado):
    """Por que o adb falhou, em palavras simples (sem a saída crua, que traz o endereço)."""
    if resultado is None:
        return "o adb não respondeu"
    saida = resultado[1].lower()
    for trecho, motivo in (("wrong password", "o código não confere (ou a janela já fechou)"),
                           ("protocol fault", "o código não confere (ou a janela já fechou)"),
                           ("connection refused", "o celular recusou: a porta mudou ou a depuração está desligada"),
                           # Com a depuração ligada e a porta aberta, o celular não aceita mais o
                           # servidor: o pareamento venceu.
                           ("failed to authenticate", f"{MOTIVO_DO_PAREAMENTO}: {COMO_PAREAR}"),
                           ("timed out", "o celular não respondeu: confira o Tailscale e o Wi-Fi dele"),
                           ("no route", "o celular não respondeu: confira o Tailscale e o Wi-Fi dele"),
                           ("unreachable", "o celular não respondeu: confira o Tailscale e o Wi-Fi dele"),
                           ("unauthorized", "o celular ainda não autorizou este servidor"),
                           # A porta da depuração responde e o adb vê o celular "offline": o servidor
                           # do adb pode ter ficado preso (reconectar_sozinho o reinicia).
                           ("offline", "o adb vê o celular desligado (offline)"),
                           ("daemon", "o adb do servidor não respondeu")):
        if trecho in saida:
            return motivo
    if _ligacao_sem_aceite(resultado[1]):
        return f"{MOTIVO_DO_PAREAMENTO}: {COMO_PAREAR}"
    resumo = _resumo_do_adb(resultado[1])
    return f"o adb não conseguiu (tente de novo; o adb disse: {resumo})" if resumo else "o adb não conseguiu (tente de novo)"


def _ligacao_sem_aceite(saida):
    """
    O adb abriu a ligação, mas o celular não aceitou o servidor: "failed to connect to
    ENDEREÇO", sem o motivo do sistema. A ligação recusada ou sem resposta vem com ele (o
    endereço entre aspas e o motivo depois dos dois-pontos). Na Depuração por Wi-Fi é o
    pareamento vencido: o celular corta a ligação sem dizer por quê.
    """
    return any(re.fullmatch(r"failed to connect to [^'\s]+", linha.strip())
               for linha in str(saida or "").lower().splitlines())


def pede_pareamento(motivo):
    """O motivo de uma falha diz que só parear de novo resolve (nem a porta nem o Reconectar)?"""
    return MOTIVO_DO_PAREAMENTO in (motivo or "")


def _resumo_do_adb(saida):
    """
    A 1ª linha da saída do adb sem o endereço, a porta, os números e os nomes de serviço
    (adb-...): o motivo vai para o registro e o aviso, e o log do checkup é público.
    """
    linha = next((l.strip() for l in str(saida or "").splitlines() if l.strip()), "")
    linha = re.sub(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?", "…", linha)
    linha = re.sub(r"adb-[\w.-]+", "…", linha)
    linha = re.sub(r"\d+", "#", linha)
    return re.sub(r"['\"`]", "", linha)[:80].strip()


def parear(ip, porta, codigo):
    """Pareia o servidor com o celular. (True, "") ou (False, motivo)."""
    if shutil.which("adb") is None:
        return False, "o adb não está instalado no servidor"
    r = av._rodar("adb", "pair", f"{ip}:{porta}", codigo, timeout=40)
    if av._ok(r) and "successfully paired" in r[1].lower():
        _gravar(ip=ip, pareado_em=_agora())
        return True, ""
    return False, _motivo(r)


def conectar(ip, porta):
    """Conecta o adb ao celular já pareado. (True, modelo) ou (False, motivo)."""
    if shutil.which("adb") is None:
        return False, "o adb não está instalado no servidor"
    endereco = f"{ip}:{porta}"
    r = av._rodar("adb", "connect", endereco, timeout=40)
    if not (av._ok(r) and "connected to" in r[1].lower()):
        return False, _motivo(r)
    estado = av._rodar("adb", "-s", endereco, "get-state", timeout=20)
    if not (av._ok(estado) and estado[1].strip() == "device"):
        return False, _motivo(estado)
    marca = av._rodar("adb", "-s", endereco, "shell", "getprop", "ro.product.manufacturer", timeout=20)
    modelo = av._rodar("adb", "-s", endereco, "shell", "getprop", "ro.product.model", timeout=20)
    versao = av._rodar("adb", "-s", endereco, "shell", "getprop", "ro.build.version.release", timeout=20)
    nome = " ".join(r[1].strip() for r in (marca, modelo) if av._ok(r)).strip() or "celular"
    if av._ok(versao):
        nome += f", Android {versao[1].strip()}"
    _gravar(ip=ip, porta=porta, modelo=nome, conectado_em=_agora())
    return True, nome


def endereco():
    """O "ip:porta" do adb do celular, se já conectou uma vez; None se não."""
    dados = ler()
    return f"{dados['ip']}:{dados['porta']}" if dados.get("ip") and dados.get("porta") else None


def conectado():
    """O adb fala com o celular agora? Quando fala, guarda a hora (visto_em, para o motivo_da_queda)."""
    alvo = endereco()
    if not alvo or shutil.which("adb") is None:
        return False
    # Prazo curto: a tela do celular no bot espera esta resposta.
    av._rodar("adb", "connect", alvo, timeout=10)
    r = av._rodar("adb", "-s", alvo, "get-state", timeout=10)
    ligado = av._ok(r) and r[1].strip() == "device"
    if ligado:
        _gravar(visto_em=_agora())
    return ligado


def portas_abertas(ip, portas=PORTAS_DA_DEPURACAO, prazo=0.5, juntas=400):
    """As portas TCP abertas do celular, testadas em paralelo pela rede privada (uns 30 s)."""
    async def testar(porta, limite):
        async with limite:
            try:
                _, escritor = await asyncio.wait_for(asyncio.open_connection(ip, porta), prazo)
            except (OSError, asyncio.TimeoutError):
                return None
            escritor.close()
            return porta

    async def todas():
        limite = asyncio.Semaphore(juntas)
        return [p for p in await asyncio.gather(*(testar(p, limite) for p in portas)) if p]

    return asyncio.run(todas())


def reconectar_sozinho():
    """
    Reconecta sem o Rafael mandar a porta: primeiro a porta guardada, refazendo a conexão
    do adb (ela pode ficar presa com o celular e a depuração ligados); se não der, procura
    a porta nova da Depuração por Wi-Fi no celular, pela rede privada, e conecta nela.
    Só a depuração desligada, o celular fora da rede ou o pareamento vencido impedem.
    (True, modelo) ou (False, motivo em palavras simples, que diz se a porta da depuração
    respondia e se é preciso parear de novo: pede_pareamento). Na volta, anota por que o
    celular tinha saído (anotar_motivo_da_queda).
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if conectado():
        return True, ler().get("modelo") or "celular"
    visto_em = ler().get("visto_em")
    ok, resultado, mesma_porta = _reconectar()
    if ok:
        anotar_motivo_da_queda(visto_em, mesma_porta)
    return ok, resultado


def _reconectar():
    """Os passos do reconectar_sozinho: (ok, modelo ou motivo, voltou na mesma porta?)."""
    dados = ler()
    if not dados.get("pareado_em") or not dados.get("ip"):
        return False, "o celular ainda não foi pareado com o servidor", False
    if shutil.which("adb") is None:
        return False, "o adb não está instalado no servidor", False
    rede = {c["ip"]: c for c in celulares_na_rede()}
    if not rede.get(dados["ip"], {}).get("online"):
        return False, "o celular não está na rede privada (Tailscale desligado ou celular sem internet)", False
    motivos = []
    if dados.get("porta"):
        # A conexão sem fio do adb pode ficar presa ("offline") com a depuração ligada: o
        # "adb connect" diz que já está conectado e nada responde. Desfazer e refazer resolve.
        av._rodar("adb", "disconnect", endereco(), timeout=10)
        ok, resultado = conectar(dados["ip"], dados["porta"])
        if ok:
            return True, resultado, True
        motivos.append(resultado)
    abertas = portas_abertas(dados["ip"])
    for porta in abertas:
        if porta == dados.get("porta"):
            continue
        ok, resultado = conectar(dados["ip"], porta)
        if ok:
            return True, resultado, False
        motivos.append(resultado)
    if dados.get("porta") in abertas:
        # A porta da depuração responde e o adb não conecta: o servidor do adb pode ter ficado
        # preso. Reiniciá-lo (as chaves do pareamento ficam) e tentar de novo uma vez, antes de
        # pedir o pareamento.
        av._rodar("adb", "kill-server", timeout=20)
        ok, resultado = conectar(dados["ip"], dados["porta"])
        if ok:
            return True, resultado, True
        if pede_pareamento(resultado):
            return False, f"a Depuração por Wi-Fi responde, mas {resultado}", False
        return False, (f"a Depuração por Wi-Fi responde no celular, mas o adb não conecta ({resultado}); "
                       "se continuar, parear de novo pelo Celular do Robô"), False
    # A porta nova (a depuração foi desligada e ligada) também não aceita o servidor: não é a
    # porta, é o pareamento.
    vencido = next((m for m in motivos if pede_pareamento(m)), None)
    if vencido:
        return False, f"a Depuração por Wi-Fi responde, mas {vencido}", False
    if abertas:
        return False, (f"o celular tem {len(abertas)} porta(s) aberta(s), mas nenhuma é a da Depuração por Wi-Fi; "
                       "se ela estiver ligada, parear de novo pelo Celular do Robô"), False
    return False, "a Depuração por Wi-Fi está desligada no celular (nenhuma porta dela aberta)", False


def ligado_ha():
    """Há quantos segundos o celular está ligado (desde que ligou pela última vez); None sem resposta."""
    alvo = endereco()
    r = av._rodar("adb", "-s", alvo, "shell", "cat", "/proc/uptime", timeout=15) if alvo else None
    if not av._ok(r):
        return None
    try:
        return float(r[1].split()[0])
    except (ValueError, IndexError):
        return None


def _faixa(mhz):
    return next((nome for limite, nome in FAIXAS_DO_WIFI if mhz < limite), "outra faixa")


def _linhas_da_busca(saida):
    """As linhas das buscas de redes do "dumpsys wifi": depois de "Latest scan results", até a linha em branco."""
    linhas, dentro = [], False
    for linha in (saida or "").splitlines():
        if "latest scan results" in linha.casefold():
            dentro = True
        elif dentro and not linha.strip():
            dentro = False
        elif dentro:
            linhas.append(linha)
    return linhas


def _forma(linha):
    """A forma de uma linha, pedaço por pedaço: o tipo (MAC, NUM...), o rótulo conhecido ("SSID:") ou TXT."""
    partes = []
    for pedaco in linha.split():
        tipo = next((nome for rx, nome in TIPOS_DA_FORMA if rx.match(pedaco)), None)
        if not tipo:
            rotulo = re.fullmatch(r"([A-Za-z_]+)([:=])(.*)", pedaco)
            conhecido = rotulo and rotulo.group(1).casefold() in ROTULOS_DA_FORMA
            tipo = (rotulo.group(1) + rotulo.group(2) + ("…" if rotulo.group(3) else "")) if conhecido else "TXT"
        partes.append(tipo)
    return " ".join(partes)


def interpretar_wifi(saida):
    """
    A rede do celular no texto do "dumpsys wifi": {"faixa", "pontos", "por_faixa"}, com a faixa
    da conexão de agora e os pontos (endereços diferentes) da última busca de redes que têm o
    mesmo nome da rede dele; None sem a conexão. O nome da rede só é comparado aqui dentro.
    Sem nenhum ponto, "forma" diz como eram as linhas da busca, sem os valores.
    """
    conexao = CONEXAO_DO_WIFI.search(saida or "")
    if not conexao or not conexao.group("nome"):
        return None
    # O nome aparece na coluna da busca, preenchida com espaços até o "[" das proteções, ou
    # depois de "SSID:" ou "SSID=", entre aspas: ele termina em dois espaços, num "[", numa
    # vírgula ou no fim da linha (assim "Casa" não conta "Casa 2").
    nome = re.compile(r'(?<=[\s=:])"?' + re.escape(conexao.group("nome")) + r'"?(?=\s{2,}|\s*\[|\s*$|,)')
    linhas = _linhas_da_busca(saida)
    pontos = {}
    for linha in linhas:
        ponto = PONTO.search(linha)
        if not ponto or not nome.search(" " + linha):
            continue
        frequencia = FREQUENCIA.search(linha, ponto.end())
        pontos[ponto.group(0).lower()] = _faixa(int(frequencia.group(1))) if frequencia else "outra faixa"
    por_faixa = {}
    for faixa in pontos.values():
        por_faixa[faixa] = por_faixa.get(faixa, 0) + 1
    wifi = {"faixa": _faixa(int(conexao.group("mhz"))), "pontos": len(pontos),
            "por_faixa": dict(sorted(por_faixa.items()))}
    if not pontos:
        com_ponto = [linha for linha in linhas if PONTO.search(linha)]
        wifi["forma"] = (f"busca de redes: {len(linhas)} linha(s), {len(com_ponto)} com ponto"
                         + (f"; forma: {_forma(com_ponto[0])}" if com_ponto else ""))
    return wifi


def ler_wifi():
    """interpretar_wifi do "dumpsys wifi" do celular (só lê); None sem resposta."""
    alvo = endereco()
    r = av._rodar("adb", "-s", alvo, "shell", "dumpsys", "wifi", timeout=30) if alvo else None
    return interpretar_wifi(r[1]) if av._ok(r) else None


def descrever_wifi(wifi):
    """A rede do celular em palavras curtas, só com a faixa e os números."""
    if not wifi:
        return "Wi-Fi não lido"
    texto = f"Wi-Fi em {wifi['faixa']}, {wifi['pontos']} ponto(s) com o mesmo nome"
    if wifi["pontos"]:
        texto += " (" + ", ".join(f"{faixa}: {n}" for faixa, n in wifi["por_faixa"].items()) + ")"
    elif wifi.get("forma"):
        texto += f" ({wifi['forma']})"
    return texto


def _wifi_agora():
    """descrever_wifi(ler_wifi()) sem nunca derrubar quem chama (o motivo da queda, o estado)."""
    try:
        return descrever_wifi(ler_wifi())
    except Exception as e:
        return f"Wi-Fi não lido (erro {type(e).__name__})"


def _duracao(segundos):
    return f"{round(segundos / 60)} min" if segundos < 7200 else f"{round(segundos / 3600)} h"


def motivo_da_queda(visto_em, mesma_porta=False, agora=None):
    """
    Por que o celular tinha saído, lido nele logo depois de voltar, em palavras fixas: a ligação
    do adb travou (voltou na mesma porta), o celular reiniciou, o motivo do Android para desligar
    a Depuração por Wi-Fi (MOTIVOS_DA_QUEDA) ou SEM_O_MOTIVO. (motivo, detalhe só com números:
    quanto tempo ficou fora, há quanto tempo está ligado e, quando não reiniciou, os pontos de
    Wi-Fi com o mesmo nome da rede dele)
    """
    agora = agora or datetime.now(fuso_horario)
    fora = None
    try:
        fora = (agora.replace(tzinfo=None) - datetime.strptime(visto_em or "", "%Y-%m-%d %H:%M:%S")).total_seconds()
    except ValueError:
        pass
    detalhe = f"fora há {round(fora / 60)} min" if fora is not None else "sem a última vez em que foi visto"
    if mesma_porta:
        return LIGACAO_PRESA, detalhe
    ligado = ligado_ha()
    if ligado is not None:
        detalhe += f"; ligado há {round(ligado / 60)} min"
        if fora is not None and ligado < fora:
            return REINICIOU, detalhe
    alvo = endereco()
    r = av._rodar("adb", "-s", alvo, "shell", "logcat", "-d", "-s", f"{TAG_DA_DEPURACAO}:*", timeout=20)
    linhas = [linha.casefold() for linha in (r[1] if av._ok(r) else "").splitlines()
              if "adbwifi" in linha.casefold() and ("disabl" in linha.casefold() or "not enabl" in linha.casefold())]
    detalhe += f"; {_wifi_agora()}"
    if linhas:
        return next((motivo for trecho, motivo in MOTIVOS_DA_QUEDA if trecho in linhas[-1]),
                    "o Android desligou a Depuração por Wi-Fi por outro motivo"), detalhe
    return SEM_O_MOTIVO, detalhe


def anotar_motivo_da_queda(visto_em, mesma_porta=False, agora=None):
    """
    O motivo_da_queda no registro dos processos (o checkup mostra) e no banco (ultima_queda, que
    o estado e o painel mostram). Nada aqui segura a volta do celular. Devolve o motivo, ou None.
    """
    agora = agora or datetime.now(fuso_horario)
    try:
        motivo, detalhe = motivo_da_queda(visto_em, mesma_porta, agora)
    except Exception as e:
        motivo, detalhe = f"não lido (erro {type(e).__name__})", ""
    registro_processos.registrar("shopee_video", PROCESSO_DA_QUEDA, motivo, detalhe, ok=None, agora=agora)
    _gravar(ultima_queda={"motivo": motivo, "detalhe": detalhe, "voltou_em": agora.strftime("%Y-%m-%d %H:%M:%S")})
    return motivo


def _estado_do_adb(resultado):
    """O estado do adb no endereço guardado, em uma palavra (sem a saída crua, que traz o endereço)."""
    if av._ok(resultado):
        return resultado[1].strip() or "?"
    saida = (resultado[1] if resultado else "").lower()
    for trecho, estado in (("offline", "offline"), ("unauthorized", "não autorizado"), ("not found", "sem conexão")):
        if trecho in saida:
            return estado
    return "sem resposta"


def ler_prazo_da_autorizacao():
    """
    Em quantos dias o Android corta o pareamento do servidor: 0 com a opção OPCAO_DO_PRAZO
    ligada (sem prazo), PRAZO_PADRAO_DIAS sem ela. None sem o celular conectado ou sem
    resposta. Só lê a configuração; não muda nada no celular.
    """
    alvo = endereco()
    if not alvo or shutil.which("adb") is None:
        return None
    r = av._rodar("adb", "-s", alvo, "shell", "settings", "get", "global", CONFIG_DO_PRAZO, timeout=15)
    if not av._ok(r):
        return None
    valor = r[1].strip().lower()
    if valor in ("", "null"):
        return PRAZO_PADRAO_DIAS
    try:
        milissegundos = int(valor)
    except ValueError:
        return None
    return 0 if milissegundos <= 0 else max(1, round(milissegundos / 86_400_000))


def anotar_prazo(forcar=False, agora=None):
    """
    Lê o prazo do pareamento no celular e guarda no banco (prazo_da_autorizacao e
    prazo_lido_em), no máximo uma vez por LER_O_PRAZO_A_CADA; forcar=True lê na hora (o
    painel). O alertas.py avisa o Rafael quando a leitura recente não é 0. Devolve o prazo
    (o lido agora ou o guardado), ou None.
    """
    agora = agora or datetime.now(fuso_horario)
    dados = ler()
    if not forcar:
        try:
            lido_em = datetime.strptime(dados.get("prazo_lido_em") or "", "%Y-%m-%d %H:%M:%S")
            if agora.replace(tzinfo=None) - lido_em < LER_O_PRAZO_A_CADA:
                return dados.get("prazo_da_autorizacao")
        except ValueError:
            pass
    prazo = ler_prazo_da_autorizacao()
    if prazo is not None:
        _gravar(prazo_da_autorizacao=prazo, prazo_lido_em=agora.strftime("%Y-%m-%d %H:%M:%S"))
    return prazo


def descrever_prazo(prazo):
    """O prazo do pareamento em palavras curtas, para o estado e o painel."""
    if prazo is None:
        return "não lido"
    return "sem prazo" if prazo == 0 else f"{prazo} dia(s)"


def descrever_estado():
    """
    A ligação com o celular guardado em uma linha, para o android.yml (estado), só com
    estados e números (o log do Actions é público: nunca o endereço, a porta nem o nome):
    se está na rede privada, se a porta guardada está aberta, o estado do adb nela,
    quantas portas abertas o celular tem, o prazo do pareamento, há quanto tempo ele está
    ligado e os pontos de Wi-Fi com o mesmo nome da rede dele (esses três com o celular
    conectado) e o motivo da última queda, com o detalhe (ultima_queda). Só lê: não conecta
    nem desconecta nada.
    """
    dados = ler()
    if not dados.get("pareado_em") or not dados.get("ip"):
        return "ainda não pareado"
    if shutil.which("adb") is None:
        return "sem o adb no servidor"
    online = {c["ip"]: c["online"] for c in celulares_na_rede()}.get(dados["ip"])
    if not online:
        return "na rede privada: não"
    abertas = portas_abertas(dados["ip"])
    alvo = endereco()
    estado = _estado_do_adb(av._rodar("adb", "-s", alvo, "get-state", timeout=10)) if alvo else "sem porta guardada"
    prazo = ler_prazo_da_autorizacao() if estado == "device" else None
    conectado_agora = ""
    if estado == "device":
        ligado = ligado_ha()
        conectado_agora = (f" | ligado há {_duracao(ligado)}" if ligado is not None else "") + f" | {_wifi_agora()}"
    queda = dados.get("ultima_queda") or {}
    detalhe = f"; {queda['detalhe']}" if queda.get("detalhe") else ""
    return (f"na rede privada: sim | porta guardada: {'aberta' if dados.get('porta') in abertas else 'fechada'} | "
            f"adb: {estado} | portas abertas no celular: {len(abertas)} | "
            f"prazo do pareamento: {descrever_prazo(prazo)}{conectado_agora}"
            + (f" | última queda: {queda['motivo']}{detalhe} (voltou em {queda['voltou_em'][8:10]}/"
               f"{queda['voltou_em'][5:7]} {queda['voltou_em'][11:16]})"
               if queda.get("motivo") and queda.get("voltou_em") else ""))


def ocupado():
    """Algum processo (o robô automático ou o explorar) está com a trava do celular agora?"""
    with trava() as livre:
        return not livre


@contextlib.contextmanager
def trava():
    """
    Um de cada vez no celular. Rende True com a trava na mão e False se outro processo
    (o robô automático ou o explorar) já está tocando nele. O sistema solta a trava
    sozinho se o processo cair no meio.
    """
    os.makedirs(os.path.dirname(ARQUIVO_TRAVA), exist_ok=True)
    with open(ARQUIVO_TRAVA, "w") as arquivo:
        try:
            fcntl.flock(arquivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(arquivo, fcntl.LOCK_UN)

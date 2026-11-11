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
privada, sem o Rafael mandar nada; só a depuração desligada pede a mão dele, e o adb
do celular travado (a porta abre e nada responde), que só volta reiniciando o celular.

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
import io
import json
import os
import re
import secrets
import shutil
import socket
import string
import struct
import time
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
# Segundos para a porta guardada responder quando conferida sozinha (a varredura usa 0,5 s).
PRAZO_DA_PORTA_GUARDADA = 3
# A porta pode aceitar a ligação e o adb do celular não responder nada: travou, e nem o adb do
# servidor reiniciado nem parear de novo resolvem, só reiniciar o celular (04/11/2026: a porta
# abria, também a nova depois de desligar e ligar a depuração, e a conexão não se completava).
# Para saber, o servidor manda à porta o começo da ligação do adb (CNXN) e espera a resposta:
# a Depuração por Wi-Fi pede a ligação cifrada (STLS); sem ela, o adb responde AUTH ou CNXN
# (adb_do_celular_responde).
RESPOSTAS_DO_ADB = (b"STLS", b"AUTH", b"CNXN")
PRAZO_DO_ADB_DO_CELULAR = 5
ADB_DO_CELULAR_TRAVADO = ("o adb do celular não responde na porta aberta (travou, ou a Depuração por Wi-Fi está "
                          "desligada): reinicie o Motorola e ligue de novo a Depuração por Wi-Fi")
# O adb do celular pode responder ao começo da ligação (pacotes pequenos) e a parte cifrada não
# se completar: ela troca os certificados, em pacotes maiores, e o pareamento usa a mesma parte
# (04/11/2026: a conexão e o pareamento pelo QR paravam, com o adb do servidor reiniciado).
# Sem o celular conectado, o estado testa o caminho até ele (rede_ate_o_celular): direto ou pelo
# relay do Tailscale, o ping pequeno e o grande sem fragmentar, e se o certificado do celular
# chega ao servidor. Só estados e números: nunca o endereço.
TAMANHOS_DO_PING = (56, 1200)
PINGS = 3
PRAZO_DO_CERTIFICADO = 8
SEM_RESPOSTA_DO_ADB = "o adb não respondeu"

# Por que o celular saiu: o Android desliga a Depuração por Wi-Fi sozinho quando o Wi-Fi cai,
# quando o celular troca de ponto de Wi-Fi (outro roteador, um repetidor ou a outra frequência do
# mesmo roteador) e quando o celular reinicia. Na volta, o servidor lê no próprio celular qual
# foi (motivo_da_queda): reiniciou, se ele está ligado há menos tempo que desde a última vez em
# que o servidor o viu (visto_em); senão, a última linha do AdbDebuggingManager no registro do
# Android (logcat) que desliga a depuração. Só o motivo fixo vai ao registro e ao banco, nunca a
# linha crua. Pergunta do Rafael (31/10): por que desconectou. DECISOES.md, Trabalho com o Claude.
PROCESSO_DA_QUEDA = "celular: motivo da queda"
# Quando nem o kill-server derruba o adb do servidor (travado de 03/11 a 05/11/2026, sem saber por
# quê), o registro anota há quanto tempo ele rodava e quem o iniciou, pelo grupo do systemd do
# processo (adb_do_servidor): um deploy que reinicia o bot, uma rodada do robô ou um workflow.
# Só estados e números. Pergunta do Rafael (05/11): por que desconectou sozinho.
PROCESSO_DO_ADB_TRAVADO = "celular: adb do servidor derrubado à força"
DONOS_DO_ADB = (("bot_mestre_bot.service", "o bot"), ("robo-shopee-video", "uma rodada do robô"),
                ("session-", "uma conexão SSH (workflow ou teste)"))
# Antes de cada reconexão, o servidor do adb é conferido com uma pergunta simples (a lista de
# aparelhos): sem resposta no prazo, ele travou e é derrubado à força na hora (destravar_servidor_do_adb),
# sem esperar as tentativas de conexão. Derrubado (aqui ou na reconexão), a reconexão insiste até
# RECONEXOES_DEPOIS_DE_DERRUBAR vezes na mesma rodada, com uma pausa entre elas. Pedido do Rafael
# (05/11): evitar que a queda de 03/11 se repita e reconectar à força depois de derrubar.
PRAZO_DO_SERVIDOR_DO_ADB = 8
RECONEXOES_DEPOIS_DE_DERRUBAR = 3
PAUSA_ENTRE_RECONEXOES = 20
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
# A força do sinal da conexão de agora (dBm: perto de -50 é forte; abaixo de uns -75, fraco).
SINAL_DO_WIFI = re.compile(r'mWifiInfo SSID: "[^"\n]*"[^\n]*?RSSI: (?P<rssi>-?\d+)')
PONTO = re.compile(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}")
FREQUENCIA = re.compile(r"(?<![\d.:])(2[4-9]\d\d|[3-6]\d{3}|7[01]\d\d)(?![\d.])")
# A forma de uma linha da busca de redes quando nenhum ponto é achado (o formato do Android pode
# mudar): só o tipo de cada pedaço, nunca o nome da rede, o endereço ou os números.
TIPOS_DA_FORMA = ((re.compile(r"^(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2},?$"), "MAC"),
                  (re.compile(r"^-?\d+,?$"), "NUM"), (re.compile(r"^-?\d+\.\d+,?$"), "DEC"),
                  (re.compile(r"^-?\d+\("), "NUM(..)"), (re.compile(r"^-?\d+[A-Za-z]+,?$"), "NUM+unid"),
                  (re.compile(r"^\["), "[..]"))
# A lista que o Android recusa (permissão, comando desconhecido) só aparece como "deu erro".
ERRO_DA_LISTA = re.compile(r"exception|permission|denied|unknown command", re.IGNORECASE)
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
        return SEM_RESPOSTA_DO_ADB
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


# O pareamento pelo código QR (P149 2): o bot manda o QR, no formato que o Android lê na
# Depuração por Wi-Fi → Parear o dispositivo com um código QR, e o celular abre uma porta de
# pareamento. O QR foi feito para o celular achar o computador no mesmo Wi-Fi (mDNS), o que não
# passa pela rede privada: o servidor procura a porta nova pela rede privada, como no
# reconectar_sozinho, e pareia nela com a senha do QR. O código de 6 dígitos continua de reserva.
# A senha vale só para esse pareamento e nunca vai para o log nem para o banco.
# Decisão do Rafael: DECISOES.md, Shopee Vídeo.
ESPERA_DO_QR = 300
TENTATIVAS_POR_PORTA_DO_QR = 2
# Enquanto o pareamento pelo QR corre, a reconexão espera (reconectar_sozinho): o kill-server dela
# derrubaria o pareamento no meio. A marca (pareando_ate) vence sozinha, com folga além da espera,
# se o bot reiniciar no meio do pareamento.
FOLGA_DO_PAREAMENTO = 60
PAREANDO_PELO_QR = "o celular está sendo pareado pelo QR agora (a reconexão espera o fim do pareamento)"
LETRAS_DO_QR = string.ascii_letters + string.digits


def novo_qr():
    """O nome e a senha de um pareamento pelo QR e o texto do QR: (nome, senha, texto)."""
    nome = "robo-" + "".join(secrets.choice(LETRAS_DO_QR) for _ in range(8))
    senha = "".join(secrets.choice(LETRAS_DO_QR) for _ in range(12))
    return nome, senha, f"WIFI:T:ADB;S:{nome};P:{senha};;"


def imagem_do_qr(texto):
    """O QR em PNG (bytes), grande o bastante para a câmera do Motorola ler de outra tela."""
    import qrcode
    saida = io.BytesIO()
    qrcode.make(texto, box_size=12, border=4).save(saida, format="PNG")
    return saida.getvalue()


def parear_pelo_qr(ip, senha, ja_abertas=(), espera=ESPERA_DO_QR, relogio=time.monotonic, pausa=time.sleep,
                   avisar=lambda etapa, detalhe="": None):
    """
    Procura pela rede privada, por até `espera` segundos, a porta de pareamento que o celular abre
    depois de ler o QR (uma que não estava aberta antes, ja_abertas) e pareia nela com a senha do
    QR. Cada porta nova é tentada até TENTATIVAS_POR_PORTA_DO_QR vezes (a varredura às vezes a
    acha antes de ela aceitar). (True, "") ou (False, motivo). avisar(etapa, detalhe) conta o
    andamento ao painel: "procurando" (o celular ainda não abriu o pareamento), "pareando" (achou
    a porta nova; detalhe = o número da tentativa) e "falhou" (a tentativa não completou; detalhe
    = o motivo). Enquanto isso, a reconexão espera (pareando_ate).
    """
    if shutil.which("adb") is None:
        return False, "o adb não está instalado no servidor"
    ate = datetime.now(fuso_horario) + timedelta(seconds=espera + FOLGA_DO_PAREAMENTO)
    _gravar(pareando_ate=ate.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        avisar("procurando")
        fim, tentadas, ultimo = relogio() + espera, {}, ""
        while relogio() < fim:
            for porta in portas_abertas(ip):
                if porta in ja_abertas or tentadas.get(porta, 0) >= TENTATIVAS_POR_PORTA_DO_QR:
                    continue
                tentadas[porta] = tentadas.get(porta, 0) + 1
                avisar("pareando", str(tentadas[porta]))
                ok, motivo = parear(ip, porta, senha)
                if ok:
                    return True, ""
                ultimo = motivo
                avisar("falhou", motivo)
            pausa(5)
    finally:
        _gravar(pareando_ate="")
    if ultimo:
        return False, f"o celular abriu a porta do pareamento, mas não pareou ({ultimo})"
    return False, ("não achei a porta do pareamento pela rede privada: o QR não foi lido a tempo, ou a porta não "
                   "respondeu")


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


# Os painéis não fazem o Rafael esperar o adb do celular travado: cada pergunta a ele espera o
# prazo inteiro, e o Robô Automático 🤖 e o Celular do Robô 📱 demoravam a abrir (vídeo do Rafael
# de 04/11/2026). Com a ligação falhando há menos disto e o celular não visto depois, eles mostram
# "desconectado" sem perguntar; o robô tenta reconectar a cada rodada, e o Reconectar Celular 🔄
# sempre pergunta.
FALHA_RECENTE = timedelta(minutes=20)


def conectado_no_painel(agora=None):
    """O conectado() dos painéis, sem perguntar ao adb quando a ligação falhou há pouco (FALHA_RECENTE)."""
    dados = ler()
    momento = (agora or datetime.now(fuso_horario)).replace(tzinfo=None)
    limite = (momento - FALHA_RECENTE).strftime("%Y-%m-%d %H:%M:%S")
    visto = dados.get("visto_em") or ""
    if any(quando and quando > visto and quando >= limite
           for quando in (dados.get("falha_em"), dados.get("sem_resposta_em"))):
        return False
    ligado = conectado()
    if not ligado:
        _gravar(sem_resposta_em=momento.strftime("%Y-%m-%d %H:%M:%S"))
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


def porta_responde(ip, porta):
    """A porta aceita conexão agora, conferida sozinha e com mais tempo que na varredura?"""
    return porta in portas_abertas(ip, [porta], prazo=PRAZO_DA_PORTA_GUARDADA)


def _pacote(comando, arg0, arg1, dados=b""):
    """Uma mensagem do adb: o comando (4 letras), os dois números, o tamanho, a soma dos bytes e a marca."""
    numero = int.from_bytes(comando, "little")
    return struct.pack("<6I", numero, arg0, arg1, len(dados), sum(dados), numero ^ 0xFFFFFFFF) + dados


def _pacote_de_conexao():
    """O CNXN com que o adb abre a ligação: versão, tamanho máximo e "host::"."""
    return _pacote(b"CNXN", 0x01000001, 256 * 1024, b"host::\x00")


def _ler(ligacao, tamanho):
    """Até `tamanho` bytes da ligação (menos, se ela fechar antes)."""
    lido = b""
    while len(lido) < tamanho:
        pedaco = ligacao.recv(tamanho - len(lido))
        if not pedaco:
            break
        lido += pedaco
    return lido


def adb_do_celular_responde(ip, porta, prazo=PRAZO_DO_ADB_DO_CELULAR):
    """
    O adb do celular responde na porta? True: respondeu como o adb (RESPOSTAS_DO_ADB);
    False: a porta aceitou a ligação e nada respondeu (ou respondeu outra coisa); None: a
    porta não aceitou. Só lê o começo da resposta e fecha: não conecta o adb nem pede nada.
    """
    try:
        ligacao = socket.create_connection((ip, porta), timeout=prazo)
    except OSError:
        return None
    with ligacao:
        try:
            ligacao.sendall(_pacote_de_conexao())
            resposta = _ler(ligacao, 4)
        except OSError:
            return False
    return resposta in RESPOSTAS_DO_ADB


def certificado_do_celular_chega(ip, porta, prazo=PRAZO_DO_CERTIFICADO):
    """
    Na parte cifrada do adb (depois do STLS), o certificado do celular chega ao servidor? True:
    chegou (e o servidor, que não o conhece, recusa: nada é conectado nem muda no celular); False:
    não chegou no prazo (os pacotes grandes se perdem no caminho); None: sem a parte cifrada (a
    porta não aceitou, o celular não pediu o STLS ou cortou a ligação). A conferência do
    certificado fica ligada: é a recusa dela que mostra que ele chegou.
    """
    import ssl
    try:
        ligacao = socket.create_connection((ip, porta), timeout=prazo)
    except OSError:
        return None
    with ligacao:
        try:
            ligacao.sendall(_pacote_de_conexao())
            if _ler(ligacao, 24)[:4] != b"STLS":
                return None
            ligacao.sendall(_pacote(b"STLS", 0x01000000, 0))
        except OSError:
            return None
        try:
            with ssl.create_default_context().wrap_socket(ligacao, server_hostname="celular-do-robo"):
                return True
        except ssl.SSLCertVerificationError:
            return True
        except TimeoutError:
            return False
        except OSError:
            return None


def caminho_ate_o_celular(ip):
    """Como o Tailscale chega ao celular: "direto, N ms", "pelo relay, N ms" ou "sem resposta"."""
    r = av._rodar("tailscale", "ping", "-c", "3", "--timeout", "5s", ip, timeout=30)
    pongs = [linha for linha in (r[1] if r else "").splitlines() if linha.startswith("pong")]
    if not pongs:
        return "sem resposta"
    tempo = re.search(r" in (\d+(?:\.\d+)?) ?ms", pongs[-1])
    caminho = "pelo relay" if "via DERP" in pongs[-1] else "direto"
    return f"{caminho}, {round(float(tempo.group(1)))} ms" if tempo else caminho


def ping_ao_celular(ip, tamanho):
    """Quantos dos PINGS pings de `tamanho` bytes, sem fragmentar, o celular respondeu; None sem o ping."""
    if shutil.which("ping") is None:
        return None
    r = av._rodar("ping", "-n", "-q", "-c", str(PINGS), "-W", "2", "-M", "do", "-s", str(tamanho), ip,
                  timeout=PINGS * 3 + 5)
    recebidos = re.search(r"(\d+) (?:packets )?received", r[1]) if r else None
    return int(recebidos.group(1)) if recebidos else None


def rede_ate_o_celular(ip, porta_do_adb):
    """O caminho da rede privada até o celular, em uma linha só com estados e números."""
    pings = [ping_ao_celular(ip, tamanho) for tamanho in TAMANHOS_DO_PING]
    ping = ("ping: sem o ping no servidor" if None in pings
            else f"ping pequeno: {pings[0]} de {PINGS}, grande: {pings[1]} de {PINGS}")
    chega = certificado_do_celular_chega(ip, porta_do_adb) if porta_do_adb else None
    certificado = {True: "chega", False: "não chega (os pacotes grandes se perdem no caminho)",
                   None: "não testado"}[chega]
    return f"caminho: {caminho_ate_o_celular(ip)} | {ping} | certificado do celular: {certificado}"


def _grupo_do_processo(pid):
    """O grupo do systemd (cgroup) do processo; "" se não deu para ler."""
    try:
        with open(f"/proc/{pid}/cgroup", encoding="utf-8") as arquivo:
            return arquivo.read()
    except OSError:
        return ""


def adb_do_servidor():
    """
    O servidor do adb rodando agora (o processo "fork-server"): (há quantos segundos ele roda,
    quem o iniciou, pelo grupo do systemd: DONOS_DO_ADB) ou None. Só estados e números.
    """
    r = av._rodar("ps", "-C", "adb", "-o", "pid=,etimes=,args=", timeout=10)
    for linha in (r[1] if av._ok(r) else "").splitlines():
        partes = linha.split(None, 2)
        if len(partes) == 3 and partes[0].isdigit() and partes[1].isdigit() and "fork-server" in partes[2]:
            grupo = _grupo_do_processo(partes[0])
            return int(partes[1]), next((dono for trecho, dono in DONOS_DO_ADB if trecho in grupo), "outro")
    return None


def anotar_adb_travado(travado, voltou, agora=None):
    """Anota no registro o adb do servidor derrubado à força (PROCESSO_DO_ADB_TRAVADO), e se o celular voltou."""
    detalhe = (f"rodava há {_duracao(travado[0])}, iniciado por {travado[1]}" if travado
               else "o processo do servidor do adb não foi achado")
    registro_processos.registrar("shopee_video", PROCESSO_DO_ADB_TRAVADO, "voltou" if voltou else "não voltou",
                                 detalhe, ok=voltou, agora=agora)
    _gravar(adb_derrubado_em=_agora())


def destravar_servidor_do_adb():
    """
    Confere o servidor do adb com uma pergunta simples (a lista de aparelhos); sem resposta em
    PRAZO_DO_SERVIDOR_DO_ADB, ele travou: é derrubado à força (as chaves do pareamento ficam), e o
    próximo comando do adb sobe um novo. (derrubou?, o que adb_do_servidor viu dele).
    """
    if shutil.which("adb") is None or av._rodar("adb", "devices", timeout=PRAZO_DO_SERVIDOR_DO_ADB) is not None:
        return False, None
    travado = adb_do_servidor()
    av._rodar("pkill", "-KILL", "-x", "adb", timeout=10)
    _gravar(adb_derrubado_em=_agora())
    return True, travado


def reconectar_sozinho():
    """
    Reconecta sem o Rafael mandar a porta: primeiro a porta guardada, refazendo a conexão
    do adb (ela pode ficar presa com o celular e a depuração ligados); se não der, procura
    a porta nova da Depuração por Wi-Fi no celular, pela rede privada, e conecta nela.
    Só a depuração desligada, o celular fora da rede, o pareamento vencido ou o adb do
    celular travado (adb_do_celular_responde: aí só reiniciar o celular resolve) impedem.
    (True, modelo) ou (False, motivo em palavras simples, que diz se a porta da depuração
    respondia e se é preciso parear de novo: pede_pareamento). Na volta, anota por que o
    celular tinha saído (anotar_motivo_da_queda).
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if conectado():
        return True, ler().get("modelo") or "celular"
    if (ler().get("pareando_ate") or "") > _agora():
        return False, PAREANDO_PELO_QR
    inicio = _agora()
    derrubou, travado = destravar_servidor_do_adb()
    visto_em = ler().get("visto_em")
    ok, resultado, mesma_porta = _reconectar()
    # Com o adb do servidor derrubado à força (aqui ou dentro da reconexão), a reconexão insiste
    # na mesma rodada, sem esperar a próxima.
    tentativas = 1
    while not ok and tentativas < RECONEXOES_DEPOIS_DE_DERRUBAR and (ler().get("adb_derrubado_em") or "") >= inicio:
        time.sleep(PAUSA_ENTRE_RECONEXOES)
        tentativas += 1
        ok, resultado, mesma_porta = _reconectar()
    if derrubou:
        anotar_adb_travado(travado, ok)
    if ok:
        anotar_motivo_da_queda(visto_em, mesma_porta)
        _gravar(falha="", falha_em="")
    else:
        # O porquê da última reconexão que falhou (o motivo em palavras simples, sem o endereço)
        # fica para o estado do android.yml e para o alertas.py: na suspensão o robô não pausa sem
        # o celular (pedido do Rafael), e só a falha do servidor vira aviso (P155 1).
        _gravar(falha=resultado, falha_em=_agora())
    return ok, resultado


# O começo do motivo da reconexão que falhou com o Motorola na rede privada e a Depuração por Wi-Fi
# dele respondendo: a falha é do servidor (ou do pareamento), não do celular. Na suspensão, ela é a
# única queda que vira aviso ao Rafael (alertas.py, que guarda o mesmo texto; P155 1).
DEPURACAO_RESPONDE = "a Depuração por Wi-Fi responde"


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
    if dados.get("porta") and dados["porta"] not in abertas and porta_responde(dados["ip"], dados["porta"]):
        # A varredura de todas as portas, com o prazo curto, pode perder a porta pela rede privada
        # (04/11/2026: a guardada respondia no estado e não na rodada, e o robô dizia "desligada"
        # sem tentar reiniciar o adb). A guardada é conferida sozinha, com mais tempo.
        abertas = [dados["porta"], *abertas]
    for porta in abertas:
        if porta == dados.get("porta"):
            continue
        ok, resultado = conectar(dados["ip"], porta)
        if ok:
            return True, resultado, False
        motivos.append(resultado)
    # A porta aceita a ligação e o adb não conecta: com o adb do celular calado em todas as
    # portas abertas, quem travou foi ele, e só reiniciar o celular resolve.
    sondas = {porta: adb_do_celular_responde(dados["ip"], porta) for porta in abertas}
    if sondas and all(sonda is False for sonda in sondas.values()):
        return False, ADB_DO_CELULAR_TRAVADO, False
    # A porta nova (a depuração foi desligada e ligada) também não aceita o servidor: não é a
    # porta, é o pareamento.
    vencido = next((m for m in motivos if pede_pareamento(m)), None)
    guardada = dados["porta"] if dados.get("porta") in abertas else None
    novas = [porta for porta, sonda in sondas.items() if sonda and porta != guardada]
    if guardada or (novas and not vencido):
        # A porta da depuração responde e o adb não conecta: o servidor do adb pode ter ficado
        # preso. Reiniciá-lo (as chaves do pareamento ficam) e tentar de novo uma vez, antes de
        # pedir o pareamento: na porta guardada e na nova em que o adb do celular responde.
        av._rodar("adb", "kill-server", timeout=20)
        alvos = ([guardada] if guardada else []) + novas
        for porta in alvos:
            ok, resultado = conectar(dados["ip"], porta)
            if ok:
                return True, resultado, porta == guardada
        if resultado == SEM_RESPOSTA_DO_ADB:
            # Nem assim o adb respondeu: o servidor dele pode ter travado de um jeito que o
            # kill-server não derruba. Derrubado à força (as chaves do pareamento ficam), mais
            # uma tentativa, e o registro anota quem o tinha iniciado (anotar_adb_travado).
            travado = adb_do_servidor()
            av._rodar("pkill", "-KILL", "-x", "adb", timeout=10)
            for porta in alvos:
                ok, resultado = conectar(dados["ip"], porta)
                if ok:
                    anotar_adb_travado(travado, True)
                    return True, resultado, porta == guardada
            anotar_adb_travado(travado, False)
        if pede_pareamento(resultado):
            return False, f"{DEPURACAO_RESPONDE}, mas {resultado}", False
        return False, (f"{DEPURACAO_RESPONDE} no celular, mas o adb não conecta ({resultado}); "
                       "se continuar, parear de novo pelo Celular do Robô"), False
    if vencido:
        return False, f"{DEPURACAO_RESPONDE}, mas {vencido}", False
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


def interpretar_wifi(saida, lista=""):
    """
    A rede do celular no texto do "dumpsys wifi": {"faixa", "pontos", "por_faixa"}, com a faixa
    da conexão de agora e os pontos (endereços diferentes) da última busca de redes que têm o
    mesmo nome da rede dele; None sem a conexão. A busca vem do próprio dumpsys ("Latest scan
    results") e de lista, a saída do "cmd wifi list-scan-results" (o Motorola não põe a busca
    no dumpsys). O nome da rede só é comparado aqui dentro. Sem nenhum ponto, "forma" diz como
    eram as linhas da busca, sem os valores.
    """
    conexao = CONEXAO_DO_WIFI.search(saida or "")
    if not conexao or not conexao.group("nome"):
        return None
    # O nome aparece na coluna da busca, preenchida com espaços até o "[" das proteções, ou
    # depois de "SSID:" ou "SSID=", entre aspas: ele termina em dois espaços, num "[", numa
    # vírgula ou no fim da linha (assim "Casa" não conta "Casa 2").
    nome = re.compile(r'(?<=[\s=:])"?' + re.escape(conexao.group("nome")) + r'"?(?=\s{2,}|\s*\[|\s*$|,)')
    do_dumpsys = _linhas_da_busca(saida)
    da_lista = [linha for linha in (lista or "").splitlines() if linha.strip()]
    linhas = do_dumpsys + da_lista
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
    sinal = SINAL_DO_WIFI.search(saida or "")
    if sinal and -120 < int(sinal.group("rssi")) < 0:
        wifi["sinal"] = int(sinal.group("rssi"))
    if not pontos:
        com_ponto = [linha for linha in linhas if PONTO.search(linha)]
        erro = " (a lista deu erro)" if ERRO_DA_LISTA.search(lista or "") else ""
        wifi["forma"] = (f"busca de redes: {len(do_dumpsys)} linha(s) no dumpsys, {len(da_lista)} na lista{erro}, "
                         f"{len(com_ponto)} com ponto" + (f"; forma: {_forma(com_ponto[0])}" if com_ponto else ""))
    return wifi


def ler_wifi():
    """
    interpretar_wifi do "dumpsys wifi" e da lista da última busca de redes do celular (só lê,
    nunca pede uma busca nova); None sem resposta.
    """
    alvo = endereco()
    r = av._rodar("adb", "-s", alvo, "shell", "dumpsys", "wifi", timeout=30) if alvo else None
    if not av._ok(r):
        return None
    lista = av._rodar("adb", "-s", alvo, "shell", "cmd", "wifi", "list-scan-results", timeout=30)
    return interpretar_wifi(r[1], lista[1] if lista else "")


def descrever_wifi(wifi):
    """A rede do celular em palavras curtas, só com a faixa e os números."""
    if not wifi:
        return "Wi-Fi não lido"
    texto = (f"Wi-Fi em {wifi['faixa']}" + (f", sinal {wifi['sinal']} dBm" if wifi.get("sinal") is not None else "")
             + f", {wifi['pontos']} ponto(s) com o mesmo nome")
    if wifi["pontos"]:
        texto += " (" + ", ".join(f"{faixa}: {n}" for faixa, n in wifi["por_faixa"].items()) + ")"
    elif wifi.get("forma"):
        texto += f" ({wifi['forma']})"
    return texto


def resumo_do_wifi(wifi):
    """A faixa e o sinal em poucas palavras ("5 GHz, -61 dBm"), para guardar e mostrar na volta."""
    if not wifi:
        return ""
    return wifi["faixa"] + (f", {wifi['sinal']} dBm" if wifi.get("sinal") is not None else "")


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
    quanto tempo ficou fora, há quanto tempo está ligado e, quando não reiniciou, a faixa e o
    sinal do Wi-Fi na última leitura antes da queda (anotar_wifi, de hora em hora) e na volta,
    com os pontos de Wi-Fi com o mesmo nome da rede dele)
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
    antes = ler().get("ultimo_wifi") or {}
    if antes.get("resumo"):
        detalhe += f"; antes da queda ({str(antes.get('lido_em') or '')[11:16]}): {antes['resumo']}"
    detalhe += f"; na volta: {_wifi_agora()}"
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
    anotar_wifi(agora)
    return prazo


def anotar_wifi(agora=None):
    """
    Guarda a faixa e o sinal do Wi-Fi de agora (ultimo_wifi), para a volta de uma queda mostrar
    como estava a rede antes dela (sinal fraco, outra faixa). Só lê; um erro aqui não atrapalha.
    """
    agora = agora or datetime.now(fuso_horario)
    try:
        resumo = resumo_do_wifi(ler_wifi())
    except Exception:
        # Sem a leitura desta hora, fica a anterior; a volta mostra quando ela foi lida.
        return
    if resumo:
        _gravar(ultimo_wifi={"resumo": resumo, "lido_em": agora.strftime("%Y-%m-%d %H:%M:%S")})


def descrever_prazo(prazo):
    """O prazo do pareamento em palavras curtas, para o estado e o painel."""
    if prazo is None:
        return "não lido"
    return "sem prazo" if prazo == 0 else f"{prazo} dia(s)"


# A tela do celular acesa ou apagada, e a carga e o Manter ativado quando ela está apagada (11/11/2026:
# das 06:44 às 08:14 a leitura da tela trazia só o Moto Display): no carregador, o Manter ativado deixa
# a tela sempre acesa (DECISOES.md, Shopee Vídeo). Fora do carregador ela apaga sozinha; no carregador
# com ele ligado, alguém a apagou no botão. Tudo pelo adb, só lendo: não muda nada no celular e não
# passa pelo app (o robô confere antes de começar, sem tocar no celular).
ESTADO_DA_TELA = re.compile(r"^\s*mWakefulness=(\w+)", re.MULTILINE)
TELA_LIGADA = ("Awake", "Dreaming")
TELA_DESLIGADA = ("Asleep", "Dozing")
CONFIG_DA_TELA_ACESA = "stay_on_while_plugged_in"


def interpretar_tela(energia_do_android):
    """Do "dumpsys power": True com a tela acesa, False apagada (ou só o relógio do Motorola), None sem o estado."""
    estado = ESTADO_DA_TELA.search(energia_do_android or "")
    if not estado:
        return None
    return True if estado.group(1) in TELA_LIGADA else False if estado.group(1) in TELA_DESLIGADA else None


def tela_acesa():
    """interpretar_tela do celular conectado; None sem o celular ou sem resposta."""
    alvo = endereco()
    if not alvo or shutil.which("adb") is None:
        return None
    r = av._rodar("adb", "-s", alvo, "shell", "dumpsys", "power", timeout=15)
    return interpretar_tela(r[1]) if av._ok(r) else None
LIGADO_NA_ENERGIA = re.compile(r"^\s*(?:AC|USB|Wireless|Dock) powered:\s*true\s*$", re.IGNORECASE | re.MULTILINE)
NIVEL_DA_BATERIA = re.compile(r"^\s*level:\s*(\d+)\s*$", re.MULTILINE)


def interpretar_energia(bateria, manter_ativado):
    """
    O que o "dumpsys battery" e a configuração do Manter ativado (CONFIG_DA_TELA_ACESA: 0 ou vazia
    é desligado; os outros números, os tipos de carregador em que a tela não apaga) dizem:
    {"carregador": no carregador?, "bateria": %, "manter_ativado": ligado?}, com None no que não veio.
    """
    texto = bateria or ""
    carregador = bool(LIGADO_NA_ENERGIA.search(texto)) if re.search(r"powered:", texto, re.IGNORECASE) else None
    nivel = NIVEL_DA_BATERIA.search(texto)
    valor = (manter_ativado or "").strip().lower()
    manter = int(valor) > 0 if valor.isdigit() else False if valor == "null" else None
    return {"carregador": carregador, "bateria": int(nivel.group(1)) if nivel else None, "manter_ativado": manter}


def ler_energia():
    """interpretar_energia do celular conectado; None sem o celular ou sem resposta."""
    alvo = endereco()
    if not alvo or shutil.which("adb") is None:
        return None
    r = av._rodar("adb", "-s", alvo, "shell", "dumpsys", "battery", timeout=15)
    if not av._ok(r):
        return None
    manter = av._rodar("adb", "-s", alvo, "shell", "settings", "get", "global", CONFIG_DA_TELA_ACESA, timeout=15)
    return interpretar_energia(r[1], manter[1] if av._ok(manter) else "")


def descrever_energia(energia):
    """A carga e o Manter ativado em palavras fixas e números (o motivo da parada e o registro)."""
    if not energia:
        return "carga não lida"
    partes = [{True: "no carregador", False: "fora do carregador"}.get(energia.get("carregador"),
                                                                         "carregador não lido")]
    if energia.get("bateria") is not None:
        partes.append(f"bateria {energia['bateria']}%")
    partes.append({True: "Manter ativado ligado", False: "Manter ativado desligado"}.get(
        energia.get("manter_ativado"), "Manter ativado não lido"))
    return ", ".join(partes)


def descrever_estado():
    """
    A ligação com o celular guardado em uma linha, para o android.yml (estado), só com
    estados e números (o log do Actions é público: nunca o endereço, a porta nem o nome):
    se está na rede privada, se a porta guardada está aberta, o estado do adb nela,
    quantas portas abertas o celular tem, o prazo do pareamento, há quanto tempo ele está
    ligado e os pontos de Wi-Fi com o mesmo nome da rede dele (esses três com o celular
    conectado), em quantas portas abertas o adb do celular responde e o caminho da rede até
    ele (esses dois com ele desconectado: rede_ate_o_celular) e o motivo da última queda, com
    o detalhe (ultima_queda). Só lê: não conecta nem desconecta nada.
    """
    dados = ler()
    if not dados.get("pareado_em") or not dados.get("ip"):
        return "ainda não pareado"
    if shutil.which("adb") is None:
        return "sem o adb no servidor"
    falha = dados.get("falha_em") or ""
    falha = (f" | última reconexão que falhou: {dados['falha']} ({falha[8:10]}/{falha[5:7]} {falha[11:16]})"
             if dados.get("falha") and falha else "")
    online = {c["ip"]: c["online"] for c in celulares_na_rede()}.get(dados["ip"])
    if not online:
        return "na rede privada: não" + falha
    abertas = portas_abertas(dados["ip"])
    alvo = endereco()
    estado = _estado_do_adb(av._rodar("adb", "-s", alvo, "get-state", timeout=10)) if alvo else "sem porta guardada"
    prazo = ler_prazo_da_autorizacao() if estado == "device" else None
    # Sem o adb conectado: em quantas portas abertas o adb do celular responde (em nenhuma, ele
    # travou ou a porta não é a da depuração; adb_do_celular_responde).
    respondem = [porta for porta in abertas if adb_do_celular_responde(dados["ip"], porta)] \
        if estado != "device" else []
    sonda = (f" | adb do celular responde em {len(respondem)} de {len(abertas)}"
             if estado != "device" and abertas else "")
    if estado != "device":
        sonda += f" | {rede_ate_o_celular(dados['ip'], respondem[0] if respondem else None)}"
    conectado_agora = ""
    if estado == "device":
        ligado = ligado_ha()
        conectado_agora = (f" | ligado há {_duracao(ligado)}" if ligado is not None else "") + f" | {_wifi_agora()}"
    queda = dados.get("ultima_queda") or {}
    detalhe = f"; {queda['detalhe']}" if queda.get("detalhe") else ""
    return (f"na rede privada: sim | porta guardada: {'aberta' if dados.get('porta') in abertas else 'fechada'} | "
            f"adb: {estado} | portas abertas no celular: {len(abertas)}{sonda} | "
            f"prazo do pareamento: {descrever_prazo(prazo)}{conectado_agora}"
            + (f" | última queda: {queda['motivo']}{detalhe} (voltou em {queda['voltou_em'][8:10]}/"
               f"{queda['voltou_em'][5:7]} {queda['voltou_em'][11:16]})"
               if queda.get("motivo") and queda.get("voltou_em") else "")
            + falha)


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

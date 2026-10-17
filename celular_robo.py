"""
O celular de verdade do Rafael, onde o robô da Shopee Vídeo vai postar (plano do
celular no roteiro_robo_shopee_video.md). O servidor fala com ele pelo adb, pela
rede privada (Tailscale): o celular fica em casa, com a "Depuração por Wi-Fi" ligada.

Quem usa:
- painel_shopee_video (botão Celular do Robô 📱): acha o celular na rede privada,
  pareia com o código que o Rafael manda no privado do bot e conecta;
- postador_shopee_video (--celular): explora o app da Shopee no celular.

O código de pareamento vale só enquanto a janela dele está aberta no celular e passa
só pelo bot: nunca vai para o log nem para o banco. No banco (chave CHAVE) ficam o
nome do celular na rede, o endereço e a porta da conexão, o modelo e as datas.
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import json
import re
import shutil
from datetime import datetime

import android_virtual as av
import db
from fuso import fuso_horario

CHAVE = "celular_robo"


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
                           ("timed out", "o celular não respondeu: confira o Tailscale e o Wi-Fi dele"),
                           ("no route", "o celular não respondeu: confira o Tailscale e o Wi-Fi dele"),
                           ("unauthorized", "o celular ainda não autorizou este servidor")):
        if trecho in saida:
            return motivo
    return "o adb não conseguiu (tente de novo)"


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
    """O adb fala com o celular agora?"""
    alvo = endereco()
    if not alvo or shutil.which("adb") is None:
        return False
    # Prazo curto: a tela do celular no bot espera esta resposta.
    av._rodar("adb", "connect", alvo, timeout=10)
    r = av._rodar("adb", "-s", alvo, "get-state", timeout=10)
    return av._ok(r) and r[1].strip() == "device"

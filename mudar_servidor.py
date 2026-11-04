#!/usr/bin/env python3
"""
O kit de mudança de servidor: leva os robôs do servidor de agora para um servidor novo, com os
dados, as chaves, o pareamento do celular do robô e os vídeos dos rascunhos. Roda no GitHub
(mudar_servidor.yml), falando por SSH com os dois: o de agora pelos segredos ORACLE_HOST,
ORACLE_USER e ORACLE_SSH_KEY, e o novo pelos NOVO_HOST, NOVO_USER e NOVO_SSH_KEY. Pedido do
Rafael (P147 1): DECISOES.md, Monitor, deploy e servidor. O passo a passo dele fica no
MUDAR_DE_SERVIDOR.md.

    python3 mudar_servidor.py conferir   # só lê os dois servidores
    python3 mudar_servidor.py preparar   # instala no novo, sem os dados e sem ligar os robôs
    python3 mudar_servidor.py mudar      # para o de agora, leva tudo e liga o novo
    python3 mudar_servidor.py voltar     # desfaz a mudança (antes de trocar os segredos)

Os dois nunca ficam ligados juntos (o mesmo bot e as mesmas sessões do Telethon em dois
lugares se atrapalham): os robôs do de agora param, e saem do início automático, antes de os
do novo ligarem, e a pasta do projeto dele vira PASTA_ANTIGA, para nenhum deploy ou workflow
religá-los lá até os segredos ORACLE_* passarem a ser os do novo. Se o novo não subir, o de
agora volta sozinho. O que passa de um para o outro vai pelo SSH, sem ser gravado no GitHub.

Só usa a biblioteca padrão: no GitHub roda sem o venv. O log é público: só estados, nomes
fixos e números, nunca o endereço dos servidores.
"""
import os
import subprocess
import sys
import time

from servicos_afetados import SERVICOS as _SERVICOS

SERVICOS = tuple(_SERVICOS)
# A rodada do robô da Shopee Vídeo, numa unidade própria do systemd (painel_shopee_video).
UNIDADE_DA_RODADA = "robo-shopee-video"
PASTA = "~/shopee"
PASTA_ANTIGA = "~/shopee.antes_da_mudanca"
PACOTE_NO_NOVO = "~/backups/da_mudanca.tar.gz"
# O que o servidor novo precisa do sistema (o resto vem do requirements.txt, no venv). O
# Tailscale e o cloudflared se instalam na hora em que são pedidos (android_virtual.py).
PACOTES = ("python3", "python3-venv", "python3-pip", "git", "ffmpeg", "adb", "sqlite3", "curl")
INSTALADOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servicos_linux", "instalar_servidor.sh")
ESPERA_DA_RODADA = 15 * 60
# As tarefas do crontab do usuário (postas à mão; o código não põe nenhuma) vão junto. No de
# agora, ficam guardadas de lado desde que os robôs param, para nada rodar nos dois servidores.
CRONTAB_GUARDADO = "~/crontab.antes_da_mudanca"
ESPERA_DOS_ROBOS = 40


class Falha(Exception):
    """Um passo que não deu certo: a mensagem é um rótulo fixo, para o log público."""


class Servidor:
    """Um dos servidores, por SSH (a chave num arquivo só do dono, no GitHub)."""

    def __init__(self, nome, host, usuario, chave):
        self.nome, self.host, self.usuario, self.chave = nome, host, usuario, chave

    def ssh(self, comando):
        return ["ssh", "-i", self.chave, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
                "-o", "ConnectTimeout=20", "-o", "LogLevel=ERROR", f"{self.usuario}@{self.host}", comando]

    def rodar(self, comando, entrada=None, tempo=600):
        """(código de saída, saída em texto) do comando no servidor."""
        try:
            r = subprocess.run(self.ssh(comando), input=entrada, capture_output=True, timeout=tempo)
        except subprocess.TimeoutExpired:
            return 124, ""
        return r.returncode, r.stdout.decode("utf-8", "replace").strip()

    def ok(self, comando, entrada=None, tempo=600):
        return self.rodar(comando, entrada, tempo)[0] == 0


def transferir(de, comando_de, para, comando_para, tempo=3600):
    """
    O que o comando_de escreve no servidor `de` vai direto para o comando_para no `para`, pelo
    GitHub, sem passar pelo disco dele. True se os dois lados terminaram bem.
    """
    origem = subprocess.Popen(de.ssh(comando_de), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    destino = subprocess.Popen(para.ssh(comando_para), stdin=origem.stdout, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    origem.stdout.close()
    try:
        fim_destino = destino.wait(timeout=tempo)
        fim_origem = origem.wait(timeout=60)
    except subprocess.TimeoutExpired:
        origem.kill()
        destino.kill()
        return False
    return fim_origem == 0 and fim_destino == 0


def servidores():
    """(o de agora, o novo ou None) pelos segredos no ambiente; as chaves vão para arquivos 0600."""
    def um(nome, prefixo):
        host, usuario, chave = (os.environ.get(f"{prefixo}_{campo}", "").strip()
                                for campo in ("HOST", "USER", "SSH_KEY"))
        if not (host and usuario and chave):
            return None
        caminho = os.path.join(os.path.expanduser("~"), ".ssh", f"chave_{nome}")
        os.makedirs(os.path.dirname(caminho), mode=0o700, exist_ok=True)
        descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descritor, "w") as arquivo:
            arquivo.write(chave + "\n")
        return Servidor(nome, host, usuario, caminho)
    return um("de agora", "ORACLE"), um("novo", "NOVO")


def _servicos():
    return " ".join(SERVICOS)


# --- conferir ---

def conferir(agora, novo):
    """Só lê: o que cada servidor tem, para saber se a mudança pode começar."""
    linhas = []
    if agora is None:
        raise Falha("faltam os segredos ORACLE_* do servidor de agora")
    linhas.append("== Servidor de agora")
    linhas += _como_esta(agora, com_dados=True)
    linhas.append("== Servidor novo")
    if novo is None:
        linhas.append("segredos NOVO_HOST, NOVO_USER e NOVO_SSH_KEY: ainda não cadastrados no GitHub")
    else:
        linhas += _como_esta(novo, com_dados=False)
    return linhas


def _como_esta(servidor, com_dados):
    codigo, _ = servidor.rodar("true", tempo=60)
    if codigo != 0:
        return ["acesso por SSH: não respondeu"]
    linhas = ["acesso por SSH: ok"]
    _, sistema = servidor.rodar("(. /etc/os-release && echo \"$PRETTY_NAME\") ; uname -m")
    linhas.append("sistema: " + " | ".join(sistema.splitlines()[:2]))
    linhas.append("sudo sem senha: " + ("sim" if servidor.ok("sudo -n true") else "não"))
    _, livre = servidor.rodar("df -h ~ | awk 'NR==2 {print $4 \" livres de \" $2}'")
    linhas.append(f"disco: {livre}")
    faltam = [p for p in PACOTES if not servidor.ok(f"dpkg -s {p} >/dev/null 2>&1")]
    linhas.append("pacotes do sistema: " + ("todos" if not faltam else "faltam " + ", ".join(faltam)))
    for programa in ("tailscale", "cloudflared"):
        linhas.append(f"{programa}: " + ("instalado" if servidor.ok(f"command -v {programa} >/dev/null")
                                         else "não (instala na hora em que for pedido)"))
    linhas.append("pasta do projeto: " + ("sim" if servidor.ok(f"test -d {PASTA}/.git") else "não")
                  + (" | pasta de antes da mudança: sim" if servidor.ok(f"test -d {PASTA_ANTIGA}") else ""))
    linhas.append("venv: " + ("sim" if servidor.ok(f"test -x {PASTA}/venv/bin/python3") else "não"))
    _, ativos = servidor.rodar(" ; ".join(f"systemctl is-active {s}" for s in SERVICOS))
    estados = ativos.splitlines()
    linhas.append("robôs: " + ", ".join(f"{s} {e}" for s, e in zip(SERVICOS, estados)))
    if com_dados:
        _, rodada = servidor.rodar(f"systemctl list-units '{UNIDADE_DA_RODADA}-*' --state=active --no-legend "
                                   "| wc -l")
        linhas.append(f"rodada do robô da Shopee Vídeo agora: {rodada or '?'}")
        _, tamanhos = servidor.rodar(f"du -sh {PASTA}/banco_dados.db ~/shopee_video 2>/dev/null | awk '{{print $1}}'")
        linhas.append("tamanhos (banco, vídeos dos rascunhos): " + ", ".join(tamanhos.splitlines()))
        for nome, caminho in (("chave das cópias cifradas", "~/.config/registro_admins.chave"),
                              ("chave do adb (pareamento do celular)", "~/.android/adbkey"),
                              ("senha da cópia do backup", "~/.config/backup_fora.chave")):
            linhas.append(f"{nome}: " + ("sim" if servidor.ok(f"test -f {caminho}") else "não"))
        _, tarefas = servidor.rodar("crontab -l 2>/dev/null | grep -cv '^#' || true")
        linhas.append(f"tarefas no crontab: {tarefas or 0} (vão junto na mudança)"
                      + (" | guardadas de lado: sim" if servidor.ok(f"test -f {CRONTAB_GUARDADO}") else ""))
    return linhas


# --- preparar ---

def preparar(novo, chave_tailscale=""):
    """Instala no servidor novo o sistema, o código, o venv e os serviços, sem ligar os robôs."""
    if novo is None:
        raise Falha("faltam os segredos NOVO_HOST, NOVO_USER e NOVO_SSH_KEY")
    if any(novo.ok(f"systemctl is-active --quiet {s}") for s in SERVICOS):
        raise Falha("o servidor novo já está com robôs ligados")
    with open(INSTALADOR, "rb") as arquivo:
        instalador = arquivo.read()
    linhas = ["== Instalando no servidor novo"]
    codigo, saida = novo.rodar(f"PACOTES='{' '.join(PACOTES)}' bash -s", entrada=instalador, tempo=3600)
    linhas += saida.splitlines()[-12:]
    if codigo != 0:
        raise Falha("a instalação no servidor novo não terminou")
    if chave_tailscale:
        codigo, saida = novo.rodar(f"read -r TS_KEY; export TS_KEY; cd {PASTA} && venv/bin/python3 android_virtual.py "
                                   "--tailscale", entrada=(chave_tailscale + "\n").encode(), tempo=1200)
        linhas += saida.splitlines()[-4:]
        linhas.append("rede privada do celular: " + ("ligada" if codigo == 0 else "não ligou"))
    else:
        linhas.append("rede privada do celular: falta o segredo TAILSCALE_AUTHKEY (fica para depois)")
    linhas.append("robôs no servidor novo: instalados, ainda desligados (a mudança liga)")
    return linhas


# --- mudar e voltar ---

def mudar(agora, novo, esperar=time.sleep):
    """Para o de agora, leva os dados e liga o novo; se o novo não subir, o de agora volta."""
    if agora is None or novo is None:
        raise Falha("faltam os segredos de um dos servidores")
    if not novo.ok(f"test -x {PASTA}/venv/bin/python3"):
        raise Falha("o servidor novo ainda não foi preparado (rode o preparar antes)")
    if any(novo.ok(f"systemctl is-active --quiet {s}") for s in SERVICOS):
        raise Falha("o servidor novo já está com robôs ligados")
    if novo.ok("crontab -l >/dev/null 2>&1"):
        # O voltar apaga o crontab do novo: ele tem de ser só a cópia do de agora.
        raise Falha("o servidor novo já tem tarefas no crontab")
    if not agora.ok(f"test -d {PASTA}"):
        raise Falha("o servidor de agora não tem a pasta do projeto (a mudança já foi feita?)")
    linhas = ["== Mudança"]
    # Daqui em diante, qualquer passo que falhe devolve os robôs ao servidor de agora.
    try:
        _parar_o_de_agora(agora, esperar, linhas)
        _levar_os_dados(agora, novo, linhas)
        if not agora.ok(f"mv {PASTA} {PASTA_ANTIGA}"):
            raise Falha("a pasta do servidor de agora não foi guardada de lado")
        linhas.append("servidor de agora: pasta do projeto guardada de lado (nada religa os robôs lá)")
        _ligar(novo, esperar, linhas)
    except Falha as e:
        linhas.append(f"❌ {e}: os robôs voltam ao servidor de agora")
        linhas += _devolver(agora, novo, esperar)
        raise Falha(f"{e} (os robôs voltaram ao servidor de agora)") from None
    linhas.append("✅ Robôs no servidor novo. Falta só trocar no GitHub os segredos ORACLE_HOST, ORACLE_USER e "
                  "ORACLE_SSH_KEY pelos do servidor novo e apagar os NOVO_* (MUDAR_DE_SERVIDOR.md)")
    return linhas


def _parar_o_de_agora(agora, esperar, linhas):
    # O bot_mestre é quem chama as rodadas do robô: ele para primeiro, e a rodada que estava
    # tocando no celular termina sozinha.
    if not agora.ok("sudo -n systemctl stop bot_mestre_bot"):
        raise Falha("o bot do servidor de agora não parou")
    fim = time.monotonic() + ESPERA_DA_RODADA
    while True:
        _, rodando = agora.rodar(f"systemctl list-units '{UNIDADE_DA_RODADA}-*' --state=active --no-legend | wc -l")
        if rodando.strip() in ("", "0"):
            break
        if time.monotonic() >= fim:
            raise Falha("a rodada do robô da Shopee Vídeo não terminou em 15 min")
        esperar(20)
    if not agora.ok(f"sudo -n systemctl stop {_servicos()} && sudo -n systemctl disable --quiet {_servicos()}"):
        raise Falha("os robôs do servidor de agora não pararam")
    linhas.append("servidor de agora: robôs parados e fora do início automático")
    if agora.ok("crontab -l >/dev/null 2>&1"):
        if not agora.ok(f"crontab -l > {CRONTAB_GUARDADO} && crontab -r"):
            raise Falha("as tarefas do crontab do servidor de agora não foram guardadas de lado")
        linhas.append("servidor de agora: tarefas do crontab guardadas de lado")


def _levar_os_dados(agora, novo, linhas):
    codigo, saida = agora.rodar(f"cd {PASTA} && venv/bin/python3 backup_dados.py >/dev/null && "
                                "ls -1t ~/backups/shopee_backup_*.tar.gz | head -1", tempo=1200)
    pacote = saida.strip()
    if codigo != 0 or not pacote:
        raise Falha("o backup do servidor de agora não saiu")
    if not transferir(agora, f"cat {pacote}", novo, f"mkdir -p ~/backups && umask 077 && cat > {PACOTE_NO_NOVO}"):
        raise Falha("o backup não chegou ao servidor novo")
    linhas.append("dados (banco, sessões, configurações, .env e as chaves): levados")
    if agora.ok("test -f ~/.config/backup_fora.chave"):
        # A mesma senha da cópia do backup: o Rafael não precisa guardar outra.
        if not transferir(agora, "cat ~/.config/backup_fora.chave", novo,
                          "mkdir -p -m 700 ~/.config && umask 077 && cat > ~/.config/backup_fora.chave"):
            raise Falha("a senha da cópia do backup não chegou ao servidor novo")
        linhas.append("senha da cópia do backup: levada (continua a mesma)")
    if agora.ok("test -d ~/shopee_video"):
        if not transferir(agora, "tar czf - -C ~ shopee_video", novo, "tar xzf - -C ~"):
            raise Falha("os vídeos dos rascunhos não chegaram ao servidor novo")
        linhas.append("vídeos e prints dos rascunhos: levados")
    if agora.ok(f"test -f {CRONTAB_GUARDADO}"):
        if not transferir(agora, f"cat {CRONTAB_GUARDADO}", novo, "crontab -"):
            raise Falha("as tarefas do crontab não chegaram ao servidor novo")
        linhas.append("tarefas do crontab: levadas")
    if not novo.ok(f"cd {PASTA} && git pull -q --ff-only && venv/bin/pip install -q --no-cache-dir -r requirements.txt "
                   f"&& venv/bin/python3 backup_dados.py restaurar {PACOTE_NO_NOVO} {PASTA}", tempo=1800):
        raise Falha("os dados não foram abertos no servidor novo")
    linhas.append("servidor novo: código em dia e dados abertos no lugar")


def _ligar(servidor, esperar, linhas):
    if not servidor.ok(f"sudo -n systemctl enable --quiet --now {_servicos()}"):
        raise Falha("os robôs do servidor novo não ligaram")
    esperar(ESPERA_DOS_ROBOS)
    _, estados = servidor.rodar(" ; ".join(f"systemctl is-active {s}" for s in SERVICOS))
    caidos = [s for s, e in zip(SERVICOS, estados.splitlines() + [""] * len(SERVICOS)) if e.strip() != "active"]
    if caidos:
        raise Falha("robôs que não ficaram ligados no servidor novo: " + ", ".join(caidos))
    linhas.append(f"servidor {servidor.nome}: os {len(SERVICOS)} robôs ligados")


def _devolver(agora, novo, esperar):
    """Desliga o novo e religa o de agora, com a pasta de volta ao lugar."""
    linhas = []
    novo.rodar(f"sudo -n systemctl disable --quiet --now {_servicos()}")
    novo.rodar("crontab -r 2>/dev/null || true")              # o do novo é só a cópia do de agora
    if agora.ok(f"test -d {PASTA_ANTIGA} && ! test -e {PASTA}"):
        agora.rodar(f"mv {PASTA_ANTIGA} {PASTA}")
    if agora.ok(f"test -f {CRONTAB_GUARDADO}"):
        if agora.ok(f"crontab {CRONTAB_GUARDADO} && rm -f {CRONTAB_GUARDADO}"):
            linhas.append("servidor de agora: tarefas do crontab de volta")
        else:
            linhas.append("❌ as tarefas do crontab do servidor de agora não voltaram")
    try:
        _ligar(agora, esperar, linhas)
    except Falha as e:
        linhas.append(f"❌ {e}")
    return linhas


def voltar(agora, novo, esperar=time.sleep):
    """Desfaz a mudança: desliga o novo e religa o de agora (antes de trocar os segredos)."""
    if agora is None or novo is None:
        raise Falha("faltam os segredos de um dos servidores")
    if not agora.ok(f"test -d {PASTA} || test -d {PASTA_ANTIGA}"):
        raise Falha("o servidor de agora não tem a pasta do projeto")
    linhas = ["== Volta ao servidor de agora"] + _devolver(agora, novo, esperar)
    if any(linha.startswith("❌") for linha in linhas):
        raise Falha("os robôs não voltaram ao servidor de agora")
    return linhas


ACOES = {"conferir": lambda a, n: conferir(a, n),
         "preparar": lambda a, n: preparar(n, os.environ.get("TAILSCALE_AUTHKEY", "").strip()),
         "mudar": lambda a, n: mudar(a, n),
         "voltar": lambda a, n: voltar(a, n)}


def main(argumentos):
    if len(argumentos) != 1 or argumentos[0] not in ACOES:
        print(f"uso: python3 mudar_servidor.py {'|'.join(ACOES)}")
        return 2
    agora, novo = servidores()
    try:
        for linha in ACOES[argumentos[0]](agora, novo):
            print(linha)
    except Falha as e:
        print(f"❌ {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""
Fuso horário único de todos os robôs: America/Sao_Paulo.

Importar este módulo já trava o processo no horário de Brasília (variável TZ +
time.tzset()); não há função para chamar. Por viajar com o repositório, trocar
de servidor não exige ajustar o relógio do sistema. Todo robô importa daqui
antes de calcular qualquer data ou hora.

Aplicar o fuso aqui e também no servidor não "soma" nada: o kernel guarda o
tempo em UTC e o fuso só decide como esse número vira texto.

Também define o formato de log comum a todos os robôs (configurar_logs), com o
offset (-0300) dentro de cada linha.
"""
import os
import time
import logging

from zoneinfo import ZoneInfo

FUSO_STR = "America/Sao_Paulo"

os.environ["TZ"] = FUSO_STR
time.tzset()

fuso_horario = ZoneInfo(FUSO_STR)

FORMATO_LOG = "%(asctime)s.%(msecs)03d " + time.strftime("%z") + " - %(message)s"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"

# configurar_logs pode ser chamado duas vezes no mesmo processo: o motor_userbot
# roda como robô próprio e também é importado pelo bot_mestre (via painel_espelhos).
# Só a primeira chamada configura; as outras só recebem o logger.
_LOGS_CONFIGURADOS = False


def fuso_do_servidor():
    """
    Nome do fuso configurado no sistema operacional. Serve só para o log de boot.

    Lê primeiro o link /etc/localtime, que é o que o systemd (e o journalctl)
    usa de verdade. O /etc/timezone é legado do Debian e o timedatectl não o
    atualiza, então pode continuar dizendo "Etc/UTC" para sempre.
    """
    try:
        caminho = os.path.realpath("/etc/localtime")
        partes = caminho.split("/zoneinfo/")
        if len(partes) > 1:
            return partes[1]
    except Exception:
        pass
    try:
        with open("/etc/timezone", encoding="utf-8") as arquivo:
            valor = arquivo.read().strip()
            if valor:
                return valor
    except Exception:
        pass
    return "desconhecido"


def configurar_logs(nome=None, nivel=logging.INFO):
    """
    Configura o log do processo no formato comum e devolve o logger `nome`.

    Usa force=True para passar por cima da configuração que motor_filas e utils
    fazem ao serem importados. Na primeira chamada registra no log o fuso do
    processo e o do servidor; se forem diferentes, avisa que a hora da margem
    do journalctl é a do servidor e que a confiável é a de dentro da linha.
    """
    global _LOGS_CONFIGURADOS
    logger = logging.getLogger(nome or "fuso")
    if _LOGS_CONFIGURADOS:
        return logger
    _LOGS_CONFIGURADOS = True

    logging.basicConfig(
        level=nivel,
        format=FORMATO_LOG,
        datefmt=FORMATO_DATA,
        force=True,
    )

    servidor = fuso_do_servidor()
    logger.info(
        f"🕐 [Fuso] Processo travado em {FUSO_STR} ({time.strftime('%z')}). "
        f"Relógio do servidor: {servidor}."
    )
    if FUSO_STR != servidor:
        logger.info(
            "🕐 [Fuso] O journalctl carimba o horário do SERVIDOR na margem esquerda. "
            "Leia sempre o horário de dentro da linha, que é o que tem o offset."
        )
    return logger

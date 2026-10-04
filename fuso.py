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


# Nível do log de cada robô, pela variável NIVEL_LOG do .env. Sem ela, INFO (tudo).
# NIVEL_LOG=WARNING deixa no journal só avisos e erros; DEBUG mostra até os detalhes.
NIVEIS_LOG = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR}

# Bibliotecas que em INFO escrevem uma linha a cada job do agendador ("Running
# job", "executed successfully"), cada update do Telegram, cada conexão do
# Telethon e cada chamada HTTP da IA: eram mais de 80% do log do bot_mestre.
# Ficam em WARNING, então os avisos e erros delas continuam aparecendo. Com
# NIVEL_LOG=DEBUG voltam a mostrar tudo.
BIBLIOTECAS_SO_AVISOS = ("apscheduler", "aiogram.event", "telethon", "httpx", "httpcore")


def configurar_logs(nome=None, nivel=None):
    """
    Configura o log do processo no formato comum e devolve o logger `nome`.
    Sem `nivel`, usa o NIVEL_LOG do .env (valor desconhecido vale INFO).

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

    if nivel is None:
        nivel = NIVEIS_LOG.get(os.getenv("NIVEL_LOG", "INFO").strip().upper(), logging.INFO)
    logging.basicConfig(
        level=nivel,
        format=FORMATO_LOG,
        datefmt=FORMATO_DATA,
        force=True,
    )
    for biblioteca in BIBLIOTECAS_SO_AVISOS:
        logging.getLogger(biblioteca).setLevel(logging.NOTSET if nivel <= logging.DEBUG else max(nivel, logging.WARNING))

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

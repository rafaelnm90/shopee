# ==========================================
# 🕐 FUSO ÚNICO DO ECOSSISTEMA
#
# Importar este módulo JÁ trava o processo no horário de Brasília — não existe
# função para chamar nem passo para esquecer. Viaja junto com o repositório,
# então trocar de servidor não exige nenhum ajuste manual no sistema.
#
# Fuso não é soma: aplicar "America/Sao_Paulo" aqui e também no relógio do
# servidor dá o mesmo resultado que aplicar só aqui. O kernel guarda epoch UTC
# e o fuso apenas decide como esse número vira texto.
# ==========================================
import os
import time
import logging

from zoneinfo import ZoneInfo

FUSO_STR = "America/Sao_Paulo"

# 🔒 Trava aplicada no import, antes de qualquer módulo calcular data/hora.
os.environ["TZ"] = FUSO_STR
time.tzset()

fuso_horario = ZoneInfo(FUSO_STR)

FORMATO_LOG = "%(asctime)s.%(msecs)03d " + time.strftime("%z") + " - %(message)s"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"

# 🔒 Trava de reentrada: o motor_userbot e um robo proprio E um modulo importado
# (bot_mestre -> painel_espelhos -> motor_userbot), entao configurar_logs seria
# chamado duas vezes no mesmo processo. Quem chega primeiro configura; os demais
# so recebem o logger, sem remontar o handler nem repetir a linha de boot.
_LOGS_CONFIGURADOS = False


def fuso_do_servidor():
    """
    Descobre o fuso do sistema operacional. Só para registrar no log.

    O symlink /etc/localtime vem PRIMEIRO porque é o que o systemd — e portanto
    o journalctl — realmente usa. O /etc/timezone é legado do Debian e o
    timedatectl não o atualiza: ele continua dizendo "Etc/UTC" para sempre.
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
    Formato de log único de todos os robôs, com o offset carimbado na linha.

    force=True vence qualquer configuração de log feita por módulo importado
    antes (motor_filas e utils configuram o root logger ao serem importados).
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

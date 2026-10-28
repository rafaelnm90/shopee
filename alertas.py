#!/usr/bin/env python3
"""
O aviso na hora dos erros graves, no privado do Rafael (pedido dele, P12: DECISOES.md,
Monitor, deploy e servidor). O diagnostico.yml roda, de hora em hora no servidor:

    python3 alertas.py verificar "SERVIÇOS FORA DO AR"

Cada grave é avisado uma vez e de novo só depois de REPETIR_DEPOIS, se continuar; quando
some, o Rafael recebe o "voltou ao normal". A saída (o log do Actions, que é público) tem
só o rótulo fixo de cada grave; o Claude lê a seção "Graves agora" nas retomadas e corrige
sem esperar o checkup da noite.

Os robôs já avisam na hora os graves que eles mesmos veem (conta suspensa, celular
desconectado, resposta no lugar errado, comentário sem resposta); aqui ficam os que
nenhum robô vê sozinho: robô fora do ar, disco cheio, backup atrasado, erros demais na
última hora e o robô da Shopee Vídeo sem rodar.

O GitHub pula boa parte das rodadas agendadas do diagnóstico (em 27 e 28/10, 8 de 37), e o
aviso "na hora" chegava com horas de atraso. Por isso o bot_mestre também confere, de hora
em hora no próprio servidor, os dois graves que só este módulo vê (robô fora do ar e o robô
da Shopee Vídeo sem rodar): servicos_fora + verificar(..., so=GRAVES_DO_SERVIDOR). Disco,
backup e erros o monitor de saúde do bot_mestre já confere sozinho.
"""
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta

import avisar_rafael
import backup_dados
import db
from fuso import fuso_horario

CHAVE = "alertas_graves"
REPETIR_DEPOIS = timedelta(hours=6)
DISCO_MAXIMO = 90
IDADE_MAXIMA_BACKUP_H = 26
ERROS_NA_HORA = 10
# O robô da Shopee Vídeo roda a cada 15 min no Horário do Robô (painel_shopee_video).
SEM_RODADA = timedelta(minutes=60)
# As chaves do robo_shopee_video (sem importá-lo, que traz a IA e o celular junto; o
# tests/test_alertas.py confere que são as mesmas).
CHAVE_CONFIG_SV, CHAVE_ESTADO_SV = "shopee_video", "shopee_video_robo"
NOMES = {"bot_mestre_bot": "bot principal (bot_mestre)", "divulgacao_canal_bot": "da divulgação",
         "motor_userbot_bot": "do Espião e do Espelhador", "espelhador_videos_autorais_bot": "dos Autorais",
         "downloader_bot": "Baixador"}


# O que o bot_mestre confere sozinho de hora em hora (o começo da chave de cada grave).
GRAVES_DO_SERVIDOR = ("fora:", "robo_sv")
# Como o diagnóstico: um serviço parado é conferido de novo depois disto, porque o systemd
# o religa sozinho em segundos e o reinício não é grave.
ESPERA_PARA_CONFIRMAR = 60


def servicos_fora(espera=ESPERA_PARA_CONFIRMAR):
    """
    Os serviços de NOMES fora do ar, conferidos duas vezes (com `espera` s entre elas), como
    o diagnóstico; None quando o systemctl não responde (aí não se sabe quem está no ar).
    """
    def fora():
        return [s for s in NOMES if subprocess.run(["systemctl", "is-active", "--quiet", f"{s}.service"],
                                                   timeout=30).returncode != 0]
    try:
        caidos = fora()
        if caidos and espera:
            time.sleep(espera)
            caidos = fora()
    except (OSError, subprocess.SubprocessError):
        return None
    return caidos


def _agora(agora=None):
    return agora or datetime.now(fuso_horario)


def _momento(quando):
    return quando.strftime("%Y-%m-%d %H:%M:%S")


def _disco_em_uso():
    uso = shutil.disk_usage("/")
    return uso.used * 100 // uso.total


def _erros_na_ultima_hora(agora):
    try:
        with db.conexao() as con:
            return con.execute("SELECT COUNT(*) FROM erros_logs WHERE timestamp >= ? AND origem != ?",
                               (_momento(agora - timedelta(hours=1)), "Link sem conversão")).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def _robo_sem_rodar(agora):
    """Minutos sem rodada do robô da Shopee Vídeo, quando ele devia estar rodando; senão None."""
    config = db.ler_config(CHAVE_CONFIG_SV, {}) or {}
    if config.get("robo_pausado", True):
        return None
    try:
        if agora.replace(tzinfo=None) < datetime.strptime(config.get("robo_suspenso_ate") or "", "%Y-%m-%d %H:%M:%S"):
            return None
    except ValueError:
        pass
    inicio, fim = config.get("robo_inicio", 9), config.get("robo_fim", 21)
    comeco = agora.replace(hour=int(inicio), minute=0, second=0, microsecond=0)
    if not (int(inicio) <= agora.hour < int(fim)) or agora - comeco < SEM_RODADA:
        return None
    ultima = (db.ler_config(CHAVE_ESTADO_SV, {}) or {}).get("ultima_rodada_em") or ""
    # Retomado há pouco, conta da retomada: a última rodada é de antes da pausa.
    ultima = max(ultima, config.get("robo_retomado_em") or "")
    try:
        parada = agora - datetime.strptime(ultima, "%Y-%m-%d %H:%M:%S").replace(tzinfo=agora.tzinfo)
    except ValueError:
        return None
    return int(parada.total_seconds() // 60) if parada > SEM_RODADA else None


def graves(caidos=(), agora=None):
    """{chave: texto do aviso} dos graves de agora. caidos: os serviços fora do ar (o diagnóstico confere 2 vezes)."""
    agora = _agora(agora)
    achados = {}
    for servico in caidos:
        achados[f"fora:{servico}"] = (f"🚨 O robô {NOMES.get(servico, servico)} está fora do ar. O systemd tenta "
                                      "religar sozinho; se não voltar, o Claude investiga na próxima retomada.")
    disco = _disco_em_uso()
    if disco >= DISCO_MAXIMO:
        achados["disco"] = f"🚨 O disco do servidor está com {disco}% em uso. A faxina precisa rodar."
    backup = backup_dados.ultimo_backup()
    if backup is None or backup[1] > IDADE_MAXIMA_BACKUP_H:
        idade = "nenhum backup" if backup is None else f"o último tem {backup[1]:.0f} h"
        achados["backup"] = f"🚨 Backup atrasado: {idade} (o diário é às 03:40)."
    erros = _erros_na_ultima_hora(agora)
    if erros >= ERROS_NA_HORA:
        achados["erros"] = f"🚨 {erros} erros registrados na última hora. Detalhes no /status."
    parado = _robo_sem_rodar(agora)
    if parado:
        achados["robo_sv"] = (f"🚨 O robô da Shopee Vídeo está ativo e no horário, mas não roda há {parado} min. "
                              "O Claude investiga na próxima retomada.")
    return achados


ROTULOS = {"disco": "disco cheio", "backup": "backup atrasado", "erros": "erros demais na última hora",
           "robo_sv": "robô da Shopee Vídeo sem rodar"}


def rotulo(chave):
    """O rótulo fixo de um grave, para o log público."""
    if chave.startswith("fora:"):
        return f"{chave[5:]} fora do ar"
    return ROTULOS.get(chave, chave)


def verificar(caidos=(), agora=None, mandar=None, so=None):
    """
    Avisa os graves novos (e de novo os que passam de REPETIR_DEPOIS) e o que voltou ao
    normal. Com so (começos de chave, como GRAVES_DO_SERVIDOR), confere só esses: os outros
    avisados ficam como estão. Devolve as chaves dos graves de agora (os conferidos).
    """
    agora = _agora(agora)
    mandar = mandar or avisar_rafael.mandar_texto

    def conferido(chave):
        return so is None or chave.startswith(tuple(so))

    atuais = {c: t for c, t in graves(caidos, agora).items() if conferido(c)}
    avisados = db.ler_config(CHAVE, {}) or {}
    for chave, texto in atuais.items():
        if avisados.get(chave, "") <= _momento(agora - REPETIR_DEPOIS):
            if mandar(texto):
                avisados[chave] = _momento(agora)
    for chave in [c for c in avisados if c not in atuais and conferido(c)]:
        mandar(f"✅ Voltou ao normal: {rotulo(chave)}.")
        del avisados[chave]
    db.salvar_config(CHAVE, avisados)
    return sorted(atuais)


def main(argumentos):
    if not argumentos or argumentos[0] != "verificar":
        print(__doc__)
        return 2
    caidos = argumentos[1].split() if len(argumentos) > 1 else []
    atuais = verificar(caidos)
    print(f"Graves agora: {len(atuais)}" + (" | " + " | ".join(rotulo(c) for c in atuais) if atuais else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

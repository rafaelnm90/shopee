# 0. CONFIGURAÇÕES INICIAIS
EXIBIR_LOGS = True

import random
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger = logging.getLogger(__name__)

FUSO_STR = "America/Sao_Paulo"
fuso_horario = ZoneInfo(FUSO_STR)

def calcular_horarios_distribuicao(itens_para_agendar, config_fila, forcar=False):
    """
    Motor Matemático Centralizado para organização de filas de postagem.
    Garante o State Isolation (Isolamento de Estado) entre diferentes robôs.
    """
    if not itens_para_agendar:
        return []

    # Extrai as regras de negócio específicas da fila que chamou a função
    inicio_janela = config_fila.get("inicio", 10)
    fim_janela = config_fila.get("fim", 22)
    modo = config_fila.get("modo", "aleatorio")
    intervalo_dias = config_fila.get("intervalo_dias", 1)

    agora = datetime.now(fuso_horario)

    if EXIBIR_LOGS:
        logger.info(f"⚙️ [Motor Filas] Iniciando cálculo matemático para {len(itens_para_agendar)} itens...")

    # Aplica o embaralhamento orgânico ou a ordem de captura
    if modo == "aleatorio":
        random.shuffle(itens_para_agendar)
    else:
        itens_para_agendar.sort(key=lambda x: x.get("data_captura", ""))

    if intervalo_dias == 0 and not forcar:
        # 📏 D+0: Postagem Imediata respeitando a Janela de Horário
        for item in itens_para_agendar:
            if agora.hour < inicio_janela:
                # De madrugada: Joga para o minuto inicial da abertura
                horario_calc = agora.replace(hour=inicio_janela, minute=random.randint(0, 5), second=0)
            elif agora.hour >= fim_janela:
                # Após o expediente: Joga para a abertura do dia seguinte
                horario_calc = (agora + timedelta(days=1)).replace(hour=inicio_janela, minute=random.randint(0, 5), second=0)
            else:
                # Dentro do expediente: Imediato com pequeno delay natural
                horario_calc = agora + timedelta(seconds=random.randint(5, 15))
                
            item["horario_disparo"] = horario_calc.strftime("%Y-%m-%d %H:%M:%S")
    else:
        # 📏 D+X ou DESCARGA FORÇADA: Distribuição diluída (Catraca Anti-Ban)
        qtd = len(itens_para_agendar)
        if forcar:
            minuto_atual_busca = agora
            espacamento_segundos = 15 # Catraca de Segurança Fixa para Rajadas
            if EXIBIR_LOGS: logger.info("⚠️ [Motor Filas] Gatilho de Descarga detectado. Aplicando catraca de 15 segundos.")
        else:
            if agora.hour >= fim_janela:
                minuto_atual_busca = (agora + timedelta(days=1)).replace(hour=inicio_janela, minute=0, second=0)
            else:
                hora_partida = max(agora.hour, inicio_janela)
                minuto_atual_busca = agora.replace(hour=hora_partida, minute=agora.minute if hora_partida == agora.hour else 0, second=0)
                
            minutos_disponiveis = (fim_janela * 60) - (minuto_atual_busca.hour * 60 + minuto_atual_busca.minute)
            
            # Trava de segurança para evitar divisão por zero
            if minutos_disponiveis < 1:
                minutos_disponiveis = 1
                
            # Calcula o espaço entre cada postagem, garantindo no mínimo 15 segundos
            espacamento_segundos = max(15, int((minutos_disponiveis * 60) / qtd))
        
        for item in itens_para_agendar:
            # Adiciona uma leve variação nos minutos para parecer humano (apenas se houver espaço e não for descarga forçada)
            variacao = random.randint(0, espacamento_segundos // 4) if espacamento_segundos > 60 and not forcar else 0
            horario_agendado = minuto_atual_busca + timedelta(seconds=variacao)
            
            item["horario_disparo"] = horario_agendado.strftime("%Y-%m-%d %H:%M:%S")
            minuto_atual_busca += timedelta(seconds=espacamento_segundos)

    if EXIBIR_LOGS:
        logger.info(f"✅ [Motor Filas] Distribuição concluída. (Modo: {modo}, Atraso: D+{intervalo_dias}, Forçado: {forcar})")

    return itens_para_agendar

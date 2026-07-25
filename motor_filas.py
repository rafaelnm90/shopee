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

def gerar_layout_item_padrao(index, item, tipo_fila, atraso_dias, agora, fuso_horario, display_origem, link_origem, link_destino=None, detalhes_extras=None):
    """
    🎨 Componente Visual Centralizado (Padrão MVC)
    Gera o layout de 3 linhas para as filas (Espião, Espelhador, etc.).
    
    🚨 REGRA DE OURO: Esta é a base estrutural imutável. 
    Para adicionar detalhes específicos de um robô futuro, passe-os no parâmetro opcional 'detalhes_extras'.
    Nunca altere o esqueleto principal para não quebrar a simetria visual da frota.
    """
    # --- 1. CÁLCULO DINÂMICO DE DATAS ---
    status_dia = "⚪ Indefinido"
    data_cap_formatada = "Desconhecida"
    data_cap_str = item.get("data_captura", "Data não registrada")
    
    hoje_obj = agora.date()
    hoje_str = agora.strftime("%Y-%m-%d")

    if data_cap_str != "Data não registrada":
        try:
            formato = "%Y-%m-%d %H:%M:%S" if len(data_cap_str) > 10 else "%Y-%m-%d"
            data_obj = datetime.strptime(data_cap_str, formato)
            data_cap_formatada = data_obj.strftime("%d/%m às %H:%M")
            
            if tipo_fila == "Espelhador":
                horario_disparo_str = item.get("horario_disparo", "")
                if horario_disparo_str:
                    hd_obj = datetime.strptime(horario_disparo_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
                    if hd_obj.date() == hoje_obj:
                        status_dia = "🔴 Atrasado" if agora > hd_obj else "🟢 Hoje"
                    elif hd_obj.date() > hoje_obj:
                        status_dia = "🟡 Amanhã" if hd_obj.date() == hoje_obj + timedelta(days=1) else f"🔵 D+{abs((hd_obj.date() - hoje_obj).days)}"
                    else:
                        status_dia = "🔴 Atrasado"
            else:
                if atraso_dias == 0:
                    status_dia = "🟢 Na Fila (D+0)" if data_obj.date() == hoje_obj else "🔴 Retido/Falha"
                elif atraso_dias == 1:
                    status_dia = "🟡 Represa (D+1)" if data_obj.date() == hoje_obj else "🔴 Retido/Falha"
                else:
                    status_dia = f"🔵 Represa (D+{atraso_dias})" if data_obj.date() == hoje_obj else "🔴 Retido/Falha"
        except Exception:
            pass

    # --- 2. CÁLCULO DE PREVISÃO EXATA ---
    data_pub = item.get("horario_disparo", "")
    if data_pub:
        try:
            dp_obj = datetime.strptime(data_pub, "%Y-%m-%d %H:%M:%S")
            previsao_texto = dp_obj.strftime("%d/%m às %H:%M")
        except:
            previsao_texto = "Pendente na esteira"
    else:
        previsao_texto = "Aguardando cálculo"
        
    is_postado = item.get("processado", False)
    horario_postagem = item.get("horario_postagem", "")
    
    if is_postado:
        status_dia = "✅ Postado"
        previsao_texto = f"Hoje às {horario_postagem}"
    elif "Fechada" in status_dia:
        status_dia = "🔴 Atrasado"

    # --- 3. ETIQUETA INTELIGENTE PARA OS LINKS ---
    if link_origem:
        if "t.me" in link_origem:
            texto_link_origem = "📥 Origem" if tipo_fila == "Espião" else "Ver Post"
        elif "shopee" in link_origem or "shp.ee" in link_origem:
            texto_link_origem = "Ver Produto"
        else:
            texto_link_origem = "Ver Link"
        link_display = f"<a href='{link_origem}'>{texto_link_origem}</a>"
    else:
        link_display = "<i>Sem link de origem</i>"
        
    # O destino só aparece se o vídeo estiver concluído E houver link
    if is_postado and link_destino:
        link_display += f" | <a href='{link_destino}'>📤 Destino</a>"

    # --- 4. LAYOUT VISUAL EM 3 LINHAS ---
    bloco = (
        f"<b>{index}.</b> {status_dia} | 📡 {display_origem}\n"
        f"   └ 📥 Cap: {data_cap_formatada} ➡️ 📤 Prev: {previsao_texto}\n"
        f"   └ 🔗 {link_display}\n"
    )
    
    # --- 5. INJEÇÃO DE DETALHES ESPECÍFICOS ---
    if detalhes_extras:
        bloco += f"   └ {detalhes_extras}\n"
        
    return bloco

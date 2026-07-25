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
        tempo_acumulado = agora
        for item in itens_para_agendar:
            if tempo_acumulado.hour < inicio_janela:
                # De madrugada: Joga para o minuto inicial da abertura
                tempo_acumulado = tempo_acumulado.replace(hour=inicio_janela, minute=random.randint(0, 5), second=0)
            elif tempo_acumulado.hour >= fim_janela:
                # Após o expediente: Joga para a abertura do dia seguinte
                tempo_acumulado = (tempo_acumulado + timedelta(days=1)).replace(hour=inicio_janela, minute=random.randint(0, 5), second=0)
            
            # Adiciona o delay natural em cascata para D+0 (Evita engarrafamento no mesmo segundo)
            tempo_acumulado += timedelta(seconds=random.randint(20, 45))
                
            item["horario_disparo"] = tempo_acumulado.strftime("%Y-%m-%d %H:%M:%S")
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
    Gera o layout estruturado exato para as filas de automação.
    """
    import re

    # --- 0. RESGATE E HIGIENIZAÇÃO DO NOME COMPLETO ---
    nome_bruto = item.get("nome_produto") or item.get("legenda") or item.get("titulo") or ""
    
    nome_limpo = "Aguardando análise da IA 🧠" 
    
    if nome_bruto:
        legenda_limpa = re.sub(r'<[^>]+>', '', str(nome_bruto)).strip()
        match_item = re.search(r'📦\s*Item:\s*([^\n]+)', legenda_limpa)
        if match_item:
            nome_limpo = match_item.group(1).strip()
        else:
            primeira_linha = legenda_limpa.split('\n')[0].strip()
            if primeira_linha:
                nome_limpo = primeira_linha

    # ✅ CORREÇÃO: Resgate Universal de Horário (Puxa a chave correta independente do Robô)
    horario_universal = item.get("horario_disparo") or item.get("data_publicacao") or ""

    # --- 1. CÁLCULO DINÂMICO DE DATAS E STATUS ---
    status_dia = "⚪ Indefinido"
    data_cap_formatada = "Desconhecida"
    data_cap_str = item.get("data_captura", "Data não registrada")
    
    hoje_obj = agora.date()
    data_alvo_esperada_obj = None

    if data_cap_str != "Data não registrada":
        try:
            formato = "%Y-%m-%d %H:%M:%S" if len(data_cap_str) > 10 else "%Y-%m-%d"
            data_obj = datetime.strptime(data_cap_str, formato)
            data_cap_formatada = data_obj.strftime("%d/%m às %H:%M")
            data_alvo_esperada_obj = data_obj + timedelta(days=atraso_dias)
            
            if tipo_fila == "Espelhador":
                if horario_universal:
                    # Tenta ler com ou sem as horas exatas
                    try:
                        hd_obj = datetime.strptime(horario_universal, "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
                    except ValueError:
                        hd_obj = datetime.strptime(horario_universal, "%Y-%m-%d").replace(tzinfo=fuso_horario)

                    if hd_obj.date() == hoje_obj:
                        status_dia = "🔴 Atrasado" if agora > hd_obj else "⏳ Hoje"
                    elif hd_obj.date() > hoje_obj:
                        status_dia = "🟡 Amanhã" if hd_obj.date() == hoje_obj + timedelta(days=1) else f"🔵 D+{abs((hd_obj.date() - hoje_obj).days)}"
                    else:
                        status_dia = "🔴 Atrasado"
            else:
                if atraso_dias == 0:
                    status_dia = f"⏳ Na Fila (D+{atraso_dias})" if data_obj.date() == hoje_obj else "🔴 Retido/Falha"
                elif atraso_dias == 1:
                    status_dia = f"🟡 Represa (D+{atraso_dias})" if data_obj.date() == hoje_obj else "🔴 Retido/Falha"
                else:
                    status_dia = f"🔵 Represa (D+{atraso_dias})" if data_obj.date() == hoje_obj else "🔴 Retido/Falha"
        except Exception:
            pass

    # --- 2. CÁLCULO DE PREVISÃO EXATA ---
    is_postado = item.get("processado", False)
    horario_postagem = item.get("horario_postagem", "")
    data_postagem_str = item.get("data_postagem", "")
    
    if is_postado:
        status_dia = "✅ Postado"
        if data_postagem_str and horario_postagem:
            try:
                dp_obj = datetime.strptime(data_postagem_str, "%Y-%m-%d")
                previsao_texto = f"{dp_obj.strftime('%d/%m')} às {horario_postagem}"
            except:
                previsao_texto = f"{data_postagem_str} às {horario_postagem}"
        else:
            previsao_texto = f"Hoje às {horario_postagem}"
    else:
        if horario_universal:
            try:
                dp_obj = datetime.strptime(horario_universal, "%Y-%m-%d %H:%M:%S")
                previsao_texto = dp_obj.strftime("%d/%m às %H:%M")
            except:
                # Se não tem hora cadastrada (só a data), exibe apenas o dia
                try:
                    dp_obj = datetime.strptime(horario_universal, "%Y-%m-%d")
                    previsao_texto = dp_obj.strftime("%d/%m")
                except:
                    previsao_texto = "Pendente"
        else:
            if data_alvo_esperada_obj:
                previsao_texto = data_alvo_esperada_obj.strftime("%d/%m")
            else:
                previsao_texto = "Aguardando..."

    if not is_postado and "Fechada" in status_dia:
        status_dia = "🔴 Atrasado"

    # --- 3. ETIQUETA INTELIGENTE PARA OS LINKS (ORIGEM E DESTINO) ---
    if link_origem:
        if "shopee" in link_origem or "shp.ee" in link_origem:
            texto_link_origem = "Ver Produto na Shopee (Origem)"
        else:
            texto_link_origem = "Ver Post no Telegram (Origem)"
        linha_origem = f"   └ 🔗 <a href='{link_origem}'>{texto_link_origem}</a>"
    else:
        linha_origem = "   └ 🔗 <i>Sem link de origem</i>"
        
    linha_destino = ""
    
    # Garante que o link de destino aponte exclusivamente para onde o vídeo foi/será postado
    if link_destino:
        if "shopee" in str(link_destino) or "shp.ee" in str(link_destino):
            texto_link_dest = "Ver Produto na Shopee (Destino)"
        else:
            texto_link_dest = "Ver Post no Telegram (Destino)"
        linha_destino = f"\n   └ 🔗 <a href='{link_destino}'>{texto_link_dest}</a>"
    elif is_postado:
        # Se foi postado, mas o banco de dados antigo não tem o ID exato da mensagem
        linha_destino = f"\n   └ 🔗 <i>Ver Post no Telegram (Link indisponível)</i>"
    else:
        # Espaço reservado para vídeos que estão na fila
        linha_destino = f"\n   └ 🔗 <i>Aguardando postagem (Destino)</i>"

    if EXIBIR_LOGS:
        logger.info(f"🎨 [Layout] Formatando item {index} | Status: {status_dia} | Destino injetado.")

    # --- 4. MONTAGEM ESTRUTURAL DO LAYOUT ---
    bloco = f"<b>{index}.</b> {status_dia} | 📡 {display_origem}\n"
    
    if nome_limpo:
        bloco += f"   └ Nome: {nome_limpo}\n"
        
    bloco += f"   └ 📥 Cap: {data_cap_formatada} ➡️ 📤 Prev: {previsao_texto}\n"
    bloco += f"{linha_origem}{linha_destino}\n\n"  # Adicionado o espaçamento duplo de respiro no final do item
    
    if detalhes_extras:
        bloco += f"   └ {detalhes_extras}\n"
        
    return bloco

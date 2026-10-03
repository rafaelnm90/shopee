"""
Motor de filas: decide QUANDO cada vídeo de uma fila vai ao ar e QUANTOS podem
ir ao ar por dia. Não publica, não lê nem grava fila: recebe a lista de itens
(dicts), preenche ou marca campos neles e devolve.

Usado por: bot_mestre (filas do Espião, Público e Parceiros), motor_userbot
(rotas do Espelhador) e espelhador_videos_autorais (fila de Autorais).

Regras gerais:
- O horário agendado fica em item["horario_disparo"], texto "AAAA-MM-DD HH:MM:SS"
  no fuso de Brasília.
- O atraso D+X (publicar X dias depois da captura) é aplicado por quem chama:
  só entram no motor os itens cuja data-alvo já chegou. Aqui dentro,
  intervalo_dias só escolhe o modo: 0 = publicar já, em cascata; qualquer outro
  valor = espalhar os itens pela janela de publicação.
- O motor nunca apaga nada. Ele marca o item (descartar_por_idade ou
  descartar_por_limite) e quem chamou tira da fila e apaga o vídeo do disco.
- Os horários precisam parecer de uma pessoa postando (proteção contra ban):
  nada de horário redondo, intervalo sempre igual ou rajada. Por isso quase
  todo cálculo tem um sorteio.
"""
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
    Preenche horario_disparo de cada item e devolve a mesma lista.

    A lista é alterada no lugar: embaralhada (modo "aleatorio") ou ordenada por
    data_captura (qualquer outro modo), e a ordem final é a ordem de publicação.

    Chaves de config_fila:
      inicio, fim               janela de publicação em horas (fim=24 vai até meia-noite)
      modo                      "aleatorio" ou ordem de captura
      intervalo_dias            0 = cascata imediata; outro valor = distribuição diluída
      espacamento_base_min      piso de minutos entre publicações; liga o espaçamento
                                orgânico (todas as filas atuais usam)
      espacamento_variacao_min  quanto o intervalo pode variar para mais ou para menos
      horarios_ocupados         horários já agendados na fila; o lote novo começa depois do último
      limite_dias_descarte      máximo de dias entre a captura e a publicação

    Modos:
      - intervalo_dias=0: um item 20 a 45 s depois do outro, a partir de agora.
        Fora da janela, vai para a próxima abertura.
      - forcar=True: descarga manual ("esvaziar agora"). Ignora a janela e o
        espaçamento orgânico e solta tudo a partir de agora, a cada 15 s.
      - demais casos com espacamento_base_min: espaçamento orgânico. O que não
        couber no dia passa para o dia seguinte; item que só caberia mais de
        limite_dias_descarte dias depois da captura fica com horário vazio e
        descartar_por_idade=True.
      - sem espacamento_base_min (nenhuma fila atual): intervalo fixo dividindo
        o resto da janela de hoje pelo lote.
    """
    if not itens_para_agendar:
        return []

    inicio_janela = config_fila.get("inicio", 10)
    fim_janela = config_fila.get("fim", 22)
    modo = config_fila.get("modo", "aleatorio")
    intervalo_dias = config_fila.get("intervalo_dias", 1)

    agora = datetime.now(fuso_horario)

    if EXIBIR_LOGS:
        logger.info(f"⚙️ [Motor Filas] Iniciando cálculo matemático para {len(itens_para_agendar)} itens...")

    if modo == "aleatorio":
        random.shuffle(itens_para_agendar)
    else:
        itens_para_agendar.sort(key=lambda x: x.get("data_captura", ""))

    if intervalo_dias == 0 and not forcar:
        tempo_acumulado = agora
        for item in itens_para_agendar:
            if tempo_acumulado.hour < inicio_janela:
                tempo_acumulado = tempo_acumulado.replace(hour=inicio_janela, minute=random.randint(0, 5), second=0)
            elif tempo_acumulado.hour >= fim_janela:
                tempo_acumulado = (tempo_acumulado + timedelta(days=1)).replace(hour=inicio_janela, minute=random.randint(0, 5), second=0)

            # Nunca dois itens no mesmo segundo.
            tempo_acumulado += timedelta(seconds=random.randint(20, 45))

            item["horario_disparo"] = tempo_acumulado.strftime("%Y-%m-%d %H:%M:%S")
    else:
        qtd = len(itens_para_agendar)
        if forcar:
            minuto_atual_busca = agora
            espacamento_segundos = 15
            if EXIBIR_LOGS: logger.info("⚠️ [Motor Filas] Gatilho de Descarga detectado. Aplicando catraca de 15 segundos.")
        else:
            # Largada: agora, ou a abertura da janela se ainda não abriu,
            # ou a abertura de amanhã se já fechou.
            if agora.hour >= fim_janela:
                minuto_atual_busca = (agora + timedelta(days=1)).replace(hour=inicio_janela, minute=0, second=0)
            else:
                hora_partida = max(agora.hour, inicio_janela)
                minuto_atual_busca = agora.replace(hour=hora_partida, minute=agora.minute if hora_partida == agora.hour else 0, second=0)

            minutos_disponiveis = (fim_janela * 60) - (minuto_atual_busca.hour * 60 + minuto_atual_busca.minute)

            if minutos_disponiveis < 1:
                minutos_disponiveis = 1

            # Só vale para o modo sem espacamento_base_min: o resto da janela dividido pelo lote.
            espacamento_segundos = max(15, int((minutos_disponiveis * 60) / qtd))

        base_min = config_fila.get("espacamento_base_min")
        var_min = config_fila.get("espacamento_variacao_min", 0)
        usar_espaco_organico = bool(base_min) and not forcar

        deslocamento_inicial_seg = 0

        # Esteira contínua: se a fila já tem itens agendados, o lote novo começa
        # depois do último deles. Sem isso, lotes calculados em momentos
        # diferentes se sobrepõem e o espaçamento real cai pela metade.
        if usar_espaco_organico:
            ocupados = config_fila.get("horarios_ocupados") or []
            ultimo_ocupado = None
            for oc in ocupados:
                try:
                    oc_obj = datetime.strptime(oc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario) if isinstance(oc, str) else oc
                    if oc_obj > minuto_atual_busca and (ultimo_ocupado is None or oc_obj > ultimo_ocupado):
                        ultimo_ocupado = oc_obj
                except Exception:
                    pass
            if ultimo_ocupado:
                passo_ini = random.randint(max(60, (base_min - var_min) * 60), (base_min + var_min) * 60)
                minuto_atual_busca = ultimo_ocupado + timedelta(seconds=passo_ini)
                if EXIBIR_LOGS:
                    logger.info(f"🔗 [Motor Filas] {len(ocupados)} item(ns) já agendados. Novo lote começa em {minuto_atual_busca.strftime('%d/%m %H:%M')}.")

        limite_dias = config_fila.get("limite_dias_descarte", 5)
        descartados_idade = []

        fim_do_dia = minuto_atual_busca.replace(hour=0, minute=0, second=0) + timedelta(days=1)
        if fim_janela < 24:
            fim_do_dia = minuto_atual_busca.replace(hour=fim_janela, minute=0, second=0)

        passo_base_min = base_min or 10
        variacao_efetiva = var_min
        if usar_espaco_organico:
            # minutos_restantes (incluindo os dias de transbordo) só alimenta o log abaixo.
            minutos_restantes = max(1, int((fim_do_dia - minuto_atual_busca).total_seconds() / 60))

            janela_dia = 1440 if fim_janela >= 24 else max(1, (fim_janela - inicio_janela) * 60)
            cabe_hoje = minutos_restantes // max(1, base_min)
            if len(itens_para_agendar) > cabe_hoje:
                dias_necessarios = 1 + ((len(itens_para_agendar) - cabe_hoje) // max(1, janela_dia // max(1, base_min)))
                minutos_restantes += janela_dia * dias_necessarios

            if ultimo_ocupado:
                # Fila já ocupada: usa o piso configurado. Espalhar um lote pequeno
                # pela janela inteira fazia cada lote ocupar um dia do calendário, e o
                # vídeo capturado no dia 10 acabava agendado para o dia 16.
                passo_base_min = base_min
                variacao_efetiva = var_min
            else:
                # Fila vazia: divide a janela CHEIA do dia pelo lote, com o piso como
                # mínimo. Dividir só o que resta do dia espremia tudo no fim da noite
                # (sorteio às 20h punha 6 vídeos em 2 horas). O que não couber hoje
                # passa para amanhã na virada de dia do laço abaixo.
                alvo = janela_dia // max(1, len(itens_para_agendar))
                passo_base_min = max(base_min, alvo)
                # Folga proporcional: 25% do passo, ou a variação configurada se for maior.
                variacao_efetiva = max(var_min, int(passo_base_min * 0.25))

            # Atraso sorteado na largada para o primeiro vídeo não cair todo dia no
            # minuto exato da abertura da janela. Até 1/3 do passo, para o último
            # vídeo do lote não transbordar para amanhã. Desloca o lote inteiro;
            # os intervalos entre os vídeos não mudam.
            if not ultimo_ocupado:
                deslocamento_inicial_seg = random.randint(0, max(0, (passo_base_min * 60) // 3))
                minuto_atual_busca += timedelta(seconds=deslocamento_inicial_seg)

            if EXIBIR_LOGS:
                logger.info(f"📐 [Motor Filas] {len(itens_para_agendar)} item(ns) em {minutos_restantes} min "
                            f"→ espaçamento de {passo_base_min} ± {variacao_efetiva} min "
                            f"(largada +{deslocamento_inicial_seg // 60} min).")

        for item in itens_para_agendar:
            if usar_espaco_organico:
                if minuto_atual_busca >= fim_do_dia:
                    # Virada de dia: pula para a abertura da janela seguinte, mas nunca
                    # para antes de onde o item cairia sem a virada. Com janela de 24 h,
                    # a abertura (00:00 a 00:05) encostaria no item das 23:5x.
                    minimo_permitido = minuto_atual_busca

                    proximo = minuto_atual_busca + timedelta(days=1) if fim_janela < 24 else minuto_atual_busca
                    minuto_atual_busca = proximo.replace(hour=inicio_janela, minute=random.randint(0, 5), second=0)

                    if minuto_atual_busca < minimo_permitido:
                        minuto_atual_busca = minimo_permitido

                    if fim_janela < 24:
                        fim_do_dia = minuto_atual_busca.replace(hour=fim_janela, minute=0, second=0)
                    else:
                        fim_do_dia = minuto_atual_busca.replace(hour=0, minute=0, second=0) + timedelta(days=1)

                # Empurrado para longe demais da captura: marca para descarte e não agenda.
                cap = item.get("data_captura", "")
                if cap:
                    try:
                        cap_obj = datetime.strptime(cap, "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
                        if (minuto_atual_busca - cap_obj).days > limite_dias:
                            item["horario_disparo"] = ""
                            item["descartar_por_idade"] = True
                            descartados_idade.append(item)
                            continue
                    except Exception:
                        pass

                item["horario_disparo"] = minuto_atual_busca.strftime("%Y-%m-%d %H:%M:%S")
                passo = random.randint(max(60, (passo_base_min - variacao_efetiva) * 60),
                                       (passo_base_min + variacao_efetiva) * 60)
                minuto_atual_busca += timedelta(seconds=passo)
                continue

            # Intervalo fixo (descarga forçada ou fila sem espacamento_base_min), com
            # até 1/4 de variação quando o intervalo passa de 1 minuto.
            variacao = random.randint(0, espacamento_segundos // 4) if espacamento_segundos > 60 and not forcar else 0
            horario_agendado = minuto_atual_busca + timedelta(seconds=variacao)

            item["horario_disparo"] = horario_agendado.strftime("%Y-%m-%d %H:%M:%S")
            minuto_atual_busca += timedelta(seconds=espacamento_segundos)

        if descartados_idade and EXIBIR_LOGS:
            logger.info(f"🗑️ [Motor Filas] {len(descartados_idade)} item(ns) marcados para descarte: passariam de {limite_dias} dias desde a captura.")

    if EXIBIR_LOGS:
        logger.info(f"✅ [Motor Filas] Distribuição concluída. (Modo: {modo}, Atraso: D+{intervalo_dias}, Forçado: {forcar})")


    return itens_para_agendar

def recompactar_horarios(itens, config_fila, agora, margem_min=20):
    """
    Puxa para dias anteriores os itens que transbordaram, quando abre vaga.

    A esteira contínua de calcular_horarios_distribuicao faz a fila só crescer
    para a frente: vídeo publicado, descartado ou removido na mão deixa um
    buraco que ninguém ocupa, e o item de 18/09 continua em 18/09 mesmo com o
    dia 13 pela metade.

    A compactação é por DIA, nunca por horário: um item só se move se houver dia
    anterior com vaga, e quem já está no dia certo não tem o horário mexido. O
    espalhamento dentro do dia é o que faz a fila parecer humana; reescrevê-lo
    amontoaria tudo no começo do expediente.

    Nunca viola:
      - o D+X: nada vai para antes de data_captura + intervalo_dias;
      - o presente: nada é agendado para o passado nem para os próximos margem_min minutos.

    Ignora itens já publicados (processado) e itens ainda sem horário.
    Altera horario_disparo no lugar e devolve a lista dos itens movidos; lista
    vazia significa que não há nada para gravar.
    """
    inicio_janela = int(config_fila.get("inicio", 0) or 0)
    fim_janela = int(config_fila.get("fim", 24) or 24)
    base_min = max(1, int(config_fila.get("espacamento_base_min") or 10))
    var_min = int(config_fila.get("espacamento_variacao_min") or 0)
    intervalo_dias = int(config_fila.get("intervalo_dias", 0) or 0)

    minutos_janela = 1440 if fim_janela >= 24 else max(1, (fim_janela - inicio_janela) * 60)
    capacidade_dia = max(1, minutos_janela // base_min)

    hoje = agora.date()
    piso_absoluto = agora + timedelta(minutes=margem_min)

    # Agrupa por dia agendado, guardando o primeiro dia em que cada item pode sair (o D+X dele).
    por_dia = {}
    for item in itens:
        if item.get("processado") in [True, 1, "true", "True"]:
            continue
        bruto = item.get("horario_disparo") or ""
        if not bruto:
            continue   # sem horário ainda: quem agenda é calcular_horarios_distribuicao
        try:
            atual = datetime.strptime(str(bruto), "%Y-%m-%d %H:%M:%S").replace(tzinfo=agora.tzinfo)
        except Exception:
            continue

        dia_minimo = hoje
        captura = str(item.get("data_captura") or "")
        if captura:
            try:
                formato = "%Y-%m-%d %H:%M:%S" if len(captura) > 10 else "%Y-%m-%d"
                alvo = datetime.strptime(captura, formato).date() + timedelta(days=intervalo_dias)
                dia_minimo = max(hoje, alvo)
            except Exception:
                pass

        por_dia.setdefault(atual.date(), []).append({"item": item, "quando": atual, "piso": dia_minimo})

    if len(por_dia) < 2:
        return []   # tudo num dia só: não há transbordo para puxar

    movidos = []
    dias = sorted(por_dia)

    for dia in dias:
        # 'dias' é uma foto tirada antes do laço; um dia pode ter sido esvaziado
        # e removido de por_dia numa volta anterior.
        if dia < hoje or dia not in por_dia:
            continue
        vagas = capacidade_dia - len(por_dia[dia])

        while vagas > 0:
            # Candidato: o item mais cedo do dia posterior mais próximo que já pode sair neste dia.
            escolhido = None
            for dia_futuro in [d for d in sorted(por_dia) if d > dia]:
                for registro in sorted(por_dia[dia_futuro], key=lambda r: r["quando"]):
                    if registro["piso"] <= dia:
                        escolhido = (dia_futuro, registro)
                        break
                if escolhido:
                    break

            if not escolhido:
                break

            dia_futuro, registro = escolhido

            # Novo horário: um passo orgânico depois do último item do dia
            # (ou logo após a abertura, se o dia estiver vazio).
            passo = random.randint(max(60, (base_min - var_min) * 60),
                                   max(60, (base_min + var_min) * 60))
            if por_dia[dia]:
                ultimo = max(r["quando"] for r in por_dia[dia])
                novo = ultimo + timedelta(seconds=passo)
            else:
                abertura = datetime.combine(dia, datetime.min.time()).replace(
                    hour=inicio_janela, tzinfo=agora.tzinfo)
                novo = abertura + timedelta(seconds=random.randint(0, passo))

            if novo < piso_absoluto:
                novo = piso_absoluto + timedelta(seconds=random.randint(0, passo))

            # Não cabe antes do fim da janela (ou viraria o dia): este dia fica como está.
            if fim_janela < 24:
                fechamento = datetime.combine(dia, datetime.min.time()).replace(
                    hour=fim_janela, tzinfo=agora.tzinfo)
                if novo >= fechamento:
                    break
            if novo.date() != dia:
                break

            registro["item"]["horario_disparo"] = novo.strftime("%Y-%m-%d %H:%M:%S")
            registro["quando"] = novo
            por_dia[dia_futuro].remove(registro)
            por_dia[dia].append(registro)
            if not por_dia[dia_futuro]:
                del por_dia[dia_futuro]
            movidos.append(registro["item"])
            vagas -= 1

    if movidos and EXIBIR_LOGS:
        ultimo_dia = max(por_dia) if por_dia else hoje
        logger.info(f"🧲 [Motor Filas] {len(movidos)} item(ns) antecipado(s) para dias com vaga. "
                    f"A fila agora termina em {ultimo_dia.strftime('%d/%m')}.")

    return movidos

def ler_faixa_limite(config):
    """
    Devolve (piso, topo) de posts por dia de uma configuração: rota do
    Espelhador (dict do JSON) ou parceiro (linha do SQLite).

    Sem limite_min, usa o antigo limite_diario como piso (configurações
    anteriores à faixa). Piso 0 = sem teto. Garante topo >= piso; topo igual
    ao piso = número fixo, sem sorteio.
    """
    piso = config.get("limite_min")
    if piso in (None, "", 0):
        piso = config.get("limite_diario") or 0
    try:
        piso = int(piso or 0)
    except (TypeError, ValueError):
        piso = 0

    try:
        topo = int(config.get("limite_max") or 0)
    except (TypeError, ValueError):
        topo = 0

    if topo < piso:
        topo = piso
    return piso, topo

def faixa_de_config(config, chave_min, chave_max, chave_legado=None):
    """
    ler_faixa_limite para configurações que usam outros nomes de chave.

    Cada fluxo batizou a sua cota de um jeito (limite_diario nos parceiros,
    limite_videos nos Autorais, repost_limite no Público); este adaptador
    traduz os nomes e delega.
    """
    return ler_faixa_limite({
        "limite_min": config.get(chave_min),
        "limite_max": config.get(chave_max),
        "limite_diario": config.get(chave_legado) if chave_legado else None,
    })

def sortear_teto_do_dia(semente, dia, piso, topo):
    """
    Quantos posts o dia aceita, sorteado dentro de [piso, topo]. 0 = sem teto.

    O sorteio é determinístico de propósito: mesma semente + mesmo dia dá
    sempre o mesmo número. O motor reavalia a fila a cada 60 s e o descarte é
    irreversível; com sorteio novo a cada volta, um vídeo aprovado às 10h00
    seria apagado às 10h01 quando o número caísse. Por ser determinístico, o
    teto do dia também sobrevive a reinício do serviço e pode ser mostrado no
    painel sem gravar nada.

    random.Random(str) semeia por SHA-512 da string e é estável entre
    processos, ao contrário de hash(), que muda a cada execução (PYTHONHASHSEED).
    """
    try:
        piso = int(piso or 0)
        topo = int(topo or 0)
    except (TypeError, ValueError):
        return 0

    if piso <= 0:
        return 0
    if topo < piso:
        piso, topo = topo, piso
    if topo == piso:
        return piso

    return random.Random(f"{semente}|{dia}").randint(piso, topo)

def aplicar_limite_diario_fila(itens, piso, topo=None, semente="", chave_horario="horario_disparo"):
    """
    Teto de publicações por dia, comum a todas as filas.

    Captura-se tudo; aqui se decide o que de fato vai ao ar. Cada dia sorteia o
    próprio teto dentro de [piso, topo] (ver sortear_teto_do_dia), o que evita o
    mesmo número de posts todo dia. Os chamadores passam o par vindo de
    ler_faixa_limite, que garante topo >= piso. piso 0 ou ausente = sem teto.

    Ficam os primeiros de cada dia por horário: como o motor já embaralhou ou
    ordenou por captura antes de agendar, essa ordem já é a prioridade.

    Itens já publicados (processado) ocupam vaga e nunca são marcados. O
    excedente recebe descartar_por_limite=True; quem chamou tira da fila e
    apaga o vídeo. Devolve a lista dos itens marcados.
    """
    try:
        piso = int(piso or 0)
    except (TypeError, ValueError):
        piso = 0

    if piso <= 0:
        return []

    por_dia = {}
    for item in itens:
        horario = item.get(chave_horario) or ""
        if not horario:
            continue
        por_dia.setdefault(horario[:10], []).append(item)

    descartados = []
    for dia, itens_do_dia in sorted(por_dia.items()):
        limite = sortear_teto_do_dia(semente, dia, piso, topo)
        if limite <= 0:
            continue

        itens_do_dia.sort(key=lambda i: i.get(chave_horario) or "")
        vagas = limite
        excedente = []

        for item in itens_do_dia:
            if item.get("processado"):
                vagas -= 1
                continue
            if vagas > 0:
                vagas -= 1
            else:
                excedente.append(item)

        for item in excedente:
            item["descartar_por_limite"] = True
            descartados.append(item)

        if excedente and EXIBIR_LOGS:
            logger.info(f"✂️ [Motor Filas] Dia {dia} sorteou teto de {limite} "
                        f"(faixa {piso}-{topo or piso}): {len(excedente)} item(ns) descartado(s).")

    return descartados

def gerar_layout_item_padrao(index, item, tipo_fila, atraso_dias, agora, fuso_horario, display_origem, link_origem, link_destino=None, detalhes_extras=None):
    """
    Monta o bloco HTML (parse_mode HTML do Telegram) de um item nas listagens
    de fila do painel: status do dia, nome do produto, captura, previsão de
    publicação e links de origem e destino. Não altera o item.

    atraso_dias é o D+X da fila, usado para estimar a data quando o item
    ainda não tem horário. tipo_fila não é usado.
    """
    import re

    # Cada robô guarda o texto do post numa chave diferente. O nome do produto
    # vem da linha "📦 Item:" que a IA escreve na legenda; sem ela, da primeira
    # linha do texto sem hashtags.
    nome_bruto = item.get("nome_produto") or item.get("legenda") or item.get("texto_processado") or item.get("titulo") or item.get("texto") or item.get("caption") or item.get("text") or ""

    nome_limpo = "Aguardando análise da IA 🧠"

    if nome_bruto:
        legenda_limpa = re.sub(r'<[^>]+>', '', str(nome_bruto)).strip()
        match_item = re.search(r'📦\s*Item:\s*([^\n]+)', legenda_limpa)

        if match_item:
            nome_limpo = match_item.group(1).strip()
        else:
            linhas_validas = [linha.strip() for linha in legenda_limpa.split('\n') if linha.strip()]
            if linhas_validas:
                primeira_linha = re.sub(r'#\w+', '', linhas_validas[0]).strip()
                if primeira_linha:
                    nome_limpo = primeira_linha

    # Horário agendado: o relatório do Público manda data_publicacao, as demais filas horario_disparo.
    horario_universal = item.get("horario_disparo") or item.get("data_publicacao") or ""

    # Status do dia: pelo horário agendado; sem horário, pela data-alvo (captura + atraso_dias).
    status_dia = "⚪ Indefinido"
    data_cap_formatada = "Desconhecida"
    data_cap_str = item.get("data_captura", "Data não registrada")

    hoje_obj = agora.date()
    amanha_obj = hoje_obj + timedelta(days=1)
    data_alvo_esperada_obj = None

    if data_cap_str != "Data não registrada":
        try:
            formato = "%Y-%m-%d %H:%M:%S" if len(data_cap_str) > 10 else "%Y-%m-%d"
            data_obj = datetime.strptime(data_cap_str, formato)
            data_cap_formatada = data_obj.strftime("%d/%m às %H:%M")

            data_alvo_esperada_obj = data_obj + timedelta(days=atraso_dias)
            data_alvo_obj = data_alvo_esperada_obj.date()

            if horario_universal:
                try:
                    hd_obj = datetime.strptime(horario_universal, "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario).date()
                except ValueError:
                    hd_obj = datetime.strptime(horario_universal, "%Y-%m-%d").replace(tzinfo=fuso_horario).date()

                if hd_obj == hoje_obj:
                    status_dia = "🟢 Agendado p/ Hoje"
                elif hd_obj == amanha_obj:
                    status_dia = "🟡 Agendado p/ Amanhã"
                elif hd_obj > amanha_obj:
                    status_dia = f"🔵 Agendado p/ {hd_obj.strftime('%d/%m')}"
                else:
                    status_dia = "🔴 Atrasado"
            else:
                if data_alvo_obj < hoje_obj:
                    status_dia = "🔴 Atrasado"
                elif data_alvo_obj == hoje_obj:
                    status_dia = "🟢 Agendado p/ Hoje"
                elif data_alvo_obj == amanha_obj:
                    status_dia = "🟡 Agendado p/ Amanhã"
                else:
                    status_dia = f"🔵 Agendado p/ {data_alvo_obj.strftime('%d/%m')}"

        except Exception:
            pass

    # Previsão: publicado mostra quando saiu; pendente mostra o horário agendado
    # (ou só a data-alvo) e vira "Atrasado" se a data já passou.
    is_postado = item.get("processado", False)
    horario_postagem = item.get("horario_postagem", "")
    data_postagem_str = item.get("data_postagem", "")
    is_pausado = item.get("is_pausado", False)

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
                if dp_obj.date() < hoje_obj:
                    status_dia = "🔴 Atrasado"
                    previsao_texto = "Pendente (Atrasado)"
                else:
                    previsao_texto = dp_obj.strftime("%d/%m às %H:%M")
            except:
                try:
                    dp_obj = datetime.strptime(horario_universal, "%Y-%m-%d")
                    if dp_obj.date() < hoje_obj:
                        status_dia = "🔴 Atrasado"
                        previsao_texto = "Pendente (Atrasado)"
                    else:
                        previsao_texto = dp_obj.strftime("%d/%m")
                except:
                    previsao_texto = "Pendente"
        else:
            if data_alvo_esperada_obj:
                if data_alvo_esperada_obj.date() < hoje_obj:
                    status_dia = "🔴 Atrasado"
                    previsao_texto = "Pendente (Atrasado)"
                else:
                    previsao_texto = data_alvo_esperada_obj.strftime("%d/%m")
            else:
                previsao_texto = "Aguardando..."

        # Fila pausada: o status vira "Pausado" e a previsão avisa que depende de reativar.
        if is_pausado:
            status_dia = "🛑 Pausado"
            if previsao_texto == "Pendente (Atrasado)":
                previsao_texto = "Retido (Pausado)"
            elif data_alvo_esperada_obj and data_alvo_esperada_obj.date() >= hoje_obj:
                previsao_texto = f"{data_alvo_esperada_obj.strftime('%d/%m')} (Se Ativo)"

    # Rótulo do link conforme o destino: produto na Shopee ou post no Telegram.
    if link_origem:
        if "shopee" in link_origem or "shp.ee" in link_origem:
            texto_link_origem = "Ver Produto na Shopee (Origem)"
        else:
            texto_link_origem = "Ver Post no Telegram (Origem)"
        linha_origem = f"   └ 🔗 <a href='{link_origem}'>{texto_link_origem}</a>"
    else:
        linha_origem = "   └ 🔗 <i>Sem link de origem</i>"

    linha_destino = ""

    if link_destino:
        if "shopee" in str(link_destino) or "shp.ee" in str(link_destino):
            texto_link_dest = "Ver Produto na Shopee (Destino)"
        else:
            texto_link_dest = "Ver Post no Telegram (Destino)"
        linha_destino = f"\n   └ 🔗 <a href='{link_destino}'>{texto_link_dest}</a>"
    elif is_postado:
        # Publicado antes de o banco guardar o ID da mensagem: não há link para montar.
        linha_destino = "\n   └ 🔗 <i>Ver Post no Telegram (Link indisponível)</i>"
    else:
        linha_destino = "\n   └ 🔗 <i>Aguardando postagem (Destino)</i>"

    if EXIBIR_LOGS:
        logger.info(f"🎨 [Layout] Formatando item {index} | Status: {status_dia} | Destino injetado.")

    bloco = f"<b>{index}.</b> {status_dia} | 📡 {display_origem}\n"

    if nome_limpo:
        bloco += f"   └ Nome: {nome_limpo}\n"

    bloco += f"   └ 📥 Cap: {data_cap_formatada} ➡️ 📤 Prev: {previsao_texto}\n"
    bloco += f"{linha_origem}{linha_destino}\n\n"

    if detalhes_extras:
        bloco += f"   └ {detalhes_extras}\n"

    return bloco

#!/usr/bin/env python3
"""
Checkup do dia: o que pode ter dado errado nos robôs, em números que o Claude
confere sozinho. Roda no servidor pelo checkup.yml (todo dia às 22:20 e à mão);
o Claude lê o resultado na rotina do checkup diário, investiga cada ponto de
atenção e corrige pelo PR. O que ainda não dá para conferir por aqui ganha uma
seção nova (DECISOES.md, Trabalho com o Claude).

Só lê, menos a memória dos próprios pontos de atenção (tabela checkup_pontos: a forma
de cada ponto, com os números trocados por #). O repositório e os logs do Actions são
públicos: saem só números,
estados, horários e trechos fixos do código (arquivo:linha e o texto fixo de
cada chamada de log ou de registrar_erro_json, com {…} no lugar das variáveis).
Nunca o texto de um erro, de um log, de uma fila ou do banco.

Seções: erros registrados (erros_logs), log de cada robô (quedas, rastros de
erro pelo tipo e pelo lugar do código, avisos e erros por lugar do código),
processos dos robôs (registro_processos.py), rotinas e divulgação (espaçamento,
assunto repetido em seguida e o que saiu contra o configurado), postagens de
hoje por fila, captura por grupo de origem (Espião, Espelhador e parceiros, pela
posição na lista do painel), produto repetido entre parceiros ou com a conta
principal, a verificação semanal do Grupo Público (só os números), robô da Shopee
Vídeo (com as respostas aos comentários e o feed), as sobreposições (uma tarefa no
horário de outra), Baixador e backup, e a meta de cada job (esperado × feito). No fim, os pontos de atenção, cada um marcado como novo,
repetido há N dias ou que voltou, e os que se resolveram desde o checkup anterior.

Com `robo-agora`, só as linhas do robô da Shopee Vídeo que o diagnostico.yml mostra de
hora em hora para a retomada do Claude (a cada 3 h): paradas, erros e pulados nas
últimas 3 h e 12 h e os aprovados que passaram da hora de ir ao ar.
"""
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import backup_dados
import casos_robo
import db
import inventario
import links_shopee
import perguntas_rafael
import registro_processos
import rotas_espelhador
import rotinas
from fuso import fuso_horario

# Erro que já tem seção própria no diagnostico.yml (Links sem conversão).
ORIGENS_A_PARTE = ("Link sem conversão",)
# Um erro é "novo" quando não apareceu nos 7 dias antes das últimas 24 h.
DIAS_PARA_NOVO = 7
# Item de fila com horário vencido há mais que isso e ainda não postado.
ATRASO_TOLERADO = timedelta(minutes=30)
# O backup roda às 03:40; mais de 26 h sem um novo quer dizer que um dia falhou.
IDADE_MAXIMA_BACKUP_H = 26
# Fila sem nenhum post até a noite, com média de pelo menos isso por dia, é ponto de atenção.
MEDIA_PARA_COBRAR = 2
HORA_PARA_COBRAR = 18
# Processo com pelo menos tantas falhas, e não menos falhas que acertos, é ponto de atenção.
FALHAS_PARA_COBRAR = 3
# Rotinas do mesmo canal com menos que isso entre uma e outra saíram "juntas". Na
# divulgação, o piso é a regra dela: 15 min entre dois envios ao mesmo grupo. Mais que
# PICO_PARA_COBRAR envios em JANELA_DO_PICO min, somando todos os grupos, é rajada.
INTERVALO_CURTO_ROTINA = 10
# Rotina adiada há menos que isto ainda tem o novo disparo marcado (a intercalação adia
# de 20 a 45 min): sai depois do checkup, então não é cobrada como "a menos".
MINUTOS_DA_ADIADA = 60
INTERVALO_CURTO_DIVULGACAO = 15
JANELA_DO_PICO, PICO_PARA_COBRAR = 5, 10
# Quantos lugares do código mostrar por robô no log.
LUGARES_POR_ROBO = 5
# As chaves do robo_shopee_video (sem importá-lo, que traz a IA e o celular junto; o
# tests/test_checkup.py confere que são as mesmas). O robô começa pausado.
CHAVE_CONFIG_SV, CHAVE_DIA_SV = "shopee_video", "shopee_video_robo_dia"
# A folga depois do fim da suspensão (a mesma do robo_shopee_video.FOLGA_DA_SUSPENSAO).
FOLGA_DA_SUSPENSAO_SV = timedelta(minutes=15)
# Resultados do robô da Shopee Vídeo que pedem investigação.
RESULTADOS_RUINS = ("erro", "parou", "verificação", "treino parou")
# O aprovado que passou da hora de ir ao ar há mais que isso (a rodada é a cada 15 min).
ATRASO_DO_APROVADO = timedelta(minutes=30)
# As janelas que a retomada do Claude lê no diagnóstico (a cada 3 h; às 8h, a noite toda).
JANELAS_DA_RETOMADA = (3, 12)
# A hora em que o robô da Shopee Vídeo só descurte (P25); o tests/test_checkup.py confere
# que é a mesma do robo_shopee_video.
HORA_DO_DESCURTIR_SV = 4


def mascarar(texto):
    """Números longos (ids de chat, de mensagem) viram #."""
    return re.sub(r"-?\d{5,}", "#", str(texto or ""))


def _agora(agora=None):
    return agora or datetime.now(fuso_horario)


def _momento(quando):
    return quando.strftime("%Y-%m-%d %H:%M:%S")


# --- Erros registrados ---

def modelos_de_erro():
    """Cada registrar_erro_json do código, para ligar a linha do erros_logs ao lugar que a gravou."""
    def eh_registro(n):
        nome = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
        return "erro" if nome == "registrar_erro_json" else None
    return inventario.modelos_de_chamadas(eh_registro)


def lugar_do_erro(erro, modelos):
    """(arquivo:linha, texto fixo) de quem gravou o erro, ou None."""
    for regex, onde, texto, *_ in modelos:
        if regex.match(erro or ""):
            return onde, texto
    return None


def erros_registrados(agora=None):
    """
    Os erros_logs das últimas 24 h agrupados por origem, lugar do código e tipo da
    exceção: [{origem, lugar, texto, tipo, qtd, ultimo, novo}], o mais frequente primeiro.
    """
    agora = _agora(agora)
    desde, antes = agora - timedelta(hours=24), agora - timedelta(hours=24, days=DIAS_PARA_NOVO)
    try:
        with db.conexao() as conexao:
            linhas = conexao.execute(
                "SELECT timestamp, origem, erro, rastro_codigo FROM erros_logs WHERE timestamp >= ?",
                (_momento(antes),)).fetchall()
    except sqlite3.OperationalError:
        return []
    modelos = modelos_de_erro()
    grupos = {}
    for quando, origem, erro, rastro in linhas:
        if origem in ORIGENS_A_PARTE:
            continue
        lugar = lugar_do_erro(erro, modelos)
        onde, tipo = inventario.classificar_erro(erro, rastro)
        lugar, texto = lugar or ("(sem lugar no código)", mascarar(onde))
        grupo = grupos.setdefault((mascarar(origem), lugar, texto, tipo), {"qtd": 0, "ultimo": "", "antes": 0})
        if (quando or "") >= _momento(desde):
            grupo["qtd"] += 1
            grupo["ultimo"] = max(grupo["ultimo"], quando or "")
        else:
            grupo["antes"] += 1
    saida = [{"origem": origem, "lugar": lugar, "texto": texto, "tipo": tipo, "qtd": g["qtd"],
              "ultimo": g["ultimo"][11:16], "novo": not g["antes"]}
             for (origem, lugar, texto, tipo), g in grupos.items() if g["qtd"]]
    return sorted(saida, key=lambda e: -e["qtd"])


# --- Log de cada robô ---

# A rodada do robô da Shopee Vídeo roda cada vez numa unidade própria do systemd
# (painel_shopee_video): o log dela é lido pelo nome no journal, não pelo serviço.
LOGS_POR_NOME = ("robo_shopee_video",)


def ler_journal(servico):
    filtro = ["-t", servico] if servico in LOGS_POR_NOME else ["-u", f"{servico}.service"]
    r = subprocess.run(["sudo", "-n", "journalctl", *filtro, "--since", "24 hours ago",
                        "-o", "cat", "-q"], capture_output=True, text=True, timeout=180)
    if r.returncode and not r.stdout:
        # Sem acesso ao journal não é o mesmo que um dia sem log.
        raise PermissionError(f"journalctl saiu com {r.returncode}")
    return [linha for linha in r.stdout.splitlines() if linha.strip()]


def _lugar_do_quadro(caminho, linha, funcao):
    """O quadro do rastro como arquivo:linha (função); de biblioteca, o caminho dentro dela."""
    if "site-packages/" in caminho:
        return f"{caminho.split('site-packages/', 1)[1]}:{linha}"
    return f"{os.path.basename(caminho)}:{linha} ({funcao})"


def _eh_do_projeto(caminho):
    return caminho.endswith(".py") and "site-packages/" not in caminho and not caminho.startswith("/usr/")


def rastros_do_log(linhas):
    """
    Os rastros de erro do log agrupados pelo tipo da exceção e pelo último lugar do
    código do projeto por onde passaram (ou, sem nenhum, o último da biblioteca):
    [(tipo, lugar, quantidade)], o mais frequente primeiro. A mensagem da exceção,
    que pode ter dados, não sai.
    """
    grupos, i = {}, 0
    while i < len(linhas):
        if not linhas[i].startswith("Traceback (most recent call last)"):
            i += 1
            continue
        do_projeto = de_biblioteca = None
        i += 1
        while i < len(linhas) and linhas[i][:1] in (" ", "\t"):
            quadro = re.match(r'\s+File "([^"]+)", line (\d+), in (\S+)', linhas[i])
            if quadro:
                caminho, linha, funcao = quadro.groups()
                lugar = _lugar_do_quadro(caminho, linha, funcao)
                if _eh_do_projeto(caminho):
                    do_projeto = lugar
                else:
                    de_biblioteca = lugar
            i += 1
        tipo = re.match(r"([A-Za-z_][\w.]*)", linhas[i].strip()) if i < len(linhas) else None
        chave = (tipo.group(1) if tipo else "?", do_projeto or de_biblioteca or "?")
        grupos[chave] = grupos.get(chave, 0) + 1
    return sorted(((tipo, lugar, qtd) for (tipo, lugar), qtd in grupos.items()), key=lambda r: -r[2])


def resumo_do_log(linhas, modelos):
    """
    O que o log de um robô diz das últimas 24 h, só em números e lugares do código:
    inícios, quedas (o systemd reiniciou sozinho), rastros de erro, avisos e erros
    por lugar do código.
    """
    nivel_de = {onde: nivel for _r, onde, _t, _f, _i, nivel in modelos}
    ranking, _sem_modelo = inventario.perfil_do_log(linhas, modelos)
    problemas = [(onde, texto, nivel_de.get(onde), qtd) for (onde, texto), qtd in ranking
                 if nivel_de.get(onde) in ("warning", "error", "exception", "critical")]
    # O log sai sem hora (-o cat): o último "Started" separa o que veio depois do último
    # início (deploy ou reinício). Um erro que o código novo corrigiu fica só antes dele.
    inicios = [i for i, l in enumerate(linhas) if l.startswith("Started ")]
    depois = linhas[inicios[-1] + 1:] if inicios else linhas
    return {
        "inicios": len(inicios),
        "quedas": sum(1 for l in linhas if "Scheduled restart job" in l or "Failed with result" in l),
        "rastros": sum(1 for l in linhas if l.startswith("Traceback (most recent call last)")),
        "rastros_por_lugar": rastros_do_log(linhas),
        "rastros_depois": sum(1 for l in depois if l.startswith("Traceback (most recent call last)")),
        "rastros_depois_por_lugar": rastros_do_log(depois),
        "avisos": sum(qtd for _o, _t, nivel, qtd in problemas if nivel == "warning"),
        "erros": sum(qtd for _o, _t, nivel, qtd in problemas if nivel != "warning"),
        "problemas": problemas,
    }


# --- Processos dos robôs ---

def processos_do_dia(agora=None):
    """
    O registro dos processos das últimas 24 h por robô e processo: acertos, falhas,
    neutros e cada resultado com o detalhe (textos fixos do código).
    """
    desde = _momento(_agora(agora) - timedelta(hours=24))
    processos = {}
    for robo, processo, resultado, detalhe, ok, qtd in registro_processos.contagem(desde):
        p = processos.setdefault((robo, processo), {"ok": 0, "falhas": 0, "neutros": 0, "resultados": []})
        p["ok" if ok == 1 else "falhas" if ok == 0 else "neutros"] += qtd
        p["resultados"].append((resultado, detalhe, ok, qtd))
    return processos


# --- Metas: o que cada job devia fazer em 24 h ---
# Pedido do Rafael (P12, DECISOES.md, Monitor, deploy e servidor): cada atividade diz o
# que devia fazer no dia, e o checkup compara com o que o registro de processos anotou.
# (robô, processo): (execuções esperadas em 24 h, o mínimo que não cobra). Os de hora em
# hora têm folga para um reinício no minuto do job.
METAS = {
    ("bot_mestre", "monitor de saúde"): (24, 21),
    ("bot_mestre", "botão de ofertas"): (24, 21),
    ("bot_mestre", "financeiro (API da Shopee)"): (24, 21),
    ("bot_mestre", "faxina do disco"): (4, 3),
    ("bot_mestre", "faxina da lixeira"): (1, 1),
    ("bot_mestre", "métricas do dia"): (1, 1),
    ("bot_mestre", "fechamento do dia dos parceiros"): (1, 1),
    ("bot_mestre", "financeiro: varredura dos pendentes"): (1, 1),
    ("bot_mestre", "conferência diária dos grupos"): (1, 1),
    ("bot_mestre", "backup diário"): (1, 1),
    ("divulgacao", "registro dos administradores"): (1, 1),
    ("divulgacao", "faxina do Acervo Viral"): (4, 3),
    ("divulgacao", "faxina do tópico do Baixador"): (144, 100),
    ("shopee_video", "resumo das 22h"): (1, 1),
    ("shopee_video", "descurtir tudo (4h)"): (1, 1),
}
# Os processos que acontecem quando há o que fazer (um pedido, uma postagem, um envio):
# não têm uma quantidade certa por dia e entram na seção dos processos e nas seções de
# cada atividade (filas, rotinas, captura, Shopee Vídeo). O começo do nome basta (os
# processos com o escopo no fim, como "envio (grupos)"). O tests/test_checkup.py barra
# processo novo de robô que não esteja aqui nem em METAS.
SEM_META = {
    ("autorais", "Correio Público: download"), ("autorais", "captura de parceiro"),
    ("autorais", "captura para o canal"), ("autorais", "repostagem ao grupo"),
    ("baixador", "Shopee pela Apify"), ("baixador", "conferência semanal da Shopee Vídeo"),
    ("baixador", "mensagem sem link"), ("baixador", "pedido "),
    ("bot_mestre", "garimpo de ofertas"), ("bot_mestre", "lembrete de pergunta do Claude"),
    ("bot_mestre", "relatório semanal de vendas"),
    ("bot_mestre", "postagem "), ("bot_mestre", "rotina "),
    ("divulgacao", "envio ("), ("divulgacao", "verificação semanal do Grupo Público"),
    ("espelhador", "captura da rota"), ("espelhador", "envio da rota"),
    ("espelhador", "vídeo com link na origem da rota"),
    ("espiao", "captura de vídeo"), ("espiao", "vídeo com link no grupo vigiado"), ("espiao", "IA: nome do produto"),
    ("notas", "envio de nota fiscal"),
    ("shopee_video", "anexar o produto"), ("shopee_video", "assistente: envio"),
    ("shopee_video", "conferência da IA (produto × vídeo)"),
    ("shopee_video", "aviso de punição para recorrer"), ("shopee_video", "conferir a tela final"),
    ("shopee_video", "curtir o produto"), ("shopee_video", "descurtir no fim do rascunho"),
    ("shopee_video", "feed: "),
    ("shopee_video", "notificações (respostas)"), ("shopee_video", "preparo interrompido"),
    ("shopee_video", "rodada fora do bot"), ("shopee_video", "título da IA"),
    ("shopee_video", "voltar no app"), ("shopee_video", "app travado"),
    ("shopee_video", "produto de loja de férias"), ("shopee_video", "comissão: "),
    ("shopee_video", "responder comentário"),
}


def classificado(robo, processo):
    """O processo tem meta (METAS) ou está entre os que acontecem quando há o que fazer (SEM_META)?"""
    return (robo, processo) in METAS or any(r == robo and processo.startswith(p) for r, p in SEM_META)


def metas_do_dia(processos):
    """Para cada job com meta: (robô, processo, esperado, feito, mínimo), pelo registro das últimas 24 h."""
    return [(robo, processo, esperado, sum(processos.get((robo, processo), {}).get(k, 0)
                                           for k in ("ok", "falhas", "neutros")), minimo)
            for (robo, processo), (esperado, minimo) in METAS.items()]


# --- Memória dos pontos de atenção ---
# Pedido do Rafael (P12): cada ponto mostra se é novo, se repete há dias ou se voltou
# depois de resolvido (a correção não funcionou), e o checkup lista o que se resolveu.
# Guarda só a forma do ponto (o texto fixo do código, com os números trocados por #).
DIAS_DA_MEMORIA = 30


def chave_do_ponto(ponto):
    """O ponto sem os números: o mesmo problema em dias diferentes tem a mesma chave."""
    return re.sub(r"\d+(?:[.,:]\d+)*", "#", ponto)


def _criar_tabela_pontos(con):
    con.execute("CREATE TABLE IF NOT EXISTS checkup_pontos (dia TEXT, chave TEXT, PRIMARY KEY (dia, chave))")


def lembrar_pontos(pontos, agora=None):
    """
    Guarda os pontos de hoje (o checkup rodado de novo no mesmo dia troca os de hoje) e
    devolve ({ponto: marca}, resolvidos): a marca é "novo", "há N dias seguidos" ou
    "voltou" (já tinha aparecido e sumido); resolvidos são as chaves do checkup anterior
    que não aparecem hoje.
    """
    agora = _agora(agora)
    hoje = agora.strftime("%Y-%m-%d")
    with db.conexao() as con:
        _criar_tabela_pontos(con)
        historico = con.execute("SELECT dia, chave FROM checkup_pontos WHERE dia < ?", (hoje,)).fetchall()
        con.execute("DELETE FROM checkup_pontos WHERE dia = ? OR dia < ?",
                    (hoje, (agora - timedelta(days=DIAS_DA_MEMORIA)).strftime("%Y-%m-%d")))
        # A linha vazia marca que o checkup rodou no dia, mesmo sem nenhum ponto.
        con.executemany("INSERT OR IGNORE INTO checkup_pontos (dia, chave) VALUES (?, ?)",
                        [(hoje, "")] + [(hoje, chave_do_ponto(p)) for p in pontos])
    dias = sorted({dia for dia, _ in historico}, reverse=True)
    por_dia = defaultdict(set)
    for dia, chave in historico:
        por_dia[dia].add(chave)
    marcas = {}
    for ponto in pontos:
        chave = chave_do_ponto(ponto)
        seguidos = 0
        for dia in dias:
            if chave not in por_dia[dia]:
                break
            seguidos += 1
        if seguidos:
            marcas[ponto] = f"há {seguidos + 1} dias seguidos"
        elif any(chave in chaves for chaves in por_dia.values()):
            marcas[ponto] = "voltou"
        else:
            marcas[ponto] = "novo"
    hoje_chaves = {chave_do_ponto(p) for p in pontos}
    resolvidos = sorted(c for c in por_dia[dias[0]] if c and c not in hoje_chaves) if dias else []
    return marcas, resolvidos


# --- Rotinas e divulgação ---

def _minutos(hora):
    horas, minutos = str(hora).split(":")[:2]
    return int(horas) * 60 + int(minutos)


def rotinas_do_dia(agora=None):
    """
    As rotinas de texto de hoje por canal, pelo histórico que o bot guarda
    (config_rotina.historico_diario: cada rotina e os horários em que saiu): quantas
    saíram, o menor intervalo, os intervalos curtos, as vezes em que o mesmo assunto
    saiu em seguida, quantas de cada assunto e as que saíram a mais ou a menos que o
    configurado (a menos só depois do fim da janela daquela rotina e sem pausa). A que
    falta mas foi adiada há pouco (MINUTOS_DA_ADIADA) ainda vai tentar: fica em "adiadas",
    sem cobrar; a de ontem que ficou adiada e não saiu vem em "ontem_sem_sair".
    """
    agora = _agora(agora)
    config = db.ler_config("config_rotina", {}) or {}
    historico = config.get("historico_diario") or {}
    contagem = historico.get("contagem", {}) if historico.get("data") == agora.strftime("%Y-%m-%d") else {}
    saidas = {canal: [] for canal in rotinas.CANAIS}
    for tipo, horarios in contagem.items():
        # Chave antiga no banco, sem texto no código: não é agendada e nunca saiu de verdade.
        if not rotinas.conhecida(tipo):
            continue
        for hora in horarios if isinstance(horarios, list) else []:
            saidas[rotinas.canal_da_rotina(tipo)].append((_minutos(hora), tipo))
    pausado = {"canal principal": config.get("pausado"), "Viral": config.get("pausado_viral"),
               "Grupo Público": config.get("pausado_publico")}
    resultado = {}
    for canal, lista in saidas.items():
        lista.sort()
        intervalos = [b[0] - a[0] for a, b in zip(lista, lista[1:])]
        por_assunto = Counter(tipo for _m, tipo in lista)
        fora, adiadas, linhas = [], [], {}
        for tipo, regra in config.items():
            if (not isinstance(regra, dict) or "frequencia" not in regra or not rotinas.conhecida(tipo)
                    or rotinas.canal_da_rotina(tipo) != canal):
                continue
            esperado, feitas = int(regra.get("frequencia") or 0), por_assunto.get(tipo, 0)
            if feitas > esperado:
                fora.append((tipo, feitas, esperado, "a mais"))
            elif feitas < esperado and agora.hour >= int(regra.get("fim", 24)) and not pausado[canal]:
                linhas[tipo] = linha_do_tempo_da_rotina(canal, tipo, agora)
                ultima = linhas[tipo][-1] if linhas[tipo] else None
                if (ultima and ultima[1].startswith("adiada")
                        and 0 <= agora.hour * 60 + agora.minute - _minutos(ultima[0]) < MINUTOS_DA_ADIADA):
                    adiadas.append((tipo, feitas, esperado, ultima[0]))
                else:
                    fora.append((tipo, feitas, esperado, "a menos"))
        resultado[canal] = {
            "linha_do_tempo": {tipo: linhas.get(tipo) or linha_do_tempo_da_rotina(canal, tipo, agora)
                               for tipo, *_ in fora},
            "adiadas": adiadas, "ontem_sem_sair": adiadas_de_ontem(canal, agora),
            "enviadas": len(lista), "menor": min(intervalos) if intervalos else None,
            "curtos": sum(1 for i in intervalos if i < INTERVALO_CURTO_ROTINA),
            "seguidos": sum(1 for a, b in zip(lista, lista[1:]) if a[1] == b[1]),
            "por_assunto": por_assunto, "fora_do_previsto": fora, "pausado": bool(pausado[canal]),
        }
    return resultado


def adiadas_de_ontem(canal, agora=None):
    """
    As rotinas do canal que ontem ficaram adiadas e não saíram depois: a última linha do
    registro de ontem é uma adiada, e ela não saiu logo depois da meia-noite. O checkup
    das 22:20 vê a rotina ainda adiada; esta conferência, no dia seguinte, diz se saiu.
    [(tipo, HH:MM da última adiada)].
    """
    agora = _agora(agora)
    ontem = (agora - timedelta(days=1)).strftime("%Y-%m-%d")
    ultima, logo_depois = {}, set()
    for momento, _p, resultado, detalhe, _o in registro_processos.sequencia(
            "bot_mestre", f"rotina {canal}", f"{ontem} 00:00:00"):
        if momento[:10] == ontem:
            ultima[detalhe] = (momento[11:16], resultado)
        elif momento[11:13] == "00":
            logo_depois.add(detalhe)
    return sorted((tipo, hora) for tipo, (hora, resultado) in ultima.items()
                  if resultado.startswith("adiada") and tipo not in logo_depois)


def linha_do_tempo_da_rotina(canal, tipo, agora=None):
    """
    O que o registro diz da rotina hoje, em ordem: [(HH:MM, resultado)] (enviada, adiada,
    pausada...). Mostra onde se perdeu a que saiu a menos; só horas e textos fixos do código.
    """
    desde = _agora(agora).strftime("%Y-%m-%d 00:00:00")
    return [(momento[11:16], resultado)
            for momento, _p, resultado, detalhe, _o in registro_processos.sequencia("bot_mestre", f"rotina {canal}", desde)
            if detalhe == tipo]


def divulgacao_do_dia(agora=None):
    """
    Os envios da divulgação nas últimas 24 h, pelo registro dos processos (o grupo vai
    só como apelido): envios, grupos, o menor intervalo no mesmo grupo, os envios ao
    mesmo grupo abaixo do piso, as vezes em que um grupo que recebe mais de um assunto
    recebeu o mesmo em seguida, e o pico de envios em JANELA_DO_PICO min.
    """
    desde = _momento(_agora(agora) - timedelta(hours=24))
    linhas = registro_processos.sequencia("divulgacao", "envio (", desde, resultado="enviado")
    por_grupo = defaultdict(list)
    for momento, processo, _resultado, _detalhe, origem in linhas:
        por_grupo[origem].append((datetime.strptime(momento, "%Y-%m-%d %H:%M:%S"), processo))
    menor, curtos, seguidos = None, 0, 0
    for envios in por_grupo.values():
        varios_assuntos = len({processo for _m, processo in envios}) > 1
        for (m1, p1), (m2, p2) in zip(envios, envios[1:]):
            intervalo = (m2 - m1).total_seconds() / 60
            menor = intervalo if menor is None else min(menor, intervalo)
            curtos += intervalo < INTERVALO_CURTO_DIVULGACAO
            seguidos += varios_assuntos and p1 == p2
    momentos = sorted(m for envios in por_grupo.values() for m, _p in envios)
    pico, inicio = 0, 0
    for fim, momento in enumerate(momentos):
        while momento - momentos[inicio] > timedelta(minutes=JANELA_DO_PICO):
            inicio += 1
        pico = max(pico, fim - inicio + 1)
    return {"envios": len(linhas), "grupos": len(por_grupo), "menor": menor, "curtos": curtos,
            "seguidos": seguidos, "pico": pico, "por_assunto": Counter(processo for _m, processo, *_ in linhas)}


# --- Captura por grupo de origem e parceiros ---

def _por_origem(robo, prefixo, agora):
    """(últimas 24 h, as 48 h antes delas): quantos registros por apelido de origem."""
    corte = _momento(agora - timedelta(hours=24))
    recente, antes = Counter(), Counter()
    for momento, _p, _r, _d, origem in registro_processos.sequencia(robo, prefixo, _momento(agora - timedelta(hours=72))):
        (recente if momento >= corte else antes)[origem] += 1
    return recente, antes


def _resumo_das_origens(origens, contagens):
    """
    Pela posição na lista do painel (1, 2, 3...): quantas origens, quantas mandaram
    vídeo nas 24 h, as que não mandaram e as que pararam (mandaram nas 48 h antes).
    """
    recente, antes = contagens
    apelidos = [registro_processos.apelido(str(o).lower()) for o in origens]
    return {
        "origens": len(apelidos),
        "com_video": sum(1 for a in apelidos if recente[a]),
        "sem_video": [i + 1 for i, a in enumerate(apelidos) if not recente[a]],
        "pararam": [i + 1 for i, a in enumerate(apelidos) if not recente[a] and antes[a]],
    }


def captura_por_origem(agora=None):
    """
    O que chegou de cada grupo vigiado: Espião (vídeo com link em cada alvo), Espelhador
    (em cada origem das rotas, na ordem das rotas) e parceiros (capturas de cada um).
    """
    agora = _agora(agora)
    alvos = (db.ler_config("alvos_espiao", {}) or {}).get("alvos", [])
    origens_das_rotas = []
    for rota in rotas_espelhador.ler().get("rotas", []):
        origens_das_rotas += [str(o) for o in rota.get("origens", [])]
        if "origem" in rota:
            origens_das_rotas.append(str(rota["origem"]))
    parceiros = []
    try:
        with db.conexao() as conexao:
            parceiros = [str(linha[0]) for linha in conexao.execute("SELECT id FROM parceiros ORDER BY id")]
    except sqlite3.OperationalError:
        pass
    return {
        "Espião": _resumo_das_origens(alvos, _por_origem("espiao", "vídeo com link no grupo vigiado", agora)),
        "Espelhador": _resumo_das_origens(origens_das_rotas,
                                          _por_origem("espelhador", "vídeo com link na origem da rota", agora)),
        "Parceiros": _resumo_das_origens(parceiros, _por_origem("autorais", "captura de parceiro", agora)),
    }


def _chave_resolvida(chave, conexao):
    """A chave do link curto trocada pela do produto, quando o espelhador já abriu o link."""
    if not chave or not chave.startswith("curto_"):
        return chave
    try:
        linha = conexao.execute("SELECT chave_final FROM links_resolvidos WHERE codigo_curto = ?",
                                (chave[len("curto_"):],)).fetchone()
    except sqlite3.OperationalError:
        return chave
    return linha[0] if linha and linha[0] else chave


def parceiros_repetidos(agora=None):
    """
    Nos últimos 3 dias: produtos capturados para mais de um parceiro, e produtos de
    parceiro que também saíram pela conta principal (reservados no sorteio do Público
    ou na fila do Viral).
    """
    agora = _agora(agora)
    desde = _momento(agora - timedelta(days=3))
    try:
        with db.conexao() as conexao:
            linhas = conexao.execute(
                "SELECT parceiro_id, chave_produto FROM fila_parceiros WHERE chave_produto IS NOT NULL "
                "AND chave_produto != '' AND data_captura >= ?", (desde,)).fetchall()
            por_chave = defaultdict(set)
            for parceiro, chave in linhas:
                por_chave[_chave_resolvida(chave, conexao)].add(parceiro)
            da_conta = set()
            try:
                da_conta |= {_chave_resolvida(c, conexao) for (c,) in conexao.execute(
                    "SELECT video_id FROM videos_reservados WHERE parceiro_id = 0 AND data_reserva >= ? "
                    "AND video_id NOT LIKE 'doc_%'", (desde,))}
            except sqlite3.OperationalError:
                pass
            for item in (db.ler_config("fila_clonagem", {}) or {}).get("fila", []):
                if str(item.get("data_captura") or "") >= desde[:10]:
                    da_conta.add(_chave_resolvida(links_shopee.chave_produto(item.get("link_original")), conexao))
    except sqlite3.OperationalError:
        return {"capturas": 0, "entre_parceiros": 0, "com_a_conta": 0}
    return {"capturas": len(linhas),
            "entre_parceiros": sum(1 for parceiros in por_chave.values() if len(parceiros) > 1),
            "com_a_conta": sum(1 for chave in por_chave if chave in da_conta)}


# --- Grupo Público: verificação semanal ---

def verificacao_do_publico(agora=None):
    """
    A última verificação semanal das mensagens do Grupo Público (moderacao_publico.py):
    quando, quantas de membros, suspeitas por regra. Só números. None se nunca rodou.
    """
    dados = db.ler_config("moderacao_publico", {}) or {}
    if not dados.get("quando"):
        return None
    quando = datetime.strptime(dados["quando"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
    return {**dados, "horas": (_agora(agora) - quando).total_seconds() / 3600}


# --- Postagens de hoje ---

def _contar(sql, *params):
    try:
        with db.conexao() as conexao:
            return conexao.execute(sql, params).fetchone()[0] or 0
    except sqlite3.OperationalError:
        return None


def _media_da_metrica(chave, hoje):
    """Média de posts por dia nos 7 dias antes de hoje, pelo retrato das 23:50 (historico_metricas)."""
    try:
        with db.conexao() as conexao:
            valores = [v for (v,) in conexao.execute(
                "SELECT valor FROM historico_metricas WHERE chave = ? AND data < ? ORDER BY data DESC LIMIT 7",
                (chave, hoje))]
    except sqlite3.OperationalError:
        return None
    return sum(valores) / len(valores) if valores else None


def _media_da_tabela(tabela, hoje):
    """Média de posts por dia nos 7 dias antes de hoje, pela data_postagem da própria fila."""
    inicio = (datetime.strptime(hoje, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    total = _contar(f"SELECT COUNT(*) FROM {tabela} WHERE processado = 1 "
                    "AND substr(data_postagem, 1, 10) >= ? AND substr(data_postagem, 1, 10) < ?", inicio, hoje)
    return None if total is None else total / 7


def postagens_de_hoje(agora=None):
    """
    Por fila: postados hoje, ainda na fila para hoje, atrasados (horário vencido há mais
    de 30 min, ou dia anterior no canal principal) e a média dos 7 dias anteriores.
    """
    agora = _agora(agora)
    hoje, limite = agora.strftime("%Y-%m-%d"), _momento(agora - ATRASO_TOLERADO)
    filas = {}

    filas["Canal principal"] = {
        "postados": _contar("SELECT COUNT(*) FROM fila_postagens WHERE status = 'CONCLUIDO' AND data_postagem = ?", hoje),
        "para_hoje": _contar("SELECT COUNT(*) FROM fila_postagens WHERE status = 'PENDENTE' AND data_alvo = ?", hoje),
        # '2000-01-01' é a marca de "postar já", não um dia atrasado.
        "atrasados": _contar("SELECT COUNT(*) FROM fila_postagens WHERE status = 'PENDENTE' "
                             "AND data_alvo < ? AND data_alvo != '2000-01-01'", hoje),
        "media": _media_da_metrica("posts_dia_principal", hoje),
    }

    fila_viral = (db.ler_config("fila_clonagem", {}) or {}).get("fila", [])
    pendentes = [i for i in fila_viral if not i.get("processado")]
    filas["Viral"] = {
        "postados": sum(1 for i in fila_viral if i.get("processado") and str(i.get("data_postagem")) == hoje),
        "para_hoje": sum(1 for i in pendentes if str(i.get("horario_disparo") or "").startswith(hoje)),
        "atrasados": sum(1 for i in pendentes if i.get("horario_disparo") and i["horario_disparo"] < limite),
        "media": _media_da_metrica("posts_dia_viral", hoje),
    }

    for nome, tabela, metrica in (("Grupo Público", "fila_publico", "posts_dia_publico"),
                                  ("Autorais", "fila_autorais", None),
                                  ("Parceiros", "fila_parceiros", None)):
        filas[nome] = {
            "postados": _contar(f"SELECT COUNT(*) FROM {tabela} WHERE processado = 1 "
                                "AND substr(data_postagem, 1, 10) = ?", hoje),
            "para_hoje": _contar(f"SELECT COUNT(*) FROM {tabela} WHERE processado = 0 AND data_alvo = ?", hoje),
            "atrasados": _contar(f"SELECT COUNT(*) FROM {tabela} WHERE processado = 0 "
                                 "AND horario_disparo != '' AND horario_disparo < ?", limite),
            "media": _media_da_metrica(metrica, hoje) if metrica else _media_da_tabela(tabela, hoje),
        }
    return filas


# --- Robô da Shopee Vídeo ---

def robo_da_shopee_video(agora=None):
    """Plano de hoje, rascunhos salvos hoje e as tentativas ruins das últimas 24 h (ação, resultado, passo)."""
    agora = _agora(agora)
    config = db.ler_config(CHAVE_CONFIG_SV, {}) or {}
    pausado = config.get("robo_pausado", True)
    # A conta de Shopee Vídeo suspensa pela Shopee: o robô espera o fim e não salva nada.
    suspenso = ""
    try:
        fim = datetime.strptime(config.get("robo_suspenso_ate") or "", "%Y-%m-%d %H:%M:%S")
        if agora.replace(tzinfo=None) < fim + FOLGA_DA_SUSPENSAO_SV:
            suspenso = fim.strftime("%d/%m %H:%M")
    except ValueError:
        pass
    plano = db.ler_config(CHAVE_DIA_SV, {}) or {}
    hoje = agora.strftime("%Y-%m-%d")
    horarios = plano.get("horarios", []) if plano.get("data") == hoje else []
    vencidos = sum(1 for h in horarios if h <= agora.strftime("%H:%M"))
    # Pela tabela dos rascunhos, que guarda todos; o histórico das tentativas pode ter
    # começado depois.
    salvos = _contar("SELECT COUNT(*) FROM shopee_video_rascunhos WHERE criado_em >= ? "
                     "AND estado NOT IN ('pulado', 'preparando')", hoje)
    linhas = tentativas_recentes(24, agora)
    ruins = [(acao, resultado, passo, qtd) for acao, resultado, passo, qtd, _p, _u in linhas
             if resultado in RESULTADOS_RUINS]
    atrasados, minutos = aprovados_atrasados(agora)
    postados = aprovados_postados(agora)
    pulados = _contar("SELECT COUNT(*) FROM shopee_video_rascunhos WHERE criado_em >= ? AND estado = 'pulado'", hoje)
    # As punições da Saúde do Vídeo que esperam o recurso do Rafael (apelacoes_shopee_video).
    punicoes = _contar("SELECT COUNT(*) FROM shopee_video_punicoes WHERE situacao = 'pendente'")
    return {"ativo": not pausado, "suspenso": suspenso, "horarios": len(horarios), "vencidos": vencidos,
            "salvos": salvos or 0, "pulados": pulados or 0, "ruins": ruins, "linhas": linhas,
            "punicoes": punicoes or 0, "atrasados": atrasados, "minutos_de_atraso": minutos,
            "postados": postados}


def aprovados_postados(agora=None):
    """
    Os aprovados que foram ao ar nas últimas 24 h: [(aprovado HH:MM, previsto HH:MM,
    postado HH:MM, atraso em min)]. O atraso é do postado sobre o previsto: diz se outra
    tarefa (um preparo longo segurando o celular, a pausa) atrasou o post.
    """
    agora = _agora(agora)
    try:
        with db.conexao() as conexao:
            linhas = conexao.execute(
                "SELECT aprovado_em, postar_em, postado_em FROM shopee_video_rascunhos WHERE estado = 'postado' "
                "AND postado_em >= ? AND postar_em IS NOT NULL ORDER BY postado_em",
                (_momento(agora - timedelta(hours=24)),)).fetchall()
    except sqlite3.OperationalError:
        return []
    postados = []
    for aprovado, previsto, postado in linhas:
        try:
            atraso = int((datetime.strptime(postado, "%Y-%m-%d %H:%M:%S")
                          - datetime.strptime(previsto, "%Y-%m-%d %H:%M:%S")).total_seconds() // 60)
        except (TypeError, ValueError):
            continue
        postados.append(((aprovado or "")[11:16] or "?", previsto[11:16], postado[11:16], atraso))
    return postados


def tentativas_recentes(horas, agora=None):
    """
    As tentativas ruins e os pulados das últimas `horas`, por ação, resultado e passo, com a
    hora (HH:MM) da primeira e da última vez: diz se o que parou continua depois de uma
    correção. Só frases fixas do código, nunca o produto nem o motivo.
    """
    agora = _agora(agora)
    vistos = RESULTADOS_RUINS + ("pulado",)
    try:
        with db.conexao() as conexao:
            linhas = conexao.execute(
                "SELECT acao, resultado, passo, COUNT(*), MIN(momento), MAX(momento) FROM shopee_video_tentativas "
                f"WHERE momento >= ? AND resultado IN ({','.join('?' * len(vistos))}) GROUP BY 1, 2, 3 "
                "ORDER BY 4 DESC, 6 DESC",
                (_momento(agora - timedelta(hours=horas)), *vistos)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(acao, resultado, passo, qtd, (primeiro or "")[11:16], (ultimo or "")[11:16])
            for acao, resultado, passo, qtd, primeiro, ultimo in linhas]


def aprovados_atrasados(agora=None):
    """
    Os rascunhos que o Rafael aprovou e passaram da hora de ir ao ar há mais de
    ATRASO_DO_APROVADO: quantos e há quantos minutos está o mais atrasado.
    """
    agora = _agora(agora)
    try:
        with db.conexao() as conexao:
            qtd, mais_antigo = conexao.execute(
                "SELECT COUNT(*), MIN(postar_em) FROM shopee_video_rascunhos WHERE estado = 'aprovado' "
                "AND postar_em IS NOT NULL AND postar_em <= ?",
                (_momento(agora - ATRASO_DO_APROVADO),)).fetchone()
    except sqlite3.OperationalError:
        return 0, 0
    if not qtd:
        return 0, 0
    try:
        antes = datetime.strptime(mais_antigo, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return qtd, 0
    return qtd, int((agora.replace(tzinfo=None) - antes).total_seconds() // 60)


def _linha_da_tentativa(tentativa):
    """Uma linha de tentativas_recentes, com a hora da primeira e da última vez."""
    acao, resultado, passo, qtd, primeiro, ultimo = tentativa
    quando = f"às {ultimo}" if qtd == 1 or primeiro == ultimo else f"de {primeiro} a {ultimo}"
    return f"   {qtd}x {acao} → {resultado} em \"{passo or '?'}\" ({quando})"


def robo_agora(agora=None):
    """
    As linhas do diagnóstico de hora em hora para a retomada do Claude (a cada 3 h): as
    paradas, os erros e os pulados do robô da Shopee Vídeo nas janelas de 3 h e 12 h e os
    aprovados que passaram da hora de ir ao ar. Só ações, passos fixos, horas e números.
    Pedido do Rafael: DECISOES.md, Trabalho com o Claude.
    """
    agora = _agora(agora)
    config = db.ler_config(CHAVE_CONFIG_SV, {}) or {}
    linhas = []
    for horas in JANELAS_DA_RETOMADA:
        recentes = tentativas_recentes(horas, agora)
        ruins = sum(qtd for _a, resultado, _p, qtd, *_h in recentes if resultado in RESULTADOS_RUINS)
        pulados = sum(qtd for _a, resultado, _p, qtd, *_h in recentes if resultado == "pulado")
        linhas.append(f"Robô agora, últimas {horas} h: paradas ou erros {ruins} | pulados {pulados}")
        linhas += [_linha_da_tentativa(t) for t in recentes]
    atrasados, minutos = aprovados_atrasados(agora)
    situacao = "pausada" if config.get("robo_pausado", True) else "ativa"
    linhas.append(f"Aprovados que passaram da hora (mais de {int(ATRASO_DO_APROVADO.total_seconds() // 60)} min): "
                  f"{atrasados}" + (f" (o mais atrasado há {minutos} min)" if atrasados else "")
                  + f" | Postagem: {situacao}")
    return linhas


# --- Sobreposições ---

# O que o robô da Shopee Vídeo faz no celular, pelo nome no registro e pela ação da
# tentativa: o que fica de fora é do bot (rodada, assistente, avisos), não do celular.
PROCESSOS_DO_DESCURTIR = ("descurtir tudo (4h)",)
PROCESSOS_DE_INTERACAO = ("feed:", "notificações (respostas)", "responder comentário")
PROCESSOS_DE_PREPARO = ("curtir o produto", "anexar o produto", "conferência da IA", "conferir a tela final",
                        "título da IA", "produto de loja de férias", "descurtir no fim do rascunho",
                        "preparo interrompido")
ACOES_DE_INTERACAO, ACOES_DE_PREPARO = ("feed", "responder"), ("rascunho", "postar", "apagar")


def _tipo_da_atividade(processo=None, acao=None):
    """'descurtir', 'interação', 'preparo' (preparar, postar, apagar) ou None (outra coisa)."""
    if acao:
        return ("descurtir" if acao == "descurtir" else "interação" if acao in ACOES_DE_INTERACAO
                else "preparo" if acao in ACOES_DE_PREPARO else None)
    if processo.startswith(PROCESSOS_DO_DESCURTIR):
        return "descurtir"
    if processo.startswith(PROCESSOS_DE_INTERACAO):
        return "interação"
    if processo.startswith(PROCESSOS_DE_PREPARO):
        return "preparo"
    return None


def atividades_do_celular(agora=None):
    """
    O que o robô da Shopee Vídeo fez no celular nas últimas 24 h, em ordem: [(momento,
    tipo, o quê)], pelas tentativas (ação e resultado) e pelo registro dos processos (cada
    passo). Só ações, resultados e nomes fixos do código.
    """
    agora = _agora(agora)
    desde = _momento(agora - timedelta(hours=24))
    atividades = []
    try:
        with db.conexao() as conexao:
            tentativas = conexao.execute("SELECT momento, acao, resultado FROM shopee_video_tentativas "
                                         "WHERE momento >= ?", (desde,)).fetchall()
    except sqlite3.OperationalError:
        tentativas = []
    for momento, acao, resultado in tentativas:
        tipo = _tipo_da_atividade(acao=acao)
        if tipo:
            atividades.append((momento, tipo, f"{acao} → {resultado}"))
    for momento, processo, resultado, _d, _o in registro_processos.sequencia("shopee_video", "", desde):
        tipo = _tipo_da_atividade(processo=processo)
        if tipo:
            atividades.append((momento, tipo, f"{processo} → {resultado}"))
    return sorted(atividades)


def sobreposicoes(agora=None):
    """
    Uma tarefa em cima da outra nas últimas 24 h, para o Claude conferir (pergunta do
    Rafael, 25/10: "a sobreposição pode atrapalhar"). O celular tem uma trava (uma tarefa
    de cada vez); aqui entra o que cai no horário de outra:
    - na hora do descurtir (4h), qualquer outra atividade do robô;
    - com o Horário das Interações escolhido, interação fora dele e preparo ou postagem
      dentro dele antes de acabarem os comentários do feed do dia (P26);
    - rotinas de texto do mesmo canal a menos de INTERVALO_CURTO_ROTINA min uma da outra;
    - os envios do modo assistente (só com o robô pausado: um cobre o outro).
    Só horas, ações e nomes fixos do código.
    """
    agora = _agora(agora)
    config = db.ler_config(CHAVE_CONFIG_SV, {}) or {}
    atividades = atividades_do_celular(agora)
    no_descurtir = [(m[11:16], o_que) for m, tipo, o_que in atividades
                    if int(m[11:13]) == HORA_DO_DESCURTIR_SV and tipo != "descurtir"]
    janela = None
    if config.get("robo_interacoes_inicio") is not None and config.get("robo_interacoes_fim") is not None:
        janela = (int(config["robo_interacoes_inicio"]), int(config["robo_interacoes_fim"]))
    # A janela só vale do momento em que o Rafael a escolheu: o que veio antes seguia a regra
    # de então e não conta como sobreposição.
    janela_desde = config.get("robo_interacoes_desde") or ""
    fora_da_janela, preparo_na_janela = [], []
    if janela:
        feitos = defaultdict(int)
        for momento, tipo, o_que in atividades:
            dentro = janela[0] <= int(momento[11:13]) < janela[1]
            if o_que.startswith("feed: comentar → comentado"):
                feitos[momento[:10]] += 1
            if momento < janela_desde:
                continue
            if tipo == "interação" and not dentro:
                fora_da_janela.append((momento[11:16], o_que))
            elif (tipo == "preparo" and dentro and int(momento[11:13]) != HORA_DO_DESCURTIR_SV
                  and feitos[momento[:10]] < COMENTARIOS_NO_FEED_POR_DIA):
                preparo_na_janela.append((momento[11:16], o_que))
    coladas = {}
    for canal, horarios in rotinas_coladas(agora).items():
        if horarios:
            coladas[canal] = horarios
    assistente = [(momento[11:16], resultado) for momento, _p, resultado, _d, _o in registro_processos.sequencia(
        "shopee_video", "assistente: envio", _momento(agora - timedelta(hours=24)))]
    return {"janela": janela, "janela_desde": janela_desde, "no_descurtir": no_descurtir,
            "fora_da_janela": fora_da_janela,
            "preparo_na_janela": preparo_na_janela, "rotinas_coladas": coladas, "assistente": assistente,
            "robo_ativo": not config.get("robo_pausado", True)}


def rotinas_coladas(agora=None):
    """
    As rotinas de texto de hoje que saíram a menos de INTERVALO_CURTO_ROTINA min da
    anterior no mesmo canal: {canal: [(HH:MM, tipo, HH:MM, tipo)]}, pelo histórico do bot.
    """
    agora = _agora(agora)
    config = db.ler_config("config_rotina", {}) or {}
    historico = config.get("historico_diario") or {}
    contagem = historico.get("contagem", {}) if historico.get("data") == agora.strftime("%Y-%m-%d") else {}
    saidas = {canal: [] for canal in rotinas.CANAIS}
    for tipo, horarios in contagem.items():
        if rotinas.conhecida(tipo):
            for hora in horarios if isinstance(horarios, list) else []:
                saidas[rotinas.canal_da_rotina(tipo)].append((_minutos(hora), str(hora)[:5], tipo))
    resultado = {}
    for canal, lista in saidas.items():
        lista.sort()
        resultado[canal] = [(a[1], a[2], b[1], b[2]) for a, b in zip(lista, lista[1:])
                            if b[0] - a[0] < INTERVALO_CURTO_ROTINA]
    return resultado


# --- Respostas aos comentários e feed da Shopee Vídeo ---

# O mesmo de interacoes_shopee_video (o tests/test_checkup.py confere): 3 por dia (P10).
COMENTARIOS_NO_FEED_POR_DIA = 3


def interacoes_da_shopee_video(agora=None):
    """
    As respostas aos comentários dos vídeos e o feed, pelo registro de processos: cada
    resultado das respostas nas últimas 24 h, os comentários com mais de uma resposta do
    perfil, se as respostas rodaram hoje, os comentários no feed hoje (a meta é 3) e o
    mesmo vídeo do feed comentado mais de uma vez em 3 dias. Pedido do Rafael: DECISOES.md,
    Shopee Vídeo.
    """
    agora = _agora(agora)
    desde, hoje = _momento(agora - timedelta(hours=24)), agora.strftime("%Y-%m-%d 00:00:00")
    respostas = registro_processos.sequencia("shopee_video", "responder comentário", desde)
    # O enviado que não apareceu na lista também conta: pode ter saído.
    feed = [linha for linha in registro_processos.sequencia("shopee_video", "feed: comentar",
                                                            _momento(agora - timedelta(days=3)))
            if linha[2] in ("comentado", "não confirmado")]
    curtidas = registro_processos.sequencia("shopee_video", "feed: curtir", desde)
    return {
        "respostas": dict(Counter(resultado for _m, _p, resultado, _d, _o in respostas)),
        # "já respondido" com "2 resposta(s) do perfil" ou mais: o comentário ganhou resposta repetida.
        "duplicadas": sum(1 for _m, _p, resultado, detalhe, _o in respostas
                          if resultado == "já respondido" and not str(detalhe).startswith("1 ")),
        "rodou_hoje": bool(registro_processos.sequencia("shopee_video", "notificações (respostas)", hoje)),
        "feed_hoje": sum(1 for momento, *_ in feed if momento >= hoje),
        "feed_repetidos": sum(1 for n in Counter(o for *_x, o in feed if o).values() if n > 1),
        "curtidas": dict(Counter(resultado for _m, _p, resultado, _d, _o in curtidas)),
        "lives": len(registro_processos.sequencia("shopee_video", "feed: vídeo olhado", desde, resultado="live pulada")),
    }


# --- Baixador e backup ---

def baixador(linhas):
    """Entregues e falhas de download nas últimas 24 h, pelas linhas fixas do log do Baixador."""
    total = {}
    for contagem in inventario.contar_baixador(linhas).values():
        for evento, qtd in contagem.items():
            total[evento] = total.get(evento, 0) + qtd
    return total


# --- Pontos de atenção ---

def pontos_de_atencao(erros, logs, filas, robo_sv, baixados, backup, agora=None, processos=None,
                      rotinas_hoje=None, divulgacao=None, captura=None, repetidos=None, publico=None,
                      interacoes=None, metas=None, sobre=None):
    """As frases fixas, com números, do que o Claude precisa investigar."""
    agora = _agora(agora)
    pontos = []
    for e in erros:
        if e["novo"] or e["qtd"] >= 3:
            marca = "erro novo" if e["novo"] else "erro repetido"
            pontos.append(f"{marca}: {e['qtd']}x {e['lugar']} ({e['tipo']}, origem {e['origem']})")
    for servico, r in logs.items():
        if r["quedas"]:
            pontos.append(f"{servico}: caiu e o systemd reiniciou {r['quedas']} vez(es)")
        # Rastro só de antes do último início (o deploy trouxe o código novo) não cobra:
        # a seção do log mostra quantos vieram depois.
        depois = r.get("rastros_depois", r["rastros"])
        if depois:
            lugares = r.get("rastros_depois_por_lugar") or r.get("rastros_por_lugar") or [("?", "?", depois)]
            tipo, lugar, qtd = lugares[0]
            pontos.append(f"{servico}: {depois} rastro(s) de erro no log depois do último início ({r['rastros']} em "
                          f"24 h; mais comum: {tipo} em {lugar}, {qtd}x)")
        erros_do_log = [p for p in r["problemas"] if p[2] != "warning"]
        if erros_do_log:
            onde, _t, _n, qtd = erros_do_log[0]
            pontos.append(f"{servico}: {r['erros']} linha(s) de erro no log (mais comum: {onde}, {qtd}x)")
    for nome, f in filas.items():
        if f["atrasados"]:
            pontos.append(f"{nome}: {f['atrasados']} item(ns) atrasado(s) na fila")
        if (f["postados"] == 0 and (f["media"] or 0) >= MEDIA_PARA_COBRAR and agora.hour >= HORA_PARA_COBRAR):
            pontos.append(f"{nome}: nenhum post hoje (média de {f['media']:.1f} por dia)")
    if robo_sv["ativo"] and not robo_sv.get("suspenso") and robo_sv["salvos"] < robo_sv["vencidos"]:
        pontos.append(f"Robô da Shopee Vídeo: {robo_sv['vencidos']} horário(s) vencido(s) hoje e "
                      f"{robo_sv['salvos']} rascunho(s) salvo(s) ({robo_sv.get('pulados', 0)} vídeo(s) pulado(s))")
    for acao, resultado, passo, qtd in robo_sv["ruins"]:
        pontos.append(f"Robô da Shopee Vídeo: {acao} → {resultado} em \"{passo or '?'}\" {qtd}x")
    tarde = [atraso for *_h, atraso in robo_sv.get("postados", []) if atraso > ATRASO_DO_APROVADO.total_seconds() // 60]
    if tarde:
        pontos.append(f"Robô da Shopee Vídeo: {len(tarde)} aprovado(s) foram ao ar com mais de "
                      f"{int(ATRASO_DO_APROVADO.total_seconds() // 60)} min de atraso (o maior: {max(tarde)} min)")
    if robo_sv["ativo"] and not robo_sv.get("suspenso") and robo_sv.get("atrasados"):
        pontos.append(f"Robô da Shopee Vídeo: {robo_sv['atrasados']} aprovado(s) passaram da hora de ir ao ar "
                      f"(o mais atrasado há {robo_sv['minutos_de_atraso']} min)")
    if interacoes:
        respostas = interacoes["respostas"]
        if respostas.get("resposta no lugar errado"):
            pontos.append(f"Respostas da Shopee Vídeo: {respostas['resposta no lugar errado']} resposta(s) que não "
                          "ficaram embaixo do comentário certo")
        if respostas.get("sem resposta"):
            pontos.append(f"Respostas da Shopee Vídeo: {respostas['sem resposta']} comentário(s) que ficaram sem "
                          "resposta depois de 3 tentativas")
        if interacoes["duplicadas"]:
            pontos.append(f"Respostas da Shopee Vídeo: {interacoes['duplicadas']} comentário(s) com mais de uma "
                          "resposta do perfil")
        if interacoes["feed_hoje"] > COMENTARIOS_NO_FEED_POR_DIA:
            pontos.append(f"Feed da Shopee Vídeo: {interacoes['feed_hoje']} comentários hoje (o combinado é "
                          f"{COMENTARIOS_NO_FEED_POR_DIA})")
        if interacoes["feed_repetidos"]:
            pontos.append(f"Feed da Shopee Vídeo: {interacoes['feed_repetidos']} vídeo(s) comentado(s) mais de uma "
                          "vez em 3 dias")
        # A meta do dia: com o robô no ar, as respostas rodam uma vez e o feed tem 3 comentários.
        if robo_sv["ativo"] and not robo_sv.get("suspenso") and agora.hour >= HORA_PARA_COBRAR:
            if not interacoes["rodou_hoje"]:
                pontos.append("Respostas da Shopee Vídeo: as Notificações não foram lidas hoje")
            if interacoes["feed_hoje"] < COMENTARIOS_NO_FEED_POR_DIA:
                pontos.append(f"Feed da Shopee Vídeo: {interacoes['feed_hoje']} de {COMENTARIOS_NO_FEED_POR_DIA} "
                              "comentários hoje")
    if sobre:
        if sobre["no_descurtir"]:
            pontos.append(f"Sobreposição: {len(sobre['no_descurtir'])} atividade(s) do robô da Shopee Vídeo na hora "
                          f"do descurtir ({HORA_DO_DESCURTIR_SV}h)")
        if sobre["fora_da_janela"]:
            pontos.append(f"Sobreposição: {len(sobre['fora_da_janela'])} interação(ões) do robô fora do Horário "
                          "das Interações")
        if sobre["preparo_na_janela"]:
            pontos.append(f"Sobreposição: {len(sobre['preparo_na_janela'])} passo(s) de preparo ou postagem no "
                          "Horário das Interações antes dos comentários do feed")
    for robo, processo, esperado, feito, minimo in metas or []:
        if feito < minimo:
            pontos.append(f"{robo}: {processo}: rodou {feito} vez(es) em 24 h, o esperado é {esperado}")
    for (robo, processo), p in (processos or {}).items():
        if p["falhas"] >= FALHAS_PARA_COBRAR and p["falhas"] >= p["ok"]:
            resultado, detalhe, _ok, qtd = max((r for r in p["resultados"] if r[2] == 0), key=lambda r: r[3])
            pontos.append(f"{robo}: {processo}: {p['falhas']} falha(s) e {p['ok']} acerto(s) "
                          f"(mais comum: {resultado}{f' - {detalhe}' if detalhe else ''}, {qtd}x)")
    for canal, r in (rotinas_hoje or {}).items():
        if r["curtos"]:
            pontos.append(f"Rotinas do {canal}: {r['curtos']} intervalo(s) abaixo de {INTERVALO_CURTO_ROTINA} min "
                          f"(menor: {r['menor']} min)")
        if r["seguidos"]:
            pontos.append(f"Rotinas do {canal}: {r['seguidos']} vez(es) o mesmo assunto em seguida")
        for tipo, feitas, esperado, sentido in r["fora_do_previsto"]:
            pontos.append(f"Rotinas do {canal}: {tipo} saiu {feitas} vez(es), configurado {esperado} ({sentido})")
        for tipo, _hora in r.get("ontem_sem_sair", []):
            pontos.append(f"Rotinas do {canal}: ontem, {tipo} ficou adiada e não saiu")
    if divulgacao and divulgacao["curtos"]:
        pontos.append(f"Divulgação: {divulgacao['curtos']} envio(s) ao mesmo grupo com menos de "
                      f"{INTERVALO_CURTO_DIVULGACAO} min (menor: {divulgacao['menor']:.0f} min)")
    if divulgacao and divulgacao["seguidos"]:
        pontos.append(f"Divulgação: {divulgacao['seguidos']} vez(es) o mesmo assunto em seguida no mesmo grupo")
    if divulgacao and divulgacao["pico"] >= PICO_PARA_COBRAR:
        pontos.append(f"Divulgação: {divulgacao['pico']} envios em {JANELA_DO_PICO} min (rajada)")
    for sistema, c in (captura or {}).items():
        if c["pararam"]:
            pontos.append(f"{sistema}: pararam de mandar vídeo (tinham nos 2 dias antes): nº "
                          + ", nº ".join(map(str, c["pararam"])) + " da lista do painel")
    if repetidos and repetidos["entre_parceiros"]:
        pontos.append(f"Parceiros: {repetidos['entre_parceiros']} produto(s) capturado(s) para mais de um parceiro "
                      "nos últimos 3 dias")
    if repetidos and repetidos["com_a_conta"]:
        pontos.append(f"Parceiros: {repetidos['com_a_conta']} produto(s) de parceiro que também saíram pela conta "
                      "principal nos últimos 3 dias")
    # Uma vez por semana: o ponto aparece só no checkup do dia em que ela rodou, e cobra
    # se passou de 8 dias sem rodar (a de segunda não rodou).
    if publico and publico["horas"] <= 24 and publico.get("suspeitas"):
        pontos.append(f"Grupo Público: {publico['suspeitas']} mensagem(ns) suspeita(s) na verificação semanal "
                      "(o Rafael recebeu no privado)")
    if publico and publico["horas"] > 8 * 24:
        pontos.append(f"Grupo Público: a verificação semanal não roda há {publico['horas'] / 24:.0f} dias")
    falhas = baixados.get("falha(s) de download", 0)
    if falhas >= 3 and falhas > baixados.get("entregue(s)", 0):
        pontos.append(f"Baixador: {falhas} falha(s) de download e {baixados.get('entregue(s)', 0)} entregue(s)")
    if backup is None:
        pontos.append("Backup: nenhum em ~/backups")
    elif backup[1] > IDADE_MAXIMA_BACKUP_H:
        pontos.append(f"Backup: o último tem {backup[1]:.0f} h")
    return pontos


# --- Saída ---

def _num(valor):
    return "?" if valor is None else valor


def main():
    agora = _agora()
    print(f"Checkup de {agora.strftime('%d/%m %H:%M')} (últimas 24 h)")

    print("\n== Erros registrados (erros_logs, sem os Links sem conversão)")
    erros = erros_registrados(agora)
    for e in erros:
        print(f"{e['qtd']:4}x  origem {e['origem']} | {e['lugar']} \"{e['texto']}\" | {e['tipo']} | "
              f"último {e['ultimo']}{' | NOVO' if e['novo'] else ''}")
    if not erros:
        print("nenhum")

    print("\n== Log de cada robô")
    modelos = inventario.modelos_de_log()
    logs, linhas_baixador, sem_journal = {}, [], []
    for servico in inventario.SERVICOS + LOGS_POR_NOME:
        try:
            linhas = ler_journal(servico)
        except Exception as e:
            print(f"{servico}: sem acesso ao journal ({type(e).__name__})")
            sem_journal.append(f"{servico}: sem acesso ao journal, o log não foi conferido")
            continue
        if servico == "downloader_bot":
            linhas_baixador = linhas
        r = logs[servico] = resumo_do_log(linhas, modelos)
        print(f"{servico}: {len(linhas)} linha(s) | inícios {r['inicios']} | quedas {r['quedas']} | "
              f"rastros {r['rastros']} ({r['rastros_depois']} depois do último início) | avisos {r['avisos']} | "
              f"erros {r['erros']}")
        for onde, texto, nivel, qtd in r["problemas"][:LUGARES_POR_ROBO]:
            print(f"   {qtd:5}x {nivel:8} {onde:34} {texto}")
        depois_por_lugar = {(tipo, lugar): qtd for tipo, lugar, qtd in r["rastros_depois_por_lugar"]}
        for tipo, lugar, qtd in r["rastros_por_lugar"][:LUGARES_POR_ROBO]:
            print(f"   {qtd:5}x rastro   {tipo} em {lugar} ({depois_por_lugar.get((tipo, lugar), 0)} depois do último início)")

    print("\n== Processos dos robôs (registro, últimas 24 h)")
    processos = processos_do_dia(agora)
    for (robo, processo), p in processos.items():
        print(f"{robo}: {processo}: acertos {p['ok']} | falhas {p['falhas']} | outros {p['neutros']}")
        for resultado, detalhe, _ok, qtd in p["resultados"]:
            print(f"   {qtd:5}x {resultado}{f' - {detalhe}' if detalhe else ''}")
    if not processos:
        print("nenhum processo registrado")

    print("\n== Metas do dia (esperado × feito em 24 h)")
    for robo, processo, esperado, feito, minimo in metas_do_dia(processos):
        print(f"{'✅' if feito >= minimo else '⚠️'} {robo}: {processo}: {feito} de {esperado}")

    print("\n== Rotinas de texto de hoje (por canal)")
    rotinas_hoje = rotinas_do_dia(agora)
    for canal, r in rotinas_hoje.items():
        menor = "—" if r["menor"] is None else f"{r['menor']} min"
        print(f"{canal}{' (pausado)' if r['pausado'] else ''}: enviadas {r['enviadas']} | menor intervalo {menor} | "
              f"abaixo de {INTERVALO_CURTO_ROTINA} min {r['curtos']} | mesmo assunto em seguida {r['seguidos']}")
        if r["por_assunto"]:
            print("   " + " | ".join(f"{tipo}: {qtd}" for tipo, qtd in sorted(r["por_assunto"].items())))
        for tipo, feitas, esperado, sentido in r["fora_do_previsto"]:
            passos = ", ".join(f"{hora} {resultado}" for hora, resultado in r["linha_do_tempo"].get(tipo, []))
            print(f"   {tipo} ({feitas} de {esperado}, {sentido}): {passos or 'nada no registro hoje'}")
        for tipo, feitas, esperado, hora in r["adiadas"]:
            print(f"   {tipo} ({feitas} de {esperado}): adiada às {hora}, ainda vai tentar de novo")
        for tipo, hora in r["ontem_sem_sair"]:
            print(f"   ontem: {tipo} ficou adiada às {hora} e não saiu")
    divulgacao = divulgacao_do_dia(agora)
    menor = "—" if divulgacao["menor"] is None else f"{divulgacao['menor']:.0f} min"
    print(f"Divulgação (24 h): envios {divulgacao['envios']} | grupos {divulgacao['grupos']} | "
          f"menor intervalo no mesmo grupo {menor} | abaixo de {INTERVALO_CURTO_DIVULGACAO} min {divulgacao['curtos']} | "
          f"mesmo assunto em seguida {divulgacao['seguidos']} | pico em {JANELA_DO_PICO} min {divulgacao['pico']}")
    if divulgacao["por_assunto"]:
        print("   " + " | ".join(f"{p}: {q}" for p, q in sorted(divulgacao["por_assunto"].items())))

    print("\n== Captura por grupo de origem (pela posição na lista do painel)")
    captura = captura_por_origem(agora)
    for sistema, c in captura.items():
        sem = ", ".join(f"nº {n}" for n in c["sem_video"]) or "nenhuma"
        print(f"{sistema}: {c['origens']} na lista | com vídeo em 24 h: {c['com_video']} | sem vídeo em 24 h: {sem}"
              + (f" | pararam: {', '.join(f'nº {n}' for n in c['pararam'])}" if c["pararam"] else ""))
    repetidos = parceiros_repetidos(agora)
    print(f"Parceiros (3 dias): capturas com produto identificado {repetidos['capturas']} | mesmo produto em mais "
          f"de um parceiro {repetidos['entre_parceiros']} | também na conta principal {repetidos['com_a_conta']}")

    publico = verificacao_do_publico(agora)
    if publico:
        regras = " | ".join(f"{regra}: {n}" for regra, n in sorted((publico.get("por_regra") or {}).items()))
        print(f"\n== Grupo Público (verificação semanal de {publico['quando'][:16]})\n"
              f"mensagens {publico.get('mensagens', 0)} | de membros {publico.get('de_membros', 0)} | "
              f"suspeitas {publico.get('suspeitas', 0)} | sem julgamento da IA {publico.get('nao_julgadas', 0)}"
              + (f"\n   {regras}" if regras else ""))

    abertas = [p["codigo"] for p in perguntas_rafael.abertas()]
    print(f"\n== Perguntas do Claude ao Rafael\nsem resposta: {len(abertas)}"
          + (f" ({', '.join(abertas)}; o bot lembra de hora em hora)" if abertas else ""))

    print("\n== Postagens de hoje")
    filas = postagens_de_hoje(agora)
    for nome, f in filas.items():
        media = "?" if f["media"] is None else f"{f['media']:.1f}"
        print(f"{nome}: postados {_num(f['postados'])} | ainda para hoje {_num(f['para_hoje'])} | "
              f"atrasados {_num(f['atrasados'])} | média dos 7 dias anteriores {media}/dia")

    print("\n== Robô da Shopee Vídeo")
    robo_sv = robo_da_shopee_video(agora)
    situacao = 'ativo' if robo_sv['ativo'] else 'pausado'
    if robo_sv["suspenso"]:
        situacao += f" | conta suspensa pela Shopee até {robo_sv['suspenso']}"
    if robo_sv.get("punicoes"):
        situacao += f" | punições esperando recurso: {robo_sv['punicoes']}"
    print(f"{situacao} | horários hoje {robo_sv['horarios']} | "
          f"vencidos {robo_sv['vencidos']} | rascunhos salvos hoje {robo_sv['salvos']} | "
          f"vídeos pulados hoje {robo_sv['pulados']}")
    # O caso completo de cada falha fica cifrado para o Claude (casos_robo.yml exportar) e
    # sai depois de analisado (casos_robo.yml apagar).
    print(f"Casos guardados para o checkup do Claude: {len(casos_robo.casos())}")
    for tentativa in robo_sv.get("linhas", []):
        print(_linha_da_tentativa(tentativa))
    print(f"Aprovados que passaram da hora de ir ao ar: {robo_sv['atrasados']}"
          + (f" (o mais atrasado há {robo_sv['minutos_de_atraso']} min)" if robo_sv["atrasados"] else ""))
    for aprovado, previsto, postado, atraso in robo_sv.get("postados", []):
        print(f"   aprovado {aprovado} → previsto {previsto} → postado {postado} (atraso {atraso} min)")

    interacoes = interacoes_da_shopee_video(agora)
    respostas = " | ".join(f"{resultado}: {qtd}" for resultado, qtd in sorted(interacoes["respostas"].items()))
    print(f"Respostas aos comentários (24 h): {respostas or 'nenhuma'} | com mais de uma resposta do perfil: "
          f"{interacoes['duplicadas']} | Notificações lidas hoje: {'sim' if interacoes['rodou_hoje'] else 'não'}")
    curtidas = " | ".join(f"{resultado}: {qtd}" for resultado, qtd in sorted(interacoes["curtidas"].items()))
    print(f"Feed: comentados hoje {interacoes['feed_hoje']} de {COMENTARIOS_NO_FEED_POR_DIA} | mesmo vídeo mais de "
          f"uma vez (3 dias): {interacoes['feed_repetidos']} | curtir (24 h): {curtidas or 'nenhum'} | "
          f"lives puladas (24 h): {interacoes['lives']}")

    print("\n== Sobreposições (uma tarefa no horário de outra, 24 h)")
    sobre = sobreposicoes(agora)
    for titulo, lista in ((f"Robô na hora do descurtir ({HORA_DO_DESCURTIR_SV}h), fora o descurtir",
                           sobre["no_descurtir"]),
                          ("Interação fora do Horário das Interações", sobre["fora_da_janela"]),
                          ("Preparo ou postagem no Horário das Interações antes dos comentários do feed",
                           sobre["preparo_na_janela"])):
        print(f"{titulo}: {len(lista)}")
        for hora, o_que in lista[:10]:
            print(f"   {hora} {o_que}")
    if not sobre["janela"]:
        print("   (Horário das Interações não escolhido: interações e preparo dividem o Horário do Robô)")
    elif sobre["janela_desde"]:
        print(f"   (Horário das Interações {sobre['janela'][0]}h-{sobre['janela'][1]}h, conferido desde "
              f"{sobre['janela_desde'][8:10]}/{sobre['janela_desde'][5:7]} {sobre['janela_desde'][11:16]})")
    else:
        print(f"   (Horário das Interações {sobre['janela'][0]}h-{sobre['janela'][1]}h, sem a hora em que foi "
              "escolhido: conferido nas 24 h)")
    print("Rotinas de texto coladas (menos de "
          f"{INTERVALO_CURTO_ROTINA} min no mesmo canal): {sum(len(v) for v in sobre['rotinas_coladas'].values())}")
    for canal, pares in sobre["rotinas_coladas"].items():
        for hora_a, tipo_a, hora_b, tipo_b in pares:
            print(f"   {canal}: {hora_a} {tipo_a} → {hora_b} {tipo_b}")
    envios = ", ".join(f"{hora} {resultado}" for hora, resultado in sobre["assistente"])
    print(f"Modo assistente (24 h, só manda com o robô pausado): {envios or 'nenhum envio'}")

    print("\n== Baixador e backup")
    baixados = baixador(linhas_baixador)
    print(" | ".join(f"{evento}: {qtd}" for evento, qtd in sorted(baixados.items())) or "nenhum evento")
    backup = backup_dados.ultimo_backup()
    print("Backup: nenhum" if backup is None else f"Backup: o último tem {backup[1]:.1f} h")

    pontos = sem_journal + pontos_de_atencao(erros, logs, filas, robo_sv, baixados, backup, agora, processos,
                                             rotinas_hoje, divulgacao, captura, repetidos, publico, interacoes,
                                             metas_do_dia(processos), sobre)
    marcas, resolvidos = lembrar_pontos(pontos, agora)
    print(f"\n== Pontos de atenção ({len(pontos)})")
    for ponto in pontos:
        print(f"⚠️ {ponto} [{marcas[ponto]}]")
    if not pontos:
        print("nenhum")
    print(f"\n== Resolvidos desde o checkup anterior ({len(resolvidos)})")
    for chave in resolvidos:
        print(f"✅ {chave}")
    if not resolvidos:
        print("nenhum")


if __name__ == "__main__":
    if sys.argv[1:] == ["robo-agora"]:
        print("\n".join(robo_agora()))
    else:
        main()

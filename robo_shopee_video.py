#!/usr/bin/env python3
"""
Robô automático da Shopee Vídeo: no celular guardado do Rafael (celular_robo.py), prepara
rascunhos sozinho e posta os que o Rafael aprova no bot (Shopee Vídeo 🎬 → Rascunhos do
Robô 📝, no painel_shopee_video.py). Usa os passos e as conferências do explorar
(postador_shopee_video.py): a IA confere o produto do link com o vídeo, o produto é achado
pelo nome em Minhas Curtidas e a tela final é conferida antes de salvar e de postar.

O painel (bot_mestre) chama uma rodada a cada 15 min, num processo à parte: o robô passa
minutos tocando no celular, e a IA dele não pode dividir a conexão com a do bot.

    python3 robo_shopee_video.py --rodada
    python3 robo_shopee_video.py --treino      # o treino na hora (botão Testar Caminho 🧭)
    python3 robo_shopee_video.py --preparar    # um rascunho na hora (botão Preparar 1 Agora ⚡)
    python3 robo_shopee_video.py --saude       # a Saúde do Vídeo na hora (botão Gerar Apelação ⚖️)

Cada rodada faz no máximo uma coisa, nesta ordem:
1. o treino da semana, na primeira rodada de segunda-feira: percorre o caminho até a tela
   final sem salvar nem postar e confere cada tela com o mapa (os CAMINHOs abaixo);
2. apaga no app um rascunho que o Rafael recusou;
3. posta um rascunho aprovado cuja hora chegou: os aprovados saem um de cada vez, com um
   intervalo sorteado entre eles, sempre dentro do Horário do Robô;
4. prepara um rascunho novo quando um horário do plano do dia passou: cada dia sorteia
   quantos (a faixa Rascunhos por Dia) e espalha os horários pelo Horário do Robô.
Pausado (Pausar Postagem ⏸️), fora do Horário do Robô, com a tela do celular aberta no
privado do Rafael ou com o explorar tocando nele, não toca em nada. Celular desconectado:
tenta reconectar sozinho (celular_robo.reconectar_sozinho); sem conseguir, pausa a
Postagem e avisa, e o modo assistente volta a mandar as postagens no privado até o
Rafael tocar em Retomar Postagem ▶️. Na Verificação da Shopee para na hora e manda o
link da tela do celular no privado. Com a conta de Shopee Vídeo suspensa pela Shopee (o
aviso fica nas Notificações do app), não toca em nada até o fim da suspensão, e o modo
assistente espera junto; no fim, os dois voltam sozinhos (painel_shopee_video).

Nunca toca em Postar sem o Aprovar do Rafael no bot, nem nos botões de comprar. Curtir e
comentar o próprio vídeo continuam à mão (diretriz 9.1.1): depois de postar, o comentário
chega no privado, numa mensagem só dele. No log, só estados e números: nada de nome de
produto, título ou link.
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import asyncio
import html
import json
import logging
import os
import random
import re
import shutil
import sys
import time
from datetime import datetime, timedelta

import android_virtual as av
import apelacoes_shopee_video as apelacoes
import assistente_shopee_video as assistente
import avisar_rafael
import celular_robo
import db
import postador_shopee_video as ps
from api_shopee import eh_video, link_para_converter
from fuso import fuso_horario
from legendas import nome_da_legenda
from motor_filas import sortear_teto_do_dia

logger = logging.getLogger("RoboShopeeVideo")

CHAVE_CONFIG = "shopee_video"  # a mesma chave do painel_shopee_video
# Começa pausado: o Rafael retoma no painel. Rascunhos por dia em faixa (sorteada a cada
# dia) e o Horário do Robô, em horas de Brasília.
PADRAO = {"robo_pausado": True, "robo_limite_min": 1, "robo_limite_max": 2,
          "robo_inicio": ps.HORARIO_DAS_RODADAS[0], "robo_fim": ps.HORARIO_DAS_RODADAS[1]}
MAXIMO_POR_DIA = 20
CHAVE_DIA = "shopee_video_robo_dia"
# Rascunho do plano que não deu certo volta nas rodadas seguintes: até estas vezes a mais
# com o mesmo vídeo e, se não der, com outro, até VIDEOS_POR_HORARIO vídeos no horário.
# Depois disso o robô espera o próximo horário do plano. Decisão do Rafael: DECISOES.md,
# Shopee Vídeo.
TENTATIVAS_A_MAIS = 2
VIDEOS_POR_HORARIO = 3
# Vídeo de produto sem oferta de afiliado (não paga comissão) fica de lado antes de tocar
# no celular; numa rodada, até estes. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
VIDEOS_SEM_OFERTA_POR_RODADA = 5
SEM_OFERTA = "o link não diz o produto do vídeo (produto sem oferta de afiliado)"
# Produtos do Ver Produtos que o robô confere num vídeo (cada um custa 2 conferências da IA).
MAXIMO_PRODUTOS_DO_VIDEO = 6
# O player do vídeo no app; sem ele, o link não abriu o vídeo.
PLAYER_DO_VIDEO = "rn_vod_player_view_with_surface"
# Segundos a mais antes de desistir do Ver Produtos: o player às vezes demora a mostrá-lo.
ESPERA_DO_VER_PRODUTOS = 8
CHAVE_ESTADO = "shopee_video_robo"
PASTA_RASCUNHOS = os.path.join(av.PASTA_TRABALHO, "rascunhos")
# Minutos sorteados entre uma postagem aprovada e a seguinte.
INTERVALO_DAS_POSTAGENS = (30, 90)
# Minutos sorteados até a primeira postagem, quando nenhuma está marcada.
ESPERA_DA_PRIMEIRA = (5, 40)
# Segunda-feira: o treino da semana roda na primeira rodada do dia. Escolha do Rafael.
DIA_DO_TREINO = 0
MAXIMO_DA_RODADA = 30 * 60  # segundos; o painel mata a rodada que passa disso

# Estados de um rascunho: o que ainda está no app do celular e o que já saiu dele.
NO_APP = ("rascunho", "aprovado", "recusado")

# A suspensão da conta de Shopee Vídeo, como a Shopee avisa (Motorola, 23/10/2026): nas
# Notificações (filtro "Lives, Vídeos e ..."), "Sua conta foi banida temporariamente até
# 26-10-2026 19:04:26 devido ... Você não poderá publicar conteúdos em Shopee Vídeo
# durante o período de suspensão"; na Saúde do Vídeo, "Seu acesso para postar vídeos foi
# banido até 26/10/2026 19:04:26 devido a múltiplas violações". A data é de Brasília.
SUSPENSAO = re.compile(r"\b(?:conta|acesso)\b.{0,80}?\bbanid[oa]\b.{0,40}?\baté (\d{1,2})[-/](\d{1,2})[-/](\d{4}),? "
                       r"(\d{1,2}):(\d{2})(?::(\d{2}))?", re.IGNORECASE | re.DOTALL)
ABA_DAS_NOTIFICACOES = "Notificações"
FILTRO_DOS_VIDEOS = "Lives, Vídeos"
# Quantas vezes o robô rola a lista das notificações procurando o aviso.
ROLADAS_NAS_NOTIFICACOES = 2
# Uns minutos depois do fim antes de voltar: o relógio da Shopee pode atrasar um pouco.
FOLGA_DA_SUSPENSAO = timedelta(minutes=15)
# O aviso de penalidade nas Notificações ("[Esta ação gerou pontos de penalidade] ...").
PENALIDADE = "pontos de penalidade"

# A Saúde do Vídeo (mapeada no Motorola em 24/10/2026, com o vídeo do Rafael): Perfil em
# Shopee Vídeo → Centro do criador (a tela "Live e Vídeo") → o quadro Saúde do Vídeo, que
# abre uma página web com o aviso de suspensão, os pontos de penalidade e os Vídeos de
# Violação dos últimos 30 dias (tipo, "Data de Punição: ..." e "Status da Apelação: ...",
# cada um num texto). Cada punição abre a tela Removido: o título, "Postado em: HH:MM:SS
# AAAA-MM-DD.", a explicação da Shopee e o Apelar aqui (que abre o Recurso, com a Razão
# para apelar de até 200 caracteres e o Enviar: o robô nunca abre nem escreve ali; quem
# cola o texto e envia é o Rafael).
CAMINHO_CENTRO_DO_CRIADOR = [("Centro do criador", 8, "Saúde do Vídeo")]
SAUDE_DO_VIDEO = "Saúde do Vídeo"
VIDEOS_DE_VIOLACAO = "Vídeos de Violação"
DATA_DA_PUNICAO = "Data de Punição:"
STATUS_DA_APELACAO = "Status da Apelação:"
POSTADO_EM = "Postado em:"
APELAR_AQUI = "Apelar aqui"
ROLADAS_NA_SAUDE = 4
# A Saúde é lida de novo pelo aviso de penalidade nas Notificações só depois disto.
INTERVALO_DA_SAUDE = timedelta(hours=6)


class Parada(Exception):
    """
    A rodada para aqui. do_video=True quando o problema é do vídeo (a IA não confirmou,
    o produto não foi achado): ele não volta. Sem isso, o vídeo pode ir numa próxima vez.
    """

    def __init__(self, motivo, do_video=False):
        super().__init__(motivo)
        self.motivo, self.do_video = motivo, do_video


class Verificacao(Exception):
    """A Shopee abriu a Verificação (CAPTCHA): só o Rafael resolve."""


class Suspensa(Exception):
    """
    A Shopee suspendeu a conta de Shopee Vídeo até ate (Brasília): nada de preparar nem
    postar até lá. Não é uma Parada: não gasta tentativa nem avisa rascunho que não saiu.
    """

    def __init__(self, ate):
        super().__init__(f"conta de Shopee Vídeo suspensa pela Shopee até {quando_acaba(ate)}")
        self.ate = ate


# --- Configuração e plano do dia ---

def ler_config():
    return {**PADRAO, **(db.ler_config(CHAVE_CONFIG, {}) or {})}


def agora_br(agora=None):
    return agora or datetime.now(fuso_horario)


def no_horario(config, agora=None):
    return config["robo_inicio"] <= agora_br(agora).hour < config["robo_fim"]


def quantos_hoje(config, dia):
    return sortear_teto_do_dia(CHAVE_ESTADO, dia, config["robo_limite_min"], config["robo_limite_max"])


def planejar(config, dia):
    """
    Horários ("HH:MM") dos rascunhos do dia: o Horário do Robô dividido em partes iguais,
    um minuto sorteado em cada parte, como os envios do modo assistente. Mesmo dia,
    mesma lista. Nunca a mesma quantidade nem os mesmos horários todo dia.
    """
    quantos = quantos_hoje(config, dia)
    if quantos <= 0:
        return []
    inicio, fim = config["robo_inicio"] * 60, min(config["robo_fim"] * 60, 24 * 60 - 1)
    parte = (fim - inicio) / quantos
    sorteio = random.Random(f"{CHAVE_ESTADO}:{dia}")
    horarios = []
    for i in range(quantos):
        minuto = int(inicio + i * parte + sorteio.uniform(min(5, parte / 3), max(parte - 5, parte * 2 / 3)))
        horarios.append(f"{minuto // 60:02d}:{minuto % 60:02d}")
    return sorted(horarios)


def estado_do_dia(config, agora=None):
    """O plano de hoje ({data, horarios, feitos}), refeito quando o dia muda."""
    dia = agora_br(agora).strftime("%Y-%m-%d")
    estado = db.ler_config(CHAVE_DIA, {}) or {}
    if estado.get("data") != dia:
        estado = {"data": dia, "horarios": planejar(config, dia), "feitos": 0}
        db.salvar_config(CHAVE_DIA, estado)
    return estado


def horarios_vencidos(estado, agora=None):
    hora = agora_br(agora).strftime("%H:%M")
    return sum(1 for h in estado["horarios"] if h <= hora)


def consumir_horarios(config, agora=None):
    """
    Marca como feitos os horários que já passaram e diz se havia algum novo. Vários de uma
    vez (robô pausado ou fora do ar) contam como um só: retomar não solta tudo de uma vez.
    O horário novo ganha as tentativas a mais, começa no primeiro vídeo e tira a repetição
    do anterior.
    """
    estado = estado_do_dia(config, agora)
    passados = horarios_vencidos(estado, agora)
    if passados <= estado["feitos"]:
        return False
    estado.update(feitos=passados, tentativas=TENTATIVAS_A_MAIS, videos=1, repetir=False)
    db.salvar_config(CHAVE_DIA, estado)
    return True


def marcar_para_repetir(config, agora=None, video=None, do_video=False):
    """
    O rascunho do plano não deu certo. Com tentativa sobrando, o mesmo vídeo volta na
    rodada seguinte. Sem tentativa, ou com o problema no próprio vídeo (do_video: ele já
    ficou de lado), o horário passa a outro vídeo, com as tentativas de novo, até
    VIDEOS_POR_HORARIO; o vídeo que esgotou as tentativas fica de lado só hoje. Sem vídeo
    na fonte não há outro para tentar: o horário acaba. Decisão do Rafael: DECISOES.md,
    Shopee Vídeo.
    """
    estado = estado_do_dia(config, agora)
    if not do_video and estado.get("tentativas", 0) > 0:
        estado["repetir"] = True
    elif video and estado.get("videos", 1) < VIDEOS_POR_HORARIO:
        if not do_video:
            estado["evitar"] = estado.get("evitar", []) + [video]
        # Uma tentativa a mais que no começo do horário: a primeira do vídeo novo também
        # passa pelo repetir_o_que_falhou.
        estado.update(videos=estado.get("videos", 1) + 1, tentativas=TENTATIVAS_A_MAIS + 1, repetir=True)
    else:
        estado["repetir"] = False
    db.salvar_config(CHAVE_DIA, estado)


def repetir_o_que_falhou(config, agora=None):
    """O rascunho do plano que falhou volta nesta rodada? Gasta uma das tentativas a mais."""
    estado = estado_do_dia(config, agora)
    if not estado.get("repetir") or estado.get("tentativas", 0) <= 0:
        return False
    estado.update(repetir=False, tentativas=estado["tentativas"] - 1)
    db.salvar_config(CHAVE_DIA, estado)
    return True


def ler_estado():
    return db.ler_config(CHAVE_ESTADO, {}) or {}


def gravar_estado(**campos):
    db.atualizar_config(CHAVE_ESTADO, lambda dados: dados.update(campos))


def semana(agora=None):
    ano, numero, _ = agora_br(agora).isocalendar()
    return f"{ano}-{numero:02d}"


def treino_da_semana_pendente(agora=None):
    """É segunda-feira e o treino desta semana ainda não rodou?"""
    return agora_br(agora).weekday() == DIA_DO_TREINO and ler_estado().get("treino_semana") != semana(agora)


# --- Suspensão da conta pela Shopee ---

def quando_acaba(ate):
    return ate.strftime("%d/%m às %H:%M")


def suspenso_ate(config):
    """O fim da suspensão guardado (datetime de Brasília), ou None."""
    try:
        fim = datetime.strptime(config.get("robo_suspenso_ate") or "", "%Y-%m-%d %H:%M:%S")
        return fim.replace(tzinfo=fuso_horario)
    except ValueError:
        return None


def suspensa(config, agora=None):
    """
    A conta de Shopee Vídeo está suspensa agora (até o fim e a folga)? Enquanto estiver, o
    robô não toca no celular e o assistente fica em espera. Decisão do Rafael:
    DECISOES.md, Shopee Vídeo.
    """
    ate = suspenso_ate(config)
    return bool(ate) and agora_br(agora) < ate + FOLGA_DA_SUSPENSAO


def guardar_suspensao(ate):
    """
    Guarda o fim da suspensão. A pausa do Rafael (robo_pausado) fica como está: no fim,
    volta o que ele tinha escolhido. Devolve True se a data é nova (para avisar uma vez só).
    """
    texto = ate.strftime("%Y-%m-%d %H:%M:%S")

    def gravar(dados):
        nova = dados.get("robo_suspenso_ate") != texto
        dados["robo_suspenso_ate"] = texto
        return nova
    return bool(db.atualizar_config(CHAVE_CONFIG, gravar))


def remarcar_aprovados(config, agora=None):
    """
    Os aprovados que esperaram a suspensão ganham horário novo, espalhados como na
    aprovação (proxima_postagem): no fim dela, nunca saem todos de uma vez.
    """
    aprovados = sorted(listar("aprovado"), key=lambda r: (r["postar_em"] or "", r["id"]))
    for rascunho in aprovados:
        atualizar(rascunho["id"], postar_em=None)
    for rascunho in aprovados:
        atualizar(rascunho["id"], postar_em=proxima_postagem(config, agora))
    return len(aprovados)


def fim_da_suspensao(agora=None):
    """
    A suspensão acabou (com a folga)? Tira a marca, espalha de novo os aprovados e devolve
    o aviso para o privado do Rafael; None se não havia suspensão ou ela continua. O
    painel chama a cada 15 min. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    config = ler_config()
    ate = suspenso_ate(config)
    if not ate or suspensa(config, agora):
        return None
    db.atualizar_config(CHAVE_CONFIG, lambda dados: dados.pop("robo_suspenso_ate", None))
    aprovados = remarcar_aprovados(config, agora)
    fila = f" Os {aprovados} aprovado(s) que esperavam saem espalhados no Horário do Robô." if aprovados else ""
    if not config["robo_pausado"]:
        return ("✅ Robô da Shopee Vídeo: a suspensão da Shopee Vídeo acabou. Voltei a preparar e postar no "
                f"Horário do Robô, e o modo assistente segue em espera.{fila}\n\n"
                "Se você tirou o Motorola do carregador, ponha de volta e confira a Depuração por Wi-Fi: sem o "
                "celular, o robô pausa e avisa aqui, e o modo assistente volta a mandar as postagens.")
    if config.get("pausado", True):
        return ("✅ Shopee Vídeo: a suspensão acabou. O robô e o modo assistente continuam pausados, como você "
                "deixou: para voltar, toque em Shopee Vídeo 🎬 → Robô Automático 🤖 → Retomar Postagem ▶️.")
    return ("✅ Shopee Vídeo: a suspensão acabou. O robô continua pausado, como você deixou, e o modo assistente "
            "volta a mandar as postagens aqui no privado.")


def suspensao_na_tela(xml, agora=None):
    """
    O fim da suspensão que a tela (Notificações ou Saúde do Vídeo) mostra (datetime de
    Brasília), ou None. Suspensão que já acabou não conta; com mais de uma, vale a que
    acaba por último.
    """
    fins = []
    for el in ps.elementos(xml):
        texto = el["texto"]
        if "publicar" not in texto.casefold() and "postar" not in texto.casefold():
            continue
        for dia, mes, ano, hora, minuto, segundo in SUSPENSAO.findall(texto):
            try:
                fim = datetime(int(ano), int(mes), int(dia), int(hora), int(minuto), int(segundo or 0),
                               tzinfo=fuso_horario)
            except ValueError:
                continue
            if fim > agora_br(agora):
                fins.append(fim)
    return max(fins, default=None)


# --- Rascunhos (tabela shopee_video_rascunhos) ---

COLUNAS = ("id", "id_video", "criado_em", "estado", "arquivo", "print", "link", "produtos", "titulo",
           "comentario", "aprovado_em", "postar_em", "postado_em", "link_post", "motivo", "fonte", "conferencia")
# Colunas que vieram depois da tabela: entram nas tabelas antigas sem perder nada.
COLUNAS_NOVAS = ("fonte", "conferencia")


def _criar_tabela(con):
    con.execute("CREATE TABLE IF NOT EXISTS shopee_video_rascunhos ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, id_video TEXT, criado_em TEXT, estado TEXT, "
                "arquivo TEXT, print TEXT, link TEXT, produtos TEXT, titulo TEXT, comentario TEXT, "
                "aprovado_em TEXT, postar_em TEXT, postado_em TEXT, link_post TEXT, motivo TEXT, "
                "fonte TEXT, conferencia TEXT)")
    existentes = {linha[1] for linha in con.execute("PRAGMA table_info(shopee_video_rascunhos)")}
    for coluna in COLUNAS_NOVAS:
        if coluna not in existentes:
            con.execute(f"ALTER TABLE shopee_video_rascunhos ADD COLUMN {coluna} TEXT")


def _momento(agora=None):
    return agora_br(agora).strftime("%Y-%m-%d %H:%M:%S")


def _linha_para_dict(linha):
    rascunho = dict(zip(COLUNAS, linha))
    rascunho["produtos"] = json.loads(rascunho["produtos"] or "[]")
    return rascunho


def listar(*estados):
    """Os rascunhos nesses estados, do mais velho para o mais novo."""
    with db.conexao() as con:
        _criar_tabela(con)
        marcas = ",".join("?" * len(estados))
        linhas = con.execute(f"SELECT {', '.join(COLUNAS)} FROM shopee_video_rascunhos "
                             f"WHERE estado IN ({marcas}) ORDER BY criado_em, id", estados).fetchall()
    return [_linha_para_dict(linha) for linha in linhas]


def pegar(ident):
    with db.conexao() as con:
        _criar_tabela(con)
        linha = con.execute(f"SELECT {', '.join(COLUNAS)} FROM shopee_video_rascunhos WHERE id = ?",
                            (ident,)).fetchone()
    return _linha_para_dict(linha) if linha else None


def atualizar(ident, **campos):
    if "produtos" in campos:
        campos["produtos"] = json.dumps(campos["produtos"], ensure_ascii=False)
    with db.conexao() as con:
        _criar_tabela(con)
        con.execute(f"UPDATE shopee_video_rascunhos SET {', '.join(f'{c} = ?' for c in campos)} WHERE id = ?",
                    (*campos.values(), ident))


def criar(id_video, agora=None):
    with db.conexao() as con:
        _criar_tabela(con)
        cursor = con.execute("INSERT INTO shopee_video_rascunhos (id_video, criado_em, estado) VALUES (?, ?, ?)",
                             (id_video, _momento(agora), "preparando"))
        return cursor.lastrowid


def apagar_registro(ident):
    with db.conexao() as con:
        _criar_tabela(con)
        con.execute("DELETE FROM shopee_video_rascunhos WHERE id = ?", (ident,))


def ids_usados():
    """Os vídeos que o robô já usou ou pulou: não voltam."""
    with db.conexao() as con:
        _criar_tabela(con)
        return {linha[0] for linha in con.execute("SELECT id_video FROM shopee_video_rascunhos")}


# --- Histórico das tentativas (tabela shopee_video_tentativas) ---
# Cada coisa que o robô tenta (rascunho, postar, apagar, treino) e como terminou, com o
# passo em que parou. O Rafael vê em Histórico do Robô 📋, recebe o aviso do rascunho que
# não saiu e o resumo das 22h; o diagnóstico do servidor, que é público, conta só os
# resultados e os passos, nunca o produto nem o motivo. Decisão do Rafael: DECISOES.md,
# Shopee Vídeo. Fica 3 dias no banco, como todo registro de processo (DECISOES.md,
# Trabalho com o Claude).
DIAS_DO_HISTORICO = 3
LINHAS_DO_HISTORICO = 12
# O passo em que parou, achado no motivo (as frases fixas do robô e do postador). A
# ordem importa: o primeiro trecho que aparece no motivo decide.
PASSOS = (
    ("suspensa pela Shopee", "conta suspensa pela Shopee"),
    ("sem oferta de afiliado", "oferta de afiliado"),
    ("o link não diz o produto", "achar o produto do link"),
    ("violação", "diretrizes da Shopee"),
    ("a IA", "conferência da IA"),
    ("Ver Produtos", "Ver Produtos"),
    ("foi removido", "vídeo removido"),
    ("coração", "curtir o produto"),
    ("curtido", "curtir o produto"),
    ("não está na página", "curtir o produto"),
    ("galeria", "escolher o vídeo na galeria"),
    ("rascunho aberto", "abrir o rascunho"),
    ("nenhum rascunho salvo", "abrir o rascunho"),
    ("legenda", "escrever o título"),
    ("título", "escrever o título"),
    ("toquei em Rascunhos", "salvar em Rascunhos"),
    ("Adicionar", "anexar o produto"),
    ("não está na lista", "anexar o produto"),
    ("tela final", "conferir a tela final"),
    ("Postar", "postar"),
    ("Excluir", "apagar o rascunho"),
    ("verificação", "verificação da Shopee"),
    ("desconectado", "celular desconectado"),
    ("nenhum vídeo", "vídeo da fonte"),
    ("sem oferta", "oferta de afiliado"),
    ("não consegui voltar", "navegar no app"),
    ("não achei", "navegar no app"),
    ("erro", "erro inesperado"),
)
SIMBOLOS = {"salvo": "✅", "postado": "📤", "apagado": "🗑️", "pulado": "⏭️", "parou": "⚠️", "erro": "❌",
            "verificação": "🧩", "suspensa": "⛔", "sem vídeo": "📭", "treino ok": "🧭", "treino parou": "🧭",
            "saúde lida": "🩺"}
NOMES_DAS_ACOES = {"rascunho": "Rascunho", "postar": "Postagem", "apagar": "Apagar rascunho",
                   "treino": "Testar Caminho", "rodada": "Rodada", "saude": "Saúde do Vídeo"}


def _criar_tabela_tentativas(con):
    con.execute("CREATE TABLE IF NOT EXISTS shopee_video_tentativas ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, momento TEXT, acao TEXT, resultado TEXT, "
                "passo TEXT, motivo TEXT, produto TEXT)")


def passo_do_motivo(motivo):
    """Em que passo o robô parou, em poucas palavras, a partir do motivo."""
    texto = str(motivo or "").casefold()
    if not texto:
        return ""
    return next((passo for trecho, passo in PASSOS if trecho.casefold() in texto), "outro")


def registrar_tentativa(acao, resultado, motivo="", produto="", agora=None):
    """Guarda uma tentativa no histórico; as com mais de DIAS_DO_HISTORICO dias saem."""
    try:
        with db.conexao() as con:
            _criar_tabela_tentativas(con)
            con.execute("INSERT INTO shopee_video_tentativas (momento, acao, resultado, passo, motivo, produto) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (_momento(agora), acao, resultado, passo_do_motivo(motivo), str(motivo or ""),
                         str(produto or "")))
            corte = _momento(agora_br(agora) - timedelta(days=DIAS_DO_HISTORICO))
            con.execute("DELETE FROM shopee_video_tentativas WHERE momento < ?", (corte,))
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Tentativa não entrou no histórico: {type(e).__name__}")


def tentativas_desde(desde):
    """As tentativas a partir de desde ("AAAA-MM-DD HH:MM:SS"), da mais nova para a mais velha."""
    with db.conexao() as con:
        _criar_tabela_tentativas(con)
        linhas = con.execute("SELECT momento, acao, resultado, passo, motivo, produto FROM shopee_video_tentativas "
                             "WHERE momento >= ? ORDER BY id DESC", (desde,)).fetchall()
    return [dict(zip(("momento", "acao", "resultado", "passo", "motivo", "produto"), linha)) for linha in linhas]


def _ultimas_24h(agora=None):
    return tentativas_desde(_momento(agora_br(agora) - timedelta(hours=24)))


def _produto_do_video(video):
    return ps.nome_do_produto(video) or ("vídeo com vários produtos (Ver Produtos)" if video.get("de_video") else "")


def _contagem(lista):
    """"✅ 1 salvo | ⏭️ 3 pulado" com o que aconteceu, na ordem de SIMBOLOS."""
    contas = {}
    for tentativa in lista:
        contas[tentativa["resultado"]] = contas.get(tentativa["resultado"], 0) + 1
    return " | ".join(f"{SIMBOLOS.get(r, '•')} {contas[r]} {r}" for r in SIMBOLOS if r in contas)


def texto_historico(agora=None):
    """A tela do Histórico do Robô 📋: as tentativas das últimas 24 h, da mais nova para a mais velha."""
    lista = _ultimas_24h(agora)
    if not lista:
        return "📋 <b>Histórico do Robô</b>\n\nNenhuma tentativa nas últimas 24 h."
    linhas = ["📋 <b>Histórico do Robô</b> (últimas 24 h)", _contagem(lista), ""]
    for t in lista[:LINHAS_DO_HISTORICO]:
        quando = datetime.strptime(t["momento"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
        linhas.append(f"{SIMBOLOS.get(t['resultado'], '•')} <b>{quando}</b> · "
                      f"{NOMES_DAS_ACOES.get(t['acao'], t['acao'])}: {html.escape(t['resultado'])}")
        if t["produto"]:
            linhas.append(f"   🛍️ {html.escape(t['produto'][:80])}")
        if t["motivo"]:
            linhas.append(f"   📍 {html.escape(t['passo'])}: {html.escape(t['motivo'][:120])}")
    if len(lista) > LINHAS_DO_HISTORICO:
        linhas.append(f"\n… e mais {len(lista) - LINHAS_DO_HISTORICO} tentativa(s) antes destas.")
    return "\n".join(linhas)


def texto_resumo(agora=None):
    """O resumo das 22h: o que o robô fez nas últimas 24 h e onde parou. None sem nenhuma tentativa."""
    lista = _ultimas_24h(agora)
    if not lista:
        return None
    problemas = {}
    for t in lista:
        if t["resultado"] in ("pulado", "parou", "erro", "verificação", "sem vídeo", "treino parou"):
            problemas[t["passo"] or "outro"] = problemas.get(t["passo"] or "outro", 0) + 1
    linhas = ["🤖 <b>Resumo do Robô da Shopee Vídeo</b> (últimas 24 h)", "", _contagem(lista)]
    if problemas:
        linhas += ["", "<b>Onde parou</b>"]
        linhas += [f"• {html.escape(passo)}: {n}×" for passo, n in sorted(problemas.items(), key=lambda p: -p[1])]
    linhas += ["", f"📝 Esperando a sua aprovação: <b>{len(esperando_aprovacao())}</b>",
               "Detalhes: Robô Automático 🤖 → Histórico do Robô 📋."]
    return "\n".join(linhas)


def aviso_rascunho_nao_saiu(config, agora=None):
    """
    O fim do "começando um rascunho" quando o rascunho do plano não sai: o produto, o
    passo em que parou, o motivo e quando o robô tenta de novo.
    """
    ultima = (tentativas_desde(_momento(agora_br(agora) - timedelta(hours=1))) or [{}])[0]
    estado = estado_do_dia(config, agora)
    video = f"vídeo {estado.get('videos', 1)} de {VIDEOS_POR_HORARIO}"
    if estado.get("repetir") and estado.get("tentativas", 0) > TENTATIVAS_A_MAIS:
        proxima = f"Tento de novo na próxima rodada (em até 15 min), com outro vídeo: {video}."
    elif estado.get("repetir"):
        feita = TENTATIVAS_A_MAIS - estado.get("tentativas", 0) + 1
        proxima = (f"Tento de novo na próxima rodada (em até 15 min): tentativa {feita + 1} de "
                   f"{TENTATIVAS_A_MAIS + 1} do {video}.")
    else:
        futuros = [h for h in estado.get("horarios", []) if h > agora_br(agora).strftime("%H:%M")]
        proxima = (f"As tentativas deste horário acabaram. Próximo horário do plano: {futuros[0]}." if futuros
                   else "As tentativas deste horário acabaram, e hoje não há mais horários: amanhã tem plano novo.")
    return ("⏭️ Robô da Shopee Vídeo: o rascunho não saiu.\n\n"
            f"🛍️ Produto: {ultima.get('produto') or '—'}\n"
            f"📍 Parou em: {ultima.get('passo') or 'outro'}\n"
            f"❓ Motivo: {ultima.get('motivo') or '—'}\n\n"
            f"🔁 {proxima}\n\n"
            "Tudo o que o robô tentou: Robô Automático 🤖 → Histórico do Robô 📋.")


def esperando_aprovacao():
    return listar("rascunho")


def proxima_postagem(config, agora=None, sorteio=random):
    """
    Quando postar um rascunho que o Rafael acabou de aprovar: depois do último aprovado
    (ou postado) com um intervalo sorteado, ou daqui a poucos minutos se nenhum está
    marcado. Fora do Horário do Robô, vai para o começo do próximo horário, com uns
    minutos sorteados: os aprovados saem espalhados, nunca todos de uma vez.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    momento = agora_br(agora)
    marcados = [r["postar_em"] for r in listar("aprovado") if r["postar_em"]]
    postados = [r["postado_em"] for r in listar("postado") if r["postado_em"]]
    ultima = max(marcados + postados, default="")
    if ultima and ultima >= _momento(momento - timedelta(minutes=INTERVALO_DAS_POSTAGENS[1])):
        base = datetime.strptime(ultima, "%Y-%m-%d %H:%M:%S").replace(tzinfo=momento.tzinfo)
        quando = max(base, momento) + timedelta(minutes=sorteio.randint(*INTERVALO_DAS_POSTAGENS))
    else:
        quando = momento + timedelta(minutes=sorteio.randint(*ESPERA_DA_PRIMEIRA))
    if quando.hour >= config["robo_fim"] or (quando.date() > momento.date() and quando.hour < config["robo_inicio"]):
        dia = quando.date() if quando.hour < config["robo_inicio"] else quando.date() + timedelta(days=1)
        quando = datetime(dia.year, dia.month, dia.day, config["robo_inicio"], tzinfo=momento.tzinfo)
        quando += timedelta(minutes=sorteio.randint(*ESPERA_DA_PRIMEIRA))
    elif quando.hour < config["robo_inicio"]:
        quando = quando.replace(hour=config["robo_inicio"], minute=0) + timedelta(
            minutes=sorteio.randint(*ESPERA_DA_PRIMEIRA))
    return _momento(quando)


def aprovar(ident, agora=None):
    """O Rafael aprovou no bot: o rascunho ganha a hora de ir ao ar. Devolve essa hora."""
    quando = proxima_postagem(ler_config(), agora)
    atualizar(ident, estado="aprovado", aprovado_em=_momento(agora), postar_em=quando)
    return quando


def recusar(ident, agora=None):
    """O Rafael recusou: o robô apaga o rascunho do app numa próxima rodada, e o vídeo não volta."""
    atualizar(ident, estado="recusado", aprovado_em=_momento(agora))


def o_que_fazer(config, agora=None):
    """
    A tarefa desta rodada: ("treino", None), ("apagar", id), ("postar", id), ("saude",
    None) (a Saúde do Vídeo, uma vez por dia), ("rascunho", None) ou None. Gasta o horário do plano, ou uma tentativa a mais do
    rascunho que falhou, quando escolhe um rascunho.
    """
    if treino_da_semana_pendente(agora):
        return "treino", None
    recusados = listar("recusado")
    if recusados:
        return "apagar", recusados[0]["id"]
    agora_txt = _momento(agora)
    prontos = [r for r in listar("aprovado") if r["postar_em"] and r["postar_em"] <= agora_txt]
    if prontos:
        return "postar", min(prontos, key=lambda r: r["postar_em"])["id"]
    if saude_do_dia_pendente(agora):
        return "saude", None
    if consumir_horarios(config, agora) or repetir_o_que_falhou(config, agora):
        return "rascunho", None
    return None


# --- Toques no celular ---

def pausa(segundos):
    """Espera com uns segundos a mais sorteados: toque em ritmo de máquina denuncia robô."""
    time.sleep(segundos + random.uniform(0.5, 2.5))


def tela(d):
    """A tela de agora; para na hora se for a Verificação."""
    xml = d.dump_hierarchy()
    if ps.eh_verificacao(xml):
        raise Verificacao()
    return xml


def tem(xml, alvo):
    return ps.achar(xml, alvo) is not None


def tocar(d, alvo, espera):
    """Toca no botão (texto ou @id) e espera. Nunca nos proibidos (Postar, comprar)."""
    xml = tela(d)
    ponto = ps.achar(xml, alvo)
    if not ponto:
        raise Parada(f"não achei {alvo} na tela")
    if ps.eh_alvo_proibido(alvo) or ps.proibido_no_ponto(xml, *ponto):
        raise Parada(ps.RECUSA)
    d.click(*ponto)
    pausa(espera)


def seguir(d, caminho):
    """Faz os toques do caminho e confere, depois de cada um, que a tela esperada abriu."""
    for alvo, espera, esperado in caminho:
        tocar(d, alvo, espera)
        xml = tela(d)
        if alvo == "@tv_pick_top_next" and tem(xml, "Dicas de Upload"):
            # Só na primeira vez: a janela de dicas antes da edição.
            tocar(d, "Ok", 3)
            tocar(d, "Próximo", 8)
            xml = tela(d)
        if not tem(xml, esperado):
            raise Parada(f"depois de {alvo}, a tela não mostrou {esperado}")


# O caminho no app, como foi mapeado no Motorola (roteiro_robo_shopee_video.md): o que
# tocar, quantos segundos esperar e o que tem de aparecer depois. O treino confere cada
# passo contra este mapa; as rodadas seguem o mesmo caminho.
CAMINHO_PERFIL = [
    ("Eu", 6, "Criadores & Afiliados"),
    ("Criadores & Afiliados", 8, "Conta"),
    ("Conta", 5, "Perfil em Shopee Vídeo"),
    ("Perfil em Shopee Vídeo", 6, "Postar vídeo"),
]
CAMINHO_GALERIA = [
    ("Postar vídeo", 8, "Biblioteca"),
    ("Biblioteca", 6, "@ll_check"),
]
# Depois da galeria (com só o vídeo mais novo marcado): a edição e a tela final.
CAMINHO_EDICAO = [
    ("@tv_pick_top_next", 10, "@tv_compress"),
    ("@tv_compress", 10, "@et_caption"),
]
CAMINHO_PRODUTO = [
    ("@ll_add_product_symbol", 8, "Minhas Curtidas"),
    ("Minhas Curtidas", 5, "Mais Recente"),
    ("Mais Recente", 5, "Adicionar"),
]
# Com um produto já anexado, a tela final mostra "Adicionar Mais" (mapeado no Motorola em
# 23/10/2026): a mesma lista, com o anexado marcado como "Adicionado".
CAMINHO_MAIS_UM_PRODUTO = [
    ("@tv_add_more", 8, "Minhas Curtidas"),
    ("Minhas Curtidas", 5, "Mais Recente"),
    ("Mais Recente", 5, "Adicionar"),
]


def aviso_de_sair(xml):
    """
    A janela que o voltar abre na tela final ("Se você voltar, ... serão ..."), com
    Cancelar e o botão de confirmar (@buttonDefaultPositive). No Motorola (22/10/2026),
    confirmar volta para a edição do vídeo; num rascunho aberto, o rascunho continua
    salvo na lista.
    """
    return (tem(xml, "@buttonDefaultPositive")
            and any(el["id"] == "content" and "voltar" in el["texto"].casefold() for el in ps.elementos(xml)))


def tem_exato(xml, texto):
    """Algum elemento com exatamente esse texto (o "Eu" da barra, não um "seu" no meio de outro)."""
    return any(ps._normal(el["texto"]) == ps._normal(texto) for el in ps.elementos(xml))


def sair_da_edicao(xml):
    """
    A janela que o voltar abre na edição de um vídeo novo (Motorola, 23/10/2026): "Deseja
    sair da página de edição?", com Salvar Rascunho, Descartar (@tv_no_save) e Cancelar.
    O robô descarta: o que ele não terminou não vira rascunho na lista do app.
    """
    return tem(xml, "@tv_no_save") and tem(xml, "sair da página de edição")


def fora_da_shopee(xml):
    """
    A tela é de outro app (o Telegram, a tela inicial do celular): um voltar a mais na
    Shopee sai dela e mostra o app que estava embaixo. Avisos do Android por cima da
    Shopee (pacotes "android" e "com.android.*") não contam: o voltar os fecha. Sem o
    pacote nos elementos, não dá para saber: False.
    """
    pacotes = {el["pacote"] for el in ps.elementos(xml) if el["pacote"]}
    outros = {p for p in pacotes if p != "android" and not p.startswith("com.android.")}
    return bool(outros) and ps.PACOTE not in pacotes


def voltar(d, ate, vezes=15):
    """
    Aperta voltar, confirmando os avisos de sair, até a tela ter um elemento com o texto
    exato. Nunca fecha o app à força: fechar e reabrir em seguida chama a Verificação.
    Fora da Shopee, não aperta voltar: traz a Shopee de volta para a frente.
    """
    for _ in range(vezes):
        xml = tela(d)
        if tem_exato(xml, ate) and not tem(xml, "@et_caption"):
            return
        if fora_da_shopee(xml):
            # Nunca apertar voltar em outro app: a Shopee volta para a frente.
            logger.warning("⚠️ [Robô Shopee Vídeo] O voltar saiu da Shopee: trazendo a Shopee de volta.")
            d.app_start(ps.PACOTE, wait=True)
            pausa(5)
            continue
        if aviso_de_sair(xml):
            tocar(d, "@buttonDefaultPositive", 3)
            continue
        if sair_da_edicao(xml):
            tocar(d, "@tv_no_save", 4)
            continue
        d.press("back")
        pausa(3)
    raise Parada(f"não consegui voltar até {ate}")


def ir_ao_inicio(d):
    """O app na tela de início (a barra de baixo, com Eu), abrindo o app se precisar."""
    d.app_start(ps.PACOTE, wait=True)
    pausa(5)
    voltar(d, "Eu")


def marcar_so_o_mais_novo(d):
    """
    Na galeria, deixa marcado só o vídeo mais novo (o 1º da grade). O app lembra a
    marcação de antes (visto no Motorola em 23/10/2026): tocar sem olhar desmarcaria o
    vídeo, ou juntaria dois vídeos no mesmo post. Cada quadro tem a caixa @ll_check, com
    o número da ordem (@check) quando está marcado.
    """
    for _ in range(4):
        elementos = ps.elementos(tela(d))
        caixas = sorted((el for el in elementos if el["id"] == "ll_check"),
                        key=lambda el: (el["caixa"][1], el["caixa"][0]))
        if not caixas:
            raise Parada("a galeria não mostrou os vídeos")
        marcados = [i for i, caixa in enumerate(caixas)
                    if any(el["id"] == "check" and el["texto"].strip() and ps._dentro(ps._centro(el), caixa["caixa"])
                           for el in elementos)]
        if marcados == [0]:
            return
        # Primeiro desmarca o que não é o mais novo; depois marca o mais novo.
        alvo = next((i for i in marcados if i != 0), 0)
        d.click(*ps._centro(caixas[alvo]))
        pausa(2)
    raise Parada("não consegui deixar marcado só o vídeo mais novo na galeria")


def ir_ao_perfil(d):
    ir_ao_inicio(d)
    seguir(d, CAMINHO_PERFIL)


def ler_suspensao(d, agora=None):
    """
    Olha nas Notificações (filtro Lives, Vídeos e ...) se a Shopee suspendeu a conta de
    Shopee Vídeo, e até quando. Só toca na aba e no filtro e rola a lista: não abre
    nenhuma notificação. Sem o aviso, ou se a tela não abre: None.
    """
    try:
        ir_ao_inicio(d)
        tocar(d, ABA_DAS_NOTIFICACOES, 6)
        tocar(d, FILTRO_DOS_VIDEOS, 5)
        for vez in range(ROLADAS_NAS_NOTIFICACOES + 1):
            xml = tela(d)
            if any(PENALIDADE in el["texto"].casefold() for el in ps.elementos(xml)):
                gravar_estado(penalidade_vista_em=_momento(agora))
            ate = suspensao_na_tela(xml, agora)
            if ate:
                return ate
            if vez < ROLADAS_NAS_NOTIFICACOES:
                ps.rolar(d)
                pausa(2)
    except Parada as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Não consegui olhar as Notificações: {ps.mascarar(e.motivo)}")
    return None


def abrir_galeria(d, agora=None):
    """
    Postar vídeo → Biblioteca. Com a conta de Shopee Vídeo suspensa, o Postar vídeo não
    abre nada (Motorola, 23/10/2026): sem a Biblioteca, o robô olha nas Notificações se
    é suspensão antes de dar a rodada por parada.
    """
    try:
        seguir(d, CAMINHO_GALERIA)
    except Parada:
        ate = ler_suspensao(d, agora)
        if ate:
            raise Suspensa(ate) from None
        raise


# --- A Saúde do Vídeo e as punições (apelação: apelacoes_shopee_video.py) ---

def punicoes_na_tela(xml):
    """
    As punições que a lista Vídeos de Violação mostra: [{tipo, data, status, ponto}], na
    ordem da tela. O tipo é o texto logo antes de "Data de Punição:"; punição sem o status
    na tela (cortada embaixo) fica para depois de rolar.
    """
    achadas, anterior, atual = [], None, None
    for el in ps.elementos(xml):
        texto = " ".join(el["texto"].split())
        if not texto:
            continue
        if texto.startswith(DATA_DA_PUNICAO) and anterior:
            atual = {"tipo": anterior["texto"], "data": texto[len(DATA_DA_PUNICAO):].strip(), "status": "",
                     "ponto": ps._centro(anterior)}
        elif texto.startswith(STATUS_DA_APELACAO) and atual:
            atual["status"] = texto[len(STATUS_DA_APELACAO):].strip()
            achadas.append(atual)
            atual = None
        else:
            anterior = dict(el, texto=texto)
    return achadas


def pontos_de_penalidade(xml):
    """O número logo depois de "Ponto de Penalidade" na Saúde do Vídeo, ou None."""
    elementos = [el for el in ps.elementos(xml) if el["texto"].strip()]
    for i, el in enumerate(elementos):
        if "ponto de penalidade" in el["texto"].casefold():
            seguinte = next((e["texto"].strip() for e in elementos[i + 1:i + 3] if e["texto"].strip().isdigit()), None)
            return int(seguinte) if seguinte else None
    return None


def ler_removido(xml):
    """
    A tela Removido de uma punição: o título do vídeo (o texto logo antes do "Postado
    em"), a data do post, a explicação da Shopee e se ainda há o Apelar aqui.
    """
    elementos = [el for el in ps.elementos(xml) if el["texto"].strip()]
    titulo = postado = explicacao = ""
    for i, el in enumerate(elementos):
        texto = " ".join(el["texto"].split())
        if texto.startswith(POSTADO_EM):
            postado = texto[len(POSTADO_EM):].strip().rstrip(".")
            titulo = " ".join(elementos[i - 1]["texto"].split()) if i else ""
            explicacao = next((" ".join(e["texto"].split()) for e in elementos[i + 1:]
                               if not e["texto"].strip().startswith(APELAR_AQUI)), "")
            break
    return {"titulo": titulo, "postado_em": postado, "explicacao": apelacoes.ler_explicacao(explicacao),
            "pode_apelar": tem(xml, APELAR_AQUI)}


def rascunho_do_post(titulo, postado_em):
    """
    O rascunho postado pelo robô que é o vídeo punido: pelo título (como o app lê, com
    ".." no lugar dos emojis) ou pela hora do post (a Shopee mostra "HH:MM:SS
    AAAA-MM-DD"), com até 20 min de diferença. None: o vídeo não é do robô.
    """
    postados = listar("postado")
    for r in postados:
        if r["titulo"] and titulo and (mesma_legenda(titulo, r["titulo"])
                                       or mesma_legenda(titulo, ps.como_o_android_le(r["titulo"]))):
            return r
    try:
        quando = datetime.strptime(postado_em, "%H:%M:%S %Y-%m-%d")
    except ValueError:
        return None
    for r in postados:
        try:
            if abs((datetime.strptime(r["postado_em"] or "", "%Y-%m-%d %H:%M:%S") - quando).total_seconds()) <= 20 * 60:
                return r
        except ValueError:
            continue
    return None


def _texto_da_apelacao(tipo, detalhe, rascunho):
    """O texto do recurso pela IA, com o que o robô sabe do vídeo. Devolve (texto, observação)."""
    if not detalhe["pode_apelar"]:
        return "", "A Shopee não mostra mais o Apelar aqui nesta punição: o prazo do recurso acabou."
    produtos, conferencia, fonte = [], "", ""
    if rascunho:
        produtos = rascunho["produtos"] or []
        fonte = rascunho.get("fonte") or ""
        try:
            conferencia = "; ".join(str(v) for v in json.loads(rascunho.get("conferencia") or "[]"))[:400]
        except (TypeError, ValueError):
            conferencia = ""
    return asyncio.run(apelacoes.gerar_texto(tipo, detalhe["explicacao"], detalhe["titulo"], produtos, conferencia,
                                             fonte))


def abrir_saude(d):
    """
    Perfil em Shopee Vídeo → Centro do criador → o quadro Saúde do Vídeo. O nome do quadro
    não aceita toque: o robô toca no que aceita na mesma linha (o "Melhoria Necessária",
    "Bom"...) ou, sem ele, na frase logo abaixo.
    """
    ir_ao_perfil(d)
    seguir(d, CAMINHO_CENTRO_DO_CRIADOR)
    elementos = ps.elementos(tela(d))
    rotulo = next((el for el in elementos if ps._normal(el["texto"]) == ps._normal(SAUDE_DO_VIDEO)), None)
    if not rotulo:
        raise Parada("o Centro do criador não mostrou a Saúde do Vídeo")
    x, y = ps._centro(rotulo)
    na_linha = [el for el in elementos if el["clicavel"] and abs(ps._centro(el)[1] - y) <= 60 and ps._centro(el)[0] > x]
    abaixo = [el for el in elementos if el["clicavel"] and y < ps._centro(el)[1] <= y + 200]
    alvo = (na_linha or sorted(abaixo, key=lambda el: ps._centro(el)[1]) or [rotulo])[0]
    d.click(*ps._centro(alvo))
    pausa(8)
    if not tem(tela(d), VIDEOS_DE_VIOLACAO):
        raise Parada("a Saúde do Vídeo não abriu")


def ler_saude(d, agora=None):
    """
    Lê a Saúde do Vídeo: a suspensão, os pontos de penalidade e cada punição. Punição nova
    sem recurso: abre a tela dela, lê o vídeo e pede à IA o texto do recurso; ela entra em
    apelacoes_shopee_video, e o bot_mestre a manda no privado e lembra de hora em hora.
    Punição já conhecida só atualiza o status (recorrida no app = o lembrete para). Não
    abre o Recurso nem escreve nada no app. Devolve (novas, total, pontos).
    Pedido do Rafael: DECISOES.md, Shopee Vídeo.
    """
    # A tentativa conta para a leitura do dia mesmo se der errado: a Saúde que não abre não
    # pode tomar todas as rodadas do dia no lugar dos rascunhos.
    gravar_estado(saude_tentada_em=_momento(agora))
    abrir_saude(d)
    xml = tela(d)
    pontos = pontos_de_penalidade(xml)
    ate = suspensao_na_tela(xml, agora)
    if ate and guardar_suspensao(ate):
        avisar_suspensao(ate)
    vistas, novas = set(), 0
    for _ in range(ROLADAS_NA_SAUDE + 1):
        andou = False
        while True:
            punicao = next((p for p in punicoes_na_tela(tela(d))
                            if apelacoes.chave(p["tipo"], p["data"]) not in vistas), None)
            if not punicao:
                break
            vistas.add(apelacoes.chave(punicao["tipo"], punicao["data"]))
            andou = True
            if apelacoes.recorrida_no_app(punicao["status"]) or apelacoes.conhecida(punicao["tipo"], punicao["data"]):
                apelacoes.guardar(punicao["tipo"], punicao["data"], punicao["status"], agora=agora)
                continue
            d.click(*punicao["ponto"])
            pausa(7)
            xml = tela(d)
            if not tem(xml, POSTADO_EM):
                # A tela da punição não abriu: o voltar sairia da lista. Fica para a próxima leitura.
                logger.warning("⚠️ [Robô Shopee Vídeo] A tela de uma punição não abriu na Saúde do Vídeo.")
                continue
            detalhe = ler_removido(xml)
            d.press("back")
            pausa(4)
            rascunho = rascunho_do_post(detalhe["titulo"], detalhe["postado_em"])
            texto, observacao = _texto_da_apelacao(punicao["tipo"], detalhe, rascunho)
            apelacoes.guardar(punicao["tipo"], punicao["data"], punicao["status"], detalhe["titulo"],
                              detalhe["postado_em"], rascunho["id"] if rascunho else None,
                              (rascunho or {}).get("fonte") or "", texto, observacao,
                              pode_apelar=detalhe["pode_apelar"], agora=agora)
            novas += 1
        if not andou:
            break
        ps.rolar(d)
        pausa(3)
    gravar_estado(saude_lida_em=_momento(agora), saude_pontos=pontos, saude_punicoes=len(vistas))
    _sair_sem_salvar(d)
    return novas, len(vistas), pontos


def saude_do_dia_pendente(agora=None):
    """O robô ainda não tentou ler a Saúde do Vídeo hoje? (uma vez por dia)"""
    return not (ler_estado().get("saude_tentada_em") or "").startswith(agora_br(agora).strftime("%Y-%m-%d"))


def saude_pedida_pela_notificacao(agora=None):
    """
    O robô viu o aviso de penalidade nas Notificações depois da última leitura da Saúde,
    e ela tem mais de INTERVALO_DA_SAUDE: lê de novo para achar a punição nova.
    """
    estado = ler_estado()
    vista = estado.get("penalidade_vista_em") or ""
    ultima = max(estado.get("saude_lida_em") or "", estado.get("saude_tentada_em") or "")
    return bool(vista) and vista > ultima and ultima <= _momento(agora_br(agora) - INTERVALO_DA_SAUDE)


# A legenda e a comparação com o título ficam no postador, que o explorar também usa.
legenda_na_tela = ps.legenda_na_tela
mesma_legenda = ps.mesma_legenda


def video_do_rascunho(rascunho):
    """O vídeo no formato que as conferências do explorar usam, com os produtos que o rascunho anexou."""
    return {"id": rascunho["id_video"], "arquivo": rascunho["arquivo"], "link": rascunho["link"],
            "nome": (rascunho["produtos"] or [""])[0], "produtos": rascunho["produtos"] or []}


def avisar(texto):
    try:
        return avisar_rafael.mandar_texto(texto)
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Aviso não chegou ao Rafael: {type(e).__name__}")
        return False


def avisar_foto(caminho, legenda):
    try:
        return avisar_rafael.mandar_foto(caminho, legenda)
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Foto não chegou ao Rafael: {type(e).__name__}")
        return False


# --- Preparar um rascunho ---

def proximo_video(config, evitar=()):
    """
    O vídeo da Fonte dos Vídeos do painel que nem o assistente mandou nem o robô usou,
    com link de produto ou de vídeo (Ver Produtos; "de_video" no dicionário), fora os de
    evitar (os que esgotaram as tentativas hoje). Sem nenhum, None.
    """
    fonte = config.get("fonte", assistente.FONTE_PADRAO)
    usados = ids_usados() | set(evitar)
    with db.conexao() as con:
        assistente._criar_tabela(con)
        mandados = {linha[0] for linha in con.execute("SELECT id_unico FROM shopee_video_enviados")}
    for id_video, arquivo, link, legenda in assistente._candidatos(fonte if fonte in assistente.FONTES
                                                                      else assistente.FONTE_PADRAO):
        if (id_video in mandados or id_video in usados or not arquivo or not link
                or not os.path.exists(arquivo) or arquivo.lower().endswith(assistente.EXTENSOES_DE_IMAGEM)):
            continue
        return {"id": id_video, "arquivo": os.path.abspath(arquivo), "link": link, "nome": nome_da_legenda(legenda),
                "de_video": eh_video(asyncio.run(link_para_converter(link)))}
    return None


def preparar_rascunho(d, config, agora=None):
    """
    Um rascunho novo, do vídeo da fonte até Rascunhos, com todas as conferências. O vídeo
    fica reservado (o assistente não o pega) enquanto o robô trabalha nele.

    Antes de tocar no celular, o vídeo cujo produto não tem oferta de afiliado (a API não
    diz o produto: não paga comissão) fica de lado, e o robô passa ao próximo na mesma
    rodada, sem gastar a tentativa do horário. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    evitar = estado_do_dia(config, agora).get("evitar", [])
    for _ in range(VIDEOS_SEM_OFERTA_POR_RODADA):
        video = proximo_video(config, evitar)
        if not video:
            resultado = "nenhum vídeo da fonte com arquivo e link de produto para um rascunho"
            registrar_tentativa("rascunho", "sem vídeo", resultado, agora=agora)
            return resultado
        # No link de vídeo, os produtos vêm do Ver Produtos, no celular.
        if video["de_video"] or ps.nome_do_produto(video):
            break
        atualizar(criar(video["id"], agora), estado="pulado", motivo=SEM_OFERTA)
        registrar_tentativa("rascunho", "pulado", SEM_OFERTA, agora=agora)
    else:
        resultado = f"os próximos {VIDEOS_SEM_OFERTA_POR_RODADA} vídeos da fonte são de produtos sem oferta de afiliado"
        registrar_tentativa("rascunho", "sem vídeo", resultado, agora=agora)
        return resultado
    ident = criar(video["id"], agora)
    assistente.registrar(video["id"], "robo", "rascunho do robô", agora)
    try:
        _preparar(d, ident, video, config.get("fonte", assistente.FONTE_PADRAO), agora)
    except Suspensa as e:
        _desfazer_reserva(ident, video["id"], "conta suspensa", False)
        registrar_tentativa("rascunho", "suspensa", str(e), _produto_do_video(video), agora)
        raise
    except Verificacao:
        _desfazer_reserva(ident, video["id"], "verificação", False)
        registrar_tentativa("rascunho", "verificação", "verificação da Shopee na tela", _produto_do_video(video), agora)
        raise
    except Parada as e:
        _desfazer_reserva(ident, video["id"], e.motivo, e.do_video)
        registrar_tentativa("rascunho", "pulado" if e.do_video else "parou", e.motivo, _produto_do_video(video), agora)
        e.id_video = video["id"]
        raise
    except Exception as e:
        _desfazer_reserva(ident, video["id"], type(e).__name__, False)
        registrar_tentativa("rascunho", "erro", f"erro inesperado ({type(e).__name__})", _produto_do_video(video), agora)
        e.id_video = video["id"]
        raise
    registrar_tentativa("rascunho", "salvo", produto=", ".join((pegar(ident) or {}).get("produtos") or [])
                        or _produto_do_video(video), agora=agora)
    return "rascunho salvo"


def _desfazer_reserva(ident, id_video, motivo, do_video):
    """Vídeo com problema próprio fica marcado e não volta; nos outros casos, volta para a fila."""
    if do_video:
        atualizar(ident, estado="pulado", motivo=motivo)
    else:
        apagar_registro(ident)
    with db.conexao() as con:
        assistente._criar_tabela(con)
        con.execute("DELETE FROM shopee_video_enviados WHERE id_unico = ? AND status = 'robo'", (id_video,))


def _conferir(resultado, do_video=True):
    ok, motivo = resultado
    if not ok:
        raise Parada(motivo, do_video=do_video)


def _preparar(d, ident, video, fonte, agora=None):
    vistos = []
    if video.get("de_video"):
        avisar("🤖 Robô da Shopee Vídeo: começando um rascunho.\n\nProdutos: os do Ver Produtos do vídeo; a IA "
               f"confere cada um.\nVídeo: o mais novo de {assistente.FONTES.get(fonte, fonte)} ainda não usado.")
        nomes = _produtos_do_video(d, video, vistos)
    else:
        nome = ps.nome_do_produto(video)
        if not nome:
            raise Parada("o link não diz o produto do vídeo", do_video=True)
        # Antes de tocar no celular, o Rafael sabe qual vídeo e qual produto o robô pegou.
        avisar(f"🤖 Robô da Shopee Vídeo: começando um rascunho.\n\nProduto: {nome}\n"
               f"Vídeo: o mais novo de {assistente.FONTES.get(fonte, fonte)} ainda não usado.")
        _conferir(ps.ia_confere_produto(video, vistos))
        nomes = [nome]
    # A origem e o que a IA viu ficam no rascunho, para o Rafael validar com isso na mão.
    atualizar(ident, fonte=fonte, conferencia=json.dumps(vistos, ensure_ascii=False))
    textos = asyncio.run(assistente.textos_do_video(video["arquivo"], video.get("nome") or ""))
    if not textos or not textos["titulo"]:
        raise Parada("a IA não devolveu o título")
    if textos["violacao"]:
        avisar(f"⚠️ Robô da Shopee Vídeo: pulei o vídeo. A IA viu possível violação das diretrizes: "
               f"{textos['motivo'] or 'sem motivo'}")
        raise Parada("a IA viu violação das diretrizes", do_video=True)

    os.makedirs(PASTA_RASCUNHOS, exist_ok=True)
    copia = os.path.join(PASTA_RASCUNHOS, f"{ident}.mp4")
    shutil.copyfile(video["arquivo"], copia)
    atualizar(ident, arquivo=copia, link=video["link"], produtos=nomes, titulo=textos["titulo"],
              comentario=textos.get("comentario") or "")

    if not video.get("de_video"):
        # Curtir o produto pela página dele, como o Rafael faz antes de postar (os do Ver
        # Produtos já foram curtidos lá).
        ir_ao_inicio(d)
        ps.abrir_link(d, video["link"])
        pausa(12)
        tela(d)
        _conferir(ps.curtir(d, video))
        pausa(3)
    ir_ao_perfil(d)

    # O vídeo na galeria com um nome só dele: o mais novo da galeria é o que vai no rascunho.
    if not ps.por_na_galeria(d, copia, nome_na_galeria(ident)):
        raise Parada("o vídeo não apareceu na galeria do celular")
    abrir_galeria(d, agora)
    marcar_so_o_mais_novo(d)
    seguir(d, CAMINHO_EDICAO)

    tocar(d, "@et_caption", 3)
    ps.escrever(d, textos["titulo"])
    pausa(3)
    copiada = ps.legenda_copiada(d)
    na_tela = copiada or ps.legenda_lida(d)
    if not mesma_legenda(na_tela, textos["titulo"]):
        # Por onde leu, tamanhos e códigos de caractere, nunca o texto: o diagnóstico do
        # servidor, que é público, mostra esta conferência para achar o que não bateu.
        conferencia = (f"{'pela cópia' if copiada else 'sem a cópia, pela acessibilidade'}: "
                       f"{ps.comparar_legenda(na_tela, textos['titulo'])}; {_forma_do_titulo(textos['titulo'])}")
        gravar_estado(ultima_legenda=conferencia, ultima_legenda_em=_momento())
        raise Parada(f"o título não ficou na legenda ({conferencia})")
    tocar(d, "@tv_right", 3)

    for i, nome in enumerate(nomes):
        seguir(d, CAMINHO_PRODUTO if i == 0 else CAMINHO_MAIS_UM_PRODUTO)
        _conferir(ps.adicionar_produto(d, dict(video, produto=nome)))
        tocar(d, "Feito", 6)
    _conferir(ps.conferir_tela_final(d, dict(video, produtos=nomes)))

    print_tela = os.path.join(PASTA_RASCUNHOS, f"{ident}.png")
    d.screenshot(print_tela)
    tocar(d, "@tv_drafts_box", 12)
    if tem(tela(d), "@btn_post"):
        raise Parada("toquei em Rascunhos, mas o app continuou na tela final")
    atualizar(ident, estado="rascunho", print=print_tela)
    esperando = len(esperando_aprovacao())
    avisar(f"📝 Robô da Shopee Vídeo: rascunho novo salvo no celular. {esperando} esperando a sua aprovação "
           "em Shopee Vídeo 🎬 → Rascunhos do Robô 📝.")


def _produtos_do_video(d, video, vistos):
    """
    Link de vídeo (Ver Produtos): abre o vídeo no celular e, na lista do Ver Produtos, cada
    produto que o criador vinculou (nunca as recomendações de "Você Também Pode Gostar"):
    lê o nome na página dele, a IA confere o vídeo com esse nome VEZES_DA_IA vezes, e o
    confirmado é curtido. Devolve os nomes confirmados; nenhum ou vídeo removido: o vídeo
    fica de lado. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    ir_ao_inicio(d)
    ps.abrir_link(d, video["link"])
    pausa(12)
    xml = tela(d)
    if not ps.video_removido(xml) and not tem(xml, "Ver Produtos"):
        pausa(ESPERA_DO_VER_PRODUTOS)
        xml = tela(d)
    if ps.video_removido(xml):
        raise Parada("o vídeo do link foi removido", do_video=True)
    if not tem(xml, "Ver Produtos"):
        raise Parada(_sem_ver_produtos(xml), do_video=True)
    tocar(d, "Ver Produtos", 6)
    quantos = len(ps.produtos_vinculados(tela(d)))
    if not quantos:
        raise Parada("o Ver Produtos não mostrou os produtos do criador", do_video=True)
    confirmados = []
    for i in range(min(quantos, MAXIMO_PRODUTOS_DO_VIDEO)):
        xml = tela(d)
        pontos = ps.produtos_vinculados(xml)
        if i >= len(pontos):
            break
        if ps.proibido_no_ponto(xml, *pontos[i]):
            raise Parada(ps.RECUSA)
        d.click(*pontos[i])
        pausa(8)
        xml = tela(d)
        nome = ps.nome_na_pagina_do_produto(xml)
        if nome and nome not in confirmados:
            deste = []
            ok, _ = ps.ia_confere_produto(dict(video, produto=nome), deste, avisar=False)
            if ok:
                _conferir(ps.curtir_na_pagina(d, xml))
                confirmados.append(nome)
                vistos.extend(deste)
        d.press("back")
        pausa(4)
    if not confirmados:
        raise Parada("a IA não confirmou nenhum produto do Ver Produtos", do_video=True)
    return confirmados


def _sem_ver_produtos(xml):
    """
    Por que o vídeo não mostrou o Ver Produtos, em texto fixo, que o investigar_robo.yml
    mostra: o link não abriu o player, o player tem o cartão de um produto (com o botão
    de comprar) sem o Ver Produtos, ou nem isso.
    """
    lista = ps.elementos(xml)
    if not any(el["id"] == PLAYER_DO_VIDEO for el in lista):
        return "o link de vídeo não abriu o vídeo no app (sem o Ver Produtos)"
    if any(ps.texto_proibido(el["texto"]) for el in lista):
        return "o vídeo mostrou o cartão de um produto, sem o Ver Produtos"
    return "o link de vídeo não mostrou o Ver Produtos"


def nome_na_galeria(ident):
    return f"robo_shopee_video_{ident}.mp4"


ARQUIVO_NO_SERVIDOR = re.compile(r"^(\d+)\.(?:mp4|png)$")


# --- Os rascunhos no app ---

def abrir_lista_de_rascunhos(d):
    """
    Perfil em Shopee Vídeo → o quadro "Rascunhos: N" (o 1º da grade; só aparece com
    algum rascunho salvo) → a lista, com Selecionar no alto.
    """
    ir_ao_perfil(d)
    if not tem(tela(d), "Rascunhos:"):
        raise Parada("o Perfil não tem nenhum rascunho salvo")
    tocar(d, "Rascunhos:", 6)
    if not tem(tela(d), "Selecionar"):
        raise Parada("a lista de rascunhos não abriu")


def quadros_da_lista(xml):
    """
    Os rascunhos da lista, na ordem da tela (linha a linha, da esquerda para a direita):
    os blocos de toque grandes abaixo do alto da tela.
    """
    quadros = [el for el in ps.elementos(xml)
               if el["clicavel"] and el["caixa"][1] > 250
               and el["caixa"][2] - el["caixa"][0] >= 200 and el["caixa"][3] - el["caixa"][1] >= 250]
    return sorted(quadros, key=lambda el: (el["caixa"][1], el["caixa"][0]))


def posicao_no_app(rascunho):
    """
    Onde o rascunho fica na lista do app: a lista vem do mais novo para o mais velho, e
    os rascunhos do robô são os mais novos (o antigo só com o vídeo é o último).
    """
    no_app = sorted(listar(*NO_APP), key=lambda r: (r["criado_em"], r["id"]), reverse=True)
    return next(i for i, r in enumerate(no_app) if r["id"] == rascunho["id"])


def _forma_do_titulo(titulo):
    """O tamanho do título como o app conta (cada emoji de fora do plano básico vale 2) e quantos emojis desses."""
    return (f"o título tem {len(titulo.encode('utf-16-le')) // 2} no contador do app e "
            f"{sum(ord(c) > 0xFFFF for c in titulo)} emoji(s) de fora do plano básico")


def abrir_rascunho(d, rascunho):
    """
    Abre o rascunho e chega à tela final; confere que a legenda é o título dele e que o
    produto anexado é o do vídeo. Não bateu: para sem tocar em nada mais.
    """
    abrir_lista_de_rascunhos(d)
    quadros = quadros_da_lista(tela(d))
    posicao = posicao_no_app(rascunho)
    if posicao >= len(quadros):
        raise Parada(f"a lista de rascunhos tem {len(quadros)}; o rascunho seria o {posicao + 1}º")
    d.click(*ps._centro(quadros[posicao]))
    pausa(10)
    seguir(d, [("@tv_compress", 10, "@et_caption")])
    tela(d)
    # Aqui só a leitura pela acessibilidade, sem a cópia: o Ctrl+A na tela final abre a
    # edição do texto e tira o Postar da tela (Motorola, 23/10/2026). Essa leitura traz
    # ".." no lugar de cada emoji de fora do plano básico; o texto com os emojis já foi
    # conferido pela cópia do campo quando o rascunho foi preparado.
    lida = ps.legenda_lida(d)
    if not (mesma_legenda(lida, rascunho["titulo"])
            or mesma_legenda(lida, ps.como_o_android_le(rascunho["titulo"]))):
        raise Parada("o rascunho aberto não tem o título do aprovado")
    _conferir(ps.conferir_tela_final(d, video_do_rascunho(rascunho)), do_video=False)


def publicar(d, rascunho, agora=None):
    """
    Posta o rascunho aprovado e manda no privado o link do post e o comentário. Antes,
    olha nas Notificações se a conta está suspensa: não se sabe o que o Postar faz com a
    conta suspensa, e o robô não marca como postado o que não foi ao ar.
    """
    ate = ler_suspensao(d, agora)
    if ate:
        raise Suspensa(ate)
    abrir_rascunho(d, rascunho)
    _conferir(ps.postar(d, video_do_rascunho(rascunho)), do_video=False)
    pausa(15)
    atualizar(rascunho["id"], estado="postado", postado_em=_momento(agora))
    link = link_do_post(d)
    if link:
        atualizar(rascunho["id"], link_post=link)
    avisar("✅ Robô da Shopee Vídeo: postei o vídeo que você aprovou.\n\n"
           + (f"🔗 {link}" if link else "O link do post está no seu Perfil em Shopee Vídeo."))
    if rascunho["comentario"]:
        avisar(ps.AVISO_COMENTARIO)
        avisar(rascunho["comentario"])
    return "rascunho aprovado postado"


def botao_de_compartilhar(xml):
    """
    No player do vídeo (o que tem "Adicionar um comentário"), o ícone de compartilhar
    fica na coluna da direita, sem texto: a descrição é "... video share icon". O Perfil
    tem outro compartilhar, o do perfil, que não serve. None se não achou.
    """
    if not tem(xml, "Adicionar um comentário"):
        return None
    for el in ps.elementos(xml):
        descricao = el["descricao"].casefold()
        if el["clicavel"] and "video" in descricao and "share" in descricao:
            return ps._centro(el)
    return None


def link_do_post(d):
    """
    O link do post que acabou de sair: Perfil em Shopee Vídeo → o vídeo mais novo → o
    ícone de compartilhar → Copiar link (mapeado no Motorola em 22/10/2026). Qualquer
    passo que não aparece: sem link (o post saiu do mesmo jeito, e a mensagem diz onde
    achar). Nada aqui desfaz a postagem: até a Verificação só abre a tela do celular no
    privado.
    """
    try:
        ir_ao_perfil(d)
        # Na grade do Perfil vêm primeiro o quadro "Rascunhos: N" e os vídeos fixados; o
        # mais novo é o primeiro depois deles.
        quadros = [q for q in quadros_da_lista(tela(d))
                   if not any(tem_texto_no_quadro(d, q, texto) for texto in ("Rascunhos", "Fixado"))]
        if not quadros:
            return ""
        d.click(*ps._centro(quadros[0]))
        pausa(8)
        compartilhar = botao_de_compartilhar(tela(d))
        if not compartilhar:
            return ""
        d.click(*compartilhar)
        pausa(4)
        if not tem(tela(d), "Copiar link"):
            return ""
        tocar(d, "Copiar link", 3)
        return ps.link_copiado(d)
    except Verificacao:
        av.abrir_tela(celular=True, verificacao=True)
        return ""
    except Parada:
        return ""
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Link do post não saiu: {type(e).__name__}")
        return ""


def tem_texto_no_quadro(d, quadro, texto):
    return any(ps._dentro(ps._centro(el), quadro["caixa"]) and texto.casefold() in el["texto"].casefold()
               for el in ps.elementos(d.dump_hierarchy()))


def apagar_do_app(d, rascunho):
    """
    Apaga do app o rascunho que o Rafael recusou. Confere antes, abrindo-o, que é o
    rascunho recusado; volta para a lista (o rascunho continua salvo) → Selecionar → o
    rascunho → "Excluir (1)" → a janela "Excluir vídeos selecionados?" → Confirmar.
    Com outro número no Excluir, para sem apagar nada.
    """
    abrir_rascunho(d, rascunho)
    voltar(d, "Selecionar")
    quadros = quadros_da_lista(tela(d))
    posicao = posicao_no_app(rascunho)
    tocar(d, "Selecionar", 3)
    d.click(*ps._centro(quadros[posicao]))
    pausa(2)
    if not tem(tela(d), "Excluir (1)"):
        raise Parada("a lista não marcou só o rascunho recusado para excluir")
    tocar(d, "Excluir (1)", 3)
    if not tem(tela(d), "Excluir vídeos selecionados?"):
        raise Parada("a confirmação de excluir não apareceu")
    tocar(d, "Confirmar", 6)
    atualizar(rascunho["id"], estado="apagado")
    return "rascunho recusado apagado"


def faxina_dos_arquivos(d):
    """
    O vídeo e o print de cada rascunho são a memória só deste robô, para aquele rascunho:
    ficam no servidor e na galeria do celular enquanto ele espera a aprovação ou a vez de
    ir ao ar, e saem depois de usados (postado, apagado do app, ou o preparo que parou no
    meio). Do rascunho fica só a linha no banco, que impede o mesmo vídeo de voltar. Roda
    no fim de cada rodada que mexeu no celular, ainda dentro da trava: nenhum rascunho
    está sendo preparado ao mesmo tempo. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    guardar = {rascunho["id"] for rascunho in listar(*NO_APP)}
    usados = {}
    for nome in os.listdir(PASTA_RASCUNHOS) if os.path.isdir(PASTA_RASCUNHOS) else []:
        achado = ARQUIVO_NO_SERVIDOR.match(nome)
        if achado and int(achado.group(1)) not in guardar:
            usados.setdefault(int(achado.group(1)), []).append(os.path.join(PASTA_RASCUNHOS, nome))
    for ident, arquivos in sorted(usados.items()):
        # A cópia do servidor sai só depois da galeria: é ela que lembra o que falta tirar
        # do celular, se ele cair no meio.
        try:
            caminho = f"{ps.GALERIA}/{nome_na_galeria(ident)}"
            d.shell(["rm", "-f", caminho])
            d.shell(["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                     "-d", "file://" + caminho])
            for arquivo in arquivos:
                os.remove(arquivo)
        except Exception as e:
            logger.warning(f"⚠️ [Robô Shopee Vídeo] Vídeo usado não saiu do celular ou do servidor: "
                           f"{type(e).__name__}")
            return


# --- Treino ---

def treinar(d, agora=None):
    """
    Percorre o caminho todo até a tela final sem salvar nem postar, conferindo cada tela
    com o mapa (os CAMINHOs): se a Shopee mudou o app, o Rafael fica sabendo antes de uma
    rodada de verdade travar no meio. Abre também a página completa de um produto já
    usado, sem curtir. Avisa no privado: caminho OK, ou a tela que mudou, com o print.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    # O resultado do treino anterior sai: enquanto este roda, o painel mostra "rodando".
    gravar_estado(treino_semana=semana(agora), treino_em=_momento(agora), treino_resultado="")
    try:
        ultimo = (listar(*NO_APP, "postado", "apagado") or [None])[-1]
        if ultimo:
            ir_ao_inicio(d)
            ps.abrir_link(d, ultimo["link"])
            pausa(12)
            ok, motivo, _ = ps.abrir_pagina_completa(d, video_do_rascunho(ultimo))
            if not ok:
                raise Parada(f"página do produto: {motivo}")
        # O quadro "Rascunhos: N" só aparece com algum rascunho salvo: o treino não o exige.
        ir_ao_perfil(d)
        abrir_galeria(d, agora)
        marcar_so_o_mais_novo(d)
        seguir(d, CAMINHO_EDICAO)
        xml = tela(d)
        faltam = [alvo for alvo in ("@et_caption", "@ll_add_product_symbol", "@tv_drafts_box", "@btn_post")
                  if not tem(xml, alvo)]
        if faltam:
            raise Parada(f"a tela final não tem {', '.join(faltam)}")
        seguir(d, CAMINHO_PRODUTO)
    except Suspensa as e:
        gravar_estado(treino_resultado=str(e))
        _sair_sem_salvar(d)
        raise
    except Parada as e:
        gravar_estado(treino_resultado=f"mudou: {e.motivo}")
        _print_do_treino(d, f"⚠️ Treino do robô da Shopee Vídeo: algo mudou no app ({e.motivo}). "
                            "Parei sem salvar nem postar; o Claude remapeia o caminho.")
        _sair_sem_salvar(d)
        return f"treino: mudou ({e.motivo})"
    _sair_sem_salvar(d)
    gravar_estado(treino_resultado="ok")
    avisar("🧭 Treino do robô da Shopee Vídeo: caminho OK. Todas as telas estão como o robô conhece, "
           "do link do produto até a tela final (sem salvar nem postar).")
    return "treino: caminho OK"


def _print_do_treino(d, legenda):
    caminho = os.path.join(PASTA_RASCUNHOS, "treino.png")
    try:
        os.makedirs(PASTA_RASCUNHOS, exist_ok=True)
        d.screenshot(caminho)
        if not avisar_foto(caminho, legenda):
            avisar(legenda)
    finally:
        if os.path.exists(caminho):
            os.remove(caminho)


def _sair_sem_salvar(d):
    try:
        ir_ao_inicio(d)
    except (Parada, Verificacao):
        pass


# --- A rodada ---

def pausar_por_desconexao(motivo):
    """
    Sem o celular, a Postagem pausa sozinha (o botão vira Retomar Postagem ▶️) e o modo
    assistente volta a mandar as postagens no privado, para o Rafael postar à mão.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    db.atualizar_config(CHAVE_CONFIG, lambda dados: dados.update(robo_pausado=True,
                                                                robo_pausa_motivo="celular desconectado"))
    logger.warning(f"⚠️ [Robô Shopee Vídeo] Celular desconectado ({motivo}): Postagem pausada.")
    avisar(f"📱 Robô da Shopee Vídeo: perdi a conexão com o celular guardado ({motivo}). Pausei a Postagem, "
           "e o modo assistente volta a mandar as postagens aqui no privado para você postar à mão.\n\n"
           "Para voltar ao automático: no Motorola, ligue a Depuração por Wi-Fi (Opções do desenvolvedor) e, "
           "no bot, toque em Shopee Vídeo 🎬 → Retomar Postagem ▶️. Eu acho o celular sozinho.")


def rodada(treino=False, preparar=False, d=None, agora=None, saude=False):
    """
    Uma rodada. treino=True é o botão Testar Caminho 🧭, preparar=True o Preparar 1
    Agora ⚡ e saude=True o Gerar Apelação ⚖️ (Relatório Geral 📊 → Saúde da Shopee
    Vídeo 🩺): rodam na hora, mesmo pausado ou fora do horário (o Rafael pediu agora), e o
    rascunho do Preparar 1 Agora é a mais do plano do dia. Com a conta suspensa, a única
    coisa que o robô faz no celular é ler a Saúde do Vídeo (uma vez por dia, ou pelo
    botão). Devolve o que aconteceu, numa frase. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    config = ler_config()
    na_hora = treino or preparar or saude
    if not na_hora:
        if config["robo_pausado"]:
            consumir_horarios(config, agora)
            return "pausado"
        if suspensa(config, agora):
            # Os horários que passam na suspensão são pulados, como pausado.
            consumir_horarios(config, agora)
            if not (no_horario(config, agora) and saude_do_dia_pendente(agora)):
                return f"conta suspensa até {quando_acaba(suspenso_ate(config))}"
            # A leitura do dia conta já aqui: com o celular fora, não tenta de novo a cada rodada.
            gravar_estado(saude_tentada_em=_momento(agora))
            saude = True
        elif not no_horario(config, agora):
            return "fora do Horário do Robô"
    elif suspensa(config, agora) and not saude:
        ate = quando_acaba(suspenso_ate(config))
        avisar(f"⛔ Robô da Shopee Vídeo: não {'preparei o rascunho' if preparar else 'testei o caminho'}. A conta "
               f"de Shopee Vídeo está suspensa pela Shopee até {ate}, e o robô não toca no celular até lá.")
        return f"conta suspensa até {ate}"
    if d is None:
        if av.tela_aberta():
            return _resposta(preparar, "a tela do celular está aberta no privado do Rafael")
        if not celular_robo.conectado():
            ok, motivo = celular_robo.reconectar_sozinho()
            if not ok and not na_hora and suspensa(config, agora):
                # Na suspensão o Rafael pode tirar o Motorola do carregador: o celular fora é
                # esperado, e o robô não pausa nem avisa. No fim dela, sem o celular, pausa e
                # avisa como sempre. Pedido do Rafael: DECISOES.md, Shopee Vídeo.
                return f"conta suspensa até {quando_acaba(suspenso_ate(config))}; celular fora (esperado)"
            if not ok:
                if not na_hora:
                    pausar_por_desconexao(motivo)
                registrar_tentativa("rodada", "parou", f"celular desconectado ({motivo})", agora=agora)
                return _resposta(preparar, f"celular desconectado ({motivo})")
    with celular_robo.trava() as livre:
        if not livre:
            return _resposta(preparar, "o explorar está tocando no celular")
        if treino:
            acao, ident = "treino", None
        elif preparar:
            acao, ident = "rascunho", None
        elif saude:
            acao, ident = "saude", None
        else:
            acao, ident = o_que_fazer(config, agora) or (None, None)
        if not acao:
            return "nada a fazer agora"
        d = d or ps.conectar(celular=True)
        try:
            resultado = _agir(d, acao, ident, preparar, config, agora, pedido=saude and na_hora)
            if acao != "saude" and saude_pedida_pela_notificacao(agora):
                _ler_saude_junto(d, agora)
            return resultado
        finally:
            faxina_dos_arquivos(d)


def _agir(d, acao, ident, preparar, config, agora, pedido=False):
    """
    A ação da rodada no celular, já dentro da trava, com o que fazer quando ela para.
    pedido=True: o Rafael pediu a Saúde do Vídeo pelo botão Gerar Apelação ⚖️ e espera a resposta.
    """
    # O rascunho entra no histórico pelo preparar_rascunho, que sabe qual vídeo tentou.
    produto = ", ".join((pegar(ident) or {}).get("produtos") or []) if ident else ""
    try:
        if acao == "treino":
            resultado = treinar(d, agora)
            registrar_tentativa("treino", "treino ok" if "OK" in resultado else "treino parou",
                                "" if "OK" in resultado else resultado, agora=agora)
            return resultado
        if acao == "saude":
            novas, total, pontos = ler_saude(d, agora)
            resultado = f"saúde lida: {total} punição(ões) em 30 dias, {novas} nova(s)"
            registrar_tentativa("saude", "saúde lida", agora=agora)
            if pedido:
                avisar(f"🩺 Robô da Shopee Vídeo: li a Saúde do Vídeo. Pontos de penalidade: "
                       f"{'?' if pontos is None else pontos}. Punições nos últimos 30 dias: {total}; "
                       f"{novas} nova(s) para recorrer" + (" (o texto de cada uma chega aqui em seguida)." if novas
                                                             else ".")
                       + "\n\nTudo em Relatório Geral 📊 → Saúde da Shopee Vídeo 🩺.")
            return resultado
        if acao == "apagar":
            resultado = apagar_do_app(d, pegar(ident))
            registrar_tentativa("apagar", "apagado", produto=produto, agora=agora)
            return resultado
        if acao == "postar":
            resultado = publicar(d, pegar(ident), agora)
            registrar_tentativa("postar", "postado", produto=produto, agora=agora)
            return resultado
        resultado = preparar_rascunho(d, config, agora)
        if resultado == "rascunho salvo":
            return resultado
        _repetir_depois(acao, preparar, config, agora)
        _avisar_que_nao_saiu(acao, preparar, config, agora)
        return _resposta(preparar, resultado)
    except Suspensa as e:
        resultado = _suspender(e, acao, preparar, produto, agora)
        # A punição que levou à suspensão ganha o texto do recurso na mesma rodada.
        _ler_saude_junto(d, agora)
        return resultado
    except Verificacao:
        logger.warning("⚠️ [Robô Shopee Vídeo] Verificação da Shopee na tela: parado.")
        if acao != "rascunho":
            registrar_tentativa(acao, "verificação", "verificação da Shopee na tela", produto, agora)
        av.abrir_tela(celular=True, verificacao=True)
        return f"{acao}: verificação na tela; parado"
    except Parada as e:
        if acao in ("postar", "apagar"):
            # Não insiste: o Rafael decide de novo pelo botão.
            atualizar(ident, estado="rascunho", postar_em=None, motivo=e.motivo)
            avisar(f"⚠️ Robô da Shopee Vídeo: não consegui {'postar' if acao == 'postar' else 'apagar'} "
                   f"o rascunho ({e.motivo}). Não toquei em mais nada; ele voltou para Rascunhos do Robô 📝.")
        if acao != "rascunho":
            registrar_tentativa(acao, "parou", e.motivo, produto, agora)
        if acao == "saude" and pedido:
            avisar(f"⚠️ Robô da Shopee Vídeo: não consegui ler a Saúde do Vídeo ({e.motivo}). Toque de novo em "
                   "Gerar Apelação ⚖️ daqui a pouco.")
        _repetir_depois(acao, preparar, config, agora, getattr(e, "id_video", None), e.do_video)
        _avisar_que_nao_saiu(acao, preparar, config, agora)
        return _resposta(preparar, f"{acao}: parado ({e.motivo})")
    except Exception as e:
        # Erro que ninguém previu: a rodada termina com o tipo dele, e o celular fica
        # para a próxima rodada voltar ao início.
        logger.exception(f"❌ [Robô Shopee Vídeo] Erro na rodada ({acao}): {type(e).__name__}")
        if acao != "rascunho":
            registrar_tentativa(acao, "erro", f"erro inesperado ({type(e).__name__})", produto, agora)
        _repetir_depois(acao, preparar, config, agora, getattr(e, "id_video", None))
        _avisar_que_nao_saiu(acao, preparar, config, agora)
        return _resposta(preparar, f"{acao}: erro {type(e).__name__}")


def _suspender(e, acao, preparar, produto="", agora=None):
    """
    A conta está suspensa: guarda até quando e avisa o Rafael uma vez. O aprovado continua
    aprovado e sai depois da suspensão (fim_da_suspensao); o rascunho do plano não gasta
    tentativa nem manda o aviso de que não saiu. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    ate = quando_acaba(e.ate)
    logger.warning(f"⛔ [Robô Shopee Vídeo] Conta suspensa pela Shopee até {ate}: robô e assistente em espera.")
    if acao != "rascunho":
        registrar_tentativa(acao, "suspensa", str(e), produto, agora)
    if guardar_suspensao(e.ate):
        avisar_suspensao(e.ate)
    elif preparar:
        _resposta(preparar, str(e))
    return str(e)


def avisar_suspensao(ate):
    """O aviso, uma vez por suspensão, de que robô e assistente esperam até o fim dela."""
    avisar(f"⛔ Robô da Shopee Vídeo: a Shopee suspendeu a sua conta de Shopee Vídeo até {quando_acaba(ate)} (o aviso "
           "está nas Notificações e na Saúde do Vídeo do app da Shopee).\n\n"
           "Pausei o robô e o modo assistente até lá: nada de preparar nem postar, e sem avisos de rascunho "
           "que não saiu. Os rascunhos aprovados ficam guardados e saem depois, espalhados.\n\n"
           "Quando a suspensão acabar, os dois voltam sozinhos e eu aviso aqui. Se quiser que o robô continue "
           "pausado depois, toque em Shopee Vídeo 🎬 → Robô Automático 🤖 → Pausar Postagem ⏸️.")


def _ler_saude_junto(d, agora=None):
    """A Saúde do Vídeo lida no fim de outra ação (suspensão achada, aviso de penalidade): erro não derruba a rodada."""
    try:
        ler_saude(d, agora)
    except (Parada, Verificacao) as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Não li a Saúde do Vídeo: {ps.mascarar(getattr(e, 'motivo', ''))}")
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Erro ao ler a Saúde do Vídeo: {type(e).__name__}")


def _avisar_que_nao_saiu(acao, preparar, config, agora=None):
    """
    O rascunho do plano que não saiu ganha um aviso no privado, com o passo e a próxima
    tentativa. O Preparar 1 Agora já responde pelo _resposta. Decisão do Rafael:
    DECISOES.md, Shopee Vídeo.
    """
    if acao == "rascunho" and not preparar:
        avisar(aviso_rascunho_nao_saiu(config, agora))


def _repetir_depois(acao, preparar, config, agora=None, video=None, do_video=False):
    """
    Rascunho do plano que não deu certo volta na rodada seguinte (marcar_para_repetir: 3
    tentativas por vídeo, até VIDEOS_POR_HORARIO vídeos). O Preparar 1 Agora não volta: o
    Rafael vê o motivo e toca de novo. A Verificação da Shopee não passa por aqui: ela para
    tudo. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if acao == "rascunho" and not preparar:
        marcar_para_repetir(config, agora, video, do_video)


def _resposta(preparar, resultado):
    """No Preparar 1 Agora o Rafael espera a resposta: o que impediu o rascunho vai também no privado."""
    if preparar:
        avisar(f"⚠️ Robô da Shopee Vídeo: não preparei o rascunho que você pediu ({resultado}).")
    return resultado


def main(argumentos):
    logging.basicConfig(level=os.getenv("NIVEL_LOG", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    treino, preparar, saude = "--treino" in argumentos, "--preparar" in argumentos, "--saude" in argumentos
    if not treino and not preparar and not saude and "--rodada" not in argumentos:
        print(__doc__)
        return 2
    resultado = rodada(treino=treino, preparar=preparar, saude=saude)
    logger.info(f"🤖 [Robô Shopee Vídeo] {resultado}.")
    # O resultado fica no banco com o texto mascarado (sem nome de produto), para o
    # diagnóstico do servidor, que é público, mostrar como foi a última rodada.
    gravar_estado(ultima_rodada=ps.mascarar(resultado), ultima_rodada_em=_momento())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

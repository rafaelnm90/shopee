#!/usr/bin/env python3
"""
Robô automático da Shopee Vídeo: no celular guardado do Rafael (celular_robo.py), prepara
rascunhos sozinho e posta os que o Rafael aprova no bot (Shopee Vídeo 🎬 → Rascunhos do
Robô 📝, no painel_shopee_video.py). Usa os passos e as conferências do explorar
(postador_shopee_video.py): a IA confere o produto do link com o vídeo, o produto é achado
no topo de Minhas Curtidas (pelo nome parecido ou, por último, pela foto conferida pela IA)
e a tela final é conferida antes de salvar e de postar. No fim de cada rascunho, salvo ou
não, descurte os produtos que curtiu para ele.

O painel (bot_mestre) chama uma rodada a cada 15 min, num processo à parte: o robô passa
minutos tocando no celular, e a IA dele não pode dividir a conexão com a do bot.

    python3 robo_shopee_video.py --rodada
    python3 robo_shopee_video.py --treino      # o treino na hora (botão Testar Caminho 🧭)
    python3 robo_shopee_video.py --preparar    # um rascunho na hora (botão Preparar 1 Agora ⚡)
    python3 robo_shopee_video.py --saude       # a Saúde do Vídeo na hora (botão Gerar Apelação ⚖️)

Cada rodada faz no máximo uma coisa, nesta ordem (às 4h, só a primeira):
0. às 4h, descurte tudo em Meus favoritos (Criadores & Afiliados), uma vez por dia (P25);
1. o treino da semana, na primeira rodada de segunda-feira: percorre o caminho até a tela
   final sem salvar nem postar e confere cada tela com o mapa (os CAMINHOs abaixo);
2. apaga no app um rascunho que o Rafael recusou;
3. posta um rascunho aprovado cuja hora chegou: os aprovados saem um de cada vez, com um
   intervalo sorteado entre eles, sempre dentro do Horário do Robô;
4. prepara um rascunho novo quando um horário do plano do dia passou: cada dia sorteia
   quantos (a faixa Rascunhos por Dia) e espalha os horários pelo Horário do Robô;
5. responde os comentários novos dos vídeos do Rafael, uma vez por dia (Notificações →
   Lives, Vídeos e ...; o texto é da IA e cada resposta é conferida embaixo do comentário);
6. curte e comenta um vídeo de outro criador no feed Live e Vídeo → Para você, até 3 por
   dia, espalhados (interacoes_shopee_video.py).
Pausado (Pausar Postagem ⏸️), fora do Horário do Robô, com a tela do celular aberta no
privado do Rafael ou com o explorar tocando nele, não toca em nada. Celular desconectado:
tenta reconectar sozinho (celular_robo.reconectar_sozinho); sem conseguir, pausa a
Postagem e avisa, e o modo assistente volta a mandar as postagens no privado até o
Rafael tocar em Retomar Postagem ▶️. Na Verificação da Shopee para na hora e manda o
link da tela do celular no privado. Com a conta de Shopee Vídeo suspensa pela Shopee (o
aviso fica nas Notificações do app), não prepara, não posta e não treina até o fim da
suspensão (o Postar vídeo fica fechado), e o modo assistente espera junto; o resto segue
no horário de sempre, e com o celular fora da tomada só pula. No fim, os dois voltam
sozinhos (painel_shopee_video).

Nunca toca em Postar sem o Aprovar do Rafael no bot, nem nos botões de comprar. Curtir e
comentar o próprio vídeo continuam à mão: depois de postar, o comentário chega no
privado, numa mensagem só dele. No log, só estados e números: nada de nome de
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
import api_shopee
import assistente_shopee_video as assistente
import avisar_rafael
import casos_robo
import celular_robo
import db
import edicao_video
import interacoes_shopee_video as interacoes
import postador_shopee_video as ps
import registro_processos
from api_shopee import eh_video, link_para_converter
from fuso import fuso_horario
from legendas import nome_da_legenda
from motor_filas import sortear_teto_do_dia

logger = logging.getLogger("RoboShopeeVideo")

CHAVE_CONFIG = "shopee_video"  # a mesma chave do painel_shopee_video
# Começa pausado: o Rafael retoma no painel. Rascunhos por dia em faixa (sorteada a cada
# dia), o Horário do Robô e o Horário das Interações (None até o Rafael escolher), em
# horas de Brasília.
PADRAO = {"robo_pausado": True, "robo_limite_min": 1, "robo_limite_max": 2,
          "robo_inicio": ps.HORARIO_DAS_RODADAS[0], "robo_fim": ps.HORARIO_DAS_RODADAS[1],
          "robo_interacoes_inicio": None, "robo_interacoes_fim": None}
MAXIMO_POR_DIA = 20
CHAVE_DIA = "shopee_video_robo_dia"
# Rascunho do plano que não deu certo volta nas rodadas seguintes: até estas vezes a mais
# com o mesmo vídeo e, se não der, com outro, até VIDEOS_POR_HORARIO vídeos no horário.
# Depois disso o robô espera o próximo horário do plano. Decisão do Rafael: DECISOES.md,
# Shopee Vídeo.
TENTATIVAS_A_MAIS = 2
VIDEOS_POR_HORARIO = 3
# A IA que volta sem o título ganha mais uma chance, depois desta pausa (segundos).
TENTATIVAS_DO_TITULO = 2
# O Google bloqueia pelo conteúdo do vídeo (24/10/2026, PROHIBITED_CONTENT nas duas
# tentativas): esses códigos se repetem para o mesmo vídeo, então ele fica de lado na hora.
BLOQUEIOS_DO_CONTEUDO = ps.api_gemini.BLOQUEIOS_DO_CONTEUDO
ESPERA_DO_TITULO = 45
# Vídeo de produto sem oferta de afiliado (não paga comissão) fica de lado antes de tocar
# no celular; numa rodada, até estes. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
VIDEOS_SEM_OFERTA_POR_RODADA = 5
SEM_OFERTA = "o link não diz o produto do vídeo (produto sem oferta de afiliado)"
# Produtos do Ver Produtos que o robô confere num vídeo (cada um custa 2 conferências da IA).
MAXIMO_PRODUTOS_DO_VIDEO = 6
# O mesmo produto com mais comissão (P33): a busca da API por maior comissão traz até
# estes, entram só os de nome parecido (PARECIDO_NA_BUSCA% das palavras do nome do link),
# e a IA confere com o vídeo até CANDIDATOS_NA_IA deles (cada um custa até 2 conferências).
# A busca usa as primeiras PALAVRAS_DA_BUSCA palavras do nome: o nome inteiro traz pouco.
OFERTAS_NA_BUSCA = 20
PARECIDO_NA_BUSCA = 60
CANDIDATOS_NA_IA = 2
PALAVRAS_DA_BUSCA = 6
# Na foto do Ver Produtos (P39), a oferta achada pelo nome tem de ser quase o mesmo nome do
# produto anexado: a foto vai em tela cheia no começo do vídeo e na miniatura.
PARECIDO_DA_FOTO = 80
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
# O Centro do criador e a Saúde do Vídeo carregam pela rede (React e página web): o robô
# relê a tela até este tanto de segundos antes de dar a leitura por parada.
ESPERA_DA_SAUDE = 24
# O quadro "Rascunhos: N" da grade do Perfil carrega pela rede depois do Postar vídeo: o
# robô relê a tela até este tanto de segundos (24/10/2026, 08:58, a postagem do aprovado
# parou com a grade ainda carregando).
ESPERA_DOS_RASCUNHOS = 18
# O aviso do Android "Shopee não está respondendo" (24/10/2026, 13:17 e 13:38, dois
# rascunhos pararam com ele na frente): quantas vezes o robô toca em Aguardar e os
# segundos que dá ao app depois de cada toque.
VEZES_DO_AGUARDAR = 3
ESPERA_DO_AGUARDAR = 15
# Segundos que a Shopee tem para abrir depois de fechada pelo aviso de app travado.
ESPERA_DEPOIS_DE_REABRIR = 20
# Produto de loja de férias (a página avisa) não entra no Adicionar Produto do vídeo.
MOTIVO_DE_FERIAS = "a loja do produto está de férias: a Shopee não deixa anexar o produto ao vídeo"
# A Saúde é lida de novo pelo aviso de penalidade nas Notificações só depois disto.
INTERVALO_DA_SAUDE = timedelta(hours=6)
# Depois do Já recorri, a Saúde é lida de hora em hora até sair o resultado (escolha do
# Rafael em 24/10, P6).
INTERVALO_DO_RECURSO = timedelta(hours=1)


class Parada(Exception):
    """
    A rodada para aqui. do_video=True quando o problema é do vídeo (a IA não confirmou,
    o produto não foi achado): ele não volta. Sem isso, o vídeo pode ir numa próxima vez.
    caso_guardado=True: quem parou já guardou o caso com a tela da hora (casos_robo).
    """

    def __init__(self, motivo, do_video=False):
        super().__init__(motivo)
        self.motivo, self.do_video, self.caso_guardado = motivo, do_video, False


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
    """O robô pode rodar agora: no Horário do Robô, no Horário das Interações ou na hora do descurtir."""
    return (config["robo_inicio"] <= agora_br(agora).hour < config["robo_fim"]
            or na_hora_das_interacoes(config, agora) or na_hora_do_descurtir(agora))


# Uma hora do dia só para descurtir tudo em Meus favoritos (os produtos curtidos para o
# Adicionar Produto, a lista de afiliado): nela o robô não prepara, não posta e não interage. Fixa às 4h, de
# madrugada. Escolha do Rafael (24/10, P25): DECISOES.md, Shopee Vídeo.
HORA_DO_DESCURTIR = 4
# Com um aprovado indo ao ar nesse tempo (o das rodadas), a rodada não começa tarefa longa:
# a seguinte já pega o post na hora. Escolha do Rafael (P30): DECISOES.md, Shopee Vídeo.
ANTES_DO_POST = timedelta(minutes=15)


def na_hora_do_descurtir(agora=None):
    return agora_br(agora).hour == HORA_DO_DESCURTIR


def descurtir_pendente(agora=None):
    """
    Falta descurtir tudo hoje? Uma vez por dia, e de novo na rodada seguinte (na mesma
    hora) quando a anterior parou depois de VOLTAS_DO_DESCURTIR voltas.
    """
    estado = ler_estado()
    hoje = agora_br(agora).strftime("%Y-%m-%d")
    return bool(estado.get("descurtir_continuar")) or not (estado.get("descurtir_em") or "").startswith(hoje)


# O Horário das Interações (responder os comentários dos vídeos do Rafael e comentar e
# curtir no feed) fica separado do de preparar e postar: nele o robô só interage, e fora
# dele, só prepara e posta. Sem ele escolhido, tudo segue no Horário do Robô, como antes.
# Escolha do Rafael (24/10, P22 a P24): DECISOES.md, Shopee Vídeo.

def janela_das_interacoes(config):
    """(início, fim) do Horário das Interações, em horas; None enquanto o Rafael não escolheu."""
    inicio, fim = config.get("robo_interacoes_inicio"), config.get("robo_interacoes_fim")
    return (int(inicio), int(fim)) if inicio is not None and fim is not None else None


def na_hora_das_interacoes(config, agora=None):
    janela = janela_das_interacoes(config)
    return bool(janela) and janela[0] <= agora_br(agora).hour < janela[1]


def trechos_de_postar(config):
    """
    Os trechos do dia, em minutos (início, fim), em que o robô prepara e posta: o Horário
    do Robô sem o Horário das Interações e sem a hora do descurtir.
    """
    trechos = [(config["robo_inicio"] * 60, min(config["robo_fim"] * 60, 24 * 60 - 1))]
    cortes = [(HORA_DO_DESCURTIR * 60, (HORA_DO_DESCURTIR + 1) * 60)]
    janela = janela_das_interacoes(config)
    if janela:
        cortes.append((janela[0] * 60, janela[1] * 60))
    for corte_inicio, corte_fim in cortes:
        trechos = [parte for a, b in trechos for parte in ((a, min(b, corte_inicio)), (max(a, corte_fim), b))]
    return [(a, b) for a, b in trechos if b > a]


def quantos_hoje(config, dia):
    return sortear_teto_do_dia(CHAVE_ESTADO, dia, config["robo_limite_min"], config["robo_limite_max"])


def planejar(config, dia):
    """
    Horários ("HH:MM") dos rascunhos do dia: o Horário do Robô dividido em partes iguais,
    um minuto sorteado em cada parte, como os envios do modo assistente. Mesmo dia,
    mesma lista. Nunca a mesma quantidade nem os mesmos horários todo dia.
    """
    quantos = quantos_hoje(config, dia)
    trechos = trechos_de_postar(config)
    total = sum(b - a for a, b in trechos)
    if quantos <= 0 or total <= 0:
        return []
    # As partes iguais correm pelos trechos de postar, pulando o Horário das Interações.
    parte = total / quantos
    sorteio = random.Random(f"{CHAVE_ESTADO}:{dia}")
    horarios = []
    for i in range(quantos):
        corrido = int(i * parte + sorteio.uniform(min(5, parte / 3), max(parte - 5, parte * 2 / 3)))
        for a, b in trechos:
            if corrido < b - a:
                minuto = a + corrido
                break
            corrido -= b - a
        else:
            minuto = trechos[-1][1] - 1
        horarios.append(f"{minuto // 60:02d}:{minuto % 60:02d}")
    return sorted(horarios)


def replanejar_hoje(config, agora=None):
    """
    O Horário das Interações mudou: os horários de rascunho que faltam hoje saem do plano
    novo, fora da janela nova; os já feitos continuam contados.
    """
    estado = estado_do_dia(config, agora)
    estado["horarios"] = planejar(config, estado["data"])
    db.salvar_config(CHAVE_DIA, estado)


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


def _em_preparo(config, agora, comecou):
    """
    Marca no plano do dia que o rascunho do horário está sendo preparado. Se a rodada
    morrer no meio (sem chegar ao fim do preparo), a rodada seguinte vê a marca e o horário
    tenta de novo (soltar_preparos_interrompidos).
    """
    estado = estado_do_dia(config, agora)
    estado["em_preparo"] = comecou
    db.salvar_config(CHAVE_DIA, estado)


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
    robô não prepara, não posta e não treina (o_que_fazer), e o assistente fica em espera.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
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
    return _aviso_de_volta(config, remarcar_aprovados(config, agora), "a suspensão da Shopee Vídeo acabou")


def _aviso_de_volta(config, aprovados, motivo):
    """O aviso de que robô e assistente voltam (a pausa do Rafael continua valendo)."""
    fila = f" Os {aprovados} aprovado(s) que esperavam saem espalhados no Horário do Robô." if aprovados else ""
    if not config["robo_pausado"]:
        return (f"✅ Robô da Shopee Vídeo: {motivo}. Voltei a preparar e postar no Horário do Robô, e o modo "
                f"assistente segue em espera.{fila}\n\n"
                "Se você tirou o Motorola do carregador, ponha de volta e confira a Depuração por Wi-Fi: sem o "
                "celular, o robô pausa e avisa aqui, e o modo assistente volta a mandar as postagens.")
    if config.get("pausado", True):
        return (f"✅ Shopee Vídeo: {motivo}. O robô e o modo assistente continuam pausados, como você deixou: "
                "para voltar, toque em Shopee Vídeo 🎬 → Robô Automático 🤖 → Retomar Postagem ▶️.")
    return (f"✅ Shopee Vídeo: {motivo}. O robô continua pausado, como você deixou, e o modo assistente volta a "
            "mandar as postagens aqui no privado.")


def suspensao_retirada(ate):
    """A Shopee já tirou essa suspensão antes do prazo (o aviso dela ainda fica nas Notificações)?"""
    return ate.strftime("%Y-%m-%d %H:%M:%S") in (ler_estado().get("suspensoes_retiradas") or [])


def anotar_retirada(ate):
    texto = ate.strftime("%Y-%m-%d %H:%M:%S")
    db.atualizar_config(CHAVE_ESTADO, lambda dados: dados.update(
        suspensoes_retiradas=sorted(set(dados.get("suspensoes_retiradas") or []) | {texto})[-10:]))


def suspensao_acabou_antes(agora=None):
    """
    A Saúde do Vídeo não mostra mais o bloqueio, mas o robô esperava a suspensão: a
    Shopee a tirou antes do prazo (o recurso deu certo e os pontos baixaram). Tira a
    marca, espalha os aprovados e avisa. Pedido do Rafael: DECISOES.md, Shopee Vídeo.
    """
    config = ler_config()
    ate = suspenso_ate(config)
    if not ate or not suspensa(config, agora):
        return False
    anotar_retirada(ate)
    db.atualizar_config(CHAVE_CONFIG, lambda dados: dados.pop("robo_suspenso_ate", None))
    logger.info("✅ [Robô Shopee Vídeo] A Shopee tirou a suspensão antes do prazo.")
    avisar(_aviso_de_volta(config, remarcar_aprovados(config, agora),
                           "a Shopee tirou a suspensão antes do prazo (a Saúde do Vídeo não mostra mais o bloqueio; "
                           "o recurso deve ter dado certo)"))
    return True


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
           "comentario", "aprovado_em", "postar_em", "postado_em", "link_post", "motivo", "fonte", "conferencia",
           "rotulo_ia")
# Colunas que vieram depois da tabela: entram nas tabelas antigas sem perder nada.
# rotulo_ia: vazio = o rótulo de IA desligado; com texto = ligado, e o texto é o que a IA viu.
COLUNAS_NOVAS = ("fonte", "conferencia", "rotulo_ia")


def _criar_tabela(con):
    con.execute("CREATE TABLE IF NOT EXISTS shopee_video_rascunhos ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, id_video TEXT, criado_em TEXT, estado TEXT, "
                "arquivo TEXT, print TEXT, link TEXT, produtos TEXT, titulo TEXT, comentario TEXT, "
                "aprovado_em TEXT, postar_em TEXT, postado_em TEXT, link_post TEXT, motivo TEXT, "
                "fonte TEXT, conferencia TEXT, rotulo_ia TEXT)")
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
    ("rodada foi interrompida", "rodada interrompida"),
    ("não está respondendo", "app travado"),
    ("Meus Favoritos", "descurtir em Meus Favoritos"),
    ("Criadores & Afiliados", "descurtir em Meus Favoritos"),
    ("de férias", "loja de férias"),
    ("notificação do comentário", "achar a notificação"),
    ("painel de comentários", "abrir os comentários"),
    ("comentário não está", "achar o comentário"),
    ("Responder", "tocar em Responder"),
    ("IA não escreveu", "texto da IA"),
    ("campo de comentar", "abrir o campo de comentar"),
    ("campo de escrever", "escrever o texto"),
    ("botão de enviar", "enviar"),
    ("resposta não", "conferir a resposta"),
    ("comentário não apareceu", "conferir o comentário"),
    ("coração do vídeo do feed", "curtir no feed"),
    ("Centro do criador", "achar a Saúde no Centro do criador"),
    ("Rótulo de IA", "rótulo de IA"),
    ("Saúde do Vídeo não abriu", "abrir a Saúde do Vídeo"),
    ("sem oferta de afiliado", "oferta de afiliado"),
    ("o link não diz o produto", "achar o produto do link"),
    ("violação", "diretrizes da Shopee"),
    ("não devolveu o título", "título da IA"),
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
            "saúde lida": "🩺", "respondido": "💬", "comentado": "❤️", "descurtido": "💔"}
NOMES_DAS_ACOES = {"rascunho": "Rascunho", "postar": "Postagem", "apagar": "Apagar rascunho",
                   "treino": "Testar Caminho", "rodada": "Rodada", "saude": "Saúde do Vídeo",
                   "responder": "Resposta a comentário", "feed": "Feed (Para você)",
                   "descurtir": "Limpeza dos favoritos (4h)"}
# Como o resultado aparece para o Rafael no resumo das 22h e no Histórico (no banco fica o
# resultado de sempre, que o checkup conta). Pedido do Rafael (25/10): DECISOES.md, Shopee Vídeo.
NOMES_DOS_RESULTADOS = {"descurtido": "limpeza dos favoritos"}


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
    return " | ".join(f"{SIMBOLOS.get(r, '•')} {contas[r]} {NOMES_DOS_RESULTADOS.get(r, r)}"
                      for r in SIMBOLOS if r in contas)


def texto_historico(agora=None):
    """A tela do Histórico do Robô 📋: as tentativas das últimas 24 h, da mais nova para a mais velha."""
    lista = _ultimas_24h(agora)
    if not lista:
        return "📋 <b>Histórico do Robô</b>\n\nNenhuma tentativa nas últimas 24 h."
    linhas = ["📋 <b>Histórico do Robô</b> (últimas 24 h)", _contagem(lista), ""]
    for t in lista[:LINHAS_DO_HISTORICO]:
        quando = datetime.strptime(t["momento"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
        linhas.append(f"{SIMBOLOS.get(t['resultado'], '•')} <b>{quando}</b> · "
                      f"{NOMES_DAS_ACOES.get(t['acao'], t['acao'])}: "
                      f"{html.escape(NOMES_DOS_RESULTADOS.get(t['resultado'], t['resultado']))}")
        if t["produto"]:
            linhas.append(f"   🛍️ {html.escape(t['produto'][:80])}")
        if t["motivo"]:
            linhas.append(f"   📍 {html.escape(t['passo'])}: {html.escape(t['motivo'][:120])}")
    if len(lista) > LINHAS_DO_HISTORICO:
        linhas.append(f"\n… e mais {len(lista) - LINHAS_DO_HISTORICO} tentativa(s) antes destas.")
    return "\n".join(linhas)


def motivo_da_espera(config, agora=None):
    """Por que um aprovado já na hora de ir ao ar ainda não saiu (o que o o_que_fazer segura agora)."""
    if config["robo_pausado"]:
        return "a Postagem está pausada"
    if suspensa(config, agora):
        return f"conta suspensa pela Shopee até {quando_acaba(suspenso_ate(config))}"
    if na_hora_do_descurtir(agora):
        return f"às {HORA_DO_DESCURTIR}h o robô só descurte"
    if not no_horario(config, agora):
        return "fora do Horário do Robô"
    if na_hora_das_interacoes(config, agora) and not interacoes_do_dia_feitas(agora):
        inicio = agora_br(agora).strftime("%Y-%m-%d 00:00:00")
        faltam = max(0, interacoes.COMENTARIOS_NO_FEED_POR_DIA
                     - interacoes.quantos_desde("video_feed", interacoes.COMENTADOS_NO_FEED, inicio))
        partes = ([f"{faltam} comentário(s) no feed"] if faltam else []) + (
            ["as respostas aos comentários"] if respostas_pendentes(agora) else [])
        return f"no Horário das Interações, esperando acabarem {' e '.join(partes) or 'as interações'} do dia"
    return "sai numa das próximas rodadas (a cada 15 min)"


def texto_da_fila(config=None, agora=None):
    """
    A tela da Fila de Rascunhos 🗂️: os rascunhos esperando a aprovação do Rafael e os
    aprovados, com a hora prevista de ir ao ar e, para o que já passou da hora, por que ainda
    não saiu. Pedido do Rafael: DECISOES.md, Shopee Vídeo.
    """
    config = config or ler_config()
    agora_txt = _momento(agora)

    def produto(r):
        nomes = r["produtos"] or []
        return html.escape((nomes[0] if nomes else r["titulo"] or "?")[:70]) + (
            f" (+{len(nomes) - 1})" if len(nomes) > 1 else "")

    def curta(texto):
        return f"{texto[8:10]}/{texto[5:7]} às {texto[11:16]}" if texto and len(texto) >= 16 else "?"

    linhas = ["🗂️ <b>Fila de Rascunhos</b>", ""]
    pendentes = esperando_aprovacao()
    linhas.append(f"📝 <b>Esperando a sua aprovação ({len(pendentes)})</b>")
    linhas += [f"• {produto(r)}\n   salvo em {curta(r['criado_em'])}" for r in pendentes] or ["nenhum"]
    aprovados = sorted(listar("aprovado"), key=lambda r: (r["postar_em"] or "", r["id"]))
    linhas += ["", f"✅ <b>Aprovados, esperando ir ao ar ({len(aprovados)})</b>"]
    espera = motivo_da_espera(config, agora)
    for r in aprovados:
        linhas.append(f"• {produto(r)}\n   posta por volta de {curta(r['postar_em'])}")
        if r["postar_em"] and r["postar_em"] <= agora_txt:
            linhas.append(f"   ⏳ já passou da hora: {html.escape(espera)}")
    if not aprovados:
        linhas.append("nenhum")
    if pendentes:
        linhas += ["", "Para aprovar ou recusar: Rascunhos do Robô 📝."]
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
    marcado. Fora do Horário do Robô, vai para o começo do próximo horário, e no Horário
    das Interações e na hora do descurtir, para o fim deles, com uns minutos sorteados: os
    aprovados saem espalhados, nunca todos de uma vez.
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
    janela = janela_das_interacoes(config)
    # Ajusta até cair no horário de postar: fora do Horário do Robô, o começo do próximo; no
    # Horário das Interações (P22) e na hora do descurtir (P25), o fim deles. Sempre com uns
    # minutos sorteados.
    for _ in range(6):
        fim_do_corte = (janela[1] if janela and janela[0] <= quando.hour < janela[1]
                        else HORA_DO_DESCURTIR + 1 if quando.hour == HORA_DO_DESCURTIR else None)
        if fim_do_corte is not None:
            quando = (datetime(quando.year, quando.month, quando.day, tzinfo=momento.tzinfo)
                      + timedelta(hours=fim_do_corte, minutes=sorteio.randint(*ESPERA_DA_PRIMEIRA)))
        elif quando.hour >= config["robo_fim"] or (quando.date() > momento.date() and quando.hour < config["robo_inicio"]):
            dia = quando.date() if quando.hour < config["robo_inicio"] else quando.date() + timedelta(days=1)
            quando = datetime(dia.year, dia.month, dia.day, config["robo_inicio"], tzinfo=momento.tzinfo)
            quando += timedelta(minutes=sorteio.randint(*ESPERA_DA_PRIMEIRA))
        elif quando.hour < config["robo_inicio"]:
            quando = quando.replace(hour=config["robo_inicio"], minute=0) + timedelta(
                minutes=sorteio.randint(*ESPERA_DA_PRIMEIRA))
        else:
            break
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
    A tarefa desta rodada: ("descurtir", None) (tudo em Meus Favoritos, às 4h, e nessa
    hora só isso), ("treino", None), ("apagar", id), ("postar", id), ("saude",
    None) (a Saúde do Vídeo, uma vez por dia e de hora em hora depois do Já recorri),
    ("rascunho", None), ("responder", None) (os comentários dos vídeos, uma vez por dia),
    ("feed", None) (um vídeo do feed, até 3 por dia) ou None. Gasta o horário do plano, ou
    uma tentativa a mais do rascunho que falhou, quando escolhe um rascunho.
    """
    if na_hora_do_descurtir(agora):
        # A hora do descurtir é só dele (P25).
        return ("descurtir", None) if descurtir_pendente(agora) else None
    # Na suspensão a Shopee fecha o Postar vídeo: o treino, o preparo e a postagem, que
    # passam por ele, esperam o fim. O resto segue: a limpeza dos favoritos, apagar o
    # recusado, a Saúde do Vídeo, as respostas e o feed. Pedido do Rafael (25/10): DECISOES.md.
    sem_postar = suspensa(config, agora)
    if treino_da_semana_pendente(agora) and not sem_postar:
        return "treino", None
    recusados = listar("recusado")
    if recusados:
        return "apagar", recusados[0]["id"]
    # Responder e o feed só no Horário das Interações (sem ele escolhido, no Horário do Robô,
    # como antes); preparar e postar fora dele, ou nele depois que as interações do dia
    # acabam. Escolhas do Rafael (P22 a P24 e P26). (A rodada já confere o horário: aqui
    # só a separação entre os dois.)
    na_janela = na_hora_das_interacoes(config, agora)
    postar = (not na_janela or interacoes_do_dia_feitas(agora)) and not sem_postar
    interagir = na_janela or not janela_das_interacoes(config)
    agora_txt = _momento(agora)
    aprovados = listar("aprovado")
    prontos = [r for r in aprovados if r["postar_em"] and r["postar_em"] <= agora_txt]
    if postar and prontos:
        return "postar", min(prontos, key=lambda r: r["postar_em"])["id"]
    # Um aprovado vai ao ar antes da próxima rodada: nada de tarefa longa (Saúde, rascunho,
    # respostas, feed), que seguraria o celular na hora do post. Escolha do Rafael (P30).
    logo = _momento(agora_br(agora) + ANTES_DO_POST)
    if postar and any(r["postar_em"] and agora_txt < r["postar_em"] <= logo for r in aprovados):
        return None
    if saude_do_dia_pendente(agora) or saude_pedida_pelo_recurso(agora):
        return "saude", None
    if postar and (consumir_horarios(config, agora) or repetir_o_que_falhou(config, agora)):
        return "rascunho", None
    if interagir and respostas_pendentes(agora):
        return "responder", None
    if interagir and feed_pendente(agora):
        return "feed", None
    return None


# --- Toques no celular ---

def pausa(segundos):
    """Espera com uns segundos a mais sorteados: toque em ritmo de máquina denuncia robô."""
    time.sleep(segundos + random.uniform(0.5, 2.5))


def tela(d, seguir=False):
    """
    A tela de agora; para na hora se for a Verificação. Com o aviso do Android de app que
    não responde ("Shopee não está respondendo", com Fechar app e Aguardar), toca em
    Aguardar e dá um tempo ao app. Ainda travado depois de VEZES_DO_AGUARDAR toques,
    fecha e reabre a Shopee (fechar_e_reabrir). O passo que esperava outra tela não
    continua do início do app: a rodada para; com seguir=True (o voltar, que leva ao
    início de qualquer jeito), devolve a tela do app reaberto.
    """
    xml = d.dump_hierarchy()
    for vez in range(VEZES_DO_AGUARDAR + 1):
        if ps.eh_verificacao(xml):
            raise Verificacao()
        if not app_travado(xml):
            if vez:
                registro_processos.registrar(REGISTRO, "app travado", "voltou depois do Aguardar",
                                             f"{vez} toque(s)", ok=True)
            return xml
        if vez == VEZES_DO_AGUARDAR:
            break
        d.click(*ps.achar(xml, "@aerr_wait"))
        pausa(ESPERA_DO_AGUARDAR)
        xml = d.dump_hierarchy()
    xml = fechar_e_reabrir(d, xml)
    if seguir:
        return xml
    raise Parada("a Shopee não está respondendo (aviso do Android): fechei e reabri o app; o passo fica "
                 "para a próxima rodada")


def fechar_e_reabrir(d, xml):
    """
    A Shopee continua sem responder depois dos Aguardar: toca em Fechar app no aviso do
    Android e abre a Shopee de novo. Devolve a tela do app reaberto. A Verificação que
    aparecer depois para a rodada como sempre (o Rafael recebe o link da tela); o app
    ainda travado também para. Fora este aviso, o robô nunca fecha o app.
    Escolha do Rafael (24/10, P15): DECISOES.md, Shopee Vídeo.
    """
    fechar = ps.achar(xml, "@aerr_close")
    if not fechar:
        registro_processos.registrar(REGISTRO, "app travado", "continuou travado", "o aviso sem o Fechar app",
                                     ok=False)
        raise Parada("a Shopee não está respondendo e o aviso do Android não tem o Fechar app")
    d.click(*fechar)
    pausa(4)
    d.app_start(ps.PACOTE, wait=True)
    pausa(ESPERA_DEPOIS_DE_REABRIR)
    xml = d.dump_hierarchy()
    if ps.eh_verificacao(xml):
        registro_processos.registrar(REGISTRO, "app travado", "fechado e reaberto", "a Verificação apareceu",
                                     ok=False)
        raise Verificacao()
    if app_travado(xml):
        registro_processos.registrar(REGISTRO, "app travado", "continuou travado", "depois de fechar e reabrir",
                                     ok=False)
        raise Parada("a Shopee não está respondendo, mesmo depois de fechar e reabrir o app")
    registro_processos.registrar(REGISTRO, "app travado", "fechado e reaberto",
                                 f"depois de {VEZES_DO_AGUARDAR} toque(s) em Aguardar", ok=True)
    return xml


def app_travado(xml):
    """O aviso do Android de app que não responde (os botões Fechar app e Aguardar) está na tela?"""
    return tem(xml, "@aerr_wait")


def tem(xml, alvo):
    return ps.achar(xml, alvo) is not None


def esperar_na_tela(d, alvo, segundos):
    """Relê a tela a cada 3 s, por até `segundos`, até o alvo aparecer. Devolve a tela com ele, ou None."""
    voltas = max(1, segundos // 3)
    for volta in range(voltas + 1):
        xml = tela(d)
        if tem(xml, alvo):
            return xml
        if volta < voltas:
            pausa(3)
    return None


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
    exato. Nunca fecha o app à força (fechar e reabrir em seguida chama a Verificação),
    fora o aviso do Android de app que não responde (tela). Fora da Shopee, não aperta
    voltar: traz a Shopee de volta para a frente.
    """
    for _ in range(vezes):
        xml = tela(d, seguir=True)
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
    onde = onde_ficou(d)
    registro_processos.registrar(REGISTRO, "voltar no app", f"não chegou ao {ate}", onde, ok=False)
    raise Parada(f"não consegui voltar até {ate} ({onde})")


def onde_ficou(d):
    """
    A tela em que o voltar ficou preso, só com nomes fixos (o registro sai no checkup, que
    é público): o app, o nome da tela dele (a classe, sem o pacote) e se a tela do celular
    estava ligada. Nunca o texto da tela.
    """
    try:
        atual = d.app_current() or {}
        app = atual.get("package") or "?"
        nome = (atual.get("activity") or "?").rsplit(".", 1)[-1]
    except Exception:
        app, nome = "?", "?"
    try:
        ligada = {True: "ligada", False: "desligada"}.get((d.info or {}).get("screenOn"), "?")
    except Exception:
        ligada = "?"
    return f"app {app}, tela {nome}, tela do celular {ligada}"


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


def ler_suspensao(d, agora=None, postar_fechado=False):
    """
    A conta está suspensa, e até quando? Primeiro as Notificações (rápido); achando o
    aviso, confirma na Saúde do Vídeo, que mostra a situação de agora: com o recurso
    aceito, a Shopee tira a suspensão antes do prazo, mas o aviso antigo continua nas
    Notificações. A suspensão que a Saúde não mostra fica anotada como retirada e não é
    mais conferida. Sem a Saúde abrir, o teste é o Postar vídeo: abrindo a Biblioteca, a
    conta não está bloqueada e o aviso antigo também fica como retirado; quem chega aqui
    porque o Postar vídeo não abriu (postar_fechado) fica com o aviso. Sem aviso: None.
    Pedido do Rafael: DECISOES.md, Shopee Vídeo.
    """
    ate = _suspensao_nas_notificacoes(d, agora)
    if not ate or suspensao_retirada(ate):
        return None
    try:
        abrir_saude(d)
        na_saude = suspensao_na_tela(tela(d), agora)
    except Parada as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Não confirmei a suspensão na Saúde do Vídeo: {ps.mascarar(e.motivo)}")
        if postar_fechado or not postar_abre(d):
            return ate
        logger.info("✅ [Robô Shopee Vídeo] O Postar vídeo abriu a Biblioteca: o aviso antigo de suspensão não vale mais.")
        na_saude = None
    if not na_saude:
        anotar_retirada(ate)
        return None
    return na_saude


def postar_abre(d):
    """
    O Postar vídeo abre a Biblioteca? Com a conta bloqueada, não abre (Motorola,
    23/10/2026). Só abre e olha: não escolhe vídeo nenhum, e o passo seguinte do robô
    começa de novo do início do app.
    """
    try:
        ir_ao_perfil(d)
        seguir(d, CAMINHO_GALERIA[:1])
    except Parada:
        return False
    return True


def _suspensao_nas_notificacoes(d, agora=None):
    """
    O fim da suspensão que o aviso nas Notificações (filtro Lives, Vídeos e ...) diz, ou
    None. Só toca na aba e no filtro e rola a lista: não abre nenhuma notificação.
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
        ate = ler_suspensao(d, agora, postar_fechado=True)
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
    botao, espera, esperado = CAMINHO_CENTRO_DO_CRIADOR[0]
    tocar(d, botao, espera)
    xml = esperar_na_tela(d, esperado, ESPERA_DA_SAUDE)
    elementos = ps.elementos(xml) if xml else []
    rotulo = next((el for el in elementos if ps._normal(el["texto"]) == ps._normal(SAUDE_DO_VIDEO)), None)
    if not rotulo:
        raise Parada("o Centro do criador não mostrou a Saúde do Vídeo")
    x, y = ps._centro(rotulo)
    na_linha = [el for el in elementos if el["clicavel"] and abs(ps._centro(el)[1] - y) <= 60 and ps._centro(el)[0] > x]
    abaixo = [el for el in elementos if el["clicavel"] and y < ps._centro(el)[1] <= y + 200]
    alvo = (na_linha or sorted(abaixo, key=lambda el: ps._centro(el)[1]) or [rotulo])[0]
    d.click(*ps._centro(alvo))
    pausa(8)
    if not esperar_na_tela(d, VIDEOS_DE_VIOLACAO, ESPERA_DA_SAUDE):
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
    if ate:
        if guardar_suspensao(ate):
            avisar_suspensao(ate)
    else:
        # Sem o bloqueio na Saúde: se o robô esperava a suspensão, ela saiu antes do prazo.
        suspensao_acabou_antes(agora)
    vistas, novas, completa, aceitas, recusadas = set(), 0, False, [], []
    for _ in range(ROLADAS_NA_SAUDE + 1):
        andou = False
        while True:
            punicao = next((p for p in punicoes_na_tela(tela(d))
                            if apelacoes.chave(p["tipo"], p["data"]) not in vistas), None)
            if not punicao:
                break
            vistas.add(apelacoes.chave(punicao["tipo"], punicao["data"]))
            andou = True
            antes = apelacoes.situacao_de(punicao["tipo"], punicao["data"])
            if apelacoes.recorrida_no_app(punicao["status"]) or antes:
                ident = apelacoes.guardar(punicao["tipo"], punicao["data"], punicao["status"], agora=agora)
                if antes in (apelacoes.PENDENTE, apelacoes.RECORRIDA) and apelacoes.aceita_no_app(punicao["status"]):
                    aceitas.append(apelacoes.pegar(ident))
                elif (antes in (apelacoes.PENDENTE, apelacoes.RECORRIDA)
                      and apelacoes.recusada_no_app(punicao["status"])):
                    recusadas.append(apelacoes.pegar(ident))
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
            completa = True
            break
        ps.rolar(d)
        pausa(3)
    if completa:
        aceitas += apelacoes.retirar_ausentes(vistas, agora)
    for p in aceitas:
        avisar(f"🎉 Robô da Shopee Vídeo: o recurso da punição {p['tipo']} ({p['data_punicao']}) deu certo: a Shopee "
               "a tirou ou marcou como aceita na Saúde do Vídeo. Parei de lembrar dela.")
    for p in recusadas:
        avisar(f"❌ Robô da Shopee Vídeo: a Shopee não aceitou o recurso da punição {p['tipo']} ({p['data_punicao']}). "
               "Os pontos dela continuam na Saúde do Vídeo.")
    gravar_estado(saude_lida_em=_momento(agora), saude_pontos=pontos, saude_punicoes=len(vistas))
    _sair_sem_salvar(d)
    return novas, len(vistas), pontos


def saude_do_dia_pendente(agora=None):
    """O robô ainda não tentou ler a Saúde do Vídeo hoje? (uma vez por dia)"""
    return not (ler_estado().get("saude_tentada_em") or "").startswith(agora_br(agora).strftime("%Y-%m-%d"))


def saude_pedida_pelo_recurso(agora=None):
    """
    O Rafael tocou em Já recorri numa punição e o resultado ainda não saiu: a Saúde é
    lida de hora em hora (a última tentativa tem 1 h ou mais). Escolha do Rafael:
    DECISOES.md, Shopee Vídeo.
    """
    if not apelacoes.esperando_resultado(agora):
        return False
    return (ler_estado().get("saude_tentada_em") or "") <= _momento(agora_br(agora) - INTERVALO_DO_RECURSO)


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


def avisar_video(caminho, legenda):
    try:
        return avisar_rafael.mandar_video(caminho, legenda)
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Vídeo não chegou ao Rafael: {type(e).__name__}")
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
    # curtidos: os produtos que o robô curtiu (descurtir_no_fim); celular: se ele já usou o
    # celular (o caso só lê a tela quando ela é deste rascunho).
    curtidos, celular = [], []
    try:
        _preparar(d, ident, video, config.get("fonte", assistente.FONTE_PADRAO), agora, curtidos, celular)
    except Suspensa as e:
        _desfazer_reserva(ident, video["id"], "conta suspensa", False)
        registrar_tentativa("rascunho", "suspensa", str(e), _produto_do_video(video), agora)
        if curtidos:
            gravar_estado(favoritos_limpos=False)
        raise
    except Verificacao:
        _guardar_caso(d, "rascunho", "verificação", "verificação da Shopee na tela", video, ident, agora)
        _desfazer_reserva(ident, video["id"], "verificação", False)
        if curtidos:
            # Na Verificação o robô para sem descurtir: a curtida fica para as 4h.
            gravar_estado(favoritos_limpos=False)
        registrar_tentativa("rascunho", "verificação", "verificação da Shopee na tela", _produto_do_video(video), agora)
        raise
    except Parada as e:
        _guardar_caso(d if celular else None, "rascunho", "pulado" if e.do_video else "parou", e.motivo, video,
                      ident, agora)
        _desfazer_reserva(ident, video["id"], e.motivo, e.do_video)
        registrar_tentativa("rascunho", "pulado" if e.do_video else "parou", e.motivo, _produto_do_video(video), agora)
        e.id_video = video["id"]
        descurtir_no_fim(d, video, curtidos)
        raise
    except Exception as e:
        _guardar_caso(d if celular else None, "rascunho", "erro", f"erro inesperado ({type(e).__name__})", video,
                      ident, agora)
        _desfazer_reserva(ident, video["id"], type(e).__name__, False)
        registrar_tentativa("rascunho", "erro", f"erro inesperado ({type(e).__name__})", _produto_do_video(video), agora)
        e.id_video = video["id"]
        descurtir_no_fim(d, video, curtidos)
        raise
    registrar_tentativa("rascunho", "salvo", produto=", ".join((pegar(ident) or {}).get("produtos") or [])
                        or _produto_do_video(video), agora=agora)
    descurtir_no_fim(d, video, curtidos)
    return "rascunho salvo"


def descurtir_no_fim(d, video, curtidos):
    """
    O fim de cada rascunho, salvo ou não: descurte os produtos que o robô curtiu nele
    (curtidos: (posição no Ver Produtos, nome), com a posição None no link de produto), pelo
    mesmo caminho do curtir. A curtida só serve para o produto subir em Minhas Curtidas; o
    rascunho salvo guarda o produto anexado, e o postar confere a tela final antes de tocar
    em Postar. O que não descurtir aqui fica para o descurtir das 4h. A Verificação da
    Shopee segue parando tudo; a conta suspensa não passa por aqui (o robô não toca no
    celular nela). Pedido do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if not curtidos:
        return
    todos = False
    try:
        if video.get("de_video"):
            _abrir_ver_produtos(d, video)
            todos = True
            for indice, nome in curtidos:
                xml = tela(d)
                pontos = ps.produtos_vinculados(xml)
                if indice >= len(pontos) or ps.proibido_no_ponto(xml, *pontos[indice]):
                    registro_processos.registrar(REGISTRO, "descurtir no fim do rascunho", "produto fora da lista",
                                                 ok=False)
                    todos = False
                    continue
                d.click(*pontos[indice])
                pausa(8)
                xml = tela(d)
                if ps.nome_na_pagina_do_produto(xml) == nome:
                    todos = ps.descurtir_na_pagina(d, xml)[0] and todos
                else:
                    registro_processos.registrar(REGISTRO, "descurtir no fim do rascunho",
                                                 "outro produto na posição", ok=False)
                    todos = False
                d.press("back")
                pausa(4)
        else:
            ir_ao_inicio(d)
            ps.limpar_aviso_rapido(d)
            ps.abrir_link(d, video["link"])
            pausa(8)
            todos = ps.descurtir(d, video)[0]
    except Verificacao:
        gravar_estado(favoritos_limpos=False)
        raise
    except Parada as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Não descurti no fim do rascunho: {ps.mascarar(e.motivo)}")
        registro_processos.registrar(REGISTRO, "descurtir no fim do rascunho", "parou", ok=False)
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Erro ao descurtir no fim do rascunho: {type(e).__name__}")
        registro_processos.registrar(REGISTRO, "descurtir no fim do rascunho", "erro", type(e).__name__, ok=False)
    if not todos:
        # Uma curtida ficou para trás: a lista não está limpa até o descurtir das 4h (P27).
        gravar_estado(favoritos_limpos=False)


def _guardar_caso(d, acao, resultado, motivo, video=None, ident=None, agora=None):
    """
    O caso completo da tentativa que não deu certo (motivo, vídeo, título, produtos, print e
    tela), cifrado para o checkup do Claude e apagado depois (casos_robo). Pedido do
    Rafael: DECISOES.md, Shopee Vídeo.
    """
    casos_robo.guardar(d, acao, resultado, motivo, passo_do_motivo(motivo), video,
                       pegar(ident) if ident else None, agora)


def _desfazer_reserva(ident, id_video, motivo, do_video):
    """Vídeo com problema próprio fica marcado e não volta; nos outros casos, volta para a fila."""
    if do_video:
        atualizar(ident, estado="pulado", motivo=motivo)
    else:
        apagar_registro(ident)
    with db.conexao() as con:
        assistente._criar_tabela(con)
        con.execute("DELETE FROM shopee_video_enviados WHERE id_unico = ? AND status = 'robo'", (id_video,))


def soltar_preparos_interrompidos(agora=None):
    """
    Rascunho que ficou em "preparando" por mais que uma rodada inteira: a rodada morreu no
    meio (o deploy reinicia o bot_mestre e mata o processo dela). O vídeo volta para a fila
    e a tentativa entra no histórico, para o checkup ver; o horário do plano que estava em
    preparo (em_preparo no plano do dia) tenta de novo. Devolve quantos soltou.
    """
    limite = _momento(agora_br(agora) - timedelta(seconds=MAXIMO_DA_RODADA))
    presos = [r for r in listar("preparando") if (r["criado_em"] or "") < limite]
    for rascunho in presos:
        _desfazer_reserva(rascunho["id"], rascunho["id_video"], "a rodada foi interrompida", False)
        registrar_tentativa("rascunho", "parou", "a rodada foi interrompida no meio do preparo", agora=agora)
        registro_processos.registrar(REGISTRO, "preparo interrompido", "solto", "o vídeo voltou para a fila", ok=False)
    estado = estado_do_dia(ler_config(), agora)
    if estado.get("em_preparo"):
        # O rascunho do plano morreu no meio: o horário tenta de novo, e a tentativa perdida
        # volta, porque a culpa não foi do vídeo. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
        estado.update(em_preparo=False, repetir=True, tentativas=estado.get("tentativas", 0) + 1)
        db.salvar_config(CHAVE_DIA, estado)
        registro_processos.registrar(REGISTRO, "preparo interrompido", "horário do plano tenta de novo", ok=None)
    return len(presos)


def _conferir(resultado, do_video=True):
    ok, motivo = resultado
    if not ok:
        raise Parada(motivo, do_video=do_video)


# Minhas Curtidas está limpa quando a última limpeza deu certo: o descurtir das 4h acabou
# a lista, e cada rascunho desde então descurtiu o que curtiu. Qualquer curtida que ficou
# para trás suja a lista até o próximo descurtir das 4h. Escolha do Rafael (P27):
# DECISOES.md, Shopee Vídeo.
def lista_limpa():
    return bool(ler_estado().get("favoritos_limpos"))


def _conferir_curtida(resultado):
    """Confere a curtida; o curtido de outro dia que não descurtiu fica mais embaixo: a lista não está limpa."""
    _conferir(resultado)
    if resultado[1] == ps.CURTIDO_DE_ANTES:
        gravar_estado(favoritos_limpos=False)


def _codigos_da_ia():
    """Os códigos do Google (finish_reason e block_reason) da última resposta vazia, sem o STOP."""
    return sorted(ps.api_gemini.codigos_do_google(ps.api_gemini.ULTIMO_ERRO_IA))


def _motivo_da_ia():
    """
    Por que a IA não deu o título, em códigos fixos do Google (nunca o texto dela): a resposta
    vazia traz o finish_reason (SAFETY, RECITATION, MAX_TOKENS...) ou o block_reason; a cota
    e os outros erros vêm do ULTIMO_ERRO_IA; sem erro, a IA respondeu sem o título no JSON.
    """
    erro = ps.api_gemini.ULTIMO_ERRO_IA or ""
    codigos = _codigos_da_ia()
    if codigos:
        return f"resposta vazia ({', '.join(codigos)})"
    if "VAZIO" in erro:
        return "resposta vazia"
    if re.search(r"429|RESOURCE_EXHAUSTED|quota", erro, re.I):
        return "cota da IA"
    return "erro da IA" if erro else "resposta sem o título"


def _avisar_recusa(video, nomes, recusa):
    """
    O vídeo que o Google recusou, no privado na hora: o vídeo, o produto, o que o Google disse
    e o que deu o pedido em palavras leves. Sem conseguir mandar o vídeo, vai só o texto.
    Escolha do Rafael (P29): DECISOES.md, Shopee Vídeo.
    """
    legenda = assistente.texto_da_recusa(recusa, ", ".join(nomes or []))
    if not (video.get("arquivo") and os.path.exists(video["arquivo"]) and avisar_video(video["arquivo"], legenda)):
        avisar(legenda)


def _textos_da_ia(video, nomes=None):
    """
    O título e o comentário da IA. A IA às vezes volta vazia (bloqueio do Google que muda de
    uma tentativa para outra, como o RECITATION): mais uma chance depois de uma pausa, antes
    de desistir. O pedido recusado pelo conteúdo (BLOQUEIOS_DO_CONTEUDO) já é refeito pelo
    assistente com as regras em palavras leves (P28); recusado de novo, o vídeo fica de lado
    na hora, e o horário passa ao próximo. Cada falha entra no registro com o motivo em código
    fixo, para o checkup mostrar a causa.
    """
    motivo, recusa = "", None
    try:
        for vez in range(TENTATIVAS_DO_TITULO):
            ps.api_gemini.ULTIMO_ERRO_IA, assistente.ULTIMA_RECUSA = None, None
            textos = asyncio.run(assistente.textos_do_video(video["arquivo"], video.get("nome") or ""))
            recusa = assistente.ULTIMA_RECUSA or recusa
            if textos and textos["titulo"]:
                if textos.get("regras_leves"):
                    registro_processos.registrar(REGISTRO, "título da IA", "veio com as regras em palavras leves",
                                                 ok=True)
                elif vez:
                    registro_processos.registrar(REGISTRO, "título da IA", "veio na nova tentativa", ok=True)
                return textos
            motivo = _motivo_da_ia()
            registro_processos.registrar(REGISTRO, "título da IA", "sem título", motivo, ok=False)
            if BLOQUEIOS_DO_CONTEUDO & set(_codigos_da_ia()):
                raise Parada(f"a IA não devolveu o título ({motivo}, também com as regras em palavras leves): o "
                             "Google bloqueia o conteúdo deste vídeo", do_video=True)
            if vez + 1 < TENTATIVAS_DO_TITULO:
                pausa(ESPERA_DO_TITULO)
        raise Parada(f"a IA não devolveu o título ({motivo})")
    finally:
        # Uma vez por vídeo, com o que deu por último (o Rafael vê a causa da recusa).
        if recusa:
            _avisar_recusa(video, nomes, recusa)


# Eu → Criadores & Afiliados → Meus favoritos, como o Rafael ensinou (vídeo de 25/10/2026): a
# lista de afiliado (AN_MyLikesListPage), a mesma do Minhas Curtidas do Adicionar Produto (o
# Meus Favoritos de comprador, direto na aba Eu, é outra lista). Cada produto tem uma caixa de
# marcar; na barra de baixo ficam a caixa de marcar tudo, o "Selecionado N/50" (até 50 de cada
# vez), o Like, que tira os marcados ("Removido das Minhas Curtidas com sucesso!"), e o
# Compartilhar. O robô marca e tira de novo, até a lista acabar, em VOLTAS_DO_DESCURTIR voltas
# por rodada. Nunca toca em Compartilhar nem no Substituir Tudo do aviso do alto da lista.
CRIADORES_E_AFILIADOS = "Criadores & Afiliados"
MEUS_FAVORITOS = "Meus favoritos"
# Uma aba da área de afiliado: com ela na tela, o toque em Criadores & Afiliados pegou (sem ela,
# "Meus favoritos" acharia o Meus Favoritos de comprador da aba Eu).
ABA_DE_AFILIADO = "Conversão"
# O filtro do alto da lista: com ele na tela, Meus favoritos abriu.
FILTRO_DOS_FAVORITOS = "Melhor Oferta"
CAIXA_DE_MARCAR = "AN_Checkbox_CheckedIconUnCheckIcon_Img"
BOTAO_LIKE = "Like"
NUNCA_NOS_FAVORITOS = ("compartilhar", "substituir")
LIMITE_DA_SELECAO = 50
VOLTAS_DO_DESCURTIR = 10
# Sem a caixa de marcar tudo, o robô marca um por um, rolando a lista até estas vezes.
ROLAGENS_DA_SELECAO = 12
# O botão que confirma a remoção, se o app perguntar (nunca o Cancelar).
CONFIRMAR_REMOCAO = ("@buttonDefaultPositive", "Remover", "Excluir", "Confirmar", "Sim", "OK")


def selecionados(xml):
    """(marcados, máximo) do "Selecionado N/M" da barra de Meus favoritos; None sem ele na tela."""
    for el in ps.elementos(xml):
        achado = re.search(r"selecionado\D*(\d+)\s*/\s*(\d+)", el["texto"], re.I)
        if achado:
            return int(achado.group(1)), int(achado.group(2))
    return None


def _marcados(xml):
    return (selecionados(xml) or (0, 0))[0]


def caixas_de_marcar(xml):
    """
    (a caixa de marcar tudo, [as caixas dos produtos]), pelo id da caixa: a de marcar tudo é a
    da linha do "Selecionado N/M"; as outras são as dos produtos na tela.
    """
    lista = ps.elementos(xml)
    texto = next((el for el in lista if re.match(r"selecionado", el["texto"].strip(), re.I)), None)
    linha = (texto["caixa"][1] + texto["caixa"][3]) // 2 if texto else None
    barra, produtos = None, []
    for el in lista:
        if el["id"] != CAIXA_DE_MARCAR:
            continue
        if linha is not None and el["caixa"][1] <= linha <= el["caixa"][3]:
            barra = ps._centro(el)
        elif ps._centro(el) not in produtos:
            produtos.append(ps._centro(el))
    return barra, produtos


def _ponto_exato(xml, alvo):
    """O centro do elemento com exatamente esse texto (ou esse @id); None sem ele."""
    for el in ps.elementos(xml):
        if (alvo.startswith("@") and el["id"] == alvo[1:]) or ps._normal(el["texto"]) == ps._normal(alvo):
            return ps._centro(el)
    return None


def _seguro(xml, ponto):
    """O toque nesse ponto não cai em Compartilhar, no Substituir Tudo nem em nada proibido (comprar, carrinho)."""
    if ps.proibido_no_ponto(xml, *ponto):
        return False
    return not any(ps._dentro(ponto, el["caixa"]) and any(p in el["texto"].casefold() for p in NUNCA_NOS_FAVORITOS)
                   for el in ps.elementos(xml))


def _confirmar_remocao(d):
    """Se o app pergunta antes de remover, toca no botão que confirma."""
    xml = tela(d)
    for alvo in CONFIRMAR_REMOCAO:
        ponto = _ponto_exato(xml, alvo)
        if ponto and not ps.proibido_no_ponto(xml, *ponto):
            d.click(*ponto)
            pausa(3)
            return


def pagina_dos_favoritos(d, segundos=12):
    """
    Como Meus favoritos abriu, relendo a tela por até `segundos`: "com produtos" (as caixas de
    marcar dos produtos) ou "vazia" (o filtro do alto da lista, sem nenhum produto, até o fim da
    espera). None: a página não abriu.
    """
    voltas = max(1, segundos // 3)
    for volta in range(voltas + 1):
        xml = tela(d)
        if caixas_de_marcar(xml)[1]:
            return "com produtos"
        if volta < voltas:
            pausa(3)
    return "vazia" if tem(xml, FILTRO_DOS_FAVORITOS) else None


def _marcar(d):
    """
    Marca até LIMITE_DA_SELECAO produtos: primeiro pela caixa de marcar tudo; se ela não marcar
    nenhum, um por um, rolando a lista. Cada toque é conferido pelo "Selecionado N/M": o que
    desmarcou (já estava marcado) leva outro toque. Os que já estavam marcados de antes valem.
    Devolve quantos ficaram marcados.
    """
    xml = tela(d)
    marcados = _marcados(xml)
    if marcados:
        return marcados
    barra, _ = caixas_de_marcar(xml)
    if barra and _seguro(xml, barra):
        d.click(*barra)
        pausa(2)
        xml = tela(d)
        marcados = _marcados(xml)
        if marcados:
            return marcados
    for _ in range(ROLAGENS_DA_SELECAO):
        for ponto in caixas_de_marcar(xml)[1]:
            if marcados >= LIMITE_DA_SELECAO:
                return marcados
            if not _seguro(xml, ponto):
                continue
            d.click(*ponto)
            pausa(1)
            xml = tela(d)
            if _marcados(xml) < marcados:
                d.click(*ponto)
                pausa(1)
                xml = tela(d)
            marcados = _marcados(xml)
        if marcados >= LIMITE_DA_SELECAO:
            break
        ps.rolar(d)
        pausa(2)
        xml = tela(d)
    return marcados


def descurtir_tudo(d, agora=None):
    """
    A rotina das 4h: tira de Meus favoritos (a lista de afiliado, a do Minhas Curtidas) tudo o
    que está curtido: Eu → Criadores & Afiliados → Meus favoritos → marcar → Like, até a lista
    acabar. Sobrou depois de VOLTAS_DO_DESCURTIR voltas: a rodada seguinte, na mesma hora,
    continua. Só números no registro, nunca o nome dos produtos.
    Escolhas do Rafael (P25 e o caminho que ele ensinou): DECISOES.md, Shopee Vídeo.
    """
    ir_ao_inicio(d)
    tocar(d, "Eu", 5)
    if not esperar_na_tela(d, CRIADORES_E_AFILIADOS, 9):
        ps.rolar(d)
        pausa(2)
        if not tem(tela(d), CRIADORES_E_AFILIADOS):
            raise Parada("não achei Criadores & Afiliados na aba Eu")
    tocar(d, CRIADORES_E_AFILIADOS, 6)
    if not esperar_na_tela(d, ABA_DE_AFILIADO, 12) or not tem(tela(d), MEUS_FAVORITOS):
        raise Parada("a área de Criadores & Afiliados não abriu com Meus favoritos")
    tocar(d, MEUS_FAVORITOS, 6)
    pagina = pagina_dos_favoritos(d)
    if pagina is None:
        raise Parada("Meus favoritos não abriu (nem produtos, nem o filtro da lista)")
    if pagina == "vazia":
        registro_processos.registrar(REGISTRO, "descurtir tudo (4h)", "nada curtido", ok=True)
        gravar_estado(favoritos_limpos=True)
        ir_ao_inicio(d)
        return "nada curtido em Meus favoritos"
    removidos, acabou = 0, False
    for _volta in range(VOLTAS_DO_DESCURTIR):
        if not caixas_de_marcar(tela(d))[1]:
            acabou = True
            break
        marcados = _marcar(d)
        if not marcados:
            raise Parada("marquei os produtos de Meus favoritos, mas nenhum ficou marcado")
        xml = tela(d)
        ponto = _ponto_exato(xml, BOTAO_LIKE)
        if not ponto or not _seguro(xml, ponto):
            raise Parada("a barra de Meus favoritos não mostrou o Like")
        d.click(*ponto)
        pausa(3)
        _confirmar_remocao(d)
        pausa(2)
        if _marcados(tela(d)) >= marcados:
            # Os mesmos continuam marcados: o Like não tirou (uma pergunta do app que o robô
            # não conhece, por exemplo).
            raise Parada("toquei em Like, mas os produtos marcados continuaram em Meus favoritos")
        removidos += marcados
    else:
        acabou = not caixas_de_marcar(tela(d))[1]
    gravar_estado(descurtir_continuar=not acabou, favoritos_limpos=acabou)
    ir_ao_inicio(d)
    registro_processos.registrar(REGISTRO, "descurtir tudo (4h)", "descurtido" if acabou else "continua depois",
                                 f"{removidos} produto(s)", ok=True if acabou else None)
    if not acabou:
        return f"{removidos} produto(s) descurtido(s) em Meus favoritos; o resto fica para a próxima rodada"
    return f"{removidos} produto(s) descurtido(s) em Meus favoritos"


# --- O mesmo produto com mais comissão (P33) ---

PROCESSO_DA_COMISSAO = "comissão: o mesmo produto que paga mais"


def termo_da_busca(nome):
    """As primeiras PALAVRAS_DA_BUSCA palavras do nome, sem o que vem entre colchetes ou parênteses e sem símbolos."""
    limpo = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", nome or "")
    palavras = [p for p in re.sub(r"[^\w\s-]", " ", limpo).split() if p.strip("-_")]
    return " ".join(palavras[:PALAVRAS_DA_BUSCA])


def candidatos_de_mais_comissao(original, ofertas):
    """
    Das ofertas da busca, as que pagam mais que o produto do link e têm o nome parecido
    com o dele, da maior comissão para a menor: [{nome, link, comissao}]. O próprio produto
    do link nunca entra: a comissão dele não é maior que ela mesma.
    """
    candidatos = []
    for oferta in ofertas:
        nome = (oferta.get("productName") or "").strip()
        link = oferta.get("productLink") or ""
        comissao = assistente._numero(oferta.get("commissionRate")) * 100
        if not nome or not link or comissao <= original["comissao"]:
            continue
        if ps.parecido_entre([nome], original["nome"])[0] < PARECIDO_NA_BUSCA:
            continue
        candidatos.append({"nome": nome, "link": link, "comissao": comissao,
                           "vendas": int(assistente._numero(oferta.get("sales")))})
    return sorted(candidatos, key=lambda c: (-c["comissao"], -c["vendas"]))


def trocar_pela_maior_comissao(video):
    """
    O mesmo produto do link, de outra loja, que paga mais comissão (contando a Comissão
    Extra), como o Rafael faz pela busca por foto com o filtro Comissão: a API busca pelo
    nome por maior comissão, ficam os de nome parecido que pagam mais, e a IA confere cada
    um com o vídeo pela foto do anúncio, com a mesma régua do produto do link (o mesmo item,
    da mesma cor). O primeiro confirmado vale: {nome, link, comissao, antes, vistos}, com o
    link curto que o celular abre. Nenhum: None, e o robô segue com o produto do link. A
    troca é um ganho a mais: um erro nela nunca derruba o rascunho.
    Escolha do Rafael (25/10, P33): DECISOES.md, Shopee Vídeo.
    """
    try:
        return _trocar_pela_maior_comissao(video)
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] A busca do produto que paga mais deu erro: {type(e).__name__}")
        registro_processos.registrar(REGISTRO, PROCESSO_DA_COMISSAO, f"mantido - erro ({type(e).__name__})")
        return None


def _trocar_pela_maior_comissao(video):
    def anotar(resultado, ok=None):
        registro_processos.registrar(REGISTRO, PROCESSO_DA_COMISSAO, resultado, ok=ok)

    produtos, _ = asyncio.run(assistente.produtos_do_link(video["link"]))
    if not produtos:
        anotar("mantido - a API não disse o produto do link")
        return None
    original = produtos[0]
    ofertas = asyncio.run(api_shopee.buscar_ofertas_shopee(termo_da_busca(original["nome"]), limite=OFERTAS_NA_BUSCA,
                                                           sort_type=5))
    candidatos = candidatos_de_mais_comissao(original, ofertas)
    if not candidatos:
        anotar("mantido - nenhum com mais comissão" if ofertas else "mantido - a busca não trouxe nada")
        return None
    for candidato in candidatos[:CANDIDATOS_NA_IA]:
        link = asyncio.run(api_shopee.converter_link_shopee(candidato["link"], api_shopee.ETIQUETA_SHOPEE_VIDEO,
                                                            avisar_falha=False))
        if not link or link == candidato["link"]:
            # Sem o link curto, o celular não abre o produto (fica no esqueleto da página).
            continue
        vistos = []
        ok, _ = ps.ia_confere_produto(dict(video, link=link), vistos, avisar=False)
        if ok:
            anotar("trocado", ok=True)
            return {**candidato, "link": link, "antes": original["comissao"], "vistos": vistos}
    anotar("mantido - a IA não confirmou nenhum")
    return None


def _preparar(d, ident, video, fonte, agora=None, curtidos=None, celular=None):
    """
    O rascunho no celular. curtidos recebe cada produto que o robô curtiu (descurtir_no_fim);
    celular ganha um item quando o robô começa a usar o celular.
    """
    curtidos = [] if curtidos is None else curtidos
    celular = [] if celular is None else celular
    vistos = []
    if video.get("de_video"):
        celular.append(True)
        avisar("🤖 Robô da Shopee Vídeo: começando um rascunho.\n\nProdutos: os do Ver Produtos do vídeo; a IA "
               f"confere cada um.\nVídeo: o mais novo de {assistente.FONTES.get(fonte, fonte)} ainda não usado.")
        nomes = _produtos_do_video(d, video, vistos, curtidos)
    else:
        nome = ps.nome_do_produto(video)
        if not nome:
            raise Parada("o link não diz o produto do vídeo", do_video=True)
        # O mesmo produto de outra loja que paga mais, já conferido pela IA com o vídeo, toma
        # o lugar do produto do link (o video muda aqui: curtir, anexar e descurtir usam o
        # novo). Escolha do Rafael (25/10, P33): DECISOES.md, Shopee Vídeo.
        troca = trocar_pela_maior_comissao(video)
        if troca:
            video["link"] = troca["link"]
            nome = ps.nome_do_produto(video) or troca["nome"]
            vistos.extend(troca["vistos"])
        # Antes de tocar no celular, o Rafael sabe qual vídeo e qual produto o robô pegou.
        avisar(f"🤖 Robô da Shopee Vídeo: começando um rascunho.\n\nProduto: {nome}\n"
               + (f"Comissão: {troca['comissao']:.1f}% (o produto do link pagava {troca['antes']:.1f}%: troquei "
                  "pelo mesmo produto de outra loja, conferido pela IA com o vídeo)\n" if troca else "")
               + f"Vídeo: o mais novo de {assistente.FONTES.get(fonte, fonte)} ainda não usado.")
        if not troca:
            _conferir(ps.ia_confere_produto(video, vistos))
        nomes = [nome]
    # A origem e o que a IA viu ficam no rascunho, para o Rafael validar com isso na mão.
    atualizar(ident, fonte=fonte, conferencia=json.dumps(vistos, ensure_ascii=False))
    textos = _textos_da_ia(video, nomes)
    if textos["violacao"]:
        avisar(f"⚠️ Robô da Shopee Vídeo: pulei o vídeo. A IA viu possível violação das diretrizes: "
               f"{textos['motivo'] or 'sem motivo'}")
        raise Parada("a IA viu violação das diretrizes", do_video=True)

    # Vídeo claramente feito por IA vai com o Rótulo de IA ligado; na dúvida, desligado.
    # Escolha do Rafael (24/10, P8): DECISOES.md, Shopee Vídeo.
    rotulo_ia = (textos.get("sinal_ia") or "a IA viu que o vídeo é gerado por IA") if textos.get("feito_por_ia") else ""

    os.makedirs(PASTA_RASCUNHOS, exist_ok=True)
    copia = os.path.join(PASTA_RASCUNHOS, f"{ident}.mp4")
    copiar_para_o_rascunho(video, fonte, copia, nomes)
    atualizar(ident, arquivo=copia, link=video["link"], produtos=nomes, titulo=textos["titulo"],
              comentario=textos.get("comentario") or "", rotulo_ia=rotulo_ia)

    celular.append(True)
    if not video.get("de_video"):
        # Curtir o produto pela página dele, como o Rafael faz antes de postar (os do Ver
        # Produtos já foram curtidos lá).
        ir_ao_inicio(d)
        ps.limpar_aviso_rapido(d)
        ps.abrir_link(d, video["link"])
        _esperar_a_pagina_do_produto(d)
        _conferir_curtida(ps.curtir(d, video))
        curtidos.append((None, ps.nome_do_produto(video)))
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

    # Os curtidos agora ficam em cima da lista: o 2º produto do vídeo procura entre os que
    # sobraram no topo. A tela final e o postar conferem o nome que a lista mostra, que pode
    # ser outro que o da API. Escolha do Rafael (P18): DECISOES.md, Shopee Vídeo.
    # Com a lista limpa (a limpeza anterior deu certo), o produto não é procurado rolando a
    # lista inteira; o topo continua conferido. Escolha do Rafael (P27): DECISOES.md, Shopee Vídeo.
    limpa = lista_limpa()
    anexados = []
    for i, nome in enumerate(nomes):
        seguir(d, CAMINHO_PRODUTO if i == 0 else CAMINHO_MAIS_UM_PRODUTO)
        _conferir(ps.adicionar_produto(d, dict(video, produto=nome), anexados, no_topo=len(nomes) - i,
                                       rolar_a_lista=not limpa))
        tocar(d, "Feito", 6)
    _conferir(ps.conferir_tela_final(d, dict(video, produtos=anexados)))
    atualizar(ident, produtos=anexados)
    # Antes do print: o Rafael vê no print a chave como vai ao ar.
    _conferir(ps.ajustar_rotulo_de_ia(d, bool(rotulo_ia)))

    print_tela = os.path.join(PASTA_RASCUNHOS, f"{ident}.png")
    d.screenshot(print_tela)
    tocar(d, "@tv_drafts_box", 12)
    if tem(tela(d), "@btn_post"):
        raise Parada("toquei em Rascunhos, mas o app continuou na tela final")
    atualizar(ident, estado="rascunho", print=print_tela)
    esperando = len(esperando_aprovacao())
    avisar(f"📝 Robô da Shopee Vídeo: rascunho novo salvo no celular. {esperando} esperando a sua aprovação "
           "em Shopee Vídeo 🎬 → Rascunhos do Robô 📝.")


PROCESSO_DA_EDICAO = "edição do vídeo: foto do produto e miniatura"
MOTIVO_SEM_EDICAO = "a edição do vídeo não saiu: só vídeo editado vai à Shopee Vídeo"


def copiar_para_o_rascunho(video, fonte, copia, nomes=()):
    """
    A cópia do vídeo que vai ao rascunho. Com a edição ligada, ela leva a foto do produto
    no começo, a miniatura e a seta (todos os vídeos do Rafael são autorais); no vídeo de
    Ver Produtos, a foto é a do 1º produto anexado (nomes[0]). Com a edição ligada, só vai
    vídeo editado: o que não sai editado fica de lado (Parada) e o robô pega o próximo; sem
    a foto do anúncio, o vídeo não volta, e o ffmpeg que falhou deixa tentar de novo depois.
    Escolhas do Rafael (25/10, P37, depois da P38, P39 e "só vídeos editados"): DECISOES.md,
    Shopee Vídeo.
    """
    if not edicao_video.vale_para(fonte):
        shutil.copyfile(video["arquivo"], copia)
        return
    if video.get("de_video"):
        foto = foto_do_ver_produtos(nomes[0]) if nomes else None
    else:
        foto = ps.foto_do_produto(video)
    motivo = edicao_video.editar(video["arquivo"], foto, copia)
    registro_processos.registrar(REGISTRO, PROCESSO_DA_EDICAO, "vídeo de lado" if motivo else "editado",
                                 motivo, ok=not motivo)
    if motivo:
        raise Parada(f"{MOTIVO_SEM_EDICAO} ({motivo})", do_video=motivo.startswith("a foto do anúncio"))


def foto_do_ver_produtos(nome):
    """
    A foto do anúncio do 1º produto anexado num vídeo de Ver Produtos (o link é do vídeo,
    não do produto): a API de afiliado busca pelo nome, por relevância, e vale a oferta de
    nome mais parecido, com pelo menos PARECIDO_DA_FOTO% das palavras. None quando não
    acha ou a foto não baixa: o vídeo fica de lado (só vídeo editado vai). A IA já conferiu esse produto
    com o vídeo. Escolha do Rafael (25/10, P39): DECISOES.md, Shopee Vídeo.
    """
    try:
        ofertas = asyncio.run(api_shopee.buscar_ofertas_shopee(termo_da_busca(nome), limite=OFERTAS_NA_BUSCA,
                                                               sort_type=1))
        parecidos = [(ps.parecido_entre([oferta.get("productName") or ""], nome)[0], i)
                     for i, oferta in enumerate(ofertas)]
        parecido, melhor = max(parecidos, default=(0, None))
        if melhor is None or parecido < PARECIDO_DA_FOTO:
            return None
        return ps.baixar_foto(ofertas[melhor].get("imageUrl") or "")
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] A foto do produto do Ver Produtos não veio: {type(e).__name__}")
        return None


def _esperar_a_pagina_do_produto(d, voltas=4):
    """
    Espera a página do produto abrir (uns 12 s), olhando a cada volta o aviso de loja de
    férias, que some em segundos. Produto de loja de férias não entra no Adicionar Produto
    do vídeo, mesmo curtido (24/10/2026, o teclado curtido às 14:25 não estava na lista):
    o vídeo fica de lado na hora, antes da galeria e do título.
    """
    for _ in range(voltas):
        pausa(2)
        if ps.loja_de_ferias(d, tela(d)):
            registro_processos.registrar(REGISTRO, "produto de loja de férias", "vídeo pulado", ok=None)
            raise Parada(MOTIVO_DE_FERIAS, do_video=True)


def _produtos_do_video(d, video, vistos, curtidos=None):
    """
    Link de vídeo (Ver Produtos): abre o vídeo no celular e, na lista do Ver Produtos (pelo
    "Ver Produtos (N)" ou, com um produto só, pela barra dele), cada produto que o criador vinculou (nunca as recomendações de "Você Também Pode Gostar"):
    lê o nome na página dele, a IA confere o vídeo com esse nome VEZES_DA_IA vezes, e o
    confirmado é curtido. Devolve os nomes confirmados; nenhum ou vídeo removido: o vídeo
    fica de lado. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    quantos = _abrir_ver_produtos(d, video)
    confirmados, de_ferias = [], 0
    for i in range(min(quantos, MAXIMO_PRODUTOS_DO_VIDEO)):
        xml = tela(d)
        pontos = ps.produtos_vinculados(xml)
        if i >= len(pontos):
            break
        if ps.proibido_no_ponto(xml, *pontos[i]):
            raise Parada(ps.RECUSA)
        ps.limpar_aviso_rapido(d)
        d.click(*pontos[i])
        pausa(8)
        xml = tela(d)
        nome = ps.nome_na_pagina_do_produto(xml)
        if ps.loja_de_ferias(d, xml):
            # Não entra no Adicionar Produto do vídeo: fica de fora, como o recusado pela IA.
            registro_processos.registrar(REGISTRO, "produto de loja de férias", "produto do Ver Produtos de fora",
                                         ok=None)
            de_ferias += 1
        elif nome and nome not in confirmados:
            deste = []
            ok, _ = ps.ia_confere_produto(dict(video, produto=nome), deste, avisar=False)
            if ok:
                _conferir_curtida(ps.curtir_na_pagina(d, xml))
                if curtidos is not None:
                    curtidos.append((i, nome))
                confirmados.append(nome)
                vistos.extend(deste)
        d.press("back")
        pausa(4)
    if not confirmados:
        raise Parada(MOTIVO_DE_FERIAS if de_ferias else "a IA não confirmou nenhum produto do Ver Produtos",
                     do_video=True)
    return confirmados


def _abrir_ver_produtos(d, video):
    """
    Abre o vídeo do link e a lista do Ver Produtos (pelo "Ver Produtos (N)" ou, com um
    produto só, pela barra dele). Devolve quantos produtos o criador vinculou.
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
    if tem(xml, "Ver Produtos"):
        tocar(d, "Ver Produtos", 6)
    else:
        # Vídeo com um produto só: no lugar do Ver Produtos, a barra com o nome dele, que
        # abre a mesma lista.
        barra = ps.barra_dos_produtos(xml)
        if not barra:
            raise Parada(_sem_ver_produtos(xml), do_video=True)
        if ps.proibido_no_ponto(xml, *barra):
            raise Parada(ps.RECUSA)
        d.click(*barra)
        pausa(6)
    quantos = len(ps.produtos_vinculados(tela(d)))
    if not quantos:
        raise Parada("o Ver Produtos não mostrou os produtos do criador", do_video=True)
    return quantos


def _sem_ver_produtos(xml):
    """
    Por que o vídeo não mostrou o Ver Produtos, em texto fixo, que o investigar_robo.yml
    mostra: o link não abriu o player, o player tem o cartão de um produto (com o botão
    de comprar) sem o Ver Produtos nem a barra dos produtos, ou nem isso.
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
    if not esperar_na_tela(d, "Rascunhos:", ESPERA_DOS_RASCUNHOS):
        raise Parada(f"o Perfil não tem nenhum rascunho salvo (o quadro Rascunhos não apareceu em "
                     f"{ESPERA_DOS_RASCUNHOS} s)")
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
    _conferir(ps.ajustar_rotulo_de_ia(d, bool(rascunho.get("rotulo_ia"))), do_video=False)
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


# --- Respostas aos comentários e o feed (interacoes_shopee_video) ---
# Pedidos do Rafael de 24/10/2026 (P9, P10 e P11): DECISOES.md, Shopee Vídeo. Cada
# resposta e cada comentário no feed é conferido na tela depois de enviado, entra no
# registro de processos (o checkup conta) e no Histórico do Robô; o que não se confirma
# para e não se repete às cegas.

# Quantas vezes o robô rola as Notificações procurando a linha do topo da vez anterior.
ROLADAS_NAS_RESPOSTAS = 6
# Respostas numa rodada (cada uma leva perto de 1 min); o resto fica para a rodada seguinte.
RESPOSTAS_POR_RODADA = 8
# O painel de comentários abre uns 8 s depois do vídeo (Motorola, 24/10/2026).
ESPERA_DOS_COMENTARIOS = 20
ROLADAS_NO_PAINEL = 4
ABA_DO_FEED = "Live e Vídeo"
ABA_PARA_VOCE = "Para você"
# Quantos vídeos do feed o robô passa, no máximo, procurando um para comentar.
VIDEOS_OLHADOS_NO_FEED = 12
# Os 3 comentários do dia no feed saem espalhados, não um atrás do outro.
INTERVALO_DO_FEED = timedelta(hours=2)
REGISTRO = "shopee_video"


def respostas_pendentes(agora=None):
    """
    Hora de responder os comentários? Uma vez por dia, e de novo na rodada seguinte
    quando a anterior parou no limite de RESPOSTAS_POR_RODADA.
    """
    estado = ler_estado()
    hoje = agora_br(agora).strftime("%Y-%m-%d")
    return bool(estado.get("respostas_continuar")) or not (estado.get("respostas_em") or "").startswith(hoje)


def feed_pendente(agora=None):
    """
    Falta comentar no feed hoje (3 por dia, P10), e o último foi há INTERVALO_DO_FEED ou mais?
    Num Horário das Interações curto, o intervalo encolhe para os 3 caberem nele.
    """
    inicio = agora_br(agora).strftime("%Y-%m-%d 00:00:00")
    if interacoes.quantos_desde("video_feed", interacoes.COMENTADOS_NO_FEED, inicio) >= \
            interacoes.COMENTARIOS_NO_FEED_POR_DIA:
        return False
    return (ler_estado().get("feed_em") or "") <= _momento(agora_br(agora) - intervalo_do_feed(ler_config()))


def interacoes_do_dia_feitas(agora=None):
    """As respostas e os comentários do feed de hoje já saíram todos? Aí o postar volta, mesmo na janela."""
    inicio = agora_br(agora).strftime("%Y-%m-%d 00:00:00")
    return not respostas_pendentes(agora) and interacoes.quantos_desde(
        "video_feed", interacoes.COMENTADOS_NO_FEED, inicio) >= interacoes.COMENTARIOS_NO_FEED_POR_DIA


def intervalo_do_feed(config):
    """INTERVALO_DO_FEED, ou a janela das interações dividida pelos comentários do dia, se for menor."""
    janela = janela_das_interacoes(config)
    if not janela:
        return INTERVALO_DO_FEED
    return min(INTERVALO_DO_FEED, timedelta(hours=janela[1] - janela[0]) / interacoes.COMENTARIOS_NO_FEED_POR_DIA)


def _ir_as_notificacoes(d):
    ir_ao_inicio(d)
    tocar(d, ABA_DAS_NOTIFICACOES, 6)
    tocar(d, FILTRO_DOS_VIDEOS, 5)


def _ler_notificacoes(d, topo=None):
    """
    As linhas das Notificações (filtro Lives, Vídeos e ...), de cima para baixo, rolando
    até achar a linha do topo da vez anterior (ou até ROLADAS_NAS_RESPOSTAS). Sem topo
    guardado, só a primeira tela.
    """
    _ir_as_notificacoes(d)
    linhas = []
    for vez in range(ROLADAS_NAS_RESPOSTAS + 1):
        novas = [t["texto"] for t in interacoes.linhas_das_notificacoes(tela(d), FILTRO_DOS_VIDEOS)
                 if t["texto"] not in linhas]
        linhas += novas
        if any(PENALIDADE in t.casefold() for t in novas):
            # O aviso de penalidade faz o robô ler a Saúde do Vídeo (saude_pedida_pela_notificacao).
            gravar_estado(penalidade_vista_em=_momento())
        if not topo or topo in map(interacoes.marca, linhas) or (vez and not novas):
            break
        ps.rolar(d)
        pausa(2)
    return linhas


def responder_comentarios(d, agora=None):
    """
    Responde os comentários novos dos vídeos do Rafael: lê as Notificações até a linha do
    topo da vez anterior e, do mais velho para o mais novo, abre cada "comentou no seu
    vídeo" e responde (_responder_um). Na primeira vez só guarda o topo (P11: só os novos).
    O topo só anda quando todos os comentários acima dele tiveram um fim: o que falhou volta
    na próxima vez.
    """
    estado = ler_estado()
    topo = estado.get("respostas_topo")
    linhas = _ler_notificacoes(d, topo)
    if not linhas:
        registro_processos.registrar(REGISTRO, "notificações (respostas)", "lista vazia", ok=None)
        return "respostas: nenhuma notificação"
    if not topo:
        for texto in linhas:
            if interacoes.comentario_da_notificacao(texto):
                interacoes.guardar(interacoes.marca(texto), "comentario", "anterior", agora)
        gravar_estado(respostas_topo=interacoes.marca(linhas[0]))
        registro_processos.registrar(REGISTRO, "notificações (respostas)", "topo guardado", ok=True)
        return "respostas: guardei o topo das notificações (respondo os que chegarem daqui em diante)"
    marcas = [interacoes.marca(t) for t in linhas]
    if topo in marcas:
        novas = linhas[:marcas.index(topo)]
        registro_processos.registrar(REGISTRO, "notificações (respostas)", "topo achado",
                                     f"{len(novas)} linha(s) nova(s)", ok=True)
    else:
        # A linha do topo sumiu ou ficou longe demais: vale tudo o que foi lido, e as marcas
        # evitam responder de novo o que já teve um fim.
        novas = linhas
        registro_processos.registrar(REGISTRO, "notificações (respostas)", "topo não achado",
                                     f"{len(linhas)} linha(s) lida(s)", ok=None)
    pendentes = [t for t in novas
                 if interacoes.comentario_da_notificacao(t) and not interacoes.terminado(interacoes.marca(t))]
    contagem, sobrou = {}, False
    for i, texto in enumerate(reversed(pendentes)):
        if i >= RESPOSTAS_POR_RODADA:
            sobrou = True
            break
        resultado = _responder_um(d, texto, agora)
        contagem[resultado] = contagem.get(resultado, 0) + 1
        pausa(random.uniform(4, 12))
    if not any(not interacoes.terminado(interacoes.marca(t)) for t in pendentes):
        gravar_estado(respostas_topo=marcas[0])
    gravar_estado(respostas_continuar=sobrou)
    if not pendentes:
        return "respostas: nenhum comentário novo"
    return "respostas: " + ", ".join(f"{n} {r}" for r, n in sorted(contagem.items())) + (
        "; o resto fica para a próxima rodada" if sobrou else "")


def _abrir_notificacao(d, texto):
    """Abre o vídeo pela linha da notificação (o texto exato), rolando a lista até ela."""
    _ir_as_notificacoes(d)
    for vez in range(ROLADAS_NAS_RESPOSTAS + 1):
        linha = next((t for t in interacoes.linhas_das_notificacoes(tela(d), FILTRO_DOS_VIDEOS)
                      if t["texto"] == texto), None)
        if linha:
            d.click(*linha["ponto"])
            pausa(4)
            return
        if vez < ROLADAS_NAS_RESPOSTAS:
            ps.rolar(d)
            pausa(2)
    raise Parada("a notificação do comentário não está mais na lista")


def _abrir_comentarios(d):
    """
    O painel de comentários do vídeo aberto pela notificação. Às vezes ele abre sozinho uns
    8 s depois do vídeo; outras, só o vídeo aparece (Motorola, 24/10/2026), e o robô toca no
    balão de comentários da coluna da direita.
    """
    if esperar_na_tela(d, "Comentários", ESPERA_DOS_COMENTARIOS // 2):
        return
    xml = tela(d)
    video = interacoes.video_do_feed(xml)
    if not video:
        raise Parada("o vídeo do comentário não abriu")
    if ps.proibido_no_ponto(xml, *video["balao"]):
        raise Parada(ps.RECUSA)
    d.click(*video["balao"])
    pausa(3)
    if not esperar_na_tela(d, "Comentários", ESPERA_DOS_COMENTARIOS // 2):
        raise Parada("o painel de comentários não abriu")


def _achar_no_painel(d, nome, comentario):
    """
    (tela, comentários do painel, posição do comentário da pessoa ou None), rolando o painel.
    Respostas escondidas ("Ver # respostas") embaixo dele são abertas uma vez, para o robô ver
    se o Rafael já respondeu.
    """
    abertas = False
    xml, painel, i = "", [], None
    for vez in range(ROLADAS_NO_PAINEL + 1):
        xml = tela(d)
        painel = interacoes.comentarios_do_painel(xml)
        i = interacoes.alvo_no_painel(painel, nome, comentario)
        if i is not None:
            escondidas = painel[i]["ver_respostas"] or next(
                (c["ver_respostas"] for c in interacoes.respostas_embaixo(painel, i) if c["ver_respostas"]), None)
            if escondidas and not abertas:
                d.click(*escondidas)
                pausa(3)
                abertas = True
                xml = tela(d)
                painel = interacoes.comentarios_do_painel(xml)
                i = interacoes.alvo_no_painel(painel, nome, comentario)
            return xml, painel, i
        if vez < ROLADAS_NO_PAINEL:
            ps.rolar(d)
            pausa(2)
    return xml, painel, None


def _fechar_teclado(d):
    """Fecha o teclado, se ele está na tela: o voltar sem teclado fecharia o painel."""
    if interacoes.teclado_aberto(tela(d)):
        d.press("back")
        pausa(2)


def _escrever_e_enviar(d, texto):
    """
    Escreve no campo em foco, confere o que ficou e toca no enviar ao lado. Para antes de
    enviar se o campo não mostra exatamente o texto.
    """
    ps.escrever(d, texto)
    pausa(2)
    campo = d(focused=True)
    escrito = campo.get_text() if campo.exists else ""
    if ps._normal(escrito) != ps._normal(texto):
        raise Parada("o texto não ficou no campo de escrever")
    xml = tela(d)
    campo_na_tela = interacoes.campo_de_escrever(xml)
    enviar = interacoes.botao_de_enviar(xml, campo_na_tela) if campo_na_tela else None
    if not enviar:
        raise Parada("não achei o botão de enviar ao lado do campo")
    if ps.proibido_no_ponto(xml, *enviar):
        raise Parada(ps.RECUSA)
    d.click(*enviar)
    pausa(4)
    _fechar_teclado(d)


def _responder_um(d, texto, agora=None):
    """
    Responde um comentário: abre o vídeo pela notificação, acha o comentário da pessoa no
    painel, confere que ninguém do perfil respondeu ainda, pede a resposta à IA, toca em
    Responder daquele comentário, escreve, envia e confere que a resposta ficou embaixo
    dele. Devolve o resultado ("respondido", "já respondido", "pulado", "lugar errado",
    "falhou" ou "desistiu").
    """
    marca = interacoes.marca(texto)
    nome, comentario = interacoes.comentario_da_notificacao(texto)
    produto = ""
    try:
        _abrir_notificacao(d, texto)
        _abrir_comentarios(d)
        xml, painel, i = _achar_no_painel(d, nome, comentario)
        if i is None:
            raise Parada("o comentário não está mais no vídeo")
        produto = interacoes.produto_do_painel(xml)
        respostas = interacoes.do_criador_embaixo(painel, i)
        if respostas:
            _guardar_o_perfil(painel, i)
            interacoes.guardar(marca, "comentario", "já respondido", agora)
            registro_processos.registrar(REGISTRO, "responder comentário", "já respondido",
                                         f"{respostas} resposta(s) do perfil", ok=None if respostas == 1 else False,
                                         origem=marca)
            return "já respondido"
        legenda = next((c["texto"] or c["nome"] for c in painel if c["criador"] and not c["resposta"]), "")
        anteriores = ler_estado().get("respostas_textos") or []
        resposta = asyncio.run(interacoes.gerar_resposta(comentario, produto, legenda, anteriores))
        if resposta is None:
            raise Parada("a IA não escreveu a resposta")
        if not resposta:
            interacoes.guardar(marca, "comentario", "pulado", agora)
            registro_processos.registrar(REGISTRO, "responder comentário", "pulado pela IA",
                                         "ofensivo, golpe ou propaganda", ok=None, origem=marca)
            registrar_tentativa("responder", "pulado", "a IA achou o comentário ofensivo, golpe ou propaganda",
                                produto, agora)
            avisar(f"💬 Robô da Shopee Vídeo: não respondi um comentário no vídeo de {produto or 'um produto'}: "
                   "a IA achou ofensivo, golpe ou propaganda. Se quiser, responda à mão.")
            return "pulado"
        if not painel[i]["responder"]:
            raise Parada("não achei o Responder do comentário")
        d.click(*painel[i]["responder"])
        pausa(3)
        campo = interacoes.campo_de_escrever(tela(d))
        if not campo or not ps._normal(campo["texto"]).startswith("respond"):
            raise Parada("o Responder não abriu o campo da resposta")
        _escrever_e_enviar(d, resposta)
        xml, painel, i = _achar_no_painel(d, nome, comentario)
        lugar = interacoes.onde_ficou(painel, i, resposta)
        if lugar == "embaixo":
            _guardar_o_perfil(painel, i)
            interacoes.guardar(marca, "comentario", "respondido", agora)
            gravar_estado(respostas_textos=(anteriores + [resposta])[-10:])
            registro_processos.registrar(REGISTRO, "responder comentário", "respondido", ok=True, origem=marca)
            registrar_tentativa("responder", "respondido", produto=produto, agora=agora)
            return "respondido"
        if lugar == "outro lugar":
            # Erro grave (P12): a resposta foi parar embaixo de outro comentário ou solta.
            interacoes.guardar(marca, "comentario", "lugar errado", agora)
            registro_processos.registrar(REGISTRO, "responder comentário", "resposta no lugar errado", ok=False,
                                         origem=marca)
            registrar_tentativa("responder", "parou", "a resposta não ficou embaixo do comentário certo", produto,
                                agora)
            avisar(f"⚠️ Robô da Shopee Vídeo: a resposta a um comentário no vídeo de {produto or 'um produto'} "
                   f"não ficou embaixo do comentário certo. Confira no app e apague à mão se precisar: "
                   f"\"{resposta}\". Não vou responder esse comentário de novo.")
            return "lugar errado"
        raise Parada("a resposta não apareceu embaixo do comentário")
    except Parada as e:
        # Na próxima vez, o robô confere de novo se o perfil já respondeu antes de responder:
        # uma resposta que saiu sem aparecer na tela não vira duas.
        tentativas = interacoes.guardar_falha(marca, "comentario", agora)
        registro_processos.registrar(REGISTRO, "responder comentário", "parou", e.motivo, ok=False, origem=marca)
        registrar_tentativa("responder", "parou", e.motivo, produto, agora)
        if tentativas < interacoes.TENTATIVAS_DO_COMENTARIO:
            return "falhou"
        interacoes.guardar(marca, "comentario", "desistiu", agora)
        registro_processos.registrar(REGISTRO, "responder comentário", "sem resposta",
                                     f"{tentativas} tentativa(s)", ok=False, origem=marca)
        avisar(f"⚠️ Robô da Shopee Vídeo: tentei {tentativas} vezes e não consegui responder o comentário de "
               f"{nome} no vídeo de {produto or 'um produto'} ({e.motivo}). Ele fica para você responder à mão.")
        return "desistiu"
    finally:
        _sair_sem_salvar(d)


def _guardar_o_perfil(painel, i):
    """A marca do nome do perfil do Rafael (o da resposta com o selo Criador), para o feed pular os vídeos dele."""
    dono = next((c["nome"] for c in interacoes.respostas_embaixo(painel, i) if c["criador"] and c["nome"]), "")
    if dono:
        gravar_estado(conta_marca=interacoes.marca(dono))


def _proprio(video):
    """O vídeo do feed é do próprio Rafael? Pelo nome do perfil (visto nas respostas) ou pelo título postado."""
    conta = ler_estado().get("conta_marca")
    if conta and interacoes.marca(video["autor"]) == conta:
        return True
    return any(interacoes.parecidos(r["titulo"] or "", video["legenda"]) for r in listar("postado") if r["titulo"])


def _curtir_no_feed(d, video):
    """Curte o vídeo pelo coração da coluna da direita e confere que ficou curtido."""
    if interacoes.coracao_curtido(video["coracao_desc"]):
        return
    xml = tela(d)
    if ps.proibido_no_ponto(xml, *video["coracao"]):
        raise Parada(ps.RECUSA)
    d.click(*video["coracao"])
    pausa(2)
    depois = interacoes.video_do_feed(tela(d))
    curtido = interacoes.coracao_curtido(depois["coracao_desc"]) if depois else None
    if not depois or curtido is False or (curtido is None and depois["coracao_desc"] == video["coracao_desc"]):
        registro_processos.registrar(REGISTRO, "feed: curtir", "não curtiu", ok=False)
        raise Parada("o toque no coração do vídeo do feed não curtiu")
    registro_processos.registrar(REGISTRO, "feed: curtir", "curtido", ok=True)


def painel_de_comentarios(d, segundos=12):
    """
    A tela com o painel de comentários aberto, relendo por até `segundos`, ou None. Vale o
    título ("N Comentários", "0 Comentário"), o campo de comentar ou o de escrever: no vídeo
    sem nenhum comentário, o painel abre com "0 Comentário" e já escrevendo (Motorola, 25/10/2026).
    """
    voltas = max(1, segundos // 3)
    for volta in range(voltas + 1):
        xml = tela(d)
        if interacoes.campo_de_comentar(xml) or interacoes.campo_de_escrever(xml) or tem(xml, "Comentário"):
            return xml
        if volta < voltas:
            pausa(3)
    return None


def _comentar_no_feed(d, video, texto):
    """
    Abre os comentários pelo balão, escreve e envia. Devolve se o comentário apareceu na
    lista; antes de enviar, o que não dá certo para (Parada).
    """
    xml = tela(d)
    if ps.proibido_no_ponto(xml, *video["balao"]):
        raise Parada(ps.RECUSA)
    d.click(*video["balao"])
    pausa(3)
    xml = painel_de_comentarios(d)
    if not xml:
        raise Parada("o painel de comentários do vídeo do feed não abriu")
    # No vídeo sem nenhum comentário, o painel já abre com o campo de escrever em foco e o
    # teclado ("Adicionar um comentário...", Motorola, 25/10/2026): escreve direto.
    if not interacoes.campo_de_escrever(xml):
        campo = interacoes.campo_de_comentar(xml)
        if not campo:
            raise Parada("não achei o campo de comentar no vídeo do feed")
        d.click(*campo)
        pausa(2)
        if not interacoes.campo_de_escrever(tela(d)):
            raise Parada("o campo de comentar não abriu")
    _escrever_e_enviar(d, texto)
    for vez in range(2):
        if any(interacoes.parecidos(c["texto"], texto) for c in interacoes.comentarios_do_painel(tela(d))):
            return True
        if not vez:
            ps.rolar(d, para_cima=True)
            pausa(2)
    return False


def interagir_no_feed(d, agora=None):
    """
    Live e Vídeo → Para você: passa as lives, olha uns vídeos e, num vídeo de outro criador
    que ainda não comentou, curte e comenta (texto da IA, diferente dos anteriores). Um
    vídeo por rodada; os 3 do dia saem espalhados (feed_pendente). Pedido do Rafael (P10).
    """
    ir_ao_inicio(d)
    tocar(d, ABA_DO_FEED, 8)
    tocar(d, ABA_PARA_VOCE, 6)
    # Comenta o 1º, o 2º ou o 3º vídeo que der: não sempre o primeiro que aparece.
    pular = random.randint(0, 2)
    anteriores = ler_estado().get("feed_textos") or []
    try:
        for _ in range(VIDEOS_OLHADOS_NO_FEED):
            # Cada tela olhada fica no registro com o que o robô viu nela (um texto fixo):
            # o checkup mostra onde ele se perde quando nenhum vídeo serve.
            video, motivo = interacoes.ler_o_feed(tela(d))
            marca = interacoes.marca(video["autor"], video["legenda"]) if video else None
            if not video:
                visto = "live pulada" if motivo == "live" else f"pulada: {motivo}"
            elif interacoes.resultado_de(marca, "video_feed"):
                visto = "já comentado antes"
            elif _proprio(video):
                visto = "vídeo do próprio perfil"
            else:
                pausa(random.uniform(6, 14))  # assiste um pouco antes
                if not pular:
                    registro_processos.registrar(REGISTRO, "feed: vídeo olhado", "escolhido", ok=None)
                    return _interagir_com(d, video, marca, anteriores, agora)
                pular -= 1
                visto = "deixado passar"
            registro_processos.registrar(REGISTRO, "feed: vídeo olhado", visto, ok=None)
            pausa(random.uniform(2, 6))
            ps.rolar(d)
            pausa(4)
        registro_processos.registrar(REGISTRO, "feed: comentar", "nenhum vídeo para comentar", ok=None)
        return "feed: nenhum vídeo para comentar"
    except Parada as e:
        # O caso guarda a tela de agora (o painel que não abriu, por exemplo), antes de sair.
        _guardar_caso(d, "feed", "parou", e.motivo, agora=agora)
        e.caso_guardado = True
        raise
    finally:
        _sair_sem_salvar(d)


def _interagir_com(d, video, marca, anteriores, agora=None):
    texto = asyncio.run(interacoes.gerar_comentario(video["legenda"], anteriores))
    if texto is None:
        raise Parada("a IA não escreveu o comentário do feed")
    if not texto:
        interacoes.guardar(marca, "video_feed", "pulado", agora)
        registro_processos.registrar(REGISTRO, "feed: comentar", "pulado pela IA", ok=None, origem=marca)
        return "feed: a IA pulou o vídeo"
    _curtir_no_feed(d, video)
    try:
        apareceu = _comentar_no_feed(d, video, texto)
    except Parada as e:
        registro_processos.registrar(REGISTRO, "feed: comentar", "parou", e.motivo, ok=False, origem=marca)
        raise
    gravar_estado(feed_textos=(anteriores + [texto])[-10:])
    if not apareceu:
        # Enviado sem aparecer: pode ter saído, então o vídeo não volta e conta no dia.
        interacoes.guardar(marca, "video_feed", "não confirmado", agora)
        registro_processos.registrar(REGISTRO, "feed: comentar", "não confirmado", "enviado sem aparecer na lista",
                                     ok=False, origem=marca)
        registrar_tentativa("feed", "parou", "o comentário não apareceu no vídeo do feed", agora=agora)
        return "feed: comentário enviado sem aparecer na lista"
    interacoes.guardar(marca, "video_feed", "comentado", agora)
    registro_processos.registrar(REGISTRO, "feed: comentar", "comentado", ok=True, origem=marca)
    registrar_tentativa("feed", "comentado", agora=agora)
    return "feed: 1 vídeo curtido e comentado"


# --- A rodada ---

# A pausa que o robô faz sozinho quando perde o celular (robo_pausa_motivo); o painel a
# mostra diferente da pausa do botão.
MOTIVO_DA_DESCONEXAO = "celular desconectado"


def pausar_por_desconexao(motivo):
    """
    Sem o celular, a Postagem pausa sozinha (o botão vira Retomar Postagem ▶️) e o modo
    assistente volta a mandar as postagens no privado, para o Rafael postar à mão.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    db.atualizar_config(CHAVE_CONFIG, lambda dados: dados.update(robo_pausado=True,
                                                                robo_pausa_motivo=MOTIVO_DA_DESCONEXAO))
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
            # Pausa do Rafael: os horários que passam nela são pulados. Pausa sozinha, por
            # desconexão: ficam, e na volta do celular contam como um só, como com o robô fora
            # do ar. Escolha do Rafael (24/10, P16): DECISOES.md, Shopee Vídeo.
            if config.get("robo_pausa_motivo") != MOTIVO_DA_DESCONEXAO:
                consumir_horarios(config, agora)
            return "pausado"
        if suspensa(config, agora):
            # Os horários de rascunho que passam na suspensão são pulados, como pausado: o
            # preparo e a postagem esperam o fim (o_que_fazer), e o resto segue.
            consumir_horarios(config, agora)
        if not no_horario(config, agora):
            return "fora do Horário do Robô"
    elif suspensa(config, agora) and not saude:
        ate = quando_acaba(suspenso_ate(config))
        avisar(f"⛔ Robô da Shopee Vídeo: não {'preparei o rascunho' if preparar else 'testei o caminho'}. A conta "
               f"de Shopee Vídeo está suspensa pela Shopee até {ate}, e até lá o Postar vídeo não abre: o "
               "robô não prepara, não posta e não testa o caminho (o resto continua).")
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
        # Dentro da trava, nenhum preparo está rodando: o "preparando" antigo é de uma rodada morta.
        soltar_preparos_interrompidos(agora)
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
        if acao == "descurtir":
            # A lista só fica limpa se este descurtir chegar ao fim (P27).
            gravar_estado(descurtir_em=_momento(agora), descurtir_continuar=False, favoritos_limpos=False)
            resultado = descurtir_tudo(d, agora)
            registrar_tentativa("descurtir", "descurtido", agora=agora)
            return resultado
        if acao == "responder":
            gravar_estado(respostas_em=_momento(agora), respostas_continuar=False)
            return responder_comentarios(d, agora)
        if acao == "feed":
            gravar_estado(feed_em=_momento(agora))
            return interagir_no_feed(d, agora)
        if acao == "apagar":
            resultado = apagar_do_app(d, pegar(ident))
            registrar_tentativa("apagar", "apagado", produto=produto, agora=agora)
            return resultado
        if acao == "postar":
            resultado = publicar(d, pegar(ident), agora)
            registrar_tentativa("postar", "postado", produto=produto, agora=agora)
            return resultado
        if not preparar:
            _em_preparo(config, agora, True)
        try:
            resultado = preparar_rascunho(d, config, agora)
        finally:
            if not preparar:
                _em_preparo(config, agora, False)
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
            _guardar_caso(d, acao, "verificação", "verificação da Shopee na tela", ident=ident, agora=agora)
            registrar_tentativa(acao, "verificação", "verificação da Shopee na tela", produto, agora)
        av.abrir_tela(celular=True, verificacao=True)
        return f"{acao}: verificação na tela; parado"
    except Parada as e:
        if acao != "rascunho" and not e.caso_guardado:
            _guardar_caso(d, acao, "parou", e.motivo, ident=ident, agora=agora)
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
            _guardar_caso(d, acao, "erro", f"erro inesperado ({type(e).__name__})", ident=ident, agora=agora)
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
           "Até lá o robô não prepara nem posta (o Postar vídeo fica fechado), o modo assistente espera, e não "
           "chegam avisos de rascunho que não saiu. Os rascunhos aprovados ficam guardados e saem depois, "
           "espalhados. O resto continua no horário de sempre: a limpeza dos favoritos às 4h, as respostas aos "
           "comentários, o feed e a Saúde do Vídeo (com o celular fora da tomada, o robô só pula, sem avisar).\n\n"
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

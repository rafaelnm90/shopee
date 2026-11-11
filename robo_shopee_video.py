#!/usr/bin/env python3
"""
Robô automático da Shopee Vídeo: no celular guardado do Rafael (celular_robo.py), prepara
rascunhos sozinho e posta os que o Rafael aprova no bot (Shopee Vídeo 🎬 → Rascunhos do
Robô 📝, no painel_shopee_video.py). Usa os passos e as conferências do explorar
(postador_shopee_video.py): a IA confere o produto do link com o vídeo; no link de produto,
a busca pela foto do app acha o mesmo item em outras lojas para os espaços livres, até 6
produtos (P59); cada produto é achado no topo de Minhas Curtidas (pelo nome parecido ou,
por último, pela foto conferida pela IA) e a tela final é conferida antes de salvar e de
postar. No fim de cada rascunho, salvo ou não, descurte os produtos que curtiu para ele.

O painel (bot_mestre) chama uma rodada a cada 15 min, num processo à parte: o robô passa
minutos tocando no celular, e a IA dele não pode dividir a conexão com a do bot.

    python3 robo_shopee_video.py --rodada
    python3 robo_shopee_video.py --treino      # o treino na hora (botão Testar Caminho 🧭)
    python3 robo_shopee_video.py --preparar    # um rascunho na hora (botão Preparar 1 Agora ⚡)
    python3 robo_shopee_video.py --saude       # a Saúde do Vídeo na hora (botão Gerar Apelação ⚖️)
    python3 robo_shopee_video.py --postar ID   # o aprovado na hora (botão Postar Agora 🚀, P138)
    python3 robo_shopee_video.py --fazer       # o pedido do Fazer Agora ⏩ que espera (P162 1)
    python3 robo_shopee_video.py --print-do-rascunho [AAAA-MM-DDTHH:MM]   # o print do rascunho mais novo no privado

Cada rodada faz no máximo uma coisa, nesta ordem, sem hora marcada: cada uma sai na 1ª rodada em
que pode (P161 1):
0. às 4h, a 1ª coisa do dia, descurte tudo em Meus favoritos (Criadores & Afiliados), uma vez por
   dia (P25): enquanto ela não acaba, a hora é só dela; acabada, fica livre. A que não termina na
   hora volta no mesmo dia, na 1ª rodada livre (P137);
1. o treino da semana, na primeira rodada de segunda-feira: percorre o caminho até a tela
   final sem salvar nem postar e confere cada tela com o mapa (os CAMINHOs abaixo);
2. apaga no app um rascunho que o Rafael recusou;
3. posta um rascunho aprovado cuja hora chegou: os aprovados saem um de cada vez, com um
   intervalo sorteado entre eles, sempre dentro do Horário do Robô;
4. prepara um rascunho novo quando um horário do plano do dia passou: cada dia sorteia
   quantos (a faixa Rascunhos por Dia) e espalha os horários pelo Horário do Robô;
5. responde os comentários novos dos vídeos do Rafael, 3 vezes por dia, das 8h às 22h, com pelo
   menos 3 h entre uma leitura e outra (P70 e P161 1; Notificações → Lives, Vídeos e ...; o texto
   é da IA e cada resposta é conferida embaixo do comentário);
6. comenta num post antigo dele, 1 vez por dia, das 8h às 22h (P148 2);
7. curte um vídeo de outro criador no feed Live e Vídeo → Para você e, quando a IA tem algo
   específico a dizer, comenta nele: até 5 por dia, um por rodada, espalhados pelo Horário do
   Robô; o que falha tenta de novo na rodada seguinte (P151 1 e P152; interacoes_shopee_video.py).
Pausado (Pausar Postagem ⏸️), fora do Horário do Robô, com a tela do celular aberta no
privado do Rafael ou com o explorar tocando nele, não toca em nada. Celular desconectado:
tenta reconectar sozinho (celular_robo.reconectar_sozinho); sem conseguir, pausa a
Postagem e avisa, e o modo assistente volta a mandar as postagens no privado até o
Rafael tocar em Retomar Postagem ▶️. Com a tela do celular apagada, para antes de começar,
sem tocar em nada, com a carga e o Manter ativado no motivo (conferir_a_tela_acesa). Na
Verificação da Shopee para na hora e manda o link da tela do celular no privado. Com a conta de Shopee Vídeo suspensa pela Shopee (o
aviso fica nas Notificações do app), não prepara, não posta e não treina até o fim da
suspensão (o Postar vídeo fica fechado), e o modo assistente espera junto; o resto segue
no horário de sempre, e com o celular fora da tomada só pula. No fim, os dois voltam
sozinhos (painel_shopee_video), e o treino da segunda que caiu na suspensão roda primeiro.

Nunca toca em Postar sem o Aprovar do Rafael no bot, nem nos botões de comprar. Depois de
postar, curte o próprio vídeo, comenta nele e curte o comentário (P148 2); o que não sai (e o
link do post que não saiu, buscar_o_link_de_novo) volta nas rodadas seguintes. No log, só
estados e números: nada de nome de produto, título ou link.
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import asyncio
import html
import io
import itertools
import json
import logging
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
from collections import namedtuple
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
import pedidos_do_canal
import postador_shopee_video as ps
import registro_processos
import videos
import visualizacoes_shopee_video as visualizacoes
from api_shopee import eh_video, link_para_converter
from fuso import fuso_horario
from legendas import nome_da_legenda

logger = logging.getLogger("RoboShopeeVideo")

CHAVE_CONFIG = "shopee_video"  # a mesma chave do painel_shopee_video
# Começa pausado: o Rafael retoma no painel. Rascunhos por dia em faixa (sorteada a cada
# dia) e o Horário do Robô, em horas de Brasília.
# robo_produtos_a_mais: os espaços livres com o mesmo item de outras lojas (P59), ligados
# até o Rafael desligar no painel ou uma punição por produto parar (P73).
PADRAO = {"robo_pausado": True, "robo_limite_min": 1, "robo_limite_max": 2,
          "robo_inicio": ps.HORARIO_DAS_RODADAS[0], "robo_fim": ps.HORARIO_DAS_RODADAS[1],
          "robo_produtos_a_mais": True}
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
# Em 10/11, o título de um rascunho levou 15 min (das 06:59 às 07:14), e a rodada passou do
# limite dela sem dizer onde o tempo foi. Os textos da IA que passam deste tempo (segundos) vão ao
# registro com o tempo de cada parte (api_gemini.TEMPOS_DA_IA: o envio do vídeo, o processamento
# no Google, as respostas dos modelos) e o que ficou fora da IA (a pausa entre as tentativas).
LENTIDAO_DA_IA = 120
# Vídeo de produto sem oferta de afiliado (não paga comissão) fica de lado antes de tocar
# no celular; numa rodada, até estes. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
VIDEOS_SEM_OFERTA_POR_RODADA = 5
SEM_OFERTA = "o link não diz o produto do vídeo (produto sem oferta de afiliado)"
# O produto que já foi ao ar (ou vai) não se repete: o vídeo dele fica de lado antes do rascunho e o
# robô passa ao próximo da fonte (produtos_ja_postados). Escolha do Rafael (06/11, P166 1):
# DECISOES.md, Shopee Vídeo.
PRODUTO_JA_POSTADO = "o produto deste vídeo já foi postado (pelo robô ou pelo assistente)"
# Onde estava o produto do vídeo que ficou de lado por já ter sido postado: o registro diz só o
# rótulo fixo e quem deixou de lado, para o checkup conferir que o produto foi ou vai mesmo ao ar
# (anotar_onde_ja_foi; P166 1 e P167 1).
PROCESSO_DO_JA_POSTADO = "produto do vídeo: já postado, onde estava"
ONDE_JA_FOI = {"rascunho": "rascunho do robô esperando a aprovação", "aprovado": "aprovado no robô",
               "postado": "postado pelo robô"}
POSTEI_NO_ASSISTENTE, EM_NENHUM = "marcado com Postei ✅ no assistente", "em nenhum"
# Produtos do Ver Produtos que o robô confere num vídeo (cada um custa 2 conferências da IA).
MAXIMO_PRODUTOS_DO_VIDEO = 6
# O mesmo produto com mais comissão (P33): a busca da API por maior comissão traz até
# estes, entram só os de nome parecido (PARECIDO_NA_BUSCA% das palavras do nome do link),
# e a IA confere com o vídeo até CANDIDATOS_NA_IA deles (cada um custa até 2 conferências).
# A busca usa as primeiras PALAVRAS_DA_BUSCA palavras do nome: o nome inteiro traz pouco.
# "Paga mais" é o que o Rafael recebe numa venda, o preço vezes a comissão, e só entra
# anúncio até MAIS_CARO_NA_TROCA% mais caro que o do link: o bem mais caro paga mais por
# venda, mas vende menos (P58).
OFERTAS_NA_BUSCA = 20
PARECIDO_NA_BUSCA = 60
CANDIDATOS_NA_IA = 2
PALAVRAS_DA_BUSCA = 6
MAIS_CARO_NA_TROCA = 20
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

# Estados de um rascunho: o que ainda está no app do celular e o que já saiu dele. "refazer": o
# rascunho editado (Editar ✏️) e aprovado, que o robô refaz no app com a nova versão do vídeo antes de
# ir ao ar (P192 1).
NO_APP = ("rascunho", "aprovado", "recusado", "refazer")

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
# Desde 04/11/2026 (vídeo do Rafael), o Centro do criador abre como "Creator Center", sem o
# quadro Saúde do Vídeo: no alto ficam "Ao vivo: ..." e "Vídeo: ..." (a situação de cada um),
# e o "Vídeo: ..." abre a Account Health, com as abas Live e Vídeo. A aba Vídeo traz o mesmo de
# antes (o aviso de suspensão, o Ponto de Penalidade e os Vídeos de Violação); a Live tem os
# pontos das lives, que não contam aqui. O robô aceita as duas telas: o app do Motorola pode
# atualizar depois do celular do Rafael.
ENTRADA_DA_SAUDE = ("vídeo:", "video:")
ABA_DO_VIDEO = "Vídeo"
NA_ABA_DA_LIVE = ("Lives com Violação", "Status de Saúde da Live")
STATUS_DO_VIDEO = "status da saúde do vídeo"
# A página carrega pela rede e mostra os títulos antes do número: sem o número, a suspensão e a
# lista podem estar pela metade, e o robô não tira conclusão nenhuma dela.
MOTIVO_SEM_OS_PONTOS = "a Saúde do Vídeo abriu sem o número do Ponto de Penalidade"
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
    antes_de_comecar=True: a ação nem começou (a tela apagada, conferir_a_tela_acesa).
    """

    def __init__(self, motivo, do_video=False):
        super().__init__(motivo)
        self.motivo, self.do_video, self.caso_guardado = motivo, do_video, False
        self.antes_de_comecar = False


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


def no_horario_do_robo(config, agora=None):
    """Agora está no Horário do Robô do painel?"""
    return config["robo_inicio"] <= agora_br(agora).hour < config["robo_fim"]


def no_horario(config, agora=None):
    """O robô pode rodar agora: no Horário do Robô ou na hora do descurtir."""
    return no_horario_do_robo(config, agora) or na_hora_do_descurtir(agora)


# A limpeza de Meus favoritos (os produtos curtidos para o Adicionar Produto, a lista de afiliado) é a
# 1ª coisa do dia, às 4h, de madrugada (P25): nessa hora, enquanto ela não acaba, o robô não prepara,
# não posta e não interage. Acabada, o resto da hora fica livre como as outras do Horário do Robô.
# Escolhas do Rafael (24/10, P25, e 06/11, P161 1): DECISOES.md, Shopee Vídeo.
HORA_DO_DESCURTIR = 4
# Com um aprovado indo ao ar nesse tempo (o das rodadas), a rodada não começa tarefa longa:
# a seguinte já pega o post na hora. Escolha do Rafael (P30): DECISOES.md, Shopee Vídeo.
ANTES_DO_POST = timedelta(minutes=15)


def na_hora_do_descurtir(agora=None):
    return agora_br(agora).hour == HORA_DO_DESCURTIR


def descurtir_pendente(agora=None):
    """
    Falta descurtir tudo hoje? Uma vez por dia, e de novo na rodada seguinte (na mesma
    hora) quando a anterior parou depois de VOLTAS_DO_DESCURTIR voltas ou parou no meio (a
    tela que não abriu, o app travado, um erro: _agir). A Verificação da Shopee para tudo, sem
    tentar de novo.
    """
    estado = ler_estado()
    hoje = agora_br(agora).strftime("%Y-%m-%d")
    return bool(estado.get("descurtir_continuar")) or not (estado.get("descurtir_em") or "").startswith(hoje)


# A limpeza de hoje que não terminou na hora dela (o celular fora às 4h, o app travado nas 4
# rodadas da hora, as voltas que acabaram) roda de novo no mesmo dia, na 1ª rodada livre, sem
# segurar um post (o_que_fazer), até LIMPEZAS_FORA_DA_HORA vezes por dia. Escolha do Rafael
# (02/11, P137 1): DECISOES.md, Shopee Vídeo.
LIMPEZAS_FORA_DA_HORA = 2
FORA_DA_HORA = "fora da hora"


def limpeza_fora_da_hora_pendente(agora=None):
    """A limpeza de hoje não terminou na hora dela, já passou a hora, e ainda cabe uma vez fora dela?"""
    momento = agora_br(agora)
    if momento.hour <= HORA_DO_DESCURTIR or not descurtir_pendente(agora):
        return False
    fora = ler_estado().get("descurtir_fora") or {}
    return fora.get("dia") != momento.strftime("%Y-%m-%d") or int(fora.get("vezes") or 0) < LIMPEZAS_FORA_DA_HORA


def _contar_limpeza_fora_da_hora(agora=None):
    """Mais uma limpeza fora da hora dela no dia (a conta de LIMPEZAS_FORA_DA_HORA)."""
    dia = agora_br(agora).strftime("%Y-%m-%d")
    fora = ler_estado().get("descurtir_fora") or {}
    vezes = int(fora.get("vezes") or 0) + 1 if fora.get("dia") == dia else 1
    gravar_estado(descurtir_fora={"dia": dia, "vezes": vezes})


def anotar_limpeza_sem_celular(agora=None, resultado="celular fora na suspensão"):
    """
    Na suspensão, com o celular fora da tomada, a limpeza das 4h não roda (pedido do
    Rafael: DECISOES.md, Shopee Vídeo); com o robô pausado (por ele, ou sozinho sem o
    celular), também não. Fica no registro uma vez por dia, com o porquê (resultado), para
    o checkup mostrar o motivo em vez de cobrar a limpeza que faltou.
    """
    if not na_hora_do_descurtir(agora) or not descurtir_pendente(agora):
        return
    hoje = agora_br(agora).strftime("%Y-%m-%d")
    if ler_estado().get("descurtir_sem_celular") == hoje:
        return
    gravar_estado(descurtir_sem_celular=hoje)
    registro_processos.registrar(REGISTRO, "descurtir tudo (4h)", resultado, ok=None, agora=agora)
    # A de Meus Favoritos (comprador) vem junto com a das 4h (P137 1): o mesmo porquê, para o
    # checkup não cobrá-la como esquecida.
    registro_processos.registrar(REGISTRO, PROCESSO_DE_COMPRADOR, resultado, ok=None, agora=agora)


# A rodada da hora do descurtir que não chega à limpeza ainda por fazer (o celular com outra
# rodada ou com o explorar, a tela do celular aberta no privado) fica no registro com o porquê,
# como a do robô pausado (anotar_limpeza_sem_celular): o checkup diz por que a limpeza não rodou
# na hora. Só o motivo fixo do código.
PROCESSO_SEM_LIMPEZA = "hora do descurtir: rodada sem a limpeza"


def anotar_rodada_sem_limpeza(motivo, agora=None):
    """Na hora do descurtir, com a limpeza de hoje por fazer, a rodada que não chegou a ela (o motivo)."""
    if na_hora_do_descurtir(agora) and descurtir_pendente(agora):
        registro_processos.registrar(REGISTRO, PROCESSO_SEM_LIMPEZA, motivo, ok=None, agora=agora)


def trechos_de_postar(config):
    """
    Os trechos do dia, em minutos (início, fim), em que o robô prepara e posta: o Horário do Robô
    inteiro. A hora do descurtir também entra: o horário que cai nela espera a limpeza acabar
    (o_que_fazer). Escolha do Rafael (06/11, P161 1): DECISOES.md, Shopee Vídeo.
    """
    inicio, fim = config["robo_inicio"] * 60, min(config["robo_fim"] * 60, 24 * 60 - 1)
    return [(inicio, fim)] if fim > inicio else []


def pontos_do_dia(dia):
    """Os pontos de penalidade que valem para o plano do dia (os lidos antes do trimestre valem 0)."""
    momento = datetime.strptime(dia, "%Y-%m-%d").replace(hour=12, tzinfo=fuso_horario)
    return apelacoes.pontos_de_agora(ler_estado(), momento)


def quantos_hoje(config, dia):
    """
    Quantos rascunhos o dia faz: o sorteio na faixa do painel e, com 4 pontos de penalidade ou
    mais, a parte dela com o teto da escada (P144 e P145; os pontos lidos antes do trimestre
    valem 0). Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    return apelacoes.quantos_pelos_pontos(CHAVE_ESTADO, dia, config["robo_limite_min"], config["robo_limite_max"],
                                          pontos_do_dia(dia))


def feito_com(config, dia):
    """
    Com o que o plano do dia é feito: a faixa do painel e os pontos daquela hora. Fica no plano
    para o checkup e o painel mostrarem quando o que vale agora já não é o do plano.
    """
    return {"faixa": [config["robo_limite_min"], config["robo_limite_max"]], "pontos": pontos_do_dia(dia)}


ESTADOS_SALVOS = ("rascunho", "aprovado", "postado", "recusado", "apagado")


def _criados_hoje(estados, agora=None):
    """Os rascunhos nesses estados criados hoje; a versão de antes de um rascunho refeito no app não conta."""
    hoje = agora_br(agora).strftime("%Y-%m-%d")
    return [r for r in listar(*estados) if (r["criado_em"] or "").startswith(hoje) and not r["versao_de"]]


def rascunhos_de_hoje(agora=None):
    """Os rascunhos salvos hoje (o do Preparar 1 Agora também), para o aviso do teto pelos pontos."""
    return len(_criados_hoje(ESTADOS_SALVOS, agora))


def postados_de_hoje(agora=None):
    """Os posts de hoje, para o aviso do teto pelos pontos no Postar Agora."""
    hoje = agora_br(agora).strftime("%Y-%m-%d")
    return sum(1 for r in listar("postado") if (r["postado_em"] or "").startswith(hoje))


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


def estado_do_dia(config, agora=None):
    """O plano de hoje ({data, horarios, feitos, feito_com}), refeito quando o dia muda."""
    dia = agora_br(agora).strftime("%Y-%m-%d")
    estado = db.ler_config(CHAVE_DIA, {}) or {}
    if estado.get("data") != dia:
        estado = {"data": dia, "horarios": planejar(config, dia), "feitos": 0, "feito_com": feito_com(config, dia)}
        db.salvar_config(CHAVE_DIA, estado)
    return estado


def horarios_vencidos(estado, agora=None):
    hora = agora_br(agora).strftime("%H:%M")
    return sum(1 for h in estado["horarios"] if h <= hora)


# Os horários do plano que passaram sem o robô (o celular fora, o robô fora do ar) não se
# perdem: o primeiro sai na volta e os outros voltam espalhados no resto do dia, junto dos que
# ainda faltam, com ESPACO_MEDIO em média e nunca menos de ESPACO_MINIMO entre um e outro (o
# mesmo espaço das postagens); o que não cabe sem apertar fica de fora. Só os do dia: o plano
# recomeça à meia-noite. A pausa do Rafael e a suspensão continuam pulando. Pedido do Rafael
# (01/11, no lugar da P16): DECISOES.md, Shopee Vídeo.
ESPACO_MEDIO = 60
ESPACO_MINIMO = INTERVALO_DAS_POSTAGENS[0]
PROCESSO_DOS_PERDIDOS = "horários perdidos na volta"
# Sem o celular, o modo assistente cobre o robô no privado. Cada vídeo que ele mandou nesse tempo e
# o Rafael marcou com Postei ✅ fecha um horário do plano do dia do robô: primeiro os que passaram
# (na volta do celular), depois os próximos que chegarem. Assim o dia não passa do plano nem do
# teto da escada dos pontos (P145). Sem o toque, o robô recupera todos, como antes. Escolha do
# Rafael (05/11, P156 1): DECISOES.md, Shopee Vídeo.
PROCESSO_DOS_COBERTOS = "horários cobertos pelo assistente"


def cobertos_pelo_assistente(estado):
    """Os vídeos do assistente postados no dia do plano, cobrindo o robô sem o celular, que ainda não fecharam um horário."""
    ja_contados = set(estado.get("cobertos") or [])
    return [ident for ident in assistente.postados_cobrindo_o_robo(estado["data"]) if ident not in ja_contados]


def _espalhar(trechos, quantos, sorteio):
    """quantos horários ("HH:MM") nos trechos (minutos do dia): partes iguais, um minuto sorteado no meio de cada."""
    total = sum(b - a for a, b in trechos)
    parte = total / quantos
    horarios = []
    for i in range(quantos):
        # No meio da parte (de 1/4 a 3/4): entre um horário e o seguinte fica no mínimo meia parte.
        corrido = int(i * parte + sorteio.uniform(parte / 4, parte * 3 / 4))
        for a, b in trechos:
            if corrido < b - a:
                minuto = a + corrido
                break
            corrido -= b - a
        else:
            minuto = trechos[-1][1] - 1
        horarios.append(f"{minuto // 60:02d}:{minuto % 60:02d}")
    return sorted(horarios)


def recuperar_horarios(config, estado, perdidos, agora=None):
    """
    Devolve ao plano de hoje os perdidos (os horários que passaram sem rascunho, fora o que sai
    agora): com os que ainda faltam, espalhados nos trechos de postar a partir de ESPACO_MINIMO
    depois de agora. Cabem tantos quantos deixam ESPACO_MEDIO em média; os que faltavam nunca
    saem do plano (só mudam de minuto, para o espaço ficar natural), e os perdidos que não cabem
    ficam de fora. Muda estado["horarios"] (o mesmo número de horários no dia) e devolve
    (recuperados, de fora).
    """
    momento = agora_br(agora)
    hora = momento.strftime("%H:%M")
    passados = [h for h in estado["horarios"] if h <= hora]
    futuros = [h for h in estado["horarios"] if h > hora]
    inicio = momento.hour * 60 + momento.minute + ESPACO_MINIMO
    trechos = [(max(a, inicio), b) for a, b in trechos_de_postar(config) if b > inicio]
    cabem = int(sum(b - a for a, b in trechos) // ESPACO_MEDIO)
    recuperados = max(0, min(perdidos, cabem - len(futuros)))
    if recuperados:
        sorteio = random.Random(f"{CHAVE_ESTADO}:{estado['data']}:{hora}")
        estado["horarios"] = sorted(passados[:len(passados) - recuperados]
                                    + _espalhar(trechos, len(futuros) + recuperados, sorteio))
    return recuperados, perdidos - recuperados


# Os Rascunhos por Dia ou o Horário do Robô mudaram: o plano de hoje é
# refeito na hora com o que vale agora (P157 1), e é o do dia inteiro: o que já saiu hoje entra na
# conta, e só o que falta sai, espalhado no resto do dia como os perdidos. Já saíram: os rascunhos de
# hoje (os do Preparar 1 Agora, os recusados e o que está no preparo também) e os vídeos do
# assistente que cobriram o robô (P156 1). Pedido do Rafael (06/11): DECISOES.md, Shopee Vídeo.
PROCESSO_DO_PLANO_REFEITO = "plano de hoje refeito"
ESTADOS_QUE_SAIRAM = ("preparando",) + ESTADOS_SALVOS


def replanejar_hoje(config, agora=None):
    """
    Refaz o plano de hoje com o número do dia que vale agora (quantos_hoje): os horários passados são
    os que já saíram hoje, e os que faltam se espalham a partir de ESPACO_MINIMO depois de agora,
    tantos quantos deixam ESPACO_MEDIO em média (nunca menos que o plano do dia inteiro teria daqui
    ao fim); os que não cabem ficam de fora, como horários passados sem tentativa. O horário que
    espera a nova tentativa é um dos que faltam; sem lugar no dia, ele acaba aqui, como o que está no
    preparo. Devolve o plano, com "refeito" ({no_dia, saidos, faltam, de_fora, proximo}) para a
    resposta do painel.
    """
    estado = estado_do_dia(config, agora)
    momento = agora_br(agora)
    hora, dia = momento.strftime("%H:%M"), estado["data"]
    no_dia = quantos_hoje(config, dia)
    rascunhos = sorted(r["criado_em"][11:16] for r in _criados_hoje(ESTADOS_QUE_SAIRAM, agora))
    cobertos = assistente.postados_cobrindo_o_robo(dia)
    saidos = len(rascunhos) + len(cobertos)
    esperando = int(bool(estado.get("repetir")) and estado.get("tentativas", 0) > 0 and not estado.get("em_preparo"))
    if saidos >= no_dia:
        esperando = 0
        estado.update(repetir=False, tentativas=0, videos=VIDEOS_POR_HORARIO, reposto=True)
    inicio = momento.hour * 60 + momento.minute + ESPACO_MINIMO
    trechos = [(max(a, inicio), b) for a, b in trechos_de_postar(config) if b > inicio]
    cabem = max(int(sum(b - a for a, b in trechos) // ESPACO_MEDIO),
                sum(1 for h in planejar(config, dia) if h > hora)) if trechos else 0
    faltam = max(no_dia - saidos - esperando, 0)
    novos = min(faltam, cabem)
    de_fora = faltam - novos
    futuros = _espalhar(trechos, novos, random.Random(f"{CHAVE_ESTADO}:{dia}:{hora}:refeito")) if novos else []
    # Com mais saídos que o número novo, ficam os últimos: o plano tem sempre o número do dia.
    passados = (rascunhos + [hora] * len(cobertos))[-no_dia:] if no_dia else []
    passados += [hora] * (esperando + de_fora)
    estado.update(horarios=sorted(passados) + futuros, feitos=len(passados), cobertos=cobertos,
                  sem_tentar=min(len(cobertos), no_dia) + de_fora, repostos=[], volta_do_horario="",
                  feito_com=feito_com(config, dia),
                  refeito={"no_dia": no_dia, "saidos": saidos, "faltam": esperando + novos, "de_fora": de_fora,
                           "proximo": futuros[0] if futuros and not esperando else ""})
    db.salvar_config(CHAVE_DIA, estado)
    registro_processos.registrar(REGISTRO, PROCESSO_DO_PLANO_REFEITO, f"{esperando + novos} de {no_dia} a fazer",
                                 f"já saíram {saidos}; de fora por falta de espaço no dia: {de_fora}",
                                 ok=None, agora=agora)
    return estado


# O horário do plano que acaba sem rascunho (os VIDEOS_POR_HORARIO vídeos não passaram, ou não havia
# vídeo na fonte) volta uma vez, mais tarde no mesmo dia: no meio do maior vão livre dos trechos de
# postar (o Horário do Robô), a pelo menos ESPACO_MINIMO de agora
# e de cada um dos outros horários que faltam; sem um vão assim, fica de fora. O horário que já é a
# volta de outro não volta de novo. Escolha do Rafael (02/11, P132): DECISOES.md, Shopee Vídeo.
PROCESSO_DO_HORARIO_SEM_RASCUNHO = "horário sem rascunho"


def _minuto_do_dia(hora):
    """ "HH:MM" em minutos do dia."""
    horas, minutos = hora.split(":")
    return int(horas) * 60 + int(minutos)


def vao_para_o_horario(config, estado, agora=None):
    """
    O "HH:MM" em que o horário sem rascunho volta: o meio do maior pedaço dos trechos de postar
    que fica a pelo menos ESPACO_MINIMO de agora e de cada horário que falta; None sem pedaço.
    """
    momento = agora_br(agora)
    hora = momento.strftime("%H:%M")
    inicio = momento.hour * 60 + momento.minute + ESPACO_MINIMO
    ocupados = [_minuto_do_dia(h) for h in estado["horarios"] if h > hora]
    livres = []
    for a, b in trechos_de_postar(config):
        pedacos = [(max(a, inicio), b)]
        for minuto in ocupados:
            pedacos = [parte for x, y in pedacos
                       for parte in ((x, min(y, minuto - ESPACO_MINIMO + 1)), (max(x, minuto + ESPACO_MINIMO), y))]
        livres += [(x, y) for x, y in pedacos if y > x]
    if not livres:
        return None
    x, y = max(livres, key=lambda pedaco: (pedaco[1] - pedaco[0], -pedaco[0]))
    minuto = (x + y - 1) // 2
    return f"{minuto // 60:02d}:{minuto % 60:02d}"


def repor_o_horario(config, estado, agora=None):
    """
    O horário do plano acabou sem rascunho: ele sai dos que já passaram e volta no vão livre do
    resto do dia (vao_para_o_horario), uma vez. Muda estado (os horários, os feitos e "repostos",
    os horários que são a volta de outro) e devolve o "HH:MM" novo, ou "" quando ele não volta; o
    registro diz qual.
    """
    if estado.get("reposto"):
        registro_processos.registrar(REGISTRO, PROCESSO_DO_HORARIO_SEM_RASCUNHO, "de fora",
                                     "já era a volta de outro horário", ok=None, agora=agora)
        return ""
    feitos = estado.get("feitos", 0)
    novo = vao_para_o_horario(config, estado, agora) if feitos > 0 else None
    if not novo:
        registro_processos.registrar(REGISTRO, PROCESSO_DO_HORARIO_SEM_RASCUNHO, "de fora", "sem espaço no dia",
                                     ok=None, agora=agora)
        return ""
    horarios = sorted(estado["horarios"])
    # O deste horário é o último que a rodada já contou como feito.
    del horarios[feitos - 1]
    estado.update(horarios=sorted(horarios + [novo]), feitos=feitos - 1,
                  repostos=estado.get("repostos", []) + [novo])
    registro_processos.registrar(REGISTRO, PROCESSO_DO_HORARIO_SEM_RASCUNHO, "volta mais tarde", f"às {novo}",
                                 ok=None, agora=agora)
    return novo


def consumir_horarios(config, agora=None, pular=False):
    """
    Marca como feitos os horários que já passaram e diz se havia algum novo. Vários de uma
    vez (o celular fora, o robô fora do ar): o primeiro sai agora e os outros voltam ao resto
    do dia (recuperar_horarios), nunca todos de uma vez. O horário novo ganha as tentativas a
    mais, começa no primeiro vídeo e tira a repetição do anterior. pular=True (a pausa do
    Rafael, a suspensão): passam sem rascunho. Os vídeos que o assistente mandou com o robô sem
    o celular e o Rafael marcou com Postei ✅ fecham horários antes disso (cobertos_pelo_assistente,
    P156 1): com todos fechados, nenhum rascunho agora (False). Os que passam sem tentativa,
    pulados, cobertos ou de fora por falta de espaço no dia, somam em "sem_tentar", que o
    checkup desconta do que cobra.
    """
    estado = estado_do_dia(config, agora)
    passados = horarios_vencidos(estado, agora)
    if passados <= estado["feitos"]:
        return False
    novos = passados - estado["feitos"]
    # Na pausa do Rafael os horários passam sem rascunho de qualquer jeito: o vídeo do assistente
    # marcado conta contra eles, e não fecha mais um depois.
    cobertos = cobertos_pelo_assistente(estado)[:novos]
    if cobertos:
        estado["cobertos"] = list(estado.get("cobertos") or []) + cobertos
        registro_processos.registrar(REGISTRO, PROCESSO_DOS_COBERTOS, f"{len(cobertos)} de {novos}",
                                     "fechados pelos vídeos do assistente com Postei ✅", ok=None, agora=agora)
    sobram = 0 if pular else novos - len(cobertos)
    de_fora = novos - len(cobertos) if pular else max(sobram - 1, 0)
    recuperados = 0
    if not pular and sobram > 1:
        recuperados, de_fora = recuperar_horarios(config, estado, sobram - 1, agora)
        passados -= recuperados
        registro_processos.registrar(REGISTRO, PROCESSO_DOS_PERDIDOS, f"{recuperados} de {sobram - 1} de volta ao plano",
                                     f"de fora por falta de espaço no dia: {de_fora}", ok=None, agora=agora)
    # O horário que começa agora é a volta de um que acabou sem rascunho (P132)? Os horários
    # espalhados de novo na volta do celular (recuperar_horarios) mudam de minuto: a marca sai.
    repostos = [] if recuperados else estado.get("repostos", [])
    atual = sorted(estado["horarios"])[passados - 1]
    hora = agora_br(agora).strftime("%H:%M")
    estado.update(feitos=passados, tentativas=TENTATIVAS_A_MAIS, videos=1, repetir=False,
                  sem_tentar=estado.get("sem_tentar", 0) + de_fora + len(cobertos),
                  reposto=not pular and sobram > 0 and atual in repostos,
                  repostos=[h for h in repostos if h > hora], volta_do_horario="")
    db.salvar_config(CHAVE_DIA, estado)
    return pular or sobram > 0


def marcar_para_repetir(config, agora=None, video=None, do_video=False):
    """
    O rascunho do plano não deu certo. Com tentativa sobrando, o mesmo vídeo volta na
    rodada seguinte. Sem tentativa, ou com o problema no próprio vídeo (do_video: ele já
    ficou de lado), o horário passa a outro vídeo, com as tentativas de novo, até
    VIDEOS_POR_HORARIO; o vídeo que esgotou as tentativas fica de lado só hoje. Sem vídeo
    na fonte não há outro para tentar: o horário acaba e volta mais tarde no mesmo dia, uma vez
    (repor_o_horario, P132). Decisão do Rafael: DECISOES.md, Shopee Vídeo.
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
        # O horário acabou sem rascunho: volta mais tarde no mesmo dia, uma vez (P132).
        estado.update(repetir=False, volta_do_horario=repor_o_horario(config, estado, agora))
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
    """
    O treino tem de rodar? Na segunda, se o desta semana ainda não rodou; e o da segunda
    que caiu na suspensão da conta, logo que ela acaba (adiar_treino_da_suspensao).
    """
    estado = ler_estado()
    if estado.get("treino_depois_da_suspensao"):
        return True
    return agora_br(agora).weekday() == DIA_DO_TREINO and estado.get("treino_semana") != semana(agora)


def adiar_treino_da_suspensao(agora=None):
    """
    Na suspensão o treino não roda (ele passa pelo Postar vídeo, que a Shopee fecha): o da
    segunda que cai nela roda logo que ela acaba, antes de voltar a postar. Escolha do
    Rafael (P41): DECISOES.md, Shopee Vídeo.
    """
    estado = ler_estado()
    if (not estado.get("treino_depois_da_suspensao") and agora_br(agora).weekday() == DIA_DO_TREINO
            and estado.get("treino_semana") != semana(agora)):
        gravar_estado(treino_depois_da_suspensao=True)


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
           "rotulo_ia", "mais_produtos", "itens", "capas", "chamada", "marca", "vistas", "links_dos_produtos",
           "falhas_ao_postar", "outras_capas", "recusadas", "outra_cor", "tirar", "trocado", "comentarios_proprios",
           "achado", "cor", "itens_do_video", "busca_do_link", "postar_agora_em", "letras", "valor", "edicao",
           "nova_versao", "versao_de", "no_app_em")
# Colunas que vieram depois da tabela: entram nas tabelas antigas sem perder nada.
# rotulo_ia: vazio = o rótulo de IA desligado; com texto = ligado, e o texto é o que a IA viu.
# mais_produtos: os produtos anexados além do do link (P59), [{nome, link, endereco}], na ordem do post.
# itens: o número (itemId) de cada produto anexado no link de produto, na ordem do post, e se é
# um produto a mais, [{item, a_mais}]: a medição das vendas da P73.
# capas: os arquivos das fotos de capa dos produtos do post, na ordem, no rascunho com produtos
# a mais: o Rafael as vê em álbum antes de aprovar (P75).
# chamada: "1" quando o vídeo vai com a capa com chamada (P76); marca: a marca da capa dele na
# grade do Perfil, guardada no post; vistas: as visualizações lidas na grade, [[momento, número]]
# (a medição da P76, visualizacoes_shopee_video).
# links_dos_produtos: no Ver Produtos, o link de cada produto anexado, na ordem do post ("" no que
# a API não achou), para o Rafael conferir no rascunho, produto por produto (P83).
# falhas_ao_postar: quantas vezes o aprovado não saiu na hora de postar (P99); zera ao aprovar.
# outras_capas: as posições (1, 2, ...) dos produtos do post cuja foto de capa não é a do anúncio
# do post: o álbum e o texto do rascunho as marcam (P102).
# recusadas: os arquivos das fotos de capa dos anúncios que a IA recusou nos produtos a mais: o
# Rafael os vê num álbum à parte, para conferir a IA (pedido dele de 01/11, provisório).
# outra_cor: as posições (1, 2, ...) dos produtos do post que são o mesmo modelo em outra cor ou
# estampa, com a foto na miniatura que troca: o texto e o álbum do rascunho os marcam (02/11).
# tirar: as posições (1, 2, ...) dos produtos que o Rafael marcou para sair do post (P123): o robô
# os tira da tela final na hora de postar, e o rascunho postado fica só com os que ficaram.
# comentarios_proprios: os textos que o robô comentou no vídeo do post (P148 2), para o próximo
# nunca sair igual.
# achado: "1" quando o produto do link não era o do vídeo e o robô achou o do vídeo pela busca da
# IA (P158 2); "0" no de link de produto sem isso; vazio nos de antes e nos de Ver Produtos (a
# medição de quais posts levam punição, P146 2, separa).
# cor: a cor em que a faixa da capa saiu no vídeo, para o post conferir a faixa nela: o nome da do
# produto (P159 2) ou, quando ela some no fundo da foto, o da 2ª cor (P173) ou o #rrggbb do tom
# (P174 3); vazio com o laranja (as cores de sempre).
# itens_do_video: os números (itemId) do produto do vídeo, o do link e o que foi ao post (o da troca ou
# o achado pela IA), ou os do criador no Ver Produtos: o mesmo produto não se repete (P166 1).
# busca_do_link: no post que ficou sem o link logo depois de postar, {"vezes": [momento de cada busca
# que não deu certo], "fim": "" enquanto o robô tenta de novo, "copiado" ou "desistiu"}
# (buscar_o_link_de_novo, P148 2).
# postar_agora_em: quando o Rafael tocou em Postar Agora 🚀 neste aprovado; vazio quando o pedido acabou
# sem o post (postando_agora).
# letras: "1" quando a foto do anúncio, que vai inteira à capa (P181 2), tem letras escritas, pela IA
# (edicao_video.letras_da_foto); "0" sem elas; vazio nos de antes e quando a IA não respondeu (a
# medição de quais posts levam punição, P146 2, separa).
# edicao: o que o Editar ✏️ precisa para refazer a edição sem a IA (P192 1): o que editar_para_postar
# guardou (os textos da IA, a frase da capa, a música, as escolhas do painel) e os arquivos do vídeo
# original, da foto do anúncio e das fotos da miniatura que troca, ao lado do vídeo do rascunho, e
# "versoes", quantas versões do vídeo já foram ao app (a galeria do celular tem uma de cada).
# nova_versao: a versão refeita pelo Editar ✏️ que espera o Aprovar ✅ (o arquivo, o número, a
# miniatura, a legenda e o jeito); vazio sem ela.
# versao_de: no registro da versão de antes de um rascunho refeito no app, o id do rascunho; ela é
# apagada do app como um recusado e não conta como rascunho do dia.
# no_app_em: quando o rascunho foi salvo no app pela última vez (refeito pelo Editar ✏️); vazio é o
# criado_em. A lista do app vem por ele (posicao_no_app).
COLUNAS_NOVAS = ("fonte", "conferencia", "rotulo_ia", "mais_produtos", "itens", "capas", "chamada", "marca", "vistas",
                 "links_dos_produtos", "falhas_ao_postar", "outras_capas", "recusadas", "outra_cor", "tirar",
                 "trocado", "comentarios_proprios", "achado", "cor", "itens_do_video", "busca_do_link",
                 "postar_agora_em", "letras", "valor", "edicao", "nova_versao", "versao_de", "no_app_em")


def _criar_tabela(con):
    con.execute("CREATE TABLE IF NOT EXISTS shopee_video_rascunhos ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, id_video TEXT, criado_em TEXT, estado TEXT, "
                "arquivo TEXT, print TEXT, link TEXT, produtos TEXT, titulo TEXT, comentario TEXT, "
                "aprovado_em TEXT, postar_em TEXT, postado_em TEXT, link_post TEXT, motivo TEXT, "
                "fonte TEXT, conferencia TEXT, rotulo_ia TEXT, mais_produtos TEXT, itens TEXT, capas TEXT)")
    existentes = {linha[1] for linha in con.execute("PRAGMA table_info(shopee_video_rascunhos)")}
    for coluna in COLUNAS_NOVAS:
        if coluna not in existentes:
            con.execute(f"ALTER TABLE shopee_video_rascunhos ADD COLUMN {coluna} TEXT")


def _momento(agora=None):
    return agora_br(agora).strftime("%Y-%m-%d %H:%M:%S")


def _linha_para_dict(linha):
    rascunho = dict(zip(COLUNAS, linha))
    rascunho["produtos"] = json.loads(rascunho["produtos"] or "[]")
    rascunho["mais_produtos"] = json.loads(rascunho["mais_produtos"] or "[]")
    rascunho["itens"] = json.loads(rascunho["itens"] or "[]")
    rascunho["capas"] = json.loads(rascunho["capas"] or "[]")
    rascunho["vistas"] = json.loads(rascunho["vistas"] or "[]")
    rascunho["links_dos_produtos"] = json.loads(rascunho["links_dos_produtos"] or "[]")
    rascunho["outras_capas"] = json.loads(rascunho["outras_capas"] or "[]")
    rascunho["recusadas"] = json.loads(rascunho["recusadas"] or "[]")
    rascunho["outra_cor"] = json.loads(rascunho["outra_cor"] or "[]")
    rascunho["tirar"] = json.loads(rascunho["tirar"] or "[]")
    rascunho["comentarios_proprios"] = json.loads(rascunho["comentarios_proprios"] or "[]")
    rascunho["itens_do_video"] = json.loads(rascunho["itens_do_video"] or "[]")
    rascunho["busca_do_link"] = json.loads(rascunho["busca_do_link"] or "{}")
    rascunho["edicao"] = json.loads(rascunho["edicao"] or "{}")
    rascunho["nova_versao"] = json.loads(rascunho["nova_versao"] or "{}")
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
    for coluna in ("produtos", "mais_produtos", "itens", "capas", "vistas", "links_dos_produtos", "outras_capas",
                   "recusadas", "outra_cor", "tirar", "comentarios_proprios", "itens_do_video", "busca_do_link",
                   "edicao", "nova_versao"):
        if coluna in campos:
            campos[coluna] = json.dumps(campos[coluna], ensure_ascii=False)
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


def ids_usados(agora=None):
    """
    Os vídeos que o robô já usou ou pulou: não voltam. O que estava em análise na Shopee
    (MOTIVO_EM_ANALISE: o criador acabou de postar e ela ainda não liberou) fica de lado só no
    dia: a partir do dia seguinte volta a ser candidato e, já liberado, pode virar rascunho.
    Escolha do Rafael (02/11, P134): DECISOES.md, Shopee Vídeo.
    """
    hoje = agora_br(agora).strftime("%Y-%m-%d")
    with db.conexao() as con:
        _criar_tabela(con)
        linhas = con.execute("SELECT id_video, estado, motivo, criado_em FROM shopee_video_rascunhos").fetchall()
    return {id_video for id_video, estado, motivo, criado_em in linhas
            if not (estado == "pulado" and motivo == MOTIVO_EM_ANALISE and (criado_em or "") < hoje)}


def onde_os_produtos_foram():
    """
    {itemId: onde} dos produtos que já foram ou vão ao ar: o produto do vídeo dos rascunhos do robô
    esperando a aprovação, aprovados e postados (o do link e o que foi ao post) e os vídeos do modo
    assistente marcados com Postei ✅. Os produtos a mais não contam. onde é o rótulo do lugar mais
    adiantado: o post do robô vale mais que o Postei ✅, que vale mais que o aprovado e o rascunho. (P166 1)
    """
    rascunhos = listar("rascunho", "aprovado", "refazer", "postado")

    def do_robo(estado):
        # O editado que o robô refaz no app (P192 1) conta como aprovado.
        estados = (estado, "refazer") if estado == "aprovado" else (estado,)
        return (ONDE_JA_FOI[estado], [item for rascunho in rascunhos if rascunho["estado"] in estados
                                      for item in _itens_do_post(rascunho)])

    lugares = [do_robo("rascunho"), do_robo("aprovado"), (POSTEI_NO_ASSISTENTE, assistente.itens_postados()),
               do_robo("postado")]
    return {str(item): onde for onde, itens in lugares for item in itens if item}


def _itens_do_post(rascunho):
    """O produto do vídeo de um rascunho (o do link e o que foi ao post), sem os produtos a mais."""
    return list(rascunho["itens_do_video"]) + [item.get("item") for item in rascunho["itens"] if not item.get("a_mais")]


def produtos_ja_postados():
    """Os números (itemId) dos produtos que já foram ou vão ao ar (onde_os_produtos_foram). (P166 1)"""
    return set(onde_os_produtos_foram())


def anotar_onde_ja_foi(item, quem):
    """
    Anota no registro onde estava o produto do vídeo que ficou de lado por já ter sido postado: só o
    rótulo fixo (ONDE_JA_FOI, o Postei ✅ do assistente ou "em nenhum") e quem deixou o vídeo de lado
    ("robô" ou "assistente"). Nada aqui segura o robô.
    """
    try:
        onde = onde_os_produtos_foram().get(str(item or ""), EM_NENHUM)
        registro_processos.registrar(REGISTRO, PROCESSO_DO_JA_POSTADO, onde, quem, ok=None)
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Onde estava o produto já postado não foi anotado: {type(e).__name__}")


def item_do_video(video):
    """O número (itemId) do produto do link do vídeo, pela API de afiliado; "" quando ela não diz."""
    try:
        produtos, _ = asyncio.run(assistente.produtos_do_link(video["link"]))
    except Exception:
        return ""
    return str((produtos[0] if produtos else {}).get("item") or "")


# --- Histórico das tentativas (tabela shopee_video_tentativas) ---
# Cada coisa que o robô tenta (rascunho, postar, apagar, treino) e como terminou, com o
# passo em que parou. O Rafael vê em Histórico do Robô 📋, recebe o aviso do rascunho que
# não saiu e o resumo das 22h; o diagnóstico do servidor, que é público, conta só os
# resultados e os passos, nunca o produto nem o motivo. Decisão do Rafael: DECISOES.md,
# Shopee Vídeo. Fica 3 dias no banco, como todo registro de processo (DECISOES.md,
# Trabalho com o Claude).
DIAS_DO_HISTORICO = 3
# As tentativas de cada dia por ação e resultado, por DIAS_DA_CONTAGEM dias (o histórico guarda
# só 3): a medição dos produtos a mais (P73) olha 7 dias.
CHAVE_TENTATIVAS_POR_DIA = "shopee_video_tentativas_por_dia"
DIAS_DA_CONTAGEM = 30
LINHAS_DO_HISTORICO = 12
# O passo em que parou, achado no motivo (as frases fixas do robô e do postador). A
# ordem importa: o primeiro trecho que aparece no motivo decide.
PASSOS = (
    ("a tela do celular está apagada", "tela do celular apagada"),
    ("suspensa pela Shopee", "conta suspensa pela Shopee"),
    ("rodada foi interrompida", "rodada interrompida"),
    ("não está respondendo", "app travado"),
    ("edição do vídeo não saiu", "edição do vídeo"),
    ("bebida alcoólica só vai", "edição do vídeo"),
    ("bebida alcoólica em espera", "bebida alcoólica em espera"),
    ("depois do Feito", "anexar o produto"),
    ("efeitos na edição", "efeitos na edição"),
    # O caminho até o Perfil em Shopee Vídeo (CAMINHO_PERFIL), o mesmo do post, do rascunho, do
    # treino e da Saúde: antes do "Criadores & Afiliados" da limpeza dos favoritos.
    ("a tela não mostrou Criadores & Afiliados", "navegar no app"),
    ("a tela não mostrou Conta", "navegar no app"),
    ("a tela não mostrou Perfil em Shopee Vídeo", "navegar no app"),
    ("a tela não mostrou Postar vídeo", "navegar no app"),
    ("não casaram com a grade", "visualizações na grade"),
    ("Meus Favoritos", "descurtir em Meus Favoritos"),
    ("busca pela foto", "busca pela foto"),
    ("câmera da busca", "busca pela foto"),
    ("Criadores & Afiliados", "descurtir em Meus Favoritos"),
    ("de férias", "loja de férias"),
    ("notificação do comentário", "achar a notificação"),
    ("vídeo do post não abriu", "abrir o vídeo do post"),
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
    ("sem o número do Ponto", "ler os pontos de penalidade"),
    ("em análise na Shopee", "vídeo em análise"),
    ("sem oferta de afiliado", "oferta de afiliado"),
    ("menos que o mínimo por venda", "valor por venda"),
    ("já foi postado", "produto já postado"),
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
    ("produto a mais", "anexar o produto"),
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
SIMBOLOS = {"salvo": "✅", "postado": "📤", "apagado": "🗑️", "pulado": "⏭️", "de lado": "↪️", "parou": "⚠️", "erro": "❌",
            "verificação": "🧩", "suspensa": "⛔", "sem vídeo": "📭", "treino ok": "🧭", "treino parou": "🧭",
            "saúde lida": "🩺", "respondido": "💬", "comentado": "❤️", "curtido": "👍", "descurtido": "💔",
            "refeito": "✏️"}
NOMES_DAS_ACOES = {"rascunho": "Rascunho", "postar": "Postagem", "apagar": "Apagar rascunho",
                   "refazer": "Refazer rascunho editado",
                   "treino": "Testar Caminho", "rodada": "Rodada", "saude": "Saúde do Vídeo",
                   "responder": "Resposta a comentário", "feed": "Feed (Para você)",
                   "comentar_post": "Comentário no post", "post_antigo": "Comentário em post antigo",
                   "descurtir": "Limpeza dos favoritos (4h)"}
# Como o resultado aparece para o Rafael no resumo das 22h e no Histórico (no banco fica o
# resultado de sempre, que o checkup conta). Pedido do Rafael (25/10): DECISOES.md, Shopee Vídeo.
NOMES_DOS_RESULTADOS = {"descurtido": "limpeza dos favoritos", "curtido": "curtido, sem comentário"}


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
    _contar_no_dia(acao, resultado, agora)


def _contar_no_dia(acao, resultado, agora=None):
    """Mais uma tentativa com essa ação e esse resultado no dia (só a contagem, sem o motivo)."""
    dia = agora_br(agora).strftime("%Y-%m-%d")
    corte = (agora_br(agora) - timedelta(days=DIAS_DA_CONTAGEM)).strftime("%Y-%m-%d")

    def contar(dados):
        for velho in [d for d in dados if d < corte]:
            dados.pop(velho)
        do_dia = dados.setdefault(dia, {})
        do_dia[f"{acao}: {resultado}"] = do_dia.get(f"{acao}: {resultado}", 0) + 1

    db.atualizar_config(CHAVE_TENTATIVAS_POR_DIA, contar)


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
    if na_hora_do_descurtir(agora) and descurtir_pendente(agora):
        return f"às {HORA_DO_DESCURTIR}h a limpeza dos favoritos vem primeiro; acabada, ele posta"
    if not no_horario_do_robo(config, agora):
        return "fora do Horário do Robô"
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
        if postando_agora(r, agora):
            linhas.append(f"   🚀 postando agora (você pediu às {r['postar_agora_em'][11:16]})")
        falhas = int(r.get("falhas_ao_postar") or 0)
        if falhas:
            # O post que não saiu e vai ser tentado de novo (P99).
            linhas.append(f"   🔁 não saiu {falhas} vez(es) ({html.escape(r['motivo'] or '?')}); tento de novo "
                          f"(tentativa {falhas + 1} de {TENTATIVAS_DE_POSTAR})")
        if r["postar_em"] and r["postar_em"] <= agora_txt:
            linhas.append(f"   ⏳ já passou da hora: {html.escape(espera)}")
    if not aprovados:
        linhas.append("nenhum")
    # Os editados (Editar ✏️) e aprovados que o robô refaz no celular antes de ganhar a hora (P192 1).
    refazer = listar("refazer")
    if refazer:
        linhas += ["", f"✏️ <b>Editados, esperando o robô refazer no celular ({len(refazer)})</b>"]
        linhas += [f"• {produto(r)}" + (f"\n   🔁 não saiu {r['falhas_ao_postar']} vez(es) "
                                        f"({html.escape(r['motivo'] or '?')}); tento de novo"
                                        if int(r.get("falhas_ao_postar") or 0) else "") for r in refazer]
    if pendentes or aprovados:
        linhas.append("")
    if pendentes:
        linhas.append("Para aprovar ou recusar: Rascunhos do Robô 📝.")
    if aprovados:
        linhas.append("Para postar já um aprovado: Aprovados para Postar ⏳.")
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
        volta = estado.get("volta_do_horario")
        proxima = (f"As tentativas deste horário acabaram: ele volta às {volta}, hoje mesmo." if volta
                   else f"As tentativas deste horário acabaram. Próximo horário do plano: {futuros[0]}." if futuros
                   else "As tentativas deste horário acabaram, e hoje não há mais horários: amanhã tem plano novo.")
    return ("⏭️ Robô da Shopee Vídeo: o rascunho não saiu.\n\n"
            f"🛍️ Produto: {ultima.get('produto') or '—'}\n"
            f"📍 Parou em: {ultima.get('passo') or 'outro'}\n"
            f"❓ Motivo: {ultima.get('motivo') or '—'}\n\n"
            f"🔁 {proxima}\n\n"
            "Tudo o que o robô tentou: Robô Automático 🤖 → Histórico do Robô 📋.")


def esperando_aprovacao():
    return listar("rascunho")


# O aprovado que o Rafael mandou postar no Postar Agora 🚀 sai de Aprovados para Postar ⏳ enquanto o
# robô o posta: tocar de novo nele só repetiria o pedido. O pedido que acaba sem o post limpa a marca
# (o robô e o painel), e ele volta à lista; a marca vale no máximo ESPERA_DO_POSTAR_AGORA, para o
# aprovado não sumir de vez se a rodada morrer. Pedido do Rafael (vídeo de 07/11, 00:59): DECISOES.md,
# Shopee Vídeo.
ESPERA_DO_POSTAR_AGORA = timedelta(seconds=MAXIMO_DA_RODADA + 10 * 60)


def postando_agora(rascunho, agora=None):
    """Se o aprovado está sendo postado agora pelo Postar Agora 🚀 (postar_agora_em recente)."""
    marca = (rascunho or {}).get("postar_agora_em")
    return bool(marca) and marca > _momento(agora_br(agora) - ESPERA_DO_POSTAR_AGORA)


def aprovados_na_fila(agora=None):
    """
    Os aprovados que ainda não foram ao ar, pela hora de postar, fora os que o Postar Agora 🚀 está
    postando: a lista de Aprovados para Postar ⏳.
    """
    return sorted((r for r in listar("aprovado") if not postando_agora(r, agora)),
                  key=lambda r: (r["postar_em"] or "", r["id"]))


def proxima_postagem(config, agora=None, sorteio=random):
    """
    Quando postar um rascunho que o Rafael acabou de aprovar: depois do último aprovado
    (ou postado) com um intervalo sorteado, ou daqui a poucos minutos se nenhum está
    marcado. Fora do Horário do Robô, vai para o começo do próximo horário, com uns minutos
    sorteados: os aprovados saem espalhados, nunca todos de uma vez. Na hora do descurtir, o
    post espera a limpeza acabar (o_que_fazer, P161 1). Decisão do Rafael: DECISOES.md, Shopee Vídeo.
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
    # Ajusta até cair no Horário do Robô: fora dele, o começo do próximo, com uns minutos sorteados.
    for _ in range(6):
        if quando.hour >= config["robo_fim"] or (quando.date() > momento.date() and quando.hour < config["robo_inicio"]):
            dia = quando.date() if quando.hour < config["robo_inicio"] else quando.date() + timedelta(days=1)
            quando = datetime(dia.year, dia.month, dia.day, config["robo_inicio"], tzinfo=momento.tzinfo)
            quando += timedelta(minutes=sorteio.randint(*ESPERA_DA_PRIMEIRA))
        elif quando.hour < config["robo_inicio"]:
            quando = quando.replace(hour=config["robo_inicio"], minute=0) + timedelta(
                minutes=sorteio.randint(*ESPERA_DA_PRIMEIRA))
        else:
            break
    return _momento(quando)


def postou_ha_pouco(agora=None):
    """O último post saiu há menos de ESPACO_MINIMO? Aí o aprovado atrasado espera (o_que_fazer)."""
    ultimo = max((r["postado_em"] for r in listar("postado") if r["postado_em"]), default="")
    return bool(ultimo) and ultimo > _momento(agora_br(agora) - timedelta(minutes=ESPACO_MINIMO))


def aprovar(ident, agora=None):
    """
    O Rafael aprovou no bot: o rascunho ganha a hora de ir ao ar. Devolve essa hora. Com a nova versão do
    Editar ✏️, o robô primeiro refaz o rascunho no app com ela ("refazer", P192 1), e a hora de ir ao ar sai
    quando ele estiver refeito: devolve None.
    """
    rascunho = pegar(ident)
    arquivo = ((rascunho or {}).get("nova_versao") or {}).get("arquivo")
    if arquivo and os.path.exists(arquivo):
        atualizar(ident, estado="refazer", aprovado_em=_momento(agora), postar_em=None, falhas_ao_postar="0",
                  postar_agora_em=None, motivo="")
        return None
    quando = proxima_postagem(ler_config(), agora)
    atualizar(ident, estado="aprovado", aprovado_em=_momento(agora), postar_em=quando, falhas_ao_postar="0",
              postar_agora_em=None)
    return quando


def recusar(ident, agora=None):
    """O Rafael recusou: o robô apaga o rascunho do app numa próxima rodada, e o vídeo não volta."""
    atualizar(ident, estado="recusado", aprovado_em=_momento(agora))


def o_que_fazer(config, agora=None):
    """
    A tarefa desta rodada: ("descurtir", None) (tudo em Meus Favoritos, a 1ª coisa do dia, às 4h:
    enquanto ela não acaba, nessa hora só ela), ("treino", None), ("apagar", id), ("postar", id),
    ("saude", None) (a Saúde do Vídeo, uma vez por dia e de hora em hora depois do Já recorri),
    ("rascunho", None), ("responder", None) (os comentários dos vídeos, 3 vezes por dia,
    respostas_pendentes), ("feed", None) (um vídeo do feed, espalhados pelo dia, P152),
    ("comentar_post", id) (o comentário de depois do post que volta, ou o link do post que não
    saiu e é buscado de novo, link_do_post_pendente), ("post_antigo", id) (o
    comentário do dia num post antigo) ou None. Sem hora marcada: cada uma sai na 1ª rodada em que
    pode, e a seguinte vem na rodada depois (P161 1). Gasta o horário do plano, ou uma tentativa a
    mais do rascunho que falhou, quando escolhe um rascunho.
    """
    if na_hora_do_descurtir(agora):
        if descurtir_pendente(agora):
            # A limpeza é a 1ª coisa do dia (P25); acabada, o resto da hora fica livre (P161 1).
            return "descurtir", None
        if not no_horario_do_robo(config, agora):
            # Fora do Horário do Robô, a rodada das 4h só vem pela limpeza.
            return None
    # Na suspensão a Shopee fecha o Postar vídeo: o treino, o preparo e a postagem, que
    # passam por ele, esperam o fim. O resto segue: a limpeza dos favoritos, apagar o
    # recusado, a Saúde do Vídeo, as respostas e o feed. Pedido do Rafael (25/10): DECISOES.md.
    sem_postar = suspensa(config, agora)
    if treino_da_semana_pendente(agora) and not sem_postar:
        return "treino", None
    recusados = listar("recusado")
    if recusados:
        return "apagar", recusados[0]["id"]
    postar = not sem_postar
    agora_txt = _momento(agora)
    aprovados = listar("aprovado")
    prontos = [r for r in aprovados if r["postar_em"] and r["postar_em"] <= agora_txt]
    if postar and prontos and postou_ha_pouco(agora):
        # Dois posts nunca saem colados (na volta do celular, com o robô fora do ar): os
        # aprovados que esperavam ganham horário novo, espalhados como na aprovação.
        # Pedido do Rafael (01/11): DECISOES.md, Shopee Vídeo.
        remarcar_aprovados(config, agora)
        aprovados = listar("aprovado")
        prontos = [r for r in aprovados if r["postar_em"] and r["postar_em"] <= agora_txt]
    if postar and prontos:
        return "postar", min(prontos, key=lambda r: r["postar_em"])["id"]
    # O comentário de depois do post que não saiu (o vídeo ainda em análise) volta com o post, e o
    # link do post que não saiu também é buscado de novo (P148 2).
    pendente = (link_do_post_pendente(agora) or comentario_do_post_pendente(agora)) if postar else None
    if pendente:
        return "comentar_post", pendente["id"]
    # Um aprovado vai ao ar antes da próxima rodada: nada de tarefa longa (Saúde, rascunho,
    # respostas, feed), que seguraria o celular na hora do post. Escolha do Rafael (P30).
    logo = _momento(agora_br(agora) + ANTES_DO_POST)
    if postar and any(r["postar_em"] and agora_txt < r["postar_em"] <= logo for r in aprovados):
        return None
    # O rascunho editado (Editar ✏️) e aprovado é refeito no app antes de ganhar a hora de ir ao ar (P192 1).
    refazer = listar("refazer")
    if postar and refazer:
        return "refazer", refazer[0]["id"]
    # A limpeza das 4h que não terminou volta no mesmo dia (P137).
    if limpeza_fora_da_hora_pendente(agora):
        return "descurtir", None
    if saude_do_dia_pendente(agora) or saude_pedida_pelo_recurso(agora):
        return "saude", None
    if postar and (consumir_horarios(config, agora) or repetir_o_que_falhou(config, agora)):
        return "rascunho", None
    # As respostas e o comentário do dia num post antigo (P148 2), durante o dia (P161 1).
    if respostas_pendentes(agora):
        return "responder", None
    antigo = post_antigo_pendente(agora)
    if antigo:
        return "post_antigo", antigo["id"]
    if feed_pendente(agora):
        return "feed", None
    return None


# --- Toques no celular ---

def pausa(segundos):
    """Espera com uns segundos a mais sorteados: toque em ritmo de máquina denuncia robô."""
    time.sleep(segundos + random.uniform(0.5, 2.5))


# O painel do Android (a cortina que desce do alto da tela, com o Wi-Fi, o Bluetooth e a lanterna)
# aberto por cima do app esconde a Shopee inteira: a leitura da tela traz só ele. Às 23:39 de
# 02/11 ele estava aberto no Motorola na volta do celular, e o post parou sem ver o Conta embaixo.
# O voltar fecha o painel sem mexer no app; as peças abaixo só existem com ele aberto.
PECAS_DO_PAINEL_DO_ANDROID = ("quick_settings_panel", "qs_frame", "notification_stack_scroller",
                              "notification_panel")


def painel_do_android_aberto(xml):
    """O painel do Android cobre a tela: as peças dele na leitura e nada da Shopee."""
    texto = str(xml or "")
    return (f'package="{ps.PACOTE}"' not in texto
            and any(f'{ps.PACOTE_SISTEMA}:id/{peca}"' in texto for peca in PECAS_DO_PAINEL_DO_ANDROID))


def fechar_o_painel_do_android(d):
    """Fecha o painel do Android com o voltar e devolve a tela de baixo; fica no registro."""
    d.press("back")
    pausa(2)
    xml = d.dump_hierarchy()
    registro_processos.registrar(REGISTRO, "voltar no app", "painel do Android por cima",
                                 "continuou aberto" if painel_do_android_aberto(xml) else "fechado com o voltar",
                                 ok=None)
    return xml


# A leitura da tela que traz só as barras do Android (a de cima e a de baixo) e nada do app: no
# Motorola, em 06/11/2026, às 19:31, com uma live tocando no Para você, a leitura veio assim com o
# app aberto na tela, e o feed parou sem "ver" a aba. A tela é lida de novo antes de seguir. A
# leitura que nem assim traz o app não conta como falha no registro: o passo que precisava dela é
# que para, e conta lá (no checkup de 08/11, 4 leituras assim, com vídeo tocando no feed e no
# próprio post, e nenhuma parada); o registro diz que app estava na frente (_quem_esta_na_frente).
RELEITURAS_SEM_O_APP, ESPERA_SEM_O_APP = 3, 2
PROCESSO_DA_LEITURA_DA_TELA = "leitura da tela"


def so_as_barras_do_android(xml):
    """A leitura tem só o Android (as barras de cima e de baixo), sem nada do app na tela."""
    return set(re.findall(r'package="([^"]*)"', str(xml or ""))) == {ps.PACOTE_SISTEMA}


def _reler_sem_o_app(d, xml):
    """
    Com só as barras do Android na leitura (so_as_barras_do_android), relê a tela até
    RELEITURAS_SEM_O_APP vezes; o registro diz se o app voltou à leitura.
    """
    vezes = 0
    while so_as_barras_do_android(xml) and vezes < RELEITURAS_SEM_O_APP:
        pausa(ESPERA_SEM_O_APP)
        vezes += 1
        xml = d.dump_hierarchy()
    if vezes:
        if not so_as_barras_do_android(xml):
            registro_processos.registrar(REGISTRO, PROCESSO_DA_LEITURA_DA_TELA, "só as barras do Android",
                                         f"o app voltou na {vezes}ª releitura", ok=True)
        else:
            frente = _quem_esta_na_frente(d)
            registro_processos.registrar(REGISTRO, PROCESSO_DA_LEITURA_DA_TELA, "só as barras do Android",
                                         f"sem o app em {vezes} releituras" + (f"; na frente: {frente}" if frente else ""),
                                         ok=None)
    return xml


def _quem_esta_na_frente(d):
    """
    O app na frente do celular, em rótulos fixos (o registro é público): "a Shopee (a tela dela)",
    "o Android" ou "outro app"; "" sem a leitura.
    """
    try:
        atual = d.app_current() or {}
    except Exception:
        return ""
    pacote, atividade = atual.get("package") or "", atual.get("activity") or ""
    if pacote == ps.PACOTE:
        return f"a Shopee ({atividade.rsplit('.', 1)[-1]})" if atividade else "a Shopee"
    if pacote == ps.PACOTE_SISTEMA:
        return "o Android"
    return "outro app" if pacote else ""


def tela(d, seguir=False):
    """
    A tela de agora; para na hora se for a Verificação. Com o painel do Android aberto por
    cima do app, fecha o painel (fechar_o_painel_do_android); com só as barras do Android na
    leitura, lê de novo (_reler_sem_o_app). Com o aviso do Android de app que
    não responde ("Shopee não está respondendo", com Fechar app e Aguardar), toca em
    Aguardar e dá um tempo ao app. Ainda travado depois de VEZES_DO_AGUARDAR toques,
    fecha e reabre a Shopee (fechar_e_reabrir). O passo que esperava outra tela não
    continua do início do app: a rodada para; com seguir=True (o voltar, que leva ao
    início de qualquer jeito), devolve a tela do app reaberto.
    """
    xml = d.dump_hierarchy()
    if painel_do_android_aberto(xml):
        xml = fechar_o_painel_do_android(d)
    xml = _reler_sem_o_app(d, xml)
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
    ainda travado também para. Fora este aviso e do produto que não fica com o app aberto há
    muitas horas (reabrir_o_app_aberto_ha_muito_tempo, P193 1), o robô nunca fecha o app.
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


# Escolha do Rafael (10/11, P193 1): o produto que não fica na tela final depois do Feito, nem na 2ª
# vez, com o app da Shopee aberto há mais de HORAS_DO_APP_ABERTO, faz o robô fechar e reabrir o app
# (em 10/11, das 05:44 às 06:24, 3 produtos seguidos não ficaram com o app aberto havia 16 h e a
# memória dele perto do teto do celular). O caso guarda antes a tela da falha; o vídeo volta mais
# tarde, como sempre (P182 1); a Verificação que aparecer na volta para tudo e avisa. Com o app aberto
# há menos tempo, nada muda. DECISOES.md, Shopee Vídeo.
HORAS_DO_APP_ABERTO = 12
PROCESSO_DO_APP_REABERTO = "app reaberto: produto que não ficou"


def reabrir_o_app_aberto_ha_muito_tempo(d):
    """
    Depois do produto que não ficou (MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU): com o app aberto há mais de
    HORAS_DO_APP_ABERTO, fecha a Shopee e abre de novo. Devolve se reabriu. Sem a leitura de há
    quanto tempo o app está aberto, não fecha. A Verificação na volta para (Verificacao).
    """
    minutos = casos_robo.minutos_do_app(d, ps.PACOTE)
    if minutos is None or minutos <= HORAS_DO_APP_ABERTO * 60:
        return False
    aberto_ha = f"o app aberto há {faixa_do_app_aberto(minutos)}"
    d.app_stop(ps.PACOTE)
    pausa(4)
    d.app_start(ps.PACOTE, wait=True)
    pausa(ESPERA_DEPOIS_DE_REABRIR)
    if ps.eh_verificacao(d.dump_hierarchy()):
        registro_processos.registrar(REGISTRO, PROCESSO_DO_APP_REABERTO, "a Verificação apareceu", aberto_ha,
                                     ok=False)
        raise Verificacao()
    registro_processos.registrar(REGISTRO, PROCESSO_DO_APP_REABERTO, "fechado e reaberto", aberto_ha, ok=True)
    return True


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


# A tela que demora a carregar (no Motorola, em 30/10, Criadores & Afiliados ficou em branco
# mais de 8 s depois do toque): o caminho relê a tela por até este tempo antes de parar.
ESPERA_A_MAIS_NO_CAMINHO = 12


def seguir(d, caminho):
    """
    Faz os toques do caminho e confere, depois de cada um, que a tela esperada abriu (a que
    demora a carregar tem mais ESPERA_A_MAIS_NO_CAMINHO segundos). O que demora a aparecer
    na tela (DEMORAM_A_APARECER) é esperado antes do toque.
    """
    for alvo, espera, esperado in caminho:
        if alvo in DEMORAM_A_APARECER:
            esperar_o_que_demora(d, alvo)
        tocar(d, alvo, espera)
        xml = tela(d)
        if alvo == "@tv_pick_top_next" and tem(xml, "Dicas de Upload"):
            # Só na primeira vez: a janela de dicas antes da edição.
            tocar(d, "Ok", 3)
            tocar(d, "Próximo", 8)
            xml = tela(d)
        if not tem(xml, esperado) and not esperar_na_tela(d, esperado, ESPERA_A_MAIS_NO_CAMINHO):
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
# Na edição, antes do Próximo, em todos os vídeos: o efeito Giro no começo (Efeitos → aba
# Transição → Giro → ✓). Pedido do Rafael: DECISOES.md, Shopee Vídeo.
# A tela de Efeitos (SSZMultipleEffectActivity) tem o ✕ (@iv_close), o ✓ (@iv_done) e a
# lista da aba Transição com o Giro primeiro; o efeito posto mostra o Desfazer (@ll_undo). Na
# primeira vez num celular, o toque no Giro só baixa o efeito, e o seguinte o põe.
# O Realçar fica desligado, e o robô não toca nele (toda edição nova começa com ele desligado):
# ele mudava a luz de cada quadro, e a faixa da capa da grade, toda preenchida, saía num laranja
# mais escuro na grade que no vídeo aberto. Escolha do Rafael (07/11, P177 2): DECISOES.md, Shopee Vídeo.
EFEITOS = "Efeitos"
GIRO = "Giro"
ABA_DO_GIRO = "Transição"
VEZES_DO_GIRO = 3
ESPERA_DO_GIRO = 6
EFEITOS_COMPLETOS = "giro"
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
# A linha do Adicionar produto (e o Adicionar Mais) da tela final que acaba de abrir pode
# aparecer só alguns segundos depois, como a fileira dos produtos (ps.ESPERA_DA_FILEIRA): no
# Motorola, em 06/11/2026, às 16:26, ela ainda não estava na tela 12 s depois do Próximo da
# edição. O caminho relê a tela por até ps.ESPERA_DA_FILEIRA s antes do toque (seguir).
DEMORAM_A_APARECER = {"@ll_add_product_symbol": "Adicionar produto", "@tv_add_more": "Adicionar Mais"}


def esperar_o_que_demora(d, alvo):
    """
    Relê a tela, de 3 em 3 s e por até ps.ESPERA_DA_FILEIRA s, até o alvo (um dos
    DEMORAM_A_APARECER) aparecer. O registro anota quando ele demorou; sem ele, a rodada para
    no passo de anexar o produto, com a linha dos produtos como a tela estava (rótulos fixos).
    """
    xml = tela(d)
    voltas = 0
    while not tem(xml, alvo) and voltas < ps.ESPERA_DA_FILEIRA // 3:
        pausa(3)
        voltas += 1
        xml = tela(d)
    nome = DEMORAM_A_APARECER[alvo]
    if not tem(xml, alvo):
        raise Parada(f"a tela final não mostrou o {nome} em {voltas * 3} s a mais ({ps.linha_dos_produtos(xml)})")
    if voltas:
        registro_processos.registrar(REGISTRO, "anexar o produto", f"o {nome} demorou a aparecer",
                                     f"mais {voltas * 3} s", ok=True)


def por_o_giro(d):
    """
    Põe o efeito Giro onde está o cursor da linha do tempo, que a tela de Efeitos abre parado no
    começo do vídeo, e confirma no ✓. Sem o Desfazer depois de VEZES_DO_GIRO toques (o
    primeiro pode só baixar o efeito), sai pelo ✕ sem mudar nada. True se o efeito ficou.
    """
    tocar(d, EFEITOS, 4)
    xml = esperar_na_tela(d, "@iv_done", 8)
    if not xml:
        raise Parada("efeitos na edição: a tela de Efeitos não abriu")
    if not tem(xml, GIRO) and tem(xml, ABA_DO_GIRO):
        tocar(d, ABA_DO_GIRO, 2)
    for _ in range(VEZES_DO_GIRO):
        tocar(d, GIRO, 2)
        if esperar_na_tela(d, "@ll_undo", ESPERA_DO_GIRO):
            tocar(d, "@iv_done", 3)
            return True
    tocar(d, "@iv_close", 3)
    return False


def voltar_para_a_edicao(d):
    """
    Volta à edição do vídeo (com o Próximo, @tv_compress) se um efeito deixou outra tela
    aberta. A tela de Efeitos tem o ✓; o ✕ dela sai sem mudar nada. Na edição, o voltar
    abriria a pergunta de sair: nele, nada é tocado.
    """
    for _ in range(3):
        xml = tela(d)
        if tem(xml, "@tv_compress") and not tem(xml, "@iv_done"):
            return
        if tem(xml, "@iv_done") and tem(xml, "@iv_close"):
            tocar(d, "@iv_close", 3)
            continue
        d.press("back")
        pausa(3)
    raise Parada("efeitos na edição: a edição do vídeo não voltou")


def efeitos_na_edicao(d):
    """
    O Giro na edição do vídeo, antes do Próximo, sem tocar no Realçar (pedidos do Rafael, 31/10 e
    P177 2: DECISOES.md, Shopee Vídeo). O Giro que não dá certo não derruba o rascunho: o vídeo
    segue sem ele, e o registro diz por quê (o checkup mostra). Devolve o que ficou, para o treino.
    """
    try:
        giro = "posto" if por_o_giro(d) else f"não ficou depois de {VEZES_DO_GIRO} toques"
    except Parada as e:
        giro = f"não: {e.motivo}"
    voltar_para_a_edicao(d)
    ficou = EFEITOS_COMPLETOS if giro == "posto" else "nenhum"
    registro_processos.registrar(REGISTRO, "efeitos na edição", ficou, f"giro: {giro}", ok=ficou == EFEITOS_COMPLETOS)
    return ficou


def aviso_de_sair(xml):
    """
    A janela que o voltar abre na tela final ("Se você voltar, ... serão ..."), com
    Cancelar e o botão de confirmar (@buttonDefaultPositive). No Motorola (22/10/2026),
    confirmar volta para a edição do vídeo; num rascunho aberto, o rascunho continua
    salvo na lista.
    """
    return (tem(xml, "@buttonDefaultPositive")
            and any(el["id"] == "content" and "voltar" in el["texto"].casefold() for el in ps.elementos(xml)))


# O aviso de erro do app da Shopee ("Ops! Algo deu errado. Estamos verificando nisso.") não
# fecha com o voltar (Motorola, 31/10/2026, 15:48 e 15:59: o robô apertou voltar até desistir);
# o único botão dele leva à página inicial do app.
BOTAO_DO_ERRO_DO_APP = "Voltar à Página Inicial"


def erro_do_app(xml):
    """O aviso de erro do app, com o Voltar à Página Inicial, está na tela?"""
    return tem_exato(xml, BOTAO_DO_ERRO_DO_APP)


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


def descartar_a_capa(xml):
    """
    A pergunta que o voltar abre na Selecione sua capa (SSZMediaCoverEditActivity) com alguma
    mudança na capa (Motorola, 30/10/2026): "Descartar Alterações na Capa?", com Cancelar
    (@tv_cancel) e Confirmar (@tv_discard). O voltar na pergunta só a fecha e volta para a capa:
    o robô confirma, como no Descartar da edição, e a capa sai sem a mudança.
    """
    return tem(xml, "@tv_discard") and tem(xml, "Descartar Alterações na Capa")


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


# A página do app presa carregando (ps.pagina_carregando) não sai com o voltar e segurava o
# celular por horas: cada rodada parava em "não consegui voltar até Eu". Abrir um link no app
# ainda funciona por cima dela. Depois deste tanto de voltar sem sair dela, o robô abre a página
# inicial pelo link, uma vez, sem fechar o app (P15: DECISOES.md, Shopee Vídeo).
VOLTAS_NA_PAGINA_CARREGANDO = 3
ESPERA_DA_PAGINA_INICIAL = 8
# Com um vídeo tocando no Para você (Motorola, 07/11/2026, às 18:12 e às 18:56), a leitura vinha só
# com as barras do Android, mesmo relida (_reler_sem_o_app): o voltar não via o Eu, apertava voltar
# em vão, a rodada parava, e o vídeo seguia tocando em laço. No caminho até a barra de baixo, a
# página inicial abre pelo link, como na página presa carregando (uma vez por voltar).
ATE_PELA_PAGINA_INICIAL = ("Eu",)


def voltar(d, ate, vezes=15):
    """
    Aperta voltar, confirmando os avisos de sair, até a tela ter um elemento com o texto
    exato. Nunca fecha o app à força (fechar e reabrir em seguida chama a Verificação),
    fora o aviso do Android de app que não responde (tela). Fora da Shopee, não aperta
    voltar: traz a Shopee de volta para a frente. Na página presa carregando, abre a
    página inicial pelo link (VOLTAS_NA_PAGINA_CARREGANDO); no caminho até o Eu, também com a
    leitura sem o app, só com as barras do Android (ATE_PELA_PAGINA_INICIAL).
    """
    carregando, abriu_o_inicio = 0, False
    for _ in range(vezes):
        xml = tela(d, seguir=True)
        if tem_exato(xml, ate) and not tem(xml, "@et_caption"):
            return
        if so_as_barras_do_android(xml) and ate in ATE_PELA_PAGINA_INICIAL and not abriu_o_inicio:
            abriu_o_inicio = True
            registro_processos.registrar(REGISTRO, "voltar no app", "leitura sem o app",
                                         "a página inicial aberta pelo link", ok=None)
            ps.abrir_pagina_inicial(d)
            pausa(ESPERA_DA_PAGINA_INICIAL)
            continue
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
        if descartar_a_capa(xml):
            tocar(d, "@tv_discard", 3)
            continue
        if erro_do_app(xml):
            registro_processos.registrar(REGISTRO, "voltar no app", "aviso de erro do app",
                                         f"{BOTAO_DO_ERRO_DO_APP} tocado", ok=None)
            tocar(d, BOTAO_DO_ERRO_DO_APP, 5)
            continue
        carregando = carregando + 1 if ps.pagina_carregando(xml) else 0
        if carregando > VOLTAS_NA_PAGINA_CARREGANDO and not abriu_o_inicio:
            abriu_o_inicio = True
            registro_processos.registrar(REGISTRO, "voltar no app", "página presa carregando",
                                         "a página inicial aberta pelo link", ok=None)
            ps.abrir_pagina_inicial(d)
            pausa(ESPERA_DA_PAGINA_INICIAL)
            continue
        d.press("back")
        pausa(3)
    onde = onde_ficou(d) + (", a página presa carregando" if carregando else "")
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


# A tela do celular apagada (11/11/2026, das 06:44 às 08:14: a leitura trazia só o Moto Display).
# Cada rodada escolhia o vídeo, perguntava à IA e só no celular apertava voltar 15 vezes em vão. O
# robô só toca no app com a tela acesa, e o Manter ativado a deixa acesa no carregador (DECISOES.md,
# Shopee Vídeo): apagada, a ação para antes de começar, sem tocar em nada e sem gastar vídeo da fonte,
# com o que o celular diz da carga e do Manter ativado no motivo. A tela é lida pelo adb
# (celular_robo.tela_acesa), sem passar pelo app.
TELA_APAGADA = "a tela do celular está apagada"


def conferir_a_tela_acesa():
    """Parada(TELA_APAGADA, com a carga) com a tela apagada; sem a leitura da tela, a ação segue como antes."""
    try:
        apagada = celular_robo.tela_acesa() is False
    except Exception:
        return
    if not apagada:
        return
    try:
        energia = celular_robo.descrever_energia(celular_robo.ler_energia())
    except Exception as e:
        energia = f"carga não lida (erro {type(e).__name__})"
    parada = Parada(f"{TELA_APAGADA} ({energia})")
    # Antes do preparo, o rascunho ainda não anotou nada: o _agir anota por ele.
    parada.antes_de_comecar = True
    raise parada


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
        xml = abrir_saude(d, agora)
        if pontos_de_penalidade(xml) is None:
            # A página pela metade pode ainda não mostrar o bloqueio: não vale como confirmação.
            raise Parada(MOTIVO_SEM_OS_PONTOS)
        na_saude = suspensao_na_tela(xml, agora)
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
    """
    O número logo depois de "Ponto de Penalidade" na Saúde do Vídeo, ou None. Com a seção "Status
    da Saúde do Vídeo" na tela (a Account Health), o dela: a aba Live tem os pontos das lives.
    """
    elementos = [el for el in ps.elementos(xml) if el["texto"].strip()]
    inicio = next((i for i, el in enumerate(elementos) if STATUS_DO_VIDEO in ps._normal(el["texto"])), 0)
    for i, el in enumerate(elementos[inicio:], inicio):
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


# Os seguidores do perfil em Shopee Vídeo, um número por dia (os últimos DIAS_DOS_SEGUIDORES),
# lidos no Perfil quando o robô passa por ele para a Saúde do Vídeo: o checkup mostra se
# sobem. Escolha do Rafael (P70): DECISOES.md, Shopee Vídeo.
CHAVE_SEGUIDORES = "shopee_video_seguidores"
DIAS_DOS_SEGUIDORES = 35


def seguidores_na_tela(xml):
    """O número logo acima de "Seguidores" no Perfil em Shopee Vídeo ("1,2K" → 1200), ou None."""
    elementos = ps.elementos(xml) if xml else []
    rotulo = next((el for el in elementos if ps._normal(el["texto"]) == "seguidores"), None)
    if not rotulo:
        return None
    x, y = ps._centro(rotulo)
    for el in elementos:
        ex, ey = ps._centro(el)
        if el is not rotulo and el["texto"].strip() and abs(ex - x) <= 80 and y - 100 <= ey < y:
            return interacoes.contagem(el["texto"])
    return None


def anotar_seguidores(xml, agora=None):
    """Guarda os seguidores de hoje (a leitura mais nova do dia); devolve o número ou None."""
    numero = seguidores_na_tela(xml)
    if numero is None:
        return None
    hoje = agora_br(agora).strftime("%Y-%m-%d")

    def anotar(guardado):
        dias = guardado.setdefault("dias", {})
        dias[hoje] = numero
        for dia in sorted(dias)[:-DIAS_DOS_SEGUIDORES]:
            del dias[dia]

    db.atualizar_config(CHAVE_SEGUIDORES, anotar)
    return numero


def _entrada_da_saude(xml):
    """
    Onde tocar no Centro do criador para abrir a Saúde do Vídeo, ou None. No app de antes, o
    nome do quadro Saúde do Vídeo não aceita toque: o que aceita na mesma linha (o "Melhoria
    Necessária", "Bom"...) ou, sem ele, a frase logo abaixo. No de agora (Creator Center,
    04/11/2026), o "Vídeo: ..." do alto da tela.
    """
    elementos = ps.elementos(xml) if xml else []
    rotulo = next((el for el in elementos if ps._normal(el["texto"]) == ps._normal(SAUDE_DO_VIDEO)), None)
    if rotulo:
        x, y = ps._centro(rotulo)
        na_linha = [el for el in elementos
                    if el["clicavel"] and abs(ps._centro(el)[1] - y) <= 60 and ps._centro(el)[0] > x]
        abaixo = [el for el in elementos if el["clicavel"] and y < ps._centro(el)[1] <= y + 200]
        return ps._centro((na_linha or sorted(abaixo, key=lambda el: ps._centro(el)[1]) or [rotulo])[0])
    novo = next((el for el in elementos
                 if any(ps._normal(el[campo]).startswith(ENTRADA_DA_SAUDE) for campo in ("texto", "descricao"))), None)
    return ps._centro(novo) if novo else None


def _na_aba_da_live(xml):
    """A Account Health aberta na aba Live (os pontos das lives), sem a lista dos vídeos?"""
    return any(tem(xml, texto) for texto in NA_ABA_DA_LIVE) and not tem(xml, VIDEOS_DE_VIOLACAO)


def _esperar_a_saude(d):
    """
    Relê a Saúde do Vídeo, que carrega pela rede (os títulos antes do número), até aparecerem os
    Vídeos de Violação e o número do Ponto de Penalidade. Aberta na aba Live (a Account Health),
    toca uma vez na aba Vídeo. Devolve a tela com os Vídeos de Violação (com o número, se ele
    chegou a tempo), ou None.
    """
    vista, trocou = None, False
    voltas = max(1, ESPERA_DA_SAUDE // 3)
    for volta in range(voltas + 1):
        xml = tela(d)
        aba = None if trocou or not _na_aba_da_live(xml) else next(
            (el for el in ps.elementos(xml) if ps._normal(el["texto"]) == ps._normal(ABA_DO_VIDEO)), None)
        if aba:
            d.click(*ps._centro(aba))
            trocou = True
        elif tem(xml, VIDEOS_DE_VIOLACAO):
            vista = xml
            if pontos_de_penalidade(xml) is not None:
                return xml
        if volta < voltas:
            pausa(3)
    return vista


def abrir_saude(d, agora=None):
    """
    Perfil em Shopee Vídeo → Centro do criador → a Saúde do Vídeo (_entrada_da_saude: o quadro do
    app de antes ou o "Vídeo: ..." do de agora) → a aba Vídeo. De passagem pelo Perfil, anota os
    seguidores. Devolve a tela da Saúde; sem o número dos pontos, só se ele não chegou a tempo.
    """
    ir_ao_perfil(d)
    anotar_seguidores(tela(d), agora)
    botao, espera, _quadro = CAMINHO_CENTRO_DO_CRIADOR[0]
    tocar(d, botao, espera)
    xml, ponto = None, None
    voltas = max(1, ESPERA_DA_SAUDE // 3)
    for volta in range(voltas + 1):
        xml = tela(d)
        ponto = _entrada_da_saude(xml)
        if ponto or volta == voltas:
            break
        pausa(3)
    if not ponto:
        raise Parada("o Centro do criador não mostrou a Saúde do Vídeo")
    if ps.proibido_no_ponto(xml, *ponto):
        raise Parada(ps.RECUSA)
    d.click(*ponto)
    pausa(8)
    saude = _esperar_a_saude(d)
    if not saude:
        raise Parada("a Saúde do Vídeo não abriu")
    return saude


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
    xml = abrir_saude(d, agora)
    pontos = pontos_de_penalidade(xml)
    if pontos is None:
        # Sem o número, a página não carregou inteira: a punição que ainda não apareceu pareceria
        # tirada, a suspensão acabada e os pontos zerados. Os da última leitura continuam valendo
        # (a escada dos posts por dia, P145), e a parada guarda o caso com a tela.
        raise Parada(MOTIVO_SEM_OS_PONTOS)
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
            if apelacoes.de_produto(punicao["tipo"]):
                parar_os_produtos_a_mais(punicao, rascunho)
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
        apagar = apelacoes.pedido_para_apagar(p["tipo"])
        avisar(f"❌ Robô da Shopee Vídeo: a Shopee não aceitou o recurso da punição {p['tipo']} ({p['data_punicao']}). "
               "Os pontos dela continuam na Saúde do Vídeo." + (f"\n\n{apagar}" if apagar else ""))
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


# --- Tirar produto no post (P123) ---
# Em Rascunhos do Robô, o Rafael marca os produtos que saem do post (Tirar Produto ➖) e aprova; na
# hora de postar, o robô os tira da tela final pelo X de cada um, confere a tela final e posta. O
# Canal Afiliados e a medição das vendas recebem só os que ficaram, e sempre fica pelo menos 1.
# Escolha do Rafael (02/11, P123): DECISOES.md, Shopee Vídeo.
PROCESSO_DE_TIRAR = "tirar produto no post"


def pode_tirar(rascunho):
    """
    O rascunho deixa tirar produto? Com 2 produtos ou mais, cada um com o seu link: no vídeo de
    link, o do link e os produtos a mais; no Ver Produtos, um link por produto.
    """
    nomes = rascunho.get("produtos") or []
    if len(nomes) < 2:
        return False
    if rascunho.get("links_dos_produtos"):
        return len(rascunho["links_dos_produtos"]) == len(nomes)
    return len(rascunho.get("mais_produtos") or []) + 1 == len(nomes)


def _posicao_da_capa(caminho):
    """A posição do produto (1, 2, ...) pelo nome do arquivo da foto de capa ({ident}_capa_{n}); None se não diz."""
    achado = re.search(r"_capa_(\d+)\.", os.path.basename(caminho or ""))
    return int(achado.group(1)) if achado else None


def com_os_que_ficam(rascunho):
    """
    O rascunho só com os produtos que ficam no post, sem os que o Rafael marcou para tirar: os
    nomes, o link (o do 1º que fica, no vídeo de link), os produtos a mais, os links do Ver
    Produtos, os itens da medição, as fotos de capa e as marcas, renumeradas. A conferência da
    tela final no post, o Canal Afiliados e a medição das vendas saem daqui. Sem marca (ou com
    todas, o que o painel não deixa), o mesmo rascunho.
    """
    nomes = list(rascunho.get("produtos") or [])
    tirar = {n for n in rascunho.get("tirar") or [] if 1 <= n <= len(nomes)}
    ficam = [n for n in range(1, len(nomes) + 1) if n not in tirar]
    if not tirar or not ficam or not pode_tirar(rascunho):
        return rascunho
    nova = {antiga: posicao for posicao, antiga in enumerate(ficam, 1)}

    def por_posicao(lista):
        return [lista[n - 1] for n in ficam] if len(lista) == len(nomes) else list(lista)

    filtrado = dict(rascunho, tirar=[], produtos=por_posicao(nomes), itens=por_posicao(rascunho.get("itens") or []),
                    capas=[c for c in rascunho.get("capas") or [] if _posicao_da_capa(c) not in tirar],
                    outras_capas=[nova[n] for n in rascunho.get("outras_capas") or [] if n in nova],
                    outra_cor=[nova[n] for n in rascunho.get("outra_cor") or [] if n in nova])
    if rascunho.get("links_dos_produtos"):
        # Ver Produtos: o link do rascunho é o do vídeo original; cada produto tem o seu.
        filtrado["links_dos_produtos"] = por_posicao(rascunho["links_dos_produtos"])
    else:
        produtos = por_posicao([{"link": rascunho["link"]}] + list(rascunho.get("mais_produtos") or []))
        filtrado.update(link=produtos[0]["link"], mais_produtos=produtos[1:])
    return filtrado


def campos_que_ficam(filtrado):
    """O que o rascunho postado guarda depois de tirar os produtos marcados (com_os_que_ficam)."""
    return {campo: filtrado[campo] for campo in ("produtos", "link", "mais_produtos", "itens", "capas", "outras_capas",
                                                 "outra_cor", "links_dos_produtos", "tirar") if campo in filtrado}


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

def _videos_da_fonte(config, evitar=(), agora=None):
    """
    Os vídeos da Fonte dos Vídeos do painel que nem o assistente mandou nem o robô usou
    (ids_usados), com link de produto ou de vídeo (Ver Produtos; "de_video" no dicionário),
    fora os de evitar (os que esgotaram as tentativas hoje e os que pagam menos que o mínimo,
    evitar_hoje) e o arquivo que o robô já levou ao Canal Afiliados, que volta pelo Viral (o
    loop; pedido do Rafael, 30/10: DECISOES.md, Shopee Vídeo), do mais novo para o mais velho.
    """
    fonte = config.get("fonte", assistente.FONTE_PADRAO)
    usados = ids_usados(agora) | set(evitar)
    with db.conexao() as con:
        assistente._criar_tabela(con)
        mandados = {linha[0] for linha in con.execute("SELECT id_unico FROM shopee_video_enviados")}
    for id_video, arquivo, link, legenda in assistente._candidatos(fonte if fonte in assistente.FONTES
                                                                      else assistente.FONTE_PADRAO):
        if (id_video in mandados or id_video in usados or not arquivo or not link
                or not os.path.exists(arquivo) or arquivo.lower().endswith(assistente.EXTENSOES_DE_IMAGEM)
                or pedidos_do_canal.ja_foi_ao_canal(arquivo)):
            continue
        yield {"id": id_video, "arquivo": os.path.abspath(arquivo), "link": link, "nome": nome_da_legenda(legenda),
               "de_video": eh_video(asyncio.run(link_para_converter(link)))}


def proximo_video(config, evitar=(), agora=None):
    """O próximo vídeo da fonte (_videos_da_fonte), ou None sem nenhum."""
    return next(_videos_da_fonte(config, evitar, agora), None)


# Escolha do Rafael (10/11, P194 1): de 25/09 a 09/11, 2 produtos deram 70% da comissão, e os posts
# do robô ainda não tinham vendido. Entre os próximos VIDEOS_NA_ESCOLHA vídeos da fonte, o robô
# escolhe o de produto que paga mais por venda (o preço vezes a comissão do produto do link, pela API
# de afiliado) e deixa de lado, só no dia, o que paga menos de MINIMO_POR_VENDA reais (no dia
# seguinte ele é visto de novo: o preço e a comissão mudam). O vídeo de vários produtos (o link é de
# um vídeo, e os produtos ficam no Ver Produtos, que só o celular lê), o de produto sem oferta e o de
# produto já postado ficam na vez deles, como antes (o primeiro vira rascunho; os outros ficam de
# lado): um produto antes deles na fila só passa na frente se pagar o mínimo. O registro diz só
# posições e contagens (o checkup é público); o valor vai no rascunho (coluna valor). O de vários
# produtos passa pelo mínimo depois de aberto no celular (P200 1, conferir_o_minimo_do_ver_produtos).
# DECISOES.md, Shopee Vídeo.
VIDEOS_NA_ESCOLHA = 10
MINIMO_POR_VENDA = 2.0
PROCESSO_DA_ESCOLHA = "escolha pelo valor por venda"
# O vídeo de link de vídeo (Ver Produtos, com 1 produto ou vários) vai na vez dele e, aberto no celular,
# com o valor por venda de cada produto da lista (os do criador e os trocados pela loja que paga mais,
# trocar_os_do_ver_produtos), fica de lado só no dia se o que paga mais pagar menos de MINIMO_POR_VENDA,
# antes de anexar (o descurtir do fim tira o que ele curtiu), e o horário passa ao próximo vídeo. Não é
# falha: sem caso guardado, e a tentativa entra como "de lado". Sem o valor de nenhum (a API não achou
# nenhum pelo nome), segue como antes. Escolha do Rafael (11/11, P200 1): DECISOES.md, Shopee Vídeo.
MOTIVO_VER_PRODUTOS_ABAIXO = "os produtos do Ver Produtos pagam menos que o mínimo por venda"


class DeLadoNoDia(Parada):
    """O vídeo fica de lado só hoje pelo que paga (P200 1): o horário passa ao próximo vídeo, sem ser falha."""

    def __init__(self, motivo):
        super().__init__(motivo, do_video=True)


def melhor_valor_do_ver_produtos(produtos):
    """
    O que paga mais por venda entre os produtos do Ver Produtos, ou None sem o valor de nenhum: o 0 é a
    oferta que a API não achou pelo nome (ou sem o preço ou a comissão), não um produto que paga 0.
    """
    valores = [p["valor"] for p in produtos or [] if (p.get("valor") or 0) > 0]
    return max(valores) if valores else None


def conferir_o_minimo_do_ver_produtos(produtos):
    """DeLadoNoDia quando o que paga mais do Ver Produtos paga menos que MINIMO_POR_VENDA (P200 1); senão, nada."""
    melhor = melhor_valor_do_ver_produtos(produtos)
    if melhor is None or melhor >= MINIMO_POR_VENDA:
        return
    registro_processos.registrar(REGISTRO, PROCESSO_DA_ESCOLHA, "Ver Produtos abaixo do mínimo - de lado no dia",
                                 f"{len(produtos)} produto(s)", ok=None)
    raise DeLadoNoDia(f"{MOTIVO_VER_PRODUTOS_ABAIXO} (o que paga mais: {assistente._reais(melhor)} por venda)")
SEM_VIDEO_NA_FONTE = "nenhum vídeo da fonte com arquivo e link de produto para um rascunho"


def de_onde_veio_o_video(video, fonte):
    """A linha do aviso do começo do rascunho que diz qual vídeo da fonte o robô pegou (P194 1)."""
    nome_da_fonte = assistente.FONTES.get(fonte, fonte)
    if video.get("valor") is not None:
        return (f"Vídeo: o que paga mais por venda ({assistente._reais(video['valor'])}) entre os próximos "
                f"{VIDEOS_NA_ESCOLHA} de {nome_da_fonte} ainda não usados.")
    return f"Vídeo: o mais novo de {nome_da_fonte} ainda não usado."


def evitar_hoje(config, agora=None):
    """Os vídeos que ficam fora da escolha hoje: os que esgotaram as tentativas e os abaixo do mínimo."""
    estado = estado_do_dia(config, agora)
    return estado.get("evitar", []) + estado.get("abaixo_do_minimo", [])


def _deixar_de_lado_no_dia(ids, config, agora=None):
    """Os vídeos que pagam menos que o mínimo ficam fora da escolha só hoje (no plano do dia)."""
    if not ids:
        return
    estado = estado_do_dia(config, agora)
    estado["abaixo_do_minimo"] = sorted(set(estado.get("abaixo_do_minimo", [])) | set(ids))
    db.salvar_config(CHAVE_DIA, estado)


def _produto_do_link_do_video(video):
    """O produto do link do vídeo pela API de afiliado ({nome, preco, comissao, item}), ou None sem a oferta."""
    produtos, _ = asyncio.run(assistente.produtos_do_link(video["link"]))
    return produtos[0] if produtos else None


def escolher_o_video(config, evitar=(), agora=None, ja_postados=None):
    """
    (o vídeo do próximo rascunho, ""), ou (None, o porquê) sem nenhum (P194 1). O de produto ganha
    "valor" (o que paga por venda) e "posicao" (na fila dos próximos VIDEOS_NA_ESCOLHA).
    """
    candidatos = list(itertools.islice(_videos_da_fonte(config, evitar, agora), VIDEOS_NA_ESCOLHA))
    if not candidatos:
        return None, SEM_VIDEO_NA_FONTE
    ja_postados = produtos_ja_postados() if ja_postados is None else ja_postados
    melhores, abaixo = [], []
    for posicao, video in enumerate(candidatos, 1):
        if not video["de_video"]:
            produto = _produto_do_link_do_video(video)
            if produto and str(produto.get("item") or "") not in ja_postados:
                valor = valor_por_venda(assistente._numero(produto.get("preco")),
                                        assistente._numero(produto.get("comissao")))
                if valor < MINIMO_POR_VENDA:
                    abaixo.append(video["id"])
                else:
                    melhores.append((valor, -posicao, posicao, video))
                continue
        # O de vários produtos, o sem oferta e o já postado: na vez deles, se nenhum antes paga o mínimo.
        if melhores:
            break
        _deixar_de_lado_no_dia(abaixo, config, agora)
        registro_processos.registrar(REGISTRO, PROCESSO_DA_ESCOLHA,
                                     "na vez dele: " + ("vídeo de vários produtos" if video["de_video"]
                                                        else "sem oferta ou já postado"),
                                     f"o {posicao}º de {len(candidatos)}; {len(abaixo)} abaixo do mínimo",
                                     ok=None)
        return video, ""
    _deixar_de_lado_no_dia(abaixo, config, agora)
    if not melhores:
        registro_processos.registrar(REGISTRO, PROCESSO_DA_ESCOLHA, "todos abaixo do mínimo",
                                     f"{len(abaixo)} de {len(candidatos)}", ok=None)
        return None, f"os próximos {len(candidatos)} vídeos da fonte pagam menos que o mínimo por venda"
    valor, _, posicao, video = max(melhores, key=lambda melhor: melhor[:2])
    registro_processos.registrar(REGISTRO, PROCESSO_DA_ESCOLHA, "o que paga mais",
                                 f"o {posicao}º de {len(candidatos)}; {len(abaixo)} abaixo do mínimo",
                                 ok=True)
    return dict(video, valor=valor, posicao=posicao), ""


# O Preparar 1 Agora ⚡ que cai num vídeo com problema próprio (em análise na Shopee, a foto do
# produto que a busca não acha, a IA que não confirma o produto) passa sozinho ao próximo vídeo,
# até VIDEOS_DO_PEDIDO, como os horários do plano, com o aviso de cada um que fica de lado. O
# próximo só começa com tempo para um rascunho inteiro na rodada: o painel a interrompe em
# MAXIMO_DA_RODADA, contados do começo dela, e um rascunho leva até MINUTOS_DE_UM_RASCUNHO com os
# produtos a mais (os prazos deles, de MINUTOS_PARA_ANEXAR_OS_A_MAIS, mais o fim) e até
# MINUTOS_DE_UM_RASCUNHO_SEM_OS_A_MAIS sem eles (desligados no painel ou pelos pontos, P145: os
# tempos do registro "tempo do rascunho" ficam de 5 a 15 min). Escolha do Rafael (02/11, P133):
# DECISOES.md, Shopee Vídeo.
VIDEOS_DO_PEDIDO = VIDEOS_POR_HORARIO
MINUTOS_DE_UM_RASCUNHO = 25
MINUTOS_DE_UM_RASCUNHO_SEM_OS_A_MAIS = 15


def minutos_de_um_rascunho():
    """Quanto um rascunho pode levar agora: MINUTOS_DE_UM_RASCUNHO com os produtos a mais; sem eles, menos."""
    return MINUTOS_DE_UM_RASCUNHO_SEM_OS_A_MAIS if sem_os_a_mais() else MINUTOS_DE_UM_RASCUNHO


def preparar_o_pedido(d, config, agora=None, comeco=None):
    """
    O rascunho do Preparar 1 Agora: preparar_rascunho com o próximo vídeo a cada Parada do
    próprio vídeo, até VIDEOS_DO_PEDIDO vídeos, enquanto cabe outro rascunho na rodada e a fonte
    tem outro vídeo. O que não é do vídeo (o celular, a Verificação, a suspensão, o app) para
    tudo, como antes; a Parada do último vídeo sobe com o motivo dele, dizendo qual vídeo era e
    por que não houve outro, para a resposta no privado. comeco: o time.monotonic() do começo
    da rodada, de onde o painel conta MAXIMO_DA_RODADA (sem ele, agora). O registro diz em que
    minuto da rodada cada próximo vídeo começou ou ficou sem tempo (só números).
    """
    comeco = time.monotonic() if comeco is None else comeco
    for vez in range(1, VIDEOS_DO_PEDIDO + 1):
        try:
            return preparar_rascunho(d, config, agora)
        except Parada as e:
            if not e.do_video:
                raise
            qual = f"o vídeo {vez} de {VIDEOS_DO_PEDIDO} {'também ' if vez > 1 else ''}ficou de lado: "
            if vez == VIDEOS_DO_PEDIDO:
                e.motivo = qual + e.motivo
                raise
            passados, minutos = time.monotonic() - comeco, minutos_de_um_rascunho()
            if passados > MAXIMO_DA_RODADA - minutos * 60:
                registro_processos.registrar(REGISTRO, PROCESSO_DO_BOTAO, "sem tempo para outro vídeo",
                                             f"aos {_minutos(passados)} min da rodada; um rascunho leva até "
                                             f"{minutos} min", ok=None, agora=agora)
                e.motivo = (f"{qual}{e.motivo}; não há tempo para outro vídeo nesta rodada, toque de novo em "
                            "Preparar 1 Agora ⚡")
                raise
            if not proximo_video(config, evitar_hoje(config, agora), agora):
                e.motivo = f"{qual if vez > 1 else ''}{e.motivo}; a fonte não tem outro vídeo para tentar"
                raise
            registro_processos.registrar(REGISTRO, PROCESSO_DO_BOTAO, "próximo vídeo",
                                         f"o {vez + 1}º, aos {_minutos(passados)} min da rodada", ok=None, agora=agora)
            avisar(f"⚠️ Robô da Shopee Vídeo: o vídeo {vez} de {VIDEOS_DO_PEDIDO} do rascunho que você pediu ficou "
                   f"de lado ({e.motivo}). Vou para o próximo vídeo.")


def preparar_rascunho(d, config, agora=None):
    """
    Um rascunho novo, do vídeo da fonte até Rascunhos, com todas as conferências. O vídeo
    fica reservado (o assistente não o pega) enquanto o robô trabalha nele.

    Antes de tocar no celular, o vídeo cujo produto não tem oferta de afiliado (a API não
    diz o produto: não paga comissão) fica de lado, e o robô passa ao próximo na mesma
    rodada, sem gastar a tentativa do horário. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    evitar = evitar_hoje(config, agora)
    ja_postados = produtos_ja_postados()
    for _ in range(VIDEOS_SEM_OFERTA_POR_RODADA):
        # O de produto que paga mais por venda entre os próximos da fonte (P194 1).
        video, sem_video = escolher_o_video(config, evitar, agora, ja_postados)
        if not video:
            registrar_tentativa("rascunho", "sem vídeo", sem_video, agora=agora)
            return sem_video
        # No link de vídeo, os produtos vêm do Ver Produtos, no celular.
        if video["de_video"]:
            break
        motivo = SEM_OFERTA
        if ps.nome_do_produto(video):
            # O produto do link que já foi ao ar não se repete (P166 1).
            video["item_do_link"] = item_do_video(video)
            if video["item_do_link"] not in ja_postados:
                break
            motivo = PRODUTO_JA_POSTADO
            anotar_onde_ja_foi(video["item_do_link"], "robô")
        atualizar(criar(video["id"], agora), estado="pulado", motivo=motivo)
        registrar_tentativa("rascunho", "pulado", motivo, agora=agora)
    else:
        resultado = (f"os próximos {VIDEOS_SEM_OFERTA_POR_RODADA} vídeos da fonte são de produtos sem oferta de "
                     "afiliado ou já postados")
        registrar_tentativa("rascunho", "sem vídeo", resultado, agora=agora)
        return resultado
    ident = criar(video["id"], agora)
    if video.get("valor") is not None:
        # O que o produto do link paga por venda, para a medição da escolha (P194 1).
        atualizar(ident, valor=f"{video['valor']:.2f}")
    assistente.registrar(video["id"], "robo", "rascunho do robô", agora)
    # curtidos: os produtos que o robô curtiu (descurtir_no_fim); celular: se ele já usou o
    # celular (o caso só lê a tela quando ela é deste rascunho).
    curtidos, celular = [], []
    comeco = time.monotonic()
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
        # O de lado no dia pelo que paga (P200 1) não é falha: sem caso, e o vídeo volta amanhã.
        de_lado = isinstance(e, DeLadoNoDia)
        resultado = "de lado" if de_lado else "pulado" if e.do_video else "parou"
        if de_lado:
            _deixar_de_lado_no_dia([video["id"]], config, agora)
        else:
            _guardar_caso(d if celular else None, "rascunho", resultado, e.motivo, video, ident, agora)
        _desfazer_reserva(ident, video["id"], e.motivo, e.do_video and not de_lado)
        registrar_tentativa("rascunho", resultado, e.motivo, _produto_do_video(video), agora)
        e.id_video = video["id"]
        if celular and e.motivo.startswith(MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU):
            # Com o caso já guardado com a tela da falha: o app aberto há muitas horas é fechado e
            # reaberto (P193 1), e o descurtir do fim já vai no app novo.
            try:
                reabrir_o_app_aberto_ha_muito_tempo(d)
            except Verificacao:
                if curtidos:
                    gravar_estado(favoritos_limpos=False)
                raise
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
    produtos = (pegar(ident) or {}).get("produtos") or []
    registrar_tentativa("rascunho", "salvo", produto=", ".join(produtos) or _produto_do_video(video), agora=agora)
    registro_processos.registrar(REGISTRO, PROCESSO_DO_TEMPO, faixa_do_tempo(time.monotonic() - comeco),
                                 f"{max(len(produtos), 1)} produto(s)")
    descurtir_no_fim(d, video, curtidos)
    return "rascunho salvo"


# O tempo de cada rascunho salvo, em faixas de 5 min, com quantos produtos ele levou: a régua
# dos prazos do rascunho (MINUTOS_PARA_OS_ESPACOS e MINUTOS_PARA_ANEXAR_OS_A_MAIS) dentro da
# rodada (MAXIMO_DA_RODADA). Só números no registro.
PROCESSO_DO_TEMPO = "tempo do rascunho"


def faixa_do_tempo(segundos):
    """A faixa de 5 min em que cai o tempo (ex.: 754 s → "10 a 15 min")."""
    comeco = int(segundos // 300) * 5
    return f"{comeco} a {comeco + 5} min"


def descurtir_no_fim(d, video, curtidos):
    """
    O fim de cada rascunho, salvo ou não: descurte os produtos que o robô curtiu nele
    (curtidos: (NoVerProdutos, nome), pelo cartão da lista do Ver Produtos, ou (link, nome), pelo
    link, com os produtos a mais da P59; o link None é o do vídeo), pelo mesmo caminho do curtir. A
    curtida só serve para o produto subir em Minhas Curtidas; o rascunho salvo guarda o
    produto anexado, e o postar confere a tela final antes de tocar em Postar. O que não
    descurtir aqui fica para o descurtir das 4h. A Verificação da Shopee segue parando
    tudo; a conta suspensa não passa por aqui (o robô não toca no celular nela).
    Pedido do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if not curtidos:
        return
    todos = False
    try:
        # Os curtidos pela lista do Ver Produtos são achados de novo nela, pelo nome do cartão (os
        # do Ver Mais também); os outros, um por um, pelo link de cada um. A lista só fica limpa
        # se todos descurtirem.
        pela_lista = [(onde.cartao, nome) for onde, nome in curtidos if isinstance(onde, NoVerProdutos)]
        descurtidos = 0
        if pela_lista:
            _abrir_ver_produtos(d, video)
        for cartao, nome in pela_lista:
            achado = _achar_cartao(d, lambda texto, cartao=cartao: texto == cartao, {cartao})
            if not achado or ps.proibido_no_ponto(achado[2], *achado[1]):
                registro_processos.registrar(REGISTRO, "descurtir no fim do rascunho", "produto fora da lista",
                                             ok=False)
                continue
            d.click(*achado[1])
            pausa(8)
            xml = tela(d)
            if ps.nome_na_pagina_do_produto(xml) == nome:
                descurtidos += ps.descurtir_na_pagina(d, xml)[0]
            else:
                registro_processos.registrar(REGISTRO, "descurtir no fim do rascunho", "outro produto no cartão",
                                             ok=False)
            d.press("back")
            pausa(4)
        for link, _nome in [(onde, nome) for onde, nome in curtidos if not isinstance(onde, NoVerProdutos)]:
            link = link or video["link"]
            ir_ao_inicio(d)
            ps.limpar_aviso_rapido(d)
            ps.abrir_link(d, link)
            pausa(8)
            descurtidos += ps.descurtir(d, dict(video, link=link))[0]
        todos = descurtidos == len(curtidos)
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


MOTIVO_DA_RODADA_INTERROMPIDA = "a rodada foi interrompida no meio do preparo"


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
        # O caso leva o que a rodada morta anotou desde o começo do rascunho: o último passo
        # diz onde ela parou. Sem o celular: quem vai usá-lo agora é a rodada de agora.
        _guardar_caso(None, "rascunho", "parou", MOTIVO_DA_RODADA_INTERROMPIDA, ident=rascunho["id"], agora=agora)
        _desfazer_reserva(rascunho["id"], rascunho["id_video"], "a rodada foi interrompida", False)
        registrar_tentativa("rascunho", "parou", MOTIVO_DA_RODADA_INTERROMPIDA, agora=agora)
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


def _motivo_da_ia(textos=None):
    """
    Por que a IA não deu o título, em códigos fixos do Google (nunca o texto dela): a resposta
    vazia traz o finish_reason (SAFETY, RECITATION, MAX_TOKENS...) ou o block_reason; a cota
    e os outros erros vêm do ULTIMO_ERRO_IA; sem erro, a IA respondeu sem o JSON (textos None)
    ou com o JSON sem o título.
    """
    erro = ps.api_gemini.ULTIMO_ERRO_IA or ""
    codigos = _codigos_da_ia()
    if codigos:
        return f"resposta vazia ({', '.join(codigos)})"
    if "VAZIO" in erro:
        return "resposta vazia"
    if re.search(r"429|RESOURCE_EXHAUSTED|quota", erro, re.I):
        return "cota da IA"
    if erro:
        return "erro da IA"
    return "resposta sem o título" if textos is not None else "resposta sem o JSON"


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
    comeco = time.monotonic()
    ps.api_gemini.zerar_tempos_da_ia()
    try:
        for vez in range(TENTATIVAS_DO_TITULO):
            ps.api_gemini.ULTIMO_ERRO_IA, assistente.ULTIMA_RECUSA = None, None
            textos = asyncio.run(assistente.textos_do_video(video["arquivo"], video.get("nome") or ""))
            recusa = assistente.ULTIMA_RECUSA or recusa
            if textos and textos.get("violacao"):
                # A IA viu violação das diretrizes, e o título costuma vir vazio: quem chama pula o
                # vídeo e avisa o Rafael, sem gastar as tentativas do horário no mesmo vídeo (um kit
                # de calcinhas voltou assim 4 vezes seguidas na madrugada de 03/11).
                return textos
            if textos and textos["titulo"]:
                if textos.get("regras_leves"):
                    registro_processos.registrar(REGISTRO, "título da IA", "veio com as regras em palavras leves",
                                                 ok=True)
                elif vez:
                    registro_processos.registrar(REGISTRO, "título da IA", "veio na nova tentativa", ok=True)
                else:
                    # O de primeira também conta: sem ele, o checkup via só as falhas e cobrava o
                    # passo como se ele nunca desse certo.
                    registro_processos.registrar(REGISTRO, "título da IA", "veio de primeira", ok=True)
                return textos
            motivo = _motivo_da_ia(textos)
            registro_processos.registrar(REGISTRO, "título da IA", "sem título", motivo, ok=False)
            if BLOQUEIOS_DO_CONTEUDO & set(_codigos_da_ia()):
                raise Parada(f"a IA não devolveu o título ({motivo}, também com as regras em palavras leves): o "
                             "Google bloqueia o conteúdo deste vídeo", do_video=True)
            if vez + 1 < TENTATIVAS_DO_TITULO:
                pausa(ESPERA_DO_TITULO)
        raise Parada(f"a IA não devolveu o título ({motivo})")
    finally:
        _anotar_lentidao_da_ia(time.monotonic() - comeco)
        # Uma vez por vídeo, com o que deu por último (o Rafael vê a causa da recusa).
        if recusa:
            _avisar_recusa(video, nomes, recusa)


def _anotar_lentidao_da_ia(segundos):
    """
    Os textos da IA que passaram de LENTIDAO_DA_IA vão ao registro com onde o tempo foi, como
    "15 min: 2 análises, envio 70 s, processamento do Google 12 min, resposta 90 s (3 modelos),
    fora da IA 20 s" (só números).
    """
    if segundos < LENTIDAO_DA_IA:
        return
    tempos = ps.api_gemini.TEMPOS_DA_IA
    na_ia = tempos["envio"] + tempos["processamento"] + tempos["resposta"]
    registro_processos.registrar(
        REGISTRO, "título da IA", "demorou",
        f"{_duracao(segundos)}: {tempos['analises']} análise{'s' if tempos['analises'] != 1 else ''}, "
        f"envio {_duracao(tempos['envio'])}, processamento do Google {_duracao(tempos['processamento'])}, "
        f"resposta {_duracao(tempos['resposta'])} ({tempos['modelos']} modelo{'s' if tempos['modelos'] != 1 else ''}), "
        f"fora da IA {_duracao(max(segundos - na_ia, 0))}")


def _duracao(segundos):
    """O tempo em segundos até 2 min e em minutos depois (ex.: 70 → "70 s", 720 → "12 min")."""
    return f"{round(segundos)} s" if segundos < 120 else f"{round(segundos / 60)} min"


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
# O produto que saiu da loja fica na lista com o selo "Inválido" na foto, e o Like não o tira
# (29/10/2026, Motorola): sobrando só ele, a lista acabou. Na linha dos filtros há também um
# filtro com o mesmo nome, que não é selo de produto.
SELO_INVALIDO = "Inválido"
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


def produtos_invalidos(xml):
    """Quantos produtos da tela têm o selo Inválido (o filtro Inválido, na linha do Melhor Oferta, não conta)."""
    lista = ps.elementos(xml)
    filtro = next((el["caixa"] for el in lista if ps._normal(el["texto"]) == ps._normal(FILTRO_DOS_FAVORITOS)), None)
    return sum(1 for el in lista if ps._normal(el["texto"]) == ps._normal(SELO_INVALIDO)
               and not (filtro and filtro[1] <= ps._centro(el)[1] <= filtro[3]))


def so_invalidos(xml):
    """Todos os produtos da tela (pelo menos um) têm o selo Inválido."""
    produtos = caixas_de_marcar(xml)[1]
    return bool(produtos) and produtos_invalidos(xml) >= len(produtos)


def _so_restam_invalidos(d, xml):
    """
    Quantos produtos inválidos sobraram, quando só eles sobraram em Meus favoritos: os da tela
    são todos inválidos e, rolando uma vez, não aparece outro. 0 quando há outros produtos.
    """
    if not so_invalidos(xml):
        return 0
    quantos = produtos_invalidos(xml)
    ps.rolar(d)
    pausa(2)
    depois = tela(d)
    if caixas_de_marcar(depois)[1] and not so_invalidos(depois):
        return 0
    return max(quantos, produtos_invalidos(depois))


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
    que está curtido (_descurtir_os_de_afiliado) e, com essa lista acabada, também o que está em
    Meus Favoritos de comprador (limpar_favoritos_de_comprador, P137 1). O que para no meio fica
    para a rodada seguinte (_limpeza_de_novo). Escolhas do Rafael (P25, P137 e o caminho que ele
    ensinou): DECISOES.md, Shopee Vídeo.
    """
    resultado, acabou = _descurtir_os_de_afiliado(d, agora)
    if not acabou:
        return resultado
    return f"{resultado}; {limpar_favoritos_de_comprador(d, agora)}"


def _descurtir_os_de_afiliado(d, agora=None):
    """
    Tira de Meus favoritos (a lista de afiliado, a do Minhas Curtidas) tudo o que está curtido:
    Eu → Criadores & Afiliados → Meus favoritos → marcar → Like, até a lista acabar. Sobrou
    depois de VOLTAS_DO_DESCURTIR voltas: a rodada seguinte, na mesma hora, continua. O produto
    inválido (que saiu da loja), que o Like não tira, fica: sobrando só ele, a lista acabou. Só
    números no registro, nunca o nome dos produtos. (o que dizer, se a lista acabou)
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
    fora = "" if na_hora_do_descurtir(agora) else FORA_DA_HORA
    if pagina == "vazia":
        registro_processos.registrar(REGISTRO, "descurtir tudo (4h)", "nada curtido", fora, ok=True)
        gravar_estado(favoritos_limpos=True)
        ir_ao_inicio(d)
        return "nada curtido em Meus favoritos", True
    removidos, acabou, invalidos = 0, False, 0
    for _volta in range(VOLTAS_DO_DESCURTIR):
        xml = tela(d)
        if not caixas_de_marcar(xml)[1]:
            acabou = True
            break
        invalidos = _so_restam_invalidos(d, xml)
        if invalidos:
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
        xml = tela(d)
        restantes = _marcados(xml)
        if restantes >= marcados:
            # Os mesmos continuam marcados: o Like não tirou. Sendo só os inválidos, a lista
            # acabou; com outros, é uma pergunta do app que o robô não conhece, por exemplo.
            invalidos = _so_restam_invalidos(d, xml)
            if invalidos:
                acabou = True
                break
            raise Parada(f"toquei em Like, mas os produtos marcados continuaram em Meus favoritos "
                         f"({marcados} marcado(s); {produtos_invalidos(xml)} inválido(s) na tela)")
        # O inválido marcado junto continua marcado depois do Like: não conta como tirado.
        removidos += marcados - restantes
    else:
        xml = tela(d)
        invalidos = _so_restam_invalidos(d, xml) if caixas_de_marcar(xml)[1] else 0
        acabou = not caixas_de_marcar(xml)[1] or bool(invalidos)
    gravar_estado(descurtir_continuar=not acabou, favoritos_limpos=acabou)
    ir_ao_inicio(d)
    ficam = f"; {invalidos} inválido(s) ficam" if invalidos else ""
    registro_processos.registrar(REGISTRO, "descurtir tudo (4h)", "descurtido" if acabou else "continua depois",
                                 f"{removidos} produto(s){ficam}" + (f"; {fora}" if fora else ""),
                                 ok=True if acabou else None)
    if not acabou:
        return f"{removidos} produto(s) descurtido(s) em Meus favoritos; o resto fica para a próxima rodada", False
    return (f"{removidos} produto(s) descurtido(s) em Meus favoritos"
            + (f"; {invalidos} inválido(s) ficam (o Like não tira produto que saiu da loja)" if invalidos else "")), True


# Meus Favoritos de comprador (aba Eu → Meus Favoritos, a tela Visualização do Comprador): a
# lista do coração da página do produto, que o robô curte para o Adicionar Produto e descurte no
# fim do rascunho; o que não descurtiu ali ficava para sempre. A limpeza tira também esses (P137
# 1): Editar (o app guarda a edição aberta: com o "Selecionado N/50" na tela, ela já está), a
# caixa de marcar tudo da barra de baixo (até 50 de cada vez), Remover dos Favoritos e o Sim da
# pergunta, até a lista acabar; no fim, Feito. O carrinho do alto e o de cada produto (que só
# aparecem fora da edição) nunca são tocados. Mapa no Motorola em 02/11/2026 (o explorar):
# roteiro. Escolha do Rafael (P137 1): DECISOES.md, Shopee Vídeo.
FAVORITOS_DE_COMPRADOR = "Meus Favoritos"         # na aba Eu; o de afiliado fica em Criadores & Afiliados
TITULO_DE_COMPRADOR = "Visualização do Comprador"
EDITAR_FAVORITOS, FEITO_FAVORITOS = "Editar", "Feito"
REMOVER_DOS_FAVORITOS = "Remover dos Favoritos"
PROCESSO_DE_COMPRADOR = "descurtir em Meus Favoritos (comprador)"
# A página aberta sem o Editar nem a seleção, até o fim desta espera: a lista está vazia.
ESPERA_DA_EDICAO = 9


def _marcar_tudo_de_comprador(xml):
    """O centro da caixa de marcar tudo (a caixa à esquerda do "Selecionado N/M", na mesma linha); None sem ela."""
    lista = ps.elementos(xml)
    texto = next((el for el in lista if re.match(r"selecionado", el["texto"].strip(), re.I)), None)
    if not texto:
        return None
    x1, y1, _x2, y2 = texto["caixa"]
    meio = (y1 + y2) // 2
    caixas = [el["caixa"] for el in lista if el.get("clicavel") and el["caixa"][1] <= meio <= el["caixa"][3]
              and el["caixa"][2] <= x1 + 2 and el["caixa"][2] - el["caixa"][0] <= 2 * (y2 - y1) + 20]
    if not caixas:
        return None
    caixa = max(caixas, key=lambda c: c[2])
    return (caixa[0] + caixa[2]) // 2, (caixa[1] + caixa[3]) // 2


def _edicao_de_comprador(d):
    """
    A tela de Meus Favoritos de comprador na edição (com o "Selecionado N/M"): toca no Editar
    quando a edição está fechada. None quando a página não tem nem o Editar nem a seleção até o fim
    da espera (a lista vazia).
    """
    voltas = max(1, ESPERA_DA_EDICAO // 3)
    for volta in range(voltas + 1):
        xml = tela(d)
        if selecionados(xml):
            return xml
        ponto = _ponto_exato(xml, EDITAR_FAVORITOS)
        if ponto:
            if not _seguro(xml, ponto):
                raise Parada("o Editar de Meus Favoritos de comprador caiu num lugar proibido")
            d.click(*ponto)
            pausa(3)
            xml = esperar_na_tela(d, "Selecionado", ESPERA_DA_EDICAO)
            if not xml:
                raise Parada("o Editar de Meus Favoritos de comprador não abriu a seleção")
            return xml
        if volta < voltas:
            pausa(3)
    return None


def limpar_favoritos_de_comprador(d, agora=None):
    """
    Tira tudo de Meus Favoritos de comprador (o comentário acima), em VOLTAS_DO_DESCURTIR voltas,
    e devolve o que dizer. Para (Parada) quando a tela não é a esperada; a limpeza tenta de novo
    (_limpeza_de_novo). Só números no registro.
    """
    fora = "" if na_hora_do_descurtir(agora) else FORA_DA_HORA
    ir_ao_inicio(d)
    tocar(d, "Eu", 5)
    xml = tela(d)
    ponto = _ponto_exato(xml, FAVORITOS_DE_COMPRADOR)
    if not ponto:
        ps.rolar(d)
        pausa(2)
        xml = tela(d)
        ponto = _ponto_exato(xml, FAVORITOS_DE_COMPRADOR)
    if not ponto or not _seguro(xml, ponto):
        raise Parada("não achei Meus Favoritos na aba Eu")
    d.click(*ponto)
    pausa(5)
    if not esperar_na_tela(d, TITULO_DE_COMPRADOR, ESPERA_A_MAIS_NO_CAMINHO):
        raise Parada("Meus Favoritos de comprador não abriu")
    removidos, acabou = 0, False
    for _volta in range(VOLTAS_DO_DESCURTIR):
        xml = _edicao_de_comprador(d)
        if xml is None:
            acabou = True
            break
        marcados = _marcados(xml)
        if not marcados:
            ponto = _marcar_tudo_de_comprador(xml)
            if not ponto or not _seguro(xml, ponto):
                raise Parada("Meus Favoritos de comprador sem a caixa de marcar tudo")
            d.click(*ponto)
            pausa(2)
            xml = tela(d)
            marcados = _marcados(xml)
        if not marcados:
            acabou = True
            break
        ponto = _ponto_exato(xml, REMOVER_DOS_FAVORITOS)
        if not ponto or not _seguro(xml, ponto):
            raise Parada("Meus Favoritos de comprador sem o Remover dos Favoritos")
        d.click(*ponto)
        pausa(3)
        _confirmar_remocao(d)
        pausa(2)
        # Com a pergunta ainda aberta, a tela só tem ela (sem o título da página).
        depois = esperar_na_tela(d, TITULO_DE_COMPRADOR, ESPERA_DA_EDICAO)
        if not depois:
            raise Parada("depois do Remover dos Favoritos, a página de Meus Favoritos de comprador não voltou")
        if selecionados(depois) and _marcados(depois) >= marcados:
            raise Parada(f"toquei em Remover dos Favoritos, mas os {marcados} marcado(s) continuaram em Meus "
                         "Favoritos de comprador")
        removidos += marcados
    # A edição fica fechada, como estava antes da limpeza (o app a guarda aberta).
    xml = tela(d)
    ponto = _ponto_exato(xml, FEITO_FAVORITOS)
    if ponto and _seguro(xml, ponto):
        d.click(*ponto)
        pausa(2)
    ir_ao_inicio(d)
    detalhe = f"{removidos} produto(s)" + (f"; {fora}" if fora else "")
    if not acabou:
        registro_processos.registrar(REGISTRO, PROCESSO_DE_COMPRADOR, "continua depois", detalhe, ok=None)
        gravar_estado(descurtir_continuar=True)
        return f"{removidos} produto(s) tirado(s) de Meus Favoritos de comprador; o resto fica para a próxima rodada"
    registro_processos.registrar(REGISTRO, PROCESSO_DE_COMPRADOR, "removido" if removidos else "nada curtido",
                                 detalhe, ok=True)
    if not removidos:
        return "nada em Meus Favoritos de comprador"
    return f"{removidos} produto(s) tirado(s) de Meus Favoritos de comprador"


# --- O mesmo produto com mais comissão (P33) ---

PROCESSO_DA_COMISSAO = "comissão: o mesmo produto que paga mais"


def termo_da_busca(nome):
    """
    As primeiras PALAVRAS_DA_BUSCA palavras do nome, sem o "0" do selo da loja colado, sem o
    que vem entre colchetes ou parênteses e sem símbolos.
    """
    limpo = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", ps.sem_o_selo_colado(nome))
    palavras = [p for p in re.sub(r"[^\w\s-]", " ", limpo).split() if p.strip("-_")]
    return " ".join(palavras[:PALAVRAS_DA_BUSCA])


def valor_por_venda(preco, comissao):
    """O que o Rafael recebe numa venda: o preço vezes a comissão (em %, com a Comissão Extra)."""
    return preco * comissao / 100


def candidatos_de_mais_comissao(original, ofertas):
    """
    Das ofertas da busca, as que pagam mais por venda que o produto do link, custam até
    MAIS_CARO_NA_TROCA% a mais que ele e têm o nome parecido com o dele, da que paga mais
    por venda para a que paga menos: [{nome, link, comissao, preco, valor, vendas}]. O preço
    é o "a partir de" dos dois lados. O próprio produto do link nunca entra: ele não paga
    mais que ele mesmo. Sem o preço do produto do link, nenhuma: não há com o que comparar.
    Escolha do Rafael (28/10, P58): DECISOES.md, Shopee Vídeo.
    """
    antes = valor_por_venda(original["preco"], original["comissao"])
    # Em centavos, como o preço: o anúncio exatamente MAIS_CARO_NA_TROCA% mais caro ainda entra.
    teto = round(original["preco"] * (1 + MAIS_CARO_NA_TROCA / 100), 2)
    candidatos = []
    for oferta in ofertas:
        nome = (oferta.get("productName") or "").strip()
        link = oferta.get("productLink") or ""
        preco = assistente._numero(oferta.get("priceMin")) or assistente._numero(oferta.get("price"))
        comissao = assistente._numero(oferta.get("commissionRate")) * 100
        valor = valor_por_venda(preco, comissao)
        if not nome or not link or not preco or preco > teto or valor <= antes:
            continue
        if ps.parecido_entre([nome], original["nome"])[0] < PARECIDO_NA_BUSCA:
            continue
        candidatos.append({"nome": nome, "link": link, "comissao": comissao, "preco": preco, "valor": valor,
                           "vendas": int(assistente._numero(oferta.get("sales"))),
                           "imagem": oferta.get("imageUrl") or "", "item": str(oferta.get("itemId") or "")})
    return sorted(candidatos, key=lambda c: (-c["valor"], -c["vendas"]))


def trocar_pela_maior_comissao(video):
    """
    O mesmo produto do link, de outra loja, que paga mais por venda (o preço vezes a
    comissão, contando a Comissão Extra) sem custar bem mais, como o Rafael faz pela busca
    por foto com o filtro Comissão: a API busca pelo nome por maior comissão, ficam os de
    nome e preço parecidos que pagam mais por venda, e a IA confere cada um com o vídeo pela
    foto do anúncio, com a mesma régua do produto do link (o mesmo item, da mesma cor). O
    primeiro confirmado vale: {nome, link, comissao, preco, valor, antes, valor_antes,
    vistos}, com o link curto que o celular abre. Nenhum: None, e o robô segue com o produto
    do link. A troca é um ganho a mais: um erro nela nunca derruba o rascunho.
    Escolhas do Rafael (25/10, P33; 28/10, P58): DECISOES.md, Shopee Vídeo.
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
    if not original["preco"]:
        anotar("mantido - a API não disse o preço do produto do link")
        return None
    # A capa do anúncio do post vai à IA como o produto do post; a do anúncio de outra loja
    # pode ser outra (P102), e o álbum do rascunho marca a diferente.
    capa = foto_do_anuncio(original.get("imagem"))
    if not capa:
        anotar("mantido - sem a foto de capa do post")
        return None
    ofertas = asyncio.run(api_shopee.buscar_ofertas_shopee(termo_da_busca(original["nome"]), limite=OFERTAS_NA_BUSCA,
                                                           sort_type=5))
    candidatos = candidatos_de_mais_comissao(original, ofertas)
    if not candidatos:
        anotar("mantido - nenhum que pague mais por venda" if ofertas else "mantido - a busca não trouxe nada")
        return None
    for candidato in candidatos[:CANDIDATOS_NA_IA]:
        link = asyncio.run(api_shopee.converter_link_shopee(candidato["link"], api_shopee.ETIQUETA_SHOPEE_VIDEO,
                                                            avisar_falha=False))
        if not link or link == candidato["link"]:
            # Sem o link curto, o celular não abre o produto (fica no esqueleto da página).
            continue
        vistos = []
        ok, _ = ps.ia_confere_produto(dict(video, link=link), vistos, avisar=False, capa=capa)
        if ok:
            anotar("trocado", ok=True)
            return {**candidato, "link": link, "antes": original["comissao"],
                    "valor_antes": valor_por_venda(original["preco"], original["comissao"]), "vistos": vistos}
    anotar("mantido - a IA não confirmou nenhum")
    return None


# --- O produto do vídeo quando o do link é outro (P158 2) ---

# O produto do link que não é o do vídeo (a IA viu outro): a IA diz o que o vídeo mostra em
# palavras de busca, a API busca por elas (por relevância), e dos RELEVANTES_DO_ACHADO primeiros,
# do que paga mais por venda para o que paga menos, até ACHADOS_NA_IA passam pela mesma conferência
# dupla da IA com a foto do anúncio. O primeiro confirmado toma o lugar do produto do link;
# nenhum, o vídeo fica de lado como antes. Nos horários e no Preparar 1 Agora, com qualquer
# número de pontos. Escolha do Rafael (06/11, P158 2): DECISOES.md, Shopee Vídeo.
PROCESSO_DO_PRODUTO_ACHADO = "produto do vídeo: busca pela IA"
RELEVANTES_DO_ACHADO = 5
ACHADOS_NA_IA = 3


def candidatos_do_achado(ofertas, fora=""):
    """
    Os RELEVANTES_DO_ACHADO primeiros da busca (a API já os dá por relevância) com nome, link e
    preço, sem o item do link (fora: a IA já o recusou), do que paga mais por venda para o que paga
    menos: [{nome, link, comissao, preco, valor, vendas, imagem, item}].
    """
    candidatos = []
    for oferta in ofertas:
        nome = (oferta.get("productName") or "").strip()
        link = oferta.get("productLink") or ""
        preco = assistente._numero(oferta.get("priceMin")) or assistente._numero(oferta.get("price"))
        numero = re.search(r"/product/\d+/(\d+)", link)
        item = str(oferta.get("itemId") or "") or (numero.group(1) if numero else "")
        if not nome or not link or not preco or (fora and item == fora):
            continue
        comissao = assistente._numero(oferta.get("commissionRate")) * 100
        candidatos.append({"nome": nome, "link": link, "comissao": comissao, "preco": preco,
                           "valor": valor_por_venda(preco, comissao),
                           "vendas": int(assistente._numero(oferta.get("sales"))),
                           "imagem": oferta.get("imageUrl") or "", "item": item})
        if len(candidatos) >= RELEVANTES_DO_ACHADO:
            break
    return sorted(candidatos, key=lambda c: (-c["valor"], -c["vendas"]))


def achar_o_produto_do_video(video):
    """
    O produto que o vídeo mostra, achado na Shopee e conferido pela IA como o produto do link é:
    {nome, link, comissao, preco, valor, vendas, imagem, item, vistos}, com o link curto que o
    celular abre; None quando não acha. Um erro aqui só deixa o vídeo de lado, como antes.
    """
    try:
        return _achar_o_produto_do_video(video)
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] A busca do produto do vídeo deu erro: {type(e).__name__}")
        registro_processos.registrar(REGISTRO, PROCESSO_DO_PRODUTO_ACHADO, f"não achado - erro ({type(e).__name__})")
        return None


def _achar_o_produto_do_video(video):
    def anotar(resultado, detalhe="", ok=None):
        registro_processos.registrar(REGISTRO, PROCESSO_DO_PRODUTO_ACHADO, resultado, detalhe, ok=ok)

    busca = ps.ia_diz_o_produto_do_video(video)
    if not busca:
        anotar("não achado - a IA não disse o produto")
        return None
    ofertas = asyncio.run(api_shopee.buscar_ofertas_shopee(busca, limite=OFERTAS_NA_BUSCA, sort_type=1))
    candidatos = candidatos_do_achado(ofertas, fora=item_do_link(video["link"]))
    if not candidatos:
        anotar("não achado - a busca não trouxe nada")
        return None
    conferidos = 0
    for candidato in candidatos:
        if conferidos >= ACHADOS_NA_IA:
            break
        link = asyncio.run(api_shopee.converter_link_shopee(candidato["link"], api_shopee.ETIQUETA_SHOPEE_VIDEO,
                                                            avisar_falha=False))
        if not link or link == candidato["link"]:
            # Sem o link curto, o celular não abre o produto (fica no esqueleto da página).
            continue
        conferidos += 1
        vistos = []
        ok, _ = ps.ia_confere_produto(dict(video, link=link), vistos, avisar=False)
        if ok:
            anotar("achado", f"{conferidos}º conferido, de {len(candidatos)} da busca", ok=True)
            return {**candidato, "link": link, "vistos": vistos}
    anotar("não achado - a IA não confirmou nenhum", f"{conferidos} conferido(s), de {len(candidatos)} da busca")
    return None


# --- O mesmo produto com mais comissão no Ver Produtos (P57) ---

PROCESSO_DA_TROCA_DO_VER_PRODUTOS = "ver produtos: o mesmo produto que paga mais"


def _valor_da_oferta(oferta):
    """O que o Rafael recebe numa venda pela oferta da API (o preço "a partir de" vezes a comissão); 0 sem ela."""
    preco = assistente._numero((oferta or {}).get("priceMin")) or assistente._numero((oferta or {}).get("price"))
    return valor_por_venda(preco, assistente._numero((oferta or {}).get("commissionRate")) * 100)


def trocar_os_do_ver_produtos(d, video, nomes, fotos, vistos, curtidos, prazo, de_outra_cor=()):
    """
    Os produtos do Ver Produtos (nomes: os que a IA confirmou, na ordem) como o post os leva
    (P57): cada um da mesma cor do vídeo ganha a busca da troca do link de produto (P33 e P58: a
    API pelo nome, por maior comissão; os de nome parecido, até MAIS_CARO_NA_TROCA% mais caros,
    que pagam mais por venda; a IA confere cada um com o vídeo, com a foto da página do produto
    do criador, fotos[nome], como o produto do post), e o 1º confirmado toma o lugar dele,
    curtido pelo link (curtidos recebe (link, nome)). Depois, os da mesma cor do vídeo do que
    paga mais por venda para o que paga menos (o 1º dá a foto da edição, P39) e os de outra cor
    (de_outra_cor) no fim, do mesmo jeito; o valor vem da oferta achada pelo nome, e o produto
    sem ela fica atrás dos que têm, na ordem do criador. Devolve [{nome, link (o curto do
    trocado; "" no do criador), valor, trocado (o nome do produto do criador que saiu, ou ""),
    do_video, foto (a da página, no do criador), imagem, preco e item (os do anúncio)}], na ordem
    do post. Passado o prazo (time.monotonic), os que faltam ficam os do criador. A
    troca é um ganho a mais: um erro nela deixa o produto do criador; a Verificação, não.
    Escolhas do Rafael (28/10, P57 e P58; 05/11, P154 3): DECISOES.md, Shopee Vídeo.
    """
    produtos = []
    for nome in nomes:
        try:
            parecido, _exato, oferta = _oferta_parecida(nome)
        except Exception as e:
            logger.warning(f"⚠️ [Robô Shopee Vídeo] A oferta de um produto do Ver Produtos não veio: {type(e).__name__}")
            parecido, oferta = 0, {}
        oferta = oferta if parecido >= PARECIDO_DA_FOTO else {}
        produto = {"nome": nome, "link": "", "valor": _valor_da_oferta(oferta), "trocado": "", "do_video": True,
                   "foto": fotos.get(nome), "imagem": oferta.get("imageUrl") or "", "item": str(oferta.get("itemId") or ""),
                   "preco": assistente._numero(oferta.get("priceMin")) or assistente._numero(oferta.get("price"))}
        if nome not in de_outra_cor:
            produto = _trocar_um_do_ver_produtos(d, video, produto, oferta, fotos.get(nome), vistos, curtidos,
                                                 prazo) or produto
        produtos.append(produto)
    return (sorted((p for p in produtos if p["nome"] not in de_outra_cor), key=lambda p: -p["valor"])
            + sorted((p for p in produtos if p["nome"] in de_outra_cor), key=lambda p: -p["valor"]))


def _trocar_um_do_ver_produtos(d, video, produto, oferta, foto, vistos, curtidos, prazo):
    """Um produto do Ver Produtos trocado pelo mesmo item da loja que paga mais (trocar_os_do_ver_produtos), ou None."""
    def anotar(resultado, detalhe="", ok=None):
        registro_processos.registrar(REGISTRO, PROCESSO_DA_TROCA_DO_VER_PRODUTOS, resultado, detalhe, ok=ok)

    if time.monotonic() > prazo:
        anotar("mantido - sem tempo na rodada")
        return None
    preco = assistente._numero(oferta.get("priceMin")) or assistente._numero(oferta.get("price"))
    if not oferta or not preco:
        anotar("mantido - a API não achou o produto pelo nome" if not oferta else "mantido - a API não disse o preço")
        return None
    if not foto:
        anotar("mantido - sem a foto da página do produto")
        return None
    original = {"nome": produto["nome"], "preco": preco,
                "comissao": assistente._numero(oferta.get("commissionRate")) * 100}
    try:
        ofertas = asyncio.run(api_shopee.buscar_ofertas_shopee(termo_da_busca(produto["nome"]),
                                                               limite=OFERTAS_NA_BUSCA, sort_type=5))
        candidatos = candidatos_de_mais_comissao(original, ofertas)
        if not candidatos:
            anotar("mantido - nenhum que pague mais por venda" if ofertas else "mantido - a busca não trouxe nada")
            return None
        for candidato in candidatos[:CANDIDATOS_NA_IA]:
            if time.monotonic() > prazo:
                anotar("mantido - sem tempo na rodada")
                return None
            link = asyncio.run(api_shopee.converter_link_shopee(candidato["link"], api_shopee.ETIQUETA_SHOPEE_VIDEO,
                                                                avisar_falha=False))
            if not link or link == candidato["link"]:
                # Sem o link curto, o celular não abre o produto (fica no esqueleto da página).
                continue
            deste = []
            ok, _ = ps.ia_confere_produto(dict(video, link=link), deste, avisar=False, capa=foto)
            if not ok:
                continue
            # O da outra loja é curtido pela página dele, como no link de produto: sem a curtida,
            # fica o do criador (já curtido pela lista).
            ir_ao_inicio(d)
            ps.limpar_aviso_rapido(d)
            ps.abrir_link(d, link)
            curtiu = _esperar_a_pagina_do_produto(d, a_mais=True) and ps.curtir(d, dict(video, link=link))
            pausa(3)
            if not curtiu or not curtiu[0]:
                anotar("mantido - o da outra loja não curtiu")
                return None
            if curtiu[1] == ps.CURTIDO_DE_ANTES:
                gravar_estado(favoritos_limpos=False)
            curtidos.append((link, candidato["nome"]))
            vistos.extend(deste)
            anotar("trocado", f"mais {round((candidato['valor'] / valor_por_venda(preco, original['comissao']) - 1) * 100)}% "
                   "por venda" if original["comissao"] else "", ok=True)
            return {"nome": candidato["nome"], "link": link, "valor": candidato["valor"], "trocado": produto["nome"],
                    "do_video": True, "foto": None, "imagem": candidato["imagem"], "item": candidato["item"],
                    "preco": candidato["preco"], "comissao": candidato["comissao"], "antes": original["comissao"],
                    "valor_antes": valor_por_venda(preco, original["comissao"])}
        anotar("mantido - a IA não confirmou nenhum")
    except (Verificacao, Suspensa):
        raise
    except Parada as e:
        anotar("mantido - parou", passo_do_motivo(e.motivo))
        logger.warning(f"⚠️ [Robô Shopee Vídeo] A troca de um produto do Ver Produtos parou: {ps.mascarar(e.motivo)}")
    except Exception as e:
        anotar(f"mantido - erro ({type(e).__name__})")
        logger.warning(f"⚠️ [Robô Shopee Vídeo] A troca de um produto do Ver Produtos deu erro: {type(e).__name__}")
    return None


# --- Os espaços livres com o mesmo item de outras lojas (P59) ---
# A busca pela foto do app, como o Rafael ensinou em vídeo (28/10/2026; o caminho está no
# roteiro): Eu → Criadores & Afiliados → a câmera da barra de busca → a foto do anúncio na
# galeria → os resultados, na ordem Vendas Populares. O robô lê os primeiros
# RESULTADOS_DA_FOTO cartões, acha cada um na API de afiliado pelo nome e pelo preço (o link,
# a foto e a comissão), fica com os até MAIS_CARO_NA_TROCA% mais caros que o produto do link,
# do que paga mais por venda para o que paga menos, e a IA confere com o vídeo, de uma vez,
# quais são o mesmo item. Os confirmados, até ESPACOS_DO_VIDEO no total com o do vídeo, entram
# no rascunho como ele: curtidos, anexados e descurtidos no fim. 6 é o ideal, não obrigatório.
# Escolhas do Rafael (28/10, P59, P67 e P68): DECISOES.md, Shopee Vídeo.
PROCESSO_DOS_ESPACOS = "espaços livres: o mesmo item de outras lojas"
# Em que minuto do rascunho a busca começou e quanto levou cada parte, com o mesmo resultado
# da linha da contagem: a régua de MINUTOS_PARA_OS_ESPACOS.
PROCESSO_DO_TEMPO_DOS_ESPACOS = "espaços livres: tempo de cada parte"
# Quantos anúncios a IA deixou de fora por serem outro produto (a outra foto de capa não tira,
# P102). Pedido do Rafael (30/10): o que dificulta achar a causa vira registro.
PROCESSO_DAS_RECUSAS_DA_IA = "espaços livres: por que a IA deixou de fora"
# Por que o cartão não foi achado pelo nome na API, numa linha à parte: a busca sem nenhuma
# oferta, uma oferta de nome parecido (o anúncio com o nome um pouco diferente do cartão) ou só
# ofertas de outros produtos (a busca não trouxe o anúncio). Só números, para o checkup achar
# qual conserto a busca pede.
PROCESSO_DA_BUSCA_NA_API = "espaços livres: por que a API não achou o cartão"
PARECIDO_NA_API = 60
ESPACOS_DO_VIDEO = 6
RESULTADOS_DA_FOTO = 20
ROLAGENS_DA_FOTO = 8
CANDIDATOS_DOS_ESPACOS = 8
# O preço do cartão e o da API podem diferir uns centavos (arredondamento, cupom do app).
DIFERENCA_DE_PRECO = 5
# O cartão com esta parte (%) das palavras do nome do produto do post tem o nome parecido: a
# contagem diz no registro se a busca partiu da foto certa.
NOME_PARECIDO_NA_BUSCA = 25
# Passado isto desde o começo do rascunho, os espaços livres ficam de fora: o resto do
# preparo (título, edição, anexar e conferir) tem de caber na rodada (MAXIMO_DA_RODADA).
# Depois de MINUTOS_PARA_ANEXAR_OS_A_MAIS, o produto a mais que falta anexar também fica de
# fora (os que pagam menos, que são os últimos a anexar).
MINUTOS_PARA_OS_ESPACOS = 10
MINUTOS_PARA_ANEXAR_OS_A_MAIS = 20
CAMERA_DA_BUSCA = "@AN_ImageSearchIconEntry_IcCameraOutline_Img"
FECHAR_OS_RESULTADOS = "@AN_component_IcCloseShape_Img"
ORDEM_DA_BUSCA = "Vendas Populares"


def foto_do_anuncio(endereco):
    """A foto de um anúncio (bytes) pelo endereço que a API de afiliado deu; None quando não baixa."""
    try:
        return ps.baixar_foto(endereco)
    except Exception:
        return None


def item_do_link(link):
    """O número do item (itemId) do produto do link; "" quando o link não leva a um produto."""
    try:
        destino = asyncio.run(link_para_converter(link))
    except Exception:
        return ""
    achado = re.search(r"/product/\d+/(\d+)", api_shopee.produto_do_link(destino) or "")
    return achado.group(1) if achado else ""


def oferta_do_cartao(cartao, perdas=None):
    """
    A oferta da API do cartão da busca pela foto: a busca pelo nome, por relevância, e vale a
    de mesmo nome (igual ou cortado) e mesmo preço (até DIFERENCA_DE_PRECO% de diferença). Lojas
    diferentes costumam copiar o mesmo título; entre as de mesmo nome e preço, fica a de taxa
    de comissão e preço mais perto dos do cartão (no empate, a mais relevante), que é o anúncio
    do cartão, e não o primeiro com aquele título, que pode ser o do próprio post. {} quando
    não acha: sem a oferta não há o link para curtir e para o canal, nem a foto da IA.
    perdas (dict), quando vem, conta por que não achou: "nome" (nenhuma oferta da busca com o
    mesmo nome) ou "preço" (a de mesmo nome tem outro preço), só números para o checkup.
    """
    ofertas = asyncio.run(api_shopee.buscar_ofertas_shopee(termo_da_busca(cartao["nome"]), limite=OFERTAS_NA_BUSCA,
                                                           sort_type=1))
    mesmo_nome = False
    iguais = []
    for ordem, oferta in enumerate(ofertas):
        if not ps.nome_na_pagina(oferta.get("productName") or "", cartao["nome"]):
            continue
        mesmo_nome = True
        preco = assistente._numero(oferta.get("priceMin")) or assistente._numero(oferta.get("price"))
        if preco and abs(preco - cartao["preco"]) <= cartao["preco"] * DIFERENCA_DE_PRECO / 100:
            taxa = assistente._numero(oferta.get("commissionRate")) * 100
            # Arredondado: 0.12 * 100 dá 12.000000000000002, e o empate tem de ser empate.
            longe_da_taxa = round(abs(taxa - cartao["comissao"]), 2) if cartao.get("comissao") else 0
            iguais.append((longe_da_taxa, round(abs(preco - cartao["preco"]), 2), ordem, oferta))
    if iguais:
        return min(iguais, key=lambda igual: igual[:3])[3]
    if perdas is not None:
        for motivo in ("preço",) if mesmo_nome else ("nome", _porque_sem_o_nome(ofertas, cartao["nome"])):
            perdas[motivo] = perdas.get(motivo, 0) + 1
    return {}


def _porque_sem_o_nome(ofertas, nome):
    """Por que nenhuma oferta da busca teve o nome do cartão (PROCESSO_DA_BUSCA_NA_API)."""
    if not ofertas:
        return "busca vazia"
    parecido = ps.mais_parecido([oferta.get("productName") or "" for oferta in ofertas], nome)[0]
    return "nome parecido" if parecido >= PARECIDO_NA_API else "outros produtos"


def nome_parecido(nome_do_cartao, nome_do_post):
    """O nome do cartão tem NOME_PARECIDO_NA_BUSCA% das palavras (de 3 letras ou mais) do nome do post?"""
    alvo = {palavra for palavra in ps._nome_normal(nome_do_post).split() if len(palavra) >= 3}
    palavras = set(ps._nome_normal(nome_do_cartao).split())
    return bool(alvo) and len(alvo & palavras) * 100 >= NOME_PARECIDO_NA_BUSCA * len(alvo)


def candidatos_da_foto(original, item_do_rascunho, achados, fora=None):
    """
    Dos cartões da busca pela foto já achados na API ([(cartão, oferta)], na ordem de Vendas
    Populares), os que podem ir nos espaços livres, do que paga mais por venda para o que paga
    menos (no empate, o mais vendido): até MAIS_CARO_NA_TROCA% mais caros que o produto do link
    (P58), nunca o produto que já está no rascunho nem o mesmo item duas vezes.
    [{nome, endereco, imagem, preco, comissao, valor, item}]. Sem o preço do produto do link, nenhum.
    fora (dict), quando vem, conta por que cada achado ficou de fora, só números para o
    checkup: "sem o preço do post", "sem dados" (a API não deu o item, o link ou o preço),
    "o do rascunho", "repetido" (o mesmo anúncio de outro cartão) e "mais caro", com "o mais
    perto": quantos % acima do preço do post está o mais barato deles.
    """
    fora = {} if fora is None else fora

    def contar(motivo):
        fora[motivo] = fora.get(motivo, 0) + 1

    if not original.get("preco"):
        contar("sem o preço do post")
        return []
    teto = round(original["preco"] * (1 + MAIS_CARO_NA_TROCA / 100), 2)
    vistos = set()
    candidatos = []
    for ordem, (_cartao, oferta) in enumerate(achados):
        item = str(oferta.get("itemId") or "")
        endereco = oferta.get("productLink") or ""
        preco = assistente._numero(oferta.get("priceMin")) or assistente._numero(oferta.get("price"))
        comissao = assistente._numero(oferta.get("commissionRate")) * 100
        if not item or not endereco or not preco:
            contar("sem dados")
            continue
        if item_do_rascunho and item == str(item_do_rascunho):
            contar("o do rascunho")
            continue
        if item in vistos:
            contar("repetido")
            continue
        if preco > teto:
            contar("mais caro")
            # Para cima: o que passou do teto nunca aparece como os 20% dele.
            acima = math.ceil(round((preco / original["preco"] - 1) * 100, 6))
            fora["o mais perto"] = min(fora.get("o mais perto", acima), acima)
            continue
        vistos.add(item)
        candidatos.append({"nome": (oferta.get("productName") or "").strip(), "endereco": endereco,
                           "imagem": oferta.get("imageUrl") or "", "preco": preco, "comissao": comissao,
                           "valor": valor_por_venda(preco, comissao), "item": item, "ordem": ordem})
    return sorted(candidatos, key=lambda c: (-c["valor"], c["ordem"]))


def buscar_pela_foto(d, foto):
    """
    Os primeiros RESULTADOS_DA_FOTO cartões da busca pela foto do app, na ordem Vendas
    Populares (P68): (cartões, motivo); sem cartão, o motivo em texto fixo. A foto do anúncio
    entra na galeria como a mais nova e sai no fim, deu certo ou não. Nunca toca no botão de
    tirar foto (a câmera do Motorola).
    """
    arquivo = ps.por_foto_na_galeria(d, foto)
    if not arquivo:
        return [], "a foto do anúncio não apareceu na galeria"
    try:
        return _buscar_pela_foto(d)
    finally:
        ps.tirar_foto_da_galeria(d, arquivo)


def _buscar_pela_foto(d):
    ir_ao_inicio(d)
    tocar(d, "Eu", 5)
    if not esperar_na_tela(d, CRIADORES_E_AFILIADOS, 9):
        ps.rolar(d)
        pausa(2)
        if not tem(tela(d), CRIADORES_E_AFILIADOS):
            raise Parada("a busca pela foto não achou Criadores & Afiliados na aba Eu")
    tocar(d, CRIADORES_E_AFILIADOS, 6)
    if not esperar_na_tela(d, CAMERA_DA_BUSCA, 12):
        raise Parada("a área de Criadores & Afiliados não abriu com a câmera da busca")
    tocar(d, CAMERA_DA_BUSCA, 5)
    xml = esperar_na_tela(d, ps.PESQUISAR_NA_GALERIA, 9)
    ponto = ps.primeira_foto_da_galeria(xml) if xml else None
    if not ponto:
        raise Parada("a câmera da busca não mostrou a foto da galeria")
    d.click(*ponto)
    pausa(8)
    xml = esperar_na_tela(d, FECHAR_OS_RESULTADOS, 15)
    if not xml:
        raise Parada("os resultados da busca pela foto não abriram")
    cartoes = []
    if ps.sem_resultados_da_busca(xml):
        motivo = "a busca pela foto não achou o produto"
    else:
        tocar(d, ORDEM_DA_BUSCA, 8)
        vistos = set()
        for rolagem in range(ROLAGENS_DA_FOTO + 1):
            xml = tela(d)
            novos = [c for c in ps.cartoes_da_busca(xml) if (c["nome"], c["preco"], c["comissao"]) not in vistos]
            vistos.update((c["nome"], c["preco"], c["comissao"]) for c in novos)
            cartoes.extend(novos)
            if len(cartoes) >= RESULTADOS_DA_FOTO or ps.fim_dos_resultados(xml) or (rolagem and not novos):
                break
            ps.rolar(d)
            pausa(3)
        motivo = "" if cartoes else "a busca pela foto não mostrou nenhum cartão inteiro"
    # O X dos resultados volta à câmera; o voltar sai dela e da área de afiliado.
    tocar(d, FECHAR_OS_RESULTADOS, 3)
    ir_ao_inicio(d)
    return cartoes[:RESULTADOS_DA_FOTO], motivo


def _minutos(segundos):
    """Os segundos em minutos com uma casa, no jeito brasileiro (2,5), para o registro."""
    return f"{segundos / 60:.1f}".replace(".", ",")


def _fora_do_preco(fora):
    """Por que os achados na API ficaram de fora do preço (candidatos_da_foto), em texto curto, só números."""
    partes = [f"mais caros {fora['mais caro']}, o mais perto +{fora['o mais perto']}%"] if fora.get("mais caro") else []
    partes += [f"{rotulo} {fora[chave]}" for chave, rotulo in
               (("o do rascunho", "o do rascunho"), ("repetido", "repetidos"), ("sem dados", "sem dados"))
               if fora.get(chave)]
    if fora.get("sem o preço do post"):
        partes.append("sem o preço do post")
    return f" ({'; '.join(partes)})" if partes else ""


def sem_os_a_mais():
    """
    Por que o rascunho de agora vai sem os produtos a mais (P59), em (resultado, detalhe) para o
    registro dos espaços livres: desligados no painel ou só o produto do vídeo pelos pontos.
    None quando eles vão.
    """
    if not ler_config().get("robo_produtos_a_mais", True):
        return "nenhum - desligados", ""
    # Com 4 pontos de penalidade ou mais, só o produto do vídeo vai ao post (P145).
    pontos = apelacoes.pontos_de_agora(ler_estado())
    if pontos >= apelacoes.PONTOS_SO_O_PRODUTO_DO_VIDEO:
        return "nenhum - só o produto do vídeo pelos pontos", f"{pontos} ponto(s) de penalidade"
    return None


def espacos_livres(d, video, principal, original, vistos, prazo, inicio=None, recusados=None,
                   espacos=ESPACOS_DO_VIDEO - 1):
    """
    Os produtos a mais do rascunho (P59; no Ver Produtos, nos espaços que sobram, P66): até
    espacos do mesmo item, de outras lojas, conferidos pela IA com o vídeo, do que paga mais por
    venda para o que paga menos: [{nome, link, endereco, preco, comissao, valor, item}], com o
    link curto que o celular abre. Nenhum quando passou o prazo (time.monotonic), a busca não
    acha ou a IA não confirma. Um erro aqui nunca derruba o rascunho; a Verificação, sim.
    inicio (time.monotonic do começo do rascunho), quando vem, põe no registro em que minuto
    do rascunho a busca começou e quanto levou cada parte: a régua dos prazos, só números.
    """
    def anotar(resultado, detalhe="", ok=None):
        registro_processos.registrar(REGISTRO, PROCESSO_DOS_ESPACOS, resultado, detalhe, ok=ok)
        # O tempo vai numa linha à parte, com o mesmo resultado: a contagem já enche o detalhe.
        if inicio is not None:
            registro_processos.registrar(REGISTRO, PROCESSO_DO_TEMPO_DOS_ESPACOS, resultado, tempos())

    marcas = [("começo", time.monotonic())]

    def marcar(parte):
        marcas.append((parte, time.monotonic()))

    def tempos():
        if inicio is None:
            return ""
        partes = [f"{parte} {_minutos(fim - comeco)} min" for (_, comeco), (parte, fim) in zip(marcas, marcas[1:])]
        return f"aos {_minutos(marcas[0][1] - inicio)} min do rascunho" + (": " + ", ".join(partes) if partes else "")

    motivo = sem_os_a_mais()
    if motivo:
        registro_processos.registrar(REGISTRO, PROCESSO_DOS_ESPACOS, *motivo)
        return []
    if time.monotonic() > prazo:
        anotar("nenhum - sem tempo na rodada")
        return []
    # A capa do anúncio do post: a busca pela foto parte dela, e ela vai à IA como o produto do
    # post. A foto do produto a mais pode ser outra (P102); o álbum do rascunho marca a diferente.
    capa = foto_do_anuncio(original.get("imagem"))
    if not capa:
        anotar("nenhum - sem a foto de capa do post")
        return []
    try:
        cartoes, motivo = buscar_pela_foto(d, capa)
        marcar("busca")
        if not cartoes:
            anotar(f"nenhum - {motivo}")
            return []
        achados, perdas = [], {}
        for cartao in cartoes:
            oferta = oferta_do_cartao(cartao, perdas)
            if oferta:
                achados.append((cartao, oferta))
        if perdas.get("nome"):
            registro_processos.registrar(REGISTRO, PROCESSO_DA_BUSCA_NA_API, "sem o nome",
                                         f"{perdas['nome']} cartão(ões): busca vazia {perdas.get('busca vazia', 0)}, "
                                         f"nome parecido {perdas.get('nome parecido', 0)}, "
                                         f"outros produtos {perdas.get('outros produtos', 0)}")
        fora_do_preco = {}
        candidatos = candidatos_da_foto(original, principal.get("item") or item_do_link(video["link"]), achados,
                                        fora_do_preco)[:CANDIDATOS_DOS_ESPACOS]
        # Quantos cartões têm o nome parecido com o do produto do post (a busca que partiu de
        # outra foto não traz nenhum), por que os outros não foram achados na API (o nome ou
        # o preço), em quantos anúncios diferentes caíram os achados e por que eles ficaram de
        # fora do preço. Só números.
        parecidos = sum(1 for cartao in cartoes if nome_parecido(cartao["nome"], principal["nome"]))
        fora = f" (sem o nome {perdas.get('nome', 0)}, outro preço {perdas.get('preço', 0)})" if perdas else ""
        diferentes = len({str(oferta.get("itemId") or "") for _cartao, oferta in achados} - {""})
        contagem = (f"{len(cartoes)} na busca ({parecidos} com o nome parecido), {len(achados)} na API{fora}, "
                    f"{diferentes} anúncio(s) diferente(s), {len(candidatos)} no preço{_fora_do_preco(fora_do_preco)}")
        fotos = []
        for candidato in candidatos:
            try:
                foto_do_candidato = ps.baixar_foto(candidato["imagem"])
            except Exception:
                # A foto que não baixa só tira esse anúncio da conferência da IA.
                foto_do_candidato = None
            if foto_do_candidato:
                fotos.append((candidato, foto_do_candidato))
        marcar("API")
        if not fotos:
            anotar("nenhum - nenhum do mesmo preço na API", contagem)
            return []
        if time.monotonic() > prazo:
            anotar("nenhum - sem tempo na rodada", contagem)
            return []
        recusas, de_outra_cor = {}, set()
        # O preço vai junto ao nome de cada foto: a imitação com a foto da marca costuma custar
        # muito menos que o produto do post (ps.IMITACAO).
        posicoes, motivo_da_ia = ps.ia_confere_iguais(video, principal["nome"],
                                                      [(c["nome"], f) for c, f in fotos], capa=capa, recusas=recusas,
                                                      precos=[c.get("preco") for c, _f in fotos],
                                                      preco_do_post=original.get("preco"), outra_cor=de_outra_cor)
        marcar("IA")
        # A foto de cada um vai junto: o álbum das capas do rascunho (P75) e, no de outra cor (o
        # mesmo modelo em outra cor ou estampa), a miniatura que troca, sem a qual ele não vai.
        confirmados = [dict(fotos[i][0], foto=fotos[i][1], outra_cor=i in de_outra_cor)
                       for i in posicoes if OUTRA_COR_NOS_PRODUTOS or i not in de_outra_cor][:espacos]
        # O mesmo modelo em outra cor fica de fora (P142 1), e o registro conta quantos.
        fora_pela_cor = 0 if OUTRA_COR_NOS_PRODUTOS else sum(1 for i in posicoes if i in de_outra_cor)
        if fora_pela_cor:
            registro_processos.registrar(REGISTRO, PROCESSO_DA_OUTRA_COR, "de fora",
                                         f"{fora_pela_cor} - {MOTIVO_DA_OUTRA_COR_DESLIGADA}")
        # Os que a IA conferiu e recusou (só quando ela respondeu): o álbum dos recusados, para o
        # Rafael conferir se ela está acertando. Pedido dele (01/11): DECISOES.md, Shopee Vídeo.
        if recusados is not None and "outro produto" in recusas:
            recusados.extend(foto for i, (_candidato, foto) in enumerate(fotos) if i not in set(posicoes))
        if motivo_da_ia:
            vistos.append(f"Produtos a mais ({len(confirmados)} de {len(fotos)}): {motivo_da_ia}")
        mais = []
        for candidato in confirmados:
            link = asyncio.run(api_shopee.converter_link_shopee(candidato["endereco"], api_shopee.ETIQUETA_SHOPEE_VIDEO,
                                                                avisar_falha=False))
            # Sem o link curto, o celular não abre o produto (fica no esqueleto da página).
            if link and link != candidato["endereco"]:
                mais.append({**candidato, "link": link})
        contagem += f", {len(fotos)} na IA, {len(posicoes)} confirmados"
        if recusas and len(posicoes) < len(fotos):
            # Quantos a IA deixou de fora, numa linha à parte (a contagem já enche o detalhe).
            registro_processos.registrar(REGISTRO, PROCESSO_DAS_RECUSAS_DA_IA, "de fora pela IA",
                                         f"outro produto {recusas.get('outro produto', 0)} (de {len(fotos)} na IA)")
        if mais:
            variacoes = sum(1 for produto in mais if produto.get("outra_cor"))
            anotar("achados", f"{len(mais)} a mais" + (f" ({variacoes} de outra cor)" if variacoes else "")
                   + f"; {contagem}", ok=True)
        else:
            anotar("nenhum - a IA não confirmou nenhum" if not posicoes else "nenhum - sem o link curto", contagem)
        return mais
    except (Verificacao, Suspensa):
        raise
    except Parada as e:
        anotar("parou", passo_do_motivo(e.motivo), ok=False)
        logger.warning(f"⚠️ [Robô Shopee Vídeo] A busca pela foto parou: {ps.mascarar(e.motivo)}")
        return []
    except Exception as e:
        anotar("erro", type(e).__name__, ok=False)
        logger.warning(f"⚠️ [Robô Shopee Vídeo] A busca dos produtos a mais deu erro: {type(e).__name__}")
        return []


def espacos_do_ver_produtos(d, video, produtos, vistos, prazo, inicio, recusados, curtidos, variacoes):
    """
    Os produtos do Ver Produtos (os do criador, também os do Ver Mais, e os trocados, na ordem do
    post) com os espaços que sobram, até ESPACOS_DO_VIDEO, cheios com o mesmo item de outras lojas
    do 1º da mesma cor do vídeo (P59): a mesma busca pela foto dos vídeos de link de produto
    (espacos_livres, com as mesmas travas: o painel, os pontos e o prazo), partindo da foto e do
    preço do anúncio dele. Os achados são curtidos pelo link (o que não curte fica de fora) e
    entram na ordem do post, do que paga mais por venda para o que paga menos, com os de outra cor
    no fim; o de outra cor vai para variacoes, com a foto que entra na miniatura. Devolve os
    produtos na ordem do post. Escolhas do Rafael (28/10, P59 e P66; 05/11, P154 3): DECISOES.md,
    Shopee Vídeo.
    """
    de_outra_cor = {nome for nome, _foto in variacoes}
    base = next((p for p in produtos if p["nome"] not in de_outra_cor), None)
    sobram = ESPACOS_DO_VIDEO - len(produtos)
    if not base or sobram <= 0:
        return produtos
    base["base"] = True
    mais = espacos_livres(d, video, {"nome": base["nome"], "item": base.get("item") or ""},
                          {"imagem": base.get("imagem"), "preco": base.get("preco")}, vistos, prazo, inicio,
                          recusados, espacos=sobram)
    if not mais:
        return produtos
    feitos = _curtir_os_produtos(d, video, sorted(mais, key=lambda p: -p["valor"]), curtidos)
    variacoes.extend((p["nome"], p.get("foto")) for p in feitos if p.get("outra_cor"))
    outra_cor = de_outra_cor | {p["nome"] for p in feitos if p.get("outra_cor")}
    todos = produtos + feitos
    return (sorted((p for p in todos if p["nome"] not in outra_cor), key=lambda p: -p["valor"])
            + sorted((p for p in todos if p["nome"] in outra_cor), key=lambda p: -p["valor"]))


def ordem_do_post(principal, mais):
    """
    Os produtos do rascunho de link de produto na ordem do post: os da mesma cor do vídeo (o
    do link e os a mais iguais), do que paga mais por venda para o que paga menos (P59), e
    depois os de outra cor, do mesmo jeito. O 1º dá a foto do começo e da miniatura, que tem de
    ser a da cor do vídeo; o de outra cor só vai com a foto dele na miniatura que troca, como
    no Ver Produtos. Pedidos do Rafael (01/11 e 02/11): DECISOES.md, Shopee Vídeo.
    """
    mesma_cor = [principal] + [produto for produto in mais if not produto.get("outra_cor")]
    outra_cor = [produto for produto in mais if produto.get("outra_cor")]
    return (sorted(mesma_cor, key=lambda produto: -produto["valor"])
            + sorted(outra_cor, key=lambda produto: -produto["valor"]))


def _curtir_os_produtos(d, video, produtos, curtidos):
    """
    Curte cada produto do rascunho de link de produto pela página dele, de trás para a frente
    na ordem do post (ordem_do_post): o curtido por último fica no alto de Minhas Curtidas, e o
    anexar pega do alto para baixo, na ordem do post (P59). O produto do vídeo que não curte
    para o rascunho, como sempre; o produto a mais que não curte (loja de férias, coração que
    não pega) só fica de fora. Devolve os curtidos, na ordem do post; curtidos recebe (link,
    nome) de cada um, para o descurtir do fim.
    """
    feitos = []
    for produto in reversed(produtos):
        a_mais = not produto.get("do_video")
        este = dict(video, link=produto["link"])
        ir_ao_inicio(d)
        ps.limpar_aviso_rapido(d)
        ps.abrir_link(d, produto["link"])
        if not _esperar_a_pagina_do_produto(d, a_mais=a_mais):
            continue
        resultado = ps.curtir(d, este)
        if a_mais and not resultado[0]:
            registro_processos.registrar(REGISTRO, PROCESSO_DOS_ESPACOS, "produto a mais de fora", "não curtiu",
                                         ok=None)
            continue
        _conferir_curtida(resultado)
        curtidos.append((produto["link"], produto["nome"]))
        feitos.append(produto)
        pausa(3)
    return feitos[::-1]


CAMINHO_DOS_PRODUTOS_A_MAIS = "Shopee Vídeo 🎬 → Robô Automático 🤖 → Produtos a Mais 🛍️"


def parar_os_produtos_a_mais(punicao, rascunho=None):
    """
    Punição nova por produto que não é o do vídeo: os produtos a mais (P59) param sozinhos,
    até o Rafael ligar de novo no painel, e o aviso no privado diz se o vídeo punido tinha
    produtos a mais. Os rascunhos seguem só com o produto do link.
    Escolha do Rafael (29/10, P73): DECISOES.md, Shopee Vídeo.
    """
    if not ler_config().get("robo_produtos_a_mais", True):
        return
    parados = f"punição de {punicao['tipo']} ({punicao['data']})"
    db.atualizar_config(CHAVE_CONFIG, lambda dados: dados.update(robo_produtos_a_mais=False,
                                                                 robo_produtos_a_mais_parados=parados,
                                                                 robo_produtos_a_mais_parados_em=_momento()))
    a_mais = sum(1 for item in (rascunho or {}).get("itens") or [] if item.get("a_mais"))
    if not rascunho:
        contexto = "Não achei o rascunho do robô desse vídeo."
    elif a_mais:
        contexto = f"O vídeo punido tinha {a_mais} produto(s) a mais."
    else:
        contexto = "O vídeo punido não tinha produtos a mais."
    registro_processos.registrar(REGISTRO, PROCESSO_DOS_ESPACOS, "desligados - punição de produto",
                                 "com produtos a mais" if a_mais else ("sem produtos a mais" if rascunho
                                                                        else "vídeo sem rascunho do robô"),
                                 ok=None)
    avisar(f"⚠️ Robô da Shopee Vídeo: a Shopee deu uma punição de {punicao['tipo']} ({punicao['data']}). Como "
           "você escolheu, desliguei os produtos a mais (o mesmo item de outras lojas): os próximos rascunhos vão "
           f"só com o produto do link. {contexto}\n\nPara ligar de novo: {CAMINHO_DOS_PRODUTOS_A_MAIS}.")


def religar_a_pausa_sem_hora():
    """
    Migração única (P153 3): a pausa dos produtos a mais por punição de produto que não guarda
    quando parou (robo_produtos_a_mais_parados_em, que toda pausa guarda) sai, e eles voltam como
    estavam, até 6 por vídeo: o Rafael escolheu que voltem quando os pontos deixarem. Até lá, com
    apelacoes.PONTOS_SO_O_PRODUTO_DO_VIDEO pontos ou mais, a escada já deixa só o produto do vídeo
    (espacos_livres, P145). A pausa de uma punição nova fica até ele ligar de novo no painel (P73).
    Devolve True quando religou. Escolha do Rafael (05/11, P153 3): DECISOES.md, Shopee Vídeo.
    """
    config = ler_config()
    if (config.get("robo_produtos_a_mais", True) or not config.get("robo_produtos_a_mais_parados")
            or config.get("robo_produtos_a_mais_parados_em")):
        return False

    def religar(dados):
        if dados.get("robo_produtos_a_mais_parados_em") or not dados.get("robo_produtos_a_mais_parados"):
            return False
        dados.update(robo_produtos_a_mais=True, robo_produtos_a_mais_parados=None)
        return True

    religados = bool(db.atualizar_config(CHAVE_CONFIG, religar))
    if religados:
        registro_processos.registrar(REGISTRO, PROCESSO_DOS_ESPACOS, "religados - voltam quando os pontos deixarem",
                                     "escolha da P153", ok=True)
    return religados


def _mais_produtos(produtos):
    """Os produtos a mais como o rascunho os guarda: [{nome, link, endereco}] (endereço vazio no do vídeo)."""
    return [{"nome": p["nome"], "link": p["link"], "endereco": p.get("endereco") or ""} for p in produtos]


def _itens(produtos):
    """
    O número (itemId) de cada produto do post, na ordem, e se é um produto a mais: com ele, a
    medição da P73 acha nas vendas o que veio do produto do vídeo e o que veio dos a mais.
    """
    return [{"item": str(p.get("item") or ""), "a_mais": not p.get("do_video")} for p in produtos]


def guardar_capas(ident, video, produtos):
    """
    As fotos de capa dos produtos do post, na ordem, em arquivos ao lado do vídeo do rascunho
    ({ident}_capa_{n}): o Rafael as vê em álbum em Rascunhos do Robô antes de aprovar, e saem
    com o vídeo depois de usadas. A do produto a mais veio da conferência; a do produto do link
    (ou da troca), da API. A que não vem fica de fora. Devolve os caminhos.
    Escolha do Rafael (29/10, P75): DECISOES.md, Shopee Vídeo.
    """
    caminhos = []
    for n, produto in enumerate(produtos, 1):
        # O álbum é para o Rafael revisar: a foto que falha não derruba o rascunho já anexado.
        try:
            foto = foto_do_produto_do_post(video, produto)
            if not foto:
                continue
            caminho = os.path.join(PASTA_RASCUNHOS, f"{ident}_capa_{n}.{ps.extensao_da_foto(foto) or 'jpg'}")
            with open(caminho, "wb") as arquivo:
                arquivo.write(foto)
            caminhos.append(caminho)
        except Exception as e:
            logger.warning(f"⚠️ [Robô Shopee Vídeo] A foto de capa de um produto não foi guardada: {type(e).__name__}")
    return caminhos


def guardar_recusados(ident, fotos):
    """
    As fotos de capa dos anúncios de outras lojas que a IA recusou nos produtos a mais, em
    arquivos ao lado do vídeo do rascunho ({ident}_recusado_{n}): o Rafael as vê num álbum à
    parte em Rascunhos do Robô, para conferir se a IA está acertando; nenhuma vai no post, e
    saem com o vídeo depois de usadas. Provisório: quando o Rafael pedir, o álbum sai. Devolve
    os caminhos. Pedido dele (01/11): DECISOES.md, Shopee Vídeo.
    """
    caminhos = []
    for n, foto in enumerate(fotos, 1):
        try:
            caminho = os.path.join(PASTA_RASCUNHOS, f"{ident}_recusado_{n}.{ps.extensao_da_foto(foto) or 'jpg'}")
            with open(caminho, "wb") as arquivo:
                arquivo.write(foto)
            caminhos.append(caminho)
        except Exception as e:
            logger.warning(f"⚠️ [Robô Shopee Vídeo] A foto de um recusado não foi guardada: {type(e).__name__}")
    return caminhos


def foto_do_produto_do_post(video, produto):
    """
    A foto de capa (bytes) de um produto do post: a do produto a mais veio da conferência; a do
    produto do link (ou da troca) vem da API e fica guardada no produto, para o álbum, a marca da
    outra foto e a miniatura não a baixarem de novo. None quando não vem.
    """
    if not produto.get("foto"):
        try:
            produto["foto"] = ps.anuncio_do_produto(dict(video, link=produto["link"])).get("foto")
        except Exception as e:
            logger.warning(f"⚠️ [Robô Shopee Vídeo] A foto de capa de um produto não veio: {type(e).__name__}")
            return None
    return produto.get("foto")


# A parte da foto que entra na comparação, em fração da largura e da altura: sem a borda, onde a
# loja põe selo, moldura ou texto.
MIOLO_DA_FOTO = (0.1, 0.9)
# A mesma foto tem as mesmas cores: o miolo é dividido numa grade de GRADE_DA_COR x GRADE_DA_COR, e
# a cor média de cada pedaço pode variar até COR_PARECIDA (a soma das diferenças das três cores, de
# 0 a 765); a compressão e um ajuste de luz da loja ficam abaixo disso. O mesmo modelo em outra cor,
# fotografado igual, muda muitos pedaços e é outra foto: ele entra na miniatura que troca, como o
# Rafael pediu (01/11: toda variação entra na miniatura).
GRADE_DA_COR = 8
COR_PARECIDA = 80
# A mesma foto em duas lojas nem sempre vem igual pixel a pixel: no vídeo do Rafael de 02/11 (a
# viseira), a foto do 3º link era a do 1º descida uns 9% por uma faixa com o nome da loja no alto, e
# a miniatura a mostrou duas vezes. A comparação procura o melhor encaixe do miolo de uma foto na
# outra, com um pouco de zoom e de deslocamento (ESCALAS_DO_ENCAIXE, DESLOCAMENTOS_DO_ENCAIXE, em
# fração do miolo), com as duas reduzidas a LADO_DA_COMPARACAO; no melhor encaixe, a diferença média
# fica até DIFERENCA_PARECIDA (de 0 a 255), e até PEDACOS_DIFERENTES pedaços da grade podem passar
# de COR_PARECIDA (o texto ou o selo que a loja pôs por cima). Pedido dele: DECISOES.md, Shopee Vídeo.
LADO_DA_COMPARACAO = 48
ESCALAS_DO_ENCAIXE = (0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15)
DESLOCAMENTOS_DO_ENCAIXE = (-0.12, -0.09, -0.06, -0.03, 0.0, 0.03, 0.06, 0.09, 0.12)
DIFERENCA_PARECIDA = 14
PEDACOS_DIFERENTES = 4
# Miolo quase de uma cor só (o desvio abaixo disto): não há desenho para comparar.
FOTO_SEM_DESENHO = 6


def _encaixes(imagem, lado):
    """
    Os recortes do miolo da imagem (do PIL) com um pouco de zoom e de deslocamento, reduzidos a
    lado x lado, como matrizes de cor (numpy): os candidatos ao melhor encaixe.
    """
    import numpy
    from PIL import Image
    largura, altura = imagem.size
    # Reduzida antes, para os recortes saírem rápido: o miolo com umas 4 vezes o lado final.
    fator = min(1.0, 4 * lado / max(1.0, largura * (MIOLO_DA_FOTO[1] - MIOLO_DA_FOTO[0])))
    if fator < 1.0:
        imagem = imagem.resize((max(1, int(largura * fator)), max(1, int(altura * fator))), Image.BOX)
        largura, altura = imagem.size
    de, ate = MIOLO_DA_FOTO
    meio_x, meio_y = largura / 2, altura / 2
    miolo_x, miolo_y = largura * (ate - de), altura * (ate - de)
    for escala in ESCALAS_DO_ENCAIXE:
        corte_x, corte_y = miolo_x * escala, miolo_y * escala
        for desloca_x in DESLOCAMENTOS_DO_ENCAIXE:
            for desloca_y in DESLOCAMENTOS_DO_ENCAIXE:
                x1 = meio_x + desloca_x * miolo_x - corte_x / 2
                y1 = meio_y + desloca_y * miolo_y - corte_y / 2
                if x1 < 0 or y1 < 0 or x1 + corte_x > largura or y1 + corte_y > altura:
                    continue
                caixa = (x1, y1, x1 + corte_x, y1 + corte_y)
                yield numpy.asarray(imagem.resize((lado, lado), Image.BOX, box=caixa), dtype=numpy.float32)


def mesma_foto(foto, outra):
    """
    Se as duas fotos (bytes) são a mesma imagem: no melhor encaixe do miolo de uma na outra (com
    um pouco de zoom e de deslocamento, a loja que amplia ou corta a foto), as mesmas cores, com
    uns poucos pedaços diferentes (o texto ou o selo da loja). O selo, a moldura ou o texto que a
    loja põe na borda não contam. None quando alguma não abre ou não tem desenho para comparar.
    """
    import numpy
    from PIL import Image, ImageStat
    imagens = []
    for dados in (foto, outra):
        try:
            imagens.append(Image.open(io.BytesIO(dados or b"")).convert("RGB"))
        except Exception:
            return None
    um, outro = imagens
    largura, altura = um.size
    de, ate = MIOLO_DA_FOTO
    miolo = um.crop((int(largura * de), int(altura * de), int(largura * ate), int(altura * ate)))
    if min(miolo.size) < GRADE_DA_COR or ImageStat.Stat(miolo.convert("L")).stddev[0] < FOTO_SEM_DESENHO:
        return None
    lado = LADO_DA_COMPARACAO
    base = numpy.asarray(miolo.resize((lado, lado), Image.BOX), dtype=numpy.float32)
    melhor = min(((float(numpy.abs(base - candidato).mean()), candidato) for candidato in _encaixes(outro, lado)),
                 key=lambda par: par[0], default=None)
    if melhor is None:
        return None
    media, encaixe = melhor
    if media > DIFERENCA_PARECIDA:
        return False
    passo = lado // GRADE_DA_COR
    grade = lambda matriz: matriz.reshape(GRADE_DA_COR, passo, GRADE_DA_COR, passo, 3).mean(axis=(1, 3))
    diferentes = int((numpy.abs(grade(base) - grade(encaixe)).sum(axis=2) > COR_PARECIDA).sum())
    return diferentes <= PEDACOS_DIFERENTES


def com_outra_foto_de_capa(video, produtos, capa):
    """
    As posições (1, 2, ...) dos produtos do post cuja foto de capa não é a do anúncio do post
    (capa, em bytes): o álbum e o texto do rascunho as marcam, para o Rafael conferir antes de
    aprovar. A comparação é da imagem (mesma_foto), não da IA, que confunde o mesmo produto com
    a mesma foto. Sem a capa do post, nenhuma; a foto que não abre não é marcada.
    Escolha do Rafael (30/10, P102): DECISOES.md, Shopee Vídeo.
    """
    if not capa:
        return []
    return [n for n, produto in enumerate(produtos, 1)
            if mesma_foto(foto_do_produto_do_post(video, produto), capa) is False]


def itens_postados():
    """
    Os produtos de cada vídeo de link de produto que o robô postou: [(dia do post AAAA-MM-DD,
    [{item, a_mais}])], para a medição das vendas dos produtos a mais (P73).
    """
    return [((r["postado_em"] or "")[:10], r["itens"]) for r in listar("postado") if r["itens"] and r["postado_em"]]


# Depois do Feito, o produto aparece na fileira da tela final. No Motorola, em 30/10 (06:17) e
# em 31/10 (09:15 e 09:35), o 1º produto não ficou: a tela final voltou com a edição da legenda
# aberta por cima (a legenda já escrita, em foco e com o texto marcado pela cópia) e a linha dos
# produtos vazia. Por isso os produtos vão antes da legenda, e o 1º anexado é conferido na tela
# final: sem ele, o robô o anexa de novo, uma vez (VEZES_DO_PRIMEIRO_PRODUTO). O que não fica
# nem na 2ª vez não é problema do vídeo: a falha vem em rajadas (07/11 às 6h e das 16h às 17h,
# 08/11 às 19h, 09/11 às 13h, com 4 produtos diferentes seguidos), e fora delas todos ficam. O
# vídeo volta como nas outras falhas que não são dele: o mesmo vídeo nas rodadas seguintes, até
# TENTATIVAS_A_MAIS vezes, e depois fica de lado só no dia (escolha do Rafael, P182 1:
# DECISOES.md, Shopee Vídeo). A tela de logo depois do Feito (ESPERA_LOGO_DEPOIS_DO_FEITO) vai
# para o caso e, em rótulos fixos, para o registro: um aviso do app na tela some antes da conferência.
VEZES_DO_PRIMEIRO_PRODUTO = 2
MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU = ("o produto anexado pelo Adicionar não ficou na tela final depois do Feito, "
                                    "nem na 2ª vez")
ESPERA_LOGO_DEPOIS_DO_FEITO, ESPERA_DEPOIS_DO_FEITO = 1, 6


def anexar_os_produtos(d, video, nomes, a_mais=(), limpa=False, prazo=None, curtidos_de_fora=0):
    """
    Anexa os produtos curtidos, na ordem de nomes (o 1º pelo Adicionar produto, os outros
    pelo Adicionar Mais). O produto a mais (a posição está em a_mais, P59) que não anexa, ou
    que chega depois do prazo (time.monotonic), só fica de fora; o do vídeo que não anexa
    para o rascunho. Devolve (os nomes como a lista os mostrou, as posições anexadas). Os
    curtidos ficam no alto da lista: cada um é procurado entre os que ainda não foram
    anexados, e mais os curtidos_de_fora (o de outra cor que saiu antes de anexar continua
    curtido no alto). Com a lista limpa (a limpeza anterior deu certo), o produto não é procurado
    rolando a lista inteira (P27). O 1º anexado é conferido na tela final depois do Feito e,
    sem ele, anexado de novo uma vez (VEZES_DO_PRIMEIRO_PRODUTO).
    """
    anexados, no_post = [], []
    _AVISO_DO_FEITO.update(texto="", logo="")
    for i, nome in enumerate(nomes):
        if i in a_mais and prazo is not None and time.monotonic() > prazo:
            registro_processos.registrar(REGISTRO, PROCESSO_DOS_ESPACOS, "produto a mais de fora",
                                         "sem tempo na rodada", ok=None)
            continue
        primeiro = not anexados
        for vez in range(1, (VEZES_DO_PRIMEIRO_PRODUTO if primeiro else 1) + 1):
            if not _anexar_um(d, video, nome, anexados, len(nomes) - len(anexados) + curtidos_de_fora, limpa,
                              i in a_mais):
                break
            if not primeiro or primeiro_na_tela_final(d, vez, anexados[0] if anexados else nome):
                no_post.append(i)
                break
            # O Feito não deixou o produto na tela final: ele sai da conta e vai de novo.
            anexados.clear()
        else:
            # O produto que o app não deixa na tela final nem na 2ª vez: a falha é da hora, e o
            # vídeo volta mais tarde (P182 1).
            aviso = _AVISO_DO_FEITO["texto"]
            raise Parada(MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU + (f"; o app avisou: {aviso}" if aviso else ""))
    return anexados, no_post


def _anexar_um(d, video, nome, anexados, no_topo, limpa, a_mais):
    """
    Um produto: o caminho até Minhas Curtidas, o Adicionar dele e o Feito. False quando é um
    produto a mais que não anexou: ele fica de fora, e o robô volta à tela final.
    """
    seguir(d, CAMINHO_PRODUTO if not anexados else CAMINHO_MAIS_UM_PRODUTO)
    ok, motivo = ps.adicionar_produto(d, dict(video, produto=nome), anexados, no_topo=no_topo,
                                      rolar_a_lista=not limpa, ultima_chance=not a_mais, avisar=not a_mais)
    if not ok and a_mais:
        registro_processos.registrar(REGISTRO, PROCESSO_DOS_ESPACOS, "produto a mais de fora", "não anexou", ok=None)
        voltar_a_tela_final(d)
        return False
    _conferir((ok, motivo))
    limpar_aviso_do_app(d)
    # A tela de logo depois do Feito vai para o caso e, em rótulos fixos, para o registro do produto
    # que não ficou; a espera de depois do Feito continua a mesma.
    tocar(d, "Feito", ESPERA_LOGO_DEPOIS_DO_FEITO)
    try:
        _AVISO_DO_FEITO["logo"] = como_ficou_logo_depois_do_feito(tela(d))
        casos_robo.anotar_tela(d, "tela logo depois do Feito")
    except (Verificacao, Parada):
        raise
    except Exception:
        # Só anota: a leitura que falha não para o rascunho (a conferência da tela final relê).
        _AVISO_DO_FEITO["logo"] = ""
    time.sleep(ESPERA_DEPOIS_DO_FEITO - ESPERA_LOGO_DEPOIS_DO_FEITO)
    return True


def como_ficou_logo_depois_do_feito(xml):
    """
    Como estava a tela logo depois do Feito, em rótulos fixos (o registro é público): a janela do
    produto ainda aberta, a tela final (como ela voltou: ps.como_esta_a_tela_final) ou outra tela.
    """
    if ps.janela_de_editar_aberta(ps.elementos(xml)):
        return "a janela do produto ainda aberta"
    if tem(xml, "@et_caption"):
        return "a tela final, " + ps.como_esta_a_tela_final(xml)
    return "outra tela"


def primeiro_na_tela_final(d, vez=1, nome=""):
    """
    Depois do Feito do 1º produto, a tela final mostra o produto na fileira? Relê a tela por
    até ps.ESPERA_DA_FILEIRA s. Sem ele, ou quando ele só veio na 2ª vez, o registro diz como a
    tela voltou (a linha dos produtos, a edição da legenda aberta por cima, a legenda em foco)
    e os sinais do nome do produto (ps.forma_do_nome), só com rótulos fixos: o próximo caso
    mostra a causa (pedido do Rafael de 30/10). O que fica de primeira anota os sinais dele
    (sinais_de_quem_ficou), para o checkup comparar com os que não ficam.
    """
    xml = tela(d)
    for _ in range(ps.ESPERA_DA_FILEIRA // 3):
        if ps.produtos_na_fileira(xml):
            break
        pausa(3)
        xml = tela(d)
    if ps.produtos_na_fileira(xml):
        if vez > 1:
            registro_processos.registrar(REGISTRO, "anexar o produto", f"anexado na {vez}ª vez",
                                         ps.como_esta_a_tela_final(xml) + ps.forma_do_nome(nome), ok=True)
        else:
            registro_processos.registrar(REGISTRO, PROCESSO_DOS_SINAIS_DO_APP, FICOU_DE_PRIMEIRA,
                                         sinais_de_quem_ficou(d), ok=None)
        return True
    lido, aviso = aviso_do_app(d)
    _AVISO_DO_FEITO["texto"] = aviso
    # O texto do aviso pode trazer o nome do produto: no registro (o checkup é público), só se houve.
    sobre_o_aviso = ("; o app mostrou um aviso" if aviso else "; sem aviso do app") if lido else ""
    logo = _AVISO_DO_FEITO.get("logo")
    registro_processos.registrar(REGISTRO, "anexar o produto", "não ficou depois do Feito",
                                 f"{vez}ª vez; {ps.como_esta_a_tela_final(xml)}{sobre_o_aviso}"
                                 + (f"; logo depois do Feito: {logo}" if logo else "") + ps.forma_do_nome(nome),
                                 ok=False)
    registro_processos.registrar(REGISTRO, PROCESSO_DOS_SINAIS_DO_APP, f"{vez}ª vez", sinais_do_app(d), ok=None)
    fechar_a_edicao_da_legenda(d, xml)
    return False


# Os sinais de que o app da Shopee estava instável perto do produto que não ficou: em 08/11 (das
# 19:04 às 19:31), no começo da noite em que o app travou 3 vezes e a leitura da tela veio sem ele
# 4 vezes, 2 produtos diferentes não ficaram seguidos (nem na 2ª vez) e 1 só ficou na 2ª vez,
# depois de um dia em que todos ficaram de primeira. A cada produto que não fica, o registro
# (PROCESSO_DOS_SINAIS_DO_APP, numa linha à parte: a do anexar já chega perto do tamanho que o
# registro guarda) diz quantas vezes o app travou e a leitura veio sem ele nesta janela, e há
# quantos minutos o app está aberto, para separar o produto da hora (só números e rótulos fixos:
# o registro sai no checkup público).
PROCESSO_DOS_SINAIS_DO_APP = "sinais do app no anexar"
JANELA_DOS_SINAIS_DO_APP = timedelta(hours=1)
# Em 09/11, das 13:08 às 13:37, 4 produtos diferentes seguidos não ficaram (nem na 2ª vez), sem o
# app travar nem a leitura vir sem ele, com o app aberto havia 16 h; na mesma hora, a busca de
# ofertas da API de afiliado deu o erro de sistema da própria Shopee (api_shopee), e às 14:03 o
# produto seguinte ficou de primeira. A linha dos sinais diz também quantas buscas da API deram
# esse erro nesta janela, e o produto que fica de primeira ganha a mesma linha (FICOU_DE_PRIMEIRA,
# com o app aberto em faixas de horas, para o checkup agrupar): o checkup compara os que ficam com
# os que não ficam, e separa a falha da Shopee da do app aberto há muito tempo.
FICOU_DE_PRIMEIRA = "ficou de primeira"
FAIXAS_DO_APP_ABERTO = ((1, "menos de 1 h"), (6, "1 a 6 h"), (12, "6 a 12 h"), (24, "12 a 24 h"))
# Em 10/11, das 05:44 às 06:24, 3 produtos seguidos não ficaram, com o app aberto havia 16 h e o
# Java dele perto do teto (512 MB no Motorola), pelo log do coletor: a cada Feito, o app refazia a
# tela de publicar e perdia o produto. A linha dos sinais diz também a memória do Java do app
# (casos_robo.memoria_do_app), e a do que fica de primeira, em faixas (FAIXAS_DA_MEMORIA, em MB).
FAIXAS_DA_MEMORIA = ((300, "menos de 300 MB"), (400, "300 a 400 MB"), (450, "400 a 450 MB"))


def sinais_do_app(d, agora=None):
    """
    Os sinais do app em rótulos fixos, como "na última hora: app travado 1, leitura sem o app 0,
    erro de sistema da Shopee na API 2; o app aberto há 95 min; a memória do app 310 de 400 MB".
    """
    desde = (agora_br(agora) - JANELA_DOS_SINAIS_DO_APP).strftime("%Y-%m-%d %H:%M:%S")
    travado = len(registro_processos.sequencia(REGISTRO, "app travado", desde))
    sem_o_app = sum(1 for linha in registro_processos.sequencia(REGISTRO, PROCESSO_DA_LEITURA_DA_TELA, desde)
                    if str(linha[3]).startswith("sem o app"))
    minutos = casos_robo.minutos_do_app(d, ps.PACOTE)
    memoria = casos_robo.memoria_do_app(d, ps.PACOTE)
    return (f"na última hora: app travado {travado}, leitura sem o app {sem_o_app}, "
            f"erro de sistema da Shopee na API {erros_da_api_da_shopee(desde)}"
            + (f"; o app aberto há {minutos} min" if minutos is not None else "")
            + (f"; a memória do app {memoria[0]} de {memoria[1]} MB" if memoria else ""))


def sinais_de_quem_ficou(d, agora=None):
    """
    Os sinais do produto que ficou de primeira, em faixas que o checkup agrupa: "na última hora:
    erro de sistema da Shopee na API 0; o app aberto há 12 a 24 h; a memória do app 300 a 400 MB".
    """
    desde = (agora_br(agora) - JANELA_DOS_SINAIS_DO_APP).strftime("%Y-%m-%d %H:%M:%S")
    minutos = casos_robo.minutos_do_app(d, ps.PACOTE)
    memoria = casos_robo.memoria_do_app(d, ps.PACOTE)
    return (f"na última hora: erro de sistema da Shopee na API {erros_da_api_da_shopee(desde)}"
            + (f"; o app aberto há {faixa_do_app_aberto(minutos)}" if minutos is not None else "")
            + (f"; a memória do app {faixa_da_memoria_do_app(memoria[0])}" if memoria else ""))


def faixa_do_app_aberto(minutos):
    """Há quanto tempo o app está aberto, na faixa de FAIXAS_DO_APP_ABERTO ("mais de 1 dia" depois da última)."""
    return next((rotulo for horas, rotulo in FAIXAS_DO_APP_ABERTO if minutos < horas * 60), "mais de 1 dia")


def faixa_da_memoria_do_app(megas):
    """A memória do Java do app na faixa de FAIXAS_DA_MEMORIA ("450 MB ou mais" depois da última)."""
    return next((rotulo for teto, rotulo in FAIXAS_DA_MEMORIA if megas < teto), "450 MB ou mais")


def erros_da_api_da_shopee(desde):
    """
    Quantas buscas da API de afiliado deram o erro de sistema da própria Shopee desde o momento
    ("AAAA-MM-DD HH:MM:SS"), em qualquer robô: as que a nova tentativa salvou e as negadas por ele.
    """
    salvas = registro_processos.sequencia(api_shopee.ROBO_DO_REGISTRO, api_shopee.PROCESSO_DO_ERRO_DE_SISTEMA, desde)
    negadas = registro_processos.sequencia(api_shopee.ROBO_DO_REGISTRO, api_shopee.PROCESSO_DA_BUSCA_NEGADA, desde,
                                           resultado=api_shopee.RESULTADO_DO_ERRO_DE_SISTEMA)
    return len(salvas) + len(negadas)


# O último aviso curto (toast) do app depois do Feito do produto que não ficou, para a parada dizer
# o que o app respondeu (31/10/2026, 15:21 e 15:35: o mesmo produto não ficou duas vezes, e a tela
# não dizia por quê).
# Com ele, logo: como estava a tela logo depois do último Feito (como_ficou_logo_depois_do_feito).
_AVISO_DO_FEITO = {"texto": "", "logo": ""}


def limpar_aviso_do_app(d):
    """Esquece o último aviso curto (toast) do app: o que vier depois do próximo toque é dele."""
    try:
        d.clear_toast()
    except Exception:
        pass


def aviso_do_app(d):
    """
    O último aviso curto (toast) que o app mostrou, pelo uiautomator2: (lido, texto, sem os
    números). Sem conseguir ler, (False, ""); lido e sem aviso, (True, ""). No uiautomator2 o
    last_toast é uma propriedade, não uma função (chamada, dava erro, e o robô nunca lia o aviso).
    """
    try:
        texto = d.last_toast
    except Exception:
        return False, ""
    return True, re.sub(r"\d+", "#", str(texto or "")).strip()[:100]


def fechar_a_edicao_da_legenda(d, xml):
    """
    A edição da legenda aberta por cima da tela final (rl_overlay, a tela escurecida) cobre a
    linha dos produtos, e o toque no Adicionar produto cairia nela. Um toque no rótulo
    "Adicionar produto", que não é botão, a fecha; sem ela por cima, o toque não faz nada.
    """
    rotulo = ps.achar(xml, "@tv_add_product_title")
    if tem(xml, "@rl_overlay") and rotulo and not ps.proibido_no_ponto(xml, *rotulo):
        d.click(*rotulo)
        pausa(3)


def voltar_a_tela_final(d, vezes=3):
    """
    Depois do produto a mais que não anexou, volta da lista de Minhas Curtidas (ou da janela de
    editar o nome) para a tela final; o aviso de sair dela, se abrir, fica no Cancelar. Os
    produtos vão antes da legenda, e sem a legenda escrita um voltar a mais na tela final leva à
    edição do vídeo sem aviso: depois de cada voltar, a tela final tem uns segundos para
    aparecer antes do próximo.
    """
    for _ in range(vezes):
        xml = tela(d)
        if tem(xml, "@et_caption"):
            return
        if aviso_de_sair(xml):
            tocar(d, "Cancelar", 3)
            continue
        d.press("back")
        pausa(3)
        if esperar_na_tela(d, "@et_caption", ESPERA_A_MAIS_NO_CAMINHO):
            return
    if not tem(tela(d), "@et_caption"):
        raise Parada("o produto a mais não anexou, e o voltar não voltou à tela final")


def escrever_a_legenda(d, titulo):
    """
    O título da IA na legenda da tela final, conferido pela cópia do campo (com os emojis), e o
    OK que fecha a edição dela. Vai depois dos produtos (VEZES_DO_PRIMEIRO_PRODUTO diz por quê).
    """
    tocar(d, "@et_caption", 3)
    ps.escrever(d, titulo)
    pausa(3)
    copiada = ps.legenda_copiada(d)
    na_tela = copiada or ps.legenda_lida(d)
    if not mesma_legenda(na_tela, titulo):
        # Por onde leu, tamanhos e códigos de caractere, nunca o texto: o diagnóstico do
        # servidor, que é público, mostra esta conferência para achar o que não bateu.
        conferencia = (f"{'pela cópia' if copiada else 'sem a cópia, pela acessibilidade'}: "
                       f"{ps.comparar_legenda(na_tela, titulo)}; {_forma_do_titulo(titulo)}")
        gravar_estado(ultima_legenda=conferencia, ultima_legenda_em=_momento())
        raise Parada(f"o título não ficou na legenda ({conferencia})")
    tocar(d, "@tv_right", 3)


# --- A capa com a frase no post ---
# A capa com a frase abre o vídeo (P125), e o app usa o 1º quadro como capa da grade (P129): no
# post, o registro diz se a faixa da frase (na cor do produto, P159 2) chegou à grade
# (marcar_o_post). Escolhas do Rafael: DECISOES.md, Shopee Vídeo.
PROCESSO_DA_CAPA = "capa no post"
PROCESSO_DO_BOTAO = "preparar 1 agora"
# A faixa da capa com a frase vai de um lado ao outro da capa: a cor dela mais estreita que isto da
# largura do quadro é outra coisa (o selo Fixado da grade, um produto da mesma cor na foto).
LARGURA_DA_FAIXA_NA_CAPA = 0.6


def faixa_da_capa(imagem, caixa, cor=None):
    """
    A faixa da capa com a frase (laranja, ou na cor do produto, P159 2) na caixa (x1, y1, x2, y2)
    da imagem do PIL, o quadro da grade: (cima, baixo, esquerda, direita), ou None. Só a que vai de
    um lado ao outro da caixa (LARGURA_DA_FAIXA_NA_CAPA).
    """
    faixa = edicao_video.faixa_laranja(imagem, caixa, cor)
    if faixa and faixa[3] - faixa[2] >= (caixa[2] - caixa[0]) * LARGURA_DA_FAIXA_NA_CAPA:
        return faixa
    return None


def _preparar(d, ident, video, fonte, agora=None, curtidos=None, celular=None):
    """
    O rascunho no celular. curtidos recebe cada produto que o robô curtiu (descurtir_no_fim);
    celular ganha um item quando o robô começa a usar o celular.
    """
    curtidos = [] if curtidos is None else curtidos
    celular = [] if celular is None else celular
    vistos = []
    inicio = time.monotonic()
    prazo = inicio + MINUTOS_PARA_OS_ESPACOS * 60
    # principal: o produto do link (ou o da troca); produtos: os do rascunho de link de
    # produto na ordem do post, com o link de cada um. No Ver Produtos, os dois ficam None, e
    # do_ver_produtos tem os do post, na ordem (os do criador, os trocados e os a mais).
    principal = produtos = do_ver_produtos = None
    # No Ver Produtos, os de outra cor (nome, foto da página): a foto deles vai na miniatura. Nos
    # produtos a mais, as fotos de capa dos que a IA recusou: o álbum dos recusados do rascunho.
    variacoes, recusados = [], []
    # No Ver Produtos, o link curto de cada produto trocado pelo da loja que paga mais (P57).
    links_trocados, trocados = {}, 0
    if video.get("de_video"):
        celular.append(True)
        avisar("🤖 Robô da Shopee Vídeo: começando um rascunho.\n\nProdutos: os do Ver Produtos do vídeo; a IA "
               "confere cada um.\n" + de_onde_veio_o_video(video, fonte))
        fotos_da_pagina = {}
        nomes = _produtos_do_video(d, video, vistos, curtidos, variacoes, fotos_da_pagina)
        # Cada um trocado pelo mesmo item da loja que paga mais, e todos do que paga mais por venda
        # para o que paga menos (o 1º dá a foto da edição). Escolhas do Rafael (28/10, P57 e P58;
        # 05/11, P154 3): DECISOES.md, Shopee Vídeo.
        do_ver_produtos = trocar_os_do_ver_produtos(d, video, nomes, fotos_da_pagina, vistos, curtidos, prazo,
                                                    {nome for nome, _foto in variacoes})
        nomes = [p["nome"] for p in do_ver_produtos]
        # O 1º produto (o que dá a foto da edição) que já foi ao ar não se repete (P166 1).
        atualizar(ident, itens_do_video=[p["item"] for p in do_ver_produtos if p.get("do_video") and p.get("item")])
        if do_ver_produtos and do_ver_produtos[0].get("item") in produtos_ja_postados():
            anotar_onde_ja_foi(do_ver_produtos[0]["item"], "robô")
            raise Parada(PRODUTO_JA_POSTADO, do_video=True)
        # O mínimo por venda, que só o celular deixa ver no vídeo de link de vídeo (P200 1).
        conferir_o_minimo_do_ver_produtos(do_ver_produtos)
        links_trocados = {p["nome"]: p["link"] for p in do_ver_produtos if p["trocado"]}
        trocados = len(links_trocados)
        # A medição de quais posts levam punição (P146 2) cruza a troca com a Saúde.
        atualizar(ident, trocado="1" if trocados else "0")
        if trocados:
            avisar(f"🤖 Robô da Shopee Vídeo: troquei {trocados} de {len(do_ver_produtos)} produto(s) do Ver "
                   "Produtos pelo mesmo item de outra loja, que paga mais por venda (conferido pela IA com o vídeo):\n"
                   + "\n".join(f"• {p['nome']}: {p['comissao']:.1f}%, "
                               f"{assistente._reais(p['valor'])} por venda (o do criador pagava {p['antes']:.1f}%, "
                               f"{assistente._reais(p['valor_antes'])})" for p in do_ver_produtos if p["trocado"]))
    else:
        nome = ps.nome_do_produto(video)
        if not nome:
            raise Parada("o link não diz o produto do vídeo", do_video=True)
        # O preço do produto do link do post: a régua dos 20% dos produtos a mais (P58).
        do_post, _ = asyncio.run(assistente.produtos_do_link(video["link"]))
        original = do_post[0] if do_post else {}
        # O mesmo produto de outra loja que paga mais por venda, já conferido pela IA com o
        # vídeo, toma o lugar do produto do link (o video muda aqui: curtir, anexar e descurtir
        # usam o novo). Escolhas do Rafael (25/10, P33; 28/10, P58): DECISOES.md, Shopee Vídeo.
        troca = trocar_pela_maior_comissao(video)
        # Se o produto foi trocado pelo de outra loja: a medição de quais posts levam punição
        # (P146 2, apelacoes_shopee_video.punicoes_por_tipo_de_post) cruza isso com a Saúde.
        atualizar(ident, trocado="1" if troca else "0")
        if troca:
            video["link"] = troca["link"]
            nome = ps.nome_do_produto(video) or troca["nome"]
            vistos.extend(troca["vistos"])
        # Antes de tocar no celular, o Rafael sabe qual vídeo e qual produto o robô pegou.
        avisar(f"🤖 Robô da Shopee Vídeo: começando um rascunho.\n\nProduto: {nome}\n"
               + (f"Comissão: {troca['comissao']:.1f}%, {assistente._reais(troca['valor'])} por venda (o produto do "
                  f"link pagava {troca['antes']:.1f}%, {assistente._reais(troca['valor_antes'])}: troquei pelo mesmo "
                  "produto de outra loja, conferido pela IA com o vídeo)\n" if troca else "")
               + de_onde_veio_o_video(video, fonte))
        achado = None
        if not troca:
            ok, motivo = ps.ia_confere_produto(video, vistos, avisar=False)
            if not ok and motivo.startswith(ps.MOTIVO_OUTRO_PRODUTO):
                # O produto do link não é o do vídeo: o robô procura o do vídeo na Shopee, com a
                # mesma conferência dupla da IA (P158 2).
                achado = achar_o_produto_do_video(video)
                if not achado:
                    avisar(f"{ps.AVISO_IA}\n\nProduto do link: {nome}\nO que a IA viu: {vistos[-1] if vistos else ''}\n"
                           "Procurei o produto do vídeo na Shopee, e a IA não confirmou nenhum.")
            if not ok and not achado:
                # O produto e o que a IA viu ficam no rascunho pulado: o caso do checkup do
                # Claude (casos_robo) os lê dele.
                atualizar(ident, fonte=fonte, produtos=[nome], conferencia=json.dumps(vistos, ensure_ascii=False))
                raise Parada(motivo, do_video=True)
        # A medição de quais posts levam punição (P146 2) separa o produto achado pela IA.
        atualizar(ident, achado="1" if achado else "0")
        if achado:
            video["link"] = achado["link"]
            nome = ps.nome_do_produto(video) or achado["nome"]
            vistos.extend(achado["vistos"])
            # O achado é o produto do post também para a régua dos produtos a mais (P58).
            original = {"nome": nome, "preco": achado["preco"], "comissao": achado["comissao"],
                        "imagem": achado["imagem"]}
            avisar(f"🤖 Robô da Shopee Vídeo: o produto do link não era o do vídeo. Achei o do vídeo na Shopee, "
                   f"conferido {ps.VEZES_DA_IA} vezes pela IA com a foto do anúncio:\n\nProduto: {nome}\n"
                   f"Comissão: {achado['comissao']:.1f}%, {assistente._reais(achado['valor'])} por venda")
        principal = {"nome": nome, "link": video["link"], "do_video": True,
                     "preco": troca["preco"] if troca else original.get("preco", 0),
                     "comissao": troca["comissao"] if troca else original.get("comissao", 0)}
        principal["valor"] = valor_por_venda(principal["preco"], principal["comissao"])
        principal["item"] = item_do_link(video["link"])
        # O produto que vai ao post (o da troca ou o achado pela IA) também não pode já ter ido (P166 1).
        atualizar(ident, itens_do_video=[i for i in dict.fromkeys((video.get("item_do_link"), principal["item"])) if i])
        if principal["item"] and principal["item"] in produtos_ja_postados():
            anotar_onde_ja_foi(principal["item"], "robô")
            raise Parada(PRODUTO_JA_POSTADO, do_video=True)
        nomes = [nome]
    # A origem e o que a IA viu ficam no rascunho, para o Rafael validar com isso na mão.
    atualizar(ident, fonte=fonte, conferencia=json.dumps(vistos, ensure_ascii=False))
    textos = _textos_da_ia(video, nomes)
    if textos["violacao"]:
        avisar(f"⚠️ Robô da Shopee Vídeo: pulei o vídeo. A IA viu possível violação das diretrizes: "
               f"{textos['motivo'] or 'sem motivo'}")
        raise Parada("a IA viu violação das diretrizes", do_video=True)
    # Bebida alcoólica em espera enquanto a página oficial das diretrizes a proíbe: fica de lado
    # antes dos produtos a mais e da edição. Escolha do Rafael (31/10, P111): DECISOES.md,
    # Shopee Vídeo.
    if assistente.bebida_em_espera(textos):
        raise Parada(assistente.MOTIVO_BEBIDA_EM_ESPERA, do_video=True)

    # Vídeo claramente feito por IA vai com o Rótulo de IA ligado; na dúvida, desligado.
    # Escolha do Rafael (24/10, P8): DECISOES.md, Shopee Vídeo.
    rotulo_ia = (textos.get("sinal_ia") or "a IA viu que o vídeo é gerado por IA") if textos.get("feito_por_ia") else ""

    if principal:
        # Os espaços livres com o mesmo item de outras lojas (P59), depois das conferências sem
        # o celular e antes da edição: todos são curtidos, e o 1º, o que paga mais por venda, dá
        # a foto da edição e o link do rascunho (P57). Escolhas do Rafael:
        # DECISOES.md, Shopee Vídeo.
        celular.append(True)
        mais = espacos_livres(d, video, principal, original, vistos, prazo, inicio, recusados)
        produtos = _curtir_os_produtos(d, video, ordem_do_post(principal, mais), curtidos)
        video["link"] = produtos[0]["link"]
        nomes = [p["nome"] for p in produtos]
        atualizar(ident, conferencia=json.dumps(vistos, ensure_ascii=False))
    elif do_ver_produtos is not None:
        # No Ver Produtos, os espaços que sobram, até 6, com o mesmo item de outras lojas (P59),
        # depois dos produtos do criador e do Ver Mais (P66), na mesma hora do preparo.
        do_ver_produtos = espacos_do_ver_produtos(d, video, do_ver_produtos, vistos, prazo, inicio, recusados,
                                                  curtidos, variacoes)
        nomes = [p["nome"] for p in do_ver_produtos]
        atualizar(ident, conferencia=json.dumps(vistos, ensure_ascii=False))

    os.makedirs(PASTA_RASCUNHOS, exist_ok=True)
    copia = os.path.join(PASTA_RASCUNHOS, f"{ident}.mp4")
    # Com produtos a mais (o mesmo item de outras lojas), a miniatura troca entre as fotos de capa
    # diferentes dos produtos do post (P103). No Ver Produtos, entre a foto do 1º e as dos de outra
    # cor (a foto da página de cada um): eles aparecem no vídeo. Pedido do Rafael (01/11):
    # DECISOES.md, Shopee Vídeo.
    outras = [foto for foto in (foto_do_produto_do_post(video, p) for p in (produtos or [])[1:]) if foto]
    if do_ver_produtos is not None:
        # Os de outra cor e os produtos a mais (o mesmo item do 1º, de outras lojas), na ordem do post.
        da_pagina = dict(variacoes)
        outras = [foto for foto in (da_pagina.get(p["nome"]) if p["nome"] in da_pagina
                                    else None if p.get("do_video") else p.get("foto")
                                    for p in do_ver_produtos[1:]) if foto]
    # O link curto de cada produto do Ver Produtos que não é o do criador (o trocado, P57, e o a mais).
    links_conhecidos = {p["nome"]: p["link"] for p in do_ver_produtos or [] if p.get("link")}
    # A capa com a frase abre o vídeo, e o app usa o 1º quadro como capa da grade. Escolha do
    # Rafael (02/11, P125): DECISOES.md, Shopee Vídeo.
    miniatura, edicao = {}, {}
    como = copiar_para_o_rascunho(video, fonte, copia, nomes, alcool=textos.get("bebida_alcoolica", False),
                                  outras=outras, miniatura=miniatura, rotulo_de_ia=bool(rotulo_ia),
                                  link_do_1o=links_conhecidos.get(nomes[0]) if nomes else None, edicao=edicao)
    # O de outra cor só vai com a foto dele na miniatura que troca: sem ela (sem a nossa
    # miniatura, ou sem tempo para a foto dele), sai antes de anexar. Ele já foi curtido e fica no
    # alto de Minhas Curtidas até o descurtir do fim: o anexar procura os outros abaixo dele.
    # Pedidos do Rafael (01/11 e 02/11): DECISOES.md, Shopee Vídeo.
    antes = len(nomes)
    de_outra_cor = dict(variacoes)
    if produtos:
        produtos = com_a_foto_na_miniatura([(p, p.get("foto"), p.get("outra_cor")) for p in produtos],
                                           miniatura.get("fotos", []))
        nomes = [p["nome"] for p in produtos]
    elif de_outra_cor:
        nomes = com_a_foto_na_miniatura([(n, de_outra_cor.get(n), n in de_outra_cor) for n in nomes],
                                        miniatura.get("fotos", []))
    if do_ver_produtos is not None:
        por_nome = {p["nome"]: p for p in do_ver_produtos}
        do_ver_produtos = [por_nome[n] for n in nomes]
    # O do criador trocado pelo da loja que paga mais (P57) também continua curtido no alto.
    curtidos_de_fora = antes - len(nomes) + trocados
    atualizar(ident, arquivo=copia, link=video["link"], produtos=nomes, titulo=textos["titulo"],
              comentario=textos.get("comentario") or "", rotulo_ia=rotulo_ia,
              mais_produtos=_mais_produtos(produtos[1:] if produtos else []),
              chamada="1" if edicao_video.COM_A_CHAMADA in (como or "") else "", cor=edicao.get("cor", ""),
              letras=edicao.get("letras", ""), edicao=edicao.get("guardado") or {})
    ir_ao_perfil(d)

    # O vídeo na galeria com um nome só dele: o mais novo da galeria é o que vai no rascunho.
    if not ps.por_na_galeria(d, copia, nome_na_galeria(ident)):
        raise Parada("o vídeo não apareceu na galeria do celular")
    abrir_galeria(d, agora)
    marcar_so_o_mais_novo(d)
    seguir(d, CAMINHO_EDICAO[:1])
    efeitos_na_edicao(d)
    seguir(d, CAMINHO_EDICAO[1:])

    # Os curtidos agora ficam em cima da lista: o 2º produto do vídeo procura entre os que
    # sobraram no topo. A tela final e o postar conferem o nome que a lista mostra, que pode
    # ser outro que o da API. Escolha do Rafael (P18): DECISOES.md, Shopee Vídeo.
    # Com a lista limpa (a limpeza anterior deu certo), o produto não é procurado rolando a
    # lista inteira; o topo continua conferido. Escolha do Rafael (P27): DECISOES.md, Shopee Vídeo.
    a_mais = {i for i, produto in enumerate(produtos or do_ver_produtos or []) if not produto.get("do_video")}
    anexados, no_post = anexar_os_produtos(d, video, nomes, a_mais, lista_limpa(),
                                           inicio + MINUTOS_PARA_ANEXAR_OS_A_MAIS * 60, curtidos_de_fora)
    # A legenda vai depois dos produtos: em foco nas idas à lista de Minhas Curtidas, o 1º
    # produto às vezes não fica (VEZES_DO_PRIMEIRO_PRODUTO).
    escrever_a_legenda(d, textos["titulo"])
    _conferir(ps.conferir_tela_final(d, dict(video, produtos=anexados)))
    if produtos:
        ordem = [produtos[i] for i in no_post]
        capas = guardar_capas(ident, video, ordem) if len(ordem) > 1 else []
        # Os de outra foto de capa que a do anúncio do post vêm marcados (P102).
        outras = com_outra_foto_de_capa(video, ordem, foto_do_anuncio(original.get("imagem"))) if capas else []
        atualizar(ident, produtos=anexados, link=ordem[0]["link"], mais_produtos=_mais_produtos(ordem[1:]),
                  itens=_itens(ordem), capas=capas, outras_capas=outras,
                  recusadas=guardar_recusados(ident, recusados),
                  outra_cor=[n for n, produto in enumerate(ordem, 1) if produto.get("outra_cor")])
    else:
        ordem = [do_ver_produtos[i] for i in no_post] if do_ver_produtos else []
        a_mais_do_ver = {}
        if any(not p.get("do_video") for p in ordem):
            # Com produtos a mais, como no link de produto: o álbum das capas (P75), a marca do
            # produto a mais com outra foto de capa que a do anúncio do 1º do criador (P102) e os
            # números da medição (P73).
            base = next((p for p in do_ver_produtos if p.get("base")), {})
            capa = foto_do_anuncio(base.get("imagem")) if base.get("imagem") else None
            a_mais_do_ver = {"itens": _itens(ordem), "capas": guardar_capas(ident, video, ordem),
                             "outras_capas": [n for n, p in enumerate(ordem, 1) if not p.get("do_video") and capa
                                              and mesma_foto(foto_do_produto_do_post(video, p), capa) is False]}
        atualizar(ident, produtos=anexados,
                  links_dos_produtos=links_do_ver_produtos(anexados, [links_conhecidos.get(nomes[i], "")
                                                                      for i in no_post]),
                  outra_cor=[n for n, i in enumerate(no_post, 1) if nomes[i] in de_outra_cor],
                  recusadas=guardar_recusados(ident, recusados), **a_mais_do_ver)
    # Antes do print: o Rafael vê no print a chave como vai ao ar.
    _conferir(ps.ajustar_rotulo_de_ia(d, bool(rotulo_ia)))

    print_tela = os.path.join(PASTA_RASCUNHOS, f"{ident}.png")
    d.screenshot(print_tela)
    tocar(d, "@tv_drafts_box", 12)
    if tem(tela(d), "@btn_post"):
        raise Parada("toquei em Rascunhos, mas o app continuou na tela final")
    atualizar(ident, estado="rascunho", print=print_tela)
    esperando = len(esperando_aprovacao())
    a_mais_no_post = sum(1 for i in no_post if i in a_mais)
    em_outra_cor = sum(1 for i in no_post if i in a_mais and (produtos or do_ver_produtos or [])[i].get("outra_cor"))
    de_outras_lojas = (f"{a_mais_no_post} de outras lojas: {a_mais_no_post - em_outra_cor} iguais e {em_outra_cor} "
                       "em outra cor, com a foto na miniatura" if em_outra_cor
                       else f"{a_mais_no_post} iguais de outras lojas")
    avisar("📝 Robô da Shopee Vídeo: rascunho novo salvo no celular"
           + (f", com {len(anexados)} produtos ({'os' if do_ver_produtos else 'o'} do vídeo e {de_outras_lojas})"
              if a_mais_no_post else "")
           + f". {esperando} esperando a sua aprovação em Shopee Vídeo 🎬 → Rascunhos do Robô 📝.")


PROCESSO_DA_EDICAO = "edição do vídeo: rascunho do robô"
# A miniatura das variações (P103): uma só ou alternada, com quantas fotos e o tempo de cada.
PROCESSO_DA_MINIATURA = "edição do vídeo: miniatura das variações"
MOTIVO_SEM_EDICAO = "a edição do vídeo não saiu: só vídeo editado vai à Shopee Vídeo"
MOTIVO_SEM_AVISOS = "bebida alcoólica só vai com os avisos na capa, e a edição dos vídeos está desligada"


def copiar_para_o_rascunho(video, fonte, copia, nomes=(), alcool=False, outras=(), miniatura=None, rotulo_de_ia=False,
                           link_do_1o=None, edicao=None):
    """
    A cópia do vídeo que vai ao rascunho. Com a edição ligada, ela vai com o Editor 2: o vídeo
    original, sem cortes, com a foto do produto no começo, a miniatura e a seta (todos os vídeos
    do Rafael são autorais) e as legendas (nome, vantagem e uma chamada para o produto, P80); se
    o Editor 2 não sai, com o Editor 1, sem legendas (edicao_video.editar_para_postar). No vídeo
    de Ver Produtos, a foto é a do 1º produto anexado (nomes[0]). Com a edição ligada,
    só vai vídeo editado: o que não sai editado fica de lado (Parada) e o robô pega o próximo;
    sem a foto do anúncio, o vídeo não volta, e o ffmpeg que falhou deixa tentar de novo
    depois. Bebida alcoólica (alcool=True) abre com a capa dos avisos da Shopee no lugar da
    foto, e sem a edição ela não tem como levar os avisos: fica de lado. Devolve como o vídeo
    saiu (o jeito de edicao_video.editar_para_postar; "" sem a edição). outras: as fotos de capa
    dos outros produtos do post, na ordem, no rascunho com produtos a mais (o mesmo item): com
    elas, a miniatura troca entre as fotos diferentes (fotos_da_miniatura, P103). Com a capa com
    chamada ligada, o vídeo abre com a capa com a frase (P125). miniatura (dict) recebe em
    "fotos" as fotos da miniatura que troca no vídeo, a do 1º e as outras, e nada sem a nossa
    miniatura: o de outra cor só vai no post com a foto dele nela (com_a_foto_na_miniatura). Com
    rotulo_de_ia=True (o vídeo vai com o Rótulo de IA ligado), a moldura do cartão, as setinhas e a
    legenda da fala sobem com o cartão do app, que sobe com a linha do rótulo (03/11). link_do_1o:
    no Ver Produtos, o link curto do 1º produto trocado pelo da loja que paga mais (P57): a foto vem
    do anúncio dele, como no link de produto. edicao (dict) recebe em "cor" a cor em que a faixa da
    capa saiu (a do produto, P159 2, ou a 2ª cor ou o tom no lugar da que some na foto, P173 e P174 3;
    "" com o laranja).
    Escolhas do Rafael (25/10, P37, depois da P38, P39 e "só vídeos editados"; 26/10, P43;
    28/10, Editor 2, P51): DECISOES.md, Shopee Vídeo.
    """
    if not edicao_video.vale_para(fonte):
        if alcool:
            raise Parada(MOTIVO_SEM_AVISOS, do_video=True)
        shutil.copyfile(video["arquivo"], copia)
        return ""
    if video.get("de_video") and link_do_1o:
        anuncio = ps.anuncio_do_produto(dict(video, link=link_do_1o))
    elif video.get("de_video"):
        anuncio = anuncio_do_ver_produtos(nomes[0]) if nomes else {}
    else:
        anuncio = ps.anuncio_do_produto(video)
    trocam = fotos_da_miniatura(video, anuncio["foto"], outras) if outras and anuncio.get("foto") else []
    motivo, como, detalhe = edicao_video.editar_para_postar(video["arquivo"], anuncio.get("foto"), copia,
                                                            anuncio.get("nome", ""), avisos=alcool,
                                                            outras_fotos=trocam, rotulo_de_ia=rotulo_de_ia,
                                                            anotar=edicao)
    # Com o Editor 1 o vídeo vai, mas conta como falha: o checkup mostra por que o Editor 2 não saiu.
    so_com_o_editor_1 = como.startswith(edicao_video.SO_COM_O_EDITOR_1)
    registro_processos.registrar(REGISTRO, PROCESSO_DA_EDICAO, "vídeo de lado" if motivo else como,
                                 motivo or detalhe, ok=not motivo and not so_com_o_editor_1)
    if motivo:
        raise Parada(f"{MOTIVO_SEM_EDICAO} ({motivo})", do_video=motivo.startswith("a foto do anúncio"))
    if miniatura is not None and anuncio.get("foto") and edicao_video.SEM_A_MINIATURA not in como:
        miniatura["fotos"] = [anuncio["foto"]] + list(trocam)
    if edicao is not None and not video.get("de_video"):
        # O que o Editar ✏️ do rascunho precisa (P192 1); o de Ver Produtos fica sem ele (pode_editar).
        edicao["guardado"] = guardar_para_o_editar(copia, video["arquivo"], anuncio.get("foto"), trocam,
                                                   edicao.get("refazer"))
    return como


# --- Editar ✏️ (P191 1 e P192 1) ---
# Em Rascunhos do Robô 📝, o Editar ✏️ muda a miniatura (à direita, à esquerda ou sem) e a legenda da fala
# (com ou sem) de um rascunho: o servidor refaz a edição do vídeo original com as escolhas da IA guardadas no
# rascunho, sem o celular, e manda a nova versão ao Rafael. Com o Aprovar ✅, o robô refaz o rascunho no app
# com ela (o app não deixa trocar o vídeo de um rascunho: o vídeo, os produtos e o título vão de novo), e a
# versão de antes só sai do app depois de o novo ficar salvo. Escolhas do Rafael (10/11, P191 1 e P192 1):
# DECISOES.md, Shopee Vídeo.
PROCESSO_DO_EDITAR = "editar o rascunho"
PROCESSO_DO_REFAZER = "refazer o rascunho editado"
SEM_O_QUE_EDITAR = "este rascunho não guardou o que a edição precisa (é de antes do Editar ✏️ ou de Ver Produtos)"


def guardar_para_o_editar(copia, original, foto, outras, refazer):
    """
    O que o Editar ✏️ do rascunho precisa para refazer a edição sem a IA, ao lado do vídeo do rascunho (copia,
    {id}.mp4): o vídeo original ({id}_original.mp4; uma ligação no disco quando dá, para não ocupar o dobro), a
    foto do anúncio ({id}_foto.jpg) e as fotos da miniatura que troca ({id}_outra_{n}.jpg), com o que o
    edicao_video.editar_para_postar guardou (refazer). Devolve o que vai à coluna edicao, ou {} quando algo
    falta: o rascunho fica sem o Editar ✏️, nunca deixa de sair.
    """
    if not refazer or not foto or not original or not os.path.exists(original):
        return {}
    base = os.path.splitext(copia)[0]
    try:
        guardado = base + "_original.mp4"
        if os.path.exists(guardado):
            os.remove(guardado)
        try:
            os.link(original, guardado)
        except OSError:
            shutil.copyfile(original, guardado)
        caminho_da_foto = f"{base}_foto.{ps.extensao_da_foto(foto) or 'jpg'}"
        with open(caminho_da_foto, "wb") as arquivo:
            arquivo.write(foto)
        caminhos = []
        for n, outra in enumerate(outras or (), 1):
            caminho = f"{base}_outra_{n}.{ps.extensao_da_foto(outra) or 'jpg'}"
            with open(caminho, "wb") as arquivo:
                arquivo.write(outra)
            caminhos.append(caminho)
    except OSError as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] O que o Editar precisa não foi guardado: {type(e).__name__}")
        registro_processos.registrar(REGISTRO, PROCESSO_DO_EDITAR, "sem o Editar",
                                     f"os arquivos não foram guardados ({type(e).__name__})", ok=False)
        return {}
    return dict(refazer, original=guardado, foto=caminho_da_foto, outras=caminhos, versoes=1)


def pode_editar(rascunho):
    """
    O rascunho que espera a aprovação deixa o Editar ✏️? Com o que a edição precisa guardado e, no vídeo de link
    de produto, o link de cada produto anexado (o robô curte cada um de novo para refazer o rascunho no app). A
    versão de antes de um rascunho refeito não.
    """
    guardado = (rascunho or {}).get("edicao") or {}
    nomes = (rascunho or {}).get("produtos") or []
    return bool(rascunho and rascunho.get("estado") == "rascunho" and not rascunho.get("versao_de")
                and guardado.get("original") and os.path.exists(guardado["original"])
                and guardado.get("foto") and os.path.exists(guardado["foto"])
                and nomes and not rascunho.get("links_dos_produtos") and rascunho.get("link")
                and len(rascunho.get("mais_produtos") or []) + 1 == len(nomes))


def sem_a_fala(rascunho):
    """
    Por que o Editar ✏️ não tem a legenda da fala para pôr ou tirar no vídeo do rascunho (o porquê fixo de
    edicao_video.legendas_da_fala: ninguém fala em português, a fala já escrita na tela, a IA sem as
    legendas), ou "" quando tem: o servidor refaz o vídeo com o que a IA escreveu, e sem a fala dela, com ou
    sem a legenda, o vídeo fica igual.
    """
    return edicao_video.legendas_da_fala(((rascunho or {}).get("edicao") or {}).get("textos") or {})[1]


def escolhas_do_rascunho(rascunho):
    """O lado da miniatura e a legenda da fala do vídeo do rascunho: os da nova versão ou os da edição."""
    nova = (rascunho or {}).get("nova_versao") or {}
    if nova.get("arquivo"):
        return nova.get("miniatura") or edicao_video.MINIATURA_A_DIREITA, bool(nova.get("legenda"))
    escolhas = edicao_video.escolhas_certas(((rascunho or {}).get("edicao") or {}).get("escolhas"))
    return escolhas["miniatura"], escolhas["legenda"]


def reeditar(ident, lado, legenda, agora=None):
    """
    O Editar ✏️ no servidor, sem o celular: a edição do vídeo original refeita com o lado da miniatura (lado) e
    a legenda da fala (legenda) pedidos, numa nova versão ({id}_nova_{n}.mp4), que espera o Aprovar ✅ do Rafael
    (nova_versao). Devolve (ok, o jeito ou o motivo).
    """
    rascunho = pegar(ident)
    if not rascunho or rascunho["estado"] != "rascunho":
        return False, "o rascunho não espera mais a sua aprovação"
    if not pode_editar(rascunho):
        return False, SEM_O_QUE_EDITAR
    guardado = rascunho["edicao"]
    versao = int(guardado.get("versoes") or 1) + 1
    destino = os.path.join(PASTA_RASCUNHOS, f"{ident}_nova_{versao}.mp4")
    try:
        with open(guardado["foto"], "rb") as arquivo:
            foto = arquivo.read()
        outras = []
        for caminho in guardado.get("outras") or []:
            with open(caminho, "rb") as arquivo:
                outras.append(arquivo.read())
        motivo, como = edicao_video.refazer_para_postar(guardado["original"], foto, destino, guardado, outras, lado,
                                                        legenda)
    except Exception as e:
        motivo, como = f"erro ({type(e).__name__})", ""
    registro_processos.registrar(REGISTRO, PROCESSO_DO_EDITAR, "não saiu" if motivo else "nova versão",
                                 motivo or f"miniatura: {lado}; legenda: {'com' if legenda else 'sem'}",
                                 ok=not motivo, agora=agora)
    if motivo:
        return False, motivo
    atualizar(ident, nova_versao={"arquivo": destino, "versao": versao, "miniatura": lado, "legenda": bool(legenda),
                                  "como": como, "feita_em": _momento(agora)})
    return True, como


def manter_a_versao_de_antes(ident):
    """O Rafael fica com o vídeo de antes do Editar ✏️: a nova versão sai, e o rascunho volta a ser o de antes."""
    rascunho = pegar(ident)
    arquivo = ((rascunho or {}).get("nova_versao") or {}).get("arquivo")
    if arquivo and os.path.exists(arquivo):
        os.remove(arquivo)
    if rascunho:
        atualizar(ident, nova_versao={})


def fotos_da_miniatura(video, foto, outras):
    """
    As outras fotos da miniatura que troca (bytes), depois da foto do 1º produto (foto): as fotos
    de capa dos outros produtos do post (outras, na ordem do post) diferentes dela e entre si, pela
    comparação da imagem (mesma_foto; a que não abre fica de fora), só as que cabem no vídeo com
    pelo menos edicao_video.MINIMO_POR_FOTO segundos cada: ficam as primeiras, as que pagam mais
    por venda. [] é a miniatura de uma foto só. O registro anota quantas e o tempo de cada; um
    erro aqui nunca derruba o rascunho. Escolha do Rafael (30/10, P103): DECISOES.md, Shopee Vídeo.
    """
    try:
        diferentes = [foto]
        for outra in outras:
            if all(mesma_foto(outra, ja) is False for ja in diferentes):
                diferentes.append(outra)
        duracao = videos.duracao(video["arquivo"]) if len(diferentes) > 1 else 0.0
        cabem = edicao_video.fotos_que_cabem(duracao, len(diferentes))
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] A escolha das fotos da miniatura deu erro: {type(e).__name__}")
        registro_processos.registrar(REGISTRO, PROCESSO_DA_MINIATURA, "uma só", f"erro ({type(e).__name__})",
                                     ok=False)
        return []
    if len(diferentes) < 2:
        resultado, detalhe = "uma só", "nenhuma foto diferente da do 1º produto"
    elif not duracao:
        resultado, detalhe = "uma só", "a duração do vídeo não foi lida"
    elif cabem < 2:
        resultado, detalhe = "uma só", f"o vídeo é curto para trocar ({duracao:.0f} s)"
    else:
        resultado = "alternada"
        detalhe = (f"{cabem} fotos" + (f" de {len(diferentes)} diferentes" if cabem < len(diferentes) else "")
                   + f", {duracao / cabem:.1f}".replace(".", ",") + " s cada")
    registro_processos.registrar(REGISTRO, PROCESSO_DA_MINIATURA, resultado, detalhe,
                                 ok=True if resultado == "alternada" else None)
    return diferentes[1:cabem]


# O de outra cor (o mesmo modelo em outra cor ou estampa) só vai no post com a foto dele na
# miniatura que troca: é ela que o mostra no vídeo, e sem isso a Shopee pode dar o produto como
# irrelevante. Sem a nossa miniatura (o canto do criador, P81, ou a edição desligada) ou sem tempo
# para a foto dele na troca (P103), ele sai antes de anexar. Vale nos produtos a mais e no Ver
# Produtos. Pedidos do Rafael (01/11 e 02/11): DECISOES.md, Shopee Vídeo.
PROCESSO_DA_OUTRA_COR = "outra cor: foto na miniatura"
# O mesmo modelo em outra cor, nos produtos a mais e no Ver Produtos: desligado. Um post com o
# produto do vídeo e 2 do mesmo modelo em outra cor foi punido como Produto Irrelevante (a página
# da Política de Relevância de Produto diz que outra cor deixa o produto "fraco", mas a punição
# veio). Volta a True só quando a Shopee liberar outra cor por escrito. Escolha do Rafael (03/11,
# P142 1): DECISOES.md, Shopee Vídeo.
OUTRA_COR_NOS_PRODUTOS = False
MOTIVO_DA_OUTRA_COR_DESLIGADA = "outra cor desligada (P142)"


def na_miniatura(foto, fotos_da_miniatura):
    """A foto (bytes) aparece na miniatura que troca: ela mesma ou uma igual (mesma_foto)."""
    return bool(foto) and any(foto == ja or mesma_foto(foto, ja) is True for ja in fotos_da_miniatura)


def com_a_foto_na_miniatura(itens, fotos_da_miniatura):
    """
    Os itens que vão ao post, na ordem: itens = [(item, foto, de_outra_cor)] na ordem do post e
    fotos_da_miniatura, as fotos da miniatura que troca no vídeo ([] sem a nossa miniatura). O
    1º e os da mesma cor ficam sempre; o de outra cor, só com a foto aparecendo na miniatura. O
    registro anota cada um de outra cor.
    """
    ficam = []
    for posicao, (item, foto, de_outra_cor) in enumerate(itens):
        if not de_outra_cor or posicao == 0:
            ficam.append(item)
        elif na_miniatura(foto, fotos_da_miniatura):
            registro_processos.registrar(REGISTRO, PROCESSO_DA_OUTRA_COR, "no post", "a foto na miniatura", ok=True)
            ficam.append(item)
        else:
            motivo = "sem a nossa miniatura" if not fotos_da_miniatura else "a foto não coube na miniatura"
            registro_processos.registrar(REGISTRO, PROCESSO_DA_OUTRA_COR, "de fora", motivo)
    return ficam


def _oferta_parecida(nome):
    """
    (quanto o nome parece, se é o mesmo nome, a oferta) da busca pelo nome na API, por
    relevância: a de nome igual (ou cortado, ps.nome_na_pagina), senão a de nome mais
    parecido; no empate, a mais relevante. (0, False, {}) sem nenhuma.
    """
    ofertas = asyncio.run(api_shopee.buscar_ofertas_shopee(termo_da_busca(nome), limite=OFERTAS_NA_BUSCA,
                                                           sort_type=1))
    notas = [(ps.nome_na_pagina(oferta.get("productName") or "", nome),
              ps.parecido_entre([oferta.get("productName") or ""], nome)[0], -i) for i, oferta in enumerate(ofertas)]
    exato, parecido, melhor = max(notas, default=(False, 0, None))
    return (parecido, exato, ofertas[-melhor]) if melhor is not None else (0, False, {})


def oferta_pelo_nome(nome):
    """
    A oferta da API de afiliado de um produto anexado num vídeo de Ver Produtos (o link é do
    vídeo, não do produto): a busca pelo nome, por relevância, e vale a de nome mais
    parecido, com pelo menos PARECIDO_DA_FOTO% das palavras. {} quando não acha.
    """
    parecido, _exato, oferta = _oferta_parecida(nome)
    return oferta if oferta and parecido >= PARECIDO_DA_FOTO else {}


# O que a busca pelo nome achou para os produtos do Ver Produtos: com o nome igual ao do app,
# parecido ou nada. Antes de a miniatura do Ver Produtos trocar entre as fotos de todos, o
# Claude confere por estes números se a busca acerta o anúncio de cada produto e pergunta de
# novo ao Rafael. Escolha dele (30/10, P105): DECISOES.md, Shopee Vídeo.
PROCESSO_DOS_LINKS_DO_VER_PRODUTOS = "ver produtos: links pelo nome"


def links_do_ver_produtos(nomes, ja_sabidos=()):
    """
    O link de cada produto anexado num vídeo de Ver Produtos, na ordem do post, para o Rafael
    conferir no rascunho, produto por produto: a oferta achada na API pelo nome (a mesma busca
    dos links do Canal Afiliados), em link curto com a etiqueta da Shopee Vídeo, como o dos
    produtos a mais; "" no que a API não acha. ja_sabidos (na ordem de nomes): o link curto do
    produto trocado pelo da loja que paga mais (P57), que vale como veio, sem a busca. Dois
    produtos de nome quase igual que caem no mesmo anúncio: o link fica com o de nome igual ao do
    anúncio (senão, o mais parecido) e o outro fica sem, para nunca mostrar o link de um produto
    no lugar do de outro. O registro conta quantos links vieram com o nome igual ao do app, com o
    nome parecido, da troca e quantos ficaram sem (P105). Pedido do Rafael (29/10, P83):
    DECISOES.md, Shopee Vídeo.
    """
    ja_sabidos = (list(ja_sabidos) + [""] * len(nomes))[:len(nomes)]
    achados = []
    for nome, sabido in zip(nomes, ja_sabidos):
        if sabido:
            achados.append((0, False, {}))
            continue
        try:
            parecido, exato, oferta = _oferta_parecida(nome)
        except Exception as e:
            logger.warning(f"⚠️ [Robô Shopee Vídeo] O link do produto do Ver Produtos não veio: {type(e).__name__}")
            parecido, exato, oferta = 0, False, {}
        achados.append((parecido, exato, oferta if parecido >= PARECIDO_DA_FOTO else {}))
    links, usados = list(ja_sabidos), set()
    for i in sorted(range(len(achados)), key=lambda i: (not achados[i][1], -achados[i][0])):
        oferta = achados[i][2]
        item, endereco = str(oferta.get("itemId") or ""), oferta.get("productLink") or ""
        if not endereco or (item and item in usados):
            continue
        usados.add(item)
        try:
            links[i] = asyncio.run(api_shopee.converter_link_shopee(endereco, api_shopee.ETIQUETA_SHOPEE_VIDEO,
                                                                   avisar_falha=False)) or endereco
        except Exception:
            links[i] = endereco
    pela_busca = [(link, achado) for link, achado, sabido in zip(links, achados, ja_sabidos) if not sabido]
    iguais = sum(1 for link, (_, exato, _o) in pela_busca if link and exato)
    parecidos = sum(1 for link, (_, exato, _o) in pela_busca if link and not exato)
    da_troca = len(links) - len(pela_busca)
    sem = len(pela_busca) - iguais - parecidos
    if links:
        registro_processos.registrar(REGISTRO, PROCESSO_DOS_LINKS_DO_VER_PRODUTOS,
                                     "todos achados" if not sem else "nenhum achado" if sem == len(links)
                                     else "achados em parte",
                                     f"{iguais} com o nome igual, {parecidos} com o nome parecido, {sem} sem"
                                     + (f", {da_troca} da troca de loja" if da_troca else ""),
                                     ok=True if not sem else None)
    return links


# O que a busca pelo nome deu para a foto do 1º produto do Ver Produtos: sem a foto, o vídeo
# fica de lado, e o registro diz por quê (nenhuma oferta na busca, o nome pouco parecido, com a
# porcentagem, ou a foto que não baixou), só com rótulos e números.
PROCESSO_DA_FOTO_DO_VER_PRODUTOS = "ver produtos: foto pelo nome"


def anuncio_do_ver_produtos(nome):
    """
    {"foto", "nome"} do anúncio do 1º produto anexado num vídeo de Ver Produtos, achado
    pelo nome (a oferta de nome mais parecido, com pelo menos PARECIDO_DA_FOTO% das palavras,
    como em oferta_pelo_nome). {} quando não acha, e foto None quando ela não baixa: o vídeo
    fica de lado (só vídeo editado vai). A IA já conferiu esse produto com o vídeo, e o nome
    fica o do app (o que ela conferiu).
    Escolha do Rafael (25/10, P39): DECISOES.md, Shopee Vídeo.
    """
    try:
        parecido, _exato, oferta = _oferta_parecida(nome)
        if not oferta or parecido < PARECIDO_DA_FOTO:
            registro_processos.registrar(REGISTRO, PROCESSO_DA_FOTO_DO_VER_PRODUTOS,
                                         "nome pouco parecido" if oferta else "nenhuma oferta na busca",
                                         f"{parecido}% das palavras" if oferta else "", ok=False)
            return {}
        foto = ps.baixar_foto(oferta.get("imageUrl") or "")
        registro_processos.registrar(REGISTRO, PROCESSO_DA_FOTO_DO_VER_PRODUTOS,
                                     "achada" if foto else "a foto não baixou", f"{parecido}% das palavras",
                                     ok=bool(foto))
        return {"foto": foto, "nome": nome}
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] A foto do produto do Ver Produtos não veio: {type(e).__name__}")
        registro_processos.registrar(REGISTRO, PROCESSO_DA_FOTO_DO_VER_PRODUTOS, "a busca falhou",
                                     type(e).__name__, ok=False)
        return {}


def _esperar_a_pagina_do_produto(d, voltas=4, a_mais=False):
    """
    Espera a página do produto abrir (uns 12 s), olhando a cada volta o aviso de loja de
    férias, que some em segundos. Produto de loja de férias não entra no Adicionar Produto
    do vídeo, mesmo curtido (24/10/2026, o teclado curtido às 14:25 não estava na lista):
    o vídeo fica de lado na hora, antes da galeria e do título. O produto a mais (a_mais=True,
    P59) só fica de fora: devolve False. Página sem o aviso: True.
    """
    for _ in range(voltas):
        pausa(2)
        if ps.loja_de_ferias(d, tela(d)):
            registro_processos.registrar(REGISTRO, "produto de loja de férias",
                                         "produto a mais de fora" if a_mais else "vídeo pulado", ok=None)
            if a_mais:
                return False
            raise Parada(MOTIVO_DE_FERIAS, do_video=True)
    return True


PROCESSO_DO_CRIADOR = "ver produtos: conferência pela foto"
# Os produtos que o criador esconde no "Ver Mais (N)" da lista do Ver Produtos entram como os
# outros (P66): o robô toca no botão e lê os cartões que aparecem, arrastando a lista devagar
# até o "Esconder". Em cada procura do próximo cartão, até VEZES_DO_VER_MAIS toques no botão (a
# lista pode voltar fechada da página do produto) e ROLAGENS_DO_VER_PRODUTOS arrastos. O registro
# conta, só em números, quantos cartões o robô abriu, quantos o botão escondia e os toques e
# arrastos. Escolha do Rafael (28/10, P66): DECISOES.md, Shopee Vídeo.
PROCESSO_DO_VER_MAIS = "ver produtos: ver mais"
VEZES_DO_VER_MAIS = 2
ROLAGENS_DO_VER_PRODUTOS = 6
# O produto curtido pela lista do Ver Produtos, pelo nome do cartão dele na lista: o descurtir do
# fim (descurtir_no_fim) o acha de novo nela. O curtido pelo link guarda o link.
NoVerProdutos = namedtuple("NoVerProdutos", "cartao")


def _achar_cartao(d, procurado, conhecidos, andamento=None):
    """
    O 1º cartão do criador na lista do Ver Produtos cujo nome procurado(nome) aceita (o próximo
    que o robô ainda não abriu, ou o de um produto curtido): (o nome do cartão, onde tocar, a
    tela), ou None quando a lista acabou. Sem ele na tela, toca no "Ver Mais (N)" (os outros
    abrem na mesma lista) e, sem o botão, arrasta a lista devagar, nunca passando do "Esconder"
    nem do "Você Também Pode Gostar" (as recomendações, que não são do vídeo). Sem nada
    conhecido da lista na tela (o título, o Ver Mais, o fim da lista do criador ou um cartão de
    conhecidos, os nomes já vistos nela), os cartões podem ser recomendações: o robô não toca
    nem arrasta, e a lista acabou para ele. andamento (dict) soma os toques no Ver Mais, os
    arrastos e quantos o botão escondia.
    """
    andamento = {} if andamento is None else andamento
    toques = rolagens = 0
    while True:
        xml = tela(d)
        cartoes = ps.cartoes_vinculados(xml)
        if not ps.lista_do_criador_na_tela(xml) and not any(cartao in conhecidos for cartao, _ in cartoes):
            andamento["sem_referencia"] = True
            return None
        for cartao, ponto in cartoes:
            if procurado(cartao):
                return cartao, ponto, xml
        ver_mais = ps.ver_mais_da_lista(xml)
        if ver_mais and toques < VEZES_DO_VER_MAIS:
            if ps.proibido_no_ponto(xml, *ver_mais):
                raise Parada(ps.RECUSA)
            andamento["escondidos"] = max(andamento.get("escondidos", 0), ps.quantos_no_ver_mais(xml))
            ps.limpar_aviso_rapido(d)
            d.click(*ver_mais)
            pausa(4)
            toques += 1
            andamento["ver_mais"] = andamento.get("ver_mais", 0) + 1
            continue
        if ps.fim_da_lista_do_criador(xml) or rolagens >= ROLAGENS_DO_VER_PRODUTOS:
            return None
        ps.rolar_a_lista_devagar(d)
        pausa(3)
        rolagens += 1
        andamento["rolagens"] = andamento.get("rolagens", 0) + 1


def _anotar_o_ver_mais(lidos, andamento):
    """A linha do registro do Ver Mais (PROCESSO_DO_VER_MAIS), só quando a lista tinha o botão ou se perdeu."""
    if not andamento.get("ver_mais") and not andamento.get("sem_referencia"):
        return
    registro_processos.registrar(
        REGISTRO, PROCESSO_DO_VER_MAIS,
        "parou - a lista sem nada conhecido na tela" if andamento.get("sem_referencia") else "lidos",
        f"{len(lidos)} cartão(ões) aberto(s); o Ver Mais escondia {andamento.get('escondidos', 0)}, tocado "
        f"{andamento.get('ver_mais', 0)} vez(es); {andamento.get('rolagens', 0)} arrasto(s)",
        ok=None if andamento.get("sem_referencia") else True)


def _produtos_do_video(d, video, vistos, curtidos=None, variacoes=None, fotos=None):
    """
    Link de vídeo (Ver Produtos): abre o vídeo no celular e, na lista do Ver Produtos (pelo
    "Ver Produtos (N)" ou, com um produto só, pela barra dele), cada produto que o criador
    vinculou, também os do Ver Mais (P66; nunca as recomendações de "Você Também Pode Gostar"),
    até MAXIMO_PRODUTOS_DO_VIDEO: lê o nome na página dele, a IA compara a foto da página com o
    vídeo VEZES_DA_IA vezes, e o confirmado é curtido (curtidos recebe (NoVerProdutos, nome)). O
    mesmo modelo em outra cor ou estampa entra também, e variacoes (lista) recebe (nome, foto)
    dele: a foto vai na miniatura que troca. fotos (dict) recebe a foto da página de cada
    confirmado, para a troca pela loja que paga mais (P57). Devolve os nomes confirmados, os da
    mesma cor primeiro (o 1º dá a foto da edição); nenhum ou vídeo removido: o vídeo fica de lado.
    Decisões do Rafael (23/10; 28/10, P66; 01/11, a outra cor): DECISOES.md, Shopee Vídeo.
    """
    _abrir_ver_produtos(d, video)
    confirmados, de_ferias, de_outra_cor, lidos, andamento = [], 0, [], [], {}
    for _ in range(MAXIMO_PRODUTOS_DO_VIDEO):
        achado = _achar_cartao(d, lambda cartao: cartao not in lidos, lidos, andamento)
        if not achado:
            break
        cartao, ponto, xml = achado
        lidos.append(cartao)
        if ps.proibido_no_ponto(xml, *ponto):
            raise Parada(ps.RECUSA)
        ps.limpar_aviso_rapido(d)
        d.click(*ponto)
        pausa(8)
        xml = tela(d)
        nome = ps.nome_na_pagina_do_produto(xml)
        if ps.loja_de_ferias(d, xml):
            # Não entra no Adicionar Produto do vídeo: fica de fora, como o recusado pela IA.
            registro_processos.registrar(REGISTRO, "produto de loja de férias", "produto do Ver Produtos de fora",
                                         ok=None)
            de_ferias += 1
        elif nome and nome not in confirmados:
            # A foto da página é o anúncio exato que a criadora vinculou: a IA vê o item e a cor,
            # que o nome muitas vezes não diz. Sem ela, o produto fica de fora.
            foto = ps.foto_da_pagina_do_produto(d, xml)
            deste = []
            ok, outra_cor, _ = ps.ia_confere_do_criador(video, nome, foto, deste) if foto else (False, False, "")
            # O mesmo modelo em outra cor fica de fora, como outro produto (P142 1).
            fora_pela_cor = ok and outra_cor and not OUTRA_COR_NOS_PRODUTOS
            registro_processos.registrar(
                REGISTRO, PROCESSO_DO_CRIADOR,
                "de fora - sem a foto da página" if not foto else "de fora - outro produto" if not ok
                else "de fora - outra cor" if fora_pela_cor
                else "outra cor - a foto vai na miniatura" if outra_cor else "mesmo produto",
                ok=True if ok and not fora_pela_cor else None)
            if ok and not fora_pela_cor:
                _conferir_curtida(ps.curtir_na_pagina(d, xml))
                if curtidos is not None:
                    curtidos.append((NoVerProdutos(cartao), nome))
                confirmados.append(nome)
                vistos.extend(deste)
                if fotos is not None:
                    fotos[nome] = foto
                if outra_cor:
                    de_outra_cor.append(nome)
                    if variacoes is not None:
                        variacoes.append((nome, foto))
        d.press("back")
        pausa(4)
    _anotar_o_ver_mais(lidos, andamento)
    if not confirmados:
        raise Parada(MOTIVO_DE_FERIAS if de_ferias else "a IA não confirmou nenhum produto do Ver Produtos",
                     do_video=True)
    # Os da mesma cor do vídeo primeiro: o 1º anexado dá a foto do começo e da miniatura (P39).
    return [n for n in confirmados if n not in de_outra_cor] + [n for n in confirmados if n in de_outra_cor]


# O link de vídeo que abre o aviso "Vídeo em Análise" da Shopee: o vídeo do criador ainda não
# foi liberado ao público, e a tela não tem o Ver Produtos (Motorola, 02/11/2026).
MOTIVO_EM_ANALISE = "o vídeo do link está em análise na Shopee (ainda não é público)"


def _abrir_ver_produtos(d, video):
    """
    Abre o vídeo do link e a lista do Ver Produtos (pelo "Ver Produtos (N)" ou, com um
    produto só, pela barra dele). Devolve quantos produtos o criador vinculou.
    """
    ir_ao_inicio(d)
    ps.abrir_link(d, video["link"])
    pausa(12)
    xml = tela(d)
    if not ps.video_removido(xml) and not ps.video_em_analise(xml) and not tem(xml, "Ver Produtos"):
        pausa(ESPERA_DO_VER_PRODUTOS)
        xml = tela(d)
    if ps.video_removido(xml):
        raise Parada("o vídeo do link foi removido", do_video=True)
    if ps.video_em_analise(xml):
        raise Parada(MOTIVO_EM_ANALISE, do_video=True)
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


def nome_na_galeria(ident, versao=1):
    """O nome do vídeo do rascunho na galeria do celular; cada versão do Editar ✏️ tem o seu (P192 1)."""
    return f"robo_shopee_video_{ident}.mp4" if versao <= 1 else f"robo_shopee_video_{ident}_v{versao}.mp4"


# O vídeo, o print, as fotos de capa (P75) e as dos recusados de cada rascunho: {id}.mp4, {id}.png,
# {id}_capa_{n}.jpg e {id}_recusado_{n}.jpg; e o que o Editar ✏️ guarda (P192 1): o vídeo original
# ({id}_original.mp4), a foto do anúncio ({id}_foto.jpg), as fotos da miniatura que troca
# ({id}_outra_{n}.jpg) e cada versão refeita, com o print dela ({id}_nova_{n}.mp4 e .png).
ARQUIVO_NO_SERVIDOR = re.compile(r"^(\d+)(?:_(?:capa|recusado|outra)_\d+\.(?:jpg|png|webp)|_foto\.(?:jpg|png|webp)"
                                 r"|_original\.mp4|_nova_\d+\.(?:mp4|png)|\.(?:mp4|png))$")


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
    no_app = sorted(listar(*NO_APP), key=lambda r: (r["no_app_em"] or r["criado_em"], r["id"]), reverse=True)
    return next(i for i, r in enumerate(no_app) if r["id"] == rascunho["id"])


def _forma_do_titulo(titulo):
    """O tamanho do título como o app conta (cada emoji de fora do plano básico vale 2) e quantos emojis desses."""
    return (f"o título tem {len(titulo.encode('utf-16-le')) // 2} no contador do app e "
            f"{sum(ord(c) > 0xFFFF for c in titulo)} emoji(s) de fora do plano básico")


def tirar_os_marcados(d, rascunho):
    """
    No rascunho reaberto para postar, tira da tela final os produtos que o Rafael marcou para
    sair do post (P123), do último para o primeiro (tirar um não muda a posição dos de antes
    dele), pelo X de cada um. O que não sai para o post sem tocar em mais nada: o aprovado tenta
    de novo (P99), e o app, sem salvar, volta a ter todos. Devolve quantos tirou.
    """
    marcados = sorted({n for n in rascunho.get("tirar") or [] if 1 <= n <= len(rascunho["produtos"])}, reverse=True)
    nomes = list(rascunho["produtos"])
    for posicao in marcados:
        ok, motivo = ps.tirar_da_fileira(d, nomes, posicao - 1)
        if not ok:
            registro_processos.registrar(REGISTRO, PROCESSO_DE_TIRAR, "de fora", motivo, ok=False)
            raise Parada(f"não consegui tirar o {posicao}º produto, que você marcou para sair do post: {motivo}")
        nomes.pop(posicao - 1)
    registro_processos.registrar(REGISTRO, PROCESSO_DE_TIRAR, "tirados",
                                 f"{len(marcados)} de {len(rascunho['produtos'])} produtos", ok=True)
    return len(marcados)


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
    Posta o rascunho aprovado, manda no privado o link do post e comenta no vídeo (P148 2). Antes,
    olha nas Notificações se a conta está suspensa: não se sabe o que o Postar faz com a
    conta suspensa, e o robô não marca como postado o que não foi ao ar. Os produtos que o
    Rafael marcou para sair do post saem antes de tudo (P123), e a tela final é conferida
    só com os que ficam.
    """
    ate = ler_suspensao(d, agora)
    if ate:
        raise Suspensa(ate)
    # O rascunho reaberto tem todos os produtos: o app só guarda o rascunho pelo Salvar, e a
    # volta da tela final do post que não saiu descarta o que o robô mudou nela.
    abrir_rascunho(d, rascunho)
    no_post = com_os_que_ficam(rascunho)
    if no_post is not rascunho:
        tirar_os_marcados(d, rascunho)
        _conferir(ps.conferir_tela_final(d, video_do_rascunho(no_post)), do_video=False)
    _conferir(ps.ajustar_rotulo_de_ia(d, bool(rascunho.get("rotulo_ia"))), do_video=False)
    _conferir(ps.postar(d, video_do_rascunho(no_post)), do_video=False)
    pausa(15)
    atualizar(rascunho["id"], estado="postado", postado_em=_momento(agora),
              **(campos_que_ficam(no_post) if no_post is not rascunho else {}))
    # O post anterior que ainda esperava o link deixa de ser o mais novo da grade: o robô não o
    # acharia mais sem confundir com este.
    for anterior in links_esperando(agora):
        if anterior["id"] != rascunho["id"]:
            desistir_do_link(anterior, "outro vídeo foi ao ar antes", agora)
    link = link_do_post(d, ident=rascunho["id"], agora=agora)
    if link:
        atualizar(rascunho["id"], link_post=link)
    else:
        atualizar(rascunho["id"], busca_do_link={"vezes": [_momento(agora)], "fim": ""})
    sairam = len(rascunho["produtos"]) - len(no_post["produtos"])
    avisar("✅ Robô da Shopee Vídeo: postei o vídeo que você aprovou"
           + (f", sem {'os produtos' if sairam > 1 else 'o produto'} que você marcou para sair "
              f"({sairam} de {len(rascunho['produtos'])})" if sairam else "")
           + ".\n\n" + (f"🔗 {link}" if link else AVISO_SEM_O_LINK_AGORA))
    if link:
        levar_ao_canal(no_post, link)
        comentar_depois_do_post(d, rascunho["id"], agora)
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


PROCESSO_DO_LINK_DO_POST = "link do post"


def link_do_post(d, ident=None, agora=None, titulo=None, busca=1):
    """
    O link do post que acabou de sair: Perfil em Shopee Vídeo → o vídeo mais novo → o
    ícone de compartilhar → Copiar link (mapeado no Motorola em 22/10/2026). Qualquer
    passo que não aparece: sem link (o post saiu do mesmo jeito, e o robô busca de novo nas
    rodadas seguintes, buscar_o_link_de_novo). Nada aqui desfaz a postagem: até a Verificação
    só abre a tela do celular no privado. Com o ident do rascunho, antes de abrir o vídeo
    guarda a marca da capa dele na grade (a medição da capa com chamada, P76). Com o titulo (a
    busca de novo, busca > 1), o vídeo aberto só vale com a legenda do post (legenda_do_post):
    outro vídeo pode ter ido ao ar depois. O registro diz em que passo o link não saiu (rótulos
    fixos), e o caso do que não saiu fica para o checkup do Claude: sem o link, o vídeo não vai ao
    Canal Afiliados nem ganha o comentário.
    """
    def sem_o_link(porque, caso=True):
        registro_processos.registrar(REGISTRO, PROCESSO_DO_LINK_DO_POST, "sem o link",
                                     f"{porque}{f' (na {busca}ª busca)' if busca > 1 else ''}", ok=False,
                                     agora=agora)
        if caso:
            try:
                _guardar_caso(d, "postar" if busca == 1 else "comentar_post", "sem o link",
                              f"link do post: {porque}", ident=ident, agora=agora)
            except Exception as e:
                logger.warning(f"⚠️ [Robô Shopee Vídeo] Caso do link do post não guardado: {type(e).__name__}")
        return ""

    try:
        ir_ao_perfil(d)
        # Na grade do Perfil vêm primeiro o quadro "Rascunhos: N" e os vídeos fixados; o
        # mais novo é o primeiro depois deles.
        quadros = [q for q in quadros_da_lista(tela(d))
                   if not any(tem_texto_no_quadro(d, q, texto) for texto in ("Rascunhos", "Fixado"))]
        if not quadros:
            return sem_o_link("nenhum vídeo na grade do Perfil")
        if ident and not titulo:
            marcar_o_post(d, ident, quadros[0]["caixa"])
        d.click(*ps._centro(quadros[0]))
        pausa(8)
        xml = tela(d)
        if titulo:
            video = interacoes.video_do_feed(xml)
            if not video:
                return sem_o_link("o vídeo mais novo da grade não abriu no player")
            if not legenda_do_post(video["legenda"], titulo):
                return sem_o_link("o vídeo mais novo da grade não é o do post")
        compartilhar = botao_de_compartilhar(xml)
        if not compartilhar:
            return sem_o_link(MOTIVO_DO_POST_EM_ANALISE if ps.video_em_analise(xml)
                              else "sem o botão de compartilhar no vídeo")
        d.click(*compartilhar)
        pausa(4)
        if not tem(tela(d), "Copiar link"):
            return sem_o_link("sem o Copiar link")
        tocar(d, "Copiar link", 3)
        link = ps.link_copiado(d)
        if not link:
            return sem_o_link("o Copiar link não deixou o link copiado")
        registro_processos.registrar(REGISTRO, PROCESSO_DO_LINK_DO_POST, "copiado",
                                     f"na {busca}ª busca" if busca > 1 else "", ok=True, agora=agora)
        return link
    except Verificacao:
        av.abrir_tela(celular=True, verificacao=True)
        return sem_o_link("verificação da Shopee", caso=False)
    except Parada as e:
        return sem_o_link(f"parou em {passo_do_motivo(e.motivo)}")
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Link do post não saiu: {type(e).__name__}")
        return sem_o_link(f"erro ({type(e).__name__})")


def tem_texto_no_quadro(d, quadro, texto):
    return any(ps._dentro(ps._centro(el), quadro["caixa"]) and texto.casefold() in el["texto"].casefold()
               for el in ps.elementos(d.dump_hierarchy()))


# --- As visualizações dos vídeos na grade do Perfil (a medição da capa com chamada) ---
# Escolha do Rafael (29/10, P76): depois de 7 dias com a capa com chamada, o Claude compara as
# visualizações dos vídeos com a chamada com as dos de antes. A grade do Perfil em Shopee Vídeo
# mostra o número embaixo de cada vídeo ("123", "1,2 mil"), mas não diz qual vídeo é qual: no
# post, o robô guarda a marca da capa do vídeo novo (visualizacoes_shopee_video), e uma vez por
# dia, depois da Saúde do Vídeo, acha na grade cada vídeo dele dos últimos
# DIAS_DAS_VISUALIZACOES dias pela marca e anota o número. DECISOES.md, Shopee Vídeo.
DIAS_DAS_VISUALIZACOES = 8
# Os vídeos comparados no painel e no checkup: os postados nestes últimos dias.
DIAS_DA_COMPARACAO = 21
LEITURAS_POR_VIDEO = 12
ROLADAS_DA_GRADE = 6
# A capa do vídeo novo pode demorar a carregar na grade: até tantas tentativas, com a pausa entre elas.
TENTATIVAS_DA_MARCA, PAUSA_DA_MARCA = 3, 4
# Quadro cortado pela beirada da tela (mais baixo que isto do mais alto) fica para a próxima rolada.
QUADRO_INTEIRO = 0.9
PROCESSO_DAS_VISUALIZACOES = "visualizações na grade do perfil"
# Nenhum vídeo do robô casou com a grade (00:39 de 09/11: 0 de 36, com 31 de 32 na véspera): o
# registro diz o que a grade mostrou (os quadros, os com o número, os com a capa carregada e a
# marca mais perto) e o caso guarda a tela, para achar a causa.
MOTIVO_DAS_VISUALIZACOES = "as capas dos posts não casaram com a grade do Perfil"
# O 1º quadro do vídeo vai com a capa da grade, e o resto da abertura com a do vídeo aberto
# (P129): na grade do post, a faixa da frase de um lado ao outro do quadro diz que o app
# usou o 1º quadro; a faixa só no meio, que pegou outro quadro da abertura (aí a grade mostra a
# do vídeo aberto, mais estreita).
LADOS_DA_CAPA = {True: "o 1º quadro na grade (a faixa de lado a lado)",
                 False: "outro quadro na grade (a faixa só no meio)"}
COR_NA_CAPA = "na cor do produto"


def marcar_o_post(d, ident, caixa):
    """
    Guarda no rascunho a marca da capa do vídeo que acabou de ir ao ar (o quadro da grade em
    caixa). Sem a marca (a capa não carregou, o print falhou), o vídeo fica fora da medição, e o
    checkup conta. Com a capa com a frase (P125), o registro diz se a faixa da frase chegou à grade
    e se a grade pegou o 1º quadro do vídeo (P129). Nada aqui segura o post nem o link.
    """
    try:
        for tentativa in range(TENTATIVAS_DA_MARCA):
            if tentativa:
                pausa(PAUSA_DA_MARCA)
            imagem = d.screenshot()
            marca = visualizacoes.marca_da_capa(imagem, caixa)
            if marca:
                atualizar(ident, marca=marca)
                rascunho = pegar(ident) or {}
                if rascunho.get("chamada"):
                    # A faixa vai na cor que a edição usou: a do produto (P159 2) ou a do lugar dela (P173, P174 3).
                    cor = edicao_video.cor_guardada(rascunho.get("cor"))
                    faixa = faixa_da_capa(imagem, caixa, cor)
                    lados = edicao_video.faixa_nos_lados(imagem, caixa, cor) if faixa else None
                    # O registro diz também se a faixa procurada era a da cor do produto ou a de
                    # sempre: o checkup separa a 1ª capa colorida que chega à grade.
                    detalhe = "; ".join(filter(None, (LADOS_DA_CAPA.get(lados, ""),
                                                      COR_NA_CAPA if cor else "")))
                    registro_processos.registrar(REGISTRO, PROCESSO_DA_CAPA,
                                                 "no post com a faixa" if faixa else "no post sem a faixa",
                                                 detalhe, ok=bool(faixa))
                return marca
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] A marca da capa do post não saiu: {type(e).__name__}")
    return None


def quadros_da_grade(xml):
    """
    Os vídeos da grade do Perfil que estão inteiros na tela, na ordem dela, sem o quadro
    "Rascunhos: N": [{"caixa", "fixado", "vistas"}], vistas o número embaixo do quadro (None
    quando ele não aparece).
    """
    textos = [el for el in (ps.elementos(xml) if xml else []) if el["texto"].strip()]
    quadros = []
    for quadro in quadros_da_lista(xml):
        dentro = [el for el in textos if ps._dentro(ps._centro(el), quadro["caixa"])]
        if any(ps._normal(el["texto"]).startswith("rascunhos") for el in dentro):
            continue
        numeros = [interacoes.contagem(el["texto"]) for el in dentro if ps._normal(el["texto"]) != "fixado"]
        numeros = [n for n in numeros if n is not None]
        quadros.append({"caixa": quadro["caixa"], "fixado": any(ps._normal(el["texto"]) == "fixado" for el in dentro),
                        "vistas": numeros[-1] if numeros else None})
    altura = max((q["caixa"][3] - q["caixa"][1] for q in quadros), default=0)
    return [q for q in quadros if q["caixa"][3] - q["caixa"][1] >= altura * QUADRO_INTEIRO]


def anotar_visualizacoes(d, agora=None):
    """
    No Perfil, acha na grade, pela marca, cada vídeo que o robô postou nos últimos
    DIAS_DAS_VISUALIZACOES dias e anota as visualizações dele no rascunho (vistas). Rola a
    grade até ROLADAS_DA_GRADE vezes, até achar todos ou chegar ao fim. Devolve (achados,
    procurados).
    """
    limite = _momento(agora_br(agora) - timedelta(days=DIAS_DAS_VISUALIZACOES))
    procurados = sorted((r for r in listar("postado") if r.get("marca") and (r["postado_em"] or "") >= limite),
                        key=lambda r: (r["postado_em"], r["id"]), reverse=True)
    if not procurados:
        return 0, 0
    ir_ao_perfil(d)
    achados, vistos, anterior = {}, set(), None
    for rolada in range(ROLADAS_DA_GRADE + 1):
        if rolada:
            ps.rolar(d)
            pausa(4)
        caixas = quadros_da_grade(tela(d))
        # Sem nenhuma capa carregada na tela (os quadros ainda cinza), espera e tira o print de
        # novo, como no post (marcar_o_post).
        for tentativa in range(TENTATIVAS_DA_MARCA):
            if tentativa:
                pausa(PAUSA_DA_MARCA)
            imagem = d.screenshot()
            quadros = [(visualizacoes.marca_da_capa(imagem, q["caixa"]), q["vistas"]) for q in caixas]
            if not quadros or any(marca for marca, _vistas in quadros):
                break
        # O quadro que já apareceu antes da rolada não conta de novo.
        novos = [q for q in quadros if q not in vistos]
        vistos.update(quadros)
        faltam = [(r["id"], r["marca"]) for r in procurados if r["id"] not in achados]
        achados.update(visualizacoes.casar(novos, faltam))
        if len(achados) == len(procurados) or quadros == anterior:
            break
        anterior = quadros
    momento = _momento(agora)
    for rascunho in procurados:
        if rascunho["id"] in achados:
            leituras = (rascunho.get("vistas") or []) + [[momento, achados[rascunho["id"]]]]
            atualizar(rascunho["id"], vistas=leituras[-LEITURAS_POR_VIDEO:])
    detalhe = f"{len(achados)} de {len(procurados)} vídeo(s)"
    if not achados:
        detalhe += _o_que_a_grade_mostrou(vistos, procurados)
        _guardar_caso(d, "visualizacoes", "nenhum achado", MOTIVO_DAS_VISUALIZACOES, agora=agora)
    registro_processos.registrar(REGISTRO, PROCESSO_DAS_VISUALIZACOES, "lidas", detalhe, ok=bool(achados))
    return len(achados), len(procurados)


def _o_que_a_grade_mostrou(vistos, procurados):
    """
    Para o registro da leitura que não achou nenhum vídeo (MOTIVO_DAS_VISUALIZACOES): quantos
    quadros a grade mostrou, quantos com o número, quantos com a capa carregada e a marca mais
    perto de uma dos posts (casa até visualizacoes.MARCA_PARECIDA). Só números.
    """
    com_numero = sum(1 for _marca, vistas in vistos if vistas is not None)
    com_capa = [marca for marca, _vistas in vistos if marca]
    distancias = [visualizacoes.diferenca(marca, r["marca"]) for marca in com_capa for r in procurados]
    perto = (f", a marca mais perto: {min(distancias)} (casa até {visualizacoes.MARCA_PARECIDA})"
             if distancias else "")
    return (f"; na grade: {len(vistos)} quadro(s), {com_numero} com o número, {len(com_capa)} com a capa"
            + perto)


def _anotar_visualizacoes_junto(d, agora=None):
    """As visualizações lidas depois da Saúde do Vídeo: erro aqui não derruba a rodada."""
    try:
        achados, procurados = anotar_visualizacoes(d, agora)
        if procurados:
            logger.info(f"📈 [Robô Shopee Vídeo] Visualizações: achei {achados} de {procurados} vídeo(s) na grade.")
    except (Parada, Verificacao) as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Não li as visualizações: {ps.mascarar(getattr(e, 'motivo', ''))}")
        registro_processos.registrar(REGISTRO, PROCESSO_DAS_VISUALIZACOES, "parou", ok=False)
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Erro ao ler as visualizações: {type(e).__name__}")
        registro_processos.registrar(REGISTRO, PROCESSO_DAS_VISUALIZACOES, f"erro ({type(e).__name__})", ok=False)


def medicao_da_capa(agora=None):
    """
    A comparação da capa com chamada (P76) com os vídeos postados nos últimos
    DIAS_DA_COMPARACAO dias; depois que o Rafael liga a capa, só os de depois.
    """
    limite = _momento(agora_br(agora) - timedelta(days=DIAS_DA_COMPARACAO))
    return visualizacoes.comparar([r for r in listar("postado") if (r["postado_em"] or "") >= limite],
                                  ler_config().get("capa_com_chamada_desde"))


# --- Canal Afiliados: o vídeo postado vai à fila do canal ---

PROCESSO_DO_CANAL = "canal afiliados: vídeo para a fila"


def levar_ao_canal(rascunho, link_post):
    """
    O vídeo aprovado e postado vai à fila do Canal Afiliados, com o link do post e os links
    dos produtos: o robô deixa o pedido (pedidos_do_canal), e o bot_mestre põe na fila no
    padrão do canal. Sem o link do post, não vai, e o aviso diz (P63). Nada aqui desfaz
    nem segura o post. Decisões do Rafael (28/10, P62 a P64): DECISOES.md, Shopee Vídeo.
    """
    try:
        if not link_post:
            # Falha do robô (o caminho do Copiar link): o checkup cobra a que se repete.
            registro_processos.registrar(REGISTRO, PROCESSO_DO_CANAL, "de fora - sem o link do post", ok=False)
            avisar("📺 Canal Afiliados: o vídeo que postei não foi para a fila do canal, porque não consegui "
                   "copiar o link do post na Shopee Vídeo (sem o link, ele não vai).")
            return
        pedidos_do_canal.pedir(rascunho["id"], rascunho["arquivo"], link_post, links_para_o_canal(rascunho),
                               (rascunho["produtos"] or [""])[0])
        registro_processos.registrar(REGISTRO, PROCESSO_DO_CANAL, "pedido", ok=True)
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] O vídeo não foi para o Canal Afiliados: {type(e).__name__}")
        registro_processos.registrar(REGISTRO, PROCESSO_DO_CANAL, f"erro ({type(e).__name__})", ok=False)
        avisar("📺 Canal Afiliados: o vídeo que postei não foi para a fila do canal (o pedido não foi guardado).")


def links_para_o_canal(rascunho):
    """
    Os links de afiliado dos produtos do rascunho, com a etiqueta do Canal Afiliados. No
    link de produto, o do produto anexado (o do link ou o da troca, P33) e os dos produtos a
    mais (P59), na ordem do post; no vídeo de Ver Produtos, cada produto anexado pelo link dele
    no rascunho (links_dos_produtos: o achado pelo nome, o trocado pelo da loja que paga mais,
    P57, e o a mais, P66), que leva ao anúncio exato do post, e o sem link achado na API pelo
    nome (como a foto da edição, P39); o que não se acha fica de fora. A API que falha deixa o
    link original, e o Rafael fica sabendo, como em todo robô que troca link (06/10:
    DECISOES.md, Canal Viral).
    """
    destino = asyncio.run(link_para_converter(rascunho["link"]))
    if eh_video(destino):
        nomes = rascunho["produtos"] or []
        curtos = rascunho.get("links_dos_produtos") or []
        curtos = curtos if len(curtos) == len(nomes) else [""] * len(nomes)
        enderecos = [(api_shopee.produto_do_link(asyncio.run(link_para_converter(curto))) if curto else None)
                     or oferta_pelo_nome(nome).get("productLink") for nome, curto in zip(nomes, curtos)]
    else:
        enderecos = [destino] + [produto.get("endereco") or asyncio.run(link_para_converter(produto["link"]))
                                 for produto in rascunho.get("mais_produtos") or []]
    links = []
    for endereco in filter(None, enderecos):
        link = asyncio.run(api_shopee.converter_link_shopee(endereco, api_shopee.ETIQUETA_CANAL_AFILIADOS)) or endereco
        if link not in links:
            links.append(link)
    return links


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


def produtos_para_refazer(rascunho):
    """
    Os produtos do rascunho de link de produto na ordem do post, com o link de cada um, para o robô curtir de
    novo ao refazer o rascunho no app (o 1º é o do vídeo, os outros os produtos a mais); [] sem o link de algum.
    """
    nomes = list(rascunho.get("produtos") or [])
    links = [rascunho.get("link") or ""] + [p.get("link") or "" for p in rascunho.get("mais_produtos") or []]
    if not nomes or len(links) != len(nomes) or not all(links):
        return []
    return [{"nome": nome, "link": link, "do_video": n == 0} for n, (nome, link) in enumerate(zip(nomes, links))]


def _guardar_a_versao_de_antes(rascunho):
    """
    A versão de antes do rascunho refeito no app ganha um registro próprio, recusado (o robô a apaga do app
    como os recusados, conferindo antes o título e os produtos), no lugar dela na lista do app (no_app_em) e
    com versao_de, para não contar como rascunho do dia. Devolve o id dele.
    """
    antigo = criar(rascunho["id_video"])
    atualizar(antigo, estado="recusado", criado_em=rascunho["criado_em"],
              no_app_em=rascunho.get("no_app_em") or rascunho["criado_em"], versao_de=str(rascunho["id"]),
              titulo=rascunho["titulo"], produtos=rascunho["produtos"], link=rascunho["link"],
              mais_produtos=rascunho.get("mais_produtos") or [], arquivo=rascunho["arquivo"],
              print=rascunho["print"], fonte=rascunho.get("fonte"), rotulo_ia=rascunho.get("rotulo_ia"),
              aprovado_em=_momento(), motivo="a versão de antes do Editar ✏️")
    return antigo


def refazer_no_app(d, rascunho, agora=None):
    """
    O rascunho que o Rafael editou (Editar ✏️) e aprovou, refeito no app com a nova versão do vídeo (P192 1):
    o app não deixa trocar o vídeo de um rascunho, então o robô curte de novo os produtos (os mesmos links),
    põe a nova versão na galeria com um nome só dela, faz o rascunho do zero (os mesmos produtos, na mesma
    ordem, e o mesmo título), confere a tela final e salva. Só com o novo salvo, a versão de antes sai do app
    (_guardar_a_versao_de_antes e apagar_do_app); o que não sair dela na hora fica para a próxima rodada, como
    um recusado. O rascunho passa a ser o novo e ganha a hora de ir ao ar. No fim, descurte o que curtiu.
    """
    nova = rascunho.get("nova_versao") or {}
    arquivo, versao = nova.get("arquivo"), int(nova.get("versao") or 2)
    if not arquivo or not os.path.exists(arquivo):
        raise Parada("a nova versão do vídeo não está mais no servidor")
    produtos = produtos_para_refazer(rascunho)
    if not produtos:
        raise Parada("o rascunho não tem o link de cada produto para refazer no app")
    video = dict(video_do_rascunho(rascunho), arquivo=arquivo)
    curtidos, verificacao = [], False
    try:
        feitos = _curtir_os_produtos(d, video, produtos, curtidos)
        if len(feitos) != len(produtos):
            raise Parada(f"não consegui curtir de novo {len(produtos) - len(feitos)} de {len(produtos)} produto(s)")
        ir_ao_perfil(d)
        if not ps.por_na_galeria(d, arquivo, nome_na_galeria(rascunho["id"], versao)):
            raise Parada("a nova versão do vídeo não apareceu na galeria do celular")
        abrir_galeria(d, agora)
        marcar_so_o_mais_novo(d)
        seguir(d, CAMINHO_EDICAO[:1])
        efeitos_na_edicao(d)
        seguir(d, CAMINHO_EDICAO[1:])
        # Todos os produtos de antes, na mesma ordem: o que não anexa para tudo (nenhum é "a mais" aqui).
        nomes = list(rascunho["produtos"])
        _anexados, no_post = anexar_os_produtos(d, video, nomes, (), lista_limpa())
        if len(no_post) != len(nomes):
            raise Parada(f"o rascunho novo ficou com {len(no_post)} de {len(nomes)} produto(s)")
        escrever_a_legenda(d, rascunho["titulo"])
        _conferir(ps.conferir_tela_final(d, video_do_rascunho(rascunho)))
        _conferir(ps.ajustar_rotulo_de_ia(d, bool(rascunho.get("rotulo_ia"))))
        print_tela = os.path.join(PASTA_RASCUNHOS, f"{rascunho['id']}_nova_{versao}.png")
        d.screenshot(print_tela)
        tocar(d, "@tv_drafts_box", 12)
        if tem(tela(d), "@btn_post"):
            raise Parada("toquei em Rascunhos, mas o app continuou na tela final")
        # O novo está salvo: a versão de antes ganha o registro dela, e o rascunho passa a ser o novo.
        antigo = _guardar_a_versao_de_antes(rascunho)
        escolhas = edicao_video.escolhas_certas((rascunho.get("edicao") or {}).get("escolhas"))
        escolhas.update(miniatura=nova.get("miniatura") or escolhas["miniatura"], legenda=bool(nova.get("legenda")))
        quando = proxima_postagem(ler_config(), agora)
        atualizar(rascunho["id"], arquivo=arquivo, print=print_tela, no_app_em=_momento(agora), nova_versao={},
                  edicao=dict(rascunho.get("edicao") or {}, versoes=versao, escolhas=escolhas), estado="aprovado",
                  postar_em=quando, falhas_ao_postar="0", postar_agora_em=None, motivo="")
        registro_processos.registrar(REGISTRO, PROCESSO_DO_REFAZER, "refeito no app",
                                     f"{len(nomes)} produto(s), versão {versao}", ok=True, agora=agora)
        apagado = ""
        try:
            apagar_do_app(d, pegar(antigo))
            apagado = "apaguei a versão de antes."
        except Parada as e:
            # Fica recusada: a próxima rodada tenta de novo, conferindo o título e os produtos antes.
            registro_processos.registrar(REGISTRO, PROCESSO_DO_REFAZER, "a versão de antes ficou", e.motivo,
                                         ok=False, agora=agora)
            apagado = f"a versão de antes ainda não saiu do celular ({e.motivo}): tento de novo na próxima rodada."
        avisar(f"✏️ Robô da Shopee Vídeo: refiz no celular o rascunho que você editou e {apagado} Ele vai ao ar "
               f"por volta de {quando[11:16]} e fica em Aprovados para Postar ⏳ até lá.")
        return "rascunho editado refeito no app"
    except Verificacao:
        # Na Verificação o robô para sem tocar em mais nada: a curtida fica para as 4h.
        verificacao = True
        if curtidos:
            gravar_estado(favoritos_limpos=False)
        raise
    finally:
        if not verificacao:
            descurtir_no_fim(d, video, curtidos)


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
        # do celular, se ele cair no meio. Com o Editar ✏️, cada versão que foi à galeria (e a que pode
        # ter ido numa vez que parou no meio) também sai (P192 1).
        try:
            edicao = (pegar(ident) or {}).get("edicao") or {}
            ultima = int(edicao.get("versoes") or 1) + (1 if edicao else 0)
            for versao in range(1, ultima + 1):
                caminho = f"{ps.GALERIA}/{nome_na_galeria(ident, versao)}"
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

# Quantos rascunhos usados, do mais novo para o mais velho, o treino olha atrás de um de
# link de produto: o de link de vídeo (Ver Produtos) abre o vídeo, não a página do produto.
RASCUNHOS_DO_TREINO = 5


def rascunho_do_treino():
    """
    O rascunho usado mais novo com link de produto, para o treino abrir a página completa
    do produto; None sem nenhum.
    """
    usados = listar(*NO_APP, "postado", "apagado")
    for rascunho in list(reversed(usados))[:RASCUNHOS_DO_TREINO]:
        if rascunho["link"] and rascunho["produtos"] and not eh_video(asyncio.run(link_para_converter(rascunho["link"]))):
            return rascunho
    return None


def treinar(d, agora=None):
    """
    Percorre o caminho todo até a tela final sem salvar nem postar, conferindo cada tela
    com o mapa (os CAMINHOs): se a Shopee mudou o app, o Rafael fica sabendo antes de uma
    rodada de verdade travar no meio. Abre também a página completa de um produto já
    usado, sem curtir. Avisa no privado: caminho OK, ou a tela que mudou, com o print.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    # O resultado do treino anterior sai: enquanto este roda, o painel mostra "rodando".
    gravar_estado(treino_semana=semana(agora), treino_em=_momento(agora), treino_resultado="",
                  treino_depois_da_suspensao=False)
    try:
        ultimo = rascunho_do_treino()
        if ultimo:
            ir_ao_inicio(d)
            ps.abrir_link(d, ultimo["link"])
            pausa(12)
            # O nome guardado no rascunho, o que o app mostrou: a API pode não dizer mais o
            # produto de um link antigo (a oferta saiu), e o treino acusaria uma mudança no app.
            video = dict(video_do_rascunho(ultimo), produto=ultimo["produtos"][0])
            ok, motivo, _ = ps.abrir_pagina_completa(d, video)
            if not ok:
                raise Parada(f"página do produto: {motivo}")
        # O quadro "Rascunhos: N" só aparece com algum rascunho salvo: o treino não o exige.
        ir_ao_perfil(d)
        abrir_galeria(d, agora)
        marcar_so_o_mais_novo(d)
        seguir(d, CAMINHO_EDICAO[:1])
        efeitos = efeitos_na_edicao(d)
        if efeitos != EFEITOS_COMPLETOS:
            raise Parada(f"efeitos na edição: ficou {efeitos}")
        seguir(d, CAMINHO_EDICAO[1:])
        # A linha do Adicionar produto pode aparecer só alguns segundos depois (DEMORAM_A_APARECER).
        xml = esperar_na_tela(d, "@ll_add_product_symbol", ps.ESPERA_DA_FILEIRA) or tela(d)
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
# As respostas aos comentários dos vídeos do Rafael (P70) e o comentário do dia num post antigo
# (P148 2) saem durante o dia (DURANTE_O_DIA), quando as pessoas comentam, sem hora marcada: na 1ª
# rodada em que o celular está livre. As respostas, LEITURAS_DAS_RESPOSTAS vezes por dia, com pelo
# menos ESPACO_DAS_RESPOSTAS entre uma leitura e outra; cada leitura espera o começo da parte dela
# (o dia dividido em LEITURAS_DAS_RESPOSTAS partes iguais: das 8h, das 12h40 e das 17h20), para as
# três não saírem todas de manhã. Escolha do Rafael (06/11, P161 1): DECISOES.md, Shopee Vídeo.
DURANTE_O_DIA = (8, 22)
LEITURAS_DAS_RESPOSTAS = 3
ESPACO_DAS_RESPOSTAS = timedelta(hours=3)
PROCESSO_DA_LEITURA = "leitura das respostas"
# Respostas numa rodada (cada uma leva perto de 1 min); o resto fica para a rodada seguinte.
RESPOSTAS_POR_RODADA = 8
# O painel de comentários abre uns 8 s depois do vídeo (Motorola, 24/10/2026).
ESPERA_DOS_COMENTARIOS = 20
ROLADAS_NO_PAINEL = 4
ABA_DO_FEED = "Live e Vídeo"
ABA_PARA_VOCE = "Para você"
# Quantos vídeos do feed o robô passa, no máximo, procurando um para comentar.
VIDEOS_OLHADOS_NO_FEED = 12
# O painel chama uma rodada a cada 15 min (painel_shopee_video).
INTERVALO_DAS_RODADAS = timedelta(minutes=15)
# Os vídeos do feed do dia se espalham pelo Horário do Robô, um por rodada: o espaço entre dois
# que deram certo é o dia do robô dividido pelos do dia, no passo das rodadas, menos esta folga
# (a rodada seguinte começa uns segundos ou minutos antes da hora certa). Escolha do Rafael
# (P152): DECISOES.md, Shopee Vídeo.
FOLGA_DO_FEED = timedelta(minutes=5)
REGISTRO = "shopee_video"


def durante_o_dia(agora=None):
    """Agora está na parte do dia das respostas e do post antigo (DURANTE_O_DIA)?"""
    return DURANTE_O_DIA[0] <= agora_br(agora).hour < DURANTE_O_DIA[1]


def leituras_de_hoje(agora=None):
    """Quantas leituras das Notificações para responder o robô começou hoje (a continuação não conta)."""
    leituras = ler_estado().get("respostas_leituras") or {}
    return int(leituras.get("vezes") or 0) if leituras.get("dia") == agora_br(agora).strftime("%Y-%m-%d") else 0


def comeco_da_leitura(vez, agora=None):
    """Desde quando a leitura de número vez (0, 1, 2...) pode sair hoje: o começo da parte dela no dia."""
    inicio, fim = DURANTE_O_DIA
    comeco = agora_br(agora).replace(hour=inicio, minute=0, second=0, microsecond=0)
    return comeco + timedelta(hours=fim - inicio) * vez / LEITURAS_DAS_RESPOSTAS


def respostas_pendentes(agora=None):
    """
    Hora de responder os comentários? Durante o dia, até LEITURAS_DAS_RESPOSTAS leituras, cada uma
    a partir do começo da parte dela (comeco_da_leitura) e a ESPACO_DAS_RESPOSTAS ou mais da
    anterior; e de novo na rodada seguinte quando a anterior parou no limite de
    RESPOSTAS_POR_RODADA. Escolha do Rafael (06/11, P161 1): DECISOES.md, Shopee Vídeo.
    """
    estado = ler_estado()
    if estado.get("respostas_continuar"):
        return True
    momento = agora_br(agora)
    feitas = leituras_de_hoje(momento)
    if not durante_o_dia(momento) or feitas >= LEITURAS_DAS_RESPOSTAS:
        return False
    if (estado.get("respostas_em") or "") > _momento(momento - ESPACO_DAS_RESPOSTAS):
        return False
    return momento >= comeco_da_leitura(feitas, momento)


def contar_leitura(agora=None):
    """Mais uma leitura das respostas hoje (respostas_em e a conta do dia); fica no registro."""
    vez = leituras_de_hoje(agora) + 1
    gravar_estado(respostas_em=_momento(agora),
                  respostas_leituras={"dia": agora_br(agora).strftime("%Y-%m-%d"), "vezes": vez})
    registro_processos.registrar(REGISTRO, PROCESSO_DA_LEITURA, f"{vez}ª de {LEITURAS_DAS_RESPOSTAS} hoje",
                                 ok=None, agora=agora)


def videos_do_feed_que_faltam(agora=None):
    """
    Quantos dos vídeos do feed de hoje (o limite, VIDEOS_NO_FEED_POR_DIA) ainda faltam: o
    comentado e o só curtido contam (P151 1).
    """
    inicio = agora_br(agora).strftime("%Y-%m-%d 00:00:00")
    return max(0, interacoes.VIDEOS_NO_FEED_POR_DIA
               - interacoes.quantos_desde("video_feed", interacoes.FEITOS_NO_FEED, inicio))


def feed_pendente(agora=None):
    """
    Falta algum vídeo do feed hoje (até VIDEOS_NO_FEED_POR_DIA, sem meta), e o último que deu
    certo foi há intervalo_do_feed ou mais? Um por rodada, em qualquer hora do robô. O que falha
    não conta nem mexe no feed_em: a rodada seguinte tenta de novo, até dar certo. Escolhas do Rafael (P151 1 e P152): DECISOES.md, Shopee Vídeo.
    """
    if not videos_do_feed_que_faltam(agora):
        return False
    return (ler_estado().get("feed_em") or "") <= _momento(agora_br(agora) - intervalo_do_feed(ler_config()))


def intervalo_do_feed(config):
    """
    O espaço entre dois vídeos do feed que deram certo: as horas do Horário do Robô divididas
    pelos do dia, no passo das rodadas, menos a FOLGA_DO_FEED. No Dia Todo, com 5 por dia, 4h40;
    das 8h às 22h, 2h40. Escolha do Rafael (P152): DECISOES.md. A hora das 4h conta: acabada a
    limpeza, ela fica livre (P161 1).
    """
    inicio, fim = int(config["robo_inicio"]), int(config["robo_fim"])
    horas = max(1, fim - inicio)
    espaco = timedelta(hours=horas) / interacoes.VIDEOS_NO_FEED_POR_DIA
    passos = max(1, int(espaco / INTERVALO_DAS_RODADAS))
    return passos * INTERVALO_DAS_RODADAS - FOLGA_DO_FEED


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
        lugar, painel, i, visto = _conferir_resposta(d, texto, nome, comentario, resposta)
        if lugar == "embaixo":
            _curtir_o_comentario(d, nome, comentario, marca)
            _guardar_o_perfil(painel, i)
            interacoes.guardar(marca, "comentario", "respondido", agora)
            gravar_estado(respostas_textos=(anteriores + [resposta])[-10:])
            registro_processos.registrar(REGISTRO, "responder comentário", "respondido", visto, ok=True,
                                         origem=marca)
            registrar_tentativa("responder", "respondido", produto=produto, agora=agora)
            return "respondido"
        if lugar == "outro lugar":
            # Erro grave (P12): a resposta foi parar embaixo de outro comentário ou solta.
            motivo = "a resposta não ficou embaixo do comentário certo"
            interacoes.guardar(marca, "comentario", "lugar errado", agora)
            registro_processos.registrar(REGISTRO, "responder comentário", "resposta no lugar errado", visto,
                                         ok=False, origem=marca)
            registrar_tentativa("responder", "parou", motivo, produto, agora)
            _guardar_caso(d, "responder", "lugar errado", f"{motivo} ({visto})", agora=agora)
            avisar(f"⚠️ Robô da Shopee Vídeo: a resposta a um comentário no vídeo de {produto or 'um produto'} "
                   f"não ficou embaixo do comentário certo. Confira no app e apague à mão se precisar: "
                   f"\"{resposta}\". Não vou responder esse comentário de novo.")
            return "lugar errado"
        raise Parada(f"a resposta não apareceu embaixo do comentário; {visto}")
    except Parada as e:
        # Na próxima vez, o robô confere de novo se o perfil já respondeu antes de responder:
        # uma resposta que saiu sem aparecer na tela não vira duas.
        tentativas = interacoes.guardar_falha(marca, "comentario", agora)
        registro_processos.registrar(REGISTRO, "responder comentário", "parou", e.motivo, ok=False, origem=marca)
        registrar_tentativa("responder", "parou", e.motivo, produto, agora)
        _guardar_caso(d, "responder", "parou", e.motivo, agora=agora)
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


def _curtir_o_comentario(d, nome, comentario, marca):
    """
    Curte o comentário da pessoa que o robô acabou de responder, pelo coração da linha dele,
    e confere pelo "Curtido pelo criador" que aparece embaixo. Pedido do Rafael (30/10):
    DECISOES.md, Shopee Vídeo. A curtida que não sai fica só no registro: a resposta já foi.
    """
    try:
        xml = tela(d)
        painel = interacoes.comentarios_do_painel(xml)
        i = interacoes.alvo_no_painel(painel, nome, comentario)
        if i is not None and painel[i]["curtido"]:
            resultado = "já curtido"
        elif i is None or not painel[i]["curtir"]:
            resultado = "sem o coração na tela"
        elif ps.proibido_no_ponto(xml, *painel[i]["curtir"]):
            resultado = "recusado"
        else:
            d.click(*painel[i]["curtir"])
            pausa(2)
            depois = interacoes.comentarios_do_painel(tela(d))
            j = interacoes.alvo_no_painel(depois, nome, comentario)
            resultado = "curtido" if j is not None and depois[j]["curtido"] else "não confirmado"
    except Exception as e:
        resultado = f"erro ({type(e).__name__})"
    registro_processos.registrar(REGISTRO, "curtir comentário", resultado,
                                 ok=True if resultado in ("curtido", "já curtido") else False, origem=marca)
    return resultado


def _conferir_resposta(d, texto, nome, comentario, resposta):
    """
    Onde a resposta enviada ficou (interacoes.onde_ficou) e o que foi visto, em rótulos
    fixos para o registro (interacoes.como_ficou): (lugar, painel, i, visto). Primeiro no
    painel como ficou depois de enviar; sem confirmar ali, de novo com o vídeo reaberto
    pela notificação. Logo depois de enviar, o painel nem sempre mostra a resposta no lugar
    em que ela ficou (Motorola, 30/10/2026); reaberto, ele vem recarregado da Shopee.
    """
    pausa(3)
    painel = interacoes.comentarios_do_painel(tela(d))
    i = interacoes.alvo_no_painel(painel, nome, comentario)
    if interacoes.onde_ficou(painel, i, resposta) == "embaixo":
        return "embaixo", painel, i, "conferida na hora"
    na_hora = interacoes.como_ficou(painel, i, resposta)
    _sair_sem_salvar(d)
    _abrir_notificacao(d, texto)
    _abrir_comentarios(d)
    _, painel, i = _achar_no_painel(d, nome, comentario)
    lugar = interacoes.onde_ficou(painel, i, resposta)
    if lugar == "embaixo":
        return lugar, painel, i, f"conferida ao reabrir (na hora: {na_hora})"
    return lugar, painel, i, f"na hora: {na_hora}; ao reabrir: {interacoes.como_ficou(painel, i, resposta)}"


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
    em que ainda não esteve, curte e, quando a IA tem algo específico a dizer, comenta (texto
    da IA, diferente dos anteriores; sem nada a dizer, só a curtida, P151 1). Um vídeo por
    rodada; os do dia se espalham pelo Horário do Robô (feed_pendente, P152). Pedido do Rafael (P10).
    """
    ir_ao_inicio(d)
    tocar(d, ABA_DO_FEED, 8)
    tocar(d, ABA_PARA_VOCE, 6)
    # Comenta o 1º, o 2º ou o 3º vídeo que der: não sempre o primeiro que aparece.
    pular = random.randint(0, 2)
    anteriores = ler_estado().get("feed_textos") or []
    try:
        for olhada in range(VIDEOS_OLHADOS_NO_FEED):
            # Cada tela olhada fica no registro com o que o robô viu nela (um texto fixo):
            # o checkup mostra onde ele se perde quando nenhum vídeo serve. O vídeo que
            # serviria leva a faixa dos comentários dele.
            video, motivo = interacoes.ler_o_feed(tela(d))
            marca = interacoes.marca(video["autor"], video["legenda"]) if video else None
            faixa = ""
            if not video:
                visto = "live pulada" if motivo == "live" else f"pulada: {motivo}"
            elif interacoes.resultado_de(marca, "video_feed"):
                visto = "já comentado antes"
            elif _proprio(video):
                visto = "vídeo do próprio perfil"
            elif _muitos_comentarios(video, olhada):
                visto = "muitos comentários"
            else:
                faixa = faixa_dos_comentarios(video)
                pausa(random.uniform(6, 14))  # assiste um pouco antes
                if not pular:
                    registro_processos.registrar(REGISTRO, "feed: vídeo olhado", "escolhido", faixa, ok=None)
                    return _interagir_com(d, video, marca, anteriores, agora)
                pular -= 1
                visto = "deixado passar"
            registro_processos.registrar(REGISTRO, "feed: vídeo olhado", visto, faixa, ok=None)
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


def faixa_dos_comentarios(video):
    """
    Quantos comentários tem o vídeo do feed, em faixa, para o registro: mostra se o robô
    lê o número embaixo do balão, de que depende a preferência pelos de poucos (P70).
    """
    numero = video.get("comentarios")
    if numero is None:
        return "sem o número de comentários"
    return (f"até {interacoes.POUCOS_COMENTARIOS} comentários" if numero <= interacoes.POUCOS_COMENTARIOS
            else f"mais de {interacoes.POUCOS_COMENTARIOS} comentários")


def _muitos_comentarios(video, olhada):
    """
    O vídeo tem mais de POUCOS_COMENTARIOS (o comentário do robô sumiria no meio)? Só na 1ª
    metade das telas: sem nenhum com poucos, depois vale qualquer um, para os do dia
    saírem. Escolha do Rafael (P70): DECISOES.md, Shopee Vídeo.
    """
    return ((video.get("comentarios") or 0) > interacoes.POUCOS_COMENTARIOS
            and olhada < VIDEOS_OLHADOS_NO_FEED // 2)


# A tela do vídeo vai à IA com metade do tamanho: basta para ver o produto e gasta menos.
TAMANHO_DA_TELA_PARA_A_IA = (540, 1200)


def _tela_do_video(d):
    """A tela do vídeo do feed em JPEG, para a IA comentar o que aparece nele (P70); None se o print falhar."""
    try:
        imagem, saida = d.screenshot().convert("RGB"), io.BytesIO()
        imagem.thumbnail(TAMANHO_DA_TELA_PARA_A_IA)
        imagem.save(saida, format="JPEG", quality=80)
        return saida.getvalue()
    except Exception:
        return None


MOTIVO_DO_FEED_SEM_O_COMENTARIO = "o comentário não apareceu no vídeo do feed"


def _interagir_com(d, video, marca, anteriores, agora=None):
    texto = asyncio.run(interacoes.gerar_comentario(video["legenda"], anteriores, _tela_do_video(d)))
    if texto is None:
        raise Parada("a IA não escreveu o comentário do feed")
    if not texto:
        interacoes.guardar(marca, "video_feed", "pulado", agora)
        registro_processos.registrar(REGISTRO, "feed: comentar", "pulado pela IA", ok=None, origem=marca)
        return "feed: a IA pulou o vídeo"
    _curtir_no_feed(d, video)
    if texto == interacoes.CURTIR:
        # Sem nada específico para dizer, fica só a curtida: o vídeo conta nos do dia e não
        # volta. Escolha do Rafael (P151 1): DECISOES.md, Shopee Vídeo.
        _feito_no_feed(marca, interacoes.SO_CURTIDO, agora)
        registro_processos.registrar(REGISTRO, "feed: comentar", interacoes.SO_CURTIDO,
                                     "a IA não viu nada específico para comentar", ok=True, origem=marca)
        registrar_tentativa("feed", "curtido", agora=agora)
        return "feed: 1 vídeo curtido, sem comentário"
    try:
        apareceu = _comentar_no_feed(d, video, texto)
    except Parada as e:
        # A curtida já saiu: o vídeo conta nos do dia, como só curtido, para nunca passarem de
        # VIDEOS_NO_FEED_POR_DIA curtidas por dia. A parada segue para o caso e o checkup.
        _feito_no_feed(marca, interacoes.SO_CURTIDO, agora)
        registro_processos.registrar(REGISTRO, "feed: comentar", interacoes.SO_CURTIDO,
                                     f"o comentário parou: {e.motivo}", ok=False, origem=marca)
        raise
    gravar_estado(feed_textos=(anteriores + [texto])[-10:])
    if not apareceu:
        # Enviado sem aparecer: pode ter saído, então o vídeo não volta e conta no dia. O caso
        # guarda o painel logo depois do envio e os toques até ele: às 23:38 de 08/11, sem o
        # caso, não deu para ver por que o comentário não apareceu.
        _feito_no_feed(marca, "não confirmado", agora)
        registro_processos.registrar(REGISTRO, "feed: comentar", "não confirmado", "enviado sem aparecer na lista",
                                     ok=False, origem=marca)
        registrar_tentativa("feed", "parou", MOTIVO_DO_FEED_SEM_O_COMENTARIO, agora=agora)
        _guardar_caso(d, "feed", "parou", MOTIVO_DO_FEED_SEM_O_COMENTARIO, agora=agora)
        return "feed: comentário enviado sem aparecer na lista"
    _feito_no_feed(marca, "comentado", agora)
    registro_processos.registrar(REGISTRO, "feed: comentar", "comentado", ok=True, origem=marca)
    registrar_tentativa("feed", "comentado", agora=agora)
    return "feed: 1 vídeo curtido e comentado"


def _feito_no_feed(marca, estado, agora=None):
    """
    O vídeo do feed que conta nos do dia (FEITOS_NO_FEED): a marca, para não voltar, e o feed_em,
    de onde se conta o espaço até o próximo. O que falha antes da curtida não passa por aqui, e a
    rodada seguinte tenta de novo (P152).
    """
    interacoes.guardar(marca, "video_feed", estado, agora)
    gravar_estado(feed_em=_momento(agora))


# --- O comentário no próprio vídeo (P148 2) ---

# Depois de cada post, o robô curte o vídeo, escreve um comentário (texto curto da IA, chamando
# para comprar) e curte o comentário; 1 vez por dia, das 8h às 22h (P161 1), faz o mesmo num
# post antigo dele. O vídeo abre pelo link do post, no mesmo player do feed. Escolha do Rafael
# (P148 2, avisado da regra de Spam e Falso Engajamento): DECISOES.md, Shopee Vídeo.
PROCESSO_DO_PROPRIO = "próprio post: comentar"
PROCESSO_DO_ANTIGO = "post antigo: comentar"
MOTIVO_DO_POST_EM_ANALISE = "o vídeo do post ainda está em análise na Shopee"
MOTIVO_DO_POST_REMOVIDO = "o vídeo do post foi removido"
# Quantos textos do robô, de todos os posts, a IA recebe para não repetir nenhum.
TEXTOS_GUARDADOS_DO_PROPRIO = 20


def _abrir_o_video_do_post(d, link):
    """O vídeo do Rafael pelo link do post, no player do feed (interacoes.video_do_feed). Parada se não abriu."""
    ir_ao_inicio(d)
    ps.abrir_link(d, link)
    pausa(12)
    xml = tela(d)
    video = interacoes.video_do_feed(xml)
    if not video and not ps.video_removido(xml) and not ps.video_em_analise(xml):
        pausa(ESPERA_DO_VER_PRODUTOS)
        xml = tela(d)
        video = interacoes.video_do_feed(xml)
    if ps.video_removido(xml):
        # Marcado, o post sai da escolha do post antigo (interacoes.TIPO_DO_REMOVIDO).
        interacoes.guardar(interacoes.marca_do_post(link), interacoes.TIPO_DO_REMOVIDO, "removido")
        raise Parada(MOTIVO_DO_POST_REMOVIDO)
    if ps.video_em_analise(xml):
        raise Parada(MOTIVO_DO_POST_EM_ANALISE)
    if not video:
        raise Parada("o vídeo do post não abriu no player")
    return video


def _registrar_no_post(antigo, passo, resultado, ok, agora=None):
    """O passo do comentário no próprio vídeo no registro: o de post antigo é interação; o outro vai com o post."""
    if antigo:
        registro_processos.registrar(REGISTRO, f"post antigo: {passo}", resultado, ok=ok, agora=agora)
    else:
        registro_processos.registrar(REGISTRO, f"próprio post: {passo}", resultado, ok=ok, agora=agora)


def _curtir_o_video_do_post(d, video, antigo, agora=None):
    """
    Curte o vídeo do Rafael pelo coração do player, só se ele não está curtido: o toque no
    curtido descurtiria, e sem a tela dizer o estado o robô não toca. A curtida que não sai
    fica só no registro, e o comentário segue.
    """
    curtido = interacoes.coracao_curtido(video["coracao_desc"])
    if curtido:
        resultado = "já curtido"
    elif curtido is None:
        resultado = "coração sem o estado na tela"
    elif ps.proibido_no_ponto(tela(d), *video["coracao"]):
        resultado = "recusado"
    else:
        d.click(*video["coracao"])
        pausa(2)
        depois = interacoes.video_do_feed(tela(d))
        resultado = "curtido" if depois and interacoes.coracao_curtido(depois["coracao_desc"]) else "não confirmado"
    _registrar_no_post(antigo, "curtir o vídeo", resultado, resultado in ("curtido", "já curtido"), agora)
    return resultado


def _abrir_os_comentarios_do_post(d, video):
    """O painel de comentários do vídeo do post, pelo balão do player: a tela com ele aberto."""
    if ps.proibido_no_ponto(tela(d), *video["balao"]):
        raise Parada(ps.RECUSA)
    d.click(*video["balao"])
    pausa(3)
    xml = painel_de_comentarios(d)
    if not xml:
        raise Parada("o painel de comentários do vídeo do post não abriu")
    return xml


def _abrir_o_campo_do_post(d, xml):
    """O campo de escrever do painel aberto. No vídeo sem nenhum comentário ele já abre escrevendo."""
    if interacoes.campo_de_escrever(xml):
        return
    campo = interacoes.campo_de_comentar(xml)
    if not campo:
        raise Parada("não achei o campo de comentar no vídeo do post")
    d.click(*campo)
    pausa(2)
    if not interacoes.campo_de_escrever(tela(d)):
        raise Parada("o campo de comentar do vídeo do post não abriu")


def _linha_do_texto(painel, texto):
    """O comentário do painel com o texto que o robô escreveu, ou None."""
    return next((c for c in painel if interacoes.parecidos(c["texto"], texto)), None)


def _apareceu_no_painel(d, texto):
    """O comentário enviado está na lista (relendo e, sem ele, com o painel rolado para o alto)?"""
    for vez in range(2):
        if _linha_do_texto(interacoes.comentarios_do_painel(tela(d)), texto):
            return True
        if not vez:
            ps.rolar(d, para_cima=True)
            pausa(2)
    return False


def _comentario_curtido(linha):
    return bool(linha) and (linha["curtido"] or interacoes.coracao_curtido(linha["coracao_desc"]) is True)


def _curtir_o_comentario_do_post(d, texto, antigo, agora=None, ident=None):
    """
    Curte o comentário que o robô acabou de escrever, pelo coração da linha dele, e confere pelo
    "Curtido pelo criador", pelo coração curtido ou pelo número de curtidas do coração, que sobe (no
    comentário do próprio Rafael, só o número muda). A curtida que não sai não para nada (o
    comentário já foi): fica no registro, e o caso dela guarda a tela de logo depois e os últimos
    toques, para o Claude ver se o toque não pegou ou se a curtida não aparece (casos_robo).
    """
    try:
        xml = tela(d)
        linha = _linha_do_texto(interacoes.comentarios_do_painel(xml), texto)
        if _comentario_curtido(linha):
            resultado = "já curtido"
        elif not linha or not linha["curtir"]:
            resultado = "sem o coração na tela"
        elif ps.proibido_no_ponto(xml, *linha["curtir"]):
            resultado = "recusado"
        else:
            d.click(*linha["curtir"])
            pausa(2)
            depois = _linha_do_texto(interacoes.comentarios_do_painel(tela(d)), texto)
            subiu = bool(depois) and depois["curtidas"] > linha["curtidas"]
            resultado = "curtido" if _comentario_curtido(depois) or subiu else "não confirmado"
    except Exception as e:
        resultado = f"erro ({type(e).__name__})"
    ok = resultado in ("curtido", "já curtido")
    _registrar_no_post(antigo, "curtir o comentário", resultado, ok, agora)
    if not ok:
        _guardar_caso(d, "post_antigo" if antigo else "comentar_post", "curtida não confirmada",
                      f"a curtida no comentário do próprio post não se confirmou ({resultado})", ident=ident,
                      agora=agora)
    return resultado


def comentar_no_post(d, rascunho, antigo=False, agora=None):
    """
    O comentário do Rafael num post do robô (P148 2): abre o vídeo pelo link do post, curte o
    vídeo (se ainda não está curtido), abre os comentários, pede à IA um texto curto chamando
    para comprar, diferente dos comentários do Rafael na tela, dos que o robô já fez nesse post
    e dos últimos de todos os posts, escreve, envia, confere que apareceu e curte o comentário.
    Devolve (resultado, texto, curtidas): "comentado" ou "não confirmado" (enviado sem aparecer
    na lista: pode ter saído, e não é repetido), o texto e o que saiu das duas curtidas (o vídeo e
    o comentário). O que não dá certo antes de enviar para (Parada), sem nada escrito.
    """
    video = _abrir_o_video_do_post(d, rascunho["link_post"])
    curtiu_o_video = _curtir_o_video_do_post(d, video, antigo, agora)
    xml = _abrir_os_comentarios_do_post(d, video)
    na_tela = [c["texto"] for c in interacoes.comentarios_do_painel(xml) if c["criador"] and c["texto"]]
    feitos = rascunho.get("comentarios_proprios") or []
    recentes = ler_estado().get("proprio_textos") or []
    anteriores = list(dict.fromkeys(na_tela + feitos + recentes))
    produto = (rascunho.get("produtos") or [""])[0]
    texto = asyncio.run(interacoes.gerar_proprio(produto, rascunho.get("titulo") or "", anteriores))
    if not texto:
        raise Parada("a IA não escreveu o comentário do post")
    _abrir_o_campo_do_post(d, xml)
    _escrever_e_enviar(d, texto)
    apareceu = _apareceu_no_painel(d, texto)
    atualizar(rascunho["id"], comentarios_proprios=feitos + [texto])
    gravar_estado(proprio_textos=(recentes + [texto])[-TEXTOS_GUARDADOS_DO_PROPRIO:])
    curtiu_o_comentario = _curtir_o_comentario_do_post(d, texto, antigo, agora, rascunho["id"]) if apareceu else ""
    return ("comentado" if apareceu else "não confirmado"), texto, (curtiu_o_video, curtiu_o_comentario)


def _comentar_a_mao(rascunho, motivo=""):
    """Sem o comentário do robô, o do Gem vai ao Rafael para ele comentar à mão, como antes da P148."""
    if motivo:
        avisar(f"⚠️ Robô da Shopee Vídeo: não consegui comentar no vídeo que foi ao ar ({motivo}).")
    if rascunho.get("comentario"):
        avisar(ps.AVISO_COMENTARIO)
        avisar(rascunho["comentario"])


def comentar_depois_do_post(d, ident, agora=None):
    """
    Logo depois do post, o comentário no vídeo (P148 2). Nada aqui desfaz nem para o post: o que
    não dá certo fica no registro e volta nas rodadas seguintes (comentario_do_post_pendente). Sem
    o link do post, o comentário do Gem vai ao Rafael para ele comentar à mão.
    """
    try:
        rascunho = pegar(ident)
        if not rascunho:
            return ""
        if not rascunho.get("link_post"):
            registro_processos.registrar(REGISTRO, PROCESSO_DO_PROPRIO, "sem o link do post", ok=False, agora=agora)
            _comentar_a_mao(rascunho)
            return "sem o link do post"
        return tentar_o_comentario_do_post(d, rascunho, agora)
    except Exception as e:
        # O post já foi ao ar: nada daqui pode fazê-lo parecer que não saiu.
        logger.warning(f"⚠️ [Robô Shopee Vídeo] O comentário depois do post não rodou: {type(e).__name__}")
        return "erro"


def tentar_o_comentario_do_post(d, rascunho, agora=None):
    """
    Uma tentativa do comentário de depois do post. Nunca para a rodada: o que não deu certo conta
    uma tentativa e volta depois de INTERVALO_DO_PROPRIO; na última, o Rafael recebe o comentário
    do Gem para fazer à mão. Devolve "comentado", "não confirmado" ou "parou".
    """
    marca = interacoes.marca_do_post(rascunho["link_post"])
    try:
        resultado, texto, curtidas = comentar_no_post(d, rascunho, antigo=False, agora=agora)
    except Verificacao:
        av.abrir_tela(celular=True, verificacao=True)
        motivo = "verificação da Shopee na tela"
    except Parada as e:
        motivo = e.motivo
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] O comentário no post não saiu: {type(e).__name__}")
        motivo = f"erro inesperado ({type(e).__name__})"
    else:
        interacoes.guardar(marca, interacoes.TIPO_DO_POST, resultado, agora)
        registro_processos.registrar(REGISTRO, PROCESSO_DO_PROPRIO, resultado, ok=resultado == "comentado",
                                     origem=marca, agora=agora)
        registrar_tentativa("comentar_post", resultado, agora=agora)
        avisar(_aviso_do_comentario(resultado, texto, curtidas))
        return resultado
    tentativas = interacoes.guardar_falha(marca, interacoes.TIPO_DO_POST, agora)
    registro_processos.registrar(REGISTRO, PROCESSO_DO_PROPRIO, "parou", motivo, ok=False, origem=marca,
                                 agora=agora)
    registrar_tentativa("comentar_post", "parou", motivo, agora=agora)
    try:
        _guardar_caso(d, "comentar_post", "parou", motivo, ident=rascunho["id"], agora=agora)
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Caso do comentário no post não guardado: {type(e).__name__}")
    if tentativas >= interacoes.TENTATIVAS_DO_PROPRIO:
        interacoes.guardar(marca, interacoes.TIPO_DO_POST, "desistiu", agora)
        registro_processos.registrar(REGISTRO, PROCESSO_DO_PROPRIO, "desistiu", motivo, ok=False, origem=marca,
                                     agora=agora)
        _comentar_a_mao(rascunho, motivo)
    return "parou"


def _aviso_do_comentario(resultado, texto, curtidas):
    """O aviso do comentário de depois do post: o texto e só as curtidas que saíram."""
    feitas = [nome for nome, curtida in zip(("o vídeo", "o comentário"), curtidas) if curtida in ("curtido", "já curtido")]
    curti = f" e curti {' e '.join(feitas)}" if feitas else ""
    enviado = "" if resultado == "comentado" else " (enviado, mas não apareceu na lista)"
    return f"💬 Robô da Shopee Vídeo: comentei no vídeo que foi ao ar{curti}{enviado}:\n\n{texto}"


def comentario_do_post_pendente(agora=None):
    """
    O post do robô de menos de 1 dia cujo comentário de depois do post não saiu e volta agora
    (P148 2): a última tentativa há INTERVALO_DO_PROPRIO ou mais e menos de TENTATIVAS_DO_PROPRIO
    tentativas. O mais novo primeiro; None sem nenhum.
    """
    momento = agora_br(agora)
    desde, limite = _momento(momento - timedelta(days=1)), _momento(momento - interacoes.INTERVALO_DO_PROPRIO)
    for rascunho in reversed(listar("postado")):
        if not rascunho["link_post"] or (rascunho["postado_em"] or "") < desde:
            continue
        situacao = interacoes.situacao(interacoes.marca_do_post(rascunho["link_post"]), interacoes.TIPO_DO_POST)
        if (situacao and situacao["resultado"] == "falhou" and situacao["momento"] <= limite
                and situacao["tentativas"] < interacoes.TENTATIVAS_DO_PROPRIO):
            return rascunho
    return None


# O post que ficou sem o link logo depois de postar (o vídeo ainda em análise na Shopee, um passo
# que não apareceu): sem o link, o robô não comenta nem leva o vídeo ao Canal Afiliados. Como a
# falha antes de comentar (P148 2), ele busca o link de novo nas rodadas seguintes, a cada
# INTERVALO_DO_PROPRIO, até TENTATIVAS_DO_LINK buscas contando a de logo depois do post, só
# enquanto o post é o mais novo do robô, e confere pela legenda que o vídeo aberto é o do post.
# Com o link, faz o que o post faria (o link no privado, o canal e o comentário); sem ele, o
# comentário do Gem vai ao Rafael e o aviso do canal também, como antes. DECISOES.md, Shopee Vídeo.
TENTATIVAS_DO_LINK = 3
AVISO_SEM_O_LINK_AGORA = ("O link do post não saiu agora (ele está no seu Perfil em Shopee Vídeo). Tento de novo nas "
                          "próximas rodadas: com ele, comento no vídeo e levo o vídeo ao Canal Afiliados.")
# A legenda que o player mostra vem cortada no fim ("... Veja mais"): o começo dela, com pelo
# menos estas letras, tem de ser o começo do título do post.
LETRAS_DA_LEGENDA = 12


def legenda_do_post(legenda, titulo):
    """
    A legenda do vídeo aberto no player (cortada no fim, com "..." e "Veja mais") é a do post com
    esse título? Pelo começo, sem os espaços nem os caracteres invisíveis (ps.mesma_legenda), e
    também como a acessibilidade lê os emojis (ps.como_o_android_le).
    """
    lida = ps._o_que_conta(re.split(r"\.\.\.|…|Veja mais", legenda or "")[0])
    if len(lida) < LETRAS_DA_LEGENDA:
        return False
    return any(ps._o_que_conta(texto).startswith(lida) for texto in (titulo, ps.como_o_android_le(titulo)))


def links_esperando(agora=None):
    """Os posts do robô de menos de 1 dia que ficaram sem o link e ainda esperam a busca de novo."""
    desde = _momento(agora_br(agora) - timedelta(days=1))
    return [r for r in listar("postado") if not r["link_post"] and (r["postado_em"] or "") >= desde
            and r["busca_do_link"].get("vezes") and not r["busca_do_link"].get("fim")]


def link_do_post_pendente(agora=None):
    """
    O post sem o link que o robô busca de novo agora, ou None: o mais novo do robô (outro vídeo
    depois dele seria o mais novo da grade), esperando a busca, a última há INTERVALO_DO_PROPRIO
    ou mais.
    """
    postados = listar("postado")
    if not postados:
        return None
    ultimo = max(postados, key=lambda r: (r["postado_em"] or "", r["id"]))
    if ultimo["id"] not in {r["id"] for r in links_esperando(agora)}:
        return None
    limite = _momento(agora_br(agora) - interacoes.INTERVALO_DO_PROPRIO)
    return ultimo if ultimo["busca_do_link"]["vezes"][-1] <= limite else None


def desistir_do_link(rascunho, motivo, agora=None):
    """
    O post fica sem o link de vez: o comentário do Gem vai ao Rafael para ele comentar à mão
    (P148 2), e o aviso diz que o vídeo não foi ao Canal Afiliados (P63).
    """
    busca = dict(rascunho["busca_do_link"] or {})
    atualizar(rascunho["id"], busca_do_link={**busca, "fim": "desistiu"})
    registro_processos.registrar(REGISTRO, PROCESSO_DO_PROPRIO, "sem o link do post", motivo, ok=False, agora=agora)
    _comentar_a_mao(rascunho)
    levar_ao_canal(rascunho, "")


def buscar_o_link_de_novo(d, rascunho, agora=None):
    """
    A busca de novo do link do post que não saiu logo depois de postar (link_do_post_pendente):
    com o link, o robô manda o link no privado, leva o vídeo ao Canal Afiliados e comenta, como
    no post; sem ele, conta a busca e, na última, desiste (desistir_do_link).
    """
    busca = dict(rascunho["busca_do_link"] or {})
    vezes = list(busca.get("vezes") or [])
    link = link_do_post(d, ident=rascunho["id"], agora=agora, titulo=rascunho["titulo"], busca=len(vezes) + 1)
    if not link:
        vezes.append(_momento(agora))
        atualizar(rascunho["id"], busca_do_link={**busca, "vezes": vezes})
        if len(vezes) >= TENTATIVAS_DO_LINK:
            desistir_do_link(pegar(rascunho["id"]), f"{len(vezes)} buscas", agora)
            return f"link do post: não saiu em {len(vezes)} buscas"
        return f"link do post: não saiu na {len(vezes)}ª busca"
    atualizar(rascunho["id"], link_post=link, busca_do_link={**busca, "fim": "copiado"})
    postado = pegar(rascunho["id"])
    hora = (postado["postado_em"] or "")[11:16]
    avisar(f"🔗 Robô da Shopee Vídeo: consegui o link do vídeo que foi ao ar às {hora}:\n\n{link}")
    levar_ao_canal(postado, link)
    return f"link do post: copiado na {len(vezes) + 1}ª busca; comentário: {comentar_depois_do_post(d, postado['id'], agora)}"


def _tentativas_do_antigo_hoje(momento):
    """Quantas vezes o robô tentou hoje o comentário do post antigo."""
    estado = ler_estado()
    return int(estado.get("antigo_tentativas") or 0) if estado.get("antigo_dia") == momento.strftime("%Y-%m-%d") else 0


def post_antigo_pendente(agora=None):
    """
    O post antigo que ganha o comentário do dia agora (P148 2), ou None: durante o dia (P161 1),
    nenhum ainda hoje, menos de TENTATIVAS_DO_PROPRIO tentativas hoje, a última há
    INTERVALO_DO_PROPRIO ou mais, e um post que pode ganhá-lo (interacoes.escolher_post_antigo).
    """
    momento = agora_br(agora)
    if not durante_o_dia(momento):
        return None
    if interacoes.antigos_hoje(momento) >= interacoes.POSTS_ANTIGOS_POR_DIA:
        return None
    if _tentativas_do_antigo_hoje(momento) >= interacoes.TENTATIVAS_DO_PROPRIO:
        return None
    estado = ler_estado()
    if (estado.get("antigo_em") or "") > _momento(momento - interacoes.INTERVALO_DO_PROPRIO):
        return None
    return interacoes.escolher_post_antigo(listar("postado"), momento)


def comentar_post_antigo(d, rascunho, agora=None):
    """
    O comentário do dia num post antigo (P148 2). O que não dá certo fica no registro e no caso,
    e volta mais tarde no mesmo dia (post_antigo_pendente).
    """
    momento = agora_br(agora)
    gravar_estado(antigo_dia=momento.strftime("%Y-%m-%d"), antigo_tentativas=_tentativas_do_antigo_hoje(momento) + 1,
                  antigo_em=_momento(agora))
    marca = interacoes.marca_do_post(rascunho["link_post"])
    try:
        resultado, _texto, _curtidas = comentar_no_post(d, rascunho, antigo=True, agora=agora)
    except Parada as e:
        registro_processos.registrar(REGISTRO, PROCESSO_DO_ANTIGO, "parou", e.motivo, ok=False, origem=marca,
                                     agora=agora)
        _guardar_caso(d, "post_antigo", "parou", e.motivo, ident=rascunho["id"], agora=agora)
        e.caso_guardado = True
        raise
    interacoes.guardar(marca, interacoes.TIPO_DO_ANTIGO, resultado, agora)
    registro_processos.registrar(REGISTRO, PROCESSO_DO_ANTIGO, resultado, ok=resultado == "comentado", origem=marca,
                                 agora=agora)
    registrar_tentativa("post_antigo", resultado, agora=agora)
    return ("post antigo: comentado e curtido" if resultado == "comentado"
            else "post antigo: comentário enviado sem aparecer na lista")


# --- Fazer Agora (P162 1) ---

# O botão Fazer Agora ⏩ (Robô Automático 🤖): o Rafael manda o robô fazer uma atividade do dia na
# próxima folga do celular, sem esperar a vez dela, como o Preparar 1 Agora: mesmo pausado, fora do
# horário ou com a conta suspensa (que não fecha nenhuma delas). Só o que ainda não saiu hoje até o
# limite do dia: a limpeza e a Saúde do Vídeo (1 vez), as leituras das respostas
# (LEITURAS_DAS_RESPOSTAS), o comentário no post antigo (POSTS_ANTIGOS_POR_DIA) e o feed
# (VIDEOS_NO_FEED_POR_DIA). O pedido fica no estado (fazer_agora) até a rodada que o faz; o de
# outro dia sai sem fazer, e com o celular desconectado os pedidos saem com o aviso. Escolha do
# Rafael (06/11, P162 1): DECISOES.md, Shopee Vídeo.
ATIVIDADES_DO_FAZER_AGORA = {
    "limpeza": ("Limpeza dos Favoritos", "descurtir"),
    "saude": ("Saúde do Vídeo", "saude"),
    "respostas": ("Responder Comentários", "responder"),
    "post_antigo": ("Comentário no Post Antigo", "post_antigo"),
    "feed": ("Feed", "feed"),
}
PROCESSO_DO_FAZER_AGORA = "fazer agora"


def feitas_hoje(atividade, agora=None):
    """(feitas, limite) hoje da atividade do Fazer Agora."""
    momento = agora_br(agora)
    if atividade == "limpeza":
        return int(not descurtir_pendente(momento)), 1
    if atividade == "saude":
        return int((ler_estado().get("saude_lida_em") or "").startswith(momento.strftime("%Y-%m-%d"))), 1
    if atividade == "respostas":
        return min(leituras_de_hoje(momento), LEITURAS_DAS_RESPOSTAS), LEITURAS_DAS_RESPOSTAS
    if atividade == "post_antigo":
        limite = interacoes.POSTS_ANTIGOS_POR_DIA
        return min(interacoes.antigos_hoje(momento), limite), limite
    limite = interacoes.VIDEOS_NO_FEED_POR_DIA
    return limite - videos_do_feed_que_faltam(momento), limite


def _de_hoje(pedidos, agora=None):
    hoje = agora_br(agora).strftime("%Y-%m-%d")
    return [p for p in pedidos or [] if p.get("atividade") in ATIVIDADES_DO_FAZER_AGORA
            and (p.get("pedido_em") or "").startswith(hoje)]


def pedidos_de_agora(agora=None):
    """Os pedidos do Fazer Agora de hoje que esperam a folga do celular, na ordem em que o Rafael pediu."""
    return _de_hoje(ler_estado().get("fazer_agora"), agora)


def pedir_agora(atividade, agora=None):
    """
    O Rafael tocou numa atividade do Fazer Agora: (pedido, feitas, limite). A que já saiu hoje até o
    limite do dia não é pedida, e a que já espera não é pedida de novo. O pedido fica no registro.
    """
    feitas, limite = feitas_hoje(atividade, agora)
    if feitas >= limite:
        return False, feitas, limite
    novo = []

    def anotar(dados):
        pedidos = _de_hoje(dados.get("fazer_agora"), agora)
        if not any(p["atividade"] == atividade for p in pedidos):
            pedidos.append({"atividade": atividade, "pedido_em": _momento(agora)})
            novo.append(True)
        dados["fazer_agora"] = pedidos

    db.atualizar_config(CHAVE_ESTADO, anotar)
    if novo:
        registro_processos.registrar(REGISTRO, PROCESSO_DO_FAZER_AGORA, "pedido",
                                     ATIVIDADES_DO_FAZER_AGORA[atividade][0], ok=None, agora=agora)
    return True, feitas, limite


def tirar_pedido(*atividades):
    """Os pedidos do Fazer Agora saem da lista (a rodada que os faz, ou o celular desconectado)."""
    db.atualizar_config(CHAVE_ESTADO, lambda dados: dados.update(fazer_agora=[
        p for p in dados.get("fazer_agora") or [] if p.get("atividade") not in atividades]))


def acao_do_pedido(atividade, agora=None):
    """
    A ação da rodada para o pedido do Fazer Agora, que sai da lista: (ação, id), ou (None, o porquê)
    quando ele não cabe mais (a atividade saiu antes, na vez dela, ou nenhum post pode ganhar o
    comentário do post antigo).
    """
    tirar_pedido(atividade)
    acao = ATIVIDADES_DO_FAZER_AGORA[atividade][1]
    feitas, limite = feitas_hoje(atividade, agora)
    if feitas >= limite:
        return None, "já tinha saído hoje, na vez dela"
    if atividade == "post_antigo":
        rascunho = interacoes.escolher_post_antigo(listar("postado"), agora_br(agora))
        if not rascunho:
            return None, "nenhum post dos últimos 30 dias pode ganhar o comentário agora"
        return acao, rascunho["id"]
    return acao, None


# --- A rodada ---

# A pausa que o robô faz sozinho quando perde o celular (robo_pausa_motivo); o painel a
# mostra diferente da pausa do botão.
MOTIVO_DA_DESCONEXAO = "celular desconectado"
# O caminho de volta ao automático, com o botão onde ele está no painel (Robô Automático 🤖) e
# o pareamento para quando a depuração já está ligada e o adb não conecta.
COMO_RETOMAR = ("no Motorola, em Opções do desenvolvedor, deixe a Depuração por Wi-Fi ligada (se ela já estiver "
                "ligada, desligue e ligue de novo) e, no bot, toque em Shopee Vídeo 🎬 → Robô Automático 🤖 → "
                "Retomar Postagem ▶️. Eu acho o celular sozinho. Se ainda não der, pareie de novo em Robô "
                "Automático 🤖 → Celular do Robô 📱 → Parear Celular 🔗 e deixe ligada, nas Opções do "
                f"desenvolvedor, a opção {celular_robo.OPCAO_DO_PRAZO}.")
# Com o pareamento vencido, ligar e desligar a depuração não adianta: só parear de novo.
COMO_RETOMAR_PAREANDO = (f"{celular_robo.COMO_PAREAR}. Depois, no bot, toque em Shopee Vídeo 🎬 → Robô "
                         "Automático 🤖 → Retomar Postagem ▶️.")


def pausar_por_desconexao(motivo):
    """
    Sem o celular, a Postagem pausa sozinha (o botão vira Retomar Postagem ▶️) e o modo
    assistente volta a mandar as postagens no privado, para o Rafael postar à mão.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    db.atualizar_config(CHAVE_CONFIG, lambda dados: dados.update(robo_pausado=True,
                                                                robo_pausa_motivo=MOTIVO_DA_DESCONEXAO))
    logger.warning(f"⚠️ [Robô Shopee Vídeo] Celular desconectado ({motivo}): Postagem pausada.")
    como = COMO_RETOMAR_PAREANDO if celular_robo.pede_pareamento(motivo) else COMO_RETOMAR
    avisar(f"📱 Robô da Shopee Vídeo: perdi a conexão com o celular guardado ({motivo}). Pausei a Postagem, "
           "e o modo assistente volta a mandar as postagens aqui no privado para você postar à mão.\n\n"
           f"Para voltar ao automático: {como}")


def rodada(treino=False, preparar=False, d=None, agora=None, saude=False, postar=None, fazer=False):
    """
    Uma rodada. treino=True é o botão Testar Caminho 🧭, preparar=True o Preparar 1
    Agora ⚡, saude=True o Gerar Apelação ⚖️ (Relatório Geral 📊 → Saúde da Shopee
    Vídeo 🩺), postar=ID o Postar Agora 🚀 (Aprovados para Postar ⏳, P138) e o pedido do Fazer
    Agora ⏩ que espera (P162 1; fazer=True: só ele): rodam na hora, mesmo pausado ou fora do
    horário (o Rafael pediu agora), e o rascunho do Preparar 1 Agora é a mais do plano do dia. Com a conta suspensa, a única coisa que o robô faz no
    celular é ler a Saúde do Vídeo (uma vez por dia, ou pelo botão). Devolve o que
    aconteceu, numa frase. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    # O painel interrompe a rodada em MAXIMO_DA_RODADA contados daqui (o Preparar 1 Agora mede o
    # tempo que sobra para outro vídeo a partir deste começo).
    comeco = time.monotonic()
    religar_a_pausa_sem_hora()
    config = ler_config()
    pedido_de_post = postar is not None
    pedidos = [] if treino or preparar or saude or pedido_de_post else pedidos_de_agora(agora)
    if fazer and not pedidos:
        return "nada a fazer agora"
    na_hora = treino or preparar or saude or pedido_de_post or bool(pedidos)
    if not na_hora:
        if config["robo_pausado"]:
            # Pausa do Rafael: os horários que passam nela são pulados. Pausa sozinha, por
            # desconexão: ficam, e na volta do celular contam como um só, como com o robô fora
            # do ar. Escolha do Rafael (24/10, P16): DECISOES.md, Shopee Vídeo.
            if config.get("robo_pausa_motivo") != MOTIVO_DA_DESCONEXAO:
                consumir_horarios(config, agora, pular=True)
            return "pausado"
        if suspensa(config, agora):
            # Os horários de rascunho que passam na suspensão são pulados, como pausado: o
            # preparo e a postagem esperam o fim (o_que_fazer), e o resto segue. O treino da
            # segunda fica para logo depois do fim.
            consumir_horarios(config, agora, pular=True)
            adiar_treino_da_suspensao(agora)
        if not no_horario(config, agora):
            return "fora do Horário do Robô"
    elif suspensa(config, agora) and not saude and not pedidos:
        ate = quando_acaba(suspenso_ate(config))
        feito = ("preparei o rascunho" if preparar else "postei o rascunho que você pediu" if pedido_de_post
                 else "testei o caminho")
        avisar(f"⛔ Robô da Shopee Vídeo: não {feito}. A conta "
               f"de Shopee Vídeo está suspensa pela Shopee até {ate}, e até lá o Postar vídeo não abre: o "
               "robô não prepara, não posta e não testa o caminho (o resto continua).")
        return f"conta suspensa até {ate}"
    if d is None:
        if av.tela_aberta():
            if not na_hora:
                anotar_rodada_sem_limpeza("a tela do celular aberta no privado", agora)
            return _resposta(preparar, "a tela do celular está aberta no privado do Rafael", pedido_de_post)
        if not celular_robo.conectado():
            ok, motivo = celular_robo.reconectar_sozinho()
            if not ok and not na_hora and suspensa(config, agora):
                # Na suspensão o Rafael pode tirar o Motorola do carregador: o celular fora é
                # esperado, e o robô não pausa; só a falha do servidor vira aviso, depois de 30 min
                # (alertas.py, P155 1). No fim dela, sem o celular, pausa e
                # avisa como sempre. Pedido do Rafael: DECISOES.md, Shopee Vídeo.
                anotar_limpeza_sem_celular(agora)
                return f"conta suspensa até {quando_acaba(suspenso_ate(config))}; celular fora (esperado)"
            if not ok:
                if not na_hora:
                    pausar_por_desconexao(motivo)
                registrar_tentativa("rodada", "parou", f"celular desconectado ({motivo})", agora=agora)
                if pedidos:
                    # Sem o celular não há folga para esperar: os pedidos saem, com o aviso (P162 1).
                    tirar_pedido(*(p["atividade"] for p in pedidos))
                    nomes = ", ".join(ATIVIDADES_DO_FAZER_AGORA[p["atividade"]][0] for p in pedidos)
                    avisar(f"⏩ Robô da Shopee Vídeo: não fiz o que você pediu no Fazer Agora ({nomes}): o celular "
                           f"do robô está desconectado ({motivo}). Peça de novo quando ele voltar.")
                return _resposta(preparar, f"celular desconectado ({motivo})", pedido_de_post)
        # De hora em hora, o prazo do pareamento no Motorola: sem a opção que o desliga, o
        # Android corta o pareamento em 7 dias, e o alertas.py avisa o Rafael antes.
        # Pedido do Rafael: DECISOES.md, Shopee Vídeo.
        try:
            celular_robo.anotar_prazo(agora=agora)
        except Exception as e:
            logger.warning(f"⚠️ [Robô Shopee Vídeo] Prazo do pareamento não lido: {type(e).__name__}")
    with celular_robo.trava() as livre:
        if not livre:
            if not na_hora:
                anotar_rodada_sem_limpeza("o celular com o explorar", agora)
            return _resposta(preparar, "o explorar está tocando no celular", pedido_de_post)
        # Dentro da trava, nenhum preparo está rodando: o "preparando" antigo é de uma rodada morta.
        soltar_preparos_interrompidos(agora)
        pedida = None
        if treino:
            acao, ident = "treino", None
        elif preparar:
            acao, ident = "rascunho", None
        elif saude:
            acao, ident = "saude", None
        elif pedido_de_post:
            # O Postar Agora 🚀 vale a qualquer hora e sem esperar os 30 min do último post (P138).
            rascunho = pegar(postar)
            if not rascunho or rascunho["estado"] != "aprovado":
                return _resposta(False, "ele não está mais aprovado esperando a hora de ir ao ar", True)
            registro_processos.registrar(REGISTRO, PROCESSO_DO_POSTAR_AGORA, "pedido", ok=None, agora=agora)
            acao, ident = "postar", rascunho["id"]
        elif pedidos:
            # O pedido do Fazer Agora mais antigo (P162 1); os outros ficam para as rodadas seguintes.
            pedida = pedidos[0]["atividade"]
            nome = ATIVIDADES_DO_FAZER_AGORA[pedida][0]
            acao, ident = acao_do_pedido(pedida, agora)
            if not acao:
                registro_processos.registrar(REGISTRO, PROCESSO_DO_FAZER_AGORA, "não saiu", ident, ok=None,
                                             agora=agora)
                avisar(f"⏩ Robô da Shopee Vídeo: {nome}, do Fazer Agora: não fiz, porque {ident}.")
                return f"fazer agora: {ident}"
            registro_processos.registrar(REGISTRO, PROCESSO_DO_FAZER_AGORA, "na rodada", nome, ok=None, agora=agora)
        else:
            acao, ident = o_que_fazer(config, agora) or (None, None)
        if not acao:
            return "nada a fazer agora"
        if preparar:
            # O rascunho pedido no botão vale a qualquer hora: o checkup o separa do preparo do plano.
            registro_processos.registrar(REGISTRO, PROCESSO_DO_BOTAO, "pedido", ok=None, agora=agora)
        # O celular anota as últimas ações, que o caso da falha guarda (casos_robo).
        d = casos_robo.com_historico(d or ps.conectar(celular=True))
        try:
            resultado = _agir(d, acao, ident, preparar, config, agora,
                              pedido=(saude or pedido_de_post or pedida == "saude") and na_hora, comeco=comeco)
            if pedida and pedida != "saude":
                # A Saúde pedida já manda o resumo dela; as outras dizem aqui como foi.
                avisar(f"⏩ Robô da Shopee Vídeo: {ATIVIDADES_DO_FAZER_AGORA[pedida][0]}, do Fazer Agora: "
                       f"{resultado}.")
            if acao != "saude" and saude_pedida_pela_notificacao(agora):
                _ler_saude_junto(d, agora)
            return resultado
        finally:
            # Só a rodada que tocou no celular pode ter deixado um vídeo aberto.
            if d.acoes:
                deixar_sem_video(d, agora)
            faxina_dos_arquivos(d)


# Vídeo deixado aberto no celular do robô roda em laço, e cada volta pode contar como uma
# visualização a mais: no vídeo do Rafael das 16:31 de 02/11, o vídeo que o robô postou às 15:59
# ainda rodava no Motorola meia hora depois (o link do post é copiado com o vídeo aberto), e o feed
# fica no vídeo do outro criador. No fim de cada rodada que mexeu no celular, o robô volta à barra
# de baixo do app e abre o Eu, onde nenhum vídeo toca. Pedido do Rafael: DECISOES.md, Shopee Vídeo.
PROCESSO_DO_FIM_DA_RODADA = "celular no fim da rodada"


def deixar_sem_video(d, agora=None):
    """
    No fim da rodada, o app no Eu (a barra de baixo, sem vídeo tocando). Na Verificação não toca
    em nada; o que falha fica no registro e no log, e nunca muda o resultado da rodada.
    """
    try:
        voltar(d, "Eu")
        tocar(d, "Eu", 3)
        registro_processos.registrar(REGISTRO, PROCESSO_DO_FIM_DA_RODADA, "no Eu", ok=True, agora=agora)
    except Verificacao:
        registro_processos.registrar(REGISTRO, PROCESSO_DO_FIM_DA_RODADA, "parado na Verificação", ok=None,
                                     agora=agora)
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] O celular não voltou ao Eu no fim da rodada: {type(e).__name__}")
        registro_processos.registrar(REGISTRO, PROCESSO_DO_FIM_DA_RODADA, "não voltou ao Eu", type(e).__name__,
                                     ok=False, agora=agora)


def _agir(d, acao, ident, preparar, config, agora, pedido=False, comeco=None):
    """
    A ação da rodada no celular, já dentro da trava, com o que fazer quando ela para.
    pedido=True: o Rafael pediu a Saúde do Vídeo pelo botão Gerar Apelação ⚖️ e espera a resposta.
    comeco: o time.monotonic() do começo da rodada (preparar_o_pedido).
    """
    # O rascunho entra no histórico pelo preparar_rascunho, que sabe qual vídeo tentou.
    produto = ", ".join((pegar(ident) or {}).get("produtos") or []) if ident else ""
    try:
        # Com a tela apagada, nada começa: nem a escolha do vídeo, nem a IA, nem um toque.
        conferir_a_tela_acesa()
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
            # De passagem, as visualizações dos vídeos na grade do Perfil (P76).
            _anotar_visualizacoes_junto(d, agora)
            return resultado
        if acao == "descurtir":
            # A lista só fica limpa se este descurtir chegar ao fim (P27).
            if not na_hora_do_descurtir(agora):
                _contar_limpeza_fora_da_hora(agora)
            gravar_estado(descurtir_em=_momento(agora), descurtir_continuar=False, favoritos_limpos=False)
            resultado = descurtir_tudo(d, agora)
            registrar_tentativa("descurtir", "descurtido", agora=agora)
            return resultado
        if acao == "responder":
            # A continuação da leitura que parou no limite da rodada não é uma leitura a mais (P161 1).
            if not ler_estado().get("respostas_continuar"):
                contar_leitura(agora)
            gravar_estado(respostas_continuar=False)
            return responder_comentarios(d, agora)
        if acao == "feed":
            return interagir_no_feed(d, agora)
        if acao in ("comentar_post", "post_antigo"):
            rascunho = pegar(ident)
            if acao == "comentar_post" and rascunho and not rascunho["link_post"] and rascunho["busca_do_link"]:
                return buscar_o_link_de_novo(d, rascunho, agora)
            if not rascunho or not rascunho["link_post"]:
                return f"{acao}: o post não está mais no banco"
            if acao == "post_antigo":
                return comentar_post_antigo(d, rascunho, agora)
            return f"comentário no post: {tentar_o_comentario_do_post(d, rascunho, agora)}"
        if acao == "apagar":
            resultado = apagar_do_app(d, pegar(ident))
            registrar_tentativa("apagar", "apagado", produto=produto, agora=agora)
            return resultado
        if acao == "postar":
            resultado = publicar(d, pegar(ident), agora)
            registrar_tentativa("postar", "postado", produto=produto, agora=agora)
            return resultado
        if acao == "refazer":
            resultado = refazer_no_app(d, pegar(ident), agora)
            registrar_tentativa("refazer", "refeito", produto=produto, agora=agora)
            return resultado
        if not preparar:
            _em_preparo(config, agora, True)
        try:
            resultado = (preparar_o_pedido(d, config, agora, comeco) if preparar
                         else preparar_rascunho(d, config, agora))
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
        # O rascunho que parou no preparo já anotou o caso e a tentativa (preparar_rascunho); o que
        # parou antes de começar, não. Antes de começar, o caso vai sem a tela: nada lê o celular.
        anotar = acao != "rascunho" or e.antes_de_comecar
        if anotar and not e.caso_guardado:
            _guardar_caso(None if e.antes_de_comecar else d, acao, "parou", e.motivo, ident=ident, agora=agora)
        if acao == "postar":
            _nao_saiu_o_post(ident, e.motivo, pedido)
        elif acao == "refazer":
            _nao_saiu_o_refazer(ident, e.motivo)
        elif acao == "apagar":
            # Não insiste: o Rafael decide de novo pelo botão.
            atualizar(ident, estado="rascunho", postar_em=None, motivo=e.motivo)
            avisar(f"⚠️ Robô da Shopee Vídeo: não consegui apagar o rascunho ({e.motivo}). Não toquei em mais "
                   "nada; ele voltou para Rascunhos do Robô 📝.")
        if anotar:
            registrar_tentativa(acao, "parou", e.motivo, produto, agora)
        if acao == "saude" and pedido:
            avisar(f"⚠️ Robô da Shopee Vídeo: não consegui ler a Saúde do Vídeo ({e.motivo}). Toque de novo em "
                   "Gerar Apelação ⚖️ daqui a pouco.")
        _limpeza_de_novo(acao)
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
        if acao == "postar":
            _nao_saiu_o_post(ident, f"erro inesperado ({type(e).__name__})", pedido)
        elif acao == "refazer":
            _nao_saiu_o_refazer(ident, f"erro inesperado ({type(e).__name__})")
        _limpeza_de_novo(acao)
        _repetir_depois(acao, preparar, config, agora, getattr(e, "id_video", None))
        _avisar_que_nao_saiu(acao, preparar, config, agora)
        return _resposta(preparar, f"{acao}: erro {type(e).__name__}")


def _limpeza_de_novo(acao):
    """
    A limpeza das 4h que parou no meio (a tela que não abriu, o app travado, um erro) tenta de
    novo na rodada seguinte, ainda na hora dela, como a que passou das voltas: sem isso, ela só
    voltava no dia seguinte, e as curtidas acumulavam em Meus favoritos (vídeo do Rafael das 20:17
    de 02/11: DECISOES.md, Shopee Vídeo).
    """
    if acao == "descurtir":
        gravar_estado(descurtir_continuar=True)


# O aprovado que não sai na hora de postar (a tela que não carregou, o app travado) continua
# aprovado: o robô tenta de novo nas rodadas seguintes, conferindo tudo antes de tocar em
# Postar, e só depois de TENTATIVAS_DE_POSTAR vezes ele volta para o Rafael aprovar de novo.
# Escolha do Rafael (30/10, P99): DECISOES.md, Shopee Vídeo.
TENTATIVAS_DE_POSTAR = 3


# O Postar Agora 🚀 (Aprovados para Postar ⏳): o aprovado vai ao ar na hora, a qualquer hora e sem
# esperar os 30 min do último post; o que não sai continua aprovado, sem gastar nenhuma das
# TENTATIVAS_DE_POSTAR das rodadas. Escolha do Rafael (03/11, P138): DECISOES.md, Shopee Vídeo.
PROCESSO_DO_POSTAR_AGORA = "postar agora"


def _nao_saiu_o_post(ident, motivo, pedido=False):
    """
    Conta a vez em que o aprovado não saiu e avisa: tenta de novo, ou volta para o Rafael na última.
    O pedido no Postar Agora 🚀 não conta: o aprovado fica como estava.
    """
    if pedido:
        # Volta para Aprovados para Postar ⏳ (postando_agora).
        atualizar(ident, motivo=motivo, postar_agora_em=None)
        avisar(f"⚠️ Robô da Shopee Vídeo: não consegui postar agora o rascunho que você pediu ({motivo}). Não "
               "toquei em mais nada. Ele continua aprovado, em Aprovados para Postar ⏳: vai ao ar na hora "
               "marcada, ou toque de novo em Postar Agora 🚀.")
        return
    falhas = int((pegar(ident) or {}).get("falhas_ao_postar") or 0) + 1
    if falhas < TENTATIVAS_DE_POSTAR:
        atualizar(ident, falhas_ao_postar=str(falhas), motivo=motivo)
        avisar(f"⚠️ Robô da Shopee Vídeo: não consegui postar o rascunho aprovado ({motivo}). Não toquei em mais "
               f"nada. Ele continua aprovado: tento de novo na próxima rodada (tentativa {falhas + 1} de "
               f"{TENTATIVAS_DE_POSTAR}).")
        return
    atualizar(ident, estado="rascunho", postar_em=None, falhas_ao_postar="0", motivo=motivo)
    avisar(f"⚠️ Robô da Shopee Vídeo: tentei postar o rascunho aprovado {TENTATIVAS_DE_POSTAR} vezes e não "
           f"consegui (da última vez: {motivo}). Não toquei em mais nada; ele voltou para Rascunhos do Robô 📝 "
           "para você decidir de novo.")


def _nao_saiu_o_refazer(ident, motivo):
    """
    O rascunho editado que não foi refeito no app (P192 1): a versão de antes continua no celular, sem mudança.
    Tenta de novo nas rodadas seguintes, até TENTATIVAS_DE_POSTAR vezes; depois volta para o Rafael, com a nova
    versão guardada (ele aprova de novo ou fica com o vídeo de antes).
    """
    rascunho = pegar(ident)
    if not rascunho or rascunho["estado"] != "refazer":
        return
    falhas = int(rascunho.get("falhas_ao_postar") or 0) + 1
    if falhas < TENTATIVAS_DE_POSTAR:
        atualizar(ident, falhas_ao_postar=str(falhas), motivo=motivo)
        avisar(f"⚠️ Robô da Shopee Vídeo: não consegui refazer no celular o rascunho que você editou ({motivo}). O "
               "de antes continua no celular, sem mudança. Tento de novo na próxima rodada (tentativa "
               f"{falhas + 1} de {TENTATIVAS_DE_POSTAR}).")
        return
    atualizar(ident, estado="rascunho", aprovado_em=None, falhas_ao_postar="0", motivo=motivo)
    avisar(f"⚠️ Robô da Shopee Vídeo: tentei {TENTATIVAS_DE_POSTAR} vezes refazer no celular o rascunho que você "
           f"editou e não consegui (da última vez: {motivo}). O de antes continua no celular. Ele voltou para "
           "Rascunhos do Robô 📝 com a nova versão guardada: aprove de novo para eu tentar outra vez, ou fique com "
           "o vídeo de antes.")


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
    tentativas por vídeo, até VIDEOS_POR_HORARIO vídeos). O Preparar 1 Agora não volta numa
    rodada seguinte: no mesmo toque ele já passou aos próximos vídeos (preparar_o_pedido, P133).
    A Verificação da Shopee não passa por aqui: ela para tudo. Decisão do Rafael: DECISOES.md,
    Shopee Vídeo.
    """
    if acao == "rascunho" and not preparar:
        marcar_para_repetir(config, agora, video, do_video)


def _resposta(preparar, resultado, postar=False):
    """
    No Preparar 1 Agora e no Postar Agora 🚀 o Rafael espera a resposta: o que impediu vai
    também no privado.
    """
    if preparar:
        avisar(f"⚠️ Robô da Shopee Vídeo: não preparei o rascunho que você pediu ({resultado}).")
    elif postar:
        avisar(f"⚠️ Robô da Shopee Vídeo: não postei agora o rascunho que você pediu ({resultado}). Se ele "
               "continua aprovado, ele volta para Aprovados para Postar ⏳: vai ao ar na hora marcada, ou toque de "
               "novo em Postar Agora 🚀.")
    return resultado


def _primeiro_quadro(arquivo):
    """O 1º quadro do vídeo (a capa que o app usa na grade) num PNG ao lado dos rascunhos; None quando não sai."""
    if not arquivo or not os.path.exists(arquivo):
        return None
    destino = os.path.join(PASTA_RASCUNHOS, "capa_para_conferir.png")
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", arquivo, "-frames:v", "1", destino],
                       capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return destino if os.path.exists(destino) else None


def print_do_rascunho(desde=None):
    """
    Manda no privado do Rafael o print da tela final do rascunho mais novo esperando a aprovação,
    feito desde `desde` ("AAAA-MM-DD HH:MM"), e o 1º quadro do vídeo dele, a capa que vai para a
    grade: para conferir a capa sem abrir Rascunhos do Robô 📝 (pedido do Rafael, 02/11). Não mexe
    no celular. Devolve o que aconteceu numa frase só com o horário (vai no log do avisar.yml).
    """
    rascunhos = [r for r in listar("rascunho") if not desde or (r["criado_em"] or "") >= desde]
    if not rascunhos:
        return "nenhum rascunho esperando a aprovação" + (f" feito desde {desde[11:16]}" if desde else "")
    rascunho = rascunhos[-1]
    hora = (rascunho["criado_em"] or "")[11:16]
    fotos = 0
    if rascunho["print"] and os.path.exists(rascunho["print"]):
        fotos += bool(avisar_foto(rascunho["print"], f"🖼️ Rascunho das {hora}: o print da tela final, com a capa como o "
                                                     "app mostra. Ele espera a sua aprovação em Rascunhos do Robô 📝."))
    quadro = _primeiro_quadro(rascunho["arquivo"])
    if quadro:
        try:
            fotos += bool(avisar_foto(quadro, f"🖼️ Rascunho das {hora}: o 1º quadro do vídeo, a capa que vai para a "
                                              "grade do perfil."))
        finally:
            os.remove(quadro)
    return f"rascunho das {hora}: {fotos} foto(s) mandada(s)"


def main(argumentos):
    logging.basicConfig(level=os.getenv("NIVEL_LOG", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    if "--print-do-rascunho" in argumentos:
        resto = argumentos[argumentos.index("--print-do-rascunho") + 1:]
        print(print_do_rascunho(resto[0].replace("T", " ") if resto and resto[0].strip() else None))
        return 0
    treino, preparar, saude = "--treino" in argumentos, "--preparar" in argumentos, "--saude" in argumentos
    fazer = "--fazer" in argumentos
    postar = None
    if "--postar" in argumentos:
        resto = argumentos[argumentos.index("--postar") + 1:]
        if not resto or not resto[0].isdigit():
            print(__doc__)
            return 2
        postar = int(resto[0])
    if not treino and not preparar and not saude and not fazer and postar is None and "--rodada" not in argumentos:
        print(__doc__)
        return 2
    resultado = rodada(treino=treino, preparar=preparar, saude=saude, postar=postar, fazer=fazer)
    logger.info(f"🤖 [Robô Shopee Vídeo] {resultado}.")
    # O resultado fica no banco com o texto mascarado (sem nome de produto), para o
    # diagnóstico do servidor, que é público, mostrar como foi a última rodada.
    gravar_estado(ultima_rodada=ps.mascarar(resultado), ultima_rodada_em=_momento())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

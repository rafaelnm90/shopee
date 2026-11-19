#!/usr/bin/env python3
"""
Vídeos feitos por IA no Google Flow, no celular do robô da Shopee Vídeo, com a conta Pro do
Rafael. Primeiro o teste que ele escolheu (P229 1, 15/11/2026): 3 vídeos do mesmo produto, um em
cada modelo do Flow, só no privado dele, para ele escolher o modelo. Depois dele, a produção (P232
1, 15/11/2026): 1 vídeo por dia no Omni 1.2 Flash, o mais avançado, que vira um rascunho do robô
(robo_shopee_video escolhe o produto entre os produtos em alta da API de afiliado, P234 1, e chama
producao_no_celular na rodada dele; o rascunho leva a nossa edição, os produtos e o Rótulo de IA
ligado, e o Rafael aprova em Rascunhos do Robô 📝). A IA vê a foto do anúncio e o nome do produto e
escreve o pedido do vídeo (a cena, o movimento da câmera e a luz), sempre com o produto igual ao da
foto; o Flow gera o vídeo a partir da foto. Desde a P247 1 (17/11/2026), o vídeo da produção (o do dia e
o do Preparar 1 Agora ⚡ → De IA ✨) é o de 16 s com uma pessoa vendendo o produto, como a amostra de 16 s
(abaixo), e a fala que o servidor ouve vai no rascunho. Desde a P256 2 (19/11/2026), ele pode ser também o
unboxing (as mãos abrindo a caixa com o produto, sem rosto e sem fala), que a IA escolhe pelo produto, nunca dois
seguidos.

O caminho no app (mapeado no Motorola em 15/11/2026, sem gerar nada; as telas estão no
roteiro_robo_shopee_video.md): o ícone "Flow" → o projeto do robô na lista ("Shopee Video";
sem ele, o teste para, sem criar outro) →
Criar → Vídeo → + (Adicionar mídia) → Imagens → a foto no seletor do Android ("Item Foto ...")
→ Adicionar → a caixa "O que você quer fazer?" → o modelo (9:16, 720p, x1, 8 s e o modelo, com
o custo em créditos) → Gerar. Depois do Gerar (mapeado no 1º vídeo, 15/11/2026): o vídeo novo
aparece no projeto como "N% Gerando…" e, pronto, com o título que o Flow dá; o teste abre o
mais novo pelo filtro Vídeos, confere no título que ele é do modelo do teste, toca em Mais opções
→ Baixar (na janela da resolução, o 1080p quando ele vem sem custo; sem isso, o tamanho
original) e traz o arquivo do celular para o servidor. Com o celular já solto, a IA confere o
produto do vídeo com a foto do anúncio, e o vídeo vai ao privado do Rafael com o modelo, o
custo, o produto, a cena e a conferência. O vídeo que não fica pronto ou não sai num teste é
baixado e mandado no próximo, sem gerar outro.

As amostras (P236 1, 16/11/2026): vídeos de teste como os da produção (o produto pela lista da
API de afiliado e o Omni 1.2 Flash), um por vez, só no privado do Rafael, para ele ver como os
vídeos de IA estão ficando; não viram rascunho nem post. A amostra de 16 s (P246 1, 16/11/2026):
uma pessoa vendendo o produto do começo ao fim (o gancho, as vantagens de perto e a chamada), nos 8 s
gerados pela foto e em mais 8 s do Estender do Flow, que continua a mesma cena (no_flow_longo); o
Rafael gostou, e ela virou o padrão do vídeo de IA (P247 1). Contra as alucinações da 1ª (P248 1, 17/11/2026), a
pessoa só segura, vira e aponta o produto, os 16 s ficam no mesmo lugar e enquadramento, a fala é
curta (PEDIDO_DO_VENDEDOR), e o servidor ouve o vídeo pronto e compara com a fala pedida: a embolada
ou cortada vai na legenda (conferir_a_fala). A amostra pode repetir o produto da anterior (--mesmo). A amostra
da fala do começo ao fim (P255 1, 19/11/2026; --fala-inteira): duas frases curtas em cada parte, faladas do 1º
segundo até por volta dos 7 s (PEDIDO_DO_VENDEDOR_FALANDO), e o servidor corta o parado que sobrar (o silêncio de
mais de 1 s, com um zoom leve depois de cada corte, cortar_o_parado); vão ao privado o vídeo cortado e o original.

Usado pelo workflow video_ia.yml (acao flow, flow-sem-gerar, amostra, amostra-16s, amostra-16s-mesmo ou
amostra-16s-fala-inteira). O
log do Actions é público: saem só estados, modelos e números; o produto e o pedido ficam no banco, e o
vídeo, no privado.

    python3 flow_shopee_video.py teste              # o próximo passo do teste (um modelo por vez)
    python3 flow_shopee_video.py teste --sem-gerar  # tudo até o Gerar, sem tocar nele
    python3 flow_shopee_video.py amostra            # a próxima amostra do vídeo de IA (P236 1)
    python3 flow_shopee_video.py amostra --longa    # a amostra do vídeo de 16 s, com o Estender (P246 1)
    python3 flow_shopee_video.py amostra --longa --mesmo  # a de 16 s com o produto da anterior (P248 1)
    python3 flow_shopee_video.py amostra --longa --fala-inteira  # a de 16 s falando o tempo todo, sem o parado (P255 1)
"""
import asyncio
import difflib
import io
import json
import logging
import os
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime

import api_gemini
import api_shopee
import assistente_shopee_video as assistente
import avisar_rafael
import casos_robo
import celular_robo
import db
import postador_shopee_video as ps
import videos
from fuso import fuso_horario

PACOTE = "com.google.android.apps.labs.whisk"
PACOTE_DO_SELETOR = "com.google.android.providers.media.module"
CHAVE = "flow_shopee_video"
PASTA = os.path.join(os.path.expanduser("~"), "shopee_video", "flow")
# Os modelos de vídeo do Flow na conta do Rafael e o custo de cada vídeo de 8 s em 720p,
# lidos no app em 15/11/2026. O teste vai do mais barato ao mais caro (46 créditos, dentro
# dos 50 grátis do dia): o 1º vídeo é o que mostra as telas depois do Gerar.
MODELOS_DO_TESTE = (("Veo 3.1 - Lite", 10), ("Omni 1.1 Flash", 12), ("Omni 1.2 Flash", 24))
# A produção: depois dos 3 vídeos do teste, o Rafael escolheu o mais avançado para 1 vídeo de IA por dia, que vira
# um rascunho do robô, no lugar de um da fonte (P232 1), de 16 s com uma pessoa vendendo o produto (P247 1): 24
# créditos dos 8 s gerados e mais CUSTO_DO_ESTENDER do Estender (CUSTO_DA_PRODUCAO); o dia tem CREDITOS_GRATIS_DO_DIA.
# O do robô é 1 por dia; o Preparar 1 Agora ⚡ → De IA ✨ faz outros, até 5 no dia contando o do robô (P243), e o
# que passa dos grátis sai do plano. Escolhas do Rafael (15/11, 16/11 e 17/11/2026): DECISOES.md, Shopee Vídeo.
MODELO_DA_PRODUCAO = ("Omni 1.2 Flash", 24)
CREDITOS_GRATIS_DO_DIA = 50
# A produção que para antes do Gerar (sem gastar crédito) tenta de novo no mesmo dia, até estas vezes.
TENTATIVAS_ANTES_DO_GERAR = 2
# O vídeo pronto que não vira rascunho nestas tentativas (o celular, o app, nada do vídeo) sai, e o robô segue com os
# vídeos da fonte.
TENTATIVAS_DO_RASCUNHO = 6
# Quantos dos próximos vídeos da fonte o teste tenta até a IA achar a foto boa para o vídeo.
PRODUTOS_TENTADOS = 10
ESPERA_DA_TELA = 20
PAUSA_DA_LEITURA = 1.5
# Depois do Gerar, o quadrado do vídeo novo aparece no projeto com "N% Gerando…" e, pronto, vira o
# vídeo com o título que o Flow dá ("…, 1 item"). O Veo 3.1 - Lite ficou pronto em menos de 1 min
# (15/11/2026). O teste espera até ESPERA_DA_GERACAO e guarda a tela a cada INTERVALO_DOS_CASOS; o
# que não fica pronto nesse tempo é baixado no próximo teste. Sem o "Gerando…" logo depois do
# Gerar, o Flow não gerou (a tela fica guardada para o Claude ver o porquê).
ESPERA_DA_GERACAO = 10 * 60
ESPERA_DO_GERANDO = 30
INTERVALO_DOS_CASOS = 60
GERANDO = re.compile(r"\bgerando\b", re.I)
# O "Gerando…" some de uma leitura da tela no meio da geração (15/11/2026, o Omni 1.2 Flash: o
# robô viu "pronto" aos 6 s e abriu o vídeo de antes). Pronto só depois de PRONTO_SEGUIDAS leituras
# seguidas do projeto sem ele.
PRONTO_SEGUIDAS = 3
ITEM_DO_PROJETO = re.compile(r",\s*\d+\s+(?:item|itens|items)\s*$", re.I)
# O vídeo aberto: o player ("Vídeo tocando, 1 de 1") e, no alto, o título com o nome, o modelo e a
# resolução, uma linha cada (mapeado em 15/11/2026).
VIDEO_ABERTO = re.compile(r"^v[íi]deo\b.*\b\d+ de \d+", re.I | re.S)
# O Baixar (Mais opções do vídeo aberto) guarda o arquivo numa destas pastas do celular. A marca é
# um arquivo vazio criado antes do toque: o vídeo baixado é o .mp4 mais novo que ela.
PASTAS_DO_BAIXAR = ("/sdcard/Download", "/sdcard/Movies", "/sdcard/DCIM", "/sdcard/Pictures")
MARCA_DO_BAIXAR = "/sdcard/Download/.flow_antes_do_baixar"
# O 1080p é o vídeo aumentado pelo Flow na hora do Baixar e pode levar uns minutos: o robô espera
# até ESPERA_DO_BAIXAR, mas segue assim que o arquivo para de crescer.
ESPERA_DO_BAIXAR = 5 * 60
# Depois do Baixar do menu, o tempo para a janela da resolução aparecer (sem ela, o download já
# começou) e, na janela, para a escolha ficar marcada.
ESPERA_DA_JANELA_DO_BAIXAR = 8
# Depois do Baixar da janela, o tempo para ela fechar (no 1080p, o Flow pode mostrar nela o andamento antes).
ESPERA_PARA_A_JANELA_FECHAR = 30
# Depois do toque na miniatura de uma versão, o tempo para o título do vídeo aberto mudar.
ESPERA_DA_VERSAO = 6
# O vídeo aberto com o player em "Falha ao carregar o vídeo" (visto em 16/11/2026, logo depois de o
# vídeo ficar pronto): o título com o modelo aparece, mas o vídeo não toca. O robô espera o player
# até ESPERA_DO_PLAYER e, sem ele, fecha o vídeo e o abre de novo depois de PAUSA_ANTES_DE_REABRIR,
# até ABERTURAS_DO_VIDEO vezes; sem carregar, Parada (o vídeo continua gerado: a próxima vez baixa).
FALHA_NO_PLAYER = re.compile(r"falha ao carregar", re.I)
ESPERA_DO_PLAYER = 10
PAUSA_ANTES_DE_REABRIR = 20
ABERTURAS_DO_VIDEO = 3
# O Estender (P246 1, mapeado no Motorola em 16/11/2026, sem gerar): embaixo do vídeo aberto, abre o painel "Qual é a
# próxima etapa?", com o vídeo em cima ("1 de 1"), a fita dos quadros com as alças (o trecho que continua; o robô não
# mexe nelas), a caixa do pedido, o + (Adicionar mídia), o botão da duração ("Estender 8s") e o Gerar, desligado com a
# caixa vazia. O robô escreve a continuação e só toca no Gerar com a caixa, os 8 s e o vídeo de uma versão só
# conferidos na tela. Os 8 s custam 24 créditos no Omni 1.2 Flash (6 s 18 e 10 s 30, vistos no celular do Rafael em
# 15/11). Depois do Gerar, o painel fecha em até ESPERA_DO_PAINEL s.
DURACAO_DO_ESTENDER = "Estender 8s"
CUSTO_DO_ESTENDER = 24
# O vídeo de IA da produção inteiro, os 8 s gerados e o Estender (P247 1).
CUSTO_DA_PRODUCAO = MODELO_DA_PRODUCAO[1] + CUSTO_DO_ESTENDER
ESPERA_DO_PAINEL = 20
# O Flow guarda a versão estendida no mesmo quadro do vídeo ("…, 2 itens"; aberto, "2 de 2", visto no celular do
# Rafael em 15/11). A versão baixada com DURACAO_ESTENDIDA s ou mais já tem os 16 s; a mais curta é só a continuação,
# e o robô baixa também a original e junta as duas no servidor (videos.juntar). Na espera do Estender, que o robô
# ainda não viu, a tela vai aos casos só nos primeiros CASOS_DO_ESTENDER minutos (para o Claude ver).
DURACAO_ESTENDIDA = 12
CASOS_DO_ESTENDER = 3
VERSOES_NO_QUADRO = re.compile(r",\s*(\d+)\s+(?:item|itens|items)\s*$", re.I)
# Logo depois do Gerar do Estender, o vídeo aberto mostra a continuação sendo gerada: "2 de 2", a porcentagem e
# "Gerando…" no lugar do player, com o Estender apagado (visto na amostra nº 5, 17/11/2026). Fechado antes disso, o
# Flow pode perder a continuação: o vídeo fica com uma versão só e nada é gerado (visto no 1º vídeo de IA de 16 s da
# produção, 17/11/2026). O robô só sai do vídeo (o Flow é aberto de novo, do zero, para a espera no projeto) com a
# continuação à vista, esperando até ESPERA_DA_CONTINUACAO s, e ainda PAUSA_DEPOIS_DA_CONTINUACAO s com ela à vista
# (nas amostras, que não a perderam, a tela guardada nesse momento dava esses segundos ao app antes de ele ser fechado).
ESPERA_DA_CONTINUACAO = 30
PAUSA_DEPOIS_DA_CONTINUACAO = 10
# Na espera do Estender no projeto, o quadro mais novo com uma versão só e nada sendo gerado por ESPERA_SEM_CONTINUACAO
# s seguidos: a continuação não está vindo, e a vez acaba sem esperar a ESPERA_DA_GERACAO inteira. No projeto, o quadro
# do vídeo que o Flow estende mostra a porcentagem (roteiro, 1ª amostra de 16 s, 17/11/2026): com ou sem o "Gerando…"
# escrito, ela conta como algo sendo gerado (porcentagem_no_projeto). Os 4 min dão folga ao Estender que demora mais
# que o da 1ª amostra (pouco mais de 1 min) e ainda acabam a vez de um vídeo que perdeu a continuação.
ESPERA_SEM_CONTINUACAO = 4 * 60
# A porcentagem do que o Flow está gerando, sozinha numa linha do quadro ("45%").
PORCENTAGEM = re.compile(r"^\s*\d{1,3}\s?%\s*$", re.M)
# O porquê da vez que acaba sem o vídeo de 16 s (no andamento, "espera"; o robô anota no registro).
ESPERA_DOS_8_S = "os 8 s sem ficar prontos"
ESPERA_DA_EXTENSAO = "a continuação sem ficar pronta"
SEM_CONTINUACAO = "a continuação não veio"
# A janela "Baixar vídeo" (mapeada em 15/11/2026) vem com o "720p Tamanho original" marcado; o
# "1080p Aumentar a resolução" fica livre no plano Pro e o 4K pede outro plano. O robô baixa no
# 1080p e só quando a linha dele não fala em plano nem em crédito, e a janela não fala em crédito;
# sem isso, no tamanho original. Nunca toca no 4K nem no plano. Pedido do Rafael (P229):
# DECISOES.md, Shopee Vídeo.
CUSTO_OU_PLANO = re.compile(r"cr[ée]dito|assin|plano|premium|ultra", re.I)
CREDITO = re.compile(r"cr[ée]dito", re.I)
# O botão da janela muda com a escolha: "Baixar" no tamanho original e "Aumentar resolução e
# baixar" no 1080p (visto no 1º Baixar no 1080p, 15/11/2026).
BOTAO_DO_BAIXAR = re.compile(r"(?:aumentar (?:a )?resolu[çc][ãa]o e )?baixar")
# Fora dessa janela, outra pergunta de tamanho depois do Baixar (ou uma permissão do Android) para
# o robô: ele não escolhe nada que não foi mapeado.
ESCOLHA_NO_BAIXAR = re.compile(r"1080p|\b4k\b|upscal|aumentar|ampliar|melhorad", re.I)
PACOTES_DE_PERMISSAO = ("com.android.permissioncontroller", "com.google.android.permissioncontroller")
# O projeto do robô no Flow: o Rafael o renomeou para "Shopee Video" (15/11/2026) e pediu que
# todos os vídeos fiquem só nele, para não bagunçar. Sem ele em lugar nenhum da lista (o Rafael
# pode tê-lo apagado), o robô cria outro com esse nome e o usa de padrão, no máximo um por dia.
# Pedido do Rafael (P229): DECISOES.md, Shopee Vídeo.
PROJETO_DO_ROBO = "Shopee Video"
# A lista do início põe o projeto novo no alto e empurra os outros para baixo: o robô rola até o
# fim (até a lista parar de andar, no máximo ROLADAS_DA_LISTA vezes) antes de dar o projeto por sumido,
# esperando cada tela da lista até ESPERA_DA_LISTA s.
ROLADAS_DA_LISTA = 10
ESPERA_DA_LISTA = 8
# O alto do projeto aberto (mapeado em 15/11/2026, entre y 152 e 278): o título, o Voltar e o Mais
# opções; no Renomear, o campo do nome com o ✓ e o ✕ ao lado. O menu do Mais opções tem Renomear,
# Grade, Ver lixeira e Excluir projeto: o robô só toca no Renomear, nunca no Excluir nem na lixeira.
ALTO_DO_PROJETO = 330
PROIBIDO_NO_MENU_DO_PROJETO = re.compile(r"excluir|lixeira", re.I)
CUSTO_NA_TELA = re.compile(r"(\d+)\s+créditos de IA", re.I)
# O saldo do Flow (pedido do Rafael, 19/11/2026: "qndo os créditos do flow acabar, nós vamos parar de fazer vídeo
# por ia e ficar só nos vídeos dos grupos ok? Até que o crédito volte"). A foto da conta, no alto do início, abre a
# tela Conta com "N créditos do Google Flow": os 1.000 do plano no mês e os 50 do dia, que não acumulam e são gastos
# primeiro (vistos na gravação do Rafael de 14/11). A descrição da foto começa com FOTO_DA_CONTA e segue com o nome
# da conta, que nunca vai ao log. O robô só lê o número e volta: nunca toca no Ver atividade nem em nada da conta.
SALDO_NA_TELA = re.compile(r"(\d[\d.]*)\s+créditos do Google Flow", re.I)
FOTO_DA_CONTA = "perfil"
ALTO_DO_INICIO = 330
ESPERA_DO_SALDO = 20
# A tela de termos ou de consentimento: o robô nunca aceita nada pelo Rafael. Também o aviso do
# teclado (o do Google Tradutor, que abriu em 15/11 com um toque fora do lugar): OK e Cancelar
# num diálogo do teclado.
PALAVRAS_DE_TERMOS = ("termos de serviço", "aceitar", "concordo", "política de privacidade")
PACOTE_DO_TECLADO = "com.google.android.inputmethod.latin"
# O jeito de cada vídeo, que a IA escolhe pelo produto e varia de um vídeo para outro (o nome que o
# Rafael vê na legenda). Com fala em português do Brasil, viral, inusitado ou de comédia: pedido do
# Rafael (15/11/2026: "você pode fazer vídeos também com falas (...) Pode ser até vídeos virais também,
# do tipo uma coisa inusitada (...) Uma coisa mais comédia"), sempre dentro das diretrizes da Shopee
# Vídeo (sem humilhar ninguém, sem marca, sem preço, sem promessa falsa): DECISOES.md, Shopee Vídeo.
# O vídeo de 16 s (P246 1) tem um jeito só, fora dos que a IA escolhe: uma pessoa vendendo o produto do começo ao
# fim.
ESTILO_DO_VENDEDOR = "vendedor"
# O unboxing (P256 2, 19/11/2026): mais um formato do vídeo de IA de 16 s, além da pessoa vendendo. Só as mãos de quem
# recebeu a encomenda, sem rosto e sem fala, abrindo a caixa e mostrando o produto de perto, com a câmera na mão e a
# luz do dia (o "POV de unboxing" dos vídeos que o Rafael mandou), e a música de fundo da nossa edição no lugar do som.
# A IA escolhe pelo produto (PEDIDO_DO_FORMATO), e nunca saem dois seguidos: depois de um unboxing, o vídeo é o
# vendedor ("não quero vídeos apenas de unboxing (...), farão parte dos vídeos produzidos, mas não serão únicos").
# Escolha do Rafael (P256 2): DECISOES.md, Shopee Vídeo.
ESTILO_DO_UNBOXING = "unboxing"
ESTILOS = {"demonstracao": "demonstração (o produto em uso)", "fala": "pessoa falando do produto",
           "inusitado": "inusitado (viral)", "comedia": "comédia",
           ESTILO_DO_VENDEDOR: "pessoa vendendo o produto, do gancho à chamada (16 s)",
           ESTILO_DO_UNBOXING: "unboxing: as mãos abrindo a caixa com o produto, sem rosto e sem fala (16 s)"}
ESTILO_PADRAO = "demonstracao"
# Quantos estilos dos últimos vídeos a IA recebe, para variar (o Rafael pediu vídeos variados, "para não
# ficar um padrão, para ser mais orgânico", 15/11/2026).
ESTILOS_LEMBRADOS = 4
# O que a IA diz da foto do anúncio (serve e muda_na_ia), igual no pedido do vídeo de 8 s e no de 16 s (P246 1).
REGRAS_DA_FOTO = (
    "- serve: false quando a foto não mostra o produto inteiro e com clareza (colagem de várias "
    "fotos, tabela de medidas, mais texto que produto, só a embalagem fechada) ou quando o produto "
    "é proibido nas diretrizes da Shopee Vídeo{bebida}; motivo: o porquê, em poucas palavras.\n"
    "- muda_na_ia: true quando o produto tem o que a IA de vídeo costuma mudar ao recriá-lo pela foto, e o "
    "vídeo sairia com outro produto: tela (TV, celular, tablet, monitor, relógio ou outro aparelho com visor), "
    "marca, logotipo ou letras no corpo do produto, ou muitos botões e peças pequenas.\n"
)
PEDIDO_DA_IA = (
    "Você é diretor de vídeos curtos de produto para a Shopee Vídeo, no Brasil. A imagem é a foto "
    "oficial do anúncio do produto \"{nome}\". O Google Flow vai gerar um vídeo de 8 segundos, em pé "
    "(9:16) e com som, a partir dessa foto. Responda só com um JSON, sem nada antes ou depois:\n"
    '{{"serve": true ou false, "muda_na_ia": true ou false, "motivo": "...", "estilo": "...", "prompt": "...", '
    '"cena": "..."}}\n'
    + REGRAS_DA_FOTO +
    "- estilo: o jeito do vídeo que mais combina com este produto e prende quem está rolando o feed, um "
    "destes: \"demonstracao\" (o produto em uso no dia a dia), \"fala\" (uma pessoa comum mostra o "
    "produto e fala dele, como um cliente contando a experiência), \"inusitado\" (uma situação curiosa "
    "ou surpreendente com o produto, de vídeo viral) ou \"comedia\" (uma cena engraçada do dia a dia com "
    "o produto; por exemplo, a bicicleta ergométrica com alguém começando a pedalar com toda a "
    "determinação e o cachorro assistindo).{evitar}\n"
    "- prompt: em inglês, até 90 palavras, o pedido do vídeo no estilo escolhido: o mesmo produto da "
    "foto, idêntico (mesma forma, cor, material, tamanho, quantidade e detalhes; nada acrescentado, "
    "tirado ou trocado) e bem à vista, numa cena real do Brasil, com luz natural, fotorrealista, com um "
    "movimento de câmera simples. Com fala, a fala vai em português do Brasil, entre aspas, curta (até "
    "15 palavras, para caber nos 8 segundos), natural, sem marca, sem preço e sem prometer o que o "
    "produto não faz. O humor é da situação, nunca de zombar do corpo, da aparência ou de um grupo de "
    "ninguém (as diretrizes punem humilhação e ódio), e nada perigoso, nojento ou com criança. Sem "
    "texto na tela, sem legenda, sem logotipo novo e sem outros produtos.\n"
    "- cena: uma frase em português que descreve a cena (com a fala, se tiver), para o Rafael."
)
# A fala de cada parte de 8 s do vídeo de 16 s: a mais longa embolava ("palavras que não existem") e a chamada do fim
# saía cortada na 1ª amostra.
PALAVRAS_POR_PARTE = 10
# A fala do começo ao fim de cada parte (P255 1, 19/11/2026): com até 10 palavras terminando antes dos 6 s, a pessoa
# ficava calada e parada boa parte do vídeo (no do hidratante, falou 6,5 s dos 16). Duas frases curtas por parte, até
# este tanto de palavras, faladas do 1º segundo até por volta dos 7 s, mexendo no produto enquanto fala. Por
# enquanto só na amostra (amostra --longa --fala-inteira): o vídeo de IA do dia e o De IA ✨ mudam com o OK do Rafael
# a ela. Escolha do Rafael (P255 1): DECISOES.md, Shopee Vídeo.
PALAVRAS_DA_FALA_INTEIRA = 14
# O pedido do vídeo de 16 s (P246 1): uma pessoa vendendo o produto do começo ao fim, como nos vídeos de IA do feed
# que o Rafael mostrou (16/11/2026): o gancho logo no começo, as vantagens mostradas de perto e a chamada no fim. Em
# duas partes de 8 s: a 1ª gerada pela foto (prompt) e a 2ª pelo Estender do Flow (continuacao), que continua a mesma
# cena. Contra as alucinações da 1ª amostra (a tampa grudada na alça, a ida a outro fogão com comida do nada, o rosto
# trocado, a fala embolada e cortada), a pessoa só segura, vira e aponta o produto, os 16 s ficam no mesmo lugar e
# enquadramento, e a fala é curta e simples. Escolha do Rafael (P248 1): DECISOES.md, Shopee Vídeo.
_COMECO_DO_VENDEDOR = (
    "Você é diretor de vídeos curtos de produto para a Shopee Vídeo, no Brasil, e escreve como os vídeos que mais "
    "vendem no feed. A imagem é a foto oficial do anúncio do produto \"{nome}\". O Google Flow vai gerar um vídeo "
    "de 16 segundos, em pé (9:16) e com som, em duas partes de 8 segundos: a 1ª a partir dessa foto e a 2ª "
    "continuando a 1ª, na mesma cena, com a mesma pessoa e a mesma voz. Uma pessoa comum, brasileira, vende o "
    "produto falando com quem assiste do começo ao fim: um gancho logo no 1º segundo, as vantagens mostradas de "
    "perto e uma chamada para comprar no fim. A IA de vídeo inventa coisas quando a cena pede demais; por isso, nas "
    "duas partes: a pessoa só segura o produto, vira devagar e aponta para ele, sem abrir, fechar, desmontar, "
    "encaixar, despejar, cozinhar, vestir ou trocar o produto de mão, e ele aparece desde o 1º quadro do jeito que "
    "é usado (vestido, montado, no lugar), sem nada mudar de estado; os 16 segundos ficam no mesmo lugar, com o "
    "mesmo fundo e o mesmo enquadramento e a câmera parada, sem corte, sem ir a outro lugar e sem aparecer comida, "
    "objeto ou pessoa nova (se o produto pede um lugar para ser mostrado, como o fogão, a pia ou a cama, o vídeo "
    "já começa lá). Responda só com um JSON, sem nada antes ou depois:\n"
    '{{"serve": true ou false, "muda_na_ia": true ou false, "motivo": "...", "prompt": "...", "continuacao": '
    '"...", "fala": "...", "cena": "..."}}\n'
    + REGRAS_DA_FOTO
)
# O fim do pedido de 16 s, igual nos dois jeitos da fala.
_FIM_DO_VENDEDOR = (
    "- fala: tudo o que a pessoa fala, em português, as duas partes juntas, como vai sair no vídeo.\n"
    "- cena: uma frase em português que descreve a cena, para o Rafael.\n"
    "A fala é natural, com palavras simples do dia a dia (sem número, sigla, palavra estrangeira ou nome difícil, "
    "que a IA de vídeo embola), sem marca, sem preço e sem prometer o que o produto não faz. Nada de zombar do "
    "corpo, da aparência ou de um grupo de ninguém (as diretrizes punem humilhação e ódio), e nada perigoso, "
    "nojento ou com criança. Sem texto na tela, sem legenda, sem logotipo novo e sem outros produtos."
)
PEDIDO_DO_VENDEDOR = _COMECO_DO_VENDEDOR + (
    "- prompt: em inglês, até 90 palavras, os 8 primeiros segundos: a pessoa olha para a câmera, segura o produto "
    "da foto, idêntico (mesma forma, cor, material, tamanho, quantidade e detalhes; nada acrescentado, tirado ou "
    "trocado) e bem à vista, e diz logo no começo o gancho, entre aspas, em português do Brasil, até "
    f"{PALAVRAS_POR_PARTE} palavras: uma dor que o produto resolve, uma pergunta ou uma surpresa (por exemplo: "
    "\"Orelha rasgada? Nunca mais!\"), terminando antes dos 6 segundos; depois, calada, vira o produto devagar para "
    "a câmera. Numa cena real do Brasil, com luz natural, fotorrealista, a câmera parada na altura do peito.\n"
    "- continuacao: em inglês, até 90 palavras, os 8 segundos seguintes, continuando o mesmo plano sem corte, no "
    "mesmo lugar e enquadramento, com a mesma pessoa, a mesma roupa e o mesmo produto, idêntico: ela aponta e "
    "mostra de perto uma vantagem que se vê no produto, só virando-o ou aproximando-o da câmera, e fala logo no "
    f"começo, entre aspas, em português do Brasil, até {PALAVRAS_POR_PARTE} palavras, a vantagem e uma chamada curta "
    "para comprar (por exemplo: \"Nada gruda e limpa fácil. Garanta a sua!\"), terminando antes dos 6 segundos.\n"
) + _FIM_DO_VENDEDOR
# O pedido de 16 s com a fala do começo ao fim de cada parte (P255 1): o resto igual ao PEDIDO_DO_VENDEDOR (só segurar,
# virar e apontar o produto, no mesmo lugar e enquadramento, com a câmera parada), sem o "depois, calada". Por enquanto
# só na amostra (amostra --longa --fala-inteira).
PEDIDO_DO_VENDEDOR_FALANDO = _COMECO_DO_VENDEDOR + (
    "- prompt: em inglês, até 90 palavras, os 8 primeiros segundos: a pessoa olha para a câmera, segura o produto "
    "da foto, idêntico (mesma forma, cor, material, tamanho, quantidade e detalhes; nada acrescentado, tirado ou "
    "trocado) e bem à vista, e fala do 1º segundo até por volta dos 7 segundos, sem ficar calada no meio, entre "
    f"aspas, em português do Brasil, 2 frases curtas com até {PALAVRAS_DA_FALA_INTEIRA} palavras ao todo: o gancho "
    "(uma dor que o produto resolve, uma pergunta ou uma surpresa) e uma vantagem que se vê no produto (por exemplo: "
    "\"Orelha rasgada? Nunca mais! Esse aqui fica firme o dia inteiro.\"); enquanto fala, aproxima o produto da "
    "câmera, vira devagar e aponta o detalhe. Escreva no pedido que ela fala sem parar até perto do fim, sem pausa "
    "longa. Numa cena real do Brasil, com luz natural, fotorrealista, a câmera parada na altura do peito.\n"
    "- continuacao: em inglês, até 90 palavras, os 8 segundos seguintes, continuando o mesmo plano sem corte, no "
    "mesmo lugar e enquadramento, com a mesma pessoa, a mesma roupa e o mesmo produto, idêntico: ela continua "
    "falando do 1º segundo até por volta dos 7 segundos, sem ficar calada no meio, entre aspas, em português do "
    f"Brasil, 2 frases curtas com até {PALAVRAS_DA_FALA_INTEIRA} palavras ao todo: outra vantagem que se vê no "
    "produto e uma chamada curta para comprar (por exemplo: \"Nada gruda e limpa num instante. Garanta já o seu "
    "hoje!\"); enquanto fala, aponta e mostra de perto a vantagem, só virando o produto ou aproximando-o da câmera. "
    "Escreva no pedido que ela fala sem parar até perto do fim, sem pausa longa.\n"
) + _FIM_DO_VENDEDOR
# A escolha do formato do vídeo de 16 s pelo produto (P256 2): o vendedor ou o unboxing.
PEDIDO_DO_FORMATO = (
    "Você é diretor de vídeos curtos de produto para a Shopee Vídeo, no Brasil. A imagem é a foto do anúncio do "
    "produto \"{nome}\". Escolha o formato do vídeo de 16 segundos feito por IA que mais combina com este produto e "
    "mais faz quem está rolando o feed parar e comprar: \"vendedor\" (uma pessoa comum segura o produto e fala dele "
    "com quem assiste, mostrando as vantagens de perto: bom para o produto que precisa de explicação, como "
    "utilidades, aparelhos e o que resolve um problema) ou \"unboxing\" (só as mãos de quem recebeu a encomenda, "
    "sem rosto e sem fala, abrindo a caixa e mostrando o produto de perto, com a câmera na mão: bom para o produto "
    "que se vende pela aparência e cabe numa caixa de encomenda, como calçados, bolsas, roupas, acessórios, "
    "maquiagem e decoração). Responda só com um JSON, sem nada antes ou depois:\n"
    '{{"formato": "vendedor" ou "unboxing", "motivo": "o porquê, em poucas palavras"}}'
)
# O pedido do unboxing de 16 s (P256 2), com os cuidados contra as alucinações da P248 1: o produto aparece inteiro
# e do jeito que vem, nada muda de estado, as mãos só abrem a caixa, levantam e viram o produto, e os 16 s ficam no
# mesmo lugar, sem corte. Sem fala: a música de fundo vai no lugar do som na nossa edição.
PEDIDO_DO_UNBOXING = (
    "Você é diretor de vídeos curtos de produto para a Shopee Vídeo, no Brasil, e escreve como os vídeos que mais "
    "vendem no feed. A imagem é a foto oficial do anúncio do produto \"{nome}\". O Google Flow vai gerar um vídeo "
    "de 16 segundos, em pé (9:16) e com som, em duas partes de 8 segundos: a 1ª a partir dessa foto e a 2ª "
    "continuando a 1ª, na mesma cena. É um unboxing filmado pelos olhos de quem recebeu a encomenda (primeira "
    "pessoa): só as mãos aparecem, sem rosto e sem ninguém falando, com a câmera na mão, como um vídeo de celular "
    "de verdade, numa casa simples e arrumada do Brasil, com a luz do dia. A IA de vídeo inventa coisas quando a "
    "cena pede demais; por isso, o produto aparece inteiro, idêntico ao da foto e do jeito que vem na embalagem, "
    "sem nada mudar de estado; as mãos só abrem a caixa, afastam o papel, levantam o produto e o viram devagar, sem "
    "montar, vestir, ligar ou desmontar nada; e os 16 segundos ficam no mesmo lugar, sem corte e sem aparecer "
    "pessoa, objeto ou produto novo. Responda só com um JSON, sem nada antes ou depois:\n"
    '{{"serve": true ou false, "muda_na_ia": true ou false, "motivo": "...", "prompt": "...", "continuacao": '
    '"...", "cena": "..."}}\n'
    + REGRAS_DA_FOTO +
    "- prompt: em inglês, até 90 palavras, os 8 primeiros segundos, em primeira pessoa, com a câmera na mão: uma "
    "caixa de papelão de encomenda fechada na mesa; as mãos tiram a fita e abrem a caixa, e lá dentro, no papel de "
    "seda, está o produto da foto, idêntico (mesma forma, cor, material, tamanho, quantidade e detalhes; nada "
    "acrescentado, tirado ou trocado) e bem à vista; a mão para um instante ao ver o produto. Escreva no pedido: "
    "authentic handheld smartphone footage, natural daylight, realistic home, packaging sounds, no face, no "
    "dialogue, no subtitles, no text.\n"
    "- continuacao: em inglês, até 90 palavras, os 8 segundos seguintes, continuando o mesmo plano sem corte, no "
    "mesmo lugar, com as mesmas mãos e o mesmo produto, idêntico: as mãos levantam o produto da caixa, aproximam da "
    "câmera e o viram devagar na luz da janela, mostrando os detalhes de perto, sem montar, vestir ou ligar nada. "
    "Escreva no pedido: no face, no dialogue, no subtitles, no text.\n"
    "- cena: uma frase em português que descreve a cena, para o Rafael.\n"
    "Sem marca, sem preço, sem texto na tela, sem legenda, sem logotipo novo e sem outros produtos; nada perigoso, "
    "nojento ou com criança."
)
# Bebida alcoólica fica de lado enquanto as diretrizes a deixam em espera (P111): o vídeo nem é gerado, para não
# gastar o crédito de um vídeo que o rascunho deixaria de lado.
TRECHO_DA_BEBIDA = ", ou é bebida alcoólica (em espera nas diretrizes)"
# O produto que a IA de vídeo costuma mudar ao recriá-lo pela foto (tela, marca ou letras no corpo, muitos botões)
# sai da escolha, mesmo com a foto boa: o vídeo dele quase sempre sai com outro produto, e as conferências o
# descartam depois de gasto o crédito. Escolha do Rafael (16/11/2026, P245 1): DECISOES.md, Shopee Vídeo.
MUDA_NA_IA = "muda na IA de vídeo"
# A conferência do vídeo pronto, que vai com ele no privado do Rafael: o produto é o da foto?
PEDIDO_DA_CONFERENCIA = (
    "Este vídeo foi feito por IA a partir da foto do anúncio que vai junto (a imagem). Compare o "
    "produto do vídeo com o da foto: forma, cor, material, detalhes e o que vem junto. Veja também o "
    "que denuncia a IA no vídeo: mãos ou pés estranhos, objetos que se deformam ou mudam de um quadro "
    "para outro, letras sem sentido e, se o vídeo tem fala, a fala que não está em português do Brasil, "
    "que sai cortada ou que não acompanha a boca de quem fala. Responda só com um JSON, sem nada antes "
    "ou depois:\n"
    '{"mesmo_produto": true ou false, "diferencas": "o que muda no produto, em até 200 letras; vazio '
    'se nada", "defeitos": "o que parece falso ou estranho no vídeo, em até 200 letras; vazio se nada"}'
)
ROTULOS_DA_CONFERENCIA = {True: "mesmo produto", False: "produto diferente", None: "sem resposta"}
# A conferência da fala do vídeo de 16 s pelo servidor (P248 1, conferir_a_fala): a palavra ouvida quase igual a uma
# da fala pedida conta como ela (FALA_PARECIDA das letras); 2 palavras ouvidas fora da fala pedida, com 3 letras ou
# mais, são a fala embolada; o fim da fala pedida que não se ouve, com a fala indo até FOLGA_DO_FIM_DA_FALA do fim do
# vídeo, é a chamada cortada.
FALA_PARECIDA = 0.8
LETRAS_DA_ESTRANHA = 3
ESTRANHAS_DA_FALA_EMBOLADA = 2
FOLGA_DO_FIM_DA_FALA = 0.5
ROTULOS_DA_FALA = {"igual": "igual à pedida", "embolada": "embolada", "cortada": "cortada no fim",
                   "embolada e cortada": "embolada e cortada no fim", "sem fala": "sem fala",
                   None: "não deu para ouvir"}


class Parada(Exception):
    """O teste parou num passo: a mensagem é um texto fixo do código (vai para o log público)."""


class SemCreditos(Parada):
    """O saldo do Flow não paga o vídeo, e nada foi gerado: saldo e preciso são os números (só eles vão ao log)."""

    def __init__(self, saldo, preciso):
        super().__init__(f"sem créditos do Flow: {saldo} na conta, o vídeo pede {preciso}")
        self.saldo, self.preciso = saldo, preciso


def agora():
    return datetime.now(fuso_horario).strftime("%Y-%m-%d %H:%M:%S")


def nome_do_estilo(estilo):
    """A chave do estilo (ESTILOS) pelo que a IA escreveu, com ou sem acento; o ESTILO_PADRAO quando não é nenhum."""
    sem_acento = unicodedata.normalize("NFKD", str(estilo or "")).encode("ascii", "ignore").decode().lower()
    return next((chave for chave in ESTILOS if chave in sem_acento), ESTILO_PADRAO)


def estilos_recentes():
    """Os estilos dos últimos vídeos de IA (o mais novo por último), para a IA variar."""
    return list((db.ler_config(CHAVE, {}) or {}).get("estilos") or [])[-ESTILOS_LEMBRADOS:]


def evitar_os_recentes(recentes):
    """O trecho do pedido à IA que pede outro estilo que não os dos últimos vídeos; "" sem vídeo antes."""
    if not recentes:
        return ""
    return (" Os últimos vídeos foram " + ", ".join(f'"{e}"' for e in recentes) + ": prefira outro estilo, "
            "se ele também combinar com este produto, para os vídeos não ficarem num padrão só.")


def ler_resposta(texto, longo=False, unboxing=False):
    """
    {"serve", "muda_na_ia", "motivo", "estilo", "prompt", "cena"} da resposta da IA; None quando ela não
    veio num JSON ou disse que serve sem escrever o pedido. longo: a resposta do pedido de 16 s (P246 1), com a
    "continuacao" (o pedido do Estender, sem ela também None) e a "fala", no estilo do vendedor; unboxing: a do
    unboxing de 16 s (P256 2), sem fala.
    """
    achado = re.search(r"\{.*\}", texto or "", re.S)
    if not achado:
        return None
    try:
        dados = json.loads(achado.group(0))
    except ValueError:
        return None
    if not isinstance(dados, dict):
        return None
    serve = dados.get("serve") is True
    prompt = " ".join(str(dados.get("prompt") or "").split())
    continuacao = " ".join(str(dados.get("continuacao") or "").split())
    if serve and (not prompt or (longo and not continuacao)):
        return None
    resposta = {"serve": serve, "muda_na_ia": dados.get("muda_na_ia") is True,
                "motivo": " ".join(str(dados.get("motivo") or "").split())[:200],
                "estilo": (ESTILO_DO_UNBOXING if unboxing else ESTILO_DO_VENDEDOR) if longo
                else nome_do_estilo(dados.get("estilo")),
                "prompt": prompt[:1000], "cena": " ".join(str(dados.get("cena") or "").split())[:300]}
    if longo:
        fala = "" if unboxing else " ".join(str(dados.get("fala") or "").split())[:400]
        resposta.update(continuacao=continuacao[:1000], fala=fala)
    return resposta


def jpeg_sem_metadados(dados):
    """
    A foto regravada em JPEG, sem os dados de câmera (EXIF): no seletor de fotos do Android, a
    mais nova é a 1ª pela hora em que entrou na galeria, e não por uma data antiga da foto.
    None quando os bytes não são uma imagem.
    """
    from PIL import Image
    try:
        with Image.open(io.BytesIO(dados)) as imagem:
            saida = io.BytesIO()
            imagem.convert("RGB").save(saida, "JPEG", quality=95)
            return saida.getvalue()
    except Exception:
        return None


def formato_do_video(nome, foto):
    """
    O formato do vídeo de 16 s que a IA escolhe pela foto do anúncio (já em JPEG) e pelo nome (P256 2):
    ESTILO_DO_UNBOXING ou ESTILO_DO_VENDEDOR; o vendedor quando ela não responde num JSON.
    """
    texto = asyncio.run(api_gemini.gerar_texto_gemini(PEDIDO_DO_FORMATO.format(nome=nome),
                                                      imagens=[(foto, "image/jpeg")]))
    achado = re.search(r"\{.*\}", texto or "", re.S)
    try:
        formato = json.loads(achado.group(0)).get("formato") if achado else ""
    except (ValueError, AttributeError):
        formato = ""
    return ESTILO_DO_UNBOXING if str(formato or "").strip().lower() == ESTILO_DO_UNBOXING else ESTILO_DO_VENDEDOR


def ultimo_foi_unboxing():
    """Se o vídeo de IA mais recente da produção foi um unboxing (P256 2): o seguinte é o vendedor."""
    return producao().get("estilo") == ESTILO_DO_UNBOXING


def pedido_para_o_anuncio(link, nome, foto, evitar="", longo=False, fala_inteira=False, com_unboxing=False):
    """
    O pedido do vídeo para o anúncio já em mãos (o link, o nome e os bytes da foto do anúncio): a foto sem os
    dados de câmera e o que a IA escreveu, num estilo diferente dos últimos vídeos quando combina (evitar, o
    trecho de evitar_os_recentes). (o pedido, serve): o pedido é {"link", "nome", "foto" (bytes), "estilo",
    "prompt", "cena"} quando a IA acha a foto boa para o vídeo; serve é False quando ela disse que a foto não
    serve, MUDA_NA_IA quando o produto tem o que a IA de vídeo costuma mudar (P245 1) e None quando não deu
    para saber (a foto não é uma imagem, ou a IA não respondeu). longo: o pedido do vídeo de 16 s com uma pessoa
    vendendo o produto (P246 1), com a "continuacao" do Estender e a "fala"; fala_inteira: o de 16 s com a fala do
    começo ao fim de cada parte (P255 1, a amostra). com_unboxing (só no de 16 s): a IA escolhe pelo produto entre o
    vendedor e o unboxing (P256 2, formato_do_video); o do unboxing vem sem fala.
    """
    foto = jpeg_sem_metadados(foto) if foto and nome else None
    if not foto:
        return None, None
    unboxing = bool(longo and com_unboxing and not fala_inteira
                    and formato_do_video(nome, foto) == ESTILO_DO_UNBOXING)
    if unboxing:
        pedido = PEDIDO_DO_UNBOXING
    elif longo:
        pedido = PEDIDO_DO_VENDEDOR_FALANDO if fala_inteira else PEDIDO_DO_VENDEDOR
    else:
        pedido = PEDIDO_DA_IA
    resposta = ler_resposta(asyncio.run(api_gemini.gerar_texto_gemini(
        pedido.format(nome=nome, evitar=evitar, bebida=TRECHO_DA_BEBIDA if assistente.BEBIDA_EM_ESPERA else ""),
        imagens=[(foto, "image/jpeg")])), longo=longo, unboxing=unboxing)
    if not resposta:
        return None, None
    if not resposta["serve"]:
        return None, False
    if resposta["muda_na_ia"]:
        return None, MUDA_NA_IA
    escolhido = {"link": link, "nome": nome, "foto": foto, "estilo": resposta["estilo"], "prompt": resposta["prompt"],
                 "cena": resposta["cena"]}
    if longo:
        escolhido.update(continuacao=resposta["continuacao"], fala=resposta["fala"])
    return escolhido, True


def pedido_para_o_produto(link, evitar=""):
    """
    O pedido do vídeo para o produto do link (pedido_para_o_anuncio, com a foto e o nome que a API de afiliado
    dá para o link); None quando o anúncio não traz a foto e o nome ou a IA não acha a foto boa para o vídeo.
    """
    anuncio = ps.anuncio_do_produto({"link": link})
    return pedido_para_o_anuncio(link, anuncio.get("nome"), anuncio.get("foto"), evitar)[0]


def escolher_o_produto():
    """
    O produto do teste: o 1º dos próximos vídeos da fonte do painel com a foto do anúncio que a
    IA acha boa para o vídeo, com o pedido dela (pedido_para_o_produto). O pedido_para_o_produto
    com "tentados"; None sem nenhum.
    """
    fonte = (db.ler_config(ps.CHAVE_PAINEL, {}) or {}).get("fonte", assistente.FONTE_PADRAO)
    evitar = evitar_os_recentes(estilos_recentes())
    tentados = 0
    for _, _, link, _ in assistente.candidatos_nao_usados(fonte)[:PRODUTOS_TENTADOS]:
        if not link:
            continue
        tentados += 1
        pedido = pedido_para_o_produto(link, evitar)
        if pedido:
            return dict(pedido, tentados=tentados)
    return None


def teste_guardado():
    """O teste de agora (o produto, o pedido e os vídeos já gerados), do banco; {} sem nenhum."""
    teste = (db.ler_config(CHAVE, {}) or {}).get("teste") or {}
    return teste if teste.get("foto") and os.path.exists(teste["foto"]) else {}


def guardar(**campos):
    """Grava os campos na chave do Flow (o projeto do robô e o teste)."""
    db.atualizar_config(CHAVE, lambda dados: dados.update(campos))


def marcar_video(modelo, **campos):
    """Anota no teste guardado o vídeo do modelo (o estado: gerando, baixado ou enviado; o custo; o arquivo)."""
    def alterar(dados):
        dados.setdefault("teste", {}).setdefault("videos", {}).setdefault(modelo, {}).update(campos)
    db.atualizar_config(CHAVE, alterar)


def proximo_modelo(teste):
    """(nome, custo) do próximo modelo do teste, do mais barato ao mais caro; None com os 3 gerados."""
    gerados = (teste or {}).get("videos") or {}
    return next(((nome, custo) for nome, custo in MODELOS_DO_TESTE if nome not in gerados), None)


def video_pendente(teste):
    """O modelo cujo vídeo já foi gerado e ainda não chegou ao Rafael (gerando ou baixado); None sem ele."""
    return next((nome for nome, video in ((teste or {}).get("videos") or {}).items()
                 if video.get("estado") in ("gerando", "baixado")), None)


def numero_do_modelo(modelo):
    """A posição do modelo no teste (1 a 3); 0 fora dele."""
    return next((numero for numero, (nome, _) in enumerate(MODELOS_DO_TESTE, 1) if nome == modelo), 0)


# --- As telas do Flow -----------------------------------------------------------------------

def _tela(d):
    try:
        return d.dump_hierarchy()
    except Exception:
        return ""


def esperar(d, condicao, espera=ESPERA_DA_TELA):
    """A tela (o xml) assim que a condição vale nela, esperando até `espera` s; "" se não veio."""
    fim = time.monotonic() + espera
    while True:
        xml = _tela(d)
        if xml and condicao(xml):
            return xml
        if time.monotonic() >= fim:
            return ""
        time.sleep(PAUSA_DA_LEITURA)


def tem_termos(xml):
    """A tela pede para aceitar termos ou dar consentimento (ou o teclado abriu um aviso)? O robô para."""
    for el in ps.elementos(xml):
        if any(palavra in f"{el['texto']} {el['descricao']}".casefold() for palavra in PALAVRAS_DE_TERMOS):
            return True
        if el["pacote"] == PACOTE_DO_TECLADO and el["texto"] in ("OK", "Cancelar"):
            return True
    return False


def ponto_parado(d, achar_ponto, passo, espera=ESPERA_DA_TELA):
    """
    O ponto (achar_ponto(xml)) quando ele para de se mexer: duas leituras seguidas no mesmo lugar.
    O pedido do Flow sobe com o teclado, e o toque no meio da subida cai em outro lugar (em 15/11,
    no Traduzir do teclado). Parada na tela de termos; None sem o ponto.
    """
    fim, anterior = time.monotonic() + espera, None
    while True:
        xml = _tela(d)
        if xml and tem_termos(xml):
            raise Parada(f"{passo}: tela de termos ou aviso do teclado; o robô nunca aceita pelo Rafael")
        ponto = achar_ponto(xml) if xml else None
        if ponto and ponto == anterior:
            return ponto
        anterior = ponto
        if time.monotonic() >= fim:
            return None
        time.sleep(PAUSA_DA_LEITURA)


def tocar(d, alvo, passo, espera=ESPERA_DA_TELA):
    """Toca no elemento (texto, descrição ou @id, como no ps.achar) quando ele aparece parado; Parada sem ele."""
    ponto = ponto_parado(d, lambda xml: ps.achar(xml, alvo), passo, espera)
    if not ponto:
        raise Parada(f"{passo}: não achei o botão na tela")
    d.click(*ponto)


def centro_da_caixa(xml):
    """O centro da caixa do pedido; None sem ela."""
    campo = next((el for el in ps.elementos(xml) if el["pacote"] == PACOTE and el["classe"] == "EditText"), None)
    if not campo:
        return None
    x1, y1, x2, y2 = campo["caixa"]
    return (x1 + x2) // 2, (y1 + y2) // 2


def projeto_na_lista(xml, nome=PROJETO_DO_ROBO):
    """
    O centro do projeto com esse nome na lista do início; None sem ele. O Flow descreve cada um como
    "O título do projeto é Shopee Video, 1 vídeo, 4 imagens" (lido em 15/11/2026): vale o nome
    inteiro, logo depois do "é" (ou no começo), e não um pedaço dele ("Shopee Video 2" não serve).
    """
    for el in ps.elementos(xml):
        if el["pacote"] != PACOTE:
            continue
        for valor in (el["descricao"], el["texto"]):
            if re.search(rf"(?:^|\bé\s+){re.escape(nome)}\s*(?:$|[,\n])", (valor or "").strip(), re.I):
                x1, y1, x2, y2 = el["caixa"]
                return (x1 + x2) // 2, (y1 + y2) // 2
    return None


def modelo_no_pedido(xml):
    """O modelo que está marcado no pedido (o botão "Omni 1.2 Flash\\nx1"); "" sem ele."""
    for el in ps.elementos(xml):
        achado = re.fullmatch(r"(.+?)\s*\n\s*x\d", el["descricao"] or "")
        if el["pacote"] == PACOTE and achado:
            return " ".join(achado.group(1).split())
    return ""


def custo_na_tela(xml):
    """Quantos créditos a geração vai usar, como o app diz ("24 créditos de IA"); None sem o aviso."""
    for el in ps.elementos(xml):
        achado = CUSTO_NA_TELA.search(f"{el['descricao']} {el['texto']}")
        if achado:
            return int(achado.group(1))
    return None


def texto_do_pedido(xml):
    """O que está escrito na caixa do pedido ("" vazia)."""
    for el in ps.elementos(xml):
        if el["pacote"] == PACOTE and el["classe"] == "EditText":
            return el["texto"]
    return ""


def fotos_no_pedido(xml):
    """
    Quantas miniaturas de foto o pedido tem: as imagens tocáveis do app, sem descrição, logo acima do
    + (Adicionar mídia). Com as opções do modelo abertas, a caixa do pedido ocupa a tela toda e a
    miniatura fica dentro dela (visto no ensaio de 15/11); o + fica abaixo da miniatura nos dois jeitos.
    """
    elementos = ps.elementos(xml)
    mais = next((el["caixa"] for el in elementos
                 if el["pacote"] == PACOTE and el["descricao"] == "Adicionar mídia"), None)
    if not mais:
        return 0
    return sum(1 for el in elementos
               if el["pacote"] == PACOTE and el["classe"] == "ImageView" and el["clicavel"] and not el["descricao"]
               and 60 <= el["caixa"][2] - el["caixa"][0] <= 300 and mais[1] - 900 <= el["caixa"][3] <= mais[1])


def foto_no_pedido(xml):
    """A miniatura da foto do produto já está no pedido?"""
    return fotos_no_pedido(xml) > 0


def pronto_para_gerar(xml, prompt, modelo, custo):
    """"" quando o pedido está como o teste quer (foto, texto, modelo e custo); senão, o que falta (texto fixo)."""
    if fotos_no_pedido(xml) != 1:
        return "o pedido não tem uma foto só"
    if " ".join(texto_do_pedido(xml).split())[:40] != " ".join(prompt.split())[:40]:
        return "o texto do pedido não entrou"
    if modelo_no_pedido(xml) != modelo:
        return "o modelo marcado não é o do teste"
    if custo_na_tela(xml) != custo:
        return "o custo na tela não é o esperado"
    return ""


def projetos_na_tela(xml):
    """As descrições dos projetos que a lista do início mostra agora (para saber se ela ainda anda)."""
    return tuple(el["descricao"] for el in ps.elementos(xml)
                 if el["pacote"] == PACOTE and (el["descricao"] or "").startswith("O título do projeto"))


def achar_o_projeto(d):
    """
    O centro do projeto do robô na lista do início, rolando até o fim dela; None quando ele não está
    em lugar nenhum da lista (a lista parou de andar sem ele).
    """
    vistos = None
    for _ in range(ROLADAS_DA_LISTA + 1):
        ponto = ponto_parado(d, projeto_na_lista, "projeto do robô", ESPERA_DA_LISTA)
        if ponto:
            return ponto
        na_tela = projetos_na_tela(_tela(d))
        if na_tela == vistos:
            return None
        vistos = na_tela
        ps.rolar(d)
        time.sleep(1)
    return None


def botao_do_alto(xml, descricao):
    """O centro do botão do alto do projeto com essa descrição (o Mais opções do projeto, não o de um vídeo); None sem ele."""
    for el in ps.elementos(xml):
        if (el["pacote"] == PACOTE and el["clicavel"] and el["descricao"] == descricao
                and el["caixa"][3] <= ALTO_DO_PROJETO):
            x1, y1, x2, y2 = el["caixa"]
            return (x1 + x2) // 2, (y1 + y2) // 2
    return None


def titulo_do_projeto(xml):
    """O nome do projeto aberto, no alto da tela; "" fora de um projeto."""
    for el in ps.elementos(xml):
        x1, y1, x2, y2 = el["caixa"]
        if (el["pacote"] == PACOTE and el["classe"] == "View" and not el["clicavel"] and el["descricao"]
                and y2 <= ALTO_DO_PROJETO and x2 - x1 >= 900):
            return el["descricao"]
    return ""


def campo_do_nome(xml):
    """O campo do nome do Renomear, no alto do projeto (o elemento); None sem ele."""
    return next((el for el in ps.elementos(xml) if el["pacote"] == PACOTE and el["classe"] == "EditText"
                 and el["caixa"][3] <= ALTO_DO_PROJETO), None)


def botoes_do_nome(xml):
    """
    Os botões sem nome ao lado do campo do Renomear, da esquerda para a direita: o ✓ e o ✕ (vistos
    em 15/11/2026). Lista de centros; vazia sem o campo.
    """
    campo = campo_do_nome(xml)
    if not campo:
        return []
    _, cima, _, baixo = campo["caixa"]
    botoes = sorted(el["caixa"] for el in ps.elementos(xml)
                    if el["pacote"] == PACOTE and el["classe"] == "Button" and el["clicavel"]
                    and not el["descricao"] and not el["texto"] and cima <= (el["caixa"][1] + el["caixa"][3]) // 2 <= baixo)
    return [((x1 + x2) // 2, (y1 + y2) // 2) for x1, y1, x2, y2 in botoes]


def criar_o_projeto(d):
    """
    Cria o projeto do robô quando ele sumiu da lista e o usa de padrão (pedido do Rafael, 15/11/2026).
    Caminho mapeado em 15/11: o Novo cria um projeto vazio com o nome do dia e já o abre; o Mais
    opções do alto abre o menu do projeto; o Renomear põe o nome num campo no alto, com o ✓ e o ✕
    ao lado. O robô escreve PROJETO_DO_ROBO, toca no ✓ e confere o título. No máximo um projeto por
    dia: o criado que não ficou com o nome não vira outro no mesmo dia. Parada no que falhar.
    """
    criado_em = (db.ler_config(CHAVE, {}) or {}).get("projeto_criado_em") or ""
    if criado_em[:10] == agora()[:10]:
        raise Parada(f"abrir o Flow: o projeto {PROJETO_DO_ROBO} não está na lista, e o robô já criou um "
                     "projeto hoje; não cria outro no mesmo dia")
    tocar(d, "Novo", "criar o projeto")
    guardar(projeto_criado_em=agora())
    ponto = ponto_parado(d, lambda x: ps.achar(x, "Criar") and botao_do_alto(x, "Mais opções"), "projeto novo")
    if not ponto:
        raise Parada("criar o projeto: o projeto novo não abriu")
    d.click(*ponto)
    menu = esperar(d, lambda x: ps.achar(x, "Renomear"))
    if not menu:
        raise Parada("criar o projeto: o Renomear não apareceu no menu do projeto")
    toque_x, toque_y = ps.achar(menu, "Renomear")
    if any(PROIBIDO_NO_MENU_DO_PROJETO.search(f"{el['texto']} {el['descricao']}")
           and el["caixa"][0] <= toque_x <= el["caixa"][2] and el["caixa"][1] <= toque_y <= el["caixa"][3]
           for el in ps.elementos(menu)):
        raise Parada("criar o projeto: o toque do Renomear cairia no Excluir ou na lixeira; o robô não toca")
    d.click(toque_x, toque_y)
    if not esperar(d, lambda x: campo_do_nome(x) is not None):
        raise Parada("renomear o projeto: o campo do nome não apareceu")
    ps.escrever(d, PROJETO_DO_ROBO)
    xml = esperar(d, lambda x: (campo_do_nome(x) or {}).get("texto") == PROJETO_DO_ROBO, 10)
    if not xml:
        raise Parada("renomear o projeto: o nome não entrou no campo")
    botoes = botoes_do_nome(xml)
    if len(botoes) != 2:
        raise Parada("renomear o projeto: o ✓ e o ✕ não estão ao lado do campo como no mapeamento")
    d.click(*botoes[0])
    # O Criar, que o teclado pode tapar logo depois do ✓, o pedido espera do jeito de sempre.
    if not esperar(d, lambda x: titulo_do_projeto(x) == PROJETO_DO_ROBO):
        raise Parada(f"renomear o projeto: o título não ficou {PROJETO_DO_ROBO}")


def abrir_o_inicio(d):
    """Abre o Flow do zero, no início (o Novo à vista). Parada sem ele ou na tela de termos."""
    d.app_start(PACOTE, stop=True, wait=True)
    xml = esperar(d, lambda x: ps.achar(x, "Novo") or tem_termos(x), 30)
    if not xml or tem_termos(xml):
        raise Parada("abrir o Flow: o início não apareceu" if not xml else
                     "abrir o Flow: tela de termos; o robô nunca aceita pelo Rafael")


def foto_da_conta(xml):
    """O centro da foto da conta no alto do início do Flow (a descrição começa com FOTO_DA_CONTA); None sem ela."""
    for el in ps.elementos(xml):
        if (el["pacote"] == PACOTE and el["caixa"][3] <= ALTO_DO_INICIO
                and (el["descricao"] or "").strip().casefold().startswith(FOTO_DA_CONTA)):
            x1, y1, x2, y2 = el["caixa"]
            return (x1 + x2) // 2, (y1 + y2) // 2
    return None


def saldo_na_tela(xml):
    """Os créditos do Flow que a tela Conta mostra ("1050 créditos do Google Flow"); None sem eles."""
    for el in ps.elementos(xml):
        if el["pacote"] != PACOTE:
            continue
        for valor in (el["texto"], el["descricao"]):
            achado = SALDO_NA_TELA.search(" ".join((valor or "").split()))
            if achado:
                return int(achado.group(1).replace(".", ""))
    return None


def ler_o_saldo(d):
    """
    Os créditos do Flow agora, com o app no início: toca na foto da conta, lê o saldo na tela Conta e volta ao
    início. Parada sem a foto, sem o saldo ou sem o início de volta: sem o saldo lido, nada é gerado.
    """
    ponto = ponto_parado(d, foto_da_conta, "saldo")
    if not ponto:
        raise Parada("saldo: a foto da conta não apareceu no alto do início do Flow")
    d.click(*ponto)
    # O saldo vem primeiro: a tela Conta pode ter, mais abaixo, os links dos termos e da privacidade, que não são a
    # tela de termos. Ela só conta quando o saldo não aparece.
    xml = esperar(d, lambda x: saldo_na_tela(x) is not None, ESPERA_DO_SALDO)
    if not xml:
        raise Parada("saldo: tela de termos; o robô nunca aceita pelo Rafael" if tem_termos(_tela(d)) else
                     "saldo: a tela Conta não mostrou os créditos do Flow")
    saldo = saldo_na_tela(xml)
    d.press("back")
    if not esperar(d, lambda x: ps.achar(x, "Novo"), 30):
        raise Parada("saldo: o início do Flow não voltou depois da tela Conta")
    return saldo


def saldo_da_conta(d):
    """Os créditos do Flow agora, abrindo o app do zero (ler_o_saldo). Parada como a dele."""
    abrir_o_inicio(d)
    return ler_o_saldo(d)


def abrir_o_projeto(d, saldo_minimo=None):
    """
    Abre o Flow do zero e entra no projeto do robô (PROJETO_DO_ROBO), conferindo o título no alto.
    Sem ele em lugar nenhum da lista, cria um com esse nome (criar_o_projeto). True quando criou.
    saldo_minimo: o vídeo vai ser gerado, e antes o robô lê o saldo do Flow no início (ler_o_saldo):
    abaixo dele, SemCreditos, sem entrar no projeto (0: só lê e mostra no log).
    """
    abrir_o_inicio(d)
    if saldo_minimo is not None:
        saldo = ler_o_saldo(d)
        print(f"Flow: {saldo} créditos na conta")
        if saldo < saldo_minimo:
            raise SemCreditos(saldo, saldo_minimo)
    ponto = achar_o_projeto(d)
    if not ponto:
        # A lista rolada esconde o Novo, que fica no alto do início: o Flow abre de novo, do alto.
        d.app_start(PACOTE, stop=True, wait=True)
        if not esperar(d, lambda x: ps.achar(x, "Novo"), 30):
            raise Parada("criar o projeto: o início do Flow não voltou")
        criar_o_projeto(d)
        return True
    d.click(*ponto)
    if not esperar(d, lambda x: ps.achar(x, "Criar") and titulo_do_projeto(x) == PROJETO_DO_ROBO):
        raise Parada(f"abrir o projeto: o Criar ou o título {PROJETO_DO_ROBO} não apareceu")
    return False


def montar_o_pedido(d, prompt, modelo, custo):
    """Criar → Vídeo → a foto → o texto → o modelo; devolve a tela pronta para o Gerar (Parada no que falhar)."""
    tocar(d, "Criar", "criar")
    tocar(d, "Vídeo", "modo vídeo")
    # O pedido guardado de antes (foto ou texto) não é apagado às cegas: o teste para, e
    # nunca gera com duas fotos ou com o texto de outro pedido.
    xml = esperar(d, lambda x: any(el["classe"] == "EditText" for el in ps.elementos(x)))
    if not xml:
        raise Parada("pedido: a caixa do pedido não apareceu")
    if fotos_no_pedido(xml) or texto_do_pedido(xml).strip():
        raise Parada("pedido: já tinha foto ou texto de antes")
    tocar(d, "Adicionar mídia", "adicionar mídia")
    tocar(d, "Imagens", "imagens")
    if not esperar(d, lambda x: PACOTE_DO_SELETOR in x and ps.achar(x, "Item Foto")):
        raise Parada("seletor de fotos: a foto do produto não apareceu")
    tocar(d, "Item Foto", "escolher a foto")
    tocar(d, "@button_add", "adicionar a foto")
    if not esperar(d, foto_no_pedido, 30):
        raise Parada("foto no pedido: a miniatura não apareceu")
    ponto = ponto_parado(d, centro_da_caixa, "texto do pedido")
    if not ponto:
        raise Parada("texto do pedido: a caixa não apareceu")
    d.click(*ponto)
    time.sleep(1)
    ps.escrever(d, prompt)
    if not esperar(d, lambda x: " ".join(texto_do_pedido(x).split())[:40] == " ".join(prompt.split())[:40], 10):
        raise Parada("texto do pedido: o texto não entrou na caixa")
    xml = _tela(d)
    atual = modelo_no_pedido(xml)
    if not atual:
        raise Parada("modelo: o botão do modelo não apareceu")
    tocar(d, f"{atual} x", "abrir o modelo")
    # O Flow abre no último modelo usado, e as opções mudam com o modelo: primeiro o modelo, depois
    # as opções dele. O Veo 3.1 - Lite não tem a escolha da resolução (visto em 15/11/2026); o custo
    # conferido antes do Gerar pega a resolução errada nos modelos que a têm.
    if atual != modelo:
        tocar(d, atual, "lista de modelos")
        tocar(d, modelo, "escolher o modelo")
        if not esperar(d, lambda x: modelo_no_pedido(x) == modelo):
            raise Parada("modelo: o escolhido não ficou marcado")
    xml = _tela(d)
    for opcao in ("9:16", "720p", "x1"):
        if opcao == "720p" and not (ps.achar(xml, "720p") or ps.achar(xml, "360p")):
            continue
        tocar(d, opcao, f"opção {opcao}")
    return esperar(d, lambda x: custo_na_tela(x) is not None) or _tela(d)


def gerando(xml):
    """Há vídeo sendo gerado no projeto (o quadrado "N% Gerando…")?"""
    return any(el["pacote"] == PACOTE and GERANDO.search(f"{el['texto']} {el['descricao']}")
               for el in ps.elementos(xml))


def esperar_o_video(d, ja_gerado=False, guardar_telas=True):
    """
    Espera o vídeo novo ficar pronto no projeto, guardando a tela a cada INTERVALO_DOS_CASOS
    (casos_robo; guardar_telas=False na produção do dia, para as telas da espera não tirarem do
    servidor os casos das falhas, que ficam no máximo 30). Logo depois do Gerar, o "Gerando…" tem de
    aparecer em ESPERA_DO_GERANDO s (Parada sem ele: o Flow não gerou). ja_gerado=True (gerado numa
    vez anterior): pronto se ele não aparece. Os segundos até ficar pronto; None se não ficou em
    ESPERA_DA_GERACAO.
    """
    inicio, proximo_caso, visto, seguidas = time.monotonic(), 0.0, ja_gerado, 0
    while True:
        passado = time.monotonic() - inicio
        if guardar_telas and passado >= proximo_caso:
            casos_robo.guardar(d, "flow", "tela", f"esperando o vídeo, aos {int(passado)} s", passo="flow gerar")
            proximo_caso += INTERVALO_DOS_CASOS
        xml = _tela(d)
        if xml and tem_termos(xml):
            raise Parada("gerar: tela de termos ou de consentimento; o robô nunca aceita pelo Rafael")
        if xml and gerando(xml):
            visto, seguidas = True, 0
        elif xml and visto and ps.achar(xml, "Criar"):
            seguidas += 1
            if seguidas >= PRONTO_SEGUIDAS:
                return int(passado)
        else:
            seguidas = 0
            if not visto and passado >= ESPERA_DO_GERANDO:
                raise Parada("gerar: o Flow não mostrou o vídeo sendo gerado")
        if passado >= ESPERA_DA_GERACAO:
            return None
        time.sleep(PAUSA_DA_LEITURA)


def quadro_mais_novo(xml):
    """O centro do quadro mais novo do projeto (o 1º da grade: o mais alto e, empatado, o da esquerda); None sem quadro."""
    quadros = [el for el in ps.elementos(xml)
               if el["pacote"] == PACOTE and el["clicavel"] and ITEM_DO_PROJETO.search(el["descricao"] or "")]
    if not quadros:
        return None
    x1, y1, x2, y2 = min(quadros, key=lambda el: (el["caixa"][1], el["caixa"][0]))["caixa"]
    return (x1 + x2) // 2, (y1 + y2) // 2


def titulo_do_video(xml):
    """As linhas do título do vídeo aberto (o nome, o modelo e a resolução); None fora do vídeo aberto."""
    elementos = [el for el in ps.elementos(xml) if el["pacote"] == PACOTE]
    if not any(VIDEO_ABERTO.search(el["descricao"] or "") for el in elementos):
        return None
    for el in elementos:
        linhas = [" ".join(linha.split()) for linha in (el["descricao"] or "").split("\n")]
        if len(linhas) >= 2 and not el["clicavel"] and el["caixa"][1] < 400:
            return linhas
    return []


def versoes_do_video(xml):
    """
    Os centros das miniaturas das versões do vídeo aberto: a coluna à direita do player, quando o
    vídeo tem mais de uma (o Estender guarda a versão nova junto da original, "1 de 2"). [] sem elas.
    """
    pontos = []
    for el in ps.elementos(xml):
        x1, y1, x2, y2 = el["caixa"]
        if (el["pacote"] == PACOTE and el["classe"] == "ImageView" and el["clicavel"] and not el["descricao"]
                and x1 > 800 and 30 <= x2 - x1 <= 120 and 30 <= y2 - y1 <= 120):
            pontos.append(((x1 + x2) // 2, (y1 + y2) // 2))
    return pontos


def video_sem_carregar(xml):
    """O vídeo aberto com o player em "Falha ao carregar o vídeo"?"""
    return any(el["pacote"] == PACOTE and FALHA_NO_PLAYER.search(f"{el['texto']} {el['descricao']}")
               for el in ps.elementos(xml))


def _abrir_o_mais_novo(d):
    """No projeto: Vídeos → o mais novo; o player que não carrega é fechado e aberto de novo (ABERTURAS_DO_VIDEO)."""
    tocar(d, "Vídeos", "filtro dos vídeos")
    for abertura in range(1, ABERTURAS_DO_VIDEO + 1):
        ponto = ponto_parado(d, quadro_mais_novo, "vídeo novo")
        if not ponto:
            raise Parada("baixar: o vídeo novo não apareceu no projeto")
        d.click(*ponto)
        xml = esperar(d, lambda x: titulo_do_video(x) is not None or video_sem_carregar(x))
        if not xml:
            raise Parada("baixar: o vídeo não abriu")
        if titulo_do_video(xml) is not None or esperar(d, lambda x: titulo_do_video(x) is not None, ESPERA_DO_PLAYER):
            break
        if abertura == ABERTURAS_DO_VIDEO:
            raise Parada(f"baixar: o Flow não carregou o vídeo ({ABERTURAS_DO_VIDEO} vezes)")
        print("Flow: o vídeo não carregou no player; fechado para abrir de novo")
        tocar(d, "Fechar", "fechar o vídeo que não carregou")
        time.sleep(PAUSA_ANTES_DE_REABRIR)


def abrir_o_video_novo(d, modelo):
    """
    No projeto: Vídeos → o mais novo. O título dele tem de ter o modelo do teste: com mais de uma
    versão (o Estender que o Rafael fez no vídeo do teste em 15/11 ficou junto do original), o robô
    passa pelas miniaturas das versões até o título dizer o modelo. Nunca baixa nem manda um vídeo
    de outro modelo (Parada). O player que não carrega é fechado e aberto de novo (ABERTURAS_DO_VIDEO).
    """
    _abrir_o_mais_novo(d)
    # O título com o modelo e a coluna das versões aparecem um pouco depois do player (visto em
    # 15/11: lido cedo demais, o vídeo parecia não ter versões); a versão estendida tem só o nome
    # no título, sem o modelo.
    xml = esperar(d, lambda x: modelo in (titulo_do_video(x) or []) or bool(versoes_do_video(x)), ESPERA_DA_VERSAO)
    if xml and modelo in (titulo_do_video(xml) or []):
        return
    for versao in versoes_do_video(xml or _tela(d)):
        d.click(*versao)
        if esperar(d, lambda x: modelo in (titulo_do_video(x) or []), ESPERA_DA_VERSAO):
            return
    raise Parada("baixar: o vídeo mais novo não é do modelo do teste")


# --- O Estender: a continuação do vídeo de 16 s (P246 1) ---

def posicao_no_player(xml):
    """(N, M) do "N de M" do player do vídeo aberto: a versão à vista e quantas há; None fora do vídeo aberto."""
    for el in ps.elementos(xml):
        valor = el["descricao"] or ""
        if el["pacote"] == PACOTE and (VIDEO_ABERTO.search(valor) or FALHA_NO_PLAYER.search(valor)):
            achado = re.search(r"\b(\d+) de (\d+)\b", valor)
            if achado:
                return int(achado.group(1)), int(achado.group(2))
    return None


def versoes_do_mais_novo(xml):
    """Quantas versões tem o quadro mais novo do projeto (o "…, 2 itens" depois do Estender); 0 sem quadro."""
    quadros = [el for el in ps.elementos(xml)
               if el["pacote"] == PACOTE and el["clicavel"] and VERSOES_NO_QUADRO.search(el["descricao"] or "")]
    if not quadros:
        return 0
    mais_novo = min(quadros, key=lambda el: (el["caixa"][1], el["caixa"][0]))
    return int(VERSOES_NO_QUADRO.search(mais_novo["descricao"]).group(1))


def _gerar_ligado(xml):
    """O Gerar do app está ligado? (O do Estender fica desligado com a caixa vazia, visto em 16/11/2026.)"""
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError:
        return False
    return any(no.get("package") == PACOTE and no.get("content-desc") == "Gerar" and no.get("enabled") == "true"
               for no in raiz.iter("node"))


def painel_do_estender(xml):
    """
    O painel do Estender aberto: {"caixa" (o centro da caixa do pedido), "texto" (o que está nela), "duracao" (o
    botão "Estender 8s"), "gerar" (o centro do Gerar), "gerar_ligado", "versoes" (o "N de M" do vídeo de cima, ou
    None)}; None sem ele.
    """
    elementos = [el for el in ps.elementos(xml) if el["pacote"] == PACOTE]
    caixa = next((el for el in elementos if el["classe"] == "EditText"), None)
    duracao = next((el for el in elementos
                    if re.fullmatch(r"estender\s+\d+\s*s", " ".join((el["descricao"] or "").split()), re.I)), None)
    gerar = next((el for el in elementos if el["descricao"] == "Gerar"), None)
    if not (caixa and duracao and gerar):
        return None
    de_cima = next((re.fullmatch(r"(\d+) de (\d+)", (el["descricao"] or "").strip()) for el in elementos
                    if re.fullmatch(r"\d+ de \d+", (el["descricao"] or "").strip())), None)
    return {"caixa": _centro(caixa), "texto": caixa["texto"], "duracao": " ".join(duracao["descricao"].split()),
            "gerar": _centro(gerar), "gerar_ligado": _gerar_ligado(xml),
            "versoes": (int(de_cima.group(1)), int(de_cima.group(2))) if de_cima else None}


def _comeco(texto):
    return " ".join((texto or "").split())[:40]


def pronto_para_estender(xml, continuacao):
    """"" quando o painel do Estender está como o robô quer (a continuação, os 8 s, uma versão só e o Gerar ligado);
    senão, o que falta (texto fixo)."""
    painel = painel_do_estender(xml)
    if not painel:
        return "o painel do Estender sumiu"
    if painel["versoes"] != (1, 1):
        return "o vídeo de cima não é o de uma versão só"
    if _comeco(painel["texto"]) != _comeco(continuacao):
        return "o texto da continuação não entrou"
    if painel["duracao"] != DURACAO_DO_ESTENDER:
        return "a duração não é a de 8 s"
    if not painel["gerar_ligado"]:
        return "o Gerar está desligado"
    return ""


def estender(d, continuacao):
    """
    No vídeo aberto (o original, com o modelo no título): Estender → a caixa → a continuação → confere o painel
    (pronto_para_estender) → Gerar, e espera o painel fechar. Parada no que falhar; antes do Gerar, sem gastar crédito.
    A caixa com outro texto de antes para (o robô não apaga às cegas); com a mesma continuação, segue.
    """
    tocar(d, "Estender", "estender")
    xml = esperar(d, lambda x: painel_do_estender(x) is not None)
    if not xml:
        raise Parada("estender: o painel do Estender não abriu")
    texto = painel_do_estender(xml)["texto"]
    if texto.strip() and _comeco(texto) != _comeco(continuacao):
        raise Parada("estender: a caixa já tinha outro texto de antes")
    if not texto.strip():
        ponto = ponto_parado(d, lambda x: (painel_do_estender(x) or {}).get("caixa"), "texto do Estender")
        if not ponto:
            raise Parada("estender: a caixa do pedido não apareceu")
        d.click(*ponto)
        time.sleep(1)
        ps.escrever(d, continuacao)
        xml = esperar(d, lambda x: _comeco((painel_do_estender(x) or {}).get("texto")) == _comeco(continuacao), 10)
        if not xml:
            raise Parada("estender: o texto não entrou na caixa")
    falta = pronto_para_estender(xml, continuacao)
    if falta:
        raise Parada(f"antes do Gerar do Estender: {falta}")
    d.click(*painel_do_estender(xml)["gerar"])
    if not esperar(d, lambda x: painel_do_estender(x) is None, ESPERA_DO_PAINEL):
        raise Parada("estender: o painel não fechou depois do Gerar")


def continuacao_na_tela(xml):
    """O vídeo aberto mostra a continuação do Estender: sendo gerada ("Gerando…") ou na coluna das versões."""
    return gerando(xml) or len(versoes_do_video(xml)) >= 2


def porcentagem_no_projeto(xml):
    """
    Um quadro do Flow com a porcentagem do que está sendo gerado ("45%"), com ou sem o "Gerando…" escrito: o do vídeo
    que o Estender continua mostra a porcentagem no projeto. A barra do player ("23%", SeekBar) não conta.
    """
    return any(el["pacote"] == PACOTE and el["classe"] != "SeekBar"
               and PORCENTAGEM.search(f"{el['texto']}\n{el['descricao']}") for el in ps.elementos(xml))


def esperar_a_extensao(d, guardar_telas=True):
    """
    No projeto (aberto de novo depois do Gerar do Estender): espera a versão estendida ficar pronta, o quadro mais novo
    com 2 versões ou mais e nada sendo gerado na tela (nem "Gerando…" nem a porcentagem num quadro), em PRONTO_SEGUIDAS
    leituras seguidas. A tela vai aos casos nos
    primeiros CASOS_DO_ESTENDER minutos (guardar_telas=False na produção do dia, como na espera dos 8 s). (os segundos
    até ficar pronta, "") ou, sem ela, (None, o porquê): ESPERA_DA_EXTENSAO, se não ficou em ESPERA_DA_GERACAO, ou
    SEM_CONTINUACAO, com o quadro mais novo de uma versão só e nada sendo gerado por ESPERA_SEM_CONTINUACAO s seguidos.
    """
    inicio, proximo_caso, seguidas, sem_continuacao = time.monotonic(), 0.0, 0, None
    while True:
        passado = time.monotonic() - inicio
        if guardar_telas and passado >= proximo_caso and proximo_caso < CASOS_DO_ESTENDER * INTERVALO_DOS_CASOS:
            casos_robo.guardar(d, "flow", "tela", f"esperando o Estender, aos {int(passado)} s", passo="flow estender")
            proximo_caso += INTERVALO_DOS_CASOS
        xml = _tela(d)
        if xml and tem_termos(xml):
            raise Parada("estender: tela de termos ou de consentimento; o robô nunca aceita pelo Rafael")
        versoes = versoes_do_mais_novo(xml) if xml else 0
        # O "Gerando…" escrito ou só a porcentagem no quadro: a continuação ainda está sendo feita.
        em_andamento = bool(xml) and (gerando(xml) or porcentagem_no_projeto(xml))
        if xml and not em_andamento and versoes >= 2:
            seguidas += 1
            if seguidas >= PRONTO_SEGUIDAS:
                return int(passado), ""
        else:
            seguidas = 0
        if xml and not em_andamento and versoes == 1:
            sem_continuacao = passado if sem_continuacao is None else sem_continuacao
            if passado - sem_continuacao >= ESPERA_SEM_CONTINUACAO:
                return None, SEM_CONTINUACAO
        else:
            sem_continuacao = None
        if passado >= ESPERA_DA_GERACAO:
            return None, ESPERA_DA_EXTENSAO
        time.sleep(PAUSA_DA_LEITURA)


def escolher_a_versao(d, estendida, modelo):
    """
    No vídeo aberto com mais de uma versão: a estendida (a última, "M de M" no player) ou a original (a 1ª, com o
    modelo no título). Passa pelas miniaturas das versões até ela ficar à vista; Parada sem ela.
    """
    def certa(xml):
        posicao = posicao_no_player(xml)
        if not posicao or posicao[1] < 2:
            return False
        if estendida:
            return posicao[0] == posicao[1]
        return posicao[0] == 1 and modelo in (titulo_do_video(xml) or [])

    xml = esperar(d, lambda x: len(versoes_do_video(x)) >= 2, ESPERA_DA_VERSAO)
    if not xml:
        raise Parada("estender: o vídeo não tem a versão estendida")
    if certa(xml):
        return
    for versao in versoes_do_video(xml):
        d.click(*versao)
        if esperar(d, certa, ESPERA_DA_VERSAO):
            return
    raise Parada(f"estender: a versão {'estendida' if estendida else 'original'} não ficou à vista")


def arquivos_novos(d):
    """Os vídeos (.mp4) que apareceram no celular depois da marca do Baixar: [(caminho, bytes)], o mais novo primeiro."""
    comando = ["find", *PASTAS_DO_BAIXAR, "-type", "f", "-name", "*.mp4", "-newer", MARCA_DO_BAIXAR,
               "-exec", "stat", "-c", "%Y %s %n", "{}", "+"]
    try:
        saida = d.shell(comando).output or ""
    except Exception:
        return []
    achados = []
    for linha in saida.splitlines():
        partes = linha.strip().split(" ", 2)
        # O arquivo com ponto na frente (o ".pending-…" do Android) ainda está sendo gravado.
        if len(partes) == 3 and partes[0].isdigit() and partes[1].isdigit() \
                and not os.path.basename(partes[2]).startswith("."):
            achados.append((int(partes[0]), int(partes[1]), partes[2]))
    return [(caminho, tamanho) for _, tamanho, caminho in sorted(achados, reverse=True)]


def pede_escolha(xml):
    """Depois da janela da resolução, o Flow pergunta outra coisa do tamanho ou o Android pede uma permissão? O robô não escolhe."""
    for el in ps.elementos(xml):
        if el["pacote"] in PACOTES_DE_PERMISSAO:
            return True
        if el["pacote"] == PACOTE and el["clicavel"] and ESCOLHA_NO_BAIXAR.search(f"{el['texto']} {el['descricao']}"):
            return True
    return False


def _centro(el):
    x1, y1, x2, y2 = el["caixa"]
    return (x1 + x2) // 2, (y1 + y2) // 2


def janela_do_baixar(xml):
    """
    A janela "Baixar vídeo": {"original", "1080p", "baixar"}; None sem ela. "original" e "1080p" são
    {"centro" (o botão redondo da linha), "marcada"}; o "1080p" é None quando falta, quando a linha
    dele fala em plano ou crédito ou quando a janela fala em crédito. "baixar" é o centro do botão
    que confirma a janela ("Baixar" ou, com o 1080p marcado, "Aumentar resolução e baixar"); None
    sem ele.
    """
    elementos = [el for el in ps.elementos(xml) if el["pacote"] == PACOTE]

    def texto(el):
        return " ".join(f"{el['texto']} {el['descricao']}".split()).casefold()

    def linha(achou):
        el = next((el for el in elementos if achou(texto(el))), None)
        if not el:
            return None
        x1, y1, x2, y2 = el["caixa"]
        na_linha = [outro for outro in elementos if x1 <= outro["caixa"][0] and outro["caixa"][2] <= x2
                    and y1 <= outro["caixa"][1] and outro["caixa"][3] <= y2]
        redondo = next((outro for outro in na_linha if outro["classe"] == "RadioButton"), None)
        if not redondo:
            return None
        return {"centro": _centro(redondo), "marcada": redondo["marcado"],
                "texto": " ".join(texto(outro) for outro in na_linha)}

    original = linha(lambda t: "tamanho original" in t)
    if not original:
        return None
    maior = linha(lambda t: t.startswith("1080p"))
    if maior and (CUSTO_OU_PLANO.search(maior["texto"]) or any(CREDITO.search(texto(el)) for el in elementos)):
        maior = None
    botao = next((el for el in elementos if el["classe"] == "Button" and BOTAO_DO_BAIXAR.fullmatch(texto(el))), None)
    return {"original": original, "1080p": maior, "baixar": _centro(botao) if botao else None}


def escolher_a_resolucao(d, xml):
    """
    Na janela do Baixar: marca o 1080p quando ele está livre (sem plano nem crédito na tela), confere
    que ficou marcado e toca no Baixar da janela; sem o 1080p livre, baixa no tamanho original, que
    vem marcado. A resolução escolhida ("1080p" ou "720p"). Nunca toca no 4K nem no plano. Pedido do
    Rafael (P229): DECISOES.md, Shopee Vídeo.
    """
    janela = janela_do_baixar(xml)
    if janela["1080p"] and not janela["1080p"]["marcada"]:
        d.click(*janela["1080p"]["centro"])
        xml = esperar(d, lambda x: bool(((janela_do_baixar(x) or {}).get("1080p") or {}).get("marcada")),
                      ESPERA_DA_JANELA_DO_BAIXAR)
        if not xml:
            raise Parada("baixar: o 1080p não ficou marcado; o robô não baixa sem conferir a resolução")
        janela = janela_do_baixar(xml)
    if janela["1080p"] and janela["1080p"]["marcada"]:
        escolhida = "1080p"
    elif janela["original"]["marcada"]:
        escolhida = "720p"
    else:
        raise Parada("baixar: nem o 1080p nem o tamanho original estão marcados; o robô não escolhe outra resolução")
    if not janela["baixar"]:
        raise Parada("baixar: a janela da resolução não tem o botão Baixar")
    d.click(*janela["baixar"])
    if not esperar(d, lambda x: janela_do_baixar(x) is None, ESPERA_PARA_A_JANELA_FECHAR):
        raise Parada("baixar: a janela da resolução não fechou depois do Baixar")
    return escolhida


def baixar(d):
    """
    No vídeo aberto: Mais opções → Baixar → (na janela da resolução, o 1080p quando ele vem sem
    custo; sem isso, o tamanho original) Baixar. (O caminho do arquivo no celular, quando ele para de
    crescer; a resolução escolhida, "" quando o Flow baixou sem perguntar.)
    """
    d.shell(["touch", MARCA_DO_BAIXAR])
    # A hora do arquivo baixado tem de passar a da marca.
    time.sleep(1.1)
    tocar(d, "Mais opções", "mais opções do vídeo")
    tocar(d, "Baixar", "baixar")
    janela = esperar(d, lambda x: janela_do_baixar(x) is not None, ESPERA_DA_JANELA_DO_BAIXAR)
    resolucao = escolher_a_resolucao(d, janela) if janela else ""
    fim, anterior = time.monotonic() + ESPERA_DO_BAIXAR, None
    while True:
        xml = _tela(d)
        if xml and (tem_termos(xml) or pede_escolha(xml)):
            raise Parada("baixar: o Flow pediu uma escolha (tamanho ou permissão); o robô não escolhe pelo Rafael")
        novos = arquivos_novos(d)
        if novos and novos[0][1] > 0 and novos[0] == anterior:
            return novos[0][0], resolucao
        anterior = novos[0] if novos else None
        if time.monotonic() >= fim:
            raise Parada("baixar: o arquivo do vídeo não apareceu no celular")
        time.sleep(2)


def puxar(d, remoto, local):
    """Traz o vídeo do celular para o servidor e tira do celular o arquivo e a marca do Baixar."""
    os.makedirs(os.path.dirname(local), exist_ok=True)
    try:
        d.pull(remoto, local)
    except Exception as e:
        raise Parada(f"baixar: o vídeo não veio do celular para o servidor ({type(e).__name__})")
    d.shell(["rm", "-f", remoto, MARCA_DO_BAIXAR])
    d.shell(["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", "file://" + remoto])
    if not os.path.exists(local) or not os.path.getsize(local):
        raise Parada("baixar: o vídeo não veio do celular para o servidor")


def ler_conferencia(texto):
    """{"mesmo": True, False ou None, "diferencas", "defeitos"} da resposta da IA (None: não deu para ler)."""
    achado = re.search(r"\{.*\}", texto or "", re.S)
    try:
        dados = json.loads(achado.group(0)) if achado else None
    except ValueError:
        dados = None
    if not isinstance(dados, dict):
        return {"mesmo": None, "diferencas": "", "defeitos": ""}
    mesmo = dados.get("mesmo_produto")
    return {"mesmo": mesmo if isinstance(mesmo, bool) else None,
            "diferencas": " ".join(str(dados.get("diferencas") or "").split())[:200],
            "defeitos": " ".join(str(dados.get("defeitos") or "").split())[:200]}


def conferir_o_video(caminho, foto):
    """A conferência da IA: o produto do vídeo é o mesmo da foto do anúncio? (ler_conferencia)"""
    try:
        with open(foto, "rb") as arquivo:
            imagem = arquivo.read()
        texto = asyncio.run(api_gemini.analisar_video_gemini(caminho, PEDIDO_DA_CONFERENCIA,
                                                             imagens=[(imagem, "image/jpeg")]))
    except Exception:
        texto = None
    return ler_conferencia(texto)


def _palavras_da_fala(texto):
    """[(a palavra sem acento e em minúsculas, como foi escrita)] do texto, na ordem, sem a pontuação."""
    palavras = []
    for original in re.findall(r"\w+", str(texto or "")):
        normal = unicodedata.normalize("NFKD", original).encode("ascii", "ignore").decode().lower()
        if normal:
            palavras.append((normal, original.lower()))
    return palavras


def _a_pedida(palavra, pedidas):
    """
    A palavra da fala pedida que a ouvida é, igual ou quase ("pra" e "para": o reconhecimento de voz erra uma letra
    à toa); None quando ela não parece nenhuma.
    """
    if palavra in pedidas:
        return palavra
    parecidas = [(difflib.SequenceMatcher(None, palavra, pedida).ratio(), pedida) for pedida in pedidas]
    nota, pedida = max(parecidas, default=(0, None))
    return pedida if nota >= FALA_PARECIDA else None


# O sinal de que quem chama a conferência da fala ainda não ouviu o vídeo (None já quer dizer "não deu para ouvir").
_SEM_OUVIR = object()


def conferir_a_fala(arquivo, fala, ouvidas=_SEM_OUVIR):
    """
    A fala ouvida no vídeo pronto comparada com a pedida (P248 1), pelo reconhecimento de voz das legendas:
    {"situacao": "igual", "embolada", "cortada", "embolada e cortada", "sem fala" ou None (não deu para ouvir),
    "estranhas": as palavras ouvidas que não estão na fala pedida, "aos": o segundo da 1ª delas, "faltou": as últimas
    palavras da fala pedida que não se ouvem, "ouvidas": quantas palavras se ouvem}. Embolada: palavras fora da
    fala pedida (a 1ª amostra disse "Vou feitecer já essa sela"); cortada: o fim da fala pedida não se ouve, e a
    fala vai até o fim do vídeo. ouvidas: as palavras de videos.palavras_faladas, quando quem chama já ouviu o vídeo.
    """
    pedidas = _palavras_da_fala(fala)
    normais = [normal for normal, _original in pedidas]
    resultado = {"situacao": None, "estranhas": [], "aos": None, "faltou": [], "ouvidas": 0}
    if not pedidas:
        ouvidas = None
    elif ouvidas is _SEM_OUVIR:
        ouvidas = videos.palavras_faladas(arquivo)
    if ouvidas is None:
        return resultado
    ditas = [(inicio, fim, normal, original) for inicio, fim, texto in ouvidas
             for normal, original in _palavras_da_fala(texto)]
    resultado["ouvidas"] = len(ditas)
    if not ditas:
        return dict(resultado, situacao="sem fala")
    lidas = [_a_pedida(normal, normais) for _inicio, _fim, normal, _original in ditas]
    # As palavras curtas ("e", "o", "a") ficam de fora: o reconhecimento de voz as troca à toa.
    estranhas = [(inicio, original) for (inicio, _fim, normal, original), lida in zip(ditas, lidas)
                 if lida is None and len(normal) >= LETRAS_DA_ESTRANHA]
    # O que faltou no fim: as palavras pedidas depois da última que se ouve na ordem da fala.
    alinhadas = [lida or normal for lida, (_inicio, _fim, normal, _original) in zip(lidas, ditas)]
    blocos = difflib.SequenceMatcher(None, normais, alinhadas, autojunk=False).get_matching_blocks()
    ultima = max((bloco.a + bloco.size for bloco in blocos if bloco.size), default=0)
    faltou = [original for _normal, original in pedidas[ultima:]]
    duracao = videos.duracao(arquivo)
    embolada = len(estranhas) >= ESTRANHAS_DA_FALA_EMBOLADA
    cortada = bool(faltou) and bool(duracao) and ditas[-1][1] >= duracao - FOLGA_DO_FIM_DA_FALA
    situacao = ("embolada e cortada" if embolada and cortada else "embolada" if embolada
                else "cortada" if cortada else "igual")
    return dict(resultado, situacao=situacao, estranhas=[original for _, original in estranhas][:8],
                aos=round(estranhas[0][0]) if estranhas else None, faltou=faltou[:8])


def texto_da_fala(conferida):
    """A linha da conferência da fala na legenda da amostra (P248 1)."""
    situacao = conferida.get("situacao")
    if situacao is None:
        return "👂 Fala no vídeo: não deu para ouvir"
    if situacao == "sem fala":
        return "⚠️ Fala no vídeo: nenhuma palavra ouvida"
    estranhas = ", ".join(f'"{palavra}"' for palavra in conferida.get("estranhas") or [])
    partes = []
    if "embolada" in situacao:
        partes.append(f"embolada aos {conferida.get('aos')} s (ouvi {estranhas}, que não estão na fala pedida)")
    if "cortada" in situacao:
        partes.append(f"cortada no fim (faltou \"{' '.join(conferida.get('faltou') or [])}\")")
    if partes:
        return "⚠️ Fala no vídeo: " + "; ".join(partes)
    return (f"👂 Fala no vídeo: igual à pedida ({conferida.get('ouvidas', 0)} palavras ouvidas"
            + (f"; fora dela só {estranhas}" if estranhas else "") + ")")


# O corte do parado do vídeo de IA de 16 s (P255 1): o silêncio de mais de PARADO_MAXIMO s (no começo, entre as falas
# e no fim) sai, e ficam FOLGA_DA_FALA s antes e depois de cada fala (FOLGA_DO_FIM depois da última, para o vídeo não
# acabar seco). Um trecho sim, um não, entra com um zoom leve (ZOOM_DO_CORTE), para o pulo do corte parecer de
# propósito, como os criadores fazem. Menos de CORTE_MINIMO s parado não vale o corte. Por enquanto só na amostra.
# Escolha do Rafael (P255 1): DECISOES.md, Shopee Vídeo.
PARADO_MAXIMO = 1.0
FOLGA_DA_FALA = 0.3
FOLGA_DO_FIM = 0.6
ZOOM_DO_CORTE = 1.08
CORTE_MINIMO = 0.5
# Na conta do tempo com fala, as palavras separadas por até este tanto de segundos são da mesma fala.
PAUSA_DA_FALA = 0.5


def _falas(palavras, duracao, juntar):
    """[[início, fim]] das falas: as palavras ouvidas, em ordem, juntas quando a pausa entre elas é de até `juntar`."""
    blocos = []
    for inicio, fim in sorted((max(0.0, i), min(duracao, f)) for i, f, _palavra in palavras or () if f > i):
        if blocos and inicio - blocos[-1][1] <= juntar:
            blocos[-1][1] = max(blocos[-1][1], fim)
        else:
            blocos.append([inicio, fim])
    return blocos


def tempo_com_fala(palavras, duracao):
    """Os segundos do vídeo em que a pessoa está falando (as pausas de até PAUSA_DA_FALA s contam como fala)."""
    return round(sum(fim - inicio for inicio, fim in _falas(palavras, duracao, PAUSA_DA_FALA)), 1)


def trechos_sem_o_parado(palavras, duracao):
    """
    [(início, fim)] dos trechos do vídeo que ficam, na ordem, sem o silêncio de mais de PARADO_MAXIMO s (P255 1); []
    quando não há o que cortar (sem palavra ouvida, sem a duração ou menos de CORTE_MINIMO s parado).
    """
    blocos = _falas(palavras, duracao, PARADO_MAXIMO) if duracao else []
    trechos = []
    for numero, (inicio, fim) in enumerate(blocos):
        ultimo = numero == len(blocos) - 1
        comeco = 0.0 if numero == 0 and inicio <= PARADO_MAXIMO else max(0.0, inicio - FOLGA_DA_FALA)
        if ultimo and duracao - fim <= PARADO_MAXIMO:
            final = duracao
        else:
            final = min(duracao, fim + (FOLGA_DO_FIM if ultimo else FOLGA_DA_FALA))
        trechos.append((round(comeco, 3), round(final, 3)))
    if not trechos or duracao - sum(fim - inicio for inicio, fim in trechos) < CORTE_MINIMO:
        return []
    return trechos


def cortar_o_parado(arquivo, palavras):
    """
    O vídeo de IA sem o parado (P255 1), gravado ao lado do original ("..._sem_o_parado.mp4"): {"arquivo": o caminho
    do cortado (None quando não cortou), "antes" e "depois": as durações, "cortes": quantos pedaços parados saíram,
    "motivo": por que não cortou ("" quando cortou)}. Os trechos de vídeo entram um sim, um não, com o zoom leve.
    """
    antes = round(videos.duracao(arquivo) or 0.0, 1)
    resultado = {"arquivo": None, "antes": antes, "depois": antes, "cortes": 0, "motivo": ""}
    if palavras is None:
        return dict(resultado, motivo="não deu para ouvir a fala")
    trechos = trechos_sem_o_parado(palavras, antes)
    if not trechos:
        return dict(resultado, motivo="nada parado para cortar")
    destino = os.path.splitext(arquivo)[0] + "_sem_o_parado.mp4"
    montagem = [(inicio, fim, 1.0, ZOOM_DO_CORTE if numero % 2 else 1.0)
                for numero, (inicio, fim) in enumerate(trechos)]
    motivo = videos.com_cortes_e_ritmo(arquivo, montagem, destino)
    if motivo:
        return dict(resultado, motivo=motivo)
    cortes = len(trechos) - 1 + (trechos[0][0] > 0) + (trechos[-1][1] < antes)
    return dict(resultado, arquivo=destino, depois=round(sum(fim - inicio for inicio, fim in trechos), 1),
                cortes=cortes)


def _segundos(valor):
    """Os segundos com vírgula ("12,3 s")."""
    return f"{valor:.1f}".replace(".", ",") + " s"


def texto_do_corte(corte, com_fala):
    """As linhas do tempo com fala e do corte do parado na legenda da amostra (P255 1)."""
    linhas = []
    if com_fala is not None:
        linhas.append(f"⏱️ Com fala: {_segundos(com_fala)} dos {_segundos(corte['antes'])} do vídeo")
    if corte.get("arquivo"):
        linhas.append(f"✂️ Parado cortado: de {_segundos(corte['antes'])} para {_segundos(corte['depois'])} "
                      f"({corte['cortes']} pedaço(s) parado(s) tirado(s), com um zoom leve depois de cada corte); "
                      "o vídeo sem o corte vem logo abaixo, para comparar")
    else:
        linhas.append(f"✂️ Corte do parado: {corte.get('motivo') or 'não saiu'}")
    return linhas


def legenda_do_video(teste, modelo, custo, conferencia):
    """O texto que vai com o vídeo no privado do Rafael (até 1000 letras): o modelo, o custo, o produto, a cena e a conferência."""
    numero = numero_do_modelo(modelo)
    if conferencia["mesmo"] is True:
        conferido = "o produto é o mesmo da foto do anúncio"
    elif conferencia["mesmo"] is False:
        conferido = f"o produto muda: {conferencia['diferencas'] or 'sem detalhes'}"
    else:
        conferido = "não deu para conferir"
    linhas = [f"🎬 Teste do Flow (P229 1): vídeo {numero} de {len(MODELOS_DO_TESTE)}",
              f"🤖 Modelo: {modelo} ({custo} créditos de IA)",
              f"📦 Produto: {teste.get('nome', '')}",
              f"🎥 Cena: {teste.get('cena', '')}",
              f"🎭 Estilo: {ESTILOS.get(teste.get('estilo'), ESTILOS[ESTILO_PADRAO])}",
              f"🔎 A IA conferiu: {conferido}"]
    video = (teste.get("videos") or {}).get(modelo) or {}
    resolucao = {"1080p": "1080p (aumentada pelo Flow no Baixar)", "720p": "720p (o tamanho original)"}.get(
        video.get("resolucao"))
    if resolucao:
        linhas.append(f"📐 Resolução: {resolucao}" + (f", {video['tamanho']}" if video.get("tamanho") else ""))
    if conferencia["defeitos"]:
        linhas.append(f"⚠️ O que parece IA: {conferencia['defeitos']}")
    linhas.append("Nada foi postado: o vídeo é só para você comparar os modelos.")
    if numero == len(MODELOS_DO_TESTE):
        linhas.append("Este é o último dos 3: o Claude vai perguntar qual modelo usar.")
    return "\n".join(linhas)[:1000]


def link_do_anuncio(link):
    """O endereço do anúncio para o Rafael abrir (https://shopee.com.br/product/<loja>/<item>); o link da fonte quando não dá para achar."""
    try:
        return api_shopee.produto_do_link(asyncio.run(api_shopee.link_para_converter(link))) or link
    except Exception:
        return link


def legenda_do_anuncio(teste, modelo):
    """O texto da foto do anúncio que vai logo depois do vídeo: para comparar, com o link do anúncio."""
    return (f"🖼️ Foto do anúncio, para comparar com o vídeo {numero_do_modelo(modelo)} de "
            f"{len(MODELOS_DO_TESTE)} do teste do Flow\n🔗 Anúncio: {link_do_anuncio(teste.get('link', ''))}")[:1000]


def mandar_ao_rafael(teste, modelo, custo, local):
    """
    Confere o vídeo pela IA e manda no privado do Rafael (sem o celular), e logo depois a foto do
    anúncio com o link dele, para ele comparar (pedido dele, 15/11: DECISOES.md, Shopee Vídeo).
    0 mandado, 1 não.
    """
    conferencia = conferir_o_video(local, teste["foto"])
    print(f"Flow: conferência da IA: {ROTULOS_DA_CONFERENCIA[conferencia['mesmo']]}")
    try:
        ok = avisar_rafael.mandar_video(local, legenda_do_video(teste, modelo, custo, conferencia))
    except Exception as e:
        print(f"Flow: o envio ao privado falhou ({type(e).__name__}); o próximo teste manda de novo")
        return 1
    if not ok:
        print("Flow: o Telegram não aceitou o vídeo; o próximo teste manda de novo")
        return 1
    marcar_video(modelo, estado="enviado", enviado_em=agora(), mesmo_produto=conferencia["mesmo"])
    print("Flow: vídeo mandado no privado do Rafael")
    try:
        foto = avisar_rafael.mandar_foto(teste["foto"], legenda_do_anuncio(teste, modelo))
    except Exception:
        foto = False
    print("Flow: foto e link do anúncio mandados" if foto else "Flow: a foto do anúncio não foi ao privado")
    return 0


def mandar_o_baixado(modelo, custo):
    """Manda o vídeo do modelo que já está no servidor (estado baixado). 0 mandado, 1 não."""
    teste = teste_guardado()
    video = (teste.get("videos") or {}).get(modelo) or {}
    if video.get("estado") != "baixado" or not os.path.exists(video.get("arquivo") or ""):
        print("Flow: o vídeo baixado não está no servidor")
        return 1
    return mandar_ao_rafael(teste, modelo, custo, video["arquivo"])


def foto_na_galeria(d, foto):
    """Põe a foto do produto na galeria do celular, com nome novo; o nome do arquivo ("" se não apareceu)."""
    with open(foto, "rb") as arquivo:
        return ps.por_foto_na_galeria(d, arquivo.read(), nome=f"flow_{int(time.time())}")


def tirar_da_galeria(d, nome):
    """Tira a foto do produto da galeria e avisa a galeria."""
    if not nome:
        return
    caminho = f"{ps.GALERIA}/{nome}"
    d.shell(["rm", "-f", caminho])
    d.shell(["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", "file://" + caminho])


def no_flow(d, pedido, modelo, custo, local, marcar, sem_gerar=False, so_baixar=False, guardar_telas=True):
    """
    O caminho no Flow, com a trava do celular na mão e a tela já conferida: a foto do pedido na
    galeria, o projeto do robô, o pedido (a foto, o texto e o modelo) conferido na tela, o Gerar e,
    com o vídeo pronto, o Baixar até o arquivo chegar ao servidor em local. marcar(**campos) guarda o
    andamento: "gerando" logo depois do Gerar (com o custo e a hora) e "baixado" com o arquivo no
    servidor. so_baixar=True: o vídeo já foi gerado e só falta baixar. Devolve True (o pedido pronto,
    com sem_gerar, ou o vídeo baixado) ou False (o vídeo não ficou pronto a tempo: a próxima vez
    baixa); Parada com o passo que parou. A foto sai da galeria no fim, dê certo ou não.
    guardar_telas: a tela da espera do vídeo vai aos casos de minuto em minuto (esperar_o_video).
    """
    nome_na_galeria = ""
    if not so_baixar:
        nome_na_galeria = foto_na_galeria(d, pedido["foto"])
        if not nome_na_galeria:
            raise Parada("celular: a foto do produto não apareceu na galeria; nada foi tocado no Flow")
    try:
        if abrir_o_projeto(d, saldo_minimo=None if so_baixar else 0 if sem_gerar else custo):
            print(f"Flow: o projeto {PROJETO_DO_ROBO} não estava na lista; criado com esse nome e aberto")
        else:
            print("Flow: aberto no projeto do robô")
        if not so_baixar:
            xml = montar_o_pedido(d, pedido["prompt"], modelo, custo)
            falta = pronto_para_gerar(xml, pedido["prompt"], modelo, custo)
            if falta:
                raise Parada(f"antes do Gerar: {falta}")
            print(f"Flow: pedido pronto (foto, texto, {modelo}, {custo} créditos)")
            if sem_gerar:
                casos_robo.guardar(d, "flow", "tela", "pedido pronto, sem gerar", passo="flow sem gerar")
                print("Flow: sem gerar; a tela do pedido pronto foi guardada")
                return True
            tocar(d, "Gerar", "gerar")
            marcar(custo=custo, gerado_em=agora(), estado="gerando")
            print(f"Flow: Gerar tocado ({modelo}, {custo} créditos)")
        pronto = esperar_o_video(d, ja_gerado=so_baixar, guardar_telas=guardar_telas)
        if pronto is None:
            print(f"Flow: o vídeo não ficou pronto em {ESPERA_DA_GERACAO // 60} min; a próxima vez baixa")
            marcar(espera=ESPERA_DOS_8_S)
            return False
        print(f"Flow: vídeo pronto ({pronto} s esperando)")
        abrir_o_video_novo(d, modelo)
        print("Flow: vídeo aberto (o modelo conferido no título)")
        remoto, resolucao = baixar(d)
        puxar(d, remoto, local)
        largura, altura = asyncio.run(videos.dimensoes(local, timeout=30))
        marcar(estado="baixado", arquivo=local, resolucao=resolucao,
               tamanho=f"{largura}x{altura}" if largura and altura else "")
        print(f"Flow: vídeo baixado ({resolucao or 'sem a janela da resolução'}, "
              f"{os.path.getsize(local) / 1e6:.1f} MB, {videos.duracao(local):.0f} s)")
        return True
    finally:
        tirar_da_galeria(d, nome_na_galeria)


def no_flow_longo(d, pedido, modelo, custo, local, marcar, sem_gerar=False, guardar_telas=True):
    """
    O vídeo de 16 s (P246 1) no Flow, com a trava do celular na mão e a tela já conferida, em etapas que a vez
    seguinte retoma pelo estado do pedido: o pedido e o Gerar dos 8 s ("gerando"), o Estender com a continuação
    ("estendendo", com o custo das duas partes) e o Baixar da versão estendida ("baixado"), juntando a original e a
    continuação quando o Flow baixa só a continuação. Nunca dois Gerar para a mesma parte: o vídeo que já tem a
    versão estendida não é estendido de novo. Depois do Gerar do Estender, o robô só sai do vídeo com a continuação à
    vista (ESPERA_DA_CONTINUACAO). True com o vídeo no servidor (ou o pedido pronto, com sem_gerar); False quando uma
    parte não ficou pronta a tempo (a próxima vez continua; o porquê vai em "espera"); Parada com o passo que parou.
    A foto sai da galeria no fim, dê certo ou não. guardar_telas: as telas do Estender vão aos casos (False na
    produção do dia, P247 1: todo dia, elas tirariam do servidor os casos das falhas, que ficam no máximo 30).
    """
    estado = pedido.get("estado")
    nome_na_galeria = ""
    if estado not in ("gerando", "estendendo"):
        nome_na_galeria = foto_na_galeria(d, pedido["foto"])
        if not nome_na_galeria:
            raise Parada("celular: a foto do produto não apareceu na galeria; nada foi tocado no Flow")
    try:
        # Antes do Gerar dos 8 s, o saldo paga as duas partes: os 8 s e o Estender.
        gerar = estado not in ("gerando", "estendendo")
        if abrir_o_projeto(d, saldo_minimo=(0 if sem_gerar else custo + CUSTO_DO_ESTENDER) if gerar else None):
            print(f"Flow: o projeto {PROJETO_DO_ROBO} não estava na lista; criado com esse nome e aberto")
        else:
            print("Flow: aberto no projeto do robô")
        if gerar:
            xml = montar_o_pedido(d, pedido["prompt"], modelo, custo)
            falta = pronto_para_gerar(xml, pedido["prompt"], modelo, custo)
            if falta:
                raise Parada(f"antes do Gerar: {falta}")
            print(f"Flow: pedido dos 8 s pronto (foto, texto, {modelo}, {custo} créditos)")
            if sem_gerar:
                casos_robo.guardar(d, "flow", "tela", "pedido pronto, sem gerar", passo="flow sem gerar")
                print("Flow: sem gerar; a tela do pedido pronto foi guardada")
                return True
            tocar(d, "Gerar", "gerar")
            marcar(custo=custo, gerado_em=agora(), estado="gerando")
            print(f"Flow: Gerar dos 8 s tocado ({modelo}, {custo} créditos)")
        if estado != "estendendo":
            pronto = esperar_o_video(d, ja_gerado=estado == "gerando", guardar_telas=False)
            if pronto is None:
                print(f"Flow: os 8 s não ficaram prontos em {ESPERA_DA_GERACAO // 60} min; a próxima vez estende")
                marcar(espera=ESPERA_DOS_8_S)
                return False
            print(f"Flow: os 8 s prontos ({pronto} s esperando)")
            abrir_o_video_novo(d, modelo)
            ja_estendido = bool(esperar(d, lambda x: len(versoes_do_video(x)) >= 2, ESPERA_DA_VERSAO))
            if ja_estendido:
                print("Flow: o vídeo já tinha a versão estendida; o robô não estende de novo")
            else:
                estender(d, pedido["continuacao"])
                print(f"Flow: Gerar do Estender tocado (8 s, {CUSTO_DO_ESTENDER} créditos)")
            # Anotado logo depois do toque (o crédito pode ter ido): o vídeo nunca é estendido de novo.
            marcar(estado="estendendo", estendido_em=agora(), custo=custo + CUSTO_DO_ESTENDER)
            if not ja_estendido:
                # O Flow fechado antes de mostrar a continuação pode perdê-la (ESPERA_DA_CONTINUACAO).
                if not esperar(d, continuacao_na_tela, ESPERA_DA_CONTINUACAO):
                    raise Parada("estender: a continuação não apareceu sendo gerada no vídeo")
                print("Flow: a continuação está sendo gerada")
                time.sleep(PAUSA_DEPOIS_DA_CONTINUACAO)
            if guardar_telas:
                casos_robo.guardar(d, "flow", "tela", "depois do Gerar do Estender", passo="flow estender")
            # De volta ao projeto, do alto, onde o quadro do vídeo mostra as versões.
            abrir_o_projeto(d)
        pronto, porque = esperar_a_extensao(d, guardar_telas=guardar_telas)
        if pronto is None:
            print(f"Flow: a versão estendida não ficou pronta ({porque}); a próxima vez baixa")
            marcar(espera=porque)
            return False
        print(f"Flow: versão estendida pronta ({pronto} s esperando)")
        _abrir_o_mais_novo(d)
        escolher_a_versao(d, True, modelo)
        remoto, resolucao = baixar(d)
        puxar(d, remoto, local)
        segundos = videos.duracao(local)
        if segundos < DURACAO_ESTENDIDA:
            # O Flow baixou só a continuação: a original vem também, e as duas são juntadas no servidor.
            continuacao, original = f"{local}.continuacao.mp4", f"{local}.original.mp4"
            os.replace(local, continuacao)
            try:
                escolher_a_versao(d, False, modelo)
                remoto, _ = baixar(d)
                puxar(d, remoto, original)
                # O Baixar que trouxe a mesma versão duas vezes não vira um vídeo com a original repetida.
                if videos.calcular_hash_video(original) == videos.calcular_hash_video(continuacao):
                    raise Parada("juntar as duas partes: o Baixar trouxe a mesma versão duas vezes")
                falha = videos.juntar([original, continuacao], local)
            finally:
                for parte in (continuacao, original):
                    if os.path.exists(parte):
                        os.remove(parte)
            if falha:
                raise Parada(f"juntar as duas partes: {falha}")
            print("Flow: o Flow baixou só a continuação; a original e a continuação foram juntadas")
            segundos = videos.duracao(local)
        largura, altura = asyncio.run(videos.dimensoes(local, timeout=30))
        marcar(estado="baixado", arquivo=local, resolucao=resolucao, duracao=round(segundos),
               tamanho=f"{largura}x{altura}" if largura and altura else "")
        print(f"Flow: vídeo de {segundos:.0f} s baixado ({resolucao or 'sem a janela da resolução'}, "
              f"{os.path.getsize(local) / 1e6:.1f} MB)")
        return True
    finally:
        tirar_da_galeria(d, nome_na_galeria)


def no_celular(teste, modelo, custo, sem_gerar, so_baixar=False):
    """
    O teste no celular, com a trava na mão: a tela, a foto, o Flow, o Gerar e, com o vídeo pronto,
    o Baixar até o arquivo chegar ao servidor (estado baixado). so_baixar=True: o vídeo do modelo foi
    gerado num teste anterior e só falta baixar. 0 deu certo, 1 parou.
    """
    if celular_robo.tela_acesa() is False:
        ps.conectar(celular=True).screen_on()
        time.sleep(2)
    if celular_robo.tela_acesa() is False or celular_robo.tela_de_bloqueio():
        print("celular: a tela está apagada ou na tela de bloqueio; nada foi tocado")
        return 1
    d = ps.conectar(celular=True)
    local = os.path.join(PASTA, f"video_{numero_do_modelo(modelo)}.mp4")
    try:
        feito = no_flow(d, teste, modelo, custo, local, lambda **campos: marcar_video(modelo, **campos),
                        sem_gerar=sem_gerar, so_baixar=so_baixar)
    except SemCreditos as e:
        print(f"Flow: {e}; nada foi gerado")
        return 1
    except Parada as e:
        casos_robo.guardar(d, "flow", "parou", str(e), passo="flow")
        print(f"Flow: parou: {e}")
        return 1
    return 0 if feito else 1


# --- A produção: 1 vídeo de IA por dia, que vira rascunho do robô (P232 1) ---
# O andamento do vídeo do dia fica na chave do Flow, em "producao": a data, o estado, o nome que o vídeo de IA tem entre
# os vídeos do robô ("id_video"), o produto ("link", "nome", "item", "valor") e de onde ele veio ("origem": a lista da
# API de afiliado, P234 1), o pedido da IA ("estilo", "prompt", "cena"; no vídeo de 16 s, P247 1, "longa", a
# "continuacao" do Estender e a "fala"), a foto e o vídeo no servidor e as conferências (a da IA e, no de 16 s, a da
# fala, "fala_conferida"). Os estados: "parou" (antes do Gerar, sem gastar crédito) e "sem foto" (a IA não achou boa
# nenhuma das fotos desta vez, e há outros produtos para olhar), que tentam de novo no dia, até
# TENTATIVAS_ANTES_DO_GERAR; "sem produto" (nenhum produto da lista serve hoje), "gerando" (o Gerar foi tocado e falta o
# vídeo chegar ao servidor; no de 16 s, falta também o Estender), "estendendo" (no de 16 s, o Gerar do Estender foi
# tocado e falta baixar), "baixado" (falta a conferência), "pronto" (espera o rascunho), "descartado" (a IA viu outro
# produto no vídeo, ou o Flow não o entregou), "usado" (virou rascunho), "desistiu" (não virou rascunho em
# TENTATIVAS_DO_RASCUNHO) e "sem créditos" (o saldo do Flow não pagava o vídeo, SEM_CREDITOS). O robô escolhe o produto
# pelas regras dele e chama a produção na rodada dele, com a trava do celular na mão. Escolhas do Rafael (15/11/2026,
# P232 1 e P234 1; 17/11/2026, P247 1): DECISOES.md.
ESTADOS_PENDENTES = ("gerando", "estendendo", "baixado")
ESTADOS_DO_DIA_ACABADO = ("sem produto", "pronto", "descartado", "usado", "desistiu")
# O saldo do Flow não pagava o vídeo (SemCreditos): nada foi gerado, e o robô fica nos vídeos dos grupos até o
# crédito voltar (pedido do Rafael, 19/11/2026). Não fecha o dia: o saldo é lido de novo mais tarde.
SEM_CREDITOS = "sem créditos"
# A escolha do produto pela lista da API de afiliado (P234 1) vai sempre do que paga mais para o que paga menos:
# sem uma memória, o produto que não deu certo num dia seria o 1º de novo no dia seguinte. Ficam de fora o produto
# que já teve um vídeo gerado (itens_gerados: virou rascunho, foi recusado ou descartado) e o de foto que a IA não
# achou boa para o vídeo (fotos_recusadas). Só os números dos produtos, os ITENS_LEMBRADOS mais novos de cada lista.
ITENS_LEMBRADOS = 600


def producao():
    """O andamento do vídeo de IA do dia ({} sem nenhum)."""
    return dict((db.ler_config(CHAVE, {}) or {}).get("producao") or {})


def guardar_producao(**campos):
    """Grava os campos no andamento do vídeo do dia."""
    db.atualizar_config(CHAVE, lambda dados: dados.setdefault("producao", {}).update(campos))


def _o_do_robo_acabou(atual):
    """
    O andamento do vídeo do dia do robô fechou o dia dele? Gerado, num estado que acaba o dia ou sem mais tentativas
    antes do Gerar. O "sem produto" sem a lista de onde veio é o da escolha antiga, pelos vídeos da fonte, que a
    P234 1 trocou pela lista da API de afiliado: não fecha o dia.
    """
    estado = atual.get("estado")
    if estado == "sem produto" and not atual.get("origem"):
        return False
    return bool(estado in ESTADOS_DO_DIA_ACABADO or atual.get("gerado_em")
                or atual.get("tentativas_de_gerar", 0) >= TENTATIVAS_ANTES_DO_GERAR)


def o_do_robo_saiu(dia, atual=None):
    """
    O vídeo de IA do dia do robô (P232 1) já saiu no dia (ou desistiu)? O andamento do Preparar 1 Agora ⚡ (do_botao,
    P243) guarda a resposta do andamento que veio antes dele (do_robo_fechado).
    """
    atual = producao() if atual is None else atual
    if atual.get("data") != dia:
        return False
    if atual.get("do_botao"):
        return bool(atual.get("do_robo_fechado"))
    return _o_do_robo_acabou(atual)


def gerados_no_dia(dia, atual=None):
    """
    Quantos Gerar o Flow teve no dia, o do robô e os do Preparar 1 Agora ⚡ (P243): o número passa de um andamento ao
    seguinte do mesmo dia. O andamento gerado conta pelo menos 1 (o de antes desta conta não a tem).
    """
    atual = producao() if atual is None else atual
    if atual.get("data") != dia:
        return 0
    return max(int(atual.get("gerados_no_dia") or 0), 1 if atual.get("gerado_em") else 0)


def recomecar_producao(dia, **campos):
    """
    Um andamento novo para o vídeo do dia, no lugar do de antes (os arquivos de antes saem do servidor). Do de antes,
    no mesmo dia, ficam quantos Gerar o dia já teve e, no do Preparar 1 Agora ⚡ (do_botao), se o vídeo do dia do
    robô já tinha saído.
    """
    anterior = producao()
    for nome in os.listdir(PASTA) if os.path.isdir(PASTA) else []:
        if nome.startswith("producao_"):
            try:
                os.remove(os.path.join(PASTA, nome))
            except OSError:
                pass
    novo = dict(campos, data=dia, gerados_no_dia=gerados_no_dia(dia, anterior))
    if novo.get("do_botao"):
        novo["do_robo_fechado"] = o_do_robo_saiu(dia, anterior)
    db.atualizar_config(CHAVE, lambda dados: dados.update(producao=novo))


def itens_gerados():
    """Os produtos que já tiveram um vídeo de IA gerado (os números deles): não ganham outro."""
    return [str(item) for item in (db.ler_config(CHAVE, {}) or {}).get("itens_gerados") or []]


def fotos_recusadas():
    """Os produtos cuja foto do anúncio a IA não achou boa para o vídeo (os números deles): não voltam à IA."""
    return [str(item) for item in (db.ler_config(CHAVE, {}) or {}).get("fotos_recusadas") or []]


def _lembrar(lista, item):
    """Põe o produto no fim da lista da chave do Flow (itens_gerados ou fotos_recusadas), sem repetir."""
    if not item:
        return

    def alterar(dados):
        dados[lista] = ([i for i in dados.get(lista) or [] if str(i) != str(item)] + [str(item)])[-ITENS_LEMBRADOS:]
    db.atualizar_config(CHAVE, alterar)


def lembrar_item_gerado(item):
    """O produto teve um vídeo gerado no Flow (o crédito foi gasto): fica de fora das próximas escolhas."""
    _lembrar("itens_gerados", item)


def lembrar_foto_recusada(item):
    """A IA disse que a foto do anúncio do produto não serve para o vídeo: ele fica fora das próximas escolhas."""
    _lembrar("fotos_recusadas", item)


def comecar_producao(dia, escolhido, tentativas_de_gerar, do_botao=False):
    """
    Guarda o pedido do vídeo do dia (escolhido: o pedido_para_o_anuncio com o nome do vídeo de IA entre os
    vídeos do robô, "id", o produto, "item" e "valor", e de onde ele veio, "origem"), no estado "escolhido". A foto
    vai a um arquivo ao lado dos vídeos; o banco fica com o caminho. O pedido de 16 s (P247 1), com a "continuacao"
    do Estender, fica "longa", com a fala, e tem um jeito só, fora da lista dos estilos dos últimos vídeos, a das
    amostras de 8 s (estilos_recentes), onde entra o estilo do pedido de 8 s. do_botao: o vídeo pedido no De IA ✨ do
    Preparar 1 Agora ⚡ (P243). Devolve o andamento novo.
    """
    recomecar_producao(dia, estado="escolhido", tentativas_de_gerar=tentativas_de_gerar,
                       **({"do_botao": True} if do_botao else {}))
    os.makedirs(PASTA, exist_ok=True)
    foto = os.path.join(PASTA, f"producao_{dia}.jpg")
    with open(foto, "wb") as arquivo:
        arquivo.write(escolhido["foto"])
    modelo, custo = MODELO_DA_PRODUCAO
    longa = bool(escolhido.get("continuacao"))
    guardar_producao(id_video=escolhido["id"], link=escolhido["link"], nome=escolhido["nome"],
                     item=escolhido.get("item", ""), valor=escolhido.get("valor"), origem=escolhido.get("origem", ""),
                     foto=foto, estilo=escolhido["estilo"], prompt=escolhido["prompt"], cena=escolhido["cena"],
                     modelo=modelo, custo=custo, escolhido_em=agora(),
                     # O nível da escolha em que o produto entrou e os números dele (P252 1), para o aviso.
                     **({"nivel": escolhido["nivel"], "filtros": escolhido.get("filtros")}
                        if escolhido.get("nivel") else {}),
                     **({"longa": True, "continuacao": escolhido["continuacao"], "fala": escolhido.get("fala", "")}
                        if longa else {}))
    if not longa:
        guardar(estilos=(estilos_recentes() + [escolhido["estilo"]])[-ESTILOS_LEMBRADOS:])
    return producao()


def producao_no_celular(d, atual):
    """
    O vídeo do dia no Flow, na rodada do robô (a trava e a tela já conferidas por ele). O de 16 s ("longa", P247
    1): o Gerar dos 8 s no MODELO_DA_PRODUCAO, o Estender e o Baixar, em etapas que a rodada seguinte retoma pelo
    estado (no_flow_longo). O de 8 s (o andamento de antes da P247 1): o Gerar e o Baixar, ou só o Baixar do que já foi
    gerado ("gerando"). True com o vídeo no servidor ("baixado"), False quando ele não ficou pronto a tempo (a
    próxima rodada continua); Parada com o passo que parou, com o caso guardado.
    """
    local = os.path.join(PASTA, f"producao_{atual['data']}.mp4")
    try:
        # Sem as telas da espera nos casos: todo dia, elas tirariam do servidor os casos das falhas.
        if atual.get("longa"):
            return no_flow_longo(d, atual, atual["modelo"], atual["custo"], local, _marcar_a_producao,
                                 guardar_telas=False)
        return no_flow(d, atual, atual["modelo"], atual["custo"], local, _marcar_a_producao,
                       so_baixar=atual.get("estado") == "gerando", guardar_telas=False)
    except SemCreditos:
        # Nada foi gerado nem deu errado no app: sem caso guardado (o robô para o vídeo de IA até o crédito voltar).
        raise
    except Parada as e:
        casos_robo.guardar(d, "video de IA", "parou", str(e), passo="flow")
        raise


def _marcar_a_producao(**campos):
    """
    Guarda o andamento do vídeo do dia; no toque do Gerar ("gerado_em"), o produto entra nos que já tiveram um
    vídeo gerado (itens_gerados), na mesma hora: a rodada que cai logo depois não deixa o produto voltar à escolha.
    O Gerar conta também entre os do dia (gerados_no_dia, P243).
    """
    if campos.get("gerado_em"):
        atual = producao()
        campos["gerados_no_dia"] = gerados_no_dia(atual.get("data"), atual) + (0 if atual.get("gerado_em") else 1)
    guardar_producao(**campos)
    if campos.get("gerado_em"):
        lembrar_item_gerado(producao().get("item"))


def conferir_a_producao():
    """
    A conferência da IA do vídeo do dia com a foto do anúncio (conferir_o_video): "pronto" ou, com outro
    produto no vídeo, "descartado" (nunca vira rascunho). No pronto de 16 s, o servidor ouve também a fala e a compara
    com a pedida (conferir_a_fala, "fala_conferida"): a embolada ou cortada não descarta o vídeo; o aviso vai no
    rascunho, para o Rafael decidir na aprovação (P248 1 e P247 1). Devolve o estado novo.
    """
    atual = producao()
    conferencia = conferir_o_video(atual["arquivo"], atual["foto"])
    estado = "descartado" if conferencia["mesmo"] is False else "pronto"
    fala = {}
    if estado == "pronto" and atual.get("longa") and atual.get("fala"):
        fala = {"fala_conferida": conferir_a_fala(atual["arquivo"], atual["fala"])}
    guardar_producao(estado=estado, conferencia=conferencia, conferido_em=agora(), **fala)
    return estado


def video_pronto():
    """O andamento do vídeo do dia que espera o rascunho, com o arquivo no servidor; None sem ele."""
    atual = producao()
    if atual.get("estado") == "pronto" and os.path.exists(atual.get("arquivo") or ""):
        return atual
    return None


def legenda_da_producao(atual, com_a_conferencia=True):
    """
    As linhas do vídeo de IA no aviso e no texto do rascunho: o modelo, o custo, o estilo, a cena e a conferência do
    Flow (com_a_conferencia=False: sem ela, no aviso do vídeo que outra conferência descartou, P245 1). No de 16 s
    (P247 1), a duração, o custo das duas partes, a fala pedida e a fala que o servidor ouviu (P248 1).
    """
    conferencia = atual.get("conferencia") or {}
    if conferencia.get("mesmo") is True:
        conferido = "o produto é o mesmo da foto do anúncio"
    elif conferencia.get("mesmo") is False:
        conferido = f"o produto muda: {conferencia.get('diferencas') or 'sem detalhes'}"
    else:
        conferido = "não deu para conferir"
    custo = atual.get("custo", 0)
    duracao = f", {atual['duracao']} s" if atual.get("duracao") else ""
    partes = (f": {custo - CUSTO_DO_ESTENDER} dos 8 s gerados e {CUSTO_DO_ESTENDER} do Estender"
              if atual.get("longa") and custo > CUSTO_DO_ESTENDER else "")
    linhas = [f"🤖 Feito por IA no Google Flow: {atual.get('modelo', '')}{duracao} ({custo} créditos de IA{partes})",
              f"🎭 Estilo: {ESTILOS.get(atual.get('estilo'), ESTILOS[ESTILO_PADRAO])}"]
    if atual.get("fala"):
        linhas.append(f"🗣️ Fala: {atual['fala']}")
    linhas.append(f"🎥 Cena: {atual.get('cena', '')}")
    if com_a_conferencia:
        linhas.append(f"🔎 A IA conferiu: {conferido}")
    if atual.get("fala_conferida"):
        # A fala embolada ou cortada não descarta o vídeo: o Rafael decide na aprovação (P248 1).
        linhas.append(texto_da_fala(atual["fala_conferida"]))
    if conferencia.get("defeitos"):
        linhas.append(f"⚠️ O que parece IA: {conferencia['defeitos']}")
    return "\n".join(linhas)


# --- As amostras: vídeos de teste da produção, só no privado do Rafael (P236 1) ---
# Pedido do Rafael (16/11, P236 1): ver como os vídeos de IA estão ficando sem esperar o do dia. Cada amostra é um
# vídeo como o da produção (o produto pela lista da API de afiliado, P234 1, o pedido da IA num estilo que varia e o
# MODELO_DA_PRODUCAO), que vai só ao privado dele, com a foto e o link do anúncio e a conferência da IA, como o teste
# da P229 1. Não vira rascunho nem post e não muda o vídeo de IA do dia: o produto da amostra fica fora só das
# amostras seguintes (amostras_feitas) e continua podendo ser o do vídeo do dia. Roda a qualquer hora, porque ele
# pediu (como o Preparar 1 Agora ⚡). Uma amostra por vez (cada video_ia.yml amostra faz a próxima); a que ficou
# gerando ou baixada vai ao privado antes de outra ser gerada. Escolha do Rafael (16/11/2026, P236 1): DECISOES.md.


def amostra_guardada():
    """A amostra de agora (o produto, o pedido e o vídeo), do banco; {} sem nenhuma."""
    atual = (db.ler_config(CHAVE, {}) or {}).get("amostra") or {}
    return atual if atual.get("foto") and os.path.exists(atual["foto"]) else {}


def marcar_amostra(**campos):
    """Grava os campos na amostra de agora (o estado: gerando, baixado ou enviado; o custo; o arquivo)."""
    db.atualizar_config(CHAVE, lambda dados: dados.setdefault("amostra", {}).update(campos))


def amostras_feitas():
    """Os produtos que já tiveram uma amostra mandada ao Rafael (os números deles): ficam fora das próximas."""
    return [str(item) for item in (db.ler_config(CHAVE, {}) or {}).get("amostras_feitas") or []]


def legenda_da_amostra(atual, conferencia, fala_ouvida=None, corte=None, com_fala=None):
    """
    O texto que vai com a amostra no privado do Rafael (até 1000 letras); a de 16 s (P246 1) com a fala pedida e o
    que o servidor ouviu no vídeo (fala_ouvida, de conferir_a_fala; P248 1); a da fala do começo ao fim (P255 1) com
    o tempo com fala (com_fala) e o corte do parado (corte, de cortar_o_parado).
    """
    if conferencia["mesmo"] is True:
        conferido = "o produto é o mesmo da foto do anúncio"
    elif conferencia["mesmo"] is False:
        conferido = f"o produto muda: {conferencia['diferencas'] or 'sem detalhes'}"
    else:
        conferido = "não deu para conferir"
    custo = atual.get("custo", 0)
    paga = (f"💰 Paga {assistente._reais(atual.get('valor') or 0)} por venda (o que paga mais entre "
            f"{atual.get('origem') or 'a lista da Shopee'}, ainda não postado)")
    if atual.get("longa"):
        if atual.get("fala_inteira"):
            jeito = "com a fala do começo ao fim e o corte do parado (P255 1)"
            de_novo = f", com o mesmo produto da nº {atual['mesmo_de']}" if atual.get("mesmo_de") else ""
        else:
            jeito = "(P246 1: uma pessoa vendendo o produto do começo ao fim)"
            de_novo = (f", com o mesmo produto da nº {atual['mesmo_de']} e as mudanças contra as alucinações (P248 1)"
                       if atual.get("mesmo_de") else "")
        linhas = [f"🎬 Amostra nº {atual.get('numero', 1)} do vídeo de IA de 16 s {jeito}{de_novo}",
                  f"🤖 Modelo: {atual.get('modelo', '')} ({custo} créditos de IA: {custo - CUSTO_DO_ESTENDER} dos "
                  f"8 s gerados e {CUSTO_DO_ESTENDER} do Estender)",
                  f"📦 Produto: {atual.get('nome', '')}", paga,
                  f"🗣️ Fala: {atual.get('fala', '')}",
                  f"🔎 A IA conferiu: {conferido}"]
        if fala_ouvida:
            linhas.append(texto_da_fala(fala_ouvida))
        if corte is not None:
            linhas.extend(texto_do_corte(corte, com_fala))
    else:
        linhas = [f"🎬 Amostra do vídeo de IA nº {atual.get('numero', 1)} (teste da P236 1)",
                  f"🤖 Modelo: {atual.get('modelo', '')} ({custo} créditos de IA)",
                  f"📦 Produto: {atual.get('nome', '')}", paga,
                  f"🎥 Cena: {atual.get('cena', '')}",
                  f"🎭 Estilo: {ESTILOS.get(atual.get('estilo'), ESTILOS[ESTILO_PADRAO])}",
                  f"🔎 A IA conferiu: {conferido}"]
    resolucao = {"1080p": "1080p (aumentada pelo Flow no Baixar)", "720p": "720p (o tamanho original)"}.get(
        atual.get("resolucao"))
    if resolucao:
        linhas.append(f"📐 Resolução: {resolucao}" + (f", {atual['tamanho']}" if atual.get("tamanho") else "")
                      + (f", {atual['duracao']} s" if atual.get("duracao") else ""))
    if conferencia["defeitos"]:
        linhas.append(f"⚠️ O que parece IA: {conferencia['defeitos']}")
    if atual.get("fala_inteira"):
        # O vídeo de IA do dia só muda com o OK do Rafael a esta amostra (P255 1).
        linhas.append("Nada foi postado. Gostando, me diga na conversa: o vídeo de IA do dia e o De IA ✨ passam a "
                      "sair assim. Até lá, saem como hoje.")
        linhas.append(f"🎥 Cena: {atual.get('cena', '')}")
    elif atual.get("longa"):
        # Desde a P247 1, o formato de 16 s é o do vídeo de IA do dia: a amostra é só para ver.
        linhas.append("Nada foi postado: é só para você ver como os vídeos de IA de 16 s estão ficando. O vídeo de IA "
                      "do dia sai normalmente e vira rascunho.")
        linhas.append(f"🎥 Cena: {atual.get('cena', '')}")
    else:
        linhas.append("Nada foi postado: é só para você ver como os vídeos de IA estão ficando. O vídeo de IA do dia "
                      "sai normalmente e vira rascunho.")
    return "\n".join(linhas)[:1000]


def mandar_a_amostra():
    """
    Confere a amostra baixada pela IA e manda no privado do Rafael (sem o celular), e logo depois a foto do anúncio
    com o link dele. O produto entra nas amostras feitas. 0 mandada, 1 não.
    """
    atual = amostra_guardada()
    if atual.get("estado") != "baixado" or not os.path.exists(atual.get("arquivo") or ""):
        print("Amostra: o vídeo baixado não está no servidor")
        return 1
    conferencia = conferir_o_video(atual["arquivo"], atual["foto"])
    print(f"Amostra: conferência da IA: {ROTULOS_DA_CONFERENCIA[conferencia['mesmo']]}")
    # A fala do vídeo de 16 s conferida pelo servidor (P248 1): a embolada ou cortada vai na legenda.
    com_a_fala = atual.get("longa") and atual.get("fala")
    ouvidas = videos.palavras_faladas(atual["arquivo"]) if com_a_fala or atual.get("fala_inteira") else None
    fala_ouvida = conferir_a_fala(atual["arquivo"], atual["fala"], ouvidas) if com_a_fala else None
    if fala_ouvida:
        print(f"Amostra: fala conferida: {ROTULOS_DA_FALA[fala_ouvida['situacao']]}")
        marcar_amostra(fala_conferida=fala_ouvida["situacao"])
    # A amostra da fala do começo ao fim (P255 1): o tempo com fala e o vídeo sem o parado, que vai primeiro.
    corte = com_fala = None
    principal = atual["arquivo"]
    if atual.get("fala_inteira"):
        corte = cortar_o_parado(atual["arquivo"], ouvidas)
        com_fala = tempo_com_fala(ouvidas, corte["antes"]) if ouvidas is not None else None
        if com_fala is not None:
            print(f"Amostra: tempo com fala: {com_fala} s de {corte['antes']} s")
        if corte["arquivo"]:
            principal = corte["arquivo"]
            print(f"Amostra: parado cortado: de {corte['antes']} s para {corte['depois']} s "
                  f"({corte['cortes']} pedaço(s) tirado(s))")
        else:
            print(f"Amostra: corte do parado: {corte['motivo']}")
        marcar_amostra(com_fala=com_fala, corte={chave: corte[chave] for chave in ("antes", "depois", "cortes")})
    try:
        ok = avisar_rafael.mandar_video(principal, legenda_da_amostra(atual, conferencia, fala_ouvida, corte, com_fala))
    except Exception as e:
        print(f"Amostra: o envio ao privado falhou ({type(e).__name__}); a próxima amostra manda de novo")
        return 1
    if not ok:
        print("Amostra: o Telegram não aceitou o vídeo; a próxima amostra manda de novo")
        return 1
    if principal != atual["arquivo"]:
        try:
            sem_corte = avisar_rafael.mandar_video(atual["arquivo"], (
                f"🎬 A amostra nº {atual.get('numero', 1)} sem o corte do parado ({_segundos(corte['antes'])}), "
                "para comparar com a de cima"))
        except Exception:
            sem_corte = False
        print("Amostra: o vídeo sem o corte também foi ao privado" if sem_corte
              else "Amostra: o vídeo sem o corte não foi ao privado")
    marcar_amostra(estado="enviado", enviado_em=agora(), mesmo_produto=conferencia["mesmo"])

    def anotar(dados):
        dados["amostras_feitas"] = ([i for i in dados.get("amostras_feitas") or [] if str(i) != str(atual["item"])]
                                    + [str(atual["item"])])[-ITENS_LEMBRADOS:]
    db.atualizar_config(CHAVE, anotar)
    print(f"Amostra nº {atual.get('numero', 1)}: vídeo mandado no privado do Rafael")
    try:
        foto = avisar_rafael.mandar_foto(atual["foto"], (
            f"🖼️ Foto do anúncio, para comparar com a amostra nº {atual.get('numero', 1)}\n"
            f"🔗 Anúncio: {link_do_anuncio(atual.get('link', ''))}")[:1000])
    except Exception:
        foto = False
    print("Amostra: foto e link do anúncio mandados" if foto else "Amostra: a foto do anúncio não foi ao privado")
    return 0


def _pedido_do_mesmo_produto(anterior, longa, fala_inteira=False):
    """
    O pedido novo da IA para o produto da amostra anterior (o link, o nome e a foto dela), com as regras de agora: a
    amostra de 16 s de novo com o mesmo produto, para o Rafael comparar (P248 1); fala_inteira: com a fala do começo
    ao fim (P255 1). None sem a amostra anterior ou sem o pedido da IA.
    """
    if not (anterior.get("link") and anterior.get("nome") and anterior.get("item")):
        return None
    try:
        with open(anterior["foto"], "rb") as arquivo:
            foto = arquivo.read()
    except (KeyError, OSError):
        return None
    escolhido, _serve = pedido_para_o_anuncio(anterior["link"], anterior["nome"], foto, longo=longa,
                                              fala_inteira=fala_inteira)
    if not escolhido:
        return None
    return dict(escolhido, item=anterior["item"], valor=anterior.get("valor"), origem=anterior.get("origem"))


def amostra(sem_gerar=False, longa=False, mesmo=False, fala_inteira=False):
    """
    A próxima amostra do vídeo de IA (P236 1): escolhe o produto como a produção, gera no MODELO_DA_PRODUCAO, baixa
    e manda no privado do Rafael. A que já foi gerada só é baixada e mandada (nunca dois Gerar para a mesma amostra).
    sem_gerar: tudo até o Gerar, sem tocar nele. longa: a amostra do vídeo de 16 s com uma pessoa vendendo o produto
    (P246 1), com o Estender; a que ficou pela metade continua do jeito dela. mesmo: com o produto da amostra
    anterior e um pedido novo da IA (P248 1). fala_inteira (só com longa): a de 16 s com a fala do começo ao fim de
    cada parte e o corte do parado (P255 1). 0 deu certo, 1 parou. Só rótulos fixos e números no log.
    """
    fala_inteira = fala_inteira and longa
    atual = amostra_guardada()
    if atual.get("estado") == "baixado" and os.path.exists(atual.get("arquivo") or ""):
        print(f"Amostra nº {atual.get('numero', 1)}: já baixada; falta mandar")
        return mandar_a_amostra()
    so_baixar = atual.get("estado") == "gerando"
    if atual.get("estado") == "estendendo":
        print(f"Amostra nº {atual.get('numero', 1)}: já estendida; falta baixar e mandar")
    elif so_baixar:
        print(f"Amostra nº {atual.get('numero', 1)}: já gerada; falta "
              + ("estender, baixar e mandar" if atual.get("longa") else "baixar e mandar"))
    else:
        numero_anterior = int(atual.get("numero") or 0)
        if mesmo:
            escolhido, origem = _pedido_do_mesmo_produto(atual, longa, fala_inteira), ""
            if not escolhido:
                print("Amostra: sem a amostra anterior ou sem o pedido novo da IA para o mesmo produto; "
                      "nada foi tocado")
                return 1
        else:
            # Só aqui: o robô importa este módulo, e a escolha é a dele (P234 1).
            import robo_shopee_video as robo
            try:
                escolhido, origem, _restam = robo.escolher_para_o_video_de_ia(fora=amostras_feitas(), amostra=True,
                                                                              longo=longa, fala_inteira=fala_inteira)
            except api_shopee.BuscaNegada as e:
                print(f"Amostra: a API da Shopee negou a lista de produtos ({e}); nada foi tocado")
                return 1
            if not escolhido:
                print("Amostra: nenhum produto da lista serviu agora (a foto ou o link curto); nada foi tocado")
                return 1
        os.makedirs(PASTA, exist_ok=True)
        foto = os.path.join(PASTA, "amostra.jpg")
        with open(foto, "wb") as arquivo:
            arquivo.write(escolhido["foto"])
        modelo, custo = MODELO_DA_PRODUCAO
        atual = {chave: escolhido.get(chave) for chave in ("link", "nome", "item", "valor", "origem", "estilo",
                                                            "prompt", "cena")}
        # A amostra com o mesmo produto não entra de novo nas feitas: o número segue a conta da anterior.
        atual.update(foto=foto, modelo=modelo, custo=custo, estado="escolhido", criado_em=agora(),
                     numero=max(len(amostras_feitas()), numero_anterior) + 1)
        if mesmo:
            atual.update(mesmo_de=numero_anterior)
        if longa:
            # O vídeo de 16 s tem um jeito só e fica fora da variação dos estilos dos vídeos de 8 s.
            atual.update(longa=True, continuacao=escolhido.get("continuacao", ""), fala=escolhido.get("fala", ""))
            if fala_inteira:
                atual.update(fala_inteira=True)
            guardar(amostra=atual)
        else:
            guardar(amostra=atual, estilos=(estilos_recentes() + [escolhido["estilo"]])[-ESTILOS_LEMBRADOS:])
        escolha = (f"o mesmo produto da amostra nº {numero_anterior}" if mesmo
                   else f"produto escolhido (o {escolhido.get('posicao')}º de {origem})")
        print(f"Amostra nº {atual['numero']}: {escolha}; "
              f"estilo {escolhido['estilo']}; pedido da IA com {len(escolhido['prompt'].split())} palavras"
              + (f" e a continuação com {len(atual['continuacao'].split())}" if longa else "")
              + ("; com a fala do começo ao fim (P255 1)" if fala_inteira else ""))
    if not celular_robo.conectado():
        print("celular: desconectado; conecte pelo bot (Shopee Vídeo 🎬 → Celular do Robô 📱)")
        return 1
    tentativas = ps.ESPERA_DO_CELULAR // ps.PAUSA_DA_ESPERA + 1
    for tentativa in range(tentativas):
        with celular_robo.trava() as livre:
            if livre:
                codigo = _amostra_no_celular(atual, sem_gerar, so_baixar)
                break
        if tentativa == 0:
            print(f"celular: o robô automático está tocando no celular; esperando ele soltar "
                  f"(até {ps.ESPERA_DO_CELULAR // 60} min)")
        if tentativa < tentativas - 1:
            time.sleep(ps.PAUSA_DA_ESPERA)
    else:
        print("celular: o robô automático continua tocando no celular; nada foi tocado")
        return 1
    # A conferência da IA e o envio ao privado vêm com o celular já solto para o robô automático.
    if codigo == 0 and not sem_gerar:
        return mandar_a_amostra()
    return codigo


def _amostra_no_celular(atual, sem_gerar, so_baixar):
    """A amostra no celular, com a trava na mão: a tela, a foto, o Flow, o Gerar e o Baixar. 0 deu certo, 1 parou."""
    if celular_robo.tela_acesa() is False:
        ps.conectar(celular=True).screen_on()
        time.sleep(2)
    if celular_robo.tela_acesa() is False or celular_robo.tela_de_bloqueio():
        print("celular: a tela está apagada ou na tela de bloqueio; nada foi tocado")
        return 1
    d = ps.conectar(celular=True)
    try:
        if atual.get("longa"):
            feito = no_flow_longo(d, atual, atual["modelo"], atual["custo"], os.path.join(PASTA, "amostra.mp4"),
                                  marcar_amostra, sem_gerar=sem_gerar)
        else:
            feito = no_flow(d, atual, atual["modelo"], atual["custo"], os.path.join(PASTA, "amostra.mp4"),
                            marcar_amostra, sem_gerar=sem_gerar, so_baixar=so_baixar, guardar_telas=False)
    except SemCreditos as e:
        print(f"Amostra: {e}; nada foi gerado")
        return 1
    except Parada as e:
        casos_robo.guardar(d, "flow", "parou", str(e), passo="flow")
        print(f"Amostra: parou: {e}")
        return 1
    return 0 if feito else 1


def teste(sem_gerar=False):
    """O próximo vídeo do teste (um modelo por vez); com sem_gerar, tudo até o Gerar, sem tocar nele."""
    teste_de_agora = teste_guardado()
    if not teste_de_agora:
        escolhido = escolher_o_produto()
        if not escolhido:
            print(f"Nenhum dos próximos {PRODUTOS_TENTADOS} vídeos da fonte tem uma foto boa para o vídeo: "
                  "o teste não roda.")
            return 1
        os.makedirs(PASTA, exist_ok=True)
        caminho = os.path.join(PASTA, "foto_do_teste.jpg")
        with open(caminho, "wb") as arquivo:
            arquivo.write(escolhido["foto"])
        teste_de_agora = {"link": escolhido["link"], "nome": escolhido["nome"], "foto": caminho,
                          "estilo": escolhido["estilo"], "prompt": escolhido["prompt"], "cena": escolhido["cena"],
                          "criado_em": agora(), "videos": {}}
        # O estilo entra na lista dos últimos, para o próximo vídeo variar (pedido do Rafael, 15/11).
        guardar(teste=teste_de_agora, estilos=(estilos_recentes() + [escolhido["estilo"]])[-ESTILOS_LEMBRADOS:])
        print(f"Produto do teste: escolhido (o {escolhido['tentados']}º dos próximos vídeos da fonte); "
              f"estilo {escolhido['estilo']}; pedido da IA com {len(escolhido['prompt'].split())} palavras")
    # O vídeo já gerado vai ao Rafael antes de outro ser gerado: o baixado só falta mandar (sem o
    # celular); o que ficou gerando é baixado agora.
    pendente = None if sem_gerar else video_pendente(teste_de_agora)
    if pendente:
        modelo = pendente
        custo = ((teste_de_agora.get("videos") or {}).get(modelo) or {}).get("custo", 0)
        if os.path.exists(((teste_de_agora.get("videos") or {}).get(modelo) or {}).get("arquivo") or ""):
            print(f"Vídeo do teste: {modelo} já baixado; falta mandar")
            return mandar_o_baixado(modelo, custo)
        print(f"Vídeo do teste: {modelo} já gerado; falta baixar e mandar")
    else:
        proximo = proximo_modelo(teste_de_agora)
        if not proximo:
            print("Os 3 vídeos do teste já foram gerados.")
            return 0
        modelo, custo = proximo
        print(f"Vídeo do teste: {modelo} ({custo} créditos)")
    if not celular_robo.conectado():
        print("celular: desconectado; conecte pelo bot (Shopee Vídeo 🎬 → Celular do Robô 📱)")
        return 1
    if not ps.no_horario_das_rodadas():
        inicio, fim = ps.horario_das_rodadas()
        print(f"celular: fora do horário das rodadas ({inicio}h às {fim}h de Brasília); nada foi tocado")
        return 1
    tentativas = ps.ESPERA_DO_CELULAR // ps.PAUSA_DA_ESPERA + 1
    for tentativa in range(tentativas):
        with celular_robo.trava() as livre:
            if livre:
                codigo = no_celular(teste_de_agora, modelo, custo, sem_gerar, so_baixar=bool(pendente))
                break
        if tentativa == 0:
            print(f"celular: o robô automático está tocando no celular; esperando ele soltar "
                  f"(até {ps.ESPERA_DO_CELULAR // 60} min)")
        if tentativa < tentativas - 1:
            time.sleep(ps.PAUSA_DA_ESPERA)
    else:
        print("celular: o robô automático continua tocando no celular; nada foi tocado")
        return 1
    # A conferência da IA e o envio ao privado vêm com o celular já solto para o robô automático.
    if codigo == 0 and not sem_gerar:
        return mandar_o_baixado(modelo, custo)
    return codigo


def main(argumentos):
    opcoes = set(argumentos[1:])
    if argumentos and ((argumentos[0] == "teste" and opcoes <= {"--sem-gerar"})
                       or (argumentos[0] == "amostra"
                           and opcoes <= {"--sem-gerar", "--longa", "--mesmo", "--fala-inteira"})):
        # Os módulos logam nomes e links; aqui o log é público, e o resultado sai pelos prints.
        logging.disable(logging.CRITICAL)
        try:
            if argumentos[0] == "teste":
                return teste(sem_gerar="--sem-gerar" in opcoes)
            return amostra(sem_gerar="--sem-gerar" in opcoes, longa="--longa" in opcoes, mesmo="--mesmo" in opcoes,
                           fala_inteira="--fala-inteira" in opcoes)
        except Exception as e:
            # Só o tipo: a mensagem de um erro inesperado pode trazer o nome do arquivo do vídeo.
            print(f"Flow: erro inesperado ({type(e).__name__})")
            return 1
        finally:
            logging.disable(logging.NOTSET)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

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
A amostra do formato mãos e voz (P261 1, 20/11/2026; --maos-e-voz), como o vídeo que o Rafael mandou: só as mãos de
quem usa o produto, sem rosto, a câmera sempre nele, e uma voz contando do começo ao fim (o gancho, o produto, o uso
mais simples com o resultado à vista e a chamada "clica no carrinho laranja"), sem a cena da loja lotada do vídeo
dele (PEDIDO_DAS_MAOS_E_VOZ); vai ao privado com o tempo com fala. A amostra da propaganda de TV (P268 1, 21/11/2026;
--tv), a ideia dele: 8 s com cara de comercial de TV, e não de vídeo de IA ou de loja, o produto em 2 ou 3 planos de
cinema (a revelação com luz de estúdio, o uso num lugar bonito e o produto sozinho no centro no fim) e um locutor em
off do 1º segundo até perto do fim, sem ninguém falando para a câmera (PEDIDO_DA_PROPAGANDA); vai ao privado com a
fala do locutor conferida e o tempo com fala.

Desde a P262 (20/11/2026), cada vídeo de IA do dia e do De IA ✨ tem a duração e o silêncio decididos vídeo a vídeo:
a IA que escolhe o formato (agora também o mãos e voz) escolhe 8 s, um Gerar só com a fala do começo ao fim, ou 16 s
(formato_do_video); o de 16 s do vendedor fala do começo ao fim de cada parte; e, com o vídeo pronto, o servidor corta
o silêncio de mais de 1 s ou mantém o vídeo inteiro (decidir_o_silencio). Desde a P269 3 (21/11/2026), todo vídeo de
IA do dia e do De IA ✨ é a propaganda de TV da amostra, de 8 s, pela foto do anúncio e inteira, sem o corte do
silêncio (SO_A_PROPAGANDA_NA_PRODUCAO); os outros formatos ficam só nas amostras, e o checkup compara as visualizações
da propaganda com as dos vídeos de IA dos formatos de antes.

Usado pelo workflow video_ia.yml (acao flow, flow-sem-gerar, amostra, amostra-16s, amostra-16s-mesmo,
amostra-16s-fala-inteira, amostra-16s-maos-e-voz ou amostra-tv). O
log do Actions é público: saem só estados, modelos e números; o produto e o pedido ficam no banco, e o
vídeo, no privado.

    python3 flow_shopee_video.py teste              # o próximo passo do teste (um modelo por vez)
    python3 flow_shopee_video.py teste --sem-gerar  # tudo até o Gerar, sem tocar nele
    python3 flow_shopee_video.py amostra            # a próxima amostra do vídeo de IA (P236 1)
    python3 flow_shopee_video.py amostra --longa    # a amostra do vídeo de 16 s, com o Estender (P246 1)
    python3 flow_shopee_video.py amostra --longa --mesmo  # a de 16 s com o produto da anterior (P248 1)
    python3 flow_shopee_video.py amostra --longa --fala-inteira  # a de 16 s falando o tempo todo, sem o parado (P255 1)
    python3 flow_shopee_video.py amostra --longa --maos-e-voz  # a de 16 s só com as mãos e a voz contando (P261 1)
    python3 flow_shopee_video.py amostra --tv       # a de 8 s com cara de propaganda de TV, com o locutor (P268 1)
    python3 flow_shopee_video.py personagens          # as fotos dos personagens que faltam (P250 1 e P258 1)
    python3 flow_shopee_video.py personagens vovo     # a foto da Vovó de novo (outra)
    python3 flow_shopee_video.py aprovar-personagens  # o OK do Rafael às fotos mandadas (P259 1); com chaves, só essas
    python3 flow_shopee_video.py imagem-teste         # a imagem de teste de um personagem com o produto (P253 1)

As fotos dos 10 personagens fixos (P250 1 e P258 1, 19/11/2026): no modo Imagem do Flow, que não gasta crédito (o
Nano Banana 2.1, conferido na tela com "0 créditos de IA" antes do Gerar), uma por personagem, baixada no tamanho
original e mandada ao privado do Rafael para ele aprovar ou pedir outra (fotos_dos_personagens). O OK dele, dado na
conversa com o Claude, fica anotado em cada foto (aprovar_as_fotos), e só as aprovadas valem (fotos_aprovadas).

Desde a P260 1 (19/11/2026), o vídeo de IA do dia e o De IA ✨ começam pela imagem de um personagem com o produto, como
a imagem de teste da P253 1 (imagem_da_producao): a IA escolhe o personagem pelo produto, o modo Imagem faz a imagem
sem crédito, a IA a confere (refeita uma vez) e escreve o pedido do vídeo por ela; sem ela, o vídeo sai pela foto do
anúncio, como antes. O formato pode ser também a comédia (P251 1), no máximo 1 a cada 3 vídeos de IA.
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


def custo_do_video_de_ia():
    """
    Os créditos que o vídeo de IA da produção pede agora: os da propaganda de TV de 8 s, um Gerar só (P269 3), ou, com
    a escolha do formato (sem SO_A_PROPAGANDA_NA_PRODUCAO), os do de 16 s, o maior (P262). O robô confere o saldo do
    Flow por ele antes de escolher o produto, e o painel mostra o custo por ele.
    """
    return MODELO_DA_PRODUCAO[1] if SO_A_PROPAGANDA_NA_PRODUCAO else CUSTO_DA_PRODUCAO
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
# A comédia de 16 s (P251 1), com os personagens (P250 1 e P258 1), desde a P260 1 (19/11/2026): na 1ª parte (os 8 s
# gerados), um personagem da comédia numa situação engraçada com o produto à vista; na 2ª (o Estender), o mesmo
# personagem mostrando o produto e vendendo. A IA escolhe pelo produto (vendedor na maioria; a comédia quando o
# produto pede uma situação engraçada), e no máximo 1 a cada VIDEOS_POR_COMEDIA vídeos de IA é comédia: nenhuma
# quando um dos últimos gerados foi (formatos_recentes). Escolha do Rafael (P251 1): DECISOES.md, Shopee Vídeo.
ESTILO_DA_COMEDIA = "comedia_16s"
VIDEOS_POR_COMEDIA = 3
# O formato mãos e voz (P261 1, 20/11/2026), como o vídeo que o Rafael mandou ("foco mais no produto em si"): só as
# mãos de quem usa o produto, sem rosto, a câmera sempre nele, e uma voz contando do começo ao fim. Primeiro numa
# amostra (amostra --longa --maos-e-voz); com o "Está muito bom o vídeo" dele à amostra nº 7 e a P262 (20/11), entra
# entre os formatos que a IA escolhe pelo produto no vídeo de IA do dia e no De IA ✨. Escolhas do Rafael (P261 1 e
# P262): DECISOES.md, Shopee Vídeo.
ESTILO_DAS_MAOS_E_VOZ = "maos_e_voz"
# A propaganda de TV (P268 1, 21/11/2026), a ideia do Rafael: o vídeo de IA "como se fossem os anúncios do YouTube
# (...) desses streams de filmes", "não com cara de IA, de Shopee (...) mas sim cara de propaganda de TV. Curta, de 8
# segundos". O produto em 2 ou 3 planos de comercial, com luz de estúdio e a câmera se movendo devagar (a revelação
# dele, o uso num lugar bonito e, no fim, ele sozinho no centro), e um locutor em off; ninguém fala para a câmera.
# Primeiro numa amostra de 8 s, só no privado dele (amostra --tv); depois dela, o formato de todo vídeo de IA do dia e
# do De IA ✨ (P269 3), e o checkup compara as visualizações dela com as dos formatos de antes. Escolhas do Rafael
# (P268 1 e P269 3): DECISOES.md, Shopee Vídeo.
ESTILO_DA_PROPAGANDA = "propaganda_tv"
# Todo vídeo de IA da produção é a propaganda de TV de 8 s (P269 3): o vendedor, o mãos e voz, o unboxing e a comédia
# saem dela e ficam só nas amostras. Com False, volta a escolha do formato pela IA (P262), com a propaganda entre os
# formatos (a P269 1, que ele respondeu primeiro e trocou pela 3 sete minutos depois). Escolha do Rafael (P269 3):
# DECISOES.md, Shopee Vídeo.
SO_A_PROPAGANDA_NA_PRODUCAO = True
ESTILOS = {"demonstracao": "demonstração (o produto em uso)", "fala": "pessoa falando do produto",
           "inusitado": "inusitado (viral)", "comedia": "comédia",
           ESTILO_DO_VENDEDOR: "pessoa vendendo o produto, do gancho à chamada",
           ESTILO_DO_UNBOXING: "unboxing: as mãos abrindo a caixa com o produto, sem rosto e sem fala (16 s)",
           ESTILO_DA_COMEDIA: "comédia: um personagem numa situação engraçada com o produto, e depois vendendo (16 s)",
           ESTILO_DAS_MAOS_E_VOZ: "mãos e voz: só as mãos usando o produto, com uma voz contando",
           ESTILO_DA_PROPAGANDA: "propaganda de TV: o produto em planos de comercial, com um locutor em off (8 s)"}
# A duração do vídeo de IA, decidida vídeo a vídeo (P262, 20/11/2026: o Rafael viu que o silêncio no meio dos vídeos
# de 16 s "tira o gancho do vídeo" e pediu: "eu gostaria q vc decidisse oq seria melhor, para cada vídeo o meu robô
# decidisse se iria manter, cortar ou fazer 8 seg"). Antes do Gerar, a IA que escolhe o formato escolhe também 8 s
# (um Gerar só, sem o Estender: o gancho, a vantagem e a chamada falados do começo ao fim) ou 16 s (o uso com o
# resultado, mais de uma vantagem, o unboxing e a comédia, sempre de 16 s); na dúvida, 8 s, que prendem mais. Com o
# vídeo pronto, o servidor ouve a fala e corta o silêncio de mais de PARADO_MAXIMO s (cortar_o_parado) ou mantém o
# vídeo inteiro (decidir_o_silencio). Escolha do Rafael (P262): DECISOES.md, Shopee Vídeo.
DURACAO_CURTA = 8
DURACAO_LONGA = 16
# O corte que deixaria o vídeo com menos que isto não sai: quase sem fala, o vídeo fica inteiro, e o Rafael decide na
# aprovação.
DURACAO_MINIMA_DO_CORTE = 6.0
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
# A fala sem embolar (P264 4, 21/11/2026): o servidor ouviu embolada e cortada no fim a fala do 1º vídeo de 8 s, e o
# Rafael quis a fala do mesmo tamanho ("tente evitar o máximo possível embolar, mas não qro reduzir fala nao"). A IA
# escreve a fala com palavras curtas, comuns e fáceis de falar em voz alta, e pede no prompt a dicção clara, palavra
# por palavra; o tanto de palavras e o tempo da fala continuam os mesmos. Escolha do Rafael (P264 4): DECISOES.md,
# Shopee Vídeo.
_FALA_SEM_EMBOLAR = (
    "A fala é natural, em frases diretas, com palavras curtas, comuns e fáceis de falar em voz alta (sem número, "
    "sigla, palavra estrangeira, nome difícil, palavra comprida ou trava-língua, que a IA de vídeo embola), e o "
    "prompt (e a continuação, quando tem) pede em inglês a dicção clara: clear Brazilian Portuguese diction, every "
    "word pronounced clearly."
)
# O pedido acima diz à IA para pôr a dicção clara no prompt; quando ela esquece, o servidor põe no fim do prompt e da
# continuação do vídeo com fala (com_a_diccao). O unboxing, sem fala, fica sem.
DICCAO_CLARA = "Clear Brazilian Portuguese diction, every word pronounced clearly."
# O tanto de letras que o prompt e a continuação guardam.
LETRAS_DO_PROMPT = 1000
# A cena e as regras da fala, iguais no pedido de 16 s e no de 8 s (P262).
_REGRAS_DA_FALA = (
    "- cena: uma frase em português que descreve a cena, para o Rafael.\n"
    + _FALA_SEM_EMBOLAR +
    " A fala vai sem marca, sem preço e sem prometer o que o produto não faz. Nada de zombar do "
    "corpo, da aparência ou de um grupo de ninguém (as diretrizes punem humilhação e ódio), e nada perigoso, "
    "nojento ou com criança. Sem texto na tela, sem legenda, sem logotipo novo e sem outros produtos."
)
# O fim do pedido de 16 s, igual nos dois jeitos da fala.
_FIM_DO_VENDEDOR = ("- fala: tudo o que a pessoa fala, em português, as duas partes juntas, como vai sair no vídeo.\n"
                    + _REGRAS_DA_FALA)
# O fim do pedido de 8 s (P262), com a fala de uma parte só.
_FIM_DO_CURTO = "- fala: tudo o que a pessoa fala, em português, como vai sair no vídeo.\n" + _REGRAS_DA_FALA
# A 2ª parte do vendedor (o Estender), igual no pedido pela foto do anúncio e no pela imagem do personagem (P260 1).
_CONTINUACAO_DO_VENDEDOR = (
    "- continuacao: em inglês, até 90 palavras, os 8 segundos seguintes, continuando o mesmo plano sem corte, no "
    "mesmo lugar e enquadramento, com a mesma pessoa, a mesma roupa e o mesmo produto, idêntico: ela aponta e "
    "mostra de perto uma vantagem que se vê no produto, só virando-o ou aproximando-o da câmera, e fala logo no "
    f"começo, entre aspas, em português do Brasil, até {PALAVRAS_POR_PARTE} palavras, a vantagem e uma chamada curta "
    "para comprar (por exemplo: \"Nada gruda e limpa fácil. Garanta a sua!\"), terminando antes dos 6 segundos.\n"
)
PEDIDO_DO_VENDEDOR = _COMECO_DO_VENDEDOR + (
    "- prompt: em inglês, até 90 palavras, os 8 primeiros segundos: a pessoa olha para a câmera, segura o produto "
    "da foto, idêntico (mesma forma, cor, material, tamanho, quantidade e detalhes; nada acrescentado, tirado ou "
    "trocado) e bem à vista, e diz logo no começo o gancho, entre aspas, em português do Brasil, até "
    f"{PALAVRAS_POR_PARTE} palavras: uma dor que o produto resolve, uma pergunta ou uma surpresa (por exemplo: "
    "\"Orelha rasgada? Nunca mais!\"), terminando antes dos 6 segundos; depois, calada, vira o produto devagar para "
    "a câmera. Numa cena real do Brasil, com luz natural, fotorrealista, a câmera parada na altura do peito.\n"
) + _CONTINUACAO_DO_VENDEDOR + _FIM_DO_VENDEDOR
# O pedido de 16 s com a fala do começo ao fim de cada parte (P255 1): o resto igual ao PEDIDO_DO_VENDEDOR (só segurar,
# virar e apontar o produto, no mesmo lugar e enquadramento, com a câmera parada), sem o "depois, calada". Por enquanto
# só na amostra (amostra --longa --fala-inteira).
# A fala da 1ª parte do vendedor de 16 s falando do começo ao fim, igual no pedido pela foto do anúncio e no pela
# imagem do personagem (P262).
_FALA_DA_1A_PARTE = (
    "fala do 1º segundo até por volta dos 7 segundos, sem ficar calada no meio, entre aspas, em português do Brasil, "
    f"2 frases curtas com até {PALAVRAS_DA_FALA_INTEIRA} palavras ao todo: o gancho (uma dor que o produto resolve, "
    "uma pergunta ou uma surpresa) e uma vantagem que se vê no produto (por exemplo: \"Orelha rasgada? Nunca mais! "
    "Esse aqui fica firme o dia inteiro.\"); enquanto fala, aproxima o produto da câmera, vira devagar e aponta o "
    "detalhe. Escreva no pedido que ela fala sem parar até perto do fim, sem pausa longa."
)
# A 2ª parte (o Estender) do vendedor de 16 s falando do começo ao fim, igual nos dois pedidos (P262).
_CONTINUACAO_FALANDO = (
    "- continuacao: em inglês, até 90 palavras, os 8 segundos seguintes, continuando o mesmo plano sem corte, no "
    "mesmo lugar e enquadramento, com a mesma pessoa, a mesma roupa e o mesmo produto, idêntico: ela continua "
    "falando do 1º segundo até por volta dos 7 segundos, sem ficar calada no meio, entre aspas, em português do "
    f"Brasil, 2 frases curtas com até {PALAVRAS_DA_FALA_INTEIRA} palavras ao todo: outra vantagem que se vê no "
    "produto e uma chamada curta para comprar (por exemplo: \"Nada gruda e limpa num instante. Garanta já o seu "
    "hoje!\"); enquanto fala, aponta e mostra de perto a vantagem, só virando o produto ou aproximando-o da câmera. "
    "Escreva no pedido que ela fala sem parar até perto do fim, sem pausa longa.\n"
)
PEDIDO_DO_VENDEDOR_FALANDO = _COMECO_DO_VENDEDOR + (
    "- prompt: em inglês, até 90 palavras, os 8 primeiros segundos: a pessoa olha para a câmera, segura o produto "
    "da foto, idêntico (mesma forma, cor, material, tamanho, quantidade e detalhes; nada acrescentado, tirado ou "
    f"trocado) e bem à vista, e {_FALA_DA_1A_PARTE} Numa cena real do Brasil, com luz natural, fotorrealista, a câmera "
    "parada na altura do peito.\n"
) + _CONTINUACAO_FALANDO + _FIM_DO_VENDEDOR
# O pedido do vídeo de 8 s (P262): um Gerar só, sem o Estender, com a pessoa vendendo o produto e falando do 1º ao
# último segundo (o gancho, a vantagem que se vê e a chamada), com os cuidados contra as alucinações da P248 1.
_COMECO_DO_VENDEDOR_CURTO = (
    "Você é diretor de vídeos curtos de produto para a Shopee Vídeo, no Brasil, e escreve como os vídeos que mais "
    "vendem no feed. A imagem é a foto oficial do anúncio do produto \"{nome}\". O Google Flow vai gerar um vídeo "
    "de 8 segundos, em pé (9:16) e com som, a partir dessa foto. Uma pessoa comum, brasileira, vende o produto "
    "falando com quem assiste do 1º ao último segundo, sem pausa: o gancho, a vantagem que se vê e a chamada para "
    "comprar. A IA de vídeo inventa coisas quando a cena pede demais; por isso, a pessoa só segura o produto, vira "
    "devagar e aponta para ele, sem abrir, fechar, desmontar, encaixar, despejar, cozinhar, vestir ou trocar o "
    "produto de mão, e ele aparece desde o 1º quadro do jeito que é usado (vestido, montado, no lugar), sem nada "
    "mudar de estado; os 8 segundos ficam no mesmo lugar, com o mesmo fundo e o mesmo enquadramento e a câmera "
    "parada, sem corte e sem aparecer comida, objeto ou pessoa nova (se o produto pede um lugar para ser mostrado, "
    "como o fogão, a pia ou a cama, o vídeo já começa lá). Responda só com um JSON, sem nada antes ou depois:\n"
    '{{"serve": true ou false, "muda_na_ia": true ou false, "motivo": "...", "prompt": "...", "fala": "...", '
    '"cena": "..."}}\n'
    + REGRAS_DA_FOTO
)
# A fala do vídeo de 8 s do vendedor, igual no pedido pela foto do anúncio e no pela imagem do personagem (P260 1).
_FALA_DO_CURTO = (
    "fala do 1º segundo até perto do fim, sem ficar calada, entre aspas, em português do Brasil, 2 ou 3 frases "
    f"curtas com até {PALAVRAS_DA_FALA_INTEIRA} palavras ao todo: o gancho (uma dor que o produto resolve, uma "
    "pergunta ou uma surpresa), a vantagem que se vê no produto e uma chamada curta para comprar (por exemplo: "
    "\"Orelha rasgada? Esse fica firme o dia todo. Garanta já o seu!\"); enquanto fala, aproxima o produto da "
    "câmera, vira devagar e aponta o detalhe. Escreva no pedido que ela fala sem parar do começo ao fim, sem pausa."
)
PEDIDO_DO_VENDEDOR_CURTO = _COMECO_DO_VENDEDOR_CURTO + (
    "- prompt: em inglês, até 90 palavras, os 8 segundos: a pessoa olha para a câmera, segura o produto da foto, "
    "idêntico (mesma forma, cor, material, tamanho, quantidade e detalhes; nada acrescentado, tirado ou trocado) e "
    f"bem à vista, e {_FALA_DO_CURTO} Numa cena real do Brasil, com luz natural, fotorrealista, a câmera parada na "
    "altura do peito.\n"
) + _FIM_DO_CURTO
# A escolha do formato do vídeo de 16 s pelo produto, só entre os que podem sair agora (pedido_do_formato): o
# vendedor, o unboxing (P256 2) e a comédia (P251 1); no vídeo de IA do dia e no De IA ✨, também o mãos e voz e a
# duração, 8 ou 16 s (P262), e a propaganda de TV, sempre de 8 s (P269 1). Com SO_A_PROPAGANDA_NA_PRODUCAO (P269 3), a
# produção não passa por esta escolha: o vídeo é sempre a propaganda.
_FORMATO_DO_VENDEDOR = (
    "\"vendedor\" (uma pessoa comum segura o produto e fala dele com quem assiste, mostrando as vantagens de perto: "
    "bom para o produto que precisa de explicação, como utilidades, aparelhos e o que resolve um problema)")
_FORMATO_DO_UNBOXING = (
    "\"unboxing\" (só as mãos de quem recebeu a encomenda, sem rosto e sem fala, abrindo a caixa e mostrando o "
    "produto de perto, com a câmera na mão: bom para o produto que se vende pela aparência e cabe numa caixa de "
    "encomenda, como calçados, bolsas, roupas, acessórios, maquiagem e decoração)")
_FORMATO_DA_COMEDIA = (
    "\"comedia\" (um personagem engraçado reage ao produto do jeito dele, numa situação engraçada do dia a dia, e "
    "depois mostra o produto e vende: só quando o produto pede mesmo uma situação engraçada; na dúvida, o vendedor, "
    "que é o da maioria dos vídeos. A graça é da situação e da reação, nunca de zombar do corpo, da aparência ou de "
    "um grupo de ninguém)")
_FORMATO_DAS_MAOS_E_VOZ = (
    "\"maos_e_voz\" (só as mãos de quem usa o produto, sem rosto, a câmera sempre nele, e uma voz contando do começo "
    "ao fim: bom para o produto que se mostra fazendo, com um gesto simples e o resultado logo à vista, como "
    "luminárias, umidificadores, organizadores, utensílios e aparelhos pequenos)")
_FORMATO_DA_PROPAGANDA = (
    f"\"{ESTILO_DA_PROPAGANDA}\" (um comercial de TV de 8 segundos, com cara de propaganda profissional: o produto "
    "em planos de cinema, com luz de estúdio, e um locutor em off, sem ninguém falando para a câmera: bom para o "
    "produto bonito de se ver, que ganha valor num comercial caprichado, como decoração, beleza, acessórios e "
    "utensílios de design)")
PEDIDO_DO_FORMATO = (
    "Você é diretor de vídeos curtos de produto para a Shopee Vídeo, no Brasil. A imagem é a foto do anúncio do "
    "produto \"{nome}\". Escolha o formato do vídeo {de_16_s}feito por IA que mais combina com este produto e mais "
    "faz quem está rolando o feed parar e comprar: {opcoes}.{duracao} Responda só com um JSON, sem nada antes ou "
    "depois:\n"
    '{{"formato": {nomes}, {campo}"motivo": "o porquê, em poucas palavras"}}'
)
# A escolha da duração junto com a do formato (P262): no vídeo de IA do dia e no De IA ✨.
TRECHO_DA_DURACAO = (
    " Escolha também a duração: 8 segundos quando o produto se entende num olhar e o gancho, a vantagem e a chamada "
    f"para comprar cabem em até {PALAVRAS_DA_FALA_INTEIRA} palavras faladas sem pausa (acessórios, beleza, roupa, "
    "decoração, utilidades simples), ou 16 segundos quando ele precisa ser mostrado em uso, com o resultado à vista, "
    "ou tem mais de uma vantagem que se vê (aparelhos, limpeza, cozinha, ferramentas). O vídeo curto prende mais e "
    "não fica com silêncio no meio: na dúvida, 8 segundos. O unboxing e a comédia têm sempre 16 segundos."
)
TRECHO_DA_PROPAGANDA = " A propaganda de TV tem sempre 8 segundos."
CAMPO_DA_DURACAO = '"duracao": 8 ou 16, '
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
# O pedido do formato mãos e voz de 16 s (P261 1), como o vídeo que o Rafael mandou: só as mãos, a câmera sempre no
# produto e uma voz contando do começo ao fim, em duas frases curtas por parte (como a amostra da P255 1). Sem a cena
# da loja lotada do vídeo dele: inventada (todo mundo comprando, com placa de preço), e as diretrizes punem
# desinformação e preço no vídeo. O produto em uso é o que a IA de vídeo mais erra (P248 1): um uso só, o mais
# simples, sem montar nem trocar peça, com o resultado logo à vista, no mesmo lugar.
PEDIDO_DAS_MAOS_E_VOZ = (
    "Você é diretor de vídeos curtos de produto para a Shopee Vídeo, no Brasil, e escreve como os vídeos que mais "
    "vendem no feed. A imagem é a foto oficial do anúncio do produto \"{nome}\". O Google Flow vai gerar um vídeo "
    "de 16 segundos, em pé (9:16) e com som, em duas partes de 8 segundos: a 1ª a partir dessa foto e a 2ª "
    "continuando a 1ª, no mesmo lugar e com a mesma voz. É uma demonstração filmada pelos olhos de quem usa o "
    "produto (primeira pessoa): só as mãos aparecem, sem rosto, com a câmera na mão e sempre no produto, numa casa "
    "simples e arrumada do Brasil, com a luz do dia; por cima, a voz de uma pessoa comum, brasileira e animada, conta "
    "do começo ao fim, como quem mostra uma descoberta para uma amiga (a narração de quem filma, sem ninguém falando "
    "na tela). A IA de vídeo inventa coisas quando a cena pede demais; por isso, o produto aparece inteiro, idêntico "
    "ao da foto, sem mudar de forma, cor ou tamanho; as mãos fazem um uso só, o mais simples do produto, com um gesto "
    "curto (apertar, ligar, encher, passar, colocar no lugar), sem montar, desmontar, cortar, cozinhar ou vestir, e o "
    "resultado aparece logo, de perto (por exemplo, a luz acesa, a fumacinha saindo, a superfície limpa); os 16 "
    "segundos ficam no mesmo lugar, sem aparecer pessoa, objeto ou produto novo, com no máximo um corte por parte, "
    "para um plano mais de perto do mesmo produto. Responda só com um JSON, sem nada antes ou depois:\n"
    '{{"serve": true ou false, "muda_na_ia": true ou false, "motivo": "...", "prompt": "...", "continuacao": '
    '"...", "fala": "...", "cena": "..."}}\n'
    + REGRAS_DA_FOTO +
    "- prompt: em inglês, até 90 palavras, os 8 primeiros segundos, em primeira pessoa: as mãos seguram o produto da "
    "foto, idêntico (mesma forma, cor, material, tamanho, quantidade e detalhes; nada acrescentado, tirado ou "
    "trocado), bem perto da câmera, e o põem na mesa com o que vem com ele; a voz fala do 1º segundo até por volta "
    "dos 7 segundos, sem pausa longa, entre aspas, em português do Brasil, 2 frases curtas com até "
    f"{PALAVRAS_DA_FALA_INTEIRA} palavras ao todo: o gancho (uma surpresa, uma dor que o produto resolve ou uma "
    "pergunta) e o que é o produto (por exemplo: \"Gente, olha esse umidificador! Já vem com as essências.\"). "
    "Escreva no pedido: Brazilian Portuguese voice-over narration from the person filming, no one speaks on camera, "
    "no face, authentic handheld smartphone footage, natural daylight, realistic home, no subtitles, no text.\n"
    "- continuacao: em inglês, até 90 palavras, os 8 segundos seguintes, continuando no mesmo lugar, com as mesmas "
    "mãos, a mesma voz e o mesmo produto, idêntico: as mãos fazem o uso mais simples do produto, e o resultado "
    "aparece de perto; a voz continua do 1º segundo até por volta dos 7 segundos, sem pausa longa, entre aspas, em "
    f"português do Brasil, 2 frases curtas com até {PALAVRAS_DA_FALA_INTEIRA} palavras ao todo: a vantagem que se "
    "vê e a chamada \"clica no carrinho laranja\" (por exemplo: \"O quarto fica cheiroso na hora. Clica no carrinho "
    "laranja!\"). Escreva no pedido: the same voice-over narration, no face, no subtitles, no text.\n"
    "- fala: tudo o que a voz fala, em português, as duas partes juntas, como vai sair no vídeo.\n"
    "- cena: uma frase em português que descreve a cena, para o Rafael.\n"
    + _FALA_SEM_EMBOLAR +
    " A fala vai sem marca, sem preço, sem dizer que todo mundo está comprando ou que vai acabar e "
    "sem prometer o que o produto não faz. Sem texto na tela, sem legenda, sem logotipo novo e sem outros produtos; "
    "nada perigoso, nojento ou com criança."
)
# O formato mãos e voz em 8 s (P262): um Gerar só, com um uso, o resultado logo à vista e a voz do 1º ao último
# segundo (o gancho, a vantagem e a chamada).
PEDIDO_DAS_MAOS_E_VOZ_CURTO = (
    "Você é diretor de vídeos curtos de produto para a Shopee Vídeo, no Brasil, e escreve como os vídeos que mais "
    "vendem no feed. A imagem é a foto oficial do anúncio do produto \"{nome}\". O Google Flow vai gerar um vídeo "
    "de 8 segundos, em pé (9:16) e com som, a partir dessa foto. É uma demonstração filmada pelos olhos de quem usa "
    "o produto (primeira pessoa): só as mãos aparecem, sem rosto, com a câmera na mão e sempre no produto, numa casa "
    "simples e arrumada do Brasil, com a luz do dia; por cima, a voz de uma pessoa comum, brasileira e animada, "
    "conta do 1º ao último segundo, como quem mostra uma descoberta para uma amiga (a narração de quem filma, sem "
    "ninguém falando na tela). A IA de vídeo inventa coisas quando a cena pede demais; por isso, o produto aparece "
    "inteiro, idêntico ao da foto, sem mudar de forma, cor ou tamanho; as mãos fazem um uso só, o mais simples do "
    "produto, com um gesto curto (apertar, ligar, encher, passar, colocar no lugar), sem montar, desmontar, cortar, "
    "cozinhar ou vestir, e o resultado aparece logo, de perto (por exemplo, a luz acesa, a fumacinha saindo, a "
    "superfície limpa); os 8 segundos ficam no mesmo lugar, sem aparecer pessoa, objeto ou produto novo, com no "
    "máximo um corte, para um plano mais de perto do mesmo produto. Responda só com um JSON, sem nada antes ou "
    "depois:\n"
    '{{"serve": true ou false, "muda_na_ia": true ou false, "motivo": "...", "prompt": "...", "fala": "...", '
    '"cena": "..."}}\n'
    + REGRAS_DA_FOTO +
    "- prompt: em inglês, até 90 palavras, os 8 segundos, em primeira pessoa: as mãos mostram o produto da foto, "
    "idêntico (mesma forma, cor, material, tamanho, quantidade e detalhes; nada acrescentado, tirado ou trocado), "
    "bem perto da câmera, e fazem o uso mais simples dele, com o resultado de perto; a voz fala do 1º segundo até "
    "perto do fim, sem pausa, entre aspas, em português do Brasil, 2 ou 3 frases curtas com até "
    f"{PALAVRAS_DA_FALA_INTEIRA} palavras ao todo: o gancho (uma surpresa, uma dor que o produto resolve ou uma "
    "pergunta), a vantagem que se vê e a chamada \"clica no carrinho laranja\" (por exemplo: \"Gente, olha esse "
    "umidificador! O quarto fica cheiroso na hora. Clica no carrinho laranja!\"). Escreva no pedido: Brazilian "
    "Portuguese voice-over narration from the person filming, no one speaks on camera, no face, authentic handheld "
    "smartphone footage, natural daylight, realistic home, no subtitles, no text.\n"
    "- fala: tudo o que a voz fala, em português, como vai sair no vídeo.\n"
    "- cena: uma frase em português que descreve a cena, para o Rafael.\n"
    + _FALA_SEM_EMBOLAR +
    " A fala vai sem marca, sem preço, sem dizer que todo mundo está comprando ou que vai acabar e "
    "sem prometer o que o produto não faz. Sem texto na tela, sem legenda, sem logotipo novo e sem outros produtos; "
    "nada perigoso, nojento ou com criança."
)
# O pedido da propaganda de TV de 8 s (P268 1): um Gerar só, com os cuidados contra as alucinações da P248 1 (o produto
# idêntico em todos os planos, sem mudar de estado, e um gesto só no plano de uso) e o locutor falando do 1º segundo
# até perto do fim, sem pausa longa, com o tanto de palavras do vídeo de 8 s (P262 e P264 4).
PEDIDO_DA_PROPAGANDA = (
    "Você é diretor de comerciais de TV e de streaming, no Brasil. A imagem é a foto oficial do anúncio do produto "
    "\"{nome}\". O Google Flow vai gerar um vídeo de 8 segundos, em pé (9:16) e com som, a partir dessa foto, com cara "
    "de propaganda de TV de verdade, feita por uma produtora, e não de vídeo caseiro, de vídeo de loja ou de vídeo "
    "feito por IA: o produto em 2 ou 3 planos de cinema ligados por cortes limpos, com luz de estúdio ou de cena bem "
    "cuidada, cores ricas, fundo desfocado e a câmera se movendo devagar (aproximação lenta, giro em volta do produto "
    "ou travelling). Os planos: a revelação do produto (por exemplo, a luz acendendo sobre ele num fundo escuro); o "
    "produto em uso num lugar bonito e real do Brasil (se aparecer alguém, só de passagem, de lado ou de costas, ou só "
    "as mãos, sem falar e sem olhar para a câmera); e, no fim, o produto sozinho no centro do quadro, como o plano "
    "final de um comercial. Por cima, um locutor profissional, brasileiro, com voz firme e calorosa, fala em off "
    "(ninguém fala na tela), com uma trilha suave de comercial por baixo. A IA de vídeo inventa coisas quando a cena "
    "pede demais; por isso, o produto aparece idêntico ao da foto em todos os planos, do jeito que é usado (vestido, "
    "montado, no lugar), sem mudar de forma, cor, tamanho ou estado; no plano de uso, um gesto só, o mais simples "
    "(acender, apoiar, passar, segurar), sem abrir, montar, desmontar, encaixar, despejar ou trocar peça; e não "
    "aparece outro produto nem objeto que se confunda com ele. Responda só com um JSON, sem nada antes ou depois:\n"
    '{{"serve": true ou false, "muda_na_ia": true ou false, "motivo": "...", "prompt": "...", "fala": "...", '
    '"cena": "..."}}\n'
    + REGRAS_DA_FOTO +
    "- prompt: em inglês, até 100 palavras, o comercial de 8 segundos, com os planos em ordem e o que se vê em cada "
    "um: o produto da foto, idêntico (mesma forma, cor, material, tamanho, quantidade e detalhes; nada acrescentado, "
    "tirado ou trocado) e bem à vista; o locutor fala do 1º segundo até perto do fim, sem pausa longa, entre aspas, em "
    f"português do Brasil, 2 ou 3 frases curtas com até {PALAVRAS_DA_FALA_INTEIRA} palavras ao todo, uma por plano: o "
    "gancho (uma promessa ou uma pergunta), a vantagem que se vê no produto e o slogan com a chamada para comprar (por "
    "exemplo: \"Seu quarto merece outra luz. Na medida certa, onde você quiser. Garanta a sua.\"). Escreva no pedido: "
    "premium TV commercial, shot on a cinema camera, photorealistic, real textures, no CGI look, cinematic lighting, "
    "shallow depth of field, smooth camera moves, clean cuts, final hero shot of the product, professional Brazilian "
    "Portuguese voice-over announcer, no one speaks on camera, subtle commercial music under the voice, no subtitles, "
    "no text, no logo.\n"
    "- fala: tudo o que o locutor fala, em português, como vai sair no vídeo.\n"
    "- cena: uma frase em português que descreve os planos do comercial, para o Rafael.\n"
    + _FALA_SEM_EMBOLAR +
    " A fala vai sem marca, sem preço, sem dizer que vai acabar e sem prometer o que o produto não faz. Sem texto na "
    "tela, sem legenda, sem logotipo novo e sem outros produtos; nada perigoso, nojento ou com criança."
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


def com_a_diccao(texto):
    """
    O prompt (ou a continuação) do vídeo com fala, com a DICCAO_CLARA no fim quando ele ainda não pede a dicção
    (P264 4), dentro das LETRAS_DO_PROMPT; o vazio fica vazio.
    """
    texto = " ".join(str(texto or "").split())
    if not texto or "diction" in texto.lower():
        return texto[:LETRAS_DO_PROMPT]
    return f"{texto[:LETRAS_DO_PROMPT - len(DICCAO_CLARA) - 1].rstrip()} {DICCAO_CLARA}"


def ler_resposta(texto, longo=False, unboxing=False, maos_e_voz=False, curto=False, propaganda=False):
    """
    {"serve", "muda_na_ia", "motivo", "estilo", "prompt", "cena"} da resposta da IA; None quando ela não
    veio num JSON ou disse que serve sem escrever o pedido. longo: a resposta do pedido de 16 s (P246 1), com a
    "continuacao" (o pedido do Estender, sem ela também None) e a "fala", no estilo do vendedor; unboxing: a do
    unboxing de 16 s (P256 2), sem fala; maos_e_voz: a do formato mãos e voz (P261 1), com a fala da voz. curto: a
    do pedido de 8 s (P262), do vendedor ou do mãos e voz, com a "fala" (sem ela, None) e sem a continuação;
    propaganda (com curto): a da propaganda de TV de 8 s (P268 1), com a fala do locutor.
    """
    if curto:
        resposta = ler_resposta(texto)
        if not resposta:
            return None
        achado = json.loads(re.search(r"\{.*\}", texto, re.S).group(0))
        fala = " ".join(str(achado.get("fala") or "").split())[:400]
        if resposta["serve"] and not fala:
            return None
        estilo = (ESTILO_DA_PROPAGANDA if propaganda else ESTILO_DAS_MAOS_E_VOZ if maos_e_voz
                  else ESTILO_DO_VENDEDOR)
        return dict(resposta, estilo=estilo, fala=fala,
                    prompt=com_a_diccao(resposta["prompt"]) if fala else resposta["prompt"])
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
    if longo:
        estilo = (ESTILO_DO_UNBOXING if unboxing else ESTILO_DAS_MAOS_E_VOZ if maos_e_voz
                  else ESTILO_DO_VENDEDOR)
    else:
        estilo = nome_do_estilo(dados.get("estilo"))
    resposta = {"serve": serve, "muda_na_ia": dados.get("muda_na_ia") is True,
                "motivo": " ".join(str(dados.get("motivo") or "").split())[:200], "estilo": estilo,
                "prompt": prompt[:1000], "cena": " ".join(str(dados.get("cena") or "").split())[:300]}
    if longo:
        fala = "" if unboxing else " ".join(str(dados.get("fala") or "").split())[:400]
        resposta.update(continuacao=continuacao[:LETRAS_DO_PROMPT], fala=fala)
        if fala:
            resposta.update(prompt=com_a_diccao(prompt), continuacao=com_a_diccao(continuacao))
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


def pedido_do_formato(nome, com_unboxing=True, com_comedia=False, com_maos_e_voz=False, com_duracao=False,
                      com_propaganda=False):
    """
    O pedido da escolha do formato do vídeo de IA, só com os formatos que podem sair agora (o vendedor sempre);
    com_duracao: a escolha da duração também, 8 ou 16 s (P262, TRECHO_DA_DURACAO); com_propaganda: a propaganda de TV
    também, sempre de 8 s (P269 1, TRECHO_DA_PROPAGANDA).
    """
    formatos = ([("vendedor", _FORMATO_DO_VENDEDOR)]
                + ([("maos_e_voz", _FORMATO_DAS_MAOS_E_VOZ)] if com_maos_e_voz else [])
                + ([("unboxing", _FORMATO_DO_UNBOXING)] if com_unboxing else [])
                + ([("comedia", _FORMATO_DA_COMEDIA)] if com_comedia else [])
                + ([(ESTILO_DA_PROPAGANDA, _FORMATO_DA_PROPAGANDA)] if com_propaganda else []))

    def juntar(partes):
        return ", ".join(partes[:-1]) + " ou " + partes[-1] if len(partes) > 1 else partes[0]
    return PEDIDO_DO_FORMATO.format(nome=nome, opcoes=juntar([texto for _, texto in formatos]),
                                    nomes=juntar([f'"{chave}"' for chave, _ in formatos]),
                                    de_16_s="" if com_duracao or com_propaganda else "de 16 segundos ",
                                    duracao=((TRECHO_DA_DURACAO if com_duracao else "")
                                             + (TRECHO_DA_PROPAGANDA if com_propaganda else "")),
                                    campo=CAMPO_DA_DURACAO if com_duracao else "")


def formato_do_video(nome, foto, com_unboxing=True, com_comedia=False, com_maos_e_voz=False, com_duracao=False,
                     com_propaganda=False):
    """
    (o formato, a duração em segundos, o porquê da IA) do vídeo de IA que a IA escolhe pela foto do anúncio (já em
    JPEG) e pelo nome, entre os formatos que podem sair agora: ESTILO_DO_UNBOXING (P256 2), ESTILO_DA_COMEDIA (P251 1),
    ESTILO_DAS_MAOS_E_VOZ (P262), ESTILO_DA_PROPAGANDA (P269 1) ou ESTILO_DO_VENDEDOR, que vale também quando ela não
    responde num JSON ou responde um formato que não podia sair. com_duracao (P262): o vendedor e o mãos e voz saem com
    8 s, a não ser que a IA diga 16 ("na dúvida, 8 segundos"); o unboxing e a comédia, e tudo sem com_duracao, com 16 s.
    A propaganda de TV sai sempre com 8 s.
    """
    texto = asyncio.run(api_gemini.gerar_texto_gemini(
        pedido_do_formato(nome, com_unboxing, com_comedia, com_maos_e_voz, com_duracao, com_propaganda),
        imagens=[(foto, "image/jpeg")]))
    achado = re.search(r"\{.*\}", texto or "", re.S)
    try:
        dados = json.loads(achado.group(0)) if achado else {}
    except ValueError:
        dados = {}
    if not isinstance(dados, dict):
        dados = {}
    pedido = unicodedata.normalize("NFKD", str(dados.get("formato") or "")).encode("ascii", "ignore").decode()
    pedido = pedido.strip().lower()
    if com_unboxing and pedido == ESTILO_DO_UNBOXING:
        formato = ESTILO_DO_UNBOXING
    elif com_comedia and pedido == "comedia":
        formato = ESTILO_DA_COMEDIA
    elif com_maos_e_voz and pedido.replace(" ", "_") == ESTILO_DAS_MAOS_E_VOZ:
        formato = ESTILO_DAS_MAOS_E_VOZ
    elif com_propaganda and pedido.startswith("propaganda"):
        formato = ESTILO_DA_PROPAGANDA
    else:
        formato = ESTILO_DO_VENDEDOR
    duracao = DURACAO_LONGA
    if formato == ESTILO_DA_PROPAGANDA:
        duracao = DURACAO_CURTA
    elif com_duracao and formato in (ESTILO_DO_VENDEDOR, ESTILO_DAS_MAOS_E_VOZ):
        pedida = re.search(r"\d+", str(dados.get("duracao") or ""))
        duracao = DURACAO_LONGA if pedida and int(pedida.group(0)) == DURACAO_LONGA else DURACAO_CURTA
    return formato, duracao, " ".join(str(dados.get("motivo") or "").split())[:160]


def ultimo_foi_unboxing():
    """Se o vídeo de IA mais recente da produção foi um unboxing (P256 2): o seguinte é o vendedor."""
    return producao().get("estilo") == ESTILO_DO_UNBOXING


def pedido_para_o_anuncio(link, nome, foto, evitar="", longo=False, fala_inteira=False, com_unboxing=False,
                          com_comedia=False, maos_e_voz=False, da_producao=False, propaganda=False):
    """
    O pedido do vídeo para o anúncio já em mãos (o link, o nome e os bytes da foto do anúncio): a foto sem os
    dados de câmera e o que a IA escreveu, num estilo diferente dos últimos vídeos quando combina (evitar, o
    trecho de evitar_os_recentes). (o pedido, serve): o pedido é {"link", "nome", "foto" (bytes), "estilo",
    "prompt", "cena"} quando a IA acha a foto boa para o vídeo; serve é False quando ela disse que a foto não
    serve, MUDA_NA_IA quando o produto tem o que a IA de vídeo costuma mudar (P245 1) e None quando não deu
    para saber (a foto não é uma imagem, ou a IA não respondeu). longo: o pedido do vídeo de 16 s com uma pessoa
    vendendo o produto (P246 1), com a "continuacao" do Estender, a "fala" e o "formato"; fala_inteira: o de 16 s com
    a fala do começo ao fim de cada parte (P255 1, a amostra). com_unboxing e com_comedia (só no de 16 s): a IA
    escolhe pelo produto entre o vendedor, o unboxing (P256 2) e a comédia (P251 1) (formato_do_video); o do unboxing
    vem sem fala. Na comédia, o pedido daqui é o do vendedor, pela foto do anúncio: o da comédia sai da imagem do
    personagem com o produto (imagem_da_producao), e este fica para quando a imagem não vale. maos_e_voz (só no de
    16 s): o pedido do formato mãos e voz (P261 1, a amostra), sem a escolha do formato. da_producao (o vídeo de IA
    do dia e o De IA ✨, P262): a IA escolhe também o mãos e voz, a propaganda de TV (P269 1) e a duração; o de 8 s
    ("duracao_pedida" 8) vem sem a continuação, com a fala do começo ao fim, e o de 16 s do vendedor, com a fala do
    começo ao fim de cada parte. propaganda: o pedido de 8 s com cara de propaganda de TV, com a fala do locutor, sem a
    escolha do formato: o da amostra (P268 1) e, desde a P269 3, o de todo vídeo de IA da produção, que o robô pede
    junto com da_producao (SO_A_PROPAGANDA_NA_PRODUCAO).
    """
    foto = jpeg_sem_metadados(foto) if foto and nome else None
    if not foto:
        return None, None
    formato, duracao, motivo_da_duracao = ESTILO_DO_VENDEDOR, DURACAO_LONGA, ""
    if propaganda:
        formato, duracao = ESTILO_DA_PROPAGANDA, DURACAO_CURTA
    elif longo and maos_e_voz:
        formato = ESTILO_DAS_MAOS_E_VOZ
    elif longo and not fala_inteira and (com_unboxing or com_comedia or da_producao):
        formato, duracao, motivo_da_duracao = formato_do_video(nome, foto, com_unboxing, com_comedia,
                                                               com_maos_e_voz=da_producao, com_duracao=da_producao,
                                                               com_propaganda=da_producao)
    # A propaganda de TV (a amostra da P268 1 e, desde a P269 3, todo vídeo de IA da produção) é de 8 s, como o de 8 s
    # da P262: um Gerar só, com a fala do locutor e sem a continuação.
    propaganda = formato == ESTILO_DA_PROPAGANDA
    curto = propaganda or (longo and duracao == DURACAO_CURTA)
    unboxing = formato == ESTILO_DO_UNBOXING
    maos = formato == ESTILO_DAS_MAOS_E_VOZ
    if propaganda:
        pedido = PEDIDO_DA_PROPAGANDA
    elif unboxing:
        pedido = PEDIDO_DO_UNBOXING
    elif maos:
        pedido = PEDIDO_DAS_MAOS_E_VOZ_CURTO if curto else PEDIDO_DAS_MAOS_E_VOZ
    elif curto:
        pedido = PEDIDO_DO_VENDEDOR_CURTO
    elif longo:
        # Na produção, o de 16 s fala do começo ao fim de cada parte, sem o "depois, calada" (P262).
        pedido = PEDIDO_DO_VENDEDOR_FALANDO if fala_inteira or da_producao else PEDIDO_DO_VENDEDOR
    else:
        pedido = PEDIDO_DA_IA
    resposta = ler_resposta(asyncio.run(api_gemini.gerar_texto_gemini(
        pedido.format(nome=nome, evitar=evitar, bebida=TRECHO_DA_BEBIDA if assistente.BEBIDA_EM_ESPERA else ""),
        imagens=[(foto, "image/jpeg")])), longo=longo and not curto, unboxing=unboxing, maos_e_voz=maos, curto=curto,
        propaganda=propaganda)
    if not resposta:
        return None, None
    if not resposta["serve"]:
        return None, False
    if resposta["muda_na_ia"]:
        return None, MUDA_NA_IA
    escolhido = {"link": link, "nome": nome, "foto": foto, "estilo": resposta["estilo"], "prompt": resposta["prompt"],
                 "cena": resposta["cena"]}
    if curto:
        escolhido.update(fala=resposta["fala"], formato=formato)
    elif longo:
        escolhido.update(continuacao=resposta["continuacao"], fala=resposta["fala"], formato=formato)
    if da_producao and longo:
        escolhido.update(duracao_pedida=duracao, motivo_da_duracao=motivo_da_duracao)
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


def esperar_o_video(d, ja_gerado=False, guardar_telas=True, espera=None):
    """
    Espera o vídeo novo ficar pronto no projeto, guardando a tela a cada INTERVALO_DOS_CASOS
    (casos_robo; guardar_telas=False na produção do dia, para as telas da espera não tirarem do
    servidor os casos das falhas, que ficam no máximo 30). Logo depois do Gerar, o "Gerando…" tem de
    aparecer em ESPERA_DO_GERANDO s (Parada sem ele: o Flow não gerou). ja_gerado=True (gerado numa
    vez anterior): pronto se ele não aparece. Os segundos até ficar pronto; None se não ficou em
    espera s (sem ela, ESPERA_DA_GERACAO; a imagem do modo Imagem espera menos, ESPERA_DA_IMAGEM).
    """
    limite = ESPERA_DA_GERACAO if espera is None else espera
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
        if passado >= limite:
            return None
        time.sleep(PAUSA_DA_LEITURA)


def _mais_novo(xml):
    """O quadro mais novo do projeto (o 1º da grade: o mais alto e, empatado, o da esquerda); None sem quadro."""
    quadros = [el for el in ps.elementos(xml)
               if el["pacote"] == PACOTE and el["clicavel"] and ITEM_DO_PROJETO.search(el["descricao"] or "")]
    return min(quadros, key=lambda el: (el["caixa"][1], el["caixa"][0])) if quadros else None


def quadro_mais_novo(xml):
    """O centro do quadro mais novo do projeto; None sem quadro."""
    quadro = _mais_novo(xml)
    if not quadro:
        return None
    x1, y1, x2, y2 = quadro["caixa"]
    return (x1 + x2) // 2, (y1 + y2) // 2


def descricao_do_mais_novo(xml):
    """A descrição do quadro mais novo do projeto (o nome que o Flow deu e os itens: "…, 1 item"); "" sem quadro."""
    quadro = _mais_novo(xml)
    return quadro["descricao"] if quadro else ""


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


def arquivos_novos(d, extensoes=(".mp4",)):
    """
    Os arquivos com essas extensões (os vídeos, ou as imagens do modo Imagem) que apareceram no celular depois da
    marca do Baixar: [(caminho, bytes)], o mais novo primeiro.
    """
    achados = []
    for extensao in extensoes:
        comando = ["find", *PASTAS_DO_BAIXAR, "-type", "f", "-name", f"*{extensao}", "-newer", MARCA_DO_BAIXAR,
                   "-exec", "stat", "-c", "%Y %s %n", "{}", "+"]
        try:
            saida = d.shell(comando).output or ""
        except Exception:
            continue
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


def puxar(d, remoto, local, o_que="o vídeo"):
    """Traz o arquivo (o vídeo ou a imagem) do celular ao servidor e tira do celular o arquivo e a marca do Baixar."""
    os.makedirs(os.path.dirname(local), exist_ok=True)
    try:
        d.pull(remoto, local)
    except Exception as e:
        raise Parada(f"baixar: {o_que} não veio do celular para o servidor ({type(e).__name__})")
    d.shell(["rm", "-f", remoto, MARCA_DO_BAIXAR])
    d.shell(["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", "file://" + remoto])
    if not os.path.exists(local) or not os.path.getsize(local):
        raise Parada(f"baixar: {o_que} não veio do celular para o servidor")


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


def foto_na_galeria(d, foto, sufixo=""):
    """Põe a foto do produto na galeria do celular, com nome novo; o nome do arquivo ("" se não apareceu)."""
    with open(foto, "rb") as arquivo:
        return ps.por_foto_na_galeria(d, arquivo.read(), nome=f"flow_{int(time.time())}{sufixo}")


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
    guardar_telas: a tela da espera do vídeo vai aos casos de minuto em minuto (esperar_o_video). A foto do Gerar é a
    da imagem do personagem com o produto, quando ela valeu ("foto_do_video", P260 1, no de 8 s da P262), ou a do
    anúncio.
    """
    nome_na_galeria = ""
    if not so_baixar:
        nome_na_galeria = foto_na_galeria(d, pedido.get("foto_do_video") or pedido["foto"])
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
        segundos = videos.duracao(local) or 0.0
        marcar(estado="baixado", arquivo=local, resolucao=resolucao, duracao=round(segundos),
               tamanho=f"{largura}x{altura}" if largura and altura else "")
        print(f"Flow: vídeo baixado ({resolucao or 'sem a janela da resolução'}, "
              f"{os.path.getsize(local) / 1e6:.1f} MB, {segundos:.0f} s)")
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
    A foto do Gerar é a da imagem do personagem com o produto, quando ela valeu ("foto_do_video", P260 1), ou a do
    anúncio.
    """
    estado = pedido.get("estado")
    nome_na_galeria = ""
    if estado not in ("gerando", "estendendo"):
        nome_na_galeria = foto_na_galeria(d, pedido.get("foto_do_video") or pedido["foto"])
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
# "continuacao" do Estender, a "fala" e o "formato"), a foto e o vídeo no servidor e as conferências (a da IA e, no de
# 16 s, a da fala, "fala_conferida"). Desde a P260 1, o de 16 s do vendedor e o da comédia guardam também a imagem do
# personagem com o produto ("imagem": o que houve com ela; "foto_do_video" e "personagem" quando ela valeu, e o pedido
# passa a ser o escrito por ela). Os estados: "parou" (antes do Gerar, sem gastar crédito) e "sem foto" (a IA não achou
# boa nenhuma das fotos desta vez, e há outros produtos para olhar), que tentam de novo no dia, até
# TENTATIVAS_ANTES_DO_GERAR; "sem produto" (nenhum produto da lista serve hoje), "gerando" (o Gerar foi tocado e falta o
# vídeo chegar ao servidor; no de 16 s, falta também o Estender), "estendendo" (no de 16 s, o Gerar do Estender foi
# tocado e falta baixar), "baixado" (falta a conferência), "pronto" (espera o rascunho), "descartado" (a IA viu outro
# produto no vídeo, ou o Flow não o entregou), "usado" (virou rascunho), "desistiu" (não virou rascunho em
# TENTATIVAS_DO_RASCUNHO) e "sem créditos" (o saldo do Flow não pagava o vídeo, SEM_CREDITOS). O robô escolhe o produto
# pelas regras dele e chama a produção na rodada dele, com a trava do celular na mão. Escolhas do Rafael (15/11/2026,
# P232 1 e P234 1; 17/11/2026, P247 1; 19/11/2026, P260 1): DECISOES.md.
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
# O formato de cada vídeo de IA da produção gerado no Flow (o estilo dele), anotado no Gerar: o limite da comédia (1 a
# cada VIDEOS_POR_COMEDIA, P251 1) olha os últimos. Só os FORMATOS_LEMBRADOS mais novos.
FORMATOS_LEMBRADOS = 6


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


def formatos_recentes():
    """Os formatos (o estilo) dos últimos vídeos de IA da produção gerados no Flow, o mais novo por último."""
    return [str(formato) for formato in (db.ler_config(CHAVE, {}) or {}).get("formatos") or []][-FORMATOS_LEMBRADOS:]


def lembrar_o_formato(estilo):
    """O vídeo de IA da produção foi gerado: o formato dele entra nos formatos_recentes."""
    def alterar(dados):
        dados["formatos"] = (list(dados.get("formatos") or []) + [str(estilo or "")])[-FORMATOS_LEMBRADOS:]
    db.atualizar_config(CHAVE, alterar)


def comedia_pode():
    """
    A comédia (P251 1) pode sair no próximo vídeo de IA? No máximo 1 a cada VIDEOS_POR_COMEDIA vídeos (nenhuma entre
    os últimos gerados) e só com a foto aprovada de um personagem da comédia (P259 1).
    """
    if ESTILO_DA_COMEDIA in formatos_recentes()[-(VIDEOS_POR_COMEDIA - 1):]:
        return False
    return any(chave in fotos_aprovadas() for chave in PERSONAGENS_DA_COMEDIA)


def comecar_producao(dia, escolhido, tentativas_de_gerar, do_botao=False):
    """
    Guarda o pedido do vídeo do dia (escolhido: o pedido_para_o_anuncio com o nome do vídeo de IA entre os
    vídeos do robô, "id", o produto, "item" e "valor", e de onde ele veio, "origem"), no estado "escolhido". A foto
    vai a um arquivo ao lado dos vídeos; o banco fica com o caminho. O pedido de 16 s (P247 1), com a "continuacao"
    do Estender, fica "longa", com a fala e o formato (o vendedor, o unboxing ou a comédia), fora da lista dos estilos
    dos últimos vídeos, a das amostras de 8 s (estilos_recentes), onde entra o estilo do pedido de 8 s. O de 8 s que a
    IA escolheu pelo produto (P262) fica "curta", com a fala e o formato, também fora dela; a propaganda de TV (P269 3)
    também. do_botao: o vídeo pedido no De IA ✨ do Preparar 1 Agora ⚡ (P243). Devolve o andamento novo.
    """
    recomecar_producao(dia, estado="escolhido", tentativas_de_gerar=tentativas_de_gerar,
                       **({"do_botao": True} if do_botao else {}))
    os.makedirs(PASTA, exist_ok=True)
    foto = os.path.join(PASTA, f"producao_{dia}.jpg")
    with open(foto, "wb") as arquivo:
        arquivo.write(escolhido["foto"])
    modelo, custo = MODELO_DA_PRODUCAO
    longa = bool(escolhido.get("continuacao"))
    # O de 8 s escolhido pela IA (P262): um Gerar só, como o de antes da P247 1, mas com a fala e o formato.
    curta = not longa and escolhido.get("duracao_pedida") == DURACAO_CURTA
    guardar_producao(id_video=escolhido["id"], link=escolhido["link"], nome=escolhido["nome"],
                     item=escolhido.get("item", ""), valor=escolhido.get("valor"), origem=escolhido.get("origem", ""),
                     foto=foto, estilo=escolhido["estilo"], prompt=escolhido["prompt"], cena=escolhido["cena"],
                     modelo=modelo, custo=custo, escolhido_em=agora(),
                     # O nível da escolha em que o produto entrou e os números dele (P252 1), para o aviso.
                     **({"nivel": escolhido["nivel"], "filtros": escolhido.get("filtros")}
                        if escolhido.get("nivel") else {}),
                     **({"longa": True, "continuacao": escolhido["continuacao"], "fala": escolhido.get("fala", "")}
                        if longa else {}),
                     **({"curta": True, "fala": escolhido.get("fala", "")} if curta else {}),
                     **({"formato": escolhido["formato"]} if (longa or curta) and escolhido.get("formato") else {}),
                     # A duração que a IA escolheu e o porquê (P262), para o aviso e o rascunho.
                     **({"duracao_pedida": escolhido["duracao_pedida"],
                         "motivo_da_duracao": escolhido.get("motivo_da_duracao", "")}
                        if escolhido.get("duracao_pedida") else {}))
    if not longa and not curta:
        guardar(estilos=(estilos_recentes() + [escolhido["estilo"]])[-ESTILOS_LEMBRADOS:])
    return producao()


def producao_no_celular(d, atual):
    """
    O vídeo do dia no Flow, na rodada do robô (a trava e a tela já conferidas por ele). O de 16 s ("longa", P247
    1): o Gerar dos 8 s no MODELO_DA_PRODUCAO, o Estender e o Baixar, em etapas que a rodada seguinte retoma pelo
    estado (no_flow_longo); antes do Gerar do vendedor e da comédia, a imagem do personagem com o produto (P260 1,
    imagem_da_producao): valendo, o vídeo sai dela; sem ela, pela foto do anúncio, como antes. O de 8 s (o "curta"
    que a IA escolheu, P262, com a imagem do personagem no vendedor, e o andamento de antes da P247 1): o Gerar e o
    Baixar, ou só o Baixar do que já foi gerado ("gerando"). True com o vídeo no servidor ("baixado"), False quando
    ele não ficou pronto a tempo (a próxima rodada continua); Parada com o passo que parou, com o caso guardado.
    """
    local = os.path.join(PASTA, f"producao_{atual['data']}.mp4")
    try:
        if pede_a_imagem(atual):
            atual = imagem_da_producao(d, atual)
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
    O Gerar conta também entre os do dia (gerados_no_dia, P243), e o formato do vídeo entra nos formatos_recentes (o
    limite da comédia, P251 1).
    """
    primeiro_gerar = False
    if campos.get("gerado_em"):
        atual = producao()
        primeiro_gerar = not atual.get("gerado_em")
        campos["gerados_no_dia"] = gerados_no_dia(atual.get("data"), atual) + (1 if primeiro_gerar else 0)
    guardar_producao(**campos)
    if campos.get("gerado_em"):
        lembrar_item_gerado(producao().get("item"))
    if primeiro_gerar:
        lembrar_o_formato(producao().get("estilo"))


def conferir_a_producao():
    """
    A conferência da IA do vídeo do dia com a foto do anúncio (conferir_o_video): "pronto" ou, com outro
    produto no vídeo, "descartado" (nunca vira rascunho). No pronto com fala (o de 16 s e o de 8 s da P262), o servidor
    ouve a fala e a compara com a pedida (conferir_a_fala, "fala_conferida"): a embolada ou cortada não descarta o
    vídeo; o aviso vai no rascunho, para o Rafael decidir na aprovação (P248 1 e P247 1). Com as mesmas palavras
    ouvidas, decide o silêncio (P262, decidir_o_silencio): cortado, o rascunho sai do vídeo sem ele ("arquivo"; o
    inteiro fica em "arquivo_inteiro"); a propaganda de TV (P269 3) fica sempre inteira. Devolve o estado novo.
    """
    atual = producao()
    conferencia = conferir_o_video(atual["arquivo"], atual["foto"])
    estado = "descartado" if conferencia["mesmo"] is False else "pronto"
    extra = {}
    if estado == "pronto" and (atual.get("longa") or atual.get("curta")) and atual.get("fala"):
        ouvidas = videos.palavras_faladas(atual["arquivo"])
        extra["fala_conferida"] = conferir_a_fala(atual["arquivo"], atual["fala"], ouvidas)
        silencio = decidir_o_silencio(atual["arquivo"], ouvidas,
                                      propaganda=atual.get("formato") == ESTILO_DA_PROPAGANDA)
        extra["silencio"] = {chave: valor for chave, valor in silencio.items() if chave != "arquivo"}
        if silencio.get("arquivo"):
            extra.update(arquivo=silencio["arquivo"], arquivo_inteiro=atual["arquivo"])
    guardar_producao(estado=estado, conferencia=conferencia, conferido_em=agora(), **extra)
    return estado


# Os porquês fixos da decisão do silêncio (P262): vão ao registro e à legenda, sem nada do vídeo.
SEM_SILENCIO = "sem silêncio de mais de 1 s"
SEM_OUVIR = "não deu para ouvir a fala"
SEM_DURACAO = "sem a duração do vídeo"
SOBRARIA_POUCO = "sobraria pouco vídeo"
CORTE_FALHOU = "o corte não saiu"
# A propaganda de TV (P269 3) fica sempre inteira, como o Flow a gerou: os planos de cinema e o produto sozinho no fim,
# depois da última frase do locutor, são o comercial; o corte do silêncio tiraria o fim e poria o pulo com o zoom no
# meio dos planos (decisão do Claude pela P262, que deixou a ele o que fazer com o silêncio de cada vídeo).
PROPAGANDA_INTEIRA = "a propaganda de TV fica inteira"


def decidir_o_silencio(arquivo, palavras, propaganda=False):
    """
    O que fazer com o silêncio do vídeo de IA pronto (P262), pelas palavras ouvidas (videos.palavras_faladas):
    {"decisao": "cortado" ou "mantido", "motivo" (um dos porquês fixos; "" no cortado), "antes" e "depois" (as
    durações), "cortes" e, no cortado, "arquivo" (o vídeo sem o silêncio, ao lado do inteiro)}. Mantido sem silêncio de
    mais de PARADO_MAXIMO s, sem ouvir a fala ou ler a duração, quando o corte deixaria menos de
    DURACAO_MINIMA_DO_CORTE s ou quando o ffmpeg falha. propaganda: a propaganda de TV (P269 3), sempre mantida
    (PROPAGANDA_INTEIRA).
    """
    antes = round(videos.duracao(arquivo) or 0.0, 1)
    mantido = {"decisao": "mantido", "antes": antes, "depois": antes, "cortes": 0}
    if propaganda:
        return dict(mantido, motivo=PROPAGANDA_INTEIRA)
    if palavras is None:
        return dict(mantido, motivo=SEM_OUVIR)
    if not antes:
        return dict(mantido, motivo=SEM_DURACAO)
    trechos = trechos_sem_o_parado(palavras, antes)
    if not trechos:
        return dict(mantido, motivo=SEM_SILENCIO)
    if sum(fim - inicio for inicio, fim in trechos) < DURACAO_MINIMA_DO_CORTE:
        return dict(mantido, motivo=SOBRARIA_POUCO)
    corte = cortar_o_parado(arquivo, palavras)
    if not corte["arquivo"]:
        return dict(mantido, motivo=CORTE_FALHOU)
    return {"decisao": "cortado", "motivo": "", "antes": corte["antes"], "depois": corte["depois"],
            "cortes": corte["cortes"], "arquivo": corte["arquivo"]}


def linha_da_duracao(atual):
    """
    A linha da duração do vídeo de IA no aviso e no rascunho (P262): 8 s sem o Estender ou 16 s, com o porquê que a IA
    deu; "" no andamento sem a duração escolhida (o de antes da P262 e as amostras).
    """
    pedida = atual.get("duracao_pedida")
    if not pedida:
        return ""
    porque = atual.get("motivo_da_duracao") or ""
    if atual.get("formato") == ESTILO_DA_PROPAGANDA:
        return "⏱️ 8 s, sem o Estender (a propaganda de TV tem sempre 8 s)"
    if pedida == DURACAO_CURTA:
        return f"⏱️ 8 s, sem o Estender (a IA escolheu pelo produto{': ' + porque if porque else ''})"
    if atual.get("formato") in (ESTILO_DO_UNBOXING, ESTILO_DA_COMEDIA):
        return "⏱️ 16 s, com o Estender (o unboxing e a comédia têm sempre 16 s)"
    return f"⏱️ 16 s, com o Estender (a IA escolheu pelo produto{': ' + porque if porque else ''})"


def linha_do_silencio(atual):
    """A linha da decisão do silêncio (P262) no aviso e no rascunho; "" sem ela."""
    silencio = atual.get("silencio") or {}
    if silencio.get("decisao") == "cortado":
        return (f"✂️ Silêncio cortado: de {_segundos(silencio['antes'])} para {_segundos(silencio['depois'])} "
                f"({silencio['cortes']} pedaço(s) parado(s) tirado(s), com um zoom leve depois de cada corte)")
    if silencio.get("decisao") == "mantido":
        return {SEM_SILENCIO: "✂️ Sem silêncio para cortar: o vídeo fica inteiro",
                SEM_OUVIR: "✂️ Silêncio não conferido (não deu para ouvir a fala): o vídeo fica inteiro",
                SEM_DURACAO: "✂️ Silêncio não conferido (sem a duração do vídeo): o vídeo fica inteiro",
                SOBRARIA_POUCO: (f"✂️ Silêncio não cortado: sobrariam menos de {_segundos(DURACAO_MINIMA_DO_CORTE)} "
                                 "de vídeo; ele fica inteiro, para você decidir na aprovação"),
                PROPAGANDA_INTEIRA: ("✂️ Propaganda de TV: o vídeo fica inteiro, sem cortar o silêncio (os planos e o "
                                     "produto no fim são o comercial)"),
                }.get(silencio.get("motivo"), "✂️ Silêncio não cortado (o corte não saiu): o vídeo fica inteiro")
    return ""


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
    (P247 1), a duração, o custo das duas partes, a fala pedida e a fala que o servidor ouviu (P248 1), e o personagem
    ou por que o vídeo saiu sem ele (P260 1, linha_do_personagem). Desde a P262, a duração que a IA escolheu (8 ou
    16 s, linha_da_duracao) e o silêncio cortado ou mantido (linha_do_silencio).
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
    # A duração que a IA escolheu pelo produto (P262).
    if linha_da_duracao(atual):
        linhas.append(linha_da_duracao(atual))
    if linha_do_personagem(atual):
        linhas.append(linha_do_personagem(atual))
    if atual.get("fala"):
        # Na propaganda de TV (P269 3), a fala é a do locutor, em off.
        rotulo = "🎙️ Locutor" if atual.get("formato") == ESTILO_DA_PROPAGANDA else "🗣️ Fala"
        linhas.append(f"{rotulo}: {atual['fala']}")
    linhas.append(f"🎥 Cena: {atual.get('cena', '')}")
    if com_a_conferencia:
        linhas.append(f"🔎 A IA conferiu: {conferido}")
    if atual.get("fala_conferida"):
        # A fala embolada ou cortada não descarta o vídeo: o Rafael decide na aprovação (P248 1).
        linhas.append(texto_da_fala(atual["fala_conferida"]))
    # O silêncio cortado ou o vídeo mantido inteiro (P262).
    if linha_do_silencio(atual):
        linhas.append(linha_do_silencio(atual))
    if conferencia.get("defeitos"):
        linhas.append(f"⚠️ O que parece IA: {conferencia['defeitos']}")
    return "\n".join(linhas)


# --- Os personagens fixos e a imagem do modo Imagem (P253 1, P250 1 e P258 1) ---
# Os 10 personagens fixos do vídeo de IA: os 4 do Rafael (Bonitão, Clássica, Largadão e Desastrada, os dois
# últimos para a comédia), os 4 que o Claude sugeriu (Vovó, Mãe Prática, Jovem Antenado e Faz-Tudo) e a
# Desconfiada e o Exagerado (P258 1). Cada um é uma pessoa inventada, sem parecer ninguém famoso, com tons de pele
# variados; a foto de cada um é feita uma vez, no modo Imagem do Flow, que não gasta crédito (0 créditos de IA,
# lido em 18/11/2026), e vai só ao privado do Rafael para aprovar antes de valer. Na comédia, a graça é da
# situação, nunca do corpo, da aparência ou de um grupo (15/11). Escolhas do Rafael (P250 1 e P258 1): DECISOES.md,
# Shopee Vídeo.
PERSONAGENS = (
    {"chave": "bonitao", "nome": "Bonitão", "resumo": "homem forte e bonito",
     "quem": "um homem de uns 30 anos, forte e bonito, de pele morena, cabelo curto e barba bem aparada, com "
             "camiseta lisa azul-marinho", "jeito": "um sorriso confiante", "onde": "numa sala moderna e clara"},
    {"chave": "classica", "nome": "Clássica", "resumo": "mulher bonita, de beleza clássica",
     "quem": "uma mulher de uns 35 anos, bonita, de beleza clássica e elegante, de pele clara, cabelo castanho "
             "liso preso num coque baixo, com blusa de seda cor creme", "jeito": "um sorriso discreto",
     "onde": "numa sala clara com plantas"},
    {"chave": "largadao", "nome": "Largadão", "resumo": "homem gordo e desleixado, para a comédia",
     "quem": "um homem de uns 40 anos, gordo, de jeito largado e bem-humorado, de pele parda, barba por fazer, "
             "com camiseta folgada", "jeito": "um sorriso preguiçoso e simpático",
     "onde": "sentado num sofá de uma sala simples"},
    {"chave": "desastrada", "nome": "Desastrada", "resumo": "mulher gorda e atrapalhada, para a comédia",
     "quem": "uma mulher de uns 30 anos, gorda, alegre e de jeito atrapalhado, de pele negra, cabelo cacheado "
             "volumoso, com blusa colorida", "jeito": "uma risada espontânea", "onde": "numa cozinha de casa"},
    {"chave": "vovo", "nome": "Vovó", "resumo": "cozinha, saúde e casa",
     "quem": "uma senhora de uns 70 anos, carinhosa, de pele clara, cabelo grisalho curto e óculos, com avental "
             "florido", "jeito": "um sorriso acolhedor", "onde": "numa cozinha aconchegante"},
    {"chave": "mae_pratica", "nome": "Mãe Prática", "resumo": "organização, limpeza e coisas de criança",
     "quem": "uma mulher de uns 38 anos, prática e organizada, de pele morena, cabelo preso num rabo de cavalo, "
             "com roupa confortável de ficar em casa", "jeito": "um sorriso decidido",
     "onde": "numa sala arrumada, sem ninguém mais na cena"},
    {"chave": "jovem_antenado", "nome": "Jovem Antenado", "resumo": "celular, fone e aparelhos",
     "quem": "um rapaz de uns 22 anos, antenado em tecnologia, de pele negra, cabelo curto moderno, com moletom",
     "jeito": "uma cara animada", "onde": "num quarto com uma luz de LED azul ao fundo"},
    {"chave": "faz_tudo", "nome": "Faz-Tudo", "resumo": "ferramentas, carro e reparos",
     "quem": "um homem de uns 50 anos, de mão na massa, de pele parda, bigode, com camisa xadrez de trabalho",
     "jeito": "um sorriso de quem resolve", "onde": "numa garagem com ferramentas penduradas ao fundo"},
    {"chave": "desconfiada", "nome": "Desconfiada", "resumo": "duvida do produto até ele provar que funciona",
     "quem": "uma mulher de uns 45 anos, de pele clara com sardas, cabelo ruivo curto, com blusa de tricô",
     "jeito": "cara de desconfiada, com uma sobrancelha levantada", "onde": "numa sala de estar"},
    {"chave": "exagerado", "nome": "Exagerado", "resumo": "se espanta com tudo",
     "quem": "um homem de uns 35 anos, muito expressivo, de pele morena, cabelo cacheado, com camisa estampada",
     "jeito": "cara de espanto exagerado, de olhos arregalados e boca aberta", "onde": "numa sala de estar"},
)
# Quem entra em cada formato do vídeo de IA (P250 1 e P258 1): o Largadão e a Desastrada são só da comédia; na
# comédia, a Desconfiada e o Exagerado se juntam a eles; no vendedor, os outros 8. Na comédia, a graça vem do jeito
# de cada um diante do produto, nunca do corpo, da aparência ou de um grupo: é o que a IA recebe de cada um.
SO_NA_COMEDIA = ("largadao", "desastrada")
GRACA_NA_COMEDIA = {
    "largadao": "o preguiçoso bem-humorado, que se anima quando o produto facilita a vida",
    "desastrada": "a atrapalhada alegre, que ri das próprias trapalhadas",
    "desconfiada": "a desconfiada, de sobrancelha levantada, que duvida do produto até ele provar que funciona",
    "exagerado": "o exagerado, que se espanta com tudo, de olhos arregalados",
}
PERSONAGENS_DA_COMEDIA = tuple(GRACA_NA_COMEDIA)
# O pedido da foto de cada personagem no modo Imagem: só a pessoa, em pé no quadro (9:16), como num vídeo de
# celular, sem produto (o produto entra depois, na imagem do personagem com ele, P253 1).
PEDIDO_DO_PERSONAGEM = (
    "Foto realista e natural, na vertical, como o quadro de um vídeo de celular de um criador de conteúdo "
    "brasileiro: {quem}, com {jeito}, da cintura para cima, olhando para a câmera, {onde}, com luz natural "
    "suave. Uma pessoa inventada, que não se pareça com ninguém famoso. Sem texto, sem logotipo, sem marca-d'água "
    "e sem nada nas mãos."
)


def personagem(chave):
    """O personagem pela chave ("vovo"); None sem ele."""
    return next((p for p in PERSONAGENS if p["chave"] == chave), None)


def pedido_do_personagem(p):
    """O texto do pedido da foto do personagem no modo Imagem."""
    return PEDIDO_DO_PERSONAGEM.format(quem=p["quem"], jeito=p["jeito"], onde=p["onde"])


# O modo Imagem (mapeado no celular do robô em 18/11 e 19/11/2026): Criar → Imagem → o texto → o modelo da imagem
# (Nano Banana 2.1, 9:16, x1, "A geração vai usar 0 créditos de IA") → Gerar. A imagem fica pronta em menos de 1 min
# como o 1º quadro do projeto, com o "Gerando…" antes, como o vídeo; aberta, o título traz o nome que o Flow dá, o
# modelo e o tamanho ("Red apple on wooden table\n.. Nano Banana 2.1\n768p"), com Fechar, Mais opções, Editar e
# Animar. Mais opções → Baixar abre a janela "Baixar imagem": 1K (o tamanho original, marcado), 2K (aumentar a
# resolução) e 4K (só com um plano maior, ao lado do "Assine um plano com IA do Google"). O robô baixa no tamanho
# original, sem custo, e nunca toca no 2K, no 4K nem no plano.
MODELO_DA_IMAGEM = "Nano Banana 2.1"
# A imagem fica pronta em menos de 1 min: a que passa disto não vem mais (o vídeo espera ESPERA_DA_GERACAO).
ESPERA_DA_IMAGEM = 3 * 60
TITULO_DA_JANELA_DA_IMAGEM = "baixar imagem"
EXTENSOES_DA_IMAGEM = (".png", ".jpg", ".jpeg", ".webp")
PASTA_DOS_PERSONAGENS = os.path.join(PASTA, "personagens")


def montar_o_pedido_da_imagem(d, prompt, com_foto=False):
    """
    Criar → Imagem → (com_foto: a foto mais nova da galeria, como no pedido do vídeo) → o texto → o modelo da imagem
    (9:16, x1); a tela pronta para o Gerar (Parada no que falhar).
    """
    tocar(d, "Criar", "criar")
    tocar(d, "Imagem", "modo imagem")
    # Como no pedido do vídeo: o pedido guardado de antes (foto ou texto) não é apagado às cegas.
    xml = esperar(d, lambda x: any(el["classe"] == "EditText" for el in ps.elementos(x)))
    if not xml:
        raise Parada("pedido da imagem: a caixa do pedido não apareceu")
    if fotos_no_pedido(xml) or texto_do_pedido(xml).strip():
        raise Parada("pedido da imagem: já tinha foto ou texto de antes")
    if com_foto:
        # O modo Imagem usa uma foto de referência só (com duas marcadas no seletor, só a 1ª entrou, 19/11/2026).
        tocar(d, "Adicionar mídia", "adicionar a foto da imagem")
        tocar(d, "Imagens", "imagens da imagem")
        if not esperar(d, lambda x: PACOTE_DO_SELETOR in x and ps.achar(x, "Item Foto")):
            raise Parada("seletor de fotos: a foto da imagem não apareceu")
        tocar(d, "Item Foto", "escolher a foto da imagem")
        tocar(d, "@button_add", "adicionar a foto da imagem")
        # A miniatura sobe ao Flow antes de aparecer (um quadro cinza, sem a imagem, por uns segundos).
        if not esperar(d, foto_no_pedido, 30):
            raise Parada("foto no pedido da imagem: a miniatura não apareceu")
    ponto = ponto_parado(d, centro_da_caixa, "texto do pedido da imagem")
    if not ponto:
        raise Parada("pedido da imagem: a caixa não apareceu")
    d.click(*ponto)
    time.sleep(1)
    ps.escrever(d, prompt)
    if not esperar(d, lambda x: " ".join(texto_do_pedido(x).split())[:40] == " ".join(prompt.split())[:40], 10):
        raise Parada("pedido da imagem: o texto não entrou na caixa")
    atual = modelo_no_pedido(_tela(d))
    if not atual:
        raise Parada("pedido da imagem: o botão do modelo não apareceu")
    tocar(d, f"{atual} x", "abrir o modelo da imagem")
    if atual != MODELO_DA_IMAGEM:
        tocar(d, atual, "lista de modelos da imagem")
        tocar(d, MODELO_DA_IMAGEM, "escolher o modelo da imagem")
        if not esperar(d, lambda x: modelo_no_pedido(x) == MODELO_DA_IMAGEM):
            raise Parada("pedido da imagem: o modelo da imagem não ficou marcado")
    for opcao in ("9:16", "x1"):
        tocar(d, opcao, f"opção {opcao} da imagem")
    return esperar(d, lambda x: custo_na_tela(x) is not None) or _tela(d)


def pronto_para_gerar_a_imagem(xml, prompt, fotos=0):
    """
    "" quando o pedido da imagem está certo (as fotos pedidas, o texto, o modelo da imagem e sem custo); senão, o que
    falta.
    """
    if fotos_no_pedido(xml) != fotos:
        return "a foto da imagem não está no pedido" if fotos else "o pedido da imagem tem foto"
    if " ".join(texto_do_pedido(xml).split())[:40] != " ".join(prompt.split())[:40]:
        return "o texto do pedido não entrou"
    if modelo_no_pedido(xml) != MODELO_DA_IMAGEM:
        return "o modelo marcado não é o da imagem"
    if custo_na_tela(xml) != 0:
        return "a imagem não sai de graça"
    return ""


def titulo_da_imagem(xml):
    """As linhas do título da imagem aberta (o nome, o modelo e o tamanho); None fora da imagem aberta."""
    for el in ps.elementos(xml):
        descricao = el["descricao"] or ""
        if el["pacote"] == PACOTE and not el["clicavel"] and MODELO_DA_IMAGEM in descricao and "\n" in descricao:
            return [" ".join(linha.split()) for linha in descricao.split("\n")]
    return None


def abrir_a_imagem_nova(d, antes=""):
    """
    No projeto: o quadro mais novo (a imagem que acabou de ficar pronta), conferindo no título que é uma imagem.
    antes: a descrição do mais novo antes do Gerar; com ela ainda no alto, o Flow não fez a imagem, e o robô não
    abre a de antes (ela iria ao Rafael como a foto de outro personagem).
    """
    ponto = ponto_parado(d, quadro_mais_novo, "imagem nova")
    if not ponto:
        raise Parada("baixar a imagem: a imagem nova não apareceu no projeto")
    if antes and descricao_do_mais_novo(_tela(d)) == antes:
        raise Parada("baixar a imagem: o mais novo do projeto ainda é o de antes do Gerar; a imagem não foi feita")
    d.click(*ponto)
    if not esperar(d, lambda x: titulo_da_imagem(x) is not None):
        raise Parada("baixar a imagem: o mais novo do projeto não abriu como uma imagem do modelo da imagem")


def janela_da_imagem(xml):
    """
    A janela "Baixar imagem": {"original": {"centro" (o botão redondo da linha do tamanho original), "marcada"},
    "baixar" (o centro do Baixar da janela)}; None sem ela, sem a linha do tamanho original ou sem o Baixar.
    """
    elementos = [el for el in ps.elementos(xml) if el["pacote"] == PACOTE]

    def texto(el):
        return " ".join(f"{el['texto']} {el['descricao']}".split()).casefold()
    if not any(texto(el) == TITULO_DA_JANELA_DA_IMAGEM for el in elementos):
        return None
    linha = next((el for el in elementos if el["classe"] != "RadioGroup" and "tamanho original" in texto(el)), None)
    if not linha:
        return None
    x1, y1, x2, y2 = linha["caixa"]
    redondo = next((el for el in elementos if el["classe"] == "RadioButton" and x1 <= el["caixa"][0]
                    and el["caixa"][2] <= x2 and y1 <= el["caixa"][1] and el["caixa"][3] <= y2), None)
    botao = next((el for el in elementos if el["classe"] == "Button" and texto(el) == "baixar"), None)
    if not redondo or not botao:
        return None
    return {"original": {"centro": _centro(redondo), "marcada": redondo["marcado"]}, "baixar": _centro(botao)}


def baixar_a_imagem(d):
    """
    Na imagem aberta: Mais opções → Baixar → na janela "Baixar imagem", o tamanho original (1K, sem custo) → Baixar.
    O caminho do arquivo no celular, quando ele para de crescer. Nunca toca no 2K, no 4K nem no plano.
    """
    d.shell(["touch", MARCA_DO_BAIXAR])
    # A hora do arquivo baixado tem de passar a da marca.
    time.sleep(1.1)
    tocar(d, "Mais opções", "mais opções da imagem")
    tocar(d, "Baixar", "baixar a imagem")
    xml = esperar(d, lambda x: janela_da_imagem(x) is not None, ESPERA_DA_JANELA_DO_BAIXAR)
    if not xml:
        raise Parada("baixar a imagem: a janela do tamanho não apareceu")
    janela = janela_da_imagem(xml)
    if not janela["original"]["marcada"]:
        d.click(*janela["original"]["centro"])
        xml = esperar(d, lambda x: bool(((janela_da_imagem(x) or {}).get("original") or {}).get("marcada")),
                      ESPERA_DA_JANELA_DO_BAIXAR)
        if not xml:
            raise Parada("baixar a imagem: o tamanho original não ficou marcado; o robô não baixa em outro")
        janela = janela_da_imagem(xml)
    d.click(*janela["baixar"])
    if not esperar(d, lambda x: janela_da_imagem(x) is None, ESPERA_PARA_A_JANELA_FECHAR):
        raise Parada("baixar a imagem: a janela do tamanho não fechou depois do Baixar")
    fim, anterior = time.monotonic() + ESPERA_DO_BAIXAR, None
    while True:
        xml = _tela(d)
        if xml and (tem_termos(xml) or pede_escolha(xml)):
            raise Parada("baixar a imagem: o Flow pediu outra escolha; o robô não escolhe pelo Rafael")
        novos = arquivos_novos(d, EXTENSOES_DA_IMAGEM)
        if novos and novos[0][1] > 0 and novos[0] == anterior:
            return novos[0][0]
        anterior = novos[0] if novos else None
        if time.monotonic() >= fim:
            raise Parada("baixar a imagem: o arquivo da imagem não apareceu no celular")
        time.sleep(2)


def gerar_a_imagem(d, prompt, local, com_foto=False):
    """
    No projeto do robô já aberto: a imagem do pedido no modo Imagem, com tudo conferido na tela antes do Gerar (o
    modelo da imagem e os 0 créditos), baixada no tamanho original e trazida ao servidor em local, em JPEG sem
    metadados; no fim, a imagem fecha e o robô volta ao projeto. com_foto: com a foto mais nova da galeria de
    referência. Parada com o passo que parou; a imagem que não fica pronta em ESPERA_DA_IMAGEM também.
    """
    antes = descricao_do_mais_novo(_tela(d))
    xml = montar_o_pedido_da_imagem(d, prompt, com_foto)
    falta = pronto_para_gerar_a_imagem(xml, prompt, 1 if com_foto else 0)
    if falta:
        raise Parada(f"antes do Gerar da imagem: {falta}")
    tocar(d, "Gerar", "gerar a imagem")
    if esperar_o_video(d, guardar_telas=False, espera=ESPERA_DA_IMAGEM) is None:
        raise Parada("gerar a imagem: a imagem não ficou pronta a tempo")
    abrir_a_imagem_nova(d, antes)
    remoto = baixar_a_imagem(d)
    baixada = local + ".baixada"
    puxar(d, remoto, baixada, "a imagem")
    with open(baixada, "rb") as arquivo:
        dados = jpeg_sem_metadados(arquivo.read())
    os.remove(baixada)
    if not dados:
        raise Parada("baixar a imagem: o arquivo que veio não é uma imagem")
    with open(local, "wb") as arquivo:
        arquivo.write(dados)
    tocar(d, "Fechar", "fechar a imagem")


def fotos_guardadas():
    """{chave: {"arquivo", "feita_em", "mandada_em", "aprovada_em"}} das fotos dos personagens."""
    return dict((db.ler_config(CHAVE, {}) or {}).get("personagens") or {})


def marcar_foto(chave, **campos):
    db.atualizar_config(CHAVE, lambda dados: dados.setdefault("personagens", {}).setdefault(chave, {}).update(campos))


def fotos_aprovadas():
    """As fotos que valem (P250 1): {chave: arquivo} das que o Rafael aprovou e continuam no servidor."""
    return {chave: foto["arquivo"] for chave, foto in fotos_guardadas().items()
            if foto.get("aprovada_em") and foto.get("mandada_em") and os.path.exists(foto.get("arquivo") or "")}


def aprovar_as_fotos(chaves=None):
    """
    O OK do Rafael às fotos dos personagens (P259 1), dado na conversa com o Claude: marca como aprovadas as fotos
    que ele viu no privado; sem chaves, todas as dos 10 personagens; com chaves, essas. Nada é marcado quando uma
    chave não existe ou quando uma das fotos pedidas não foi ao privado (ele não a viu). A foto refeita perde a marca
    ao ser feita e só volta a valer com um OK novo. 0 aprovou, 1 não. Só chaves e números no log.
    """
    if chaves and not set(chaves) <= {p["chave"] for p in PERSONAGENS}:
        print("Personagens: chave desconhecida; as chaves são " + ", ".join(p["chave"] for p in PERSONAGENS))
        return 1
    guardadas = fotos_guardadas()
    pedidas = [p["chave"] for p in PERSONAGENS if not chaves or p["chave"] in chaves]
    sem_ver = [chave for chave in pedidas if not (guardadas.get(chave, {}).get("mandada_em")
                                                  and os.path.exists(guardadas[chave].get("arquivo") or ""))]
    if sem_ver:
        print("Personagens: nada foi aprovado; sem a foto no privado: " + ", ".join(sem_ver))
        return 1
    for chave in pedidas:
        marcar_foto(chave, aprovada_em=agora())
    print(f"Personagens: {len(pedidas)} foto(s) aprovada(s); valendo: {len(fotos_aprovadas())} de {len(PERSONAGENS)}")
    return 0


def legenda_do_personagem(p, numero, total):
    """A legenda da foto no privado do Rafael: quem é e o que ele faz com ela."""
    return (f"👤 Personagem {numero} de {total}: {p['nome']} ({p['resumo']})\n"
            "Foto feita no Google Flow, no modo Imagem, sem gastar crédito (P250 1). Ela só vale depois do seu OK: "
            "aprove ou peça outra na conversa com o Claude.")


def fotos_dos_personagens(chaves=None):
    """
    As fotos dos personagens (P250 1 e P258 1) no modo Imagem do Flow, que não gasta crédito: uma por personagem,
    baixada para o servidor (PASTA_DOS_PERSONAGENS) e mandada ao privado do Rafael com o nome e o jeito, para ele
    aprovar ou pedir outra. Sem chaves, as que ainda não foram mandadas; com chaves, essas, de novo (outra foto).
    A feita e não mandada (o privado falhou) vai na próxima vez, sem gerar outra. 0 deu certo, 1 parou. Só rótulos
    fixos, chaves e números no log.
    """
    guardadas = fotos_guardadas()
    lista = [p for p in PERSONAGENS if (p["chave"] in chaves if chaves else not guardadas.get(p["chave"], {}).get(
        "mandada_em"))]
    if chaves and len(lista) != len(set(chaves)):
        print("Personagens: chave desconhecida; as chaves são " + ", ".join(p["chave"] for p in PERSONAGENS))
        return 1
    if not lista:
        print("Personagens: todas as fotos já foram mandadas; para refazer, passe as chaves")
        return 0
    por_gerar = [p for p in lista if chaves or not os.path.exists(guardadas.get(p["chave"], {}).get("arquivo") or "")]
    if por_gerar:
        if not celular_robo.conectado():
            print("celular: desconectado; conecte pelo bot (Shopee Vídeo 🎬 → Celular do Robô 📱)")
            return 1
        tentativas = ps.ESPERA_DO_CELULAR // ps.PAUSA_DA_ESPERA + 1
        for tentativa in range(tentativas):
            with celular_robo.trava() as livre:
                if livre:
                    codigo = _fotos_no_celular(por_gerar)
                    break
            if tentativa == 0:
                print(f"celular: o robô automático está tocando no celular; esperando ele soltar "
                      f"(até {ps.ESPERA_DO_CELULAR // 60} min)")
            if tentativa < tentativas - 1:
                time.sleep(ps.PAUSA_DA_ESPERA)
        else:
            print("celular: o robô automático continua tocando no celular; nada foi tocado")
            return 1
    else:
        codigo = 0
    # As fotos vão ao privado com o celular já solto para o robô automático; a refeita perdeu o "mandada_em" ao ser
    # feita, e a que o celular não refez fica como estava.
    guardadas, mandadas = fotos_guardadas(), 0
    for numero, p in enumerate(PERSONAGENS, 1):
        foto = guardadas.get(p["chave"], {})
        if p not in lista or foto.get("mandada_em") or not os.path.exists(foto.get("arquivo") or ""):
            continue
        if avisar_rafael.mandar_foto(foto["arquivo"], legenda_do_personagem(p, numero, len(PERSONAGENS))):
            marcar_foto(p["chave"], mandada_em=agora())
            mandadas += 1
            print(f"Personagens: a foto de {p['chave']} foi ao privado")
        else:
            print(f"Personagens: a foto de {p['chave']} não chegou ao privado; vai na próxima vez")
            codigo = 1
    print(f"Personagens: {mandadas} foto(s) no privado")
    return codigo


def _fotos_no_celular(lista):
    """As fotos no celular, com a trava na mão: a tela, o projeto do robô e uma imagem por personagem. 0 ou 1."""
    if celular_robo.tela_acesa() is False:
        ps.conectar(celular=True).screen_on()
        time.sleep(2)
    if celular_robo.tela_acesa() is False or celular_robo.tela_de_bloqueio():
        print("celular: a tela está apagada ou na tela de bloqueio; nada foi tocado")
        return 1
    d = ps.conectar(celular=True)
    os.makedirs(PASTA_DOS_PERSONAGENS, exist_ok=True)
    try:
        # A imagem não gasta crédito: o saldo não é lido.
        if abrir_o_projeto(d):
            print(f"Flow: o projeto {PROJETO_DO_ROBO} não estava na lista; criado com esse nome e aberto")
        for p in lista:
            local = os.path.join(PASTA_DOS_PERSONAGENS, f"{p['chave']}.jpg")
            gerar_a_imagem(d, pedido_do_personagem(p), local)
            # A foto nova ainda não foi vista: vai ao privado de novo e só vale com um OK novo (P259 1).
            marcar_foto(p["chave"], arquivo=local, feita_em=agora(), mandada_em="", aprovada_em="")
            print(f"Personagens: a foto de {p['chave']} foi feita ({os.path.getsize(local) // 1024} KB)")
    except Parada as e:
        casos_robo.guardar(d, "flow", "parou", str(e), passo="flow imagem")
        print(f"Personagens: parou: {e}")
        return 1
    return 0


# --- A imagem de teste do personagem com o produto (P253 1) ---
# A 1ª imagem do vídeo de IA com um personagem (P253 1): a IA escolhe pelo produto qual dos personagens combina mais com
# ele e diz, em inglês, o que a pessoa faz com o produto e onde; o modo Imagem do Flow (sem crédito) faz a imagem a
# partir de uma foto de referência só (com duas marcadas no seletor, só a 1ª entrou no pedido, visto em 19/11/2026),
# e por isso o servidor junta as duas: o personagem à esquerda e o produto à direita, num fundo branco
# (foto_do_personagem_com_o_produto). A IA confere a imagem com a foto do anúncio e a do personagem, e a imagem vai
# só ao privado do Rafael, seguida da foto do anúncio com o link. Com o OK dele a ela (P260 1), o vídeo de IA do dia
# começa por uma imagem assim (imagem_da_producao, abaixo).
# Escolha do Rafael (P253 1): DECISOES.md, Shopee Vídeo.
ALTURA_DA_REFERENCIA = 1024
FOLGA_DA_REFERENCIA = 24
# O trecho do pedido da escolha do personagem em cada uso: na imagem de teste (P253 1), todos os personagens valem; no
# vídeo de IA da produção (P260 1), a lista já vem só com os do formato, e a comédia (P251 1) pede a situação engraçada.
TRECHO_DA_IMAGEM_DE_TESTE = ("Os de comédia também valem, e a graça é da situação, nunca do corpo, da aparência ou de "
                             "um grupo. ")
TRECHO_DA_COMEDIA = (
    "É um vídeo de comédia: a ação é o começo de uma situação engraçada, com o jeito do personagem diante do produto "
    "(por exemplo, olhando-o de lado, com cara de desconfiada), sempre com o produto inteiro e virado para a câmera; "
    "a graça é da situação, nunca do corpo, da aparência ou de um grupo. ")
PEDIDO_DO_PERSONAGEM_COM_O_PRODUTO = (
    "Você monta a primeira cena de um vídeo de venda da Shopee Vídeo: um dos personagens fixos com o produto da foto "
    "({nome}). Os personagens:\n{personagens}\n"
    "Escolha pela foto e pelo nome quem combina mais com o produto (quem compraria ou usaria). {trecho}Responda só "
    "com um JSON, sem mais nada: {{\"personagem\": \"a chave\", \"acao\": \"em inglês, começando por um verbo no "
    "gerúndio, o que a "
    "pessoa faz com o produto: segurando-o inteiro e virado para a câmera, ou vestindo ou usando, se for roupa, "
    "calçado ou acessório\", \"cena\": \"em inglês, o lugar, combinando com o produto e com o personagem\"}}"
)
PEDIDO_DA_IMAGEM_COM_O_PRODUTO = (
    "The reference image has two parts: the person on the left and the product on the right. Create one new "
    "realistic vertical photo, like a frame of a Brazilian content creator's smartphone video: the same person from "
    "the left side (same face, hair, skin tone and body; same clothes unless the product is something to wear) "
    "{acao}, {cena}, looking at the camera, natural "
    "soft light. The product must look exactly like on the right side: same shape, colors, materials, logos, text "
    "and proportions, whole and clearly visible. Only this one person and this one product, nobody else. No "
    "collage, no split screen, no white background, no text, no captions and no watermark."
)
PEDIDO_DA_CONFERENCIA_DA_IMAGEM = (
    "A 1ª imagem foi feita por IA para a primeira cena de um vídeo de venda. A 2ª é a foto do anúncio do produto e a "
    "3ª é a foto do personagem. Compare só o que se vê nas imagens. Responda só com um JSON, sem mais nada: "
    "{\"mesmo_produto\": true ou false (o produto da 1ª é o mesmo da 2ª: forma, cores, logotipo e letras), "
    "\"mesma_pessoa\": true ou false (a pessoa da 1ª é a mesma da 3ª: rosto, cabelo e tom de pele), "
    "\"diferencas\": \"em português, curto, o que mudou no produto ou na pessoa; vazio se nada\", "
    "\"defeitos\": \"em português, curto, defeitos visíveis, como mãos, dedos, rosto ou letras estranhas; vazio se "
    "nada\"}"
)
ROTULOS_DA_PESSOA = {True: "a pessoa é a mesma do personagem", False: "a pessoa mudou", None: "a pessoa sem resposta"}


def foto_do_personagem_com_o_produto(foto_do_personagem, foto_do_produto):
    """
    A foto de referência da imagem de teste (bytes JPEG): a do personagem à esquerda, na altura ALTURA_DA_REFERENCIA, e
    a do produto à direita, inteira, num quadrado da mesma altura, num fundo branco. None quando uma não é imagem.
    """
    from PIL import Image
    try:
        with Image.open(io.BytesIO(foto_do_personagem)) as pessoa, Image.open(io.BytesIO(foto_do_produto)) as produto:
            altura = ALTURA_DA_REFERENCIA
            pessoa = pessoa.convert("RGB")
            pessoa = pessoa.resize((max(1, round(pessoa.width * altura / pessoa.height)), altura))
            produto = produto.convert("RGB")
            escala = min(altura / produto.width, altura / produto.height)
            produto = produto.resize((max(1, round(produto.width * escala)), max(1, round(produto.height * escala))))
            tela = Image.new("RGB", (pessoa.width + FOLGA_DA_REFERENCIA + altura, altura), (255, 255, 255))
            tela.paste(pessoa, (0, 0))
            tela.paste(produto, (pessoa.width + FOLGA_DA_REFERENCIA + (altura - produto.width) // 2,
                                 (altura - produto.height) // 2))
            saida = io.BytesIO()
            tela.save(saida, "JPEG", quality=92)
            return saida.getvalue()
    except Exception:
        return None


def escolher_o_personagem(nome, foto, personagens, formato=None):
    """
    A escolha da IA para a imagem do personagem com o produto: {"personagem" (a chave, entre os personagens dados),
    "acao", "cena"}; None sem resposta ou com uma chave de fora. formato: None na imagem de teste (P253 1);
    ESTILO_DO_VENDEDOR ou ESTILO_DA_COMEDIA no vídeo de IA da produção (P260 1), com cada personagem da comédia
    descrito pela graça dele (GRACA_NA_COMEDIA).
    """
    comedia = formato == ESTILO_DA_COMEDIA
    trecho = TRECHO_DA_COMEDIA if comedia else TRECHO_DA_IMAGEM_DE_TESTE if formato is None else ""
    lista = "\n".join(f"- {p['chave']}: {p['nome']} "
                      f"({GRACA_NA_COMEDIA.get(p['chave'], p['resumo']) if comedia else p['resumo']})"
                      for p in personagens)
    try:
        texto = asyncio.run(api_gemini.gerar_texto_gemini(
            PEDIDO_DO_PERSONAGEM_COM_O_PRODUTO.format(nome=nome, personagens=lista, trecho=trecho),
            imagens=[(foto, "image/jpeg")]))
    except Exception:
        texto = None
    achado = re.search(r"\{.*\}", texto or "", re.S)
    try:
        dados = json.loads(achado.group(0)) if achado else None
    except ValueError:
        dados = None
    if not isinstance(dados, dict):
        return None
    escolha = {campo: " ".join(str(dados.get(campo) or "").split()) for campo in ("personagem", "acao", "cena")}
    if escolha["personagem"] not in {p["chave"] for p in personagens} or not escolha["acao"] or not escolha["cena"]:
        return None
    escolha["acao"], escolha["cena"] = escolha["acao"][:200].rstrip(" ,."), escolha["cena"][:120].rstrip(" ,.")
    return escolha


def conferir_a_imagem(imagem, foto, foto_do_personagem):
    """A conferência da IA da imagem de teste: {"mesmo", "pessoa", "diferencas", "defeitos"} (None: sem resposta)."""
    try:
        imagens = []
        for caminho in (imagem, foto, foto_do_personagem):
            with open(caminho, "rb") as arquivo:
                imagens.append((jpeg_sem_metadados(arquivo.read()), "image/jpeg"))
        texto = asyncio.run(api_gemini.gerar_texto_gemini(PEDIDO_DA_CONFERENCIA_DA_IMAGEM, imagens=imagens))
    except Exception:
        texto = None
    conferencia = ler_conferencia(texto)
    achado = re.search(r"\{.*\}", texto or "", re.S)
    try:
        pessoa = json.loads(achado.group(0)).get("mesma_pessoa") if achado else None
    except (ValueError, AttributeError):
        pessoa = None
    conferencia["pessoa"] = pessoa if isinstance(pessoa, bool) else None
    return conferencia


def imagem_de_teste_guardada():
    """A imagem de teste de agora (o personagem, o produto, o pedido e a imagem), do banco; {} sem nenhuma."""
    return dict((db.ler_config(CHAVE, {}) or {}).get("imagem_de_teste") or {})


def marcar_imagem_de_teste(**campos):
    db.atualizar_config(CHAVE, lambda dados: dados.setdefault("imagem_de_teste", {}).update(campos))


def legenda_da_imagem_de_teste(atual, conferencia):
    """O texto que vai com a imagem de teste no privado do Rafael (até 1000 letras)."""
    p = personagem(atual["personagem"]) or {"nome": atual["personagem"], "resumo": ""}
    linhas = [f"🧪 Imagem de teste nº {atual.get('numero', 1)} do vídeo de IA (P253 1)",
              f"👤 {p['nome']} com {atual.get('nome') or 'o produto'}",
              "Feita no modo Imagem do Flow, sem gastar crédito, a partir da foto do personagem e da foto do anúncio.",
              f"🔎 Conferência da IA: {ROTULOS_DA_CONFERENCIA[conferencia['mesmo']]}; "
              f"{ROTULOS_DA_PESSOA[conferencia['pessoa']]}"]
    if conferencia["diferencas"]:
        linhas.append(f"O que mudou: {conferencia['diferencas']}")
    if conferencia["defeitos"]:
        linhas.append(f"Defeitos: {conferencia['defeitos']}")
    linhas.append("Nada foi postado: é só um teste.")
    return "\n".join(linhas)[:1000]


def imagem_de_teste():
    """
    A imagem de teste da P253 1, só no privado do Rafael: o produto da última amostra (que ele já viu em vídeo), o
    personagem que a IA escolhe entre os que têm foto, a foto de referência dos dois e a imagem no modo Imagem do Flow,
    sem crédito. A feita e não mandada vai sem gerar outra. 0 deu certo, 1 parou. Só rótulos, chaves e números no log.
    """
    atual = imagem_de_teste_guardada()
    if atual.get("estado") == "feita" and os.path.exists(atual.get("arquivo") or ""):
        print(f"Imagem de teste nº {atual.get('numero', 1)}: já feita; falta mandar")
        return mandar_a_imagem_de_teste()
    produto = amostra_guardada()
    if not (produto.get("nome") and produto.get("link")):
        print("Imagem de teste: sem a amostra de antes para pegar o produto; nada foi tocado")
        return 1
    guardadas = fotos_guardadas()
    com_foto = [p for p in PERSONAGENS if os.path.exists(guardadas.get(p["chave"], {}).get("arquivo") or "")]
    if not com_foto:
        print("Imagem de teste: sem as fotos dos personagens (video_ia.yml personagens); nada foi tocado")
        return 1
    with open(produto["foto"], "rb") as arquivo:
        foto_do_produto = jpeg_sem_metadados(arquivo.read())
    escolha = escolher_o_personagem(produto["nome"], foto_do_produto, com_foto) if foto_do_produto else None
    if not escolha:
        print("Imagem de teste: a IA não escolheu o personagem; nada foi tocado")
        return 1
    with open(guardadas[escolha["personagem"]]["arquivo"], "rb") as arquivo:
        referencia = foto_do_personagem_com_o_produto(arquivo.read(), foto_do_produto)
    if not referencia:
        print("Imagem de teste: a foto de referência não saiu; nada foi tocado")
        return 1
    os.makedirs(PASTA, exist_ok=True)
    caminho = os.path.join(PASTA, "imagem_de_teste_referencia.jpg")
    with open(caminho, "wb") as arquivo:
        arquivo.write(referencia)
    atual = {"numero": int(atual.get("numero") or 0) + 1, "personagem": escolha["personagem"],
             "link": produto["link"], "nome": produto["nome"], "foto": produto["foto"], "referencia": caminho,
             "prompt": PEDIDO_DA_IMAGEM_COM_O_PRODUTO.format(acao=escolha["acao"], cena=escolha["cena"]),
             "estado": "escolhido", "criado_em": agora()}
    guardar(imagem_de_teste=atual)
    print(f"Imagem de teste nº {atual['numero']}: personagem {atual['personagem']}; "
          f"pedido com {len(atual['prompt'].split())} palavras")
    if not celular_robo.conectado():
        print("celular: desconectado; conecte pelo bot (Shopee Vídeo 🎬 → Celular do Robô 📱)")
        return 1
    tentativas = ps.ESPERA_DO_CELULAR // ps.PAUSA_DA_ESPERA + 1
    for tentativa in range(tentativas):
        with celular_robo.trava() as livre:
            if livre:
                codigo = _imagem_de_teste_no_celular(atual)
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
    return mandar_a_imagem_de_teste() if codigo == 0 else codigo


def _imagem_de_teste_no_celular(atual):
    """A imagem de teste no celular, com a trava na mão: a foto de referência na galeria, o projeto e a imagem. 0/1."""
    if celular_robo.tela_acesa() is False:
        ps.conectar(celular=True).screen_on()
        time.sleep(2)
    if celular_robo.tela_acesa() is False or celular_robo.tela_de_bloqueio():
        print("celular: a tela está apagada ou na tela de bloqueio; nada foi tocado")
        return 1
    d = ps.conectar(celular=True)
    nome_na_galeria = foto_na_galeria(d, atual["referencia"], "_referencia")
    if not nome_na_galeria:
        print("Imagem de teste: a foto de referência não apareceu na galeria do celular")
        return 1
    local = os.path.join(PASTA, "imagem_de_teste.jpg")
    try:
        if abrir_o_projeto(d):
            print(f"Flow: o projeto {PROJETO_DO_ROBO} não estava na lista; criado com esse nome e aberto")
        gerar_a_imagem(d, atual["prompt"], local, com_foto=True)
    except Parada as e:
        casos_robo.guardar(d, "flow", "parou", str(e), passo="flow imagem de teste")
        print(f"Imagem de teste: parou: {e}")
        return 1
    finally:
        tirar_da_galeria(d, nome_na_galeria)
    marcar_imagem_de_teste(arquivo=local, estado="feita", feita_em=agora())
    print(f"Imagem de teste nº {atual['numero']}: feita ({os.path.getsize(local) // 1024} KB)")
    return 0


def mandar_a_imagem_de_teste():
    """
    Confere a imagem de teste pela IA e a manda ao privado do Rafael (sem o celular), e logo depois a foto do anúncio
    com o link dele. 0 mandada, 1 não.
    """
    atual = imagem_de_teste_guardada()
    foto_do_personagem = fotos_guardadas().get(atual.get("personagem"), {}).get("arquivo") or ""
    if atual.get("estado") != "feita" or not os.path.exists(atual.get("arquivo") or ""):
        print("Imagem de teste: a imagem não está no servidor")
        return 1
    conferencia = conferir_a_imagem(atual["arquivo"], atual["foto"], foto_do_personagem)
    print(f"Imagem de teste: conferência da IA: {ROTULOS_DA_CONFERENCIA[conferencia['mesmo']]}; "
          f"{ROTULOS_DA_PESSOA[conferencia['pessoa']]}")
    try:
        ok = avisar_rafael.mandar_foto(atual["arquivo"], legenda_da_imagem_de_teste(atual, conferencia))
    except Exception:
        ok = False
    if not ok:
        print("Imagem de teste: a imagem não chegou ao privado; vai na próxima vez, sem gerar outra")
        return 1
    marcar_imagem_de_teste(estado="enviada", mandada_em=agora(), mesmo_produto=conferencia["mesmo"],
                           mesma_pessoa=conferencia["pessoa"])
    print(f"Imagem de teste nº {atual.get('numero', 1)}: mandada no privado do Rafael")
    try:
        foto = avisar_rafael.mandar_foto(atual["foto"], (
            f"🖼️ Foto do anúncio, para comparar com a imagem de teste nº {atual.get('numero', 1)}\n"
            f"🔗 Anúncio: {link_do_anuncio(atual.get('link', ''))}")[:1000])
    except Exception:
        foto = False
    print("Imagem de teste: foto e link do anúncio mandados" if foto
          else "Imagem de teste: a foto do anúncio não foi ao privado")
    return 0


# --- A imagem do personagem com o produto no vídeo de IA da produção (P260 1) ---
# Com o OK do Rafael à imagem de teste (P260 1), o vídeo de IA do dia e o De IA ✨ começam por uma imagem como a de
# teste (P253 1): antes do Gerar do vídeo de 16 s do vendedor ou da comédia, com o celular na mão, a IA escolhe pelo
# produto o personagem, só entre os de foto aprovada (P259 1) e do formato (elenco_do_formato), e o que ele faz com o
# produto; o modo Imagem do Flow faz a imagem, sem crédito, pela foto de referência dos dois, e a IA a confere com a
# foto do anúncio e a do personagem: vale com o mesmo produto e a mesma pessoa; sem isso, o robô a refaz uma vez
# (TENTATIVAS_DA_IMAGEM). Valendo, a IA escreve o pedido do vídeo pela imagem (pedido_pela_imagem), e o Flow anima a
# imagem nos 16 s da P247 1, com as regras contra as alucinações da P248 1. Sem a imagem (nenhuma valeu, o Flow
# parou, a IA não respondeu), o vídeo sai pela foto do anúncio, como antes, e o porquê vai na legenda. O saldo do Flow
# é lido antes da imagem: sem os créditos do vídeo, nem ela é feita. O unboxing (P256 2) não tem rosto e sai como
# antes, e a conferência do vídeo pronto continua sendo com a foto do anúncio. Escolhas do Rafael (P253 1, P250 1,
# P258 1, P251 1, P259 1 e P260 1): DECISOES.md, Shopee Vídeo.
TENTATIVAS_DA_IMAGEM = 2
SEM_FOTO_APROVADA = "nenhuma foto de personagem aprovada para este formato"
# O começo do pedido do vídeo pela imagem: a 1ª imagem é o 1º quadro (o que o Flow anima), e a foto do anúncio vai
# junto, para o produto ficar idêntico. Os cuidados contra as alucinações são os do PEDIDO_DO_VENDEDOR (P248 1).
_COMECO_PELA_IMAGEM = (
    "Você é diretor de vídeos curtos de produto para a Shopee Vídeo, no Brasil, e escreve como os vídeos que mais "
    "vendem no feed. A 1ª imagem é o primeiro quadro do vídeo: {quem}, já com o produto \"{nome}\". A 2ª é a foto "
    "oficial do anúncio, para o produto ficar idêntico a ela. O Google Flow vai animar a 1ª imagem num vídeo de 16 "
    "segundos, em pé (9:16) e com som, em duas partes de 8 segundos: a 1ª a partir da imagem e a 2ª continuando a "
    "1ª, na mesma cena, com a mesma pessoa e a mesma voz. A IA de vídeo inventa coisas quando a cena pede demais; por "
    "isso, nas duas partes: a pessoa só segura o produto (ou fica com ele no corpo, se na imagem o veste ou usa), "
    "vira devagar e aponta para ele, sem abrir, fechar, desmontar, encaixar, despejar, cozinhar, vestir, tirar ou "
    "trocar o produto de mão, e nada muda de estado; os 16 segundos ficam no lugar da imagem, com o mesmo fundo, o "
    "mesmo enquadramento e a câmera parada, sem corte, sem ir a outro lugar e sem aparecer comida, objeto ou pessoa "
    "nova. Responda só com um JSON, sem nada antes ou depois:\n"
    '{{"prompt": "...", "continuacao": "...", "fala": "...", "cena": "..."}}\n'
)
# O vendedor de 16 s pela imagem fala do começo ao fim de cada parte (P262): o "terminando antes dos 6 segundos;
# depois, calada" deixava o silêncio no meio que o Rafael viu nos vídeos de IA.
PEDIDO_DO_VENDEDOR_PELA_IMAGEM = _COMECO_PELA_IMAGEM + (
    "- prompt: em inglês, até 90 palavras, os 8 primeiros segundos, a partir da imagem: a pessoa da imagem olha para "
    "a câmera, com o produto como na imagem, idêntico ao da foto do anúncio (mesma forma, cor, material, tamanho, "
    f"quantidade e detalhes; nada acrescentado, tirado ou trocado) e bem à vista, e {_FALA_DA_1A_PARTE} "
    "Fotorrealista, com a luz da imagem e a câmera parada.\n"
) + _CONTINUACAO_FALANDO + _FIM_DO_VENDEDOR
# O vendedor de 8 s pela imagem (P262): um Gerar só, com a fala do começo ao fim.
_COMECO_PELA_IMAGEM_CURTO = (
    "Você é diretor de vídeos curtos de produto para a Shopee Vídeo, no Brasil, e escreve como os vídeos que mais "
    "vendem no feed. A 1ª imagem é o primeiro quadro do vídeo: {quem}, já com o produto \"{nome}\". A 2ª é a foto "
    "oficial do anúncio, para o produto ficar idêntico a ela. O Google Flow vai animar a 1ª imagem num vídeo de 8 "
    "segundos, em pé (9:16) e com som. A IA de vídeo inventa coisas quando a cena pede demais; por isso, a pessoa só "
    "segura o produto (ou fica com ele no corpo, se na imagem o veste ou usa), vira devagar e aponta para ele, sem "
    "abrir, fechar, desmontar, encaixar, despejar, cozinhar, vestir, tirar ou trocar o produto de mão, e nada muda de "
    "estado; os 8 segundos ficam no lugar da imagem, com o mesmo fundo, o mesmo enquadramento e a câmera parada, sem "
    "corte, sem ir a outro lugar e sem aparecer comida, objeto ou pessoa nova. Responda só com um JSON, sem nada "
    "antes ou depois:\n"
    '{{"prompt": "...", "fala": "...", "cena": "..."}}\n'
)
PEDIDO_DO_VENDEDOR_PELA_IMAGEM_CURTO = _COMECO_PELA_IMAGEM_CURTO + (
    "- prompt: em inglês, até 90 palavras, os 8 segundos, a partir da imagem: a pessoa da imagem olha para a câmera, "
    "com o produto como na imagem, idêntico ao da foto do anúncio (mesma forma, cor, material, tamanho, quantidade e "
    f"detalhes; nada acrescentado, tirado ou trocado) e bem à vista, e {_FALA_DO_CURTO} Fotorrealista, com a luz da "
    "imagem e a câmera parada.\n"
) + _FIM_DO_CURTO
# A comédia de 16 s (P251 1): na 1ª parte, a situação engraçada, com a graça vinda do jeito do personagem diante do
# produto e da fala, só com movimentos pequenos; na 2ª, o mesmo personagem, convencido, mostrando o produto e vendendo.
PEDIDO_DA_COMEDIA_PELA_IMAGEM = _COMECO_PELA_IMAGEM + (
    "- prompt: em inglês, até 90 palavras, os 8 primeiros segundos, a partir da imagem: uma situação engraçada do dia "
    "a dia com o produto à vista o tempo todo, idêntico ao da foto do anúncio (mesma forma, cor, material, tamanho, "
    "quantidade e detalhes; nada acrescentado, tirado ou trocado). A graça vem do jeito do personagem diante do "
    "produto (a cara, a reação) e de uma fala engraçada logo no começo, entre aspas, em português do Brasil, até "
    f"{PALAVRAS_POR_PARTE} palavras, terminando antes dos 6 segundos (por exemplo, a desconfiada olha o copo de "
    "sobrancelha levantada e diz: \"Gelo o dia todo? Duvido!\"); só movimentos pequenos (a cara, um gesto, virar o "
    "produto), sem cair, derrubar, correr, pular ou mexer em outra coisa. Fotorrealista, com a luz da imagem e a "
    "câmera parada.\n"
    "- continuacao: em inglês, até 90 palavras, os 8 segundos seguintes, continuando o mesmo plano sem corte, no "
    "mesmo lugar e enquadramento, com a mesma pessoa, a mesma roupa e o mesmo produto, idêntico: agora convencido, o "
    "personagem aponta e mostra de perto uma vantagem que se vê no produto, só virando-o ou aproximando-o da câmera, "
    f"e fala logo no começo, entre aspas, em português do Brasil, até {PALAVRAS_POR_PARTE} palavras, a vantagem e "
    "uma chamada curta para comprar (por exemplo: \"Nada gruda e limpa fácil. Garanta a sua!\"), terminando antes "
    "dos 6 segundos.\n"
) + _FIM_DO_VENDEDOR


def pede_a_imagem(atual):
    """
    O andamento pede a imagem do personagem antes do Gerar (P260 1)? O de 16 s do vendedor ou da comédia e o de 8 s
    do vendedor (P262), antes do Gerar e sem a imagem tentada; o unboxing e o mãos e voz (sem rosto), a propaganda de
    TV (P269 3, pela foto do anúncio, sem ninguém falando para a câmera) e o andamento sem o formato (de antes dela),
    não.
    """
    return bool((atual.get("longa") or atual.get("curta")) and atual.get("estado") == "escolhido"
                and not atual.get("imagem") and atual.get("formato") in (ESTILO_DO_VENDEDOR, ESTILO_DA_COMEDIA))


def elenco_do_formato(formato, aprovadas=None):
    """
    Os personagens que podem estar no vídeo de IA do formato, só os de foto aprovada (P259 1): na comédia, os
    PERSONAGENS_DA_COMEDIA; no vendedor, os que não são só da comédia (SO_NA_COMEDIA).
    """
    aprovadas = fotos_aprovadas() if aprovadas is None else aprovadas
    if formato == ESTILO_DA_COMEDIA:
        return [p for p in PERSONAGENS if p["chave"] in aprovadas and p["chave"] in PERSONAGENS_DA_COMEDIA]
    return [p for p in PERSONAGENS if p["chave"] in aprovadas and p["chave"] not in SO_NA_COMEDIA]


def pedido_pela_imagem(nome, imagem, foto, chave, comedia=False, curto=False):
    """
    O pedido do vídeo de 16 s pela imagem do personagem com o produto (P260 1), com a foto do anúncio junto: {"estilo",
    "prompt", "continuacao", "fala", "cena"}, no vendedor ou na comédia (P251 1); None sem a resposta da IA ou sem uma
    das partes (o prompt, a continuação ou a fala). curto: o de 8 s do vendedor (P262), sem a continuação.
    """
    p = personagem(chave) or {"nome": chave, "resumo": ""}
    descricao = GRACA_NA_COMEDIA.get(chave, p["resumo"]) if comedia else p["resumo"]
    imagens = []
    for caminho in (imagem, foto):
        try:
            with open(caminho, "rb") as arquivo:
                dados = jpeg_sem_metadados(arquivo.read())
        except OSError:
            dados = None
        if not dados:
            return None
        imagens.append((dados, "image/jpeg"))
    pedido = (PEDIDO_DA_COMEDIA_PELA_IMAGEM if comedia else PEDIDO_DO_VENDEDOR_PELA_IMAGEM_CURTO if curto
              else PEDIDO_DO_VENDEDOR_PELA_IMAGEM)
    try:
        texto = asyncio.run(api_gemini.gerar_texto_gemini(
            pedido.format(nome=nome, quem=f"o personagem {p['nome']} ({descricao})"), imagens=imagens))
    except Exception:
        texto = None
    achado = re.search(r"\{.*\}", texto or "", re.S)
    try:
        resposta = json.loads(achado.group(0)) if achado else None
    except ValueError:
        resposta = None
    if not isinstance(resposta, dict):
        return None
    partes = {campo: " ".join(str(resposta.get(campo) or "").split())
              for campo in ("prompt", "continuacao", "fala", "cena")}
    if not (partes["prompt"] and (curto or partes["continuacao"]) and partes["fala"]):
        return None
    escrito = {"estilo": ESTILO_DA_COMEDIA if comedia else ESTILO_DO_VENDEDOR, "prompt": com_a_diccao(partes["prompt"]),
               "fala": partes["fala"][:400], "cena": partes["cena"][:300]}
    if not curto:
        escrito["continuacao"] = com_a_diccao(partes["continuacao"])
    return escrito


def _sem_a_imagem(motivo, chave="", conferencia=None):
    """
    A imagem do personagem não vale desta vez: o vídeo sai pela foto do anúncio, como antes (P253 1), com o porquê no
    andamento (no log, só o texto fixo do código). Devolve o andamento.
    """
    guardar_producao(imagem={"estado": "sem", "motivo": motivo, "personagem": chave, "em": agora(),
                             **({"conferencia": conferencia} if conferencia else {})})
    print(f"Vídeo de IA: sem a imagem do personagem ({motivo}); o vídeo sai pela foto do anúncio")
    return producao()


def imagem_da_producao(d, atual):
    """
    A imagem do personagem com o produto antes do Gerar do vídeo (P260 1; o de 8 s também, P262), com a trava do
    celular na mão: a escolha do personagem pela IA, a foto de referência na galeria, o saldo do Flow (SemCreditos sem
    os créditos do vídeo: nem a imagem é feita), a imagem no modo Imagem, sem crédito, e a conferência da IA, refeita
    uma vez; valendo, o pedido do vídeo pela imagem ("foto_do_video", "personagem" e o pedido novo no andamento). Sem
    ela, o porquê fica no andamento e o vídeo sai pela foto do anúncio (a parada no Flow fica nos casos). Devolve o
    andamento.
    """
    formato = atual.get("formato")
    aprovadas = fotos_aprovadas()
    elenco = elenco_do_formato(formato, aprovadas)
    if not elenco:
        return _sem_a_imagem(SEM_FOTO_APROVADA)
    try:
        with open(atual["foto"], "rb") as arquivo:
            foto = jpeg_sem_metadados(arquivo.read())
    except OSError:
        foto = None
    escolha = escolher_o_personagem(atual.get("nome", ""), foto, elenco, formato) if foto else None
    if not escolha:
        return _sem_a_imagem("a IA não escolheu o personagem")
    chave = escolha["personagem"]
    try:
        with open(aprovadas[chave], "rb") as arquivo:
            referencia = foto_do_personagem_com_o_produto(arquivo.read(), foto)
    except OSError:
        referencia = None
    if not referencia:
        return _sem_a_imagem("a foto de referência não saiu", chave)
    os.makedirs(PASTA, exist_ok=True)
    caminho = os.path.join(PASTA, f"producao_{atual['data']}_referencia.jpg")
    with open(caminho, "wb") as arquivo:
        arquivo.write(referencia)
    imagem = os.path.join(PASTA, f"producao_{atual['data']}_imagem.jpg")
    prompt = PEDIDO_DA_IMAGEM_COM_O_PRODUTO.format(acao=escolha["acao"], cena=escolha["cena"])
    print(f"Vídeo de IA: personagem {chave}; a imagem com o produto antes do vídeo")
    nome_na_galeria = foto_na_galeria(d, caminho, "_referencia")
    if not nome_na_galeria:
        return _sem_a_imagem("a foto de referência não apareceu na galeria do celular", chave)
    conferencia, feitas, vale = None, 0, False
    try:
        # O saldo antes da imagem: sem os créditos do vídeo (o de 8 s da P262, sem o Estender), nem ela é feita (o
        # SemCreditos sobe ao robô).
        if abrir_o_projeto(d, saldo_minimo=atual["custo"] + (CUSTO_DO_ESTENDER if atual.get("longa") else 0)):
            print(f"Flow: o projeto {PROJETO_DO_ROBO} não estava na lista; criado com esse nome e aberto")
        while feitas < TENTATIVAS_DA_IMAGEM and not vale:
            feitas += 1
            gerar_a_imagem(d, prompt, imagem, com_foto=True)
            conferencia = conferir_a_imagem(imagem, atual["foto"], aprovadas[chave])
            vale = conferencia["mesmo"] is True and conferencia["pessoa"] is True
            print(f"Vídeo de IA: imagem {feitas} feita; a IA conferiu: {ROTULOS_DA_CONFERENCIA[conferencia['mesmo']]}"
                  f"; {ROTULOS_DA_PESSOA[conferencia['pessoa']]}")
    except SemCreditos:
        raise
    except Parada as e:
        casos_robo.guardar(d, "video de IA", "parou", f"imagem do personagem: {e}", passo="flow imagem")
        return _sem_a_imagem(f"o Flow parou na imagem: {e}", chave, conferencia)
    finally:
        tirar_da_galeria(d, nome_na_galeria)
    if not vale:
        return _sem_a_imagem(f"a IA não confirmou o produto e a pessoa em {feitas} imagens", chave, conferencia)
    pedido = pedido_pela_imagem(atual.get("nome", ""), imagem, atual["foto"], chave, formato == ESTILO_DA_COMEDIA,
                                curto=bool(atual.get("curta")))
    if not pedido:
        return _sem_a_imagem("a IA não escreveu o pedido do vídeo pela imagem", chave, conferencia)
    guardar_producao(foto_do_video=imagem, personagem=chave, **pedido,
                     imagem={"estado": "feita", "personagem": chave, "tentativas": feitas, "conferencia": conferencia,
                             "em": agora()})
    print(f"Vídeo de IA: a imagem vale ({feitas} imagem(ns)); o vídeo sai dela")
    return producao()


def linha_do_personagem(atual):
    """
    A linha do personagem no aviso e no rascunho do vídeo de IA (P260 1): quem está no vídeo ou por que ele saiu sem
    personagem; "" sem a imagem tentada.
    """
    imagem = atual.get("imagem") or {}
    if imagem.get("estado") == "feita":
        p = personagem(imagem.get("personagem")) or {"nome": imagem.get("personagem") or "?"}
        return (f"👤 Personagem: {p['nome']} (o vídeo saiu da imagem do personagem com o produto, feita no modo Imagem "
                "do Flow, sem crédito)")
    if imagem.get("estado") == "sem":
        comedia = "; a comédia fica para outro vídeo" if atual.get("formato") == ESTILO_DA_COMEDIA else ""
        return (f"👤 Sem personagem desta vez ({imagem.get('motivo') or 'sem detalhes'}): o vídeo saiu pela foto do "
                f"anúncio, como antes{comedia}")
    return ""


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
    propaganda = atual.get("formato") == ESTILO_DA_PROPAGANDA
    if propaganda:
        linhas = [f"🎬 Amostra nº {atual.get('numero', 1)} do vídeo de IA de 8 s com cara de propaganda de TV "
                  "(P268 1)",
                  f"🤖 Modelo: {atual.get('modelo', '')} ({custo} créditos de IA)",
                  f"📦 Produto: {atual.get('nome', '')}", paga,
                  f"🎙️ Locutor: {atual.get('fala', '')}",
                  f"🔎 A IA conferiu: {conferido}"]
        if fala_ouvida:
            linhas.append(texto_da_fala(fala_ouvida))
        if com_fala is not None:
            linhas.append(f"⏱️ Com fala: {_segundos(com_fala)} dos {_segundos(atual.get('duracao') or 0)} do vídeo")
    elif atual.get("longa"):
        if atual.get("formato") == ESTILO_DAS_MAOS_E_VOZ:
            jeito = "no formato mãos e voz (P261 1: só as mãos usando o produto, com uma voz contando)"
            de_novo = f", com o mesmo produto da nº {atual['mesmo_de']}" if atual.get("mesmo_de") else ""
        elif atual.get("fala_inteira"):
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
        elif com_fala is not None:
            linhas.append(f"⏱️ Com fala: {_segundos(com_fala)} dos {_segundos(atual.get('duracao') or 0)} do vídeo")
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
    if propaganda:
        # A amostra da propaganda de TV (P268 1) é só para ver; desde a P269 3, a propaganda é o formato de todo
        # vídeo de IA do robô.
        linhas.append("Nada foi postado: é só para você ver como fica a propaganda de TV, que é, desde a P269 3, o "
                      "formato de todo vídeo de IA do robô.")
        linhas.append(f"🎥 Cena: {atual.get('cena', '')}")
    elif atual.get("longa") and atual.get("formato") == ESTILO_DAS_MAOS_E_VOZ:
        # Desde a P262, o formato mãos e voz já está entre os do vídeo de IA do dia (P261 1): a amostra é só para ver.
        linhas.append("Nada foi postado: o formato mãos e voz já sai no vídeo de IA do dia e no De IA ✨, escolhido "
                      "pela IA quando combina com o produto, em 8 ou 16 s (P262).")
        linhas.append(f"🎥 Cena: {atual.get('cena', '')}")
    elif atual.get("fala_inteira"):
        # Desde a P262, o vídeo de IA de 16 s do dia já fala do começo ao fim de cada parte (P255 1).
        linhas.append("Nada foi postado: o vídeo de IA de 16 s do dia já fala do começo ao fim e tem o silêncio "
                      "cortado (P262).")
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
    # A fala do vídeo de 16 s e a do locutor da propaganda de TV (P268 1) conferidas pelo servidor (P248 1): a
    # embolada ou cortada vai na legenda.
    com_a_fala = (atual.get("longa") or atual.get("formato") == ESTILO_DA_PROPAGANDA) and atual.get("fala")
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
    elif atual.get("formato") in (ESTILO_DAS_MAOS_E_VOZ, ESTILO_DA_PROPAGANDA) and ouvidas is not None:
        # A voz do começo ao fim do formato mãos e voz (P261 1) e o locutor da propaganda de TV (P268 1), medidos
        # como na P255 1, sem o corte do parado.
        duracao = videos.duracao(atual["arquivo"])
        if duracao:
            com_fala = tempo_com_fala(ouvidas, duracao)
            print(f"Amostra: tempo com fala: {com_fala} s de {round(duracao, 1)} s")
            marcar_amostra(com_fala=com_fala)
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


def _pedido_do_mesmo_produto(anterior, longa, fala_inteira=False, maos_e_voz=False):
    """
    O pedido novo da IA para o produto da amostra anterior (o link, o nome e a foto dela), com as regras de agora: a
    amostra de 16 s de novo com o mesmo produto, para o Rafael comparar (P248 1); fala_inteira: com a fala do começo
    ao fim (P255 1); maos_e_voz: no formato mãos e voz (P261 1). None sem a amostra anterior ou sem o pedido da IA.
    """
    if not (anterior.get("link") and anterior.get("nome") and anterior.get("item")):
        return None
    try:
        with open(anterior["foto"], "rb") as arquivo:
            foto = arquivo.read()
    except (KeyError, OSError):
        return None
    escolhido, _serve = pedido_para_o_anuncio(anterior["link"], anterior["nome"], foto, longo=longa,
                                              fala_inteira=fala_inteira, maos_e_voz=maos_e_voz)
    if not escolhido:
        return None
    return dict(escolhido, item=anterior["item"], valor=anterior.get("valor"), origem=anterior.get("origem"))


def amostra(sem_gerar=False, longa=False, mesmo=False, fala_inteira=False, maos_e_voz=False, tv=False):
    """
    A próxima amostra do vídeo de IA (P236 1): escolhe o produto como a produção, gera no MODELO_DA_PRODUCAO, baixa
    e manda no privado do Rafael. A que já foi gerada só é baixada e mandada (nunca dois Gerar para a mesma amostra).
    sem_gerar: tudo até o Gerar, sem tocar nele. longa: a amostra do vídeo de 16 s com uma pessoa vendendo o produto
    (P246 1), com o Estender; a que ficou pela metade continua do jeito dela. mesmo: com o produto da amostra
    anterior e um pedido novo da IA (P248 1). fala_inteira (só com longa): a de 16 s com a fala do começo ao fim de
    cada parte e o corte do parado (P255 1). maos_e_voz (só com longa, sem fala_inteira): a de 16 s no formato mãos e
    voz (P261 1). tv (sem longa e sem mesmo): a de 8 s com cara de propaganda de TV, com o locutor em off (P268 1).
    0 deu certo, 1 parou. Só rótulos fixos e números no log.
    """
    fala_inteira = fala_inteira and longa
    maos_e_voz = maos_e_voz and longa and not fala_inteira
    tv = tv and not (longa or mesmo)
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
            escolhido, origem = _pedido_do_mesmo_produto(atual, longa, fala_inteira, maos_e_voz), ""
            if not escolhido:
                print("Amostra: sem a amostra anterior ou sem o pedido novo da IA para o mesmo produto; "
                      "nada foi tocado")
                return 1
        else:
            # Só aqui: o robô importa este módulo, e a escolha é a dele (P234 1).
            import robo_shopee_video as robo
            try:
                escolhido, origem, _restam = robo.escolher_para_o_video_de_ia(fora=amostras_feitas(), amostra=True,
                                                                              longo=longa, fala_inteira=fala_inteira,
                                                                              maos_e_voz=maos_e_voz,
                                                                              **({"propaganda": True} if tv else {}))
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
            if maos_e_voz:
                atual.update(formato=ESTILO_DAS_MAOS_E_VOZ)
            guardar(amostra=atual)
        elif tv:
            # A propaganda de TV (P268 1) tem um jeito só, como a de 16 s, e fica fora da variação dos estilos.
            atual.update(formato=ESTILO_DA_PROPAGANDA, fala=escolhido.get("fala", ""))
            guardar(amostra=atual)
        else:
            guardar(amostra=atual, estilos=(estilos_recentes() + [escolhido["estilo"]])[-ESTILOS_LEMBRADOS:])
        escolha = (f"o mesmo produto da amostra nº {numero_anterior}" if mesmo
                   else f"produto escolhido (o {escolhido.get('posicao')}º de {origem})")
        print(f"Amostra nº {atual['numero']}: {escolha}; "
              f"estilo {escolhido['estilo']}; pedido da IA com {len(escolhido['prompt'].split())} palavras"
              + (f" e a continuação com {len(atual['continuacao'].split())}" if longa else "")
              + ("; com a fala do começo ao fim (P255 1)" if fala_inteira else "")
              + ("; no formato mãos e voz (P261 1)" if maos_e_voz else "")
              + ("; com cara de propaganda de TV (P268 1)" if tv else ""))
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
    if argumentos == ["imagem-teste"]:
        logging.disable(logging.CRITICAL)
        try:
            return imagem_de_teste()
        except Exception as e:
            print(f"Flow: erro inesperado ({type(e).__name__})")
            return 1
        finally:
            logging.disable(logging.NOTSET)
    if argumentos and argumentos[0] in ("personagens", "aprovar-personagens"):
        # As chaves vêm do campo "quais" do video_ia.yml, separadas por vírgula ou espaço; vazio = as que faltam (no
        # aprovar, todas).
        chaves = [c for c in " ".join(argumentos[1:]).replace(",", " ").split() if c]
        logging.disable(logging.CRITICAL)
        try:
            if argumentos[0] == "aprovar-personagens":
                return aprovar_as_fotos(chaves or None)
            return fotos_dos_personagens(chaves or None)
        except Exception as e:
            print(f"Flow: erro inesperado ({type(e).__name__})")
            return 1
        finally:
            logging.disable(logging.NOTSET)
    opcoes = set(argumentos[1:])
    # O formato mãos e voz (P261 1) é só da amostra de 16 s e tem a voz dele: nem sem o --longa, nem com a fala inteira.
    # A propaganda de TV (P268 1) é a de 8 s, com o locutor dela: sozinha, só com o --sem-gerar.
    sem_jeito = (("--maos-e-voz" in opcoes and ("--longa" not in opcoes or "--fala-inteira" in opcoes))
                 or ("--tv" in opcoes and not opcoes <= {"--tv", "--sem-gerar"}))
    if argumentos and not sem_jeito and ((argumentos[0] == "teste" and opcoes <= {"--sem-gerar"})
                                         or (argumentos[0] == "amostra"
                                             and opcoes <= {"--sem-gerar", "--longa", "--mesmo", "--fala-inteira",
                                                            "--maos-e-voz", "--tv"})):
        # Os módulos logam nomes e links; aqui o log é público, e o resultado sai pelos prints.
        logging.disable(logging.CRITICAL)
        try:
            if argumentos[0] == "teste":
                return teste(sem_gerar="--sem-gerar" in opcoes)
            return amostra(sem_gerar="--sem-gerar" in opcoes, longa="--longa" in opcoes, mesmo="--mesmo" in opcoes,
                           fala_inteira="--fala-inteira" in opcoes, maos_e_voz="--maos-e-voz" in opcoes,
                           tv="--tv" in opcoes)
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

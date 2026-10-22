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

Cada rodada faz no máximo uma coisa, nesta ordem:
1. o treino da semana, na primeira rodada de segunda-feira: percorre o caminho até a tela
   final sem salvar nem postar e confere cada tela com o mapa (os CAMINHOs abaixo);
2. apaga no app um rascunho que o Rafael recusou;
3. posta um rascunho aprovado cuja hora chegou: os aprovados saem um de cada vez, com um
   intervalo sorteado entre eles, sempre dentro do Horário do Robô;
4. prepara um rascunho novo quando um horário do plano do dia passou: cada dia sorteia
   quantos (a faixa Rascunhos por Dia) e espalha os horários pelo Horário do Robô.
Pausado (Pausar Postagem ⏸️), fora do Horário do Robô, com o celular desconectado, com a
tela do celular aberta no privado do Rafael ou com o explorar tocando nele, não toca em
nada. Na Verificação da Shopee para na hora e manda o link da tela do celular no privado.

Nunca toca em Postar sem o Aprovar do Rafael no bot, nem nos botões de comprar. Curtir e
comentar o próprio vídeo continuam à mão (diretriz 9.1.1): depois de postar, o comentário
chega no privado, numa mensagem só dele. No log, só estados e números: nada de nome de
produto, título ou link.
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import asyncio
import json
import logging
import os
import random
import shutil
import sys
import time
from datetime import datetime, timedelta

import android_virtual as av
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
    """
    estado = estado_do_dia(config, agora)
    passados = horarios_vencidos(estado, agora)
    if passados <= estado["feitos"]:
        return False
    estado["feitos"] = passados
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


# --- Rascunhos (tabela shopee_video_rascunhos) ---

COLUNAS = ("id", "id_video", "criado_em", "estado", "arquivo", "print", "link", "produtos", "titulo",
           "comentario", "aprovado_em", "postar_em", "postado_em", "link_post", "motivo")


def _criar_tabela(con):
    con.execute("CREATE TABLE IF NOT EXISTS shopee_video_rascunhos ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, id_video TEXT, criado_em TEXT, estado TEXT, "
                "arquivo TEXT, print TEXT, link TEXT, produtos TEXT, titulo TEXT, comentario TEXT, "
                "aprovado_em TEXT, postar_em TEXT, postado_em TEXT, link_post TEXT, motivo TEXT)")


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
    A tarefa desta rodada: ("treino", None), ("apagar", id), ("postar", id),
    ("rascunho", None) ou None. Gasta o horário do plano quando escolhe um rascunho.
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
    if consumir_horarios(config, agora):
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
CAMINHO_POSTAR = [
    ("Postar vídeo", 8, "Biblioteca"),
    ("Biblioteca", 6, "@ll_check"),
    ("@ll_check", 3, "@tv_pick_top_next"),
    ("@tv_pick_top_next", 10, "@tv_compress"),
    ("@tv_compress", 10, "@et_caption"),
]
CAMINHO_PRODUTO = [
    ("@ll_add_product_symbol", 8, "Minhas Curtidas"),
    ("Minhas Curtidas", 5, "Mais Recente"),
    ("Mais Recente", 5, "Adicionar"),
]
# Botões de janelas que perguntam se o robô quer sair sem salvar o que está editando.
SAIR_SEM_SALVAR = ("Descartar", "Sair sem salvar", "Não salvar")


def ir_ao_inicio(d):
    """
    O app na tela de início (a barra de baixo, com Eu). Abre o app se precisar e volta
    tela por tela; nunca fecha o app à força: fechar e reabrir em seguida chama a
    Verificação.
    """
    d.app_start(ps.PACOTE, wait=True)
    pausa(5)
    for _ in range(8):
        xml = tela(d)
        if tem(xml, "Eu") and not tem(xml, "@et_caption"):
            return
        saida = next((b for b in SAIR_SEM_SALVAR if tem(xml, b)), None)
        if saida:
            tocar(d, saida, 3)
            continue
        d.press("back")
        pausa(3)
    raise Parada("não consegui voltar ao início do app")


def ir_ao_perfil(d):
    ir_ao_inicio(d)
    seguir(d, CAMINHO_PERFIL)


def legenda_na_tela(xml):
    return next((el["texto"] for el in ps.elementos(xml) if el["id"] == "et_caption"), "")


def mesma_legenda(na_tela, titulo):
    """A legenda da tela é o título guardado? O campo pode cortar o fim."""
    a, b = (" ".join((t or "").split()) for t in (na_tela, titulo))
    return bool(a and b) and (a == b or (len(a) >= 30 and b.startswith(a.rstrip(".… "))))


def video_do_rascunho(rascunho):
    """O vídeo no formato que as conferências do explorar usam."""
    return {"id": rascunho["id_video"], "arquivo": rascunho["arquivo"], "link": rascunho["link"],
            "nome": (rascunho["produtos"] or [""])[0]}


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

def proximo_video(config):
    """
    O vídeo da Fonte dos Vídeos do painel que nem o assistente mandou nem o robô usou,
    com link de produto: o caminho do link que abre um vídeo (Ver Produtos) ainda não
    está mapeado no Motorola, e o robô não adivinha. Sem nenhum, None.
    """
    fonte = config.get("fonte", assistente.FONTE_PADRAO)
    usados = ids_usados()
    with db.conexao() as con:
        assistente._criar_tabela(con)
        mandados = {linha[0] for linha in con.execute("SELECT id_unico FROM shopee_video_enviados")}
    for id_video, arquivo, link, legenda in assistente._candidatos(fonte if fonte in assistente.FONTES
                                                                      else assistente.FONTE_PADRAO):
        if (id_video in mandados or id_video in usados or not arquivo or not link
                or not os.path.exists(arquivo) or arquivo.lower().endswith(assistente.EXTENSOES_DE_IMAGEM)):
            continue
        if eh_video(asyncio.run(link_para_converter(link))):
            continue
        return {"id": id_video, "arquivo": os.path.abspath(arquivo), "link": link, "nome": nome_da_legenda(legenda)}
    return None


def preparar_rascunho(d, config, agora=None):
    """
    Um rascunho novo, do vídeo da fonte até Rascunhos, com todas as conferências. O vídeo
    fica reservado (o assistente não o pega) enquanto o robô trabalha nele.
    """
    video = proximo_video(config)
    if not video:
        return "nenhum vídeo da fonte com arquivo e link de produto para um rascunho"
    ident = criar(video["id"], agora)
    assistente.registrar(video["id"], "robo", "rascunho do robô", agora)
    try:
        _preparar(d, ident, video, config.get("fonte", assistente.FONTE_PADRAO))
    except (Parada, Verificacao) as e:
        do_video = isinstance(e, Parada) and e.do_video
        _desfazer_reserva(ident, video["id"], e.motivo if isinstance(e, Parada) else "verificação", do_video)
        raise
    except Exception as e:
        _desfazer_reserva(ident, video["id"], type(e).__name__, False)
        raise
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


def _preparar(d, ident, video, fonte):
    nome = ps.nome_do_produto(video)
    if not nome:
        raise Parada("o link não diz o produto do vídeo", do_video=True)
    # Antes de tocar no celular, o Rafael sabe qual vídeo e qual produto o robô pegou.
    avisar(f"🤖 Robô da Shopee Vídeo: começando um rascunho.\n\nProduto: {nome}\n"
           f"Vídeo: o mais novo de {assistente.FONTES.get(fonte, fonte)} ainda não usado.")
    _conferir(ps.ia_confere_produto(video))
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
    atualizar(ident, arquivo=copia, link=video["link"], produtos=[nome], titulo=textos["titulo"],
              comentario=textos.get("comentario") or "")

    # Curtir o produto pela página dele, como o Rafael faz antes de postar.
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
    seguir(d, CAMINHO_POSTAR)

    tocar(d, "@et_caption", 3)
    d.send_keys(textos["titulo"])
    pausa(3)
    if not mesma_legenda(legenda_na_tela(tela(d)), textos["titulo"]):
        raise Parada("o título não ficou na legenda")
    tocar(d, "@tv_right", 3)

    seguir(d, CAMINHO_PRODUTO)
    _conferir(ps.adicionar_produto(d, video))
    tocar(d, "Feito", 6)
    _conferir(ps.conferir_tela_final(d, video))

    print_tela = os.path.join(PASTA_RASCUNHOS, f"{ident}.png")
    d.screenshot(print_tela)
    tocar(d, "@tv_drafts_box", 12)
    if tem(tela(d), "@btn_post"):
        raise Parada("toquei em Rascunhos, mas o app continuou na tela final")
    atualizar(ident, estado="rascunho", print=print_tela)
    esperando = len(esperando_aprovacao())
    avisar(f"📝 Robô da Shopee Vídeo: rascunho novo salvo no celular. {esperando} esperando a sua aprovação "
           "em Shopee Vídeo 🎬 → Rascunhos do Robô 📝.")


def nome_na_galeria(ident):
    return f"robo_shopee_video_{ident}.mp4"


# --- Os rascunhos no app ---

def abrir_lista_de_rascunhos(d):
    """Perfil em Shopee Vídeo → o quadro "Rascunhos: N" → a lista."""
    ir_ao_perfil(d)
    tocar(d, "Rascunhos", 6)


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
    xml = tela(d)
    if not mesma_legenda(legenda_na_tela(xml), rascunho["titulo"]):
        raise Parada("o rascunho aberto não tem o título do aprovado")
    _conferir(ps.conferir_tela_final(d, video_do_rascunho(rascunho)), do_video=False)


def publicar(d, rascunho, agora=None):
    """Posta o rascunho aprovado e manda no privado o link do post e o comentário."""
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
    _limpar_galeria(d, rascunho)
    return "rascunho aprovado postado"


def link_do_post(d):
    """
    O link do post que acabou de sair: Perfil em Shopee Vídeo → o vídeo mais novo →
    Compartilhar → Copiar link. Qualquer passo que não aparece: sem link (o post saiu
    do mesmo jeito, e a mensagem diz onde achar). Nada aqui desfaz a postagem: até a
    Verificação só abre a tela do celular no privado.
    """
    try:
        ir_ao_perfil(d)
        quadros = [q for q in quadros_da_lista(tela(d)) if not tem_texto_no_quadro(d, q, "Rascunhos")]
        if not quadros:
            return ""
        d.click(*ps._centro(quadros[0]))
        pausa(8)
        for alvo in ("Compartilhar", "Copiar link"):
            if not tem(tela(d), alvo):
                return ""
            tocar(d, alvo, 4)
        copiado = (d.clipboard or "").strip()
        return copiado if copiado.startswith("http") and "shopee" in copiado else ""
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
    Apaga do app o rascunho que o Rafael recusou: a lista → Selecionar → o rascunho →
    Excluir → confirmar. Confere antes, abrindo-o, que é o rascunho recusado.
    """
    abrir_rascunho(d, rascunho)
    ir_ao_inicio(d)
    abrir_lista_de_rascunhos(d)
    quadros = quadros_da_lista(tela(d))
    posicao = posicao_no_app(rascunho)
    tocar(d, "Selecionar", 3)
    d.click(*ps._centro(quadros[posicao]))
    pausa(2)
    tocar(d, "Excluir", 3)
    tocar(d, "Excluir", 6)
    atualizar(rascunho["id"], estado="apagado")
    _limpar_galeria(d, rascunho)
    return "rascunho recusado apagado"


def _limpar_galeria(d, rascunho):
    """O vídeo do rascunho sai da galeria do celular quando não é mais preciso."""
    try:
        caminho = f"{ps.GALERIA}/{nome_na_galeria(rascunho['id'])}"
        d.shell(["rm", "-f", caminho])
        d.shell(["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", "file://" + caminho])
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Vídeo não saiu da galeria: {type(e).__name__}")


# --- Treino ---

def treinar(d, agora=None):
    """
    Percorre o caminho todo até a tela final sem salvar nem postar, conferindo cada tela
    com o mapa (os CAMINHOs): se a Shopee mudou o app, o Rafael fica sabendo antes de uma
    rodada de verdade travar no meio. Abre também a página completa de um produto já
    usado, sem curtir. Avisa no privado: caminho OK, ou a tela que mudou, com o print.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    gravar_estado(treino_semana=semana(agora), treino_em=_momento(agora))
    try:
        ultimo = (listar(*NO_APP, "postado", "apagado") or [None])[-1]
        if ultimo:
            ir_ao_inicio(d)
            ps.abrir_link(d, ultimo["link"])
            pausa(12)
            ok, motivo, _ = ps.abrir_pagina_completa(d, video_do_rascunho(ultimo))
            if not ok:
                raise Parada(f"página do produto: {motivo}")
        ir_ao_perfil(d)
        if not tem(tela(d), "Rascunhos"):
            raise Parada("o Perfil em Shopee Vídeo não mostrou os Rascunhos")
        seguir(d, CAMINHO_POSTAR)
        xml = tela(d)
        faltam = [alvo for alvo in ("@et_caption", "@ll_add_product_symbol", "@tv_drafts_box", "@btn_post")
                  if not tem(xml, alvo)]
        if faltam:
            raise Parada(f"a tela final não tem {', '.join(faltam)}")
        seguir(d, CAMINHO_PRODUTO)
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

def celular_pronto():
    """O celular responde e o Rafael não está com a tela dele aberta no privado."""
    return celular_robo.conectado() and not av.tela_aberta()


def avisar_desconectado(agora=None):
    """Uma vez por dia: sem o celular, o robô não faz nada, e o Rafael precisa reconectar."""
    dia = agora_br(agora).strftime("%Y-%m-%d")
    if ler_estado().get("aviso_desconectado") == dia:
        return
    gravar_estado(aviso_desconectado=dia)
    avisar("📱 Robô da Shopee Vídeo: não consigo falar com o celular guardado, então não fiz nada. No "
           "Motorola, ligue a Depuração por Wi-Fi e, no bot, toque em Shopee Vídeo 🎬 → Celular do Robô 📱 → "
           "Reconectar Celular 🔄.")


def rodada(treino=False, d=None, agora=None):
    """
    Uma rodada. treino=True é o botão Testar Caminho 🧭: roda o treino na hora, mesmo
    pausado ou fora do horário (o Rafael pediu agora). Devolve o que aconteceu, numa frase.
    """
    config = ler_config()
    if not treino:
        if config["robo_pausado"]:
            consumir_horarios(config, agora)
            return "pausado"
        if not no_horario(config, agora):
            return "fora do Horário do Robô"
    if d is None and not celular_pronto():
        if not treino:
            avisar_desconectado(agora)
        return "celular desconectado ou com a tela aberta no privado"
    with celular_robo.trava() as livre:
        if not livre:
            return "o explorar está tocando no celular"
        acao, ident = ("treino", None) if treino else (o_que_fazer(config, agora) or (None, None))
        if not acao:
            return "nada a fazer agora"
        d = d or ps.conectar(celular=True)
        try:
            if acao == "treino":
                return treinar(d, agora)
            if acao == "apagar":
                return apagar_do_app(d, pegar(ident))
            if acao == "postar":
                return publicar(d, pegar(ident), agora)
            return preparar_rascunho(d, config, agora)
        except Verificacao:
            logger.warning("⚠️ [Robô Shopee Vídeo] Verificação da Shopee na tela: parado.")
            av.abrir_tela(celular=True, verificacao=True)
            return f"{acao}: verificação na tela; parado"
        except Parada as e:
            if acao in ("postar", "apagar"):
                # Não insiste: o Rafael decide de novo pelo botão.
                atualizar(ident, estado="rascunho", postar_em=None, motivo=e.motivo)
                avisar(f"⚠️ Robô da Shopee Vídeo: não consegui {'postar' if acao == 'postar' else 'apagar'} "
                       f"o rascunho ({e.motivo}). Não toquei em mais nada; ele voltou para Rascunhos do Robô 📝.")
            return f"{acao}: parado ({e.motivo})"


def main(argumentos):
    logging.basicConfig(level=os.getenv("NIVEL_LOG", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    treino = "--treino" in argumentos
    if not treino and "--rodada" not in argumentos:
        print(__doc__)
        return 2
    resultado = rodada(treino=treino)
    logger.info(f"🤖 [Robô Shopee Vídeo] {resultado}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

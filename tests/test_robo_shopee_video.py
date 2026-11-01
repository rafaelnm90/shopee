"""Robô automático da Shopee Vídeo (robo_shopee_video): plano do dia, aprovação espalhada, rodada e o caminho no app."""
import io
import json
import math
import os
import random
import re
import time
from datetime import datetime
from xml.sax.saxutils import escape

import pytest

import robo_shopee_video as robo
from conftest import consultar, inserir
from fuso import fuso_horario

VESTIDO = "Vestido Infantil Estampado Gatinho Para Meninas de 4 a 14 Anos"
TITULO = "Vestido Infantil Estampado Gatinho 👗 #vestidoinfantil #modainfantil #menina"
LINK = "https://s.shopee.com.br/vestido"


def momento(texto):
    """"2026-10-22 15:00" em Brasília."""
    return datetime.strptime(texto, "%Y-%m-%d %H:%M").replace(tzinfo=fuso_horario)


# A leitura da Saúde do Vídeo do dia fica de fora dos testes que não são dela.
SAUDE_DO_DIA = robo.saude_do_dia_pendente
# A busca do mesmo produto com mais comissão (P33) também: ela vai à API de afiliado.
TROCAR = robo.trocar_pela_maior_comissao
# E o vídeo postado que vai à fila do Canal Afiliados (P62 a P64), com testes no fim.
LEVAR_AO_CANAL = robo.levar_ao_canal


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(robo.time, "sleep", lambda s: None)
    monkeypatch.setattr(robo.ps.time, "sleep", lambda s: None)
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    monkeypatch.setattr(robo, "trocar_pela_maior_comissao", lambda video: None)
    monkeypatch.setattr(robo, "levar_ao_canal", lambda rascunho, link_post: None)
    # As respostas aos comentários e o feed têm testes próprios (test_interacoes_shopee_video).
    monkeypatch.setattr(robo, "respostas_pendentes", lambda agora=None: False)
    monkeypatch.setattr(robo, "feed_pendente", lambda agora=None: False)
    # No servidor a tabela já existe (o bot_mestre cria).
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")


@pytest.fixture
def avisos(monkeypatch):
    mandados = []
    monkeypatch.setattr(robo.avisar_rafael, "mandar_texto", lambda texto: mandados.append(texto) or True)
    monkeypatch.setattr(robo.avisar_rafael, "mandar_foto",
                        lambda caminho, legenda="": mandados.append(("foto", legenda)) or True)
    monkeypatch.setattr(robo.avisar_rafael, "mandar_video",
                        lambda caminho, legenda="": mandados.append(("video", legenda)) or True)
    return mandados


def ativar(**mudancas):
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": False, **mudancas})


# --- Plano do dia ---

def test_plano_do_dia_fica_na_faixa_e_no_horario_e_varia_de_um_dia_para_outro():
    config = {**robo.PADRAO, "robo_limite_min": 2, "robo_limite_max": 4, "robo_inicio": 9, "robo_fim": 21}
    planos = [robo.planejar(config, f"2026-10-{dia:02d}") for dia in range(1, 21)]
    for plano in planos:
        assert 2 <= len(plano) <= 4 and plano == sorted(plano)
        assert all("09:00" <= h < "21:00" for h in plano)
    assert planos[0] == robo.planejar(config, "2026-10-01")          # mesmo dia, mesmo plano
    assert len({tuple(p) for p in planos}) > 10 and len({len(p) for p in planos}) > 1


def test_horarios_que_passam_de_uma_vez_sem_espaco_no_dia_contam_como_um_so():
    # Às 19:59 de um Horário do Robô que acaba às 20h, não cabe mais nenhum: sai um só.
    config = {**robo.PADRAO, "robo_limite_min": 3, "robo_limite_max": 3, "robo_inicio": 8, "robo_fim": 20}
    assert not robo.consumir_horarios(config, momento("2026-10-22 08:00"))
    assert robo.consumir_horarios(config, momento("2026-10-22 19:59"))
    assert not robo.consumir_horarios(config, momento("2026-10-22 19:59"))
    assert robo.consumir_horarios(config, momento("2026-10-23 19:59"))  # dia novo, plano novo



def test_horarios_perdidos_voltam_espalhados_no_resto_do_dia():
    # Pedido do Rafael (01/11, no lugar da P16): com o celular fora das 22:05 às 11:35, 5 dos 9
    # horários do dia passaram e só 1 rascunho saiu por eles. Agora o 1º sai na volta e os outros
    # voltam ao resto do dia, com os que faltavam: 1 h em média, nunca menos de 30 min entre um e
    # outro, fora do Horário das Interações; o que não cabe sem apertar fica de fora.
    config = {**robo.PADRAO, "robo_pausado": False, "robo_inicio": 8, "robo_fim": 22,
              "robo_interacoes_inicio": 20, "robo_interacoes_fim": 21}
    horarios = ["08:30", "09:30", "10:30", "11:30", "12:30", "14:30", "16:30", "18:30", "21:30"]
    robo.db.salvar_config(robo.CHAVE_DIA, {"data": "2026-11-01", "horarios": horarios, "feitos": 0})
    agora = momento("2026-11-01 13:00")
    assert robo.consumir_horarios(config, agora) is True                # o 1º dos perdidos, agora
    estado = robo.estado_do_dia(config, agora)
    futuros = [h for h in estado["horarios"] if h > "13:00"]
    # Das 13:30 às 22:00, sem as 20h, cabem 7: os 4 que faltavam e 3 dos 4 perdidos; 1 fica de fora.
    assert len(estado["horarios"]) == 9 and len(futuros) == 7
    assert (estado["feitos"], estado["sem_tentar"]) == (2, 1)
    minutos = [int(h[:2]) * 60 + int(h[3:]) for h in futuros]
    assert minutos[0] >= 13 * 60 + 30 and not any(20 * 60 <= m < 21 * 60 for m in minutos)
    assert all(depois - antes >= 30 for antes, depois in zip(minutos, minutos[1:]))
    assert robo.consumir_horarios(config, agora) is False
    resultado, detalhe = consultar("SELECT resultado, detalhe FROM registro_processos WHERE processo = ?",
                                   robo.PROCESSO_DOS_PERDIDOS)
    assert resultado == "3 de 4 de volta ao plano" and detalhe == "de fora por falta de espaço no dia: 1"
    # Cada perdido que volta sai no seu horário, um de cada vez.
    assert robo.consumir_horarios(config, momento(f"2026-11-01 {futuros[0]}")) is True
    assert robo.estado_do_dia(config, agora)["feitos"] == 3


def test_dois_posts_nunca_saem_colados_e_os_atrasados_se_espalham():
    # Pedido do Rafael (01/11): na volta do celular, os 2 aprovados atrasados saíam um logo depois
    # do outro. Com um post saído há menos de 30 min, os atrasados ganham horário novo, espalhados.
    config = {**robo.PADRAO, "robo_pausado": False, "robo_limite_min": 1, "robo_limite_max": 1,
              "robo_inicio": 0, "robo_fim": 24}
    agora = momento("2026-11-01 12:00")
    robo.gravar_estado(treino_semana=robo.semana(agora))
    robo.db.salvar_config(robo.CHAVE_DIA, {"data": "2026-11-01", "horarios": [], "feitos": 0})
    postado = _rascunho("postado", postado_em="2026-11-01 11:50:00")
    primeiro = _rascunho("aprovado", postar_em="2026-10-31 21:54:00")
    segundo = _rascunho("aprovado", postar_em="2026-10-31 22:47:00")
    assert robo.o_que_fazer(config, agora) != ("postar", primeiro)
    horas = [datetime.strptime(robo.pegar(i)["postar_em"], "%Y-%m-%d %H:%M:%S") for i in (primeiro, segundo)]
    assert horas[0] >= datetime(2026, 11, 1, 12, 30) and 30 <= (horas[1] - horas[0]).total_seconds() / 60 <= 90
    # Com o último post há mais de 30 min, o atrasado sai na hora.
    robo.atualizar(postado, postado_em="2026-11-01 11:20:00")
    robo.atualizar(primeiro, postar_em="2026-11-01 11:55:00")
    assert robo.o_que_fazer(config, agora) == ("postar", primeiro)

# --- Aprovação: postagens espalhadas ---

def _rascunho(estado="rascunho", criado="2026-10-22 10:00:00", **campos):
    ident = robo.criar("video:1", None)
    robo.atualizar(ident, estado=estado, criado_em=criado, titulo=TITULO, link=LINK, produtos=[VESTIDO],
                   comentario="Amei! #achadinhos", **campos)
    return ident


def test_aprovados_saem_um_de_cada_vez_com_intervalo_sorteado(monkeypatch):
    ativar(robo_inicio=8, robo_fim=22)
    primeiro, segundo, terceiro = _rascunho(), _rascunho(), _rascunho()
    agora = momento("2026-10-22 10:00")
    quando = [robo.aprovar(ident, agora) for ident in (primeiro, segundo, terceiro)]
    horas = [datetime.strptime(q, "%Y-%m-%d %H:%M:%S") for q in quando]
    assert 5 <= (horas[0] - agora.replace(tzinfo=None)).total_seconds() / 60 <= 40
    for antes, depois in zip(horas, horas[1:]):
        assert 30 <= (depois - antes).total_seconds() / 60 <= 90
    assert all(r["estado"] == "aprovado" for r in robo.listar("aprovado"))


def test_fila_mostra_os_que_esperam_aprovacao_e_os_aprovados_com_a_hora_e_o_porque(monkeypatch):
    # Pedido do Rafael (25/10): ver os rascunhos e os aprovados, e saber por que o aprovado
    # que passou da hora ainda não saiu.
    ativar(robo_inicio=8, robo_fim=22, robo_interacoes_inicio=10, robo_interacoes_fim=12)
    _rascunho(criado="2026-10-25 09:00:00")
    atrasado = _rascunho()
    robo.atualizar(atrasado, estado="aprovado", postar_em="2026-10-25 09:50:00", produtos=["Copo Térmico"])
    depois = _rascunho()
    robo.atualizar(depois, estado="aprovado", postar_em="2026-10-25 12:20:00", produtos=["Mini Saia", "Blusa"])
    texto = robo.texto_da_fila(agora=momento("2026-10-25 10:30"))
    assert "Esperando a sua aprovação (1)" in texto and "salvo em 25/10 às 09:00" in texto
    assert "Aprovados, esperando ir ao ar (2)" in texto
    assert texto.index("Copo Térmico") < texto.index("Mini Saia (+1)")
    assert "posta por volta de 25/10 às 09:50" in texto and "posta por volta de 25/10 às 12:20" in texto
    assert texto.count("já passou da hora") == 1
    assert "no Horário das Interações, esperando acabarem 3 comentário(s) no feed" in texto
    # Pausado, o motivo é a pausa; sem nada, a fila diz "nenhum".
    ativar(robo_pausado=True)
    assert "a Postagem está pausada" in robo.texto_da_fila(agora=momento("2026-10-25 10:30"))
    for ident in (atrasado, depois):
        robo.atualizar(ident, estado="postado")
    robo.atualizar(robo.esperando_aprovacao()[0]["id"], estado="recusado")
    assert robo.texto_da_fila(agora=momento("2026-10-25 10:30")).count("nenhum") == 2


def test_aprovado_fora_do_horario_vai_para_o_comeco_do_proximo(monkeypatch):
    ativar(robo_inicio=8, robo_fim=22)
    noite = robo.proxima_postagem(robo.ler_config(), momento("2026-10-22 21:50"), random.Random(1))
    assert "2026-10-23 08:05:00" <= noite <= "2026-10-23 08:40:00"
    madrugada = robo.proxima_postagem(robo.ler_config(), momento("2026-10-23 03:00"), random.Random(1))
    assert "2026-10-23 08:05:00" <= madrugada <= "2026-10-23 08:40:00"


# --- O que fazer em cada rodada ---

def test_ordem_da_rodada_treino_apagar_postar_e_rascunho():
    config = {**robo.PADRAO, "robo_pausado": False, "robo_limite_min": 1, "robo_limite_max": 1,
              "robo_inicio": 0, "robo_fim": 24}
    segunda = momento("2026-10-26 23:59")
    assert robo.o_que_fazer(config, segunda) == ("treino", None)
    robo.gravar_estado(treino_semana=robo.semana(segunda))
    recusado = _rascunho("recusado")
    aprovado = _rascunho("aprovado", postar_em="2026-10-26 23:00:00")
    assert robo.o_que_fazer(config, segunda) == ("apagar", recusado)
    robo.atualizar(recusado, estado="apagado")
    assert robo.o_que_fazer(config, segunda) == ("postar", aprovado)
    robo.atualizar(aprovado, estado="postado")
    assert robo.o_que_fazer(config, segunda) == ("rascunho", None)
    assert robo.o_que_fazer(config, segunda) is None                     # o horário do dia já foi usado
    terca = momento("2026-10-27 23:59")
    assert robo.o_que_fazer(config, terca) == ("rascunho", None)          # treino só na segunda


def test_aprovado_espera_a_hora_dele():
    config = {**robo.PADRAO, "robo_limite_min": 1, "robo_limite_max": 1, "robo_inicio": 23, "robo_fim": 24}
    _rascunho("aprovado", postar_em="2026-10-22 16:00:00")
    assert robo.o_que_fazer(config, momento("2026-10-22 15:59")) is None
    assert robo.o_que_fazer(config, momento("2026-10-22 16:00"))[0] == "postar"


def test_aprovado_chegando_segura_tarefa_longa_e_sai_na_hora(monkeypatch):
    # Escolha do Rafael (25/10, P30): o de 09:59 saiu às 10:15 porque o feed segurava o
    # celular. Com um aprovado indo ao ar antes da próxima rodada, nada de tarefa longa.
    config = {**robo.PADRAO, "robo_pausado": False, "robo_limite_min": 1, "robo_limite_max": 1,
              "robo_inicio": 0, "robo_fim": 24}
    agora = momento("2026-10-25 09:46")
    robo.gravar_estado(treino_semana=robo.semana(agora))
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    monkeypatch.setattr(robo, "respostas_pendentes", lambda agora=None: False)
    monkeypatch.setattr(robo, "feed_pendente", lambda agora=None: True)
    robo.db.salvar_config(robo.CHAVE_DIA, {"data": "2026-10-25", "horarios": ["09:30"], "feitos": 0})
    perto = _rascunho("aprovado", postar_em="2026-10-25 09:59:00")
    assert robo.o_que_fazer(config, agora) is None                          # espera: nem rascunho nem feed
    assert robo.o_que_fazer(config, momento("2026-10-25 10:00")) == ("postar", perto)
    robo.atualizar(perto, estado="postado")
    _rascunho("aprovado", postar_em="2026-10-25 11:30:00")                  # longe: segue o resto
    assert robo.o_que_fazer(config, momento("2026-10-25 10:01")) == ("rascunho", None)
    assert robo.o_que_fazer(config, momento("2026-10-25 10:02")) == ("feed", None)


# --- O Horário das Interações (escolha do Rafael, P22 a P24) ---

def _com_interacoes(inicio=12, fim=15, **mais):
    return {**robo.PADRAO, "robo_limite_min": 6, "robo_limite_max": 6, "robo_inicio": 8, "robo_fim": 22,
            "robo_interacoes_inicio": inicio, "robo_interacoes_fim": fim, **mais}


def test_plano_do_dia_pula_o_horario_das_interacoes():
    horarios = robo.planejar(_com_interacoes(), "2026-10-25")
    assert len(horarios) == 6 and all(not "12:00" <= h < "15:00" for h in horarios)
    assert all("08:00" <= h < "22:00" for h in horarios)
    # Sem ele escolhido, o plano corre o Horário do Robô inteiro, como antes.
    sem = {**_com_interacoes(), "robo_interacoes_inicio": None, "robo_interacoes_fim": None}
    assert robo.planejar(sem, "2026-10-25") != horarios


def test_na_janela_das_interacoes_so_responde_e_comenta_no_feed(monkeypatch):
    config = _com_interacoes()
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-25 13:00")))
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    monkeypatch.setattr(robo, "respostas_pendentes", lambda agora=None: True)
    monkeypatch.setattr(robo, "feed_pendente", lambda agora=None: True)
    aprovado = _rascunho("aprovado", postar_em="2026-10-25 09:00:00")
    # 13h: na janela, nem o aprovado vencido sai nem o plano gasta horário.
    assert robo.o_que_fazer(config, momento("2026-10-25 13:00")) == ("responder", None)
    assert robo.estado_do_dia(config, momento("2026-10-25 13:00"))["feitos"] == 0
    # 16h: fora dela, o robô posta e prepara, e não comenta no feed; as respostas, nas horas
    # delas, saem dentro ou fora (P70).
    assert robo.o_que_fazer(config, momento("2026-10-25 16:00")) == ("postar", aprovado)
    robo.atualizar(aprovado, estado="postado")
    assert robo.o_que_fazer(config, momento("2026-10-25 16:00")) == ("rascunho", None)
    monkeypatch.setattr(robo, "consumir_horarios", lambda config, agora=None: False)
    monkeypatch.setattr(robo, "repetir_o_que_falhou", lambda config, agora=None: False)
    assert robo.o_que_fazer(config, momento("2026-10-25 16:30")) == ("responder", None)
    monkeypatch.setattr(robo, "respostas_pendentes", lambda agora=None: False)
    assert robo.o_que_fazer(config, momento("2026-10-25 16:30")) is None


def test_na_janela_o_postar_volta_quando_as_interacoes_do_dia_acabam(monkeypatch):
    # Escolha do Rafael (P26): o postar só para enquanto ainda tem comentário ou resposta.
    config = _com_interacoes()
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-25 13:00")))
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    monkeypatch.setattr(robo, "respostas_pendentes", lambda agora=None: False)
    monkeypatch.setattr(robo, "feed_pendente", lambda agora=None: False)
    aprovado = _rascunho("aprovado", postar_em="2026-10-25 09:00:00")
    monkeypatch.setattr(robo.interacoes, "quantos_desde", lambda *a, **k: 2)
    assert robo.o_que_fazer(config, momento("2026-10-25 13:00")) is None        # falta 1 do feed
    monkeypatch.setattr(robo.interacoes, "quantos_desde", lambda *a, **k: 3)
    assert robo.o_que_fazer(config, momento("2026-10-25 13:00")) == ("postar", aprovado)


def test_janela_das_interacoes_fora_do_horario_do_robo_tambem_roda():
    config = _com_interacoes(inicio=22, fim=24)
    assert robo.no_horario(config, momento("2026-10-25 22:30"))
    assert not robo.no_horario(config, momento("2026-10-25 07:30"))


def test_aprovado_nao_cai_no_horario_das_interacoes():
    class Sorteio:
        @staticmethod
        def randint(a, b):
            return a

    quando = robo.proxima_postagem(_com_interacoes(), momento("2026-10-25 11:58"), sorteio=Sorteio)
    assert quando == "2026-10-25 15:05:00"
    # Interações até a meia-noite: o aprovado vai para o começo do Horário do Robô de amanhã.
    quando = robo.proxima_postagem(_com_interacoes(inicio=21, fim=24), momento("2026-10-25 20:58"), sorteio=Sorteio)
    assert quando == "2026-10-26 08:05:00"


def test_feed_numa_janela_curta_espalha_os_3_comentarios_nela():
    from datetime import timedelta
    assert robo.intervalo_do_feed(_com_interacoes(inicio=12, fim=15)) == timedelta(hours=1)
    assert robo.intervalo_do_feed(_com_interacoes(inicio=10, fim=20)) == robo.INTERVALO_DO_FEED
    assert robo.intervalo_do_feed({**robo.PADRAO}) == robo.INTERVALO_DO_FEED


def test_mudar_a_janela_replaneja_o_que_falta_sem_perder_os_feitos():
    config = _com_interacoes(inicio=None, fim=None)
    estado = robo.estado_do_dia(config, momento("2026-10-25 09:00"))
    estado["feitos"] = 2
    robo.db.salvar_config(robo.CHAVE_DIA, estado)
    robo.replanejar_hoje(_com_interacoes(), momento("2026-10-25 09:00"))
    novo = robo.db.ler_config(robo.CHAVE_DIA)
    assert novo["feitos"] == 2 and all(not "12:00" <= h < "15:00" for h in novo["horarios"])


# --- A hora do descurtir (escolha do Rafael, P25: fixa às 4h) ---

def test_as_4h_o_robo_so_descurte_uma_vez(monkeypatch):
    config = {**robo.PADRAO, "robo_limite_min": 6, "robo_limite_max": 6, "robo_inicio": 0, "robo_fim": 24}
    monkeypatch.setattr(robo, "respostas_pendentes", lambda agora=None: True)
    aprovado = _rascunho("aprovado", postar_em="2026-10-25 03:00:00")
    _rascunho("recusado")
    assert robo.no_horario({**config, "robo_inicio": 8, "robo_fim": 22}, momento("2026-10-25 04:10"))
    assert robo.o_que_fazer(config, momento("2026-10-25 04:10")) == ("descurtir", None)
    robo.gravar_estado(descurtir_em="2026-10-25 04:10:00", descurtir_continuar=False)
    # Feito o descurtir, o resto da hora fica parado: nem o treino, nem apagar, nem postar.
    assert robo.o_que_fazer(config, momento("2026-10-25 04:40")) is None
    robo.gravar_estado(descurtir_continuar=True)
    assert robo.o_que_fazer(config, momento("2026-10-25 04:40")) == ("descurtir", None)
    robo.gravar_estado(descurtir_continuar=False)
    assert robo.o_que_fazer(config, momento("2026-10-25 05:00"))[0] in ("treino", "apagar")
    assert robo.o_que_fazer({**config, "robo_inicio": 8}, momento("2026-10-25 04:59")) is None
    assert aprovado


def test_plano_e_aprovados_pulam_a_hora_do_descurtir():
    class Sorteio:
        @staticmethod
        def randint(a, b):
            return a

    config = {**robo.PADRAO, "robo_limite_min": 24, "robo_limite_max": 24, "robo_inicio": 0, "robo_fim": 24}
    horarios = robo.planejar(config, "2026-10-25")
    assert len(horarios) == 24 and not any(h.startswith("04:") for h in horarios)
    assert robo.proxima_postagem(config, momento("2026-10-25 03:58"), sorteio=Sorteio) == "2026-10-25 05:05:00"


def test_conta_suspensa_as_4h_faz_a_limpeza_dos_favoritos_e_nao_le_a_saude(monkeypatch, avisos):
    # Pedido do Rafael (25/10): na suspensão, só o preparo, a postagem e o treino esperam; a
    # limpeza dos favoritos das 4h continua, e a hora dela segue só dela.
    ativar(robo_inicio=0, robo_fim=24, robo_suspenso_ate="2026-11-01 00:00:00")
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: True)
    app = AppDosFavoritos(favoritos=3)
    assert robo.rodada(d=app, agora=momento("2026-10-25 04:10")) == "3 produto(s) descurtido(s) em Meus favoritos"
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-25 04:25")) == "nada a fazer agora"


# --- A rodada não toca no celular quando não deve ---

class Intocavel:
    def __getattr__(self, nome):
        pytest.fail(f"o robô não devia tocar no celular ({nome})")


def test_pausado_nao_toca_e_pula_os_horarios(monkeypatch, avisos):
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_limite_min": 1, "robo_limite_max": 1})
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: pytest.fail("pausado nem olha o celular"))
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 21:59")) == "pausado"
    assert robo.estado_do_dia(robo.ler_config(), momento("2026-10-22 21:59"))["feitos"] == 1
    # Pulado sem tentativa: o checkup não o cobra.
    assert robo.estado_do_dia(robo.ler_config(), momento("2026-10-22 21:59"))["sem_tentar"] == 1


def test_pausa_por_desconexao_guarda_os_horarios_e_na_volta_sem_espaco_ficam_de_fora(monkeypatch, avisos):
    # 24/10/2026: o celular caiu às 15:09 e o horário das 15:29 foi pulado na pausa sozinha. Na
    # pausa sozinha os horários ficam; na volta (pedido do Rafael de 01/11, no lugar da P16), o 1º
    # sai e os outros voltam ao resto do dia. Às 21:59 não cabe mais nenhum.
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_limite_min": 2, "robo_limite_max": 2,
                                              "robo_pausado": True, "robo_pausa_motivo": robo.MOTIVO_DA_DESCONEXAO})
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: pytest.fail("pausado nem olha o celular"))
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 21:59")) == "pausado"
    assert robo.estado_do_dia(robo.ler_config(), momento("2026-10-22 21:59"))["feitos"] == 0
    # Retomado: o 1º dos 2 horários que passaram sai agora; o outro não cabe mais no dia.
    robo.db.atualizar_config(robo.CHAVE_CONFIG, lambda dados: dados.update(robo_pausado=False, robo_pausa_motivo=""))
    assert robo.consumir_horarios(robo.ler_config(), momento("2026-10-22 21:59")) is True
    assert robo.consumir_horarios(robo.ler_config(), momento("2026-10-22 21:59")) is False
    # O que não coube fica como sem tentativa, e o checkup não o cobra.
    assert robo.estado_do_dia(robo.ler_config(), momento("2026-10-22 21:59"))["sem_tentar"] == 1


def test_fora_do_horario_nao_toca(monkeypatch, avisos):
    ativar(robo_inicio=8, robo_fim=22)
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 22:00")) == "fora do Horário do Robô"


def test_celular_desconectado_tenta_sozinho_e_sem_ele_pausa_e_avisa(monkeypatch, avisos):
    ativar(robo_inicio=0, robo_fim=24)
    tentativas = []
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "reconectar_sozinho",
                        lambda: tentativas.append(1) or (False, "a Depuração por Wi-Fi está desligada no celular"))
    assert "desconectado" in robo.rodada(agora=momento("2026-10-22 10:00"))
    config = robo.ler_config()
    # A Postagem pausa sozinha, e o assistente volta a mandar no privado.
    assert tentativas == [1] and config["robo_pausado"] is True
    assert config["robo_pausa_motivo"] == "celular desconectado"
    assert len(avisos) == 1 and "Retomar Postagem ▶️" in avisos[0] and "assistente" in avisos[0]
    # 31/10: o aviso mandava a "Shopee Vídeo 🎬 → Retomar Postagem ▶️", mas o botão fica em Robô
    # Automático 🤖; com a depuração ligada e o adb sem conectar, o caminho é parear de novo.
    assert "Shopee Vídeo 🎬 → Robô Automático 🤖 → Retomar Postagem ▶️" in avisos[0]
    assert "Celular do Robô 📱 → Parear Celular 🔗" in avisos[0] and "desligue e ligue de novo" in avisos[0]
    assert robo.rodada(agora=momento("2026-10-22 10:15")) == "pausado"
    assert len(avisos) == 1 and tentativas == [1]


def test_pareamento_vencido_avisa_para_parear_e_nao_para_ligar_a_depuracao(monkeypatch, avisos):
    # 31/10, 16:09: o pareamento venceu 7 dias depois de feito; desligar e ligar a depuração
    # não adiantava, e o aviso mandava fazer isso.
    ativar(robo_inicio=0, robo_fim=24)
    vencido = f"a Depuração por Wi-Fi responde, mas {robo.celular_robo.MOTIVO_DO_PAREAMENTO}: x"
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "reconectar_sozinho", lambda: (False, vencido))
    assert "desconectado" in robo.rodada(agora=momento("2026-10-31 16:09"))
    assert len(avisos) == 1 and robo.celular_robo.COMO_PAREAR in avisos[0]
    assert "desligue e ligue de novo" not in avisos[0] and "Retomar Postagem ▶️" in avisos[0]


def test_rodada_anota_o_prazo_do_pareamento(monkeypatch, avisos):
    # Pedido do Rafael (31/10): a opção que impede o pareamento de vencer fica sempre ligada; o
    # robô a lê quando usa o celular, e o alertas.py avisa se ela desligar.
    ativar(robo_inicio=0, robo_fim=24)
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-22 10:00")))
    anotados = []
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: True)
    monkeypatch.setattr(robo.celular_robo, "anotar_prazo", lambda agora=None: anotados.append(agora) or 0)
    assert robo.rodada(agora=momento("2026-10-22 00:01")) == "nada a fazer agora"
    assert anotados == [momento("2026-10-22 00:01")]
    # Um erro na leitura não derruba a rodada.
    monkeypatch.setattr(robo.celular_robo, "anotar_prazo", lambda agora=None: 1 / 0)
    assert robo.rodada(agora=momento("2026-10-22 00:02")) == "nada a fazer agora"


def test_celular_que_reconecta_sozinho_segue_a_rodada(monkeypatch, avisos):
    ativar(robo_inicio=0, robo_fim=24)
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-22 10:00")))
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "reconectar_sozinho", lambda: (True, "moto g(100)"))
    assert robo.rodada(agora=momento("2026-10-22 00:01")) == "nada a fazer agora"
    assert robo.ler_config()["robo_pausado"] is False and avisos == []


def test_com_a_tela_do_celular_aberta_nem_reconecta(monkeypatch, avisos):
    ativar(robo_inicio=0, robo_fim=24)
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: True)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: pytest.fail("não devia olhar o celular"))
    assert "tela do celular está aberta" in robo.rodada(agora=momento("2026-10-22 10:00"))
    assert robo.ler_config()["robo_pausado"] is False


def test_com_o_explorar_no_celular_a_rodada_nao_toca(monkeypatch, avisos):
    ativar(robo_inicio=0, robo_fim=24)
    with robo.celular_robo.trava() as livre:
        assert livre
        with robo.celular_robo.trava() as outra:
            assert not outra
        assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 10:00")) == "o explorar está tocando no celular"


# --- O caminho no app, com um app de mentira ---

def _no(texto="", ident="", caixa=(0, 0, 10, 10), clicavel=True, filhos="", desc=""):
    x1, y1, x2, y2 = caixa
    atributos = f'text="{escape(texto, {chr(34): "&quot;"})}" class="android.view.View" clickable="{"true" if clicavel else "false"}"'
    if ident:
        atributos += f' resource-id="com.shopee.br:id/{ident}"'
    if desc:
        atributos += f' content-desc="{escape(desc)}"'
    return f'<node {atributos} bounds="[{x1},{y1}][{x2},{y2}]">{filhos}</node>'


def _xml(*nos):
    return f'<hierarchy><node class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">{"".join(nos)}</node></hierarchy>'


ABA_EU = _no("Eu", caixa=(860, 2250, 1080, 2400))
ABA_NOTIFICACOES = _no("Notificações", caixa=(650, 2250, 860, 2400))
FILTRO_DOS_VIDEOS = _no("Lives, Vídeos e Afiliados", caixa=(440, 900, 640, 990))
PRODUTO_NA_LISTA = _no(caixa=(0, 1060, 1080, 1330), filhos=(
    _no(VESTIDO, caixa=(300, 1070, 1040, 1130), clicavel=False)
    + _no(caixa=(840, 1225, 1010, 1290), filhos=_no("Adicionar", caixa=(850, 1235, 1000, 1280), clicavel=False))))


def _tela_final(legenda="", produto=False):
    return [_no(legenda, "et_caption", (40, 300, 1040, 400)), _no("OK", "tv_right", (960, 150, 1060, 210)),
            _no("Adicionar produto", "ll_add_product_symbol", (600, 700, 860, 780)),
            _no("Rascunhos", "tv_drafts_box", (20, 2260, 220, 2360)), _no("Postar", "btn_post", (300, 2260, 960, 2360))
            ] + ([_no(VESTIDO, "tv_product_title", (100, 820, 900, 880), clicavel=False)] if produto else [])


TELAS = {
    "inicio": [ABA_EU, ABA_NOTIFICACOES, _no("Início", caixa=(0, 2250, 200, 2400))],
    "pagina_curta": [_no(caixa=(0, 1100, 1080, 1300), filhos=_no(VESTIDO, caixa=(40, 1190, 1010, 1245), clicavel=False)),
                     _no("Compre Agora", caixa=(500, 1365, 720, 1410))],
    "pagina_completa": [_no(ident="buttonItemLike", caixa=(1000, 1205, 1056, 1261))],
    "pagina_curtida": [_no(ident="buttonItemLiked", caixa=(1000, 1205, 1056, 1261))],
    "eu": [ABA_EU, _no("Criadores & Afiliados", caixa=(360, 700, 700, 780))],
    "criadores": [_no("Conta", caixa=(800, 200, 1000, 260))],
    "conta": [_no("Perfil em Shopee Vídeo", caixa=(100, 600, 700, 680))],
    "perfil": [_no("Postar vídeo", caixa=(700, 2200, 1040, 2300)), _no("Rascunhos: 1", caixa=(20, 900, 350, 1300))],
    "camera": [_no("Biblioteca", caixa=(800, 2100, 1000, 2200))],
    # Dois vídeos na galeria: o mais novo (1º) e um antigo; a caixa marcada tem o número.
    "galeria": [_no(ident="ll_check", caixa=(300, 300, 360, 360)), _no(ident="ll_check", caixa=(600, 300, 660, 360))],
    "galeria_marcada": [_no(ident="ll_check", caixa=(300, 300, 360, 360),
                            filhos=_no("1", "check", (320, 310, 340, 330), clicavel=False)),
                        _no(ident="ll_check", caixa=(600, 300, 660, 360)),
                        _no("Próximo (1)", "tv_pick_top_next", (860, 2080, 980, 2130))],
    # A edição como no Motorola: o Efeitos e o Realçar na coluna da direita, e o Próximo.
    "edicao": [_no("Efeitos", caixa=(950, 640, 1030, 700)), _no("Realçar", caixa=(950, 840, 1030, 900)),
               _no("Próximo", "tv_compress", (860, 150, 1040, 210))],
    "efeitos": [_no(ident="iv_close", caixa=(40, 160, 110, 230)), _no(ident="iv_done", caixa=(970, 160, 1050, 230)),
                _no("Giro", caixa=(80, 2150, 180, 2200))],
    "efeitos_com_giro": [_no(ident="iv_close", caixa=(40, 160, 110, 230)),
                         _no(ident="iv_done", caixa=(970, 160, 1050, 230)), _no("Giro", caixa=(80, 2150, 180, 2200)),
                         _no("Desfazer", "ll_undo", (880, 1880, 1040, 1940))],
    "final": "final",
    "final_editando": [_no("", "et_caption", (40, 300, 1040, 400))],
    "curtidas": [_no("Minhas Curtidas", caixa=(300, 410, 510, 460)), _no("Mais Recente", caixa=(300, 520, 510, 570)),
                 PRODUTO_NA_LISTA],
    "janela": [_no("Editar nome do produto", caixa=(300, 1310, 780, 1370), clicavel=False),
               _no(VESTIDO, caixa=(360, 1450, 1040, 1510), clicavel=False), _no("Feito", caixa=(480, 2290, 600, 2340))],
    "live": [ABA_EU, _no("Live e Vídeo", caixa=(400, 2250, 600, 2400))],
    # As Notificações, como no Motorola: os filtros no alto e a lista embaixo.
    "notificacoes": [_no("Notificações", caixa=(400, 160, 680, 220), clicavel=False), FILTRO_DOS_VIDEOS,
                     ABA_NOTIFICACOES, ABA_EU],
    "notificacoes_videos": [_no("Notificações", caixa=(400, 160, 680, 220), clicavel=False), FILTRO_DOS_VIDEOS,
                            _no("Seu vídeo teve mais de 100 visualizações", caixa=(40, 1990, 1040, 2050),
                                clicavel=False), ABA_NOTIFICACOES, ABA_EU],
}
CAMINHO = {
    ("inicio", "Eu"): "eu", ("eu", "Criadores & Afiliados"): "criadores", ("criadores", "Conta"): "conta",
    ("conta", "Perfil em Shopee Vídeo"): "perfil", ("perfil", "Postar vídeo"): "camera",
    ("camera", "Biblioteca"): "galeria", ("galeria", "@ll_check"): "galeria_marcada",
    ("galeria_marcada", "@tv_pick_top_next"): "edicao", ("edicao", "@tv_compress"): "final",
    ("edicao", "Efeitos"): "efeitos", ("efeitos", "Giro"): "efeitos_com_giro", ("efeitos", "@iv_close"): "edicao",
    ("efeitos_com_giro", "@iv_done"): "edicao", ("efeitos_com_giro", "@iv_close"): "edicao",
    ("pagina_curta", VESTIDO): "pagina_completa", ("pagina_completa", "@buttonItemLike"): "pagina_curtida",
    ("pagina_curtida", "@buttonItemLiked"): "pagina_completa",
    ("final", "@ll_add_product_symbol"): "curtidas", ("curtidas", "Adicionar"): "janela",
    ("janela", "Feito"): "final", ("final", "@tv_drafts_box"): "live",
    ("inicio", "Notificações"): "notificacoes", ("notificacoes", "Lives, Vídeos e Afiliados"): "notificacoes_videos",
    ("notificacoes", "Eu"): "eu", ("notificacoes_videos", "Eu"): "eu",
}


class AppDeMentira:
    """O app da Shopee de mentira: cada toque leva à tela seguinte do CAMINHO."""

    def __init__(self):
        self.atual, self.legenda, self.com_produto = "inicio", "", False
        self.toques, self.teclas, self.comandos, self.enviados, self.prints = [], [], [], [], []
        self.clipboard, self.em_foco = None, False
        self.galeria = set()
        # A curtida do produto fica na conta: a página completa aberta de novo mostra o coração cheio.
        self.curtido = False

    def _nos(self):
        nos = TELAS[self.atual]
        # Como no Motorola: a leitura da tela traz ".." no lugar de cada emoji como o 👗.
        return _tela_final(robo.ps.como_o_android_le(self.legenda), self.com_produto) if nos == "final" else nos

    def dump_hierarchy(self):
        return _xml(*self._nos())

    def click(self, x, y):
        import postador_shopee_video as ps
        tocados = [el for el in ps.elementos(self.dump_hierarchy()) if ps._dentro((x, y), el["caixa"])]
        tocados.sort(key=lambda el: (el["caixa"][2] - el["caixa"][0]) * (el["caixa"][3] - el["caixa"][1]))
        nomes = [nome for el in tocados for nome in (el["texto"], "@" + el["id"] if el["id"] else "") if nome]
        self.toques.append(next((n for n in nomes if n.startswith("@")), nomes[0]) if nomes else (x, y))
        self.em_foco = "@et_caption" in nomes
        for nome in nomes:
            if (self.atual, nome) in CAMINHO:
                if nome == "Feito":
                    self.com_produto = True
                if nome in ("@buttonItemLike", "@buttonItemLiked"):
                    self.curtido = nome == "@buttonItemLike"
                self.atual = CAMINHO[(self.atual, nome)]
                if self.atual == "pagina_completa" and self.curtido:
                    self.atual = "pagina_curtida"
                return

    def __call__(self, **seletor):
        """O d(focused=True) do uiautomator2: aqui, nenhum campo em foco (cai no send_keys)."""
        return type("Campo", (), {"exists": False})()

    def send_keys(self, texto):
        self.legenda += texto

    def set_clipboard(self, texto, label=None):
        self.clipboard = texto

    def press(self, tecla, meta=None):
        if meta:
            if self.atual == "final" and not self.em_foco:
                # Como no Motorola: Ctrl+A na tela final, fora da edição da legenda, abre a
                # edição do texto e tira o Postar e o Rascunhos da tela.
                self.atual = "final_editando"
            elif tecla == robo.ps.TECLA_C and self.atual == "final":
                # Ctrl+C com o cursor no campo da legenda copia o texto como o app guardou.
                self.clipboard = self.legenda
            return
        self.teclas.append(tecla)
        self.atual = "inicio"

    def app_start(self, pacote, wait=False):
        self.comandos.append(["abrir"])

    def shell(self, partes):
        self.comandos.append(partes)
        if "android.intent.action.VIEW" in partes:
            self.atual = "pagina_curta"
        if partes[:2] == ["rm", "-f"]:
            self.galeria.discard(partes[2].rsplit("/", 1)[-1])
        if partes[0] == "ls":
            saida = "\n".join(sorted(self.galeria))
        else:
            saida = " ".join(nome for _, nome in self.enviados) if "content" in partes else ""
        return type("R", (), {"output": saida})()

    def push(self, origem, destino):
        self.enviados.append((origem, destino.rsplit("/", 1)[-1]))
        self.galeria.add(destino.rsplit("/", 1)[-1])

    def screenshot(self, caminho):
        self.prints.append(caminho)
        with open(caminho, "wb") as f:
            f.write(b"png")

    def window_size(self):
        return 1080, 2400

    def swipe(self, *pontos):
        self.toques.append("rolar")


def _fonte(monkeypatch, confere=True, violacao=False):
    os.makedirs("archive", exist_ok=True)
    with open("archive/vestido.mp4", "wb") as f:
        f.write(b"video")
    inserir("CREATE TABLE IF NOT EXISTS fila_autorais (id_unico TEXT, caminho_arquivo TEXT, legenda TEXT, data_captura TEXT)")
    inserir("INSERT INTO fila_autorais VALUES (?, ?, ?, ?)", "a1", "archive/vestido.mp4",
            f"Vestido 👗\n{LINK}", "2026-10-22 09:00:00")

    async def converter(link):
        return "https://shopee.com.br/product/1/2"

    async def produtos_do_link(link):
        return [{"nome": VESTIDO, "preco": 59.9, "comissao": 10.0}], link

    async def analisar(arquivo, prompt):
        return '{"confere": %s, "motivo": "vestido"}' % ("true" if confere else "false")

    async def textos(arquivo, nome):
        return {"violacao": violacao, "motivo": "marca" if violacao else "", "titulo": TITULO,
                "comentario": "Amei! #achadinhos"}

    monkeypatch.setattr(robo, "link_para_converter", converter)
    monkeypatch.setattr(robo.ps, "link_para_converter", converter)
    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)
    monkeypatch.setattr(robo.ps.api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(robo.assistente, "textos_do_video", textos)


def test_robo_nao_pega_de_volta_o_video_que_levou_ao_canal(monkeypatch):
    # O loop do vídeo do Rafael (30/10, 22:28): o vídeo que o robô postou vai ao Canal Afiliados
    # e volta por uma fila (o Viral, pelo Espião); o mesmo arquivo não vira rascunho de novo.
    _fonte(monkeypatch)
    with open("archive/outro.mp4", "wb") as f:
        f.write(b"outro video")
    inserir("INSERT INTO fila_autorais VALUES (?, ?, ?, ?)", "a2", "archive/outro.mp4",
            f"Vestido 👗\n{LINK}", "2026-10-22 08:00:00")
    assert robo.proximo_video(robo.ler_config())["id"] == "a1"
    robo.pedidos_do_canal.pedir(9, "archive/vestido.mp4", "https://sv.shopee.com.br/share-video/abc", [])
    assert robo.proximo_video(robo.ler_config())["id"] == "a2"
    assert robo.assistente.proximo_video("autorais")["id"] == "a2"


def test_rascunho_completo_curte_pelo_nome_e_salva_sem_tocar_em_postar(monkeypatch, avisos):
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    app = AppDeMentira()
    resultado = robo.rodada(d=app, agora=momento("2026-10-22 23:59"))
    assert resultado == "rascunho salvo"
    assert "@buttonItemLike" in app.toques and "Postar" not in app.toques and "@btn_post" not in app.toques
    assert "@tv_drafts_box" in app.toques and app.legenda == TITULO
    # Salvo o rascunho, o robô descurte o produto que curtiu para ele (pedido do Rafael, 24/10).
    assert app.toques.index("@tv_drafts_box") < app.toques.index("@buttonItemLiked") and not app.curtido
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["titulo"] == TITULO and rascunho["produtos"] == [VESTIDO] and rascunho["link"] == LINK
    # O tempo do rascunho salvo vai ao registro em faixas de 5 min, com quantos produtos: a
    # régua dos prazos da rodada, só números.
    tempo = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DO_TEMPO, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in tempo] == [("0 a 5 min", "1 produto(s)")]
    assert os.path.exists(rascunho["arquivo"]) and os.path.exists(rascunho["print"])
    assert app.enviados[0][1] == robo.nome_na_galeria(rascunho["id"])
    # Primeiro o aviso de qual vídeo e produto; no fim, o rascunho esperando aprovação.
    assert "começando um rascunho" in avisos[0] and VESTIDO in avisos[0]
    assert "Rascunhos do Robô 📝" in avisos[-1]
    # O assistente não pega o mesmo vídeo.
    assert robo.assistente.proximo_video("autorais") is None


# --- O Realçar e o Giro na edição (pedido do Rafael, vídeo de 31/10) ---

class ComAvisos(AppDeMentira):
    """O app avisa num toast o que o toque no Realçar fez; o realce pode já vir ligado."""

    def __init__(self, realce_ligado=False, giro_baixa_antes=0):
        super().__init__()
        self.atual, self.realce, self.toast, self.baixar = "edicao", realce_ligado, None, giro_baixa_antes

    def clear_toast(self):
        self.toast = None

    def last_toast(self):
        return self.toast

    def click(self, x, y):
        antes = self.atual
        super().click(x, y)
        if self.toques[-1] == "Realçar":
            self.realce = not self.realce
            self.toast = "Realce ativado" if self.realce else "Realce desativado"
        if self.toques[-1] == "Giro" and self.baixar:
            # Na primeira vez num celular, o toque só baixa o efeito.
            self.baixar -= 1
            self.atual = antes


def test_edicao_liga_o_realce_e_poe_o_giro_antes_do_proximo():
    app = ComAvisos()
    assert robo.efeitos_na_edicao(app) == robo.EFEITOS_COMPLETOS
    assert app.toques == ["Realçar", "Efeitos", "Giro", "@iv_done"] and app.realce and app.atual == "edicao"
    registro = robo.registro_processos.sequencia("shopee_video", "efeitos na edição", "2000-01-01 00:00:00")
    assert [r[2] for r in registro] == ["realce e giro"] and "realce: ligado; giro: posto" in registro[0][3]


def test_realce_que_ja_estava_ligado_e_giro_que_so_baixa_no_primeiro_toque():
    app = ComAvisos(realce_ligado=True, giro_baixa_antes=1)
    assert robo.efeitos_na_edicao(app) == robo.EFEITOS_COMPLETOS
    # O 1º toque desligou o realce (o app avisou): tocou de novo. O 1º Giro só baixou o efeito.
    assert app.toques == ["Realçar", "Realçar", "Efeitos", "Giro", "Giro", "@iv_done"] and app.realce


def test_efeito_que_nao_fica_nao_derruba_o_rascunho():
    app = ComAvisos(giro_baixa_antes=robo.VEZES_DO_GIRO)
    assert robo.efeitos_na_edicao(app) == "só o realce"
    # Sem o Desfazer, sai dos Efeitos pelo ✕, sem mudar nada, e a edição segue para o Próximo.
    assert app.toques[-1] == "@iv_close" and app.toques.count("Giro") == robo.VEZES_DO_GIRO and app.atual == "edicao"
    registro = robo.registro_processos.sequencia("shopee_video", "efeitos na edição", "2000-01-01 00:00:00")
    assert registro[-1][2] == "só o realce" and "não ficou depois de 3 toques" in registro[-1][3]


def test_edicao_sem_os_botoes_dos_efeitos_segue_sem_eles():
    app = AppDeMentira()
    app.atual = "galeria_marcada"
    TELAS["edicao_antiga"] = [_no("Próximo", "tv_compress", (860, 150, 1040, 210))]
    CAMINHO[("galeria_marcada", "@tv_pick_top_next")] = "edicao_antiga"
    try:
        robo.seguir(app, robo.CAMINHO_EDICAO[:1])
        assert robo.efeitos_na_edicao(app) == "nenhum" and app.atual == "edicao_antiga"
    finally:
        CAMINHO[("galeria_marcada", "@tv_pick_top_next")] = "edicao"
        del TELAS["edicao_antiga"]
    assert robo.passo_do_motivo("efeitos na edição: a edição do vídeo não voltou") == "efeitos na edição"


def test_rascunho_e_treino_passam_pelos_efeitos(monkeypatch, avisos):
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    app = AppDeMentira()
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.toques.index("Realçar") < app.toques.index("Giro") < app.toques.index("@tv_compress")
    app = AppDeMentira()
    assert robo.rodada(treino=True, d=app, agora=momento("2026-10-23 03:00")) == "treino: caminho OK"
    assert "Giro" in app.toques and "@tv_drafts_box" not in app.toques


def test_treino_avisa_quando_o_giro_nao_fica(monkeypatch, avisos):
    TELAS["efeitos_sem_giro"] = [_no(ident="iv_close", caixa=(40, 160, 110, 230)),
                                 _no(ident="iv_done", caixa=(970, 160, 1050, 230)), _no("Giro", caixa=(80, 2150, 180, 2200))]
    CAMINHO[("edicao", "Efeitos")] = "efeitos_sem_giro"
    CAMINHO[("efeitos_sem_giro", "@iv_close")] = "edicao"
    try:
        resultado = robo.rodada(treino=True, d=AppDeMentira(), agora=momento("2026-10-22 03:00"))
    finally:
        CAMINHO[("edicao", "Efeitos")] = "efeitos"
        del CAMINHO[("efeitos_sem_giro", "@iv_close")], TELAS["efeitos_sem_giro"]
    assert resultado.startswith("treino: mudou") and "efeitos na edição" in resultado


FOLHAS = "Folhas Prontas Facial Depilsam Ouro 10 Pares"


def _busca_de_comissao(monkeypatch, ofertas, confirma=(), preco=10.9):
    """
    A API (produto do link a 5%, pelo preço dado, e as ofertas da busca), o link curto e a
    IA de mentira; devolve o que foi pedido.
    """
    pedidos = {"busca": [], "ia": [], "capa": []}

    async def produtos_do_link(link):
        return [{"nome": FOLHAS, "preco": preco, "comissao": 5.0, "imagem": "https://cf.shopee.com.br/capa"}], link

    async def buscar(termo, limite=10, sort_type=2):
        pedidos["busca"].append((termo, limite, sort_type))
        return ofertas

    async def converter(link, etiqueta, avisar_falha=True):
        return link if "falha" in link else "https://s.shopee.com.br/" + link.rsplit("/", 1)[-1]

    def ia(video, vistos, avisar=True, capa=None):
        pedidos["ia"].append(video["link"])
        pedidos["capa"].append(capa)
        if video["link"] in confirma:
            vistos.append("é o mesmo pacote")
            return True, "confere"
        return False, "outro produto"

    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)
    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", buscar)
    monkeypatch.setattr(robo.api_shopee, "converter_link_shopee", converter)
    monkeypatch.setattr(robo.ps, "ia_confere_produto", ia)
    monkeypatch.setattr(robo.ps, "baixar_foto", lambda endereco: b"\xff\xd8capa" if endereco else None)
    return pedidos


def _oferta(nome, comissao, item, preco=10.9):
    return {"productName": nome, "commissionRate": str(comissao), "priceMin": str(preco),
            "productLink": f"https://shopee.com.br/product/9/{item}", "sales": 10}


def test_troca_pelo_mesmo_produto_que_paga_mais_conferido_pela_ia(monkeypatch):
    # Escolha do Rafael (25/10, P33): como a busca por foto com o filtro Comissão que ele faz,
    # o robô acha o mesmo produto de outra loja que paga mais e a IA confere com o vídeo.
    ofertas = [_oferta(FOLHAS, 0.05, 1),                                       # o do link: não paga mais
               _oferta("Óleo Finalizador Semi Di Lino Cristal", 0.20, 2),      # paga mais, mas é outro
               _oferta("Folhas Prontas Facial Depilsam Ouro 20 Folhas", 0.095, 3),
               _oferta("Promoção Folhas Prontas Depilsam Facial Ouro", 0.08, 4)]
    pedidos = _busca_de_comissao(monkeypatch, ofertas, confirma=("https://s.shopee.com.br/4",))
    troca = TROCAR({"link": LINK, "arquivo": "video.mp4"})
    assert pedidos["busca"] == [("Folhas Prontas Facial Depilsam Ouro 10", robo.OFERTAS_NA_BUSCA, 5)]
    # Da maior comissão para a menor, só os de nome parecido; a IA recusou o de 9,5%.
    assert pedidos["ia"] == ["https://s.shopee.com.br/3", "https://s.shopee.com.br/4"]
    assert troca["link"] == "https://s.shopee.com.br/4" and troca["comissao"] == 8.0 and troca["antes"] == 5.0
    assert troca["vistos"] == ["é o mesmo pacote"]
    # A IA confere cada um com a foto de capa do anúncio do post (P74).
    assert pedidos["capa"] == [b"\xff\xd8capa", b"\xff\xd8capa"]
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_COMISSAO, "2000-01-01 00:00:00")
    assert [r[2] for r in registro] == ["trocado"]


def test_troca_sem_a_foto_de_capa_do_post_fica_o_do_link(monkeypatch):
    # Escolha do Rafael (29/10, P74): só entra o anúncio com a mesma foto de capa; sem a capa
    # do post para comparar, não há troca, nem busca, nem IA.
    pedidos = _busca_de_comissao(monkeypatch, [_oferta(FOLHAS + " Kit", 0.2, 1)], confirma=("https://s.shopee.com.br/1",))
    monkeypatch.setattr(robo.ps, "baixar_foto", lambda endereco: None)
    assert TROCAR({"link": LINK, "arquivo": "video.mp4"}) is None
    assert pedidos["busca"] == [] and pedidos["ia"] == []
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_COMISSAO, "2000-01-01 00:00:00")
    assert [r[2] for r in registro] == ["mantido - sem a foto de capa do post"]


def test_troca_compara_os_reais_por_venda_com_preco_parecido(monkeypatch):
    # Escolha do Rafael (28/10, P58): "paga mais" é o que ele recebe numa venda, o preço vezes
    # a comissão, e só entra anúncio até 20% mais caro que o do link (R$ 10,90 a 5%: R$ 0,545).
    ofertas = [_oferta(FOLHAS + " Original", 0.08, 1, preco=6.0),        # mais %, menos reais: R$ 0,48
               _oferta(FOLHAS + " Kit", 0.06, 2, preco=12.5),            # menos %, mais reais: R$ 0,75
               _oferta(FOLHAS + " Envio Rápido", 0.07, 3, preco=11.0),   # R$ 0,77: o que paga mais
               _oferta(FOLHAS + " Atacado", 0.09, 4, preco=20.0),        # R$ 1,80, mas 83% mais caro
               _oferta(FOLHAS + " Sem Preço", 0.2, 5, preco=0)]          # sem o preço, não entra
    pedidos = _busca_de_comissao(monkeypatch, ofertas, confirma=("https://s.shopee.com.br/2",))
    troca = TROCAR({"link": LINK, "arquivo": "video.mp4"})
    # Do que paga mais por venda para o que paga menos; a IA recusou o de R$ 0,77.
    assert pedidos["ia"] == ["https://s.shopee.com.br/3", "https://s.shopee.com.br/2"]
    assert troca["link"] == "https://s.shopee.com.br/2" and troca["comissao"] == 6.0 and troca["preco"] == 12.5
    assert troca["valor"] == pytest.approx(0.75) and troca["valor_antes"] == pytest.approx(0.545)
    # Exatamente 20% mais caro ainda entra; um centavo a mais, não.
    teto = round(10.9 * 1.2, 2)
    dentro = robo.candidatos_de_mais_comissao({"nome": FOLHAS, "preco": 10.9, "comissao": 5.0},
                                              [_oferta(FOLHAS + " Kit", 0.06, 6, preco=teto),
                                               _oferta(FOLHAS + " Atacado", 0.06, 7, preco=teto + 0.01)])
    assert [c["link"].rsplit("/", 1)[-1] for c in dentro] == ["6"]


def test_sem_o_preco_do_link_fica_o_do_link(monkeypatch):
    # Sem o preço do produto do link não há com o que comparar: nem busca, nem IA.
    pedidos = _busca_de_comissao(monkeypatch, [_oferta(FOLHAS + " Kit", 0.2, 1)], preco=0.0)
    assert TROCAR({"link": LINK, "arquivo": "video.mp4"}) is None
    assert pedidos == {"busca": [], "ia": [], "capa": []}
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_COMISSAO, "2000-01-01 00:00:00")
    assert [r[2] for r in registro] == ["mantido - a API não disse o preço do produto do link"]


def test_sem_produto_que_pague_mais_fica_o_do_link(monkeypatch):
    pedidos = _busca_de_comissao(monkeypatch, [_oferta(FOLHAS, 0.04, 1), _oferta("Kit Óleo Finalizador", 0.2, 2)])
    assert TROCAR({"link": LINK, "arquivo": "video.mp4"}) is None and pedidos["ia"] == []
    # Nenhum confirmado pela IA (ou sem o link curto, que o celular abre): fica o do link.
    pedidos = _busca_de_comissao(monkeypatch, [_oferta(FOLHAS + " Kit", 0.09, "falha"), _oferta(FOLHAS, 0.08, 5)])
    assert TROCAR({"link": LINK, "arquivo": "video.mp4"}) is None
    assert pedidos["ia"] == ["https://s.shopee.com.br/5"]
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_COMISSAO, "2000-01-01 00:00:00")
    assert [r[2] for r in registro] == ["mantido - nenhum que pague mais por venda", "mantido - a IA não confirmou nenhum"]
    assert (robo.termo_da_busca("Kit [Oficial] Folhas (10 pares) Prontas ✨ Facial Depilsam Ouro Mel")
            == "Kit Folhas Prontas Facial Depilsam Ouro")

    # Um erro na busca nunca derruba o rascunho: fica o produto do link.
    async def quebrada(termo, limite=10, sort_type=2):
        raise ConnectionError("sem rede")
    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", quebrada)
    assert TROCAR({"link": LINK, "arquivo": "video.mp4"}) is None


def test_rascunho_vai_com_o_produto_que_paga_mais(monkeypatch, avisos):
    _fonte(monkeypatch)
    analises = []

    async def produtos_do_link(link):
        return [{"nome": VESTIDO, "preco": 59.9, "comissao": 15.0 if "mais" in link else 10.0}], link

    async def analisar(arquivo, prompt, imagens=None):
        analises.append(prompt)
        return '{"confere": true, "motivo": "vestido"}'

    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)
    monkeypatch.setattr(robo.ps.api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(robo, "trocar_pela_maior_comissao",
                        lambda video: {"nome": VESTIDO, "link": "https://s.shopee.com.br/mais", "comissao": 15.0,
                                       "preco": 59.9, "valor": 8.99, "antes": 10.0, "valor_antes": 5.99,
                                       "vistos": ["mesmo vestido", "mesmo vestido"]})
    monkeypatch.setattr(robo, "item_do_link", lambda link: "77" if "mais" in link else "")
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    app = AppDeMentira()
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["link"] == "https://s.shopee.com.br/mais" and rascunho["produtos"] == [VESTIDO]
    # O número do produto do post fica guardado para a medição das vendas (P73).
    assert rascunho["itens"] == [{"item": "77", "a_mais": False}]
    assert "Comissão: 15.0%, R$ 8,99 por venda (o produto do link pagava 10.0%, R$ 5,99" in avisos[0]
    # A IA já conferiu o produto novo com o vídeo na troca: a conferência não se repete.
    assert not any(p.startswith("Você confere um vídeo") for p in analises)
    assert json.loads(robo.pegar(rascunho["id"])["conferencia"]) == ["mesmo vestido", "mesmo vestido"]


def _editar_para_postar(chamadas, respostas=None, capa=None):
    """
    O editar_para_postar de mentira: guarda (vídeo, foto, produto, avisos) e grava o editado. Com a
    capa (bytes), ela vai para a figurinha do rascunho, como na capa com chamada ligada (P110).
    """
    def editar_para_postar(video, foto, destino, produto="", avisos=False, outras_fotos=(), figurinha=None):
        chamadas.append((video, foto, produto, avisos))
        motivo, como, detalhe = respostas.pop(0) if respostas else ("", robo.edicao_video.COM_LEGENDAS, "")
        if not motivo:
            with open(destino, "wb") as arquivo:
                arquivo.write(b"com os avisos" if avisos else b"editado")
        if capa and figurinha is not None and not motivo:
            figurinha["capa"] = capa
            como += robo.edicao_video.COM_A_CHAMADA_PARA_A_FIGURINHA
        return motivo, como + (robo.edicao_video.COM_OS_AVISOS if avisos else ""), detalhe
    return editar_para_postar


def test_rascunho_dos_autorais_vai_editado_com_a_edicao_ligada(monkeypatch, avisos):
    # Escolhas do Rafael (P37; 28/10, P51): nos vídeos dele (Autorais), com a edição ligada no
    # painel, o rascunho vai com o Editor 2: a foto do produto no começo, a miniatura, a seta e
    # as legendas: o nome do produto da API, a vantagem e a chamada da IA (sem o preço, P80).
    _fonte(monkeypatch)
    editados = []

    async def analisar(arquivo, prompt, imagens=None):
        return '{"confere": true, "motivo": "vestido"}'

    # A mesma foto do anúncio vai à conferência da IA (com a foto) e à edição.
    monkeypatch.setattr(robo.ps, "anuncio_do_produto",
                        lambda video: {"foto": b"foto do anuncio", "nome": VESTIDO, "preco": 59.9})
    monkeypatch.setattr(robo.ps.api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(robo.edicao_video, "editar_para_postar", _editar_para_postar(editados))
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24, edicao_ligada=True)
    assert robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    rascunho = robo.esperando_aprovacao()[0]
    assert open(rascunho["arquivo"], "rb").read() == b"editado"
    assert editados == [(os.path.abspath("archive/vestido.mp4"), b"foto do anuncio", VESTIDO, False)]
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DA_EDICAO) == (robo.edicao_video.COM_LEGENDAS, 1)
    # Sem a capa com chamada, o rascunho fica no grupo de antes na medição (P76).
    assert not rascunho["chamada"]


def test_rascunho_com_a_capa_com_chamada_fica_marcado_para_a_medicao(monkeypatch, avisos):
    # Escolha do Rafael (29/10, P76): a medição compara os vídeos com a chamada com os de antes. A
    # capa com a frase vai pela figurinha, por último, depois do título e dos produtos (P110): o
    # rascunho só fica marcado quando ela ficou.
    _fonte(monkeypatch)

    async def analisar(arquivo, prompt, imagens=None):
        return '{"confere": true, "motivo": "vestido"}'

    monkeypatch.setattr(robo.ps, "anuncio_do_produto",
                        lambda video: {"foto": b"foto do anuncio", "nome": VESTIDO, "preco": 59.9})
    monkeypatch.setattr(robo.ps.api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(robo.edicao_video, "editar_para_postar", _editar_para_postar([], capa=b"a capa"))
    postas = []

    def capa_pela_figurinha(d, capa, ao_falhar=None, prazo=None):
        # O rascunho dá à capa o prazo para começar outra tentativa (MINUTOS_PARA_A_CAPA).
        assert prazo > time.monotonic()
        postas.append((capa, list(d.toques)))
        return len(postas) == 1, "a faixa do tamanho do desenho (1 ajuste(s))" if len(postas) == 1 else "o motivo"

    monkeypatch.setattr(robo, "capa_pela_figurinha", capa_pela_figurinha)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24, edicao_ligada=True)
    assert robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert robo.esperando_aprovacao()[0]["chamada"] == "1"
    capa, antes = postas[0]
    assert capa == b"a capa" and "@tv_right" in antes and "Feito" in antes
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DA_CAPA) == ("posta", 1)


def test_capa_pela_figurinha_que_nao_deu_certo_guarda_o_caso_e_o_rascunho_segue(monkeypatch, avisos):
    # Na 1ª capa pela figurinha de verdade (31/10), a faixa parou menor que o desenho e não havia
    # como ver a tela: o caso da capa (o print da tela da capa, o vídeo e o rascunho) fica para
    # o checkup do Claude, e o rascunho segue com a capa de sempre (DECISOES.md, Trabalho com o
    # Claude: o que dificulta a análise vira registro).
    import json
    _fonte(monkeypatch)

    async def analisar(arquivo, prompt, imagens=None):
        return '{"confere": true, "motivo": "vestido"}'

    monkeypatch.setattr(robo.ps, "anuncio_do_produto",
                        lambda video: {"foto": b"foto do anuncio", "nome": VESTIDO, "preco": 59.9})
    monkeypatch.setattr(robo.ps.api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(robo.edicao_video, "editar_para_postar", _editar_para_postar([], capa=b"a capa"))
    motivo = "a faixa não ficou do tamanho do desenho; alto x largura e o meio da faixa a cada medida"

    def capa_pela_figurinha(d, capa, ao_falhar=None, prazo=None):
        if ao_falhar:
            ao_falhar(motivo)
        return False, motivo

    monkeypatch.setattr(robo, "capa_pela_figurinha", capa_pela_figurinha)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24, edicao_ligada=True)
    assert robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    rascunho = robo.esperando_aprovacao()[0]
    assert not rascunho["chamada"]
    (caso,) = robo.casos_robo.casos()
    with open(os.path.join(robo.casos_robo.PASTA, caso, "caso.json"), encoding="utf-8") as f:
        dados = json.load(f)
    assert (dados["acao"], dados["resultado"], dados["passo"], dados["motivo"]) == (
        "capa", "de fora", "capa pela figurinha", motivo)
    assert dados["rascunho"]["id"] == rascunho["id"] and dados["video"]["link"]
    assert "app" in dados


def test_produto_recusado_pela_ia_deixa_no_caso_o_produto_e_o_que_ela_viu(monkeypatch, avisos):
    # O caso do checkup do Claude tem de dizer qual era o produto do link e o que a IA viu
    # no vídeo, para saber se ela acertou ao pular.
    import json
    _fonte(monkeypatch)

    async def analisar(arquivo, prompt, imagens=None):
        return '{"confere": false, "motivo": "o vídeo mostra uma luminária, não um vestido"}'

    monkeypatch.setattr(robo.ps.api_gemini, "analisar_video_gemini", analisar)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    resultado = robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59"))
    assert "a IA viu outro produto no vídeo" in resultado and not robo.esperando_aprovacao()
    casos = robo.casos_robo.casos()
    with open(os.path.join(robo.casos_robo.PASTA, casos[-1], "caso.json"), encoding="utf-8") as f:
        caso = json.load(f)
    assert caso["resultado"] == "pulado" and caso["rascunho"]["produtos"] == [VESTIDO]
    assert json.loads(caso["rascunho"]["conferencia"]) == ["o vídeo mostra uma luminária, não um vestido"]


def test_rascunho_sem_edicao_nao_sai_com_a_edicao_ligada(monkeypatch, avisos):
    # Pedido do Rafael (25/10): na Shopee Vídeo, só vídeo editado. Sem a foto do anúncio, o
    # rascunho não sai e o vídeo fica de lado, sem tocar no celular.
    _fonte(monkeypatch)

    async def analisar(arquivo, prompt, imagens=None):
        return '{"confere": true, "motivo": "vestido"}'

    monkeypatch.setattr(robo.ps, "foto_do_produto", lambda video: None)
    monkeypatch.setattr(robo.ps.api_gemini, "analisar_video_gemini", analisar)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24, edicao_ligada=True)
    app = AppDeMentira()
    resultado = robo.rodada(d=app, agora=momento("2026-10-22 23:59"))
    assert robo.MOTIVO_SEM_EDICAO in resultado and not robo.esperando_aprovacao()
    assert consultar("SELECT resultado FROM shopee_video_tentativas ORDER BY rowid DESC") == ("pulado",)


def test_sem_edicao_desligada_ou_quando_falha(monkeypatch, tmp_path):
    original, copia = str(tmp_path / "original.mp4"), str(tmp_path / "copia.mp4")
    with open(original, "wb") as arquivo:
        arquivo.write(b"original")
    respostas = [("o ffmpeg falhou", robo.edicao_video.SO_COM_O_EDITOR_1, ""),
                 ("", robo.edicao_video.COM_LEGENDAS, "")]
    chamadas = []
    monkeypatch.setattr(robo.ps, "anuncio_do_produto", lambda video: {"foto": b"foto", "nome": VESTIDO, "preco": 59.9})
    monkeypatch.setattr(robo.edicao_video, "editar_para_postar", _editar_para_postar(chamadas, respostas))
    video = {"arquivo": original, "link": LINK}
    # Desligada: nenhum vídeo é editado.
    robo.copiar_para_o_rascunho(video, "autorais", copia)
    assert open(copia, "rb").read() == b"original" and not chamadas
    ativar(edicao_ligada=True)
    # Com a edição ligada, só vídeo editado vai (pedido do Rafael, 25/10): a edição que não
    # sai deixa o vídeo de lado. O ffmpeg que falhou deixa o vídeo tentar de novo depois.
    os.remove(copia)
    with pytest.raises(robo.Parada) as parada:
        robo.copiar_para_o_rascunho(video, "viral", copia)
    assert parada.value.motivo.startswith(robo.MOTIVO_SEM_EDICAO) and not parada.value.do_video
    assert [c[0] for c in chamadas] == [original] and not os.path.exists(copia)
    assert consultar("SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DA_EDICAO) == ("vídeo de lado", "o ffmpeg falhou", 0)
    # Todos os vídeos do Rafael são autorais: o do Viral também vai editado.
    robo.copiar_para_o_rascunho(video, "viral", copia)
    assert open(copia, "rb").read() == b"editado"


def test_sem_o_editor_2_o_rascunho_vai_com_o_editor_1_e_o_registro_anota(monkeypatch, tmp_path):
    # Escolha do Rafael (28/10, P51): se o Editor 2 não sai, o vídeo vai com o Editor 1, sem
    # legendas, e o rascunho não se perde; o registro anota (como falha, para o checkup ver).
    original, copia = str(tmp_path / "original.mp4"), str(tmp_path / "copia.mp4")
    with open(original, "wb") as arquivo:
        arquivo.write(b"original")
    chamadas = []
    monkeypatch.setattr(robo.ps, "anuncio_do_produto", lambda video: {"foto": b"foto", "nome": VESTIDO, "preco": 59.9})
    monkeypatch.setattr(robo.edicao_video, "editar_para_postar", _editar_para_postar(chamadas, [
        ("", robo.edicao_video.SO_COM_O_EDITOR_1, "o Editor 2 não saiu: o ffmpeg falhou")]))
    ativar(edicao_ligada=True)
    robo.copiar_para_o_rascunho({"arquivo": original, "link": LINK}, "viral", copia)
    assert open(copia, "rb").read() == b"editado"
    assert consultar("SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DA_EDICAO) == (robo.edicao_video.SO_COM_O_EDITOR_1,
                                                  "o Editor 2 não saiu: o ffmpeg falhou", 0)



def test_bebida_alcoolica_vai_com_a_capa_dos_avisos_e_sem_edicao_fica_de_lado(monkeypatch, tmp_path):
    # Escolha do Rafael (26/10, P43): o robô põe os avisos da Shopee na capa do vídeo. É o
    # caminho que volta quando a página oficial trouxer a regra nova (P111, em espera).
    original, copia = str(tmp_path / "original.mp4"), str(tmp_path / "copia.mp4")
    with open(original, "wb") as arquivo:
        arquivo.write(b"original")
    chamadas = []
    monkeypatch.setattr(robo.ps, "anuncio_do_produto", lambda video: {"foto": b"foto", "nome": "Vinho", "preco": 39.9})
    monkeypatch.setattr(robo.edicao_video, "editar_para_postar", _editar_para_postar(chamadas))
    video = {"arquivo": original, "link": LINK}
    # Sem a edição não há capa com os avisos: o vídeo fica de lado e não volta.
    with pytest.raises(robo.Parada) as parada:
        robo.copiar_para_o_rascunho(video, "viral", copia, alcool=True)
    assert parada.value.motivo == robo.MOTIVO_SEM_AVISOS and parada.value.do_video
    assert not chamadas and not os.path.exists(copia)
    ativar(edicao_ligada=True)
    robo.copiar_para_o_rascunho(video, "viral", copia, alcool=True)
    assert [c[-1] for c in chamadas] == [True] and open(copia, "rb").read() == b"com os avisos"
    assert consultar("SELECT resultado FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DA_EDICAO) == (robo.edicao_video.COM_LEGENDAS + robo.edicao_video.COM_OS_AVISOS,)

def _ate_os_textos_da_ia(monkeypatch, alcool):
    """O rascunho de link de produto até a conferência dos textos da IA, sem o celular."""
    monkeypatch.setattr(robo.ps, "nome_do_produto", lambda video: "Vinho Tinto Seco 750ml")

    async def produtos(link):
        return [{"nome": "Vinho Tinto Seco 750ml", "preco": 39.9, "comissao": 8.0}], link
    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos)
    monkeypatch.setattr(robo.ps, "ia_confere_produto", lambda video, vistos: (True, "confere"))
    monkeypatch.setattr(robo, "item_do_link", lambda link: "123")
    monkeypatch.setattr(robo, "_textos_da_ia", lambda video, nomes=None: {
        "violacao": False, "motivo": "", "bebida_alcoolica": alcool, "titulo": "Vinho Tinto 🍷 #vinho",
        "comentario": "c"})


def test_bebida_alcoolica_em_espera_fica_de_lado_antes_dos_produtos_a_mais(monkeypatch, avisos):
    # Escolha do Rafael (31/10, P111): a página oficial das diretrizes da Shopee Vídeo ainda
    # proíbe divulgar bebida alcoólica. Até ela trazer a regra nova, o vídeo de bebida alcoólica
    # fica de lado (não volta) antes dos produtos a mais, da edição e do celular.
    _ate_os_textos_da_ia(monkeypatch, alcool=True)
    seguiu = []
    monkeypatch.setattr(robo, "espacos_livres", lambda *a, **k: seguiu.append("espaços livres") or [])
    monkeypatch.setattr(robo, "copiar_para_o_rascunho", lambda *a, **k: seguiu.append("cópia") or "")
    with pytest.raises(robo.Parada) as parada:
        robo._preparar(None, robo.criar("video:1"), {"id": "video:1", "arquivo": "v.mp4", "link": LINK}, "viral")
    assert parada.value.motivo == robo.assistente.MOTIVO_BEBIDA_EM_ESPERA and parada.value.do_video
    assert not seguiu
    assert robo.passo_do_motivo(parada.value.motivo) == "bebida alcoólica em espera"


def test_sem_a_espera_a_bebida_alcoolica_segue_para_os_avisos_da_p43(monkeypatch, avisos):
    # Quando a página trouxer a regra nova, BEBIDA_EM_ESPERA volta a False e a bebida segue o
    # caminho da P43 (os avisos na capa e no título); o vídeo que não é bebida segue sempre.
    def parar(*a, **k):
        raise RuntimeError("seguiu para os produtos a mais")
    monkeypatch.setattr(robo, "espacos_livres", parar)
    for alcool, espera in ((True, False), (False, True)):
        monkeypatch.setattr(robo.assistente, "BEBIDA_EM_ESPERA", espera)
        _ate_os_textos_da_ia(monkeypatch, alcool=alcool)
        with pytest.raises(RuntimeError, match="seguiu para os produtos a mais"):
            robo._preparar(None, robo.criar(f"video:{alcool}"),
                           {"id": f"video:{alcool}", "arquivo": "v.mp4", "link": LINK}, "viral")


def test_ver_produtos_vai_editado_com_a_foto_do_1o_produto_anexado(monkeypatch, tmp_path):
    # Escolha do Rafael (25/10, P39): no vídeo de Ver Produtos (vários produtos), a foto da
    # edição é a do anúncio do 1º produto anexado, achado na API pelo nome.
    original, copia = str(tmp_path / "original.mp4"), str(tmp_path / "copia.mp4")
    with open(original, "wb") as arquivo:
        arquivo.write(b"original")
    fotos, buscas = [], []

    def editar_para_postar(video, foto, destino, produto="", avisos=False, outras_fotos=(), figurinha=None):
        fotos.append((foto, produto))
        if not foto:
            return "a foto do anúncio não veio", robo.edicao_video.SO_COM_O_EDITOR_1, ""
        with open(destino, "wb") as arquivo:
            arquivo.write(b"editado")
        return "", robo.edicao_video.COM_LEGENDAS, ""

    async def buscar(termo, limite=10, sort_type=2):
        buscas.append((termo, sort_type))
        return [{"productName": "Capinha Transparente Celular", "imageUrl": "https://cf.shopee.com.br/outra",
                 "priceMin": "9.90"},
                {"productName": "Vestido Infantil Estampado Gatinho Verão Menina",
                 "imageUrl": "https://cf.shopee.com.br/vestido", "priceMin": "45.50"}]

    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", buscar)
    monkeypatch.setattr(robo.ps, "baixar_foto", lambda endereco: b"foto de " + endereco.encode())
    monkeypatch.setattr(robo.ps, "anuncio_do_produto", lambda video: pytest.fail("o link é de vídeo, não de produto"))
    monkeypatch.setattr(robo.edicao_video, "editar_para_postar", editar_para_postar)
    ativar(edicao_ligada=True)
    video = {"arquivo": original, "link": LINK, "de_video": True}
    robo.copiar_para_o_rascunho(video, "viral", copia, ["Vestido Infantil Estampado Gatinho Verão Menina", "Laço"])
    # A foto é a do anúncio achado; o nome (das legendas do Editor 2), o do app.
    assert fotos == [(b"foto de https://cf.shopee.com.br/vestido", "Vestido Infantil Estampado Gatinho Verão Menina")]
    assert open(copia, "rb").read() == b"editado"
    # Busca pelo nome, por relevância (1), com as primeiras palavras.
    assert buscas == [("Vestido Infantil Estampado Gatinho Verão Menina", 1)]
    # Nenhuma oferta com o nome parecido o bastante: sem a foto não há edição, e o vídeo fica
    # de lado de vez (só vídeo editado vai).
    os.remove(copia)
    with pytest.raises(robo.Parada) as parada:
        robo.copiar_para_o_rascunho(video, "viral", copia, ["Tênis Esportivo Corrida Masculino"])
    assert fotos[-1][0] is None and not os.path.exists(copia) and parada.value.do_video
    assert consultar("SELECT resultado, detalhe FROM registro_processos WHERE processo = ? ORDER BY rowid DESC",
                     robo.PROCESSO_DA_EDICAO) == ("vídeo de lado", "a foto do anúncio não veio")


NOME_NO_APP = "Vestidinho Gatinho Estampado Menina Infantil Verão"


def test_produto_com_outro_nome_no_app_vai_pelo_1o_da_lista_com_a_foto_conferida(monkeypatch, avisos):
    # 24/10/2026: o produto curtido estava em 1º em Minhas Curtidas, com um nome sem nenhuma
    # palavra do nome da API, e o rascunho parava. Escolha do Rafael (P18): o 1º da lista, pela
    # foto conferida pela IA; a tela final e o rascunho ficam com o nome que o app mostra.
    import sys
    from PIL import Image
    _fonte(monkeypatch)
    fotos = []

    async def analisar(arquivo, prompt, imagens=None):
        fotos.extend(imagens or [])
        return '{"confere": true, "motivo": "vestido"}'

    monkeypatch.setattr(robo.ps.api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setitem(TELAS, "curtidas", [n.replace(VESTIDO, NOME_NO_APP) for n in TELAS["curtidas"]])
    monkeypatch.setitem(TELAS, "janela", [n.replace(VESTIDO, NOME_NO_APP) for n in TELAS["janela"]])
    modulo = sys.modules[__name__]
    tela_final = modulo._tela_final
    monkeypatch.setattr(modulo, "_tela_final", lambda legenda="", produto=False: [
        n.replace(VESTIDO, NOME_NO_APP) for n in tela_final(legenda, produto)])
    print_da_tela = AppDeMentira.screenshot
    monkeypatch.setattr(AppDeMentira, "screenshot", lambda self, caminho=None: (
        Image.new("RGB", (1080, 2400)) if caminho is None else print_da_tela(self, caminho)))
    monkeypatch.setattr(robo.ps.time, "sleep", lambda s: None)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    assert robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert fotos and fotos[0][1] == "image/png"
    assert robo.esperando_aprovacao()[0]["produtos"] == [NOME_NO_APP]


def _titulo_vazio_e_depois(monkeypatch, respostas):
    """A IA do título: None (resposta vazia do Google, motivo no ULTIMO_ERRO_IA) ou o título."""
    vazia = ("Todos os modelos da cascata falharam → gemini-x: VAZIO (finish_reason=<FinishReason.RECITATION: "
             "'RECITATION'>)")

    async def textos(arquivo, nome):
        if respostas.pop(0) is None:
            robo.ps.api_gemini.ULTIMO_ERRO_IA = vazia
            return None
        return {"violacao": False, "motivo": "", "titulo": TITULO, "comentario": "Amei! #achadinhos"}

    monkeypatch.setattr(robo.assistente, "textos_do_video", textos)


def test_preparar_1_agora_fica_no_registro(monkeypatch, avisos):
    # O rascunho pedido no botão vale a qualquer hora; o registro guarda o pedido, para o
    # checkup não o contar como preparo do plano no Horário das Interações (31/10, 20:32).
    from conftest import consultar
    # Os outros passos do rascunho anotam com o relógio de verdade: o registro de 22/10 não sai.
    monkeypatch.setattr(robo.registro_processos, "DIAS_DO_REGISTRO", 3650)
    _fonte(monkeypatch)
    assert robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert consultar("SELECT momento, resultado FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DO_BOTAO) == ("2026-10-22 23:59:00", "pedido")


def test_titulo_vazio_da_ia_tenta_de_novo_e_anota_o_motivo(monkeypatch, avisos):
    # 24/10/2026 (Preparar 1 Agora, 12:48): a IA conferiu o produto, mas voltou vazia no
    # título em todos os modelos, e o robô desistiu na hora. A resposta vazia do Google muda
    # de uma tentativa para outra: o robô tenta mais uma vez depois de uma pausa.
    from conftest import consultar
    _fonte(monkeypatch)
    _titulo_vazio_e_depois(monkeypatch, [None, "ok"])
    assert robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert consultar("SELECT resultado, detalhe FROM registro_processos WHERE processo = 'título da IA' "
                     "AND ok = 0") == ("sem título", "resposta vazia (RECITATION)")
    assert consultar("SELECT resultado FROM registro_processos WHERE processo = 'título da IA' AND ok = 1") == (
        "veio na nova tentativa",)


def test_titulo_vazio_duas_vezes_para_com_o_motivo_e_o_passo(monkeypatch, avisos):
    _fonte(monkeypatch)
    _titulo_vazio_e_depois(monkeypatch, [None, None])
    resultado = robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59"))
    assert "a IA não devolveu o título (resposta vazia (RECITATION))" in resultado
    assert robo.passo_do_motivo(resultado) == "título da IA"


def test_bloqueio_do_google_pelo_conteudo_pula_o_video_sem_tentar_de_novo(monkeypatch, avisos):
    # 24/10/2026: as duas tentativas voltaram PROHIBITED_CONTENT, bloqueio que não muda para o
    # mesmo vídeo: ele fica de lado na hora, e o horário passa ao próximo vídeo.
    _fonte(monkeypatch)
    chamadas = []

    async def textos(arquivo, nome):
        chamadas.append(arquivo)
        robo.ps.api_gemini.ULTIMO_ERRO_IA = ("Todos os modelos da cascata falharam → gemini-x: VAZIO "
                                             "(block_reason=<BlockedReason.PROHIBITED_CONTENT: 'PROHIBITED_CONTENT'>)")
        return None

    monkeypatch.setattr(robo.assistente, "textos_do_video", textos)
    resultado = robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59"))
    assert "o Google bloqueia o conteúdo deste vídeo" in resultado and len(chamadas) == 1
    pulado = robo.listar("pulado")[0]
    assert "PROHIBITED_CONTENT" in pulado["motivo"] and robo.passo_do_motivo(pulado["motivo"]) == "título da IA"


def test_titulo_que_veio_com_as_regras_em_palavras_leves_fica_no_registro(monkeypatch, avisos):
    # Escolha do Rafael (P28): o assistente refaz o pedido recusado com as regras em palavras
    # leves; o checkup conta quantos títulos vieram assim.
    from conftest import consultar
    _fonte(monkeypatch)

    async def textos(arquivo, nome):
        return {"violacao": False, "motivo": "", "titulo": TITULO, "comentario": "Amei! #achadinhos",
                "regras_leves": True}

    monkeypatch.setattr(robo.assistente, "textos_do_video", textos)
    assert robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = 'título da IA'") == (
        "veio com as regras em palavras leves", 1)


def test_video_recusado_pelo_google_chega_no_privado_uma_vez_com_o_que_ele_disse(monkeypatch, avisos, tmp_path):
    # Escolha do Rafael (P29): cada vídeo que o Google recusa chega no privado na hora, com
    # o vídeo, o produto, o que o Google disse e o que deu o pedido em palavras leves.
    _fonte(monkeypatch)
    recusa = {"codigos": ["PROHIBITED_CONTENT"], "categorias": [("HARM_CATEGORY_SEXUALLY_EXPLICIT", "MEDIUM")]}

    async def passou_com_leves(arquivo, nome):
        robo.assistente.ULTIMA_RECUSA = {**recusa, "leves": "passou"}
        return {"violacao": False, "motivo": "", "titulo": TITULO, "comentario": "Amei! #achadinhos",
                "regras_leves": True}

    monkeypatch.setattr(robo.assistente, "textos_do_video", passou_com_leves)
    assert robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    videos = [legenda for tipo, legenda in (a for a in avisos if isinstance(a, tuple)) if tipo == "video"]
    assert len(videos) == 1 and VESTIDO in videos[0] and "conteúdo proibido" in videos[0]
    assert "sexual (médio)" in videos[0] and "passou ✅" in videos[0]

    # Recusado de novo: o vídeo é pulado, e o aviso diz isso (uma vez só).
    avisos.clear()
    inserir("INSERT INTO fila_autorais VALUES (?, ?, ?, ?)", "a2", "archive/vestido.mp4",
            f"Vestido 👗\n{LINK}", "2026-10-22 09:30:00")

    async def recusado(arquivo, nome):
        robo.ps.api_gemini.ULTIMO_ERRO_IA = ("Todos os modelos da cascata falharam → gemini-x: VAZIO "
                                             "(block_reason=<BlockedReason.PROHIBITED_CONTENT: 'PROHIBITED_CONTENT'>)")
        robo.assistente.ULTIMA_RECUSA = {**recusa, "leves": "recusado de novo"}
        return None

    monkeypatch.setattr(robo.assistente, "textos_do_video", recusado)
    resultado = robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-23 00:30"))
    assert "o Google bloqueia o conteúdo deste vídeo" in resultado
    videos = [a[1] for a in avisos if isinstance(a, tuple) and a[0] == "video"]
    assert len(videos) == 1 and "recusado de novo ❌" in videos[0]


def test_ia_que_nao_confirma_pula_o_video_sem_tocar_no_celular(monkeypatch, avisos):
    _fonte(monkeypatch, confere=False)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    resultado = robo.rodada(d=Intocavel(), agora=momento("2026-10-22 23:59"))
    assert "parado" in resultado and robo.esperando_aprovacao() == []
    assert robo.listar("pulado")[0]["id_video"] == "a1"
    # O robô não volta a esse vídeo; o assistente pode mandar.
    assert robo.proximo_video(robo.ler_config()) is None
    assert robo.assistente.proximo_video("autorais")["id"] == "a1"


def test_video_com_problema_proprio_passa_ao_proximo_e_sem_video_o_horario_acaba(monkeypatch, avisos):
    # Escolha do Rafael (23/10): o horário das 01:03 falhou e o dia ficou sem aquele
    # rascunho; o rascunho do plano tenta de novo. O vídeo pulado (problema dele) passa
    # direto ao próximo; sem mais vídeo na fonte, as tentativas do horário acabam.
    _fonte(monkeypatch, confere=False)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    agora = momento("2026-10-22 23:59")
    resultados = [robo.rodada(d=Intocavel(), agora=agora) for _ in range(5)]
    assert "parado" in resultados[0]                         # o horário do plano: vídeo pulado
    assert all(r.startswith("nenhum vídeo") for r in resultados[1:4])   # as 3 tentativas do vídeo 2
    assert resultados[4] == "nada a fazer agora"              # acabaram as tentativas


def test_mesmo_video_3_vezes_depois_outro_ate_3_videos_e_espera_o_proximo_horario(monkeypatch, avisos):
    # Pedido do Rafael (23/10): tenta o mesmo vídeo; sem dar certo, outro vídeo, para o dia
    # ter os rascunhos do plano; depois de 3 vídeos, para até o próximo horário.
    _fonte(monkeypatch)
    for numero in range(2, 5):
        inserir("INSERT INTO fila_autorais VALUES (?, ?, ?, ?)", f"a{numero}", "archive/vestido.mp4",
                f"Vestido 👗\n{LINK}", f"2026-10-22 0{numero}:00:00")
    tentados = []

    def falha(d, ident, video, fonte, agora=None, curtidos=None, celular=None):
        tentados.append(video["id"])
        raise robo.Parada("não achei o botão Rascunhos")

    monkeypatch.setattr(robo, "_preparar", falha)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    agora = momento("2026-10-22 23:59")
    resultados = [robo.rodada(d=Intocavel(), agora=agora) for _ in range(10)]
    assert all("parado" in r for r in resultados[:9]) and resultados[9] == "nada a fazer agora"
    primeiro, segundo, terceiro = tentados[0], tentados[3], tentados[6]
    assert tentados == [primeiro] * 3 + [segundo] * 3 + [terceiro] * 3
    assert len({primeiro, segundo, terceiro}) == 3
    finais = [a for a in avisos if isinstance(a, str) and "o rascunho não saiu" in a]
    assert "tentativa 2 de 3 do vídeo 1 de 3" in finais[0] and "com outro vídeo: vídeo 2 de 3" in finais[2]
    assert "acabaram" in finais[8] and len(finais) == 9
    # O vídeo fica de lado só naquele dia: no dia seguinte ele pode voltar.
    assert robo.estado_do_dia(robo.ler_config(), momento("2026-10-23 08:00")).get("evitar") is None
    assert robo.proximo_video(robo.ler_config())["id"] in {primeiro, segundo, terceiro, "a1", "a2", "a3", "a4"}


def test_rascunho_do_plano_que_nao_saiu_avisa_onde_parou_e_quando_tenta_de_novo(monkeypatch, avisos):
    # Escolha do Rafael (23/10): o "começando um rascunho" sempre tem um fim no privado.
    _fonte(monkeypatch, confere=False)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    agora = momento("2026-10-22 23:59")
    robo.rodada(d=Intocavel(), agora=agora)
    aviso = next(a for a in avisos if isinstance(a, str) and "o rascunho não saiu" in a)
    assert "Parou em: conferência da IA" in aviso and "com outro vídeo: vídeo 2 de 3" in aviso
    assert "Histórico do Robô 📋" in aviso
    for _ in range(3):
        robo.rodada(d=Intocavel(), agora=agora)
    finais = [a for a in avisos if isinstance(a, str) and "o rascunho não saiu" in a]
    assert "tentativa 2 de 3 do vídeo 2 de 3" in finais[1] and "tentativa 3 de 3" in finais[2]
    assert "acabaram" in finais[3]
    # O histórico guarda cada tentativa, e o diagnóstico conta resultado e passo sem nomes.
    lista = robo.tentativas_desde("2026-10-22 00:00:00")
    assert [(t["resultado"], t["passo"]) for t in lista] == [
        ("sem vídeo", "vídeo da fonte")] * 3 + [("pulado", "conferência da IA")]
    assert "Parou em: vídeo da fonte" in finais[3]


def test_preparar_1_agora_que_falha_nao_repete_o_aviso(monkeypatch, avisos):
    _fonte(monkeypatch, confere=False)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True})
    robo.rodada(preparar=True, d=Intocavel(), agora=momento("2026-10-22 23:59"))
    assert not any(isinstance(a, str) and "o rascunho não saiu" in a for a in avisos)
    assert "não preparei o rascunho que você pediu" in avisos[-1]


def test_rascunho_salvo_entra_no_historico_com_o_produto(monkeypatch, avisos):
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    assert robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    ultima = robo.tentativas_desde("2026-10-22 00:00:00")[0]
    assert (ultima["acao"], ultima["resultado"], ultima["produto"]) == ("rascunho", "salvo", VESTIDO)
    assert "✅ 1 salvo" in robo.texto_historico(momento("2026-10-22 23:59"))


def test_passo_do_motivo():
    assert robo.passo_do_motivo(robo.SEM_OFERTA) == "oferta de afiliado"
    assert robo.passo_do_motivo("a IA viu outro produto no vídeo (1ª vez): parado") == "conferência da IA"
    assert robo.passo_do_motivo("a IA viu violação das diretrizes") == "diretrizes da Shopee"
    assert robo.passo_do_motivo("toquei no coração, mas o produto não ficou curtido") == "curtir o produto"
    assert robo.passo_do_motivo("o título não ficou na legenda (pela cópia: ...)") == "escrever o título"
    assert robo.passo_do_motivo("toquei em Rascunhos, mas o app continuou na tela final") == "salvar em Rascunhos"
    assert robo.passo_do_motivo("o rascunho aberto não tem o título do aprovado") == "abrir o rascunho"
    assert robo.passo_do_motivo("não consegui voltar até Eu") == "navegar no app"
    # A Saúde do Vídeo: o checkup diz onde parou (não "outro").
    assert robo.passo_do_motivo("o Centro do criador não mostrou a Saúde do Vídeo") == "achar a Saúde no Centro do criador"
    assert robo.passo_do_motivo("não achei Centro do criador na tela") == "achar a Saúde no Centro do criador"
    assert robo.passo_do_motivo("a Saúde do Vídeo não abriu") == "abrir a Saúde do Vídeo"
    assert robo.passo_do_motivo("toquei no Rótulo de IA, mas ele não ficou ligado") == "rótulo de IA"
    assert robo.passo_do_motivo(f"{robo.MOTIVO_SEM_EDICAO} (a foto do anúncio não veio)") == "edição do vídeo"
    assert robo.passo_do_motivo(robo.MOTIVO_SEM_AVISOS) == "edição do vídeo"
    assert robo.passo_do_motivo("algo novo") == "outro" and robo.passo_do_motivo("") == ""


def test_historico_guarda_30_dias_e_mostra_as_12_mais_novas():
    for dia in range(1, 21):
        robo.registrar_tentativa("rascunho", "pulado", robo.SEM_OFERTA, agora=momento(f"2026-10-{dia:02d} 10:00"))
    robo.registrar_tentativa("rascunho", "salvo", produto="Vestido", agora=momento("2026-11-25 10:00"))
    # Só ficam os dos últimos 30 dias.
    assert [t["resultado"] for t in robo.tentativas_desde("2000-01-01 00:00:00")] == ["salvo"]
    for minuto in range(15):
        robo.registrar_tentativa("rascunho", "pulado", robo.SEM_OFERTA, agora=momento(f"2026-11-25 11:{minuto:02d}"))
    texto = robo.texto_historico(momento("2026-11-25 12:00"))
    assert "⏭️ 15 pulado" in texto and "✅ 1 salvo" in texto and "e mais 4 tentativa(s)" in texto
    assert len(texto) < 4096


def test_horario_novo_tira_a_repeticao_do_anterior_e_o_que_deu_certo_nao_repete():
    config = {**robo.PADRAO, "robo_limite_min": 2, "robo_limite_max": 2, "robo_inicio": 0, "robo_fim": 24}
    cedo, tarde = momento("2026-10-22 11:59"), momento("2026-10-22 23:59")
    assert robo.o_que_fazer(config, cedo) == ("rascunho", None)
    robo.marcar_para_repetir(config, cedo)
    assert robo.o_que_fazer(config, tarde) == ("rascunho", None)     # o 2º horário, com tentativas novas
    assert robo.o_que_fazer(config, tarde) is None                    # a repetição do 1º saiu
    assert robo.estado_do_dia(config, tarde)["tentativas"] == robo.TENTATIVAS_A_MAIS


def test_verificacao_e_preparar_1_agora_nao_repetem(monkeypatch, avisos):
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    agora = momento("2026-10-22 23:59")
    monkeypatch.setattr(robo.av, "abrir_tela", lambda **kwargs: None)

    erro = [robo.Verificacao()]

    def falha(*args, **kwargs):
        raise erro[0]

    monkeypatch.setattr(robo, "_preparar", falha)
    assert "verificação" in robo.rodada(d=AppDeMentira(), agora=agora)
    assert robo.rodada(d=Intocavel(), agora=agora) == "nada a fazer agora"
    erro[0] = robo.Parada("a tela mudou")
    assert "parado" in robo.rodada(preparar=True, d=AppDeMentira(), agora=agora)
    assert robo.rodada(d=Intocavel(), agora=agora) == "nada a fazer agora"


def test_video_sem_oferta_de_afiliado_fica_de_lado_e_o_proximo_vira_rascunho(monkeypatch, avisos):
    # Investigação de 23/10: o vídeo em que "o link não diz o produto" é de um produto sem
    # oferta de afiliado (não paga comissão). Escolha do Rafael: pular na hora, sem gastar
    # a tentativa do horário, e seguir com o próximo vídeo na mesma rodada.
    _fonte(monkeypatch)
    with open("archive/sem_oferta.mp4", "wb") as f:
        f.write(b"video")
    inserir("INSERT INTO fila_autorais VALUES (?, ?, ?, ?)", "b2", "archive/sem_oferta.mp4",
            "Copo 🥤\nhttps://s.shopee.com.br/semoferta", "2026-10-22 10:00:00")

    async def produtos_do_link(link):
        if "semoferta" in link:
            return [], link
        return [{"nome": VESTIDO, "preco": 59.9, "comissao": 10.0}], link

    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True, "fonte": "autorais"})
    assert robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert robo.esperando_aprovacao()[0]["id_video"] == "a1"
    pulado = robo.listar("pulado")[0]
    assert pulado["id_video"] == "b2" and pulado["motivo"] == robo.SEM_OFERTA
    assert "Copo" not in " ".join(str(a) for a in avisos)        # o robô nem começou o do copo


def test_so_videos_sem_oferta_param_a_rodada_sem_tocar_no_celular(monkeypatch, avisos):
    _fonte(monkeypatch)

    async def produtos_do_link(link):
        return [], link

    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)
    monkeypatch.setattr(robo, "VIDEOS_SEM_OFERTA_POR_RODADA", 1)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    resultado = robo.rodada(d=Intocavel(), agora=momento("2026-10-22 23:59"))
    assert resultado == "os próximos 1 vídeos da fonte são de produtos sem oferta de afiliado"
    assert robo.estado_do_dia(robo.ler_config(), momento("2026-10-22 23:59"))["repetir"] is True


class AppDeLojaDeFerias(AppDeMentira):
    """A página do produto avisa "Esse vendedor está de férias." (24/10, o teclado HB199)."""

    def __init__(self, pelo_toast=False):
        super().__init__()
        self.pelo_toast, self.toast_limpo = pelo_toast, False

    def _nos(self):
        nos = super()._nos()
        if self.atual == "pagina_curta" and not self.pelo_toast:
            nos = nos + [_no("Esse vendedor está de férias.", caixa=(200, 2180, 880, 2240), clicavel=False)]
        return nos

    def clear_toast(self):
        self.toast_limpo = True

    @property
    def last_toast(self):
        return "Esse vendedor está de férias." if self.pelo_toast and self.atual == "pagina_curta" else None


@pytest.mark.parametrize("pelo_toast", [False, True])
def test_produto_de_loja_de_ferias_pula_o_video_antes_da_galeria(monkeypatch, avisos, pelo_toast):
    # 24/10/2026: o robô curtiu o teclado, pôs o vídeo, escreveu o título e não achou o
    # produto no Adicionar Produto: a loja estava de férias, e a Shopee esconde o produto.
    from conftest import consultar
    _fonte(monkeypatch)
    app = AppDeLojaDeFerias(pelo_toast=pelo_toast)
    resultado = robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59"))
    assert robo.MOTIVO_DE_FERIAS in resultado and app.toast_limpo
    assert app.enviados == [] and "@buttonItemLike" not in app.toques     # nem galeria nem curtida
    pulado = robo.listar("pulado")[0]
    assert pulado["motivo"] == robo.MOTIVO_DE_FERIAS and robo.passo_do_motivo(pulado["motivo"]) == "loja de férias"
    assert consultar("SELECT resultado FROM registro_processos WHERE processo = 'produto de loja de férias'") == (
        "vídeo pulado",)


def test_aviso_de_ferias_de_outra_tela_nao_conta():
    # O nome de um produto pode ter "de férias": só o aviso da loja conta.
    xml = _xml(_no("Kit de férias para praia", caixa=(0, 0, 500, 60)))
    assert not robo.ps.loja_de_ferias(object(), xml)
    assert robo.ps.loja_de_ferias(object(), _xml(_no("Esse vendedor está de férias.", caixa=(0, 0, 500, 60))))


def test_violacao_pula_o_video(monkeypatch, avisos):
    _fonte(monkeypatch, violacao=True)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    assert "violação" in robo.rodada(d=Intocavel(), agora=momento("2026-10-22 23:59"))
    assert any("violação" in a for a in avisos if isinstance(a, str))


def test_verificacao_no_meio_para_e_manda_a_tela(monkeypatch, avisos):
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    abertas = []
    monkeypatch.setattr(robo.av, "abrir_tela", lambda celular=False, verificacao=False: abertas.append(verificacao))
    TELAS["verificacao"] = [_no("Verificação", "title_text", (200, 100, 500, 160))]
    CAMINHO[("eu", "Criadores & Afiliados")] = "verificacao"
    try:
        resultado = robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59"))
    finally:
        CAMINHO[("eu", "Criadores & Afiliados")] = "criadores"
    assert "verificação" in resultado and abertas == [True]
    # O vídeo não foi culpa dele: volta para a fila.
    assert robo.listar("pulado") == [] and robo.proximo_video(robo.ler_config())["id"] == "a1"


def test_treino_percorre_o_caminho_sem_salvar_nem_postar(monkeypatch, avisos):
    app = AppDeMentira()
    robo.gravar_estado(treino_resultado="mudou: antigo")
    vistos = []
    original = robo.ir_ao_perfil

    def ir_ao_perfil(d):
        vistos.append(robo.ler_estado()["treino_resultado"])     # o do treino anterior já saiu
        original(d)

    monkeypatch.setattr(robo, "ir_ao_perfil", ir_ao_perfil)
    resultado = robo.rodada(treino=True, d=app, agora=momento("2026-10-22 03:00"))
    assert resultado == "treino: caminho OK"
    assert "@tv_drafts_box" not in app.toques and "@btn_post" not in app.toques and "Postar" not in app.toques
    assert "caminho OK" in avisos[-1]
    assert robo.ler_estado()["treino_resultado"] == "ok" and vistos == [""]


def test_treino_abre_o_produto_do_rascunho_de_link_de_produto_pelo_nome_guardado(monkeypatch, avisos):
    # 28/10: o rascunho mais novo era de link de vídeo (ou a oferta do link saiu), a API não
    # disse o produto, e o treino acusou "algo mudou no app" sem o app ter mudado.
    async def sem_produto_na_api(link):
        return [], link

    async def link_para_converter(link):
        return link

    monkeypatch.setattr(robo.assistente, "produtos_do_link", sem_produto_na_api)
    monkeypatch.setattr(robo, "link_para_converter", link_para_converter)
    _rascunho("postado", criado="2026-10-20 10:00:00")
    robo.atualizar(_rascunho("rascunho", criado="2026-10-21 10:00:00"), link="https://sv.shopee.com.br/share-video/abc")
    app = AppDeMentira()
    assert robo.rodada(treino=True, d=app, agora=momento("2026-10-22 03:00")) == "treino: caminho OK"
    # Abriu o produto do rascunho de link de produto, pelo nome guardado nele, sem curtir.
    assert VESTIDO in app.toques and "@buttonItemLike" not in app.toques
    assert "caminho OK" in avisos[-1]


def test_treino_avisa_com_print_quando_uma_tela_mudou(monkeypatch, avisos):
    TELAS["camera_nova"] = [_no("Galeria", caixa=(800, 2100, 1000, 2200))]
    CAMINHO[("perfil", "Postar vídeo")] = "camera_nova"
    try:
        resultado = robo.rodada(treino=True, d=AppDeMentira(), agora=momento("2026-10-22 03:00"))
    finally:
        CAMINHO[("perfil", "Postar vídeo")] = "camera"
    assert resultado.startswith("treino: mudou") and "Biblioteca" in resultado
    assert avisos[-1][0] == "foto" and "algo mudou no app" in avisos[-1][1]
    assert robo.ler_estado()["treino_resultado"].startswith("mudou")


def test_mesma_legenda():
    assert robo.mesma_legenda(TITULO, TITULO)
    assert robo.mesma_legenda(TITULO[:40] + "…", TITULO)
    assert not robo.mesma_legenda("Outro título qualquer que não é este de jeito nenhum", TITULO)
    assert not robo.mesma_legenda("", TITULO)
    # O que o app pode mudar sem mudar o título: quebra de linha antes das hashtags,
    # espaço de largura zero e o seletor de variação do emoji.
    assert robo.mesma_legenda(TITULO.replace(" #", "\n#").replace("👗", "👗\ufe0f"), TITULO)
    assert robo.mesma_legenda(TITULO.replace("#", "\u200b#"), TITULO)
    assert not robo.mesma_legenda(TITULO.replace("Gatinho", "Cachorro"), TITULO)


def test_comparar_legenda_diz_onde_difere_sem_mostrar_o_texto():
    assert robo.ps.comparar_legenda(TITULO, TITULO).startswith("a legenda é o título")
    texto = robo.ps.comparar_legenda("Vestido Infantil Estampado Cachorro", TITULO)
    assert "NÃO é o título" in texto and "caractere 28" in texto and "U+0043" in texto and "Vestido" not in texto


TELAS["lista_rascunhos"] = [_no("Selecionar", caixa=(860, 150, 1040, 200)),
                            _no(caixa=(20, 400, 350, 800)), _no(caixa=(370, 400, 700, 800))]
TELAS["rascunho_aberto"] = [_no("Próximo", "tv_compress", (860, 150, 1040, 210))]


@pytest.fixture
def caminho_do_rascunho(monkeypatch):
    """No app de mentira: Rascunhos → o 1º quadro → Próximo → tela final → Postar."""
    for chave, destino in ((("perfil", "Rascunhos: 1"), "lista_rascunhos"), (("lista_rascunhos", (185, 600)), "rascunho_aberto"),
                           (("rascunho_aberto", "@tv_compress"), "final"), (("final", "@btn_post"), "live")):
        monkeypatch.setitem(CAMINHO, chave, destino)


class AppComQuadros(AppDeMentira):
    """Toque num quadro sem texto vai pelo ponto (os quadros da lista não têm nome)."""

    def click(self, x, y):
        if (self.atual, (x, y)) in CAMINHO:
            self.toques.append((x, y))
            self.atual = CAMINHO[(self.atual, (x, y))]
            return
        super().click(x, y)


def _aprovado(monkeypatch):
    async def produtos_do_link(link):
        return [{"nome": VESTIDO, "preco": 59.9, "comissao": 10.0}], link

    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)
    ativar(robo_inicio=0, robo_fim=24)
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-22 23:59")))
    return _rascunho("aprovado", postar_em="2026-10-22 12:00:00")


def test_aprovado_e_postado_com_a_tela_final_conferida(monkeypatch, avisos, caminho_do_rascunho):
    ident = _aprovado(monkeypatch)
    app = AppComQuadros()
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho aprovado postado"
    assert app.toques.count("@btn_post") == 1 and robo.pegar(ident)["estado"] == "postado"
    assert "postei o vídeo que você aprovou" in avisos[0]
    # O comentário vem numa mensagem só dele, depois do lembrete.
    assert avisos[1:] == [robo.ps.AVISO_COMENTARIO, "Amei! #achadinhos"]


def test_rascunho_aberto_com_outro_titulo_nao_e_postado(monkeypatch, avisos, caminho_do_rascunho):
    # Escolha do Rafael (30/10, P99): o aprovado que não sai continua aprovado e o robô tenta de
    # novo nas rodadas seguintes, conferindo tudo antes; só na 3ª vez volta para ele aprovar.
    ident = _aprovado(monkeypatch)
    for vez, hora in enumerate(("23:57", "23:58", "23:59"), 1):
        app = AppComQuadros()
        app.legenda, app.com_produto = "Outro título de outro rascunho qualquer #outro", True
        assert "parado" in robo.rodada(d=app, agora=momento(f"2026-10-22 {hora}"))
        assert "@btn_post" not in app.toques
        rascunho = robo.pegar(ident)
        assert "título" in rascunho["motivo"]
        if vez < robo.TENTATIVAS_DE_POSTAR:
            assert rascunho["estado"] == "aprovado" and rascunho["falhas_ao_postar"] == str(vez)
            assert "não consegui postar" in avisos[-1] and f"tentativa {vez + 1} de 3" in avisos[-1]
            assert f"não saiu {vez} vez(es)" in robo.texto_da_fila(agora=momento(f"2026-10-22 {hora}"))
    rascunho = robo.pegar(ident)
    assert rascunho["estado"] == "rascunho" and rascunho["falhas_ao_postar"] == "0"
    assert "tentei postar o rascunho aprovado 3 vezes" in avisos[-1] and "título" in avisos[-1]
    # Aprovado de novo, ganha mais 3 tentativas.
    robo.atualizar(ident, falhas_ao_postar="2")
    robo.aprovar(ident, agora=momento("2026-10-23 08:00"))
    assert robo.pegar(ident)["falhas_ao_postar"] == "0"


def test_erro_inesperado_ao_postar_tambem_conta_nas_3_tentativas(monkeypatch, avisos, caminho_do_rascunho):
    ident = _aprovado(monkeypatch)
    monkeypatch.setattr(robo, "abrir_rascunho", lambda d, rascunho: (_ for _ in ()).throw(ConnectionError("caiu")))
    for hora in ("23:57", "23:58", "23:59"):
        assert "erro ConnectionError" in robo.rodada(d=AppComQuadros(), agora=momento(f"2026-10-22 {hora}"))
    assert robo.pegar(ident)["estado"] == "rascunho"
    assert "tentei postar o rascunho aprovado 3 vezes" in avisos[-1]


# --- Telas mapeadas no Motorola em 22/10/2026: aviso de sair, apagar e o link do post ---

TELAS["aviso"] = [_no("Se você voltar, as edições serão descartadas.", "content", (60, 1100, 1020, 1250), clicavel=False),
                  _no("Cancelar", "buttonDefaultNegative", (100, 1300, 500, 1380)),
                  _no("Descartar", "buttonDefaultPositive", (580, 1300, 980, 1380))]
QUADROS = [_no(caixa=(20, 400, 350, 800)), _no(caixa=(370, 400, 700, 800))]
TELAS["lista_selecao"] = [_no("Cancelar", caixa=(860, 150, 1040, 200))] + QUADROS + [_no("Excluir (0)", caixa=(300, 2280, 780, 2350))]
TELAS["lista_marcada"] = [_no("Cancelar", caixa=(860, 150, 1040, 200))] + QUADROS + [_no("Excluir (1)", caixa=(300, 2280, 780, 2350))]
TELAS["confirmar_exclusao"] = [_no("Excluir vídeos selecionados?", caixa=(200, 1160, 880, 1220), clicavel=False),
                               _no("Cancelar", caixa=(200, 1280, 460, 1340)), _no("Confirmar", caixa=(620, 1280, 880, 1340))]
TELAS["lista_vazia"] = [_no("Rascunhos", caixa=(400, 150, 620, 200), clicavel=False)]


class AppComVoltar(AppComQuadros):
    """O voltar como no Motorola: da tela final abre o aviso; no aviso, fecha o aviso."""
    VOLTAR = {"final": "aviso", "aviso": "final", "rascunho_aberto": "lista_rascunhos",
              "lista_rascunhos": "perfil", "perfil": "conta", "conta": "criadores", "criadores": "eu"}

    def press(self, tecla):
        self.teclas.append(tecla)
        self.atual = self.VOLTAR.get(self.atual, "inicio")


@pytest.fixture
def caminho_de_apagar(monkeypatch, caminho_do_rascunho):
    for chave, destino in ((("aviso", "@buttonDefaultPositive"), "rascunho_aberto"),
                           (("lista_rascunhos", "Selecionar"), "lista_selecao"),
                           (("lista_selecao", (185, 600)), "lista_marcada"),
                           (("lista_marcada", "Excluir (1)"), "confirmar_exclusao"),
                           (("confirmar_exclusao", "Confirmar"), "lista_vazia")):
        monkeypatch.setitem(CAMINHO, chave, destino)


def _recusado(monkeypatch):
    ident = _aprovado(monkeypatch)
    robo.atualizar(ident, estado="recusado", postar_em=None)
    return ident


def test_recusado_e_apagado_com_a_confirmacao_e_o_aviso_de_sair(monkeypatch, avisos, caminho_de_apagar):
    ident = _recusado(monkeypatch)
    app = AppComVoltar()
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho recusado apagado"
    # Abre para conferir, sai pelo aviso (o rascunho continua salvo) e apaga pela lista.
    assert "@buttonDefaultPositive" in app.toques
    assert app.toques[-3:] == [(185, 600), "Excluir (1)", "Confirmar"]
    assert "@btn_post" not in app.toques and robo.pegar(ident)["estado"] == "apagado"


def test_com_outro_numero_no_excluir_nada_e_apagado(monkeypatch, avisos, caminho_de_apagar):
    ident = _recusado(monkeypatch)
    monkeypatch.setitem(TELAS, "lista_marcada", TELAS["lista_selecao"][:-1] + [_no("Excluir (2)", caixa=(300, 2280, 780, 2350))])
    app = AppComVoltar()
    app.legenda, app.com_produto = TITULO, True
    assert "parado" in robo.rodada(d=app, agora=momento("2026-10-22 23:59"))
    assert "Confirmar" not in app.toques and robo.pegar(ident)["estado"] == "rascunho"
    assert "não consegui apagar" in avisos[-1]


def test_sem_rascunho_salvo_o_perfil_nao_tem_o_quadro_e_o_robo_para(monkeypatch, avisos, caminho_de_apagar):
    ident = _recusado(monkeypatch)
    monkeypatch.setitem(TELAS, "perfil", [_no("Postar vídeo", caixa=(700, 2200, 1040, 2300))])
    app = AppComVoltar()
    assert "nenhum rascunho salvo" in robo.rodada(d=app, agora=momento("2026-10-22 23:59"))
    assert robo.pegar(ident)["estado"] == "rascunho"


class PerfilDevagar(AppComQuadros):
    """O Perfil com a grade (o quadro Rascunhos) carregando pela rede nas primeiras leituras."""

    def __init__(self, leituras_sem_grade):
        super().__init__()
        self.sem_grade = leituras_sem_grade

    def _nos(self):
        nos = super()._nos()
        if self.atual == "perfil" and self.sem_grade > 0:
            self.sem_grade -= 1
            return [n for n in nos if "Rascunhos:" not in n]
        return nos


def test_aprovado_espera_o_quadro_rascunhos_carregar_no_perfil(monkeypatch, avisos, caminho_do_rascunho):
    # 24/10, 08:58: a postagem parou com "o Perfil não tem nenhum rascunho salvo"; a grade
    # do Perfil carrega pela rede depois do Postar vídeo.
    ident = _aprovado(monkeypatch)
    app = PerfilDevagar(3)
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho aprovado postado"
    assert robo.pegar(ident)["estado"] == "postado"


def _no_do_app(pacote, texto, caixa):
    return _no(texto, caixa=caixa).replace("<node ", f'<node package="{pacote}" ', 1)


class CelularQueSaiuDaShopee:
    """O voltar a mais saiu da Shopee e o Telegram ficou na frente."""

    def __init__(self):
        self.app, self.teclas, self.aberturas = "org.telegram.messenger", [], []

    def dump_hierarchy(self):
        if self.app == robo.ps.PACOTE:
            return _xml(_no_do_app(robo.ps.PACOTE, "Eu", (860, 2250, 1080, 2400)))
        return _xml(_no_do_app(self.app, "Conversas", (0, 100, 500, 200)))

    def press(self, tecla):
        self.teclas.append(tecla)

    def app_start(self, pacote, wait=False):
        self.aberturas.append(pacote)
        self.app = pacote


def test_voltar_fora_da_shopee_traz_a_shopee_e_nunca_aperta_voltar_no_outro_app():
    # O Rafael via o Telegram na frente no Motorola (23/10): o voltar não pode mexer em outro app.
    celular = CelularQueSaiuDaShopee()
    robo.voltar(celular, "Eu")
    assert celular.teclas == [] and celular.aberturas == [robo.ps.PACOTE]


class CelularPresoSemEu:
    """O voltar não chega ao Eu (como nos rascunhos de 24/10, 13:17 e 13:38)."""

    info = {"screenOn": False}

    def __init__(self):
        self.teclas = []

    def dump_hierarchy(self):
        return _xml(_no_do_app(robo.ps.PACOTE, "Ver Produtos (1)", (0, 1500, 600, 1600)))

    def press(self, tecla):
        self.teclas.append(tecla)

    def app_current(self):
        return {"package": robo.ps.PACOTE, "activity": "com.shopee.app.react.ReactTransparentActivity_"}


def test_voltar_que_nao_chega_anota_a_tela_em_que_ficou_sem_o_texto_dela():
    from conftest import consultar
    celular = CelularPresoSemEu()
    with pytest.raises(robo.Parada) as parada:
        robo.voltar(celular, "Eu", vezes=3)
    onde = f"app {robo.ps.PACOTE}, tela ReactTransparentActivity_, tela do celular desligada"
    assert str(parada.value) == f"não consegui voltar até Eu ({onde})" and celular.teclas == ["back"] * 3
    assert consultar("SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = 'voltar no app'") == (
        "não chegou ao Eu", onde, 0)


class CelularComErroDoApp:
    """
    O app da Shopee no aviso de erro (Motorola, 31/10, 15:48 e 15:59): "Ops! Algo deu errado.
    Estamos verificando nisso.", que o voltar não fecha; o Voltar à Página Inicial leva ao início.
    """

    info = {"screenOn": True}

    def __init__(self):
        self.teclas, self.toques, self.no_inicio = [], [], False

    def dump_hierarchy(self):
        if self.no_inicio:
            return _xml(_no_do_app(robo.ps.PACOTE, "Eu", (860, 2250, 1080, 2400)))
        return _xml(_no_do_app(robo.ps.PACOTE, "Ops! Algo deu errado. Estamos verificando nisso.", (70, 1150, 1010, 1250)),
                    _no_do_app(robo.ps.PACOTE, "Voltar à Página Inicial", (70, 1290, 1010, 1390)))

    def press(self, tecla):
        self.teclas.append(tecla)

    def click(self, x, y):
        self.toques.append((x, y))
        self.no_inicio = self.no_inicio or (70 <= x <= 1010 and 1290 <= y <= 1390)

    def app_current(self):
        return {"package": robo.ps.PACOTE, "activity": "com.shopee.app.react.ReactActivity_"}


def test_voltar_sai_do_aviso_de_erro_do_app_pelo_voltar_a_pagina_inicial(monkeypatch):
    # 31/10, 15:48 e 15:59: o app caiu no aviso de erro e o robô apertou voltar até desistir; o
    # rascunho parou duas vezes. O botão do aviso leva ao início, e o registro anota o aviso.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    celular = CelularComErroDoApp()
    robo.voltar(celular, "Eu", vezes=3)
    assert celular.no_inicio and celular.teclas == []
    assert consultar("SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = 'voltar no app'") == (
        "aviso de erro do app", "Voltar à Página Inicial tocado", None)


AVISO_DE_APP_TRAVADO = _xml(
    '<node text="Shopee não está respondendo" resource-id="android:id/alertTitle" package="android" '
    'class="android.widget.TextView" clickable="false" bounds="[100,1090][980,1160]"></node>',
    '<node text="Fechar app" resource-id="android:id/aerr_close" package="android" '
    'class="android.widget.Button" clickable="true" bounds="[100,1210][980,1300]"></node>',
    '<node text="Aguardar" resource-id="android:id/aerr_wait" package="android" '
    'class="android.widget.Button" clickable="true" bounds="[100,1340][980,1430]"></node>')


class CelularComAppTravado:
    """
    O Motorola em 24/10 (13:17 e 13:38): o Android pergunta se fecha a Shopee, que não
    responde. travado_por: quantos toques em Aguardar até voltar; depois_de_reabrir: a
    tela da Shopee aberta de novo pelo Fechar app (None: continua travada).
    """

    def __init__(self, travado_por, depois_de_reabrir=None):
        self.travado_por, self.depois_de_reabrir = travado_por, depois_de_reabrir
        self.toques, self.aberturas, self.fechado = [], [], False

    def dump_hierarchy(self):
        if self.fechado:
            return self.depois_de_reabrir or AVISO_DE_APP_TRAVADO
        if len(self.toques) < self.travado_por:
            return AVISO_DE_APP_TRAVADO
        return _xml(ABA_EU)

    def click(self, x, y):
        self.toques.append((x, y))
        self.fechado = self.fechado or (x, y) == FECHAR_APP

    def app_start(self, pacote, wait=False):
        self.aberturas.append(pacote)


AGUARDAR, FECHAR_APP = (540, 1385), (540, 1255)


def test_app_que_nao_responde_ganha_o_aguardar_e_a_rodada_segue():
    from conftest import consultar
    celular = CelularComAppTravado(travado_por=1)
    assert robo.tem_exato(robo.tela(celular), "Eu")
    assert celular.toques == [AGUARDAR] and celular.aberturas == []
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = 'app travado'") == (
        "voltou depois do Aguardar", 1)


def test_app_que_continua_travado_e_fechado_e_reaberto_e_o_passo_fica_para_a_proxima():
    # Escolha do Rafael (24/10, P15): depois de 3 Aguardar, Fechar app e reabrir.
    from conftest import consultar
    celular = CelularComAppTravado(travado_por=99, depois_de_reabrir=_xml(ABA_EU))
    with pytest.raises(robo.Parada) as parada:
        robo.tela(celular)
    assert celular.toques == [AGUARDAR] * robo.VEZES_DO_AGUARDAR + [FECHAR_APP]
    assert celular.aberturas == [robo.ps.PACOTE]
    assert robo.passo_do_motivo(parada.value.motivo) == "app travado"
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = 'app travado'") == (
        "fechado e reaberto", 1)


def test_app_travado_mesmo_depois_de_reabrir_para_sem_fechar_de_novo():
    from conftest import consultar
    celular = CelularComAppTravado(travado_por=99)
    with pytest.raises(robo.Parada) as parada:
        robo.tela(celular)
    assert celular.toques.count(FECHAR_APP) == 1 and celular.aberturas == [robo.ps.PACOTE]
    assert "mesmo depois de fechar e reabrir" in parada.value.motivo
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = 'app travado'") == (
        "continuou travado", 0)


def test_verificacao_depois_de_reabrir_o_app_travado_para_como_sempre(monkeypatch):
    celular = CelularComAppTravado(travado_por=99, depois_de_reabrir=_xml(ABA_EU))
    monkeypatch.setattr(robo.ps, "eh_verificacao", lambda xml: celular.fechado)
    with pytest.raises(robo.Verificacao):
        robo.tela(celular)


def test_voltar_toca_em_aguardar_no_aviso_de_app_travado_em_vez_de_apertar_voltar():
    celular = CelularComAppTravado(travado_por=1)
    celular.teclas = []
    celular.press = celular.teclas.append
    robo.voltar(celular, "Eu")
    assert celular.toques == [AGUARDAR] and celular.teclas == []


def test_voltar_segue_do_app_reaberto_depois_do_fechar_app():
    celular = CelularComAppTravado(travado_por=99, depois_de_reabrir=_xml(ABA_EU))
    celular.teclas = []
    celular.press = celular.teclas.append
    robo.voltar(celular, "Eu")
    assert celular.toques[-1] == FECHAR_APP and celular.teclas == []


def test_aviso_do_android_por_cima_da_shopee_nao_conta_como_outro_app():
    aviso = _xml(_no_do_app("com.android.permissioncontroller", "Permitir", (100, 1000, 500, 1100)))
    telegram = _xml(_no_do_app("org.telegram.messenger", "Conversas", (0, 100, 500, 200)))
    shopee = _xml(_no_do_app(robo.ps.PACOTE, "Eu", (860, 2250, 1080, 2400)))
    assert robo.fora_da_shopee(telegram)
    assert not robo.fora_da_shopee(aviso) and not robo.fora_da_shopee(shopee)
    # Sem o pacote nos elementos (como nas telas de mentira), não dá para saber.
    assert not robo.fora_da_shopee(_xml(_no("Conversas")))


def test_volta_ao_inicio_pelo_eu_da_barra_e_nao_por_um_seu_no_meio_do_texto(monkeypatch):
    app = AppComVoltar()
    app.atual = "perfil"
    monkeypatch.setitem(TELAS, "perfil", TELAS["perfil"] + [_no("Siga o seu perfil", caixa=(40, 500, 1040, 560), clicavel=False)])
    robo.ir_ao_inicio(app)
    assert app.atual == "eu" and app.teclas == ["back"] * 3


def test_link_do_post_pula_o_quadro_de_rascunhos_e_os_fixados(monkeypatch):
    TELAS_PERFIL = [_no("Postar vídeo", caixa=(700, 2200, 1040, 2300)),
                    _no(caixa=(0, 1210, 358, 1680), filhos=_no("Rascunhos: 1", caixa=(40, 1460, 320, 1510), clicavel=False)),
                    _no(caixa=(361, 1210, 719, 1680), filhos=_no("Fixado", caixa=(380, 1230, 480, 1270), clicavel=False)),
                    _no(caixa=(722, 1210, 1080, 1680))]
    monkeypatch.setitem(TELAS, "perfil", TELAS_PERFIL)
    monkeypatch.setitem(TELAS, "player", [
        '<node text="" content-desc="post video share icon" class="android.view.View" clickable="true" '
        'bounds="[950,1935][1052,2035]"></node>', _no("Adicionar um comentário...", caixa=(200, 2300, 900, 2360))])
    monkeypatch.setitem(TELAS, "folha", [_no("Copiar link", caixa=(280, 2200, 440, 2300))])
    for chave, destino in ((("perfil", (901, 1445)), "player"), (("player", (1001, 1985)), "folha"),
                           (("folha", "Copiar link"), "player")):
        monkeypatch.setitem(CAMINHO, chave, destino)
    app = AppComQuadros()
    app.clipboard = "https://sv.shopee.com.br/share-video/abc"
    monkeypatch.setattr(robo, "ir_ao_perfil", lambda d: setattr(d, "atual", "perfil"))
    assert robo.link_do_post(app) == "https://sv.shopee.com.br/share-video/abc"
    assert app.toques == [(901, 1445), (1001, 1985), "Copiar link"]
    app.clipboard = "texto qualquer"
    assert robo.link_do_post(app) == ""


def test_o_compartilhar_do_perfil_nao_serve_para_o_link_do_post():
    perfil = _xml('<node text="" content-desc="profile share" class="android.view.View" clickable="true" '
                  'bounds="[860,140][940,200]"></node>')
    assert robo.botao_de_compartilhar(perfil) is None


def _saida_da_tela_final(monkeypatch, **voltar):
    """
    O app de mentira com a saída da tela final de um vídeo novo, como no Motorola: o aviso de
    sair, a edição e o "Deseja sair da página de edição?". voltar: telas a mais no voltar.
    """
    monkeypatch.setitem(TELAS, "sair_da_edicao", [
        _no("Deseja sair da página de edição?", "tv_main_title", (100, 1780, 980, 1840), clicavel=False),
        _no("Salvar Rascunho", "tv_save", (100, 2090, 980, 2150)),
        _no("Descartar", "tv_no_save", (100, 2190, 980, 2250)),
        _no("Cancelar", "tv_cancel", (100, 2310, 980, 2370))])
    monkeypatch.setitem(CAMINHO, ("sair_da_edicao", "@tv_no_save"), "galeria")
    app = AppComVoltar()
    monkeypatch.setattr(app, "VOLTAR", {**AppComVoltar.VOLTAR, "aviso": "final", "edicao": "sair_da_edicao",
                                        "sair_da_edicao": "edicao", "galeria": "camera", "camera": "perfil",
                                        **voltar})
    monkeypatch.setitem(CAMINHO, ("aviso", "@buttonDefaultPositive"), "edicao")
    return app


def test_da_edicao_de_um_video_novo_o_robo_descarta_e_volta_ao_inicio(monkeypatch):
    # Na edição de um vídeo novo, o voltar pergunta se salva como rascunho: o robô
    # descarta, para a lista do app só ter os rascunhos que ele terminou.
    app = _saida_da_tela_final(monkeypatch)
    app.atual = "final"
    robo.ir_ao_inicio(app)
    assert app.atual == "eu"
    assert "@buttonDefaultPositive" in app.toques and "@tv_no_save" in app.toques and "@tv_save" not in app.toques


def test_da_selecao_da_capa_com_mudanca_o_robo_confirma_o_descartar_e_volta_ao_inicio(monkeypatch):
    # Como no Motorola em 30/10 (21:20 e 21:35, com o celular deixado na capa de um teste):
    # na Selecione sua capa com uma figurinha posta, o voltar pergunta se descarta as
    # alterações, e o voltar na pergunta só a fecha. O robô ficava indo e vindo entre as duas
    # até desistir; agora confirma e segue a saída de sempre da tela final.
    monkeypatch.setitem(TELAS, "capa", [
        _no(ident="cancel_btn", caixa=(42, 157, 116, 231)),
        _no("Selecione sua capa", "title_tv", (116, 162, 964, 225), clicavel=False),
        _no(ident="save_btn", caixa=(964, 157, 1038, 231)),
        _no("Adicionar figurinha", "tv_add_sticker", (679, 2288, 994, 2339), clicavel=False)])
    monkeypatch.setitem(TELAS, "descartar_capa", [
        _no("Descartar Alterações na Capa?", "tv_title", (92, 1229, 988, 1286), clicavel=False),
        _no("Cancelar", "tv_cancel", (92, 1350, 539, 1476)),
        _no("Confirmar", "tv_discard", (540, 1350, 988, 1476))])
    monkeypatch.setitem(CAMINHO, ("descartar_capa", "@tv_discard"), "final")
    app = _saida_da_tela_final(monkeypatch, capa="descartar_capa", descartar_capa="capa")
    app.atual = "capa"
    robo.ir_ao_inicio(app)
    assert app.atual == "eu"
    assert app.toques[0] == "@tv_discard" and "@tv_cancel" not in app.toques and "@tv_no_save" in app.toques


# --- Preparar 1 Agora e o que o rascunho guarda para o Rafael validar (23/10/2026) ---

def test_preparar_1_agora_salva_um_rascunho_mesmo_pausado_e_fora_do_plano(monkeypatch, avisos):
    _fonte(monkeypatch)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True, "robo_inicio": 8, "robo_fim": 9,
                                               "fonte": "autorais"})
    app = AppDeMentira()
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["fonte"] == "autorais"
    assert robo.json.loads(rascunho["conferencia"]) == ["vestido", "vestido"]     # as 2 vezes da IA
    assert "Postar" not in app.toques and "@btn_post" not in app.toques
    assert robo.ler_config()["robo_pausado"] is True                              # continua pausado


def test_titulo_com_emoji_trocado_pelo_app_para_sem_salvar_o_rascunho(monkeypatch, avisos):
    # A conferência vale pela cópia do campo: se o próprio app guardar ".." no lugar do 👗,
    # o robô para, mesmo que a leitura da tela também mostre "..".
    _fonte(monkeypatch)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True})

    class AppQueTrocaEmoji(AppDeMentira):
        def send_keys(self, texto):
            self.legenda += robo.ps.como_o_android_le(texto)

    app = AppQueTrocaEmoji()
    resultado = robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59"))
    assert "o título não ficou na legenda" in resultado and robo.esperando_aprovacao() == []
    assert "@tv_drafts_box" not in app.toques
    # O diagnóstico (público) mostra por onde leu e os tamanhos, nunca o título.
    conferencia = robo.ler_estado()["ultima_legenda"]
    assert conferencia.startswith("pela cópia: a legenda NÃO é o título") and "U+1F457" in conferencia
    assert "1 emoji(s) de fora do plano básico" in conferencia and "Gatinho" not in conferencia


def test_sem_a_copia_do_campo_o_emoji_lido_como_ponto_para_o_rascunho(monkeypatch, avisos):
    # Sem a cópia (o Android não deixou ler), sobra a leitura com ".." no lugar do 👗: para.
    _fonte(monkeypatch)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True})

    class AppSemCopia(AppDeMentira):
        def press(self, tecla, meta=None):
            if not meta:
                super().press(tecla)

    resultado = robo.rodada(preparar=True, d=AppSemCopia(), agora=momento("2026-10-22 23:59"))
    assert "o título não ficou na legenda" in resultado and robo.esperando_aprovacao() == []
    assert robo.ler_estado()["ultima_legenda"].startswith("sem a cópia, pela acessibilidade: ")


def _arquivos_do_rascunho(ident, app):
    """O vídeo e o print do rascunho no servidor, e o vídeo na galeria do celular."""
    os.makedirs(robo.PASTA_RASCUNHOS, exist_ok=True)
    arquivos = [os.path.join(robo.PASTA_RASCUNHOS, f"{ident}.{ext}") for ext in ("mp4", "png")]
    for arquivo in arquivos:
        with open(arquivo, "wb") as f:
            f.write(b"x")
    robo.atualizar(ident, arquivo=arquivos[0], print=arquivos[1])
    app.galeria.add(robo.nome_na_galeria(ident))
    return arquivos


def test_postado_sai_do_servidor_e_da_galeria_e_o_que_espera_aprovacao_fica(monkeypatch, avisos, caminho_do_rascunho):
    # Pedido do Rafael (23/10): a memória de cada rascunho é só do robô e sai depois de usada.
    ident = _aprovado(monkeypatch)
    esperando = _rascunho("rascunho", criado="2026-10-21 10:00:00")   # mais velho: fica depois na lista do app
    app = AppComQuadros()
    app.legenda, app.com_produto = TITULO, True
    postado, guardado = _arquivos_do_rascunho(ident, app), _arquivos_do_rascunho(esperando, app)
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho aprovado postado"
    assert not any(os.path.exists(arquivo) for arquivo in postado)
    assert all(os.path.exists(arquivo) for arquivo in guardado)
    assert app.galeria == {robo.nome_na_galeria(esperando)}
    # A linha do banco fica: é ela que impede o mesmo vídeo de voltar.
    assert robo.pegar(ident)["estado"] == "postado" and "video:1" in robo.ids_usados()


def test_preparo_que_parou_no_meio_nao_deixa_o_video_no_servidor_nem_na_galeria(monkeypatch, avisos):
    _fonte(monkeypatch)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True})

    class AppQueTrocaEmoji(AppDeMentira):
        def send_keys(self, texto):
            self.legenda += robo.ps.como_o_android_le(texto)

    app = AppQueTrocaEmoji()
    resultado = robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59"))
    assert "o título não ficou na legenda" in resultado
    # O vídeo chegou a ir para a galeria antes de parar; no fim da rodada, saiu dos dois lugares.
    assert app.enviados and app.galeria == set() and os.listdir(robo.PASTA_RASCUNHOS) == []


def test_celular_que_cai_na_faxina_deixa_a_copia_do_servidor_para_a_proxima_rodada(avisos):
    ident = _rascunho("postado")

    class AppQueCaiu(AppDeMentira):
        def shell(self, partes):
            raise ConnectionError("o celular saiu da rede")

    app = AppQueCaiu()
    arquivos = _arquivos_do_rascunho(ident, app)
    robo.faxina_dos_arquivos(app)
    assert all(os.path.exists(arquivo) for arquivo in arquivos)
    robo.faxina_dos_arquivos(AppDeMentira())
    assert not any(os.path.exists(arquivo) for arquivo in arquivos)


def test_preparar_1_agora_sem_video_diz_no_privado_por_que_nao_preparou(monkeypatch, avisos):
    inserir("CREATE TABLE IF NOT EXISTS fila_autorais (id_unico TEXT, caminho_arquivo TEXT, legenda TEXT, data_captura TEXT)")
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True})
    resultado = robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59"))
    assert "nenhum vídeo" in resultado
    assert "não preparei o rascunho que você pediu" in avisos[-1]


def test_tabela_antiga_ganha_as_colunas_novas_sem_perder_os_rascunhos():
    inserir("CREATE TABLE shopee_video_rascunhos (id INTEGER PRIMARY KEY AUTOINCREMENT, id_video TEXT, "
            "criado_em TEXT, estado TEXT, arquivo TEXT, print TEXT, link TEXT, produtos TEXT, titulo TEXT, "
            "comentario TEXT, aprovado_em TEXT, postar_em TEXT, postado_em TEXT, link_post TEXT, motivo TEXT)")
    inserir("INSERT INTO shopee_video_rascunhos (id_video, criado_em, estado, produtos) VALUES (?, ?, ?, ?)",
            "antigo", "2026-10-22 10:00:00", "rascunho", "[]")
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["id_video"] == "antigo" and rascunho["fonte"] is None and rascunho["conferencia"] is None


def test_erro_inesperado_no_preparar_avisa_e_nao_derruba_a_rodada(monkeypatch, avisos):
    _fonte(monkeypatch)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True})

    def quebra(*args, **kwargs):
        raise KeyError("x")

    monkeypatch.setattr(robo.ps, "curtir", quebra)
    resultado = robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59"))
    assert resultado == "rascunho: erro KeyError"
    assert "não preparei o rascunho que você pediu (rascunho: erro KeyError)" in avisos[-1]
    assert robo.listar("preparando", "rascunho") == []                       # a reserva foi desfeita


def test_main_grava_a_ultima_rodada_mascarada(monkeypatch):
    monkeypatch.setattr(robo, "rodada", lambda **kw: f"rascunho: parado (não achei {VESTIDO} na lista)")
    assert robo.main(["--preparar"]) == 0
    estado = robo.ler_estado()
    assert estado["ultima_rodada"].startswith("rascunho: parado (não achei") and "Vestido" not in estado["ultima_rodada"]
    assert estado["ultima_rodada_em"]


def test_galeria_que_lembra_um_video_antigo_marcado_fica_so_com_o_mais_novo(monkeypatch):
    # No Motorola (23/10) a galeria lembrou a marcação de antes: tocar sem olhar desmarcava
    # o vídeo ou juntaria dois vídeos no mesmo post.
    monkeypatch.setitem(TELAS, "galeria_lembrada", [
        _no(ident="ll_check", caixa=(300, 300, 360, 360)),
        _no(ident="ll_check", caixa=(600, 300, 660, 360), filhos=_no("1", "check", (620, 310, 640, 330), clicavel=False)),
        _no("Próximo (1)", "tv_pick_top_next", (860, 2080, 980, 2130))])
    monkeypatch.setitem(CAMINHO, ("galeria_lembrada", (630, 330)), "galeria")
    monkeypatch.setitem(CAMINHO, ("galeria", (330, 330)), "galeria_marcada")
    app = AppComQuadros()
    app.atual = "galeria_lembrada"
    robo.marcar_so_o_mais_novo(app)
    assert app.toques == [(630, 330), (330, 330)] and app.atual == "galeria_marcada"
    # Já certo: não toca em nada.
    app.toques = []
    robo.marcar_so_o_mais_novo(app)
    assert app.toques == []


# --- Link de vídeo: o Ver Produtos (mapeado no Motorola em 23/10/2026) ---

PRODUTO_A = "Garrafa Térmica Inox 1 Litro Com Alça e Tampa Rosqueável"
PRODUTO_B = "Copo Térmico Inox 500 ml Com Canudo e Tampa"
RECOMENDADO = "Kit Potes Herméticos De Vidro Para Cozinha Com Tampa"
LINK_DE_VIDEO = "https://s.shopee.com.br/videocomprodutos"


def _cartao(nome, y):
    """Um cartão da lista do Ver Produtos: nome, preço e o botão de comprar (que o robô nunca toca)."""
    return _no(caixa=(0, y, 1080, y + 300), filhos=(
        _no(nome, caixa=(300, y + 20, 1040, y + 80), clicavel=False)
        + _no("R$59,90", caixa=(300, y + 200, 500, y + 240), clicavel=False)
        + _no(caixa=(780, y + 200, 1050, y + 280),
              filhos=_no("Comprar com cupom", caixa=(790, y + 210, 1040, y + 270), clicavel=False))))


def _item_curtido(nome, y, adicionado):
    return _no(caixa=(0, y, 1080, y + 270), filhos=(
        _no(nome, caixa=(300, y + 10, 1040, y + 70), clicavel=False)
        + _no(caixa=(840, y + 165, 1010, y + 230),
              filhos=_no("Adicionado" if adicionado else "Adicionar", caixa=(850, y + 175, 1000, y + 220),
                         clicavel=False))))


class AppDoVerProdutos(AppDeMentira):
    """O app com um link de vídeo: o player, o Ver Produtos, as páginas dos produtos e o Adicionar Mais."""

    def __init__(self, removido=False, player="normal"):
        super().__init__()
        self.removido, self.curtidos, self.anexados, self.janela = removido, set(), [], None
        # Todos os que o robô curtiu, mesmo os descurtidos no fim do rascunho.
        self.ja_curtidos = set()
        # player: "normal"; "lento" (o Ver Produtos só aparece na segunda olhada); "um_produto"
        # (um produto só: o cartão e a barra com o nome dele, sem o Ver Produtos); "so_cartao"
        # (o cartão, sem a barra); "vazio"; "sem_player" (outra tela).
        self.player, self.olhadas_no_player = player, 0

    def _nos(self):
        if self.atual == "removido":
            return [_no("Detalhes do Vídeo", caixa=(300, 1160, 780, 1220), clicavel=False),
                    _no("Este vídeo foi removido pelo criador", caixa=(200, 1240, 880, 1280), clicavel=False)]
        if self.atual == "player":
            self.olhadas_no_player += 1
            if self.player == "sem_player":
                return [_no("Para você", caixa=(640, 140, 830, 195), clicavel=False)]
            nos = [_no(ident=robo.PLAYER_DO_VIDEO, caixa=(0, 0, 1080, 2260), clicavel=False)]
            if self.player in ("um_produto", "so_cartao"):
                nos.append(_cartao(PRODUTO_A, 1600))
            if self.player == "um_produto":
                # A barra embaixo do vídeo com o desconto e o nome (Motorola, 24/10/2026).
                nos.append(_no(desc="shopee video product icon", caixa=(30, 2050, 820, 2110), filhos=(
                    _no("-20% de desconto", caixa=(40, 2060, 300, 2100), clicavel=False)
                    + _no("Garrafa Térmica Inox de 1 Litro", caixa=(320, 2060, 810, 2100), clicavel=False))))
            elif self.player == "normal" or (self.player == "lento" and self.olhadas_no_player > 1):
                nos.append(_no("Ver Produtos (2)", caixa=(400, 1940, 650, 2000)))
            return nos
        if self.atual == "ver_produtos" and self.player == "um_produto":
            return [_no(caixa=(0, 400, 1080, 2400), filhos=(
                _no("Ver Produtos (1)", caixa=(40, 700, 300, 750), clicavel=False)
                + _cartao(PRODUTO_A, 1030)
                + _no("Você Também Pode Gostar", caixa=(300, 1420, 780, 1470), clicavel=False)
                + _cartao(RECOMENDADO, 1500)))]
        if self.atual == "ver_produtos":
            return [_no(caixa=(0, 400, 1080, 2400), filhos=(
                _no("Ver Produtos (2)", caixa=(40, 700, 300, 750), clicavel=False)
                + _cartao(PRODUTO_A, 1030) + _cartao(PRODUTO_B, 1350)
                + _no("Ver Mais (1)", caixa=(400, 1720, 640, 1770))
                + _no("Você Também Pode Gostar", caixa=(300, 1870, 780, 1920), clicavel=False)
                + _cartao(RECOMENDADO, 1940)))]
        if self.atual.startswith("pdp:"):
            nome = self.atual[4:]
            return [_no(ident="buttonItemLiked" if nome in self.curtidos else "buttonItemLike", caixa=(1000, 1510, 1056, 1566)),
                    _no(nome, "labelProductPageProductName", (40, 1850, 1040, 1900), clicavel=False),
                    _no("Compre agora", "buttonProductBuyNow", (600, 2290, 1040, 2370))]
        if self.atual == "curtidas":
            return [_no("Minhas Curtidas", caixa=(300, 410, 510, 460)), _no("Mais Recente", caixa=(300, 520, 510, 570)),
                    _item_curtido(PRODUTO_A, 650, PRODUTO_A in self.anexados),
                    _item_curtido(PRODUTO_B, 930, PRODUTO_B in self.anexados)]
        if self.atual == "janela":
            return [_no("Editar nome do produto", caixa=(300, 1310, 780, 1370), clicavel=False),
                    _no(self.janela, caixa=(360, 1450, 1040, 1510), clicavel=False), _no("Feito", caixa=(480, 2290, 600, 2340))]
        if self.atual == "final":
            nos = _tela_final(robo.ps.como_o_android_le(self.legenda))
            for i, nome in enumerate(self.anexados):
                nos.append(_no(nome, "tv_product_title", (40 + 500 * i, 820, 500 + 500 * i, 880), clicavel=False))
            if self.anexados:
                nos.append(_no("Adicionar Mais", "tv_add_more", (800, 700, 980, 760)))
            return nos
        return super()._nos()

    def shell(self, partes):
        resposta = super().shell(partes)
        if "android.intent.action.VIEW" in partes:
            self.atual = "removido" if self.removido else "player"
        return resposta

    def screenshot(self, caminho=None):
        if caminho:
            return super().screenshot(caminho)
        # A página do produto: a foto no alto (de uma cor por produto) e a linha do preço embaixo.
        from PIL import Image
        cor = {"pdp:" + PRODUTO_A: "blue", "pdp:" + PRODUTO_B: "pink"}.get(self.atual, "white")
        self.prints_da_pagina = getattr(self, "prints_da_pagina", []) + [self.atual]
        return Image.new("RGB", (1080, 2400), cor)

    def click(self, x, y):
        tocados = [el for el in robo.ps.elementos(self.dump_hierarchy()) if robo.ps._dentro((x, y), el["caixa"])]
        textos = {el["texto"] for el in tocados} | {"@" + el["id"] for el in tocados if el["id"]}
        assert not any(robo.ps.texto_proibido(t) for t in textos), f"tocou num botão de comprar: {textos}"
        if self.atual == "player" and ("Ver Produtos (2)" in textos
                                       or any(el["descricao"] == "shopee video product icon" for el in tocados)):
            self.atual = "ver_produtos"
        elif self.atual == "ver_produtos":
            nome = next((t for t in textos if t in (PRODUTO_A, PRODUTO_B, RECOMENDADO)), None)
            self.toques.append(nome or (x, y))
            if nome:
                self.atual = "pdp:" + nome
            return
        elif self.atual.startswith("pdp:") and "@buttonItemLike" in textos:
            self.curtidos.add(self.atual[4:])
            self.ja_curtidos.add(self.atual[4:])
        elif self.atual.startswith("pdp:") and "@buttonItemLiked" in textos:
            self.curtidos.discard(self.atual[4:])
        elif self.atual == "final" and "@tv_add_more" in textos:
            self.atual = "curtidas"
        elif self.atual == "final" and "@ll_add_product_symbol" in textos:
            self.atual = "curtidas"
        elif self.atual == "curtidas" and "Adicionar" in textos:
            self.janela = PRODUTO_A if y < 930 else PRODUTO_B       # o item de cima é o A
            self.atual = "janela"
        elif self.atual == "janela" and "Feito" in textos:
            self.anexados.append(self.janela)
            self.atual = "final"
        else:
            return super().click(x, y)
        self.toques.append(next((t for t in textos if t.startswith("@")), next(iter(textos), (x, y))))

    def press(self, tecla, meta=None):
        if meta or tecla != "back" or not (self.atual.startswith("pdp:") or self.atual in ("ver_produtos", "player")):
            return super().press(tecla, meta)
        self.teclas.append(tecla)
        self.atual = {"ver_produtos": "player", "player": "inicio"}.get(self.atual, "ver_produtos")


def _fonte_de_video(monkeypatch, confirma=(PRODUTO_A, PRODUTO_B), outra_cor=()):
    _fonte(monkeypatch)
    inserir("UPDATE fila_autorais SET legenda = ?", f"Garrafa 🧴\n{LINK_DE_VIDEO}")

    async def converter(link):
        return "https://sv.shopee.com.br/share-video/AAAA" if link == LINK_DE_VIDEO else "https://shopee.com.br/product/1/2"

    async def produtos_do_link(link):
        return [], link       # link de vídeo: a API não diz os produtos

    async def analisar(arquivo, prompt, imagens=None):
        # Os produtos da criadora a IA confere pela foto da página de cada um (01/11), em JPEG.
        assert imagens is None or imagens[0][0].startswith(b"\xff\xd8")
        confere = any(nome in prompt for nome in confirma)
        cor = any(nome in prompt for nome in outra_cor)
        return '{"confere": %s, "outra_cor": %s, "motivo": "a IA viu no vídeo"}' % (
            "true" if confere else "false", "true" if cor else "false")

    async def buscar(termo, limite=10, sort_type=2):
        # A API acha o 1º produto pelo nome; o 2º, não (o rascunho diz que falta o link dele).
        return [{"itemId": 11, "productName": PRODUTO_A, "productLink": "https://shopee.com.br/product/1/11"}]

    async def encurtar(link, etiqueta, avisar_falha=True):
        return "https://s.shopee.com.br/curto-" + link.rsplit("/", 1)[-1]

    monkeypatch.setattr(robo, "link_para_converter", converter)
    monkeypatch.setattr(robo.ps, "link_para_converter", converter)
    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)
    monkeypatch.setattr(robo.ps.api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", buscar)
    monkeypatch.setattr(robo.api_shopee, "converter_link_shopee", encurtar)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True, "fonte": "autorais"})


def test_link_de_video_curte_e_anexa_todos_os_produtos_que_a_ia_confirma(monkeypatch, avisos):
    # Escolha do Rafael (23/10): no Ver Produtos, todos os produtos do criador que a IA
    # confirmar; nunca os de "Você Também Pode Gostar" nem um botão de comprar.
    _fonte_de_video(monkeypatch)
    app = AppDoVerProdutos()
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.ja_curtidos == {PRODUTO_A, PRODUTO_B} and app.anexados == [PRODUTO_A, PRODUTO_B]
    # No fim do rascunho, as curtidas que o robô deu saem (pedido do Rafael, 24/10).
    assert app.curtidos == set()
    assert RECOMENDADO not in app.toques
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["produtos"] == [PRODUTO_A, PRODUTO_B]
    assert len(robo.json.loads(rascunho["conferencia"])) == 4          # 2 conferências por produto
    assert "os do Ver Produtos" in avisos[0]
    # Pedido do Rafael (29/10, P83): o link de cada produto anexado, para ele conferir no
    # rascunho; o que a API não acha pelo nome fica sem.
    assert rascunho["links_dos_produtos"] == ["https://s.shopee.com.br/curto-11", ""]



def test_ver_produtos_de_outra_cor_entra_e_a_foto_dele_vai_na_miniatura(monkeypatch, avisos):
    # Pedido do Rafael (01/11): num post de Ver Produtos, um dos produtos da criadora era o mesmo
    # puff em outra cor, e a IA, que conferia só pelo nome, deixou passar sem ninguém saber. Agora
    # ela confere cada produto pela foto da página dele no app: o mesmo modelo em outra cor entra,
    # e a foto dele vai na miniatura que troca, para aparecer no vídeo; outro produto fica de fora.
    import io
    from PIL import Image
    _fonte_de_video(monkeypatch, outra_cor=(PRODUTO_A,))
    edicao = {}

    def copiar(video, fonte, copia, nomes=(), alcool=False, outras=(), figurinha=None):
        edicao.update(nomes=list(nomes), outras=list(outras))
        robo.shutil.copyfile(video["arquivo"], copia)
        return ""

    monkeypatch.setattr(robo, "copiar_para_o_rascunho", copiar)
    app = AppDoVerProdutos()
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    # A IA viu a página de cada produto.
    assert app.prints_da_pagina == ["pdp:" + PRODUTO_A, "pdp:" + PRODUTO_B]
    # O de outra cor (o A, 1º da lista da criadora) vai depois do da mesma cor do vídeo: o 1º
    # anexado dá a foto do começo do vídeo.
    assert app.anexados == [PRODUTO_B, PRODUTO_A] and edicao["nomes"] == [PRODUTO_B, PRODUTO_A]
    # A foto da página do A (a cor dele) vai para a miniatura.
    assert len(edicao["outras"]) == 1
    assert Image.open(io.BytesIO(edicao["outras"][0])).convert("RGB").getpixel((10, 10))[2] > 200
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DO_CRIADOR, "2000-01-01 00:00:00")
    assert sorted(r[2] for r in registro) == ["mesmo produto", "outra cor - a foto vai na miniatura"]


def test_ver_produtos_de_outro_produto_fica_de_fora(monkeypatch, avisos):
    # O produto da criadora que a IA não confirma pela foto da página (outro produto) fica de fora.
    _fonte_de_video(monkeypatch, confirma=(PRODUTO_A,))
    app = AppDoVerProdutos()
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.anexados == [PRODUTO_A]
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DO_CRIADOR, "2000-01-01 00:00:00")
    assert [r[2] for r in registro] == ["mesmo produto", "de fora - outro produto"]


def test_ver_produtos_sem_a_foto_da_pagina_fica_de_fora(monkeypatch, avisos):
    # Sem a foto da página (o print não veio), o produto fica de fora: nada entra só pelo nome.
    class SemPrint(AppDoVerProdutos):
        def screenshot(self, caminho=None):
            if caminho is None and self.atual == "pdp:" + PRODUTO_B:
                raise OSError("o print não veio")
            return super().screenshot(caminho)

    _fonte_de_video(monkeypatch)
    app = SemPrint()
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.anexados == [PRODUTO_A]
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DO_CRIADOR, "2000-01-01 00:00:00")
    assert [r[2] for r in registro] == ["mesmo produto", "de fora - sem a foto da página"]


def test_link_de_cada_produto_do_ver_produtos_nunca_troca_um_pelo_outro(monkeypatch):
    # Pedido do Rafael (29/10, P83): no rascunho de Ver Produtos, um link para cada produto, para
    # ele conferir que bate com o produto. No vídeo dele, eram duas cortinas de nome quase igual,
    # de lojas diferentes: o anúncio que a API acha fica com o produto de nome igual ao dele, e o
    # outro fica sem link, em vez de ganhar o link errado.
    cortina_a = "Cortina Jacquard 2,00m x 1,35m Sala Quarto Cozinha Semi Blackout Premium"
    cortina_b = "Cortina Jacquard 2,00m x 1,35m Sala E Quarto Cozinha Semi Blackout"
    etiquetas = []

    async def buscar(termo, limite=10, sort_type=2):
        assert sort_type == 1
        return [{"itemId": 7, "productName": cortina_a, "productLink": "https://shopee.com.br/product/1/7"}]

    async def encurtar(link, etiqueta, avisar_falha=True):
        etiquetas.append((etiqueta, avisar_falha))
        return "https://s.shopee.com.br/curto-" + link.rsplit("/", 1)[-1]

    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", buscar)
    monkeypatch.setattr(robo.api_shopee, "converter_link_shopee", encurtar)
    assert robo.links_do_ver_produtos([cortina_b, cortina_a, "Abajur de Mesa Articulado"]) == [
        "", "https://s.shopee.com.br/curto-7", ""]
    assert etiquetas == [(robo.api_shopee.ETIQUETA_SHOPEE_VIDEO, False)]
    # Com os dois anúncios na busca, cada produto fica com o seu.
    outra = {"itemId": 8, "productName": cortina_b, "productLink": "https://shopee.com.br/product/1/8"}

    async def buscar_os_dois(termo, limite=10, sort_type=2):
        return [{"itemId": 7, "productName": cortina_a, "productLink": "https://shopee.com.br/product/1/7"}, outra]

    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", buscar_os_dois)
    assert robo.links_do_ver_produtos([cortina_b, cortina_a]) == [
        "https://s.shopee.com.br/curto-8", "https://s.shopee.com.br/curto-7"]

    # A API fora: o rascunho sai, sem os links (o Rafael confere pelo vídeo original).
    async def fora(termo, limite=10, sort_type=2):
        raise RuntimeError("fora do ar")

    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", fora)
    assert robo.links_do_ver_produtos([cortina_a]) == [""]
    # Escolha do Rafael (30/10, P105): o registro conta, por rascunho, os links com o nome igual ao
    # do app, com o nome parecido e os que ficaram sem, para o Claude conferir se a busca acerta
    # antes de perguntar de novo da miniatura do Ver Produtos.
    import registro_processos as rp
    registros = sorted((l[2], l[3], l[4], l[5]) for l in rp.contagem("2000-01-01 00:00:00")
                       if l[1] == robo.PROCESSO_DOS_LINKS_DO_VER_PRODUTOS)
    assert registros == [("achados em parte", "1 com o nome igual, 0 com o nome parecido, 2 sem", None, 1),
                         ("nenhum achado", "0 com o nome igual, 0 com o nome parecido, 1 sem", None, 1),
                         ("todos achados", "2 com o nome igual, 0 com o nome parecido, 0 sem", 1, 1)]
    assert robo.links_do_ver_produtos([]) == [] and len(rp.contagem("2000-01-01 00:00:00")) == 3


def test_o_0_do_selo_colado_no_nome_nao_atrapalha_a_busca_na_api(monkeypatch):
    # Caso das 18:04 de 29/10 (e o das 00:32): no Ver Produtos, o selo da loja chegou como um "0"
    # colado no nome ("0Tênis ..."); a busca ia com "0Tênis" e a foto do 1º produto não vinha, e
    # o vídeo ficava de lado na edição.
    nome = "Tênis Feminino Slip On Casual Conforto Esportivo Amortecedor"
    termos = []

    async def buscar(termo, limite=10, sort_type=2):
        termos.append(termo)
        if termo.startswith("0"):
            return []
        return [{"itemId": 9, "productName": nome, "productLink": "https://shopee.com.br/product/1/9",
                 "imageUrl": "https://cf.shopee.com.br/foto"}]

    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", buscar)
    monkeypatch.setattr(robo.ps, "baixar_foto", lambda endereco: "/tmp/foto.jpg" if endereco else None)
    assert robo.termo_da_busca("0" + nome) == "Tênis Feminino Slip On Casual Conforto"
    assert robo.oferta_pelo_nome("0" + nome)["itemId"] == 9
    assert robo.anuncio_do_ver_produtos("0" + nome) == {"foto": "/tmp/foto.jpg", "nome": "0" + nome}
    assert not any(t.startswith("0") for t in termos)


def test_a_foto_do_ver_produtos_que_nao_vem_fica_no_registro_com_o_porque(monkeypatch):
    # Caso das 17:29 de 30/10: o vídeo de Ver Produtos ficou de lado sem a foto do 1º produto, e o
    # registro não dizia se a busca pelo nome não achou nada, achou um nome pouco parecido ou se
    # a foto não baixou.
    import registro_processos as rp
    nome = "Tênis Feminino Slip On Casual Conforto Esportivo Amortecedor"
    respostas = {
        "nada": [],
        "outro": [{"itemId": 1, "productName": "Sandália Rasteira Feminina Conforto",
                   "imageUrl": "https://cf.shopee.com.br/outra"}],
        "igual": [{"itemId": 2, "productName": nome, "imageUrl": "https://cf.shopee.com.br/foto"}],
        "quebrada": [{"itemId": 3, "productName": nome, "imageUrl": "https://cf.shopee.com.br/quebrada"}]}
    vez = []

    async def buscar(termo, limite=10, sort_type=2):
        return respostas[vez[-1]]

    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", buscar)
    monkeypatch.setattr(robo.ps, "baixar_foto", lambda endereco: None if "quebrada" in endereco else "/tmp/foto.jpg")
    esperado = {"nada": {}, "outro": {}, "igual": {"foto": "/tmp/foto.jpg", "nome": nome},
                "quebrada": {"foto": None, "nome": nome}}
    for caso, anuncio in esperado.items():
        vez.append(caso)
        assert robo.anuncio_do_ver_produtos(nome) == anuncio, caso
    registros = sorted((l[2], l[3], l[4]) for l in rp.contagem("2000-01-01 00:00:00")
                       if l[1] == robo.PROCESSO_DA_FOTO_DO_VER_PRODUTOS)
    assert registros == [("a foto não baixou", "100% das palavras", 0), ("achada", "100% das palavras", 1),
                         ("nenhuma oferta na busca", "", 0), ("nome pouco parecido", "14% das palavras", 0)]


def test_link_de_video_deixa_de_fora_o_produto_que_a_ia_recusa(monkeypatch, avisos):
    _fonte_de_video(monkeypatch, confirma=(PRODUTO_B,))
    app = AppDoVerProdutos()
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.ja_curtidos == {PRODUTO_B} and app.anexados == [PRODUTO_B] and app.curtidos == set()
    assert robo.esperando_aprovacao()[0]["produtos"] == [PRODUTO_B]
    assert not any("A IA" in str(a) and PRODUTO_A in str(a) for a in avisos)   # recusado não vira aviso


def test_link_de_video_sem_produto_confirmado_fica_de_lado(monkeypatch, avisos):
    _fonte_de_video(monkeypatch, confirma=())
    resultado = robo.rodada(preparar=True, d=AppDoVerProdutos(), agora=momento("2026-10-22 23:59"))
    assert "a IA não confirmou nenhum produto do Ver Produtos" in resultado
    assert robo.listar("pulado")[0]["id_video"] == "a1"


def test_link_de_video_espera_o_ver_produtos_que_demora(monkeypatch, avisos):
    _fonte_de_video(monkeypatch)
    app = AppDoVerProdutos(player="lento")
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.anexados == [PRODUTO_A, PRODUTO_B]


def test_link_de_video_com_um_produto_so_abre_a_lista_pela_barra(monkeypatch, avisos):
    # 24/10/2026 (Preparar 1 Agora do Rafael): o vídeo de um produto só não mostra o "Ver
    # Produtos (N)", só a barra com o nome dele, e o robô desistia. A barra abre a mesma lista.
    _fonte_de_video(monkeypatch)
    app = AppDoVerProdutos(player="um_produto")
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.ja_curtidos == {PRODUTO_A} and app.anexados == [PRODUTO_A] and app.curtidos == set()
    assert RECOMENDADO not in app.toques
    assert robo.esperando_aprovacao()[0]["produtos"] == [PRODUTO_A]


@pytest.mark.parametrize("player, motivo", [
    ("so_cartao", "o vídeo mostrou o cartão de um produto, sem o Ver Produtos"),
    ("vazio", "o link de vídeo não mostrou o Ver Produtos"),
    ("sem_player", "o link de vídeo não abriu o vídeo no app (sem o Ver Produtos)"),
])
def test_link_de_video_sem_ver_produtos_diz_o_que_a_tela_mostrou(monkeypatch, avisos, player, motivo):
    # O motivo é texto fixo, para o investigar_robo.yml mostrar qual dos casos foi.
    _fonte_de_video(monkeypatch)
    app = AppDoVerProdutos(player=player)
    resultado = robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59"))
    # Duas olhadas do robô (a segunda depois da espera) e a do caso guardado para o checkup.
    assert motivo in resultado and app.olhadas_no_player == 3
    pulado = robo.listar("pulado")[0]
    assert pulado["motivo"] == motivo and robo.passo_do_motivo(motivo) == "Ver Produtos"
    import investigar_robo
    assert motivo in investigar_robo.textos_fixos()


def test_link_de_video_removido_fica_de_lado(monkeypatch, avisos):
    _fonte_de_video(monkeypatch)
    resultado = robo.rodada(preparar=True, d=AppDoVerProdutos(removido=True), agora=momento("2026-10-22 23:59"))
    assert "o vídeo do link foi removido" in resultado and robo.listar("pulado")[0]["id_video"] == "a1"


def test_rascunho_de_varios_produtos_so_e_postado_com_todos_na_tela_final(monkeypatch, avisos):
    app = AppDoVerProdutos()
    app.atual, app.anexados = "final", [PRODUTO_A]
    video = {"id": "a1", "arquivo": "x.mp4", "link": LINK_DE_VIDEO, "produtos": [PRODUTO_A, PRODUTO_B]}
    ok, motivo = robo.ps.conferir_tela_final(app, video)
    assert not ok and "1 produto(s) anexado(s)" in motivo
    app.anexados = [PRODUTO_B, PRODUTO_A]
    assert robo.ps.conferir_tela_final(app, video)[0]
    app.anexados = [PRODUTO_A, PRODUTO_B, RECOMENDADO]
    assert not robo.ps.conferir_tela_final(app, video)[0]


# --- Conta de Shopee Vídeo suspensa pela Shopee ---

BANIDA = ("Sua conta foi banida temporariamente até 26-10-2026 19:04:26 devido à violação das Diretrizes da "
          "Comunidade da Shopee Vídeo. Você não poderá publicar conteúdos em Shopee Vídeo durante o período "
          "de suspensão.")


@pytest.fixture
def conta_suspensa(monkeypatch):
    """O Postar vídeo não abre nada, e as Notificações mostram o aviso da suspensão (Motorola, 23/10/2026)."""
    monkeypatch.setitem(CAMINHO, ("perfil", "Postar vídeo"), "perfil")
    monkeypatch.setitem(TELAS, "notificacoes_videos",
                        TELAS["notificacoes_videos"] + [_no(BANIDA, caixa=(40, 1100, 1040, 1300), clicavel=False)])


def test_suspensao_na_tela_le_o_fim_e_ignora_a_que_ja_acabou():
    agora = momento("2026-10-23 19:30")
    fim = robo.suspensao_na_tela(_xml(_no(BANIDA, clicavel=False)), agora)
    assert fim == datetime(2026, 10, 26, 19, 4, 26, tzinfo=fuso_horario)
    assert robo.suspensao_na_tela(_xml(_no(BANIDA, clicavel=False)), momento("2026-10-26 19:05")) is None
    # Com duas, vale a que acaba por último; sem o "publicar", não é a suspensão.
    outra = BANIDA.replace("26-10-2026 19:04:26", "29-10-2026 08:00:00")
    assert robo.suspensao_na_tela(_xml(_no(BANIDA), _no(outra)), agora).day == 29
    assert robo.suspensao_na_tela(_xml(_no("Sua conta foi verificada até 26-10-2026 19:04:26 e pode publicar")),
                                  agora) is None
    # O mesmo aviso, como a Saúde do Vídeo mostra.
    saude = "Seu acesso para postar vídeos foi banido até 26/10/2026 19:04:26 devido a múltiplas violações. Ver Detalhes"
    assert robo.suspensao_na_tela(_xml(_no(saude, clicavel=False)), agora) == fim


def test_conta_suspensa_para_o_rascunho_avisa_uma_vez_e_nao_toca_ate_o_fim(monkeypatch, avisos, conta_suspensa):
    # Escolha do Rafael (23/10, P4): pausar robô e assistente, avisar com a data e voltar sozinho.
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    app = AppDeMentira()
    resultado = robo.rodada(d=app, agora=momento("2026-10-23 23:59"))
    assert resultado == "conta de Shopee Vídeo suspensa pela Shopee até 26/10 às 19:04"
    config = robo.ler_config()
    assert config["robo_suspenso_ate"] == "2026-10-26 19:04:26" and config["robo_pausado"] is False
    assert "Biblioteca" not in app.toques and "@tv_drafts_box" not in app.toques
    # Primeiro o "começando um rascunho"; depois só o aviso da suspensão, sem o "não saiu".
    assert len(avisos) == 2 and "26/10 às 19:04" in avisos[1] and "voltam sozinhos" in avisos[1]
    assert not any("o rascunho não saiu" in a for a in avisos)
    # O horário não volta, e o vídeo volta para a fila (o problema não era dele).
    assert robo.estado_do_dia(config, momento("2026-10-23 23:59")).get("repetir") is False
    assert robo.proximo_video(config)["id"] == "a1"
    assert robo.tentativas_desde("2026-10-23 00:00:00")[0]["resultado"] == "suspensa"
    # Até o fim (com a folga), nem a rodada nem o Preparar 1 Agora preparam ou postam (o resto
    # continua: aqui não há mais nada a fazer, e o celular não é tocado).
    robo.gravar_estado(saude_tentada_em="2026-10-24 09:00:00", treino_semana=robo.semana(momento("2026-10-24 10:00")))
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-24 10:00")) == "nada a fazer agora"
    assert len(avisos) == 2
    assert robo.rodada(preparar=True, d=Intocavel(), agora=momento("2026-10-26 19:15")).startswith("conta suspensa")
    assert "não preparei o rascunho" in avisos[-1] and "26/10 às 19:04" in avisos[-1]


def test_aprovado_espera_a_suspensao_sem_tocar_em_postar(monkeypatch, avisos, caminho_do_rascunho, conta_suspensa):
    ident = _aprovado(monkeypatch)
    app = AppComQuadros()
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(d=app, agora=momento("2026-10-23 19:30")).startswith("conta de Shopee Vídeo suspensa")
    assert "@btn_post" not in app.toques and "Rascunhos: 1" not in app.toques
    assert robo.pegar(ident)["estado"] == "aprovado" and len(avisos) == 1 and "26/10 às 19:04" in avisos[0]


def test_sem_suspensao_o_aprovado_e_postado_depois_de_olhar_as_notificacoes(monkeypatch, avisos, caminho_do_rascunho):
    ident = _aprovado(monkeypatch)
    app = AppComQuadros()
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(d=app, agora=momento("2026-10-23 19:30")) == "rascunho aprovado postado"
    # Olhou as Notificações (rolou a lista procurando o aviso) e só então postou.
    assert app.toques.index("Lives, Vídeos e Afiliados") < app.toques.index("@btn_post")
    assert app.toques.count("rolar") == robo.ROLADAS_NAS_NOTIFICACOES and robo.pegar(ident)["estado"] == "postado"
    assert "robo_suspenso_ate" not in robo.ler_config()


def test_fim_da_suspensao_volta_sozinho_e_espalha_os_aprovados(monkeypatch):
    ativar(robo_inicio=8, robo_fim=22, robo_suspenso_ate="2026-10-26 19:04:26")
    um = _rascunho("aprovado", postar_em="2026-10-24 10:00:00")
    dois = _rascunho("aprovado", postar_em="2026-10-24 11:00:00")
    assert robo.fim_da_suspensao(momento("2026-10-26 19:10")) is None          # ainda na folga
    aviso = robo.fim_da_suspensao(momento("2026-10-26 19:20"))
    assert "acabou" in aviso and "Voltei a preparar e postar" in aviso and "2 aprovado(s)" in aviso
    assert "robo_suspenso_ate" not in robo.ler_config() and robo.fim_da_suspensao(momento("2026-10-26 19:35")) is None
    horas = sorted(robo.pegar(i)["postar_em"] for i in (um, dois))
    assert horas[0] > "2026-10-26 19:20:00"
    distancia = (datetime.strptime(horas[1], "%Y-%m-%d %H:%M:%S") - datetime.strptime(horas[0], "%Y-%m-%d %H:%M:%S"))
    assert distancia.total_seconds() >= robo.INTERVALO_DAS_POSTAGENS[0] * 60


def test_quem_pausou_na_suspensao_continua_pausado_no_fim():
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True, "pausado": False,
                                              "robo_suspenso_ate": "2026-10-26 19:04:26"})
    aviso = robo.fim_da_suspensao(momento("2026-10-26 19:20"))
    assert "continua pausado" in aviso and "assistente volta" in aviso
    assert robo.ler_config()["robo_pausado"] is True


def test_treino_na_conta_suspensa_avisa_a_suspensao_e_nao_que_o_app_mudou(monkeypatch, avisos, conta_suspensa):
    resultado = robo.rodada(treino=True, d=AppDeMentira(), agora=momento("2026-10-23 19:30"))
    assert resultado.startswith("conta de Shopee Vídeo suspensa")
    assert robo.ler_estado()["treino_resultado"].startswith("conta de Shopee Vídeo suspensa")
    assert len(avisos) == 1 and "algo mudou" not in str(avisos) and "26/10 às 19:04" in avisos[0]


# --- Saúde do Vídeo e apelação (mapeada no Motorola em 24/10/2026) ---

SAUDE_BANIDO = ("Seu acesso para postar vídeos foi banido até 26/10/2026 19:04:26 devido a múltiplas violações. "
                "Ver Detalhes")
EXPLICACAO = ("Conteúdos publicados devem promover de forma clara e direta o mesmo produto do anúncio vinculado.")


def _punicao_na_lista(tipo, data, status, y):
    return [_no(tipo, caixa=(300, y, 1000, y + 40), clicavel=False),
            _no(f"Data de Punição: {data}", caixa=(300, y + 50, 1000, y + 90), clicavel=False),
            _no(f"Status da Apelação: {status}", caixa=(300, y + 100, 1000, y + 140), clicavel=False)]


def _removido(titulo, postado, apelar=True):
    return ([_no("Removido", caixa=(400, 460, 680, 510), clicavel=False),
             _no("O vídeo violou nossas Diretrizes da Comunidade.", caixa=(100, 540, 980, 580), clicavel=False),
             _no(titulo, caixa=(300, 760, 1000, 810), clicavel=False),
             _no(f"Postado em: {postado}.", caixa=(300, 890, 1000, 930), clicavel=False),
             _no(EXPLICACAO, caixa=(60, 1000, 1020, 1250), clicavel=False)]
            + ([_no(caixa=(40, 1280, 1040, 1340), filhos=_no("Apelar aqui.", caixa=(60, 1300, 430, 1350),
                                                              clicavel=False))] if apelar else []))


TELAS_DA_SAUDE = {
    "centro": [_no("Live e Vídeo", caixa=(100, 180, 520, 240), clicavel=False),
               _no("Saúde do Vídeo", caixa=(60, 1330, 380, 1385), clicavel=False),
               _no("Melhoria Necessária", caixa=(640, 1330, 980, 1385)),
               _no("O acesso para postagem de vídeos está temporariamente bloqueado.", caixa=(40, 1410, 1040, 1470))],
    "saude": ([_no("Saúde do Vídeo", caixa=(400, 180, 700, 220), clicavel=False),
               _no("Banido Temporariamente", caixa=(400, 410, 760, 450), clicavel=False),
               _no(SAUDE_BANIDO, caixa=(60, 500, 1020, 580), clicavel=False),
               _no("Ponto de Penalidade", caixa=(380, 1010, 700, 1050), clicavel=False),
               _no("6", caixa=(510, 1090, 570, 1150), clicavel=False),
               _no("Vídeos de Violação", caixa=(380, 1860, 700, 1900), clicavel=False)]
              + _punicao_na_lista("Produto Irrelevante", "23/10/2026 19:04:25", "Não Recorrido", 1950)
              + _punicao_na_lista("Contrafeito", "06/10/2026 22:44:53", "Bem-sucedido", 2110)
              + _punicao_na_lista("Violação de Propriedade Intelectual", "18/10/2026 20:20:56", "Não Recorrido", 2260)),
    "removido_1": _removido(robo.ps.como_o_android_le(TITULO), "18:46:10 2026-10-23"),
    "removido_3": _removido("Organizador de Gaveta #casa", "20:20:00 2026-10-18"),
}


class AppDaSaude(AppDeMentira):
    """O app de mentira com o Centro do criador, a Saúde do Vídeo e a tela Removido de cada punição."""

    CAMINHO = {("perfil", "Centro do criador"): "centro", ("centro", "Melhoria Necessária"): "saude",
               ("saude", "Produto Irrelevante"): "removido_1",
               ("saude", "Violação de Propriedade Intelectual"): "removido_3",
               ("saude", "Contrafeito"): "removido_2"}

    def _nos(self):
        if self.atual in TELAS_DA_SAUDE:
            return TELAS_DA_SAUDE[self.atual]
        nos = super()._nos()
        if self.atual != "perfil":
            return nos
        # O Perfil como o Motorola mostrou (explorar de 29/10/2026): o número acima de Seguidores.
        return nos + [_no("12", caixa=(430, 310, 520, 360), clicavel=False),
                      _no("Seguindo", caixa=(410, 365, 540, 405), clicavel=False),
                      _no("1,2K", caixa=(650, 310, 750, 360), clicavel=False),
                      _no("Seguidores", caixa=(630, 365, 770, 405), clicavel=False),
                      _no("Centro do criador", caixa=(620, 980, 980, 1040))]

    def click(self, x, y):
        import postador_shopee_video as ps
        tocados = [el for el in ps.elementos(self.dump_hierarchy()) if ps._dentro((x, y), el["caixa"]) and el["texto"]]
        for el in sorted(tocados, key=lambda el: (el["caixa"][2] - el["caixa"][0]) * (el["caixa"][3] - el["caixa"][1])):
            if (self.atual, el["texto"]) in self.CAMINHO:
                self.toques.append(el["texto"])
                self.atual = self.CAMINHO[(self.atual, el["texto"])]
                return
        super().click(x, y)

    def press(self, tecla, meta=None):
        if tecla == "back" and self.atual.startswith("removido"):
            self.teclas.append(tecla)
            self.atual = "saude"
            return
        super().press(tecla, meta)


@pytest.fixture
def ia_da_apelacao(monkeypatch):
    pedidos = []

    async def gerar(prompt):
        pedidos.append(prompt)
        return ("O vídeo mostra o mesmo produto do anúncio: vestido infantil estampado de gatinho, igual em cor e "
                "modelo. Peço a revisão da penalidade.")
    import api_gemini
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", gerar)
    return pedidos


def _postado_pelo_robo():
    ident = _rascunho("postado", postado_em="2026-10-23 18:45:30", fonte="viral",
                      conferencia='["o vestido do vídeo é o do link"]')
    return ident


def test_gerar_apelacao_le_a_saude_acha_o_video_e_escreve_so_o_que_e_verdade(monkeypatch, avisos, ia_da_apelacao):
    # Pedido do Rafael (23/10, P5): o texto do recurso pronto para copiar, de cada punição sem recurso.
    ident = _postado_pelo_robo()
    app = AppDaSaude()
    resultado = robo.rodada(saude=True, d=app, agora=momento("2026-10-24 10:00"))
    assert resultado == "saúde lida: 3 punição(ões) em 30 dias, 2 nova(s)"
    punicoes = {p["tipo"]: p for p in robo.apelacoes.todas()}
    irrelevante = punicoes["Produto Irrelevante"]
    assert irrelevante["situacao"] == "pendente" and irrelevante["rascunho"] == ident and irrelevante["fonte"] == "viral"
    assert irrelevante["texto"].startswith("O vídeo mostra o mesmo produto") and len(irrelevante["texto"]) <= 200
    assert irrelevante["postado_em"] == "18:46:10 2026-10-23"
    # Só um pedido à IA: a de propriedade intelectual, de vídeo que não é dos Autorais, ganha o texto
    # sem autoria, que não passa pela IA (P31).
    assert len(ia_da_apelacao) == 1 and VESTIDO in ia_da_apelacao[0] and "vestido do vídeo" in ia_da_apelacao[0]
    intelectual = punicoes["Violação de Propriedade Intelectual"]
    assert intelectual["texto"].startswith("Sou afiliado da Shopee.") and "outro canal" in intelectual["observacao"]
    assert punicoes["Contrafeito"]["situacao"] == "aceita"
    # Nunca abre o Recurso: só lê a tela Removido e volta.
    assert "Apelar aqui." not in app.toques and "Enviar" not in app.toques
    # A Saúde também mostra a suspensão: guardada e avisada uma vez.
    assert robo.ler_config()["robo_suspenso_ate"] == "2026-10-26 19:04:26"
    assert any("suspendeu a sua conta" in a for a in avisos)
    assert "Pontos de penalidade: 6" in avisos[-1] and "2 nova(s)" in avisos[-1]
    estado = robo.ler_estado()
    assert estado["saude_pontos"] == 6 and estado["saude_punicoes"] == 3
    # De novo: nada novo, a IA não é chamada de novo.
    robo.rodada(saude=True, d=AppDaSaude(), agora=momento("2026-10-24 11:00"))
    assert len(ia_da_apelacao) == 1 and len(robo.apelacoes.todas()) == 3


def test_punicao_sem_apelar_aqui_nao_e_lembrada(monkeypatch, avisos, ia_da_apelacao):
    monkeypatch.setitem(TELAS_DA_SAUDE, "removido_1", _removido("Outro vídeo", "10:00:00 2026-10-05", apelar=False))
    robo.rodada(saude=True, d=AppDaSaude(), agora=momento("2026-10-24 10:00"))
    irrelevante = next(p for p in robo.apelacoes.todas() if p["tipo"] == "Produto Irrelevante")
    assert irrelevante["situacao"] == "encerrada" and "prazo" in irrelevante["observacao"]


def test_saude_uma_vez_por_dia_e_tambem_com_a_conta_suspensa(monkeypatch, avisos, ia_da_apelacao):
    monkeypatch.setattr(robo, "saude_do_dia_pendente", SAUDE_DO_DIA)
    ativar(robo_inicio=0, robo_fim=24, robo_suspenso_ate="2026-10-26 19:04:26")
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-24 10:00")))
    assert robo.rodada(d=AppDaSaude(), agora=momento("2026-10-24 10:00")).startswith("saúde lida")
    # Já leu hoje: com a conta suspensa e nada mais a fazer, não toca mais no celular.
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-24 10:15")) == "nada a fazer agora"
    assert robo.saude_do_dia_pendente(momento("2026-10-25 08:00"))


def test_saude_anota_os_seguidores_do_perfil(monkeypatch, avisos, ia_da_apelacao):
    # Escolha do Rafael (P70): os seguidores, um número por dia, para o checkup ver se sobem.
    monkeypatch.setattr(robo, "saude_do_dia_pendente", SAUDE_DO_DIA)
    ativar(robo_inicio=0, robo_fim=24)
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-24 10:00")))
    assert robo.rodada(d=AppDaSaude(), agora=momento("2026-10-24 10:00")).startswith("saúde lida")
    assert robo.db.ler_config(robo.CHAVE_SEGUIDORES)["dias"] == {"2026-10-24": 1200}


def test_seguidores_na_tela_e_os_dias_guardados():
    perfil = _xml(_no("12", caixa=(430, 310, 520, 360)), _no("Seguindo", caixa=(410, 365, 540, 405)),
                  _no("1,2 mil", caixa=(650, 310, 750, 360)), _no("Seguidores", caixa=(630, 365, 770, 405)))
    assert robo.seguidores_na_tela(perfil) == 1200
    assert robo.seguidores_na_tela(_xml(_no("Seguindo", caixa=(410, 365, 540, 405)))) is None
    sem_numero = _xml(_no("Seguidores", caixa=(630, 365, 770, 405)))
    assert robo.anotar_seguidores(sem_numero, momento("2026-10-24 10:00")) is None
    assert robo.db.ler_config(robo.CHAVE_SEGUIDORES, {}) == {}
    for dia in range(1, 31):
        robo.anotar_seguidores(perfil, momento(f"2026-10-{dia:02d} 10:00"))
    for dia in range(1, 10):
        robo.anotar_seguidores(perfil, momento(f"2026-11-{dia:02d} 10:00"))
    dias = robo.db.ler_config(robo.CHAVE_SEGUIDORES)["dias"]
    assert len(dias) == robo.DIAS_DOS_SEGUIDORES and min(dias) == "2026-10-05" and max(dias) == "2026-11-09"


def test_saude_que_nao_abre_nao_toma_as_rodadas_do_dia(monkeypatch, avisos):
    monkeypatch.setattr(robo, "saude_do_dia_pendente", SAUDE_DO_DIA)
    ativar(robo_inicio=0, robo_fim=24)
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-24 10:00")))
    # O app de mentira comum não tem o Centro do criador: a leitura para.
    assert "saude: parado" in robo.rodada(d=AppDeMentira(), agora=momento("2026-10-24 10:00"))
    assert robo.o_que_fazer(robo.ler_config(), momento("2026-10-24 10:15")) != ("saude", None)


def test_aviso_de_penalidade_nas_notificacoes_pede_a_saude_de_novo():
    robo.gravar_estado(saude_lida_em="2026-10-24 08:00:00", saude_tentada_em="2026-10-24 08:00:00",
                       penalidade_vista_em="2026-10-24 09:00:00")
    assert not robo.saude_pedida_pela_notificacao(momento("2026-10-24 10:00"))     # leu há menos de 6 h
    assert robo.saude_pedida_pela_notificacao(momento("2026-10-24 14:30"))
    robo.gravar_estado(saude_tentada_em="2026-10-24 14:31:00")
    assert not robo.saude_pedida_pela_notificacao(momento("2026-10-24 22:00"))     # nada visto depois


def test_punicoes_na_tela_e_tela_removido():
    xml = _xml(*TELAS_DA_SAUDE["saude"])
    punicoes = robo.punicoes_na_tela(xml)
    assert [(p["tipo"], p["data"], p["status"]) for p in punicoes] == [
        ("Produto Irrelevante", "23/10/2026 19:04:25", "Não Recorrido"),
        ("Contrafeito", "06/10/2026 22:44:53", "Bem-sucedido"),
        ("Violação de Propriedade Intelectual", "18/10/2026 20:20:56", "Não Recorrido")]
    assert robo.pontos_de_penalidade(xml) == 6
    # Punição cortada embaixo da tela (sem o status) fica para depois de rolar.
    assert robo.punicoes_na_tela(_xml(*TELAS_DA_SAUDE["saude"][:-1]))[-1]["tipo"] == "Contrafeito"
    detalhe = robo.ler_removido(_xml(*TELAS_DA_SAUDE["removido_3"]))
    assert detalhe == {"titulo": "Organizador de Gaveta #casa", "postado_em": "20:20:00 2026-10-18",
                       "explicacao": EXPLICACAO, "pode_apelar": True}


def test_limpeza_das_4h_aparece_como_limpeza_dos_favoritos():
    # Pedido do Rafael (25/10): no resumo das 22h e no Histórico, "limpeza dos favoritos" no
    # lugar de "descurtido" (no banco fica o resultado de sempre, que o checkup conta).
    texto = robo._contagem([{"resultado": "descurtido"}, {"resultado": "salvo"}])
    assert texto == "✅ 1 salvo | 💔 1 limpeza dos favoritos"


def test_na_suspensao_so_o_preparo_a_postagem_e_o_treino_esperam(monkeypatch, avisos):
    # Pedido do Rafael (25/10): na suspensão, o que não passa pelo Postar vídeo continua
    # (apagar o recusado, a Saúde, as respostas e o feed); o preparo, a postagem e o treino
    # esperam o fim, porque a Shopee fecha o Postar vídeo.
    ativar(robo_inicio=0, robo_fim=24, robo_suspenso_ate="2026-10-29 00:00:00")
    config = robo.ler_config()
    segunda = momento("2026-10-26 10:00")
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    monkeypatch.setattr(robo, "consumir_horarios", lambda config, agora=None: True)
    assert robo.o_que_fazer(config, segunda) is None                      # sem treino, sem rascunho
    monkeypatch.setattr(robo, "respostas_pendentes", lambda agora=None: True)
    assert robo.o_que_fazer(config, segunda) == ("responder", None)
    monkeypatch.setattr(robo, "respostas_pendentes", lambda agora=None: False)
    monkeypatch.setattr(robo, "feed_pendente", lambda agora=None: True)
    assert robo.o_que_fazer(config, segunda) == ("feed", None)
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: True)
    assert robo.o_que_fazer(config, segunda) == ("saude", None)
    monkeypatch.setattr(robo, "listar", lambda *estados: [{"id": 7, "postar_em": "2026-10-26 09:00:00"}])
    # Com um recusado e um aprovado já na hora: apaga o recusado; o aprovado espera o fim.
    assert robo.o_que_fazer(config, segunda) == ("apagar", 7)
    monkeypatch.setattr(robo, "listar", lambda *estados: [] if "recusado" in estados else
                        [{"id": 8, "postar_em": "2026-10-26 09:00:00"}])
    assert robo.o_que_fazer(config, segunda) == ("saude", None)
    # Acabada a suspensão, o treino da segunda e a postagem voltam.
    ativar(robo_inicio=0, robo_fim=24)
    assert robo.o_que_fazer(robo.ler_config(), segunda) == ("treino", None)



def test_treino_da_segunda_na_suspensao_roda_logo_depois_do_fim(monkeypatch, avisos):
    # Escolha do Rafael (P41): o treino da segunda que cai na suspensão roda logo que ela
    # acaba, antes de voltar a preparar e postar, e não fica para a segunda seguinte.
    ativar(robo_inicio=0, robo_fim=24, robo_suspenso_ate="2026-10-28 14:41:00")
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-19 10:00")))
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "reconectar_sozinho", lambda: (False, "fora da tomada"))
    # Domingo, na suspensão: ainda não é o dia do treino, nada fica marcado.
    robo.rodada(agora=momento("2026-10-25 10:00"))
    assert not robo.ler_estado().get("treino_depois_da_suspensao")
    # Segunda, na suspensão e com o celular fora: o treino fica para depois do fim.
    assert "celular fora (esperado)" in robo.rodada(agora=momento("2026-10-26 10:00"))
    assert robo.ler_estado()["treino_depois_da_suspensao"] is True
    config = robo.ler_config()
    assert robo.o_que_fazer(config, momento("2026-10-27 10:00")) != ("treino", None)
    # Quarta, acabada a suspensão: a primeira rodada faz o treino antes de tudo.
    monkeypatch.setattr(robo, "consumir_horarios", lambda config, agora=None: True)
    assert robo.fim_da_suspensao(momento("2026-10-28 15:00"))
    quarta = momento("2026-10-28 15:00")
    assert robo.o_que_fazer(robo.ler_config(), quarta) == ("treino", None)
    # O treino rodou (aqui, parado no primeiro passo): a marca sai, e na quinta o robô volta
    # ao preparo de sempre.
    monkeypatch.setattr(robo, "listar", lambda *estados: (_ for _ in ()).throw(robo.Parada("tela")))
    monkeypatch.setattr(robo, "_print_do_treino", lambda d, legenda: None)
    monkeypatch.setattr(robo, "_sair_sem_salvar", lambda d: None)
    assert robo.treinar(None, quarta) == "treino: mudou (tela)"
    assert robo.ler_estado()["treino_depois_da_suspensao"] is False
    monkeypatch.undo()
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    monkeypatch.setattr(robo, "consumir_horarios", lambda config, agora=None: True)
    assert robo.o_que_fazer(robo.ler_config(), momento("2026-10-29 10:00")) == ("rascunho", None)


def test_celular_fora_na_suspensao_nao_pausa_nem_avisa(monkeypatch, avisos):
    # Pedido do Rafael (24/10): na suspensão ele pode tirar o Motorola do carregador.
    monkeypatch.setattr(robo, "saude_do_dia_pendente", SAUDE_DO_DIA)
    ativar(robo_inicio=0, robo_fim=24, robo_suspenso_ate="2026-10-26 19:04:26")
    tentativas = []
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "reconectar_sozinho",
                        lambda: tentativas.append(1) or (False, "a Depuração por Wi-Fi está desligada no celular"))
    assert "celular fora (esperado)" in robo.rodada(agora=momento("2026-10-24 10:00"))
    assert robo.ler_config()["robo_pausado"] is False and avisos == []
    # Na suspensão o resto continua (pedido do Rafael, 25/10): cada rodada procura o celular de
    # novo, e com ele fora só pula, sem pausar nem avisar.
    assert "celular fora (esperado)" in robo.rodada(agora=momento("2026-10-24 10:15")) and tentativas == [1, 1]
    assert robo.ler_config()["robo_pausado"] is False and avisos == []
    # Acabou a suspensão (com a folga) e o celular não voltou: pausa e avisa, como sempre.
    assert "desconectado" in robo.rodada(agora=momento("2026-10-26 19:30"))
    assert robo.ler_config()["robo_pausado"] is True and "Retomar Postagem" in avisos[-1]


def test_limpeza_das_4h_sem_celular_na_suspensao_fica_no_registro_uma_vez(monkeypatch, avisos):
    # Checkup de 26/10, 04:42: "descurtir tudo (4h): 0 de 1", sem dizer que o celular estava
    # fora da tomada na suspensão (o que o Rafael pode fazer). O registro guarda o porquê.
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    ativar(robo_inicio=8, robo_fim=22, robo_suspenso_ate="2026-10-28 14:41:00")
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "reconectar_sozinho", lambda: (False, "fora da tomada"))

    def anotados():
        return consultar("SELECT COUNT(*), MIN(resultado), MAX(ok) FROM registro_processos "
                         "WHERE processo = 'descurtir tudo (4h)'")
    for hora in ("04:05", "04:20", "04:35"):
        assert "celular fora (esperado)" in robo.rodada(agora=momento(f"2026-10-26 {hora}"))
    assert anotados() == (1, "celular fora na suspensão", None)
    # Fora da hora da limpeza, nada vai ao registro dela; no dia seguinte, de novo uma vez.
    robo.rodada(agora=momento("2026-10-26 10:00"))
    robo.rodada(agora=momento("2026-10-27 04:05"))
    assert anotados()[0] == 2 and avisos == []



def test_aviso_antigo_nas_notificacoes_nao_vale_se_a_saude_nao_mostra_o_bloqueio(monkeypatch, avisos, conta_suspensa):
    # Pedido do Rafael (24/10): o recurso aceito tira a suspensão antes do prazo, mas o aviso
    # antigo continua nas Notificações; quem diz a situação de agora é a Saúde do Vídeo.
    sem_bloqueio = [n for n in TELAS_DA_SAUDE["saude"] if "banido" not in n.casefold() and "Banido" not in n]
    monkeypatch.setitem(TELAS_DA_SAUDE, "saude", sem_bloqueio)
    monkeypatch.setitem(CAMINHO, ("perfil", "Postar vídeo"), "camera")
    app = AppDaSaude()
    assert robo.ler_suspensao(app, momento("2026-10-24 10:00")) is None
    assert robo.suspensao_retirada(datetime(2026, 10, 26, 19, 4, 26, tzinfo=fuso_horario))
    # Da segunda vez nem abre a Saúde: a suspensão já ficou anotada como retirada.
    app = AppDaSaude()
    assert robo.ler_suspensao(app, momento("2026-10-24 11:00")) is None and "Centro do criador" not in app.toques
    # Com o bloqueio na Saúde, vale a data dela.
    robo.db.salvar_config(robo.CHAVE_ESTADO, {})
    monkeypatch.setitem(TELAS_DA_SAUDE, "saude", TELAS_DA_SAUDE["saude"] + [_no(SAUDE_BANIDO, clicavel=False)])
    assert robo.ler_suspensao(AppDaSaude(), momento("2026-10-24 12:00")).day == 26


def _linha_do_rotulo(ligado):
    """A linha do Rótulo de IA na tela final, como no Motorola: nome, explicação embaixo e a chave à direita."""
    return [_no("Salvar no dispositivo", caixa=(40, 1150, 700, 1200), clicavel=False),
            '<node text="" class="android.widget.Switch" clickable="true" checked="false" bounds="[900,1150][1040,1200]"/>',
            _no(robo.ps.ROTULO_DE_IA, caixa=(40, 1300, 700, 1350), clicavel=False),
            _no("Ative isso se o seu vídeo incluir conteúdo gerado por IA", caixa=(40, 1360, 860, 1450), clicavel=False),
            f'<node text="" class="android.widget.Switch" clickable="true" checked="{"true" if ligado else "false"}" '
            'bounds="[900,1340][1040,1390]"/>',
            _no("Compartilhar automaticamente", caixa=(40, 1560, 700, 1610), clicavel=False),
            _no(ident="iv_facebook", caixa=(930, 1550, 1030, 1620))]


class ComRotuloDeIA(AppComQuadros):
    """A tela final com a linha do Rótulo de IA; o toque na chave dela liga ou desliga."""

    def __init__(self, chave_funciona=True):
        super().__init__()
        self.rotulo, self.chave_funciona = False, chave_funciona

    def _nos(self):
        nos = super()._nos()
        return nos + _linha_do_rotulo(self.rotulo) if self.atual in ("final", "final_editando") else nos

    def click(self, x, y):
        if self.atual in ("final", "final_editando") and 900 <= x <= 1040 and 1340 <= y <= 1390:
            self.toques.append("rotulo_ia")
            self.rotulo = self.rotulo != self.chave_funciona
            return
        super().click(x, y)


def test_chave_do_rotulo_de_ia_e_a_da_linha_dele():
    lista = robo.ps.elementos(_xml(*_linha_do_rotulo(True)))
    chave = robo.ps.chave_do_rotulo_de_ia(lista)
    assert robo.ps._centro(chave) == (970, 1365) and chave["marcado"] is True
    assert robo.ps.chave_do_rotulo_de_ia(robo.ps.elementos(_xml(*_tela_final()))) is None


def test_video_feito_por_ia_vai_com_o_rotulo_ligado_e_o_rafael_ve(monkeypatch, avisos, caminho_do_rascunho):
    # Escolha do Rafael (24/10, P8): a IA marca sozinha; claramente IA liga, na dúvida desligado.
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)

    async def textos(arquivo, nome):
        return {"violacao": False, "motivo": "", "feito_por_ia": True, "sinal_ia": "avatar com voz sintética",
                "titulo": TITULO, "comentario": "Amei!"}
    monkeypatch.setattr(robo.assistente, "textos_do_video", textos)
    app = ComRotuloDeIA()
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.rotulo and app.toques.index("rotulo_ia") < app.toques.index("@tv_drafts_box")
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["rotulo_ia"] == "avatar com voz sintética"
    import painel_shopee_video as sv
    assert "Rótulo de IA:</b> ligado. A IA viu: avatar com voz sintética" in sv.texto_rascunho(rascunho, 1, 1)
    # A chave que não muda com o toque, ou a linha que não está na tela: não vai sem o rótulo.
    app = ComRotuloDeIA(chave_funciona=False)
    app.atual = "final"
    ok, motivo = robo.ps.ajustar_rotulo_de_ia(app, True)
    assert not ok and robo.passo_do_motivo(motivo) == "rótulo de IA"
    app = AppComQuadros()
    app.atual = "final"
    assert not robo.ps.ajustar_rotulo_de_ia(app, True)[0] and robo.ps.ajustar_rotulo_de_ia(app, False)[0]


class RotuloEmbaixo(ComRotuloDeIA):
    """Como no Motorola com produto anexado: a linha do Rótulo de IA só aparece depois de rolar."""

    def __init__(self):
        super().__init__()
        self.descida = 0

    def _nos(self):
        nos = super()._nos()
        if self.descida:
            return nos
        return [n for n in nos if n not in _linha_do_rotulo(self.rotulo)]

    def swipe(self, x1, y1, x2, y2, duracao):
        self.toques.append("rolar" if y1 > y2 else "subir")
        self.descida += 1 if y1 > y2 else -1


def test_rotulo_de_ia_embaixo_da_tela_e_achado_rolando_e_a_tela_volta_ao_alto():
    # Visto em 24/10 de madrugada: com o produto anexado, a linha fica abaixo da tela.
    app = RotuloEmbaixo()
    app.atual = "final"
    ok, motivo = robo.ps.ajustar_rotulo_de_ia(app, True)
    assert ok and app.rotulo, motivo
    assert app.toques == ["rolar", "rotulo_ia", "subir"] and app.descida == 0
    # Desligado não rola: fica como o app abre.
    app = RotuloEmbaixo()
    app.atual = "final"
    assert robo.ps.ajustar_rotulo_de_ia(app, False)[0] and app.toques == []
    # Sem a linha em lugar nenhum: rola o máximo, diz o que viu e volta ao alto.
    app = AppComQuadros()
    app.atual = "final"
    ok, motivo = robo.ps.ajustar_rotulo_de_ia(app, True)
    assert not ok and "nem a linha do nome" in motivo and f"{robo.ps.ROLAGENS_DO_ROTULO} rolada(s)" in motivo
    assert app.toques.count("rolar") == 2 * robo.ps.ROLAGENS_DO_ROTULO
    assert robo.passo_do_motivo(motivo) == "rótulo de IA"


# As chaves da tela final como no Motorola em 31/10: desenhos (View) sem clicável nem marcado no
# XML; ligada ou desligada só se vê pela cor no print (a de reutilização vem ligada).
CHAVE_DO_REUSO = (917, 1126, 1038, 1194)
CHAVE_DO_DISPOSITIVO = (917, 1288, 1038, 1356)
CHAVE_DESENHADA = (917, 1495, 1038, 1563)


def _chave_desenhada(ident, caixa):
    x1, y1, x2, y2 = caixa
    return (f'<node text="" resource-id="com.shopee.br.dfpluginshopee16:id/{ident}" class="android.view.View" '
            f'checkable="false" checked="false" clickable="false" bounds="[{x1},{y1}][{x2},{y2}]"/>')


def _linhas_das_chaves_desenhadas():
    return [_no("Permitir a reutilização do conteúdo", ident="tv_allow_reuse", caixa=(42, 1111, 615, 1162),
                clicavel=False),
            _chave_desenhada("allow_reuse_toggle", CHAVE_DO_REUSO),
            _no("Salvar no dispositivo", ident="tv_device_toggle", caixa=(42, 1288, 382, 1339), clicavel=False),
            _chave_desenhada("save_device_toggle", CHAVE_DO_DISPOSITIVO),
            _no(robo.ps.ROTULO_DE_IA, ident="tv_ai_generated_title", caixa=(42, 1434, 885, 1485), clicavel=False),
            _no("Ative isso se o seu vídeo incluir conteúdo gerado por IA", ident="tv_ai_generated_desc",
                caixa=(42, 1490, 885, 1625), clicavel=False),
            _chave_desenhada("ai_generated_toggle", CHAVE_DESENHADA),
            _no(ident="iv_facebook", caixa=(959, 1696, 1038, 1775))]


class ComRotuloDesenhado(ComRotuloDeIA):
    """A tela final do app de hoje: a chave do Rótulo de IA só mostra se está ligada pela cor no print."""

    def _nos(self):
        nos = AppComQuadros._nos(self)
        return nos + _linhas_das_chaves_desenhadas() if self.atual in ("final", "final_editando") else nos

    def click(self, x, y):
        x1, y1, x2, y2 = CHAVE_DESENHADA
        if self.atual in ("final", "final_editando") and x1 <= x <= x2 and y1 <= y <= y2:
            self.toques.append("rotulo_ia")
            self.rotulo = self.rotulo != self.chave_funciona
            return
        AppComQuadros.click(self, x, y)

    def screenshot(self, caminho=None):
        if caminho:
            return super().screenshot(caminho)
        from PIL import Image, ImageDraw
        imagem = Image.new("RGB", (1080, 2400), "white")
        desenho = ImageDraw.Draw(imagem)
        for caixa, ligada in ((CHAVE_DO_REUSO, True), (CHAVE_DO_DISPOSITIVO, False), (CHAVE_DESENHADA, self.rotulo)):
            x1, y1, x2, y2 = caixa
            altura = y2 - y1
            desenho.rounded_rectangle(caixa, radius=altura // 2, fill=(20, 200, 60) if ligada else (226, 226, 226))
            esquerda = x2 - altura if ligada else x1
            desenho.ellipse((esquerda + 5, y1 + 5, esquerda + altura - 5, y2 - 5), fill="white")
        return imagem


def test_chave_desenhada_do_rotulo_de_ia_e_lida_pela_cor_do_print():
    # Retomada de 31/10: o app trocou a chave do rótulo por um desenho sem clicável nem marcado
    # no XML, e dois vídeos com voz sintética ficaram de lado ("a chave não está na tela").
    chave = robo.ps.chave_do_rotulo_de_ia(robo.ps.elementos(_xml(*_linhas_das_chaves_desenhadas())))
    assert chave and chave["id"] == "ai_generated_toggle"
    app = ComRotuloDesenhado()
    app.atual = "final"
    assert robo.ps.ajustar_rotulo_de_ia(app, False) == (True, "Rótulo de IA já desligado") and app.toques == []
    assert robo.ps.ajustar_rotulo_de_ia(app, True) == (True, "Rótulo de IA ligado")
    assert app.rotulo and app.toques == ["rotulo_ia"]
    assert robo.ps.ajustar_rotulo_de_ia(app, True) == (True, "Rótulo de IA já ligado")
    # A chave que não muda com o toque: não vai sem o rótulo.
    app = ComRotuloDesenhado(chave_funciona=False)
    app.atual = "final"
    ok, motivo = robo.ps.ajustar_rotulo_de_ia(app, True)
    assert not ok and robo.passo_do_motivo(motivo) == "rótulo de IA"

    class SemPrint(ComRotuloDesenhado):
        def screenshot(self, caminho=None):
            if caminho:
                return super().screenshot(caminho)
            raise OSError("o print não veio")

    # Sem o print não dá para saber: ligado não vai; desligado fica como o app abre.
    app = SemPrint()
    app.atual = "final"
    ok, motivo = robo.ps.ajustar_rotulo_de_ia(app, True)
    assert not ok and robo.passo_do_motivo(motivo) == "rótulo de IA" and app.toques == []
    assert robo.ps.ajustar_rotulo_de_ia(app, False)[0] and app.toques == []


def test_video_com_voz_de_ia_vai_com_a_chave_desenhada_ligada(monkeypatch, avisos, caminho_do_rascunho):
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)

    async def textos(arquivo, nome):
        return {"violacao": False, "motivo": "", "feito_por_ia": True, "sinal_ia": "narração com voz sintética",
                "titulo": TITULO, "comentario": "Amei!"}
    monkeypatch.setattr(robo.assistente, "textos_do_video", textos)
    app = ComRotuloDesenhado()
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.rotulo and app.toques.index("rotulo_ia") < app.toques.index("@tv_drafts_box")


def test_video_real_fica_com_o_rotulo_desligado(monkeypatch, avisos, caminho_do_rascunho):
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    app = ComRotuloDeIA()
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert not app.rotulo and "rotulo_ia" not in app.toques
    import painel_shopee_video as sv
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["rotulo_ia"] == "" and "Rótulo de IA:</b> desligado" in sv.texto_rascunho(rascunho, 1, 1)
    assert sv.linha_do_rotulo_de_ia(None) == ""      # rascunho de antes da conferência


def test_aprovado_com_rotulo_de_ia_confere_a_chave_antes_de_postar(monkeypatch, avisos, caminho_do_rascunho):
    ident = _aprovado(monkeypatch)
    robo.atualizar(ident, rotulo_ia="avatar com voz sintética")
    app = ComRotuloDeIA()
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(d=app, agora=momento("2026-10-23 19:30")) == "rascunho aprovado postado"
    assert app.rotulo and app.toques.index("rotulo_ia") < app.toques.index("@btn_post")


class SaudeDevagar(AppDaSaude):
    """O Centro do criador e a Saúde do Vídeo, que carregam pela rede, vazios nas primeiras leituras."""

    def __init__(self, leituras_vazias):
        super().__init__()
        self.vazias = dict(leituras_vazias)

    def _nos(self):
        if self.vazias.get(self.atual, 0) > 0:
            self.vazias[self.atual] -= 1
            return []
        return super()._nos()


def test_saude_que_demora_a_carregar_e_esperada():
    # Checkup de 23/10: a leitura da Saúde parou uma vez; as duas telas carregam pela rede.
    app = SaudeDevagar({"centro": 3, "saude": 5})
    robo.abrir_saude(app)
    assert app.atual == "saude"
    with pytest.raises(robo.Parada, match="a Saúde do Vídeo não abriu"):
        robo.abrir_saude(SaudeDevagar({"saude": 50}))
    with pytest.raises(robo.Parada, match="Centro do criador não mostrou"):
        robo.abrir_saude(SaudeDevagar({"centro": 50}))


def test_saude_que_nao_abre_nao_pausa_pelo_aviso_antigo_se_o_postar_abre(monkeypatch, avisos, caminho_do_rascunho,
                                                                          conta_suspensa):
    # O recurso aceito tira a suspensão, mas o aviso antigo fica nas Notificações. Sem a
    # Saúde do Vídeo para confirmar, o teste é o Postar vídeo: abrindo a Biblioteca, a conta
    # não está bloqueada, e o aprovado é postado em vez de esperar até 26/10.
    monkeypatch.setitem(CAMINHO, ("perfil", "Postar vídeo"), "camera")
    ident = _aprovado(monkeypatch)
    app = AppComQuadros()
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(d=app, agora=momento("2026-10-23 19:30")) == "rascunho aprovado postado"
    assert app.toques.index("Postar vídeo") < app.toques.index("@btn_post") and "Biblioteca" not in app.toques
    assert robo.pegar(ident)["estado"] == "postado" and "robo_suspenso_ate" not in robo.ler_config()
    assert robo.suspensao_retirada(datetime(2026, 10, 26, 19, 4, 26, tzinfo=fuso_horario))
    # Com o Postar vídeo fechado, o aviso das Notificações vale, antes de postar e na galeria.
    robo.db.salvar_config(robo.CHAVE_ESTADO, {})
    monkeypatch.setitem(CAMINHO, ("perfil", "Postar vídeo"), "perfil")
    assert robo.ler_suspensao(AppDeMentira(), momento("2026-10-23 20:00")).day == 26
    app = AppDeMentira()
    with pytest.raises(robo.Suspensa):
        robo.ir_ao_perfil(app)
        robo.abrir_galeria(app, momento("2026-10-23 20:00"))
    assert app.toques.count("Postar vídeo") == 1


def test_suspensao_tirada_antes_do_prazo_volta_na_leitura_da_saude(monkeypatch, avisos, ia_da_apelacao):
    sem_bloqueio = [n for n in TELAS_DA_SAUDE["saude"] if "banido" not in n.casefold()]
    monkeypatch.setitem(TELAS_DA_SAUDE, "saude", sem_bloqueio)
    ativar(robo_inicio=8, robo_fim=22, robo_suspenso_ate="2026-10-26 19:04:26")
    aprovado = _rascunho("aprovado", postar_em="2026-10-24 09:00:00")
    robo.rodada(saude=True, d=AppDaSaude(), agora=momento("2026-10-24 10:00"))
    config = robo.ler_config()
    assert "robo_suspenso_ate" not in config and config["robo_pausado"] is False
    assert any("tirou a suspensão antes do prazo" in a for a in avisos)
    assert robo.pegar(aprovado)["postar_em"] > "2026-10-24 10:00:00"


def test_punicao_que_sumiu_da_lista_avisa_que_o_recurso_deu_certo(monkeypatch, avisos, ia_da_apelacao):
    robo.apelacoes.guardar("Produto Irrelevante", "22/10/2026 11:00:00", "Não Recorrido", titulo="Garrafa",
                           agora=momento("2026-10-23 10:00"))
    robo.rodada(saude=True, d=AppDaSaude(), agora=momento("2026-10-24 10:00"))
    sumiu = next(p for p in robo.apelacoes.todas() if p["data_punicao"] == "22/10/2026 11:00:00")
    assert sumiu["situacao"] == "retirada"
    assert any("deu certo" in a and "22/10/2026 11:00:00" in a for a in avisos)



def test_depois_do_ja_recorri_a_saude_e_lida_de_hora_em_hora_ate_o_resultado(monkeypatch, avisos, ia_da_apelacao):
    # Escolha do Rafael (24/10, P6): de hora em hora depois do Já recorri, até sair o resultado.
    ap = robo.apelacoes
    ident = ap.guardar("Produto Irrelevante", "23/10/2026 19:04:25", "Não Recorrido", titulo="Botijão",
                       agora=momento("2026-10-24 09:00"))
    assert not robo.saude_pedida_pelo_recurso(momento("2026-10-24 10:00"))
    ap.marcar(ident, ap.RECORRIDA, momento("2026-10-24 10:00"))
    robo.gravar_estado(saude_tentada_em="2026-10-24 09:30:00")
    assert robo.saude_pedida_pelo_recurso(momento("2026-10-24 10:30"))
    ativar(robo_inicio=0, robo_fim=24)
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-24 10:30")))
    assert robo.o_que_fazer(robo.ler_config(), momento("2026-10-24 10:30")) == ("saude", None)
    # Leu agora: só daqui a 1 h.
    robo.gravar_estado(saude_tentada_em="2026-10-24 10:30:00")
    assert not robo.saude_pedida_pelo_recurso(momento("2026-10-24 11:00"))
    # O resultado saiu (recusado): para de olhar e avisa.
    original = TELAS_DA_SAUDE["saude"]
    monkeypatch.setitem(TELAS_DA_SAUDE, "saude", original[:6]
                        + _punicao_na_lista("Produto Irrelevante", "23/10/2026 19:04:25", "Malsucedido", 1950)
                        + original[9:])
    robo.rodada(saude=True, d=AppDaSaude(), agora=momento("2026-10-24 11:40"))
    assert ap.pegar(ident)["situacao"] == "recusada" and not ap.esperando_resultado(momento("2026-10-24 12:00"))
    assert any("não aceitou o recurso" in a for a in avisos)
    # Já recorri de mais de 7 dias sem resultado: para de olhar.
    outra = ap.guardar("Contrafeito", "20/10/2026 10:00:00", "Não Recorrido", agora=momento("2026-10-20 11:00"))
    ap.marcar(outra, ap.RECORRIDA, momento("2026-10-20 12:00"))
    assert ap.esperando_resultado(momento("2026-10-26 12:00")) and not ap.esperando_resultado(momento("2026-10-28 12:00"))


def test_preparo_interrompido_pelo_reinicio_volta_para_a_fila_na_rodada_seguinte():
    # 24/10/2026: o deploy das 09:42 matou a rodada no meio, e o rascunho ficou em "preparando".
    preso = robo.criar("video:9", momento("2026-10-24 09:42"))
    novo = robo.criar("video:10", momento("2026-10-24 10:20"))
    assert robo.soltar_preparos_interrompidos(momento("2026-10-24 10:30")) == 1
    assert robo.pegar(preso) is None and robo.pegar(novo)["estado"] == "preparando"
    assert "video:9" not in robo.ids_usados()
    assert robo.tentativas_desde("2026-10-24 00:00:00")[0]["passo"] == "rodada interrompida"


def test_preparo_interrompido_guarda_o_caso_com_os_passos_da_rodada_que_morreu():
    # Retomada de 31/10: a rodada das 05:30 morreu no meio do preparo e nada dizia onde.
    import json
    robo.criar("video:9", momento("2026-10-24 09:20"))
    robo.registro_processos.registrar(robo.REGISTRO, "anexar o produto", "anexado", "no topo, pelo nome",
                                      agora=momento("2026-10-24 09:50"))
    assert robo.soltar_preparos_interrompidos(momento("2026-10-24 10:30")) == 1
    casos = robo.casos_robo.casos()
    assert len(casos) == 1
    with open(os.path.join(robo.casos_robo.PASTA, casos[0], "caso.json"), encoding="utf-8") as f:
        caso = json.load(f)
    assert caso["passo"] == "rodada interrompida" and caso["rascunho"]["id_video"] == "video:9"
    assert [linha[1:3] for linha in caso["registro"]][-1] == ["anexar o produto", "anexado"]


def test_horario_do_plano_interrompido_no_meio_tenta_de_novo(monkeypatch):
    # 24/10/2026: os deploys da manhã mataram a rodada no meio do preparo; o vídeo voltou
    # para a fila, mas o horário do plano ficou como feito, e o robô dizia "nada a fazer
    # agora" com horários vencidos sem rascunho.
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    config = {**robo.PADRAO, "robo_pausado": False, "robo_limite_min": 1, "robo_limite_max": 1,
              "robo_inicio": 0, "robo_fim": 24}
    robo.db.salvar_config(robo.CHAVE_CONFIG, config)
    agora = momento("2026-10-27 23:59")
    robo.gravar_estado(treino_semana=robo.semana(agora), respostas_em="2026-10-27 23:59:00",
                       feed_em="2026-10-27 23:59:00")
    assert robo.o_que_fazer(config, agora) == ("rascunho", None)
    # A rodada começa o preparo e morre no meio (o processo é morto: nada depois roda).
    robo._em_preparo(config, agora, True)
    robo.criar("video:9", momento("2026-10-27 23:00"))
    assert robo.o_que_fazer(config, agora) is None
    assert robo.soltar_preparos_interrompidos(agora) == 1
    assert robo.o_que_fazer(config, agora) == ("rascunho", None)
    # Só uma vez: a marca saiu.
    robo.soltar_preparos_interrompidos(agora)
    assert robo.o_que_fazer(config, agora) is None


# --- Descurtir tudo às 4h (escolha do Rafael, P25) ---

CAIXA = robo.CAIXA_DE_MARCAR


class AppDosFavoritos(AppDeMentira):
    """
    Eu → Criadores & Afiliados → Meus favoritos, como o Rafael mostrou no Motorola (25/10/2026):
    o título com quantos há (até 1000), o filtro Melhor Oferta e o aviso com Substituir Tudo no
    alto, 5 produtos por tela, cada um com a caixa de marcar; na barra de baixo, a caixa de
    marcar tudo, o "Selecionado N/50", o Like (tira os marcados) e o Compartilhar. O Meus
    Favoritos de comprador da aba Eu é outra lista: o robô não pode ir para lá.
    marcar_tudo=False: a caixa de baixo não marca nada, e o robô marca um por um, rolando.
    invalidos: as posições dos produtos que saíram da loja, com o selo Inválido na foto, que o
    Like não tira e que continuam marcados depois dele (Motorola, 29/10/2026). Na linha dos
    filtros há também o filtro Inválido.
    """

    def __init__(self, favoritos=6, marcar_tudo=True, invalidos=()):
        super().__init__()
        self.favoritos = [f"Produto {i}" for i in range(favoritos)]
        self.invalidos = {f"Produto {i}" for i in invalidos}
        self.marcados, self.marcar_tudo, self.topo = [], marcar_tudo, 0

    def _visiveis(self):
        return self.favoritos[self.topo:self.topo + 5]

    def _nos(self):
        if self.atual == "eu":
            return [ABA_EU, _no("Criadores & Afiliados", caixa=(600, 1630, 1000, 1700)),
                    _no("Meus Favoritos", caixa=(600, 1990, 950, 2060))]
        if self.atual == "afiliado":
            return [_no("Meus favoritos", caixa=(660, 680, 830, 760)), _no("Oferta", caixa=(60, 2300, 210, 2400)),
                    _no("Conversão", caixa=(330, 2300, 480, 2400)), _no("Conta", caixa=(870, 2300, 1020, 2400))]
        if self.atual == "favoritos":
            nos = [_no(f"Meus favoritos({min(len(self.favoritos), 1000)})", caixa=(120, 160, 560, 220)),
                   _no("Melhor Oferta", caixa=(480, 300, 650, 350)),
                   _no("Inválido", caixa=(700, 300, 820, 350), clicavel=False),
                   _no("Substituir Tudo", caixa=(740, 440, 910, 500))]
            for i, nome in enumerate(self._visiveis()):
                y = 600 + 340 * i
                nos += [_no(caixa=(50, y + 80, 120, y + 150), ident=CAIXA),
                        _no(nome, caixa=(420, y, 1040, y + 60), clicavel=False)]
                if nome in self.invalidos:
                    nos.append(_no("Inválido", caixa=(140, y + 200, 300, y + 240), clicavel=False))
            nos += [_no(caixa=(30, 2290, 96, 2356), ident=CAIXA),
                    _no(f"Selecionado {len(self.marcados)}/50", caixa=(120, 2300, 380, 2350), clicavel=False),
                    _no("Like", caixa=(600, 2290, 750, 2356)), _no("Compartilhar", caixa=(800, 2290, 1010, 2356))]
            return nos
        return super()._nos()

    def click(self, x, y):
        tocados = {el["texto"] for el in robo.ps.elementos(self.dump_hierarchy()) if robo.ps._dentro((x, y), el["caixa"])}
        assert not tocados & {"Compartilhar", "Substituir Tudo", "Meus Favoritos"}, f"tocou em {tocados}"
        if self.atual == "inicio" and "Eu" in tocados:
            self.atual = "eu"
        elif self.atual == "eu" and "Criadores & Afiliados" in tocados:
            self.atual = "afiliado"
        elif self.atual == "afiliado" and "Meus favoritos" in tocados:
            self.atual, self.topo = "favoritos", 0
        elif self.atual == "favoritos" and "Like" in tocados:
            self.favoritos = [f for f in self.favoritos if f not in self.marcados or f in self.invalidos]
            self.marcados, self.topo = [f for f in self.marcados if f in self.invalidos], 0
        elif self.atual == "favoritos" and 30 <= x <= 96 and 2290 <= y <= 2356:
            if self.marcar_tudo:
                self.marcados = self.favoritos[:50]
        elif self.atual == "favoritos" and 50 <= x <= 120:
            linha = (y - 680) // 340
            nome = self._visiveis()[linha]
            if nome in self.marcados:
                self.marcados.remove(nome)
            elif len(self.marcados) < 50:
                self.marcados.append(nome)
        else:
            return super().click(x, y)
        self.toques.append(next(iter(tocados), (x, y)))

    def swipe(self, *pontos):
        self.toques.append("rolar")
        if self.atual == "favoritos":
            self.topo = min(self.topo + 3, max(0, len(self.favoritos) - 1))


def test_as_4h_descurte_tudo_em_meus_favoritos_pelo_caminho_de_afiliado(monkeypatch, avisos):
    # O Rafael ensinou (vídeo de 25/10): Eu → Criadores & Afiliados → Meus favoritos → marcar →
    # Like. O Meus Favoritos de comprador da aba Eu é outra lista (o app de mentira barra).
    from conftest import consultar
    ativar(robo_inicio=8, robo_fim=22)
    app = AppDosFavoritos(favoritos=6)
    resultado = robo.rodada(d=app, agora=momento("2026-10-25 04:05"))
    assert resultado == "6 produto(s) descurtido(s) em Meus favoritos"
    assert app.favoritos == [] and "Like" in app.toques and robo.lista_limpa()
    assert consultar("SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = 'descurtir tudo (4h)'") == (
        "descurtido", "6 produto(s)", 1)
    # Feito, a hora fica parada até as 5h.
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-25 04:20")) == "nada a fazer agora"


def test_lista_grande_vai_de_50_em_50_e_continua_na_rodada_seguinte(monkeypatch, avisos):
    monkeypatch.setattr(robo, "VOLTAS_DO_DESCURTIR", 2)
    ativar(robo_inicio=8, robo_fim=22)
    app = AppDosFavoritos(favoritos=130)
    assert "o resto fica para a próxima rodada" in robo.rodada(d=app, agora=momento("2026-10-25 04:05"))
    assert len(app.favoritos) == 30
    assert robo.o_que_fazer(robo.ler_config(), momento("2026-10-25 04:20")) == ("descurtir", None)
    assert robo.rodada(d=app, agora=momento("2026-10-25 04:20")) == "30 produto(s) descurtido(s) em Meus favoritos"
    assert app.favoritos == [] and robo.o_que_fazer(robo.ler_config(), momento("2026-10-25 04:35")) is None


def test_sem_a_caixa_de_marcar_tudo_marca_um_por_um_rolando(monkeypatch, avisos):
    # Como o Rafael fez no vídeo: marcando produto por produto, rolando a lista.
    ativar(robo_inicio=8, robo_fim=22)
    app = AppDosFavoritos(favoritos=12, marcar_tudo=False)
    assert robo.rodada(d=app, agora=momento("2026-10-25 04:05")) == "12 produto(s) descurtido(s) em Meus favoritos"
    assert app.favoritos == [] and "rolar" in app.toques


def test_caminho_espera_a_tela_que_demora_a_carregar(monkeypatch):
    # No Motorola (30/10, 06:38), Criadores & Afiliados ficou em branco mais de 8 s depois do
    # toque, e o rascunho parava. O caminho relê a tela por mais um tempo antes de parar.
    monkeypatch.setattr(robo, "pausa", lambda segundos: None)

    class Lenta:
        def __init__(self, em_branco):
            self.tocado, self.em_branco = False, em_branco

        def dump_hierarchy(self, *a, **k):
            if not self.tocado:
                return _xml(_no("Criadores & Afiliados", caixa=(600, 1630, 1000, 1700)))
            if self.em_branco:
                self.em_branco -= 1
                return _xml()
            return _xml(_no("Conta", caixa=(0, 300, 200, 360)))

        def click(self, x, y):
            self.tocado = True

    caminho = [("Criadores & Afiliados", 8, "Conta")]
    robo.seguir(Lenta(em_branco=3), caminho)
    # Em branco depois da espera a mais: para, como antes.
    with pytest.raises(robo.Parada, match="depois de Criadores & Afiliados, a tela não mostrou Conta"):
        robo.seguir(Lenta(em_branco=99), caminho)


def test_sem_nada_curtido_nao_ha_o_que_descurtir(monkeypatch, avisos):
    ativar(robo_inicio=8, robo_fim=22)
    assert robo.rodada(d=AppDosFavoritos(favoritos=0), agora=momento("2026-10-25 04:05")) == (
        "nada curtido em Meus favoritos")
    assert robo.lista_limpa()


def test_favoritos_que_nao_abrem_param_sem_dar_a_lista_por_limpa(monkeypatch, avisos):
    class NaoAbre(AppDosFavoritos):
        def _nos(self):
            return [ABA_EU] if self.atual == "favoritos" else super()._nos()

    monkeypatch.setattr(robo, "pausa", lambda segundos: None)
    ativar(robo_inicio=8, robo_fim=22)
    resultado = robo.rodada(d=NaoAbre(favoritos=3), agora=momento("2026-10-25 04:05"))
    assert "Meus favoritos não abriu" in resultado and not robo.lista_limpa()
    assert robo.passo_do_motivo(resultado) == "descurtir em Meus Favoritos"


def test_sem_a_area_de_afiliado_nao_cai_no_meus_favoritos_de_comprador(monkeypatch, avisos):
    # Se o toque em Criadores & Afiliados não abrir a área de afiliado, o "Meus favoritos" da
    # aba Eu é o de comprador, outra lista: o robô para em vez de tocar nele.
    class SemAfiliado(AppDosFavoritos):
        def click(self, x, y):
            if self.atual == "eu" and 600 <= x <= 1000 and 1630 <= y <= 1700:
                self.toques.append("Criadores & Afiliados")
                return
            return super().click(x, y)

    monkeypatch.setattr(robo, "pausa", lambda segundos: None)
    ativar(robo_inicio=8, robo_fim=22)
    resultado = robo.rodada(d=SemAfiliado(favoritos=3), agora=momento("2026-10-25 04:05"))
    assert "Criadores & Afiliados não abriu" in resultado and not robo.lista_limpa()


def test_pausado_nao_descurte(monkeypatch, avisos):
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True})
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-25 04:05")) == "pausado"


def test_produto_invalido_que_o_like_nao_tira_fica_e_a_lista_acaba(monkeypatch, avisos):
    # 29/10/2026: o produto que saiu da loja (selo Inválido) continuou depois do Like, e a
    # limpeza parava todo dia, sem dar a lista por limpa (P27).
    from conftest import consultar
    ativar(robo_inicio=8, robo_fim=22)
    app = AppDosFavoritos(favoritos=6, invalidos=[5])
    resultado = robo.rodada(d=app, agora=momento("2026-10-29 04:05"))
    assert resultado == ("5 produto(s) descurtido(s) em Meus favoritos; 1 inválido(s) ficam "
                         "(o Like não tira produto que saiu da loja)")
    assert app.favoritos == ["Produto 5"] and robo.lista_limpa()
    assert consultar("SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = 'descurtir tudo (4h)'") == (
        "descurtido", "5 produto(s); 1 inválido(s) ficam", 1)
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-29 04:20")) == "nada a fazer agora"


def test_so_invalidos_na_lista_a_limpeza_acaba_sem_tocar_no_like(monkeypatch, avisos):
    # O caso das 04:48 de 29/10: só o inválido na lista; marcar e tocar em Like não adianta.
    ativar(robo_inicio=8, robo_fim=22)
    app = AppDosFavoritos(favoritos=1, invalidos=[0])
    resultado = robo.rodada(d=app, agora=momento("2026-10-29 04:05"))
    assert resultado.startswith("0 produto(s) descurtido(s) em Meus favoritos; 1 inválido(s) ficam")
    assert "Like" not in app.toques and app.favoritos == ["Produto 0"] and robo.lista_limpa()


def test_invalidos_no_alto_e_outros_embaixo_continua_descurtindo(monkeypatch, avisos):
    # Só inválidos na tela, mas a lista continua embaixo: o robô rola, acha os outros e tira.
    ativar(robo_inicio=8, robo_fim=22)
    app = AppDosFavoritos(favoritos=8, invalidos=range(5))
    resultado = robo.rodada(d=app, agora=momento("2026-10-29 04:05"))
    assert resultado.startswith("3 produto(s) descurtido(s) em Meus favoritos; 5 inválido(s) ficam")
    assert app.favoritos == [f"Produto {i}" for i in range(5)] and robo.lista_limpa()


def test_selo_invalido_do_filtro_nao_conta_como_produto():
    # A linha dos filtros tem o filtro Inválido; só o selo na foto do produto conta.
    filtro = _no("Melhor Oferta", caixa=(480, 300, 650, 350)), _no("Inválido", caixa=(700, 300, 820, 350))
    produto = _no(caixa=(50, 680, 120, 750), ident=CAIXA), _no("Produto", caixa=(420, 600, 1040, 660))
    selo = _no("Inválido", caixa=(140, 800, 300, 840))
    assert robo.produtos_invalidos(_xml(*filtro, *produto)) == 0 and not robo.so_invalidos(_xml(*filtro, *produto))
    assert robo.produtos_invalidos(_xml(*filtro, *produto, selo)) == 1 and robo.so_invalidos(_xml(*filtro, *produto, selo))
    assert not robo.so_invalidos(_xml(*filtro))


def test_like_que_nao_tira_para_e_diz_onde(monkeypatch, avisos):
    # Uma pergunta do app que o robô não conhece: os produtos continuam marcados e na lista.
    class LikeQueNaoPega(AppDosFavoritos):
        def click(self, x, y):
            if self.atual == "favoritos" and 600 <= x <= 750 and 2290 <= y <= 2356:
                self.toques.append("Like")
                return
            return super().click(x, y)

    ativar(robo_inicio=8, robo_fim=22)
    app = LikeQueNaoPega(favoritos=3)
    resultado = robo.rodada(d=app, agora=momento("2026-10-25 04:05"))
    assert "continuaram em Meus favoritos (3 marcado(s); 0 inválido(s) na tela)" in resultado
    assert len(app.favoritos) == 3 and not robo.lista_limpa()
    assert robo.passo_do_motivo(resultado) == "descurtir em Meus Favoritos"


def _anexar_espiao(monkeypatch):
    """O rolar_a_lista com que o robô chamou o anexar em cada produto."""
    chamadas = []
    original = robo.ps.adicionar_produto

    def espiao(d, video, anexados=None, no_topo=1, rolar_a_lista=True, **outros):
        chamadas.append(rolar_a_lista)
        return original(d, video, anexados, no_topo, rolar_a_lista, **outros)

    monkeypatch.setattr(robo.ps, "adicionar_produto", espiao)
    return chamadas


def test_lista_limpa_pelas_4h_o_rascunho_nao_rola_e_continua_limpa(monkeypatch, avisos):
    # Escolha do Rafael (P27): depois da limpeza dada certo, o anexar não rola a lista inteira.
    ativar(robo_inicio=8, robo_fim=22, robo_limite_min=1, robo_limite_max=1)
    assert not robo.lista_limpa()
    robo.rodada(d=AppDosFavoritos(favoritos=2), agora=momento("2026-10-25 04:05"))
    assert robo.lista_limpa()
    _fonte(monkeypatch)
    chamadas = _anexar_espiao(monkeypatch)
    app = AppDeMentira()
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-25 10:00")) == "rascunho salvo"
    assert chamadas == [False] and not app.curtido and robo.lista_limpa()


def test_descurtir_que_falha_no_fim_suja_a_lista_e_o_proximo_rola(monkeypatch, avisos):
    ativar(robo_inicio=8, robo_fim=22, robo_limite_min=1, robo_limite_max=1)
    robo.gravar_estado(favoritos_limpos=True)
    _fonte(monkeypatch)
    monkeypatch.setattr(robo.ps, "descurtir", lambda d, video: (False, "toquei no coração, mas o produto continuou curtido"))
    assert robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-25 10:00")) == "rascunho salvo"
    assert not robo.lista_limpa()
    inserir("INSERT INTO fila_autorais VALUES (?, ?, ?, ?)", "a2", "archive/vestido.mp4",
            f"Vestido 👗\n{LINK}", "2026-10-25 09:30:00")
    chamadas = _anexar_espiao(monkeypatch)
    assert robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-25 11:00")) == "rascunho salvo"
    assert chamadas == [True]


def test_curtido_de_outro_dia_que_nao_descurtiu_suja_a_lista(monkeypatch, avisos):
    robo.gravar_estado(favoritos_limpos=True)
    robo._conferir_curtida((True, robo.ps.CURTIDO_DE_ANTES))
    assert not robo.lista_limpa()
    robo.gravar_estado(favoritos_limpos=True)
    robo._conferir_curtida((True, "produto curtido"))
    assert robo.lista_limpa()


def test_descurtir_das_4h_que_para_no_meio_deixa_a_lista_suja(monkeypatch, avisos):
    class LikeQueNaoPega(AppDosFavoritos):
        def click(self, x, y):
            if self.atual == "favoritos" and 600 <= x <= 750 and 2290 <= y <= 2356:
                return
            return super().click(x, y)

    ativar(robo_inicio=8, robo_fim=22)
    robo.gravar_estado(favoritos_limpos=True)
    robo.rodada(d=LikeQueNaoPega(favoritos=3), agora=momento("2026-10-25 04:05"))
    assert not robo.lista_limpa()


def test_rascunho_que_nao_sai_deixa_o_caso_completo_para_o_checkup(monkeypatch, avisos):
    # Pedido do Rafael (25/10): depois de um erro, o Claude vê tudo o que o robô viu (o
    # motivo, o título, o produto, a tela), cifrado; depois de resolvido, é apagado.
    import json
    _fonte(monkeypatch)
    monkeypatch.setattr(robo.ps, "adicionar_produto", lambda *a, **k: (
        False, "o produto do vídeo não está na lista, nem pela foto do 1º (x): nada adicionado (aviso no privado)"))
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59"))
    casos = robo.casos_robo.casos()
    assert len(casos) == 1 and casos[0].endswith("-rascunho")
    with open(os.path.join(robo.casos_robo.PASTA, casos[0], "caso.json"), encoding="utf-8") as f:
        caso = json.load(f)
    assert (caso["resultado"], caso["passo"]) == ("pulado", "anexar o produto")
    assert caso["rascunho"]["titulo"] == TITULO and caso["rascunho"]["produtos"] == [VESTIDO]
    assert caso["video"]["link"] == LINK and os.path.exists(os.path.join(robo.casos_robo.PASTA, casos[0], "tela.xml"))


# --- Canal Afiliados: o vídeo postado vai à fila do canal (P62 a P64) ---

LINK_DO_POST = "https://sv.shopee.com.br/share-video/abc"


def _postado_com_video(tmp_path, **campos):
    video = tmp_path / "rascunho.mp4"
    video.write_bytes(b"video aprovado")
    ident = _rascunho("postado", arquivo=str(video))
    if campos:
        robo.atualizar(ident, **campos)
    return robo.pegar(ident)


def _resultado_no_registro():
    return consultar("SELECT resultado, ok FROM registro_processos WHERE processo = ?", robo.PROCESSO_DO_CANAL)


def test_postado_vai_ao_canal_com_o_link_do_post(monkeypatch, avisos, caminho_do_rascunho):
    ident = _aprovado(monkeypatch)
    levados = []
    monkeypatch.setattr(robo, "link_do_post", lambda d, ident=None: LINK_DO_POST)
    monkeypatch.setattr(robo, "levar_ao_canal", lambda rascunho, link_post: levados.append((rascunho["id"], link_post)))
    app = AppComQuadros()
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho aprovado postado"
    assert levados == [(ident, LINK_DO_POST)]


def test_pedido_ao_canal_leva_a_copia_do_video_e_o_link_do_produto_com_a_etiqueta_do_canal(monkeypatch, avisos,
                                                                                            tmp_path):
    # Pedido do Rafael (28/10): o vídeo aprovado, o link do post e os links dos produtos.
    convertidos = []

    async def link_para_converter(link):
        return "https://shopee.com.br/product/1/2"

    async def converter(endereco, etiqueta="geral", **kw):
        convertidos.append((endereco, etiqueta))
        return "https://s.shopee.com.br/canal1"

    monkeypatch.setattr(robo, "link_para_converter", link_para_converter)
    monkeypatch.setattr(robo.api_shopee, "converter_link_shopee", converter)
    rascunho = _postado_com_video(tmp_path)
    LEVAR_AO_CANAL(rascunho, LINK_DO_POST)
    [pedido] = robo.pedidos_do_canal.pendentes()
    assert (pedido["id"], pedido["link_post"], pedido["links"], pedido["produto"]) == (
        rascunho["id"], LINK_DO_POST, ["https://s.shopee.com.br/canal1"], VESTIDO)
    assert convertidos == [("https://shopee.com.br/product/1/2", robo.api_shopee.ETIQUETA_CANAL_AFILIADOS)]
    # A cópia é só do canal: a do rascunho o robô apaga no fim da rodada.
    assert pedido["arquivo"] != rascunho["arquivo"] and open(pedido["arquivo"], "rb").read() == b"video aprovado"
    assert avisos == [] and _resultado_no_registro() == ("pedido", 1)

    # A API que falha devolve o link original: vai ele (06/10: DECISOES.md, Canal Viral), e o
    # mesmo rascunho pedido de novo troca o pedido, sem dobrar.
    async def falhou(endereco, etiqueta="geral", **kw):
        return endereco

    monkeypatch.setattr(robo.api_shopee, "converter_link_shopee", falhou)
    LEVAR_AO_CANAL(rascunho, LINK_DO_POST)
    assert [p["links"] for p in robo.pedidos_do_canal.pendentes()] == [["https://shopee.com.br/product/1/2"]]


def test_ver_produtos_vai_ao_canal_com_cada_produto_achado_na_api_pelo_nome(monkeypatch, avisos, tmp_path):
    ofertas = [{"productName": "Mini Saia Plissada Feminina Cintura Alta", "productLink": "https://shopee.com.br/product/1/1"},
               {"productName": "Blusa Cropped Canelada Manga Curta", "productLink": "https://shopee.com.br/product/2/2"}]

    async def link_para_converter(link):
        return "https://sv.shopee.com.br/share-video/xyz?jumpType=1"

    async def buscar(termo, limite=10, app_id=None, app_secret=None, sort_type=2):
        return ofertas

    async def converter(endereco, etiqueta="geral", **kw):
        return endereco.replace("https://shopee.com.br/product/", "https://s.shopee.com.br/canal-")

    monkeypatch.setattr(robo, "link_para_converter", link_para_converter)
    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", buscar)
    monkeypatch.setattr(robo.api_shopee, "converter_link_shopee", converter)
    produtos = ["Mini Saia Plissada Feminina Cintura Alta", "Blusa Cropped Canelada Manga Curta",
                "Brinco Argola Dourado Grande"]
    LEVAR_AO_CANAL(_postado_com_video(tmp_path, produtos=produtos), LINK_DO_POST)
    # O que a API não acha pelo nome fica de fora.
    assert robo.pedidos_do_canal.pendentes()[0]["links"] == ["https://s.shopee.com.br/canal-1/1",
                                                             "https://s.shopee.com.br/canal-2/2"]


def test_sem_o_link_do_post_o_video_nao_vai_ao_canal_e_o_rafael_fica_sabendo(avisos, tmp_path):
    # Escolha do Rafael (28/10, P63): sem o link do post, não vai.
    LEVAR_AO_CANAL(_postado_com_video(tmp_path), "")
    assert robo.pedidos_do_canal.pendentes() == []
    assert len(avisos) == 1 and "não foi para a fila do canal" in avisos[0] and "sem o link" in avisos[0]
    assert _resultado_no_registro() == ("de fora - sem o link do post", 0)


def test_erro_ao_guardar_o_pedido_avisa_sem_derrubar_o_post(monkeypatch, avisos, tmp_path):
    monkeypatch.setattr(robo, "links_para_o_canal", lambda rascunho: ["https://s.shopee.com.br/canal1"])
    rascunho = robo.pegar(_rascunho("postado", arquivo=str(tmp_path / "sumiu.mp4")))
    LEVAR_AO_CANAL(rascunho, LINK_DO_POST)
    assert robo.pedidos_do_canal.pendentes() == []
    assert len(avisos) == 1 and "o pedido não foi guardado" in avisos[0]
    assert _resultado_no_registro() == ("erro (FileNotFoundError)", 0)


# --- Os espaços livres com o mesmo item de outras lojas (P59) ---

def _registro_dos_espacos():
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DOS_ESPACOS, "2000-01-01 00:00:00")
    return [r[2] for r in registro]


def _oferta_da_foto(item, preco, comissao, link=True):
    return {"itemId": item, "productName": f"Garrafa Térmica Inox Loja {item}", "priceMin": str(preco),
            "commissionRate": str(comissao / 100), "imageUrl": f"https://img.exemplo/{item}.jpg",
            "productLink": f"https://shopee.com.br/product/9/{item}" if link else ""}


def test_candidatos_da_foto_ate_20_por_cento_mais_caros_do_que_paga_mais_para_o_que_paga_menos():
    # Escolhas do Rafael (P58, P59, P68): o mesmo item de outras lojas, até 20% mais caro que o
    # do link (R$ 50: até R$ 60), nunca o que já está no rascunho nem o mesmo anúncio duas vezes,
    # do que paga mais por venda para o que paga menos.
    achados = [({}, _oferta_da_foto(1, 55, 10)),          # R$ 5,50 por venda
               ({}, _oferta_da_foto(2, 45, 20)),          # R$ 9,00: o que paga mais
               ({}, _oferta_da_foto(3, 61, 30)),          # mais caro que o teto
               ({}, _oferta_da_foto(7, 50, 10)),          # o produto do rascunho
               ({}, _oferta_da_foto(2, 45, 20)),          # o mesmo anúncio de novo
               ({}, _oferta_da_foto(4, 40, 5, link=False)),
               ({}, _oferta_da_foto(5, 60, 12))]          # exatamente no teto: R$ 7,20
    candidatos = robo.candidatos_da_foto({"preco": 50.0, "comissao": 10.0}, "7", achados)
    assert [c["item"] for c in candidatos] == ["2", "5", "1"]
    assert candidatos[0]["valor"] == pytest.approx(9.0) and candidatos[0]["endereco"].endswith("/9/2")
    assert robo.candidatos_da_foto({"preco": 0}, "7", achados) == []


def test_oferta_do_cartao_e_a_de_mesmo_nome_e_mesmo_preco(monkeypatch):
    pedidos = []

    async def buscar(termo, limite=20, sort_type=1):
        pedidos.append((termo, sort_type))
        return [{"productName": "Garrafa Térmica Inox 1 Litro Preta", "priceMin": "79.90", "itemId": 1},
                {"productName": "Outra Coisa Qualquer De Cozinha", "priceMin": "49.90", "itemId": 2},
                {"productName": "Garrafa Térmica Inox 1 Litro Preta", "priceMin": "49.50", "itemId": 3}]

    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", buscar)
    cartao = {"nome": "Garrafa Térmica Inox 1 Litro Preta", "preco": 49.9, "comissao": 10.0, "extra": False}
    assert robo.oferta_do_cartao(cartao)["itemId"] == 3 and pedidos[0][1] == 1
    assert robo.oferta_do_cartao(dict(cartao, preco=20.0)) == {}
    # Por que não achou, só números para o checkup: o mesmo nome com outro preço, ou nenhum
    # com o mesmo nome.
    perdas = {}
    assert robo.oferta_do_cartao(dict(cartao, preco=20.0), perdas) == {} and perdas == {"preço": 1}
    assert robo.oferta_do_cartao(dict(cartao, nome="Panela De Pressão Elétrica"), perdas) == {}
    assert perdas == {"preço": 1, "nome": 1, "outros produtos": 1}
    # Conferência de 30/10 (P59): 3 a 15 dos 20 cartões não eram achados pelo nome, sem dizer por
    # quê. O anúncio de nome um pouco diferente do cartão é "nome parecido"; a busca sem nada,
    # "busca vazia".
    assert robo.oferta_do_cartao(dict(cartao, nome="Garrafa Térmica Inox 1 Litro Azul"), perdas) == {}
    assert perdas["nome parecido"] == 1

    async def nada(termo, limite=20, sort_type=1):
        return []

    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", nada)
    assert robo.oferta_do_cartao(cartao, perdas) == {} and perdas["busca vazia"] == 1 and perdas["nome"] == 3


def test_oferta_do_cartao_e_o_anuncio_do_cartao_entre_lojas_de_titulo_copiado(monkeypatch):
    # Lojas diferentes copiam o mesmo título, e o 1º da busca com aquele nome e preço pode ser o
    # anúncio do próprio post: vale o de taxa de comissão e preço mais perto dos do cartão; no
    # empate, o mais relevante.
    async def buscar(termo, limite=20, sort_type=1):
        nome = "Garrafa Térmica Inox 1 Litro Preta"
        return [{"productName": nome, "priceMin": "49.90", "commissionRate": "0.08", "itemId": 7},
                {"productName": nome, "priceMin": "50.50", "commissionRate": "0.12", "itemId": 8},
                {"productName": nome, "priceMin": "49.90", "commissionRate": "0.12", "itemId": 9},
                {"productName": nome, "priceMin": "49.90", "commissionRate": "0.12", "itemId": 10}]

    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", buscar)
    cartao = {"nome": "Garrafa Térmica Inox 1 Litro Preta", "preco": 49.9, "comissao": 12.0, "extra": False}
    assert robo.oferta_do_cartao(cartao)["itemId"] == 9
    assert robo.oferta_do_cartao(dict(cartao, comissao=8.0))["itemId"] == 7
    assert robo.oferta_do_cartao(dict(cartao, preco=50.5))["itemId"] == 8
    # Sem a taxa no cartão, ficam o preço e a ordem da busca.
    assert robo.oferta_do_cartao(dict(cartao, comissao=0))["itemId"] == 7


def test_candidatos_da_foto_contam_por_que_cada_achado_ficou_de_fora():
    # Só números para o checkup: os mais caros (e quantos % acima do post está o mais barato
    # deles), o anúncio do rascunho, o mesmo anúncio de outro cartão e o que veio sem dados.
    achados = [({}, _oferta_da_foto(7, 50, 10)), ({}, _oferta_da_foto(7, 50, 10)),
               ({}, _oferta_da_foto(3, 61, 30)), ({}, _oferta_da_foto(4, 75, 30)),
               ({}, _oferta_da_foto(1, 55, 10)), ({}, _oferta_da_foto(1, 55, 10)),
               ({}, _oferta_da_foto(5, 40, 5, link=False))]
    fora = {}
    assert [c["item"] for c in robo.candidatos_da_foto({"preco": 50.0}, "7", achados, fora)] == ["1"]
    assert fora == {"o do rascunho": 2, "mais caro": 2, "o mais perto": 22, "repetido": 1, "sem dados": 1}
    assert robo._fora_do_preco(fora) == " (mais caros 2, o mais perto +22%; o do rascunho 2; repetidos 1; sem dados 1)"
    fora = {}
    assert robo.candidatos_da_foto({"preco": 0}, "7", achados, fora) == [] and fora == {"sem o preço do post": 1}
    assert robo._fora_do_preco(fora) == " (sem o preço do post)" and robo._fora_do_preco({}) == ""
    # O que passa do teto por pouco nunca aparece como os 20% dele.
    fora = {}
    assert robo.candidatos_da_foto({"preco": 50.0}, "", [({}, _oferta_da_foto(3, 60.01, 10))], fora) == []
    assert fora == {"mais caro": 1, "o mais perto": 21}


@pytest.fixture
def busca_pela_foto(monkeypatch):
    """A busca pela foto e a API de mentira: 3 cartões, todos achados na API, e a IA confirma o 1º e o 3º."""
    estado = {"cartoes": [{"nome": f"Garrafa {i}", "preco": 50.0, "comissao": 10.0, "extra": False} for i in (1, 2, 3)],
              "motivo": "", "iguais": [0, 2], "fotos_da_ia": []}
    ofertas = {"Garrafa 1": _oferta_da_foto(1, 52, 12), "Garrafa 2": _oferta_da_foto(2, 50, 11),
               "Garrafa 3": _oferta_da_foto(3, 55, 8)}

    def buscar(d, foto):
        estado["foto_da_busca"] = foto
        if isinstance(estado["cartoes"], Exception):
            raise estado["cartoes"]
        return estado["cartoes"], estado["motivo"]

    def iguais(video, nome, anuncios, capa=None, recusas=None):
        estado["fotos_da_ia"] = [n for n, _ in anuncios]
        estado["capa"] = capa
        if recusas is not None and "recusas" in estado:
            recusas.update(estado["recusas"])
        return estado["iguais"], "a mesma garrafa"

    async def converter(endereco, etiqueta, avisar_falha=True):
        return "https://s.shopee.com.br/curto" + endereco.rsplit("/", 1)[-1]

    monkeypatch.setattr(robo.ps, "anuncio_do_produto", lambda video: {"foto": b"\xff\xd8foto"})
    monkeypatch.setattr(robo, "buscar_pela_foto", buscar)
    def oferta(cartao, perdas=None):
        achada = estado["ofertas"].get(cartao["nome"], {})
        if not achada and perdas is not None:
            for motivo in ("nome", "outros produtos"):
                perdas[motivo] = perdas.get(motivo, 0) + 1
        return achada

    estado["ofertas"] = ofertas
    monkeypatch.setattr(robo, "oferta_do_cartao", oferta)
    monkeypatch.setattr(robo, "item_do_link", lambda link: "7")
    monkeypatch.setattr(robo.ps, "baixar_foto",
                        lambda endereco: b"\xff\xd8capa" if endereco == "https://cf.shopee.com.br/capa" else b"\xff\xd8anuncio")
    monkeypatch.setattr(robo.ps, "ia_confere_iguais", iguais)
    monkeypatch.setattr(robo.api_shopee, "converter_link_shopee", converter)
    return estado


PRINCIPAL = {"nome": "Garrafa Térmica Inox 1 Litro", "link": "https://s.shopee.com.br/principal", "do_video": True,
             "preco": 50.0, "comissao": 10.0, "valor": 5.0}


def test_espacos_livres_trazem_os_confirmados_pela_ia_do_que_paga_mais_para_o_que_paga_menos(busca_pela_foto):
    vistos = []
    original = {"preco": 50.0, "imagem": "https://cf.shopee.com.br/capa"}
    mais = robo.espacos_livres(None, {"link": LINK, "arquivo": "v.mp4"}, PRINCIPAL, original, vistos,
                               robo.time.monotonic() + 600)
    # A IA vê os 3 de uma vez, do que paga mais (R$ 6,24) para o que paga menos (R$ 4,40).
    assert busca_pela_foto["fotos_da_ia"] == ["Garrafa Térmica Inox Loja 1", "Garrafa Térmica Inox Loja 2",
                                              "Garrafa Térmica Inox Loja 3"]
    assert [p["link"] for p in mais] == ["https://s.shopee.com.br/curto1", "https://s.shopee.com.br/curto3"]
    assert mais[0]["endereco"] == "https://shopee.com.br/product/9/1" and not mais[0].get("do_video")
    # A busca parte da foto de capa do anúncio do post, e a IA confere cada um com ela (P74);
    # a foto de cada um vai junto, para o álbum das capas do rascunho (P75).
    assert busca_pela_foto["foto_da_busca"] == b"\xff\xd8capa" and busca_pela_foto["capa"] == b"\xff\xd8capa"
    assert mais[0]["foto"] == b"\xff\xd8anuncio"
    assert vistos == ["Produtos a mais (2 de 3): a mesma garrafa"]
    assert _registro_dos_espacos() == ["achados"]


def test_espacos_livres_guardam_as_fotos_dos_que_a_ia_recusou(busca_pela_foto, monkeypatch, tmp_path):
    # Pedido do Rafael (01/11, provisório): a foto de capa de cada anúncio que a IA conferiu e
    # recusou vai a um álbum à parte do rascunho, para ele conferir se ela está acertando.
    monkeypatch.setattr(robo.ps, "baixar_foto", lambda endereco: b"\xff\xd8" + endereco.encode())
    busca_pela_foto["recusas"] = {"outro produto": 1}
    recusados = []
    original = {"preco": 50.0, "imagem": "https://cf.shopee.com.br/capa"}
    mais = robo.espacos_livres(None, {"link": LINK, "arquivo": "v.mp4"}, PRINCIPAL, original, [],
                               robo.time.monotonic() + 600, recusados=recusados)
    # A IA confirmou o 1º e o 3º (do que paga mais para o que paga menos): o 2º foi recusado.
    assert [p["foto"] for p in mais] == [b"\xff\xd8https://img.exemplo/1.jpg", b"\xff\xd8https://img.exemplo/3.jpg"]
    assert recusados == [b"\xff\xd8https://img.exemplo/2.jpg"]
    # Quando a IA não respondeu, nenhum foi recusado por ela: o álbum não ganha nada.
    del busca_pela_foto["recusas"]
    busca_pela_foto["iguais"] = []
    recusados = []
    robo.espacos_livres(None, {"link": LINK, "arquivo": "v.mp4"}, PRINCIPAL, original, [],
                        robo.time.monotonic() + 600, recusados=recusados)
    assert recusados == []
    # As fotos ficam ao lado do vídeo do rascunho e saem com ele depois de usadas.
    monkeypatch.setattr(robo, "PASTA_RASCUNHOS", str(tmp_path))
    caminhos = robo.guardar_recusados(7, [b"\xff\xd8\xffum", b"\x89PNG\r\n\x1a\ndois"])
    assert [os.path.basename(c) for c in caminhos] == ["7_recusado_1.jpg", "7_recusado_2.png"]
    assert all(robo.ARQUIVO_NO_SERVIDOR.match(os.path.basename(c)) for c in caminhos)
    ident = robo.criar("v11")
    robo.atualizar(ident, recusadas=caminhos)
    assert robo.pegar(ident)["recusadas"] == caminhos and robo.pegar(robo.criar("v12"))["recusadas"] == []


def test_espacos_livres_contam_os_cartoes_que_nao_acharam_na_api(busca_pela_foto):
    # Só números no registro: por que os cartões da busca não foram achados na API.
    del busca_pela_foto["ofertas"]["Garrafa 2"]
    busca_pela_foto["iguais"] = [0]
    original = {"preco": 50.0, "imagem": "https://cf.shopee.com.br/capa"}
    robo.espacos_livres(None, {"link": LINK, "arquivo": "v.mp4"}, PRINCIPAL, original, [], robo.time.monotonic() + 600)
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DOS_ESPACOS, "2000-01-01 00:00:00")
    assert ("3 na busca (3 com o nome parecido), 2 na API (sem o nome 1, outro preço 0), 2 anúncio(s) diferente(s), "
            "2 no preço") in registro[-1][3]
    # E por que o cartão não foi achado pelo nome, numa linha à parte (conferência de 30/10, P59).
    porque = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_BUSCA_NA_API, "2000-01-01 00:00:00")
    assert [(linha[2], linha[3]) for linha in porque] == [
        ("sem o nome", "1 cartão(ões): busca vazia 0, nome parecido 0, outros produtos 1")]


class _Relogio:
    """O time do robô com o monotonic nas marcas dadas, uma por chamada (a última fica)."""

    def __init__(self, *marcas):
        self.marcas = list(marcas)

    def monotonic(self):
        return self.marcas.pop(0) if len(self.marcas) > 1 else self.marcas[0]


def test_espacos_livres_anotam_os_anuncios_diferentes_o_que_ficou_fora_do_preco_e_o_tempo(busca_pela_foto,
                                                                                         monkeypatch):
    video = {"link": LINK, "arquivo": "v.mp4"}
    original = {"preco": 50.0, "imagem": "https://cf.shopee.com.br/capa"}

    def ultimo(processo):
        return robo.registro_processos.sequencia("shopee_video", processo, "2000-01-01 00:00:00")[-1][2:4]

    # Os 3 cartões caem no anúncio do rascunho: nenhum no preço, e o registro diz por quê; numa
    # linha à parte, com o mesmo resultado, em que minuto do rascunho a busca começou e quanto
    # levou cada parte (a régua dos prazos).
    ofertas = busca_pela_foto["ofertas"]
    busca_pela_foto["ofertas"] = {nome: _oferta_da_foto(7, 50, 10) for nome in ofertas}
    monkeypatch.setattr(robo, "time", _Relogio(1000, 1000, 1150, 1180))
    assert robo.espacos_livres(None, video, PRINCIPAL, original, [], 1240, inicio=640) == []
    assert ultimo(robo.PROCESSO_DOS_ESPACOS) == (
        "nenhum - nenhum do mesmo preço na API",
        "3 na busca (3 com o nome parecido), 3 na API, 1 anúncio(s) diferente(s), 0 no preço (o do rascunho 3)")
    assert ultimo(robo.PROCESSO_DO_TEMPO_DOS_ESPACOS) == (
        "nenhum - nenhum do mesmo preço na API", "aos 6,0 min do rascunho: busca 2,5 min, API 0,5 min")
    # Com os achados, o tempo da IA também.
    busca_pela_foto["ofertas"] = ofertas
    monkeypatch.setattr(robo, "time", _Relogio(1000, 1000, 1150, 1180, 1180, 1240))
    assert len(robo.espacos_livres(None, video, PRINCIPAL, original, [], 1240, inicio=640)) == 2
    assert ultimo(robo.PROCESSO_DOS_ESPACOS) == (
        "achados", "2 a mais; 3 na busca (3 com o nome parecido), 3 na API, 3 anúncio(s) diferente(s), 3 no preço, "
                   "3 na IA, 2 confirmados")
    assert ultimo(robo.PROCESSO_DO_TEMPO_DOS_ESPACOS) == (
        "achados", "aos 6,0 min do rascunho: busca 2,5 min, API 0,5 min, IA 1,0 min")
    # Quantos a IA deixou de fora (30/10: 8 na IA e 2 confirmados, sem dizer o motivo); a outra
    # foto de capa não tira mais ninguém (P102), e o que fica de fora é outro produto.
    busca_pela_foto["recusas"] = {"outro produto": 1}
    monkeypatch.setattr(robo, "time", _Relogio(1000, 1000, 1150, 1180, 1180, 1240))
    assert len(robo.espacos_livres(None, video, PRINCIPAL, original, [], 1240, inicio=640)) == 2
    assert ultimo(robo.PROCESSO_DOS_ESPACOS)[1].endswith("3 na IA, 2 confirmados")
    assert ultimo(robo.PROCESSO_DAS_RECUSAS_DA_IA) == ("de fora pela IA", "outro produto 1 (de 3 na IA)")
    del busca_pela_foto["recusas"]
    # O prazo que passa durante a busca, e o que já tinha passado antes dela.
    monkeypatch.setattr(robo, "time", _Relogio(1000, 1000, 1150, 1180, 1300))
    assert robo.espacos_livres(None, video, PRINCIPAL, original, [], 1240, inicio=640) == []
    assert ultimo(robo.PROCESSO_DO_TEMPO_DOS_ESPACOS) == (
        "nenhum - sem tempo na rodada", "aos 6,0 min do rascunho: busca 2,5 min, API 0,5 min")
    monkeypatch.setattr(robo, "time", _Relogio(1300))
    assert robo.espacos_livres(None, video, PRINCIPAL, original, [], 1240, inicio=640) == []
    assert ultimo(robo.PROCESSO_DOS_ESPACOS) == ("nenhum - sem tempo na rodada", "")
    assert ultimo(robo.PROCESSO_DO_TEMPO_DOS_ESPACOS) == ("nenhum - sem tempo na rodada", "aos 11,0 min do rascunho")
    # A contagem mais longa ainda cabe no detalhe do registro.
    longa = ("5 a mais; 20 na busca (18 com o nome parecido), 15 na API (sem o nome 4, outro preço 1), "
             "12 anúncio(s) diferente(s), 8 no preço"
             + robo._fora_do_preco({"mais caro": 3, "o mais perto": 135, "o do rascunho": 2, "repetido": 1,
                                    "sem dados": 1})
             + ", 8 na IA, 5 confirmados")
    assert len(longa) <= robo.registro_processos.TAMANHO_DO_DETALHE


def test_nome_parecido_diz_se_a_busca_partiu_da_foto_certa():
    # 29/10: a busca de um liquidificador trouxe só óculos de sol (a foto de outra busca).
    post = "Meoky Liquidificador Blender Portátil Tritura Gelo 700ml"
    assert robo.nome_parecido("Liquidificador Portátil Recarregável USB 6 Lâminas", post)
    assert robo.nome_parecido("0Mini Liquidificador Blender Portátil...", post)
    assert not robo.nome_parecido("Óculos De Sol Polarizado Masculino Proteção UV400", post)
    assert not robo.nome_parecido("Liquidificador", "")


def test_faixa_do_tempo_do_rascunho():
    assert [robo.faixa_do_tempo(s) for s in (0, 299, 300, 754, 1799, 1800)] == [
        "0 a 5 min", "0 a 5 min", "5 a 10 min", "10 a 15 min", "25 a 30 min", "30 a 35 min"]


def test_espacos_livres_sem_resultado_sem_tempo_ou_com_a_busca_parada_seguem_sem_nenhum(busca_pela_foto, monkeypatch):
    video = {"link": LINK, "arquivo": "v.mp4"}
    agora = robo.time.monotonic()
    assert robo.espacos_livres(None, video, PRINCIPAL, {"preco": 50.0}, [], agora - 1) == []
    busca_pela_foto.update(cartoes=[], motivo="a busca pela foto não achou o produto")
    assert robo.espacos_livres(None, video, PRINCIPAL, {"preco": 50.0}, [], agora + 600) == []
    busca_pela_foto["cartoes"] = robo.Parada("os resultados da busca pela foto não abriram")
    assert robo.espacos_livres(None, video, PRINCIPAL, {"preco": 50.0}, [], agora + 600) == []
    assert _registro_dos_espacos() == ["nenhum - sem tempo na rodada", "nenhum - a busca pela foto não achou o produto",
                                       "parou"]
    # A Verificação da Shopee para tudo, como em qualquer passo.
    busca_pela_foto["cartoes"] = robo.Verificacao()
    with pytest.raises(robo.Verificacao):
        robo.espacos_livres(None, video, PRINCIPAL, {"preco": 50.0}, [], agora + 600)
    # Sem a foto de capa do post, nem a busca: não há com o que comparar (P74).
    busca_pela_foto.pop("foto_da_busca", None)
    monkeypatch.setattr(robo.ps, "baixar_foto", lambda endereco: None)
    assert robo.espacos_livres(None, video, PRINCIPAL, {"preco": 50.0}, [], agora + 600) == []
    assert "foto_da_busca" not in busca_pela_foto and _registro_dos_espacos()[-1] == "nenhum - sem a foto de capa do post"


def test_curte_do_que_paga_menos_para_o_que_paga_mais_e_o_a_mais_que_nao_curte_fica_de_fora(monkeypatch):
    abertos = []
    monkeypatch.setattr(robo, "ir_ao_inicio", lambda d: None)
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    monkeypatch.setattr(robo.ps, "limpar_aviso_rapido", lambda d: None)
    monkeypatch.setattr(robo.ps, "abrir_link", lambda d, link: abertos.append(link))
    monkeypatch.setattr(robo, "_esperar_a_pagina_do_produto",
                        lambda d, a_mais=False: abertos[-1] != "https://s.shopee.com.br/ferias")
    monkeypatch.setattr(robo.ps, "curtir", lambda d, video: (video["link"] != "https://s.shopee.com.br/sem-coracao",
                                                             "produto curtido"))
    mais = [dict(PRINCIPAL, nome="Loja 1", link="https://s.shopee.com.br/1", do_video=False, valor=9.0),
            dict(PRINCIPAL, nome="Férias", link="https://s.shopee.com.br/ferias", do_video=False, valor=7.0),
            dict(PRINCIPAL, nome="Sem coração", link="https://s.shopee.com.br/sem-coracao", do_video=False, valor=6.0),
            dict(PRINCIPAL, nome="Loja 4", link="https://s.shopee.com.br/4", do_video=False, valor=2.0)]
    produtos = sorted([PRINCIPAL] + mais, key=lambda p: -p["valor"])
    curtidos = []
    feitos = robo._curtir_os_produtos(None, {"link": LINK}, produtos, curtidos)
    # O último curtido fica no alto de Minhas Curtidas: curte do que paga menos para o que paga mais.
    assert abertos == ["https://s.shopee.com.br/4", PRINCIPAL["link"], "https://s.shopee.com.br/sem-coracao",
                       "https://s.shopee.com.br/ferias", "https://s.shopee.com.br/1"]
    assert [p["nome"] for p in feitos] == ["Loja 1", PRINCIPAL["nome"], "Loja 4"]
    assert [link for link, _ in curtidos] == ["https://s.shopee.com.br/4", PRINCIPAL["link"], "https://s.shopee.com.br/1"]
    # O produto do vídeo que não curte para o rascunho, como sempre.
    monkeypatch.setattr(robo.ps, "curtir", lambda d, video: (False, "toquei no coração, mas o produto não ficou curtido"))
    with pytest.raises(robo.Parada):
        robo._curtir_os_produtos(None, {"link": LINK}, [PRINCIPAL], [])


def test_anexa_na_ordem_e_o_a_mais_que_nao_anexa_fica_de_fora(monkeypatch):
    caminhos, voltas, chamadas = [], [], []
    monkeypatch.setattr(robo, "seguir", lambda d, caminho: caminhos.append(caminho[0][0]))
    monkeypatch.setattr(robo, "tocar", lambda d, alvo, espera: None)
    monkeypatch.setattr(robo, "primeiro_na_tela_final", lambda d, vez=1: True)
    monkeypatch.setattr(robo, "voltar_a_tela_final", lambda d: voltas.append(True))

    def adicionar(d, video, anexados=None, no_topo=1, rolar_a_lista=True, ultima_chance=True, avisar=True):
        chamadas.append((video["produto"], no_topo, ultima_chance, avisar))
        if video["produto"] in ("B", "Z"):
            return False, "não achei"
        anexados.append(video["produto"])
        return True, "anexado"

    monkeypatch.setattr(robo.ps, "adicionar_produto", adicionar)
    anexados, no_post = robo.anexar_os_produtos(None, {"link": LINK}, ["A", "B", "C"], a_mais={1, 2})
    assert anexados == ["A", "C"] and no_post == [0, 2] and len(voltas) == 1
    assert caminhos == ["@ll_add_product_symbol", "@tv_add_more", "@tv_add_more"]
    # O a mais vai sem a última chance e sem o aviso; o curtido que não anexou continua no alto da lista.
    assert chamadas == [("A", 3, True, True), ("B", 2, False, False), ("C", 2, False, False)]
    assert _registro_dos_espacos() == ["produto a mais de fora"]
    # O produto do vídeo que não anexa para o rascunho.
    with pytest.raises(robo.Parada):
        robo.anexar_os_produtos(None, {"link": LINK}, ["Z", "A"], a_mais={1})


def test_passado_o_prazo_os_a_mais_que_faltam_anexar_ficam_de_fora(monkeypatch):
    # Os a mais são anexados do que paga mais para o que paga menos: passado o prazo, ficam de
    # fora os que faltam, sem tocar no celular; o do vídeo é anexado sempre.
    caminhos, chamadas = [], []
    monkeypatch.setattr(robo, "seguir", lambda d, caminho: caminhos.append(caminho[0][0]))
    monkeypatch.setattr(robo, "tocar", lambda d, alvo, espera: None)
    monkeypatch.setattr(robo, "primeiro_na_tela_final", lambda d, vez=1: True)
    # Cada anexar leva 250 s no relógio do teste.
    relogio = [0.0]
    monkeypatch.setattr(robo.time, "monotonic", lambda: relogio[0])

    def adicionar(d, video, anexados=None, **outros):
        chamadas.append(video["produto"])
        anexados.append(video["produto"])
        relogio[0] += 250
        return True, "anexado"

    monkeypatch.setattr(robo.ps, "adicionar_produto", adicionar)
    anexados, no_post = robo.anexar_os_produtos(None, {"link": LINK}, ["X", "A", "B", "C"], a_mais={0, 2, 3},
                                                prazo=300.0)
    assert anexados == ["X", "A"] and no_post == [0, 1] and chamadas == ["X", "A"]
    assert caminhos == ["@ll_add_product_symbol", "@tv_add_more"]
    assert _registro_dos_espacos() == ["produto a mais de fora", "produto a mais de fora"]


class AppQueReabreALegenda(AppDeMentira):
    """
    Como o Motorola em 31/10 (09:15 e 09:35): a legenda editada fica em foco, e o Feito volta à
    tela final com a edição da legenda aberta por cima (a tela escurecida) e sem o produto.
    perdidos diz quantos Feitos perdem o produto mesmo sem a legenda editada (None: nenhum).
    """

    def __init__(self, perdidos=None):
        super().__init__()
        self.legenda_editada, self.por_cima, self.perdidos = False, False, perdidos

    def _nos(self):
        nos = super()._nos()
        if self.atual != "final":
            return nos
        if not self.com_produto:
            nos = nos + [_no("Adicionar produto", "tv_add_product_title", (32, 713, 326, 764), clicavel=False),
                         _no("Toque para adicionar produtos", "tv_add_product_tip", (870, 717, 974, 760),
                             clicavel=False)]
        if self.por_cima:
            nos = nos + [_no(ident="rl_overlay", caixa=(0, 674, 1080, 2394))]
        return nos

    def click(self, x, y):
        no_feito = self.atual == "janela"
        super().click(x, y)
        tocado = self.toques[-1] if self.toques else None
        if tocado == "@et_caption":
            self.legenda_editada = True
        if tocado == "@tv_add_product_title" and self.por_cima:
            self.por_cima = False
        if no_feito and self.atual == "final":
            perde = self.legenda_editada or (self.perdidos or 0) > 0
            if self.perdidos:
                self.perdidos -= 1
            if perde:
                self.com_produto, self.por_cima = False, True


def _anexar_no_app(app):
    """O rascunho do vestido no app de mentira, já na tela final: os produtos e a legenda, como o robô faz."""
    app.atual = "final"
    anexados, no_post = robo.anexar_os_produtos(app, {"link": LINK, "produto": VESTIDO}, [VESTIDO])
    robo.escrever_a_legenda(app, TITULO)
    return anexados, no_post


def _registro_do_anexar():
    registro = robo.registro_processos.sequencia("shopee_video", "anexar o produto", "2000-01-01 00:00:00")
    return [(r[2], r[3]) for r in registro if r[2] != "anexado"]


def test_produto_vai_antes_da_legenda_e_fica_na_tela_final(monkeypatch, avisos):
    # No Motorola (31/10, 09:15 e 09:35), com a legenda escrita antes, o Feito voltava com a edição
    # da legenda aberta e sem o produto: o rascunho parou e foi pulado. Os produtos vão antes.
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    app = AppQueReabreALegenda()
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.toques.index("Feito") < app.toques.index("@et_caption") and app.legenda == TITULO
    assert robo.esperando_aprovacao()[0]["produtos"] == [VESTIDO]
    assert _registro_do_anexar() == []


def test_primeiro_produto_que_nao_ficou_depois_do_feito_e_anexado_de_novo(monkeypatch, avisos):
    _fonte(monkeypatch)
    app = AppQueReabreALegenda(perdidos=1)
    anexados, no_post = _anexar_no_app(app)
    assert anexados == [VESTIDO] and no_post == [0] and app.com_produto and not app.por_cima
    # A edição da legenda por cima fecha no rótulo "Adicionar produto" (não é botão), e o produto
    # vai de novo pelo mesmo caminho.
    assert app.toques.count("Feito") == 2 and "@tv_add_product_title" in app.toques
    assert app.toques.index("@tv_add_product_title") < len(app.toques) - app.toques[::-1].index("Feito") - 1
    assert _registro_do_anexar() == [
        ("não ficou depois do Feito", "1ª vez; a linha dos produtos vazia; a edição da legenda aberta por cima"),
        ("anexado na 2ª vez", "a linha dos produtos com produto")]


def test_primeiro_produto_que_nao_fica_nem_na_segunda_vez_para_o_rascunho(monkeypatch, avisos):
    _fonte(monkeypatch)
    app = AppQueReabreALegenda(perdidos=5)
    with pytest.raises(robo.Parada) as parada:
        _anexar_no_app(app)
    # Não é culpa do vídeo (o app não guardou o produto): ele pode ir numa próxima vez.
    assert parada.value.motivo == robo.MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU and not parada.value.do_video
    assert robo.passo_do_motivo(parada.value.motivo) == "anexar o produto"
    assert app.toques.count("Feito") == robo.VEZES_DO_PRIMEIRO_PRODUTO and "@et_caption" not in app.toques
    assert [r[0] for r in _registro_do_anexar()] == ["não ficou depois do Feito"] * robo.VEZES_DO_PRIMEIRO_PRODUTO


class AppQueAvisaNoFeito(AppQueReabreALegenda):
    """O app que perde o produto no Feito e mostra um aviso curto (toast), como o uiautomator2 lê."""

    def __init__(self, perdidos=None, aviso="Não foi possível adicionar o produto 1"):
        super().__init__(perdidos)
        self.aviso, self.ultimo_aviso = aviso, None

    def clear_toast(self):
        self.ultimo_aviso = None

    def last_toast(self):
        return self.ultimo_aviso

    def click(self, x, y):
        no_feito = self.atual == "janela"
        super().click(x, y)
        if no_feito and self.atual == "final" and not self.com_produto:
            self.ultimo_aviso = self.aviso


def test_produto_que_nao_fica_no_feito_diz_o_aviso_do_app(monkeypatch, avisos):
    # 31/10, 15:21 e 15:35: o mesmo produto não ficou depois do Feito, duas vezes, e a tela não
    # dizia por quê. A parada traz o aviso curto que o app mostrou (sem os números); o registro, que
    # sai no checkup público, diz só que houve aviso.
    _fonte(monkeypatch)
    app = AppQueAvisaNoFeito(perdidos=5)
    with pytest.raises(robo.Parada) as parada:
        _anexar_no_app(app)
    assert parada.value.motivo == (robo.MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU
                                   + "; o app avisou: Não foi possível adicionar o produto #")
    assert robo.passo_do_motivo(parada.value.motivo) == "anexar o produto"
    assert [d for _r, d in _registro_do_anexar()] == [
        f"{vez}ª vez; a linha dos produtos vazia; a edição da legenda aberta por cima; o app mostrou um aviso"
        for vez in range(1, robo.VEZES_DO_PRIMEIRO_PRODUTO + 1)]
    # Sem aviso nenhum depois do Feito, o registro também diz.
    app = AppQueAvisaNoFeito(perdidos=1, aviso=None)
    _anexar_no_app(app)
    assert _registro_do_anexar()[-2][1].endswith("; sem aviso do app")


class ListaQueDemoraAVoltar:
    """O voltar da lista de Minhas Curtidas que leva uns segundos para mostrar a tela final."""

    def __init__(self):
        self.voltas, self.leituras = 0, 0

    def dump_hierarchy(self):
        self.leituras += 1
        if self.voltas and self.leituras > 2:
            return _xml(*_tela_final())
        return _xml(*TELAS["curtidas"])

    def press(self, tecla, meta=None):
        self.voltas += 1


def test_voltar_a_tela_final_espera_a_tela_antes_de_outro_voltar():
    # Sem a legenda escrita (os produtos vão antes dela), um voltar a mais na tela final leva à
    # edição do vídeo sem aviso: o robô espera a tela final aparecer antes de apertar de novo.
    d = ListaQueDemoraAVoltar()
    robo.voltar_a_tela_final(d)
    assert d.voltas == 1


def test_como_esta_a_tela_final_diz_a_edicao_da_legenda_e_o_foco():
    # A tela final de 31/10, às 09:35, só com os ids que contam (rótulos fixos, nunca o texto).
    tela = ('<hierarchy><node class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">'
            '<node resource-id="com.shopee.br:id/et_caption" text="Título" focused="true" clickable="true" '
            'bounds="[337,280][1080,537]" />'
            '<node resource-id="com.shopee.br:id/rl_overlay" clickable="true" bounds="[0,674][1080,2394]" />'
            '<node resource-id="com.shopee.br:id/tv_add_product_tip" text="Toque para adicionar produtos" '
            'bounds="[539,717][974,760]" /></node></hierarchy>')
    assert robo.ps.como_esta_a_tela_final(tela) == ("a linha dos produtos vazia; a edição da legenda aberta por cima; "
                                                    "a legenda em foco")
    sem_nada = tela.replace('focused="true"', 'focused="false"').replace("rl_overlay", "outro")
    assert robo.ps.como_esta_a_tela_final(sem_nada) == "a linha dos produtos vazia"


def test_descurtir_no_fim_desfaz_cada_produto_curtido_pelo_link_dele(monkeypatch):
    abertos = []
    monkeypatch.setattr(robo, "ir_ao_inicio", lambda d: None)
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    monkeypatch.setattr(robo.ps, "limpar_aviso_rapido", lambda d: None)
    monkeypatch.setattr(robo.ps, "abrir_link", lambda d, link: abertos.append(link))
    monkeypatch.setattr(robo.ps, "descurtir", lambda d, video: (video["link"] != "https://s.shopee.com.br/2", "ok"))
    robo.gravar_estado(favoritos_limpos=True)
    curtidos = [("https://s.shopee.com.br/1", "A"), (None, "B"), ("https://s.shopee.com.br/3", "C")]
    robo.descurtir_no_fim(None, {"link": "https://s.shopee.com.br/2"}, curtidos)
    assert abertos == ["https://s.shopee.com.br/1", "https://s.shopee.com.br/2", "https://s.shopee.com.br/3"]
    # Um não descurtiu: a lista não está limpa até o descurtir das 4h (P27).
    assert not robo.lista_limpa()
    robo.gravar_estado(favoritos_limpos=True)
    robo.descurtir_no_fim(None, {"link": "https://s.shopee.com.br/9"}, curtidos)
    assert robo.lista_limpa()


def test_links_do_canal_levam_os_produtos_a_mais_na_ordem_do_post(monkeypatch):
    async def destino(link):
        return "https://shopee.com.br/product/1/" + link.rsplit("/", 1)[-1]

    async def converter(endereco, etiqueta, avisar_falha=True):
        return f"canal:{endereco.rsplit('/', 1)[-1]}"

    monkeypatch.setattr(robo, "link_para_converter", destino)
    monkeypatch.setattr(robo.api_shopee, "converter_link_shopee", converter)
    rascunho = {"link": "https://s.shopee.com.br/a", "produtos": ["A", "B", "C"],
                "mais_produtos": [{"nome": "B", "link": "https://s.shopee.com.br/b",
                                   "endereco": "https://shopee.com.br/product/9/b9"},
                                  {"nome": "C", "link": "https://s.shopee.com.br/c", "endereco": ""}]}
    assert robo.links_para_o_canal(rascunho) == ["canal:a", "canal:b9", "canal:c"]


def test_itens_do_post_e_os_postados_para_a_medicao():
    # A medição da P73: o número (itemId) de cada produto do post e se é um produto a mais.
    produtos = [dict(PRINCIPAL, item="1"), dict(PRINCIPAL, nome="Loja 2", do_video=False, item=2)]
    assert robo._itens(produtos) == [{"item": "1", "a_mais": False}, {"item": "2", "a_mais": True}]
    ident = robo.criar("v1")
    robo.atualizar(ident, estado="postado", postado_em="2026-10-30 10:00:00", itens=robo._itens(produtos))
    robo.atualizar(robo.criar("v2"), estado="postado", postado_em="2026-10-30 11:00:00")
    robo.atualizar(robo.criar("v3"), estado="rascunho", itens=robo._itens(produtos))
    assert robo.itens_postados() == [("2026-10-30", [{"item": "1", "a_mais": False}, {"item": "2", "a_mais": True}])]
    assert robo.pegar(robo.criar("v4"))["itens"] == []


def test_punicao_de_produto_irrelevante_para_os_produtos_a_mais(monkeypatch, avisos, ia_da_apelacao):
    # Escolha do Rafael (29/10, P73): a punição nova por produto que não é o do vídeo desliga os
    # produtos a mais sozinha, com aviso no privado; ligar de novo, só no painel.
    ident = _postado_pelo_robo()
    robo.atualizar(ident, itens=[{"item": "1", "a_mais": False}, {"item": "2", "a_mais": True}])
    assert robo.ler_config()["robo_produtos_a_mais"] is True
    robo.rodada(saude=True, d=AppDaSaude(), agora=momento("2026-10-24 10:00"))
    config = robo.ler_config()
    assert config["robo_produtos_a_mais"] is False
    assert config["robo_produtos_a_mais_parados"] == "punição de Produto Irrelevante (23/10/2026 19:04:25)"
    parados = [a for a in avisos if "desliguei os produtos a mais" in a]
    assert len(parados) == 1 and "O vídeo punido tinha 1 produto(s) a mais." in parados[0]
    assert robo.CAMINHO_DOS_PRODUTOS_A_MAIS in parados[0]
    # Já desligados, outra punição não avisa de novo; e os espaços livres ficam de fora sem o celular.
    robo.parar_os_produtos_a_mais({"tipo": "Produto Irrelevante", "data": "25/10/2026 10:00:00"})
    assert len([a for a in avisos if "desliguei os produtos a mais" in a]) == 1
    assert robo.espacos_livres(None, {"link": LINK}, PRINCIPAL, {"preco": 50.0}, [], robo.time.monotonic() + 600) == []
    assert _registro_dos_espacos() == ["desligados - punição de produto", "nenhum - desligados"]


def test_punicao_de_outro_tipo_nao_mexe_nos_produtos_a_mais(avisos):
    robo.parar_os_produtos_a_mais({"tipo": "Produto Irrelevante", "data": "23/10/2026 19:04:25"})
    assert "O vídeo punido" not in avisos[-1] and "Não achei o rascunho do robô desse vídeo." in avisos[-1]
    robo.db.atualizar_config(robo.CHAVE_CONFIG, lambda dados: dados.update(robo_produtos_a_mais=True))
    assert robo.PUNICAO_DE_PRODUTO not in "Violação de Propriedade Intelectual".casefold()
    assert robo.PUNICAO_DE_PRODUTO in "Produto Irrelevante".casefold()


def test_rascunho_guarda_as_fotos_de_capa_para_o_album(monkeypatch, tmp_path):
    # Escolha do Rafael (29/10, P75): as fotos de capa de cada produto, na ordem do post, ao lado
    # do vídeo do rascunho; a do produto a mais veio da conferência, a do principal vem da API.
    monkeypatch.setattr(robo, "PASTA_RASCUNHOS", str(tmp_path))
    monkeypatch.setattr(robo.ps, "anuncio_do_produto",
                        lambda video: {"foto": b"\x89PNG\r\n\x1a\nprincipal"} if "principal" in video["link"] else {})
    produtos = [dict(PRINCIPAL), dict(PRINCIPAL, nome="Loja 2", link="https://s.shopee.com.br/2", do_video=False,
                                      foto=b"\xff\xd8\xffloja2"),
                dict(PRINCIPAL, nome="Loja 3", link="https://s.shopee.com.br/3", do_video=False)]
    capas = robo.guardar_capas(7, {"link": LINK}, produtos)
    assert [os.path.basename(c) for c in capas] == ["7_capa_1.png", "7_capa_2.jpg"]
    assert open(capas[1], "rb").read() == b"\xff\xd8\xffloja2"
    # As capas saem com o vídeo e o print do rascunho usado.
    assert all(robo.ARQUIVO_NO_SERVIDOR.match(nome) for nome in ("7.mp4", "7.png", "7_capa_1.png", "7_capa_2.jpg"))
    assert not robo.ARQUIVO_NO_SERVIDOR.match("treino.png") and not robo.ARQUIVO_NO_SERVIDOR.match("7_capa.jpg")
    ident = robo.criar("v9")
    robo.atualizar(ident, capas=capas)
    assert robo.pegar(ident)["capas"] == capas and robo.pegar(robo.criar("v10"))["capas"] == []


def _foto_de_teste(forma, loja=None):
    """Uma foto de anúncio em JPEG; com loja (uma cor), a moldura e o selo que a loja põe na borda."""
    from PIL import Image, ImageDraw
    imagem = Image.new("RGB", (400, 400), "white")
    desenho = ImageDraw.Draw(imagem)
    if forma == "cubo":
        desenho.rectangle((100, 120, 300, 320), fill=(230, 120, 30))
        desenho.ellipse((150, 170, 250, 270), fill=(200, 30, 30))
    elif forma == "triangulo":
        desenho.polygon(((200, 50), (360, 350), (40, 350)), fill=(40, 140, 60))
    else:
        desenho.ellipse((60, 60, 340, 340), fill=(40, 160, 200))
        desenho.rectangle((180, 100, 220, 300), fill=(250, 220, 0))
    if loja:
        desenho.rectangle((0, 0, 399, 399), outline=loja, width=18)
        desenho.rectangle((300, 0, 399, 40), fill=loja)
    saida = io.BytesIO()
    imagem.save(saida, format="JPEG")
    return saida.getvalue()


def test_rascunho_marca_os_produtos_com_outra_foto_de_capa(monkeypatch):
    # Escolha do Rafael (30/10, P102): basta ser o mesmo produto, e a foto de capa diferente da do
    # anúncio do post vem marcada para ele conferir. A comparação é da imagem: a moldura e o selo
    # que a loja põe na borda não contam.
    capa = _foto_de_teste("cubo")
    pedidos = []

    def anuncio(video):
        pedidos.append(video["link"])
        return {"foto": capa}

    monkeypatch.setattr(robo.ps, "anuncio_do_produto", anuncio)
    produtos = [dict(PRINCIPAL), dict(PRINCIPAL, nome="Loja 2", link="https://s.shopee.com.br/2", do_video=False,
                                      foto=_foto_de_teste("cubo", loja=(0, 120, 0))),
                dict(PRINCIPAL, nome="Loja 3", link="https://s.shopee.com.br/3", do_video=False,
                     foto=_foto_de_teste("outra"))]
    assert robo.mesma_foto(capa, produtos[1]["foto"]) is True
    assert robo.mesma_foto(capa, produtos[2]["foto"]) is False
    assert robo.mesma_foto(capa, b"nao e foto") is None
    assert robo.com_outra_foto_de_capa({"link": LINK}, produtos, capa) == [3]
    # A foto do produto do link vem da API uma vez só e fica no produto (o álbum usa a mesma).
    assert robo.com_outra_foto_de_capa({"link": LINK}, produtos, capa) == [3] and pedidos == [PRINCIPAL["link"]]
    assert robo.com_outra_foto_de_capa({"link": LINK}, produtos, None) == []
    ident = robo.criar("v11")
    robo.atualizar(ident, outras_capas=[3])
    assert robo.pegar(ident)["outras_capas"] == [3] and robo.pegar(robo.criar("v12"))["outras_capas"] == []


def test_miniatura_troca_entre_as_fotos_diferentes_dos_produtos_do_post(monkeypatch, tmp_path):
    # Escolha do Rafael (30/10, P103): no rascunho com produtos a mais (o mesmo item de outras
    # lojas), a miniatura troca entre as fotos de capa diferentes dos produtos do post, na ordem
    # do post, uma volta só, com o vídeo dividido igual e pelo menos 3 s para cada: as que não
    # cabem, as últimas (as que pagam menos), ficam de fora. A foto de outra loja igual a uma que
    # já entrou (só com o selo e a moldura dela) conta uma vez, e a que não abre fica de fora.
    import registro_processos as rp
    original, copia = str(tmp_path / "v.mp4"), str(tmp_path / "c.mp4")
    with open(original, "wb") as arquivo:
        arquivo.write(b"v")
    chamadas, duracoes = [], [30.0, 7.0, 4.0, 0.0, RuntimeError("sem ffprobe")]

    def editar_para_postar(video, foto, destino, produto="", avisos=False, outras_fotos=(), figurinha=None):
        chamadas.append(list(outras_fotos))
        with open(destino, "wb") as arquivo:
            arquivo.write(b"editado")
        return "", robo.edicao_video.COM_LEGENDAS, ""

    def duracao(caminho):
        resposta = duracoes.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    cubo, bola, triangulo = _foto_de_teste("cubo"), _foto_de_teste("bola"), _foto_de_teste("triangulo")
    monkeypatch.setattr(robo.ps, "anuncio_do_produto", lambda video: {"foto": cubo, "nome": VESTIDO})
    monkeypatch.setattr(robo.edicao_video, "editar_para_postar", editar_para_postar)
    monkeypatch.setattr(robo.videos, "duracao", duracao)
    ativar(edicao_ligada=True)
    video = {"arquivo": original, "link": LINK}
    outras = [_foto_de_teste("cubo", (20, 20, 200)), bola, b"nao abre", _foto_de_teste("bola", (200, 20, 20)),
              triangulo]
    for _ in range(5):
        robo.copiar_para_o_rascunho(video, "viral", copia, [VESTIDO], outras=outras)
    # 30 s: as 3 fotos diferentes, 10 s cada; 7 s: só cabem 2; 4 s: nenhuma troca; sem a duração
    # do vídeo, ou com erro, também não.
    assert chamadas == [[bola, triangulo], [bola], [], [], []]
    # Todas iguais à do 1º: uma foto só, sem nem ler a duração.
    robo.copiar_para_o_rascunho(video, "viral", copia, [VESTIDO], outras=[_foto_de_teste("cubo", (20, 20, 200))])
    assert chamadas[-1] == [] and not duracoes
    registros = {(l[2], l[3], l[4]) for l in rp.contagem("2000-01-01 00:00:00") if l[1] == robo.PROCESSO_DA_MINIATURA}
    assert registros == {("alternada", "3 fotos, 10,0 s cada", 1),
                         ("alternada", "2 fotos de 3 diferentes, 3,5 s cada", 1),
                         ("uma só", "o vídeo é curto para trocar (4 s)", None),
                         ("uma só", "a duração do vídeo não foi lida", None),
                         ("uma só", "erro (RuntimeError)", 0),
                         ("uma só", "nenhuma foto diferente da do 1º produto", None)}
    # Sem os outros produtos (um produto só, ou o Ver Produtos, de itens que podem ser outros), nada
    # é comparado, e a miniatura fica uma só.
    robo.copiar_para_o_rascunho(video, "viral", copia, [VESTIDO])
    assert chamadas[-1] == [] and len(registros) == 6


def test_rascunho_guarda_os_produtos_a_mais():
    ident = robo.criar("v1")
    robo.atualizar(ident, produtos=["A", "B"], mais_produtos=[{"nome": "B", "link": "l", "endereco": "e"}])
    rascunho = robo.pegar(ident)
    assert rascunho["produtos"] == ["A", "B"] and rascunho["mais_produtos"] == [{"nome": "B", "link": "l", "endereco": "e"}]
    assert robo.pegar(robo.criar("v2"))["mais_produtos"] == []


def _cartao_da_busca(coluna, y, nome, preco, taxa):
    """Um cartão dos resultados da busca pela foto, nas posições do Motorola (29/10/2026)."""
    x = 276 if coluna == 0 else 799
    return [_no(nome, caixa=(x - 220, y - 278, x + 220, y - 208), clicavel=False),
            _no("R$", caixa=(x - 231, y - 120, x - 203, y - 92), clicavel=False),
            _no(preco, caixa=(x - 203, y - 136, x - 103, y - 92), clicavel=False),
            _no(f"Taxa de comissão {taxa}%", caixa=(x - 227, y - 18, x + 133, y + 18), clicavel=False)]


class AppDaBuscaPelaFoto(AppDeMentira):
    """A busca pela foto de mentira: Eu → Criadores & Afiliados → câmera → galeria → resultados, em páginas."""

    def __init__(self, sem_resultado=False):
        super().__init__()
        self.sem_resultado, self.pagina, self.ordenado = sem_resultado, 0, False
        linha = lambda y, *nomes: [n for i, nome in enumerate(nomes) for n in _cartao_da_busca(i, y, nome, "49,90", "10,0")]
        self.paginas = [linha(1533, "Garrafa A", "Garrafa B"),
                        linha(1326, "Garrafa C", "Garrafa D") + linha(2262, "Garrafa E", "Garrafa F")]

    def _nos(self):
        topo = [_no("Resultados da busca por imagem", caixa=(240, 250, 840, 300), clicavel=False),
                _no(ident="AN_component_IcCloseShape_Img", caixa=(990, 246, 1046, 302))]
        if self.atual == "afiliado":
            return [_no(ident="AN_ImageSearchIconEntry_IcCameraOutline_Img", caixa=(870, 163, 922, 215)),
                    _no("Conversão", caixa=(40, 600, 300, 660))]
        if self.atual == "camera":
            return [_no(caixa=(451, 1480, 631, 1660)), _no("Pesquisar na galeria", caixa=(268, 1820, 668, 1864),
                                                          clicavel=False),
                    '<node text="" class="android.widget.ImageView" clickable="true" bounds="[38,1917][278,2157]" />']
        if self.atual == "resultados":
            if self.sem_resultado:
                return topo + [_no("Nenhum produto encontrado", caixa=(340, 906, 740, 946), clicavel=False),
                               _no("Você também pode gostar", caixa=(340, 1259, 740, 1299), clicavel=False)]
            return topo + [_no("Vendas Populares", caixa=(300, 555, 540, 600))] + (
                self.paginas[min(self.pagina, len(self.paginas) - 1)] if self.ordenado else [])
        return {"inicio": [ABA_EU], "eu": [ABA_EU, _no("Criadores & Afiliados", caixa=(560, 1640, 1060, 1700))]}[self.atual]

    def click(self, x, y):
        import postador_shopee_video as ps
        nomes = [el["texto"] or "@" + el["id"] for el in ps.elementos(self.dump_hierarchy()) if ps._dentro((x, y), el["caixa"])]
        self.toques.append(nomes[0] if nomes else (x, y))
        destinos = {("inicio", "Eu"): "eu", ("eu", "Criadores & Afiliados"): "afiliado",
                    ("afiliado", "@AN_ImageSearchIconEntry_IcCameraOutline_Img"): "camera",
                    ("resultados", "@AN_component_IcCloseShape_Img"): "camera"}
        if self.atual == "camera" and (x, y) == (158, 2037):
            self.atual = "resultados"
        elif self.atual == "resultados" and "Vendas Populares" in nomes:
            self.ordenado = True
        for nome in nomes:
            if (self.atual, nome) in destinos:
                self.atual = destinos[(self.atual, nome)]
                return

    def swipe(self, *pontos):
        self.toques.append("rolar")
        self.pagina += 1


def test_busca_pela_foto_le_os_cartoes_em_vendas_populares_e_tira_a_foto_da_galeria(monkeypatch):
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    monkeypatch.setattr(robo.ps.time, "sleep", lambda s: None)
    app = AppDaBuscaPelaFoto()
    cartoes, motivo = robo.buscar_pela_foto(app, b"\xff\xd8\xfffoto")
    assert motivo == "" and [c["nome"] for c in cartoes] == ["Garrafa A", "Garrafa B", "Garrafa C", "Garrafa D",
                                                              "Garrafa E", "Garrafa F"]
    assert cartoes[0] == {"nome": "Garrafa A", "selo": False, "preco": 49.9, "comissao": 10.0, "extra": False}
    # Nunca o botão de tirar foto: a foto mais nova da galeria, e a ordem Vendas Populares (P68).
    assert (541, 1570) not in app.toques and "Vendas Populares" in app.toques
    assert app.toques.count("rolar") == 2 and "@AN_component_IcCloseShape_Img" in app.toques
    # A foto entra com um nome novo e sai no fim, com as que outra busca deixou.
    [(_origem, foto)] = app.enviados
    assert foto.startswith(f"{robo.ps.NOME_DA_FOTO}_")
    assert ["find", robo.ps.GALERIA, "-maxdepth", "1", "-name", f"{robo.ps.NOME_DA_FOTO}*", "-delete"] in app.comandos
    assert ["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d",
            f"file://{robo.ps.GALERIA}/{foto}"] in app.comandos


def test_busca_pela_foto_sem_resultado_nao_le_as_recomendacoes(monkeypatch):
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    monkeypatch.setattr(robo.ps.time, "sleep", lambda s: None)
    app = AppDaBuscaPelaFoto(sem_resultado=True)
    assert robo.buscar_pela_foto(app, b"\xff\xd8\xfffoto") == ([], "a busca pela foto não achou o produto")
    assert "Vendas Populares" not in app.toques and "rolar" not in app.toques
    assert ["find", robo.ps.GALERIA, "-maxdepth", "1", "-name", f"{robo.ps.NOME_DA_FOTO}*", "-delete"] in app.comandos


# --- As visualizações na grade do Perfil: a medição da capa com chamada (P76) ---

LARGURA_DO_QUADRO, ALTURA_DO_QUADRO = 358, 470


def _capa_de_mentira(semente):
    """Uma capa que dá uma marca só dela (ruído com a semente)."""
    from PIL import Image
    gerador = random.Random(semente)
    pequena = Image.new("L", (12, 12))
    pequena.putdata([gerador.randrange(256) for _ in range(144)])
    return pequena.resize((LARGURA_DO_QUADRO, ALTURA_DO_QUADRO)).convert("RGB")


def _tela_da_grade(quadros):
    """
    (xml, print) do Perfil: quadros [(x1, y1, semente ou None, textos)] com o tamanho do
    Motorola; semente None é o quadro sem a capa carregada (uma cor só).
    """
    from PIL import Image
    imagem = Image.new("RGB", (1080, 2400), "black")
    nos = []
    for x1, y1, semente, textos in quadros:
        y2 = min(y1 + ALTURA_DO_QUADRO, 2400)
        if semente is not None:
            imagem.paste(_capa_de_mentira(semente).crop((0, 0, LARGURA_DO_QUADRO, y2 - y1)), (x1, y1))
        filhos = "".join(_no(t, caixa=(x1 + 20, y2 - 60 - 50 * i, x1 + 200, y2 - 20 - 50 * i), clicavel=False)
                         for i, t in enumerate(textos))
        nos.append(_no(caixa=(x1, y1, x1 + LARGURA_DO_QUADRO, y2), filhos=filhos, desc="profile video 1"))
    return _xml(*nos), imagem


class AppDaGrade:
    """O Perfil em Shopee Vídeo de mentira: cada rolada mostra a próxima tela da grade."""

    def __init__(self, telas):
        self.telas, self.vez, self.roladas = telas, 0, 0

    def dump_hierarchy(self):
        return self.telas[self.vez][0]

    def screenshot(self, caminho=None):
        return self.telas[self.vez][1]

    def window_size(self):
        return 1080, 2400

    def swipe(self, *pontos):
        self.roladas += 1
        self.vez = min(self.vez + 1, len(self.telas) - 1)


def _marca(semente):
    imagem = _capa_de_mentira(semente)
    return robo.visualizacoes.marca_da_capa(imagem, (0, 0, LARGURA_DO_QUADRO, ALTURA_DO_QUADRO))


def test_quadros_da_grade_tiram_o_de_rascunhos_e_o_cortado_e_leem_o_numero():
    xml, _ = _tela_da_grade([(0, 1210, 1, ["Rascunhos: 1"]), (361, 1210, 2, ["3,4 mil", "Fixado"]),
                             (722, 1210, 3, ["57"]), (0, 2156, 4, ["9"])])
    quadros = robo.quadros_da_grade(xml)
    assert [(q["caixa"][0], q["fixado"], q["vistas"]) for q in quadros] == [(361, True, 3400), (722, False, 57)]


def test_post_guarda_a_marca_da_capa_e_espera_a_capa_carregar(monkeypatch):
    ident = _rascunho("postado", postado_em="2026-10-29 10:00:00")
    _, sem_capa = _tela_da_grade([(722, 1210, None, ["0"])])
    _, com_capa = _tela_da_grade([(722, 1210, 7, ["0"])])
    prints = [sem_capa, com_capa]
    celular = type("Celular", (), {"screenshot": lambda self, caminho=None: prints.pop(0)})()
    caixa = (722, 1210, 722 + LARGURA_DO_QUADRO, 1210 + ALTURA_DO_QUADRO)
    assert robo.marcar_o_post(celular, ident, caixa) == _marca(7) == robo.pegar(ident)["marca"]
    # Sem o print, o post segue sem a marca (e o checkup conta).
    outro = _rascunho("postado", postado_em="2026-10-29 11:00:00")
    assert robo.marcar_o_post(object(), outro, caixa) is None and not robo.pegar(outro)["marca"]


def test_visualizacoes_achadas_pela_marca_na_grade_rolando_ate_o_fim(monkeypatch):
    # Escolha do Rafael (29/10, P76): os vídeos do robô são achados na grade pela marca da
    # capa, e o número de cada um fica no rascunho; o que não é do robô fica de fora.
    monkeypatch.setattr(robo, "ir_ao_perfil", lambda d: None)
    agora = momento("2026-10-30 09:00")
    r1 = _rascunho("postado", postado_em="2026-10-23 10:00:00", marca=_marca(16))
    r2 = _rascunho("postado", postado_em="2026-10-27 10:00:00", marca=_marca(13))
    # Dois posts com a mesma foto de capa: casam na ordem da grade (o mais novo vem antes).
    r2b = _rascunho("postado", postado_em="2026-10-28 10:00:00", marca=_marca(13))
    r3 = _rascunho("postado", postado_em="2026-10-29 20:00:00", marca=_marca(11), chamada="1")
    velho = _rascunho("postado", postado_em="2026-10-20 10:00:00", marca=_marca(15))
    sem_marca = _rascunho("postado", postado_em="2026-10-29 21:00:00")
    linha_2 = [(0, 1683, 12, ["1,2 mil"]), (361, 1683, 13, ["980"]), (722, 1683, 14, ["15"])]
    tela_1 = _tela_da_grade([(0, 1210, 1, ["Rascunhos: 1"]), (361, 1210, 10, ["3,4 mil", "Fixado"]),
                             (722, 1210, 11, ["57"])] + linha_2 + [(0, 2156, 15, ["9"])])
    linha_2_em_cima = [(x, 1210, semente, textos) for x, _y, semente, textos in linha_2]
    tela_2 = _tela_da_grade(linha_2_em_cima + [(0, 1683, 15, ["9"]), (361, 1683, 16, ["400"]),
                                               (722, 1683, 13, ["321"])])
    app = AppDaGrade([tela_1, tela_2])
    assert robo.anotar_visualizacoes(app, agora) == (4, 4)
    momento_da_leitura = "2026-10-30 09:00:00"
    assert robo.pegar(r3)["vistas"] == [[momento_da_leitura, 57]]
    assert robo.pegar(r2b)["vistas"] == [[momento_da_leitura, 980]]
    assert robo.pegar(r2)["vistas"] == [[momento_da_leitura, 321]]
    assert robo.pegar(r1)["vistas"] == [[momento_da_leitura, 400]]
    assert robo.pegar(velho)["vistas"] == [] and robo.pegar(sem_marca)["vistas"] == []
    assert app.roladas == 1
    assert consultar("SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DAS_VISUALIZACOES) == ("lidas", "4 de 4 vídeo(s)", 1)
    # A medição separa os com a chamada dos de antes (o de 10 dias ainda entra na comparação).
    medicao = robo.medicao_da_capa(agora)
    assert (medicao["com"]["videos"], medicao["sem"]["videos"], medicao["sem_marca"]) == (1, 4, 1)


def test_sem_video_com_marca_nao_abre_o_perfil(monkeypatch):
    monkeypatch.setattr(robo, "ir_ao_perfil", lambda d: pytest.fail("não precisava abrir o Perfil"))
    _rascunho("postado", postado_em="2026-10-29 10:00:00")
    assert robo.anotar_visualizacoes(object(), momento("2026-10-30 09:00")) == (0, 0)


# --- A capa com a frase pela figurinha (P110) ---

def _foto_do_anuncio():
    """Uma foto com desenho (um degradê azul), para a marca da capa na grade sair."""
    from PIL import Image
    foto = Image.new("RGB", (800, 800))
    foto.putdata([(40 + x // 8, 100 + y // 6, 200) for y in range(800) for x in range(800)])
    saida = io.BytesIO()
    foto.save(saida, "JPEG")
    return saida.getvalue()


CAPA_DA_FIGURINHA = robo.edicao_video.capa_com_chamada(_foto_do_anuncio(), "Alivia a dor")
QUADRO_DA_CAPA = (61, 267, 1018, 1969)
ESCALA_DO_DESENHO = (QUADRO_DA_CAPA[2] - QUADRO_DA_CAPA[0]) / 720


class CelularDaCapa:
    """
    A tela final, a Selecione sua capa e as telas da figurinha com foto, como no Motorola em
    30 e 31/10. A figurinha (o miolo da capa) entra com a escala de entrada (px da tela por px
    da capa) no meio do quadro; dois dedos a aumentam pela razão das distâncias vezes o ganho
    (o app não segue os dedos à risca), até a escala máxima, e o arrastar a move.
    """

    def __init__(self, entrada=0.443, ganho=1.0, maxima=10.0, meio=(540, 1118), usadas=False, parado=1.0,
                 letras_grossas=False, teimosas=0):
        self.atual, self.figurinha, self.salva, self.usadas = "final", None, None, usadas
        # teimosas: as primeiras figurinhas que entram não mudam com os dois dedos.
        self.teimosas, self.entradas = teimosas, 0
        self.entrada, self.ganho, self.maxima, self.meio = entrada, ganho, maxima, meio
        # parado: dedos que abrem ou fecham menos que essa razão não mudam a figurinha.
        # letras_grossas: no print, as letras brancas da faixa mais grossas (como no Motorola).
        self.parado, self.letras_grossas = parado, letras_grossas
        self.galeria, self.toques, self.gestos, self.arrastos, self.teclas = set(), [], [], [], []
        self.pontos = []

    def _nos(self):
        capa = [_no(ident="player_container", caixa=(0, 267, 1080, 1969), clicavel=False),
                _no(ident="cancel_btn", caixa=(40, 150, 120, 240)), _no(ident="save_btn", caixa=(960, 150, 1040, 240)),
                _no("Adicionar Texto", "fl_add_text", (40, 2260, 520, 2366)),
                _no("Adicionar figurinha", "fl_add_sticker", (560, 2260, 1040, 2366))]
        if self.atual == "final":
            return _tela_final(TITULO, self.salva is not None) + [
                _no("Selecionar Capa", "tv_select_cover", (42, 563, 305, 632))]
        if self.atual == "capa":
            return capa
        if self.atual == "figurinhas":
            painel = [_no(ident="tab_layout", caixa=(0, 1260, 1080, 1366), clicavel=False,
                          filhos=_no(ident="image", caixa=(20, 1270, 110, 1342), clicavel=False)
                          + _no("Texto", "text", (380, 1280, 470, 1332))),
                      _no(ident="local_sticker_frame_layout", caixa=(0, 1400, 1080, 2366), clicavel=False)]
            if self.usadas:
                painel += [_no(caixa=(90, 1450, 200, 1560)), _no(caixa=(350, 1450, 470, 1560))]
            else:
                painel += [_no("Enviar", "btn_upload", (440, 1880, 640, 1956))]
            return capa + painel
        if self.atual == "fotos":
            return [_no(ident="iv_picture", caixa=(60, 330, 206, 476)), _no(ident="iv_picture", caixa=(220, 330, 366, 476))]
        if self.atual == "recorte":
            return [_no("Próximo", "tv_next_full", (860, 2230, 1014, 2306))]
        if self.atual == "descartar":
            return capa + [_no("Descartar Alterações na Capa?", caixa=(200, 1100, 880, 1160), clicavel=False),
                           _no("Cancelar", "tv_cancel", (200, 1300, 520, 1380)),
                           _no("Confirmar", "tv_discard", (560, 1300, 880, 1380))]
        return []

    def dump_hierarchy(self):
        return _xml(*self._nos())

    def click(self, x, y):
        tocados = [el for el in robo.ps.elementos(self.dump_hierarchy()) if robo.ps._dentro((x, y), el["caixa"])]
        tocados.sort(key=lambda el: (el["caixa"][2] - el["caixa"][0]) * (el["caixa"][3] - el["caixa"][1]))
        ids = {"@" + el["id"] for el in tocados if el["id"]}
        # O menor elemento no ponto é o que o dedo tocou.
        self.toques.append(next(("@" + el["id"] for el in tocados if el["id"]), (x, y)))
        if self.atual == "final" and "@tv_select_cover" in ids:
            self.atual = "capa"
        elif self.atual == "capa" and "@fl_add_sticker" in ids:
            self.atual = "figurinhas"
        elif self.atual == "figurinhas" and ("@btn_upload" in ids or (self.usadas and 1450 <= y <= 1560 and x < 200)):
            self.atual = "fotos"
        elif self.atual == "fotos" and "@iv_picture" in ids:
            self.atual = "recorte"
        elif self.atual == "recorte" and "@tv_next_full" in ids:
            self.atual, self.figurinha = "capa", {"escala": self.entrada, "x": self.meio[0], "y": self.meio[1]}
            self.entradas += 1
        elif self.atual == "capa" and "@save_btn" in ids:
            self.atual, self.salva = "final", self.figurinha
        elif self.atual == "capa" and "@cancel_btn" in ids:
            self.atual = "descartar" if self.figurinha else "final"
        elif self.atual == "descartar" and "@tv_discard" in ids:
            self.atual, self.figurinha = "final", None

    def press(self, tecla, meta=None):
        self.teclas.append(tecla)
        self.atual = {"figurinhas": "capa", "fotos": "figurinhas", "recorte": "fotos",
                      "capa": "descartar" if self.figurinha else "final"}.get(self.atual, self.atual)

    def __call__(self, **seletor):
        celular = self

        class Gesto:
            def gesture(self, *dedos, steps=0):
                # O uiautomator2 recusa ponto negativo com AssertionError (pos_rel2abs).
                assert all(x >= 0 and y >= 0 for x, y in dedos)
                celular.pontos.append(dedos)
                (a, b, c, d) = dedos
                de = math.dist(a, b)
                ate = math.dist(c, d)
                meio_x, meio_y = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                celular.gestos.append((de, ate))
                f = celular.figurinha
                if 1 / celular.parado < ate / de < celular.parado or celular.entradas <= celular.teimosas:
                    return
                nova = min(celular.maxima, f["escala"] * (ate / de) ** celular.ganho)
                razao = nova / f["escala"]
                f.update(escala=nova, x=meio_x + (f["x"] - meio_x) * razao, y=meio_y + (f["y"] - meio_y) * razao)
        return Gesto()

    def drag(self, x1, y1, x2, y2, duracao=0):
        self.arrastos.append((x1, y1, x2, y2))
        if self.figurinha:
            self.figurinha["x"] += x2 - x1
            self.figurinha["y"] += y2 - y1

    def screenshot(self, caminho=None):
        from PIL import Image
        tela = Image.new("RGB", (1080, 2400), (25, 25, 25))
        x1, y1, x2, y2 = QUADRO_DA_CAPA
        quadro = Image.new("RGB", (x2 - x1, y2 - y1), "black")
        if self.atual == "capa" and self.figurinha:
            miolo = Image.open(io.BytesIO(robo.edicao_video.recorte_da_figurinha(CAPA_DA_FIGURINHA))).convert("RGB")
            f = self.figurinha
            largura, altura = round(miolo.width * f["escala"]), round(miolo.height * f["escala"])
            quadro.paste(miolo.resize((largura, altura)), (round(f["x"] - largura / 2) - x1, round(f["y"] - altura / 2) - y1))
        tela.paste(quadro, (x1, y1))
        return _com_letras_grossas(tela) if self.letras_grossas else tela

    def shell(self, partes):
        if partes[0] == "find":
            self.galeria = {n for n in self.galeria if not n.startswith(robo.ps.NOME_DA_FOTO)}
        saida = "\n".join(sorted(self.galeria)) if partes[0] == "content" else ""
        return type("R", (), {"output": saida})()

    def push(self, origem, destino):
        self.galeria.add(destino.rsplit("/", 1)[-1])


def _com_letras_grossas(imagem, px=3):
    """
    O print com o branco px pontos mais largo para cada lado: as letras da faixa ficam como no
    print do Motorola em 31/10, com mais branco que laranja nas linhas do meio delas.
    """
    import numpy
    from PIL import Image, ImageFilter
    pontos = numpy.asarray(imagem.convert("RGB")).copy()
    branco = Image.fromarray(((pontos.min(axis=2) > 200) * 255).astype("uint8")).filter(ImageFilter.MaxFilter(2 * px + 1))
    pontos[numpy.asarray(branco) > 0] = 255
    return Image.fromarray(pontos)


def _faixa_na_tela(celular):
    return robo.edicao_video.faixa_laranja(celular.screenshot(), QUADRO_DA_CAPA)


def _no_desenho(celular):
    """
    A figurinha salva deixa a faixa do tamanho e no lugar do desenho, de uma borda à outra do
    quadro? (A medida do print erra uma ou duas linhas.)
    """
    atual, celular.atual, celular.figurinha = celular.atual, "capa", celular.salva
    cima, baixo, esquerda, direita = _faixa_na_tela(celular)
    celular.atual, celular.figurinha = atual, None
    e_cima, e_baixo, e_esquerda, e_direita = robo.faixa_esperada(CAPA_DA_FIGURINHA, QUADRO_DA_CAPA)
    return (abs((baixo - cima) / (e_baixo - e_cima) - 1) <= robo.FOLGA_DA_ESCALA + 0.01
            and abs((cima + baixo) / 2 - (e_cima + e_baixo) / 2) <= robo.FOLGA_DA_POSICAO + 1
            and abs(esquerda - e_esquerda) <= robo.FOLGA_DAS_PONTAS and abs(direita - e_direita) <= robo.FOLGA_DAS_PONTAS)


def test_capa_pela_figurinha_fica_do_tamanho_do_desenho_e_volta_a_tela_final(monkeypatch):
    # Escolha do Rafael (31/10, P110): a capa com a frase pela figurinha com foto, do tamanho do
    # desenho da P107 (a faixa logo acima do número de visualizações da grade).
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    celular = CelularDaCapa()
    ok, motivo = robo.capa_pela_figurinha(celular, CAPA_DA_FIGURINHA)
    assert ok and motivo.startswith("a faixa do tamanho do desenho")
    assert celular.atual == "final" and _no_desenho(celular)
    # A foto da capa saiu da galeria, e nada de voltar na tela final.
    assert celular.galeria == set() and celular.teclas == []


def test_figurinha_que_cresce_mais_que_os_dedos_e_ajustada_ate_o_desenho(monkeypatch):
    # No teste de 31/10, os dois dedos de 200 a 900 px deixaram a figurinha um terço maior que o
    # desenho (a faixa caiu sobre o número de visualizações): o robô mede e corrige. A
    # figurinha que entra fora do meio é arrastada para o lugar.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    celular = CelularDaCapa(ganho=1.25, meio=(540, 1000), usadas=True)
    ok, _ = robo.capa_pela_figurinha(celular, CAPA_DA_FIGURINHA)
    assert ok and _no_desenho(celular)
    assert len(celular.gestos) >= 2 and celular.arrastos
    # Com fotos já usadas, a figurinha nova entra pelo + (o 1º quadro da lista).
    assert "@btn_upload" not in celular.toques


def test_figurinha_que_nao_chega_ao_desenho_e_descartada_e_vai_a_capa_de_sempre(monkeypatch, avisos):
    # O app que não deixa a figurinha crescer até o desenho: o robô desiste, confirma o
    # "Descartar Alterações na Capa?" e segue com a capa de sempre; o registro diz por quê.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    celular = CelularDaCapa(maxima=0.9)
    assert robo.por_a_capa(celular, CAPA_DA_FIGURINHA) is False
    assert celular.atual == "final" and celular.salva is None
    # Antes de desistir, a figurinha foi posta e descartada TENTATIVAS_DA_FIGURINHA vezes (01/11).
    assert celular.entradas == celular.toques.count("@tv_discard") == robo.TENTATIVAS_DA_FIGURINHA
    assert celular.galeria == set()
    resultado, detalhe, ok = consultar("SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = ?",
                                       robo.PROCESSO_DA_CAPA)
    assert (resultado, ok) == ("de fora", None)
    assert detalhe.startswith("3 tentativas; a última: a faixa não ficou do tamanho do desenho")
    # Nenhuma receita de gestos (nenhuma deu certo), mas o ganho dos dedos aprendido fica para a
    # próxima capa: "invés de desistir, aprender para que na próxima dê certo" (Rafael, 01/11).
    guardado = robo.db.ler_config(robo.CHAVE_FIGURINHA, {})
    assert "gestos" not in guardado and robo.GANHO_DOS_DEDOS[0] <= guardado["ganho"] <= robo.GANHO_DOS_DEDOS[1]


def test_figurinha_que_nao_chega_ao_desenho_anota_a_medida_de_cada_ajuste(monkeypatch, avisos):
    # Na 1ª capa pela figurinha de verdade (31/10), a faixa parou em 2/3 do desenho, e o registro
    # só tinha a última medida: não dava para saber se o app não deixou a figurinha crescer ou se
    # a medida pegou outra coisa laranja. Agora o registro diz a faixa de cada medida, só números.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    celular = CelularDaCapa(maxima=0.9)
    # Uma tentativa só (sem tempo para outra): o registro traz as medidas dela inteiras.
    assert robo.por_a_capa(celular, CAPA_DA_FIGURINHA, prazo=time.monotonic() - 1) is False
    (detalhe,) = consultar("SELECT detalhe FROM registro_processos WHERE processo = ?", robo.PROCESSO_DA_CAPA)
    e_cima, e_baixo, e_esquerda, e_direita = robo.faixa_esperada(CAPA_DA_FIGURINHA, QUADRO_DA_CAPA)
    inicio = ("a faixa não ficou do tamanho do desenho; a cada medida, alto x largura, meio e o gesto (o "
              f"desenho, {round(e_baixo - e_cima)}x{round(e_direita - e_esquerda)} e 0): ")
    assert detalhe.startswith(inicio)
    medidas = [medida.split(" ") for medida in detalhe[len(inicio):].split(", ")]
    assert len(medidas) == robo.AJUSTES_DA_FIGURINHA + 1
    altos = [int(medida[0].split("x")[0]) for medida in medidas]
    # Os dois dedos aumentaram a figurinha até o máximo do app, e ali ela parou, abaixo do desenho.
    assert altos[0] < altos[-1] == altos[-2] < round(e_baixo - e_cima)
    assert all(medida[1][0] in "+-" for medida in medidas)
    # Depois de cada medida, menos a última, os dois dedos: de quanto a quanto abertos, em px.
    assert all(len(medida) == 3 and re.fullmatch(r"\d+→\d+", medida[2]) for medida in medidas[:-1])
    assert len(medidas[-1]) == 2
    # Cabe inteiro no registro (os detalhes passam de 240 letras cortados).
    assert len(detalhe) < robo.registro_processos.TAMANHO_DO_DETALHE


def test_figurinha_com_letras_grossas_e_dedos_que_nao_mexem_chega_ao_desenho(monkeypatch):
    # 31/10, 18:49, 19:02 e 19:37: no print do Motorola, as letras da faixa tinham mais branco que
    # laranja nas linhas do meio, a medida pegava só o pedaço acima delas, e o robô aumentava a
    # figurinha além do quadro; e os dedos 3 vezes mais abertos a deixaram 2 vezes maior, e os 1,5
    # vez mais abertos não a mudaram. O robô mede a faixa inteira e aprende com cada gesto.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    celular = CelularDaCapa(ganho=0.66, parado=1.6, letras_grossas=True)
    ok, motivo = robo.capa_pela_figurinha(celular, CAPA_DA_FIGURINHA)
    assert ok and _no_desenho(celular), motivo
    assert len(celular.gestos) >= 2


def test_figurinha_que_nao_ficou_tenta_de_novo_e_fica_na_2a_vez(monkeypatch):
    # Pedido do Rafael (01/11): a capa que não fica certa não é descartada de cara; o robô sai da
    # capa sem salvar, põe a figurinha de novo e ajusta outra vez, e só desiste depois de
    # TENTATIVAS_DA_FIGURINHA vezes.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    celular = CelularDaCapa(teimosas=1)
    ok, motivo = robo.capa_pela_figurinha(celular, CAPA_DA_FIGURINHA)
    assert ok and motivo.endswith(", na 2ª tentativa") and _no_desenho(celular), motivo
    assert celular.entradas == 2 and celular.toques.count("@tv_discard") == 1
    assert celular.atual == "final" and celular.galeria == set()
    # A receita da que deu certo fica guardada para a próxima capa.
    receita = robo.db.ler_config(robo.CHAVE_FIGURINHA, {})
    assert receita["gestos"] and receita["quadro"] == list(QUADRO_DA_CAPA) and receita["entrada"][1] > 0


def test_figurinha_comeca_pela_receita_da_ultima_que_deu_certo(monkeypatch):
    # "a capa uma vez dando certo sempre vai dar dali pra frente" (Rafael, 01/11): a figurinha entra
    # sempre do mesmo tamanho e no mesmo lugar, então os gestos da última que deu certo, refeitos de
    # uma vez, a deixam no desenho, e a medida só confere.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    primeira = CelularDaCapa(ganho=0.66, parado=1.6)
    ok, motivo = robo.capa_pela_figurinha(primeira, CAPA_DA_FIGURINHA)
    assert ok and "da última que deu certo" not in motivo, motivo
    receita = robo.db.ler_config(robo.CHAVE_FIGURINHA, {})
    assert len(receita["gestos"]) == len(primeira.gestos) + len(primeira.arrastos) >= 2
    segunda = CelularDaCapa(ganho=0.66, parado=1.6)
    ok, motivo = robo.capa_pela_figurinha(segunda, CAPA_DA_FIGURINHA)
    assert ok and _no_desenho(segunda), motivo
    assert motivo == f"a faixa do tamanho do desenho (1 ajuste(s), o 1º com os {len(receita['gestos'])} gesto(s) da última que deu certo)"
    # Os mesmos gestos, e nenhum a mais.
    assert segunda.gestos == primeira.gestos and segunda.arrastos == primeira.arrastos
    assert robo.db.ler_config(robo.CHAVE_FIGURINHA, {})["gestos"] == receita["gestos"]


def test_receita_que_nao_chega_fica_de_lado_e_a_nova_toma_o_lugar(monkeypatch):
    # A receita que não leva ao desenho (o app mudou, a figurinha não cresceu) não é refeita de
    # novo no mesmo rascunho: a 2ª tentativa começa do zero, e a receita dela toma o lugar.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    robo.capa_pela_figurinha(CelularDaCapa(), CAPA_DA_FIGURINHA)
    antiga = robo.db.ler_config(robo.CHAVE_FIGURINHA, {})
    robo.db.salvar_config(robo.CHAVE_FIGURINHA, dict(antiga, gestos=[["arrasto", 540, 1118, 540, 900]]))
    celular = CelularDaCapa(teimosas=1)
    ok, motivo = robo.capa_pela_figurinha(celular, CAPA_DA_FIGURINHA)
    assert ok and motivo.endswith(", na 2ª tentativa") and "da última que deu certo" not in motivo, motivo
    assert celular.arrastos[0] == (540, 1118, 540, 900)
    nova = robo.db.ler_config(robo.CHAVE_FIGURINHA, {})
    assert ["arrasto", 540, 1118, 540, 900] not in nova["gestos"] and nova["gestos"]


def test_capa_de_fora_ensina_a_proxima_pelo_ganho_dos_dedos(monkeypatch):
    # Os dedos 3 vezes mais abertos deixam a figurinha só 2 vezes maior (31/10): a capa que ficou
    # de fora guarda o ganho que aprendeu, e a próxima já começa com ele, sem a receita velha.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    robo.db.salvar_config(robo.CHAVE_FIGURINHA, {"quadro": list(QUADRO_DA_CAPA), "entrada": [46, 318],
                                                 "gestos": [["arrasto", 540, 1118, 540, 900]], "ganho": 1.0})
    ok, _ = robo.capa_pela_figurinha(CelularDaCapa(ganho=0.63, maxima=0.9), CAPA_DA_FIGURINHA)
    guardado = robo.db.ler_config(robo.CHAVE_FIGURINHA, {})
    assert not ok and "gestos" not in guardado and guardado["ganho"] < 1.0
    vistos = []
    real = robo.ajustar_a_figurinha

    def ajustar(d, capa, quadro, receita=None, aprendida=None):
        vistos.append(dict(receita or {}))
        return real(d, capa, quadro, receita, aprendida)

    monkeypatch.setattr(robo, "ajustar_a_figurinha", ajustar)
    ok, motivo = robo.capa_pela_figurinha(CelularDaCapa(ganho=0.63), CAPA_DA_FIGURINHA)
    assert ok and vistos[0]["ganho"] == guardado["ganho"] and "gestos" not in vistos[0], motivo


def test_receita_so_serve_no_mesmo_quadro_e_com_a_figurinha_do_mesmo_tamanho():
    receita = {"quadro": list(QUADRO_DA_CAPA), "entrada": [46, 318], "gestos": [["dedos", 540, 1118, 300, 900]]}
    assert robo.receita_serve(receita, QUADRO_DA_CAPA, [46, 330])
    assert not robo.receita_serve(receita, QUADRO_DA_CAPA, [46, 400])
    assert not robo.receita_serve(receita, (0, 0, 10, 10), [46, 318])
    assert not robo.receita_serve(dict(receita, gestos=[]), QUADRO_DA_CAPA, [46, 318])
    assert not robo.receita_serve({}, QUADRO_DA_CAPA, [46, 318])


def test_sem_tempo_no_rascunho_a_capa_nao_tenta_de_novo(monkeypatch):
    # A rodada tem 30 min: depois do prazo (MINUTOS_PARA_A_CAPA do começo do rascunho), a figurinha
    # que não ficou vai direto para a capa de sempre, sem outra tentativa.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    celular = CelularDaCapa(maxima=0.9)
    ok, motivo = robo.capa_pela_figurinha(celular, CAPA_DA_FIGURINHA, prazo=time.monotonic() - 1)
    assert not ok and motivo.startswith("a faixa não ficou do tamanho do desenho; a cada medida")
    assert celular.entradas == 1 and celular.atual == "final" and celular.galeria == set()


def test_ganho_dos_dedos_aprende_com_o_gesto():
    menor, maior = robo.GANHO_DOS_DEDOS
    # Os dedos 3 vezes mais abertos deixaram a figurinha 2 vezes maior: o ganho é log 2 / log 3.
    assert robo.ganho_dos_dedos(1.0, 3.0, 50, 100) == pytest.approx(math.log(2) / math.log(3))
    # Nada mudou: o ganho diminui, e o próximo gesto abre mais os dedos; nunca abaixo do menor.
    assert robo.ganho_dos_dedos(1.0, 1.5, 93, 93) == pytest.approx(robo.REDUCAO_SEM_EFEITO)
    assert robo.ganho_dos_dedos(menor, 1.5, 93, 94) == menor
    # Mudou para o outro lado (a medida errou): nada se aprende. E o ganho fica nos limites.
    assert robo.ganho_dos_dedos(0.8, 2.0, 100, 90) == 0.8
    assert robo.ganho_dos_dedos(1.0, 1.1, 100, 300) == maior


def test_capa_pela_figurinha_guarda_o_caso_com_a_tela_da_capa_antes_de_descartar(monkeypatch):
    # O caso da capa que não deu certo sai com a figurinha ainda na tela da capa (o print mostra
    # como ela ficou); só depois o robô descarta e volta à tela final. A capa que deu certo não
    # guarda caso.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    celular, vistos = CelularDaCapa(maxima=0.9), []
    ok, motivo = robo.capa_pela_figurinha(
        celular, CAPA_DA_FIGURINHA, lambda motivo: vistos.append((celular.atual, celular.figurinha is not None, motivo)))
    # Um caso só, o da última tentativa, com o motivo de todas.
    assert not ok and [visto[:2] for visto in vistos] == [("capa", True)]
    assert vistos[0][2].startswith("3 tentativas: 1ª: a faixa não ficou do tamanho do desenho")
    assert "; 2ª: " in vistos[0][2] and "; 3ª: " in vistos[0][2]
    assert celular.atual == "final" and celular.salva is None and celular.galeria == set()
    celular, vistos = CelularDaCapa(), []
    ok, _ = robo.capa_pela_figurinha(celular, CAPA_DA_FIGURINHA, vistos.append)
    assert ok and vistos == []


def test_dedos_da_figurinha_ficam_no_quadro_mesmo_com_a_faixa_medida_fina(monkeypatch, avisos):
    # 31/10, 14:18 e 14:42: a faixa medida fina demais pediu um gesto maior que a tela, o celular
    # recusou o ponto negativo (AssertionError do uiautomator2) e o rascunho se perdeu. Os dedos
    # ficam sempre dentro do quadro do vídeo, e a figurinha muda no máximo 3 vezes por ajuste.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    real, finas = robo.edicao_video.faixa_laranja, [(1300, 1306, 380, 700)]

    def faixa_laranja(imagem, caixa=None):
        # A 1ª medida no print pega só um fio da faixa; a do desenho (sem caixa) é a de sempre.
        return finas.pop() if caixa is not None and finas else real(imagem, caixa)

    monkeypatch.setattr(robo.edicao_video, "faixa_laranja", faixa_laranja)
    celular = CelularDaCapa()
    ok, motivo = robo.capa_pela_figurinha(celular, CAPA_DA_FIGURINHA)
    assert ok and _no_desenho(celular), motivo
    x1, y1, x2, y2 = QUADRO_DA_CAPA
    assert celular.pontos and all(x1 < x < x2 and y1 < y < y2 for gesto in celular.pontos for x, y in gesto)
    assert all(ate / de <= robo.RAZAO_MAXIMA_POR_AJUSTE + 0.01 for de, ate in celular.gestos)


def test_dedos_da_figurinha_perto_da_borda_chegam_para_dentro():
    x1, _y1, x2, _y2 = QUADRO_DA_CAPA
    for x, largura, razao in ((540, 319, 23), (100, 200, 2), (1000, 150, 0.2), (70, 956, 3), (540, 956, 0.01)):
        meio, de, ate = robo.dedos_da_figurinha(x, QUADRO_DA_CAPA, largura, razao)
        pontos = (meio - de / 2, meio + de / 2, meio - ate / 2, meio + ate / 2)
        assert all(x1 + robo.MARGEM_DOS_DEDOS <= p <= x2 - robo.MARGEM_DOS_DEDOS for p in pontos), (x, razao)
        assert min(de, ate) >= robo.MENOR_DISTANCIA_DOS_DEDOS
        assert 1 / robo.RAZAO_MAXIMA_POR_AJUSTE - 0.01 <= ate / de <= robo.RAZAO_MAXIMA_POR_AJUSTE + 0.01


def test_erro_no_gesto_da_figurinha_descarta_a_capa_e_o_rascunho_segue(monkeypatch, avisos):
    # O gesto que o celular recusa não derruba o rascunho: a figurinha sai (de fora, com as
    # medidas), o caso é guardado com a tela da capa ainda aberta e o rascunho segue com a capa
    # de sempre.
    monkeypatch.setattr(robo, "pausa", lambda s: None)

    def recusa(*args, **kwargs):
        raise AssertionError()

    monkeypatch.setattr(robo.ps, "dois_dedos", recusa)
    celular, vistos = CelularDaCapa(), []
    assert robo.por_a_capa(celular, CAPA_DA_FIGURINHA, lambda motivo: vistos.append((celular.atual, motivo))) is False
    assert [atual for atual, _motivo in vistos] == ["capa"]
    assert vistos[0][1].startswith("3 tentativas: 1ª: a figurinha não foi ajustada: erro AssertionError no gesto; "
                                   "a cada medida, alto x largura")
    assert celular.atual == "final" and celular.salva is None and celular.galeria == set()
    resultado, detalhe = consultar("SELECT resultado, detalhe FROM registro_processos WHERE processo = ?",
                                   robo.PROCESSO_DA_CAPA)
    assert resultado == "de fora" and "AssertionError" in detalhe


def test_erro_inesperado_na_capa_descarta_a_figurinha_mas_a_verificacao_para(monkeypatch):
    # Faltando algum passo da capa, a figurinha sai e o rascunho segue (P110), também num erro
    # que o robô não esperava; a Verificação da Shopee continua parando a rodada.
    monkeypatch.setattr(robo, "pausa", lambda s: None)

    def quebra(xml):
        raise ValueError()

    monkeypatch.setattr(robo, "quadro_da_capa", quebra)
    celular, vistos = CelularDaCapa(), []
    ok, motivo = robo.capa_pela_figurinha(celular, CAPA_DA_FIGURINHA, lambda motivo: vistos.append(celular.atual))
    assert (ok, motivo) == (False, "3 tentativas; a última: a capa pela figurinha deu erro (ValueError)")
    assert vistos == ["capa"]
    assert celular.atual == "final" and celular.galeria == set()
    assert robo.passo_do_motivo(motivo) == "capa pela figurinha"

    def verificacao(xml):
        raise robo.Verificacao()

    monkeypatch.setattr(robo, "quadro_da_capa", verificacao)
    with pytest.raises(robo.Verificacao):
        robo.capa_pela_figurinha(CelularDaCapa(), CAPA_DA_FIGURINHA)


def test_falhas_da_capa_pela_figurinha_ficam_no_passo_dela():
    # O caso e o histórico dizem que a falha foi na capa pela figurinha, não num passo do rascunho.
    for motivo in ("a faixa não ficou do tamanho do desenho; alto x largura e o meio da faixa a cada medida",
                   "a faixa laranja não apareceu na capa (0 ajuste(s))", "a capa não tem a faixa laranja",
                   "a tela da capa não abriu", "a aba da foto da figurinha não apareceu",
                   "nem o Enviar nem o + da figurinha apareceram", "as Fotos não abriram",
                   "o recorte da foto não abriu", "a figurinha não voltou para a capa",
                   "o ✓ da capa não voltou à tela final", f"a figurinha não foi ajustada: {robo.ps.RECUSA}",
                   "a capa pela figurinha não deu certo, e o robô não voltou à tela final"):
        assert robo.passo_do_motivo(motivo) == "capa pela figurinha", motivo
    # As outras fotos e vídeos da galeria continuam no passo da galeria.
    assert robo.passo_do_motivo("a foto do anúncio não apareceu na galeria") == "escolher o vídeo na galeria"
    assert robo.passo_do_motivo("o vídeo não apareceu na galeria do celular") == "escolher o vídeo na galeria"


def test_post_com_a_capa_pela_figurinha_diz_se_a_faixa_chegou_a_grade():
    # A capa vai no rascunho guardado e reaberto para postar: o registro diz se a faixa chegou ao post.
    from PIL import Image
    caixa = (722, 1210, 722 + LARGURA_DO_QUADRO, 1210 + ALTURA_DO_QUADRO)

    def grade(capa_png):
        tela = Image.new("RGB", (1080, 2400), (240, 240, 240))
        capa = Image.open(io.BytesIO(capa_png)).convert("RGB").crop((0, 196, 720, 1116))
        tela.paste(capa.resize((LARGURA_DO_QUADRO, ALTURA_DO_QUADRO)), caixa[:2])
        return type("Celular", (), {"screenshot": lambda self, caminho=None: tela})()

    com = _rascunho("postado", postado_em="2026-10-31 10:00:00", chamada="1")
    assert robo.marcar_o_post(grade(CAPA_DA_FIGURINHA), com, caixa)
    sem = _rascunho("postado", postado_em="2026-10-31 11:00:00", chamada="1")
    assert robo.marcar_o_post(grade(robo.edicao_video.capa_sem_chamada(_foto_do_anuncio())), sem, caixa)
    # Sem a capa pela figurinha, nada a dizer.
    outro = _rascunho("postado", postado_em="2026-10-31 12:00:00")
    assert robo.marcar_o_post(grade(CAPA_DA_FIGURINHA), outro, caixa)
    linhas = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_CAPA, "2000-01-01 00:00:00")
    assert [r[2] for r in linhas] == ["no post com a faixa", "no post sem a faixa"]


class TelaFinalReaberta:
    """A tela final do rascunho reaberto para postar: a miniatura da capa em cima do Selecionar Capa."""
    CAIXA = (78, 286, 268, 626)

    def __init__(self, capa_png=None):
        from PIL import Image
        self.imagem = Image.new("RGB", (1080, 2400), (250, 250, 250))
        if capa_png:
            x1, y1, x2, y2 = self.CAIXA
            capa = Image.open(io.BytesIO(capa_png)).convert("RGB").resize((x2 - x1, y2 - y1))
            self.imagem.paste(capa, (x1, y1))
        self.com_previa = capa_png is not None

    def dump_hierarchy(self):
        nos = [_no(ident="et_caption", caixa=(400, 300, 1040, 520)),
               _no("Selecionar Capa", "tv_select_cover", (78, 575, 268, 620))]
        if self.com_previa:
            nos.append(_no(ident=robo.PREVIA_DA_CAPA, caixa=self.CAIXA, clicavel=False))
        return _xml(*nos)

    def screenshot(self, caminho=None):
        return self.imagem

    def click(self, x, y):
        pass


def _capa_no_post(monkeypatch, tela, chamada="1", guardada=True, volta=(True, "a faixa do tamanho do desenho")):
    ident = _rascunho("aprovado", postar_em="2026-11-01 14:55:00", chamada=chamada)
    if guardada:
        robo.guardar_a_figurinha(ident, CAPA_DA_FIGURINHA)
    pedidas = []

    def capa_pela_figurinha(d, capa, ao_falhar=None, prazo=None):
        pedidas.append(capa)
        if not volta[0] and ao_falhar:
            ao_falhar(volta[1])
        return volta

    casos = []
    monkeypatch.setattr(robo, "capa_pela_figurinha", capa_pela_figurinha)
    monkeypatch.setattr(robo, "_guardar_caso", lambda *a, **k: casos.append(a[1:3]))
    robo.capa_de_novo_no_post(tela, robo.pegar(ident), momento("2026-11-01 14:55"))
    linhas = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_CAPA, "2000-01-01 00:00:00")
    return pedidas, [(r[2], r[3]) for r in linhas], casos


def test_post_poe_a_capa_de_novo_quando_o_rascunho_reaberto_volta_sem_a_faixa(monkeypatch):
    # O app não guarda a figurinha da capa no rascunho: o post das 14:55 de 01/11 foi à grade com o
    # 1º quadro do vídeo. A capa que o Rafael aprovou (P110) vai de novo antes do Postar.
    sem_a_faixa = robo.edicao_video.capa_sem_chamada(_foto_do_anuncio())
    pedidas, linhas, casos = _capa_no_post(monkeypatch, TelaFinalReaberta(sem_a_faixa))
    assert pedidas == [CAPA_DA_FIGURINHA] and casos == []
    assert linhas == [("no rascunho reaberto sem a faixa", ""),
                      ("posta de novo no post", "a faixa do tamanho do desenho")]


def test_post_com_a_faixa_no_rascunho_reaberto_nao_mexe_na_capa(monkeypatch):
    pedidas, linhas, _ = _capa_no_post(monkeypatch, TelaFinalReaberta(CAPA_DA_FIGURINHA))
    assert pedidas == [] and linhas == [("no rascunho reaberto com a faixa", "")]


def test_post_sem_a_miniatura_da_capa_poe_a_capa_de_novo(monkeypatch):
    pedidas, linhas, _ = _capa_no_post(monkeypatch, TelaFinalReaberta())
    assert pedidas == [CAPA_DA_FIGURINHA]
    assert [r for r, _ in linhas] == ["no rascunho reaberto sem a miniatura da capa", "posta de novo no post"]


def test_capa_que_nao_volta_no_post_guarda_o_caso_e_segue(monkeypatch):
    sem_a_faixa = robo.edicao_video.capa_sem_chamada(_foto_do_anuncio())
    pedidas, linhas, casos = _capa_no_post(monkeypatch, TelaFinalReaberta(sem_a_faixa),
                                           volta=(False, "a tela da capa não abriu"))
    assert pedidas == [CAPA_DA_FIGURINHA] and casos == [("postar", "capa de fora")]
    assert linhas[-1] == ("de fora no post", "a tela da capa não abriu")


def test_post_sem_a_capa_pela_figurinha_no_rascunho_nao_mexe_na_capa(monkeypatch):
    # O rascunho que saiu com a capa de sempre vai assim (foi o que o Rafael aprovou); sem o
    # arquivo da capa, também (nada para pôr de novo).
    sem_a_faixa = robo.edicao_video.capa_sem_chamada(_foto_do_anuncio())
    assert _capa_no_post(monkeypatch, TelaFinalReaberta(sem_a_faixa), chamada="")[:2] == ([], [])
    assert _capa_no_post(monkeypatch, TelaFinalReaberta(sem_a_faixa), guardada=False)[:2] == ([], [])


def test_capa_com_a_frase_guardada_sai_na_faxina_com_o_rascunho():
    robo.guardar_a_figurinha(7, CAPA_DA_FIGURINHA)
    caminho = robo.arquivo_da_figurinha(7)
    assert open(caminho, "rb").read() == CAPA_DA_FIGURINHA
    assert robo.ARQUIVO_NO_SERVIDOR.match(os.path.basename(caminho)).group(1) == "7"
    assert not robo.ARQUIVO_NO_SERVIDOR.match("7_figurinha.jpg")


def test_laranja_estreito_nao_e_a_faixa_da_capa():
    # O selo Fixado da grade (laranja, no canto) e um produto laranja na foto não são a faixa,
    # que vai de um lado ao outro da capa.
    from PIL import Image, ImageDraw
    imagem = Image.new("RGB", (358, 476), (240, 240, 240))
    ImageDraw.Draw(imagem).rectangle((12, 20, 110, 60), fill=robo.edicao_video.LARANJA_DA_SHOPEE)
    caixa = (0, 0, 358, 476)
    assert robo.edicao_video.faixa_laranja(imagem, caixa) and robo.faixa_da_capa(imagem, caixa) is None
    ImageDraw.Draw(imagem).rectangle((0, 300, 357, 360), fill=robo.edicao_video.LARANJA_DA_SHOPEE)
    assert robo.faixa_da_capa(imagem, caixa)[:2] == (300, 361)

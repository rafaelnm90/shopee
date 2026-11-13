"""Robô automático da Shopee Vídeo (robo_shopee_video): plano do dia, aprovação espalhada, rodada e o caminho no app."""
import io
import json
import os
import random
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
ACHAR = robo.achar_o_produto_do_video
# E a troca de cada produto do Ver Produtos pelo da loja que paga mais (P57).
TROCAR_OS_DO_VER_PRODUTOS = robo.trocar_os_do_ver_produtos
# E o vídeo postado que vai à fila do Canal Afiliados (P62 a P64), com testes no fim.
LEVAR_AO_CANAL = robo.levar_ao_canal
# E a limpeza das 4h que volta no mesmo dia (P137): no banco novo do teste, ela nunca rodou.
LIMPEZA_FORA_DA_HORA = robo.limpeza_fora_da_hora_pendente


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(robo.time, "sleep", lambda s: None)
    monkeypatch.setattr(robo.ps.time, "sleep", lambda s: None)
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    monkeypatch.setattr(robo, "limpeza_fora_da_hora_pendente", lambda agora=None: False)
    monkeypatch.setattr(robo, "trocar_pela_maior_comissao", lambda video: None)
    # A busca do produto do vídeo quando o do link é outro (P158 2) tem testes próprios.
    monkeypatch.setattr(robo, "achar_o_produto_do_video", lambda video: None)
    # A troca do Ver Produtos (P57) tem testes próprios: aqui, cada produto fica o do criador, na ordem dele.
    monkeypatch.setattr(robo, "trocar_os_do_ver_produtos", lambda d, video, nomes, *a, **k: [
        {"nome": nome, "link": "", "valor": 0, "trocado": "", "do_video": True} for nome in nomes])
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
    # Os alertas do celular (P205 1) vão com o id, para o próximo apagar o de antes: o id é a posição.
    monkeypatch.setattr(robo.avisar_rafael, "mandar_texto_com_id",
                        lambda texto, html=False, teclado=None: mandados.append(texto) or len(mandados))
    monkeypatch.setattr(robo.avisar_rafael, "apagar_mensagem", lambda ident: True)
    monkeypatch.setattr(robo.avisar_rafael, "mandar_foto",
                        lambda caminho, legenda="": mandados.append(("foto", legenda)) or True)
    monkeypatch.setattr(robo.avisar_rafael, "mandar_video",
                        lambda caminho, legenda="": mandados.append(("video", legenda)) or True)
    return mandados


@pytest.fixture
def apagados(monkeypatch, avisos):
    """Os ids das mensagens que o robô apagou do privado (o alerta de antes, P205 1)."""
    lista = []
    monkeypatch.setattr(robo.avisar_rafael, "apagar_mensagem", lambda ident: lista.append(ident) or True)
    return lista


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
    # outro; o que não cabe sem apertar fica de fora.
    config = {**robo.PADRAO, "robo_pausado": False, "robo_inicio": 8, "robo_fim": 22}
    horarios = ["08:30", "09:30", "10:30", "11:30", "12:30", "14:30", "16:30", "18:30", "21:30"]
    robo.db.salvar_config(robo.CHAVE_DIA, {"data": "2026-11-01", "horarios": horarios, "feitos": 0})
    agora = momento("2026-11-01 14:00")
    assert robo.consumir_horarios(config, agora) is True                # o 1º dos perdidos, agora
    estado = robo.estado_do_dia(config, agora)
    futuros = [h for h in estado["horarios"] if h > "14:00"]
    # Das 14:30 às 22:00 cabem 7: os 4 que faltavam e 3 dos 4 perdidos; 1 fica de fora.
    assert len(estado["horarios"]) == 9 and len(futuros) == 7
    assert (estado["feitos"], estado["sem_tentar"]) == (2, 1)
    minutos = [int(h[:2]) * 60 + int(h[3:]) for h in futuros]
    assert minutos[0] >= 14 * 60 + 30
    assert all(depois - antes >= 30 for antes, depois in zip(minutos, minutos[1:]))
    assert robo.consumir_horarios(config, agora) is False
    resultado, detalhe = consultar("SELECT resultado, detalhe FROM registro_processos WHERE processo = ?",
                                   robo.PROCESSO_DOS_PERDIDOS)
    assert resultado == "3 de 4 de volta ao plano" and detalhe == "de fora por falta de espaço no dia: 1"
    # Cada perdido que volta sai no seu horário, um de cada vez.
    assert robo.consumir_horarios(config, momento(f"2026-11-01 {futuros[0]}")) is True
    assert robo.estado_do_dia(config, agora)["feitos"] == 3


def _postado_pelo_assistente(ident, postado_em, cobrindo=True):
    """Um vídeo que o assistente mandou (cobrindo o robô sem o celular, ou não) e o Rafael marcou com Postei ✅."""
    robo.assistente.registrar(ident, "enviado", "", agora=momento(postado_em), cobrindo=cobrindo)
    assert robo.assistente.marcar_postado(robo.assistente.chave_do_envio(ident), momento(postado_em))[0] == "marcado"


def test_videos_do_assistente_com_postei_fecham_horarios_do_plano_do_robo():
    # Escolha do Rafael (05/11, P156 1): sem o celular, o assistente cobre o robô no privado; cada
    # vídeo dele que o Rafael marca com Postei ✅ fecha um horário do plano do dia do robô, primeiro
    # os que passaram e depois os próximos, e o dia não passa do plano.
    config = {**robo.PADRAO, "robo_pausado": False, "robo_inicio": 8, "robo_fim": 22}
    horarios = ["09:00", "12:00", "15:00", "18:00", "21:00"]
    robo.db.salvar_config(robo.CHAVE_DIA, {"data": "2026-11-05", "horarios": horarios, "feitos": 1})
    _postado_pelo_assistente("a1", "2026-11-05 13:10")
    _postado_pelo_assistente("no_ar", "2026-11-05 14:00", cobrindo=False)   # com o robô no ar: não conta
    _postado_pelo_assistente("ontem", "2026-11-04 20:00")                    # de outro dia: não conta
    agora = momento("2026-11-05 16:00")
    # Passaram o das 12h e o das 15h: o a1 fecha um, e o outro sai agora, sem nada para espalhar.
    assert robo.consumir_horarios(config, agora) is True
    estado = robo.estado_do_dia(config, agora)
    assert (estado["feitos"], estado["sem_tentar"], estado["cobertos"]) == (3, 1, ["a1"])
    assert estado["horarios"] == horarios
    assert consultar("SELECT resultado FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DOS_COBERTOS) == ("1 de 2",)
    assert consultar("SELECT COUNT(*) FROM registro_processos WHERE processo = ?", robo.PROCESSO_DOS_PERDIDOS) == (0,)
    assert robo.consumir_horarios(config, agora) is False
    # Marcado depois da volta, o próximo vídeo fecha o horário das 18h, que passa sem rascunho.
    _postado_pelo_assistente("a2", "2026-11-05 16:30")
    assert robo.consumir_horarios(config, momento("2026-11-05 18:00")) is False
    estado = robo.estado_do_dia(config, agora)
    assert (estado["feitos"], estado["sem_tentar"], estado["cobertos"]) == (4, 2, ["a1", "a2"])
    # Sem outro marcado, o das 21h sai como sempre.
    assert robo.consumir_horarios(config, momento("2026-11-05 21:00")) is True


def test_sem_o_postei_o_robo_recupera_todos_os_horarios_como_antes():
    config = {**robo.PADRAO, "robo_pausado": False, "robo_inicio": 8, "robo_fim": 22}
    robo.db.salvar_config(robo.CHAVE_DIA, {"data": "2026-11-05", "horarios": ["09:00", "12:00", "15:00"], "feitos": 0})
    # Mandado cobrindo o robô, mas sem o toque no Postei ✅.
    robo.assistente.registrar("a1", "enviado", "", agora=momento("2026-11-05 10:00"), cobrindo=True)
    agora = momento("2026-11-05 16:00")
    assert robo.consumir_horarios(config, agora) is True
    assert not robo.estado_do_dia(config, agora).get("cobertos")
    assert consultar("SELECT resultado FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DOS_PERDIDOS) == ("2 de 2 de volta ao plano",)


def test_na_pausa_do_rafael_o_video_do_assistente_conta_contra_os_horarios_pulados():
    # Os horários da pausa passam sem rascunho de qualquer jeito: o vídeo marcado conta contra eles
    # e não fecha mais um depois dela.
    config = {**robo.PADRAO, "robo_inicio": 8, "robo_fim": 22}
    robo.db.salvar_config(robo.CHAVE_DIA, {"data": "2026-11-05", "horarios": ["09:00", "12:00", "18:00"], "feitos": 0})
    _postado_pelo_assistente("a1", "2026-11-05 10:00")
    agora = momento("2026-11-05 13:00")
    robo.consumir_horarios(config, agora, pular=True)
    estado = robo.estado_do_dia(config, agora)
    assert (estado["feitos"], estado["sem_tentar"], estado["cobertos"]) == (2, 2, ["a1"])
    assert robo.consumir_horarios(config, momento("2026-11-05 18:00")) is True


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
    ativar(robo_inicio=8, robo_fim=22)
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
    assert "sai numa das próximas rodadas (a cada 15 min)" in texto
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


# --- Sem hora marcada (escolha do Rafael, P161 1) ---

def _sem_hora(**mais):
    return {**robo.PADRAO, "robo_limite_min": 6, "robo_limite_max": 6, "robo_inicio": 8, "robo_fim": 22, **mais}


def test_plano_do_dia_corre_o_horario_do_robo_inteiro():
    # O Horário das Interações saiu do painel (P161 1): o plano espalha os rascunhos pelo Horário do
    # Robô inteiro, e a janela que ficou guardada no banco não conta mais.
    horarios = robo.planejar(_sem_hora(), "2026-10-25")
    assert len(horarios) == 6 and all("08:00" <= h < "22:00" for h in horarios)
    assert robo.trechos_de_postar(_sem_hora()) == [(8 * 60, 22 * 60)]
    antiga = _sem_hora(robo_interacoes_inicio=12, robo_interacoes_fim=15)
    assert robo.planejar(antiga, "2026-10-25") == horarios
    assert robo.no_horario(antiga, momento("2026-10-25 13:00"))
    assert not robo.no_horario(_sem_hora(robo_interacoes_inicio=22, robo_interacoes_fim=24),
                               momento("2026-10-25 22:30"))


def test_sem_hora_marcada_postar_preparar_e_interagir_saem_na_primeira_rodada_livre(monkeypatch):
    # Na hora em que antes ficava a janela das interações, o robô posta e prepara como em qualquer
    # outra; as respostas e o post antigo saem quando chega a vez deles, sem segurar o postar.
    config = _sem_hora(robo_interacoes_inicio=20, robo_interacoes_fim=21)
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-25 20:00")))
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    monkeypatch.setattr(robo, "respostas_pendentes", lambda agora=None: True)
    monkeypatch.setattr(robo, "feed_pendente", lambda agora=None: True)
    monkeypatch.setattr(robo, "post_antigo_pendente", lambda agora=None: {"id": 99})
    aprovado = _rascunho("aprovado", postar_em="2026-10-25 19:00:00")
    assert robo.o_que_fazer(config, momento("2026-10-25 20:00")) == ("postar", aprovado)
    robo.atualizar(aprovado, estado="postado")
    assert robo.o_que_fazer(config, momento("2026-10-25 20:15")) == ("rascunho", None)
    monkeypatch.setattr(robo, "consumir_horarios", lambda config, agora=None: False)
    monkeypatch.setattr(robo, "repetir_o_que_falhou", lambda config, agora=None: False)
    assert robo.o_que_fazer(config, momento("2026-10-25 20:30")) == ("responder", None)
    monkeypatch.setattr(robo, "respostas_pendentes", lambda agora=None: False)
    assert robo.o_que_fazer(config, momento("2026-10-25 20:30")) == ("post_antigo", 99)
    monkeypatch.setattr(robo, "post_antigo_pendente", lambda agora=None: None)
    assert robo.o_que_fazer(config, momento("2026-10-25 20:30")) == ("feed", None)
    monkeypatch.setattr(robo, "feed_pendente", lambda agora=None: False)
    assert robo.o_que_fazer(config, momento("2026-10-25 20:30")) is None


def test_aprovado_sai_em_qualquer_hora_do_horario_do_robo():
    class Sorteio:
        @staticmethod
        def randint(a, b):
            return a

    # Na hora em que antes ficava a janela das interações, o aprovado vai ao ar como em qualquer outra.
    antiga = _sem_hora(robo_interacoes_inicio=12, robo_interacoes_fim=15)
    assert robo.proxima_postagem(antiga, momento("2026-10-25 11:58"), sorteio=Sorteio) == "2026-10-25 12:03:00"
    # Perto do fim do Horário do Robô: vai para o começo dele amanhã.
    assert robo.proxima_postagem(_sem_hora(), momento("2026-10-25 21:58"), sorteio=Sorteio) == "2026-10-26 08:05:00"


def test_feed_se_espalha_pelo_horario_do_robo_inteiro():
    # Escolha do Rafael (P152): os 5 do dia pelo Horário do Robô, no passo das rodadas, com a folga da
    # rodada que começa um pouco antes. A hora das 4h conta: acabada a limpeza, ela fica livre (P161 1).
    from datetime import timedelta
    assert robo.interacoes.VIDEOS_NO_FEED_POR_DIA == 5
    assert robo.intervalo_do_feed({**robo.PADRAO}) == timedelta(hours=2, minutes=40)               # 8h às 22h
    assert robo.intervalo_do_feed({**robo.PADRAO, "robo_inicio": 0, "robo_fim": 24}) == timedelta(hours=4,
                                                                                                minutes=40)
    assert robo.intervalo_do_feed({**robo.PADRAO, "robo_inicio": 9, "robo_fim": 10}) == timedelta(minutes=10)


def test_plano_refeito_conta_o_que_ja_saiu_hoje_e_so_faz_o_que_falta():
    # Pedido do Rafael (06/11): "se eu postei 8 vídeos e depois mudar a faixa de 8-10 e o cálculo der
    # 9 vídeos no dia , ele não deve postar mais nove vídeos e sim 1 somente". Já saíram: os rascunhos
    # de hoje (os do Preparar 1 Agora e os recusados também) e os vídeos do assistente que cobriram o
    # robô sem o celular (P156 1).
    config = {**robo.PADRAO, "robo_pausado": False, "robo_inicio": 8, "robo_fim": 22,
              "robo_limite_min": 8, "robo_limite_max": 12}
    agora = momento("2026-11-10 15:00")
    estado = robo.estado_do_dia(config, agora)
    estado["feitos"] = 5                                          # os horários do plano: 2 saíram no Preparar 1 Agora
    robo.db.salvar_config(robo.CHAVE_DIA, estado)
    for i, situacao in enumerate(["postado"] * 4 + ["aprovado", "recusado", "rascunho"]):
        _rascunho(situacao, criado=f"2026-11-10 {8 + i:02d}:20:00")
    _rascunho("postado", criado="2026-11-09 21:00:00")             # de ontem: não conta
    _rascunho("pulado", criado="2026-11-10 14:10:00")              # o vídeo que ficou de lado: não conta
    _postado_pelo_assistente("a1", "2026-11-10 07:50")
    novo = {**config, "robo_limite_min": 9, "robo_limite_max": 9}
    plano = robo.replanejar_hoje(novo, agora)
    futuros = [h for h in plano["horarios"] if h > "15:00"]
    assert len(plano["horarios"]) == 9 and plano["feitos"] == 8 and len(futuros) == 1 and futuros[0] >= "15:30"
    assert plano["refeito"] == {"no_dia": 9, "saidos": 8, "faltam": 1, "de_fora": 0, "proximo": futuros[0]}
    assert (plano["sem_tentar"], plano["cobertos"]) == (1, ["a1"])
    # Até o fim do dia, só 1 rascunho a mais.
    rodadas = [momento(f"2026-11-10 {h:02d}:{m:02d}") for h in range(15, 22) for m in (0, 15, 30, 45)]
    assert sum(robo.consumir_horarios(novo, rodada) for rodada in rodadas) == 1
    assert consultar("SELECT resultado, detalhe FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DO_PLANO_REFEITO) == ("1 de 9 a fazer",
                                                         "já saíram 8; de fora por falta de espaço no dia: 0")


def test_plano_refeito_e_o_horario_que_espera_a_nova_tentativa():
    config = {**robo.PADRAO, "robo_pausado": False, "robo_inicio": 8, "robo_fim": 22}
    agora = momento("2026-11-10 15:00")
    _rascunho("postado", criado="2026-11-10 09:00:00")
    # Com lugar no dia, o horário que falhou agora e espera a nova tentativa é um dos que faltam.
    estado = robo.estado_do_dia(config, agora)
    estado.update(feitos=2, repetir=True, tentativas=2)
    robo.db.salvar_config(robo.CHAVE_DIA, estado)
    plano = robo.replanejar_hoje({**config, "robo_limite_min": 4, "robo_limite_max": 4}, agora)
    assert (len(plano["horarios"]), plano["feitos"]) == (4, 2)
    assert plano["refeito"] == {"no_dia": 4, "saidos": 1, "faltam": 3, "de_fora": 0, "proximo": ""}
    assert robo.repetir_o_que_falhou(config, agora)
    # Sem lugar (já saíram mais que o número novo), ele acaba: nem tenta de novo, nem volta mais tarde.
    for hora in ("10:00", "11:00", "12:00"):
        _rascunho("postado", criado=f"2026-11-10 {hora}:00")
    estado = robo.estado_do_dia(config, agora)
    estado.update(repetir=True, tentativas=2)
    robo.db.salvar_config(robo.CHAVE_DIA, estado)
    novo = {**config, "robo_limite_min": 3, "robo_limite_max": 3}
    plano = robo.replanejar_hoje(novo, agora)
    assert len(plano["horarios"]) == 3 and plano["feitos"] == 3 and all(h <= "15:00" for h in plano["horarios"])
    assert plano["refeito"] == {"no_dia": 3, "saidos": 4, "faltam": 0, "de_fora": 0, "proximo": ""}
    assert not robo.repetir_o_que_falhou(novo, agora)
    assert not any(robo.consumir_horarios(novo, momento(f"2026-11-10 {h}:00")) for h in range(15, 23))


def test_plano_refeito_no_fim_do_dia_deixa_de_fora_o_que_nao_cabe():
    # Como os perdidos (01/11): os que faltam e não cabem com 1 h em média ficam de fora, e o plano
    # continua com o número do dia.
    config = {**robo.PADRAO, "robo_pausado": False, "robo_inicio": 8, "robo_fim": 22,
              "robo_limite_min": 9, "robo_limite_max": 9}
    agora = momento("2026-11-10 21:50")
    _rascunho("postado", criado="2026-11-10 09:00:00")
    _rascunho("postado", criado="2026-11-10 13:00:00")
    plano = robo.replanejar_hoje(config, agora)
    assert (len(plano["horarios"]), plano["feitos"], plano["sem_tentar"]) == (9, 9, 7)
    assert plano["refeito"] == {"no_dia": 9, "saidos": 2, "faltam": 0, "de_fora": 7, "proximo": ""}
    assert not robo.consumir_horarios(config, momento("2026-11-10 21:59"))


# --- A hora do descurtir (escolhas do Rafael, P25: fixa às 4h, e P161 1: acabada, a hora fica livre) ---

def test_as_4h_a_limpeza_vem_primeiro_e_acabada_a_hora_fica_livre(monkeypatch):
    config = {**robo.PADRAO, "robo_limite_min": 6, "robo_limite_max": 6, "robo_inicio": 0, "robo_fim": 24}
    monkeypatch.setattr(robo, "respostas_pendentes", lambda agora=None: True)
    aprovado = _rascunho("aprovado", postar_em="2026-10-25 03:00:00")
    _rascunho("recusado")
    assert robo.no_horario({**config, "robo_inicio": 8, "robo_fim": 22}, momento("2026-10-25 04:10"))
    assert robo.o_que_fazer(config, momento("2026-10-25 04:10")) == ("descurtir", None)
    assert "a limpeza dos favoritos vem primeiro" in robo.motivo_da_espera(
        {**config, "robo_pausado": False}, momento("2026-10-25 04:10"))
    robo.gravar_estado(descurtir_em="2026-10-25 04:10:00", descurtir_continuar=False)
    # Acabada a limpeza, o resto da hora fica livre: o treino, apagar e postar seguem.
    assert robo.o_que_fazer(config, momento("2026-10-25 04:40"))[0] in ("treino", "apagar")
    # A que parou no meio continua na frente de tudo.
    robo.gravar_estado(descurtir_continuar=True)
    assert robo.o_que_fazer(config, momento("2026-10-25 04:40")) == ("descurtir", None)
    robo.gravar_estado(descurtir_continuar=False)
    # Com o Horário do Robô sem as 4h, a rodada das 4h só vem pela limpeza.
    assert robo.o_que_fazer({**config, "robo_inicio": 8}, momento("2026-10-25 04:59")) is None
    assert aprovado


def test_plano_e_aprovados_podem_cair_na_hora_do_descurtir():
    class Sorteio:
        @staticmethod
        def randint(a, b):
            return a

    # O horário que cai às 4h espera a limpeza acabar (o_que_fazer): o plano e o aprovado não pulam a hora.
    config = {**robo.PADRAO, "robo_limite_min": 24, "robo_limite_max": 24, "robo_inicio": 0, "robo_fim": 24}
    horarios = robo.planejar(config, "2026-10-25")
    assert len(horarios) == 24 and any(h.startswith("04:") for h in horarios)
    assert robo.proxima_postagem(config, momento("2026-10-25 03:58"), sorteio=Sorteio) == "2026-10-25 04:03:00"


def test_conta_suspensa_as_4h_faz_a_limpeza_dos_favoritos_e_depois_le_a_saude(monkeypatch, avisos):
    # Pedido do Rafael (25/10): na suspensão, só o preparo, a postagem e o treino esperam; a
    # limpeza dos favoritos das 4h continua, como a 1ª coisa do dia, e depois dela a hora fica livre
    # para o resto (P161 1).
    ativar(robo_inicio=0, robo_fim=24, robo_suspenso_ate="2026-11-01 00:00:00")
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: True)
    app = AppDosFavoritos(favoritos=3)
    assert robo.rodada(d=app, agora=momento("2026-10-25 04:10")) == (
        "3 produto(s) descurtido(s) em Meus favoritos; nada em Meus Favoritos de comprador")
    assert robo.o_que_fazer(robo.ler_config(), momento("2026-10-25 04:25")) == ("saude", None)


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


def test_na_hora_do_descurtir_a_rodada_que_nao_chega_a_limpeza_fica_no_registro(monkeypatch, avisos):
    # A limpeza das 4h que não roda tem de dizer por quê: a rodada da hora que não chega a ela
    # (o explorar no celular, a tela aberta no privado) anota o porquê, como o robô pausado.
    ativar(robo_inicio=8, robo_fim=22)

    def sem_limpeza():
        return [(linha[0][11:16], linha[2]) for linha in robo.registro_processos.sequencia(
            "shopee_video", robo.PROCESSO_SEM_LIMPEZA, "2000-01-01 00:00:00")]
    with robo.celular_robo.trava() as livre:
        assert livre
        assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 04:00")) == "o explorar está tocando no celular"
        # Fora da hora do descurtir, nada.
        assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 10:00")) == "o explorar está tocando no celular"
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: True)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: pytest.fail("não devia olhar o celular"))
    assert "tela do celular está aberta" in robo.rodada(agora=momento("2026-10-22 04:15"))
    assert sem_limpeza() == [("04:00", "o celular com o explorar"), ("04:15", "a tela do celular aberta no privado")]
    # Com a limpeza de hoje feita, a rodada da hora não anota nada.
    robo.gravar_estado(descurtir_em="2026-10-22 04:20:00", descurtir_continuar=False)
    assert "tela do celular está aberta" in robo.rodada(agora=momento("2026-10-22 04:30"))
    assert len(sem_limpeza()) == 2


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


def _outro_produto(monkeypatch, item="3"):
    """O link da fonte passa a levar a outro produto: o que já tem rascunho não se repete (P166 1)."""
    async def converter(link):
        return f"https://shopee.com.br/product/1/{item}"

    monkeypatch.setattr(robo, "link_para_converter", converter)
    monkeypatch.setattr(robo.ps, "link_para_converter", converter)


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


def _tela(monkeypatch, acesa, energia=None, bloqueio=False, acende=None):
    """
    A tela do celular lida pelo adb (celular_robo), sem o celular de verdade: acesa ou apagada, a carga,
    a tela de bloqueio e o que a tecla de acender faz. Devolve as vezes em que o robô acendeu a tela.
    """
    acendeu = []
    monkeypatch.setattr(robo.celular_robo, "tela_acesa", lambda: acesa)
    monkeypatch.setattr(robo.celular_robo, "ler_energia", lambda: energia)
    monkeypatch.setattr(robo.celular_robo, "tela_de_bloqueio", lambda: bloqueio)
    monkeypatch.setattr(robo.celular_robo, "acender_tela", lambda: acendeu.append(1) or acende)
    return acendeu


FORA_DO_CARREGADOR = {"carregador": False, "bateria": 41, "manter_ativado": True}
NO_CARREGADOR = {"carregador": True, "bateria": 81, "manter_ativado": True}
CARGA_NO_CARREGADOR = "no carregador, bateria 81%, Manter ativado ligado"


def _avisos_da_tela(avisos):
    return [a for a in avisos if isinstance(a, str) and a.startswith(robo.CELULAR_DESLIGADO)]


def _registros_da_tela(monkeypatch):
    """O que o robô anota no registro sobre a tela (o registro de 3 dias apaga as linhas da data dos testes)."""
    anotados, registrar = [], robo.registro_processos.registrar

    def anotar(quem, processo, resultado, detalhe="", ok=None, **outros):
        if processo == robo.PROCESSO_DA_TELA:
            anotados.append((resultado, detalhe, ok))
        return registrar(quem, processo, resultado, detalhe, ok, **outros)

    monkeypatch.setattr(robo.registro_processos, "registrar", anotar)
    return anotados


def _alertas_anotados(monkeypatch):
    """Os alertas do celular no registro (P205 1), como (resultado, detalhe, ok)."""
    anotados, registrar = [], robo.registro_processos.registrar

    def anotar(quem, processo, resultado, detalhe="", ok=None, **outros):
        if processo == robo.PROCESSO_DO_ALERTA:
            anotados.append((resultado, detalhe, ok))
        return registrar(quem, processo, resultado, detalhe, ok, **outros)

    monkeypatch.setattr(robo.registro_processos, "registrar", anotar)
    return anotados


def test_tela_apagada_fora_do_carregador_para_antes_de_escolher_e_avisa_uma_vez(monkeypatch, avisos):
    # Em 11/11, das 06:44 às 08:14, seis rodadas escolheram o vídeo, perguntaram à IA e só no celular
    # apertaram voltar 15 vezes com a tela apagada (o Moto Display). Fora do carregador, o robô não acende
    # a tela (P203 1): a rodada para antes de escolher o que fazer, sem tocar no celular, e o Rafael recebe
    # um aviso só, com a bateria.
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    acendeu = _tela(monkeypatch, False, FORA_DO_CARREGADOR)
    monkeypatch.setattr(robo, "preparar_rascunho", lambda *a, **k: pytest.fail("com a tela apagada, nada de preparo"))
    motivo = "a tela do celular está apagada (fora do carregador, bateria 41%, Manter ativado ligado)"
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 23:59")) == motivo
    assert acendeu == []
    assert consultar("SELECT acao, resultado, passo, motivo FROM shopee_video_tentativas") == (
        "rodada", "parou", "tela do celular apagada", motivo)
    assert len(avisos) == 1 and avisos[0].startswith(robo.CELULAR_DESLIGADO) and "🔌" in avisos[0]
    assert "bateria 41%" in avisos[0] and "de hora em hora" in avisos[0] and "nada perde a vez" in avisos[0]
    # Nada gastou a vez: o horário do plano espera, e o vídeo da fonte continua o próximo.
    assert robo.estado_do_dia(robo.ler_config(), momento("2026-10-22 23:59"))["feitos"] == 0
    assert robo.proximo_video(robo.ler_config())["id"] == "a1"
    # A rodada seguinte, ainda apagada: sem outro aviso e sem outra linha no histórico.
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 23:59")) == motivo
    assert len(avisos) == 1 and consultar("SELECT COUNT(*) FROM shopee_video_tentativas") == (1,)
    assert robo.passo_do_motivo(robo.TELA_APAGADA) == "tela do celular apagada"


def test_tela_apagada_sem_a_carga_lida_nao_acende(monkeypatch, avisos):
    ativar(robo_inicio=0, robo_fim=24)
    acendeu = _tela(monkeypatch, False)
    with pytest.raises(robo.TelaSemUso) as parada:
        robo.conferir_a_tela()
    assert parada.value.motivo == f"{robo.TELA_APAGADA} (carga não lida)" and acendeu == []
    # Com a tela acesa e livre, ou sem a leitura dela (o adb sem resposta), nada muda.
    for acesa, bloqueio in ((True, False), (None, True), (True, None)):
        _tela(monkeypatch, acesa, bloqueio=bloqueio)
        robo.conferir_a_tela()


def test_tela_apagada_no_carregador_o_robo_acende_e_segue(monkeypatch, avisos):
    # P203 1: no carregador, o robô acende a tela como o botão de ligar, sem desbloquear nada, e segue.
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    acendeu = _tela(monkeypatch, False, NO_CARREGADOR, acende=True)
    registros = _registros_da_tela(monkeypatch)
    assert robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert acendeu == [1] and _avisos_da_tela(avisos) == []
    assert registros == [("acesa pelo robô", CARGA_NO_CARREGADOR, True)]


def test_tela_que_nao_acende_ou_acende_na_tela_de_bloqueio_para_e_avisa_cada_problema(monkeypatch, avisos):
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    _tela(monkeypatch, False, NO_CARREGADOR, acende=False)
    motivo = f"{robo.TELA_NAO_ACENDEU} quando o robô tentou ({CARGA_NO_CARREGADOR})"
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 23:59")) == motivo
    assert robo.passo_do_motivo(motivo) == "tela do celular apagada"
    assert len(_avisos_da_tela(avisos)) == 1 and "Aperte o botão de ligar" in avisos[-1]
    # Acesa pelo robô, na tela de bloqueio: outro problema, outro aviso; o robô não desbloqueia.
    _tela(monkeypatch, False, NO_CARREGADOR, bloqueio=True, acende=True)
    motivo = f"{robo.TELA_DE_BLOQUEIO} (o robô não desbloqueia o celular; {CARGA_NO_CARREGADOR})"
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 23:59")) == motivo
    assert len(_avisos_da_tela(avisos)) == 2 and "🔒" in avisos[-1] and "Desbloqueie" in avisos[-1]
    assert consultar("SELECT COUNT(*) FROM shopee_video_tentativas") == (2,)


def test_tela_de_bloqueio_na_frente_para_a_rodada_e_avisa_uma_vez_ate_sair(monkeypatch, avisos):
    # Das 08:27 às 09:33 de 11/11, a tela estava acesa no cadeado, com a Shopee por trás, e cada rodada
    # apertava voltar em vão. O robô não desbloqueia o celular (P203 1): para antes de escolher o que fazer
    # e avisa uma vez; desbloqueado, segue, e a próxima vez avisa de novo.
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    acendeu = _tela(monkeypatch, True, NO_CARREGADOR, bloqueio=True)
    motivo = f"{robo.TELA_DE_BLOQUEIO} (o robô não desbloqueia o celular; {CARGA_NO_CARREGADOR})"
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 23:59")) == motivo
    assert acendeu == [] and len(avisos) == 1 and avisos[0].startswith(robo.CELULAR_DESLIGADO) and "🔒" in avisos[0]
    assert consultar("SELECT acao, passo FROM shopee_video_tentativas") == ("rodada", "tela de bloqueio")
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 23:59")) == motivo
    assert len(avisos) == 1
    # Desbloqueado (a leitura do adb sem dizer nada da tela de bloqueio): o rascunho sai, e o fim da
    # rodada no app diz que a tela voltou.
    _tela(monkeypatch, True, NO_CARREGADOR, bloqueio=None)
    registros = _registros_da_tela(monkeypatch)
    assert robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert robo.ler_estado()["tela_avisada"] == "" and registros == [("de volta depois do aviso", "", True)]
    assert avisos[-1].startswith(robo.CELULAR_DE_VOLTA) and "continua sozinho" in avisos[-1]
    # Na próxima vez, o aviso vem de novo.
    _tela(monkeypatch, True, NO_CARREGADOR, bloqueio=True)
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 23:59")) == motivo
    assert len(_avisos_da_tela(avisos)) == 2


def test_celular_desligado_alerta_de_hora_em_hora_apagando_o_de_antes(monkeypatch, avisos, apagados):
    # P205 1 (11/11): enquanto a tela não deixa o robô usar o celular, o 🚨 CELULAR DESLIGADO volta de
    # hora em hora, e o alerta de antes sai do privado; no fim, o ✅ CELULAR DE VOLTA.
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    _tela(monkeypatch, True, NO_CARREGADOR, bloqueio=True)
    anotados = _alertas_anotados(monkeypatch)
    motivo = f"{robo.TELA_DE_BLOQUEIO} (o robô não desbloqueia o celular; {CARGA_NO_CARREGADOR})"
    for hora in ("10:00", "10:15", "10:45"):
        assert robo.rodada(d=Intocavel(), agora=momento(f"2026-10-22 {hora}")) == motivo
    assert len(_avisos_da_tela(avisos)) == 1 and apagados == []
    # Uma hora depois do 1º: o alerta de novo, e o de antes (o id 1) sai do privado.
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 11:00")) == motivo
    assert len(_avisos_da_tela(avisos)) == 2 and apagados == [1]
    assert robo.ler_estado()["tela_avisada_id"] == 2 and robo.ler_estado()["tela_avisada_em"] == "2026-10-22 11:00:00"
    # O histórico continua com a 1ª parada só.
    assert consultar("SELECT COUNT(*) FROM shopee_video_tentativas") == (1,)
    # O alerta que não chega não apaga o de antes e tenta de novo na rodada seguinte.
    monkeypatch.setattr(robo.avisar_rafael, "mandar_texto_com_id", lambda texto, html=False, teclado=None: None)
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 12:00")) == motivo
    assert apagados == [1] and robo.ler_estado()["tela_avisada_em"] == "2026-10-22 11:00:00"
    monkeypatch.setattr(robo.avisar_rafael, "mandar_texto_com_id",
                        lambda texto, html=False, teclado=None: avisos.append(texto) or 9)
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 12:15")) == motivo
    assert apagados == [1, 2] and robo.ler_estado()["tela_avisada_id"] == 9
    # Desbloqueado: o ✅ CELULAR DE VOLTA, e os alertas param.
    _tela(monkeypatch, True, NO_CARREGADOR, bloqueio=False)
    assert robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 13:30")) == "rascunho salvo"
    assert [a for a in avisos if a.startswith(robo.CELULAR_DE_VOLTA)] and robo.ler_estado()["tela_avisada_id"] is None
    # Cada alerta no registro: o checkup confere o de hora em hora, mostra o que não chegou e aponta o
    # alerta de antes que ficou no privado.
    saiu = robo.O_DE_ANTES_SAIU
    assert anotados == [("celular desligado: 1º alerta", "", True), ("celular desligado: de novo", saiu, True),
                        ("celular desligado: não chegou", "", False), ("celular desligado: de novo", saiu, True),
                        ("celular de volta: a tela", "", True)]


def test_celular_desligado_na_suspensao_alerta_uma_vez_so(monkeypatch, avisos, apagados):
    # Na suspensão da conta, como antes da P205: o alerta da tela vem uma vez por problema.
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    ativar(robo_inicio=0, robo_fim=24, robo_suspenso_ate="2026-10-28 14:41:00")
    _tela(monkeypatch, True, NO_CARREGADOR, bloqueio=True)
    for hora in ("10:00", "11:00", "12:30"):
        robo.rodada(d=Intocavel(), agora=momento(f"2026-10-26 {hora}"))
    assert len(_avisos_da_tela(avisos)) == 1 and apagados == []
    assert robo.UMA_VEZ_NA_SUSPENSAO in avisos[0] and "de hora em hora" not in avisos[0]


def test_celular_desconectado_alerta_de_hora_em_hora_ate_voltar(monkeypatch, avisos, apagados):
    # P205 1: sem o celular, a Postagem pausa e o 🚨 CELULAR DESCONECTADO vem na hora; o painel confere a
    # cada 15 min e, de hora em hora, manda de novo, apagando o de antes. Com o celular de volta, o ✅
    # CELULAR DE VOLTA, e a Postagem continua esperando o Retomar Postagem ▶️, como sempre.
    ativar(robo_inicio=0, robo_fim=24)
    anotados = _alertas_anotados(monkeypatch)
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: False)
    no_ar = {"celular": False}
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: no_ar["celular"])
    monkeypatch.setattr(robo.celular_robo, "reconectar_sozinho", lambda: (False, "a Depuração por Wi-Fi está desligada"))
    assert "desconectado" in robo.rodada(agora=momento("2026-10-22 10:00"))
    assert len(avisos) == 1 and avisos[0].startswith(robo.CELULAR_DESCONECTADO)
    assert "Retomar Postagem ▶️" in avisos[0] and "de hora em hora" in avisos[0]
    assert robo.lembrar_celular_desconectado(momento("2026-10-22 10:15")) is None
    assert robo.lembrar_celular_desconectado(momento("2026-10-22 10:45")) is None and len(avisos) == 1
    assert robo.lembrar_celular_desconectado(momento("2026-10-22 11:00")) == "alertado de novo"
    assert len(avisos) == 2 and avisos[1].startswith(robo.CELULAR_DESCONECTADO) and apagados == [1]
    assert "a Depuração por Wi-Fi está desligada" in avisos[1]
    # O Reconectar Celular 🔄 (ou a rede de volta): na conferência seguinte, o ✅, e os alertas param.
    no_ar["celular"] = True
    assert robo.lembrar_celular_desconectado(momento("2026-10-22 11:15")) == "de volta"
    assert avisos[-1].startswith(robo.CELULAR_DE_VOLTA) and "Retomar Postagem ▶️" in avisos[-1]
    assert robo.ler_config()["robo_pausado"] is True
    assert robo.lembrar_celular_desconectado(momento("2026-10-22 13:00")) is None and len(avisos) == 3
    # Durante o pareamento pelo QR, nada de mexer no adb.
    robo.pausar_por_desconexao("caiu de novo", momento("2026-10-22 14:00"))
    monkeypatch.setattr(robo.celular_robo, "pareando_agora", lambda: True)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: pytest.fail("o pareamento está correndo"))
    assert robo.lembrar_celular_desconectado(momento("2026-10-22 14:30")) is None
    # O Retomar Postagem ▶️ acaba com os alertas (o painel diz o CELULAR DE VOLTA).
    assert robo.fim_do_alerta_desconectado() is True and robo.fim_do_alerta_desconectado() is False
    assert anotados == [("celular desconectado: 1º alerta", "", True),
                        ("celular desconectado: de novo", robo.O_DE_ANTES_SAIU, True),
                        ("celular de volta: o servidor achou o celular", "", True),
                        ("celular desconectado: 1º alerta", "", True), ("celular de volta: o Retomar Postagem", "", True)]


def test_alerta_do_celular_anota_quando_o_de_antes_fica_no_privado(monkeypatch, avisos):
    # P205 1: o registro de cada alerta diz se o de antes saiu do privado, e o checkup aponta o que ficou:
    # o Telegram recusa apagar (só deixa até 48 h), ou o de antes foi sem o id.
    ativar(robo_inicio=0, robo_fim=24, robo_pausado=True, robo_pausa_motivo=robo.MOTIVO_DA_DESCONEXAO)
    anotados = _alertas_anotados(monkeypatch)
    monkeypatch.setattr(robo.celular_robo, "pareando_agora", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: False)
    monkeypatch.setattr(robo.avisar_rafael, "apagar_mensagem", lambda ident: False)
    for anterior in (7, True):
        robo.gravar_estado(alerta_desconectado={"motivo": "x", "em": "2026-10-22 09:00:00", "id": anterior})
        assert robo.lembrar_celular_desconectado(momento("2026-10-22 10:00")) == "alertado de novo"
    assert anotados == [("celular desconectado: de novo", robo.O_DE_ANTES_FICOU, True)] * 2


def test_celular_desconectado_sem_pausa_ou_na_suspensao_nao_alerta_de_novo(monkeypatch, avisos, apagados):
    ativar(robo_inicio=0, robo_fim=24)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: pytest.fail("sem o alerta, nem olha o celular"))
    assert robo.lembrar_celular_desconectado(momento("2026-10-22 11:00")) is None
    robo.gravar_estado(alerta_desconectado={"motivo": "x", "em": "2026-10-22 09:00:00", "id": 1})
    assert robo.lembrar_celular_desconectado(momento("2026-10-22 11:00")) is None      # a Postagem não está pausada
    ativar(robo_inicio=0, robo_fim=24, robo_pausado=True, robo_pausa_motivo=robo.MOTIVO_DA_DESCONEXAO,
           robo_suspenso_ate="2026-10-28 14:41:00")
    assert robo.lembrar_celular_desconectado(momento("2026-10-26 11:00")) is None      # na suspensão
    assert avisos == [] and apagados == []


def test_tela_sem_uso_responde_os_pedidos_do_rafael_e_o_aprovado_nao_perde_a_vez(monkeypatch, avisos):
    ident = _aprovado(monkeypatch)
    _tela(monkeypatch, False, FORA_DO_CARREGADOR)
    motivo = "a tela do celular está apagada (fora do carregador, bateria 41%, Manter ativado ligado)"
    agora = momento("2026-10-22 23:59")
    antes = robo.pegar(ident)
    # O aprovado que passou da hora não é tentado: não conta uma tentativa de postar.
    assert robo.rodada(d=Intocavel(), agora=agora) == motivo
    assert robo.pegar(ident)["estado"] == "aprovado"
    assert robo.pegar(ident)["falhas_ao_postar"] == antes["falhas_ao_postar"]
    assert len(avisos) == 1
    # Postar Agora 🚀, Preparar 1 Agora ⚡, Gerar Apelação ⚖️ e Testar Caminho 🧭: cada um ganha a resposta.
    assert robo.rodada(d=Intocavel(), postar=ident, agora=agora) == motivo
    assert "não postei agora o rascunho que você pediu" in avisos[-1] and motivo in avisos[-1]
    assert robo.pegar(ident)["estado"] == "aprovado"
    assert robo.rodada(d=Intocavel(), preparar=True, agora=agora) == motivo
    assert "não preparei o rascunho que você pediu" in avisos[-1]
    robo.rodada(d=Intocavel(), saude=True, agora=agora)
    assert "não consegui ler a Saúde do Vídeo" in avisos[-1] and "Gerar Apelação ⚖️" in avisos[-1]
    robo.rodada(d=Intocavel(), treino=True, agora=agora)
    assert "não comecei" in avisos[-1] and "Testar Caminho 🧭" in avisos[-1]
    # O pedido do Fazer Agora ⏩ sai da lista com o aviso (sem isso, voltaria a cada rodada).
    assert robo.pedir_agora("saude", agora)[0]
    robo.rodada(d=Intocavel(), fazer=True, agora=agora)
    assert "não fiz o que você pediu no Fazer Agora" in avisos[-1] and robo.pedidos_de_agora(agora) == []
    # O aviso da tela continua um só; cada pedido fica no histórico.
    assert len(_avisos_da_tela(avisos)) == 1
    assert consultar("SELECT COUNT(*) FROM shopee_video_tentativas") == (6,)


BLOQUEIO_NA_LEITURA = (
    '<hierarchy><node package="com.android.systemui" resource-id="com.android.systemui:id/notification_panel">'
    '<node package="com.android.systemui" resource-id="com.android.systemui:id/notification_stack_scroller"/>'
    '<node package="com.android.systemui" resource-id="com.android.systemui:id/keyguard_status_view"/>'
    '<node package="com.android.systemui" resource-id="com.android.systemui:id/keyguard_bottom_area"/>'
    '</node></hierarchy>')


def test_tela_de_bloqueio_na_leitura_para_na_hora_sem_apertar_voltar(monkeypatch, avisos):
    # A tela de bloqueio traz as peças do painel do Android, e o voltar não a fecha: às 09:18 e às 09:33 de
    # 11/11, o robô apertou voltar 15 vezes em vão. Achada na leitura, o robô para na hora e avisa uma vez.
    _tela(monkeypatch, True, NO_CARREGADOR)

    class Bloqueado:
        def __init__(self):
            self.apertos = []

        def dump_hierarchy(self):
            return BLOQUEIO_NA_LEITURA

        def press(self, tecla):
            self.apertos.append(tecla)

    d = Bloqueado()
    assert robo.tela_de_bloqueio_na_leitura(BLOQUEIO_NA_LEITURA)
    with pytest.raises(robo.Parada) as parada:
        robo.tela(d, seguir=True)
    assert parada.value.motivo.startswith(robo.TELA_DE_BLOQUEIO) and d.apertos == []
    assert robo.passo_do_motivo(parada.value.motivo) == "tela de bloqueio"
    assert len(avisos) == 1 and avisos[0].startswith(robo.CELULAR_DESLIGADO) and "🔒" in avisos[0]
    with pytest.raises(robo.Parada):
        robo.voltar(d, "Eu")
    assert len(avisos) == 1 and d.apertos == []
    # O painel do Android sem a tela de bloqueio, e a Shopee na frente, não são ela.
    painel = BLOQUEIO_NA_LEITURA.replace("keyguard_status_view", "qs_frame").replace("keyguard_bottom_area",
                                                                                     "quick_settings_panel")
    assert not robo.tela_de_bloqueio_na_leitura(painel) and robo.painel_do_android_aberto(painel)
    com_a_shopee = BLOQUEIO_NA_LEITURA.replace("<hierarchy>", f'<hierarchy><node package="{robo.ps.PACOTE}"/>')
    assert not robo.tela_de_bloqueio_na_leitura(com_a_shopee)


# --- O Giro na edição (pedido do Rafael, vídeo de 31/10), sem o Realçar (P177 2) ---

class ComAvisos(AppDeMentira):
    """O app avisa num toast o que o toque no Realçar faria; o Giro pode só baixar no 1º toque."""

    def __init__(self, realce_ligado=False, giro_baixa_antes=0):
        super().__init__()
        self.atual, self.realce, self.toast, self.baixar = "edicao", realce_ligado, None, giro_baixa_antes

    def clear_toast(self):
        self.toast = None

    @property
    def last_toast(self):
        # Como no uiautomator2: uma propriedade, não uma função.
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


def test_edicao_poe_o_giro_e_nao_toca_no_realcar():
    # Escolha do Rafael (07/11, P177 2): o Realçar mudava a luz de cada quadro, e a faixa da capa
    # da grade saía num laranja mais escuro na grade que no vídeo aberto. Ele fica desligado, como
    # toda edição nova começa, e o Giro continua.
    app = ComAvisos()
    assert robo.efeitos_na_edicao(app) == robo.EFEITOS_COMPLETOS == "giro"
    assert app.toques == ["Efeitos", "Giro", "@iv_done"] and not app.realce and app.atual == "edicao"
    registro = robo.registro_processos.sequencia("shopee_video", "efeitos na edição", "2000-01-01 00:00:00")
    assert [r[2] for r in registro] == ["giro"] and registro[0][3] == "giro: posto"


def test_giro_que_so_baixa_no_primeiro_toque():
    app = ComAvisos(giro_baixa_antes=1)
    assert robo.efeitos_na_edicao(app) == robo.EFEITOS_COMPLETOS
    # O 1º Giro só baixou o efeito; o 2º o pôs.
    assert app.toques == ["Efeitos", "Giro", "Giro", "@iv_done"] and "Realçar" not in app.toques


def test_efeito_que_nao_fica_nao_derruba_o_rascunho():
    app = ComAvisos(giro_baixa_antes=robo.VEZES_DO_GIRO)
    assert robo.efeitos_na_edicao(app) == "nenhum"
    # Sem o Desfazer, sai dos Efeitos pelo ✕, sem mudar nada, e a edição segue para o Próximo.
    assert app.toques[-1] == "@iv_close" and app.toques.count("Giro") == robo.VEZES_DO_GIRO and app.atual == "edicao"
    registro = robo.registro_processos.sequencia("shopee_video", "efeitos na edição", "2000-01-01 00:00:00")
    assert registro[-1][2] == "nenhum" and "não ficou depois de 3 toques" in registro[-1][3]


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
    assert "Realçar" not in app.toques and app.toques.index("Giro") < app.toques.index("@tv_compress")
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

    async def buscar(termo, limite=10, sort_type=2, negada_levanta=False):
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


def test_produto_do_video_achado_pela_busca_da_ia_do_que_paga_mais(monkeypatch):
    # Escolha do Rafael (06/11, P158 2): o produto do link não é o do vídeo; a IA diz o que o vídeo
    # mostra, a API busca por relevância, e os primeiros, sem o do link, do que paga mais por venda
    # para o que paga menos, passam pela mesma conferência dupla com a foto do anúncio.
    ofertas = [_oferta("Colar Trevo do Link", 0.30, 1),                          # o do link: a IA já recusou
               _oferta("Colar Trevo Corações Magnético", 0.05, 2),
               _oferta("Colar Trevo Corações Zircônia", 0.12, 3),
               _oferta("Colar Sem Preço", 0.40, 4, preco=0)]                     # sem preço: fica de fora
    pedidos = _busca_de_comissao(monkeypatch, ofertas, confirma=("https://s.shopee.com.br/2",))
    monkeypatch.setattr(robo.ps, "ia_diz_o_produto_do_video", lambda video: "colar trevo corações")
    monkeypatch.setattr(robo, "item_do_link", lambda link: "1")
    achado = ACHAR({"link": LINK, "arquivo": "video.mp4"})
    assert pedidos["busca"] == [("colar trevo corações", robo.OFERTAS_NA_BUSCA, 1)]
    # O que paga mais primeiro (a IA recusou), depois o confirmado; a conferência é a do produto do
    # link, sem a capa da troca de loja.
    assert pedidos["ia"] == ["https://s.shopee.com.br/3", "https://s.shopee.com.br/2"]
    assert pedidos["capa"] == [None, None]
    assert achado["link"] == "https://s.shopee.com.br/2" and achado["comissao"] == 5.0
    assert achado["vistos"] == ["é o mesmo pacote"]
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DO_PRODUTO_ACHADO, "2000-01-01 00:00:00")
    assert [r[2] for r in registro] == ["achado"]


def test_produto_do_video_que_a_ia_nao_confirma_deixa_o_video_de_lado(monkeypatch):
    # Até ACHADOS_NA_IA anúncios vão à IA; sem confirmação, None (o vídeo fica de lado, como antes).
    ofertas = [_oferta(f"Colar Trevo {n}", 0.05 + n / 100, 10 + n) for n in range(6)]
    pedidos = _busca_de_comissao(monkeypatch, ofertas)
    monkeypatch.setattr(robo.ps, "ia_diz_o_produto_do_video", lambda video: "colar trevo")
    monkeypatch.setattr(robo, "item_do_link", lambda link: "")
    assert ACHAR({"link": LINK, "arquivo": "video.mp4"}) is None
    assert len(pedidos["ia"]) == robo.ACHADOS_NA_IA
    # A IA que não diz o produto: nem busca.
    pedidos["busca"].clear()
    monkeypatch.setattr(robo.ps, "ia_diz_o_produto_do_video", lambda video: "")
    assert ACHAR({"link": LINK, "arquivo": "video.mp4"}) is None and pedidos["busca"] == []
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DO_PRODUTO_ACHADO, "2000-01-01 00:00:00")
    assert [r[2] for r in registro] == ["não achado - a IA não confirmou nenhum", "não achado - a IA não disse o produto"]


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


def _troca_do_ver_produtos(monkeypatch, ofertas_pelo_nome, busca, confirma=(), curte=True):
    """
    A API (a oferta de cada produto do criador pelo nome e a busca por maior comissão), o link
    curto, a IA e o celular de mentira da troca do Ver Produtos; devolve o que foi pedido.
    """
    pedidos = {"busca": [], "ia": [], "abertos": []}

    def oferta_parecida(nome):
        oferta = ofertas_pelo_nome.get(nome)
        return (100, True, oferta) if oferta else (0, False, {})

    async def buscar(termo, limite=10, sort_type=2, negada_levanta=False):
        pedidos["busca"].append((termo, sort_type))
        return busca.get(termo, [])

    async def encurtar(link, etiqueta, avisar_falha=True):
        return "https://s.shopee.com.br/" + link.rsplit("/", 1)[-1]

    def conferir(video, vistos=None, avisar=True, capa=None):
        pedidos["ia"].append((video["link"], capa))
        if vistos is not None:
            vistos.append("a IA viu o mesmo produto")
        return video["link"] in confirma, ""

    monkeypatch.setattr(robo, "_oferta_parecida", oferta_parecida)
    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", buscar)
    monkeypatch.setattr(robo.api_shopee, "converter_link_shopee", encurtar)
    monkeypatch.setattr(robo.ps, "ia_confere_produto", conferir)
    monkeypatch.setattr(robo, "ir_ao_inicio", lambda d: None)
    monkeypatch.setattr(robo.ps, "limpar_aviso_rapido", lambda d: None)
    monkeypatch.setattr(robo.ps, "abrir_link", lambda d, link: pedidos["abertos"].append(link))
    monkeypatch.setattr(robo, "_esperar_a_pagina_do_produto", lambda d, voltas=4, a_mais=False: True)
    monkeypatch.setattr(robo.ps, "curtir", lambda d, video: (curte, "curtido"))
    return pedidos


def test_ver_produtos_troca_cada_produto_pelo_da_loja_que_paga_mais_e_ordena_pelo_valor(monkeypatch):
    # Escolhas do Rafael (28/10, P57 e P58; 05/11, P154 3): cada produto do Ver Produtos ganha a
    # busca da troca do link de produto (o mesmo item, que paga mais por venda, até 20% mais caro,
    # conferido pela IA com a foto da página do produto do criador), e o post vai do que paga mais
    # por venda para o que paga menos: o 1º dá a foto da edição.
    termo_a, termo_b = robo.termo_da_busca(PRODUTO_A), robo.termo_da_busca(PRODUTO_B)
    pelo_nome = {PRODUTO_A: _oferta(PRODUTO_A, 0.05, 1, preco=50.0),       # R$ 2,50 por venda
                 PRODUTO_B: _oferta(PRODUTO_B, 0.08, 2, preco=100.0)}      # R$ 8,00; o C sem oferta
    busca = {termo_a: [_oferta(PRODUTO_A + " Envio Rápido", 0.10, 3, preco=55.0),   # R$ 5,50: troca
                       _oferta(PRODUTO_A + " Atacado", 0.20, 4, preco=90.0)],       # 80% mais caro: não
             termo_b: [_oferta(PRODUTO_B + " Kit", 0.05, 5, preco=100.0)]}          # paga menos: não
    pedidos = _troca_do_ver_produtos(monkeypatch, pelo_nome, busca, confirma=("https://s.shopee.com.br/3",))
    fotos = {PRODUTO_A: b"\xff\xd8pagina A", PRODUTO_B: b"\xff\xd8pagina B", PRODUTO_C: b"\xff\xd8pagina C"}
    vistos, curtidos = [], []
    produtos = TROCAR_OS_DO_VER_PRODUTOS(None, {"link": LINK_DE_VIDEO, "arquivo": "video.mp4", "de_video": True},
                                         [PRODUTO_A, PRODUTO_B, PRODUTO_C], fotos, vistos, curtidos,
                                         time.monotonic() + 600)
    assert [(p["nome"], p["link"], p["trocado"]) for p in produtos] == [
        (PRODUTO_B, "", ""), (PRODUTO_A + " Envio Rápido", "https://s.shopee.com.br/3", PRODUTO_A),
        (PRODUTO_C, "", "")]
    assert produtos[1]["valor"] == pytest.approx(5.5) and produtos[1]["valor_antes"] == pytest.approx(2.5)
    # A IA viu o anúncio da outra loja com a foto da página do produto do criador.
    assert pedidos["ia"] == [("https://s.shopee.com.br/3", b"\xff\xd8pagina A")]
    # O da outra loja é curtido pelo link dele, e o descurtir do fim o acha pelo link.
    assert pedidos["abertos"] == ["https://s.shopee.com.br/3"]
    assert curtidos == [("https://s.shopee.com.br/3", PRODUTO_A + " Envio Rápido")]
    assert vistos == ["a IA viu o mesmo produto"]
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_TROCA_DO_VER_PRODUTOS,
                                                 "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in registro] == [("trocado", "mais 120% por venda"),
                                                ("mantido - nenhum que pague mais por venda", ""),
                                                ("mantido - a API não achou o produto pelo nome", "")]


def test_ver_produtos_sem_tempo_ou_sem_curtir_fica_o_do_criador(monkeypatch):
    # A troca é um ganho a mais: passado o prazo do rascunho, ou sem curtir o da outra loja, fica o
    # produto do criador (já curtido pela lista); a ordem pelo valor continua.
    termo_a = robo.termo_da_busca(PRODUTO_A)
    pelo_nome = {PRODUTO_A: _oferta(PRODUTO_A, 0.05, 1, preco=50.0), PRODUTO_B: _oferta(PRODUTO_B, 0.08, 2, preco=100.0)}
    busca = {termo_a: [_oferta(PRODUTO_A + " Envio Rápido", 0.10, 3, preco=55.0)]}
    video, fotos = {"link": LINK_DE_VIDEO, "arquivo": "video.mp4", "de_video": True}, {PRODUTO_A: b"\xff\xd8a"}
    pedidos = _troca_do_ver_produtos(monkeypatch, pelo_nome, busca, confirma=("https://s.shopee.com.br/3",))
    produtos = TROCAR_OS_DO_VER_PRODUTOS(None, video, [PRODUTO_A, PRODUTO_B], fotos, [], [], time.monotonic() - 1)
    assert [p["nome"] for p in produtos] == [PRODUTO_B, PRODUTO_A] and pedidos["busca"] == []
    pedidos = _troca_do_ver_produtos(monkeypatch, pelo_nome, busca, confirma=("https://s.shopee.com.br/3",),
                                     curte=False)
    curtidos = []
    produtos = TROCAR_OS_DO_VER_PRODUTOS(None, video, [PRODUTO_A], fotos, [], curtidos, time.monotonic() + 600)
    assert [p["nome"] for p in produtos] == [PRODUTO_A] and curtidos == []
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_TROCA_DO_VER_PRODUTOS,
                                                 "2000-01-01 00:00:00")
    assert [r[2] for r in registro] == ["mantido - sem tempo na rodada", "mantido - sem tempo na rodada",
                                        "mantido - o da outra loja não curtiu"]


def test_ver_produtos_com_o_produto_trocado_leva_o_link_e_a_foto_da_troca(monkeypatch, avisos):
    # O trocado vai no rascunho com o link curto dele (P83, sem a busca pelo nome), a foto da edição
    # vem do anúncio dele quando ele é o 1º, e o do criador que saiu continua curtido no alto de
    # Minhas Curtidas até o fim: o anexar procura os outros abaixo dele.
    _fonte_de_video(monkeypatch)
    trocado, link = PRODUTO_B + " Loja Dois", "https://s.shopee.com.br/troca"

    def trocar(d, video, nomes, fotos, vistos, curtidos, prazo, de_outra_cor=()):
        assert nomes == [PRODUTO_A, PRODUTO_B] and set(fotos) == {PRODUTO_A, PRODUTO_B}
        curtidos.append((link, trocado))
        return [{"nome": trocado, "link": link, "valor": 9.0, "trocado": PRODUTO_B, "comissao": 12.0, "antes": 8.0,
                 "valor_antes": 4.0, "do_video": True}, {"nome": PRODUTO_A, "link": "", "valor": 2.0, "trocado": "",
                                                         "do_video": True}]

    edicao, anexar = {}, {}

    def copiar(video, fonte, copia, nomes=(), alcool=False, outras=(), miniatura=None, rotulo_de_ia=False,
               link_do_1o=None, **_opcoes):
        edicao.update(nomes=list(nomes), link_do_1o=link_do_1o)
        robo.shutil.copyfile(video["arquivo"], copia)
        return ""

    def anexar_os(d, video, nomes, a_mais=(), limpa=False, prazo=None, curtidos_de_fora=0):
        anexar.update(nomes=list(nomes), de_fora=curtidos_de_fora)
        return list(nomes), list(range(len(nomes)))

    monkeypatch.setattr(robo, "trocar_os_do_ver_produtos", trocar)
    monkeypatch.setattr(robo, "copiar_para_o_rascunho", copiar)
    monkeypatch.setattr(robo, "anexar_os_produtos", anexar_os)
    monkeypatch.setattr(robo.ps, "conferir_tela_final", lambda d, video: (True, "conferida"))
    assert robo.rodada(preparar=True, d=AppDoVerProdutos(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert edicao == {"nomes": [trocado, PRODUTO_A], "link_do_1o": link}
    assert anexar == {"nomes": [trocado, PRODUTO_A], "de_fora": 1}
    rascunho = robo.pegar(1)
    assert rascunho["links_dos_produtos"] == [link, "https://s.shopee.com.br/curto-11"]
    assert rascunho["trocado"] == "1"
    assert any("troquei 1 de 2 produto(s) do Ver Produtos" in a and "12.0%" in a for a in avisos if isinstance(a, str))
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DOS_LINKS_DO_VER_PRODUTOS,
                                                 "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in registro] == [("todos achados",
                                                 "1 com o nome igual, 0 com o nome parecido, 0 sem, 1 da troca de loja")]


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
    async def quebrada(termo, limite=10, sort_type=2, negada_levanta=False):
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
    # A troca fica anotada no rascunho, para a medição de quais posts levam punição (P146 2).
    assert robo.pegar(rascunho["id"])["trocado"] == "1"


def test_video_de_produto_ja_postado_fica_de_lado_e_o_proximo_vira_rascunho(monkeypatch, avisos):
    # Escolha do Rafael (06/11, P166 1): o mesmo produto não se repete. O vídeo do produto que o robô
    # (ou o assistente, com Postei) já postou fica de lado antes do rascunho, sem gastar a IA nem o
    # celular, e o próximo da fonte vira rascunho.
    _fonte(monkeypatch)
    with open("archive/copo.mp4", "wb") as f:
        f.write(b"video")
    inserir("INSERT INTO fila_autorais VALUES (?, ?, ?, ?)", "b2", "archive/copo.mp4",
            "Copo 🥤\nhttps://s.shopee.com.br/repetido", "2026-10-22 10:00:00")

    async def produtos_do_link(link):
        return [{"nome": VESTIDO, "preco": 59.9, "comissao": 10.0, "item": "555" if "repetido" in link else "2"}], link

    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)
    _rascunho("postado", itens=[{"item": "555", "a_mais": False}])
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True, "fonte": "autorais"})
    assert robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["id_video"] == "a1"
    pulado = robo.listar("pulado")[0]
    assert pulado["id_video"] == "b2" and pulado["motivo"] == robo.PRODUTO_JA_POSTADO
    assert robo.passo_do_motivo(robo.PRODUTO_JA_POSTADO) == "produto já postado"
    assert not any("Copo" in str(a) for a in avisos)                 # o robô nem começou o do copo
    # O rascunho novo guarda o produto do vídeo: outro vídeo dele também fica de lado.
    assert rascunho["itens_do_video"] == ["2"] and "2" in robo.produtos_ja_postados()
    # O registro diz onde estava o produto do vídeo de lado, para o checkup conferir.
    assert consultar("SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DO_JA_POSTADO) == (robo.ONDE_JA_FOI["postado"], "robô", None)


def test_produto_da_troca_ja_postado_deixa_o_video_de_lado(monkeypatch, avisos):
    # O produto que vai ao post (o da loja que paga mais, P33, ou o achado pela IA, P158 2) também
    # não pode já ter ido ao ar: o produto do link era outro, mas o da troca já foi postado.
    _fonte(monkeypatch)
    monkeypatch.setattr(robo, "trocar_pela_maior_comissao",
                        lambda video: {"nome": VESTIDO, "link": "https://s.shopee.com.br/mais", "comissao": 15.0,
                                       "preco": 59.9, "valor": 8.99, "antes": 10.0, "valor_antes": 5.99,
                                       "vistos": ["mesmo vestido"]})
    monkeypatch.setattr(robo, "item_do_link", lambda link: "77" if "mais" in link else "2")
    _rascunho("aprovado", itens=[{"item": "77", "a_mais": False}])
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59"))
    assert [r["motivo"] for r in robo.listar("pulado")] == [robo.PRODUTO_JA_POSTADO]
    assert len(robo.listar("rascunho")) == 0
    assert consultar("SELECT resultado, detalhe FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DO_JA_POSTADO) == (robo.ONDE_JA_FOI["aprovado"], "robô")


def test_produtos_ja_postados_pelo_robo_e_pelo_assistente():
    # Contam os rascunhos esperando, aprovados e postados (o produto do vídeo, nunca os a mais) e os
    # vídeos do assistente marcados com Postei ✅.
    _rascunho("rascunho", itens_do_video=["10", "11"])
    _rascunho("aprovado", itens=[{"item": "20", "a_mais": False}, {"item": "21", "a_mais": True}])
    _rascunho("postado", itens=[{"item": "30", "a_mais": False}], itens_do_video=["31"])
    _rascunho("recusado", itens_do_video=["40"])
    _rascunho("pulado", itens_do_video=["50"])
    robo.assistente.registrar("v1", "enviado", "", agora=momento("2026-11-05 10:00"), item="60")
    assert robo.assistente.marcar_postado(robo.assistente.chave_do_envio("v1"), momento("2026-11-05 11:00"))[0] == "marcado"
    robo.assistente.registrar("v2", "enviado", "", agora=momento("2026-11-05 10:00"), item="70")   # sem o Postei
    assert robo.produtos_ja_postados() == {"10", "11", "20", "30", "31", "60"}
    # Onde estava cada um: o lugar mais adiantado (o post do robô vale mais que o Postei ✅, que vale
    # mais que o aprovado e o rascunho).
    _rascunho("postado", itens_do_video=["10"])
    robo.assistente.registrar("v3", "enviado", "", agora=momento("2026-11-05 10:00"), item="20")
    assert robo.assistente.marcar_postado(robo.assistente.chave_do_envio("v3"), momento("2026-11-05 11:00"))[0] == "marcado"
    onde = robo.onde_os_produtos_foram()
    assert onde == {"10": robo.ONDE_JA_FOI["postado"], "11": robo.ONDE_JA_FOI["rascunho"],
                    "20": robo.POSTEI_NO_ASSISTENTE, "30": robo.ONDE_JA_FOI["postado"],
                    "31": robo.ONDE_JA_FOI["postado"], "60": robo.POSTEI_NO_ASSISTENTE}
    robo.anotar_onde_ja_foi("99", "robô")
    assert consultar("SELECT resultado FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DO_JA_POSTADO) == (robo.EM_NENHUM,)


def _editar_para_postar(chamadas, respostas=None, capa=None, rotulos=None, cor="", letras=None):
    """
    O editar_para_postar de mentira: guarda (vídeo, foto, produto, avisos) e grava o editado. Com a
    capa (bytes), o vídeo abre com a capa com a frase, como na capa com chamada ligada (P125). Com
    rotulos (lista), guarda se o vídeo vai com o Rótulo de IA. Com a cor (o nome), a edição diz que
    usou a cor do produto (P159 2). Com letras ("1" ou "0"), a edição diz se a foto do anúncio da
    capa tem letras (P181 2).
    """
    def editar_para_postar(video, foto, destino, produto="", avisos=False, outras_fotos=(), rotulo_de_ia=False,
                           anotar=None):
        chamadas.append((video, foto, produto, avisos))
        if anotar is not None:
            anotar["cor"] = cor
            if letras is not None:
                anotar["letras"] = letras
        if rotulos is not None:
            rotulos.append(rotulo_de_ia)
        motivo, como, detalhe = respostas.pop(0) if respostas else ("", robo.edicao_video.COM_LEGENDAS, "")
        if not motivo:
            with open(destino, "wb") as arquivo:
                arquivo.write(b"com os avisos" if avisos else b"editado")
        if capa and not motivo:
            como += robo.edicao_video.COM_A_CHAMADA
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
    # Sem troca de loja, o rascunho anota "0" (a medição da P146 2 separa do que não anotou).
    assert rascunho["trocado"] == "0"


def test_video_com_o_rotulo_de_ia_vai_a_edicao_com_ele(monkeypatch, avisos, tmp_path):
    # Print e vídeo do Rafael de 03/11 (07:08 e 07:10): com o Rótulo de IA, o app põe embaixo a
    # linha "Identificado como conteúdo gerado por IA" e o cartão do produto sobe; a edição sabe
    # disso, para a moldura subir junto.
    monkeypatch.setattr(robo.ps, "anuncio_do_produto",
                        lambda video: {"foto": b"foto do anuncio", "nome": VESTIDO, "preco": 59.9})
    chamadas, rotulos = [], []
    monkeypatch.setattr(robo.edicao_video, "editar_para_postar", _editar_para_postar(chamadas, rotulos=rotulos))
    ativar(edicao_ligada=True)
    video = {"arquivo": os.path.abspath("v.mp4"), "link": "https://s.shopee.com.br/x"}
    for rotulo in (True, False):
        robo.copiar_para_o_rascunho(video, "autorais", str(tmp_path / f"c_{rotulo}.mp4"), [VESTIDO],
                                    rotulo_de_ia=rotulo)
    assert rotulos == [True, False]


def test_rascunho_com_a_capa_com_chamada_abre_o_video_com_ela(monkeypatch, avisos):
    # Escolha do Rafael (02/11, P125): a capa com a frase abre o vídeo, no lugar da foto, e o app usa
    # o 1º quadro como capa da grade; o rascunho fica marcado para a medição (P76) desde o preparo.
    _fonte(monkeypatch)

    async def analisar(arquivo, prompt, imagens=None):
        return '{"confere": true, "motivo": "vestido"}'

    monkeypatch.setattr(robo.ps, "anuncio_do_produto",
                        lambda video: {"foto": b"foto do anuncio", "nome": VESTIDO, "preco": 59.9})
    monkeypatch.setattr(robo.ps.api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(robo.edicao_video, "editar_para_postar", _editar_para_postar([], capa=b"a capa"))
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24, edicao_ligada=True)
    assert robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["chamada"] == "1"
    assert consultar("SELECT COUNT(*) FROM registro_processos WHERE processo = ?", robo.PROCESSO_DA_CAPA) == (0,)


def test_rascunho_guarda_a_cor_do_produto_que_a_edicao_usou(monkeypatch, avisos):
    # Escolha do Rafael (06/11, P159 2): o vídeo vai na cor principal do produto, e o rascunho guarda
    # o nome dela, para o post conferir a faixa da capa nela.
    _fonte(monkeypatch)

    async def analisar(arquivo, prompt, imagens=None):
        return '{"confere": true, "motivo": "vestido"}'

    monkeypatch.setattr(robo.ps, "anuncio_do_produto",
                        lambda video: {"foto": b"foto do anuncio", "nome": VESTIDO, "preco": 59.9})
    monkeypatch.setattr(robo.ps.api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(robo.edicao_video, "editar_para_postar", _editar_para_postar([], capa=b"a capa", cor="verde"))
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24, edicao_ligada=True)
    assert robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert robo.esperando_aprovacao()[0]["cor"] == "verde"


def test_rascunho_guarda_se_a_foto_da_capa_tem_letras(monkeypatch, avisos):
    # Escolha do Rafael (08/11, P181 2): a foto do anúncio vai inteira à capa, com as letras que
    # tiver; o rascunho guarda se ela tem letras, para a medição de quais posts levam punição.
    _fonte(monkeypatch)

    async def analisar(arquivo, prompt, imagens=None):
        return '{"confere": true, "motivo": "vestido"}'

    monkeypatch.setattr(robo.ps, "anuncio_do_produto",
                        lambda video: {"foto": b"foto do anuncio", "nome": VESTIDO, "preco": 59.9})
    monkeypatch.setattr(robo.ps.api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(robo.edicao_video, "editar_para_postar",
                        _editar_para_postar([], capa=b"a capa", cor="verde", letras="1"))
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24, edicao_ligada=True)
    assert robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    rascunho = robo.esperando_aprovacao()[0]
    assert (rascunho["letras"], rascunho["cor"]) == ("1", "verde")


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
    monkeypatch.setattr(robo.ps, "ia_confere_produto", lambda video, vistos, avisar=True: (True, "confere"))
    monkeypatch.setattr(robo, "item_do_link", lambda link: "123")
    monkeypatch.setattr(robo, "_textos_da_ia", lambda video, nomes=None: {
        "violacao": False, "motivo": "", "bebida_alcoolica": alcool, "titulo": "Vinho Tinto 🍷 #vinho",
        "comentario": "c"})


def _ia_que_ve_outro_produto(monkeypatch):
    def ia(video, vistos, avisar=True):
        vistos.append("outro pingente")
        return False, robo.ps.MOTIVO_OUTRO_PRODUTO + " (1ª vez)"
    monkeypatch.setattr(robo.ps, "ia_confere_produto", ia)


def test_produto_achado_pela_ia_toma_o_lugar_do_produto_do_link(monkeypatch, avisos):
    # Escolha do Rafael (06/11, P158 2): no lugar de deixar o vídeo de lado, o robô segue com o
    # produto do vídeo que achou: curtir, anexar e a régua dos produtos a mais usam o achado.
    _ate_os_textos_da_ia(monkeypatch, alcool=False)
    _ia_que_ve_outro_produto(monkeypatch)
    achado = {"nome": "Colar Trevo", "link": "https://s.shopee.com.br/achado", "comissao": 12.0, "preco": 30.0,
              "valor": 3.6, "vendas": 5, "imagem": "", "item": "2", "vistos": ["é o mesmo colar"]}
    monkeypatch.setattr(robo, "achar_o_produto_do_video", lambda video: achado)
    seguiu = []

    def espacos_livres(d, video, principal, original, vistos, *a, **k):
        seguiu.append((video["link"], principal, original, list(vistos)))
        raise RuntimeError("seguiu para os produtos a mais")

    monkeypatch.setattr(robo, "espacos_livres", espacos_livres)
    ident = robo.criar("video:1")
    with pytest.raises(RuntimeError, match="seguiu para os produtos a mais"):
        robo._preparar(None, ident, {"id": "video:1", "arquivo": "v.mp4", "link": LINK}, "viral")
    link, principal, original, vistos = seguiu[0]
    assert link == principal["link"] == achado["link"] and principal["comissao"] == 12.0
    assert original["preco"] == 30.0 and vistos == ["outro pingente", "é o mesmo colar"]
    assert any("Achei o do vídeo na Shopee" in a and "12.0%" in a for a in avisos if isinstance(a, str))
    assert consultar("SELECT achado FROM shopee_video_rascunhos WHERE id = ?", ident) == ("1",)


def test_sem_o_produto_do_video_achado_o_video_fica_de_lado_com_o_aviso(monkeypatch, avisos):
    _ate_os_textos_da_ia(monkeypatch, alcool=False)
    _ia_que_ve_outro_produto(monkeypatch)
    ident = robo.criar("video:1")
    with pytest.raises(robo.Parada) as parada:
        robo._preparar(None, ident, {"id": "video:1", "arquivo": "v.mp4", "link": LINK}, "viral")
    assert parada.value.motivo.startswith(robo.ps.MOTIVO_OUTRO_PRODUTO) and parada.value.do_video
    aviso = [a for a in avisos if isinstance(a, str) and robo.ps.AVISO_IA in a]
    assert len(aviso) == 1 and "O que a IA viu: outro pingente" in aviso[0]
    assert "Procurei o produto do vídeo na Shopee, e a IA não confirmou nenhum." in aviso[0]
    # A IA que não respondeu não procura nem avisa: o vídeo fica de lado como antes.
    procurou = []
    monkeypatch.setattr(robo, "achar_o_produto_do_video", lambda video: procurou.append(video) or None)
    monkeypatch.setattr(robo.ps, "ia_confere_produto",
                        lambda video, vistos, avisar=True: (False, "a IA não respondeu à conferência (1ª vez): parado"))
    with pytest.raises(robo.Parada):
        robo._preparar(None, robo.criar("video:2"), {"id": "video:2", "arquivo": "v.mp4", "link": LINK}, "viral")
    assert not procurou


async def _busca_negada(termo, limite=10, sort_type=2, negada_levanta=False):
    """A busca da API de afiliado negada pelo erro de sistema da Shopee em todas as tentativas."""
    if negada_levanta:
        raise robo.api_shopee.BuscaNegada("código 10.000")
    return []


def test_busca_negada_no_produto_do_video_nao_deixa_o_video_de_lado(monkeypatch, avisos):
    # 12/11: a API de afiliado negou buscas com o erro de sistema da Shopee (código 10000) mesmo depois
    # das tentativas, e a busca negada parecia a busca que não achou nada: o vídeo ficava de lado de vez.
    # A busca negada não é do vídeo: a rodada para e o vídeo volta mais tarde (como na P182 1).
    _ate_os_textos_da_ia(monkeypatch, alcool=False)
    _ia_que_ve_outro_produto(monkeypatch)
    monkeypatch.setattr(robo, "achar_o_produto_do_video", ACHAR)
    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", _busca_negada)
    monkeypatch.setattr(robo.ps, "ia_diz_o_produto_do_video", lambda video: "pingente de trevo")
    with pytest.raises(robo.Parada) as parada:
        robo._preparar(None, robo.criar("video:1"), {"id": "video:1", "arquivo": "v.mp4", "link": LINK}, "viral")
    assert parada.value.motivo == robo.motivo_da_busca_negada("código 10.000") and not parada.value.do_video
    assert robo.passo_do_motivo(parada.value.motivo) == "busca negada pela Shopee"
    assert consultar("SELECT resultado, detalhe FROM registro_processos WHERE processo = ? ORDER BY rowid DESC",
                     robo.PROCESSO_DO_PRODUTO_ACHADO) == ("não achado - a busca foi negada pela Shopee", "código 10.000")
    assert not any(isinstance(a, str) and "Procurei o produto do vídeo" in a for a in avisos)


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

    def editar_para_postar(video, foto, destino, produto="", avisos=False, outras_fotos=(), rotulo_de_ia=False,
                           anotar=None):
        fotos.append((foto, produto))
        if not foto:
            return "a foto do anúncio não veio", robo.edicao_video.SO_COM_O_EDITOR_1, ""
        with open(destino, "wb") as arquivo:
            arquivo.write(b"editado")
        return "", robo.edicao_video.COM_LEGENDAS, ""

    async def buscar(termo, limite=10, sort_type=2, negada_levanta=False):
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


def test_ver_produtos_com_a_busca_da_foto_negada_volta_mais_tarde(monkeypatch, tmp_path):
    # 12/11 às 10:13: a busca da foto do 1º produto de um vídeo de Ver Produtos foi negada pela API
    # (código 10000), e o vídeo ficou de lado de vez, como se o anúncio não existisse. A busca negada
    # não é do vídeo: ele volta mais tarde.
    original, copia = str(tmp_path / "original.mp4"), str(tmp_path / "copia.mp4")
    with open(original, "wb") as arquivo:
        arquivo.write(b"video")
    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", _busca_negada)
    monkeypatch.setattr(robo.edicao_video, "editar_para_postar", lambda *a, **k: pytest.fail("sem a foto não edita"))
    ativar(edicao_ligada=True)
    video = {"arquivo": original, "link": LINK, "de_video": True}
    with pytest.raises(robo.Parada) as parada:
        robo.copiar_para_o_rascunho(video, "viral", copia, ["Vestido Infantil Estampado Gatinho Verão Menina"])
    assert parada.value.motivo == robo.motivo_da_busca_negada("código 10.000") and not parada.value.do_video
    assert consultar("SELECT resultado, detalhe FROM registro_processos WHERE processo = ? ORDER BY rowid DESC",
                     robo.PROCESSO_DA_FOTO_DO_VER_PRODUTOS) == ("a busca foi negada pela Shopee", "código 10.000")
    assert not os.path.exists(copia)


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


def test_titulo_de_primeira_tambem_conta_no_registro(monkeypatch, avisos):
    # Só as falhas e as novas tentativas iam para o registro: num dia com um vídeo que voltou
    # vazio duas vezes, o checkup cobrou "8 falhas e 0 acertos" com os outros títulos em dia.
    from conftest import consultar
    _fonte(monkeypatch)
    assert robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = 'título da IA'") == (
        "veio de primeira", 1)


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


def test_violacao_com_o_titulo_vazio_pula_o_video_na_hora(monkeypatch, avisos):
    # Madrugada de 03/11: um kit de calcinhas parou 4 vezes seguidas em "título da IA" ("resposta sem
    # o título"): a IA via violação (lingerie em foco) e deixava o título vazio, e o robô tentava o
    # mesmo vídeo de novo. A violação pula o vídeo na hora, com o aviso no privado.
    _fonte(monkeypatch)
    chamadas = []

    async def textos(arquivo, nome):
        chamadas.append(arquivo)
        return {"violacao": True, "motivo": "lingerie em foco", "titulo": "", "comentario": ""}

    monkeypatch.setattr(robo.assistente, "textos_do_video", textos)
    resultado = robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59"))
    assert "a IA viu violação das diretrizes" in resultado and len(chamadas) == 1
    assert "não devolveu o título" not in resultado
    assert robo.listar("pulado") and any("possível violação" in aviso and "lingerie" in aviso for aviso in avisos)


def test_ia_sem_o_json_ou_sem_o_titulo_anota_qual_dos_dois(monkeypatch, avisos):
    # Sem erro do Google, o registro diz se a IA respondeu sem o JSON ou com o JSON sem o título.
    from conftest import consultar
    _fonte(monkeypatch)
    respostas = [None, {"violacao": False, "motivo": "", "titulo": "", "comentario": ""}]

    async def textos(arquivo, nome):
        return respostas.pop(0)

    monkeypatch.setattr(robo.assistente, "textos_do_video", textos)
    resultado = robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59"))
    assert "a IA não devolveu o título (resposta sem o título)" in resultado
    detalhes = consultar("SELECT GROUP_CONCAT(detalhe, ' | ') FROM registro_processos WHERE processo = 'título da IA'")
    assert detalhes == ("resposta sem o JSON | resposta sem o título",)


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
    _outro_produto(monkeypatch)
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


def test_print_do_rascunho_manda_o_print_e_a_capa_do_mais_novo(monkeypatch, avisos, tmp_path):
    # Pedido do Rafael (02/11, depois da capa até a beirada): o print do próximo rascunho, para
    # conferir a capa sem abrir Rascunhos do Robô 📝; vai também o 1º quadro do vídeo, a capa que
    # vai para a grade. Não mexe no celular.
    import os
    os.makedirs(robo.PASTA_RASCUNHOS, exist_ok=True)
    assert robo.print_do_rascunho() == "nenhum rascunho esperando a aprovação"
    for numero, hora in ((1, "17:20"), (2, "18:35")):
        ident = robo.criar(f"video:{numero}", momento(f"2026-11-02 {hora}"))
        imagem = tmp_path / f"print_{numero}.png"
        imagem.write_bytes(b"\x89PNG")
        robo.atualizar(ident, estado="rascunho", print=str(imagem), arquivo=str(tmp_path / f"video_{numero}.mp4"))
    quadros = []

    def primeiro_quadro(arquivo):
        quadros.append(os.path.basename(arquivo))
        destino = os.path.join(robo.PASTA_RASCUNHOS, "capa_para_conferir.png")
        open(destino, "wb").write(b"\x89PNG")
        return destino

    monkeypatch.setattr(robo, "_primeiro_quadro", primeiro_quadro)
    assert robo.print_do_rascunho("2026-11-02 17:40") == "rascunho das 18:35: 2 foto(s) mandada(s)"
    assert quadros == ["video_2.mp4"]
    legendas = [aviso[1] for aviso in avisos if isinstance(aviso, tuple) and aviso[0] == "foto"]
    assert "Rascunho das 18:35: o print da tela final" in legendas[0] and "1º quadro do vídeo" in legendas[1]
    # O PNG do quadro não fica no servidor.
    assert not os.path.exists(os.path.join(robo.PASTA_RASCUNHOS, "capa_para_conferir.png"))
    # Nenhum feito depois do horário pedido.
    assert robo.print_do_rascunho("2026-11-02 19:00") == "nenhum rascunho esperando a aprovação feito desde 19:00"
    # Pelo comando do avisar.yml: "AAAA-MM-DDTHH:MM", e o resultado sai na tela.
    assert robo.main(["--print-do-rascunho", "2026-11-02T17:40"]) == 0


def test_primeiro_quadro_do_video_do_rascunho(tmp_path):
    import os
    import shutil
    import subprocess
    os.makedirs(robo.PASTA_RASCUNHOS, exist_ok=True)
    assert robo._primeiro_quadro(str(tmp_path / "nao_existe.mp4")) is None and robo._primeiro_quadro("") is None
    if not shutil.which("ffmpeg"):
        return
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0xee4d2d:size=72x128:rate=10:duration=1",
                    str(video)], check=True)
    quadro = robo._primeiro_quadro(str(video))
    from PIL import Image
    with Image.open(quadro) as imagem:
        assert imagem.size == (72, 128)


def test_horario_sem_rascunho_volta_mais_tarde_no_mesmo_dia_uma_vez(monkeypatch, avisos):
    # Escolha do Rafael (02/11, P132 1): o horário cujos 3 vídeos não passaram volta mais tarde no
    # mesmo dia, no maior vão livre, a pelo menos 30 min de agora e dos outros horários; o que já é a
    # volta de outro não volta de novo.
    import registro_processos as rp
    ativar(robo_limite_min=3, robo_limite_max=3, robo_inicio=8, robo_fim=20)
    config = robo.ler_config()
    robo.db.salvar_config(robo.CHAVE_DIA, {"data": "2026-10-22", "horarios": ["10:00", "14:00", "18:00"],
                                            "feitos": 0})
    assert robo.consumir_horarios(config, momento("2026-10-22 10:00"))
    estado = robo.estado_do_dia(config, momento("2026-10-22 10:00"))
    assert estado["feitos"] == 1 and not estado["reposto"]
    # Os 3 vídeos do horário das 10:00 não passaram: o último pulado acaba o horário às 10:40.
    robo.db.salvar_config(robo.CHAVE_DIA, dict(estado, videos=robo.VIDEOS_POR_HORARIO, tentativas=0))
    robo.marcar_para_repetir(config, momento("2026-10-22 10:40"), video={"id": "a3"}, do_video=True)
    estado = robo.estado_do_dia(config, momento("2026-10-22 10:40"))
    # Os vãos livres: das 11:10 às 13:30, das 14:30 às 17:30 e das 18:30 às 20:00 (o fim do Horário do
    # Robô); o maior é o da tarde, e ele volta no meio dele.
    assert estado["horarios"] == ["14:00", "16:00", "18:00"] and estado["feitos"] == 0
    assert estado["repostos"] == ["16:00"] and estado["volta_do_horario"] == "16:00"
    assert "ele volta às 16:00, hoje mesmo" in robo.aviso_rascunho_nao_saiu(config, momento("2026-10-22 10:40"))
    # O dia segue com os mesmos horários: às 14:00 o de sempre, às 16:00 a volta.
    assert not robo.consumir_horarios(config, momento("2026-10-22 13:59"))
    assert robo.consumir_horarios(config, momento("2026-10-22 14:00"))
    assert not robo.estado_do_dia(config, momento("2026-10-22 14:00"))["reposto"]
    assert robo.consumir_horarios(config, momento("2026-10-22 16:00"))
    estado = robo.estado_do_dia(config, momento("2026-10-22 16:00"))
    assert estado["reposto"] and estado["repostos"] == []
    # A volta que também acaba sem rascunho não volta de novo.
    robo.db.salvar_config(robo.CHAVE_DIA, dict(estado, videos=robo.VIDEOS_POR_HORARIO, tentativas=0))
    robo.marcar_para_repetir(config, momento("2026-10-22 16:30"), video=None)
    estado = robo.estado_do_dia(config, momento("2026-10-22 16:30"))
    assert estado["horarios"] == ["14:00", "16:00", "18:00"] and estado["feitos"] == 2
    assert "Próximo horário do plano: 18:00" in robo.aviso_rascunho_nao_saiu(config, momento("2026-10-22 16:30"))
    registro = [(r, d) for _m, _p, r, d, _o in rp.sequencia("shopee_video", robo.PROCESSO_DO_HORARIO_SEM_RASCUNHO,
                                                            "2000-01-01 00:00:00")]
    assert registro == [("volta mais tarde", "às 16:00"), ("de fora", "já era a volta de outro horário")]


def test_horario_sem_rascunho_sem_vao_no_dia_fica_de_fora(monkeypatch, avisos):
    import registro_processos as rp
    ativar(robo_limite_min=2, robo_limite_max=2, robo_inicio=8, robo_fim=22)
    config = robo.ler_config()
    # Às 21:40, até o fim do Horário do Robô (22h) não cabem 30 min de agora: o horário fica de fora.
    robo.db.salvar_config(robo.CHAVE_DIA, {"data": "2026-10-22", "horarios": ["10:00", "21:35"], "feitos": 2,
                                            "videos": robo.VIDEOS_POR_HORARIO, "tentativas": 0})
    robo.marcar_para_repetir(config, momento("2026-10-22 21:40"), video=None)
    estado = robo.estado_do_dia(config, momento("2026-10-22 21:40"))
    assert estado["horarios"] == ["10:00", "21:35"] and estado["feitos"] == 2 and not estado["volta_do_horario"]
    assert "hoje não há mais horários" in robo.aviso_rascunho_nao_saiu(config, momento("2026-10-22 21:40"))
    registro = [(r, d) for _m, _p, r, d, _o in rp.sequencia("shopee_video", robo.PROCESSO_DO_HORARIO_SEM_RASCUNHO,
                                                            "2000-01-01 00:00:00")]
    assert registro == [("de fora", "sem espaço no dia")]
    # O vão fica a pelo menos 30 min de cada horário que falta, também perto dele.
    estado = {"data": "2026-10-22", "horarios": ["10:00", "12:00", "13:00"], "feitos": 1}
    # Das 13:30 às 22:00, o maior vão: no meio dele.
    assert robo.vao_para_o_horario(config, estado, momento("2026-10-22 11:00")) == "17:44"
    # Até as 12h, só cabe às 11:30, a 30 min de agora e das 12:00; às 11:40, nem isso.
    assert robo.vao_para_o_horario({**config, "robo_fim": 12}, estado, momento("2026-10-22 11:00")) == "11:30"
    assert robo.vao_para_o_horario({**config, "robo_fim": 12}, estado, momento("2026-10-22 11:40")) is None


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
    # O caminho até o Perfil (post, rascunho, treino) não é a limpeza dos favoritos, que também
    # passa por Criadores & Afiliados.
    assert robo.passo_do_motivo("depois de Criadores & Afiliados, a tela não mostrou Conta") == "navegar no app"
    assert robo.passo_do_motivo("depois de Eu, a tela não mostrou Criadores & Afiliados") == "navegar no app"
    assert robo.passo_do_motivo("não achei Criadores & Afiliados na aba Eu") == "descurtir em Meus Favoritos"


PAINEL_DO_ANDROID = ('<hierarchy><node package="com.android.systemui" resource-id="com.android.systemui:id/qs_frame" '
                     'bounds="[0,0][1080,2400]" text="" content-desc="" clickable="false" />'
                     '<node package="com.android.systemui" resource-id="com.android.systemui:id/tile_label" '
                     'bounds="[100,500][400,560]" text="Lanterna" content-desc="" clickable="false" /></hierarchy>')


def test_painel_do_android_por_cima_do_app_e_fechado_e_a_tela_segue(monkeypatch):
    # 02/11, 23:39: o painel do Android (Wi-Fi, Bluetooth, lanterna) estava aberto no Motorola, por
    # cima do app, e o post parou em "depois de Criadores & Afiliados, a tela não mostrou Conta".
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    app = AppDeMentira()
    app.atual = "eu"
    shopee = app.dump_hierarchy()
    assert not robo.painel_do_android_aberto(shopee) and robo.painel_do_android_aberto(PAINEL_DO_ANDROID)

    class ComOPainel(AppDeMentira):
        aberto = True

        def dump_hierarchy(self):
            return PAINEL_DO_ANDROID if self.aberto else super().dump_hierarchy()

        def press(self, tecla):
            self.teclas.append(tecla)
            self.aberto = False

    d = ComOPainel()
    d.atual = "eu"
    xml = robo.tela(d)
    assert d.teclas == ["back"] and xml == shopee and robo.tem(xml, "Criadores & Afiliados")
    registro = [(linha[2], linha[3]) for linha in robo.registro_processos.sequencia(
        "shopee_video", "voltar no app", "2000-01-01 00:00:00")]
    assert registro == [("painel do Android por cima", "fechado com o voltar")]
    # Sem o painel, nenhuma tecla.
    assert robo.tela(d) == shopee and d.teclas == ["back"]


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
    assert resultado == "os próximos 1 vídeos da fonte são de produtos sem oferta de afiliado ou já postados"
    assert robo.estado_do_dia(robo.ler_config(), momento("2026-10-22 23:59"))["repetir"] is True


def _videos_com_valor(monkeypatch, valores, padrao=5.99):
    """
    Vídeos da fonte mais novos que o a1, do mais novo para o mais velho, cada um com o produto do link que
    paga valores[i] reais por venda (o preço 100 e a comissão valores[i]%); o do a1 paga padrao.
    """
    for i, _valor in enumerate(valores):
        with open(f"archive/v{i}.mp4", "wb") as f:
            f.write(b"video")
        inserir("INSERT INTO fila_autorais VALUES (?, ?, ?, ?)", f"v{i}", f"archive/v{i}.mp4",
                f"Produto {i}\nhttps://s.shopee.com.br/valor{i}", f"2026-10-22 {19 - i}:00:00")

    async def produtos_do_link(link):
        for i, valor in enumerate(valores):
            if link.endswith(f"/valor{i}"):
                return [{"nome": VESTIDO, "preco": 100.0, "comissao": valor, "item": f"9{i}"}], link
        return [{"nome": VESTIDO, "preco": 100.0, "comissao": padrao, "item": "2"}], link

    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)


def test_robo_escolhe_entre_os_proximos_o_produto_que_paga_mais_por_venda(monkeypatch, avisos):
    # Escolha do Rafael (10/11, P194 1): de 25/09 a 09/11, 2 produtos deram 70% da comissão e os posts
    # do robô ainda não tinham vendido. Entre os próximos 10 vídeos da fonte, o robô escolhe o de
    # produto que paga mais por venda (o preço vezes a comissão) e deixa de lado, só no dia, o que paga
    # menos de R$ 2.
    _fonte(monkeypatch)
    _videos_com_valor(monkeypatch, [1.5, 5.0, 9.0, 3.0])
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True, "fonte": "autorais"})
    agora = momento("2026-10-22 23:59")
    assert robo.rodada(preparar=True, d=AppDeMentira(), agora=agora) == "rascunho salvo"
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["id_video"] == "v2" and rascunho["valor"] == "9.00"
    # O de menos de R$ 2 fica de lado só hoje, sem virar pulado; os outros continuam na fila.
    assert robo.listar("pulado") == []
    assert robo.estado_do_dia(robo.ler_config(), agora)["abaixo_do_minimo"] == ["v0"]
    assert consultar("SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DA_ESCOLHA) == ("o que paga mais", "o 3º de 5; 1 abaixo do mínimo", 1)
    assert any("Vídeo: o que paga mais por venda (R$ 9,00) entre os próximos 10 de" in str(a) for a in avisos)
    assert robo.proximo_video(robo.ler_config(), robo.evitar_hoje(robo.ler_config(), agora), agora)["id"] == "v1"
    # No dia seguinte, o de baixo é visto de novo (o preço e a comissão mudam).
    assert "v0" not in robo.evitar_hoje(robo.ler_config(), momento("2026-10-23 12:00"))


def test_so_videos_abaixo_do_minimo_por_venda_param_sem_tocar_no_celular(monkeypatch, avisos):
    # P194 1: com todos os próximos pagando menos de R$ 2 por venda, nenhum vira rascunho (nem fica
    # pulado: no dia seguinte eles são vistos de novo), e o celular nem é tocado.
    _fonte(monkeypatch)
    _videos_com_valor(monkeypatch, [1.0, 1.99], padrao=0.5)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    agora = momento("2026-10-22 23:59")
    resultado = robo.rodada(d=Intocavel(), agora=agora)
    assert resultado == "os próximos 3 vídeos da fonte pagam menos que o mínimo por venda"
    assert robo.passo_do_motivo(resultado) == "valor por venda" and "R$" not in resultado
    assert robo.listar("pulado") == []
    assert robo.estado_do_dia(robo.ler_config(), agora)["abaixo_do_minimo"] == ["a1", "v0", "v1"]
    assert consultar("SELECT resultado, detalhe FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DA_ESCOLHA) == ("todos abaixo do mínimo", "3 de 3")


def test_video_de_varios_produtos_fica_na_vez_dele_na_escolha_pelo_valor(monkeypatch):
    # P194 1: o vídeo de vários produtos (o link é de um vídeo; os produtos ficam no Ver Produtos) só
    # tem o valor no celular. Até o Rafael decidir (P200), ele fica na vez dele, como antes: o produto
    # antes dele na fila só passa na frente se pagar o mínimo.
    _fonte_de_video(monkeypatch)
    _videos_com_valor(monkeypatch, [1.0])
    config = {**robo.PADRAO, "fonte": "autorais"}
    hoje = momento("2026-10-22 12:00")
    video, porque = robo.escolher_o_video(config, robo.evitar_hoje(config, hoje), hoje)
    assert (video["id"], video["de_video"], porque) == ("a1", True, "") and "valor" not in video
    assert consultar("SELECT resultado, detalhe FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DA_ESCOLHA) == ("na vez dele: vídeo de vários produtos", "o 2º de 2; 1 abaixo do mínimo")
    # Com o produto antes dele pagando o mínimo, o produto passa na frente.
    async def produtos_do_link(link):
        return [{"nome": VESTIDO, "preco": 100.0, "comissao": 2.0, "item": "90"}], link
    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)
    amanha = momento("2026-10-23 12:00")
    video, porque = robo.escolher_o_video(config, robo.evitar_hoje(config, amanha), amanha)
    assert (video["id"], video["valor"], porque) == ("v0", 2.0, "")


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
    # Sem o link do post (o celular de mentira não tem o Perfil), o comentário e o Canal Afiliados
    # esperam a busca de novo nas rodadas seguintes (P148 2), e o aviso do post diz isso.
    assert robo.AVISO_SEM_O_LINK_AGORA in avisos[0] and len(avisos) == 1
    assert robo.pegar(ident)["busca_do_link"] == {"vezes": ["2026-10-22 23:59:00"], "fim": ""}


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


def test_postar_agora_posta_o_aprovado_na_hora_mesmo_pausado_e_fora_do_horario(monkeypatch, avisos,
                                                                              caminho_do_rascunho):
    # Escolha do Rafael (03/11, P138): o Postar Agora 🚀 posta o aprovado na hora, a qualquer hora e
    # sem esperar os 30 min do último post.
    ident = _aprovado(monkeypatch)
    robo.atualizar(ident, postar_em="2026-10-23 09:00:00")
    ativar(robo_inicio=8, robo_fim=22, robo_pausado=True)
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-22 23:30")))
    robo.registrar_tentativa("postar", "postado", agora=momento("2026-10-22 23:20"))
    app = AppComQuadros()
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(postar=ident, d=app, agora=momento("2026-10-22 23:30")) == "rascunho aprovado postado"
    assert app.toques.count("@btn_post") == 1 and robo.pegar(ident)["estado"] == "postado"
    assert "postei o vídeo que você aprovou" in avisos[0]
    pedidos = [linha[2] for linha in robo.registro_processos.sequencia(
        "shopee_video", robo.PROCESSO_DO_POSTAR_AGORA, "2000-01-01 00:00:00")]
    assert pedidos == ["pedido"]


def test_postar_agora_que_nao_sai_nao_gasta_tentativa(monkeypatch, avisos, caminho_do_rascunho):
    ident = _aprovado(monkeypatch)
    app = AppComQuadros()
    app.legenda, app.com_produto = "Outro título de outro rascunho qualquer #outro", True
    assert "parado" in robo.rodada(postar=ident, d=app, agora=momento("2026-10-22 23:30"))
    rascunho = robo.pegar(ident)
    assert rascunho["estado"] == "aprovado" and int(rascunho["falhas_ao_postar"] or 0) == 0
    assert "não consegui postar agora o rascunho que você pediu" in avisos[-1] and "Postar Agora 🚀" in avisos[-1]
    # O que não está mais aprovado não vai ao ar pelo botão, e o Rafael fica sabendo.
    robo.atualizar(ident, estado="postado")
    assert "não está mais aprovado" in robo.rodada(postar=ident, d=Intocavel(), agora=momento("2026-10-22 23:40"))
    assert "não postei agora o rascunho que você pediu" in avisos[-1]


def test_main_do_postar_agora(monkeypatch):
    pedidos = []
    monkeypatch.setattr(robo, "rodada", lambda **kw: pedidos.append(kw) or "ok")
    assert robo.main(["--postar", "7"]) == 0 and pedidos[-1]["postar"] == 7
    assert robo.main(["--postar"]) == 2 and robo.main(["--postar", "x"]) == 2 and len(pedidos) == 1


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
    # Depois de apagar, o fim da rodada deixa o app no Eu, sem vídeo tocando.
    assert app.toques[-4:] == [(185, 600), "Excluir (1)", "Confirmar", "Eu"]
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


# A página do app presa carregando (Motorola, madrugada de 02/11): o esqueleto, sem texto
# nenhum, que o voltar não tira.
ESQUELETO = _xml(*(_no_do_app(robo.ps.PACOTE, "", (0, 300 + 40 * i, 1080, 330 + 40 * i)) for i in range(25)))


class CelularComPaginaCarregando:
    """O app preso na página carregando; o link da página inicial a tira (ou não, com o_link_tira=False)."""

    info = {"screenOn": True}

    def __init__(self, o_link_tira=True):
        self.o_link_tira, self.teclas, self.comandos, self.no_inicio = o_link_tira, [], [], False

    def dump_hierarchy(self):
        return _xml(_no_do_app(robo.ps.PACOTE, "Eu", (860, 2250, 1080, 2400))) if self.no_inicio else ESQUELETO

    def press(self, tecla):
        self.teclas.append(tecla)

    def shell(self, comando):
        self.comandos.append(comando)
        self.no_inicio = self.o_link_tira

    def app_current(self):
        return {"package": robo.ps.PACOTE, "activity": "com.shopee.app.react.ReactActivity_"}


def test_voltar_na_pagina_presa_carregando_abre_a_pagina_inicial_pelo_link(monkeypatch):
    # Madrugada de 02/11 (04:02, 04:14, 05:25 e 07:03): uma página do app ficou presa carregando,
    # o voltar não a tirava e cada rodada parava em "não consegui voltar até Eu". Abrir um link
    # no app funcionava por cima dela: depois de alguns voltar, o robô abre a página inicial pelo
    # link, sem fechar o app (P15).
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    assert robo.ps.pagina_carregando(ESQUELETO)
    celular = CelularComPaginaCarregando()
    robo.voltar(celular, "Eu")
    assert celular.no_inicio and celular.teclas == ["back"] * robo.VOLTAS_NA_PAGINA_CARREGANDO
    assert celular.comandos == [["am", "start", "-a", "android.intent.action.VIEW", "-d",
                                 robo.ps.LINK_DA_PAGINA_INICIAL, "-p", robo.ps.PACOTE]]
    assert consultar("SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = 'voltar no app'") == (
        "página presa carregando", "a página inicial aberta pelo link", None)


def test_voltar_que_nem_o_link_tira_da_pagina_carregando_para_e_diz_onde(monkeypatch):
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    celular = CelularComPaginaCarregando(o_link_tira=False)
    with pytest.raises(robo.Parada) as parada:
        robo.voltar(celular, "Eu", vezes=8)
    # O link vai uma vez só; depois, o voltar segue até desistir.
    assert len(celular.comandos) == 1 and celular.teclas == ["back"] * 7
    onde = (f"app {robo.ps.PACOTE}, tela ReactActivity_, tela do celular ligada, a página presa carregando")
    assert str(parada.value) == f"não consegui voltar até Eu ({onde})"


class CelularNoFeedComVideo:
    """
    O app no Para você com um vídeo tocando (Motorola, 07/11, às 18:12 e às 18:56): a leitura traz só
    as barras do Android, mesmo relida, e o voltar não muda nada; o link da página inicial a tira.
    """

    info = {"screenOn": True}

    def __init__(self):
        self.teclas, self.comandos, self.no_inicio = [], [], False

    def dump_hierarchy(self):
        if self.no_inicio:
            return _xml(_no_do_app(robo.ps.PACOTE, "Eu", (860, 2250, 1080, 2400)))
        return _xml(_no_do_app(robo.ps.PACOTE_SISTEMA, "", (0, 0, 1080, 120)))

    def press(self, tecla):
        self.teclas.append(tecla)

    def shell(self, comando):
        self.comandos.append(comando)
        self.no_inicio = True

    def app_current(self):
        return {"package": robo.ps.PACOTE, "activity": "com.shopee.app.ui.home.HomeActivity_"}


def test_voltar_ao_eu_sem_o_app_na_leitura_abre_a_pagina_inicial_pelo_link(monkeypatch):
    # 07/11, 18:12 e 18:56: com um vídeo tocando no Para você, a leitura vinha só com as barras do
    # Android, mesmo relida; o voltar apertava voltar em vão, a rodada parava em "não consegui
    # voltar até Eu", e o vídeo seguia tocando em laço. No caminho até o Eu, a página inicial abre
    # pelo link, sem fechar o app (P15).
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    celular = CelularNoFeedComVideo()
    robo.voltar(celular, "Eu")
    assert celular.no_inicio and celular.teclas == []
    assert celular.comandos == [["am", "start", "-a", "android.intent.action.VIEW", "-d",
                                 robo.ps.LINK_DA_PAGINA_INICIAL, "-p", robo.ps.PACOTE]]
    assert consultar("SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = 'voltar no app'") == (
        "leitura sem o app", "a página inicial aberta pelo link", None)
    # No caminho até outra tela (a lista dos rascunhos), o link não abre: o voltar segue como antes.
    celular = CelularNoFeedComVideo()
    with pytest.raises(robo.Parada):
        robo.voltar(celular, "Selecionar", vezes=3)
    assert celular.comandos == [] and celular.teclas == ["back"] * 3


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
    assert _registro_do_link() == [("copiado", ""), ("sem o link", "o Copiar link não deixou o link copiado")]


def _registro_do_link():
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DO_LINK_DO_POST, "2000-01-01 00:00:00")
    return [(r[2], r[3]) for r in registro]


def test_link_do_post_que_nao_sai_diz_o_passo_no_registro(monkeypatch):
    # Em 06/11, às 19:18, um post saiu sem o link, e nada dizia em que passo: sem o link, o vídeo
    # não vai ao Canal Afiliados nem ganha o comentário no próprio post (P148 2).
    def sem_o_eu(d):
        raise robo.Parada("não achei Eu na tela")
    monkeypatch.setattr(robo, "ir_ao_perfil", sem_o_eu)
    assert robo.link_do_post(None) == ""
    monkeypatch.setattr(robo, "ir_ao_perfil", lambda d: None)
    monkeypatch.setattr(robo, "tela", lambda d, seguir=False: _xml())
    assert robo.link_do_post(None) == ""
    assert _registro_do_link() == [("sem o link", "parou em navegar no app"),
                                   ("sem o link", "nenhum vídeo na grade do Perfil")]


class CelularSoComAsBarras:
    """
    A leitura que traz só as barras do Android nas primeiras vezes, com o app na tela (Motorola,
    06/11, às 19:31, com uma live tocando no Para você).
    """

    def __init__(self, leituras_sem_o_app):
        self.leituras_sem_o_app, self.toques = leituras_sem_o_app, []

    def dump_hierarchy(self):
        if self.leituras_sem_o_app > 0:
            self.leituras_sem_o_app -= 1
            return _xml(_no_do_app(robo.ps.PACOTE_SISTEMA, "", (0, 0, 1080, 120)))
        return _xml(_no_do_app(robo.ps.PACOTE, robo.ABA_PARA_VOCE, (640, 150, 760, 210)))

    def click(self, x, y):
        self.toques.append((x, y))


def _registro_da_leitura():
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_LEITURA_DA_TELA,
                                                 "2000-01-01 00:00:00")
    return [(r[2], r[3]) for r in registro]


def test_leitura_so_com_as_barras_do_android_e_feita_de_novo(monkeypatch):
    # No Motorola, em 06/11 às 19:31, a leitura veio só com as barras do Android, com o app na
    # tela, e o feed parou ("não achei Para você na tela"). A tela é lida de novo antes de seguir.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    celular = CelularSoComAsBarras(2)
    robo.tocar(celular, robo.ABA_PARA_VOCE, 0)
    assert celular.toques == [(700, 180)]
    assert _registro_da_leitura() == [("só as barras do Android", "o app voltou na 2ª releitura")]
    # O app que não volta à leitura: a parada de sempre, e o registro diz quantas vezes leu.
    with pytest.raises(robo.Parada):
        robo.tocar(CelularSoComAsBarras(99), robo.ABA_PARA_VOCE, 0)
    assert _registro_da_leitura()[-1] == ("só as barras do Android",
                                          f"sem o app em {robo.RELEITURAS_SEM_O_APP} releituras")
    # A leitura com o app não é refeita nem anotada.
    robo.tocar(CelularSoComAsBarras(0), robo.ABA_PARA_VOCE, 0)
    assert len(_registro_da_leitura()) == 2


def test_leitura_que_nao_traz_o_app_nao_conta_como_falha_e_diz_quem_esta_na_frente(monkeypatch):
    # Checkup de 08/11: 4 leituras sem o app nem relidas, com vídeo tocando no feed e no próprio
    # post, e nenhuma parada; o checkup as contava como falha 2 dias seguidos. A leitura sem o app
    # não é falha (o passo que precisava dela é que para, e conta lá), e o registro diz que app
    # estava na frente, para conferir que era o vídeo tocando.
    monkeypatch.setattr(robo, "pausa", lambda s: None)

    class Celular(CelularSoComAsBarras):
        def __init__(self, atual):
            super().__init__(99)
            self.atual = atual

        def app_current(self):
            if self.atual is None:
                raise ConnectionError("caiu")
            return self.atual

    for atual, frente in (({"package": robo.ps.PACOTE, "activity": "com.shopee.sz.video.VideoActivity"},
                           "; na frente: a Shopee (VideoActivity)"),
                          ({"package": robo.ps.PACOTE_SISTEMA, "activity": ""}, "; na frente: o Android"),
                          ({"package": "com.outro.app", "activity": "x.Tela"}, "; na frente: outro app"),
                          (None, "")):
        with pytest.raises(robo.Parada):
            robo.tocar(Celular(atual), robo.ABA_PARA_VOCE, 0)
        assert _registro_da_leitura()[-1] == ("só as barras do Android",
                                              f"sem o app em {robo.RELEITURAS_SEM_O_APP} releituras{frente}")
    oks = consultar("SELECT COUNT(*), SUM(ok IS NULL) FROM registro_processos WHERE processo = ?",
                    robo.PROCESSO_DA_LEITURA_DA_TELA)
    assert oks == (4, 4)
    # A que volta continua contando como acerto.
    robo.tocar(CelularSoComAsBarras(1), robo.ABA_PARA_VOCE, 0)
    assert consultar("SELECT ok FROM registro_processos WHERE processo = ? ORDER BY id DESC",
                     robo.PROCESSO_DA_LEITURA_DA_TELA) == (1,)


def _post_sem_o_link(monkeypatch, ident, agora, links=()):
    """
    O publicar com o celular de mentira e o link do post que não sai na hora: cada busca devolve o
    próximo de links ("" sem ele), e o canal e o comentário de depois do post ficam anotados.
    """
    buscas, levados, comentados = [], [], []
    respostas = list(links)

    def link_do_post(d, ident=None, agora=None, titulo=None, busca=1):
        buscas.append((titulo, busca))
        return respostas.pop(0) if respostas else ""

    monkeypatch.setattr(robo, "ler_suspensao", lambda d, agora=None: None)
    monkeypatch.setattr(robo, "abrir_rascunho", lambda d, rascunho: None)
    monkeypatch.setattr(robo.ps, "conferir_tela_final", lambda d, video: (True, "confere"))
    monkeypatch.setattr(robo.ps, "ajustar_rotulo_de_ia", lambda d, ligado: (True, "rótulo"))
    monkeypatch.setattr(robo.ps, "postar", lambda d, video: (True, "ok"))
    monkeypatch.setattr(robo, "link_do_post", link_do_post)
    monkeypatch.setattr(robo, "levar_ao_canal", lambda rascunho, link: levados.append((rascunho["id"], link)))
    monkeypatch.setattr(robo, "comentar_depois_do_post", lambda d, ident, agora=None: comentados.append(ident) or "comentado")
    assert robo.publicar(object(), robo.pegar(ident), momento(agora)) == "rascunho aprovado postado"
    return buscas, levados, comentados


def test_post_sem_o_link_busca_de_novo_e_depois_comenta_e_leva_ao_canal(monkeypatch, avisos):
    # Print do Rafael das 21:41 de 06/11: o vídeo do macacão, postado às 19:18, ficou sem
    # comentário, porque logo depois do post o link não saiu (e sem ele o robô não comenta nem leva
    # o vídeo ao Canal Afiliados). Como a falha antes de comentar (P148 2), o link é buscado de novo
    # nas rodadas seguintes, a cada 30 min, conferindo pela legenda que o vídeo é o do post.
    ident = _rascunho("aprovado", postar_em="2026-10-22 12:00:00")
    buscas, levados, comentados = _post_sem_o_link(monkeypatch, ident, "2026-10-22 12:00", links=["", LINK_DO_POST])
    assert (levados, comentados) == ([], [])
    assert robo.AVISO_SEM_O_LINK_AGORA in avisos[0] and len(avisos) == 1
    assert robo.link_do_post_pendente(momento("2026-10-22 12:20")) is None
    pendente = robo.link_do_post_pendente(momento("2026-10-22 12:31"))
    assert pendente["id"] == ident
    resultado = robo.buscar_o_link_de_novo(object(), pendente, momento("2026-10-22 12:31"))
    assert resultado == "link do post: copiado na 2ª busca; comentário: comentado"
    assert buscas == [(None, 1), (TITULO, 2)]
    postado = robo.pegar(ident)
    assert postado["link_post"] == LINK_DO_POST and postado["busca_do_link"]["fim"] == "copiado"
    assert (levados, comentados) == ([(ident, LINK_DO_POST)], [ident])
    assert avisos[-1] == f"🔗 Robô da Shopee Vídeo: consegui o link do vídeo que foi ao ar às 12:00:\n\n{LINK_DO_POST}"
    assert robo.link_do_post_pendente(momento("2026-10-22 13:30")) is None
    # Na rodada, a busca de novo é a tarefa do comentário de depois do post.
    assert robo.NOMES_DAS_ACOES["comentar_post"] == "Comentário no post"


def test_link_que_nao_sai_em_tres_buscas_vai_ao_rafael_como_antes(monkeypatch, avisos):
    ident = _rascunho("aprovado", postar_em="2026-10-22 12:00:00")
    buscas, levados, comentados = _post_sem_o_link(monkeypatch, ident, "2026-10-22 12:00")
    for hora, resultado in (("12:31", "link do post: não saiu na 2ª busca"),
                            ("13:02", "link do post: não saiu em 3 buscas")):
        pendente = robo.link_do_post_pendente(momento(f"2026-10-22 {hora}"))
        assert robo.buscar_o_link_de_novo(object(), pendente, momento(f"2026-10-22 {hora}")) == resultado
    assert [busca for _titulo, busca in buscas] == [1, 2, 3]
    assert robo.link_do_post_pendente(momento("2026-10-22 14:00")) is None
    # Na última, o comentário do Gem vai ao Rafael para ele fazer à mão, e o vídeo fica fora do canal.
    assert avisos[1:] == [robo.ps.AVISO_COMENTARIO, "Amei! #achadinhos"]
    assert (levados, comentados) == ([(ident, "")], [])
    assert robo.pegar(ident)["busca_do_link"] == {"vezes": ["2026-10-22 12:00:00", "2026-10-22 12:31:00",
                                                            "2026-10-22 13:02:00"], "fim": "desistiu"}
    assert consultar("SELECT resultado, detalhe FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DO_PROPRIO) == ("sem o link do post", "3 buscas")


def test_outro_post_antes_do_link_desiste_do_anterior(monkeypatch, avisos):
    # Outro vídeo do robô no ar vira o mais novo da grade: o link do anterior não é mais buscado.
    primeiro = _rascunho("aprovado", postar_em="2026-10-22 12:00:00")
    _post_sem_o_link(monkeypatch, primeiro, "2026-10-22 12:00")
    segundo = _rascunho("aprovado", postar_em="2026-10-22 12:30:00")
    _buscas, levados, comentados = _post_sem_o_link(monkeypatch, segundo, "2026-10-22 12:30", links=[LINK_DO_POST])
    assert robo.pegar(primeiro)["busca_do_link"]["fim"] == "desistiu"
    assert (levados, comentados) == ([(primeiro, ""), (segundo, LINK_DO_POST)], [segundo])
    assert robo.link_do_post_pendente(momento("2026-10-22 13:30")) is None
    assert consultar("SELECT detalhe FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DO_PROPRIO) == ("outro vídeo foi ao ar antes",)


def test_legenda_do_post_confere_o_comeco_do_titulo():
    titulo = "Macaquinho Verde Elegante #moda #achadinhos"
    assert robo.legenda_do_post("Macaquinho Verde Elegante #m ... Veja mais", titulo)
    assert robo.legenda_do_post("Macaquinho Verde  Elegante #m…", titulo)
    assert not robo.legenda_do_post("Copo resistente que não quebra ... Veja mais", titulo)
    # Curta demais para dizer, ou sem legenda: não confere.
    assert not robo.legenda_do_post("Maca...", titulo) and not robo.legenda_do_post("", titulo)
    # O emoji que a acessibilidade lê como "..".
    com_emoji = "🔥 Macaquinho Verde Elegante #moda"
    assert robo.legenda_do_post(robo.ps.como_o_android_le(com_emoji)[:20], com_emoji)


def test_link_do_post_buscado_de_novo_confere_a_legenda_do_video(monkeypatch):
    # Na busca de novo, o vídeo mais novo da grade só vale com a legenda do post: outro vídeo pode
    # ter ido ao ar depois dele.
    def player(legenda):
        return [_no(ident="rn_vod_player_view_with_surface", caixa=(0, 0, 1080, 2260), clicavel=False),
                _no(desc="video caption user", caixa=(40, 2030, 460, 2080)),
                _no("TechPremium", caixa=(40, 2030, 460, 2080), clicavel=False),
                _no(desc="video caption title", caixa=(40, 2100, 820, 2160)),
                _no(legenda, caixa=(40, 2100, 820, 2160), clicavel=False),
                _no(desc="avatar icon", caixa=(960, 1390, 1040, 1470)),
                _no(desc="like icon", caixa=(960, 1600, 1040, 1680)),
                _no(desc="comment video icon", caixa=(960, 1770, 1040, 1840)),
                _no(desc="post video share icon", caixa=(950, 1935, 1052, 2035)),
                _no("Adicionar um comentário...", caixa=(200, 2300, 900, 2360))]

    monkeypatch.setitem(TELAS, "perfil", [_no(caixa=(0, 1210, 358, 1680))])
    monkeypatch.setitem(CAMINHO, ("perfil", (179, 1445)), "player")
    monkeypatch.setitem(CAMINHO, ("player", (1001, 1985)), "folha")
    monkeypatch.setitem(TELAS, "folha", [_no("Copiar link", caixa=(280, 2200, 440, 2300))])
    monkeypatch.setitem(CAMINHO, ("folha", "Copiar link"), "player")
    monkeypatch.setattr(robo, "ir_ao_perfil", lambda d: setattr(d, "atual", "perfil"))
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    monkeypatch.setitem(TELAS, "player", player("Copo resistente que não quebra ... Veja mais"))
    app = AppComQuadros()
    app.clipboard = LINK_DO_POST
    assert robo.link_do_post(app, titulo=TITULO, busca=2) == ""
    assert "Copiar link" not in app.toques
    # Com a legenda do post, o link sai, e o registro diz em que busca.
    monkeypatch.setitem(TELAS, "player", player(TITULO[:30] + "... Veja mais"))
    app = AppComQuadros()
    app.clipboard = LINK_DO_POST
    assert robo.link_do_post(app, titulo=TITULO, busca=2) == LINK_DO_POST
    assert _registro_do_link() == [("sem o link", "o vídeo mais novo da grade não é o do post (na 2ª busca)"),
                                   ("copiado", "na 2ª busca")]


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
        # (o cartão, sem a barra); "vazio"; "sem_player" (outra tela); "em_analise" (o aviso de
        # vídeo em análise da Shopee, Motorola, 02/11/2026).
        self.player, self.olhadas_no_player = player, 0

    def _nos(self):
        if self.atual == "removido":
            return [_no("Detalhes do Vídeo", caixa=(300, 1160, 780, 1220), clicavel=False),
                    _no("Este vídeo foi removido pelo criador", caixa=(200, 1240, 880, 1280), clicavel=False)]
        if self.atual == "player":
            self.olhadas_no_player += 1
            if self.player == "sem_player":
                return [_no("Para você", caixa=(640, 140, 830, 195), clicavel=False)]
            if self.player == "em_analise":
                return [_no("Pesquisar", caixa=(242, 143, 909, 238)),
                        _no("Vídeo em Análise", caixa=(377, 1146, 704, 1199), clicavel=False),
                        _no("Video em análise: em breve estará disponível ao público.", caixa=(173, 1215, 908, 1321),
                            clicavel=False)]
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


PRODUTO_C = "Squeeze Térmico Inox 750 ml Com Bico Retrátil"
PRODUTO_D = "Caneca Térmica Inox 350 ml Com Tampa Deslizante"
PRODUTO_E = "Garrafa Térmica Inox 2 Litros Com Alça Dobrável"


class AppDoVerMais(AppDoVerProdutos):
    """
    O Ver Produtos com o "Ver Mais (3)" (gravação do Rafael de 01/11/2026): 2 cartões de cara; o
    toque abre os outros 3 na mesma lista, com o "Esconder" depois do último, e os de baixo só
    aparecem arrastando a lista (a tela mostra só o que cabe nela). fecha_ao_voltar: a lista volta
    fechada da página do produto. perdida_depois: depois da página do 2º produto, a lista volta
    rolada até as recomendações, sem nada conhecido dela na tela.
    """

    def __init__(self, fecha_ao_voltar=False, perdida_depois=None):
        super().__init__()
        self.aberta, self.deslocamento, self.arrastos, self.toques_no_ver_mais = False, 0, 0, 0
        self.fecha_ao_voltar, self.perdida_depois, self.paginas = fecha_ao_voltar, perdida_depois, 0

    def _itens(self):
        nomes = [PRODUTO_A, PRODUTO_B] + ([PRODUTO_C, PRODUTO_D, PRODUTO_E] if self.aberta else [])
        itens, y = [("Ver Produtos (5)", 700, 50)], 1030
        for nome in nomes:
            itens.append((nome, y, 300))
            y += 320
        itens += [("Esconder" if self.aberta else "Ver Mais (3)", y, 50), ("Você Também Pode Gostar", y + 150, 50),
                  (RECOMENDADO, y + 220, 300)]
        return itens

    def _nos(self):
        if self.atual != "ver_produtos":
            return super()._nos()
        nos = []
        for texto, topo, altura in self._itens():
            topo -= self.deslocamento
            if topo < 400 or topo + altura > 2400:
                continue
            nos.append(_cartao(texto, topo) if altura == 300 else
                       _no(texto, caixa=(300, topo, 780, topo + altura), clicavel=texto in ("Ver Mais (3)", "Esconder")))
        return [_no(caixa=(0, 400, 1080, 2400), filhos="".join(nos))]

    def click(self, x, y):
        if self.atual == "ver_produtos":
            tocados = [el for el in robo.ps.elementos(self.dump_hierarchy()) if robo.ps._dentro((x, y), el["caixa"])]
            textos = {el["texto"] for el in tocados}
            assert not any(robo.ps.texto_proibido(t) for t in textos), f"tocou num botão de comprar: {textos}"
            nome = next((t for t in textos if t in (PRODUTO_A, PRODUTO_B, PRODUTO_C, PRODUTO_D, PRODUTO_E,
                                                    RECOMENDADO, "Ver Mais (3)")), None)
            self.toques.append(nome or (x, y))
            if nome == "Ver Mais (3)":
                self.aberta, self.toques_no_ver_mais = True, self.toques_no_ver_mais + 1
            elif nome:
                self.atual = "pdp:" + nome
            return
        antes = self.atual
        super().click(x, y)
        if antes == "player" and self.atual == "ver_produtos":
            # A lista abre sempre fechada e no começo.
            self.aberta, self.deslocamento = False, 0

    def press(self, tecla, meta=None):
        da_pagina = self.atual.startswith("pdp:")
        super().press(tecla, meta)
        if da_pagina and self.atual == "ver_produtos":
            self.paginas += 1
            if self.fecha_ao_voltar:
                self.aberta, self.deslocamento = False, 0
            if self.perdida_depois == self.paginas:
                recomendado = next(topo for texto, topo, _ in self._itens() if texto == RECOMENDADO)
                self.deslocamento = recomendado - 400

    def swipe(self, x1, y1, x2, y2, duracao=None):
        if self.atual == "ver_produtos":
            self.arrastos += 1
            self.deslocamento = max(0, self.deslocamento + y1 - y2)


def _produtos_do_ver_mais(app, confirma):
    """Os produtos do Ver Produtos que o robô lê na lista do AppDoVerMais: (os confirmados, os curtidos)."""
    app.atual = "player"
    app.click(500, 1970)
    video, curtidos = {"link": LINK_DE_VIDEO, "arquivo": "archive/vestido.mp4", "de_video": True}, []
    return robo._produtos_do_video(app, video, [], curtidos), curtidos


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

    async def buscar(termo, limite=10, sort_type=2, negada_levanta=False):
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


def _ver_produtos_com_valor(monkeypatch, *valores):
    """A troca do Ver Produtos (P57) devolve os produtos do criador com o valor por venda de cada um."""
    monkeypatch.setattr(robo, "trocar_os_do_ver_produtos", lambda d, video, nomes, *a, **k: [
        {"nome": nome, "link": "", "valor": valor, "trocado": "", "do_video": True, "item": str(i + 1)}
        for i, (nome, valor) in enumerate(zip(nomes, valores))])


def test_ver_produtos_que_paga_menos_que_o_minimo_fica_de_lado_no_dia(monkeypatch, avisos):
    # Escolha do Rafael (11/11, P200 1): o vídeo de link de vídeo vai na vez dele e, aberto no celular,
    # fica de lado só no dia se o produto que paga mais do Ver Produtos pagar menos de R$ 2 por venda.
    _fonte_de_video(monkeypatch)
    _ver_produtos_com_valor(monkeypatch, 1.0, 0.5)     # o que paga mais: R$ 1,00 por venda
    app = AppDoVerProdutos()
    resultado = robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59"))
    motivo = f"{robo.MOTIVO_VER_PRODUTOS_ABAIXO} (o que paga mais: R$ 1,00 por venda)"
    assert resultado.startswith(f"rascunho: parado ({motivo}")
    # Nada anexado, e as curtidas do Ver Produtos saem (a lista continua limpa).
    assert app.anexados == [] and app.curtidos == set()
    # Não é falha: a tentativa entra como "de lado", sem caso guardado, e o vídeo volta amanhã.
    assert consultar("SELECT acao, resultado, passo, motivo FROM shopee_video_tentativas") == (
        "rascunho", "de lado", "valor por venda", motivo)
    assert robo.casos_robo.casos() == [] and consultar("SELECT COUNT(*) FROM shopee_video_rascunhos") == (0,)
    assert "a1" in robo.evitar_hoje(robo.ler_config(), momento("2026-10-22 23:59"))
    assert robo.proximo_video(robo.ler_config(), robo.evitar_hoje(robo.ler_config(), momento("2026-10-23 10:00")),
                              momento("2026-10-23 10:00"))["id"] == "a1"


def test_ver_produtos_que_paga_o_minimo_segue_como_antes(monkeypatch, avisos):
    _fonte_de_video(monkeypatch)
    _ver_produtos_com_valor(monkeypatch, 3.0, 0.5)     # basta um pagar o mínimo: R$ 3,00 por venda
    app = AppDoVerProdutos()
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.anexados == [PRODUTO_A, PRODUTO_B]


def test_minimo_do_ver_produtos_vale_com_um_produto_ou_varios():
    # Com 1 produto, vale o dele; com vários, basta um pagar R$ 2 ou mais. O 0 é a oferta que a API não
    # achou pelo nome: sem o valor de nenhum, o vídeo segue como antes.
    with pytest.raises(robo.DeLadoNoDia) as parada:
        robo.conferir_o_minimo_do_ver_produtos([{"valor": 1.2, "item": "1"}, {"valor": 0, "item": ""}])
    assert parada.value.do_video and parada.value.motivo.endswith("(o que paga mais: R$ 1,20 por venda)")
    assert robo.passo_do_motivo(parada.value.motivo) == "valor por venda"
    robo.conferir_o_minimo_do_ver_produtos([{"valor": 2.0}])
    robo.conferir_o_minimo_do_ver_produtos([{"valor": 0.5}, {"valor": 3.1}])
    assert robo.melhor_valor_do_ver_produtos([{"valor": 0}, {"nome": "sem valor"}]) is None
    robo.conferir_o_minimo_do_ver_produtos([{"valor": 0}])



def test_ver_produtos_abre_o_ver_mais_e_le_os_escondidos_sem_tocar_nas_recomendacoes(monkeypatch):
    # Escolha do Rafael (28/10, P66): os produtos que o criador esconde no "Ver Mais (N)" entram
    # como os outros, conferidos pela IA, até 6; nunca os de "Você Também Pode Gostar".
    _fonte_de_video(monkeypatch, confirma=(PRODUTO_A, PRODUTO_C, PRODUTO_E))
    monkeypatch.setattr(robo, "ir_ao_inicio", lambda d: None)
    app = AppDoVerMais()
    confirmados, curtidos = _produtos_do_ver_mais(app, (PRODUTO_A, PRODUTO_C, PRODUTO_E))
    assert confirmados == [PRODUTO_A, PRODUTO_C, PRODUTO_E]
    assert app.ja_curtidos == {PRODUTO_A, PRODUTO_C, PRODUTO_E} and RECOMENDADO not in app.toques
    # O botão uma vez (a lista ficou aberta) e um arrasto devagar até o último, o 5º.
    assert app.toques_no_ver_mais == 1 and app.arrastos == 1
    assert [n for n in app.toques if isinstance(n, str) and not n.startswith("@")] == [
        PRODUTO_A, PRODUTO_B, "Ver Mais (3)", PRODUTO_C, PRODUTO_D, PRODUTO_E]
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DO_VER_MAIS, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in registro] == [
        ("lidos", "5 cartão(ões) aberto(s); o Ver Mais escondia 3, tocado 1 vez(es); 1 arrasto(s)")]
    assert curtidos == [(robo.NoVerProdutos(n), n) for n in (PRODUTO_A, PRODUTO_C, PRODUTO_E)]
    # No fim do rascunho, cada um é achado de novo pelo cartão, também os do Ver Mais, e descurtido.
    robo.gravar_estado(favoritos_limpos=True)
    robo.descurtir_no_fim(app, {"link": LINK_DE_VIDEO, "de_video": True}, curtidos)
    assert app.curtidos == set() and robo.lista_limpa() and RECOMENDADO not in app.toques


def test_ver_mais_que_fecha_ao_voltar_da_pagina_e_tocado_de_novo(monkeypatch):
    # A lista pode voltar fechada da página do produto: o robô toca no Ver Mais de novo a cada
    # procura do próximo cartão (do 3º ao 5º e na que acha o fim da lista, depois do 5º).
    _fonte_de_video(monkeypatch, confirma=(PRODUTO_B, PRODUTO_D))
    monkeypatch.setattr(robo, "ir_ao_inicio", lambda d: None)
    app = AppDoVerMais(fecha_ao_voltar=True)
    confirmados, curtidos = _produtos_do_ver_mais(app, (PRODUTO_B, PRODUTO_D))
    assert confirmados == [PRODUTO_B, PRODUTO_D] and RECOMENDADO not in app.toques
    assert app.toques_no_ver_mais == 4 and app.arrastos == 2
    robo.descurtir_no_fim(app, {"link": LINK_DE_VIDEO, "de_video": True}, curtidos)
    assert app.curtidos == set()


def test_ver_produtos_que_volta_sem_nada_conhecido_da_lista_para_sem_tocar_nas_recomendacoes(monkeypatch):
    # A lista que volta da página do produto rolada até as recomendações, sem o título, o Ver
    # Mais nem o fim da lista na tela: os cartões podem ser recomendações, e o robô para ali,
    # com os que já conferiu.
    _fonte_de_video(monkeypatch, confirma=(PRODUTO_A, PRODUTO_B, RECOMENDADO))
    app = AppDoVerMais(perdida_depois=2)
    confirmados, _ = _produtos_do_ver_mais(app, (PRODUTO_A, PRODUTO_B))
    assert confirmados == [PRODUTO_A, PRODUTO_B] and RECOMENDADO not in app.toques
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DO_VER_MAIS, "2000-01-01 00:00:00")
    assert [r[2] for r in registro] == ["parou - a lista sem nada conhecido na tela"]


def _do_criador(nome, valor, **campos):
    return {"nome": nome, "link": "", "valor": valor, "trocado": "", "do_video": True, "foto": b"\xff\xd8" + nome.encode(),
            "imagem": "https://cf.shopee.com.br/" + nome[:6], "item": nome[:3], "preco": 50.0, **campos}


def test_ver_produtos_enche_os_espacos_que_sobram_com_o_mesmo_item_de_outras_lojas(monkeypatch):
    # Escolhas do Rafael (28/10, P59 e P66; 05/11, P154 3): depois dos produtos do criador e do Ver
    # Mais, os espaços que sobram, até 6, recebem o mesmo item do 1º produto do post, de outras
    # lojas, pela mesma busca pela foto do link de produto; o post vai do que paga mais por venda
    # para o que paga menos.
    pedidos = []

    def espacos(d, video, principal, original, vistos, prazo, inicio=None, recusados=None, espacos=5):
        pedidos.append((principal, original, espacos))
        return [{"nome": "Igual Loja 3", "link": "https://s.shopee.com.br/3", "valor": 9.0, "foto": b"\xff\xd8c3"},
                {"nome": "Igual Loja 4", "link": "https://s.shopee.com.br/4", "valor": 1.0, "foto": b"\xff\xd8c4"}]

    monkeypatch.setattr(robo, "espacos_livres", espacos)
    monkeypatch.setattr(robo, "_curtir_os_produtos", lambda d, video, produtos, curtidos: [
        p for p in produtos if not curtidos.append((p["link"], p["nome"]))])
    produtos = [_do_criador(PRODUTO_A, 5.0), _do_criador(PRODUTO_B, 3.0)]
    curtidos, variacoes = [], []
    ordem = robo.espacos_do_ver_produtos(None, {"link": LINK_DE_VIDEO, "de_video": True}, produtos, [],
                                         time.monotonic() + 600, time.monotonic(), [], curtidos, variacoes)
    # A busca parte do 1º da mesma cor do vídeo (a foto e o preço do anúncio dele) e enche os 4 que sobram.
    assert pedidos == [({"nome": PRODUTO_A, "item": PRODUTO_A[:3]},
                        {"imagem": "https://cf.shopee.com.br/" + PRODUTO_A[:6], "preco": 50.0}, 4)]
    assert [p["nome"] for p in ordem] == ["Igual Loja 3", PRODUTO_A, PRODUTO_B, "Igual Loja 4"]
    assert curtidos == [("https://s.shopee.com.br/3", "Igual Loja 3"), ("https://s.shopee.com.br/4", "Igual Loja 4")]
    assert produtos[0]["base"] is True and variacoes == []
    # Com os 6 já cheios pelos do criador, nada de busca.
    cheio = [_do_criador(f"Produto {n}", n) for n in range(6)]
    assert robo.espacos_do_ver_produtos(None, {}, cheio, [], 0, 0, [], [], []) == cheio and len(pedidos) == 1


def test_ver_produtos_com_4_pontos_ou_mais_vai_so_com_os_produtos_do_video(monkeypatch):
    # Com 4 pontos de penalidade ou mais, só os produtos do vídeo (P145): os espaços livres do Ver
    # Produtos ficam vazios, como no link de produto, antes de qualquer toque no celular.
    robo.gravar_estado(saude_pontos=8, saude_lida_em=datetime.now(robo.fuso_horario).strftime("%Y-%m-%d %H:%M:%S"))
    produtos = [_do_criador(PRODUTO_A, 5.0)]
    assert robo.espacos_do_ver_produtos(None, {"link": LINK_DE_VIDEO}, produtos, [], time.monotonic() + 600,
                                        time.monotonic(), [], [], []) == produtos
    assert _registro_dos_espacos() == ["nenhum - só o produto do vídeo pelos pontos"]


def test_rascunho_de_ver_produtos_com_produto_a_mais_leva_o_album_e_a_medicao(monkeypatch, avisos):
    # O rascunho de Ver Produtos com produto a mais vai como o de link de produto: o álbum das
    # capas (P75), a marca do a mais com outra foto de capa (P102), os números da medição (P73) e
    # o link curto de cada um (P83).
    _fonte_de_video(monkeypatch)
    extra = {"nome": "Garrafa Térmica Inox Loja Três", "link": "https://s.shopee.com.br/3", "valor": 1.0,
             "item": "33", "foto": b"\xff\xd8outra foto"}

    def espacos(d, video, principal, original, vistos, prazo, inicio=None, recusados=None, espacos=5):
        recusados.append(b"\xff\xd8recusado")
        return [extra]

    anexar = {}

    def anexar_os(d, video, nomes, a_mais=(), limpa=False, prazo=None, curtidos_de_fora=0):
        anexar.update(nomes=list(nomes), a_mais=set(a_mais))
        return list(nomes), list(range(len(nomes)))

    monkeypatch.setattr(robo, "trocar_os_do_ver_produtos", lambda d, video, nomes, *a, **k: [
        _do_criador(nome, 5.0 - n) for n, nome in enumerate(nomes)])
    monkeypatch.setattr(robo, "espacos_livres", espacos)
    monkeypatch.setattr(robo, "_curtir_os_produtos", lambda d, video, produtos, curtidos: list(produtos))
    monkeypatch.setattr(robo, "foto_do_anuncio", lambda endereco: b"\xff\xd8capa do anuncio")
    monkeypatch.setattr(robo, "mesma_foto", lambda uma, outra: uma == outra)
    monkeypatch.setattr(robo, "anexar_os_produtos", anexar_os)
    monkeypatch.setattr(robo.ps, "conferir_tela_final", lambda d, video: (True, "conferida"))
    _copia_com_a_miniatura(monkeypatch)
    assert robo.rodada(preparar=True, d=AppDoVerProdutos(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert anexar == {"nomes": [PRODUTO_A, PRODUTO_B, extra["nome"]], "a_mais": {2}}
    rascunho = robo.pegar(1)
    assert rascunho["itens"] == [{"item": PRODUTO_A[:3], "a_mais": False}, {"item": PRODUTO_B[:3], "a_mais": False},
                                 {"item": "33", "a_mais": True}]
    assert len(rascunho["capas"]) == 3 and rascunho["outras_capas"] == [3] and len(rascunho["recusadas"]) == 1
    assert rascunho["links_dos_produtos"][2] == "https://s.shopee.com.br/3"
    assert "(os do vídeo e 1 iguais de outras lojas)" in avisos[-1]


def test_ver_produtos_de_outra_cor_entra_e_a_foto_dele_vai_na_miniatura(monkeypatch, avisos):
    # Pedido do Rafael (01/11): num post de Ver Produtos, um dos produtos da criadora era o mesmo
    # puff em outra cor, e a IA, que conferia só pelo nome, deixou passar sem ninguém saber. Agora
    # ela confere cada produto pela foto da página dele no app: o mesmo modelo em outra cor entra,
    # e a foto dele vai na miniatura que troca, para aparecer no vídeo; outro produto fica de fora.
    import io
    from PIL import Image
    # A outra cor está desligada desde a P142 1 (03/11): o caminho fica testado para quando voltar.
    monkeypatch.setattr(robo, "OUTRA_COR_NOS_PRODUTOS", True)
    _fonte_de_video(monkeypatch, outra_cor=(PRODUTO_A,))
    edicao = _copia_com_a_miniatura(monkeypatch)
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
    # A foto dele está na miniatura do vídeo: ele vai no post, marcado para o Rafael conferir.
    assert robo.pegar(1)["outra_cor"] == [2]
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_OUTRA_COR, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in registro] == [("no post", "a foto na miniatura")]


def _copia_com_a_miniatura(monkeypatch, com_miniatura=True):
    """A edição de mentira: guarda os nomes e as outras fotos e diz as fotos da miniatura que troca."""
    edicao = {}

    def copiar(video, fonte, copia, nomes=(), alcool=False, outras=(), miniatura=None, rotulo_de_ia=False,
               link_do_1o=None, **_opcoes):
        edicao.update(nomes=list(nomes), outras=list(outras))
        if com_miniatura and miniatura is not None:
            miniatura["fotos"] = [b"\xff\xd8primeira"] + list(outras)
        robo.shutil.copyfile(video["arquivo"], copia)
        return ""

    monkeypatch.setattr(robo, "copiar_para_o_rascunho", copiar)
    return edicao


def test_ver_produtos_de_outra_cor_sem_a_nossa_miniatura_fica_de_fora(monkeypatch, avisos):
    # O de outra cor só vai com a foto na miniatura que troca, que o mostra no vídeo (pedido do
    # Rafael de 01/11: "desde que pelo menos entre na miniatura"). Sem a nossa miniatura (o canto
    # do criador, P81), ele sai antes de anexar, e o anexar procura o outro abaixo dele, que
    # continua curtido no alto da lista até o descurtir do fim.
    monkeypatch.setattr(robo, "OUTRA_COR_NOS_PRODUTOS", True)
    _fonte_de_video(monkeypatch, outra_cor=(PRODUTO_A,))
    _copia_com_a_miniatura(monkeypatch, com_miniatura=False)
    app = AppDoVerProdutos()
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.anexados == [PRODUTO_B] and robo.pegar(1)["outra_cor"] == []
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_OUTRA_COR, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in registro] == [("de fora", "sem a nossa miniatura")]


def test_ver_produtos_de_outra_cor_fica_de_fora(monkeypatch, avisos):
    # Vídeo do Rafael das 07:20 de 03/11: um post com o produto do vídeo e 2 do mesmo modelo em
    # outra cor foi punido como Produto Irrelevante. Escolha dele (P142 1): nunca outra cor, no Ver
    # Produtos e nos produtos a mais; o produto da criadora em outra cor fica de fora, sem curtir.
    assert robo.OUTRA_COR_NOS_PRODUTOS is False
    _fonte_de_video(monkeypatch, outra_cor=(PRODUTO_A,))
    edicao = _copia_com_a_miniatura(monkeypatch)
    app = AppDoVerProdutos()
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.anexados == [PRODUTO_B] and edicao["nomes"] == [PRODUTO_B] and edicao["outras"] == []
    assert robo.pegar(1)["outra_cor"] == []
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DO_CRIADOR, "2000-01-01 00:00:00")
    assert sorted(r[2] for r in registro) == ["de fora - outra cor", "mesmo produto"]


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

    async def buscar(termo, limite=10, sort_type=2, negada_levanta=False):
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

    async def buscar_os_dois(termo, limite=10, sort_type=2, negada_levanta=False):
        return [{"itemId": 7, "productName": cortina_a, "productLink": "https://shopee.com.br/product/1/7"}, outra]

    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", buscar_os_dois)
    assert robo.links_do_ver_produtos([cortina_b, cortina_a]) == [
        "https://s.shopee.com.br/curto-8", "https://s.shopee.com.br/curto-7"]

    # A API fora: o rascunho sai, sem os links (o Rafael confere pelo vídeo original).
    async def fora(termo, limite=10, sort_type=2, negada_levanta=False):
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

    async def buscar(termo, limite=10, sort_type=2, negada_levanta=False):
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

    async def buscar(termo, limite=10, sort_type=2, negada_levanta=False):
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


def test_link_de_video_em_analise_diz_que_o_video_esta_em_analise(monkeypatch, avisos):
    # Preparar 1 Agora das 18:16 e das 18:33 de 02/11: o link abriu o aviso "Vídeo em Análise" da
    # Shopee, e o motivo dizia que o link não abriu o vídeo no app. O robô não espera o Ver Produtos
    # que não vem: uma olhada só, mais a do caso guardado.
    _fonte_de_video(monkeypatch)
    app = AppDoVerProdutos(player="em_analise")
    resultado = robo.rodada(preparar=True, d=app, agora=momento("2026-11-02 18:16"))
    assert robo.MOTIVO_EM_ANALISE in resultado and "não abriu o vídeo" not in resultado
    assert app.olhadas_no_player == 2
    pulado = robo.listar("pulado")[0]
    assert pulado["motivo"] == robo.MOTIVO_EM_ANALISE and pulado["id_video"] == "a1"
    assert robo.passo_do_motivo(robo.MOTIVO_EM_ANALISE) == "vídeo em análise"
    assert any(robo.MOTIVO_EM_ANALISE in aviso for aviso in avisos)
    import investigar_robo
    assert robo.MOTIVO_EM_ANALISE in investigar_robo.textos_fixos()


class AppDeVariosVideos(AppDoVerProdutos):
    """O AppDoVerProdutos em que cada link aberto mostra o player do modo seguinte da lista."""

    def __init__(self, modos):
        super().__init__()
        self.modos = list(modos)

    def shell(self, partes):
        if "android.intent.action.VIEW" in partes and self.modos:
            self.player = self.modos.pop(0)
        return super().shell(partes)


def _mais_videos_de_video(*idents):
    """Mais vídeos de link de vídeo na fonte (os Autorais), cada um mais velho que o anterior."""
    for i, ident in enumerate(idents, start=1):
        with open(f"archive/{ident}.mp4", "wb") as f:
            f.write(b"video")
        inserir("INSERT INTO fila_autorais VALUES (?, ?, ?, ?)", ident, f"archive/{ident}.mp4",
                f"Garrafa 🧴\n{LINK_DE_VIDEO}", f"2026-10-21 0{9 - i}:00:00")


def test_preparar_1_agora_passa_sozinho_ao_proximo_video(monkeypatch, avisos):
    # Escolha do Rafael (02/11, P133): às 18:16, 18:25 e 18:33 foram 3 toques e nenhum rascunho, um
    # vídeo por toque. O vídeo com problema próprio fica de lado, com o aviso, e o mesmo toque passa
    # ao próximo vídeo.
    _fonte_de_video(monkeypatch)
    _mais_videos_de_video("a2")
    app = AppDeVariosVideos(["em_analise", "normal"])
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-11-02 18:16")) == "rascunho salvo"
    assert [p["id_video"] for p in robo.listar("pulado")] == ["a1"]
    assert robo.esperando_aprovacao()[0]["id_video"] == "a2"
    de_lado = [a for a in avisos if isinstance(a, str) and "Vou para o próximo vídeo" in a]
    assert len(de_lado) == 1 and "o vídeo 1 de 3" in de_lado[0] and robo.MOTIVO_EM_ANALISE in de_lado[0]
    assert not any(isinstance(a, str) and "não preparei" in a for a in avisos)


def test_preparar_1_agora_desiste_depois_de_3_videos(monkeypatch, avisos):
    _fonte_de_video(monkeypatch)
    _mais_videos_de_video("a2", "a3", "a4")
    app = AppDeVariosVideos(["em_analise", "em_analise", "em_analise", "normal"])
    resultado = robo.rodada(preparar=True, d=app, agora=momento("2026-11-02 18:16"))
    assert "o vídeo 3 de 3 também ficou de lado" in resultado and robo.MOTIVO_EM_ANALISE in resultado
    assert sorted(p["id_video"] for p in robo.listar("pulado")) == ["a1", "a2", "a3"]
    assert not robo.esperando_aprovacao()
    assert sum(1 for a in avisos if isinstance(a, str) and "Vou para o próximo vídeo" in a) == 2
    assert any(isinstance(a, str) and "não preparei o rascunho que você pediu" in a and "3 de 3" in a for a in avisos)


def test_preparar_1_agora_para_tudo_no_que_nao_e_do_video(monkeypatch, avisos):
    # O que não é do próprio vídeo (o celular, o app) para o pedido na hora, como antes.
    vezes = []

    def preparar(d, config, agora=None):
        vezes.append(1)
        raise robo.Parada("o app não abriu a galeria")

    monkeypatch.setattr(robo, "preparar_rascunho", preparar)
    with pytest.raises(robo.Parada):
        robo.preparar_o_pedido(None, {})
    assert len(vezes) == 1 and not avisos


def test_preparar_1_agora_so_passa_ao_proximo_com_tempo_na_rodada(monkeypatch, avisos):
    # O painel interrompe a rodada em 30 min, e um rascunho leva até uns 25: o vídeo que fica de
    # lado depois de 5 min não ganha o próximo nesta rodada, e o aviso diz para tocar de novo.
    relogio = iter([0, robo.MAXIMO_DA_RODADA - robo.MINUTOS_DE_UM_RASCUNHO * 60 + 1])
    monkeypatch.setattr(robo.time, "monotonic", lambda: next(relogio))
    vezes = []

    def preparar(d, config, agora=None):
        vezes.append(1)
        raise robo.Parada(robo.MOTIVO_EM_ANALISE, do_video=True)

    monkeypatch.setattr(robo, "preparar_rascunho", preparar)
    with pytest.raises(robo.Parada) as erro:
        robo.preparar_o_pedido(None, {})
    assert len(vezes) == 1 and "toque de novo em Preparar 1 Agora" in erro.value.motivo
    assert "o vídeo 1 de 3 ficou de lado" in erro.value.motivo and not avisos


def _relogio_da_rodada(monkeypatch, *segundos):
    """time.monotonic() dando estes valores, um por chamada, e depois o último."""
    valores = list(segundos)
    monkeypatch.setattr(robo.time, "monotonic", lambda: valores.pop(0) if len(valores) > 1 else valores[0])


def _linhas_do_botao():
    return [(r[2], r[3]) for r in robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DO_BOTAO,
                                                                     "2000-01-01 00:00:00")]


def test_preparar_1_agora_sem_os_a_mais_conta_o_rascunho_pelo_tempo_medido(monkeypatch, avisos):
    # No Preparar 1 Agora das 16:40 de 07/11, o 1º vídeo ficou de lado aos 7 min da rodada, e o robô
    # não tentou o 2º: contava 25 min para um rascunho. Sem os produtos a mais (8 pontos, P145), os
    # rascunhos levam de 5 a 15 min (registro "tempo do rascunho"): aos 7 min ainda cabe outro vídeo
    # quando a parada é do vídeo (aqui, a IA viu outro produto nele).
    robo.gravar_estado(saude_pontos=8, saude_lida_em=datetime.now(robo.fuso_horario).strftime("%Y-%m-%d %H:%M:%S"))
    assert robo.minutos_de_um_rascunho() == robo.MINUTOS_DE_UM_RASCUNHO_SEM_OS_A_MAIS == 15
    _relogio_da_rodada(monkeypatch, 0, 7 * 60)
    monkeypatch.setattr(robo, "proximo_video", lambda *a, **k: {"id": "a2"})
    vezes = []

    def preparar(d, config, agora=None):
        vezes.append(1)
        if len(vezes) == 1:
            raise robo.Parada(robo.ps.MOTIVO_OUTRO_PRODUTO, do_video=True)
        return "rascunho salvo"

    monkeypatch.setattr(robo, "preparar_rascunho", preparar)
    assert robo.preparar_o_pedido(None, robo.ler_config()) == "rascunho salvo"
    assert len(vezes) == 2
    assert sum(1 for a in avisos if isinstance(a, str) and "Vou para o próximo vídeo" in a) == 1
    assert _linhas_do_botao() == [("próximo vídeo", "o 2º, aos 7,0 min da rodada")]


def test_preparar_1_agora_com_os_a_mais_ainda_conta_25_min(monkeypatch, avisos):
    # Com os produtos a mais (menos de 4 pontos), o rascunho pode levar até uns 25 min: aos 7 min da
    # rodada não cabe outro, e o registro diz em que minuto parou.
    assert robo.sem_os_a_mais() is None and robo.minutos_de_um_rascunho() == robo.MINUTOS_DE_UM_RASCUNHO == 25
    _relogio_da_rodada(monkeypatch, 0, 7 * 60)

    def preparar(d, config, agora=None):
        raise robo.Parada(robo.ps.MOTIVO_OUTRO_PRODUTO, do_video=True)

    monkeypatch.setattr(robo, "preparar_rascunho", preparar)
    with pytest.raises(robo.Parada) as erro:
        robo.preparar_o_pedido(None, robo.ler_config())
    assert "não há tempo para outro vídeo nesta rodada" in erro.value.motivo and not avisos
    assert _linhas_do_botao() == [("sem tempo para outro vídeo", "aos 7,0 min da rodada; um rascunho leva até 25 min")]


def test_preparar_1_agora_conta_o_tempo_desde_o_comeco_da_rodada(monkeypatch, avisos):
    # O painel interrompe a rodada em 30 min contados do começo dela, não do começo do pedido: com
    # 11 min gastos antes (a volta do celular, a trava), o vídeo que fica de lado 5 min depois deixa
    # só 14 min, e o rascunho sem os produtos a mais leva até 15.
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.ler_config(), "robo_produtos_a_mais": False})
    assert robo.sem_os_a_mais() == ("nenhum - desligados", "")
    _relogio_da_rodada(monkeypatch, 16 * 60)

    def preparar(d, config, agora=None):
        raise robo.Parada(robo.MOTIVO_EM_ANALISE, do_video=True)

    monkeypatch.setattr(robo, "preparar_rascunho", preparar)
    with pytest.raises(robo.Parada) as erro:
        robo.preparar_o_pedido(None, robo.ler_config(), comeco=0)
    assert "toque de novo em Preparar 1 Agora" in erro.value.motivo
    assert _linhas_do_botao() == [("sem tempo para outro vídeo", "aos 16,0 min da rodada; um rascunho leva até 15 min")]


def test_rodada_passa_o_comeco_dela_ao_preparar_1_agora(monkeypatch):
    vistos = []
    monkeypatch.setattr(robo, "_agir", lambda d, acao, ident, preparar, config, agora, pedido=False, comeco=None:
                        vistos.append(comeco) or "rascunho salvo")
    antes = time.monotonic()
    assert robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-11-07 16:39")) == "rascunho salvo"
    assert len(vistos) == 1 and vistos[0] is not None and antes <= vistos[0] <= time.monotonic()


def test_preparar_1_agora_sem_outro_video_na_fonte_diz_o_motivo_do_que_ficou_de_lado(monkeypatch, avisos):
    # Com um vídeo só na fonte, o motivo dele vai na resposta (e não "nenhum vídeo da fonte").
    _fonte_de_video(monkeypatch)
    resultado = robo.rodada(preparar=True, d=AppDoVerProdutos(player="em_analise"), agora=momento("2026-11-02 18:16"))
    assert robo.MOTIVO_EM_ANALISE in resultado and "a fonte não tem outro vídeo para tentar" in resultado
    assert not any(isinstance(a, str) and "Vou para o próximo vídeo" in a for a in avisos)


def test_video_em_analise_fica_de_lado_so_no_dia(monkeypatch, avisos):
    # Escolha do Rafael (02/11, P134): o vídeo em análise na Shopee (o criador acabou de postar) não
    # fica de lado para sempre, como o removido: no dia seguinte volta a ser candidato.
    _fonte_de_video(monkeypatch)
    config = robo.ler_config()
    robo.rodada(preparar=True, d=AppDeVariosVideos(["em_analise"] * 3), agora=momento("2026-11-02 18:16"))
    assert robo.listar("pulado")[0]["motivo"] == robo.MOTIVO_EM_ANALISE
    assert "a1" in robo.ids_usados(momento("2026-11-02 23:59"))
    assert robo.proximo_video(config, agora=momento("2026-11-02 23:59")) is None
    assert "a1" not in robo.ids_usados(momento("2026-11-03 00:01"))
    assert robo.proximo_video(config, agora=momento("2026-11-03 00:01"))["id"] == "a1"
    # Já liberado, vira rascunho no dia seguinte.
    assert robo.rodada(preparar=True, d=AppDoVerProdutos(), agora=momento("2026-11-03 10:00")) == "rascunho salvo"
    assert robo.esperando_aprovacao()[0]["id_video"] == "a1"
    assert "a1" in robo.ids_usados(momento("2026-11-04 10:00"))


def test_video_removido_continua_de_lado_para_sempre(monkeypatch, avisos):
    _fonte_de_video(monkeypatch)
    robo.rodada(preparar=True, d=AppDoVerProdutos(removido=True), agora=momento("2026-11-02 18:16"))
    assert "a1" in robo.ids_usados(momento("2026-11-10 10:00"))


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
                "modelo.")
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
    monkeypatch.setattr(robo, "limpeza_fora_da_hora_pendente", lambda agora=None: False)
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

    def anotados(processo="descurtir tudo (4h)"):
        return consultar("SELECT COUNT(*), MIN(resultado), MAX(ok) FROM registro_processos "
                         "WHERE processo = ?", processo)
    for hora in ("04:05", "04:20", "04:35"):
        assert "celular fora (esperado)" in robo.rodada(agora=momento(f"2026-10-26 {hora}"))
    assert anotados() == (1, "celular fora na suspensão", None)
    # Checkup de 04/11: a limpeza de Meus Favoritos (comprador), que vem junto, também anota o porquê.
    assert anotados(robo.PROCESSO_DE_COMPRADOR) == (1, "celular fora na suspensão", None)
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
    # A edição sabe que o vídeo vai com o rótulo (a moldura sobe com o cartão do app, 03/11).
    pedidos, copiar = [], robo.copiar_para_o_rascunho

    def copiar_para_o_rascunho(*args, **opcoes):
        pedidos.append(opcoes.get("rotulo_de_ia"))
        return copiar(*args, **opcoes)
    monkeypatch.setattr(robo, "copiar_para_o_rascunho", copiar_para_o_rascunho)
    app = ComRotuloDeIA()
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert pedidos == [True]
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


class PerfilSemOCentroAinda(AppDaSaude):
    """O Perfil que mostra o alto (os números e o Postar vídeo) antes do Centro do criador, que vem pela rede."""

    def __init__(self, leituras_sem_o_centro):
        super().__init__()
        self.sem_o_centro = leituras_sem_o_centro

    def _nos(self):
        nos = super()._nos()
        if self.atual == "perfil" and self.sem_o_centro > 0:
            self.sem_o_centro -= 1
            return [no for no in nos if 'text="Centro do criador"' not in no]
        return nos


def test_saude_espera_o_centro_do_criador_que_chega_depois_do_alto_do_perfil():
    # 13/11, 00:28: o Perfil em Shopee Vídeo abriu (os números e o Postar vídeo na tela), mas o
    # Centro do criador ainda não estava lá, e a leitura da Saúde parou na 1ª leitura. O robô
    # relê a tela até ele chegar; sem ele de jeito nenhum, para como antes.
    app = PerfilSemOCentroAinda(3)
    robo.abrir_saude(app)
    assert app.atual == "saude" and "Centro do criador" in app.toques
    with pytest.raises(robo.Parada, match="não achei Centro do criador na tela"):
        robo.abrir_saude(PerfilSemOCentroAinda(50))


# O Centro do criador e a Saúde do Vídeo do app de agora (vídeo do Rafael de 04/11/2026): o
# Creator Center sem o quadro, com "Ao vivo: ..." e "Vídeo: ..." no alto, e a Account Health
# com as abas Live e Vídeo (a Live com os pontos das lives).
ENTRADA_NOVA = "Vídeo: Precisa melhorar"
PONTOS_DA_SAUDE_NOVA = _no("8", caixa=(510, 690, 570, 750), clicavel=False)
TELAS_DA_SAUDE_NOVA = {
    "centro": [_no("Creator Center", caixa=(160, 90, 600, 150), clicavel=False),
               _no("Ao vivo: Excelente", caixa=(150, 200, 420, 240)),
               _no(ENTRADA_NOVA, caixa=(440, 200, 760, 240)),
               _no("Dados dos Últimos 7 Dias", caixa=(60, 600, 600, 650), clicavel=False),
               _no("Ao vivo", caixa=(60, 680, 220, 730)), _no("Vídeo", caixa=(240, 680, 400, 730))],
    "saude_live": [_no("Account Health", caixa=(160, 90, 600, 150), clicavel=False),
                   _no("Live", caixa=(100, 180, 400, 240)), _no("Vídeo", caixa=(560, 180, 900, 240)),
                   _no("Status de Saúde da Live", caixa=(60, 280, 700, 320), clicavel=False),
                   _no("Ponto de Penalidade", caixa=(380, 520, 700, 560), clicavel=False),
                   _no("0", caixa=(510, 580, 570, 640), clicavel=False),
                   _no("Lives com Violação", caixa=(60, 1500, 700, 1540), clicavel=False)],
    "saude": ([_no("Account Health", caixa=(160, 90, 600, 150), clicavel=False),
               _no("Live", caixa=(100, 180, 400, 240)), _no("Vídeo", caixa=(560, 180, 900, 240)),
               _no("Banido Temporariamente", caixa=(400, 280, 760, 320), clicavel=False),
               _no(SAUDE_BANIDO, caixa=(60, 340, 1020, 420), clicavel=False),
               _no("Status da Saúde do Vídeo", caixa=(60, 460, 700, 500), clicavel=False),
               _no("Ponto de Penalidade", caixa=(380, 630, 700, 670), clicavel=False),
               PONTOS_DA_SAUDE_NOVA,
               _no("Vídeos de Violação", caixa=(60, 1300, 700, 1340), clicavel=False)]
              + _punicao_na_lista("Produto Irrelevante", "23/10/2026 19:04:25", "Não Recorrido", 1400)
              + _punicao_na_lista("Contrafeito", "06/10/2026 22:44:53", "Bem-sucedido", 1560)
              + _punicao_na_lista("Violação de Propriedade Intelectual", "18/10/2026 20:20:56", "Não Recorrido", 1720)),
}


class AppDaSaudeNova(AppDaSaude):
    """O app de mentira com o Creator Center e a Account Health (o app de 04/11/2026)."""

    def __init__(self, abre_na_live=False):
        super().__init__()
        self.CAMINHO = {**{chave: tela for chave, tela in AppDaSaude.CAMINHO.items() if chave[0] != "centro"},
                        ("centro", ENTRADA_NOVA): "saude_live" if abre_na_live else "saude",
                        ("saude_live", "Vídeo"): "saude"}

    def _nos(self):
        return TELAS_DA_SAUDE_NOVA.get(self.atual) or super()._nos()


class SaudeCarregando(AppDaSaude):
    """A Saúde do Vídeo (a de antes) que mostra os títulos antes do número e da lista, pela rede."""

    def __init__(self, leituras_pela_metade):
        super().__init__()
        self.pela_metade = leituras_pela_metade

    def _nos(self):
        nos = super()._nos()
        if self.atual == "saude" and self.pela_metade > 0:
            self.pela_metade -= 1
            return [n for n in nos if '"Saúde do Vídeo"' in n or '"Vídeos de Violação"' in n]
        return nos


def test_saude_no_app_de_agora_pelo_creator_center_e_a_aba_video(avisos, ia_da_apelacao):
    # Vídeo do Rafael de 04/11/2026: o Centro do criador virou Creator Center, sem o quadro, e o
    # "Vídeo: ..." do alto abre a Account Health; os pontos e a lista são os da aba Vídeo.
    _postado_pelo_robo()
    app = AppDaSaudeNova()
    assert robo.rodada(saude=True, d=app, agora=momento("2026-10-24 10:00")) == (
        "saúde lida: 3 punição(ões) em 30 dias, 2 nova(s)")
    assert app.toques.index("Centro do criador") < app.toques.index(ENTRADA_NOVA)
    assert robo.ler_estado()["saude_pontos"] == 8 and "Pontos de penalidade: 8" in avisos[-1]
    assert robo.ler_config()["robo_suspenso_ate"] == "2026-10-26 19:04:26"
    # Aberta na aba Live, o robô troca para a aba Vídeo: os pontos das lives (0) não contam.
    robo.gravar_estado(saude_pontos=None)
    na_live = AppDaSaudeNova(abre_na_live=True)
    robo.rodada(saude=True, d=na_live, agora=momento("2026-10-24 11:00"))
    assert na_live.toques.index(ENTRADA_NOVA) < na_live.toques.index("Vídeo")
    assert robo.ler_estado()["saude_pontos"] == 8
    # Com as duas seções na mesma tela, o número é o da seção do vídeo.
    duas = _xml(*TELAS_DA_SAUDE_NOVA["saude_live"][3:], *TELAS_DA_SAUDE_NOVA["saude"][3:])
    assert robo.pontos_de_penalidade(duas) == 8
    assert robo.pontos_de_penalidade(_xml(*TELAS_DA_SAUDE_NOVA["saude_live"])) == 0


def test_saude_espera_o_numero_e_pela_metade_nao_tira_conclusao(avisos, ia_da_apelacao):
    # A página carrega os títulos antes do número e da lista: o robô espera o número.
    _postado_pelo_robo()
    agora = momento("2026-10-24 10:00")
    robo.rodada(saude=True, d=SaudeCarregando(4), agora=agora)
    estado = robo.ler_estado()
    assert estado["saude_pontos"] == 6 and estado["saude_lida_em"] == "2026-10-24 10:00:00"
    pendentes = [p for p in robo.apelacoes.todas() if p["situacao"] == "pendente"]
    assert len(pendentes) == 2
    # Sem o número até o fim da espera, nada da página vale: os pontos da última leitura ficam
    # (nunca 0), a punição que não apareceu não vira recurso aceito, e a suspensão não acaba.
    avisos.clear()
    depois = momento("2026-10-24 16:00")
    resultado = robo.rodada(saude=True, d=SaudeCarregando(99), agora=depois)
    assert robo.MOTIVO_SEM_OS_PONTOS in resultado
    estado = robo.ler_estado()
    assert estado["saude_pontos"] == 6 and estado["saude_lida_em"] == "2026-10-24 10:00:00"
    assert robo.apelacoes.pontos_de_agora(agora=depois) == 6
    assert [p["situacao"] for p in robo.apelacoes.todas() if p["situacao"] == "pendente"] == ["pendente"] * 2
    assert not any("deu certo" in a for a in avisos)
    assert robo.ler_config()["robo_suspenso_ate"] == "2026-10-26 19:04:26"
    assert robo.passo_do_motivo(robo.MOTIVO_SEM_OS_PONTOS) == "ler os pontos de penalidade"


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
    recusado = next(a for a in avisos if "não aceitou o recurso" in a)
    # O vídeo do produto irrelevante pode ser apagado já, com o pedido da gravação (pedido do
    # Rafael, 09/11: até o robô aprender a apagar, P183 2).
    assert "pode apagar agora" in recusado and ap.PEDIDO_DA_GRAVACAO in recusado
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
    marcar tudo, o "Selecionado N/50", o Like (tira os marcados) e o Compartilhar.
    marcar_tudo=False: a caixa de baixo não marca nada, e o robô marca um por um, rolando.
    invalidos: as posições dos produtos que saíram da loja, com o selo Inválido na foto, que o
    Like não tira e que continuam marcados depois dele (Motorola, 29/10/2026). Na linha dos
    filtros há também o filtro Inválido.
    E o Meus Favoritos de comprador da aba Eu (Motorola, 02/11/2026, P137): a Visualização do
    Comprador, com o Editar (o app guarda a edição aberta: editando), o carrinho no alto e em cada
    produto fora da edição (nunca tocar), e, na edição, o Feito, a caixa de marcar tudo, o
    "Selecionado N/50" e o Remover dos Favoritos, que pergunta (Não/Sim). comprador: quantos
    estão lá; remover_pega=False: o Sim não tira nada.
    """

    def __init__(self, favoritos=6, marcar_tudo=True, invalidos=(), comprador=0, editando=False, remover_pega=True):
        super().__init__()
        self.favoritos = [f"Produto {i}" for i in range(favoritos)]
        self.invalidos = {f"Produto {i}" for i in invalidos}
        self.marcados, self.marcar_tudo, self.topo = [], marcar_tudo, 0
        self.comprador = [f"Item {i}" for i in range(comprador)]
        self.editando, self.remover_pega, self.pergunta, self.marcados_de_comprador = editando, remover_pega, False, []

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
        if self.atual == "comprador":
            return self._nos_de_comprador()
        return super()._nos()

    # O carrinho do alto e o de cada produto, fora da edição (sem texto, como no Motorola).
    CARRINHO_DO_ALTO = (818, 137, 923, 242)

    def _carrinho_do_produto(self, i):
        y = 421 + 850 * (i // 2)
        x = 22 + 529 * (i % 2)
        return (x + 392, y + 724, x + 476, y + 808)

    def _nos_de_comprador(self):
        if self.pergunta:
            # Como no Motorola: com a pergunta aberta, a leitura da tela só traz ela.
            return [_no("Você deseja remover os itens selecionados dos Meus Favoritos?", ident="content",
                        caixa=(123, 1136, 978, 1238), clicavel=False),
                    _no("Não", ident="buttonDefaultNegative", caixa=(70, 1304, 538, 1430)),
                    _no("Sim", ident="buttonDefaultPositive", caixa=(541, 1304, 1010, 1430))]
        nos = [_no("Visualização do Comprador", caixa=(126, 158, 731, 221), clicavel=False)]
        visiveis = self.comprador[:4]
        if not self.editando:
            nos += [_no(caixa=(934, 137, 1070, 242), filhos=_no("Editar", caixa=(955, 169, 1049, 211), clicavel=False)),
                    _no(caixa=self.CARRINHO_DO_ALTO, filhos=_no("40", caixa=(882, 150, 908, 182), clicavel=False))]
            for i, nome in enumerate(visiveis):
                y = 421 + 850 * (i // 2)
                x = 22 + 529 * (i % 2)
                nos += [_no(nome, caixa=(x + 21, y + 526, x + 487, y + 600), clicavel=False),
                        _no("Similares", caixa=(x + 206, y + 748, x + 330, y + 785), clicavel=False),
                        _no(caixa=self._carrinho_do_produto(i))]
            return nos
        nos.append(_no(caixa=(951, 137, 1070, 242), filhos=_no("Feito", caixa=(972, 169, 1049, 211), clicavel=False)))
        for i, nome in enumerate(visiveis):
            y = 421 + 850 * (i // 2)
            x = 22 + 529 * (i % 2)
            nos += [_no(nome, caixa=(x + 21, y + 526, x + 487, y + 600), clicavel=False),
                    _no(caixa=(x + 17, y + 756, x + 152, y + 808))]
        nos += [_no(caixa=(32, 2300, 360, 2352),
                    filhos=_no(caixa=(32, 2300, 84, 2352))
                    + _no(f"Selecionado {len(self.marcados_de_comprador)}/50", caixa=(95, 2305, 360, 2347),
                          clicavel=False)),
                _no(caixa=(634, 2279, 1049, 2373),
                    filhos=_no("Remover dos Favoritos", caixa=(666, 2306, 1018, 2348), clicavel=False))]
        return nos

    def _clique_de_comprador(self, x, y, tocados):
        if self.pergunta:
            if "Sim" in tocados:
                if self.remover_pega:
                    self.comprador = [c for c in self.comprador if c not in self.marcados_de_comprador]
                    self.marcados_de_comprador = []
                self.pergunta = False
            elif "Não" in tocados:
                self.pergunta = False
            return
        if not self.editando:
            carrinhos = [self.CARRINHO_DO_ALTO] + [self._carrinho_do_produto(i) for i in range(len(self.comprador[:4]))]
            assert not any(robo.ps._dentro((x, y), c) for c in carrinhos), "tocou no carrinho"
            if "Editar" in tocados:
                self.editando = True
            return
        if "Feito" in tocados:
            self.editando, self.marcados_de_comprador = False, []
        elif 32 <= x <= 84 and 2300 <= y <= 2352:
            self.marcados_de_comprador = [] if self.marcados_de_comprador else self.comprador[:50]
        elif "Remover dos Favoritos" in tocados and self.marcados_de_comprador:
            self.pergunta = True

    def click(self, x, y):
        tocados = {el["texto"] for el in robo.ps.elementos(self.dump_hierarchy()) if robo.ps._dentro((x, y), el["caixa"])}
        assert not tocados & {"Compartilhar", "Substituir Tudo"}, f"tocou em {tocados}"
        if self.atual == "inicio" and "Eu" in tocados:
            self.atual = "eu"
        elif self.atual == "eu" and "Meus Favoritos" in tocados:
            self.atual = "comprador"
        elif self.atual == "comprador":
            self._clique_de_comprador(x, y, tocados)
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
    assert resultado == "6 produto(s) descurtido(s) em Meus favoritos; nada em Meus Favoritos de comprador"
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
    assert robo.rodada(d=app, agora=momento("2026-10-25 04:20")) == (
        "30 produto(s) descurtido(s) em Meus favoritos; nada em Meus Favoritos de comprador")
    assert app.favoritos == [] and robo.o_que_fazer(robo.ler_config(), momento("2026-10-25 04:35")) is None


def test_sem_a_caixa_de_marcar_tudo_marca_um_por_um_rolando(monkeypatch, avisos):
    # Como o Rafael fez no vídeo: marcando produto por produto, rolando a lista.
    ativar(robo_inicio=8, robo_fim=22)
    app = AppDosFavoritos(favoritos=12, marcar_tudo=False)
    assert robo.rodada(d=app, agora=momento("2026-10-25 04:05")) == (
        "12 produto(s) descurtido(s) em Meus favoritos; nada em Meus Favoritos de comprador")
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
        "nada curtido em Meus favoritos; nada em Meus Favoritos de comprador")
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
                         "(o Like não tira produto que saiu da loja); nada em Meus Favoritos de comprador")
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
    # Antes de parar, abriu a lista de novo uma vez (a tela podia estar velha).
    assert app.toques.count("Meus favoritos") == 2


class ListaVelhaDepoisDoLike(AppDosFavoritos):
    """
    Meus favoritos como o Motorola mostrou em 13/11 às 04:13: o Like tira os marcados da lista
    guardada e limpa a marcação, mas a lista da tela continua a mesma até ser aberta de novo; a
    caixa de baixo marca os da tela, e o Like nos que já saíram não faz nada (continuam marcados).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.na_tela = None

    def _visiveis(self):
        lista = self.favoritos if self.na_tela is None else self.na_tela
        return lista[self.topo:self.topo + 5]

    def click(self, x, y):
        tocados = {el["texto"] for el in robo.ps.elementos(self.dump_hierarchy()) if robo.ps._dentro((x, y), el["caixa"])}
        if self.atual == "afiliado" and "Meus favoritos" in tocados:
            super().click(x, y)
            self.na_tela = list(self.favoritos)
            return
        if self.atual == "favoritos" and 30 <= x <= 96 and 2290 <= y <= 2356:
            self.marcados = list(self._visiveis())
            self.toques.append((x, y))
            return
        if self.atual == "favoritos" and "Like" in tocados:
            tirados = [f for f in self.marcados if f in self.favoritos and f not in self.invalidos]
            if tirados:
                self.favoritos = [f for f in self.favoritos if f not in tirados]
                self.marcados = [f for f in self.marcados if f in self.invalidos]
            self.toques.append("Like")
            return
        return super().click(x, y)


def _registro_da_limpeza():
    with robo.db.conexao() as con:
        return [tuple(linha) for linha in con.execute(
            "SELECT resultado, detalhe FROM registro_processos WHERE processo = 'descurtir tudo (4h)' ORDER BY id")]


def test_lista_velha_depois_do_like_e_aberta_de_novo_antes_de_parar(monkeypatch, avisos):
    # 13/11, 04:13: o 1º Like tirou os 2 produtos de Meus favoritos e limpou a marcação, mas a tela
    # continuou com eles; o robô os marcou de novo, o 2º Like não fez nada, e a limpeza parou ("os
    # produtos marcados continuaram"). Na rodada seguinte, a lista aberta de novo só tinha 1
    # inválido. Antes de dar por parada, o robô abre a lista de novo uma vez.
    ativar(robo_inicio=8, robo_fim=22)
    app = ListaVelhaDepoisDoLike(favoritos=2)
    resultado = robo.rodada(d=app, agora=momento("2026-11-13 04:12"))
    assert resultado.startswith("2 produto(s) descurtido(s) em Meus favoritos") and "continuaram" not in resultado
    assert app.favoritos == [] and robo.lista_limpa() and app.toques.count("Meus favoritos") == 2
    assert _registro_da_limpeza()[-1] == ("descurtido", "2 produto(s); a lista aberta de novo")
    # Sobrando só o inválido na lista aberta de novo, a lista acabou, como na rodada das 04:27.
    robo.gravar_estado(favoritos_limpos=False, descurtir_em=None, descurtir_continuar=False)
    app = ListaVelhaDepoisDoLike(favoritos=3, invalidos=(2,))
    resultado = robo.rodada(d=app, agora=momento("2026-11-14 04:12"))
    assert resultado.startswith("2 produto(s) descurtido(s) em Meus favoritos; 1 inválido(s) ficam")
    assert app.favoritos == ["Produto 2"] and robo.lista_limpa()


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
    _outro_produto(monkeypatch)
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


def test_limpeza_das_4h_que_para_no_meio_tenta_de_novo_na_mesma_hora(monkeypatch, avisos):
    # Vídeo do Rafael das 20:17 de 02/11: a limpeza das 4h parou às 04:14 (o app travado numa
    # página carregando) e só voltaria no dia seguinte, e as curtidas acumularam em Meus
    # favoritos. A que para no meio tenta de novo na rodada seguinte, ainda na hora dela.
    class LikeQueNaoPega(AppDosFavoritos):
        def click(self, x, y):
            if self.atual == "favoritos" and 600 <= x <= 750 and 2290 <= y <= 2356:
                return
            return super().click(x, y)

    ativar(robo_inicio=8, robo_fim=22)
    config = {**robo.PADRAO, "robo_inicio": 8, "robo_fim": 22}
    robo.rodada(d=LikeQueNaoPega(favoritos=3), agora=momento("2026-10-25 04:05"))
    assert robo.o_que_fazer(config, momento("2026-10-25 04:20")) == ("descurtir", None)
    app = AppDosFavoritos(favoritos=3)
    robo.rodada(d=app, agora=momento("2026-10-25 04:20"))
    assert app.favoritos == [] and robo.lista_limpa()
    assert robo.o_que_fazer(config, momento("2026-10-25 04:35")) is None
    # O erro que ninguém previu também tenta de novo na mesma hora.
    monkeypatch.setattr(robo, "descurtir_tudo", lambda d, agora=None: 1 / 0)
    robo.rodada(d=AppDosFavoritos(favoritos=3), agora=momento("2026-10-26 04:05"))
    assert robo.o_que_fazer(config, momento("2026-10-26 04:20")) == ("descurtir", None)
    # Na Verificação da Shopee, o robô para tudo e não tenta de novo.
    robo.gravar_estado(descurtir_continuar=False)

    def verificacao(d, agora=None):
        raise robo.Verificacao()
    monkeypatch.setattr(robo, "descurtir_tudo", verificacao)
    monkeypatch.setattr(robo.av, "abrir_tela", lambda **kwargs: None)
    robo.rodada(d=AppDosFavoritos(favoritos=3), agora=momento("2026-10-27 04:05"))
    assert robo.o_que_fazer(config, momento("2026-10-27 04:20")) is None


def test_limpeza_que_nao_terminou_as_4h_volta_no_mesmo_dia_na_primeira_rodada_livre(monkeypatch, avisos):
    # Escolha do Rafael (02/11, P137 1): a limpeza das 4h que não terminou (o celular fora às 4h,
    # o app travado) roda de novo no mesmo dia, na 1ª rodada livre, sem segurar um post, até
    # LIMPEZAS_FORA_DA_HORA vezes. Sem hora marcada (P161 1), também na hora da antiga janela.
    monkeypatch.setattr(robo, "limpeza_fora_da_hora_pendente", LIMPEZA_FORA_DA_HORA)
    config = {**robo.PADRAO, "robo_inicio": 8, "robo_fim": 22, "robo_interacoes_inicio": 19,
              "robo_interacoes_fim": 21}
    robo.gravar_estado(descurtir_em="2026-10-24 04:10:00", descurtir_continuar=False)
    assert not robo.limpeza_fora_da_hora_pendente(momento("2026-10-25 03:30"))
    assert robo.o_que_fazer(config, momento("2026-10-25 10:00")) == ("descurtir", None)
    assert robo.o_que_fazer(config, momento("2026-10-25 19:30")) == ("descurtir", None)
    # Um aprovado indo ao ar logo: a limpeza espera, para não segurar o post.
    aprovado = _rascunho("aprovado", postar_em="2026-10-25 10:10:00")
    assert robo.o_que_fazer(config, momento("2026-10-25 10:00")) is None
    robo.atualizar(aprovado, estado="postado")
    ativar(robo_inicio=8, robo_fim=22)
    app = AppDosFavoritos(favoritos=3)
    robo.rodada(d=app, agora=momento("2026-10-25 10:00"))
    assert app.favoritos == [] and robo.lista_limpa()
    assert not robo.limpeza_fora_da_hora_pendente(momento("2026-10-25 10:20"))
    linhas = [(l[2], l[3]) for l in robo.registro_processos.contagem("2000-01-01 00:00:00")
              if l[1] == "descurtir tudo (4h)"]
    assert linhas == [("descurtido", "3 produto(s); fora da hora")]
    # No máximo LIMPEZAS_FORA_DA_HORA vezes por dia fora da hora dela.
    robo.gravar_estado(descurtir_continuar=True)
    assert robo.limpeza_fora_da_hora_pendente(momento("2026-10-25 11:00"))
    robo.gravar_estado(descurtir_fora={"dia": "2026-10-25", "vezes": robo.LIMPEZAS_FORA_DA_HORA})
    assert not robo.limpeza_fora_da_hora_pendente(momento("2026-10-25 11:00"))
    assert robo.limpeza_fora_da_hora_pendente(momento("2026-10-26 11:00"))


def test_limpeza_tira_tambem_os_de_meus_favoritos_de_comprador(monkeypatch, avisos):
    # Escolha do Rafael (02/11, P137 1): depois de Meus favoritos de afiliado, a limpeza tira
    # também os de Meus Favoritos de comprador (aba Eu → Meus Favoritos, a Visualização do
    # Comprador): Editar, marcar tudo, Remover dos Favoritos e o Sim da pergunta; no fim, Feito.
    # O carrinho (no alto e em cada produto) nunca é tocado: o celular de teste barra.
    ativar(robo_inicio=8, robo_fim=22)
    app = AppDosFavoritos(favoritos=2, comprador=3)
    resultado = robo.rodada(d=app, agora=momento("2026-10-25 04:05"))
    assert resultado == ("2 produto(s) descurtido(s) em Meus favoritos; 3 produto(s) tirado(s) de Meus "
                         "Favoritos de comprador")
    assert app.favoritos == [] and app.comprador == [] and not app.editando
    linhas = [(l[2], l[3]) for l in robo.registro_processos.contagem("2000-01-01 00:00:00")
              if l[1] == robo.PROCESSO_DE_COMPRADOR]
    assert linhas == [("removido", "3 produto(s)")]
    # O app guarda a edição aberta: com ela aberta, o robô segue sem o Editar; e mais de 50
    # saem em voltas, 50 de cada vez.
    robo.gravar_estado(descurtir_continuar=True)
    app = AppDosFavoritos(favoritos=0, comprador=60, editando=True)
    resultado = robo.rodada(d=app, agora=momento("2026-10-25 04:20"))
    assert resultado.endswith("; 60 produto(s) tirado(s) de Meus Favoritos de comprador")
    assert app.comprador == [] and not app.editando


def test_remover_dos_favoritos_de_comprador_que_nao_tira_para_e_a_limpeza_tenta_de_novo(monkeypatch, avisos):
    ativar(robo_inicio=8, robo_fim=22)
    app = AppDosFavoritos(favoritos=0, comprador=3, remover_pega=False)
    resultado = robo.rodada(d=app, agora=momento("2026-10-25 04:05"))
    assert "os 3 marcado(s) continuaram em Meus Favoritos de comprador" in resultado
    assert len(app.comprador) == 3 and not app.pergunta
    assert robo.passo_do_motivo(resultado) == "descurtir em Meus Favoritos"
    # Na rodada seguinte, ainda na hora, tenta de novo (e a lista de afiliado já está limpa).
    assert robo.o_que_fazer({**robo.PADRAO, "robo_inicio": 8, "robo_fim": 22},
                            momento("2026-10-25 04:20")) == ("descurtir", None)


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
    # O produto que não aparece em Minhas Curtidas faz o vídeo voltar mais tarde (P216 1): a rodada para.
    assert (caso["resultado"], caso["passo"]) == ("parou", "anexar o produto")
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
    monkeypatch.setattr(robo, "link_do_post", lambda d, ident=None, agora=None: LINK_DO_POST)
    monkeypatch.setattr(robo, "levar_ao_canal", lambda rascunho, link_post: levados.append((rascunho["id"], link_post)))
    app = AppComQuadros()
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho aprovado postado"
    assert levados == [(ident, LINK_DO_POST)]


def test_depois_do_post_o_video_nao_fica_rodando_no_celular(monkeypatch, avisos, caminho_do_rascunho):
    # Vídeo do Rafael das 16:31 de 02/11: o vídeo postado às 15:59 ainda rodava no Motorola meia
    # hora depois (o link do post é copiado com o vídeo aberto), e cada volta pode contar como uma
    # visualização a mais. No fim da rodada, o app fica no Eu, sem vídeo tocando.
    import registro_processos as rp
    _aprovado(monkeypatch)
    # O link do post deixa o vídeo aberto, como no Motorola.
    monkeypatch.setitem(TELAS, "player", [_no("Adicionar um comentário...", caixa=(200, 2300, 900, 2360))])
    monkeypatch.setattr(robo, "link_do_post", lambda d, ident=None, agora=None: setattr(d, "atual", "player") or LINK_DO_POST)
    app = AppComVoltar()
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho aprovado postado"
    assert app.atual == "eu" and app.toques[-1] == "Eu" and app.teclas[-1] == "back"
    registro = [(r, d) for _m, _p, r, d, _o in rp.sequencia("shopee_video", robo.PROCESSO_DO_FIM_DA_RODADA,
                                                            "2000-01-01 00:00:00")]
    assert registro == [("no Eu", "")]


def test_fim_da_rodada_nao_toca_na_verificacao_e_nao_muda_o_resultado(monkeypatch):
    import registro_processos as rp

    def verificacao(d, ate, vezes=15):
        raise robo.Verificacao()

    monkeypatch.setattr(robo, "voltar", verificacao)
    monkeypatch.setattr(robo, "tocar", lambda d, alvo, espera: pytest.fail("tocou na Verificação"))
    robo.deixar_sem_video(object())
    # O que falha só fica no registro: a rodada segue com o resultado dela.
    monkeypatch.setattr(robo, "voltar", lambda d, ate, vezes=15: (_ for _ in ()).throw(robo.Parada("x")))
    robo.deixar_sem_video(object())
    registro = [(r, d) for _m, _p, r, d, _o in rp.sequencia("shopee_video", robo.PROCESSO_DO_FIM_DA_RODADA,
                                                            "2000-01-01 00:00:00")]
    assert registro == [("parado na Verificação", ""), ("não voltou ao Eu", "Parada")]


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

    async def buscar(termo, limite=10, app_id=None, app_secret=None, sort_type=2, negada_levanta=False):
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


def test_ver_produtos_vai_ao_canal_pelo_link_de_cada_produto_no_rascunho(monkeypatch, avisos, tmp_path):
    # O trocado pelo da loja que paga mais (P57) e o a mais (P66) vão ao Canal Afiliados pelo link
    # deles no rascunho, que leva ao anúncio exato do post; o sem link, pela busca do nome.
    async def link_para_converter(link):
        if link == "https://s.shopee.com.br/41":
            return "https://shopee.com.br/Produto-i.7.41"
        return "https://sv.shopee.com.br/share-video/xyz?jumpType=1"

    async def buscar(termo, limite=10, app_id=None, app_secret=None, sort_type=2, negada_levanta=False):
        return [{"itemId": 3, "productName": "Brinco Argola Dourado Grande",
                 "productLink": "https://shopee.com.br/product/1/3"}]

    async def converter(endereco, etiqueta="geral", **kw):
        return endereco.replace("https://shopee.com.br/product/", "https://s.shopee.com.br/canal-")

    monkeypatch.setattr(robo, "link_para_converter", link_para_converter)
    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", buscar)
    monkeypatch.setattr(robo.api_shopee, "converter_link_shopee", converter)
    produtos = ["Mini Saia Plissada Feminina Cintura Alta Loja Dois", "Brinco Argola Dourado Grande"]
    rascunho = _postado_com_video(tmp_path, produtos=produtos, links_dos_produtos=["https://s.shopee.com.br/41", ""])
    assert robo.links_para_o_canal(rascunho) == ["https://s.shopee.com.br/canal-7/41", "https://s.shopee.com.br/canal-1/3"]


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

    async def buscar(termo, limite=20, sort_type=1, negada_levanta=False):
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

    async def nada(termo, limite=20, sort_type=1, negada_levanta=False):
        return []

    monkeypatch.setattr(robo.api_shopee, "buscar_ofertas_shopee", nada)
    assert robo.oferta_do_cartao(cartao, perdas) == {} and perdas["busca vazia"] == 1 and perdas["nome"] == 3


def test_oferta_do_cartao_e_o_anuncio_do_cartao_entre_lojas_de_titulo_copiado(monkeypatch):
    # Lojas diferentes copiam o mesmo título, e o 1º da busca com aquele nome e preço pode ser o
    # anúncio do próprio post: vale o de taxa de comissão e preço mais perto dos do cartão; no
    # empate, o mais relevante.
    async def buscar(termo, limite=20, sort_type=1, negada_levanta=False):
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

    def iguais(video, nome, anuncios, capa=None, recusas=None, precos=(), preco_do_post=None, outra_cor=None):
        estado["fotos_da_ia"] = [n for n, _ in anuncios]
        estado["precos"], estado["preco_do_post"] = list(precos), preco_do_post
        if outra_cor is not None:
            outra_cor.update(estado.get("outra_cor", ()))
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
    # O preço de cada um e o do post vão junto à IA: a imitação com a foto da marca costuma
    # custar muito menos (rascunho de 02/11 recusado pelo Rafael).
    assert busca_pela_foto["precos"] == [52.0, 50.0, 55.0] and busca_pela_foto["preco_do_post"] == 50.0
    assert [p["link"] for p in mais] == ["https://s.shopee.com.br/curto1", "https://s.shopee.com.br/curto3"]
    assert mais[0]["endereco"] == "https://shopee.com.br/product/9/1" and not mais[0].get("do_video")
    # A busca parte da foto de capa do anúncio do post, e a IA confere cada um com ela (P74);
    # a foto de cada um vai junto, para o álbum das capas do rascunho (P75).
    assert busca_pela_foto["foto_da_busca"] == b"\xff\xd8capa" and busca_pela_foto["capa"] == b"\xff\xd8capa"
    assert mais[0]["foto"] == b"\xff\xd8anuncio"
    assert vistos == ["Produtos a mais (2 de 3): a mesma garrafa"]
    assert _registro_dos_espacos() == ["achados"]


def test_espacos_livres_marcam_o_mesmo_modelo_em_outra_cor(busca_pela_foto, monkeypatch):
    # Pedido do Rafael (02/11, vídeo das 10:01): o mesmo modelo em outra cor entra nos produtos a
    # mais, marcado: ele só vai no post com a foto dele na miniatura que troca. Desligado desde a
    # P142 1 (03/11): o caminho fica testado para quando voltar.
    monkeypatch.setattr(robo, "OUTRA_COR_NOS_PRODUTOS", True)
    busca_pela_foto["outra_cor"] = {2}
    original = {"preco": 50.0, "imagem": "https://cf.shopee.com.br/capa"}
    mais = robo.espacos_livres(None, {"link": LINK, "arquivo": "v.mp4"}, PRINCIPAL, original, [],
                               robo.time.monotonic() + 600)
    assert [(p["nome"], p["outra_cor"]) for p in mais] == [("Garrafa Térmica Inox Loja 1", False),
                                                           ("Garrafa Térmica Inox Loja 3", True)]
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DOS_ESPACOS, "2000-01-01 00:00:00")
    assert registro[-1][3].startswith("2 a mais (1 de outra cor); ")


def test_espacos_livres_deixam_de_fora_o_mesmo_modelo_em_outra_cor(busca_pela_foto):
    # Escolha do Rafael (03/11, P142 1, depois da punição de Produto Irrelevante do vídeo das 07:20):
    # nunca outra cor nos produtos a mais; o registro conta quantos ficaram de fora por isso.
    busca_pela_foto["outra_cor"] = {2}
    original = {"preco": 50.0, "imagem": "https://cf.shopee.com.br/capa"}
    mais = robo.espacos_livres(None, {"link": LINK, "arquivo": "v.mp4"}, PRINCIPAL, original, [],
                               robo.time.monotonic() + 600)
    assert [(p["nome"], p["outra_cor"]) for p in mais] == [("Garrafa Térmica Inox Loja 1", False)]
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_OUTRA_COR, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in registro] == [("de fora", "1 - " + robo.MOTIVO_DA_OUTRA_COR_DESLIGADA)]
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DOS_ESPACOS, "2000-01-01 00:00:00")
    assert registro[-1][3].startswith("1 a mais; ")


def test_post_poe_a_mesma_cor_primeiro_e_o_de_outra_cor_so_com_a_foto_na_miniatura():
    # O 1º do post dá a foto do começo e da miniatura, na cor do vídeo; o de outra cor vai depois,
    # mesmo pagando mais por venda, e só com a foto dele na miniatura que troca: sem a nossa
    # miniatura, ou sem tempo para a foto dele, ele sai antes de anexar (pedidos do Rafael de
    # 01/11 e 02/11).
    principal = dict(PRINCIPAL, foto=b"principal")
    igual = dict(PRINCIPAL, nome="Igual", do_video=False, valor=4.0, outra_cor=False, foto=b"igual")
    outra = dict(PRINCIPAL, nome="Outra cor", do_video=False, valor=9.0, outra_cor=True, foto=b"outra")
    ordem = robo.ordem_do_post(principal, [outra, igual])
    assert [p["nome"] for p in ordem] == [PRINCIPAL["nome"], "Igual", "Outra cor"]
    itens = [(p, p.get("foto"), p.get("outra_cor")) for p in ordem]
    assert robo.com_a_foto_na_miniatura(itens, [b"principal", b"outra"]) == ordem
    assert robo.com_a_foto_na_miniatura(itens, []) == ordem[:2]
    assert robo.com_a_foto_na_miniatura(itens, [b"principal"]) == ordem[:2]
    # O 1º nunca sai, nem marcado.
    assert robo.com_a_foto_na_miniatura([(outra, b"outra", True)], []) == [outra]
    registro = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_OUTRA_COR, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in registro] == [("no post", "a foto na miniatura"), ("de fora", "sem a nossa miniatura"),
                                                ("de fora", "a foto não coube na miniatura")]


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
    monkeypatch.setattr(robo, "primeiro_na_tela_final", lambda d, vez=1, nome="": True)
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
    monkeypatch.setattr(robo, "primeiro_na_tela_final", lambda d, vez=1, nome="": True)
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


class AppComOAdicionarQueDemora(AppDeMentira):
    """A tela final que só mostra a linha do Adicionar produto depois de algumas leituras."""

    def __init__(self, leituras_sem_a_linha):
        super().__init__()
        self.atual = "final"
        self.leituras_sem_a_linha = leituras_sem_a_linha

    def _nos(self):
        nos = super()._nos()
        if self.atual == "final" and self.leituras_sem_a_linha > 0:
            self.leituras_sem_a_linha -= 1
            return [no for no in nos if "ll_add_product_symbol" not in no]
        return nos


def _registro_do_anexo():
    registro = robo.registro_processos.sequencia("shopee_video", "anexar o produto", "2000-01-01 00:00:00")
    return [(r[2], r[3]) for r in registro]


def test_a_linha_do_adicionar_produto_que_demora_e_esperada_antes_do_toque(monkeypatch):
    # No Motorola, em 06/11 às 16:26, a tela final ainda não mostrava a linha do Adicionar
    # produto 12 s depois do Próximo da edição, e o rascunho parou. O caminho relê a tela por
    # até ps.ESPERA_DA_FILEIRA s antes do toque, e o registro anota quanto ela demorou.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    app = AppComOAdicionarQueDemora(2)
    robo.seguir(app, robo.CAMINHO_PRODUTO)
    assert app.toques[0] == "@ll_add_product_symbol" and app.atual == "curtidas"
    assert _registro_do_anexo() == [("o Adicionar produto demorou a aparecer", "mais 6 s")]
    # A linha que aparece na hora não fica no registro.
    robo.seguir(AppComOAdicionarQueDemora(0), robo.CAMINHO_PRODUTO)
    assert len(_registro_do_anexo()) == 1


def test_sem_a_linha_do_adicionar_produto_a_parada_e_no_passo_de_anexar(monkeypatch):
    # A linha que não aparece nem depois da espera para a rodada sem tocar em nada, e a parada diz
    # o passo de anexar o produto (não "navegar no app") e como estava a linha dos produtos.
    monkeypatch.setattr(robo, "pausa", lambda s: None)
    app = AppComOAdicionarQueDemora(100)
    with pytest.raises(robo.Parada) as parada:
        robo.seguir(app, robo.CAMINHO_PRODUTO)
    assert not app.toques and not _registro_do_anexo()
    assert parada.value.motivo == (f"a tela final não mostrou o Adicionar produto em {robo.ps.ESPERA_DA_FILEIRA} s "
                                   "a mais (sem a linha dos produtos na tela)")
    assert robo.passo_do_motivo(parada.value.motivo) == "anexar o produto"


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


LOGO_DEPOIS_DO_FEITO = "; logo depois do Feito: a tela final, a linha dos produtos vazia; a edição da legenda aberta por cima"


def test_video_do_produto_que_nao_fica_na_tela_final_volta_mais_tarde(monkeypatch, avisos):
    # P182 1 (09/11): o produto que o app não deixa na tela final depois do Feito, nem na 2ª vez, vem
    # em rajadas (das 13:08 às 13:37 de 09/11, 4 produtos diferentes seguidos; às 14:03 o seguinte
    # ficou de primeira): a falha é da hora, não do vídeo. Ele volta como nas outras falhas que não
    # são do vídeo: o mesmo vídeo na rodada seguinte, sem ficar de lado.
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    agora = momento("2026-10-22 23:59")
    app = AppQueReabreALegenda(perdidos=5)
    resultado = robo.rodada(d=app, agora=agora)
    assert robo.MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU in resultado and robo.esperando_aprovacao() == []
    assert robo.listar("pulado") == [] and app.toques.count("Feito") == robo.VEZES_DO_PRIMEIRO_PRODUTO
    assert robo.proximo_video(robo.ler_config())["id"] == "a1"
    # Na rodada seguinte, com o app de volta ao normal, o mesmo vídeo vira rascunho.
    assert robo.rodada(d=AppQueReabreALegenda(), agora=agora) == "rascunho salvo"
    assert [r["id_video"] for r in robo.listar("rascunho")] == ["a1"]


def test_video_cujo_produto_nao_aparece_em_minhas_curtidas_volta_mais_tarde(monkeypatch, avisos):
    # P216 1 (13/11): às 05:54, o produto curtido pouco antes não apareceu em Minhas Curtidas (a lista
    # vazia nas 4 leituras) nem pela foto do 1º da lista, e o vídeo ficou de lado de vez; pouco depois
    # das 8h, a lista já o mostrava. A falha é da hora, não do vídeo: ele volta mais tarde, como o
    # produto que não fica depois do Feito (P182 1).
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    agora = momento("2026-10-22 23:59")
    adicionar = robo.ps.adicionar_produto
    fora = (f"{robo.ps.MOTIVO_FORA_DE_MINHAS_CURTIDAS} (a lista não tem produto para conferir): nada adicionado "
            "(aviso no privado)")
    monkeypatch.setattr(robo.ps, "adicionar_produto", lambda *a, **k: (False, fora))
    resultado = robo.rodada(d=AppQueReabreALegenda(), agora=agora)
    assert robo.ps.MOTIVO_FORA_DE_MINHAS_CURTIDAS in resultado and robo.esperando_aprovacao() == []
    assert robo.listar("pulado") == [] and robo.proximo_video(robo.ler_config())["id"] == "a1"
    assert robo.passo_do_motivo(fora) == "anexar o produto"
    # Na rodada seguinte, com o produto na lista, o mesmo vídeo vira rascunho.
    monkeypatch.setattr(robo.ps, "adicionar_produto", adicionar)
    assert robo.rodada(d=AppQueReabreALegenda(), agora=agora) == "rascunho salvo"
    assert [r["id_video"] for r in robo.listar("rascunho")] == ["a1"]


def test_outra_falha_do_adicionar_continua_deixando_o_video_de_lado(monkeypatch, avisos):
    # Só o produto que a lista de Minhas Curtidas não mostra volta mais tarde (P216 1); o Adicionar
    # coberto por outro app continua como estava.
    _fonte(monkeypatch)
    monkeypatch.setattr(robo.ps, "adicionar_produto",
                        lambda *a, **k: (False, "o Adicionar do produto está coberto por outro app: nada tocado"))
    with pytest.raises(robo.Parada) as parada:
        _anexar_no_app(AppQueReabreALegenda())
    assert parada.value.do_video


def test_tela_de_logo_depois_do_feito_vai_para_o_caso(monkeypatch, avisos):
    # O caso de 07/11 só tinha a tela de 30 s depois do Feito: um aviso do app na tela já tinha
    # sumido. A tela lida logo depois do Feito entra entre as ações do caso.
    _fonte(monkeypatch)
    app = robo.casos_robo.com_historico(AppQueReabreALegenda(perdidos=5))
    with pytest.raises(robo.Parada):
        _anexar_no_app(app)
    # O caso guarda as últimas ações: o Feito, a tela de logo depois dele e o toque que fecha a
    # edição da legenda aberta por cima.
    acoes = list(app.acoes)
    assert [a["acao"] for a in acoes[-2:]][0] == "tela logo depois do Feito"
    assert acoes[-3]["ponto"] == robo.ps.achar(acoes[-3]["tela"], "Feito")
    logo = acoes[-2]
    assert logo["ponto"] is None and "rl_overlay" in logo["tela"]
    assert robo.como_ficou_logo_depois_do_feito(logo["tela"]) == LOGO_DEPOIS_DO_FEITO.split(": ", 1)[1]
    assert robo.como_ficou_logo_depois_do_feito("<hierarchy/>") == "outra tela"


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
    # A tela de logo depois do Feito também vai para o registro, em rótulos fixos (07/11).
    assert _registro_do_anexar() == [
        ("não ficou depois do Feito", "1ª vez; a linha dos produtos vazia; a edição da legenda aberta por cima"
                                      + LOGO_DEPOIS_DO_FEITO),
        ("anexado na 2ª vez", "a linha dos produtos com produto")]


def test_primeiro_produto_que_nao_fica_nem_na_segunda_vez_para_o_rascunho(monkeypatch, avisos):
    _fonte(monkeypatch)
    app = AppQueReabreALegenda(perdidos=5)
    with pytest.raises(robo.Parada) as parada:
        _anexar_no_app(app)
    # O produto que não fica nem na 2ª vez é falha da hora, não do vídeo (P182 1): o vídeo volta
    # mais tarde, como nas outras falhas que não são dele.
    assert parada.value.motivo == robo.MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU and not parada.value.do_video
    assert robo.passo_do_motivo(parada.value.motivo) == "anexar o produto"
    assert app.toques.count("Feito") == robo.VEZES_DO_PRIMEIRO_PRODUTO and "@et_caption" not in app.toques
    assert [r[0] for r in _registro_do_anexar()] == ["não ficou depois do Feito"] * robo.VEZES_DO_PRIMEIRO_PRODUTO


class AppAbertoHaHoras(AppQueReabreALegenda):
    """O app que perde o produto no Feito, com o processo do app rodando há etime (o ELAPSED do ps)."""

    def __init__(self, perdidos=None, etime="16:02:03"):
        super().__init__(perdidos)
        self.etime = etime

    def shell(self, partes):
        if partes and partes[0] in ("pidof", "ps"):
            self.comandos.append(partes)
            saida = ({"pidof": "4321", "ps": f"     ELAPSED\n  {self.etime}"}[partes[0]]) if self.etime else ""
            return type("R", (), {"output": saida})()
        return super().shell(partes)

    def app_stop(self, pacote):
        self.comandos.append(["fechar", pacote])
        self.atual = "inicio"

    def app_start(self, pacote, wait=False):
        self.comandos.append(["abrir", pacote])


def _app_reaberto(processo=robo.PROCESSO_DO_APP_REABERTO):
    import sqlite3
    try:
        with robo.db.conexao() as con:
            return [tuple(linha) for linha in con.execute(
                "SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = ? ORDER BY id",
                (processo,))]
    except sqlite3.OperationalError:
        return []


def test_app_aberto_ha_mais_de_12_horas_e_reaberto_depois_do_produto_que_nao_ficou(monkeypatch, avisos):
    # Escolha do Rafael (10/11, P193 1): em 10/11, das 05:44 às 06:24, 3 produtos seguidos não ficaram
    # depois do Feito com o app aberto havia 16 h e a memória dele perto do teto do celular. Só quando
    # o produto não fica nem na 2ª vez e o app está aberto há mais de 12 h, o robô fecha e reabre a
    # Shopee, depois de guardar o caso com a tela da falha; o vídeo volta mais tarde (P182 1).
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    ordem = []
    guardar = robo.casos_robo.guardar
    monkeypatch.setattr(robo.casos_robo, "guardar", lambda d, *a, **k: ordem.append("caso") or guardar(d, *a, **k))
    app = AppAbertoHaHoras(perdidos=5)
    parar = app.app_stop
    monkeypatch.setattr(app, "app_stop", lambda pacote: ordem.append("fechar") or parar(pacote))
    resultado = robo.rodada(d=app, agora=momento("2026-10-22 23:59"))
    assert robo.MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU in resultado and robo.esperando_aprovacao() == []
    # Fechado uma vez e aberto de novo logo depois (o 1º abrir é o do começo da rodada).
    assert app.comandos.count(["fechar", robo.ps.PACOTE]) == 1
    assert ["abrir", robo.ps.PACOTE] in app.comandos[app.comandos.index(["fechar", robo.ps.PACOTE]):]
    assert ordem[:2] == ["caso", "fechar"]
    assert _app_reaberto() == [("fechado e reaberto", "pelo tempo aberto: o app aberto há 12 a 24 h", 1)]
    assert robo.listar("pulado") == [] and robo.proximo_video(robo.ler_config())["id"] == "a1"


def test_app_aberto_ha_pouco_tempo_ou_sem_a_leitura_nao_e_fechado(monkeypatch, avisos):
    # P193 1: só com o app aberto há mais de 12 h; com menos, ou sem saber, o robô não fecha o app
    # (P15: fora do aviso de app travado e do app sem memória, P215 1, ele nunca fecha).
    for etime in ("11:59:00", "12:00:00", None):
        app = AppAbertoHaHoras(etime=etime)
        assert robo.reabrir_o_app_antigo_ou_sem_memoria(app, robo.MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU) is False, etime
        assert not any(c[0] in ("fechar", "abrir") for c in app.comandos), etime
    assert _app_reaberto() == []
    # O produto que não fica com o app aberto há pouco tempo também não fecha nada na rodada.
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    app = AppAbertoHaHoras(perdidos=5, etime="03:10:00")
    assert robo.MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU in robo.rodada(d=app, agora=momento("2026-10-22 23:59"))
    assert ["fechar", robo.ps.PACOTE] not in app.comandos and _app_reaberto() == []


def test_verificacao_depois_de_reabrir_o_app_aberto_ha_horas_para_e_avisa(monkeypatch, avisos):
    # P193 1: se a Verificação aparecer depois de reabrir, o robô para e avisa, como sempre.
    app = AppAbertoHaHoras(etime="1-02:03:04")
    monkeypatch.setattr(robo.ps, "eh_verificacao", lambda xml: ["abrir", robo.ps.PACOTE] in app.comandos)
    with pytest.raises(robo.Verificacao):
        robo.reabrir_o_app_antigo_ou_sem_memoria(app, robo.MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU)
    assert _app_reaberto() == [("a Verificação apareceu", "pelo tempo aberto: o app aberto há mais de 1 dia", 0)]


class AppSemMemoria(AppAbertoHaHoras):
    """O app aberto há etime com o Java dele em usada MB (a linha Dalvik Heap do dumpsys meminfo)."""

    def __init__(self, perdidos=None, etime="11:00:00", usada=460):
        super().__init__(perdidos, etime)
        self.usada = usada

    def shell(self, partes):
        if partes[:2] == ["dumpsys", "meminfo"]:
            self.comandos.append(partes)
            saida = (f"  Dalvik Heap   480000   470000      100     2000   500000   524288   {self.usada * 1024}"
                     f"     {524288 - self.usada * 1024}\n") if self.usada is not None else ""
            return type("R", (), {"output": saida})()
        return super().shell(partes)


def _guardar_e_fechar_em_ordem(monkeypatch, app):
    """A ordem do caso guardado e do app fechado (o caso tem de guardar antes a tela da falha)."""
    ordem = []
    guardar = robo.casos_robo.guardar
    monkeypatch.setattr(robo.casos_robo, "guardar", lambda d, *a, **k: ordem.append("caso") or guardar(d, *a, **k))
    parar = app.app_stop
    monkeypatch.setattr(app, "app_stop", lambda pacote: ordem.append("fechar") or parar(pacote))
    return ordem


PELA_MEMORIA = "pela memória: o app aberto há 6 a 12 h; a memória do app 450 MB ou mais"


def test_app_sem_memoria_e_reaberto_no_produto_que_nao_ficou_mesmo_aberto_ha_menos_de_12_horas(monkeypatch, avisos):
    # Escolha do Rafael (12/11, P215 1): às 20:52 e às 21:11 de 12/11, o produto não ficou depois do
    # Feito (nem na 2ª vez) com o app aberto havia 11 h e o Java dele em 410 a 460 MB; os 11 que ficaram
    # de primeira tinham menos de 400 MB. Com a memória acima de 400 MB, o robô guarda o caso, fecha e
    # reabre a Shopee, mesmo com o app aberto há menos de 12 h; o vídeo volta mais tarde (P182 1).
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    app = AppSemMemoria(perdidos=5, etime="11:00:00", usada=460)
    ordem = _guardar_e_fechar_em_ordem(monkeypatch, app)
    resultado = robo.rodada(d=app, agora=momento("2026-10-22 23:59"))
    assert robo.MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU in resultado and robo.esperando_aprovacao() == []
    assert app.comandos.count(["fechar", robo.ps.PACOTE]) == 1 and ordem[:2] == ["caso", "fechar"]
    assert ["abrir", robo.ps.PACOTE] in app.comandos[app.comandos.index(["fechar", robo.ps.PACOTE]):]
    assert _app_reaberto() == [("fechado e reaberto", PELA_MEMORIA, 1)]
    assert robo.listar("pulado") == [] and robo.proximo_video(robo.ler_config())["id"] == "a1"
    # Com as 12 h e a memória alta, as duas razões ficam no registro.
    app = AppSemMemoria(etime="13:00:00", usada=430)
    assert robo.reabrir_o_app_antigo_ou_sem_memoria(app, robo.MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU) is True
    assert _app_reaberto()[-1] == ("fechado e reaberto", "pelo tempo aberto e pela memória: o app aberto há 12 a 24 h; "
                                   "a memória do app 400 a 450 MB", 1)


def test_app_com_400_mb_ou_menos_e_aberto_ha_menos_de_12_horas_nao_e_fechado(monkeypatch, avisos):
    # P215 1: só com a memória acima de 400 MB (ou, no produto que não ficou, com o app aberto há
    # mais de 12 h, P193 1); com 400 MB ou menos, ou sem a leitura, o robô não fecha o app (P15).
    for usada in (380, 400, None):
        app = AppSemMemoria(etime="11:00:00", usada=usada)
        assert robo.reabrir_o_app_antigo_ou_sem_memoria(app, robo.MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU) is False, usada
        assert robo.reabrir_o_app_antigo_ou_sem_memoria(app, "não achei Criadores & Afiliados na tela") is False, usada
        assert not any(c[0] in ("fechar", "abrir") for c in app.comandos), usada
    assert _app_reaberto() == [] and _app_reaberto(robo.PROCESSO_DA_PAGINA_EM_BRANCO) == []


def test_pagina_em_branco_do_app_sem_memoria_fecha_e_reabre_o_app(monkeypatch, avisos):
    # P215 1: às 08:58 e às 21:26 de 12/11, o app da Shopee ficou sem memória (o Java no teto dos
    # 512 MB, o OutOfMemoryError no log) e a página abriu em branco: o robô parou em "navegar no app"
    # e o app só voltou ao normal depois. Com a memória acima de 400 MB, a tela que não mostrou o que
    # devia fecha e reabre a Shopee; abaixo, só para, como antes, mesmo com o app aberto há mais de
    # 12 h (as horas valem só para o produto que não ficou, P193 1).
    em_branco = ["não achei Criadores & Afiliados na tela", "depois de Eu, a tela não mostrou Criadores & Afiliados",
                 "não consegui voltar até Eu (só as barras do Android)", "não achei Meus Favoritos na aba Eu",
                 "não achei o campo de comentar no vídeo do post"]
    outros = ["a IA viu outro produto no vídeo (1ª vez)", robo.MOTIVO_DO_PRIMEIRO_QUE_NAO_FICOU,
              "não consegui deixar marcado só o vídeo mais novo na galeria", "rodada foi interrompida", "", None]
    assert all(robo.pagina_em_branco(motivo) for motivo in em_branco)
    assert not any(robo.pagina_em_branco(motivo) for motivo in outros)
    for motivo in em_branco:
        app = AppSemMemoria(etime="11:00:00", usada=505)
        assert robo.reabrir_o_app_antigo_ou_sem_memoria(app, motivo) is True, motivo
        assert app.comandos.count(["fechar", robo.ps.PACOTE]) == 1, motivo
    assert _app_reaberto(robo.PROCESSO_DA_PAGINA_EM_BRANCO) == [("fechado e reaberto", PELA_MEMORIA, 1)] * len(em_branco)
    assert _app_reaberto() == []
    # Abaixo dos 400 MB, a página em branco só para, mesmo com o app aberto há mais de 1 dia.
    app = AppSemMemoria(etime="1-02:00:00", usada=390)
    assert robo.reabrir_o_app_antigo_ou_sem_memoria(app, em_branco[0]) is False
    assert ["fechar", robo.ps.PACOTE] not in app.comandos
    # A parada que não é do app nem lê o celular.
    app = AppSemMemoria(usada=505)
    assert robo.reabrir_o_app_antigo_ou_sem_memoria(app, outros[0]) is False and app.comandos == []
    # O celular que cai no meio do fechar não para nada além da parada que já houve: só o registro.
    app = AppSemMemoria(usada=505)

    def caiu(pacote):
        raise ConnectionError("caiu")

    monkeypatch.setattr(app, "app_stop", caiu)
    assert robo.reabrir_o_app_antigo_ou_sem_memoria(app, em_branco[0]) is False
    assert _app_reaberto(robo.PROCESSO_DA_PAGINA_EM_BRANCO)[-1] == ("não reabriu", f"{PELA_MEMORIA}; ConnectionError", 0)
    # A Verificação depois de reabrir para e avisa, como sempre.
    app = AppSemMemoria(usada=505)
    monkeypatch.setattr(robo.ps, "eh_verificacao", lambda xml: ["abrir", robo.ps.PACOTE] in app.comandos)
    with pytest.raises(robo.Verificacao):
        robo.reabrir_o_app_antigo_ou_sem_memoria(app, em_branco[1])
    assert _app_reaberto(robo.PROCESSO_DA_PAGINA_EM_BRANCO)[-1] == ("a Verificação apareceu", PELA_MEMORIA, 0)


def test_pagina_em_branco_no_rascunho_guarda_o_caso_e_reabre_o_app_sem_memoria(monkeypatch, avisos):
    # P215 1, como às 21:26 de 12/11: no meio do rascunho, a página do app abriu em branco com o Java
    # no teto. O caso guarda a tela da falha, e só depois o robô fecha e reabre a Shopee; o vídeo
    # volta mais tarde, como em toda parada que não é dele.
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)

    def em_branco(d, ident, video, fonte, agora=None, curtidos=None, celular=None):
        celular.append(True)
        raise robo.Parada("não achei Criadores & Afiliados na tela")

    monkeypatch.setattr(robo, "_preparar", em_branco)
    app = AppSemMemoria(usada=505)
    ordem = _guardar_e_fechar_em_ordem(monkeypatch, app)
    resultado = robo.rodada(d=app, agora=momento("2026-10-22 23:59"))
    assert "não achei Criadores & Afiliados na tela" in resultado and ordem[:2] == ["caso", "fechar"]
    assert _app_reaberto(robo.PROCESSO_DA_PAGINA_EM_BRANCO) == [("fechado e reaberto", PELA_MEMORIA, 1)]
    assert robo.listar("pulado") == [] and robo.proximo_video(robo.ler_config())["id"] == "a1"


def test_pagina_em_branco_fora_do_rascunho_reabre_o_app_sem_memoria_e_a_verificacao_para(monkeypatch, avisos):
    # P215 1: a página em branco na resposta aos comentários (ou no post, na Saúde, no feed) também
    # fecha e reabre a Shopee com a memória acima de 400 MB, depois de guardar o caso; a resposta fica
    # para a próxima, como antes. A Verificação na volta para tudo e abre a tela para o Rafael.
    abertas = []
    monkeypatch.setattr(robo.av, "abrir_tela", lambda celular=False, verificacao=False: abertas.append(verificacao))

    def em_branco(d, agora=None):
        raise robo.Parada("depois de Eu, a tela não mostrou Notificações")

    monkeypatch.setattr(robo, "responder_comentarios", em_branco)
    app = AppSemMemoria(usada=505)
    ordem = _guardar_e_fechar_em_ordem(monkeypatch, app)
    agora = momento("2026-10-22 15:00")
    resultado = robo._agir(app, "responder", None, False, robo.ler_config(), agora)
    assert resultado.endswith("parado (depois de Eu, a tela não mostrou Notificações)") and abertas == []
    assert ordem[:2] == ["caso", "fechar"]
    assert _app_reaberto(robo.PROCESSO_DA_PAGINA_EM_BRANCO) == [("fechado e reaberto", PELA_MEMORIA, 1)]
    app = AppSemMemoria(usada=505)
    monkeypatch.setattr(robo.ps, "eh_verificacao", lambda xml: ["abrir", robo.ps.PACOTE] in app.comandos)
    assert robo._agir(app, "responder", None, False, robo.ler_config(), agora) == "responder: verificação na tela; parado"
    assert abertas == [True]
    # Abaixo dos 400 MB, só para, sem fechar o app.
    app = AppSemMemoria(usada=350)
    assert "parado" in robo._agir(app, "responder", None, False, robo.ler_config(), agora)
    assert ["fechar", robo.ps.PACOTE] not in app.comandos


class AppQueAvisaNoFeito(AppQueReabreALegenda):
    """O app que perde o produto no Feito e mostra um aviso curto (toast), como o uiautomator2 lê."""

    def __init__(self, perdidos=None, aviso="Não foi possível adicionar o produto 1"):
        super().__init__(perdidos)
        self.aviso, self.ultimo_aviso = aviso, None

    def clear_toast(self):
        self.ultimo_aviso = None

    @property
    def last_toast(self):
        # Como no uiautomator2: uma propriedade, não uma função.
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
        + LOGO_DEPOIS_DO_FEITO for vez in range(1, robo.VEZES_DO_PRIMEIRO_PRODUTO + 1)]
    # Sem aviso nenhum depois do Feito, o registro também diz.
    app = AppQueAvisaNoFeito(perdidos=1, aviso=None)
    _anexar_no_app(app)
    assert _registro_do_anexar()[-2][1].endswith("; sem aviso do app" + LOGO_DEPOIS_DO_FEITO)


def test_produto_que_nao_fica_no_feito_diz_os_sinais_do_nome(monkeypatch, avisos):
    # 07/11 (06:09 e 16:46): os 2 produtos que o app não deixou na tela final depois do Feito, sem
    # aviso, tinham dois-pontos no nome. O registro diz os sinais do nome em rótulos fixos (o nome
    # nunca vai ao registro, que sai no checkup público).
    app = AppQueReabreALegenda()
    app.atual = "final"
    assert not robo.primeiro_na_tela_final(app, 1, "Kit Creme Facial Hidratante: 2 Unidades")
    assert _registro_do_anexar()[-1][0] == "não ficou depois do Feito"
    assert _registro_do_anexar()[-1][1].endswith("; o nome com dois-pontos")
    app.com_produto = True
    assert robo.primeiro_na_tela_final(app, 2, "Kit Creme Facial Hidratante: 2 Unidades")
    assert _registro_do_anexar()[-1] == ("anexado na 2ª vez", "a linha dos produtos com produto; o nome com dois-pontos")


def test_produto_que_nao_fica_no_feito_diz_os_sinais_do_app(monkeypatch, avisos):
    # 08/11, das 19:04 às 19:31: no começo da noite em que o app travou e a leitura da tela veio sem
    # ele, 2 produtos diferentes não ficaram seguidos (nem na 2ª vez) e 1 só ficou na 2ª vez. O
    # registro diz, numa linha à parte de cada um que não fica, quantas vezes o app travou e a leitura
    # veio sem ele na última hora, e há quantos minutos o app está aberto (só números: o checkup é
    # público).
    from datetime import timedelta as intervalo
    agora = robo.agora_br()
    registrar = robo.registro_processos.registrar
    registrar("shopee_video", "app travado", "voltou depois do Aguardar", "1 toque(s)", ok=True,
              agora=agora - intervalo(minutes=20))
    registrar("shopee_video", "app travado", "voltou depois do Aguardar", "1 toque(s)", ok=True,
              agora=agora - intervalo(hours=2))                                # fora da janela
    registrar("shopee_video", robo.PROCESSO_DA_LEITURA_DA_TELA, "só as barras do Android", "sem o app em 3 releituras",
              ok=False, agora=agora - intervalo(minutes=10))
    registrar("shopee_video", robo.PROCESSO_DA_LEITURA_DA_TELA, "só as barras do Android",
              "o app voltou na 2ª releitura", ok=True, agora=agora - intervalo(minutes=5))
    app = AppQueReabreALegenda()
    app.atual = "final"

    def shell(partes):
        app.comandos.append(partes)
        saida = {"pidof": "4321", "ps": "     ELAPSED\n  1-02:03:04"}.get(partes[0], "")
        return type("R", (), {"output": saida})()
    monkeypatch.setattr(app, "shell", shell)
    assert not robo.primeiro_na_tela_final(app, 1, "Bolsa de Palha")
    assert _registro_do_anexar()[-1][0] == "não ficou depois do Feito"
    sinais = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DOS_SINAIS_DO_APP, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in sinais] == [
        ("1ª vez", "na última hora: app travado 1, leitura sem o app 1, erro de sistema da Shopee na API 0; "
                   "o app aberto há 1563 min")]
    assert ["pidof", robo.ps.PACOTE] in app.comandos and ["ps", "-o", "ETIME", "-p", "4321"] in app.comandos
    # Sem a leitura do celular, só os números do registro.
    monkeypatch.setattr(app, "shell", lambda partes: type("R", (), {"output": ""})())
    assert not robo.primeiro_na_tela_final(app, 2, "Bolsa de Palha")
    sinais = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DOS_SINAIS_DO_APP, "2000-01-01 00:00:00")
    assert (sinais[-1][2], sinais[-1][3]) == (
        "2ª vez", "na última hora: app travado 1, leitura sem o app 1, erro de sistema da Shopee na API 0")


def test_sinais_do_anexar_contam_o_erro_de_sistema_da_shopee_e_o_produto_que_fica(monkeypatch, avisos):
    # 09/11, das 13:08 às 13:37: 4 produtos diferentes seguidos não ficaram, sem o app travar, e na
    # mesma hora a busca de ofertas da API deu o erro de sistema da própria Shopee; às 14:03 o
    # seguinte ficou de primeira. A linha dos sinais conta esses erros da API na última hora (os que
    # a nova tentativa salvou e os negados por ele, de qualquer robô; outro código não conta), e o
    # produto que fica de primeira ganha a mesma linha, com o app aberto em faixas, para o checkup
    # comparar os que ficam com os que não ficam.
    from datetime import timedelta as intervalo
    agora = robo.agora_br()
    registrar, api = robo.registro_processos.registrar, robo.api_shopee
    registrar(api.ROBO_DO_REGISTRO, api.PROCESSO_DO_ERRO_DE_SISTEMA, "deu certo na 2ª tentativa", "robo_shopee_video",
              ok=True, agora=agora - intervalo(minutes=40))
    registrar(api.ROBO_DO_REGISTRO, api.PROCESSO_DA_BUSCA_NEGADA, api.rotulo_do_codigo("10000"), "bot_mestre",
              ok=False, agora=agora - intervalo(minutes=15))
    registrar(api.ROBO_DO_REGISTRO, api.PROCESSO_DA_BUSCA_NEGADA, api.rotulo_do_codigo("10030"), "bot_mestre",
              ok=False, agora=agora - intervalo(minutes=10))                  # outro código
    registrar(api.ROBO_DO_REGISTRO, api.PROCESSO_DA_BUSCA_NEGADA, api.rotulo_do_codigo("10000"), "robo_shopee_video",
              ok=False, agora=agora - intervalo(hours=2))                     # fora da janela
    assert api.RESULTADO_DO_ERRO_DE_SISTEMA == "código 10.000" and api.rotulo_do_codigo("") == "sem código"
    app = AppQueReabreALegenda()
    app.atual = "final"
    elapsed = {"ps": "     ELAPSED\n  16:57:04"}

    def shell(partes):
        return type("R", (), {"output": {"pidof": "4321"}.get(partes[0], elapsed.get(partes[0], ""))})()
    monkeypatch.setattr(app, "shell", shell)
    assert not robo.primeiro_na_tela_final(app, 1, "Mala de Bordo")
    sinais = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DOS_SINAIS_DO_APP, "2000-01-01 00:00:00")
    assert (sinais[-1][2], sinais[-1][3]) == (
        "1ª vez", "na última hora: app travado 0, leitura sem o app 0, erro de sistema da Shopee na API 2; "
                  "o app aberto há 1017 min")
    # O que fica de primeira: a mesma contagem, e o app aberto na faixa de horas.
    app.com_produto = True
    assert robo.primeiro_na_tela_final(app, 1, "Mala de Bordo")
    sinais = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DOS_SINAIS_DO_APP, "2000-01-01 00:00:00")
    assert (sinais[-1][2], sinais[-1][3]) == (
        robo.FICOU_DE_PRIMEIRA, "na última hora: erro de sistema da Shopee na API 2; o app aberto há 12 a 24 h")
    # Na 2ª vez, o registro do anexar já diz que ficou; a linha dos sinais não se repete.
    assert robo.primeiro_na_tela_final(app, 2, "Mala de Bordo")
    assert len(robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DOS_SINAIS_DO_APP,
                                                 "2000-01-01 00:00:00")) == 2
    # Sem a leitura do celular, só a contagem da API.
    monkeypatch.setattr(app, "shell", lambda partes: type("R", (), {"output": ""})())
    assert robo.primeiro_na_tela_final(app, 1, "Mala de Bordo")
    sinais = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DOS_SINAIS_DO_APP, "2000-01-01 00:00:00")
    assert sinais[-1][3] == "na última hora: erro de sistema da Shopee na API 2"


def test_sinais_do_anexar_dizem_a_memoria_do_app(monkeypatch, avisos):
    # 10/11, das 05:44 às 06:24: o produto não ficou depois do Feito em 3 tentativas seguidas, com o
    # app aberto havia 16 h e o Java dele perto do teto (512 MB no Motorola), pelo log do coletor: a
    # cada Feito, o app refazia a tela de publicar e perdia o produto. A linha dos sinais diz a
    # memória do Java do app (a linha Dalvik Heap do dumpsys meminfo); a do que fica, em faixas.
    app = AppQueReabreALegenda()
    app.atual = "final"
    meminfo = ("** MEMINFO in pid 4321 [com.shopee.br] **\n"
               "                   Pss  Private  Private  SwapPss      Rss     Heap     Heap     Heap\n"
               "                 Total    Dirty    Clean    Dirty    Total     Size    Alloc     Free\n"
               "  Native Heap    81920    81000        0      100    90000   120000    95000    25000\n"
               "  Dalvik Heap   480000   470000      100     2000   500000   524288   515072     9216\n"
               " App Summary\n           Java Heap:   515072\n")
    comandos = []

    def shell(partes):
        comandos.append(partes)
        return type("R", (), {"output": {"pidof": "4321", "ps": "     ELAPSED\n  16:41:00",
                                         "dumpsys": meminfo}.get(partes[0], "")})()
    monkeypatch.setattr(app, "shell", shell)
    assert not robo.primeiro_na_tela_final(app, 1, "Mala de Bordo")
    sinais = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DOS_SINAIS_DO_APP, "2000-01-01 00:00:00")
    assert sinais[-1][3].endswith("; o app aberto há 1001 min; a memória do app 503 de 512 MB")
    assert ["dumpsys", "meminfo", robo.ps.PACOTE] in comandos
    app.com_produto = True
    assert robo.primeiro_na_tela_final(app, 1, "Mala de Bordo")
    sinais = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DOS_SINAIS_DO_APP, "2000-01-01 00:00:00")
    assert sinais[-1][3].endswith("; o app aberto há 12 a 24 h; a memória do app 450 MB ou mais")
    faixa = robo.faixa_da_memoria_do_app
    assert [faixa(mb) for mb in (120, 299, 300, 399, 400, 449, 450, 600)] == [
        "menos de 300 MB", "menos de 300 MB", "300 a 400 MB", "300 a 400 MB", "400 a 450 MB", "400 a 450 MB",
        "450 MB ou mais", "450 MB ou mais"]
    # O Android antigo, sem a coluna Rss, tem as mesmas três últimas; sem a linha ou sem a leitura, nada.
    antigo = type("C", (), {"shell": lambda self, partes: type("R", (), {"output": (
        "  Dalvik Heap   200000   190000      100     2000   262144   204800    57344\n")})()})()
    assert robo.casos_robo.memoria_do_app(antigo, robo.ps.PACOTE) == (200, 256)
    assert robo.casos_robo.memoria_do_app(object(), robo.ps.PACOTE) is None
    assert robo.casos_robo.memoria_do_app(type("C", (), {"shell": lambda self, partes: type(
        "R", (), {"output": " App Summary\n           Java Heap:   515072\n"})()})(), robo.ps.PACOTE) is None


class _RelogioDoRobo:
    """O time do robô com o monotonic de mentira (o do asyncio continua o de verdade)."""

    def __init__(self):
        self.agora = 0.0

    def monotonic(self):
        return self.agora

    def __getattr__(self, nome):
        return getattr(time, nome)


def test_titulo_da_ia_lento_diz_onde_o_tempo_foi(monkeypatch):
    # 10/11: o título de um rascunho levou 15 min (das 06:59 às 07:14), e a rodada passou do limite
    # dela sem dizer onde o tempo foi. Os textos que passam de LENTIDAO_DA_IA vão ao registro com o
    # tempo do envio do vídeo, do processamento no Google, da resposta dos modelos e o de fora da IA.
    relogio, duracoes = _RelogioDoRobo(), iter([900.0, 20.0])

    async def textos_do_video(arquivo, nome):
        robo.ps.api_gemini.TEMPOS_DA_IA.update(analises=2, envio=70.0, processamento=720.0, resposta=90.0,
                                               modelos=3)
        if relogio.agora == 0:
            # 12/11: os 21 min de 2 títulos não diziam qual modelo segurou o pedido.
            robo.ps.api_gemini.MAIS_LENTO = {"modelo": "gemini-x", "segundos": 600.0, "resultado": "erro ServerError"}
        relogio.agora += next(duracoes)
        return {"titulo": "Mala de bordo", "violacao": False}
    monkeypatch.setattr(robo.assistente, "textos_do_video", textos_do_video)
    monkeypatch.setattr(robo, "time", relogio)
    assert robo._textos_da_ia({"arquivo": "v.mp4", "nome": "Mala"})["titulo"] == "Mala de bordo"
    linhas = [(r[2], r[3]) for r in robo.registro_processos.sequencia("shopee_video", "título da IA",
                                                                      "2000-01-01 00:00:00")]
    assert ("demorou", "15 min: 2 análises, envio 70 s, processamento do Google 12 min, resposta 90 s "
                       "(3 modelos), fora da IA 20 s; o mais lento: gemini-x, 10 min, erro ServerError") in linhas
    # A rápida não vai ao registro como lenta, e cada texto zera as somas da IA.
    assert robo._textos_da_ia({"arquivo": "v.mp4", "nome": "Mala"})["titulo"] == "Mala de bordo"
    linhas = [r[2] for r in robo.registro_processos.sequencia("shopee_video", "título da IA", "2000-01-01 00:00:00")]
    assert linhas.count("demorou") == 1
    robo.ps.api_gemini.TEMPOS_DA_IA.update(analises=5)
    monkeypatch.setattr(robo.assistente, "textos_do_video", lambda arquivo, nome: _sem_titulo())
    monkeypatch.setattr(robo, "pausa", lambda segundos: None)
    with pytest.raises(robo.Parada):
        robo._textos_da_ia({"arquivo": "v.mp4", "nome": "Mala"})
    assert robo.ps.api_gemini.TEMPOS_DA_IA["analises"] == 0


async def _sem_titulo():
    return None


def test_faixas_do_app_aberto():
    faixa = robo.faixa_do_app_aberto
    assert [faixa(m) for m in (0, 59, 60, 359, 360, 719, 720, 1439, 1440, 5000)] == [
        "menos de 1 h", "menos de 1 h", "1 a 6 h", "1 a 6 h", "6 a 12 h", "6 a 12 h", "12 a 24 h", "12 a 24 h",
        "mais de 1 dia", "mais de 1 dia"]


def test_minutos_do_app_pelo_ps_do_android():
    # O ELAPSED do ps do Android: [[dias-]horas:]minutos:segundos; sem a leitura, None.
    minutos = robo.casos_robo._minutos_do_elapsed
    assert (minutos("05:06"), minutos("02:03:04"), minutos("1-00:00:10"), minutos("  12:00:59 ")) == (5, 123, 1440, 720)
    assert minutos("") is None and minutos("ELAPSED") is None and minutos(None) is None

    class Celular:
        def __init__(self, pids, saida):
            self.respostas = {"pidof": pids, "ps": saida}

        def shell(self, partes):
            return type("R", (), {"output": self.respostas[partes[0]]})()

    assert robo.casos_robo.minutos_do_app(Celular("4321\n", "ELAPSED\n 10:00"), "com.shopee.br") == 10
    assert robo.casos_robo.minutos_do_app(Celular("", "ELAPSED\n 10:00"), "com.shopee.br") is None
    assert robo.casos_robo.minutos_do_app(Celular("4321", ""), "com.shopee.br") is None
    assert robo.casos_robo.minutos_do_app(object(), "com.shopee.br") is None


def test_aviso_do_app_le_o_toast_como_o_uiautomator2_da(monkeypatch):
    # No uiautomator2 (3.7.0, requirements.txt) o last_toast é uma propriedade: chamado como
    # função, dava erro, e o robô nunca lia o aviso do app (o produto que não fica depois do Feito,
    # o Realçar). O caso de 02/11, 15:26, saiu sem dizer se o app avisou alguma coisa.
    import uiautomator2
    assert any(isinstance(vars(classe).get("last_toast"), property) for classe in type.mro(uiautomator2.Device))

    class Celular:
        last_toast = "Produto 1 adicionado"

    assert robo.aviso_do_app(Celular()) == (True, "Produto # adicionado")
    # Pelo histórico do caso (casos_robo), que passa tudo para o celular.
    assert robo.aviso_do_app(robo.casos_robo.com_historico(Celular())) == (True, "Produto # adicionado")

    class SemAviso:
        last_toast = None

    assert robo.aviso_do_app(SemAviso()) == (True, "")

    class Quebrado:
        @property
        def last_toast(self):
            raise RuntimeError("sem o serviço do uiautomator2")

    assert robo.aviso_do_app(Quebrado()) == (False, "")


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


def test_pausa_sem_a_hora_sai_e_os_produtos_a_mais_voltam_quando_os_pontos_deixarem(avisos):
    # Escolha do Rafael (05/11, P153 3): os produtos a mais, parados pela punição de produto, voltam
    # como estavam, até 6, quando os pontos deixarem. A pausa que não guardou a hora sai na rodada
    # seguinte; com 4 pontos ou mais, a escada (P145) continua deixando só o produto do vídeo.
    robo.db.atualizar_config(robo.CHAVE_CONFIG, lambda dados: dados.update(
        robo_produtos_a_mais=False, robo_produtos_a_mais_parados="punição de Produto Irrelevante (03/11/2026 09:00:00)"))
    assert robo.rodada(agora=momento("2026-11-05 15:00")) == "pausado"
    config = robo.ler_config()
    assert config["robo_produtos_a_mais"] is True and not config.get("robo_produtos_a_mais_parados")
    assert _registro_dos_espacos() == ["religados - voltam quando os pontos deixarem"]
    agora = datetime.now(robo.fuso_horario).strftime("%Y-%m-%d %H:%M:%S")
    robo.gravar_estado(saude_pontos=8, saude_lida_em=agora)
    assert robo.espacos_livres(None, {"link": LINK}, PRINCIPAL, {"preco": 50.0}, [], time.monotonic() + 600) == []
    assert _registro_dos_espacos()[-1] == "nenhum - só o produto do vídeo pelos pontos"
    # A pausa de uma punição nova guarda a hora e fica até o Rafael ligar no painel (P73).
    robo.parar_os_produtos_a_mais({"tipo": "Produto Irrelevante", "data": "20/11/2026 10:00:00"})
    config = robo.ler_config()
    assert config["robo_produtos_a_mais"] is False and config["robo_produtos_a_mais_parados_em"][:4] == agora[:4]
    assert robo.religar_a_pausa_sem_hora() is False
    robo.rodada(agora=momento("2026-11-20 15:00"))
    assert robo.ler_config()["robo_produtos_a_mais"] is False
    # Desligados pelo Rafael (sem o motivo da punição), a migração não mexe.
    robo.db.atualizar_config(robo.CHAVE_CONFIG, lambda dados: dados.update(
        robo_produtos_a_mais_parados=None, robo_produtos_a_mais_parados_em=None))
    assert robo.religar_a_pausa_sem_hora() is False and robo.ler_config()["robo_produtos_a_mais"] is False


def test_punicao_de_outro_tipo_nao_mexe_nos_produtos_a_mais(avisos):
    robo.parar_os_produtos_a_mais({"tipo": "Produto Irrelevante", "data": "23/10/2026 19:04:25"})
    assert "O vídeo punido" not in avisos[-1] and "Não achei o rascunho do robô desse vídeo." in avisos[-1]
    robo.db.atualizar_config(robo.CHAVE_CONFIG, lambda dados: dados.update(robo_produtos_a_mais=True))
    assert not robo.apelacoes.de_produto("Violação de Propriedade Intelectual")
    assert robo.apelacoes.de_produto("Produto Irrelevante")


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

    def editar_para_postar(video, foto, destino, produto="", avisos=False, outras_fotos=(), rotulo_de_ia=False,
                           anotar=None):
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


def _puff(cor, luz=0):
    """O mesmo modelo fotografado do mesmo jeito, na cor pedida (e com um pouco mais de luz)."""
    from PIL import Image, ImageDraw
    mais = lambda c: tuple(min(255, max(0, v) + luz) for v in c)
    imagem = Image.new("RGB", (600, 600), mais((245, 245, 245)))
    desenho = ImageDraw.Draw(imagem)
    desenho.ellipse((150, 120, 450, 300), fill=mais(cor))
    desenho.rectangle((180, 300, 420, 470), fill=mais(tuple(v - 40 for v in cor)))
    desenho.rectangle((160, 470, 440, 490), fill=mais((200, 160, 60)))
    saida = io.BytesIO()
    imagem.save(saida, format="JPEG")
    return saida.getvalue()


def test_mesma_foto_olha_tambem_a_cor():
    # O mesmo modelo em outra cor, fotografado igual, dava a mesma marca (ela é do desenho, em preto
    # e branco) e ficava de fora da miniatura que troca, contra a regra do Rafael (01/11: toda
    # variação entra na miniatura). A mesma foto com um pouco mais de luz continua a mesma.
    cinza = _puff((128, 128, 128))
    assert robo.mesma_foto(cinza, _puff((240, 110, 170))) is False
    assert robo.mesma_foto(cinza, _puff((70, 110, 200))) is False
    assert robo.mesma_foto(cinza, _puff((128, 128, 128), luz=8)) is True


def _viseira(lente=(235, 160, 20), descida=0, faixa=False):
    """
    A foto de uma viseira num carro (a do vídeo do Rafael de 02/11), recortada de uma cena maior:
    com descida, a loja desceu a foto esses px e pôs no alto uma faixa com o nome dela.
    """
    from PIL import Image, ImageDraw
    cena = Image.new("RGB", (700, 760), (55, 55, 62))
    desenho = ImageDraw.Draw(cena)
    for x in range(0, 700, 46):
        desenho.rectangle((x, 470, x + 26, 760), fill=(205, 205, 215))
    desenho.rectangle((170, 120, 300, 230), fill=(215, 215, 220))
    desenho.polygon(((180, 230), (600, 200), (620, 400), (210, 430)), fill=lente)
    desenho.ellipse((60, 260, 190, 380), fill=(225, 175, 145))
    imagem = cena.crop((50, 80 - descida, 650, 680 - descida))
    if faixa:
        ImageDraw.Draw(imagem).rectangle((0, 0, 599, descida), fill=(250, 250, 250))
        for x in range(10, 200, 22):
            ImageDraw.Draw(imagem).rectangle((x, 12, x + 14, 30), fill=(20, 120, 90))
    saida = io.BytesIO()
    imagem.save(saida, format="JPEG", quality=85)
    return saida.getvalue()


def test_mesma_foto_de_outra_loja_descida_e_com_o_nome_da_loja_conta_uma_vez(monkeypatch):
    # Vídeo do Rafael de 02/11 (a viseira): a foto do 3º link era a do 1º descida uns 9% por uma
    # faixa com o nome da loja no alto, e a miniatura que troca a mostrou duas vezes. Ele pediu que
    # essas pequenas diferenças de edição contem como a mesma foto: o tempo fica só com as fotos
    # diferentes (P116). O mesmo modelo em outra cor continua outra foto.
    original, da_loja = _viseira(), _viseira(descida=54, faixa=True)
    assert robo.mesma_foto(original, da_loja) is True and robo.mesma_foto(da_loja, original) is True
    assert robo.mesma_foto(original, _viseira(lente=(40, 90, 200), descida=54, faixa=True)) is False
    assert robo.mesma_foto(original, _viseira(lente=(40, 90, 200))) is False
    # Na miniatura que troca, a da loja não ganha tempo: a do 1º e a outra cor dividem o vídeo.
    monkeypatch.setattr(robo.videos, "duracao", lambda caminho: 24.0)
    azul = _viseira(lente=(40, 90, 200))
    assert robo.fotos_da_miniatura({"arquivo": "v.mp4"}, original, [da_loja, azul]) == [azul]


def test_miniatura_troca_para_o_mesmo_modelo_em_outra_cor(monkeypatch):
    rosa = _puff((240, 110, 170))
    monkeypatch.setattr(robo.videos, "duracao", lambda caminho: 30.0)
    video = {"arquivo": "v.mp4"}
    assert robo.fotos_da_miniatura(video, _puff((128, 128, 128)), [rosa, _puff((128, 128, 128), luz=8)]) == [rosa]


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


class GradeQueCarrega(AppDaGrade):
    """A grade cujas capas carregam depois de uns prints (os de antes, quadros de uma cor só)."""

    def __init__(self, telas, prints):
        super().__init__(telas)
        self.prints = list(prints)

    def screenshot(self, caminho=None):
        return self.prints.pop(0) if len(self.prints) > 1 else self.prints[0]


def test_visualizacoes_sem_nenhum_achado_dizem_o_que_a_grade_mostrou_e_guardam_o_caso(monkeypatch):
    # 09/11, 00:39: 0 de 36 achados (31 de 32 na véspera), e nada dizia por quê. Sem nenhuma capa
    # carregada na tela, o print vai de novo, como no post; sem nenhum achado, o registro diz o
    # que a grade mostrou e o caso guarda a tela.
    monkeypatch.setattr(robo, "ir_ao_perfil", lambda d: None)
    casos = []
    monkeypatch.setattr(robo, "_guardar_caso", lambda d, acao, resultado, motivo, **k: casos.append((acao, motivo)))
    agora = momento("2026-10-30 09:00")
    r = _rascunho("postado", postado_em="2026-10-29 10:00:00", marca=_marca(11))
    cinza = _tela_da_grade([(361, 1210, None, ["57"]), (722, 1210, None, ["980"])])
    carregada = _tela_da_grade([(361, 1210, 11, ["57"]), (722, 1210, 12, ["980"])])
    app = GradeQueCarrega([cinza], [cinza[1], cinza[1], carregada[1]])
    assert robo.anotar_visualizacoes(app, agora) == (1, 1)                 # achado no 3º print
    assert robo.pegar(r)["vistas"] == [["2026-10-30 09:00:00", 57]] and not casos

    def registro():
        return consultar("SELECT detalhe, ok FROM registro_processos WHERE processo = ? ORDER BY rowid DESC",
                         robo.PROCESSO_DAS_VISUALIZACOES)

    # Capas carregadas, mas de outros vídeos: a marca mais perto diz o quanto faltou.
    outra = _tela_da_grade([(361, 1210, 13, ["57"]), (722, 1210, 14, [])])
    assert robo.anotar_visualizacoes(AppDaGrade([outra]), agora) == (0, 1)
    detalhe, ok = registro()
    assert not ok and detalhe.startswith("0 de 1 vídeo(s); na grade: 2 quadro(s), 1 com o número, 2 com a capa, "
                                         "a marca mais perto: ")
    assert casos == [("visualizacoes", robo.MOTIVO_DAS_VISUALIZACOES)]
    assert robo.passo_do_motivo(robo.MOTIVO_DAS_VISUALIZACOES) == "visualizações na grade"
    # Nenhuma capa carregou nem depois das esperas.
    assert robo.anotar_visualizacoes(AppDaGrade([cinza]), agora) == (0, 1)
    assert registro() == ("0 de 1 vídeo(s); na grade: 2 quadro(s), 2 com o número, 0 com a capa", 0)


def test_sem_video_com_marca_nao_abre_o_perfil(monkeypatch):
    monkeypatch.setattr(robo, "ir_ao_perfil", lambda d: pytest.fail("não precisava abrir o Perfil"))
    _rascunho("postado", postado_em="2026-10-29 10:00:00")
    assert robo.anotar_visualizacoes(object(), momento("2026-10-30 09:00")) == (0, 0)


# --- A capa com a frase no post (P125 e P129) ---

def _foto_do_anuncio():
    """Uma foto com desenho (um degradê azul), para a marca da capa na grade sair."""
    from PIL import Image
    foto = Image.new("RGB", (800, 800))
    foto.putdata([(40 + x // 8, 100 + y // 6, 200) for y in range(800) for x in range(800)])
    saida = io.BytesIO()
    foto.save(saida, "JPEG")
    return saida.getvalue()


def test_post_com_a_capa_com_a_frase_diz_se_a_faixa_chegou_a_grade():
    # A capa com a frase abre o vídeo (P125): no post, o registro diz se a faixa chegou à grade.
    from PIL import Image
    caixa = (722, 1210, 722 + LARGURA_DO_QUADRO, 1210 + ALTURA_DO_QUADRO)

    def grade(capa_png):
        tela = Image.new("RGB", (1080, 2400), (240, 240, 240))
        capa = Image.open(io.BytesIO(capa_png)).convert("RGB").crop((0, 196, 720, 1116))
        tela.paste(capa.resize((LARGURA_DO_QUADRO, ALTURA_DO_QUADRO)), caixa[:2])
        return type("Celular", (), {"screenshot": lambda self, caminho=None: tela})()

    capa = robo.edicao_video.capa_com_chamada(_foto_do_anuncio(), "Alivia a dor")
    com = _rascunho("postado", postado_em="2026-10-31 10:00:00", chamada="1")
    assert robo.marcar_o_post(grade(capa), com, caixa)
    sem = _rascunho("postado", postado_em="2026-10-31 11:00:00", chamada="1")
    assert robo.marcar_o_post(grade(robo.edicao_video.foto_em_tela_cheia(_foto_do_anuncio())), sem, caixa)
    # Sem a capa com a frase, nada a dizer.
    outro = _rascunho("postado", postado_em="2026-10-31 12:00:00")
    assert robo.marcar_o_post(grade(capa), outro, caixa)
    linhas = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_CAPA, "2000-01-01 00:00:00")
    assert [r[2] for r in linhas] == ["no post com a faixa", "no post sem a faixa"]


def test_post_diz_se_a_grade_usou_o_1o_quadro_com_a_faixa_de_lado_a_lado():
    # Escolha do Rafael (02/11, P129): o 1º quadro do vídeo vai com a capa da grade e o resto da
    # abertura com a do vídeo aberto. No post, o registro diz qual a grade mostrou: a faixa de lado
    # a lado (o 1º quadro) ou a faixa só no meio (outro quadro da abertura).
    from PIL import Image
    caixa = (722, 1210, 722 + LARGURA_DO_QUADRO, 1210 + ALTURA_DO_QUADRO)
    ev = robo.edicao_video

    def grade(capa_png):
        tela = Image.new("RGB", (1080, 2400), (240, 240, 240))
        esquerda, direita = ev.LADOS_NA_GRADE
        cima, baixo = ev.VISIVEL_NA_GRADE
        capa = Image.open(io.BytesIO(capa_png)).convert("RGB").crop((esquerda, cima, direita, baixo))
        tela.paste(capa.resize((LARGURA_DO_QUADRO, ALTURA_DO_QUADRO)), caixa[:2])
        return type("Celular", (), {"screenshot": lambda self, caminho=None: tela})()

    da_grade = ev.capa_com_chamada(_foto_do_anuncio(), "Alivia a dor")
    do_video = ev.capa_com_chamada(_foto_do_anuncio(), "Alivia a dor", no_video=True)
    um = _rascunho("postado", postado_em="2026-10-31 10:00:00", chamada="1")
    assert robo.marcar_o_post(grade(da_grade), um, caixa)
    outro = _rascunho("postado", postado_em="2026-10-31 11:00:00", chamada="1")
    assert robo.marcar_o_post(grade(do_video), outro, caixa)
    linhas = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_CAPA, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in linhas] == [("no post com a faixa", robo.LADOS_DA_CAPA[True]),
                                              ("no post com a faixa", robo.LADOS_DA_CAPA[False])]


def test_post_confere_a_faixa_da_capa_na_cor_do_produto():
    # P159 2: a faixa da capa vai na cor do produto, e o post a procura na cor que o rascunho guardou;
    # sem a cor guardada, procura o laranja de sempre.
    from PIL import Image
    caixa = (722, 1210, 722 + LARGURA_DO_QUADRO, 1210 + ALTURA_DO_QUADRO)
    ev = robo.edicao_video

    def grade(capa_png):
        tela = Image.new("RGB", (1080, 2400), (240, 240, 240))
        esquerda, direita = ev.LADOS_NA_GRADE
        cima, baixo = ev.VISIVEL_NA_GRADE
        capa = Image.open(io.BytesIO(capa_png)).convert("RGB").crop((esquerda, cima, direita, baixo))
        tela.paste(capa.resize((LARGURA_DO_QUADRO, ALTURA_DO_QUADRO)), caixa[:2])
        return type("Celular", (), {"screenshot": lambda self, caminho=None: tela})()

    capa = ev.capa_com_chamada(_foto_do_anuncio(), "Alivia a dor", cor=ev.CORES_DO_PRODUTO["verde"])
    com_a_cor = _rascunho("postado", postado_em="2026-10-31 10:00:00", chamada="1", cor="verde")
    assert robo.marcar_o_post(grade(capa), com_a_cor, caixa)
    sem_a_cor = _rascunho("postado", postado_em="2026-10-31 11:00:00", chamada="1")
    assert robo.marcar_o_post(grade(capa), sem_a_cor, caixa)
    linhas = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_CAPA, "2000-01-01 00:00:00")
    # O registro diz quando a faixa procurada era a da cor do produto (a 1ª capa colorida na grade); sem
    # a faixa, quanto do quadro tem a cor dela (aqui, a faixa verde procurada no laranja: nada).
    assert [(r[2], r[3]) for r in linhas] == [("no post com a faixa", f"{robo.LADOS_DA_CAPA[True]}; {robo.COR_NA_CAPA}"),
                                              ("no post sem a faixa", "0% do quadro na cor da faixa")]


def test_post_acha_a_faixa_na_miniatura_comprimida_com_a_frase_em_duas_linhas():
    # Retomada de 12/11: o post das 02:06 chegou à grade com a faixa azul e a frase em duas linhas, e a
    # cor a 5 da edição, mas saiu "sem a faixa": a miniatura que a grade mostra vem comprimida, e a
    # faixa achada linha a linha se desmonta. Sem ela, vale a parte de cima do quadro, na cor de lado a
    # lado; o quadro sem a faixa continua sem ela.
    from PIL import Image
    ev = robo.edicao_video
    caixa = (722, 1210, 722 + LARGURA_DO_QUADRO, 1210 + ALTURA_DO_QUADRO)
    foto = Image.new("RGB", (800, 800))
    foto.putdata([(200 + x // 16, 120 + y // 10, 60) for y in range(800) for x in range(800)])
    saida = io.BytesIO()
    foto.save(saida, "JPEG")
    azul = ev.cor_guardada("azul")

    def comprimida(capa_png):
        # A miniatura da grade: a capa em metade do tamanho do quadro, em JPEG fraco, esticada no quadro.
        quadro = Image.open(io.BytesIO(capa_png)).convert("RGB").crop(
            (0, ev.GRADE_NO_CELULAR[0], ev.TELA[0], ev.GRADE_NO_CELULAR[1]))
        miniatura = io.BytesIO()
        quadro.resize((LARGURA_DO_QUADRO // 2, ALTURA_DO_QUADRO // 2)).save(miniatura, "JPEG", quality=20)
        tela = Image.new("RGB", (1080, 2400), (255, 255, 255))
        tela.paste(Image.open(io.BytesIO(miniatura.getvalue())).convert("RGB").resize(
            (LARGURA_DO_QUADRO, ALTURA_DO_QUADRO), Image.BILINEAR), caixa[:2])
        return tela

    com = comprimida(ev.capa_com_chamada(saida.getvalue(), "Vestido jeans", cor=azul))
    faixa = robo.faixa_da_capa(com, caixa, azul)
    assert faixa and faixa[0] == caixa[1] and faixa[3] - faixa[2] >= LARGURA_DO_QUADRO * robo.LARGURA_DA_FAIXA_NA_CAPA
    assert robo.diferenca_da_cor(com, faixa, azul) <= 20
    assert robo.faixa_da_capa(comprimida(ev.foto_em_tela_cheia(saida.getvalue())), caixa, azul) is None
    # No post, o registro diz que a faixa chegou, sem outra olhada nem caso.
    rascunho = _rascunho("postado", postado_em="2026-11-12 02:06:00", chamada="1", cor="azul")
    celular = type("Celular", (), {"screenshot": lambda self, caminho=None: com})()
    assert robo.marcar_o_post(celular, rascunho, caixa)
    linhas = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_CAPA, "2000-01-01 00:00:00")
    assert [r[2] for r in linhas] == ["no post com a faixa"]


def test_post_sem_a_faixa_olha_de_novo_e_guarda_o_caso(monkeypatch):
    # Checkup de 11/11: o post das 21:37 chegou à grade sem a faixa, e nada dizia por quê. A capa que
    # ainda carrega ganha outra olhada; a que continua sem a faixa vai ao registro com quanto do quadro
    # tem a cor dela, e o caso guarda o print da grade e os quadros do vídeo para o checkup.
    from PIL import Image
    caixa = (722, 1210, 722 + LARGURA_DO_QUADRO, 1210 + ALTURA_DO_QUADRO)
    ev = robo.edicao_video
    casos = []
    monkeypatch.setattr(robo, "_guardar_caso", lambda d, acao, resultado, motivo, **k: casos.append((acao, resultado,
                                                                                                    motivo)))

    def tela(capa_png):
        imagem = Image.new("RGB", (1080, 2400), (240, 240, 240))
        esquerda, direita = ev.LADOS_NA_GRADE
        cima, baixo = ev.VISIVEL_NA_GRADE
        capa = Image.open(io.BytesIO(capa_png)).convert("RGB").crop((esquerda, cima, direita, baixo))
        imagem.paste(capa.resize((LARGURA_DO_QUADRO, ALTURA_DO_QUADRO)), caixa[:2])
        return imagem

    def celular(*prints):
        fila = list(prints)
        return type("Celular", (), {"screenshot": lambda self, caminho=None: fila.pop(0) if len(fila) > 1 else fila[0]})()

    capa = tela(ev.capa_com_chamada(_foto_do_anuncio(), "Alivia a dor"))
    sem_faixa = tela(ev.foto_em_tela_cheia(_foto_do_anuncio()))
    # A capa que chega na 2ª olhada: com a faixa, e a marca dela.
    devagar = _rascunho("postado", postado_em="2026-10-31 10:00:00", chamada="1")
    assert robo.marcar_o_post(celular(sem_faixa, capa), devagar, caixa) == robo.visualizacoes.marca_da_capa(capa, caixa)
    # A que não chega nem na última: o registro com quanto do quadro tem a cor, e o caso.
    nunca = _rascunho("postado", postado_em="2026-10-31 11:00:00", chamada="1")
    assert robo.marcar_o_post(celular(sem_faixa), nunca, caixa) == robo.pegar(nunca)["marca"]
    linhas = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_CAPA, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in linhas] == [("no post com a faixa", robo.LADOS_DA_CAPA[True]),
                                              ("no post sem a faixa", "0% do quadro na cor da faixa")]
    assert casos == [("postar", "capa sem a faixa", robo.MOTIVO_DA_CAPA_SEM_A_FAIXA)]
    # Sem a capa com a frase, nada de outra olhada nem de caso.
    sem_chamada = _rascunho("postado", postado_em="2026-10-31 12:00:00")
    assert robo.marcar_o_post(celular(sem_faixa, capa), sem_chamada, caixa) == robo.visualizacoes.marca_da_capa(
        sem_faixa, caixa)
    assert len(casos) == 1


def test_post_anota_a_que_distancia_da_cor_da_edicao_a_faixa_chegou():
    # P204 1: o vídeo vai na tabela de cores do HD, e o registro diz a que distância da cor da
    # edição a faixa chegou à grade (com a tabela errada, o rosa chegava a 27 dela, mais claro).
    from PIL import Image, ImageDraw
    caixa = (722, 1210, 722 + LARGURA_DO_QUADRO, 1210 + ALTURA_DO_QUADRO)
    ev = robo.edicao_video
    rosa, rosa_lavado = ev.CORES_DO_PRODUTO["rosa"], (240, 105, 148)

    tela = Image.new("RGB", (400, 300), (240, 240, 240))
    desenho = ImageDraw.Draw(tela)
    desenho.rectangle([0, 0, 399, 99], fill=rosa_lavado)
    desenho.rectangle([150, 30, 250, 70], fill=(255, 255, 255))   # as letras ficam de fora da conta
    assert robo.diferenca_da_cor(tela, (0, 100, 0, 400), rosa) == 27
    assert robo.diferenca_da_cor(tela, (0, 100, 0, 400), (20, 200, 20)) is None
    assert [robo.faixa_da_diferenca_da_cor(d) for d in (0, 10, 11, 20, 27, 40, 41)] == [
        "até 10 da cor da edição", "até 10 da cor da edição", "de 11 a 20 da cor da edição",
        "de 11 a 20 da cor da edição", "de 21 a 40 da cor da edição", "de 21 a 40 da cor da edição",
        "mais de 40 da cor da edição"]

    def grade(capa_png):
        quadro = Image.new("RGB", (1080, 2400), (240, 240, 240))
        esquerda, direita = ev.LADOS_NA_GRADE
        cima, baixo = ev.VISIVEL_NA_GRADE
        capa = Image.open(io.BytesIO(capa_png)).convert("RGB").crop((esquerda, cima, direita, baixo))
        quadro.paste(capa.resize((LARGURA_DO_QUADRO, ALTURA_DO_QUADRO)), caixa[:2])
        return type("Celular", (), {"screenshot": lambda self, caminho=None: quadro})()

    capa = ev.capa_com_chamada(_foto_do_anuncio(), "Alivia a dor", cor=rosa)
    certo = _rascunho("postado", postado_em="2026-10-31 10:00:00", chamada="1", cor="rosa")
    assert robo.marcar_o_post(grade(capa), certo, caixa)
    # A mesma capa como chegava com a tabela errada: o rosa da faixa mais claro, as letras brancas iguais.
    import numpy
    pontos = numpy.array(Image.open(io.BytesIO(capa)).convert("RGB"))
    pontos[(pontos == rosa).all(axis=2)] = rosa_lavado
    saida = io.BytesIO()
    Image.fromarray(pontos).save(saida, "PNG")
    lavado = _rascunho("postado", postado_em="2026-10-31 11:00:00", chamada="1", cor="rosa")
    assert robo.marcar_o_post(grade(saida.getvalue()), lavado, caixa)
    linhas = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_COR_DA_CAPA, "2000-01-01 00:00:00")
    assert [r[2] for r in linhas] == ["até 10 da cor da edição", "de 21 a 40 da cor da edição"]


def test_post_confere_a_faixa_no_tom_que_o_rascunho_guardou():
    # P174 3: sem a 2ª cor, a faixa vai num tom da cor do produto, e o rascunho guarda o #rrggbb
    # dele; o post procura a faixa nesse tom, não no laranja.
    from PIL import Image
    caixa = (722, 1210, 722 + LARGURA_DO_QUADRO, 1210 + ALTURA_DO_QUADRO)
    ev = robo.edicao_video
    tom = (176, 176, 176)
    capa = Image.open(io.BytesIO(ev.capa_com_chamada(_foto_do_anuncio(), "Alivia a dor", cor=tom))).convert("RGB")
    esquerda, direita = ev.LADOS_NA_GRADE
    cima, baixo = ev.VISIVEL_NA_GRADE
    tela = Image.new("RGB", (1080, 2400), (240, 240, 240))
    tela.paste(capa.crop((esquerda, cima, direita, baixo)).resize((LARGURA_DO_QUADRO, ALTURA_DO_QUADRO)), caixa[:2])
    celular = type("Celular", (), {"screenshot": lambda self, caminho=None: tela})()
    rascunho = _rascunho("postado", postado_em="2026-10-31 10:00:00", chamada="1", cor=ev.nome_da_cor(tom))
    assert robo.marcar_o_post(celular, rascunho, caixa)
    linhas = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_CAPA, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in linhas] == [("no post com a faixa", f"{robo.LADOS_DA_CAPA[True]}; {robo.COR_NA_CAPA}")]


def test_post_acha_a_faixa_que_desce_ate_embaixo_com_o_numero_por_cima():
    # P168: na grade do celular do Rafael (a largura toda, GRADE_NO_CELULAR), a faixa da capa desce
    # até o fim do quadro, e o número de visualizações do app fica por cima dela, em branco. O post
    # continua achando a faixa de lado a lado, também na cor clara do produto (letra preta), em que a
    # faixa desce até embaixo na mesma cor (P171) e o branco do número não é uma das cores dela.
    from PIL import Image, ImageDraw
    caixa = (722, 1210, 722 + LARGURA_DO_QUADRO, 1210 + ALTURA_DO_QUADRO)
    ev = robo.edicao_video
    alto, baixo = ev.GRADE_NO_CELULAR
    x1, y1, x2, y2 = ev.NUMERO_DA_GRADE

    def grade(capa_png):
        capa = Image.open(io.BytesIO(capa_png)).convert("RGB").crop((0, alto, 720, baixo))
        desenho = ImageDraw.Draw(capa)
        desenho.polygon([(x1, y1 - alto + 8), (x1, y2 - alto - 8), (x1 + 34, (y1 + y2) // 2 - alto)],
                        outline=(255, 255, 255), width=5)
        desenho.rectangle((x1 + 60, y1 - alto + 8, x1 + 140, y2 - alto - 8), fill=(255, 255, 255))
        tela = Image.new("RGB", (1080, 2400), (240, 240, 240))
        tela.paste(capa.resize((caixa[2] - caixa[0], caixa[3] - caixa[1])), caixa[:2])
        return type("Celular", (), {"screenshot": lambda self, caminho=None: tela})()

    for n, nome in enumerate((None, "amarelo")):
        cor = ev.CORES_DO_PRODUTO.get(nome)
        capa = ev.capa_com_chamada(_foto_do_anuncio(), "Alivia a dor", cor=cor)
        rascunho = _rascunho("postado", postado_em=f"2026-10-31 1{n}:00:00", chamada="1", cor=nome or "")
        assert robo.marcar_o_post(grade(capa), rascunho, caixa), nome
    linhas = robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_CAPA, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in linhas] == [("no post com a faixa", robo.LADOS_DA_CAPA[True]),
                                              ("no post com a faixa", f"{robo.LADOS_DA_CAPA[True]}; {robo.COR_NA_CAPA}")]


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


# --- Tirar produto no post (P123) ---

LINKS_DOS_CUBOS = {"B": "https://s.shopee.com.br/cubo-b", "C": "https://s.shopee.com.br/cubo-c"}


def _com_tres_produtos(estado="aprovado", **campos):
    """Um rascunho de link com o produto do vídeo e 2 produtos a mais."""
    ident = _rascunho(estado, postar_em="2026-10-22 12:00:00")
    robo.atualizar(ident, produtos=["Cubo A", "Cubo B", "Cubo C"],
                   mais_produtos=[{"nome": f"Cubo {letra}", "link": link, "endereco": ""}
                                  for letra, link in LINKS_DOS_CUBOS.items()],
                   itens=[{"item": str(n), "a_mais": n > 1} for n in (1, 2, 3)], **campos)
    return ident


def _post_com_os_passos(monkeypatch, tirar_da_fileira=None):
    """O publicar com o celular de mentira: cada passo anotado, e a tela final que sempre confere."""
    passos, levados = [], []
    monkeypatch.setattr(robo, "ler_suspensao", lambda d, agora=None: None)
    monkeypatch.setattr(robo, "abrir_rascunho", lambda d, rascunho: passos.append("abrir"))
    monkeypatch.setattr(robo.ps, "tirar_da_fileira", tirar_da_fileira or (
        lambda d, nomes, indice: passos.append(("tirar", list(nomes), indice)) or (True, "saiu")))
    monkeypatch.setattr(robo.ps, "conferir_tela_final",
                        lambda d, video: passos.append(("conferir", video["produtos"])) or (True, "confere"))
    monkeypatch.setattr(robo.ps, "ajustar_rotulo_de_ia", lambda d, ligado: (True, "rótulo"))
    monkeypatch.setattr(robo.ps, "postar", lambda d, video: passos.append(("postar", video["produtos"])) or (True, "ok"))
    monkeypatch.setattr(robo, "link_do_post", lambda d, ident=None, agora=None: LINK_DO_POST)
    monkeypatch.setattr(robo, "levar_ao_canal", lambda rascunho, link_post: levados.append(rascunho))
    return passos, levados


def test_post_tira_os_produtos_marcados_e_guarda_so_os_que_ficaram(monkeypatch, avisos):
    # Escolha do Rafael (02/11, P123): ele marca os produtos que saem do post e aprova; na hora de
    # postar, o robô os tira da tela final pelo X, do último para o primeiro (tirar um não muda a
    # posição dos de antes), confere a tela final só com os que ficam e posta. O Canal Afiliados e
    # a medição das vendas recebem só os que ficaram.
    ident = _com_tres_produtos(tirar=[1, 2], outra_cor=[3], outras_capas=[2],
                               capas=["/x/9_capa_1.jpg", "/x/9_capa_3.jpg"])
    passos, levados = _post_com_os_passos(monkeypatch)
    assert robo.publicar(object(), robo.pegar(ident), momento("2026-10-22 12:00")) == "rascunho aprovado postado"
    assert passos == ["abrir", ("tirar", ["Cubo A", "Cubo B", "Cubo C"], 1), ("tirar", ["Cubo A", "Cubo C"], 0),
                      ("conferir", ["Cubo C"]), ("postar", ["Cubo C"])]
    postado = robo.pegar(ident)
    assert (postado["estado"], postado["produtos"], postado["link"], postado["mais_produtos"]) == (
        "postado", ["Cubo C"], LINKS_DOS_CUBOS["C"], [])
    assert postado["itens"] == [{"item": "3", "a_mais": True}] and postado["capas"] == ["/x/9_capa_3.jpg"]
    assert (postado["outra_cor"], postado["outras_capas"], postado["tirar"]) == ([1], [], [])
    assert [(r["produtos"], r["link"]) for r in levados] == [(["Cubo C"], LINKS_DOS_CUBOS["C"])]
    assert avisos[0].startswith("✅ Robô da Shopee Vídeo: postei o vídeo que você aprovou, sem os produtos que "
                                "você marcou para sair (2 de 3).")
    assert consultar("SELECT resultado, detalhe, ok FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DE_TIRAR) == ("tirados", "2 de 3 produtos", 1)


def test_post_sem_marca_vai_com_todos_os_produtos(monkeypatch, avisos):
    ident = _com_tres_produtos()
    passos, levados = _post_com_os_passos(monkeypatch)
    robo.publicar(object(), robo.pegar(ident), momento("2026-10-22 12:00"))
    assert passos == ["abrir", ("postar", ["Cubo A", "Cubo B", "Cubo C"])]
    assert robo.pegar(ident)["produtos"] == ["Cubo A", "Cubo B", "Cubo C"] and levados[0]["link"] == LINK
    assert avisos[0].startswith("✅ Robô da Shopee Vídeo: postei o vídeo que você aprovou.\n\n")


def test_produto_marcado_que_nao_sai_para_o_post_sem_postar(monkeypatch, avisos):
    # Nunca vai ao ar com um produto que o Rafael mandou tirar: para sem tocar em mais nada, e o
    # aprovado tenta de novo (P99), com o app sem salvar e com todos os produtos de novo.
    ident = _com_tres_produtos(tirar=[2])
    passos, _ = _post_com_os_passos(monkeypatch, lambda d, nomes, indice: (False, "não achei o X do produto na fileira"))
    with pytest.raises(robo.Parada) as parou:
        robo.publicar(object(), robo.pegar(ident), momento("2026-10-22 12:00"))
    assert parou.value.motivo == ("não consegui tirar o 2º produto, que você marcou para sair do post: não achei o X "
                                  "do produto na fileira") and not parou.value.do_video
    assert passos == ["abrir"] and robo.pegar(ident)["estado"] == "aprovado"
    assert robo.pegar(ident)["produtos"] == ["Cubo A", "Cubo B", "Cubo C"] and robo.pegar(ident)["tirar"] == [2]
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = ?",
                     robo.PROCESSO_DE_TIRAR) == ("de fora", 0)


def test_com_os_que_ficam_no_ver_produtos_e_quando_nao_da_para_tirar():
    # No Ver Produtos, o link do rascunho é o do vídeo original e cada produto tem o seu.
    ident = _rascunho()
    robo.atualizar(ident, produtos=["A", "B", "C"], links_dos_produtos=["https://a", "", "https://c"], outra_cor=[2],
                   tirar=[1])
    filtrado = robo.com_os_que_ficam(robo.pegar(ident))
    assert (filtrado["produtos"], filtrado["links_dos_produtos"], filtrado["link"]) == (
        ["B", "C"], ["", "https://c"], LINK)
    assert filtrado["outra_cor"] == [1] and filtrado["tirar"] == []
    # Sem marca, com todas (o painel não deixa) ou com um produto só: o mesmo rascunho.
    for tirar, produtos in (([], ["A", "B", "C"]), ([1, 2, 3], ["A", "B", "C"]), ([1], ["A"])):
        robo.atualizar(ident, tirar=tirar, produtos=produtos, links_dos_produtos=[""] * len(produtos))
        rascunho = robo.pegar(ident)
        assert robo.com_os_que_ficam(rascunho) is rascunho
    # O rascunho de link sem um link por produto não deixa tirar (não dá para saber qual sai).
    assert not robo.pode_tirar({"produtos": ["A", "B"], "mais_produtos": []})
    assert robo.pode_tirar({"produtos": ["A", "B"], "mais_produtos": [{"link": "b"}]})


def test_plano_do_dia_guarda_a_faixa_e_os_pontos_com_que_foi_feito():
    # 06/11: o plano saiu com 1 rascunho com 8 pontos, e nada mostrava com que faixa ele foi feito.
    # O plano guarda a faixa e os pontos, para o checkup e o painel mostrarem.
    config = {**robo.PADRAO, "robo_limite_min": 8, "robo_limite_max": 12}
    robo.gravar_estado(saude_pontos=8, saude_lida_em="2026-11-05 10:00:00")
    agora = datetime(2026, 11, 6, 0, 5, tzinfo=fuso_horario)
    estado = robo.estado_do_dia(config, agora)
    assert estado["feito_com"] == {"faixa": [8, 12], "pontos": 8} and 2 <= len(estado["horarios"]) <= 3
    # O plano refeito (o Horário das Interações mudou) guarda o que vale agora.
    robo.replanejar_hoje({**config, "robo_limite_min": 1, "robo_limite_max": 2}, agora)
    assert robo.db.ler_config(robo.CHAVE_DIA)["feito_com"] == {"faixa": [1, 2], "pontos": 8}


def test_plano_do_dia_segue_a_escada_dos_pontos_e_so_vai_o_produto_do_video():
    # Escolha do Rafael (03/11, P145): com 4 pontos de penalidade ou mais, o dia faz a parte da
    # faixa do painel até o teto do degrau, e só o produto do vídeo vai ao post.
    import apelacoes_shopee_video as apelacoes
    assert apelacoes.CHAVE_DA_SAUDE == robo.CHAVE_ESTADO
    config = {**robo.PADRAO, "robo_limite_min": 6, "robo_limite_max": 10}
    robo.gravar_estado(saude_pontos=7, saude_lida_em="2026-11-03 10:00:00")
    assert 2 <= robo.quantos_hoje(config, "2026-11-10") <= 3
    robo.gravar_estado(saude_pontos=12)
    assert robo.quantos_hoje(config, "2026-11-10") == 0 and robo.planejar(config, "2026-11-10") == []
    # No trimestre seguinte os pontos zeram, e volta a faixa do painel.
    assert 6 <= robo.quantos_hoje(config, "2027-01-02") <= 10
    robo.gravar_estado(saude_pontos=4, saude_lida_em=datetime.now(robo.fuso_horario).strftime("%Y-%m-%d %H:%M:%S"))
    assert robo.espacos_livres(None, {"link": LINK}, PRINCIPAL, {"preco": 50.0}, [], time.monotonic() + 600) == []
    assert _registro_dos_espacos() == ["nenhum - só o produto do vídeo pelos pontos"]


# --- Fazer Agora (escolha do Rafael, P162 1) ---

def test_fazer_agora_pede_so_o_que_ainda_nao_saiu_hoje_e_uma_vez():
    agora = momento("2026-11-06 15:00")
    assert robo.pedir_agora("saude", agora) == (True, 0, 1)
    assert robo.pedir_agora("saude", agora) == (True, 0, 1)                   # já pedida: não pede de novo
    assert [p["atividade"] for p in robo.pedidos_de_agora(agora)] == ["saude"]
    linhas = [(r[2], r[3]) for r in robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DO_FAZER_AGORA,
                                                                       "2000-01-01 00:00:00")]
    assert linhas == [("pedido", "Saúde do Vídeo")]
    # Já saiu hoje até o limite do dia: não pede.
    robo.gravar_estado(saude_lida_em="2026-11-06 08:10:00", descurtir_em="2026-11-06 04:05:00",
                       descurtir_continuar=False, respostas_leituras={"dia": "2026-11-06", "vezes": 3})
    assert robo.pedir_agora("limpeza", agora) == (False, 1, 1)
    assert robo.pedir_agora("respostas", agora) == (False, 3, 3)
    robo.gravar_estado(respostas_leituras={"dia": "2026-11-06", "vezes": 1})
    assert robo.pedir_agora("respostas", agora) == (True, 1, 3)
    for n in range(robo.interacoes.VIDEOS_NO_FEED_POR_DIA):
        robo.interacoes.guardar(f"video{n}", "video_feed", "comentado", agora)
    assert robo.pedir_agora("feed", agora) == (False, 5, 5)
    # O pedido de outro dia sai sem fazer.
    assert robo.pedidos_de_agora(momento("2026-11-07 08:00")) == []


def test_fazer_agora_roda_na_proxima_folga_mesmo_pausado_e_diz_como_foi(monkeypatch, avisos):
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_inicio": 8, "robo_fim": 22})   # pausado
    feitas = []
    monkeypatch.setattr(robo, "_agir", lambda d, acao, ident, preparar, config, agora, pedido=False, comeco=None:
                        feitas.append((acao, ident, pedido)) or f"{acao} feito")
    agora = momento("2026-11-06 23:10")                                          # fora do Horário do Robô
    assert robo.rodada(d=AppDeMentira(), agora=agora, fazer=True) == "nada a fazer agora"
    robo.pedir_agora("feed", agora)
    robo.pedir_agora("saude", agora)
    assert robo.rodada(d=AppDeMentira(), agora=agora, fazer=True) == "feed feito"
    assert "⏩ Robô da Shopee Vídeo: Feed, do Fazer Agora: feed feito." in avisos
    assert [p["atividade"] for p in robo.pedidos_de_agora(agora)] == ["saude"]
    # A rodada agendada também atende o pedido que espera, antes de tudo; a Saúde manda o resumo dela.
    assert robo.rodada(d=AppDeMentira(), agora=agora) == "saude feito"
    assert feitas == [("feed", None, False), ("saude", None, True)] and robo.pedidos_de_agora(agora) == []
    assert robo.rodada(d=AppDeMentira(), agora=agora) == "pausado"
    # O pedido que saiu na vez dele antes da rodada, ou o post antigo sem post que possa ganhá-lo, não sai.
    robo.pedir_agora("post_antigo", agora)
    assert robo.rodada(d=AppDeMentira(), agora=agora, fazer=True) == (
        "fazer agora: nenhum post dos últimos 30 dias pode ganhar o comentário agora")
    assert "Comentário no Post Antigo, do Fazer Agora: não fiz, porque nenhum post" in avisos[-1]
    robo.pedir_agora("limpeza", agora)
    robo.gravar_estado(descurtir_em="2026-11-06 23:00:00", descurtir_continuar=False)
    assert robo.rodada(d=AppDeMentira(), agora=agora, fazer=True) == "fazer agora: já tinha saído hoje, na vez dela"
    assert len(feitas) == 2
    linhas = [r[2] for r in robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DO_FAZER_AGORA,
                                                               "2000-01-01 00:00:00")]
    assert linhas == ["pedido", "pedido", "na rodada", "na rodada", "pedido", "não saiu", "pedido", "não saiu"]


def test_fazer_agora_na_suspensao_roda_e_sem_o_celular_sai_com_o_aviso(monkeypatch, avisos):
    ativar(robo_inicio=0, robo_fim=24, robo_suspenso_ate="2026-11-10 00:00:00")
    monkeypatch.setattr(robo, "_agir", lambda d, acao, ident, preparar, config, agora, pedido=False, comeco=None:
                        f"{acao} feito")
    agora = momento("2026-11-06 15:00")
    robo.pedir_agora("respostas", agora)
    # A suspensão não fecha nenhuma das atividades do Fazer Agora.
    assert robo.rodada(d=AppDeMentira(), agora=agora, fazer=True) == "responder feito"
    # Sem o celular não há folga para esperar: o pedido sai, com o aviso, e a Postagem não pausa por isso.
    robo.pedir_agora("feed", agora)
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "reconectar_sozinho", lambda: (False, "o celular não responde"))
    assert "desconectado" in robo.rodada(agora=agora, fazer=True)
    assert robo.pedidos_de_agora(agora) == [] and robo.ler_config()["robo_pausado"] is False
    assert "não fiz o que você pediu no Fazer Agora (Feed): o celular do robô está desconectado" in avisos[-1]


# --- Editar ✏️ (P191 1 e P192 1) ---

def _editavel(monkeypatch, tmp_path=None, **campos):
    """Um rascunho de link de produto com o que o Editar ✏️ precisa guardado (o original, a foto, a edição)."""
    os.makedirs(robo.PASTA_RASCUNHOS, exist_ok=True)
    ident = _rascunho(**campos)
    copia = os.path.join(robo.PASTA_RASCUNHOS, f"{ident}.mp4")
    original = os.path.join(robo.PASTA_RASCUNHOS, f"fonte_{ident}.mp4")
    for arquivo in (copia, original):
        with open(arquivo, "wb") as f:
            f.write(b"video")
    refazer = {"textos": {"nome": "Vestido"}, "frase": "", "musica": "", "avisos": False, "rotulo_de_ia": False,
               "escolhas": dict(robo.edicao_video.ESCOLHAS_PADRAO)}
    guardado = robo.guardar_para_o_editar(copia, original, b"\xff\xd8\xfffoto", [b"\xff\xd8\xffoutra"], refazer)
    robo.atualizar(ident, arquivo=copia, edicao=guardado)
    return ident


def test_o_rascunho_guarda_o_que_o_editar_precisa_e_so_o_de_link_de_produto_edita(monkeypatch):
    ident = _editavel(monkeypatch)
    guardado = robo.pegar(ident)["edicao"]
    base = os.path.join(robo.PASTA_RASCUNHOS, str(ident))
    assert guardado["original"] == base + "_original.mp4" and guardado["foto"] == base + "_foto.jpg"
    assert guardado["outras"] == [base + "_outra_1.jpg"] and guardado["versoes"] == 1
    assert open(guardado["original"], "rb").read() == b"video"
    # A faxina conhece os arquivos novos (saem com o rascunho).
    for nome in (f"{ident}_original.mp4", f"{ident}_foto.jpg", f"{ident}_outra_1.jpg", f"{ident}_nova_2.mp4",
                 f"{ident}_nova_2.png"):
        assert robo.ARQUIVO_NO_SERVIDOR.match(nome), nome
    assert robo.pode_editar(robo.pegar(ident))
    # O de Ver Produtos (um link por produto), o aprovado, a versão de antes e o sem os arquivos não editam.
    assert not robo.pode_editar(dict(robo.pegar(ident), links_dos_produtos=["https://s.shopee.com.br/a"]))
    assert not robo.pode_editar(dict(robo.pegar(ident), estado="aprovado"))
    assert not robo.pode_editar(dict(robo.pegar(ident), versao_de="3"))
    assert not robo.pode_editar(dict(robo.pegar(ident), edicao={}))
    # Sem o que a edição guardou, nada é guardado e o rascunho só fica sem o Editar.
    assert robo.guardar_para_o_editar(base + ".mp4", guardado["original"], b"foto", [], None) == {}


def test_editar_faz_a_nova_versao_e_o_aprovar_refaz_o_rascunho_no_app(monkeypatch):
    ident = _editavel(monkeypatch)
    pedidos = []

    def refazer_para_postar(video, foto, destino, guardado, outras_fotos=(), lado=None, legenda=None):
        pedidos.append((video, foto, outras_fotos, lado, legenda))
        with open(destino, "wb") as f:
            f.write(b"nova")
        return "", robo.edicao_video.COM_LEGENDAS
    monkeypatch.setattr(robo.edicao_video, "refazer_para_postar", refazer_para_postar)
    assert robo.escolhas_do_rascunho(robo.pegar(ident)) == ("direita", True)
    ok, como = robo.reeditar(ident, "esquerda", False)
    nova = robo.pegar(ident)["nova_versao"]
    assert ok and nova["arquivo"].endswith(f"{ident}_nova_2.mp4") and nova["versao"] == 2
    assert (nova["miniatura"], nova["legenda"]) == ("esquerda", False)
    assert pedidos[0][1:] == (b"\xff\xd8\xfffoto", [b"\xff\xd8\xffoutra"], "esquerda", False)
    assert robo.escolhas_do_rascunho(robo.pegar(ident)) == ("esquerda", False)
    # O Aprovar com a nova versão: o robô refaz no app antes de marcar a hora de ir ao ar.
    ativar(robo_inicio=0, robo_fim=24)
    agora = momento("2026-10-22 15:00")
    robo.gravar_estado(treino_semana=robo.semana(agora))
    assert robo.aprovar(ident, agora) is None and robo.pegar(ident)["estado"] == "refazer"
    assert robo.pegar(ident)["postar_em"] is None
    assert robo.o_que_fazer(robo.ler_config(), agora) == ("refazer", ident)
    # O que não sai não muda nada.
    monkeypatch.setattr(robo.edicao_video, "refazer_para_postar", lambda *a, **k: ("o ffmpeg falhou", ""))
    outro = _editavel(monkeypatch)
    assert robo.reeditar(outro, "sem", True) == (False, "o ffmpeg falhou") and not robo.pegar(outro)["nova_versao"]
    # Manter o de antes tira a nova versão.
    robo.atualizar(ident, estado="rascunho")
    robo.manter_a_versao_de_antes(ident)
    assert robo.pegar(ident)["nova_versao"] == {} and not os.path.exists(nova["arquivo"])
    assert robo.aprovar(ident, agora) is not None and robo.pegar(ident)["estado"] == "aprovado"


def _celular_do_refazer(monkeypatch, passos, anexados=None):
    """O celular de mentira do refazer: cada passo anotado em passos, sem tocar em tela."""
    def curtir(d, video, produtos, curtidos):
        passos.append(("curtir", [(p["nome"], p["link"], p["do_video"]) for p in produtos]))
        curtidos.extend((p["link"], p["nome"]) for p in produtos)
        return list(produtos)
    monkeypatch.setattr(robo, "_curtir_os_produtos", curtir)
    monkeypatch.setattr(robo, "ir_ao_perfil", lambda d: None)
    monkeypatch.setattr(robo.ps, "por_na_galeria", lambda d, arquivo, nome: passos.append(("galeria", nome)) or True)
    for nome in ("abrir_galeria", "marcar_so_o_mais_novo", "efeitos_na_edicao"):
        monkeypatch.setattr(robo, nome, lambda *a, **k: None)
    monkeypatch.setattr(robo, "seguir", lambda d, caminho: None)

    def anexar(d, video, nomes, a_mais=(), limpa=False, prazo=None, curtidos_de_fora=0):
        passos.append(("anexar", list(nomes), tuple(a_mais)))
        feitos = list(range(len(nomes))) if anexados is None else anexados
        return [nomes[i] for i in feitos], feitos
    monkeypatch.setattr(robo, "anexar_os_produtos", anexar)
    monkeypatch.setattr(robo, "escrever_a_legenda", lambda d, titulo: passos.append(("título", titulo)))
    monkeypatch.setattr(robo.ps, "conferir_tela_final", lambda d, video: (True, "tela final confere"))
    monkeypatch.setattr(robo.ps, "ajustar_rotulo_de_ia", lambda d, ligado: (True, "rótulo"))
    monkeypatch.setattr(robo, "tocar", lambda d, alvo, espera=0: passos.append(("tocar", alvo)))
    monkeypatch.setattr(robo, "tela", lambda d: "")

    def apagar(d, rascunho):
        passos.append(("apagar", rascunho["id"], robo.posicao_no_app(rascunho)))
        robo.atualizar(rascunho["id"], estado="apagado")
        return "rascunho recusado apagado"
    monkeypatch.setattr(robo, "apagar_do_app", apagar)
    monkeypatch.setattr(robo, "descurtir_no_fim", lambda d, video, curtidos: passos.append(("descurtir", len(curtidos))))


class _Tela:
    def screenshot(self, caminho):
        with open(caminho, "wb") as f:
            f.write(b"print")


def test_o_rascunho_editado_e_refeito_no_app_e_so_depois_a_versao_de_antes_sai(monkeypatch, avisos):
    # P192 1: com o Aprovar, o robô refaz o rascunho no app com a nova versão (os mesmos produtos, na mesma
    # ordem, e o mesmo título) e só depois de o novo ficar salvo apaga o de antes, conferindo-o.
    ativar(robo_inicio=0, robo_fim=24)
    mais = [{"nome": "Vestido de Outra Loja", "link": "https://s.shopee.com.br/outra", "endereco": ""}]
    antes = _rascunho("aprovado", criado="2026-10-22 08:00:00", postar_em="2026-10-23 09:00:00")
    ident = _editavel(monkeypatch, criado="2026-10-22 09:00:00")
    robo.atualizar(ident, produtos=[VESTIDO, mais[0]["nome"]], mais_produtos=mais)
    depois = _rascunho("rascunho", criado="2026-10-22 10:00:00")
    nova = os.path.join(robo.PASTA_RASCUNHOS, f"{ident}_nova_2.mp4")
    with open(nova, "wb") as f:
        f.write(b"nova")
    robo.atualizar(ident, estado="refazer", nova_versao={"arquivo": nova, "versao": 2, "miniatura": "esquerda",
                                                          "legenda": False})
    # Na lista do app, do mais novo para o mais velho: o depois, o editado e o antes.
    assert [robo.posicao_no_app(robo.pegar(i)) for i in (depois, ident, antes)] == [0, 1, 2]
    passos = []
    _celular_do_refazer(monkeypatch, passos)
    agora = momento("2026-10-22 15:00")
    assert robo.refazer_no_app(_Tela(), robo.pegar(ident), agora) == "rascunho editado refeito no app"
    assert passos[0] == ("curtir", [(VESTIDO, LINK, True), (mais[0]["nome"], mais[0]["link"], False)])
    assert passos[1] == ("galeria", robo.nome_na_galeria(ident, 2)) == ("galeria", f"robo_shopee_video_{ident}_v2.mp4")
    # Todos os produtos, nenhum como "a mais": o que não anexa para tudo.
    assert passos[2] == ("anexar", [VESTIDO, mais[0]["nome"]], ())
    assert passos[3] == ("título", TITULO) and passos[4] == ("tocar", "@tv_drafts_box")
    # A versão de antes ganhou um registro recusado, no lugar dela na lista (o novo agora é o 1º), e saiu.
    antigo = [r for r in robo.listar("apagado") if r["versao_de"] == str(ident)][0]
    assert passos[5] == ("apagar", antigo["id"], 2) and passos[-1] == ("descurtir", 2)
    assert antigo["titulo"] == TITULO and antigo["produtos"] == [VESTIDO, mais[0]["nome"]]
    assert antigo["criado_em"] == "2026-10-22 09:00:00" and antigo["arquivo"].endswith(f"{ident}.mp4")
    refeito = robo.pegar(ident)
    assert refeito["estado"] == "aprovado" and refeito["postar_em"] and refeito["arquivo"] == nova
    assert refeito["no_app_em"] == "2026-10-22 15:00:00" and refeito["criado_em"] == "2026-10-22 09:00:00"
    assert refeito["nova_versao"] == {} and refeito["print"].endswith(f"{ident}_nova_2.png")
    assert refeito["edicao"]["versoes"] == 2 and refeito["edicao"]["escolhas"]["miniatura"] == "esquerda"
    assert not refeito["edicao"]["escolhas"]["legenda"]
    assert robo.posicao_no_app(refeito) == 0 and robo.posicao_no_app(robo.pegar(depois)) == 1
    # A versão de antes não conta como rascunho do dia.
    assert robo.rascunhos_de_hoje(agora) == 3
    assert "refiz no celular o rascunho que você editou e apaguei a versão de antes" in avisos[-1]


def test_rascunho_editado_que_nao_e_refeito_fica_como_estava_e_tenta_de_novo(monkeypatch, avisos):
    ativar(robo_inicio=0, robo_fim=24)
    ident = _editavel(monkeypatch)
    nova = os.path.join(robo.PASTA_RASCUNHOS, f"{ident}_nova_2.mp4")
    with open(nova, "wb") as f:
        f.write(b"nova")
    robo.atualizar(ident, estado="refazer", nova_versao={"arquivo": nova, "versao": 2})
    passos = []
    _celular_do_refazer(monkeypatch, passos, anexados=[])
    with pytest.raises(robo.Parada):
        robo.refazer_no_app(_Tela(), robo.pegar(ident), momento("2026-10-22 15:00"))
    # Nada foi salvo nem apagado, e o que curtiu sai no fim.
    assert ("tocar", "@tv_drafts_box") not in passos and not any(p[0] == "apagar" for p in passos)
    assert passos[-1][0] == "descurtir" and robo.listar("recusado", "apagado") == []
    for vez in range(1, robo.TENTATIVAS_DE_POSTAR):
        robo._nao_saiu_o_refazer(ident, "o produto não ficou")
        assert robo.pegar(ident)["estado"] == "refazer" and f"tentativa {vez + 1} de" in avisos[-1]
    robo._nao_saiu_o_refazer(ident, "o produto não ficou")
    voltou = robo.pegar(ident)
    assert voltou["estado"] == "rascunho" and voltou["nova_versao"]["arquivo"] == nova
    assert "O de antes continua no celular" in avisos[-1]


def test_faxina_tira_da_galeria_cada_versao_do_editar(avisos):
    ident = _rascunho("postado")
    app = AppDeMentira()
    arquivos = _arquivos_do_rascunho(ident, app)
    robo.atualizar(ident, edicao={"versoes": 2})
    app.galeria.update({robo.nome_na_galeria(ident, 2), robo.nome_na_galeria(ident, 3)})
    robo.faxina_dos_arquivos(app)
    assert app.galeria == set() and not any(os.path.exists(arquivo) for arquivo in arquivos)


def test_editado_que_espera_o_refazer_aparece_na_fila_e_o_produto_dele_conta_como_postado(monkeypatch):
    # O produto do editado que o robô refaz no app não volta noutro rascunho (P166 1), e a Fila de
    # Rascunhos 🗂️ mostra que ele espera o robô refazer no celular (P192 1).
    ativar(robo_inicio=8, robo_fim=22)
    ident = _rascunho("refazer", itens_do_video=["77"])
    assert robo.onde_os_produtos_foram()["77"] == robo.ONDE_JA_FOI["aprovado"]
    robo.atualizar(ident, falhas_ao_postar="1", motivo="o produto não ficou")
    texto = robo.texto_da_fila(agora=momento("2026-10-25 10:30"))
    assert "Editados, esperando o robô refazer no celular (1)" in texto
    assert "não saiu 1 vez(es) (o produto não ficou); tento de novo" in texto


def test_verificacao_no_refazer_para_sem_descurtir(monkeypatch, avisos):
    # Na Verificação da Shopee o robô para sem tocar em mais nada, também no refazer do editado (P192 1).
    ativar(robo_inicio=0, robo_fim=24)
    ident = _editavel(monkeypatch)
    nova = os.path.join(robo.PASTA_RASCUNHOS, f"{ident}_nova_2.mp4")
    with open(nova, "wb") as f:
        f.write(b"nova")
    robo.atualizar(ident, estado="refazer", nova_versao={"arquivo": nova, "versao": 2})
    passos = []
    _celular_do_refazer(monkeypatch, passos)

    def galeria(d, arquivo, nome):
        raise robo.Verificacao()
    monkeypatch.setattr(robo.ps, "por_na_galeria", galeria)
    robo.gravar_estado(favoritos_limpos=True)
    with pytest.raises(robo.Verificacao):
        robo.refazer_no_app(_Tela(), robo.pegar(ident), momento("2026-10-22 15:00"))
    assert not any(p[0] == "descurtir" for p in passos) and robo.ler_estado()["favoritos_limpos"] is False
    assert robo.pegar(ident)["estado"] == "refazer"


# --- Editar ✏️ nos rascunhos de Ver Produtos (P202 1) ---

def test_rascunho_de_ver_produtos_guarda_como_curtir_de_novo_e_deixa_editar(monkeypatch, avisos):
    # P202 1: o rascunho de Ver Produtos também guarda o que o Editar ✏️ precisa e, para o refazer, como curtir
    # de novo cada produto do post: o do criador sem link (pela lista do vídeo dele) e o trocado com o link.
    _fonte_de_video(monkeypatch)
    monkeypatch.setattr(robo.edicao_video, "vale_para", lambda fonte: True)
    monkeypatch.setattr(robo, "anuncio_do_ver_produtos", lambda nome: {"foto": b"\xff\xd8\xfffoto", "nome": nome})

    def editar_para_postar(video, foto, destino, produto="", avisos=False, outras_fotos=(), rotulo_de_ia=False,
                           anotar=None):
        with open(destino, "wb") as f:
            f.write(b"editado")
        anotar["refazer"] = {"textos": {"nome": produto}, "frase": "", "musica": "", "avisos": False,
                             "rotulo_de_ia": False, "escolhas": dict(robo.edicao_video.ESCOLHAS_PADRAO)}
        return "", robo.edicao_video.COM_LEGENDAS, ""
    monkeypatch.setattr(robo.edicao_video, "editar_para_postar", editar_para_postar)
    app = AppDoVerProdutos()
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["produtos"] == [PRODUTO_A, PRODUTO_B]
    assert rascunho["edicao"]["curtir"] == [{"nome": PRODUTO_A, "link": ""}, {"nome": PRODUTO_B, "link": ""}]
    assert os.path.exists(rascunho["edicao"]["original"]) and robo.pode_editar(rascunho)
    assert robo.produtos_para_refazer(rascunho) == [{"nome": PRODUTO_A, "link": "", "do_video": True},
                                                    {"nome": PRODUTO_B, "link": "", "do_video": True}]
    # O de Ver Produtos de antes (sem como curtir de novo) continua sem o Editar.
    sem = dict(rascunho, edicao={k: v for k, v in rascunho["edicao"].items() if k != "curtir"})
    assert not robo.pode_editar(sem) and robo.produtos_para_refazer(sem) == []
    assert not robo.pode_editar(dict(rascunho, edicao=dict(rascunho["edicao"], curtir=rascunho["edicao"]["curtir"][:1])))


def test_refazer_do_ver_produtos_curte_de_novo_pelo_nome_na_lista_do_criador(monkeypatch):
    # P202 1: no refazer, os produtos do criador são curtidos de novo pelo mesmo caminho do rascunho, a lista do
    # Ver Produtos do vídeo dele, cada um pelo nome da página; o trocado e o a mais, pelo link deles. Sem a IA,
    # nunca nas recomendações nem num botão de comprar.
    _fonte_de_video(monkeypatch)
    monkeypatch.setattr(robo.ps, "ia_confere_do_criador", lambda *a, **k: pytest.fail("o refazer não pergunta à IA"))
    pelo_link = []

    def curtir_pelo_link(d, video, produtos, curtidos):
        pelo_link.extend(p["nome"] for p in produtos)
        curtidos.extend((p["link"], p["nome"]) for p in produtos)
        return list(produtos)
    monkeypatch.setattr(robo, "_curtir_os_produtos", curtir_pelo_link)
    video = {"id": "a1", "arquivo": "", "link": LINK_DE_VIDEO, "nome": PRODUTO_B, "produtos": [PRODUTO_B]}
    trocado = {"nome": "Copo Térmico de Outra Loja", "link": "https://s.shopee.com.br/outra", "do_video": True}
    produtos = [{"nome": PRODUTO_B, "link": "", "do_video": True}, trocado]
    app, curtidos = AppDoVerProdutos(), []
    assert robo._curtir_de_novo_pelo_ver_produtos(app, video, produtos, curtidos) == produtos
    # Só o B: o A foi aberto pela lista e ficou como estava.
    assert app.ja_curtidos == {PRODUTO_B} and RECOMENDADO not in app.toques
    assert curtidos == [(robo.NoVerProdutos(PRODUTO_B), PRODUTO_B), (trocado["link"], trocado["nome"])]
    assert pelo_link == [trocado["nome"]]
    # O produto que não está mais na lista do criador fica sem a curtida (o refazer para por isso).
    app = AppDoVerProdutos()
    assert robo._curtir_de_novo_pelo_ver_produtos(app, video, [{"nome": "Produto Que Saiu Da Lista", "link": "",
                                                               "do_video": True}], []) == []
    assert app.ja_curtidos == set()


def test_rascunho_de_ver_produtos_editado_e_refeito_no_app_pela_lista_do_criador(monkeypatch, avisos):
    # P202 1: com o Aprovar do editado, o robô curte de novo pelo caminho do rascunho, refaz no app com os mesmos
    # produtos, na mesma ordem, e descurte no fim, como hoje.
    ativar(robo_inicio=0, robo_fim=24)
    ident = _editavel(monkeypatch)
    trocado = "Copo Térmico de Outra Loja"
    robo.atualizar(ident, link=LINK_DE_VIDEO, produtos=[PRODUTO_A, trocado], mais_produtos=[],
                   links_dos_produtos=["https://s.shopee.com.br/curto-11", "https://s.shopee.com.br/outra"],
                   edicao=dict(robo.pegar(ident)["edicao"], curtir=[
                       {"nome": PRODUTO_A, "link": ""}, {"nome": trocado, "link": "https://s.shopee.com.br/outra"}]))
    assert robo.pode_editar(robo.pegar(ident))
    nova = os.path.join(robo.PASTA_RASCUNHOS, f"{ident}_nova_2.mp4")
    with open(nova, "wb") as f:
        f.write(b"nova")
    robo.atualizar(ident, estado="refazer", nova_versao={"arquivo": nova, "versao": 2})
    passos = []
    _celular_do_refazer(monkeypatch, passos)
    monkeypatch.setattr(robo, "_curtir_os_produtos", lambda *a, **k: pytest.fail("no Ver Produtos, pela lista"))

    def pela_lista(d, video, produtos, curtidos):
        passos.append(("curtir pela lista", video["link"], [(p["nome"], p["link"]) for p in produtos]))
        curtidos.extend((robo.NoVerProdutos(p["nome"]) if not p["link"] else p["link"], p["nome"]) for p in produtos)
        return list(produtos)
    monkeypatch.setattr(robo, "_curtir_de_novo_pelo_ver_produtos", pela_lista)
    assert robo.refazer_no_app(_Tela(), robo.pegar(ident), momento("2026-10-22 15:00")) == (
        "rascunho editado refeito no app")
    assert passos[0] == ("curtir pela lista", LINK_DE_VIDEO, [(PRODUTO_A, ""), (trocado, "https://s.shopee.com.br/outra")])
    assert ("anexar", [PRODUTO_A, trocado], ()) in passos and passos[-1] == ("descurtir", 2)
    assert robo.pegar(ident)["estado"] == "aprovado"
    # Sem curtir de novo todos, nada é refeito.
    outro = _editavel(monkeypatch)
    robo.atualizar(outro, link=LINK_DE_VIDEO, produtos=[PRODUTO_A], links_dos_produtos=[""], estado="refazer",
                   nova_versao={"arquivo": nova, "versao": 2},
                   edicao=dict(robo.pegar(outro)["edicao"], curtir=[{"nome": PRODUTO_A, "link": ""}]))
    monkeypatch.setattr(robo, "_curtir_de_novo_pelo_ver_produtos", lambda d, video, produtos, curtidos: [])
    with pytest.raises(robo.Parada) as parada:
        robo.refazer_no_app(_Tela(), robo.pegar(outro), momento("2026-10-22 15:30"))
    assert "não consegui curtir de novo 1 de 1" in parada.value.motivo

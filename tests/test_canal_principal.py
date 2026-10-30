"""
Canal principal e Grupo Público: pausa, novas tentativas, Publicar Agora, saldo, limpeza,
a legenda do Criar Postagem e os vídeos do robô da Shopee Vídeo na fila do canal.
"""
import os
import sqlite3
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from conftest import consultar, inserir, rodar


def video(bm, id_unico, data=None, caminho=None):
    data = data or datetime.now(bm.fuso_horario).strftime("%Y-%m-%d")
    inserir("INSERT INTO fila_postagens (id_unico, caminho_video, video_id, legenda, data_alvo, prioridade) "
            "VALUES (?, ?, 'fileid', 'Vídeo 7', ?, 1)", id_unico, caminho, data)


def status(id_unico):
    return consultar("SELECT status FROM fila_postagens WHERE id_unico = ?", id_unico)[0]


@pytest.fixture
def telegram(bm, monkeypatch):
    """send_video falso; 'falhas' quantas vezes seguidas ele estoura."""
    estado = SimpleNamespace(enviados=[], falhas=0)

    async def send_video(chat_id=None, video=None, caption=None, parse_mode=None, **k):
        if estado.falhas > 0:
            estado.falhas -= 1
            raise RuntimeError("Telegram fora do ar")
        estado.enviados.append(video)
        return SimpleNamespace(message_id=1, video=SimpleNamespace(file_id="novo"))

    async def send_message(*a, **k):
        return SimpleNamespace(message_id=1)
    monkeypatch.setattr(bm.bot, "send_video", send_video)
    monkeypatch.setattr(bm.bot, "send_message", send_message)
    return estado


def test_pausa_segura_os_videos(bm, telegram):
    bm.salvar_pausa_programada({"ativa": True, "data_retorno": "01/01/2099", "servicos_pausados": []})
    video(bm, "p1")
    bm.agendar_fila_postagens()
    rodar(bm.executar_postagem_fila("p1"))
    assert not [j for j in bm.scheduler.get_jobs() if j.id.startswith("job_fila_postagem_")]
    assert telegram.enviados == [] and status("p1") == "PENDENTE"


def test_falha_de_envio_tenta_de_novo_ate_3_vezes(bm, telegram):
    video(bm, "r1")
    telegram.falhas = 2
    for _ in range(3):
        if status("r1") == "PENDENTE":
            rodar(bm.executar_postagem_fila("r1"))
    assert status("r1") == "CONCLUIDO" and len(telegram.enviados) == 1

    video(bm, "r2")
    telegram.falhas = 5
    inicio = time.monotonic()
    for _ in range(4):
        if status("r2") == "PENDENTE":
            rodar(bm.executar_postagem_fila("r2"))
    assert status("r2") == "ERRO"
    # A desistência vai para o /status sem travar o robô esperando o próprio banco.
    assert consultar("SELECT COUNT(*) FROM erros_logs WHERE erro LIKE '%desistiu do vídeo r2%'")[0] == 1
    assert time.monotonic() - inicio < 10
    # Cada tentativa fica no registro dos processos, que o checkup do dia conta.
    resultados = [r[2] for r in bm.registro_processos.contagem("2000-01-01 00:00:00")
                  if r[1] == "postagem canal principal" for _ in range(r[5])]
    assert sorted(resultados) == sorted(["falhou, tenta de novo"] * 4 + ["postado", "desistiu"])


def test_fim_da_pausa_no_meio_do_dia_volta_no_mesmo_dia(bm, telegram, monkeypatch, relogio):
    relogio("15:00")    # meio do dia: o Bom Dia já passou e a Boa Noite ainda não
    agora = datetime.now(bm.fuso_horario)
    hoje = agora.strftime("%Y-%m-%d")
    ontem = (agora - timedelta(days=1)).strftime("%Y-%m-%d")

    async def gerar(prompt):
        return "voltamos"

    async def apagar(*a, **k):
        pass
    monkeypatch.setattr(bm, "gerar_mensagem_gemini", gerar)
    monkeypatch.setattr(bm, "apagar_mensagem_automatica", apagar)
    r = bm.ler_config_rotina()
    r.update({"bom_dia": {"inicio": 6, "fim": 9}, "boa_noite": {"inicio": 21, "fim": 23},
              "pausado": True, "ultimo_bom_dia": ontem, "ultimo_boa_noite": ontem,
              "historico_diario": {"data": hoje, "contagem": {}}})
    bm.salvar_config_rotina(r)
    for i in range(3):
        video(bm, f"v{i}", data=ontem)
    bm.salvar_pausa_programada({"ativa": True, "servicos_pausados": ["spam", "rotina"], "id_aviso_imediato": 5,
                                "data_retorno": (agora - timedelta(minutes=1)).strftime("%d/%m/%Y %H:%M")})

    async def cenario():
        bm.scheduler.start()
        bm.scheduler.add_job(bm.disparar_mensagem, 'cron', hour=7, minute=30, timezone=bm.FUSO_STR,
                             args=["bom_dia"], id="job_rotina_bom_dia_0")
        await bm.verificar_retorno_pausa_minuto()
        jobs = [j.next_run_time.astimezone(bm.fuso_horario).date() for j in bm.scheduler.get_jobs()
                if j.id.startswith("job_fila_postagem_")]
        bom_dia = bm.scheduler.get_job("job_rotina_bom_dia_0").next_run_time.astimezone(bm.fuso_horario)
        bm.scheduler.shutdown(wait=False)
        return jobs, bom_dia
    jobs, bom_dia = rodar(cenario())
    assert len(jobs) == 3 and all(d == agora.date() for d in jobs)
    assert bom_dia.date() == agora.date()


@pytest.fixture
def grupo(bm, monkeypatch):
    """O que o bot manda (chat, texto) e apaga; a IA responde "volta" na mensagem de volta e "aviso" no resto."""
    estado = SimpleNamespace(mandados=[], apagados=[])

    async def send_message(chat_id, texto, **k):
        estado.mandados.append((chat_id, texto))
        return SimpleNamespace(message_id=100 + len(estado.mandados))

    async def apagar(msg_id, chat_id):
        estado.apagados.append(msg_id)

    async def gerar(prompt):
        return "volta" if "voltou à ativa" in prompt else "aviso"
    monkeypatch.setattr(bm.bot, "send_message", send_message)
    monkeypatch.setattr(bm, "apagar_mensagem_automatica", apagar)
    monkeypatch.setattr(bm, "gerar_mensagem_gemini", gerar)
    return estado


def _suspensa_ate(bm, quando):
    """O robô da Shopee Vídeo leu a suspensão até quando (None: ela saiu)."""
    config = bm.db.ler_config("shopee_video", {}) or {}
    if quando is None:
        config.pop("robo_suspenso_ate", None)
    else:
        config["robo_suspenso_ate"] = quando.strftime("%Y-%m-%d %H:%M:%S")
    bm.db.salvar_config("shopee_video", config)


def _minuto(bm):
    """Uma volta do job de minuto em minuto (o fim da pausa e a suspensão)."""
    async def cenario():
        bm.scheduler.start()
        try:
            await bm.verificar_retorno_pausa_minuto()
        finally:
            bm.scheduler.shutdown(wait=False)
    rodar(cenario())


def _pausados(bm):
    return bm.ler_alvos_divulgacao().get("pausado", False), bm.ler_config_rotina().get("pausado", False)


def test_suspensao_da_shopee_video_pausa_o_canal_e_a_pausa_acompanha(bm, grupo, relogio):
    # Pedido do Rafael (vídeo de 29/10, 18:22; P86 e P87): suspensa a conta de Shopee Vídeo, o
    # Pausar Postagens do Canal Afiliados se preenche sozinho, com o Pausar Ambos e a volta
    # quando o robô volta; a pausa acompanha a suspensão.
    relogio("15:00")
    agora = datetime.now(bm.fuso_horario).replace(second=0, microsecond=0)
    ate = agora + timedelta(days=2)
    _suspensa_ate(bm, ate)
    _minuto(bm)
    pausa = bm.ler_pausa_programada()
    volta = ate + bm.robo_shopee_video.FOLGA_DA_SUSPENSAO
    assert pausa["ativa"] and pausa["data_retorno"] == volta.strftime("%d/%m/%Y %H:%M")
    assert pausa["origem"] == bm.ORIGEM_DA_SUSPENSAO and pausa["servicos_pausados"] == ["spam", "rotina"]
    assert _pausados(bm) == (True, True)
    assert (bm.GRUPO_ID, "aviso") in grupo.mandados
    assert any(chat == bm.ADMIN_ID and "pausado sozinho" in texto for chat, texto in grupo.mandados)
    aviso = pausa["id_aviso_imediato"]
    # Outra volta do minuto com a mesma suspensão: nada de novo.
    antes = len(grupo.mandados)
    _minuto(bm)
    assert len(grupo.mandados) == antes

    # Data nova: a volta muda e o aviso do grupo é trocado.
    ate = agora + timedelta(days=3)
    _suspensa_ate(bm, ate)
    _minuto(bm)
    pausa = bm.ler_pausa_programada()
    assert pausa["data_retorno"] == (ate + bm.robo_shopee_video.FOLGA_DA_SUSPENSAO).strftime("%d/%m/%Y %H:%M")
    assert aviso in grupo.apagados and pausa["id_aviso_imediato"] != aviso
    assert any(chat == bm.ADMIN_ID and "mudou" in texto for chat, texto in grupo.mandados)

    # A Shopee tirou a suspensão antes: o canal volta na hora.
    _suspensa_ate(bm, None)
    _minuto(bm)
    pausa = bm.ler_pausa_programada()
    assert not pausa["ativa"] and "origem" not in pausa
    assert (bm.GRUPO_ID, "volta") in grupo.mandados and _pausados(bm) == (False, False)
    assert any(chat == bm.ADMIN_ID and "acabou antes do prazo" in texto for chat, texto in grupo.mandados)
    resultados = [r[2] for r in bm.registro_processos.contagem("2000-01-01 00:00:00")
                  if r[1] == bm.PROCESSO_DA_PAUSA_AUTOMATICA]
    assert sorted(resultados) == sorted(["ligada", "data nova", "encerrada (a suspensão acabou antes)"])


def test_pausa_automatica_nao_religa_o_que_o_rafael_pausou(bm, grupo, relogio):
    relogio("15:00")
    rotina = bm.ler_config_rotina()
    rotina["pausado"] = True            # pausada à mão antes da suspensão
    bm.salvar_config_rotina(rotina)
    _suspensa_ate(bm, datetime.now(bm.fuso_horario) + timedelta(days=1))
    _minuto(bm)
    assert bm.ler_pausa_programada()["servicos_pausados"] == ["spam"]
    _suspensa_ate(bm, None)
    _minuto(bm)
    assert _pausados(bm) == (False, True)


def test_suspensao_que_ja_acabou_nao_pausa_de_novo(bm, grupo, relogio):
    # O robô tira a marca até 15 min depois da volta; nesse meio tempo o canal não pausa de novo.
    relogio("15:00")
    _suspensa_ate(bm, datetime.now(bm.fuso_horario) - timedelta(minutes=20))
    _minuto(bm)
    assert not bm.ler_pausa_programada().get("ativa") and grupo.mandados == []


def test_pausa_feita_a_mao_continua_valendo(bm, grupo, relogio):
    relogio("15:00")
    agora = datetime.now(bm.fuso_horario).replace(second=0, microsecond=0)
    rotina = bm.ler_config_rotina()
    rotina["pausado"] = True
    bm.salvar_config_rotina(rotina)
    manual = {"ativa": True, "servicos_pausados": ["rotina"], "id_aviso_imediato": 7, "motivo": "x",
              "data_retorno": (agora + timedelta(days=5)).strftime("%d/%m/%Y %H:%M")}
    bm.salvar_pausa_programada(dict(manual))
    # Volta mais tarde que a suspensão: fica como o Rafael deixou.
    _suspensa_ate(bm, agora + timedelta(days=2))
    _minuto(bm)
    assert bm.ler_pausa_programada() == manual and grupo.mandados == []

    # Volta antes do fim da suspensão: vai até ele, com o Pausar Ambos.
    manual["data_retorno"] = (agora + timedelta(days=1)).strftime("%d/%m/%Y %H:%M")
    bm.salvar_pausa_programada(dict(manual))
    _minuto(bm)
    pausa = bm.ler_pausa_programada()
    volta = agora + timedelta(days=2) + bm.robo_shopee_video.FOLGA_DA_SUSPENSAO
    assert pausa["data_retorno"] == volta.strftime("%d/%m/%Y %H:%M") and pausa["retorno_manual"] == manual["data_retorno"]
    assert pausa["servicos_pausados"] == ["rotina", "spam"] and _pausados(bm) == (True, True)
    assert 7 in grupo.apagados

    # A suspensão acabou antes: volta a pausa feita à mão, com a data e os serviços dela.
    _suspensa_ate(bm, None)
    _minuto(bm)
    pausa = bm.ler_pausa_programada()
    assert pausa["ativa"] and pausa["data_retorno"] == manual["data_retorno"] and "origem" not in pausa
    assert pausa["servicos_pausados"] == ["rotina"] and _pausados(bm) == (False, True)
    assert (bm.GRUPO_ID, "volta") not in grupo.mandados


def _retomar(bm, Msg, Est):
    """O Rafael toca Retomar Postagens ▶️ e aprova o encerramento; devolve a mensagem dele."""
    msg = Msg("Aprovar Encerramento ✅")

    async def cenario():
        bm.scheduler.start()
        try:
            await bm.processar_encerramento_pausa(msg, Est())
        finally:
            bm.scheduler.shutdown(wait=False)
    rodar(cenario())
    return msg


def test_retomar_postagens_no_meio_da_suspensao_vale_o_que_o_rafael_fez(bm, grupo, Msg, Est, relogio):
    # Escolha do Rafael (P92): no meio da suspensão, ele toca Retomar Postagens ▶️ e aprova; o
    # bot pausava o canal de novo 1 min depois, com outro aviso no grupo. Agora o canal fica no
    # ar até a suspensão acabar, nem com data nova o bot pausa de novo, e a resposta diz até
    # quando vai a suspensão; na próxima suspensão, ele pausa sozinho de novo.
    relogio("15:00")
    agora = datetime.now(bm.fuso_horario).replace(second=0, microsecond=0)
    ate = agora + timedelta(days=2)
    _suspensa_ate(bm, ate)
    _minuto(bm)
    assert bm.ler_pausa_programada()["ativa"]
    assert any("Preenchi o Pausar Postagens 🛑" in texto for chat, texto in grupo.mandados if chat == bm.ADMIN_ID)
    msg = _retomar(bm, Msg, Est)
    assert not bm.ler_pausa_programada()["ativa"] and _pausados(bm) == (False, False)
    assert any(f"continua suspensa pela Shopee até {bm.robo_shopee_video.quando_acaba(ate)}" in texto
               and "não pauso de novo por essa suspensão" in texto for texto in msg.saidas)
    # Os minutos seguintes, com a mesma suspensão e com data nova: o canal continua no ar.
    antes = len(grupo.mandados)
    for nova in (ate, ate + timedelta(days=1)):
        _suspensa_ate(bm, nova)
        _minuto(bm)
        assert not bm.ler_pausa_programada().get("ativa") and len(grupo.mandados) == antes
    # Uma pausa nova dele, que acaba antes da suspensão, fica como ele fez (não vai até o fim dela).
    manual = {"ativa": True, "servicos_pausados": [], "id_aviso_imediato": 7, "motivo": "x",
              "data_retorno": (agora + timedelta(days=1)).strftime("%d/%m/%Y %H:%M")}
    bm.salvar_pausa_programada(dict(manual))
    _minuto(bm)
    assert bm.ler_pausa_programada() == manual and len(grupo.mandados) == antes
    bm.salvar_pausa_programada({"ativa": False})
    # A suspensão acabou: a marca sai, e a próxima suspensão pausa sozinha de novo.
    _suspensa_ate(bm, None)
    _minuto(bm)
    _suspensa_ate(bm, agora + timedelta(days=5))
    _minuto(bm)
    pausa = bm.ler_pausa_programada()
    assert pausa["ativa"] and pausa["origem"] == bm.ORIGEM_DA_SUSPENSAO and _pausados(bm) == (True, True)
    resultados = [r[2] for r in bm.registro_processos.contagem("2000-01-01 00:00:00")
                  if r[1] == bm.PROCESSO_DA_PAUSA_AUTOMATICA]
    assert bm.RETOMADA_PELO_RAFAEL in resultados and bm.FIM_DA_RETOMADA in resultados


def test_retomar_postagens_sem_suspensao_e_o_mesmo_de_antes(bm, grupo, Msg, Est, relogio):
    relogio("15:00")
    bm.salvar_pausa_programada({"ativa": True, "servicos_pausados": [], "id_aviso_imediato": 7, "motivo": "x",
                                "data_retorno": "30/12/2099 15:00"})
    msg = _retomar(bm, Msg, Est)
    assert not bm.ler_pausa_programada()["ativa"] and (bm.GRUPO_ID, "volta") in grupo.mandados
    assert not any("suspensa" in texto for texto in msg.saidas)
    assert not bm.db.ler_config(bm.CHAVE_RETOMADA_NA_SUSPENSAO, {})


def test_pausar_postagens_do_formulario_e_o_mesmo_de_antes(bm, grupo, Msg, Est):
    rodar(bm.confirmar_pausa_programada_final(Msg("Confirmar Pausa ✅"), Est(
        {"data_retorno_str": "30/12/2099 15:00", "servicos_selecionados": "Apenas Rotina"})))
    pausa = bm.ler_pausa_programada()
    assert pausa["ativa"] and pausa["servicos_pausados"] == ["rotina"] and "origem" not in pausa
    assert pausa["motivo"] in bm.MOTIVOS_DA_PAUSA and (bm.GRUPO_ID, "aviso") in grupo.mandados
    assert _pausados(bm) == (False, True)


def test_publicar_agora_pelo_file_id_nao_repete(bm, telegram, Msg, Est, monkeypatch):
    video(bm, "so_fileid")

    async def menu(*a, **k):
        pass
    monkeypatch.setattr(bm, "menu_gerenciar_fila", menu)
    rodar(bm.processar_publicacao_imediata(Msg("Publicar Vídeo 🚀"), Est({"posicao_publicar": 0})))
    rodar(bm.executar_postagem_fila("so_fileid"))       # o job agendado do mesmo vídeo
    assert status("so_fileid") == "CONCLUIDO" and len(telegram.enviados) == 1


@pytest.mark.parametrize("antes, status_novo, comissao, esperado", [
    (("PENDING", 10.0), "COMPLETED", 12, 112.0),
    (("COMPLETED", 10.0), "CANCELLED", 0, 90.0),
    (("COMPLETED", 10.0), "COMPLETED", 12, 102.0),
    (("PENDING", 10.0), "COMPLETED", 10, 110.0),
    (("PENDING", 10.0), "PENDING", 12, 100.0),
])
def test_saldo_soma_a_comissao_confirmada_uma_vez(bm, monkeypatch, antes, status_novo, comissao, esperado):
    monkeypatch.setattr(bm, "salvar_historico_financeiro", lambda h: None)
    bm.salvar_banco_pedidos({"A1": {"data": "2026-09-01", "status": antes[0], "comissao_total": antes[1],
                                    "comissao_shopee": antes[1], "comissao_vendedor": 0.0}})
    bm.db.salvar_config("saldo_caixa_shopee", 100.0)
    bm.processar_e_salvar_pedidos_api([{
        "purchaseTime": 1788000000, "totalCommission": str(comissao), "shopeeCommissionCapped": str(comissao),
        "sellerCommission": "0", "orders": [{"orderId": "A1", "orderStatus": status_novo}]}])
    assert bm.db.ler_config("saldo_caixa_shopee", 0.0) == pytest.approx(esperado)


def test_excluir_parceiro_apaga_so_a_pasta_dele(bm):
    ids = [bm.salvar_parceiro({"nome": n, "app_id": "123456", "app_secret": "x" * 20,
                               "canal_origem": "@a", "canal_destino": "-1001"}) for n in ("A", "B")]
    for pid in ids:
        os.makedirs(f"parceiros/{pid}", exist_ok=True)
        open(f"parceiros/{pid}/v.mp4", "wb").write(b"x")
    bm.excluir_parceiro(ids[0])
    assert not os.path.exists(f"parceiros/{ids[0]}") and os.path.exists(f"parceiros/{ids[1]}/v.mp4")


def test_zerar_uma_fila_nao_apaga_arquivos_das_outras(bm, Msg, Est):
    velho = time.time() - 3600
    for nome in ("clone.mp4", "publico.mp4", "lixo.mp4"):
        open(f"temp/{nome}", "wb").write(b"x")
        os.utime(f"temp/{nome}", (velho, velho))
    # Recém-criado pelo relógio do teste: com --relogio, a hora do sistema de arquivos não é a do teste.
    open("temp/baixando.mp4", "wb").write(b"x")
    os.utime("temp/baixando.mp4", (time.time(), time.time()))
    bm.salvar_fila_clonagem({"fila": [{"id": "c1", "processado": False, "caminho_video": "temp/clone.mp4"}]})
    conexao = sqlite3.connect("banco_dados.db")
    conexao.execute("CREATE TABLE IF NOT EXISTS fila_publico (id_unico TEXT PRIMARY KEY, msg_id_destino INTEGER, "
                    "legenda TEXT, data_captura TEXT, data_alvo TEXT, horario_disparo TEXT, processado INTEGER "
                    "DEFAULT 0, data_postagem TEXT, caminho_arquivo TEXT, msg_postada_id INTEGER)")
    conexao.execute("INSERT INTO fila_publico (id_unico, processado, caminho_arquivo) VALUES ('p1', 0, 'temp/publico.mp4')")
    conexao.execute("CREATE TABLE IF NOT EXISTS fila_autorais (id_unico TEXT PRIMARY KEY, msg_id_destino INTEGER, "
                    "legenda TEXT, caminho_arquivo TEXT, data_captura TEXT, data_alvo TEXT, horario_disparo TEXT, "
                    "processado INTEGER DEFAULT 0)")
    conexao.commit()
    conexao.close()
    rodar(bm.processar_zerar_filas_tarefas(Msg("Aprovar Exclusão ✅"),
                                           Est({"tipo_limpeza": "Limpar Fila Autorais 🎥"})))
    assert sorted(os.listdir("temp")) == ["baixando.mp4", "clone.mp4", "publico.mp4"]


# --- A legenda do Criar Postagem e os vídeos do robô da Shopee Vídeo (P62 a P64) ---

LINK_DO_POST = "https://sv.shopee.com.br/share-video/abc"
LINKS = ["https://s.shopee.com.br/canal1", "https://s.shopee.com.br/canal2"]


def test_criar_postagem_usa_o_padrao_do_canal_e_o_numero_reservado(bm, Msg, Est, monkeypatch):
    import legendas
    monkeypatch.setattr(bm, "agendar_fila_postagens", lambda: None)
    # O robô tirou o 42 do contador enquanto o Rafael montava o 41.
    bm.salvar_contador(43)
    nome = "Vídeo 41\n📦 Item: Copo & Tampa"
    msg = Msg("Finalizar ✅")
    rodar(bm.finalizar_postagem(msg, Est({
        "nome_produto": nome, "video_id": "fileid", "video_path": None, "plataforma_escolhida": "Apenas Shopee 🛒",
        "link_video_shopee": LINK_DO_POST, "links_shopee": LINKS, "numero_reservado": 41})))
    legenda, video_id = consultar("SELECT legenda, video_id FROM fila_postagens")
    assert legenda == legendas.legenda_do_canal(nome, shopee=(LINK_DO_POST, LINKS)) and video_id == "fileid"
    assert legenda.startswith("<b>Vídeo 41 | 📦 Item: Copo &amp; Tampa</b>")
    assert "Vídeo #41 entrou na fila" in msg.saidas[-1]


@pytest.fixture
def canal(bm, monkeypatch, tmp_path):
    """O que o bot manda no privado, o que a IA responde e um pedido do robô com a cópia do vídeo."""
    import pedidos_do_canal
    estado = SimpleNamespace(avisos=[], prompts=[], resposta="Vídeo 99\n📦 Item: Copo Térmico", agendados=0)

    async def send_message(chat_id, texto, **k):
        estado.avisos.append(texto)

    async def analisar(caminho, prompt):
        estado.prompts.append(prompt)
        return estado.resposta

    def agendar():
        estado.agendados += 1

    monkeypatch.setattr(bm.bot, "send_message", send_message)
    monkeypatch.setattr(bm, "analisar_video_gemini", analisar)
    monkeypatch.setattr(bm, "agendar_fila_postagens", agendar)
    bm.salvar_contador(7)

    def pedir(links=LINKS, produto="Copo Térmico Inox Com Tampa 500ml Para Café"):
        video = tmp_path / "rascunho.mp4"
        video.write_bytes(b"video aprovado")
        return pedidos_do_canal.pedir(5, str(video), LINK_DO_POST, links, produto)

    estado.pedir, estado.pedidos = pedir, pedidos_do_canal
    return estado


def test_video_do_robo_entra_na_fila_do_canal_com_o_numero_e_o_padrao(bm, canal):
    import legendas
    copia = canal.pedir()
    rodar(bm.levar_videos_do_robo_ao_canal())
    legenda, caminho, video_id, data_alvo = consultar("SELECT legenda, caminho_video, video_id, data_alvo "
                                                      "FROM fila_postagens")
    # O número é o do contador, nunca o que a IA escreveu.
    assert legenda == legendas.legenda_do_canal("Vídeo 7\n📦 Item: Copo Térmico", shopee=(LINK_DO_POST, LINKS))
    assert (caminho, video_id, data_alvo) == (copia, None, "2000-01-01")   # o Bom Dia de hoje não saiu
    assert canal.prompts == [legendas.prompt_do_item(7)] and bm.ler_contador() == 8
    assert canal.pedidos.pendentes() == [] and canal.agendados == 1
    assert len(canal.avisos) == 1 and "Vídeo #7</b>" in canal.avisos[0] and "Publica" in canal.avisos[0]
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = ?",
                     bm.PROCESSO_ROBO_NO_CANAL) == ("na fila", 1)


def test_sem_a_ia_o_item_e_o_nome_do_produto_e_sem_links_o_aviso_diz(bm, canal):
    canal.resposta = None
    canal.pedir(links=[])
    rodar(bm.levar_videos_do_robo_ao_canal())
    legenda = consultar("SELECT legenda FROM fila_postagens")[0]
    assert legenda.startswith("<b>Vídeo 7 | 📦 Item: Copo Térmico Inox Com Tampa 500ml Para Café</b>")
    assert "Links dos Produtos" not in legenda and LINK_DO_POST in legenda
    assert "sem os links dos produtos" in canal.avisos[0]


def test_fila_que_nao_grava_tenta_de_novo_com_o_mesmo_numero_e_desiste_na_terceira(bm, canal, monkeypatch):
    monkeypatch.setattr(bm, "adicionar_na_fila_do_canal", lambda *a: None)
    canal.pedir()
    for tentativa in (1, 2):
        rodar(bm.levar_videos_do_robo_ao_canal())
        [pedido] = canal.pedidos.pendentes()
        assert (pedido["tentativas"], pedido["numero"]) == (tentativa, 7) and canal.avisos == []
    assert bm.ler_contador() == 8          # o número não pula a cada tentativa
    rodar(bm.levar_videos_do_robo_ao_canal())
    assert canal.pedidos.pendentes() == [] and "depois de 3 tentativas" in canal.avisos[0]


def test_copia_que_sumiu_sai_dos_pedidos_com_aviso(bm, canal):
    os.remove(canal.pedir())
    rodar(bm.levar_videos_do_robo_ao_canal())
    assert canal.pedidos.pendentes() == [] and "a cópia do vídeo sumiu" in canal.avisos[0]
    assert consultar("SELECT COUNT(*) FROM fila_postagens")[0] == 0 and bm.ler_contador() == 7

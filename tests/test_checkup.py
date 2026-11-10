"""checkup.py: o checkup do dia sai em números e lugares do código, nunca no texto dos erros."""
from datetime import datetime, timedelta

import pytest

import checkup
import db
from conftest import inserir
from fuso import fuso_horario

AGORA = datetime(2026, 10, 23, 22, 20, tzinfo=fuso_horario)


@pytest.fixture(autouse=True)
def configuracoes():
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")


def _momento(horas_atras):
    return (AGORA - timedelta(hours=horas_atras)).strftime("%Y-%m-%d %H:%M:%S")


def _erro(horas_atras, erro, origem="bot_mestre.py", rastro=""):
    from utils import registrar_erro_json
    registrar_erro_json("cria a tabela", origem="teste")
    inserir("DELETE FROM erros_logs WHERE origem = 'teste'")
    inserir("INSERT INTO erros_logs (timestamp, origem, erro, rastro_codigo, contexto) VALUES (?, ?, ?, ?, '{}')",
            _momento(horas_atras), origem, erro, rastro)


def test_chaves_do_robo_sao_as_mesmas():
    import robo_shopee_video as robo
    assert checkup.CHAVE_CONFIG_SV == robo.CHAVE_CONFIG
    assert checkup.CHAVE_DIA_SV == robo.CHAVE_DIA
    assert checkup.FOLGA_DA_SUSPENSAO_SV == robo.FOLGA_DA_SUSPENSAO
    assert robo.PADRAO["robo_pausado"] is True
    assert checkup.VIDEOS_NO_FEED_POR_DIA == robo.interacoes.VIDEOS_NO_FEED_POR_DIA
    assert checkup.FEITOS_NO_FEED == robo.interacoes.FEITOS_NO_FEED
    assert checkup.SO_CURTIDO_NO_FEED == robo.interacoes.SO_CURTIDO
    assert checkup.POSTS_ANTIGOS_POR_DIA == robo.interacoes.POSTS_ANTIGOS_POR_DIA
    assert checkup.DURANTE_O_DIA_SV == robo.DURANTE_O_DIA
    assert checkup.LEITURAS_DAS_RESPOSTAS_SV == robo.LEITURAS_DAS_RESPOSTAS
    assert checkup.ESPACO_DAS_RESPOSTAS_SV == robo.ESPACO_DAS_RESPOSTAS
    assert checkup.PROCESSO_DA_LEITURA_SV == robo.PROCESSO_DA_LEITURA
    assert checkup.HORARIO_DO_ROBO_SV == robo.ps.HORARIO_DAS_RODADAS
    assert checkup.CHAVE_SEGUIDORES_SV == robo.CHAVE_SEGUIDORES
    assert checkup.CHAVE_TENTATIVAS_POR_DIA_SV == robo.CHAVE_TENTATIVAS_POR_DIA


def test_erro_ligado_ao_lugar_do_codigo_sem_o_texto():
    rastro = "Traceback (most recent call last):\n  ...\nTimeoutError: segredo"
    _erro(2, "buscador_produtos (fone secreto): estourou", rastro=rastro)
    _erro(3, "buscador_produtos (outro produto): estourou", rastro=rastro)
    _erro(1, "Erro qualquer de -1001234567890", origem="-1001234567890")
    _erro(1, "link saiu sem marca", origem="Link sem conversão")
    _erro(24 * 3, "fechar_dia_captura_parceiros: velho")
    _erro(2, "fechar_dia_captura_parceiros: de hoje")

    erros = checkup.erros_registrados(AGORA)
    por_lugar = {e["lugar"]: e for e in erros}
    busca = next(e for lugar, e in por_lugar.items() if lugar.startswith("bot_mestre.py:") and e["qtd"] == 2)
    assert busca["texto"] == "buscador_produtos ({…}): {…}" and busca["tipo"] == "TimeoutError"
    assert busca["novo"] is True
    fechar = next(e for e in erros if e["texto"].startswith("fechar_dia_captura_parceiros"))
    assert fechar["qtd"] == 1 and fechar["novo"] is False   # já apareceu 3 dias atrás
    sem_lugar = next(e for e in erros if e["lugar"] == "(sem lugar no código)")
    assert sem_lugar["origem"] == "#" and "1234567890" not in sem_lugar["texto"]
    assert all(e["origem"] != "Link sem conversão" for e in erros)
    assert "secreto" not in str(erros) and "segredo" not in str(erros)


def test_log_do_robo_conta_quedas_rastros_avisos_e_erros():
    import inventario
    linhas = [
        "Started bot_mestre_bot.service - Bot Mestre.",
        "2026-10-23 10:00:00.123 -0300 - ❌ [Métricas] Falha na coleta diária: dado privado",
        "2026-10-23 10:01:00.123 -0300 - ❌ [Métricas] Falha na coleta diária: dado privado",
        "2026-10-23 10:02:00.123 -0300 - ⚠️ [Métricas] Não consegui contar membros de canal: x",
        "Traceback (most recent call last):",
        "bot_mestre_bot.service: Scheduled restart job, restart counter is at 1.",
        "Started bot_mestre_bot.service - Bot Mestre.",
    ]
    r = checkup.resumo_do_log(linhas, inventario.modelos_de_log())
    assert (r["inicios"], r["quedas"], r["rastros"], r["avisos"], r["erros"]) == (2, 1, 1, 1, 2)
    onde, texto, nivel, qtd = r["problemas"][0]
    assert onde.startswith("bot_mestre.py:") and nivel == "error" and qtd == 2
    assert "privado" not in texto and "{…}" in texto


def test_queda_e_so_o_reinicio_automatico_e_o_systemd_diz_o_que_foi():
    # Checkup de 27/10: "bot_mestre_bot: caiu e o systemd reiniciou 1 vez" sem reinício
    # automático nenhum (0 no diagnóstico): o "Failed with result" também sai quando o deploy
    # mata o robô que demorou a parar. A queda conta só o reinício que o systemd fez sozinho,
    # e os eventos dizem o que foi e a que horas.
    import inventario
    morto = ["bot_mestre_bot.service: State 'stop-sigterm' timed out. Killing.",
             "bot_mestre_bot.service: Failed with result 'timeout'.",
             "Started bot_mestre_bot.service - Bot Mestre."]
    assert checkup.resumo_do_log(morto, inventario.modelos_de_log())["quedas"] == 0
    linhas = [
        "2026-10-27T22:09:31-0300 servidor systemd[1]: Stopping bot_mestre_bot.service - Bot Mestre...",
        "2026-10-27T22:11:01-0300 servidor systemd[1]: bot_mestre_bot.service: State 'stop-sigterm' timed out. "
        "Killing.",
        "2026-10-27T22:11:01-0300 servidor systemd[1]: bot_mestre_bot.service: Main process exited, code=killed, "
        "status=9/KILL",
        "2026-10-27T22:11:01-0300 servidor systemd[1]: bot_mestre_bot.service: Failed with result 'timeout'.",
        "2026-10-27T22:11:02-0300 servidor python3[123]: texto do robô com dado secreto",
        "2026-10-27T23:00:00-0300 servidor systemd[1]: bot_mestre_bot.service: Main process exited, code=killed, "
        "status=15/TERM",
        "2026-10-28T03:15:00-0300 servidor systemd[1]: bot_mestre_bot.service: Main process exited, code=exited, "
        "status=1/FAILURE",
        "2026-10-28T03:15:00-0300 servidor systemd[1]: bot_mestre_bot.service: Failed with result 'exit-code'.",
        "2026-10-28T03:15:10-0300 servidor systemd[1]: bot_mestre_bot.service: Scheduled restart job, restart "
        "counter is at 1.",
    ]
    eventos = checkup.eventos_do_systemd(linhas)
    assert eventos == [("22:11", checkup.MORTO_AO_PARAR), ("22:11", "o processo saiu (killed, KILL)"),
                       ("22:11", "terminou com falha (timeout)"), ("03:15", "o processo saiu (exited, FAILURE)"),
                       ("03:15", "terminou com falha (exit-code)"), ("03:15", checkup.REINICIO_AUTOMATICO)]
    assert "secreto" not in str(eventos)
    logs = {"bot_mestre_bot": {"quedas": 0, "rastros": 0, "erros": 0, "avisos": 0, "problemas": [],
                               "eventos": eventos[:3]}}
    pontos = checkup.pontos_de_atencao([], logs, {}, {"ativo": False, "vencidos": 0, "salvos": 0, "ruins": []},
                                       {}, ("x", 1.0, 1), AGORA)
    assert pontos == ["bot_mestre_bot: não parou no tempo ao ser parado e o systemd o matou 1 vez(es)"]


def test_rastros_agrupados_pelo_tipo_e_pelo_lugar_do_codigo():
    rastro_do_projeto = [
        "Traceback (most recent call last):",
        '  File "/home/ubuntu/shopee/bot_mestre.py", line 120, in publicar',
        "    await bot.send_video(chat, video)",
        '  File "/home/ubuntu/shopee/venv/lib/python3.12/site-packages/aiogram/client/bot.py", line 50, in send_video',
        "    raise TelegramBadRequest(...)",
        "aiogram.exceptions.TelegramBadRequest: Bad Request: chat -1001234567890 dado privado",
    ]
    so_biblioteca = [
        "Traceback (most recent call last):",
        '  File "/usr/lib/python3.12/asyncio/tasks.py", line 10, in run',
        '  File "/home/ubuntu/shopee/venv/lib/python3.12/site-packages/telethon/client.py", line 77, in conectar',
        "ConnectionError: segredo",
    ]
    linhas = ["2026-10-23 10:00:00.000 -0300 - ❌ algo"] + rastro_do_projeto * 2 + so_biblioteca
    rastros = checkup.rastros_do_log(linhas)
    assert rastros[0] == ("aiogram.exceptions.TelegramBadRequest", "bot_mestre.py:120 (publicar)", 2)
    assert ("ConnectionError", "telethon/client.py:77", 1) in rastros
    assert "privado" not in str(rastros) and "segredo" not in str(rastros)


def test_rastro_so_de_antes_do_ultimo_inicio_nao_cobra():
    # Checkup de 23/10: os rastros corrigidos às 17h continuavam como ponto de atenção à
    # noite, porque o log das 24 h não tem hora. O último "Started" (deploy) separa.
    import inventario
    rastro = ["Traceback (most recent call last):",
              '  File "/home/ubuntu/shopee/bot_mestre.py", line 2093, in disparar_mensagem',
              "UnboundLocalError: cannot access local variable 'prompt'"]
    corrigido = (["Started bot_mestre_bot.service - Bot Mestre."] + rastro * 3
                 + ["Started bot_mestre_bot.service - Bot Mestre.", "2026-10-23 18:00:00.000 -0300 - ok"])
    r = checkup.resumo_do_log(corrigido, inventario.modelos_de_log())
    assert (r["rastros"], r["rastros_depois"], r["rastros_depois_por_lugar"]) == (3, 0, [])
    sem_robo = {"ativo": False, "vencidos": 0, "salvos": 0, "ruins": []}
    assert checkup.pontos_de_atencao([], {"bot_mestre_bot": r}, {}, sem_robo, {}, ("x", 1.0, 1), AGORA) == []
    # Depois do último início ainda acontece: cobra, dizendo quantos vieram depois.
    r = checkup.resumo_do_log(corrigido + rastro, inventario.modelos_de_log())
    pontos = checkup.pontos_de_atencao([], {"bot_mestre_bot": r}, {}, sem_robo, {}, ("x", 1.0, 1), AGORA)
    assert pontos == ["bot_mestre_bot: 1 rastro(s) de erro no log depois do último início (4 em 24 h; mais comum: "
                      "UnboundLocalError em bot_mestre.py:2093 (disparar_mensagem), 1x)"]
    # Sem nenhum início nas 24 h, o robô estava no ar o dia todo: tudo conta.
    assert checkup.resumo_do_log(rastro * 2, inventario.modelos_de_log())["rastros_depois"] == 2


def test_processo_que_mais_falha_que_acerta_vira_ponto_de_atencao():
    import registro_processos as rp
    for _ in range(4):
        rp.registrar("baixador", "pedido Shopee (vídeo)", "não entregue", "a Shopee demorou", ok=False,
                     agora=AGORA - timedelta(hours=2))
    rp.registrar("baixador", "pedido Shopee (vídeo)", "entregue", ok=True, agora=AGORA - timedelta(hours=1))
    for _ in range(5):
        rp.registrar("baixador", "pedido TikTok", "trava de canais", agora=AGORA - timedelta(hours=1))
    rp.registrar("baixador", "pedido TikTok", "não entregue", "o vídeo é privado", ok=False, agora=AGORA)

    processos = checkup.processos_do_dia(AGORA)
    assert processos[("baixador", "pedido Shopee (vídeo)")]["falhas"] == 4
    assert processos[("baixador", "pedido TikTok")]["neutros"] == 5
    pontos = checkup.pontos_de_atencao([], {}, {}, {"ativo": False, "vencidos": 0, "salvos": 0, "ruins": []},
                                       {}, ("x", 1.0, 1), AGORA, processos)
    # A hora da última falha (checkup de 07/11/2026): diz se a falha continuou depois de uma correção.
    assert processos[("baixador", "pedido Shopee (vídeo)")]["ultima_falha"] == "20:20"
    assert processos[("baixador", "pedido TikTok")]["ultima_falha"] == "22:20"
    assert pontos == ["baixador: pedido Shopee (vídeo): 4 falha(s) e 1 acerto(s) "
                      "(mais comum: não entregue - a Shopee demorou, 4x; a última às 20:20)"]


def _filas_de_teste():
    with db.conexao() as c:
        c.execute("CREATE TABLE IF NOT EXISTS fila_postagens (id_unico TEXT, data_alvo TEXT, status TEXT, "
                  "data_postagem TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS historico_metricas (data TEXT, chave TEXT, valor INTEGER)")
        for tabela in ("fila_publico", "fila_autorais", "fila_parceiros"):
            c.execute(f"CREATE TABLE IF NOT EXISTS {tabela} (id_unico TEXT, data_alvo TEXT, horario_disparo TEXT, "
                      "processado INTEGER, data_postagem TEXT)")


def test_postagens_de_hoje_por_fila():
    _filas_de_teste()
    inserir("INSERT INTO fila_postagens VALUES ('a', '2026-10-23', 'CONCLUIDO', '2026-10-23')")
    inserir("INSERT INTO fila_postagens VALUES ('b', '2026-10-23', 'PENDENTE', NULL)")
    inserir("INSERT INTO fila_postagens VALUES ('c', '2026-10-21', 'PENDENTE', NULL)")
    inserir("INSERT INTO fila_postagens VALUES ('d', '2000-01-01', 'PENDENTE', NULL)")
    for dia, valor in (("2026-10-22", 6), ("2026-10-21", 4), ("2026-10-23", 99)):
        inserir("INSERT INTO historico_metricas VALUES (?, 'posts_dia_principal', ?)", dia, valor)
    inserir("INSERT INTO fila_publico VALUES ('p1', '2026-10-23', '2026-10-23 10:00:00', 1, '2026-10-23 10:00:05')")
    inserir("INSERT INTO fila_publico VALUES ('p2', '2026-10-23', '2026-10-23 21:00:00', 0, NULL)")
    inserir("INSERT INTO fila_publico VALUES ('p3', '2026-10-23', '2026-10-23 22:10:00', 0, NULL)")
    inserir("INSERT INTO fila_autorais VALUES ('u1', '2026-10-20', '2026-10-20 12:00:00', 1, '2026-10-20 12:00:01')")
    db.salvar_config("fila_clonagem", {"fila": [
        {"processado": True, "data_postagem": "2026-10-23"},
        {"processado": False, "horario_disparo": "2026-10-23 23:00:00"},
        {"processado": False, "horario_disparo": "2026-10-23 08:00:00"},
    ]})

    filas = checkup.postagens_de_hoje(AGORA)
    principal = filas["Canal principal"]
    assert (principal["postados"], principal["para_hoje"], principal["atrasados"]) == (1, 1, 1)
    assert principal["media"] == 5
    publico = filas["Grupo Público"]
    assert (publico["postados"], publico["para_hoje"], publico["atrasados"]) == (1, 2, 1)
    assert (filas["Viral"]["postados"], filas["Viral"]["para_hoje"], filas["Viral"]["atrasados"]) == (1, 2, 1)
    assert filas["Autorais"]["postados"] == 0 and filas["Autorais"]["media"] == 1 / 7


def test_canal_principal_aponta_o_video_depois_da_boa_noite():
    # Vídeo do Rafael (07/11, 22:03): a Boa Noite saiu às 21:05 no Canal Afiliados, e 3 vídeos
    # saíram depois (21:14, 21:34 e 21:47). O checkup mostra a hora de cada um, se veio de uma nova
    # tentativa de envio, e cobra o ponto.
    with db.conexao() as c:
        c.execute("CREATE TABLE fila_postagens (id_unico TEXT, data_alvo TEXT, status TEXT, data_postagem TEXT, "
                  "horario_postagem TEXT, tentativas INTEGER)")
    _filas_de_teste()
    hoje = "2026-10-23"
    for ident, hora, vezes in (("a", "20:40", 0), ("b", "21:14", 0), ("c", "21:34", 1), ("d", "21:47", 0)):
        inserir("INSERT INTO fila_postagens VALUES (?, ?, 'CONCLUIDO', ?, ?, ?)", ident, hoje, hoje, hora, vezes)
    db.salvar_config("config_rotina", {"ultimo_boa_noite": hoje, "hora_ultimo_boa_noite": "21:05"})
    principal = checkup.postagens_de_hoje(AGORA)["Canal principal"]
    assert principal["boa_noite"] == "21:05"
    assert principal["depois_da_boa_noite"] == [("21:14", 0), ("21:34", 1), ("21:47", 0)]
    parado = {"ativo": False, "vencidos": 0, "salvos": 0, "ruins": []}
    pontos = checkup.pontos_de_atencao([], {}, checkup.postagens_de_hoje(AGORA), parado, {}, ("x", 5.0, 1), AGORA)
    assert "Canal principal: 3 vídeo(s) depois da Boa Noite (21:05)" in pontos
    # A Boa Noite de outro dia não conta.
    db.salvar_config("config_rotina", {"ultimo_boa_noite": "2026-10-22", "hora_ultimo_boa_noite": "21:05"})
    assert checkup.postagens_de_hoje(AGORA)["Canal principal"]["depois_da_boa_noite"] == []


def test_canal_principal_pausado_nao_cobra_o_atraso_nem_o_dia_sem_post():
    # A pausa da suspensão da Shopee Vídeo para o canal por dias: o pendente de ontem espera a
    # volta, que refaz as datas, e o checkup não cobra o que a pausa explica.
    _filas_de_teste()
    inserir("INSERT INTO fila_postagens VALUES ('c', '2026-10-22', 'PENDENTE', NULL)")
    for dia in ("2026-10-21", "2026-10-22"):
        inserir("INSERT INTO historico_metricas VALUES (?, 'posts_dia_principal', 9)", dia)
    parado = {"ativo": False, "vencidos": 0, "salvos": 0, "ruins": []}
    db.salvar_config("pausa_programada", {"ativa": True, "data_retorno": "26/10/2026 03:05"})
    filas = checkup.postagens_de_hoje(AGORA)
    assert (filas["Canal principal"]["atrasados"], filas["Canal principal"]["pausado"]) == (1, "26/10/2026 03:05")
    assert checkup.pontos_de_atencao([], {}, filas, parado, {}, ("x", 5.0, 1), AGORA) == []

    db.salvar_config("pausa_programada", {"ativa": False, "data_retorno": None})
    filas = checkup.postagens_de_hoje(AGORA)
    texto = "\n".join(checkup.pontos_de_atencao([], {}, filas, parado, {}, ("x", 5.0, 1), AGORA))
    assert filas["Canal principal"]["pausado"] is None
    assert "Canal principal: 1 item(ns) atrasado(s)" in texto and "Canal principal: nenhum post hoje" in texto


def test_fila_sem_tabela_nao_derruba_o_checkup():
    filas = checkup.postagens_de_hoje(AGORA)
    assert filas["Parceiros"]["postados"] is None and filas["Canal principal"]["media"] is None


def test_robo_da_shopee_video_horarios_vencidos_e_tentativas_ruins():
    import robo_shopee_video as robo
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_pausado": False})
    db.salvar_config(robo.CHAVE_DIA, {"data": "2026-10-23", "horarios": ["09:43", "12:40", "23:10"], "feitos": 2})
    robo.registrar_tentativa("rascunho", "salvo", agora=AGORA - timedelta(hours=12))
    # Os rascunhos contam pela tabela deles: o histórico das tentativas pode ter começado depois.
    robo.atualizar(robo.criar("v1", AGORA - timedelta(hours=12)), estado="postado")
    robo.atualizar(robo.criar("v2", AGORA - timedelta(hours=9)), estado="pulado")
    robo.criar("v3", AGORA - timedelta(hours=1))                                  # ainda preparando
    robo.atualizar(robo.criar("v0", AGORA - timedelta(days=1)), estado="rascunho")  # ontem
    robo.registrar_tentativa("rascunho", "parou", "não achei o botão Rascunhos", "Fone X",
                             agora=AGORA - timedelta(hours=9))

    robo.registrar_tentativa("rascunho", "pulado", "o produto do vídeo não está na lista", "Fone X",
                             agora=AGORA - timedelta(hours=8))
    robo.registrar_tentativa("rascunho", "pulado", "o produto do vídeo não está na lista", "Fone X",
                             agora=AGORA - timedelta(hours=2))

    r = checkup.robo_da_shopee_video(AGORA)
    assert (r["ativo"], r["horarios"], r["vencidos"], r["salvos"], r["pulados"]) == (True, 3, 2, 1, 1)
    assert r["ruins"] == [("rascunho", "parou", "navegar no app", 1)]
    # Os pulados também, com a hora da primeira e da última vez (diz se continua depois de uma correção).
    primeiro, ultimo = ((AGORA - timedelta(hours=h)).strftime("%H:%M") for h in (8, 2))
    assert ("rascunho", "pulado", "anexar o produto", 2, primeiro, ultimo) in r["linhas"]
    assert "Fone X" not in str(r)


def test_checkup_mostra_a_faixa_do_painel_e_com_que_o_plano_do_dia_foi_feito():
    # 06/11: o plano saiu com 1 rascunho com 8 pontos, e o checkup não mostrava a faixa que o robô
    # leu nem com que faixa e pontos o plano foi feito.
    import painel_shopee_video as painel
    import robo_shopee_video as robo
    assert checkup.FAIXA_PADRAO_DO_ROBO_SV == (robo.PADRAO["robo_limite_min"], robo.PADRAO["robo_limite_max"])
    assert checkup.FAIXA_PADRAO_DO_ASSISTENTE_SV == (painel.PADRAO["limite_min"], painel.PADRAO["limite_max"])
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_pausado": False})
    robo.gravar_estado(saude_pontos=8, saude_lida_em=_momento(1))
    r = checkup.robo_da_shopee_video(AGORA)
    assert checkup.linha_das_faixas(r) == (
        "Rascunhos por Dia do robô: 1 a 2 (a padrão, nunca mudada no painel), pelos pontos 1 | "
        "Vídeos por Dia do assistente: 5 a 10 (a padrão, nunca mudada no painel), pelos pontos 2 a 3")
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_pausado": False, "robo_limite_min": 8, "robo_limite_max": 12,
                                         "limite_min": 6, "limite_max": 6})
    db.salvar_config(robo.CHAVE_DIA, {"data": "2026-10-23", "horarios": ["21:03"], "feitos": 0,
                                      "feito_com": {"faixa": [1, 2], "pontos": 8}})
    r = checkup.robo_da_shopee_video(AGORA)
    assert checkup.linha_das_faixas(r) == (
        "Rascunhos por Dia do robô: 8 a 12, pelos pontos 2 a 3 | Vídeos por Dia do assistente: 6, pelos pontos 2 | "
        "o plano de hoje foi feito com a faixa 1 a 2 e 8 ponto(s)")
    # Feito com o que vale agora, o plano não ganha a parte dele.
    db.salvar_config(robo.CHAVE_DIA, {"data": "2026-10-23", "horarios": ["14:01", "17:23"], "feitos": 0,
                                      "feito_com": {"faixa": [8, 12], "pontos": 8}})
    assert "plano de hoje" not in checkup.linha_das_faixas(checkup.robo_da_shopee_video(AGORA))


def test_horarios_sem_tentativa_nao_sao_cobrados():
    # 28/10: a suspensão pulou os horários da manhã e a pausa sem o celular juntou os da tarde
    # num só; o checkup cobrava "8 horários vencidos e 1 rascunho salvo".
    import robo_shopee_video as robo
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_pausado": False})
    db.salvar_config(robo.CHAVE_DIA, {"data": "2026-10-23", "horarios": ["09:43", "12:40", "15:10", "21:30"],
                                      "feitos": 4, "sem_tentar": 3})
    robo.atualizar(robo.criar("v1", AGORA - timedelta(hours=1)), estado="rascunho")
    r = checkup.robo_da_shopee_video(AGORA)
    assert (r["vencidos"], r["sem_tentar"], r["salvos"]) == (4, 3, 1)
    assert not any("com tentativa hoje" in p for p in checkup.pontos_de_atencao([], {}, {}, r, {}, None, AGORA))
    # Com uma tentativa a mais sem rascunho, cobra.
    db.salvar_config(robo.CHAVE_DIA, {"data": "2026-10-23", "horarios": ["09:43", "12:40", "15:10", "21:30"],
                                      "feitos": 4, "sem_tentar": 2})
    r = checkup.robo_da_shopee_video(AGORA)
    assert "Robô da Shopee Vídeo: 2 horário(s) com tentativa hoje e 1 rascunho(s) salvo(s) (0 vídeo(s) pulado(s))" in \
        checkup.pontos_de_atencao([], {}, {}, r, {}, None, AGORA)


def test_robo_agora_mostra_as_falhas_recentes_e_o_aprovado_que_passou_da_hora():
    # Pedido do Rafael (25/10): o Claude reconhece sozinho, na retomada de cada 3 h, as falhas
    # do robô e o aprovado que não saiu, sem esperar o checkup da noite nem o Rafael pedir.
    import robo_shopee_video as robo
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_pausado": False})
    robo.registrar_tentativa("feed", "parou", "o painel de comentários do vídeo do feed não abriu",
                             agora=AGORA - timedelta(hours=2))
    robo.registrar_tentativa("feed", "parou", "o painel de comentários do vídeo do feed não abriu",
                             agora=AGORA - timedelta(hours=1))
    robo.registrar_tentativa("rascunho", "pulado", "o produto do vídeo não está na lista", "Fone X",
                             agora=AGORA - timedelta(hours=8))
    atrasado = robo.criar("v1", AGORA - timedelta(hours=3))
    robo.atualizar(atrasado, estado="aprovado", postar_em=(AGORA - timedelta(minutes=90)).strftime("%Y-%m-%d %H:%M:%S"))
    na_hora = robo.criar("v2", AGORA - timedelta(hours=3))
    robo.atualizar(na_hora, estado="aprovado", postar_em=(AGORA - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"))
    texto = "\n".join(checkup.robo_agora(AGORA))
    tres, doze = texto.split("últimas 12 h")
    assert "últimas 3 h: paradas ou erros 2 | pulados 0" in tres and "2x feed → parou em" in tres
    assert "paradas ou erros 2 | pulados 1" in doze and "rascunho → pulado" in doze
    # Só o que passou da hora há mais de 30 min (a rodada é a cada 15 min).
    assert "Aprovados que passaram da hora (mais de 30 min): 1 (o mais atrasado há 90 min) | Postagem: ativa" in texto
    assert "Fone X" not in texto
    r = checkup.robo_da_shopee_video(AGORA)
    assert (r["atrasados"], r["minutos_de_atraso"]) == (1, 90)
    pontos = checkup.pontos_de_atencao([], {}, {}, r, {}, None, AGORA)
    assert "Robô da Shopee Vídeo: 1 aprovado(s) passaram da hora de ir ao ar (o mais atrasado há 90 min)" in pontos
    # Pausado pelo Rafael, o aprovado esperando não é falha.
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_pausado": True})
    r = checkup.robo_da_shopee_video(AGORA)
    assert not any("aprovado" in p for p in checkup.pontos_de_atencao([], {}, {}, r, {}, None, AGORA))
    assert "Postagem: pausada" in checkup.robo_agora(AGORA)[-1]


def test_checkup_conta_os_videos_do_canal_afiliados_na_fila_do_viral():
    # O loop (vídeo do Rafael, 30/10, 22:28): o Espião traz o Canal Afiliados para a fila do
    # Viral; o checkup mostra quantos são, que o robô e o assistente não pegam.
    import pedidos_do_canal
    db.salvar_config("fila_clonagem", {"fila": [{"id": "1", "chat_origem": pedidos_do_canal.CANAL},
                                                {"id": "2", "chat_origem": "-1001"}]})
    assert checkup.robo_da_shopee_video(AGORA)["do_canal_no_viral"] == 1


def test_video_postado_que_nao_entra_na_fila_do_canal_e_cobrado(tmp_path):
    # Pedido do Rafael (28/10, P62): o vídeo que o robô postou vai à fila do Canal Afiliados;
    # o que fica esperando (o bot_mestre confere a cada 5 min) vira ponto de atenção.
    import pedidos_do_canal
    video = tmp_path / "rascunho.mp4"
    video.write_bytes(b"video")
    pedidos_do_canal.pedir(1, str(video), "https://sv.shopee.com.br/share-video/abc", [],
                           agora=AGORA - timedelta(minutes=checkup.ESPERA_DO_CANAL + 5))
    pedidos_do_canal.pedir(2, str(video), "https://sv.shopee.com.br/share-video/abc", [], agora=AGORA)
    r = checkup.robo_da_shopee_video(AGORA)
    assert r["canal_parados"] == 1
    pontos = checkup.pontos_de_atencao([], {}, {}, r, {}, None, AGORA)
    assert ("Canal Afiliados: 1 vídeo(s) postado(s) pelo robô da Shopee Vídeo esperando há mais de "
            f"{checkup.ESPERA_DO_CANAL} min para entrar na fila do canal") in pontos
    assert checkup.robo_agora(AGORA)[-1].endswith(
        f"Canal Afiliados, postados esperando a fila há mais de {checkup.ESPERA_DO_CANAL} min: 1")
    pedidos_do_canal.concluir(1)
    r = checkup.robo_da_shopee_video(AGORA)
    assert not any("Canal Afiliados" in p for p in checkup.pontos_de_atencao([], {}, {}, r, {}, None, AGORA))


def test_aprovados_postados_mostram_o_atraso_sobre_o_previsto():
    # 25/10: o Rafael viu um aprovado que "ficou de postar agora" sair depois; o checkup
    # mostra o aprovado, o previsto e o postado de cada um, e cobra o que atrasou demais.
    import robo_shopee_video as robo

    def em(horas_atras):
        return (AGORA - timedelta(hours=horas_atras)).strftime("%Y-%m-%d %H:%M:%S")

    na_hora = robo.criar("v1", AGORA - timedelta(hours=5))
    robo.atualizar(na_hora, estado="postado", aprovado_em=em(4), postar_em=em(3.5), postado_em=em(3.4))
    tarde = robo.criar("v2", AGORA - timedelta(hours=5))
    robo.atualizar(tarde, estado="postado", aprovado_em=em(3), postar_em=em(2.5), postado_em=em(1.5))
    # 09/11: um aprovado saiu 36 min depois do previsto, e o checkup não dizia o que segurou o
    # celular. No atrasado, vêm as tentativas do robô entre o previsto e o postado, por ação, e os
    # pedidos do Preparar 1 Agora.
    import registro_processos
    for horas in (2.4, 2.2, 1.9):
        robo.registrar_tentativa("rascunho", "pulado", "anexar o produto", agora=AGORA - timedelta(hours=horas))
    robo.registrar_tentativa("feed", "ok", agora=AGORA - timedelta(hours=1.6))
    robo.registrar_tentativa("rascunho", "salvo", agora=AGORA - timedelta(hours=1))      # depois do post
    for horas in (2.45, 2.25):
        registro_processos.registrar("shopee_video", checkup.PROCESSO_DO_BOTAO, "pedido", ok=None,
                                     agora=AGORA - timedelta(hours=horas))
    r = checkup.robo_da_shopee_video(AGORA)
    assert [p[3] for p in r["postados"]] == [6, 60]
    assert [p[4] for p in r["postados"]] == ["", "no meio: rascunho 3, feed 1; Preparar 1 Agora 2"]
    pontos = checkup.pontos_de_atencao([], {}, {}, r, {}, None, AGORA)
    assert "Robô da Shopee Vídeo: 1 aprovado(s) foram ao ar com mais de 30 min de atraso (o maior: 60 min)" in pontos


def test_sobreposicoes_mostram_tarefa_no_horario_de_outra():
    # Pergunta do Rafael (25/10): uma tarefa em cima da outra pode atrapalhar; o checkup mostra
    # quando o robô fez outra coisa na hora do descurtir antes de a limpeza acabar, as leituras das
    # respostas e o post antigo fora do dia ou coladas (P161 1), as rotinas coladas e os envios do
    # assistente. A janela das interações que ficou no banco não conta mais.
    import robo_shopee_video as robo
    import registro_processos
    assert checkup.HORA_DO_DESCURTIR_SV == robo.HORA_DO_DESCURTIR
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_pausado": False, "robo_interacoes_inicio": 9,
                                         "robo_interacoes_fim": 11})
    dia = AGORA.strftime("%Y-%m-%d")

    def em(hora):
        return datetime.strptime(f"{dia} {hora}", "%Y-%m-%d %H:%M").replace(tzinfo=fuso_horario)

    registro_processos.registrar("shopee_video", "rodada fora do bot", "unidade própria", agora=em("04:00"))
    registro_processos.registrar("shopee_video", "curtir o produto", "curtido agora", agora=em("04:05"))   # antes dela
    robo.registrar_tentativa("descurtir", "descurtido", agora=em("04:10"))
    registro_processos.registrar("shopee_video", "descurtir tudo (4h)", "descurtido", agora=em("04:12"))
    robo.registrar_tentativa("feed", "comentado", agora=em("04:20"))                # acabada a limpeza: livre
    robo.registrar_tentativa("apagar", "apagado", agora=em("04:30"))
    robo.registrar_tentativa("rascunho", "salvo", agora=em("09:30"))                # na antiga janela: certo
    robo.registrar_tentativa("post_antigo", "comentado", agora=em("10:20"))         # durante o dia: certo
    robo.registrar_tentativa("feed", "comentado", agora=em("15:00"))                # o feed, no dia todo (P152)
    robo.registrar_tentativa("post_antigo", "comentado", agora=em("22:05"))         # fora do dia
    registro_processos.registrar("shopee_video", robo.PROCESSO_DA_LEITURA, "1ª de 3 hoje", agora=em("08:10"))
    registro_processos.registrar("shopee_video", robo.PROCESSO_DA_LEITURA, "2ª de 3 hoje", agora=em("10:00"))
    registro_processos.registrar("shopee_video", robo.PROCESSO_DA_LEITURA, "3ª de 3 hoje", agora=em("22:10"))
    registro_processos.registrar("shopee_video", "assistente: envio", "postagem mandada no seu privado",
                                 agora=em("15:20"))
    db.salvar_config("config_rotina", {"historico_diario": {"data": dia, "contagem": {
        "link_grupo_viral": ["10:00", "18:00"], "promo_principal": ["10:00"]}}})
    r = checkup.sobreposicoes(AGORA)
    assert [hora for hora, _o in r["no_descurtir"]] == ["04:05"] and r["pedidos_no_botao"] == []
    assert [hora for hora, _o in r["antigo_fora"]] == ["22:05"]
    assert r["leituras_fora"] == [("22:10", "3ª de 3 hoje")]
    assert r["leituras_coladas"] == [("08:10", "10:00")]
    assert r["rotinas_coladas"] == {"Viral": [("10:00", "link_grupo_viral", "10:00", "promo_principal")]}
    assert r["assistente"] == [("15:20", "postagem mandada no seu privado")]
    pontos = checkup.pontos_de_atencao([], {}, {}, {"ativo": False, "ruins": [], "salvos": 0, "vencidos": 0},
                                       {}, None, AGORA, sobre=r)
    assert ("Sobreposição: 1 atividade(s) do robô da Shopee Vídeo na hora do descurtir (4h) antes de a limpeza "
            "acabar") in pontos
    assert "Sobreposição: 1 leitura(s) das respostas fora do dia (das 8h às 22h)" in pontos
    assert "Sobreposição: 1 leitura(s) das respostas a menos de 3 h da anterior" in pontos
    assert "Sobreposição: 1 comentário(s) no post antigo fora do dia (das 8h às 22h)" in pontos


def test_pedido_nos_botoes_nao_e_sobreposicao():
    # 31/10, 20:32: o rascunho pedido no Preparar 1 Agora entrou como sobreposição, como se o robô
    # tivesse preparado sozinho. O pedido nos botões do painel vale a qualquer hora: o que o robô faz
    # logo depois dele aparece à parte.
    import robo_shopee_video as robo
    import registro_processos
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_pausado": False})
    dia = AGORA.strftime("%Y-%m-%d")

    def em(hora):
        return datetime.strptime(f"{dia} {hora}", "%Y-%m-%d %H:%M").replace(tzinfo=fuso_horario)

    registro_processos.registrar("shopee_video", robo.PROCESSO_DO_BOTAO, "pedido", ok=None, agora=em("04:00"))
    # O próximo vídeo do mesmo pedido (P133) é da mesma rodada: não estica a meia hora do pedido.
    registro_processos.registrar("shopee_video", robo.PROCESSO_DO_BOTAO, "próximo vídeo",
                                 "o 2º, aos 7,0 min da rodada", ok=None, agora=em("04:07"))
    robo.registrar_tentativa("rascunho", "salvo", agora=em("04:11"))                # o pedido no botão
    robo.registrar_tentativa("rascunho", "pulado", agora=em("04:35"))               # do plano, antes da limpeza
    robo.registrar_tentativa("descurtir", "descurtido", agora=em("04:50"))
    r = checkup.sobreposicoes(AGORA)
    assert [hora for hora, _o in r["pedidos_no_botao"]] == ["04:11"]
    assert [hora for hora, _o in r["no_descurtir"]] == ["04:35"]
    # O post pedido no Postar Agora 🚀 (P138) também vale a qualquer hora.
    assert checkup.PROCESSO_DO_POSTAR_AGORA == robo.PROCESSO_DO_POSTAR_AGORA
    assert checkup.classificado("shopee_video", robo.PROCESSO_DO_POSTAR_AGORA)
    registro_processos.registrar("shopee_video", robo.PROCESSO_DO_POSTAR_AGORA, "pedido", ok=None,
                                 agora=em("04:36"))
    robo.registrar_tentativa("postar", "postado", agora=em("04:38"))
    r = checkup.sobreposicoes(AGORA)
    assert [hora for hora, _o in r["pedidos_no_botao"]] == ["04:11", "04:38"]
    assert [hora for hora, _o in r["no_descurtir"]] == ["04:35"]
    # O que ele pede no Fazer Agora ⏩ (P162 1) também: a leitura pedida às 22:10 não é a do robô fora do dia.
    assert checkup.PROCESSO_DO_FAZER_AGORA == robo.PROCESSO_DO_FAZER_AGORA
    assert checkup.classificado("shopee_video", robo.PROCESSO_DO_FAZER_AGORA)
    registro_processos.registrar("shopee_video", robo.PROCESSO_DO_FAZER_AGORA, "pedido", "Responder Comentários",
                                 ok=None, agora=em("22:05"))
    registro_processos.registrar("shopee_video", robo.PROCESSO_DA_LEITURA, "1ª de 3 hoje", agora=em("22:10"))
    assert checkup.sobreposicoes(AGORA)["leituras_fora"] == []


def test_pontos_de_atencao():
    erros = [{"origem": "bot_mestre.py", "lugar": "bot_mestre.py:10", "texto": "x", "tipo": "ValueError",
              "qtd": 1, "ultimo": "10:00", "novo": True},
             {"origem": "a", "lugar": "a.py:1", "texto": "y", "tipo": "(sem rastro)", "qtd": 2, "ultimo": "",
              "novo": False}]
    logs = {"downloader_bot": {"quedas": 1, "rastros": 2, "erros": 3, "avisos": 0,
                               "rastros_por_lugar": [("ValueError", "downloader_bot.py:9 (f)", 2)],
                               "problemas": [("downloader_bot.py:5", "t", "error", 3)]}}
    filas = {"Viral": {"postados": 0, "para_hoje": 0, "atrasados": 2, "media": 4.0},
             "Autorais": {"postados": 0, "para_hoje": 0, "atrasados": 0, "media": 1.0}}
    robo_sv = {"ativo": True, "horarios": 3, "vencidos": 2, "salvos": 1,
               "ruins": [("rascunho", "parou", "navegar no app", 1)]}
    pontos = checkup.pontos_de_atencao(erros, logs, filas, robo_sv, {"falha(s) de download": 4}, None, AGORA)
    texto = "\n".join(pontos)
    assert "erro novo: 1x bot_mestre.py:10" in texto and "a.py:1" not in texto   # 2x antigo não cobra
    assert "downloader_bot: caiu" in texto and "downloader_bot.py:5" in texto
    assert ("2 rastro(s) de erro no log depois do último início (2 em 24 h; mais comum: ValueError em "
            "downloader_bot.py:9 (f), 2x)") in texto
    assert "Viral: 2 item(ns) atrasado(s)" in texto and "Viral: nenhum post hoje" in texto
    assert "Autorais: nenhum post" not in texto      # média baixa não cobra
    assert "2 horário(s) com tentativa hoje" in texto and "navegar no app" in texto
    assert "Baixador: 4 falha(s)" in texto and "Backup: nenhum" in texto
    assert checkup.pontos_de_atencao([], {}, {}, {"ativo": False, "vencidos": 3, "salvos": 0, "ruins": []},
                                     {}, ("x", 5.0, 1), AGORA) == []


def test_saida_completa_sem_dado_privado(monkeypatch, capsys):
    _filas_de_teste()
    _erro(1, "buscador_produtos (produto secreto): falhou")
    monkeypatch.setattr(checkup, "ler_journal", lambda servico: [
        "2026-10-23 10:00:00.123 -0300 - ❌ [Métricas] Falha na coleta diária: conteúdo secreto"])
    monkeypatch.setattr(checkup, "ler_eventos_do_systemd", lambda servico: [
        ("22:09", checkup.MORTO_AO_PARAR)] if servico == "bot_mestre_bot" else [])
    monkeypatch.setattr(checkup.backup_dados, "ultimo_backup", lambda: None)
    checkup.main()
    saida = capsys.readouterr().out
    assert "   systemd: 22:09 não parou no tempo e foi morto" in saida
    assert "bot_mestre_bot: não parou no tempo ao ser parado e o systemd o matou 1 vez(es)" in saida
    for secao in ("== Erros registrados", "== Log de cada robô", "== Processos dos robôs", "== Postagens de hoje",
                  "== Robô da Shopee Vídeo",
                  "== Baixador e backup", "== Pontos de atenção"):
        assert secao in saida
    assert "secreto" not in saida
    assert "Backup: nenhum" in saida


def test_rotinas_espacamento_assunto_seguido_e_o_configurado():
    db.salvar_config("config_rotina", {
        "incentivo": {"inicio": 10, "fim": 20, "frequencia": 2},
        "link_grupo": {"inicio": 9, "fim": 21, "frequencia": 3},
        "promo_principal": {"inicio": 10, "fim": 20, "frequencia": 1},
        "link_grupo_publico": {"inicio": 9, "fim": 23, "frequencia": 2},
        "pausado_viral": True,
        "historico_diario": {"data": "2026-10-23", "contagem": {
            "incentivo": ["10:00", "10:05", "15:00"],           # 3 de 2 configuradas, duas juntas
            "link_grupo": ["12:00"],                            # 1 de 3, janela já fechou às 21h
            "link_grupo_publico": ["11:00"],                    # janela até 23h: ainda não cobra
        }},
    })
    r = checkup.rotinas_do_dia(AGORA)
    principal = r["canal principal"]
    assert (principal["enviadas"], principal["menor"], principal["curtos"], principal["seguidos"]) == (4, 5, 1, 1)
    # Qual foi o mesmo assunto em seguida, com os horários (26/10: só o número não dizia qual).
    assert principal["pares_seguidos"] == ["10:00 incentivo → 10:05 incentivo"]
    assert ("incentivo", 3, 2, "a mais") in principal["fora_do_previsto"]
    assert ("link_grupo", 1, 3, "a menos") in principal["fora_do_previsto"]
    assert r["Grupo Público"]["fora_do_previsto"] == []
    assert r["Viral"]["fora_do_previsto"] == [] and r["Viral"]["pausado"]   # pausado não cobra "a menos"
    pontos = checkup.pontos_de_atencao([], {}, {}, {"ativo": False, "vencidos": 0, "salvos": 0, "ruins": []},
                                       {}, ("x", 1.0, 1), AGORA, {}, r, None)
    assert "Rotinas do canal principal: 1 intervalo(s) abaixo de 10 min (menor: 5 min)" in pontos
    assert "Rotinas do canal principal: 1 vez(es) o mesmo assunto em seguida" in pontos


def test_rotina_fora_da_janela_do_painel_e_cobrada():
    # P84 e P85 (29/10): cada rotina sai na janela dela e não espera o vídeo além do fim; o
    # espaçamento ainda pode empurrar a que saiu no fim da janela, até FOLGA_DA_JANELA min.
    db.salvar_config("config_rotina", {
        "incentivo": {"inicio": 10, "fim": 20, "frequencia": 3},
        "link_grupo_viral": {"inicio": 9, "fim": 21, "frequencia": 2},
        "historico_diario": {"data": "2026-10-23", "contagem": {
            "incentivo": ["09:45", "15:00", "20:20"],           # antes da janela; dentro; na folga
            "link_grupo_viral": ["12:00", "21:40"],             # dentro; 40 min depois do fim
            "promo_publico_viral": ["23:30"],                    # sem janela no banco: não conta
        }},
    })
    r = checkup.rotinas_do_dia(AGORA)
    assert r["canal principal"]["fora_da_janela"] == ["09:45 incentivo (janela 10h às 20h)"]
    assert r["Viral"]["fora_da_janela"] == ["21:40 link_grupo_viral (janela 9h às 21h)"]
    assert r["Grupo Público"]["fora_da_janela"] == []
    pontos = checkup.pontos_de_atencao([], {}, {}, {"ativo": False, "vencidos": 0, "salvos": 0, "ruins": []},
                                       {}, ("x", 1.0, 1), AGORA, {}, r, None)
    assert "Rotinas do canal principal: 1 vez(es) fora da janela do painel" in pontos
    assert "Rotinas do Viral: 1 vez(es) fora da janela do painel" in pontos
    # 29/10: o deploy das 20:33 religou o bot depois do fim das janelas, e a grade refeita
    # mandou logo as que se perderiam (P85). Essa não é cobrada; a de antes do começo, sim.
    r = checkup.rotinas_do_dia(AGORA, inicios=[8 * 60, 21 * 60 + 35])
    assert r["Viral"]["fora_da_janela"] == []
    assert r["Viral"]["depois_do_reinicio"] == ["21:40 link_grupo_viral (janela 9h às 21h), com o bot ligado às 21:35"]
    assert r["canal principal"]["fora_da_janela"] == ["09:45 incentivo (janela 10h às 20h)"]
    pontos = checkup.pontos_de_atencao([], {}, {}, {"ativo": False, "vencidos": 0, "salvos": 0, "ruins": []},
                                       {}, ("x", 1.0, 1), AGORA, {}, r, None)
    assert "Rotinas do Viral: 1 vez(es) fora da janela do painel" not in pontos
    assert "Rotinas do canal principal: 1 vez(es) fora da janela do painel" in pontos


def test_inicios_do_bot_saem_das_linhas_do_systemd():
    linhas = ["2026-10-29T20:33:05-0300 servidor systemd[1]: Started bot_mestre_bot.service - Bot Mestre.",
              "2026-10-29T20:33:09-0300 servidor python3[812]: Started a rodada",
              "2026-10-29T20:40:00-0300 servidor systemd[1]: Stopping bot_mestre_bot.service - Bot Mestre...",
              "2026-10-29T21:02:44-0300 servidor systemd[1]: Started bot_mestre_bot.service - Bot Mestre."]
    assert checkup.inicios_de_hoje(linhas) == [20 * 60 + 33, 21 * 60 + 2]


def test_rotina_em_seguida_sem_outro_assunto_marcado_nao_e_cobrada():
    # 28/10, Viral: promo_publico_viral às 18:57, 20:47 e 21:33. Sem outro assunto marcado no
    # dia, a regra deixa sair (23/10); o bot anota, e o checkup só cobra o que a regra segura.
    import registro_processos
    import rotinas
    db.salvar_config("config_rotina", {"historico_diario": {"data": "2026-10-23", "contagem": {
        "promo_publico_viral": ["18:57", "20:47", "21:33"]}}})
    registro_processos.registrar("bot_mestre", "rotina Viral", rotinas.EM_SEGUIDA_SEM_OUTRO, "promo_publico_viral",
                                 ok=None, agora=AGORA.replace(hour=21, minute=34))
    viral = checkup.rotinas_do_dia(AGORA)["Viral"]
    assert (viral["seguidos"], viral["seguidos_sem_outro"]) == (1, 1)
    assert viral["pares_seguidos"] == ["18:57 promo_publico_viral → 20:47 promo_publico_viral",
                                       "20:47 promo_publico_viral → 21:33 promo_publico_viral "
                                       "(sem outro assunto marcado)"]


def test_rotina_em_seguida_com_o_outro_assunto_so_depois_da_janela_nao_e_cobrada():
    # 09/11, Viral: a espera pelo outro assunto não passa do fim da janela da rotina (P93 e P94);
    # com o outro marcado só depois, ela sai na hora, o bot anota o porquê, e o checkup não a cobra.
    import registro_processos
    import rotinas
    db.salvar_config("config_rotina", {"historico_diario": {"data": "2026-10-23", "contagem": {
        "promo_achadinhos_viral": ["19:00", "19:30"]}}})
    registro_processos.registrar("bot_mestre", "rotina Viral", rotinas.EM_SEGUIDA_FIM_DA_JANELA,
                                 "promo_achadinhos_viral", ok=None, agora=AGORA.replace(hour=19, minute=31))
    viral = checkup.rotinas_do_dia(AGORA)["Viral"]
    assert (viral["seguidos"], viral["seguidos_sem_outro"]) == (0, 1)
    assert viral["pares_seguidos"] == ["19:00 promo_achadinhos_viral → 19:30 promo_achadinhos_viral "
                                       "(o outro assunto só depois do fim da janela)"]


def test_rotina_antiga_do_banco_nao_conta_e_a_que_falta_mostra_a_linha_do_tempo():
    # Checkup de 23/10: uma chave antiga do banco (sem texto no código, nunca enviada)
    # contava como 16 rotinas do canal principal, com intervalos curtos e "a menos".
    import registro_processos as rp
    db.salvar_config("config_rotina", {
        "repost_fake_publico": {"inicio": 8, "fim": 20, "frequencia": 20},
        "promo_principal": {"inicio": 8, "fim": 20, "frequencia": 3},
        "historico_diario": {"data": "2026-10-23", "contagem": {
            "repost_fake_publico": ["10:00", "10:01", "10:02"],
            "promo_principal": ["09:00", "15:00"],
        }},
    })
    for horas, resultado in ((9, "enviada"), (13, "adiada (intercalação)"), (15, "enviada"),
                             (19, "adiada (mesmo assunto em seguida)")):
        rp.registrar("bot_mestre", "rotina Viral", resultado, "promo_principal",
                     agora=AGORA.replace(hour=horas, minute=5))
    r = checkup.rotinas_do_dia(AGORA)
    assert r["canal principal"]["enviadas"] == 0 and r["canal principal"]["fora_do_previsto"] == []
    assert r["Viral"]["fora_do_previsto"] == [("promo_principal", 2, 3, "a menos")]
    assert r["Viral"]["linha_do_tempo"]["promo_principal"] == [
        ("09:05", "enviada"), ("13:05", "adiada (intercalação)"), ("15:05", "enviada"),
        ("19:05", "adiada (mesmo assunto em seguida)")]


def test_rotina_adiada_ha_pouco_ainda_vai_sair_e_a_de_ontem_que_nao_saiu_e_cobrada():
    # Checkup de 24/10: às 22:20, divulgar_gem_viral estava 2 de 3, adiada pela intercalação
    # às 21:51; saiu depois do checkup. A adiada há pouco não é cobrada; a de ontem que
    # ficou adiada e não saiu mais, sim (no checkup do dia seguinte).
    import registro_processos as rp
    db.salvar_config("config_rotina", {
        "divulgar_gem_viral": {"inicio": 8, "fim": 22, "frequencia": 3},
        "promo_principal": {"inicio": 8, "fim": 22, "frequencia": 2},
        "historico_diario": {"data": "2026-10-23", "contagem": {
            "divulgar_gem_viral": ["09:05", "17:51"], "promo_principal": ["10:00"]}},
    })

    def linha(quando, tipo, resultado):
        rp.registrar("bot_mestre", "rotina Viral", resultado, tipo, agora=quando)
    linha(AGORA.replace(hour=9, minute=5), "divulgar_gem_viral", "enviada")
    linha(AGORA.replace(hour=21, minute=51), "divulgar_gem_viral", "adiada (intercalação)")
    linha(AGORA.replace(hour=10, minute=0), "promo_principal", "enviada")
    linha(AGORA.replace(hour=19, minute=0), "promo_principal", "adiada (intercalação)")   # há 3 h: perdeu
    ontem = AGORA - timedelta(days=1)
    linha(ontem.replace(hour=21, minute=0), "link_grupo_viral", "enviada")
    linha(ontem.replace(hour=23, minute=10), "link_grupo_viral", "adiada (intercalação)")
    linha(ontem.replace(hour=23, minute=40), "promo_publico_viral", "adiada (intercalação)")
    linha(AGORA.replace(hour=0, minute=5), "promo_publico_viral", "enviada")       # saiu depois da meia-noite
    linha(ontem.replace(hour=22, minute=0), "promo_achadinhos_viral", "adiada (intercalação)")
    linha(ontem.replace(hour=22, minute=30), "promo_achadinhos_viral", "enviada")

    viral = checkup.rotinas_do_dia(AGORA)["Viral"]
    assert viral["adiadas"] == [("divulgar_gem_viral", 2, 3, "21:51")]
    assert viral["fora_do_previsto"] == [("promo_principal", 1, 2, "a menos")]
    assert viral["ontem_sem_sair"] == [("link_grupo_viral", "23:10")]
    pontos = checkup.pontos_de_atencao([], {}, {}, {"ativo": False, "vencidos": 0, "salvos": 0, "ruins": []},
                                       {}, ("x", 1.0, 1), AGORA, {}, {"Viral": viral}, None)
    assert not any("divulgar_gem_viral" in ponto for ponto in pontos)
    assert "Rotinas do Viral: ontem, link_grupo_viral ficou adiada e não saiu" in pontos
    assert "Rotinas do Viral: promo_principal saiu 1 vez(es), configurado 2 (a menos)" in pontos


def test_divulgacao_piso_por_grupo_assunto_seguido_e_rajada():
    import registro_processos as rp

    def envio(escopo, alvo, minutos_atras):
        rp.registrar("divulgacao", f"envio ({escopo})", "enviado", ok=True, origem=alvo,
                     agora=AGORA - timedelta(minutes=minutos_atras))
    envio("principal", "-1001", 120)
    envio("viral", "-1001", 110)        # outro assunto, 10 min depois: abaixo do piso de 15
    envio("viral", "-1001", 60)         # mesmo assunto em seguida, num grupo com dois assuntos
    envio("principal", "-1002", 100)
    envio("principal", "-1002", 40)     # grupo de um assunto só: em seguida é o normal
    d = checkup.divulgacao_do_dia(AGORA)
    assert (d["envios"], d["grupos"], d["curtos"], d["seguidos"]) == (5, 2, 1, 1)
    assert d["menor"] == 10 and d["pico"] == 1       # nenhum par a menos de 5 min
    assert "-1001" not in str(d)


def test_canal_de_cada_rotina():
    import rotinas
    assert rotinas.canal_da_rotina("promo_principal") == "Viral"
    assert rotinas.canal_da_rotina("promo_publico") == "canal principal"
    assert rotinas.canal_da_rotina("promo_publico_viral") == "Viral"
    assert rotinas.canal_da_rotina("link_grupo_publico") == "Grupo Público"
    assert rotinas.canal_da_rotina("campanha_pub_0_11.11") == "Grupo Público"
    assert rotinas.canal_da_rotina("campanha_0_11.11") == "canal principal"


def test_captura_por_grupo_de_origem_mostra_quem_parou_pela_posicao():
    import registro_processos as rp
    db.salvar_config("alvos_espiao", {"alvos": ["@GrupoA", "-1009:5", "@grupoc"]})
    db.salvar_config("espelhador_rotas", {"rotas": [{"nome": "r1", "origens": ["@origem1", "@origem2"]}]})
    # Grupo 1 manda hoje; o 2 mandou ontem e parou; o 3 nunca mandou.
    rp.registrar("espiao", "vídeo com link no grupo vigiado", "visto", origem="@grupoa",
                 agora=AGORA - timedelta(hours=2))
    rp.registrar("espiao", "vídeo com link no grupo vigiado", "visto", origem="-1009:5",
                 agora=AGORA - timedelta(hours=30))
    rp.registrar("espelhador", "vídeo com link na origem da rota", "visto", origem="@origem2",
                 agora=AGORA - timedelta(hours=1))
    c = checkup.captura_por_origem(AGORA)
    assert c["Espião"] == {"origens": 3, "com_video": 1, "sem_video": [2, 3], "pararam": [2], "pararam_todo_dia": [],
                           "por_dia": (1, 1, 0), "ultima_dos_que_pararam": None, "anotacao_desde": None,
                           "sem_link_dos_que_pararam": {2: 0}}
    assert c["Espelhador"]["sem_video"] == [1] and c["Espelhador"]["pararam"] == []

    def pontos():
        return checkup.pontos_de_atencao([], {}, {}, {"ativo": False, "vencidos": 0, "salvos": 0, "ruins": []},
                                         {}, ("x", 1.0, 1), AGORA, {}, {}, None, c, None)
    # Checkup de 04/11/2026: os grupos que postam de vez em quando param e voltam a cada dia. O que
    # mandou só num dos 2 dias antes fica na linha do sistema, sem virar ponto de atenção.
    assert pontos() == []
    # O que mandava nos dois dias e parou vira.
    rp.registrar("espiao", "vídeo com link no grupo vigiado", "visto", origem="-1009:5",
                 agora=AGORA - timedelta(hours=54))
    c = checkup.captura_por_origem(AGORA)
    assert c["Espião"]["pararam_todo_dia"] == [2] and c["Espião"]["por_dia"] == (1, 1, 1)
    assert pontos() == ["Espião: pararam de mandar vídeo (mandavam todo dia nos 2 dias antes): nº 2 da lista do painel"]


def test_grupo_que_parou_mostra_a_ultima_mensagem_que_chegou_dele():
    # Checkup de 06/11/2026: o nº 17 do Espião e o nº 13 do Espelhador pararam de mandar vídeo, e
    # não dava para saber se o grupo só não postou vídeo com link (mas manda mensagem) ou se nada
    # chegou dele (quieto, ou a conta perdeu o acesso). O motor_userbot anota a última mensagem de
    # cada grupo vigiado, e o checkup mostra a de cada grupo que parou.
    import registro_processos as rp
    db.salvar_config("alvos_espiao", {"alvos": ["@GrupoA", "@GrupoB", "@GrupoC"]})
    for origem, horas in (("@grupoa", 30), ("@grupob", 30), ("@grupoc", 2)):
        rp.registrar("espiao", "vídeo com link no grupo vigiado", "visto", origem=origem,
                     agora=AGORA - timedelta(hours=horas))
    db.salvar_config(checkup.CHAVE_DAS_ULTIMAS_MENSAGENS, {
        "desde": (AGORA - timedelta(hours=40)).strftime("%Y-%m-%d %H:%M:%S"),
        "espiao": {rp.apelido("@grupoa"): (AGORA - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")}})
    # Checkup de 07/11/2026: e quantos vídeos sem link reconhecido cada grupo que parou mandou em 24 h.
    for horas in (1, 3, 30):
        rp.registrar("espiao", "vídeo sem link no grupo vigiado", "visto", origem="@grupoa",
                     agora=AGORA - timedelta(hours=horas))
    c = checkup.captura_por_origem(AGORA)["Espião"]
    assert c["pararam"] == [1, 2] and set(c["ultima_dos_que_pararam"]) == {1, 2}
    assert c["sem_link_dos_que_pararam"] == {1: 2, 2: 0}
    desde = (AGORA - timedelta(hours=40)).strftime("%d/%m %H:%M")
    assert checkup._ultimas_dos_que_pararam(c, AGORA) == (f"nº 1 há 2 h (2 vídeo(s) sem link em 24 h) | "
                                                          f"nº 2 nenhuma desde {desde} (0 vídeo(s) sem link em 24 h)")
    # Sem a anotação (o motor_userbot ainda não gravou), a linha não aparece.
    db.salvar_config(checkup.CHAVE_DAS_ULTIMAS_MENSAGENS, {})
    c = checkup.captura_por_origem(AGORA)["Espião"]
    assert c["ultima_dos_que_pararam"] is None and checkup._ultimas_dos_que_pararam(c, AGORA) == ""


def test_parceiros_produto_repetido_entre_parceiros_e_com_a_conta_principal():
    with db.conexao() as c:
        c.execute("CREATE TABLE fila_parceiros (id_unico TEXT, parceiro_id INTEGER, data_captura TEXT, "
                  "chave_produto TEXT)")
        c.execute("CREATE TABLE videos_reservados (video_id TEXT PRIMARY KEY, parceiro_id INTEGER, data_reserva TEXT)")
        c.execute("CREATE TABLE links_resolvidos (codigo_curto TEXT PRIMARY KEY, chave_final TEXT, data_resolucao TEXT)")
        c.execute("INSERT INTO links_resolvidos VALUES ('abc1', 'prod_1_2', '2026-10-23')")
        for linha in (("p1", 1, "2026-10-23 10:00:00", "prod_1_2"),
                      ("p2", 2, "2026-10-23 11:00:00", "curto_abc1"),     # o mesmo produto, por link curto
                      ("p3", 1, "2026-10-23 12:00:00", "prod_7_8"),
                      ("p4", 2, "2026-10-15 12:00:00", "prod_9_9")):     # fora dos 3 dias
            c.execute("INSERT INTO fila_parceiros VALUES (?, ?, ?, ?)", linha)
        c.execute("INSERT INTO videos_reservados VALUES ('prod_7_8', 0, '2026-10-23 09:00:00')")
    db.salvar_config("fila_clonagem", {"fila": [{"link_original": "https://shopee.com.br/x-i.9.9",
                                                 "data_captura": "2026-10-23 08:00:00"}]})
    r = checkup.parceiros_repetidos(AGORA)
    assert r == {"capturas": 3, "entre_parceiros": 1, "com_a_conta": 1}


def test_verificacao_semanal_do_publico_so_numeros_e_cobra_atraso():
    db.salvar_config("moderacao_publico", {"quando": "2026-10-23 07:47:00", "mensagens": 900, "de_membros": 120,
                                           "suspeitas": 2, "por_regra": {"golpe ou fraude": 2}})
    p = checkup.verificacao_do_publico(AGORA)
    vazio = {"ativo": False, "vencidos": 0, "salvos": 0, "ruins": []}
    pontos = checkup.pontos_de_atencao([], {}, {}, vazio, {}, ("x", 1.0, 1), AGORA, {}, {}, None, {}, None, p)
    assert pontos == ["Grupo Público: 2 mensagem(ns) suspeita(s) na verificação semanal (o Rafael recebeu no privado)"]
    p = checkup.verificacao_do_publico(AGORA + timedelta(days=9))
    pontos = checkup.pontos_de_atencao([], {}, {}, vazio, {}, ("x", 1.0, 1), AGORA, {}, {}, None, {}, None, p)
    assert pontos == ["Grupo Público: a verificação semanal não roda há 10 dias"]
    db.salvar_config("moderacao_publico", {})
    assert checkup.verificacao_do_publico(AGORA) is None


def test_conta_suspensa_nao_cobra_horario_vencido_e_mostra_ate_quando():
    import robo_shopee_video as robo
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_pausado": False, "robo_suspenso_ate": "2026-10-26 19:04:26"})
    db.salvar_config(robo.CHAVE_DIA, {"data": "2026-10-23", "horarios": ["09:43", "12:40"], "feitos": 2})
    r = checkup.robo_da_shopee_video(AGORA)
    assert r["suspenso"] == "26/10 19:04" and r["vencidos"] == 2 and r["salvos"] == 0
    pontos = checkup.pontos_de_atencao([], {}, {}, r, {}, None, AGORA)
    assert not any("horário(s) com tentativa hoje" in p for p in pontos)
    # As punições que esperam o recurso aparecem só como número.
    import apelacoes_shopee_video as ap
    ap.guardar("Produto Irrelevante", "23/10/2026 19:04:25", "Não Recorrido", titulo="Botijão secreto")
    r = checkup.robo_da_shopee_video(AGORA)
    assert r["punicoes"] == 1 and "Botijão" not in str(r)
    # Depois do fim (e da folga), volta a cobrar.
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_pausado": False, "robo_suspenso_ate": "2026-10-23 10:00:00"})
    assert checkup.robo_da_shopee_video(AGORA)["suspenso"] == ""


def test_respostas_e_feed_da_shopee_video_no_radar():
    import registro_processos
    registro = registro_processos.registrar

    def antes(horas):
        return AGORA - timedelta(hours=horas)

    registro("shopee_video", "leitura das respostas", "1ª de 3 hoje", ok=None, agora=antes(10))
    registro("shopee_video", "notificações (respostas)", "topo achado", "2 linha(s) nova(s)", ok=True, agora=antes(10))
    registro("shopee_video", "responder comentário", "respondido", ok=True, origem="a", agora=antes(10))
    registro("shopee_video", "responder comentário", "resposta no lugar errado", ok=False, origem="b", agora=antes(9))
    registro("shopee_video", "responder comentário", "já respondido", "2 resposta(s) do perfil", ok=False,
             origem="c", agora=antes(9))
    registro("shopee_video", "responder comentário", "sem resposta", "3 tentativa(s)", ok=False, origem="d",
             agora=antes(8))
    for horas, origem in ((30, "v1"), (5, "v1"), (4, "v2"), (3, "v3")):
        registro("shopee_video", "feed: comentar", "comentado", ok=True, origem=origem, agora=antes(horas))
    registro("shopee_video", "feed: comentar", "não confirmado", ok=False, origem="v4", agora=antes(2))
    registro("shopee_video", "feed: comentar", "parou", ok=False, origem="v5", agora=antes(1))
    registro("shopee_video", "feed: comentar", "só curtido", ok=True, origem="v6", agora=antes(0.75))
    registro("shopee_video", "feed: comentar", "comentado", ok=True, origem="v7", agora=antes(0.5))
    r = checkup.interacoes_da_shopee_video(AGORA)
    assert r["respostas"] == {"respondido": 1, "resposta no lugar errado": 1, "já respondido": 1, "sem resposta": 1}
    assert r["duplicadas"] == 1 and r["rodou_hoje"] and r["feed_hoje"] == 6 and r["feed_repetidos"] == 1
    assert r["feed_horas"] == ["17:20", "18:20", "19:20", "20:20", "21:35", "21:50"]
    assert r["feed_so_curtidos"] == 1
    assert (r["leituras_hoje"], r["leituras_esperadas"]) == (1, 3)           # só uma das 3 do dia (P161 1)
    robo_sv = {"ativo": True, "vencidos": 0, "salvos": 0, "ruins": []}
    texto = "\n".join(checkup.pontos_de_atencao([], {}, {}, robo_sv, {}, ("x", 1.0, 1), AGORA, interacoes=r))
    for trecho in ("não ficaram embaixo do comentário certo", "ficaram sem resposta depois de 3 tentativas",
                   "com mais de uma resposta do perfil", "6 vídeos hoje (o limite é 5)",
                   "as Notificações foram lidas 1 de 3 vezes hoje",
                   "comentado(s) mais de uma vez em 3 dias"):
        assert trecho in texto
    # A meta do dia: sem as Notificações lidas, à noite, cobra. O feed tem limite, não meta: o dia
    # com menos é normal (P151 1).
    vazio = {"respostas": {}, "duplicadas": 0, "rodou_hoje": False, "feed_hoje": 1, "feed_repetidos": 0}
    texto = "\n".join(checkup.pontos_de_atencao([], {}, {}, robo_sv, {}, ("x", 1.0, 1), AGORA, interacoes=vazio))
    assert "as Notificações não foram lidas hoje" in texto and "Feed da Shopee Vídeo" not in texto
    pausado = dict(robo_sv, ativo=False)
    assert checkup.pontos_de_atencao([], {}, {}, pausado, {}, ("x", 1.0, 1), AGORA, interacoes=vazio) == []


def test_feed_so_curtido_conta_no_dia_e_o_dia_com_menos_nao_e_cobrado():
    # Escolha do Rafael (P151 1): nem toda curtida vem com comentário, e o feed tem limite, não
    # meta. O só curtido conta nos do dia; abaixo do limite, nada. O feed se espalha pelo dia todo
    # (P152) e não conta nas sobreposições.
    import registro_processos
    import robo_shopee_video as robo
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_pausado": False})
    dia = AGORA.strftime("%Y-%m-%d")

    def em(hora):
        return datetime.strptime(f"{dia} {hora}", "%Y-%m-%d %H:%M").replace(tzinfo=fuso_horario)

    registro_processos.registrar("shopee_video", "feed: comentar", "comentado", ok=True, origem="v1", agora=em("20:10"))
    registro_processos.registrar("shopee_video", "feed: comentar", "só curtido", "a IA não viu nada específico",
                                 ok=True, origem="v2", agora=em("20:25"))
    registro_processos.registrar("shopee_video", "feed: comentar", "não confirmado", ok=False, origem="v3",
                                 agora=em("20:40"))
    robo.registrar_tentativa("rascunho", "salvo", agora=em("20:50"))
    r = checkup.interacoes_da_shopee_video(AGORA)
    assert (r["feed_hoje"], r["feed_so_curtidos"]) == (3, 1)
    sobre = checkup.sobreposicoes(AGORA)
    assert sobre["no_descurtir"] == [] and sobre["antigo_fora"] == [] and sobre["leituras_fora"] == []
    robo_sv = {"ativo": True, "vencidos": 0, "salvos": 0, "ruins": []}
    r.update(respostas={}, duplicadas=0, rodou_hoje=True, leituras_hoje=1, leituras_esperadas=1,
             seguidores={"lido_hoje": True, "dia": None, "semana": None})
    pontos = checkup.pontos_de_atencao([], {}, {}, robo_sv, {}, ("x", 1.0, 1), AGORA, interacoes=r)
    assert not any(p.startswith("Feed da Shopee Vídeo") for p in pontos)
    r.update(feed_hoje=1)
    pontos = checkup.pontos_de_atencao([], {}, {}, robo_sv, {}, ("x", 1.0, 1), AGORA, interacoes=r)
    assert not any(p.startswith("Feed da Shopee Vídeo") for p in pontos)


def test_comentario_no_proprio_video_no_radar():
    # Escolha do Rafael (P148 2): o de depois do post vai com o post; o do post antigo é interação,
    # 1 por dia, cobrado à noite quando algum post podia ganhá-lo.
    import registro_processos
    import robo_shopee_video as robo
    assert checkup._tipo_da_atividade("post antigo: comentar") == "interação"
    assert checkup._tipo_da_atividade("próprio post: curtir o vídeo") == "preparo"
    assert checkup._tipo_da_atividade(acao="post_antigo") == "interação"
    assert checkup._tipo_da_atividade(acao="comentar_post") == "preparo"
    antes = AGORA - timedelta(hours=2)
    registro_processos.registrar("shopee_video", "próprio post: comentar", "comentado", ok=True, agora=antes)
    registro_processos.registrar("shopee_video", "próprio post: comentar", "desistiu", "x", ok=False, agora=antes)
    registro_processos.registrar("shopee_video", "próprio post: curtir o comentário", "curtido", ok=True, agora=antes)
    r = checkup.interacoes_da_shopee_video(AGORA)
    assert r["proprio"] == {"comentado": 1, "desistiu": 1} and r["antigos_hoje"] == 0
    assert r["proprio_curtidas"] == {"curtir o comentário → curtido": 1} and not r["antigo_possivel"]
    # Um post do robô de 10 dias atrás, nunca comentado: podia ganhar o comentário de hoje.
    ident = robo.criar("video:1", None)
    robo.atualizar(ident, estado="postado", postado_em=(AGORA - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S"),
                   link_post="https://exemplo.com/post")
    r = checkup.interacoes_da_shopee_video(AGORA)
    assert r["antigo_possivel"]
    robo_sv = {"ativo": True, "vencidos": 0, "salvos": 0, "ruins": []}
    r.update(respostas={}, duplicadas=0, rodou_hoje=True, feed_hoje=3, feed_repetidos=0,
             seguidores={"lido_hoje": True, "dia": None, "semana": None})
    texto = "\n".join(checkup.pontos_de_atencao([], {}, {}, robo_sv, {}, ("x", 1.0, 1), AGORA, interacoes=r))
    assert "1 post(s) sem o comentário depois de 3 tentativas" in texto
    assert "0 de 1 post antigo comentado hoje" in texto


def test_leituras_das_notificacoes_contam_as_vezes_do_dia():
    # Escolhas do Rafael (P70 e P161 1): as Notificações 3 vezes por dia, das 8h às 22h, uma em cada
    # parte do dia (8h, 12h40 e 17h20), cobrada só depois que a parte acaba.
    import registro_processos
    import robo_shopee_video as robo
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_inicio": 0, "robo_fim": 24})
    dia = AGORA.strftime("%Y-%m-%d")

    def em(hora):
        return datetime.strptime(f"{dia} {hora}", "%Y-%m-%d %H:%M").replace(tzinfo=fuso_horario)

    def leu(hora, vez):
        registro_processos.registrar("shopee_video", robo.PROCESSO_DA_LEITURA, f"{vez}ª de 3 hoje", ok=None,
                                     agora=em(hora))

    assert checkup.leituras_das_notificacoes(em("12:30")) == (0, 0)           # a 1ª ainda pode sair
    assert checkup.leituras_das_notificacoes(em("12:40")) == (0, 1)
    leu("12:10", 1)
    registro_processos.registrar("shopee_video", "notificações (respostas)", "topo achado", ok=True,
                                 agora=em("12:25"))                            # a continuação não conta
    assert checkup.leituras_das_notificacoes(em("12:45")) == (1, 1)
    assert checkup.leituras_das_notificacoes(em("17:20")) == (1, 2)           # a 2ª faltou
    leu("17:30", 2)                                                             # atrasada
    assert checkup.leituras_das_notificacoes(em("22:20")) == (2, 3)
    leu("20:30", 3)
    assert checkup.leituras_das_notificacoes(em("22:20")) == (3, 3)
    # A parte que cai toda fora do horário em que o robô roda não é cobrada.
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_inicio": 8, "robo_fim": 12})
    amanha = em("23:00").replace(day=AGORA.day + 1)
    assert checkup.leituras_das_notificacoes(amanha) == (0, 1)


def test_seguidores_mostram_so_a_variacao():
    # Escolha do Rafael (P70): o checkup mostra se os seguidores sobem; o número fica no banco.
    dia = AGORA.strftime("%Y-%m-%d")
    assert checkup.seguidores_da_shopee_video(AGORA) == {"lido_hoje": False, "dia": None, "semana": None}
    db.salvar_config(checkup.CHAVE_SEGUIDORES_SV, {"dias": {"2026-10-14": 90, "2026-10-15": 100,
                                                            "2026-10-22": 110, dia: 112}})
    assert checkup.seguidores_da_shopee_video(AGORA) == {"lido_hoje": True, "dia": 2, "semana": 12}
    robo_sv = {"ativo": True, "vencidos": 0, "salvos": 0, "ruins": []}
    interacoes = {"respostas": {}, "duplicadas": 0, "rodou_hoje": True, "feed_hoje": 3, "feed_repetidos": 0,
                  "seguidores": {"lido_hoje": False, "dia": None, "semana": None}}
    pontos = checkup.pontos_de_atencao([], {}, {}, robo_sv, {}, ("x", 1.0, 1), AGORA, interacoes=interacoes)
    assert any(p.startswith("Seguidores da Shopee Vídeo: não lidos hoje") for p in pontos)
    assert checkup._variacao(2) == "+2" and checkup._variacao(-1) == "-1" and checkup._variacao(None) == (
        "sem leitura de antes")


# Funções que dão o nome do processo, com o começo fixo que devolvem.
CHAMADAS = {"processo_do_pedido": "pedido "}


def _processos_no_codigo():
    """
    (robô, processo) de cada registrar e anotar do registro de processos nos .py do
    projeto, lidos pelo código (AST). Constante do módulo vale como texto; no f-string,
    vale o começo fixo.
    """
    import ast
    import os
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    achados = set()
    for nome in sorted(os.listdir(raiz)):
        if not nome.endswith(".py"):
            continue
        with open(os.path.join(raiz, nome), encoding="utf-8") as arquivo:
            arvore = ast.parse(arquivo.read())
        def texto(no):
            if isinstance(no, ast.Constant) and isinstance(no.value, str):
                return no.value
            if isinstance(no, ast.Name):
                return variaveis.get(no.id)
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name):
                return CHAMADAS.get(no.func.id)
            if isinstance(no, ast.JoinedStr):
                fixo = ""
                for parte in no.values:
                    if not isinstance(parte, ast.Constant):
                        break
                    fixo += parte.value
                return fixo
            return None

        # Variável com o nome do processo (constante do módulo ou f-string na função).
        variaveis = {}
        for no in ast.walk(arvore):
            if isinstance(no, ast.Assign) and len(no.targets) == 1 and isinstance(no.targets[0], ast.Name):
                valor = texto(no.value) if isinstance(no.value, (ast.Constant, ast.JoinedStr)) else None
                if valor is not None:
                    variaveis.setdefault(no.targets[0].id, valor)
        for no in ast.walk(arvore):
            if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                    and no.func.attr in ("registrar", "anotar") and isinstance(no.func.value, ast.Name)
                    and no.func.value.id == "registro_processos" and len(no.args) >= 2):
                robo, processo = texto(no.args[0]), texto(no.args[1])
                assert robo is not None and processo is not None, f"{nome}:{no.lineno}: robô ou processo sem texto fixo"
                achados.add((nome, no.lineno, robo, processo))
    return achados


def test_todo_processo_de_robo_tem_lugar_no_checkup():
    # Pedido do Rafael (P12): ação nova de robô sem registro e sem linha no checkup não passa.
    achados = _processos_no_codigo()
    assert len(achados) > 40
    fora = [f"{nome}:{linha} ({robo}, {processo})" for nome, linha, robo, processo in achados
            if not checkup.classificado(robo, processo)]
    assert not fora, "processo sem meta (METAS) nem lugar em SEM_META no checkup.py: " + "; ".join(fora)
    # E o contrário: o que está nas listas do checkup ainda existe no código.
    pares = {(robo, processo) for _n, _l, robo, processo in achados}
    for robo, processo in checkup.METAS:
        assert (robo, processo) in pares, f"meta de um processo que não existe mais: {robo}, {processo}"
    for robo, comeco in checkup.SEM_META:
        assert any(r == robo and p.startswith(comeco) for r, p in pares), f"SEM_META sobrando: {robo}, {comeco}"


def test_meta_de_cada_job_e_memoria_dos_pontos():
    import registro_processos
    for horas in range(10):
        registro_processos.registrar("bot_mestre", "monitor de saúde", "concluído", ok=True,
                                     agora=AGORA - timedelta(hours=horas))
    processos = checkup.processos_do_dia(AGORA)
    metas = {(r, p): (feito, minimo) for r, p, _e, feito, minimo in checkup.metas_do_dia(processos)}
    assert metas[("bot_mestre", "monitor de saúde")] == (10, 21)
    robo_sv = {"ativo": False, "vencidos": 0, "salvos": 0, "ruins": []}
    pontos = checkup.pontos_de_atencao([], {}, {}, robo_sv, {}, ("x", 1.0, 1), AGORA, processos,
                                       metas=checkup.metas_do_dia(processos))
    assert "bot_mestre: monitor de saúde: rodou 10 vez(es) em 24 h, o esperado é 24" in pontos

    # A memória: novo no 1º dia, repetido no 2º, resolvido no 3º e "voltou" no 4º.
    def dia(n):
        return AGORA + timedelta(days=n)
    marcas, resolvidos = checkup.lembrar_pontos(["Backup: o último tem 30 h"], dia(0))
    assert marcas == {"Backup: o último tem 30 h": "novo"} and resolvidos == []
    marcas, _ = checkup.lembrar_pontos(["Backup: o último tem 31 h"], dia(1))
    assert marcas == {"Backup: o último tem 31 h": "há 2 dias seguidos"}
    checkup.lembrar_pontos(["Backup: o último tem 31 h"], dia(1))        # rodou de novo no mesmo dia
    marcas, resolvidos = checkup.lembrar_pontos([], dia(2))
    assert resolvidos == ["Backup: o último tem # h"]
    marcas, _ = checkup.lembrar_pontos(["Backup: o último tem 27 h"], dia(3))
    assert marcas == {"Backup: o último tem 27 h": "voltou"}


def test_log_da_rodada_do_robo_e_lido_pelo_nome_no_journal(monkeypatch):
    # A rodada do robô da Shopee Vídeo roda numa unidade própria a cada vez: o log dela é
    # achado pelo nome (-t), e o dos serviços pela unidade (-u).
    pedidos = []

    class Feito:
        returncode, stdout = 0, "linha\n"

    monkeypatch.setattr(checkup.subprocess, "run", lambda partes, **k: pedidos.append(partes) or Feito())
    checkup.ler_journal("robo_shopee_video")
    checkup.ler_journal("bot_mestre_bot")
    assert pedidos[0][3:5] == ["-t", "robo_shopee_video"] and pedidos[1][3:5] == ["-u", "bot_mestre_bot.service"]


def test_medicao_dos_produtos_a_mais_so_com_numeros():
    # Escolha do Rafael (29/10, P73): em 7 dias, os números dos produtos a mais. O checkup mostra
    # os rascunhos, os postados, as vendas do produto do vídeo e dos a mais (a parte na comissão em
    # %, nunca o valor) e as punições de Produto Irrelevante.
    import apelacoes_shopee_video as ap
    import robo_shopee_video as robo
    vazio = checkup.produtos_a_mais_da_shopee_video(AGORA)
    assert (vazio["ligados"], vazio["salvos"], vazio["vendas_a_mais"], vazio["parte_a_mais"]) == (True, 0, 0, None)
    depois = AGORA + timedelta(days=7)
    com = [{"item": "1", "a_mais": False}, {"item": "2", "a_mais": True}, {"item": "3", "a_mais": True}]
    robo.atualizar(robo.criar("v1", AGORA + timedelta(days=6)), estado="postado", postado_em="2026-10-30 10:00:00",
                   itens=com)
    robo.atualizar(robo.criar("v2", AGORA + timedelta(days=6)), estado="rascunho",
                   itens=[{"item": "4", "a_mais": False}])
    robo.atualizar(robo.criar("v3", AGORA + timedelta(days=6)), estado="pulado", itens=com)
    db.salvar_config("banco_pedidos", {
        "a": {"data": "2026-10-30", "status": "COMPLETED", "etiqueta": "",
              "itens": [{"id": "2", "nome": "Garrafa Loja Dois", "qtd": 1, "comissao": 3.0}]},
        "b": {"data": "2026-10-31", "status": "PENDING", "etiqueta": "",
              "itens": [{"id": "1", "nome": "Garrafa", "qtd": 1, "comissao": 1.0}]}})
    ap.guardar("Produto Irrelevante", "30/10/2026 12:00:00", "Não Recorrido", agora=depois)
    # As tentativas contam pela contagem por dia: o histórico guarda só 3 dias.
    robo.registrar_tentativa("rascunho", "salvo", agora=depois - timedelta(days=1))
    robo.registrar_tentativa("rascunho", "parou", "não achei o botão Rascunhos", agora=depois - timedelta(days=1))
    robo.registrar_tentativa("rascunho", "verificação", "verificação", agora=depois - timedelta(hours=5))
    robo.registrar_tentativa("rascunho", "salvo", agora=depois)
    robo.registrar_tentativa("rascunho", "pulado", "antes da medição", agora=AGORA - timedelta(days=1))
    db.atualizar_config(robo.CHAVE_CONFIG, lambda dados: dados.update(
        robo_produtos_a_mais=False, robo_produtos_a_mais_parados="punição de Produto Irrelevante"))
    m = checkup.produtos_a_mais_da_shopee_video(depois)
    assert (m["salvos"], m["com_a_mais"], m["a_mais"], m["postados"], m["postados_com_a_mais"]) == (2, 1, 2, 1, 1)
    assert (m["vendas_do_video"], m["vendas_a_mais"], m["parte_a_mais"], m["punicoes"]) == (1, 1, 75, 1)
    linha = checkup._linha_dos_produtos_a_mais(m)
    assert linha.startswith("Produtos a mais (P73, desde 29/10): parados por punição de produto")
    assert "vendas: 1 do produto do vídeo, 1 dos produtos a mais (75% da comissão)" in linha
    assert m["tentativas"] == {"salvo": 2, "pulado": 0, "parou": 1, "erro": 0} and m["verificacoes"] == 1
    assert linha.endswith("| tentativas de rascunho: salvo 2, pulado 0, parou 1, erro 0 | verificações: 1")
    # Em que estado está cada rascunho com produtos a mais: o Rafael não o achou para aprovar (30/10).
    assert m["estados_com_a_mais"] == {"postado": 1}
    assert "(com produtos a mais 1: postado 1; produtos a mais 2)" in linha
    assert "Garrafa" not in linha and "R$" not in linha and "Rascunhos" not in linha


def test_medicao_da_capa_com_chamada_so_com_contagens_e_porcento():
    # Escolha do Rafael (29/10, P76): depois de 7 dias, as visualizações dos vídeos com a
    # chamada comparadas com as dos de antes. O log é público: só contagens e a diferença em %,
    # nunca o número de visualizações.
    import robo_shopee_video as robo
    vazio = checkup.capa_com_chamada_da_shopee_video(AGORA)
    assert not vazio["ligada"] and checkup._linha_da_capa_com_chamada(vazio).startswith(
        "Capa com chamada (P76): desligada | postados com a marca da capa: com a chamada 0, sem 0")
    for postado, chamada, marca, vistas in (
            # Antes de ligar: fora da comparação, que usa só os vídeos dos mesmos dias (P77).
            ("2026-10-25 10:00:00", "", "a", [["2026-10-26 10:00:00", 9999]]),
            ("2026-10-26 09:00:00", "", "a", [["2026-10-27 09:30:00", 1234]]),
            ("2026-10-26 10:00:00", "1", "b", [["2026-10-27 09:00:00", 1851]]),
            ("2026-10-26 12:00:00", "1", "", [])):
        robo.atualizar(robo.criar("v", AGORA - timedelta(days=3)), estado="postado", postado_em=postado,
                       chamada=chamada, marca=marca, vistas=vistas)
    db.atualizar_config(robo.CHAVE_CONFIG, lambda dados: dados.update(
        capa_com_chamada=True, capa_com_chamada_desde="2026-10-26 08:00:00"))
    medicao = checkup.capa_com_chamada_da_shopee_video(AGORA)
    linha = checkup._linha_da_capa_com_chamada(medicao)
    assert linha == ("Capa com chamada (P76): ligada desde 26/10 | postados com a marca da capa: com a chamada 1, "
                     "sem 1 (lidos 1 e 1); sem a marca 1 | com 1 dia(s): a chamada +50% (1 com, 1 sem) | "
                     "com 3 dia(s): sem comparação ainda (0 com, 0 sem)")
    assert "1234" not in linha and "1851" not in linha and "9999" not in linha


def test_o_que_espera_o_rafael_sai_dos_pontos_de_atencao():
    # P146 5: o que depende de algo que só o Rafael faz (os chips novos dos Autorais) vai para
    # "Esperando o Rafael", conferido pelos números do dia; resolvida a causa, volta a contar.
    import registro_processos
    for _ in range(3):
        registro_processos.registrar("autorais", "repostagem ao grupo", checkup.SEM_CONTA_DE_REPOSTAGEM, ok=False,
                                     agora=AGORA)
    pontos = ["Autorais: 1 item(ns) atrasado(s) na fila",
              "autorais: repostagem ao grupo: 3 falha(s) e 0 acerto(s) (mais comum: sem conta de repostagem, 3x)",
              "Viral: 2 item(ns) atrasado(s) na fila"]
    ficam, esperando = checkup.separar_o_que_espera_o_rafael(pontos, checkup.processos_do_dia(AGORA))
    assert ficam == ["Viral: 2 item(ns) atrasado(s) na fila"]
    assert [p for p, _o in esperando] == pontos[:2] and "chips novos dos Autorais" in esperando[0][1]

    # Uma repostagem que deu certo: a causa não é mais a falta de conta, e os dois voltam a contar.
    registro_processos.registrar("autorais", "repostagem ao grupo", "repostado", ok=True, agora=AGORA)
    ficam, esperando = checkup.separar_o_que_espera_o_rafael(pontos, checkup.processos_do_dia(AGORA))
    assert ficam == pontos and esperando == []


def test_senha_da_copia_diz_se_foi_guardada_e_se_o_lugar_esta_no_painel():
    # O lembrete diário cobra o Guardei a senha ✅: o checkup mostra se ele foi tocado e se o
    # lugar da senha está no Acessos do Servidor, sem nunca mostrar o lugar.
    import backup_dados
    import painel_acessos
    assert checkup.senha_da_copia() == ("senha da cópia: Guardei a senha ✅ ainda não tocado, "
                                        "lugar no Acessos do Servidor: não")
    db.salvar_config(backup_dados.CHAVE_STATUS, {"senha_guardada_em": "2026-11-03 21:40:05"})
    painel_acessos.salvar_servico("backup", {"onde": "https://exemplo.com/onde-esta"})
    linha = checkup.senha_da_copia()
    assert linha == "senha da cópia: Guardei a senha ✅ em 03/11 21:40, lugar no Acessos do Servidor: sim"
    assert "exemplo.com" not in linha


def test_celular_do_robo_fora_por_horas_vira_ponto_de_atencao():
    # De 03/11 a 05/11/2026 o adb do servidor ficou travado 37 h; na suspensão o robô não avisa do
    # celular fora (pedido do Rafael), e nada apontava. O checkup aponta, com as horas e o motivo fixo.
    import celular_robo
    motivo = "a Depuração por Wi-Fi responde no celular, mas o adb não conecta (o adb não respondeu)"
    db.salvar_config(celular_robo.CHAVE, {"pareado_em": "2026-10-17 10:00:00", "visto_em": "2026-10-22 09:20:00",
                                          "falha_em": "2026-10-23 22:07:00", "falha": motivo})
    fora = checkup.celular_fora(AGORA)
    assert fora == (37, motivo, "22:07")
    robo_sv = {"ativo": True, "vencidos": 0, "salvos": 0, "ruins": [], "celular_fora": fora}
    pontos = checkup.pontos_de_atencao([], {}, {}, robo_sv, {}, ("x", 1.0, 1), AGORA)
    assert pontos == [f"Celular do robô da Shopee Vídeo: sem conexão há 37 h (a última reconexão, às 22:07, "
                      f"falhou: {motivo})"]
    assert checkup.robo_da_shopee_video(AGORA)["celular_fora"] == fora
    # Visto depois da última falha (voltou), ou fora há menos de 3 h: nada.
    db.salvar_config(celular_robo.CHAVE, {"pareado_em": "x", "visto_em": "2026-10-23 22:10:00",
                                          "falha_em": "2026-10-23 22:07:00", "falha": motivo})
    assert checkup.celular_fora(AGORA) is None
    db.salvar_config(celular_robo.CHAVE, {"pareado_em": "x", "visto_em": "2026-10-23 20:00:00",
                                          "falha_em": "2026-10-23 22:07:00", "falha": motivo})
    assert checkup.celular_fora(AGORA) is None
    # Nunca pareado: nada.
    db.salvar_config(celular_robo.CHAVE, {})
    assert checkup.celular_fora(AGORA) is None

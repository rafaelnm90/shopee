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
    assert checkup.COMENTARIOS_NO_FEED_POR_DIA == robo.interacoes.COMENTARIOS_NO_FEED_POR_DIA
    assert checkup.HORAS_DAS_RESPOSTAS_SV == robo.HORAS_DAS_RESPOSTAS
    assert checkup.HORA_DAS_RESPOSTAS_SEM_JANELA_SV == robo.HORA_DAS_RESPOSTAS_SEM_JANELA
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
    assert pontos == ["baixador: pedido Shopee (vídeo): 4 falha(s) e 1 acerto(s) "
                      "(mais comum: não entregue - a Shopee demorou, 4x)"]


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
    r = checkup.robo_da_shopee_video(AGORA)
    assert [atraso for *_h, atraso in r["postados"]] == [6, 60]
    pontos = checkup.pontos_de_atencao([], {}, {}, r, {}, None, AGORA)
    assert "Robô da Shopee Vídeo: 1 aprovado(s) foram ao ar com mais de 30 min de atraso (o maior: 60 min)" in pontos


def test_sobreposicoes_mostram_tarefa_no_horario_de_outra():
    # Pergunta do Rafael (25/10): uma tarefa em cima da outra pode atrapalhar; o checkup mostra
    # quando o robô fez outra coisa na hora do descurtir, interação fora do Horário das
    # Interações, preparo dentro dele antes do feed, rotinas coladas e os envios do assistente.
    import robo_shopee_video as robo
    import registro_processos
    assert checkup.HORA_DO_DESCURTIR_SV == robo.HORA_DO_DESCURTIR
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_pausado": False, "robo_interacoes_inicio": 9,
                                         "robo_interacoes_fim": 11})
    dia = AGORA.strftime("%Y-%m-%d")

    def em(hora):
        return datetime.strptime(f"{dia} {hora}", "%Y-%m-%d %H:%M").replace(tzinfo=fuso_horario)

    robo.registrar_tentativa("descurtir", "descurtido", agora=em("04:10"))
    robo.registrar_tentativa("feed", "comentado", agora=em("04:20"))                # na hora do descurtir
    robo.registrar_tentativa("feed", "comentado", agora=em("15:00"))                # fora da janela
    robo.registrar_tentativa("rascunho", "salvo", agora=em("09:30"))                # antes dos 3 do feed
    robo.registrar_tentativa("rascunho", "salvo", agora=em("13:00"))                # fora da janela: certo
    robo.registrar_tentativa("responder", "respondido", agora=em("17:05"))          # as respostas: em qualquer hora (P70)
    # Apagar o rascunho recusado roda nos dois horários (P22 a P24): não é preparo na janela,
    # mas na hora do descurtir conta.
    robo.registrar_tentativa("apagar", "apagado", agora=em("09:40"))
    robo.registrar_tentativa("apagar", "apagado", agora=em("04:30"))
    registro_processos.registrar("shopee_video", "notificações (respostas)", "topo achado", agora=em("17:00"))
    registro_processos.registrar("shopee_video", "descurtir tudo (4h)", "descurtido", agora=em("04:12"))
    registro_processos.registrar("shopee_video", "curtir o produto", "curtido agora", agora=em("04:05"))
    registro_processos.registrar("shopee_video", "rodada fora do bot", "unidade própria", agora=em("04:00"))
    registro_processos.registrar("shopee_video", "assistente: envio", "postagem mandada no seu privado",
                                 agora=em("15:20"))
    db.salvar_config("config_rotina", {"historico_diario": {"data": dia, "contagem": {
        "link_grupo_viral": ["10:00", "18:00"], "promo_principal": ["10:00"]}}})
    r = checkup.sobreposicoes(AGORA)
    assert r["janela"] == (9, 11)
    assert [hora for hora, _o in r["no_descurtir"]] == ["04:05", "04:20", "04:30"]
    assert [hora for hora, _o in r["fora_da_janela"]] == ["04:20", "15:00"]
    assert [hora for hora, _o in r["preparo_na_janela"]] == ["09:30"]
    assert r["rotinas_coladas"] == {"Viral": [("10:00", "link_grupo_viral", "10:00", "promo_principal")]}
    assert r["assistente"] == [("15:20", "postagem mandada no seu privado")]
    pontos = checkup.pontos_de_atencao([], {}, {}, {"ativo": False, "ruins": [], "salvos": 0, "vencidos": 0},
                                       {}, None, AGORA, sobre=r)
    assert "Sobreposição: 3 atividade(s) do robô da Shopee Vídeo na hora do descurtir (4h)" in pontos
    assert "Sobreposição: 2 interação(ões) do robô fora do Horário das Interações" in pontos
    assert ("Sobreposição: 1 passo(s) de preparo ou postagem no Horário das Interações antes dos comentários "
            "do feed") in pontos
    # A janela escolhida às 10:00 não cobra o que o robô fez antes dela.
    db.atualizar_config(robo.CHAVE_CONFIG, lambda c: c.update(robo_interacoes_desde=f"{dia} 10:00:00"))
    r = checkup.sobreposicoes(AGORA)
    assert [hora for hora, _o in r["fora_da_janela"]] == ["15:00"] and r["preparo_na_janela"] == []
    assert r["janela_desde"] == f"{dia} 10:00:00"


def test_preparo_pedido_no_botao_nao_e_sobreposicao():
    # 31/10, 20:32: o rascunho pedido no Preparar 1 Agora dentro do Horário das Interações entrou
    # como sobreposição, como se o robô tivesse preparado sozinho antes do feed. O pedido no
    # botão vale a qualquer hora: o preparo que começa logo depois dele aparece à parte.
    import robo_shopee_video as robo
    import registro_processos
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_pausado": False, "robo_interacoes_inicio": 9,
                                         "robo_interacoes_fim": 11})
    dia = AGORA.strftime("%Y-%m-%d")

    def em(hora):
        return datetime.strptime(f"{dia} {hora}", "%Y-%m-%d %H:%M").replace(tzinfo=fuso_horario)

    registro_processos.registrar("shopee_video", robo.PROCESSO_DO_BOTAO, "pedido", ok=None, agora=em("09:20"))
    robo.registrar_tentativa("rascunho", "salvo", agora=em("09:31"))                # o pedido no botão
    robo.registrar_tentativa("rascunho", "pulado", agora=em("10:15"))               # do plano, antes do feed
    r = checkup.sobreposicoes(AGORA)
    assert [hora for hora, _o in r["pedidos_no_botao"]] == ["09:31"]
    assert [hora for hora, _o in r["preparo_na_janela"]] == ["10:15"]


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
    assert c["Espião"] == {"origens": 3, "com_video": 1, "sem_video": [2, 3], "pararam": [2]}
    assert c["Espelhador"]["sem_video"] == [1] and c["Espelhador"]["pararam"] == []
    pontos = checkup.pontos_de_atencao([], {}, {}, {"ativo": False, "vencidos": 0, "salvos": 0, "ruins": []},
                                       {}, ("x", 1.0, 1), AGORA, {}, {}, None, c, None)
    assert pontos == ["Espião: pararam de mandar vídeo (tinham nos 2 dias antes): nº 2 da lista do painel"]


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
    r = checkup.interacoes_da_shopee_video(AGORA)
    assert r["respostas"] == {"respondido": 1, "resposta no lugar errado": 1, "já respondido": 1, "sem resposta": 1}
    assert r["duplicadas"] == 1 and r["rodou_hoje"] and r["feed_hoje"] == 4 and r["feed_repetidos"] == 1
    assert r["feed_horas"] == ["17:20", "18:20", "19:20", "20:20"]
    assert (r["leituras_hoje"], r["leituras_esperadas"]) == (1, 3)           # só a das 12h (P70)
    robo_sv = {"ativo": True, "vencidos": 0, "salvos": 0, "ruins": []}
    texto = "\n".join(checkup.pontos_de_atencao([], {}, {}, robo_sv, {}, ("x", 1.0, 1), AGORA, interacoes=r))
    for trecho in ("não ficaram embaixo do comentário certo", "ficaram sem resposta depois de 3 tentativas",
                   "com mais de uma resposta do perfil", "4 comentários hoje (o combinado é 3)",
                   "as Notificações foram lidas 1 de 3 vezes hoje",
                   "comentado(s) mais de uma vez em 3 dias"):
        assert trecho in texto
    # A meta do dia: sem as Notificações lidas e com menos de 3 no feed, à noite, cobra.
    vazio = {"respostas": {}, "duplicadas": 0, "rodou_hoje": False, "feed_hoje": 1, "feed_repetidos": 0}
    texto = "\n".join(checkup.pontos_de_atencao([], {}, {}, robo_sv, {}, ("x", 1.0, 1), AGORA, interacoes=vazio))
    assert "as Notificações não foram lidas hoje" in texto and "1 de 3 comentários hoje" in texto
    pausado = dict(robo_sv, ativo=False)
    assert checkup.pontos_de_atencao([], {}, {}, pausado, {}, ("x", 1.0, 1), AGORA, interacoes=vazio) == []


def test_leituras_das_notificacoes_contam_as_vezes_do_dia():
    # Escolha do Rafael (P70): as Notificações às 12h, às 17h e no começo do Horário das Interações.
    import registro_processos
    import robo_shopee_video as robo
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_interacoes_inicio": 20, "robo_interacoes_fim": 21})
    dia = AGORA.strftime("%Y-%m-%d")

    def em(hora):
        return datetime.strptime(f"{dia} {hora}", "%Y-%m-%d %H:%M").replace(tzinfo=fuso_horario)

    def leu(hora):
        registro_processos.registrar("shopee_video", "notificações (respostas)", "topo achado", ok=True, agora=em(hora))

    assert checkup.leituras_das_notificacoes(em("12:30")) == (0, 0)           # a vez das 12h ainda pode sair
    leu("12:10")
    leu("12:25")                                                                # a continuação, na mesma vez
    assert checkup.leituras_das_notificacoes(em("12:30")) == (1, 1)
    assert checkup.leituras_das_notificacoes(em("18:00")) == (1, 2)           # a das 17h faltou
    leu("18:40")                                                                # atrasada, ainda na vez das 17h
    assert checkup.leituras_das_notificacoes(em("22:20")) == (2, 3)
    leu("20:05")
    assert checkup.leituras_das_notificacoes(em("22:20")) == (3, 3)
    # A vez que cai toda fora do horário em que o robô roda não é cobrada.
    db.salvar_config(robo.CHAVE_CONFIG, {"robo_inicio": 8, "robo_fim": 12})
    assert checkup.leituras_das_notificacoes(em("10:00").replace(day=AGORA.day + 1)) == (0, 0)
    assert checkup.leituras_das_notificacoes(em("23:00").replace(day=AGORA.day + 1)) == (0, 0)


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

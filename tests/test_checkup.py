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
    assert robo.PADRAO["robo_pausado"] is True


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

    r = checkup.robo_da_shopee_video(AGORA)
    assert (r["ativo"], r["horarios"], r["vencidos"], r["salvos"], r["pulados"]) == (True, 3, 2, 1, 1)
    assert r["ruins"] == [("rascunho", "parou", "navegar no app", 1)]
    assert "Fone X" not in str(r)


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
    assert "2 rastro(s) de erro no log (mais comum: ValueError em downloader_bot.py:9 (f), 2x)" in texto
    assert "Viral: 2 item(ns) atrasado(s)" in texto and "Viral: nenhum post hoje" in texto
    assert "Autorais: nenhum post" not in texto      # média baixa não cobra
    assert "2 horário(s) vencido(s)" in texto and "navegar no app" in texto
    assert "Baixador: 4 falha(s)" in texto and "Backup: nenhum" in texto
    assert checkup.pontos_de_atencao([], {}, {}, {"ativo": False, "vencidos": 3, "salvos": 0, "ruins": []},
                                     {}, ("x", 5.0, 1), AGORA) == []


def test_saida_completa_sem_dado_privado(monkeypatch, capsys):
    _filas_de_teste()
    _erro(1, "buscador_produtos (produto secreto): falhou")
    monkeypatch.setattr(checkup, "ler_journal", lambda servico: [
        "2026-10-23 10:00:00.123 -0300 - ❌ [Métricas] Falha na coleta diária: conteúdo secreto"])
    monkeypatch.setattr(checkup.backup_dados, "ultimo_backup", lambda: None)
    checkup.main()
    saida = capsys.readouterr().out
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
    assert ("incentivo", 3, 2, "a mais") in principal["fora_do_previsto"]
    assert ("link_grupo", 1, 3, "a menos") in principal["fora_do_previsto"]
    assert r["Grupo Público"]["fora_do_previsto"] == []
    assert r["Viral"]["fora_do_previsto"] == [] and r["Viral"]["pausado"]   # pausado não cobra "a menos"
    pontos = checkup.pontos_de_atencao([], {}, {}, {"ativo": False, "vencidos": 0, "salvos": 0, "ruins": []},
                                       {}, ("x", 1.0, 1), AGORA, {}, r, None)
    assert "Rotinas do canal principal: 1 intervalo(s) abaixo de 10 min (menor: 5 min)" in pontos
    assert "Rotinas do canal principal: 1 vez(es) o mesmo assunto em seguida" in pontos


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

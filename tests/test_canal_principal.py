"""Canal principal e Grupo Público: pausa, novas tentativas, Publicar Agora, saldo, limpeza."""
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
    for _ in range(4):
        if status("r2") == "PENDENTE":
            rodar(bm.executar_postagem_fila("r2"))
    assert status("r2") == "ERRO"


def test_fim_da_pausa_no_meio_do_dia_volta_no_mesmo_dia(bm, telegram, monkeypatch):
    agora = datetime.now(bm.fuso_horario)
    if not 10 <= agora.hour < 20:
        pytest.skip("cenário montado para o meio do dia (Bom Dia já passou, Boa Noite ainda não)")
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
    bm.salvar_config_bd("saldo_caixa_shopee", 100.0)
    bm.processar_e_salvar_pedidos_api([{
        "purchaseTime": 1788000000, "totalCommission": str(comissao), "shopeeCommissionCapped": str(comissao),
        "sellerCommission": "0", "orders": [{"orderId": "A1", "orderStatus": status_novo}]}])
    assert bm.ler_config_bd("saldo_caixa_shopee", 0.0) == pytest.approx(esperado)


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
    open("temp/baixando.mp4", "wb").write(b"x")
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

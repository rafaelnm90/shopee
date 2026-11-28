"""Espião e canal Viral: retentativa da IA, trava de silêncio, intercalação e alerta."""
import os
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from conftest import consultar, rodar

FMT = "%Y-%m-%d %H:%M:%S"


@pytest.fixture
def espiao(bm, monkeypatch):
    """Destino configurado, janela de 24 h e Telegram/IA falsos."""
    d = bm.ler_alvos_espiao()
    d.update({"canal_destino": "-100999", "inicio": 0, "fim": 24})
    bm.salvar_alvos_espiao(d)
    estado = SimpleNamespace(enviados=[], chamadas_ia=0)

    async def send_video(chat_id=None, video=None, caption=None, parse_mode=None):
        estado.enviados.append(caption)
        return SimpleNamespace(message_id=9)

    async def ia(*a, **k):
        estado.chamadas_ia += 1
        return None

    async def converter(link, *a, **k):
        return link + "?afiliado"

    async def sem_espera(*a, **k):
        pass
    monkeypatch.setattr(bm.bot, "send_video", send_video)
    monkeypatch.setattr(bm, "analisar_video_gemini", ia)
    monkeypatch.setattr(bm, "converter_link_shopee", converter)
    monkeypatch.setattr(bm.asyncio, "sleep", sem_espera)
    return estado


def item_da_fila(bm, id_):
    return next(x for x in bm.ler_fila_clonagem()["fila"] if x["id"] == id_)


def test_retentativa_da_ia_marca_o_clone_certo(bm, espiao):
    agora = datetime.now(bm.fuso_horario)
    vencido = (agora - timedelta(minutes=5)).strftime(FMT)
    open("temp/b.mp4", "wb").write(b"v")
    # A saiu hoje: postado num dia anterior, a faxina da fila o tiraria (à 00:00 "5 min atrás" é ontem).
    bm.salvar_fila_clonagem({"fila": [
        {"id": "A", "processado": True, "data_postagem": agora.strftime("%Y-%m-%d"), "horario_disparo": vencido,
         "caminho_video": "x", "link_original": "l", "data_captura": vencido},
        {"id": "B", "processado": False, "horario_disparo": vencido, "caminho_video": "temp/b.mp4",
         "link_original": "https://s.shopee.com.br/b", "data_captura": vencido},
    ]})
    for _ in range(4):
        rodar(bm.processar_fila_espiao())
    assert espiao.chamadas_ia == 1
    assert item_da_fila(bm, "B")["tentativas_ia"] == 1 and "tentativas_ia" not in item_da_fila(bm, "A")

    for _ in range(3):                                    # três janelas de 30 min
        dados = bm.ler_fila_clonagem()
        for x in dados["fila"]:
            if x["id"] == "B" and not x.get("processado"):
                x["horario_disparo"] = vencido
        bm.salvar_fila_clonagem(dados)
        rodar(bm.processar_fila_espiao())
    assert item_da_fila(bm, "B")["processado"] is True
    assert espiao.enviados[-1] == "https://s.shopee.com.br/b?afiliado"


def test_clone_que_falha_por_rede_volta_para_a_fila(bm, espiao, monkeypatch):
    # 28/10, deploy das 20:12: o aiogram fecha a conexão do bot ao desligar, o envio do clone
    # caiu com TelegramNetworkError, e o clone ficou como processado sem ter saído.
    from aiogram.exceptions import TelegramNetworkError
    agora = datetime.now(bm.fuso_horario)
    vencido = (agora - timedelta(minutes=5)).strftime(FMT)
    open("temp/d.mp4", "wb").write(b"v")
    bm.salvar_fila_clonagem({"fila": [
        {"id": "D", "processado": False, "horario_disparo": vencido, "caminho_video": "temp/d.mp4",
         "link_original": "https://s.shopee.com.br/d", "legenda_ia": "Produto\n#Casa", "data_captura": vencido}]})

    async def sem_rede(**k):
        raise TelegramNetworkError(method=None, message="ClientConnectionError: Connector is closed.")

    monkeypatch.setattr(bm.bot, "send_video", sem_rede)
    rodar(bm.processar_fila_espiao())
    item = item_da_fila(bm, "D")
    assert not item["processado"] and item["falhas_de_rede"] == 1 and item["horario_disparo"] > vencido
    assert os.path.exists("temp/d.mp4")

    def de_novo():
        dados = bm.ler_fila_clonagem()
        dados["fila"][0]["horario_disparo"] = vencido
        bm.salvar_fila_clonagem(dados)
        rodar(bm.processar_fila_espiao())

    # 20/11, de madrugada: a rede até o Telegram ficou fora mais de meia hora, e 2 clones se
    # perderam na 3ª falha. O clone espera a rede por até 1 h, de 10 em 10 min.
    for _ in range(2):
        de_novo()
    item = item_da_fila(bm, "D")
    assert not item["processado"] and item["falhas_de_rede"] == 3
    assert (bm.MAX_FALHAS_DE_REDE_DO_CLONE - 1) * bm.ESPERA_DA_REDE_DO_CLONE_MIN >= 60
    # Na última falha de rede, fica de lado como as outras falhas.
    for _ in range(bm.MAX_FALHAS_DE_REDE_DO_CLONE - 3):
        de_novo()
    assert item_da_fila(bm, "D")["processado"] is True


def test_clone_acima_do_limite_do_telegram_fica_de_lado_na_hora(bm, espiao, monkeypatch):
    # Checkup de 27/11: um clone acima do limite da Bot API (TelegramEntityTooLarge, que o aiogram põe entre os
    # erros de rede) foi mandado 7 vezes, de 10 em 10 min, como se a rede tivesse caído. Ele nunca passa: fica de
    # lado na 1ª vez, como as outras falhas.
    from aiogram.exceptions import TelegramEntityTooLarge
    agora = datetime.now(bm.fuso_horario)
    vencido = (agora - timedelta(minutes=5)).strftime(FMT)
    open("temp/g.mp4", "wb").write(b"v")
    bm.salvar_fila_clonagem({"fila": [
        {"id": "G", "processado": False, "horario_disparo": vencido, "caminho_video": "temp/g.mp4",
         "link_original": "https://s.shopee.com.br/g", "legenda_ia": "Produto\n#Casa", "data_captura": vencido}]})
    envios = []

    async def grande_demais(**k):
        envios.append(1)
        raise TelegramEntityTooLarge(method=None, message="Request Entity Too Large")

    monkeypatch.setattr(bm.bot, "send_video", grande_demais)
    rodar(bm.processar_fila_espiao())
    item = item_da_fila(bm, "G")
    assert item["processado"] is True and not item.get("falhas_de_rede") and len(envios) == 1
    assert bm.falha_de_rede(TelegramEntityTooLarge(method=None, message="x")) is False
    # Não é erro do código: fica no registro como de fora, sem o "falhou".
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = 'postagem Viral'") == (
        "de fora - acima do limite do Telegram", None)


def test_clone_acima_de_50_mb_fica_de_fora_antes_da_ia(bm, espiao, monkeypatch):
    # Checkup de 27/11: o clone acima do teto da Bot API foi analisado pela IA e mandado ao Telegram, que o recusou
    # ("Falha ao postar clone"). O arquivo acima dos LIMITE_UPLOAD_BOT_MB fica de fora antes da IA e do envio, como
    # na fila do Público.
    agora = datetime.now(bm.fuso_horario)
    vencido = (agora - timedelta(minutes=5)).strftime(FMT)
    open("temp/h.mp4", "wb").write(b"v" * 2048)
    bm.salvar_fila_clonagem({"fila": [
        {"id": "H", "processado": False, "horario_disparo": vencido, "caminho_video": "temp/h.mp4",
         "link_original": "https://s.shopee.com.br/h", "data_captura": vencido}]})
    monkeypatch.setattr(bm, "LIMITE_UPLOAD_BOT_MB", 0.001)          # 1 KB: o arquivo de 2 KB passa do teto
    rodar(bm.processar_fila_espiao())
    assert item_da_fila(bm, "H")["processado"] is True
    assert espiao.chamadas_ia == 0 and espiao.enviados == []
    assert not os.path.exists("temp/h.mp4") and os.path.exists("temp/h.mp4.pendente")
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = 'postagem Viral'") == (
        "de fora - acima de 0.001 MB", None)


@pytest.mark.parametrize("rotina, segura", [
    ("promo_achadinhos_viral", True),
    ("promo_publico_viral", True),
    ("promo_principal", True),
    ("promo_principal_publico", False),               # rotina do Grupo Público
])
def test_trava_de_silencio_so_nas_rotinas_do_viral(bm, espiao, rotina, segura):
    async def noop():
        pass

    async def cenario():
        bm.scheduler.start()
        agora = datetime.now(bm.fuso_horario)
        open("temp/c.mp4", "wb").write(b"v")
        bm.salvar_fila_clonagem({"fila": [{
            "id": "C", "processado": False, "horario_disparo": (agora - timedelta(minutes=1)).strftime(FMT),
            "caminho_video": "temp/c.mp4", "link_original": "l", "legenda_ia": "Produto\n#Casa",
            "data_captura": (agora - timedelta(days=1)).strftime(FMT)}]})
        bm.scheduler.add_job(noop, 'date', run_date=agora + timedelta(minutes=1), id=f"job_rotina_{rotina}_0")
        await bm.processar_fila_espiao()
        bm.scheduler.shutdown(wait=False)
    rodar(cenario())
    assert (not espiao.enviados) == segura


def test_intercalacao_do_viral_conta_so_os_clones_de_hoje(bm):
    d = bm.ler_alvos_espiao()
    d["canal_destino"] = str(bm.GRUPO_VIRAL_ID)
    bm.salvar_alvos_espiao(d)
    agora = datetime.now(bm.fuso_horario)
    amanha = (agora + timedelta(days=1)).strftime(FMT)
    bm.salvar_fila_clonagem({"fila": [{"id": "a", "processado": False, "horario_disparo": amanha},
                                      {"id": "b", "processado": False, "horario_disparo": ""}]})
    assert bm.contar_videos_pendentes(bm.GRUPO_VIRAL_ID) == 0
    # Ainda hoje, mais tarde: "daqui a 20 min" às 23:59 já é amanhã.
    bm.salvar_fila_clonagem({"fila": [{"id": "c", "processado": False,
                                       "horario_disparo": agora.replace(hour=23, minute=59, second=59).strftime(FMT)}]})
    assert bm.contar_videos_pendentes(bm.GRUPO_VIRAL_ID) == 1


def test_alerta_sem_publicacao_ignora_clones_de_amanha(bm, monkeypatch):
    agora = datetime.now(bm.fuso_horario)
    amanha = (agora + timedelta(days=1)).replace(hour=11).strftime(FMT)
    bm.salvar_fila_clonagem({"fila": [{"id": f"c{i}", "processado": False, "horario_disparo": amanha}
                                      for i in range(8)]})
    alertas = []

    async def send_message(chat, texto, **k):
        alertas.append(texto)
    monkeypatch.setattr(bm.bot, "send_message", send_message)

    class Relogio(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz).replace(hour=15)
    monkeypatch.setattr(bm, "datetime", Relogio)
    rodar(bm.monitor_saude())
    assert not any("Nenhuma publicação" in a for a in alertas)


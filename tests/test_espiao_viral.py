"""Espião e canal Viral: retentativa da IA, trava de silêncio, intercalação e alerta."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from conftest import rodar

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
    vencido = (datetime.now(bm.fuso_horario) - timedelta(minutes=5)).strftime(FMT)
    open("temp/b.mp4", "wb").write(b"v")
    bm.salvar_fila_clonagem({"fila": [
        {"id": "A", "processado": True, "data_postagem": vencido[:10], "horario_disparo": vencido,
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
    bm.salvar_fila_clonagem({"fila": [{"id": "c", "processado": False,
                                       "horario_disparo": (agora + timedelta(minutes=20)).strftime(FMT)}]})
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

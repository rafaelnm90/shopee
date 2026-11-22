"""A foto das métricas do dia (bot_mestre, 23:50): o dia que ficou sem ela porque o bot estava fora do ar ganha a foto
na subida seguinte, com a data dele, e o acervo acumulado não zera por um dia sem a foto."""
from datetime import datetime, timedelta

import db
from conftest import consultar, rodar
from fuso import fuso_horario


def _hoje(delta=0):
    return (datetime.now(fuso_horario) + timedelta(days=delta)).strftime("%Y-%m-%d")


def _sem_o_telegram(bm, monkeypatch):
    async def membros(chat_id):
        return 100
    monkeypatch.setattr(bm.bot, "get_chat_member_count", membros)


def test_dia_sem_a_foto_ganha_a_foto_na_subida(bm, relogio, monkeypatch):
    # 21/11: o deploy reiniciou o bot às 23:49, e a foto das 23:50 não saiu ("métricas do dia: rodou 0 vez(es)").
    relogio("10:40")
    _sem_o_telegram(bm, monkeypatch)
    anteontem, ontem = _hoje(-2), _hoje(-1)
    bm.salvar_metrica(anteontem, "posts_total_principal", 50)
    assert bm.dia_sem_a_foto() == ontem
    rodar(bm.tirar_a_foto_que_faltou())
    with db.conexao() as conexao:
        linhas = dict(conexao.execute("SELECT chave, valor FROM historico_metricas WHERE data = ?",
                                      (ontem,)).fetchall())
    assert linhas["membros_principal"] == 100 and linhas["posts_total_principal"] == 50
    # Com a foto de ontem, a subida não tira outra.
    assert bm.dia_sem_a_foto() is None


def test_depois_das_23_50_a_foto_que_falta_e_a_de_hoje(bm, relogio, monkeypatch):
    relogio("23:55")
    _sem_o_telegram(bm, monkeypatch)
    assert bm.dia_sem_a_foto() == _hoje()
    rodar(bm.tirar_a_foto_que_faltou())
    assert consultar("SELECT COUNT(*) FROM historico_metricas WHERE data = ?", _hoje())[0] > 0
    assert bm.dia_sem_a_foto() is None


def test_acervo_acumulado_nao_zera_com_um_dia_sem_a_foto(bm, relogio, monkeypatch):
    # O total de hoje soma ao do último dia com a foto, mesmo com o dia de ontem sem ela.
    relogio("23:50")
    _sem_o_telegram(bm, monkeypatch)
    bm.salvar_metrica(_hoje(-2), "posts_total_viral", 700)
    rodar(bm.coletar_metricas_diarias())
    assert consultar("SELECT valor FROM historico_metricas WHERE data = ? AND chave = 'posts_total_viral'",
                     _hoje())[0] == 700


def test_a_foto_que_faltou_e_conferida_na_subida(bm):
    import inspect
    assert "tirar_a_foto_que_faltou" in inspect.getsource(bm.main)

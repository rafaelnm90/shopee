"""rotinas.py e as rotinas de texto do bot_mestre: só as que o código conhece são agendadas e disparadas."""
import inspect
from datetime import datetime

import pytest

import rotinas
from conftest import rodar

ANTIGA = "rotina_antiga_publico"


def test_toda_rotina_conhecida_tem_texto_no_codigo(bm):
    codigo = inspect.getsource(bm.disparar_mensagem)
    for tipo in rotinas.ROTINAS_PRINCIPAIS + rotinas.ROTINAS_VIRAIS + rotinas.ROTINAS_PUBLICO:
        assert f'"{tipo}"' in codigo, tipo
    assert rotinas.conhecida("campanha_pub_0_11.11") and not rotinas.conhecida(ANTIGA)


def _config(bm, hoje):
    r = bm.ler_config_rotina()
    r.update({"pausado": False, "ultimo_bom_dia": hoje, "hora_ultimo_bom_dia": "06:00",
              "historico_diario": {"data": hoje, "contagem": {}},
              "incentivo": {"inicio": 8, "fim": 20, "frequencia": 2},
              ANTIGA: {"inicio": 8, "fim": 20, "frequencia": 5}})
    bm.salvar_config_rotina(r)


def test_chave_antiga_do_banco_nao_quebra_nem_entra_no_historico(bm, relogio, monkeypatch):
    relogio("15:00")
    hoje = datetime.now(bm.fuso_horario).strftime("%Y-%m-%d")
    _config(bm, hoje)

    async def gerar(prompt):
        pytest.fail("não devia pedir texto à IA")
    monkeypatch.setattr(bm, "gerar_mensagem_gemini", gerar)
    rodar(bm.disparar_mensagem(ANTIGA))
    assert ANTIGA not in bm.ler_config_rotina()["historico_diario"]["contagem"]
    linhas = bm.registro_processos.contagem("2000-01-01 00:00:00")
    assert any(l[2] == "ignorada (rotina sem texto no código)" and l[4] == 0 for l in linhas)


def test_chave_antiga_do_banco_nao_ganha_horario(bm, relogio):
    relogio("10:00")
    hoje = datetime.now(bm.fuso_horario).strftime("%Y-%m-%d")
    _config(bm, hoje)

    async def cenario():
        bm.scheduler.start()
        try:
            bm.agendar_tarefas_diarias("principal")
            return [job.id for job in bm.scheduler.get_jobs()]
        finally:
            bm.scheduler.shutdown(wait=False)
    ids = rodar(cenario())
    assert any(i.startswith("job_rotina_incentivo_") for i in ids)
    assert not any(ANTIGA in i for i in ids)

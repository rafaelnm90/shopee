"""
Testes do Motor de Filas — o coração da distribuição de todos os robôs.

⚠️ O RELÓGIO É FIXADO em cada teste. Sem isso, o mesmo teste passa de manhã
e falha à noite, porque o motor distribui no tempo que RESTA do dia.

Rodar:  python3 -m pytest test_motor_filas.py -v
"""
from unittest.mock import patch
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import motor_filas

FUSO = ZoneInfo("America/Sao_Paulo")

CFG_ESPIAO = {"inicio": 0, "fim": 24, "modo": "aleatorio", "intervalo_dias": 1,
              "espacamento_base_min": 10, "espacamento_variacao_min": 5, "limite_dias_descarte": 5}
CFG_PUBLICO = {"inicio": 10, "fim": 20, "modo": "aleatorio", "intervalo_dias": 1,
               "espacamento_base_min": 15, "espacamento_variacao_min": 6, "limite_dias_descarte": 5}

def distribuir(qtd, cfg, hora=0, captura="2026-08-19 06:00:00", forcar=False, ocupados=None):
    """Roda o motor com o relógio travado às 'hora' do dia 20/08."""
    congelado = datetime(2026, 8, 20, hora, 1, tzinfo=FUSO)
    class RelogioFixo(datetime):
        @classmethod
        def now(cls, tz=None): return congelado
    c = dict(cfg)
    if ocupados: c["horarios_ocupados"] = ocupados
    itens = [{"id_unico": f"v{i}", "data_captura": captura, "horario_disparo": ""} for i in range(qtd)]
    with patch.object(motor_filas, "datetime", RelogioFixo):
        motor_filas.calcular_horarios_distribuicao(itens, c, forcar=forcar)
    return itens

def horarios(itens):
    return sorted(i["horario_disparo"] for i in itens if i.get("horario_disparo"))

def gaps(h):
    return [(datetime.strptime(h[i+1], "%Y-%m-%d %H:%M:%S") -
             datetime.strptime(h[i], "%Y-%m-%d %H:%M:%S")).total_seconds()/60
            for i in range(len(h)-1)]

# ── DISTRIBUIÇÃO ───────────────────────────────────────────────
def test_todos_recebem_horario():
    itens = distribuir(20, CFG_ESPIAO)
    assert all(i["horario_disparo"] for i in itens)

def test_horarios_sao_unicos():
    """Dois vídeos no mesmo segundo = rajada. Foi o bug do flood de 17/08."""
    h = horarios(distribuir(50, CFG_ESPIAO))
    assert len(h) == len(set(h))

def test_poucos_videos_ocupam_o_dia():
    """Agendando à 00h, 5 vídeos devem se espalhar — não terminar de madrugada."""
    h = horarios(distribuir(5, CFG_ESPIAO, hora=0))
    span = (datetime.strptime(h[-1], "%Y-%m-%d %H:%M:%S") -
            datetime.strptime(h[0], "%Y-%m-%d %H:%M:%S")).total_seconds()/3600
    assert span > 10, f"5 vídeos em apenas {span:.1f}h"

def test_muitos_videos_nao_estouram_o_piso():
    h = horarios(distribuir(300, CFG_ESPIAO, hora=0))
    primeiro_dia = [x for x in h if x[:10] == h[0][:10]]
    assert min(gaps(primeiro_dia)) >= 4.5

def test_intervalo_nao_e_fixo():
    """Ritmo metronômico denuncia automação."""
    g = [round(x) for x in gaps(horarios(distribuir(30, CFG_ESPIAO, hora=0))) if x < 600]
    assert len(set(g)) > 3, f"intervalos pouco variados: {sorted(set(g))}"

def test_espacamento_cresce_quando_ha_poucos():
    """5 vídeos devem ter intervalo MUITO maior que 100."""
    g5 = gaps(horarios(distribuir(5, CFG_ESPIAO, hora=0)))
    g100 = gaps(horarios(distribuir(100, CFG_ESPIAO, hora=0)))
    assert min(g5) > max(g100)

# ── JANELA ─────────────────────────────────────────────────────
def test_respeita_janela_restrita():
    for x in horarios(distribuir(20, CFG_PUBLICO, hora=0)):
        assert 10 <= int(x[11:13]) < 20, f"{x} fora da janela 10h-20h"

def test_fim_do_dia_comprime_e_esta_correto():
    """Rodando às 22h sobra pouco: comprimir é o certo, pois vencem hoje."""
    h = horarios(distribuir(5, CFG_ESPIAO, hora=22))
    assert h[0][:10] == "2026-08-20"
    assert min(gaps(h)) >= 4.5

# ── TRANSBORDO ─────────────────────────────────────────────────
def test_transborda_quando_nao_cabe():
    assert len(set(x[:10] for x in horarios(distribuir(300, CFG_ESPIAO, hora=0)))) > 1

def test_transbordo_nao_pula_dia():
    dias = sorted(set(x[:10] for x in horarios(distribuir(300, CFG_ESPIAO, hora=0))))
    for a, b in zip(dias, dias[1:]):
        assert (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days == 1

def test_transbordo_mantem_espacamento():
    h = horarios(distribuir(300, CFG_ESPIAO, hora=0))
    dias = sorted(set(x[:10] for x in h))
    d2 = [x for x in h if x[:10] == dias[1]]
    assert min(gaps(d2)) >= 4.5

# ── ESTEIRA CONTÍNUA ───────────────────────────────────────────
def test_nao_colide_com_ja_agendados():
    l1 = distribuir(40, CFG_ESPIAO, hora=0)
    ocup = horarios(l1)
    l2 = distribuir(40, CFG_ESPIAO, hora=0, ocupados=ocup)
    todos = sorted(ocup + horarios(l2))
    assert min(gaps(todos)) >= 4.5, "lotes se sobrepondo"

# ── DESCARTE ───────────────────────────────────────────────────
def test_descarta_video_muito_antigo():
    itens = distribuir(200, CFG_ESPIAO, hora=0, captura="2026-07-01 06:00:00")
    assert any(i.get("descartar_por_idade") for i in itens)

def test_nao_descarta_video_recente():
    itens = distribuir(20, CFG_ESPIAO, hora=0, captura="2026-08-19 06:00:00")
    assert not any(i.get("descartar_por_idade") for i in itens)

# ── ROBUSTEZ ───────────────────────────────────────────────────
def test_lista_vazia_nao_quebra():
    assert motor_filas.calcular_horarios_distribuicao([], dict(CFG_ESPIAO)) == []

def test_um_item_so():
    assert distribuir(1, CFG_ESPIAO)[0]["horario_disparo"]

def test_fila_sem_piso_usa_motor_antigo():
    """Filas que não configuram piso não podem quebrar."""
    itens = distribuir(10, {"inicio": 10, "fim": 20, "modo": "ordem", "intervalo_dias": 1})
    assert all(i["horario_disparo"] for i in itens)

def test_descarga_forcada_e_rapida():
    g = gaps(horarios(distribuir(10, CFG_ESPIAO, forcar=True)))
    assert max(g) < 5

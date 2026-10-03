"""Espelhador: o histórico do que já saiu fica só DIAS_HISTORICO_ESPELHADOR dias na fila."""
import motor_userbot as mu


def test_poda_so_publicado_antigo():
    fila = [
        {"id": "hoje", "processado": True, "data_postagem": "2026-10-03"},
        {"id": "3_dias", "processado": True, "data_postagem": "2026-09-30"},
        {"id": "4_dias", "processado": True, "data_postagem": "2026-09-29"},
        {"id": "setembro", "processado": True, "data_postagem": "2026-09-14"},
        {"id": "pendente_antigo", "processado": False, "data_captura": "2026-09-01 10:00:00"},
        {"id": "publicado_sem_data", "processado": True},
    ]
    mantidos = [i["id"] for i in mu.podar_historico(fila, "2026-10-03")]
    assert mantidos == ["hoje", "3_dias", "pendente_antigo", "publicado_sem_data"]

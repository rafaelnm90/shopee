"""downloader_bot: quando o aviso de canais obrigatórios expira, o link da pessoa sai junto."""

import downloader_bot as dl
from conftest import rodar


class Mensagem:
    def __init__(self, message_id):
        self.message_id = message_id
        self.apagada = False

    async def delete(self):
        self.apagada = True


def test_aviso_de_trava_expirado_leva_o_link_junto(monkeypatch):
    async def sem_espera(_segundos):
        return None

    monkeypatch.setattr(dl.asyncio, "sleep", sem_espera)
    aviso, link = Mensagem(10), Mensagem(9)
    monkeypatch.setitem(dl.GATES_ABERTOS, 555, aviso)
    monkeypatch.setitem(dl.LINKS_PENDENTES, 555, link)

    rodar(dl.expirar_aviso_trava(555, 10))
    assert aviso.apagada and link.apagada
    assert 555 not in dl.GATES_ABERTOS and 555 not in dl.LINKS_PENDENTES


def test_aviso_trocado_por_outro_nao_mexe_em_nada(monkeypatch):
    async def sem_espera(_segundos):
        return None

    monkeypatch.setattr(dl.asyncio, "sleep", sem_espera)
    novo, link = Mensagem(20), Mensagem(19)
    monkeypatch.setitem(dl.GATES_ABERTOS, 555, novo)
    monkeypatch.setitem(dl.LINKS_PENDENTES, 555, link)

    rodar(dl.expirar_aviso_trava(555, 10))                    # o aviso 10 já foi substituído
    assert not novo.apagada and not link.apagada
    assert dl.LINKS_PENDENTES[555] is link


def test_sem_link_guardado_so_apaga_o_aviso(monkeypatch):
    async def sem_espera(_segundos):
        return None

    monkeypatch.setattr(dl.asyncio, "sleep", sem_espera)
    aviso = Mensagem(30)
    monkeypatch.setitem(dl.GATES_ABERTOS, 777, aviso)
    rodar(dl.expirar_aviso_trava(777, 30))
    assert aviso.apagada and 777 not in dl.GATES_ABERTOS

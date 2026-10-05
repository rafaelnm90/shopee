"""Botão Tela do Android 📱 (Opções do Servidor): abre a tela pelo android_virtual e diz onde parou se falhar."""
import asyncio

from conftest import rodar

SAIDA_FALHA = """== Tela no navegador
android: desligado; rode o preparar antes
== Android virtual (Shopee Vídeo)
docker: instalado | adb: instalado | binder: carregado
"""


def test_botao_esta_nas_opcoes_do_servidor(bm):
    textos = [b.text for linha in bm.obter_teclado_opcoes_servidor().keyboard for b in linha]
    assert "Tela do Android 📱" in textos


def test_abre_a_tela_e_avisa_que_o_link_chegou(bm, Msg, Est, monkeypatch):
    async def abrir():
        return True, ""

    monkeypatch.setattr(bm, "abrir_tela_android", abrir)
    msg = Msg("Tela do Android 📱")
    rodar(bm.tela_android_handler(msg, Est()))
    assert "Abrindo a tela do Android" in msg.saidas[0]
    assert "aberta" in msg.saidas[-1] and "link" in msg.saidas[-1]
    assert bm._tela_android["abrindo"] is False


def test_falha_mostra_onde_parou(bm, Msg, Est, monkeypatch):
    async def abrir():
        return False, bm.motivo_da_tela(SAIDA_FALHA)

    monkeypatch.setattr(bm, "abrir_tela_android", abrir)
    msg = Msg("Tela do Android 📱")
    rodar(bm.tela_android_handler(msg, Est()))
    assert "não abriu: android: desligado; rode o preparar antes" in msg.saidas[-1]
    assert bm._tela_android["abrindo"] is False


def test_erro_inesperado_nao_trava_o_botao(bm, Msg, Est, monkeypatch):
    async def abrir():
        raise OSError("sem python")

    monkeypatch.setattr(bm, "abrir_tela_android", abrir)
    msg = Msg("Tela do Android 📱")
    rodar(bm.tela_android_handler(msg, Est()))
    assert "não abriu: OSError" in msg.saidas[-1]
    assert bm._tela_android["abrindo"] is False


def test_dois_toques_seguidos_abrem_uma_tela_so(bm, Msg, Est, monkeypatch):
    chamadas = []

    async def abrir():
        chamadas.append(1)
        await asyncio.sleep(0.05)
        return True, ""

    async def cenario():
        monkeypatch.setattr(bm, "abrir_tela_android", abrir)
        primeira, segunda = Msg("Tela do Android 📱"), Msg("Tela do Android 📱")
        await asyncio.gather(bm.tela_android_handler(primeira, Est()), bm.tela_android_handler(segunda, Est()))
        return segunda.saidas

    saidas = rodar(cenario())
    assert chamadas == [1] and "Já estou abrindo" in saidas[0]


def test_so_o_admin_abre(bm, Msg, Est, monkeypatch):
    async def abrir():
        raise AssertionError("não devia abrir")

    monkeypatch.setattr(bm, "abrir_tela_android", abrir)
    msg = Msg("Tela do Android 📱", user_id=123)
    rodar(bm.tela_android_handler(msg, Est()))
    assert msg.saidas == []


def test_roda_o_android_virtual_com_a_tela(bm, monkeypatch):
    pedidos = []

    class Proc:
        def __init__(self, codigo, saida):
            self.returncode, self._saida = codigo, saida

        async def communicate(self):
            return self._saida, None

    respostas = [Proc(0, b"== Tela no navegador\ntela: aberta\n"), Proc(1, SAIDA_FALHA.encode())]

    async def criar(*partes, **kw):
        pedidos.append(partes)
        return respostas.pop(0)

    monkeypatch.setattr(bm.asyncio, "create_subprocess_exec", criar)
    assert rodar(bm.abrir_tela_android()) == (True, "")
    assert rodar(bm.abrir_tela_android()) == (False, "android: desligado; rode o preparar antes")
    assert pedidos[0][0] == bm.sys.executable
    assert pedidos[0][1].endswith("android_virtual.py") and pedidos[0][2:] == ("--tela",)


def test_abertura_que_trava_e_cortada(bm, monkeypatch):
    class Proc:
        returncode = None
        morto = False

        async def communicate(self):
            await asyncio.sleep(10)

        def kill(self):
            Proc.morto = True

    async def criar(*partes, **kw):
        return Proc()

    monkeypatch.setattr(bm.asyncio, "create_subprocess_exec", criar)
    ok, motivo = rodar(bm.abrir_tela_android(timeout=0.01))
    assert not ok and "demorou demais" in motivo and Proc.morto


def test_motivo_sem_a_parte_da_tela(bm):
    assert bm.motivo_da_tela("") == "sem detalhes"

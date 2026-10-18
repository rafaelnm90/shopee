"""Celular do robô (Shopee Vídeo 🎬 → Celular do Robô 📱): achar na rede privada, parear pelo bot e conectar."""
import json

import pytest

from conftest import rodar

IP = "100.70.1.2"


def _textos(teclado):
    return [b.text for linha in teclado.keyboard for b in linha]


@pytest.fixture
def cr(monkeypatch):
    import celular_robo
    monkeypatch.setattr(celular_robo.shutil, "which", lambda nome: f"/usr/bin/{nome}")
    return celular_robo


def _rede(*pares):
    return json.dumps({"BackendState": "Running", "Peer": {
        str(i): {"HostName": nome, "OS": so, "Online": online, "TailscaleIPs": [ip, "fd7a::1"]}
        for i, (nome, so, online, ip) in enumerate(pares)}})


class AdbFalso:
    """Respostas do adb e do tailscale por comando; guarda o que foi pedido."""

    def __init__(self, rede, pair="Successfully paired to x [guid=adb-1]", connect="connected to x"):
        self.rede, self.pair, self.connect, self.pedidos = rede, pair, connect, []

    def __call__(self, *partes, timeout=0):
        self.pedidos.append(partes)
        if partes[0] == "tailscale":
            return 0, self.rede
        if partes[1] == "pair":
            return (0 if "Successfully" in self.pair else 1), self.pair
        if partes[1] == "connect":
            return 0, self.connect
        if "get-state" in partes:
            return 0, "device"
        prop = partes[-1]
        return 0, {"ro.product.manufacturer": "motorola", "ro.product.model": "moto g84 5G",
                   "ro.build.version.release": "14"}.get(prop, "")


@pytest.mark.parametrize("texto, esperado", [
    ("123456 37123", ("123456", 37123)), ("37123 123456", ("123456", 37123)),
    ("Código 123456\nIP e porta 192.168.0.5:37123", ("123456", 37123)),
    ("12345 37123", None), ("123456", None), ("123456 37123 41000", None), ("abc", None),
])
def test_codigo_e_porta_do_pareamento_em_qualquer_ordem(cr, texto, esperado):
    assert cr.interpretar_pareamento(texto) == esperado


@pytest.mark.parametrize("texto, esperado", [
    ("41235", 41235), ("192.168.0.5:41235", 41235), ("porta 41235", 41235), ("80", None), ("abc", None),
    ("41235 37123", None),
])
def test_porta_da_conexao(cr, texto, esperado):
    assert cr.interpretar_porta(texto) == esperado


def test_acha_so_os_android_da_rede_os_ligados_primeiro(cr, monkeypatch):
    rede = _rede(("servidor", "linux", True, "100.70.0.1"), ("moto-velho", "android", False, "100.70.9.9"),
                 ("moto-g84", "android", True, IP))
    monkeypatch.setattr(cr.av, "_rodar", AdbFalso(rede))
    assert cr.celulares_na_rede() == [{"nome": "moto-g84", "ip": IP, "online": True},
                                      {"nome": "moto-velho", "ip": "100.70.9.9", "online": False}]


def test_pareia_e_conecta_sem_guardar_o_codigo(cr, monkeypatch):
    adb = AdbFalso(_rede(("moto-g84", "android", True, IP)))
    monkeypatch.setattr(cr.av, "_rodar", adb)
    assert cr.parear(IP, 37123, "123456") == (True, "")
    assert ("adb", "pair", f"{IP}:37123", "123456") in adb.pedidos
    assert cr.conectar(IP, 41235) == (True, "motorola moto g84 5G, Android 14")
    assert cr.endereco() == f"{IP}:41235" and cr.conectado()
    assert "123456" not in json.dumps(cr.ler())                          # o código não fica no banco


def test_codigo_errado_explica_em_palavras_simples(cr, monkeypatch):
    adb = AdbFalso(_rede(), pair="Failed: Wrong password or connection was dropped.")
    monkeypatch.setattr(cr.av, "_rodar", adb)
    ok, motivo = cr.parear(IP, 37123, "000000")
    assert not ok and "código não confere" in motivo and IP not in motivo
    assert not cr.ler().get("pareado_em")


def _painel(bm, cr, monkeypatch, rede, **adb):
    monkeypatch.setattr(cr.av, "_rodar", AdbFalso(rede, **adb))
    return bm.painel_shopee_video


def test_botao_no_painel_e_tela_do_celular(bm, cr, monkeypatch, Msg, Est):
    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g84", "android", True, IP)))
    assert "Celular do Robô 📱" in _textos(sv.teclado_painel(sv.ler_config()))
    msg, est = Msg("Celular do Robô 📱"), Est()
    rodar(sv.celular_handler(msg, est))
    assert "moto-g84</b> ✅ ligado" in msg.saidas[0] and "Pareado: ⏳ ainda não" in msg.saidas[0]
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.celular.state


def test_pareamento_pelo_bot_apaga_a_mensagem_do_codigo(bm, cr, monkeypatch, Msg, Est):
    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g84", "android", True, IP)))
    est = Est()
    rodar(sv.pedir_pareamento(Msg("Parear Celular 🔗"), est))
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.aguardando_pareamento.state
    codigo = Msg("123456 37123")
    rodar(sv.receber_pareamento(codigo, est))
    assert codigo.apagada and "Pareado" in codigo.saidas[-1]
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.aguardando_porta.state
    assert "123456" not in json.dumps(rodar(est.get_data()))
    porta = Msg("41235")
    rodar(sv.receber_porta(porta, est))
    assert "Celular conectado:</b> motorola moto g84 5G, Android 14" in porta.saidas[-2]
    assert "✅ conectado" in porta.saidas[-1]


def test_codigo_recusado_volta_para_a_tela_do_celular(bm, cr, monkeypatch, Msg, Est):
    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g84", "android", True, IP)),
                 pair="Failed: Wrong password or connection was dropped.")
    est = Est(dados={"celular_ip": IP}, estado=sv.ShopeeVideoFluxo.aguardando_pareamento)
    msg = Msg("123456 37123")
    rodar(sv.receber_pareamento(msg, est))
    assert msg.apagada and "Não pareou: o código não confere" in msg.saidas[-1]
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.celular.state


def test_sem_celular_na_rede_ou_com_dois_ligados(bm, cr, monkeypatch, Msg, Est):
    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g84", "android", False, IP)))
    msg = Msg("Parear Celular 🔗")
    rodar(sv.pedir_pareamento(msg, Est()))
    assert "Não achei nenhum celular ligado" in msg.saidas[0]

    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g84", "android", True, IP),
                                            ("celular-do-dia", "android", True, "100.70.3.3")))
    est = Est()
    rodar(sv.pedir_pareamento(Msg("Parear Celular 🔗"), est))
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.aguardando_escolha_celular.state
    msg = Msg("moto-g84")
    rodar(sv.receber_escolha_celular(msg, est))
    assert "Parear o celular</b> (moto-g84)" in msg.saidas[-1] and rodar(est.get_data())["celular_ip"] == IP


def test_reconectar_so_depois_de_parear(bm, cr, monkeypatch, Msg, Est):
    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g84", "android", True, IP)))
    msg = Msg("Reconectar Celular 🔄")
    rodar(sv.pedir_reconexao(msg, Est()))
    assert "ainda não foi pareado" in msg.saidas[0]
    cr.parear(IP, 37123, "123456")
    est = Est()
    rodar(sv.pedir_reconexao(Msg("Reconectar Celular 🔄"), est))
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.aguardando_porta.state


def test_explorar_no_celular_desconectado_nem_comeca(cr, monkeypatch, capsys):
    import postador_shopee_video as ps
    assert ps.explorar("tela", celular=True) is None
    assert "Celular do Robô" in capsys.readouterr().out


def test_passo_a_passo_para_refazer_depois_do_reset(bm, cr, monkeypatch, Msg, Est):
    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g100", "android", True, IP)))
    tela = Msg("Celular do Robô 📱")
    rodar(sv.celular_handler(tela, Est()))
    assert "Passo a Passo 📖" in _textos(sv.teclado_celular()) and "Resetou o celular?" in tela.saidas[0]
    msg, est = Msg("Passo a Passo 📖"), Est(estado=sv.ShopeeVideoFluxo.aguardando_porta)
    rodar(sv.passo_a_passo_handler(msg, est))
    texto = msg.saidas[0]
    for trecho in ("Shopee", "Tailscale", "VPN sempre ativa", "7 vezes", "Manter ativado",
                   "Depuração por Wi-Fi", "Parear Celular 🔗", "Reconectar Celular 🔄", "Disable key expiry"):
        assert trecho in texto
    assert len(texto) < 4096                                             # cabe numa mensagem do Telegram
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.celular.state


def test_ver_tela_do_celular_manda_o_link_so_conectado(bm, cr, monkeypatch, Msg, Est):
    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g100", "android", True, IP)))
    assert "Ver Tela do Celular 🖥️" in _textos(sv.teclado_celular())
    abertas = []
    monkeypatch.setattr(sv.av, "abrir_tela", lambda celular=False: abertas.append(celular) or True)
    msg = Msg("Ver Tela do Celular 🖥️")
    rodar(sv.abrir_tela_handler(msg, Est()))
    assert "desconectado" in msg.saidas[0] and abertas == []             # nunca conectou

    monkeypatch.setattr(cr, "conectado", lambda: True)
    msg, est = Msg("Ver Tela do Celular 🖥️"), Est(estado=sv.ShopeeVideoFluxo.aguardando_porta)
    rodar(sv.abrir_tela_handler(msg, est))
    assert abertas == [True] and "link da tela chegou" in msg.saidas[-1] and "Terminei" in msg.saidas[-1]
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.celular.state

    monkeypatch.setattr(sv.av, "abrir_tela", lambda celular=False: False)
    monkeypatch.setattr(sv.av, "_ler_estado_tela", lambda: "erro: o túnel não deu endereço")
    msg = Msg("Ver Tela do Celular 🖥️")
    rodar(sv.abrir_tela_handler(msg, Est()))
    assert "A tela não abriu (o túnel não deu endereço)" in msg.saidas[-1]

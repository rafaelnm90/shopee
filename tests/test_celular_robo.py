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
    assert "Celular do Robô 📱" in _textos(sv.teclado_robo(sv.ler_config()))
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
    # Com a depuração desligada, não acha a porta sozinho e pede ao Rafael.
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [])
    est, msg = Est(), Msg("Reconectar Celular 🔄")
    rodar(sv.pedir_reconexao(msg, est))
    assert "Não achei sozinho" in msg.saidas[1]
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.aguardando_porta.state


def test_explorar_no_celular_desconectado_nem_comeca(cr, monkeypatch, capsys):
    import postador_shopee_video as ps
    assert ps.explorar("tela", celular=True) is None
    assert "Celular do Robô" in capsys.readouterr().out


def test_passo_a_passo_para_refazer_depois_do_reset(bm, cr, monkeypatch, Msg, Est):
    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g100", "android", True, IP)))
    tela = Msg("Celular do Robô 📱")
    rodar(sv.celular_handler(tela, Est()))
    assert "Passo a Passo 📖" in _textos(sv.teclado_celular()) and "resetar o Motorola" in tela.saidas[0]
    # Cada botão explicado, e sem nome de botão quebrado no texto.
    assert "O que cada botão faz" in tela.saidas[0] and "{" not in tela.saidas[0]
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


def test_acha_a_porta_aberta_da_depuracao(cr):
    import socket
    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen()
    porta = servidor.getsockname()[1]
    try:
        assert cr.portas_abertas("127.0.0.1", range(porta - 2, porta + 3)) == [porta]
    finally:
        servidor.close()


def test_reconecta_sozinho_procurando_a_porta_nova(cr, monkeypatch):
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-17 10:00:00")
    monkeypatch.setattr(cr, "conectado", lambda: False)
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [37000, 39999, 41000])
    tentadas = []
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: tentadas.append(porta) or (
        (True, "moto g(100)") if porta == 41000 else (False, "o celular recusou")))
    pedidos = []
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: pedidos.append(partes) or (0, ""))
    assert cr.reconectar_sozinho() == (True, "moto g(100)")
    # A porta guardada é tentada uma vez, depois de desfazer a conexão presa; na busca, não de novo.
    assert pedidos == [("adb", "disconnect", f"{IP}:37000")] and tentadas == [37000, 39999, 41000]


def test_conexao_presa_volta_na_porta_guardada_sem_procurar_outra(cr, monkeypatch):
    # 24/10, 15:09: o robô disse "Depuração desligada" com ela ligada; o adb tinha ficado preso.
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-17 10:00:00")
    monkeypatch.setattr(cr, "conectado", lambda: False)
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: pytest.fail("não devia procurar outra porta"))
    pedidos = []
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: pedidos.append(partes) or (0, ""))
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (True, "moto g(100)") if porta == 37000 else (False, "x"))
    assert cr.reconectar_sozinho() == (True, "moto g(100)")
    assert pedidos == [("adb", "disconnect", f"{IP}:37000")]


def test_porta_guardada_aberta_que_nao_conecta_nao_culpa_a_depuracao(cr, monkeypatch):
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-17 10:00:00")
    monkeypatch.setattr(cr, "conectado", lambda: False)
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [37000])
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: (0, ""))
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (False, "o celular ainda não autorizou este servidor"))
    ok, motivo = cr.reconectar_sozinho()
    assert not ok and "responde no celular" in motivo and "não autorizou" in motivo
    assert "desligada" not in motivo


def test_porta_aberta_que_nao_conecta_reinicia_o_adb_do_servidor_e_tenta_de_novo(cr, monkeypatch):
    # 31/10, 16:09: a porta da depuração respondia, o adb não conectava, e o Retomar também não
    # achava o celular. O servidor do adb preso volta com o kill-server (as chaves do pareamento
    # ficam), e o robô tenta de novo antes de pedir o pareamento.
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-17 10:00:00")
    monkeypatch.setattr(cr, "conectado", lambda: False)
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [37000])
    pedidos = []
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: pedidos.append(partes) or (0, ""))
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (True, "moto g(100)") if ("adb", "kill-server") in pedidos
                        else (False, "o adb vê o celular desligado (offline)"))
    assert cr.reconectar_sozinho() == (True, "moto g(100)")
    assert ("adb", "kill-server") in pedidos


@pytest.mark.parametrize("saida, motivo", [
    ("error: device offline", "o adb vê o celular desligado (offline)"),
    ("failed to connect to x: Connection reset by peer",
     "o adb não conseguiu (tente de novo; o adb disse: failed to connect to …: Connection reset by peer)"),
])
def test_motivo_do_adb_diz_o_que_o_adb_respondeu_sem_o_endereco(cr, saida, motivo):
    assert cr._motivo((1, saida.replace("x", f"{IP}:37000"))) == motivo


@pytest.mark.parametrize("resposta, esperado", [
    ((0, "device"), "adb: device"), ((1, "error: device offline"), "adb: offline"),
    ((1, "error: device unauthorized"), "adb: não autorizado"), (None, "adb: sem resposta"),
])
def test_estado_do_celular_so_com_estados_e_numeros(cr, monkeypatch, resposta, esperado):
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-17 10:00:00")
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [37000, 41000])
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: resposta)
    linha = cr.descrever_estado()
    assert esperado in linha and "porta guardada: aberta" in linha and "portas abertas no celular: 2" in linha
    # O log do android.yml é público: nem o endereço nem a porta.
    assert IP not in linha and "37000" not in linha


@pytest.mark.parametrize("dados, online, portas, motivo", [
    ({}, True, [41000], "ainda não foi pareado"),
    ({"ip": IP, "pareado_em": "x"}, False, [41000], "não está na rede privada"),
    ({"ip": IP, "pareado_em": "x"}, True, [], "Depuração por Wi-Fi está desligada"),
])
def test_sem_achar_o_celular_diz_o_motivo(cr, monkeypatch, dados, online, portas, motivo):
    cr._gravar(**dados)
    monkeypatch.setattr(cr, "conectado", lambda: False)
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": online}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: portas)
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: pytest.fail("não devia conectar"))
    ok, resultado = cr.reconectar_sozinho()
    assert not ok and motivo in resultado


def test_ocupado_ve_a_trava_de_outra_rodada(cr, monkeypatch, tmp_path):
    # O bot vê a rodada que ficou rodando na unidade própria depois de um reinício pela trava.
    monkeypatch.setattr(cr, "ARQUIVO_TRAVA", str(tmp_path / "celular.trava"))
    assert cr.ocupado() is False
    with cr.trava() as livre:
        assert livre and cr.ocupado() is True
    assert cr.ocupado() is False


@pytest.mark.parametrize("saida, motivo", [
    ("failed to authenticate to x", "pareie de novo"),
    ("failed to connect to x: Connection refused", "a porta mudou ou a depuração está desligada"),
    ("algo novo", "o adb não conseguiu"),
])
def test_motivo_do_adb_em_palavras_simples_sem_o_endereco(cr, saida, motivo):
    assert motivo in cr._motivo((1, saida.replace("x", f"{IP}:37000")))
    assert IP not in cr._motivo((1, saida.replace("x", f"{IP}:37000")))


# --- O pareamento vencido (31/10, 16:09: 7 dias depois do pareamento de 24/10, 16:05) ---

@pytest.mark.parametrize("saida, vencido", [
    ("failed to connect to x", True),                                    # a ligação abriu e o celular cortou
    ("failed to authenticate to x", True),
    ("failed to connect to 'x': Connection refused", False),             # a porta não abriu
    ("failed to connect to 'x': Connection timed out", False),
    ("failed to connect to x: Connection reset by peer", False),
])
def test_ligacao_aberta_que_o_celular_nao_aceita_pede_para_parear(cr, saida, vencido):
    # O Rafael mandou a porta certa duas vezes e o bot dizia "confira a porta": o celular não
    # reconhecia mais o servidor, e só parear de novo resolvia.
    motivo = cr._motivo((1, saida.replace("x", f"{IP}:41999")))
    assert cr.pede_pareamento(motivo) is vencido and IP not in motivo and "41999" not in motivo
    if vencido:
        assert "Parear Celular 🔗" in motivo and cr.OPCAO_DO_PRAZO in motivo


def test_o_botao_de_parear_no_motivo_e_o_do_painel(bm, cr):
    assert bm.painel_shopee_video.BOTAO_PAREAR in cr.COMO_PAREAR


def _vencido(cr):
    return cr._motivo((1, f"failed to connect to {IP}:41999"))


def test_porta_nova_que_nao_aceita_o_servidor_nao_culpa_a_porta(cr, monkeypatch):
    # 18:32: com a depuração desligada e ligada, a porta nova abriu, e o bot dizia que nenhuma
    # porta aberta era a da depuração.
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-24 16:05:00")
    monkeypatch.setattr(cr, "conectado", lambda: False)
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [41999])
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: (0, ""))
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (False, _vencido(cr)) if porta == 41999
                        else (False, "o celular recusou: a porta mudou ou a depuração está desligada"))
    ok, motivo = cr.reconectar_sozinho()
    assert not ok and cr.pede_pareamento(motivo) and "nenhuma é a da Depuração" not in motivo


def test_porta_guardada_aberta_com_o_pareamento_vencido_pede_para_parear(cr, monkeypatch):
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-24 16:05:00")
    monkeypatch.setattr(cr, "conectado", lambda: False)
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [37000])
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: (0, ""))
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (False, _vencido(cr)))
    ok, motivo = cr.reconectar_sozinho()
    assert not ok and cr.pede_pareamento(motivo) and motivo.startswith("a Depuração por Wi-Fi responde, mas")
    assert "se continuar" not in motivo


@pytest.mark.parametrize("resposta, prazo", [
    ((0, "0"), 0), ((0, "null"), 7), ((0, "604800000"), 7), ((0, "86400000"), 1),
    ((1, "error: device offline"), None), (None, None), ((0, "abc"), None),
])
def test_prazo_do_pareamento_lido_no_celular(cr, monkeypatch, resposta, prazo):
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-24 16:05:00")
    pedidos = []
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: pedidos.append(partes) or resposta)
    assert cr.ler_prazo_da_autorizacao() == prazo
    # Só lê a configuração do Android: nada é mudado no celular.
    assert pedidos == [("adb", "-s", f"{IP}:37000", "shell", "settings", "get", "global", cr.CONFIG_DO_PRAZO)]


def test_prazo_anotado_de_hora_em_hora_e_na_hora_pelo_painel(cr, monkeypatch):
    from datetime import datetime, timedelta
    from fuso import fuso_horario
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-24 16:05:00")
    lidas = []
    monkeypatch.setattr(cr, "ler_prazo_da_autorizacao", lambda: lidas.append(1) or 7)
    agora = datetime(2026, 10, 31, 19, 0, tzinfo=fuso_horario)
    assert cr.anotar_prazo(agora=agora) == 7 and lidas == [1]
    assert cr.ler()["prazo_da_autorizacao"] == 7 and cr.ler()["prazo_lido_em"] == "2026-10-31 19:00:00"
    assert cr.anotar_prazo(agora=agora + timedelta(minutes=30)) == 7 and lidas == [1]
    assert cr.anotar_prazo(agora=agora + timedelta(minutes=61)) == 7 and lidas == [1, 1]
    assert cr.anotar_prazo(forcar=True, agora=agora + timedelta(minutes=62)) == 7 and len(lidas) == 3


def test_estado_mostra_o_prazo_do_pareamento(cr, monkeypatch):
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-24 16:05:00")
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [37000])
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: (0, "0") if "settings" in partes else (0, "device"))
    assert cr.descrever_estado().endswith("adb: device | portas abertas no celular: 1 | prazo do pareamento: sem prazo")
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: (1, "error: device offline"))
    assert cr.descrever_estado().endswith("prazo do pareamento: não lido")


def test_reconectar_com_o_pareamento_vencido_manda_parear_sem_pedir_a_porta(bm, cr, monkeypatch, Msg, Est):
    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g100", "android", True, IP)))
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-24 16:05:00")
    monkeypatch.setattr(cr, "reconectar_sozinho", lambda: (False, f"a Depuração por Wi-Fi responde, mas {_vencido(cr)}"))
    monkeypatch.setattr(sv, "_escolher_celular", lambda *a: pytest.fail("não devia pedir a porta"))
    msg, est = Msg("Reconectar Celular 🔄"), Est()
    rodar(sv.pedir_reconexao(msg, est))
    assert "Não reconectei" in msg.saidas[-1] and "Parear Celular 🔗" in msg.saidas[-1]
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.celular.state


def test_porta_certa_com_o_pareamento_vencido_manda_parear(bm, cr, monkeypatch, Msg, Est):
    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g100", "android", True, IP)))
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (False, _vencido(cr)))
    msg, est = Msg("41999"), Est(dados={"celular_ip": IP}, estado=sv.ShopeeVideoFluxo.aguardando_porta)
    rodar(sv.receber_porta(msg, est))
    assert "Parear Celular 🔗" in msg.saidas[-1] and "Confira a porta" not in msg.saidas[-1]
    assert rodar(est.get_state()) == sv.ShopeeVideoFluxo.celular.state


def test_retomar_com_o_pareamento_vencido_diz_para_parear(bm, cr, monkeypatch, Msg, Est):
    sv = bm.painel_shopee_video
    sv.alterar_config(robo_pausado=True, robo_pausa_motivo=sv.robo.MOTIVO_DA_DESCONEXAO)
    monkeypatch.setattr(cr, "reconectar_sozinho", lambda: (False, f"a Depuração por Wi-Fi responde, mas {_vencido(cr)}"))
    msg = Msg("Confirmar Retomada ✅")
    rodar(sv.salvar_pausa_robo(msg, Est(estado=sv.ShopeeVideoFluxo.aguardando_confirmacao_pausa_robo)))
    resposta = next(t for t in msg.saidas if "Não retomei" in t)
    assert "Parear Celular 🔗" in resposta and "Depois de parear" in resposta
    assert "desligue e ligue de novo" not in resposta and sv.ler_config()["robo_pausado"] is True


def test_painel_do_celular_mostra_o_prazo_do_pareamento(bm, cr, monkeypatch, Msg, Est):
    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g100", "android", True, IP)))
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-24 16:05:00", modelo="moto g(100)")
    monkeypatch.setattr(cr, "conectado", lambda: True)
    monkeypatch.setattr(cr, "ler_prazo_da_autorizacao", lambda: 7)
    tela = Msg("Celular do Robô 📱")
    rodar(sv.celular_handler(tela, Est()))
    assert "Conectado, mas o pareamento vence" in tela.saidas[0] and "vence 7 dia(s)" in tela.saidas[0]
    assert cr.OPCAO_DO_PRAZO in tela.saidas[0] and cr.ler()["prazo_da_autorizacao"] == 7
    monkeypatch.setattr(cr, "ler_prazo_da_autorizacao", lambda: 0)
    tela = Msg("Celular do Robô 📱")
    rodar(sv.celular_handler(tela, Est()))
    assert "Tudo certo" in tela.saidas[0] and "✅ sem prazo" in tela.saidas[0]


def test_passo_a_passo_manda_deixar_a_opcao_do_prazo_sempre_ligada(bm, cr, monkeypatch, Msg, Est):
    # Pedido do Rafael (31/10): a opção entra em tudo, inclusive no Passo a Passo do botão.
    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g100", "android", True, IP)))
    msg = Msg("Passo a Passo 📖")
    rodar(sv.passo_a_passo_handler(msg, Est()))
    assert cr.OPCAO_DO_PRAZO in msg.saidas[0] and "sempre ligada" in msg.saidas[0]
    assert "não reconhece mais o servidor" in msg.saidas[0] and len(msg.saidas[0]) < 4096

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


@pytest.fixture(autouse=True)
def de_verdade(monkeypatch):
    """
    Nos testes, a sonda do adb do celular e o teste do certificado, sem rede; os testes deles
    recebem os de verdade (com um servidor local).
    """
    import celular_robo
    reais = {"sonda": celular_robo.adb_do_celular_responde,
             "certificado": celular_robo.certificado_do_celular_chega}
    monkeypatch.setattr(celular_robo, "adb_do_celular_responde", lambda ip, porta, prazo=0: True)
    monkeypatch.setattr(celular_robo, "certificado_do_celular_chega", lambda ip, porta, prazo=0: None)
    return reais


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
    # O Manter ativado com o texto que o Motorola mostra e o porquê (print do Rafael de 01/11).
    assert "Nunca deixar a tela em modo ocioso" in texto and "a tela não apaga" in texto
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
    # (Os comandos "shell" são a leitura do motivo da queda, na volta.)
    assert [p for p in pedidos if "shell" not in p] == [("adb", "disconnect", f"{IP}:37000")]
    assert tentadas == [37000, 39999, 41000]


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
    monkeypatch.setattr(cr, "portas_abertas", lambda ip, *_, **__: [41999])
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


def test_qr_do_pareamento_no_formato_do_android_e_senha_nova_a_cada_vez(cr):
    # P149 2 (05/11/2026): o pareamento também pelo QR que o Motorola lê na Depuração por Wi-Fi.
    nome, senha, texto = cr.novo_qr()
    assert texto == f"WIFI:T:ADB;S:{nome};P:{senha};;" and nome.startswith("robo-") and len(senha) == 12
    assert senha.isalnum() and nome[5:].isalnum() and cr.novo_qr()[1] != senha
    assert cr.imagem_do_qr(texto)[:4] == b"\x89PNG"


def test_pareamento_pelo_qr_acha_a_porta_nova_pela_rede_privada(cr, monkeypatch):
    # O QR foi feito para o celular achar o computador no mesmo Wi-Fi; pela rede privada o servidor
    # procura a porta que o celular abre depois de ler o QR e pareia nela com a senha do QR.
    varreduras = iter([[39615], [39615], [39615, 41001]])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: next(varreduras, [39615, 41001]))
    pedidos = []
    monkeypatch.setattr(cr, "parear", lambda ip, porta, senha: pedidos.append((ip, porta, senha)) or (porta == 41001, ""))

    def relogio(passo):
        tempos = iter(range(0, 10000, passo))
        return lambda: next(tempos)
    ok, motivo = cr.parear_pelo_qr(IP, "senha", {39615}, relogio=relogio(10), pausa=lambda s: None)
    assert ok and pedidos == [(IP, 41001, "senha")]
    # Sem porta nova até o fim da espera: o QR não foi lido a tempo.
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [39615])
    ok, motivo = cr.parear_pelo_qr(IP, "senha", {39615}, espera=300, relogio=relogio(60), pausa=lambda s: None)
    assert not ok and "não achei a porta do pareamento" in motivo
    # A porta nova que não pareia é tentada no máximo duas vezes, e o motivo traz o que o adb disse.
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [39615, 41001])
    pedidos.clear()
    monkeypatch.setattr(cr, "parear", lambda ip, porta, senha: pedidos.append(porta) or (False, "o código não confere"))
    ok, motivo = cr.parear_pelo_qr(IP, "senha", {39615}, espera=300, relogio=relogio(30), pausa=lambda s: None)
    assert not ok and pedidos == [41001, 41001] and "não pareou (o código não confere)" in motivo


def test_parear_por_qr_manda_o_qr_pareia_conecta_e_apaga_o_qr(bm, cr, monkeypatch, Msg, Est):
    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g100", "android", True, IP)))
    assert "Parear por QR 📷" in _textos(sv.teclado_celular())
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-17 10:00:00")
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [39615])
    monkeypatch.setattr(cr, "novo_qr", lambda: ("robo-teste", "senha", "WIFI:T:ADB;S:robo-teste;P:senha;;"))
    pedidos = []
    monkeypatch.setattr(cr, "parear_pelo_qr", lambda ip, senha, antes: pedidos.append((ip, senha, antes)) or (True, ""))
    monkeypatch.setattr(cr, "reconectar_sozinho", lambda: (True, "moto g(100)"))

    def com_foto(msg):
        enviadas = []

        async def answer_photo(foto, caption="", **_):
            enviadas.append(Msg(caption, saidas=msg.saidas))
            enviadas[-1].foto = foto
            return enviadas[-1]
        msg.answer_photo = answer_photo
        return enviadas
    msg = Msg("Parear por QR 📷")
    enviadas = com_foto(msg)
    rodar(sv.pedir_pareamento_pelo_qr(msg, Est()))
    # O QR em PNG, com o caminho no Motorola; a porta procurada é a que não estava aberta antes.
    assert enviadas[0].foto.data[:4] == b"\x89PNG" and "Parear o dispositivo com um código QR" in enviadas[0].text
    assert pedidos == [(IP, "senha", {39615})]
    # A senha do pareamento sai da conversa no fim, e o celular conecta.
    assert enviadas[0].apagada
    assert any("Pareado pelo QR" in s for s in msg.saidas) and any("Celular conectado" in s for s in msg.saidas)
    # Sem achar a porta: o QR sai do mesmo jeito, e o código de 6 dígitos fica de reserva.
    monkeypatch.setattr(cr, "parear_pelo_qr", lambda ip, senha, antes: (False, "não achei a porta do pareamento"))
    msg = Msg("Parear por QR 📷")
    enviadas = com_foto(msg)
    rodar(sv.pedir_pareamento_pelo_qr(msg, Est()))
    assert enviadas[0].apagada and "Não pareou pelo QR" in msg.saidas[-1] and "Parear Celular 🔗" in msg.saidas[-1]


def test_painel_nao_espera_o_adb_travado(bm, cr, monkeypatch, Msg, Est):
    # Vídeo do Rafael de 04/11/2026: com o adb do celular travado, o Robô Automático 🤖 e o Celular
    # do Robô 📱 esperavam o prazo inteiro do adb a cada tela. Com a ligação falhando há pouco, o
    # painel mostra "desconectado" sem perguntar.
    from datetime import datetime, timedelta
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-17 10:00:00", visto_em="2026-11-02 23:43:00",
               falha="o adb não respondeu", falha_em="2026-11-04 22:14:00")
    perguntas = []
    monkeypatch.setattr(cr, "conectado", lambda: perguntas.append("adb") or False)
    agora = datetime(2026, 11, 4, 22, 20)
    assert cr.conectado_no_painel(agora) is False and perguntas == []
    # Passados 20 min, pergunta uma vez; o "não respondeu" vale outros 20 min.
    assert cr.conectado_no_painel(agora + timedelta(minutes=30)) is False and perguntas == ["adb"]
    assert cr.conectado_no_painel(agora + timedelta(minutes=35)) is False and perguntas == ["adb"]
    # Visto depois (o celular voltou): pergunta na hora.
    cr._gravar(visto_em="2026-11-04 23:00:00")
    monkeypatch.setattr(cr, "conectado", lambda: perguntas.append("adb de novo") or True)
    assert cr.conectado_no_painel(agora + timedelta(minutes=41)) is True and perguntas[-1] == "adb de novo"
    # As duas telas usam o conectado do painel.
    sv = _painel(bm, cr, monkeypatch, _rede(("moto-g100", "android", True, IP)))
    monkeypatch.setattr(cr, "conectado_no_painel", lambda: perguntas.append("painel") or False)
    monkeypatch.setattr(cr, "conectado", lambda: pytest.fail("o painel não espera o adb"))
    rodar(sv.mostrar_robo(Msg("Robô Automático 🤖"), Est()))
    rodar(sv.celular_handler(Msg("Celular do Robô 📱"), Est()))
    assert perguntas[-2:] == ["painel", "painel"]


def test_porta_guardada_que_a_varredura_perde_e_conferida_sozinha(cr, monkeypatch):
    # 04/11/2026, 21:33: a varredura de todas as portas não achou a porta guardada, que respondia
    # no estado logo depois; o robô dizia "Depuração desligada" sem tentar reiniciar o adb.
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-17 10:00:00")
    monkeypatch.setattr(cr, "conectado", lambda: False)
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    conferidas = []
    monkeypatch.setattr(cr, "portas_abertas", lambda ip, portas=cr.PORTAS_DA_DEPURACAO, prazo=0.5:
                        conferidas.append((list(portas)[:2], prazo)) or ([37000] if list(portas) == [37000] else []))
    pedidos = []
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: pedidos.append(partes) or (0, ""))
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (True, "moto g(100)") if ("adb", "kill-server") in pedidos
                        else (False, "o adb vê o celular desligado (offline)"))
    monkeypatch.setattr(cr, "anotar_motivo_da_queda", lambda *partes, **nomes: None)
    assert cr.reconectar_sozinho() == (True, "moto g(100)")
    assert ("adb", "kill-server") in pedidos and ([37000], cr.PRAZO_DA_PORTA_GUARDADA) in conferidas
    # A guardada fechada de verdade continua dizendo que a depuração está desligada.
    monkeypatch.setattr(cr, "portas_abertas", lambda ip, portas=cr.PORTAS_DA_DEPURACAO, prazo=0.5: [])
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (False, "o adb vê o celular desligado (offline)"))
    ok, motivo = cr.reconectar_sozinho()
    assert not ok and "desligada" in motivo


def test_reconexao_que_falha_fica_no_estado_ate_o_celular_voltar(cr, monkeypatch):
    # 04/11/2026: na suspensão o robô não pausa nem avisa sem o celular, e o estado do android.yml
    # mostrava só "adb: sem resposta". O porquê da última reconexão que falhou fica no estado.
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-17 10:00:00")
    monkeypatch.setattr(cr, "conectado", lambda: False)
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [37000])
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: None)
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (False, "o celular ainda não autorizou este servidor"))
    ok, motivo = cr.reconectar_sozinho()
    linha = cr.descrever_estado()
    assert not ok and "adb: sem resposta | portas abertas no celular: 1" in linha
    assert f"última reconexão que falhou: {motivo} (" in linha
    # O log do android.yml é público: nem o endereço nem a porta.
    assert IP not in linha and "37000" not in linha
    # Fora da rede privada também aparece.
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": False}])
    assert cr.descrever_estado().startswith("na rede privada: não | última reconexão que falhou:")
    # Voltou: o motivo sai.
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (True, "moto g(100)"))
    monkeypatch.setattr(cr, "anotar_motivo_da_queda", lambda *partes, **nomes: None)
    assert cr.reconectar_sozinho() == (True, "moto g(100)")
    assert "última reconexão que falhou" not in cr.descrever_estado()


def test_estado_mostra_o_prazo_do_pareamento(cr, monkeypatch):
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-24 16:05:00")
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [37000])
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: (0, "0") if "settings" in partes else (0, "device"))
    assert "adb: device | portas abertas no celular: 1 | prazo do pareamento: sem prazo" in cr.descrever_estado()
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


class CelularQueVoltou:
    """O adb do celular que acabou de voltar: há quanto tempo está ligado, o registro do Android e o Wi-Fi."""

    def __init__(self, ligado_ha=None, logcat="", wifi="", lista=""):
        self.ligado_ha, self.logcat, self.wifi, self.lista, self.pedidos = ligado_ha, logcat, wifi, lista, []

    def __call__(self, *partes, timeout=0):
        self.pedidos.append(partes)
        if "/proc/uptime" in partes:
            return (0, f"{self.ligado_ha} 99999.0") if self.ligado_ha is not None else (1, "")
        if "logcat" in partes:
            return 0, self.logcat
        if "dumpsys" in partes:
            return 0, self.wifi
        if "list-scan-results" in partes:
            return 0, self.lista
        return 0, ""


# Um pedaço do "dumpsys wifi": a conexão de agora (5 GHz) e a última busca de redes, com o mesmo
# ponto duas vezes, o mesmo nome em 2,4 GHz, uma rede de nome parecido e outra rede; depois da
# linha em branco, outra seção do Android, que não conta.
WIFI = "\n".join([
    "Dump of ClientModeImpl:",
    'mWifiInfo SSID: "RedeDeTeste", BSSID: 02:00:00:00:00:01, MAC: 02:00:00:00:00:99, IP: /10.0.0.5, '
    "Security type: 2, Supplicant state: COMPLETED, RSSI: -50, Link speed: 433Mbps, Frequency: 5180MHz, Net ID: 3",
    "Latest scan results:",
    "    BSSID              Frequency      RSSI           Age(sec)     SSID                                 Flags",
    "  02:00:00:00:00:01       5180    -50(0:-52/1:-53)    1.234    RedeDeTeste                       [WPA2-PSK-CCMP][ESS]",
    "  02:00:00:00:00:02       2437    -45(0:-47/1:-48)    1.234    RedeDeTeste                       [WPA2-PSK-CCMP][ESS]",
    "  02:00:00:00:00:03       2412      -70    2.000    RedeDeTeste 2                     [WPA2-PSK-CCMP][ESS]",
    "  02:00:00:00:00:04       5745      -80    3.100    OutraRede                         [WPA2-PSK-CCMP][ESS]",
    "  02:00:00:00:00:01       5180      -51    4.000    RedeDeTeste                       [WPA2-PSK-CCMP][ESS]",
    "",
    "  02:00:00:00:00:05       2437      -40    1.000    RedeDeTeste                       [ESS]",
])


def test_wifi_conta_os_pontos_com_o_mesmo_nome_sem_mostrar_o_nome(cr):
    # Pedido do Rafael (01/11): numa queda longa o registro do Android some; os pontos de Wi-Fi com o
    # mesmo nome dizem se o celular pode ter trocado de ponto (o que desliga a Depuração por Wi-Fi).
    wifi = cr.interpretar_wifi(WIFI)
    assert wifi == {"faixa": "5 GHz", "sinal": -50, "pontos": 2, "por_faixa": {"2,4 GHz": 1, "5 GHz": 1}}
    texto = cr.descrever_wifi(wifi)
    assert texto == "Wi-Fi em 5 GHz, sinal -50 dBm, 2 ponto(s) com o mesmo nome (2,4 GHz: 1, 5 GHz: 1)"
    # O log do android.yml é público: nem o nome da rede nem o endereço do ponto.
    assert "RedeDeTeste" not in texto and "02:00" not in texto
    assert cr.interpretar_wifi("sem conexão") is None and cr.descrever_wifi(None) == "Wi-Fi não lido"
    so_a_conexao = WIFI.split("Latest scan results")[0]
    assert cr.descrever_wifi(cr.interpretar_wifi(so_a_conexao)) == (
        "Wi-Fi em 5 GHz, sinal -50 dBm, 0 ponto(s) com o mesmo nome (busca de redes: 0 linha(s) no dumpsys, 0 na "
        "lista, 0 com ponto)")


def test_wifi_le_a_busca_no_formato_de_rotulos_e_mostra_a_forma_quando_nada_bate(cr):
    # 01/11: no Motorola, a contagem saiu 0, e o celular sempre enxerga o próprio ponto. A busca
    # também pode vir como "SSID: ..., BSSID: ..., frequency: ...", e quando nenhuma linha bate, o
    # estado mostra a forma das linhas (o tipo de cada pedaço), nunca o nome, o endereço ou os números.
    conexao = WIFI.split("Latest scan results")[0]
    rotulos = conexao + "\n".join([
        "Latest scan results:",
        '  SSID: "RedeDeTeste", BSSID: 02:00:00:00:00:01, capabilities: [WPA2-PSK-CCMP][ESS], level: -50, '
        "frequency: 5180, timestamp: 123456",
        '  SSID: "RedeDeTeste", BSSID: 02:00:00:00:00:02, capabilities: [WPA2-PSK-CCMP][ESS], level: -45, '
        "frequency: 2437, timestamp: 123456",
        '  SSID: "RedeDeTeste 2", BSSID: 02:00:00:00:00:03, capabilities: [ESS], level: -70, frequency: 2412',
        ""])
    assert cr.interpretar_wifi(rotulos)["por_faixa"] == {"2,4 GHz": 1, "5 GHz": 1}
    estranho = conexao + "\n".join([
        "Latest scan results:",
        "    BSSID              Frequency      RSSI           Age(sec)     SSID                                 Flags",
        "  02:00:00:00:00:01       5180      -50    1.234    5265646554657374                  [WPA2-PSK-CCMP][ESS]",
        ""])
    texto = cr.descrever_wifi(cr.interpretar_wifi(estranho))
    assert texto == ("Wi-Fi em 5 GHz, sinal -50 dBm, 0 ponto(s) com o mesmo nome (busca de redes: 2 linha(s) no dumpsys, 0 na lista, "
                     "1 com ponto; forma: MAC NUM NUM DEC NUM [..])")
    assert "02:00" not in texto and "5180" not in texto and "RedeDeTeste" not in texto
    # Pedaço do nome de outra rede com cara de rótulo ("Casa:") não aparece: só os rótulos do Android.
    outra = conexao + "\n".join([
        "Latest scan results:",
        "  SSID: Casa: 5G, BSSID: 02:00:00:00:00:04, frequency: 5180 level=-60",
        ""])
    texto = cr.descrever_wifi(cr.interpretar_wifi(outra))
    assert texto.endswith("forma: SSID: TXT NUM+unid BSSID: MAC frequency: NUM level=…)")
    assert "Casa" not in texto


def _linha_do_android(texto):
    return f"10-31 22:01:13.456  1234  5678 I AdbDebuggingManager: {texto}"


@pytest.mark.parametrize("ligado_ha, logcat, motivo", [
    # Ligado há 10 min, fora há 2 h: reiniciou no meio.
    (600, "", "reiniciou"),
    # Ligado há 3 dias: a Depuração caiu com o Wi-Fi, pela última linha do Android que a desliga.
    (259200, "\n".join([_linha_do_android("Network disconnected. Disabling adbwifi."),
                        _linha_do_android("Detected wifi network change. Disabling adbwifi.")]), "trocou de ponto"),
    (259200, _linha_do_android("Network disconnected. Disabling adbwifi."), "o Wi-Fi caiu"),
    (259200, _linha_do_android("Wifi disabled. Disabling adbwifi."), "o Wi-Fi foi desligado"),
    (259200, _linha_do_android("Starting adbwifi on port 41999"), "não guardou o motivo"),
    (None, "", "não guardou o motivo"),
])
def test_motivo_da_queda_lido_no_celular_na_volta(cr, monkeypatch, ligado_ha, logcat, motivo):
    # Pergunta do Rafael (31/10, 22:05): por que o celular desconectou de novo? O Android desliga a
    # Depuração por Wi-Fi quando o Wi-Fi cai, quando o celular troca de ponto de Wi-Fi ou quando
    # ele reinicia; na volta, o servidor lê no celular qual foi.
    from datetime import datetime
    from fuso import fuso_horario
    cr._gravar(ip=IP, porta=41000, pareado_em="2026-10-17 10:00:00")
    monkeypatch.setattr(cr.av, "_rodar", CelularQueVoltou(ligado_ha, logcat))
    agora = datetime(2026, 11, 1, 17, 0, tzinfo=fuso_horario)
    achado, detalhe = cr.motivo_da_queda("2026-11-01 15:00:00", agora=agora)
    assert motivo in achado and "fora há 120 min" in detalhe
    # A linha crua do Android nunca sai: só o motivo fixo.
    assert "adbwifi" not in achado.casefold() and "1234" not in detalhe


def test_queda_longa_guarda_o_tempo_fora_o_tempo_ligado_e_o_wifi_no_registro_e_no_estado(cr, monkeypatch):
    # Queda de 22:05 de 31/10: 13 h fora, o registro do Android já renovado e o motivo perdido. O
    # detalhe (fora há, ligado há e os pontos de Wi-Fi) vai ao registro, ao banco e ao estado.
    from datetime import datetime
    from conftest import consultar
    from fuso import fuso_horario
    cr._gravar(ip=IP, porta=41000, pareado_em="2026-10-17 10:00:00")
    monkeypatch.setattr(cr.av, "_rodar", CelularQueVoltou(259200, "", wifi=WIFI))
    agora = datetime(2026, 11, 1, 11, 35, tzinfo=fuso_horario)
    assert cr.anotar_motivo_da_queda("2026-10-31 22:05:00", agora=agora) == cr.SEM_O_MOTIVO
    esperado = ("fora há 810 min; ligado há 4320 min; na volta: Wi-Fi em 5 GHz, sinal -50 dBm, 2 ponto(s) com o mesmo "
                "nome (2,4 GHz: 1, 5 GHz: 1)")
    assert cr.ler()["ultima_queda"]["detalhe"] == esperado
    assert consultar("SELECT detalhe FROM registro_processos WHERE processo = ?", cr.PROCESSO_DA_QUEDA)[0] == esperado
    # O estado (android.yml), com o celular conectado: há quanto tempo está ligado, o Wi-Fi de agora
    # e a última queda com o detalhe.
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [41000])
    voltou = CelularQueVoltou(7200, "", wifi=WIFI)
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: (0, "device") if "get-state" in partes
                        else (0, "0") if "settings" in partes else voltou(*partes))
    linha = cr.descrever_estado()
    assert "prazo do pareamento: sem prazo | ligado há 2 h | Wi-Fi em 5 GHz, sinal -50 dBm, 2 ponto(s) com o mesmo nome" in linha
    assert f"última queda: {cr.SEM_O_MOTIVO}; fora há 810 min; ligado há 4320 min" in linha
    assert "RedeDeTeste" not in linha and "02:00" not in linha and IP not in linha


def test_wifi_do_motorola_vem_da_lista_do_cmd_wifi(cr, monkeypatch):
    # 01/11: no Motorola, o "dumpsys wifi" veio sem a busca de redes (0 linhas); a lista da última
    # busca vem do "cmd wifi list-scan-results", que o celular só lê (nenhuma busca nova é pedida).
    so_a_conexao = WIFI.split("Latest scan results")[0]
    tabela = WIFI.split("Latest scan results:\n")[1].split("\n\n")[0]
    assert cr.interpretar_wifi(so_a_conexao, tabela)["por_faixa"] == {"2,4 GHz": 1, "5 GHz": 1}
    recusa = "Exception occurred while executing 'list-scan-results':\njava.lang.SecurityException: sem permissão"
    texto = cr.descrever_wifi(cr.interpretar_wifi(so_a_conexao, recusa))
    assert texto == ("Wi-Fi em 5 GHz, sinal -50 dBm, 0 ponto(s) com o mesmo nome (busca de redes: 0 linha(s) no dumpsys, 2 na lista "
                     "(a lista deu erro), 0 com ponto)")
    # Pelo adb do celular: os dois comandos só leem.
    cr._gravar(ip=IP, porta=41000, pareado_em="2026-10-17 10:00:00")
    adb = CelularQueVoltou(7200, "", wifi=so_a_conexao, lista=tabela)
    monkeypatch.setattr(cr.av, "_rodar", adb)
    assert cr.descrever_wifi(cr.ler_wifi()) == (
        "Wi-Fi em 5 GHz, sinal -50 dBm, 2 ponto(s) com o mesmo nome (2,4 GHz: 1, 5 GHz: 1)")
    comandos = [" ".join(p[p.index("shell") + 1:]) for p in adb.pedidos if "shell" in p]
    assert comandos == ["dumpsys wifi", "cmd wifi list-scan-results"]


def test_sinal_do_wifi_de_hora_em_hora_aparece_na_volta_da_queda(cr, monkeypatch):
    # 01/11: o celular enxerga um ponto só com o nome da rede (5 GHz), então a queda das 22:05 não
    # foi troca de ponto; falta saber se foi o sinal fraco. A leitura de hora em hora (junto do
    # prazo do pareamento) guarda a faixa e o sinal, e a volta mostra os de antes da queda.
    from datetime import datetime
    from fuso import fuso_horario
    cr._gravar(ip=IP, porta=41000, pareado_em="2026-10-17 10:00:00")
    fraco = WIFI.replace("RSSI: -50", "RSSI: -81")
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: (0, "0") if "settings" in partes
                        else CelularQueVoltou(7200, "", wifi=fraco)(*partes))
    monkeypatch.setattr(cr.shutil, "which", lambda nome: "/usr/bin/adb")
    assert cr.anotar_prazo(agora=datetime(2026, 11, 1, 21, 0, tzinfo=fuso_horario)) == 0
    assert cr.ler()["ultimo_wifi"] == {"resumo": "5 GHz, -81 dBm", "lido_em": "2026-11-01 21:00:00"}
    # Dentro da mesma hora, nada é lido de novo.
    ler_wifi = cr.ler_wifi
    monkeypatch.setattr(cr, "ler_wifi", lambda: pytest.fail("leu o Wi-Fi antes de uma hora"))
    cr.anotar_prazo(agora=datetime(2026, 11, 1, 21, 30, tzinfo=fuso_horario))
    monkeypatch.setattr(cr, "ler_wifi", ler_wifi)
    monkeypatch.setattr(cr.av, "_rodar", CelularQueVoltou(259200, "", wifi=WIFI))
    agora = datetime(2026, 11, 2, 11, 35, tzinfo=fuso_horario)
    motivo, detalhe = cr.motivo_da_queda("2026-11-01 22:05:00", agora=agora)
    assert motivo == cr.SEM_O_MOTIVO
    assert detalhe == ("fora há 810 min; ligado há 4320 min; antes da queda (21:00): 5 GHz, -81 dBm; na volta: "
                       "Wi-Fi em 5 GHz, sinal -50 dBm, 2 ponto(s) com o mesmo nome (2,4 GHz: 1, 5 GHz: 1)")
    assert "RedeDeTeste" not in detalhe and "02:00" not in detalhe and len(detalhe) < 240


def test_wifi_que_falha_nao_derruba_o_motivo_da_queda(cr, monkeypatch):
    from datetime import datetime
    from fuso import fuso_horario
    cr._gravar(ip=IP, porta=41000, pareado_em="2026-10-17 10:00:00")
    monkeypatch.setattr(cr.av, "_rodar", CelularQueVoltou(259200, ""))
    monkeypatch.setattr(cr, "ler_wifi", lambda: 1 / 0)
    agora = datetime(2026, 11, 1, 17, 0, tzinfo=fuso_horario)
    motivo, detalhe = cr.motivo_da_queda("2026-11-01 15:00:00", agora=agora)
    assert motivo == cr.SEM_O_MOTIVO and detalhe.endswith("Wi-Fi não lido (erro ZeroDivisionError)")


def test_ligacao_presa_na_mesma_porta_nao_le_o_celular(cr, monkeypatch):
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: pytest.fail("não devia ler o celular"))
    assert cr.motivo_da_queda("2026-11-01 15:00:00", mesma_porta=True)[0] == cr.LIGACAO_PRESA


def test_volta_do_celular_anota_o_motivo_no_registro_no_estado_e_no_retomar(bm, cr, monkeypatch, Msg, Est):
    from datetime import datetime, timedelta

    from conftest import consultar
    from fuso import fuso_horario
    sv = bm.painel_shopee_video
    # Visto pela última vez há 30 min, pelo relógio do teste: ligado há 3 dias, o celular não
    # reiniciou depois disso (com uma data fixa, a conta dependeria do dia em que o teste roda).
    visto_em = (datetime.now(fuso_horario) - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-17 10:00:00", visto_em=visto_em)
    monkeypatch.setattr(cr, "conectado", lambda: False)
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip, *_, **__: [41000])
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (True, "moto g(100)") if porta == 41000 else (False, "x"))
    monkeypatch.setattr(cr.av, "_rodar", CelularQueVoltou(
        259200, _linha_do_android("Detected wifi network change. Disabling adbwifi.")))
    sv.alterar_config(robo_pausado=True, robo_pausa_motivo=sv.robo.MOTIVO_DA_DESCONEXAO)
    msg = Msg("Confirmar Retomada ✅")
    rodar(sv.salvar_pausa_robo(msg, Est(estado=sv.ShopeeVideoFluxo.aguardando_confirmacao_pausa_robo)))
    resultado, detalhe = consultar("SELECT resultado, detalhe FROM registro_processos WHERE processo = ?",
                                   cr.PROCESSO_DA_QUEDA)
    assert "trocou de ponto de Wi-Fi" in resultado and detalhe.startswith("fora há")
    assert "trocou de ponto de Wi-Fi" in (cr.ler().get("ultima_queda") or {}).get("motivo", "")
    retomado = next(t for t in msg.saidas if "retomado" in t)
    assert "Por que o celular tinha saído: o celular trocou de ponto de Wi-Fi" in retomado
    # O estado (android.yml) mostra a última queda, só com o motivo fixo e a hora.
    monkeypatch.setattr(cr, "portas_abertas", lambda ip, *_, **__: [41000])
    cr._gravar(porta=41000)
    assert "última queda: o celular trocou de ponto de Wi-Fi" in cr.descrever_estado()


def _servidor_de_teste(resposta):
    """Um servidor local que recebe o começo da ligação e responde (ou fica calado, com None)."""
    import contextlib
    import socket
    import threading
    escuta = socket.socket()
    escuta.bind(("127.0.0.1", 0))
    escuta.listen()
    recebido = []

    def atender():
        ligacao, _ = escuta.accept()
        with ligacao:
            recebido.append(ligacao.recv(31, socket.MSG_WAITALL))
            # Espera a sonda fechar; ela pode fechar sem ler o resto (a ligação cai).
            with contextlib.suppress(OSError):
                if resposta is not None:
                    ligacao.sendall(resposta)
                ligacao.recv(64)

    threading.Thread(target=atender, daemon=True).start()
    return escuta, recebido


@pytest.mark.parametrize("resposta, esperado", [
    (b"STLS" + bytes(20), True), (b"AUTH" + bytes(20), True), (b"HTTP/1.1 400 Bad Request\r\n\r\n", False),
    (None, False),
])
def test_sonda_separa_o_adb_do_celular_que_responde_do_calado(de_verdade, resposta, esperado):
    # 04/11/2026: a porta da depuração abria, também a nova, e a conexão não se completava. A sonda
    # manda o começo da ligação do adb (CNXN) e lê a resposta: o adb do celular calado travou.
    import struct
    escuta, recebido = _servidor_de_teste(resposta)
    try:
        assert de_verdade["sonda"]("127.0.0.1", escuta.getsockname()[1], prazo=0.5) is esperado
    finally:
        escuta.close()
    comando, versao, maximo, tamanho, soma, magica = struct.unpack("<6I", recebido[0][:24])
    assert recebido[0][:4] == b"CNXN" and magica == comando ^ 0xFFFFFFFF and versao == 0x01000001
    assert recebido[0][24:] == b"host::\x00" and tamanho == 7 and soma == sum(b"host::\x00") and maximo > 0


def test_sonda_na_porta_fechada_diz_que_nem_aceitou(de_verdade):
    import socket
    fechada = socket.socket()
    fechada.bind(("127.0.0.1", 0))
    porta = fechada.getsockname()[1]
    fechada.close()
    assert de_verdade["sonda"]("127.0.0.1", porta, prazo=0.5) is None


def test_adb_do_celular_calado_pede_para_reiniciar_o_celular(cr, monkeypatch):
    # 04/11/2026, 23:16: depois de desligar e ligar a depuração, a porta nova abria e o adb não
    # conectava; com o adb do celular travado, nem o adb do servidor reiniciado nem parear de novo
    # resolvem: o motivo manda reiniciar o celular.
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-17 10:00:00")
    monkeypatch.setattr(cr, "conectado", lambda: False)
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip, *_, **__: [41000])
    pedidos = []
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: pedidos.append(partes) or (0, ""))
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (False, "o adb não respondeu"))
    monkeypatch.setattr(cr, "adb_do_celular_responde", lambda ip, porta, prazo=0: False)
    ok, motivo = cr.reconectar_sozinho()
    assert not ok and motivo == cr.ADB_DO_CELULAR_TRAVADO and "reinicie o Motorola" in motivo
    assert not cr.pede_pareamento(motivo) and ("adb", "kill-server") not in pedidos
    # Também com a porta guardada aberta e calada: o adb do servidor não é reiniciado à toa.
    monkeypatch.setattr(cr, "portas_abertas", lambda ip, *_, **__: [37000])
    ok, motivo = cr.reconectar_sozinho()
    assert not ok and motivo == cr.ADB_DO_CELULAR_TRAVADO and ("adb", "kill-server") not in pedidos


def test_porta_nova_em_que_o_adb_responde_reinicia_o_adb_do_servidor(cr, monkeypatch):
    # Com a porta guardada fechada (a depuração foi desligada e ligada), o adb do servidor preso só
    # era reiniciado se a guardada estivesse aberta, e a porta nova nunca conectava.
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-17 10:00:00")
    monkeypatch.setattr(cr, "conectado", lambda: False)
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip, *_, **__: [41000])
    pedidos = []
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: pedidos.append(partes) or (0, ""))
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (True, "moto g(100)")
                        if porta == 41000 and ("adb", "kill-server") in pedidos else (False, "o adb não respondeu"))
    quedas = []
    monkeypatch.setattr(cr, "anotar_motivo_da_queda", lambda visto_em, mesma_porta=False, **_: quedas.append(mesma_porta))
    assert cr.reconectar_sozinho() == (True, "moto g(100)")
    assert ("adb", "kill-server") in pedidos and quedas == [False]
    # Se nem assim conectar, o adb do servidor é derrubado à força e tentado de novo; sem conectar,
    # o motivo diz que a depuração responde, sem mandar reiniciar o celular.
    pedidos.clear()
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (True, "moto g(100)")
                        if ("pkill", "-KILL", "-x", "adb") in pedidos else (False, "o adb não respondeu"))
    assert cr.reconectar_sozinho() == (True, "moto g(100)")
    assert pedidos.index(("adb", "kill-server")) < pedidos.index(("pkill", "-KILL", "-x", "adb"))
    pedidos.clear()
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (False, "o adb não respondeu"))
    ok, motivo = cr.reconectar_sozinho()
    assert not ok and "responde no celular, mas o adb não conecta (o adb não respondeu)" in motivo
    assert ("adb", "kill-server") in pedidos and "reinicie" not in motivo
    # Outro motivo (o celular respondeu algo) não derruba o adb do servidor à força.
    pedidos.clear()
    monkeypatch.setattr(cr, "conectar", lambda ip, porta: (False, "o celular ainda não autorizou este servidor"))
    assert not cr.reconectar_sozinho()[0] and ("pkill", "-KILL", "-x", "adb") not in pedidos


def test_estado_mostra_se_o_adb_do_celular_responde_nas_portas_abertas(cr, monkeypatch):
    cr._gravar(ip=IP, porta=37000, pareado_em="2026-10-17 10:00:00")
    monkeypatch.setattr(cr, "celulares_na_rede", lambda: [{"nome": "moto", "ip": IP, "online": True}])
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [41000])
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: None)
    monkeypatch.setattr(cr, "adb_do_celular_responde", lambda ip, porta, prazo=0: False)
    linha = cr.descrever_estado()
    assert "portas abertas no celular: 1 | adb do celular responde em 0 de 1 | caminho: " in linha
    assert "certificado do celular: não testado | prazo do pareamento" in linha
    # O log do android.yml é público: nem o endereço nem a porta.
    assert IP not in linha and "41000" not in linha
    # Conectado, o adb já responde: nada é sondado.
    monkeypatch.setattr(cr, "portas_abertas", lambda ip: [37000])
    monkeypatch.setattr(cr.av, "_rodar", lambda *partes, timeout=0: (0, "0") if "settings" in partes else (0, "device"))
    monkeypatch.setattr(cr, "adb_do_celular_responde", lambda *_, **__: pytest.fail("conectado não sonda"))
    assert "adb do celular responde" not in cr.descrever_estado()


def _certificado_de_teste(pasta):
    """Um certificado próprio (como o do adb do celular), feito na hora numa pasta do teste."""
    from datetime import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    chave = ec.generate_private_key(ec.SECP256R1())
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "adb")])
    certificado = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
                   .serial_number(x509.random_serial_number()).not_valid_before(datetime(2026, 1, 1))
                   .not_valid_after(datetime(2036, 1, 1)).sign(chave, hashes.SHA256()))
    (pasta / "cert.pem").write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
    (pasta / "chave.pem").write_bytes(chave.private_bytes(serialization.Encoding.PEM,
                                                          serialization.PrivateFormat.PKCS8,
                                                          serialization.NoEncryption()))
    return str(pasta / "cert.pem"), str(pasta / "chave.pem")


@pytest.mark.parametrize("comportamento, esperado", [("tls", True), ("calado", False), ("auth", None)])
def test_certificado_do_celular_chega_ou_se_perde_no_caminho(de_verdade, tmp_path, comportamento, esperado):
    # 04/11/2026: o adb do celular respondia ao começo da ligação e a parte cifrada (a dos
    # certificados, com pacotes maiores) não se completava, nem no pareamento pelo QR.
    import contextlib
    import socket
    import ssl
    import struct
    import threading
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.load_cert_chain(*_certificado_de_teste(tmp_path))
    escuta = socket.socket()
    escuta.bind(("127.0.0.1", 0))
    escuta.listen()
    recebido = []

    def cabecalho(comando):
        numero = int.from_bytes(comando, "little")
        return struct.pack("<6I", numero, 0x01000000, 0, 0, 0, numero ^ 0xFFFFFFFF)

    def atender():
        ligacao, _ = escuta.accept()
        with ligacao, contextlib.suppress(OSError):
            ligacao.recv(31, socket.MSG_WAITALL)
            ligacao.sendall(cabecalho(b"AUTH" if comportamento == "auth" else b"STLS"))
            recebido.append(ligacao.recv(24, socket.MSG_WAITALL))
            if comportamento == "tls":
                contexto.wrap_socket(ligacao, server_side=True)
            # Calado: lê o que chega (o começo da parte cifrada) e não responde, até a sonda fechar.
            while ligacao.recv(4096):
                pass

    threading.Thread(target=atender, daemon=True).start()
    try:
        assert de_verdade["certificado"]("127.0.0.1", escuta.getsockname()[1], prazo=1) is esperado
    finally:
        escuta.close()
    # Depois do STLS do celular, o servidor responde STLS, como o adb, antes da parte cifrada.
    if comportamento != "auth":
        assert recebido and recebido[0][:4] == b"STLS"


def test_caminho_e_ping_ate_o_celular_so_com_estados_e_numeros(cr, monkeypatch):
    respostas = {
        "direto": (0, f"pong from moto ({IP}) via 189.1.2.3:41641 in 33ms"),
        "relay": (1, f"pong from moto ({IP}) via DERP(sao) in 152ms\npong from moto ({IP}) via DERP(sao) "
                     "in 140ms\ndirect connection not established"),
        "nada": (1, "timeout waiting for ping reply"),
    }
    caminho = ["direto"]

    def rodar_falso(*partes, timeout=0):
        if partes[:2] == ("tailscale", "ping"):
            return respostas[caminho[0]]
        if partes[0] == "ping":
            grande = partes[partes.index("-s") + 1] == "1200"
            return (1, "3 packets transmitted, 0 received, 100% packet loss") if grande else \
                (0, f"--- {IP} ping statistics ---\n3 packets transmitted, 3 received, 0% packet loss")
        return None
    monkeypatch.setattr(cr.av, "_rodar", rodar_falso)
    monkeypatch.setattr(cr, "certificado_do_celular_chega", lambda ip, porta, prazo=0: False)
    linha = cr.rede_ate_o_celular(IP, 41000)
    assert linha == ("caminho: direto, 33 ms | ping pequeno: 3 de 3, grande: 0 de 3 | certificado do celular: "
                     "não chega (os pacotes grandes se perdem no caminho)")
    # O log do android.yml é público: nem o endereço nem a porta.
    assert IP not in linha and "41000" not in linha and "189.1" not in linha
    caminho[0] = "relay"
    assert cr.caminho_ate_o_celular(IP) == "pelo relay, 140 ms"
    caminho[0] = "nada"
    assert cr.caminho_ate_o_celular(IP) == "sem resposta"
    # Sem porta do adb que responda, o certificado não é testado; sem o ping no servidor, diz isso.
    monkeypatch.setattr(cr.shutil, "which", lambda nome: None if nome == "ping" else f"/usr/bin/{nome}")
    assert cr.rede_ate_o_celular(IP, None).endswith("ping: sem o ping no servidor | certificado do celular: não testado")

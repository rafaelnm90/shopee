"""tela_android.py: só responde com a chave, e cada ação da página vira um comando adb seguro."""
import asyncio

import pytest
from aiohttp import web

import tela_android as tela
from conftest import rodar


class Pedido:
    def __init__(self, chave="", corpo=None):
        self.query = {"k": chave} if chave else {}
        self._corpo = corpo or {}

    async def json(self):
        return self._corpo


def test_sem_a_chave_nada_responde():
    for handler in (tela.pagina, tela.tela):
        with pytest.raises(web.HTTPNotFound):
            rodar(handler(Pedido("chave-errada")))
    with pytest.raises(web.HTTPNotFound):
        rodar(tela.acao(Pedido("", {"tipo": "toque", "x": 1, "y": 1})))


def test_pagina_com_a_chave(monkeypatch):
    resposta = rodar(tela.pagina(Pedido(tela.CHAVE)))
    assert resposta.status == 200 and tela.CHAVE in resposta.text


def test_acoes_viram_comandos_adb():
    assert tela.comando_da_acao({"tipo": "toque", "x": 100.6, "y": 200}) == \
        ["shell", "input", "tap", "100", "200"]
    assert tela.comando_da_acao({"tipo": "arrastar", "x1": 10, "y1": 20, "x2": 300, "y2": 20, "ms": 50}) == \
        ["shell", "input", "swipe", "10", "20", "300", "20", "100"]       # duração mínima de 100 ms
    assert tela.comando_da_acao({"tipo": "tecla", "tecla": "voltar"}) == ["shell", "input", "keyevent", "4"]


def test_texto_vai_protegido_do_shell_do_android():
    comando = tela.comando_da_acao({"tipo": "texto", "texto": "minha senha; rm -rf /"})
    assert comando[:3] == ["shell", "input", "text"]
    assert comando[3] == "'minha%ssenha;%srm%s-rf%s/'"                 # um argumento só, entre aspas


def test_acoes_invalidas_sao_recusadas():
    for dados in ({"tipo": "toque", "x": -5, "y": 1}, {"tipo": "toque", "x": "1;reboot", "y": 1},
                  {"tipo": "tecla", "tecla": "desligar"}, {"tipo": "texto", "texto": ""},
                  {"tipo": "toque"}, {"tipo": "outra"}):
        assert tela.comando_da_acao(dados) is None
    with pytest.raises(web.HTTPBadRequest):
        rodar(tela.acao(Pedido(tela.CHAVE, {"tipo": "tecla", "tecla": "desligar"})))


def test_acao_valida_chama_o_adb(monkeypatch):
    chamados = []

    async def adb(*partes, timeout=20):
        chamados.append(partes)
        return b""

    monkeypatch.setattr(tela, "adb", adb)
    rodar(tela.acao(Pedido(tela.CHAVE, {"tipo": "toque", "x": 5, "y": 6})))
    assert chamados == [("shell", "input", "tap", "5", "6")]


def test_terminei_fecha_a_tela(monkeypatch):
    monkeypatch.setattr(tela, "FIM", asyncio.Event())
    rodar(tela.acao(Pedido(tela.CHAVE, {"tipo": "fim"})))
    assert tela.FIM.is_set()


def _zip(caminho, nomes):
    import zipfile
    with zipfile.ZipFile(caminho, "w") as z:
        for nome in nomes:
            z.writestr(nome, "x")
    return open(caminho, "rb").read()


def _enviar(conteudo, chave=None, tamanho_pedaco=None, inicios=None):
    """Sobe o servidor da tela de verdade e envia o arquivo em pedaços, como a página faz."""
    from aiohttp.test_utils import TestClient, TestServer
    k = tela.CHAVE if chave is None else chave
    tamanho = tamanho_pedaco or max(1, len(conteudo))
    inicios = inicios if inicios is not None else list(range(0, max(1, len(conteudo)), tamanho))

    async def cenario():
        async with TestClient(TestServer(tela.montar_app())) as cliente:
            for inicio in inicios:
                r = await cliente.post(f"/app/pedaco?k={k}&inicio={inicio}", data=conteudo[inicio:inicio + tamanho])
                if r.status != 200:
                    return r.status, None
                corpo = await r.json()
                if not corpo["ok"]:
                    return r.status, corpo
            r = await cliente.post(f"/app/instalar?k={k}")
            return r.status, (await r.json() if r.status == 200 else None)
    return rodar(cenario())


def _android_falso(monkeypatch, tmp_path):
    instalados = []
    monkeypatch.setattr(tela.av, "PASTA_APP", str(tmp_path / "app"))
    monkeypatch.setattr(tela.av, "_adb", lambda *p, timeout=30: instalados.append(p) or (0, ""))
    monkeypatch.setattr(tela.av, "versao_shopee", lambda pacote=None: "instalado, versão 3.40.21")
    return instalados


def test_enviar_app_em_pedacos_instala_as_partes(monkeypatch, tmp_path):
    instalados = _android_falso(monkeypatch, tmp_path)
    conteudo = _zip(tmp_path / "s.xapk", ["manifest.json", "com.shopee.br.apk", "config.arm64_v8a.apk",
                                         "config.x86_64.apk"])
    status, corpo = _enviar(conteudo, tamanho_pedaco=len(conteudo) // 3 + 1)   # 3 pedaços
    assert status == 200 and corpo == {"ok": True, "mensagem": "app da Shopee: instalado, versão 3.40.21"}
    comando = instalados[0]
    assert comando[0] == "install-multiple" and len(comando) == 5          # -r -g e as 2 partes do ARM 64
    assert not (tmp_path / "app").exists()                                # nada fica no servidor


def test_apkm_trancado_e_recusado_com_o_motivo(monkeypatch, tmp_path):
    instalados = _android_falso(monkeypatch, tmp_path)
    status, corpo = _enviar(b"conteudo cifrado do apkmirror")
    assert status == 200 and corpo["ok"] is False and ".apkm" in corpo["mensagem"]
    assert instalados == []


def test_enviar_app_sem_a_chave(monkeypatch, tmp_path):
    instalados = _android_falso(monkeypatch, tmp_path)
    status, _ = _enviar(b"x", chave="errada")
    assert status == 404 and instalados == []


def test_enviar_app_grande_demais(monkeypatch, tmp_path):
    instalados = _android_falso(monkeypatch, tmp_path)
    monkeypatch.setattr(tela, "LIMITE_APP_MB", 1)
    status, corpo = _enviar(b"x" * (2 * 1024 * 1024), tamanho_pedaco=700 * 1024)
    assert corpo == {"ok": False, "mensagem": "arquivo maior que 1 MB"} and instalados == []
    assert not (tmp_path / "app").exists()


def test_pedaco_que_pula_bytes_pede_para_enviar_de_novo(monkeypatch, tmp_path):
    instalados = _android_falso(monkeypatch, tmp_path)
    status, corpo = _enviar(b"abcdef", tamanho_pedaco=2, inicios=[0, 4])
    assert corpo == {"ok": False, "mensagem": "o envio se perdeu no meio: envie de novo"}
    assert instalados == []


def test_pedaco_repetido_nao_duplica_o_arquivo(monkeypatch, tmp_path):
    # O celular repete o pedaço quando a resposta se perde no caminho.
    instalados = _android_falso(monkeypatch, tmp_path)
    recebido = []
    monkeypatch.setattr(tela, "instalar_arquivo", lambda arq: recebido.append(open(arq, "rb").read()) or (True, "ok"))
    conteudo = b"0123456789"
    status, corpo = _enviar(conteudo, tamanho_pedaco=4, inicios=[0, 4, 4, 8])
    assert corpo == {"ok": True, "mensagem": "ok"} and recebido == [conteudo]
    assert instalados == []


def test_erro_no_envio_fica_registrado_so_o_tipo(monkeypatch, tmp_path):
    _android_falso(monkeypatch, tmp_path)
    monkeypatch.setattr(tela, "ESTADO", str(tmp_path / "tela_estado"))

    original = tela.os.makedirs

    def quebra(caminho, *a, **k):
        if caminho == tela.av.PASTA_APP:
            raise PermissionError("/home/fulano/segredo")
        return original(caminho, *a, **k)

    monkeypatch.setattr(tela.os, "makedirs", quebra)
    status, _ = _enviar(b"abc")
    assert status == 500
    assert (tmp_path / "tela_estado").read_text() == "enviado; último erro: pedaço PermissionError"


def test_endereco_do_tunel_na_saida_do_cloudflared():
    class Saida:
        def __init__(self, linhas):
            self.linhas = [l.encode() for l in linhas]

        async def readline(self):
            return self.linhas.pop(0) if self.linhas else b""

    processo = type("P", (), {})()
    processo.stdout = Saida(["INF Requesting new quick Tunnel", "|  https://palavras-soltas-aqui.trycloudflare.com  |"])
    assert rodar(tela.achar_url(processo, 5)) == "https://palavras-soltas-aqui.trycloudflare.com"
    processo.stdout = Saida(["INF erro qualquer"])
    assert rodar(tela.achar_url(processo, 5)) is None


def test_recusa_do_android_mostra_o_motivo(monkeypatch, tmp_path):
    monkeypatch.setattr(tela.av, "PASTA_APP", str(tmp_path / "app"))
    saida = ("Performing Streamed Install\nadb: failed to install /x/shopee.apk: Failure "
             "[INSTALL_FAILED_NO_MATCHING_ABIS: Failed to extract native libraries, res=-113]")
    monkeypatch.setattr(tela.av, "_adb", lambda *p, timeout=30: (1, saida))
    (tmp_path / "app").mkdir()
    arquivo = tmp_path / "app" / "enviado.zip"
    _zip(arquivo, ["AndroidManifest.xml"])
    ok, mensagem = tela.instalar_arquivo(str(arquivo))
    assert ok is False and "processador do servidor" in mensagem


def test_codigo_de_recusa_desconhecido_aparece_como_veio():
    assert tela.motivo_da_recusa("Failure [INSTALL_FAILED_ALGO_NOVO]") == \
        "o Android recusou o app: INSTALL_FAILED_ALGO_NOVO"
    assert "sem motivo" in tela.motivo_da_recusa("")

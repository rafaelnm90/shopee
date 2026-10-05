"""tela_android.py: só responde com a chave, e cada ação da página vira um comando adb seguro."""
import asyncio
import json

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


RECENTES = b"""ACTIVITY MANAGER RECENT TASKS (dumpsys activity recents)
mRecentsUid=10085
  Recent tasks:
  * Recent #0: Task{8c1d2e5 #1 type=home A=10085:com.android.launcher3 U=0 visible=true sz=1}
  * Recent #1: Task{2d4c1b4 #12 type=standard A=10123:com.shopee.br U=0 visible=false sz=1}
  * Recent #2: Task{9f03a77 #9 type=standard A=10118:com.apkpure.aegon U=0 visible=false sz=0}
  Visible recent tasks (most recent first):
  * RecentTaskInfo #0: id=12 userId=0 hasTask=true lastActiveTime=1234
"""


def test_fechar_apps_limpa_os_recentes_fecha_os_instalados_e_volta_ao_inicio(monkeypatch):
    chamados = []

    async def adb(*partes, timeout=20):
        chamados.append(partes)
        if partes[:4] == ("shell", "pm", "list", "packages"):
            return b"package:com.shopee.br\npackage:com.apkpure.aegon\n"
        if partes == ("shell", "dumpsys", "activity", "recents"):
            return RECENTES
        return b""

    monkeypatch.setattr(tela, "adb", adb)
    resposta = rodar(tela.acao(Pedido(tela.CHAVE, {"tipo": "fechar_apps"})))
    assert resposta.status == 200
    assert "2 app(s)" in json.loads(resposta.text)["mensagem"]
    # O cartão de cada app sai da lista de recentes; o da tela inicial fica.
    removidos = [p[4] for p in chamados if p[:4] == ("shell", "am", "stack", "remove")]
    assert removidos == ["12", "9"]
    assert ("shell", "am", "force-stop", "com.shopee.br") in chamados
    assert ("shell", "am", "force-stop", "com.apkpure.aegon") in chamados
    assert chamados[-1] == ("shell", "input", "keyevent", "3")             # tela inicial


def test_fechar_apps_com_a_lista_de_recentes_vazia(monkeypatch):
    chamados = []

    async def adb(*partes, timeout=20):
        chamados.append(partes)
        return b""

    monkeypatch.setattr(tela, "adb", adb)
    assert rodar(tela.fechar_apps()) == 0
    assert not [p for p in chamados if p[:3] == ("shell", "am", "stack")]
    assert chamados[-1] == ("shell", "input", "keyevent", "3")


def test_reiniciar_religa_o_conteiner_e_espera_ligar(monkeypatch):
    comandos, boot = [], iter([b"", b"1\n"])

    async def rodar_comando(*partes, timeout=120):
        comandos.append(partes)
        return True

    async def adb(*partes, timeout=20):
        return next(boot)

    monkeypatch.setattr(tela, "_rodar_comando", rodar_comando)
    monkeypatch.setattr(tela, "adb", adb)
    assert rodar(tela.reiniciar_android(espera=0)) is True
    assert comandos[0] == ("sudo", "-n", "docker", "restart", tela.av.CONTEINER)   # religa, não apaga nada
    assert ("adb", "connect", tela.av.ENDERECO_ADB) in comandos


def _prints(monkeypatch, respostas):
    """Prints falsos do Android, em ordem; devolve a lista de comandos de reconexão."""
    fila, comandos = list(respostas), []

    async def print_da_tela(timeout=20):
        return fila.pop(0)

    async def rodar_comando(*partes, timeout=120):
        comandos.append(partes)
        return True

    monkeypatch.setattr(tela, "print_da_tela", print_da_tela)
    monkeypatch.setattr(tela, "_rodar_comando", rodar_comando)
    monkeypatch.setitem(tela._imagem, "reconectou", 0.0)
    monkeypatch.setitem(tela._imagem, "motivo", "")
    monkeypatch.setitem(tela._reinicio, "tarefa", None)
    return comandos


def test_imagem_que_falha_reconecta_o_adb_e_tenta_de_novo(monkeypatch, tmp_path):
    monkeypatch.setattr(tela, "ESTADO", str(tmp_path / "tela_estado"))
    comandos = _prints(monkeypatch, [(b"", "adb desconectado (offline)"), (b"\x89PNG ok", "")])
    resposta = rodar(tela.tela(Pedido(tela.CHAVE)))
    assert resposta.status == 200 and resposta.body == b"\x89PNG ok"
    assert ("adb", "reconnect", "offline") in comandos
    assert ("adb", "connect", tela.av.ENDERECO_ADB) in comandos
    assert not (tmp_path / "tela_estado").exists()                       # voltou: nada a registrar


def test_imagem_que_nao_volta_responde_503_e_registra_o_motivo_uma_vez(monkeypatch, tmp_path):
    monkeypatch.setattr(tela, "ESTADO", str(tmp_path / "tela_estado"))
    sem_imagem = (b"", "o Android não conseguiu tirar o print")
    comandos = _prints(monkeypatch, [sem_imagem] * 3)
    gravacoes = []
    original = tela.gravar_estado
    monkeypatch.setattr(tela, "gravar_estado", lambda texto: (gravacoes.append(texto), original(texto)))
    primeira = rodar(tela.tela(Pedido(tela.CHAVE)))
    segunda = rodar(tela.tela(Pedido(tela.CHAVE)))                       # logo depois: não reconecta de novo
    assert primeira.status == segunda.status == 503
    assert len([c for c in comandos if c[:2] == ("adb", "connect")]) == 1
    assert gravacoes == ["enviado; último erro: imagem (o Android não conseguiu tirar o print)"]


def test_imagem_durante_o_reinicio_nao_conta_como_erro(monkeypatch, tmp_path):
    monkeypatch.setattr(tela, "ESTADO", str(tmp_path / "tela_estado"))
    _prints(monkeypatch, [(b"", "adb desconectado (offline)")] * 2)

    class Rodando:
        def done(self):
            return False

    monkeypatch.setitem(tela._reinicio, "tarefa", Rodando())
    assert rodar(tela.tela(Pedido(tela.CHAVE))).status == 503
    assert not (tmp_path / "tela_estado").exists()


def test_print_da_tela_de_verdade_pelo_adb(monkeypatch):
    class Proc:
        returncode = 1

        async def communicate(self):
            return b"", b"error: device offline"

    async def criar(*partes, **kw):
        assert partes == ("adb", "-s", tela.av.ENDERECO_ADB, "exec-out", "screencap", "-p")
        return Proc()

    monkeypatch.setattr(tela.asyncio, "create_subprocess_exec", criar)
    assert rodar(tela.print_da_tela()) == (b"", "adb desconectado (offline)")


def test_pagina_avisa_quando_a_imagem_nao_vem():
    assert "Esperando a imagem do Android" in tela.PAGINA and "A imagem do Android voltou" in tela.PAGINA


def test_reiniciar_que_falha_fica_registrado(monkeypatch, tmp_path):
    monkeypatch.setattr(tela, "ESTADO", str(tmp_path / "tela_estado"))

    async def rodar_comando(*partes, timeout=120):
        return False

    monkeypatch.setattr(tela, "_rodar_comando", rodar_comando)
    assert rodar(tela.reiniciar_android(espera=0)) is False
    assert "reinício RuntimeError" in (tmp_path / "tela_estado").read_text()


def test_botao_reiniciar_nao_empilha_dois_reinicios(monkeypatch):
    async def demora():
        await asyncio.sleep(10)

    async def cenario():
        monkeypatch.setattr(tela, "reiniciar_android", demora)
        monkeypatch.setitem(tela._reinicio, "tarefa", None)
        primeira = await tela.acao(Pedido(tela.CHAVE, {"tipo": "reiniciar"}))
        segunda = await tela.acao(Pedido(tela.CHAVE, {"tipo": "reiniciar"}))
        tela._reinicio["tarefa"].cancel()
        return json.loads(primeira.text)["mensagem"], json.loads(segunda.text)["mensagem"]

    primeira, segunda = rodar(cenario())
    assert "reiniciando o Android" in primeira and "já está reiniciando" in segunda


def test_resetar_desliga_apaga_os_dados_e_liga_do_zero(monkeypatch):
    comandos = []

    async def rodar_comando(*partes, timeout=120):
        comandos.append(partes)
        return True

    async def adb(*partes, timeout=20):
        return b"1"

    monkeypatch.setattr(tela, "_rodar_comando", rodar_comando)
    monkeypatch.setattr(tela, "adb", adb)
    assert rodar(tela.resetar_android(espera=0)) is True
    assert comandos[:3] == [
        ("sudo", "-n", "docker", "stop", tela.av.CONTEINER),
        ("sudo", "-n", "find", tela.av.PASTA_DADOS, "-mindepth", "1", "-delete"),   # a pasta fica, o conteúdo sai
        ("sudo", "-n", "docker", "start", tela.av.CONTEINER),
    ]


def test_resetar_para_no_primeiro_passo_que_falha(monkeypatch, tmp_path):
    monkeypatch.setattr(tela, "ESTADO", str(tmp_path / "tela_estado"))
    comandos = []

    async def rodar_comando(*partes, timeout=120):
        comandos.append(partes)
        return "stop" not in partes                       # o docker stop falha

    monkeypatch.setattr(tela, "_rodar_comando", rodar_comando)
    assert rodar(tela.resetar_android(espera=0)) is False
    assert len(comandos) == 1                             # não apaga nada se não conseguiu desligar
    assert "reset RuntimeError" in (tmp_path / "tela_estado").read_text()


def test_reset_e_reinicio_nao_rodam_juntos(monkeypatch):
    async def demora():
        await asyncio.sleep(10)

    async def cenario():
        monkeypatch.setattr(tela, "reiniciar_android", demora)
        monkeypatch.setattr(tela, "resetar_android", demora)
        monkeypatch.setitem(tela._reinicio, "tarefa", None)
        primeira = await tela.acao(Pedido(tela.CHAVE, {"tipo": "resetar"}))
        segunda = await tela.acao(Pedido(tela.CHAVE, {"tipo": "reiniciar"}))
        tela._reinicio["tarefa"].cancel()
        return json.loads(primeira.text)["mensagem"], json.loads(segunda.text)["mensagem"]

    primeira, segunda = rodar(cenario())
    assert "apagando tudo" in primeira and "já está reiniciando" in segunda


def test_os_tres_botoes_pedem_confirmacao():
    for funcao in ("function fecharApps()", "function reiniciar()", "function resetar()"):
        corpo = tela.PAGINA.split(funcao, 1)[1].split("\nfunction ", 1)[0]
        assert "confirm(" in corpo, funcao
    assert tela.PAGINA.split("function resetar()", 1)[1].split("\nfunction ", 1)[0].count("confirm(") == 2

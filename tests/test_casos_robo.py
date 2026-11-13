"""casos_robo: o caso completo de cada falha do robô da Shopee Vídeo, cifrado para o Claude e apagado depois."""
import json
import os
from datetime import datetime, timedelta

from cryptography.fernet import Fernet

import casos_robo
from fuso import fuso_horario

AGORA = datetime(2026, 10, 25, 10, 0, tzinfo=fuso_horario)
TELA = '<hierarchy><node text="Minhas Curtidas" bounds="[0,0][10,10]"/></hierarchy>'


class Celular:
    """O celular só lendo: a tela, o app e o print (o uiautomator2 grava o PNG no caminho)."""

    def __init__(self, quebrado=False):
        self.quebrado, self.toques = quebrado, []

    def dump_hierarchy(self):
        if self.quebrado:
            raise ConnectionError("caiu")
        return TELA

    def app_current(self):
        return {"package": "com.shopee.br", "activity": "ReactActivity_"}

    def shell(self, partes):
        # Só a leitura de há quanto tempo o app está aberto (pidof e ps do Android).
        return type("R", (), {"output": {"pidof": "4321", "ps": "ELAPSED\n  02:03:04"}.get(partes[0], "")})()

    def screenshot(self, caminho):
        if self.quebrado:
            raise ConnectionError("caiu")
        from PIL import Image
        Image.new("RGB", (1080, 2400), "white").save(caminho)

    def click(self, *ponto):
        self.toques.append(ponto)


def _caso(pasta):
    with open(os.path.join(pasta, "caso.json"), encoding="utf-8") as f:
        return json.load(f)


def test_caso_guarda_o_motivo_o_titulo_os_produtos_o_print_e_a_tela():
    celular = Celular()
    pasta = casos_robo.guardar(
        celular, "rascunho", "pulado", "o produto do vídeo não está na lista", "anexar o produto",
        video={"id": "viral:7", "link": "https://s.shopee.com.br/x", "produto": "Vestido Gatinho"},
        rascunho={"id": 3, "titulo": "Vestido lindo 👗", "comentario": "Amei!", "produtos": ["Vestido Gatinho"],
                  "conferencia": '["vestido"]', "fonte": "viral"}, agora=AGORA)
    caso = _caso(pasta)
    assert (caso["acao"], caso["resultado"], caso["passo"]) == ("rascunho", "pulado", "anexar o produto")
    assert caso["motivo"] == "o produto do vídeo não está na lista" and caso["momento"] == "2026-10-25 10:00:00"
    assert caso["rascunho"]["titulo"] == "Vestido lindo 👗" and caso["rascunho"]["produtos"] == ["Vestido Gatinho"]
    assert caso["video"]["produto"] == "Vestido Gatinho" and caso["app"]["tela"] == "ReactActivity_"
    # Há quantos minutos o app está aberto (08/11: o app instável no começo da noite).
    assert caso["app"]["aberto_ha_min"] == 123
    # O print vai menor, em JPEG, e a forma da tela inteira; nada é tocado no celular.
    from PIL import Image
    with Image.open(os.path.join(pasta, "tela.jpg")) as imagem:
        assert imagem.width == casos_robo.LARGURA_DO_PRINT
    assert not os.path.exists(os.path.join(pasta, "tela.png")) and celular.toques == []
    assert open(os.path.join(pasta, "tela.xml"), encoding="utf-8").read() == TELA
    assert casos_robo.casos() == [os.path.basename(pasta)]


class CelularComLog(Celular):
    """O celular com os processos, o log do Android (logcat) e a versão do app."""

    LOG = [
        "--------- beginning of main",
        "10-25 09:30:00.100  4321  4330 I ReactNativeJS: velho demais",
        "10-25 09:58:10.200  4321  4330 W ReactNativeJS: o produto não entrou",
        "10-25 09:58:11.300  4400  4410 I Push: recebido",
        "10-25 09:58:12.000  5000  5010 I Gmail: outro app",
        "10-25 09:58:13.000  1500  1600 I ActivityTaskManager: START u0 {cmp=com.shopee.br/.Publicar}",
        "linha sem o formato",
    ]

    def shell(self, partes):
        if partes[:2] == ["ps", "-A"]:
            saida = "  PID NAME\n 4321 com.shopee.br\n 4400 com.shopee.br:push\n 5000 com.google.android.gm\n"
        elif partes[0] == "logcat":
            self.leitura_do_log = partes
            saida = "\n".join(self.LOG)
        elif partes[0] == "dumpsys":
            saida = "Packages:\n  Package [com.shopee.br]\n    versionCode=1 minSdk=24\n    versionName=3.61.20\n"
        else:
            return super().shell(partes)
        return type("R", (), {"output": saida})()


class CelularSemMemoria(Celular):
    """O celular com o Java do app perto do teto (a linha Dalvik Heap do dumpsys meminfo, em KB)."""

    def shell(self, partes):
        if partes[:2] == ["dumpsys", "meminfo"]:
            return type("R", (), {"output": "  Dalvik Heap   480000   470000      100     2000   500000   524288"
                                            "   471040    53248\n"})()
        return super().shell(partes)


def test_caso_guarda_a_memoria_do_app():
    # P215 1: às 08:58 e às 21:26 de 12/11, a página do app abriu em branco com o Java dele no teto
    # (512 MB no Motorola). O caso guarda a memória do Java do app, (usada, tamanho) em MB, para a
    # página em branco com a memória abaixo do limite também mostrar quanto o app tinha.
    pasta = casos_robo.guardar(CelularSemMemoria(), "rascunho", "parou", "não achei Criadores & Afiliados na tela",
                               "navegar no app", agora=AGORA)
    assert _caso(pasta)["app"]["memoria_mb"] == [460, 512]
    # Sem a leitura, fica vazia.
    pasta = casos_robo.guardar(Celular(), "rascunho", "parou", "não achei Eu na tela", "navegar no app", agora=AGORA)
    assert _caso(pasta)["app"]["memoria_mb"] is None


def test_caso_guarda_o_log_do_app_dos_ultimos_minutos_e_a_versao(monkeypatch):
    # 09/11, das 13:08 às 13:37: o app não deixou o produto na tela final depois do Feito em 4 vídeos
    # seguidos, sem aviso na tela. O caso guarda o log do Android dos processos do app e as linhas
    # do Android que citam o pacote, dos últimos minutos (nada de outro app nem de antes), e a
    # versão do app.
    pasta = casos_robo.guardar(CelularComLog(), "rascunho", "pulado", "não ficou", "anexar o produto", agora=AGORA)
    caso = _caso(pasta)
    assert caso["app"]["versao"] == "3.61.20" and caso["app"]["log"] == casos_robo.ARQUIVO_DO_LOG
    with open(os.path.join(pasta, casos_robo.ARQUIVO_DO_LOG), encoding="utf-8") as f:
        assert f.read().splitlines() == [CelularComLog.LOG[2], CelularComLog.LOG[3], CelularComLog.LOG[5]]
    # No máximo LINHAS_DO_LOG_DO_APP, as mais novas.
    monkeypatch.setattr(casos_robo, "LINHAS_DO_LOG_DO_APP", 1)
    assert casos_robo.log_do_app(CelularComLog(), "com.shopee.br", AGORA) == CelularComLog.LOG[5]
    # Sem a leitura, o caso fica sem o log e sem a versão.
    pasta = casos_robo.guardar(Celular(), "rascunho", "pulado", "não ficou", "anexar o produto", agora=AGORA)
    caso = _caso(pasta)
    assert caso["app"]["versao"] is None and "log" not in caso["app"]
    assert not os.path.exists(os.path.join(pasta, casos_robo.ARQUIVO_DO_LOG))
    assert casos_robo.log_do_app(object(), "com.shopee.br", AGORA) == ""
    assert casos_robo.versao_do_app(object(), "com.shopee.br") is None


class CelularComACurtida(CelularComLog):
    """O log com a curtida do produto 9 min antes da falha, e uma linha de antes da janela."""

    LOG = ["--------- beginning of main",
           "10-25 09:49:30.000  4321  4330 I ReactNativeJS: antes da janela",
           "10-25 09:51:00.000  4321  4330 I ReactNativeJS: curtiu o produto",
           "10-25 09:58:10.200  4321  4330 W ReactNativeJS: o produto não entrou"]


def test_log_do_app_cobre_a_curtida_de_antes_do_anexar():
    # 10/11, às 07:40: o produto curtido às 07:33 não apareceu no Minhas Curtidas, e o log do caso
    # (6 min) começava às 07:34, depois da curtida. O log cobre os 10 min de antes da falha.
    assert casos_robo.log_do_app(CelularComACurtida(), "com.shopee.br", AGORA).splitlines() == \
        CelularComACurtida.LOG[2:]


class CelularComRepetidas(CelularComLog):
    """O app escrevendo a mesma linha muitas vezes (só os números mudam)."""

    LOG = CelularComLog.LOG[:2] + [
        f"10-25 09:58:{segundo:02d}.{milesimo:03d}  4321  4331 I Rede    : v2:msg invalid, {segundo}, {milesimo}, errno=11"
        for segundo in range(20, 30) for milesimo in (100, 600)
    ] + CelularComLog.LOG[2:]


def test_log_do_app_le_pela_hora_sem_as_linhas_que_se_repetem():
    # 09/11, 22:21: o app escrevia 43 linhas por segundo de "LOOPER msg invalid", e as 400 linhas
    # do caso cobriam só 9 s. O log é lido pela hora (os últimos MINUTOS_DO_LOG_DO_APP), sem as
    # ETIQUETAS_CALADAS, e da linha que se repete (só os números mudam) ficam as primeiras; o fim
    # diz quantas saíram de cada etiqueta.
    celular = CelularComRepetidas()
    linhas = casos_robo.log_do_app(celular, "com.shopee.br", AGORA).splitlines()
    desde = (AGORA - timedelta(minutes=casos_robo.MINUTOS_DO_LOG_DO_APP)).strftime("%m-%d %H:%M:%S")
    assert celular.leitura_do_log == ["logcat", "-d", "-v", "threadtime", "-t", f"{desde}.000"] + [
        f"{etiqueta}:S" for etiqueta in casos_robo.ETIQUETAS_CALADAS]
    repetidas = [linha for linha in linhas if "msg invalid" in linha]
    assert repetidas == CelularComRepetidas.LOG[2:2 + casos_robo.REPETICOES_NO_LOG]
    assert linhas[-1] == f"-- linhas repetidas que saíram: Rede {20 - casos_robo.REPETICOES_NO_LOG}"
    assert CelularComLog.LOG[2] in linhas and CelularComLog.LOG[5] in linhas and CelularComLog.LOG[1] not in linhas


def test_caso_leva_os_passos_do_registro_desde_o_comeco_do_rascunho():
    # 29/10, 22:41: o produto curtido não estava em Minhas Curtidas, e o caso não dizia o que o
    # curtir anotou antes. Os passos do registro do rascunho vão junto (textos fixos e números).
    import registro_processos
    for minuto, processo, resultado in ((50, "curtir o produto", "curtido agora"),     # de outro rascunho
                                        (55, "curtir o produto", "curtido agora"),
                                        (58, "anexar o produto", "nome não achado em Minhas Curtidas")):
        registro_processos.registrar("shopee_video", processo, resultado, "1 rolada(s)",
                                     agora=AGORA - timedelta(minutes=60 - minuto))
    registro_processos.registrar("bot_mestre", "postagem Viral", "postado", agora=AGORA - timedelta(minutes=3))
    pasta = casos_robo.guardar(None, "rascunho", "pulado", "x", "anexar o produto",
                               rascunho={"id": 3, "criado_em": "2026-10-25 09:52:00"}, agora=AGORA)
    assert _caso(pasta)["registro"] == [["09:55:00", "curtir o produto", "curtido agora", "1 rolada(s)"],
                                        ["09:58:00", "anexar o produto", "nome não achado em Minhas Curtidas",
                                         "1 rolada(s)"]]
    # Sem o começo do rascunho, os últimos MINUTOS_DO_REGISTRO.
    pasta = casos_robo.guardar(None, "postar", "parou", "x", agora=AGORA + timedelta(seconds=1))
    assert [linha[0] for linha in _caso(pasta)["registro"]] == ["09:50:00", "09:55:00", "09:58:00"]


TELA_DO_FEITO = ('<hierarchy><node package="com.shopee.br" bounds="[0,0][1080,2400]">'
                 '<node package="com.shopee.br" resource-id="com.shopee.br:id/tv_done" text="Feito" '
                 'bounds="[900,100][1060,180]"/></node></hierarchy>')
# O aviso do Telegram por cima da Shopee, no alto da tela (Motorola, 30/10, 07:35).
TELA_DO_AVISO = TELA_DO_FEITO.replace("</hierarchy>", '<node package="com.android.systemui" text="Telegram" '
                                                      'bounds="[0,0][1080,300]"/></hierarchy>')


def test_caso_guarda_as_ultimas_acoes_com_a_tela_de_antes_e_onde_o_toque_caiu():
    # 30/10: o produto sumiu depois do Feito (06:17) e um toque abriu o Telegram (07:35), e o
    # caso só tinha a tela da falha. O celular da rodada anota as últimas ações, e o caso guarda
    # cada uma com a tela lida logo antes e em que o toque caiu.
    class Real(Celular):
        tela, teclas, apelido = TELA_DO_FEITO, [], "motorola"

        def dump_hierarchy(self):
            return self.tela

        def press(self, tecla):
            self.teclas.append(tecla)

    real = Real()
    d = casos_robo.com_historico(real)
    assert casos_robo.com_historico(d) is d
    d.dump_hierarchy()
    d.click(980, 140)
    d.press("back")
    real.tela = TELA_DO_AVISO
    d.dump_hierarchy()
    d.click(500, 200)
    # Tudo passa direto para o celular: os toques, as teclas e o resto.
    assert real.toques == [(980, 140), (500, 200)] and real.teclas == ["back"]
    assert d.apelido == "motorola" and d.app_current()["package"] == "com.shopee.br"
    pasta = casos_robo.guardar(d, "rascunho", "parou", "x", agora=AGORA)
    antes = _caso(pasta)["antes_da_falha"]
    assert [a["acao"] for a in antes] == ["toque em (980,140)", "tecla back", "toque em (500,200)"]
    assert antes[0]["caiu_em"] == 'com.shopee.br id=tv_done "Feito"'
    assert antes[2]["caiu_em"] == 'com.android.systemui "Telegram"' and "caiu_em" not in antes[1]
    assert open(os.path.join(pasta, antes[2]["tela"]), encoding="utf-8").read() == TELA_DO_AVISO
    # Ficam só as últimas ACOES_DO_CASO; o celular de antes (sem anotar) segue sem elas.
    for _ in range(casos_robo.ACOES_DO_CASO + 3):
        d.click(1, 1)
    assert len(d.acoes) == casos_robo.ACOES_DO_CASO
    assert "antes_da_falha" not in _caso(casos_robo.guardar(real, "postar", "parou", "x",
                                                            agora=AGORA + timedelta(seconds=1)))
    assert casos_robo.elemento_no_ponto("<quebrado", 1, 1) == "" and casos_robo.elemento_no_ponto(TELA, 50, 50) == ""


def test_caso_guarda_a_tela_anotada_sem_toque():
    # 07/11: o caso do produto que não ficou depois do Feito só tinha a tela de 30 s depois. A tela
    # lida logo depois do toque entra entre as ações, com o arquivo dela e sem "caiu_em".
    celular = Celular()
    d = casos_robo.com_historico(celular)
    d.dump_hierarchy()
    d.click(10, 10)
    d.dump_hierarchy()
    casos_robo.anotar_tela(d, "tela logo depois do Feito")
    casos_robo.anotar_tela(celular, "nada")                    # o celular sem o histórico: nada
    assert celular.toques == [(10, 10)]
    pasta = casos_robo.guardar(d, "rascunho", "pulado", "x", agora=AGORA)
    antes = _caso(pasta)["antes_da_falha"]
    assert [a["acao"] for a in antes] == ["toque em (10,10)", "tela logo depois do Feito"]
    assert "caiu_em" not in antes[1] and open(os.path.join(pasta, antes[1]["tela"]), encoding="utf-8").read() == TELA


def test_a_leitura_que_a_conexao_derruba_e_feita_mais_uma_vez(monkeypatch):
    # 09/11, 04:22: o servidor do uiautomator2 fechou a conexão no meio da leitura da tela
    # (RemoteDisconnected), e o feed acabou em erro inesperado. A leitura vai mais uma vez e
    # fica no registro; caída de novo, o erro segue para a rodada. O toque nunca se repete.
    from http.client import RemoteDisconnected

    import pytest
    import registro_processos
    monkeypatch.setattr(casos_robo, "ESPERA_DA_RELEITURA", 0)

    class Instavel(Celular):
        quedas = 1

        def dump_hierarchy(self):
            if self.quedas:
                self.quedas -= 1
                raise RemoteDisconnected("Remote end closed connection without response")
            return TELA

        def click(self, *ponto):
            self.toques.append(ponto)
            raise RemoteDisconnected("caiu")

    celular = Instavel()
    d = casos_robo.com_historico(celular)
    assert d.dump_hierarchy() == TELA
    linhas = registro_processos.sequencia("shopee_video", "leitura da tela", "2000-01-01 00:00:00")
    assert [(linha[2], linha[3]) for linha in linhas] == [
        ("a conexão com o celular caiu", "lida de novo (RemoteDisconnected)")]
    celular.quedas = 2
    with pytest.raises(RemoteDisconnected):
        d.dump_hierarchy()
    with pytest.raises(RemoteDisconnected):
        d.click(5, 5)
    assert celular.toques == [(5, 5)]


def test_caso_sem_celular_ou_com_o_celular_caido_nao_derruba_a_rodada():
    pasta = casos_robo.guardar(Celular(quebrado=True), "rascunho", "erro", "erro inesperado (ConnectionError)",
                               agora=AGORA)
    assert _caso(pasta)["app"]["sem_print"] == "ConnectionError"
    assert casos_robo.guardar(None, "postar", "parou", "x", agora=AGORA + timedelta(seconds=1))
    # Sem nem a pasta para gravar: devolve None, sem erro.
    import pytest
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(casos_robo.os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(PermissionError()))
        assert casos_robo.guardar(None, "postar", "parou", "x", agora=AGORA) is None


def test_nada_acumula_mais_de_30_casos_nem_mais_de_3_dias():
    for minuto in range(casos_robo.MAXIMO_DE_CASOS + 5):
        casos_robo.guardar(None, "rascunho", "parou", "x", agora=AGORA + timedelta(minutes=minuto))
    lista = casos_robo.casos()
    assert len(lista) == casos_robo.MAXIMO_DE_CASOS and lista[0].startswith("20261025-1005")
    casos_robo.guardar(None, "rascunho", "parou", "x", agora=AGORA + timedelta(days=4))
    assert len(casos_robo.casos()) == 1


def test_pacote_cifrado_abre_com_a_chave_e_apagar_tira_tudo(monkeypatch, tmp_path):
    import registro_privado
    chave = Fernet.generate_key()
    monkeypatch.setattr(registro_privado, "chave", lambda: chave)
    casos_robo.guardar(Celular(), "rascunho", "pulado", "motivo com Vestido Gatinho",
                       rascunho={"titulo": "Vestido lindo"}, agora=AGORA)
    texto = casos_robo.cifrado()
    assert texto.startswith("gAAAAA") and "Vestido" not in texto
    nomes = casos_robo.abrir(texto, chave.decode("ascii"), str(tmp_path / "aberto"))
    assert len(nomes) == 1 and _caso(str(tmp_path / "aberto" / nomes[0]))["rascunho"]["titulo"] == "Vestido lindo"
    assert casos_robo.apagar() == 1 and casos_robo.casos() == [] and not os.path.exists(casos_robo.PASTA)


def test_apagar_tira_so_os_casos_ate_o_mais_novo_da_exportacao(capsys):
    # Em 06/11, um caso guardado depois da exportação foi apagado sem o Claude ver: o apagar
    # tira só até o mais novo do pacote (o nome vai no ramo), e o que chegou depois fica.
    for minuto in range(3):
        casos_robo.guardar(None, "rascunho", "parou", "x", agora=AGORA + timedelta(minutes=minuto))
    exportado = casos_robo.ultimo()
    assert exportado == casos_robo.casos()[-1] and exportado.startswith("20261025-1002")
    casos_robo.guardar(None, "rascunho", "pulado", "x", agora=AGORA + timedelta(minutes=30))
    novo = casos_robo.casos()[-1]
    assert casos_robo.main(["apagar", exportado]) == 0
    assert capsys.readouterr().out.strip() == ("3 caso(s) apagado(s) do servidor; 1 mais novo(s) que a "
                                               "exportação ficam para a próxima.")
    assert casos_robo.casos() == [novo]
    assert casos_robo.apagar(novo) == 1 and casos_robo.casos() == [] and not os.path.exists(casos_robo.PASTA)
    assert casos_robo.ultimo() == ""
    # Só o nome de um caso: outra coisa no lugar dele não apaga nada.
    casos_robo.guardar(None, "rascunho", "parou", "x", agora=AGORA)
    assert casos_robo.main(["apagar", "../outra"]) == 2 and len(casos_robo.casos()) == 1


def test_linha_de_comando(capsys, monkeypatch, tmp_path):
    import registro_privado
    chave = Fernet.generate_key()
    monkeypatch.setattr(registro_privado, "chave", lambda: chave)
    casos_robo.guardar(None, "rascunho", "parou", "x", agora=AGORA)
    assert casos_robo.main(["contar"]) == 0 and capsys.readouterr().out.strip() == "1"
    assert casos_robo.main(["cifrado"]) == 0
    arquivo = tmp_path / "casos.zip.cifrado"
    arquivo.write_text(capsys.readouterr().out.strip())
    monkeypatch.setenv(registro_privado.VARIAVEL_CHAVE, chave.decode("ascii"))
    assert casos_robo.main(["ler", str(arquivo), str(tmp_path / "abertos")]) == 0
    assert "1 caso(s)" in capsys.readouterr().out
    monkeypatch.setenv(registro_privado.VARIAVEL_CHAVE, Fernet.generate_key().decode("ascii"))
    assert casos_robo.main(["ler", str(arquivo), str(tmp_path / "outra")]) == 1
    assert casos_robo.main(["apagar"]) == 0 and "1 caso(s) apagado(s)" in capsys.readouterr().out
    assert casos_robo.main([]) == 2

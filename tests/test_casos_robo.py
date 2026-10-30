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
    # O print vai menor, em JPEG, e a forma da tela inteira; nada é tocado no celular.
    from PIL import Image
    with Image.open(os.path.join(pasta, "tela.jpg")) as imagem:
        assert imagem.width == casos_robo.LARGURA_DO_PRINT
    assert not os.path.exists(os.path.join(pasta, "tela.png")) and celular.toques == []
    assert open(os.path.join(pasta, "tela.xml"), encoding="utf-8").read() == TELA
    assert casos_robo.casos() == [os.path.basename(pasta)]


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

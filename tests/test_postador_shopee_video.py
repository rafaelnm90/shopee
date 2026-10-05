"""Exploração das telas do app da Shopee (postador_shopee_video): forma da tela sem os dados da conta, toques e passos."""
import os

import pytest

import postador_shopee_video as ps
from conftest import inserir

TELA_EU = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node text="" class="android.widget.FrameLayout" bounds="[0,0][720,1280]" clickable="false">
    <node text="ContaDoRafael.Oficial" resource-id="com.shopee.br:id/nome" class="android.widget.TextView"
          bounds="[100,50][400,90]" />
    <node text="2mil Seguidores" class="android.widget.TextView" bounds="[100,100][300,130]" />
    <node text="" content-desc="Criadores &amp; Afiliados" class="android.view.ViewGroup" clickable="true"
          bounds="[360,700][700,780]" />
    <node text="Postar vídeo" class="android.widget.Button" clickable="true" bounds="[500,1100][700,1180]" />
    <node text="Postar" class="android.widget.Button" clickable="true" bounds="[200,1200][520,1260]" />
    <node text="Reutilização" class="android.widget.Switch" checked="true" bounds="[600,300][700,340]" />
    <node text="sem tamanho" class="android.widget.TextView" bounds="[0,0][0,0]" />
    <node text="escondido" class="android.widget.TextView" bounds="[0,0][10,10]" visible-to-user="false" />
  </node>
</hierarchy>"""


class Resposta:
    def __init__(self, output=""):
        self.output = output


class Aparelho:
    """O Android de mentira: guarda os toques, as teclas e os comandos."""

    def __init__(self, tela=TELA_EU, galeria=""):
        self.tela, self.galeria = tela, galeria
        self.toques, self.teclas, self.comandos, self.enviados, self.escrito = [], [], [], [], []

    def dump_hierarchy(self):
        return self.tela

    def click(self, x, y):
        self.toques.append((x, y))

    def press(self, tecla):
        self.teclas.append(tecla)

    def app_start(self, pacote, wait=False):
        self.comandos.append(["abrir", pacote])

    def app_stop(self, pacote):
        self.comandos.append(["fechar", pacote])

    def app_current(self):
        return {"package": "com.shopee.br", "activity": "com.shopee.app.ui.home.HomeActivity"}

    def window_size(self):
        return 720, 1280

    def swipe(self, *pontos):
        self.comandos.append(["rolar", *pontos])

    def send_keys(self, texto):
        self.escrito.append(texto)

    def shell(self, partes):
        self.comandos.append(partes)
        return Resposta(self.galeria if "content" in partes else "")

    def push(self, origem, destino):
        self.enviados.append((origem, destino))


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)


@pytest.mark.parametrize("texto, forma", [
    ("ContaDoRafael.Oficial", "…"),
    ("Postar vídeo", "Postar vídeo"),
    ("Ver Produtos (3)", "Ver Produtos (#)"),
    ("Taxa de comissão 1.5%", "Taxa de comissão #.#%"),
    ("R$749,90", "R$#,#"),
    ("Rafael Novais de Miranda", "… de …"),
    ("2mil Seguidores", "… Seguidores"),
    ("Criadores & Afiliados 🛍️", "Criadores & Afiliados 🛍️"),
    ("", ""),
])
def test_mascara_tira_o_que_nao_e_botao(texto, forma):
    assert ps.mascarar(texto) == forma


def test_descricao_tem_os_botoes_e_nao_tem_a_conta():
    linhas = ps.descrever(TELA_EU)
    texto = "\n".join(linhas)
    assert "ContaDoRafael" not in texto and "2mil" not in texto
    assert '(600,1140) Button "Postar vídeo" [toque]' in linhas[3]
    assert 'desc="Criadores & Afiliados"' in texto and "id=nome" in texto
    assert "[ligado]" in texto
    assert "sem tamanho" not in texto and "escondido" not in texto


def test_acha_igual_antes_de_parecido():
    assert ps.achar(TELA_EU, "Postar") == (360, 1230)
    assert ps.achar(TELA_EU, "postar VÍDEO") == (600, 1140)
    assert ps.achar(TELA_EU, "Criadores") == (530, 740)
    assert ps.achar(TELA_EU, "@nome") == (250, 70)
    assert ps.achar(TELA_EU, "Comprar") is None
    assert ps.achar("isso não é xml", "Postar") is None


def test_explorar_toca_e_descreve_cada_tela(capsys):
    aparelho = Aparelho()
    assert ps.explorar("abrir; tocar:Postar vídeo; voltar", aparelho)
    saida = capsys.readouterr().out
    assert aparelho.toques == [(600, 1140)] and aparelho.teclas == ["back"]
    assert ["abrir", ps.PACOTE] in aparelho.comandos
    assert "== passo 2: tocar:Postar vídeo → tocado em (600, 1140)" in saida
    assert "tela: HomeActivity" in saida
    assert "ContaDoRafael" not in saida


@pytest.mark.parametrize("passo", ["tocar:Postar", "tocar: postar ", "tocar:POSTAR"])
def test_explorar_nunca_toca_em_postar(passo, capsys):
    aparelho = Aparelho()
    assert not ps.explorar(passo, aparelho)
    assert aparelho.toques == []
    assert "nunca toca em Postar" in capsys.readouterr().out


def test_passo_desconhecido_nao_toca_em_nada(capsys):
    aparelho = Aparelho()
    assert not ps.explorar("abrir; publicar", aparelho)
    assert aparelho.comandos == [] and "passo desconhecido: publicar" in capsys.readouterr().out


def test_para_no_primeiro_passo_que_falha(capsys):
    aparelho = Aparelho()
    assert not ps.explorar("tocar:Comprar; voltar", aparelho)
    assert aparelho.teclas == [] and "não achei na tela" in capsys.readouterr().out


def test_erro_no_passo_mostra_so_o_tipo(capsys):
    class Quebrado(Aparelho):
        def click(self, x, y):
            raise RuntimeError("segredo do aparelho")

    assert not ps.explorar("xy:10,20", Quebrado())
    saida = capsys.readouterr().out
    assert "erro: RuntimeError" in saida and "segredo" not in saida


def test_rolar_escrever_e_teclas():
    aparelho = Aparelho()
    assert ps.explorar("rolar:baixo; rolar:cima; escrever:teste; inicio; esperar:2; tela", aparelho)
    assert ["rolar", 360, 960, 360, 384, 0.4] in aparelho.comandos
    assert ["rolar", 360, 384, 360, 960, 0.4] in aparelho.comandos
    assert aparelho.escrito == ["teste"] and aparelho.teclas == ["home"]


def _autorais():
    inserir("CREATE TABLE fila_autorais (id_unico TEXT PRIMARY KEY, legenda TEXT, caminho_arquivo TEXT, "
            "data_captura TEXT)")
    with open("archive/antigo.mp4", "wb") as f:
        f.write(b"video")
    inserir("INSERT INTO fila_autorais VALUES ('novo', 'Link: https://s.shopee.com.br/novo', "
            "'archive/sumiu.mp4', '2026-10-05 10:00')")
    inserir("INSERT INTO fila_autorais VALUES ('antigo', '<b>Produto</b>\n🔗 https://s.shopee.com.br/abc\n#tag', "
            "'archive/antigo.mp4', '2026-10-04 10:00')")


def test_ultimo_autoral_pula_o_que_perdeu_o_arquivo():
    assert ps.ultimo_autoral() == (None, None)
    _autorais()
    arquivo, link = ps.ultimo_autoral()
    assert arquivo == os.path.abspath("archive/antigo.mp4") and link == "https://s.shopee.com.br/abc"


def test_link_abre_o_produto_no_app_sem_mostrar_o_endereco(monkeypatch, capsys):
    _autorais()

    async def converter(link):
        assert link == "https://s.shopee.com.br/abc"
        return "https://shopee.com.br/product/11/22"

    monkeypatch.setattr(ps, "link_para_converter", converter)
    aparelho = Aparelho()
    assert ps.explorar("link", aparelho)
    assert ["am", "start", "-a", "android.intent.action.VIEW", "-d", "https://shopee.com.br/product/11/22",
            "-p", ps.PACOTE] in aparelho.comandos
    saida = capsys.readouterr().out
    assert "aberto: produto" in saida and "shopee.com.br/product" not in saida


def test_video_vai_para_a_galeria():
    _autorais()
    aparelho = Aparelho(galeria=f"Row: 0 _display_name={ps.NOME_NA_GALERIA}")
    assert ps.explorar("video", aparelho)
    assert aparelho.enviados == [(os.path.abspath("archive/antigo.mp4"), f"{ps.GALERIA}/{ps.NOME_NA_GALERIA}")]
    assert not ps.explorar("video", Aparelho(galeria=""))


def test_sem_autorais_o_link_e_o_video_falham(capsys):
    assert not ps.explorar("video", Aparelho())
    assert "nenhum vídeo dos Autorais" in capsys.readouterr().out


def test_android_desligado_nem_conecta(monkeypatch, capsys):
    monkeypatch.setattr(ps.av, "android_ligado", lambda: False)
    monkeypatch.setattr(ps, "conectar", lambda: pytest.fail("não devia conectar"))
    assert not ps.explorar("tela")
    assert "android: desligado" in capsys.readouterr().out

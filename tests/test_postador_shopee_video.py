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
    <node text="12:00" resource-id="com.android.systemui:id/clock" package="com.android.systemui"
          class="android.widget.TextView" bounds="[0,0][100,40]" />
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

    def screenshot(self, caminho):
        self.print = caminho
        with open(caminho, "wb") as f:
            f.write(b"png")


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
    assert "clock" not in texto and ps.achar(TELA_EU, "@clock") is None


def test_id_que_e_endereco_nao_vai_para_o_log():
    tela = """<hierarchy><node class="android.widget.FrameLayout" bounds="[0,0][720,1280]">
      <node resource-id="_https://cf.shopee.com.br/file/br-11134207-abc_tn_mainpic" class="android.widget.ImageView"
            bounds="[0,0][300,300]" />
      <node resource-id="com.shopee.br:id/buttonActionBarBack" class="android.view.ViewGroup" clickable="true"
            bounds="[0,0][100,100]" />
    </node></hierarchy>"""
    linhas = "\n".join(ps.descrever(tela))
    assert "https" not in linhas and "cf.shopee" not in linhas and "id=…" in linhas
    assert "id=buttonActionBarBack" in linhas


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


TELA_PRODUTO = """<hierarchy><node class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">
  <node resource-id="com.shopee.br:id/buttonItemLike" class="android.widget.ImageView"
        bounds="[1000,1205][1056,1261]" />
  <node resource-id="com.shopee.br:id/buttonProductAddCart" class="android.view.ViewGroup" clickable="true"
        bounds="[270,2262][540,2400]" />
  <node resource-id="com.shopee.br:id/buttonProductBuyNow" class="android.view.ViewGroup" clickable="true"
        bounds="[540,2262][1080,2400]">
    <node text="Compre agora" class="android.widget.TextView" bounds="[700,2300][920,2360]" />
  </node>
</node></hierarchy>"""


@pytest.mark.parametrize("passo", ["tocar:Compre agora", "tocar:Compre", "tocar:@buttonProductBuyNow",
                                   "tocar:@buttonProductAddCart", "tocar:@btn_post", "xy:810,2331",
                                   "xy:400,2300"])
def test_explorar_nunca_toca_nos_botoes_de_comprar(passo, capsys):
    aparelho = Aparelho(tela=TELA_PRODUTO)
    assert not ps.explorar(passo, aparelho)
    assert aparelho.toques == []
    assert "nunca toca em Postar nem nos botões de comprar" in capsys.readouterr().out


def test_curtir_toca_so_no_coracao():
    aparelho = Aparelho(tela=TELA_PRODUTO)
    assert ps.explorar("tocar:@buttonItemLike", aparelho)
    assert aparelho.toques == [(1028, 1233)]


def test_passo_desconhecido_nao_toca_em_nada(capsys):
    aparelho = Aparelho()
    assert ps.explorar("abrir; publicar", aparelho) is None
    assert aparelho.comandos == [] and "passo desconhecido: publicar" in capsys.readouterr().out


def test_para_no_primeiro_passo_que_falha(capsys):
    aparelho = Aparelho()
    assert ps.explorar("tocar:Comprar; voltar", aparelho) is False
    assert aparelho.teclas == [] and "não achei na tela" in capsys.readouterr().out


TELA_VERIFICACAO = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node text="" class="android.widget.FrameLayout" bounds="[0,0][720,1280]">
    <node text="Verificação" resource-id="com.shopee.br:id/title_text" class="android.widget.TextView"
          clickable="true" bounds="[200,100][500,160]" />
    <node text="" resource-id="NEW_CAPTCHA" class="android.view.View" bounds="[0,300][720,900]" />
    <node text="Atualizar CAPTCHA" class="android.widget.Button" clickable="true" bounds="[500,700][600,760]" />
  </node>
</hierarchy>"""


def test_verificacao_antes_do_primeiro_passo_nao_toca_em_nada(capsys):
    aparelho = Aparelho(tela=TELA_VERIFICACAO)
    assert ps.explorar("voltar; xy:300,600; tocar:Atualizar", aparelho) is False
    assert aparelho.toques == [] and aparelho.teclas == []
    assert "o Rafael resolve com a mão" in capsys.readouterr().out


def test_verificacao_depois_de_um_passo_para_ali(capsys):
    class VaiParaVerificacao(Aparelho):
        def app_start(self, pacote, wait=False):
            super().app_start(pacote, wait)
            self.tela = TELA_VERIFICACAO

    aparelho = VaiParaVerificacao()
    assert ps.explorar("abrir; voltar; tocar:Atualizar", aparelho) is False
    saida = capsys.readouterr().out
    assert aparelho.teclas == [] and aparelho.toques == []
    assert "== passo 1: abrir" in saida and "passo 2" not in saida and "o Rafael resolve com a mão" in saida
    assert ps.codigo_de_saida(False) == 0                                # resposta da exploração, não erro


def test_tela_comum_nao_e_verificacao():
    assert not ps.eh_verificacao(TELA_EU) and ps.eh_verificacao(TELA_VERIFICACAO)


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
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    inserir("CREATE TABLE fila_autorais (id_unico TEXT PRIMARY KEY, legenda TEXT, caminho_arquivo TEXT, "
            "data_captura TEXT)")
    with open("archive/antigo.mp4", "wb") as f:
        f.write(b"video")
    inserir("INSERT INTO fila_autorais VALUES ('novo', 'Link: https://s.shopee.com.br/novo', "
            "'archive/sumiu.mp4', '2026-10-05 10:00')")
    inserir("INSERT INTO fila_autorais VALUES ('antigo', '<b>Produto</b>\n🔗 https://s.shopee.com.br/abc\n#tag', "
            "'archive/antigo.mp4', '2026-10-04 10:00')")


def test_video_da_fonte_pula_o_que_perdeu_o_arquivo():
    assert ps.video_da_fonte() is None
    _autorais()
    video = ps.video_da_fonte()
    assert video["arquivo"] == os.path.abspath("archive/antigo.mp4") and video["link"] == "https://s.shopee.com.br/abc"
    assert video["id"] == "antigo" and video["nome"] == "Produto"


def test_video_da_fonte_segue_a_fonte_do_painel():
    _autorais()
    import db
    db.salvar_config("fila_clonagem", {"fila": [{"id": 7, "caminho_video": "archive/viral.mp4",
                                                 "link_original": "https://s.shopee.com.br/viral",
                                                 "data_captura": "2026-10-17 10:00"}]})
    with open("archive/viral.mp4", "wb") as f:
        f.write(b"video")
    db.salvar_config(ps.CHAVE_PAINEL, {"fonte": "viral"})
    video = ps.video_da_fonte()
    assert (video["arquivo"], video["link"]) == (os.path.abspath("archive/viral.mp4"), "https://s.shopee.com.br/viral")


def test_link_e_titulo_usam_o_video_escolhido_no_passo_video():
    _autorais()
    assert ps.explorar("video", Aparelho(galeria=f"Row: 0 _display_name={ps.NOME_NA_GALERIA}"))
    with open("archive/mais_novo.mp4", "wb") as f:
        f.write(b"video")
    inserir("INSERT INTO fila_autorais VALUES ('mais_novo', 'Link: https://s.shopee.com.br/outro', "
            "'archive/mais_novo.mp4', '2026-10-06 10:00')")
    assert ps.video_do_teste()["id"] == "antigo"
    assert ps.video_do_teste(novo=True)["id"] == "mais_novo"
    os.remove("archive/mais_novo.mp4")
    assert ps.video_do_teste()["id"] == "antigo"


def test_titulo_da_ia_vai_para_o_campo_e_o_log_mostra_so_o_tamanho(monkeypatch, capsys):
    _autorais()
    pedidos = []

    async def textos(arquivo, nome):
        pedidos.append((arquivo, nome))
        return {"violacao": False, "motivo": "", "titulo": "Garrafa térmica inox 1 litro", "comentario": "x"}

    monkeypatch.setattr(ps.assistente, "textos_do_video", textos)
    aparelho = Aparelho()
    assert ps.explorar("titulo", aparelho)
    assert aparelho.escrito == ["Garrafa térmica inox 1 litro"]
    assert pedidos == [(os.path.abspath("archive/antigo.mp4"), "Produto")]
    saida = capsys.readouterr().out
    assert "título com 28 caracteres" in saida and "Garrafa" not in saida


def test_titulo_com_violacao_nao_e_escrito(monkeypatch, capsys):
    _autorais()

    async def textos(arquivo, nome):
        return {"violacao": True, "motivo": "marca", "titulo": "", "comentario": ""}

    monkeypatch.setattr(ps.assistente, "textos_do_video", textos)
    aparelho = Aparelho()
    assert not ps.explorar("titulo", aparelho)
    assert aparelho.escrito == [] and "violação" in capsys.readouterr().out


def test_print_vai_so_para_o_privado_e_o_arquivo_sai(monkeypatch, capsys):
    mandados = []

    def mandar_foto(caminho, legenda=""):
        with open(caminho, "rb") as f:
            mandados.append(f.read())
        return True

    monkeypatch.setattr(ps.avisar_rafael, "mandar_foto", mandar_foto)
    aparelho = Aparelho()
    assert ps.explorar("print", aparelho)
    assert mandados == [b"png"] and not os.path.exists(aparelho.print)
    assert "print mandado no privado" in capsys.readouterr().out
    monkeypatch.setattr(ps.avisar_rafael, "mandar_foto", lambda caminho, legenda="": False)
    assert not ps.explorar("print", aparelho) and not os.path.exists(aparelho.print)


def test_link_abre_o_link_do_video_como_veio_sem_mostrar_o_endereco(monkeypatch, capsys):
    _autorais()

    async def converter(link):
        assert link == "https://s.shopee.com.br/abc"
        return "https://shopee.com.br/product/11/22"

    monkeypatch.setattr(ps, "link_para_converter", converter)
    aparelho = Aparelho()
    assert ps.explorar("link", aparelho)
    assert ["am", "start", "-a", "android.intent.action.VIEW", "-d", "https://s.shopee.com.br/abc",
            "-p", ps.PACOTE] in aparelho.comandos
    assert not any("shopee.com.br/product" in parte for comando in aparelho.comandos for parte in comando)
    saida = capsys.readouterr().out
    assert "aberto: produto" in saida and "shopee.com.br" not in saida


def test_video_vai_para_a_galeria():
    _autorais()
    aparelho = Aparelho(galeria=f"Row: 0 _display_name={ps.NOME_NA_GALERIA}")
    assert ps.explorar("video", aparelho)
    assert aparelho.enviados == [(os.path.abspath("archive/antigo.mp4"), f"{ps.GALERIA}/{ps.NOME_NA_GALERIA}")]
    assert not ps.explorar("video", Aparelho(galeria=""))


def test_sem_video_na_fonte_o_link_e_o_video_falham(capsys):
    assert not ps.explorar("video", Aparelho())
    assert "nenhum vídeo da fonte do painel" in capsys.readouterr().out


def test_android_desligado_nem_conecta(monkeypatch, capsys):
    monkeypatch.setattr(ps.av, "android_ligado", lambda: False)
    monkeypatch.setattr(ps, "conectar", lambda: pytest.fail("não devia conectar"))
    assert ps.explorar("tela") is None
    assert "android: desligado" in capsys.readouterr().out


@pytest.mark.parametrize("hora, comeca", [("07:59", False), ("08:00", True), ("21:59", True), ("22:00", False),
                                         ("03:00", False)])
def test_no_celular_so_das_8h_as_22h(hora, comeca, relogio, monkeypatch, capsys):
    relogio(hora)
    aparelho = Aparelho()
    monkeypatch.setattr(ps.celular_robo, "conectado", lambda: True)
    monkeypatch.setattr(ps, "conectar", lambda celular: aparelho)
    assert ps.explorar("xy:10,20", celular=True) is (True if comeca else None)
    assert aparelho.toques == ([(10, 20)] if comeca else [])
    assert ("fora do horário das rodadas" in capsys.readouterr().out) is not comeca


def test_so_fica_vermelho_quando_nem_comecou():
    assert ps.codigo_de_saida(True) == 0
    assert ps.codigo_de_saida(False) == 0
    assert ps.codigo_de_saida(None) == 1

"""Exploração das telas do app da Shopee (postador_shopee_video): forma da tela sem os dados da conta, toques e passos."""
import logging
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


def test_verificacao_no_celular_manda_a_tela_no_privado(monkeypatch, capsys):
    abertas = []
    monkeypatch.setattr(ps.av, "abrir_tela", lambda celular=False, verificacao=False:
                        abertas.append((celular, verificacao)) or True)
    aparelho = Aparelho(tela=TELA_VERIFICACAO)
    assert ps.explorar("voltar", aparelho, celular=True) is False
    assert abertas == [(True, True)] and aparelho.teclas == []
    assert not ps.explorar("voltar", Aparelho(tela=TELA_VERIFICACAO))  # no Android virtual, só para
    assert abertas == [(True, True)]


def test_com_a_tela_do_celular_aberta_o_robo_nao_mexe(relogio, monkeypatch, capsys):
    relogio("15:00")
    monkeypatch.setattr(ps.celular_robo, "conectado", lambda: True)
    monkeypatch.setattr(ps.av, "tela_aberta", lambda: True)
    monkeypatch.setattr(ps, "conectar", lambda celular: pytest.fail("não devia conectar"))
    assert ps.explorar("xy:10,20", celular=True) is None
    assert "tela do celular está aberta" in capsys.readouterr().out


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


def test_passo_video_usa_o_video_guardado_e_so_video_novo_troca(monkeypatch):
    _autorais()

    async def converter(link):
        return "https://shopee.com.br/product/11/22"

    monkeypatch.setattr(ps, "link_para_converter", converter)
    assert ps.explorar("link", Aparelho())
    with open("archive/mais_novo.mp4", "wb") as f:
        f.write(b"video")
    inserir("INSERT INTO fila_autorais VALUES ('mais_novo', 'Link: https://s.shopee.com.br/outro', "
            "'archive/mais_novo.mp4', '2026-10-06 10:00')")
    galeria = f"Row: 0 _display_name={ps.NOME_NA_GALERIA}"
    aparelho = Aparelho(galeria=galeria)
    assert ps.explorar("video", aparelho)
    assert aparelho.enviados[0][0] == os.path.abspath("archive/antigo.mp4")
    aparelho = Aparelho(galeria=galeria)
    assert ps.explorar("video:novo", aparelho)
    assert aparelho.enviados[0][0] == os.path.abspath("archive/mais_novo.mp4")


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


def test_comentario_da_ia_vai_so_para_o_privado_com_o_lembrete(monkeypatch, capsys):
    _autorais()

    async def textos(arquivo, nome):
        return {"violacao": False, "motivo": "", "titulo": "Garrafa térmica inox 1 litro",
                "comentario": "Amei essa garrafa! #achadinhos"}

    monkeypatch.setattr(ps.assistente, "textos_do_video", textos)
    avisos = []
    monkeypatch.setattr(ps.avisar_rafael, "mandar_texto", lambda texto: avisos.append(texto) or True)
    assert not ps.explorar("comentario", Aparelho())
    assert avisos == [] and "o passo titulo vem antes" in capsys.readouterr().out
    assert ps.explorar("titulo; comentario", Aparelho())
    assert len(avisos) == 1 and "Amei essa garrafa! #achadinhos" in avisos[0]
    assert "curta o vídeo e comente" in avisos[0]
    saida = capsys.readouterr().out
    assert "comentário com 30 caracteres" in saida and "Amei" not in saida


def test_log_da_ia_nao_vai_para_o_log_publico(monkeypatch, capsys, caplog):
    _autorais()

    async def textos(arquivo, nome):
        logging.getLogger("httpx").warning("HTTP Request: POST /upload?upload_id=SESSAO")
        logging.getLogger("API_Gemini").error("falha com SESSAO")
        return {"violacao": False, "motivo": "", "titulo": "Garrafa", "comentario": "x"}

    monkeypatch.setattr(ps.assistente, "textos_do_video", textos)
    assert ps.explorar("titulo", Aparelho())
    saida = capsys.readouterr()
    assert "SESSAO" not in saida.out + saida.err + caplog.text
    assert logging.getLogger("API_Gemini").isEnabledFor(logging.ERROR)


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


TELA_CURTIDAS = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node text="" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]" clickable="false">
    <node text="Adicionar Produto" class="android.widget.TextView" bounds="[400,150][740,200]" />
    <node text="Minhas Curtidas" class="android.view.ViewGroup" clickable="true" bounds="[300,410][510,460]" />
    <node text="" class="android.widget.ScrollView" clickable="true" bounds="[0,700][1080,2400]">
      <node text="" class="android.view.ViewGroup" clickable="true" bounds="[0,780][1080,1055]">
        <node text="Fibra Proteína Cabelo Cacheado Luxo" class="android.widget.TextView"
              bounds="[300,770][1040,830]" />
        <node text="R$125,32" class="android.widget.TextView" bounds="[300,970][430,1010]" />
        <node text="" class="android.view.ViewGroup" clickable="true" bounds="[840,945][1010,1010]">
          <node text="Adicionar" class="android.widget.TextView" bounds="[850,955][1000,1000]" />
        </node>
      </node>
      <node text="" class="android.view.ViewGroup" clickable="true" bounds="[0,1060][1080,1330]">
        <node text="Vestido Infantil Estampado Gatinho Para Meninas de 4 a 14 Anos"
              class="android.widget.TextView" bounds="[300,1070][1040,1130]" />
        <node text="R$59,90" class="android.widget.TextView" bounds="[300,1250][430,1290]" />
        <node text="" class="android.view.ViewGroup" clickable="true" bounds="[840,1225][1010,1290]">
          <node text="Adicionar" class="android.widget.TextView" bounds="[850,1235][1000,1280]" />
        </node>
      </node>
    </node>
  </node>
</hierarchy>"""
VESTIDO = "Vestido Infantil Estampado Gatinho Para Meninas de 4 a 14 Anos"


TELA_EDITAR_NOME = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node text="" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]" clickable="false">
    <node text="Editar nome do produto" class="android.widget.TextView" bounds="[300,1310][780,1370]" />
    <node text="NOME_NA_JANELA" class="android.widget.TextView" bounds="[360,1450][1040,1510]" />
    <node text="R$59,90" class="android.widget.TextView" bounds="[360,1610][700,1660]" />
    <node text="" class="android.view.ViewGroup" clickable="true" bounds="[40,2270][1040,2360]">
      <node text="Feito" class="android.widget.TextView" bounds="[480,2290][600,2340]" />
    </node>
  </node>
</hierarchy>"""


class AparelhoComJanela(Aparelho):
    """Mostra a lista até o primeiro toque e, depois dele, a janela de editar o nome."""

    def __init__(self, tela=TELA_CURTIDAS, nome_na_janela=VESTIDO):
        super().__init__(tela=tela)
        self.janela = TELA_EDITAR_NOME.replace("NOME_NA_JANELA", nome_na_janela)

    def dump_hierarchy(self):
        return self.janela if self.toques else self.tela


def _produto_do_link(monkeypatch, nome):
    links = []

    async def produtos_do_link(link):
        links.append(link)
        return ([{"nome": nome, "preco": 59.9, "comissao": 10.0}] if nome else []), link

    monkeypatch.setattr(ps.assistente, "produtos_do_link", produtos_do_link)
    return links


def _avisos(monkeypatch):
    avisos = []
    monkeypatch.setattr(ps.avisar_rafael, "mandar_texto", lambda texto: avisos.append(texto) or True)
    return avisos


def test_produto_adiciona_o_do_video_pelo_nome_e_nao_o_primeiro_da_lista(monkeypatch, capsys):
    _autorais()
    links = _produto_do_link(monkeypatch, VESTIDO)
    avisos = _avisos(monkeypatch)
    aparelho = AparelhoComJanela()
    assert ps.explorar("produto", aparelho)
    assert aparelho.toques == [(925, 1257)] and links == ["https://s.shopee.com.br/abc"] and avisos == []
    saida = capsys.readouterr().out
    assert "achado pelo nome" in saida and "a janela confere" in saida
    assert "Vestido" not in saida and "Gatinho" not in saida


def test_produto_aceita_o_nome_cortado_na_lista_e_na_janela(monkeypatch):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    aparelho = AparelhoComJanela(tela=TELA_CURTIDAS.replace(VESTIDO, "Vestido Infantil Estampado Gatinho…"),
                                 nome_na_janela="Vestido Infantil Estampado Gatinho Para")
    assert ps.explorar("produto", aparelho)
    assert aparelho.toques == [(925, 1257)]


def test_produto_nao_toca_onde_a_bolinha_da_motorola_cobre(monkeypatch):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    bolinha = ('<node text="" resource-id="com.motorola.mototour:id/root" package="com.motorola.mototour" '
               'class="android.widget.FrameLayout" bounds="[890,1190][1060,1330]" />\n  </node>\n</hierarchy>')
    tela = TELA_CURTIDAS.replace("  </node>\n</hierarchy>", bolinha).replace(
        'class="android.widget.TextView" bounds=', 'package="com.shopee.br" class="android.widget.TextView" bounds=')
    aparelho = AparelhoComJanela(tela=tela)
    assert ps.explorar("produto", aparelho)
    assert aparelho.toques == [(880, 1257)]
    coberta = tela.replace("[890,1190][1060,1330]", "[840,1190][1060,1330]")
    aparelho = AparelhoComJanela(tela=coberta)
    assert not ps.explorar("produto", aparelho)
    assert aparelho.toques == []


def test_janela_de_outro_produto_para_sem_tocar_em_feito(monkeypatch, capsys):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    avisos = _avisos(monkeypatch)
    aparelho = AparelhoComJanela(nome_na_janela="Fibra Proteína Cabelo Cacheado Luxo")
    assert not ps.explorar("produto; tocar:Feito", aparelho)
    assert aparelho.toques == [(925, 1257)]
    assert len(avisos) == 1 and "outro produto" in avisos[0] and VESTIDO in avisos[0]
    saida = capsys.readouterr().out
    assert "Feito não tocado" in saida and "passo 2" not in saida and "Fibra" not in saida


def test_janela_de_outro_produto_ja_aberta_nao_toca_em_nada(monkeypatch, capsys):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    avisos = _avisos(monkeypatch)
    aparelho = AparelhoComJanela(nome_na_janela="Fibra Proteína Cabelo Cacheado Luxo")
    aparelho.tela = aparelho.janela
    assert not ps.explorar("produto", aparelho)
    assert aparelho.toques == [] and not any(comando[0] == "rolar" for comando in aparelho.comandos)
    assert len(avisos) == 1 and "Feito não tocado" in capsys.readouterr().out


def test_produto_fora_da_lista_nao_adiciona_nada_e_avisa_no_privado(monkeypatch, capsys):
    _autorais()
    _produto_do_link(monkeypatch, "Garrafa Térmica Inox 1 Litro Com Alça")
    avisos = _avisos(monkeypatch)
    aparelho = Aparelho(tela=TELA_CURTIDAS)
    assert not ps.explorar("produto", aparelho)
    assert aparelho.toques == []
    assert sum(1 for comando in aparelho.comandos if comando[0] == "rolar") == ps.ROLAGENS_DO_PRODUTO
    assert len(avisos) == 1 and "Garrafa Térmica Inox" in avisos[0]
    saida = capsys.readouterr().out
    assert "nada adicionado" in saida and "Garrafa" not in saida


def test_produto_sem_nome_pelo_link_nao_adiciona_nada(monkeypatch, capsys):
    _autorais()
    _produto_do_link(monkeypatch, "")
    avisos = _avisos(monkeypatch)
    aparelho = Aparelho(tela=TELA_CURTIDAS)
    assert not ps.explorar("produto", aparelho)
    assert aparelho.toques == [] and len(avisos) == 1
    assert "o link não diz o produto" in capsys.readouterr().out


TELA_FINAL = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node text="" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]" clickable="false">
    <node text="Adicionar produto" resource-id="com.shopee.br:id/tv_add_product_title"
          class="android.widget.TextView" bounds="[40,710][320,750]" />
    PRODUTOS
    <node text="Rascunhos" resource-id="com.shopee.br:id/tv_drafts_box" class="android.widget.TextView"
          clickable="true" bounds="[40,2270][185,2345]" />
    <node text="Postar" resource-id="com.shopee.br:id/btn_post" class="android.widget.TextView"
          clickable="true" bounds="[260,2265][1000,2340]" />
  </node>
</hierarchy>"""


def _tela_final(*nomes):
    produtos = "\n".join(f'<node text="{nome}" resource-id="com.shopee.br:id/tv_product_title" '
                         f'class="android.widget.TextView" bounds="[130,{820 + 200 * i}][960,{875 + 200 * i}]" />'
                         for i, nome in enumerate(nomes))
    return TELA_FINAL.replace("PRODUTOS", produtos)


@pytest.mark.parametrize("anexados, confere", [
    ((VESTIDO,), True),
    (("Vestido Infantil Estampado Gatinho Para Meni",), True),
    (("Fibra Proteína Cabelo Cacheado Luxo",), False),
    ((VESTIDO, "Fibra Proteína Cabelo Cacheado Luxo"), False),
    ((), False),
])
def test_conferir_tela_final(anexados, confere, monkeypatch, capsys):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    avisos = _avisos(monkeypatch)
    assert ps.explorar("conferir", Aparelho(tela=_tela_final(*anexados))) is confere
    assert len(avisos) == (0 if confere else 1)
    saida = capsys.readouterr().out
    assert ("tela final confere" in saida) is confere and "Vestido" not in saida and "Fibra" not in saida


def test_rascunhos_so_e_tocado_com_o_produto_do_video_na_tela_final(monkeypatch, capsys):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    _avisos(monkeypatch)
    assert ps.explorar("video", Aparelho(galeria=f"Row: 0 _display_name={ps.NOME_NA_GALERIA}"))
    errada = Aparelho(tela=_tela_final("Fibra Proteína Cabelo Cacheado Luxo"))
    assert not ps.explorar("tocar:@tv_drafts_box", errada)
    assert not ps.explorar("xy:112,2308", errada)
    assert errada.toques == [] and "nada salvo" in capsys.readouterr().out
    certa = Aparelho(tela=_tela_final(VESTIDO))
    assert ps.explorar("tocar:Rascunhos", certa)
    assert certa.toques == [(112, 2307)]


def test_postar_so_toca_em_postar_com_o_produto_do_video_na_tela_final(monkeypatch, capsys):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    avisos = _avisos(monkeypatch)
    errada = Aparelho(tela=_tela_final("Fibra Proteína Cabelo Cacheado Luxo"))
    assert not ps.explorar("postar", errada)
    assert errada.toques == [] and len(avisos) == 1
    # Fora da tela final (sem o btn_post), nem o texto "Postar" de outro botão serve.
    fora = Aparelho()
    assert not ps.explorar("postar", fora)
    assert fora.toques == [] and len(avisos) == 1
    certa = Aparelho(tela=_tela_final(VESTIDO))
    assert ps.explorar("postar", certa)
    assert certa.toques == [(630, 2302)]
    saida = capsys.readouterr().out
    assert "nada postado" in saida and "Postar tocado" in saida
    assert "Vestido" not in saida and "Fibra" not in saida


def test_print_antes_de_postar_avisa_na_legenda(monkeypatch):
    legendas = []
    monkeypatch.setattr(ps.avisar_rafael, "mandar_foto", lambda caminho, legenda="": legendas.append(legenda) or True)
    assert ps.explorar("print:postar; print", Aparelho())
    assert legendas == [ps.LEGENDA_PRINT_POSTAR, ps.LEGENDA_PRINT]


def _ia(monkeypatch, resposta):
    pedidos = []

    async def analisar(arquivo, prompt):
        pedidos.append((arquivo, prompt))
        return resposta

    monkeypatch.setattr(ps.api_gemini, "analisar_video_gemini", analisar)
    return pedidos


def test_ia_confere_o_produto_do_link_com_o_video(monkeypatch, capsys):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    avisos = _avisos(monkeypatch)
    pedidos = _ia(monkeypatch, '```json\n{"confere": true, "motivo": "vestido infantil"}\n```')
    assert ps.explorar("ia", Aparelho())
    assert pedidos[0][0] == os.path.abspath("archive/antigo.mp4") and VESTIDO in pedidos[0][1]
    assert avisos == [] and "a IA confere" in capsys.readouterr().out


@pytest.mark.parametrize("resposta, avisa", [
    ('{"confere": false, "motivo": "o vídeo mostra um vestido; o link é de fibra de cabelo"}', True),
    ('{"confere": "talvez"}', True),
    ("não consegui ver o vídeo", False),
    (None, False),
])
def test_ia_sem_confirmacao_para(resposta, avisa, monkeypatch, capsys):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    avisos = _avisos(monkeypatch)
    _ia(monkeypatch, resposta)
    assert not ps.explorar("ia", Aparelho())
    assert len(avisos) == (1 if avisa else 0)
    saida = capsys.readouterr().out
    assert "parado" in saida and "fibra" not in saida and "Vestido" not in saida


@pytest.mark.parametrize("texto, nome, igual", [
    (VESTIDO, VESTIDO, True),
    ("  vestido infantil  estampado gatinho para meninas de 4 a 14 anos ", VESTIDO, True),
    ("Vestido Infantil Estampado...", VESTIDO, True),
    ("Vestido", VESTIDO, False),
    ("Vestido Infantil Liso Para Meninas", VESTIDO, False),
    ("", VESTIDO, False),
])
def test_mesmo_produto(texto, nome, igual):
    assert ps.mesmo_produto(texto, nome) is igual


def test_botao_adicionar_so_dentro_do_bloco_do_produto():
    # Sem o bloco de cada produto, o menor bloco com o nome é a lista inteira: o robô não adivinha.
    tela = TELA_CURTIDAS.replace('class="android.view.ViewGroup" clickable="true" bounds="[0,1060][1080,1330]"',
                                 'class="android.view.ViewGroup" clickable="false" bounds="[0,1060][1080,1330]"')
    assert ps.adicionar_do_produto(TELA_CURTIDAS, VESTIDO)["caixa"] == (850, 1235, 1000, 1280)
    assert ps.adicionar_do_produto(tela, VESTIDO) is None


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
    monkeypatch.setattr(ps.av, "tela_aberta", lambda: False)
    monkeypatch.setattr(ps, "conectar", lambda celular: aparelho)
    assert ps.explorar("xy:10,20", celular=True) is (True if comeca else None)
    assert aparelho.toques == ([(10, 20)] if comeca else [])
    assert ("fora do horário das rodadas" in capsys.readouterr().out) is not comeca


def test_so_fica_vermelho_quando_nem_comecou():
    assert ps.codigo_de_saida(True) == 0
    assert ps.codigo_de_saida(False) == 0
    assert ps.codigo_de_saida(None) == 1

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

    def __call__(self, **seletor):
        """O d(focused=True) do uiautomator2: aqui, nenhum campo em foco (cai no send_keys)."""
        return type("Campo", (), {"exists": False})()

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
    ("Excluir 1 item?", "Excluir # item?"),
    ("Descartar alterações", "Descartar alterações"),
    ("Fixado", "Fixado"),
    ("Copiar link", "Copiar link"),
    ("share video button", "share video button"),
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


# A página que o link abre: foto, preço, nome com a seta e Compre Agora, sem o coração.
TELA_PAGINA_CURTA = """<hierarchy><node class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">
  <node class="android.view.ViewGroup" clickable="true" bounds="[0,1100][1080,1440]">
    <node text="R$59,90" class="android.widget.TextView" bounds="[40,1100][300,1150]" />
    <node text="Vestido Infantil Estampado Gatinho Para Meninas de 4 a 14 Anos"
          class="android.widget.TextView" bounds="[40,1190][1010,1245]" />
  </node>
  <node class="android.view.ViewGroup" clickable="true" bounds="[230,1350][1040,1420]">
    <node text="Compre Agora" class="android.widget.TextView" bounds="[500,1365][720,1410]" />
  </node>
</node></hierarchy>"""


class AparelhoDaPagina(Aparelho):
    """A página curta até o primeiro toque; depois, a página completa (curtida ou não)."""

    def __init__(self, completa=TELA_PRODUTO, curtiu=None):
        super().__init__(tela=TELA_PAGINA_CURTA)
        self.completa, self.curtiu = completa, curtiu

    def dump_hierarchy(self):
        if not self.toques:
            return self.tela
        if len(self.toques) > 1 and self.curtiu:
            return self.curtiu
        return self.completa


CURTIDO = TELA_PRODUTO.replace("buttonItemLike", "buttonItemLiked")


def test_curtir_abre_a_pagina_completa_pelo_nome_e_curte(monkeypatch, capsys):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    aparelho = AparelhoDaPagina(curtiu=CURTIDO)
    assert ps.explorar("curtir", aparelho)
    # Primeiro o nome do produto (abre a página completa), depois o coração.
    assert aparelho.toques == [(525, 1217), (1028, 1233)]
    saida = capsys.readouterr().out
    assert "produto curtido" in saida and "Vestido" not in saida


class Coracao(AparelhoDaPagina):
    """A página completa com o coração que troca a cada toque (ou não, quando o toque não pega)."""

    def __init__(self, descurte=True, curte=True):
        super().__init__(completa=CURTIDO)
        self.descurte, self.curte = descurte, curte

    def click(self, x, y):
        super().click(x, y)
        if len(self.toques) == 1:
            return                                                        # o nome: abre a página completa
        if self.completa == CURTIDO and self.descurte:
            self.completa = TELA_PRODUTO
        elif self.completa == TELA_PRODUTO and self.curte:
            self.completa = CURTIDO


def test_curtir_com_o_produto_ja_curtido_descurte_e_curte_de_novo(monkeypatch, capsys):
    # Pedido do Rafael (24/10): já curtido de outro dia, descurtir e curtir de novo faz o
    # produto ir para o 1º lugar de Minhas Curtidas.
    import registro_processos as rp
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    aparelho = Coracao()
    assert ps.explorar("curtir", aparelho)
    assert aparelho.toques == [(525, 1217), (1028, 1233), (1028, 1233)] and aparelho.completa == CURTIDO
    assert "descurti e curti de novo" in capsys.readouterr().out
    linha = [l for l in rp.contagem("2000-01-01 00:00:00") if l[1] == "curtir o produto"][0]
    assert linha[2:4] == ("já estava curtido", "descurtido e curtido de novo")


def test_curtido_que_nao_descurte_segue_e_o_que_nao_volta_a_curtir_para(monkeypatch):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    # O toque para descurtir não pegou: continua curtido, só mais embaixo; segue.
    aparelho = Coracao(descurte=False)
    assert ps.explorar("curtir", aparelho)
    assert len(aparelho.toques) == 2
    # Descurtiu, mas não volta a curtir: tenta 2 vezes e para (sem o produto na lista).
    aparelho = Coracao(curte=False)
    assert not ps.explorar("curtir", aparelho)
    assert len(aparelho.toques) == 4 and aparelho.completa == TELA_PRODUTO


def test_curtir_deixa_no_registro_se_o_produto_ja_estava_curtido():
    # O checkup liga o curtir ao "nome não achado" do anexar.
    import registro_processos as rp
    aparelho = Aparelho(tela=TELA_PRODUTO)
    aparelho.click = lambda x, y: setattr(aparelho, "tela", CURTIDO)
    assert ps.curtir_na_pagina(aparelho, TELA_PRODUTO)[0]
    # O toque para descurtir que não pega fica no registro com o motivo.
    assert ps.curtir_na_pagina(Aparelho(tela=CURTIDO), CURTIDO)[0]
    linhas = {(l[2], l[3]) for l in rp.contagem("2000-01-01 00:00:00") if l[1] == "curtir o produto"}
    assert linhas == {("curtido agora", ""), ("já estava curtido", "o toque para descurtir não pegou")}


def test_curtir_rola_atras_do_coracao_e_para_sem_ele(monkeypatch, capsys):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    aparelho = AparelhoDaPagina(completa=TELA_PAGINA_CURTA.replace("Vestido", "Outro"))
    assert not ps.explorar("curtir", aparelho)
    assert aparelho.toques == [(525, 1217)]
    assert len([c for c in aparelho.comandos if c[0] == "rolar"]) == ps.ROLAGENS_DO_CORACAO
    assert "o coração não está na página" in capsys.readouterr().out


def test_curtir_sem_o_nome_do_produto_na_pagina_nao_toca_em_nada(monkeypatch, capsys):
    _autorais()
    _produto_do_link(monkeypatch, "Fibra Proteína Cabelo Cacheado Luxo")
    aparelho = AparelhoDaPagina()
    assert not ps.explorar("curtir", aparelho)
    assert aparelho.toques == []
    assert "não está na página" in capsys.readouterr().out


def test_curtir_que_nao_pega_avisa(monkeypatch, capsys):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    aparelho = AparelhoDaPagina()
    assert not ps.explorar("curtir", aparelho)
    # O nome, o coração e, sem o coração trocar depois da espera, mais um toque nele.
    assert aparelho.toques == [(525, 1217), (1028, 1233), (1028, 1233)]
    assert "não ficou curtido" in capsys.readouterr().out


def test_passo_desconhecido_nao_toca_em_nada(capsys):
    aparelho = Aparelho()
    assert ps.explorar("abrir; publicar", aparelho) is None
    assert aparelho.comandos == [] and "passo desconhecido: publicar" in capsys.readouterr().out


def test_para_no_primeiro_passo_que_falha(capsys):
    aparelho = Aparelho()
    assert ps.explorar("tocar:Botão que não existe; voltar", aparelho) is False
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
    # Guardado para a aprovação do rascunho mostrar o texto que está na legenda.
    assert ps.db.ler_config(ps.CHAVE_TESTE)["titulo"] == "Garrafa térmica inox 1 litro"
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
    # O comentário vai sozinho, numa mensagem só dele, para copiar com um toque.
    assert avisos == [ps.AVISO_COMENTARIO, "Amei essa garrafa! #achadinhos"]
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
    assert not ps.explorar("foto", Aparelho())


JPG = b"\xff\xd8\xff\xe0" + b"0" * 32


@pytest.mark.parametrize("dados, extensao", [
    (JPG, "jpg"), (b"\x89PNG\r\n\x1a\n" + b"0" * 8, "png"), (b"RIFF\x10\x00\x00\x00WEBPVP8 ", "webp"),
    (b"<html>erro</html>", None), (b"", None)])
def test_extensao_da_foto_sai_dos_bytes(dados, extensao):
    assert ps.extensao_da_foto(dados) == extensao


def test_foto_do_anuncio_vai_para_a_galeria_e_foto_apagar_tira(monkeypatch, capsys):
    _autorais()
    monkeypatch.setattr(ps, "anuncio_do_produto", lambda video: {"foto": JPG, "nome": "Produto", "preco": 9.9})
    aparelho = Aparelho(galeria=f"Row: 0 _display_name={ps.NOME_DA_FOTO}.jpg")
    assert ps.explorar("foto", aparelho)
    [(temporario, destino)] = aparelho.enviados
    assert destino == f"{ps.GALERIA}/{ps.NOME_DA_FOTO}.jpg" and not os.path.exists(temporario)
    assert ["content", "query", "--uri", "content://media/external/images/media",
            "--projection", "_display_name"] in aparelho.comandos
    assert "foto do anúncio na galeria" in capsys.readouterr().out
    # Sem a foto na galeria depois do aviso, o passo falha.
    assert not ps.explorar("foto", Aparelho(galeria=""))
    aparelho = Aparelho()
    assert ps.explorar("foto:apagar", aparelho)
    assert ["rm", "-f", f"{ps.GALERIA}/{ps.NOME_DA_FOTO}.jpg"] in aparelho.comandos
    assert aparelho.toques == [] and aparelho.enviados == []


@pytest.mark.parametrize("anuncio", [{}, {"foto": None}, {"foto": b"<html>erro</html>"}])
def test_sem_a_foto_do_anuncio_nada_vai_para_a_galeria(anuncio, monkeypatch, capsys):
    _autorais()
    monkeypatch.setattr(ps, "anuncio_do_produto", lambda video: anuncio)
    aparelho = Aparelho()
    assert not ps.explorar("foto", aparelho)
    assert aparelho.enviados == []


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
    # O anexado fica no registro, com quantas vezes rolou a lista.
    import registro_processos as rp
    assert [l[2:4] for l in rp.contagem("2000-01-01 00:00:00") if l[1] == "anexar o produto"] == [
        ("anexado", "pelo nome; 0 rolada(s)")]


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
    # A lista não muda depois de rolar: acabou, e o robô para de rolar e volta ao alto para
    # a última chance (o 1º pela foto, que aqui não tem o print da tela).
    assert sum(1 for comando in aparelho.comandos if comando[0] == "rolar") == 2
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


def test_tela_final_que_nao_confere_deixa_no_registro_so_numeros(monkeypatch):
    # 24/10, 09:19: a tela final não conferiu e não deu para saber por quê. O registro
    # diz quantos anexados e o quanto o mais parecido lembra o nome (o nome não vai).
    import registro_processos as rp
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    _avisos(monkeypatch)
    assert not ps.explorar("conferir", Aparelho(tela=_tela_final("Vestido Infantil Estampado Rosa")))
    assert not ps.explorar("conferir", Aparelho(tela=_tela_final()))
    linhas = [l[3] for l in rp.contagem("2000-01-01 00:00:00") if l[1] == "conferir a tela final"]
    assert sorted(linhas) == ["0 anexado(s) na tela; 1 do vídeo",
                              "1 anexado(s) na tela; 1 do vídeo; o mais parecido com cada um: 42% das palavras"]
    assert not any("Vestido" in l for l in linhas)


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
    # Confere duas vezes: a IA já recusou um vídeo que tinha aceitado antes.
    assert len(pedidos) == 2
    assert pedidos[0][0] == os.path.abspath("archive/antigo.mp4") and VESTIDO in pedidos[0][1]
    assert avisos == [] and "a IA confere 2 vezes" in capsys.readouterr().out


def test_ia_que_confirma_e_depois_nega_para(monkeypatch, capsys):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    avisos = _avisos(monkeypatch)
    respostas = iter(['{"confere": true, "motivo": "vestido"}', '{"confere": false, "motivo": "outro produto"}'])

    async def analisar(arquivo, prompt):
        return next(respostas)

    monkeypatch.setattr(ps.api_gemini, "analisar_video_gemini", analisar)
    assert not ps.explorar("ia", Aparelho())
    assert len(avisos) == 1 and "2ª vez" in capsys.readouterr().out


def test_ia_compara_o_video_com_a_foto_do_anuncio(monkeypatch, capsys):
    # Pedido do Rafael (P13): a foto do anúncio vai junto com o vídeo, e a IA compara o
    # item, não só o tipo (24/10: punição de "produto irrelevante").
    _autorais()
    avisos = _avisos(monkeypatch)

    async def produtos_do_link(link):
        return [{"nome": VESTIDO, "preco": 59.9, "comissao": 10.0, "imagem": "https://cf.shopee.com.br/file/x"}], link

    class Foto:
        def __init__(self, url, timeout=None):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, limite):
            return b"\xff\xd8foto"

    pedidos = []

    async def analisar(arquivo, prompt, imagens=None):
        pedidos.append((prompt, imagens))
        return '{"confere": true, "motivo": "o mesmo vestido da foto"}'

    monkeypatch.setattr(ps.assistente, "produtos_do_link", produtos_do_link)
    monkeypatch.setattr(ps.urllib.request, "urlopen", Foto)
    monkeypatch.setattr(ps.api_gemini, "analisar_video_gemini", analisar)
    assert ps.explorar("ia", Aparelho())
    assert len(pedidos) == 2 and pedidos[0][1] == [(b"\xff\xd8foto", "image/jpeg")]
    assert "foto do anúncio" in pedidos[0][0] and VESTIDO in pedidos[0][0]
    assert "com a foto do anúncio" in capsys.readouterr().out and avisos == []

    # A foto que não baixa: a conferência segue só pelo nome, como antes.
    def falha(url, timeout=None):
        raise OSError("sem rede")

    monkeypatch.setattr(ps.urllib.request, "urlopen", falha)
    pedidos.clear()
    assert ps.explorar("ia", Aparelho())
    assert pedidos[0][1] is None and "foto do anúncio" not in pedidos[0][0]


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


@pytest.mark.parametrize("texto, igual", [
    (VESTIDO, True), ("Oficial " + VESTIDO, True), ("1 " + VESTIDO, True), ("￼ " + VESTIDO, True),
    ("Vestido Infantil Liso Para Meninas", False), ("Fibra " + "Proteína Cabelo Cacheado Luxo", False),
    ("Um texto bem comprido antes do nome " + VESTIDO, False),
])
def test_nome_na_pagina_aceita_um_pedaco_curto_antes(texto, igual):
    # Na página do link, o app pôs um pedaço antes do nome (19 e 22/10): o nome tem de valer.
    assert ps.nome_na_pagina(texto, VESTIDO) is igual


def test_curtir_acha_o_nome_com_o_selo_antes(monkeypatch):
    _autorais()
    _produto_do_link(monkeypatch, VESTIDO)
    aparelho = AparelhoDaPagina(curtiu=CURTIDO)
    aparelho.tela = TELA_PAGINA_CURTA.replace(f'text="{VESTIDO}"', f'text="Oficial {VESTIDO}"')
    assert ps.explorar("curtir", aparelho)
    assert aparelho.toques == [(525, 1217), (1028, 1233)]


def test_copiado_diz_so_se_e_link_da_shopee_e_o_tamanho():
    class Celular:
        clipboard = "Olha este vídeo: https://sv.shopee.com.br/share-video/abc"
    ok, texto = ps.fazer_passo(Celular(), "copiado", "")
    assert ok and texto == "link da Shopee copiado (40 caracteres, num texto de 57)" and "http" not in texto
    assert ps.link_copiado(Celular()) == "https://sv.shopee.com.br/share-video/abc"
    Celular.clipboard = "outra coisa"
    assert ps.fazer_passo(Celular(), "copiado", "") == (False, "o copiado (11 caracteres) não tem link da Shopee")
    Celular.clipboard = None
    assert ps.fazer_passo(Celular(), "copiado", "") == (False, "nada copiado, ou o Android não deixou ler")


def test_passo_legenda_compara_com_o_titulo_guardado_sem_mostrar_o_texto():
    titulo = "Lustre Escandinavo de 3 Cores ✨ #iluminacao #casamoderna"
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    ps.db.salvar_config(ps.CHAVE_TESTE, {"titulo": titulo})

    class Celular:
        legenda = titulo.replace(" #", "\n#")

        def __call__(self, **seletor):
            return type("Campo", (), {"exists": False})()

        def dump_hierarchy(self):
            return ('<hierarchy><node class="android.widget.EditText" clickable="true" '
                    f'resource-id="com.shopee.br:id/et_caption" text="{self.legenda}" bounds="[40,300][1040,400]"/>'
                    '<node class="android.widget.TextView" clickable="false" resource-id="com.shopee.br:id/tv_content_num" '
                    'text="56/150" bounds="[980,580][1060,620]"/></hierarchy>')

    ok, texto = ps.fazer_passo(Celular(), "legenda", "")
    assert ok and "pela acessibilidade: a legenda é o título" in texto and "contador do app: 56/150" in texto
    assert "pela cópia: a legenda NÃO é o título: 0 caracteres" in texto      # sem a cópia, nada
    Celular.legenda = "Outra coisa"
    ok, texto = ps.fazer_passo(Celular(), "legenda", "")
    assert ok and "NÃO é o título" in texto and "Lustre" not in texto and "Outra" not in texto


class CelularComCopia:
    """O campo da legenda em foco guarda o texto com os emojis; a leitura da tela troca cada um por ".."."""

    def __init__(self, guardado, copia=True):
        self.guardado, self.copia, self.clipboard, self.teclas = guardado, copia, "copiado antigo", []

    def set_clipboard(self, texto, label=None):
        self.clipboard = texto

    def press(self, tecla, meta=None):
        self.teclas.append((tecla, meta))
        if self.copia and (tecla, meta) == (ps.TECLA_C, ps.CTRL):
            self.clipboard = self.guardado
        if (tecla, meta) == (ps.TECLA_V, ps.CTRL):
            self.guardado = self.clipboard

    def __call__(self, **seletor):
        lido = ps.como_o_android_le(self.guardado)
        return type("Campo", (), {"exists": True, "get_text": lambda campo: lido})()

    def dump_hierarchy(self):
        return ('<hierarchy><node class="android.widget.EditText" clickable="true" resource-id='
                f'"com.shopee.br:id/et_caption" text="{ps.como_o_android_le(self.guardado)}" bounds="[40,300][1040,400]"/>'
                '</hierarchy>')


def test_legenda_copiada_traz_os_emojis_que_a_leitura_da_tela_troca_por_ponto():
    titulo = "Luminária 💡 de mesa ✨ #decoracao"
    celular = CelularComCopia(titulo)
    assert ps.legenda_lida(celular) == "Luminária .. de mesa ✨ #decoracao"
    assert not ps.mesma_legenda(ps.legenda_lida(celular), titulo)
    assert ps.legenda_do_campo(celular) == titulo and ps.mesma_legenda(ps.legenda_do_campo(celular), titulo)
    assert celular.teclas[-2:] == [(ps.TECLA_A, ps.CTRL), (ps.TECLA_C, ps.CTRL)]


def test_copia_que_nao_aconteceu_nunca_devolve_o_copiado_antigo():
    celular = CelularComCopia("Luminária 💡 de mesa", copia=False)
    assert ps.legenda_copiada(celular) == ""
    assert ps.legenda_do_campo(celular) == "Luminária .. de mesa"         # cai na leitura da tela


def test_como_o_android_le_troca_so_os_emojis_de_fora_do_plano_basico():
    assert ps.como_o_android_le("Vestido 👗 lindo ✨ ❤️") == "Vestido .. lindo ✨ ❤️"
    assert ps.como_o_android_le(None) == ""


def test_passos_colar_e_legenda_com_texto_comparam_com_o_texto_dado():
    celular = CelularComCopia("")
    assert ps.separar_passos("colar:Teste 💡 ok; legenda:Teste 💡 ok") == [
        ("colar", "Teste 💡 ok"), ("legenda", "Teste 💡 ok")]
    assert ps.fazer_passo(celular, "colar", "Teste 💡 ok") == (True, "colado")
    assert celular.guardado == "Teste 💡 ok"
    assert celular.teclas == [(ps.TECLA_A, ps.CTRL), (ps.TECLA_V, ps.CTRL)]
    ok, texto = ps.fazer_passo(celular, "legenda", "Teste 💡 ok")
    assert ok and texto.startswith("pela cópia: a legenda é o título (10 caracteres na tela, 10 no título)")
    assert ("pela acessibilidade: a legenda NÃO é o título: 11 caracteres na tela, 10 no título; a 1ª diferença "
            "está no caractere 7 (na tela U+002E, no título U+1F4A1)") in texto
    assert texto.endswith("; 1 emoji(s) de fora do plano básico no título")


def test_escrever_poe_o_texto_inteiro_no_campo_em_foco_com_os_emojis():
    # O texto vai inteiro pelo set_text do campo em foco, com os emojis.
    class Campo:
        exists, texto = True, None

        def set_text(self, texto):
            Campo.texto = texto

    class Celular:
        teclado = []

        def __call__(self, **seletor):
            assert seletor == {"focused": True}
            return Campo()

        def send_keys(self, texto):
            Celular.teclado.append(texto)

    ps.escrever(Celular(), "Luminária 💡 de mesa ✨ #decoracao")
    assert Campo.texto == "Luminária 💡 de mesa ✨ #decoracao" and Celular.teclado == []


def test_legenda_lida_do_campo_e_nao_do_retrato_que_troca_emoji_por_ponto():
    # Sem a cópia do campo, a leitura vem do campo (get_text) antes do retrato da tela.
    titulo = "Luminária 💡 de mesa ✨ #decoracao"

    class Campo:
        exists = True

        def get_text(self):
            return titulo

    class Celular:
        def __call__(self, **seletor):
            assert seletor == {"resourceId": "com.shopee.br:id/et_caption"}
            return Campo()

        def dump_hierarchy(self):
            raise AssertionError("não deveria ler o retrato")

    assert ps.mesma_legenda(ps.legenda_do_campo(Celular()), titulo)


def test_video_link_de_video_escolhe_o_que_abre_um_video(monkeypatch):
    # Para mapear o Ver Produtos no celular: o vídeo da fonte cujo link abre outro vídeo.
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    os.makedirs("archive", exist_ok=True)
    for nome in ("a.mp4", "b.mp4"):
        open(os.path.join("archive", nome), "wb").close()
    candidatos = [("viral:1", "archive/a.mp4", "https://s.shopee.com.br/produto", ""),
                  ("viral:2", "archive/b.mp4", "https://s.shopee.com.br/video", "")]
    destinos = {"https://s.shopee.com.br/produto": "https://shopee.com.br/product/1/2",
                "https://s.shopee.com.br/video": "https://sv.shopee.com.br/share-video/AAAA"}

    async def converter(link):
        return destinos[link]

    candidatos.append(("viral:3", "archive/b.mp4", "https://s.shopee.com.br/video", ""))
    monkeypatch.setattr(ps.assistente, "_candidatos", lambda fonte: candidatos)
    monkeypatch.setattr(ps, "link_para_converter", converter)
    ps.assistente.registrar("viral:2", "enviado")          # já mandado pelo assistente: fica de fora
    video = ps.video_do_teste(novo=True, de_video=True)
    assert video["id"] == "viral:3" and ps.db.ler_config(ps.CHAVE_TESTE)["id"] == "viral:3"
    # De novo: o de agora fica de fora, e não há outro com link de vídeo.
    assert ps.video_da_fonte(de_video=True) is None
    assert ps.separar_passos("video:link-de-video") == [("video", "link-de-video")]


def test_comprar_com_cupom_do_player_e_proibido():
    # No player de um vídeo (Motorola, 23/10) há "Comprar com cupom": botão de comprar.
    for texto in ("Comprar com cupom", "Compre agora", "COMPRAR", "comprar  agora", "Adicionar ao carrinho"):
        assert ps.eh_alvo_proibido(texto), texto
    for texto in ("Ver Produtos (2)", "Compras", "Compartilhar", "Postar vídeo", "Comprou 2 mil"):
        assert not ps.eh_alvo_proibido(texto), texto
    tela = ('<hierarchy><node class="android.view.ViewGroup" clickable="true" bounds="[400,1820][830,1890]">'
            '<node text="Comprar com cupom" class="android.widget.TextView" bounds="[450,1830][780,1880]"/></node>'
            '</hierarchy>')
    assert ps.proibido_no_ponto(tela, 613, 1855) and not ps.proibido_no_ponto(tela, 522, 1969)


VER_PRODUTOS = """<hierarchy><node class="android.view.ViewGroup" clickable="true" bounds="[0,400][1080,2400]">
  <node text="Ver Produtos (2)" class="android.widget.TextView" bounds="[40,700][300,750]" />
  <node class="android.view.ViewGroup" clickable="true" bounds="[0,1030][1080,1330]">
    <node text="-20%" class="android.widget.TextView" bounds="[200,1050][300,1090]" />
    <node text="Garrafa Térmica Inox 1 Litro Com Alça" class="android.widget.TextView" bounds="[330,1070][1040,1120]" />
    <node text="R$5 de desconto" class="android.widget.TextView" bounds="[330,1140][700,1180]" />
    <node class="android.view.ViewGroup" clickable="true" bounds="[780,1240][1050,1310]">
      <node text="Comprar com cupom" class="android.widget.TextView" bounds="[790,1250][1040,1300]" />
    </node>
  </node>
  <node class="android.view.ViewGroup" clickable="true" bounds="[0,1350][1080,1650]">
    <node text="Copo Térmico 500 ml" class="android.widget.TextView" bounds="[330,1390][1040,1440]" />
    <node class="android.view.ViewGroup" clickable="true" bounds="[780,1560][1050,1630]">
      <node text="Comprar com cupom" class="android.widget.TextView" bounds="[790,1570][1040,1620]" />
    </node>
  </node>
  <node text="Ver Mais (1)" class="android.widget.TextView" clickable="true" bounds="[400,1720][640,1770]" />
  <node text="Você Também Pode Gostar" class="android.widget.TextView" bounds="[300,1870][780,1920]" />
  <node class="android.view.ViewGroup" clickable="true" bounds="[0,1940][1080,2240]">
    <node text="Kit Potes Herméticos De Vidro Para Cozinha" class="android.widget.TextView" bounds="[330,1960][1040,2010]" />
  </node>
</node></hierarchy>"""


def test_ver_produtos_toca_no_nome_dos_vinculados_e_nunca_nas_recomendacoes():
    # Mapeado no Motorola (23/10): a lista do Ver Produtos tem os produtos do criador e,
    # depois de "Ver Mais" e "Você Também Pode Gostar", recomendações que não são do vídeo.
    assert ps.produtos_vinculados(VER_PRODUTOS) == [(685, 1095), (685, 1415)]
    assert all(not ps.proibido_no_ponto(VER_PRODUTOS, x, y) for x, y in ps.produtos_vinculados(VER_PRODUTOS))


def test_pagina_do_produto_e_video_removido():
    pagina = ('<hierarchy><node text="Copo Térmico 500 ml " resource-id="com.shopee.br:id/labelProductPageProductName" '
              'class="android.widget.TextView" bounds="[40,1850][1040,1900]"/></hierarchy>')
    assert ps.nome_na_pagina_do_produto(pagina) == "Copo Térmico 500 ml"
    assert ps.nome_na_pagina_do_produto(VER_PRODUTOS) == ""
    removido = ('<hierarchy><node text="Este vídeo foi removido pelo criador" class="android.widget.TextView" '
                'bounds="[200,1240][880,1280]"/></hierarchy>')
    assert ps.video_removido(removido) and not ps.video_removido(VER_PRODUTOS)


def test_nome_lido_no_celular_vale_sem_a_api_e_os_produtos_do_video_vao_juntos(monkeypatch):
    async def nao_chamar(link):
        raise AssertionError("o nome já veio do celular")

    monkeypatch.setattr(ps.assistente, "produtos_do_link", nao_chamar)
    assert ps.nome_do_produto({"link": "https://s.shopee.com.br/v", "produto": "Copo"}) == "Copo"
    assert ps.nomes_dos_produtos({"link": "x", "produtos": ["Copo", "Garrafa"]}) == ["Copo", "Garrafa"]


def test_minhas_curtidas_aceita_o_mesmo_pedaco_antes_do_nome_que_a_pagina():
    # 23/10 15:28: o robô curtiu na página (que aceita um selo antes do nome) e não achou o
    # produto em Minhas Curtidas, que exigia o nome igual. Os dois lugares usam a mesma régua.
    tela = TELA_CURTIDAS.replace(f'text="{VESTIDO}"', f'text="Oficial {VESTIDO}"')
    assert ps.adicionar_do_produto(tela, VESTIDO)["caixa"] == (850, 1235, 1000, 1280)
    assert ps.adicionar_do_produto(TELA_CURTIDAS, "Vestido Infantil Liso Para Meninas de Festa") is None


def test_minhas_curtidas_espera_a_lista_carregar(monkeypatch):
    esperas = []
    monkeypatch.setattr(ps.time, "sleep", esperas.append)
    ps.esperar_a_lista(Aparelho(tela=TELA_CURTIDAS))
    assert esperas == []
    ps.esperar_a_lista(Aparelho(tela=TELA_EU))
    assert sum(esperas) == ps.ESPERA_DA_LISTA


def test_nome_nao_achado_deixa_no_registro_o_quanto_o_mais_parecido_lembra(monkeypatch):
    import registro_processos as rp
    avisos = []
    monkeypatch.setattr(ps.avisar_rafael, "mandar_texto", avisos.append)
    monkeypatch.setattr(ps, "rolar", lambda d, para_cima=False: None)
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)

    class Celular:
        def dump_hierarchy(self):
            return TELA_CURTIDAS.replace(f'text="{VESTIDO}"', 'text="Um texto bem comprido antes do nome ' + VESTIDO + '"')

    ok, motivo = ps.adicionar_produto(Celular(), {"produto": VESTIDO})
    assert not ok and "não está na lista" in motivo and VESTIDO in avisos[0]
    linha = [l for l in rp.contagem("2000-01-01 00:00:00")
             if l[1] == "anexar o produto" and l[2] == "nome não achado em Minhas Curtidas"][0]
    assert linha[2] == "nome não achado em Minhas Curtidas"
    assert linha[3] == ("o mais parecido tem 100% e o nome começa depois de 7 palavra(s); "
                        "o 1º da lista tem 0%; 1 rolada(s); a lista acabou")
    assert "Vestido" not in linha[3]
    assert ps.parecido_na_tela(TELA_CURTIDAS, "Panela de Pressão Inox") == (0, -1)


def _nao_achado(monkeypatch, tela, nome):
    """O detalhe que o anexar deixa no registro quando não acha o produto em Minhas Curtidas."""
    import registro_processos as rp
    monkeypatch.setattr(ps.avisar_rafael, "mandar_texto", lambda texto: None)
    monkeypatch.setattr(ps, "rolar", lambda d, para_cima=False: None)
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)

    class Celular:
        def dump_hierarchy(self):
            return tela

    ok, _ = ps.adicionar_produto(Celular(), {"produto": nome})
    assert not ok
    return [l for l in rp.contagem("2000-01-01 00:00:00")
            if l[1] == "anexar o produto" and l[2] == "nome não achado em Minhas Curtidas"][0][3]


def test_nome_nao_achado_diz_onde_o_mais_parecido_difere_e_o_quanto_o_1o_lembra(monkeypatch):
    # 24/10 18:09: o mais parecido tinha 85% das palavras e a lista acabou. Para a próxima
    # vez dizer se era o produto com o nome mostrado de outro jeito (o 1º da lista é o
    # curtido por último) ou outro produto: as posições que faltam e o 1º, só em números.
    tela = TELA_CURTIDAS.replace(f'text="{VESTIDO}"', 'text="Vestido Infantil Liso Gatinho Para Meninas de 4 a 14 Anos"')
    detalhe = _nao_achado(monkeypatch, tela, VESTIDO)
    assert detalhe == ("o mais parecido tem 85% (faltam a 3ª; 1 a mais); o 1º da lista tem 0%; "
                       "1 rolada(s); a lista acabou")
    assert len(detalhe) <= 120 and "Vestido" not in detalhe and "Liso" not in detalhe


def test_detalhe_do_nao_achado_cabe_no_registro_com_muitas_diferencas(monkeypatch):
    tela = TELA_CURTIDAS.replace(f'text="{VESTIDO}"', 'text="Vestido Adulto Liso Grande Para Mulheres Festa Noite Longo"')
    detalhe = _nao_achado(monkeypatch, tela, VESTIDO)
    assert detalhe.startswith("o mais parecido tem ") and "(faltam a 2ª, 3ª, 4ª…;" in detalhe
    assert detalhe.endswith("; a lista acabou") and len(detalhe) <= 120


@pytest.mark.parametrize("texto", [
    "【Oferta】Vestido Infantil Estampado Gatinho Para Meninas de 4 a 14 Anos",
    "Vestido Infantil - Estampado Gatinho Para Meninas de 4 a 14 Anos",
    "Vestido Infantil Estampado Gatinho Para Meninas de 4 a 14 Anos 🔥",
])
def test_sinal_ou_acento_codificado_de_outro_jeito_nao_faz_outro_produto(texto):
    # Um colchete, traço, emoji ou acento de outra codificação a mais não é outro produto: a
    # lista de Adicionar Produto pode mostrar os sinais do nome de outro jeito.
    assert ps.nome_na_pagina(texto, VESTIDO)
    tela = TELA_CURTIDAS.replace(f'text="{VESTIDO}"', f'text="{texto}"')
    assert ps.adicionar_do_produto(tela, VESTIDO)["caixa"] == (850, 1235, 1000, 1280)


def test_acento_de_outra_codificacao_e_o_mesmo_nome():
    import unicodedata
    panela = "Panela de Pressão Inox 4,5 Litros"
    assert ps.mesmo_produto(unicodedata.normalize("NFD", panela), panela)
    assert not ps.mesmo_produto("Panela de Pressao Inox 4,5 Litros", panela)


def test_nomes_da_lista_de_cima_para_baixo_so_os_que_tem_adicionar():
    assert ps.nomes_da_lista(TELA_CURTIDAS) == ["Fibra Proteína Cabelo Cacheado Luxo", VESTIDO]
    assert ps.nomes_da_lista(TELA_EU) == []


# --- O 1º da lista de Minhas Curtidas (escolha do Rafael, P18) ---

PARECIDO = "Vestido Infantil Liso Gatinho Para Meninas de 4 a 14 Anos"   # 85% das palavras do VESTIDO
PANELA = "Panela de Pressão Inox 4,5 Litros Fechamento Externo"
FIBRA = "Fibra Proteína Cabelo Cacheado Luxo"


def _lista(primeiro, segundo):
    return TELA_CURTIDAS.replace(f'text="{FIBRA}"', f'text="{primeiro}"').replace(
        f'text="{VESTIDO}"', f'text="{segundo}"')


class AparelhoComPrint(AparelhoComJanela):
    """A lista, a janela depois do toque e o print da tela (o do uiautomator2 é uma imagem PIL)."""

    def screenshot(self):
        from PIL import Image
        return Image.new("RGB", (1080, 2400), "white")


def _ia_da_foto(monkeypatch, confere):
    chamadas = []

    async def analisar(arquivo, prompt, imagens=None):
        chamadas.append((prompt, imagens))
        return '{"confere": %s, "motivo": "o item da imagem"}' % ("true" if confere else "false")

    monkeypatch.setattr(ps.api_gemini, "analisar_video_gemini", analisar)
    return chamadas


def _anexar_linhas():
    import registro_processos as rp
    return sorted(l[2:4] for l in rp.contagem("2000-01-01 00:00:00") if l[1] == "anexar o produto")


def test_o_1o_da_lista_com_o_nome_parecido_e_anexado_com_o_nome_que_o_app_mostra(monkeypatch):
    # 24/10/2026: o produto curtido estava em 1º, mas com o nome diferente do da API. O 1º vale
    # com 80% das palavras, e a janela e a tela final conferem o nome da lista.
    _avisos(monkeypatch)
    anexados = []
    aparelho = AparelhoComJanela(tela=_lista(PARECIDO, PANELA), nome_na_janela=PARECIDO)
    ok, motivo = ps.adicionar_produto(aparelho, {"produto": VESTIDO}, anexados)
    assert ok and aparelho.toques == [(925, 977)] and anexados == [PARECIDO]
    assert _anexar_linhas() == [("anexado", "no topo, pelo nome")]


def test_o_2o_produto_do_video_procura_entre_os_que_sobraram_no_topo(monkeypatch):
    _avisos(monkeypatch)
    anexados = []
    aparelho = AparelhoComJanela(tela=_lista(FIBRA, PARECIDO), nome_na_janela=PARECIDO)
    assert ps.adicionar_produto(aparelho, {"produto": VESTIDO}, anexados, no_topo=2)[0]
    assert aparelho.toques == [(925, 1257)] and anexados == [PARECIDO]


def test_nome_parecido_fora_do_topo_nao_vale(monkeypatch):
    # Só os curtidos agora (no topo) valem pelo nome parecido; mais embaixo, só o nome igual.
    _avisos(monkeypatch)
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)
    aparelho = AparelhoComJanela(tela=_lista(FIBRA, PARECIDO), nome_na_janela=PARECIDO)
    assert not ps.adicionar_produto(aparelho, {"produto": VESTIDO}, [], no_topo=1)[0]
    assert aparelho.toques == []


def test_ultima_chance_a_ia_confere_a_foto_do_1o_e_ele_e_anexado(monkeypatch):
    avisos = _avisos(monkeypatch)
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)
    chamadas = _ia_da_foto(monkeypatch, confere=True)
    anexados = []
    aparelho = AparelhoComPrint(tela=_lista(FIBRA, PANELA), nome_na_janela=FIBRA)
    ok, motivo = ps.adicionar_produto(aparelho, {"produto": VESTIDO, "arquivo": "video.mp4"}, anexados)
    assert ok and aparelho.toques == [(925, 977)] and anexados == [FIBRA] and avisos == []
    # A IA recebe o recorte do 1º, em PNG, com a régua da mesma cor, VEZES_DA_IA vezes.
    assert len(chamadas) == ps.VEZES_DA_IA
    assert all(prompt == ps.PROMPT_ITEM_DA_LISTA and imagens[0][1] == "image/png" and imagens[0][0][:4] == b"\x89PNG"
               for prompt, imagens in chamadas)
    assert ("anexado", "o 1º da lista, pela IA") in _anexar_linhas()
    import registro_processos as rp
    assert ("confere", "o 1º da lista, pela foto") in [l[2:4] for l in rp.contagem("2000-01-01 00:00:00")
                                                      if l[1] == "conferência da IA (produto × vídeo)"]


def test_ultima_chance_recusada_pela_ia_nao_anexa_e_avisa(monkeypatch):
    import robo_shopee_video as robo
    avisos = _avisos(monkeypatch)
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)
    _ia_da_foto(monkeypatch, confere=False)
    aparelho = AparelhoComPrint(tela=_lista(FIBRA, PANELA), nome_na_janela=FIBRA)
    ok, motivo = ps.adicionar_produto(aparelho, {"produto": VESTIDO, "arquivo": "video.mp4"}, [])
    assert not ok and aparelho.toques == []
    assert len(avisos) == 1 and VESTIDO in avisos[0] and "o item da imagem" not in motivo
    assert robo.passo_do_motivo(motivo) == "anexar o produto"
    assert ("não anexado", "nem pelo nome nem pela foto do 1º da lista") in _anexar_linhas()


def test_a_ia_so_confirma_a_mesma_cor_da_foto(monkeypatch):
    # Escolha do Rafael (P19): a Shopee pede o produto exato do vídeo; outra cor não confirma.
    for prompt in (ps.PROMPT_PRODUTO_COM_FOTO, ps.PROMPT_ITEM_DA_LISTA):
        assert "da mesma cor" in prompt and "outra cor" in prompt
    assert "podem ser outra variação" not in ps.PROMPT_PRODUTO_COM_FOTO


def test_com_a_lista_limpa_o_anexar_nao_rola_a_lista(monkeypatch):
    # Escolha do Rafael (P27): com a limpeza anterior dada certo, os curtidos são só os de
    # agora; o produto não é procurado rolando a lista inteira, e o topo continua conferido.
    rolagens = []
    monkeypatch.setattr(ps, "rolar", lambda d, para_cima=False: rolagens.append(para_cima))
    detalhe = None
    import registro_processos as rp
    monkeypatch.setattr(ps.avisar_rafael, "mandar_texto", lambda texto: None)
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)

    class Celular:
        def dump_hierarchy(self):
            return TELA_CURTIDAS

    ok, _ = ps.adicionar_produto(Celular(), {"produto": "Panela de Pressão Inox"}, rolar_a_lista=False)
    detalhe = [l for l in rp.contagem("2000-01-01 00:00:00")
               if l[1] == "anexar o produto" and l[2] == "nome não achado em Minhas Curtidas"][0][3]
    assert not ok and rolagens == [] and detalhe.endswith("0 rolada(s); lista limpa") and len(detalhe) <= 120
    # Sem a lista limpa, rola como sempre.
    ps.adicionar_produto(Celular(), {"produto": "Panela de Pressão Inox"})
    assert False in rolagens



class CoracaoLento(Coracao):
    """A página do produto novo (coração vazio) que troca só na 2ª leitura depois do toque, ou só no 2º toque."""

    def __init__(self, leituras_ate_trocar=0, toques_ate_curtir=1):
        super().__init__()
        self.completa = TELA_PRODUTO
        self.leituras, self.leituras_ate_trocar, self.toques_ate_curtir = 0, leituras_ate_trocar, toques_ate_curtir

    def click(self, x, y):
        self.toques.append((x, y))
        if len(self.toques) >= self.toques_ate_curtir:
            self.leituras = 0
            self.vai_curtir = True

    def dump_hierarchy(self):
        if not self.toques:
            return self.tela
        if getattr(self, "vai_curtir", False):
            self.leituras += 1
            if self.leituras > self.leituras_ate_trocar:
                return CURTIDO
        return TELA_PRODUTO


def test_coracao_que_demora_a_trocar_e_esperado_sem_tocar_de_novo(monkeypatch):
    # 24/10, 18:32: o robô tocou no coração e leu a tela antes de ela mudar.
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)
    aparelho = CoracaoLento(leituras_ate_trocar=2)
    assert ps.curtir_na_pagina(aparelho, TELA_PRODUTO) == (True, "produto curtido")
    assert len(aparelho.toques) == 1


def test_toque_no_coracao_que_nao_pega_ganha_mais_um(monkeypatch):
    import registro_processos as rp
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)
    aparelho = CoracaoLento(toques_ate_curtir=2)
    assert ps.curtir_na_pagina(aparelho, TELA_PRODUTO)[0] and len(aparelho.toques) == 2
    assert ("curtido agora", "no 2º toque") in {(l[2], l[3]) for l in rp.contagem("2000-01-01 00:00:00")
                                                if l[1] == "curtir o produto"}
    # Nem no 2º toque: para, e o registro diz.
    aparelho = CoracaoLento(toques_ate_curtir=9)
    assert ps.curtir_na_pagina(aparelho, TELA_PRODUTO) == (False, "toquei no coração, mas o produto não ficou curtido")
    assert len(aparelho.toques) == 2

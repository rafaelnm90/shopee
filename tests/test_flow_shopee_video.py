"""flow_shopee_video: o teste da P229 1 monta o pedido no Flow como mapeado, só gera com tudo conferido e o log público não tem o produto."""
import contextlib
import io
import json
from xml.sax.saxutils import quoteattr

import pytest
from PIL import Image

import db
import flow_shopee_video as flow

CUSTOS = {"Omni 1.2 Flash": 24, "Omni 1.1 Flash": 12, "Veo 3.1 - Lite": 10}
SELETOR = flow.PACOTE_DO_SELETOR
# O arquivo que o Baixar do Flow deixa no celular (o nome é o título que o Flow dá ao vídeo).
BAIXADO = "/sdcard/Download/Mulher usando o copo.mp4"
MENU_DO_VIDEO = (("Gostei", 278, ""), ("Renomear", 425, ""), ("Reutilizar comando", 530, ""), ("Favorito", 635, ""),
                 ("Baixar", 740, "baixar"), ("Enviar", 845, ""), ("Compartilhar", 950, ""),
                 ("Compartilhar no YouTube", 1055, ""), ("Enviar feedback", 1202, ""))


def _no(caixa, classe="android.view.View", desc="", texto="", pacote=flow.PACOTE, clicavel=True, rid="", marcado=False):
    x1, y1, x2, y2 = caixa
    return (f'<node index="0" text={quoteattr(texto)} resource-id={quoteattr(rid)} class="{classe}" '
            f'package="{pacote}" content-desc={quoteattr(desc)} clickable="{str(clicavel).lower()}" '
            f'checked="{str(marcado).lower()}" visible-to-user="true" bounds="[{x1},{y1}][{x2},{y2}]" />')


class Campo:
    def __init__(self, celular):
        self.celular, self.exists = celular, True

    def set_text(self, texto):
        self.celular.texto = texto


class Resposta:
    def __init__(self, output=""):
        self.output = output


class Flow:
    """O celular de mentira com o Flow: as telas mapeadas em 15/11/2026 e o que cada toque faz."""

    def __init__(self, custos=CUSTOS, termos=False):
        self.custos, self.termos = custos, termos
        self.tela, self.texto, self.modelo, self.foto = "fora", "", "Omni 1.2 Flash", False
        self.folha = self.lista = self.marcada = self.gerado = False
        self.na_galeria, self.comandos, self.toques = "", [], []
        # Depois do Gerar: quantas leituras o quadrado mostra "Gerando…", de que modelo é o vídeo pronto
        # e o que o Baixar faz.
        self.gerando_leituras, self.modelo_do_video, self.filtro = 0, "", False
        self.falha_ao_gerar = self.baixado = False
        # A janela "Baixar vídeo" (15/11): o 720p "Tamanho original" vem marcado e o 1080p fica livre
        # (sem custo na tela); o 4K pede outro plano. Os toques no plano ficam em toques_proibidos.
        self.original_marcado, self.maior_marcado, self.toques_proibidos = True, False, []
        self.sem_1080p = self.custo_no_1080p = self.aviso_de_credito = self.maior_nao_marca = False
        self.geracoes, self.puxados = 0, []
        # O projeto do robô na lista do início (o Rafael o renomeou em 15/11) e os toques fora dele.
        self.projeto_do_robo, self.fora_do_projeto = "Shopee Video", []
        # As versões do vídeo aberto (o modelo de cada uma) e a que aparece; vazio = só a do vídeo gerado.
        self.versoes, self.versao = [], 0
        # Como no app (15/11): a coluna das versões só aparece algumas leituras depois do player.
        self.atraso_das_versoes, self.leituras_do_video = 2, 0

    # --- o que o uiautomator2 faz
    def app_start(self, pacote, stop=False, wait=False):
        self.tela = "inicio"

    def screen_on(self):
        pass

    def __call__(self, **seletor):
        return Campo(self)

    def push(self, origem, destino):
        self.na_galeria = destino.rsplit("/", 1)[-1]

    def shell(self, partes):
        self.comandos.append(partes)
        if partes and partes[0] == "find":
            return Resposta(f"1763216000 2345678 {BAIXADO}\n" if self.baixado else "")
        return Resposta(self.na_galeria if "content" in partes else "")

    def pull(self, origem, destino):
        self.puxados.append(origem)
        with open(destino, "wb") as arquivo:
            arquivo.write(b"\0" * 2048)

    def nos(self):
        """(caixa, xml do nó, o que o toque faz) da tela de agora."""
        nos = []
        if self.tela == "inicio":
            nos += [((775, 908, 1038, 1034), _no((775, 908, 1038, 1034), "android.widget.Button", "Novo"), "novo"),
                    ((42, 900, 1038, 1080), _no((42, 900, 1038, 1080), desc="O título do projeto é nov. 15, 12:09 PM",
                                                 clicavel=False), "outro")]
            if self.projeto_do_robo:
                # Como no Flow (15/11): a descrição diz o título e quantos vídeos e imagens o projeto tem.
                nos.append(((42, 1100, 1038, 1300), _no((42, 1100, 1038, 1300), clicavel=False,
                                                        desc=f"O título do projeto é {self.projeto_do_robo}, 1 vídeo, 4 imagens"),
                            "projeto"))
            if self.termos:
                nos.append(((0, 1400, 1080, 1500), _no((0, 1400, 1080, 1500), texto="Aceitar os Termos de Serviço"), ""))
        elif self.tela == "projeto":
            nos += [((0, 152, 1080, 278), _no((0, 152, 1080, 278), desc=self.projeto_do_robo, clicavel=False), ""),
                    ((42, 330, 191, 425), _no((42, 330, 191, 425), "android.widget.Button", "Tudo", clicavel=False), ""),
                    ((500, 330, 737, 425), _no((500, 330, 737, 425), "android.widget.Button", "Vídeos", clicavel=False),
                     "filtro"),
                    ((403, 2171, 677, 2339), _no((403, 2171, 677, 2339), "android.widget.Button", "Criar"), "pedido")]
            if self.gerado and self.gerando_leituras > 0:
                nos.append(((0, 466, 537, 1422), _no((0, 466, 537, 1422), desc="1%\nGerando…"), ""))
            elif self.gerado:
                nos.append(((0, 466, 537, 1422), _no((0, 466, 537, 1422), desc="Mulher usando o copo, 1 item"), "video"))
            if not self.filtro:
                nos.append(((543, 466, 1080, 1004), _no((543, 466, 1080, 1004), desc="Copo na mesa, 1 item"), "foto"))
        elif self.tela == "video":
            versoes = self.versoes or [self.modelo_do_video]
            # A versão estendida (a 2ª em diante) tem só o nome no título, sem o modelo.
            titulo = f"Mulher usando o copo\n{versoes[self.versao]}\n720p" if self.versao == 0 else "Mulher usando o copo"
            nos += [((0, 131, 1080, 299), _no((0, 131, 1080, 299), desc=titulo, clicavel=False), ""),
                    ((42, 152, 168, 278), _no((42, 152, 168, 278), "android.widget.Button", "Fechar"), "projeto"),
                    ((891, 152, 1017, 278), _no((891, 152, 1017, 278), "android.widget.Button", "Mais opções"), "menu_video"),
                    ((0, 309, 1080, 2184), _no((0, 309, 1080, 2184),
                                                desc=f"Vídeo tocando, {self.versao + 1} de {len(versoes)}\n0:08"), ""),
                    ((42, 2216, 530, 2363), _no((42, 2216, 530, 2363), "android.widget.Button", "Editar"), ""),
                    ((551, 2216, 1038, 2363), _no((551, 2216, 1038, 2363), "android.widget.Button", "Estender"), "")]
            if len(versoes) > 1 and self.leituras_do_video >= self.atraso_das_versoes:
                nos += [((962, y, 1025, y + 63), _no((962, y, 1025, y + 63), "android.widget.ImageView"), f"versao:{i}")
                        for i, y in enumerate(range(1178, 1178 + 74 * len(versoes), 74))]
        elif self.tela == "menu_video":
            nos.append(((0, 0, 1080, 2520), _no((0, 0, 1080, 2520), desc="Dispensar menu"), "video"))
            nos += [((341, y, 954, y + 105), _no((341, y, 954, y + 105), "android.widget.Button", nome), acao)
                    for nome, y, acao in MENU_DO_VIDEO]
        elif self.tela == "tamanho":
            nos += [((0, 0, 1080, 2520), _no((0, 0, 1080, 2520), desc="Dispensar"), "video"),
                    ((168, 874, 912, 947), _no((168, 874, 912, 947), desc="Baixar vídeo", clicavel=False), ""),
                    ((168, 989, 912, 1451), _no((168, 989, 912, 1451), "android.widget.RadioGroup", clicavel=False,
                                                desc="Escolha uma resolução para fazer o download.\n4K"), ""),
                    ((168, 1136, 912, 1241), _no((168, 1136, 912, 1241), desc="720p\nTamanho original"), "original"),
                    ((168, 1165, 215, 1212), _no((168, 1165, 215, 1212), "android.widget.RadioButton",
                                                 marcado=self.original_marcado), "original")]
            if self.aviso_de_credito:
                nos.append(((168, 947, 912, 989), _no((168, 947, 912, 989), clicavel=False,
                                                      desc="Aumentar a resolução usa 10 créditos de IA"), ""))
            if not self.sem_1080p:
                maior = "1080p\nAumentar a resolução" + ("\n10 créditos" if self.custo_no_1080p else "")
                nos += [((168, 1241, 912, 1346), _no((168, 1241, 912, 1346), desc=maior), "maior"),
                        ((168, 1270, 215, 1317), _no((168, 1270, 215, 1317), "android.widget.RadioButton",
                                                     marcado=self.maior_marcado), "maior")]
            nos.append(((302, 1378, 807, 1420), _no((302, 1378, 807, 1420), desc="Assine um plano com IA do Google"), "plano"))
            # Como no app (15/11): com o 1080p marcado, o botão vira "Aumentar resolução e baixar", mais largo.
            if self.maior_marcado:
                nos.append(((290, 1514, 912, 1640), _no((290, 1514, 912, 1640), "android.widget.Button",
                                                        "Aumentar resolução e baixar"), "confirmar"))
            else:
                nos.append(((677, 1514, 912, 1640), _no((677, 1514, 912, 1640), "android.widget.Button", "Baixar"), "confirmar"))
        elif self.tela == "seletor":
            nos += [((0, 630, 354, 984), _no((0, 630, 354, 984), "android.widget.FrameLayout",
                                              "Item Foto criado em 15 de nov. de 2026 9:48:38 AM", pacote=SELETOR), "marcar"),
                    ((700, 2230, 1070, 2330), _no((700, 2230, 1070, 2330), "android.widget.Button", texto="Adicionar (1)",
                                                   pacote=SELETOR, rid=f"{SELETOR}:id/button_add"), "adicionar")]
        elif self.tela in ("pedido", "menu"):
            nos += [((272, 900, 398, 1000), _no((272, 900, 398, 1000), "android.widget.Button", "Imagem"), ""),
                    ((419, 900, 661, 1000), _no((419, 900, 661, 1000), "android.widget.Button", "Vídeo"), ""),
                    ((45, 1100, 1035, 1200), _no((45, 1100, 1035, 1200), "android.widget.EditText", texto=self.texto), ""),
                    ((45, 1200, 171, 1300), _no((45, 1200, 171, 1300), "android.widget.Button", "Adicionar mídia"), "menu"),
                    ((548, 1200, 867, 1300), _no((548, 1200, 867, 1300), "android.widget.Button", f"{self.modelo}\nx1"), "folha"),
                    ((888, 1200, 1014, 1300), _no((888, 1200, 1014, 1300), "android.widget.Button", "Gerar"), "gerar")]
            if self.foto:
                nos.append(((66, 1000, 213, 1095), _no((66, 1000, 213, 1095), "android.widget.ImageView"), ""))
            if self.tela == "menu":
                nos += [((63, 700, 383, 790), _no((63, 700, 383, 790), "android.widget.Button", "Capturar"), ""),
                        ((63, 790, 383, 880), _no((63, 790, 383, 880), "android.widget.Button", "Imagens"), "seletor")]
            if self.folha:
                nos += [((259, 1400, 823, 1460), _no((259, 1400, 823, 1460), desc="A geração vai usar ", clicavel=False), ""),
                        ((535, 1460, 823, 1520), _no((535, 1460, 823, 1520), "android.widget.Button",
                                                      f"{self.custos[self.modelo]} créditos de IA"), ""),
                        ((540, 1550, 1051, 1650), _no((540, 1550, 1051, 1650), desc="9:16\nGuia 2 de 2"), "")]
                # Como no app (15/11): o Veo 3.1 - Lite não tem a escolha da resolução.
                if self.modelo != "Veo 3.1 - Lite":
                    nos.append(((540, 1660, 1051, 1760), _no((540, 1660, 1051, 1760), desc="720p\nGuia 2 de 2"), ""))
                nos += [((29, 1770, 284, 1870), _no((29, 1770, 284, 1870), desc="x1\nGuia 1 de 4"), ""),
                        ((24, 2244, 1056, 2370), _no((24, 2244, 1056, 2370), desc=self.modelo), "lista")]
            if self.lista:
                nos += [((24, 1880, 1056, 1990), _no((24, 1880, 1056, 1990), desc="Omni 1.1 Flash\n12 créditos / video"),
                         "Omni 1.1 Flash"),
                        ((24, 2000, 1056, 2100), _no((24, 2000, 1056, 2100), desc="Veo 3.1 - Lite\n10 créditos / video"),
                         "Veo 3.1 - Lite"),
                        ((24, 2110, 1056, 2230), _no((24, 2110, 1056, 2230), desc="Omni 1.2 Flash\n24 créditos / video"),
                         "Omni 1.2 Flash")]
        return nos

    def dump_hierarchy(self):
        xml = '<?xml version="1.0" ?><hierarchy rotation="0">' + "".join(no for _, no, _ in self.nos()) + "</hierarchy>"
        if self.tela == "projeto" and self.gerando_leituras > 0:
            self.gerando_leituras -= 1
        if self.tela == "video":
            self.leituras_do_video += 1
        return xml

    def click(self, x, y):
        self.toques.append((x, y))
        # O de cima ganha: a folha e a lista vêm depois na tela.
        for (x1, y1, x2, y2), _no_xml, acao in reversed(self.nos()):
            if x1 <= x <= x2 and y1 <= y <= y2:
                break
        else:
            return
        if acao in ("projeto", "pedido", "menu", "seletor"):
            self.tela = acao
        elif acao == "folha":
            self.folha = True
        elif acao == "lista":
            self.lista = True
        elif acao in CUSTOS:
            self.modelo, self.lista = acao, False
        elif acao == "marcar":
            self.marcada = True
        elif acao == "adicionar" and self.marcada:
            self.tela, self.foto = "pedido", True
        elif acao == "gerar":
            self.geracoes += 1
            self.tela = "projeto"
            if not self.falha_ao_gerar:
                self.gerado, self.gerando_leituras, self.modelo_do_video = True, 2, self.modelo
        elif acao.startswith("versao:"):
            self.versao = int(acao.split(":")[1])
        elif acao in ("novo", "outro"):
            self.fora_do_projeto.append(acao)
        elif acao == "filtro":
            self.filtro = True
        elif acao in ("video", "menu_video"):
            if acao == "video" and self.tela != "menu_video":
                self.leituras_do_video = 0
            self.tela = acao
        elif acao == "baixar":
            self.tela = "tamanho"
        elif acao == "maior":
            if not self.maior_nao_marca:
                self.maior_marcado, self.original_marcado = True, False
        elif acao == "original":
            self.maior_marcado, self.original_marcado = False, True
        elif acao == "plano":
            self.toques_proibidos.append((x, y))
        elif acao == "confirmar":
            self.tela = "video"
            self.baixado = "1080p" if self.maior_marcado else "720p" if self.original_marcado else False


@pytest.fixture
def celular(bm, monkeypatch, tmp_path):
    aparelho = Flow()
    guardados = []
    monkeypatch.setattr(flow.time, "sleep", lambda segundos: None)
    monkeypatch.setattr(flow.celular_robo, "tela_acesa", lambda: True)
    monkeypatch.setattr(flow.celular_robo, "tela_de_bloqueio", lambda: False)
    monkeypatch.setattr(flow.ps, "conectar", lambda celular=False: aparelho)
    monkeypatch.setattr(flow.casos_robo, "guardar",
                        lambda d, acao, resultado, motivo, passo="", **extra: guardados.append((resultado, motivo)) or "caso")
    monkeypatch.setattr(flow, "ESPERA_DA_TELA", 0.2)
    monkeypatch.setattr(flow, "ESPERA_DA_GERACAO", 30)
    monkeypatch.setattr(flow, "ESPERA_DA_VERSAO", 0.2)
    monkeypatch.setattr(flow, "PASTA", str(tmp_path / "flow"))
    monkeypatch.setattr(flow.celular_robo, "conectado", lambda: True)
    monkeypatch.setattr(flow.ps, "no_horario_das_rodadas", lambda: True)
    monkeypatch.setattr(flow.celular_robo, "trava", contextlib.contextmanager(lambda: (yield True)))
    aparelho.mandados, aparelho.conferidos, aparelho.fotos = [], [], []

    async def conferir(caminho, prompt, imagens=None):
        aparelho.conferidos.append((caminho, imagens[0][1]))
        return '{"mesmo_produto": true, "diferencas": "", "defeitos": "a mão muda de forma no fim"}'

    monkeypatch.setattr(flow.api_gemini, "analisar_video_gemini", conferir)
    # O anúncio que o Rafael abre para comparar (sem rede nos testes): o link curto vira o do produto.
    async def converter(link):
        return "https://shopee.com.br/produto-i.123.456?sp_atk=x"

    monkeypatch.setattr(flow.api_shopee, "link_para_converter", converter)
    monkeypatch.setattr(flow.avisar_rafael, "mandar_foto",
                        lambda caminho, legenda="": aparelho.fotos.append((caminho, legenda)) or True)
    monkeypatch.setattr(flow.avisar_rafael, "mandar_video",
                        lambda caminho, legenda="": aparelho.mandados.append((caminho, legenda)) or True)
    foto = tmp_path / "foto.jpg"
    foto.write_bytes(_jpeg())
    aparelho.guardados = guardados
    aparelho.teste = {"link": "https://s.shopee.com.br/abc", "nome": "Copo Térmico Inox", "foto": str(foto),
                      "prompt": "The exact stainless steel tumbler from the photo on a kitchen counter, slow push-in.",
                      "cena": "O copo na bancada da cozinha.", "videos": {}}
    return aparelho


def _jpeg():
    saida = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(saida, "JPEG")
    return saida.getvalue()


def test_sem_gerar_monta_o_pedido_inteiro_e_nao_toca_no_gerar(celular, capsys):
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=True) == 0
    assert not celular.gerado
    assert celular.foto and celular.modelo == "Veo 3.1 - Lite" and celular.texto == celular.teste["prompt"]
    assert ("tela", "pedido pronto, sem gerar") in celular.guardados
    # A foto do produto sai da galeria no fim.
    assert any(partes[:2] == ["rm", "-f"] for partes in celular.comandos)
    assert celular.fora_do_projeto == []
    saida = capsys.readouterr().out
    assert "Veo 3.1 - Lite, 10 créditos" in saida and "Copo" not in saida and "tumbler" not in saida


def test_gera_com_tudo_conferido_espera_pronto_e_baixa_o_video(celular, capsys):
    flow.guardar(teste=celular.teste)
    assert flow.no_celular(celular.teste, "Omni 1.1 Flash", 12, sem_gerar=False) == 0
    assert celular.gerado and celular.geracoes == 1
    videos = db.ler_config(flow.CHAVE, {})["teste"]["videos"]
    assert videos["Omni 1.1 Flash"]["estado"] == "baixado" and videos["Omni 1.1 Flash"]["custo"] == 12
    assert videos["Omni 1.1 Flash"]["arquivo"].endswith("video_2.mp4")
    assert any("esperando o vídeo" in motivo for _, motivo in celular.guardados)
    # O arquivo veio do celular, e o celular ficou sem ele e sem a marca do Baixar.
    assert celular.puxados == [BAIXADO]
    assert ["rm", "-f", BAIXADO, flow.MARCA_DO_BAIXAR] in celular.comandos
    saida = capsys.readouterr().out
    assert "Gerar tocado (Omni 1.1 Flash, 12 créditos)" in saida and "Flow: vídeo baixado (1080p, 0.0 MB" in saida
    assert "Mulher" not in saida and ".mp4" not in saida
    assert flow.proximo_modelo(db.ler_config(flow.CHAVE, {})["teste"]) == ("Veo 3.1 - Lite", 10)


def test_teste_gera_baixa_confere_e_manda_no_privado(celular, capsys):
    flow.guardar(teste=celular.teste)
    assert flow.teste() == 0
    assert celular.geracoes == 1 and celular.modelo_do_video == "Veo 3.1 - Lite"
    assert len(celular.mandados) == 1 and celular.conferidos[0][1] == "image/jpeg"
    caminho, legenda = celular.mandados[0]
    assert caminho.endswith("video_1.mp4")
    for trecho in ("vídeo 1 de 3", "Veo 3.1 - Lite (10 créditos de IA)", "Copo Térmico Inox", "O copo na bancada",
                   "o produto é o mesmo da foto do anúncio", "a mão muda de forma no fim", "Nada foi postado"):
        assert trecho in legenda
    video = db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]
    assert video["estado"] == "enviado" and video["mesmo_produto"] is True
    # Pedido do Rafael (15/11): logo depois do vídeo, a foto do anúncio com o link dele, para comparar.
    assert celular.fotos == [(celular.teste["foto"], "🖼️ Foto do anúncio, para comparar com o vídeo 1 de 3 do teste "
                                                     "do Flow\n🔗 Anúncio: https://shopee.com.br/product/123/456")]
    saida = capsys.readouterr().out
    assert "conferência da IA: mesmo produto" in saida and "vídeo mandado no privado do Rafael" in saida
    assert "foto e link do anúncio mandados" in saida and "shopee.com.br" not in saida
    assert "Copo" not in saida and "tumbler" not in saida and "Mulher" not in saida


def test_foto_do_anuncio_que_nao_vai_nao_desfaz_o_envio_do_video(celular, monkeypatch, capsys):
    def falha(caminho, legenda=""):
        raise OSError("sem rede")

    monkeypatch.setattr(flow.avisar_rafael, "mandar_foto", falha)
    flow.guardar(teste=celular.teste)
    assert flow.teste() == 0
    assert len(celular.mandados) == 1
    assert db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]["estado"] == "enviado"
    assert "a foto do anúncio não foi ao privado" in capsys.readouterr().out


def test_link_do_anuncio_sem_o_produto_fica_o_da_fonte(monkeypatch):
    async def falha(link):
        raise OSError("sem rede")

    monkeypatch.setattr(flow.api_shopee, "link_para_converter", falha)
    assert flow.link_do_anuncio("https://s.shopee.com.br/abc") == "https://s.shopee.com.br/abc"

    async def busca(link):
        return "https://shopee.com.br/search?keyword=copo"

    monkeypatch.setattr(flow.api_shopee, "link_para_converter", busca)
    assert flow.link_do_anuncio("https://s.shopee.com.br/abc") == "https://s.shopee.com.br/abc"


def test_video_ja_gerado_e_baixado_e_mandado_sem_gerar_outro(celular):
    celular.teste["videos"] = {"Veo 3.1 - Lite": {"custo": 10, "estado": "gerando"}}
    flow.guardar(teste=celular.teste)
    celular.gerado, celular.modelo_do_video = True, "Veo 3.1 - Lite"
    assert flow.teste() == 0
    assert celular.geracoes == 0 and celular.na_galeria == ""
    assert len(celular.mandados) == 1
    teste = db.ler_config(flow.CHAVE, {})["teste"]
    assert teste["videos"]["Veo 3.1 - Lite"]["estado"] == "enviado"
    assert flow.proximo_modelo(teste) == ("Omni 1.1 Flash", 12)


def test_video_mais_novo_de_outro_modelo_nao_e_baixado_nem_mandado(celular):
    celular.teste["videos"] = {"Veo 3.1 - Lite": {"custo": 10, "estado": "gerando"}}
    flow.guardar(teste=celular.teste)
    celular.gerado, celular.modelo_do_video = True, "Omni 1.1 Flash"
    assert flow.teste() == 1
    assert ("parou", "baixar: o vídeo mais novo não é do modelo do teste") in celular.guardados
    assert not celular.baixado and celular.mandados == []
    assert db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]["estado"] == "gerando"


def test_baixar_marca_o_1080p_e_confirma(celular):
    # O Rafael (15/11): "Mas se podemos baixar 1080 pq vou baixar 720?". Na janela da resolução, o robô
    # marca o 1080p, confere que ficou marcado e só então toca no Baixar dela; nunca no plano do 4K.
    flow.guardar(teste=celular.teste)
    assert flow.teste() == 0
    assert celular.baixado == "1080p" and celular.toques_proibidos == [] and len(celular.mandados) == 1
    video = db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]
    assert video["resolucao"] == "1080p" and video["estado"] == "enviado"
    assert "📐 Resolução: 1080p (aumentada pelo Flow no Baixar)" in celular.mandados[0][1]


def test_baixar_com_custo_no_1080p_baixa_o_tamanho_original(celular):
    # Com crédito na linha do 1080p (ou na janela), o robô não o escolhe: o tamanho original vem marcado.
    celular.custo_no_1080p = True
    flow.guardar(teste=celular.teste)
    assert flow.teste() == 0
    assert celular.baixado == "720p" and (191, 1293) not in celular.toques and celular.toques_proibidos == []
    assert db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]["resolucao"] == "720p"
    assert "📐 Resolução: 720p (o tamanho original)" in celular.mandados[0][1]


def test_aviso_de_credito_na_janela_tira_o_1080p():
    aparelho = Flow()
    aparelho.tela = "tamanho"
    assert flow.janela_do_baixar(aparelho.dump_hierarchy())["1080p"] == {
        "centro": (191, 1293), "marcada": False, "texto": "1080p aumentar a resolução "}
    aparelho.maior_marcado, aparelho.original_marcado = True, False
    janela = flow.janela_do_baixar(aparelho.dump_hierarchy())
    assert janela["1080p"]["marcada"] and not janela["original"]["marcada"] and janela["baixar"] == (601, 1577)
    aparelho.maior_marcado, aparelho.original_marcado = False, True
    aparelho.aviso_de_credito = True
    janela = flow.janela_do_baixar(aparelho.dump_hierarchy())
    assert janela["1080p"] is None and janela["original"]["marcada"] and janela["baixar"] == (794, 1577)


def test_baixar_sem_o_1080p_baixa_o_tamanho_original(celular):
    celular.sem_1080p = True
    flow.guardar(teste=celular.teste)
    assert flow.teste() == 0
    assert celular.baixado == "720p" and celular.toques_proibidos == [] and len(celular.mandados) == 1


def test_baixar_com_o_1080p_que_nao_fica_marcado_para(celular, monkeypatch):
    monkeypatch.setattr(flow, "ESPERA_DA_JANELA_DO_BAIXAR", 0.2)
    celular.maior_nao_marca = True
    flow.guardar(teste=celular.teste)
    assert flow.teste() == 1
    assert celular.tela == "tamanho" and not celular.baixado and celular.mandados == []
    assert ("parou", "baixar: o 1080p não ficou marcado; o robô não baixa sem conferir a resolução") \
        in celular.guardados
    assert db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]["estado"] == "gerando"


def test_baixar_sem_nada_marcado_para_sem_escolher(celular):
    celular.sem_1080p, celular.original_marcado = True, False
    flow.guardar(teste=celular.teste)
    assert flow.teste() == 1
    assert celular.tela == "tamanho" and celular.mandados == [] and celular.toques_proibidos == []
    assert ("parou", "baixar: nem o 1080p nem o tamanho original estão marcados; o robô não escolhe outra resolução") \
        in celular.guardados
    assert db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]["estado"] == "gerando"


def test_gerar_sem_o_gerando_para_e_guarda_a_tela(celular, monkeypatch):
    monkeypatch.setattr(flow, "ESPERA_DO_GERANDO", 0.05)
    celular.falha_ao_gerar = True
    flow.guardar(teste=celular.teste)
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=False) == 1
    assert ("parou", "gerar: o Flow não mostrou o vídeo sendo gerado") in celular.guardados
    assert celular.puxados == []


def test_baixado_que_nao_chegou_ao_rafael_vai_sem_o_celular(celular, monkeypatch, tmp_path):
    arquivo = tmp_path / "video_1.mp4"
    arquivo.write_bytes(b"\0" * 2048)
    celular.teste["videos"] = {"Veo 3.1 - Lite": {"custo": 10, "estado": "baixado", "arquivo": str(arquivo)}}
    flow.guardar(teste=celular.teste)
    monkeypatch.setattr(flow.celular_robo, "conectado", lambda: False)
    assert flow.teste() == 0
    assert celular.toques == [] and celular.mandados[0][0] == str(arquivo)


def test_envio_recusado_fica_para_o_proximo_teste(celular, monkeypatch, capsys):
    flow.guardar(teste=celular.teste)
    monkeypatch.setattr(flow.avisar_rafael, "mandar_video", lambda caminho, legenda="": False)
    assert flow.teste() == 1
    assert db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]["estado"] == "baixado"
    assert "o próximo teste manda de novo" in capsys.readouterr().out


def test_conferencia_e_legenda():
    assert flow.ler_conferencia('ok {"mesmo_produto": false, "diferencas": "a  tampa\\nmudou", "defeitos": ""}') == \
        {"mesmo": False, "diferencas": "a tampa mudou", "defeitos": ""}
    assert flow.ler_conferencia("sem json") == {"mesmo": None, "diferencas": "", "defeitos": ""}
    assert flow.ler_conferencia('{"mesmo_produto": "sim"}')["mesmo"] is None
    teste = {"nome": "Copo Térmico Inox", "cena": "O copo na bancada."}
    diferente = flow.legenda_do_video(teste, "Omni 1.1 Flash", 12, {"mesmo": False, "diferencas": "a tampa mudou",
                                                                     "defeitos": ""})
    assert "vídeo 2 de 3" in diferente and "o produto muda: a tampa mudou" in diferente
    assert "O que parece IA" not in diferente and "último dos 3" not in diferente
    ultimo = flow.legenda_do_video(dict(teste, nome="X" * 2000), "Omni 1.2 Flash", 24,
                                   {"mesmo": None, "diferencas": "", "defeitos": ""})
    assert "vídeo 3 de 3" in ultimo and len(ultimo) <= 1000
    assert "último dos 3" in flow.legenda_do_video(teste, "Omni 1.2 Flash", 24,
                                                   {"mesmo": True, "diferencas": "", "defeitos": ""})


def test_leitura_das_telas_depois_do_gerar():
    projeto = ('<hierarchy>' + _no((0, 466, 537, 1422), desc="1%\nGerando…")
               + _no((543, 466, 1080, 1004), desc="Copo na mesa, 1 item") + '</hierarchy>')
    assert flow.gerando(projeto) and flow.quadro_mais_novo(projeto) == (811, 735)
    pronto = projeto.replace("1%&#10;Gerando…", "Mulher usando o copo, 1 item")
    assert not flow.gerando(pronto) and flow.quadro_mais_novo(pronto) == (268, 944)
    aberto = ('<hierarchy>' + _no((0, 131, 1080, 299), desc="Mulher usando o copo\nVeo 3.1 - Lite\n720p", clicavel=False)
              + _no((0, 309, 1080, 2184), desc="Vídeo tocando, 1 de 1\n0:07") + '</hierarchy>')
    assert flow.titulo_do_video(aberto) == ["Mulher usando o copo", "Veo 3.1 - Lite", "720p"]
    assert flow.titulo_do_video(projeto) is None
    assert not flow.pede_escolha(aberto)
    assert flow.janela_do_baixar(aberto) is None
    assert flow.pede_escolha('<hierarchy>' + _no((100, 1000, 980, 1100), "android.widget.Button", "1080p") + '</hierarchy>')
    assert flow.pede_escolha('<hierarchy>' + _no((0, 0, 10, 10), texto="Permitir",
                                                 pacote="com.google.android.permissioncontroller") + '</hierarchy>')


def test_arquivos_novos_do_baixar():
    class Celular:
        def shell(self, partes):
            assert partes[0] == "find" and flow.MARCA_DO_BAIXAR in partes and "*.mp4" in partes
            return Resposta("find: /sdcard/Movies: No such file or directory\n"
                            "1763216000 100 /sdcard/Download/velho.mp4\n"
                            "1763216200 512 /sdcard/Download/.pending-1763216200-Vídeo novo.mp4\n"
                            "1763216100 2048 /sdcard/Download/Vídeo com espaço.mp4\n")

    assert flow.arquivos_novos(Celular()) == [("/sdcard/Download/Vídeo com espaço.mp4", 2048),
                                              ("/sdcard/Download/velho.mp4", 100)]


def test_flow_aberto_no_veo_lite_troca_o_modelo_antes_das_opcoes(celular):
    # O vídeo 2 do teste (15/11): o Flow abriu no último modelo usado, o Veo 3.1 - Lite, que não tem
    # a escolha da resolução; o robô parava procurando o 720p. Agora escolhe o modelo e depois as opções.
    celular.modelo = "Veo 3.1 - Lite"
    flow.guardar(teste=celular.teste)
    assert flow.no_celular(celular.teste, "Omni 1.1 Flash", 12, sem_gerar=False) == 0
    assert celular.gerado and celular.modelo_do_video == "Omni 1.1 Flash"
    assert not any(resultado == "parou" for resultado, _ in celular.guardados)


def test_custo_diferente_na_tela_nao_gera(celular, capsys):
    celular.custos = dict(CUSTOS, **{"Omni 1.2 Flash": 30})
    assert flow.no_celular(celular.teste, "Omni 1.2 Flash", 24, sem_gerar=False) == 1
    assert not celular.gerado
    assert ("parou", "antes do Gerar: o custo na tela não é o esperado") in celular.guardados
    assert "Flow: parou: antes do Gerar: o custo na tela não é o esperado" in capsys.readouterr().out


def test_tela_de_termos_para_sem_tocar(celular):
    celular.termos = True
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=False) == 1
    assert not celular.gerado and celular.toques == []
    assert any("termos" in motivo for resultado, motivo in celular.guardados if resultado == "parou")


def test_pedido_com_foto_de_antes_para_sem_por_outra_e_sem_gerar(celular):
    celular.foto = True
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=False) == 1
    assert not celular.gerado and celular.tela == "pedido" and not celular.marcada
    assert ("parou", "pedido: já tinha foto ou texto de antes") in celular.guardados


def test_tela_de_bloqueio_nao_toca_em_nada(celular, monkeypatch, capsys):
    monkeypatch.setattr(flow.celular_robo, "tela_de_bloqueio", lambda: True)
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=False) == 1
    assert celular.toques == [] and celular.na_galeria == ""
    assert "tela de bloqueio" in capsys.readouterr().out


class Subindo:
    """O pedido que sobe com o teclado: o Vídeo aparece embaixo e, na leitura seguinte, já no lugar."""

    def __init__(self, dialogo=False):
        self.leituras, self.toques, self.dialogo = 0, [], dialogo

    def dump_hierarchy(self):
        self.leituras += 1
        y = 1900 if self.leituras == 1 else 900
        nos = _no((419, y, 661, y + 100), "android.widget.Button", "Vídeo")
        if self.dialogo:
            nos += _no((154, 1335, 435, 1461), "android.widget.Button", texto="Cancelar", pacote=flow.PACOTE_DO_TECLADO)
        return f'<hierarchy>{nos}</hierarchy>'

    def click(self, x, y):
        self.toques.append((x, y))


def test_toca_so_quando_o_botao_para_de_subir(monkeypatch):
    monkeypatch.setattr(flow.time, "sleep", lambda segundos: None)
    celular = Subindo()
    flow.tocar(celular, "Vídeo", "modo vídeo")
    assert celular.toques == [(540, 950)] and celular.leituras >= 3


def test_aviso_do_teclado_para_sem_tocar(monkeypatch):
    monkeypatch.setattr(flow.time, "sleep", lambda segundos: None)
    celular = Subindo(dialogo=True)
    with pytest.raises(flow.Parada, match="aviso do teclado"):
        flow.tocar(celular, "Vídeo", "modo vídeo")
    assert celular.toques == []


def test_ordem_dos_modelos_do_mais_barato_ao_mais_caro():
    assert flow.proximo_modelo({}) == ("Veo 3.1 - Lite", 10)
    assert flow.proximo_modelo({"videos": {"Veo 3.1 - Lite": {}}}) == ("Omni 1.1 Flash", 12)
    assert flow.proximo_modelo({"videos": {"Veo 3.1 - Lite": {}, "Omni 1.1 Flash": {}}}) == ("Omni 1.2 Flash", 24)
    assert flow.proximo_modelo({"videos": dict.fromkeys(CUSTOS, {})}) is None
    assert sum(custo for _, custo in flow.MODELOS_DO_TESTE) <= 50


def test_resposta_da_ia():
    texto = 'Claro!\n{"serve": true, "motivo": "", "prompt": "Slow orbit  around\\nthe mug", "cena": "A caneca na mesa."}'
    assert flow.ler_resposta(texto) == {"serve": True, "motivo": "", "prompt": "Slow orbit around the mug",
                                        "cena": "A caneca na mesa."}
    assert flow.ler_resposta('{"serve": false, "motivo": "colagem de fotos"}')["serve"] is False
    assert flow.ler_resposta('{"serve": true, "prompt": ""}') is None
    assert flow.ler_resposta("não sei") is None and flow.ler_resposta(None) is None


def test_escolhe_o_primeiro_produto_com_foto_boa_e_o_log_nao_tem_o_produto(bm, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(flow, "PASTA", str(tmp_path))
    monkeypatch.setattr(flow.assistente, "candidatos_nao_usados",
                        lambda fonte: [("a", "a.mp4", "https://s.shopee.com.br/sem-foto", ""),
                                       ("b", "b.mp4", "https://s.shopee.com.br/com-foto", "")])
    monkeypatch.setattr(flow.ps, "anuncio_do_produto",
                        lambda video: {"foto": _jpeg(), "nome": "Copo Térmico Inox"} if "com-foto" in video["link"] else {})

    async def ia(prompt, imagens=None):
        assert "Copo Térmico Inox" in prompt and imagens[0][1] == "image/jpeg"
        return json.dumps({"serve": True, "motivo": "", "prompt": "The exact tumbler, slow push-in.",
                           "cena": "O copo na bancada."})

    monkeypatch.setattr(flow.api_gemini, "gerar_texto_gemini", ia)
    monkeypatch.setattr(flow.celular_robo, "conectado", lambda: False)
    assert flow.main(["teste", "--sem-gerar"]) == 1
    saida = capsys.readouterr().out
    assert "o 2º dos próximos vídeos da fonte" in saida and "celular: desconectado" in saida
    assert "Copo" not in saida and "tumbler" not in saida
    teste = db.ler_config(flow.CHAVE, {})["teste"]
    assert teste["nome"] == "Copo Térmico Inox" and teste["link"].endswith("com-foto") and teste["videos"] == {}
    # A foto do teste fica guardada para os 3 vídeos serem do mesmo produto.
    assert flow.teste_guardado()["foto"].endswith("foto_do_teste.jpg")


def test_foto_contada_com_as_opcoes_do_modelo_abertas():
    # Como no ensaio de 15/11: com as opções abertas, a caixa do pedido ocupa a tela toda, e a
    # miniatura da foto fica dentro dela, acima do +.
    aberta = ('<hierarchy>' + _no((0, 950, 1080, 2394), "android.widget.EditText", texto="The exact product, slow push-in.")
              + _no((63, 992, 210, 1118), "android.widget.ImageView")
              + _no((42, 1643, 168, 1769), "android.widget.Button", "Adicionar mídia")
              + _no((573, 1643, 870, 1769), "android.widget.Button", "Veo 3.1 - Lite\nx1")
              + _no((536, 1866, 820, 1929), "android.widget.Button", "10 créditos de IA") + '</hierarchy>')
    assert flow.fotos_no_pedido(aberta) == 1
    assert flow.pronto_para_gerar(aberta, "The exact product, slow push-in.", "Veo 3.1 - Lite", 10) == ""
    # Sem as opções: a miniatura acima da caixa do pedido, e o + embaixo dela.
    fechada = ('<hierarchy>' + _no((66, 1950, 213, 2076), "android.widget.ImageView")
               + _no((45, 2076, 1035, 2202), "android.widget.EditText")
               + _no((45, 2202, 171, 2328), "android.widget.Button", "Adicionar mídia") + '</hierarchy>')
    assert flow.fotos_no_pedido(fechada) == 1
    duas = fechada.replace('</hierarchy>', _no((230, 1950, 377, 2076), "android.widget.ImageView") + '</hierarchy>')
    assert flow.fotos_no_pedido(duas) == 2


def test_leitura_das_telas():
    folha = ('<hierarchy>' + _no((535, 1460, 823, 1520), "android.widget.Button", "24 créditos de IA")
             + _no((548, 1200, 867, 1300), "android.widget.Button", "Omni 1.2 Flash\nx1")
             + _no((24, 2110, 1056, 2230), desc="Veo 3.1 - Lite\n10 créditos / video") + '</hierarchy>')
    assert flow.custo_na_tela(folha) == 24 and flow.modelo_no_pedido(folha) == "Omni 1.2 Flash"
    inicio = ('<hierarchy>' + _no((42, 900, 1038, 1080), desc="O título do projeto é nov. 15, 12:09 PM")
              + _no((42, 1100, 1038, 1300), desc="O título do projeto é Shopee Video, 1 vídeo, 4 imagens")
              + '</hierarchy>')
    assert flow.projeto_na_lista(inicio) == (540, 1200)
    assert flow.projeto_na_lista(inicio.replace("Shopee Video,", "Shopee Video 2,")) is None
    assert flow.projeto_na_lista(inicio.replace("O título do projeto é Shopee Video", "shopee video")) == (540, 1200)
    assert flow.projeto_na_lista('<hierarchy>' + _no((42, 1100, 1038, 1300), desc="Shopee Video") + '</hierarchy>') \
        == (540, 1200)
    assert flow.custo_na_tela('<hierarchy></hierarchy>') is None


def test_sem_o_projeto_shopee_video_para_sem_criar_outro(celular):
    # O Rafael renomeou o projeto do robô para Shopee Video e pediu tudo nele (15/11): sem ele na lista,
    # o robô não cria um projeto novo nem entra em outro.
    celular.projeto_do_robo = ""
    assert flow.no_celular(celular.teste, "Veo 3.1 - Lite", 10, sem_gerar=False) == 1
    assert celular.fora_do_projeto == [] and not celular.gerado
    assert ("parou", "abrir o Flow: o projeto Shopee Video não está na lista; o robô não cria outro") \
        in celular.guardados


def test_video_com_a_versao_estendida_escolhe_a_do_modelo_do_teste(celular):
    # O Estender que o Rafael fez no vídeo do teste (15/11) ficou junto do original: no celular dele, o
    # vídeo abriu na versão estendida (Omni 1.2 Flash). O robô passa para a versão do Veo antes de baixar.
    celular.teste["videos"] = {"Veo 3.1 - Lite": {"custo": 10, "estado": "gerando"}}
    flow.guardar(teste=celular.teste)
    celular.gerado, celular.versoes, celular.versao = True, ["Veo 3.1 - Lite", "Omni 1.2 Flash"], 1
    assert flow.teste() == 0
    assert celular.versao == 0 and celular.baixado and len(celular.mandados) == 1
    assert db.ler_config(flow.CHAVE, {})["teste"]["videos"]["Veo 3.1 - Lite"]["estado"] == "enviado"


def test_versoes_sem_a_do_modelo_do_teste_nao_baixam(celular):
    celular.teste["videos"] = {"Veo 3.1 - Lite": {"custo": 10, "estado": "gerando"}}
    flow.guardar(teste=celular.teste)
    celular.gerado, celular.versoes = True, ["Omni 1.2 Flash", "Omni 1.1 Flash"]
    assert flow.teste() == 1
    assert not celular.baixado and celular.mandados == []
    assert ("parou", "baixar: o vídeo mais novo não é do modelo do teste") in celular.guardados

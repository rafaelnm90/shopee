"""flow_shopee_video: o teste da P229 1 monta o pedido no Flow como mapeado, só gera com tudo conferido e o log público não tem o produto."""
import io
import json
from xml.sax.saxutils import quoteattr

import pytest
from PIL import Image

import db
import flow_shopee_video as flow

CUSTOS = {"Omni 1.2 Flash": 24, "Omni 1.1 Flash": 12, "Veo 3.1 - Lite": 10}
SELETOR = flow.PACOTE_DO_SELETOR


def _no(caixa, classe="android.view.View", desc="", texto="", pacote=flow.PACOTE, clicavel=True, rid=""):
    x1, y1, x2, y2 = caixa
    return (f'<node index="0" text={quoteattr(texto)} resource-id={quoteattr(rid)} class="{classe}" '
            f'package="{pacote}" content-desc={quoteattr(desc)} clickable="{str(clicavel).lower()}" '
            f'visible-to-user="true" bounds="[{x1},{y1}][{x2},{y2}]" />')


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
        return Resposta(self.na_galeria if "content" in partes else "")

    def nos(self):
        """(caixa, xml do nó, o que o toque faz) da tela de agora."""
        nos = []
        if self.tela == "inicio":
            nos += [((775, 908, 1038, 1034), _no((775, 908, 1038, 1034), "android.widget.Button", "Novo"), "projeto"),
                    ((42, 1100, 1038, 1300), _no((42, 1100, 1038, 1300), desc="nov. 15, 08:23 AM"), "projeto")]
            if self.termos:
                nos.append(((0, 1400, 1080, 1500), _no((0, 1400, 1080, 1500), texto="Aceitar os Termos de Serviço"), ""))
        elif self.tela == "projeto":
            nos += [((0, 152, 1080, 278), _no((0, 152, 1080, 278), desc="nov. 15, 08:23 AM", clicavel=False), ""),
                    ((403, 2171, 677, 2339), _no((403, 2171, 677, 2339), "android.widget.Button", "Criar"), "pedido")]
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
                        ((540, 1550, 1051, 1650), _no((540, 1550, 1051, 1650), desc="9:16\nGuia 2 de 2"), ""),
                        ((540, 1660, 1051, 1760), _no((540, 1660, 1051, 1760), desc="720p\nGuia 2 de 2"), ""),
                        ((29, 1770, 284, 1870), _no((29, 1770, 284, 1870), desc="x1\nGuia 1 de 4"), ""),
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
        return '<?xml version="1.0" ?><hierarchy rotation="0">' + "".join(no for _, no, _ in self.nos()) + "</hierarchy>"

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
            self.gerado = True


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
    monkeypatch.setattr(flow, "ESPERA_DA_GERACAO", 0)
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
    assert (db.ler_config(flow.CHAVE, {}) or {}).get("projeto") == "nov. 15, 08:23 AM"
    saida = capsys.readouterr().out
    assert "Veo 3.1 - Lite, 10 créditos" in saida and "Copo" not in saida and "tumbler" not in saida


def test_gera_com_tudo_conferido_e_anota_o_modelo_do_teste(celular, capsys):
    flow.guardar(teste=celular.teste)
    assert flow.no_celular(celular.teste, "Omni 1.1 Flash", 12, sem_gerar=False) == 0
    assert celular.gerado
    videos = db.ler_config(flow.CHAVE, {})["teste"]["videos"]
    assert videos["Omni 1.1 Flash"]["estado"] == "gerando" and videos["Omni 1.1 Flash"]["custo"] == 12
    assert any("depois do Gerar" in motivo for _, motivo in celular.guardados)
    assert "Gerar tocado (Omni 1.1 Flash, 12 créditos)" in capsys.readouterr().out
    assert flow.proximo_modelo(db.ler_config(flow.CHAVE, {})["teste"]) == ("Veo 3.1 - Lite", 10)


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


def test_leitura_das_telas():
    folha = ('<hierarchy>' + _no((535, 1460, 823, 1520), "android.widget.Button", "24 créditos de IA")
             + _no((548, 1200, 867, 1300), "android.widget.Button", "Omni 1.2 Flash\nx1")
             + _no((24, 2110, 1056, 2230), desc="Veo 3.1 - Lite\n10 créditos / video") + '</hierarchy>')
    assert flow.custo_na_tela(folha) == 24 and flow.modelo_no_pedido(folha) == "Omni 1.2 Flash"
    inicio = '<hierarchy>' + _no((42, 1100, 1038, 1300), desc="nov. 15, 08:23 AM") + '</hierarchy>'
    assert flow.projeto_na_lista(inicio) == (540, 1200)
    assert flow.projeto_na_lista(inicio, "nov. 15, 08:23 AM") == (540, 1200)
    assert flow.projeto_na_lista(inicio, "nov. 16, 09:00 AM") is None
    assert flow.custo_na_tela('<hierarchy></hierarchy>') is None

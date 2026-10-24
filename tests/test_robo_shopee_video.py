"""Robô automático da Shopee Vídeo (robo_shopee_video): plano do dia, aprovação espalhada, rodada e o caminho no app."""
import os
import random
from datetime import datetime
from xml.sax.saxutils import escape

import pytest

import robo_shopee_video as robo
from conftest import inserir
from fuso import fuso_horario

VESTIDO = "Vestido Infantil Estampado Gatinho Para Meninas de 4 a 14 Anos"
TITULO = "Vestido Infantil Estampado Gatinho 👗 #vestidoinfantil #modainfantil #menina"
LINK = "https://s.shopee.com.br/vestido"


def momento(texto):
    """"2026-10-22 15:00" em Brasília."""
    return datetime.strptime(texto, "%Y-%m-%d %H:%M").replace(tzinfo=fuso_horario)


# A leitura da Saúde do Vídeo do dia fica de fora dos testes que não são dela.
SAUDE_DO_DIA = robo.saude_do_dia_pendente


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(robo.time, "sleep", lambda s: None)
    monkeypatch.setattr(robo.ps.time, "sleep", lambda s: None)
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    # No servidor a tabela já existe (o bot_mestre cria).
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")


@pytest.fixture
def avisos(monkeypatch):
    mandados = []
    monkeypatch.setattr(robo.avisar_rafael, "mandar_texto", lambda texto: mandados.append(texto) or True)
    monkeypatch.setattr(robo.avisar_rafael, "mandar_foto",
                        lambda caminho, legenda="": mandados.append(("foto", legenda)) or True)
    return mandados


def ativar(**mudancas):
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": False, **mudancas})


# --- Plano do dia ---

def test_plano_do_dia_fica_na_faixa_e_no_horario_e_varia_de_um_dia_para_outro():
    config = {**robo.PADRAO, "robo_limite_min": 2, "robo_limite_max": 4, "robo_inicio": 9, "robo_fim": 21}
    planos = [robo.planejar(config, f"2026-10-{dia:02d}") for dia in range(1, 21)]
    for plano in planos:
        assert 2 <= len(plano) <= 4 and plano == sorted(plano)
        assert all("09:00" <= h < "21:00" for h in plano)
    assert planos[0] == robo.planejar(config, "2026-10-01")          # mesmo dia, mesmo plano
    assert len({tuple(p) for p in planos}) > 10 and len({len(p) for p in planos}) > 1


def test_horarios_que_passam_de_uma_vez_contam_como_um_so():
    config = {**robo.PADRAO, "robo_limite_min": 3, "robo_limite_max": 3, "robo_inicio": 8, "robo_fim": 20}
    assert not robo.consumir_horarios(config, momento("2026-10-22 08:00"))
    assert robo.consumir_horarios(config, momento("2026-10-22 19:59"))
    assert not robo.consumir_horarios(config, momento("2026-10-22 19:59"))
    assert robo.consumir_horarios(config, momento("2026-10-23 19:59"))  # dia novo, plano novo


# --- Aprovação: postagens espalhadas ---

def _rascunho(estado="rascunho", criado="2026-10-22 10:00:00", **campos):
    ident = robo.criar("video:1", None)
    robo.atualizar(ident, estado=estado, criado_em=criado, titulo=TITULO, link=LINK, produtos=[VESTIDO],
                   comentario="Amei! #achadinhos", **campos)
    return ident


def test_aprovados_saem_um_de_cada_vez_com_intervalo_sorteado(monkeypatch):
    ativar(robo_inicio=8, robo_fim=22)
    primeiro, segundo, terceiro = _rascunho(), _rascunho(), _rascunho()
    agora = momento("2026-10-22 10:00")
    quando = [robo.aprovar(ident, agora) for ident in (primeiro, segundo, terceiro)]
    horas = [datetime.strptime(q, "%Y-%m-%d %H:%M:%S") for q in quando]
    assert 5 <= (horas[0] - agora.replace(tzinfo=None)).total_seconds() / 60 <= 40
    for antes, depois in zip(horas, horas[1:]):
        assert 30 <= (depois - antes).total_seconds() / 60 <= 90
    assert all(r["estado"] == "aprovado" for r in robo.listar("aprovado"))


def test_aprovado_fora_do_horario_vai_para_o_comeco_do_proximo(monkeypatch):
    ativar(robo_inicio=8, robo_fim=22)
    noite = robo.proxima_postagem(robo.ler_config(), momento("2026-10-22 21:50"), random.Random(1))
    assert "2026-10-23 08:05:00" <= noite <= "2026-10-23 08:40:00"
    madrugada = robo.proxima_postagem(robo.ler_config(), momento("2026-10-23 03:00"), random.Random(1))
    assert "2026-10-23 08:05:00" <= madrugada <= "2026-10-23 08:40:00"


# --- O que fazer em cada rodada ---

def test_ordem_da_rodada_treino_apagar_postar_e_rascunho():
    config = {**robo.PADRAO, "robo_pausado": False, "robo_limite_min": 1, "robo_limite_max": 1,
              "robo_inicio": 0, "robo_fim": 24}
    segunda = momento("2026-10-26 23:59")
    assert robo.o_que_fazer(config, segunda) == ("treino", None)
    robo.gravar_estado(treino_semana=robo.semana(segunda))
    recusado = _rascunho("recusado")
    aprovado = _rascunho("aprovado", postar_em="2026-10-26 23:00:00")
    assert robo.o_que_fazer(config, segunda) == ("apagar", recusado)
    robo.atualizar(recusado, estado="apagado")
    assert robo.o_que_fazer(config, segunda) == ("postar", aprovado)
    robo.atualizar(aprovado, estado="postado")
    assert robo.o_que_fazer(config, segunda) == ("rascunho", None)
    assert robo.o_que_fazer(config, segunda) is None                     # o horário do dia já foi usado
    terca = momento("2026-10-27 23:59")
    assert robo.o_que_fazer(config, terca) == ("rascunho", None)          # treino só na segunda


def test_aprovado_espera_a_hora_dele():
    config = {**robo.PADRAO, "robo_limite_min": 1, "robo_limite_max": 1, "robo_inicio": 23, "robo_fim": 24}
    _rascunho("aprovado", postar_em="2026-10-22 16:00:00")
    assert robo.o_que_fazer(config, momento("2026-10-22 15:59")) is None
    assert robo.o_que_fazer(config, momento("2026-10-22 16:00"))[0] == "postar"


# --- A rodada não toca no celular quando não deve ---

class Intocavel:
    def __getattr__(self, nome):
        pytest.fail(f"o robô não devia tocar no celular ({nome})")


def test_pausado_nao_toca_e_pula_os_horarios(monkeypatch, avisos):
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_limite_min": 1, "robo_limite_max": 1})
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: pytest.fail("pausado nem olha o celular"))
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 21:59")) == "pausado"
    assert robo.estado_do_dia(robo.ler_config(), momento("2026-10-22 21:59"))["feitos"] == 1


def test_fora_do_horario_nao_toca(monkeypatch, avisos):
    ativar(robo_inicio=8, robo_fim=22)
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 22:00")) == "fora do Horário do Robô"


def test_celular_desconectado_tenta_sozinho_e_sem_ele_pausa_e_avisa(monkeypatch, avisos):
    ativar(robo_inicio=0, robo_fim=24)
    tentativas = []
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "reconectar_sozinho",
                        lambda: tentativas.append(1) or (False, "a Depuração por Wi-Fi está desligada no celular"))
    assert "desconectado" in robo.rodada(agora=momento("2026-10-22 10:00"))
    config = robo.ler_config()
    # A Postagem pausa sozinha, e o assistente volta a mandar no privado.
    assert tentativas == [1] and config["robo_pausado"] is True
    assert config["robo_pausa_motivo"] == "celular desconectado"
    assert len(avisos) == 1 and "Retomar Postagem ▶️" in avisos[0] and "assistente" in avisos[0]
    assert robo.rodada(agora=momento("2026-10-22 10:15")) == "pausado"
    assert len(avisos) == 1 and tentativas == [1]


def test_celular_que_reconecta_sozinho_segue_a_rodada(monkeypatch, avisos):
    ativar(robo_inicio=0, robo_fim=24)
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-22 10:00")))
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "reconectar_sozinho", lambda: (True, "moto g(100)"))
    assert robo.rodada(agora=momento("2026-10-22 00:01")) == "nada a fazer agora"
    assert robo.ler_config()["robo_pausado"] is False and avisos == []


def test_com_a_tela_do_celular_aberta_nem_reconecta(monkeypatch, avisos):
    ativar(robo_inicio=0, robo_fim=24)
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: True)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: pytest.fail("não devia olhar o celular"))
    assert "tela do celular está aberta" in robo.rodada(agora=momento("2026-10-22 10:00"))
    assert robo.ler_config()["robo_pausado"] is False


def test_com_o_explorar_no_celular_a_rodada_nao_toca(monkeypatch, avisos):
    ativar(robo_inicio=0, robo_fim=24)
    with robo.celular_robo.trava() as livre:
        assert livre
        with robo.celular_robo.trava() as outra:
            assert not outra
        assert robo.rodada(d=Intocavel(), agora=momento("2026-10-22 10:00")) == "o explorar está tocando no celular"


# --- O caminho no app, com um app de mentira ---

def _no(texto="", ident="", caixa=(0, 0, 10, 10), clicavel=True, filhos=""):
    x1, y1, x2, y2 = caixa
    atributos = f'text="{escape(texto, {chr(34): "&quot;"})}" class="android.view.View" clickable="{"true" if clicavel else "false"}"'
    if ident:
        atributos += f' resource-id="com.shopee.br:id/{ident}"'
    return f'<node {atributos} bounds="[{x1},{y1}][{x2},{y2}]">{filhos}</node>'


def _xml(*nos):
    return f'<hierarchy><node class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">{"".join(nos)}</node></hierarchy>'


ABA_EU = _no("Eu", caixa=(860, 2250, 1080, 2400))
ABA_NOTIFICACOES = _no("Notificações", caixa=(650, 2250, 860, 2400))
FILTRO_DOS_VIDEOS = _no("Lives, Vídeos e Afiliados", caixa=(440, 900, 640, 990))
PRODUTO_NA_LISTA = _no(caixa=(0, 1060, 1080, 1330), filhos=(
    _no(VESTIDO, caixa=(300, 1070, 1040, 1130), clicavel=False)
    + _no(caixa=(840, 1225, 1010, 1290), filhos=_no("Adicionar", caixa=(850, 1235, 1000, 1280), clicavel=False))))


def _tela_final(legenda="", produto=False):
    return [_no(legenda, "et_caption", (40, 300, 1040, 400)), _no("OK", "tv_right", (960, 150, 1060, 210)),
            _no("Adicionar produto", "ll_add_product_symbol", (600, 700, 860, 780)),
            _no("Rascunhos", "tv_drafts_box", (20, 2260, 220, 2360)), _no("Postar", "btn_post", (300, 2260, 960, 2360))
            ] + ([_no(VESTIDO, "tv_product_title", (100, 820, 900, 880), clicavel=False)] if produto else [])


TELAS = {
    "inicio": [ABA_EU, ABA_NOTIFICACOES, _no("Início", caixa=(0, 2250, 200, 2400))],
    "pagina_curta": [_no(caixa=(0, 1100, 1080, 1300), filhos=_no(VESTIDO, caixa=(40, 1190, 1010, 1245), clicavel=False)),
                     _no("Compre Agora", caixa=(500, 1365, 720, 1410))],
    "pagina_completa": [_no(ident="buttonItemLike", caixa=(1000, 1205, 1056, 1261))],
    "pagina_curtida": [_no(ident="buttonItemLiked", caixa=(1000, 1205, 1056, 1261))],
    "eu": [ABA_EU, _no("Criadores & Afiliados", caixa=(360, 700, 700, 780))],
    "criadores": [_no("Conta", caixa=(800, 200, 1000, 260))],
    "conta": [_no("Perfil em Shopee Vídeo", caixa=(100, 600, 700, 680))],
    "perfil": [_no("Postar vídeo", caixa=(700, 2200, 1040, 2300)), _no("Rascunhos: 1", caixa=(20, 900, 350, 1300))],
    "camera": [_no("Biblioteca", caixa=(800, 2100, 1000, 2200))],
    # Dois vídeos na galeria: o mais novo (1º) e um antigo; a caixa marcada tem o número.
    "galeria": [_no(ident="ll_check", caixa=(300, 300, 360, 360)), _no(ident="ll_check", caixa=(600, 300, 660, 360))],
    "galeria_marcada": [_no(ident="ll_check", caixa=(300, 300, 360, 360),
                            filhos=_no("1", "check", (320, 310, 340, 330), clicavel=False)),
                        _no(ident="ll_check", caixa=(600, 300, 660, 360)),
                        _no("Próximo (1)", "tv_pick_top_next", (860, 2080, 980, 2130))],
    "edicao": [_no("Próximo", "tv_compress", (860, 150, 1040, 210))],
    "final": "final",
    "final_editando": [_no("", "et_caption", (40, 300, 1040, 400))],
    "curtidas": [_no("Minhas Curtidas", caixa=(300, 410, 510, 460)), _no("Mais Recente", caixa=(300, 520, 510, 570)),
                 PRODUTO_NA_LISTA],
    "janela": [_no("Editar nome do produto", caixa=(300, 1310, 780, 1370), clicavel=False),
               _no(VESTIDO, caixa=(360, 1450, 1040, 1510), clicavel=False), _no("Feito", caixa=(480, 2290, 600, 2340))],
    "live": [ABA_EU, _no("Live e Vídeo", caixa=(400, 2250, 600, 2400))],
    # As Notificações, como no Motorola: os filtros no alto e a lista embaixo.
    "notificacoes": [_no("Notificações", caixa=(400, 160, 680, 220), clicavel=False), FILTRO_DOS_VIDEOS,
                     ABA_NOTIFICACOES, ABA_EU],
    "notificacoes_videos": [_no("Notificações", caixa=(400, 160, 680, 220), clicavel=False), FILTRO_DOS_VIDEOS,
                            _no("Seu vídeo teve mais de 100 visualizações", caixa=(40, 1990, 1040, 2050),
                                clicavel=False), ABA_NOTIFICACOES, ABA_EU],
}
CAMINHO = {
    ("inicio", "Eu"): "eu", ("eu", "Criadores & Afiliados"): "criadores", ("criadores", "Conta"): "conta",
    ("conta", "Perfil em Shopee Vídeo"): "perfil", ("perfil", "Postar vídeo"): "camera",
    ("camera", "Biblioteca"): "galeria", ("galeria", "@ll_check"): "galeria_marcada",
    ("galeria_marcada", "@tv_pick_top_next"): "edicao", ("edicao", "@tv_compress"): "final",
    ("pagina_curta", VESTIDO): "pagina_completa", ("pagina_completa", "@buttonItemLike"): "pagina_curtida",
    ("final", "@ll_add_product_symbol"): "curtidas", ("curtidas", "Adicionar"): "janela",
    ("janela", "Feito"): "final", ("final", "@tv_drafts_box"): "live",
    ("inicio", "Notificações"): "notificacoes", ("notificacoes", "Lives, Vídeos e Afiliados"): "notificacoes_videos",
    ("notificacoes", "Eu"): "eu", ("notificacoes_videos", "Eu"): "eu",
}


class AppDeMentira:
    """O app da Shopee de mentira: cada toque leva à tela seguinte do CAMINHO."""

    def __init__(self):
        self.atual, self.legenda, self.com_produto = "inicio", "", False
        self.toques, self.teclas, self.comandos, self.enviados, self.prints = [], [], [], [], []
        self.clipboard, self.em_foco = None, False
        self.galeria = set()

    def _nos(self):
        nos = TELAS[self.atual]
        # Como no Motorola: a leitura da tela traz ".." no lugar de cada emoji como o 👗.
        return _tela_final(robo.ps.como_o_android_le(self.legenda), self.com_produto) if nos == "final" else nos

    def dump_hierarchy(self):
        return _xml(*self._nos())

    def click(self, x, y):
        import postador_shopee_video as ps
        tocados = [el for el in ps.elementos(self.dump_hierarchy()) if ps._dentro((x, y), el["caixa"])]
        tocados.sort(key=lambda el: (el["caixa"][2] - el["caixa"][0]) * (el["caixa"][3] - el["caixa"][1]))
        nomes = [nome for el in tocados for nome in (el["texto"], "@" + el["id"] if el["id"] else "") if nome]
        self.toques.append(next((n for n in nomes if n.startswith("@")), nomes[0]) if nomes else (x, y))
        self.em_foco = "@et_caption" in nomes
        for nome in nomes:
            if (self.atual, nome) in CAMINHO:
                if nome == "Feito":
                    self.com_produto = True
                self.atual = CAMINHO[(self.atual, nome)]
                return

    def __call__(self, **seletor):
        """O d(focused=True) do uiautomator2: aqui, nenhum campo em foco (cai no send_keys)."""
        return type("Campo", (), {"exists": False})()

    def send_keys(self, texto):
        self.legenda += texto

    def set_clipboard(self, texto, label=None):
        self.clipboard = texto

    def press(self, tecla, meta=None):
        if meta:
            if self.atual == "final" and not self.em_foco:
                # Como no Motorola: Ctrl+A na tela final, fora da edição da legenda, abre a
                # edição do texto e tira o Postar e o Rascunhos da tela.
                self.atual = "final_editando"
            elif tecla == robo.ps.TECLA_C and self.atual == "final":
                # Ctrl+C com o cursor no campo da legenda copia o texto como o app guardou.
                self.clipboard = self.legenda
            return
        self.teclas.append(tecla)
        self.atual = "inicio"

    def app_start(self, pacote, wait=False):
        self.comandos.append(["abrir"])

    def shell(self, partes):
        self.comandos.append(partes)
        if "android.intent.action.VIEW" in partes:
            self.atual = "pagina_curta"
        if partes[:2] == ["rm", "-f"]:
            self.galeria.discard(partes[2].rsplit("/", 1)[-1])
        if partes[0] == "ls":
            saida = "\n".join(sorted(self.galeria))
        else:
            saida = " ".join(nome for _, nome in self.enviados) if "content" in partes else ""
        return type("R", (), {"output": saida})()

    def push(self, origem, destino):
        self.enviados.append((origem, destino.rsplit("/", 1)[-1]))
        self.galeria.add(destino.rsplit("/", 1)[-1])

    def screenshot(self, caminho):
        self.prints.append(caminho)
        with open(caminho, "wb") as f:
            f.write(b"png")

    def window_size(self):
        return 1080, 2400

    def swipe(self, *pontos):
        self.toques.append("rolar")


def _fonte(monkeypatch, confere=True, violacao=False):
    os.makedirs("archive", exist_ok=True)
    with open("archive/vestido.mp4", "wb") as f:
        f.write(b"video")
    inserir("CREATE TABLE IF NOT EXISTS fila_autorais (id_unico TEXT, caminho_arquivo TEXT, legenda TEXT, data_captura TEXT)")
    inserir("INSERT INTO fila_autorais VALUES (?, ?, ?, ?)", "a1", "archive/vestido.mp4",
            f"Vestido 👗\n{LINK}", "2026-10-22 09:00:00")

    async def converter(link):
        return "https://shopee.com.br/product/1/2"

    async def produtos_do_link(link):
        return [{"nome": VESTIDO, "preco": 59.9, "comissao": 10.0}], link

    async def analisar(arquivo, prompt):
        return '{"confere": %s, "motivo": "vestido"}' % ("true" if confere else "false")

    async def textos(arquivo, nome):
        return {"violacao": violacao, "motivo": "marca" if violacao else "", "titulo": TITULO,
                "comentario": "Amei! #achadinhos"}

    monkeypatch.setattr(robo, "link_para_converter", converter)
    monkeypatch.setattr(robo.ps, "link_para_converter", converter)
    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)
    monkeypatch.setattr(robo.ps.api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(robo.assistente, "textos_do_video", textos)


def test_rascunho_completo_curte_pelo_nome_e_salva_sem_tocar_em_postar(monkeypatch, avisos):
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    app = AppDeMentira()
    resultado = robo.rodada(d=app, agora=momento("2026-10-22 23:59"))
    assert resultado == "rascunho salvo"
    assert "@buttonItemLike" in app.toques and "Postar" not in app.toques and "@btn_post" not in app.toques
    assert app.toques[-1] == "@tv_drafts_box" and app.legenda == TITULO
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["titulo"] == TITULO and rascunho["produtos"] == [VESTIDO] and rascunho["link"] == LINK
    assert os.path.exists(rascunho["arquivo"]) and os.path.exists(rascunho["print"])
    assert app.enviados[0][1] == robo.nome_na_galeria(rascunho["id"])
    # Primeiro o aviso de qual vídeo e produto; no fim, o rascunho esperando aprovação.
    assert "começando um rascunho" in avisos[0] and VESTIDO in avisos[0]
    assert "Rascunhos do Robô 📝" in avisos[-1]
    # O assistente não pega o mesmo vídeo.
    assert robo.assistente.proximo_video("autorais") is None


def test_ia_que_nao_confirma_pula_o_video_sem_tocar_no_celular(monkeypatch, avisos):
    _fonte(monkeypatch, confere=False)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    resultado = robo.rodada(d=Intocavel(), agora=momento("2026-10-22 23:59"))
    assert "parado" in resultado and robo.esperando_aprovacao() == []
    assert robo.listar("pulado")[0]["id_video"] == "a1"
    # O robô não volta a esse vídeo; o assistente pode mandar.
    assert robo.proximo_video(robo.ler_config()) is None
    assert robo.assistente.proximo_video("autorais")["id"] == "a1"


def test_video_com_problema_proprio_passa_ao_proximo_e_sem_video_o_horario_acaba(monkeypatch, avisos):
    # Escolha do Rafael (23/10): o horário das 01:03 falhou e o dia ficou sem aquele
    # rascunho; o rascunho do plano tenta de novo. O vídeo pulado (problema dele) passa
    # direto ao próximo; sem mais vídeo na fonte, as tentativas do horário acabam.
    _fonte(monkeypatch, confere=False)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    agora = momento("2026-10-22 23:59")
    resultados = [robo.rodada(d=Intocavel(), agora=agora) for _ in range(5)]
    assert "parado" in resultados[0]                         # o horário do plano: vídeo pulado
    assert all(r.startswith("nenhum vídeo") for r in resultados[1:4])   # as 3 tentativas do vídeo 2
    assert resultados[4] == "nada a fazer agora"              # acabaram as tentativas


def test_mesmo_video_3_vezes_depois_outro_ate_3_videos_e_espera_o_proximo_horario(monkeypatch, avisos):
    # Pedido do Rafael (23/10): tenta o mesmo vídeo; sem dar certo, outro vídeo, para o dia
    # ter os rascunhos do plano; depois de 3 vídeos, para até o próximo horário.
    _fonte(monkeypatch)
    for numero in range(2, 5):
        inserir("INSERT INTO fila_autorais VALUES (?, ?, ?, ?)", f"a{numero}", "archive/vestido.mp4",
                f"Vestido 👗\n{LINK}", f"2026-10-22 0{numero}:00:00")
    tentados = []

    def falha(d, ident, video, fonte, agora=None):
        tentados.append(video["id"])
        raise robo.Parada("não achei o botão Rascunhos")

    monkeypatch.setattr(robo, "_preparar", falha)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    agora = momento("2026-10-22 23:59")
    resultados = [robo.rodada(d=Intocavel(), agora=agora) for _ in range(10)]
    assert all("parado" in r for r in resultados[:9]) and resultados[9] == "nada a fazer agora"
    primeiro, segundo, terceiro = tentados[0], tentados[3], tentados[6]
    assert tentados == [primeiro] * 3 + [segundo] * 3 + [terceiro] * 3
    assert len({primeiro, segundo, terceiro}) == 3
    finais = [a for a in avisos if isinstance(a, str) and "o rascunho não saiu" in a]
    assert "tentativa 2 de 3 do vídeo 1 de 3" in finais[0] and "com outro vídeo: vídeo 2 de 3" in finais[2]
    assert "acabaram" in finais[8] and len(finais) == 9
    # O vídeo fica de lado só naquele dia: no dia seguinte ele pode voltar.
    assert robo.estado_do_dia(robo.ler_config(), momento("2026-10-23 08:00")).get("evitar") is None
    assert robo.proximo_video(robo.ler_config())["id"] in {primeiro, segundo, terceiro, "a1", "a2", "a3", "a4"}


def test_rascunho_do_plano_que_nao_saiu_avisa_onde_parou_e_quando_tenta_de_novo(monkeypatch, avisos):
    # Escolha do Rafael (23/10): o "começando um rascunho" sempre tem um fim no privado.
    _fonte(monkeypatch, confere=False)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    agora = momento("2026-10-22 23:59")
    robo.rodada(d=Intocavel(), agora=agora)
    aviso = next(a for a in avisos if isinstance(a, str) and "o rascunho não saiu" in a)
    assert "Parou em: conferência da IA" in aviso and "com outro vídeo: vídeo 2 de 3" in aviso
    assert "Histórico do Robô 📋" in aviso
    for _ in range(3):
        robo.rodada(d=Intocavel(), agora=agora)
    finais = [a for a in avisos if isinstance(a, str) and "o rascunho não saiu" in a]
    assert "tentativa 2 de 3 do vídeo 2 de 3" in finais[1] and "tentativa 3 de 3" in finais[2]
    assert "acabaram" in finais[3]
    # O histórico guarda cada tentativa, e o diagnóstico conta resultado e passo sem nomes.
    lista = robo.tentativas_desde("2026-10-22 00:00:00")
    assert [(t["resultado"], t["passo"]) for t in lista] == [
        ("sem vídeo", "vídeo da fonte")] * 3 + [("pulado", "conferência da IA")]
    assert "Parou em: vídeo da fonte" in finais[3]


def test_preparar_1_agora_que_falha_nao_repete_o_aviso(monkeypatch, avisos):
    _fonte(monkeypatch, confere=False)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True})
    robo.rodada(preparar=True, d=Intocavel(), agora=momento("2026-10-22 23:59"))
    assert not any(isinstance(a, str) and "o rascunho não saiu" in a for a in avisos)
    assert "não preparei o rascunho que você pediu" in avisos[-1]


def test_rascunho_salvo_entra_no_historico_com_o_produto(monkeypatch, avisos):
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    assert robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    ultima = robo.tentativas_desde("2026-10-22 00:00:00")[0]
    assert (ultima["acao"], ultima["resultado"], ultima["produto"]) == ("rascunho", "salvo", VESTIDO)
    assert "✅ 1 salvo" in robo.texto_historico(momento("2026-10-22 23:59"))


def test_passo_do_motivo():
    assert robo.passo_do_motivo(robo.SEM_OFERTA) == "oferta de afiliado"
    assert robo.passo_do_motivo("a IA viu outro produto no vídeo (1ª vez): parado") == "conferência da IA"
    assert robo.passo_do_motivo("a IA viu violação das diretrizes") == "diretrizes da Shopee"
    assert robo.passo_do_motivo("toquei no coração, mas o produto não ficou curtido") == "curtir o produto"
    assert robo.passo_do_motivo("o título não ficou na legenda (pela cópia: ...)") == "escrever o título"
    assert robo.passo_do_motivo("toquei em Rascunhos, mas o app continuou na tela final") == "salvar em Rascunhos"
    assert robo.passo_do_motivo("o rascunho aberto não tem o título do aprovado") == "abrir o rascunho"
    assert robo.passo_do_motivo("não consegui voltar até Eu") == "navegar no app"
    assert robo.passo_do_motivo("algo novo") == "outro" and robo.passo_do_motivo("") == ""


def test_historico_guarda_30_dias_e_mostra_as_12_mais_novas():
    for dia in range(1, 21):
        robo.registrar_tentativa("rascunho", "pulado", robo.SEM_OFERTA, agora=momento(f"2026-10-{dia:02d} 10:00"))
    robo.registrar_tentativa("rascunho", "salvo", produto="Vestido", agora=momento("2026-11-25 10:00"))
    # Só ficam os dos últimos 30 dias.
    assert [t["resultado"] for t in robo.tentativas_desde("2000-01-01 00:00:00")] == ["salvo"]
    for minuto in range(15):
        robo.registrar_tentativa("rascunho", "pulado", robo.SEM_OFERTA, agora=momento(f"2026-11-25 11:{minuto:02d}"))
    texto = robo.texto_historico(momento("2026-11-25 12:00"))
    assert "⏭️ 15 pulado" in texto and "✅ 1 salvo" in texto and "e mais 4 tentativa(s)" in texto
    assert len(texto) < 4096


def test_horario_novo_tira_a_repeticao_do_anterior_e_o_que_deu_certo_nao_repete():
    config = {**robo.PADRAO, "robo_limite_min": 2, "robo_limite_max": 2, "robo_inicio": 0, "robo_fim": 24}
    cedo, tarde = momento("2026-10-22 11:59"), momento("2026-10-22 23:59")
    assert robo.o_que_fazer(config, cedo) == ("rascunho", None)
    robo.marcar_para_repetir(config, cedo)
    assert robo.o_que_fazer(config, tarde) == ("rascunho", None)     # o 2º horário, com tentativas novas
    assert robo.o_que_fazer(config, tarde) is None                    # a repetição do 1º saiu
    assert robo.estado_do_dia(config, tarde)["tentativas"] == robo.TENTATIVAS_A_MAIS


def test_verificacao_e_preparar_1_agora_nao_repetem(monkeypatch, avisos):
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    agora = momento("2026-10-22 23:59")
    monkeypatch.setattr(robo.av, "abrir_tela", lambda **kwargs: None)

    erro = [robo.Verificacao()]

    def falha(*args, **kwargs):
        raise erro[0]

    monkeypatch.setattr(robo, "_preparar", falha)
    assert "verificação" in robo.rodada(d=AppDeMentira(), agora=agora)
    assert robo.rodada(d=Intocavel(), agora=agora) == "nada a fazer agora"
    erro[0] = robo.Parada("a tela mudou")
    assert "parado" in robo.rodada(preparar=True, d=AppDeMentira(), agora=agora)
    assert robo.rodada(d=Intocavel(), agora=agora) == "nada a fazer agora"


def test_video_sem_oferta_de_afiliado_fica_de_lado_e_o_proximo_vira_rascunho(monkeypatch, avisos):
    # Investigação de 23/10: o vídeo em que "o link não diz o produto" é de um produto sem
    # oferta de afiliado (não paga comissão). Escolha do Rafael: pular na hora, sem gastar
    # a tentativa do horário, e seguir com o próximo vídeo na mesma rodada.
    _fonte(monkeypatch)
    with open("archive/sem_oferta.mp4", "wb") as f:
        f.write(b"video")
    inserir("INSERT INTO fila_autorais VALUES (?, ?, ?, ?)", "b2", "archive/sem_oferta.mp4",
            "Copo 🥤\nhttps://s.shopee.com.br/semoferta", "2026-10-22 10:00:00")

    async def produtos_do_link(link):
        if "semoferta" in link:
            return [], link
        return [{"nome": VESTIDO, "preco": 59.9, "comissao": 10.0}], link

    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True, "fonte": "autorais"})
    assert robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert robo.esperando_aprovacao()[0]["id_video"] == "a1"
    pulado = robo.listar("pulado")[0]
    assert pulado["id_video"] == "b2" and pulado["motivo"] == robo.SEM_OFERTA
    assert "Copo" not in " ".join(str(a) for a in avisos)        # o robô nem começou o do copo


def test_so_videos_sem_oferta_param_a_rodada_sem_tocar_no_celular(monkeypatch, avisos):
    _fonte(monkeypatch)

    async def produtos_do_link(link):
        return [], link

    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)
    monkeypatch.setattr(robo, "VIDEOS_SEM_OFERTA_POR_RODADA", 1)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    resultado = robo.rodada(d=Intocavel(), agora=momento("2026-10-22 23:59"))
    assert resultado == "os próximos 1 vídeos da fonte são de produtos sem oferta de afiliado"
    assert robo.estado_do_dia(robo.ler_config(), momento("2026-10-22 23:59"))["repetir"] is True


def test_violacao_pula_o_video(monkeypatch, avisos):
    _fonte(monkeypatch, violacao=True)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    assert "violação" in robo.rodada(d=Intocavel(), agora=momento("2026-10-22 23:59"))
    assert any("violação" in a for a in avisos if isinstance(a, str))


def test_verificacao_no_meio_para_e_manda_a_tela(monkeypatch, avisos):
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    abertas = []
    monkeypatch.setattr(robo.av, "abrir_tela", lambda celular=False, verificacao=False: abertas.append(verificacao))
    TELAS["verificacao"] = [_no("Verificação", "title_text", (200, 100, 500, 160))]
    CAMINHO[("eu", "Criadores & Afiliados")] = "verificacao"
    try:
        resultado = robo.rodada(d=AppDeMentira(), agora=momento("2026-10-22 23:59"))
    finally:
        CAMINHO[("eu", "Criadores & Afiliados")] = "criadores"
    assert "verificação" in resultado and abertas == [True]
    # O vídeo não foi culpa dele: volta para a fila.
    assert robo.listar("pulado") == [] and robo.proximo_video(robo.ler_config())["id"] == "a1"


def test_treino_percorre_o_caminho_sem_salvar_nem_postar(monkeypatch, avisos):
    app = AppDeMentira()
    robo.gravar_estado(treino_resultado="mudou: antigo")
    vistos = []
    original = robo.ir_ao_perfil

    def ir_ao_perfil(d):
        vistos.append(robo.ler_estado()["treino_resultado"])     # o do treino anterior já saiu
        original(d)

    monkeypatch.setattr(robo, "ir_ao_perfil", ir_ao_perfil)
    resultado = robo.rodada(treino=True, d=app, agora=momento("2026-10-22 03:00"))
    assert resultado == "treino: caminho OK"
    assert "@tv_drafts_box" not in app.toques and "@btn_post" not in app.toques and "Postar" not in app.toques
    assert "caminho OK" in avisos[-1]
    assert robo.ler_estado()["treino_resultado"] == "ok" and vistos == [""]


def test_treino_avisa_com_print_quando_uma_tela_mudou(monkeypatch, avisos):
    TELAS["camera_nova"] = [_no("Galeria", caixa=(800, 2100, 1000, 2200))]
    CAMINHO[("perfil", "Postar vídeo")] = "camera_nova"
    try:
        resultado = robo.rodada(treino=True, d=AppDeMentira(), agora=momento("2026-10-22 03:00"))
    finally:
        CAMINHO[("perfil", "Postar vídeo")] = "camera"
    assert resultado.startswith("treino: mudou") and "Biblioteca" in resultado
    assert avisos[-1][0] == "foto" and "algo mudou no app" in avisos[-1][1]
    assert robo.ler_estado()["treino_resultado"].startswith("mudou")


def test_mesma_legenda():
    assert robo.mesma_legenda(TITULO, TITULO)
    assert robo.mesma_legenda(TITULO[:40] + "…", TITULO)
    assert not robo.mesma_legenda("Outro título qualquer que não é este de jeito nenhum", TITULO)
    assert not robo.mesma_legenda("", TITULO)
    # O que o app pode mudar sem mudar o título: quebra de linha antes das hashtags,
    # espaço de largura zero e o seletor de variação do emoji.
    assert robo.mesma_legenda(TITULO.replace(" #", "\n#").replace("👗", "👗\ufe0f"), TITULO)
    assert robo.mesma_legenda(TITULO.replace("#", "\u200b#"), TITULO)
    assert not robo.mesma_legenda(TITULO.replace("Gatinho", "Cachorro"), TITULO)


def test_comparar_legenda_diz_onde_difere_sem_mostrar_o_texto():
    assert robo.ps.comparar_legenda(TITULO, TITULO).startswith("a legenda é o título")
    texto = robo.ps.comparar_legenda("Vestido Infantil Estampado Cachorro", TITULO)
    assert "NÃO é o título" in texto and "caractere 28" in texto and "U+0043" in texto and "Vestido" not in texto


TELAS["lista_rascunhos"] = [_no("Selecionar", caixa=(860, 150, 1040, 200)),
                            _no(caixa=(20, 400, 350, 800)), _no(caixa=(370, 400, 700, 800))]
TELAS["rascunho_aberto"] = [_no("Próximo", "tv_compress", (860, 150, 1040, 210))]


@pytest.fixture
def caminho_do_rascunho(monkeypatch):
    """No app de mentira: Rascunhos → o 1º quadro → Próximo → tela final → Postar."""
    for chave, destino in ((("perfil", "Rascunhos: 1"), "lista_rascunhos"), (("lista_rascunhos", (185, 600)), "rascunho_aberto"),
                           (("rascunho_aberto", "@tv_compress"), "final"), (("final", "@btn_post"), "live")):
        monkeypatch.setitem(CAMINHO, chave, destino)


class AppComQuadros(AppDeMentira):
    """Toque num quadro sem texto vai pelo ponto (os quadros da lista não têm nome)."""

    def click(self, x, y):
        if (self.atual, (x, y)) in CAMINHO:
            self.toques.append((x, y))
            self.atual = CAMINHO[(self.atual, (x, y))]
            return
        super().click(x, y)


def _aprovado(monkeypatch):
    async def produtos_do_link(link):
        return [{"nome": VESTIDO, "preco": 59.9, "comissao": 10.0}], link

    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)
    ativar(robo_inicio=0, robo_fim=24)
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-22 23:59")))
    return _rascunho("aprovado", postar_em="2026-10-22 12:00:00")


def test_aprovado_e_postado_com_a_tela_final_conferida(monkeypatch, avisos, caminho_do_rascunho):
    ident = _aprovado(monkeypatch)
    app = AppComQuadros()
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho aprovado postado"
    assert app.toques.count("@btn_post") == 1 and robo.pegar(ident)["estado"] == "postado"
    assert "postei o vídeo que você aprovou" in avisos[0]
    # O comentário vem numa mensagem só dele, depois do lembrete.
    assert avisos[1:] == [robo.ps.AVISO_COMENTARIO, "Amei! #achadinhos"]


def test_rascunho_aberto_com_outro_titulo_nao_e_postado(monkeypatch, avisos, caminho_do_rascunho):
    ident = _aprovado(monkeypatch)
    app = AppComQuadros()
    app.legenda, app.com_produto = "Outro título de outro rascunho qualquer #outro", True
    assert "parado" in robo.rodada(d=app, agora=momento("2026-10-22 23:59"))
    assert "@btn_post" not in app.toques
    rascunho = robo.pegar(ident)
    assert rascunho["estado"] == "rascunho" and "título" in rascunho["motivo"]
    assert "não consegui postar" in avisos[-1]


# --- Telas mapeadas no Motorola em 22/10/2026: aviso de sair, apagar e o link do post ---

TELAS["aviso"] = [_no("Se você voltar, as edições serão descartadas.", "content", (60, 1100, 1020, 1250), clicavel=False),
                  _no("Cancelar", "buttonDefaultNegative", (100, 1300, 500, 1380)),
                  _no("Descartar", "buttonDefaultPositive", (580, 1300, 980, 1380))]
QUADROS = [_no(caixa=(20, 400, 350, 800)), _no(caixa=(370, 400, 700, 800))]
TELAS["lista_selecao"] = [_no("Cancelar", caixa=(860, 150, 1040, 200))] + QUADROS + [_no("Excluir (0)", caixa=(300, 2280, 780, 2350))]
TELAS["lista_marcada"] = [_no("Cancelar", caixa=(860, 150, 1040, 200))] + QUADROS + [_no("Excluir (1)", caixa=(300, 2280, 780, 2350))]
TELAS["confirmar_exclusao"] = [_no("Excluir vídeos selecionados?", caixa=(200, 1160, 880, 1220), clicavel=False),
                               _no("Cancelar", caixa=(200, 1280, 460, 1340)), _no("Confirmar", caixa=(620, 1280, 880, 1340))]
TELAS["lista_vazia"] = [_no("Rascunhos", caixa=(400, 150, 620, 200), clicavel=False)]


class AppComVoltar(AppComQuadros):
    """O voltar como no Motorola: da tela final abre o aviso; no aviso, fecha o aviso."""
    VOLTAR = {"final": "aviso", "aviso": "final", "rascunho_aberto": "lista_rascunhos",
              "lista_rascunhos": "perfil", "perfil": "conta", "conta": "criadores", "criadores": "eu"}

    def press(self, tecla):
        self.teclas.append(tecla)
        self.atual = self.VOLTAR.get(self.atual, "inicio")


@pytest.fixture
def caminho_de_apagar(monkeypatch, caminho_do_rascunho):
    for chave, destino in ((("aviso", "@buttonDefaultPositive"), "rascunho_aberto"),
                           (("lista_rascunhos", "Selecionar"), "lista_selecao"),
                           (("lista_selecao", (185, 600)), "lista_marcada"),
                           (("lista_marcada", "Excluir (1)"), "confirmar_exclusao"),
                           (("confirmar_exclusao", "Confirmar"), "lista_vazia")):
        monkeypatch.setitem(CAMINHO, chave, destino)


def _recusado(monkeypatch):
    ident = _aprovado(monkeypatch)
    robo.atualizar(ident, estado="recusado", postar_em=None)
    return ident


def test_recusado_e_apagado_com_a_confirmacao_e_o_aviso_de_sair(monkeypatch, avisos, caminho_de_apagar):
    ident = _recusado(monkeypatch)
    app = AppComVoltar()
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho recusado apagado"
    # Abre para conferir, sai pelo aviso (o rascunho continua salvo) e apaga pela lista.
    assert "@buttonDefaultPositive" in app.toques
    assert app.toques[-3:] == [(185, 600), "Excluir (1)", "Confirmar"]
    assert "@btn_post" not in app.toques and robo.pegar(ident)["estado"] == "apagado"


def test_com_outro_numero_no_excluir_nada_e_apagado(monkeypatch, avisos, caminho_de_apagar):
    ident = _recusado(monkeypatch)
    monkeypatch.setitem(TELAS, "lista_marcada", TELAS["lista_selecao"][:-1] + [_no("Excluir (2)", caixa=(300, 2280, 780, 2350))])
    app = AppComVoltar()
    app.legenda, app.com_produto = TITULO, True
    assert "parado" in robo.rodada(d=app, agora=momento("2026-10-22 23:59"))
    assert "Confirmar" not in app.toques and robo.pegar(ident)["estado"] == "rascunho"
    assert "não consegui apagar" in avisos[-1]


def test_sem_rascunho_salvo_o_perfil_nao_tem_o_quadro_e_o_robo_para(monkeypatch, avisos, caminho_de_apagar):
    ident = _recusado(monkeypatch)
    monkeypatch.setitem(TELAS, "perfil", [_no("Postar vídeo", caixa=(700, 2200, 1040, 2300))])
    app = AppComVoltar()
    assert "nenhum rascunho salvo" in robo.rodada(d=app, agora=momento("2026-10-22 23:59"))
    assert robo.pegar(ident)["estado"] == "rascunho"


def _no_do_app(pacote, texto, caixa):
    return _no(texto, caixa=caixa).replace("<node ", f'<node package="{pacote}" ', 1)


class CelularQueSaiuDaShopee:
    """O voltar a mais saiu da Shopee e o Telegram ficou na frente."""

    def __init__(self):
        self.app, self.teclas, self.aberturas = "org.telegram.messenger", [], []

    def dump_hierarchy(self):
        if self.app == robo.ps.PACOTE:
            return _xml(_no_do_app(robo.ps.PACOTE, "Eu", (860, 2250, 1080, 2400)))
        return _xml(_no_do_app(self.app, "Conversas", (0, 100, 500, 200)))

    def press(self, tecla):
        self.teclas.append(tecla)

    def app_start(self, pacote, wait=False):
        self.aberturas.append(pacote)
        self.app = pacote


def test_voltar_fora_da_shopee_traz_a_shopee_e_nunca_aperta_voltar_no_outro_app():
    # O Rafael via o Telegram na frente no Motorola (23/10): o voltar não pode mexer em outro app.
    celular = CelularQueSaiuDaShopee()
    robo.voltar(celular, "Eu")
    assert celular.teclas == [] and celular.aberturas == [robo.ps.PACOTE]


def test_aviso_do_android_por_cima_da_shopee_nao_conta_como_outro_app():
    aviso = _xml(_no_do_app("com.android.permissioncontroller", "Permitir", (100, 1000, 500, 1100)))
    telegram = _xml(_no_do_app("org.telegram.messenger", "Conversas", (0, 100, 500, 200)))
    shopee = _xml(_no_do_app(robo.ps.PACOTE, "Eu", (860, 2250, 1080, 2400)))
    assert robo.fora_da_shopee(telegram)
    assert not robo.fora_da_shopee(aviso) and not robo.fora_da_shopee(shopee)
    # Sem o pacote nos elementos (como nas telas de mentira), não dá para saber.
    assert not robo.fora_da_shopee(_xml(_no("Conversas")))


def test_volta_ao_inicio_pelo_eu_da_barra_e_nao_por_um_seu_no_meio_do_texto(monkeypatch):
    app = AppComVoltar()
    app.atual = "perfil"
    monkeypatch.setitem(TELAS, "perfil", TELAS["perfil"] + [_no("Siga o seu perfil", caixa=(40, 500, 1040, 560), clicavel=False)])
    robo.ir_ao_inicio(app)
    assert app.atual == "eu" and app.teclas == ["back"] * 3


def test_link_do_post_pula_o_quadro_de_rascunhos_e_os_fixados(monkeypatch):
    TELAS_PERFIL = [_no("Postar vídeo", caixa=(700, 2200, 1040, 2300)),
                    _no(caixa=(0, 1210, 358, 1680), filhos=_no("Rascunhos: 1", caixa=(40, 1460, 320, 1510), clicavel=False)),
                    _no(caixa=(361, 1210, 719, 1680), filhos=_no("Fixado", caixa=(380, 1230, 480, 1270), clicavel=False)),
                    _no(caixa=(722, 1210, 1080, 1680))]
    monkeypatch.setitem(TELAS, "perfil", TELAS_PERFIL)
    monkeypatch.setitem(TELAS, "player", [
        '<node text="" content-desc="post video share icon" class="android.view.View" clickable="true" '
        'bounds="[950,1935][1052,2035]"></node>', _no("Adicionar um comentário...", caixa=(200, 2300, 900, 2360))])
    monkeypatch.setitem(TELAS, "folha", [_no("Copiar link", caixa=(280, 2200, 440, 2300))])
    for chave, destino in ((("perfil", (901, 1445)), "player"), (("player", (1001, 1985)), "folha"),
                           (("folha", "Copiar link"), "player")):
        monkeypatch.setitem(CAMINHO, chave, destino)
    app = AppComQuadros()
    app.clipboard = "https://sv.shopee.com.br/share-video/abc"
    monkeypatch.setattr(robo, "ir_ao_perfil", lambda d: setattr(d, "atual", "perfil"))
    assert robo.link_do_post(app) == "https://sv.shopee.com.br/share-video/abc"
    assert app.toques == [(901, 1445), (1001, 1985), "Copiar link"]
    app.clipboard = "texto qualquer"
    assert robo.link_do_post(app) == ""


def test_o_compartilhar_do_perfil_nao_serve_para_o_link_do_post():
    perfil = _xml('<node text="" content-desc="profile share" class="android.view.View" clickable="true" '
                  'bounds="[860,140][940,200]"></node>')
    assert robo.botao_de_compartilhar(perfil) is None


def test_da_edicao_de_um_video_novo_o_robo_descarta_e_volta_ao_inicio(monkeypatch):
    # Na edição de um vídeo novo, o voltar pergunta se salva como rascunho: o robô
    # descarta, para a lista do app só ter os rascunhos que ele terminou.
    monkeypatch.setitem(TELAS, "sair_da_edicao", [
        _no("Deseja sair da página de edição?", "tv_main_title", (100, 1780, 980, 1840), clicavel=False),
        _no("Salvar Rascunho", "tv_save", (100, 2090, 980, 2150)),
        _no("Descartar", "tv_no_save", (100, 2190, 980, 2250)),
        _no("Cancelar", "tv_cancel", (100, 2310, 980, 2370))])
    monkeypatch.setitem(CAMINHO, ("sair_da_edicao", "@tv_no_save"), "galeria")
    app = AppComVoltar()
    monkeypatch.setattr(app, "VOLTAR", {**AppComVoltar.VOLTAR, "aviso": "final", "edicao": "sair_da_edicao",
                                        "sair_da_edicao": "edicao", "galeria": "camera", "camera": "perfil"})
    monkeypatch.setitem(CAMINHO, ("aviso", "@buttonDefaultPositive"), "edicao")
    app.atual = "final"
    robo.ir_ao_inicio(app)
    assert app.atual == "eu"
    assert "@buttonDefaultPositive" in app.toques and "@tv_no_save" in app.toques and "@tv_save" not in app.toques


# --- Preparar 1 Agora e o que o rascunho guarda para o Rafael validar (23/10/2026) ---

def test_preparar_1_agora_salva_um_rascunho_mesmo_pausado_e_fora_do_plano(monkeypatch, avisos):
    _fonte(monkeypatch)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True, "robo_inicio": 8, "robo_fim": 9,
                                               "fonte": "autorais"})
    app = AppDeMentira()
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["fonte"] == "autorais"
    assert robo.json.loads(rascunho["conferencia"]) == ["vestido", "vestido"]     # as 2 vezes da IA
    assert "Postar" not in app.toques and "@btn_post" not in app.toques
    assert robo.ler_config()["robo_pausado"] is True                              # continua pausado


def test_titulo_com_emoji_trocado_pelo_app_para_sem_salvar_o_rascunho(monkeypatch, avisos):
    # A conferência vale pela cópia do campo: se o próprio app guardar ".." no lugar do 👗,
    # o robô para, mesmo que a leitura da tela também mostre "..".
    _fonte(monkeypatch)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True})

    class AppQueTrocaEmoji(AppDeMentira):
        def send_keys(self, texto):
            self.legenda += robo.ps.como_o_android_le(texto)

    app = AppQueTrocaEmoji()
    resultado = robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59"))
    assert "o título não ficou na legenda" in resultado and robo.esperando_aprovacao() == []
    assert "@tv_drafts_box" not in app.toques
    # O diagnóstico (público) mostra por onde leu e os tamanhos, nunca o título.
    conferencia = robo.ler_estado()["ultima_legenda"]
    assert conferencia.startswith("pela cópia: a legenda NÃO é o título") and "U+1F457" in conferencia
    assert "1 emoji(s) de fora do plano básico" in conferencia and "Gatinho" not in conferencia


def test_sem_a_copia_do_campo_o_emoji_lido_como_ponto_para_o_rascunho(monkeypatch, avisos):
    # Sem a cópia (o Android não deixou ler), sobra a leitura com ".." no lugar do 👗: para.
    _fonte(monkeypatch)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True})

    class AppSemCopia(AppDeMentira):
        def press(self, tecla, meta=None):
            if not meta:
                super().press(tecla)

    resultado = robo.rodada(preparar=True, d=AppSemCopia(), agora=momento("2026-10-22 23:59"))
    assert "o título não ficou na legenda" in resultado and robo.esperando_aprovacao() == []
    assert robo.ler_estado()["ultima_legenda"].startswith("sem a cópia, pela acessibilidade: ")


def _arquivos_do_rascunho(ident, app):
    """O vídeo e o print do rascunho no servidor, e o vídeo na galeria do celular."""
    os.makedirs(robo.PASTA_RASCUNHOS, exist_ok=True)
    arquivos = [os.path.join(robo.PASTA_RASCUNHOS, f"{ident}.{ext}") for ext in ("mp4", "png")]
    for arquivo in arquivos:
        with open(arquivo, "wb") as f:
            f.write(b"x")
    robo.atualizar(ident, arquivo=arquivos[0], print=arquivos[1])
    app.galeria.add(robo.nome_na_galeria(ident))
    return arquivos


def test_postado_sai_do_servidor_e_da_galeria_e_o_que_espera_aprovacao_fica(monkeypatch, avisos, caminho_do_rascunho):
    # Pedido do Rafael (23/10): a memória de cada rascunho é só do robô e sai depois de usada.
    ident = _aprovado(monkeypatch)
    esperando = _rascunho("rascunho", criado="2026-10-21 10:00:00")   # mais velho: fica depois na lista do app
    app = AppComQuadros()
    app.legenda, app.com_produto = TITULO, True
    postado, guardado = _arquivos_do_rascunho(ident, app), _arquivos_do_rascunho(esperando, app)
    assert robo.rodada(d=app, agora=momento("2026-10-22 23:59")) == "rascunho aprovado postado"
    assert not any(os.path.exists(arquivo) for arquivo in postado)
    assert all(os.path.exists(arquivo) for arquivo in guardado)
    assert app.galeria == {robo.nome_na_galeria(esperando)}
    # A linha do banco fica: é ela que impede o mesmo vídeo de voltar.
    assert robo.pegar(ident)["estado"] == "postado" and "video:1" in robo.ids_usados()


def test_preparo_que_parou_no_meio_nao_deixa_o_video_no_servidor_nem_na_galeria(monkeypatch, avisos):
    _fonte(monkeypatch)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True})

    class AppQueTrocaEmoji(AppDeMentira):
        def send_keys(self, texto):
            self.legenda += robo.ps.como_o_android_le(texto)

    app = AppQueTrocaEmoji()
    resultado = robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59"))
    assert "o título não ficou na legenda" in resultado
    # O vídeo chegou a ir para a galeria antes de parar; no fim da rodada, saiu dos dois lugares.
    assert app.enviados and app.galeria == set() and os.listdir(robo.PASTA_RASCUNHOS) == []


def test_celular_que_cai_na_faxina_deixa_a_copia_do_servidor_para_a_proxima_rodada(avisos):
    ident = _rascunho("postado")

    class AppQueCaiu(AppDeMentira):
        def shell(self, partes):
            raise ConnectionError("o celular saiu da rede")

    app = AppQueCaiu()
    arquivos = _arquivos_do_rascunho(ident, app)
    robo.faxina_dos_arquivos(app)
    assert all(os.path.exists(arquivo) for arquivo in arquivos)
    robo.faxina_dos_arquivos(AppDeMentira())
    assert not any(os.path.exists(arquivo) for arquivo in arquivos)


def test_preparar_1_agora_sem_video_diz_no_privado_por_que_nao_preparou(monkeypatch, avisos):
    inserir("CREATE TABLE IF NOT EXISTS fila_autorais (id_unico TEXT, caminho_arquivo TEXT, legenda TEXT, data_captura TEXT)")
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True})
    resultado = robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59"))
    assert "nenhum vídeo" in resultado
    assert "não preparei o rascunho que você pediu" in avisos[-1]


def test_tabela_antiga_ganha_as_colunas_novas_sem_perder_os_rascunhos():
    inserir("CREATE TABLE shopee_video_rascunhos (id INTEGER PRIMARY KEY AUTOINCREMENT, id_video TEXT, "
            "criado_em TEXT, estado TEXT, arquivo TEXT, print TEXT, link TEXT, produtos TEXT, titulo TEXT, "
            "comentario TEXT, aprovado_em TEXT, postar_em TEXT, postado_em TEXT, link_post TEXT, motivo TEXT)")
    inserir("INSERT INTO shopee_video_rascunhos (id_video, criado_em, estado, produtos) VALUES (?, ?, ?, ?)",
            "antigo", "2026-10-22 10:00:00", "rascunho", "[]")
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["id_video"] == "antigo" and rascunho["fonte"] is None and rascunho["conferencia"] is None


def test_erro_inesperado_no_preparar_avisa_e_nao_derruba_a_rodada(monkeypatch, avisos):
    _fonte(monkeypatch)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True})

    def quebra(*args, **kwargs):
        raise KeyError("x")

    monkeypatch.setattr(robo.ps, "curtir", quebra)
    resultado = robo.rodada(preparar=True, d=AppDeMentira(), agora=momento("2026-10-22 23:59"))
    assert resultado == "rascunho: erro KeyError"
    assert "não preparei o rascunho que você pediu (rascunho: erro KeyError)" in avisos[-1]
    assert robo.listar("preparando", "rascunho") == []                       # a reserva foi desfeita


def test_main_grava_a_ultima_rodada_mascarada(monkeypatch):
    monkeypatch.setattr(robo, "rodada", lambda **kw: f"rascunho: parado (não achei {VESTIDO} na lista)")
    assert robo.main(["--preparar"]) == 0
    estado = robo.ler_estado()
    assert estado["ultima_rodada"].startswith("rascunho: parado (não achei") and "Vestido" not in estado["ultima_rodada"]
    assert estado["ultima_rodada_em"]


def test_galeria_que_lembra_um_video_antigo_marcado_fica_so_com_o_mais_novo(monkeypatch):
    # No Motorola (23/10) a galeria lembrou a marcação de antes: tocar sem olhar desmarcava
    # o vídeo ou juntaria dois vídeos no mesmo post.
    monkeypatch.setitem(TELAS, "galeria_lembrada", [
        _no(ident="ll_check", caixa=(300, 300, 360, 360)),
        _no(ident="ll_check", caixa=(600, 300, 660, 360), filhos=_no("1", "check", (620, 310, 640, 330), clicavel=False)),
        _no("Próximo (1)", "tv_pick_top_next", (860, 2080, 980, 2130))])
    monkeypatch.setitem(CAMINHO, ("galeria_lembrada", (630, 330)), "galeria")
    monkeypatch.setitem(CAMINHO, ("galeria", (330, 330)), "galeria_marcada")
    app = AppComQuadros()
    app.atual = "galeria_lembrada"
    robo.marcar_so_o_mais_novo(app)
    assert app.toques == [(630, 330), (330, 330)] and app.atual == "galeria_marcada"
    # Já certo: não toca em nada.
    app.toques = []
    robo.marcar_so_o_mais_novo(app)
    assert app.toques == []


# --- Link de vídeo: o Ver Produtos (mapeado no Motorola em 23/10/2026) ---

PRODUTO_A = "Garrafa Térmica Inox 1 Litro Com Alça e Tampa Rosqueável"
PRODUTO_B = "Copo Térmico Inox 500 ml Com Canudo e Tampa"
RECOMENDADO = "Kit Potes Herméticos De Vidro Para Cozinha Com Tampa"
LINK_DE_VIDEO = "https://s.shopee.com.br/videocomprodutos"


def _cartao(nome, y):
    """Um cartão da lista do Ver Produtos: nome, preço e o botão de comprar (que o robô nunca toca)."""
    return _no(caixa=(0, y, 1080, y + 300), filhos=(
        _no(nome, caixa=(300, y + 20, 1040, y + 80), clicavel=False)
        + _no("R$59,90", caixa=(300, y + 200, 500, y + 240), clicavel=False)
        + _no(caixa=(780, y + 200, 1050, y + 280),
              filhos=_no("Comprar com cupom", caixa=(790, y + 210, 1040, y + 270), clicavel=False))))


def _item_curtido(nome, y, adicionado):
    return _no(caixa=(0, y, 1080, y + 270), filhos=(
        _no(nome, caixa=(300, y + 10, 1040, y + 70), clicavel=False)
        + _no(caixa=(840, y + 165, 1010, y + 230),
              filhos=_no("Adicionado" if adicionado else "Adicionar", caixa=(850, y + 175, 1000, y + 220),
                         clicavel=False))))


class AppDoVerProdutos(AppDeMentira):
    """O app com um link de vídeo: o player, o Ver Produtos, as páginas dos produtos e o Adicionar Mais."""

    def __init__(self, removido=False, player="normal"):
        super().__init__()
        self.removido, self.curtidos, self.anexados, self.janela = removido, set(), [], None
        # player: "normal"; "lento" (o Ver Produtos só aparece na segunda olhada); "um_produto"
        # (o cartão de um produto, sem o Ver Produtos); "vazio"; "sem_player" (outra tela).
        self.player, self.olhadas_no_player = player, 0

    def _nos(self):
        if self.atual == "removido":
            return [_no("Detalhes do Vídeo", caixa=(300, 1160, 780, 1220), clicavel=False),
                    _no("Este vídeo foi removido pelo criador", caixa=(200, 1240, 880, 1280), clicavel=False)]
        if self.atual == "player":
            self.olhadas_no_player += 1
            if self.player == "sem_player":
                return [_no("Para você", caixa=(640, 140, 830, 195), clicavel=False)]
            nos = [_no(ident=robo.PLAYER_DO_VIDEO, caixa=(0, 0, 1080, 2260), clicavel=False)]
            if self.player == "um_produto":
                nos.append(_cartao(PRODUTO_A, 1600))
            elif self.player == "normal" or (self.player == "lento" and self.olhadas_no_player > 1):
                nos.append(_no("Ver Produtos (2)", caixa=(400, 1940, 650, 2000)))
            return nos
        if self.atual == "ver_produtos":
            return [_no(caixa=(0, 400, 1080, 2400), filhos=(
                _no("Ver Produtos (2)", caixa=(40, 700, 300, 750), clicavel=False)
                + _cartao(PRODUTO_A, 1030) + _cartao(PRODUTO_B, 1350)
                + _no("Ver Mais (1)", caixa=(400, 1720, 640, 1770))
                + _no("Você Também Pode Gostar", caixa=(300, 1870, 780, 1920), clicavel=False)
                + _cartao(RECOMENDADO, 1940)))]
        if self.atual.startswith("pdp:"):
            nome = self.atual[4:]
            return [_no(ident="buttonItemLiked" if nome in self.curtidos else "buttonItemLike", caixa=(1000, 1510, 1056, 1566)),
                    _no(nome, "labelProductPageProductName", (40, 1850, 1040, 1900), clicavel=False),
                    _no("Compre agora", "buttonProductBuyNow", (600, 2290, 1040, 2370))]
        if self.atual == "curtidas":
            return [_no("Minhas Curtidas", caixa=(300, 410, 510, 460)), _no("Mais Recente", caixa=(300, 520, 510, 570)),
                    _item_curtido(PRODUTO_A, 650, PRODUTO_A in self.anexados),
                    _item_curtido(PRODUTO_B, 930, PRODUTO_B in self.anexados)]
        if self.atual == "janela":
            return [_no("Editar nome do produto", caixa=(300, 1310, 780, 1370), clicavel=False),
                    _no(self.janela, caixa=(360, 1450, 1040, 1510), clicavel=False), _no("Feito", caixa=(480, 2290, 600, 2340))]
        if self.atual == "final":
            nos = _tela_final(robo.ps.como_o_android_le(self.legenda))
            for i, nome in enumerate(self.anexados):
                nos.append(_no(nome, "tv_product_title", (40 + 500 * i, 820, 500 + 500 * i, 880), clicavel=False))
            if self.anexados:
                nos.append(_no("Adicionar Mais", "tv_add_more", (800, 700, 980, 760)))
            return nos
        return super()._nos()

    def shell(self, partes):
        resposta = super().shell(partes)
        if "android.intent.action.VIEW" in partes:
            self.atual = "removido" if self.removido else "player"
        return resposta

    def click(self, x, y):
        tocados = [el for el in robo.ps.elementos(self.dump_hierarchy()) if robo.ps._dentro((x, y), el["caixa"])]
        textos = {el["texto"] for el in tocados} | {"@" + el["id"] for el in tocados if el["id"]}
        assert not any(robo.ps.texto_proibido(t) for t in textos), f"tocou num botão de comprar: {textos}"
        if self.atual == "player" and "Ver Produtos (2)" in textos:
            self.atual = "ver_produtos"
        elif self.atual == "ver_produtos":
            nome = next((t for t in textos if t in (PRODUTO_A, PRODUTO_B, RECOMENDADO)), None)
            self.toques.append(nome or (x, y))
            if nome:
                self.atual = "pdp:" + nome
            return
        elif self.atual.startswith("pdp:") and "@buttonItemLike" in textos:
            self.curtidos.add(self.atual[4:])
        elif self.atual == "final" and "@tv_add_more" in textos:
            self.atual = "curtidas"
        elif self.atual == "final" and "@ll_add_product_symbol" in textos:
            self.atual = "curtidas"
        elif self.atual == "curtidas" and "Adicionar" in textos:
            self.janela = PRODUTO_A if y < 930 else PRODUTO_B       # o item de cima é o A
            self.atual = "janela"
        elif self.atual == "janela" and "Feito" in textos:
            self.anexados.append(self.janela)
            self.atual = "final"
        else:
            return super().click(x, y)
        self.toques.append(next((t for t in textos if t.startswith("@")), next(iter(textos), (x, y))))

    def press(self, tecla, meta=None):
        if meta or tecla != "back" or not (self.atual.startswith("pdp:") or self.atual in ("ver_produtos", "player")):
            return super().press(tecla, meta)
        self.teclas.append(tecla)
        self.atual = {"ver_produtos": "player", "player": "inicio"}.get(self.atual, "ver_produtos")


def _fonte_de_video(monkeypatch, confirma=(PRODUTO_A, PRODUTO_B)):
    _fonte(monkeypatch)
    inserir("UPDATE fila_autorais SET legenda = ?", f"Garrafa 🧴\n{LINK_DE_VIDEO}")

    async def converter(link):
        return "https://sv.shopee.com.br/share-video/AAAA" if link == LINK_DE_VIDEO else "https://shopee.com.br/product/1/2"

    async def produtos_do_link(link):
        return [], link       # link de vídeo: a API não diz os produtos

    async def analisar(arquivo, prompt):
        confere = any(nome in prompt for nome in confirma)
        return '{"confere": %s, "motivo": "a IA viu no vídeo"}' % ("true" if confere else "false")

    monkeypatch.setattr(robo, "link_para_converter", converter)
    monkeypatch.setattr(robo.ps, "link_para_converter", converter)
    monkeypatch.setattr(robo.assistente, "produtos_do_link", produtos_do_link)
    monkeypatch.setattr(robo.ps.api_gemini, "analisar_video_gemini", analisar)
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True, "fonte": "autorais"})


def test_link_de_video_curte_e_anexa_todos_os_produtos_que_a_ia_confirma(monkeypatch, avisos):
    # Escolha do Rafael (23/10): no Ver Produtos, todos os produtos do criador que a IA
    # confirmar; nunca os de "Você Também Pode Gostar" nem um botão de comprar.
    _fonte_de_video(monkeypatch)
    app = AppDoVerProdutos()
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.curtidos == {PRODUTO_A, PRODUTO_B} and app.anexados == [PRODUTO_A, PRODUTO_B]
    assert RECOMENDADO not in app.toques
    rascunho = robo.esperando_aprovacao()[0]
    assert rascunho["produtos"] == [PRODUTO_A, PRODUTO_B]
    assert len(robo.json.loads(rascunho["conferencia"])) == 4          # 2 conferências por produto
    assert "os do Ver Produtos" in avisos[0]


def test_link_de_video_deixa_de_fora_o_produto_que_a_ia_recusa(monkeypatch, avisos):
    _fonte_de_video(monkeypatch, confirma=(PRODUTO_B,))
    app = AppDoVerProdutos()
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.curtidos == {PRODUTO_B} and app.anexados == [PRODUTO_B]
    assert robo.esperando_aprovacao()[0]["produtos"] == [PRODUTO_B]
    assert not any("A IA" in str(a) and PRODUTO_A in str(a) for a in avisos)   # recusado não vira aviso


def test_link_de_video_sem_produto_confirmado_fica_de_lado(monkeypatch, avisos):
    _fonte_de_video(monkeypatch, confirma=())
    resultado = robo.rodada(preparar=True, d=AppDoVerProdutos(), agora=momento("2026-10-22 23:59"))
    assert "a IA não confirmou nenhum produto do Ver Produtos" in resultado
    assert robo.listar("pulado")[0]["id_video"] == "a1"


def test_link_de_video_espera_o_ver_produtos_que_demora(monkeypatch, avisos):
    _fonte_de_video(monkeypatch)
    app = AppDoVerProdutos(player="lento")
    assert robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59")) == "rascunho salvo"
    assert app.anexados == [PRODUTO_A, PRODUTO_B]


@pytest.mark.parametrize("player, motivo", [
    ("um_produto", "o vídeo mostrou o cartão de um produto, sem o Ver Produtos"),
    ("vazio", "o link de vídeo não mostrou o Ver Produtos"),
    ("sem_player", "o link de vídeo não abriu o vídeo no app (sem o Ver Produtos)"),
])
def test_link_de_video_sem_ver_produtos_diz_o_que_a_tela_mostrou(monkeypatch, avisos, player, motivo):
    # O motivo é texto fixo, para o investigar_robo.yml mostrar qual dos casos foi.
    _fonte_de_video(monkeypatch)
    app = AppDoVerProdutos(player=player)
    resultado = robo.rodada(preparar=True, d=app, agora=momento("2026-10-22 23:59"))
    assert motivo in resultado and app.olhadas_no_player == 2
    pulado = robo.listar("pulado")[0]
    assert pulado["motivo"] == motivo and robo.passo_do_motivo(motivo) == "Ver Produtos"
    import investigar_robo
    assert motivo in investigar_robo.textos_fixos()


def test_link_de_video_removido_fica_de_lado(monkeypatch, avisos):
    _fonte_de_video(monkeypatch)
    resultado = robo.rodada(preparar=True, d=AppDoVerProdutos(removido=True), agora=momento("2026-10-22 23:59"))
    assert "o vídeo do link foi removido" in resultado and robo.listar("pulado")[0]["id_video"] == "a1"


def test_rascunho_de_varios_produtos_so_e_postado_com_todos_na_tela_final(monkeypatch, avisos):
    app = AppDoVerProdutos()
    app.atual, app.anexados = "final", [PRODUTO_A]
    video = {"id": "a1", "arquivo": "x.mp4", "link": LINK_DE_VIDEO, "produtos": [PRODUTO_A, PRODUTO_B]}
    ok, motivo = robo.ps.conferir_tela_final(app, video)
    assert not ok and "1 produto(s) anexado(s)" in motivo
    app.anexados = [PRODUTO_B, PRODUTO_A]
    assert robo.ps.conferir_tela_final(app, video)[0]
    app.anexados = [PRODUTO_A, PRODUTO_B, RECOMENDADO]
    assert not robo.ps.conferir_tela_final(app, video)[0]


# --- Conta de Shopee Vídeo suspensa pela Shopee ---

BANIDA = ("Sua conta foi banida temporariamente até 26-10-2026 19:04:26 devido à violação das Diretrizes da "
          "Comunidade da Shopee Vídeo. Você não poderá publicar conteúdos em Shopee Vídeo durante o período "
          "de suspensão.")


@pytest.fixture
def conta_suspensa(monkeypatch):
    """O Postar vídeo não abre nada, e as Notificações mostram o aviso da suspensão (Motorola, 23/10/2026)."""
    monkeypatch.setitem(CAMINHO, ("perfil", "Postar vídeo"), "perfil")
    monkeypatch.setitem(TELAS, "notificacoes_videos",
                        TELAS["notificacoes_videos"] + [_no(BANIDA, caixa=(40, 1100, 1040, 1300), clicavel=False)])


def test_suspensao_na_tela_le_o_fim_e_ignora_a_que_ja_acabou():
    agora = momento("2026-10-23 19:30")
    fim = robo.suspensao_na_tela(_xml(_no(BANIDA, clicavel=False)), agora)
    assert fim == datetime(2026, 10, 26, 19, 4, 26, tzinfo=fuso_horario)
    assert robo.suspensao_na_tela(_xml(_no(BANIDA, clicavel=False)), momento("2026-10-26 19:05")) is None
    # Com duas, vale a que acaba por último; sem o "publicar", não é a suspensão.
    outra = BANIDA.replace("26-10-2026 19:04:26", "29-10-2026 08:00:00")
    assert robo.suspensao_na_tela(_xml(_no(BANIDA), _no(outra)), agora).day == 29
    assert robo.suspensao_na_tela(_xml(_no("Sua conta foi verificada até 26-10-2026 19:04:26 e pode publicar")),
                                  agora) is None
    # O mesmo aviso, como a Saúde do Vídeo mostra.
    saude = "Seu acesso para postar vídeos foi banido até 26/10/2026 19:04:26 devido a múltiplas violações. Ver Detalhes"
    assert robo.suspensao_na_tela(_xml(_no(saude, clicavel=False)), agora) == fim


def test_conta_suspensa_para_o_rascunho_avisa_uma_vez_e_nao_toca_ate_o_fim(monkeypatch, avisos, conta_suspensa):
    # Escolha do Rafael (23/10, P4): pausar robô e assistente, avisar com a data e voltar sozinho.
    _fonte(monkeypatch)
    ativar(robo_limite_min=1, robo_limite_max=1, robo_inicio=0, robo_fim=24)
    app = AppDeMentira()
    resultado = robo.rodada(d=app, agora=momento("2026-10-23 23:59"))
    assert resultado == "conta de Shopee Vídeo suspensa pela Shopee até 26/10 às 19:04"
    config = robo.ler_config()
    assert config["robo_suspenso_ate"] == "2026-10-26 19:04:26" and config["robo_pausado"] is False
    assert "Biblioteca" not in app.toques and "@tv_drafts_box" not in app.toques
    # Primeiro o "começando um rascunho"; depois só o aviso da suspensão, sem o "não saiu".
    assert len(avisos) == 2 and "26/10 às 19:04" in avisos[1] and "voltam sozinhos" in avisos[1]
    assert not any("o rascunho não saiu" in a for a in avisos)
    # O horário não volta, e o vídeo volta para a fila (o problema não era dele).
    assert robo.estado_do_dia(config, momento("2026-10-23 23:59")).get("repetir") is False
    assert robo.proximo_video(config)["id"] == "a1"
    assert robo.tentativas_desde("2026-10-23 00:00:00")[0]["resultado"] == "suspensa"
    # Até o fim (com a folga), nem a rodada nem o Preparar 1 Agora tocam no celular.
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-24 10:00")).startswith("conta suspensa até 26/10")
    assert len(avisos) == 2
    assert robo.rodada(preparar=True, d=Intocavel(), agora=momento("2026-10-26 19:15")).startswith("conta suspensa")
    assert "não preparei o rascunho" in avisos[-1] and "26/10 às 19:04" in avisos[-1]


def test_aprovado_espera_a_suspensao_sem_tocar_em_postar(monkeypatch, avisos, caminho_do_rascunho, conta_suspensa):
    ident = _aprovado(monkeypatch)
    app = AppComQuadros()
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(d=app, agora=momento("2026-10-23 19:30")).startswith("conta de Shopee Vídeo suspensa")
    assert "@btn_post" not in app.toques and "Rascunhos: 1" not in app.toques
    assert robo.pegar(ident)["estado"] == "aprovado" and len(avisos) == 1 and "26/10 às 19:04" in avisos[0]


def test_sem_suspensao_o_aprovado_e_postado_depois_de_olhar_as_notificacoes(monkeypatch, avisos, caminho_do_rascunho):
    ident = _aprovado(monkeypatch)
    app = AppComQuadros()
    app.legenda, app.com_produto = TITULO, True
    assert robo.rodada(d=app, agora=momento("2026-10-23 19:30")) == "rascunho aprovado postado"
    # Olhou as Notificações (rolou a lista procurando o aviso) e só então postou.
    assert app.toques.index("Lives, Vídeos e Afiliados") < app.toques.index("@btn_post")
    assert app.toques.count("rolar") == robo.ROLADAS_NAS_NOTIFICACOES and robo.pegar(ident)["estado"] == "postado"
    assert "robo_suspenso_ate" not in robo.ler_config()


def test_fim_da_suspensao_volta_sozinho_e_espalha_os_aprovados(monkeypatch):
    ativar(robo_inicio=8, robo_fim=22, robo_suspenso_ate="2026-10-26 19:04:26")
    um = _rascunho("aprovado", postar_em="2026-10-24 10:00:00")
    dois = _rascunho("aprovado", postar_em="2026-10-24 11:00:00")
    assert robo.fim_da_suspensao(momento("2026-10-26 19:10")) is None          # ainda na folga
    aviso = robo.fim_da_suspensao(momento("2026-10-26 19:20"))
    assert "acabou" in aviso and "Voltei a preparar e postar" in aviso and "2 aprovado(s)" in aviso
    assert "robo_suspenso_ate" not in robo.ler_config() and robo.fim_da_suspensao(momento("2026-10-26 19:35")) is None
    horas = sorted(robo.pegar(i)["postar_em"] for i in (um, dois))
    assert horas[0] > "2026-10-26 19:20:00"
    distancia = (datetime.strptime(horas[1], "%Y-%m-%d %H:%M:%S") - datetime.strptime(horas[0], "%Y-%m-%d %H:%M:%S"))
    assert distancia.total_seconds() >= robo.INTERVALO_DAS_POSTAGENS[0] * 60


def test_quem_pausou_na_suspensao_continua_pausado_no_fim():
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO, "robo_pausado": True, "pausado": False,
                                              "robo_suspenso_ate": "2026-10-26 19:04:26"})
    aviso = robo.fim_da_suspensao(momento("2026-10-26 19:20"))
    assert "continua pausado" in aviso and "assistente volta" in aviso
    assert robo.ler_config()["robo_pausado"] is True


def test_treino_na_conta_suspensa_avisa_a_suspensao_e_nao_que_o_app_mudou(monkeypatch, avisos, conta_suspensa):
    resultado = robo.rodada(treino=True, d=AppDeMentira(), agora=momento("2026-10-23 19:30"))
    assert resultado.startswith("conta de Shopee Vídeo suspensa")
    assert robo.ler_estado()["treino_resultado"].startswith("conta de Shopee Vídeo suspensa")
    assert len(avisos) == 1 and "algo mudou" not in str(avisos) and "26/10 às 19:04" in avisos[0]


# --- Saúde do Vídeo e apelação (mapeada no Motorola em 24/10/2026) ---

SAUDE_BANIDO = ("Seu acesso para postar vídeos foi banido até 26/10/2026 19:04:26 devido a múltiplas violações. "
                "Ver Detalhes")
EXPLICACAO = ("Conteúdos publicados devem promover de forma clara e direta o mesmo produto do anúncio vinculado.")


def _punicao_na_lista(tipo, data, status, y):
    return [_no(tipo, caixa=(300, y, 1000, y + 40), clicavel=False),
            _no(f"Data de Punição: {data}", caixa=(300, y + 50, 1000, y + 90), clicavel=False),
            _no(f"Status da Apelação: {status}", caixa=(300, y + 100, 1000, y + 140), clicavel=False)]


def _removido(titulo, postado, apelar=True):
    return ([_no("Removido", caixa=(400, 460, 680, 510), clicavel=False),
             _no("O vídeo violou nossas Diretrizes da Comunidade.", caixa=(100, 540, 980, 580), clicavel=False),
             _no(titulo, caixa=(300, 760, 1000, 810), clicavel=False),
             _no(f"Postado em: {postado}.", caixa=(300, 890, 1000, 930), clicavel=False),
             _no(EXPLICACAO, caixa=(60, 1000, 1020, 1250), clicavel=False)]
            + ([_no(caixa=(40, 1280, 1040, 1340), filhos=_no("Apelar aqui.", caixa=(60, 1300, 430, 1350),
                                                              clicavel=False))] if apelar else []))


TELAS_DA_SAUDE = {
    "centro": [_no("Live e Vídeo", caixa=(100, 180, 520, 240), clicavel=False),
               _no("Saúde do Vídeo", caixa=(60, 1330, 380, 1385), clicavel=False),
               _no("Melhoria Necessária", caixa=(640, 1330, 980, 1385)),
               _no("O acesso para postagem de vídeos está temporariamente bloqueado.", caixa=(40, 1410, 1040, 1470))],
    "saude": ([_no("Saúde do Vídeo", caixa=(400, 180, 700, 220), clicavel=False),
               _no("Banido Temporariamente", caixa=(400, 410, 760, 450), clicavel=False),
               _no(SAUDE_BANIDO, caixa=(60, 500, 1020, 580), clicavel=False),
               _no("Ponto de Penalidade", caixa=(380, 1010, 700, 1050), clicavel=False),
               _no("6", caixa=(510, 1090, 570, 1150), clicavel=False),
               _no("Vídeos de Violação", caixa=(380, 1860, 700, 1900), clicavel=False)]
              + _punicao_na_lista("Produto Irrelevante", "23/10/2026 19:04:25", "Não Recorrido", 1950)
              + _punicao_na_lista("Contrafeito", "06/10/2026 22:44:53", "Bem-sucedido", 2110)
              + _punicao_na_lista("Violação de Propriedade Intelectual", "18/10/2026 20:20:56", "Não Recorrido", 2260)),
    "removido_1": _removido(robo.ps.como_o_android_le(TITULO), "18:46:10 2026-10-23"),
    "removido_3": _removido("Organizador de Gaveta #casa", "20:20:00 2026-10-18"),
}


class AppDaSaude(AppDeMentira):
    """O app de mentira com o Centro do criador, a Saúde do Vídeo e a tela Removido de cada punição."""

    CAMINHO = {("perfil", "Centro do criador"): "centro", ("centro", "Melhoria Necessária"): "saude",
               ("saude", "Produto Irrelevante"): "removido_1",
               ("saude", "Violação de Propriedade Intelectual"): "removido_3",
               ("saude", "Contrafeito"): "removido_2"}

    def _nos(self):
        if self.atual in TELAS_DA_SAUDE:
            return TELAS_DA_SAUDE[self.atual]
        nos = super()._nos()
        return nos + [_no("Centro do criador", caixa=(620, 980, 980, 1040))] if self.atual == "perfil" else nos

    def click(self, x, y):
        import postador_shopee_video as ps
        tocados = [el for el in ps.elementos(self.dump_hierarchy()) if ps._dentro((x, y), el["caixa"]) and el["texto"]]
        for el in sorted(tocados, key=lambda el: (el["caixa"][2] - el["caixa"][0]) * (el["caixa"][3] - el["caixa"][1])):
            if (self.atual, el["texto"]) in self.CAMINHO:
                self.toques.append(el["texto"])
                self.atual = self.CAMINHO[(self.atual, el["texto"])]
                return
        super().click(x, y)

    def press(self, tecla, meta=None):
        if tecla == "back" and self.atual.startswith("removido"):
            self.teclas.append(tecla)
            self.atual = "saude"
            return
        super().press(tecla, meta)


@pytest.fixture
def ia_da_apelacao(monkeypatch):
    pedidos = []

    async def gerar(prompt):
        pedidos.append(prompt)
        return ("O vídeo mostra o mesmo produto do anúncio: vestido infantil estampado de gatinho, igual em cor e "
                "modelo. Peço a revisão da penalidade.")
    import api_gemini
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", gerar)
    return pedidos


def _postado_pelo_robo():
    ident = _rascunho("postado", postado_em="2026-10-23 18:45:30", fonte="viral",
                      conferencia='["o vestido do vídeo é o do link"]')
    return ident


def test_gerar_apelacao_le_a_saude_acha_o_video_e_escreve_so_o_que_e_verdade(monkeypatch, avisos, ia_da_apelacao):
    # Pedido do Rafael (23/10, P5): o texto do recurso pronto para copiar, de cada punição sem recurso.
    ident = _postado_pelo_robo()
    app = AppDaSaude()
    resultado = robo.rodada(saude=True, d=app, agora=momento("2026-10-24 10:00"))
    assert resultado == "saúde lida: 3 punição(ões) em 30 dias, 2 nova(s)"
    punicoes = {p["tipo"]: p for p in robo.apelacoes.todas()}
    irrelevante = punicoes["Produto Irrelevante"]
    assert irrelevante["situacao"] == "pendente" and irrelevante["rascunho"] == ident and irrelevante["fonte"] == "viral"
    assert irrelevante["texto"].startswith("O vídeo mostra o mesmo produto") and len(irrelevante["texto"]) <= 200
    assert irrelevante["postado_em"] == "18:46:10 2026-10-23"
    # Só um pedido à IA: a de propriedade intelectual, de vídeo que não é dos Autorais, não ganha texto.
    assert len(ia_da_apelacao) == 1 and VESTIDO in ia_da_apelacao[0] and "vestido do vídeo" in ia_da_apelacao[0]
    intelectual = punicoes["Violação de Propriedade Intelectual"]
    assert intelectual["texto"] == "" and "outro canal" in intelectual["observacao"]
    assert punicoes["Contrafeito"]["situacao"] == "aceita"
    # Nunca abre o Recurso: só lê a tela Removido e volta.
    assert "Apelar aqui." not in app.toques and "Enviar" not in app.toques
    # A Saúde também mostra a suspensão: guardada e avisada uma vez.
    assert robo.ler_config()["robo_suspenso_ate"] == "2026-10-26 19:04:26"
    assert any("suspendeu a sua conta" in a for a in avisos)
    assert "Pontos de penalidade: 6" in avisos[-1] and "2 nova(s)" in avisos[-1]
    estado = robo.ler_estado()
    assert estado["saude_pontos"] == 6 and estado["saude_punicoes"] == 3
    # De novo: nada novo, a IA não é chamada de novo.
    robo.rodada(saude=True, d=AppDaSaude(), agora=momento("2026-10-24 11:00"))
    assert len(ia_da_apelacao) == 1 and len(robo.apelacoes.todas()) == 3


def test_punicao_sem_apelar_aqui_nao_e_lembrada(monkeypatch, avisos, ia_da_apelacao):
    monkeypatch.setitem(TELAS_DA_SAUDE, "removido_1", _removido("Outro vídeo", "10:00:00 2026-10-05", apelar=False))
    robo.rodada(saude=True, d=AppDaSaude(), agora=momento("2026-10-24 10:00"))
    irrelevante = next(p for p in robo.apelacoes.todas() if p["tipo"] == "Produto Irrelevante")
    assert irrelevante["situacao"] == "encerrada" and "prazo" in irrelevante["observacao"]


def test_saude_uma_vez_por_dia_e_tambem_com_a_conta_suspensa(monkeypatch, avisos, ia_da_apelacao):
    monkeypatch.setattr(robo, "saude_do_dia_pendente", SAUDE_DO_DIA)
    ativar(robo_inicio=0, robo_fim=24, robo_suspenso_ate="2026-10-26 19:04:26")
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-24 10:00")))
    assert robo.rodada(d=AppDaSaude(), agora=momento("2026-10-24 10:00")).startswith("saúde lida")
    # Já leu hoje: com a conta suspensa, não toca mais no celular.
    assert robo.rodada(d=Intocavel(), agora=momento("2026-10-24 10:15")).startswith("conta suspensa")
    assert robo.saude_do_dia_pendente(momento("2026-10-25 08:00"))


def test_saude_que_nao_abre_nao_toma_as_rodadas_do_dia(monkeypatch, avisos):
    monkeypatch.setattr(robo, "saude_do_dia_pendente", SAUDE_DO_DIA)
    ativar(robo_inicio=0, robo_fim=24)
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-24 10:00")))
    # O app de mentira comum não tem o Centro do criador: a leitura para.
    assert "saude: parado" in robo.rodada(d=AppDeMentira(), agora=momento("2026-10-24 10:00"))
    assert robo.o_que_fazer(robo.ler_config(), momento("2026-10-24 10:15")) != ("saude", None)


def test_aviso_de_penalidade_nas_notificacoes_pede_a_saude_de_novo():
    robo.gravar_estado(saude_lida_em="2026-10-24 08:00:00", saude_tentada_em="2026-10-24 08:00:00",
                       penalidade_vista_em="2026-10-24 09:00:00")
    assert not robo.saude_pedida_pela_notificacao(momento("2026-10-24 10:00"))     # leu há menos de 6 h
    assert robo.saude_pedida_pela_notificacao(momento("2026-10-24 14:30"))
    robo.gravar_estado(saude_tentada_em="2026-10-24 14:31:00")
    assert not robo.saude_pedida_pela_notificacao(momento("2026-10-24 22:00"))     # nada visto depois


def test_punicoes_na_tela_e_tela_removido():
    xml = _xml(*TELAS_DA_SAUDE["saude"])
    punicoes = robo.punicoes_na_tela(xml)
    assert [(p["tipo"], p["data"], p["status"]) for p in punicoes] == [
        ("Produto Irrelevante", "23/10/2026 19:04:25", "Não Recorrido"),
        ("Contrafeito", "06/10/2026 22:44:53", "Bem-sucedido"),
        ("Violação de Propriedade Intelectual", "18/10/2026 20:20:56", "Não Recorrido")]
    assert robo.pontos_de_penalidade(xml) == 6
    # Punição cortada embaixo da tela (sem o status) fica para depois de rolar.
    assert robo.punicoes_na_tela(_xml(*TELAS_DA_SAUDE["saude"][:-1]))[-1]["tipo"] == "Contrafeito"
    detalhe = robo.ler_removido(_xml(*TELAS_DA_SAUDE["removido_3"]))
    assert detalhe == {"titulo": "Organizador de Gaveta #casa", "postado_em": "20:20:00 2026-10-18",
                       "explicacao": EXPLICACAO, "pode_apelar": True}


def test_celular_fora_na_suspensao_nao_pausa_nem_avisa(monkeypatch, avisos):
    # Pedido do Rafael (24/10): na suspensão ele pode tirar o Motorola do carregador.
    monkeypatch.setattr(robo, "saude_do_dia_pendente", SAUDE_DO_DIA)
    ativar(robo_inicio=0, robo_fim=24, robo_suspenso_ate="2026-10-26 19:04:26")
    tentativas = []
    monkeypatch.setattr(robo.av, "tela_aberta", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "conectado", lambda: False)
    monkeypatch.setattr(robo.celular_robo, "reconectar_sozinho",
                        lambda: tentativas.append(1) or (False, "a Depuração por Wi-Fi está desligada no celular"))
    assert "celular fora (esperado)" in robo.rodada(agora=momento("2026-10-24 10:00"))
    assert robo.ler_config()["robo_pausado"] is False and avisos == []
    # A leitura do dia já contou: as rodadas seguintes nem procuram o celular.
    assert robo.rodada(agora=momento("2026-10-24 10:15")).startswith("conta suspensa") and tentativas == [1]
    # Acabou a suspensão (com a folga) e o celular não voltou: pausa e avisa, como sempre.
    assert "desconectado" in robo.rodada(agora=momento("2026-10-26 19:30"))
    assert robo.ler_config()["robo_pausado"] is True and "Retomar Postagem" in avisos[-1]



def test_aviso_antigo_nas_notificacoes_nao_vale_se_a_saude_nao_mostra_o_bloqueio(monkeypatch, avisos, conta_suspensa):
    # Pedido do Rafael (24/10): o recurso aceito tira a suspensão antes do prazo, mas o aviso
    # antigo continua nas Notificações; quem diz a situação de agora é a Saúde do Vídeo.
    sem_bloqueio = [n for n in TELAS_DA_SAUDE["saude"] if "banido" not in n.casefold() and "Banido" not in n]
    monkeypatch.setitem(TELAS_DA_SAUDE, "saude", sem_bloqueio)
    monkeypatch.setitem(CAMINHO, ("perfil", "Postar vídeo"), "camera")
    app = AppDaSaude()
    assert robo.ler_suspensao(app, momento("2026-10-24 10:00")) is None
    assert robo.suspensao_retirada(datetime(2026, 10, 26, 19, 4, 26, tzinfo=fuso_horario))
    # Da segunda vez nem abre a Saúde: a suspensão já ficou anotada como retirada.
    app = AppDaSaude()
    assert robo.ler_suspensao(app, momento("2026-10-24 11:00")) is None and "Centro do criador" not in app.toques
    # Com o bloqueio na Saúde, vale a data dela.
    robo.db.salvar_config(robo.CHAVE_ESTADO, {})
    monkeypatch.setitem(TELAS_DA_SAUDE, "saude", TELAS_DA_SAUDE["saude"] + [_no(SAUDE_BANIDO, clicavel=False)])
    assert robo.ler_suspensao(AppDaSaude(), momento("2026-10-24 12:00")).day == 26


def test_suspensao_tirada_antes_do_prazo_volta_na_leitura_da_saude(monkeypatch, avisos, ia_da_apelacao):
    sem_bloqueio = [n for n in TELAS_DA_SAUDE["saude"] if "banido" not in n.casefold()]
    monkeypatch.setitem(TELAS_DA_SAUDE, "saude", sem_bloqueio)
    ativar(robo_inicio=8, robo_fim=22, robo_suspenso_ate="2026-10-26 19:04:26")
    aprovado = _rascunho("aprovado", postar_em="2026-10-24 09:00:00")
    robo.rodada(saude=True, d=AppDaSaude(), agora=momento("2026-10-24 10:00"))
    config = robo.ler_config()
    assert "robo_suspenso_ate" not in config and config["robo_pausado"] is False
    assert any("tirou a suspensão antes do prazo" in a for a in avisos)
    assert robo.pegar(aprovado)["postar_em"] > "2026-10-24 10:00:00"


def test_punicao_que_sumiu_da_lista_avisa_que_o_recurso_deu_certo(monkeypatch, avisos, ia_da_apelacao):
    robo.apelacoes.guardar("Produto Irrelevante", "22/10/2026 11:00:00", "Não Recorrido", titulo="Garrafa",
                           agora=momento("2026-10-23 10:00"))
    robo.rodada(saude=True, d=AppDaSaude(), agora=momento("2026-10-24 10:00"))
    sumiu = next(p for p in robo.apelacoes.todas() if p["data_punicao"] == "22/10/2026 11:00:00")
    assert sumiu["situacao"] == "retirada"
    assert any("deu certo" in a and "22/10/2026 11:00:00" in a for a in avisos)



def test_depois_do_ja_recorri_a_saude_e_lida_de_hora_em_hora_ate_o_resultado(monkeypatch, avisos, ia_da_apelacao):
    # Escolha do Rafael (24/10, P6): de hora em hora depois do Já recorri, até sair o resultado.
    ap = robo.apelacoes
    ident = ap.guardar("Produto Irrelevante", "23/10/2026 19:04:25", "Não Recorrido", titulo="Botijão",
                       agora=momento("2026-10-24 09:00"))
    assert not robo.saude_pedida_pelo_recurso(momento("2026-10-24 10:00"))
    ap.marcar(ident, ap.RECORRIDA, momento("2026-10-24 10:00"))
    robo.gravar_estado(saude_tentada_em="2026-10-24 09:30:00")
    assert robo.saude_pedida_pelo_recurso(momento("2026-10-24 10:30"))
    ativar(robo_inicio=0, robo_fim=24)
    robo.gravar_estado(treino_semana=robo.semana(momento("2026-10-24 10:30")))
    assert robo.o_que_fazer(robo.ler_config(), momento("2026-10-24 10:30")) == ("saude", None)
    # Leu agora: só daqui a 1 h.
    robo.gravar_estado(saude_tentada_em="2026-10-24 10:30:00")
    assert not robo.saude_pedida_pelo_recurso(momento("2026-10-24 11:00"))
    # O resultado saiu (recusado): para de olhar e avisa.
    original = TELAS_DA_SAUDE["saude"]
    monkeypatch.setitem(TELAS_DA_SAUDE, "saude", original[:6]
                        + _punicao_na_lista("Produto Irrelevante", "23/10/2026 19:04:25", "Malsucedido", 1950)
                        + original[9:])
    robo.rodada(saude=True, d=AppDaSaude(), agora=momento("2026-10-24 11:40"))
    assert ap.pegar(ident)["situacao"] == "recusada" and not ap.esperando_resultado(momento("2026-10-24 12:00"))
    assert any("não aceitou o recurso" in a for a in avisos)
    # Já recorri de mais de 7 dias sem resultado: para de olhar.
    outra = ap.guardar("Contrafeito", "20/10/2026 10:00:00", "Não Recorrido", agora=momento("2026-10-20 11:00"))
    ap.marcar(outra, ap.RECORRIDA, momento("2026-10-20 12:00"))
    assert ap.esperando_resultado(momento("2026-10-26 12:00")) and not ap.esperando_resultado(momento("2026-10-28 12:00"))

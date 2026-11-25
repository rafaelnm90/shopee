"""
O vídeo que viraliza nos fixados do Perfil (P263 1): as curtidas de cada vídeo contadas nas linhas
"curtiu seu vídeo." das Notificações (interacoes_shopee_video), juntadas pela marca da capa pequena
(visualizacoes_shopee_video), a troca no app (robo_shopee_video.fixar_o_que_viraliza) e o comentário
no vídeo fixado (pedido do Rafael, 21/11/2026).
"""
import random
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

import pytest
from PIL import Image

import interacoes_shopee_video as it
import postador_shopee_video as ps
import robo_shopee_video as robo
import visualizacoes_shopee_video as vz
from conftest import inserir
from fuso import fuso_horario

AGORA = datetime(2026, 11, 21, 10, 0, tzinfo=fuso_horario)
FILTRO = "Lives, Vídeos e Prêmios"


@pytest.fixture(autouse=True)
def registro_sem_prazo(monkeypatch):
    # Os testes anotam no registro com a hora AGORA, fixa, e o robô anota também com a hora de verdade, que apaga o que
    # passou dos 3 dias do registro: a partir de 24/11/2026, o anotado com AGORA sumia no meio do teste. Aqui o
    # registro não perde nada pela data do dia em que os testes rodam.
    monkeypatch.setattr(robo.registro_processos, "DIAS_DO_REGISTRO", 100 * 365)


def _el(texto="", desc="", ident="", classe="TextView", caixa=(0, 0, 10, 10), clicavel=False):
    x1, y1, x2, y2 = caixa
    clicar = "true" if clicavel else "false"
    atributos = (f'text="{escape(texto, {chr(34): "&quot;"})}" content-desc="{escape(desc, {chr(34): "&quot;"})}" '
                 f'class="android.widget.{classe}" clickable="{clicar}" package="com.shopee.br"')
    if ident:
        atributos += f' resource-id="com.shopee.br:id/{ident}"'
    return f'<node {atributos} bounds="[{x1},{y1}][{x2},{y2}]"/>'


def _xml(*nos):
    raiz = '<node class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">'
    return f'<hierarchy>{raiz}{"".join(nos)}</node></hierarchy>'


BARRA = [_el("Notificações", ident="title", caixa=(650, 2350, 860, 2400), clicavel=True),
         _el("Eu", ident="title", caixa=(870, 2350, 1080, 2400), clicavel=True),
         _el(ident="sp_bottom_navigation_container", classe="FrameLayout", caixa=(0, 2255, 1080, 2400))]
CHIPS = [_el("Notificações", caixa=(400, 160, 680, 220)),
         _el("Mais relevantes", caixa=(28, 474, 206, 506), clicavel=True),
         _el(FILTRO, caixa=(450, 458, 630, 522), clicavel=True)]
# As linhas da lista começam abaixo dos filtros e têm a altura das do Motorola (20/11/2026).
PRIMEIRA_LINHA, ALTURA_DA_LINHA, LINHAS_NA_TELA = 556, 190, 8


def _linha(texto, hora, y, capa_a_direita):
    """A linha das Notificações do Motorola: a foto (ou a capa) à esquerda, o aviso, a hora e a capa à direita."""
    nos = [_el(classe="ViewGroup", caixa=(0, y, 1080, y + 189), clicavel=True),
           _el(classe="ImageView", caixa=(32, y + 42, 137, y + 147)),
           _el(texto, caixa=(168, y + 42, 800, y + 95)),
           _el(hora, caixa=(168, y + 111, 240, y + 148))]
    if capa_a_direita:
        nos.append(_el(classe="ImageView", caixa=(944, y + 42, 1049, y + 147)))
    return nos


def _desenho(semente, tamanho=105):
    """Uma imagem que é sempre a mesma para a mesma semente: a capa de um vídeo (ou a foto de quem curtiu)."""
    sorteio = random.Random(semente)
    pequeno = Image.new("L", (9, 8))
    pequeno.putdata([sorteio.randrange(0, 256) for _ in range(72)])
    return pequeno.resize((tamanho, tamanho), Image.NEAREST).convert("RGB")


def _capa_na_grade(video):
    """A capa do vídeo no quadro da grade do Perfil (358 x 476): outra imagem, e não a capa pequena das Notificações."""
    return _desenho(f"capa {video}").resize((358, 476), Image.NEAREST)


def _notificacoes(*linhas):
    return _xml(*CHIPS, *[no for i, (texto, hora, direita) in enumerate(linhas)
                          for no in _linha(texto, hora, PRIMEIRA_LINHA + ALTURA_DA_LINHA * i, direita)], *BARRA)


# --- A leitura da lista ---

def test_curtidas_das_notificacoes_pegam_a_capa_da_direita_ou_a_da_esquerda():
    xml = _xml(*CHIPS,
               *_linha("Ana Your comment gets a like.", "18:59", 556, True),
               *_linha("Bia curtiu seu vídeo.", "18:38", 746, True),
               *_linha("Caio curtiu seu vídeo.", "17:37", 936, False),
               *_linha('Dani comentou no seu vídeo: "Amei"', "17:00", 1126, True),
               # A linha cortada pela barra de baixo fica para a próxima rolada.
               *_linha("Edu curtiu seu vídeo.", "16:10", 2150, True), *BARRA)
    linhas = it.curtidas_das_notificacoes(xml, "Lives, Vídeos")
    assert [(l["texto"], l["hora"], l["miniatura"]) for l in linhas] == [
        ("Bia curtiu seu vídeo.", "18:38", (944, 788, 1049, 893)),
        ("Caio curtiu seu vídeo.", "17:37", (32, 978, 137, 1083))]
    assert linhas[0]["ponto"] == (484, 814)
    # Sem a fileira de filtros, a tela não é a lista.
    sem_filtros = _xml(*_linha("Bia curtiu seu vídeo.", "18:38", 746, True))
    assert it.curtidas_das_notificacoes(sem_filtros, "Lives, Vídeos") == []


def test_momento_da_hora_nos_jeitos_que_o_app_escreve():
    assert it.momento_da_hora("09:38", AGORA) == AGORA.replace(hour=9, minute=38)
    assert it.momento_da_hora("Hoje 07:05", AGORA) == AGORA.replace(hour=7, minute=5)
    assert it.momento_da_hora("Ontem 21:40", AGORA) == AGORA.replace(day=20, hour=21, minute=40)
    assert it.momento_da_hora("20-11 18:38", AGORA) == AGORA.replace(day=20, hour=18, minute=38)
    assert it.momento_da_hora("há 5 min", AGORA) == AGORA - timedelta(minutes=5)
    assert it.momento_da_hora("há 2 h", AGORA) == AGORA - timedelta(hours=2)
    # A hora de hoje depois de agora é de ontem (a lista nunca mostra o futuro).
    assert it.momento_da_hora("23:50", AGORA) == AGORA.replace(day=20, hour=23, minute=50)
    for sem_hora in ("20-11", "25:00", "", "semana passada"):
        assert it.momento_da_hora(sem_hora, AGORA) is None


def test_marca_da_miniatura_junta_a_mesma_capa_e_separa_as_outras():
    tela = Image.new("RGB", (1080, 2400), "white")
    tela.paste(_desenho("video A"), (944, 788))
    tela.paste(_desenho("video A"), (32, 1168))
    tela.paste(_desenho("video B"), (944, 1358))
    a1 = vz.marca_da_miniatura(tela, (944, 788, 1049, 893))
    a2 = vz.marca_da_miniatura(tela, (32, 1168, 137, 1273))
    b = vz.marca_da_miniatura(tela, (944, 1358, 1049, 1463))
    assert a1 == a2 and vz.diferenca(a1, b) > vz.MARCA_PARECIDA
    # A capa que ainda não carregou (de uma cor só) fica sem marca.
    assert vz.marca_da_miniatura(tela, (944, 1548, 1049, 1653)) is None


def test_videos_mais_curtidos_juntam_pela_capa_e_contam_so_as_24_h():
    parecida = f"{int('f0f0f0f0f0f0f0f0', 16) ^ 0b111:016x}"   # 3 bits diferentes: o mesmo vídeo
    curtidas = [{"texto": f"Pessoa {i} curtiu seu vídeo.", "chave": f"10:0{i}", "video": "f0f0f0f0f0f0f0f0",
                 "momento": AGORA - timedelta(minutes=i)} for i in range(4)]
    curtidas += [{"texto": "Pessoa 9 curtiu seu vídeo.", "chave": "09:00", "video": parecida,
                  "momento": AGORA - timedelta(hours=1)},
                 {"texto": "Outra curtiu seu vídeo.", "chave": "09:30", "video": "0f0f0f0f0f0f0f0f",
                  "momento": AGORA - timedelta(minutes=30)},
                 # A de ontem, mais de 24 h atrás, fica fora da conta.
                 {"texto": "Velha curtiu seu vídeo.", "chave": "2026-11-20 09:00", "video": "f0f0f0f0f0f0f0f0",
                  "momento": AGORA - timedelta(hours=25)}]
    assert it.guardar_curtidas(curtidas, AGORA) == 7
    # A mesma linha lida de novo não conta duas vezes.
    assert it.guardar_curtidas(curtidas[:2], AGORA) == 0
    assert it.videos_mais_curtidos(AGORA) == [{"video": "f0f0f0f0f0f0f0f0", "curtidas": 5},
                                               {"video": "0f0f0f0f0f0f0f0f", "curtidas": 1}]


# --- A folha do compartilhar e o coração ---

FOLHA = ["Promover", "Copiar link", "Salvar"]
# Os nomes do Fixar e do Desfixar: os da gravação do Rafael (20/11) e os do Motorola do robô (21/11; o "Afixar" é o
# par do "Desafixar" que ele mostrou).
DO_RAFAEL, DO_MOTOROLA = ("Fixar", "Desfixar"), ("Afixar", "Desafixar")


def _folha(fixado, rotulos=DO_RAFAEL):
    nos = [_el("Link copiado", desc="title of share panel", caixa=(434, 1738, 646, 1789)),
           _el("WhatsApp", caixa=(60, 2010, 180, 2050))]
    for i, rotulo in enumerate(FOLHA + [rotulos[1] if fixado else rotulos[0]]):
        nos.append(_el(rotulo, caixa=(65 + 250 * i, 2234, 190 + 250 * i, 2269)))
    return _xml(*nos)


def test_folha_do_compartilhar_nunca_confunde_o_fixar_com_o_desfixar():
    assert it.estado_do_fixar(_folha(fixado=False)) == "fixar"
    assert it.estado_do_fixar(_folha(fixado=True)) == "desfixar"
    assert it.estado_do_fixar(_xml(_el("Copiar link", caixa=(299, 2234, 421, 2269)))) is None
    # O ps.achar pega "contendo" e cairia no Desfixar; o texto exato, não.
    assert ps.achar(_folha(fixado=True), "Fixar") is not None
    assert it.texto_exato(_folha(fixado=True), "Fixar") is None


def test_folha_do_motorola_com_o_desafixar():
    # Caso de 21/11 (17:24): no Motorola do robô, a folha do vídeo fixado mostra "Desafixar", e o robô só conhecia o
    # "Desfixar" da gravação do Rafael: o comentário no 1º fixado parou com o vídeo fixado na tela.
    fixado, solto = _folha(fixado=True, rotulos=DO_MOTOROLA), _folha(fixado=False, rotulos=DO_MOTOROLA)
    assert it.estado_do_fixar(fixado) == "desfixar"
    assert it.estado_do_fixar(solto) == "fixar"
    assert it.rotulo_na_tela(fixado, it.DESFIXAR) == "Desafixar"
    # O nome de fixar nunca casa com o de desfixar (nem o "Afixar" com o "Desafixar").
    assert it.rotulo_na_tela(fixado, it.FIXAR) is None and it.rotulo_na_tela(solto, it.DESFIXAR) is None
    assert not ps.eh_alvo_proibido("Desafixar") and not ps.eh_alvo_proibido("Afixar")


def test_aviso_do_limite_de_fixados_com_os_dois_nomes():
    for texto in ("Você só pode fixar até 3 vídeos", "Você só pode afixar até 3 vídeos"):
        assert it.limite_de_fixados(_xml(_el(texto, caixa=(200, 1100, 880, 1180))))
    assert not it.limite_de_fixados(_folha(fixado=True, rotulos=DO_MOTOROLA))


def test_o_promover_nunca_e_tocado():
    assert ps.texto_proibido("Promover") and ps.eh_alvo_proibido("Promover")
    folha = _folha(fixado=False)
    assert ps.proibido_no_ponto(folha, *it.texto_exato(folha, "Promover"))
    assert not ps.proibido_no_ponto(folha, *it.texto_exato(folha, "Fixar"))


def _player(legenda, curtidas, curtido=False):
    """
    O vídeo do Rafael aberto pela curtida, como no Motorola (20/11/2026): o número dentro do coração e o
    Promover embaixo do compartilhar.
    """
    return _xml(_el(ident="rn_vod_player_view_with_text", classe="FrameLayout", caixa=(0, 0, 1080, 2263)),
                _el(desc="click top right create icon", classe="ViewGroup", caixa=(980, 136, 1043, 199), clicavel=True),
                _el(desc="click other profile avatar icon", classe="ViewGroup", caixa=(944, 1375, 1059, 1491),
                    clicavel=True),
                _el(desc="unlike video" if curtido else "like video", ident="like btn", classe="ViewGroup",
                    caixa=(926, 1569, 1078, 1721), clicavel=True),
                _el(str(curtidas), caixa=(984, 1669, 1020, 1706)),
                _el(desc="click video comment_icon", classe="ViewGroup", caixa=(955, 1722, 1050, 1890), clicavel=True),
                _el("1", caixa=(993, 1853, 1011, 1890)),
                _el(desc="click video share icon", classe="ViewGroup", caixa=(923, 1890, 1080, 2074), clicavel=True),
                _el("Promover", caixa=(932, 2037, 1071, 2074)),
                _el(desc="click video music icon", classe="ViewGroup", caixa=(949, 2116, 1054, 2221), clicavel=True),
                _el(desc="video caption user", classe="ViewGroup", caixa=(35, 2091, 468, 2148), clicavel=True),
                _el("@loja", caixa=(35, 2091, 468, 2148)),
                _el(desc="video caption content", classe="ViewGroup", caixa=(35, 2171, 817, 2221), clicavel=True),
                _el(legenda, caixa=(35, 2171, 817, 2221)), *BARRA)


def test_curtidas_do_video_le_o_numero_dentro_do_coracao():
    assert it.curtidas_do_video(_player("Poltrona", 69)) == 69
    assert it.curtidas_do_video(_player("Poltrona", "1,2 mil", curtido=True)) == 1200
    assert it.curtidas_do_video(_xml(*BARRA)) is None


# --- A troca no celular ---

# A grade do Perfil (3 quadros por linha, como no Motorola): o "Rascunhos: N" e os fixados primeiro.
VISTAS = {"T1": "235,2mil", "T2": "1,2 mil", "T3": "263,8mil", "A": "240,1mil", "N1": "50", "N2": "70"}


class CelularDasCurtidas:
    """
    A Shopee do Rafael nas telas da P263 1: a lista das Notificações (linhas de curtida, a lista rola de 6 em 6), o
    vídeo aberto (pela curtida ou pela grade), a folha do compartilhar e a grade do Perfil. curtidas: [(texto, hora,
    vídeo, capa à direita)]; fixados: os vídeos fixados, na ordem da grade; no_coracao: as curtidas que o coração de
    cada vídeo mostra. Depois do Copiar link a folha fecha. some_depois: o vídeo cujas curtidas saem da lista depois
    da 1ª vez que ele abre. folha_atrasada: a folha do vídeo aberto pelas Notificações mostra o Fixar no vídeo já
    fixado até o app carregar o Perfil ("perfil"; Motorola, 25/11/2026, às 08:03) ou até um Desfixar ("desfixar").
    sem_legenda: de onde ("lista", as Notificações, ou "perfil", a grade) o vídeo aberto mostra o player sem a legenda.
    capas: o print da grade mostra a capa de cada vídeo (sem elas, as capas não carregaram, e o robô não tem a marca
    delas).
    """

    def __init__(self, curtidas, fixados=("T1", "T2", "T3"), no_coracao=None, some_depois=None, limite=3,
                 rotulos=DO_RAFAEL, folha_atrasada=None, sem_legenda=(), capas=False):
        self.curtidas, self.fixados, self.rotulos = list(curtidas), list(fixados), rotulos
        self.no_coracao = no_coracao or {}
        self.some_depois, self.limite = some_depois, limite
        self.folha_atrasada, self.perfil_visto, self.desfixou = folha_atrasada, False, False
        self.sem_legenda, self.capas = sem_legenda, capas
        self.atual, self.aberto, self.de_onde, self.inicio_da_lista = "inicio", None, None, 0
        self.clipboard, self.toques, self.abertos = "https://s.shopee.com.br/linkAntigo", [], []

    # As telas

    def _visiveis(self):
        return self.curtidas[self.inicio_da_lista:self.inicio_da_lista + LINHAS_NA_TELA]

    def _grade(self):
        quadros = [("rascunhos", False)] + [(v, True) for v in self.fixados] + [(v, False) for v in ("N1", "N2")]
        nos = [_el("Postar vídeo", caixa=(700, 1050, 1040, 1150), clicavel=True)]
        for i, (video, fixado) in enumerate(quadros[:6]):
            x, y = 361 * (i % 3), 1205 + 478 * (i // 3)
            nos.append(_el(desc=f"video {i}", classe="ViewGroup", caixa=(x, y, x + 358, y + 476), clicavel=True))
            if video == "rascunhos":
                nos.append(_el("Rascunhos: 1", caixa=(x + 40, y + 250, x + 320, y + 300)))
                continue
            if fixado:
                nos.append(_el("Fixado", caixa=(x + 10, y + 20, x + 110, y + 60)))
            nos.append(_el(VISTAS[video], caixa=(x + 40, y + 420, x + 200, y + 460)))
        return nos, quadros

    def dump_hierarchy(self):
        if self.atual == "lista":
            return _notificacoes(*[(t, h, d) for t, h, _v, d in self._visiveis()])
        if self.atual == "player":
            legenda = "" if self.de_onde in self.sem_legenda else f"Legenda do {self.aberto}"
            return _player(legenda, self.no_coracao.get(self.aberto, 57))
        if self.atual == "folha":
            fixado = self.aberto in self.fixados
            if fixado and self.de_onde == "lista" and (
                    (self.folha_atrasada == "perfil" and not self.perfil_visto)
                    or (self.folha_atrasada == "desfixar" and not self.desfixou)):
                fixado = False
            return _folha(fixado, self.rotulos)
        if self.atual == "limite":
            aviso = f"Você só pode {self.rotulos[0].lower()} até 3 vídeos"
            return _xml(_el(aviso, caixa=(200, 1100, 880, 1180)), *BARRA)
        if self.atual == "perfil":
            self.perfil_visto = True
            return _xml(*self._grade()[0], *BARRA)
        return _xml(*BARRA)

    def screenshot(self):
        imagem = Image.new("RGB", (1080, 2400), "white")
        if self.atual == "lista":
            for i, (texto, _hora, video, direita) in enumerate(self._visiveis()):
                y = PRIMEIRA_LINHA + ALTURA_DA_LINHA * i + 42
                if direita:
                    imagem.paste(_desenho(f"foto de {texto}"), (32, y))
                    imagem.paste(_desenho(video), (944, y))
                else:
                    imagem.paste(_desenho(video), (32, y))
        if self.atual == "perfil" and self.capas:
            for i, (video, _fixado) in enumerate(self._grade()[1][:6]):
                if video != "rascunhos":
                    imagem.paste(_capa_na_grade(video), (361 * (i % 3), 1205 + 478 * (i // 3)))
        return imagem

    # Os toques

    def click(self, x, y):
        tocados = [el for el in ps.elementos(self.dump_hierarchy()) if ps._dentro((x, y), el["caixa"])]
        textos = [el["texto"] or el["descricao"] for el in tocados if el["texto"] or el["descricao"]]
        self.toques.append(textos[-1] if textos else (x, y))
        assert "Promover" not in textos, "o robô tocou no Promover"
        if self.atual == "lista":
            linha = (y - PRIMEIRA_LINHA) // ALTURA_DA_LINHA
            self.aberto = self._visiveis()[linha][2]
            self._abrir("lista")
        elif self.atual == "perfil":
            _nos, quadros = self._grade()
            coluna, fileira = x // 361, (y - 1205) // 478
            self.aberto = quadros[fileira * 3 + coluna][0]
            self._abrir("perfil")
        elif self.atual == "player" and "click video share icon" in textos:
            self.atual = "folha"
        elif self.atual == "folha":
            if "Copiar link" in textos:
                self.clipboard, self.atual = f"https://s.shopee.com.br/{self.aberto}", "player"
            elif self.rotulos[1] in textos:
                self.fixados.remove(self.aberto)
                self.atual, self.desfixou = "player", True
            elif self.rotulos[0] in textos:
                if self.aberto in self.fixados:
                    self.atual = "player"
                elif len(self.fixados) >= self.limite:
                    self.atual = "limite"
                else:
                    self.fixados.insert(0, self.aberto)
                    self.atual = "player"

    def _abrir(self, de_onde):
        self.atual, self.de_onde = "player", de_onde
        self.abertos.append(self.aberto)
        if self.aberto == self.some_depois:
            self.curtidas = [c for c in self.curtidas if c[2] != self.aberto]

    def press(self, tecla, meta=None):
        if self.atual in ("folha", "limite"):
            self.atual = "player"
        elif self.atual == "player":
            self.atual = self.de_onde or "inicio"
        else:
            self.atual = "inicio"

    def swipe(self, *pontos):
        if self.inicio_da_lista + LINHAS_NA_TELA < len(self.curtidas):
            self.inicio_da_lista += 6

    def set_clipboard(self, texto):
        self.clipboard = texto

    def app_start(self, pacote, wait=False):
        pass

    def window_size(self):
        return 1080, 2400


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(robo.time, "sleep", lambda s: None)
    monkeypatch.setattr(robo.ps.time, "sleep", lambda s: None)
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    # Os caminhos até a lista e até o Perfil têm testes próprios: aqui o app já abre neles.
    monkeypatch.setattr(robo, "_ir_as_notificacoes", lambda d: d.__dict__.update(atual="lista", inicio_da_lista=0))
    monkeypatch.setattr(robo, "ir_ao_perfil", lambda d: setattr(d, "atual", "perfil"))
    monkeypatch.setattr(robo, "ir_ao_inicio", lambda d: setattr(d, "atual", "inicio"))


@pytest.fixture
def avisos(monkeypatch):
    mandados = []
    monkeypatch.setattr(robo.avisar_rafael, "mandar_texto", lambda texto: mandados.append(texto) or True)
    return mandados


@pytest.fixture(autouse=True)
def comentarios(monkeypatch):
    """
    O comentário no vídeo fixado sem o painel de comentários: o caminho dele no app (robo._comentar_no_aberto) é o
    do comentário de depois do post, com os testes dele (test_interacoes_shopee_video). Aqui, cada chamada anota
    o vídeo aberto no player e o que o robô passou; "falhas": os motivos das próximas chamadas, que param.
    """
    feitos = {"chamadas": [], "falhas": [], "casos": []}

    def comentar(d, video, onde, produto, titulo, anteriores=(), agora=None, ident=None, ao_enviar=None):
        feitos["chamadas"].append({"aberto": d.aberto, "tela": d.atual, "onde": onde, "produto": produto,
                                   "titulo": titulo})
        if feitos["falhas"]:
            raise robo.Parada(feitos["falhas"].pop(0))
        return "comentado", f"Esse vale muito a pena! {len(feitos['chamadas'])}", ("curtido", "curtido")

    monkeypatch.setattr(robo, "_comentar_no_aberto", comentar)
    # O pedido de uma vez do 1º fixado tem os testes dele; nos outros, nenhum pedido.
    monkeypatch.setattr(robo, "PEDIDOS_DE_COMENTARIO_NO_1O_FIXADO", ())
    monkeypatch.setattr(robo, "_guardar_caso", lambda d, acao, resultado, motivo, **k: feitos["casos"].append(
        (acao, resultado, motivo)))
    return feitos


def _aviso_do_comentario(numero, video):
    return (f"💬 Robô da Shopee Vídeo: comentei no vídeo que fixei no seu Perfil e curti o vídeo e o comentário:"
            f"\n\nEsse vale muito a pena! {numero}\n\n🔗 https://s.shopee.com.br/{video}")


def _curtidas(video, quantas, desde=9, direita=True):
    """Curtidas de hoje no vídeo, da mais nova para a mais velha, de 3 em 3 min a partir das 09:5x."""
    momento = AGORA.replace(hour=desde, minute=59)
    linhas = []
    for i in range(quantas):
        quando = momento - timedelta(minutes=3 * i)
        linhas.append((f"Pessoa {video}{i} curtiu seu vídeo.", quando.strftime("%H:%M"), video,
                       direita if i % 3 else not direita))
    return linhas


TOPO = ("Zé curtiu seu vídeo.", "07:00", "VELHO", True)


def _leitura(app):
    """A 1ª leitura das Notificações de hoje, com o topo da anterior no fim da lista: as respostas e a contagem."""
    robo.contar_leitura(AGORA)
    robo.gravar_estado(respostas_topo=it.marca(TOPO[0]))
    assert robo.responder_comentarios(app, AGORA) == "respostas: nenhum comentário novo"


def _registro(processo=robo.PROCESSO_DO_FIXAR):
    return [(r, d) for _m, _p, r, d, _o in robo.registro_processos.sequencia("shopee_video", processo,
                                                                            "2000-01-01 00:00:00")]


def test_video_com_10_curtidas_entra_no_lugar_do_fixado_de_menos_visualizacoes(avisos, comentarios):
    app = CelularDasCurtidas(_curtidas("A", 10) + _curtidas("B", 2, desde=8) + [TOPO])
    _leitura(app)
    assert it.videos_mais_curtidos(AGORA)[:2] == [{"video": it.videos_mais_curtidos(AGORA)[0]["video"], "curtidas": 10},
                                                   {"video": it.videos_mais_curtidos(AGORA)[1]["video"], "curtidas": 2}]
    assert _registro(robo.PROCESSO_DAS_CURTIDAS) == [("lidas", "12 nova(s); o vídeo mais curtido com 10 em 24 h")]
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: troquei o fixado de menos visualizações pelo "
                                                     "vídeo que viraliza; comentei nele")
    # O de menos visualizações (o T2, com 1,2 mil) saiu, e o A entrou no topo dos fixados. Antes do Desafixar, o robô
    # conferiu que o A não é um dos 3 fixados, abertos pela grade (pedido do Rafael, 25/11/2026).
    assert app.fixados == ["A", "T1", "T3"]
    assert app.abertos == ["A", "T1", "T2", "T3", "T2", "A"]
    # Pedido do Rafael (21/11): logo depois do Fixar, o robô comenta no vídeo fixado, que está no player, e o
    # aviso do comentário vem com o texto e o link.
    assert comentarios["chamadas"] == [{"aberto": "A", "tela": "player", "onde": robo.ONDE_DO_FIXADO, "produto": "",
                                        "titulo": "Legenda do A"}]
    assert avisos == ["📌 Robô da Shopee Vídeo: fixei no seu Perfil o vídeo que está viralizando (10 curtidas nas "
                      "últimas 24 h, nas Notificações).\n\n📌 Fixado agora: https://s.shopee.com.br/A\n📤 Saiu dos "
                      "fixados (o de menos visualizações, 1.200): https://s.shopee.com.br/T2",
                      _aviso_do_comentario(1, "A")]
    assert _registro(robo.PROCESSO_DO_COMENTARIO_FIXADO) == [("comentado", "")]
    assert _registro() == [("desfixado", "o de menos visualizações"),
                           ("trocado", "no lugar do fixado de menos visualizações")]
    # O que saiu fica guardado: ele volta no lugar vazio sem vídeo curtido para ele (P299 1).
    assert robo._o_tirado()["link"] == "https://s.shopee.com.br/T2"
    # Uma troca por leitura: a continuação da mesma leitura não troca de novo.
    assert robo.fixar_o_que_viraliza(app, AGORA) == ""


def test_video_ja_fixado_fica_como_esta_ganha_o_comentario_e_sai_da_conta_por_um_dia(avisos, comentarios):
    # Pedido do Rafael (21/11): o vídeo que viraliza e ele já fixou à mão também ganha o comentário do robô.
    app = CelularDasCurtidas(_curtidas("A", 11) + [TOPO], fixados=("T1", "A", "T3"))
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: o vídeo que viraliza já estava fixado; "
                                                     "comentei nele")
    assert app.fixados == ["T1", "A", "T3"] and "Desfixar" not in app.toques and "Fixar" not in app.toques
    assert _registro() == [("já fixado", "")]
    assert comentarios["chamadas"] == [{"aberto": "A", "tela": "player", "onde": robo.ONDE_DO_FIXADO, "produto": "",
                                        "titulo": "Legenda do A"}]
    assert avisos == [_aviso_do_comentario(1, "A")]
    # Na leitura seguinte, o mesmo vídeo nem abre.
    robo.contar_leitura(AGORA + timedelta(hours=3))
    assert robo.fixar_o_que_viraliza(app, AGORA + timedelta(hours=3)) == ""
    assert app.abertos == ["A"] and len(comentarios["chamadas"]) == 1
    assert _registro()[-1] == ("nenhum vídeo para fixar", "o mais curtido com 11 em 24 h, já visto")


def test_video_ja_fixado_e_ja_comentado_pelo_robo_fica_sem_outro_comentario(avisos, comentarios):
    app = CelularDasCurtidas(_curtidas("A", 11) + [TOPO], fixados=("T1", "A", "T3"))
    _leitura(app)
    marca = it.videos_mais_curtidos(AGORA)[0]["video"]
    robo._anotar_o_comentario_do_fixado(marca, "https://s.shopee.com.br/A", "comentado", AGORA - timedelta(days=2))
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: nenhum dos vídeos com as curtidas em alta "
                                                     "ficou para fixar")
    assert not comentarios["chamadas"] and not avisos and "Copiar link" not in app.toques
    assert _registro() == [("já fixado", "")]


def test_com_lugar_entre_os_fixados_so_fixa(avisos):
    app = CelularDasCurtidas(_curtidas("A", 10) + [TOPO], fixados=("T1", "T3"))
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == "fixar no perfil: fixei o vídeo que viraliza; comentei nele"
    assert app.fixados == ["A", "T1", "T3"] and "Desfixar" not in app.toques
    assert avisos[0].endswith("📌 Fixado agora: https://s.shopee.com.br/A\n\nAinda havia lugar entre os 3 fixados: "
                              "nenhum saiu.")


def test_menos_de_10_curtidas_nao_mexe_nos_fixados(avisos):
    # Com os 3 fixados no Perfil, nenhum sai pelo vídeo com menos de 10 curtidas (o lugar vazio, P299 1, mais abaixo).
    app = CelularDasCurtidas(_curtidas("A", 9) + [TOPO])
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ""
    assert not app.abertos and not avisos
    assert _registro() == [("nenhum vídeo para fixar", "o mais curtido com 9 em 24 h")]


def test_coracao_com_menos_curtidas_que_a_conta_nao_fixa(avisos):
    app = CelularDasCurtidas(_curtidas("A", 10) + [TOPO], no_coracao={"A": 4})
    _leitura(app)
    robo.fixar_o_que_viraliza(app, AGORA)
    assert app.fixados == ["T1", "T2", "T3"] and app.abertos == ["A"] and not avisos
    assert _registro() == [("pulado", "o coração do vídeo com menos curtidas")]


def test_fixar_que_para_depois_do_desfixar_devolve_o_que_saiu_e_avisa_com_os_dois_links(avisos, monkeypatch):
    # Pedido do Rafael (25/11/2026): o Perfil sempre com os 3 fixados. O novo que não fica faz o que saiu voltar,
    # aberto pelo link copiado antes do Desafixar; a leitura seguinte tenta de novo.
    abertos = _abrir_pelo_link(monkeypatch)
    app = CelularDasCurtidas(_curtidas("A", 10) + [TOPO], some_depois="A")
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: parou (a curtida do vídeo não está mais nas "
                                                     "Notificações)")
    assert app.fixados == ["T2", "T1", "T3"] and abertos == ["https://s.shopee.com.br/T2"]
    assert avisos == ["⚠️ Robô da Shopee Vídeo: tirei dos fixados do seu Perfil o vídeo de menos visualizações, para "
                      "dar lugar ao que está viralizando (10 curtidas nas últimas 24 h), mas não consegui fixar o "
                      "novo (a curtida do vídeo não está mais nas Notificações). Pus de volta o que tinha tirado, e o "
                      "seu Perfil continua com os 3 fixados. Tento de novo na próxima leitura das Notificações."
                      "\n\n📤 Saiu: https://s.shopee.com.br/T2\n📌 O que ia entrar: https://s.shopee.com.br/A"]
    assert _registro() == [("desfixado", "o de menos visualizações"),
                           ("devolvido", "o desfixado, depois do fixar que parou"),
                           ("parou", "a curtida do vídeo não está mais nas Notificações")]
    assert robo._o_tirado() is None


def _verificacao_ao_abrir_pelo_link(monkeypatch):
    """A Verificação da Shopee no meio da volta do que saiu, ao abrir o vídeo pelo link."""
    def abrir(d, link):
        raise robo.Verificacao("a Shopee abriu a Verificação")

    monkeypatch.setattr(robo, "_abrir_o_video_do_post", abrir)


def test_volta_do_desfixado_que_para_na_verificacao_avisa_com_os_dois_links(avisos, monkeypatch):
    # O aviso sai mesmo quando a volta do que saiu para no meio, e a Verificação segue adiante: só o Rafael a resolve.
    _verificacao_ao_abrir_pelo_link(monkeypatch)
    app = CelularDasCurtidas(_curtidas("A", 10) + [TOPO], some_depois="A")
    _leitura(app)
    with pytest.raises(robo.Verificacao):
        robo.fixar_o_que_viraliza(app, AGORA)
    assert app.fixados == ["T1", "T3"]
    assert avisos == ["⚠️ Robô da Shopee Vídeo: tirei dos fixados do seu Perfil o vídeo de menos visualizações, para "
                      "dar lugar ao que está viralizando (10 curtidas nas últimas 24 h), mas não consegui fixar o "
                      "novo (a curtida do vídeo não está mais nas Notificações). E não consegui pôr de volta o que "
                      "tirei: se quiser, fixe-o à mão, para o Perfil voltar a ter os 3 fixados.\n\n📤 Saiu: "
                      "https://s.shopee.com.br/T2\n📌 O que ia entrar: https://s.shopee.com.br/A"]
    assert _registro() == [("desfixado", "o de menos visualizações"),
                           ("não devolvido", "o desfixado, depois do fixar que parou")]
    assert robo._o_tirado()["link"] == "https://s.shopee.com.br/T2"


def test_aviso_do_limite_de_fixados_para_sem_mais_toques(avisos):
    app = CelularDasCurtidas(_curtidas("A", 10) + [TOPO], fixados=("T1", "T3"), limite=2)
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: parou (o app disse que o limite de fixados "
                                                     "acabou)")
    assert app.fixados == ["T1", "T3"] and not avisos


def test_troca_dos_fixados_no_motorola_com_o_afixar_e_o_desafixar(avisos, comentarios):
    app = CelularDasCurtidas(_curtidas("A", 10) + _curtidas("B", 2, desde=8) + [TOPO], rotulos=DO_MOTOROLA)
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: troquei o fixado de menos visualizações pelo "
                                                     "vídeo que viraliza; comentei nele")
    assert app.fixados == ["A", "T1", "T3"]
    assert "Desafixar" in app.toques and "Afixar" in app.toques


def test_video_ja_fixado_que_so_se_mostra_fixado_depois_do_perfil_nao_tira_nenhum_fixado(avisos, comentarios):
    # 25/11/2026, às 08:03 (Motorola, o app aberto havia 22 min): o vídeo que viralizava, já fixado, mostrou o Afixar
    # na folha aberta pelas Notificações, antes de o app carregar o Perfil. O robô tirou dos fixados o de menos
    # visualizações e, aberto de novo, o vídeo mostrou o Desafixar: o lugar ficou vazio, e o aviso disse "fixei". O robô
    # passa pelo Perfil antes de olhar a folha: o já fixado só ganha o comentário, e nenhum fixado sai.
    app = CelularDasCurtidas(_curtidas("A", 11) + [TOPO], fixados=("T1", "A", "T2"), folha_atrasada="perfil",
                             rotulos=DO_MOTOROLA)
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: o vídeo que viraliza já estava fixado; "
                                                     "comentei nele")
    assert app.fixados == ["T1", "A", "T2"] and "Desafixar" not in app.toques and "Afixar" not in app.toques
    assert _registro() == [("já fixado", "")]
    assert avisos == [_aviso_do_comentario(1, "A")]


def test_video_ja_fixado_que_a_folha_mostra_sem_fixar_e_conferido_nos_fixados_sem_tirar_nenhum(avisos, comentarios):
    # Pedido do Rafael (25/11/2026): conferir se o vídeo já está fixado antes de tirar qualquer fixado. Mesmo com a
    # folha das Notificações mostrando o Afixar, o robô abre os fixados pela grade e acha o A entre eles pela legenda:
    # nenhum sai, e o A só ganha o comentário, no player em que ficou.
    app = CelularDasCurtidas(_curtidas("A", 11) + [TOPO], fixados=("T1", "A", "T2"), folha_atrasada="desfixar",
                             rotulos=DO_MOTOROLA)
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: o vídeo que viraliza já estava fixado; "
                                                     "comentei nele")
    assert app.fixados == ["T1", "A", "T2"] and "Desafixar" not in app.toques and "Afixar" not in app.toques
    assert app.abertos == ["A", "T1", "A"]
    assert _registro() == [("já fixado", "conferido nos fixados do Perfil")]
    assert comentarios["chamadas"] == [{"aberto": "A", "tela": "player", "onde": robo.ONDE_DO_FIXADO, "produto": "",
                                        "titulo": "Legenda do A"}]
    assert avisos == [_aviso_do_comentario(1, "A")]


def test_video_sem_a_legenda_no_player_para_sem_tirar_nenhum_fixado(avisos, comentarios):
    # Sem a legenda do vídeo que viraliza, a conferência nos fixados não o distingue de nenhum: nenhum sai, e a
    # leitura seguinte tenta de novo (pedido do Rafael, 25/11/2026: conferir antes de tirar).
    app = CelularDasCurtidas(_curtidas("A", 11) + [TOPO], sem_legenda=("lista",))
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: parou (sem a legenda do vídeo para conferir "
                                                     "nos fixados)")
    assert app.fixados == ["T1", "T2", "T3"] and "Desfixar" not in app.toques and "Fixar" not in app.toques
    assert _registro() == [("parou", "sem a legenda do vídeo para conferir nos fixados")]
    assert avisos == [] and comentarios["chamadas"] == []


def test_video_que_so_se_mostra_fixado_depois_do_desfixar_devolve_o_que_saiu(avisos, comentarios, monkeypatch):
    # Se a conferência nos fixados não achar o vídeo (aqui, o player aberto pela grade sem a legenda) e ele só se
    # mostrar fixado depois do Desafixar de outro, ele já estava fixado e a troca não devia ter acontecido: o que saiu
    # volta aos fixados, aberto pelo link copiado antes do Desafixar, nenhum aviso diz que fixou, e o vídeo que viraliza
    # só ganha o comentário, aberto pelo link dele (P263 1).
    abertos = _abrir_pelo_link(monkeypatch)
    app = CelularDasCurtidas(_curtidas("A", 11) + [TOPO], fixados=("T1", "A", "T2"), folha_atrasada="desfixar",
                             rotulos=DO_MOTOROLA, sem_legenda=("perfil",))
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: o vídeo que viraliza já estava fixado; "
                                                     "comentei nele")
    assert sorted(app.fixados) == ["A", "T1", "T2"] and app.toques.count("Afixar") == 1
    assert _registro() == [("desfixado", "o de menos visualizações"),
                           ("já fixado", "depois do desfixar; o desfixado voltou")]
    assert avisos == [_aviso_do_comentario(1, "A")]
    assert abertos == ["https://s.shopee.com.br/T2", "https://s.shopee.com.br/A"]


def test_desfixado_que_nao_volta_vai_ao_rafael_com_o_link(avisos, comentarios, monkeypatch):
    # Sem conseguir fixar de novo o que tirou (aqui, o app no limite dos fixados), o Rafael recebe o link dele.
    _abrir_pelo_link(monkeypatch)
    app = CelularDasCurtidas(_curtidas("A", 11) + [TOPO], fixados=("T1", "A", "T2"), folha_atrasada="desfixar",
                             rotulos=DO_MOTOROLA, limite=2, sem_legenda=("perfil",))
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: o vídeo que viraliza já estava fixado; "
                                                     "comentei nele")
    assert app.fixados == ["T1", "A"]
    assert _registro() == [("desfixado", "o de menos visualizações"),
                           ("já fixado", "depois do desfixar; o desfixado não voltou")]
    assert avisos[0] == ("⚠️ Robô da Shopee Vídeo: tirei dos fixados do seu Perfil o vídeo de menos visualizações para "
                         "dar lugar ao que está viralizando, mas ele já estava fixado, e não consegui fixar de novo o "
                         "que tirei. Se quiser, fixe-o à mão, para o Perfil voltar a ter os 3 fixados.\n\n📤 Saiu: "
                         "https://s.shopee.com.br/T2")


def test_volta_que_para_na_verificacao_depois_do_ja_fixado_avisa_com_o_link(avisos, comentarios, monkeypatch):
    # Também no vídeo que só se mostrou fixado depois do Desafixar: a volta que para na Verificação avisa o link do que
    # saiu, sem o comentário.
    _verificacao_ao_abrir_pelo_link(monkeypatch)
    app = CelularDasCurtidas(_curtidas("A", 11) + [TOPO], fixados=("T1", "A", "T2"), folha_atrasada="desfixar",
                             rotulos=DO_MOTOROLA, sem_legenda=("perfil",))
    _leitura(app)
    with pytest.raises(robo.Verificacao):
        robo.fixar_o_que_viraliza(app, AGORA)
    assert app.fixados == ["T1", "A"] and comentarios["chamadas"] == []
    assert avisos == ["⚠️ Robô da Shopee Vídeo: tirei dos fixados do seu Perfil o vídeo de menos visualizações para "
                      "dar lugar ao que está viralizando, mas ele já estava fixado, e não consegui fixar de novo o "
                      "que tirei. Se quiser, fixe-o à mão, para o Perfil voltar a ter os 3 fixados.\n\n📤 Saiu: "
                      "https://s.shopee.com.br/T2"]


def test_aviso_do_limite_de_fixados_no_motorola_para_sem_mais_toques(avisos):
    app = CelularDasCurtidas(_curtidas("A", 10) + [TOPO], fixados=("T1", "T3"), limite=2, rotulos=DO_MOTOROLA)
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: parou (o app disse que o limite de fixados "
                                                     "acabou)")
    assert app.fixados == ["T1", "T3"] and not avisos


def test_as_curtidas_de_antes_do_topo_nao_contam_de_novo(avisos):
    app = CelularDasCurtidas(_curtidas("A", 6) + [TOPO] + _curtidas("A", 6, desde=8))
    _leitura(app)
    # Só as 6 de cima do topo entram; as de baixo dele já entraram na leitura anterior.
    assert it.videos_mais_curtidos(AGORA)[0]["curtidas"] == 6


def test_mesmo_video_pela_legenda_cortada_em_lugares_diferentes():
    assert robo._mesmo_video("Poltrona giratória estofada com couro ... Veja mais",
                             "Poltrona giratória estofada com... Veja mais")
    assert not robo._mesmo_video("Poltrona giratória estofada com couro", "Copo térmico que gela o dia todo")
    assert robo._mesmo_video("", "") and not robo._mesmo_video("Poltrona giratória estofada", "")


def _abrir_pelo_link(monkeypatch):
    """O link do vídeo (o copiado no fixar) abre o player dele, como o link do post."""
    abertos = []

    def abrir(d, link):
        abertos.append(link)
        d.__dict__.update(atual="player", aberto=link.rsplit("/", 1)[1], de_onde="inicio")

    monkeypatch.setattr(robo.ps, "abrir_link", abrir)
    return abertos


def test_comentario_que_para_no_fixado_volta_na_leitura_seguinte_pelo_link(avisos, comentarios, monkeypatch):
    abertos = _abrir_pelo_link(monkeypatch)
    comentarios["falhas"].append("o painel de comentários do vídeo do post não abriu")
    app = CelularDasCurtidas(_curtidas("A", 10) + [TOPO], fixados=("T1", "T3"))
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == (
        "fixar no perfil: fixei o vídeo que viraliza; o comentário nele parou (o painel de comentários do vídeo do "
        "post não abriu), e volta na próxima leitura")
    # O Fixar ficou; o comentário parou sem nada no privado além do aviso do Fixar, e o caso fica para o Claude.
    assert app.fixados == ["A", "T1", "T3"] and len(avisos) == 1
    assert comentarios["casos"] == [("fixar", "parou", "comentar no vídeo fixado: o painel de comentários do vídeo "
                                                       "do post não abriu")]
    assert robo.comentario_do_fixado_pendente(AGORA)["tentativas"] == 1
    # Na leitura seguinte, o vídeo abre pelo link copiado no fixar, e o comentário sai.
    depois = AGORA + timedelta(hours=3)
    robo.contar_leitura(depois)
    assert robo.fixar_o_que_viraliza(app, depois) == "fixar no perfil: vídeo fixado antes: comentei nele"
    assert abertos == ["https://s.shopee.com.br/A"]
    assert [c["aberto"] for c in comentarios["chamadas"]] == ["A", "A"]
    assert avisos[1:] == [_aviso_do_comentario(2, "A")]
    assert _registro(robo.PROCESSO_DO_COMENTARIO_FIXADO) == [
        ("parou", "o painel de comentários do vídeo do post não abriu"), ("comentado", "")]
    assert robo.comentario_do_fixado_pendente(depois) is None


def test_comentario_que_nao_sai_em_3_tentativas_vai_ao_rafael_com_o_link(avisos, comentarios, monkeypatch):
    _abrir_pelo_link(monkeypatch)
    comentarios["falhas"].extend(["a IA não escreveu o comentário do post"] * 3)
    app = CelularDasCurtidas(_curtidas("A", 10) + [TOPO], fixados=("T1", "T3"))
    _leitura(app)
    robo.fixar_o_que_viraliza(app, AGORA)
    robo.contar_leitura(AGORA + timedelta(hours=3))
    assert robo.fixar_o_que_viraliza(app, AGORA + timedelta(hours=3)) == (
        "fixar no perfil: vídeo fixado antes: o comentário nele parou (a IA não escreveu o comentário do post), e "
        "volta na próxima leitura")
    robo.contar_leitura(AGORA + timedelta(hours=6))
    assert robo.fixar_o_que_viraliza(app, AGORA + timedelta(hours=6)) == (
        "fixar no perfil: vídeo fixado antes: o comentário nele parou (a IA não escreveu o comentário do post), na "
        "última tentativa")
    assert avisos[-1] == ("⚠️ Robô da Shopee Vídeo: não consegui comentar no vídeo que fixei no seu Perfil (a IA não "
                          "escreveu o comentário do post), em 3 tentativas. Se quiser, comente à mão.\n\n🔗 "
                          "https://s.shopee.com.br/A")
    assert [r for r, _d in _registro(robo.PROCESSO_DO_COMENTARIO_FIXADO)] == ["parou", "parou", "parou", "desistiu"]
    # Depois da última, nada volta.
    robo.contar_leitura(AGORA + timedelta(hours=9))
    assert robo.fixar_o_que_viraliza(app, AGORA + timedelta(hours=9)) == ""
    assert len(comentarios["chamadas"]) == 3


def test_video_fixado_ja_comentado_nao_ganha_outro_comentario_por_7_dias(comentarios):
    app = CelularDasCurtidas([], fixados=("A", "T1", "T3"))
    app.atual, app.aberto = "player", "A"
    marca = vz.marca_da_miniatura(_desenho("A"), (0, 0, 105, 105))
    robo._anotar_o_comentario_do_fixado(marca, "https://s.shopee.com.br/A", "comentado", AGORA)
    assert robo._comentar_no_fixado(app, marca, "https://s.shopee.com.br/A", AGORA + timedelta(days=2)) == (
        "já tinha comentado nele")
    assert not comentarios["chamadas"]
    assert _registro(robo.PROCESSO_DO_COMENTARIO_FIXADO) == [("já comentado", "há menos de 7 dias")]
    # Passados os 7 dias (como no post antigo), o vídeo fixado de novo ganha outro comentário.
    assert robo._comentar_no_fixado(app, marca, "https://s.shopee.com.br/A", AGORA + timedelta(days=8)) == (
        "comentei nele")
    assert len(comentarios["chamadas"]) == 1


def test_pedido_de_uma_vez_comenta_no_1o_fixado_do_perfil(avisos, comentarios, monkeypatch):
    # Pedido do Rafael (21/11): o vídeo que ele fixou à mão em 20/11 (o 1º fixado da grade) ganha o comentário uma vez.
    monkeypatch.setattr(robo, "PEDIDOS_DE_COMENTARIO_NO_1O_FIXADO", ("2026-11-21",))
    app = CelularDasCurtidas(_curtidas("B", 2) + [TOPO], fixados=("T1", "T2", "T3"))
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == "fixar no perfil: 1º fixado do Perfil: comentei nele"
    assert app.abertos == ["T1"] and app.fixados == ["T1", "T2", "T3"]
    assert "Desfixar" not in app.toques and "Fixar" not in app.toques
    assert comentarios["chamadas"] == [{"aberto": "T1", "tela": "player", "onde": robo.ONDE_DO_FIXADO,
                                        "produto": "", "titulo": "Legenda do T1"}]
    assert avisos == [_aviso_do_comentario(1, "T1")]
    # Uma vez só: na leitura seguinte, o pedido já foi feito.
    robo.contar_leitura(AGORA + timedelta(hours=3))
    assert robo.fixar_o_que_viraliza(app, AGORA + timedelta(hours=3)) == ""
    assert len(comentarios["chamadas"]) == 1


def test_pedido_do_1o_fixado_sem_fixado_na_grade_tenta_3_vezes(avisos, comentarios, monkeypatch):
    monkeypatch.setattr(robo, "PEDIDOS_DE_COMENTARIO_NO_1O_FIXADO", ("2026-11-21",))
    app = CelularDasCurtidas([TOPO], fixados=())
    _leitura(app)
    for vez in range(4):
        momento = AGORA + timedelta(hours=3 * vez)
        robo.contar_leitura(momento)
        resultado = robo.fixar_o_que_viraliza(app, momento)
        if vez < 3:
            assert resultado == ("fixar no perfil: 1º fixado do Perfil: parou (nenhum vídeo com o selo Fixado na "
                                 "grade do Perfil)")
        else:
            assert resultado == ""
    assert not comentarios["chamadas"] and not avisos and len(comentarios["casos"]) == 3
    assert [r for r, _d in _registro(robo.PROCESSO_DO_COMENTARIO_FIXADO)] == ["parou"] * 3


def test_pedido_do_1o_fixado_no_motorola_com_o_desafixar(avisos, comentarios, monkeypatch):
    # Caso de 21/11 (17:24): o 1º fixado abriu e a folha mostrou o "Desafixar"; o robô agora o reconhece e comenta.
    monkeypatch.setattr(robo, "PEDIDOS_DE_COMENTARIO_NO_1O_FIXADO", ("2026-11-21",))
    app = CelularDasCurtidas(_curtidas("B", 2) + [TOPO], fixados=("T1", "T2", "T3"), rotulos=DO_MOTOROLA)
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == "fixar no perfil: 1º fixado do Perfil: comentei nele"
    assert app.abertos == ["T1"] and app.fixados == ["T1", "T2", "T3"] and "Desafixar" not in app.toques
    assert avisos == [_aviso_do_comentario(1, "T1")]
    assert not comentarios["casos"]


def test_legenda_do_player_vai_a_ia_sem_o_veja_mais():
    assert robo._legenda_sem_o_corte("Poltrona giratória estofada com ... Veja mais") == (
        "Poltrona giratória estofada com")
    assert robo._legenda_sem_o_corte("Copo térmico… Veja mais") == "Copo térmico"
    assert robo._legenda_sem_o_corte("") == ""


def test_registro_do_comentario_no_fixado_tem_o_nome_proprio():
    for onde, nome in ((robo.ONDE_DO_FIXADO, "vídeo fixado: curtir o vídeo"),
                       (robo.ONDE_DO_ANTIGO, "post antigo: curtir o vídeo"),
                       (True, "post antigo: curtir o vídeo"), (False, "próprio post: curtir o vídeo")):
        robo._registrar_no_post(onde, "curtir o vídeo", "curtido", True, AGORA)
        assert robo.registro_processos.sequencia("shopee_video", nome, "2000-01-01 00:00:00")
    assert robo.ACAO_DO_CASO_DO_COMENTARIO[robo._onde_do_comentario(robo.ONDE_DO_FIXADO)] == "fixar"


def test_rodada_das_respostas_fixa_depois_de_responder(monkeypatch):
    feitos = []
    monkeypatch.setattr(robo, "responder_comentarios",
                        lambda d, agora=None: feitos.append("respostas") or "respostas: ok")
    monkeypatch.setattr(robo, "fixar_o_que_viraliza",
                        lambda d, agora=None: feitos.append("fixar") or "fixar no perfil: x")
    resultado = robo._agir(object(), "responder", None, False, dict(robo.PADRAO), AGORA)
    assert resultado == "respostas: ok; fixar no perfil: x"
    assert feitos == ["respostas", "fixar"]


# --- O fixado que sai na troca: o que esfriou (P300 1) ---

# Três capas da grade bem diferentes (32 bits ou mais entre elas).
MARCAS = ("f0f0f0f0f0f0f0f0", "0f0f0f0f0f0f0f0f", "ff00ff00ff00ff00")


def _fixados(*vistas):
    """Os quadros dos fixados na grade, com as visualizações de cada um (None: o número não aparece)."""
    return [{"caixa": (361 * i, 1205, 361 * i + 358, 1681), "fixado": True, "vistas": v} for i, v in enumerate(vistas)]


def _notas(*anotacoes):
    """As anotações dos fixados, gravadas como o robô as guarda: (marca, vistas, quando)."""
    robo.db.salvar_config(robo.CHAVE_DOS_FIXADOS, {"notas": [
        {"marca": marca, "vistas": vistas, "em": robo._momento(quando)} for marca, vistas, quando in anotacoes]})


def test_sai_o_fixado_que_menos_cresceu_e_nao_o_de_menos_visualizacoes(avisos, comentarios, monkeypatch):
    # Resposta do Rafael (25/11/2026, P300 1, com 30 dias): sai o fixado que ganhou menos visualizações por dia, e não o
    # de menos visualizações, que pode ser um vídeo novo começando a crescer (aqui, o T2: 1,2 mil, mas 100 por dia).
    app = CelularDasCurtidas(_curtidas("A", 10) + [TOPO], capas=True)
    # Dez dias antes, a leitura da grade anotou os 3 fixados.
    for video, antes in (("T1", "235,0mil"), ("T2", "200"), ("T3", "250,0mil")):
        monkeypatch.setitem(VISTAS, video, antes)
    robo.anotar_os_fixados(app, AGORA - timedelta(days=10))
    for video, agora in (("T1", "235,2mil"), ("T2", "1,2 mil"), ("T3", "263,8mil")):
        monkeypatch.setitem(VISTAS, video, agora)
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: troquei o fixado que menos cresceu pelo vídeo "
                                                     "que viraliza; comentei nele")
    # O T1 ganhou 200 em 10 dias (20 por dia), o T2 1.000 (100 por dia) e o T3 13.800 (1.380 por dia).
    assert app.fixados == ["A", "T2", "T3"]
    assert app.abertos == ["A", "T1", "T2", "T3", "T1", "A"]
    assert avisos[0] == ("📌 Robô da Shopee Vídeo: fixei no seu Perfil o vídeo que está viralizando (10 curtidas nas "
                         "últimas 24 h, nas Notificações).\n\n📌 Fixado agora: https://s.shopee.com.br/A\n📤 Saiu dos "
                         "fixados (o que menos cresceu: 20 visualizações por dia em 10 dias; 235.200 no total): "
                         "https://s.shopee.com.br/T1")
    assert _registro() == [("desfixado", "o que menos cresceu"), ("trocado", "no lugar do fixado que menos cresceu")]
    # O A, que entrou, começa a contar o dia dele logo depois do Fixar, e o T1, que saiu, perde as anotações: fixado de
    # novo, ele conta do zero, como o recém-fixado.
    notas = robo._notas_dos_fixados(AGORA)
    assert [n["vistas"] for n in notas] == [200, 250000, 1200, 263800, 240100]
    assert [n["em"] == robo._momento(AGORA) for n in notas] == [False, False, True, True, True]
    marca_do_t1 = vz.marca_da_capa(_capa_na_grade("T1"), (0, 0, 358, 476))
    assert not any(vz.diferenca(n["marca"], marca_do_t1) <= vz.MARCA_PARECIDA for n in notas)
    assert [r for r, _d in _registro(robo.PROCESSO_DOS_FIXADOS)] == ["anotados"] * 3


def test_o_recem_fixado_fica_e_sai_o_que_menos_cresceu_entre_os_outros():
    # P300 1: o fixado com menos de 1 dia de anotação (o recém-fixado) não sai, mesmo com menos visualizações; entre
    # os outros, sai o que ganhou menos por dia (o 2º: 300 em 10 dias), e não o de menos visualizações (o 1º).
    dez_dias = AGORA - timedelta(days=10)
    _notas((MARCAS[0], 230000, dez_dias), (MARCAS[1], 263500, dez_dias), (MARCAS[2], 900, AGORA - timedelta(hours=5)))
    fixados = _fixados(235200, 263800, 1000)
    alvo, ritmo, porque = robo._o_que_esfriou(fixados, list(MARCAS), AGORA)
    assert alvo is fixados[1] and ritmo == {"ritmo": 30, "dias": 10} and porque == "o que menos cresceu"


def test_so_contam_as_anotacoes_dos_ultimos_30_dias():
    # Resposta do Rafael (25/11/2026): o crescimento dos últimos 30 dias. Com as anotações de 40 dias atrás, sairia o 2º
    # (800 em 40 dias); nos 30 dias, quem menos cresceu foi o 1º (100 em 2 dias).
    quarenta, dois = AGORA - timedelta(days=40), AGORA - timedelta(days=2)
    _notas((MARCAS[0], 0, quarenta), (MARCAS[1], 263000, quarenta), (MARCAS[2], 200000, quarenta),
           (MARCAS[0], 235100, dois), (MARCAS[1], 263000, dois), (MARCAS[2], 263500, dois))
    fixados = _fixados(235200, 263800, 263800)
    alvo, ritmo, _porque = robo._o_que_esfriou(fixados, list(MARCAS), AGORA)
    assert alvo is fixados[0] and ritmo == {"ritmo": 50, "dias": 2}


def test_no_empate_sai_o_de_menos_curtidas_no_coracao():
    # P300 1: as curtidas desempatam (as do coração de cada fixado, lidas quando o robô os abre para conferir).
    cinco_dias = AGORA - timedelta(days=5)
    _notas(*[(marca, vistas, cinco_dias) for marca, vistas in zip(MARCAS, (235200, 263800, 50000))])
    fixados = _fixados(235200, 263800, 50000)
    # Nenhum cresceu: o empate em 0 por dia.
    alvo, ritmo, porque = robo._o_que_esfriou(fixados, list(MARCAS), AGORA, curtidas=[40, 12, 30])
    assert alvo is fixados[1] and ritmo == {"ritmo": 0, "dias": 5}
    assert porque == "o que menos cresceu; no empate, o de menos curtidas"
    # Sem o número do coração de um dos empatados, sai o de menos visualizações entre eles.
    alvo, _ritmo, porque = robo._o_que_esfriou(fixados, list(MARCAS), AGORA, curtidas=[40, None, 30])
    assert alvo is fixados[2] and porque == "o que menos cresceu"


def test_sem_1_dia_de_anotacoes_sai_o_de_menos_visualizacoes_menos_o_fixado_depois():
    # Nos primeiros dias das anotações, nenhum fixado tem 1 dia delas: sai o de menos visualizações, como antes, menos o
    # que apareceu nos fixados depois dos outros (o recém-fixado, que não sai).
    seis_horas = AGORA - timedelta(hours=6)
    _notas((MARCAS[0], 235000, seis_horas), (MARCAS[1], 263000, seis_horas),
           (MARCAS[2], 900, AGORA - timedelta(hours=2)))
    fixados = _fixados(235200, 263800, 1000)
    alvo, ritmo, porque = robo._o_que_esfriou(fixados, list(MARCAS), AGORA)
    assert alvo is fixados[0] and ritmo is None and porque == "o de menos visualizações"
    # Sem as capas (nenhuma marca), o de menos visualizações de todos.
    assert robo._o_que_esfriou(fixados, [None] * 3, AGORA)[0] is fixados[2]
    # Sem o número de nenhum na grade, nenhum.
    assert robo._o_que_esfriou(_fixados(None, None), [None, None], AGORA) == (None, None, "")


def test_anotacoes_dos_fixados_uma_por_dia_e_so_os_ultimos_30_dias():
    _notas((MARCAS[0], 100, AGORA - timedelta(days=31)))
    robo._guardar_os_fixados(_fixados(235200, 263800, None), list(MARCAS), AGORA)
    # A mesma capa (ou uma parecida) no mesmo dia não entra de novo; a de 31 dias saiu.
    parecida = f"{int(MARCAS[0], 16) ^ 0b111:016x}"
    robo._guardar_os_fixados(_fixados(235300, 263900), [parecida, None], AGORA + timedelta(hours=3))
    notas = robo.db.ler_config(robo.CHAVE_DOS_FIXADOS, {})["notas"]
    assert [(n["marca"], n["vistas"]) for n in notas] == [(MARCAS[0], 235200), (MARCAS[1], 263800)]
    assert _registro(robo.PROCESSO_DOS_FIXADOS) == [("anotados", "2 nova(s); 2 de 3 fixado(s) com a capa e o número"),
                                                     ("anotados", "0 nova(s); 1 de 2 fixado(s) com a capa e o número")]
    # No dia seguinte, entram de novo.
    robo._guardar_os_fixados(_fixados(236000, 264000), list(MARCAS[:2]), AGORA + timedelta(days=1))
    assert len(robo.db.ler_config(robo.CHAVE_DOS_FIXADOS, {})["notas"]) == 4
    # O 1º saiu dos fixados e entrou outro. Na leitura dos 3 fixados com a capa de todos, o que não está mais entre
    # eles perde as anotações: fixado de novo, ele conta do zero, como o recém-fixado. Sem a capa de algum (ou com
    # menos de 3 na tela, um deles cortado), nenhuma sai.
    outro = "00ff00ff00ff00ff"
    robo._guardar_os_fixados(_fixados(264100, 900, 50), [MARCAS[1], MARCAS[2], None], AGORA + timedelta(days=2))
    assert len(robo.db.ler_config(robo.CHAVE_DOS_FIXADOS, {})["notas"]) == 6
    robo._guardar_os_fixados(_fixados(264200, 1000, 60), [MARCAS[1], MARCAS[2], outro], AGORA + timedelta(days=3))
    notas = robo.db.ler_config(robo.CHAVE_DOS_FIXADOS, {})["notas"]
    assert sorted((n["marca"], n["vistas"]) for n in notas) == sorted(
        [(MARCAS[1], v) for v in (263800, 264000, 264100, 264200)] + [(MARCAS[2], 900), (MARCAS[2], 1000), (outro, 60)])

# --- O lugar vazio entre os fixados (P299 1) ---

def test_lugar_vazio_recebe_o_mais_curtido_em_24_h_mesmo_com_menos_de_10(avisos, comentarios):
    # Resposta do Rafael (25/11/2026, P299 1): com um lugar vazio entre os 3 fixados, entra o vídeo dele com mais
    # curtidas nas últimas 24 h que não está fixado, mesmo com menos de 10, com o aviso e o comentário, como no fixar.
    app = CelularDasCurtidas(_curtidas("A", 6) + _curtidas("B", 2, desde=8) + [TOPO], fixados=("T1", "T3"))
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: fixei no lugar vazio o mais curtido em 24 h; "
                                                     "comentei nele")
    assert app.fixados == ["A", "T1", "T3"] and "Desfixar" not in app.toques
    assert app.abertos == ["A", "T1", "T3", "A"]
    assert avisos == ["📌 Robô da Shopee Vídeo: havia um lugar vazio entre os 3 fixados do seu Perfil, e fixei nele o "
                      "seu vídeo com mais curtidas nas últimas 24 h que não estava fixado (6 curtidas nas "
                      "Notificações, menos de 10).\n\n📌 Fixado agora: https://s.shopee.com.br/A",
                      _aviso_do_comentario(1, "A")]
    assert _registro() == [("nenhum vídeo para fixar", "o mais curtido com 6 em 24 h"),
                           ("fixado", "no lugar vazio: o mais curtido em 24 h")]
    # Um por leitura.
    assert robo.fixar_o_que_viraliza(app, AGORA) == ""


def test_lugar_vazio_com_o_mais_curtido_ja_fixado_recebe_o_seguinte(avisos, comentarios):
    # O mais curtido do dia já é um dos fixados: fica como está, sem o comentário (o do já fixado é do vídeo que
    # viraliza, pedido de 21/11/2026), e o seguinte entra no lugar vazio.
    app = CelularDasCurtidas(_curtidas("A", 5) + _curtidas("B", 3, desde=8) + [TOPO], fixados=("T1", "A"))
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: fixei no lugar vazio o mais curtido em 24 h; "
                                                     "comentei nele")
    assert app.fixados == ["B", "T1", "A"]
    assert [c["aberto"] for c in comentarios["chamadas"]] == ["B"]
    assert "(3 curtidas nas Notificações, menos de 10)" in avisos[0]
    assert _registro() == [("nenhum vídeo para fixar", "o mais curtido com 5 em 24 h"), ("já fixado", "no lugar vazio"),
                           ("fixado", "no lugar vazio: o mais curtido em 24 h")]


class CelularComFixadoAMao(CelularDasCurtidas):
    """O Rafael fixa o T2 à mão logo depois de o robô abrir pelas Notificações o vídeo das curtidas."""

    def _abrir(self, de_onde):
        super()._abrir(de_onde)
        if de_onde == "lista" and "T2" not in self.fixados:
            self.fixados.insert(0, "T2")


def test_lugar_vazio_ocupado_no_meio_da_leitura_nao_tira_nenhum_fixado(avisos, comentarios):
    app = CelularComFixadoAMao(_curtidas("A", 6) + [TOPO], fixados=("T1", "T3"))
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: o lugar vazio entre os fixados foi ocupado no "
                                                     "meio da leitura")
    assert app.fixados == ["T2", "T1", "T3"] and not {"Fixar", "Desfixar"} & set(app.toques)
    assert not avisos and not comentarios["chamadas"]
    assert _registro()[-1] == ("lugar ocupado", "no meio da leitura")


def test_lugar_vazio_sem_curtida_fixa_de_novo_o_ultimo_que_o_robo_tirou(avisos, comentarios, monkeypatch):
    # P299 1: sem curtida nenhuma nas últimas 24 h, volta o último vídeo que o robô tirou dos fixados, aberto pelo link
    # copiado antes do Desafixar, com o aviso e o comentário.
    abertos = _abrir_pelo_link(monkeypatch)
    robo._anotar_o_tirado("https://s.shopee.com.br/T2", MARCAS[1], AGORA - timedelta(days=1))
    app = CelularDasCurtidas([TOPO], fixados=("T1", "T3"))
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: fixei de novo, no lugar vazio, o último que eu "
                                                     "tinha tirado; comentei nele")
    assert app.fixados == ["T2", "T1", "T3"] and abertos == ["https://s.shopee.com.br/T2"]
    assert avisos == ["📌 Robô da Shopee Vídeo: o seu Perfil estava com 2 de 3 fixados, e nenhum vídeo seu com "
                      "curtidas nas últimas 24 h ficou para o lugar vazio: fixei de novo o último vídeo que eu tinha "
                      "tirado dos fixados (tirado em 20/11).\n\n📌 Fixado agora: https://s.shopee.com.br/T2",
                      _aviso_do_comentario(1, "T2")]
    assert _registro() == [("nenhum vídeo para fixar", "o mais curtido com 0 em 24 h"),
                           ("fixado", "no lugar vazio: o último que o robô tirou")]
    assert robo._o_tirado() is None


def test_o_que_saiu_na_troca_volta_quando_um_fixado_sai_a_mao_e_ninguem_mais_curtiu(avisos, comentarios, monkeypatch):
    # A troca guarda o que saiu (o T2); o Rafael tira o T3 à mão; na leitura seguinte, com as curtidas só no A (fixado
    # pelo robô, fora da conta por 24 h), o T2 volta ao lugar vazio.
    abertos = _abrir_pelo_link(monkeypatch)
    app = CelularDasCurtidas(_curtidas("A", 10) + [TOPO])
    _leitura(app)
    robo.fixar_o_que_viraliza(app, AGORA)
    assert app.fixados == ["A", "T1", "T3"]
    app.fixados.remove("T3")
    depois = AGORA + timedelta(hours=3)
    robo.contar_leitura(depois)
    assert robo.fixar_o_que_viraliza(app, depois).startswith("fixar no perfil: fixei de novo, no lugar vazio, ")
    assert app.fixados == ["T2", "A", "T1"] and abertos == ["https://s.shopee.com.br/T2"]
    assert _registro()[-2:] == [("nenhum vídeo para fixar", "o mais curtido com 10 em 24 h, já visto"),
                                ("fixado", "no lugar vazio: o último que o robô tirou")]


def test_lugar_vazio_com_curtidas_so_nos_fixados_fixa_de_novo_o_ultimo_tirado(avisos, comentarios, monkeypatch):
    # Com curtidas só nos vídeos que já estão fixados, nenhum curtido fica para o lugar vazio: volta o último tirado,
    # mesmo tirado há mais tempo.
    abertos = _abrir_pelo_link(monkeypatch)
    robo._anotar_o_tirado("https://s.shopee.com.br/T2", None, AGORA - timedelta(days=40))
    app = CelularDasCurtidas(_curtidas("A", 4) + [TOPO], fixados=("T1", "A"))
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA).startswith("fixar no perfil: fixei de novo, no lugar vazio, ")
    assert app.fixados == ["T2", "T1", "A"] and abertos == ["https://s.shopee.com.br/T2"]
    assert _registro()[1:] == [("já fixado", "no lugar vazio"), ("fixado", "no lugar vazio: o último que o robô tirou")]
    assert [c["aberto"] for c in comentarios["chamadas"]] == ["T2"]


def test_ultimo_tirado_que_ja_voltou_aos_fixados_sai_do_estado(avisos, monkeypatch):
    _abrir_pelo_link(monkeypatch)
    robo._anotar_o_tirado("https://s.shopee.com.br/T2", None, AGORA - timedelta(days=1))
    app = CelularDasCurtidas([TOPO], fixados=("T1", "T2"))
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ""
    assert app.fixados == ["T1", "T2"] and not avisos and robo._o_tirado() is None
    assert _registro()[-1] == ("já fixado", "o último tirado pelo robô")


def test_ultimo_tirado_que_nao_abre_em_3_leituras_sai(avisos, comentarios, monkeypatch):
    def nao_abre(d, link):
        raise robo.Parada(robo.MOTIVO_DO_POST_REMOVIDO)

    monkeypatch.setattr(robo, "_abrir_o_video_do_post", nao_abre)
    robo._anotar_o_tirado("https://s.shopee.com.br/T2", None, AGORA - timedelta(days=1))
    app = CelularDasCurtidas([TOPO], fixados=("T1", "T3"))
    _leitura(app)
    for leitura in range(robo.TENTATIVAS_DO_TIRADO):
        momento = AGORA + timedelta(hours=3 * leitura)
        if leitura:
            robo.contar_leitura(momento)
        assert robo.fixar_o_que_viraliza(app, momento) == "fixar no perfil: parou (o vídeo do post foi removido)"
    assert robo._o_tirado() is None and len(comentarios["casos"]) == robo.TENTATIVAS_DO_TIRADO
    # Sem o tirado, o lugar fica vazio, e o registro diz por quê.
    robo.contar_leitura(AGORA + timedelta(hours=9))
    assert robo.fixar_o_que_viraliza(app, AGORA + timedelta(hours=9)) == ""
    assert _registro()[-1] == ("lugar vazio", "sem vídeo curtido para fixar e sem vídeo tirado pelo robô")
    assert app.fixados == ["T1", "T3"] and not avisos


def test_ultimo_tirado_que_para_no_fixar_em_3_leituras_sai(avisos, monkeypatch):
    # Também o que abre, mas não fica fixado (aqui, o app no limite dos fixados): na 3ª leitura, ele é esquecido.
    _abrir_pelo_link(monkeypatch)
    robo._anotar_o_tirado("https://s.shopee.com.br/T2", None, AGORA - timedelta(days=1))
    app = CelularDasCurtidas([TOPO], fixados=("T1", "T3"), limite=2)
    _leitura(app)
    for leitura in range(robo.TENTATIVAS_DO_TIRADO):
        momento = AGORA + timedelta(hours=3 * leitura)
        if leitura:
            robo.contar_leitura(momento)
        assert robo.fixar_o_que_viraliza(app, momento) == ("fixar no perfil: parou (o app disse que o limite de "
                                                           "fixados acabou)")
        assert (robo._o_tirado() is None) == (leitura == robo.TENTATIVAS_DO_TIRADO - 1)
    assert app.fixados == ["T1", "T3"] and not avisos


def test_ultimo_tirado_sem_o_link_nao_e_guardado():
    robo._anotar_o_tirado("https://s.shopee.com.br/T3", MARCAS[0], AGORA)
    # Sem o link (o Copiar link não saiu), não há como abrir: fica o de antes.
    robo._anotar_o_tirado("", MARCAS[1], AGORA + timedelta(hours=1))
    assert robo._o_tirado() == {"link": "https://s.shopee.com.br/T3", "marca": MARCAS[0], "em": robo._momento(AGORA),
                                "falhas": 0}

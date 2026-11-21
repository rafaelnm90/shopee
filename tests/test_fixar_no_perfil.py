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


def _folha(fixado):
    nos = [_el("Link copiado", desc="title of share panel", caixa=(434, 1738, 646, 1789)),
           _el("WhatsApp", caixa=(60, 2010, 180, 2050))]
    for i, rotulo in enumerate(FOLHA + ["Desfixar" if fixado else "Fixar"]):
        nos.append(_el(rotulo, caixa=(65 + 250 * i, 2234, 190 + 250 * i, 2269)))
    return _xml(*nos)


def test_folha_do_compartilhar_nunca_confunde_o_fixar_com_o_desfixar():
    assert it.estado_do_fixar(_folha(fixado=False)) == "fixar"
    assert it.estado_do_fixar(_folha(fixado=True)) == "desfixar"
    assert it.estado_do_fixar(_xml(_el("Copiar link", caixa=(299, 2234, 421, 2269)))) is None
    # O ps.achar pega "contendo" e cairia no Desfixar; o texto exato, não.
    assert ps.achar(_folha(fixado=True), "Fixar") is not None
    assert it.texto_exato(_folha(fixado=True), "Fixar") is None


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
VISTAS = {"T1": "235,2mil", "T2": "1,2 mil", "T3": "263,8mil", "N1": "50", "N2": "70"}


class CelularDasCurtidas:
    """
    A Shopee do Rafael nas telas da P263 1: a lista das Notificações (linhas de curtida, a lista rola de 6 em 6), o
    vídeo aberto (pela curtida ou pela grade), a folha do compartilhar e a grade do Perfil. curtidas: [(texto, hora,
    vídeo, capa à direita)]; fixados: os vídeos fixados, na ordem da grade; no_coracao: as curtidas que o coração de
    cada vídeo mostra. Depois do Copiar link a folha fecha. some_depois: o vídeo cujas curtidas saem da lista depois
    da 1ª vez que ele abre.
    """

    def __init__(self, curtidas, fixados=("T1", "T2", "T3"), no_coracao=None, some_depois=None, limite=3):
        self.curtidas, self.fixados = list(curtidas), list(fixados)
        self.no_coracao = no_coracao or {}
        self.some_depois, self.limite = some_depois, limite
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
            return _player(f"Legenda do {self.aberto}", self.no_coracao.get(self.aberto, 57))
        if self.atual == "folha":
            return _folha(self.aberto in self.fixados)
        if self.atual == "limite":
            return _xml(_el("Você só pode fixar até 3 vídeos", caixa=(200, 1100, 880, 1180)), *BARRA)
        if self.atual == "perfil":
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
            elif "Desfixar" in textos:
                self.fixados.remove(self.aberto)
                self.atual = "player"
            elif "Fixar" in textos:
                if len(self.fixados) >= self.limite:
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
    # O de menos visualizações (o T2, com 1,2 mil) saiu, e o A entrou no topo dos fixados.
    assert app.fixados == ["A", "T1", "T3"]
    assert app.abertos == ["A", "T2", "A"]
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


def test_fixar_que_para_depois_do_desfixar_avisa_com_os_dois_links(avisos):
    app = CelularDasCurtidas(_curtidas("A", 10) + [TOPO], some_depois="A")
    _leitura(app)
    assert robo.fixar_o_que_viraliza(app, AGORA) == ("fixar no perfil: parou (a curtida do vídeo não está mais nas "
                                                     "Notificações)")
    assert app.fixados == ["T1", "T3"]
    assert avisos == ["⚠️ Robô da Shopee Vídeo: tirei dos fixados do seu Perfil o vídeo de menos visualizações, para "
                      "dar lugar ao que está viralizando (10 curtidas nas últimas 24 h), mas não consegui fixar o "
                      "novo (a curtida do vídeo não está mais nas Notificações). Tento de novo na próxima leitura das "
                      "Notificações.\n\n📤 Saiu: https://s.shopee.com.br/T2\n📌 O que ia entrar: "
                      "https://s.shopee.com.br/A"]
    assert _registro() == [("desfixado", "o de menos visualizações"),
                           ("parou", "a curtida do vídeo não está mais nas Notificações")]


def test_aviso_do_limite_de_fixados_para_sem_mais_toques(avisos):
    app = CelularDasCurtidas(_curtidas("A", 10) + [TOPO], fixados=("T1", "T3"), limite=2)
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

"""Respostas aos comentários e interação no feed da Shopee Vídeo (interacoes_shopee_video e o robô)."""
import asyncio
from datetime import datetime
from xml.sax.saxutils import escape

import pytest

import interacoes_shopee_video as it
import robo_shopee_video as robo
from conftest import inserir
from fuso import fuso_horario


def momento(texto):
    return datetime.strptime(texto, "%Y-%m-%d %H:%M").replace(tzinfo=fuso_horario)


def _el(texto="", desc="", ident="", classe="TextView", caixa=(0, 0, 10, 10), clicavel=False):
    x1, y1, x2, y2 = caixa
    atributos = (f'text="{escape(texto, {chr(34): "&quot;"})}" content-desc="{escape(desc, {chr(34): "&quot;"})}" '
                 f'class="android.widget.{classe}" clickable="{"true" if clicavel else "false"}" package="com.shopee.br"')
    if ident:
        atributos += f' resource-id="com.shopee.br:id/{ident}"'
    return f'<node {atributos} bounds="[{x1},{y1}][{x2},{y2}]"/>'


def _xml(*nos):
    return f'<hierarchy><node class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">{"".join(nos)}</node></hierarchy>'


BARRA = [_el("Live e Vídeo", ident="title", caixa=(430, 2350, 650, 2400), clicavel=True),
         _el("Notificações", ident="title", caixa=(650, 2350, 860, 2400), clicavel=True),
         _el("Eu", ident="title", caixa=(870, 2350, 1080, 2400), clicavel=True),
         _el(ident="sp_bottom_navigation_container", classe="FrameLayout", caixa=(0, 2255, 1080, 2400))]
FILTRO = _el("Lives, Vídeos e Afiliados", caixa=(440, 470, 640, 510), clicavel=True)


def _notificacoes(*linhas, y=600):
    """A lista das Notificações como no Motorola: cada linha com o aviso e a hora embaixo."""
    nos = [_el("Notificações", caixa=(400, 160, 680, 220)), FILTRO]
    for texto in linhas:
        nos += [_el(texto, caixa=(160, y, 1040, y + 60)), _el("Hoje 10:15", caixa=(160, y + 70, 400, y + 100))]
        y += 190
    return _xml(*(nos + BARRA))


def _comentario(nome, texto, y, resposta=False, criador=False, ver=""):
    """Um comentário do painel: foto, nome (e o selo), texto, coração, data, Responder."""
    x = 178 if resposta else 84
    nos = [_el(desc="avatar comment item", classe="ImageView", caixa=(x - 40, y - 40, x + 40, y + 40)),
           _el(nome, caixa=(x + 80, y - 30, x + 400, y + 10))]
    if criador:
        nos.append(_el("Criador", caixa=(x + 420, y - 30, x + 520, y + 10)))
    nos += [_el(texto, caixa=(x + 80, y + 30, 1000, y + 80)),
            _el(desc="button comment like", classe="ViewGroup", caixa=(990, y, 1040, y + 50), clicavel=True),
            _el("há 2 horas", caixa=(x + 80, y + 100, x + 250, y + 140)),
            _el("Responder", caixa=(x + 280, y + 100, x + 420, y + 140))]
    if ver:
        nos.append(_el(ver, caixa=(x + 80, y + 150, x + 400, y + 190)))
    return nos


def _painel(*comentarios, campo=None):
    """O painel de comentários: o cartão do produto, o título e, embaixo, emojis e o campo."""
    nos = [_el("Vestido Infantil Gatinho Estampado", caixa=(150, 700, 700, 760)), _el("com cupom", caixa=(300, 760, 400, 790)),
           _el("4 Comentários", desc="comments", caixa=(400, 860, 680, 920))]
    for c in comentarios:
        nos += c
    nos += [_el("..", caixa=(40 + 134 * k, 2170, 100 + 134 * k, 2220)) for k in range(8)]
    if campo is None:
        nos += [_el(desc="input add a comment", classe="ViewGroup", caixa=(40, 2290, 930, 2350)),
                _el(desc="send comment", classe="ImageView", caixa=(980, 2290, 1040, 2350))]
    else:
        nos += [_el(campo, desc="input comment", classe="EditText", caixa=(40, 2290, 930, 2350), clicavel=True),
                _el(desc="send comment", classe="ImageView", caixa=(980, 2290, 1040, 2350))]
    return _xml(*nos)


NOTIFICACAO = 'Maria Souza comentou no seu vídeo: "Amei esse vestido, tem tamanho 10?"'


# --- Leitura das telas ---

def test_comentario_da_notificacao_separa_nome_e_texto_e_ignora_os_outros_avisos():
    assert it.comentario_da_notificacao(NOTIFICACAO) == ("Maria Souza", "Amei esse vestido, tem tamanho 10?")
    assert it.comentario_da_notificacao("Ana e mais 2 curtiram seu vídeo.") is None
    assert it.comentario_da_notificacao("Seu vídeo teve mais de 100 visualizações") is None


def test_linhas_das_notificacoes_sem_a_hora_e_sem_o_que_fica_atras_dos_filtros():
    xml = _xml(_el("Notificações", caixa=(400, 160, 680, 220)), FILTRO,
               _el("linha rolada por baixo dos filtros", caixa=(160, 440, 1040, 480)),
               _el(NOTIFICACAO, caixa=(160, 600, 1040, 660)), _el("Hoje 10:15", caixa=(160, 670, 400, 700)),
               _el("Ana curtiu seu vídeo.", caixa=(160, 800, 1040, 860)), _el("24-10 09:02", caixa=(160, 870, 400, 900)),
               _el("linha cortada pela barra", caixa=(160, 2230, 1040, 2290)), *BARRA)
    assert [t["texto"] for t in it.linhas_das_notificacoes(xml, "Lives, Vídeos")] == [NOTIFICACAO, "Ana curtiu seu vídeo."]


def test_painel_separa_comentarios_respostas_e_o_selo_criador():
    xml = _painel(_comentario("Loja Rafa", "Vestido lindo para as meninas ✨ ... mais", 960, criador=True),
                  _comentario("Maria Souza", "Amei esse vestido, tem tamanho 10?", 1250),
                  _comentario("Loja Rafa", "Tem sim!", 1500, resposta=True, criador=True),
                  _comentario("João", "Chegou rápido", 1800))
    painel = it.comentarios_do_painel(xml)
    assert [(c["nome"], c["resposta"], c["criador"]) for c in painel] == [
        ("Loja Rafa", False, True), ("Maria Souza", False, False), ("Loja Rafa", True, True), ("João", False, False)]
    i = it.alvo_no_painel(painel, "Maria Souza", "Amei esse vestido, tem tamanho 10?")
    assert i == 1 and it.do_criador_embaixo(painel, i) == 1 and painel[i]["responder"]
    assert it.do_criador_embaixo(painel, it.alvo_no_painel(painel, "João", "Chegou rápido")) == 0
    assert it.produto_do_painel(xml) == "Vestido Infantil Gatinho Estampado"
    # O emoji lido como ".." na fileira de emojis rápidos não vira comentário.
    assert all(c["texto"] != ".." for c in painel)


def test_comentario_cortado_e_com_emoji_lido_como_pontos_ainda_e_o_mesmo():
    assert it.parecidos("Amei esse vestido, tem tamanho 10? Quero dois ... mais", "Amei esse vestido, tem tamanho 10? Quero dois pra minha filha")
    assert it.parecidos("Lindo .. demais", "Lindo 😍 demais")
    assert not it.parecidos("Lindo", "Feio")
    assert not it.parecidos("A", "Amei")


def test_onde_ficou_a_resposta():
    resposta = "Tem sim! Corre que é sucesso"
    certo = it.comentarios_do_painel(_painel(_comentario("Maria Souza", "Tem tamanho 10?", 1250),
                                             _comentario("Loja Rafa", resposta, 1500, resposta=True, criador=True)))
    assert it.onde_ficou(certo, 0, resposta) == "embaixo"
    errado = it.comentarios_do_painel(_painel(_comentario("Maria Souza", "Tem tamanho 10?", 1250),
                                              _comentario("João", "Chegou rápido", 1500),
                                              _comentario("Loja Rafa", resposta, 1750, resposta=True, criador=True)))
    assert it.onde_ficou(errado, 0, resposta) == "outro lugar"
    assert it.onde_ficou(certo, 0, "outra coisa") is None


def test_texto_da_ia_sem_aspas_sem_emoji_que_a_tela_nao_le_e_no_limite():
    assert it.texto_simples('"Pronta pra arrasar 😍✨!"', 150) == "Pronta pra arrasar ✨!"
    assert len(it.texto_simples("palavra " * 40, 80)) <= 80


def test_ia_que_diz_pular_e_ia_fora(monkeypatch):
    import api_gemini
    respostas = iter(["PULAR", None, None])

    async def gerar(prompt):
        return next(respostas)

    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", gerar)
    assert asyncio.run(it.gerar_resposta("compre no meu site www")) == ""
    assert asyncio.run(it.gerar_comentario("Mini saia")) is None


# As abas do alto do player (Live e Vídeo), como no Motorola.
ABAS = [_el("Vídeos", caixa=(350, 140, 460, 195), clicavel=True), _el("Lives", caixa=(510, 140, 600, 195), clicavel=True),
        _el("Para você", caixa=(660, 140, 810, 195), clicavel=True)]


def _player(autor="Loja da Bia", legenda="Mini saia que veste bem", coracao="like icon", live=False):
    if live:
        return _xml(_el(ident="live_room_in_video_feed_18", classe="FrameLayout", caixa=(0, 0, 1080, 2260)),
                    _el("Diga alguma coisa", ident="tv_send_message", caixa=(200, 2150, 600, 2210), clicavel=True),
                    *ABAS, *BARRA)
    return _xml(_el(ident="rn_vod_player_view_with_surface", classe="FrameLayout", caixa=(0, 0, 1080, 2260)),
                *ABAS,
                _el(desc="video author", classe="ViewGroup", caixa=(40, 2030, 460, 2080), clicavel=True),
                _el(autor, caixa=(40, 2030, 460, 2080)),
                _el(desc="video title", classe="ViewGroup", caixa=(40, 2100, 820, 2160), clicavel=True),
                _el(legenda, caixa=(40, 2100, 820, 2160)),
                _el(desc="avatar icon", classe="ViewGroup", caixa=(960, 1390, 1040, 1470), clicavel=True),
                _el(desc=coracao, classe="ViewGroup", caixa=(960, 1600, 1040, 1680), clicavel=True),
                _el("12", caixa=(980, 1675, 1020, 1700)),
                _el(desc="comment video icon", classe="ViewGroup", caixa=(960, 1770, 1040, 1840), clicavel=True),
                _el(desc="video share icon", classe="ViewGroup", caixa=(960, 1950, 1040, 2010), clicavel=True),
                *BARRA)


def test_feed_live_e_video():
    assert it.eh_live(_player(live=True)) and it.video_do_feed(_player(live=True)) is None
    video = it.video_do_feed(_player())
    assert video["autor"] == "Loja da Bia" and video["legenda"] == "Mini saia que veste bem"
    assert video["coracao"] == (1000, 1640) and video["balao"] == (1000, 1805)
    assert it.coracao_curtido("like icon") is False and it.coracao_curtido("unlike icon") is True
    assert it.coracao_curtido("…") is None


def test_marcas_guardam_o_fim_e_contam_as_tentativas():
    m = it.marca(NOTIFICACAO)
    assert len(m) == 16 and NOTIFICACAO not in m and not it.terminado(m)
    assert it.guardar_falha(m, "comentario") == 1 and it.guardar_falha(m, "comentario") == 2
    assert not it.terminado(m)
    it.guardar(m, "comentario", "respondido")
    assert it.terminado(m)


# --- O robô no celular ---

@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(robo.time, "sleep", lambda s: None)
    monkeypatch.setattr(robo.ps.time, "sleep", lambda s: None)
    monkeypatch.setattr(robo.random, "uniform", lambda a, b: 0)
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")


@pytest.fixture
def avisos(monkeypatch):
    mandados = []
    monkeypatch.setattr(robo.avisar_rafael, "mandar_texto", lambda texto: mandados.append(texto) or True)
    return mandados


class Campo:
    def __init__(self, app):
        self.app = app

    @property
    def exists(self):
        return self.app.em_foco

    def set_text(self, texto):
        self.app.escrito = texto

    def get_text(self):
        return self.app.escrito


class CelularDosComentarios:
    """
    O app nas telas das respostas: início, Notificações, o painel do vídeo e o Responder.
    lugar: onde a resposta aparece depois de enviada ("embaixo", "outro" ou "nenhum").
    """

    def __init__(self, linhas=(NOTIFICACAO,), ja_respondido=False, lugar="embaixo", campo="Responder a Maria Souza",
                 abre_sozinho=False):
        self.linhas, self.ja_respondido, self.lugar, self.campo = list(linhas), ja_respondido, lugar, campo
        # Como no Motorola: às vezes o painel abre sozinho; outras, só o vídeo, e o robô toca no balão.
        self.abre_sozinho = abre_sozinho
        self.atual, self.em_foco, self.escrito, self.enviadas, self.toques = "inicio", False, "", [], []

    def _comentarios(self):
        nos = [_comentario("Loja Rafa", "Vestido lindo ✨", 960, criador=True),
               _comentario("Maria Souza", "Amei esse vestido, tem tamanho 10?", 1250)]
        y = 1500
        respostas = (["Tem sim!"] if self.ja_respondido else []) + (self.enviadas if self.lugar == "embaixo" else [])
        for texto in respostas:
            nos.append(_comentario("Loja Rafa", texto, y, resposta=True, criador=True))
            y += 250
        nos.append(_comentario("João", "Chegou rápido", y))
        if self.lugar == "outro":
            nos += [_comentario("Loja Rafa", texto, y + 250, resposta=True, criador=True) for texto in self.enviadas]
        return nos

    def dump_hierarchy(self):
        if self.atual == "inicio":
            return _xml(*BARRA)
        if self.atual == "notificacoes":
            return _xml(_el("Notificações", caixa=(400, 160, 680, 220)), FILTRO, *BARRA)
        if self.atual == "lista":
            return _notificacoes(*self.linhas)
        if self.atual == "player":
            return _player("Loja Rafa", "Vestido lindo", coracao="unlike icon")
        teclado = [_el(ident="key_pos_space", classe="FrameLayout", caixa=(300, 1900, 800, 1950))] if self.em_foco else []
        return _painel(*self._comentarios(), campo=self.campo if self.atual == "respondendo" else None)[:-len(
            "</node></hierarchy>")] + "".join(teclado) + "</node></hierarchy>"

    def click(self, x, y):
        import postador_shopee_video as ps
        tocados = [el for el in ps.elementos(self.dump_hierarchy()) if ps._dentro((x, y), el["caixa"])]
        textos = [el["texto"] or el["descricao"] for el in tocados]
        self.toques.append(textos[0] if textos else (x, y))
        if self.atual == "inicio" and "Notificações" in textos:
            self.atual = "notificacoes"
        elif self.atual == "notificacoes" and "Lives, Vídeos e Afiliados" in textos:
            self.atual = "lista"
        elif self.atual == "lista" and any(t in self.linhas for t in textos):
            self.atual = "painel" if self.abre_sozinho else "player"
        elif self.atual == "player" and "comment video icon" in textos:
            self.atual = "painel"
        elif self.atual == "painel" and "Responder" in textos:
            self.atual, self.em_foco = "respondendo", True
        elif self.atual == "respondendo" and "send comment" in textos:
            self.enviadas.append(self.escrito)
            self.atual, self.escrito = "painel", ""

    def __call__(self, **seletor):
        return Campo(self)

    def press(self, tecla, meta=None):
        if self.em_foco:
            self.em_foco = False
        else:
            self.atual = "inicio"

    def app_start(self, pacote, wait=False):
        pass

    def window_size(self):
        return 1080, 2400

    def swipe(self, *pontos):
        pass


@pytest.fixture
def ia(monkeypatch):
    pedidos = []

    async def resposta(comentario, produto="", legenda="", anteriores=()):
        pedidos.append((comentario, produto))
        return "Tem sim! Corre que esse vestido é sucesso"

    monkeypatch.setattr(it, "gerar_resposta", resposta)
    return pedidos


def test_primeira_vez_so_guarda_o_topo_e_nao_responde(avisos, ia):
    app = CelularDosComentarios()
    assert "guardei o topo" in robo.responder_comentarios(app, momento("2026-10-24 10:00"))
    assert not app.enviadas and not ia
    assert it.resultado_de(it.marca(NOTIFICACAO), "comentario") == "anterior"


def test_comentario_novo_e_respondido_embaixo_dele_e_nao_volta(avisos, ia):
    robo.gravar_estado(respostas_topo=it.marca("Ana curtiu seu vídeo."))
    app = CelularDosComentarios(linhas=(NOTIFICACAO, "Ana curtiu seu vídeo."))
    assert robo.responder_comentarios(app, momento("2026-10-24 10:00")) == "respostas: 1 respondido"
    assert app.enviadas == ["Tem sim! Corre que esse vestido é sucesso"]
    assert ia == [("Amei esse vestido, tem tamanho 10?", "Vestido Infantil Gatinho Estampado")]
    assert robo.ler_estado()["respostas_topo"] == it.marca(NOTIFICACAO)
    # O mesmo comentário não é respondido de novo, mesmo com o topo perdido.
    robo.gravar_estado(respostas_topo="outro")
    assert robo.responder_comentarios(app, momento("2026-10-24 11:00")) == "respostas: nenhum comentário novo"
    assert len(app.enviadas) == 1
    assert robo.tentativas_desde("2026-10-24 00:00:00")[-1]["resultado"] == "respondido"


def test_painel_que_abre_sozinho_tambem_serve_e_o_aviso_de_penalidade_pede_a_saude(avisos, ia):
    robo.gravar_estado(respostas_topo=it.marca("Ana curtiu seu vídeo."))
    penalidade = "[Esta ação gerou pontos de penalidade] O produto adicionado ao seu vídeo foi identificado"
    app = CelularDosComentarios(linhas=(penalidade, NOTIFICACAO, "Ana curtiu seu vídeo."), abre_sozinho=True)
    assert robo.responder_comentarios(app, momento("2026-10-24 10:00")) == "respostas: 1 respondido"
    assert "comment video icon" not in app.toques
    assert robo.ler_estado().get("penalidade_vista_em")


def test_comentario_que_o_perfil_ja_respondeu_nao_ganha_outra_resposta(avisos, ia):
    robo.gravar_estado(respostas_topo="velho")
    app = CelularDosComentarios(ja_respondido=True)
    assert robo.responder_comentarios(app, momento("2026-10-24 10:00")) == "respostas: 1 já respondido"
    assert not app.enviadas and not ia


def test_resposta_que_vai_para_outro_lugar_avisa_na_hora_e_nao_repete(avisos, ia):
    robo.gravar_estado(respostas_topo="velho")
    app = CelularDosComentarios(lugar="outro")
    assert robo.responder_comentarios(app, momento("2026-10-24 10:00")) == "respostas: 1 lugar errado"
    assert any("não ficou embaixo do comentário certo" in a for a in avisos)
    assert it.terminado(it.marca(NOTIFICACAO))


def test_resposta_que_nao_aparece_tenta_3_vezes_conferindo_antes_e_depois_desiste(avisos, ia):
    robo.gravar_estado(respostas_topo="velho")
    app = CelularDosComentarios(lugar="nenhum")
    for vez in range(2):
        assert robo.responder_comentarios(app, momento(f"2026-10-24 1{vez}:00")) == "respostas: 1 falhou"
        assert robo.ler_estado()["respostas_topo"] == "velho"       # o topo só anda com tudo resolvido
    assert robo.responder_comentarios(app, momento("2026-10-24 12:00")) == "respostas: 1 desistiu"
    assert any("fica para você responder à mão" in a for a in avisos)
    assert robo.ler_estado()["respostas_topo"] == it.marca(NOTIFICACAO)


def test_responder_que_nao_abre_o_campo_da_resposta_para_sem_escrever(avisos, ia):
    robo.gravar_estado(respostas_topo="velho")
    app = CelularDosComentarios(campo="Adicione um comentário")
    assert robo.responder_comentarios(app, momento("2026-10-24 10:00")) == "respostas: 1 falhou"
    assert not app.enviadas and app.escrito == ""
    assert robo.tentativas_desde("2026-10-24 00:00:00")[0]["passo"] == "tocar em Responder"


def test_comentario_que_a_ia_pula_avisa_e_nao_volta(monkeypatch, avisos):
    async def pular(*args, **kwargs):
        return ""

    monkeypatch.setattr(it, "gerar_resposta", pular)
    robo.gravar_estado(respostas_topo="velho")
    app = CelularDosComentarios()
    assert robo.responder_comentarios(app, momento("2026-10-24 10:00")) == "respostas: 1 pulado"
    assert not app.enviadas and avisos and it.terminado(it.marca(NOTIFICACAO))


def test_respostas_uma_vez_por_dia_e_o_feed_3_por_dia_espalhados():
    agora = momento("2026-10-24 10:00")
    assert robo.respostas_pendentes(agora)
    robo.gravar_estado(respostas_em="2026-10-24 09:00:00")
    assert not robo.respostas_pendentes(agora)
    robo.gravar_estado(respostas_continuar=True)
    assert robo.respostas_pendentes(agora)
    assert robo.feed_pendente(agora)
    robo.gravar_estado(feed_em="2026-10-24 09:00:00")
    assert not robo.feed_pendente(agora)
    assert robo.feed_pendente(momento("2026-10-24 11:00"))
    for n in range(3):
        it.guardar(f"video{n}", "video_feed", "comentado", agora)
    assert not robo.feed_pendente(momento("2026-10-24 20:00"))


class CelularDoFeed:
    """O feed Para você: uma live, um vídeo do próprio Rafael e vídeos de outros criadores."""

    def __init__(self, videos=None):
        self.videos = videos or ["live", ("Loja Rafa", "Vestido Infantil Gatinho"), ("Loja da Bia", "Mini saia linda"),
                                 ("Ana Achados", "Copo térmico que gela"), ("Leo", "Fone sem fio")]
        self.atual, self.indice, self.curtidos, self.comentarios = "inicio", 0, set(), {}
        self.em_foco, self.escrito, self.toques = False, "", []

    def _video(self):
        return self.videos[self.indice]

    def dump_hierarchy(self):
        if self.atual == "inicio":
            return _xml(*BARRA)
        video = self._video()
        if self.atual == "player":
            if video == "live":
                return _player(live=True)
            return _player(*video, coracao="unlike icon" if self.indice in self.curtidos else "like icon")
        feitos = [_comentario("Eu", texto, 1250 + 250 * k) for k, texto in enumerate(self.comentarios.get(self.indice, []))]
        return _painel(*feitos, campo="" if self.atual == "escrevendo" else None)

    def click(self, x, y):
        import postador_shopee_video as ps
        tocados = [el for el in ps.elementos(self.dump_hierarchy()) if ps._dentro((x, y), el["caixa"])]
        textos = [el["texto"] or el["descricao"] for el in tocados]
        self.toques.append(textos[0] if textos else (x, y))
        if self.atual == "inicio" and "Live e Vídeo" in textos:
            self.atual = "player"
        elif self.atual == "player" and any(t in ("like icon", "unlike icon") for t in textos):
            self.curtidos ^= {self.indice}
        elif self.atual == "player" and "comment video icon" in textos:
            self.atual = "painel"
        elif self.atual == "painel" and "input add a comment" in textos:
            self.atual, self.em_foco = "escrevendo", True
        elif self.atual == "escrevendo" and "send comment" in textos:
            self.comentarios.setdefault(self.indice, []).append(self.escrito)
            self.atual, self.escrito = "painel", ""

    def __call__(self, **seletor):
        return Campo(self)

    def press(self, tecla, meta=None):
        if self.em_foco:
            self.em_foco = False
        elif self.atual in ("painel", "escrevendo"):
            self.atual = "player"
        else:
            self.atual = "inicio"

    def app_start(self, pacote, wait=False):
        pass

    def window_size(self):
        return 1080, 2400

    def swipe(self, *pontos):
        self.indice = min(self.indice + 1, len(self.videos) - 1)


@pytest.fixture
def ia_do_feed(monkeypatch):
    async def comentario(legenda="", anteriores=()):
        return f"Que achado! {len(anteriores)}"

    monkeypatch.setattr(it, "gerar_comentario", comentario)
    monkeypatch.setattr(robo.random, "randint", lambda a, b: a)


def test_feed_pula_a_live_e_o_video_do_rafael_curte_e_comenta_um_de_outro_criador(avisos, ia_do_feed):
    robo.gravar_estado(conta_marca=it.marca("Loja Rafa"))
    app = CelularDoFeed()
    assert robo.interagir_no_feed(app, momento("2026-10-24 10:00")) == "feed: 1 vídeo curtido e comentado"
    assert app.curtidos == {2} and app.comentarios == {2: ["Que achado! 0"]}
    assert it.quantos_desde("video_feed", "comentado", "2026-10-24 00:00:00") == 1
    # O mesmo vídeo não é comentado de novo: o seguinte é o escolhido.
    app.atual, app.indice = "inicio", 0
    robo.interagir_no_feed(app, momento("2026-10-24 12:00"))
    assert app.comentarios == {2: ["Que achado! 0"], 3: ["Que achado! 1"]}


def test_feed_com_o_coracao_que_nao_curte_para_sem_comentar(monkeypatch, avisos, ia_do_feed):
    app = CelularDoFeed(videos=[("Loja da Bia", "Mini saia linda")])
    monkeypatch.setattr(app, "click", lambda x, y, original=app.click: None if (x, y) == (1000, 1640) else original(x, y))
    with pytest.raises(robo.Parada, match="coração"):
        robo.interagir_no_feed(app, momento("2026-10-24 10:00"))
    assert not app.comentarios


def test_rodada_responde_depois_dos_rascunhos_e_o_feed_por_ultimo(monkeypatch):
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    config = {**robo.PADRAO, "robo_pausado": False, "robo_limite_min": 1, "robo_limite_max": 1,
              "robo_inicio": 0, "robo_fim": 24}
    agora = momento("2026-10-27 23:59")
    robo.gravar_estado(treino_semana=robo.semana(agora))
    assert robo.o_que_fazer(config, agora) == ("rascunho", None)
    assert robo.o_que_fazer(config, agora) == ("responder", None)
    robo.gravar_estado(respostas_em="2026-10-27 23:59:00")
    assert robo.o_que_fazer(config, agora) == ("feed", None)
    robo.gravar_estado(feed_em="2026-10-27 23:59:00")
    assert robo.o_que_fazer(config, agora) is None


def test_comentario_do_feed_que_nao_aparece_conta_no_dia_e_o_video_nao_volta(monkeypatch, avisos, ia_do_feed):
    app = CelularDoFeed(videos=[("Loja da Bia", "Mini saia linda"), ("Ana Achados", "Copo térmico")])
    original = app.click

    def envia_e_some(x, y):
        original(x, y)
        if app.atual == "painel":
            app.comentarios.clear()

    monkeypatch.setattr(app, "click", envia_e_some)
    assert robo.interagir_no_feed(app, momento("2026-10-24 10:00")) == "feed: comentário enviado sem aparecer na lista"
    marca = it.marca("Loja da Bia", "Mini saia linda")
    assert it.resultado_de(marca, "video_feed") == "não confirmado"
    assert it.quantos_desde("video_feed", it.COMENTADOS_NO_FEED, "2026-10-24 00:00:00") == 1

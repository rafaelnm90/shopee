"""Respostas aos comentários e interação no feed da Shopee Vídeo (interacoes_shopee_video e o robô)."""
import asyncio
from datetime import datetime, timedelta
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


def _comentario(nome, texto, y, resposta=False, criador=False, ver="", curtido=False, curtidas=0):
    """
    Um comentário do painel: foto, nome (e o selo), texto, coração (com o número de curtidas
    dentro, quando há), data, Responder (e o "Curtido pelo criador").
    """
    x = 178 if resposta else 84
    nos = [_el(desc="avatar comment item", classe="ImageView", caixa=(x - 40, y - 40, x + 40, y + 40)),
           _el(nome, caixa=(x + 80, y - 30, x + 400, y + 10))]
    if criador:
        nos.append(_el("Criador", caixa=(x + 420, y - 30, x + 520, y + 10)))
    nos += [_el(texto, caixa=(x + 80, y + 30, 1000, y + 80)),
            _el(desc="button comment like", classe="ViewGroup", caixa=(990, y, 1040, y + 50), clicavel=True),
            _el("há 2 horas", caixa=(x + 80, y + 100, x + 250, y + 140)),
            _el("Responder", caixa=(x + 280, y + 100, x + 420, y + 140))]
    if curtidas:
        nos.append(_el(str(curtidas), caixa=(1005, y + 15, 1025, y + 45)))
    if curtido:
        nos.append(_el("Curtido pelo criador", caixa=(x + 450, y + 100, x + 750, y + 140)))
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
    assert it.como_ficou(certo, 0, resposta) == "comentário na tela, resposta embaixo dele, com o selo Criador"
    assert it.como_ficou(errado, 0, resposta) == ("comentário na tela, resposta embaixo de outro comentário, "
                                                  "com o selo Criador")
    assert it.como_ficou(certo, 0, "outra coisa") == "comentário na tela, resposta não vista"
    assert it.como_ficou([], None, resposta) == "painel sem comentários na tela"


def test_resposta_so_fica_no_lugar_errado_com_o_comentario_de_cima_dela_na_tela():
    resposta = "Tem sim! Corre que esse vestido é sucesso"
    # Logo depois de enviar, o painel pode mostrar a resposta com o comentário de cima dela
    # fora da tela (Motorola, 30/10/2026): não dá para dizer onde ela ficou.
    rolado = it.comentarios_do_painel(_painel(_comentario("Loja Rafa", resposta, 960, resposta=True, criador=True),
                                              _comentario("João", "Chegou rápido", 1250)))
    assert it.onde_ficou(rolado, None, resposta) is None
    assert it.como_ficou(rolado, None, resposta) == ("comentário fora da tela, resposta sem o comentário de cima "
                                                     "na tela, com o selo Criador")
    # Solta na lista, fora das respostas: lugar errado, mesmo sem o comentário da pessoa na tela.
    solta = it.comentarios_do_painel(_painel(_comentario("João", "Chegou rápido", 960),
                                             _comentario("Loja Rafa", resposta, 1250, criador=True)))
    assert it.onde_ficou(solta, None, resposta) == "outro lugar"
    assert it.como_ficou(solta, None, resposta).endswith("resposta solta na lista, com o selo Criador")
    # Embaixo do comentário certo, mesmo ainda sem o selo Criador.
    sem_selo = it.comentarios_do_painel(_painel(_comentario("Maria Souza", "Tem tamanho 10?", 1250),
                                                _comentario("Loja Rafa", resposta, 1500, resposta=True)))
    assert it.onde_ficou(sem_selo, 0, resposta) == "embaixo"
    # O comentário curto de outra pessoa, que só começa igual à resposta, não é ela.
    comeco = it.comentarios_do_painel(_painel(_comentario("Maria Souza", "Tem tamanho 10?", 1250),
                                              _comentario("João", "Tem sim", 1500)))
    assert it.onde_ficou(comeco, 0, resposta) is None


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


def test_ia_sem_nada_especifico_para_dizer_no_feed_responde_curtir(monkeypatch):
    # Escolha do Rafael (P151 1): nem toda curtida vem com comentário. O pedido do comentário
    # continua o mesmo, com a saída de só curtir; a palavra nunca vira o texto do comentário.
    import api_gemini
    pedidos, respostas = [], iter(["Curtir.", "CURTIR 👍", "Que cor linda!", "CURTIR"])

    async def gerar(prompt, imagens=None):
        pedidos.append(prompt)
        return next(respostas)

    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", gerar)
    assert asyncio.run(it.gerar_comentario("Dança nova")) == it.CURTIR
    assert asyncio.run(it.gerar_comentario("Dança nova", imagem=b"\xff\xd8jpeg")) == it.CURTIR
    assert asyncio.run(it.gerar_comentario("Mini saia")) == "Que cor linda!"
    assert all(it.PROMPT_COMENTARIO.split("{legenda}")[0] in prompt and prompt.endswith("escreva só: CURTIR")
               for prompt in pedidos)
    # Nas respostas aos comentários dos vídeos do Rafael não há a saída de só curtir.
    assert asyncio.run(it.gerar_resposta("Amei!")) == "CURTIR"


def test_comentario_do_feed_com_a_tela_do_video_vai_a_ia_com_a_imagem(monkeypatch):
    # Escolha do Rafael (P70): a IA comenta o que aparece no vídeo, não só a legenda.
    import api_gemini
    pedidos = []

    async def gerar(prompt, imagens=None):
        pedidos.append((prompt, imagens))
        return "Que cor linda!"

    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", gerar)
    assert asyncio.run(it.gerar_comentario("Mini saia", imagem=b"\xff\xd8jpeg")) == "Que cor linda!"
    prompt, imagens = pedidos[-1]
    assert imagens == [(b"\xff\xd8jpeg", "image/jpeg")] and "imagem anexa" in prompt
    assert asyncio.run(it.gerar_comentario("Mini saia")) == "Que cor linda!"
    prompt, imagens = pedidos[-1]
    assert imagens is None and "imagem anexa" not in prompt


def test_numero_do_app_vira_contagem():
    assert it.contagem("3") == 3 and it.contagem("1.234") == 1234
    assert it.contagem("1,2 mil") == 1200 and it.contagem("2K") == 2000 and it.contagem("1,5mi") == 1500000
    assert it.contagem("Comentar") is None and it.contagem("") is None


# As abas do alto do player (Live e Vídeo), como no Motorola.
ABAS = [_el("Vídeos", caixa=(350, 140, 460, 195), clicavel=True), _el("Lives", caixa=(510, 140, 600, 195), clicavel=True),
        _el("Para você", caixa=(660, 140, 810, 195), clicavel=True)]


def _player(autor="Loja da Bia", legenda="Mini saia que veste bem", coracao="like icon", live=False,
            comentarios=None):
    if live:
        return _xml(_el(ident="live_room_in_video_feed_18", classe="FrameLayout", caixa=(0, 0, 1080, 2260)),
                    _el("Diga alguma coisa", ident="tv_send_message", caixa=(200, 2150, 600, 2210), clicavel=True),
                    *ABAS, *BARRA)
    return _xml(_el(ident="rn_vod_player_view_with_surface", classe="FrameLayout", caixa=(0, 0, 1080, 2260)),
                *ABAS,
                _el(desc="video caption user", classe="ViewGroup", caixa=(40, 2030, 460, 2080), clicavel=True),
                _el(autor, caixa=(40, 2030, 460, 2080)),
                _el(desc="video caption title", classe="ViewGroup", caixa=(40, 2100, 820, 2160), clicavel=True),
                _el(legenda, caixa=(40, 2100, 820, 2160)),
                _el(desc="avatar icon", classe="ViewGroup", caixa=(960, 1390, 1040, 1470), clicavel=True),
                _el(desc=coracao, classe="ViewGroup", caixa=(960, 1600, 1040, 1680), clicavel=True),
                _el("12", caixa=(980, 1675, 1020, 1700)),
                _el(desc="comment video icon", classe="ViewGroup", caixa=(960, 1770, 1040, 1840), clicavel=True),
                *([_el(str(comentarios), caixa=(985, 1852, 1020, 1878))] if comentarios is not None else []),
                _el(desc="video share icon", classe="ViewGroup", caixa=(960, 1950, 1040, 2010), clicavel=True),
                *BARRA)


def test_feed_live_e_video():
    assert it.eh_live(_player(live=True)) and it.video_do_feed(_player(live=True)) is None
    video = it.video_do_feed(_player())
    assert video["autor"] == "Loja da Bia" and video["legenda"] == "Mini saia que veste bem"
    assert video["coracao"] == (1000, 1640) and video["balao"] == (1000, 1805)
    assert it.coracao_curtido("like icon") is False and it.coracao_curtido("unlike icon") is True
    assert it.coracao_curtido("…") is None


def _player_do_motorola(compartilhar=True, autor="Loja da Bia"):
    """O vídeo do Para você como o Motorola mostrou em 24/10/2026 (explorar 156): o ícone do alto à
    direita, a foto e o seguir do criador, o cartão do produto e o rótulo de IA."""
    nos = [_el(ident="rn_vod_player_view_with_surface", classe="FrameLayout", caixa=(0, 0, 1080, 2260)), *ABAS,
           _el(desc="search icon", classe="ViewGroup", caixa=(970, 130, 1052, 205), clicavel=True),
           _el(desc="shopee video product card", classe="ViewGroup", caixa=(250, 1820, 975, 1890), clicavel=True),
           _el("Comprar com cupom", caixa=(450, 1830, 780, 1880)),
           _el(desc="close product card", classe="ViewGroup", caixa=(760, 1620, 812, 1670), clicavel=True),
           _el(desc="video caption user", classe="ViewGroup", caixa=(40, 2030, 285, 2082), clicavel=True),
           _el(autor, caixa=(40, 2030, 285, 2082)),
           _el(desc="video caption title", classe="ViewGroup", caixa=(30, 2105, 822, 2161), clicavel=True),
           _el("Mini saia que veste bem... mais", caixa=(30, 2105, 822, 2161)),
           _el(desc="creator profile avatar icon", classe="ViewGroup", caixa=(961, 1393, 1041, 1473), clicavel=True),
           _el(desc="creator profile avatar follow icon", classe="ViewGroup", caixa=(980, 1466, 1024, 1510),
               clicavel=True),
           _el(desc="like icon", classe="ViewGroup", caixa=(962, 1605, 1042, 1685), clicavel=True),
           _el("12", caixa=(985, 1675, 1020, 1700)),
           _el(desc="comment video icon", classe="ViewGroup", caixa=(962, 1766, 1042, 1846), clicavel=True),
           _el("3", caixa=(985, 1858, 1020, 1884))]
    if compartilhar:
        nos += [_el(desc="video share icon", classe="ViewGroup", caixa=(961, 1942, 1041, 2022), clicavel=True),
                _el("Compartilhar", caixa=(940, 2040, 1062, 2070))]
    nos += [_el(desc="video more icon", classe="ViewGroup", caixa=(961, 2128, 1041, 2208), clicavel=True),
            _el("Identificado como conteúdo gerado por IA.", caixa=(40, 2185, 805, 2215)), *BARRA]
    return _xml(*nos)


def test_feed_le_o_video_como_o_motorola_mostra_e_diz_por_que_pula():
    video, motivo = it.ler_o_feed(_player_do_motorola())
    assert motivo == "" and video["autor"] == "Loja da Bia" and video["legenda"].startswith("Mini saia")
    assert video["comentarios"] == 3                                      # o número embaixo do balão
    assert video["coracao"] == (1002, 1645) and video["balao"] == (1002, 1806)
    assert it.ler_o_feed(_player(live=True)) == (None, "live")
    assert it.ler_o_feed(_xml(*ABAS, *BARRA)) == (None, "tela sem o player de vídeo")
    assert it.ler_o_feed(_player_do_motorola(compartilhar=False)) == (None, "sem o compartilhar na coluna da direita")
    assert it.ler_o_feed(_player_do_motorola(autor="")) == (None, "sem o nome do criador")


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
    # A limpeza das 4h que volta no mesmo dia (P137) tem testes próprios: no banco novo do teste, ela nunca rodou.
    monkeypatch.setattr(robo, "limpeza_fora_da_hora_pendente", lambda agora=None: False)
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
    rola_ao_enviar: logo depois de enviar, o painel rola até a resposta, e o vídeo e o
    comentário de cima dela saem da tela até o painel ser aberto de novo.
    """

    def __init__(self, linhas=(NOTIFICACAO,), ja_respondido=False, lugar="embaixo", campo="Responder a Maria Souza",
                 abre_sozinho=False, rola_ao_enviar=False, ja_curtido=False, curte=True):
        self.linhas, self.ja_respondido, self.lugar, self.campo = list(linhas), ja_respondido, lugar, campo
        # O coração do comentário da Maria: já curtido antes, e se o toque nele curte (o "Curtido pelo criador").
        self.curtido, self.curte = ja_curtido, curte
        # Como no Motorola: às vezes o painel abre sozinho; outras, só o vídeo, e o robô toca no balão.
        self.abre_sozinho, self.rola_ao_enviar, self.rolado = abre_sozinho, rola_ao_enviar, False
        self.atual, self.em_foco, self.escrito, self.enviadas, self.toques = "inicio", False, "", [], []

    def _comentarios(self):
        nos = [_comentario("Loja Rafa", "Vestido lindo ✨", 960, criador=True),
               _comentario("Maria Souza", "Amei esse vestido, tem tamanho 10?", 1250, curtido=self.curtido)]
        y = 1500
        if self.rolado:
            nos, y = [], 960
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
            self.atual, self.rolado = "painel" if self.abre_sozinho else "player", False
        elif self.atual == "player" and "comment video icon" in textos:
            self.atual = "painel"
        elif self.atual == "painel" and "Responder" in textos:
            self.atual, self.em_foco = "respondendo", True
        elif self.atual == "painel" and "button comment like" in textos and not self.rolado and 1250 <= y < 1300:
            self.curtido = self.curtido or self.curte
        elif self.atual == "respondendo" and "send comment" in textos:
            self.enviadas.append(self.escrito)
            self.atual, self.escrito, self.rolado = "painel", "", self.rola_ao_enviar

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
    # Confirmado no painel reaberto, com o caso guardado para o checkup.
    assert _registro_das_respostas() == [("resposta no lugar errado", (
        "na hora: comentário na tela, resposta embaixo de outro comentário, com o selo Criador; "
        "ao reabrir: comentário na tela, resposta embaixo de outro comentário, com o selo Criador"))]
    assert [c.split("-")[-1] for c in robo.casos_robo.casos()] == ["responder"]


def test_resposta_vista_com_o_painel_rolado_e_conferida_no_painel_reaberto_sem_aviso(avisos, ia):
    # No Motorola (30/10/2026), logo depois de enviar, o painel mostrou as respostas sem o
    # comentário de cima delas, e as 4 do dia foram dadas como no lugar errado; no app,
    # estavam embaixo do comentário certo.
    robo.gravar_estado(respostas_topo="velho")
    app = CelularDosComentarios(rola_ao_enviar=True)
    assert robo.responder_comentarios(app, momento("2026-10-24 10:00")) == "respostas: 1 respondido"
    assert len(app.enviadas) == 1 and not any("não ficou embaixo" in a for a in avisos)
    assert it.resultado_de(it.marca(NOTIFICACAO), "comentario") == "respondido"
    assert _registro_das_respostas() == [("respondido", (
        "conferida ao reabrir (na hora: comentário fora da tela, resposta sem o comentário de cima na tela, "
        "com o selo Criador)"))]
    assert not robo.casos_robo.casos()


def _registro_das_respostas():
    return [(resultado, detalhe) for _m, _p, resultado, detalhe, _o
            in robo.registro_processos.sequencia("shopee_video", "responder comentário", "2000-01-01 00:00:00")]


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


def test_respostas_tres_vezes_durante_o_dia_com_3_h_entre_elas_e_o_feed_espalhado(monkeypatch):
    # Escolhas do Rafael (P70 e P161 1): as Notificações 3 vezes por dia, das 8h às 22h, sem hora
    # marcada, com pelo menos 3 h entre uma leitura e outra; cada uma a partir do começo da parte
    # dela no dia (8h, 12h40 e 17h20), para as três não saírem todas de manhã.
    assert robo.LEITURAS_DAS_RESPOSTAS == 3 and robo.DURANTE_O_DIA == (8, 22)
    assert not robo.respostas_pendentes(momento("2026-10-24 07:59"))
    assert robo.respostas_pendentes(momento("2026-10-24 08:00"))
    robo.contar_leitura(momento("2026-10-24 08:05"))
    assert robo.leituras_de_hoje(momento("2026-10-24 09:00")) == 1
    assert not robo.respostas_pendentes(momento("2026-10-24 12:35"))
    assert robo.respostas_pendentes(momento("2026-10-24 12:40"))
    robo.gravar_estado(respostas_continuar=True)                          # parou no limite: segue
    assert robo.respostas_pendentes(momento("2026-10-24 09:20"))
    robo.gravar_estado(respostas_continuar=False)
    # A leitura que começou tarde empurra a seguinte para 3 h depois dela.
    robo.contar_leitura(momento("2026-10-24 15:00"))
    assert not robo.respostas_pendentes(momento("2026-10-24 17:20"))
    assert not robo.respostas_pendentes(momento("2026-10-24 17:59"))
    assert robo.respostas_pendentes(momento("2026-10-24 18:00"))
    robo.contar_leitura(momento("2026-10-24 18:00"))
    # Feitas as 3, só no dia seguinte, a partir das 8h.
    assert not robo.respostas_pendentes(momento("2026-10-24 21:30"))
    assert not robo.respostas_pendentes(momento("2026-10-25 07:59"))
    assert robo.respostas_pendentes(momento("2026-10-25 08:00"))
    linhas = [r[2] for r in robo.registro_processos.sequencia("shopee_video", robo.PROCESSO_DA_LEITURA,
                                                               "2000-01-01 00:00:00")]
    assert linhas == ["1ª de 3 hoje", "2ª de 3 hoje", "3ª de 3 hoje"]
    # A continuação da leitura que parou no limite da rodada não conta como outra leitura.
    monkeypatch.setattr(robo, "responder_comentarios", lambda d, agora=None: "respostas: nenhum comentário novo")
    robo.gravar_estado(respostas_continuar=True)
    robo._agir(None, "responder", None, False, robo.ler_config(), momento("2026-10-25 08:15"))
    assert robo.leituras_de_hoje(momento("2026-10-25 08:15")) == 0 and not robo.ler_estado()["respostas_continuar"]
    robo._agir(None, "responder", None, False, robo.ler_config(), momento("2026-10-25 08:30"))
    assert robo.leituras_de_hoje(momento("2026-10-25 08:30")) == 1
    # Uma leitura que não saiu até as 22h não sai fora do dia.
    robo.gravar_estado(respostas_leituras={"dia": "2026-10-26", "vezes": 2}, respostas_em="2026-10-26 18:30:00")
    assert not robo.respostas_pendentes(momento("2026-10-26 22:00"))
    # O feed (P152): até 5 por dia, espalhados pelo Horário do Robô (das 8h às 22h: um a cada 2h40).
    agora = momento("2026-10-24 10:00")
    assert robo.feed_pendente(agora)
    robo.gravar_estado(feed_em="2026-10-24 09:00:00")
    assert not robo.feed_pendente(agora)
    assert not robo.feed_pendente(momento("2026-10-24 11:35"))
    assert robo.feed_pendente(momento("2026-10-24 11:40"))
    for n in range(4):
        it.guardar(f"video{n}", "video_feed", "comentado", agora)
    assert robo.feed_pendente(momento("2026-10-24 20:00"))
    it.guardar("video4", "video_feed", it.SO_CURTIDO, agora)
    assert not robo.feed_pendente(momento("2026-10-24 20:00"))


def test_feed_espalhado_no_dia_todo_e_o_que_falha_tenta_de_novo_na_rodada_seguinte(monkeypatch, avisos, ia_do_feed):
    # Escolha do Rafael (P152): os 5 do dia espalhados pelo Horário do Robô (no Dia Todo, um a
    # cada 4h40: a hora das 4h conta, porque acabada a limpeza ela fica livre, P161 1); o que falha
    # não conta, e a rodada seguinte tenta de novo, até dar certo.
    config = {**robo.PADRAO, "robo_inicio": 0, "robo_fim": 24}
    robo.db.salvar_config(robo.CHAVE_CONFIG, config)
    assert robo.intervalo_do_feed(config) == timedelta(hours=4, minutes=40)
    robo.gravar_estado(conta_marca=it.marca("Loja Rafa"))
    app = CelularDoFeed()
    agora = momento("2026-10-28 00:05")
    assert robo.feed_pendente(agora)
    assert robo._agir(app, "feed", None, False, config, agora) == "feed: 1 vídeo curtido e comentado"
    assert robo.ler_estado()["feed_em"] == "2026-10-28 00:05:00"
    assert not robo.feed_pendente(momento("2026-10-28 04:40"))
    assert robo.feed_pendente(momento("2026-10-28 04:45"))
    # Às 4h, a limpeza vem primeiro; acabada, o feed sai na mesma hora.
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    monkeypatch.setattr(robo, "respostas_pendentes", lambda agora=None: False)
    robo.gravar_estado(treino_semana=robo.semana(agora))
    assert robo.o_que_fazer(config, momento("2026-10-28 04:45")) == ("descurtir", None)
    robo.gravar_estado(descurtir_em="2026-10-28 04:00:00", favoritos_limpos=True)
    assert robo.o_que_fazer(config, momento("2026-10-28 04:45")) == ("feed", None)
    # Às 5h, a curtida não pega: nada conta, o feed_em fica, e a rodada das 5:15 tenta de novo.
    app.atual, app.indice = "inicio", 0
    monkeypatch.setattr(app, "click", lambda x, y, original=app.click: None if (x, y) == (1000, 1640)
                        else original(x, y))
    with pytest.raises(robo.Parada, match="coração"):
        robo.interagir_no_feed(app, momento("2026-10-28 05:00"))
    assert robo.ler_estado()["feed_em"] == "2026-10-28 00:05:00"
    assert robo.videos_do_feed_que_faltam(momento("2026-10-28 05:15")) == 4
    assert robo.feed_pendente(momento("2026-10-28 05:15"))
    assert robo.o_que_fazer(config, momento("2026-10-28 05:15")) == ("feed", None)


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
            return _player(*video[:2], coracao="unlike icon" if self.indice in self.curtidos else "like icon",
                           comentarios=video[2] if len(video) > 2 else None)
        # O comentário do robô sai com o nome do perfil (o do vídeo do próprio Rafael), não "Eu".
        feitos = [_comentario("Loja Rafa", texto, 1250 + 250 * k)
                  for k, texto in enumerate(self.comentarios.get(self.indice, []))]
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
    imagens = []

    async def comentario(legenda="", anteriores=(), imagem=None):
        imagens.append(imagem)
        return f"Que achado! {len(anteriores)}"

    monkeypatch.setattr(it, "gerar_comentario", comentario)
    monkeypatch.setattr(robo.random, "randint", lambda a, b: a)
    return imagens


def test_feed_prefere_o_video_com_poucos_comentarios(avisos, ia_do_feed):
    # Escolha do Rafael (P70): o comentário do robô fica no alto e é visto.
    app = CelularDoFeed(videos=[("Loja da Bia", "Mini saia linda", 500), ("Ana Achados", "Copo térmico que gela", 4)])
    assert robo.interagir_no_feed(app, momento("2026-10-24 10:00")) == "feed: 1 vídeo curtido e comentado"
    assert app.comentarios == {1: ["Que achado! 0"]}
    vistos = [(r, d) for _m, _p, r, d, _o in robo.registro_processos.sequencia("shopee_video", "feed: vídeo olhado", "")]
    # O escolhido leva a faixa dos comentários: o checkup mostra que o robô leu o número.
    assert vistos == [("muitos comentários", ""), ("escolhido", "até 20 comentários")]


def test_feed_sem_video_de_poucos_comentarios_comenta_um_qualquer_na_2a_metade(monkeypatch, avisos, ia_do_feed):
    monkeypatch.setattr(robo, "VIDEOS_OLHADOS_NO_FEED", 2)
    app = CelularDoFeed(videos=[("Loja da Bia", "Mini saia linda", 500), ("Ana Achados", "Copo térmico", 300)])
    assert robo.interagir_no_feed(app, momento("2026-10-24 10:00")) == "feed: 1 vídeo curtido e comentado"
    assert app.comentarios == {1: ["Que achado! 0"]}
    vistos = [(r, d) for _m, _p, r, d, _o in robo.registro_processos.sequencia("shopee_video", "feed: vídeo olhado", "")]
    assert vistos == [("muitos comentários", ""), ("escolhido", "mais de 20 comentários")]


def test_feed_anota_quando_nao_le_o_numero_de_comentarios(monkeypatch, avisos, ia_do_feed):
    # Sem o número embaixo do balão, a preferência pelos de poucos comentários não funciona:
    # o registro diz, e o checkup mostra.
    monkeypatch.setattr(robo.random, "randint", lambda a, b: 1)
    app = CelularDoFeed(videos=[("Loja da Bia", "Mini saia linda"), ("Ana Achados", "Copo térmico", 7)])
    assert robo.interagir_no_feed(app, momento("2026-10-24 10:00")) == "feed: 1 vídeo curtido e comentado"
    vistos = [(r, d) for _m, _p, r, d, _o in robo.registro_processos.sequencia("shopee_video", "feed: vídeo olhado", "")]
    assert vistos == [("deixado passar", "sem o número de comentários"), ("escolhido", "até 20 comentários")]


def test_feed_manda_a_tela_do_video_para_a_ia(avisos, ia_do_feed):
    from PIL import Image

    class ComTela(CelularDoFeed):
        def screenshot(self):
            return Image.new("RGB", (1080, 2400), (200, 50, 50))

    app = ComTela(videos=[("Loja da Bia", "Mini saia linda")])
    robo.interagir_no_feed(app, momento("2026-10-24 10:00"))
    assert ia_do_feed[-1][:2] == b"\xff\xd8"                              # JPEG
    import io
    assert Image.open(io.BytesIO(ia_do_feed[-1])).size == robo.TAMANHO_DA_TELA_PARA_A_IA   # metade do tamanho
    # Sem o print, o comentário sai só pela legenda.
    robo.interagir_no_feed(CelularDoFeed(videos=[("Ana Achados", "Copo térmico")]), momento("2026-10-24 11:00"))
    assert ia_do_feed[-1] is None


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


def test_rodada_do_feed_faz_um_video_so_mesmo_com_os_5_do_dia_por_fazer(avisos, ia_do_feed):
    # Escolha do Rafael (P152): um vídeo por rodada, nunca vários seguidos, mesmo com os 5 do dia
    # por fazer e o dia acabando.
    robo.db.salvar_config(robo.CHAVE_CONFIG, {**robo.PADRAO})
    robo.gravar_estado(conta_marca=it.marca("Loja Rafa"))
    app = CelularDoFeed()
    agora = momento("2026-10-28 20:44")
    resultado = robo._agir(app, "feed", None, False, robo.ler_config(), agora)
    assert resultado == "feed: 1 vídeo curtido e comentado"
    assert app.comentarios == {2: ["Que achado! 0"]}
    assert robo.videos_do_feed_que_faltam(agora) == robo.interacoes.VIDEOS_NO_FEED_POR_DIA - 1


def test_comentario_que_para_depois_da_curtida_conta_como_so_curtido(monkeypatch, avisos, ia_do_feed):
    # A curtida já saiu quando o comentário para: o vídeo conta nos do dia, para nunca passarem de
    # 5 curtidas por dia com as tentativas de novo (P152), e a parada segue para o caso.
    app = CelularDoFeed(videos=[("Loja da Bia", "Mini saia linda")])
    monkeypatch.setattr(robo, "painel_de_comentarios", lambda d, segundos=12: None)
    agora = momento("2026-10-24 10:00")
    with pytest.raises(robo.Parada):
        robo.interagir_no_feed(app, agora)
    assert app.curtidos == {0} and not app.comentarios
    assert it.resultado_de(it.marca("Loja da Bia", "Mini saia linda"), "video_feed") == it.SO_CURTIDO
    assert robo.ler_estado()["feed_em"] == "2026-10-24 10:00:00"
    linhas = robo.registro_processos.sequencia("shopee_video", "feed: comentar", "")
    assert [(r, d.startswith("o comentário parou: ")) for _m, _p, r, d, _o in linhas] == [(it.SO_CURTIDO, True)]


def test_feed_sem_nada_para_dizer_so_curte_e_o_video_conta_no_dia(monkeypatch, avisos, ia_do_feed):
    # Escolha do Rafael (P151 1): sem nada específico para dizer, fica só a curtida; o vídeo conta
    # nos do dia e não volta.
    async def so_curtir(legenda="", anteriores=(), imagem=None):
        return it.CURTIR

    monkeypatch.setattr(it, "gerar_comentario", so_curtir)
    app = CelularDoFeed(videos=[("Loja da Bia", "Mini saia linda"), ("Ana Achados", "Copo térmico")])
    agora = momento("2026-10-24 10:00")
    faltavam = robo.videos_do_feed_que_faltam(agora)
    assert robo.interagir_no_feed(app, agora) == "feed: 1 vídeo curtido, sem comentário"
    assert app.curtidos == {0} and not app.comentarios
    assert "comment video icon" not in app.toques                        # o painel de comentários nem abre
    assert it.resultado_de(it.marca("Loja da Bia", "Mini saia linda"), "video_feed") == it.SO_CURTIDO
    assert robo.videos_do_feed_que_faltam(agora) == faltavam - 1
    assert [r for _m, _p, r, _d, _o in robo.registro_processos.sequencia("shopee_video", "feed: comentar", "")] == [
        it.SO_CURTIDO]
    # O mesmo vídeo não volta: na rodada seguinte, o próximo é o escolhido.
    app.atual, app.indice = "inicio", 0
    robo.interagir_no_feed(app, momento("2026-10-24 12:00"))
    assert app.curtidos == {0, 1} and not app.comentarios


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
    agora = momento("2026-10-27 21:00")
    robo.gravar_estado(treino_semana=robo.semana(agora))
    robo.estado_do_dia(config, agora)
    robo.db.atualizar_config(robo.CHAVE_DIA, lambda plano: plano.update(horarios=["20:00"], feitos=0))
    assert robo.o_que_fazer(config, agora) == ("rascunho", None)
    assert robo.o_que_fazer(config, agora) == ("responder", None)
    robo.contar_leitura(agora)
    assert robo.o_que_fazer(config, agora) == ("feed", None)
    robo.gravar_estado(feed_em="2026-10-27 21:00:00")
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
    assert it.quantos_desde("video_feed", it.FEITOS_NO_FEED, "2026-10-24 00:00:00") == 1


class CelularDoFeedSemComentarios(CelularDoFeed):
    """O vídeo sem nenhum comentário: o painel abre sem o título "N Comentários" (Motorola, 25/10/2026)."""

    def dump_hierarchy(self):
        xml = super().dump_hierarchy()
        if self.atual in ("painel", "escrevendo") and not self.comentarios.get(self.indice):
            xml = xml.replace('text="4 Comentários"', 'text="Seja o primeiro"')
        return xml


def test_feed_comenta_no_video_sem_nenhum_comentario(avisos, ia_do_feed):
    # Em 25/10, os 3 comentários do feed que pararam em "o painel de comentários não abriu"
    # eram em vídeos com 0 comentários: o painel abria, mas sem o título que o robô esperava.
    app = CelularDoFeedSemComentarios(videos=[("Loja da Bia", "Mini saia linda")])
    assert robo.interagir_no_feed(app, momento("2026-10-24 10:00")) == "feed: 1 vídeo curtido e comentado"
    assert app.comentarios == {0: ["Que achado! 0"]}


class CelularDoFeedQueAbreEscrevendo(CelularDoFeed):
    """O vídeo sem nenhum comentário: o painel já abre com o campo de escrever em foco e o teclado (Motorola, 25/10/2026, 12:15)."""

    def click(self, x, y):
        antes = self.atual
        super().click(x, y)
        if antes == "player" and self.atual == "painel":
            self.atual, self.em_foco = "escrevendo", True


def test_feed_escreve_direto_quando_o_painel_ja_abre_escrevendo(avisos, ia_do_feed):
    # Em 25/10 às 12:15, o painel do vídeo sem comentários abriu já com "Adicionar um comentário..."
    # em foco e o teclado: não havia o "add a comment" fechado, e o robô parava.
    app = CelularDoFeedQueAbreEscrevendo(videos=[("Loja da Bia", "Mini saia linda")])
    assert robo.interagir_no_feed(app, momento("2026-10-24 10:00")) == "feed: 1 vídeo curtido e comentado"
    assert app.comentarios == {0: ["Que achado! 0"]}
    assert "input add a comment" not in app.toques


def test_feed_que_para_guarda_o_caso_com_a_tela_da_hora(monkeypatch, avisos, ia_do_feed):
    # O caso tem de mostrar a tela em que parou (o painel), e não a de depois de sair dela.
    class PainelQueNaoAbre(CelularDoFeed):
        def click(self, x, y):
            super().click(x, y)
            if self.atual == "painel":
                self.atual = "travado"

        def dump_hierarchy(self):
            return _xml(_el("Carregando")) if self.atual == "travado" else super().dump_hierarchy()

    telas = []
    monkeypatch.setattr(robo, "_guardar_caso", lambda d, acao, resultado, motivo, **k: telas.append(d.atual))
    monkeypatch.setattr(robo, "pausa", lambda segundos: None)
    app = PainelQueNaoAbre(videos=[("Loja da Bia", "Mini saia linda")])
    with pytest.raises(robo.Parada, match="painel de comentários") as erro:
        robo.interagir_no_feed(app, momento("2026-10-24 10:00"))
    assert telas == ["travado"] and erro.value.caso_guardado


def test_comentarios_do_painel_dizem_onde_curtir_e_se_ja_esta_curtido():
    painel = it.comentarios_do_painel(_painel(_comentario("Maria Souza", "Amei!", 1250, curtido=True),
                                              _comentario("João", "Chegou rápido", 1500)))
    assert [(c["nome"], c["curtir"], c["curtido"]) for c in painel] == [
        ("Maria Souza", (1015, 1275), True), ("João", (1015, 1525), False)]
    # O "Curtido pelo criador" não vira o texto do comentário.
    assert painel[0]["texto"] == "Amei!"


def test_comentario_respondido_tambem_e_curtido(avisos, ia):
    # Print do Rafael (30/10, 20:57): a resposta saiu, mas o comentário da pessoa ficou sem a curtida.
    robo.gravar_estado(respostas_topo="velho")
    app = CelularDosComentarios()
    assert robo.responder_comentarios(app, momento("2026-10-24 10:00")) == "respostas: 1 respondido"
    assert app.curtido and app.toques.count("button comment like") == 1
    assert _registro_das_curtidas() == ["curtido"]


def test_comentario_ja_curtido_nao_e_tocado_de_novo(avisos, ia):
    robo.gravar_estado(respostas_topo="velho")
    app = CelularDosComentarios(ja_curtido=True)
    assert robo.responder_comentarios(app, momento("2026-10-24 10:00")) == "respostas: 1 respondido"
    assert "button comment like" not in app.toques
    assert _registro_das_curtidas() == ["já curtido"]


def test_curtida_que_nao_aparece_fica_no_registro_e_a_resposta_vale(avisos, ia):
    robo.gravar_estado(respostas_topo="velho")
    app = CelularDosComentarios(curte=False)
    assert robo.responder_comentarios(app, momento("2026-10-24 10:00")) == "respostas: 1 respondido"
    assert _registro_das_curtidas() == ["não confirmado"]
    assert it.resultado_de(it.marca(NOTIFICACAO), "comentario") == "respondido"


def test_resposta_no_lugar_errado_nao_curte_o_comentario(avisos, ia):
    robo.gravar_estado(respostas_topo="velho")
    app = CelularDosComentarios(lugar="outro")
    assert robo.responder_comentarios(app, momento("2026-10-24 10:00")) == "respostas: 1 lugar errado"
    assert "button comment like" not in app.toques and not _registro_das_curtidas()


def _registro_das_curtidas():
    return [resultado for _m, _p, resultado, _d, _o
            in robo.registro_processos.sequencia("shopee_video", "curtir comentário", "2000-01-01 00:00:00")]


# --- O comentário no próprio vídeo (P148 2) ---

LINK_DO_POST = "https://sv.shopee.com.br/share-video/post1"
TITULO_DO_POST = "Vestido Infantil Gatinho"


class CelularDoPost:
    """
    O vídeo do Rafael aberto pelo link do post (o player do feed) e o painel de comentários
    dele, com os comentários do Rafael (selo Criador; o novo aparece no alto). em_analise: o
    link abre o aviso de vídeo em análise, sem o player.
    """

    def __init__(self, comentarios=(), curtido=False, em_analise=False, removido=False):
        self.atual, self.curtido, self.em_analise, self.removido = "inicio", curtido, em_analise, removido
        self.comentarios, self.curtidos_no_painel = list(comentarios), set()
        self.em_foco, self.escrito, self.toques = False, "", []

    def dump_hierarchy(self):
        if self.atual == "inicio":
            return _xml(*BARRA)
        if self.atual == "player":
            if self.removido:
                return _xml(_el("Este vídeo foi removido", caixa=(300, 1000, 780, 1060)), *BARRA)
            if self.em_analise:
                return _xml(_el("Vídeo em Análise", caixa=(300, 1000, 780, 1060)),
                            _el("em breve estará disponível ao público", caixa=(200, 1080, 880, 1130)), *BARRA)
            return _player("Loja Rafa", TITULO_DO_POST, coracao="unlike icon" if self.curtido else "like icon")
        feitos = [_comentario("Loja Rafa", texto, 1250 + 250 * k, criador=True, curtido=texto in self.curtidos_no_painel)
                  for k, texto in enumerate(self.comentarios)]
        return _painel(*feitos, campo="" if self.atual == "escrevendo" else None)

    def click(self, x, y):
        import postador_shopee_video as ps
        tocados = [el for el in ps.elementos(self.dump_hierarchy()) if ps._dentro((x, y), el["caixa"])]
        textos = [el["texto"] or el["descricao"] for el in tocados]
        self.toques.append(textos[0] if textos else (x, y))
        if self.atual == "player" and any(t in ("like icon", "unlike icon") for t in textos):
            self.curtido = not self.curtido
        elif self.atual == "player" and "comment video icon" in textos:
            self.atual = "painel"
        elif self.atual == "painel" and "input add a comment" in textos:
            self.atual, self.em_foco = "escrevendo", True
        elif self.atual == "escrevendo" and "send comment" in textos:
            self.comentarios.insert(0, self.escrito)
            self.atual, self.escrito, self.em_foco = "painel", "", False
        elif self.atual == "painel" and "button comment like" in textos:
            self.curtidos_no_painel ^= {self.comentarios[round((y - 1275) / 250)]}

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
        pass


def _postado(link=LINK_DO_POST, quando="2026-11-01 10:00:00"):
    ident = robo.criar("video:1", None)
    robo.atualizar(ident, estado="postado", criado_em=quando, postado_em=quando, link_post=link, titulo=TITULO_DO_POST,
                   produtos=["Vestido Infantil Gatinho Estampado"], comentario="Amei! #achadinhos")
    return ident


@pytest.fixture
def ia_do_proprio(monkeypatch):
    pedidos = []

    async def proprio(produto="", titulo="", anteriores=()):
        pedidos.append(list(anteriores))
        return f"Esse vale muito a pena! {len(pedidos)}"

    monkeypatch.setattr(it, "gerar_proprio", proprio)
    # O registro guarda as datas dos testes (2026-11-01), mais velhas que os 3 dias de sempre.
    monkeypatch.setattr(robo.registro_processos, "DIAS_DO_REGISTRO", 3650)
    return pedidos


@pytest.fixture
def pelo_link(monkeypatch):
    abertos = []
    monkeypatch.setattr(robo.ps, "abrir_link", lambda d, link: abertos.append(link) or setattr(d, "atual", "player"))
    return abertos


def _passos_do_proprio():
    return [(processo, resultado) for _m, processo, resultado, _d, _o in robo.registro_processos.sequencia(
        "shopee_video", "próprio post:", "2000-01-01 00:00:00")]


def test_post_antigo_escolhido_nos_30_dias_e_no_maximo_1_vez_por_semana():
    # Escolha do Rafael (P148 2): 1 post antigo por dia, dos últimos 30 dias, cada um no máximo
    # 1 vez por semana, contando o comentário de depois do post.
    agora = momento("2026-11-10 20:00")
    novo = {"link_post": "https://exemplo.com/a", "postado_em": "2026-11-08 10:00:00"}
    velho = {"link_post": "https://exemplo.com/b", "postado_em": "2026-10-28 10:00:00"}
    fora = {"link_post": "https://exemplo.com/c", "postado_em": "2026-10-05 10:00:00"}
    sem_link = {"link_post": "", "postado_em": "2026-11-09 10:00:00"}
    postados = [velho, novo, fora, sem_link]
    assert it.escolher_post_antigo(postados, agora) is novo              # o mais novo dos nunca comentados
    it.guardar(it.marca_do_post(novo["link_post"]), it.TIPO_DO_POST, "comentado", momento("2026-11-08 10:05"))
    assert it.escolher_post_antigo(postados, agora) is velho
    it.guardar(it.marca_do_post(velho["link_post"]), it.TIPO_DO_ANTIGO, "comentado", momento("2026-11-05 20:00"))
    assert it.escolher_post_antigo(postados, agora) is None              # os dois comentados há menos de 7 dias
    assert it.escolher_post_antigo(postados, momento("2026-11-12 20:30")) is velho


def test_comentario_do_proprio_video_pede_de_novo_quando_repete_e_vai_sem_hashtag(monkeypatch):
    import api_gemini
    pedidos, respostas = [], iter(["Corre que vale a pena!", "Esse é achado! Está nos produtos do vídeo",
                                   "Corre que vale a pena!", "corre que vale a pena"])

    async def gerar(prompt):
        pedidos.append(prompt)
        return next(respostas)

    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", gerar)
    ja = ["Corre que vale a pena!"]
    assert asyncio.run(it.gerar_proprio("Vestido", TITULO_DO_POST, ja)) == "Esse é achado! Está nos produtos do vídeo"
    assert "Corre que vale a pena!" in pedidos[0] and "sem hashtags" in pedidos[0] and len(pedidos) == 2
    assert asyncio.run(it.gerar_proprio("Vestido", TITULO_DO_POST, ja)) is None   # repetido nas duas vezes


def test_depois_do_post_curte_o_video_comenta_e_curte_o_comentario(avisos, ia_do_proprio, pelo_link):
    ident = _postado()
    app = CelularDoPost(comentarios=[TITULO_DO_POST])                     # a legenda do vídeo, com o selo
    assert robo.comentar_depois_do_post(app, ident, momento("2026-11-01 10:01")) == "comentado"
    texto = "Esse vale muito a pena! 1"
    assert pelo_link == [LINK_DO_POST] and app.curtido
    assert app.comentarios[0] == texto and texto in app.curtidos_no_painel
    # A IA recebe o que o Rafael já tem no vídeo, e o texto fica no post para o próximo não repetir.
    assert ia_do_proprio == [[TITULO_DO_POST]]
    assert robo.pegar(ident)["comentarios_proprios"] == [texto]
    assert any(texto in aviso and "curti o vídeo e o comentário" in aviso for aviso in avisos)
    assert it.situacao(it.marca_do_post(LINK_DO_POST), it.TIPO_DO_POST)["resultado"] == "comentado"
    assert {("próprio post: curtir o vídeo", "curtido"), ("próprio post: comentar", "comentado"),
            ("próprio post: curtir o comentário", "curtido")} <= set(_passos_do_proprio())


class CelularQueNaoCurteOComentario(CelularDoPost):
    """O coração do comentário não pega: o toque cai, e o comentário continua sem a curtida."""

    def click(self, x, y):
        import postador_shopee_video as ps
        textos = [el["texto"] or el["descricao"] for el in ps.elementos(self.dump_hierarchy())
                  if ps._dentro((x, y), el["caixa"])]
        if self.atual == "painel" and "button comment like" in textos:
            self.toques.append("button comment like")
            return
        super().click(x, y)


class CelularQueSoMostraONumero(CelularDoPost):
    """
    Como no Motorola (casos de 06/11): curtido, o coração do comentário do próprio Rafael não
    muda de descrição nem traz o "Curtido pelo criador"; só ganha o número de curtidas.
    """

    def dump_hierarchy(self):
        if self.atual not in ("painel", "escrevendo"):
            return super().dump_hierarchy()
        feitos = [_comentario("Loja Rafa", texto, 1250 + 250 * k, criador=True,
                              curtidas=int(texto in self.curtidos_no_painel))
                  for k, texto in enumerate(self.comentarios)]
        return _painel(*feitos, campo="" if self.atual == "escrevendo" else None)


def test_curtida_do_proprio_comentario_se_confirma_pelo_numero_do_coracao(avisos, ia_do_proprio, pelo_link):
    # Casos de 06/11: as 3 curtidas no próprio comentário saíram (o coração vermelho com o "1"), mas
    # ficaram "não confirmado": o robô só olhava o "Curtido pelo criador" e a descrição do coração.
    ident = _postado()
    app = CelularQueSoMostraONumero(comentarios=[TITULO_DO_POST])
    assert robo.comentar_depois_do_post(app, ident, momento("2026-11-01 10:01")) == "comentado"
    assert ("próprio post: curtir o comentário", "curtido") in set(_passos_do_proprio())
    assert app.toques.count("button comment like") == 1                     # um toque só: não descurte


def test_numero_de_curtidas_do_coracao():
    assert [it.numero_de_curtidas(t) for t in ("1", "12", "1.234", "1,2 mil", "", "Responder")] == [1, 12, 1234, 1200, 0, 0]
    painel = it.comentarios_do_painel(_xml(*_painel(_comentario("Ana", "Lindo!", 1250, curtidas=3))))
    assert painel[0]["curtidas"] == 3 and painel[0]["texto"] == "Lindo!"


def test_curtida_do_comentario_que_nao_se_confirma_guarda_o_caso(avisos, ia_do_proprio, pelo_link, monkeypatch):
    # Checkup de 05/11: no post antigo, a curtida no próprio comentário ficou "não confirmado", sem
    # caso guardado. Sem a tela, não se sabe se o toque não pegou ou se a curtida não aparece.
    casos = []
    monkeypatch.setattr(robo.casos_robo, "guardar",
                        lambda d, acao, resultado, motivo, *a, **k: casos.append((acao, resultado, motivo, a[2]["id"])))
    ident = _postado()
    app = CelularQueNaoCurteOComentario(comentarios=[TITULO_DO_POST])
    assert robo.comentar_depois_do_post(app, ident, momento("2026-11-01 10:01")) == "comentado"
    assert ("próprio post: curtir o comentário", "não confirmado") in set(_passos_do_proprio())
    assert casos == [("comentar_post", "curtida não confirmada",
                      "a curtida no comentário do próprio post não se confirmou (não confirmado)", ident)]


def test_video_em_analise_volta_a_cada_30_min_e_na_3a_vez_o_comentario_vai_ao_rafael(avisos, ia_do_proprio,
                                                                                    pelo_link):
    ident = _postado()
    app = CelularDoPost(em_analise=True)
    assert robo.comentar_depois_do_post(app, ident, momento("2026-11-01 10:01")) == "parou"
    assert app.comentarios == [] and avisos == [] and ia_do_proprio == []
    assert robo.comentario_do_post_pendente(momento("2026-11-01 10:20")) is None     # antes dos 30 min
    assert robo.comentario_do_post_pendente(momento("2026-11-01 10:32"))["id"] == ident
    robo.tentar_o_comentario_do_post(app, robo.pegar(ident), momento("2026-11-01 10:32"))
    assert avisos == []
    robo.tentar_o_comentario_do_post(app, robo.pegar(ident), momento("2026-11-01 11:03"))
    # Na 3ª, desiste: o comentário do Gem vai para ele comentar à mão, e o post não volta mais.
    assert "não consegui comentar" in avisos[-3] and "em análise" in avisos[-3]
    assert avisos[-2:] == [robo.ps.AVISO_COMENTARIO, "Amei! #achadinhos"]
    assert robo.comentario_do_post_pendente(momento("2026-11-01 12:00")) is None
    assert ("próprio post: comentar", "desistiu") in _passos_do_proprio()


def test_coracao_ja_curtido_nao_e_tocado_e_texto_repetido_para_antes_de_escrever(monkeypatch, avisos, pelo_link):
    async def so_repetido(produto="", titulo="", anteriores=()):
        return None

    monkeypatch.setattr(it, "gerar_proprio", so_repetido)
    app = CelularDoPost(comentarios=["Corre que vale a pena!"], curtido=True)
    with pytest.raises(robo.Parada, match="IA não escreveu"):
        robo.comentar_no_post(app, robo.pegar(_postado()))
    assert app.curtido and not {"like icon", "unlike icon"} & set(app.toques)
    assert app.comentarios == ["Corre que vale a pena!"]                    # nada escrito


def test_post_antigo_sai_durante_o_dia_uma_vez_por_dia(monkeypatch, avisos, ia_do_proprio, pelo_link):
    # Escolhas do Rafael (P148 2 e P161 1): 1 por dia, a qualquer hora das 8h às 22h.
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    monkeypatch.setattr(robo, "respostas_pendentes", lambda agora=None: False)
    monkeypatch.setattr(robo, "consumir_horarios", lambda config, agora=None: False)
    config = {**robo.PADRAO, "robo_pausado": False}
    robo.db.salvar_config(robo.CHAVE_CONFIG, config)
    ident = _postado(quando="2026-10-28 10:00:00")
    agora = momento("2026-11-01 20:05")
    robo.gravar_estado(treino_semana=robo.semana(agora))
    assert robo.o_que_fazer(config, agora) == ("post_antigo", ident)
    assert robo.post_antigo_pendente(momento("2026-11-01 15:00"))["id"] == ident
    # Fora do dia, não.
    assert robo.post_antigo_pendente(momento("2026-11-01 07:59")) is None
    assert robo.post_antigo_pendente(momento("2026-11-01 22:00")) is None
    app = CelularDoPost()
    assert robo._agir(app, "post_antigo", ident, False, config, agora) == "post antigo: comentado e curtido"
    assert app.curtido and app.comentarios == ["Esse vale muito a pena! 1"]
    assert it.antigos_hoje(agora) == 1 and robo.post_antigo_pendente(momento("2026-11-01 20:40")) is None
    # No dia seguinte, o mesmo post não volta antes de 7 dias.
    assert robo.post_antigo_pendente(momento("2026-11-02 20:05")) is None
    assert robo.post_antigo_pendente(momento("2026-11-08 20:10"))["id"] == ident


def test_post_antigo_removido_sai_da_escolha_e_o_proximo_ganha_o_comentario(monkeypatch, avisos, ia_do_proprio,
                                                                            pelo_link):
    # 09/11, 08:22: o link do post antigo abriu "Este vídeo foi removido", e nada marcava o post:
    # ele seria escolhido de novo em toda tentativa, todo dia. Marcado, a escolha passa ao próximo.
    monkeypatch.setattr(robo, "saude_do_dia_pendente", lambda agora=None: False)
    monkeypatch.setattr(robo, "respostas_pendentes", lambda agora=None: False)
    monkeypatch.setattr(robo, "consumir_horarios", lambda config, agora=None: False)
    config = {**robo.PADRAO, "robo_pausado": False}
    robo.db.salvar_config(robo.CHAVE_CONFIG, config)
    removido = _postado(link="https://exemplo.com/removido", quando="2026-10-28 10:00:00")
    outro = _postado(link="https://exemplo.com/outro", quando="2026-10-27 10:00:00")
    agora = momento("2026-11-01 20:05")
    robo.gravar_estado(treino_semana=robo.semana(agora))
    assert robo.post_antigo_pendente(agora)["id"] == removido      # o mais novo dos nunca comentados
    with pytest.raises(robo.Parada) as parada:
        robo.comentar_post_antigo(CelularDoPost(removido=True), robo.pegar(removido), agora)
    assert parada.value.motivo == robo.MOTIVO_DO_POST_REMOVIDO
    assert it.resultado_de(it.marca_do_post("https://exemplo.com/removido"), it.TIPO_DO_REMOVIDO) == "removido"
    assert robo.post_antigo_pendente(momento("2026-11-01 20:40"))["id"] == outro
    assert robo.post_antigo_pendente(momento("2026-11-09 20:40"))["id"] == outro


def test_erro_no_comentario_nunca_desfaz_o_post_e_o_aviso_diz_so_a_curtida_que_saiu(monkeypatch, avisos):
    # O post já foi ao ar: um erro no comentário de depois dele não pode virar "o post não saiu".
    def quebra(d, rascunho, agora=None):
        raise RuntimeError("banco travado")

    monkeypatch.setattr(robo, "tentar_o_comentario_do_post", quebra)
    assert robo.comentar_depois_do_post(CelularDoPost(), _postado()) == "erro"
    aviso = robo._aviso_do_comentario("comentado", "Corre que vale!", ("não confirmado", "curtido"))
    assert "curti o comentário" in aviso and "curti o vídeo" not in aviso and aviso.endswith("Corre que vale!")
    assert "não apareceu na lista" in robo._aviso_do_comentario("não confirmado", "Oi", ("curtido", ""))

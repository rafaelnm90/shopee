"""api_shopee: o link de afiliado sai para o produto, mesmo quando o redirecionamento para fora dele."""
import json

import api_shopee
import inventario
from conftest import rodar

CURTO = "https://s.shopee.com.br/gO7p0x2tU"
PRODUTO = "https://shopee.com.br/Jogo-de-Panelas-Cacarolas-10-Pecas-i.123456.7890123"
CATEGORIA = "https://shopee.com.br/Panelas-cat.11059983.11060094.11060104"


def test_produto_do_link_acha_o_produto_em_cada_formato():
    canonico = "https://shopee.com.br/product/123456/7890123"
    assert api_shopee.produto_do_link(PRODUTO + "?sp_atk=x&xptdk=y") == canonico
    assert api_shopee.produto_do_link("https://shopee.com.br/product/123456/7890123?utm=a") == canonico
    assert api_shopee.produto_do_link("https://shopee.com.br/universal-link/product/123456/7890123") == canonico
    escondido = "https://shopee.com.br/an_redir?origin_link=https%3A%2F%2Fshopee.com.br%2Fproduct%2F123456%2F7890123&affiliate_id=9"
    assert api_shopee.produto_do_link(escondido) == canonico
    assert api_shopee.produto_do_link("https://shopee.com.br/x?shopid=123456&itemid=7890123") == canonico
    for sem_produto in (CATEGORIA, "https://shopee.com.br/search?keyword=Panelas", CURTO, "", None):
        assert api_shopee.produto_do_link(sem_produto) is None, sem_produto


def test_tipo_de_link_numa_palavra():
    assert api_shopee.tipo_de_link(PRODUTO) == "produto"
    assert api_shopee.tipo_de_link(CATEGORIA) == "categoria"
    assert api_shopee.tipo_de_link("https://shopee.com.br/search?keyword=Panelas") == "busca"
    assert api_shopee.tipo_de_link(CURTO) == "link curto"
    assert api_shopee.tipo_de_link("https://br.shp.ee/abc") == "link curto"
    assert api_shopee.tipo_de_link("https://shopee.com.br/an_redir?x=1") == "redirecionador de afiliado"
    assert api_shopee.tipo_de_link("https://shopee.com.br/buyer/login?next=x") == "login ou verificação"
    assert api_shopee.tipo_de_link("https://shopee.com.br/") == "página inicial"


def _caminho(monkeypatch, caminho):
    async def seguir(link, saltos=10):
        return [link] + caminho
    monkeypatch.setattr(api_shopee, "seguir_link", seguir)


def test_redirecionamento_que_termina_na_categoria_ainda_converte_o_produto(monkeypatch):
    # O caso do vídeo: o post de origem abre o produto, mas o servidor termina na
    # categoria "Panelas"; o link de afiliado tem de sair para o produto.
    _caminho(monkeypatch, [PRODUTO + "?sp_atk=x", CATEGORIA])
    assert rodar(api_shopee.link_para_converter(CURTO)) == PRODUTO


def test_produto_escondido_no_redirecionador_de_afiliado(monkeypatch):
    escondido = "https://shopee.com.br/an_redir?origin_link=https%3A%2F%2Fshopee.com.br%2Fproduct%2F1%2F2&affiliate_id=9"
    _caminho(monkeypatch, [escondido, CATEGORIA])
    assert rodar(api_shopee.link_para_converter(CURTO)) == "https://shopee.com.br/product/1/2"


def test_sem_produto_no_caminho_fica_a_ultima_pagina_e_avisa(monkeypatch):
    avisos = []
    monkeypatch.setattr(api_shopee.logger, "warning", avisos.append)
    _caminho(monkeypatch, [CATEGORIA + "?x=1"])
    assert rodar(api_shopee.link_para_converter(CURTO)) == CATEGORIA
    assert avisos == ["⚠️ [API Shopee] Link sem produto: termina em categoria."]   # sem o link no log


def test_link_que_nao_e_curto_vai_como_veio(monkeypatch):
    def nao_seguir(*a, **k):
        raise AssertionError("não devia seguir")
    monkeypatch.setattr(api_shopee, "seguir_link", nao_seguir)
    assert rodar(api_shopee.link_para_converter(PRODUTO + "?a=1")) == PRODUTO + "?a=1"


class _Resposta:
    def __init__(self, status=200, local=None, corpo=None):
        self.status, self.headers, self._corpo = status, ({"Location": local} if local else {}), corpo

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._corpo


class _Sessao:
    """aiohttp.ClientSession falso: responde os GETs em ordem e guarda o que foi postado."""

    def __init__(self, gets=(), corpo_post=None):
        self.gets, self.corpo_post, self.postados, self.pedidos = list(gets), corpo_post, [], []

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, url, allow_redirects=True):
        self.pedidos.append((url, allow_redirects))
        resposta = self.gets.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    def post(self, url, headers=None, data=None):
        self.postados.append(json.loads(data))
        return _Resposta(200, corpo=self.corpo_post)


def test_seguir_link_guarda_cada_salto_e_junta_endereco_relativo(monkeypatch):
    sessao = _Sessao(gets=[_Resposta(302, PRODUTO + "?sp_atk=x"), _Resposta(301, "/Panelas-cat.11059983.11060094"),
                           _Resposta(200)])
    monkeypatch.setattr(api_shopee.aiohttp, "ClientSession", sessao)
    caminho = rodar(api_shopee.seguir_link(CURTO))
    assert caminho == [CURTO, PRODUTO + "?sp_atk=x", "https://shopee.com.br/Panelas-cat.11059983.11060094"]
    assert all(permite is False for _, permite in sessao.pedidos)           # um salto de cada vez


def test_seguir_link_com_erro_de_rede_devolve_o_que_andou(monkeypatch):
    sessao = _Sessao(gets=[_Resposta(302, PRODUTO), OSError("caiu")])
    monkeypatch.setattr(api_shopee.aiohttp, "ClientSession", sessao)
    assert rodar(api_shopee.seguir_link(CURTO)) == [CURTO, PRODUTO]


def test_converter_manda_o_produto_para_a_api_e_nao_a_categoria(monkeypatch):
    sessao = _Sessao(gets=[_Resposta(302, PRODUTO + "?sp_atk=x"), _Resposta(302, CATEGORIA), _Resposta(200)],
                     corpo_post={"data": {"generateShortLink": {"shortLink": "https://s.shopee.com.br/novo"}}})
    monkeypatch.setattr(api_shopee.aiohttp, "ClientSession", sessao)
    monkeypatch.setattr(api_shopee, "SHOPEE_APP_ID", "1")
    monkeypatch.setattr(api_shopee, "SHOPEE_APP_SECRET", "2")
    assert rodar(api_shopee.converter_link_shopee(CURTO, "espiao")) == "https://s.shopee.com.br/novo"
    assert sessao.postados[0]["variables"]["originUrl"] == PRODUTO


def test_inventario_mostra_so_o_tipo_de_cada_salto(bm, monkeypatch, capsys):
    bm.db.salvar_config("fila_clonagem", {"fila": [
        {"id": "a", "link_original": "https://s.shopee.com.br/segredo1"},
        {"id": "b", "link_original": "https://s.shopee.com.br/segredo2"},
    ]})
    caminhos = {"https://s.shopee.com.br/segredo1": [PRODUTO + "?segredo3", CATEGORIA],
                "https://s.shopee.com.br/segredo2": [CATEGORIA]}

    async def seguir(link, saltos=10):
        return [link] + caminhos[link]

    monkeypatch.setattr(api_shopee, "seguir_link", seguir)
    inventario.links_do_espiao()
    saida = capsys.readouterr().out
    assert "1. link curto → produto → categoria | produto no caminho: sim" in saida
    assert "      shopee.com.br/<nome>-i.#.# + 1 outro(s)" not in saida                 # sem espaço sobrando
    assert "      shopee.com.br/<nome>-i.#.# ? +1 outro(s)" in saida                   # o parâmetro só é contado
    assert "      shopee.com.br/<nome>-cat.#" in saida
    assert "2. link curto → categoria | produto no caminho: NÃO" in saida
    assert "1 parou fora do produto, mas com o produto no meio do caminho; 1 sem produto" in saida
    assert "segredo" not in saida and "https://" not in saida               # nenhum link inteiro


def test_forma_do_link_sem_nada_que_identifique_produto_ou_loja():
    assert inventario.forma_do_link("https://shopee.com.br/opaanlp/123456789/22334455667?gads_t_sig=x&utm_source=an_1") \
        == "shopee.com.br/opaanlp/#9/#11 ?gads_t_sig,utm_source"
    assert inventario.forma_do_link(PRODUTO + "?sp_atk=1") == "shopee.com.br/<nome>-i.#.# ?sp_atk"
    assert inventario.forma_do_link("https://shopee.com.br/x?shopid=3&itemid=2&catid=1") \
        == "shopee.com.br/<texto> ?catid,itemid,shopid"
    desenho = inventario.forma_do_link("https://shopee.com.br/lojadamaria/Panela-Bonita?maria=1&telefone=5511")
    assert desenho == "shopee.com.br/<texto>/<texto> ? +2 outro(s)"
    assert "maria" not in desenho and "5511" not in desenho and "Panela" not in desenho


def test_inventario_conta_sinais_de_produto_na_pagina_do_video(bm, monkeypatch, capsys):
    video = "https://sv.shopee.com.br/share-video/abcSEGREDO?uls_trackid=x&nome=maria"
    bm.db.salvar_config("fila_clonagem", {"fila": [{"id": "a", "link_original": "https://s.shopee.com.br/segredo1"}]})

    async def seguir(link, saltos=10):
        return [link, "https://shopee.com.br/universal-link?redir=x&uls_trackid=y", video]

    paginas = []

    async def pagina(url, navegador):
        paginas.append(url)
        return "status 200, 10 KB; sinais de produto: -i. 0, /product/ 0, itemid 2, shopid 2"

    monkeypatch.setattr(api_shopee, "seguir_link", seguir)
    monkeypatch.setattr(inventario, "produto_na_pagina", pagina)
    inventario.links_do_espiao()
    saida = capsys.readouterr().out
    assert "      sv.shopee.com.br/share-video/<texto> ?uls_trackid +1 outro(s)" in saida
    assert "página do vídeo (computador): status 200" in saida and "página do vídeo (celular)" in saida
    assert paginas == [video, video]                                       # abre a página inteira
    assert "segredo" not in saida.lower() and "maria" not in saida and "https://" not in saida


def test_sinais_de_produto_contados_na_pagina(monkeypatch):
    html = ('<a href="/Panela-i.123456789.22334455667">x</a> {"itemid": 22334455667, "shopid": 123456789} '
            '{"item_id":"22334455668","shop_id":"123456789"}')

    class Resp:
        status = 200

        class content:
            @staticmethod
            async def read(n):
                return html.encode()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class Sessao:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def get(self, url, allow_redirects=True):
            return Resp()

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", Sessao)
    resumo = rodar(inventario.produto_na_pagina("https://sv.shopee.com.br/x", inventario.CELULAR))
    assert resumo.startswith("status 200") and "-i. 1" in resumo and "/product/ 0" in resumo
    assert "itemid 2" in resumo and "shopid 2" in resumo


def test_parametros_mascarados_mostram_so_nome_e_tamanho():
    url = "https://sv.shopee.com.br/share-video/x?item_id=22334455667&shop_id=123456789&from=feed&Tok3n=abc&uls_trackid=zz"
    assert inventario.parametros_mascarados(url) == \
        "from=<texto>, item_id=#11, shop_id=#9, uls_trackid=<texto> +1 outro(s)"
    assert inventario.parametros_mascarados("https://sv.shopee.com.br/x") == "nenhum"


def test_inventario_pergunta_a_api_pelo_produto_do_opaanlp(bm, monkeypatch, capsys):
    bm.db.salvar_config("fila_clonagem", {"fila": [{"id": "a", "link_original": "https://s.shopee.com.br/segredo1"}]})

    async def seguir(link, saltos=10):
        return [link, "https://shopee.com.br/opaanlp/123456789/22334455667?utm_source=x"]

    perguntas = []

    async def api(loja, item):
        perguntas.append((loja, item))
        return "achou: shopee.com.br/product/#9/#11" if loja == "123456789" else "não achou"

    monkeypatch.setattr(api_shopee, "seguir_link", seguir)
    monkeypatch.setattr(inventario, "produto_pela_api", api)
    inventario.links_do_espiao()
    saida = capsys.readouterr().out
    assert "API de afiliado, loja/item: achou: shopee.com.br/product/#9/#11 | invertido: não achou" in saida
    assert perguntas == [("123456789", "22334455667"), ("22334455667", "123456789")]
    assert "123456789" not in saida and "segredo" not in saida

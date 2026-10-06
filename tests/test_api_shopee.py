"""api_shopee: o link de afiliado sai para o produto, mesmo quando o redirecionamento para fora dele."""
import json

import pytest

import api_shopee
import inventario
from conftest import rodar


@pytest.fixture(autouse=True)
def fila_do_espelhador_na_pasta_do_teste(monkeypatch, tmp_path):
    monkeypatch.setattr(inventario, "PASTA", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def sem_espera_entre_tentativas(monkeypatch):
    pausas = []

    async def dormir(segundos):
        pausas.append(segundos)

    monkeypatch.setattr(api_shopee.asyncio, "sleep", dormir)
    return pausas

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

    async def como(link, navegador, saltos=10):
        assert navegador is inventario.CELULAR
        return [link, "https://shopee.com.br/Panela-i.123456789.22334455667?x=1"]

    monkeypatch.setattr(api_shopee, "seguir_link", seguir)
    monkeypatch.setattr(inventario, "produto_na_pagina", pagina)
    monkeypatch.setattr(inventario, "seguir_como", como)
    inventario.links_do_espiao()
    saida = capsys.readouterr().out
    assert "      sv.shopee.com.br/share-video/<texto> ?uls_trackid +1 outro(s)" in saida
    assert "página do vídeo (computador): status 200" in saida and "página do vídeo (celular)" in saida
    assert paginas == [video, video]                                       # abre a página inteira
    assert "      como celular: shopee.com.br/<nome>-i.#.# ? +1 outro(s)" in saida
    assert "      parâmetros de shopee.com.br/universal-link: redir=<texto>, uls_trackid=<texto>" in saida
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
    app = "https://shopee.com.br/universal-link?redir=https%3A%2F%2Fsv.shopee.com.br%2Fshare-video%2Fabc&deepLink=" \
          "shopee%3A%2F%2Fproduct%2F123456789%2F22334455667&itemId=22334455667"
    assert inventario.parametros_mascarados(app) == \
        "deepLink=[product/#9/#11], itemId=#11, redir=[sv.shopee.com.br/share-video/<texto>]"
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


def test_share_obj_mostra_so_a_estrutura():
    import base64
    obj = {"item_id": 22334455667, "shop_id": "123456789", "nome": "Panela da Maria", "lista": [{"x": 1}]}
    cod = base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    desenho = inventario.estrutura_do_share_obj(f"https://sv.shopee.com.br/share-video/a?share_obj={cod}")
    assert desenho == "base64 → JSON {item_id: #11, shop_id: #9, nome: <texto>, lista: [1× {x: #1}]}"
    assert "Maria" not in desenho and "22334455667" not in desenho
    binario = base64.b64encode(b"\x01\x02 22334455667 \xff").decode()
    assert "não é JSON; números longos com [11] dígitos" in \
        inventario.estrutura_do_share_obj(f"https://sv.shopee.com.br/x?share_obj={binario}")
    assert inventario.estrutura_do_share_obj("https://sv.shopee.com.br/x") == "sem share_obj"


def test_conversao_de_teste_mostra_por_onde_o_link_gerado_leva(monkeypatch):
    pedidos = []

    async def api(consulta, variaveis=None):
        pedidos.append(variaveis)
        return {"data": {"generateShortLink": {"shortLink": "https://s.shopee.com.br/teste"}}}

    async def seguir(link, saltos=10):
        return [link, PRODUTO + "?utm_source=x"]

    monkeypatch.setattr(inventario, "_consultar_api", api)
    monkeypatch.setattr(api_shopee, "seguir_link", seguir)
    assert rodar(inventario.conversao_de_teste(PRODUTO)) == "shopee.com.br/<nome>-i.#.# ?utm_source"
    assert pedidos == [{"originUrl": PRODUTO, "subIds": ["diagnostico"]}]


def test_testes_de_conversao_por_tipo_de_link(monkeypatch, capsys):
    origens = []

    async def conversao(origem):
        origens.append(origem)
        return "shopee.com.br/<nome>-i.#.#"

    monkeypatch.setattr(inventario, "conversao_de_teste", conversao)
    video = "https://sv.shopee.com.br/share-video/abc?share_obj=x&pid=y"
    universal = "https://shopee.com.br/universal-link?redir=z"
    opaanlp = "https://shopee.com.br/opaanlp/123456789/22334455667?utm_source=x"
    inventario.testes_de_conversao([[CURTO, universal, video], [CURTO, opaanlp]])
    saida = capsys.readouterr().out
    assert origens == ["https://sv.shopee.com.br/share-video/abc", video, universal,
                       "https://shopee.com.br/opaanlp/123456789/22334455667",
                       "https://shopee.com.br/product/123456789/22334455667"]
    for rotulo in ("vídeo cortado (como é hoje)", "vídeo inteiro", "universal-link inteiro",
                   "opaanlp cortado", "produto loja/item (como é hoje)"):
        assert f"      {rotulo}: shopee.com.br/<nome>-i.#.#" in saida
    assert "123456789" not in saida and "https://" not in saida


VIDEO = "https://sv.shopee.com.br/share-video/abc?jumpType=pdp&pid=x&share_obj=y&shareUserId=1234567890"


def test_link_de_video_vai_inteiro_para_a_api(monkeypatch):
    # O app abre o produto do vídeo guiado pelos parâmetros (jumpType...); cortados, abre a categoria.
    avisos = []
    monkeypatch.setattr(api_shopee.logger, "warning", avisos.append)
    _caminho(monkeypatch, ["https://shopee.com.br/universal-link?redir=x&deep_and_web=1", VIDEO])
    assert rodar(api_shopee.link_para_converter(CURTO)) == VIDEO
    assert avisos == []
    assert api_shopee.tipo_de_link(VIDEO) == "vídeo da Shopee Vídeo"


OPAANLP = "https://shopee.com.br/opaanlp/123456789/22334455667"
CANONICO = "https://shopee.com.br/product/123456789/22334455667"


def test_pagina_de_afiliado_de_outra_pessoa_vira_o_link_padrao_do_produto(monkeypatch):
    # Vídeo do Rafael de 05/10: o post de origem abria o produto, e o link gerado da página
    # de afiliado (opaanlp) cortada abria no app uma busca ("Mochilas").
    assert api_shopee.produto_do_link(OPAANLP + "?utm_source=x") == CANONICO
    assert api_shopee.tipo_de_link(OPAANLP) == "produto"
    _caminho(monkeypatch, [OPAANLP + "?utm_source=x&utm_campaign=y"])
    assert rodar(api_shopee.link_para_converter(CURTO)) == CANONICO


def test_converter_manda_o_link_padrao_do_produto_da_pagina_de_afiliado(monkeypatch):
    sessao = _Sessao(gets=[_Resposta(302, OPAANLP + "?utm_source=x"), _Resposta(200)],
                     corpo_post={"data": {"generateShortLink": {"shortLink": "https://s.shopee.com.br/novo"}}})
    monkeypatch.setattr(api_shopee.aiohttp, "ClientSession", sessao)
    monkeypatch.setattr(api_shopee, "SHOPEE_APP_ID", "1")
    monkeypatch.setattr(api_shopee, "SHOPEE_APP_SECRET", "2")
    assert rodar(api_shopee.converter_link_shopee(CURTO, "espiao")) == "https://s.shopee.com.br/novo"
    assert sessao.postados[0]["variables"]["originUrl"] == CANONICO


def test_converter_manda_o_video_inteiro(monkeypatch):
    sessao = _Sessao(gets=[_Resposta(302, "https://shopee.com.br/universal-link?redir=x"), _Resposta(302, VIDEO),
                           _Resposta(200)],
                     corpo_post={"data": {"generateShortLink": {"shortLink": "https://s.shopee.com.br/novo"}}})
    monkeypatch.setattr(api_shopee.aiohttp, "ClientSession", sessao)
    monkeypatch.setattr(api_shopee, "SHOPEE_APP_ID", "1")
    monkeypatch.setattr(api_shopee, "SHOPEE_APP_SECRET", "2")
    assert rodar(api_shopee.converter_link_shopee(CURTO, "espiao")) == "https://s.shopee.com.br/novo"
    assert sessao.postados[0]["variables"]["originUrl"] == VIDEO


def _fila_com_video(bm, monkeypatch):
    bm.db.salvar_config("fila_clonagem", {"fila": [
        {"id": "a", "link_original": "https://s.shopee.com.br/video_velho"},
        {"id": "b", "link_original": "https://s.shopee.com.br/produto_velho"},
        {"id": "c", "link_original": "https://s.shopee.com.br/produto_novo"},
        {"id": "d", "link_original": "https://s.shopee.com.br/categoria"},
        {"id": "e", "link_original": "https://s.shopee.com.br/video_novo"},
    ]})

    async def seguir(link, saltos=10):
        if "video" in link:
            return [link, VIDEO]
        return [link, CATEGORIA] if "categoria" in link else [link, OPAANLP + "?utm_source=x"]

    monkeypatch.setattr(api_shopee, "seguir_link", seguir)


def test_link_de_teste_vai_no_privado_com_o_video_e_o_produto_mais_recentes(bm, monkeypatch, capsys):
    import avisar_rafael
    _fila_com_video(bm, monkeypatch)
    convertidos, mensagens = [], []

    async def converter(link, sub_id="geral", **k):
        convertidos.append((link, sub_id))
        return "https://s.shopee.com.br/teste_" + link.rsplit("/", 1)[1]

    monkeypatch.setattr(api_shopee, "converter_link_shopee", converter)
    monkeypatch.setattr(avisar_rafael, "mandar_texto", lambda texto: mensagens.append(texto) or True)
    inventario.link_de_teste()
    saida = capsys.readouterr().out
    assert convertidos == [("https://s.shopee.com.br/video_novo", "diagnostico"),
                           ("https://s.shopee.com.br/produto_novo", "diagnostico")]
    assert len(mensagens) == 1
    for trecho in ("teste_video_novo", "video_novo", "teste_produto_novo", "produto_novo", "abre o PRODUTO",
                   "abre o VÍDEO"):
        assert trecho in mensagens[0], trecho
    assert "enviado no privado do Rafael (vídeo e produto)" in saida and "https://" not in saida   # sem links no log


def test_link_de_teste_sem_video_nem_produto_ou_com_conversao_falha(bm, monkeypatch, capsys):
    import avisar_rafael
    monkeypatch.setattr(avisar_rafael, "mandar_texto", lambda texto: pytest_falha())
    bm.db.salvar_config("fila_clonagem", {"fila": [{"id": "d", "link_original": "https://s.shopee.com.br/categoria"}]})

    async def seguir(link, saltos=10):
        return [link, CATEGORIA]

    monkeypatch.setattr(api_shopee, "seguir_link", seguir)
    inventario.link_de_teste()
    assert "nenhum link de vídeo nem de produto" in capsys.readouterr().out

    _fila_com_video(bm, monkeypatch)

    async def falha(link, sub_id="geral", **k):
        return link

    monkeypatch.setattr(api_shopee, "converter_link_shopee", falha)
    inventario.link_de_teste()
    saida = capsys.readouterr().out
    assert "a conversão do vídeo falhou" in saida and "a conversão do produto falhou" in saida


def test_link_de_teste_manda_o_que_converteu_quando_um_falha(bm, monkeypatch, capsys):
    import avisar_rafael
    _fila_com_video(bm, monkeypatch)
    mensagens = []

    async def so_produto(link, sub_id="geral", **k):
        return link if "video" in link else "https://s.shopee.com.br/teste_produto"

    monkeypatch.setattr(api_shopee, "converter_link_shopee", so_produto)
    monkeypatch.setattr(avisar_rafael, "mandar_texto", lambda texto: mensagens.append(texto) or True)
    inventario.link_de_teste()
    saida = capsys.readouterr().out
    assert "teste_produto" in mensagens[0] and "abre o VÍDEO" not in mensagens[0]
    assert "a conversão do vídeo falhou" in saida and "enviado no privado do Rafael (produto)" in saida


def pytest_falha():
    raise AssertionError("não devia mandar mensagem")


# --- Link que sai sem a marcação de afiliado: vai para o erros_logs (/status e monitor) ---

def _registros_sem_conversao():
    import db
    with db.conexao() as con:
        tabela = con.execute("SELECT name FROM sqlite_master WHERE name = 'erros_logs'").fetchone()
        if not tabela:
            return []
        return [linha[0] for linha in con.execute(
            "SELECT erro FROM erros_logs WHERE origem = ?", (api_shopee.ORIGEM_SEM_CONVERSAO,))]


def _api_que_responde(monkeypatch, corpo=None, erro=None):
    sessao = _Sessao(gets=[_Resposta(200)], corpo_post=corpo)
    if erro:
        def post(*a, **k):
            raise erro
        sessao.post = post
    monkeypatch.setattr(api_shopee.aiohttp, "ClientSession", sessao)
    monkeypatch.setattr(api_shopee, "SHOPEE_APP_ID", "1")
    monkeypatch.setattr(api_shopee, "SHOPEE_APP_SECRET", "2")


def test_recusa_da_api_registra_o_link_sem_conversao_sem_mostrar_o_link(monkeypatch):
    recusa = {"errors": [{"message": "error", "extensions": {"code": 10020, "message": "invalid signature"}}]}
    _api_que_responde(monkeypatch, corpo=recusa)
    assert rodar(api_shopee.converter_link_shopee(PRODUTO, "espiao")) == PRODUTO   # o post segue com o original
    registros = _registros_sem_conversao()
    assert len(registros) == 1
    assert "sem a sua marcação" in registros[0] and "subId espiao" in registros[0]
    assert "10020 invalid signature" in registros[0] and "shopee.com.br" not in registros[0]


def test_api_fora_do_ar_e_chaves_ausentes_tambem_registram(monkeypatch):
    _api_que_responde(monkeypatch, erro=OSError("caiu"))
    assert rodar(api_shopee.converter_link_shopee(PRODUTO)) == PRODUTO
    monkeypatch.setattr(api_shopee, "SHOPEE_APP_ID", None)
    assert rodar(api_shopee.converter_link_shopee(PRODUTO)) == PRODUTO
    registros = _registros_sem_conversao()
    assert "sem resposta da API (OSError)" in registros[0] and "sem as chaves de afiliado" in registros[1]


def test_link_do_parceiro_sem_conversao_diz_que_e_do_parceiro(monkeypatch):
    _api_que_responde(monkeypatch, corpo={"data": None})
    rodar(api_shopee.converter_link_shopee(PRODUTO, "parceiro", app_id="9", app_secret="8"))
    assert "sem a marcação do parceiro" in _registros_sem_conversao()[0]


def test_conversao_certa_e_diagnostico_nao_registram(monkeypatch):
    _api_que_responde(monkeypatch, corpo={"data": {"generateShortLink": {"shortLink": "https://s.shopee.com.br/novo"}}})
    assert rodar(api_shopee.converter_link_shopee(PRODUTO)) == "https://s.shopee.com.br/novo"
    _api_que_responde(monkeypatch, corpo={"data": None})
    assert rodar(api_shopee.converter_link_shopee(PRODUTO, "diagnostico", avisar_falha=False)) == PRODUTO
    assert _registros_sem_conversao() == []


def test_status_e_monitor_mostram_os_links_sem_conversao(bm, Msg, monkeypatch):
    from types import SimpleNamespace
    alertas = []

    async def send_message(chat, texto, **k):
        alertas.append(texto)

    monkeypatch.setattr(bm.bot, "send_message", send_message)
    monkeypatch.setattr(bm.subprocess, "run", lambda cmd, **k: SimpleNamespace(stdout=""))
    msg = Msg("/status")
    rodar(bm.comando_status(msg, None))
    assert "Links sem a sua marcação de afiliado (24 h): <b>0</b> ✅" in msg.saidas[-1]
    rodar(bm.monitor_saude())
    assert not any("sem a sua marcação" in a for a in alertas)

    _api_que_responde(monkeypatch, corpo={"data": None})
    rodar(api_shopee.converter_link_shopee(PRODUTO, "espiao"))
    msg = Msg("/status")
    rodar(bm.comando_status(msg, None))
    assert "Links sem a sua marcação de afiliado (24 h): <b>1</b> ⚠️" in msg.saidas[-1]
    assert "[Link sem conversão]" in msg.saidas[-1]
    rodar(bm.monitor_saude())
    assert any("1 link(s) sem a sua marcação de afiliado" in a for a in alertas)
    alertas.clear()
    rodar(bm.monitor_saude())                                              # não repete na hora seguinte
    assert not any("sem a sua marcação" in a for a in alertas)


def test_tenta_tres_vezes_antes_de_desistir_e_acerta_na_segunda(monkeypatch, sem_espera_entre_tentativas):
    respostas = [{"data": None}, {"data": {"generateShortLink": {"shortLink": "https://s.shopee.com.br/novo"}}}]
    _api_que_responde(monkeypatch)
    sessao = api_shopee.aiohttp.ClientSession
    sessao.post = lambda url, headers=None, data=None: _Resposta(200, corpo=respostas.pop(0))
    assert rodar(api_shopee.converter_link_shopee(PRODUTO)) == "https://s.shopee.com.br/novo"
    assert sem_espera_entre_tentativas == [2] and _registros_sem_conversao() == []    # acertou: nada registrado

    tentativas = []

    def sempre_cai(url, headers=None, data=None):
        tentativas.append(json.loads(data))
        raise OSError("caiu")

    sessao.post = sempre_cai
    sem_espera_entre_tentativas.clear()
    assert rodar(api_shopee.converter_link_shopee(PRODUTO)) == PRODUTO
    assert len(tentativas) == 3 and sem_espera_entre_tentativas == [2, 5]
    assert len(_registros_sem_conversao()) == 1                            # um registro por link, não por tentativa


def test_registro_traz_robo_tipo_e_detalhe_no_contexto(monkeypatch):
    import db
    recusa = {"errors": [{"message": "error", "extensions": {"code": 10020, "message": "invalid signature"}}]}
    _api_que_responde(monkeypatch, corpo=recusa)
    rodar(api_shopee.converter_link_shopee(PRODUTO, "espiao"))
    with db.conexao() as con:
        contexto = json.loads(con.execute("SELECT contexto FROM erros_logs").fetchone()[0])
    assert contexto["tipo"] == "recusa" and contexto["detalhe"] == "10020" and contexto["robo"]


def _fila_espelhador(pasta, itens):
    import fila_espelhador
    fila_espelhador.atualizar(lambda dados: dados.update({"fila": itens}))


def test_link_de_teste_manda_tambem_o_proximo_do_espelhador(bm, monkeypatch, capsys, fila_do_espelhador_na_pasta_do_teste):
    import avisar_rafael
    bm.db.salvar_config("fila_clonagem", {"fila": []})
    _fila_espelhador(fila_do_espelhador_na_pasta_do_teste, [
        {"id": "ja_saiu", "processado": True, "link_convertido": "https://s.shopee.com.br/velho_postado"},
        {"id": "antigo", "link_convertido": "https://s.shopee.com.br/guardado_antigo"},
        {"id": "novo", "link_original": "https://s.shopee.com.br/original_novo",
         "link_convertido": "https://s.shopee.com.br/guardado_novo"},
    ])
    convertidos, mensagens = [], []

    async def converter(link, sub_id="geral", **k):
        convertidos.append(link)
        return "https://s.shopee.com.br/renovado"

    monkeypatch.setattr(api_shopee, "converter_link_shopee", converter)
    monkeypatch.setattr(avisar_rafael, "mandar_texto", lambda texto: mensagens.append(texto) or True)
    inventario.link_de_teste()
    saida = capsys.readouterr().out
    assert convertidos == ["https://s.shopee.com.br/original_novo"]      # o pendente mais novo, do original
    assert "Link do Espelhador" in mensagens[0] and "renovado" in mensagens[0] and "guardado_novo" in mensagens[0]
    assert "enviado no privado do Rafael (Espelhador)" in saida and "https://" not in saida


def test_inventario_conta_pendentes_do_espelhador_de_antes_do_conserto(capsys, fila_do_espelhador_na_pasta_do_teste):
    pasta = fila_do_espelhador_na_pasta_do_teste
    _fila_espelhador(pasta, [
        {"id": "a", "nome_rota": "R", "data_captura": "2026-10-04 10:00:00", "link_convertido": "x"},
        {"id": "b", "nome_rota": "R", "data_captura": "2026-10-06 09:00:00", "link_convertido": "x",
         "link_original": "y"},
        {"id": "c", "nome_rota": "R", "processado": True, "data_postagem": "2026-10-05"},
    ])
    (pasta / "espelhos_config.json").write_text(json.dumps({"rotas": [{"nome": "R"}]}), encoding="utf-8")
    inventario.fila_do_espelhador()
    saida = capsys.readouterr().out
    assert "pendentes: 2, capturados antes do conserto do link de produto: 1, sem o link original guardado: 1" in saida

"""video_ia: o teste do vídeo feito por IA (P34) escolhe o modelo mais barato e só mostra números no log público."""
from conftest import inserir

import video_ia


def test_escolhe_o_veo_mais_novo_e_mais_barato():
    nomes = ["veo-2.0-generate-001", "veo-3.1-generate-001", "veo-3.1-fast-generate-001", "veo-3.1-lite-generate-001"]
    assert video_ia.escolher_modelo(nomes) == "veo-3.1-lite-generate-001"
    assert video_ia.escolher_modelo(["veo-3.0-generate-001", "veo-3.0-fast-generate-001"]) == "veo-3.0-fast-generate-001"
    assert video_ia.escolher_modelo(["veo-2.0-generate-001"]) == "veo-2.0-generate-001"
    assert video_ia.escolher_modelo([]) is None
    # Modelo de vídeo com outro nome (a ação de gerar vídeo) entra quando não há Veo.
    assert video_ia.escolher_modelo(["gemini-omni-flash-video"]) == "gemini-omni-flash-video"


class _Modelo:
    def __init__(self, nome, acoes):
        self.name, self.supported_actions = f"models/{nome}", acoes


def test_modelos_de_video_pelo_nome_ou_pela_acao(monkeypatch, capsys):
    modelos = [_Modelo("gemini-2.5-flash", ["generateContent", "countTokens"]),
               _Modelo("veo-3.1-lite-generate-001", ["predictLongRunning"]),
               _Modelo("omni-video", ["predictLongRunning"]), _Modelo("imagen-4", ["predict"])]
    monkeypatch.setattr(video_ia.api_gemini.client_genai.models, "list", lambda: modelos)
    assert video_ia.modelos_de_video() == ["omni-video", "veo-3.1-lite-generate-001"]
    assert video_ia.main(["modelos"]) == 0
    saida = capsys.readouterr().out
    assert "Modelos de vídeo na chave: 2" in saida and "predictLongRunning 2" in saida and "generateContent 1" in saida


def test_teste_manda_o_video_so_no_privado_e_o_log_so_tem_numeros(monkeypatch, capsys):
    mandados = []

    def gerar(modelo, foto, destino):
        with open(destino, "wb") as arquivo:
            arquivo.write(b"video")
        return ""

    async def dimensoes(caminho, timeout=None):
        return 720, 1280

    monkeypatch.setattr(video_ia, "PASTA", "video_ia")
    monkeypatch.setattr(video_ia, "modelos_de_video", lambda: ["veo-3.1-fast-generate-001"])
    monkeypatch.setattr(video_ia, "produto_para_teste", lambda: ("Copo Térmico Inox", b"foto"))
    monkeypatch.setattr(video_ia, "gerar", gerar)
    monkeypatch.setattr(video_ia.videos, "dimensoes", dimensoes)
    monkeypatch.setattr(video_ia.avisar_rafael, "mandar_video",
                        lambda caminho, legenda="": mandados.append(legenda) or True)
    assert video_ia.main(["testar"]) == 0
    saida = capsys.readouterr().out
    assert "720x1280" in saida and "Mandado no privado do Rafael: sim" in saida and "Copo" not in saida
    assert "Copo Térmico Inox" in mandados[0] and "Não foi postado" in mandados[0]


def test_sem_modelo_de_video_ou_sem_foto_o_teste_nao_roda(monkeypatch, capsys):
    monkeypatch.setattr(video_ia, "modelos_de_video", lambda: [])
    assert video_ia.main(["testar"]) == 1
    assert "não enxerga nenhum modelo de vídeo" in capsys.readouterr().out
    monkeypatch.setattr(video_ia, "modelos_de_video", lambda: ["veo-3.1-lite-generate-001"])
    monkeypatch.setattr(video_ia, "produto_para_teste", lambda: None)
    assert video_ia.main(["testar"]) == 1
    assert video_ia.main(["outra"]) == 2


def _produto(item, preco, comissao, nota, vendas=100, nome="Garrafa Térmica Azul"):
    return {"itemId": item, "productName": nome, "priceMin": str(preco), "commissionRate": str(comissao),
            "ratingStar": str(nota), "sales": vendas, "imageUrl": "https://img.exemplo/garrafa.jpg",
            "productLink": f"https://shopee.com.br/product/11/{item}"}


def test_o_erro_da_api_vai_ao_log_sem_numeros():
    erros = [{"message": "Invalid   argument listType for app 123456 0123456789abcdef0123", "extensions": {"code": 10020}}]
    texto = video_ia.erro_da_api(erros)
    assert texto == "código 10.020: Invalid argument listType for app # #"
    assert video_ia.erro_da_api([{}]) == "sem código: sem mensagem"


def test_as_contagens_da_lista_da_sonda():
    # 1: nota e mínimo (R$ 3 por venda); 2: nota sem o mínimo (R$ 1); 3: mínimo sem a nota; 4: as duas, já postado.
    produtos = [_produto(1, 30, 0.10, 4.8), _produto(2, 10, 0.10, 4.9), _produto(3, 100, 0.10, 4.2),
                _produto(4, 300, 0.10, 4.5, vendas=900)]
    linhas = video_ia.contagens_da_lista(produtos, {"4"}, lambda preco, comissao: preco * comissao / 100, 2.0)
    assert linhas[0] == ("   nota 4,5 ou mais: 3 | pagam o mínimo por venda: 3 | as duas coisas: 2 "
                         "(ainda não postados: 1)")
    assert "com a foto: 4 | com o link do produto: 4 | vendas (mediana): 100 | nota (mediana): 4,7" in linhas[1]
    assert linhas[2] == "   preço: até R$ 50: 2 | de R$ 50 a R$ 200: 1 | acima de R$ 200: 1"
    assert linhas[3] == ("   por venda, entre os das duas coisas: de R$ 2 a R$ 5: 1 | de R$ 5 a R$ 15: 0 | "
                         "acima de R$ 15: 1")
    assert video_ia.contagens_da_lista([], set(), lambda p, c: 0, 2.0)[1].endswith("vendas (mediana): - | nota (mediana): -")


def test_a_sonda_dos_produtos_so_mostra_contagens_no_log(monkeypatch, capsys):
    pedidos = []

    async def pedir_lista(argumentos, extra=""):
        pedidos.append((argumentos, extra))
        if "listType: 1" in argumentos:
            return [], "código 10.020: Invalid argument", None
        if "keyword" in argumentos:
            return [_produto(9, 80, 0.10, 4.9)], "", None
        return [_produto(1, 30, 0.10, 4.8), _produto(2, 10, 0.10, 4.9)], "", (True if extra else None)

    async def em_alta(negada_levanta=False):
        # A lista que o robô usa na escolha: 3 produtos, 2 com a nota, 1 deles pagando o mínimo.
        return [_produto(1, 30, 0.10, 4.8), _produto(2, 10, 0.10, 4.9), _produto(3, 90, 0.10, 4.0)]

    monkeypatch.setattr(video_ia, "pedir_lista", pedir_lista)
    monkeypatch.setattr(video_ia.api_shopee, "ofertas_em_alta_shopee", em_alta)
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    video_ia.db.salvar_config("achadinhos_config", {"nichos": [{"nome": "Casa", "keywords": ["organizador secreto", "x"]},
                                                              {"nome": "Vazio", "keywords": []},
                                                              {"nome": "Pet", "keywords": ["coleira rara"]}]})
    assert video_ia.main(["produtos"]) == 0
    saida = capsys.readouterr().out
    assert "== em alta (listType 2): 2 produto(s), 2 diferente(s)" in saida
    assert "== maior comissão (listType 1): a API recusou (código 10.020: Invalid argument)" in saida
    assert "== em alta, com a página informada: 2 produto(s), 2 diferente(s) | tem próxima página: sim" in saida
    assert "em comum com a 1ª lista: 2" in saida
    assert "== Nichos dos Achadinhos: 3 nicho(s), 3 palavra(s)-chave" in saida
    assert "== nicho nº 1, 1ª palavra, por mais vendidos: 1 produto(s)" in saida
    assert "== nicho nº 2, 1ª palavra, por mais vendidos: 1 produto(s)" in saida
    # O que a escolha do robô acharia agora (P234 1), sem a IA: a lista e as contagens da peneira dele.
    assert ("== A escolha do robô agora: os produtos em alta da Shopee: 3 da lista; 2 com a nota; 1 pagam o mínimo; "
            "1 novos") in saida
    # E, dos novos, quantos passam em cada corte do 2º nível (P252 1) e nos três, só pelos links do Espião já
    # seguidos: a sonda não vai à Shopee seguir link nenhum.
    assert ("1 novos; dos novos, 0 com os vendidos, 1 com o preço e 1 com os canais do Espião; 0 no 2º nível "
            "(0 link(s) do Espião sem seguir)") in saida
    # A palavra de busca vai à API, nunca ao log; nem o nome, o link ou a foto do produto.
    assert any('keyword: "organizador secreto", sortType: 2, limit: 50' == argumentos for argumentos, _ in pedidos)
    for privado in ("organizador", "coleira", "Garrafa", "shopee.com.br", "img.exemplo", "Casa", "Pet"):
        assert privado not in saida


def test_a_linha_da_comissao_da_sonda():
    # P297 1: a sonda conta como a API divide a comissão (a parte da Shopee e a do vendedor), só em números, para
    # conferir a conta da comissão do vídeo (api_shopee.comissao_no_video).
    produtos = [{**_produto(1, 30, 0.13, 4.8), "sellerCommissionRate": "0.1", "shopeeCommissionRate": "0.03"},
                {**_produto(2, 30, 0.03, 4.8), "sellerCommissionRate": "0", "shopeeCommissionRate": "0.03"},
                {**_produto(3, 30, 0.07, 4.8), "sellerCommissionRate": "0.03", "shopeeCommissionRate": "0.025"},
                _produto(4, 30, 0.05, 4.8)]                          # sem as partes
    # A parte da Shopee de cada produto, da mais comum para a menos comum: 3% em 2 e 2,5% em 1.
    assert video_ia.contagens_da_comissao(produtos) == (
        "   comissão: com as duas partes: 3 de 4 | a da Shopee: 3% em 2, 2,5% em 1 | com a extra do vendedor: 2 | "
        "a da API é a soma das duas: 2")
    assert video_ia.contagens_da_comissao(produtos[3:]) == (
        "   comissão: com as duas partes: 0 de 1 | a da Shopee: nenhuma | com a extra do vendedor: 0 | "
        "a da API é a soma das duas: 0")
    # Na lista da sonda, é a última linha, e o que pagam por venda é pela comissão do vídeo (R$ 3,45 no 1º).
    linhas = video_ia.contagens_da_lista(produtos[:1], set(), lambda preco, comissao: preco * comissao / 100, 2.0)
    assert linhas[-1].startswith("   comissão: com as duas partes: 1 de 1")
    assert linhas[3] == ("   por venda, entre os das duas coisas: de R$ 2 a R$ 5: 1 | de R$ 5 a R$ 15: 0 | "
                         "acima de R$ 15: 0")

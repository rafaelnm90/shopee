import random

import visualizacoes_shopee_video as vsv


def _imagem(semente, tamanho=(358, 470)):
    from PIL import Image
    gerador = random.Random(semente)
    pequena = Image.new("L", (12, 12))
    pequena.putdata([gerador.randrange(256) for _ in range(144)])
    return pequena.resize(tamanho).convert("RGB")


def test_marca_e_a_mesma_para_a_mesma_capa_e_outra_para_outra():
    caixa = (0, 0, 358, 470)
    marca = vsv.marca_da_capa(_imagem(1), caixa)
    assert len(marca) == 16 and vsv.diferenca(marca, vsv.marca_da_capa(_imagem(1), caixa)) == 0
    assert vsv.diferenca(marca, vsv.marca_da_capa(_imagem(2), caixa)) > vsv.MARCA_PARECIDA
    # O número de visualizações embaixo e o selo Fixado em cima ficam fora da marca: o mesmo
    # vídeo com outro número tem a mesma marca.
    from PIL import ImageDraw
    com_numero = _imagem(1)
    desenho = ImageDraw.Draw(com_numero)
    desenho.rectangle((10, 440, 200, 465), fill="white")
    desenho.rectangle((10, 5, 120, 40), fill="white")
    assert vsv.marca_da_capa(com_numero, caixa) == marca
    # A mesma capa um pouco menor (outra tela) continua parecida.
    menor = _imagem(1, (300, 394))
    assert vsv.diferenca(marca, vsv.marca_da_capa(menor, (0, 0, 300, 394))) <= vsv.MARCA_PARECIDA
    # A capa que ainda não carregou (uma cor só) não tem marca.
    from PIL import Image
    assert vsv.marca_da_capa(Image.new("RGB", (358, 470), (90, 90, 90)), caixa) is None


def test_casar_fica_com_a_marca_mais_parecida_e_desempata_pelo_mais_novo():
    a, b = "0" * 16, "f" * 16
    quase_a = "0" * 15 + "3"
    quadros = [(quase_a, 10), (a, 20), (b, 30), (None, 40), (a, None)]
    procurados = [("novo", a), ("velho", a), ("outro", "0f" * 8)]
    assert vsv.casar(quadros, procurados) == {"novo": 10, "velho": 20}


def test_comparar_usa_a_leitura_mais_perto_de_cada_idade():
    videos = [
        {"postado_em": "2026-10-20 10:00:00", "chamada": "", "marca": "a",
         "vistas": [["2026-10-21 09:00:00", 100], ["2026-10-23 11:00:00", 300]]},
        {"postado_em": "2026-10-20 12:00:00", "chamada": "", "marca": "b",
         "vistas": [["2026-10-21 18:00:00", 120]]},
        {"postado_em": "2026-10-27 10:00:00", "chamada": "1", "marca": "c",
         "vistas": [["2026-10-28 08:00:00", 150], ["2026-10-29 08:00:00", 210]]},
        # Lido só com 2 dias e meio: fica fora da idade de 1 dia, entra na de 3.
        {"postado_em": "2026-10-27 12:00:00", "chamada": "1", "marca": "d",
         "vistas": [["2026-10-30 00:00:00", 400]]},
        # Antes da primeira marca (da medição): não conta como sem marca.
        {"postado_em": "2026-10-19 10:00:00", "chamada": "", "marca": "", "vistas": []},
        {"postado_em": "2026-10-28 10:00:00", "chamada": "1", "marca": "", "vistas": []},
    ]
    medicao = vsv.comparar(videos)
    assert medicao["sem_marca"] == 1
    assert medicao["sem"] == {"videos": 2, "lidos": 2, "idades": {1: (2, 110), 3: (1, 300)}}
    assert medicao["com"] == {"videos": 2, "lidos": 2, "idades": {1: (1, 150), 3: (1, 400)}}
    assert vsv.diferenca_em_porcento(medicao, 1) == 36 and vsv.diferenca_em_porcento(medicao, 3) == 33
    vazio = vsv.comparar([])
    assert vazio["sem_marca"] == 0 and vsv.diferenca_em_porcento(vazio, 1) is None

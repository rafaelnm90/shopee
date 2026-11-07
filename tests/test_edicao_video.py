"""edicao_video e videos.com_foto_e_miniatura: a foto do produto no começo, a miniatura no canto e a seta do Rafael, com o ffmpeg de mentira (e de verdade, quando a máquina tem)."""
import io
import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest

import db
import edicao_video
from conftest import inserir


@pytest.fixture(autouse=True)
def _revisao_sem_resposta(monkeypatch):
    # Os textos da tela passam pela revisão da ortografia, uma chamada de texto à IA: nos testes
    # ela fica sem resposta, como sem rede, e o teste que a confere põe a sua.
    import api_gemini

    async def sem_resposta(prompt, imagens=None):
        return None

    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", sem_resposta)


def _programas(monkeypatch, largura_da_foto="800", audio="1", codigo_ffmpeg=0):
    """ffprobe e ffmpeg de mentira: guarda cada comando e, no ffmpeg que dá certo, cria a saída."""
    comandos = []

    def run(comando, capture_output=True, text=False, timeout=None):
        comandos.append(comando)
        if comando[0] == "ffprobe":
            saida = largura_da_foto if "v:0" in comando else audio
            return SimpleNamespace(returncode=0, stdout=saida + "\n")
        if codigo_ffmpeg == 0:
            with open(comando[-1], "wb") as arquivo:
                arquivo.write(b"editado")
        return SimpleNamespace(returncode=codigo_ffmpeg, stdout=b"")

    monkeypatch.setattr(edicao_video.videos.subprocess, "run", run)
    return comandos


def test_vale_em_todas_as_fontes_so_depois_de_ligar():
    # O Rafael confirmou que todos os grupos e vídeos dele são autorais: a edição vale em
    # todas as fontes do robô, só depois de ele ligar (DECISOES.md, Shopee Vídeo).
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    fontes = ("autorais", "viral", "principal", "publico")
    assert edicao_video.FONTES_COM_EDICAO == fontes
    assert not any(edicao_video.vale_para(fonte) for fonte in fontes)
    db.salvar_config("shopee_video", {"edicao_ligada": True})
    assert all(edicao_video.vale_para(fonte) for fonte in fontes) and not edicao_video.vale_para("outra")


def test_edita_com_a_foto_no_comeco_a_miniatura_no_canto_e_a_seta(monkeypatch, tmp_path):
    # Vídeo do Rafael (25/10): a miniatura no alto à direita (P120: um pouco menor e logo abaixo
    # da barra de busca) e a seta dele embaixo à esquerda, até o fim.
    comandos = _programas(monkeypatch)
    pasta = tmp_path / "rascunhos"
    pasta.mkdir()
    destino = str(pasta / "rascunho.mp4")
    assert edicao_video.editar("video.mp4", b"foto", destino) == ""
    with open(destino, "rb") as arquivo:
        assert arquivo.read() == b"editado"
    ffmpeg = comandos[-1]
    filtro = ffmpeg[ffmpeg.index("-filter_complex") + 1]
    assert "720:1280" in filtro
    largura, (mx, my) = edicao_video.LARGURA_DA_MINIATURA, edicao_video.CENTRO_DA_MINIATURA
    assert f"-t {edicao_video.SEGUNDOS_DA_FOTO}" in " ".join(ffmpeg) and f"scale={largura}:-2" in filtro
    assert f"overlay=x={mx}-w/2:y={my}-h/2:shortest=1" in filtro
    # As setinhas entram só no vídeo, logo depois da foto (pedido do Rafael, 25/10), e a volta da
    # cascata (os 25 quadros do arquivo, P130) se repete até o fim.
    assert "[3:v]loop=loop=-1:size=25:start=0[seta]" in filtro
    cx, cy = edicao_video.CENTRO_DA_SETA
    assert f"[comfoto][seta]overlay=x={cx}-w/2:y={cy}-h/2:shortest=1,format=yuv420p[editado]" in filtro
    assert "[foto][editado]concat=n=2:v=1:a=0[v]" in filtro
    entradas = [ffmpeg[i + 1] for i, parte in enumerate(ffmpeg) if parte == "-i"]
    assert entradas[3] == edicao_video.SETA
    # Com som: o áudio do vídeo começa depois da foto, que vai em silêncio.
    assert "[4:a][som]concat=n=2:v=0:a=1[a]" in filtro and "[a]" in ffmpeg
    # Só o vídeo editado fica na pasta do rascunho.
    assert os.listdir(pasta) == ["rascunho.mp4"]
    # Escolha do Rafael (29/10, P81): sem a nossa miniatura, o vídeo passa direto, e as outras
    # entradas (a seta e o silêncio) continuam com os mesmos números.
    assert edicao_video.editar("video.mp4", b"foto", destino, miniatura=False) == ""
    ffmpeg = comandos[-1]
    filtro = ffmpeg[ffmpeg.index("-filter_complex") + 1]
    assert "[corpo]null[semmoldura]" in filtro and "[mini]" not in filtro and f"scale={largura}:-2" not in filtro
    # A moldura do cartão (P128) entra por último, por cima do corpo do vídeo, e sai em [comfoto]. Ela
    # espera o cartão do app aparecer: entra ESPERA_DA_MOLDURA segundos depois do fim da abertura
    # (vídeos do Rafael das 00:32 e 00:36 de 03/11, P140 2: a moldura vazia ficava solta).
    assert ffmpeg[[i for i, parte in enumerate(ffmpeg) if parte == "-i"][-1] + 1].endswith("moldura.png")
    espera = edicao_video.ESPERA_DA_MOLDURA
    assert 1 <= espera <= 2
    assert ("[5:v]format=rgba[moldura];[semmoldura][moldura]overlay=0:0:shortest=1"
            f":enable='gte(t,{espera:.3f})'[comfoto]") in filtro
    assert [ffmpeg[i + 1] for i, parte in enumerate(ffmpeg) if parte == "-i"][3] == edicao_video.SETA
    assert "[3:v]loop=loop=-1:size=25:start=0[seta]" in filtro and "[4:a][som]concat=n=2:v=0:a=1[a]" in filtro


def test_setinhas_em_cascata_acendem_de_cima_para_baixo():
    # Escolha do Rafael (02/11, P130): três setinhas para baixo, uma embaixo da outra, com o contorno
    # branco e a sombra leve (P127), acendendo de cima para baixo, uma volta por segundo, num fundo
    # transparente; no vermelho do destaque, para chamar mais a atenção (03/11, P140 2).
    from PIL import Image
    with Image.open(edicao_video.SETA) as arquivo:
        assert arquivo.format == "PNG" and arquivo.mode == "RGBA" and arquivo.size == edicao_video.TAMANHO_DA_SETA
        inicio, quadros = edicao_video.PULSO_DA_SETA
        assert (inicio, quadros) == (0, arquivo.n_frames) and arquivo.info.get("duration") == 40   # 25 por segundo
        assert quadros == 25
        vistos = []
        for n in range(arquivo.n_frames):
            arquivo.seek(n)
            vistos.append(arquivo.convert("RGBA").copy())
    cor = edicao_video.VERMELHO_DO_DESTAQUE
    largura, altura = vistos[0].size

    def pontas(quadro):
        """
        Na coluna do meio, onde ficam as pontas das três setinhas: a força do vermelho (a soma da
        opacidade) de cada trecho seguido com vermelho, de cima para baixo.
        """
        trechos, soma = [], 0
        for y in range(altura):
            r, g, b, a = quadro.getpixel((largura // 2, y))
            if a > 30 and sum(abs(c - d) for c, d in zip((r, g, b), cor)) < 30:
                soma += a
            elif soma:
                trechos.append(soma)
                soma = 0
        return trechos + ([soma] if soma else [])

    # Três setinhas separadas, em todos os quadros, e sempre uma bem acesa (na passagem de uma para
    # a de baixo, as duas ficam pela metade do caminho, mais da metade da força).
    for quadro in vistos:
        assert len(pontas(quadro)) == 3
        assert max(quadro.getpixel((x, y))[3] for x in range(largura) for y in range(altura)
                   if sum(abs(c - d) for c, d in zip(quadro.getpixel((x, y))[:3], cor)) < 30) > 150
    # Cada uma acende na sua vez: a de cima, depois a do meio, depois a de baixo.
    for quadro, acesa in ((vistos[3], 0), (vistos[11], 1), (vistos[20], 2)):
        forcas = pontas(quadro)
        assert forcas.index(max(forcas)) == acesa
    # O contorno branco em volta e o fundo transparente; nada escuro e opaco.
    pixels = [vistos[0].getpixel((x, y)) for x in range(largura) for y in range(altura)]
    assert [p for p in pixels if p[3] == 255 and min(p[:3]) > 240]
    assert len([p for p in pixels if p[3] == 0]) > len(pixels) * 0.5
    assert not [p for p in pixels if p[3] > 200 and max(p[:3]) < 120]
    for canto in ((0, 0), (largura - 10, 0), (0, altura - 10), (largura - 10, altura - 10)):
        assert all(vistos[0].getpixel((canto[0] + x, canto[1] + y))[3] == 0 for x in range(10) for y in range(10))
    assert os.path.getsize(edicao_video.SETA) < 1024 * 1024


def test_moldura_do_cartao_fica_em_volta_do_cartao_do_produto(monkeypatch):
    # Escolha do Rafael (02/11, P128, em teste): a moldura em volta do cartão do produto que o app
    # mostra embaixo, no lugar em que ele aparece no celular dele, abaixo da seta e da legenda da
    # fala, acima da linha do Ver Produtos e dentro do que o app mostra do vídeo aberto; no vermelho
    # do destaque (03/11, P140 2).
    import io

    from PIL import Image, ImageSequence
    imagem = Image.open(io.BytesIO(edicao_video.moldura_do_cartao()))
    assert imagem.mode == "RGBA" and imagem.size == edicao_video.TELA
    x1, y1, x2, y2 = edicao_video.CARTAO_DO_PRODUTO
    folga, grossura = edicao_video.FOLGA_DO_CARTAO, edicao_video.GROSSURA_DA_MOLDURA_DO_CARTAO
    meio_x, meio_y = (x1 + x2) // 2, (y1 + y2) // 2
    vermelho = edicao_video.VERMELHO_DO_DESTAQUE
    # Vermelho na moldura, nos quatro lados; transparente no cartão, na folga e fora dela.
    for ponto in ((x1 - folga - grossura // 2, meio_y), (x2 + folga + grossura // 2, meio_y),
                  (meio_x, y1 - folga - grossura // 2), (meio_x, y2 + folga + grossura // 2)):
        pixel = imagem.getpixel(ponto)
        assert pixel[3] > 200 and sum(abs(a - b) for a, b in zip(pixel[:3], vermelho)) < 30, ponto
    for ponto in ((meio_x, meio_y), (x1 - folga // 2, meio_y), (meio_x, y1 - folga - grossura - 3), (10, 10)):
        assert imagem.getpixel(ponto)[3] == 0, ponto
    caixa = imagem.getchannel("A").getbbox()
    esquerda, direita = edicao_video.VISIVEL_NO_APP
    assert esquerda <= caixa[0] and caixa[2] <= direita
    # Abaixo da seta (no maior pulso) e da legenda da fala; acima da linha do Ver Produtos (y 1122).
    with Image.open(edicao_video.SETA) as seta:
        pe_da_seta = max(q.convert("RGBA").getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()[3]
                         for q in ImageSequence.Iterator(seta) if q.convert("RGBA").getchannel("A").getbbox())
        topo_da_seta = edicao_video.CENTRO_DA_SETA[1] - seta.size[1] // 2
    assert topo_da_seta + pe_da_seta < caixa[1] and edicao_video.PE_DA_LEGENDA < caixa[1] and caixa[3] <= 1115
    # Desligada, nada vai.
    monkeypatch.setattr(edicao_video, "MOLDURA_DO_CARTAO", False)
    edicao_video.moldura_do_cartao.cache_clear()
    try:
        assert edicao_video.moldura_do_cartao() is None
    finally:
        monkeypatch.setattr(edicao_video, "MOLDURA_DO_CARTAO", True)
        edicao_video.moldura_do_cartao.cache_clear()


def test_com_o_rotulo_de_ia_a_moldura_as_setinhas_e_a_legenda_sobem_com_o_cartao(monkeypatch, tmp_path):
    # Print e vídeo do Rafael de 03/11 (07:08 e 07:10): com o Rótulo de IA, o app põe embaixo a linha
    # "Identificado como conteúdo gerado por IA" e o cartão do produto sobe uns 40 px no vídeo; a
    # moldura ficava no lugar de sempre, embaixo do cartão ("ele tem que subir a moldura nesses
    # casos"). Ela sobe junto, com as setinhas e a legenda da fala, no mesmo lugar em relação ao cartão.
    import io

    from PIL import Image
    subida = edicao_video.SUBIDA_COM_O_ROTULO_DE_IA
    assert 30 <= subida <= 50
    de_sempre = Image.open(io.BytesIO(edicao_video.moldura_do_cartao())).getchannel("A").getbbox()
    com_rotulo = Image.open(io.BytesIO(edicao_video.moldura_do_cartao(True))).getchannel("A").getbbox()
    assert com_rotulo == (de_sempre[0], de_sempre[1] - subida, de_sempre[2], de_sempre[3] - subida)
    # A edição: as setinhas e a moldura sobem; sem o rótulo, ficam onde estavam.
    pedidos = []

    def com_foto_e_miniatura(video, foto, destino, segundos, largura, centro, seta, centro_seta, *args, **opcoes):
        pedidos.append((centro_seta, opcoes.get("moldura")))
        return ""
    monkeypatch.setattr(edicao_video.videos, "com_foto_e_miniatura", com_foto_e_miniatura)
    destino = str(tmp_path / "r.mp4")
    assert edicao_video.editar("v.mp4", _foto_jpg(), destino, rotulo_de_ia=True) == ""
    assert edicao_video.editar("v.mp4", _foto_jpg(), destino) == ""
    cx, cy = edicao_video.CENTRO_DA_SETA
    assert pedidos == [((cx, cy - subida), edicao_video.moldura_do_cartao(True)),
                       ((cx, cy), edicao_video.moldura_do_cartao())]
    # A legenda da fala sobe o mesmo tanto.
    legenda = [(1.0, 3.0, "Olha que lindo esse vestido")]
    assert ([y for *_, y in edicao_video.letreiros_da_fala(legenda, 10.0, subida)]
            == [y - subida for *_, y in edicao_video.letreiros_da_fala(legenda, 10.0)])
    # O Editor 2 leva o rótulo até a legenda e a edição.
    vistos = []

    def com_cortes_e_ritmo(video, trechos, destino, letreiros=(), espera=300):
        vistos.append([y for *_, y in letreiros][-1])
        return ""

    def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outras_fotos=(),
               rotulo_de_ia=False, cor=None):
        vistos.append(rotulo_de_ia)
        return ""
    monkeypatch.setattr(edicao_video.videos, "com_cortes_e_ritmo", com_cortes_e_ritmo)
    monkeypatch.setattr(edicao_video, "editar", editar)
    edicao_video._editor_2_no_original("v.mp4", b"foto", destino, 10.0, "", "", "", "alto", legendas=legenda,
                                       rotulo_de_ia=True)
    assert vistos == [edicao_video.letreiros_da_fala(legenda, 10.0, subida)[-1][-1], True]
    # E o vídeo que vai ao ar leva o rótulo ao Editor 2.
    _versoes_de_mentira(monkeypatch)
    _textos_da_tela(monkeypatch, {"nome": "Bolsa", "vantagem": "Leve", "falas": [], "lugar": "alto"})
    repasses = []

    def editar_2(*args, **opcoes):
        repasses.append(args[13] if len(args) > 13 else opcoes.get("rotulo_de_ia"))
        return "", {"textos": ["Bolsa"], "legendas": 0}
    monkeypatch.setattr(edicao_video, "editar_2", editar_2)
    edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa", rotulo_de_ia=True)
    edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa")
    assert repasses == [True, False]


def test_edicao_de_verdade_tem_a_seta_sem_fundo_ate_o_fim(tmp_path):
    # Com o ffmpeg de verdade: num vídeo claro, onde a seta está o vermelho aparece e o resto
    # do recorte dela continua claro (sem o quadrado preto), também depois do fim do arquivo.
    if not shutil.which("ffmpeg"):
        assert edicao_video.editar(str(tmp_path / "nao_existe.mp4"), b"foto", str(tmp_path / "r.mp4")) != ""
        return
    video, foto = tmp_path / "v.mp4", tmp_path / "foto.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0xf0e0c0:size=360x640:rate=30:duration=6",
                    str(video)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x3060a0:size=200x200",
                    "-frames:v", "1", str(foto)], check=True)
    destino = tmp_path / "editado.mp4"
    assert edicao_video.editar(str(video), foto.read_bytes(), str(destino)) == ""
    from PIL import Image

    def onde_fica_a_seta(segundo):
        quadro = tmp_path / f"quadro_{segundo}.ppm"
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(segundo), "-i", str(destino), "-frames:v", "1",
                        str(quadro)], check=True)
        with Image.open(quadro) as imagem:
            tela = imagem.convert("RGB")
        assert tela.size == (720, 1280)
        cx, cy = edicao_video.CENTRO_DA_SETA
        recorte = [tela.getpixel((x, y)) for x in range(cx - 90, cx + 90, 2) for y in range(cy - 68, cy + 68, 2)]
        cor = edicao_video.VERMELHO_DO_DESTAQUE
        vermelhos = [p for p in recorte if sum(abs(a - b) for a, b in zip(p, cor)) < 70]
        escuros = [p for p in recorte if max(p) < 90]
        return len(vermelhos) / len(recorte), escuros

    # Na foto (os 2 primeiros segundos), nada de seta; ela começa a se desenhar com o vídeo.
    assert onde_fica_a_seta(1.9) == (0, [])
    # A moldura do cartão do produto (P128) também só entra no vídeo, e só ESPERA_DA_MOLDURA (1,5 s)
    # depois da abertura, com o cartão do app já na tela (P140 2): aos 3 s, ainda não; aos 4 s, sim.
    def na_moldura(segundo):
        quadro = tmp_path / f"moldura_{segundo}.ppm"
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(segundo), "-i", str(destino), "-frames:v", "1",
                        str(quadro)], check=True)
        with Image.open(quadro) as imagem:
            tela = imagem.convert("RGB")
        x1, y1, _x2, y2 = edicao_video.CARTAO_DO_PRODUTO
        x = x1 - edicao_video.FOLGA_DO_CARTAO - edicao_video.GROSSURA_DA_MOLDURA_DO_CARTAO // 2
        return [tela.getpixel((x, y)) for y in range(y1 + 20, y2 - 20, 10)]
    cor = edicao_video.VERMELHO_DO_DESTAQUE
    for segundo in (1.0, 3.0):
        assert not [p for p in na_moldura(segundo) if sum(abs(a - b) for a, b in zip(p, cor)) < 70], segundo
    assert all(sum(abs(a - b) for a, b in zip(p, cor)) < 70 for p in na_moldura(4.0))
    vermelho, escuros = onde_fica_a_seta(2.6)
    assert vermelho > 0 and not escuros
    # 7,5 s: depois do fim do arquivo, já na volta repetida da cascata (uma setinha acesa por inteiro).
    vermelho, escuros = onde_fica_a_seta(7.5)
    assert vermelho > 0.02 and not escuros


def test_foto_do_comeco_e_capa_dos_avisos_no_fundo_preto(tmp_path):
    # Escolha do Rafael (29/10, P72): o app usa o primeiro quadro como capa na grade do perfil,
    # e o número de visualizações, em letras brancas, some num fundo branco.
    import io

    from PIL import Image
    capa = Image.open(io.BytesIO(edicao_video.capa_com_avisos(_foto_jpg()))).convert("RGB")
    # O alto e o pé da capa, fora da foto e dos avisos: onde a grade põe o número.
    assert max(capa.getpixel((360, 20))) < 20 and max(capa.getpixel((360, 1250))) < 20
    if not shutil.which("ffmpeg"):
        return
    video, foto = tmp_path / "v.mp4", tmp_path / "foto.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0xf0e0c0:size=360x640:rate=30:duration=3",
                    str(video)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x3060a0:size=200x200",
                    "-frames:v", "1", str(foto)], check=True)
    destino = tmp_path / "editado.mp4"
    assert edicao_video.editar(str(video), foto.read_bytes(), str(destino)) == ""
    quadro = tmp_path / "quadro.ppm"
    subprocess.run(["ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(destino), "-frames:v", "1", str(quadro)],
                   check=True)
    with Image.open(quadro) as imagem:
        tela = imagem.convert("RGB")
    # A foto quadrada fica no meio da tela; acima e abaixo dela, o fundo preto.
    assert max(tela.getpixel((360, 60))) < 30 and max(tela.getpixel((360, 1220))) < 30
    vermelho, _, azul = tela.getpixel((360, 640))
    assert azul > 120 and vermelho < 90


def _foto_jpg():
    import io

    from PIL import Image
    saida = io.BytesIO()
    Image.new("RGB", (800, 800), (200, 120, 40)).save(saida, "JPEG")
    return saida.getvalue()


def test_capa_da_bebida_alcoolica_tem_a_foto_e_os_tres_avisos(monkeypatch, tmp_path):
    # Escolha do Rafael (26/10, P43): os avisos da Shopee na capa, que é o começo do vídeo.
    import io

    from PIL import Image
    capa = Image.open(io.BytesIO(edicao_video.capa_com_avisos(_foto_jpg()))).convert("RGB")
    assert capa.size == edicao_video.TELA
    meio = (edicao_video.AREA_DA_FOTO[0] + edicao_video.AREA_DA_FOTO[1]) // 2
    assert capa.getpixel((360, meio)) == (200, 120, 40) or max(abs(a - b) for a, b in zip(
        capa.getpixel((360, meio)), (200, 120, 40))) < 8
    cima, baixo = edicao_video.AREA_DOS_AVISOS
    faixa = [capa.getpixel((x, y)) for x in range(0, 720, 4) for y in range(cima, baixo, 4)]
    assert sum(1 for p in faixa if max(p) < 40) > len(faixa) * 0.6       # a faixa preta
    assert sum(1 for p in faixa if min(p) > 200) > 50                     # as letras brancas
    assert edicao_video.capa_com_avisos(b"nao e imagem") is None
    # Na edição, a capa abre o vídeo no lugar da foto.
    comandos = _programas(monkeypatch)
    destino = tmp_path / "editado.mp4"
    assert edicao_video.editar(str(tmp_path / "v.mp4"), _foto_jpg(), str(destino), avisos=True) == ""
    ffmpeg = [c for c in comandos if c[0] == "ffmpeg"][0]
    assert ffmpeg[ffmpeg.index("-i") + 1].endswith("capa.png")
    comandos.clear()
    # Sem os avisos, a abertura é a foto do anúncio em tela cheia, montada à parte: a foto que vai
    # ao ffmpeg é a da miniatura, com a moldura (P115), e a do começo vai sem ela (P119).
    assert edicao_video.editar(str(tmp_path / "v.mp4"), _foto_jpg(), str(destino)) == ""
    ffmpeg = [c for c in comandos if c[0] == "ffmpeg"][0]
    assert ffmpeg[ffmpeg.index("-i") + 1].endswith("capa.png")


def test_edicao_de_verdade_da_bebida_alcoolica_abre_com_os_avisos(tmp_path):
    if not shutil.which("ffmpeg"):
        return
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0xf0e0c0:size=360x640:rate=30:duration=3",
                    str(video)], check=True)
    destino = tmp_path / "editado.mp4"
    assert edicao_video.editar(str(video), _foto_jpg(), str(destino), avisos=True) == ""
    from PIL import Image

    def faixa_escura(segundo):
        quadro = tmp_path / f"quadro_{segundo}.ppm"
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(segundo), "-i", str(destino), "-frames:v", "1",
                        str(quadro)], check=True)
        with Image.open(quadro) as imagem:
            tela = imagem.convert("RGB")
        cima, baixo = edicao_video.AREA_DOS_AVISOS
        pontos = [tela.getpixel((x, y)) for x in range(0, 720, 8) for y in range(cima + 10, baixo - 10, 8)]
        return sum(1 for p in pontos if max(p) < 60) / len(pontos)

    # O primeiro quadro (a capa) tem a faixa dos avisos; o vídeo depois da foto, não.
    assert faixa_escura(0) > 0.5 and faixa_escura(2.5) < 0.1

def test_video_sem_som_sai_sem_som(monkeypatch, tmp_path):
    comandos = _programas(monkeypatch, audio="")
    assert edicao_video.editar("video.mp4", b"foto", str(tmp_path / "r.mp4")) == ""
    ffmpeg = comandos[-1]
    assert "anullsrc" not in " ".join(ffmpeg) and "[a]" not in ffmpeg


def test_sem_foto_foto_que_nao_abre_ou_ffmpeg_falhou_nao_deixa_arquivo(monkeypatch, tmp_path):
    destino = str(tmp_path / "r.mp4")
    assert edicao_video.editar("video.mp4", None, destino) == "a foto do anúncio não veio"
    # Uma imagem que não abre prenderia o ffmpeg em laço: nem chega a ele.
    comandos = _programas(monkeypatch, largura_da_foto="0")
    assert edicao_video.editar("video.mp4", b"x", destino) == "a foto do anúncio não é uma imagem que abre"
    assert all(c[0] == "ffprobe" for c in comandos)
    _programas(monkeypatch, codigo_ffmpeg=1)
    assert edicao_video.editar("video.mp4", b"foto", destino) == "o ffmpeg falhou (código 1)"
    assert not os.path.exists(destino)


def test_ffmpeg_que_demora_demais_desiste(monkeypatch, tmp_path):
    def run(comando, **kwargs):
        if comando[0] == "ffprobe":
            return SimpleNamespace(returncode=0, stdout="800\n")
        raise subprocess.TimeoutExpired(comando, kwargs.get("timeout"))

    monkeypatch.setattr(edicao_video.videos.subprocess, "run", run)
    assert edicao_video.editar("video.mp4", b"foto", str(tmp_path / "r.mp4")).startswith("o ffmpeg passou de")


def _fontes_de_mentira(monkeypatch, candidatos, fonte_do_robo="autorais"):
    """O exemplo com as fontes de mentira ({fonte: [(id, arquivo, link, legenda)]}) e a foto e o nome fixos."""
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    db.salvar_config("shopee_video", {"fonte": fonte_do_robo})
    monkeypatch.setattr(edicao_video.assistente, "candidatos_nao_usados", lambda fonte: candidatos.get(fonte, []))
    monkeypatch.setattr(edicao_video.ps, "foto_do_produto",
                        lambda video: None if "sem-foto" in video["link"] else b"foto")
    monkeypatch.setattr(edicao_video.ps, "nome_do_produto", lambda video: "Copo Térmico")
    editados = []
    monkeypatch.setattr(edicao_video, "editar", lambda video, foto, destino: editados.append(video) or "")
    return editados


def _exemplo_simples():
    """O exemplo com o Editor 1 só (sem IA nem versões): a escolha do vídeo é a mesma dos dois editores."""
    return edicao_video._exemplo("ids", lambda arquivo, link, foto: (
        edicao_video.editar(arquivo, foto, "exemplo.mp4"), None))[:2]


def test_exemplo_usa_o_proximo_video_do_robo_com_arquivo_link_e_foto(monkeypatch, tmp_path):
    sem_arquivo, com_foto = str(tmp_path / "sumiu.mp4"), str(tmp_path / "a.mp4")
    open(com_foto, "wb").close()
    editados = _fontes_de_mentira(monkeypatch, {"autorais": [
        ("1", sem_arquivo, "https://s.shopee.com.br/a", ""), ("2", com_foto, None, ""),
        ("3", com_foto, "https://s.shopee.com.br/sem-foto", ""), ("4", com_foto, "https://s.shopee.com.br/b", "")]})
    assert _exemplo_simples() == ("Copo Térmico", "")
    assert editados == [com_foto]


def test_cada_exemplo_mostra_um_video_novo_e_recomeca_no_fim(monkeypatch, tmp_path):
    # Pedido do Rafael (25/10): cada toque em Ver Exemplo da Edição mostra um vídeo novo, o
    # próximo que o robô pegaria para postar (a fonte do robô primeiro), sem postar.
    videos = {nome: str(tmp_path / f"{nome}.mp4") for nome in ("v1", "v2", "a1")}
    for caminho in videos.values():
        open(caminho, "wb").close()
    editados = _fontes_de_mentira(monkeypatch, {
        "viral": [("viral:1", videos["v1"], "https://s.shopee.com.br/1", ""),
                  ("viral:2", videos["v2"], "https://s.shopee.com.br/2", "")],
        "autorais": [("a1", videos["a1"], "https://s.shopee.com.br/3", "")]}, fonte_do_robo="viral")
    for _ in range(4):
        assert _exemplo_simples()[0] == "Copo Térmico"
    assert editados == [videos["v1"], videos["v2"], videos["a1"], videos["v1"]]


def test_exemplo_sem_video_diz_o_motivo(monkeypatch):
    _fontes_de_mentira(monkeypatch, {})
    nome, motivo = _exemplo_simples()
    assert nome is None and motivo == "nenhum vídeo com o arquivo e o link no servidor agora"


def test_exemplo_procura_nas_outras_fontes_quando_a_do_robo_so_tem_ver_produtos(monkeypatch, tmp_path):
    # 25/10: os próximos do Viral eram quase todos de Ver Produtos (sem uma foto só) e os dois
    # com foto já tinham sido mostrados; o exemplo olhava só os 10 primeiros do Viral e falhava.
    arquivo = str(tmp_path / "v.mp4")
    open(arquivo, "wb").close()
    viral = [(f"viral:{i}", arquivo, f"https://s.shopee.com.br/sem-foto-{i}", "") for i in range(12)]
    editados = _fontes_de_mentira(monkeypatch, {"viral": viral, "autorais": [
        ("a1", arquivo, "https://s.shopee.com.br/a1", "")]}, fonte_do_robo="viral")
    fotos = []
    monkeypatch.setattr(edicao_video.ps, "foto_do_produto",
                        lambda video: fotos.append(video["link"]) or (None if "sem-foto" in video["link"] else b"foto"))
    assert _exemplo_simples() == ("Copo Térmico", "")
    assert editados == [arquivo] and fotos[-1].endswith("/a1")
    assert len(fotos) == edicao_video.VIDEOS_POR_FONTE + 1
    # Os sem foto ficam lembrados: o toque seguinte não pergunta de novo à API por eles.
    fotos.clear()
    _exemplo_simples()
    assert not [link for link in fotos if "sem-foto-0" in link]


def test_sem_video_novo_com_foto_recomeca_pelos_ja_mostrados(monkeypatch, tmp_path):
    arquivo = str(tmp_path / "v.mp4")
    open(arquivo, "wb").close()
    editados = _fontes_de_mentira(monkeypatch, {"viral": [
        ("viral:1", arquivo, "https://s.shopee.com.br/1", ""),
        ("viral:2", arquivo, "https://s.shopee.com.br/sem-foto-2", "")]}, fonte_do_robo="viral")
    for _ in range(3):
        assert _exemplo_simples() == ("Copo Térmico", "")
    assert len(editados) == 3
    assert db.ler_config(edicao_video.CHAVE_EXEMPLOS, {})["ids"] == ["viral:1"]


def test_so_videos_sem_foto_diz_que_nenhum_tem_a_foto(monkeypatch, tmp_path):
    arquivo = str(tmp_path / "v.mp4")
    open(arquivo, "wb").close()
    _fontes_de_mentira(monkeypatch, {"viral": [("viral:1", arquivo, "https://s.shopee.com.br/sem-foto-1", "")]},
                       fonte_do_robo="viral")
    for _ in range(2):
        nome, motivo = _exemplo_simples()
        assert nome is None and motivo.startswith("nenhum dos próximos vídeos tem a foto do anúncio")


# --- Editor 2 (pedido do Rafael, 27/10: o Editor 1 sem as partes paradas, com trechos
# acelerados e uma câmera lenta curta, e os textos da tela; só no exemplo até ele escolher) ---

def _movimentos(*partes):
    """Movimento de mentira, 10 medidas por segundo: partes = [(segundos, quanto mexe)]."""
    return [quanto for segundos, quanto in partes for _ in range(round(segundos * 10))]


def _remontado(trechos):
    return sum((fim - inicio) / velocidade for inicio, fim, velocidade in trechos)


def test_ritmo_tira_o_parado_acelera_o_calmo_e_poe_camera_lenta_na_acao():
    movimentos = _movimentos((3, 0.1), (4, 6.0), (3, 2.0), (2, 9.0), (3, 6.0))
    trechos = edicao_video.ritmo(movimentos, 15)
    # Os 3 s parados do começo saem inteiros; o resto fica, na ordem.
    assert trechos[0][0] == 3.0 and trechos[-1][1] == 15
    assert all(trechos[i][1] <= trechos[i + 1][0] for i in range(len(trechos) - 1))
    velocidades = {v for *_, v in trechos}
    assert velocidades == {1.0, edicao_video.ACELERADO, edicao_video.CAMERA_LENTA}
    # A câmera lenta fica no segundo de mais ação (de 10 a 12 s) e dura 1 s.
    lentos = [(inicio, fim) for inicio, fim, v in trechos if v == edicao_video.CAMERA_LENTA]
    assert len(lentos) == 1 and 10 <= lentos[0][0] and lentos[0][1] <= 12 and lentos[0][1] - lentos[0][0] == 1
    # O calmo (de 7 a 10 s) vai acelerado, num trecho só.
    acelerados = [(inicio, fim) for inicio, fim, v in trechos if v == edicao_video.ACELERADO]
    assert len(acelerados) == 1 and 7 <= acelerados[0][0] and acelerados[0][1] <= 10
    # Nenhum trecho normal ou acelerado com menos de 1,5 s: o ritmo não fica soluçando.
    assert all(fim - inicio >= edicao_video.TRECHO_MINIMO for inicio, fim, v in trechos
               if v != edicao_video.CAMERA_LENTA and fim != 15)


def test_ritmo_nao_corta_parado_curto_nem_deixa_o_video_curto_demais():
    # Meio segundo parado no meio só acelera, não sai.
    trechos = edicao_video.ritmo(_movimentos((4, 5.0), (0.5, 0.1), (4.5, 5.0)), 9)
    assert trechos[0][0] == 0 and trechos[-1][1] == 9 and _remontado(trechos) > 8
    # 7 s parados num vídeo de 10 s: cortar deixaria 3 s. O vídeo fica com 8 s ou mais.
    trechos = edicao_video.ritmo(_movimentos((7, 0.1), (3, 5.0)), 10)
    assert _remontado(trechos) >= edicao_video.MINIMO_DO_REMONTADO
    # Sem medição (o vídeo não abriu no ffmpeg), fica inteiro como está.
    assert edicao_video.ritmo([], 12) == [(0.0, 12, 1.0)] and edicao_video.ritmo([1.0], 0) == []


def test_textos_um_de_cada_vez_e_o_que_nao_cabe_sai():
    horarios = edicao_video.horarios_dos_textos(["nome", "vantagem", "chamada"], 12)
    assert [t for t, *_ in horarios] == ["nome", "vantagem", "chamada"]
    assert all(fim - inicio <= edicao_video.SEGUNDOS_DE_CADA_TEXTO for _, inicio, fim in horarios)
    assert all(horarios[i][2] < horarios[i + 1][1] for i in range(2)) and horarios[-1][2] <= 12
    # Vídeo curto: cada texto precisa de 1,5 s; o do fim sai primeiro.
    assert [t for t, *_ in edicao_video.horarios_dos_textos(["nome", "vantagem", "chamada"], 4)] == ["nome", "vantagem"]
    assert edicao_video.horarios_dos_textos(["nome"], 1) == []


def test_chamada_para_o_produto_no_lugar_do_preco(monkeypatch):
    # Escolha do Rafael (29/10, P80): o preço ficava parado no vídeo e não batia com o do cartão
    # do app (o do Pix, mais baixo). No lugar dele, uma chamada para o produto anexado embaixo,
    # que a IA escreve para cada vídeo, numa caixa vermelha (03/11, P140 2); o preço e o desconto
    # ficam só no cartão, sempre atualizados.
    import api_gemini
    pedidos = []

    async def analisar(video, prompt, imagens=None):
        pedidos.append(prompt)
        return ('{"nome": "Copo Térmico", "vantagem": "Mantém gelado", '
                '"chamada": "Toque no produto aqui embaixo 👇 #oferta", "lugar": "alto"}')

    monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)
    textos = edicao_video.textos_da_tela("v.mp4", "Copo Térmico Inox 500 ml")
    assert textos["chamada"] == "Toque no produto aqui embaixo" and len(textos["chamada"]) <= edicao_video.MAXIMO_DA_CHAMADA
    assert "\"chamada\"" in pedidos[0] and "aqui embaixo" in pedidos[0] and "fora da Shopee" in pedidos[0]
    assert "sem preço, desconto" in pedidos[0] and not hasattr(edicao_video, "texto_do_preco")
    import io

    from PIL import Image
    with Image.open(io.BytesIO(edicao_video.letreiro(textos["chamada"], edicao_video.FUNDO_DA_CHAMADA,
                                                     edicao_video.LUGARES_DOS_TEXTOS["alto"][2]))) as imagem:
        # Dentro da caixa do alto, com o fundo transparente em volta e o vermelho do destaque.
        assert imagem.mode == "RGBA" and imagem.width <= 720 and imagem.getpixel((0, 0))[3] == 0
        vermelho, verde, _azul, opaco = imagem.getpixel((imagem.width // 2, 8))
        assert opaco > 150 and vermelho > 180 and verde < 120


def test_chamada_vai_vermelha_e_em_caixa_alta_nas_mesmas_linhas():
    # Vídeos do Rafael das 00:32 e 00:36 de 03/11 (P140 2): a última mensagem, a chamada para o
    # produto, chamava pouco a atenção no laranja; vai numa caixa vermelha, com o texto em CAIXA
    # ALTA, e cabe nas mesmas 2 linhas da caixa do alto (a letra desce um pouco mais que a dos
    # outros textos, porque a maiúscula é mais larga).
    import io

    from PIL import Image
    assert edicao_video.FUNDO_DA_CHAMADA[:3] == edicao_video.VERMELHO_DO_DESTAQUE
    assert edicao_video.LARANJA_DA_SHOPEE != edicao_video.VERMELHO_DO_DESTAQUE
    _x, _topo, largura, linhas = edicao_video.LUGARES_DOS_TEXTOS["alto"]
    chamada = "Garanta sua garrafa na Shopee!"
    caixa = edicao_video.letreiro_da_chamada(chamada, largura, linhas)
    assert caixa == edicao_video.letreiro(chamada.upper(), edicao_video.FUNDO_DA_CHAMADA, largura, linhas,
                                          edicao_video.LETRA_MENOR_DA_CHAMADA)
    assert caixa != edicao_video.letreiro(chamada, edicao_video.FUNDO_DA_CHAMADA, largura, linhas)
    with Image.open(io.BytesIO(caixa)) as imagem:
        menor = edicao_video.LETRA_MENOR_DA_CHAMADA
        # 2 linhas: a margem de 18 px em cima e embaixo e a altura de cada linha (1,25 da letra).
        assert imagem.height <= 2 * round(edicao_video.LETRA_DOS_TEXTOS[0] * 1.25) + 36
        assert imagem.height >= 2 * round(menor * 1.25) + 36 and imagem.width <= largura + 56
        r, g, b, opaco = imagem.getpixel((imagem.width // 2, 8))
        assert opaco > 150 and sum(abs(x - y) for x, y in zip((r, g, b), edicao_video.VERMELHO_DO_DESTAQUE)) < 30
    # No vídeo, a chamada vai por ela; o nome e a vantagem continuam no fundo escuro, como escritos.
    letreiros, textos = edicao_video._letreiros([("Copo Térmico", edicao_video.FUNDO_DOS_TEXTOS),
                                                 ("Mantém gelado", edicao_video.FUNDO_DOS_TEXTOS),
                                                 (chamada, edicao_video.FUNDO_DA_CHAMADA)], "alto", 30.0)
    assert textos == ["Copo Térmico", "Mantém gelado", chamada]
    assert letreiros[-1][0] == caixa
    assert letreiros[0][0] == edicao_video.letreiro("Copo Térmico", edicao_video.FUNDO_DOS_TEXTOS, largura, linhas)


def test_textos_da_ia_vem_limpos_e_curtos(monkeypatch):
    import api_gemini
    pedidos = []

    async def analisar(video, prompt, imagens=None):
        pedidos.append(prompt)
        return ('ok {"nome": "Copo Térmico 🥤 de Inox Grande Premium Novo", '
                '"vantagem": "Mantém gelado o dia todo #top"}')

    monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)
    textos = edicao_video.textos_das_versoes("v.mp4", "Copo Térmico Marca X 500 ml")
    assert textos == {"nome": "Copo Térmico de Inox Grande", "vantagem": "Mantém gelado o dia todo top"}
    assert "Copo Térmico Marca X 500 ml" in pedidos[0] and "marca" in pedidos[0]

    async def sem_resposta(video, prompt, imagens=None):
        return None

    monkeypatch.setattr(api_gemini, "analisar_video_gemini", sem_resposta)
    assert edicao_video.textos_das_versoes("v.mp4", "Copo") == {}


def test_editor_2_de_verdade_e_o_video_original_sem_cortes_com_os_textos(tmp_path):
    # Pedido do Rafael (vídeo de 28/10): o 1º vídeo do Editor 2, o que vai ao ar, é o vídeo
    # original, inteiro e na velocidade dele, só com a foto, a miniatura, a seta e as legendas.
    if not shutil.which("ffmpeg"):
        assert edicao_video.editar_2(str(tmp_path / "nao_existe.mp4"), b"foto", str(tmp_path / "r.mp4"))[0] != ""
        return
    video = tmp_path / "v.mp4"
    # 3 s parados, 9 s mexendo e 3 s parados de novo, com som.
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0xd0c0a0:size=360x640:rate=30:duration=3",
                    "-f", "lavfi", "-i", "testsrc2=size=360x640:rate=30:duration=9",
                    "-f", "lavfi", "-i", "color=c=0xa0c0d0:size=360x640:rate=30:duration=3",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=15",
                    "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a",
                    "-shortest", str(video)], check=True)
    destino = tmp_path / "editado.mp4"
    motivo, resumo = edicao_video.editar_2(str(video), _foto_jpg(), str(destino), "Copo Térmico", "",
                                           "Toque no produto aqui embaixo", lugar="meio")
    assert motivo == ""
    # Nada sai: o vídeo inteiro, mais a foto no começo.
    assert abs(edicao_video.videos.duracao(str(destino)) - (15 + edicao_video.SEGUNDOS_DA_FOTO)) < 0.3
    assert edicao_video.videos.tem_audio(str(destino))
    assert resumo["textos"] == ["Copo Térmico", "Toque no produto aqui embaixo"]
    from PIL import Image

    def ponto(segundo, onde):
        quadro = tmp_path / f"quadro_{segundo}.ppm"
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(segundo), "-i", str(destino), "-frames:v", "1",
                        str(quadro)], check=True)
        with Image.open(quadro) as imagem:
            return imagem.convert("RGB").getpixel(onde)

    caixa = (360, edicao_video.LUGARES_DOS_TEXTOS["meio"][1] + 6)
    # Os 3 s parados do começo e do fim continuam lá, com a cor deles.
    meio_da_tela = (360, 700)
    assert all(abs(a - b) < 30 for a, b in zip(ponto(2.5, meio_da_tela), (0xd0, 0xc0, 0xa0)))
    assert all(abs(a - b) < 30 for a, b in zip(ponto(16.5, meio_da_tela), (0xa0, 0xc0, 0xd0)))
    # O nome logo depois da foto (caixa escura) e a chamada na 2ª metade (caixa vermelha, P80 e P140 2).
    assert max(ponto(3.0, caixa)) < 80
    vermelho, verde, azul = ponto(11.0, caixa)
    assert vermelho > 180 and verde < 120 and azul < 100
    # Sem o lugar da IA, o texto vai no padrão: no alto, à esquerda, ao lado da miniatura (P46).
    motivo, resumo = edicao_video.editar_2(str(video), _foto_jpg(), str(destino), "Copo", "", "")
    x, topo, *_ = edicao_video.LUGARES_DOS_TEXTOS[edicao_video.LUGAR_PADRAO]
    assert motivo == "" and resumo["lugar"] == "alto" and max(ponto(2.8, (x + 12, topo + 6))) < 80


def test_remontar_sem_som_nao_mexe_no_som(monkeypatch, tmp_path):
    comandos = _programas(monkeypatch, audio="")
    trechos = [(0.0, 2.0, 1.0), (3.0, 5.0, 1.5)]
    assert edicao_video.videos.com_cortes_e_ritmo("v.mp4", trechos, str(tmp_path / "r.mp4")) == ""
    filtro = comandos[-1][comandos[-1].index("-filter_complex") + 1]
    assert "asplit" not in filtro and "atempo" not in filtro and "concat=n=2:v=1:a=0" in filtro
    assert "trim=start=3.000:end=5.000,setpts=(PTS-STARTPTS)/1.5" in filtro
    assert edicao_video.videos.com_cortes_e_ritmo("v.mp4", [], str(tmp_path / "r.mp4")) != ""


def test_exemplos_dos_dois_editores_tem_a_lista_propria_e_a_chamada_da_ia(monkeypatch, tmp_path):
    # Pedido do Rafael (27/10): dois editores, o 1 sem legendas e o 2 com legendas, cada um com o
    # vídeo completo e as versões; cada um com a lista própria dos vídeos já mostrados.
    videos = {nome: str(tmp_path / f"{nome}.mp4") for nome in ("v1", "v2")}
    for caminho in videos.values():
        open(caminho, "wb").close()
    _fontes_de_mentira(monkeypatch, {"viral": [
        ("viral:1", videos["v1"], "https://s.shopee.com.br/1", ""),
        ("viral:2", videos["v2"], "https://s.shopee.com.br/2", "")]}, fonte_do_robo="viral")
    monkeypatch.setattr(edicao_video, "_produto_do_link", lambda link: {"nome": "Copo Marca X", "preco": 39.9})
    versoes = [{"vantagem": "Tampa firme", "inicio": 4.0, "fim": 6.0, "chamada": "Veja aqui"}]
    monkeypatch.setattr(edicao_video, "textos_das_versoes", lambda video, nome: {
        "nome": "Copo Térmico", "vantagem": "Gelado o dia todo", "chamada": "Toque no copo aqui embaixo",
        "versoes": versoes, "falas": [], "lugar": "meio"})
    pedidos = []

    def editar_1_e_versoes(video, foto, destino, versoes_da_ia=(), falas=None, miniatura=True):
        pedidos.append((1, video, list(versoes_da_ia), falas, miniatura))
        return "", {"versoes": []}

    def editar_2_e_versoes(video, foto, destino, nome="", vantagem="", versoes_da_ia=(), chamada="", falas=None,
                           lugar=None, miniatura=True, legendas=(), cor=None):
        pedidos.append((2, video, nome, vantagem, list(versoes_da_ia), chamada, lugar, miniatura))
        return "", {"versoes": []}

    monkeypatch.setattr(edicao_video, "editar_1_e_versoes", editar_1_e_versoes)
    monkeypatch.setattr(edicao_video, "editar_2_e_versoes", editar_2_e_versoes)
    nome, motivo, resumo = edicao_video.exemplo_editor_1("exemplo.mp4")
    assert (nome, motivo) == ("Copo Térmico", "") and resumo["versoes_da_ia"] == 1 and resumo["lugar_da_ia"]
    nome, motivo, resumo = edicao_video.exemplo_editor_2("exemplo.mp4")
    # O Editor 1 já mostrou o v1; o Editor 2 tem a lista dele e começa pelo v1 também.
    assert (nome, motivo) == ("Copo Térmico", "") and resumo["textos_da_ia"]
    inteira = edicao_video.LARGURA_DA_MINIATURA
    assert pedidos == [(1, videos["v1"], versoes, [], inteira),
                       (2, videos["v1"], "Copo Térmico", "Gelado o dia todo", versoes, "Toque no copo aqui embaixo",
                        "meio", inteira)]
    dados = db.ler_config(edicao_video.CHAVE_EXEMPLOS, {})
    assert dados["ids"] == ["viral:1"] and dados["ids_2"] == ["viral:1"]
    edicao_video.exemplo_editor_2("exemplo.mp4")
    assert pedidos[-1][1] == videos["v2"]
    # Escolha do Rafael (P52): o vídeo que já tem texto próprio na tela vai sem as nossas legendas.
    monkeypatch.setattr(edicao_video, "textos_das_versoes", lambda video, nome: {
        "nome": "Presilha", "vantagem": "Firme", "versoes": versoes, "falas": [], "lugar": "alto",
        "texto_no_video": True})
    _, _, resumo = edicao_video.exemplo_editor_2("exemplo.mp4")
    assert pedidos[-1][-2] == edicao_video.SEM_LUGAR and resumo["texto_no_video"]
    # Escolha do Rafael (29/10, P81): o criador pôs coisa no canto da nossa miniatura, e os dois
    # exemplos vão sem ela, como o vídeo que vai ao ar; as nossas legendas continuam (P82).
    monkeypatch.setattr(edicao_video, "textos_das_versoes", lambda video, nome: {
        "nome": "Cortina", "vantagem": "Tecido com relevo", "versoes": versoes, "falas": [], "lugar": "alto",
        "canto_ocupado": True})
    _, _, resumo = edicao_video.exemplo_editor_1("exemplo.mp4")
    assert pedidos[-1][0] == 1 and pedidos[-1][-1] == 0 and resumo["miniatura"] == 0
    _, _, resumo = edicao_video.exemplo_editor_2("exemplo.mp4")
    assert pedidos[-1][0] == 2 and pedidos[-1][-1] == 0 and pedidos[-1][-2] == "alto"
    assert resumo["miniatura"] == 0
    # Escolha do Rafael (29/10, P97): com a coisa dele logo abaixo do canto, os dois exemplos levam
    # a miniatura menor, como o vídeo que vai ao ar.
    monkeypatch.setattr(edicao_video, "textos_das_versoes", lambda video, nome: {
        "nome": "Mercadinho", "vantagem": "Brincar de vender", "versoes": versoes, "falas": [], "lugar": "alto",
        "canto_ocupado": True, "por_cima": [(55.0, 95.0, 24.5, 30.0)]})
    for exemplo in (edicao_video.exemplo_editor_1, edicao_video.exemplo_editor_2):
        _, _, resumo = exemplo("exemplo.mp4")
        assert pedidos[-1][-1] == 132 and resumo["miniatura"] == 132


def test_onde_alguem_fala_o_ritmo_nao_corta_nao_acelera_nem_poe_camera_lenta():
    # Escolha do Rafael (P45, 27/10): no 1º exemplo, o começo da fala saiu junto com a parte
    # parada. 3 s parados com fala, 3 s calmos com fala, 2 s de ação com fala e 6 s de ação.
    movimentos = _movimentos((3, 0.1), (3, 2.0), (2, 9.0), (6, 6.0))
    com_fala = edicao_video.janelas_com_fala([(0.2, 7.9)], 14)
    trechos = edicao_video.ritmo(movimentos, 14, com_fala=com_fala)
    assert trechos[0][:2] == (0.0, 8.5) and trechos[0][2] == 1.0
    lentos = [(inicio, fim) for inicio, fim, v in trechos if v == edicao_video.CAMERA_LENTA]
    assert lentos and all(inicio >= 8.0 for inicio, _ in lentos)
    # Sem fala, os mesmos 3 s parados saem.
    assert edicao_video.ritmo(movimentos, 14)[0][0] == 3.0


def test_janelas_com_fala_pela_ia_com_folga_ou_pelo_som():
    # Pela IA: de 1,0 a 1,6 s, com 0,3 s de folga de cada lado (0,7 a 1,9 s).
    assert edicao_video.janelas_com_fala([(1.0, 1.6)], 5) == {1, 2, 3}
    assert edicao_video.janelas_com_fala([], 5) == frozenset()
    # Sem a IA (None): as janelas com som acima do silêncio, também música.
    volumes = [-100.0, -20.0, -55.0, -30.0]
    assert edicao_video.janelas_com_fala(None, 2, volumes) == {1, 3}


def test_ia_diz_onde_tem_fala_e_resposta_torta_vira_sem_resposta(monkeypatch):
    import api_gemini

    def responde(texto):
        async def analisar(video, prompt, imagens=None):
            return texto
        monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)

    responde('{"nome": "Copo", "vantagem": "", "falas": [[0.5, 3], [4, 6.5], [9, 8]]}')
    assert edicao_video.textos_das_versoes("v.mp4", "Copo") == {"nome": "Copo", "falas": [(0.5, 3.0), (4.0, 6.5)]}
    responde('{"nome": "Copo", "falas": []}')
    assert edicao_video.textos_das_versoes("v.mp4", "Copo")["falas"] == []
    responde('{"nome": "Copo", "falas": "o vídeo inteiro"}')
    assert "falas" not in edicao_video.textos_das_versoes("v.mp4", "Copo")
    # O lugar dos textos (P46 e P47): os de LUGARES_DOS_TEXTOS ou "nenhum"; o resto não vale.
    for lugar in ("meio", "esquerda", "direita", "nenhum"):
        responde('{"nome": "Copo", "lugar": "%s"}' % lugar)
        assert edicao_video.textos_das_versoes("v.mp4", "Copo")["lugar"] == lugar
    responde('{"nome": "Copo", "lugar": "embaixo"}')
    assert "lugar" not in edicao_video.textos_das_versoes("v.mp4", "Copo")


def test_volume_do_som_por_janela(tmp_path):
    if not shutil.which("ffmpeg"):
        return
    video = tmp_path / "v.mp4"
    # 1 s de silêncio e 1 s de apito.
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:size=64x64:rate=10:duration=2",
                    "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=8000:d=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1:sample_rate=8000",
                    "-filter_complex", "[1:a][2:a]concat=n=2:v=0:a=1[a]", "-map", "0:v", "-map", "[a]",
                    str(video)], check=True)
    volumes = edicao_video.videos.som_por_janela(str(video))
    # O AAC pode deixar um restinho depois do fim: as 4 primeiras janelas são as que contam.
    assert len(volumes) >= 4 and max(volumes[:2]) < edicao_video.SILENCIO < min(volumes[2:4])
    assert all(type(v) is float for v in volumes)
    sem_som = tmp_path / "mudo.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:size=64x64:rate=10:duration=1",
                    str(sem_som)], check=True)
    assert edicao_video.videos.som_por_janela(str(sem_som)) == []


def test_texto_da_tela_menor_cabe_ao_lado_da_miniatura():
    # Escolha do Rafael (P46, 27/10): a caixa grande cobria o produto; agora uns 7% da tela, e
    # no alto ela cabe à esquerda da miniatura, com folga.
    import io

    from PIL import Image
    for texto in ("Confortável e cheio de estilo", "Cintura alta e ótima modelagem", "Aparador Buffet Retrô",
                  "Mantém a bebida gelada por 24 horas", "Toque no produto aqui embaixo"):
        for lugar, (x, topo, largura, linhas) in edicao_video.LUGARES_DOS_TEXTOS.items():
            with Image.open(io.BytesIO(edicao_video.letreiro(texto, largura_maxima=largura,
                                                             linhas_maximas=linhas))) as imagem:
                assert imagem.width * imagem.height <= 0.08 * 720 * 1280, (texto, lugar)
                if lugar == "alto":
                    comeco_da_miniatura = edicao_video.CANTO_DA_MINIATURA[0] - edicao_video.LARGURA_DA_MINIATURA
                    assert x + imagem.width < comeco_da_miniatura - 10 and topo + imagem.height < 280
                if lugar in ("esquerda", "direita"):
                    # Nos lados (P47): estreita, longe do meio da tela, acima da seta e dos
                    # botões do app à direita.
                    topo_da_seta = edicao_video.CENTRO_DA_SETA[1] - 70
                    assert imagem.width <= 0.34 * 720 and topo + imagem.height < topo_da_seta, (texto, lugar)


def test_seta_e_textos_dentro_do_que_o_app_mostra():
    # Escolha do Rafael (P71, vídeo de 28/10 às 23:20): no celular dele o app corta as bordas do
    # vídeo, a barra de busca cobria o alto da caixa do texto e o cartão do produto tampava a
    # ponta da seta. A seta fica inteira acima do cartão, mesmo no maior pulso, e os textos dentro
    # do que o app mostra, abaixo da busca.
    import io

    from PIL import Image, ImageSequence
    esquerda, direita = edicao_video.VISIVEL_NO_APP
    with Image.open(edicao_video.SETA) as seta:
        caixas = [q.convert("RGBA").getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
                  for q in ImageSequence.Iterator(seta)]
        largura, altura = seta.size
    cx, cy = edicao_video.CENTRO_DA_SETA
    assert cy - altura // 2 + max(c[3] for c in caixas if c) < edicao_video.COMECO_DO_CARTAO_DO_PRODUTO
    assert cx - largura // 2 + min(c[0] for c in caixas if c) >= esquerda
    for texto in ("Óculos de Sol Hexagonal", "Mantém a bebida gelada por 24 horas", "Design elegante e moderno",
                  "Toque no produto aqui embaixo"):
        for lugar, (x, topo, largura_maxima, linhas) in edicao_video.LUGARES_DOS_TEXTOS.items():
            with Image.open(io.BytesIO(edicao_video.letreiro(texto, largura_maxima=largura_maxima,
                                                             linhas_maximas=linhas))) as imagem:
                inicio = (720 - imagem.width) // 2 if x is None else (720 + x - imagem.width if x < 0 else x)
                assert esquerda + 10 <= inicio and inicio + imagem.width <= direita - 10, (texto, lugar)
                assert topo >= edicao_video.FIM_DA_BARRA_DE_BUSCA + 5, lugar


def test_editor_2_nos_lados_e_sem_lugar_livre_sem_texto(monkeypatch, tmp_path):
    # Escolha do Rafael (P47, 27/10): no vídeo do conjunto, o alto cobriu o rosto da modelo e
    # o meio cobriria o conjunto. A IA ganha os lados e, sem lugar livre, o vídeo vai sem texto.
    monkeypatch.setattr(edicao_video.videos, "duracao", lambda video, timeout=30: 12.0)
    monkeypatch.setattr(edicao_video.videos, "movimento", lambda video, por_segundo=10, timeout=120: [5.0] * 120)
    monkeypatch.setattr(edicao_video, "editar",
                        lambda video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True,
                               outras_fotos=(), rotulo_de_ia=False, cor=None: "")
    montados = []

    def com_cortes_e_ritmo(video, trechos, destino, letreiros=(), espera=300):
        montados.append(list(letreiros))
        return ""
    monkeypatch.setattr(edicao_video.videos, "com_cortes_e_ritmo", com_cortes_e_ritmo)
    destino = str(tmp_path / "r.mp4")

    motivo, resumo = edicao_video.editar_2("v.mp4", b"foto", destino, "Conjunto Corset e Saia", "Modelo elegante",
                                           "Confira no produto abaixo", lugar="nenhum")
    # Sem texto, o vídeo vai direto ao Editor 1, sem passar pelo ffmpeg dos textos.
    assert motivo == "" and montados == [] and resumo["textos"] == [] and resumo["lugar"] == "nenhum"

    edicao_video.editar_2("v.mp4", b"foto", destino, "Conjunto Corset e Saia", "", "Confira no produto abaixo",
                          lugar="esquerda")
    margem = edicao_video.LUGARES_DOS_TEXTOS["esquerda"][0]
    assert [(x, topo) for _, _, _, x, topo in montados[-1]] == [(margem, 400), (margem, 400)]

    edicao_video.editar_2("v.mp4", b"foto", destino, "Conjunto Corset e Saia", "", "Confira no produto abaixo",
                          lugar="direita")
    for imagem, _, _, x, topo in montados[-1]:
        # Encostado na direita: a caixa termina à mesma distância da borda que a da esquerda.
        assert topo == 400 and x + int.from_bytes(imagem[16:20], "big") == 720 - margem


def test_texto_da_ia_comprido_nao_termina_em_palavra_de_ligacao():
    # Exemplo do Editor 2 de 27/10: a vantagem passou do limite e o corte deixou
    # "Caimento fluido e amarração na" na tela.
    corta = edicao_video._so_letras
    assert corta("Caimento fluido e amarração na cintura", 36) == "Caimento fluido e amarração"
    assert corta("Mantém gelado por muito tempo com tampa", 36) == "Mantém gelado por muito tempo"
    assert corta("Copo Térmico", 28) == "Copo Térmico"
    assert edicao_video.MAXIMO_DA_VANTAGEM == 36


def _no_original(trechos, segundo):
    """O segundo do vídeo original que a versão mostra no segundo dado dela."""
    for a, b, v in trechos:
        if segundo < (b - a) / v:
            return a + segundo * v
        segundo -= (b - a) / v
    return None


def test_versoes_seguem_do_gancho_e_cada_uma_tem_um_tamanho():
    # Escolha do Rafael (P49): nas versões do conjunto de jardim, todas voltavam ao começo do
    # vídeo depois do gancho e terminavam iguais, com o mesmo tamanho. Agora o 1º vídeo é o
    # completo (pedido de 27/10) e cada versão segue do seu gancho (o que vinha antes vai para
    # o fim), com um tamanho: uns 3/4 do completo e a mais curta.
    trechos = [(0.0, 8.0, 1.0), (8.0, 12.0, edicao_video.ACELERADO), (12.0, 20.0, 1.0)]
    inteira = edicao_video._segundos_remontados(trechos)
    # O 2º gancho começa a 2 s do começo do vídeo (onde o completo começa) e o 3º a 1 s do 1º:
    # não viram versão.
    versoes = edicao_video.planejar_versoes(trechos, [(13.0, 15.0), (2.0, 3.5), (14.0, 15.5), (6.0, 7.0)],
                                            frozenset())
    assert [v["gancho"] for v in versoes] == [0, 3]
    primeira, segunda = versoes
    assert primeira["trechos"] == [(13.0, 20.0, 1.0), (0.0, pytest.approx(7.0), 1.0)] and primeira["curta"]
    assert segunda["trechos"][:2] == [(6.0, 8.0, 1.0), (8.0, 12.0, edicao_video.ACELERADO)] and segunda["curta"]
    assert segunda["trechos"][2][0] == 12.0 and segunda["trechos"][2][1] == pytest.approx(12.0 + inteira * 0.5 - 2.0 - 4.0 / 1.5)
    tamanhos = [edicao_video._segundos_remontados(v["trechos"]) for v in versoes]
    assert tamanhos == pytest.approx([inteira * 0.75, inteira * 0.5])
    # Em nenhum segundo dois vídeos (o completo e as versões) mostram a mesma parte do vídeo.
    todos = [trechos] + [v["trechos"] for v in versoes]
    for n, uma in enumerate(todos):
        for outra in todos[n + 1:]:
            segundos = [t / 10 for t in range(int(min(tamanhos) * 10))]
            assert min(abs(_no_original(uma, t) - _no_original(outra, t)) for t in segundos) >= 2
    # Nenhum pedaço do vídeo aparece duas vezes na mesma versão.
    for versao in versoes:
        pedacos = sorted((a, b) for a, b, _ in versao["trechos"])
        assert all(pedacos[i][1] <= pedacos[i + 1][0] for i in range(len(pedacos) - 1))
    # Vídeo curto: nenhuma versão fica com menos de MINIMO_DO_REMONTADO.
    curtas = edicao_video.planejar_versoes([(0.0, 10.0, 1.0)], [(0.0, 2.0), (5.0, 7.0)], frozenset())
    assert [edicao_video._segundos_remontados(v["trechos"]) for v in curtas] == [edicao_video.MINIMO_DO_REMONTADO]


def test_versao_nao_abre_com_fala_nem_corta_a_fala_e_sem_gancho_so_o_completo():
    # P45: onde alguém fala, o vídeo fica inteiro e na ordem; o gancho nunca tem fala, e o corte
    # do fim de uma versão mais curta não cai no meio de uma fala: ela fica inteira.
    trechos = [(0.0, 12.0, 1.0)]
    com_fala = edicao_video.janelas_com_fala([(0.5, 3.0)], 12.0)
    versoes = edicao_video.planejar_versoes(trechos, [(1.0, 2.5), (6.0, 7.5)], com_fala)
    assert [v["gancho"] for v in versoes] == [1] and versoes[0]["trechos"] == [(6.0, 12.0, 1.0), (0.0, 3.5, 1.0)]
    com_fala = edicao_video.janelas_com_fala([(6.5, 8.0)], 20.0)
    _, segunda = edicao_video.planejar_versoes([(0.0, 20.0, 1.0)], [(3.0, 5.0), (17.0, 18.0)], com_fala)
    assert segunda["curta"] and segunda["trechos"] == [(17.0, 20.0, 1.0), (0.0, 8.5, 1.0)]
    # Gancho fora dos trechos (parte parada que saiu) ou curto demais não serve: só o completo.
    assert edicao_video.planejar_versoes([(0.0, 5.0, 1.0), (8.0, 12.0, 1.0)], [(5.2, 7.8), (3.0, 3.5)],
                                         frozenset()) == []
    assert edicao_video.planejar_versoes(trechos, [], frozenset()) == []


def test_versoes_da_ia(monkeypatch):
    import api_gemini

    def responde(texto):
        async def analisar(video, prompt, imagens=None):
            assert "o vídeo completo e versões diferentes dele" in prompt and "Bolsa" in prompt
            assert "pelo menos 3 segundos entre o começo do vídeo e o começo de um momento" in prompt
            return texto
        monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)

    responde('{"nome": "Bolsa de Palha", "vantagem": "Leve e resistente", "lugar": "esquerda", "falas": [], "versoes": ['
             '{"vantagem": "Várias cores", "inicio": 0.5, "fim": 2.5, "chamada": "Escolha a sua aqui embaixo"},'
             '{"vantagem": "Fechamento com zíper", "inicio": "6", "fim": 8, "chamada": "Toque no produto"},'
             '{"vantagem": "", "inicio": 9, "fim": 10}, {"vantagem": "Torta", "inicio": 5, "fim": 4},'
             '{"vantagem": "Leve", "inicio": 9, "fim": 11, "chamada": "Veja aqui"},'
             '{"vantagem": "Quarta", "inicio": 11, "fim": 12}]}')
    textos = edicao_video.textos_das_versoes("v.mp4", "Bolsa")
    assert textos["nome"] == "Bolsa de Palha" and textos["lugar"] == "esquerda" and textos["falas"] == []
    assert textos["vantagem"] == "Leve e resistente"
    assert [(v["vantagem"], v["inicio"], v["fim"], v["chamada"]) for v in textos["versoes"]] == [
        ("Várias cores", 0.5, 2.5, "Escolha a sua aqui embaixo"), ("Fechamento com zíper", 6.0, 8.0, "Toque no produto"),
        ("Leve", 9.0, 11.0, "Veja aqui")]
    responde("sem JSON")
    assert edicao_video.textos_das_versoes("v.mp4", "Bolsa") == {}


def _versoes_de_mentira(monkeypatch, musicas=None):
    """
    Vídeo de 12 s com 4 s acelerados no meio, e o que o ffmpeg e o Editor 1 receberam (em
    musicas, se vier, a música de fundo de cada vídeo editado).
    """
    monkeypatch.setattr(edicao_video.videos, "duracao", lambda video, timeout=30: 12.0)
    monkeypatch.setattr(edicao_video, "ritmo", lambda movimentos, duracao, por_segundo=10, com_fala=frozenset(): [
        (0.0, 4.0, 1.0), (4.0, 8.0, edicao_video.ACELERADO), (8.0, 12.0, 1.0)])
    monkeypatch.setattr(edicao_video.videos, "movimento", lambda video, por_segundo=10, timeout=120: [])
    montados, editados = [], []

    def com_cortes_e_ritmo(video, trechos, destino, letreiros=(), espera=300):
        montados.append((list(trechos), len(letreiros)))
        return ""

    def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outras_fotos=(),
               rotulo_de_ia=False, cor=None):
        editados.append((os.path.basename(video), os.path.basename(destino)))
        if musicas is not None:
            musicas.append(os.path.basename(musica) if musica else None)
        return ""
    monkeypatch.setattr(edicao_video.videos, "com_cortes_e_ritmo", com_cortes_e_ritmo)
    monkeypatch.setattr(edicao_video, "editar", editar)
    return montados, editados


VERSOES_DA_IA = [{"vantagem": "Fechamento com zíper", "inicio": 9.0, "fim": 10.5, "chamada": "Toque no produto"},
                 {"vantagem": "Várias cores", "inicio": 4.5, "fim": 6.0, "chamada": "Escolha a sua"}]


def test_editor_1_entrega_o_original_e_as_versoes_remontadas_sem_textos(monkeypatch, tmp_path):
    # Pedidos do Rafael (27/10): o Editor 1 sem legendas entrega o vídeo completo e as versões,
    # cada uma seguindo do seu momento e com um tamanho (P49). (Vídeo de 28/10, 00:12) o mesmo
    # padrão do Editor 2: o original sem cortes e as versões remontadas, só sem legendas.
    montados, editados = _versoes_de_mentira(monkeypatch)
    motivo, resumo = edicao_video.editar_1_e_versoes("v.mp4", b"foto", str(tmp_path / "exemplo.mp4"), VERSOES_DA_IA, falas=[])
    # O original vai inteiro direto ao Editor 1; as versões são remontadas antes.
    assert motivo == "" and editados == [("v.mp4", "exemplo_1.mp4"), ("remontado_2.mp4", "exemplo_2.mp4"),
                                         ("remontado_3.mp4", "exemplo_3.mp4")]
    # As mesmas versões do Editor 2 (o trecho calmo acelerado), sem nenhum texto por cima.
    montados_1 = list(montados)
    montados.clear()
    edicao_video.editar_2_e_versoes("v.mp4", b"foto", str(tmp_path / "exemplo.mp4"), "Bolsa de Palha", "Leve",
                                    VERSOES_DA_IA, "Garanta a sua aqui embaixo", falas=[], lugar="alto")
    assert [m[0] for m in montados_1] == [m[0] for m in montados[1:]]
    assert [m[0][0] for m in montados_1] == [(9.0, 12.0, 1.0), (4.5, 8.0, edicao_video.ACELERADO)]
    assert [m[1] for m in montados_1] == [0, 0]
    assert all(not v["textos"] for v in resumo["versoes"]) and resumo["inteiro"] == 12.0
    assert resumo["remontagem"]["acelerados"] == 1
    assert [(v["gancho"], v["curta"]) for v in resumo["versoes"]] == [
        (None, False), ((9.0, 10.5), True), ((4.5, 6.0), True)]
    assert [v["remontado"] for v in resumo["versoes"]] == [
        12.0, pytest.approx(9.0), pytest.approx(edicao_video.MINIMO_DO_REMONTADO)]
    assert [v["vantagem"] for v in resumo["versoes"]] == ["", "Fechamento com zíper", "Várias cores"]
    # Sem momento que sirva, só o original: o próprio vídeo com o Editor 1, sem remontar.
    montados.clear()
    editados.clear()
    _, resumo = edicao_video.editar_1_e_versoes("v.mp4", b"foto", str(tmp_path / "exemplo.mp4"), [], falas=[])
    assert montados == [] and editados == [("v.mp4", "exemplo_1.mp4")]
    assert [v["gancho"] for v in resumo["versoes"]] == [None]


def test_editor_2_entrega_o_completo_e_cada_versao_com_os_textos_dela(monkeypatch, tmp_path):
    # Pedidos do Rafael (27/10): o Editor 2 com legendas entrega o vídeo completo e as versões;
    # (vídeo de 28/10) o 1º é o vídeo original, sem cortes nem mudança de velocidade, só com as
    # edições; as versões é que são modificadas.
    montados, editados = _versoes_de_mentira(monkeypatch)
    motivo, resumo = edicao_video.editar_2_e_versoes("v.mp4", b"foto", str(tmp_path / "exemplo.mp4"), "Bolsa de Palha",
                                           "Leve e resistente", VERSOES_DA_IA, "Garanta a sua aqui embaixo", falas=[],
                                           lugar="alto")
    assert motivo == "" and [e[1] for e in editados] == ["exemplo_1.mp4", "exemplo_2.mp4", "exemplo_3.mp4"]
    # O 1º é o vídeo inteiro, numa parte só e na velocidade dele, com os 3 textos.
    assert montados[0] == ([(0.0, 12.0, 1.0)], 3)
    # As versões são remontadas (o trecho calmo acelerado) e abrem no seu momento.
    assert [m[0][0] for m in montados[1:]] == [(9.0, 12.0, 1.0), (4.5, 8.0, edicao_video.ACELERADO)]
    assert [m[1] for m in montados[1:]] == [3, 3]
    # Até uns 3/4 e 1/2 do vídeo original (12 s), nunca menos de 8 s.
    assert [edicao_video._segundos_remontados(m[0]) for m in montados[1:]] == [
        pytest.approx(9.0), pytest.approx(edicao_video.MINIMO_DO_REMONTADO)]
    completo, segunda, terceira = resumo["versoes"]
    assert resumo["inteiro"] == 12.0 and completo["remontado"] == 12.0
    # O que a remontagem muda nas versões, para a legenda delas.
    assert resumo["remontagem"]["acelerados"] == 1 and resumo["remontagem"]["cortado"] == 0
    # O preço não entra mais (P80): o original fecha com a chamada da IA para o produto.
    assert completo["gancho"] is None and completo["textos"] == [
        "Bolsa de Palha", "Leve e resistente", "Garanta a sua aqui embaixo"]
    # Nas versões, a vantagem do gancho abre e a chamada da versão fecha.
    assert segunda["textos"] == ["Fechamento com zíper", "Bolsa de Palha", "Toque no produto"]
    assert terceira["textos"][0] == "Várias cores" and terceira["textos"][-1] == "Escolha a sua"
    assert segunda["gancho"] == (9.0, 10.5) and segunda["curta"] and not completo["curta"]
    # Sem lugar livre (P47), todos vão sem os textos.
    montados.clear()
    _, resumo = edicao_video.editar_2_e_versoes("v.mp4", b"foto", str(tmp_path / "exemplo.mp4"), "Bolsa", "Leve",
                                      VERSOES_DA_IA, "Garanta a sua aqui embaixo", falas=[], lugar="nenhum")
    # O original vai direto ao Editor 1 (sem texto, nada a pôr por cima); as versões, sem texto.
    assert [m[1] for m in montados] == [0, 0] and all(v["textos"] == [] for v in resumo["versoes"])


def _textos_da_tela(monkeypatch, textos):
    """A IA de mentira dos textos da tela; devolve os nomes de produto que ela recebeu."""
    pedidos = []
    monkeypatch.setattr(edicao_video, "textos_da_tela", lambda video, nome: pedidos.append(nome) or dict(textos))
    return pedidos


def test_o_que_vai_ao_ar_e_o_completo_do_editor_2_com_as_legendas(monkeypatch, tmp_path):
    # Escolhas do Rafael (28/10, P50 e o vídeo seguinte): os rascunhos do robô e o modo
    # assistente vão com o vídeo original do Editor 2 (a foto, a miniatura, a seta e as
    # legendas, sem cortes); as versões modificadas ficam só no exemplo.
    montados, editados = _versoes_de_mentira(monkeypatch)
    pedidos = _textos_da_tela(monkeypatch, {"nome": "Bolsa de Palha", "vantagem": "Leve e resistente",
                                            "chamada": "Garanta a sua aqui embaixo", "falas": [], "lugar": "alto"})
    destino = str(tmp_path / "rascunho.mp4")
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa Palha Marca X") == (
        "", edicao_video.COM_LEGENDAS, "")
    # Um vídeo só: a remontagem inteira com o nome, a vantagem e a chamada, e o Editor 1 por cima.
    assert pedidos == ["Bolsa Palha Marca X"]
    # O vídeo original inteiro, sem cortes nem mudança de velocidade (pedido do Rafael, 28/10).
    assert montados == [([(0.0, 12.0, 1.0)], 3)]
    assert editados == [("com_textos.mp4", "rascunho.mp4")]
    # Sem lugar livre do produto e do rosto (P47), o Editor 2 vai sem os textos, e o registro diz por quê.
    _textos_da_tela(monkeypatch, {"nome": "Bolsa de Palha", "vantagem": "Leve", "falas": [], "lugar": "nenhum"})
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa") == (
        "", edicao_video.SEM_LEGENDAS_NA_TELA, edicao_video.SEM_LUGAR_LIVRE)
    # Escolha do Rafael (P52): o vídeo que já tem texto próprio na tela vai sem as nossas legendas.
    montados.clear()
    _textos_da_tela(monkeypatch, {"nome": "Presilha", "vantagem": "Firme", "lugar": "alto", "texto_no_video": True})
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Presilha") == (
        "", edicao_video.SEM_LEGENDAS_NA_TELA, edicao_video.TEXTO_JA_NO_VIDEO)
    assert montados == []
    # Sem a resposta da IA, o vídeo vai sem os textos (o preço não entra mais, P80).
    _textos_da_tela(monkeypatch, {})
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa") == (
        "", edicao_video.SEM_LEGENDAS_NA_TELA, edicao_video.SEM_OS_TEXTOS_DA_IA)
    assert montados == []


def test_sem_o_editor_2_o_que_vai_ao_ar_e_o_editor_1(monkeypatch, tmp_path):
    # Escolha do Rafael (28/10, P51): se o Editor 2 não sai, o vídeo vai com o Editor 1 (foto,
    # miniatura e seta, sem legendas), e o detalhe diz por quê.
    montados, editados = _versoes_de_mentira(monkeypatch)
    _textos_da_tela(monkeypatch, {"nome": "Bolsa", "vantagem": "Leve", "falas": [], "lugar": "alto"})
    monkeypatch.setattr(edicao_video.videos, "com_cortes_e_ritmo",
                        lambda video, trechos, destino, letreiros=(), espera=300: "o ffmpeg falhou")
    destino = str(tmp_path / "rascunho.mp4")
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa") == (
        "", edicao_video.SO_COM_O_EDITOR_1, "o Editor 2 não saiu: o ffmpeg falhou")
    assert editados == [("v.mp4", "rascunho.mp4")]

    # Um erro no meio do Editor 2 também.
    def quebra(*args, **kwargs):
        raise RuntimeError("quebrou")
    monkeypatch.setattr(edicao_video, "editar_2", quebra)
    editados.clear()
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa") == (
        "", edicao_video.SO_COM_O_EDITOR_1, "o Editor 2 não saiu: erro (RuntimeError)")
    assert editados == [("v.mp4", "rascunho.mp4")]


def test_sem_a_foto_nada_vai_ao_ar_e_a_ia_nem_e_chamada(monkeypatch, tmp_path):
    _programas(monkeypatch)
    pedidos = _textos_da_tela(monkeypatch, {"nome": "Bolsa"})
    motivo, _, _ = edicao_video.editar_para_postar("v.mp4", None, str(tmp_path / "r.mp4"), "Bolsa")
    assert motivo == "a foto do anúncio não veio" and pedidos == [] and not os.path.exists(tmp_path / "r.mp4")


def test_bebida_alcoolica_vai_ao_ar_com_os_avisos_no_editor_2_e_no_editor_1(monkeypatch, tmp_path):
    # Escolha do Rafael (26/10, P43): a capa com os avisos abre o vídeo, com o Editor 2 também.
    _versoes_de_mentira(monkeypatch)
    _textos_da_tela(monkeypatch, {"nome": "Vinho Tinto", "vantagem": "Encorpado", "falas": [], "lugar": "alto"})
    avisos = []

    def editar(video, foto, destino, com_avisos=False, musica=None, capa=None, miniatura=True,
               outras_fotos=(), rotulo_de_ia=False, cor=None):
        avisos.append(com_avisos)
        return ""
    monkeypatch.setattr(edicao_video, "editar", editar)
    destino = str(tmp_path / "r.mp4")
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Vinho", avisos=True)[1] == (
        edicao_video.COM_LEGENDAS + edicao_video.COM_OS_AVISOS)
    monkeypatch.setattr(edicao_video.videos, "com_cortes_e_ritmo",
                        lambda video, trechos, destino, letreiros=(), espera=300: "o ffmpeg falhou")
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Vinho", avisos=True)[1] == (
        edicao_video.SO_COM_O_EDITOR_1 + edicao_video.COM_OS_AVISOS)
    assert avisos == [True, True]


def test_textos_da_tela_pede_so_o_do_video_completo(monkeypatch):
    import api_gemini
    pedidos = []

    async def analisar(video, prompt, imagens=None):
        pedidos.append(prompt)
        return ('{"nome": "Copo Térmico", "vantagem": "Mantém gelado 🧊", "lugar": "meio", '
                '"capa": "Copo sempre gelado", "textos_do_video": [{"inicio": 0, "fim": 9}]}')

    monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(edicao_video.videos, "duracao", lambda video, timeout=30: 10.0)
    textos = edicao_video.textos_da_tela("v.mp4", "Copo Marca X")
    assert textos == {"nome": "Copo Térmico", "vantagem": "Mantém gelado", "lugar": "meio", "texto_no_video": True,
                      "parte_com_texto": 0.9, "capa": "Copo sempre gelado"}
    assert "Copo Marca X" in pedidos[0] and "versoes" not in pedidos[0] and "textos_do_video" in pedidos[0]
    # O vídeo com texto próprio na tela fica sem lugar para as nossas legendas (P52).
    assert edicao_video.lugar_dos_textos(textos) == edicao_video.SEM_LUGAR
    assert edicao_video.lugar_dos_textos({"lugar": "meio", "texto_no_video": False}) == "meio"


def test_texto_da_ia_com_letra_fora_do_portugues_e_corrigido_ou_sai(monkeypatch):
    # 30/10: a capa com chamada saiu com "Por dentro tem pelüia bem macia" (o certo é pelúcia), e o
    # Rafael recusou o rascunho. Letra que não existe no português faz a IA reescrever só o texto;
    # sem conserto, o texto sai (a capa de sempre), e o registro anota.
    import api_gemini
    import registro_processos as rp
    correcoes = []

    async def analisar(video, prompt, imagens=None):
        return ('{"nome": "Meia-Calça Térmica", "vantagem": "Por dentro tem pelüia bem macia", '
                '"chamada": "Confira aqui embaixo", "capa": "Meia-calça quentinha"}')

    async def corrigir(prompt, imagens=None):
        if prompt.startswith("Revise a ortografia"):
            return None
        correcoes.append(prompt)
        return correcoes_da_ia.pop(0)

    monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", corrigir)
    correcoes_da_ia = ['"Por dentro tem pelúcia bem macia"']
    textos = edicao_video.textos_da_tela("v.mp4", "Meia")
    assert textos["vantagem"] == "Por dentro tem pelúcia bem macia" and textos["nome"] == "Meia-Calça Térmica"
    assert len(correcoes) == 1 and "pelüia" in correcoes[0]
    # A correção que volta errada (ou nada) tira o texto: a vantagem não vai para a capa.
    correcoes_da_ia = ["Por dentro tem pelüia bem macia"]
    assert "vantagem" not in edicao_video.textos_da_tela("v.mp4", "Meia")
    correcoes_da_ia = [None]
    assert "vantagem" not in edicao_video.textos_da_tela("v.mp4", "Meia")
    linhas = [(l[2], l[5]) for l in rp.contagem("2000-01-01 00:00:00")
              if l[1] == edicao_video.PROCESSO_DA_ORTOGRAFIA and l[2] in ("corrigida", "texto tirado")]
    assert sorted(linhas) == [("corrigida", 1), ("texto tirado", 2)]
    assert edicao_video.letras_fora_do_portugues("Ação, pão e crème") == ["è"]
    assert edicao_video.letras_fora_do_portugues("Mantém gelado o dia todo, 100% à prova") == []
    assert edicao_video.letras_fora_do_portugues("Qualidade de 1ª linha, nº 1") == []
    assert "ortografia" in edicao_video.PROMPT_DOS_TEXTOS and "ortografia" in edicao_video.PROMPT_DAS_VERSOES


def test_revisao_pega_o_erro_so_com_letras_do_portugues(monkeypatch):
    # Pedido do Rafael (30/10): pegar também o erro feito só com letras do português (o acento que
    # falta, a letra trocada), que a conferência das letras não vê. Uma chamada de texto revisa
    # todos os textos do vídeo de uma vez, e fica só a revisão que mexeu na ortografia.
    import json
    import re

    import api_gemini
    import registro_processos as rp
    pedidos = []
    revisoes = {"Garrafa Termica": "Garrafa Térmica", "Mantem gelado o dia todo": "Mantém gelado o dia todo",
                "Toque no produtu": "Toque no produto",
                "Gelada por horas": "Compre agora a melhor garrafa do Brasil"}

    async def analisar(video, prompt, imagens=None):
        return ('{"nome": "Garrafa Termica", "vantagem": "Mantem gelado o dia todo", "chamada": "Veja aqui embaixo", '
                '"capa": "Garrafa bem gelada", '
                '"versoes": [{"vantagem": "Gelada por horas", "inicio": 1, "fim": 3, "chamada": "Toque no produtu"}]}')

    async def revisar(prompt, imagens=None):
        pedidos.append(prompt)
        textos = json.loads(re.search(r"\{.*\}", prompt, re.S).group(0))
        return json.dumps({chave: revisoes.get(texto, texto) for chave, texto in textos.items()}, ensure_ascii=False)

    monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", revisar)
    textos = edicao_video.textos_da_tela("v.mp4", "Garrafa")
    assert (textos["nome"], textos["vantagem"], textos["chamada"]) == (
        "Garrafa Térmica", "Mantém gelado o dia todo", "Veja aqui embaixo")
    assert len(pedidos) == 1 and pedidos[0].startswith("Revise a ortografia") and "Mantem gelado" in pedidos[0]
    # As versões do exemplo vão na mesma chamada; a revisão que muda a frase não vale.
    pedidos.clear()
    textos = edicao_video.textos_das_versoes("v.mp4", "Garrafa")
    assert len(pedidos) == 1 and textos["vantagem"] == "Mantém gelado o dia todo"
    assert [(v["vantagem"], v["chamada"]) for v in textos["versoes"]] == [("Gelada por horas", "Toque no produto")]
    # Sem resposta, os textos ficam como a IA os deu.
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", lambda prompt, imagens=None: _sem_resposta())
    assert edicao_video.textos_da_tela("v.mp4", "Garrafa")["nome"] == "Garrafa Termica"
    linhas = [(l[2], l[3]) for l in rp.contagem("2000-01-01 00:00:00") if l[1] == edicao_video.PROCESSO_DA_ORTOGRAFIA]
    assert sorted(linhas) == [("revisada", "2 corrigido(s)"), ("revisada", "3 corrigido(s)"),
                              ("sem a revisão", "a IA não respondeu")]
    # Só a ortografia: palavra a mais, texto maior que o máximo, letra fora do português ou nada mudado não valem.
    assert edicao_video._so_ortografia("Mantem gelado", "Mantém gelado", 36) == "Mantém gelado"
    assert edicao_video._so_ortografia("Leve", "Leve e muito resistente", 36) == ""
    assert edicao_video._so_ortografia("Copo Termico de Inox Grande", "Copo Térmico de Inox Grandes", 27) == ""
    assert edicao_video._so_ortografia("pelucia macia", "pelüia macia", 36) == ""
    assert edicao_video._so_ortografia("Leve", "Leve", 36) == ""


async def _sem_resposta():
    return None


def test_remontar_pode_trocar_a_ordem_dos_trechos(tmp_path):
    # Os Editores 3 e 4 abrem cada versão com um momento do meio do vídeo: o ffmpeg monta na ordem da lista.
    if not shutil.which("ffmpeg"):
        return
    from PIL import Image
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:size=360x640:rate=30:duration=2",
                    "-f", "lavfi", "-i", "color=c=green:size=360x640:rate=30:duration=2",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", str(video)], check=True)
    destino = tmp_path / "r.mp4"
    assert edicao_video.videos.com_cortes_e_ritmo(str(video), [(2.0, 4.0, 1.0), (0.0, 2.0, 1.0)], str(destino)) == ""

    def cor(segundo):
        quadro = tmp_path / f"q_{segundo}.ppm"
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(segundo), "-i", str(destino), "-frames:v", "1",
                        str(quadro)], check=True)
        with Image.open(quadro) as imagem:
            return imagem.convert("RGB").getpixel((360, 640))
    vermelho, verde, _ = cor(0.5)
    assert verde > 100 and vermelho < 80
    vermelho, verde, _ = cor(3.0)
    assert vermelho > 150 and verde < 80


def test_as_tres_musicas_de_fundo_estao_na_midia():
    # Escolha do Rafael (28/10, P55): 3 músicas feitas pelo Claude do zero (animada, calma e
    # divertida), sem música de ninguém, para os vídeos sem som.
    assert [nome for nome, _ in edicao_video.MUSICAS] == ["animada", "calma", "divertida"]
    for _, arquivo in edicao_video.MUSICAS:
        caminho = os.path.join(edicao_video.PASTA_DA_MIDIA, arquivo)
        assert os.path.getsize(caminho) > 100_000


def test_video_sem_som_ganha_a_musica_da_vez_e_o_rodizio_anda(monkeypatch):
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    db.salvar_config("shopee_video", {"edicao_ligada": True})
    monkeypatch.setattr(edicao_video.videos, "mudo", lambda video: False)
    assert edicao_video.musicas_de_fundo("com_som.mp4", 3) == [None, None, None]
    monkeypatch.setattr(edicao_video.videos, "mudo", lambda video: True)
    nomes = [edicao_video.musicas_de_fundo("mudo.mp4")[0][0] for _ in range(4)]
    assert nomes == ["animada", "calma", "divertida", "animada"]
    # Cada versão do exemplo leva outra música, a partir da da vez.
    assert [m[0] for m in edicao_video.musicas_de_fundo("mudo.mp4", 3)] == ["calma", "divertida", "animada"]
    assert edicao_video.musicas_de_fundo("mudo.mp4")[0][1].endswith(os.path.join("midia", "musica_divertida.m4a"))
    # A vez fica junto da configuração, sem apagar o resto.
    assert db.ler_config("shopee_video", {})["edicao_ligada"]


def test_o_que_vai_ao_ar_sem_som_leva_a_musica_e_o_registro_diz(monkeypatch, tmp_path):
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    musicas = []
    _versoes_de_mentira(monkeypatch, musicas)
    _textos_da_tela(monkeypatch, {"nome": "Bolsa de Palha", "vantagem": "Leve", "falas": [], "lugar": "alto"})
    monkeypatch.setattr(edicao_video.videos, "mudo", lambda video: True)
    destino = str(tmp_path / "rascunho.mp4")
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa") == (
        "", edicao_video.COM_LEGENDAS + edicao_video.COM_MUSICA, "")
    assert musicas == ["musica_animada.m4a"]
    # Com som, nada muda.
    monkeypatch.setattr(edicao_video.videos, "mudo", lambda video: False)
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa")[1] == edicao_video.COM_LEGENDAS
    assert musicas[-1] is None


def test_exemplo_sem_som_tem_uma_musica_em_cada_video(monkeypatch, tmp_path):
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    musicas = []
    _versoes_de_mentira(monkeypatch, musicas)
    monkeypatch.setattr(edicao_video.videos, "mudo", lambda video: True)
    _, resumo = edicao_video.editar_1_e_versoes("v.mp4", b"foto", str(tmp_path / "exemplo.mp4"), VERSOES_DA_IA,
                                                falas=[])
    assert musicas == ["musica_animada.m4a", "musica_calma.m4a", "musica_divertida.m4a"]
    assert [v["musica"] for v in resumo["versoes"]] == ["animada", "calma", "divertida"]
    musicas.clear()
    _, resumo = edicao_video.editar_2_e_versoes("v.mp4", b"foto", str(tmp_path / "exemplo.mp4"), "Bolsa", "Leve",
                                                VERSOES_DA_IA, "Garanta a sua aqui embaixo", falas=[], lugar="alto")
    assert musicas == ["musica_calma.m4a", "musica_divertida.m4a", "musica_animada.m4a"]
    assert [v["musica"] for v in resumo["versoes"]] == ["calma", "divertida", "animada"]


def test_comando_com_musica_poe_ela_no_video_inteiro_em_laco(monkeypatch, tmp_path):
    comandos = _programas(monkeypatch, audio="")
    monkeypatch.setattr(edicao_video.videos, "duracao", lambda video, timeout=30: 10.0)
    assert edicao_video.editar("video.mp4", b"foto", str(tmp_path / "r.mp4"), musica="musica.m4a") == ""
    ffmpeg = comandos[-1]
    texto = " ".join(ffmpeg)
    filtro = ffmpeg[ffmpeg.index("-filter_complex") + 1]
    assert "-stream_loop -1 -i musica.m4a" in texto and "anullsrc" not in texto
    # A música é a 5ª entrada (foto, vídeo, miniatura, seta), do começo da foto ao fim: 2 + 10 s.
    assert "[4:a]aresample=44100,aformat=channel_layouts=stereo,atrim=0:12.000" in filtro
    assert "afade=t=in:d=0.3" in filtro and "afade=t=out:st=10.500:d=1.5[a]" in filtro
    assert "[1:a]" not in filtro and "[a]" in ffmpeg


def test_edicao_de_verdade_do_video_sem_som_sai_com_a_musica(tmp_path):
    if not shutil.which("ffmpeg"):
        return
    video, foto = tmp_path / "v.mp4", tmp_path / "foto.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0xf0e0c0:size=360x640:rate=30:duration=3",
                    str(video)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x3060a0:size=200x200",
                    "-frames:v", "1", str(foto)], check=True)
    assert edicao_video.videos.mudo(str(video))
    destino = tmp_path / "editado.mp4"
    musica = os.path.join(edicao_video.PASTA_DA_MIDIA, "musica_calma.m4a")
    assert edicao_video.editar(str(video), foto.read_bytes(), str(destino), musica=musica) == ""
    assert not edicao_video.videos.mudo(str(destino))
    assert abs(edicao_video.videos.duracao(str(destino)) - 5.0) < 0.3


# --- A capa com chamada (escolha do Rafael, 29/10, P76) ---

def _capa(chamada):
    import io

    from PIL import Image
    return Image.open(io.BytesIO(edicao_video.capa_com_chamada(_foto_jpg(), chamada))).convert("RGB")


def _claros(imagem, caixa, passo=4):
    x1, y1, x2, y2 = caixa
    return sum(1 for x in range(x1, x2, passo) for y in range(y1, y2, passo) if min(imagem.getpixel((x, y))) > 200)


def _cor_de(imagem, ponto, cor):
    return max(abs(a - b) for a, b in zip(imagem.getpixel(ponto), cor)) < 8


def _pretos(imagem, caixa, passo=4):
    x1, y1, x2, y2 = caixa
    return all(max(imagem.getpixel((x, y))) < 20 for x in range(x1, x2, passo) for y in range(y1, y2, passo))


def test_capa_da_grade_com_a_foto_quadrada_tampa_o_que_a_grade_mostra_e_a_faixa_desce_ate_embaixo():
    # Vídeo do Rafael das 20:14 de 02/11: sem as laterais laranja, um fio laranja em cima da foto e,
    # no pé, a faixa laranja com a frase em letras brancas (P107). Print das 21:09 de 06/11 (P168): a
    # grade do celular dele mostra o quadro com a largura toda, e a foto quadrada aumenta, sem
    # deformar, até tampar tudo do fio à faixa. Vídeo das 23:29 de 06/11 (P171): a faixa desce até o
    # fim do quadro na mesma cor, e a frase, maior, fica no meio dela, não em cima, logo acima do
    # número de visualizações, que fica por cima da faixa.
    capa = _capa("Organize sua cozinha")
    assert capa.size == edicao_video.TELA
    _esquerda, _cima, _direita, faixa = edicao_video.lugar_da_foto()
    fio = edicao_video.FIO_DA_CAPA_NA_GRADE
    alto, baixo = edicao_video.GRADE_NO_CELULAR
    topo = alto + fio
    # Vídeo das 01:04 de 07/11: o fio que a grade mostra, mais grosso que o do vídeo aberto.
    assert edicao_video.FIO_DA_CAPA < fio <= 20 and alto < topo < faixa < baixo
    # A foto, aumentada sem deformar, de uma beirada à outra, do fio até a faixa, sem nada por cima:
    # a quadrada perde só um pouco em cima e embaixo.
    foto = edicao_video._foto_que_tampa(_foto_jpg(), 720, faixa - topo)
    assert foto.size == (720, faixa - topo) and (faixa - topo) / 720 >= 1 - edicao_video.CORTE_MAXIMO_AO_TAMPAR
    assert capa.crop((0, topo, 720, faixa)).tobytes() == foto.tobytes()
    # O fio no alto do que a grade mostra, de uma beirada à outra, vem do alto do quadro: nada fica no
    # preto do fundo, nem se a grade mostrar um pouco mais do quadro (vídeo das 01:04 de 07/11).
    for ponto in [(0, 0), (360, alto - 30), (0, alto), (360, topo - 1), (719, alto + fio // 2)]:
        assert _cor_de(capa, ponto, edicao_video.LARANJA_DA_SHOPEE), ponto
    assert not any(max(capa.getpixel((x, y))) < 20 for x in range(0, 720, 3) for y in range(0, 1280, 3))
    # A faixa logo abaixo da foto, de uma beirada à outra e até o fim do quadro.
    for ponto in [(0, faixa), (719, faixa), (360, faixa + 2), (3, baixo - 1), (716, 1279), (360, 1279)]:
        assert _cor_de(capa, ponto, edicao_video.LARANJA_DA_SHOPEE), ponto
    # As letras brancas só na faixa, no meio do retângulo dela à direita do número de visualizações
    # (do lugar do número até a beirada da grade e do alto da faixa até o pé do que a grade mostra),
    # na maior letra que cabe nele, e o número fica livre (vídeos do Rafael de 07/11, 01:04 e 01:31).
    x1, y1, x2, y2 = edicao_video.NUMERO_DA_GRADE
    esquerda, cima_das_letras, direita, pe_das_letras = edicao_video.lugar_das_letras_na_grade()
    assert x1 < edicao_video.FIM_DO_NUMERO < esquerda and faixa < cima_das_letras and y2 < pe_das_letras <= baixo
    letras = [(x, y) for x in range(720) for y in range(faixa, 1280) if min(capa.getpixel((x, y))) > 200]
    assert letras and _claros(capa, (0, 0, 720, faixa)) == 0
    xs, ys = [x for x, _y in letras], [y for _x, y in letras]
    assert esquerda - 1 <= min(xs) and max(xs) <= direita and cima_das_letras - 1 <= min(ys) and max(ys) <= pe_das_letras
    assert abs((min(xs) + max(xs)) / 2 - (esquerda + direita - 1) / 2) <= 3
    assert abs((min(ys) + max(ys)) / 2 - (cima_das_letras + pe_das_letras - 1) / 2) <= 3
    assert (max(xs) - min(xs) + 1 >= 0.9 * (direita - esquerda) or
            max(ys) - min(ys) + 1 >= 0.9 * (pe_das_letras - cima_das_letras))
    assert _claros(capa, (0, faixa, edicao_video.FIM_DO_NUMERO + 1, 1280), passo=1) == 0
    assert faixa < y1 and y2 < baixo
    # O número com até 2 algarismos fica livre (P172 3).
    assert all(_cor_de(capa, (x, y), edicao_video.LARANJA_DA_SHOPEE)
               for x in range(x1, edicao_video.FIM_DO_NUMERO, 4) for y in range(y1, y2, 4))
    # A sacolinha da Shopee fica por cima do canto de cima da foto (P139 2).
    assert topo < edicao_video.SACOLINHA_DA_GRADE[1] and not _pretos(capa, edicao_video.SACOLINHA_DA_GRADE)


def test_capa_da_grade_sem_preto_com_o_fio_mais_grosso_e_a_frase_grande_a_direita_do_numero():
    # Vídeo do Rafael das 01:04 de 07/11: o fio de cima quase sumia na grade ("pode dar uma
    # aumentadinha nela"), havia uma faixinha preta do fundo ("não é para ter nada de preto ali") e a
    # frase não aproveitava a faixa. Vídeo das 01:31: a frase no retângulo à direita do número de
    # visualizações, do alto da faixa até embaixo, no meio dele, em letras grandes, em duas linhas se
    # precisar.
    import io

    from PIL import Image

    def foto(largura, altura):
        saida = io.BytesIO()
        Image.new("RGB", (largura, altura), (128, 128, 128)).save(saida, "PNG")
        return saida.getvalue()

    marrom = (124, 84, 56)
    alto = edicao_video.GRADE_NO_CELULAR[0]
    faixa = edicao_video.lugar_da_foto()[3]
    for tamanho in ((800, 800), (800, 600), (600, 800), (1200, 500)):
        capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(foto(*tamanho), "Potes para biscoitos",
                                                                   cor=marrom))).convert("RGB")
        # Nada no preto do fundo, no quadro todo.
        assert not any(max(capa.getpixel((x, y))) < 30 for x in range(0, 720, 2) for y in range(0, 1280, 2)), tamanho
        # O fio vem do alto do quadro e a grade mostra 16 px dele, o dobro de antes.
        assert all(_cor_de(capa, (x, y), marrom) for x in (0, 360, 719) for y in range(0, alto + 16)), tamanho
        assert _cor_de(capa, (360, alto + 17), (128, 128, 128)), tamanho
    # A frase em duas linhas grandes no retângulo à direita do número: nada dela no lugar do número.
    esquerda, cima, direita, baixo = edicao_video.lugar_das_letras_na_grade()
    assert edicao_video.NUMERO_DA_GRADE[0] < edicao_video.FIM_DO_NUMERO < esquerda < direita <= 720
    assert faixa < cima < edicao_video.NUMERO_DA_GRADE[1] < edicao_video.NUMERO_DA_GRADE[3] < baixo
    letras = [(x, y) for x in range(720) for y in range(faixa, 1280) if min(capa.getpixel((x, y))) > 200]
    xs, ys = [x for x, _y in letras], [y for _x, y in letras]
    assert min(xs) >= esquerda - 1 and max(xs) <= direita and min(ys) >= cima - 1 and max(ys) <= baixo
    linhas_com_letras = sorted(set(ys))
    vaos = [b - a for a, b in zip(linhas_com_letras, linhas_com_letras[1:]) if b - a > 1]
    assert len(vaos) == 1, "duas linhas"
    # Bem maior que a letra de uma linha só que cabia antes (até 84, P171).
    assert max(ys) - min(ys) + 1 > 1.5 * 84 and max(xs) - min(xs) + 1 >= 0.9 * (direita - esquerda)


def test_foto_quase_quadrada_tampa_e_a_outra_fica_inteira():
    # P168: só a foto que perde no máximo CORTE_MAXIMO_AO_TAMPAR ao tampar aumenta cortando (a
    # quadrada, a um pouco mais alta ou mais larga); a outra não é cortada (estica, P169 1). A que
    # não abre não tampa.
    import io

    from PIL import Image

    def foto(largura, altura):
        saida = io.BytesIO()
        Image.new("RGB", (largura, altura), (200, 120, 40)).save(saida, "JPEG")
        return saida.getvalue()

    for largura, altura in ((800, 800), (1000, 1000), (770, 800), (800, 780)):
        assert edicao_video._foto_que_tampa(foto(largura, altura), 720, 728).size == (720, 728), (largura, altura)
    for largura, altura in ((800, 600), (600, 800), (800, 700), (700, 800)):
        assert edicao_video._foto_que_tampa(foto(largura, altura), 720, 728) is None, (largura, altura)
    assert edicao_video._foto_que_tampa(b"nao e imagem", 720, 728) is None
    # Na capa da grade com a faixa da P171, a quadrada continua tampando.
    _esquerda, _cima, _direita, faixa = edicao_video.lugar_da_foto()
    lugar = (720, faixa - edicao_video.GRADE_NO_CELULAR[0] - edicao_video.FIO_DA_CAPA_NA_GRADE)
    for largura, altura in ((800, 800), (1000, 1000), (840, 800)):
        assert edicao_video._foto_que_tampa(foto(largura, altura), *lugar).size == lugar, (largura, altura)
    # O corte sai por igual dos dois lados: o meio da foto fica no meio.
    listrada = Image.new("RGB", (800, 780), (0, 0, 0))
    listrada.paste((255, 255, 255), (390, 0, 410, 780))
    saida = io.BytesIO()
    listrada.save(saida, "PNG")
    tampada = edicao_video._foto_que_tampa(saida.getvalue(), 720, 728)
    brancos = [x for x in range(720) if min(tampada.getpixel((x, 364))) > 200]
    assert abs((min(brancos) + max(brancos)) / 2 - 359.5) <= 2


def test_capa_da_grade_com_a_foto_que_nao_e_quadrada_estica_ate_15_e_o_resto_fica_desfocado():
    # P169 1 (vídeo do Rafael das 23:29 de 06/11): a foto que não é quase quadrada (a mais larga,
    # quando o robô corta as letras do anúncio, ou a de pé) estica só até 15% na direção em que
    # falta e, se ainda não tampar, o que faltar fica com a própria foto desfocada; nada de preto
    # no que a grade mostra, e nada da foto é cortado. A faixa desce até o fim do quadro (P171).
    import io

    from PIL import Image

    def listrada(largura, altura):
        imagem = Image.new("RGB", (largura, altura), (200, 120, 40))
        for x in range(0, largura, 40):
            imagem.paste((40, 90, 200), (x, 0, x + 20, altura))
        saida = io.BytesIO()
        imagem.save(saida, "PNG")
        return saida.getvalue(), imagem

    x1, cima, x2, faixa = edicao_video.lugar_da_foto()
    fio = edicao_video.FIO_DA_CAPA_NA_GRADE
    alto, baixo = edicao_video.GRADE_NO_CELULAR
    largura, altura = x2 - x1, faixa - cima - fio
    assert (x1, x2, cima) == (0, edicao_video.TELA[0], alto)
    for tamanho in ((800, 560), (800, 680), (600, 800)):
        foto, imagem = listrada(*tamanho)
        capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(foto, "Leve"))).convert("RGB")
        # Nada de preto no que a grade mostra.
        assert not any(max(capa.getpixel((x, y))) < 20 for x in range(0, 720, 3) for y in range(alto, baixo, 3)), tamanho
        escala = min(largura / imagem.width, altura / imagem.height)
        esticada = (round(min(largura, imagem.width * escala * 1.15)), round(min(altura, imagem.height * escala * 1.15)))
        # A foto inteira, esticada no máximo 15%, no pé do lugar dela e no meio da largura.
        x, y = (largura - esticada[0]) // 2, cima + fio + altura - esticada[1]
        assert capa.crop((x, y, x + esticada[0], y + esticada[1])).tobytes() == imagem.resize(esticada,
                                                                                             Image.LANCZOS).tobytes()
        assert max(esticada[0] / (imagem.width * escala), esticada[1] / (imagem.height * escala)) <= 1.15 + 0.01
        if esticada == (largura, altura):
            continue
        # O resto, a própria foto desfocada: as listras se misturam, sem o laranja nem o azul puros.
        fora = (0, cima + fio, 720, y) if esticada[0] == largura else (0, cima + fio, x, faixa)
        pontos = [capa.getpixel((px, py)) for px in range(fora[0], fora[2], 2) for py in range(fora[1], fora[3], 2)]
        assert pontos and not any(p in ((200, 120, 40), (40, 90, 200)) for p in pontos), tamanho
    # A foto um pouco mais larga estica até tampar, sem desfocado (no máximo 15%).
    foto, imagem = listrada(800, 680)
    capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(foto, "Leve"))).convert("RGB")
    assert capa.crop((0, cima + fio, 720, faixa)).tobytes() == imagem.resize((largura, altura), Image.LANCZOS).tobytes()
    assert _cor_de(capa, (360, cima + fio - 1), edicao_video.LARANJA_DA_SHOPEE)
    assert _cor_de(capa, (3, 1279), edicao_video.LARANJA_DA_SHOPEE)


def test_foto_em_tela_cheia_como_o_ffmpeg_punha_antes_da_moldura():
    # Vídeo do Rafael das 22:01 de 01/11 (P119): sem a capa, a foto do começo é a do anúncio no
    # maior tamanho que cabe na tela, no meio, no fundo preto (o FILTRO_720P), também a que não é
    # quadrada, e sem a moldura laranja da miniatura.
    import io

    from PIL import Image

    def foto(largura, altura):
        saida = io.BytesIO()
        Image.new("RGB", (largura, altura), (200, 120, 40)).save(saida, "JPEG")
        return saida.getvalue()

    quadrada = Image.open(io.BytesIO(edicao_video.foto_em_tela_cheia(foto(200, 200)))).convert("RGB")
    assert quadrada.size == edicao_video.TELA
    x1, y1, x2, y2 = edicao_video.FOTO_DA_CAPA
    for ponto in [(x1 + 1, y1 + 1), (x2 - 2, y1 + 1), (x1 + 1, y2 - 2), (x2 - 2, y2 - 2), (x1 + 3, 640)]:
        assert _cor_de(quadrada, ponto, (200, 120, 40)), ponto
    assert _pretos(quadrada, (0, 0, 720, y1)) and _pretos(quadrada, (0, y2, 720, 1280))
    # A de pé (3:4) vai de um lado ao outro e mais alta, como o ffmpeg a punha.
    de_pe = Image.open(io.BytesIO(edicao_video.foto_em_tela_cheia(foto(600, 800)))).convert("RGB")
    assert _cor_de(de_pe, (2, 170), (200, 120, 40)) and _cor_de(de_pe, (717, 1109), (200, 120, 40))
    assert _pretos(de_pe, (0, 0, 720, 158)) and _pretos(de_pe, (0, 1122, 720, 1280))
    assert edicao_video.foto_em_tela_cheia(b"nao e imagem") is None


def test_edicao_de_verdade_abre_com_a_foto_sem_a_moldura_da_miniatura(tmp_path):
    # Com o ffmpeg de verdade: a foto que vai ao ffmpeg é a da miniatura, com a moldura (P115),
    # mas os 2 primeiros segundos mostram a foto do anúncio grande, sem a moldura (P119).
    if not shutil.which("ffmpeg"):
        return
    from PIL import Image
    video, foto = tmp_path / "v.mp4", tmp_path / "foto.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0xf0e0c0:size=360x640:rate=30:duration=4",
                    str(video)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x3060a0:size=200x200",
                    "-frames:v", "1", str(foto)], check=True)
    destino = tmp_path / "editado.mp4"
    assert edicao_video.editar(str(video), foto.read_bytes(), str(destino)) == ""
    quadro = tmp_path / "quadro.ppm"
    subprocess.run(["ffmpeg", "-v", "error", "-ss", "1", "-i", str(destino), "-frames:v", "1", str(quadro)], check=True)
    with Image.open(quadro) as imagem:
        tela = imagem.convert("RGB")
    x1, y1, x2, y2 = edicao_video.FOTO_DA_CAPA
    # As pontas e as bordas da foto são da foto: nada do laranja da moldura nem dos cantos dela.
    for ponto in [(x1 + 4, y1 + 4), (x2 - 5, y1 + 4), (x1 + 4, y2 - 5), (x2 - 5, y2 - 5), (x1 + 4, 640), (360, y1 + 4)]:
        assert max(abs(a - b) for a, b in zip(tela.getpixel(ponto), (48, 96, 160))) < 24, ponto
    assert _pretos(tela, (0, 0, 720, y1 - 4)) and _pretos(tela, (0, y2 + 4, 720, 1280))


def test_frase_da_capa_fica_dentro_do_que_o_app_mostra_do_video_aberto():
    # Vídeo do Rafael (31/10, 08:38): com o vídeo aberto, o app corta os lados do quadro, e o
    # "C" e o "l" de "Caimento impecável" ficavam cortados nas pontas da faixa. As letras ficam
    # dentro do que o app mostra do vídeo aberto, na capa do vídeo aberto (P129). Na da grade, que
    # o vídeo aberto não mostra, a frase vai no retângulo que o Rafael desenhou, até a beirada da
    # grade, com a margem (vídeo de 07/11, 01:31).
    import io

    from PIL import Image
    esquerda, direita = edicao_video.VISIVEL_NO_APP
    folga = edicao_video.MARGEM_DA_FAIXA // 2
    pe = edicao_video.PE_DA_FAIXA_NO_VIDEO
    cima, y2 = pe - edicao_video.FAIXA_DA_CHAMADA, pe
    for frase in ("Caimento impecável", "Organize sua cozinha", "Acaba com a bagunça da cozinha"):
        capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(_foto_jpg(), frase, no_video=True))).convert("RGB")
        assert _claros(capa, (esquerda + folga, cima, direita - folga, y2), passo=2) > 50
        assert _claros(capa, (0, cima, esquerda + folga, y2), passo=1) == 0, frase
        assert _claros(capa, (direita - folga, cima, 720, y2), passo=1) == 0, frase
        da_grade = _capa(frase)
        faixa = edicao_video.lugar_da_foto()[3]
        assert _claros(da_grade, (720 - edicao_video.MARGEM_DA_FAIXA, faixa, 720, 1280), passo=1) == 0, frase


def test_capa_do_video_aberto_tem_a_foto_inteira_e_a_faixa_acima_do_cartao_do_produto():
    # No vídeo aberto, que corta mais dos lados que a grade (P129), o resto da abertura vai com a
    # foto inteira da largura do que o app mostra, o fio em cima e a faixa no pé, de um lado ao
    # outro dela (vídeo do Rafael das 20:14 de 02/11). Vídeo das 09:56 de 06/11 (P160 2): o cartão
    # do produto que o app põe por cima do vídeo cobria a metade de baixo da frase; a faixa fica
    # acima dele, e a foto, inteira entre a barra de pesquisa do app e a faixa.
    import io

    from PIL import Image
    capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(_foto_jpg(), "Organize sua cozinha",
                                                               no_video=True))).convert("RGB")
    assert capa.size == edicao_video.TELA
    esquerda, direita = edicao_video.VISIVEL_NO_APP
    assert edicao_video.lados_da_capa(True) == (esquerda, direita) and edicao_video.lados_da_capa() == (0, 720)
    x1, cima, x2, alto_da_faixa = edicao_video.lugar_da_foto(True)
    fio, faixa = edicao_video.FIO_DA_CAPA, edicao_video.FAIXA_DA_CHAMADA
    pe = alto_da_faixa + faixa
    assert (x1, x2) == (esquerda, direita) and pe == edicao_video.PE_DA_FAIXA_NO_VIDEO < edicao_video.CARTAO_NO_VIDEO_ABERTO
    lado = direita - esquerda
    topo = pe - faixa - lado
    assert topo - fio >= cima == edicao_video.TOPO_NO_VIDEO_ABERTO
    for x in (esquerda, direita - 1):
        assert _cor_de(capa, (x, (topo + pe - faixa) // 2), (200, 120, 40)), x
        assert _cor_de(capa, (x, topo - fio + 1), edicao_video.LARANJA_DA_SHOPEE), x
        assert _cor_de(capa, (x, pe - faixa // 2), edicao_video.LARANJA_DA_SHOPEE), x
    assert _cor_de(capa, (360, topo + 2), (200, 120, 40)) and _cor_de(capa, (360, pe - faixa - 3), (200, 120, 40))
    assert _pretos(capa, (0, 0, esquerda, 1280), passo=2) and _pretos(capa, (direita, 0, 720, 1280), passo=2)
    assert _pretos(capa, (0, 0, 720, topo - fio), passo=2) and _pretos(capa, (0, pe, 720, 1280), passo=2)
    # Nada da capa onde fica o cartão do produto.
    assert _pretos(capa, (0, edicao_video.CARTAO_NO_VIDEO_ABERTO, 720, 1280), passo=2)
    # O que o app mostra do vídeo aberto: a foto de um lado ao outro, sem preto dos lados.
    recorte = Image.open(io.BytesIO(edicao_video.recorte_do_video_aberto(
        edicao_video.capa_com_chamada(_foto_jpg(), "Organize sua cozinha", no_video=True)))).convert("RGB")
    assert recorte.size == (lado, 1280)
    assert _cor_de(recorte, (0, 640), (200, 120, 40)) and _cor_de(recorte, (lado - 1, 640), (200, 120, 40))
    # A frase fica no pé da foto, dentro do que o app mostra.
    assert _claros(capa, (0, 0, esquerda + 6, 1280)) == 0 and _claros(capa, (direita - 6, 0, 720, 1280)) == 0
    assert _claros(capa, (esquerda, pe - faixa, direita, pe)) > 50


def test_faixa_nos_lados_diz_qual_capa_a_grade_mostrou():
    # No post, a grade mostra o 1º quadro (a capa da grade, a faixa de lado a lado) ou outro quadro
    # da abertura (a do vídeo aberto, a faixa só no meio, P129); sem a faixa, não dá para dizer.
    import io

    from PIL import Image
    caixa = (100, 300, 454, 772)

    def grade(capa_png):
        tela = Image.new("RGB", (1080, 2400), (240, 240, 240))
        esquerda, direita = edicao_video.LADOS_NA_GRADE
        cima, baixo = edicao_video.VISIVEL_NA_GRADE
        capa = Image.open(io.BytesIO(capa_png)).convert("RGB").crop((esquerda, cima, direita, baixo))
        tela.paste(capa.resize((caixa[2] - caixa[0], caixa[3] - caixa[1])), caixa[:2])
        return tela

    assert edicao_video.faixa_nos_lados(grade(edicao_video.capa_com_chamada(_foto_jpg(), "Leve")), caixa) is True
    assert edicao_video.faixa_nos_lados(
        grade(edicao_video.capa_com_chamada(_foto_jpg(), "Leve", no_video=True)), caixa) is False
    # A foto laranja da Shopee também não engana: na do vídeo aberto, os lados ficam no preto.
    laranja = io.BytesIO()
    Image.new("RGB", (800, 800), edicao_video.LARANJA_DA_SHOPEE).save(laranja, "JPEG", quality=95)
    assert edicao_video.faixa_nos_lados(
        grade(edicao_video.capa_com_chamada(laranja.getvalue(), "Leve", no_video=True)), caixa) is False
    assert edicao_video.faixa_nos_lados(grade(edicao_video.foto_em_tela_cheia(_foto_jpg())), caixa) is None
    assert edicao_video.faixa_nos_lados(grade(edicao_video.foto_em_tela_cheia(_foto_jpg())), (0, 0, 20, 20)) is None


def test_faixa_so_no_meio_com_uma_letra_bem_na_coluna_do_centro():
    # No vídeo aberto, a frase acaba antes dos ícones do app e sai do meio da faixa (P165 1): uma
    # letra pode cruzar bem a coluna do centro do quadro. A faixa só no meio continua reconhecida
    # pelas outras colunas do meio.
    from PIL import Image, ImageDraw
    caixa = (100, 300, 454, 772)
    tela = Image.new("RGB", (1080, 2400), (240, 240, 240))
    desenho = ImageDraw.Draw(tela)
    desenho.rectangle(caixa, fill=(0, 0, 0))
    altura = round(edicao_video.FAIXA_DA_CHAMADA * (caixa[3] - caixa[1])
                   / (edicao_video.VISIVEL_NA_GRADE[1] - edicao_video.VISIVEL_NA_GRADE[0]))
    cima = caixa[3] - altura - 20
    desenho.rectangle((caixa[0] + 20, cima, caixa[2] - 20, cima + altura), fill=edicao_video.LARANJA_DA_SHOPEE)
    meio = (caixa[0] + caixa[2]) // 2
    desenho.rectangle((meio - 4, cima + altura // 4, meio + 4, cima + altura * 3 // 4), fill=(255, 255, 255))
    assert edicao_video.faixa_nos_lados(tela, caixa) is False


def test_abertura_de_verdade_tem_a_capa_da_grade_so_no_1o_quadro(tmp_path):
    # Com o ffmpeg de verdade (P129): o 1º quadro, que o app usa como capa da grade, tem a faixa de
    # uma beirada à outra do vídeo; do 2º em diante, a do vídeo aberto (preto onde a outra é laranja).
    from PIL import Image
    if not shutil.which("ffmpeg"):
        return
    video, foto = tmp_path / "v.mp4", _foto_jpg()
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x808080:size=360x640:rate=30:duration=3",
                    str(video)], check=True)
    capas = (edicao_video.capa_com_chamada(foto, "Leve"), edicao_video.capa_com_chamada(foto, "Leve", no_video=True))
    destino = tmp_path / "editado.mp4"
    assert edicao_video.editar(str(video), foto, str(destino), capa=capas) == ""

    def quadro(numero):
        saida = tmp_path / f"q{numero}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(destino), "-vf", f"select=eq(n\\,{numero})",
                        "-frames:v", "1", str(saida)], check=True)
        with Image.open(saida) as imagem:
            return imagem.convert("RGB")

    ponto = (edicao_video.VISIVEL_NO_APP[0] // 2, edicao_video.FOTO_DA_CAPA[3] - edicao_video.FAIXA_DA_CHAMADA // 2)
    assert _cor_de(quadro(0), ponto, edicao_video.LARANJA_DA_SHOPEE)
    for numero in (1, 30, 58):
        assert max(quadro(numero).getpixel(ponto)) < 40, numero


def test_frase_da_capa_vai_numa_linha_a_comprida_em_duas_e_sem_frase_nao_ha_capa():
    import io
    import os

    import matplotlib
    from PIL import Image, ImageDraw
    desenho = ImageDraw.Draw(Image.new("RGB", edicao_video.TELA))
    fonte_ttf = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")
    # A frase curta (até MAXIMO_DA_CAPA letras, P106) vai numa linha só, em letra grande.
    fonte, linhas = edicao_video._quebra_da_chamada("Leve", desenho, fonte_ttf)
    assert (fonte.size, linhas) == (edicao_video.LETRAS_DA_CHAMADA[0], ["Leve"])
    for curta in ("Organize sua cozinha", "Mochila impermeável", "Limpeza sem esforço", "Gelado o dia todo"):
        assert len(curta) <= edicao_video.MAXIMO_DA_CAPA
        fonte, linhas = edicao_video._quebra_da_chamada(curta, desenho, fonte_ttf)
        assert linhas == [curta] and fonte.size >= edicao_video.LETRAS_DA_CHAMADA[1]
    # A comprida (o nome ou a vantagem, sem a curta) vai em duas linhas equilibradas, sem a 1ª
    # terminar numa palavra de ligação.
    assert edicao_video._quebra_da_chamada("Acaba com a bagunça da cozinha", desenho, fonte_ttf)[1] == [
        "Acaba com a bagunça", "da cozinha"]
    longa = "Organiza todos os temperos em segundos"[:edicao_video.MAXIMO_DA_VANTAGEM]
    fonte, linhas = edicao_video._quebra_da_chamada(longa, desenho, fonte_ttf)
    assert len(linhas) == 2 and fonte.size >= edicao_video.LETRAS_EM_DUAS_LINHAS[1]
    # Vídeo do Rafael das 20:14 de 02/11: com duas linhas, a faixa crescia para cima e cobria mais
    # da foto. Agora as duas cabem na faixa de uma linha, com a folga, e a foto não perde nada.
    maior = edicao_video.LETRAS_EM_DUAS_LINHAS[0]
    assert 2 * round(maior * 1.2) + 2 * edicao_video.FOLGA_DA_FAIXA <= edicao_video.FAIXA_DA_CHAMADA
    capa, curta = _capa(longa), _capa("Leve")
    cima = edicao_video.lugar_da_foto()[3]
    y2 = edicao_video.lugar_das_letras_na_grade()[3]
    assert _cor_de(capa, (3, cima), edicao_video.LARANJA_DA_SHOPEE)
    assert _cor_de(capa, (20, cima - 3), (200, 120, 40)) and _cor_de(capa, (360, cima - 3), (200, 120, 40))
    acima = (0, 0, 720, cima)
    assert capa.crop(acima).tobytes() == curta.crop(acima).tobytes()
    assert _claros(capa, (0, cima, 720, y2)) > 50 and _claros(capa, acima) == 0
    # Embaixo da frase, a faixa sem letras até o fim do quadro (P168 e P171).
    assert _claros(capa, (0, y2, 720, 1280)) == 0 and _cor_de(capa, (360, 1279), edicao_video.LARANJA_DA_SHOPEE)
    # Vídeo do Rafael das 23:29 de 06/11 (P171): na grade, a letra é maior que a do vídeo aberto. Vídeos
    # de 07/11, 01:04 e 01:31: as duas linhas da frase comprida no meio do retângulo da faixa à direita
    # do número.

    def altura_das_letras(imagem, caixa):
        ys = [y for x in range(caixa[0], caixa[2]) for y in range(caixa[1], caixa[3]) if min(imagem.getpixel((x, y))) > 200]
        return (max(ys) - min(ys) + 1, min(ys)) if ys else (0, None)
    da_grade = altura_das_letras(curta, (0, cima, 720, 1280))[0]
    pe_no_video = edicao_video.PE_DA_FAIXA_NO_VIDEO
    no_video = Image.open(io.BytesIO(edicao_video.capa_com_chamada(_foto_jpg(), "Leve", no_video=True))).convert("RGB")
    assert da_grade > 1.1 * altura_das_letras(no_video, (0, pe_no_video - edicao_video.FAIXA_DA_CHAMADA, 720,
                                                          pe_no_video))[0]
    altura, alto_das_letras = altura_das_letras(capa, (0, cima, 720, 1280))
    _esquerda, cima_das_letras, _direita, pe_das_letras = edicao_video.lugar_das_letras_na_grade()
    assert altura > 2 * edicao_video.LETRAS_NA_GRADE[1] and alto_das_letras >= cima_das_letras - 1
    assert abs(alto_das_letras + (altura - 1) / 2 - (cima_das_letras + pe_das_letras - 1) / 2) <= 3
    # Sem a frase ou com a foto que não abre, não há capa com chamada (vai a capa de sempre).
    assert edicao_video.capa_com_chamada(_foto_jpg(), "") is None
    assert edicao_video.capa_com_chamada(b"nao e imagem", "Leve") is None
    # O exemplo do painel mostra também o pedaço que a grade do celular do Rafael mostra, com a
    # largura toda: a foto, o fio e a faixa vão até as bordas, sem preto nenhum, com o fio no alto
    # e a faixa até embaixo (P168).
    capa_png = edicao_video.capa_com_chamada(_foto_jpg(), "Leve")
    recorte = Image.open(io.BytesIO(edicao_video.recorte_da_grade(capa_png))).convert("RGB")
    alto, baixo = edicao_video.GRADE_NO_CELULAR
    assert recorte.size == (720, baixo - alto) and recorte.width * 4 == recorte.height * 3
    capa = Image.open(io.BytesIO(capa_png)).convert("RGB")
    assert recorte.tobytes() == capa.crop((0, alto, 720, baixo)).tobytes()
    fio = edicao_video.FIO_DA_CAPA_NA_GRADE
    for x in (0, recorte.width - 1):
        assert _cor_de(recorte, (x, 0), edicao_video.LARANJA_DA_SHOPEE), x
        assert _cor_de(recorte, (x, fio + 2), (200, 120, 40)), x
        assert _cor_de(recorte, (x, 640 - alto), (200, 120, 40)), x
        assert _cor_de(recorte, (x, y2 - 3 - alto), edicao_video.LARANJA_DA_SHOPEE), x
        assert _cor_de(recorte, (x, recorte.height - 1), edicao_video.LARANJA_DA_SHOPEE), x


def test_capa_com_chamada_so_vai_ao_ar_ligada_e_nunca_na_bebida_alcoolica(monkeypatch, tmp_path):
    _versoes_de_mentira(monkeypatch)
    _textos_da_tela(monkeypatch, {"nome": "Bolsa de Palha", "vantagem": "Leve e resistente", "lugar": "alto"})
    capas = []

    def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outras_fotos=(),
               rotulo_de_ia=False, cor=None):
        capas.append(capa)
        return ""
    monkeypatch.setattr(edicao_video, "editar", editar)
    destino = str(tmp_path / "r.mp4")
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    # Desligada (o padrão), a capa é a de antes.
    assert edicao_video.editar_para_postar("v.mp4", _foto_jpg(), destino, "Bolsa")[1] == edicao_video.COM_LEGENDAS
    assert capas == [None]
    # Ligada no painel, sem a frase curta da IA vai o nome do produto (P131), e o registro diz.
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DA_CAPA: True})
    assert edicao_video.editar_para_postar("v.mp4", _foto_jpg(), destino, "Bolsa")[1] == (
        edicao_video.COM_LEGENDAS + edicao_video.COM_A_CHAMADA)
    # O 1º quadro vai com a capa da grade, e o resto da abertura com a do vídeo aberto (P129).
    assert capas[-1] == (edicao_video.capa_com_chamada(_foto_jpg(), "Bolsa de Palha"),
                         edicao_video.capa_com_chamada(_foto_jpg(), "Bolsa de Palha", no_video=True))
    assert all(capa[:8] == b"\x89PNG\r\n\x1a\n" for capa in capas[-1])
    # A bebida alcoólica fica com a capa dos avisos (P43).
    assert edicao_video.editar_para_postar("v.mp4", _foto_jpg(), destino, "Vinho", avisos=True)[1] == (
        edicao_video.COM_LEGENDAS + edicao_video.COM_OS_AVISOS)
    assert capas[-1] is None
    # Sem a frase, o nome e a vantagem da IA, a capa de antes também.
    _textos_da_tela(monkeypatch, {"lugar": "alto"})
    edicao_video.editar_para_postar("v.mp4", _foto_jpg(), destino, "Bolsa")
    assert capas[-1] is None
    # A capa que não sai (a letra que não abre, por exemplo) não segura o vídeo: vai a capa de antes.
    _textos_da_tela(monkeypatch, {"nome": "Bolsa de Palha", "vantagem": "Leve e resistente", "lugar": "alto"})

    def quebrada(foto, chamada, no_video=False):
        raise OSError("sem a letra")
    monkeypatch.setattr(edicao_video, "capa_com_chamada", quebrada)
    assert edicao_video.editar_para_postar("v.mp4", _foto_jpg(), destino, "Bolsa")[1] == edicao_video.COM_LEGENDAS
    assert capas[-1] is None


def test_capa_com_a_frase_abre_o_video_no_robo_e_no_assistente(monkeypatch, tmp_path):
    # Escolha do Rafael (02/11, P125): a capa com a frase abre o vídeo, no rascunho do robô e no
    # modo assistente; o 1º quadro vai com a capa da grade e o resto da abertura com a do vídeo
    # aberto (P129). Desligada, o vídeo abre sem ela.
    _versoes_de_mentira(monkeypatch)
    _textos_da_tela(monkeypatch, {"nome": "Bolsa de Palha", "vantagem": "Leve e resistente", "capa": "Leve e forte",
                                  "lugar": "alto"})
    aberturas = []

    def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outras_fotos=(),
               rotulo_de_ia=False, cor=None):
        aberturas.append(capa)
        return ""
    monkeypatch.setattr(edicao_video, "editar", editar)
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DA_CAPA: True})
    destino = str(tmp_path / "r.mp4")
    assert edicao_video.editar_para_postar("v.mp4", _foto_jpg(), destino, "Bolsa")[1] == (
        edicao_video.COM_LEGENDAS + edicao_video.COM_A_CHAMADA)
    assert aberturas[-1] == (edicao_video.capa_com_chamada(_foto_jpg(), "Leve e forte"),
                             edicao_video.capa_com_chamada(_foto_jpg(), "Leve e forte", no_video=True))
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DA_CAPA: False})
    assert edicao_video.editar_para_postar("v.mp4", _foto_jpg(), destino, "Bolsa")[1] == edicao_video.COM_LEGENDAS
    assert aberturas[-1] is None


def test_faixa_laranja_acha_a_faixa_da_capa_no_print_e_nao_acha_sem_ela():
    # O robô confere a capa do post pela faixa laranja no print (marcar_o_post): na capa, a faixa
    # está onde o desenho a pôs; num print com a capa reduzida dentro de um quadro, no lugar
    # proporcional, mesmo com as letras brancas no meio.
    from PIL import Image
    capa = _capa("Organize sua cozinha")
    cima, baixo, esquerda, direita = edicao_video.faixa_laranja(capa)
    # A faixa vai de uma beirada à outra da capa, do pé da foto até o fim do quadro (P168 e P171); o
    # fio fino em cima da foto não é a faixa.
    assert (esquerda, direita) == (0, edicao_video.TELA[0])
    assert (cima, baixo) == (edicao_video.lugar_da_foto()[3], edicao_video.TELA[1])
    tela = Image.new("RGB", (1080, 2400), (30, 30, 30))
    escala = 957 / 720
    tela.paste(capa.resize((957, round(1280 * escala))), (61, 267))
    medida = edicao_video.faixa_laranja(tela, (61, 267, 1018, 1969))
    assert medida is not None
    assert abs(medida[0] - (267 + cima * escala)) <= 2 and abs(medida[1] - (267 + baixo * escala)) <= 2
    assert abs(medida[2] - (61 + esquerda * escala)) <= 2 and abs(medida[3] - (61 + direita * escala)) <= 2
    # A foto sem a faixa (a capa de sempre) não tem faixa nenhuma.
    assert edicao_video.faixa_laranja(Image.open(io.BytesIO(edicao_video.foto_em_tela_cheia(_foto_jpg())))) is None


def test_faixa_laranja_mede_a_faixa_inteira_com_letras_grossas_e_cortadas_nas_pontas():
    # No print do celular, as linhas do meio das letras têm mais branco (e a borda borrada delas)
    # que laranja, e a medida pegaria só o pedaço da faixa acima das letras; com a faixa maior que
    # a caixa, as letras chegam às pontas.
    from PIL import Image, ImageDraw
    laranja, branco, borda = edicao_video.LARANJA_DA_SHOPEE, (255, 255, 255), (246, 166, 150)
    for cortadas in (False, True):
        tela = Image.new("RGB", (800, 600), (20, 20, 20))
        desenho = ImageDraw.Draw(tela)
        desenho.rectangle((100, 200, 699, 299), fill=laranja)
        for x in range(100 if cortadas else 130, 699 if cortadas else 669, 20):
            desenho.rectangle((x, 230, x + 12, 269), fill=branco)
            desenho.rectangle((x + 13, 230, x + 14, 269), fill=borda)
        assert edicao_video.faixa_laranja(tela) == (200, 300, 100, 700), cortadas
    # O branco da foto logo acima da faixa (sem laranja nenhum) não entra na medida.
    tela = Image.new("RGB", (800, 600), (20, 20, 20))
    desenho = ImageDraw.Draw(tela)
    desenho.rectangle((100, 100, 699, 199), fill=branco)
    desenho.rectangle((100, 200, 699, 299), fill=laranja)
    assert edicao_video.faixa_laranja(tela) == (200, 300, 100, 700)


def test_faixa_laranja_pequena_em_cima_de_uma_moldura_laranja_no_print_do_celular():
    # No print do celular (JPEG, qualidade 80), a faixa da capa reduzida tem as letras pequenas, que
    # cortariam a faixa em dois pedaços baixos demais, e o laranja de uma moldura dos lados, na
    # mesma linha, esticaria as pontas dela: a medida acha a faixa inteira, no tamanho dela.
    from PIL import Image, ImageDraw
    quadro, meio = (61, 267, 1018, 1969), (540, 1118)
    capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(_foto_jpg(), "Madeira maciça"))).convert("RGB")
    # O fundo: uma foto com os lados da moldura laranja por dentro (P115), nas mesmas linhas da
    # faixa, separados dela por outras cores.
    fundo = Image.open(io.BytesIO(edicao_video.foto_em_tela_cheia(_foto_jpg()))).convert("RGB")
    x1, y1, x2, y2 = edicao_video.FOTO_DA_CAPA
    desenho = ImageDraw.Draw(fundo)
    desenho.rectangle((x1 + 40, y1 + 40, x1 + 53, y2 - 41), fill=edicao_video.LARANJA_DA_SHOPEE)
    desenho.rectangle((x2 - 54, y1 + 40, x2 - 41, y2 - 41), fill=edicao_video.LARANJA_DA_SHOPEE)
    cima, baixo, esquerda, direita = edicao_video.faixa_laranja(capa)
    for escala in (0.443, 0.8, 957 / 720):
        tela = Image.new("RGB", (1080, 2520), "black")
        tela.paste(fundo.resize((quadro[2] - quadro[0], quadro[3] - quadro[1])), quadro[:2])
        reduzida = capa.resize((round(capa.width * escala), round(capa.height * escala)))
        x, y = meio[0] - reduzida.width // 2, meio[1] - reduzida.height // 2
        tela.paste(reduzida, (x, y))
        jpeg = io.BytesIO()
        tela.save(jpeg, format="JPEG", quality=80)
        medida = edicao_video.faixa_laranja(Image.open(io.BytesIO(jpeg.getvalue())).convert("RGB"), quadro)
        assert medida is not None, escala
        # A faixa da capa, no tamanho dela (a medida do print erra uns pontos).
        esperada = (y + cima * escala, y + baixo * escala, x + esquerda * escala, x + direita * escala)
        assert all(abs(m - e) <= 4 for m, e in zip(medida, esperada)), (escala, medida, esperada)


def test_capa_com_chamada_vai_em_todos_os_videos(monkeypatch, tmp_path):
    # Escolha do Rafael (30/10, P100): ligada, a chamada vai na capa de todos os vídeos (antes,
    # P77, alternava um sim e outro não); o vídeo sem a frase, o nome e a vantagem da IA vai com a
    # capa de sempre.
    _versoes_de_mentira(monkeypatch)
    capas = []

    def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outras_fotos=(),
               rotulo_de_ia=False, cor=None):
        capas.append(capa is not None)
        return ""
    monkeypatch.setattr(edicao_video, "editar", editar)
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DA_CAPA: True})
    destino = str(tmp_path / "r.mp4")
    com_vantagem = {"nome": "Bolsa de Palha", "vantagem": "Leve e resistente", "lugar": "alto"}
    for textos in (com_vantagem, com_vantagem, {"lugar": "alto"}, com_vantagem, com_vantagem):
        _textos_da_tela(monkeypatch, textos)
        edicao_video.editar_para_postar("v.mp4", _foto_jpg(), destino, "Bolsa")
    assert capas == [True, True, False, True, True]


def test_exemplo_da_capa_usa_o_proximo_video_e_a_vantagem_da_ia(monkeypatch):
    _fontes_de_mentira(monkeypatch, {"autorais": [("autorais:1", "/tmp/a.mp4", "https://s.shopee.com.br/a", "")]})
    monkeypatch.setattr(edicao_video.os.path, "exists", lambda caminho: True)
    monkeypatch.setattr(edicao_video.ps, "foto_do_produto", lambda video: _foto_jpg())
    monkeypatch.setattr(edicao_video, "_produto_do_link", lambda link: {"nome": "Copo Térmico", "preco": 30.0})
    _textos_da_tela(monkeypatch, {"vantagem": "Gelado por 12 horas"})
    nome, motivo, exemplo = edicao_video.exemplo_capa()
    assert (nome, motivo, exemplo["chamada"]) == ("Copo Térmico", "", "Gelado por 12 horas")
    assert exemplo["capa"][:4] == b"\x89PNG" and exemplo["grade"][:4] == b"\x89PNG"
    # E o que o app mostra do vídeo aberto no resto da abertura (P129).
    assert exemplo["video"] == edicao_video.recorte_do_video_aberto(
        edicao_video.capa_com_chamada(_foto_jpg(), "Gelado por 12 horas", no_video=True))
    # Com a frase curta da IA para a capa (P106), é ela que vai.
    _textos_da_tela(monkeypatch, {"nome": "Copo Térmico", "vantagem": "Gelado por 12 horas", "capa": "Gelado 12 horas"})
    assert edicao_video.exemplo_capa()[2]["chamada"] == "Gelado 12 horas"
    # Sem a curta, o nome do produto (P131); sem a frase, o nome e a vantagem da IA, o exemplo diz por quê.
    _textos_da_tela(monkeypatch, {"nome": "Copo Térmico", "vantagem": "Gelado por 12 horas"})
    assert edicao_video.exemplo_capa()[2]["chamada"] == "Copo Térmico"
    _textos_da_tela(monkeypatch, {"lugar": "meio"})
    assert edicao_video.exemplo_capa()[:2] == (
        None, "a IA não escreveu a frase da capa, o nome nem a vantagem do produto deste vídeo")


def test_frase_curta_da_capa_vem_da_ia_e_a_longa_fica_de_fora_sem_ser_cortada(monkeypatch):
    # Escolhas do Rafael (30/10, P106, e 02/11, P122): a IA escreve só para a capa uma frase de 2
    # a 4 palavras, até 20 letras, que sai em letra grande; a maior que isso não é cortada
    # (perderia o sentido) e, sem a certa nem na 2ª vez (aqui a IA não responde), a capa vai com
    # a vantagem.
    import api_gemini
    respostas = iter([
        '{"nome": "Cubo", "vantagem": "Estimula o desenvolvimento do bebê", "capa": "Cubo que estimula"}',
        '{"nome": "Cubo", "vantagem": "Estimula o desenvolvimento do bebê", "capa": "Cubo que estimula o bebê"}'])

    async def analisar(video, prompt, imagens=None):
        return next(respostas)

    monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(edicao_video, "_revisar_ortografia", lambda textos: textos)
    assert '"capa"' in edicao_video.PROMPT_DOS_TEXTOS and "até 20 caracteres" in edicao_video.PROMPT_DOS_TEXTOS
    curta = edicao_video.textos_da_tela("v.mp4", "Cubo")
    assert curta["capa"] == "Cubo que estimula" and edicao_video.frase_da_capa(curta) == "Cubo que estimula"
    assert "capa_de_novo" not in curta
    longa = edicao_video.textos_da_tela("v.mp4", "Cubo")
    # Sem a curta nem na 2ª vez, o nome do produto (P131).
    assert "capa" not in longa and edicao_video.frase_da_capa(longa) == "Cubo"
    assert (longa["capa_de_novo"], longa["sem_a_capa"]) == (edicao_video.LONGA_DEMAIS, edicao_video.SEM_FRASE)
    assert edicao_video.MAXIMOS_DOS_TEXTOS["capa"] == edicao_video.MAXIMO_DA_CAPA == 20


def _ia_dos_textos(monkeypatch, resposta_do_video, frases_de_novo):
    """
    A IA de mentira que vê o vídeo (resposta_do_video, o JSON) e a das chamadas só de texto: o
    pedido da frase da capa de novo responde, em ordem, com frases_de_novo; os outros (a
    revisão, a ortografia) ficam sem resposta. Devolve os pedidos da frase de novo.
    """
    import api_gemini
    pedidos, frases = [], iter(frases_de_novo)

    async def analisar(video, prompt, imagens=None):
        return resposta_do_video

    async def texto(prompt, imagens=None):
        if prompt.startswith("Escreva a frase da capa"):
            pedidos.append(prompt)
            return next(frases, None)
        return None

    monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", texto)
    return pedidos


def test_frase_da_capa_longa_demais_volta_a_ia_uma_vez_com_o_tamanho(monkeypatch):
    # No print da grade de 02/11 (16:06), a capa "Remove bolinhas de tecido" não dizia o que era o
    # produto (P122): a frase da IA passou de 20 letras e a capa foi com a vantagem. Agora a frase
    # que não segue a regra volta à IA uma vez, só ela, dizendo o que estava errado.
    import json
    pedidos = _ia_dos_textos(monkeypatch, json.dumps({
        "nome": "Removedor de Bolinhas", "vantagem": "Remove bolinhas de tecido",
        "capa": "Removedor de bolinhas"}), ['"Removedor sem fio."'])
    textos = edicao_video.textos_da_tela("v.mp4", "Removedor")
    assert textos["capa"] == "Removedor sem fio" and edicao_video.frase_da_capa(textos) == "Removedor sem fio"
    assert textos["capa_de_novo"] == edicao_video.LONGA_DEMAIS and "sem_a_capa" not in textos
    assert len(pedidos) == 1
    # O pedido diz o produto, a vantagem e o tamanho da de antes.
    for pedaco in ("Removedor de Bolinhas", "Remove bolinhas de tecido", "tem 21 caracteres, mais que 20",
                   "começa pelo que é o produto", "até 20 caracteres"):
        assert pedaco in pedidos[0], pedaco
    assert edicao_video.registro_da_frase(textos, textos["capa"]) == (
        "curta na 2ª vez", "a 1ª: mais de 20 letras; 17 letras", True)


def test_frase_da_capa_sem_dizer_o_que_e_o_produto_volta_a_ia(monkeypatch):
    # A P122: a frase começa pelo que é o produto. "Melhor visibilidade", numa viseira de carro,
    # só trazia a vantagem: volta à IA, que reescreve começando pelo produto.
    import json
    pedidos = _ia_dos_textos(monkeypatch, json.dumps({
        "nome": "Viseira para Carro", "vantagem": "Melhor visibilidade", "capa": "Melhor visibilidade"}),
        ["Viseira contra o sol"])
    textos = edicao_video.textos_da_tela("v.mp4", "Viseira")
    assert textos["capa"] == "Viseira contra o sol" and textos["capa_de_novo"] == edicao_video.SEM_O_PRODUTO
    assert '"Melhor visibilidade" não começa pelo que é o produto' in pedidos[0]


def test_sem_a_frase_certa_nem_na_2a_vez_a_capa_vai_com_o_nome_e_o_registro_diz_por_que(monkeypatch):
    import json
    _ia_dos_textos(monkeypatch, json.dumps({
        "nome": "Removedor de Bolinhas", "vantagem": "Remove bolinhas de tecido", "capa": "Removedor de bolinhas"}),
        ["Removedor de bolinhas elétrico"])
    textos = edicao_video.textos_da_tela("v.mp4", "Removedor")
    # Escolha do Rafael (02/11, P131 1): sem a frase certa nem na 2ª vez, o nome do produto, que diz o
    # que ele é; sem o nome, a vantagem.
    assert "capa" not in textos and edicao_video.frase_da_capa(textos) == "Removedor de Bolinhas"
    assert edicao_video.registro_da_frase(textos, edicao_video.frase_da_capa(textos)) == (
        "o nome (sem a curta)", "a 1ª: mais de 20 letras; a 2ª: mais de 20 letras; 21 letras", None)
    sem_nome = {"vantagem": "Remove bolinhas de tecido", "capa_de_novo": edicao_video.SEM_FRASE,
                "sem_a_capa": edicao_video.SEM_FRASE}
    assert edicao_video.frase_da_capa(sem_nome) == "Remove bolinhas de tecido"
    assert edicao_video.registro_da_frase(sem_nome, edicao_video.frase_da_capa(sem_nome)) == (
        "a vantagem (sem a curta nem o nome)", "a 1ª: sem frase; a 2ª: sem frase; 25 letras", None)
    # O nome que não cabe numa linha vai em duas, na faixa do tamanho de uma linha (a letra menor:
    # vídeo do Rafael das 20:14 de 02/11, a faixa não cresce e a foto não perde nada).
    import os

    import matplotlib
    from PIL import Image, ImageDraw
    desenho = ImageDraw.Draw(Image.new("RGB", edicao_video.TELA))
    fonte_ttf = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")
    fonte, linhas = edicao_video._quebra_da_chamada("Removedor de Bolinhas Elétrico", desenho, fonte_ttf)
    assert len(linhas) == 2 and fonte.size >= edicao_video.LETRAS_EM_DUAS_LINHAS[1]
    # Sem a frase da IA nenhuma vez (a IA de texto sem resposta).
    _ia_dos_textos(monkeypatch, json.dumps({"nome": "Removedor de Bolinhas", "vantagem": "Remove bolinhas"}), [])
    textos = edicao_video.textos_da_tela("v.mp4", "Removedor")
    assert (textos["capa_de_novo"], textos["sem_a_capa"]) == (edicao_video.SEM_FRASE, edicao_video.SEM_FRASE)
    # Sem o nome nem a vantagem, a IA não teria de onde tirar a frase: não pede de novo.
    pedidos = _ia_dos_textos(monkeypatch, json.dumps({"lugar": "meio"}), ["Removedor sem fio"])
    textos = edicao_video.textos_da_tela("v.mp4", "Removedor")
    assert pedidos == [] and "capa" not in textos and edicao_video.frase_da_capa(textos) == ""


def test_frase_da_capa_comeca_pelo_que_e_o_produto():
    # A 1ª palavra (sem artigo nem número na frente) tem o mesmo começo de uma palavra do nome:
    # o plural, o diminutivo e o acento não atrapalham.
    for frase, nome in (("Travessas 3 tamanhos", "Travessa de Vidro"), ("Sapatinho macio", "Sapato Infantil"),
                        ("Mesinha dobrável", "Mesa Portátil"), ("A calça que modela", "Calça Jeans Feminina"),
                        ("3 travessas de vidro", "Travessas"), ("Tênis bem leve", "Tenis Casual"),
                        ("Copo sempre gelado", "Kit Copo Térmico"), ("Calça que modela", "")):
        assert edicao_video.comeca_pelo_produto(frase, nome), (frase, nome)
    for frase, nome in (("Melhor visibilidade", "Viseira para Carro"), ("Conforto e estilo", "Tênis Infantil"),
                        ("Bolsa de praia", "Bolinhas de Gel"), ("Caimento impecável", "Calça Jeans")):
        assert not edicao_video.comeca_pelo_produto(frase, nome), (frase, nome)
    # De 2 a 4 palavras, até 20 letras.
    assert edicao_video.por_que_a_frase_nao_serve("Removedor", "Removedor") == edicao_video.FORA_DAS_PALAVRAS
    assert edicao_video.por_que_a_frase_nao_serve("Calça que modela bem demais", "Calça") == edicao_video.LONGA_DEMAIS
    assert edicao_video.por_que_a_frase_nao_serve("", "Calça") == edicao_video.SEM_FRASE
    assert edicao_video.por_que_a_frase_nao_serve("Calça que modela", "Calça Jeans") == ""


def test_frase_da_capa_diz_o_que_e_o_produto_e_a_vantagem():
    # Escolha do Rafael (02/11, P122 1): no print da grade, a capa da calça só com a vantagem
    # ("Caimento impecável") não dizia o que era o produto. A frase da capa começa pelo que é o
    # produto e traz a vantagem, numa linha de letra grande, até 20 letras como antes.
    import os

    import matplotlib
    from PIL import Image, ImageDraw
    for prompt in (edicao_video.PROMPT_DOS_TEXTOS.format(nome="Calça"), edicao_video._CAPA_NO_PROMPT):
        assert "começa pelo que é o produto e traz a vantagem que o vídeo mostra" in prompt
        assert "a mesma vantagem em poucas palavras" not in prompt and "até 20 caracteres" in prompt
    desenho = ImageDraw.Draw(Image.new("RGB", edicao_video.TELA))
    fonte_ttf = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")
    # Os exemplos que a IA recebe cabem no limite e numa linha só, em letra grande.
    for exemplo in ("Calça que modela", "Travessas 3 tamanhos", "Copo sempre gelado"):
        assert f'"{exemplo}"' in edicao_video._CAPA_NO_PROMPT and len(exemplo) <= edicao_video.MAXIMO_DA_CAPA
        fonte, linhas = edicao_video._quebra_da_chamada(exemplo, desenho, fonte_ttf)
        assert linhas == [exemplo] and fonte.size >= edicao_video.LETRAS_DA_CHAMADA[1]


def test_capa_vai_com_a_frase_curta_e_sem_ela_com_o_nome(monkeypatch, tmp_path):
    import registro_processos as rp
    _versoes_de_mentira(monkeypatch)
    frases = []
    # A capa do vídeo aberto (P129) usa a mesma frase: conta só a da grade.
    monkeypatch.setattr(edicao_video, "_capa_da_vez",
                        lambda foto, frase, no_video=False, cor=None: (None if no_video else frases.append(frase))
                        or b"\x89PNG")
    monkeypatch.setattr(edicao_video, "editar", lambda *a, **k: "")
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DA_CAPA: True})
    destino = str(tmp_path / "r.mp4")
    longa = {"nome": "Cubo", "vantagem": "Estimula o desenvolvimento do bebê", "lugar": "alto"}
    _textos_da_tela(monkeypatch, dict(longa, capa="Estimula o bebê"))
    edicao_video.editar_para_postar("v.mp4", _foto_jpg(), destino, "Cubo")
    _textos_da_tela(monkeypatch, longa)
    edicao_video.editar_para_postar("v.mp4", _foto_jpg(), destino, "Cubo")
    # Sem a curta, o nome do produto (P131).
    assert frases == ["Estimula o bebê", "Cubo"]
    registro = [(r, d) for _m, _p, r, d, _o in rp.sequencia("shopee_video", edicao_video.PROCESSO_DA_FRASE_DA_CAPA,
                                                            "2000-01-01 00:00:00")]
    assert registro == [("curta", "15 letras"), ("o nome (sem a curta)", "4 letras")]


def test_sem_a_miniatura_o_canto_mostra_o_proprio_video(tmp_path):
    # Escolha do Rafael (29/10, P81): com o ffmpeg de verdade, sem a nossa miniatura o canto de
    # cima à direita fica com o próprio vídeo; com ela, com a foto do produto.
    if not shutil.which("ffmpeg"):
        assert edicao_video.editar(str(tmp_path / "nao_existe.mp4"), b"foto", str(tmp_path / "r.mp4"),
                                   miniatura=False) != ""
        return
    video, foto = tmp_path / "v.mp4", tmp_path / "foto.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0xf0e0c0:size=360x640:rate=30:duration=4",
                    str(video)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x3060a0:size=200x200",
                    "-frames:v", "1", str(foto)], check=True)
    from PIL import Image
    # Escolha do Rafael (29/10, P97): a miniatura menor fica no mesmo canto de cima à direita;
    # a ponta de baixo à esquerda da de sempre volta a mostrar o próprio vídeo.
    (cx, cy), lado = edicao_video.CANTO_DA_MINIATURA, edicao_video.LARGURA_DA_MINIATURA
    dentro_do_canto, ponta_de_baixo = (cx - 26, cy + 22), (cx - lado + 14, cy + lado - 13)
    for miniatura, azuis in ((True, (True, True, True)), (False, (False, False, False)),
                             (lado * 3 // 4 // 2 * 2, (True, True, False))):
        destino = tmp_path / f"editado_{miniatura}.mp4"
        assert edicao_video.editar(str(video), foto.read_bytes(), str(destino), miniatura=miniatura) == ""
        quadro = tmp_path / f"quadro_{miniatura}.ppm"
        subprocess.run(["ffmpeg", "-v", "error", "-ss", "3", "-i", str(destino), "-frames:v", "1", str(quadro)],
                       check=True)
        with Image.open(quadro) as imagem:
            for ponto, azul in zip((edicao_video.CENTRO_DA_MINIATURA, dentro_do_canto, ponta_de_baixo), azuis):
                r, g, b = imagem.convert("RGB").getpixel(ponto)
                assert (b > r + 60) == azul, (miniatura, ponto)


def test_miniatura_vai_com_a_moldura_e_a_foto_do_comeco_como_antes(monkeypatch, tmp_path):
    # Pedido do Rafael (vídeo das 15:35 de 01/11, P115): a moldura laranja com os cantos
    # arredondados em volta da miniatura, dentro do lugar de sempre dela. A foto do começo volta a
    # ser como antes, sem a moldura (vídeo das 22:01 de 01/11, P119).
    import io

    from PIL import Image
    pedidos, molduras = [], []

    def com_foto_e_miniatura(video, foto, destino, segundos, largura, centro, *args, outras=(), **opcoes):
        pedidos.append((foto, largura, centro, args[4], list(outras)))
        molduras.append(opcoes.get("moldura"))
        return ""
    monkeypatch.setattr(edicao_video.videos, "com_foto_e_miniatura", com_foto_e_miniatura)
    destino = str(tmp_path / "r.mp4")
    assert edicao_video.editar("v.mp4", _foto_jpg(), destino, outras_fotos=[_foto_jpg()]) == ""
    foto, largura, centro, capa, outras = pedidos[-1]
    # A moldura do cartão do produto vai junto (P128).
    assert molduras[-1] == edicao_video.moldura_do_cartao() and molduras[-1][:8] == b"\x89PNG\r\n\x1a\n"
    assert (largura, centro) == (edicao_video.LARGURA_DA_MINIATURA, edicao_video.CENTRO_DA_MINIATURA)
    for miniatura in [foto] + outras:
        imagem = Image.open(io.BytesIO(miniatura))
        assert imagem.mode == "RGBA" and imagem.size == (largura, largura)
        # Os cantos transparentes, a moldura laranja na borda e a foto no meio.
        assert imagem.getpixel((0, 0))[3] == 0 and imagem.getpixel((largura - 1, largura - 1))[3] == 0
        assert _cor_de(imagem.convert("RGB"), (largura // 2, 2), edicao_video.LARANJA_DA_SHOPEE)
        assert _cor_de(imagem.convert("RGB"), (largura // 2, largura // 2), (200, 120, 40))
    # Sem a capa, a foto do começo vai como antes: a do anúncio, em tela cheia no fundo preto,
    # sem a moldura da miniatura (P119).
    assert capa == edicao_video.foto_em_tela_cheia(_foto_jpg())
    # A miniatura menor (P97) leva a moldura do tamanho dela; sem a miniatura (P81), a foto vai
    # como veio; a foto que não abre também (o ffmpeg diz o motivo).
    assert edicao_video.editar("v.mp4", _foto_jpg(), destino, miniatura=120) == ""
    assert Image.open(io.BytesIO(pedidos[-1][0])).size == (120, 120)
    assert edicao_video.editar("v.mp4", _foto_jpg(), destino, miniatura=False) == ""
    assert pedidos[-1][0] == _foto_jpg()
    assert edicao_video.editar("v.mp4", b"nao abre", destino) == ""
    assert pedidos[-1][0] == b"nao abre" and pedidos[-1][3] is None
    # Com a capa (a da frase, a dos avisos), ela abre o vídeo como veio.
    assert edicao_video.editar("v.mp4", _foto_jpg(), destino, capa=b"capa") == ""
    assert pedidos[-1][3] == b"capa"


def test_fotos_que_cabem_com_pelo_menos_3_segundos_cada():
    # Escolha do Rafael (30/10, P103): cada foto da miniatura que troca fica pelo menos 3 s; no
    # vídeo curto demais para todas, ficam as primeiras, as que pagam mais por venda.
    assert edicao_video.MINIMO_POR_FOTO == 3
    casos = ((30, 4), (60, 2), (15, 6), (14.9, 6), (5, 3), (0, 3), (9, 1))
    assert [edicao_video.fotos_que_cabem(duracao, quantas) for duracao, quantas in casos] == [4, 2, 5, 4, 1, 1, 1]


def test_a_miniatura_troca_entre_todas_as_fotos_uma_volta_so(monkeypatch, tmp_path):
    # Escolha do Rafael (30/10, P103): a miniatura troca, no mesmo canto, entre a foto do 1º
    # produto e as outras fotos diferentes dos produtos do post, na ordem, uma volta só, com o
    # vídeo dividido igual (9 s com 3 fotos: 3 s cada), e a última fica até o fim. As outras fotos
    # entram por último: a seta e o som continuam com os mesmos números. Cada foto cabe no quadrado
    # da miniatura, sem esticar.
    comandos = _programas(monkeypatch)
    monkeypatch.setattr(edicao_video.videos, "duracao", lambda caminho: 9.0)
    destino = str(tmp_path / "r.mp4")
    assert edicao_video.editar("video.mp4", b"foto", destino, outras_fotos=[b"bola", b"triangulo"]) == ""
    ffmpeg = comandos[-1]
    filtro = ffmpeg[ffmpeg.index("-filter_complex") + 1]
    entradas = [ffmpeg[i + 1] for i, parte in enumerate(ffmpeg) if parte == "-i"]
    # A moldura do cartão do produto (P128) entra por último: as outras entradas não mudam de número.
    assert len(entradas) == 8 and entradas[3] == edicao_video.SETA and entradas[7].endswith("moldura.png")
    assert entradas[5].endswith("outra_0.jpg") and entradas[6].endswith("outra_1.jpg")
    lado = edicao_video.LARGURA_DA_MINIATURA
    quadrado = (f"scale={lado}:{lado}:force_original_aspect_ratio=decrease,format=rgba,"
                f"pad={lado}:{lado}:(ow-iw)/2:(oh-ih)/2:color=black@0")
    assert all(f"[{entrada}:v]{quadrado}[mini{n}]" in filtro for n, entrada in enumerate((2, 5, 6)))
    mx, my = edicao_video.CENTRO_DA_MINIATURA
    lugar = f"overlay=x={mx}-w/2:y={my}-h/2:shortest=1"
    assert f"[corpo][mini0]{lugar}:enable='lt(t,3.000)'[mini0_no_corpo]" in filtro
    assert f"[mini0_no_corpo][mini1]{lugar}:enable='gte(t,3.000)*lt(t,6.000)'[mini1_no_corpo]" in filtro
    assert f"[mini1_no_corpo][mini2]{lugar}:enable='gte(t,6.000)'[semmoldura]" in filtro
    assert "[3:v]loop=loop=-1:size=25:start=0[seta]" in filtro and "[4:a][som]concat=n=2:v=0:a=1[a]" in filtro
    # A foto que não abre fica de fora, e as que sobram dividem o vídeo igual.
    monkeypatch.setattr(edicao_video.videos, "imagem_abre", lambda caminho: not caminho.endswith("outra_0.jpg"))
    assert edicao_video.editar("video.mp4", b"foto", destino, outras_fotos=[b"nao abre", b"triangulo"]) == ""
    ffmpeg = comandos[-1]
    filtro = ffmpeg[ffmpeg.index("-filter_complex") + 1]
    entradas = [ffmpeg[i + 1] for i, parte in enumerate(ffmpeg) if parte == "-i"]
    assert len(entradas) == 7 and entradas[5].endswith("outra_1.jpg")
    assert "enable='lt(t,4.500)'" in filtro and "enable='gte(t,4.500)'[semmoldura]" in filtro
    # Sem a nossa miniatura (P81), nada troca, e as outras fotos nem entram; sem a duração do
    # vídeo, a miniatura fica uma só.
    assert edicao_video.editar("video.mp4", b"foto", destino, miniatura=False, outras_fotos=[b"bola"]) == ""
    ffmpeg = comandos[-1]
    assert "mini0" not in ffmpeg[ffmpeg.index("-filter_complex") + 1] and ffmpeg.count("-i") == 6
    monkeypatch.setattr(edicao_video.videos, "duracao", lambda caminho: 0.0)
    assert edicao_video.editar("video.mp4", b"foto", destino, outras_fotos=[b"bola"]) == ""
    ffmpeg = comandos[-1]
    assert f"[2:v]scale={lado}:-2[mini]" in ffmpeg[ffmpeg.index("-filter_complex") + 1] and ffmpeg.count("-i") == 6
    # No que vai ao ar, o registro diz; sem a nossa miniatura, não.
    _versoes_de_mentira(monkeypatch)
    pedidas = []

    def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outras_fotos=(),
               rotulo_de_ia=False, cor=None):
        pedidas.append(list(outras_fotos))
        return ""
    monkeypatch.setattr(edicao_video, "editar", editar)
    _textos_da_tela(monkeypatch, {"nome": "Cubo", "vantagem": "Estimula o bebê", "lugar": "alto"})
    como = edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Cubo", outras_fotos=[b"bola", b"tri"])[1]
    assert como.endswith(edicao_video.COM_A_MINIATURA_ALTERNADA) and pedidas == [[b"bola", b"tri"]]
    _textos_da_tela(monkeypatch, {"nome": "Cubo", "vantagem": "Estimula o bebê", "lugar": "alto",
                                  "canto_ocupado": True})
    como = edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Cubo", outras_fotos=[b"bola"])[1]
    assert edicao_video.COM_A_MINIATURA_ALTERNADA not in como
    como = edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Cubo")[1]
    assert edicao_video.COM_A_MINIATURA_ALTERNADA not in como


def test_a_miniatura_de_verdade_mostra_cada_foto_uma_vez_pelo_mesmo_tempo(tmp_path):
    # Com o ffmpeg de verdade (P103): vídeo de 9 s com 3 fotos, 3 s cada, na ordem do post; a foto
    # em pé cabe no quadrado da miniatura e não desce além dele.
    if not shutil.which("ffmpeg"):
        return
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0xf0e0c0:size=360x640:rate=30:duration=9",
                    str(video)], check=True)
    fotos = {}
    for nome, cor, tamanho in (("azul", "0x3060a0", "200x200"), ("vermelha", "0xc03030", "200x200"),
                               ("verde", "0x30a040", "100x200")):
        fotos[nome] = tmp_path / f"{nome}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c={cor}:size={tamanho}",
                        "-frames:v", "1", str(fotos[nome])], check=True)
    destino = tmp_path / "editado.mp4"
    assert edicao_video.editar(str(video), fotos["azul"].read_bytes(), str(destino),
                               outras_fotos=[fotos["vermelha"].read_bytes(), fotos["verde"].read_bytes()]) == ""
    from PIL import Image

    def cor(segundo, ponto=edicao_video.CENTRO_DA_MINIATURA):
        quadro = tmp_path / f"quadro_{segundo}.ppm"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(segundo), "-i", str(destino), "-frames:v", "1",
                        str(quadro)], check=True)
        with Image.open(quadro) as imagem:
            r, g, b = imagem.convert("RGB").getpixel(ponto)
        if min(r, g, b) > 150:
            return "fundo"
        return "azul" if b > r + 60 else "vermelha" if r > b + 60 else "verde" if g > r + 60 and g > b + 60 else "?"

    # O vídeo começa depois dos 2 s da foto: 1,5 s, 4,5 s e 7,5 s do vídeo.
    assert [cor(s) for s in (3.5, 6.5, 9.5)] == ["azul", "vermelha", "verde"]
    centro_x, centro_y = edicao_video.CENTRO_DA_MINIATURA
    assert cor(9.5, (centro_x, centro_y + edicao_video.LARGURA_DA_MINIATURA // 2 + 20)) == "fundo"


def test_sem_a_nossa_miniatura_quando_o_criador_ja_pos_coisa_no_canto(monkeypatch, tmp_path):
    # Escolha do Rafael (29/10, P81): no vídeo da cortina, o criador já tinha posto a colagem das
    # cores no alto, e a nossa miniatura cobriu a ponta dela. Quando a IA vê foto, quadro, texto
    # ou figura do criador no canto de cima à direita, a nossa miniatura fica de fora (a foto do
    # começo, a seta e as legendas continuam), e o registro diz.
    _versoes_de_mentira(monkeypatch)
    miniaturas = []

    def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outras_fotos=(),
               rotulo_de_ia=False, cor=None):
        miniaturas.append(miniatura)
        return ""
    monkeypatch.setattr(edicao_video, "editar", editar)
    destino = str(tmp_path / "r.mp4")
    ocupado = {"nome": "Cortina", "vantagem": "Tecido com relevo", "lugar": "alto", "canto_ocupado": True}
    _textos_da_tela(monkeypatch, ocupado)
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Cortina") == (
        "", edicao_video.COM_LEGENDAS + edicao_video.SEM_A_MINIATURA, "")
    assert miniaturas == [0]
    # Canto livre, ou sem a resposta da IA: a miniatura vai, como sempre.
    for textos in (dict(ocupado, canto_ocupado=False), {}):
        miniaturas.clear()
        _textos_da_tela(monkeypatch, textos)
        assert edicao_video.SEM_A_MINIATURA not in edicao_video.editar_para_postar("v.mp4", b"foto", destino,
                                                                                  "Cortina")[1]
        assert miniaturas == [edicao_video.LARGURA_DA_MINIATURA]
    # Sem o Editor 2, o Editor 1 também vai sem ela.
    monkeypatch.setattr(edicao_video.videos, "com_cortes_e_ritmo",
                        lambda video, trechos, destino, letreiros=(), espera=300: "o ffmpeg falhou")
    _textos_da_tela(monkeypatch, ocupado)
    miniaturas.clear()
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Cortina")[1] == (
        edicao_video.SO_COM_O_EDITOR_1 + edicao_video.SEM_A_MINIATURA)
    assert miniaturas == [0]


def test_canto_so_com_o_que_foi_filmado_nao_tira_a_miniatura(monkeypatch, tmp_path):
    # Vídeo do Rafael das 22:38 de 02/11 ("Pq não veio a miniatura?"): a IA contou como coisa do
    # criador no alto a caixa do produto, filmada atrás do brinquedo, e a miniatura saiu (P81).
    # Quando a resposta tira ou diminui a miniatura, uma pergunta só sobre o canto confere: só
    # filmado, a miniatura fica do tamanho de sempre; com algo posto por cima, ou sem resposta,
    # fica a 1ª.
    import json

    import api_gemini
    primeira = {"nome": "Brinquedo Fofo", "vantagem": "Macio de apertar", "lugar": "alto", "canto_ocupado": True,
                "por_cima_no_alto": [{"esquerda": 60, "direita": 100, "topo": 3, "base": 35}]}
    pedidos = []

    def com_o_canto(por_cima, resposta=primeira):
        async def analisar(video, prompt, imagens=None):
            canto = "Olhe só o canto de cima à direita" in prompt
            pedidos.append("canto" if canto else "textos")
            if canto:
                return json.dumps({"o_que_ha_no_canto": "a caixa do produto", "por_cima_na_edicao": por_cima})
            return json.dumps(resposta)
        monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)

    async def texto(prompt, imagens=None):
        return None
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", texto)
    com_o_canto(False)
    textos = edicao_video.textos_da_tela("v.mp4", "Brinquedo")
    assert pedidos == ["textos", "canto"]
    assert edicao_video.miniatura_no_video(textos) == edicao_video.LARGURA_DA_MINIATURA
    assert textos["canto_filmado"] == "a coisa do criador no alto começa a 3% da altura"
    for por_cima in (True, None):
        com_o_canto(por_cima)
        textos = edicao_video.textos_da_tela("v.mp4", "Brinquedo")
        assert edicao_video.miniatura_no_video(textos) == 0 and "canto_filmado" not in textos
    # Com o canto livre na 1ª resposta, não há o que conferir: uma chamada só.
    pedidos.clear()
    com_o_canto(False, dict(primeira, canto_ocupado=False, por_cima_no_alto=[]))
    edicao_video.textos_da_tela("v.mp4", "Brinquedo")
    assert pedidos == ["textos"]
    # No que vai ao ar, o registro diz que a miniatura ficou e o que a 1ª resposta dizia.
    _versoes_de_mentira(monkeypatch)
    miniaturas = []

    def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outras_fotos=(),
               rotulo_de_ia=False, cor=None):
        miniaturas.append(miniatura)
        return ""
    monkeypatch.setattr(edicao_video, "editar", editar)
    _textos_da_tela(monkeypatch, {"nome": "Brinquedo Fofo", "lugar": "alto", "canto_ocupado": False,
                                  "canto_filmado": "a coisa do criador no alto começa a 3% da altura"})
    edicao_video.editar_para_postar("v.mp4", b"foto", str(tmp_path / "r.mp4"), "Brinquedo")
    assert miniaturas == [edicao_video.LARGURA_DA_MINIATURA]
    linhas = [(l[2], l[3]) for l in edicao_video.registro_processos.contagem("2000-01-01 00:00:00")
              if l[1] == edicao_video.PROCESSO_DO_CANTO]
    assert linhas == [(edicao_video.CANTO_FILMADO, "a 1ª resposta: a coisa do criador no alto começa a 3% da altura")]


def test_a_miniatura_sai_quando_a_legenda_do_criador_passa_por_ela(monkeypatch, tmp_path):
    # Print do Rafael (29/10): num rascunho, a legenda do criador, centralizada logo abaixo da
    # barra de busca, passava por baixo da ponta da nossa miniatura, e a IA tinha dito que o
    # canto estava livre (P81). Ela diz também onde fica cada coisa que o criador pôs no alto
    # da tela, e a miniatura não passa por nenhuma, com a folga: diminui para ficar acima dela
    # (P97) ou, quando nem com 2/3 do tamanho cabe, sai.
    for prompt in (edicao_video.PROMPT_DOS_TEXTOS, edicao_video.PROMPT_DAS_VERSOES):
        assert "\"por_cima_no_alto\"" in prompt and "em qualquer momento" in prompt
    legenda = {"esquerda": 29, "direita": 69, "topo": 11, "base": 14}
    textos = edicao_video._nome_lugar_e_falas({"canto_ocupado": False, "por_cima_no_alto": [legenda]})
    assert textos == {"canto_ocupado": False, "por_cima": [(29.0, 69.0, 11.0, 14.0)]}
    assert edicao_video.miniatura_no_video(textos) == 0
    # A IA errando um pouco para fora da miniatura (até uns 66% da largura) ainda conta, pela folga.
    assert edicao_video.miniatura_no_video({"por_cima": [(30.0, 66.5, 11.0, 14.0)]}) == 0
    # Longe dela (no alto à esquerda, ou logo abaixo), a miniatura fica inteira.
    for longe in ((5.0, 50.0, 5.0, 12.0), (20.0, 80.0, 29.0, 33.0)):
        assert edicao_video.miniatura_no_video({"canto_ocupado": False, "por_cima": [longe]}) == (
            edicao_video.LARGURA_DA_MINIATURA)
    # Resposta em fração, com os lados trocados, ou sem os quatro números.
    assert edicao_video._por_cima_no_alto([{"esquerda": 0.69, "direita": 0.29, "topo": 0.18, "base": 0.15},
                                           {"esquerda": "x"}, "texto", {"esquerda": 1, "direita": 2},
                                           {"esquerda": float("nan"), "direita": 2, "topo": 1, "base": 2}]) == [
        (29.0, 69.0, 15.0, 18.0)]
    assert edicao_video._por_cima_no_alto(None) == [] and "por_cima" not in edicao_video._nome_lugar_e_falas(
        {"por_cima_no_alto": []})
    # No que vai ao ar, o vídeo vai sem ela, e o registro diz.
    _versoes_de_mentira(monkeypatch)
    miniaturas = []

    def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outras_fotos=(),
               rotulo_de_ia=False, cor=None):
        miniaturas.append(miniatura)
        return ""
    monkeypatch.setattr(edicao_video, "editar", editar)
    _textos_da_tela(monkeypatch, {"nome": "Clipe de Unha", "vantagem": "Tira o gel sem esforço", "lugar": "alto",
                                  "texto_no_video": True, "canto_ocupado": False,
                                  "por_cima": [(29.0, 69.0, 11.0, 14.0)]})
    como = edicao_video.editar_para_postar("v.mp4", b"foto", str(tmp_path / "r.mp4"), "Clipe de Unha")[1]
    assert como.endswith(edicao_video.SEM_A_MINIATURA) and miniaturas == [0]


def test_a_miniatura_fica_do_tamanho_de_sempre_abaixo_da_barra_de_busca_e_longe_da_borda():
    # Vídeo do Rafael das 22:01 de 01/11 (P120): a miniatura ficava grudada no canto de cima à
    # direita, embaixo do ícone da barra de busca do app. A ponta de cima fica abaixo da barra de
    # busca e a da direita um pouco para dentro da borda que o app mostra. Print dele das 01:29 de
    # 02/11 (P121): uns 15% menor (152 px), ela ficou pequena demais; fica do tamanho de sempre.
    largura = edicao_video.LARGURA_DA_MINIATURA
    canto_x, canto_y = edicao_video.CANTO_DA_MINIATURA
    largura_da_tela, altura = edicao_video.TELA
    assert largura == 180 == largura_da_tela // 4
    assert canto_y >= edicao_video.FIM_DA_BARRA_DE_BUSCA + 5
    assert edicao_video.VISIVEL_NO_APP[1] - canto_x >= 12
    # Os textos do Editor 2 não passam por ela: o do alto fica ao lado, o do meio logo abaixo.
    x, _topo, largura_maxima, _linhas = edicao_video.LUGARES_DOS_TEXTOS["alto"]
    assert x + largura_maxima + 56 < canto_x - largura
    topo_do_meio = edicao_video.LUGARES_DOS_TEXTOS["meio"][1]
    assert topo_do_meio >= canto_y + largura + 10
    # O pedido à IA diz o lugar do meio onde ele fica, logo abaixo da miniatura.
    assert f"\"meio\" (centralizado, entre uns {round(topo_do_meio * 100 / altura)}% e" in edicao_video.PROMPT_DOS_TEXTOS
    # A IA olha o lugar onde ela fica, com a folga (P81), e o pedido diz o mesmo lugar.
    comeco, fim, desde, ate = edicao_video.CANTO_OLHADO_PELA_IA
    folga = edicao_video.FOLGA_DA_MINIATURA
    assert comeco * largura_da_tela / 100 <= canto_x - largura - folga and canto_x <= fim * largura_da_tela / 100
    assert desde * altura / 100 <= canto_y - folga and canto_y + largura + folga <= ate * altura / 100
    for prompt in (edicao_video.PROMPT_DOS_TEXTOS, edicao_video.PROMPT_DAS_VERSOES):
        assert f"de uns {comeco}% a {fim}% da largura e de uns {desde}% a {ate}% da altura" in prompt
    # O que o criador pôs bem no alto, acima dela, não a tira mais do vídeo.
    assert edicao_video.miniatura_no_video({"canto_ocupado": False, "por_cima": [(70.0, 95.0, 1.0, 7.0)]}) == largura


def test_a_miniatura_diminui_para_caber_acima_do_que_o_criador_pos(monkeypatch, tmp_path):
    # Escolha do Rafael (29/10, P97): no rascunho das 23:09, o balão de resposta da criadora
    # ficava logo abaixo do canto da nossa miniatura, e a folga a tirou, mas ela caberia acima
    # dele. A miniatura diminui, no mesmo canto, só o necessário para ficar acima da coisa do
    # criador sem encostar (a folga); menor que 2/3 do tamanho de sempre, fica de fora.
    editar_de_verdade = edicao_video.editar
    assert edicao_video.CANTO_DA_MINIATURA == (657, 150) and edicao_video.MENOR_MINIATURA == 120
    assert edicao_video.centro_da_miniatura(edicao_video.LARGURA_DA_MINIATURA) == edicao_video.CENTRO_DA_MINIATURA
    balao = (55.0, 95.0, 24.5, 30.0)
    largura = edicao_video.miniatura_no_video({"canto_ocupado": False, "por_cima": [balao]})
    assert largura == 132 and not edicao_video._cruza_a_miniatura(balao, largura)
    x, y = edicao_video.centro_da_miniatura(largura)
    assert (x + largura // 2, y - largura // 2) == edicao_video.CANTO_DA_MINIATURA
    # Sem encostar: a base da miniatura fica a folga acima do topo do balão.
    assert y + largura // 2 + edicao_video.FOLGA_DA_MINIATURA <= balao[2] * edicao_video.TELA[1] / 100
    # A IA viu o balão no canto (canto_ocupado) e disse onde: vale a conta do lugar.
    assert edicao_video.miniatura_no_video({"canto_ocupado": True, "por_cima": [balao]}) == 132
    # Com 2/3 do tamanho ainda vai; menor que isso, fica de fora.
    assert edicao_video.miniatura_no_video({"por_cima": [(55.0, 95.0, 23.5, 30.0)]}) == 120
    assert edicao_video.miniatura_no_video({"por_cima": [(55.0, 95.0, 23.4, 30.0)]}) == 0
    # Com várias, a mais alta decide.
    assert edicao_video.miniatura_no_video({"por_cima": [balao, (40.0, 80.0, 24.0, 28.0)]}) == 126
    # O canto ocupado sem nenhuma coisa no canto dizendo onde: fica de fora, como na P81.
    assert edicao_video.miniatura_no_video({"canto_ocupado": True, "por_cima": [(5.0, 40.0, 2.0, 8.0)]}) == 0
    # O que vai ao ar leva a miniatura menor, e o registro diz.
    _versoes_de_mentira(monkeypatch)
    miniaturas = []

    def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outras_fotos=(),
               rotulo_de_ia=False, cor=None):
        miniaturas.append(miniatura)
        return ""
    monkeypatch.setattr(edicao_video, "editar", editar)
    _textos_da_tela(monkeypatch, {"nome": "Mercadinho", "vantagem": "Brincar de vender", "lugar": "alto",
                                  "canto_ocupado": True, "por_cima": [balao]})
    como = edicao_video.editar_para_postar("v.mp4", b"foto", str(tmp_path / "r.mp4"), "Mercadinho")[1]
    assert como.endswith(edicao_video.COM_A_MINIATURA_MENOR) and miniaturas == [132]
    # A edição recebe a largura e o centro no mesmo canto.
    pedidos = []
    monkeypatch.setattr(edicao_video.videos, "com_foto_e_miniatura",
                        lambda video, foto, destino, segundos, miniatura, centro, *resto, **opcoes: pedidos.append(
                            (miniatura, centro)) or "")
    for pedida, esperada in ((True, (180, (567, 240))), (132, (132, (591, 216))), (False, (0, (657, 150)))):
        assert editar_de_verdade("v.mp4", b"foto", str(tmp_path / "r.mp4"), miniatura=pedida) == ""
        assert pedidos.pop() == esperada

def test_os_quadros_do_criador_nao_tiram_as_nossas_legendas():
    # Escolha do Rafael (29/10, P82): a IA contava como texto próprio do vídeo (P52) os quadros
    # que o criador pôs por cima com a foto do produto (as cores, a quantidade), e as nossas
    # legendas saíam (4 de 9 rascunhos editados em 29/10). O texto dentro deles não conta mais,
    # e as legendas entram onde não os cobrem; a IA também diz se o canto da miniatura está livre.
    for prompt in (edicao_video.PROMPT_DOS_TEXTOS, edicao_video.PROMPT_DAS_VERSOES):
        assert "nem o texto dentro das fotos e quadros do produto que o vídeo pôs por cima" in prompt
        assert "sem cobrir, em nenhum momento, as fotos, quadros ou textos" in prompt
        assert "\"canto_ocupado\"" in prompt and "não contam marca d'água, logo nem nome do perfil" in prompt
    assert edicao_video._nome_lugar_e_falas({"canto_ocupado": True, "texto_no_video": "sim"}) == {
        "canto_ocupado": True}
    assert edicao_video.miniatura_no_video({"canto_ocupado": True}) == 0
    assert edicao_video.miniatura_no_video({"canto_ocupado": False}) == edicao_video.LARGURA_DA_MINIATURA
    assert edicao_video.miniatura_no_video({}) == edicao_video.LARGURA_DA_MINIATURA


def test_texto_do_criador_so_no_fim_nao_tira_os_nossos_textos(monkeypatch):
    # Rascunho dos fones de 02/11 (vídeo do Rafael das 09:21): as duas frases do criador só
    # apareciam nos últimos 5 s de 26, e a IA disse que o vídeo tinha texto próprio na maior
    # parte do tempo; o rascunho foi sem os nossos textos. A P52 vale para mais da metade do
    # tempo: a IA diz os trechos, e a conta é feita aqui.
    import api_gemini
    respostas, duracoes = [], []

    async def analisar(video, prompt, imagens=None):
        return respostas.pop(0)

    monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(edicao_video.videos, "duracao", lambda video, timeout=30: duracoes.append(video) or 26.4)
    respostas.append('{"nome": "Fone", "lugar": "alto", "textos_do_video": [{"inicio": 20.5, "fim": 23.0}, '
                     '{"inicio": 23.0, "fim": 26.0}]}')
    textos = edicao_video.textos_da_tela("v.mp4", "Fone Marca X")
    assert textos["texto_no_video"] is False and textos["parte_com_texto"] == 0.21
    assert edicao_video.lugar_dos_textos(textos) == "alto"
    # Na maior parte do tempo, continua sem os nossos (o que se cruza conta uma vez).
    respostas.append('{"nome": "Fone", "lugar": "alto", "textos_do_video": [{"inicio": 0, "fim": 10}, '
                     '{"inicio": 5, "fim": 20}, {"inicio": 6, "fim": 8}]}')
    textos = edicao_video.textos_da_tela("v.mp4", "Fone Marca X")
    assert textos["texto_no_video"] is True and textos["parte_com_texto"] == 0.76
    assert edicao_video.lugar_dos_textos(textos) == edicao_video.SEM_LUGAR
    # As versões do exemplo seguem a mesma conta.
    respostas.append('{"nome": "Fone", "lugar": "meio", "textos_do_video": [{"inicio": 24, "fim": 99}]}')
    assert edicao_video.textos_das_versoes("v.mp4", "Fone Marca X")["texto_no_video"] is False
    # Sem nenhum trecho, a duração nem é lida, e o vídeo leva os nossos textos.
    duracoes.clear()
    respostas.append('{"nome": "Fone", "lugar": "alto", "textos_do_video": []}')
    assert "texto_no_video" not in edicao_video.textos_da_tela("v.mp4", "Fone Marca X") and duracoes == []
    # Os trechos: o que passa do fim do vídeo é cortado, e o que veio errado fica de fora.
    assert edicao_video._trechos_com_texto([{"inicio": 3, "fim": 1}, {"inicio": "x", "fim": 2}, "texto",
                                            {"inicio": -1, "fim": 2}, {"inicio": 2, "fim": 4.5}]) == [(2.0, 4.5)]
    assert edicao_video._trechos_com_texto(None) is None
    assert edicao_video.parte_com_texto_proprio([(8.0, 30.0)], 10.0) == 0.2
    assert edicao_video.parte_com_texto_proprio([(1.0, 2.0)], 0.0) is None


def test_o_que_foi_filmado_nao_conta_como_coisa_do_criador():
    # Rascunho dos fones de 02/11: a IA contou o nome escrito na capa de uma revista em cima da
    # mesa como texto do criador no canto da nossa miniatura (P81), e a miniatura saiu. Só conta
    # o que o criador acrescentou por cima na edição; o lugar dos nossos textos não cobre o que
    # ele pôs por cima em nenhum momento (P52 e P82).
    for prompt in (edicao_video.PROMPT_DOS_TEXTOS, edicao_video.PROMPT_DAS_VERSOES):
        texto = prompt.format(nome="Fone")
        assert edicao_video._O_QUE_FOI_FILMADO_NAO_CONTA in texto
        assert "uma revista ou a tela de um celular" in texto and "nunca contam" in texto
        assert "as coisas filmadas também não" in texto and "nome do perfil nem as coisas filmadas" in texto
        assert "sem cobrir, em nenhum momento, as fotos, quadros ou textos" in texto
        assert '"textos_do_video": []' in texto and '"texto_no_video"' not in texto


def test_o_registro_diz_por_que_a_miniatura_ficou_menor_ou_de_fora(monkeypatch, tmp_path):
    # O registro dizia só "sem a nossa miniatura": separa o canto ocupado sem dizer onde (P81)
    # da coisa do criador no alto que passa por ela (P97), e o texto próprio diz a parte do tempo.
    import registro_processos as rp
    _versoes_de_mentira(monkeypatch)
    destino = str(tmp_path / "rascunho.mp4")
    base = {"nome": "Fone", "vantagem": "Encaixe firme", "chamada": "Toque aqui embaixo", "lugar": "alto"}
    _textos_da_tela(monkeypatch, dict(base, canto_ocupado=True))
    assert edicao_video.SEM_A_MINIATURA in edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Fone")[1]
    _textos_da_tela(monkeypatch, dict(base, canto_ocupado=True, por_cima=[(55.0, 95.0, 25.0, 30.0)]))
    assert edicao_video.COM_A_MINIATURA_MENOR in edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Fone")[1]
    # Com o canto livre, a miniatura vai inteira, e nada é anotado.
    _textos_da_tela(monkeypatch, dict(base, canto_ocupado=False))
    edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Fone")
    registro = rp.sequencia("shopee_video", edicao_video.PROCESSO_DO_CANTO, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in registro] == [
        ("de fora", edicao_video.CANTO_SEM_DIZER_ONDE), ("menor", "a coisa do criador no alto começa a 25% da altura")]
    # O texto próprio na maior parte do tempo diz quanto, no detalhe do registro da edição.
    _textos_da_tela(monkeypatch, dict(base, texto_no_video=True, parte_com_texto=0.76))
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Fone") == (
        "", edicao_video.SEM_LEGENDAS_NA_TELA, edicao_video.TEXTO_JA_NO_VIDEO + " (76% do tempo)")


# --- As legendas da fala (escolha do Rafael, 01/11, P118) ---

def _medidas(imagem):
    """(largura, altura) do PNG pelo cabeçalho."""
    return int.from_bytes(imagem[16:20], "big"), int.from_bytes(imagem[20:24], "big")


def test_a_seta_tem_o_tamanho_que_a_legenda_usa():
    from PIL import Image
    with Image.open(edicao_video.SETA) as seta:
        assert seta.size == edicao_video.TAMANHO_DA_SETA


def test_legenda_da_fala_fica_com_o_pe_na_altura_do_pe_da_seta_a_direita_dela():
    # O pé da legenda na altura do pé da seta (logo abaixo vem o cartão do produto), em letra
    # pequena, sem cobrir a seta e dentro do que o app mostra.
    letreiros = edicao_video.letreiros_da_fala([(1.0, 3.0, "Olha que lindo esse vestido")], 10.0)
    assert len(letreiros) == 1
    imagem, inicio, fim, x, y = letreiros[0]
    largura, altura = _medidas(imagem)
    # O pé e o lado da seta sem a margem transparente do arquivo (onde ficam o contorno e a sombra).
    margem = edicao_video.MARGEM_DA_SETA
    pe_da_seta = edicao_video.CENTRO_DA_SETA[1] + edicao_video.TAMANHO_DA_SETA[1] // 2 - margem
    direita_da_seta = edicao_video.CENTRO_DA_SETA[0] + edicao_video.TAMANHO_DA_SETA[0] // 2 - margem
    assert (inicio, fim) == (1.0, 3.0) and y + altura == edicao_video.PE_DA_LEGENDA == pe_da_seta
    assert edicao_video.PE_DA_LEGENDA <= edicao_video.COMECO_DO_CARTAO_DO_PRODUTO
    assert x > direita_da_seta and x + largura <= edicao_video.VISIVEL_NO_APP[1]
    # Pedido do Rafael (02/11): a legenda para antes da coluna dos ícones do app à direita (o perfil,
    # o coração e os comentários), que começa em x 586 no celular dele.
    assert edicao_video.COLUNA_DOS_ICONES == 586
    assert x + largura <= edicao_video.DIREITA_DA_LEGENDA < edicao_video.COLUNA_DOS_ICONES
    longas = edicao_video.letreiros_da_fala(
        [(1.0, 6.0, "Fechamento prático, zíper frontal e punhos com zíper, variedade de tamanhos disponível")], 10.0)
    assert longas
    for imagem, _inicio, _fim, x, _y in longas:
        assert x + _medidas(imagem)[0] <= edicao_video.DIREITA_DA_LEGENDA
    # Até 2 linhas (LINHAS_DA_LEGENDA), em letra pequena: a frase curta vai numa linha só, bem menor
    # que a dos textos da tela.
    assert altura < edicao_video.LETRA_DOS_TEXTOS[0] * 2 * edicao_video.LINHAS_DA_LEGENDA
    curta = edicao_video.letreiros_da_fala([(1.0, 3.0, "Olha que lindo")], 10.0)[0][0]
    assert _medidas(curta)[1] < edicao_video.LETRA_DOS_TEXTOS[0] * 2


def test_trecho_que_nao_cabe_em_duas_linhas_e_dividido_com_o_tempo_repartido():
    texto = ("Esse aqui é o melhor organizador que eu já comprei na Shopee, cabe tudo dentro e ainda "
             "fica bonito na bancada da cozinha")
    letreiros = edicao_video.letreiros_da_fala([(2.0, 8.0, texto)], 20.0)
    assert len(letreiros) >= 2
    assert letreiros[0][1] == 2.0 and letreiros[-1][2] == 8.0
    for (_, _, fim, _, _), (_, inicio, _, _, _) in zip(letreiros, letreiros[1:]):
        assert fim == inicio
    for imagem, _, _, x, y in letreiros:
        largura, altura = _medidas(imagem)
        assert y + altura == edicao_video.PE_DA_LEGENDA and x + largura <= edicao_video.DIREITA_DA_LEGENDA


def test_fala_longa_vira_varias_legendas_sem_perder_nenhuma_palavra():
    # Pedido do Rafael (02/11, vídeo das 12:28): a legenda da fala é exatamente o que foi dito. Na
    # jaqueta, com o limite de 50 letras por trecho no pedido, a IA encurtou "Couro ecológico premium,
    # fabricada em couro de alta qualidade" e pulou a frase do revestimento. A frase longa vem inteira
    # e é dividida aqui, em legendas de até 2 linhas, com o tempo repartido e todas as palavras.
    texto = ("Couro ecológico premium, fabricada em couro de alta qualidade, resistente e sustentável. "
             "Revestimento interno em poliéster ou veludo para melhor aquecimento.")
    pedacos = edicao_video.pedacos_da_legenda(30.0, 38.0, texto)
    assert len(pedacos) >= 3 and " ".join(p[2] for p in pedacos) == texto
    assert pedacos[0][0] == 30.0 and pedacos[-1][1] == 38.0
    for (_, fim, _, _), (inicio, _, _, _) in zip(pedacos, pedacos[1:]):
        assert fim == inicio
    for inicio, fim, parte, imagem in pedacos:
        assert imagem and fim > inicio
    # O corte fica perto do meio, de preferência depois de uma vírgula ou de um ponto.
    assert edicao_video._ponto_de_corte("Couro ecológico premium, fabricada em couro".split()) == 3
    assert edicao_video._ponto_de_corte("um dois três quatro".split()) == 2


def test_o_pedido_da_ia_quer_a_fala_inteira_palavra_por_palavra():
    pedido = edicao_video.PROMPT_DOS_TEXTOS.format(nome="Jaqueta")
    for exigido in ("palavra por palavra", "sem resumir", "sem pular nenhuma frase", "Siga o áudio, não a imagem"):
        assert exigido in pedido
    # Sem limite de tamanho por trecho: com ele, a IA encurtava a fala.
    assert "trechos curtos" not in pedido and "caracteres, como [" not in pedido


def test_legendas_que_se_encostam_cortam_e_a_curta_demais_sai():
    letreiros = edicao_video.letreiros_da_fala(
        [(0.0, 3.0, "Primeira fala"), (2.5, 2.7, "rápida"), (2.7, 6.0, "Segunda fala"), (9.5, 14.0, "Fim")], 11.0)
    # A primeira acaba quando a seguinte começa; a de 0,2 s sai; a última fica dentro do vídeo.
    assert [(inicio, fim) for _, inicio, fim, _, _ in letreiros] == [(0.0, 2.5), (2.7, 6.0), (9.5, 11.0)]


# As palavras de um vídeo no áudio (o reconhecimento de voz, em segundos) e as legendas da IA com o tempo
# dela adiantado, como no vídeo do Rafael das 19:29 de 02/11 (até 2 s antes da fala).
AUDIO_DO_VESTIDO = [(1.0, 1.3, "Olha"), (1.3, 1.5, "só"), (1.5, 1.8, "esse"), (1.8, 2.4, "vestido,"),
                    (4.0, 4.2, "não"), (4.2, 4.8, "amassa"), (4.8, 5.0, "e"), (5.0, 5.6, "seca"), (5.6, 5.9, "rápido.")]
FALA_DO_VESTIDO = [(0.5, 2.0, "Olha só esse vestido,"), (2.0, 4.0, "não amassa e seca rapidinho.")]


def test_as_legendas_da_fala_seguem_o_tempo_do_audio():
    no_tempo, achadas, total = edicao_video.legendas_no_tempo_da_fala(FALA_DO_VESTIDO, AUDIO_DO_VESTIDO)
    # A palavra que o áudio não reconheceu ("rapidinho") fica depois da última achada.
    assert (achadas, total) == (8, 9)
    assert [(inicio, fim, texto) for inicio, fim, texto, _tempos in no_tempo] == [
        (1.0, 2.7, "Olha só esse vestido,"), (4.0, 6.2, "não amassa e seca rapidinho.")]
    assert no_tempo[1][3] == [(4.0, 4.2), (4.2, 4.8), (4.8, 5.0), (5.0, 5.6), (5.6, 5.9)]
    # Na tela: cada uma na hora da fala dela, a 1ª até um pouco depois da última palavra.
    letreiros = edicao_video.letreiros_da_fala(no_tempo, 10.0)
    assert [(inicio, fim) for _, inicio, fim, _, _ in letreiros] == [(1.0, 2.7), (4.0, 6.2)]
    # Com menos da metade das palavras da IA no áudio, o tempo fica o da IA.
    assert edicao_video.legendas_no_tempo_da_fala(FALA_DO_VESTIDO, [(0.0, 0.5, "outra"), (0.5, 1.0, "coisa")])[0] is None
    assert edicao_video.legendas_no_tempo_da_fala(FALA_DO_VESTIDO, [])[0] is None


def test_palavra_com_hifen_e_sem_acento_acha_a_do_audio():
    no_tempo, achadas, total = edicao_video.legendas_no_tempo_da_fala(
        [(0.0, 1.0, "Kit mesa posta de café")], [(2.0, 2.3, "kit"), (2.3, 2.6, "mesa"), (2.6, 3.0, "-posta"),
                                                 (3.0, 3.1, "de"), (3.1, 3.6, "cafe")])
    assert (achadas, total) == (5, 5) and no_tempo[0][:2] == (2.0, 3.9)


def test_palavras_que_faltam_ficam_entre_as_vizinhas():
    tempos = [None, (1.0, 1.5), None, None, (3.0, 3.5), None]
    edicao_video._preencher_os_tempos(tempos)
    assert tempos == [(0.7, 1.0), (1.0, 1.5), (1.5, 2.25), (2.25, 3.0), (3.0, 3.5), (3.5, 3.8)]


def test_a_legenda_longa_divide_quando_a_palavra_e_dita():
    palavras = [f"palavra{n}" for n in range(24)]
    tempos = [(1.0 + n * 0.5, 1.4 + n * 0.5) for n in range(24)]
    pedacos = edicao_video.pedacos_da_legenda(1.0, 13.4, " ".join(palavras), tempos)
    assert len(pedacos) > 1 and " ".join(texto for _i, _f, texto, _im in pedacos) == " ".join(palavras)
    for inicio, _fim, texto, _imagem in pedacos[1:]:
        assert inicio == tempos[palavras.index(texto.split()[0])][0]


def test_sem_o_reconhecimento_de_voz_as_legendas_ficam_com_o_tempo_da_ia(monkeypatch, tmp_path):
    video = str(tmp_path / "v.mp4")
    open(video, "wb").write(b"video")
    # O reconhecimento de mentira do conftest não abre (os testes não baixam o modelo).
    assert edicao_video.legendas_no_tempo(video, FALA_DO_VESTIDO) == (
        FALA_DO_VESTIDO, edicao_video.PELO_TEMPO_DA_IA, edicao_video.SEM_O_RECONHECIMENTO)
    monkeypatch.setattr(edicao_video.videos, "palavras_faladas", lambda caminho: AUDIO_DO_VESTIDO)
    legendas, resultado, detalhe = edicao_video.legendas_no_tempo(video, FALA_DO_VESTIDO)
    assert (resultado, detalhe) == (edicao_video.PELO_AUDIO, "8 de 9 palavras no áudio")
    assert legendas[0][:2] == (1.0, 2.7)
    monkeypatch.setattr(edicao_video.videos, "palavras_faladas", lambda caminho: [(0.0, 0.5, "outra")])
    assert edicao_video.legendas_no_tempo(video, FALA_DO_VESTIDO) == (
        FALA_DO_VESTIDO, edicao_video.PELO_TEMPO_DA_IA, f"{edicao_video.FALA_NAO_BATEU} (0 de 9 palavras no áudio)")
    assert edicao_video.legendas_no_tempo(video, []) == ([], "", "")


def test_a_resposta_da_ia_vira_as_legendas_so_com_os_trechos_certos():
    textos = edicao_video._nome_lugar_e_falas({
        "legendas": [{"inicio": 3, "fim": 4.5, "texto": "e não amassa"},
                     {"inicio": 0.5, "fim": 2, "texto": "Olha só esse vestido 😍"},
                     {"inicio": 5, "fim": 4, "texto": "ao contrário"},
                     {"inicio": "x", "fim": 6, "texto": "sem número"},
                     {"inicio": 6, "fim": 7, "texto": "Straße"}, "quebrado"],
        "legenda_no_video": False})
    assert textos["legendas"] == [(0.5, 2.0, "Olha só esse vestido"), (3.0, 4.5, "e não amassa")]
    assert textos["legenda_no_video"] is False
    assert "legendas" not in edicao_video._nome_lugar_e_falas({"legendas": "nenhuma"})


def test_sem_fala_ou_com_a_fala_ja_escrita_o_video_vai_sem_as_legendas():
    fala = [(0.5, 2.0, "Olha só esse vestido")]
    assert edicao_video.legendas_da_fala({"legendas": fala}) == (fala, "")
    assert edicao_video.legendas_da_fala({"legendas": []}) == ([], edicao_video.SEM_FALA)
    assert edicao_video.legendas_da_fala({"legendas": fala, "legenda_no_video": True}) == (
        [], edicao_video.LEGENDA_JA_NO_VIDEO)
    assert edicao_video.legendas_da_fala({}) == ([], edicao_video.SEM_AS_LEGENDAS_DA_IA)


def test_os_dois_pedidos_a_ia_trazem_as_legendas_da_fala(monkeypatch):
    import api_gemini
    pedidos = []

    async def analisar(video, prompt, imagens=None):
        pedidos.append(prompt)
        return ('{"nome": "Vestido", "vantagem": "Tecido leve", "lugar": "alto", "legenda_no_video": false, '
                '"legendas": [{"inicio": 0.5, "fim": 2.0, "texto": "Olha só esse vestido"}]}')

    async def sem_revisao(prompt, imagens=None):
        return None

    monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", sem_revisao)
    textos = edicao_video.textos_da_tela("v.mp4", "Vestido Marca X")
    assert textos["legendas"] == [(0.5, 2.0, "Olha só esse vestido")] and textos["legenda_no_video"] is False
    assert edicao_video.textos_das_versoes("v.mp4", "Vestido Marca X")["legendas"] == textos["legendas"]
    # Só a voz de gente falando em português: sem fala, música, canto ou outra língua, nenhuma.
    for pedido in pedidos:
        assert '"legendas"' in pedido and '"legenda_no_video"' in pedido and "não música nem canto" in pedido


def test_o_que_vai_ao_ar_leva_as_legendas_da_fala_e_o_registro_conta(monkeypatch, tmp_path):
    import registro_processos as rp
    montados, editados = _versoes_de_mentira(monkeypatch)
    fala = [(0.5, 2.0, "Olha só esse vestido"), (3.0, 4.5, "o tecido é bem leve")]
    _textos_da_tela(monkeypatch, {"nome": "Vestido", "vantagem": "Tecido leve", "chamada": "Toque aqui embaixo",
                                  "lugar": "alto", "legendas": fala, "legenda_no_video": False})
    destino = str(tmp_path / "rascunho.mp4")
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Vestido") == (
        "", edicao_video.COM_LEGENDAS + edicao_video.COM_AS_LEGENDAS_DA_FALA, "")
    # Os 3 textos da tela e as 2 legendas por cima do vídeo inteiro, e depois o Editor 1.
    assert montados == [([(0.0, 12.0, 1.0)], 5)] and editados[-1][1] == "rascunho.mp4"
    registro = rp.sequencia("shopee_video", edicao_video.PROCESSO_DAS_LEGENDAS, "2000-01-01 00:00:00")
    # Com as palavras e os segundos de fala: o checkup vê se a IA resume a fala (pedido do Rafael, 02/11).
    assert [(r[2], r[3]) for r in registro] == [("postas", "2 trecho(s), 9 palavra(s) em 3 s de fala")]
    # Sem o reconhecimento de voz (o de mentira do conftest), o tempo é o da IA, e o registro diz por quê.
    tempo = rp.sequencia("shopee_video", edicao_video.PROCESSO_DO_TEMPO_DAS_LEGENDAS, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in tempo] == [(edicao_video.PELO_TEMPO_DA_IA, edicao_video.SEM_O_RECONHECIMENTO)]

    # Sem lugar para os textos (P47), as legendas da fala vão do mesmo jeito.
    montados.clear()
    _textos_da_tela(monkeypatch, {"nome": "Vestido", "lugar": edicao_video.SEM_LUGAR, "legendas": fala})
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Vestido")[1] == (
        edicao_video.SEM_LEGENDAS_NA_TELA + edicao_video.COM_AS_LEGENDAS_DA_FALA)
    assert montados == [([(0.0, 12.0, 1.0)], 2)]

    # O vídeo que já tem a fala escrita na tela vai sem elas, e o registro diz por quê.
    montados.clear()
    _textos_da_tela(monkeypatch, {"nome": "Vestido", "lugar": edicao_video.SEM_LUGAR, "legendas": fala,
                                  "legenda_no_video": True})
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Vestido")[1] == edicao_video.SEM_LEGENDAS_NA_TELA
    assert montados == []
    registro = rp.sequencia("shopee_video", edicao_video.PROCESSO_DAS_LEGENDAS, "2000-01-01 00:00:00")
    assert (registro[-1][2], registro[-1][3]) == ("sem as legendas", edicao_video.LEGENDA_JA_NO_VIDEO)


def test_o_exemplo_do_editor_2_mostra_as_legendas_da_fala_como_vai_ao_ar(monkeypatch, tmp_path):
    video = str(tmp_path / "v1.mp4")
    open(video, "wb").close()
    _fontes_de_mentira(monkeypatch, {"viral": [("viral:1", video, "https://s.shopee.com.br/1", "")]},
                       fonte_do_robo="viral")
    monkeypatch.setattr(edicao_video, "_produto_do_link", lambda link: {"nome": "Vestido Marca X", "preco": 59.9})
    fala = [(0.5, 2.0, "Olha só esse vestido")]
    monkeypatch.setattr(edicao_video, "textos_das_versoes", lambda video, nome: {
        "nome": "Vestido", "vantagem": "Tecido leve", "lugar": "alto", "legendas": fala, "falas": [[0.5, 2.0]]})
    recebidas = []

    def editar_2_e_versoes(video, foto, destino, nome="", vantagem="", versoes_da_ia=(), chamada="", falas=None,
                           lugar=None, miniatura=True, legendas=(), cor=None):
        recebidas.append(list(legendas))
        return "", {"versoes": []}

    monkeypatch.setattr(edicao_video, "editar_2_e_versoes", editar_2_e_versoes)
    edicao_video.exemplo_editor_2("exemplo.mp4")
    assert recebidas == [fala]
    # Com o reconhecimento de voz, o exemplo também leva as legendas no tempo do áudio.
    recebidas.clear()
    monkeypatch.setattr(edicao_video.videos, "palavras_faladas",
                        lambda caminho: [(1.5, 1.8, "Olha"), (1.8, 2.0, "só"), (2.0, 2.3, "esse"), (2.3, 2.9, "vestido")])
    inserir("DELETE FROM configuracoes")
    edicao_video.exemplo_editor_2("exemplo.mp4")
    assert [legenda[:3] for legenda in recebidas[0]] == [(1.5, 3.2, "Olha só esse vestido")]


def test_foto_da_capa_sem_as_letras_do_anuncio(monkeypatch):
    # Pedido do Rafael (06/11, P160 2): na foto da capa não pode ter letra nenhuma, de outra língua
    # nem em português, para não se misturar com a frase da faixa. Com as letras numa beirada,
    # fora do produto, a capa usa o pedaço da foto sem elas.
    import io

    import api_gemini
    from PIL import Image
    respostas, pedidos = [], []

    async def ia(prompt, imagens=None):
        pedidos.append((prompt, [tipo for _dados, tipo in imagens or []]))
        return respostas.pop(0)
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", ia)
    foto = _foto_jpg()
    respostas.append('{"letras": true, "sobre_o_produto": false, "caixa": [150, 0, 1000, 1000]}')
    cortada, resultado = edicao_video.foto_sem_letras(foto)
    assert resultado == edicao_video.LETRAS_CORTADAS
    assert Image.open(io.BytesIO(cortada)).size == (800, 680)
    assert pedidos == [(edicao_video.PROMPT_DAS_LETRAS_DA_FOTO, ["image/jpeg"])]
    # Sem letras, com as letras em cima do produto (aí a capa procura um quadro do vídeo, P164 1:
    # foto_para_a_capa), com a IA sem resposta ou com a caixa que não serve (pequena demais, a foto
    # toda ou fora do formato), a foto vai como está.
    for resposta, esperado in (
            ('{"letras": false}', edicao_video.SEM_LETRAS),
            ('```json\n{"letras": true, "sobre_o_produto": true, "caixa": [0, 0, 500, 500]}\n```',
             edicao_video.LETRAS_NO_PRODUTO),
            (None, edicao_video.SEM_RESPOSTA_DAS_LETRAS), ("sem json", edicao_video.SEM_RESPOSTA_DAS_LETRAS),
            ('{"letras": true, "sobre_o_produto": false, "caixa": [0, 0, 300, 300]}', edicao_video.CAIXA_QUE_NAO_SERVE),
            ('{"letras": true, "sobre_o_produto": false, "caixa": [0, 0, 1000, 1000]}', edicao_video.CAIXA_QUE_NAO_SERVE),
            ('{"letras": true, "sobre_o_produto": false, "caixa": "alto"}', edicao_video.CAIXA_QUE_NAO_SERVE)):
        respostas.append(resposta)
        assert edicao_video.foto_sem_letras(foto) == (foto, esperado), resposta
    assert edicao_video.foto_sem_letras(b"nao e imagem") == (b"nao e imagem", edicao_video.SEM_RESPOSTA_DAS_LETRAS)


def test_capa_que_vai_ao_ar_usa_a_foto_sem_as_letras_e_anota_no_registro(monkeypatch, tmp_path):
    # A capa da grade e a do vídeo aberto saem da foto sem as letras (P160 2); a miniatura e o resto
    # do vídeo continuam com a foto do anúncio. O registro diz o que houve com as letras, para o
    # checkup contar.
    import io

    from PIL import Image
    _versoes_de_mentira(monkeypatch)
    _textos_da_tela(monkeypatch, {"nome": "Bolsa de Palha", "vantagem": "Leve e resistente", "capa": "Leve e forte",
                                  "lugar": "alto"})
    sem_letras = io.BytesIO()
    Image.new("RGB", (800, 680), (30, 90, 200)).save(sem_letras, "PNG")
    pedidas = []
    monkeypatch.setattr(edicao_video, "foto_sem_letras",
                        lambda foto: pedidas.append(foto) or (sem_letras.getvalue(), edicao_video.LETRAS_CORTADAS))
    aberturas, fotos = [], []

    def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outras_fotos=(),
               rotulo_de_ia=False, cor=None):
        aberturas.append(capa)
        fotos.append(foto)
        return ""
    monkeypatch.setattr(edicao_video, "editar", editar)
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DA_CAPA: True})
    edicao_video.editar_para_postar("v.mp4", _foto_jpg(), str(tmp_path / "r.mp4"), "Bolsa")
    assert pedidas == [_foto_jpg()] and fotos == [_foto_jpg()]
    assert aberturas[-1] == (edicao_video.capa_com_chamada(sem_letras.getvalue(), "Leve e forte"),
                             edicao_video.capa_com_chamada(sem_letras.getvalue(), "Leve e forte", no_video=True))
    linhas = edicao_video.registro_processos.sequencia("shopee_video", edicao_video.PROCESSO_DAS_LETRAS_DA_FOTO,
                                                       "2000-01-01 00:00:00")
    assert [r[2] for r in linhas] == [edicao_video.LETRAS_CORTADAS]
    # Desligada, a capa não sai e a IA nem olha a foto.
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DA_CAPA: False})
    edicao_video.editar_para_postar("v.mp4", _foto_jpg(), str(tmp_path / "r.mp4"), "Bolsa")
    assert len(pedidas) == 1 and aberturas[-1] is None


# --- A cor de cada vídeo (P159 2) ---

def test_cada_cor_do_produto_tem_um_tom_e_a_letra_que_contrasta():
    # Escolha do Rafael (06/11, P159 2): a cor principal do produto no lugar do laranja e do preto,
    # com a letra branca ou preta, a de mais contraste. O vermelho (a cor da chamada final), o de
    # várias cores e o sem a cor da IA ficam com as cores de sempre.
    assert edicao_video.cor_do_produto("Azul") == edicao_video.CORES_DO_PRODUTO["azul"]
    assert edicao_video.cor_do_produto(" azul-claro ") == edicao_video.CORES_DO_PRODUTO["azul-claro"]
    for nome in ("vermelho", "colorido", "", None, "fúcsia"):
        assert edicao_video.cor_do_produto(nome) is None, nome
    branca, preta = edicao_video.LETRA_BRANCA, edicao_video.LETRA_PRETA
    # As cores de sempre continuam com a letra branca.
    for cor in (edicao_video.LARANJA_DA_SHOPEE, edicao_video.FUNDO_DOS_TEXTOS, edicao_video.FUNDO_DA_CHAMADA):
        assert edicao_video.letra_que_contrasta(cor) == branca
    for nome, letra in (("preto", branca), ("azul", branca), ("verde", branca), ("rosa", branca),
                        ("amarelo", preta), ("branco", preta), ("bege", preta)):
        assert edicao_video.letra_que_contrasta(edicao_video.CORES_DO_PRODUTO[nome]) == letra, nome
    # A IA escolhe da lista, pelo nome, nos dois pedidos; a resposta fora dela vale como sem a cor.
    assert edicao_video._nome_lugar_e_falas({"cor": "Amarelo"})["cor"] == "amarelo"
    assert edicao_video._nome_lugar_e_falas({"cor": "vermelho"})["cor"] == "vermelho"
    assert "cor" not in edicao_video._nome_lugar_e_falas({"cor": "fúcsia"})
    for prompt in (edicao_video.PROMPT_DOS_TEXTOS, edicao_video.PROMPT_DAS_VERSOES):
        assert '"cor"' in prompt and all(nome in prompt for nome in edicao_video.CORES_DO_PRODUTO)


def test_capa_com_a_cor_do_produto_no_fio_e_na_faixa_com_a_letra_que_contrasta():
    import io

    from PIL import Image
    faixa, fio = edicao_video.lugar_da_foto()[3], edicao_video.FIO_DA_CAPA_NA_GRADE
    topo = edicao_video.GRADE_NO_CELULAR[0] + fio
    for nome, letra_branca in (("azul", True), ("amarelo", False), ("branco", False)):
        cor = edicao_video.CORES_DO_PRODUTO[nome]
        capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(_foto_jpg(), "Organize sua cozinha",
                                                                   cor=cor))).convert("RGB")
        for ponto in [(360, 0), (0, topo - fio), (719, topo - 1), (0, faixa), (719, faixa + 5)]:
            assert _cor_de(capa, ponto, cor), (nome, ponto)
        # Na grade, a faixa desce até o fim do quadro na mesma cor, também nas claras, com o número
        # de visualizações por cima dela (P171, que respondeu a P170).
        assert _cor_de(capa, (3, 1279), cor) and _cor_de(capa, (360, 1279), cor)
        assert all(_cor_de(capa, (x, y), cor) for x in range(edicao_video.NUMERO_DA_GRADE[0],
                                                            edicao_video.FIM_DO_NUMERO, 6)
                   for y in range(edicao_video.NUMERO_DA_GRADE[1], edicao_video.NUMERO_DA_GRADE[3], 6)), nome
        pontos = [capa.getpixel((x, y)) for x in range(0, 720, 2) for y in range(faixa, 1280, 2)]
        brancos = sum(1 for p in pontos if min(p) > 250)
        pretos = sum(1 for p in pontos if max(p) < 50)
        assert (brancos > 50 and pretos == 0) if letra_branca else (pretos > 50 and brancos == 0), nome


def test_caixa_do_nome_e_moldura_da_miniatura_na_cor_do_produto():
    import io

    from PIL import Image
    azul, amarelo = edicao_video.CORES_DO_PRODUTO["azul"], edicao_video.CORES_DO_PRODUTO["amarelo"]
    assert edicao_video.caixa_dos_textos() == edicao_video.FUNDO_DOS_TEXTOS
    assert edicao_video.caixa_dos_textos(azul) == azul + (edicao_video.ALFA_DA_CAIXA_DA_COR,)
    import numpy
    caixa = Image.open(io.BytesIO(edicao_video.letreiro("Copo Térmico", edicao_video.caixa_dos_textos(amarelo))))
    pontos = numpy.asarray(caixa.convert("RGBA")).reshape(-1, 4)
    pontos = pontos[pontos[:, 3] > 200, :3]
    assert (pontos.max(axis=1) < 50).any() and not (pontos.min(axis=1) > 220).any()
    largura = edicao_video.LARGURA_DA_MINIATURA
    miniatura = Image.open(io.BytesIO(edicao_video.miniatura_com_moldura(_foto_jpg(), cor=azul))).convert("RGB")
    assert _cor_de(miniatura, (largura // 2, 2), azul)
    assert _cor_de(miniatura, (largura // 2, largura // 2), (200, 120, 40))


def test_video_que_vai_ao_ar_leva_a_cor_do_produto_e_o_registro_conta(monkeypatch, tmp_path):
    # A cor que a IA disse vai na capa da grade e na do vídeo aberto, no Editor 2 (a caixa do nome
    # e da vantagem e a moldura da miniatura) e no rascunho do robô (anotar). O produto vermelho e o
    # sem a cor ficam com as cores de sempre.
    _versoes_de_mentira(monkeypatch)
    textos = {"nome": "Bolsa de Palha", "vantagem": "Leve e resistente", "capa": "Bolsa leve e forte",
              "lugar": "alto", "cor": "azul"}
    monkeypatch.setattr(edicao_video, "foto_sem_letras", lambda foto: (foto, edicao_video.SEM_LETRAS))
    capas, editores = [], []
    monkeypatch.setattr(edicao_video, "capa_com_chamada",
                        lambda foto, frase, no_video=False, cor=None: capas.append(cor) or b"capa")

    def editar_2(video, foto, destino, nome="", vantagem="", chamada="", lugar=None, avisos=False, musica=None,
                 capa=None, miniatura=True, outras_fotos=(), legendas=(), rotulo_de_ia=False, cor=None):
        editores.append(cor)
        return "", {"textos": [nome], "legendas": 0}
    monkeypatch.setattr(edicao_video, "editar_2", editar_2)
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DA_CAPA: True})
    azul = edicao_video.CORES_DO_PRODUTO["azul"]
    for cor, esperada, nome in (("azul", azul, "azul"), ("vermelho", None, ""), (None, None, "")):
        _textos_da_tela(monkeypatch, {**textos, "cor": cor} if cor else {k: v for k, v in textos.items() if k != "cor"})
        capas.clear()
        editores.clear()
        anotado = {}
        edicao_video.editar_para_postar("v.mp4", _foto_jpg(), str(tmp_path / "r.mp4"), "Bolsa", anotar=anotado)
        assert (capas, editores, anotado) == ([esperada, esperada], [esperada], {"cor": nome}), cor
    linhas = edicao_video.registro_processos.sequencia("shopee_video", edicao_video.PROCESSO_DA_COR,
                                                       "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in linhas] == [("azul", ""), (edicao_video.COM_AS_CORES_DE_SEMPRE, "vermelho"),
                                              (edicao_video.COM_AS_CORES_DE_SEMPRE, "a IA não disse a cor")]


def test_faixa_da_capa_na_cor_do_produto_e_achada_no_print():
    # O post confere a faixa da capa na cor que o rascunho guardou (marcar_o_post): azul com a letra
    # branca, amarelo com a preta e o grafite do preto, no fundo preto da capa.
    import io

    from PIL import Image
    caixa = (100, 300, 454, 772)

    def grade(capa_png):
        tela = Image.new("RGB", (1080, 2400), (240, 240, 240))
        esquerda, direita = edicao_video.LADOS_NA_GRADE
        cima, baixo = edicao_video.VISIVEL_NA_GRADE
        capa = Image.open(io.BytesIO(capa_png)).convert("RGB").crop((esquerda, cima, direita, baixo))
        tela.paste(capa.resize((caixa[2] - caixa[0], caixa[3] - caixa[1])), caixa[:2])
        return tela

    cima = edicao_video.lugar_da_foto()[3]
    for nome in ("azul", "amarelo", "preto", "branco"):
        cor = edicao_video.CORES_DO_PRODUTO[nome]
        png = edicao_video.capa_com_chamada(_foto_jpg(), "Organize sua cozinha", cor=cor)
        capa = Image.open(io.BytesIO(png)).convert("RGB")
        assert edicao_video.faixa_laranja(capa, cor=cor) == (cima, edicao_video.TELA[1], 0, edicao_video.TELA[0]), nome
        # Pelo laranja de sempre, ela não é achada.
        assert edicao_video.faixa_laranja(capa) is None, nome
        assert edicao_video.faixa_nos_lados(grade(png), caixa, cor) is True, nome
        no_video = edicao_video.capa_com_chamada(_foto_jpg(), "Organize sua cozinha", no_video=True, cor=cor)
        assert edicao_video.faixa_nos_lados(grade(no_video), caixa, cor) is False, nome


def test_frase_do_video_aberto_acaba_antes_dos_icones_do_app():
    # Escolha do Rafael (06/11, P165 1): no vídeo aberto, o coração e os ícones da direita do app
    # ficavam por cima do fim da frase; ela acaba antes deles, e a faixa continua de um lado ao outro.
    # A capa da grade, sem os ícones, vai até a beirada da grade, no meio do retângulo à direita do
    # número de visualizações (vídeos de 07/11, 01:04 e 01:31).
    import io

    from PIL import Image
    frase = "Almofada respirável"
    pe, faixa = edicao_video.PE_DA_FAIXA_NO_VIDEO, edicao_video.FAIXA_DA_CHAMADA
    esquerda, direita = edicao_video.VISIVEL_NO_APP
    capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(_foto_jpg(), frase, no_video=True))).convert("RGB")
    letras = [x for x in range(esquerda, direita) for y in range(pe - faixa, pe, 2) if min(capa.getpixel((x, y))) > 200]
    assert letras and max(letras) < edicao_video.ICONES_NO_VIDEO_ABERTO - edicao_video.MARGEM_DA_FAIXA + 3
    assert _cor_de(capa, (direita - 2, pe - 3), edicao_video.LARANJA_DA_SHOPEE)
    grade = Image.open(io.BytesIO(edicao_video.capa_com_chamada(_foto_jpg(), frase))).convert("RGB")
    cima = edicao_video.lugar_da_foto()[3]
    letras = [x for x in range(0, 720) for y in range(cima, 1280, 2) if min(grade.getpixel((x, y))) > 200]
    x1, _cima, x2, _baixo = edicao_video.lugar_das_letras_na_grade()
    assert abs((min(letras) + max(letras)) / 2 - (x1 + x2 - 1) / 2) <= 3 and max(letras) > edicao_video.ICONES_NO_VIDEO_ABERTO


def _quadro_jpg(largura=720, altura=1280):
    """Um quadro do vídeo de mentira: o produto (um quadrado azul) no meio, num fundo cinza."""
    import io

    from PIL import Image, ImageDraw
    imagem = Image.new("RGB", (largura, altura), (90, 90, 90))
    ImageDraw.Draw(imagem).rectangle((160, 400, 560, 800), fill=(30, 90, 210))
    saida = io.BytesIO()
    imagem.save(saida, "JPEG", quality=95)
    return saida.getvalue()


def test_com_as_letras_em_cima_do_produto_a_capa_usa_um_quadro_do_video(monkeypatch):
    # Escolha do Rafael (06/11, P164 1): com as letras em cima do produto, o corte não as tira; a IA
    # escolhe no vídeo um momento com o produto inteiro e sem letras, e a capa usa esse quadro,
    # recortado no produto e conferido sem letras. Sem um momento assim, vai a foto do anúncio.
    import io

    from PIL import Image
    pedidos, conferidas = [], []
    respostas = [{"momento": 2.5, "caixa": [250, 150, 700, 850]}]
    monkeypatch.setattr(edicao_video, "_resposta_da_ia", lambda video, prompt: pedidos.append((video, prompt))
                        or respostas.pop(0))
    monkeypatch.setattr(edicao_video.videos, "quadro_em", lambda video, segundos: _quadro_jpg())
    letras_do_quadro = [edicao_video.SEM_LETRAS]
    monkeypatch.setattr(edicao_video, "foto_sem_letras",
                        lambda foto: conferidas.append(foto) or (foto, letras_do_quadro.pop(0)))
    quadro, motivo = edicao_video.quadro_sem_letras("v.mp4", "Almofada de Gel")
    assert motivo == edicao_video.QUADRO_DO_VIDEO and quadro == conferidas[0]
    assert Image.open(io.BytesIO(quadro)).size == (504, 576)          # a caixa, em milésimos do quadro
    assert pedidos == [("v.mp4", edicao_video.PROMPT_DO_QUADRO_DA_CAPA.format(nome="Almofada de Gel"))]
    # Sem um momento assim, sem o quadro, ou com letras também no quadro: não entra.
    for resposta, quadro_em, letras, esperado in (
            ({"momento": None}, _quadro_jpg(), None, edicao_video.SEM_MOMENTO_SEM_LETRAS),
            ({}, _quadro_jpg(), None, edicao_video.SEM_MOMENTO_SEM_LETRAS),
            ({"momento": 1, "caixa": [0, 0, 100, 100]}, _quadro_jpg(), None, edicao_video.SEM_MOMENTO_SEM_LETRAS),
            ({"momento": 1, "caixa": [0, 0, 1000, 1000]}, None, None, edicao_video.QUADRO_QUE_NAO_SAIU),
            ({"momento": 1, "caixa": [0, 0, 1000, 1000]}, _quadro_jpg(), edicao_video.LETRAS_NO_PRODUTO,
             edicao_video.QUADRO_COM_LETRAS)):
        respostas.append(resposta)
        monkeypatch.setattr(edicao_video.videos, "quadro_em", lambda video, segundos, q=quadro_em: q)
        letras_do_quadro[:] = [letras] if letras else []
        assert edicao_video.quadro_sem_letras("v.mp4", "Almofada") == (None, esperado), resposta
    # A foto da capa: a do anúncio sem letras ou cortada; com as letras em cima do produto, o quadro.
    monkeypatch.setattr(edicao_video, "foto_sem_letras", lambda foto: (b"cortada", edicao_video.LETRAS_CORTADAS))
    assert edicao_video.foto_para_a_capa(b"foto", "v.mp4") == (b"cortada", edicao_video.LETRAS_CORTADAS, "")
    monkeypatch.setattr(edicao_video, "foto_sem_letras", lambda foto: (foto, edicao_video.LETRAS_NO_PRODUTO))
    monkeypatch.setattr(edicao_video, "quadro_sem_letras", lambda video, nome="": (b"quadro", edicao_video.QUADRO_DO_VIDEO))
    assert edicao_video.foto_para_a_capa(b"foto", "v.mp4") == (b"quadro", edicao_video.QUADRO_DO_VIDEO, "")
    monkeypatch.setattr(edicao_video, "quadro_sem_letras",
                        lambda video, nome="": (None, edicao_video.QUADRO_COM_LETRAS))
    assert edicao_video.foto_para_a_capa(b"foto", "v.mp4") == (b"foto", edicao_video.LETRAS_NO_PRODUTO,
                                                               edicao_video.QUADRO_COM_LETRAS)


def test_capa_que_vai_ao_ar_com_o_quadro_do_video_e_o_registro(monkeypatch, tmp_path):
    # O vídeo que vai ao ar abre com a capa feita do quadro do vídeo, e o registro diz "quadro do
    # vídeo"; sem o quadro, a foto do anúncio e o porquê.
    _versoes_de_mentira(monkeypatch)
    _textos_da_tela(monkeypatch, {"nome": "Bolsa de Palha", "vantagem": "Leve e resistente", "capa": "Bolsa leve",
                                  "lugar": "alto"})
    monkeypatch.setattr(edicao_video, "foto_sem_letras", lambda foto: (foto, edicao_video.LETRAS_NO_PRODUTO))
    quadros = [(_quadro_jpg(), edicao_video.QUADRO_DO_VIDEO), (None, edicao_video.SEM_MOMENTO_SEM_LETRAS)]
    monkeypatch.setattr(edicao_video, "quadro_sem_letras", lambda video, nome="": quadros.pop(0))
    capas = []
    monkeypatch.setattr(edicao_video, "capa_com_chamada",
                        lambda foto, frase, no_video=False, cor=None: capas.append(foto) or b"capa")
    monkeypatch.setattr(edicao_video, "editar_2", lambda *a, **k: ("", {"textos": ["Bolsa"], "legendas": 0}))
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DA_CAPA: True})
    edicao_video.editar_para_postar("v.mp4", _foto_jpg(), str(tmp_path / "r.mp4"), "Bolsa")
    edicao_video.editar_para_postar("v.mp4", _foto_jpg(), str(tmp_path / "r.mp4"), "Bolsa")
    assert capas == [_quadro_jpg(), _quadro_jpg(), _foto_jpg(), _foto_jpg()]
    linhas = edicao_video.registro_processos.sequencia("shopee_video", edicao_video.PROCESSO_DAS_LETRAS_DA_FOTO,
                                                       "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in linhas] == [(edicao_video.QUADRO_DO_VIDEO, ""),
                                              (edicao_video.LETRAS_NO_PRODUTO, edicao_video.SEM_MOMENTO_SEM_LETRAS)]

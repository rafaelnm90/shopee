"""edicao_video e videos.com_foto_e_miniatura: a foto do produto no começo, a miniatura no canto e a seta do Rafael, com o ffmpeg de mentira (e de verdade, quando a máquina tem)."""
import io
import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest

import db
import edicao_video
import videos
from conftest import consultar, inserir


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
    assert f"[3:v]loop=loop=-1:size=25:start=0,{videos.POR_CIMA}[seta]" in filtro
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
    assert (f"[5:v]{videos.POR_CIMA}[moldura];[semmoldura][moldura]overlay=0:0:shortest=1"
            f":enable='gte(t,{espera:.3f})'[comfoto]") in filtro
    assert [ffmpeg[i + 1] for i, parte in enumerate(ffmpeg) if parte == "-i"][3] == edicao_video.SETA
    assert f"[3:v]loop=loop=-1:size=25:start=0,{videos.POR_CIMA}[seta]" in filtro and "[4:a][som]concat=n=2:v=0:a=1[a]" in filtro


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
    # Na cor escolhida no painel (P192 1), no mesmo lugar.
    azul = edicao_video.CORES_DO_DESTAQUE["azul"]
    na_cor = Image.open(io.BytesIO(edicao_video.moldura_do_cartao(cor=azul)))
    assert na_cor.getchannel("A").getbbox() == caixa
    pixel = na_cor.getpixel((x1 - folga - grossura // 2, meio_y))
    assert pixel[3] > 200 and sum(abs(a - b) for a, b in zip(pixel[:3], azul)) < 30


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
               rotulo_de_ia=False, cor=None, escolhas=None):
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
    monkeypatch.setattr(edicao_video, "textos_das_versoes", lambda video, nome, *_: {
        "nome": "Copo Térmico", "vantagem": "Gelado o dia todo", "chamada": "Toque no copo aqui embaixo",
        "versoes": versoes, "falas": [], "lugar": "meio"})
    pedidos = []

    def editar_1_e_versoes(video, foto, destino, versoes_da_ia=(), falas=None, miniatura=True, escolhas=None):
        pedidos.append((1, video, list(versoes_da_ia), falas, miniatura))
        return "", {"versoes": []}

    def editar_2_e_versoes(video, foto, destino, nome="", vantagem="", versoes_da_ia=(), chamada="", falas=None,
                           lugar=None, miniatura=True, legendas=(), cor=None, escolhas=None, lugares=None,
                           por_cima=()):
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
    monkeypatch.setattr(edicao_video, "textos_das_versoes", lambda video, nome, *_: {
        "nome": "Presilha", "vantagem": "Firme", "versoes": versoes, "falas": [], "lugar": "alto",
        "texto_no_video": True})
    _, _, resumo = edicao_video.exemplo_editor_2("exemplo.mp4")
    assert pedidos[-1][-2] == edicao_video.SEM_LUGAR and resumo["texto_no_video"]
    # Escolha do Rafael (29/10, P81): o criador pôs coisa no canto da nossa miniatura, e os dois
    # exemplos vão sem ela, como o vídeo que vai ao ar; as nossas legendas continuam (P82).
    monkeypatch.setattr(edicao_video, "textos_das_versoes", lambda video, nome, *_: {
        "nome": "Cortina", "vantagem": "Tecido com relevo", "versoes": versoes, "falas": [], "lugar": "alto",
        "canto_ocupado": True})
    _, _, resumo = edicao_video.exemplo_editor_1("exemplo.mp4")
    assert pedidos[-1][0] == 1 and pedidos[-1][-1] == 0 and resumo["miniatura"] == 0
    _, _, resumo = edicao_video.exemplo_editor_2("exemplo.mp4")
    assert pedidos[-1][0] == 2 and pedidos[-1][-1] == 0 and pedidos[-1][-2] == "alto"
    assert resumo["miniatura"] == 0
    # Escolha do Rafael (29/10, P97): com a coisa dele logo abaixo do canto, os dois exemplos levam
    # a miniatura menor, como o vídeo que vai ao ar.
    monkeypatch.setattr(edicao_video, "textos_das_versoes", lambda video, nome, *_: {
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
                               outras_fotos=(), rotulo_de_ia=False, cor=None, escolhas=None: "")
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
               rotulo_de_ia=False, cor=None, escolhas=None):
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
    monkeypatch.setattr(edicao_video, "textos_da_tela", lambda video, nome, *_: pedidos.append(nome) or dict(textos))
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
               outras_fotos=(), rotulo_de_ia=False, cor=None, escolhas=None):
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



def test_legendas_seguidas_nao_ficam_juntas_no_quadro_da_troca(tmp_path):
    # Vídeo do Rafael das 14:47 de 10/11: na troca de uma legenda da fala para a seguinte, um quadro
    # mostrava as duas juntas, uma por cima da outra ("a priduradouroção"). A legenda acaba quando a
    # seguinte começa (letreiros_da_fala): no quadro desse instante, só a seguinte fica na tela.
    if not shutil.which("ffmpeg"):
        return
    import io

    from PIL import Image

    def quadrado(cor):
        saida = io.BytesIO()
        Image.new("RGBA", (60, 60), cor + (255,)).save(saida, "PNG")
        return saida.getvalue()
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:size=360x640:rate=30:duration=2",
                    str(video)], check=True)
    destino = tmp_path / "r.mp4"
    letreiros = [(quadrado((230, 20, 20)), 0.0, 1.0, 100, 100), (quadrado((20, 20, 230)), 1.0, 2.0, 300, 100)]
    assert edicao_video.videos.com_cortes_e_ritmo(str(video), [(0.0, 2.0, 1.0)], str(destino), letreiros) == ""

    def quadro(numero):
        saida = tmp_path / f"q{numero}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(destino), "-vf", f"select=eq(n\\,{numero})",
                        "-frames:v", "1", str(saida)], check=True)
        with Image.open(saida) as imagem:
            return imagem.convert("RGB")
    antes, troca = quadro(29), quadro(30)                 # 30 quadros por segundo: o 30 é o de 1,0 s
    assert antes.getpixel((130, 130))[0] > 180 and antes.getpixel((330, 130))[2] < 180
    assert troca.getpixel((130, 130))[0] < 180 and troca.getpixel((330, 130))[2] > 180

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


def test_capa_da_grade_com_a_frase_em_cima_e_so_o_fio_fino_embaixo():
    # Print da grade de 09/11: a frase no meio da faixa de baixo se misturava com o número de
    # visualizações ("▷ 9" encostado em "com rodinhas"). Escolha do Rafael (10/11, P188 2, a "3b"): a
    # frase vai numa faixa no alto do quadro, à esquerda da sacolinha, longe do número; a foto tampa o
    # que a grade mostra abaixo dela (P168 e P169 1), sem nada no preto do fundo (vídeo das 01:04 de
    # 07/11). Vídeo do Rafael das 11:54 de 10/11 (P196 1): embaixo, em vez da faixa grossa, só um fio
    # fino, como no vídeo aberto, e o número fica em cima da foto, como nos outros posts.
    capa = _capa("Organize sua cozinha")
    assert capa.size == edicao_video.TELA
    x1, cima, x2, baixo = edicao_video.lugar_da_foto()
    alto, pe_da_grade = edicao_video.GRADE_NO_CELULAR
    assert (x1, cima, x2, baixo) == (0, edicao_video.PE_DA_FAIXA_DE_CIMA, 720, edicao_video.PE_DA_FOTO_NA_GRADE)
    assert alto < cima < baixo < pe_da_grade and pe_da_grade - baixo == edicao_video.FIO_NA_GRADE == 16
    # A foto tampa o lugar todo, de uma beirada à outra.
    assert capa.crop((0, cima, 720, baixo)).tobytes() == edicao_video._foto_da_grade(_foto_jpg()).tobytes()
    # A faixa de cima vem do alto do quadro até a foto, e o fio de baixo vai da foto até o fim do
    # quadro, de uma beirada à outra; nada no preto do fundo.
    for ponto in [(0, 0), (719, 0), (0, cima - 1), (719, cima - 1), (360, alto - 30), (0, baixo), (719, baixo),
                  (360, baixo + 2), (3, pe_da_grade - 1), (716, 1279)]:
        assert _cor_de(capa, ponto, edicao_video.LARANJA_DA_SHOPEE), ponto
    assert not any(max(capa.getpixel((x, y))) < 20 for x in range(0, 720, 3) for y in range(0, 1280, 3))
    # As letras brancas só no retângulo da frase, na faixa de cima, no meio dele: à esquerda da
    # sacolinha e longe do número de visualizações, que fica embaixo, em cima da foto.
    esquerda, cima_das_letras, direita, pe_das_letras = edicao_video.lugar_das_letras_na_grade()
    sx1, _sy1, _sx2, sy2 = edicao_video.SACOLINHA_DA_GRADE
    _nx1, ny1, _nx2, ny2 = edicao_video.NUMERO_DA_GRADE
    assert alto < cima_das_letras and pe_das_letras < cima and direita < sx1 and sy2 < cima
    assert cima < ny1 and ny2 < baixo
    letras = [(x, y) for x in range(720) for y in range(0, cima) if min(capa.getpixel((x, y))) > 200]
    assert letras and _claros(capa, (0, cima, 720, 1280)) == 0
    xs, ys = [x for x, _y in letras], [y for _x, y in letras]
    assert esquerda - 1 <= min(xs) and max(xs) <= direita and cima_das_letras - 1 <= min(ys) and max(ys) <= pe_das_letras
    assert abs((min(xs) + max(xs)) / 2 - (esquerda + direita - 1) / 2) <= 3
    assert abs((min(ys) + max(ys)) / 2 - (cima_das_letras + pe_das_letras - 1) / 2) <= 3
    # Em duas linhas, na maior letra que cabe, até o teto (print de 07/11, 02:49); com a frase no meio
    # (P198 1), a de 20 letras fica um pouco menor que o teto, e a curta continua nele.
    fonte, linhas = edicao_video._quebra_da_grade("Organize sua cozinha", _fonte_da_capa(), direita - esquerda,
                                                  pe_das_letras - cima_das_letras)
    assert len(linhas) == 2 and 76 <= fonte.size < edicao_video.LETRAS_NA_GRADE[0]
    fonte, linhas = edicao_video._quebra_da_grade("Banho de verniz", _fonte_da_capa(), direita - esquerda,
                                                  pe_das_letras - cima_das_letras)
    assert len(linhas) == 2 and fonte.size == edicao_video.LETRAS_NA_GRADE[0]


def test_capa_da_grade_so_com_o_fio_fino_embaixo_e_o_numero_em_cima_da_foto():
    # Vídeo do Rafael das 11:54 de 10/11: "tanto a capa qnto o vídeo tivesse esse padrão com apenas um
    # fio pequeno embaixo, não pode destoar tanto assim não"; com as imagens das opções no print do
    # perfil, "P196 1". No pedaço que a grade mostra, a cor da faixa embaixo é só o fio de 16 px; no
    # lugar do número de visualizações, a foto, como nos outros posts; e a foto quadrada tampa o lugar
    # perdendo só uns 1% de cada lado, sem esticar.
    import io

    from PIL import Image
    alto, _pe_da_grade = edicao_video.GRADE_NO_CELULAR
    capa_png = edicao_video.capa_com_chamada(_foto_jpg(), "Organize sua cozinha")
    grade = Image.open(io.BytesIO(edicao_video.recorte_da_grade(capa_png))).convert("RGB")
    laranja = edicao_video.LARANJA_DA_SHOPEE
    linhas_na_cor = [y for y in range(edicao_video.PE_DA_FAIXA_DE_CIMA - alto, grade.height)
                     if all(_cor_de(grade, (x, y), laranja) for x in (0, 360, 719))]
    assert linhas_na_cor == list(range(grade.height - 16, grade.height))
    nx1, ny1, nx2, ny2 = edicao_video.NUMERO_DA_GRADE
    assert all(_cor_de(grade, (x, y - alto), (200, 120, 40)) for x in range(nx1, nx2, 8) for y in range(ny1, ny2, 8))
    # A quadrada perde só uns 1% de cada lado: tampa sem esticar, com a mesma escala nos dois sentidos.
    x1, cima, x2, baixo = edicao_video.lugar_da_foto()
    escala = (baixo - cima) / 800
    assert edicao_video._foto_que_tampa(_foto_jpg(), x2 - x1, baixo - cima).size == (x2 - x1, baixo - cima)
    assert 0 < (800 * escala - (x2 - x1)) / 2 / (800 * escala) < 0.012


def test_capa_da_grade_sem_preto_com_a_faixa_e_o_fio_em_qualquer_foto():
    # Vídeo do Rafael das 01:04 de 07/11: "não é para ter nada de preto ali". Com a frase em cima
    # (P188 2), a faixa de cima vem do alto do quadro até a foto, e o fio de baixo (P196 1) vai da foto
    # até o fim do quadro, em qualquer formato de foto; a frase, em duas linhas grandes, no meio do
    # retângulo dela.
    import io

    from PIL import Image

    def foto(largura, altura):
        saida = io.BytesIO()
        Image.new("RGB", (largura, altura), (128, 128, 128)).save(saida, "PNG")
        return saida.getvalue()

    marrom = (124, 84, 56)
    _x1, cima, _x2, baixo = edicao_video.lugar_da_foto()
    for tamanho in ((800, 800), (800, 600), (600, 800), (1200, 500)):
        capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(foto(*tamanho), "Potes para biscoitos",
                                                                   cor=marrom))).convert("RGB")
        # Nada no preto do fundo, no quadro todo.
        assert not any(max(capa.getpixel((x, y))) < 30 for x in range(0, 720, 2) for y in range(0, 1280, 2)), tamanho
        # A faixa e o fio nas beiradas do quadro, e a foto entre eles.
        assert all(_cor_de(capa, (x, y), marrom) for x in (0, 719) for y in range(0, cima)), tamanho
        assert all(_cor_de(capa, (x, y), marrom) for x in (0, 360, 719) for y in range(baixo, 1280)), tamanho
        assert _cor_de(capa, (360, cima + 1), (128, 128, 128)), tamanho
        assert _cor_de(capa, (360, baixo - 2), (128, 128, 128)), tamanho
    # A frase em duas linhas grandes, no meio do retângulo dela.
    esquerda, cima_das_letras, direita, pe_das_letras = edicao_video.lugar_das_letras_na_grade()
    letras = [(x, y) for x in range(720) for y in range(0, cima) if min(capa.getpixel((x, y))) > 200]
    xs, ys = [x for x, _y in letras], [y for _x, y in letras]
    assert min(xs) >= esquerda - 1 and max(xs) <= direita and min(ys) >= cima_das_letras - 1 and max(ys) <= pe_das_letras
    linhas_com_letras = sorted(set(ys))
    vaos = [b - a for a, b in zip(linhas_com_letras, linhas_com_letras[1:]) if b - a > 1]
    assert len(vaos) == 1, "duas linhas"
    assert abs((min(xs) + max(xs)) / 2 - (esquerda + direita - 1) / 2) <= 3
    assert abs((min(ys) + max(ys)) / 2 - (cima_das_letras + pe_das_letras - 1) / 2) <= 3
    # Bem maior que a letra de uma linha só que cabia antes (até 84, P171).
    fonte, linhas = edicao_video._quebra_da_grade("Potes para biscoitos", _fonte_da_capa(), direita - esquerda,
                                                  pe_das_letras - cima_das_letras)
    assert len(linhas) == 2 and fonte.size > 84
def _fonte_da_capa():
    import os

    import matplotlib
    return os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")


def test_frase_da_grade_em_letra_harmonica_nem_enorme_nem_pequena():
    # Print do Rafael de 07/11, 02:49: "Bolsa espaçosa", em duas linhas na letra 120, enchia a faixa
    # toda ("ficou feio muito grande"); "pode reduzir um pouco o tamanho do texto para ficar mais
    # harmônico [...] Mas tbm não deixe muito pequeno". A letra vai até LETRAS_NA_GRADE, maior que a de
    # uma linha de antes (84, P171) e menor que a que enchia a faixa; na faixa de cima (P188 2), as
    # duas linhas cabem no retângulo da frase, no meio dele.
    import io

    from PIL import Image
    esquerda, cima, direita, baixo = edicao_video.lugar_das_letras_na_grade()
    fonte, linhas = edicao_video._quebra_da_grade("Bolsa espaçosa", _fonte_da_capa(), direita - esquerda, baixo - cima)
    assert linhas == ["Bolsa", "espaçosa"] and fonte.size == edicao_video.LETRAS_NA_GRADE[0]
    assert 84 < edicao_video.LETRAS_NA_GRADE[0] < 120
    capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(_foto_jpg(), "Bolsa espaçosa",
                                                               cor=(205, 93, 132)))).convert("RGB")
    ys = [y for x in range(esquerda, direita) for y in range(cima, baixo) if min(capa.getpixel((x, y))) > 200]
    altura = max(ys) - min(ys) + 1
    assert 0.8 * (baixo - cima) < altura <= baixo - cima
    assert abs((min(ys) + max(ys)) / 2 - (cima + baixo - 1) / 2) <= 3
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
    # Na capa da grade com a frase em cima (P188 2) e só o fio fino embaixo (P196 1), o lugar da foto
    # é quase quadrado: a quadrada, a maioria, tampa perdendo só uns 1% de cada lado, sem esticar; a
    # mais larga, de 7:6, estica (P169 1).
    x1, cima, x2, baixo = edicao_video.lugar_da_foto()
    lugar = (x2 - x1, baixo - cima)
    for largura, altura in ((800, 800), (1000, 1000), (790, 800), (800, 780)):
        assert edicao_video._foto_que_tampa(foto(largura, altura), *lugar).size == lugar, (largura, altura)
    for largura, altura in ((840, 726), (1000, 864)):
        assert edicao_video._foto_que_tampa(foto(largura, altura), *lugar) is None, (largura, altura)
    # O corte sai por igual dos dois lados: o meio da foto fica no meio.
    listrada = Image.new("RGB", (800, 780), (0, 0, 0))
    listrada.paste((255, 255, 255), (390, 0, 410, 780))
    saida = io.BytesIO()
    listrada.save(saida, "PNG")
    tampada = edicao_video._foto_que_tampa(saida.getvalue(), 720, 728)
    brancos = [x for x in range(720) if min(tampada.getpixel((x, 364))) > 200]
    assert abs((min(brancos) + max(brancos)) / 2 - 359.5) <= 2
def test_capa_da_grade_com_a_foto_que_nao_e_quadrada_estica_ate_15_e_o_resto_fica_desfocado():
    # P169 1 (vídeo do Rafael das 23:29 de 06/11): a foto que não é quase do formato do lugar (com o
    # fio fino embaixo, P196 1, o lugar é quase quadrado) estica só até 15% na direção em que falta e,
    # se ainda não tampar, o que faltar fica com a própria foto desfocada; nada de preto no que a grade
    # mostra, e nada da foto é cortado. O fio de baixo vai até o fim do quadro. A foto fica no meio do
    # desfocado, com ele por igual dos dois lados (P206 1, 11/11: no exemplo, a foto embaixo e o
    # desfocado só em cima).
    import io

    from PIL import Image

    def listrada(largura, altura):
        imagem = Image.new("RGB", (largura, altura), (200, 120, 40))
        for x in range(0, largura, 40):
            imagem.paste((40, 90, 200), (x, 0, x + 20, altura))
        saida = io.BytesIO()
        imagem.save(saida, "PNG")
        return saida.getvalue(), imagem

    x1, cima, x2, baixo = edicao_video.lugar_da_foto()
    alto, pe_da_grade = edicao_video.GRADE_NO_CELULAR
    largura, altura = x2 - x1, baixo - cima
    assert (x1, x2) == (0, edicao_video.TELA[0]) and alto < cima < baixo < pe_da_grade
    for tamanho in ((800, 560), (1000, 800), (600, 800)):
        foto, imagem = listrada(*tamanho)
        capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(foto, "Leve"))).convert("RGB")
        # Nada de preto no que a grade mostra.
        assert not any(max(capa.getpixel((x, y))) < 20 for x in range(0, 720, 3)
                       for y in range(alto, pe_da_grade, 3)), tamanho
        escala = min(largura / imagem.width, altura / imagem.height)
        esticada = (round(min(largura, imagem.width * escala * 1.15)), round(min(altura, imagem.height * escala * 1.15)))
        # A foto inteira, esticada no máximo 15%, no meio do lugar dela, na altura e na largura.
        x, y = (largura - esticada[0]) // 2, cima + (altura - esticada[1]) // 2
        assert capa.crop((x, y, x + esticada[0], y + esticada[1])).tobytes() == imagem.resize(esticada,
                                                                                             Image.LANCZOS).tobytes()
        assert max(esticada[0] / (imagem.width * escala), esticada[1] / (imagem.height * escala)) <= 1.15 + 0.01
        if esticada == (largura, altura):
            continue
        # O resto, a própria foto desfocada, dos dois lados dela, por igual (no máximo 1 px de diferença):
        # as listras se misturam, sem o laranja nem o azul puros.
        if esticada[0] == largura:
            fora = ((0, cima, 720, y), (0, y + esticada[1], 720, baixo))
            sobras = (y - cima, baixo - y - esticada[1])
        else:
            fora = ((0, cima, x, baixo), (x + esticada[0], cima, 720, baixo))
            sobras = (x, largura - x - esticada[0])
        assert min(sobras) > 0 and abs(sobras[0] - sobras[1]) <= 1, (tamanho, sobras)
        for x1_fora, y1_fora, x2_fora, y2_fora in fora:
            pontos = [capa.getpixel((px, py)) for px in range(x1_fora, x2_fora, 2) for py in range(y1_fora, y2_fora, 2)]
            assert pontos and not any(p in ((200, 120, 40), (40, 90, 200)) for p in pontos), tamanho
    # A foto mais larga que a quadrada, que não tampa perdendo só 7%, estica até tampar, sem desfocado
    # (no máximo 15%).
    foto, imagem = listrada(880, 800)
    assert edicao_video._foto_que_tampa(foto, largura, altura) is None
    capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(foto, "Leve"))).convert("RGB")
    assert capa.crop((0, cima, 720, baixo)).tobytes() == imagem.resize((largura, altura), Image.LANCZOS).tobytes()
    assert _cor_de(capa, (360, cima - 1), edicao_video.LARANJA_DA_SHOPEE)
    assert _cor_de(capa, (3, 1279), edicao_video.LARANJA_DA_SHOPEE)
def _listrada(largura, altura):
    """Uma foto sem branco nenhum (listras laranja e azuis), de largura x altura px."""
    from PIL import Image
    imagem = Image.new("RGB", (largura, altura), (200, 120, 40))
    for x in range(0, largura, 40):
        imagem.paste((40, 90, 200), (x, 0, x + 20, altura))
    return imagem


def _jpeg(imagem):
    saida = io.BytesIO()
    imagem.save(saida, "JPEG", quality=90)
    return saida.getvalue()


def _colada_no_branco(foto, lugar, lado=1000):
    """A foto (PIL) colada num quadrado branco de lado px, no lugar (x, y), em JPEG, como as lojas fazem."""
    from PIL import Image
    quadrado = Image.new("RGB", (lado, lado), "white")
    quadrado.paste(foto, lugar)
    return _jpeg(quadrado)


def test_foto_colada_num_quadrado_branco_perde_as_faixas_brancas_nas_capas():
    # Print do Rafael de 11/11 às 20:33 (a mesa e cadeiras): a foto deitada, colada pela loja num
    # quadrado branco, ia à capa com uma faixa branca em cima e outra embaixo. Escolha dele (P206 1 e
    # P207 1): as faixas saem antes das duas capas, também as dos lados na foto em pé, e a foto que
    # fica tampa o lugar como as outras (até 15% esticada e o resto desfocado, no meio). A foto de
    # fundo branco (o produto no meio, com o branco em volta, como o banho de verniz do print) fica
    # como está.
    from PIL import Image, ImageDraw

    com_faixas = _colada_no_branco(_listrada(1000, 680), (0, 160))
    onde, caixa = edicao_video.faixas_brancas(com_faixas)
    assert onde == edicao_video.FAIXAS_EM_CIMA_E_EMBAIXO
    assert (caixa[0], caixa[2]) == (0, 1000) and abs(caixa[1] - 160) <= 2 and abs(caixa[3] - 840) <= 2, caixa
    sem = edicao_video.sem_faixas_brancas(com_faixas)
    assert Image.open(io.BytesIO(sem)).width == 1000 and abs(Image.open(io.BytesIO(sem)).height - 680) <= 4
    # As duas capas saem da foto sem as faixas: as mesmas da foto que já veio sem elas.
    for no_video in (False, True):
        assert (edicao_video.capa_com_chamada(com_faixas, "Mesa e cadeiras", no_video=no_video)
                == edicao_video.capa_com_chamada(sem, "Mesa e cadeiras", no_video=no_video)), no_video

    def linhas_brancas(capa, x1, x2, y1, y2):
        return [y for y in range(y1, y2, 2) if all(min(capa.getpixel((x, y))) > 235 for x in range(x1, x2, 8))]
    # Na grade, nenhuma linha branca no lugar da foto (antes, as faixas iam de uma beirada à outra).
    x1, cima, x2, baixo = edicao_video.lugar_da_foto()
    grade = Image.open(io.BytesIO(edicao_video.capa_com_chamada(com_faixas, "Mesa e cadeiras"))).convert("RGB")
    assert not linhas_brancas(grade, x1, x2, cima, baixo)
    # No vídeo aberto, a foto inteira logo abaixo da faixa de cima, sem o branco em cima dela.
    esquerda, direita = edicao_video.VISIVEL_NO_APP
    aberto = Image.open(io.BytesIO(edicao_video.capa_com_chamada(com_faixas, "Mesa e cadeiras", no_video=True)))
    assert not linhas_brancas(aberto.convert("RGB"), esquerda + 4, direita - 4, cima, cima + 400)
    # A cor da faixa olha a foto como ela fica na capa: a faixa branca (o produto branco) não some mais
    # nas faixas brancas de enchimento, que saíram.
    branco = edicao_video.CORES_DO_PRODUTO["branco"]
    assert edicao_video.cor_da_faixa(com_faixas, branco) == edicao_video.cor_da_faixa(sem, branco) == branco
    # A foto em pé, colada no quadrado branco: as faixas dos lados saem (P207 1).
    em_pe = _colada_no_branco(_listrada(600, 1000), (200, 0))
    onde, caixa = edicao_video.faixas_brancas(em_pe)
    assert onde == edicao_video.FAIXAS_DOS_LADOS
    assert (caixa[1], caixa[3]) == (0, 1000) and abs(caixa[0] - 200) <= 2 and abs(caixa[2] - 800) <= 2, caixa
    # Ficam como estão: a foto de fundo branco (o produto no meio, com o branco em volta, e o produto
    # largo, de uma beirada à outra, sem borda reta), a faixa só em cima, a faixa fina (menos de 3% da
    # foto), a foto sem branco e a foto que não abre.
    fundo_branco = Image.new("RGB", (1000, 1000), "white")
    ImageDraw.Draw(fundo_branco).ellipse((300, 250, 700, 750), fill=(200, 120, 40))
    largo = Image.new("RGB", (1000, 1000), "white")
    ImageDraw.Draw(largo).ellipse((-40, 300, 1040, 700), fill=(40, 90, 200))
    for foto in (_jpeg(fundo_branco), _jpeg(largo), _colada_no_branco(_listrada(1000, 840), (0, 160)),
                 _colada_no_branco(_listrada(1000, 960), (0, 20)), _jpeg(_listrada(1000, 1000)), b"nao e imagem"):
        assert edicao_video.faixas_brancas(foto) is None
        assert edicao_video.sem_faixas_brancas(foto) is foto


def test_foto_com_uma_coluna_branca_na_beirada_tambem_perde_as_faixas_brancas():
    # A foto da loja às vezes tem uma coluna branca fina na beirada (a sobra do recorte): as tiras
    # dos lados conferidas (5% da largura) passam dela e acham a foto. Em 12/11, a constante dessas
    # tiras tinha o mesmo nome da tira da conferência da faixa na grade (0,8%), que valia por cima.
    foto = _listrada(1000, 680)
    foto.paste((255, 255, 255), (990, 0, 1000, 680))
    onde, caixa = edicao_video.faixas_brancas(_colada_no_branco(foto, (0, 160)))
    assert onde == edicao_video.FAIXAS_EM_CIMA_E_EMBAIXO and abs(caixa[1] - 160) <= 2 and abs(caixa[3] - 840) <= 2


def test_edicao_anota_as_faixas_brancas_tiradas_da_foto(monkeypatch, tmp_path):
    # O registro conta as fotos que perdem as faixas brancas antes das capas (P206 1 e P207 1), para o
    # checkup mostrar; a foto sem as faixas não anota nada.
    import api_gemini
    _versoes_de_mentira(monkeypatch)
    _textos_da_tela(monkeypatch, {"nome": "Mesa de jantar", "vantagem": "Para 4 pessoas", "capa": "Mesa e cadeiras",
                                  "lugar": "alto"})

    async def ia(prompt, imagens=None):
        return '{"letras": false}'

    async def ia_do_video(video, prompt):
        return None
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", ia)
    monkeypatch.setattr(api_gemini, "analisar_video_gemini", ia_do_video)
    monkeypatch.setattr(edicao_video, "capa_com_chamada", lambda *a, **k: b"capa")
    monkeypatch.setattr(edicao_video, "editar_2", lambda *a, **k: ("", {"textos": ["Mesa"], "legendas": 0}))
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DA_CAPA: True})
    fotos = (_colada_no_branco(_listrada(1000, 680), (0, 160)), _foto_jpg(),
             _colada_no_branco(_listrada(600, 1000), (200, 0)))
    for foto in fotos:
        edicao_video.editar_para_postar("v.mp4", foto, str(tmp_path / "r.mp4"), "Mesa", anotar={})
    linhas = edicao_video.registro_processos.sequencia("shopee_video", edicao_video.PROCESSO_DAS_FAIXAS_BRANCAS,
                                                       "2000-01-01 00:00:00")
    assert [r[2] for r in linhas] == [edicao_video.FAIXAS_EM_CIMA_E_EMBAIXO, edicao_video.FAIXAS_DOS_LADOS]


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
    # "C" e o "l" de "Caimento impecável" ficavam cortados nas pontas da faixa. A frase fica dentro do
    # que o app mostra do vídeo aberto, com a margem. Escolha do Rafael (10/11, P189 B): ela é a mesma
    # nas duas capas e fica no mesmo lugar, para não se mexer ao abrir o vídeo.
    import io

    from PIL import Image
    esquerda, direita = edicao_video.VISIVEL_NO_APP
    folga = edicao_video.MARGEM_DA_FAIXA // 2
    pe = edicao_video.PE_DA_FAIXA_DE_CIMA
    for frase in ("Caimento impecável", "Organize sua cozinha", "Acaba com a bagunça da cozinha"):
        capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(_foto_jpg(), frase, no_video=True))).convert("RGB")
        assert _claros(capa, (esquerda + folga, 0, direita - folga, pe), passo=2) > 50, frase
        assert _claros(capa, (0, 0, esquerda + folga, 1280), passo=1) == 0, frase
        assert _claros(capa, (direita - folga, 0, 720, 1280), passo=1) == 0, frase
        da_grade = _capa(frase)
        assert _claros(da_grade, (0, 0, esquerda + folga, 1280), passo=1) == 0, frase
        letras = edicao_video.lugar_das_letras_na_grade()
        assert capa.crop(letras).tobytes() == da_grade.crop(letras).tobytes(), frase
def test_capa_do_video_aberto_com_a_faixa_de_cima_e_a_foto_inteira_logo_abaixo():
    # No vídeo aberto, que corta mais dos lados que a grade (P129), o resto da abertura vai com a foto
    # inteira (P160 2). Escolha do Rafael (10/11, P189 B): a mesma faixa de cima da capa da grade,
    # com a frase parada ao abrir o vídeo, e a foto inteira logo abaixo dela, com o fio embaixo da
    # foto, acima do cartão do produto que o app põe por cima do vídeo.
    import io

    from PIL import Image
    capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(_foto_jpg(), "Organize sua cozinha",
                                                               no_video=True))).convert("RGB")
    assert capa.size == edicao_video.TELA
    esquerda, direita = edicao_video.VISIVEL_NO_APP
    assert edicao_video.lados_da_capa(True) == (esquerda, direita) and edicao_video.lados_da_capa() == (0, 720)
    x1, cima, x2, baixo = edicao_video.lugar_da_foto(True)
    fio = edicao_video.FIO_DA_CAPA
    assert (x1, cima, x2) == (esquerda, edicao_video.PE_DA_FAIXA_DE_CIMA, direita)
    assert baixo + fio < edicao_video.CARTAO_NO_VIDEO_ABERTO
    # A faixa de cima, de um lado ao outro do que o app mostra.
    for x in (esquerda, direita - 1):
        assert all(_cor_de(capa, (x, y), edicao_video.LARANJA_DA_SHOPEE) for y in range(0, cima, 7)), x
    # A foto quadrada inteira, no maior tamanho que cabe, logo abaixo da faixa e no meio da largura.
    lado = min(direita - esquerda, baixo - cima)
    inicio = esquerda + (direita - esquerda - lado) // 2
    for ponto in [(inicio, cima), (inicio + lado - 1, cima), (360, cima + lado // 2), (inicio, cima + lado - 1)]:
        assert _cor_de(capa, ponto, (200, 120, 40)), ponto
    # O fio logo abaixo do pé da foto, de um lado ao outro do que o app mostra.
    for x in (esquerda, 360, direita - 1):
        assert _cor_de(capa, (x, cima + lado), edicao_video.LARANJA_DA_SHOPEE), x
        assert _cor_de(capa, (x, cima + lado + fio - 1), edicao_video.LARANJA_DA_SHOPEE), x
    # Preto fora do que o app mostra, nos lados da foto e embaixo do fio (onde fica o cartão do produto).
    assert _pretos(capa, (0, 0, esquerda, 1280), passo=2) and _pretos(capa, (direita, 0, 720, 1280), passo=2)
    assert _pretos(capa, (esquerda, cima, inicio, cima + lado), passo=2)
    assert _pretos(capa, (0, cima + lado + fio, 720, 1280), passo=2)
    # A frase só na faixa de cima.
    assert _claros(capa, (esquerda, 0, direita, cima)) > 50 and _claros(capa, (0, cima, 720, 1280)) == 0
    # O exemplo do painel mostra o que o app mostra do vídeo aberto: a faixa de um lado ao outro.
    recorte = Image.open(io.BytesIO(edicao_video.recorte_do_video_aberto(
        edicao_video.capa_com_chamada(_foto_jpg(), "Organize sua cozinha", no_video=True)))).convert("RGB")
    assert recorte.size == (direita - esquerda, 1280)
    assert _cor_de(recorte, (0, 0), edicao_video.LARANJA_DA_SHOPEE)
    assert _cor_de(recorte, (recorte.width - 1, 0), edicao_video.LARANJA_DA_SHOPEE)
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
    # Na capa do vídeo aberto, a faixa de cima só no meio (P189 B), e a frase, à esquerda da
    # sacolinha e dos ícones do app (P165 1), fora do meio do quadro: uma letra pode cruzar bem a
    # coluna do centro. A faixa só no meio continua reconhecida pelas outras colunas do meio.
    from PIL import Image, ImageDraw
    caixa = (100, 300, 454, 772)
    tela = Image.new("RGB", (1080, 2400), (240, 240, 240))
    desenho = ImageDraw.Draw(tela)
    desenho.rectangle(caixa, fill=(0, 0, 0))
    alto, baixo = edicao_video.GRADE_NO_CELULAR
    altura = round((edicao_video.PE_DA_FAIXA_DE_CIMA - alto) * (caixa[3] - caixa[1]) / (baixo - alto))
    cima = caixa[1]
    desenho.rectangle((caixa[0] + 20, cima, caixa[2] - 20, cima + altura), fill=edicao_video.LARANJA_DA_SHOPEE)
    meio = (caixa[0] + caixa[2]) // 2
    desenho.rectangle((meio - 4, cima + altura // 4, meio + 4, cima + altura * 3 // 4), fill=(255, 255, 255))
    assert edicao_video.faixa_nos_lados(tela, caixa) is False
def test_abertura_de_verdade_tem_a_capa_da_grade_so_no_1o_quadro(tmp_path, monkeypatch):
    # Com o ffmpeg de verdade (P129) e a passagem desligada (PASSAGEM_NOS_VIDEOS): o 1º quadro, que o
    # app usa como capa da grade, tem a faixa de uma beirada à outra do vídeo; do 2º em diante, a do
    # vídeo aberto (preto onde a outra é laranja). Com a passagem, que vale nos vídeos (P178 1), o
    # teste seguinte.
    from PIL import Image
    if not shutil.which("ffmpeg"):
        return
    monkeypatch.setattr(edicao_video, "PASSAGEM_NOS_VIDEOS", False)
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

    ponto = (edicao_video.VISIVEL_NO_APP[0] // 2, (edicao_video.PE_DA_FOTO_NA_GRADE + edicao_video.TELA[1]) // 2)
    assert _cor_de(quadro(0), ponto, edicao_video.LARANJA_DA_SHOPEE)
    for numero in (1, 30, 58):
        assert max(quadro(numero).getpixel(ponto)) < 40, numero


def test_abertura_de_verdade_com_a_passagem_suave_entre_as_capas(tmp_path):
    # Escolha do Rafael (07/11, P175 1): o 1º quadro continua a capa da grade, inteira, e ela se desfaz
    # na do vídeo aberto em PASSAGEM_DA_CAPA segundos, sem o pulo de um quadro para o outro. Ele viu o
    # exemplo e a passagem vale também nos vídeos que vão ao ar (08/11, P178 1).
    from PIL import Image
    if not shutil.which("ffmpeg"):
        return
    assert edicao_video.PASSAGEM_NOS_VIDEOS
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

    # No ponto em que a capa da grade tem a cor do fio e a do vídeo aberto tem o preto do fundo.
    ponto = (edicao_video.VISIVEL_NO_APP[0] // 2, (edicao_video.PE_DA_FOTO_NA_GRADE + edicao_video.TELA[1]) // 2)
    assert _cor_de(quadro(0), ponto, edicao_video.LARANJA_DA_SHOPEE)
    vermelho = [quadro(numero).getpixel(ponto)[0] for numero in (2, 5, 8)]
    assert vermelho[0] > vermelho[1] > vermelho[2] > 40, vermelho          # a faixa vai sumindo aos poucos
    fim = round(edicao_video.PASSAGEM_DA_CAPA * 30) + 2
    for numero in (fim, 30, 58):
        assert max(quadro(numero).getpixel(ponto)) < 40, numero


def test_frase_da_capa_vai_numa_linha_a_comprida_em_duas_e_sem_frase_nao_ha_capa():
    import io

    from PIL import Image
    esquerda, cima_das_letras, direita, pe_das_letras = edicao_video.lugar_das_letras_na_grade()
    largura, altura = direita - esquerda, pe_das_letras - cima_das_letras
    # A frase de uma palavra vai numa linha só, na letra do teto.
    fonte, linhas = edicao_video._quebra_da_grade("Leve", _fonte_da_capa(), largura, altura)
    assert (fonte.size, linhas) == (edicao_video.LETRAS_NA_GRADE[0], ["Leve"])
    # A curta (até MAXIMO_DA_CAPA letras, P106) vai em duas linhas grandes (print de 07/11, 02:49); com
    # a frase no meio (P198 1), a de quase 20 letras fica um pouco menor.
    for curta in ("Organize sua cozinha", "Mochila impermeável", "Limpeza sem esforço", "Gelado o dia todo"):
        assert len(curta) <= edicao_video.MAXIMO_DA_CAPA
        fonte, linhas = edicao_video._quebra_da_grade(curta, _fonte_da_capa(), largura, altura)
        assert len(linhas) == 2 and fonte.size >= 70, curta
    # A comprida (o nome ou a vantagem, sem a curta) também cabe, em duas linhas, sem a 1ª terminar
    # numa palavra de ligação.
    assert edicao_video._quebra_da_grade("Acaba com a bagunça da cozinha", _fonte_da_capa(), largura, altura)[1] == [
        "Acaba com a bagunça", "da cozinha"]
    longa = "Organiza todos os temperos em segundos"[:edicao_video.MAXIMO_DA_VANTAGEM]
    fonte, linhas = edicao_video._quebra_da_grade(longa, _fonte_da_capa(), largura, altura)
    assert len(linhas) == 2 and fonte.size >= edicao_video.LETRAS_NA_GRADE[1]
    # A frase só muda a faixa de cima (P188 2): a foto e o fio de baixo ficam iguais.
    capa, curta = _capa(longa), _capa("Leve")
    pe = edicao_video.PE_DA_FAIXA_DE_CIMA
    abaixo = (0, pe, 720, 1280)
    assert capa.crop(abaixo).tobytes() == curta.crop(abaixo).tobytes()
    assert _claros(capa, (0, 0, 720, pe)) > 50 and _claros(capa, abaixo) == 0
    # As duas linhas da comprida no meio do retângulo da frase.
    ys = [y for x in range(esquerda, direita) for y in range(0, pe) if min(capa.getpixel((x, y))) > 200]
    assert min(ys) >= cima_das_letras - 1 and max(ys) <= pe_das_letras
    assert abs((min(ys) + max(ys)) / 2 - (cima_das_letras + pe_das_letras - 1) / 2) <= 3
    # Sem a frase ou com a foto que não abre, não há capa com chamada (vai a capa de sempre).
    assert edicao_video.capa_com_chamada(_foto_jpg(), "") is None
    assert edicao_video.capa_com_chamada(b"nao e imagem", "Leve") is None
    # O exemplo do painel mostra também o pedaço que a grade do celular do Rafael mostra, com a
    # largura toda: a foto, a faixa e o fio vão até as bordas, sem preto nenhum (P168).
    capa_png = edicao_video.capa_com_chamada(_foto_jpg(), "Leve")
    recorte = Image.open(io.BytesIO(edicao_video.recorte_da_grade(capa_png))).convert("RGB")
    alto, baixo = edicao_video.GRADE_NO_CELULAR
    assert recorte.size == (720, baixo - alto) and recorte.width * 4 == recorte.height * 3
    capa = Image.open(io.BytesIO(capa_png)).convert("RGB")
    assert recorte.tobytes() == capa.crop((0, alto, 720, baixo)).tobytes()
    fio = edicao_video.PE_DA_FOTO_NA_GRADE - alto
    for x in (0, recorte.width - 1):
        assert _cor_de(recorte, (x, 0), edicao_video.LARANJA_DA_SHOPEE), x
        assert _cor_de(recorte, (x, pe - alto + 2), (200, 120, 40)), x
        assert _cor_de(recorte, (x, fio - 3), (200, 120, 40)), x
        assert _cor_de(recorte, (x, fio + 2), edicao_video.LARANJA_DA_SHOPEE), x
        assert _cor_de(recorte, (x, recorte.height - 1), edicao_video.LARANJA_DA_SHOPEE), x
def test_capa_com_chamada_so_vai_ao_ar_ligada_e_nunca_na_bebida_alcoolica(monkeypatch, tmp_path):
    _versoes_de_mentira(monkeypatch)
    _textos_da_tela(monkeypatch, {"nome": "Bolsa de Palha", "vantagem": "Leve e resistente", "lugar": "alto"})
    capas = []

    def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outras_fotos=(),
               rotulo_de_ia=False, cor=None, escolhas=None):
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
               rotulo_de_ia=False, cor=None, escolhas=None):
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
    # A maior das duas faixas da capa (P188 2): a de cima, com a frase, de uma beirada à outra, do alto
    # do quadro até a foto.
    assert (esquerda, direita) == (0, edicao_video.TELA[0])
    assert (cima, baixo) == (0, edicao_video.PE_DA_FAIXA_DE_CIMA)
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
               rotulo_de_ia=False, cor=None, escolhas=None):
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
    # E o começo do vídeo, em MP4, com a passagem de uma capa para a outra (P175 1).
    if shutil.which("ffmpeg"):
        assert exemplo["abertura"][4:8] == b"ftyp"
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
    # O nome comprido cabe em duas linhas, no retângulo da frase na faixa de cima (P188 2).
    esquerda, cima, direita, baixo = edicao_video.lugar_das_letras_na_grade()
    fonte, linhas = edicao_video._quebra_da_grade("Removedor de Bolinhas Elétrico", _fonte_da_capa(), direita - esquerda,
                                                  baixo - cima)
    assert len(linhas) == 2 and fonte.size >= edicao_video.LETRAS_NA_GRADE[1]
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
    # produto e traz a vantagem, em letra grande, até 20 letras como antes.
    for prompt in (edicao_video.prompt_dos_textos("Calça"), edicao_video._CAPA_NO_PROMPT):
        assert "começa pelo que é o produto e traz a vantagem que o vídeo mostra" in prompt
        assert "a mesma vantagem em poucas palavras" not in prompt and "até 20 caracteres" in prompt
    # Os exemplos que a IA recebe cabem no limite e no retângulo da frase, em letra grande (com a frase
    # no meio, P198 1, a de quase 20 letras um pouco menor).
    esquerda, cima, direita, baixo = edicao_video.lugar_das_letras_na_grade()
    for exemplo in ("Calça que modela", "Travessas 3 tamanhos", "Copo sempre gelado"):
        assert f'"{exemplo}"' in edicao_video._CAPA_NO_PROMPT and len(exemplo) <= edicao_video.MAXIMO_DA_CAPA
        fonte, _linhas = edicao_video._quebra_da_grade(exemplo, _fonte_da_capa(), direita - esquerda, baixo - cima)
        assert fonte.size >= 70, exemplo


def test_capa_vai_com_a_frase_curta_e_sem_ela_com_o_nome(monkeypatch, tmp_path):
    import registro_processos as rp
    _versoes_de_mentira(monkeypatch)
    frases = []
    # A capa do vídeo aberto (P129) usa a mesma frase: conta só a da grade.
    monkeypatch.setattr(edicao_video, "_capa_da_vez",
                        lambda foto, frase, no_video=False, cor=None, segunda=None: (None if no_video else
                                                                                     frases.append(frase))
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
    assert all(f"[{entrada}:v]{quadrado},{videos.POR_CIMA}[mini{n}]" in filtro for n, entrada in enumerate((2, 5, 6)))
    mx, my = edicao_video.CENTRO_DA_MINIATURA
    lugar = f"overlay=x={mx}-w/2:y={my}-h/2:shortest=1"
    assert f"[corpo][mini0]{lugar}:enable='lt(t,3.000)'[mini0_no_corpo]" in filtro
    assert f"[mini0_no_corpo][mini1]{lugar}:enable='gte(t,3.000)*lt(t,6.000)'[mini1_no_corpo]" in filtro
    assert f"[mini1_no_corpo][mini2]{lugar}:enable='gte(t,6.000)'[semmoldura]" in filtro
    assert f"[3:v]loop=loop=-1:size=25:start=0,{videos.POR_CIMA}[seta]" in filtro and "[4:a][som]concat=n=2:v=0:a=1[a]" in filtro
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
    assert f"[2:v]scale={lado}:-2,{videos.POR_CIMA}[mini]" in ffmpeg[ffmpeg.index("-filter_complex") + 1] and ffmpeg.count("-i") == 6
    # No que vai ao ar, o registro diz; sem a nossa miniatura, não.
    _versoes_de_mentira(monkeypatch)
    pedidas = []

    def editar(video, foto, destino, avisos=False, musica=None, capa=None, miniatura=True, outras_fotos=(),
               rotulo_de_ia=False, cor=None, escolhas=None):
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
               rotulo_de_ia=False, cor=None, escolhas=None):
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
               rotulo_de_ia=False, cor=None, escolhas=None):
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
    # canto estava livre (P81). Ela diz também onde fica cada coisa que o criador pôs por cima
    # do vídeo (desde a P212 1, em qualquer parte da tela e com o tempo), e a miniatura não passa
    # por nenhuma, com a folga: diminui para ficar acima dela (P97) ou, quando nem com 2/3 do
    # tamanho cabe, sai. A lista de antes, só do alto e sem o tempo, ainda é lida.
    for prompt in (edicao_video.PROMPT_DOS_TEXTOS, edicao_video.PROMPT_DAS_VERSOES):
        assert "\"por_cima_do_video\"" in prompt and "em qualquer parte da tela" in prompt
        assert "em qualquer momento do vídeo" in prompt
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
               rotulo_de_ia=False, cor=None, escolhas=None):
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
    for pedir in (edicao_video.prompt_dos_textos, edicao_video.prompt_das_versoes):
        assert f"de uns {comeco}% a {fim}% da largura e de uns {desde}% a {ate}% da altura" in pedir("Bolsa")
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
               rotulo_de_ia=False, cor=None, escolhas=None):
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
    # e as legendas entram onde não os cobrem, no momento de cada uma (P212 1: a IA diz onde e
    # quando eles aparecem); a IA também diz se o canto da miniatura está livre.
    for prompt in (edicao_video.PROMPT_DOS_TEXTOS, edicao_video.PROMPT_DAS_VERSOES):
        assert "nem o texto dentro das fotos e quadros do produto que o vídeo pôs por cima" in prompt
        assert "Aqui não contam as fotos, quadros e textos que o próprio vídeo pôs por cima da imagem" in prompt
        assert "\"por_cima_do_video\"" in prompt
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
    # o que o criador acrescentou por cima na edição; cada texto nosso não cobre o que ele pôs
    # por cima no momento em que o texto aparece (P52, P82 e P212 1).
    for pedir in (edicao_video.prompt_dos_textos, edicao_video.prompt_das_versoes):
        texto = pedir("Fone")
        assert edicao_video._O_QUE_FOI_FILMADO_NAO_CONTA in texto
        assert "uma revista ou a tela de um celular" in texto and "nunca contam" in texto
        assert "as coisas filmadas também não" in texto and "nome do perfil nem as coisas filmadas" in texto
        assert "onde e quando aparecem, em qualquer parte da tela" in texto
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
    # O porquê de ela não ir ao outro canto de cima também (P213 1).
    _textos_da_tela(monkeypatch, dict(base, canto_ocupado=True, outro_canto_ocupado=True,
                                      por_cima=[(55.0, 95.0, 25.0, 30.0)]))
    assert edicao_video.COM_A_MINIATURA_MENOR in edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Fone")[1]
    # Com o canto livre, a miniatura vai inteira, e nada é anotado.
    _textos_da_tela(monkeypatch, dict(base, canto_ocupado=False))
    edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Fone")
    registro = rp.sequencia("shopee_video", edicao_video.PROCESSO_DO_CANTO, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in registro] == [
        ("de fora", f"{edicao_video.CANTO_SEM_DIZER_ONDE}; {edicao_video.OUTRO_CANTO_SEM_RESPOSTA}"),
        ("menor", f"a coisa do criador no alto começa a 25% da altura; {edicao_video.OUTRO_CANTO_OCUPADO}")]
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
    # O pé da legenda na altura do pé da seta (logo abaixo vem o cartão do produto), sem cobrir a seta e
    # dentro do que o app mostra.
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
    # Até 2 linhas (LINHAS_DA_LEGENDA): a frase curta vai numa linha só.
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


def test_legenda_quebra_nas_pausas_sem_separar_o_nome_do_produto():
    # Vídeo do Rafael das 14:47 de 10/11: a fala comprida foi dividida em "com esse kit de / banho de" e
    # "verniz para seus cabelos. / Clica no link e compre já!", com o nome do produto cortado entre duas
    # legendas. Escolha dele (P199 1): a troca de legenda não separa "banho de verniz", e nem ela nem a
    # troca de linha deixam "de", "e", "com", "para"... no fim; o ponto e a vírgula seguem preferidos.
    texto = ("Tratamento potente e duradouro com esse kit de banho de verniz para seus cabelos. "
             "Clica no link e compre já!")
    pedacos = edicao_video.pedacos_da_legenda(0.0, 8.0, texto)
    assert [parte for _i, _f, parte, _imagem in pedacos] == [
        "Tratamento potente e duradouro", "com esse kit de banho de verniz", "para seus cabelos.",
        "Clica no link e compre já!"]

    def linhas(parte):
        return edicao_video.letra_e_linhas_da_legenda(parte)[1]
    assert [linhas(parte) for _i, _f, parte, _imagem in pedacos] == [
        ["TRATAMENTO POTENTE", "E DURADOURO"], ["COM ESSE KIT", "DE BANHO DE VERNIZ"], ["PARA SEUS", "CABELOS."],
        ["CLICA NO LINK", "E COMPRE JÁ!"]]
    # Na letra maior, "com esse kit de / banho de verniz" era a única quebra que cabia: a letra um pouco
    # menor, que quebra sem a ligação no fim da 1ª linha, ganha dela (com a letra de 34 a 28 px, P214 1).
    assert edicao_video.letra_e_linhas_da_legenda("com esse kit de banho de verniz")[0] < \
        edicao_video.LETRA_DA_LEGENDA[0]
    assert edicao_video.letra_e_linhas_da_legenda("Resultado visível desde a primeira") == (
        edicao_video.LETRA_DA_LEGENDA[0] - 2, ["RESULTADO VISÍVEL", "DESDE A PRIMEIRA"])
    # Sem ligação nem pontuação no caminho, a 1ª linha fica a mais comprida que cabe, como antes.
    assert linhas("Deixa o cabelo brilhante hoje") == ["DEIXA O CABELO", "BRILHANTE HOJE"]
    assert linhas("Leve") == ["LEVE"] and edicao_video._linhas_da_legenda("", lambda linha: True) == ([], True)


def test_o_pedido_da_ia_quer_a_fala_inteira_palavra_por_palavra():
    pedido = edicao_video.prompt_dos_textos("Jaqueta")
    for exigido in ("palavra por palavra", "sem resumir", "sem pular nenhuma frase", "Siga o áudio, não a imagem"):
        assert exigido in pedido
    # Sem limite de tamanho por trecho: com ele, a IA encurtava a fala.
    assert "trechos curtos" not in pedido and "caracteres, como [" not in pedido


def test_legendas_que_se_encostam_cortam_e_a_curta_demais_sai():
    letreiros = edicao_video.letreiros_da_fala(
        [(0.0, 3.0, "Primeira fala"), (2.5, 2.7, "rápida"), (2.7, 6.0, "Segunda fala"), (9.5, 14.0, "Fim")], 11.0)
    # A primeira acaba quando a seguinte começa; a de 0,2 s sai; a última fica dentro do vídeo.
    assert [(inicio, fim) for _, inicio, fim, _, _ in letreiros] == [(0.0, 2.5), (2.7, 6.0), (9.5, 11.0)]


def test_a_legenda_vai_embaixo_em_caixa_alta_na_letra_grossa_estreitada_com_a_sombra():
    # Escolha do Rafael (12/11, P214 1): a legenda da fala embaixo, ao lado das setinhas, com a letra da que
    # ficou em teste no meio da tela: em CAIXA ALTA, grossa e estreitada, branca com o contorno preto e a
    # sombra ("mais pra frente"), de 34 a 28 px, em até 2 linhas, sempre na mesma altura.
    import io

    import numpy
    from PIL import Image
    assert edicao_video.LETRA_DA_LEGENDA == (34, 28) and edicao_video.LINHAS_DA_LEGENDA == 2
    # Em CAIXA ALTA: a fala como foi dita dá a mesma legenda que ela em maiúsculas.
    imagem = edicao_video.legenda_da_fala("Olha que lindo")
    assert imagem == edicao_video.legenda_da_fala("OLHA QUE LINDO")
    # Na maior letra que cabe, estreitada: 85% da largura da letra normal.
    assert edicao_video.letra_e_linhas_da_legenda("Olha que lindo") == (34, ["OLHA QUE LINDO"])
    normal = edicao_video._medida_da_linha("OLHA QUE LINDO", edicao_video._fonte_da_legenda(34))[1]
    assert _medidas(imagem)[0] == round(normal * edicao_video.ESTREITA_DA_LEGENDA) < normal
    # Branca com o contorno preto e a sombra (preto semitransparente à direita e embaixo das letras).
    pixels = numpy.asarray(Image.open(io.BytesIO(imagem)).convert("RGBA")).reshape(-1, 4).astype(int)
    cor, alfa = pixels[:, :3], pixels[:, 3]
    brancos = int(((alfa > 240) & (cor.min(axis=1) > 230)).sum())
    pretos = int(((alfa > 240) & (cor.max(axis=1) < 30)).sum())
    sombra = int(((alfa >= 190) & (alfa <= 210) & (cor.max(axis=1) < 30)).sum())
    assert brancos > 300 and pretos > 300 and sombra > 50
    # Sempre na mesma altura, com o pé no das setinhas, entre elas e os ícones do app.
    letreiros = edicao_video.letreiros_da_fala(
        [(0.0, 2.0, "Olha que lindo"), (2.0, 4.0, "esse vestido de festa é perfeito para o verão")], 5.0)
    assert len(letreiros) >= 2
    for png, _inicio, _fim, x, y in letreiros:
        largura, altura = _medidas(png)
        assert y + altura == edicao_video.PE_DA_LEGENDA
        assert edicao_video.ESQUERDA_DA_LEGENDA <= x and x + largura <= edicao_video.DIREITA_DA_LEGENDA
    # A palavra sozinha que não cabe nem na menor letra vai encolhida até caber: nenhuma palavra sai.
    longa = edicao_video.pedacos_da_legenda(0.0, 2.0, "Inconstitucionalissimamente")
    assert [parte for _i, _f, parte, _imagem in longa] == ["Inconstitucionalissimamente"]
    assert _medidas(longa[0][3])[0] <= edicao_video.DIREITA_DA_LEGENDA - edicao_video.ESQUERDA_DA_LEGENDA
    # O pedido à IA não quer mais onde fica o produto em cada trecho da fala (era só da legenda do meio).
    assert '"produto": [' not in edicao_video.prompt_dos_textos("Vestido")


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
    monkeypatch.setattr(edicao_video, "textos_das_versoes", lambda video, nome, *_: {
        "nome": "Vestido", "vantagem": "Tecido leve", "lugar": "alto", "legendas": fala, "falas": [[0.5, 2.0]]})
    recebidas = []

    def editar_2_e_versoes(video, foto, destino, nome="", vantagem="", versoes_da_ia=(), chamada="", falas=None,
                           lugar=None, miniatura=True, legendas=(), cor=None, escolhas=None, lugares=None,
                           por_cima=()):
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


def test_ia_diz_se_a_foto_do_anuncio_tem_letras(monkeypatch):
    # Escolha do Rafael (08/11, P181 2): a foto do anúncio vai inteira à capa, com as letras que
    # tiver; a IA só diz se ela tem letras, vendo só a foto, para a medição das punições.
    import api_gemini
    respostas, pedidos = [], []

    async def ia(prompt, imagens=None):
        pedidos.append((prompt, [tipo for _dados, tipo in imagens or []]))
        return respostas.pop(0)
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", ia)
    foto = _foto_jpg()
    for resposta, esperado in (('{"letras": true}', edicao_video.COM_LETRAS),
                               ('```json\n{"letras": false}\n```', edicao_video.SEM_LETRAS),
                               (None, edicao_video.SEM_RESPOSTA_DAS_LETRAS),
                               ("sem json", edicao_video.SEM_RESPOSTA_DAS_LETRAS),
                               ('{"letras": "sim"}', edicao_video.SEM_RESPOSTA_DAS_LETRAS)):
        respostas.append(resposta)
        assert edicao_video.letras_da_foto(foto) == esperado, resposta
    assert pedidos == [(edicao_video.PROMPT_DAS_LETRAS_DA_FOTO, ["image/jpeg"])] * 5
    # A foto que não abre nem vai à IA.
    assert edicao_video.letras_da_foto(b"nao e imagem") == edicao_video.SEM_RESPOSTA_DAS_LETRAS
    assert edicao_video.letras_da_foto(None) == edicao_video.SEM_RESPOSTA_DAS_LETRAS
    assert len(pedidos) == 5


def test_capa_que_vai_ao_ar_usa_a_foto_do_anuncio_inteira_mesmo_com_letras(monkeypatch, tmp_path):
    # Escolha do Rafael (08/11, P181 2): sem corte e sem quadro do vídeo. Com as letras numa beirada
    # (que antes saíam pelo corte) ou em cima do produto (que antes levavam a um quadro do vídeo), a
    # capa da grade e a do vídeo aberto saem da foto do anúncio inteira; o registro diz se ela tinha
    # letras, e o rascunho do robô as anota (anotar), para a medição de quais posts levam punição.
    import api_gemini
    _versoes_de_mentira(monkeypatch)
    _textos_da_tela(monkeypatch, {"nome": "Bolsa de Palha", "vantagem": "Leve e resistente", "capa": "Leve e forte",
                                  "lugar": "alto"})
    letras = ['{"letras": true, "sobre_o_produto": false, "caixa": [150, 0, 1000, 1000]}',
              '{"letras": true, "sobre_o_produto": true, "caixa": [0, 0, 1000, 1000]}']
    pedidos = []

    async def ia(prompt, imagens=None):
        pedidos.append(prompt)
        if "recorte" in prompt:                    # a conferência do corte, de antes da P181 2
            return '{"inteiro": true}'
        return letras.pop(0) if letras else None

    async def ia_do_video(video, prompt):
        return None
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", ia)
    monkeypatch.setattr(api_gemini, "analisar_video_gemini", ia_do_video)
    capas = []
    monkeypatch.setattr(edicao_video, "capa_com_chamada",
                        lambda foto, frase, no_video=False, cor=None, segunda=None: capas.append(foto) or b"capa")
    monkeypatch.setattr(edicao_video, "editar_2", lambda *a, **k: ("", {"textos": ["Bolsa"], "legendas": 0}))
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DA_CAPA: True})
    anotados = []
    for _vez in range(2):
        anotado = {}
        edicao_video.editar_para_postar("v.mp4", _foto_jpg(), str(tmp_path / "r.mp4"), "Bolsa", anotar=anotado)
        anotados.append(anotado.get("letras"))
    assert capas == [_foto_jpg()] * 4
    # Uma pergunta só à IA por vídeo: se a foto tem letras (nada de corte nem de quadro do vídeo).
    assert pedidos == [edicao_video.PROMPT_DAS_LETRAS_DA_FOTO] * 2
    assert anotados == ["1", "1"]
    linhas = edicao_video.registro_processos.sequencia("shopee_video", edicao_video.PROCESSO_DAS_LETRAS_DA_FOTO,
                                                       "2000-01-01 00:00:00")
    assert [r[2] for r in linhas] == [edicao_video.COM_LETRAS] * 2
    # Sem a resposta da IA, a foto vai do mesmo jeito, e o rascunho não anota (fica fora da medição).
    letras[:] = ['{"letras": false}']
    for esperado in ("0", ""):
        anotado = {}
        edicao_video.editar_para_postar("v.mp4", _foto_jpg(), str(tmp_path / "r.mp4"), "Bolsa", anotar=anotado)
        assert anotado["letras"] == esperado
    assert capas == [_foto_jpg()] * 8
    assert consultar("SELECT resultado, ok FROM registro_processos WHERE processo = ? ORDER BY id DESC",
                     edicao_video.PROCESSO_DAS_LETRAS_DA_FOTO) == (edicao_video.SEM_RESPOSTA_DAS_LETRAS, 0)
    # No modo assistente (sem anotar), fora da medição, a foto vai inteira sem a pergunta à IA.
    edicao_video.editar_para_postar("v.mp4", _foto_jpg(), str(tmp_path / "r.mp4"), "Bolsa")
    assert len(pedidos) == 4 and capas == [_foto_jpg()] * 10
    # Desligada, a capa não sai e a IA nem olha a foto.
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DA_CAPA: False})
    anotado = {}
    edicao_video.editar_para_postar("v.mp4", _foto_jpg(), str(tmp_path / "r.mp4"), "Bolsa", anotar=anotado)
    assert len(pedidos) == 4 and "letras" not in anotado and len(capas) == 10


def test_exemplo_da_capa_usa_a_foto_do_anuncio_inteira(monkeypatch):
    # O exemplo do painel mostra a capa como ela vai ao ar (P181 2): a foto do anúncio inteira, mesmo
    # com as letras numa beirada (que antes saíam pelo corte), sem perguntar nada à IA sobre elas.
    import api_gemini
    respostas = ['{"letras": true, "sobre_o_produto": false, "caixa": [150, 0, 1000, 1000]}', '{"inteiro": true}']
    pedidos = []

    async def ia(prompt, imagens=None):
        pedidos.append(prompt)
        return respostas.pop(0) if respostas else None
    monkeypatch.setattr(api_gemini, "gerar_texto_gemini", ia)
    monkeypatch.setattr(edicao_video, "_produto_do_link", lambda link: {"nome": "Bolsa de Palha"})
    monkeypatch.setattr(edicao_video, "textos_da_tela", lambda video, nome, *_: {"capa": "Leve e forte"})
    capas = []
    monkeypatch.setattr(edicao_video, "capa_com_chamada",
                        lambda foto, frase, no_video=False, cor=None, segunda=None: capas.append(foto) or None)
    feitos = []
    monkeypatch.setattr(edicao_video, "_exemplo", lambda chave, editar_um: feitos.append(
        editar_um("v.mp4", "link", _foto_jpg())))
    edicao_video.exemplo_capa()
    assert capas == [_foto_jpg()] and feitos == [("a capa com a chamada não saiu", None)]
    assert pedidos == []


# --- A cor de cada vídeo (P159 2) ---

def test_cada_cor_do_produto_tem_um_tom_e_a_letra_que_contrasta():
    # Escolha do Rafael (06/11, P159 2): a cor principal do produto no lugar do laranja e do preto,
    # com a letra branca ou preta, a de mais contraste. O vermelho (a cor da chamada final), o
    # "colorido" (que a IA não deve mais dizer, P179 1) e o sem a cor da IA ficam com as cores de sempre.
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


def test_produto_de_varias_cores_vai_na_cor_que_mais_aparece_nele():
    # Escolha do Rafael (08/11, P179 1): no produto de várias cores, a IA diz a cor da lista que mais
    # aparece nele, e o "colorido" (que deixava o vídeo no laranja de sempre) sai dos dois pedidos; o
    # vermelho continua na lista, para ficar com as cores de sempre.
    for pedir in (edicao_video.prompt_dos_textos, edicao_video.prompt_das_versoes):
        pedido = pedir("Pote")
        assert "colorido" not in pedido
        assert "várias cores, diga a que mais aparece nele" in pedido
        assert "vermelho" in pedido
    # Se a IA ainda disser "colorido", o vídeo fica com as cores de sempre, e o registro conta.
    assert edicao_video._nome_lugar_e_falas({"cor": "Colorido"})["cor"] == "colorido"
    assert edicao_video.cor_do_produto("colorido") is None


def test_capa_com_a_cor_do_produto_nas_faixas_com_a_letra_que_contrasta():
    import io

    from PIL import Image
    _x1, cima, _x2, baixo = edicao_video.lugar_da_foto()
    for nome, letra_branca in (("azul", True), ("amarelo", False), ("branco", False)):
        cor = edicao_video.CORES_DO_PRODUTO[nome]
        capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(_foto_jpg(), "Organize sua cozinha",
                                                                   cor=cor))).convert("RGB")
        for ponto in [(360, 0), (0, 0), (719, cima - 1), (0, baixo), (719, baixo + 5)]:
            assert _cor_de(capa, ponto, cor), (nome, ponto)
        # Na grade, o fio de baixo vai do pé da foto até o fim do quadro na mesma cor, também nas claras
        # (P171, que respondeu a P170, e P196 1).
        assert _cor_de(capa, (3, 1279), cor) and _cor_de(capa, (360, 1279), cor)
        assert all(_cor_de(capa, (x, y), cor) for x in range(0, 720, 6) for y in range(baixo, 1280, 6)), nome
        # A frase, na faixa de cima, na letra que contrasta.
        pontos = [capa.getpixel((x, y)) for x in range(0, 720, 2) for y in range(0, cima, 2)]
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
    monkeypatch.setattr(edicao_video, "letras_da_foto", lambda foto: edicao_video.SEM_LETRAS)
    capas, editores = [], []
    monkeypatch.setattr(edicao_video, "capa_com_chamada",
                        lambda foto, frase, no_video=False, cor=None, segunda=None: capas.append(cor) or b"capa")

    def editar_2(video, foto, destino, nome="", vantagem="", chamada="", lugar=None, avisos=False, musica=None,
                 capa=None, miniatura=True, outras_fotos=(), legendas=(), rotulo_de_ia=False, cor=None, escolhas=None,
                 lugares=None, por_cima=()):
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
        # O que o Editar ✏️ precisa (P192 1) vai junto, em "refazer".
        anotado.pop("refazer")
        assert (capas, editores, anotado) == ([esperada, esperada], [esperada], {"cor": nome, "letras": "0"}), cor
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

    for nome in ("azul", "amarelo", "preto", "branco"):
        cor = edicao_video.CORES_DO_PRODUTO[nome]
        png = edicao_video.capa_com_chamada(_foto_jpg(), "Organize sua cozinha", cor=cor)
        capa = Image.open(io.BytesIO(png)).convert("RGB")
        assert edicao_video.faixa_laranja(capa, cor=cor) == (0, edicao_video.PE_DA_FAIXA_DE_CIMA, 0,
                                                             edicao_video.TELA[0]), nome
        # Pelo laranja de sempre, ela não é achada.
        assert edicao_video.faixa_laranja(capa) is None, nome
        assert edicao_video.faixa_nos_lados(grade(png), caixa, cor) is True, nome
        no_video = edicao_video.capa_com_chamada(_foto_jpg(), "Organize sua cozinha", no_video=True, cor=cor)
        assert edicao_video.faixa_nos_lados(grade(no_video), caixa, cor) is False, nome


def _foto_de_fundo(fundo, produto=(200, 30, 40)):
    """Uma foto de anúncio de mentira, 800x800: o produto (um retângulo) no meio do fundo, longe do pé da foto."""
    import io

    from PIL import Image, ImageDraw
    imagem = Image.new("RGB", (800, 800), fundo)
    ImageDraw.Draw(imagem).rectangle((200, 100, 600, 500), fill=produto)
    saida = io.BytesIO()
    imagem.save(saida, "JPEG", quality=95)
    return saida.getvalue()


def _foto_branca(desenhar=None):
    """Uma foto de mentira, 800x800, de fundo branco, com o que desenhar (ImageDraw) põe nela."""
    import io

    from PIL import Image, ImageDraw
    imagem = Image.new("RGB", (800, 800), (250, 250, 250))
    if desenhar:
        desenhar(ImageDraw.Draw(imagem))
    saida = io.BytesIO()
    imagem.save(saida, "JPEG", quality=95)
    return saida.getvalue()


def test_faixa_que_some_no_fundo_da_foto_vai_na_2a_cor_do_produto():
    # Print do Rafael de 07/11, 04:15 (P173): o pote branco numa foto de fundo branco, com a faixa
    # branca, sumia na foto, e isso tem de ser evitado daqui pra frente: o fio e a faixa das duas capas
    # vão na 2ª cor que mais se destaca no produto (no vermelho, o laranja da Shopee, como na P159 2), e
    # o post confere a faixa nela. Sem a 2ª cor, ou com ela sumindo também, vai um tom mais escuro da
    # cor (no branco, um cinza-claro) e, no fundo escuro, um mais claro (P174 3). Na foto que não é da
    # cor da faixa, ela continua na do produto.
    import io

    from PIL import Image
    branco, azul = edicao_video.CORES_DO_PRODUTO["branco"], edicao_video.CORES_DO_PRODUTO["azul"]
    preto, laranja = edicao_video.CORES_DO_PRODUTO["preto"], edicao_video.LARANJA_DA_SHOPEE
    escuro = (60, 50, 40)
    fundo_branco, fundo_laranja = _foto_de_fundo((250, 250, 250)), _foto_de_fundo(laranja, produto=azul)
    assert [edicao_video.cor_da_segunda(nome) for nome in ("azul", " Vermelho ", "", None, "xadrez")] == [
        azul, laranja, None, None, None]
    cinza_claro, laranja_claro = (176, 176, 176), (243, 127, 104)
    assert edicao_video.tons_da_cor(branco)[:2] == [cinza_claro, (122, 122, 122)]
    assert edicao_video.tons_da_cor(laranja)[0] == laranja_claro and edicao_video.tons_da_cor(preto)[0] == (104, 104, 104)
    assert edicao_video.cor_da_faixa(fundo_branco, branco, azul) == azul
    assert edicao_video.cor_da_faixa(fundo_branco, branco, edicao_video.cor_da_segunda("vermelho")) == laranja
    assert edicao_video.cor_da_faixa(fundo_branco, branco) == cinza_claro
    assert edicao_video.cor_da_faixa(fundo_branco) == laranja
    assert edicao_video.cor_da_faixa(fundo_laranja) == laranja_claro
    assert edicao_video.cor_da_faixa(fundo_laranja, None, azul) == azul
    assert edicao_video.cor_da_faixa(fundo_laranja, edicao_video.CORES_DO_PRODUTO["laranja"]) == laranja_claro
    # O produto preto na foto de fundo escuro: um tom mais claro.
    assert edicao_video.cor_da_faixa(_foto_de_fundo((50, 50, 50), produto=(200, 30, 40)), preto) == (104, 104, 104)
    assert edicao_video.cor_da_faixa(fundo_laranja, branco, azul) == branco
    assert edicao_video.cor_da_faixa(_foto_jpg(), branco, azul) == branco
    assert edicao_video.cor_da_faixa(b"", branco, azul) == branco
    # Metade do pé da foto no azul: a 2ª cor sumiria também, e vai o tom mais escuro do branco.
    assert edicao_video.cor_da_faixa(_foto_branca(lambda d: d.rectangle((0, 700, 399, 799), fill=azul)),
                                     branco, azul) == cinza_claro
    # Só o alto da foto no branco (um chão escuro embaixo): o fio sumiria nele, e os dois vão na 2ª cor.
    assert edicao_video.cor_da_faixa(_foto_branca(lambda d: d.rectangle((0, 300, 799, 799), fill=escuro)),
                                     branco, azul) == azul
    # Menos de um quarto da beirada na cor da faixa não troca.
    assert edicao_video.cor_da_faixa(_foto_branca(lambda d: d.rectangle((160, 0, 799, 799), fill=escuro)),
                                     branco, azul) == branco
    assert [edicao_video.nome_da_cor(cor) for cor in (laranja, None, preto, azul, cinza_claro)] == [
        "", "", "preto", "azul", "#b0b0b0"]
    assert [edicao_video.cor_guardada(texto) for texto in ("#b0b0b0", "azul", "", None, "#zzzzzz", "vermelho")] == [
        cinza_claro, azul, None, None, None, None]

    frase = "Creme para cachos"
    _x1, cima, _x2, baixo = edicao_video.lugar_da_foto()
    capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(fundo_branco, frase, cor=branco,
                                                               segunda=azul))).convert("RGB")
    for ponto in [(360, 0), (0, cima - 1), (719, cima - 1), (0, baixo), (719, baixo + 5), (3, 1279)]:
        assert _cor_de(capa, ponto, azul), ponto
    pontos = [capa.getpixel((x, y)) for x in range(0, 720, 2) for y in range(0, cima, 2)]
    assert sum(1 for p in pontos if min(p) > 250) > 50 and not any(max(p) < 50 for p in pontos)
    # O robô confere no post a faixa na cor que o rascunho guardou (o nome dela).
    cor_guardada = edicao_video.cor_do_produto(edicao_video.nome_da_cor(edicao_video.cor_da_faixa(fundo_branco, branco,
                                                                                                azul)))
    assert edicao_video.faixa_laranja(capa, cor=cor_guardada) == (0, cima, 0, edicao_video.TELA[0])
    # A do vídeo aberto vai na mesma cor: a faixa de cima e o fio logo abaixo da foto.
    no_video = Image.open(io.BytesIO(edicao_video.capa_com_chamada(fundo_branco, frase, no_video=True, cor=branco,
                                                                   segunda=azul))).convert("RGB")
    esquerda, direita = edicao_video.VISIVEL_NO_APP
    assert _cor_de(no_video, (esquerda + 2, 3), azul) and _cor_de(no_video, (direita - 2, cima - 3), azul)
    pe_do_fio = max(y for y in range(1280) if max(no_video.getpixel((360, y))) > 60) + 1
    assert all(_cor_de(no_video, (360, y), azul) for y in range(pe_do_fio - edicao_video.FIO_DA_CAPA, pe_do_fio))
    # Sem a 2ª cor, o cinza-claro (o tom mais escuro do branco), com a letra preta, e o post o confere
    # pelo #rrggbb que o rascunho guarda; no fundo laranja, um laranja mais claro, nas duas.
    capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(fundo_branco, frase, cor=branco))).convert("RGB")
    assert _cor_de(capa, (360, 0), cinza_claro) and _cor_de(capa, (3, 1279), cinza_claro)
    pontos = [capa.getpixel((x, y)) for x in range(0, 720, 2) for y in range(0, cima, 2)]
    assert sum(1 for p in pontos if max(p) < 50) > 50 and not any(min(p) > 250 for p in pontos)
    assert edicao_video.faixa_laranja(capa, cor=edicao_video.cor_guardada(edicao_video.nome_da_cor(cinza_claro))) == (
        0, cima, 0, edicao_video.TELA[0])
    capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(fundo_laranja, "Bolsa espaçosa"))).convert("RGB")
    assert all(_cor_de(capa, ponto, laranja_claro) for ponto in [(360, 0), (3, 1279), (719, baixo)])
    no_video = Image.open(io.BytesIO(edicao_video.capa_com_chamada(fundo_laranja, "Bolsa espaçosa",
                                                                   no_video=True))).convert("RGB")
    assert _cor_de(no_video, (esquerda + 2, 3), laranja_claro)
    # Na foto que não é da cor da faixa, a faixa branca continua.
    capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(fundo_laranja, frase, cor=branco,
                                                               segunda=azul))).convert("RGB")
    assert _cor_de(capa, (3, 1279), branco) and _cor_de(capa, (360, 0), branco)


def test_ia_diz_a_2a_cor_do_produto():
    # P173: a IA diz também a 2ª cor que mais se destaca no produto, da mesma lista, diferente da
    # principal; o "colorido" e o nome fora da lista ficam de fora.
    assert '"cor_2"' in edicao_video.prompt_dos_textos("Pote")
    assert '"cor_2"' in edicao_video.prompt_das_versoes("Pote")
    for dados, segunda in (({"cor": "branco", "cor_2": " Azul "}, "azul"), ({"cor": "branco", "cor_2": "vermelho"}, "vermelho"),
                           ({"cor": "branco", "cor_2": "branco"}, None), ({"cor": "branco", "cor_2": "colorido"}, None),
                           ({"cor": "branco", "cor_2": "xadrez"}, None), ({"cor": "branco"}, None),
                           ({"cor_2": "roxo"}, "roxo")):
        assert edicao_video._nome_lugar_e_falas(dados).get("cor_2") == segunda, dados


def test_video_com_a_faixa_que_some_na_foto_guarda_a_cor_em_que_ela_saiu(monkeypatch, tmp_path):
    # P173 e P174 3: com o fio e a faixa na 2ª cor do produto (ou, sem ela, num tom mais escuro) no lugar do branco que
    # sumia na foto, o rascunho guarda a cor em que a faixa saiu (o robô confere a faixa no post nela)
    # e o registro conta; a capa recebe a cor do produto e a 2ª (e troca só o fio e a faixa), e a caixa
    # do nome e da vantagem e a moldura da miniatura continuam na cor do produto.
    _versoes_de_mentira(monkeypatch)
    textos = {"nome": "Creme de Cabelo", "vantagem": "Cachos definidos", "capa": "Creme para cachos", "lugar": "alto",
              "cor": "branco"}
    monkeypatch.setattr(edicao_video, "letras_da_foto", lambda foto: edicao_video.SEM_LETRAS)
    capas, editores = [], []
    monkeypatch.setattr(edicao_video, "capa_com_chamada",
                        lambda foto, frase, no_video=False, cor=None, segunda=None: capas.append((cor, segunda))
                        or b"capa")

    def editar_2(video, foto, destino, nome="", vantagem="", chamada="", lugar=None, avisos=False, musica=None,
                 capa=None, miniatura=True, outras_fotos=(), legendas=(), rotulo_de_ia=False, cor=None, escolhas=None,
                 lugares=None, por_cima=()):
        editores.append(cor)
        return "", {"textos": [nome], "legendas": 0}
    monkeypatch.setattr(edicao_video, "editar_2", editar_2)
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DA_CAPA: True})
    branco, azul = edicao_video.CORES_DO_PRODUTO["branco"], edicao_video.CORES_DO_PRODUTO["azul"]
    pe_azul = _foto_branca(lambda d: d.rectangle((0, 700, 399, 799), fill=azul))
    for foto, segunda, guardada in ((_foto_de_fundo((250, 250, 250)), "azul", "azul"),
                                    (_foto_de_fundo((250, 250, 250)), None, "#b0b0b0"), (pe_azul, "azul", "#b0b0b0"),
                                    (_foto_jpg(), "azul", "branco")):
        _textos_da_tela(monkeypatch, dict(textos, cor_2=segunda) if segunda else textos)
        capas.clear()
        editores.clear()
        anotado = {}
        edicao_video.editar_para_postar("v.mp4", foto, str(tmp_path / "r.mp4"), "Creme de Cabelo", anotar=anotado)
        anotado.pop("refazer")
        tom = azul if segunda else None
        assert (capas, editores, anotado) == ([(branco, tom), (branco, tom)], [branco],
                                              {"cor": guardada, "letras": "0"}), guardada
    linhas = edicao_video.registro_processos.sequencia("shopee_video", edicao_video.PROCESSO_DA_FAIXA_QUE_SOME,
                                                       "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in linhas] == [(edicao_video.A_2A_COR, "azul"),
                                              (edicao_video.TOM_MAIS_ESCURO, edicao_video.SEM_A_2A_COR),
                                              (edicao_video.TOM_MAIS_ESCURO, edicao_video.A_2A_COR_SOME_TAMBEM)]


def test_frase_acaba_antes_da_sacolinha_e_dos_icones_do_app():
    # Escolha do Rafael (06/11, P165 1): no vídeo aberto, o coração e os ícones da direita do app
    # ficavam por cima do fim da frase; ela acaba antes deles. Com a frase em cima (P188 2 e P189 B),
    # o retângulo dela acaba antes da sacolinha da grade e da coluna de ícones do vídeo aberto, nas
    # duas capas, e a faixa continua de um lado ao outro. Escolha do Rafael (10/11, P198 1): no print
    # das 14:47, a frase ficava 86 px à esquerda do meio no vídeo aberto; o retângulo dela fica no meio
    # do que o vídeo aberto mostra (o meio da grade também), ainda antes da sacolinha e dos ícones.
    import io

    from PIL import Image
    esquerda, direita = edicao_video.VISIVEL_NO_APP
    x1, _cima, x2, _baixo = edicao_video.lugar_das_letras_na_grade()
    fim = min(edicao_video.SACOLINHA_DA_GRADE[0], edicao_video.ICONES_NO_VIDEO_ABERTO) - edicao_video.MARGEM_DA_FAIXA
    assert x2 == fim and x1 - esquerda == direita - x2 and (x1 + x2) / 2 == edicao_video.TELA[0] / 2
    assert x1 > esquerda + edicao_video.MARGEM_DA_FAIXA
    pe = edicao_video.PE_DA_FAIXA_DE_CIMA
    for frase in ("Almofada respirável", "Almofada ortopédica respirável"):
        for no_video in (True, False):
            capa = Image.open(io.BytesIO(edicao_video.capa_com_chamada(_foto_jpg(), frase,
                                                                       no_video=no_video))).convert("RGB")
            letras = [x for x in range(0, 720) for y in range(0, pe, 2) if min(capa.getpixel((x, y))) > 200]
            assert letras and max(letras) <= fim and min(letras) >= x1 - 1, (frase, no_video)
            assert abs((min(letras) + max(letras)) / 2 - (x1 + x2 - 1) / 2) <= 3, (frase, no_video)
            assert abs((min(letras) + max(letras)) / 2 - (esquerda + direita - 1) / 2) <= 3, (frase, no_video)
            assert _cor_de(capa, (direita - 2, pe - 3), edicao_video.LARANJA_DA_SHOPEE), (frase, no_video)


# --- Itens do vídeo no painel (P191 1 e P192 1) ---

def _edicao_de_mentira(monkeypatch):
    """O que a edição pediu ao ffmpeg (videos.com_foto_e_miniatura): a largura, o centro, as setinhas e a moldura."""
    pedidos = []

    def com_foto_e_miniatura(video, foto, destino, segundos, largura, centro, seta, centro_seta, *args, **opcoes):
        cores = None
        if seta and seta != edicao_video.SETA:
            # As setinhas noutra cor existem durante a edição; a cor de um ponto do meio da setinha acesa.
            from PIL import Image
            with Image.open(seta) as arquivo:
                quadro = arquivo.convert("RGBA")
                cores = {quadro.getpixel((x, y))[:3] for x in range(quadro.width) for y in range(quadro.height)
                         if quadro.getpixel((x, y))[3] == 255}
        pedidos.append({"largura": largura, "centro": centro, "seta": seta, "cores": cores,
                        "moldura": opcoes.get("moldura")})
        return ""
    monkeypatch.setattr(edicao_video.videos, "com_foto_e_miniatura", com_foto_e_miniatura)
    return pedidos


def test_itens_do_video_comecam_como_eram(monkeypatch, tmp_path):
    # Escolha do Rafael (10/11, P192 1): tudo começa igual a hoje.
    assert edicao_video.escolhas_do_painel() == edicao_video.ESCOLHAS_PADRAO == {
        "miniatura": "direita", "legenda": True, "setinhas": True, "moldura": True, "cor": "vermelho"}
    # O que não vale fica o padrão.
    assert edicao_video.escolhas_certas({"miniatura": "embaixo", "legenda": "sim", "cor": "roxo"}) == (
        edicao_video.ESCOLHAS_PADRAO)
    pedidos = _edicao_de_mentira(monkeypatch)
    destino = str(tmp_path / "r.mp4")
    assert edicao_video.editar("v.mp4", _foto_jpg(), destino) == ""
    assert pedidos == [{"largura": edicao_video.LARGURA_DA_MINIATURA, "centro": edicao_video.CENTRO_DA_MINIATURA,
                        "seta": edicao_video.SETA, "cores": None, "moldura": edicao_video.moldura_do_cartao()}]


def test_itens_do_video_mudam_a_edicao(monkeypatch, tmp_path):
    # Escolhas do Rafael (10/11, P191 1 e P192 1): a miniatura à esquerda ou sem ela, as setinhas e a
    # moldura do cartão com ou sem, e uma cor só para as duas.
    pedidos = _edicao_de_mentira(monkeypatch)
    destino = str(tmp_path / "r.mp4")
    largura = edicao_video.LARGURA_DA_MINIATURA
    assert edicao_video.editar("v.mp4", _foto_jpg(), destino, escolhas={"miniatura": "esquerda"}) == ""
    canto_x, canto_y = edicao_video.CANTO_DA_ESQUERDA
    assert pedidos[-1]["centro"] == (canto_x + largura // 2, canto_y + largura // 2)
    # O espelho do canto de sempre, dentro do que o app mostra do vídeo aberto.
    esquerda, direita = edicao_video.VISIVEL_NO_APP
    assert canto_x - esquerda == direita - edicao_video.CANTO_DA_MINIATURA[0] > 0
    assert canto_y == edicao_video.CANTO_DA_MINIATURA[1] > edicao_video.FIM_DA_BARRA_DE_BUSCA
    assert edicao_video.editar("v.mp4", _foto_jpg(), destino, escolhas={"miniatura": "sem"}) == ""
    assert pedidos[-1]["largura"] == 0
    assert edicao_video.editar("v.mp4", _foto_jpg(), destino, escolhas={"setinhas": False, "moldura": False}) == ""
    assert pedidos[-1]["seta"] is None and pedidos[-1]["moldura"] is None
    # Em azul: as setinhas (num arquivo à parte, que some depois) e a moldura.
    azul = edicao_video.CORES_DO_DESTAQUE["azul"]
    assert edicao_video.editar("v.mp4", _foto_jpg(), destino, escolhas={"cor": "azul"}) == ""
    assert pedidos[-1]["moldura"] == edicao_video.moldura_do_cartao(False, azul)
    assert azul in pedidos[-1]["cores"] and edicao_video.VERMELHO_DO_DESTAQUE not in pedidos[-1]["cores"]
    assert not os.path.exists(os.path.dirname(pedidos[-1]["seta"]))
    # Na cor do produto; sem ela (o produto vermelho), no vermelho de sempre.
    verde = edicao_video.CORES_DO_PRODUTO["verde"]
    assert edicao_video.editar("v.mp4", _foto_jpg(), destino, cor=verde, escolhas={"cor": "produto"}) == ""
    assert pedidos[-1]["moldura"] == edicao_video.moldura_do_cartao(False, verde)
    assert edicao_video.editar("v.mp4", _foto_jpg(), destino, escolhas={"cor": "produto"}) == ""
    assert pedidos[-1]["seta"] == edicao_video.SETA and pedidos[-1]["moldura"] == edicao_video.moldura_do_cartao()


def test_setinhas_na_cor_trocam_so_o_vermelho(tmp_path):
    # P192 1: o contorno branco, a sombra e a cascata (a setinha apagada) ficam como são.
    from PIL import Image, ImageSequence
    azul = edicao_video.CORES_DO_DESTAQUE["azul"]
    caminho = edicao_video.seta_na_cor(azul, str(tmp_path / "setas.apng"))
    assert edicao_video.seta_na_cor(edicao_video.VERMELHO_DO_DESTAQUE, "outro.apng") == edicao_video.SETA
    with Image.open(edicao_video.SETA) as original, Image.open(caminho) as nova:
        assert nova.n_frames == original.n_frames and nova.size == original.size
        for antes, depois in zip(ImageSequence.Iterator(original), ImageSequence.Iterator(nova)):
            antes, depois = antes.convert("RGBA"), depois.convert("RGBA")
            assert antes.getchannel("A").tobytes() == depois.getchannel("A").tobytes()
            for x in range(0, antes.width, 3):
                for y in range(0, antes.height, 3):
                    r, g, b, a = antes.getpixel((x, y))
                    if a == 255 and (r, g, b) == edicao_video.VERMELHO_DO_DESTAQUE:
                        assert depois.getpixel((x, y))[:3] == azul
                    elif a == 255 and min(r, g, b) > 240:
                        assert min(depois.getpixel((x, y))[:3]) > 240


def test_miniatura_a_esquerda_leva_os_textos_do_alto_para_a_direita_e_a_ia_olha_o_canto_dela():
    # P192 1: com a miniatura à esquerda, os textos do alto passam para a direita, e a IA confere o canto
    # da esquerda; a resposta sobre o canto da direita não vale para ela.
    letreiros, _textos = edicao_video._letreiros([("Bolsa de Palha", edicao_video.FUNDO_DOS_TEXTOS)], "alto", 10.0,
                                                 edicao_video.MINIATURA_A_ESQUERDA)
    imagem, _inicio, _fim, x, topo = letreiros[0]
    largura_do_texto = int.from_bytes(imagem[16:20], "big")
    margem, topo_do_alto = edicao_video.LUGARES_DOS_TEXTOS["alto"][:2]
    assert x + largura_do_texto == edicao_video.TELA[0] - margem and topo == topo_do_alto
    centro_x, _ = edicao_video.centro_da_miniatura(edicao_video.LARGURA_DA_MINIATURA, edicao_video.MINIATURA_A_ESQUERDA)
    assert x > centro_x + edicao_video.LARGURA_DA_MINIATURA // 2
    # À direita, o lugar de sempre.
    de_sempre = edicao_video._letreiros([("Bolsa de Palha", edicao_video.FUNDO_DOS_TEXTOS)], "alto", 10.0)[0][0]
    assert de_sempre[3] == margem
    pedido = edicao_video.prompt_dos_textos("Bolsa", edicao_video.MINIATURA_A_ESQUERDA)
    assert "o canto de cima à esquerda do vídeo (de uns 5% a 38% da largura" in pedido
    # A IA diz o alto dos dois lados (P213 1), e o "alto" dos nossos textos é o do lado oposto à miniatura.
    assert "\"alto_direita\" (no topo, à direita, a partir de uns 35% da largura" in pedido
    assert "E o mesmo do canto de cima à direita (de uns 62% a 95% da largura, na mesma altura)" in pedido
    lugares = {"lugares": ["alto_esquerda", "alto_direita", "meio"]}
    assert edicao_video.lugares_dos_textos(lugares, edicao_video.MINIATURA_A_ESQUERDA) == ["alto", "meio"]
    assert edicao_video.lugares_dos_textos(lugares) == ["alto", "meio"]
    assert edicao_video.lugares_dos_textos({"lugares": ["alto_direita"]}) == []
    assert "o canto de cima à direita do vídeo (de uns 62% a 95% da largura" in edicao_video.prompt_dos_textos("Bolsa")
    # A coisa do criador no canto da esquerda tira a miniatura da esquerda, não a da direita.
    no_canto_da_esquerda = {"canto_ocupado": False, "por_cima": [(8.0, 30.0, 10.0, 20.0)]}
    assert edicao_video.miniatura_no_video(no_canto_da_esquerda, edicao_video.MINIATURA_A_ESQUERDA) == 0
    assert edicao_video.miniatura_no_video(no_canto_da_esquerda) == edicao_video.LARGURA_DA_MINIATURA
    # O canto ocupado que a IA disse olhando o da direita não vale para a esquerda (e vice-versa).
    ocupado = {"canto_ocupado": True, "por_cima": []}
    assert edicao_video.miniatura_no_video(ocupado) == 0
    assert edicao_video.miniatura_no_video(ocupado, edicao_video.MINIATURA_A_ESQUERDA) == (
        edicao_video.LARGURA_DA_MINIATURA)
    ocupado["lado_olhado"] = edicao_video.MINIATURA_A_ESQUERDA
    assert edicao_video.miniatura_no_video(ocupado, edicao_video.MINIATURA_A_ESQUERDA) == 0
    assert edicao_video.miniatura_no_video(ocupado, edicao_video.SEM_MINIATURA) == 0


def test_textos_da_tela_olham_o_canto_do_lado_da_miniatura(monkeypatch):
    pedidos = []
    monkeypatch.setattr(edicao_video, "_resposta_da_ia", lambda video, prompt: pedidos.append(prompt) or {
        "nome": "Bolsa", "canto_ocupado": True, "por_cima_no_alto": []})
    monkeypatch.setattr(edicao_video, "_revisar_ortografia", lambda textos: textos)
    textos = edicao_video.textos_da_tela("v.mp4", "Bolsa", edicao_video.MINIATURA_A_ESQUERDA)
    assert textos["lado_olhado"] == edicao_video.MINIATURA_A_ESQUERDA
    # A 2ª pergunta, só do canto, é a do canto da esquerda.
    assert "canto de cima à esquerda" in pedidos[0] and "Olhe só o canto de cima à esquerda" in pedidos[1]
    # Sem a miniatura, nenhuma 2ª pergunta.
    pedidos.clear()
    textos = edicao_video.textos_da_tela("v.mp4", "Bolsa", edicao_video.SEM_MINIATURA)
    assert len(pedidos) == 1 and "lado_olhado" not in textos


def test_o_que_vai_ao_ar_segue_os_itens_do_painel(monkeypatch, tmp_path):
    # P192 1: os itens que o Rafael escolhe no painel valem para os próximos vídeos que vão ao ar, e o
    # jeito do registro diz o que mudou.
    import registro_processos as rp
    fala = [(0.5, 2.0, "Olha só essa bolsa")]
    lados = []
    monkeypatch.setattr(edicao_video, "textos_da_tela", lambda video, nome, lado="direita": lados.append(lado) or {
        "nome": "Bolsa", "vantagem": "Leve", "chamada": "Toque aqui", "lugar": "alto", "legendas": fala})
    recebidos = []

    def editar_2(video, foto, destino, nome="", vantagem="", chamada="", lugar=None, avisos=False, musica=None,
                 capa=None, miniatura=True, outras_fotos=(), legendas=(), rotulo_de_ia=False, cor=None, escolhas=None,
                 lugares=None, por_cima=()):
        recebidos.append({"miniatura": miniatura, "legendas": list(legendas), "escolhas": escolhas})
        return "", {"textos": [nome], "legendas": len(legendas)}
    monkeypatch.setattr(edicao_video, "editar_2", editar_2)
    destino = str(tmp_path / "r.mp4")
    inserir("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DAS_ESCOLHAS: {
        "miniatura": "sem", "legenda": False, "setinhas": False, "moldura": False, "cor": "azul"}})
    _motivo, como, _detalhe = edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa")
    assert lados == ["sem"] and recebidos[-1]["miniatura"] == 0 and recebidos[-1]["legendas"] == []
    assert recebidos[-1]["escolhas"]["cor"] == "azul" and not recebidos[-1]["escolhas"]["setinhas"]
    assert como == (edicao_video.COM_LEGENDAS + edicao_video.SEM_A_MINIATURA_PELO_PAINEL + edicao_video.SEM_AS_SETINHAS
                    + edicao_video.SEM_A_MOLDURA_DO_CARTAO)
    assert edicao_video.SEM_A_MINIATURA in como
    registro = rp.sequencia("shopee_video", edicao_video.PROCESSO_DAS_LEGENDAS, "2000-01-01 00:00:00")
    assert (registro[-1][2], registro[-1][3]) == ("sem as legendas", edicao_video.LEGENDAS_DESLIGADAS)
    # Sem a miniatura pelo painel, o canto dela não vai ao registro como "de fora".
    assert rp.sequencia("shopee_video", edicao_video.PROCESSO_DO_CANTO, "2000-01-01 00:00:00") == []
    # À esquerda, com a cor do produto nas setinhas e na moldura.
    db.salvar_config("shopee_video", {edicao_video.CHAVE_DAS_ESCOLHAS: {"miniatura": "esquerda", "cor": "produto"}})
    monkeypatch.setattr(edicao_video, "textos_da_tela", lambda video, nome, lado="direita": lados.append(lado) or {
        "nome": "Bolsa", "lugar": "alto", "legendas": fala, "cor": "verde"})
    _motivo, como, _detalhe = edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa")
    assert lados[-1] == "esquerda" and recebidos[-1]["miniatura"] == edicao_video.LARGURA_DA_MINIATURA
    assert recebidos[-1]["legendas"] and edicao_video.COM_A_MINIATURA_A_ESQUERDA in como
    assert como == (edicao_video.COM_LEGENDAS + edicao_video.COM_A_MINIATURA_A_ESQUERDA
                    + ", setinhas e moldura na cor do produto" + edicao_video.COM_AS_LEGENDAS_DA_FALA)


def test_o_editar_refaz_a_edicao_sem_a_ia_mudando_so_a_miniatura_e_a_legenda(monkeypatch, tmp_path):
    # Escolhas do Rafael (10/11, P191 1 e P192 1): o Editar ✏️ do rascunho refaz a edição com o que a IA já
    # disse (guardado pelo editar_para_postar), mudando só a miniatura e a legenda daquele vídeo.
    fala = [(0.5, 2.0, "Olha só essa bolsa")]
    _textos_da_tela(monkeypatch, {"nome": "Bolsa", "vantagem": "Leve", "chamada": "Toque aqui", "lugar": "alto",
                                  "legendas": fala, "cor": "azul", "por_cima": [(8.0, 30.0, 10.0, 20.0)]})
    recebidos = []

    def editar_2(video, foto, destino, nome="", vantagem="", chamada="", lugar=None, avisos=False, musica=None,
                 capa=None, miniatura=True, outras_fotos=(), legendas=(), rotulo_de_ia=False, cor=None, escolhas=None,
                 lugares=None, por_cima=()):
        recebidos.append({"nome": nome, "lugar": lugar, "musica": musica, "capa": capa, "miniatura": miniatura,
                          "outras": list(outras_fotos), "legendas": [legenda[:3] for legenda in legendas],
                          "rotulo": rotulo_de_ia, "cor": cor, "escolhas": escolhas})
        return "", {"textos": [nome], "legendas": len(legendas)}
    monkeypatch.setattr(edicao_video, "editar_2", editar_2)
    monkeypatch.setattr(edicao_video, "musicas_de_fundo", lambda video, quantas=1: [("calma", "/m/musica_calma.m4a")])
    monkeypatch.setattr(edicao_video, "_capa_da_vez", lambda foto, frase, no_video=False, cor=None, segunda=None:
                        f"{frase}|{no_video}".encode())
    monkeypatch.setattr(edicao_video, "capa_ligada", lambda: True)
    monkeypatch.setattr(edicao_video, "letras_da_foto", lambda foto: edicao_video.SEM_LETRAS)
    anotado = {}
    destino = str(tmp_path / "r.mp4")
    edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa", outras_fotos=[b"outra"], rotulo_de_ia=True,
                                    anotar=anotado)
    guardado = anotado["refazer"]
    # O que vai ao banco é JSON.
    import json
    guardado = json.loads(json.dumps(guardado))
    assert guardado["musica"] == "calma" and guardado["rotulo_de_ia"] and guardado["frase"]
    original = recebidos[-1]
    # Refazer sem mudar nada dá o mesmo vídeo: os mesmos textos, a mesma capa, a mesma música e a mesma miniatura.
    motivo, como = edicao_video.refazer_para_postar("v.mp4", b"foto", destino, guardado, [b"outra"])
    assert motivo == "" and recebidos[-1]["musica"].endswith("musica_calma.m4a")
    assert {k: v for k, v in recebidos[-1].items() if k != "musica"} == {k: v for k, v in original.items() if k != "musica"}
    assert como.startswith(edicao_video.COM_LEGENDAS) and edicao_video.COM_AS_LEGENDAS_DA_FALA in como
    # À esquerda e sem a legenda: o que o criador pôs no canto da esquerda tira a miniatura (P81 e P97).
    motivo, como = edicao_video.refazer_para_postar("v.mp4", b"foto", destino, guardado, [b"outra"],
                                                    edicao_video.MINIATURA_A_ESQUERDA, False)
    assert motivo == "" and recebidos[-1]["miniatura"] == 0 and recebidos[-1]["legendas"] == []
    assert recebidos[-1]["outras"] == [] and recebidos[-1]["escolhas"]["miniatura"] == "esquerda"
    assert not recebidos[-1]["escolhas"]["legenda"] and edicao_video.COM_AS_LEGENDAS_DA_FALA not in como
    # Sem a miniatura.
    edicao_video.refazer_para_postar("v.mp4", b"foto", destino, guardado, [], edicao_video.SEM_MINIATURA, True)
    assert recebidos[-1]["miniatura"] == 0 and recebidos[-1]["legendas"] == [(0.5, 2.0, "Olha só essa bolsa")]


# --- Os textos da tela desviam do que o criador pôs por cima (P212 1) e a miniatura vai ao outro canto (P213 1) ---

# No vídeo da garrafinha (19:37 de 12/11), o criador tinha frases no alto no começo e no fim, e o nome e a chamada
# ficaram em cima delas: o lugar único da IA valia para os 3 textos.
FRASE_NO_COMECO = (10.0, 60.0, 12.0, 19.0, 0.0, 2.0)
FRASE_NO_FIM = (10.0, 60.0, 12.0, 19.0, 9.0, 12.0)
QUADRO_NO_FIM = (15.0, 60.0, 26.0, 37.0, 9.0, 12.0)


def test_cada_texto_desvia_do_que_o_criador_pos_por_cima_no_momento_dele():
    # Escolha do Rafael (12/11, P212 1): cada texto nosso vai ao primeiro lugar livre (da lista da IA, do melhor para
    # o pior) do que o criador pôs por cima no momento em que o texto aparece; sem nenhum, só ele sai.
    textos = [("Garrafinha infantil", edicao_video.FUNDO_DOS_TEXTOS), ("Não vaza na mochila", edicao_video.FUNDO_DOS_TEXTOS),
              ("Garanta a sua aqui", edicao_video.FUNDO_DA_CHAMADA)]
    anotado = {}
    letreiros, postos = edicao_video._letreiros(textos, "alto", 12.0, edicao_video.MINIATURA_A_DIREITA, ["alto", "meio"],
                                                [FRASE_NO_COMECO, FRASE_NO_FIM, QUADRO_NO_FIM], anotado)
    # O nome (de 0,3 a 3,3 s) cruza a frase do começo no alto e vai ao meio; a vantagem (4,3 a 7,3 s) fica no alto;
    # a chamada (8,3 a 11,3 s) cruzaria a frase do fim no alto e o quadro no meio, e sai.
    assert postos == ["Garrafinha infantil", "Não vaza na mochila"] and anotado == {"mudaram": 1, "sairam": 1}
    alto, meio = edicao_video.LUGARES_DOS_TEXTOS["alto"][1], edicao_video.LUGARES_DOS_TEXTOS["meio"][1]
    assert [(inicio, y) for _imagem, inicio, _fim, _x, y in letreiros] == [(0.3, meio), (4.3, alto)]
    # Nenhum fica por cima de nada do criador no tempo dele.
    for imagem, inicio, fim, x, y in letreiros:
        largura, altura = _medidas(imagem)
        assert not edicao_video._cobre_o_criador((x, y, x + largura, y + altura), inicio, fim,
                                                 [FRASE_NO_COMECO, FRASE_NO_FIM, QUADRO_NO_FIM])
    # A folga do tempo: a frase que some 0,2 s antes do texto aparecer ainda conta (a IA acerta o tempo só mais ou
    # menos); a que some 0,5 s antes, não.
    caixa = (68, 150, 400, 230)
    assert edicao_video._cobre_o_criador(caixa, 2.2, 5.0, [FRASE_NO_COMECO])
    assert not edicao_video._cobre_o_criador(caixa, 2.5, 5.0, [FRASE_NO_COMECO])
    # Sem nada do criador, ou só com o que veio sem o tempo (os rascunhos de antes), todos no 1º lugar.
    for por_cima in ((), [FRASE_NO_COMECO[:4]]):
        anotado = {}
        letreiros, postos = edicao_video._letreiros(textos, "alto", 12.0, lugares=["alto", "meio"], por_cima=por_cima,
                                                    anotar=anotado)
        assert len(postos) == 3 and {y for *_resto, y in letreiros} == {alto} and anotado == {}
    # A lista vazia da IA (nenhum lugar livre do produto e do rosto, P47) não põe nenhum.
    assert edicao_video._letreiros(textos, "alto", 12.0, lugares=[]) == ([], [])


def test_a_ia_nao_recebe_os_momentos_e_os_textos_ficam_no_lugar_do_video_todo(monkeypatch):
    # Pedido do Rafael (13/11, à tarde): "a legenda de engajamento (legenda que fica ao lado da miniatura), nao
    # gostei de fazer ela mudar de posição, me arrependi, prefiro manter ela fixa msm". Os lugares de cada momento
    # (pedido da manhã de 13/11) saem: a IA não recebe os momentos dos nossos textos, a resposta que os traz não
    # muda o lugar nem fica guardada no rascunho, e os textos voltam ao lugar do vídeo todo (P212 1).
    import api_gemini
    pedidos = []

    async def analisar(video, prompt, imagens=None):
        pedidos.append(prompt)
        return ('{"nome": "Copo Térmico", "vantagem": "Mantém gelado", "chamada": "Toque aqui embaixo", '
                '"lugares": ["esquerda", "alto_esquerda"], '
                '"lugares_nos_momentos": [["alto_esquerda"], ["meio"], ["direita"]]}')

    monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)
    monkeypatch.setattr(edicao_video.videos, "duracao", lambda video, *a, **k: 12.0)
    textos = edicao_video.textos_da_tela("v.mp4", "Copo Térmico Inox 500 ml")
    assert pedidos and all("lugares_nos_momentos" not in p and "nestes momentos do vídeo" not in p for p in pedidos)
    assert "lugares_nos_momentos" not in textos and "lugares_nos_momentos" not in edicao_video.TEXTOS_GUARDADOS
    assert edicao_video.lugar_dos_textos(textos) == "esquerda"
    # Os 3 textos no mesmo lugar, um depois do outro, sem nada do criador por cima.
    caixa = edicao_video.FUNDO_DOS_TEXTOS
    letreiros, postos = edicao_video._letreiros(
        [(textos["nome"], caixa), (textos["vantagem"], caixa), (textos["chamada"], edicao_video.FUNDO_DA_CHAMADA)],
        "esquerda", 12.0, lugares=edicao_video.lugares_dos_textos(textos))
    assert len(postos) == 3 and len({(x, y) for _imagem, _inicio, _fim, x, y in letreiros}) == 1


def test_a_ia_diz_os_lugares_livres_e_onde_e_quando_o_criador_pos_coisa_por_cima():
    # P212 1: a IA diz a lista dos lugares livres do produto e do rosto (o alto dos dois lados, P213 1) e, de cada
    # coisa que o criador pôs por cima, onde e quando ela aparece.
    textos = edicao_video._nome_lugar_e_falas({
        "lugares": ["meio", "alto_esquerda", "meio", "embaixo", {"x": 1}], "outro_canto_ocupado": False,
        "por_cima_do_video": [
            {"esquerda": 10, "direita": 60, "topo": 12, "base": 19, "inicio": 0, "fim": 2},
            {"esquerda": 0.5, "direita": 0.1, "topo": 0.6, "base": 0.7},
            {"esquerda": 5, "direita": 9, "topo": 1, "base": 2, "inicio": 3, "fim": 1},
            {"esquerda": "x"}, "texto"]})
    assert textos["lugares"] == ["meio", "alto_esquerda"] and textos["outro_canto_ocupado"] is False
    # A que veio sem o tempo certo conta o vídeo inteiro.
    ate = edicao_video.ATE_O_FIM
    assert textos["por_cima"] == [(10.0, 60.0, 12.0, 19.0, 0.0, 2.0), (10.0, 50.0, 60.0, 70.0, 0.0, ate),
                                  (5.0, 9.0, 1.0, 2.0, 0.0, ate)]
    assert edicao_video.lugar_dos_textos(textos) == "meio"
    # Com a miniatura à esquerda, o alto da esquerda é dela: fica o meio.
    assert edicao_video.lugares_dos_textos(textos, edicao_video.MINIATURA_A_ESQUERDA) == ["meio"]
    # Nenhum lugar livre do produto e do rosto (P47): sem os textos.
    assert edicao_video.lugar_dos_textos(edicao_video._nome_lugar_e_falas({"lugares": []})) == edicao_video.SEM_LUGAR
    assert edicao_video.lugar_dos_textos({"lugares": ["alto_esquerda"]}, edicao_video.MINIATURA_A_ESQUERDA) == (
        edicao_video.SEM_LUGAR)
    # A lista só com nomes que não existem vale como sem a lista: o lugar único, se veio.
    assert edicao_video._nome_lugar_e_falas({"lugares": ["embaixo"], "lugar": "meio"}) == {"lugar": "meio"}
    # O texto próprio na maior parte do tempo (P52) continua tirando os nossos.
    assert edicao_video.lugar_dos_textos({"lugares": ["meio"], "texto_no_video": True}) == edicao_video.SEM_LUGAR
    # O que o Editar ✏️ guarda volta igual.
    guardado = edicao_video._textos_guardados(edicao_video.textos_para_guardar(textos))
    assert guardado["por_cima"] == textos["por_cima"] and guardado["lugares"] == textos["lugares"]
    assert guardado["outro_canto_ocupado"] is False


def test_o_que_vai_ao_ar_desvia_os_textos_e_o_registro_conta(monkeypatch, tmp_path):
    # P212 1 no que vai ao ar: o nome muda de lugar, a chamada sai, e o registro diz quantos.
    import registro_processos as rp
    montados, _editados = _versoes_de_mentira(monkeypatch)
    base = {"nome": "Garrafinha infantil", "vantagem": "Não vaza na mochila", "chamada": "Garanta a sua aqui",
            "lugares": ["alto_esquerda", "meio"], "canto_ocupado": False, "outro_canto_ocupado": False}
    _textos_da_tela(monkeypatch, dict(base, por_cima=[FRASE_NO_COMECO, FRASE_NO_FIM, QUADRO_NO_FIM]))
    destino = str(tmp_path / "rascunho.mp4")
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Garrafa") == (
        "", edicao_video.COM_LEGENDAS, "")
    assert montados[-1][1] == 2
    registro = rp.sequencia("shopee_video", edicao_video.PROCESSO_DO_TEXTO_DO_CRIADOR, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in registro] == [("algum saiu", "1 em outro lugar, 1 fora (sem lugar livre na hora dele)")]
    # O registro diz também, em todo vídeo, se a IA respondeu com a lista e com o tempo das coisas do criador.
    registro = rp.sequencia("shopee_video", edicao_video.PROCESSO_DOS_LUGARES, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in registro] == [(edicao_video.COM_A_LISTA, edicao_video.COM_O_TEMPO)]
    # Com o criador por cima dos dois lugares o vídeo todo, nenhum texto entra, e o detalhe diz por quê.
    tudo = [caixa[:4] + (0.0, 12.0) for caixa in (FRASE_NO_COMECO, QUADRO_NO_FIM)]
    _textos_da_tela(monkeypatch, dict(base, por_cima=tudo))
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Garrafa") == (
        "", edicao_video.SEM_LEGENDAS_NA_TELA, edicao_video.SEM_LUGAR_PELO_CRIADOR)
    # Sem nada do criador por cima, nada é anotado.
    _textos_da_tela(monkeypatch, base)
    edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Garrafa")
    assert len(rp.sequencia("shopee_video", edicao_video.PROCESSO_DO_TEXTO_DO_CRIADOR, "2000-01-01 00:00:00")) == 2
    assert montados[-1][1] == 3
    registro = rp.sequencia("shopee_video", edicao_video.PROCESSO_DOS_LUGARES, "2000-01-01 00:00:00")
    assert (registro[-1][2], registro[-1][3]) == (edicao_video.COM_A_LISTA, edicao_video.NADA_DO_CRIADOR)
    # A resposta só com o lugar único (sem a lista) e as coisas do criador sem o tempo também ficam no registro.
    _textos_da_tela(monkeypatch, {"nome": "Garrafinha infantil", "lugar": "alto", "por_cima": [FRASE_NO_COMECO[:4]]})
    edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Garrafa")
    registro = rp.sequencia("shopee_video", edicao_video.PROCESSO_DOS_LUGARES, "2000-01-01 00:00:00")
    assert (registro[-1][2], registro[-1][3]) == (edicao_video.SEM_A_LISTA, edicao_video.SEM_O_TEMPO)


# A cor do produto que o criador pôs no canto de cima à direita, o vídeo todo (P213 1).
CORES_NO_CANTO_DA_DIREITA = (70.0, 95.0, 10.0, 20.0, 0.0, 30.0)


def test_a_miniatura_vai_para_o_outro_canto_de_cima_quando_o_dela_tem_coisa_do_criador(monkeypatch):
    # Escolha do Rafael (12/11, P213 1): com coisa do criador no canto da miniatura, ela vai inteira para o outro
    # canto de cima, quando a IA diz que ele está livre e a pergunta só sobre ele confirma; senão, fica como antes
    # (diminui ou sai, P81 e P97).
    perguntas, respostas = [], []
    monkeypatch.setattr(edicao_video, "_resposta_da_ia", lambda video, prompt: perguntas.append(prompt) or respostas.pop(0))
    direita, esquerda = edicao_video.MINIATURA_A_DIREITA, edicao_video.MINIATURA_A_ESQUERDA
    ocupado = {"canto_ocupado": True, "outro_canto_ocupado": False, "por_cima": [CORES_NO_CANTO_DA_DIREITA]}
    respostas.append({"por_cima_na_edicao": False})
    textos = dict(ocupado)
    assert edicao_video.canto_da_miniatura("v.mp4", textos, direita) == esquerda and "outro_canto" not in textos
    assert "canto de cima à esquerda" in perguntas[-1] and "da borda até uns 45%" in perguntas[-1]
    # No outro canto, ela cabe inteira: nada do criador passa por ela lá.
    assert edicao_video.miniatura_no_video(textos, esquerda) == edicao_video.LARGURA_DA_MINIATURA
    # A pergunta só sobre o outro canto viu coisa do criador, ou não respondeu: fica no do painel.
    for resposta, porque in (({"por_cima_na_edicao": True}, edicao_video.OUTRO_CANTO_NA_2A_PERGUNTA),
                             ({}, edicao_video.OUTRO_CANTO_SEM_A_2A)):
        respostas.append(resposta)
        textos = dict(ocupado)
        assert edicao_video.canto_da_miniatura("v.mp4", textos, direita) == direita and textos["outro_canto"] == porque
    # Sem perguntar de novo: o outro canto ocupado, coisa do criador passando pela miniatura lá, a IA sem dizer do
    # outro canto, o canto do painel livre, sem a miniatura ou sem a resposta da IA.
    perguntas.clear()
    no_canto_da_esquerda = (8.0, 30.0, 10.0, 20.0, 0.0, 30.0)
    for textos, lado, porque in (
            (dict(ocupado, outro_canto_ocupado=True), direita, edicao_video.OUTRO_CANTO_OCUPADO),
            (dict(ocupado, por_cima=[CORES_NO_CANTO_DA_DIREITA, no_canto_da_esquerda]), direita,
             edicao_video.OUTRO_CANTO_OCUPADO),
            ({"canto_ocupado": True}, direita, edicao_video.OUTRO_CANTO_SEM_RESPOSTA),
            ({"canto_ocupado": False, "outro_canto_ocupado": False}, direita, None),
            (dict(ocupado), edicao_video.SEM_MINIATURA, None), ({}, direita, None)):
        assert edicao_video.canto_da_miniatura("v.mp4", textos, lado) == lado and textos.get("outro_canto") == porque
    assert perguntas == []
    # Com a miniatura à esquerda no painel, o outro canto é o da direita.
    respostas.append({"por_cima_na_edicao": False})
    textos = {"canto_ocupado": True, "outro_canto_ocupado": False, "lado_olhado": esquerda,
              "por_cima": [no_canto_da_esquerda]}
    assert edicao_video.canto_da_miniatura("v.mp4", textos, esquerda) == direita
    assert "canto de cima à direita" in perguntas[-1]
    # O outro_canto_ocupado vale só para o outro canto: dito sem onde, a miniatura não vai para lá (P81).
    assert edicao_video.miniatura_no_video({"outro_canto_ocupado": True}, esquerda) == 0
    assert edicao_video.miniatura_no_video({"outro_canto_ocupado": True}) == edicao_video.LARGURA_DA_MINIATURA


def test_no_outro_canto_os_textos_do_alto_trocam_de_lado_e_o_editar_guarda_o_canto(monkeypatch, tmp_path):
    # P213 1 no que vai ao ar: a miniatura vai ao canto da esquerda, os nossos textos do alto vão para a direita, o
    # jeito e o registro dizem, e o Editar ✏️ guarda o canto em que ela saiu.
    import registro_processos as rp
    _versoes_de_mentira(monkeypatch)
    _textos_da_tela(monkeypatch, {"nome": "Garrafa", "vantagem": "Leve", "chamada": "Toque aqui",
                                  "lugares": ["alto_esquerda", "alto_direita", "meio"], "canto_ocupado": True,
                                  "outro_canto_ocupado": False, "por_cima": [CORES_NO_CANTO_DA_DIREITA]})
    perguntas = []
    monkeypatch.setattr(edicao_video, "_resposta_da_ia",
                        lambda video, prompt: perguntas.append(prompt) or {"por_cima_na_edicao": False})
    recebidos = []

    def editar_2(video, foto, destino, nome="", vantagem="", chamada="", lugar=None, avisos=False, musica=None,
                 capa=None, miniatura=True, outras_fotos=(), legendas=(), rotulo_de_ia=False, cor=None, escolhas=None,
                 lugares=None, por_cima=()):
        recebidos.append({"lugar": lugar, "lugares": lugares, "por_cima": list(por_cima), "miniatura": miniatura,
                          "lado": escolhas["miniatura"]})
        return "", {"textos": [nome], "legendas": 0}
    monkeypatch.setattr(edicao_video, "editar_2", editar_2)
    anotado = {}
    destino = str(tmp_path / "rascunho.mp4")
    motivo, como, _detalhe = edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Garrafa", anotar=anotado,
                                                             escolhas=edicao_video.ESCOLHAS_PADRAO)
    assert motivo == "" and len(perguntas) == 1
    assert recebidos[-1] == {"lugar": "alto", "lugares": ["alto", "meio"], "por_cima": [CORES_NO_CANTO_DA_DIREITA],
                             "miniatura": edicao_video.LARGURA_DA_MINIATURA, "lado": edicao_video.MINIATURA_A_ESQUERDA}
    assert edicao_video.COM_A_MINIATURA_NO_OUTRO_CANTO in como and edicao_video.COM_A_MINIATURA_A_ESQUERDA not in como
    registro = rp.sequencia("shopee_video", edicao_video.PROCESSO_DO_CANTO, "2000-01-01 00:00:00")
    assert [(r[2], r[3]) for r in registro] == [
        (edicao_video.MINIATURA_NO_OUTRO_CANTO, "o do painel: a coisa do criador no alto começa a 10% da altura")]
    # O "alto" com a miniatura à esquerda é o da direita, ao lado dela.
    letreiros, _postos = edicao_video._letreiros([("Garrafa", edicao_video.FUNDO_DOS_TEXTOS)], "alto", 10.0,
                                                 edicao_video.MINIATURA_A_ESQUERDA, ["alto"])
    imagem, _inicio, _fim, x, _y = letreiros[0]
    assert x + _medidas(imagem)[0] == edicao_video.TELA[0] - edicao_video.LUGARES_DOS_TEXTOS["alto"][0]
    # O Editar ✏️ refaz no canto guardado, sem perguntar à IA; o lado que o Rafael escolhe nele vale como escolhido.
    import json
    guardado = json.loads(json.dumps(anotado["refazer"]))
    assert guardado["escolhas"]["miniatura"] == edicao_video.MINIATURA_A_ESQUERDA
    perguntas.clear()
    assert edicao_video.refazer_para_postar("v.mp4", b"foto", destino, guardado)[0] == ""
    assert recebidos[-1] == recebidos[0] and perguntas == []
    assert edicao_video.refazer_para_postar("v.mp4", b"foto", destino, guardado, lado=edicao_video.MINIATURA_A_DIREITA,
                                            legenda=False)[0] == ""
    assert recebidos[-1]["lado"] == edicao_video.MINIATURA_A_DIREITA and recebidos[-1]["miniatura"] == 0
    assert recebidos[-1]["lugares"] == ["alto", "meio"] and perguntas == []

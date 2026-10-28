"""edicao_video e videos.com_foto_e_miniatura: a foto do produto no começo, a miniatura no canto e a seta do Rafael, com o ffmpeg de mentira (e de verdade, quando a máquina tem)."""
import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest

import db
import edicao_video
from conftest import inserir


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
    # Vídeo do Rafael (25/10): a miniatura com 25% da largura no canto de cima à direita
    # (posição X 60 e Y -80 no LumaFusion) e a seta dele embaixo à esquerda, até o fim.
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
    assert f"-t {edicao_video.SEGUNDOS_DA_FOTO}" in " ".join(ffmpeg) and "scale=180:-2" in filtro
    assert "overlay=x=576-w/2:y=128-h/2:shortest=1" in filtro
    # A seta entra só no vídeo, logo depois da foto (pedido do Rafael, 25/10), e o pulso do fim
    # do arquivo (quadros 72 a 101) se repete até o fim.
    assert "[3:v]loop=loop=-1:size=30:start=72[seta]" in filtro
    assert "[comfoto][seta]overlay=x=142-w/2:y=846-h/2:shortest=1,format=yuv420p[editado]" in filtro
    assert "[foto][editado]concat=n=2:v=1:a=0[v]" in filtro
    entradas = [ffmpeg[i + 1] for i, parte in enumerate(ffmpeg) if parte == "-i"]
    assert entradas[3] == edicao_video.SETA
    # Com som: o áudio do vídeo começa depois da foto, que vai em silêncio.
    assert "[4:a][som]concat=n=2:v=0:a=1[a]" in filtro and "[a]" in ffmpeg
    # Só o vídeo editado fica na pasta do rascunho.
    assert os.listdir(pasta) == ["rascunho.mp4"]


def test_a_seta_e_a_do_rafael_sem_fundo_com_a_entrada_e_um_pulso():
    # Pedido do Rafael (25/10): a seta do arquivo dele, sem o fundo preto.
    from PIL import Image
    with Image.open(edicao_video.SETA) as arquivo:
        assert arquivo.format == "PNG" and arquivo.mode == "RGBA"
        inicio, quadros = edicao_video.PULSO_DA_SETA
        assert arquivo.n_frames == inicio + quadros and arquivo.info.get("duration") == 40   # 25 por segundo
        arquivo.seek(0)
        primeiro = arquivo.copy()
        arquivo.seek(inicio + quadros // 2)
        pulso = arquivo.copy()
    # O primeiro quadro já é o começo do desenho (a seta aparece logo depois da foto, sem
    # espera); no pulso ela é vermelha, num fundo todo transparente.
    largura, altura = pulso.size
    pixels = [pulso.getpixel((x, y)) for x in range(largura) for y in range(altura)]
    comeco = [primeiro.getpixel((x, y))[3] for x in range(largura) for y in range(altura)]
    assert 0 < sum(1 for a in comeco if a) < len(pixels) * 0.02
    vermelhos = [p for p in pixels if p[3] == 255 and p[0] > 180 and p[1] < 40 and p[2] < 40]
    transparentes = [p for p in pixels if p[3] == 0]
    assert len(vermelhos) > len(pixels) * 0.1 and len(transparentes) > len(pixels) * 0.4
    # Nada escuro e opaco: o preto do fundo saiu, e a borda não fica com contorno escuro.
    assert not [p for p in pixels if p[3] > 60 and max(p[:3]) < 120]
    # O canto de baixo à direita tem a ponta; os cantos de cima e o de baixo à esquerda ficam vazios.
    assert any(pulso.getpixel((x, y))[3] == 255 for x in range(largura * 2 // 3, largura)
               for y in range(altura // 2, altura))
    for cantos in ((0, 0), (largura - 10, 0), (0, altura - 10)):
        assert all(pulso.getpixel((cantos[0] + x, cantos[1] + y))[3] == 0 for x in range(10) for y in range(10))
    assert os.path.getsize(edicao_video.SETA) < 1024 * 1024


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
        vermelhos = [p for p in recorte if p[0] > 150 and p[1] < 70 and p[2] < 70]
        escuros = [p for p in recorte if max(p) < 90]
        return len(vermelhos) / len(recorte), escuros

    # Na foto (os 2 primeiros segundos), nada de seta; ela começa a se desenhar com o vídeo.
    assert onde_fica_a_seta(1.9) == (0, [])
    vermelho, escuros = onde_fica_a_seta(2.6)
    assert vermelho > 0 and not escuros
    # 7,5 s: depois do fim do arquivo da seta, já no pulso repetido.
    vermelho, escuros = onde_fica_a_seta(7.5)
    assert vermelho > 0.05 and not escuros



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
    assert edicao_video.editar(str(tmp_path / "v.mp4"), _foto_jpg(), str(destino)) == ""
    ffmpeg = [c for c in comandos if c[0] == "ffmpeg"][0]
    assert ffmpeg[ffmpeg.index("-i") + 1].endswith("foto.jpg")


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
    horarios = edicao_video.horarios_dos_textos(["nome", "vantagem", "preço"], 12)
    assert [t for t, *_ in horarios] == ["nome", "vantagem", "preço"]
    assert all(fim - inicio <= edicao_video.SEGUNDOS_DE_CADA_TEXTO for _, inicio, fim in horarios)
    assert all(horarios[i][2] < horarios[i + 1][1] for i in range(2)) and horarios[-1][2] <= 12
    # Vídeo curto: cada texto precisa de 1,5 s; o do fim sai primeiro.
    assert [t for t, *_ in edicao_video.horarios_dos_textos(["nome", "vantagem", "preço"], 4)] == ["nome", "vantagem"]
    assert edicao_video.horarios_dos_textos(["nome"], 1) == []


def test_preco_a_partir_de_numa_linha_so_com_o_numero():
    # "A partir de": o anúncio pode ter variações de preço (regra 14, informação errada).
    assert edicao_video.texto_do_preco(39.9) == "A\u00a0partir\u00a0de R$\u00a039,90"
    assert edicao_video.texto_do_preco(0) == edicao_video.texto_do_preco(None) == ""
    import io

    from PIL import Image
    with Image.open(io.BytesIO(edicao_video.letreiro(edicao_video.texto_do_preco(1299.9),
                                                     edicao_video.FUNDO_DO_PRECO))) as imagem:
        # Duas linhas ("A partir de" e o preço), dentro da tela e com o fundo transparente.
        assert imagem.mode == "RGBA" and imagem.width <= 720 and 100 < imagem.height < 200
        assert imagem.getpixel((0, 0))[3] == 0 and imagem.getpixel((imagem.width // 2, 8))[3] > 150


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
    motivo, resumo = edicao_video.editar_2(str(video), _foto_jpg(), str(destino), "Copo Térmico", "", 39.9,
                                           lugar="meio")
    assert motivo == ""
    # Nada sai: o vídeo inteiro, mais a foto no começo.
    assert abs(edicao_video.videos.duracao(str(destino)) - (15 + edicao_video.SEGUNDOS_DA_FOTO)) < 0.3
    assert edicao_video.videos.tem_audio(str(destino))
    assert resumo["textos"] == ["Copo Térmico", "A\u00a0partir\u00a0de R$\u00a039,90"]
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
    # O nome logo depois da foto (caixa escura) e o preço na 2ª metade (caixa laranja).
    assert max(ponto(3.0, caixa)) < 80
    vermelho, verde, azul = ponto(11.0, caixa)
    assert vermelho > 180 and verde < 120 and azul < 100
    # Sem o lugar da IA, o texto vai no padrão: no alto, à esquerda, ao lado da miniatura (P46).
    motivo, resumo = edicao_video.editar_2(str(video), _foto_jpg(), str(destino), "Copo", "", None)
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


def test_exemplos_dos_dois_editores_tem_a_lista_propria_e_o_preco_da_api(monkeypatch, tmp_path):
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
        "nome": "Copo Térmico", "vantagem": "Gelado o dia todo", "versoes": versoes, "falas": [], "lugar": "meio"})
    pedidos = []

    def editar_1_e_versoes(video, foto, destino, versoes_da_ia=(), falas=None):
        pedidos.append((1, video, list(versoes_da_ia), falas))
        return "", {"versoes": []}

    def editar_2_e_versoes(video, foto, destino, nome="", vantagem="", versoes_da_ia=(), preco=None, falas=None,
                           lugar=None):
        pedidos.append((2, video, nome, vantagem, list(versoes_da_ia), preco, lugar))
        return "", {"versoes": []}

    monkeypatch.setattr(edicao_video, "editar_1_e_versoes", editar_1_e_versoes)
    monkeypatch.setattr(edicao_video, "editar_2_e_versoes", editar_2_e_versoes)
    nome, motivo, resumo = edicao_video.exemplo_editor_1("exemplo.mp4")
    assert (nome, motivo) == ("Copo Térmico", "") and resumo["versoes_da_ia"] == 1 and resumo["lugar_da_ia"]
    nome, motivo, resumo = edicao_video.exemplo_editor_2("exemplo.mp4")
    # O Editor 1 já mostrou o v1; o Editor 2 tem a lista dele e começa pelo v1 também.
    assert (nome, motivo) == ("Copo Térmico", "") and resumo["textos_da_ia"]
    assert pedidos == [(1, videos["v1"], versoes, []),
                       (2, videos["v1"], "Copo Térmico", "Gelado o dia todo", versoes, 39.9, "meio")]
    dados = db.ler_config(edicao_video.CHAVE_EXEMPLOS, {})
    assert dados["ids"] == ["viral:1"] and dados["ids_2"] == ["viral:1"]
    edicao_video.exemplo_editor_2("exemplo.mp4")
    assert pedidos[-1][1] == videos["v2"]
    # Escolha do Rafael (P52): o vídeo que já tem texto próprio na tela vai sem as nossas legendas.
    monkeypatch.setattr(edicao_video, "textos_das_versoes", lambda video, nome: {
        "nome": "Presilha", "vantagem": "Firme", "versoes": versoes, "falas": [], "lugar": "alto",
        "texto_no_video": True})
    _, _, resumo = edicao_video.exemplo_editor_2("exemplo.mp4")
    assert pedidos[-1][-1] == edicao_video.SEM_LUGAR and resumo["texto_no_video"]


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
    # no alto ela cabe à esquerda da miniatura (que começa em x 486).
    import io

    from PIL import Image
    for texto in ("Confortável e cheio de estilo", "Cintura alta e ótima modelagem", "Aparador Buffet Retrô",
                  "Mantém a bebida gelada por 24 horas", edicao_video.texto_do_preco(1299.9)):
        for lugar, (x, topo, largura, linhas) in edicao_video.LUGARES_DOS_TEXTOS.items():
            with Image.open(io.BytesIO(edicao_video.letreiro(texto, largura_maxima=largura,
                                                             linhas_maximas=linhas))) as imagem:
                assert imagem.width * imagem.height <= 0.08 * 720 * 1280, (texto, lugar)
                if lugar == "alto":
                    assert x + imagem.width < 486 - 10 and topo + imagem.height < 280
                if lugar in ("esquerda", "direita"):
                    # Nos lados (P47): estreita, longe do meio da tela, acima da seta (que
                    # começa em y 776) e dos botões do app à direita.
                    assert imagem.width <= 0.34 * 720 and topo + imagem.height < 740, (texto, lugar)
                    if texto.startswith("A\u00a0partir"):
                        # O preço em 2 linhas: "A partir de" e o valor, sem quebrar por dentro.
                        assert imagem.height < 3 * round(28 * 1.25) + 2 * 18


def test_editor_2_nos_lados_e_sem_lugar_livre_sem_texto(monkeypatch, tmp_path):
    # Escolha do Rafael (P47, 27/10): no vídeo do conjunto, o alto cobriu o rosto da modelo e
    # o meio cobriria o conjunto. A IA ganha os lados e, sem lugar livre, o vídeo vai sem texto.
    monkeypatch.setattr(edicao_video.videos, "duracao", lambda video, timeout=30: 12.0)
    monkeypatch.setattr(edicao_video.videos, "movimento", lambda video, por_segundo=10, timeout=120: [5.0] * 120)
    monkeypatch.setattr(edicao_video, "editar", lambda video, foto, destino, avisos=False, musica=None: "")
    montados = []

    def com_cortes_e_ritmo(video, trechos, destino, letreiros=(), espera=300):
        montados.append(list(letreiros))
        return ""
    monkeypatch.setattr(edicao_video.videos, "com_cortes_e_ritmo", com_cortes_e_ritmo)
    destino = str(tmp_path / "r.mp4")

    motivo, resumo = edicao_video.editar_2("v.mp4", b"foto", destino, "Conjunto Corset e Saia", "Modelo elegante",
                                           50.99, lugar="nenhum")
    # Sem texto, o vídeo vai direto ao Editor 1, sem passar pelo ffmpeg dos textos.
    assert motivo == "" and montados == [] and resumo["textos"] == [] and resumo["lugar"] == "nenhum"

    edicao_video.editar_2("v.mp4", b"foto", destino, "Conjunto Corset e Saia", "", 50.99, lugar="esquerda")
    assert [(x, topo) for _, _, _, x, topo in montados[-1]] == [(16, 400), (16, 400)]

    edicao_video.editar_2("v.mp4", b"foto", destino, "Conjunto Corset e Saia", "", 50.99, lugar="direita")
    for imagem, _, _, x, topo in montados[-1]:
        # Encostado na direita: a caixa termina a 16 px da borda.
        assert topo == 400 and x + int.from_bytes(imagem[16:20], "big") == 720 - 16


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

    def editar(video, foto, destino, avisos=False, musica=None):
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
                                    VERSOES_DA_IA, 25.8, falas=[], lugar="alto")
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
                                           "Leve e resistente", VERSOES_DA_IA, 25.8, falas=[], lugar="alto")
    assert motivo == "" and [e[1] for e in editados] == ["exemplo_1.mp4", "exemplo_2.mp4", "exemplo_3.mp4"]
    # O 1º é o vídeo inteiro, numa parte só e na velocidade dele, com os 3 textos.
    assert montados[0] == ([(0.0, 12.0, 1.0)], 3)
    # As versões são remontadas (o trecho calmo acelerado) e abrem no seu momento.
    assert [m[0][0] for m in montados[1:]] == [(9.0, 12.0, 1.0), (4.5, 8.0, edicao_video.ACELERADO)]
    assert [m[1] for m in montados[1:]] == [4, 4]
    # Até uns 3/4 e 1/2 do vídeo original (12 s), nunca menos de 8 s.
    assert [edicao_video._segundos_remontados(m[0]) for m in montados[1:]] == [
        pytest.approx(9.0), pytest.approx(edicao_video.MINIMO_DO_REMONTADO)]
    completo, segunda, terceira = resumo["versoes"]
    assert resumo["inteiro"] == 12.0 and completo["remontado"] == 12.0
    # O que a remontagem muda nas versões, para a legenda delas.
    assert resumo["remontagem"]["acelerados"] == 1 and resumo["remontagem"]["cortado"] == 0
    preco = edicao_video.texto_do_preco(25.8)
    assert completo["gancho"] is None and completo["textos"] == ["Bolsa de Palha", "Leve e resistente", preco]
    # Nas versões, a vantagem do gancho abre e a chamada fecha.
    assert segunda["textos"] == ["Fechamento com zíper", "Bolsa de Palha", preco, "Toque no produto"]
    assert terceira["textos"][0] == "Várias cores" and terceira["textos"][-1] == "Escolha a sua"
    assert segunda["gancho"] == (9.0, 10.5) and segunda["curta"] and not completo["curta"]
    # Sem lugar livre (P47), todos vão sem os textos.
    montados.clear()
    _, resumo = edicao_video.editar_2_e_versoes("v.mp4", b"foto", str(tmp_path / "exemplo.mp4"), "Bolsa", "Leve",
                                      VERSOES_DA_IA, 25.8, falas=[], lugar="nenhum")
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
    pedidos = _textos_da_tela(monkeypatch, {"nome": "Bolsa de Palha", "vantagem": "Leve e resistente", "falas": [],
                                            "lugar": "alto"})
    destino = str(tmp_path / "rascunho.mp4")
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa Palha Marca X", 25.8) == (
        "", edicao_video.COM_LEGENDAS, "")
    # Um vídeo só: a remontagem inteira com o nome, a vantagem e o preço, e o Editor 1 por cima.
    assert pedidos == ["Bolsa Palha Marca X"]
    # O vídeo original inteiro, sem cortes nem mudança de velocidade (pedido do Rafael, 28/10).
    assert montados == [([(0.0, 12.0, 1.0)], 3)]
    assert editados == [("com_textos.mp4", "rascunho.mp4")]
    # Sem lugar livre do produto e do rosto (P47), o Editor 2 vai sem os textos, e o registro diz por quê.
    _textos_da_tela(monkeypatch, {"nome": "Bolsa de Palha", "vantagem": "Leve", "falas": [], "lugar": "nenhum"})
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa", 25.8) == (
        "", edicao_video.SEM_LEGENDAS_NA_TELA, edicao_video.SEM_LUGAR_LIVRE)
    # Escolha do Rafael (P52): o vídeo que já tem texto próprio na tela vai sem as nossas legendas.
    montados.clear()
    _textos_da_tela(monkeypatch, {"nome": "Presilha", "vantagem": "Firme", "lugar": "alto", "texto_no_video": True})
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Presilha", 20.93) == (
        "", edicao_video.SEM_LEGENDAS_NA_TELA, edicao_video.TEXTO_JA_NO_VIDEO)
    assert montados == []
    # Sem a resposta da IA, só o preço na tela.
    _textos_da_tela(monkeypatch, {})
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa", 25.8) == (
        "", edicao_video.COM_LEGENDAS, edicao_video.SEM_OS_TEXTOS_DA_IA)
    assert montados[0][1] == 1


def test_sem_o_editor_2_o_que_vai_ao_ar_e_o_editor_1(monkeypatch, tmp_path):
    # Escolha do Rafael (28/10, P51): se o Editor 2 não sai, o vídeo vai com o Editor 1 (foto,
    # miniatura e seta, sem legendas), e o detalhe diz por quê.
    montados, editados = _versoes_de_mentira(monkeypatch)
    _textos_da_tela(monkeypatch, {"nome": "Bolsa", "vantagem": "Leve", "falas": [], "lugar": "alto"})
    monkeypatch.setattr(edicao_video.videos, "com_cortes_e_ritmo",
                        lambda video, trechos, destino, letreiros=(), espera=300: "o ffmpeg falhou")
    destino = str(tmp_path / "rascunho.mp4")
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa", 25.8) == (
        "", edicao_video.SO_COM_O_EDITOR_1, "o Editor 2 não saiu: o ffmpeg falhou")
    assert editados == [("v.mp4", "rascunho.mp4")]

    # Um erro no meio do Editor 2 também.
    def quebra(*args, **kwargs):
        raise RuntimeError("quebrou")
    monkeypatch.setattr(edicao_video, "editar_2", quebra)
    editados.clear()
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa", 25.8) == (
        "", edicao_video.SO_COM_O_EDITOR_1, "o Editor 2 não saiu: erro (RuntimeError)")
    assert editados == [("v.mp4", "rascunho.mp4")]


def test_sem_a_foto_nada_vai_ao_ar_e_a_ia_nem_e_chamada(monkeypatch, tmp_path):
    _programas(monkeypatch)
    pedidos = _textos_da_tela(monkeypatch, {"nome": "Bolsa"})
    motivo, _, _ = edicao_video.editar_para_postar("v.mp4", None, str(tmp_path / "r.mp4"), "Bolsa", 25.8)
    assert motivo == "a foto do anúncio não veio" and pedidos == [] and not os.path.exists(tmp_path / "r.mp4")


def test_bebida_alcoolica_vai_ao_ar_com_os_avisos_no_editor_2_e_no_editor_1(monkeypatch, tmp_path):
    # Escolha do Rafael (26/10, P43): a capa com os avisos abre o vídeo, com o Editor 2 também.
    _versoes_de_mentira(monkeypatch)
    _textos_da_tela(monkeypatch, {"nome": "Vinho Tinto", "vantagem": "Encorpado", "falas": [], "lugar": "alto"})
    avisos = []

    def editar(video, foto, destino, com_avisos=False, musica=None):
        avisos.append(com_avisos)
        return ""
    monkeypatch.setattr(edicao_video, "editar", editar)
    destino = str(tmp_path / "r.mp4")
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Vinho", 39.9, avisos=True)[1] == (
        edicao_video.COM_LEGENDAS + edicao_video.COM_OS_AVISOS)
    monkeypatch.setattr(edicao_video.videos, "com_cortes_e_ritmo",
                        lambda video, trechos, destino, letreiros=(), espera=300: "o ffmpeg falhou")
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Vinho", 39.9, avisos=True)[1] == (
        edicao_video.SO_COM_O_EDITOR_1 + edicao_video.COM_OS_AVISOS)
    assert avisos == [True, True]


def test_textos_da_tela_pede_so_o_do_video_completo(monkeypatch):
    import api_gemini
    pedidos = []

    async def analisar(video, prompt, imagens=None):
        pedidos.append(prompt)
        return ('{"nome": "Copo Térmico", "vantagem": "Mantém gelado 🧊", "lugar": "meio", '
                '"texto_no_video": true}')

    monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)
    textos = edicao_video.textos_da_tela("v.mp4", "Copo Marca X")
    assert textos == {"nome": "Copo Térmico", "vantagem": "Mantém gelado", "lugar": "meio", "texto_no_video": True}
    assert "Copo Marca X" in pedidos[0] and "versoes" not in pedidos[0] and "texto_no_video" in pedidos[0]
    # O vídeo com texto próprio na tela fica sem lugar para as nossas legendas (P52).
    assert edicao_video.lugar_dos_textos(textos) == edicao_video.SEM_LUGAR
    assert edicao_video.lugar_dos_textos({"lugar": "meio", "texto_no_video": False}) == "meio"


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
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa", 25.8) == (
        "", edicao_video.COM_LEGENDAS + edicao_video.COM_MUSICA, "")
    assert musicas == ["musica_animada.m4a"]
    # Com som, nada muda.
    monkeypatch.setattr(edicao_video.videos, "mudo", lambda video: False)
    assert edicao_video.editar_para_postar("v.mp4", b"foto", destino, "Bolsa", 25.8)[1] == edicao_video.COM_LEGENDAS
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
                                                VERSOES_DA_IA, 25.8, falas=[], lugar="alto")
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

"""edicao_video e videos.com_foto_e_miniatura: a foto do produto no começo, a miniatura no canto e a seta do Rafael, com o ffmpeg de mentira (e de verdade, quando a máquina tem)."""
import os
import shutil
import subprocess
from types import SimpleNamespace

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


def test_exemplo_usa_o_proximo_video_do_robo_com_arquivo_link_e_foto(monkeypatch, tmp_path):
    sem_arquivo, com_foto = str(tmp_path / "sumiu.mp4"), str(tmp_path / "a.mp4")
    open(com_foto, "wb").close()
    editados = _fontes_de_mentira(monkeypatch, {"autorais": [
        ("1", sem_arquivo, "https://s.shopee.com.br/a", ""), ("2", com_foto, None, ""),
        ("3", com_foto, "https://s.shopee.com.br/sem-foto", ""), ("4", com_foto, "https://s.shopee.com.br/b", "")]})
    assert edicao_video.exemplo("exemplo.mp4") == ("Copo Térmico", "")
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
        assert edicao_video.exemplo("exemplo.mp4")[0] == "Copo Térmico"
    assert editados == [videos["v1"], videos["v2"], videos["a1"], videos["v1"]]


def test_exemplo_sem_video_diz_o_motivo(monkeypatch):
    _fontes_de_mentira(monkeypatch, {})
    nome, motivo = edicao_video.exemplo("exemplo.mp4")
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
    assert edicao_video.exemplo("exemplo.mp4") == ("Copo Térmico", "")
    assert editados == [arquivo] and fotos[-1].endswith("/a1")
    assert len(fotos) == edicao_video.VIDEOS_POR_FONTE + 1
    # Os sem foto ficam lembrados: o toque seguinte não pergunta de novo à API por eles.
    fotos.clear()
    edicao_video.exemplo("exemplo.mp4")
    assert not [link for link in fotos if "sem-foto-0" in link]


def test_sem_video_novo_com_foto_recomeca_pelos_ja_mostrados(monkeypatch, tmp_path):
    arquivo = str(tmp_path / "v.mp4")
    open(arquivo, "wb").close()
    editados = _fontes_de_mentira(monkeypatch, {"viral": [
        ("viral:1", arquivo, "https://s.shopee.com.br/1", ""),
        ("viral:2", arquivo, "https://s.shopee.com.br/sem-foto-2", "")]}, fonte_do_robo="viral")
    for _ in range(3):
        assert edicao_video.exemplo("exemplo.mp4") == ("Copo Térmico", "")
    assert len(editados) == 3
    assert db.ler_config(edicao_video.CHAVE_EXEMPLOS, {})["ids"] == ["viral:1"]


def test_so_videos_sem_foto_diz_que_nenhum_tem_a_foto(monkeypatch, tmp_path):
    arquivo = str(tmp_path / "v.mp4")
    open(arquivo, "wb").close()
    _fontes_de_mentira(monkeypatch, {"viral": [("viral:1", arquivo, "https://s.shopee.com.br/sem-foto-1", "")]},
                       fonte_do_robo="viral")
    for _ in range(2):
        nome, motivo = edicao_video.exemplo("exemplo.mp4")
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
    assert edicao_video.texto_do_preco(39.9) == "A partir de R$ 39,90"
    assert edicao_video.texto_do_preco(0) == edicao_video.texto_do_preco(None) == ""
    import io

    from PIL import Image
    with Image.open(io.BytesIO(edicao_video.letreiro(edicao_video.texto_do_preco(1299.9),
                                                     edicao_video.FUNDO_DO_PRECO))) as imagem:
        # Duas linhas ("A partir de" e o preço), dentro da tela e com o fundo transparente.
        assert imagem.mode == "RGBA" and imagem.width <= 720 and 100 < imagem.height < 200
        assert imagem.getpixel((0, 0))[3] == 0 and imagem.getpixel((imagem.width // 2, 8))[3] > 150


def test_textos_da_tela_vem_da_ia_limpos_e_curtos(monkeypatch):
    import api_gemini
    pedidos = []

    async def analisar(video, prompt, imagens=None):
        pedidos.append(prompt)
        return ('ok {"nome": "Copo Térmico 🥤 de Inox Grande Premium Novo", '
                '"vantagem": "Mantém gelado o dia todo #top"}')

    monkeypatch.setattr(api_gemini, "analisar_video_gemini", analisar)
    textos = edicao_video.textos_da_tela("v.mp4", "Copo Térmico Marca X 500 ml")
    assert textos == {"nome": "Copo Térmico de Inox Grande", "vantagem": "Mantém gelado o dia todo top"}
    assert "Copo Térmico Marca X 500 ml" in pedidos[0] and "marca" in pedidos[0]

    async def sem_resposta(video, prompt, imagens=None):
        return None

    monkeypatch.setattr(api_gemini, "analisar_video_gemini", sem_resposta)
    assert edicao_video.textos_da_tela("v.mp4", "Copo") == {}


def test_editor_2_de_verdade_tira_o_parado_e_poe_os_textos(tmp_path):
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
    # A IA disse que ninguém fala (o som é só um apito): os parados podem sair.
    motivo, resumo = edicao_video.editar_2(str(video), _foto_jpg(), str(destino), "Copo Térmico", "", 39.9,
                                           falas=[])
    assert motivo == ""
    # Os 6 s parados saem; dos 9 s mexendo, 1 s vai em câmera lenta. A foto continua no começo.
    assert resumo["cortado"] == 6 and resumo["camera_lenta"] == 1 and resumo["acelerados"] == 0
    assert abs(resumo["remontado"] - (8 + 1 / edicao_video.CAMERA_LENTA)) < 0.01
    assert abs(edicao_video.videos.duracao(str(destino)) - (resumo["remontado"] + edicao_video.SEGUNDOS_DA_FOTO)) < 0.3
    assert edicao_video.videos.tem_audio(str(destino))
    assert resumo["textos"] == ["Copo Térmico", "A partir de R$ 39,90"]
    from PIL import Image

    def caixa_do_texto(segundo):
        quadro = tmp_path / f"quadro_{segundo}.ppm"
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(segundo), "-i", str(destino), "-frames:v", "1",
                        str(quadro)], check=True)
        with Image.open(quadro) as imagem:
            return imagem.convert("RGB").getpixel((360, edicao_video.TOPO_DOS_TEXTOS + 6))

    # O nome logo depois da foto (caixa escura) e o preço no fim (caixa laranja).
    assert max(caixa_do_texto(3.0)) < 80
    vermelho, verde, azul = caixa_do_texto(8.5)
    assert vermelho > 180 and verde < 120 and azul < 100
    # Escolha do Rafael (P45): onde alguém fala, nada sai. Fala nos 3 s parados do começo:
    # só os 3 s parados do fim saem.
    motivo, resumo = edicao_video.editar_2(str(video), _foto_jpg(), str(destino), "Copo", "", None,
                                           falas=[(0.5, 2.5)])
    assert motivo == "" and resumo["cortado"] == 3 and resumo["com_fala"] == 3
    # Sem a resposta da IA, todo trecho com som conta como fala: nada é cortado.
    motivo, resumo = edicao_video.editar_2(str(video), _foto_jpg(), str(destino), "Copo", "", None)
    assert motivo == "" and resumo["cortado"] == 0 and resumo["acelerados"] == 0


def test_remontar_sem_som_nao_mexe_no_som(monkeypatch, tmp_path):
    comandos = _programas(monkeypatch, audio="")
    trechos = [(0.0, 2.0, 1.0), (3.0, 5.0, 1.5)]
    assert edicao_video.videos.com_cortes_e_ritmo("v.mp4", trechos, str(tmp_path / "r.mp4")) == ""
    filtro = comandos[-1][comandos[-1].index("-filter_complex") + 1]
    assert "asplit" not in filtro and "atempo" not in filtro and "concat=n=2:v=1:a=0" in filtro
    assert "trim=start=3.000:end=5.000,setpts=(PTS-STARTPTS)/1.5" in filtro
    assert edicao_video.videos.com_cortes_e_ritmo("v.mp4", [], str(tmp_path / "r.mp4")) != ""


def test_exemplo_do_editor_2_tem_a_lista_propria_e_o_preco_da_api(monkeypatch, tmp_path):
    videos = {nome: str(tmp_path / f"{nome}.mp4") for nome in ("v1", "v2")}
    for caminho in videos.values():
        open(caminho, "wb").close()
    editados = _fontes_de_mentira(monkeypatch, {"viral": [
        ("viral:1", videos["v1"], "https://s.shopee.com.br/1", ""),
        ("viral:2", videos["v2"], "https://s.shopee.com.br/2", "")]}, fonte_do_robo="viral")
    monkeypatch.setattr(edicao_video, "_produto_do_link", lambda link: {"nome": "Copo Marca X", "preco": 39.9})
    monkeypatch.setattr(edicao_video, "textos_da_tela", lambda video, nome: {"nome": "Copo Térmico"})
    pedidos = []

    def editar_2(video, foto, destino, nome="", vantagem="", preco=None, falas=None):
        pedidos.append((video, nome, vantagem, preco))
        return "", {"textos": [nome]}

    monkeypatch.setattr(edicao_video, "editar_2", editar_2)
    assert edicao_video.exemplo("exemplo.mp4") == ("Copo Térmico", "")
    nome, motivo, resumo = edicao_video.exemplo_editor_2("exemplo.mp4")
    # O Editor 1 já mostrou o v1; o Editor 2 tem a lista dele e começa pelo v1 também.
    assert (nome, motivo) == ("Copo Térmico", "") and resumo["textos_da_ia"]
    assert editados == [videos["v1"]] and pedidos == [(videos["v1"], "Copo Térmico", "", 39.9)]
    assert db.ler_config(edicao_video.CHAVE_EXEMPLOS, {})["ids_2"] == ["viral:1"]
    edicao_video.exemplo_editor_2("exemplo.mp4")
    assert pedidos[-1][0] == videos["v2"]


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
    assert edicao_video.textos_da_tela("v.mp4", "Copo") == {"nome": "Copo", "falas": [(0.5, 3.0), (4.0, 6.5)]}
    responde('{"nome": "Copo", "falas": []}')
    assert edicao_video.textos_da_tela("v.mp4", "Copo")["falas"] == []
    responde('{"nome": "Copo", "falas": "o vídeo inteiro"}')
    assert "falas" not in edicao_video.textos_da_tela("v.mp4", "Copo")


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

"""O gravador das aulas do curso pelo celular do robô (cursos_robo, P288 3)."""
import hashlib
import os
import shutil
import subprocess

import cursos_robo


class Feito:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class Resposta:
    def __init__(self, dados):
        self.dados = dados

    def read(self):
        return self.dados

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        return False


def test_gravador_grava_sem_janela_sem_tocar_no_celular_e_no_tempo(tmp_path):
    destino = str(tmp_path / "aula.mkv")
    chamados = []

    def rodar(comando, **opcoes):
        chamados.append((comando, opcoes))
        with open(destino, "wb") as arquivo:
            arquivo.write(b"gravacao")
        return Feito()

    assert cursos_robo.gravar("celular:5555", 20, destino, rodar=rodar) == (True, "gravado")
    comando, opcoes = chamados[0]
    assert comando[:3] == ["scrcpy", "-s", "celular:5555"]
    for opcao in ("--no-window", "--no-playback", "--no-control", f"--record={destino}", "--record-format=mkv",
                  "--time-limit=20"):
        assert opcao in comando
    assert opcoes["timeout"] == 20 + cursos_robo.FOLGA_DO_GRAVADOR
    assert opcoes["env"]["SDL_VIDEODRIVER"] == opcoes["env"]["SDL_AUDIODRIVER"] == "dummy"


def test_gravacao_que_nao_sai_da_um_motivo_fixo_sem_o_endereco_do_celular(tmp_path):
    destino = str(tmp_path / "aula.mkv")
    for saida, motivo in (("ERROR: Could not find any ADB device celular:5555", "o celular não respondeu ao gravador"),
                          ("ERROR: Audio capture failed (celular:5555)", "o som do celular não pôde ser gravado"),
                          ("algo inesperado com celular:5555", "a gravação não saiu")):
        ok, texto = cursos_robo.gravar("celular:5555", 5, destino,
                                       rodar=lambda comando, saida=saida, **opcoes: Feito(1, stderr=saida))
        assert (ok, texto) == (False, motivo)
        assert "celular:5555" not in texto

    def sem_o_gravador(comando, **opcoes):
        raise FileNotFoundError("scrcpy")

    ok, texto = cursos_robo.gravar("celular:5555", 5, destino, rodar=sem_o_gravador)
    assert not ok and "instalar-gravador" in texto

    def demorou(comando, **opcoes):
        raise subprocess.TimeoutExpired(comando, opcoes["timeout"])

    assert cursos_robo.gravar("celular:5555", 5, destino, rodar=demorou) == (False, "o gravador não terminou no prazo")


def test_instalar_nao_mexe_em_nada_com_a_versao_ja_instalada(monkeypatch):
    monkeypatch.setattr(cursos_robo.shutil, "which", lambda nome: "/usr/local/bin/scrcpy")
    chamados = []

    def rodar(comando, **opcoes):
        chamados.append(comando)
        return Feito(stdout=f"scrcpy {cursos_robo.VERSAO_DO_GRAVADOR} <https://github.com/Genymobile/scrcpy>\n")

    assert cursos_robo.instalar(rodar=rodar, abrir=None) is True
    assert chamados == [["/usr/local/bin/scrcpy", "--version"]]


def test_instalar_so_compila_com_a_parte_do_celular_conferida(monkeypatch, tmp_path, capsys):
    pasta = tmp_path / "scrcpy"
    monkeypatch.setattr(cursos_robo, "PASTA_DO_GRAVADOR", str(pasta))
    instalado = {"agora": False}
    monkeypatch.setattr(cursos_robo.shutil, "which",
                        lambda nome: "/usr/local/bin/scrcpy" if instalado["agora"] else None)
    chamados = []

    def rodar(comando, **opcoes):
        chamados.append(comando)
        if comando[:2] == ["git", "clone"]:
            os.makedirs(comando[-1])
        if comando[-1] == "install":
            instalado["agora"] = True
        if comando[-1] == "--version":
            return Feito(stdout=f"scrcpy {cursos_robo.VERSAO_DO_GRAVADOR}\n")
        return Feito()

    # A parte do celular que não bate com o SHA-256 da versão: nada é compilado nem instalado.
    assert cursos_robo.instalar(rodar=rodar, abrir=lambda url, timeout: Resposta(b"outra coisa")) is False
    assert not any(c[0] in ("meson", "ninja") or "ninja" in c[:3] for c in chamados)
    assert "o SHA-256 não bate" in capsys.readouterr().out
    # Com o SHA-256 da versão, compila, instala e confere a versão no fim.
    parte = b"parte do celular"
    monkeypatch.setattr(cursos_robo, "SHA256_DA_PARTE_DO_CELULAR", hashlib.sha256(parte).hexdigest())
    chamados.clear()
    assert cursos_robo.instalar(rodar=rodar, abrir=lambda url, timeout: Resposta(parte)) is True
    assert (pasta / "scrcpy-server").read_bytes() == parte
    assert [c[0] if c[0] != "sudo" else " ".join(c[:4]) for c in chamados] == [
        "sudo -n apt-get update", "sudo -n env DEBIAN_FRONTEND=noninteractive", "git", "meson", "ninja",
        "sudo -n ninja -C", "/usr/local/bin/scrcpy"]
    saida = capsys.readouterr().out
    assert f"gravador: instalado (scrcpy {cursos_robo.VERSAO_DO_GRAVADOR})" in saida


def test_passo_da_instalacao_que_falha_mostra_o_codigo_e_para(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cursos_robo, "PASTA_DO_GRAVADOR", str(tmp_path / "scrcpy"))
    monkeypatch.setattr(cursos_robo.shutil, "which", lambda nome: None)
    chamados = []

    def rodar(comando, **opcoes):
        chamados.append(comando)
        return Feito(100, stderr="E: Unable to locate package libsdl2-dev")

    assert cursos_robo.instalar(rodar=rodar, abrir=None) is False
    assert len(chamados) == 1
    assert "lista de pacotes: falhou (código 100)" in capsys.readouterr().out


def test_problema_da_gravacao_preta_ou_muda():
    # P288 3: preta ou muda, o player não deixa gravar, e a gravação para.
    boa = {"segundos": 20, "tem_som": True, "som": -20.0, "brilho": 80}
    assert cursos_robo.problema(boa) == ""
    assert cursos_robo.problema(dict(boa, segundos=0)) == "a gravação saiu vazia"
    assert cursos_robo.problema(dict(boa, brilho=3)) == "a imagem saiu preta"
    assert cursos_robo.problema(dict(boa, brilho=None)) == "a imagem saiu preta"
    assert cursos_robo.problema(dict(boa, tem_som=False, som=None)) == "a gravação saiu sem o som"
    assert cursos_robo.problema(dict(boa, som=None)) == "o som saiu mudo"
    # O som baixo com a fala reconhecida serve: o player deixou gravar (22/11, uma aula a -61,5 LUFS com 180
    # palavras reconhecidas em 60 s); sem fala reconhecida, continua mudo.
    baixo = dict(boa, som=-61.5)
    assert cursos_robo.problema(baixo, palavras=180) == ""
    assert cursos_robo.problema(baixo) == cursos_robo.problema(baixo, palavras=0) == "o som saiu mudo"
    assert cursos_robo.linha_dos_numeros(boa, 2, 30) == (
        "20 s, brilho 80, som -20.0 LUFS, 2 folha(s) de quadros, 30 palavra(s) na fala")
    assert cursos_robo.linha_dos_numeros(dict(boa, som=None, brilho=None)) == "20 s, sem quadros, som mudo"


def test_numeros_de_uma_gravacao_de_verdade(tmp_path):
    if not shutil.which("ffmpeg"):
        return
    imagem_com_som = tmp_path / "boa.mkv"
    preta = tmp_path / "preta.mkv"
    sem_som = tmp_path / "sem_som.mkv"
    for destino, video, audio in (
            (imagem_com_som, "testsrc=duration=4:size=320x240:rate=5", "sine=frequency=440:duration=4"),
            (preta, "color=c=black:duration=4:size=320x240:rate=5", "sine=frequency=440:duration=4"),
            (sem_som, "testsrc=duration=4:size=320x240:rate=5", None)):
        comando = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", video]
        if audio:
            comando += ["-f", "lavfi", "-i", audio, "-shortest"]
        subprocess.run(comando + [str(destino)], check=True)
    medidos = cursos_robo.numeros(str(imagem_com_som))
    assert medidos["segundos"] == 4 and medidos["tem_som"] and medidos["som"] > -40 and medidos["brilho"] > 40
    assert cursos_robo.problema(medidos) == ""
    assert cursos_robo.problema(cursos_robo.numeros(str(preta))) == "a imagem saiu preta"
    assert cursos_robo.problema(cursos_robo.numeros(str(sem_som))) == "a gravação saiu sem o som"


def test_para_o_claude_grava_a_fala_com_o_segundo_de_cada_trecho(monkeypatch, tmp_path):
    monkeypatch.setattr(cursos_robo.videos, "folhas_de_quadros", lambda arquivo, pasta, maximo: 3)
    monkeypatch.setattr(cursos_robo.videos, "fala_em_trechos",
                        lambda arquivo: [(0.5, "Bem-vindos à aula."), (64.25, "Agora o segundo passo.")])
    assert cursos_robo.para_o_claude("aula.mkv", str(tmp_path)) == (3, 7)
    assert (tmp_path / "fala.txt").read_text(encoding="utf-8") == (
        "[    0.5s] Bem-vindos à aula.\n[   64.2s] Agora o segundo passo.\n")
    # Sem o reconhecimento de voz, as folhas vão sem a fala.
    monkeypatch.setattr(cursos_robo.videos, "fala_em_trechos", lambda arquivo: None)
    os.remove(tmp_path / "fala.txt")
    assert cursos_robo.para_o_claude("aula.mkv", str(tmp_path)) == (3, None)
    assert not (tmp_path / "fala.txt").exists()


TELA_DO_LOGIN = """<hierarchy>
  <node class="android.widget.TextView" text="Acesse sua área de membros" bounds="[100,600][980,660]" />
  <node class="android.widget.EditText" text="" password="false" bounds="[40,700][1040,800]" />
  <node class="android.widget.EditText" text="" password="true" bounds="[40,840][1040,940]" />
  <node class="android.widget.Button" text="Entrar" bounds="[40,1000][1040,1100]" />
</hierarchy>"""
TELA_DO_CURSO = """<hierarchy>
  <node class="android.widget.TextView" text="Cursos" bounds="[0,100][300,160]" />
</hierarchy>"""


class Chrome:
    """O celular de mentira com o Chrome: as telas em sequência, os toques, as teclas e os comandos."""

    def __init__(self, *telas):
        self.telas, self.toques, self.teclas, self.comandos = list(telas), [], [], []

    def dump_hierarchy(self):
        return self.telas.pop(0) if len(self.telas) > 1 else self.telas[0]

    def click(self, x, y):
        self.toques.append((x, y))

    def press(self, tecla):
        self.teclas.append(tecla)

    def shell(self, partes):
        self.comandos.append(partes)


def _guardar_o_acesso(**campos):
    import db
    db.salvar_config("acessos_servidor", {"curso": campos})


def test_abrir_o_curso_pelo_link_guardado_sem_o_link_no_log(bm):
    celular = Chrome(TELA_DO_CURSO)
    assert cursos_robo.abrir_o_curso(celular) == (False, "sem o link do curso no Acessos do Servidor")
    assert celular.comandos == []
    _guardar_o_acesso(link="https://curso.exemplo.com/m/courses")
    ok, texto = cursos_robo.abrir_o_curso(celular)
    assert (ok, texto) == (True, "curso aberto no Chrome")
    # Sempre na mesma aba do Chrome (a marca do robô no pedido), sem juntar uma aba nova a cada vez.
    assert celular.comandos == [["am", "start", "-a", "android.intent.action.VIEW", "-d",
                                 "https://curso.exemplo.com/m/courses", "-p", "com.android.chrome",
                                 "--es", "com.android.browser.application_id", "cursos_robo"]]


def test_campos_do_login_so_na_pagina_de_login():
    assert cursos_robo.campos_do_login(TELA_DO_LOGIN) == ((540, 750), (540, 890))
    assert cursos_robo.campos_do_login(TELA_DO_CURSO) is None
    assert cursos_robo.campos_do_login("<quebrado") is None


EMAIL_DO_TESTE = "aluno@exemplo.com"
SENHA_DO_TESTE = "senha do curso"


class PaginaDeLogin:
    """
    O Chrome de mentira na página de login, como no Motorola em 22/11: o teclado aberto sobe a página
    560 px, o toque fora dos campos (numa tecla) deixa o cursor onde estava, e o Enter só entra com o
    e-mail no campo de e-mail e a senha no de senha.
    """

    def __init__(self, entra_pelo_enter=True, senha_sem_cursor=False):
        self.foco, self.teclado, self.entrou = None, False, False
        self.campos = {"email": "", "senha": ""}
        self.toques, self.teclas = [], []
        self.entra_pelo_enter, self.senha_sem_cursor = entra_pelo_enter, senha_sem_cursor

    def _caixas(self):
        sobe = 560 if self.teclado else 0
        return {"email": (42, 1369 - sobe, 1039, 1492 - sobe), "senha": (42, 1542 - sobe, 900, 1666 - sobe)}

    def dump_hierarchy(self):
        if self.entrou:
            return TELA_DO_CURSO
        nos = "".join(
            f'<node class="android.widget.EditText" text="" password="{str(nome == "senha").lower()}" '
            f'focused="{str(self.foco == nome).lower()}" bounds="[{x1},{y1}][{x2},{y2}]" />'
            for nome, (x1, y1, x2, y2) in self._caixas().items())
        return (f'<hierarchy>{nos}<node class="android.widget.Button" text="Entrar" '
                'bounds="[42,1800][1039,1900]" /></hierarchy>')

    def click(self, x, y):
        self.toques.append((x, y))
        for nome, (x1, y1, x2, y2) in self._caixas().items():
            if x1 <= x <= x2 and y1 <= y <= y2 and not (nome == "senha" and self.senha_sem_cursor):
                self.foco, self.teclado = nome, True

    def escrever(self, texto):
        if self.foco:
            self.campos[self.foco] = texto

    def press(self, tecla):
        self.teclas.append(tecla)
        certo = self.campos == {"email": EMAIL_DO_TESTE, "senha": SENHA_DO_TESTE}
        self.entrou = tecla == "enter" and certo and self.entra_pelo_enter


def test_entrar_no_curso_escreve_o_login_guardado_e_confere_que_passou(bm):
    escrever = lambda d, texto: d.escrever(texto)
    achar = lambda tela, alvo: (540, 1850) if alvo == "Entrar" and "Entrar" in tela else None
    sem_pausa = lambda segundos: None
    # Sem o e-mail e a senha guardados, nada é tocado.
    celular = Chrome(TELA_DO_LOGIN)
    assert cursos_robo.entrar_no_curso(celular, escrever, achar, pausa=sem_pausa) == (
        False, "sem o login do curso no Acessos do Servidor")
    assert celular.toques == []
    _guardar_o_acesso(link="https://curso.exemplo.com", email=EMAIL_DO_TESTE, senha=SENHA_DO_TESTE)
    # Fora da página de login, também não.
    celular = Chrome(TELA_DO_CURSO)
    assert cursos_robo.entrar_no_curso(celular, escrever, achar, pausa=sem_pausa) == (
        False, "a tela não é a de login do curso")
    assert celular.toques == []
    # Na página de login: o teclado do e-mail sobe a página, e a senha é tocada no lugar novo do campo
    # (no de antes, o toque caía no teclado e a senha ia para o campo do e-mail).
    celular = PaginaDeLogin()
    assert cursos_robo.entrar_no_curso(celular, escrever, achar, pausa=sem_pausa) == (True, "login feito")
    assert celular.toques == [(540, 1430), (471, 1044)] and celular.teclas == ["enter"]
    assert celular.campos == {"email": EMAIL_DO_TESTE, "senha": SENHA_DO_TESTE}
    # O Enter não entrou: toca no Entrar; continuando no login, diz que não passou.
    celular = PaginaDeLogin(entra_pelo_enter=False)
    assert cursos_robo.entrar_no_curso(celular, escrever, achar, pausa=sem_pausa) == (
        False, "o login não passou (a página de login continua)")
    assert celular.toques[-1] == (540, 1850)


def test_entrar_no_curso_nunca_escreve_a_senha_fora_do_campo_de_senha(bm):
    _guardar_o_acesso(link="https://curso.exemplo.com", email=EMAIL_DO_TESTE, senha=SENHA_DO_TESTE)
    celular = PaginaDeLogin(senha_sem_cursor=True)
    escrever = lambda d, texto: d.escrever(texto)
    assert cursos_robo.entrar_no_curso(celular, escrever, lambda tela, alvo: None, pausa=lambda s: None) == (
        False, "o cursor não ficou no campo certo do login")
    # O cursor ficou no e-mail: a senha não foi escrita em lugar nenhum, e nada foi enviado.
    assert celular.campos == {"email": EMAIL_DO_TESTE, "senha": ""} and celular.teclas == []


def test_campo_em_foco_diz_se_o_cursor_esta_no_campo_de_senha():
    assert cursos_robo.campo_em_foco(TELA_DO_LOGIN) is None
    celular = PaginaDeLogin()
    celular.foco = "email"
    assert cursos_robo.campo_em_foco(celular.dump_hierarchy()) is False
    celular.foco = "senha"
    assert cursos_robo.campo_em_foco(celular.dump_hierarchy()) is True
    assert cursos_robo.campo_em_foco("<quebrado") is None


class CelularDoVolume:
    """O celular de mentira que responde pelo adb ao volume de mídia e à sessão de mídia do Chrome."""

    def __init__(self, volume=2, maximo=15, midia="", muda=True, responde=True):
        self.volume, self.maximo, self.midia, self.muda, self.responde = volume, maximo, midia, muda, responde
        self.comandos = []

    def shell(self, partes):
        import types
        self.comandos.append(partes)
        saida = ""
        if partes[:3] == ["cmd", "media_session", "volume"] and self.responde:
            if "--set" in partes:
                if self.muda:
                    self.volume = int(partes[-1])
                saida = f"[V] will set volume to index={partes[-1]}\n"
            else:
                saida = ("[V] will get volume\n[V] Connecting to AudioService\n"
                         f"[V] volume is {self.volume} in range [0..{self.maximo}]\n")
        elif partes[:2] == ["dumpsys", "media_session"]:
            saida = self.midia
        return types.SimpleNamespace(output=saida, exit_code=0)


# A sessão de mídia de outro app e duas do Chrome (uma aba pausada e a aula tocando), no formato do Android.
DUMP_DA_MIDIA = """MEDIA SESSION SERVICE (dumpsys media_session)
Sessions Stack - have 3 sessions:
  Musica com.exemplo.musica/sessao (userId=0)
    ownerPid=111, ownerUid=10100, userId=0
    package=com.exemplo.musica
    active=true
    state=PlaybackState {state=3, position=99000, buffered position=0, speed=1.0, updated=1, actions=0, error=null}
    metadata: size=3, description=Outra musica, Outro, null
  Chrome com.android.chrome/MediaSession (userId=0)
    package=com.android.chrome
    active=false
    state=PlaybackState {state=2, position=5000, buffered position=0, speed=0.0, updated=2, actions=0, error=null}
    metadata: size=3, description=Aula antiga do curso, Curso, null
  Chrome com.android.chrome/MediaSession (userId=0)
    package=com.android.chrome
    active=true
    state=PlaybackState {state=PLAYING(3), position=40311, buffered position=0, speed=1.0, updated=3, error=null}
    metadata: size=3, description=Aula de agora do curso, Curso, null
"""


def test_volume_de_midia_lido_e_mudado_pelo_adb_sem_tocar_na_tela():
    # P291 1: o som chega ao servidor no volume de mídia do celular; o robô o muda pelo adb, sem toque.
    celular = CelularDoVolume(volume=2)
    assert cursos_robo.volume_de_midia(celular) == (2, 15)
    assert cursos_robo.mudar_o_volume(celular, 8) == (8, 15)
    assert ["cmd", "media_session", "volume", "--stream", "3", "--set", "8"] in celular.comandos
    assert all(partes[0] in ("cmd",) for partes in celular.comandos)
    assert cursos_robo.volume_no_explorar(celular, "") == (True, "volume de mídia: 8 de 15")
    assert cursos_robo.volume_no_explorar(celular, "4") == (True, "volume de mídia: de 8 para 4 de 15")
    assert cursos_robo.volume_no_explorar(celular, "16") == (False, "volume vai de 0 a 15")
    assert cursos_robo.volume_no_explorar(celular, "alto") == (False, "volume pede o número (ex.: volume:8)")
    assert celular.volume == 4
    assert cursos_robo.volume_no_explorar(CelularDoVolume(muda=False), "8") == (
        False, "o volume de mídia não mudou (estava em 2 de 15)")
    assert cursos_robo.volume_no_explorar(CelularDoVolume(responde=False), "") == (
        False, "o Android não disse o volume de mídia")


def test_estado_do_video_no_chrome_sem_o_titulo_da_aula():
    # Com duas abas do Chrome, vale a que está tocando; o outro app não conta, e o título da aula não sai.
    estado = cursos_robo.estado_da_midia(DUMP_DA_MIDIA)
    assert estado == {"estado": "tocando", "posicao": 40}
    assert "Aula" not in str(estado)
    so_pausada = DUMP_DA_MIDIA.replace("state=PLAYING(3), position=40311", "state=2, position=7000")
    assert cursos_robo.estado_da_midia(so_pausada) == {"estado": "pausado", "posicao": 5}
    assert cursos_robo.estado_da_midia(DUMP_DA_MIDIA.replace("com.android.chrome", "com.outro.app")) is None
    assert cursos_robo.estado_da_midia("") is None


def test_midia_no_explorar_pausa_e_toca_pela_tecla_de_midia():
    celular = CelularDoVolume(midia=DUMP_DA_MIDIA)
    assert cursos_robo.midia_no_explorar(celular, "", pausa=lambda s: None) == (
        True, "vídeo do Chrome: tocando, em 40 s")
    assert not any(partes[0] == "input" for partes in celular.comandos)
    assert cursos_robo.midia_no_explorar(celular, "pausar", pausa=lambda s: None)[0] is True
    assert ["input", "keyevent", "KEYCODE_MEDIA_PAUSE"] in celular.comandos
    assert cursos_robo.midia_no_explorar(celular, "Tocar", pausa=lambda s: None)[0] is True
    assert ["input", "keyevent", "KEYCODE_MEDIA_PLAY"] in celular.comandos
    assert cursos_robo.midia_no_explorar(celular, "pular", pausa=lambda s: None) == (
        False, "midia lê o vídeo do Chrome (midia), pausa (midia:pausar) ou toca (midia:tocar)")
    assert cursos_robo.midia_no_explorar(CelularDoVolume(), "", pausa=lambda s: None) == (True, "sem vídeo no Chrome")

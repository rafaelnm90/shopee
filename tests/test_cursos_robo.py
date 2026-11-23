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
    # Sem o som da gravação, o gravador para (--require-audio): a aula nunca toca alto no quarto do Rafael.
    for opcao in ("--no-window", "--no-playback", "--no-control", "--require-audio", f"--record={destino}",
                  "--record-format=mkv", "--time-limit=20"):
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


# O dumpsys media_session sem nenhum vídeo ou som no celular.
SEM_SESSOES = "MEDIA SESSION SERVICE (dumpsys media_session)\nSessions Stack - have 0 sessions:\n"


class CelularDoVolume:
    """O celular de mentira que responde pelo adb ao volume de mídia e à sessão de mídia do Chrome."""

    def __init__(self, volume=2, maximo=15, midia=SEM_SESSOES, muda=True, responde=True, pausa_funciona=True):
        self.volume, self.maximo, self.midia, self.muda, self.responde = volume, maximo, midia, muda, responde
        self.pausa_funciona, self.comandos = pausa_funciona, []

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
        elif partes == ["input", "keyevent", "KEYCODE_MEDIA_PAUSE"] and self.pausa_funciona:
            self.midia = self.midia.replace("state=PLAYING(3)", "state=PAUSED(2)").replace("state=3,", "state=2,")
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
    # Tocando, a posição anotada anda com o relógio do celular (20 s depois da anotação, 20 s a mais);
    # pausado, ela fica onde parou.
    assert cursos_robo.estado_da_midia(DUMP_DA_MIDIA, agora_ms=3 + 20000) == {"estado": "tocando", "posicao": 60}
    assert cursos_robo.estado_da_midia(so_pausada, agora_ms=3 + 20000) == {"estado": "pausado", "posicao": 5}


def test_relogio_do_celular_pelo_uptime():
    class Celular:
        def __init__(self, saida):
            self.saida = saida

        def shell(self, partes):
            import types
            return types.SimpleNamespace(output=self.saida if partes == ["cat", "/proc/uptime"] else "")

    assert cursos_robo.relogio_do_celular(Celular("12345.67 45678.90\n")) == 12345670
    assert cursos_robo.relogio_do_celular(Celular("")) is None


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


def _br(texto):
    from datetime import datetime
    from fuso import fuso_horario
    return datetime.strptime(texto, "%Y-%m-%d %H:%M").replace(tzinfo=fuso_horario)


def test_madrugada_e_fora_do_horario_do_robo_e_antes_das_3h45():
    # P289 1: grava de madrugada, fora do Horário do Robô, parando antes da limpeza das 4h.
    horario = {"robo_inicio": 8, "robo_fim": 22}
    for hora, vale in (("21:59", False), ("22:00", True), ("23:30", True), ("00:30", True), ("03:44", True),
                       ("03:45", False), ("04:00", False), ("07:59", False), ("12:00", False)):
        assert cursos_robo.na_madrugada(horario, _br(f"2026-11-23 {hora}")) is vale, hora
    # O robô tem a preferência: com o Horário do Robô o dia todo, não há madrugada.
    assert not cursos_robo.na_madrugada({"robo_inicio": 0, "robo_fim": 24}, _br("2026-11-23 02:00"))
    # O Horário do Robô que começa antes das 3h45 encurta a madrugada.
    assert cursos_robo.na_madrugada({"robo_inicio": 2, "robo_fim": 22}, _br("2026-11-23 01:00"))
    assert not cursos_robo.na_madrugada({"robo_inicio": 2, "robo_fim": 22}, _br("2026-11-23 02:30"))


def test_disco_usado_como_o_df_mostra(monkeypatch):
    import collections
    Uso = collections.namedtuple("Uso", "total used free")
    monkeypatch.setattr(cursos_robo.shutil, "disk_usage", lambda caminho: Uso(100, 69.2, 30.8))
    assert cursos_robo.disco_usado() == 70
    monkeypatch.setattr(cursos_robo.shutil, "disk_usage", lambda caminho: Uso(100, 68, 32))
    assert cursos_robo.disco_usado() == 68


def test_sinal_da_gravacao_e_pedido_do_celular_pelo_robo(bm):
    inicio = _br("2026-11-23 23:00")
    assert not cursos_robo.gravando(inicio)
    cursos_robo.anotar_o_sinal(inicio)
    assert cursos_robo.gravando(_br("2026-11-23 23:01"))
    assert not cursos_robo.gravando(_br("2026-11-23 23:03"))
    cursos_robo.soltar_o_sinal()
    assert not cursos_robo.gravando(inicio)
    cursos_robo.pedir_o_celular("robô", _br("2026-11-23 23:10"))
    assert cursos_robo.pediram_o_celular("2026-11-23 23:00:00")
    assert not cursos_robo.pediram_o_celular("2026-11-23 23:11:00")


def test_robo_pede_o_celular_e_a_gravacao_solta_em_segundos(bm):
    # O robô da Shopee Vídeo nunca para por causa do curso (pedido do Rafael, 22/11).
    pausas = []
    assert cursos_robo.liberar_para_o_robo(pausa=pausas.append, ocupado=lambda: True)
    assert pausas == [] and "pedido_em" not in cursos_robo.estado_da_noite()
    cursos_robo.anotar_o_sinal()
    respostas = iter([True, True, False])
    assert cursos_robo.liberar_para_o_robo(pausa=pausas.append, ocupado=lambda: next(respostas))
    assert len(pausas) == 2 and cursos_robo.estado_da_noite()["pedido_por"] == "robô"
    # A gravação que não solta a tempo: o robô fica sabendo.
    assert not cursos_robo.liberar_para_o_robo(espera=6, pausa=lambda s: None, ocupado=lambda: True)


def test_volume_da_aula_sobe_ao_meio_e_volta_ao_de_antes(bm):
    celular = CelularDoVolume(volume=2)
    assert cursos_robo.subir_o_volume(celular) == (8, 15)
    assert cursos_robo.estado_da_noite()["volume_antes"] == 2
    assert cursos_robo.devolver_o_volume(celular) and celular.volume == 2
    assert cursos_robo.estado_da_noite()["volume_antes"] is None
    assert not cursos_robo.devolver_o_volume(celular)
    # A gravação que cai e começa de novo antes de o volume voltar guarda o de antes da 1ª, não o da aula.
    assert cursos_robo.subir_o_volume(celular) == (8, 15)
    assert cursos_robo.subir_o_volume(celular) == (8, 15)
    assert cursos_robo.estado_da_noite()["volume_antes"] == 2
    assert cursos_robo.devolver_o_volume(celular) and celular.volume == 2
    # Já acima do meio, fica como está.
    alto = CelularDoVolume(volume=12)
    assert cursos_robo.subir_o_volume(alto) == (12, 15)
    assert not any("--set" in partes for partes in alto.comandos)
    # Sem resposta do Android, nada é guardado nem mudado.
    cursos_robo._anotar(volume_antes=None)
    assert cursos_robo.subir_o_volume(CelularDoVolume(responde=False)) is None
    assert cursos_robo.estado_da_noite()["volume_antes"] is None


def test_calar_o_celular_para_o_explorar_de_madrugada(bm):
    # P294 1: de madrugada, o explorar do curso deixa o celular mudo, e o volume de antes volta no fim.
    celular = CelularDoVolume(volume=6)
    assert cursos_robo.calar_o_celular(celular) == (0, 15)
    assert cursos_robo.estado_da_noite()["volume_antes"] == 6
    assert cursos_robo.devolver_o_volume(celular) and celular.volume == 6
    # Já mudo, nada muda.
    mudo = CelularDoVolume(volume=0)
    assert cursos_robo.calar_o_celular(mudo) == (0, 15)
    assert not any("--set" in partes for partes in mudo.comandos)
    # Sem resposta do Android, None (o explorar não toca em nada).
    cursos_robo._anotar(volume_antes=None)
    assert cursos_robo.calar_o_celular(CelularDoVolume(responde=False)) is None


def test_o_volume_so_volta_com_nada_tocando_no_celular_do_quarto_do_rafael(bm):
    # O celular fica no quarto do Rafael (pedido dele, 22/11/2026): o que toca é pausado antes de o volume voltar.
    assert cursos_robo.tocando_agora(DUMP_DA_MIDIA)
    assert not cursos_robo.tocando_agora(SEM_SESSOES)
    assert cursos_robo.tocando_agora(SEM_SESSOES + "    state=PlaybackState {state=6, position=0, speed=0.0}\n")
    celular = CelularDoVolume(volume=8, midia=DUMP_DA_MIDIA)
    cursos_robo._anotar(volume_antes=2)
    assert cursos_robo.devolver_o_volume(celular, pausa=lambda s: None) and celular.volume == 2
    pausou = celular.comandos.index(["input", "keyevent", "KEYCODE_MEDIA_PAUSE"])
    voltou = next(n for n, partes in enumerate(celular.comandos) if "--set" in partes)
    assert pausou < voltou and not cursos_robo.tocando_agora(celular.midia)
    # O que não pausa (ou o Android que não responde) deixa o celular mudo, nunca alto; o de antes volta depois.
    for celular in (CelularDoVolume(volume=8, midia=DUMP_DA_MIDIA, pausa_funciona=False),
                    CelularDoVolume(volume=8, midia="")):
        cursos_robo._anotar(volume_antes=2)
        assert not cursos_robo.devolver_o_volume(celular, pausa=lambda s: None)
        assert celular.volume == 0 and cursos_robo.estado_da_noite()["volume_antes"] == 2
    celular.midia = SEM_SESSOES
    assert cursos_robo.devolver_o_volume(celular, pausa=lambda s: None) and celular.volume == 2


class ProcessoDoGravador:
    """O scrcpy de mentira: grava (ou não) o arquivo quando recebe o Ctrl+C."""

    def __init__(self, comando, grava=True, erro="", **opcoes):
        import signal
        self.comando, self.grava, self.erro, self.sinais, self.vivo = comando, grava, erro, [], True
        self.destino = next(parte.split("=", 1)[1] for parte in comando if parte.startswith("--record="))
        self.saida = opcoes["stderr"]
        self.SIGINT = signal.SIGINT

    def poll(self):
        return None if self.vivo else 0

    def send_signal(self, sinal):
        self.sinais.append(sinal)
        if self.grava:
            with open(self.destino, "wb") as arquivo:
                arquivo.write(b"aula")
        self.saida.write(self.erro)
        self.vivo = False

    def wait(self, timeout=None):
        return 0


def test_gravacao_em_fundo_para_com_o_ctrl_c_e_fecha_o_arquivo(tmp_path):
    import signal
    criados = []

    def abrir(comando, **opcoes):
        criados.append(ProcessoDoGravador(comando, **opcoes))
        return criados[-1]

    destino = str(tmp_path / "aula.mkv")
    gravacao = cursos_robo.GravacaoEmFundo("celular:5555", destino, 3600, abrir=abrir)
    assert gravacao.rodando()
    assert "--no-control" in criados[0].comando and "--time-limit=3600" in criados[0].comando
    assert gravacao.parar() == (True, "gravado")
    assert criados[0].sinais == [signal.SIGINT] and not os.path.exists(destino + ".saida")

    def sem_celular(comando, **opcoes):
        return ProcessoDoGravador(comando, grava=False, erro="ERROR: Could not find any ADB device", **opcoes)

    outra = cursos_robo.GravacaoEmFundo("celular:5555", str(tmp_path / "outra.mkv"), 60, abrir=sem_celular)
    assert outra.parar() == (False, "o celular não respondeu ao gravador")


def test_fim_da_aula_pela_sessao_de_midia():
    olho = cursos_robo.OlhoNaAula()
    # Antes de tocar, nada acaba (a página ainda carrega o vídeo).
    assert olho.olhar(None, 0) is None and olho.olhar({"estado": "pausado", "posicao": 0}, 30) is None
    assert olho.olhar({"estado": "tocando", "posicao": 5}, 35) is None
    assert olho.olhar({"estado": "tocando", "posicao": 600}, 630) is None and olho.maior == 600
    # Parado depois de tocar: acaba depois de PARADO_NO_FIM s; carregando, espera mais.
    assert olho.olhar({"estado": "pausado", "posicao": 610}, 640) is None
    assert olho.olhar({"estado": "pausado", "posicao": 610}, 654) is None
    assert olho.olhar({"estado": "pausado", "posicao": 610}, 655) == "o vídeo parou"
    olho.de_novo()
    assert olho.olhar({"estado": "carregando", "posicao": 610}, 660) is None
    assert olho.olhar({"estado": "carregando", "posicao": 610}, 700) is None
    assert olho.olhar({"estado": "carregando", "posicao": 610}, 780) == "carregando demais"
    # O vídeo que volta ao começo é outro (a aula seguinte, que o site começa sozinho).
    assert olho.olhar({"estado": "tocando", "posicao": 2}, 790) == "outro vídeo começou"
    assert cursos_robo.OlhoNaAula().olhar(None, 10) is None


def _sessao_do_chrome(estado, posicao_s):
    """O dumpsys media_session com só a aula no Chrome, nesse estado (3 tocando, 2 pausada, 6 carregando)."""
    return ("MEDIA SESSION SERVICE (dumpsys media_session)\nSessions Stack - have 1 sessions:\n"
            "  Chrome com.android.chrome/MediaSession (userId=0)\n    package=com.android.chrome\n    active=true\n"
            f"    state=PlaybackState {{state={estado}, position={int(posicao_s * 1000)}, buffered position=0, "
            f"speed={1.0 if estado == 3 else 0.0}, updated=1, actions=0, error=null}}\n"
            "    metadata: size=3, description=Aula, Curso, null\n")


class AulaNoCelular(CelularDoVolume):
    """O celular de mentira com a aula aberta no Chrome: toca no play e para sozinha aos `dura` s."""

    def __init__(self, relogio, dura=60, carrega=False, **opcoes):
        super().__init__(**opcoes)
        self.relogio, self.dura, self.carrega = relogio, dura, carrega
        self.comeco, self.pausada, self.eventos = None, False, []

    def tocar(self, d):
        self.comeco = self.relogio()
        self.eventos.append("play")
        return True

    def shell(self, partes):
        if partes[:2] == ["dumpsys", "media_session"]:
            self.midia = self._midia()
        if partes == ["input", "keyevent", "KEYCODE_MEDIA_PAUSE"]:
            self.eventos.append("pausa")
            self.pausada = True
        if "--set" in partes:
            self.eventos.append(f"volume {partes[-1]}")
        return super().shell(partes)

    def _midia(self):
        if self.comeco is None:
            return SEM_SESSOES
        tocou = self.relogio() - self.comeco
        if self.pausada or tocou >= self.dura:
            return _sessao_do_chrome(2, min(tocou, self.dura))
        if self.carrega and tocou >= 20:
            return _sessao_do_chrome(6, 20)
        return _sessao_do_chrome(3, tocou)


def _gravar_a_aula(celular, tmp_path, tempo, quando=None, madrugada=lambda: True, gravador_vivo=True):
    """Grava a aula de mentira com o relógio de mentira; quando(t) roda a cada pausa (o robô pede, o gravador cai)."""
    gravadores = []

    def abrir(comando, **opcoes):
        processo = ProcessoDoGravador(comando, **opcoes)
        processo.vivo = gravador_vivo
        original = processo.send_signal

        def parar(sinal):
            celular.eventos.append("gravador parou")
            original(sinal)

        processo.send_signal = parar
        gravadores.append(processo)
        return processo

    def pausa(segundos):
        tempo[0] += segundos
        if quando:
            quando(tempo[0], gravadores)

    destino = str(tmp_path / "aula.mkv")
    feito = cursos_robo.gravar_a_aula_aberta(celular, "celular:5555", destino, celular.tocar, pausa=pausa,
                                             relogio=lambda: tempo[0], abrir=abrir, madrugada=madrugada)
    return feito, destino, gravadores


def test_aula_aberta_gravada_inteira_com_o_volume_de_volta_antes_de_o_gravador_parar(bm, tmp_path):
    # P291 1 e o pedido de 22/11 (o celular no quarto do Rafael): o gravador liga antes de o volume subir e
    # para só depois de a aula pausar e o volume voltar.
    tempo = [0.0]
    celular = AulaNoCelular(lambda: tempo[0], dura=60, volume=2)
    feito, destino, gravadores = _gravar_a_aula(celular, tmp_path, tempo)
    assert feito == (True, "o vídeo parou")
    assert celular.eventos == ["volume 8", "play", "volume 2", "gravador parou"]
    assert os.path.exists(destino) and celular.volume == 2
    assert cursos_robo.estado_da_noite()["volume_antes"] is None
    # Enquanto grava, o sinal ao robô fica renovado (quem solta é a noite, no fim).
    assert cursos_robo.gravando()
    assert "--require-audio" in gravadores[0].comando and tempo[0] >= 5 + 60 + cursos_robo.PARADO_NO_FIM


def test_robo_que_pede_o_celular_para_a_aula_que_fica_pela_metade(bm, tmp_path):
    # O robô da Shopee Vídeo tem a preferência (pedido de 22/11): a aula pausa e solta o celular na hora, e
    # fica pela metade (P295 1: volta depois, do início).
    tempo = [0.0]
    celular = AulaNoCelular(lambda: tempo[0], dura=600, volume=2)

    def quando(agora, gravadores):
        if agora >= 30 and "pedido_em" not in cursos_robo.estado_da_noite():
            cursos_robo.pedir_o_celular("robô")

    feito, destino, _ = _gravar_a_aula(celular, tmp_path, tempo, quando)
    assert feito == (False, "o robô pediu o celular")
    assert celular.eventos == ["volume 8", "play", "pausa", "volume 2", "gravador parou"]
    assert tempo[0] < 40 and celular.volume == 2


def test_gravador_que_cai_no_meio_pausa_a_aula_e_devolve_o_volume(bm, tmp_path):
    # Parado o gravador, o alto-falante volta a tocar: a aula pausa e o volume volta na hora.
    tempo = [0.0]
    celular = AulaNoCelular(lambda: tempo[0], dura=600, volume=2)

    def quando(agora, gravadores):
        if agora >= 20:
            gravadores[0].vivo = False

    feito, _, _ = _gravar_a_aula(celular, tmp_path, tempo, quando)
    assert feito == (False, "o gravador parou no meio")
    assert celular.eventos == ["volume 8", "play", "pausa", "volume 2"]


def test_gravador_que_nao_grava_o_som_nao_deixa_a_aula_tocar(bm, tmp_path):
    # Sem o som da gravação, o --require-audio para o gravador, e o alto-falante não ficaria mudo.
    tempo = [0.0]
    celular = AulaNoCelular(lambda: tempo[0], volume=2)
    feito, _, _ = _gravar_a_aula(celular, tmp_path, tempo, gravador_vivo=False)
    assert feito == (False, "o gravador não ficou gravando")
    assert celular.eventos == [] and celular.volume == 2


def test_madrugada_que_acaba_e_video_que_nao_carrega_param_a_aula(bm, tmp_path):
    # Às 3h45 (P289 1), a aula para pela metade, antes do descurtir das 4h.
    tempo = [0.0]
    celular = AulaNoCelular(lambda: tempo[0], dura=600, volume=2)
    feito, _, _ = _gravar_a_aula(celular, tmp_path, tempo, madrugada=lambda: tempo[0] < 40)
    assert feito == (False, "a madrugada acabou")
    assert celular.eventos[-3:] == ["pausa", "volume 2", "gravador parou"]
    # O vídeo que fica carregando não conta como aula inteira.
    tempo = [0.0]
    cursos_robo._anotar(volume_antes=None)
    celular = AulaNoCelular(lambda: tempo[0], dura=600, carrega=True, volume=2)
    feito, _, _ = _gravar_a_aula(celular, tmp_path, tempo)
    assert feito == (False, "carregando demais")
    assert celular.eventos[-2:] == ["volume 2", "gravador parou"]


def test_quadros_da_aula_um_a_cada_20_s_de_40_a_120():
    assert cursos_robo.quadros_da_aula(600) == 40
    assert cursos_robo.quadros_da_aula(1800) == 90
    assert cursos_robo.quadros_da_aula(7200) == 120
    assert cursos_robo.quadros_da_aula(None) == 40


def test_aula_guardada_so_com_a_fala_e_os_quadros_e_o_video_sai(monkeypatch, tmp_path):
    # P290 1: o vídeo da aula sai logo depois de lido; ficam a fala e as folhas, e o aula.json só de números.
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_AULAS", str(tmp_path / "aulas"))
    monkeypatch.setattr(cursos_robo, "numeros",
                        lambda arquivo: {"segundos": 1800, "tem_som": True, "som": -20.0, "brilho": 90})
    pedidos = []

    def para_o_claude(arquivo, pasta, quadros):
        pedidos.append(quadros)
        (tmp_path / "aulas").joinpath(os.path.basename(pasta), "fala.txt").write_text("[0.0s] texto da aula")
        return 18, 4100

    monkeypatch.setattr(cursos_robo, "para_o_claude", para_o_claude)
    video = tmp_path / "aula.mkv"
    video.write_bytes(b"video")
    pasta, info = cursos_robo.guardar_a_aula(str(video), 1, 7, "o vídeo parou", _br("2026-11-23 23:30"))
    assert os.path.basename(pasta) == "20261123-233000-c01-a007"
    assert not video.exists() and pedidos == [90]
    assert info == {"curso": 1, "aula": 7, "gravada_em": "2026-11-23 23:30:00", "fim": "o vídeo parou",
                    "segundos": 1800, "som": -20.0, "brilho": 90, "folhas": 18, "palavras": 4100, "problema": ""}
    import json
    assert json.loads((tmp_path / "aulas" / os.path.basename(pasta) / "aula.json").read_text()) == info
    assert cursos_robo.aulas_guardadas() == ["20261123-233000-c01-a007"]


def test_pacote_das_aulas_ate_o_tamanho_e_o_apagar_so_das_que_foram(monkeypatch, tmp_path):
    pasta = tmp_path / "aulas"
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_AULAS", str(pasta))
    monkeypatch.setattr(cursos_robo, "TAMANHO_DO_PACOTE", 250)
    nomes = ["20261123-230000-c01-a001", "20261123-233000-c01-a002", "20261124-001000-c01-a003"]
    for nome in nomes:
        (pasta / nome).mkdir(parents=True)
        (pasta / nome / "fala.txt").write_bytes(b"x" * 100)
    (pasta / "outra-coisa").mkdir()
    assert cursos_robo.aulas_guardadas() == nomes
    assert cursos_robo.aulas_do_pacote() == nomes[:2]
    assert cursos_robo.aulas_do_pacote(ate=nomes[0]) == nomes[:1]
    monkeypatch.setattr(cursos_robo, "TAMANHO_DO_PACOTE", 10)
    assert cursos_robo.aulas_do_pacote() == nomes[:1]   # ao menos uma, mesmo maior que o pacote
    assert cursos_robo.apagar_aulas(nomes[1]) == 2
    assert cursos_robo.aulas_guardadas() == nomes[2:]


def test_aulas_vao_cifradas_e_so_abrem_com_a_chave(monkeypatch, tmp_path):
    from cryptography.fernet import Fernet
    import registro_privado
    pasta = tmp_path / "aulas"
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_AULAS", str(pasta))
    (pasta / "20261123-230000-c01-a001").mkdir(parents=True)
    (pasta / "20261123-230000-c01-a001" / "fala.txt").write_text("[0.0s] conteúdo da aula")
    chave = Fernet.generate_key()
    monkeypatch.setattr(registro_privado, "chave", lambda: chave)
    texto = cursos_robo.cifrado_das_aulas()
    assert texto.startswith("gAAAAA") and "conteúdo" not in texto
    destino = tmp_path / "aberto"
    assert cursos_robo.abrir_aulas(texto, chave.decode(), str(destino)) == ["20261123-230000-c01-a001"]
    assert (destino / "20261123-230000-c01-a001" / "fala.txt").read_text() == "[0.0s] conteúdo da aula"


def test_comando_das_aulas_do_workflow_so_com_contagens_e_nomes_de_pasta(monkeypatch, tmp_path, capsys):
    from cryptography.fernet import Fernet
    import registro_privado
    pasta = tmp_path / "aulas"
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_AULAS", str(pasta))
    nomes = ["20261123-230000-c01-a001", "20261123-233000-c01-a002"]
    for nome in nomes:
        (pasta / nome).mkdir(parents=True)
        (pasta / nome / "fala.txt").write_text("[0.0s] conteúdo da aula")
    chave = Fernet.generate_key()
    monkeypatch.setattr(registro_privado, "chave", lambda: chave)

    def rodar(*argumentos):
        codigo = cursos_robo.main(["aulas", *argumentos])
        return codigo, capsys.readouterr().out.strip()
    assert rodar("contar") == (0, "2")
    assert rodar("ultima") == (0, nomes[1])
    codigo, texto = rodar("cifrado", nomes[0])
    assert codigo == 0 and texto.startswith("gAAAAA") and "conteúdo" not in texto
    # O ler, no scratchpad do Claude, abre com a chave do ambiente dele.
    arquivo = tmp_path / "aulas.zip.cifrado"
    arquivo.write_text(texto)
    monkeypatch.setenv(registro_privado.VARIAVEL_CHAVE, chave.decode())
    codigo, saida = rodar("ler", str(arquivo), str(tmp_path / "aberto"))
    assert codigo == 0 and saida.splitlines()[0].startswith("1 aula(s)") and nomes[0] in saida
    assert "conteúdo" not in saida
    # O apagar só aceita o nome de uma aula, e tira só até ela.
    assert rodar("apagar", "../outra")[0] == 2 and cursos_robo.aulas_guardadas() == nomes
    assert rodar("apagar", nomes[0]) == (0, "1 aula(s) apagada(s) do servidor.")
    assert cursos_robo.aulas_guardadas() == nomes[1:]
    assert rodar("outra")[0] == 2

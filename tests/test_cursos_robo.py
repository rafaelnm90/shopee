"""O gravador das aulas do curso pelo celular do robô (cursos_robo, P288 3)."""
import hashlib
import json
import os
import shutil
import subprocess

import pytest

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

    def __init__(self, entra_pelo_enter=True, senha_sem_cursor=False, preenchimento=False):
        self.foco, self.teclado, self.entrou = None, False, False
        self.campos = {"email": "", "senha": ""}
        self.toques, self.teclas = [], []
        self.entra_pelo_enter, self.senha_sem_cursor = entra_pelo_enter, senha_sem_cursor
        # A janela do gerenciador de senhas do Chrome (23/11/2026): abre no 1º toque num campo, cobre a página e sai
        # pela tecla voltar, sem deixar o cursor no campo.
        self.preenchimento, self.folha, self.folha_fechada = preenchimento, False, False

    def _caixas(self):
        sobe = 560 if self.teclado else 0
        return {"email": (42, 1369 - sobe, 1039, 1492 - sobe), "senha": (42, 1542 - sobe, 900, 1666 - sobe)}

    def dump_hierarchy(self):
        if self.entrou:
            return TELA_DO_CURSO
        if self.folha:
            return ('<hierarchy><node class="android.widget.TextView" '
                    'resource-id="com.android.chrome:id/touch_to_fill_sheet_title" text="Usar a senha salva?" '
                    'bounds="[0,1780][1080,1850]" /><node class="android.widget.Button" '
                    'resource-id="com.android.chrome:id/touch_to_fill_button_title" text="Continuar" '
                    'bounds="[40,2200][1040,2340]" /></hierarchy>')
        nos = "".join(
            f'<node class="android.widget.EditText" text="" password="{str(nome == "senha").lower()}" '
            f'focused="{str(self.foco == nome).lower()}" bounds="[{x1},{y1}][{x2},{y2}]" />'
            for nome, (x1, y1, x2, y2) in self._caixas().items())
        return (f'<hierarchy>{nos}<node class="android.widget.Button" text="Entrar" '
                'bounds="[42,1800][1039,1900]" /></hierarchy>')

    def click(self, x, y):
        self.toques.append((x, y))
        for nome, (x1, y1, x2, y2) in self._caixas().items():
            if x1 <= x <= x2 and y1 <= y <= y2 and self.preenchimento and not self.folha_fechada:
                self.folha = True
            elif x1 <= x <= x2 and y1 <= y <= y2 and not (nome == "senha" and self.senha_sem_cursor):
                self.foco, self.teclado = nome, True

    def escrever(self, texto):
        if self.foco:
            self.campos[self.foco] = texto

    def press(self, tecla):
        self.teclas.append(tecla)
        if tecla == "back" and self.folha:
            self.folha, self.folha_fechada = False, True
            return
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


def test_entrar_no_curso_fecha_a_janela_de_senhas_do_chrome_e_escreve_o_login_guardado(bm):
    # 23/11/2026, 10:05: o toque no campo do e-mail abriu a janela do gerenciador de senhas do Chrome, que cobre a
    # página, e o login parou ("o cursor não ficou no campo certo"). Ela sai pela tecla voltar, sem nada escolhido nela,
    # e o campo é tocado de novo.
    _guardar_o_acesso(link="https://curso.exemplo.com", email=EMAIL_DO_TESTE, senha=SENHA_DO_TESTE)
    celular = PaginaDeLogin(preenchimento=True)
    escrever = lambda d, texto: d.escrever(texto)
    achar = lambda tela, alvo: None
    assert cursos_robo.entrar_no_curso(celular, escrever, achar, pausa=lambda s: None) == (True, "login feito")
    assert celular.campos == {"email": EMAIL_DO_TESTE, "senha": SENHA_DO_TESTE}
    assert celular.teclas == ["back", "enter"] and celular.toques[:2] == [(540, 1430), (540, 1430)]
    assert all(not (40 <= x <= 1040 and 2200 <= y <= 2340) for x, y in celular.toques)


def test_entrar_no_curso_nunca_escreve_a_senha_fora_do_campo_de_senha(bm):
    _guardar_o_acesso(link="https://curso.exemplo.com", email=EMAIL_DO_TESTE, senha=SENHA_DO_TESTE)
    celular = PaginaDeLogin(senha_sem_cursor=True)
    escrever = lambda d, texto: d.escrever(texto)
    assert cursos_robo.entrar_no_curso(celular, escrever, lambda tela, alvo: None, pausa=lambda s: None) == (
        False, "o cursor não ficou no campo certo do login")
    # O cursor ficou no e-mail: a senha não foi escrita em lugar nenhum, e nada foi enviado.
    assert celular.campos == {"email": EMAIL_DO_TESTE, "senha": ""} and celular.teclas == []


# A página de uma aula, na forma que o Chrome do Motorola mostra (22/11/2026), com nomes e endereço inventados.
TELA_DA_AULA = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node class="android.widget.EditText" resource-id="com.android.chrome:id/url_bar" clickable="true"
        text="escola.exemplo.pro/m/lessons/abcDEF123_x-y" content-desc="" bounds="[211,120][691,267]" />
  <node class="android.widget.ToggleButton" resource-id="" clickable="true" text="" content-desc="Tocar vídeo"
        bounds="[191,996][280,1083]" />
  <node class="android.widget.ToggleButton" resource-id="" clickable="true" text="" content-desc="Tocar vídeo"
        bounds="[475,729][603,857]" />
  <node class="android.view.View" resource-id="" clickable="false" text="" content-desc=""
        bounds="[42,1112][1039,2075]">
    <node class="android.widget.Button" resource-id="" clickable="true" text="Aula de exemplo um 8:03"
          content-desc="" bounds="[178,1204][942,1290]" />
    <node class="android.widget.Button" resource-id="" clickable="true"
          text="Aula de exemplo dois com nome comprido 28:58" content-desc="" bounds="[178,1508][942,1608]" />
    <node class="android.widget.Button" resource-id="" clickable="true" text="Encontro gravado 1:02:03"
          content-desc="" bounds="[178,1674][942,1760]" />
  </node>
  <node class="android.widget.Button" resource-id="radix-_r_5p_" clickable="true" text="68% Módulo de exemplo"
        content-desc="" bounds="[42,1912][1010,2036]" />
  <node class="android.widget.Button" resource-id="" clickable="true" text="Próximo: Aula de exemplo dois"
        content-desc="" bounds="[0,2175][1080,2394]" />
</hierarchy>"""


def test_a_pagina_da_aula_lida_pela_tela_do_chrome():
    # Mapa do site de 22/11/2026: a linha da aula traz a duração, a barra do Chrome o endereço, e o "Próximo:" leva à
    # aula seguinte. O botão do módulo (sem duração) não é aula.
    assert cursos_robo.segundos_do_tempo("4:54") == 294 and cursos_robo.segundos_do_tempo("1:02:03") == 3723
    assert cursos_robo.linhas_das_aulas(TELA_DA_AULA) == [
        ("Aula de exemplo um", 483, (560, 1247)), ("Aula de exemplo dois com nome comprido", 1738, (560, 1558)),
        ("Encontro gravado", 3723, (560, 1717))]
    assert cursos_robo.endereco_da_aula(TELA_DA_AULA) == "https://escola.exemplo.pro/m/lessons/abcDEF123_x-y"
    assert cursos_robo.botao_do_proximo(TELA_DA_AULA) == (540, 2284)
    # O play do meio do player, o maior dos dois "Tocar vídeo".
    assert cursos_robo.botao_do_play(TELA_DA_AULA) == (539, 793)
    # Fora de uma aula (a página dos cursos), na última aula (sem o Próximo) e com o player fora da tela: nada.
    fora = TELA_DA_AULA.replace("/m/lessons/abcDEF123_x-y", "/m/courses").replace("Próximo: ", "Comentar ")
    fora = fora.replace('content-desc="Tocar vídeo"', 'content-desc=""')
    assert cursos_robo.endereco_da_aula(fora) is None
    assert cursos_robo.botao_do_proximo(fora) is None and cursos_robo.botao_do_play(fora) is None
    assert cursos_robo.linhas_das_aulas("<quebrado") == [] and cursos_robo.endereco_da_aula("") is None


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


def test_madrugada_e_fora_do_horario_do_robo_e_antes_das_3h45(monkeypatch):
    # P289 1: grava de madrugada, fora do Horário do Robô, parando antes da limpeza das 4h.
    horario = {"robo_inicio": 8, "robo_fim": 22}
    for hora, vale in (("21:59", False), ("22:00", True), ("23:30", True), ("00:30", True), ("03:44", True),
                       ("03:45", False), ("04:00", False), ("07:59", False), ("12:00", False)):
        assert cursos_robo.na_madrugada(horario, _br(f"2026-11-23 {hora}")) is vale, hora
    # Enquanto o curso não termina, a madrugada da 0h às 3h45 é dele, também com o Horário do Robô no Dia Todo ou
    # começando antes das 4h: o robô começa às 4h (P296 1).
    monkeypatch.setattr(cursos_robo, "CURSO_EM_ANDAMENTO", True)
    for horario in ({"robo_inicio": 0, "robo_fim": 24}, {"robo_inicio": 2, "robo_fim": 22}):
        for hora, vale in (("00:00", True), ("02:30", True), ("03:44", True), ("03:45", False), ("04:00", False)):
            assert cursos_robo.na_madrugada(horario, _br(f"2026-11-23 {hora}")) is vale, (horario, hora)


def test_p296_o_robo_comeca_as_4h_so_enquanto_o_curso_nao_acaba(monkeypatch):
    # P296 1: com o Horário do Robô no Dia Todo, o robô fica das 4h às 24h até o curso acabar; depois, o do painel.
    monkeypatch.setattr(cursos_robo, "CURSO_EM_ANDAMENTO", True)
    assert cursos_robo.horario_do_robo(0, 24) == (4, 24)
    assert cursos_robo.horario_do_robo(2, 22) == (4, 22)
    assert cursos_robo.horario_do_robo(8, 22) == (8, 22)
    assert cursos_robo.horario_do_robo(4, 24) == (4, 24)
    monkeypatch.setattr(cursos_robo, "CURSO_EM_ANDAMENTO", False)
    assert cursos_robo.horario_do_robo(0, 24) == (0, 24)
    assert cursos_robo.horario_do_robo(2, 22) == (2, 22)
    # Terminado o curso, o Dia Todo volta a não ter madrugada, e o Horário que começa às 2h a encurta.
    assert not cursos_robo.na_madrugada({"robo_inicio": 0, "robo_fim": 24}, _br("2026-11-23 02:00"))
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
    """
    O celular de mentira com a aula no Chrome: a página abre como em abre (o tipo e o porquê de ir_para_o_endereco),
    toca no play e para sozinha aos `dura` s.
    """

    def __init__(self, relogio, dura=60, carrega=False, abre=("com vídeo", ""), **opcoes):
        super().__init__(**opcoes)
        self.relogio, self.dura, self.carrega, self.abre = relogio, dura, carrega, abre
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


def _gravar_a_aula(celular, tmp_path, tempo, quando=None, madrugada=lambda: True, gravador_vivo=True, **opcoes):
    """
    Grava a aula de mentira com o relógio de mentira; quando(t) roda a cada pausa (o robô pede, o gravador cai). As
    opcoes vão à gravação (o maximo do teste de dia).
    """
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

    def ir_para_a_aula(d):
        # A página abre com o gravador já gravando: o vídeo pode começar sozinho com ela.
        celular.eventos.append("abriu gravando" if gravadores and gravadores[0].vivo else "abriu sem gravar")
        return celular.abre

    destino = str(tmp_path / "aula.mkv")
    feito = cursos_robo.gravar_a_aula(celular, "celular:5555", destino, ir_para_a_aula, celular.tocar, pausa=pausa,
                                      relogio=lambda: tempo[0], abrir=abrir, madrugada=madrugada, **opcoes)
    return feito, destino, gravadores


def test_aula_aberta_gravada_inteira_com_o_volume_de_volta_antes_de_o_gravador_parar(bm, tmp_path):
    # P291 1 e o pedido de 22/11 (o celular no quarto do Rafael): o gravador liga antes de o volume subir e
    # para só depois de a aula pausar e o volume voltar. A página da aula abre já com ele gravando (23/11: o vídeo
    # pode começar sozinho com a página, e o começo dele fica na gravação).
    tempo = [0.0]
    celular = AulaNoCelular(lambda: tempo[0], dura=60, volume=2)
    feito, destino, gravadores = _gravar_a_aula(celular, tmp_path, tempo)
    assert feito == (True, True, "o vídeo parou")
    assert celular.eventos == ["volume 8", "abriu gravando", "play", "volume 2", "gravador parou"]
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
    assert feito == (True, False, "o robô pediu o celular")
    assert celular.eventos == ["volume 8", "abriu gravando", "play", "pausa", "volume 2", "gravador parou"]
    assert tempo[0] < 40 and celular.volume == 2


def test_gravador_que_cai_no_meio_pausa_a_aula_e_devolve_o_volume(bm, tmp_path):
    # Parado o gravador, o alto-falante volta a tocar: a aula pausa e o volume volta na hora.
    tempo = [0.0]
    celular = AulaNoCelular(lambda: tempo[0], dura=600, volume=2)

    def quando(agora, gravadores):
        if agora >= 20:
            gravadores[0].vivo = False

    feito, _, _ = _gravar_a_aula(celular, tmp_path, tempo, quando)
    assert feito == (True, False, "o gravador parou no meio")
    assert celular.eventos == ["volume 8", "abriu gravando", "play", "pausa", "volume 2"]


def test_o_teste_de_dia_grava_no_maximo_dez_minutos(bm, tmp_path):
    # A noite grava até AULA_MAIS_LONGA de uma vez; o teste de dia (curso:gravar:N), até GRAVACAO_DO_TESTE.
    tempo = [0.0]
    celular = AulaNoCelular(lambda: tempo[0], dura=60, volume=2)
    feito, _, gravadores = _gravar_a_aula(celular, tmp_path, tempo, maximo=cursos_robo.GRAVACAO_DO_TESTE)
    assert feito == (True, True, "o vídeo parou") and "--time-limit=600" in gravadores[0].comando
    tempo = [0.0]
    _, _, gravadores = _gravar_a_aula(AulaNoCelular(lambda: tempo[0], dura=60), tmp_path, tempo)
    assert f"--time-limit={cursos_robo.AULA_MAIS_LONGA}" in gravadores[0].comando


def test_gravador_que_nao_grava_o_som_nao_deixa_a_aula_tocar(bm, tmp_path):
    # Sem o som da gravação, o --require-audio para o gravador, e o alto-falante não ficaria mudo.
    tempo = [0.0]
    celular = AulaNoCelular(lambda: tempo[0], volume=2)
    feito, _, _ = _gravar_a_aula(celular, tmp_path, tempo, gravador_vivo=False)
    assert feito == (False, False, "o gravador não ficou gravando")
    assert celular.eventos == [] and celular.volume == 2


def test_madrugada_que_acaba_e_video_que_nao_carrega_param_a_aula(bm, tmp_path):
    # Às 3h45 (P289 1), a aula para pela metade, antes do descurtir das 4h.
    tempo = [0.0]
    celular = AulaNoCelular(lambda: tempo[0], dura=600, volume=2)
    feito, _, _ = _gravar_a_aula(celular, tmp_path, tempo, madrugada=lambda: tempo[0] < 40)
    assert feito == (True, False, "a madrugada acabou")
    assert celular.eventos[-3:] == ["pausa", "volume 2", "gravador parou"]
    # O vídeo que fica carregando não conta como aula inteira.
    tempo = [0.0]
    cursos_robo._anotar(volume_antes=None)
    celular = AulaNoCelular(lambda: tempo[0], dura=600, carrega=True, volume=2)
    feito, _, _ = _gravar_a_aula(celular, tmp_path, tempo)
    assert feito == (True, False, "carregando demais")
    assert celular.eventos[-2:] == ["volume 2", "gravador parou"]


def test_a_pagina_que_nao_abre_ou_sem_video_nao_toca_e_o_volume_volta(bm, tmp_path):
    # A aula que não abriu (o endereço que não ficou na barra) e a aula sem vídeo: nada de play, e o volume volta
    # antes de o gravador parar, como no fim de qualquer aula.
    for abre, feito_esperado in ((None, "o endereço não ficou escrito na barra"),
                                 ("sem vídeo", "")):
        tempo = [0.0]
        cursos_robo._anotar(volume_antes=None)
        celular = AulaNoCelular(lambda: tempo[0], volume=2, abre=(abre, feito_esperado))
        feito, _, _ = _gravar_a_aula(celular, tmp_path, tempo)
        esperado = ((False, False, "a aula não abriu (o endereço não ficou escrito na barra)") if abre is None
                    else (True, False, "sem vídeo"))
        assert feito == esperado
        assert celular.eventos == ["volume 8", "abriu gravando", "volume 2", "gravador parou"]


CHROME = "com.android.chrome"


class SiteDoCurso(CelularDoVolume):
    """
    O Chrome de mentira com o site do curso: as aulas em ordem [(nome, segundos, endereço[, tipo])], a barra de
    endereço, o player (só com a página no alto) e a barra do Próximo. O endereço vai à barra pelo adb, tecla por tecla,
    e o Enter abre a aula escrita. O Próximo troca a aula na mesma página, do alto, e o endereço da barra continua o da
    aula aberta pelo Enter, como no site de verdade (23/11/2026). Com outro app na frente (na_frente), só ele aparece na
    tela; abre_o_chrome=False: o Chrome não vem para a frente. A aula de tipo "documento" não tem player: tem o leitor
    de PDF com o Baixar, o texto com o "Ver mais", um link e as abas; a de tipo "texto longo" tem o texto em duas telas
    (as abas aparecem depois de rolar). autoplay: a página aberta começa a tocar sozinha (sem o play na tela);
    escreve=False: o que vai pelo adb não chega à barra; completa: o pedaço que o Chrome completa sozinho depois do
    escrito, marcado; rotulo_no_texto: o nome do play no texto do botão, como no Motorola. aberturas: (volume,
    gravando) de cada aula aberta (pelo Enter ou pelo Próximo). nova_guia: o Chrome na página de Nova guia (a caixa de
    busca dela abre a barra); barra_escondida: a página rolada para baixo, sem a barra no alto (rolar para cima a traz,
    se a rolagem funciona). baixa: o Baixar do leitor de PDF baixa o documento; aviso: quantas leituras da tela o aviso
    do download do Chrome fica nela. texto_na_videoaula: a página da videoaula tem, embaixo do vídeo, um texto e um
    link. volumes_das_telas: o volume de mídia em cada print da tela. A aula de tipo "slides" é um carrossel de
    imagens (slides: quantas), com o Anterior e o Próximo dele; carrossel_volta: o Próximo do último volta ao 1º.
    """

    def __init__(self, aulas, aberta=0, no_alto=False, play_toca=True, na_frente=CHROME, abre_o_chrome=True,
                 autoplay=False, escreve=True, completa="", rotulo_no_texto=False, nova_guia=False,
                 barra_escondida=False, rolagem_funciona=True, sessao_vencida=False, inicio_na_guia_nova=False,
                 outro_site=False, baixa=True, aviso=2, atraso_do_proximo=0, baixar_sai=False,
                 texto_na_videoaula=False, slides=4, carrossel_volta=False, **opcoes):
        super().__init__(**opcoes)
        # A página fora das aulas em que o Enter caiu: "login" (a sessão vencida), "inicio" (a página inicial do
        # curso, pela guia nova) ou "outro" (outro site); None na aula aberta.
        self.logado, self.inicio_na_guia_nova, self.outro_site = not sessao_vencida, inicio_na_guia_nova, outro_site
        self.pagina, self.logins = None, []
        self.nova_guia, self.barra_escondida, self.rolagem_funciona = nova_guia, barra_escondida, rolagem_funciona
        self.rolagens = []
        self.aulas, self.aberta, self.no_alto, self.play_toca = aulas, aberta, no_alto, play_toca
        self.endereco_na_barra = aulas[aberta][2]
        self.escrito, self.barra_em_foco, self.toques = None, False, []
        self.na_frente, self.abre_o_chrome, self.abertos = na_frente, abre_o_chrome, []
        self.autoplay, self.escreve, self.completa, self.rotulo_no_texto = autoplay, escreve, completa, rotulo_no_texto
        self.aberturas, self.gravando, self.teclas = [], False, []
        self.baixa, self.aviso_do_download, self.aviso = baixa, aviso, 0
        self.baixados, self.marcado, self.ver_mais_aberto, self.rolada, self.puxados = [], False, False, 0, []
        # O Próximo que só aparece depois de algumas leituras da página nova (ela ainda carrega) e o Baixar que abre o
        # documento no lugar da página da aula.
        self.atraso_do_proximo, self.sem_o_proximo, self.baixar_sai = atraso_do_proximo, 0, baixar_sai
        self.texto_na_videoaula, self.volumes_das_telas = texto_na_videoaula, []
        self.slides, self.carrossel_volta, self.slide = slides, carrossel_volta, 0

    def _tipo(self, numero):
        return self.aulas[numero][3] if len(self.aulas[numero]) > 3 else "vídeo"

    def _com_video(self, numero):
        return self._tipo(numero) == "vídeo"

    def _tocando(self):
        return "state=3," in self.midia or "PLAYING(3)" in self.midia

    def _player(self):
        if not self._com_video(self.aberta):
            return []
        nos = ['<node class="android.widget.SeekBar" resource-id="plyr-seek-1" clickable="true" text="" '
               'content-desc="" bounds="[380,1015][417,1067]" />']
        if self._tocando():
            return nos
        rotulo = 'text="Tocar vídeo" content-desc=""' if self.rotulo_no_texto else 'text="" content-desc="Tocar vídeo"'
        return nos + [f'<node class="android.widget.ToggleButton" resource-id="" clickable="true" {rotulo} '
                      f'bounds="{caixa}" />' for caixa in ("[191,996][280,1083]", "[475,729][603,857]")]

    def _sem_video(self):
        """O leitor de PDF, o texto e o link da aula sem vídeo (como no site, 23/11/2026)."""
        nos = []
        if self._tipo(self.aberta) == "slides":
            # O carrossel da 3ª aula do curso 5 (23/11/2026, 12:53): o Anterior e o Próximo dele, a imagem da aula
            # (e a seguinte, quase fora da tela) e as miniaturas.
            return ['<node class="android.widget.Button" resource-id="" clickable="true" text="Anterior" '
                    'content-desc="" bounds="[157,763][220,826]" />',
                    '<node class="android.widget.Button" resource-id="" clickable="true" text="Próximo" '
                    'content-desc="" bounds="[858,763][921,826]" />',
                    '<node class="android.widget.Image" resource-id="" clickable="false" text="" '
                    'content-desc="Imagem da aula" bounds="[141,540][937,991]" />',
                    '<node class="android.widget.Image" resource-id="" clickable="false" text="" '
                    'content-desc="Imagem da aula" bounds="[968,540][1080,991]" />',
                    '<node class="android.widget.Button" resource-id="" clickable="true" text="imagem do carrossel" '
                    'content-desc="" bounds="[141,1015][346,1133]" />',
                    '<node class="android.widget.TextView" resource-id="" text="Instruções da aula" content-desc="" '
                    'bounds="[42,1285][1021,1335]" />'], "[60,1555][336,1747]"
        if self._tipo(self.aberta) == "documento":
            nos += ['<node class="android.widget.TextView" resource-id="p8R_mc0" text="Lista de produtos do dia" '
                    'content-desc="" bounds="[86,820][900,876]" />',
                    '<node class="android.widget.Button" resource-id="" clickable="true" text="" '
                    'content-desc="Diminuir zoom" bounds="[252,1437][322,1508]" />',
                    '<node class="android.widget.Button" resource-id="" clickable="true" text="" content-desc="Baixar" '
                    'bounds="[595,1437][669,1508]" />',
                    '<node class="android.widget.Button" resource-id="" clickable="true" text="" '
                    'content-desc="Imprimir" bounds="[669,1437][740,1508]" />',
                    '<node class="android.widget.TextView" resource-id="" text="Sobre a lista" content-desc="" '
                    'bounds="[42,1653][1021,1702]" />',
                    '<node class="android.view.View" resource-id="" clickable="false" text="Veja o material abaixo:" '
                    'content-desc="" bounds="[42,1870][924,1915]" />',
                    '<node class="android.view.View" resource-id="" clickable="true" text="" '
                    'content-desc="Clique aqui e entre no grupo" bounds="[42,1920][787,1965]">'
                    '<node class="android.view.View" resource-id="" clickable="false" '
                    'text="Clique aqui e entre no grupo" content-desc="" bounds="[42,1920][787,1965]" /></node>']
            if self.ver_mais_aberto:
                nos.append('<node class="android.widget.TextView" resource-id="" text="Use a lista para escolher." '
                           'content-desc="" bounds="[42,1970][1000,2030]" />')
            else:
                nos.append('<node class="android.widget.Button" resource-id="" clickable="true" text="Ver mais" '
                           'content-desc="" bounds="[42,1968][189,2054]" />')
            return nos, "[60,2109][336,2301]"
        if self.rolada == 0:
            return ['<node class="android.widget.TextView" resource-id="" text="Parte um da aula" content-desc="" '
                    'bounds="[42,600][1021,700]" />',
                    '<node class="android.widget.TextView" resource-id="" text="Parte dois da aula" content-desc="" '
                    'bounds="[42,2200][1021,2300]" />'], "[60,2600][336,2790]"
        return ['<node class="android.widget.TextView" resource-id="" text="Parte dois da aula" content-desc="" '
                'bounds="[42,500][1021,600]" />',
                '<node class="android.widget.TextView" resource-id="" text="Parte três da aula" content-desc="" '
                'bounds="[42,700][1021,800]" />'], "[60,1200][336,1390]"

    def app_current(self):
        return {"package": self.na_frente, "activity": ""}

    def app_start(self, pacote, wait=False):
        self.abertos.append(pacote)
        if self.abre_o_chrome:
            self.na_frente = pacote

    def dump_hierarchy(self):
        if self.na_frente != CHROME:
            return ('<hierarchy rotation="0"><node class="android.widget.TextView" resource-id="" clickable="true" '
                    'text="Eu" content-desc="" bounds="[880,2250][1080,2394]" /></hierarchy>')
        if self.nova_guia and not self.barra_em_foco:
            return ('<hierarchy rotation="0"><node class="android.widget.EditText" '
                    'resource-id="com.android.chrome:id/search_box_text" clickable="true" text="" content-desc="" '
                    'bounds="[100,540][840,626]" /></hierarchy>')
        if self.pagina and not self.barra_em_foco:
            endereco, resto = PAGINAS_FORA_DAS_AULAS[self.pagina]
            return ('<hierarchy rotation="0"><node class="android.widget.EditText" '
                    'resource-id="com.android.chrome:id/url_bar" clickable="true" '
                    f'text="{endereco}" content-desc="" bounds="[211,120][691,267]" />{resto}</hierarchy>')
        barra = self.endereco_na_barra.removeprefix("https://")
        if self.barra_em_foco and self.escrito is not None:
            barra = self.escrito
        fora = [] if self.barra_escondida and not self.barra_em_foco else [
            '<node class="android.widget.EditText" resource-id="com.android.chrome:id/url_bar" clickable="true" '
            f'text="{barra}" content-desc="" bounds="[211,120][691,267]" />']
        nos = self._player() if self.no_alto else []
        abas = "[60,1466][336,1658]"
        if not self._com_video(self.aberta):
            nos, abas = self._sem_video()
        elif self.texto_na_videoaula:
            nos += ['<node class="android.widget.TextView" resource-id="" text="Tarefa da aula" content-desc="" '
                    'bounds="[42,1200][1021,1260]" />',
                    '<node class="android.view.View" resource-id="" clickable="true" text="" '
                    'content-desc="Planilha de apoio" bounds="[42,1300][787,1345]">'
                    '<node class="android.view.View" resource-id="" clickable="false" text="Planilha de apoio" '
                    'content-desc="" bounds="[42,1300][787,1345]" /></node>']
        nos.append('<node class="android.view.View" resource-id="radix-_r_m_-trigger-modules" clickable="true" '
                   f'text="Módulos" content-desc="" bounds="{abas}" />')
        if self.sem_o_proximo:
            self.sem_o_proximo -= 1
        elif self.aberta + 1 < len(self.aulas):
            nome = self.aulas[self.aberta + 1][0]
            nos.append('<node class="android.widget.Button" resource-id="" clickable="true" content-desc="" '
                       f'text="Próximo: {nome} Próxima aula:" bounds="[0,2175][1080,2394]" />')
        if self.aviso:
            self.aviso -= 1
            fora.append('<node class="android.widget.TextView" resource-id="com.android.chrome:id/message_title" '
                        'clickable="false" text="Download concluído" content-desc="" bounds="[0,2200][1080,2300]" />')
        pagina = ('<node class="android.webkit.WebView" resource-id="" text="" content-desc="" '
                  'bounds="[0,267][1080,2394]">' + "".join(nos) + "</node>")
        return '<hierarchy rotation="0">' + "".join(fora[:1]) + pagina + "".join(fora[1:]) + "</hierarchy>"

    def screenshot(self):
        from PIL import Image, ImageDraw
        self.volumes_das_telas.append(self.volume)
        imagem = Image.new("RGB", (1080, 2400), (30, 30, 30))
        if self._tipo(self.aberta) == "slides":
            desenho = ImageDraw.Draw(imagem)
            desenho.rectangle((141, 540, 937, 991), fill=(250 - 40 * self.slide, 240, 200))
            desenho.rectangle((200 + 80 * self.slide, 600, 300 + 80 * self.slide, 700), fill=(200, 80, 40))
        return imagem

    def swipe(self, x1, y1, x2, y2, duracao=None):
        self.rolagens.append((x1, y1, x2, y2))
        if y2 > y1 and not self.barra_escondida and not self.rolada and not self.pagina and not self.nova_guia:
            # No alto da página, o arrasto para baixo é o "puxar para atualizar" do Chrome: a página recarrega o
            # endereço da barra, que o Próximo não muda (a aula aberta pela barra volta).
            self._abrir(next(n for n, aula in enumerate(self.aulas) if aula[2] == self.endereco_na_barra))
        if y2 > y1 and self.rolagem_funciona:
            self.barra_escondida = False
        if y1 > y2 and self._tipo(self.aberta) == "texto longo":
            self.rolada = 1

    def _abrir(self, numero):
        self.aberta, self.no_alto, self.ver_mais_aberto, self.rolada, self.slide = numero, True, False, 0, 0
        self.sem_o_proximo = self.atraso_do_proximo
        self.midia = _sessao_do_chrome(3, 0) if self.autoplay and self._com_video(numero) else SEM_SESSOES

    def click(self, x, y):
        self.toques.append((x, y))
        if self.nova_guia and 100 <= x <= 840 and 540 <= y <= 626 and not self.barra_em_foco:
            self.barra_em_foco, self.escrito = True, None
        elif 211 <= x <= 691 and 120 <= y <= 267 and not self.barra_escondida:
            self.barra_em_foco, self.escrito = True, None
        elif (x, y) == (539, 793) and self.no_alto and self.play_toca and self._com_video(self.aberta):
            self.midia = _sessao_do_chrome(3, 1)
        elif (x, y) == (632, 1472) and self._tipo(self.aberta) == "documento" and self.baixa:
            self.baixados.append(("/sdcard/Download/Lista do dia.pdf", 2048))
            self.aviso = self.aviso_do_download
            if self.baixar_sai:
                self.pagina = "documento"
        elif (x, y) == (115, 2011) and self._tipo(self.aberta) == "documento":
            self.ver_mais_aberto = True
        elif (x, y) == (889, 794) and self._tipo(self.aberta) == "slides":
            if self.slide + 1 < self.slides:
                self.slide += 1
            elif self.carrossel_volta:
                self.slide = 0
        elif y >= 2175 and self.aberta + 1 < len(self.aulas):
            self.aberturas.append((self.volume, self.gravando))
            self._abrir(self.aberta + 1)

    def press(self, tecla):
        self.teclas.append(tecla)
        if tecla == "back":
            self.barra_em_foco = False

    def pull(self, remoto, local):
        self.puxados.append(remoto)
        with open(local, "wb") as arquivo:
            arquivo.write(b"%PDF-1.4 lista do dia")

    def shell(self, partes):
        import types
        if partes[:2] == ["input", "text"] and self.barra_em_foco and self.escreve:
            self.escrito = partes[2] + self.completa
        if partes == ["input", "keyevent", "KEYCODE_FORWARD_DEL"]:
            if self.barra_em_foco and self.completa and (self.escrito or "").endswith(self.completa):
                self.escrito = self.escrito[:-len(self.completa)]
        if partes == ["input", "keyevent", "KEYCODE_ENTER"] and self.barra_em_foco:
            self.aberturas.append((self.volume, self.gravando))
            alvo = next((n for n, aula in enumerate(self.aulas) if aula[2] == self.escrito), None)
            if alvo is not None and self.outro_site:
                self.pagina = "outro"
            elif alvo is not None and not self.logado:
                self.pagina = "login"
            elif alvo is not None and self.nova_guia and self.inicio_na_guia_nova:
                self.pagina, self.nova_guia = "inicio", False
            elif alvo is not None:
                self.nova_guia, self.pagina, self.endereco_na_barra = False, None, self.aulas[alvo][2]
                self._abrir(alvo)
            self.barra_em_foco = False
        if partes[:1] == ["touch"]:
            self.marcado = True
        if partes[:2] == ["find", cursos_robo.PASTA_DOS_BAIXADOS] and self.marcado:
            saida = "".join(f"1700000100 {tamanho} {caminho}\n" for caminho, tamanho in self.baixados)
            self.comandos.append(partes)
            return types.SimpleNamespace(output=saida, exit_code=0)
        if partes[:2] == ["rm", "-f"]:
            self.baixados = [item for item in self.baixados if item[0] not in partes]
            self.marcado = self.marcado and cursos_robo.MARCA_DO_CURSO not in partes
        return super().shell(partes)


# As páginas fora das aulas: (o endereço na barra, o resto da tela).
PAGINAS_FORA_DAS_AULAS = {
    "login": ("escola.exemplo.pro/login",
              '<node class="android.widget.EditText" text="" password="false" bounds="[42,1369][1039,1492]" />'
              '<node class="android.widget.EditText" text="" password="true" bounds="[42,1542][900,1666]" />'),
    "inicio": ("escola.exemplo.pro/m/courses",
               '<node class="android.widget.Button" resource-id="" clickable="true" text="Próximo" '
               'content-desc="" bounds="[800,900][960,1040]" />'),
    "outro": ("www.busca.exemplo.com/search?q=aula", ""),
    "documento": ("escola.exemplo.pro/arquivos/lista.pdf", ""),
}


def _login_de_mentira(passa=True):
    """O entrar da noite: anota com que volume e se gravando o login foi feito e, se passa, entra no site."""
    def entrar(d, pausa):
        d.logins.append((d.volume, d.gravando))
        if passa:
            d.logado, d.pagina = True, "inicio"
        return (True, "login feito") if passa else (False, "o login não passou (a página de login continua)")
    return entrar


AULAS_DO_SITE = [("Aula um", 300, "https://escola.exemplo.pro/m/lessons/aaa111"),
                 ("Aula dois", 600, "https://escola.exemplo.pro/m/lessons/bbb222"),
                 ("Aula três", 120, "https://escola.exemplo.pro/m/lessons/ccc333")]


SEM_ESPERA = {"pausa": lambda segundos: None}
AULA_DE_DOCUMENTO = ("Dia 01", 0, "https://escola.exemplo.pro/m/lessons/doc444", "documento")
AULA_DE_SLIDES = ("Instruções", 0, "https://escola.exemplo.pro/m/lessons/sli555", "slides")


def test_a_aula_abre_pelo_endereco_na_mesma_guia_e_do_alto():
    # O link por fora abria uma guia nova a cada vez (de 8 para 11 no mapa de 22/11/2026): a aula abre pela barra de
    # endereço da guia da frente, e a página nova vem do alto, com o play na tela.
    site = SiteDoCurso(AULAS_DO_SITE, aberta=0, no_alto=False)
    aberta = cursos_robo.ir_para_o_endereco(site, AULAS_DO_SITE[2][2], **SEM_ESPERA)
    assert aberta == ("com vídeo", "") and site.aberta == 2 and site.no_alto and site.toques == [(451, 193)]
    assert site.abertos == []                                           # o Chrome já estava na frente
    # O endereço que a página não abre: o porquê depois da espera.
    assert cursos_robo.ir_para_o_endereco(site, "https://escola.exemplo.pro/m/lessons/zzz999", **SEM_ESPERA) == (
        None, "o endereço da aula não ficou na barra")


def test_o_endereco_vai_a_barra_como_num_teclado_e_o_enter_so_com_ele_la():
    # Às 03:00, 03:15 e 03:30 de 23/11/2026, o texto posto pela acessibilidade aparecia na barra, mas o Enter abria
    # outra página (a do Gemini): o endereço vai pelo adb, tecla por tecla, e o Enter só vem com ele na barra.
    endereco = AULAS_DO_SITE[1][2]
    site = SiteDoCurso(AULAS_DO_SITE)
    assert cursos_robo.ir_para_o_endereco(site, endereco, **SEM_ESPERA) == ("com vídeo", "")
    escrito = site.comandos.index(["input", "text", endereco])
    assert site.comandos.index(["input", "keyevent", "KEYCODE_ENTER"]) > escrito
    # O pedaço que o Chrome completa sozinho sai com a tecla de apagar à frente, antes do Enter.
    completado = SiteDoCurso(AULAS_DO_SITE, completa="-outra")
    assert cursos_robo.ir_para_o_endereco(completado, endereco, **SEM_ESPERA) == ("com vídeo", "")
    assert completado.aberta == 1
    # O que não chega à barra: sem o Enter, a barra sai da edição, e a página de antes fica como estava.
    surdo = SiteDoCurso(AULAS_DO_SITE, escreve=False)
    assert cursos_robo.ir_para_o_endereco(surdo, endereco, **SEM_ESPERA) == (
        None, "o endereço não ficou escrito na barra")
    assert ["input", "keyevent", "KEYCODE_ENTER"] not in surdo.comandos and surdo.teclas == ["back"]
    assert surdo.aberta == 0


def test_a_aula_abre_pela_caixa_da_nova_guia_e_com_a_barra_escondida():
    # Depois de horas parado, o Chrome abre na página de Nova guia, sem a barra no alto (o teste de dia de 23/11/2026):
    # a caixa de busca dela abre a barra, e o endereço vai por ela.
    site = SiteDoCurso(AULAS_DO_SITE, nova_guia=True)
    assert cursos_robo.ir_para_o_endereco(site, AULAS_DO_SITE[1][2], **SEM_ESPERA) == ("com vídeo", "")
    assert site.toques == [(470, 583)] and site.aberta == 1
    # Com a página rolada para baixo, a barra some: rolar para cima a traz de volta.
    rolada = SiteDoCurso(AULAS_DO_SITE, barra_escondida=True)
    assert cursos_robo.ir_para_o_endereco(rolada, AULAS_DO_SITE[2][2], **SEM_ESPERA) == ("com vídeo", "")
    assert rolada.rolagens == [(540, 700, 540, 1500)] and rolada.aberta == 2
    # A barra que não volta: nada é tocado, e o porquê vai ao registro.
    presa = SiteDoCurso(AULAS_DO_SITE, barra_escondida=True, rolagem_funciona=False)
    assert cursos_robo.ir_para_o_endereco(presa, AULAS_DO_SITE[2][2], **SEM_ESPERA) == (
        None, "sem a barra de endereço do Chrome")
    assert presa.toques == []


def test_a_sessao_vencida_entra_com_o_acesso_guardado_e_abre_a_aula():
    # 23/11/2026, 09:53: horas depois do último login, o endereço da aula levou à página de login do site. O robô entra
    # com o acesso guardado (pedido do Rafael de 22/11) e escreve o endereço de novo.
    um = AULAS_DO_SITE[0][2]
    site = SiteDoCurso(AULAS_DO_SITE, aberta=2, sessao_vencida=True)
    entrar = _login_de_mentira()
    assert cursos_robo.ir_para_o_endereco(site, um, entrar=entrar, **SEM_ESPERA) == (cursos_robo.COM_VIDEO, "")
    assert len(site.logins) == 1 and len(site.aberturas) == 2
    assert cursos_robo.endereco_da_aula(site.dump_hierarchy()) == um
    # O login que não passa para ali, sem insistir.
    site = SiteDoCurso(AULAS_DO_SITE, aberta=2, sessao_vencida=True)
    assert cursos_robo.ir_para_o_endereco(site, um, entrar=_login_de_mentira(passa=False), **SEM_ESPERA) == (
        None, cursos_robo.SEM_O_LOGIN)
    assert len(site.logins) == 1 and len(site.aberturas) == 1


def test_a_guia_nova_que_leva_a_pagina_inicial_abre_a_aula_na_segunda_vez():
    # Pela caixa da Nova guia (o Chrome depois de horas parado), o endereço levou à página inicial do curso; na mesma
    # guia, a 2ª vez abre a aula. Uma página de outro site não é tentada de novo.
    um = AULAS_DO_SITE[0][2]
    site = SiteDoCurso(AULAS_DO_SITE, nova_guia=True, inicio_na_guia_nova=True)
    assert cursos_robo.ir_para_o_endereco(site, um, entrar=_login_de_mentira(), **SEM_ESPERA) == (
        cursos_robo.COM_VIDEO, "")
    assert len(site.aberturas) == 2 and site.logins == []
    fora = SiteDoCurso(AULAS_DO_SITE, outro_site=True)
    assert cursos_robo.ir_para_o_endereco(fora, um, entrar=_login_de_mentira(), **SEM_ESPERA) == (
        None, cursos_robo.SEM_O_ENDERECO)
    assert len(fora.aberturas) == 1 and fora.logins == []


def test_a_pagina_que_toca_sozinha_abriu_e_segue_sem_o_play():
    # Aberta pela barra, a página da aula pode começar a tocar sozinha, sem o play na tela: ela abriu, e o play não é
    # tocado (seria a pausa).
    site = SiteDoCurso(AULAS_DO_SITE, autoplay=True)
    assert cursos_robo.ir_para_o_endereco(site, AULAS_DO_SITE[1][2], **SEM_ESPERA) == ("com vídeo", "")
    assert cursos_robo.tocar_pelo_play(site, **SEM_ESPERA) and site.toques == [(451, 193)]


def test_o_play_pelo_texto_do_botao_como_no_motorola():
    # Na tela das 03:45 de 23/11/2026, a aula abriu com o player, mas o nome do play vinha no texto do botão, e a noite
    # procurava na descrição: vale qualquer um.
    motorola = TELA_DA_AULA.replace('text="" content-desc="Tocar vídeo"', 'text="Tocar vídeo" content-desc=""')
    assert 'text="Tocar vídeo"' in motorola and cursos_robo.botao_do_play(motorola) == (539, 793)
    site = SiteDoCurso(AULAS_DO_SITE, rotulo_no_texto=True)
    assert cursos_robo.ir_para_o_endereco(site, AULAS_DO_SITE[2][2], **SEM_ESPERA) == ("com vídeo", "")
    assert cursos_robo.tocar_pelo_play(site, **SEM_ESPERA) and site.toques[-1] == (539, 793)


def test_a_aula_sem_video_e_a_pagina_sem_o_play():
    # Há aulas que são um documento ou um texto (o vídeo do Rafael das 08:22 de 23/11/2026): a página pronta, com as
    # abas, sem player nenhum, nem depois de mais um tempo, é a aula sem vídeo.
    aulas = AULAS_DO_SITE[:1] + [AULA_DE_DOCUMENTO]
    assert cursos_robo.ir_para_o_endereco(SiteDoCurso(aulas), AULA_DE_DOCUMENTO[2], **SEM_ESPERA) == ("sem vídeo", "")

    # O player na página sem o play à vista e sem o vídeo tocando: o porquê leva o estado do vídeo.
    class SemPlay(SiteDoCurso):
        def _player(self):
            return super()._player()[:1]

    site = SemPlay(AULAS_DO_SITE, aberta=0)
    assert cursos_robo.ir_para_o_endereco(site, AULAS_DO_SITE[1][2], **SEM_ESPERA) == (
        None, "a página não mostrou o player; sem vídeo no Chrome")


def test_a_aula_abre_com_a_shopee_na_frente_trazendo_o_chrome():
    # A rodada do robô termina com a Shopee no Eu: o Chrome vem para a frente antes de o endereço da aula ir à barra.
    site = SiteDoCurso(AULAS_DO_SITE, aberta=0, na_frente="com.shopee.br")
    aberta = cursos_robo.ir_para_o_endereco(site, AULAS_DO_SITE[1][2], **SEM_ESPERA)
    assert aberta == ("com vídeo", "") and site.abertos == [CHROME] and site.aberta == 1
    # O Chrome que não vem para a frente (a tela de bloqueio por cima): nada é tocado, e o porquê vai ao registro.
    preso = SiteDoCurso(AULAS_DO_SITE, na_frente="com.android.systemui", abre_o_chrome=False)
    aberta = cursos_robo.ir_para_o_endereco(preso, AULAS_DO_SITE[1][2], **SEM_ESPERA)
    assert aberta == (None, "o Chrome não veio para a frente") and preso.toques == []


def test_o_play_da_aula_conferido_pela_sessao_de_midia():
    site = SiteDoCurso(AULAS_DO_SITE, no_alto=True)
    assert cursos_robo.tocar_pelo_play(site, **SEM_ESPERA) and site.toques == [(539, 793)]
    # Com o player fora da tela, nada é tocado; o play que não faz o vídeo tocar dá False, tocado uma vez só.
    rolada = SiteDoCurso(AULAS_DO_SITE, no_alto=False)
    assert not cursos_robo.tocar_pelo_play(rolada, **SEM_ESPERA) and rolada.toques == []
    parado = SiteDoCurso(AULAS_DO_SITE, no_alto=True, play_toca=False)
    assert not cursos_robo.tocar_pelo_play(parado, **SEM_ESPERA) and parado.toques == [(539, 793)]


def test_o_mapa_das_aulas_segue_a_ordem_dos_cursos_e_o_proximo_do_site(bm):
    # P293 1: os cursos pela posição na lista de Turmas (os de Shopee Vídeo primeiro, o dos encontros ao vivo por
    # último). A 1ª aula de cada um vem do Claude, com o endereço; as outras, do "Próximo" do site, pelo número,
    # porque o site troca a aula sem trocar o endereço (23/11/2026).
    um, dois, tres = (aula[2] for aula in AULAS_DO_SITE)
    assert cursos_robo.proxima_aula() is None
    assert not cursos_robo.guardar_a_primeira_aula(9, um) and not cursos_robo.guardar_a_primeira_aula(4, "x/y")
    assert cursos_robo.guardar_a_primeira_aula(5, tres) and cursos_robo.guardar_a_primeira_aula(4, um)
    assert cursos_robo.proxima_aula() == (4, 1)
    # Gravada a 1ª, a seguinte vem pelo Próximo dela; a que ficou pela metade volta inteira (P295 1).
    cursos_robo.anotar_a_aula_gravada(4, 1, _br("2026-11-24 00:30"))
    assert cursos_robo.proxima_aula() == (4, 2)
    cursos_robo.anotar_a_aula_seguinte(4, 2, "Aula dois")
    cursos_robo.anotar_a_aula_seguinte(4, 2, "Outro nome")
    cursos_robo.anotar_a_aula_seguinte(4, 9, "Fora da ordem")
    aulas = cursos_robo.mapa_das_aulas()["cursos"]["4"]["aulas"]
    assert aulas[1] == {"endereco": "", "nome": "Aula dois", "gravada_em": ""} and len(aulas) == 2
    assert cursos_robo.proxima_aula() == (4, 2)
    # A que não ficou guardada nesta noite fica para a seguinte, e a noite segue pelo Próximo dela.
    assert cursos_robo.proxima_aula(pular={(4, 2)}) == (4, 3)
    # Depois de uma aula gravada, a 1ª do curso não muda mais; antes, o Claude pode corrigir.
    assert not cursos_robo.guardar_a_primeira_aula(4, tres)
    assert cursos_robo.guardar_a_primeira_aula(5, dois) and cursos_robo.mapa_das_aulas()["cursos"]["5"]["aulas"] == [
        {"endereco": dois, "nome": "", "gravada_em": ""}]
    # Terminado o curso (a última aula, sem o Próximo), a que ficou para trás ainda volta; depois, vem o seguinte da
    # ordem.
    cursos_robo.anotar_o_fim_do_curso(4)
    assert cursos_robo.proxima_aula() == (4, 2) and cursos_robo.proxima_aula(pular={(4, 2)}) == (5, 1)
    cursos_robo.anotar_a_aula_gravada(4, 2, sem_video=True)
    assert cursos_robo.proxima_aula() == (5, 1)
    assert cursos_robo.resumo_do_mapa().startswith("curso 4: terminado (2 aulas, 1 sem vídeo); curso 5: 0 de 1")
    # A gravada que não serviu (preta ou muda) volta a ficar por gravar.
    cursos_robo.desmarcar_a_aula(4, 1)
    assert cursos_robo.proxima_aula() == (4, 1)


def test_o_claude_guarda_a_primeira_aula_de_cada_curso_pelo_explorar(bm):
    # O passo curso:primeira:N lê o endereço na barra do Chrome e o guarda no banco; o log diz só números.
    site = SiteDoCurso(AULAS_DO_SITE, aberta=1)
    assert cursos_robo.curso_no_explorar(site, "primeira:4") == (True, "1ª aula do curso 4 guardada")
    assert cursos_robo.proxima_aula() == (4, 1)
    assert cursos_robo.mapa_das_aulas()["cursos"]["4"]["aulas"][0]["endereco"] == AULAS_DO_SITE[1][2]
    assert cursos_robo.curso_no_explorar(site, "primeira:9") == (
        False, "o curso vai de 1 a 7 (a posição na lista de Turmas)")
    assert not cursos_robo.curso_no_explorar(site, "primeira:x")[0]
    assert not cursos_robo.curso_no_explorar(site, "segunda:4")[0]
    fora = SiteDoCurso([("Cursos", 0, "https://escola.exemplo.pro/m/courses")])
    assert cursos_robo.curso_no_explorar(fora, "primeira:5") == (False, "a tela não é a de uma aula do curso")
    ok, resumo = cursos_robo.curso_no_explorar(site, "")
    assert ok and resumo.startswith("curso 4: 0 de 1 aula(s) conhecida(s) gravada(s); curso 5: sem a 1ª aula")
    assert "escola" not in resumo and "Aula" not in resumo
    cursos_robo.anotar_a_aula_gravada(4, 1)
    assert cursos_robo.curso_no_explorar(site, "primeira:4") == (
        False, "o curso 4 já tem aula gravada: a 1ª dele não muda")


def test_o_explorar_abre_a_aula_como_a_noite_sem_mudar_o_mapa(bm):
    # O teste de dia, com o celular mudo (23/11/2026): curso:abrir:N abre a 1ª aula do curso N pela barra, como a
    # noite, e curso:proximo, a seguinte pelo Próximo (o endereço da barra não muda); o log diz só o tipo da aula, o
    # estado do vídeo e se o play está na tela.
    aulas = AULAS_DO_SITE[:2] + [AULA_DE_DOCUMENTO]
    cursos_robo.guardar_a_primeira_aula(4, aulas[0][2])
    site = SiteDoCurso(aulas, aberta=2)
    com_video = (True, "aula aberta, com vídeo: sem vídeo no Chrome; o play na tela")
    assert cursos_robo.curso_no_explorar(site, "abrir:4", **SEM_ESPERA) == com_video and site.aberta == 0
    assert cursos_robo.curso_no_explorar(site, "proximo", **SEM_ESPERA) == com_video and site.aberta == 1
    assert cursos_robo.endereco_da_aula(site.dump_hierarchy()) == aulas[0][2]
    assert cursos_robo.curso_no_explorar(site, "proximo", **SEM_ESPERA) == (
        True, "aula aberta, sem vídeo: sem vídeo no Chrome; sem o play na tela")
    # Na última aula, sem o Próximo; o curso sem a 1ª aula no mapa; e o mapa não muda.
    assert cursos_robo.curso_no_explorar(site, "proximo", **SEM_ESPERA) == (
        False, "a tela não é a de uma aula com o Próximo")
    assert cursos_robo.curso_no_explorar(site, "abrir:5", **SEM_ESPERA) == (
        False, "o curso 5 ainda não tem a 1ª aula no mapa")
    assert len(cursos_robo.mapa_das_aulas()["cursos"]["4"]["aulas"]) == 1
    # Com esses passos (e o midia:tocar), o explorar deixa o celular mudo também de dia.
    assert cursos_robo.toca_aula("curso", "abrir:4") and cursos_robo.toca_aula("curso", "proximo")
    assert cursos_robo.toca_aula("midia", "tocar") and not cursos_robo.toca_aula("midia", "pausar")
    assert not cursos_robo.toca_aula("curso", "primeira:4") and not cursos_robo.toca_aula("curso", "")


class AjudanteNaHora:
    """O ajudante de mentira: lê cada aula na hora em que ela chega (a de número problema_na sai preta)."""

    def __init__(self, problema_na=None):
        self.problema, self.guardadas, self.lidas, self.problema_na = "", 0, [], problema_na

    def mandar_as_que_ficaram(self):
        return 0

    def mandar(self, arquivo, posicao, numero, fim):
        self.lidas.append((posicao, numero, fim))
        if numero == self.problema_na:
            self.problema = "a imagem saiu preta"
            cursos_robo.desmarcar_a_aula(posicao, numero)
        else:
            self.guardadas += 1

    def acabar(self):
        pass


@pytest.fixture
def noite_do_curso(bm, monkeypatch, tmp_path):
    """A madrugada do curso com o celular livre, o disco folgado e a gravação de mentira (gravar(numero) diz o fim)."""
    import contextlib
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_GRAVACOES", str(tmp_path / "brutas"))
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_AULAS", str(tmp_path / "aulas"))
    monkeypatch.setattr(cursos_robo, "disco_usado", lambda caminho=None: 20)
    monkeypatch.setattr(cursos_robo, "_madrugada_agora", lambda: True)
    gravadas, casos = [], []
    monkeypatch.setattr(cursos_robo, "guardar_o_caso",
                        lambda d, motivo, resultado="não abriu": casos.append((motivo, resultado)), raising=False)

    def rodar(site, ajudante, fim_da=lambda nome: (True, "o vídeo parou")):
        def gravar(d, alvo, destino, ir_para_a_aula, tocar, pausa=None, **_):
            # Na ordem da gravação de verdade: o gravador (que deixa o alto-falante mudo), o volume, a página e o play.
            d.gravando = True
            try:
                cursos_robo.subir_o_volume(d)
                tipo, porque = ir_para_a_aula(d)
                if not tipo:
                    return False, False, f"a aula não abriu ({porque})"
                if tipo == cursos_robo.SEM_VIDEO:
                    return True, False, tipo
                assert tocar(d)
                gravadas.append(d.aulas[d.aberta][0])
                with open(destino, "wb") as arquivo:
                    arquivo.write(b"aula")
                return (True,) + tuple(fim_da(gravadas[-1]))
            finally:
                cursos_robo.pausar_o_que_toca(d, pausa)
                cursos_robo.devolver_o_volume(d, pausa)
                d.gravando = False

        monkeypatch.setattr(cursos_robo, "gravar_a_aula", gravar, raising=False)

        @contextlib.contextmanager
        def trava():
            yield True
        return cursos_robo.noite(conectar=lambda: site, pausa=lambda s: None, ajudante=ajudante, trava=trava,
                                 conectado=lambda: True)
    rodar.gravadas, rodar.casos = gravadas, casos
    return rodar


def test_a_noite_grava_o_curso_inteiro_pelo_proximo_do_site(noite_do_curso):
    # P289 1 a P293 1: da 1ª aula guardada pelo Claude, a noite segue o Próximo do site até a última, e o curso termina.
    # O Próximo troca a aula sem trocar o endereço da barra (o teste de 23/11/2026, às 10:49): a noite segue pelo nome
    # no Próximo, e cada aula abre pelo Próximo da de antes, com o gravador já gravando.
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    site, ajudante = SiteDoCurso(AULAS_DO_SITE, aberta=2), AjudanteNaHora()
    resumo = noite_do_curso(site, ajudante)
    assert resumo == ("3 aula(s) gravada(s), 3 guardada(s), 0 pela metade, 0 sem vídeo guardada(s); parou: nenhuma "
                      "aula por gravar")
    assert noite_do_curso.gravadas == ["Aula um", "Aula dois", "Aula três"]
    assert ajudante.lidas == [(4, 1, "o vídeo parou"), (4, 2, "o vídeo parou"), (4, 3, "o vídeo parou")]
    assert site.endereco_na_barra == AULAS_DO_SITE[0][2]
    curso = cursos_robo.mapa_das_aulas()["cursos"]["4"]
    assert curso["fim"] and [aula["nome"] for aula in curso["aulas"]] == ["", "Aula dois", "Aula três"]
    assert all(aula["gravada_em"] for aula in curso["aulas"]) and not cursos_robo.gravando()
    import registro_processos
    assert registro_processos.sequencia("curso", "noite do curso", "2000-01-01 00:00:00")


def test_a_noite_que_comeca_com_a_shopee_na_frente_grava_a_aula_da_vez(noite_do_curso):
    # A rodada do robô deixa a Shopee no Eu, e a noite começa com ela na frente: o Chrome vem antes da 1ª aula.
    um = AULAS_DO_SITE[0][2]
    cursos_robo.guardar_a_primeira_aula(4, um)
    site = SiteDoCurso(AULAS_DO_SITE, aberta=2, na_frente="com.shopee.br")
    resumo = noite_do_curso(site, AjudanteNaHora())
    assert resumo.startswith("3 aula(s) gravada(s)") and noite_do_curso.gravadas[0] == "Aula um"
    assert site.abertos == [CHROME]


def test_a_aula_que_nao_abre_fica_no_registro_com_o_porque(noite_do_curso):
    # O porquê de a aula não abrir vai ao registro de cada aula, para o relatório da manhã; 2 seguidas param a noite.
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    site = SiteDoCurso(AULAS_DO_SITE, na_frente="com.android.systemui", abre_o_chrome=False)
    resumo = noite_do_curso(site, AjudanteNaHora())
    assert resumo == ("0 aula(s) gravada(s), 0 guardada(s), 0 pela metade, 0 sem vídeo guardada(s); parou: a aula não "
                      "abriu (o Chrome não veio para a frente)")
    import registro_processos
    linhas = registro_processos.sequencia("curso", "aula do curso", "2000-01-01 00:00:00")
    assert [(linha[2], linha[3]) for linha in linhas] == [
        ("não abriu", "curso 4, aula 1: a aula não abriu (o Chrome não veio para a frente)")] * 2
    # A tela da 1ª que não abriu fica guardada para o Claude achar o porquê (só uma por noite).
    assert noite_do_curso.casos == [("a aula não abriu (o Chrome não veio para a frente)", "não abriu")]


def test_a_aula_so_abre_muda_ou_com_o_gravador_gravando(noite_do_curso):
    # O vídeo pode começar a tocar sozinho quando a página da aula abre, e o celular fica no quarto do Rafael (pedido
    # dele, 22/11): a aula aberta antes da gravação (pela barra ou pelo Próximo) abre com o volume de mídia em 0; a da
    # gravação abre com o volume da aula só com o gravador gravando (o som vai só ao servidor). O de antes fica
    # guardado, e a próxima rodada do robô o devolve.
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    site = SiteDoCurso(AULAS_DO_SITE, aberta=2, volume=6, autoplay=True)
    resumo = noite_do_curso(site, AjudanteNaHora())
    assert resumo.startswith("3 aula(s) gravada(s)")
    assert all(volume == 0 or gravando for volume, gravando in site.aberturas)
    assert (0, False) in site.aberturas and (8, True) in site.aberturas
    assert cursos_robo.estado_da_noite()["volume_antes"] == 6


def test_a_noite_entra_no_site_muda_antes_de_ligar_o_gravador(noite_do_curso, monkeypatch):
    # Com a sessão do site vencida, a aula abre antes, muda e sem o gravador, e o login fica fora da gravação (a tela do
    # login nunca vai às folhas de quadros); depois, a aula abre de novo, do começo, gravando.
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    site = SiteDoCurso(AULAS_DO_SITE, volume=6, sessao_vencida=True)
    monkeypatch.setattr(cursos_robo, "_entrar", _login_de_mentira(), raising=False)
    resumo = noite_do_curso(site, AjudanteNaHora())
    assert resumo.startswith("3 aula(s) gravada(s)")
    assert site.logins == [(0, False)]


def test_a_aula_que_toca_sozinha_e_gravada_sem_tocar_no_play(noite_do_curso):
    # A aula que começa a tocar com a página é gravada do começo, com o gravador ligado antes de ela abrir, e o play
    # não é tocado (seria a pausa).
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    site = SiteDoCurso(AULAS_DO_SITE, autoplay=True)
    resumo = noite_do_curso(site, AjudanteNaHora())
    assert resumo.startswith("3 aula(s) gravada(s)") and noite_do_curso.gravadas == [aula[0] for aula in AULAS_DO_SITE]
    assert (539, 793) not in site.toques


def test_a_aula_sem_video_e_guardada_com_a_pagina_e_o_documento(noite_do_curso):
    # O vídeo do Rafael das 08:22 e as mensagens das 08:44 e das 09:12 de 23/11/2026: há aulas que são um documento ou
    # um texto, e o Claude, no papel de aluno, vê tudo. A noite guarda a aula sem vídeo com o texto, as telas e o
    # documento pelo Baixar do próprio site, e a seguinte vem pelo Próximo dela.
    aulas = [AULAS_DO_SITE[0], AULA_DE_DOCUMENTO, AULAS_DO_SITE[1]]
    cursos_robo.guardar_a_primeira_aula(4, aulas[0][2])
    site = SiteDoCurso(aulas)
    resumo = noite_do_curso(site, AjudanteNaHora())
    assert resumo == ("2 aula(s) gravada(s), 2 guardada(s), 0 pela metade, 1 sem vídeo guardada(s); parou: nenhuma "
                      "aula por gravar")
    assert noite_do_curso.gravadas == ["Aula um", "Aula dois"]
    documento = cursos_robo.mapa_das_aulas()["cursos"]["4"]["aulas"][1]
    assert documento["nome"] == "Dia 01" and documento["sem_video"] and documento["gravada_em"]
    (pasta,) = os.listdir(cursos_robo.PASTA_DAS_AULAS)
    assert pasta.endswith("-c04-a002")
    assert sorted(os.listdir(os.path.join(cursos_robo.PASTA_DAS_AULAS, pasta))) == [
        "aula.json", "documento_1.pdf", "tela_01.jpg", "texto.txt"]
    import registro_processos
    linhas = registro_processos.sequencia("curso", "aula do curso", "2000-01-01 00:00:00")
    assert [(linha[2], linha[3]) for linha in linhas] == [
        ("guardada sem vídeo", "curso 4, aula 2: 1 tela(s), 5 linha(s), 1 link(s), documento de 2 KB")]
    # O documento saiu do celular, e nenhum link foi tocado (entrar num grupo é com o Rafael).
    assert site.baixados == [] and (464, 1942) not in site.toques
    assert cursos_robo.resumo_do_mapa().startswith("curso 4: terminado (3 aulas, 1 sem vídeo)")


def test_a_aula_sem_video_que_nao_fica_guardada_volta_e_a_noite_segue(noite_do_curso):
    # Nenhuma aula é pulada (23/11/2026): o documento que não vem deixa a aula para a noite seguinte, que começa por
    # ela; nesta, a noite segue pelo Próximo dela.
    aulas = [AULAS_DO_SITE[0], AULA_DE_DOCUMENTO, AULAS_DO_SITE[1]]
    cursos_robo.guardar_a_primeira_aula(4, aulas[0][2])
    resumo = noite_do_curso(SiteDoCurso(aulas, baixa=False), AjudanteNaHora())
    assert resumo.startswith("2 aula(s) gravada(s), 2 guardada(s), 0 pela metade, 0 sem vídeo guardada(s)")
    assert os.listdir(cursos_robo.PASTA_DAS_AULAS) == []
    import registro_processos
    linhas = registro_processos.sequencia("curso", "aula do curso", "2000-01-01 00:00:00")
    assert [(linha[2], linha[3]) for linha in linhas] == [
        ("não guardada", "curso 4, aula 2: o documento não apareceu no celular")]
    assert noite_do_curso.casos == [("o documento não apareceu no celular", "não guardada")]
    assert cursos_robo.proxima_aula() == (4, 2)


def test_a_aula_conhecida_sem_o_proximo_antes_dela_nao_prende_a_noite(noite_do_curso):
    # O mapa com uma aula que o site não mostra mais depois da de antes: a noite não marca o curso como terminado (a
    # aula ainda não foi guardada) e para depois de 2 tentativas, sem ficar em volta.
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    for numero, nome in ((2, "Aula dois"), (3, "Aula três")):
        cursos_robo.anotar_a_aula_seguinte(4, numero, nome)
    cursos_robo.anotar_a_aula_gravada(4, 1)
    cursos_robo.anotar_a_aula_gravada(4, 2)
    resumo = noite_do_curso(SiteDoCurso(AULAS_DO_SITE[:2]), AjudanteNaHora())
    assert resumo.endswith("parou: a aula não abriu (sem o Próximo na aula de antes)")
    assert not cursos_robo.mapa_das_aulas()["cursos"]["4"]["fim"]


def test_sem_a_leitura_do_volume_a_aula_nao_abre(noite_do_curso):
    # Sem a certeza de o celular estar mudo, a aula não abre: nada é tocado, e a noite para.
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    surdo = SiteDoCurso(AULAS_DO_SITE, responde=False)
    resumo = noite_do_curso(surdo, AjudanteNaHora())
    assert resumo.endswith("parou: o celular não ficou mudo antes de abrir a aula") and surdo.toques == []


def test_o_robo_que_pede_o_celular_deixa_a_aula_para_a_noite_seguinte(noite_do_curso):
    # O robô da Shopee Vídeo tem a preferência (22/11): a aula fica pela metade, o vídeo dela sai, e ela volta depois,
    # inteira, do início (P295 1).
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    ajudante = AjudanteNaHora()
    resumo = noite_do_curso(SiteDoCurso(AULAS_DO_SITE), ajudante,
                            fim_da=lambda nome: (True, "o vídeo parou") if nome == "Aula um"
                            else (False, "o robô pediu o celular"))
    assert resumo == ("1 aula(s) gravada(s), 1 guardada(s), 1 pela metade, 0 sem vídeo guardada(s); parou: o robô "
                      "pediu o celular")
    assert cursos_robo.proxima_aula() == (4, 2)
    assert cursos_robo.mapa_das_aulas()["cursos"]["4"]["aulas"][1]["nome"] == "Aula dois"
    assert os.listdir(cursos_robo.PASTA_DAS_GRAVACOES) == []
    # O registro diz qual aula ficou pela metade e por quê, só com números (o relatório da manhã, pedido de 23/11).
    import registro_processos
    linhas = registro_processos.sequencia("curso", "aula do curso", "2000-01-01 00:00:00")
    assert [(linha[2], linha[3]) for linha in linhas] == [("pela metade", "curso 4, aula 2: o robô pediu o celular")]


def test_a_noite_guarda_tambem_a_pagina_de_cada_videoaula(noite_do_curso):
    # Pedidos do Rafael de 23/11 (08:44 e 09:12): tudo o que está nas aulas vai ao Claude, também o texto e os links
    # embaixo de cada videoaula. Gravada a aula inteira, a página dela é guardada à parte, com o celular mudo e sem
    # tocar em nada, e a noite segue para a seguinte pelo Próximo.
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    site, ajudante = SiteDoCurso(AULAS_DO_SITE, aberta=2, texto_na_videoaula=True), AjudanteNaHora()
    resumo = noite_do_curso(site, ajudante)
    assert resumo == ("3 aula(s) gravada(s), 3 guardada(s), 0 pela metade, 0 sem vídeo guardada(s); parou: nenhuma "
                      "aula por gravar")
    assert noite_do_curso.gravadas == ["Aula um", "Aula dois", "Aula três"]
    paginas = sorted(os.listdir(cursos_robo.PASTA_DAS_AULAS))
    assert [nome[-8:] for nome in paginas] == ["c04-a001", "c04-a002", "c04-a003"]
    for nome in paginas:
        pasta = os.path.join(cursos_robo.PASTA_DAS_AULAS, nome)
        with open(os.path.join(pasta, "aula.json"), encoding="utf-8") as arquivo:
            info = json.load(arquivo)
        assert (info["tipo"], info["linhas"], info["links"], info["documento"]) == (
            cursos_robo.PAGINA_DA_VIDEOAULA, 2, 1, None)
        with open(os.path.join(pasta, "texto.txt"), encoding="utf-8") as arquivo:
            assert "Tarefa da aula" in arquivo.read()
    assert site.volumes_das_telas == [0, 0, 0]
    # Só a barra de endereço (a 1ª aula), o play e o Próximo: nada no texto ou no link da página.
    assert all(y <= 267 or y >= 2175 or (x, y) == (539, 793) for x, y in site.toques)
    import registro_processos
    linhas = registro_processos.sequencia("curso", "aula do curso", "2000-01-01 00:00:00")
    assert [(linha[2], linha[3]) for linha in linhas] == [
        ("página guardada", f"curso 4, aula {numero}: 1 tela(s), 2 linha(s), 1 link(s), sem documento")
        for numero in (1, 2, 3)]


def test_o_robo_que_pede_o_celular_na_pagina_da_videoaula_para_a_noite_com_a_aula_gravada(noite_do_curso, monkeypatch):
    # O robô tem a preferência (22/11): pedido o celular enquanto a página é lida, a noite para, e a aula gravada
    # inteira vale (a página pela metade sai).
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    ajudante, gravou = AjudanteNaHora(), []
    monkeypatch.setattr(cursos_robo, "pediram_o_celular", lambda inicio: bool(gravou))

    def fim_da(nome):
        gravou.append(nome)
        return True, "o vídeo parou"
    resumo = noite_do_curso(SiteDoCurso(AULAS_DO_SITE, texto_na_videoaula=True), ajudante, fim_da=fim_da)
    assert resumo == ("1 aula(s) gravada(s), 1 guardada(s), 0 pela metade, 0 sem vídeo guardada(s); parou: o robô "
                      "pediu o celular")
    assert ajudante.lidas == [(4, 1, "o vídeo parou")] and cursos_robo.proxima_aula() == (4, 2)
    assert os.listdir(cursos_robo.PASTA_DAS_AULAS) == []


def test_a_pagina_de_outra_aula_nao_e_guardada_como_a_da_videoaula(bm, monkeypatch, tmp_path):
    # A página que voltou para a aula de antes (o Próximo com o nome da própria aula gravada) não é guardada como a
    # dela: o registro diz o porquê, e a aula gravada vale do mesmo jeito.
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_AULAS", str(tmp_path / "aulas"))
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    cursos_robo.anotar_a_aula_seguinte(4, 2, "Aula dois")
    site = SiteDoCurso(AULAS_DO_SITE, aberta=0, no_alto=True, texto_na_videoaula=True)
    assert cursos_robo._guardar_a_pagina_da_videoaula(site, 4, 2, lambda s: None, lambda: "") == ""
    assert not os.path.exists(tmp_path / "aulas") and site.toques == []
    import registro_processos
    linhas = registro_processos.sequencia("curso", "aula do curso", "2000-01-01 00:00:00")
    assert [(linha[2], linha[3]) for linha in linhas] == [
        ("página não guardada", "curso 4, aula 2: a página não é a da aula gravada")]
    # Na aula certa, a mesma página é guardada; a videoaula sem nada embaixo do vídeo não vai ao registro.
    site._abrir(1)
    assert cursos_robo._guardar_a_pagina_da_videoaula(site, 4, 2, lambda s: None, lambda: "") == ""
    (pasta,) = os.listdir(tmp_path / "aulas")
    assert pasta.endswith("-c04-a002")
    site.texto_na_videoaula = False
    assert cursos_robo._guardar_a_pagina_da_videoaula(site, 4, 2, lambda s: None, lambda: "") == ""
    assert len(registro_processos.sequencia("curso", "aula do curso", "2000-01-01 00:00:00")) == 2


def test_a_gravacao_preta_para_a_noite_e_a_aula_volta_a_ficar_por_gravar(noite_do_curso):
    # P288 3: preta ou muda, o player não deixa gravar, e a gravação para.
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    ajudante = AjudanteNaHora(problema_na=1)
    resumo = noite_do_curso(SiteDoCurso(AULAS_DO_SITE), ajudante)
    assert resumo.endswith("parou: a imagem saiu preta") and noite_do_curso.gravadas == ["Aula um"]
    assert cursos_robo.proxima_aula() == (4, 1)


def test_o_proximo_troca_a_aula_sem_trocar_o_endereco_da_barra():
    # 23/11/2026, 10:49: o Próximo do site abriu a aula seguinte (um documento), e o endereço da barra continuou o da
    # aula de antes; o explorar esperava o endereço novo ("o Próximo não abriu a aula seguinte"). A troca é conferida
    # pelo nome no Próximo, e o tipo, pela página.
    aulas = AULAS_DO_SITE[:2] + [AULA_DE_DOCUMENTO]
    site = SiteDoCurso(aulas)
    assert cursos_robo.nome_no_proximo(site.dump_hierarchy()) == "Aula dois"
    assert cursos_robo.passar_para_a_seguinte(site, **SEM_ESPERA) == ("com vídeo", "", "Aula dois")
    assert cursos_robo.passar_para_a_seguinte(site, **SEM_ESPERA) == ("sem vídeo", "", "Dia 01")
    assert site.aberta == 2 and cursos_robo.endereco_da_aula(site.dump_hierarchy()) == aulas[0][2]
    # Na última aula, sem o Próximo: o fim do curso, sem toque.
    toques = list(site.toques)
    assert cursos_robo.passar_para_a_seguinte(site, **SEM_ESPERA) == (None, "o curso terminou", "")
    assert site.toques == toques


def test_chegar_na_aula_pelo_comeco_do_curso_mudo_e_sem_o_gravador(bm):
    # A aula N do curso: a 1ª pelo endereço guardado e as outras pelo Próximo, com o celular mudo e sem o gravador; os
    # nomes vão ao mapa.
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    site = SiteDoCurso(AULAS_DO_SITE, aberta=2, volume=0)
    assert cursos_robo.chegar_na_aula(site, 4, 3, **SEM_ESPERA) == ("com vídeo", "")
    assert site.aberta == 2 and site.aberturas == [(0, False)] * 3
    assert [aula["nome"] for aula in cursos_robo.mapa_das_aulas()["cursos"]["4"]["aulas"]] == [
        "", "Aula dois", "Aula três"]
    assert cursos_robo.chegar_na_aula(site, 5, 1, **SEM_ESPERA) == (None, "o curso 5 ainda não tem a 1ª aula no mapa")


def test_o_caminho_ate_a_aula_renova_o_sinal_e_solta_o_celular_quando_o_robo_pede(bm):
    # O robô da Shopee Vídeo tem a preferência (22/11): o caminho até uma aula do fim do curso leva minutos, e a cada
    # aula a noite renova o sinal ao robô e para na hora em que ele pede o celular.
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    site, vistas = SiteDoCurso(AULAS_DO_SITE, aberta=2), []

    def vigiar():
        vistas.append(site.aberta)
        return "o robô pediu o celular" if len(vistas) == 2 else ""
    assert cursos_robo.chegar_na_aula(site, 4, 3, vigiar=vigiar, **SEM_ESPERA) == (None, "o robô pediu o celular")
    assert vistas == [0, 1] and site.aberta == 1


def test_o_proximo_espera_o_aviso_do_chrome_sair_e_nunca_toca_com_ele_na_tela():
    # O aviso do download do Chrome (com o Abrir) fica embaixo, onde está o Próximo: o Próximo só é tocado depois de ele
    # sair; com ele na tela o tempo todo, nada é tocado.
    site = SiteDoCurso(AULAS_DO_SITE)
    site.aviso = 3
    assert cursos_robo.passar_para_a_seguinte(site, **SEM_ESPERA)[:2] == ("com vídeo", "") and site.aberta == 1
    preso = SiteDoCurso(AULAS_DO_SITE)
    preso.aviso = 999
    assert cursos_robo.passar_para_a_seguinte(preso, **SEM_ESPERA) == (
        None, "um aviso do Chrome ficou em cima do Próximo", "Aula dois")
    assert preso.toques == [] and preso.aberta == 0


def test_o_texto_longo_da_aula_rola_ate_as_abas_sem_repetir(bm, monkeypatch, tmp_path):
    # O texto da aula sem vídeo em duas telas: a página rola até as abas, e o pedaço que as duas mostram entra uma vez.
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_AULAS", str(tmp_path / "aulas"))
    site = SiteDoCurso([("Texto", 0, "https://escola.exemplo.pro/m/lessons/txt555", "texto longo")], no_alto=True)
    pasta, info = cursos_robo.guardar_a_aula_sem_video(site, 4, 7, **SEM_ESPERA)
    assert info["telas"] == 2 and info["documento"] is None and info["links"] == 0
    with open(os.path.join(pasta, "texto.txt"), encoding="utf-8") as arquivo:
        assert arquivo.read() == "Parte um da aula\nParte dois da aula\nParte três da aula\n"
    assert sorted(os.listdir(pasta)) == ["aula.json", "tela_01.jpg", "tela_02.jpg", "texto.txt"]
    assert cursos_robo.descrever_a_aula_guardada(info) == "2 tela(s), 3 linha(s), 0 link(s), sem documento"


def test_a_aula_sem_video_para_no_meio_quando_o_robo_pede_o_celular(bm, monkeypatch, tmp_path):
    # O robô da Shopee Vídeo tem a preferência (22/11): a aula pela metade sai da pasta e volta depois, inteira.
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_AULAS", str(tmp_path / "aulas"))
    site = SiteDoCurso([AULA_DE_DOCUMENTO], no_alto=True)
    assert cursos_robo.guardar_a_aula_sem_video(site, 5, 2, vigiar=lambda: "o robô pediu o celular",
                                                **SEM_ESPERA) == (None, {"problema": "o robô pediu o celular"})
    assert os.listdir(tmp_path / "aulas") == [] and site.toques == []


@pytest.mark.parametrize("volta", [False, True])
def test_a_aula_de_slides_guarda_cada_imagem_do_carrossel(bm, monkeypatch, tmp_path, volta):
    # O teste de dia de 23/11 (12:53): a 3ª aula do curso 5 é um carrossel de imagens, com o Anterior e o Próximo
    # dele. Cada slide vai recortado da tela, no tamanho em que aparece, pelo Próximo do carrossel (nunca o da barra da
    # aula seguinte), até o último: o que não muda com o toque ou o que volta ao 1º.
    from PIL import Image
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_AULAS", str(tmp_path / "aulas"))
    site = SiteDoCurso([AULA_DE_SLIDES, AULAS_DO_SITE[0]], no_alto=True, carrossel_volta=volta)
    pasta, info = cursos_robo.guardar_a_aula_sem_video(site, 5, 3, **SEM_ESPERA)
    assert info["slides"] == 4 and info["linhas"] == 1
    assert sorted(nome for nome in os.listdir(pasta) if nome.startswith("slide_")) == [
        f"slide_0{numero}.jpg" for numero in (1, 2, 3, 4)]
    assert site.toques == [(889, 794)] * 4 and site.aberta == 0
    imagens = []
    for numero in (1, 2, 3, 4):
        with Image.open(os.path.join(pasta, f"slide_0{numero}.jpg")) as slide:
            assert slide.size == (796, 451)
            imagens.append(slide.copy())
    assert not any(cursos_robo.mesma_imagem(imagens[n], imagens[n + 1]) for n in range(3))
    assert cursos_robo.descrever_a_aula_guardada(info) == "1 tela(s), 4 slide(s), 1 linha(s), 0 link(s), sem documento"


def test_um_slide_com_uma_palavra_a_mais_nao_e_o_mesmo():
    # Dois prints da mesma imagem são o mesmo slide; o slide que só ganha uma palavra é outro (não é o fim do
    # carrossel).
    from PIL import Image, ImageDraw
    slide = Image.new("RGB", (796, 451), (250, 240, 200))
    ImageDraw.Draw(slide).rectangle((60, 60, 700, 110), fill=(120, 60, 20))
    print_de_novo = slide.copy()
    print_de_novo.putpixel((300, 300), (240, 230, 190))
    com_palavra = slide.copy()
    ImageDraw.Draw(com_palavra).rectangle((60, 200, 200, 240), fill=(120, 60, 20))
    assert cursos_robo.mesma_imagem(slide, print_de_novo)
    assert not cursos_robo.mesma_imagem(slide, com_palavra)


def test_os_slides_param_quando_o_robo_pede_o_celular(bm, monkeypatch, tmp_path):
    # O robô tem a preferência (22/11): no meio dos slides, a aula para e a pasta pela metade sai.
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_AULAS", str(tmp_path / "aulas"))
    site, chamadas = SiteDoCurso([AULA_DE_SLIDES], no_alto=True), []

    def vigiar():
        chamadas.append(1)
        return "o robô pediu o celular" if len(chamadas) > 3 else ""
    assert cursos_robo.guardar_a_aula_sem_video(site, 5, 3, vigiar=vigiar, **SEM_ESPERA) == (
        None, {"problema": "o robô pediu o celular"})
    assert os.listdir(tmp_path / "aulas") == [] and site.toques == [(889, 794)] * 2


def test_o_proximo_do_carrossel_nao_e_o_da_aula_seguinte():
    # O Próximo do carrossel é só "Próximo"; o da barra tem os dois pontos e o nome da aula seguinte.
    site = SiteDoCurso([AULA_DE_SLIDES, AULAS_DO_SITE[0]], no_alto=True)
    tela = site.dump_hierarchy()
    assert cursos_robo.carrossel_na_tela(tela) == ((141, 540, 937, 991), (889, 794))
    assert cursos_robo.nome_no_proximo(tela) == "Aula um" and cursos_robo.botao_do_proximo(tela) == (540, 2284)
    assert cursos_robo.carrossel_na_tela(SiteDoCurso([AULA_DE_DOCUMENTO], no_alto=True).dump_hierarchy()) == (
        None, None)


def test_os_toques_da_aula_nunca_caem_no_proximo_na_bolha_do_chat_ou_na_barra():
    tela = ('<hierarchy><node class="android.widget.EditText" resource-id="com.android.chrome:id/url_bar" '
            'text="escola.exemplo.pro/m/lessons/x" bounds="[211,120][691,267]" />'
            '<node class="android.widget.Button" clickable="true" text="Próximo: Outra Próxima aula:" '
            'bounds="[0,2175][1080,2394]" /></hierarchy>')
    assert cursos_robo._livre_para_tocar(tela, (115, 2011))
    assert not cursos_robo._livre_para_tocar(tela, (115, 2200))       # o Próximo
    assert not cursos_robo._livre_para_tocar(tela, (950, 2080))       # a bolha do chat
    assert not cursos_robo._livre_para_tocar(tela, (632, 200))        # a barra do Chrome
    assert cursos_robo.nome_no_proximo(tela) == "Outra"


def test_o_explorar_guarda_a_aula_sem_video_aberta(bm, monkeypatch, tmp_path):
    # O teste de dia da aula sem vídeo (curso:guardar): guardada como a noite guarda, como a aula 0 do curso 0; o log
    # diz só números.
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_AULAS", str(tmp_path / "aulas"))
    site = SiteDoCurso([AULA_DE_DOCUMENTO], no_alto=True)
    assert cursos_robo.curso_no_explorar(site, "guardar", **SEM_ESPERA) == (
        True, "aula sem vídeo guardada: 1 tela(s), 5 linha(s), 1 link(s), documento de 2 KB")
    (pasta,) = os.listdir(tmp_path / "aulas")
    assert pasta.endswith("-c00-a000") and site.baixados == []
    assert not cursos_robo.toca_aula("curso", "guardar")


def test_o_explorar_guarda_a_pagina_da_videoaula_sem_tocar_no_play(bm, monkeypatch, tmp_path):
    # O teste de dia da página da videoaula (curso:guardar): o texto e o link embaixo do vídeo, sem tocar no player.
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_AULAS", str(tmp_path / "aulas"))
    vazia = SiteDoCurso(AULAS_DO_SITE, no_alto=True)
    assert cursos_robo.curso_no_explorar(vazia, "guardar", **SEM_ESPERA) == (
        False, "a página da videoaula não foi guardada (a página da aula não mostrou texto nem documento)")
    com_texto = SiteDoCurso(AULAS_DO_SITE, no_alto=True, texto_na_videoaula=True)
    assert cursos_robo.curso_no_explorar(com_texto, "guardar", **SEM_ESPERA) == (
        True, "página da videoaula guardada: 1 tela(s), 2 linha(s), 1 link(s), sem documento")
    (pasta,) = os.listdir(tmp_path / "aulas")
    assert pasta.endswith("-c00-a000") and com_texto.toques == [] and not com_texto._tocando()
    with open(os.path.join(tmp_path / "aulas", pasta, "aula.json"), encoding="utf-8") as arquivo:
        assert json.load(arquivo)["tipo"] == cursos_robo.PAGINA_DA_VIDEOAULA


@pytest.fixture
def teste_de_dia(bm, monkeypatch, tmp_path):
    """
    O passo curso:gravar:N de dia, com a gravação de mentira na ordem da de verdade: fim(site) diz como a aula acabou
    (com o arquivo gravado). Anota o máximo e a madrugada de cada gravação e o que foi lido de cada uma.
    """
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_GRAVACOES", str(tmp_path / "brutas"))
    monkeypatch.setattr(cursos_robo, "_madrugada_agora", lambda: False)
    gravacoes, lidas = [], []

    def rodar(site, passo="gravar:5", fim=lambda site: (True, "o vídeo parou")):
        def gravar(d, alvo, destino, ir_para_a_aula, tocar, pausa=None, madrugada=None, maximo=None, **_):
            gravacoes.append((maximo, madrugada()))
            d.gravando = True
            try:
                cursos_robo.subir_o_volume(d)
                tipo, porque = ir_para_a_aula(d)
                if not tipo:
                    return False, False, f"a aula não abriu ({porque})"
                assert tocar(d)
                with open(destino, "wb") as arquivo:
                    arquivo.write(b"aula")
                return (True,) + tuple(fim(d))
            finally:
                cursos_robo.pausar_o_que_toca(d, pausa)
                cursos_robo.devolver_o_volume(d, pausa)
                d.gravando = False

        def guardar(arquivo, curso, aula, como_acabou, agora=None):
            lidas.append((os.path.exists(arquivo), curso, aula, como_acabou))
            os.remove(arquivo)
            return "pasta", {"segundos": 95, "som": -21.4, "palavras": 230, "folhas": 2, "problema": ""}

        monkeypatch.setattr(cursos_robo, "gravar_a_aula", gravar, raising=False)
        monkeypatch.setattr(cursos_robo, "guardar_a_aula", guardar, raising=False)
        # O explorar deixa o celular mudo antes dos passos que tocam uma aula, e o volume volta no fim dele.
        assert cursos_robo.toca_aula("curso", passo) and cursos_robo.calar_o_celular(site)[0] == 0
        return cursos_robo.curso_no_explorar(site, passo, **SEM_ESPERA)
    rodar.gravacoes, rodar.lidas, rodar.brutas = gravacoes, lidas, tmp_path / "brutas"
    return rodar


def test_o_teste_de_dia_grava_a_primeira_aula_como_a_noite(teste_de_dia):
    # O teste de dia da gravação da noite (23/11/2026): a 1ª aula do curso abre antes, muda e sem o gravador, e de novo
    # pela barra com o gravador gravando; o play só com o vídeo parado; a gravação tem no máximo 10 min e é lida como a
    # aula 0 do curso 0. Depois, o celular fica mudo até o explorar devolver o volume; o log diz só números.
    cursos_robo.guardar_a_primeira_aula(5, AULAS_DO_SITE[0][2])
    site = SiteDoCurso(AULAS_DO_SITE, aberta=2, volume=6)
    assert teste_de_dia(site) == (
        True, "aula gravada inteira (o vídeo parou): 95 s, som -21.4 LUFS, 230 palavra(s), 2 folha(s) de quadros, sem "
              "problema; para ler: cursos_robo.yml exportar")
    assert teste_de_dia.gravacoes == [(cursos_robo.GRAVACAO_DO_TESTE, True)]
    assert teste_de_dia.lidas == [(True, 0, 0, "o vídeo parou")] and not os.listdir(teste_de_dia.brutas)
    assert site.aberturas == [(0, False), (8, True)] and site.aberta == 0 and site.toques[-1] == (539, 793)
    assert site.volume == 0 and cursos_robo.estado_da_noite()["volume_antes"] == 6
    # O mapa não muda: a aula do teste não conta como gravada.
    assert cursos_robo.proxima_aula() == (5, 1)


def test_o_teste_de_dia_recusa_a_madrugada_o_curso_sem_mapa_e_a_aula_sem_video(teste_de_dia, monkeypatch):
    site = SiteDoCurso(AULAS_DO_SITE, aberta=2)
    assert teste_de_dia(site) == (False, "o curso 5 ainda não tem a 1ª aula no mapa")
    cursos_robo.guardar_a_primeira_aula(5, AULA_DE_DOCUMENTO[2])
    documento = SiteDoCurso([AULA_DE_DOCUMENTO, AULAS_DO_SITE[0]], aberta=1)
    assert teste_de_dia(documento) == (False, "a 1ª aula do curso 5 não tem vídeo")
    monkeypatch.setattr(cursos_robo, "_madrugada_agora", lambda: True)
    assert teste_de_dia(site) == (False, "de madrugada, quem grava as aulas é a noite")
    assert site.toques == [] and teste_de_dia.gravacoes == [] and teste_de_dia.lidas == []
    assert not cursos_robo.curso_no_explorar(site, "gravar:9", **SEM_ESPERA)[0]


def test_o_robo_que_pede_o_celular_no_teste_de_dia_tem_o_celular_na_hora(teste_de_dia):
    # O robô da Shopee Vídeo tem a preferência também no teste: a gravação para e sai sem ser lida (a leitura da fala
    # seguraria o celular), e o celular fica mudo.
    cursos_robo.guardar_a_primeira_aula(5, AULAS_DO_SITE[0][2])
    site = SiteDoCurso(AULAS_DO_SITE, aberta=2, volume=6)
    assert teste_de_dia(site, fim=lambda d: (False, "o robô pediu o celular")) == (
        False, "a gravação parou (o robô pediu o celular) e saiu sem ser lida")
    assert teste_de_dia.lidas == [] and not os.listdir(teste_de_dia.brutas) and site.volume == 0
    # A aula que não começou a tocar também não tem o que ler.
    assert teste_de_dia(site, fim=lambda d: (False, cursos_robo.NAO_TOCOU)) == (
        False, "a gravação parou (a aula não começou a tocar) e saiu sem ser lida")
    assert teste_de_dia.lidas == [] and not os.listdir(teste_de_dia.brutas)


def test_a_pagina_que_ainda_carrega_nao_passa_por_a_ultima_aula(noite_do_curso):
    # O Próximo pode demorar a aparecer na página da aula: sem a conferência, a noite tomaria a aula pela última e daria
    # o curso por terminado.
    carregando = SiteDoCurso(AULAS_DO_SITE, no_alto=True)
    carregando.sem_o_proximo = 2
    assert cursos_robo.passar_para_a_seguinte(carregando, **SEM_ESPERA) == ("com vídeo", "", "Aula dois")
    # Na noite, com o Próximo demorando a cada aula aberta, o curso inteiro é gravado e só então termina.
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    resumo = noite_do_curso(SiteDoCurso(AULAS_DO_SITE, atraso_do_proximo=2), AjudanteNaHora())
    assert resumo.startswith("3 aula(s) gravada(s)")
    assert noite_do_curso.gravadas == ["Aula um", "Aula dois", "Aula três"]
    assert cursos_robo.mapa_das_aulas()["cursos"]["4"]["fim"]
    # Fora da página da aula (sem as abas), a falta do Próximo não é o fim do curso.
    fora = SiteDoCurso(AULAS_DO_SITE)
    fora.pagina = "documento"
    assert cursos_robo.passar_para_a_seguinte(fora, **SEM_ESPERA) == (None, "a página da aula não está na tela", "")


def test_o_baixar_que_tira_a_pagina_da_tela_nao_guarda_a_aula_e_a_noite_volta_pelo_comeco(noite_do_curso):
    # O documento aberto no lugar da página da aula: a aula não fica guardada (volta na noite seguinte), e a seguinte é
    # achada pelo começo do curso, sem dar o curso por terminado.
    aulas = [AULAS_DO_SITE[0], AULA_DE_DOCUMENTO, AULAS_DO_SITE[1]]
    cursos_robo.guardar_a_primeira_aula(4, aulas[0][2])
    site = SiteDoCurso(aulas, baixar_sai=True)
    resumo = noite_do_curso(site, AjudanteNaHora())
    assert resumo.startswith("2 aula(s) gravada(s), 2 guardada(s), 0 pela metade, 0 sem vídeo guardada(s)")
    assert noite_do_curso.gravadas == ["Aula um", "Aula dois"]
    import registro_processos
    linhas = registro_processos.sequencia("curso", "aula do curso", "2000-01-01 00:00:00")
    assert [(linha[2], linha[3]) for linha in linhas] == [
        ("não guardada", "curso 4, aula 2: a página da aula saiu da tela depois do Baixar")]
    assert cursos_robo.proxima_aula() == (4, 2) and cursos_robo.mapa_das_aulas()["cursos"]["4"]["fim"]


def test_a_pagina_que_volta_para_uma_aula_de_antes_nao_e_gravada_como_a_seguinte(noite_do_curso, monkeypatch):
    # 23/11/2026, 12:00: a página recarregou o endereço da barra (o da 1ª aula) logo depois do Próximo. Sem a
    # conferência pelo nome no Próximo, a noite gravaria a 1ª aula de novo, como se fosse cada uma das seguintes, a
    # noite toda.
    aulas = [AULAS_DO_SITE[0], AULA_DE_DOCUMENTO, AULAS_DO_SITE[1]]
    cursos_robo.guardar_a_primeira_aula(4, aulas[0][2])
    site = SiteDoCurso(aulas)
    original = cursos_robo._tipo_da_pagina

    def tipo_e_recarrega(d, tela, pausa):
        feito = original(d, tela, pausa)
        if d.aberta == 1:
            d._abrir(0)                      # o Chrome recarregou o endereço da barra: a 1ª aula
        return feito
    monkeypatch.setattr(cursos_robo, "_tipo_da_pagina", tipo_e_recarrega)
    resumo = noite_do_curso(site, AjudanteNaHora())
    assert resumo == ("1 aula(s) gravada(s), 1 guardada(s), 0 pela metade, 0 sem vídeo guardada(s); parou: a aula não "
                      "abriu (a página voltou para uma aula de antes)")
    assert noite_do_curso.gravadas == ["Aula um"]
    assert len(cursos_robo.mapa_das_aulas()["cursos"]["4"]["aulas"]) == 1
    # A página de uma aula de antes, mais longe (a 1ª, quando a da vez é a 3ª): o nome no Próximo dela é o de uma aula
    # do mapa.
    cursos_robo.anotar_a_aula_seguinte(4, 2, "Dia 01")
    na_primeira = SiteDoCurso(aulas)
    assert not cursos_robo.na_aula_certa(na_primeira, 4, 3, "Aula dois")
    assert cursos_robo.na_aula_certa(SiteDoCurso(aulas, aberta=2), 4, 3, "Aula dois")
    monkeypatch.setattr(cursos_robo, "_tipo_da_pagina", original)
    # Nenhuma noite gira sem fim: passado o limite de voltas, ela para.
    monkeypatch.setattr(cursos_robo, "VOLTAS_DA_NOITE", 0)
    assert noite_do_curso(SiteDoCurso(aulas), AjudanteNaHora()).endswith("parou: a noite passou de 0 voltas")


def test_o_ajudante_le_as_aulas_a_parte_e_as_que_ficaram_da_noite_anterior(bm, monkeypatch, tmp_path):
    brutas = tmp_path / "brutas"
    brutas.mkdir()
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_GRAVACOES", str(brutas))
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    cursos_robo.anotar_a_aula_seguinte(4, 2, "Aula dois")
    for numero in (1, 2):
        cursos_robo.anotar_a_aula_gravada(4, numero)
    lidas = []

    def guardar(arquivo, posicao, numero, fim):
        lidas.append((posicao, numero))
        return None, {"problema": "o som saiu mudo" if numero == 2 else ""}

    # A gravação que ficou na fila de uma noite parada no meio (o .json ao lado) é lida na seguinte.
    sobra = brutas / "20261124-010000.mkv"
    sobra.write_bytes(b"aula")
    (brutas / "20261124-010000.mkv.json").write_text(
        '{"posicao": 4, "numero": 1, "fim": "o vídeo parou"}')
    ajudante = cursos_robo.Ajudante(guardar=guardar)
    assert ajudante.mandar_as_que_ficaram() == 1
    nova = brutas / "20261124-012000.mkv"
    nova.write_bytes(b"aula")
    ajudante.mandar(str(nova), 4, 2, "o vídeo parou")
    ajudante.acabar()
    assert lidas == [(4, 1), (4, 2)] and ajudante.guardadas == 1 and ajudante.problema == "o som saiu mudo"
    assert os.listdir(brutas) == []
    # A muda volta a ficar por gravar; a outra continua gravada.
    assert cursos_robo.proxima_aula() == (4, 2)
    # O registro diz qual aula foi guardada e qual não serviu, e por quê, só com números (pedido de 23/11).
    import registro_processos
    linhas = registro_processos.sequencia("curso", "aula do curso", "2000-01-01 00:00:00")
    assert [(linha[2], linha[3]) for linha in linhas] == [("guardada", "curso 4, aula 1"),
                                                         ("não serviu", "curso 4, aula 2: o som saiu mudo")]


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


class CelularDosBaixados:
    """
    O celular de mentira com a pasta Download: cada leitura (o find depois da marca) devolve a próxima lista de
    leituras [(hora, bytes, caminho)], e o pull traz o arquivo ao servidor.
    """

    def __init__(self, leituras, conteudo=b"%PDF-1.4 documento"):
        self.leituras, self.conteudo, self.comandos, self.puxados = list(leituras), conteudo, [], []

    def shell(self, partes):
        import types
        self.comandos.append(partes)
        saida = ""
        if partes[:2] == ["find", cursos_robo.PASTA_DOS_BAIXADOS]:
            lista = self.leituras.pop(0) if len(self.leituras) > 1 else (self.leituras[0] if self.leituras else [])
            saida = "".join(f"{hora} {tamanho} {caminho}\n" for hora, tamanho, caminho in lista)
        return types.SimpleNamespace(output=saida, exit_code=0)

    def pull(self, remoto, local):
        self.puxados.append(remoto)
        with open(local, "wb") as arquivo:
            arquivo.write(self.conteudo)


def test_o_documento_baixado_e_o_mais_novo_ja_inteiro_depois_da_marca():
    celular = CelularDosBaixados([[(1700000100, 2048, "/sdcard/Download/Material da aula.pdf"),
                                   (1700000200, 10, "/sdcard/Download/.pending-1700-Outro.pdf"),
                                   (1700000300, 99, "/sdcard/Download/Planilha.xlsx.crdownload"),
                                   (1700000050, 512, "/sdcard/Download/Antigo.pdf")]])
    assert cursos_robo.baixados_depois_da_marca(celular) == [("/sdcard/Download/Material da aula.pdf", 2048),
                                                             ("/sdcard/Download/Antigo.pdf", 512)]
    comando = celular.comandos[0]
    assert comando[:6] == ["find", "/sdcard/Download", "-maxdepth", "1", "-type", "f"]
    assert comando[comando.index("-newer") + 1] == cursos_robo.MARCA_DO_CURSO
    assert cursos_robo.nome_do_documento("/sdcard/Download/Material da aula.PDF", 2) == "documento_2.pdf"
    assert cursos_robo.nome_do_documento("/sdcard/Download/sem extensao", 1) == "documento_1"


def test_o_documento_vem_ao_servidor_quando_para_de_crescer_e_sai_do_celular(tmp_path):
    caminho = "/sdcard/Download/Material da aula.pdf"
    celular = CelularDosBaixados([[], [(1700000100, 100, caminho)], [(1700000100, 2048, caminho)],
                                  [(1700000100, 2048, caminho)]])
    nome, tamanho, porque = cursos_robo.trazer_o_baixado(celular, str(tmp_path / "aula"), 1, **SEM_ESPERA)
    assert (nome, tamanho, porque) == ("documento_1.pdf", 2048, "")
    assert (tmp_path / "aula" / "documento_1.pdf").read_bytes() == b"%PDF-1.4 documento"
    assert celular.puxados == [caminho]
    # O baixado e a marca saem do celular, e a galeria fica sabendo.
    assert ["rm", "-f", caminho, cursos_robo.MARCA_DO_CURSO] in celular.comandos
    assert any(partes[:2] == ["am", "broadcast"] for partes in celular.comandos)


def test_o_documento_que_nao_aparece_ou_grande_demais_fica_so_anotado(tmp_path, monkeypatch):
    nada = CelularDosBaixados([[]])
    assert cursos_robo.trazer_o_baixado(nada, str(tmp_path / "a"), 1, espera=6, **SEM_ESPERA) == (
        None, 0, "o documento não apareceu no celular")
    assert nada.puxados == [] and not (tmp_path / "a").exists()
    monkeypatch.setattr(cursos_robo, "MAIOR_DOCUMENTO", 1000)
    caminho = "/sdcard/Download/Livro.pdf"
    grande = CelularDosBaixados([[(1700000100, 5000, caminho)]])
    assert cursos_robo.trazer_o_baixado(grande, str(tmp_path / "b"), 1, **SEM_ESPERA) == (
        None, 5000, "o documento é grande demais para o pacote")
    # Não vem ao servidor, mas sai do celular (a memória dele não enche).
    assert grande.puxados == [] and ["rm", "-f", caminho, cursos_robo.MARCA_DO_CURSO] in grande.comandos


PAGINA_DE_TEXTO = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
<node class="android.widget.FrameLayout" text="" content-desc="" bounds="[0,0][1080,2400]">
<node class="android.widget.EditText" resource-id="com.android.chrome:id/url_bar" text="escola.exemplo.pro/m/lessons/x"
 content-desc="" bounds="[211,120][691,267]" />
<node class="android.webkit.WebView" text="Escola" content-desc="" bounds="[0,270][1080,2400]">
<node class="android.view.View" text="" content-desc="" bounds="[0,270][1080,2400]">
<node class="android.widget.TextView" text="Sobre a aula" content-desc="" bounds="[60,300][900,360]" />
<node class="android.widget.TextView" text="Leia o   material   com atenção." content-desc=""
 bounds="[60,380][900,460]" />
<node class="android.widget.TextView" text="Leia o material com atenção." content-desc="" bounds="[60,380][900,460]" />
<node class="android.view.View" text="" content-desc="Material de apoio" bounds="[60,480][900,540]" />
</node>
</node>
<node class="android.widget.ImageButton" resource-id="com.android.chrome:id/menu_button" text=""
 content-desc="Personalizar e controlar o Google Chrome" bounds="[960,120][1080,267]" />
</node>
</hierarchy>"""


def test_o_texto_da_pagina_sem_a_barra_e_os_botoes_do_chrome():
    assert cursos_robo.textos_da_pagina(PAGINA_DE_TEXTO) == [
        "Escola", "Sobre a aula", "Leia o material com atenção.", "Material de apoio"]
    so_o_app = "<hierarchy><node class='android.widget.TextView' text='Eu' /></hierarchy>"
    assert cursos_robo.textos_da_pagina(so_o_app) == []
    assert cursos_robo.textos_da_pagina("") == []

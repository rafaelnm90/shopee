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
    toca no play e para sozinha aos `dura` s do vídeo; comeca_em: o segundo do vídeo em que o play começa (o site
    lembra onde a pessoa parou).
    """

    def __init__(self, relogio, dura=60, carrega=False, abre=("com vídeo", ""), comeca_em=0, **opcoes):
        super().__init__(**opcoes)
        self.relogio, self.dura, self.carrega, self.abre, self.comeca_em = relogio, dura, carrega, abre, comeca_em
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
        posicao = self.comeca_em + self.relogio() - self.comeco
        if self.pausada or posicao >= self.dura:
            return _sessao_do_chrome(2, min(posicao, self.dura))
        if self.carrega and posicao >= 20:
            return _sessao_do_chrome(6, 20)
        return _sessao_do_chrome(3, posicao)


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


def test_o_video_conferido_pela_duracao_da_lista_do_inicio_ao_fim(bm, tmp_path):
    # Pedido do Rafael de 24/11/2026: nunca achar que viu a aula sem tê-la visto. Com a duração da lista, o vídeo que
    # começa adiantado (o site lembra onde a pessoa parou) para na 1ª olhada, e o que para antes do fim fica pela
    # metade.
    tempo = [0.0]
    celular = AulaNoCelular(lambda: tempo[0], dura=600, comeca_em=200, volume=2)
    feito, _, _ = _gravar_a_aula(celular, tmp_path, tempo, duracao=600)
    assert feito == (True, False, "o vídeo não começou do início (em 203 s de 600 s)") and tempo[0] < 20
    assert celular.eventos[-3:] == ["pausa", "volume 2", "gravador parou"]
    # O vídeo que começou sozinho com a página tocou só o tempo desde que ela começou a abrir: vale.
    tempo = [0.0]
    cursos_robo._anotar(volume_antes=None)
    celular = AulaNoCelular(lambda: tempo[0], dura=300, volume=2)

    def abre_devagar(d):
        tempo[0] += 30                     # a página levou 30 s para abrir, com o vídeo tocando desde o começo
        celular.comeca_em = 30
        return "com vídeo", ""
    celular.abre = None
    destino = str(tmp_path / "devagar.mkv")
    feito = cursos_robo.gravar_a_aula(celular, "celular:5555", destino, abre_devagar, celular.tocar,
                                      pausa=lambda s: tempo.__setitem__(0, tempo[0] + s), relogio=lambda: tempo[0],
                                      abrir=lambda comando, **opcoes: ProcessoDoGravador(comando, **opcoes),
                                      madrugada=lambda: True, duracao=300)
    assert feito == (True, True, "o vídeo parou")
    # Parado antes do fim da duração da lista: pela metade; dentro da folga do fim: inteiro.
    tempo = [0.0]
    cursos_robo._anotar(volume_antes=None)
    feito, _, _ = _gravar_a_aula(AulaNoCelular(lambda: tempo[0], dura=300, volume=2), tmp_path, tempo, duracao=600)
    assert feito[:2] == (True, False) and feito[2].startswith(cursos_robo.ANTES_DO_FIM)
    assert feito[2].endswith("s de 600 s)") and cursos_robo.no_video_pela_metade(feito[2])
    tempo = [0.0]
    cursos_robo._anotar(volume_antes=None)
    feito, _, _ = _gravar_a_aula(AulaNoCelular(lambda: tempo[0], dura=590, volume=2), tmp_path, tempo, duracao=600)
    assert feito == (True, True, "o vídeo parou")
    # A página que não é mais a da aula com o vídeo tocando: a gravação para ali.
    tempo = [0.0]
    cursos_robo._anotar(volume_antes=None)
    feito, _, _ = _gravar_a_aula(AulaNoCelular(lambda: tempo[0], dura=300, volume=2), tmp_path, tempo, duracao=300,
                                 na_aula_certa=lambda d: False)
    assert feito == (True, False, "a página não é a da aula da vez")
    # Sem a duração (a aula sem ela na lista), nada disso é conferido.
    tempo = [0.0]
    cursos_robo._anotar(volume_antes=None)
    feito, _, _ = _gravar_a_aula(AulaNoCelular(lambda: tempo[0], dura=600, comeca_em=200, volume=2), tmp_path, tempo)
    assert feito == (True, True, "o vídeo parou")


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
                 texto_na_videoaula=False, slides=4, carrossel_volta=False, em_branco=0, branco_ate_voltar=False,
                 **opcoes):
        super().__init__(**opcoes)
        # A guia em branco depois do Enter (24/11/2026): em_branco leituras da tela sem nada da página, ou, com
        # branco_ate_voltar, até o Chrome sair da frente e voltar.
        self.em_branco, self.branco_ate_voltar, self.brancos, self.preso = em_branco, branco_ate_voltar, 0, False
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
        if self.abre_o_chrome and pacote == CHROME and self.na_frente != CHROME:
            self.preso = False
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
        if (self.brancos or self.preso) and not self.barra_em_foco:
            # A guia sem nada da página: só a barra com o endereço e o quadro do Chrome, sem a página (o WebView).
            self.brancos = max(0, self.brancos - 1)
            return ('<hierarchy rotation="0"><node class="android.widget.EditText" '
                    f'resource-id="com.android.chrome:id/url_bar" clickable="true" text="{barra}" content-desc="" '
                    'bounds="[211,120][691,267]" /><node class="android.widget.FrameLayout" resource-id="" '
                    'clickable="false" text="" content-desc="Guia" bounds="[0,267][1080,2394]" /></hierarchy>')
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
        if tecla == "home":
            self.na_frente, self.barra_em_foco = "com.android.launcher", False

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
                self.brancos, self.preso = self.em_branco, self.branco_ate_voltar
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


def test_a_guia_em_branco_espera_mais_e_o_chrome_sai_da_frente_e_volta():
    # 24/11/2026, das 04:05 às 04:25, nos cursos 4, 6 e 7: depois do Enter, a barra já com o endereço da aula e a guia
    # sem nada da página por minutos; a página só apareceu quando o Chrome saiu da frente e voltou. Em branco, a espera
    # passa dos 20 s, e o Chrome sai da frente e volta, sem nenhum toque na página.
    endereco = AULAS_DO_SITE[1][2]
    presa = SiteDoCurso(AULAS_DO_SITE, branco_ate_voltar=True)
    assert cursos_robo.ir_para_o_endereco(presa, endereco, **SEM_ESPERA) == ("com vídeo", "")
    assert presa.teclas == ["home"] and presa.abertos == [CHROME] and presa.toques == [(451, 193)]
    # A que só demora mais que os 20 s também abre, na mesma espera.
    lenta = SiteDoCurso(AULAS_DO_SITE, em_branco=15)
    assert cursos_robo.ir_para_o_endereco(lenta, endereco, **SEM_ESPERA) == ("com vídeo", "")
    # A que fica em branco: o Chrome sai da frente no máximo duas vezes, e o porquê vai ao registro.
    branca = SiteDoCurso(AULAS_DO_SITE, em_branco=1000)
    assert cursos_robo.ir_para_o_endereco(branca, endereco, **SEM_ESPERA) == (None, cursos_robo.EM_BRANCO)
    assert branca.teclas == ["home", "home"] and branca.toques == [(451, 193)]
    # A página de verdade (com o que o site mostra) nunca passa por em branco.
    assert not cursos_robo.pagina_em_branco(SiteDoCurso(AULAS_DO_SITE, no_alto=True).dump_hierarchy())


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


class ListaDoSite:
    """
    O Chrome de mentira com a aba Módulos de uma aula aberta (24/11/2026): módulos [(nome, [(aula, "7:28" ou None)])],
    cada um um botão "N% Nome" que abre e fecha as aulas dele embaixo; um_aberto: abrir um fecha os outros, como um
    acordeão de um só; abertos: os módulos abertos no começo (o da aula aberta). A lista começa em `comeco` da página,
    embaixo das abas; rolagem: quanto a página já rolou para baixo. O arrasto com o dedo para cima rola a página para
    baixo (até o fim dela); o para baixo fica anotado em puxados (no alto, o Chrome recarregaria a página). A barra do
    Próximo e a bolha do chat ficam por cima da página, e cada toque fica anotado com o que estava embaixo dele.
    aba_aberta=False: outra aba (Comentários) aberta, sem a lista, até o toque na aba Módulos. aberta: a aula aberta,
    pela ordem da lista inteira (a barra do Próximo mostra a seguinte; na última, nenhuma); o toque numa linha abre a
    aula dela.
    """
    TOPO, FIM, PROXIMO = 267, 2394, 2175

    def __init__(self, modulos, abertos=(), um_aberto=False, comeco=1500, rolagem=0, aba_aberta=True, aberta=0):
        self.modulos, self.abertos, self.um_aberto = modulos, set(abertos), um_aberto
        self.comeco, self.rolagem, self.aba_aberta, self.aberta = comeco, rolagem, aba_aberta, aberta
        self.toques, self.puxados, self.teclas = [], [], []
        self.todas = [aula for _modulo, aulas in modulos for aula, _tempo in aulas]

    def _itens(self):
        """(tipo, chave, texto, x1, x2, y1, y2 na página) de cada botão da lista, e o fim da página."""
        itens, y = [], self.comeco
        for numero, (nome, aulas) in enumerate(self.modulos):
            itens.append(("módulo", numero, f"{10 * numero}% {nome}", 42, 1010, y, y + 124))
            y += 192
            if numero in self.abertos:
                for aula, tempo in aulas:
                    itens.append(("aula", aula, f"{aula} {tempo}" if tempo else aula, 178, 942, y, y + 86))
                    y += 150
        return itens, y + 400

    def _na_tela(self, y1, y2):
        y1, y2 = y1 - self.rolagem + self.TOPO, y2 - self.rolagem + self.TOPO
        return max(y1, self.TOPO), min(y2, self.FIM)

    def dump_hierarchy(self):
        itens, fim = self._itens()
        nos = []
        aba = self._na_tela(self.comeco - 250, self.comeco - 60)
        if aba[1] > aba[0]:
            nos.append('<node class="android.view.View" resource-id="radix-_r_m_-trigger-modules" clickable="true" '
                       f'text="Módulos" content-desc="" bounds="[60,{aba[0]}][336,{aba[1]}]" />')
        lista = self._na_tela(self.comeco, fim - 400)
        if self.aba_aberta and lista[1] > lista[0]:
            dentro = []
            for tipo, chave, texto, x1, x2, y1, y2 in itens:
                topo, baixo = self._na_tela(y1, y2)
                if baixo <= topo:
                    continue
                ident = f"radix-_r_{chave}_" if tipo == "módulo" else ""
                if tipo == "módulo":
                    dentro.append(f'<node class="android.view.View" resource-id="" clickable="false" text="{texto}" '
                                  f'content-desc="" bounds="[{x1},{topo}][{x2},{baixo}]" />')
                dentro.append(f'<node class="android.widget.Button" resource-id="{ident}" clickable="true" '
                              f'text="{texto}" content-desc="" bounds="[{x1},{topo}][{x2},{baixo}]" />')
            nos.append('<node class="android.view.View" resource-id="radix-_r_m_-content-modules" clickable="false" '
                       f'text="" content-desc="" bounds="[42,{lista[0]}][1039,{lista[1]}]">' + "".join(dentro)
                       + "</node>")
        pagina = ('<node class="android.webkit.WebView" resource-id="" text="" content-desc="" '
                  f'bounds="[0,{self.TOPO}][1080,{self.FIM}]">' + "".join(nos) + "</node>")
        proximo = ('<node class="android.widget.Button" resource-id="" clickable="true" content-desc="" '
                   f'text="Próximo: {self.todas[self.aberta + 1]} Próxima aula:" bounds="[0,2175][1080,2394]" />'
                   if self.aberta + 1 < len(self.todas) else "")
        return ('<hierarchy rotation="0">' + pagina + proximo
                + '<node class="android.widget.Button" resource-id="" clickable="true" text="" content-desc="" '
                  'bounds="[884,1999][1039,2157]" /></hierarchy>')

    def click(self, x, y):
        if y >= self.PROXIMO and self.aberta + 1 < len(self.todas):
            self.toques.append("o Próximo")
            return
        if 884 <= x <= 1039 and 1999 <= y <= 2157:
            self.toques.append("a bolha do chat")
            return
        itens, _fim = self._itens()
        for tipo, chave, _texto, x1, x2, y1, y2 in itens:
            topo, baixo = self._na_tela(y1, y2)
            if x1 <= x <= x2 and topo <= y <= baixo:
                self.toques.append(f"{tipo} {chave}")
                if tipo == "aula":
                    self.aberta = self.todas.index(chave)
                if tipo == "módulo":
                    if chave in self.abertos:
                        self.abertos.discard(chave)
                    else:
                        self.abertos = ({chave} if self.um_aberto else self.abertos | {chave})
                return
        aba = self._na_tela(self.comeco - 250, self.comeco - 60)
        if 60 <= x <= 336 and aba[0] <= y <= aba[1]:
            self.toques.append("a aba Módulos")
            self.aba_aberta = True
            return
        self.toques.append("nada")

    def swipe(self, x1, y1, x2, y2, duracao=None):
        if y2 > y1:
            self.puxados.append((x1, y1, x2, y2))
            return
        _itens, fim = self._itens()
        self.rolagem = max(0, min(fim - (self.FIM - self.TOPO), self.rolagem + (y1 - y2)))

    def press(self, tecla):
        self.teclas.append(tecla)


MODULOS_DO_CURSO = [
    ("Comece por aqui", [("Boas vindas", "7:28")]),
    ("Primeiros passos", [("Sobre o suporte", None), ("Como escolher o produto", "12:05"), ("Regras", "3:10")]),
    ("Módulo sem aula", []),
    ("Semana 01", [(f"Dia {numero:02d}", None) for numero in range(1, 15)]),
    ("Encontros ao vivo", [("Encontro gravado", "1:02:03")]),
]
LISTA_DO_CURSO = [{"modulo": modulo, "nome": aula, "segundos": cursos_robo.segundos_do_tempo(tempo) if tempo else None}
                  for modulo, aulas in MODULOS_DO_CURSO for aula, tempo in aulas]


@pytest.mark.parametrize("um_aberto", [False, True])
def test_a_lista_das_aulas_lida_pela_aba_modulos_na_ordem_sem_tocar_numa_aula(um_aberto):
    # Pedido do Rafael de 24/11/2026 (00:17): os nomes de todas as aulas, na ordem, para o check de cada uma. O módulo
    # da aula aberta já vem aberto; os outros abrem pelo botão; o vazio fica sem aula; o comprido passa de uma tela.
    site = ListaDoSite(MODULOS_DO_CURSO, abertos={0}, um_aberto=um_aberto)
    lista, porque = cursos_robo.ler_a_lista(site, pausa=lambda segundos: None)
    assert (lista, porque) == (LISTA_DO_CURSO, "")
    # Só os botões dos módulos fechados, um toque em cada; nenhuma aula, nem o Próximo, nem a bolha do chat.
    assert site.toques == ["módulo 1", "módulo 2", "módulo 3", "módulo 4"]
    # A página só rolou para baixo (no alto, o arrasto para baixo recarregaria a 1ª aula).
    assert site.puxados == []


def test_a_lista_com_a_pagina_no_alto_e_a_aba_de_comentarios_aberta():
    # A página no alto (o player em cima): a lista aparece rolando para baixo; com outra aba aberta, a aba Módulos é
    # tocada uma vez.
    site = ListaDoSite(MODULOS_DO_CURSO[:2], comeco=2600, aba_aberta=False)
    lista, porque = cursos_robo.ler_a_lista(site, pausa=lambda segundos: None)
    assert (lista, porque) == (LISTA_DO_CURSO[:4], "")
    assert site.toques == ["a aba Módulos", "módulo 0", "módulo 1"] and site.puxados == []


def test_a_aula_abre_pela_lista_tambem_com_a_aba_de_comentarios_aberta(bm, monkeypatch):
    # Nas gravações da noite de 24/11/2026, a aba aberta embaixo da aula era a de Comentários (o site lembra a última
    # escolhida): sem a lista na tela, a aba Módulos é tocada uma vez, e a aula abre pela lista como sempre.
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    cursos_robo.guardar_a_lista(4, LISTA_DO_CURSO)
    monkeypatch.setattr(cursos_robo, "ir_para_o_endereco", lambda d, endereco, pausa=None: (cursos_robo.COM_VIDEO, ""))
    monkeypatch.setattr(cursos_robo, "pausar_o_que_toca", lambda d, pausa=None: True)
    site = ListaDoSite(MODULOS_DO_CURSO, comeco=2600, aba_aberta=False, aberta=4)
    assert cursos_robo.abrir_pela_lista(site, 4, 2, pausa=lambda segundos: None) == (True, "")
    assert site.toques == ["a aba Módulos", "módulo 1", "aula Sobre o suporte"] and site.puxados == []


def test_a_lista_que_comeca_cortada_no_alto_nao_vale():
    # A página já rolada para o meio da lista: o começo dela ficou para trás, e a página não sobe (nada é guardado).
    site = ListaDoSite(MODULOS_DO_CURSO, abertos={0, 1, 3}, rolagem=2000)
    assert cursos_robo.ler_a_lista(site, pausa=lambda segundos: None) == (None, cursos_robo.LISTA_SEM_O_COMECO)
    assert site.toques == [] and site.puxados == []


def test_os_itens_da_lista_so_de_dentro_da_aba_modulos():
    # Os botões do leitor de PDF ("100%"), o Próximo e a bolha do chat ficam fora da aba Módulos; o botão cortado pela
    # beira da tela não é tocado.
    site = ListaDoSite(MODULOS_DO_CURSO, abertos={1}, rolagem=500)
    tela = site.dump_hierarchy().replace(
        '<node class="android.view.View" resource-id="radix-_r_m_-trigger-modules"',
        '<node class="android.widget.Button" resource-id="" clickable="true" text="100%" content-desc="" '
        'bounds="[322,400][435,450]" /><node class="android.view.View" resource-id="radix-_r_m_-trigger-modules"')
    caixa, itens = cursos_robo.itens_da_lista(tela)
    assert caixa[1] == 1267
    assert [(item["tipo"], item["nome"], item["segundos"]) for item in itens] == [
        ("módulo", "Comece por aqui", None), ("módulo", "Primeiros passos", None), ("aula", "Sobre o suporte", None),
        ("aula", "Como escolher o produto", 725), ("aula", "Regras", 190), ("módulo", "Módulo sem aula", None),
        ("módulo", "Semana 01", None)]
    # Embaixo da barra do Próximo (e cortado pela beira da tela), nenhum botão é tocado.
    assert [cursos_robo._tocavel(tela, item["caixa"]) for item in itens] == [True] * 5 + [False, False]
    assert cursos_robo.itens_da_lista("<quebrado") is None
    assert cursos_robo.itens_da_lista(tela.replace("-content-modules", "-content-coments")) is None


def test_a_lista_pelo_explorar_fica_no_mapa_e_vai_ao_claude_sem_os_enderecos(bm, monkeypatch):
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    abertos = []
    monkeypatch.setattr(cursos_robo, "ir_para_o_endereco",
                        lambda d, endereco, pausa=None: abertos.append(endereco) or (cursos_robo.COM_VIDEO, ""))
    monkeypatch.setattr(cursos_robo, "pausar_o_que_toca", lambda d, pausa=None: True)
    # O passo toca a aula (o endereço abre a aula em que o site parou): o celular fica mudo, também de dia.
    assert cursos_robo.toca_aula("curso", "lista:4")
    site = ListaDoSite(MODULOS_DO_CURSO, abertos={0})
    ok, texto = cursos_robo.curso_no_explorar(site, "lista:4", pausa=lambda segundos: None)
    assert ok and abertos == [AULAS_DO_SITE[0][2]]
    # Só números no log público: nem os nomes dos módulos, nem os das aulas.
    assert texto == "lista do curso 4: 4 módulo(s) com aula, 19 aula(s), 4 com a duração (84 min de vídeo) e 15 sem"
    assert not any(modulo in texto for modulo, _aulas in MODULOS_DO_CURSO)
    curso = cursos_robo.mapa_das_aulas()["cursos"]["4"]
    assert curso["lista"] == LISTA_DO_CURSO and curso["lista_em"]
    # O pacote do Claude leva o mapa sem os endereços, mesmo sem aula guardada.
    assert cursos_robo.tem_lista()
    import io, json, zipfile
    with zipfile.ZipFile(io.BytesIO(cursos_robo.pacote_das_aulas())) as pacote:
        assert pacote.namelist() == ["mapa.json"]
        mapa = json.loads(pacote.read("mapa.json"))
    assert mapa["ordem"] == list(cursos_robo.ORDEM_DOS_CURSOS) and mapa["cursos"]["4"]["lista"] == LISTA_DO_CURSO
    assert "lessons" not in json.dumps(mapa)
    # A lista que não chega ao fim não troca a do mapa, e a tela dela vai ao Claude pelos casos.
    casos = []
    monkeypatch.setattr(cursos_robo, "guardar_o_caso", lambda d, motivo, resultado="", passo="": casos.append(
        (motivo, resultado, passo)))
    ok, texto = cursos_robo.curso_no_explorar(ListaDoSite(MODULOS_DO_CURSO, rolagem=2000), "lista:4",
                                              pausa=lambda segundos: None)
    assert not ok and texto == f"a lista do curso 4 não foi lida ({cursos_robo.LISTA_SEM_O_COMECO})"
    assert casos == [(cursos_robo.LISTA_SEM_O_COMECO, "lista não lida", "ler a lista das aulas")]
    assert cursos_robo.mapa_das_aulas()["cursos"]["4"]["lista"] == LISTA_DO_CURSO


@pytest.mark.parametrize("numero, toques", [
    (1, []), (3, ["módulo 1", "aula Como escolher o produto"]), (5, ["módulo 3", "aula Dia 01"]),
    (18, ["módulo 3", "aula Dia 14"]), (19, ["módulo 4", "aula Encontro gravado"])])
def test_a_aula_aberta_pelo_nome_na_lista_e_conferida_pelo_proximo(bm, monkeypatch, numero, toques):
    # O caminho da noite (pedido do Rafael de 24/11/2026, as aulas em ordem): o curso abre pelo endereço (a aula em
    # que o site parou), a página rola até a linha da aula, o módulo dela abre pelo botão, e a linha é tocada; o Próximo
    # confere que abriu a aula certa. Só o módulo da aula é aberto; a 1ª, no módulo já aberto, é tocada direto.
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    cursos_robo.guardar_a_lista(4, LISTA_DO_CURSO)
    monkeypatch.setattr(cursos_robo, "ir_para_o_endereco", lambda d, endereco, pausa=None: (cursos_robo.COM_VIDEO, ""))
    monkeypatch.setattr(cursos_robo, "pausar_o_que_toca", lambda d, pausa=None: True)
    site = ListaDoSite(MODULOS_DO_CURSO, abertos={0}, aberta=2)
    assert cursos_robo.abrir_pela_lista(site, 4, numero, pausa=lambda segundos: None) == (True, "")
    nome = LISTA_DO_CURSO[numero - 1]["nome"]
    assert site.todas[site.aberta] == nome
    assert site.toques == (toques or [f"aula {nome}"]) and site.puxados == []


def test_a_aula_que_nao_aparece_na_lista_ou_abre_outra_nao_vale(bm, monkeypatch):
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    monkeypatch.setattr(cursos_robo, "ir_para_o_endereco", lambda d, endereco, pausa=None: (cursos_robo.COM_VIDEO, ""))
    monkeypatch.setattr(cursos_robo, "pausar_o_que_toca", lambda d, pausa=None: True)
    sem_pausa = {"pausa": lambda segundos: None}
    # Antes do curso:lista:N, nenhuma aula abre pela lista.
    assert cursos_robo.abrir_pela_lista(ListaDoSite(MODULOS_DO_CURSO), 4, 1, **sem_pausa) == (
        False, cursos_robo.FORA_DA_LISTA)
    cursos_robo.guardar_a_lista(4, LISTA_DO_CURSO)
    assert cursos_robo.abrir_pela_lista(ListaDoSite(MODULOS_DO_CURSO), 4, 20, **sem_pausa) == (
        False, cursos_robo.FORA_DA_LISTA)
    # O site mudou a lista: a aula não está mais no módulo dela.
    outra = [(modulo, [aula for aula in aulas if aula[0] != "Regras"]) for modulo, aulas in MODULOS_DO_CURSO]
    site = ListaDoSite(outra, abertos={0})
    assert cursos_robo.abrir_pela_lista(site, 4, 4, **sem_pausa) == (False, cursos_robo.SEM_A_AULA_NA_LISTA)
    assert site.puxados == [] and not any(toque.startswith("aula") for toque in site.toques)

    # A linha tocada que não abre a aula (o Próximo não muda): a página não é a da aula da vez.
    class SemAbrir(ListaDoSite):
        def click(self, x, y):
            aberta = self.aberta
            super().click(x, y)
            self.aberta = aberta
    assert cursos_robo.abrir_pela_lista(SemAbrir(MODULOS_DO_CURSO, abertos={0}, aberta=9), 4, 3, **sem_pausa) == (
        False, cursos_robo.OUTRA_AULA)


def test_o_explorar_abre_a_aula_pela_lista_e_guarda_a_tela_para_o_claude(bm, monkeypatch):
    cursos_robo.guardar_a_primeira_aula(4, AULAS_DO_SITE[0][2])
    monkeypatch.setattr(cursos_robo, "ir_para_o_endereco", lambda d, endereco, pausa=None: (cursos_robo.COM_VIDEO, ""))
    monkeypatch.setattr(cursos_robo, "pausar_o_que_toca", lambda d, pausa=None: True)
    monkeypatch.setattr(cursos_robo, "midia_do_chrome", lambda d: None)
    casos = []
    monkeypatch.setattr(cursos_robo, "guardar_o_caso", lambda d, motivo, resultado="", passo="": casos.append(
        (motivo, resultado, passo)))
    site = ListaDoSite(MODULOS_DO_CURSO, abertos={0})
    assert cursos_robo.toca_aula("curso", "tocar:4:3")
    assert cursos_robo.curso_no_explorar(site, "tocar:4:3", pausa=lambda s: None) == (
        False, "o curso 4 ainda não tem a lista das aulas (curso:lista:4)")
    cursos_robo.guardar_a_lista(4, LISTA_DO_CURSO)
    assert cursos_robo.curso_no_explorar(site, "tocar:4:3", pausa=lambda s: None) == (
        True, "aula 3 do curso 4 aberta pela lista: sem o player à vista; sem vídeo no Chrome")
    assert casos == [("aula aberta pela lista", "aula pela lista", "abrir a aula pela lista")]
    assert cursos_robo.curso_no_explorar(site, "tocar:4:30", pausa=lambda s: None) == (
        False, f"a aula 30 do curso 4 não abriu pela lista ({cursos_robo.FORA_DA_LISTA})")
    assert not cursos_robo.curso_no_explorar(site, "tocar:9:1", pausa=lambda s: None)[0]


class CursoComLista(SiteDoCurso):
    """
    O site do curso com a aba Módulos embaixo da aula (24/11/2026): as aulas do SiteDoCurso, na ordem, nos módulos
    [(nome, quantas aulas)]. A página rola (rolagem: quanto ela desceu; 0 no alto, com a tela do SiteDoCurso e o
    player): o arrasto com o dedo para cima a desce, o com o dedo para baixo a sobe e, começado com ela no alto,
    recarrega o endereço da barra (recarregadas). Rolada, a tela mostra a lista: o botão de cada módulo ("N% Nome")
    abre e fecha as aulas dele embaixo, e o módulo da aula aberta fica aberto; o toque no nome de uma aula a abre sem
    mudar a rolagem (a página fica na lista; tocadas), e o Próximo e o Enter abrem a aula do alto. passa_no_fim: no fim
    do vídeo (fim_do_video), o site abre sozinho a aula seguinte, do alto, e o vídeo dela começa.
    """
    COMECO, TOPO, ALTURA = 2300, 267, 2127

    def __init__(self, aulas, modulos=None, passa_no_fim=False, **opcoes):
        super().__init__(aulas, **opcoes)
        self.modulos = modulos or [("Módulo único", len(aulas))]
        self.rolagem, self.recarregadas, self.tocadas, self.passa_no_fim = 0, 0, [], passa_no_fim
        self.modulos_abertos = {self._modulo_de(self.aberta)}

    def _modulo_de(self, numero):
        fim = 0
        for indice, (_nome, quantas) in enumerate(self.modulos):
            fim += quantas
            if numero < fim:
                return indice
        return len(self.modulos) - 1

    def _abrir(self, numero, do_alto=True):
        super()._abrir(numero)
        if do_alto:
            self.rolagem = 0
        self.no_alto = not self.rolagem
        self.modulos_abertos = getattr(self, "modulos_abertos", set()) | {self._modulo_de(numero)}

    def fim_do_video(self):
        if self.passa_no_fim and self.aberta + 1 < len(self.aulas):
            self.aberturas.append((self.volume, self.gravando))
            self._abrir(self.aberta + 1)
            if self._com_video(self.aberta):
                self.midia = _sessao_do_chrome(3, 0)

    def _itens(self):
        itens, y, numero = [], self.COMECO, 0
        for indice, (nome, quantas) in enumerate(self.modulos):
            itens.append(("módulo", indice, f"{10 * indice}% {nome}", 42, 1010, y, y + 124))
            y += 192
            for _ in range(quantas):
                if indice in self.modulos_abertos:
                    aula, segundos = self.aulas[numero][0], self.aulas[numero][1]
                    texto = f"{aula} {segundos // 60}:{segundos % 60:02d}" if segundos else aula
                    itens.append(("aula", numero, texto, 178, 942, y, y + 86))
                    y += 150
                numero += 1
        return itens, y + 400

    def _na_tela(self, y1, y2):
        return max(y1 - self.rolagem + self.TOPO, self.TOPO), min(y2 - self.rolagem + self.TOPO, 2394)

    def dump_hierarchy(self):
        tela = super().dump_hierarchy()
        if not self.rolagem or self.na_frente != CHROME or self.pagina or self.nova_guia or self.barra_em_foco:
            return tela
        itens, fim = self._itens()
        botoes = []
        for tipo, chave, texto, x1, x2, y1, y2 in itens:
            topo, baixo = self._na_tela(y1, y2)
            if baixo > topo:
                ident = f"radix-_r_{chave}_" if tipo == "módulo" else ""
                botoes.append(f'<node class="android.widget.Button" resource-id="{ident}" clickable="true" '
                              f'text="{texto}" content-desc="" bounds="[{x1},{topo}][{x2},{baixo}]" />')
        nos = []
        topo, baixo = self._na_tela(self.COMECO, fim - 400)
        if baixo > topo:
            nos.append('<node class="android.view.View" resource-id="radix-_r_m_-content-modules" clickable="false" '
                       f'text="" content-desc="" bounds="[42,{topo}][1039,{baixo}]">' + "".join(botoes) + "</node>")
        if self.aberta + 1 < len(self.aulas):
            nos.append('<node class="android.widget.Button" resource-id="" clickable="true" content-desc="" '
                       f'text="Próximo: {self.aulas[self.aberta + 1][0]} Próxima aula:" '
                       'bounds="[0,2175][1080,2394]" />')
        barra = ('<node class="android.widget.EditText" resource-id="com.android.chrome:id/url_bar" clickable="true" '
                 f'text="{self.endereco_na_barra.removeprefix("https://")}" content-desc="" '
                 'bounds="[211,120][691,267]" />')
        return ('<hierarchy rotation="0">' + barra + '<node class="android.webkit.WebView" resource-id="" text="" '
                'content-desc="" bounds="[0,267][1080,2394]">' + "".join(nos) + "</node></hierarchy>")

    def swipe(self, x1, y1, x2, y2, duracao=None):
        if self.pagina or self.nova_guia or self.barra_escondida:
            return super().swipe(x1, y1, x2, y2, duracao)
        self.rolagens.append((x1, y1, x2, y2))
        if y2 > y1 and not self.rolagem:
            # No alto da página, o arrasto para baixo é o "puxar para atualizar": ela recarrega o endereço da barra.
            self.recarregadas += 1
            self._abrir(next(n for n, aula in enumerate(self.aulas) if aula[2] == self.endereco_na_barra))
            return
        _itens, fim = self._itens()
        self.rolagem = max(0, min(fim - self.ALTURA, self.rolagem + y1 - y2))
        self.no_alto = not self.rolagem

    def click(self, x, y):
        if not self.rolagem or y >= 2175 or y <= 267 or self.pagina:
            return super().click(x, y)
        self.toques.append((x, y))
        itens, _fim = self._itens()
        for tipo, chave, _texto, x1, x2, y1, y2 in itens:
            topo, baixo = self._na_tela(y1, y2)
            if x1 <= x <= x2 and topo <= y <= baixo:
                if tipo == "aula":
                    self.tocadas.append(chave)
                    self.aberturas.append((self.volume, self.gravando))
                    self._abrir(chave, do_alto=False)
                else:
                    self.modulos_abertos ^= {chave}
                return


# O curso da noite: 2 módulos, a 3ª aula um documento; o endereço guardado abre a 4ª (onde o site parou).
AULAS_DA_LISTA = [("Aula um", 300, "https://escola.exemplo.pro/m/lessons/aaa111"),
                  ("Aula dois", 600, "https://escola.exemplo.pro/m/lessons/bbb222"),
                  AULA_DE_DOCUMENTO,
                  ("Aula quatro", 120, "https://escola.exemplo.pro/m/lessons/ddd444")]
MODULOS_DA_LISTA = [("Comece por aqui", 2), ("Prática", 2)]


def _lista_no_mapa(posicao, aulas=AULAS_DA_LISTA, modulos=MODULOS_DA_LISTA, retomada=3):
    """O curso com o endereço guardado (o da aula `retomada`, onde o site parou) e a lista das aulas no mapa."""
    assert cursos_robo.guardar_a_primeira_aula(posicao, aulas[retomada][2])
    nomes = [nome for nome, quantas in modulos for _ in range(quantas)]
    cursos_robo.guardar_a_lista(posicao, [{"modulo": modulo, "nome": aula[0], "segundos": aula[1] or None}
                                          for modulo, aula in zip(nomes, aulas)])


def _curso_da_noite(aulas=AULAS_DA_LISTA, modulos=MODULOS_DA_LISTA, retomada=3, **opcoes):
    """O site com o endereço guardado aberto antes numa aula qualquer do curso (a da retomada, sem o login)."""
    return CursoComLista(aulas, modulos, aberta=retomada, **opcoes)


def _registro_das_aulas():
    import registro_processos
    return [(linha[2], linha[3]) for linha in
            registro_processos.sequencia("curso", "aula do curso", "2000-01-01 00:00:00")]


def test_o_mapa_das_aulas_pela_lista_na_ordem_e_o_check_do_claude(bm):
    # Pedidos do Rafael de 24/11/2026: aula por aula, da 1ª à última de cada curso, curso por curso (P293 1), e o check
    # de cada aula só depois de o Claude conferir que ela foi vista inteira e que algo foi aprendido.
    assert cursos_robo.proxima_aula() is None
    assert not cursos_robo.guardar_a_primeira_aula(9, AULAS_DA_LISTA[0][2])
    assert not cursos_robo.guardar_a_primeira_aula(4, "x/y")
    _lista_no_mapa(5)
    _lista_no_mapa(4)
    assert cursos_robo.proxima_aula() == (4, 1)
    # O endereço guardado só leva ao curso; ele pode ser trocado a qualquer hora, e a lista fica.
    assert cursos_robo.guardar_a_primeira_aula(4, AULAS_DA_LISTA[1][2])
    assert cursos_robo.endereco_do_curso(4) == AULAS_DA_LISTA[1][2] and len(cursos_robo.lista_do_curso(4)) == 4
    # Guardada pela noite, a aula espera a conferência, e a noite segue para a seguinte; a que não ficou guardada nesta
    # noite fica para a seguinte.
    cursos_robo.anotar_a_aula_gravada(4, 1, _br("2026-11-25 00:30"))
    assert cursos_robo.proxima_aula() == (4, 2) and cursos_robo.proxima_aula(pular={(4, 2)}) == (4, 3)
    cursos_robo.anotar_a_aula_gravada(4, 3, sem_video=True)
    assert cursos_robo.lista_do_curso(4)[2]["sem_video"]
    assert cursos_robo.resumo_do_mapa().startswith(
        "curso 4: 0 de 4 aula(s) vista(s), 2 esperando a conferência; curso 5: 0 de 4 aula(s) vista(s)")
    # O check do Claude; a que não serviu volta inteira para a noite (P295 1).
    assert cursos_robo.conferir_as_aulas(4, {1, 3}) == 2
    assert cursos_robo.conferir_as_aulas(4, {3}, vistas=False) == 1
    lista = cursos_robo.lista_do_curso(4)
    assert lista[0]["vista_em"] and not {"gravada_em", "sem_video", "vista_em"} & set(lista[2])
    assert cursos_robo.proxima_aula() == (4, 2)
    assert cursos_robo.resumo_do_mapa().startswith("curso 4: 1 de 4 aula(s) vista(s), 0 esperando a conferência")
    # A gravada que não serviu (preta ou muda) volta a ficar por gravar; o curso todo visto passa ao seguinte.
    cursos_robo.anotar_a_aula_gravada(4, 2)
    cursos_robo.desmarcar_a_aula(4, 2)
    assert cursos_robo.proxima_aula() == (4, 2)
    cursos_robo.conferir_as_aulas(4, range(1, 5))
    assert cursos_robo.proxima_aula() == (5, 1)
    assert "curso 1: sem a lista das aulas" in cursos_robo.resumo_do_mapa()


def test_os_numeros_da_conferencia_so_em_numeros():
    assert cursos_robo.numeros_das_aulas("4:15,16;5:2-4") == {4: {15, 16}, 5: {2, 3, 4}}
    assert cursos_robo.numeros_das_aulas(" 1: 3 - 5 , 9 ; ") == {1: {3, 4, 5, 9}}
    assert cursos_robo.numeros_das_aulas("") == {}
    for errado in ("4", "9:1", "4:a", "4:5-2", "4:0", "Aula um"):
        with pytest.raises(ValueError):
            cursos_robo.numeros_das_aulas(errado)


def test_a_conferencia_pelo_workflow_marca_as_vistas_e_manda_refazer(bm, capsys):
    _lista_no_mapa(4)
    assert cursos_robo.main(["aulas", "vistas", "4:1-2"]) == 0
    saida = capsys.readouterr().out
    assert saida.startswith("curso 4: 2 aula(s) marcada(s) como vista(s)\ncurso 4: 2 de 4 aula(s) vista(s)")
    assert cursos_robo.main(["aulas", "refazer", "4:2"]) == 0
    assert capsys.readouterr().out.startswith("curso 4: 1 aula(s) para a noite gravar de novo")
    assert cursos_robo.proxima_aula() == (4, 2)
    # Fora da lista ou fora do formato, nada muda.
    assert cursos_robo.main(["aulas", "vistas", "4:9"]) == 2
    assert "a 9 não existe. Nada mudou." in capsys.readouterr().out
    assert cursos_robo.main(["aulas", "vistas", "Aula um"]) == 2
    assert [bool(aula.get("vista_em")) for aula in cursos_robo.lista_do_curso(4)] == [True, False, False, False]
    # O workflow manda ao servidor só os números e os separadores.
    with open(os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "cursos_robo.yml"),
              encoding="utf-8") as arquivo:
        workflow = arquivo.read()
    assert "tr -dc '0-9:;,-'" in workflow and "servidor \"$PEDIDO '$NUMEROS'\"" in workflow


def test_o_claude_guarda_o_endereco_de_cada_curso_pelo_explorar(bm):
    # O passo curso:primeira:N lê o endereço na barra do Chrome e o guarda no banco; o log diz só números.
    site = SiteDoCurso(AULAS_DO_SITE, aberta=1)
    assert cursos_robo.curso_no_explorar(site, "primeira:4") == (True, "endereço do curso 4 guardado")
    assert cursos_robo.endereco_do_curso(4) == AULAS_DO_SITE[1][2]
    assert cursos_robo.curso_no_explorar(site, "primeira:9") == (
        False, "o curso vai de 1 a 7 (a posição na lista de Turmas)")
    assert not cursos_robo.curso_no_explorar(site, "primeira:x")[0]
    assert not cursos_robo.curso_no_explorar(site, "segunda:4")[0]
    fora = SiteDoCurso([("Cursos", 0, "https://escola.exemplo.pro/m/courses")])
    assert cursos_robo.curso_no_explorar(fora, "primeira:5") == (False, "a tela não é a de uma aula do curso")
    ok, resumo = cursos_robo.curso_no_explorar(site, "")
    assert ok and resumo.startswith("curso 4: sem a lista das aulas; curso 5: sem a lista das aulas")
    assert "escola" not in resumo and "Aula" not in resumo


@pytest.fixture
def noite_do_curso(bm, monkeypatch, tmp_path):
    """
    A madrugada do curso com o celular livre, o disco folgado e a gravação de mentira, na ordem da de verdade (o
    gravador, o volume, a página, o play e a conferência da aula): fim_da(nome) diz como o vídeo acabou; no fim dele,
    o site pode passar sozinho para a aula seguinte. Anota as aulas gravadas e a duração que cada uma levou.
    """
    import contextlib
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_GRAVACOES", str(tmp_path / "brutas"))
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_AULAS", str(tmp_path / "aulas"))
    monkeypatch.setattr(cursos_robo, "disco_usado", lambda caminho=None: 20)
    monkeypatch.setattr(cursos_robo, "_madrugada_agora", lambda: True)
    gravadas, duracoes, casos = [], [], []
    monkeypatch.setattr(cursos_robo, "guardar_o_caso",
                        lambda d, motivo, resultado="não abriu", passo="": casos.append((motivo, resultado)),
                        raising=False)

    def rodar(site, ajudante, fim_da=lambda nome: (True, "o vídeo parou")):
        def gravar(d, alvo, destino, ir_para_a_aula, tocar, pausa=None, duracao=None, na_aula_certa=None, **_):
            d.gravando = True
            try:
                cursos_robo.subir_o_volume(d)
                tipo, porque = ir_para_a_aula(d)
                if not tipo:
                    return False, False, (porque if porque in cursos_robo.PARADAS_DA_AULA
                                          else f"a aula não abriu ({porque})")
                if tipo == cursos_robo.SEM_VIDEO:
                    return True, False, tipo
                assert tocar(d)
                if na_aula_certa and not na_aula_certa(d):
                    return True, False, cursos_robo.OUTRA_PAGINA
                gravadas.append(d.aulas[d.aberta][0])
                duracoes.append(duracao)
                with open(destino, "wb") as arquivo:
                    arquivo.write(b"aula")
                feito = (True,) + tuple(fim_da(gravadas[-1]))
                if feito[2] in ("o vídeo parou", "outro vídeo começou"):
                    d.fim_do_video()
                return feito
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
    rodar.gravadas, rodar.duracoes, rodar.casos = gravadas, duracoes, casos
    return rodar


def test_a_noite_grava_as_aulas_na_ordem_da_lista_e_nao_pula_nenhuma(noite_do_curso):
    # Vídeo do Rafael de 24/11/2026, 00:17: o endereço guardado abre a aula em que o site parou, e a noite pulava
    # aulas. A 1ª do curso abre pela lista (o toque no nome dela, com o gravador gravando), e cada uma das outras pelo
    # Próximo da de antes, conferida pelo nome dela na lista; o documento é guardado com a página, e a página nunca é
    # arrastada para baixo no alto (o Chrome a recarregaria).
    _lista_no_mapa(4)
    site, ajudante = _curso_da_noite(), AjudanteNaHora()
    resumo = noite_do_curso(site, ajudante)
    assert resumo == ("3 aula(s) gravada(s), 3 guardada(s), 0 pela metade, 1 sem vídeo guardada(s); parou: nenhuma "
                      "aula por gravar")
    assert noite_do_curso.gravadas == ["Aula um", "Aula dois", "Aula quatro"]
    assert noite_do_curso.duracoes == [300, 600, 120]
    assert ajudante.lidas == [(4, 1, "o vídeo parou"), (4, 2, "o vídeo parou"), (4, 4, "o vídeo parou")]
    assert site.tocadas == [0] and site.recarregadas == 0
    lista = cursos_robo.lista_do_curso(4)
    assert all(aula["gravada_em"] for aula in lista) and [bool(aula.get("sem_video")) for aula in lista] == [
        False, False, True, False]
    assert not any(aula.get("vista_em") for aula in lista)
    assert _registro_das_aulas() == [("guardada sem vídeo",
                                      "curso 4, aula 3: 1 tela(s), 5 linha(s), 1 link(s), documento de 2 KB")]
    (pasta,) = os.listdir(cursos_robo.PASTA_DAS_AULAS)
    assert pasta.endswith("-c04-a003") and not cursos_robo.gravando()
    # O documento saiu do celular, e nenhum link foi tocado.
    assert site.baixados == [] and (464, 1942) not in site.toques


def test_a_noite_que_comeca_com_a_shopee_na_frente_e_a_sessao_vencida(noite_do_curso, monkeypatch):
    # A rodada do robô deixa a Shopee no Eu: o Chrome vem antes da 1ª aula. Com a sessão do site vencida, o login fica
    # fora da gravação (o curso abre antes, mudo e sem o gravador).
    _lista_no_mapa(4)
    monkeypatch.setattr(cursos_robo, "_entrar", _login_de_mentira(), raising=False)
    site = _curso_da_noite(na_frente="com.shopee.br", sessao_vencida=True, volume=6)
    resumo = noite_do_curso(site, AjudanteNaHora())
    assert resumo.startswith("3 aula(s) gravada(s)") and noite_do_curso.gravadas[0] == "Aula um"
    assert site.abertos == [CHROME] and site.logins == [(0, False)]


def test_a_aula_so_abre_muda_ou_com_o_gravador_gravando(noite_do_curso):
    # O vídeo pode começar a tocar sozinho quando a página da aula abre, e o celular fica no quarto do Rafael (pedido
    # dele, 22/11): cada aula aberta antes da gravação abre com o volume de mídia em 0; a da gravação, com o volume da
    # aula só com o gravador gravando (o som vai só ao servidor). O de antes fica guardado, e o robô o devolve.
    _lista_no_mapa(4)
    site = _curso_da_noite(volume=6, autoplay=True)
    assert noite_do_curso(site, AjudanteNaHora()).startswith("3 aula(s) gravada(s)")
    assert all(volume == 0 or gravando for volume, gravando in site.aberturas)
    assert (0, False) in site.aberturas and (8, True) in site.aberturas
    assert cursos_robo.estado_da_noite()["volume_antes"] == 6
    # O vídeo que começou sozinho não leva o toque no play (seria a pausa): só a 1ª aula, pausada enquanto a página
    # subia da lista, volta pelo play.
    assert site.toques.count((539, 793)) == 1 and site.recarregadas == 0


def test_a_aula_que_nao_abre_fica_no_registro_com_o_porque(noite_do_curso):
    # O porquê de a aula não abrir vai ao registro de cada aula, para o relatório da manhã; 2 seguidas param a noite.
    _lista_no_mapa(4)
    site = _curso_da_noite(na_frente="com.android.systemui", abre_o_chrome=False)
    resumo = noite_do_curso(site, AjudanteNaHora())
    assert resumo == ("0 aula(s) gravada(s), 0 guardada(s), 0 pela metade, 0 sem vídeo guardada(s); parou: a aula não "
                      "abriu (o Chrome não veio para a frente)")
    assert _registro_das_aulas() == [
        ("não abriu", "curso 4, aula 1: a aula não abriu (o Chrome não veio para a frente)")] * 2
    # A tela da 1ª que não abriu fica guardada para o Claude achar o porquê (só uma por noite).
    assert noite_do_curso.casos == [("a aula não abriu (o Chrome não veio para a frente)", "não abriu")]


def test_sem_a_leitura_do_volume_a_aula_nao_abre(noite_do_curso):
    # Sem a certeza de o celular estar mudo, a aula não abre: nada é tocado, e a noite para.
    _lista_no_mapa(4)
    surdo = _curso_da_noite(responde=False)
    resumo = noite_do_curso(surdo, AjudanteNaHora())
    assert resumo.endswith("parou: o celular não ficou mudo antes de abrir a aula") and surdo.toques == []


def test_a_aula_sem_video_que_nao_fica_guardada_volta_e_a_noite_segue(noite_do_curso):
    # Nenhuma aula é pulada (23/11/2026): o documento que não vem deixa a aula para a noite seguinte, e nesta a noite
    # segue pelo Próximo dela, que volta pela lista (muda e sem o gravador).
    _lista_no_mapa(4)
    site = _curso_da_noite(baixa=False)
    resumo = noite_do_curso(site, AjudanteNaHora())
    assert resumo.startswith("3 aula(s) gravada(s), 3 guardada(s), 0 pela metade, 0 sem vídeo guardada(s)")
    assert noite_do_curso.gravadas == ["Aula um", "Aula dois", "Aula quatro"]
    assert _registro_das_aulas() == [("não guardada", "curso 4, aula 3: o documento não apareceu no celular")]
    assert noite_do_curso.casos == [("o documento não apareceu no celular", "não guardada")]
    assert cursos_robo.proxima_aula() == (4, 3) and site.tocadas == [0, 2] and site.recarregadas == 0


def test_o_robo_que_pede_o_celular_deixa_a_aula_para_a_noite_seguinte(noite_do_curso):
    # O robô da Shopee Vídeo tem a preferência (22/11): a aula fica pela metade, o vídeo dela sai, e ela volta depois,
    # inteira, do início (P295 1).
    _lista_no_mapa(4)
    resumo = noite_do_curso(_curso_da_noite(), AjudanteNaHora(),
                            fim_da=lambda nome: (True, "o vídeo parou") if nome == "Aula um"
                            else (False, "o robô pediu o celular"))
    assert resumo == ("1 aula(s) gravada(s), 1 guardada(s), 1 pela metade, 0 sem vídeo guardada(s); parou: o robô "
                      "pediu o celular")
    assert cursos_robo.proxima_aula() == (4, 2) and os.listdir(cursos_robo.PASTA_DAS_GRAVACOES) == []
    # O registro diz qual aula ficou pela metade e por quê, só com números (o relatório da manhã, pedido de 23/11).
    assert _registro_das_aulas() == [("pela metade", "curso 4, aula 2: o robô pediu o celular")]


def test_o_robo_que_pede_o_celular_no_caminho_pela_lista_tem_o_celular_logo(noite_do_curso, monkeypatch):
    # A lista do curso de centenas de aulas leva minutos: a cada tela dela, a noite renova o sinal ao robô e para na
    # hora em que ele pede o celular.
    _lista_no_mapa(4)
    sinais = []
    monkeypatch.setattr(cursos_robo, "anotar_o_sinal", lambda agora=None: sinais.append(1))
    monkeypatch.setattr(cursos_robo, "pediram_o_celular", lambda inicio: len(sinais) > 2)
    site = _curso_da_noite()
    resumo = noite_do_curso(site, AjudanteNaHora())
    assert resumo.endswith("parou: o robô pediu o celular") and noite_do_curso.gravadas == []
    assert site.tocadas == [] and cursos_robo.proxima_aula() == (4, 1)


def test_a_noite_guarda_tambem_a_pagina_de_cada_videoaula(noite_do_curso):
    # Pedidos do Rafael de 23/11 (08:44 e 09:12): tudo o que está nas aulas vai ao Claude, também o texto e os links
    # embaixo de cada videoaula. Gravada a aula inteira, a página dela é guardada à parte, com o celular mudo e sem
    # tocar em nada, e a noite segue para a seguinte pelo Próximo.
    aulas = [aula for aula in AULAS_DA_LISTA if aula is not AULA_DE_DOCUMENTO]
    _lista_no_mapa(4, aulas, [("Comece por aqui", 3)], retomada=2)
    site = _curso_da_noite(aulas, [("Comece por aqui", 3)], retomada=2, texto_na_videoaula=True)
    resumo = noite_do_curso(site, AjudanteNaHora())
    assert resumo.startswith("3 aula(s) gravada(s), 3 guardada(s), 0 pela metade, 0 sem vídeo guardada(s)")
    paginas = sorted(os.listdir(cursos_robo.PASTA_DAS_AULAS))
    assert [nome[-8:] for nome in paginas] == ["c04-a001", "c04-a002", "c04-a003"]
    for nome in paginas:
        with open(os.path.join(cursos_robo.PASTA_DAS_AULAS, nome, "aula.json"), encoding="utf-8") as arquivo:
            info = json.load(arquivo)
        assert (info["tipo"], info["linhas"], info["links"], info["documento"]) == (
            cursos_robo.PAGINA_DA_VIDEOAULA, 2, 1, None)
    assert site.volumes_das_telas == [0, 0, 0]
    assert _registro_das_aulas() == [
        ("página guardada", f"curso 4, aula {numero}: 1 tela(s), 2 linha(s), 1 link(s), sem documento")
        for numero in (1, 2, 3)]


def test_o_robo_que_pede_o_celular_na_pagina_da_videoaula_para_a_noite_com_a_aula_gravada(noite_do_curso, monkeypatch):
    # Pedido o celular enquanto a página é lida, a noite para, e a aula gravada inteira vale (a página pela metade sai).
    _lista_no_mapa(4)
    ajudante, gravou = AjudanteNaHora(), []
    monkeypatch.setattr(cursos_robo, "pediram_o_celular", lambda inicio: bool(gravou))

    def fim_da(nome):
        gravou.append(nome)
        return True, "o vídeo parou"
    resumo = noite_do_curso(_curso_da_noite(texto_na_videoaula=True), ajudante, fim_da=fim_da)
    assert resumo == ("1 aula(s) gravada(s), 1 guardada(s), 0 pela metade, 0 sem vídeo guardada(s); parou: o robô "
                      "pediu o celular")
    assert ajudante.lidas == [(4, 1, "o vídeo parou")] and cursos_robo.proxima_aula() == (4, 2)
    assert os.listdir(cursos_robo.PASTA_DAS_AULAS) == []


@pytest.mark.parametrize("autoplay, fim", [(False, "o vídeo parou"), (True, "outro vídeo começou")])
def test_o_site_que_passa_sozinho_para_a_seguinte_nao_faz_a_noite_pular_uma_aula(noite_do_curso, autoplay, fim):
    # Na noite de 24/11/2026, o site passou sozinho para a aula seguinte no fim de quase todas as videoaulas. A página
    # da aula gravada volta pela lista (muda e pausada) e é guardada; a seguinte vem pelo Próximo dela, cada aula com o
    # número dela, e nenhuma fica de fora.
    _lista_no_mapa(4)
    site = _curso_da_noite(texto_na_videoaula=True, autoplay=autoplay, passa_no_fim=True)
    resumo = noite_do_curso(site, AjudanteNaHora(), fim_da=lambda nome: (True, fim))
    assert resumo == ("3 aula(s) gravada(s), 3 guardada(s), 0 pela metade, 1 sem vídeo guardada(s); parou: nenhuma "
                      "aula por gravar")
    assert noite_do_curso.gravadas == ["Aula um", "Aula dois", "Aula quatro"]
    linhas = _registro_das_aulas()
    assert [linha[0] for linha in linhas] == ["página guardada", "página guardada", "guardada sem vídeo",
                                              "página guardada"]
    assert [linha[1].split(":")[0] for linha in linhas] == [f"curso 4, aula {numero}" for numero in (1, 2, 3, 4)]
    # A 1ª e a 2ª voltam pela lista para guardar a página (a 4ª, a última, fica na tela); a página nunca recarrega.
    assert site.tocadas == [0, 0, 1] and site.recarregadas == 0


def test_a_pagina_que_nao_volta_pela_lista_nao_e_guardada_e_a_aula_gravada_vale(bm, monkeypatch, tmp_path):
    # A página de outra aula não é guardada como a da videoaula: sem voltar à aula gravada, o registro diz o porquê.
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_AULAS", str(tmp_path / "aulas"))
    _lista_no_mapa(4)
    site = _curso_da_noite(retomada=2, texto_na_videoaula=True)
    monkeypatch.setattr(cursos_robo, "_tocar_na_lista", lambda d, lista, numero, pausa, vigiar: (
        False, cursos_robo.SEM_A_AULA_NA_LISTA))
    assert cursos_robo._guardar_a_pagina_da_videoaula(site, 4, 2, lambda s: None, lambda: "") == ("", None)
    assert not os.path.exists(tmp_path / "aulas")
    assert _registro_das_aulas() == [
        ("página não guardada", f"curso 4, aula 2: {cursos_robo.SAIU_DA_AULA} (a aula não apareceu na lista)")]
    # Na aula certa, a mesma página é guardada; a videoaula sem nada embaixo do vídeo não vai ao registro.
    site._abrir(1)
    assert cursos_robo._guardar_a_pagina_da_videoaula(site, 4, 2, lambda s: None, lambda: "") == ("", (4, 2))
    (pasta,) = os.listdir(tmp_path / "aulas")
    assert pasta.endswith("-c04-a002")
    site.texto_na_videoaula = False
    assert cursos_robo._guardar_a_pagina_da_videoaula(site, 4, 2, lambda s: None, lambda: "") == ("", (4, 2))
    assert len(_registro_das_aulas()) == 2


def test_a_gravacao_preta_para_a_noite_e_a_aula_volta_a_ficar_por_gravar(noite_do_curso):
    # P288 3: preta ou muda, o player não deixa gravar, e a gravação para.
    _lista_no_mapa(4)
    resumo = noite_do_curso(_curso_da_noite(), AjudanteNaHora(problema_na=1))
    assert resumo.endswith("parou: a imagem saiu preta") and noite_do_curso.gravadas == ["Aula um"]
    assert cursos_robo.proxima_aula() == (4, 1)


def test_o_video_que_nao_toca_do_inicio_ao_fim_volta_numa_noite_seguinte(noite_do_curso):
    # Pedido do Rafael de 24/11/2026: nunca achar que viu a aula sem tê-la visto. O vídeo que começou adiantado (o site
    # lembra onde a pessoa parou, nas aulas que o Rafael viu à mão) não é falha do caminho: a noite segue, e a aula
    # volta numa noite seguinte. O que parou antes do fim da duração da lista conta como falha.
    _lista_no_mapa(4)

    def fim_da(nome):
        if nome == "Aula um":
            return False, f"{cursos_robo.NAO_DO_INICIO} (em 200 s de 300 s)"
        if nome == "Aula dois":
            return False, f"{cursos_robo.NAO_DO_INICIO} (em 90 s de 600 s)"
        return False, f"{cursos_robo.ANTES_DO_FIM} (em 60 s de 120 s)"
    resumo = noite_do_curso(_curso_da_noite(), AjudanteNaHora(), fim_da=fim_da)
    assert resumo.startswith("0 aula(s) gravada(s), 0 guardada(s), 3 pela metade, 1 sem vídeo guardada(s)")
    assert [linha for linha in _registro_das_aulas() if linha[0] == "pela metade"] == [
        ("pela metade", "curso 4, aula 1: o vídeo não começou do início (em 200 s de 300 s)"),
        ("pela metade", "curso 4, aula 2: o vídeo não começou do início (em 90 s de 600 s)"),
        ("pela metade", "curso 4, aula 4: o vídeo parou antes do fim (em 60 s de 120 s)")]
    assert cursos_robo.proxima_aula() == (4, 1) and os.listdir(cursos_robo.PASTA_DAS_GRAVACOES) == []


def test_a_pagina_de_outra_aula_com_o_video_tocando_nao_e_gravada_como_a_da_vez(noite_do_curso, monkeypatch):
    # A página que, com o vídeo já tocando, não é a da aula da vez (o Próximo dela não mostra a seguinte da lista) não
    # vira a gravação dessa aula: ela fica para a noite seguinte, e 2 seguidas param a noite.
    _lista_no_mapa(4)
    monkeypatch.setattr(cursos_robo, "na_aula", lambda d, posicao, numero, pausa: numero != 1 or d.aberta != 0)
    resumo = noite_do_curso(_curso_da_noite(), AjudanteNaHora())
    assert noite_do_curso.gravadas[:1] != ["Aula um"]
    assert ("pela metade", "curso 4, aula 1: a página não é a da aula da vez") in _registro_das_aulas()
    assert cursos_robo.proxima_aula() == (4, 1) and "parou" in resumo


def test_nenhuma_noite_gira_sem_fim(noite_do_curso, monkeypatch):
    _lista_no_mapa(4)
    monkeypatch.setattr(cursos_robo, "VOLTAS_DA_NOITE", 0)
    assert noite_do_curso(_curso_da_noite(), AjudanteNaHora()).endswith("parou: a noite passou de 0 voltas")


def test_a_pagina_que_ainda_carrega_nao_passa_por_a_ultima_aula():
    # O Próximo pode demorar a aparecer na página da aula: sem a conferência, a noite tomaria a aula pela última.
    carregando = SiteDoCurso(AULAS_DO_SITE, no_alto=True)
    carregando.sem_o_proximo = 2
    assert cursos_robo.passar_para_a_seguinte(carregando, **SEM_ESPERA) == ("com vídeo", "", "Aula dois")
    # Fora da página da aula (sem as abas), a falta do Próximo não é o fim do curso.
    fora = SiteDoCurso(AULAS_DO_SITE)
    fora.pagina = "documento"
    assert cursos_robo.passar_para_a_seguinte(fora, **SEM_ESPERA) == (None, "a página da aula não está na tela", "")


def test_a_ultima_aula_conferida_com_a_pagina_rolada_na_lista(bm):
    # A última aula do curso não tem o Próximo: tocada lá embaixo da lista, com as abas fora da tela, a página dela é
    # reconhecida pela lista à vista; sem página de aula nenhuma, não.
    _lista_no_mapa(4)
    site = _curso_da_noite(retomada=0)
    assert cursos_robo.abrir_pela_lista(site, 4, 4, **SEM_ESPERA) == (True, "")
    assert site.aberta == 3 and site.rolagem and cursos_robo.na_aula(site, 4, 4, lambda s: None)
    assert not cursos_robo._mostra_a_seguinte('<hierarchy rotation="0"></hierarchy>', "")


def test_a_pagina_sobe_ate_o_player_inteiro_sem_recarregar(bm):
    # A aula aberta pela lista fica com a página lá embaixo: ela sobe meia tela por vez até o player inteiro à vista
    # (o play do meio dele a meia altura do player do alto da página) e nunca é arrastada para baixo no alto.
    _lista_no_mapa(4)
    site = _curso_da_noite(retomada=0)
    assert cursos_robo.abrir_pela_lista(site, 4, 2, **SEM_ESPERA) == (True, "")
    assert site.rolagem > 0 and not cursos_robo.botao_do_play(site.dump_hierarchy())
    aula = cursos_robo.lista_do_curso(4)[1]
    assert cursos_robo.subir_ate_o_alto(site, aula, lambda s: None)
    assert site.rolagem == 0 and site.recarregadas == 0 and cursos_robo.botao_do_play(site.dump_hierarchy())
    # Já no alto, nada é arrastado.
    rolagens = len(site.rolagens)
    assert cursos_robo.subir_ate_o_alto(site, aula, lambda s: None) and len(site.rolagens) == rolagens
    # O play cortado no alto da tela ainda não é o alto; o player tocando (sem o play) para a subida ali.
    cortado = ('<hierarchy rotation="0"><node class="android.webkit.WebView" bounds="[0,267][1080,2394]">'
               '<node class="android.widget.ToggleButton" clickable="true" text="" content-desc="Tocar vídeo" '
               'bounds="[475,300][603,428]" /></node></hierarchy>')
    assert not cursos_robo.alto_da_aula(cortado, "Aula dois")
    tocando = cortado.replace('class="android.widget.ToggleButton" clickable="true" text="" content-desc="Tocar '
                              'vídeo"', 'class="android.widget.SeekBar" resource-id="plyr-seek-1" clickable="true" '
                              'text="" content-desc=""')
    assert cursos_robo.alto_da_aula(tocando, "Aula dois")
    # Na aula sem vídeo, o nome dela no alto basta; na videoaula, não.
    titulo = ('<hierarchy rotation="0"><node class="android.webkit.WebView" bounds="[0,267][1080,2394]">'
              '<node class="android.widget.TextView" text="Dia 01" bounds="[42,500][1000,560]" /></node></hierarchy>')
    assert cursos_robo.alto_da_aula(titulo, "Dia 01", com_video=False)
    assert not cursos_robo.alto_da_aula(titulo, "Dia 01", com_video=True)


@pytest.fixture
def teste_de_dia(bm, monkeypatch, tmp_path):
    """
    O passo curso:gravar:N[:K] de dia, com a gravação de mentira na ordem da de verdade: fim(site) diz como a aula
    acabou (com o arquivo gravado). Anota o máximo, a madrugada e a duração de cada gravação e o que foi lido de cada
    uma.
    """
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_GRAVACOES", str(tmp_path / "brutas"))
    monkeypatch.setattr(cursos_robo, "_madrugada_agora", lambda: False)
    gravacoes, lidas, casos = [], [], []
    monkeypatch.setattr(cursos_robo, "guardar_o_caso",
                        lambda d, motivo, resultado="", passo="": casos.append((motivo, resultado)), raising=False)

    def rodar(site, passo="gravar:4", fim=lambda site: (True, "o vídeo parou")):
        def gravar(d, alvo, destino, ir_para_a_aula, tocar, pausa=None, madrugada=None, maximo=None, duracao=None,
                   na_aula_certa=None, **_):
            gravacoes.append((maximo, madrugada(), duracao))
            d.gravando = True
            try:
                cursos_robo.subir_o_volume(d)
                tipo, porque = ir_para_a_aula(d)
                if not tipo:
                    return False, False, f"a aula não abriu ({porque})"
                if tipo == cursos_robo.SEM_VIDEO:
                    return True, False, tipo
                assert tocar(d) and na_aula_certa(d)
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
    rodar.gravacoes, rodar.lidas, rodar.casos, rodar.brutas = gravacoes, lidas, casos, tmp_path / "brutas"
    return rodar


def test_o_teste_de_dia_grava_uma_aula_da_lista_como_a_noite(teste_de_dia):
    # O teste de dia da gravação da noite: a 1ª aula do curso pela lista, com o curso aberto antes, mudo e sem o
    # gravador; a 2ª pelo Próximo da 1ª, que vem antes pela lista. A gravação tem no máximo 10 min, leva a duração da
    # lista e é lida como a aula 0 do curso 0; depois, o celular fica mudo até o explorar devolver o volume.
    _lista_no_mapa(4)
    site = _curso_da_noite(volume=6)
    assert teste_de_dia(site) == (
        True, "aula 1 do curso 4 gravada inteira (o vídeo parou): 95 s, som -21.4 LUFS, 230 palavra(s), 2 folha(s) de "
              "quadros, sem problema; para ler: cursos_robo.yml exportar")
    assert teste_de_dia.gravacoes == [(cursos_robo.GRAVACAO_DO_TESTE, True, 300)]
    assert teste_de_dia.lidas == [(True, 0, 0, "o vídeo parou")] and not os.listdir(teste_de_dia.brutas)
    assert site.aberturas == [(0, False), (8, True)] and site.aberta == 0 and site.tocadas == [0]
    assert site.volume == 0 and cursos_robo.estado_da_noite()["volume_antes"] == 6
    site = _curso_da_noite(volume=6)
    assert teste_de_dia(site, "gravar:4:2")[1].startswith("aula 2 do curso 4 gravada inteira")
    assert site.aberturas == [(0, False), (0, False), (8, True)] and site.aberta == 1 and site.tocadas == [0]
    # O mapa não muda: a aula do teste não conta como gravada.
    assert cursos_robo.proxima_aula() == (4, 1)


def test_o_teste_de_dia_recusa_a_madrugada_o_curso_sem_lista_e_a_aula_sem_video(teste_de_dia, monkeypatch):
    site = _curso_da_noite()
    assert teste_de_dia(site) == (False, "o curso 4 ainda não tem a lista das aulas (curso:lista:4)")
    _lista_no_mapa(4)
    assert teste_de_dia(site, "gravar:4:9") == (False, "a lista do curso 4 tem 4 aula(s)")
    assert teste_de_dia(_curso_da_noite(), "gravar:4:3") == (False, "a aula 3 do curso 4 não tem vídeo")
    assert teste_de_dia.casos == [(cursos_robo.SEM_VIDEO, "teste da gravação")]
    monkeypatch.setattr(cursos_robo, "_madrugada_agora", lambda: True)
    assert teste_de_dia(site) == (False, "de madrugada, quem grava as aulas é a noite")
    assert not cursos_robo.curso_no_explorar(site, "gravar:9", **SEM_ESPERA)[0]
    assert not cursos_robo.curso_no_explorar(site, "gravar:9:1", **SEM_ESPERA)[0]


def test_o_robo_que_pede_o_celular_no_teste_de_dia_tem_o_celular_na_hora(teste_de_dia):
    # O robô da Shopee Vídeo tem a preferência também no teste: a gravação para e sai sem ser lida (a leitura da fala
    # seguraria o celular), e o celular fica mudo.
    _lista_no_mapa(4)
    site = _curso_da_noite(volume=6)
    assert teste_de_dia(site, fim=lambda d: (False, "o robô pediu o celular")) == (
        False, "a gravação parou (o robô pediu o celular) e saiu sem ser lida")
    assert teste_de_dia.lidas == [] and not os.listdir(teste_de_dia.brutas) and site.volume == 0
    # A aula que não começou a tocar também não tem o que ler, e a tela dela vai ao Claude.
    assert teste_de_dia(_curso_da_noite(), fim=lambda d: (False, cursos_robo.NAO_TOCOU)) == (
        False, "a gravação parou (a aula não começou a tocar) e saiu sem ser lida")
    assert teste_de_dia.lidas == [] and teste_de_dia.casos == [(cursos_robo.NAO_TOCOU, "teste da gravação")]


def test_o_ajudante_le_as_aulas_a_parte_e_as_que_ficaram_da_noite_anterior(bm, monkeypatch, tmp_path):
    brutas = tmp_path / "brutas"
    brutas.mkdir()
    monkeypatch.setattr(cursos_robo, "PASTA_DAS_GRAVACOES", str(brutas))
    _lista_no_mapa(4)
    for numero in (1, 2):
        cursos_robo.anotar_a_aula_gravada(4, numero)
    lidas = []

    def guardar(arquivo, posicao, numero, fim):
        lidas.append((posicao, numero))
        return None, {"problema": "o som saiu mudo" if numero == 2 else ""}

    # A gravação que ficou na fila de uma noite parada no meio (o .json ao lado) é lida na seguinte.
    sobra = brutas / "20261124-010000.mkv"
    sobra.write_bytes(b"aula")
    (brutas / "20261124-010000.mkv.json").write_text('{"posicao": 4, "numero": 1, "fim": "o vídeo parou"}')
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
    assert _registro_das_aulas() == [("guardada", "curso 4, aula 1"),
                                     ("não serviu", "curso 4, aula 2: o som saiu mudo")]

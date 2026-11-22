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

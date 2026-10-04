"""android_virtual.py: prepara só o que falta, adb nunca aberto para a internet, saída só com estados."""
import android_virtual as av


class Maquina:
    """Servidor falso: responde aos comandos e guarda o que foi pedido."""

    def __init__(self, docker=True, binder=True, conteiner="running", ligado=True):
        self.docker, self.binder, self.conteiner, self.ligado = docker, binder, conteiner, ligado
        self.comandos = []

    def rodar(self, *partes, timeout=120):
        self.comandos.append(partes)
        if "inspect" in partes:
            return (0, self.conteiner) if self.conteiner else (1, "")
        if "getprop" in partes and "sys.boot_completed" in partes:
            return (0, "1" if self.ligado else "")
        if "getprop" in partes:
            return (0, "13")
        if "pm" in partes:
            return (0, "")
        if "stats" in partes:
            return (0, "1.5GiB / 4GiB | CPU 3.00%")
        return (0, "")

    def pediu(self, *trecho):
        return [c for c in self.comandos if all(t in c for t in trecho)]


def _instalar(monkeypatch, maquina):
    monkeypatch.setattr(av, "_rodar", maquina.rodar)
    monkeypatch.setattr(av, "docker_instalado", lambda: maquina.docker)
    monkeypatch.setattr(av, "binder_carregado", lambda: maquina.binder)
    monkeypatch.setattr(av.shutil, "which", lambda nome: f"/usr/bin/{nome}" if maquina.docker else None)
    monkeypatch.setattr(av.time, "sleep", lambda s: None)


def test_preparar_do_zero_instala_carrega_e_cria_so_local(monkeypatch, capsys):
    m = Maquina(docker=False, binder=False, conteiner=None)
    _instalar(monkeypatch, m)

    def depois_de_instalar(*partes, timeout=120):
        if "install" in partes:
            m.docker = True
        if "run" in partes:
            m.conteiner = "running"
        return Maquina.rodar(m, *partes, timeout=timeout)

    monkeypatch.setattr(av, "_rodar", depois_de_instalar)
    assert av.preparar() is True
    assert m.pediu("apt-get", "install", "docker.io", "adb")
    assert m.pediu("modprobe", "binder_linux", "devices=binder,hwbinder,vndbinder")
    criar = m.pediu("docker", "run")[0]
    assert "127.0.0.1:5555:5555" in criar                      # adb só para a própria máquina
    assert not any(p.startswith("5555:") or p.startswith("0.0.0.0") for p in criar)
    assert "--memory" in criar and "--cpus" in criar and "unless-stopped" in criar
    assert "android: ligado" in capsys.readouterr().out


def test_preparar_de_novo_nao_reinstala_nem_recria(monkeypatch):
    m = Maquina()
    _instalar(monkeypatch, m)
    assert av.preparar() is True
    assert not m.pediu("apt-get") and not m.pediu("modprobe") and not m.pediu("docker", "run")


def test_conteiner_parado_e_religado(monkeypatch):
    m = Maquina(conteiner="exited")
    _instalar(monkeypatch, m)
    assert av.preparar() is True
    assert m.pediu("docker", "start", av.CONTEINER) and not m.pediu("docker", "run")


def test_falha_na_instalacao_para_e_mostra_so_o_codigo(monkeypatch, capsys):
    m = Maquina(docker=False, conteiner=None)
    _instalar(monkeypatch, m)
    monkeypatch.setattr(av, "_rodar", lambda *p, timeout=120: (100, "E: segredo do apt") if "install" in p else (0, ""))
    assert av.preparar() is False
    saida = capsys.readouterr().out
    assert "instalar docker e adb: falhou (código 100)" in saida and "segredo" not in saida


def test_estado_sem_docker(monkeypatch, capsys):
    m = Maquina(docker=False, binder=False, conteiner=None)
    _instalar(monkeypatch, m)
    av.mostrar_estado()
    saida = capsys.readouterr().out
    assert "docker: não instalado" in saida and f"contêiner {av.CONTEINER}: não existe" in saida
    assert not m.pediu("apt-get")                              # só mostrar nunca instala nada


def test_estado_com_android_ligado(monkeypatch, capsys):
    m = Maquina()
    _instalar(monkeypatch, m)
    av.mostrar_estado()
    saida = capsys.readouterr().out
    assert "android: ligado, versão 13" in saida and "app da Shopee: não instalado" in saida


def test_arquivos_de_trabalho_fora_da_pasta_que_o_docker_cria():
    # O Docker cria a pasta dos dados do Android (e a de cima) como root: o usuário
    # dos robôs não escreve ali, e o instalar-shopee caía com PermissionError.
    pasta_do_docker = av.os.path.dirname(av.PASTA_DADOS)
    for caminho in (av.PASTA_APP, av.ARQUIVO_TELA, av.LOG_TELA):
        assert not caminho.startswith(pasta_do_docker + av.os.sep)


def _zip(caminho, nomes):
    import zipfile
    with zipfile.ZipFile(caminho, "w") as z:
        for nome in nomes:
            z.writestr(nome, "x")
    return str(caminho)


def test_xapk_sobe_so_as_partes_do_arm64(tmp_path):
    arquivo = _zip(tmp_path / "s.zip", ["manifest.json", "icon.png", "com.shopee.br.apk",
                                        "config.arm64_v8a.apk", "config.armeabi_v7a.apk",
                                        "config.x86.apk", "config.x86_64.apk", "config.xhdpi.apk"])
    partes = av.partes_do_app(arquivo, str(tmp_path / "x"))
    assert [p.rsplit("/", 1)[1] for p in partes] == ["com.shopee.br.apk", "config.arm64_v8a.apk",
                                                    "config.xhdpi.apk"]


def test_apk_comum_vai_inteiro(tmp_path):
    arquivo = _zip(tmp_path / "s.zip", ["AndroidManifest.xml", "classes.dex"])
    assert av.partes_do_app(arquivo, str(tmp_path)) == [arquivo]


def test_instalar_shopee_baixa_instala_e_limpa(monkeypatch, tmp_path, capsys):
    m = Maquina()
    _instalar(monkeypatch, m)
    monkeypatch.setattr(av, "PASTA_APP", str(tmp_path / "app"))

    def rodar(*partes, timeout=120):
        if partes[0] == "curl":
            _zip(partes[partes.index("-o") + 1], ["base.apk", "config.arm64_v8a.apk"])
            return (0, "")
        if "dumpsys" in partes:
            return (0, "    versionName=3.40.21\n")
        return Maquina.rodar(m, *partes, timeout=timeout)

    monkeypatch.setattr(av, "_rodar", rodar)
    m.rodar = rodar
    assert av.instalar_shopee() is True
    saida = capsys.readouterr().out
    assert "instalar no Android: ok" in saida and "versão 3.40.21" in saida
    assert not (tmp_path / "app").exists()                     # o arquivo baixado não fica no servidor


def test_tela_abre_e_nao_mostra_o_link(monkeypatch, tmp_path, capsys):
    m = Maquina()
    _instalar(monkeypatch, m)
    monkeypatch.setattr(av, "ARQUIVO_TELA", str(tmp_path / "tela_estado"))
    monkeypatch.setattr(av, "LOG_TELA", str(tmp_path / "tela.log"))
    abertos = []

    def popen(comando, **kw):
        abertos.append((comando, kw))
        (tmp_path / "tela_estado").write_text("enviado")

    monkeypatch.setattr(av.subprocess, "Popen", popen)
    assert av.abrir_tela() is True
    comando, kw = abertos[0]
    assert comando[-1].endswith("tela_android.py") and kw["start_new_session"] is True
    saida = capsys.readouterr().out
    assert "o link foi no privado" in saida and "https://" not in saida


def test_tela_com_erro_conta_o_motivo(monkeypatch, tmp_path, capsys):
    m = Maquina()
    _instalar(monkeypatch, m)
    monkeypatch.setattr(av, "ARQUIVO_TELA", str(tmp_path / "tela_estado"))
    monkeypatch.setattr(av, "LOG_TELA", str(tmp_path / "tela.log"))
    monkeypatch.setattr(av.subprocess, "Popen",
                        lambda c, **k: (tmp_path / "tela_estado").write_text("erro: já existe uma tela aberta"))
    assert av.abrir_tela() is False
    assert "tela: erro: já existe uma tela aberta" in capsys.readouterr().out

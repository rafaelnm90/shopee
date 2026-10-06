"""Deploy: reinicia só os robôs cujo código mudou; na dúvida, todos."""
import servicos_afetados as sa

TODOS = sorted(sa.SERVICOS)


def test_so_documentacao_testes_e_workflows_nao_reinicia_ninguem():
    assert sa.servicos_afetados(["CLAUDE.md", "DECISOES.md", "tests/test_db.py", ".github/workflows/deploy.yml",
                                 ".claude/scripts/ver_video.sh", "inventario.py", "validar_deploy.py"]) == []


def test_modulo_de_um_robo_reinicia_so_ele():
    assert sa.servicos_afetados(["faxina_baixador.py"]) == ["divulgacao_canal_bot", "downloader_bot"]
    assert sa.servicos_afetados(["painel_notas.py"]) == ["bot_mestre_bot"]
    assert sa.servicos_afetados(["servicos_linux/downloader_bot.service"]) == ["downloader_bot"]


def test_modulo_que_todos_usam_reinicia_todos():
    assert sa.servicos_afetados(["db.py"]) == TODOS
    assert sa.servicos_afetados(["README.md", "requirements.txt"]) == TODOS


def test_na_duvida_reinicia_todos():
    assert sa.servicos_afetados(["fonte_nova.ttf"]) == TODOS
    assert sa.servicos_afetados(["servicos_linux/robo_novo.service"]) == TODOS
    assert sa.main("abc123", "abc123") == TODOS          # deploy rodado de novo à mão
    assert sa.main("commit-que-nao-existe", "HEAD") == TODOS


def test_so_comentario_ou_docstring_nao_e_codigo():
    original = 'def f(x):\n    """Soma um."""\n    return x + 1  # simples\n'
    so_texto = '"""Módulo."""\n\ndef f(x):\n    """Soma um ao número."""\n\n    # outro comentário\n    return x + 1\n'
    assert sa.codigo_sem_comentarios(original) == sa.codigo_sem_comentarios(so_texto)
    assert sa.codigo_sem_comentarios(original) != sa.codigo_sem_comentarios(original.replace("+ 1", "+ 2"))
    # Docstring que vira o único conteúdo da função continua sendo código válido.
    assert sa.codigo_sem_comentarios('def g():\n    """Nada."""\n') == sa.codigo_sem_comentarios("def g():\n    pass\n")


def test_commit_so_de_comentario_nao_reinicia(tmp_path):
    import subprocess

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "teste@exemplo.com")
    git("config", "user.name", "Teste")
    (tmp_path / "util.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "a")
    (tmp_path / "util.py").write_text("def f():\n    # comentário novo\n    return 1\n", encoding="utf-8")
    git("commit", "-qam", "b")
    (tmp_path / "util.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    git("commit", "-qam", "c")
    assert sa.so_comentarios_mudaram("util.py", "HEAD~2", "HEAD~1", pasta=str(tmp_path))
    assert not sa.so_comentarios_mudaram("util.py", "HEAD~1", "HEAD", pasta=str(tmp_path))
    assert not sa.so_comentarios_mudaram("sumiu.py", "HEAD~1", "HEAD", pasta=str(tmp_path))
    assert not sa.so_comentarios_mudaram("README.md", "HEAD~1", "HEAD", pasta=str(tmp_path))

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

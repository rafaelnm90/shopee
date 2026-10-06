"""
Quais robôs o deploy precisa reiniciar, pelos arquivos que mudaram entre o
commit que estava no servidor e o novo. Usado pelo deploy.yml:

    python3 servicos_afetados.py COMMIT_ANTIGO COMMIT_NOVO

Imprime os serviços, um por linha. Reinicia só quem roda código que mudou: o
arquivo do robô e todo módulo do projeto que ele importa, direta ou
indiretamente (inclusive import dentro de função). Mudança só em documentação,
testes, workflows ou ferramentas que nenhum robô importa não reinicia ninguém:
cada reinício derruba os painéis abertos e refaz a grade do dia.

Um .py que mudou só em comentários ou docstrings também não reinicia ninguém.
Na dúvida, todos: requirements.txt mudou, o mesmo commit de novo (deploy
rodado outra vez à mão), git falhou ou arquivo que não se encaixa nas regras.
"""
import ast
import functools
import os
import subprocess
import sys

PASTA = os.path.dirname(os.path.abspath(__file__))

SERVICOS = {
    "bot_mestre_bot": "bot_mestre.py",
    "divulgacao_canal_bot": "divulgacao_canal.py",
    "motor_userbot_bot": "motor_userbot.py",
    "espelhador_videos_autorais_bot": "espelhador_videos_autorais.py",
    "downloader_bot": "downloader_bot.py",
}

# Não rodam dentro de robô nenhum.
PASTAS_SEM_EFEITO = ("tests/", ".github/", ".claude/")
ARQUIVOS_SEM_EFEITO = {".gitignore", "servicos_linux/instalar_servicos.sh"}


@functools.lru_cache(maxsize=None)
def _importados(caminho):
    """Nomes de primeiro nível que o arquivo importa (o bot_mestre leva ~0,5 s para ler)."""
    with open(caminho, encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and not no.level:
            nomes.add(no.module.split(".")[0])
    return frozenset(nomes)


def modulos_do_robo(arquivo, pasta=PASTA):
    """Arquivos .py do projeto que o robô carrega: ele mesmo e tudo que importa."""
    locais = {nome[:-3] for nome in os.listdir(pasta) if nome.endswith(".py")}
    vistos, pendentes = set(), [arquivo]
    while pendentes:
        atual = pendentes.pop()
        if atual in vistos:
            continue
        vistos.add(atual)
        pendentes += [nome + ".py" for nome in _importados(os.path.join(pasta, atual)) if nome in locais]
    return vistos


def servicos_afetados(mudados, pasta=PASTA):
    """Serviços a reiniciar para a lista de arquivos mudados (caminhos do git)."""
    todos = sorted(SERVICOS)
    modulos = {servico: modulos_do_robo(arquivo, pasta) for servico, arquivo in SERVICOS.items()}
    afetados = set()
    for caminho in mudados:
        if caminho == "requirements.txt":
            return todos
        if caminho.startswith(PASTAS_SEM_EFEITO) or caminho.endswith(".md") or caminho in ARQUIVOS_SEM_EFEITO:
            continue
        if caminho.startswith("servicos_linux/") and caminho.endswith(".service"):
            servico = os.path.basename(caminho)[:-len(".service")]
            if servico in SERVICOS:
                afetados.add(servico)
                continue
            return todos
        if "/" not in caminho and caminho.endswith(".py"):
            # .py da raiz que nenhum robô importa é ferramenta (inventario, validar_deploy).
            afetados |= {servico for servico, mods in modulos.items() if caminho in mods}
            continue
        return todos
    return sorted(afetados)


def codigo_sem_comentarios(texto):
    """
    O código do arquivo sem comentários, docstrings, linhas em branco e posição das
    linhas (ast.dump não guarda nada disso): dois textos com o mesmo resultado rodam igual.
    """
    arvore = ast.parse(texto)
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if (isinstance(no, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and corpo
                and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant)
                and isinstance(corpo[0].value.value, str)):
            no.body = corpo[1:] or [ast.Pass()]
    return ast.dump(arvore)


def so_comentarios_mudaram(caminho, antigo, novo, pasta=PASTA):
    """True se o .py mudou só em comentários ou docstrings entre os dois commits."""
    if not caminho.endswith(".py"):
        return False
    try:
        textos = [subprocess.run(["git", "show", f"{commit}:{caminho}"], cwd=pasta, capture_output=True,
                                 text=True, timeout=30, check=True).stdout for commit in (antigo, novo)]
        return codigo_sem_comentarios(textos[0]) == codigo_sem_comentarios(textos[1])
    except Exception:
        return False


def main(antigo, novo):
    if antigo == novo:
        return sorted(SERVICOS)
    try:
        r = subprocess.run(["git", "diff", "--name-only", antigo, novo], cwd=PASTA,
                           capture_output=True, text=True, timeout=30, check=True)
        mudados = [linha for linha in r.stdout.splitlines() if linha.strip()]
        # Comentário não muda o que o robô faz: reiniciar por ele só derrubaria os painéis.
        return servicos_afetados([c for c in mudados if not so_comentarios_mudaram(c, antigo, novo)])
    except Exception:
        return sorted(SERVICOS)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("\n".join(sorted(SERVICOS)))
    else:
        print("\n".join(main(sys.argv[1], sys.argv[2])))

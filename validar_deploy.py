#!/usr/bin/env python3
"""
🛡️ VALIDADOR DE DEPLOY — Shopee Video Bot
Roda antes de reiniciar os serviços. Pega os erros que o 'ast.parse' sozinho não pega.
Uso:  python3 validar_deploy.py [arquivo1.py arquivo2.py ...]
Sem argumentos, valida todos os .py da pasta atual.
Código de saída: 0 = liberado para deploy | 1 = NÃO reinicie
"""
import ast, sys, os
from collections import Counter

ERROS, AVISOS = [], []
FONTES = {}   # guarda o conteúdo dos arquivos para mostrar o trecho do erro

def erro(arq, linha, msg): ERROS.append((arq, linha, msg))
def aviso(arq, linha, msg): AVISOS.append((arq, linha, msg))

def mostrar_trecho(arq, linha, margem=4):
    """Imprime o código em volta do erro, já numerado e com a linha marcada."""
    linhas = FONTES.get(arq, [])
    if not linhas or not linha:
        return ""
    ini = max(0, linha - margem - 1)
    fim = min(len(linhas), linha + margem)
    saida = []
    for i in range(ini, fim):
        marca = ">>>" if (i + 1) == linha else "   "
        saida.append(f"     {marca} {i+1:>6} | {linhas[i]}")
    return "\n".join(saida)

PRIMEIRO_PARAM_OK = {"message", "callback", "event", "query", "msg", "callback_query"}

def eh_decorator_handler(dec):
    txt = ast.unparse(dec)
    return txt.startswith(("dp.message", "dp.callback_query", "dp.edited_message",
                           "router.message", "router.callback_query", "client.on"))

def validar(caminho):
    fonte = open(caminho, encoding="utf-8").read()
    arq = os.path.basename(caminho)
    FONTES[arq] = fonte.split("\n")

    # 1) SINTAXE
    try:
        arvore = ast.parse(fonte)
    except (SyntaxError, IndentationError) as e:
        erro(arq, e.lineno, f"{type(e).__name__}: {e.msg}")
        return

    linhas = fonte.split("\n")

    # 2) DECORATOR COM COMENTÁRIO GRUDADO  (bug do 'Disparar Repost Autoral')
    for i, l in enumerate(linhas, 1):
        s = l.strip()
        if s.startswith("@") and ")#" in s.replace(") #", ")#"):
            erro(arq, i, "decorator com comentário grudado no fim da linha — pode ter engolido código")

    # 3) FUNÇÕES DUPLICADAS no nível do módulo
    nomes = Counter()
    for n in arvore.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nomes[n.name] += 1
    for nome, qtd in nomes.items():
        if qtd > 1:
            aviso(arq, 0, f"função '{nome}' definida {qtd}x — a última sobrescreve as anteriores")

    # 4) HANDLER COM ASSINATURA ERRADA  (bug do 'criar_painel_submissao')
    for n in ast.walk(arvore):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.decorator_list:
            if any(eh_decorator_handler(d) for d in n.decorator_list):
                params = [a.arg for a in n.args.args]
                if not params:
                    erro(arq, n.lineno, f"'{n.name}' é handler mas não recebe nenhum parâmetro")
                elif params[0] not in PRIMEIRO_PARAM_OK:
                    erro(arq, n.lineno,
                         f"'{n.name}' está decorado como handler, mas o 1º parâmetro é '{params[0]}' "
                         f"— o decorator provavelmente está na função errada")

    # 5) DECORATOR IDÊNTICO REGISTRADO DUAS VEZES
    filtros = Counter()
    posicao = {}
    for n in ast.walk(arvore):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in n.decorator_list:
                if eh_decorator_handler(d):
                    # Compara o decorator INTEIRO: o mesmo texto em estados diferentes é legítimo
                    txt = ast.unparse(d)
                    if "F.text" in txt or "F.data" in txt:
                        filtros[txt] += 1
                        posicao.setdefault(txt, n.lineno)
    for chave, qtd in filtros.items():
        if qtd > 1:
            resumo = chave if len(chave) < 90 else chave[:87] + "..."
            erro(arq, posicao[chave], f"decorator idêntico registrado {qtd}x — só o primeiro responde:\n       {resumo}")

    # 6) CHAMADAS COM ARGUMENTOS DE MENOS
    assinaturas = {}
    for n in ast.walk(arvore):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            p = [a.arg for a in n.args.args]
            obrig = p[:len(p) - len(n.args.defaults)]
            tem_decorator = bool(n.decorator_list)
            assinaturas[n.name] = (len(obrig), obrig, tem_decorator, bool(n.args.vararg or n.args.kwarg))
    for n in ast.walk(arvore):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in assinaturas:
            n_obrig, nomes_obrig, tem_dec, flexivel = assinaturas[n.func.id]
            if tem_dec or flexivel:
                continue
            informados = len(n.args) + len([k for k in n.keywords if k.arg in nomes_obrig])
            if informados < n_obrig:
                erro(arq, n.lineno,
                     f"chamada a '{n.func.id}' com {informados} argumento(s), mas exige {n_obrig} ({', '.join(nomes_obrig)})")

if __name__ == "__main__":
    alvos = sys.argv[1:] or [f for f in os.listdir(".") if f.endswith(".py")]
    alvos = [a for a in alvos if os.path.exists(a)]
    print(f"🛡️  Validando {len(alvos)} arquivo(s)...\n")
    for a in alvos:
        validar(a)
    if AVISOS:
        print("─" * 70)
        print("AVISOS (não bloqueiam o deploy):")
        for arq, linha, msg in AVISOS:
            print(f"  ⚠️  {arq}:{linha} — {msg}")
        print()

    if ERROS:
        print("=" * 70)
        print(f"🛑 {len(ERROS)} ERRO(S) ENCONTRADO(S) — NÃO reinicie os serviços")
        print("=" * 70)
        for i, (arq, linha, msg) in enumerate(ERROS, 1):
            print(f"\n[ERRO {i}/{len(ERROS)}]  {arq}  linha {linha}")
            print(f"  ❌ {msg}")
            trecho = mostrar_trecho(arq, linha)
            if trecho:
                print("\n     ── código nessa região ──")
                print(trecho)
        print("\n" + "=" * 70)
        print("👉 Copie TUDO acima e envie para análise.")
        print("=" * 70)
        sys.exit(1)
    print("✅ Tudo certo. Liberado para reiniciar.")
    sys.exit(0)

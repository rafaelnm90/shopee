"""
🔍 SIMULADOR DE REAJUSTE DE FILA — não grava nada, só mostra o que aconteceria.

Serve para conferir os números ANTES de a redistribuição virar botão no painel.
Responde: se eu mudar a quantidade diária para N, quantos vídeos são reagendados,
quantos são descartados, e como fica cada dia.

Uso:
    python3 simular_reajuste.py autorais 2
    python3 simular_reajuste.py publico 3

Regras simuladas (as mesmas combinadas):
  • o excedente de cada dia é SORTEADO, não escolhido por ordem de chegada;
  • quem sobra é empurrado para o dia seguinte, em cascata;
  • só é descartado o que passar de 7 dias além da data-alvo ORIGINAL.
"""
import json
import random
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta

BANCO = "banco_dados.db"
FOLGA_DIAS = 7

TABELAS = {
    "autorais": ("fila_autorais", "autorais_config", "limite_videos"),
    "publico": ("fila_publico", "submissao_config", "repost_limite"),
}


def ler_config(chave):
    conexao = sqlite3.connect(BANCO, timeout=30.0)
    try:
        linha = conexao.execute(
            "SELECT valor FROM configuracoes WHERE chave=?", (chave,)
        ).fetchone()
        return json.loads(linha[0]) if linha else {}
    finally:
        conexao.close()


def ler_pendentes(tabela):
    conexao = sqlite3.connect(BANCO, timeout=30.0)
    conexao.row_factory = sqlite3.Row
    try:
        return [
            dict(l)
            for l in conexao.execute(
                f"SELECT * FROM {tabela} WHERE processado = 0"
            ).fetchall()
        ]
    finally:
        conexao.close()


def simular(itens, limite_por_dia):
    """Roda a cascata em memória. Devolve (movidos, descartados, mapa_final)."""
    por_dia = defaultdict(list)
    for item in itens:
        alvo = (item.get("data_alvo") or "")[:10]
        if alvo:
            item["_alvo_original"] = alvo
            por_dia[alvo].append(item)

    movidos, descartados = [], []

    for dia in sorted(por_dia.keys()):
        # o dia pode ter engordado com o excedente do dia anterior
        while len(por_dia[dia]) > limite_por_dia:
            excedente = random.sample(
                por_dia[dia], len(por_dia[dia]) - limite_por_dia
            )
            for item in excedente:
                por_dia[dia].remove(item)

                proximo = (
                    datetime.strptime(dia, "%Y-%m-%d") + timedelta(days=1)
                ).strftime("%Y-%m-%d")
                original = item["_alvo_original"]
                atraso = (
                    datetime.strptime(proximo, "%Y-%m-%d")
                    - datetime.strptime(original, "%Y-%m-%d")
                ).days

                if atraso > FOLGA_DIAS:
                    item["_motivo"] = f"passaria de {atraso} dias além do alvo {original}"
                    item["_destino_final"] = "descartado"
                else:
                    item["_novo_alvo"] = proximo
                    item["_destino_final"] = "movido"
                    por_dia[proximo].append(item)
            break  # o novo excedente do dia seguinte é tratado na volta dele

    # 🧮 Um item pode ser empurrado várias vezes antes de parar (ou de ser descartado).
    # Contar cada empurrão daria número inflado e soma negativa em "mantidos", então a
    # classificação é feita no fim, pelo estado FINAL de cada item.
    descartados = [i for i in itens if i.get("_destino_final") == "descartado"]
    movidos = [i for i in itens if i.get("_destino_final") == "movido"]

    return movidos, descartados, por_dia


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return

    fila = sys.argv[1].lower()
    if fila not in TABELAS:
        print(f"Fila desconhecida: {fila}. Use 'autorais' ou 'publico'.")
        return

    novo_limite = int(sys.argv[2])
    tabela, chave_cfg, campo_limite = TABELAS[fila]

    cfg = ler_config(chave_cfg)
    limite_atual = cfg.get(campo_limite, "?")
    itens = ler_pendentes(tabela)

    print(f"\n{'=' * 62}")
    print(f"  SIMULAÇÃO — fila {fila.upper()} (nada será gravado)")
    print(f"{'=' * 62}")
    print(f"  limite atual : {limite_atual} por dia")
    print(f"  novo limite  : {novo_limite} por dia")
    print(f"  pendentes    : {len(itens)}")
    print(f"  folga        : {FOLGA_DIAS} dias além da data-alvo\n")

    if not itens:
        print("  Fila vazia, nada a redistribuir.\n")
        return

    antes = defaultdict(int)
    for item in itens:
        antes[(item.get("data_alvo") or "")[:10]] += 1

    movidos, descartados, depois = simular(itens, novo_limite)

    print(f"  ➡️  reagendados : {len(movidos)}")
    print(f"  🗑️  descartados : {len(descartados)}")
    print(f"  ✅ mantidos    : {len(itens) - len(movidos) - len(descartados)}\n")

    print(f"  {'dia':<12} {'antes':>6} {'depois':>7}")
    print(f"  {'-' * 12} {'-' * 6} {'-' * 7}")
    dias = sorted(set(list(antes.keys()) + list(depois.keys())))
    for dia in dias[:20]:
        if dia:
            print(f"  {dia:<12} {antes.get(dia, 0):>6} {len(depois.get(dia, [])):>7}")
    if len(dias) > 20:
        print(f"  ... e mais {len(dias) - 20} dia(s)")

    if descartados:
        print(f"\n  🗑️  Exemplos do que seria descartado:")
        for item in descartados[:5]:
            print(f"     {item.get('id_unico')}  →  {item.get('_motivo')}")

    print(f"\n{'=' * 62}")
    print("  Nada foi gravado. Isto é só a prévia.\n")


if __name__ == "__main__":
    main()

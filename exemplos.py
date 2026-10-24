"""
Os exemplos das perguntas de configuração dos painéis (o "ex.: 8-12") com o que está
valendo agora, não um número fixo. Pedido do Rafael: DECISOES.md, Código e manutenção.

Cada exemplo tem um nome. Quando o valor de agora é daquele jeito (a faixa 8-12 na
pergunta da Faixa), ele é o exemplo. Quando é de outro jeito (está em Faixa e a pergunta
é do Fixo, ou o horário está em Dia Todo), vale o último daquele jeito que o Rafael
mandou; se ele nunca mandou, o exemplo padrão de cada pergunta. Os últimos ficam na
chave `exemplos_dos_paineis` de configuracoes.

Usado pelo bot_mestre e pelos painéis em arquivo próprio (painel_shopee_video,
painel_espelhos).
"""
import db

CHAVE = "exemplos_dos_paineis"


def lembrar(nome, valor):
    """Guarda o último valor que o Rafael mandou para o exemplo `nome`."""
    db.atualizar_config(CHAVE, lambda dados: dados.update({nome: str(valor)}))


def exemplo(nome, padrao, atual=None):
    """O valor de agora; sem ele, o último que o Rafael mandou; nunca mandou, o padrão."""
    if atual not in (None, ""):
        return str(atual)
    return str(db.ler_config(CHAVE, {}).get(nome) or padrao)


def _em_faixa(piso, topo):
    return piso is not None and topo is not None and int(topo) > int(piso)


def faixa_e_fixo(nome, cota, faixa_padrao, fixo_padrao):
    """
    (exemplo da Faixa, exemplo do Fixo) de uma quantidade por dia que hoje está em
    cota = (piso, topo): o de agora vale para o jeito dele, o outro jeito mostra o último
    mandado.
    """
    piso, topo = cota
    em_faixa = _em_faixa(piso, topo)
    faixa_agora = f"{int(piso)}-{int(topo)}" if em_faixa else None
    fixo_agora = int(piso) if not em_faixa and piso else None
    return (exemplo(f"{nome}_faixa", faixa_padrao, faixa_agora),
            exemplo(f"{nome}_fixo", fixo_padrao, fixo_agora))


def lembrar_faixa(nome, piso, topo):
    """Guarda a quantidade por dia que o Rafael mandou, no jeito dela (Faixa ou Fixo)."""
    if _em_faixa(piso, topo):
        lembrar(f"{nome}_faixa", f"{int(piso)}-{int(topo)}")
    else:
        lembrar(f"{nome}_fixo", int(piso))


def janela(nome, inicio, fim, padrao):
    """O exemplo de horário (início-fim): o de agora; em Dia Todo, o último horário mandado."""
    agora = None if inicio is None or fim is None or (int(inicio), int(fim)) == (0, 24) else f"{int(inicio)}-{int(fim)}"
    return exemplo(f"{nome}_janela", padrao, agora)


def lembrar_janela(nome, inicio, fim):
    """Dia Todo não vira exemplo: ele tem botão próprio."""
    if (int(inicio), int(fim)) != (0, 24):
        lembrar(f"{nome}_janela", f"{int(inicio)}-{int(fim)}")


def partes_da_faixa(faixa):
    """"8-12" → (8, 12), para a frase "cada dia sorteia um número entre 8 e 12"."""
    piso, topo = faixa.split("-")
    return int(piso), int(topo)


def media(faixa):
    """A média da faixa como o Rafael lê: "8-12" → "10", "5-8" → "6,5"."""
    piso, topo = partes_da_faixa(faixa)
    meio = (piso + topo) / 2
    return str(int(meio)) if meio == int(meio) else f"{meio:.1f}".replace(".", ",")

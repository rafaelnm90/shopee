"""
A fila do Espelhador de canais, no banco (chave CHAVE da tabela configuracoes), no
mesmo formato do arquivo fila_espelhador.json que ela substitui: {"fila": [itens]}.

Quem usa: o motor_userbot (a captura acrescenta, o laço de disparo agenda e publica),
o painel_espelhos (renomear rota, reagendar), o bot_mestre (relatório da fila, limpar
filas, faxina dos temporários) e o inventario.

Toda gravação passa por atualizar(), que lê e grava numa transação só. Com o arquivo,
um robô gravava a fila inteira por cima do outro: o vídeo capturado durante um
disparo, ou a mudança feita pelo painel nesse meio tempo, sumia.
(DECISOES.md, Código e manutenção)
"""
import json
import logging
import os

import db

CHAVE = "espelhador_fila"
ARQUIVO = "fila_espelhador.json"

logger = logging.getLogger("Fila_Espelhador")


def chave_do_item(item):
    """
    Identidade do item. O id sozinho não basta: o mesmo vídeo vai para cada rota com o
    mesmo id (e destino diferente), e vídeos de um álbum chegam no mesmo segundo (mesmo
    id, msg_id diferente). O nome da rota fica de fora porque o Rafael pode renomeá-la.
    """
    return (item.get("id"), str(item.get("destino")), str(item.get("msg_id")))


def _garantir_tabela():
    """A tabela configuracoes, caso este robô grave antes de o bot_mestre criá-la."""
    with db.conexao() as con:
        con.execute("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")


def _ler_arquivo():
    """A fila do arquivo antigo, ou None se não houver arquivo legível."""
    try:
        with open(ARQUIVO, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if isinstance(dados, list):
        return {"fila": dados}
    if isinstance(dados, dict):
        dados.setdefault("fila", [])
        return dados
    return None


def ler():
    """
    A fila ({"fila": [...]}). Até o motor_userbot passar o arquivo para o banco (ao
    ligar, depois do deploy), lê o arquivo. Sem nenhum dos dois, fila vazia.
    """
    dados = db.ler_config(CHAVE, {})
    if isinstance(dados, dict) and isinstance(dados.get("fila"), list):
        return dados
    return _ler_arquivo() or {"fila": []}


def atualizar(alterar):
    """
    Lê a fila, chama alterar(dados) e grava, tudo numa transação só (db.atualizar_config).
    alterar muda dados["fila"] no lugar e devolve o que quiser repassar a quem chamou.
    Se a fila ainda não está no banco, começa pelo arquivo, que então vira .bkp.
    Devolve o retorno de alterar, ou None se der erro.
    """
    veio_do_arquivo = []

    def _alterar(dados):
        if not isinstance(dados.get("fila"), list):
            dados.clear()
            dados.update(_ler_arquivo() or {"fila": []})
            veio_do_arquivo.append(os.path.exists(ARQUIVO))
        return ("gravou", alterar(dados))

    try:
        _garantir_tabela()
    except Exception as e:
        logger.error(f"❌ [Espelhador] Sem acesso ao banco para gravar a fila: {e}")
        return None
    retorno = db.atualizar_config(CHAVE, _alterar)
    if retorno is None:
        return None
    if any(veio_do_arquivo):
        _aposentar_arquivo()
    return retorno[1]


def _aposentar_arquivo(sufixo=".bkp"):
    try:
        os.replace(ARQUIVO, ARQUIVO + sufixo)
        logger.info(f"📦 [Espelhador] Fila passada do {ARQUIVO} para o banco ({ARQUIVO}{sufixo} guardado).")
    except OSError as e:
        logger.error(f"❌ [Espelhador] Fila já no banco, mas o {ARQUIVO} não virou {sufixo}: {e}")


def juntar(dados, de_fora):
    """
    Junta à fila do banco os itens de outra fila (de_fora): os que o banco não tem
    entram, e o que lá já saiu (processado) vale sobre a cópia pendente do banco,
    para o vídeo não ser postado de novo.
    """
    por_chave = {chave_do_item(i): n for n, i in enumerate(dados["fila"])}
    for item in de_fora.get("fila", []):
        n = por_chave.get(chave_do_item(item))
        if n is None:
            dados["fila"].append(item)
        elif item.get("processado") and not dados["fila"][n].get("processado"):
            dados["fila"][n] = item


def passar_arquivo_para_o_banco():
    """
    Chamado pelo motor_userbot ao ligar, quando a versão anterior dele já parou. Passa o
    arquivo para o banco. Se a fila já está no banco e o arquivo reapareceu (gravado por
    uma versão velha durante o deploy), junta o que ele tem de novo e o aposenta.
    """
    if not os.path.exists(ARQUIVO):
        return
    _garantir_tabela()
    de_fora = _ler_arquivo()
    if de_fora is None:
        _aposentar_arquivo(".ilegivel.bkp")
        return

    def _juntar(dados):
        if isinstance(dados.get("fila"), list):
            juntar(dados, de_fora)
        else:
            dados.clear()
            dados.update(de_fora)

    if db.atualizar_config(CHAVE, lambda dados: (_juntar(dados), True)[1]):
        _aposentar_arquivo()


def fotografar(fila):
    """Como cada item estava na leitura, para gravar_mudancas saber o que mudou."""
    return {chave_do_item(i): json.dumps(i, sort_keys=True, ensure_ascii=False) for i in fila}


def gravar_mudancas(foto, restantes):
    """
    Grava o que mudou desde a leitura (foto) para quem leu a fila, mexeu nela por um
    tempo e ficou com restantes: o laço de disparo, que passa minutos publicando, ou o
    relatório da fila. Sobre a fila de agora:
    - item que chegou depois da leitura (captura nova) fica;
    - item que quem chamou mudou (agendou, publicou, renomeou) vai como ficou;
    - item que quem chamou tirou (teto do dia, histórico velho, rota excluída) sai;
    - item que quem chamou não mexeu fica como está agora (outro pode ter mudado);
    - item tirado por outro (limpar filas) não volta.
    """
    depois = {chave_do_item(i): i for i in restantes}

    def _alterar(dados):
        nova = []
        for atual in dados["fila"]:
            chave = chave_do_item(atual)
            if chave not in foto:
                nova.append(atual)
            elif chave in depois:
                do_ciclo = depois[chave]
                mudou = json.dumps(do_ciclo, sort_keys=True, ensure_ascii=False) != foto[chave]
                nova.append(do_ciclo if mudou else atual)
        dados["fila"] = nova

    return atualizar(_alterar)

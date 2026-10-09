"""
Vídeos que já foram para o Grupo Público, para o mesmo vídeo não ir de novo quando o
grupo de origem dos Autorais o posta outra vez. Usado pelo espelhador_videos_autorais
(sorteio do Público) e pelo bot_mestre (botão Disparar Repost Autoral).

O vídeo é reconhecido pelo arquivo do Telegram (doc_<id>, o mesmo quando é
encaminhado) e pelo SHA-256 do arquivo baixado (sha_<hash>, o mesmo quando é enviado
de novo igual). O mesmo produto com outro vídeo pode ir: é conteúdo novo.
Decisão do Rafael: DECISOES.md, Grupo Público e Achadinhos.
"""
import json
import logging
from datetime import datetime

import db
import videos

logger = logging.getLogger("Repetidos_Publico")


def chaves_do_video(doc_id, caminho):
    """As chaves que reconhecem o vídeo: o arquivo do Telegram e o SHA-256 do arquivo baixado."""
    chaves = [f"doc_{doc_id}"] if doc_id else []
    assinatura = videos.calcular_hash_video(caminho) if caminho else None
    if assinatura:
        chaves.append(f"sha_{assinatura}")
    return chaves


def chaves_da_coluna(texto):
    """As chaves gravadas na fila (JSON) de volta em lista; vazia se não houver."""
    try:
        chaves = json.loads(texto or "[]")
    except ValueError:
        return []
    return [str(c) for c in chaves if c] if isinstance(chaves, list) else []


def _garantir_tabela(con):
    con.execute("CREATE TABLE IF NOT EXISTS videos_no_publico "
                "(chave TEXT PRIMARY KEY, id_unico TEXT, data TEXT)")


def ja_foi(chaves):
    """
    True se alguma chave já foi (ou está na fila) para o Grupo Público. Erro no banco
    também dá True: na dúvida, o vídeo fica de fora em vez de arriscar repetir.
    """
    chaves = [c for c in chaves if c]
    if not chaves:
        return False
    try:
        with db.conexao() as con:
            _garantir_tabela(con)
            marcadores = ",".join("?" * len(chaves))
            achou = con.execute(f"SELECT 1 FROM videos_no_publico WHERE chave IN ({marcadores}) LIMIT 1",
                                chaves).fetchone()
        return achou is not None
    except Exception as e:
        logger.error(f"❌ [Repetidos] Erro ao consultar os vídeos do Grupo Público: {type(e).__name__}")
        return True


def registrar(chaves, id_unico):
    """Marca o vídeo (todas as chaves) como levado ao Grupo Público pelo item id_unico."""
    chaves = [c for c in chaves if c]
    if not chaves:
        return
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with db.conexao() as con:
            _garantir_tabela(con)
            for chave in chaves:
                con.execute("INSERT OR IGNORE INTO videos_no_publico (chave, id_unico, data) VALUES (?, ?, ?)",
                            (chave, str(id_unico), agora))
    except Exception as e:
        logger.error(f"❌ [Repetidos] Erro ao registrar vídeo do Grupo Público: {type(e).__name__}")


def liberar(id_unico):
    """
    Desfaz o registro de um item que saiu da fila do Público sem ser postado (a vaga
    foi tomada por outro vídeo no sorteio): esse vídeo nunca chegou ao grupo.
    """
    try:
        with db.conexao() as con:
            _garantir_tabela(con)
            con.execute("DELETE FROM videos_no_publico WHERE id_unico = ?", (str(id_unico),))
    except Exception as e:
        logger.error(f"❌ [Repetidos] Erro ao liberar vídeo do Grupo Público: {type(e).__name__}")

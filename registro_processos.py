"""
O registro de tudo o que os robôs fazem: cada processo (um pedido ao Baixador, uma
postagem, um envio) e como terminou. O checkup do dia (checkup.py) conta esse
registro para achar o que deu errado. Cada linha fica 3 dias no banco e depois
sai sozinha, para não acumular no servidor (pedido do Rafael: DECISOES.md,
Trabalho com o Claude).

Só rótulos e textos fixos do código (robô, processo, resultado, detalhe): nunca
link, nome de produto, texto de mensagem ou id de pessoa, porque o checkup
imprime o registro no log público do Actions. Números longos que escaparem
viram "#".

Uso: registro_processos.registrar("baixador", "pedido Shopee (vídeo)", "erro",
detalhe="a Shopee demorou demais para responder", ok=False). Nunca levanta erro:
o registro não pode derrubar o processo que ele anota.
"""
import logging
import re
from datetime import datetime, timedelta

import db
from fuso import fuso_horario

logger = logging.getLogger(__name__)

DIAS_DO_REGISTRO = 3
TAMANHO_DO_DETALHE = 120


def _criar_tabela(con):
    con.execute("CREATE TABLE IF NOT EXISTS registro_processos ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, momento TEXT, robo TEXT, processo TEXT, "
                "resultado TEXT, detalhe TEXT, ok INTEGER)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_registro_processos_momento ON registro_processos (momento)")


def _limpo(texto):
    return re.sub(r"-?\d{5,}", "#", str(texto or ""))[:TAMANHO_DO_DETALHE]


def registrar(robo, processo, resultado, detalhe="", ok=None, agora=None):
    """
    Anota um processo. ok: True deu certo, False deu errado, None nem um nem outro
    (ex.: o pedido parou na trava de canais, que é a regra funcionando).
    """
    agora = agora or datetime.now(fuso_horario)
    try:
        with db.conexao() as con:
            _criar_tabela(con)
            con.execute("INSERT INTO registro_processos (momento, robo, processo, resultado, detalhe, ok) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (agora.strftime("%Y-%m-%d %H:%M:%S"), robo, _limpo(processo), _limpo(resultado),
                         _limpo(detalhe), None if ok is None else int(bool(ok))))
            corte = (agora - timedelta(days=DIAS_DO_REGISTRO)).strftime("%Y-%m-%d %H:%M:%S")
            con.execute("DELETE FROM registro_processos WHERE momento < ?", (corte,))
    except Exception as e:
        logger.warning(f"⚠️ [Registro] Processo não entrou no registro: {type(e).__name__}")


def contagem(desde):
    """
    [(robo, processo, resultado, detalhe, ok, quantidade)] desde o momento
    ("AAAA-MM-DD HH:MM:SS"), o mais frequente primeiro dentro de cada robô.
    """
    try:
        with db.conexao() as con:
            _criar_tabela(con)
            return con.execute(
                "SELECT robo, processo, resultado, detalhe, ok, COUNT(*) FROM registro_processos "
                "WHERE momento >= ? GROUP BY 1, 2, 3, 4, 5 ORDER BY 1, 2, 6 DESC", (desde,)).fetchall()
    except Exception:
        return []

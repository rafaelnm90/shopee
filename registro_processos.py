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

origem (opcional) é de onde ou para onde foi o processo (o grupo vigiado, o alvo da
divulgação, o tópico): fica só como um apelido (os 8 primeiros caracteres do SHA-1),
para o checkup comparar o mesmo grupo ao longo do dia sem o id sair no log.
"""
import asyncio
import functools
import hashlib
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
                "resultado TEXT, detalhe TEXT, ok INTEGER, origem TEXT)")
    if "origem" not in {linha[1] for linha in con.execute("PRAGMA table_info(registro_processos)")}:
        con.execute("ALTER TABLE registro_processos ADD COLUMN origem TEXT")
    con.execute("CREATE INDEX IF NOT EXISTS idx_registro_processos_momento ON registro_processos (momento)")


def apelido(origem):
    """O apelido de um grupo, alvo ou tópico: o mesmo sempre, sem dizer qual é."""
    return hashlib.sha1(str(origem).encode()).hexdigest()[:8] if origem not in (None, "") else None


def _limpo(texto):
    return re.sub(r"-?\d{5,}", "#", str(texto or ""))[:TAMANHO_DO_DETALHE]


def registrar(robo, processo, resultado, detalhe="", ok=None, agora=None, origem=None):
    """
    Anota um processo. ok: True deu certo, False deu errado, None nem um nem outro
    (ex.: o pedido parou na trava de canais, que é a regra funcionando).
    """
    agora = agora or datetime.now(fuso_horario)
    try:
        with db.conexao() as con:
            _criar_tabela(con)
            con.execute("INSERT INTO registro_processos (momento, robo, processo, resultado, detalhe, ok, origem) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (agora.strftime("%Y-%m-%d %H:%M:%S"), robo, _limpo(processo), _limpo(resultado),
                         _limpo(detalhe), None if ok is None else int(bool(ok)), apelido(origem)))
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


def sequencia(robo, prefixo_do_processo, desde, resultado=None):
    """
    As linhas do robô cujo processo começa pelo prefixo, desde o momento, em ordem de
    tempo: [(momento, processo, resultado, detalhe, origem)]. Para o checkup medir o
    espaçamento e a ordem dos assuntos.
    """
    try:
        with db.conexao() as con:
            _criar_tabela(con)
            sql = ("SELECT momento, processo, resultado, detalhe, origem FROM registro_processos "
                   "WHERE robo = ? AND processo LIKE ? AND momento >= ?")
            parametros = [robo, prefixo_do_processo.replace("%", "") + "%", desde]
            if resultado is not None:
                sql += " AND resultado = ?"
                parametros.append(resultado)
            return con.execute(sql + " ORDER BY momento, id", parametros).fetchall()
    except Exception:
        return []


def anotar(robo, processo):
    """
    Decorador para os jobs de manutenção (rodam de hora em hora ou menos): cada execução
    fica no registro, como "concluído" ou "falhou" com o tipo do erro. O que o job trata
    sozinho aparece no log do robô, que o checkup lê por lugar do código.
    """
    def decorar(funcao):
        if asyncio.iscoroutinefunction(funcao):
            @functools.wraps(funcao)
            async def envolvida(*args, **kwargs):
                try:
                    resultado = await funcao(*args, **kwargs)
                except Exception as e:
                    registrar(robo, processo, "falhou", type(e).__name__, ok=False)
                    raise
                registrar(robo, processo, "concluído", ok=True)
                return resultado
            return envolvida

        @functools.wraps(funcao)
        def envolvida_sincrona(*args, **kwargs):
            try:
                resultado = funcao(*args, **kwargs)
            except Exception as e:
                registrar(robo, processo, "falhou", type(e).__name__, ok=False)
                raise
            registrar(robo, processo, "concluído", ok=True)
            return resultado
        return envolvida_sincrona
    return decorar

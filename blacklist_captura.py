# =============================================================================
# 🚫 LISTA NEGRA DE CAPTURA — blacklist_captura.py
# =============================================================================
#
# 📖 LEIA-ME PARA A IA (e para o Rafael daqui a seis meses)
#
# ─── O QUE ESTE ARQUIVO É ────────────────────────────────────────────────────
# Uma lista de autores cujas postagens o espelhador NUNCA deve capturar. Ele
# responde a uma pergunta só, e é chamado uma vez por mensagem que chega:
#
#       "Esta mensagem é de alguém que eu devo ignorar?"
#
# Ele não captura, não posta, não agenda. Só diz sim ou não.
#
# ─── POR QUE ELE PRECISOU EXISTIR ────────────────────────────────────────────
# ⚠️ ISTO AQUI É O MOTIVO REAL DESTE ARQUIVO. NÃO APAGUE ESTE BLOCO.
#
# Até então, a única proteção contra capturar as próprias postagens era o
# 'incoming=True' do Telethon mais o 'if event.out: return' no espelhador.
# Esses dois filtros olham para UMA coisa só: "esta mensagem foi enviada pela
# conta que está rodando ESTE userbot?".
#
# Isso funcionava quando uma conta só fazia tudo. Com o pool de contas
# (pool_contas.py), o espelho e a repostagem podem ser contas DIFERENTES — e aí
# a proteção se rompe:
#
#   • a conta da REPOSTAGEM devolve o vídeo ao grupo de origem no D+X
#   • para a conta do ESPELHO, essa mensagem é INCOMING (out=False)
#   • o espelho recaptura, republica no canal, reentra na fila
#   • no D+X seguinte, reposta de novo → laço infinito
#
# Não existe nenhum anti-loop por hash no espelhador_videos_autorais.py para
# segurar isso (procurei: hashlib está importado mas não é usado para dedupe).
# Ou seja: a lista negra não é um luxo, é o que impede o laço assim que as duas
# funções ficam em contas diferentes.
#
# ─── AS DUAS ORIGENS DE UMA ENTRADA ──────────────────────────────────────────
#   origem='pool'   → AUTOMÁTICA. Toda conta cadastrada no pool_contas entra
#                     aqui sozinha, inclusive as que você cadastrar no futuro.
#                     Você não precisa fazer nada. Não dá para remover pelo
#                     painel (se pudesse, você criaria o laço de novo sem
#                     perceber); some sozinha se a conta sair do pool.
#   origem='manual' → VOCÊ adicionou. Gente de fora que você não quer pegar.
#                     Pode remover quando quiser.
#
# ─── OS DOIS ESCOPOS ─────────────────────────────────────────────────────────
#   escopo='global'   → ignora essa pessoa em QUALQUER lugar que o espelhador
#                       escute (grupo dos autorais e canais de parceiros).
#                       É o escopo das suas contas do pool.
#   escopo='autorais' → ignora só dentro do grupo de origem dos Autorais.
#                       É o padrão de quem você adiciona na mão.
#
# ─── @USERNAME vs ID ─────────────────────────────────────────────────────────
# Você quase nunca tem o ID numérico de alguém, só o @. Então o fluxo é:
#
#   1. Você adiciona "@fulano".
#   2. O módulo TENTA resolver o @ para o ID numérico na hora, usando uma das
#      suas contas do pool (só funciona se essa conta consegue enxergar o
#      usuário — normalmente sim, se vocês estão no mesmo grupo).
#   3. Resolveu → guarda o ID. A checagem passa a ser por ID, que é instantânea
#      e à prova de troca de @.
#   4. Não resolveu → guarda só o @ e marca como pendente. A checagem ainda
#      funciona (compara o @ do autor), e o comando 'resolver' tenta de novo
#      depois.
#
# Guardar o ID importa porque @ muda: a pessoa troca o @ e escapa da lista. O
# ID não muda nunca.
#
# ─── COMO OS OUTROS ARQUIVOS USAM ────────────────────────────────────────────
#     import blacklist_captura
#
#     # no topo do handler, antes de qualquer trabalho:
#     if blacklist_captura.deve_ignorar(event.sender_id, contexto="global"):
#         return
#
#     # depois de confirmar que é o grupo dos autorais:
#     autor = await event.get_sender()
#     if blacklist_captura.deve_ignorar(getattr(autor, "id", None),
#                                       getattr(autor, "username", None)):
#         return
#
# ─── LINHA DE COMANDO ────────────────────────────────────────────────────────
#     python3 blacklist_captura.py listar
#     python3 blacklist_captura.py add @fulano          # escopo autorais
#     python3 blacklist_captura.py add @fulano global   # em todo lugar
#     python3 blacklist_captura.py del @fulano
#     python3 blacklist_captura.py sincronizar          # puxa as contas do pool
#     python3 blacklist_captura.py resolver             # resolve os @ pendentes
#     python3 blacklist_captura.py testar 123456789     # simula uma checagem
#
# ─── O QUE ESTE ARQUIVO NÃO FAZ ──────────────────────────────────────────────
#   • Não bloqueia ninguém no Telegram. Ele só faz o SEU robô ignorar. A pessoa
#     continua postando normalmente e nem fica sabendo.
#   • Não apaga nada que já foi capturado antes. Só vale daqui para frente.
#   • Não mexe em fila, em configuração nem em nenhuma tabela dos outros robôs.
#
# =============================================================================

EXIBIR_LOGS = True

import os
import sys
import time
import sqlite3
import logging
import asyncio
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

# 🕐 Trava de fuso centralizada, no mesmo padrão dos outros módulos.
try:
    from fuso import fuso_horario, configurar_logs
    logger = configurar_logs(__name__)
except Exception:  # pragma: no cover
    from zoneinfo import ZoneInfo
    fuso_horario = ZoneInfo("America/Sao_Paulo")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    logger = logging.getLogger(__name__)


DB_NAME = "banco_dados.db"

ESCOPO_GLOBAL = "global"
ESCOPO_AUTORAIS = "autorais"
ESCOPOS = (ESCOPO_GLOBAL, ESCOPO_AUTORAIS)

ORIGEM_POOL = "pool"
ORIGEM_MANUAL = "manual"

# Cache em memória. O handler do espelhador chama deve_ignorar() em TODA
# mensagem que chega; ir ao SQLite a cada uma é desperdício. 30 segundos é curto
# o bastante para uma mudança no painel valer quase na hora.
_CACHE = {"dados": None, "carregado_em": 0.0}
_CACHE_SEGUNDOS = 30
_TABELA_PRONTA = False


# =============================================================================
# 1. BANCO
# =============================================================================

def _obter_conexao():
    conexao = sqlite3.connect(DB_NAME, timeout=20.0)
    conexao.row_factory = sqlite3.Row
    return conexao


def inicializar_tabelas():
    """Cria a tabela da lista negra. Seguro chamar quantas vezes quiser."""
    global _TABELA_PRONTA
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blacklist_captura (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            nome_exibicao TEXT,
            origem TEXT DEFAULT 'manual',
            escopo TEXT DEFAULT 'autorais',
            motivo TEXT,
            resolvido INTEGER DEFAULT 0,
            criada_em TEXT,
            atualizada_em TEXT
        )
    ''')
    # Índices únicos parciais: impedem a mesma pessoa entrar duas vezes, sem
    # atrapalhar as linhas que ainda estão sem id (ou sem @).
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bl_user_id "
                   "ON blacklist_captura(user_id) WHERE user_id IS NOT NULL")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bl_username "
                   "ON blacklist_captura(username) WHERE username IS NOT NULL")
    conexao.commit()
    conexao.close()
    if EXIBIR_LOGS and not _TABELA_PRONTA:
        logger.info("🚫 [Lista Negra] Tabela verificada.")
    _TABELA_PRONTA = True


def _agora():
    return datetime.now(fuso_horario).strftime("%Y-%m-%d %H:%M:%S")


def _limpar_arroba(valor):
    """Normaliza '@Fulano', 'Fulano', ' @fulano ' → 'fulano'."""
    if valor is None:
        return None
    texto = str(valor).strip().lstrip("@").strip().lower()
    return texto or None


def extrair_alvo(texto):
    """
    Descobre QUEM é o alvo a partir de qualquer coisa que você colar.

    Aceita, nesta ordem de preferência:
      https://web.telegram.org/a/?account=2#630077263  → ID 630077263
      https://web.telegram.org/k/#630077263            → ID 630077263
      https://web.telegram.org/a/#@fulano              → @fulano
      tg://user?id=630077263                           → ID 630077263
      https://t.me/fulano                              → @fulano
      630077263                                        → ID
      @fulano  ou  fulano                              → @fulano

    ⚠️ O LINK É O MELHOR CAMINHO. No Telegram Web, o que vem depois do '#' na
    barra de endereço é o ID numérico da conversa aberta — ou seja, o ID da
    pessoa. E ID não muda nunca, enquanto o @ a pessoa troca quando quiser. Além
    disso, bloquear por ID funciona na hora: a checagem compara com o
    event.sender_id, sem precisar resolver nada no Telegram.

    O '?account=2' do link é só qual das SUAS contas está aberta no navegador.
    Não tem nada a ver com o alvo e é ignorado de propósito.

    Devolve (user_id, username, erro). Se erro != "", não dá para usar.
    """
    import re

    bruto = (texto or "").strip()
    if not bruto:
        return (None, None, "Não veio nada para bloquear.")

    # tg://user?id=123456
    achado = re.search(r"tg://user\?id=(\d+)", bruto, re.I)
    if achado:
        return (int(achado.group(1)), None, "")

    # Telegram Web: o alvo é o fragmento depois do '#'
    if "web.telegram.org" in bruto.lower():
        fragmento = bruto.split("#", 1)[1].strip() if "#" in bruto else ""
        if not fragmento:
            return (None, None,
                    "Esse link do Telegram Web não tem a parte do <code>#</code>. "
                    "Abra a conversa com a pessoa e copie a barra de endereço inteira.")
        if fragmento.lstrip("-").isdigit():
            numero = int(fragmento)
            if numero < 0:
                return (None, None,
                        "Esse link aponta para um <b>grupo ou canal</b>, não para uma pessoa. "
                        "Abra a conversa privada com ela e copie de lá.")
            return (numero, None, "")
        return (None, _limpar_arroba(fragmento), "")

    # t.me/alguma-coisa
    achado = re.search(r"(?:https?://)?t\.me/([^/?#\s]+)", bruto, re.I)
    if achado:
        parte = achado.group(1)
        if parte.startswith("+") or parte.lower() in ("joinchat", "c", "s", "proxy", "share", "addstickers"):
            return (None, None,
                    "Esse é um link de convite ou de canal, não o perfil de uma pessoa.")
        return (None, _limpar_arroba(parte), "")

    # ID numérico solto
    if bruto.lstrip("-").isdigit():
        numero = int(bruto)
        if numero < 0:
            return (None, None, "Isso é ID de grupo/canal, não de pessoa.")
        return (numero, None, "")

    # @fulano ou fulano
    limpo = _limpar_arroba(bruto)
    if limpo and re.fullmatch(r"[a-z0-9_]{3,32}", limpo):
        return (None, limpo, "")
    return (None, None,
            "Não entendi. Mande o <code>@usuario</code>, o ID numérico, "
            "ou cole o link do perfil da pessoa.")


async def _cliente_para_consulta():
    """
    Devolve um cliente Telethon de QUALQUER conta saudável do pool.

    Antes isto usava só a conta do posto 'espelho'. O problema: enquanto nenhuma
    conta está dentro do grupo, o posto fica VAGO e a consulta falhava sem ter
    por quê — as contas existem e estão logadas, só não estão de plantão.
    """
    try:
        import pool_contas
    except Exception as e:
        if EXIBIR_LOGS:
            logger.error(f"❌ [Lista Negra] pool_contas indisponível: {e}")
        return None

    cliente = await pool_contas.criar_cliente_da_funcao(pool_contas.FUNCAO_ESPELHO)
    if cliente is not None:
        return cliente

    for conta in pool_contas.listar_contas(somente_habilitadas=True):
        if conta.get("status_sessao") != pool_contas.SESSAO_OK:
            continue
        cliente = await pool_contas.criar_cliente(conta)
        if cliente is not None:
            return cliente
    return None


def invalidar_cache():
    """Força a próxima checagem a reler do banco."""
    _CACHE["dados"] = None
    _CACHE["carregado_em"] = 0.0


# =============================================================================
# 2. LEITURA E CHECAGEM  (o caminho quente)
# =============================================================================

def listar(incluir_pool=True):
    """Devolve as entradas da lista negra como lista de dicionários."""
    inicializar_tabelas()
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    if incluir_pool:
        cursor.execute("SELECT * FROM blacklist_captura ORDER BY origem DESC, id ASC")
    else:
        cursor.execute("SELECT * FROM blacklist_captura WHERE origem != ? ORDER BY id ASC",
                       (ORIGEM_POOL,))
    linhas = [dict(l) for l in cursor.fetchall()]
    conexao.close()
    return linhas


def _carregar_cache():
    """Monta os dois conjuntos de busca (ids e usernames) por escopo."""
    agora = time.time()
    if _CACHE["dados"] is not None and (agora - _CACHE["carregado_em"]) < _CACHE_SEGUNDOS:
        return _CACHE["dados"]

    ids_globais, ids_autorais = set(), set()
    users_globais, users_autorais = set(), set()
    try:
        for linha in listar():
            escopo = linha.get("escopo") or ESCOPO_AUTORAIS
            if linha.get("user_id"):
                (ids_globais if escopo == ESCOPO_GLOBAL else ids_autorais).add(int(linha["user_id"]))
            if linha.get("username"):
                alvo = users_globais if escopo == ESCOPO_GLOBAL else users_autorais
                alvo.add(str(linha["username"]).lower())
    except Exception as e:
        if EXIBIR_LOGS:
            logger.error(f"❌ [Lista Negra] Falha ao carregar cache: {e}")
        # Devolve o cache velho se existir: melhor uma lista desatualizada do
        # que deixar passar tudo por causa de um erro momentâneo de banco.
        if _CACHE["dados"] is not None:
            return _CACHE["dados"]

    dados = {
        "ids_globais": ids_globais,
        "ids_autorais": ids_autorais,
        "users_globais": users_globais,
        "users_autorais": users_autorais,
    }
    _CACHE["dados"] = dados
    _CACHE["carregado_em"] = agora
    return dados


def deve_ignorar(user_id, username=None, contexto=ESCOPO_AUTORAIS):
    """
    A pergunta do dia a dia: ignoro esta mensagem?

    contexto='global'   → checa só as entradas de escopo global. Use no topo do
                          handler, antes de saber de que chat veio.
    contexto='autorais' → checa global + autorais. Use depois de confirmar que a
                          mensagem veio do grupo de origem dos Autorais.

    Nunca levanta exceção: qualquer erro devolve False (não ignora), porque
    travar a captura inteira por causa da lista negra seria pior que o problema.
    """
    try:
        dados = _carregar_cache()

        if user_id is not None:
            uid = int(user_id)
            if uid in dados["ids_globais"]:
                return True
            if contexto != ESCOPO_GLOBAL and uid in dados["ids_autorais"]:
                return True

        arroba = _limpar_arroba(username)
        if arroba:
            if arroba in dados["users_globais"]:
                return True
            if contexto != ESCOPO_GLOBAL and arroba in dados["users_autorais"]:
                return True

        return False
    except Exception as e:
        if EXIBIR_LOGS:
            logger.error(f"❌ [Lista Negra] Erro na checagem (deixando passar): {e}")
        return False


def descrever_bloqueio(user_id, username=None):
    """Devolve um texto curto dizendo por que aquele autor está bloqueado."""
    try:
        alvo_id = int(user_id) if user_id is not None else None
        arroba = _limpar_arroba(username)
        for linha in listar():
            if alvo_id is not None and linha.get("user_id") and int(linha["user_id"]) == alvo_id:
                return f"{linha.get('origem')}/{linha.get('escopo')}"
            if arroba and linha.get("username") and str(linha["username"]).lower() == arroba:
                return f"{linha.get('origem')}/{linha.get('escopo')}"
    except Exception:
        pass
    return "desconhecido"


# =============================================================================
# 3. ESCRITA
# =============================================================================

def adicionar(user_id=None, username=None, nome_exibicao=None,
              origem=ORIGEM_MANUAL, escopo=ESCOPO_AUTORAIS, motivo=""):
    """
    Insere ou atualiza uma entrada.

    Aceita ID, @ ou os dois. Se a pessoa já estiver na lista (por qualquer um
    dos dois), completa os campos que faltam em vez de duplicar.
    """
    inicializar_tabelas()
    arroba = _limpar_arroba(username)
    if user_id is None and not arroba:
        return (False, "informe um ID numérico ou um @username")

    conexao = _obter_conexao()
    cursor = conexao.cursor()

    existente = None
    if user_id is not None:
        cursor.execute("SELECT * FROM blacklist_captura WHERE user_id = ?", (int(user_id),))
        existente = cursor.fetchone()
    if existente is None and arroba:
        cursor.execute("SELECT * FROM blacklist_captura WHERE username = ?", (arroba,))
        existente = cursor.fetchone()

    if existente is not None:
        campos, valores = [], []
        if user_id is not None and not existente["user_id"]:
            campos.append("user_id = ?")
            valores.append(int(user_id))
            campos.append("resolvido = 1")
        if arroba and not existente["username"]:
            campos.append("username = ?")
            valores.append(arroba)
        if nome_exibicao:
            campos.append("nome_exibicao = ?")
            valores.append(nome_exibicao)
        # O escopo mais amplo vence: se já era global, continua global.
        if escopo == ESCOPO_GLOBAL and existente["escopo"] != ESCOPO_GLOBAL:
            campos.append("escopo = ?")
            valores.append(ESCOPO_GLOBAL)
        campos.append("atualizada_em = ?")
        valores.append(_agora())
        valores.append(existente["id"])
        cursor.execute(f"UPDATE blacklist_captura SET {', '.join(campos)} WHERE id = ?", valores)
        conexao.commit()
        conexao.close()
        invalidar_cache()
        return (True, "entrada já existia e foi atualizada")

    cursor.execute(
        "INSERT INTO blacklist_captura "
        "(user_id, username, nome_exibicao, origem, escopo, motivo, resolvido, criada_em, atualizada_em) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (int(user_id) if user_id is not None else None, arroba, nome_exibicao,
         origem, escopo, motivo, 1 if user_id is not None else 0, _agora(), _agora()),
    )
    conexao.commit()
    conexao.close()
    invalidar_cache()

    rotulo = f"@{arroba}" if arroba else str(user_id)
    if EXIBIR_LOGS:
        logger.info(f"🚫 [Lista Negra] {rotulo} adicionado ({origem}/{escopo}).")
    return (True, "adicionado")


def remover(alvo):
    """
    Remove uma entrada manual. Aceita '@fulano', 'fulano' ou o ID numérico.

    Entradas de origem 'pool' NÃO podem ser removidas por aqui de propósito: são
    as suas próprias contas, e tirar uma delas recria o laço de recaptura. Para
    tirar de vez, remova a conta do pool_contas — aí ela sai daqui sozinha.
    """
    inicializar_tabelas()
    conexao = _obter_conexao()
    cursor = conexao.cursor()

    texto = str(alvo).strip()
    if texto.lstrip("-").isdigit():
        cursor.execute("SELECT * FROM blacklist_captura WHERE user_id = ?", (int(texto),))
    else:
        cursor.execute("SELECT * FROM blacklist_captura WHERE username = ?", (_limpar_arroba(texto),))
    linha = cursor.fetchone()

    if linha is None:
        conexao.close()
        return (False, "não encontrado na lista")
    if linha["origem"] == ORIGEM_POOL:
        conexao.close()
        return (False, "é uma conta sua do pool — remova pelo painel de Contas e Postos")

    cursor.execute("DELETE FROM blacklist_captura WHERE id = ?", (linha["id"],))
    conexao.commit()
    conexao.close()
    invalidar_cache()
    if EXIBIR_LOGS:
        logger.info(f"✅ [Lista Negra] {texto} removido.")
    return (True, "removido")


def sincronizar_contas_do_pool():
    """
    Garante que TODA conta do pool_contas está na lista negra, com escopo
    global — inclusive as que forem cadastradas no futuro.

    Também limpa: conta que saiu do pool sai daqui junto, para não ficar
    bloqueando um ID que não é mais seu.

    Chame no start do espelhador e depois de qualquer mexida no pool.
    Devolve (quantas_adicionadas, quantas_removidas).
    """
    inicializar_tabelas()
    try:
        import pool_contas
        contas = pool_contas.listar_contas()
    except Exception as e:
        if EXIBIR_LOGS:
            logger.error(f"❌ [Lista Negra] Não consegui ler o pool de contas: {e}")
        return (0, 0)

    ids_do_pool = set()
    adicionadas = 0
    for conta in contas:
        if not conta.get("user_id"):
            # Conta cadastrada mas ainda sem ID: roda 'identificar' no pool.
            if EXIBIR_LOGS:
                logger.warning(
                    f"⚠️ [Lista Negra] Conta '{conta.get('apelido')}' ainda sem user_id — "
                    f"ela NÃO está protegida. Rode: python3 pool_contas.py identificar"
                )
            continue
        ids_do_pool.add(int(conta["user_id"]))
        ok, resultado = adicionar(
            user_id=conta["user_id"],
            username=conta.get("username") or None,
            nome_exibicao=conta.get("nome_exibicao") or conta.get("apelido"),
            origem=ORIGEM_POOL,
            escopo=ESCOPO_GLOBAL,
            motivo="conta própria do pool",
        )
        if ok and resultado == "adicionado":
            adicionadas += 1

    # Faxina: entradas 'pool' de contas que não existem mais.
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    cursor.execute("SELECT id, user_id FROM blacklist_captura WHERE origem = ?", (ORIGEM_POOL,))
    removidas = 0
    for linha in cursor.fetchall():
        if linha["user_id"] and int(linha["user_id"]) not in ids_do_pool:
            cursor.execute("DELETE FROM blacklist_captura WHERE id = ?", (linha["id"],))
            removidas += 1
    conexao.commit()
    conexao.close()
    if removidas or adicionadas:
        invalidar_cache()
        if EXIBIR_LOGS:
            logger.info(f"🔄 [Lista Negra] Pool sincronizado: +{adicionadas} / -{removidas}.")
    return (adicionadas, removidas)


# =============================================================================
# 4. RESOLUÇÃO DE @USERNAME PARA ID
# =============================================================================

async def resolver_pendentes(cliente=None):
    """
    Passa nas entradas que só têm @ e tenta descobrir o ID numérico.

    Usa uma conta do pool para perguntar ao Telegram quem é aquele @. Se a conta
    não consegue enxergar o usuário (privacidade, nunca se cruzaram), a entrada
    fica pendente e continua valendo pelo @ mesmo.

    Devolve quantas foram resolvidas nesta passada.
    """
    inicializar_tabelas()
    pendentes = [l for l in listar() if not l.get("user_id") and l.get("username")]
    if not pendentes:
        return 0

    proprio = False
    if cliente is None:
        try:
            cliente = await _cliente_para_consulta()
            proprio = True
        except Exception as e:
            if EXIBIR_LOGS:
                logger.error(f"❌ [Lista Negra] Sem cliente para resolver @: {e}")
            return 0
    if cliente is None:
        if EXIBIR_LOGS:
            logger.warning("⚠️ [Lista Negra] Nenhuma conta apta para resolver os @ pendentes.")
        return 0

    resolvidas = 0
    try:
        for linha in pendentes:
            arroba = linha["username"]
            try:
                entidade = await cliente.get_entity(arroba)
                nome = " ".join(filter(None, [getattr(entidade, "first_name", None),
                                              getattr(entidade, "last_name", None)])).strip()
                conexao = _obter_conexao()
                cursor = conexao.cursor()
                cursor.execute(
                    "UPDATE blacklist_captura SET user_id = ?, nome_exibicao = ?, "
                    "resolvido = 1, atualizada_em = ? WHERE id = ?",
                    (int(entidade.id), nome or linha.get("nome_exibicao"), _agora(), linha["id"]),
                )
                conexao.commit()
                conexao.close()
                resolvidas += 1
                if EXIBIR_LOGS:
                    logger.info(f"🔎 [Lista Negra] @{arroba} resolvido para o ID {entidade.id}.")
            except Exception as e:
                if EXIBIR_LOGS:
                    logger.info(f"⏭️ [Lista Negra] @{arroba} não resolvido ainda ({type(e).__name__}).")
            await asyncio.sleep(1)
    finally:
        if proprio and cliente is not None:
            try:
                await cliente.disconnect()
            except Exception:
                pass

    if resolvidas:
        invalidar_cache()
    return resolvidas


async def adicionar_por_arroba(arroba, escopo=ESCOPO_AUTORAIS, motivo=""):
    """
    Adiciona pelo @ e já tenta resolver o ID na mesma ação.

    É esta que o painel do Telegram chama. Devolve (ok, mensagem_para_o_usuario).
    """
    user_id, username, erro = extrair_alvo(arroba)
    if erro:
        return (False, erro)

    # Caminho do ID (é o que vem do link): já está valendo na hora, porque a
    # checagem compara com o event.sender_id. Buscar o nome é só enfeite.
    if user_id is not None:
        ok, msg = adicionar(user_id=user_id, username=username,
                            escopo=escopo, motivo=motivo)
        if not ok:
            return (False, msg)

        rotulo = f"ID <code>{user_id}</code>"
        cliente = None
        try:
            cliente = await _cliente_para_consulta()
            if cliente is not None:
                entidade = await cliente.get_entity(user_id)
                nome = " ".join(filter(None, [getattr(entidade, "first_name", None),
                                              getattr(entidade, "last_name", None)])).strip()
                arroba_real = getattr(entidade, "username", None)
                adicionar(user_id=user_id, username=arroba_real, nome_exibicao=nome,
                          escopo=escopo, motivo=motivo)
                rotulo = nome or (f"@{arroba_real}" if arroba_real else rotulo)
        except Exception:
            # Sem nome não tem problema nenhum: o bloqueio é pelo número.
            pass
        finally:
            if cliente is not None:
                try:
                    await cliente.disconnect()
                except Exception:
                    pass

        return (True, f"{rotulo} bloqueado ✅")

    ok, msg = adicionar(username=username, escopo=escopo, motivo=motivo)
    if not ok:
        return (False, msg)

    resolvidas = await resolver_pendentes()
    if resolvidas:
        return (True, f"@{username} bloqueado e ID resolvido ✅")
    return (True, f"@{username} bloqueado (ID ainda não resolvido — vale pelo @ mesmo assim)")


# =============================================================================
# 5. RELATÓRIOS
# =============================================================================

def montar_relatorio_telegram():
    """
    Texto HTML da lista, para o painel do bot.

    Corta em 40 entradas de propósito: o Telegram derruba mensagem acima de
    4096 caracteres, e esse erro já derrubou tela neste projeto antes.
    """
    entradas = listar()
    if not entradas:
        return ("🚫 <b>Lista Negra de Captura</b>\n\n"
                "<i>Vazia.</i> Nem as suas contas estão protegidas — "
                "rode a sincronização.")

    do_pool = [e for e in entradas if e["origem"] == ORIGEM_POOL]
    manuais = [e for e in entradas if e["origem"] != ORIGEM_POOL]

    linhas = ["🚫 <b>Lista Negra de Captura</b>", ""]

    linhas.append(f"🔒 <b>Suas contas ({len(do_pool)})</b> — automático, em todo lugar")
    for e in do_pool[:10]:
        rotulo = e["nome_exibicao"] or (f"@{e['username']}" if e["username"] else "—")
        linhas.append(f"   • {rotulo} · <code>{e['user_id']}</code>")
    if not do_pool:
        linhas.append("   <i>nenhuma — rode a sincronização</i>")

    linhas.append("")
    linhas.append(f"✋ <b>Adicionados por você ({len(manuais)})</b>")
    if not manuais:
        linhas.append("   <i>nenhum</i>")
    for e in manuais[:30]:
        alvo = f"@{e['username']}" if e["username"] else f"<code>{e['user_id']}</code>"
        marca = "🌐" if e["escopo"] == ESCOPO_GLOBAL else "🎥"
        pendente = "" if e["user_id"] else " ⏳"
        linhas.append(f"   {marca} {alvo}{pendente}")
    if len(manuais) > 30:
        linhas.append(f"   <i>… e mais {len(manuais) - 30}</i>")

    linhas.append("")
    linhas.append("<i>🌐 em todo lugar · 🎥 só nos Autorais · ⏳ @ ainda não resolvido</i>")
    return "\n".join(linhas)


def montar_relatorio_terminal():
    """Versão sem HTML, para a linha de comando."""
    entradas = listar()
    if not entradas:
        return "🚫 Lista negra vazia. Rode: python3 blacklist_captura.py sincronizar"

    linhas = ["", "🚫 LISTA NEGRA DE CAPTURA", "=" * 56]
    for e in entradas:
        alvo = f"@{e['username']}" if e["username"] else "(sem @)"
        linhas.append(f"{alvo:<24} id={e['user_id'] or 'pendente':<14} "
                      f"{e['origem']}/{e['escopo']}")
        if e["nome_exibicao"]:
            linhas.append(f"    {e['nome_exibicao']}")
    linhas.append("=" * 56)
    pendentes = len([e for e in entradas if not e["user_id"]])
    if pendentes:
        linhas.append(f"⏳ {pendentes} @ sem ID resolvido. Rode: python3 blacklist_captura.py resolver")
    return "\n".join(linhas)


# =============================================================================
# 6. AUTOTESTE — roda sem Telegram e sem rede
# =============================================================================

def autoteste():
    """Confere as regras de escopo e origem com um banco temporário."""
    global DB_NAME
    banco_real = DB_NAME
    DB_NAME = "teste_blacklist_temp.db"
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)

    falhas = []

    def conferir(rotulo, obtido, esperado):
        marca = "✅" if obtido == esperado else "❌"
        print(f"  {marca} {rotulo}: {obtido} (esperado: {esperado})")
        if obtido != esperado:
            falhas.append(rotulo)

    try:
        inicializar_tabelas()

        print("\n🧪 Conta própria (escopo global) é ignorada em qualquer contexto")
        adicionar(user_id=1226920464, username="Rafaelnm", origem=ORIGEM_POOL,
                  escopo=ESCOPO_GLOBAL)
        invalidar_cache()
        conferir("nos autorais", deve_ignorar(1226920464), True)
        conferir("em canal de parceiro", deve_ignorar(1226920464, contexto=ESCOPO_GLOBAL), True)

        print("\n🧪 Entrada manual com escopo autorais NÃO vale fora dos autorais")
        adicionar(username="@concorrente", escopo=ESCOPO_AUTORAIS)
        invalidar_cache()
        conferir("nos autorais, pelo @", deve_ignorar(None, "concorrente"), True)
        conferir("nos autorais, com @ maiúsculo", deve_ignorar(None, "@CONCORRENTE"), True)
        conferir("fora dos autorais", deve_ignorar(None, "concorrente", ESCOPO_GLOBAL), False)

        print("\n🧪 Quem não está na lista passa")
        conferir("estranho por id", deve_ignorar(999999999), False)
        conferir("estranho por @", deve_ignorar(None, "ninguem"), False)
        conferir("sem autor nenhum", deve_ignorar(None, None), False)

        print("\n🧪 Não duplica e o escopo mais amplo vence")
        adicionar(username="@concorrente", escopo=ESCOPO_GLOBAL)
        invalidar_cache()
        conferir("continua com 2 entradas", len(listar()), 2)
        conferir("agora vale fora dos autorais", deve_ignorar(None, "concorrente", ESCOPO_GLOBAL), True)

        print("\n🧪 Entrada do pool não pode ser removida pelo painel")
        ok, _motivo = remover("1226920464")
        conferir("remoção recusada", ok, False)
        ok, _motivo = remover("@concorrente")
        conferir("remoção manual aceita", ok, True)
        invalidar_cache()
        conferir("sobrou só a do pool", len(listar()), 1)

        print("\n🧪 Erro de banco não trava a captura")
        DB_NAME = "/caminho/que/nao/existe/x.db"
        invalidar_cache()
        conferir("deixa passar em vez de quebrar", deve_ignorar(1226920464), False)

    finally:
        DB_NAME = banco_real
        invalidar_cache()
        if os.path.exists("teste_blacklist_temp.db"):
            os.remove("teste_blacklist_temp.db")

    print("\n" + "=" * 52)
    if falhas:
        print(f"🛑 {len(falhas)} verificação(ões) falharam: {', '.join(falhas)}")
        return False
    print("✅ Todas as regras da lista negra estão corretas.")
    return True


# =============================================================================
# 7. LINHA DE COMANDO
# =============================================================================

def main():
    argumentos = sys.argv[1:]
    comando = argumentos[0] if argumentos else "listar"
    resto = argumentos[1:]

    if comando in ("ajuda", "-h", "--help"):
        print("Comandos: listar | add <@user|id|link> [global] | del <@user|id> |")
        print("  O 'link' pode ser a barra de endereço do Telegram Web na conversa")
        print("  com a pessoa, ex: https://web.telegram.org/a/?account=2#630077263")
        print("          sincronizar | resolver | testar <id|@user> | autoteste")
        return

    if comando == "autoteste":
        sys.exit(0 if autoteste() else 1)

    if comando == "listar":
        print(montar_relatorio_terminal())
        return

    if comando == "sincronizar":
        adicionadas, removidas = sincronizar_contas_do_pool()
        print(f"✅ Pool sincronizado: {adicionadas} adicionada(s), {removidas} removida(s).")
        print(montar_relatorio_terminal())
        return

    if comando == "resolver":
        quantas = asyncio.run(resolver_pendentes())
        print(f"🔎 {quantas} @ resolvido(s) para ID.")
        print(montar_relatorio_terminal())
        return

    if comando == "add" and resto:
        escopo = ESCOPO_GLOBAL if len(resto) > 1 and resto[1].lower() == "global" else ESCOPO_AUTORAIS
        ok, msg = asyncio.run(adicionar_por_arroba(resto[0], escopo=escopo))
        print(("✅ " if ok else "❌ ") + msg.replace("<code>", "").replace("</code>", ""))
        return

    if comando == "del" and resto:
        ok, msg = remover(resto[0])
        print(("✅ " if ok else "❌ ") + msg)
        return

    if comando == "testar" and resto:
        alvo = resto[0]
        if alvo.lstrip("-").isdigit():
            resultado = deve_ignorar(int(alvo))
            detalhe = descrever_bloqueio(int(alvo))
        else:
            resultado = deve_ignorar(None, alvo)
            detalhe = descrever_bloqueio(None, alvo)
        print(f"{'🚫 IGNORADO' if resultado else '✅ passa'}  ({detalhe})")
        return

    print(f"❓ Comando desconhecido: {comando}. Use: python3 blacklist_captura.py ajuda")


if __name__ == "__main__":
    main()

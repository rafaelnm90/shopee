"""
Funções compartilhadas pelos robôs: registro de erros, cache de análises da IA,
cache de nomes de grupos e validação de IDs do Telegram. O acesso ao banco fica
no db.py.
"""
import os
import json
from datetime import datetime
import logging
from zoneinfo import ZoneInfo
import traceback
import db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

MAX_ERRORS = 50

def registrar_erro_json(mensagem_erro, origem="Geral", contexto_extra=None):
    """
    Grava um erro (com o traceback atual, se houver) na tabela erros_logs, que o
    painel de erros do bot_mestre mostra. Guarda só os MAX_ERRORS mais recentes.

    O nome diz "json" porque antes gravava num arquivo JSON; ficou para não
    quebrar quem importa.

    Não grava nada enquanto existir trava_manutencao.txt: o botão de limpar logs
    do bot_mestre cria esse arquivo para silenciar erros enquanto o código é
    corrigido, e o divulgacao_canal apaga ao iniciar (no próximo deploy).
    """
    try:
        if os.path.exists("trava_manutencao.txt"):
            return

        rastro = traceback.format_exc()
        if rastro == "NoneType: None\n":
            rastro = "Sem rastro de código associado (Possível erro lógico ou manual)."

        # Fuso explícito: a hora precisa sair certa mesmo num processo que não importou fuso.py.
        timestamp = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M:%S")
        contexto_str = json.dumps(contexto_extra) if contexto_extra else "{}"

        conexao = db.conectar()
        cursor = conexao.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS erros_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                origem TEXT,
                erro TEXT,
                rastro_codigo TEXT,
                contexto TEXT
            )
        ''')
        
        cursor.execute('''
            INSERT INTO erros_logs (timestamp, origem, erro, rastro_codigo, contexto)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, origem, str(mensagem_erro), rastro.strip(), contexto_str))
        
        cursor.execute(f'''
            DELETE FROM erros_logs 
            WHERE id NOT IN (
                SELECT id FROM erros_logs ORDER BY id DESC LIMIT {MAX_ERRORS}
            )
        ''')
        
        conexao.commit()
        conexao.close()
        
        logger.info(f"✅ Sucesso: Erro de {origem} registado com rastro no SQLite.")
    except Exception as e:
        logger.error(f"❌ Falha crítica ao tentar registar log no SQLite: {e}")

# Cache de análises da IA: o Espião e as rotas do Espelhador capturam dos mesmos
# canais, e sem cache o mesmo vídeo iria para a IA uma vez por robô, gastando cota.
# A chave é o post de origem (chat + msg_id), na tabela cache_analises_ia.
def _garantir_cache_ia(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cache_analises_ia (
            chave TEXT PRIMARY KEY,
            resultado TEXT,
            data_analise TEXT,
            usos INTEGER DEFAULT 1
        )
    ''')

def chave_cache_ia(chat_origem, msg_id):
    """
    Chave do cache para o post de origem: "<chat>_<msg_id>", sem o tópico do chat.
    None quando falta chat ou msg_id.
    """
    if not chat_origem or not msg_id:
        return None
    return f"{str(chat_origem).split(':')[0].strip()}_{msg_id}"

def consultar_cache_ia(chave):
    """Devolve a análise já feita para este post (e conta mais um uso), ou None."""
    if not chave:
        return None
    try:
        conexao = db.conectar()
        cursor = conexao.cursor()
        _garantir_cache_ia(cursor)
        cursor.execute("SELECT resultado FROM cache_analises_ia WHERE chave = ?", (str(chave),))
        linha = cursor.fetchone()
        if linha:
            cursor.execute("UPDATE cache_analises_ia SET usos = usos + 1 WHERE chave = ?", (str(chave),))
            conexao.commit()
        conexao.close()
        return linha[0] if linha else None
    except Exception as e:
        logger.error(f"❌ [Cache IA] Erro ao consultar: {e}")
        return None

def gravar_cache_ia(chave, resultado):
    """Guarda a análise do post. Se a chave já existe, mantém a primeira. Devolve True se gravou."""
    if not chave or not resultado:
        return False
    try:
        conexao = db.conectar()
        cursor = conexao.cursor()
        _garantir_cache_ia(cursor)
        cursor.execute(
            "INSERT OR IGNORE INTO cache_analises_ia (chave, resultado, data_analise, usos) VALUES (?, ?, ?, 1)",
            (str(chave), str(resultado), datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M:%S"))
        )
        conexao.commit()
        conexao.close()
        return True
    except Exception as e:
        logger.error(f"❌ [Cache IA] Erro ao gravar: {e}")
        return False

def estatisticas_cache_ia():
    """(análises guardadas, chamadas à IA economizadas), para o log de faxina."""
    try:
        conexao = db.conectar()
        cursor = conexao.cursor()
        _garantir_cache_ia(cursor)
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(usos - 1), 0) FROM cache_analises_ia")
        total, economizadas = cursor.fetchone()
        conexao.close()
        return total or 0, economizadas or 0
    except Exception:
        return 0, 0

def limpar_cache_ia_antigo(dias=30):
    """
    Apaga análises com mais de `dias` dias; a essa altura todos os robôs já
    publicaram o vídeo. Devolve quantas foram removidas.
    """
    try:
        from datetime import timedelta
        corte = (datetime.now(ZoneInfo("America/Sao_Paulo")) - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
        conexao = db.conectar()
        cursor = conexao.cursor()
        _garantir_cache_ia(cursor)
        cursor.execute("DELETE FROM cache_analises_ia WHERE data_analise < ?", (corte,))
        removidos = cursor.rowcount
        conexao.commit()
        conexao.close()
        if removidos:
            logger.info(f"🧹 [Cache IA] {removidos} análise(s) com mais de {dias} dias removida(s).")
        return removidos
    except Exception:
        return 0

def ler_cache_nomes_grupos():
    """
    Nomes de grupos/canais/tópicos já descobertos, {chat_id: nome}. Os painéis
    mostram o nome em vez do ID. A chave de um tópico é "<grupo>_<tópico>".
    """
    try:
        conexao = db.conectar()
        cursor = conexao.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS cache_nomes (chat_id TEXT PRIMARY KEY, nome TEXT)")
        cursor.execute("SELECT chat_id, nome FROM cache_nomes")
        resultados = cursor.fetchall()
        conexao.close()
        
        return {linha[0]: linha[1] for linha in resultados}
    except Exception as e:
        logger.error(f"❌ Erro ao ler cache de nomes do SQLite: {e}")
        return {}

def salvar_nome_grupo(chat_id, nome):
    """Guarda o nome no cache; ignora nome vazio ou igual ao próprio ID."""
    if not chat_id or not nome:
        return
    chave = str(chat_id).strip()
    nome_str = str(nome).strip()
    if not chave or not nome_str or nome_str == chave:
        return
        
    try:
        conexao = db.conectar()
        cursor = conexao.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS cache_nomes (chat_id TEXT PRIMARY KEY, nome TEXT)")
        
        cursor.execute("SELECT nome FROM cache_nomes WHERE chat_id = ?", (chave,))
        resultado = cursor.fetchone()
        
        if resultado and resultado[0] == nome_str:
            conexao.close()
            return
            
        cursor.execute("INSERT OR REPLACE INTO cache_nomes (chat_id, nome) VALUES (?, ?)", (chave, nome_str))
        conexao.commit()
        conexao.close()
        
        logger.info(f"✅ Nome do grupo {chave} salvo no cache do SQLite: {nome_str}")
    except Exception as e:
        logger.error(f"❌ Falha ao salvar nome do grupo {chave} no cache SQLite: {e}")

async def validar_e_formatar_alvo(bot_instance, entrada):
    """
    Converte o que o admin digitou (link t.me, link do Telegram Web, @username,
    ID, "ID_tópico", "ID:tópico" ou "ID/tópico") no ID do chat, confirmando no
    Telegram.

    Devolve (ok, id_final, nome). id_final é "<id>" ou "<id>:<tópico>".
    - Bot consegue ler o chat: ok=True com o ID real (-100... para canal e
      supergrupo) e o nome.
    - Bot não consegue ler, mas é ID numérico: aceita assim mesmo (o Espião pode
      estar num chat onde o bot não está) e devolve o próprio ID como nome.
    - Bot não consegue ler e é @username: recusa (ok=False), porque sem o
      Telegram não dá para descobrir o ID numérico.
    """
    entrada = str(entrada).strip()
    if not entrada:
        return False, None, None

    chat_base = entrada
    topico_id = None

    # Separa o chat e o tópico conforme o formato digitado.
    if "t.me/c/" in entrada:
        partes = entrada.split("t.me/c/")[1].split("/")
        chat_base = f"-100{partes[0]}"
        if len(partes) > 1 and partes[1].isdigit(): topico_id = partes[1]
    elif "t.me/" in entrada:
        partes = entrada.split("t.me/")[1].split("/")
        chat_base = f"@{partes[0]}"
        if len(partes) > 1 and partes[1].isdigit(): topico_id = partes[1]
    elif "web.telegram.org" in entrada and "#" in entrada:
        # Telegram Web (versões K e A): o tópico vem depois de "_".
        parte_web = entrada.split("#")[1].split("/")[0]
        if "_" in parte_web:
            partes_web = parte_web.split("_")
            chat_base = partes_web[0]
            if partes_web[1].isdigit(): topico_id = partes_web[1]
        else:
            chat_base = parte_web
    elif "_" in entrada and not "http" in entrada:
        # Formato que o painel exibe ("-1003673555953_1"). Só vale se os dois lados
        # forem números, para não quebrar @usernames com underline (@meu_canal).
        partes = entrada.rsplit("_", 1)
        if len(partes) == 2 and partes[1].strip().isdigit() and partes[0].strip().lstrip('-').isdigit():
            chat_base = partes[0].strip()
            topico_id = partes[1].strip()
    elif ":" in entrada and not "http" in entrada:
        partes = entrada.split(":")
        chat_base = partes[0]
        if len(partes) > 1 and partes[1].isdigit(): topico_id = partes[1]
    elif "/" in entrada and not "http" in entrada:
        partes = entrada.split("/")
        chat_base = partes[0]
        if len(partes) > 1 and partes[1].isdigit(): topico_id = partes[1]

    # O admin pode ter digitado o ID com ou sem -100; testa as variações.
    variacoes = [chat_base]
    if chat_base.lstrip('-').isdigit():
        so_num = chat_base.replace("-100", "").replace("-", "")
        variacoes = [chat_base, f"-100{so_num}", f"-{so_num}", so_num]

    id_confirmado = None
    nome_confirmado = None
    for var in variacoes:
        try:
            chat_obj = await bot_instance.get_chat(var)
            id_confirmado = str(chat_obj.id)
            if chat_obj.type in ["supergroup", "channel"] and not id_confirmado.startswith("-100"):
                 id_confirmado = f"-100{id_confirmado}"
            nome_confirmado = chat_obj.title or chat_obj.full_name or id_confirmado
            break 
        except Exception:
            continue 

    if id_confirmado:
        id_final = f"{id_confirmado}:{topico_id}" if topico_id else id_confirmado
        return True, id_final, nome_confirmado
    else:
        if chat_base.lstrip('-').isdigit() or chat_base.startswith("@"):
             if chat_base.startswith("@"):
                  return False, entrada, None 
             else:
                  id_final = f"{chat_base}:{topico_id}" if topico_id else chat_base
                  return True, id_final, chat_base

        return False, entrada, None

def obter_banco_global_origens():
    """
    Todas as origens (canais/grupos) monitoradas por algum robô: alvos do Espião,
    origem do Autorais e origens das rotas do Espelhador (espelhos_config.json).
    Alimenta o botão "Importar Banco Global", que copia essas origens para outro robô.
    """
    origens_globais = set()
    try:
        conexao = db.conectar()
        cursor = conexao.cursor()
        
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'alvos_espiao'")
        res = cursor.fetchone()
        if res:
            dados_espiao = json.loads(res[0])
            for alvo in dados_espiao.get("alvos", []):
                origens_globais.add(str(alvo))
                
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'autorais_config'")
        res = cursor.fetchone()
        if res:
            dados_aut = json.loads(res[0])
            origem = dados_aut.get("origem")
            if origem and str(origem) not in ["Não definida", "Não definido"]:
                origens_globais.add(str(origem))
                
        conexao.close()
    except Exception: pass
    
    try:
        with open("espelhos_config.json", "r", encoding="utf-8") as f:
            dados_espelhos = json.load(f)
            for rota in dados_espelhos.get("rotas", []):
                for o in rota.get("origens", []):
                    origens_globais.add(id_da_origem(o))
                if "origem" in rota:
                    origens_globais.add(str(rota["origem"]))
    except Exception: pass
    
    return list(origens_globais)


def id_da_origem(origem):
    """
    Origem de rota do Espelhador como texto ("-100123", "-100123:5" ou "@canal").

    Rotas criadas pelo assistente do painel antes da correção gravavam a origem como
    {"id": ..., "nome": ...}; o motor compara texto e nunca casava com esse formato.
    """
    if isinstance(origem, dict):
        return str(origem.get("id") or "")
    return str(origem)


def normalizar_origens_rotas(dados):
    """
    Converte, em dados (conteúdo do espelhos_config.json), as origens gravadas como
    {"id", "nome"} para o ID em texto, sem repetir origem. Também tira de
    status_canais as entradas que o auditor criou para o formato antigo.

    Altera dados no lugar e devolve True se mudou alguma coisa (quem chamou decide
    se grava).
    """
    mudou = False
    for rota in dados.get("rotas", []):
        origens = rota.get("origens")
        if isinstance(origens, list) and any(isinstance(o, dict) for o in origens):
            novas = []
            for o in origens:
                alvo = id_da_origem(o)
                if alvo and alvo not in novas:
                    novas.append(alvo)
            rota["origens"] = novas
            mudou = True

        status = rota.get("status_canais")
        if isinstance(status, dict):
            lixo = [chave for chave in status if str(chave).startswith("{")]
            for chave in lixo:
                del status[chave]
                mudou = True
    return mudou


def salvar_json_atomico(caminho, dados, **opcoes_dump):
    """
    Grava dados em JSON sem que outro processo leia o arquivo pela metade.

    espelhos_config.json e fila_espelhador.json são reescritos pelo painel, pelo
    motor_userbot e pelo bot_mestre. Com open("w") o arquivo fica vazio até o
    json.dump terminar; quem lê nesse instante recebe JSON inválido, e o painel trata
    isso como "nenhuma rota" (um salvamento seguinte apagaria todas). Aqui o conteúdo
    vai para um arquivo temporário na mesma pasta e os.replace troca os dois de uma
    vez: quem lê vê o arquivo antigo inteiro ou o novo inteiro.

    opcoes_dump vai direto para json.dump (indent, ensure_ascii).
    """
    import tempfile
    pasta = os.path.dirname(os.path.abspath(caminho))
    descritor, temporario = tempfile.mkstemp(dir=pasta, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(descritor, "w", encoding="utf-8") as f:
            json.dump(dados, f, **opcoes_dump)
        # mkstemp cria com permissão 600; mantém a do arquivo que está sendo trocado.
        try:
            os.chmod(temporario, os.stat(caminho).st_mode & 0o777)
        except FileNotFoundError:
            os.chmod(temporario, 0o644)
        os.replace(temporario, caminho)
    except BaseException:
        try:
            os.remove(temporario)
        except OSError:
            pass
        raise

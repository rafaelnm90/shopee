EXIBIR_LOGS = True
import os
import json
from datetime import datetime
import logging
from zoneinfo import ZoneInfo
import traceback
import sqlite3

if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger = logging.getLogger(__name__)

MAX_ERRORS = 50
DB_NAME = "banco_dados.db"

def obter_conexao_utils():
    """Conexão local para o utils não depender de importações cruzadas."""
    return sqlite3.connect(DB_NAME, timeout=20.0)

# Mantivemos o nome 'registrar_erro_json' para não quebrar a importação dos outros scripts
def registrar_erro_json(mensagem_erro, origem="Geral", contexto_extra=None):
    try:
        # Se a trava de manutenção existir, o erro é completamente ignorado
        if os.path.exists("trava_manutencao.txt"):
            return

        rastro = traceback.format_exc()
        if rastro == "NoneType: None\n":
            rastro = "Sem rastro de código associado (Possível erro lógico ou manual)."

        # 🕐 Fuso explícito: o log de erro é lido por humano, então a hora precisa
        # estar certa mesmo se esta função for chamada fora dos serviços principais.
        timestamp = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d %H:%M:%S")
        contexto_str = json.dumps(contexto_extra) if contexto_extra else "{}"

        conexao = obter_conexao_utils()
        cursor = conexao.cursor()
        
        # Garante que a tabela existe
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
        
        # Limpa logs antigos para manter o limite exato de MAX_ERRORS no banco
        cursor.execute(f'''
            DELETE FROM erros_logs 
            WHERE id NOT IN (
                SELECT id FROM erros_logs ORDER BY id DESC LIMIT {MAX_ERRORS}
            )
        ''')
        
        conexao.commit()
        conexao.close()
        
        if EXIBIR_LOGS: logger.info(f"✅ Sucesso: Erro de {origem} registado com rastro no SQLite.")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha crítica ao tentar registar log no SQLite: {e}")

# --- CACHE PERSISTENTE DE NOMES DE GRUPOS/CANAIS ---

# ==========================================
# 🧠 CACHE DE ANÁLISES DA IA
# Vários robôs capturam dos MESMOS canais (Espião e as rotas do Espelhador).
# Sem cache, o mesmo vídeo é enviado à IA uma vez por robô — triplicando a cota.
# A chave é a mensagem de origem: chat + msg_id identificam o post exato.
# ==========================================
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
    """Identidade do post de origem. None quando não há dados suficientes."""
    if not chat_origem or not msg_id:
        return None
    return f"{str(chat_origem).split(':')[0].strip()}_{msg_id}"

def consultar_cache_ia(chave):
    """Devolve a análise já feita por outro robô, ou None."""
    if not chave:
        return None
    try:
        conexao = obter_conexao_utils()
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
        if EXIBIR_LOGS: logger.error(f"❌ [Cache IA] Erro ao consultar: {e}")
        return None

def gravar_cache_ia(chave, resultado):
    if not chave or not resultado:
        return False
    try:
        conexao = obter_conexao_utils()
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
        if EXIBIR_LOGS: logger.error(f"❌ [Cache IA] Erro ao gravar: {e}")
        return False

def estatisticas_cache_ia():
    """(entradas, reaproveitamentos) — mostra quanto o cache economizou."""
    try:
        conexao = obter_conexao_utils()
        cursor = conexao.cursor()
        _garantir_cache_ia(cursor)
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(usos - 1), 0) FROM cache_analises_ia")
        total, economizadas = cursor.fetchone()
        conexao.close()
        return total or 0, economizadas or 0
    except Exception:
        return 0, 0

def limpar_cache_ia_antigo(dias=30):
    """O vídeo já foi publicado por todos muito antes disso."""
    try:
        from datetime import timedelta
        corte = (datetime.now(ZoneInfo("America/Sao_Paulo")) - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
        conexao = obter_conexao_utils()
        cursor = conexao.cursor()
        _garantir_cache_ia(cursor)
        cursor.execute("DELETE FROM cache_analises_ia WHERE data_analise < ?", (corte,))
        removidos = cursor.rowcount
        conexao.commit()
        conexao.close()
        if removidos and EXIBIR_LOGS:
            logger.info(f"🧹 [Cache IA] {removidos} análise(s) com mais de {dias} dias removida(s).")
        return removidos
    except Exception:
        return 0

def ler_cache_nomes_grupos():
    try:
        conexao = obter_conexao_utils()
        cursor = conexao.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS cache_nomes (chat_id TEXT PRIMARY KEY, nome TEXT)")
        cursor.execute("SELECT chat_id, nome FROM cache_nomes")
        resultados = cursor.fetchall()
        conexao.close()
        
        return {linha[0]: linha[1] for linha in resultados}
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler cache de nomes do SQLite: {e}")
        return {}

def salvar_nome_grupo(chat_id, nome):
    if not chat_id or not nome:
        return
    chave = str(chat_id).strip()
    nome_str = str(nome).strip()
    if not chave or not nome_str or nome_str == chave:
        return
        
    try:
        conexao = obter_conexao_utils()
        cursor = conexao.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS cache_nomes (chat_id TEXT PRIMARY KEY, nome TEXT)")
        
        # Verifica se já existe e é exatamente igual para poupar gravações desnecessárias
        cursor.execute("SELECT nome FROM cache_nomes WHERE chat_id = ?", (chave,))
        resultado = cursor.fetchone()
        
        if resultado and resultado[0] == nome_str:
            conexao.close()
            return
            
        cursor.execute("INSERT OR REPLACE INTO cache_nomes (chat_id, nome) VALUES (?, ?)", (chave, nome_str))
        conexao.commit()
        conexao.close()
        
        if EXIBIR_LOGS: logger.info(f"✅ Nome do grupo {chave} salvo no cache do SQLite: {nome_str}")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha ao salvar nome do grupo {chave} no cache SQLite: {e}")

# --- NOVO: MOTOR INTELIGENTE DE VALIDAÇÃO DE ALVOS ---
async def validar_e_formatar_alvo(bot_instance, entrada):
    """
    Analisa a entrada, extrai o subgrupo (tópico) se existir,
    testa as variações de ID no Telegram e devolve o ID numérico confirmado + Nome.
    """
    entrada = str(entrada).strip()
    if not entrada:
        return False, None, None

    chat_base = entrada
    topico_id = None

    # 1. Extrair ID base e Subgrupo (Tópico)
    if "t.me/c/" in entrada:
        partes = entrada.split("t.me/c/")[1].split("/")
        chat_base = f"-100{partes[0]}"
        if len(partes) > 1 and partes[1].isdigit(): topico_id = partes[1]
    elif "t.me/" in entrada:
        partes = entrada.split("t.me/")[1].split("/")
        chat_base = f"@{partes[0]}"
        if len(partes) > 1 and partes[1].isdigit(): topico_id = partes[1]
    elif "web.telegram.org" in entrada and "#" in entrada:
        # ✅ NOVO: Trata o Telegram Web "K" e "A", separando o tópico pelo underline (_)
        parte_web = entrada.split("#")[1].split("/")[0]
        if "_" in parte_web:
            partes_web = parte_web.split("_")
            chat_base = partes_web[0]
            if partes_web[1].isdigit(): topico_id = partes_web[1]
        else:
            chat_base = parte_web
    elif "_" in entrada and not "http" in entrada:
        # ✅ NOVO: aceita o formato exibido no painel ("-1003673555953_1").
        # rsplit + checagem dupla evita quebrar @usernames com underline (@meu_canal).
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

    # 2. Gerar variações de ID para o teste
    variacoes = [chat_base]
    if chat_base.lstrip('-').isdigit():
        so_num = chat_base.replace("-100", "").replace("-", "")
        variacoes = [chat_base, f"-100{so_num}", f"-{so_num}", so_num]

    # 3. Testar no Telegram
    id_confirmado = None
    nome_confirmado = None
    for var in variacoes:
        try:
            chat_obj = await bot_instance.get_chat(var)
            id_confirmado = str(chat_obj.id)
            # Adiciona o -100 ao ID confirmado se for um supergrupo/canal
            if chat_obj.type in ["supergroup", "channel"] and not id_confirmado.startswith("-100"):
                 id_confirmado = f"-100{id_confirmado}"
            nome_confirmado = chat_obj.title or chat_obj.full_name or id_confirmado
            break 
        except Exception:
            continue 

    # 4. Retornar os resultados
    if id_confirmado:
        id_final = f"{id_confirmado}:{topico_id}" if topico_id else id_confirmado
        return True, id_final, nome_confirmado
    else:
        # ✅ CORREÇÃO (MODO TRUST): Se o bot não tem permissão para ler o grupo para pegar o nome,
        # MAS o que você enviou é claramente um ID numérico ou @username, ele aprova mesmo assim!
        # No Modo Trust, tentaremos extrair o ID numérico do username se possível.
        if chat_base.lstrip('-').isdigit() or chat_base.startswith("@"):
             if chat_base.startswith("@"):
                  # Modo Trust não pode resolver usernames em IDs numéricos de forma confiável
                  # É mais seguro falhar e pedir o ID numérico do que arriscar um loop
                  return False, entrada, None 
             else:
                  id_final = f"{chat_base}:{topico_id}" if topico_id else chat_base
                  return True, id_final, chat_base # Retorna o próprio ID no lugar do nome

        return False, entrada, None

def obter_banco_global_origens():
    """Varre todos os bancos de dados e junta todos os IDs monitorados no sistema."""
    origens_globais = set()
    try:
        conexao = obter_conexao_utils()
        cursor = conexao.cursor()
        
        # 1. Puxa do Espião
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'alvos_espiao'")
        res = cursor.fetchone()
        if res:
            dados_espiao = json.loads(res[0])
            for alvo in dados_espiao.get("alvos", []):
                origens_globais.add(str(alvo))
                
        # 2. Puxa de Autorais
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'autorais_config'")
        res = cursor.fetchone()
        if res:
            dados_aut = json.loads(res[0])
            origem = dados_aut.get("origem")
            if origem and str(origem) not in ["Não definida", "Não definido"]:
                origens_globais.add(str(origem))
                
        conexao.close()
    except Exception: pass
    
    # 3. Puxa do Espelhador (JSON)
    try:
        with open("espelhos_config.json", "r", encoding="utf-8") as f:
            dados_espelhos = json.load(f)
            for rota in dados_espelhos.get("rotas", []):
                for o in rota.get("origens", []):
                    origens_globais.add(str(o))
                if "origem" in rota:
                    origens_globais.add(str(rota["origem"]))
    except Exception: pass
    
    return list(origens_globais)

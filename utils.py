EXIBIR_LOGS = True
import os
import json
from datetime import datetime
import logging
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

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

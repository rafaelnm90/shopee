# 0. CONFIGURAÇÕES INICIAIS
EXIBIR_LOGS = True
import sqlite3
import logging
import os
from datetime import datetime

if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger = logging.getLogger(__name__)

DB_NAME = "banco_dados.db"

def obter_conexao():
    """Retorna uma conexão limpa com o SQLite, configurada para ler colunas por nome."""
    conexao = sqlite3.connect(DB_NAME, timeout=20.0) # Timeout estendido para lidar com alta concorrência
    conexao.row_factory = sqlite3.Row
    return conexao

def inicializar_banco():
    if EXIBIR_LOGS: logger.info("🚀 [Database] Iniciando a construção e verificação das fundações do banco de dados SQLite...")
    
    conexao = obter_conexao()
    cursor = conexao.cursor()

    # 1. Fila Principal (Aba de postagens normais)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fila_postagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_unico TEXT UNIQUE,
            caminho_video TEXT,
            video_id TEXT,
            legenda TEXT,
            data_alvo TEXT,
            status TEXT DEFAULT 'PENDENTE',
            prioridade INTEGER DEFAULT 0,
            data_postagem TEXT,
            horario_postagem TEXT
        )
    ''')

    # 2. Configurações Globais (Substitui config_rotina, alvos_divulgacao, pausa_programada, etc.)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    ''')

    # 3. Fila do Espião (Substitui fila_clonagem.json)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fila_espiao (
            id_unico TEXT PRIMARY KEY,
            chat_origem TEXT,
            nome_origem TEXT,
            msg_id INTEGER,
            caminho_video TEXT,
            link_original TEXT,
            processado INTEGER DEFAULT 0,
            data_captura TEXT,
            data_postagem TEXT,
            horario_postagem TEXT
        )
    ''')

    # 4. Fila do Espelhador (Substitui fila_espelhador.json)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fila_espelhador (
            id_unico TEXT PRIMARY KEY,
            chat_origem TEXT,
            nome_origem TEXT,
            msg_id INTEGER,
            destino TEXT,
            nome_rota TEXT,
            texto_processado TEXT,
            caminho_video TEXT,
            processado INTEGER DEFAULT 0,
            data_captura TEXT,
            horario_disparo TEXT,
            data_publicacao TEXT
        )
    ''')

    # 5. Fila de Retorno / Autorais (Substitui fila_retorno.json)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fila_autorais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_id_destino INTEGER,
            legenda TEXT,
            caminho_arquivo TEXT,
            data_alvo TEXT
        )
    ''')

    # 6. Banco de Pedidos Financeiro (Substitui banco_pedidos.json)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pedidos_financeiro (
            order_sn TEXT PRIMARY KEY,
            data TEXT,
            status TEXT,
            comissao_total REAL,
            comissao_shopee REAL,
            comissao_vendedor REAL
        )
    ''')

    # 7. Histórico Financeiro Agrupado (Substitui historico_financeiro.json)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico_financeiro (
            data_ref TEXT PRIMARY KEY,
            aprovado REAL,
            pendente REAL,
            cancelado REAL,
            shopee REAL,
            vendedor REAL,
            qtd_aprovado INTEGER,
            qtd_pendente INTEGER,
            qtd_cancelado INTEGER,
            clicks INTEGER
        )
    ''')

    # 8. Cache de Nomes de Grupos (Substitui cache_nomes_grupos.json)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cache_nomes (
            chat_id TEXT PRIMARY KEY,
            nome TEXT
        )
    ''')

    # 9. Lixeira de Mensagens (Substitui lixeira_mensagens.json)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lixeira_mensagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_id INTEGER,
            chat_id TEXT,
            data_inclusao TEXT
        )
    ''')

    # 10. Registros Únicos para Anti-Loop (Substitui registro_hashes.json e registro_espelhos.json)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registros_unicos (
            identificador TEXT,
            contexto TEXT,
            tipo TEXT,
            data_registro TEXT,
            PRIMARY KEY (identificador, contexto)
        )
    ''')

    conexao.commit()
    conexao.close()
    
    if EXIBIR_LOGS: logger.info("✅ [Database] Todas as tabelas foram criadas e auditadas com sucesso. A fundação está pronta.")

# Se o arquivo for rodado diretamente, ele constrói as tabelas.
if __name__ == "__main__":
    inicializar_banco()

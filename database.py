"""
Script MANUAL de criação de tabelas: rode `python3 database.py` uma vez num
banco novo. Nenhum robô importa este arquivo; cada robô cria as próprias
tabelas ao iniciar (bot_mestre, utils, espelhador_videos_autorais, etc.).

É o ÚNICO lugar que cria fila_notas (painel_notas) e registros_unicos
(motor_userbot). Sem rodar este script, essas duas tabelas não existem.

fila_espiao, fila_espelhador, pedidos_financeiro e historico_financeiro
não são usadas por nenhum código: esses dados continuam guardados como JSON
(na tabela configuracoes ou em fila_espelhador.json).
"""
EXIBIR_LOGS = True
import sqlite3
import logging

if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger = logging.getLogger(__name__)

DB_NAME = "banco_dados.db"

def obter_conexao():
    """Retorna uma conexão limpa com o SQLite, configurada para ler colunas por nome."""
    # Vários robôs gravam no mesmo arquivo: espera até 20 s pelo lock em vez de falhar na hora.
    conexao = sqlite3.connect(DB_NAME, timeout=20.0)
    conexao.row_factory = sqlite3.Row
    return conexao

def inicializar_banco():
    if EXIBIR_LOGS: logger.info("🚀 [Database] Iniciando a construção e verificação das fundações do banco de dados SQLite...")
    
    conexao = obter_conexao()
    cursor = conexao.cursor()

    # Fila principal de postagens (bot_mestre). Também criada pelo próprio bot_mestre.
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

    # Chave-valor (valor em JSON) com as configurações e várias filas de todos os robôs.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    ''')

    # Não usada: a fila do Espião fica em configuracoes, chave "fila_clonagem".
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

    # Não usada: a fila do Espelhador fica no arquivo fila_espelhador.json.
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

    # Fila dos vídeos Autorais. O espelhador_videos_autorais também cria a tabela e
    # acrescenta as colunas que faltarem ao iniciar.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fila_autorais (
            id_unico TEXT PRIMARY KEY,
            msg_id_destino INTEGER,
            legenda TEXT,
            caminho_arquivo TEXT,
            data_captura TEXT,
            data_alvo TEXT,
            horario_disparo TEXT,
            processado INTEGER DEFAULT 0,
            repostado_publico INTEGER DEFAULT 0,
            data_repost_publico TEXT,
            data_postagem TEXT
        )
    ''')

    # Não usada: os pedidos ficam em configuracoes, chave "banco_pedidos".
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

    # Não usada: o histórico fica em configuracoes, chave "historico_financeiro".
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

    # Nomes de grupos/tópicos já resolvidos no Telegram. Também criada pelo utils.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cache_nomes (
            chat_id TEXT PRIMARY KEY,
            nome TEXT
        )
    ''')

    # Mensagens do bot a apagar depois. Também criada pelo bot_mestre.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lixeira_mensagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_id INTEGER,
            chat_id TEXT,
            data_inclusao TEXT
        )
    ''')

    # Anti-duplicata do motor_userbot (hashes de vídeo e mensagens já espelhadas).
    # Só é criada aqui.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registros_unicos (
            identificador TEXT,
            contexto TEXT,
            tipo TEXT,
            data_registro TEXT,
            PRIMARY KEY (identificador, contexto)
        )
    ''')

    # Fila de envio de notas fiscais por e-mail (painel_notas). Só é criada aqui.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fila_notas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_loja TEXT,
            email_destino TEXT,
            caminho_pdf TEXT,
            status TEXT DEFAULT 'PENDENTE',
            motivo_erro TEXT
        )
    ''')

    conexao.commit()
    conexao.close()
    
    if EXIBIR_LOGS: logger.info("✅ [Database] Todas as tabelas foram criadas e auditadas com sucesso. A fundação está pronta.")

if __name__ == "__main__":
    inicializar_banco()

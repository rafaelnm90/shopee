# =============================================================================
# POOL DE CONTAS — pool_contas.py
# =============================================================================
#
# LEIA-ME PARA A IA (e para o Rafael daqui a seis meses)
#
# ─── O QUE ESTE ARQUIVO É ────────────────────────────────────────────────────
# Este módulo é o "RH" das contas de usuário do Telegram (userbots Telethon) do
# ecossistema Shopee. Ele guarda, num banco SQLite, TODAS as contas que já
# fizeram login no servidor e decide, sozinho, QUAL conta exerce QUAL função no
# grupo dos Autorais a cada momento.
#
# Ele NÃO captura vídeo, NÃO reposta, NÃO agenda nada. Ele só responde a uma
# pergunta, e responde sempre a mesma coisa para quem perguntar:
#
#       "Qual conta é a responsável pela função X agora?"
#
# Quem captura/reposta é o espelhador_videos_autorais.py: ele pergunta aqui quem
# está em cada posto, conecta essas contas e, de 10 em 10 minutos, checa todas as
# contas no Telegram (sincronizar_pool) e troca as que mudaram. Sem nenhuma conta
# cadastrada, ele usa a sessão fixa antiga (sessao_espelhador_isolado).
#
# O ✅/❌ de cada conta na sua função sai de avaliar_saude(): sessão viva, conta no
# grupo e último envio sem erro (o robô registra cada envio em atividade_contas).
# O painel "Contas 👥" do bot_mestre mostra isso e o bot avisa no privado quando muda.
#
# ─── AS DUAS FUNÇÕES (POSTOS DE TRABALHO) ────────────────────────────────────
#   • "espelho" (captura) → UMA conta, que fica DENTRO do grupo dos Autorais
#                     capturando os vídeos e publicando no canal "Vídeos Autorais
#                     Afiliados" (e baixa os do Grupo Público e vigia os parceiros).
#   • "repostagem"  → RODÍZIO: todas as contas aptas, menos a da captura, devolvem
#                     os vídeos ao grupo de origem no D+X, cada vídeo por uma.
#
# A captura nunca reposta: postar no grupo dos outros é o que arrisca expulsão, e
# assim a captura fica protegida. Sem conta de repostagem, a repostagem para (os
# vídeos esperam na fila) e o bot avisa.
#
# ─── A REGRA DE REVEZAMENTO (o coração deste arquivo) ────────────────────────
# Roda em resolver_funcoes(). Exemplo com 5 contas:
#
#   1. Conta 1 captura, conta 2 reposta.
#   2. Conta 2 sai do grupo; conta 3 entra.             → a 3 entra no rodízio
#   3. Conta 4 entra depois.                            → rodízio com a 3 e a 4
#   4. Todas saem; só a conta 5 fica no grupo.          → a 5 captura e a
#                                                          repostagem fica parada
#
# Captura: quem está no posto e continua apta nunca é trocada. Posto vago vai
# primeiro para uma conta que não reposta (reserva da captura), depois pela
# coluna 'prioridade' e por quem cadastrou antes; sem reserva, uma conta do rodízio
# passa para a captura. Sem conta apta, o posto fica VAGO e a captura para (em vez
# de quebrar com sessão inválida).
#
# Para uma conta só repostar (nunca capturar), bloqueie "Captura" nela no painel;
# para só capturar, bloqueie "Repostagem".
#
# ─── OS ESTADOS QUE UMA CONTA PODE TER ───────────────────────────────────────
# Duas dimensões independentes, propositalmente separadas:
#
#   status_grupo   → a relação da conta com o grupo dos Autorais
#       NO_GRUPO        está dentro, pode trabalhar
#       SAIU_DO_GRUPO   já esteve dentro e não está mais
#       NUNCA_ENTROU    logou no servidor mas nunca pisou no grupo
#       BANIDA_NO_GRUPO foi banida/restrita pelos administradores DO GRUPO
#       DESCONHECIDO     ainda não foi checada nenhuma vez
#
#   status_sessao  → a saúde da conta no Telegram, independente de grupo
#       OK              sessão viva, autenticada
#       SESSAO_MORTA    a sessão foi revogada (logout em outro aparelho, etc.)
#       CONTA_BANIDA    a conta foi banida/desativada PELO TELEGRAM
#
# Só trabalha quem tem status_sessao=OK **e** status_grupo=NO_GRUPO **e**
# habilitada=1 **e** a função na lista de funcoes_permitidas.
#
# ─── ONDE FICAM OS DADOS SENSÍVEIS ───────────────────────────────────────────
# O repositório é PÚBLICO. Nada sensível pode entrar nele. O desenho é:
#
#   • O arquivo .py (este aqui) é público e NÃO contém segredo nenhum.
#   • As credenciais moram no banco_dados.db, que já está no .gitignore.
#   • Dentro do banco, a sessão e a senha de 2FA ficam CIFRADAS com Fernet
#     (AES-128-CBC + HMAC), nunca em texto puro. Quem abrir o .db sem a chave
#     vê só um bloco de bytes.
#   • A chave vem de uma senha-mestra no .env (CHAVE_MESTRA_CONTAS). Se ela não
#     existir, o módulo usa o API_HASH — que já é secreto, já está no .env e já
#     é copiado pelo backup diário (backup_dados.py). Assim nunca há um
#     "esqueci de configurar e tudo parou".
#   • O sal do PBKDF2 mora na tabela 'configuracoes' do próprio banco. Ou seja:
#     .env + banco_dados.db = tudo funcionando. É exatamente o par que o
#     backup diário já empacota.
#
# ─── TROCAR DE SERVIDOR SEM REFAZER LOGIN ────────────────────────────────────
# O que é guardado não é o arquivo .session (que é preso a caminho de disco),
# e sim a StringSession — que é portátil. Então:
#
#   Caminho A (o normal): copie banco_dados.db e .env para o servidor novo.
#                         Pronto. Nenhum SMS, nenhum código, nada.
#   Caminho B (o cofre):  python3 pool_contas.py exportar cofre.bin
#                         → gera UM arquivo cifrado com uma senha que você
#                           digita na hora, independente do .env.
#                         python3 pool_contas.py importar cofre.bin
#                         → restaura tudo no servidor novo.
#
# ─── COMO OS OUTROS ARQUIVOS DEVEM USAR ESTE MÓDULO ──────────────────────────
#     import pool_contas
#
#     # quem está de plantão?
#     conta = pool_contas.obter_conta_da_funcao("espelho")
#
#     # cliente Telethon já montado e conectado com a sessão certa
#     cliente = await pool_contas.criar_cliente_da_funcao("espelho")
#
#     # as contas do rodízio da repostagem
#     contas = pool_contas.obter_contas_repostagem()
#
#     # rotina periódica (o robô dos Autorais roda de 10 em 10 minutos, passando
#     # os clientes que já tem conectados; o painel também tem o botão)
#     await pool_contas.sincronizar_pool(clientes={conta_id: cliente})
#
#     # resultado de cada envio, para o ✅/❌ do relatório
#     pool_contas.registrar_atividade(conta_id, "repostagem", ok=True)
#
# ─── LINHA DE COMANDO ────────────────────────────────────────────────────────
#     python3 pool_contas.py login             # loga uma conta nova e cadastra
#                                              # (ou pelo bot: Contas 👥 › Cadastrar Conta ➕)
#     python3 pool_contas.py listar            # a tabela de todas as contas
#     python3 pool_contas.py sincronizar       # checa todo mundo e redistribui
#     python3 pool_contas.py importar-sessoes  # adota os .session já existentes
#     python3 pool_contas.py identificar       # lê telefone/id/@ de cada sessão
#     python3 pool_contas.py senha <apelido>   # guarda a senha de 2 etapas
#     python3 pool_contas.py credenciais       # mostra tudo o que está guardado
#     python3 pool_contas.py entrar <apelido>  # entra no grupo por link convite
#     python3 pool_contas.py permitir <apelido> espelho,repostagem
#     python3 pool_contas.py desabilitar <apelido>
#     python3 pool_contas.py habilitar <apelido>
#     python3 pool_contas.py remover <apelido>
#     python3 pool_contas.py exportar <arquivo>
#     python3 pool_contas.py importar <arquivo>
#
# ─── O QUE ESTE ARQUIVO NÃO FAZ (de propósito) ───────────────────────────────
#   • Não entra em grupo sozinho sem o link estar configurado.
#   • Não cria conta de Telegram, não resolve captcha, não burla nada.
#   • Não mexe em nenhuma tabela além das quatro dele (contas_telegram,
#     funcoes_contas, historico_contas, atividade_contas) e de duas chaves da
#     'configuracoes' (o sal da criptografia e o link de convite).
#   • Não reinicia serviço. Trocou o plantonista? Ele grava no banco e avisa no
#     log; quem lê o plantão é o serviço, na próxima vez que precisar.
#
# =============================================================================


import os
import sys
import json
import base64
import sqlite3
import db
import logging
import asyncio
import getpass
import re
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

# Importar fuso já trava o processo no horário de Brasília; sem o fuso.py, segue
# com o fuso e o log padrão.
try:
    from fuso import fuso_horario, configurar_logs
    logger = configurar_logs(__name__)
except Exception:  # pragma: no cover - só acontece fora do servidor
    from zoneinfo import ZoneInfo
    fuso_horario = ZoneInfo("America/Sao_Paulo")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    logger = logging.getLogger(__name__)


# =============================================================================
# 1. CONSTANTES
# =============================================================================

# Os dois postos de trabalho. A ordem importa: quando os dois estão vagos e só
# existe uma conta apta, o primeiro da lista é atribuído primeiro.
FUNCAO_ESPELHO = "espelho"
FUNCAO_REPOSTAGEM = "repostagem"
FUNCOES = (FUNCAO_ESPELHO, FUNCAO_REPOSTAGEM)

# Estados da relação com o grupo dos Autorais.
STATUS_NO_GRUPO = "NO_GRUPO"
STATUS_SAIU = "SAIU_DO_GRUPO"
STATUS_NUNCA_ENTROU = "NUNCA_ENTROU"
STATUS_BANIDA_GRUPO = "BANIDA_NO_GRUPO"
STATUS_DESCONHECIDO = "DESCONHECIDO"

# Estados de saúde da própria conta no Telegram.
SESSAO_OK = "OK"
SESSAO_MORTA = "SESSAO_MORTA"
SESSAO_CONTA_BANIDA = "CONTA_BANIDA"

# Emojis usados na listagem, só para o olho bater rápido no terminal.
ICONES_GRUPO = {
    STATUS_NO_GRUPO: "✅",
    STATUS_SAIU: "🚪",
    STATUS_NUNCA_ENTROU: "⚪",
    STATUS_BANIDA_GRUPO: "⛔",
    STATUS_DESCONHECIDO: "❓",
}

API_ID = int(os.getenv("API_ID", 0) or 0)
API_HASH = os.getenv("API_HASH", "") or ""

# Chave do sal no dicionário 'configuracoes' (tabela que já existe no projeto).
CHAVE_SAL = "pool_contas_sal"
# Chave onde guardamos o link de convite do grupo dos Autorais (opcional).
CHAVE_CONVITE = "pool_contas_convite_autorais"


# =============================================================================
# 2. CRIPTOGRAFIA DAS CREDENCIAIS
# =============================================================================
# Regra de ouro deste bloco: texto puro NUNCA toca o disco. A StringSession e a
# senha de 2FA entram cifradas no banco e só são abertas dentro da memória, no
# instante de montar o cliente Telethon.

def _obter_conexao():
    """Conexão ao banco principal que devolve linhas acessíveis por nome de coluna."""
    return db.conectar(linhas_por_nome=True)


def _obter_sal():
    """
    Lê (ou cria na primeira vez) o sal do PBKDF2 na tabela 'configuracoes'.

    Por que o sal fica no BANCO e não no .env? Porque ele não é segredo — é só
    um valor único por instalação, para impedir tabelas pré-computadas. Deixando
    ele no banco, o par que precisa viajar junto continua sendo só
    (.env + banco_dados.db).
    """
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)"
    )
    cursor.execute("SELECT valor FROM configuracoes WHERE chave = ?", (CHAVE_SAL,))
    linha = cursor.fetchone()
    if linha and linha["valor"]:
        conexao.close()
        return base64.b64decode(linha["valor"])

    sal = os.urandom(16)
    cursor.execute(
        "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
        (CHAVE_SAL, base64.b64encode(sal).decode()),
    )
    conexao.commit()
    conexao.close()
    logger.info("🧂 [Pool] Sal criptográfico criado pela primeira vez neste banco.")
    return sal


def _derivar_chave(senha, sal):
    """Transforma uma senha em texto numa chave Fernet de 32 bytes via PBKDF2."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=sal,
        iterations=390000,
    )
    return base64.urlsafe_b64encode(kdf.derive(senha.encode("utf-8")))


def _chaves_disponiveis():
    """
    Devolve a lista de chaves a tentar, na ordem de preferência.

    [0] = a chave "oficial" (usada para CIFRAR de agora em diante)
    [1:] = chaves legadas, só para CONSEGUIR ABRIR o que já estava salvo

    Isso resolve o caso chato: se um dia o Rafael criar a CHAVE_MESTRA_CONTAS
    depois de já ter cadastrado contas com o API_HASH, nada quebra — o módulo
    abre com a antiga e regrava com a nova sozinho.
    """
    sal = _obter_sal()
    senhas = []

    mestra = os.getenv("CHAVE_MESTRA_CONTAS", "").strip()
    if mestra:
        senhas.append(mestra)
    if API_HASH:
        senhas.append(API_HASH)

    if not senhas:
        raise RuntimeError(
            "Nenhuma chave disponível para cifrar as contas. "
            "Defina CHAVE_MESTRA_CONTAS (ou pelo menos API_HASH) no .env."
        )
    return [_derivar_chave(s, sal) for s in senhas]


def cifrar(texto):
    """Cifra uma string e devolve bytes prontos para gravar no SQLite (BLOB)."""
    from cryptography.fernet import Fernet

    if texto is None or texto == "":
        return None
    chave = _chaves_disponiveis()[0]
    return Fernet(chave).encrypt(texto.encode("utf-8"))


def decifrar(blob):
    """
    Abre um BLOB cifrado. Tenta todas as chaves conhecidas antes de desistir.
    Devolve None se o campo estiver vazio ou se nenhuma chave servir.
    """
    from cryptography.fernet import Fernet, InvalidToken

    if not blob:
        return None
    for chave in _chaves_disponiveis():
        try:
            return Fernet(chave).decrypt(blob).decode("utf-8")
        except InvalidToken:
            continue
        except Exception:
            continue
    logger.error(
        "❌ [Pool] Não consegui decifrar uma credencial. "
        "A CHAVE_MESTRA_CONTAS/API_HASH do .env mudou desde o cadastro?"
    )
    return None


# =============================================================================
# 3. ESTRUTURA DO BANCO
# =============================================================================
# Três tabelas novas, isoladas. Nenhuma tabela existente é tocada (a única
# exceção é a leitura/escrita de duas chaves em 'configuracoes', que já é o
# dicionário global do projeto).

# Trava de sessão: as funções de leitura chamam inicializar_tabelas() por
# segurança, e sem esta flag o journalctl levaria uma linha repetida a cada
# consulta. O CREATE TABLE IF NOT EXISTS continua barato; só o log é que some.
_TABELAS_PRONTAS = False


def inicializar_tabelas():
    """Cria as tabelas do pool. Seguro chamar quantas vezes quiser."""
    global _TABELAS_PRONTAS
    conexao = _obter_conexao()
    cursor = conexao.cursor()

    # 1) O cadastro das contas.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contas_telegram (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apelido TEXT UNIQUE NOT NULL,
            telefone TEXT,
            user_id INTEGER,
            username TEXT,
            nome_exibicao TEXT,
            sessao_cifrada BLOB,
            senha_2fa_cifrada BLOB,
            status_grupo TEXT DEFAULT 'DESCONHECIDO',
            status_sessao TEXT DEFAULT 'OK',
            ja_esteve_no_grupo INTEGER DEFAULT 0,
            funcoes_permitidas TEXT DEFAULT 'espelho,repostagem',
            prioridade INTEGER DEFAULT 100,
            habilitada INTEGER DEFAULT 1,
            ultima_checagem TEXT,
            ultimo_erro TEXT,
            criada_em TEXT,
            atualizada_em TEXT
        )
    ''')

    # 2) Quem está de plantão em cada posto. Uma linha por função, sempre.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS funcoes_contas (
            funcao TEXT PRIMARY KEY,
            conta_id INTEGER,
            assumida_em TEXT,
            motivo TEXT
        )
    ''')

    # 3) Diário de bordo. Serve para responder "por que a conta X parou de
    #    postar dia tal?" sem depender do journalctl, que rotaciona.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico_contas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            apelido TEXT,
            evento TEXT,
            detalhe TEXT
        )
    ''')

    # 4) O que cada conta fez em cada função: última ação ok e último erro. É daqui
    #    que sai o ✅/❌ do relatório ("a conta está funcionando na função dela?").
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS atividade_contas (
            conta_id INTEGER,
            funcao TEXT,
            ultimo_ok TEXT,
            ultimo_erro TEXT,
            erro_em TEXT,
            total_ok INTEGER DEFAULT 0,
            PRIMARY KEY (conta_id, funcao)
        )
    ''')

    # A repostagem é um rodízio: a linha dela guarda a lista inteira em contas_ids
    # (conta_id fica com a primeira, para quem ainda lê um plantonista só).
    try:
        cursor.execute("ALTER TABLE funcoes_contas ADD COLUMN contas_ids TEXT")
    except sqlite3.OperationalError:
        pass  # coluna já existe

    # A conta da captura é quem publica no canal de destino: 1 = pode publicar,
    # 0 = não pode (não é admin), NULL = ainda não conferido.
    try:
        cursor.execute("ALTER TABLE contas_telegram ADD COLUMN publica_no_destino INTEGER")
    except sqlite3.OperationalError:
        pass  # coluna já existe

    # Garante que as duas linhas de função existem desde o começo (vagas).
    for funcao in FUNCOES:
        cursor.execute(
            "INSERT OR IGNORE INTO funcoes_contas (funcao, conta_id, assumida_em, motivo) "
            "VALUES (?, NULL, NULL, 'posto criado vago')",
            (funcao,),
        )

    conexao.commit()
    conexao.close()
    if not _TABELAS_PRONTAS:
        logger.info("👥 [Pool] Tabelas de contas verificadas.")
    _TABELAS_PRONTAS = True


def _agora():
    return datetime.now(fuso_horario).strftime("%Y-%m-%d %H:%M:%S")


def registrar_evento(apelido, evento, detalhe=""):
    """Grava uma linha no diário de bordo e espelha no log."""
    try:
        conexao = _obter_conexao()
        cursor = conexao.cursor()
        cursor.execute(
            "INSERT INTO historico_contas (data, apelido, evento, detalhe) VALUES (?, ?, ?, ?)",
            (_agora(), apelido, evento, detalhe),
        )
        conexao.commit()
        conexao.close()
    except Exception as e:
        logger.error(f"❌ [Pool] Falha ao gravar histórico: {e}")
    logger.info(f"📒 [Pool] {apelido}: {evento} {('— ' + detalhe) if detalhe else ''}")


# =============================================================================
# 4. CADASTRO DE CONTAS (leitura e escrita)
# =============================================================================

def listar_contas(somente_habilitadas=False):
    """Devolve todas as contas como lista de dicionários."""
    inicializar_tabelas()
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    sql = "SELECT * FROM contas_telegram"
    if somente_habilitadas:
        sql += " WHERE habilitada = 1"
    sql += " ORDER BY prioridade ASC, id ASC"
    cursor.execute(sql)
    linhas = [dict(l) for l in cursor.fetchall()]
    conexao.close()
    return linhas


def obter_conta(apelido):
    """Busca uma conta pelo apelido (aceita também o id numérico em texto)."""
    inicializar_tabelas()
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    cursor.execute("SELECT * FROM contas_telegram WHERE apelido = ?", (str(apelido),))
    linha = cursor.fetchone()
    if not linha and str(apelido).isdigit():
        cursor.execute("SELECT * FROM contas_telegram WHERE id = ?", (int(apelido),))
        linha = cursor.fetchone()
    conexao.close()
    return dict(linha) if linha else None


def salvar_conta(apelido, sessao=None, telefone=None, user_id=None, username=None,
                 nome_exibicao=None, senha_2fa=None, funcoes_permitidas=None,
                 prioridade=None):
    """
    Cria ou atualiza uma conta. Só sobrescreve os campos que forem informados —
    passar None significa "não mexe nesse campo".

    'sessao' e 'senha_2fa' entram em texto puro e saem cifrados daqui.
    """
    inicializar_tabelas()
    conexao = _obter_conexao()
    cursor = conexao.cursor()

    cursor.execute("SELECT id FROM contas_telegram WHERE apelido = ?", (apelido,))
    existente = cursor.fetchone()

    if not existente:
        cursor.execute(
            "INSERT INTO contas_telegram (apelido, criada_em, atualizada_em) VALUES (?, ?, ?)",
            (apelido, _agora(), _agora()),
        )
        conexao.commit()

    campos = []
    valores = []

    if sessao is not None:
        campos.append("sessao_cifrada = ?")
        valores.append(cifrar(sessao))
    if senha_2fa is not None:
        campos.append("senha_2fa_cifrada = ?")
        valores.append(cifrar(senha_2fa))
    if telefone is not None:
        campos.append("telefone = ?")
        valores.append(telefone)
    if user_id is not None:
        campos.append("user_id = ?")
        valores.append(user_id)
    if username is not None:
        campos.append("username = ?")
        valores.append(username)
    if nome_exibicao is not None:
        campos.append("nome_exibicao = ?")
        valores.append(nome_exibicao)
    if funcoes_permitidas is not None:
        campos.append("funcoes_permitidas = ?")
        valores.append(funcoes_permitidas)
    if prioridade is not None:
        campos.append("prioridade = ?")
        valores.append(int(prioridade))

    campos.append("atualizada_em = ?")
    valores.append(_agora())
    valores.append(apelido)

    cursor.execute(
        f"UPDATE contas_telegram SET {', '.join(campos)} WHERE apelido = ?",
        valores,
    )
    conexao.commit()
    conexao.close()

    if not existente:
        registrar_evento(apelido, "CADASTRADA", f"user_id={user_id} telefone={telefone}")
    return obter_conta(apelido)


def atualizar_status(apelido, status_grupo=None, status_sessao=None, erro=None):
    """Grava o resultado de uma checagem. Só registra evento quando algo muda."""
    conta = obter_conta(apelido)
    if not conta:
        return None

    conexao = _obter_conexao()
    cursor = conexao.cursor()
    campos = ["ultima_checagem = ?"]
    valores = [_agora()]

    if status_grupo is not None:
        campos.append("status_grupo = ?")
        valores.append(status_grupo)
        # Memória de "já esteve dentro": é o que diferencia NUNCA_ENTROU de SAIU.
        if status_grupo == STATUS_NO_GRUPO:
            campos.append("ja_esteve_no_grupo = 1")
    if status_sessao is not None:
        campos.append("status_sessao = ?")
        valores.append(status_sessao)

    campos.append("ultimo_erro = ?")
    valores.append(erro or "")
    valores.append(apelido)

    cursor.execute(
        f"UPDATE contas_telegram SET {', '.join(campos)} WHERE apelido = ?",
        valores,
    )
    conexao.commit()
    conexao.close()

    if status_grupo and status_grupo != conta.get("status_grupo"):
        registrar_evento(apelido, "STATUS_GRUPO",
                         f"{conta.get('status_grupo')} → {status_grupo}")
    if status_sessao and status_sessao != conta.get("status_sessao"):
        registrar_evento(apelido, "STATUS_SESSAO",
                         f"{conta.get('status_sessao')} → {status_sessao}")
    return obter_conta(apelido)


def definir_habilitada(apelido, ligada):
    """Liga/desliga uma conta manualmente, sem apagar nada."""
    inicializar_tabelas()
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    cursor.execute(
        "UPDATE contas_telegram SET habilitada = ?, atualizada_em = ? WHERE apelido = ?",
        (1 if ligada else 0, _agora(), apelido),
    )
    conexao.commit()
    conexao.close()
    registrar_evento(apelido, "HABILITADA" if ligada else "DESABILITADA", "ação manual")


def remover_conta(apelido):
    """Apaga a conta do cadastro. O plantão dela é redistribuído na sequência."""
    inicializar_tabelas()
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    cursor.execute("SELECT id FROM contas_telegram WHERE apelido = ?", (apelido,))
    linha = cursor.fetchone()
    if linha:
        cursor.execute("UPDATE funcoes_contas SET conta_id = NULL, motivo = 'conta removida' "
                       "WHERE conta_id = ?", (linha["id"],))
    cursor.execute("DELETE FROM contas_telegram WHERE apelido = ?", (apelido,))
    conexao.commit()
    conexao.close()
    registrar_evento(apelido, "REMOVIDA", "ação manual")


# =============================================================================
# 4B. CREDENCIAIS — o que dá e o que NÃO dá para descobrir sozinho
# =============================================================================
#
# LEIA ISTO ANTES DE ESPERAR MÁGICA DESTE BLOCO.
#
# O Telegram NÃO tem login e senha no sentido clássico. O que existe é:
#
#   • TELEFONE  → é o "login". Dá para ler da sessão. ✅ automático
#   • USER ID   → dá para ler da sessão.              ✅ automático
#   • @USERNAME → dá para ler da sessão.              ✅ automático
#   • NOME      → dá para ler da sessão.              ✅ automático
#   • CÓDIGO SMS → é descartável, vale uma vez só.    ❌ não existe guardar
#   • SENHA DE 2 ETAPAS → ❌ IMPOSSÍVEL recuperar.
#
# Por que a senha de 2 etapas é impossível: o Telegram usa SRP. A senha em texto
# NUNCA sai do seu aparelho — nem para o servidor do Telegram. O que trafega é
# uma prova matemática de que você sabe a senha. O servidor guarda só um
# verificador, que não dá para reverter. O arquivo .session guarda a auth_key
# (a credencial já autenticada), e não a senha.
#
# Conclusão prática: telefone, id, @ e nome o pool preenche sozinho com
# 'identificar'. A senha de 2 etapas, se a conta tiver uma, você digita UMA vez
# com 'senha <apelido>' e a partir dali ela fica guardada cifrada aqui, junto
# com o resto — e viaja com você na troca de servidor.

async def identificar_contas():
    """
    Passa em todas as contas cadastradas, conecta com a sessão guardada e
    preenche telefone, user_id, @username e nome na tabela.

    É o "reconhecer quais são os logins". Não pede nada a você: usa a sessão
    que já está no banco. Rode depois do 'importar-sessoes'.
    """
    inicializar_tabelas()
    contas = listar_contas()
    if not contas:
        print("⚠️ Nenhuma conta cadastrada. Rode antes: python3 pool_contas.py importar-sessoes")
        return 0

    achadas = 0
    for conta in contas:
        apelido = conta["apelido"]
        cliente = None
        try:
            cliente = await criar_cliente(conta)
            if cliente is None:
                print(f"❌ {apelido}: sessão inválida ou não autorizada.")
                continue
            eu = await cliente.get_me()
            nome = " ".join(filter(None, [eu.first_name, eu.last_name])).strip()
            telefone = getattr(eu, "phone", None)
            if telefone and not str(telefone).startswith("+"):
                telefone = "+" + str(telefone)
            salvar_conta(apelido, user_id=eu.id, username=eu.username or "",
                         nome_exibicao=nome or apelido, telefone=telefone)
            print(f"✅ {apelido}")
            print(f"     telefone (login): {telefone or 'não exposto por esta sessão'}")
            print(f"     user id:          {eu.id}")
            print(f"     username:         {('@' + eu.username) if eu.username else 'sem @'}")
            print(f"     nome:             {nome or '—'}")
            tem_senha = bool(conta.get("senha_2fa_cifrada"))
            print(f"     senha 2 etapas:   {'guardada ✅' if tem_senha else 'NÃO guardada — use o comando senha'}")
            achadas += 1
        except Exception as e:
            print(f"❌ {apelido}: {type(e).__name__}: {e}")
        finally:
            if cliente is not None:
                try:
                    await cliente.disconnect()
                except Exception:
                    pass
        await asyncio.sleep(1)

    print(f"\n📋 {achadas} conta(s) identificadas e gravadas na tabela.")
    return achadas


def definir_senha_2fa(apelido):
    """
    Guarda a senha da verificação em duas etapas de uma conta já cadastrada.

    Digitada uma vez, cifrada no banco, nunca mais precisa ser lembrada. Se a
    conta não tiver 2FA, simplesmente não use este comando.

    A digitação usa getpass: não aparece na tela nem fica no histórico do bash.
    """
    conta = obter_conta(apelido)
    if not conta:
        print(f"❌ Conta '{apelido}' não encontrada.")
        return False
    senha = getpass.getpass(f"🔐 Senha de 2 etapas de '{apelido}' (vazio para apagar): ")
    if senha == "":
        conexao = _obter_conexao()
        cursor = conexao.cursor()
        cursor.execute("UPDATE contas_telegram SET senha_2fa_cifrada = NULL WHERE apelido = ?",
                       (apelido,))
        conexao.commit()
        conexao.close()
        registrar_evento(apelido, "SENHA_2FA_REMOVIDA", "")
        print("🗑️ Senha removida do cofre.")
        return True
    confirma = getpass.getpass("🔐 Repita para conferir: ")
    if senha != confirma:
        print("❌ As duas digitações não bateram. Nada foi salvo.")
        return False
    salvar_conta(apelido, senha_2fa=senha)
    registrar_evento(apelido, "SENHA_2FA_GUARDADA", "cifrada no banco")
    print(f"✅ Senha de '{apelido}' guardada cifrada.")
    return True


def mostrar_credenciais(apelido=None):
    """
    Mostra na tela as credenciais guardadas, já decifradas.

    ⚠️ Isto imprime senha em texto puro no terminal. Use só quando precisar
    mesmo, e nunca com a tela compartilhada. A sessão sai truncada de propósito
    (ela é gigante e não serve para digitar em lugar nenhum).
    """
    contas = [obter_conta(apelido)] if apelido else listar_contas()
    contas = [c for c in contas if c]
    if not contas:
        print("⚠️ Nenhuma conta encontrada.")
        return

    print("\n" + "=" * 60)
    print("🔐 CREDENCIAIS GUARDADAS  —  não compartilhe esta tela")
    print("=" * 60)
    for c in contas:
        senha = decifrar(c.get("senha_2fa_cifrada"))
        sessao = decifrar(c.get("sessao_cifrada"))
        print(f"\n👤 {c['apelido']}")
        print(f"   telefone (login):  {c['telefone'] or '— rode identificar'}")
        print(f"   user id:           {c['user_id'] or '—'}")
        print(f"   username:          {('@' + c['username']) if c['username'] else 'sem @'}")
        print(f"   nome:              {c['nome_exibicao'] or '—'}")
        print(f"   senha 2 etapas:    {senha if senha else '— não guardada'}")
        if sessao:
            print(f"   sessão (cifrada no banco): {sessao[:24]}... [{len(sessao)} caracteres]")
        else:
            print("   sessão:            — ausente")
    print("\n" + "=" * 60)


# =============================================================================
# 4C. AÇÕES USADAS PELO PAINEL DO TELEGRAM
# =============================================================================
# Estas três funções existem para o botão "Contas e Postos" do bot_mestre.
# Ficam aqui, e não lá, para o painel ser só tela: toda a regra mora neste
# arquivo. Se um dia o painel mudar, a regra continua a mesma.

def alternar_funcao_permitida(apelido, funcao):
    """
    Liga/desliga a permissão de uma conta exercer uma função.

    É esta a ação de "tirar o usuário do posto" de verdade: desligar a permissão
    faz ele sair do posto E impede que o revezamento o coloque de volta na
    próxima sincronização. Só vagar o posto não adiantaria — o motor recolocaria
    a mesma conta em dois segundos, por ela continuar sendo a melhor candidata.

    Devolve (permitida_agora, lista_de_mudancas_de_posto).
    """
    conta = obter_conta(apelido)
    if not conta:
        return (None, [])

    atuais = [f.strip() for f in str(conta.get("funcoes_permitidas") or "").split(",") if f.strip()]
    if funcao in atuais:
        atuais.remove(funcao)
        ligada = False
    else:
        atuais.append(funcao)
        ligada = True

    salvar_conta(apelido, funcoes_permitidas=",".join(atuais) if atuais else "nenhuma")
    registrar_evento(apelido, "PERMISSAO_ALTERADA",
                     f"{funcao} {'liberada' if ligada else 'bloqueada'} (painel)")
    return (ligada, aplicar_funcoes())


# Papéis que o painel oferece, em vez de ligar e desligar cada função. São só dois:
# várias contas na repostagem já são reserva umas das outras. Decisão do Rafael:
# DECISOES.md, Vídeos Autorais e contas do pool.
PAPEL_CAPTURA = "captura"        # pega do grupo de origem e publica no canal; nunca reposta
PAPEL_REPOSTAGEM = "repostagem"  # só reveza na devolução ao grupo; nunca assume a captura
# Conta antiga com as duas funções ligadas: continua valendo até o Rafael escolher.
PAPEL_AMBAS = "ambas"
FUNCOES_DO_PAPEL = {
    PAPEL_CAPTURA: FUNCAO_ESPELHO,
    PAPEL_REPOSTAGEM: FUNCAO_REPOSTAGEM,
}
ROTULOS_PAPEL = {
    PAPEL_CAPTURA: "🎯 Captura e publicação no seu canal",
    PAPEL_REPOSTAGEM: "🔁 Repostagem no grupo de origem",
    PAPEL_AMBAS: "🔀 captura ou repostagem (escolha uma)",
}


def papel_da_conta(conta):
    """O papel que as funções permitidas da conta formam (None: nenhuma)."""
    permitidas = {f.strip() for f in str(conta.get("funcoes_permitidas") or "").split(",")}
    if FUNCAO_ESPELHO in permitidas and FUNCAO_REPOSTAGEM in permitidas:
        return PAPEL_AMBAS
    if FUNCAO_ESPELHO in permitidas:
        return PAPEL_CAPTURA
    if FUNCAO_REPOSTAGEM in permitidas:
        return PAPEL_REPOSTAGEM
    return None


def definir_papel(apelido, papel):
    """
    Grava as funções do papel e redistribui os postos. Na captura, a conta assume
    o posto agora se já estiver apta (senão assume sozinha quando ficar).
    Devolve (ok, mensagem, mudanças).
    """
    conta = obter_conta(apelido)
    if not conta or papel not in FUNCOES_DO_PAPEL:
        return (False, "conta ou papel não encontrado", [])
    salvar_conta(apelido, funcoes_permitidas=FUNCOES_DO_PAPEL[papel])
    registrar_evento(apelido, "PAPEL", f"{papel} (escolhido no painel)")
    if papel == PAPEL_CAPTURA:
        ok, motivo = atribuir_funcao(apelido, FUNCAO_ESPELHO)
        if ok:
            return (True, "assumiu a captura", [])
        return (True, f"assume a captura assim que puder ({motivo})", aplicar_funcoes())
    return (True, "entra no revezamento da repostagem assim que puder", aplicar_funcoes())


def atribuir_funcao(apelido, funcao):
    """
    Coloca uma conta específica no posto AGORA, na marra.

    Só funciona se a conta estiver apta (no grupo, sessão viva, habilitada e com
    a função permitida) — caso contrário devolve o motivo da recusa. A escolha
    se mantém sozinha: o revezamento nunca tira quem está no posto e continua
    apto, então a atribuição manual dura até a conta sair do grupo ou você
    mudar de ideia.

    Devolve (True, "") ou (False, "motivo").
    """
    conta = obter_conta(apelido)
    if not conta:
        return (False, "conta não encontrada")
    if funcao not in FUNCOES:
        return (False, f"função '{funcao}' não existe")
    if not conta_apta(conta, funcao):
        return (False, _motivo_inaptidao(conta, funcao))

    if funcao == FUNCAO_REPOSTAGEM:
        # Na repostagem não há titular: toda conta apta já está no rodízio. A única
        # que fica fora é a da captura, de propósito.
        if ler_ocupacao().get(FUNCAO_ESPELHO) == conta["id"]:
            return (False, "é a conta da captura, que não reposta")
        aplicar_funcoes()
        return (True, "")

    anterior = obter_conta_da_funcao(funcao)
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    cursor.execute(
        "UPDATE funcoes_contas SET conta_id = ?, assumida_em = ?, motivo = ? WHERE funcao = ?",
        (conta["id"], _agora(), "atribuição manual pelo painel", funcao),
    )
    conexao.commit()
    conexao.close()
    registrar_evento(apelido, f"FUNCAO_{funcao.upper()}",
                     f"{anterior['apelido'] if anterior else '—'} → {apelido} (manual)")

    # Se a conta anterior perdeu o posto e havia outro posto vago, o motor
    # aproveita para reacomodar todo mundo.
    aplicar_funcoes()
    return (True, "")


# =============================================================================
# ATIVIDADE E SAÚDE: "a conta está funcionando na função dela?"
# =============================================================================
# Quem trabalha (o robô dos Autorais) registra cada envio aqui: ok ou erro. O
# relatório e os avisos do bot_mestre só leem. Uma conta está ✅ quando a sessão
# está viva, ela está no grupo e o último envio da função não falhou.

# Sem checagem há mais que isto, o robô dos Autorais provavelmente está parado
# (ele checa as contas de 10 em 10 minutos).
MINUTOS_CHECAGEM_ATRASADA = 30

ROTULOS_FUNCAO = {FUNCAO_ESPELHO: "🪞 Captura", FUNCAO_REPOSTAGEM: "♻️ Repostagem"}


def registrar_atividade(conta_id, funcao, ok, detalhe=""):
    """Grava o resultado de um envio da conta na função (ok ou erro com o motivo)."""
    if not conta_id:
        return
    try:
        inicializar_tabelas()
        conexao = _obter_conexao()
        cursor = conexao.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO atividade_contas (conta_id, funcao, total_ok) VALUES (?, ?, 0)",
            (conta_id, funcao),
        )
        if ok:
            cursor.execute(
                "UPDATE atividade_contas SET ultimo_ok = ?, total_ok = total_ok + 1 "
                "WHERE conta_id = ? AND funcao = ?",
                (_agora(), conta_id, funcao),
            )
        else:
            cursor.execute(
                "UPDATE atividade_contas SET ultimo_erro = ?, erro_em = ? "
                "WHERE conta_id = ? AND funcao = ?",
                (str(detalhe)[:200], _agora(), conta_id, funcao),
            )
        conexao.commit()
        conexao.close()
    except Exception as e:
        logger.error(f"❌ [Pool] Falha ao registrar atividade: {e}")


def ler_atividade():
    """{(conta_id, funcao): {ultimo_ok, ultimo_erro, erro_em, total_ok}}"""
    inicializar_tabelas()
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    cursor.execute("SELECT * FROM atividade_contas")
    dados = {(linha["conta_id"], linha["funcao"]): dict(linha) for linha in cursor.fetchall()}
    conexao.close()
    return dados


def _tempo_legivel(minutos):
    """12 → 'há 12 min'; 150 → 'há 2 h'; 3000 → 'há 2 dias'."""
    if minutos < 120:
        return f"há {minutos} min"
    if minutos < 48 * 60:
        return f"há {minutos // 60} h"
    return f"há {minutos // (24 * 60)} dias"


def _data_curta(texto):
    """'2026-10-03 14:32:10' → '03/10 14:32'."""
    try:
        return datetime.strptime(texto, "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return texto or "?"


def avaliar_saude(contas, ocupacao, atividade, agora=None):
    """
    Estado de cada posto, sem tocar em banco nem rede (testável no autoteste).

    Devolve {"postos": [...], "checagem_atrasada_min": int|None}. Cada item de
    postos: {"chave", "funcao", "conta_id", "apelido", "ok", "motivo"}; conta_id
    None é o posto sem ninguém (captura vaga ou rodízio vazio).
    """
    if agora is None:
        agora = datetime.now(fuso_horario).replace(tzinfo=None)
    por_id = {c["id"]: c for c in contas}
    postos = []

    def avaliar(funcao, conta):
        reg = atividade.get((conta["id"], funcao)) or {}
        ultimo_ok, erro_em = reg.get("ultimo_ok"), reg.get("erro_em")
        if conta.get("status_sessao") != SESSAO_OK:
            return False, _motivo_inaptidao(conta, funcao)
        if conta.get("status_grupo") != STATUS_NO_GRUPO or not conta.get("habilitada", 1):
            return False, _motivo_inaptidao(conta, funcao)
        if funcao == FUNCAO_ESPELHO and conta.get("publica_no_destino") == 0:
            return False, "não é admin do seu canal: não consegue publicar os vídeos"
        if erro_em and (not ultimo_ok or erro_em > ultimo_ok):
            return False, f"último envio falhou ({_data_curta(erro_em)}): {reg.get('ultimo_erro') or '?'}"
        if ultimo_ok:
            return True, f"último envio ok {_data_curta(ultimo_ok)}"
        return True, "sem envio ainda"

    trabalhando = [(FUNCAO_ESPELHO, i) for i in _lista_ids(ocupacao.get(FUNCAO_ESPELHO))]
    trabalhando += [(FUNCAO_REPOSTAGEM, i) for i in _lista_ids(ocupacao.get(FUNCAO_REPOSTAGEM))]
    for funcao, conta_id in trabalhando:
        conta = por_id.get(conta_id)
        if conta is None:
            continue
        ok, motivo = avaliar(funcao, conta)
        postos.append({"chave": f"{funcao}:{conta_id}", "funcao": funcao, "conta_id": conta_id,
                       "apelido": conta["apelido"], "ok": ok, "motivo": motivo})

    for funcao, vazio in ((FUNCAO_ESPELHO, "nenhuma conta apta: a captura está parada"),
                          (FUNCAO_REPOSTAGEM, "nenhuma conta no rodízio: a repostagem está parada")):
        if contas and not any(p["funcao"] == funcao for p in postos):
            postos.append({"chave": f"{funcao}:vago", "funcao": funcao, "conta_id": None,
                           "apelido": None, "ok": False, "motivo": vazio})

    atrasada = None
    checagens = [c.get("ultima_checagem") for c in contas if c.get("ultima_checagem")]
    if contas:
        try:
            ultima = datetime.strptime(max(checagens), "%Y-%m-%d %H:%M:%S") if checagens else None
        except ValueError:
            ultima = None
        minutos = int((agora - ultima).total_seconds() // 60) if ultima else None
        if minutos is None or minutos > MINUTOS_CHECAGEM_ATRASADA:
            atrasada = minutos if minutos is not None else -1
    return {"postos": postos, "checagem_atrasada_min": atrasada}


def motivo_saida(conta_id, funcao, ocupacao=None):
    """Por que a conta não está mais no posto (texto para o aviso do bot_mestre)."""
    conta = obter_conta(conta_id)
    if not conta:
        return "conta removida do cadastro"
    postos = postos_da_conta(conta_id, ocupacao)
    if funcao == FUNCAO_REPOSTAGEM and FUNCAO_ESPELHO in postos:
        return "passou para a captura"
    if not conta_apta(conta, funcao):
        return _motivo_inaptidao(conta, funcao)
    return "outra conta assumiu o posto"


# Situação da conta no grupo de origem, em palavras (painel do bot).
TEXTOS_GRUPO = {
    STATUS_NO_GRUPO: "no grupo de origem",
    STATUS_SAIU: "saiu do grupo de origem",
    STATUS_NUNCA_ENTROU: "não está no grupo de origem (nunca entrou ou foi removida)",
    STATUS_BANIDA_GRUPO: "banida ou restrita no grupo de origem",
    STATUS_DESCONHECIDO: "ainda não conferida",
}


def telefone_legivel(telefone):
    """Telefone no formato que o Rafael reconhece no chip (+55 32 99999-0001)."""
    numeros = re.sub(r"\D", "", str(telefone or ""))
    if not numeros:
        return "telefone ainda não lido"
    if numeros.startswith("55") and len(numeros) in (12, 13):
        resto = numeros[4:]
        return f"+55 {numeros[2:4]} {resto[:-4]}-{resto[-4:]}"
    return "+" + numeros


def identificar(conta):
    """Como a conta aparece em todas as telas, sempre igual: apelido e telefone do chip."""
    return f"<b>{conta['apelido']}</b> · 📱 {telefone_legivel(conta.get('telefone'))}"


def texto_canal(conta):
    """Se a conta consegue publicar no seu canal (só importa para quem captura)."""
    pode = conta.get("publica_no_destino")
    if pode is None:
        return "❔ ainda não conferido"
    return "✅ pode publicar" if pode else "❌ não é admin (não consegue publicar)"


def montar_relatorio_telegram():
    """
    Texto do painel de Contas: o que cada posto faz, o ✅/❌ de quem está nele e,
    numeradas, todas as contas (o número é o que o Rafael digita para gerenciar).

    Enxuto de propósito: mensagem do Telegram estoura em 4096 caracteres, e este
    painel cresce a cada conta nova. Com 20 contas ainda cabe.
    """
    contas = listar_contas()
    ocupacao = ler_ocupacao()
    saude = avaliar_saude(contas, ocupacao, ler_atividade())

    linhas = ["👥 <b>Contas dos Autorais</b>",
              "<i>🎯 Captura: uma conta pega os vídeos do grupo de origem e publica no seu canal.\n"
              "🔁 Repostagem: as outras devolvem os vídeos ao grupo de origem, revezando.</i>",
              ""]
    if not contas:
        linhas.append("<i>Nenhuma conta cadastrada ainda: toque em Cadastrar Conta ➕.</i>")
        return "\n".join(linhas)

    titulos = {FUNCAO_ESPELHO: "🎯 <b>Captura</b>", FUNCAO_REPOSTAGEM: "🔁 <b>Repostagem</b>"}
    for funcao in FUNCOES:
        for p in (p for p in saude["postos"] if p["funcao"] == funcao):
            icone = "✅" if p["ok"] else "❌"
            nome = f"<b>{p['apelido']}</b> · " if p["apelido"] else ""
            linhas.append(f"{titulos[funcao]}: {icone} {nome}<i>{p['motivo']}</i>")
    if saude["checagem_atrasada_min"] is not None:
        quando = ("nunca" if saude["checagem_atrasada_min"] < 0
                  else _tempo_legivel(saude["checagem_atrasada_min"]))
        linhas.append(f"⚠️ <i>Contas checadas pela última vez: {quando}. O robô dos Autorais "
                      f"checa de 10 em 10 min; se isto não mudar, ele está parado.</i>")
    linhas.append("")

    for i, c in enumerate(contas, 1):
        trabalho = postos_da_conta(c["id"], ocupacao)
        if not c["habilitada"]:
            agora = "⏸️ pausada"
        elif c["status_sessao"] != SESSAO_OK:
            agora = "⚠️ desconectada do Telegram"
        elif FUNCAO_ESPELHO in trabalho:
            agora = "capturando"
        elif trabalho:
            agora = "repostando"
        else:
            agora = "parada"
        papel = papel_da_conta(c)
        grupo = f"{ICONES_GRUPO.get(c['status_grupo'], '❓')} {TEXTOS_GRUPO.get(c['status_grupo'], c['status_grupo'])}"
        linha = (f"<blockquote><b>{i}</b> — {identificar(c)}\n"
                 f"🧩 {ROTULOS_PAPEL[papel] if papel else '⚪ papel não escolhido'} · {agora}\n"
                 f"📍 {grupo}")
        if papel != PAPEL_REPOSTAGEM:
            linha += f"\n📣 canal: {texto_canal(c)}"
        linhas.append(linha + "</blockquote>")
    return "\n".join(linhas)


# =============================================================================
# 5. MOTOR DE REVEZAMENTO
# =============================================================================
# Este bloco é PURO: recebe listas e dicionários, devolve listas e dicionários,
# não toca no banco nem na rede. Foi feito assim de propósito, para poder ser
# testado sem Telegram nenhum (ver a função autoteste() no fim do arquivo).

def conta_apta(conta, funcao):
    """
    A pergunta única: esta conta pode assumir este posto agora?

    Quatro condições, todas obrigatórias:
      1. está habilitada manualmente
      2. a sessão do Telegram está viva
      3. está DENTRO do grupo dos Autorais
      4. a função consta na lista de funções permitidas dela
    """
    if not conta.get("habilitada", 1):
        return False
    if conta.get("status_sessao", SESSAO_OK) != SESSAO_OK:
        return False
    if conta.get("status_grupo") != STATUS_NO_GRUPO:
        return False
    permitidas = str(conta.get("funcoes_permitidas") or "").lower()
    permitidas = [p.strip() for p in permitidas.split(",") if p.strip()]
    return funcao in permitidas


def _lista_ids(valor):
    """Normaliza a ocupação da repostagem para lista de ids (aceita None, id ou lista)."""
    if valor is None:
        return []
    if isinstance(valor, (list, tuple)):
        return [v for v in valor if v is not None]
    return [valor]


def resolver_funcoes(contas, ocupacao_atual):
    """
    Distribui os postos. Não escreve nada: devolve o que DEVERIA ser.

    Entrada:
      contas         → lista de dicts de contas (como vem do listar_contas)
      ocupacao_atual → {"espelho": id_ou_None, "repostagem": [ids]}

    Saída:
      (nova_ocupacao, mudancas)
      mudancas → lista de tuplas (funcao, id_antigo, id_novo, motivo)

    Espelho: uma titular. Quem está no posto e continua apta fica; posto vago vai
    primeiro para uma conta que não reposta (reserva da captura), depois pela
    prioridade.
    Repostagem: rodízio com TODAS as contas aptas, menos a do espelho. A conta da
    captura nunca reposta: sem conta de repostagem, a repostagem fica parada.
    """
    por_id = {c["id"]: c for c in contas}
    espelho = ocupacao_atual.get(FUNCAO_ESPELHO)
    rodizio_antes = _lista_ids(ocupacao_atual.get(FUNCAO_REPOSTAGEM))
    mudancas = []

    # Espelho, passo 1: a titular continua se ainda estiver apta. É o que garante a
    # estabilidade: conta nova no grupo nunca derruba quem está trabalhando.
    if espelho is not None:
        conta = por_id.get(espelho)
        if conta is None:
            mudancas.append((FUNCAO_ESPELHO, espelho, None, "conta não existe mais no cadastro"))
            espelho = None
        elif not conta_apta(conta, FUNCAO_ESPELHO):
            mudancas.append((FUNCAO_ESPELHO, espelho, None, _motivo_inaptidao(conta, FUNCAO_ESPELHO)))
            espelho = None

    # Espelho, passo 2: posto vago. Prefere quem não pode repostar, para não tirar
    # ninguém do rodízio à toa.
    if espelho is None:
        candidatas = [c for c in contas if conta_apta(c, FUNCAO_ESPELHO)]
        if candidatas:
            escolhida = sorted(candidatas, key=lambda c: (
                conta_apta(c, FUNCAO_REPOSTAGEM), int(c.get("prioridade") or 100), c["id"]))[0]
            espelho = escolhida["id"]
            mudancas.append((FUNCAO_ESPELHO, None, espelho, "assumiu posto vago"))

    # Repostagem: o rodízio é recalculado do zero; as mudanças são o que entrou e saiu.
    rodizio = [c["id"] for c in _ordenar_candidatas(
        [c for c in contas if conta_apta(c, FUNCAO_REPOSTAGEM) and c["id"] != espelho])]
    for antigo in rodizio_antes:
        if antigo in rodizio:
            continue
        conta = por_id.get(antigo)
        if conta is None:
            motivo = "conta não existe mais no cadastro"
        elif antigo == espelho:
            motivo = "passou para a captura (a captura não reposta)"
        else:
            motivo = _motivo_inaptidao(conta, FUNCAO_REPOSTAGEM)
        mudancas.append((FUNCAO_REPOSTAGEM, antigo, None, motivo))
    for novo in rodizio:
        if novo not in rodizio_antes:
            mudancas.append((FUNCAO_REPOSTAGEM, None, novo, "entrou no rodízio"))

    return {FUNCAO_ESPELHO: espelho, FUNCAO_REPOSTAGEM: rodizio}, mudancas


def _ordenar_candidatas(candidatas):
    """Ordem de preferência: prioridade manual, depois quem cadastrou antes."""
    return sorted(candidatas, key=lambda c: (int(c.get("prioridade") or 100), c["id"]))


def _motivo_inaptidao(conta, funcao):
    """Texto legível para o histórico explicando por que a conta saiu do posto."""
    if not conta.get("habilitada", 1):
        return "conta desabilitada manualmente"
    if conta.get("status_sessao") == SESSAO_MORTA:
        return "sessão do Telegram morreu (logout/revogação)"
    if conta.get("status_sessao") == SESSAO_CONTA_BANIDA:
        return "conta banida ou desativada pelo Telegram"
    if conta.get("status_grupo") == STATUS_BANIDA_GRUPO:
        return "banida dentro do grupo dos Autorais"
    if conta.get("status_grupo") == STATUS_SAIU:
        return "saiu do grupo dos Autorais"
    if conta.get("status_grupo") == STATUS_NUNCA_ENTROU:
        return "não está no grupo dos Autorais"
    permitidas = str(conta.get("funcoes_permitidas") or "")
    if funcao not in permitidas:
        return f"função '{funcao}' não está liberada para esta conta"
    return "ficou inapta"


def aplicar_funcoes():
    """
    Roda o motor contra o estado atual do banco e GRAVA o resultado.
    Devolve a lista de mudanças (vazia = nada mudou, que é o caso normal).
    """
    inicializar_tabelas()
    contas = listar_contas()
    ocupacao = ler_ocupacao()

    nova, mudancas = resolver_funcoes(contas, ocupacao)
    if not mudancas:
        return []

    apelido_por_id = {c["id"]: c["apelido"] for c in contas}
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    if nova[FUNCAO_ESPELHO] != ocupacao.get(FUNCAO_ESPELHO):
        cursor.execute(
            "UPDATE funcoes_contas SET conta_id = ?, assumida_em = ?, motivo = ? WHERE funcao = ?",
            (nova[FUNCAO_ESPELHO], _agora(), "redistribuição automática", FUNCAO_ESPELHO),
        )
    rodizio = nova[FUNCAO_REPOSTAGEM]
    if rodizio != _lista_ids(ocupacao.get(FUNCAO_REPOSTAGEM)):
        cursor.execute(
            "UPDATE funcoes_contas SET conta_id = ?, contas_ids = ?, assumida_em = ?, motivo = ? "
            "WHERE funcao = ?",
            (rodizio[0] if rodizio else None, ",".join(str(i) for i in rodizio),
             _agora(), "redistribuição automática", FUNCAO_REPOSTAGEM),
        )
    conexao.commit()
    conexao.close()

    for funcao, antigo, novo, motivo in mudancas:
        de = apelido_por_id.get(antigo, "—")
        para = apelido_por_id.get(novo, "VAGO")
        registrar_evento(para if novo else de, f"FUNCAO_{funcao.upper()}",
                         f"{de} → {para} ({motivo})")
        logger.info(f"🔄 [Pool] Posto '{funcao}': {de} → {para} — {motivo}")

    return mudancas


def ler_ocupacao():
    """Devolve {"espelho": id|None, "repostagem": [ids do rodízio]} lido do banco."""
    inicializar_tabelas()
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    cursor.execute("SELECT funcao, conta_id, contas_ids FROM funcoes_contas")
    linhas = {linha["funcao"]: linha for linha in cursor.fetchall()}
    conexao.close()

    espelho = linhas.get(FUNCAO_ESPELHO)
    repost = linhas.get(FUNCAO_REPOSTAGEM)
    rodizio = []
    if repost is not None:
        if repost["contas_ids"]:
            rodizio = [int(i) for i in str(repost["contas_ids"]).split(",") if i.strip().isdigit()]
        elif repost["conta_id"]:
            rodizio = [repost["conta_id"]]  # gravado antes do rodízio existir
    return {FUNCAO_ESPELHO: espelho["conta_id"] if espelho is not None else None,
            FUNCAO_REPOSTAGEM: rodizio}


def postos_da_conta(conta_id, ocupacao=None):
    """Funções que a conta exerce agora (lista vazia = nenhuma)."""
    if ocupacao is None:
        ocupacao = ler_ocupacao()
    postos = []
    if ocupacao.get(FUNCAO_ESPELHO) == conta_id:
        postos.append(FUNCAO_ESPELHO)
    if conta_id in _lista_ids(ocupacao.get(FUNCAO_REPOSTAGEM)):
        postos.append(FUNCAO_REPOSTAGEM)
    return postos


# =============================================================================
# 6. API PÚBLICA — é isto que os outros arquivos chamam
# =============================================================================

def obter_conta_da_funcao(funcao):
    """
    A pergunta do dia a dia: quem está de plantão neste posto?
    Devolve o dicionário da conta, ou None se o posto estiver vago.

    ⚠️ Quem chamar isto DEVE tratar o None. Posto vago significa "não tem
    nenhuma conta minha dentro do grupo agora" — o certo é pular o ciclo e
    logar, não quebrar.
    """
    inicializar_tabelas()
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    cursor.execute("SELECT conta_id FROM funcoes_contas WHERE funcao = ?", (funcao,))
    linha = cursor.fetchone()
    if not linha or not linha["conta_id"]:
        conexao.close()
        return None
    cursor.execute("SELECT * FROM contas_telegram WHERE id = ?", (linha["conta_id"],))
    conta = cursor.fetchone()
    conexao.close()
    return dict(conta) if conta else None


def obter_contas_repostagem():
    """As contas do rodízio da repostagem, na ordem do rodízio (lista vazia = parada)."""
    ids = _lista_ids(ler_ocupacao().get(FUNCAO_REPOSTAGEM))
    por_id = {c["id"]: c for c in listar_contas()}
    return [por_id[i] for i in ids if i in por_id]


def obter_sessao_da_funcao(funcao):
    """A StringSession já decifrada do plantonista, ou None."""
    conta = obter_conta_da_funcao(funcao)
    if not conta:
        return None
    return decifrar(conta.get("sessao_cifrada"))


async def criar_cliente(conta, conectar=True):
    """
    Monta um TelegramClient a partir da sessão CIFRADA da conta.

    Usa StringSession (memória) em vez de arquivo .session. Vantagens:
      • nada de arquivo solto no disco com credencial em texto
      • duas contas nunca disputam o mesmo arquivo .session
      • a sessão viaja dentro do banco quando trocar de servidor
    """
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    if not conta:
        return None
    sessao = decifrar(conta.get("sessao_cifrada"))
    if not sessao:
        logger.error(f"❌ [Pool] Conta '{conta.get('apelido')}' sem sessão utilizável.")
        return None

    cliente = TelegramClient(StringSession(sessao), API_ID, API_HASH)
    if conectar:
        await cliente.connect()
        if not await cliente.is_user_authorized():
            atualizar_status(conta["apelido"], status_sessao=SESSAO_MORTA,
                             erro="sessão não autorizada ao conectar")
            await cliente.disconnect()
            return None
    return cliente


async def criar_cliente_da_funcao(funcao):
    """Atalho: o cliente já conectado de quem está de plantão no posto."""
    conta = obter_conta_da_funcao(funcao)
    if not conta:
        logger.warning(f"⚠️ [Pool] Posto '{funcao}' está VAGO — nenhuma conta apta.")
        return None
    return await criar_cliente(conta)


# =============================================================================
# 7. CHECAGEM CONTRA O TELEGRAM
# =============================================================================

def obter_grupo_autorais():
    """
    Descobre qual é o grupo dos Autorais lendo a MESMA configuração que o
    espelhador usa ('autorais_config' → 'origem'). Assim, quando o grupo for
    trocado no painel, o pool acompanha sozinho, sem editar código.
    """
    try:
        conexao = _obter_conexao()
        cursor = conexao.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'autorais_config'")
        linha = cursor.fetchone()
        conexao.close()
        if linha and linha["valor"]:
            cfg = json.loads(linha["valor"])
            origem = cfg.get("origem")
            if origem:
                return int(origem)
    except Exception as e:
        logger.error(f"❌ [Pool] Não consegui ler o grupo dos Autorais: {e}")
    return None


def obter_destino_autorais():
    """Canal onde a conta da captura publica os vídeos ('autorais_config' → 'destino')."""
    try:
        conexao = _obter_conexao()
        linha = conexao.execute("SELECT valor FROM configuracoes WHERE chave = 'autorais_config'").fetchone()
        conexao.close()
        destino = str(json.loads(linha["valor"]).get("destino") or "").split(":")[0].strip() if linha else ""
        if destino.lstrip("-").isdigit():
            return int(destino)
        return destino or None
    except Exception as e:
        logger.error(f"❌ [Pool] Não consegui ler o canal de destino dos Autorais: {e}")
        return None


def marcar_publicacao_no_destino(apelido, pode):
    conexao = _obter_conexao()
    conexao.execute("UPDATE contas_telegram SET publica_no_destino = ? WHERE apelido = ?",
                    (None if pode is None else int(bool(pode)), apelido))
    conexao.commit()
    conexao.close()


async def conferir_destino(cliente, conta):
    """
    A conta consegue publicar no canal de destino? Num canal de transmissão só o
    dono e o admin com "publicar mensagens" conseguem; num grupo, qualquer membro
    não restrito. Grava em publica_no_destino e devolve True/False, ou None quando
    não deu para concluir (sem destino configurado, limite do Telegram).
    """
    from telethon import errors

    destino = obter_destino_autorais()
    if not destino:
        return None
    try:
        try:
            entidade = await cliente.get_entity(destino)
        except ValueError:
            # Cache vazio (StringSession nova): carrega as conversas e tenta de novo.
            # Se nem assim aparece, a conta não está no canal.
            await cliente.get_dialogs()
            entidade = await cliente.get_entity(destino)
        permissoes = await cliente.get_permissions(entidade, "me")
        if getattr(entidade, "broadcast", False):
            direitos = getattr(getattr(permissoes, "participant", None), "admin_rights", None)
            pode = bool(permissoes.is_creator or (permissoes.is_admin and getattr(direitos, "post_messages", False)))
        else:
            pode = not getattr(permissoes, "is_banned", False)
    except errors.FloodWaitError:
        return None
    except Exception:
        pode = False   # fora do canal, canal privado para ela ou não encontrado
    marcar_publicacao_no_destino(conta["apelido"], pode)
    return pode


async def checar_conta(conta, grupo_id=None, cliente=None):
    """
    Conecta com a conta, descobre em que pé ela está e grava no banco.

    cliente: o TelegramClient já conectado desta conta (o robô dos Autorais passa
    os dele). Assim a checagem não abre uma segunda conexão da mesma conta, e o
    cliente continua conectado no fim.

    Devolve (status_grupo, status_sessao).

    Traduzindo os erros do Telethon para os nossos estados:
      UserNotParticipantError   → saiu / nunca entrou
      ChannelPrivateError       → foi removida, banida, ou o grupo sumiu
      UserDeactivated*          → conta banida pelo Telegram
      AuthKeyUnregistered etc.  → sessão morreu
      FloodWaitError            → não conclui nada; mantém o estado anterior
    """
    from telethon import errors

    apelido = conta["apelido"]
    if grupo_id is None:
        grupo_id = obter_grupo_autorais()

    emprestado = cliente is not None
    try:
        if not emprestado:
            cliente = await criar_cliente(conta)
        if cliente is None:
            return (conta.get("status_grupo"), SESSAO_MORTA)

        # Atualiza os dados de identidade a cada checagem: nome, @ e id.
        # É isto que faz a tabela "se atualizar sozinha" depois do login.
        eu = await cliente.get_me()
        if eu:
            nome = " ".join(filter(None, [eu.first_name, eu.last_name])).strip()
            salvar_conta(apelido, user_id=eu.id, username=eu.username or "",
                         nome_exibicao=nome or apelido,
                         telefone=getattr(eu, "phone", None))

        # Quem pode capturar também publica no seu canal: confere antes do grupo,
        # para o cadastro já avisar mesmo com a conta ainda fora do grupo de origem.
        # Conta sem papel escolhido também, para o painel não mostrar a linha vazia.
        if papel_da_conta(conta) != PAPEL_REPOSTAGEM:
            await conferir_destino(cliente, conta)

        if not grupo_id:
            atualizar_status(apelido, status_sessao=SESSAO_OK,
                             erro="grupo dos Autorais não configurado")
            return (conta.get("status_grupo"), SESSAO_OK)

        # A checagem de participação propriamente dita.
        try:
            entidade = await cliente.get_entity(grupo_id)
            permissoes = await cliente.get_permissions(entidade, "me")
            if getattr(permissoes, "is_banned", False):
                atualizar_status(apelido, status_grupo=STATUS_BANIDA_GRUPO,
                                 status_sessao=SESSAO_OK, erro="restrita no grupo")
                return (STATUS_BANIDA_GRUPO, SESSAO_OK)
            atualizar_status(apelido, status_grupo=STATUS_NO_GRUPO, status_sessao=SESSAO_OK)
            return (STATUS_NO_GRUPO, SESSAO_OK)

        except errors.UserNotParticipantError:
            fora = STATUS_SAIU if conta.get("ja_esteve_no_grupo") else STATUS_NUNCA_ENTROU
            atualizar_status(apelido, status_grupo=fora, status_sessao=SESSAO_OK)
            return (fora, SESSAO_OK)

        except errors.ChannelPrivateError:
            # Não enxerga mais o grupo: foi removida/banida, ou o grupo virou
            # privado para ela. Tratado como banimento por segurança.
            fora = STATUS_BANIDA_GRUPO if conta.get("ja_esteve_no_grupo") else STATUS_NUNCA_ENTROU
            atualizar_status(apelido, status_grupo=fora, status_sessao=SESSAO_OK,
                             erro="grupo inacessível para esta conta")
            return (fora, SESSAO_OK)

        except ValueError:
            # ARMADILHA: o cache de entidades mora no arquivo .session e NÃO
            # viaja para a StringSession. Numa conta recém-adotada o cache está
            # vazio, então get_entity() falha por ID mesmo quando a conta ESTÁ
            # no grupo. Procura o grupo direto nas conversas da conta: estar lá
            # (sem "left") é estar no grupo. Erro aqui (FloodWait, rede) sobe para
            # os tratadores de fora, que guardam o motivo e não mudam o estado.
            logger.info(f"🗂️ [Pool] {apelido}: cache vazio, procurando o grupo nas conversas...")
            entidade = None
            async for dialogo in cliente.iter_dialogs():
                if dialogo.id == grupo_id:
                    entidade = dialogo.entity
                    break
            fora = STATUS_SAIU if conta.get("ja_esteve_no_grupo") else STATUS_NUNCA_ENTROU
            if type(entidade).__name__ == "ChannelForbidden":
                atualizar_status(apelido, status_grupo=STATUS_BANIDA_GRUPO, status_sessao=SESSAO_OK,
                                 erro="banida do grupo de origem")
                return (STATUS_BANIDA_GRUPO, SESSAO_OK)
            if entidade is None or getattr(entidade, "left", False):
                atualizar_status(apelido, status_grupo=fora, status_sessao=SESSAO_OK,
                                 erro="o grupo de origem não está nas conversas da conta")
                return (fora, SESSAO_OK)
            try:
                permissoes = await cliente.get_permissions(entidade, "me")
            except errors.UserNotParticipantError:
                atualizar_status(apelido, status_grupo=fora, status_sessao=SESSAO_OK)
                return (fora, SESSAO_OK)
            if getattr(permissoes, "is_banned", False):
                atualizar_status(apelido, status_grupo=STATUS_BANIDA_GRUPO,
                                 status_sessao=SESSAO_OK, erro="restrita no grupo")
                return (STATUS_BANIDA_GRUPO, SESSAO_OK)
            atualizar_status(apelido, status_grupo=STATUS_NO_GRUPO, status_sessao=SESSAO_OK)
            return (STATUS_NO_GRUPO, SESSAO_OK)

    except errors.FloodWaitError as e:
        # Não dá para concluir nada: preserva o estado anterior e sai quieto.
        atualizar_status(apelido, erro=f"FloodWait de {e.seconds}s — checagem adiada")
        logger.warning(f"⏳ [Pool] {apelido}: FloodWait de {e.seconds}s. Checagem adiada.")
        return (conta.get("status_grupo"), conta.get("status_sessao"))

    except (errors.UserDeactivatedBanError, errors.UserDeactivatedError):
        atualizar_status(apelido, status_sessao=SESSAO_CONTA_BANIDA,
                         erro="conta banida/desativada pelo Telegram")
        return (conta.get("status_grupo"), SESSAO_CONTA_BANIDA)

    except (errors.AuthKeyUnregisteredError, errors.AuthKeyDuplicatedError,
            errors.SessionRevokedError, errors.SessionExpiredError):
        atualizar_status(apelido, status_sessao=SESSAO_MORTA, erro="sessão revogada/expirada")
        return (conta.get("status_grupo"), SESSAO_MORTA)

    except Exception as e:
        atualizar_status(apelido, erro=f"{type(e).__name__}: {e}")
        logger.error(f"❌ [Pool] Erro ao checar '{apelido}': {type(e).__name__}: {e}")
        return (conta.get("status_grupo"), conta.get("status_sessao"))

    finally:
        if cliente is not None and not emprestado:
            try:
                await cliente.disconnect()
            except Exception:
                pass


async def sincronizar_pool(clientes=None):
    """
    A rotina completa, para pendurar no APScheduler (sugestão: 10 em 10 min).

      1. checa conta por conta contra o Telegram
      2. redistribui os postos conforme o resultado
      3. devolve a lista de mudanças

    É idempotente: rodar duas vezes seguidas não muda nada na segunda.

    clientes: {conta_id: TelegramClient conectado}, os que o robô dos Autorais já
    tem abertos; as outras contas conectam só para a checagem.
    """
    inicializar_tabelas()
    contas = listar_contas()
    if not contas:
        logger.info("👥 [Pool] Nenhuma conta cadastrada ainda. Use: python3 pool_contas.py login")
        return []

    grupo_id = obter_grupo_autorais()
    logger.info(f"🔍 [Pool] Checando {len(contas)} conta(s) contra o grupo {grupo_id}...")

    for conta in contas:
        # Uma pausa curta entre contas: várias conexões simultâneas com o mesmo
        # API_ID é o caminho mais rápido para tomar FloodWait.
        await checar_conta(conta, grupo_id, cliente=(clientes or {}).get(conta["id"]))
        await asyncio.sleep(2)

    return aplicar_funcoes()


# =============================================================================
# 8. LOGIN E ADOÇÃO DE SESSÕES EXISTENTES
# =============================================================================

async def iniciar_login(telefone):
    """
    Primeira etapa do login de uma conta nova: pede o código ao Telegram.
    Devolve (cliente, phone_code_hash). O cliente fica conectado até
    confirmar_codigo/confirmar_senha/finalizar_cadastro (ou cancelar_login).
    """
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    if not API_ID or not API_HASH:
        raise RuntimeError("API_ID / API_HASH não encontrados no .env.")
    cliente = TelegramClient(StringSession(), API_ID, API_HASH)
    await cliente.connect()
    try:
        enviado = await cliente.send_code_request(telefone)
    except Exception:
        await cliente.disconnect()
        raise
    return cliente, enviado.phone_code_hash


async def confirmar_codigo(cliente, telefone, codigo, phone_code_hash):
    """Segunda etapa. Devolve True se a conta pede a senha das duas etapas."""
    from telethon.errors import SessionPasswordNeededError
    try:
        await cliente.sign_in(telefone, codigo, phone_code_hash=phone_code_hash)
        return False
    except SessionPasswordNeededError:
        return True


async def confirmar_senha(cliente, senha):
    """Terceira etapa, só para conta com verificação em duas etapas."""
    await cliente.sign_in(password=senha)


async def cancelar_login(cliente):
    """Desconecta um login que não vai ser concluído."""
    try:
        await cliente.disconnect()
    except Exception:
        pass


def apelido_sugerido(eu):
    """
    Apelido para a conta logada: o que ela já tem no pool (novo login da mesma
    conta só renova a sessão), senão o @ ou "conta<id>"; se o nome estiver com
    outra conta, ganha o fim do id.
    """
    for c in listar_contas():
        if c.get("user_id") == eu.id:
            return c["apelido"]
    base = (eu.username or f"conta{eu.id}").lower()
    existente = obter_conta(base)
    if existente and existente.get("user_id") not in (None, eu.id):
        return f"{base}_{eu.id % 10000}"
    return base


async def finalizar_cadastro(cliente, telefone, senha_2fa=None, apelido=None):
    """
    Última etapa: grava a conta logada no pool (sessão cifrada), confere o grupo
    dos Autorais e redistribui os postos. Desconecta o cliente do login.
    Devolve (apelido, status_grupo, mudancas).
    """
    eu = await cliente.get_me()
    sessao = cliente.session.save()
    await cliente.disconnect()

    apelido = apelido or apelido_sugerido(eu)
    nome = " ".join(filter(None, [eu.first_name, eu.last_name])).strip()
    salvar_conta(
        apelido=apelido,
        sessao=sessao,
        senha_2fa=senha_2fa,
        telefone=telefone,
        user_id=eu.id,
        username=eu.username or "",
        nome_exibicao=nome or apelido,
    )
    registrar_evento(apelido, "CADASTRO", f"login da conta id {eu.id}")

    status = await checar_conta(obter_conta(apelido))
    return apelido, status[0], aplicar_funcoes()


async def login_interativo(apelido=None):
    """
    Loga uma conta NOVA pelo terminal e cadastra tudo automaticamente.

    Fluxo: telefone → código do SMS/app → senha de 2FA (se houver) → get_me()
    → cifra a StringSession → grava → checa o grupo → redistribui os postos.
    O bot faz o mesmo pelo painel Contas 👥 (Cadastrar Conta ➕), com as mesmas etapas.
    """
    inicializar_tabelas()

    telefone = input("📱 Telefone com DDI (ex: +5532999998888): ").strip()
    try:
        cliente, codigo_hash = await iniciar_login(telefone)
    except Exception as e:
        print(f"❌ Falha ao pedir o código: {type(e).__name__}: {e}")
        return None

    senha_2fa = None
    try:
        codigo = input("🔑 Código recebido no Telegram: ").strip()
        if await confirmar_codigo(cliente, telefone, codigo, codigo_hash):
            # getpass: a senha não aparece na tela nem no histórico do bash.
            senha_2fa = getpass.getpass("🔐 Senha da verificação em duas etapas: ")
            await confirmar_senha(cliente, senha_2fa)
    except Exception as e:
        print(f"❌ Falha no login: {type(e).__name__}: {e}")
        await cancelar_login(cliente)
        return None

    if not apelido:
        eu = await cliente.get_me()
        sugestao = apelido_sugerido(eu)
        apelido = input(f"🏷️  Apelido para esta conta [{sugestao}]: ").strip() or sugestao

    apelido, status_grupo, mudancas = await finalizar_cadastro(cliente, telefone, senha_2fa, apelido)
    print(f"✅ Conta '{apelido}' cadastrada. Sessão gravada cifrada.")
    print(f"📍 Situação no grupo dos Autorais: {status_grupo}")
    if mudancas:
        print("🔄 Postos redistribuídos:")
        apelidos = {c["id"]: c["apelido"] for c in listar_contas()}
        for funcao, antigo, novo, motivo in mudancas:
            quem = apelidos.get(novo if novo else antigo, "?")
            print(f"   • {funcao}: {quem} — {motivo}")
    else:
        print("ℹ️  Nenhum posto mudou.")
    return apelido


async def adotar_sessoes_existentes():
    """
    Importa para o pool as contas que JÁ estão logadas no servidor pelos
    arquivos .session antigos, sem refazer login nenhum.

    Converte cada arquivo .session para StringSession, cifra e cadastra. Os
    arquivos originais continuam onde estão — nada é apagado, para não correr o
    risco de derrubar os serviços que ainda os usam.
    """
    import shutil
    import tempfile
    from telethon import TelegramClient
    from telethon.sessions import StringSession, SQLiteSession

    inicializar_tabelas()
    sessoes = [
        ("sessao_espelhador_isolado", "espelhador"),
        ("sessao_divulgacao", "divulgacao"),
        ("sessao_espiao", "espiao"),
    ]

    encontradas = 0
    for nome_arquivo, apelido_padrao in sessoes:
        if not os.path.exists(f"{nome_arquivo}.session"):
            print(f"⏭️  {nome_arquivo}.session não existe neste servidor.")
            continue

        # NÃO ABRA O .session ORIGINAL. Ele é um banco SQLite que o serviço
        # correspondente mantém ABERTO E TRAVADO enquanto roda. Tentar abrir
        # dava "database is locked" e a adoção falhava justamente nas contas dos
        # serviços que estão no ar. Trabalhamos sempre sobre uma CÓPIA.
        copia = None
        cliente = None
        try:
            copia = os.path.join(tempfile.gettempdir(), f"adocao_{nome_arquivo}.session")
            shutil.copy2(f"{nome_arquivo}.session", copia)

            # Ler a auth_key da cópia NÃO precisa de rede nem de conexão: o
            # StringSession se monta só com dc_id, endereço, porta e auth_key.
            sessao_disco = SQLiteSession(copia)
            sessao_texto = StringSession.save(sessao_disco)
            sessao_disco.close()

            if not sessao_texto:
                print(f"⚠️  {nome_arquivo}: sem chave de autorização. Pulando.")
                continue

            # Identidade é um bônus: se der erro (sessão em uso, rede fora), a
            # conta é adotada assim mesmo e o 'identificar' preenche depois.
            eu = None
            try:
                cliente = TelegramClient(StringSession(sessao_texto), API_ID, API_HASH)
                await cliente.connect()
                if await cliente.is_user_authorized():
                    eu = await cliente.get_me()
            except Exception as e_id:
                print(f"⚠️  {nome_arquivo}: adotada, mas não consegui ler a identidade agora "
                      f"({type(e_id).__name__}). Rode o comando 'identificar' depois.")
            finally:
                if cliente is not None:
                    try:
                        await cliente.disconnect()
                    except Exception:
                        pass

            if eu is not None:
                nome = " ".join(filter(None, [eu.first_name, eu.last_name])).strip()
                apelido = (eu.username or apelido_padrao).lower()
                salvar_conta(
                    apelido=apelido,
                    sessao=sessao_texto,
                    user_id=eu.id,
                    username=eu.username or "",
                    nome_exibicao=nome or apelido,
                    telefone=getattr(eu, "phone", None),
                )
                print(f"✅ Adotada: {apelido} (id {eu.id}) a partir de {nome_arquivo}.session")
            else:
                apelido = apelido_padrao.lower()
                salvar_conta(apelido=apelido, sessao=sessao_texto, nome_exibicao=apelido)
                print(f"✅ Adotada: {apelido} (identidade pendente) a partir de {nome_arquivo}.session")
            encontradas += 1

        except Exception as e:
            print(f"❌ Erro ao adotar {nome_arquivo}: {type(e).__name__}: {e}")
        finally:
            # A cópia carrega credencial: não pode ficar largada no /tmp.
            if copia and os.path.exists(copia):
                try:
                    os.remove(copia)
                except Exception:
                    pass

    if encontradas:
        print("\n🔍 Checando situação de cada uma no grupo...")
        await sincronizar_pool()
    return encontradas


def ler_convite():
    """O link de convite do grupo dos Autorais guardado, ou None."""
    inicializar_tabelas()
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    cursor.execute("SELECT valor FROM configuracoes WHERE chave = ?", (CHAVE_CONVITE,))
    linha = cursor.fetchone()
    conexao.close()
    if not linha or not linha["valor"]:
        return None
    try:
        return json.loads(linha["valor"]) or None
    except ValueError:
        return None


async def entrar_no_grupo(apelido):
    """
    Faz a conta entrar no grupo dos Autorais usando o link de convite guardado
    (comando 'convite' ou o painel do bot). Serve para "acabei de logar a conta 5,
    coloca ela lá dentro" sem abrir o Telegram no celular.

    Devolve (ok, mensagem). A mensagem também sai no terminal.
    """
    from telethon import functions
    from telethon.errors import (UserAlreadyParticipantError, InviteHashExpiredError,
                                 InviteHashInvalidError, InviteRequestSentError,
                                 ChannelPrivateError, UserBannedInChannelError)

    def resultado(ok, mensagem):
        print(mensagem)
        return ok, mensagem

    inicializar_tabelas()
    conta = obter_conta(apelido)
    if not conta:
        return resultado(False, f"❌ Conta '{apelido}' não encontrada.")
    link = ler_convite()
    if not link:
        return resultado(False, "❌ Nenhum link de convite guardado. Use: python3 pool_contas.py convite <link>")
    hash_convite = link.rstrip("/").split("/")[-1].lstrip("+")

    cliente = await criar_cliente(conta)
    if not cliente:
        return resultado(False, f"❌ Não consegui conectar '{apelido}' (sessão inválida).")
    try:
        await cliente(functions.messages.ImportChatInviteRequest(hash_convite))
        registrar_evento(apelido, "ENTROU_NO_GRUPO", "via link de convite")
        msg = f"✅ {apelido} entrou no grupo."
    except UserAlreadyParticipantError:
        msg = f"ℹ️ {apelido} já estava no grupo."
    except InviteRequestSentError:
        return resultado(False, f"⏳ Pedido de entrada de {apelido} enviado: um admin do grupo precisa aprovar.")
    except (InviteHashExpiredError, InviteHashInvalidError):
        return resultado(False, "❌ O link de convite expirou ou é inválido. Guarde um link novo.")
    except (ChannelPrivateError, UserBannedInChannelError):
        # Com o link certo, o Telegram só recusa assim quem foi banido do grupo.
        atualizar_status(apelido, status_grupo=STATUS_BANIDA_GRUPO, erro="banida do grupo de origem")
        return resultado(False, f"⛔ {apelido} foi banida do grupo de origem e não consegue entrar. "
                                "Só um admin do grupo pode desbanir; senão, use outra conta.")
    except Exception as e:
        return resultado(False, f"❌ Falha ao entrar: {type(e).__name__}: {e}")
    finally:
        await cliente.disconnect()

    await checar_conta(obter_conta(apelido))
    aplicar_funcoes()
    return resultado(True, msg)


def guardar_convite(link):
    """Grava o link de convite do grupo dos Autorais na tabela configuracoes."""
    inicializar_tabelas()
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
        (CHAVE_CONVITE, json.dumps(link)),
    )
    conexao.commit()
    conexao.close()
    print("✅ Link de convite guardado.")


# =============================================================================
# 9. COFRE PORTÁTIL (mudança de servidor)
# =============================================================================
# O caminho normal é copiar banco_dados.db + .env. O cofre é o plano B: um único
# arquivo cifrado com uma senha digitada na hora, que não depende do .env nem do
# banco. Serve para levar as contas para uma máquina nova em um passo só.

def exportar_cofre(caminho):
    """Exporta todas as contas para um arquivo cifrado com senha."""
    from cryptography.fernet import Fernet

    inicializar_tabelas()
    contas = listar_contas()
    if not contas:
        print("⚠️ Nenhuma conta para exportar.")
        return False

    senha = getpass.getpass("🔐 Crie uma senha para o cofre: ")
    confirma = getpass.getpass("🔐 Repita a senha: ")
    if senha != confirma or not senha:
        print("❌ As senhas não conferem.")
        return False

    pacote = []
    for c in contas:
        pacote.append({
            "apelido": c["apelido"],
            "telefone": c["telefone"],
            "user_id": c["user_id"],
            "username": c["username"],
            "nome_exibicao": c["nome_exibicao"],
            "sessao": decifrar(c["sessao_cifrada"]),
            "senha_2fa": decifrar(c["senha_2fa_cifrada"]),
            "funcoes_permitidas": c["funcoes_permitidas"],
            "prioridade": c["prioridade"],
        })

    sal = os.urandom(16)
    chave = _derivar_chave(senha, sal)
    corpo = Fernet(chave).encrypt(json.dumps(pacote, ensure_ascii=False).encode("utf-8"))

    with open(caminho, "wb") as f:
        f.write(b"POOLCONTAS1" + sal + corpo)
    os.chmod(caminho, 0o600)
    print(f"✅ {len(pacote)} conta(s) exportadas para {caminho} (cifrado).")
    print("   Leve este arquivo e a senha. Sem os dois juntos, ele não abre.")
    return True


def importar_cofre(caminho):
    """Importa um cofre gerado por exportar_cofre() neste servidor."""
    from cryptography.fernet import Fernet

    if not os.path.exists(caminho):
        print(f"❌ Arquivo não encontrado: {caminho}")
        return False

    with open(caminho, "rb") as f:
        bruto = f.read()
    if not bruto.startswith(b"POOLCONTAS1"):
        print("❌ Este arquivo não é um cofre do pool_contas.")
        return False

    sal = bruto[11:27]
    corpo = bruto[27:]
    senha = getpass.getpass("🔐 Senha do cofre: ")

    try:
        dados = json.loads(Fernet(_derivar_chave(senha, sal)).decrypt(corpo).decode("utf-8"))
    except Exception:
        print("❌ Senha incorreta ou arquivo corrompido.")
        return False

    inicializar_tabelas()
    for item in dados:
        salvar_conta(
            apelido=item["apelido"],
            sessao=item.get("sessao"),
            senha_2fa=item.get("senha_2fa"),
            telefone=item.get("telefone"),
            user_id=item.get("user_id"),
            username=item.get("username"),
            nome_exibicao=item.get("nome_exibicao"),
            funcoes_permitidas=item.get("funcoes_permitidas"),
            prioridade=item.get("prioridade"),
        )
    print(f"✅ {len(dados)} conta(s) importadas. Rode 'sincronizar' para checar o grupo.")
    return True


# =============================================================================
# 10. RELATÓRIO
# =============================================================================

def montar_relatorio():
    """
    Monta o texto da listagem. Devolve string — assim serve tanto para o
    terminal quanto para mandar no Telegram depois, sem reescrever nada.
    """
    contas = listar_contas()
    ocupacao = ler_ocupacao()

    if not contas:
        return "👥 Nenhuma conta cadastrada.\n   Cadastre com: python3 pool_contas.py login"

    linhas = ["👥 CONTAS DO POOL", ""]
    for c in contas:
        icone = ICONES_GRUPO.get(c["status_grupo"], "❓")
        trabalho = postos_da_conta(c["id"], ocupacao)
        if trabalho:
            papel = "🎯 " + " + ".join(trabalho).upper()
        elif conta_apta(c, FUNCAO_ESPELHO) or conta_apta(c, FUNCAO_REPOSTAGEM):
            papel = "🟡 RESERVA (apta, mas sem posto vago)"
        else:
            papel = "⚫ fora de operação"

        saude = "" if c["status_sessao"] == SESSAO_OK else f" ⚠️ {c['status_sessao']}"
        if not c["habilitada"]:
            saude += " ⏸️ desabilitada"

        linhas.append(f"{icone} {c['apelido']}  —  {papel}")
        linhas.append(f"    id {c['user_id'] or '?'} · {('@' + c['username']) if c['username'] else 'sem @'} · "
                      f"{c['nome_exibicao'] or '?'}")
        linhas.append(f"    grupo: {c['status_grupo']}{saude}")
        linhas.append(f"    pode: {c['funcoes_permitidas']} · prioridade {c['prioridade']}")
        if c["ultima_checagem"]:
            linhas.append(f"    checada em {c['ultima_checagem']}")
        if c["ultimo_erro"]:
            linhas.append(f"    último erro: {c['ultimo_erro']}")
        linhas.append("")

    linhas.append("─" * 50)
    espelho = obter_conta_da_funcao(FUNCAO_ESPELHO)
    rodizio = [c["apelido"] for c in obter_contas_repostagem()]
    linhas.append(f"🎯 {'ESPELHO':<12} → {espelho['apelido'] if espelho else '⚠️ VAGO'}")
    linhas.append(f"🎯 {'REPOSTAGEM':<12} → {', '.join(rodizio) if rodizio else '⚠️ PARADA (rodízio vazio)'}")
    return "\n".join(linhas)


# =============================================================================
# 11. AUTOTESTE — roda sem Telegram, sem banco, sem rede
# =============================================================================
# Reproduz o cenário das 5 contas exatamente como foi descrito. Serve de
# documentação executável: se alguém mexer na regra de revezamento e quebrar o
# comportamento esperado, este teste acusa na hora.
#     python3 pool_contas.py autoteste

def _conta_falsa(id_, apelido, status_grupo, funcoes="espelho,repostagem"):
    return {
        "id": id_, "apelido": apelido, "status_grupo": status_grupo,
        "status_sessao": SESSAO_OK, "habilitada": 1,
        "funcoes_permitidas": funcoes, "prioridade": 100,
    }


def autoteste():
    """Simula a novela das 5 contas e confere cada desfecho."""
    falhas = []

    def conferir(rotulo, obtido, esperado):
        marca = "✅" if obtido == esperado else "❌"
        print(f"  {marca} {rotulo}: {obtido}  (esperado: {esperado})")
        if obtido != esperado:
            falhas.append(rotulo)

    vazio = {FUNCAO_ESPELHO: None, FUNCAO_REPOSTAGEM: []}

    print("\n🧪 CENÁRIO 1 — conta 1 espelha, conta 2 reposta")
    contas = [_conta_falsa(1, "u1", STATUS_NO_GRUPO), _conta_falsa(2, "u2", STATUS_NO_GRUPO)]
    ocupacao, _ = resolver_funcoes(contas, vazio)
    conferir("espelho", ocupacao[FUNCAO_ESPELHO], 1)
    conferir("repostagem", ocupacao[FUNCAO_REPOSTAGEM], [2])

    print("\n🧪 CENÁRIO 2 — a conta 2 sai e a conta 3 entra")
    contas = [_conta_falsa(1, "u1", STATUS_NO_GRUPO), _conta_falsa(2, "u2", STATUS_SAIU),
              _conta_falsa(3, "u3", STATUS_NO_GRUPO)]
    ocupacao, mudancas = resolver_funcoes(contas, ocupacao)
    conferir("espelho continua com a 1", ocupacao[FUNCAO_ESPELHO], 1)
    conferir("repostagem passa para a 3", ocupacao[FUNCAO_REPOSTAGEM], [3])
    conferir("houve exatamente 2 movimentos", len(mudancas), 2)

    print("\n🧪 CENÁRIO 3 — a conta 4 entra: passa a revezar a repostagem com a 3")
    contas.append(_conta_falsa(4, "u4", STATUS_NO_GRUPO))
    ocupacao, mudancas = resolver_funcoes(contas, ocupacao)
    conferir("espelho intacto", ocupacao[FUNCAO_ESPELHO], 1)
    conferir("rodízio com a 3 e a 4", ocupacao[FUNCAO_REPOSTAGEM], [3, 4])
    conferir("um movimento (a 4 entrou)", len(mudancas), 1)

    print("\n🧪 CENÁRIO 4 — todas saem, só a conta 5 fica: captura sim, repostagem parada")
    contas = [_conta_falsa(1, "u1", STATUS_SAIU), _conta_falsa(3, "u3", STATUS_SAIU),
              _conta_falsa(4, "u4", STATUS_SAIU), _conta_falsa(5, "u5", STATUS_NO_GRUPO)]
    ocupacao, _ = resolver_funcoes(contas, ocupacao)
    conferir("espelho com a 5", ocupacao[FUNCAO_ESPELHO], 5)
    conferir("a captura não reposta: rodízio vazio", ocupacao[FUNCAO_REPOSTAGEM], [])

    print("\n🧪 CENÁRIO 5 — ninguém no grupo: captura vaga e repostagem parada")
    contas = [_conta_falsa(5, "u5", STATUS_BANIDA_GRUPO)]
    ocupacao, _ = resolver_funcoes(contas, ocupacao)
    conferir("espelho vago", ocupacao[FUNCAO_ESPELHO], None)
    conferir("rodízio vazio", ocupacao[FUNCAO_REPOSTAGEM], [])

    print("\n🧪 CENÁRIO 6 — conta restrita a uma função só")
    contas = [_conta_falsa(6, "u6", STATUS_NO_GRUPO, funcoes="repostagem"),
              _conta_falsa(7, "u7", STATUS_NO_GRUPO, funcoes="espelho")]
    ocupacao, _ = resolver_funcoes(contas, vazio)
    conferir("espelho só pode ser a 7", ocupacao[FUNCAO_ESPELHO], 7)
    conferir("repostagem só pode ser a 6", ocupacao[FUNCAO_REPOSTAGEM], [6])

    print("\n🧪 CENÁRIO 7 — a captura cai: assume a reserva que não reposta")
    contas = [_conta_falsa(1, "u1", STATUS_SAIU), _conta_falsa(2, "u2", STATUS_NO_GRUPO),
              _conta_falsa(8, "u8", STATUS_NO_GRUPO, funcoes="espelho")]
    ocupacao, _ = resolver_funcoes(contas, {FUNCAO_ESPELHO: 1, FUNCAO_REPOSTAGEM: [2]})
    conferir("espelho com a 8", ocupacao[FUNCAO_ESPELHO], 8)
    conferir("rodízio intacto", ocupacao[FUNCAO_REPOSTAGEM], [2])

    print("\n🧪 CENÁRIO 8 — a captura cai sem reserva: uma do rodízio passa para a captura")
    contas = [_conta_falsa(1, "u1", STATUS_SAIU), _conta_falsa(2, "u2", STATUS_NO_GRUPO),
              _conta_falsa(3, "u3", STATUS_NO_GRUPO)]
    ocupacao, mudancas = resolver_funcoes(contas, {FUNCAO_ESPELHO: 1, FUNCAO_REPOSTAGEM: [2, 3]})
    conferir("espelho com a 2", ocupacao[FUNCAO_ESPELHO], 2)
    conferir("rodízio só com a 3", ocupacao[FUNCAO_REPOSTAGEM], [3])

    print("\n🧪 CENÁRIO 9 — saúde: envio que falhou depois do último ok vira ❌")
    contas = [_conta_falsa(1, "u1", STATUS_NO_GRUPO), _conta_falsa(2, "u2", STATUS_NO_GRUPO),
              _conta_falsa(3, "u3", STATUS_NO_GRUPO)]
    for c in contas:
        c["ultima_checagem"] = "2026-10-03 12:00:00"
    atividade = {
        (1, FUNCAO_ESPELHO): {"ultimo_ok": "2026-10-03 11:00:00"},
        (2, FUNCAO_REPOSTAGEM): {"ultimo_ok": "2026-10-03 10:00:00", "erro_em": "2026-10-03 11:30:00",
                                 "ultimo_erro": "ChatWriteForbiddenError"},
        (3, FUNCAO_REPOSTAGEM): {"ultimo_ok": "2026-10-03 11:45:00", "erro_em": "2026-10-03 09:00:00"},
    }
    saude = avaliar_saude(contas, {FUNCAO_ESPELHO: 1, FUNCAO_REPOSTAGEM: [2, 3]}, atividade,
                          agora=datetime(2026, 10, 3, 12, 5))
    estado = {p["chave"]: p["ok"] for p in saude["postos"]}
    conferir("captura da 1 ✅", estado.get("espelho:1"), True)
    conferir("repostagem da 2 ❌", estado.get("repostagem:2"), False)
    conferir("repostagem da 3 ✅", estado.get("repostagem:3"), True)
    conferir("checagem em dia", saude["checagem_atrasada_min"], None)
    saude = avaliar_saude(contas, {FUNCAO_ESPELHO: 1, FUNCAO_REPOSTAGEM: []}, atividade,
                          agora=datetime(2026, 10, 3, 13, 0))
    estado = {p["chave"]: p["ok"] for p in saude["postos"]}
    conferir("rodízio vazio aparece como ❌", estado.get("repostagem:vago"), False)
    conferir("checagem atrasada (60 min)", saude["checagem_atrasada_min"], 60)

    print("\n" + "=" * 52)
    if falhas:
        print(f"🛑 {len(falhas)} verificação(ões) falharam: {', '.join(falhas)}")
        return False
    print("✅ Todos os cenários passaram. A regra de revezamento está correta.")
    return True


# =============================================================================
# 12. LINHA DE COMANDO
# =============================================================================

def main():
    """Ponto de entrada do CLI. Cada comando é uma linha do bloco de ajuda."""
    argumentos = sys.argv[1:]
    comando = argumentos[0] if argumentos else "listar"
    resto = argumentos[1:]

    if comando in ("ajuda", "-h", "--help"):
        print(__doc__ or "Veja o cabeçalho do arquivo para a lista de comandos.")
        print("Comandos: login | listar | sincronizar | importar-sessoes | identificar |")
        print("          senha <apelido> | credenciais [apelido] | entrar <apelido> |")
        print("          convite <link> | permitir <apelido> <funcoes> | prioridade <apelido> <n> |")
        print("          habilitar <apelido> | desabilitar <apelido> | remover <apelido> |")
        print("          exportar <arquivo> | importar <arquivo> | autoteste")
        return

    if comando == "autoteste":
        sys.exit(0 if autoteste() else 1)

    if comando == "listar":
        inicializar_tabelas()
        print(montar_relatorio())
        return

    if comando == "login":
        asyncio.run(login_interativo())
        return

    if comando == "sincronizar":
        asyncio.run(sincronizar_pool())
        print(montar_relatorio())
        return

    if comando == "importar-sessoes":
        asyncio.run(adotar_sessoes_existentes())
        asyncio.run(identificar_contas())
        print(montar_relatorio())
        return

    if comando == "identificar":
        asyncio.run(identificar_contas())
        return

    if comando == "senha" and resto:
        definir_senha_2fa(resto[0])
        return

    if comando == "credenciais":
        mostrar_credenciais(resto[0] if resto else None)
        return

    if comando == "entrar" and resto:
        asyncio.run(entrar_no_grupo(resto[0]))
        return

    if comando == "convite" and resto:
        guardar_convite(resto[0])
        return

    if comando == "permitir" and len(resto) >= 2:
        salvar_conta(resto[0], funcoes_permitidas=resto[1].lower())
        registrar_evento(resto[0], "FUNCOES_ALTERADAS", resto[1])
        aplicar_funcoes()
        print(montar_relatorio())
        return

    if comando == "prioridade" and len(resto) >= 2:
        salvar_conta(resto[0], prioridade=int(resto[1]))
        aplicar_funcoes()
        print(montar_relatorio())
        return

    if comando in ("habilitar", "desabilitar") and resto:
        definir_habilitada(resto[0], comando == "habilitar")
        aplicar_funcoes()
        print(montar_relatorio())
        return

    if comando == "remover" and resto:
        remover_conta(resto[0])
        aplicar_funcoes()
        print(montar_relatorio())
        return

    if comando == "exportar" and resto:
        exportar_cofre(resto[0])
        return

    if comando == "importar" and resto:
        importar_cofre(resto[0])
        return

    print(f"❓ Comando desconhecido ou faltando argumento: {comando}")
    print("   Use: python3 pool_contas.py ajuda")


if __name__ == "__main__":
    main()

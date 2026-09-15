# =============================================================================
# 👥 POOL DE CONTAS — pool_contas.py
# =============================================================================
#
# 📖 LEIA-ME PARA A IA (e para o Rafael daqui a seis meses)
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
# Quem captura/reposta continua sendo o espelhador_videos_autorais.py. O que
# muda é que ele para de ter uma sessão fixa escrita no código
# (NOME_SESSAO = 'sessao_espelhador_isolado') e passa a PERGUNTAR aqui quem
# está de plantão. A conta virou variável — era exatamente esse o pedido.
#
# ─── AS DUAS FUNÇÕES (POSTOS DE TRABALHO) ────────────────────────────────────
#   • "espelho"     → a conta que fica DENTRO do grupo dos Autorais capturando
#                     os vídeos e publicando no canal "Vídeos Autorais Afiliados".
#   • "repostagem"  → a conta que devolve o vídeo ao grupo de origem no D+X.
#
# Uma função é um POSTO, não uma conta. O posto existe sempre; quem o ocupa
# muda conforme as contas entram e saem do grupo.
#
# ─── A REGRA DE REVEZAMENTO (o coração deste arquivo) ────────────────────────
# Roda em resolver_funcoes(). Foi escrita para reproduzir exatamente o cenário
# que o Rafael descreveu, com 5 contas:
#
#   1. Conta 1 espelha, conta 2 reposta.                → dois postos ocupados
#   2. Conta 2 sai do grupo; conta 3 entra.             → conta 3 assume a
#                                                          repostagem sozinha
#   3. Conta 4 entra depois.                            → fica de RESERVA, não
#                                                          faz nada, porque
#                                                          nenhum posto vagou
#   4. Todas saem; só a conta 5 fica no grupo.          → a conta 5 acumula os
#                                                          DOIS postos
#
# Em uma frase: posto vago é preenchido na hora pela melhor conta livre; se não
# houver conta livre, uma conta que já trabalha acumula; se não houver conta
# nenhuma apta, o posto fica VAGO e o robô daquela função simplesmente não roda
# (em vez de quebrar com sessão inválida).
#
# Ordem de escolha do substituto:
#   (1) contas que não estão ocupando nenhum outro posto  → espalha o trabalho
#   (2) menor valor da coluna 'prioridade'                → preferência manual
#   (3) menor id                                          → quem cadastrou antes
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
# ⚠️ O repositório é PÚBLICO. Nada sensível pode entrar nele. O desenho é:
#
#   • O arquivo .py (este aqui) é público e NÃO contém segredo nenhum.
#   • As credenciais moram no banco_dados.db, que já está no .gitignore.
#   • Dentro do banco, a sessão e a senha de 2FA ficam CIFRADAS com Fernet
#     (AES-128-CBC + HMAC), nunca em texto puro. Quem abrir o .db sem a chave
#     vê só um bloco de bytes.
#   • A chave vem de uma senha-mestra no .env (CHAVE_MESTRA_CONTAS). Se ela não
#     existir, o módulo usa o API_HASH — que já é secreto, já está no .env e já
#     é copiado pelo backup_config.sh. Assim nunca há um "esqueci de configurar
#     e tudo parou".
#   • O sal do PBKDF2 mora na tabela 'configuracoes' do próprio banco. Ou seja:
#     .env + banco_dados.db = tudo funcionando. É exatamente o par que o
#     backup_config.sh já empacota.
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
#     # rotina periódica (colocar no APScheduler, de 10 em 10 minutos)
#     await pool_contas.sincronizar_pool()
#
# ─── LINHA DE COMANDO ────────────────────────────────────────────────────────
#     python3 pool_contas.py login             # loga uma conta nova e cadastra
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
#   • Não mexe em nenhuma tabela que não seja as três dele.
#   • Não reinicia serviço. Trocou o plantonista? Ele grava no banco e avisa no
#     log; quem lê o plantão é o serviço, na próxima vez que precisar.
#
# =============================================================================

EXIBIR_LOGS = True

import os
import sys
import json
import base64
import sqlite3
import logging
import asyncio
import getpass
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

# 🕐 Trava de fuso centralizada: importar o módulo já aplica America/Sao_Paulo.
# Mantém o padrão dos outros arquivos do projeto (fuso.py).
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

DB_NAME = "banco_dados.db"

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
    """Conexão SQLite no mesmo padrão do database.py do projeto."""
    conexao = sqlite3.connect(DB_NAME, timeout=20.0)
    conexao.row_factory = sqlite3.Row
    return conexao


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
    if EXIBIR_LOGS:
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
    if EXIBIR_LOGS:
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

    # Garante que as duas linhas de função existem desde o começo (vagas).
    for funcao in FUNCOES:
        cursor.execute(
            "INSERT OR IGNORE INTO funcoes_contas (funcao, conta_id, assumida_em, motivo) "
            "VALUES (?, NULL, NULL, 'posto criado vago')",
            (funcao,),
        )

    conexao.commit()
    conexao.close()
    if EXIBIR_LOGS and not _TABELAS_PRONTAS:
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
        if EXIBIR_LOGS:
            logger.error(f"❌ [Pool] Falha ao gravar histórico: {e}")
    if EXIBIR_LOGS:
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
# ⚠️ LEIA ISTO ANTES DE ESPERAR MÁGICA DESTE BLOCO.
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
            print(f"     username:         @{eu.username or 'sem @'}")
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
        print(f"   username:          @{c['username'] or 'sem @'}")
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


def montar_relatorio_telegram():
    """
    Mesma listagem do terminal, em HTML curto para caber numa mensagem.

    Enxuto de propósito: mensagem do Telegram estoura em 4096 caracteres, e este
    painel cresce a cada conta nova. Com 20 contas ainda cabe.
    """
    contas = listar_contas()
    ocupacao = ler_ocupacao()
    postos = {}
    for funcao, conta_id in ocupacao.items():
        postos.setdefault(conta_id, []).append(funcao)

    linhas = ["👥 <b>Contas e Postos</b>", ""]
    for funcao in FUNCOES:
        conta = obter_conta_da_funcao(funcao)
        alvo = f"<b>{conta['apelido']}</b>" if conta else "<i>⚠️ VAGO</i>"
        rotulo = "🪞 Espelho" if funcao == FUNCAO_ESPELHO else "♻️ Repostagem"
        linhas.append(f"{rotulo}: {alvo}")

    if not contas:
        linhas.append("")
        linhas.append("<i>Nenhuma conta cadastrada ainda.</i>")
        linhas.append("<i>No servidor: python3 pool_contas.py importar-sessoes</i>")
        return "\n".join(linhas)

    linhas.append("")
    linhas.append("━━━━━━━━━━━━━━━━")
    for c in contas:
        icone = ICONES_GRUPO.get(c["status_grupo"], "❓")
        trabalho = postos.get(c["id"], [])
        if trabalho:
            papel = "🎯 " + " + ".join(trabalho)
        elif conta_apta(c, FUNCAO_ESPELHO) or conta_apta(c, FUNCAO_REPOSTAGEM):
            papel = "🟡 reserva"
        else:
            papel = "⚫ fora"
        extra = "" if c["habilitada"] else " ⏸️"
        if c["status_sessao"] != SESSAO_OK:
            extra += f" ⚠️{c['status_sessao']}"
        linhas.append(f"{icone} <b>{c['apelido']}</b> · {papel}{extra}")
        linhas.append(f"   <code>{c['user_id'] or '?'}</code> · @{c['username'] or 'sem @'} "
                      f"· pode: {c['funcoes_permitidas']}")

    linhas.append("")
    linhas.append("<i>Toque numa conta para mudar as funções dela.</i>")
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


def resolver_funcoes(contas, ocupacao_atual):
    """
    Distribui os postos. Não escreve nada: devolve o que DEVERIA ser.

    Entrada:
      contas         → lista de dicts de contas (como vem do listar_contas)
      ocupacao_atual → {"espelho": id_ou_None, "repostagem": id_ou_None}

    Saída:
      (nova_ocupacao, mudancas)
      mudancas → lista de tuplas (funcao, id_antigo, id_novo, motivo)
    """
    por_id = {c["id"]: c for c in contas}
    nova = dict(ocupacao_atual)
    mudancas = []

    # ── Passo 1: quem está no posto continua, se ainda estiver apto ──────────
    # Este passo é o que garante a estabilidade: uma conta que está trabalhando
    # e continua apta NUNCA é trocada só porque entrou gente nova no grupo.
    for funcao in FUNCOES:
        atual_id = nova.get(funcao)
        if atual_id is None:
            continue
        conta = por_id.get(atual_id)
        if conta is None:
            nova[funcao] = None
            mudancas.append((funcao, atual_id, None, "conta não existe mais no cadastro"))
        elif not conta_apta(conta, funcao):
            nova[funcao] = None
            motivo = _motivo_inaptidao(conta, funcao)
            mudancas.append((funcao, atual_id, None, motivo))

    # ── Passo 2: preencher os postos vagos ──────────────────────────────────
    for funcao in FUNCOES:
        if nova.get(funcao) is not None:
            continue

        candidatas = [c for c in contas if conta_apta(c, funcao)]
        if not candidatas:
            continue

        # Contas que já pegaram algum posto NESTA rodada de distribuição.
        ja_ocupadas = {v for k, v in nova.items() if v is not None}

        livres = [c for c in candidatas if c["id"] not in ja_ocupadas]
        acumulando = [c for c in candidatas if c["id"] in ja_ocupadas]

        # Preferência: conta livre. Só acumula quando não sobrou mais ninguém —
        # é o cenário "todas saíram, só a conta 5 ficou: ela faz tudo".
        fila = _ordenar_candidatas(livres) or _ordenar_candidatas(acumulando)
        if not fila:
            continue

        escolhida = fila[0]
        motivo = "assumiu posto vago" if escolhida["id"] not in ja_ocupadas \
            else "acumulou função (não havia outra conta apta)"
        nova[funcao] = escolhida["id"]
        mudancas.append((funcao, None, escolhida["id"], motivo))

    return nova, mudancas


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
    for funcao in FUNCOES:
        if nova.get(funcao) != ocupacao.get(funcao):
            cursor.execute(
                "UPDATE funcoes_contas SET conta_id = ?, assumida_em = ?, motivo = ? WHERE funcao = ?",
                (nova.get(funcao), _agora(), "redistribuição automática", funcao),
            )
    conexao.commit()
    conexao.close()

    for funcao, antigo, novo, motivo in mudancas:
        de = apelido_por_id.get(antigo, "—")
        para = apelido_por_id.get(novo, "VAGO")
        registrar_evento(para if novo else de, f"FUNCAO_{funcao.upper()}",
                         f"{de} → {para} ({motivo})")
        if EXIBIR_LOGS:
            logger.info(f"🔄 [Pool] Posto '{funcao}': {de} → {para} — {motivo}")

    return mudancas


def ler_ocupacao():
    """Devolve {"espelho": id|None, "repostagem": id|None} lido do banco."""
    inicializar_tabelas()
    conexao = _obter_conexao()
    cursor = conexao.cursor()
    cursor.execute("SELECT funcao, conta_id FROM funcoes_contas")
    dados = {linha["funcao"]: linha["conta_id"] for linha in cursor.fetchall()}
    conexao.close()
    return {f: dados.get(f) for f in FUNCOES}


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
        if EXIBIR_LOGS:
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
        if EXIBIR_LOGS:
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
        if EXIBIR_LOGS:
            logger.error(f"❌ [Pool] Não consegui ler o grupo dos Autorais: {e}")
    return None


async def checar_conta(conta, grupo_id=None):
    """
    Conecta com a conta, descobre em que pé ela está e grava no banco.

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

    cliente = None
    try:
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
            # Telethon não achou a entidade: a conta nunca viu esse grupo.
            fora = STATUS_SAIU if conta.get("ja_esteve_no_grupo") else STATUS_NUNCA_ENTROU
            atualizar_status(apelido, status_grupo=fora, status_sessao=SESSAO_OK,
                             erro="grupo não encontrado no cache desta conta")
            return (fora, SESSAO_OK)

    except errors.FloodWaitError as e:
        # Não dá para concluir nada: preserva o estado anterior e sai quieto.
        atualizar_status(apelido, erro=f"FloodWait de {e.seconds}s — checagem adiada")
        if EXIBIR_LOGS:
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
        if EXIBIR_LOGS:
            logger.error(f"❌ [Pool] Erro ao checar '{apelido}': {type(e).__name__}: {e}")
        return (conta.get("status_grupo"), conta.get("status_sessao"))

    finally:
        if cliente is not None:
            try:
                await cliente.disconnect()
            except Exception:
                pass


async def sincronizar_pool():
    """
    A rotina completa, para pendurar no APScheduler (sugestão: 10 em 10 min).

      1. checa conta por conta contra o Telegram
      2. redistribui os postos conforme o resultado
      3. devolve a lista de mudanças

    É idempotente: rodar duas vezes seguidas não muda nada na segunda.
    """
    inicializar_tabelas()
    contas = listar_contas()
    if not contas:
        if EXIBIR_LOGS:
            logger.info("👥 [Pool] Nenhuma conta cadastrada ainda. Use: python3 pool_contas.py login")
        return []

    grupo_id = obter_grupo_autorais()
    if EXIBIR_LOGS:
        logger.info(f"🔍 [Pool] Checando {len(contas)} conta(s) contra o grupo {grupo_id}...")

    for conta in contas:
        # Uma pausa curta entre contas: várias conexões simultâneas com o mesmo
        # API_ID é o caminho mais rápido para tomar FloodWait.
        await checar_conta(conta, grupo_id)
        await asyncio.sleep(2)

    return aplicar_funcoes()


# =============================================================================
# 8. LOGIN E ADOÇÃO DE SESSÕES EXISTENTES
# =============================================================================

async def login_interativo(apelido=None):
    """
    Loga uma conta NOVA pelo terminal e cadastra tudo automaticamente.

    Fluxo: telefone → código do SMS/app → senha de 2FA (se houver) → get_me()
    → cifra a StringSession → grava → checa o grupo → redistribui os postos.

    É o "na hora que eu logar no servidor com outro usuário, a tabela atualiza
    sozinha com nome, id e tudo mais".
    """
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.errors import SessionPasswordNeededError

    inicializar_tabelas()

    if not API_ID or not API_HASH:
        print("❌ API_ID / API_HASH não encontrados no .env.")
        return None

    telefone = input("📱 Telefone com DDI (ex: +5532999998888): ").strip()

    cliente = TelegramClient(StringSession(), API_ID, API_HASH)
    await cliente.connect()

    senha_2fa = None
    try:
        await cliente.send_code_request(telefone)
        codigo = input("🔑 Código recebido no Telegram: ").strip()
        try:
            await cliente.sign_in(telefone, codigo)
        except SessionPasswordNeededError:
            # getpass: a senha não aparece na tela nem no histórico do bash.
            senha_2fa = getpass.getpass("🔐 Senha da verificação em duas etapas: ")
            await cliente.sign_in(password=senha_2fa)
    except Exception as e:
        print(f"❌ Falha no login: {type(e).__name__}: {e}")
        await cliente.disconnect()
        return None

    eu = await cliente.get_me()
    sessao = cliente.session.save()
    await cliente.disconnect()

    if not apelido:
        sugestao = (eu.username or f"conta{eu.id}").lower()
        apelido = input(f"🏷️  Apelido para esta conta [{sugestao}]: ").strip() or sugestao

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
    print(f"✅ Conta '{apelido}' cadastrada (id {eu.id}). Sessão gravada cifrada.")

    conta = obter_conta(apelido)
    status = await checar_conta(conta)
    print(f"📍 Situação no grupo dos Autorais: {status[0]}")

    mudancas = aplicar_funcoes()
    if mudancas:
        print("🔄 Postos redistribuídos:")
        for funcao, _antigo, novo, motivo in mudancas:
            quem = obter_conta_da_funcao(funcao)
            print(f"   • {funcao}: {quem['apelido'] if quem else 'VAGO'} — {motivo}")
    else:
        print("ℹ️  Nenhum posto mudou (os dois já estavam ocupados e saudáveis).")
    return apelido


async def adotar_sessoes_existentes():
    """
    Importa para o pool as contas que JÁ estão logadas no servidor pelos
    arquivos .session antigos, sem refazer login nenhum.

    Converte cada arquivo .session para StringSession, cifra e cadastra. Os
    arquivos originais continuam onde estão — nada é apagado, para não correr o
    risco de derrubar os serviços que ainda os usam.
    """
    from telethon import TelegramClient
    from telethon.sessions import StringSession

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
        try:
            cliente = TelegramClient(nome_arquivo, API_ID, API_HASH)
            await cliente.connect()
            if not await cliente.is_user_authorized():
                print(f"⚠️  {nome_arquivo}: existe mas não está autorizada. Pulando.")
                await cliente.disconnect()
                continue

            eu = await cliente.get_me()
            # Converte a sessão de ARQUIVO para TEXTO reaproveitando a auth_key
            # que já existe (não refaz login, não gasta SMS, não desloga nada).
            # StringSession.save() aceita qualquer objeto de sessão do Telethon.
            sessao_texto = StringSession.save(cliente.session)
            await cliente.disconnect()

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
            encontradas += 1
        except Exception as e:
            print(f"❌ Erro ao adotar {nome_arquivo}: {type(e).__name__}: {e}")

    if encontradas:
        print("\n🔍 Checando situação de cada uma no grupo...")
        await sincronizar_pool()
    return encontradas


async def entrar_no_grupo(apelido):
    """
    Faz a conta entrar no grupo dos Autorais usando um link de convite guardado
    na configuração. Serve para o caso "acabei de logar a conta 5, coloca ela lá
    dentro" sem precisar abrir o Telegram no celular.

    Para guardar o link uma vez:
        python3 pool_contas.py convite https://t.me/+xxxxxxxx
    """
    from telethon import functions
    from telethon.errors import UserAlreadyParticipantError, InviteHashExpiredError

    inicializar_tabelas()
    conta = obter_conta(apelido)
    if not conta:
        print(f"❌ Conta '{apelido}' não encontrada.")
        return False

    conexao = _obter_conexao()
    cursor = conexao.cursor()
    cursor.execute("SELECT valor FROM configuracoes WHERE chave = ?", (CHAVE_CONVITE,))
    linha = cursor.fetchone()
    conexao.close()
    if not linha or not linha["valor"]:
        print("❌ Nenhum link de convite guardado. Use: python3 pool_contas.py convite <link>")
        return False

    link = json.loads(linha["valor"])
    hash_convite = link.rstrip("/").split("/")[-1].lstrip("+")

    cliente = await criar_cliente(conta)
    if not cliente:
        return False
    try:
        await cliente(functions.messages.ImportChatInviteRequest(hash_convite))
        print(f"✅ {apelido} entrou no grupo.")
        registrar_evento(apelido, "ENTROU_NO_GRUPO", "via link de convite")
    except UserAlreadyParticipantError:
        print(f"ℹ️  {apelido} já estava no grupo.")
    except InviteHashExpiredError:
        print("❌ O link de convite expirou. Gere um novo e regrave com o comando 'convite'.")
        return False
    except Exception as e:
        print(f"❌ Falha ao entrar: {type(e).__name__}: {e}")
        return False
    finally:
        await cliente.disconnect()

    await checar_conta(obter_conta(apelido))
    aplicar_funcoes()
    return True


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
    postos = {}
    for funcao, conta_id in ocupacao.items():
        postos.setdefault(conta_id, []).append(funcao)

    if not contas:
        return "👥 Nenhuma conta cadastrada.\n   Cadastre com: python3 pool_contas.py login"

    linhas = ["👥 CONTAS DO POOL", ""]
    for c in contas:
        icone = ICONES_GRUPO.get(c["status_grupo"], "❓")
        trabalho = postos.get(c["id"], [])
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
        linhas.append(f"    id {c['user_id'] or '?'} · @{c['username'] or 'sem @'} · "
                      f"{c['nome_exibicao'] or '?'}")
        linhas.append(f"    grupo: {c['status_grupo']}{saude}")
        linhas.append(f"    pode: {c['funcoes_permitidas']} · prioridade {c['prioridade']}")
        if c["ultima_checagem"]:
            linhas.append(f"    checada em {c['ultima_checagem']}")
        if c["ultimo_erro"]:
            linhas.append(f"    último erro: {c['ultimo_erro']}")
        linhas.append("")

    linhas.append("─" * 50)
    for funcao in FUNCOES:
        conta = obter_conta_da_funcao(funcao)
        linhas.append(f"🎯 {funcao.upper():<12} → {conta['apelido'] if conta else '⚠️ VAGO'}")
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

    print("\n🧪 CENÁRIO 1 — conta 1 espelha, conta 2 reposta")
    contas = [_conta_falsa(1, "u1", STATUS_NO_GRUPO), _conta_falsa(2, "u2", STATUS_NO_GRUPO)]
    ocupacao, _ = resolver_funcoes(contas, {FUNCAO_ESPELHO: None, FUNCAO_REPOSTAGEM: None})
    conferir("espelho", ocupacao[FUNCAO_ESPELHO], 1)
    conferir("repostagem", ocupacao[FUNCAO_REPOSTAGEM], 2)

    print("\n🧪 CENÁRIO 2 — a conta 2 sai e a conta 3 entra")
    contas = [_conta_falsa(1, "u1", STATUS_NO_GRUPO), _conta_falsa(2, "u2", STATUS_SAIU),
              _conta_falsa(3, "u3", STATUS_NO_GRUPO)]
    ocupacao, mudancas = resolver_funcoes(contas, ocupacao)
    conferir("espelho continua com a 1", ocupacao[FUNCAO_ESPELHO], 1)
    conferir("repostagem passa para a 3", ocupacao[FUNCAO_REPOSTAGEM], 3)
    conferir("houve exatamente 2 movimentos", len(mudancas), 2)

    print("\n🧪 CENÁRIO 3 — a conta 4 entra no grupo com tudo ocupado")
    contas.append(_conta_falsa(4, "u4", STATUS_NO_GRUPO))
    ocupacao, mudancas = resolver_funcoes(contas, ocupacao)
    conferir("espelho intacto", ocupacao[FUNCAO_ESPELHO], 1)
    conferir("repostagem intacta", ocupacao[FUNCAO_REPOSTAGEM], 3)
    conferir("a 4 ficou de reserva (nada mudou)", len(mudancas), 0)

    print("\n🧪 CENÁRIO 4 — todas saem, só a conta 5 fica: ela acumula tudo")
    contas = [_conta_falsa(1, "u1", STATUS_SAIU), _conta_falsa(3, "u3", STATUS_SAIU),
              _conta_falsa(4, "u4", STATUS_SAIU), _conta_falsa(5, "u5", STATUS_NO_GRUPO)]
    ocupacao, _ = resolver_funcoes(contas, ocupacao)
    conferir("espelho com a 5", ocupacao[FUNCAO_ESPELHO], 5)
    conferir("repostagem também com a 5", ocupacao[FUNCAO_REPOSTAGEM], 5)

    print("\n🧪 CENÁRIO 5 — ninguém no grupo: os dois postos ficam VAGOS")
    contas = [_conta_falsa(5, "u5", STATUS_BANIDA_GRUPO)]
    ocupacao, _ = resolver_funcoes(contas, ocupacao)
    conferir("espelho vago", ocupacao[FUNCAO_ESPELHO], None)
    conferir("repostagem vaga", ocupacao[FUNCAO_REPOSTAGEM], None)

    print("\n🧪 CENÁRIO 6 — conta restrita a uma função só")
    contas = [_conta_falsa(6, "u6", STATUS_NO_GRUPO, funcoes="repostagem"),
              _conta_falsa(7, "u7", STATUS_NO_GRUPO, funcoes="espelho")]
    ocupacao, _ = resolver_funcoes(contas, {FUNCAO_ESPELHO: None, FUNCAO_REPOSTAGEM: None})
    conferir("espelho só pode ser a 7", ocupacao[FUNCAO_ESPELHO], 7)
    conferir("repostagem só pode ser a 6", ocupacao[FUNCAO_REPOSTAGEM], 6)

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

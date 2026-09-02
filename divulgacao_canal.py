# 0. CONFIGURAÇÕES INICIAIS
EXIBIR_LOGS = True
import os
import json
import logging
import asyncio
import random
from datetime import datetime, timedelta
import re
from telethon import TelegramClient
from telethon.errors import FloodWaitError, PeerFloodError, ChatWriteForbiddenError, UserBannedInChannelError
from telethon.tl.functions.messages import GetForumTopicsRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
load_dotenv()
from utils import registrar_erro_json, salvar_nome_grupo

# ✅ Importando o nosso Cérebro Central
from api_gemini import gerar_texto_gemini

# 🕐 Trava de fuso centralizada: importar o modulo ja aplica America/Sao_Paulo.
from fuso import FUSO_STR, fuso_horario, configurar_logs

# 1. CREDENCIAIS DA CONTA
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
# A chave do Gemini e a cascata foram movidas para o módulo api_gemini.py com segurança.

# 2. CONFIGURAÇÃO DE LOGS 🚀
if EXIBIR_LOGS:
    logger = configurar_logs(__name__)

# 3. SISTEMA DE AUTOLIMPEZA E INICIALIZAÇÃO
def limpar_travas_fantasma(nome_sessao):
    import glob
    import os
    
    # ✅ NOVO: Destrói a trava de manutenção no exato segundo em que o script inicia
    if os.path.exists("trava_manutencao.txt"):
        try:
            os.remove("trava_manutencao.txt")
            print("🔓 [Auto-cura] Trava de manutenção removida! Monitoramento de erros reativado.")
        except:
            pass

    arquivos_trava = glob.glob(f"{nome_sessao}.session-journal") + glob.glob(f"{nome_sessao}.session.lock")
    for arquivo in arquivos_trava:
        try:
            os.remove(arquivo)
            if EXIBIR_LOGS: logger.info(f"🧹 [Auto-cura] Trava fantasma de crash removida: {arquivo}")
        except Exception as e:
            if EXIBIR_LOGS: logger.error(f"❌ [Auto-cura] Falha ao tentar remover trava {arquivo}: {e}")

# ✅ Limpa resíduos de reboot forçado no servidor antes de tocar na base de dados
limpar_travas_fantasma('sessao_divulgacao')

# O nome da sessão é mantido independente
def normalizar_alvo(alvo):
    """🔢 O get_entity só resolve ID numérico quando recebe int. Com string ele
    tenta interpretar como @usuario, não acha e falha — mesmo a conta estando
    no canal. Links e @usuarios seguem como texto."""
    texto = str(alvo).strip()
    if re.fullmatch(r"-?\d+", texto):
        return int(texto)
    return texto


client = TelegramClient('sessao_divulgacao', API_ID, API_HASH)
scheduler = AsyncIOScheduler()

# 🚦 Semáforo de proteção assíncrona para o banco de dados SQLite
telegram_lock = asyncio.Lock()
if EXIBIR_LOGS: logger.info("🚦 Semáforo de controle de tráfego do Telegram ativado!")

import sqlite3

def ler_config_bd_divulgacao(chave, padrao=None):
    if padrao is None: padrao = {}
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,))
        resultado = cursor.fetchone()
        conexao.close()
        if resultado:
            return json.loads(resultado[0])
        return padrao
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao ler '{chave}' do SQLite: {e}")
        return padrao

def salvar_config_bd_divulgacao(chave, dados):
    try:
        conexao = sqlite3.connect("banco_dados.db", timeout=20.0)
        cursor = conexao.cursor()
        dados_str = json.dumps(dados, ensure_ascii=False)
        cursor.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)", (chave, dados_str))
        conexao.commit()
        conexao.close()
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Erro ao salvar '{chave}' no SQLite: {e}")

# 4. MOTOR UNIFICADO DE DIVULGAÇÃO
# ✅ Consolidação: Principal, Viral e Público usam o MESMO motor. Antes eram
# blocos clonados e toda correção precisava ser aplicada N vezes — na prática
# nunca era (a validação de alvo só existia no Viral). Para criar um escopo
# novo agora basta acrescentar uma entrada neste dicionário.
ESCOPOS = {
    "principal": {
        "rotulo": "PRINCIPAL",
        "chave": "alvos_divulgacao",
        "rotulo_link": "LINK PARA O GRUPO:",
        "link": "https://t.me/shopee_video_afiliado",
        "prompt": (
            "Você atua como um copywriter persuasivo e focado em conversão, divulgando um grupo do Telegram exclusivo para afiliados da Shopee. "
            "Crie UMA ÚNICA FRASE curta, altamente chamativa, convidativa e diferente de todas as anteriores. A cada nova solicitação, varie completamente a estrutura, o tom e a estratégia de persuasão para garantir originalidade."
            "Foque em atrair o usuário oferecendo acesso imediato a um acervo de ouro com vídeos prontos e validados que aumentam as comissões e visualizações na plataforma. "
            "É OBRIGATÓRIO informar organicamente na frase que o acesso ao grupo é GRÁTIS (exatamente assim, em letras maiúsculas). "
            "OBRIGATÓRIO: Inicie a sua resposta com uma sequência de 10 a 15 emojis repetidos de impacto (como 🚨, 🚀, ⚠️, 🔥 ou 💰) para criar uma forte barreira visual na tela, trocando a combinação a cada execução. "
            "Use um tom entusiasmado, adicione outros emojis variados ao longo do texto para despertar interesse orgânico, mas sem parecer apelativo ou alarmista. "
            "Entregue APENAS a frase final, sem aspas."
        ),
        "fallback": "🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨\nQuer turbinar suas vendas hoje? Acesse nosso acervo de ouro com vídeos validados e prontos para viralizar na Shopee!",
    },
    "viral": {
        "rotulo": "VIRAL",
        "chave": "alvos_divulgacao_viral",
        "rotulo_link": "LINK PARA O GRUPO VIRAL:",
        "link": "https://t.me/acervo_viral_shopee",
        "prompt": (
            "Você atua como um copywriter persuasivo e focado em conversão, divulgando um grupo do Telegram exclusivo para afiliados da Shopee chamado 'Acervo Viral Shopee'. "
            "Crie UMA ÚNICA FRASE curta, altamente chamativa, convidativa e diferente de todas as anteriores. "
            "Foque em atrair os afiliados oferecendo acesso imediato aos vídeos mais virais, achados do TikTok e tendências do momento, mantendo a mesma pegada agressiva de aumentar comissões e faturamento em alta. "
            "É OBRIGATÓRIO informar organicamente na frase que o acesso ao grupo é GRÁTIS (exatamente assim, em letras maiúsculas). "
            "OBRIGATÓRIO: Inicie a sua resposta com uma sequência de 10 a 15 emojis repetidos de impacto (como 🚨, 🚀, ⚠️, 🔥 ou 💰) para criar uma forte barreira visual na tela. "
            "Use um tom entusiasmado e adicione outros emojis variados. Entregue APENAS a frase final, sem aspas."
        ),
        "fallback": "🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨\nAfiliado, venha pegar os produtos mais virais e bombados do momento no nosso acervo 100% GRÁTIS!",
    },
    "publico": {
        "rotulo": "PÚBLICO",
        "chave": "alvos_divulgacao_publico",
        "rotulo_link": "ENTRE NO GRUPO:",
        "link": "https://t.me/GrupoPublicoAfiliados",
        # Lista = rodízio. Um ângulo é sorteado a cada disparo.
        # Para criar um terceiro, acrescente uma string aqui.
        "prompt": [
            # Ângulo 1 — comunidade
            "Você é um copywriter que divulga uma comunidade do Telegram para afiliados da Shopee. "
            "Escreva UMA ÚNICA FRASE curta e convidativa, diferente das anteriores, variando estrutura e tom a cada execução. "
            "Destaque que é uma comunidade ativa onde os membros trocam vídeos, achados e experiências, e que a entrada é GRÁTIS (exatamente assim, em maiúsculas). "
            "Use no máximo 3 emojis no total, distribuídos naturalmente pelo texto. "
            "Tom cordial e direto, como quem convida um colega — nada de urgência artificial ou alarmismo. "
            "Entregue APENAS a frase final, sem aspas.",

            # Ângulo 2 — o baixador de vídeos (fatos vindos do downloader_bot.py)
            "Você é um copywriter que divulga uma comunidade do Telegram para afiliados da Shopee. "
            "Escreva UMA ÚNICA FRASE curta e convidativa, diferente das anteriores, variando estrutura e tom a cada execução. "
            "Destaque que dentro do grupo tem um robô que baixa vídeos SEM MARCA D'ÁGUA de Shopee, TikTok, Pinterest e Instagram: "
            "o afiliado cola o link e recebe o arquivo pronto para postar. NÃO cite YouTube, que ainda não funciona. "
            "Mencione que a entrada é GRÁTIS (exatamente assim, em maiúsculas). "
            "Use no máximo 3 emojis no total, distribuídos naturalmente pelo texto. "
            "Tom cordial e direto, como quem indica uma ferramenta útil — nada de urgência artificial ou alarmismo. "
            "Entregue APENAS a frase final, sem aspas.",
        ],
        "fallback": "📬 Comunidade de afiliados Shopee: vídeos, achados e um robô que baixa vídeos sem marca d'água. Entrada GRÁTIS.",
    },
    "achadinhos": {
        "rotulo": "ACHADINHOS",
        "chave": "alvos_divulgacao_achadinhos",
        "rotulo_link": "ENTRE NO CANAL:",
        "link": "https://t.me/centraldeachadinhosvip",
        "prompt": (
            "Você é um copywriter que divulga um canal do Telegram de achadinhos e ofertas da Shopee. "
            "Escreva UMA ÚNICA FRASE curta e convidativa, diferente das anteriores, variando estrutura e tom a cada execução. "
            "Destaque que o canal garimpa ofertas e cupons de forma automática, o dia inteiro, e que a entrada é GRÁTIS (exatamente assim, em maiúsculas). "
            "Use no máximo 3 emojis no total, distribuídos naturalmente pelo texto. "
            "Tom cordial e direto, como quem indica um achado para um amigo — nada de urgência artificial ou alarmismo. "
            "Entregue APENAS a frase final, sem aspas."
        ),
        "fallback": "🛍️ Central de Achadinhos: ofertas e cupons da Shopee garimpados automaticamente, o dia todo. Entrada GRÁTIS.",
    },
}

# 🛡️ Cooldown global de flood. Quando o Telegram devolve FloodWait/PeerFlood,
# TODOS os escopos param até a punição expirar. Sem isto os jobs já agendados
# seguiam batendo na porta durante o castigo — que é o caminho de uma limitação
# temporária virar permanente.
bloqueio_flood_ate = None


# Escopos que já avisaram "config ausente". Sem isto o monitorar_comandos(),
# que roda de 5 em 5 segundos, repetiria o mesmo aviso ~17 mil vezes por dia
# por escopo. Avisa uma vez e rearma se a configuração aparecer depois.
_avisos_config_ausente = set()


def carregar_config_escopo(escopo):
    conf = ESCOPOS[escopo]
    dados = ler_config_bd_divulgacao(conf["chave"], padrao=None)

    if not dados:
        if escopo not in _avisos_config_ausente:
            _avisos_config_ausente.add(escopo)
            if EXIBIR_LOGS:
                logger.warning(f"⚠️ [{conf['rotulo']}] Configuração '{conf['chave']}' ainda não existe no banco. Ela é criada quando você abre o painel no bot principal. Este aviso não se repete.")
    elif escopo in _avisos_config_ausente:
        _avisos_config_ausente.discard(escopo)
        if EXIBIR_LOGS:
            logger.info(f"✅ [{conf['rotulo']}] Configuração '{conf['chave']}' encontrada no banco.")

    return dados


async def gerar_texto(escopo, repeticoes=1):
    conf = ESCOPOS[escopo]
    if EXIBIR_LOGS: logger.info(f"🚀 [{conf['rotulo']}] Montando texto de divulgação ({repeticoes}x)...")

    # "prompt" aceita uma string (um ângulo só) ou uma lista de strings.
    # Sendo lista, sorteia um ângulo por disparo. Para dar rodízio a qualquer
    # escopo, basta transformar a string dele numa lista.
    p = conf["prompt"]
    prompt_escolhido = random.choice(p) if isinstance(p, list) else p

    frase_ia = await gerar_texto_gemini(prompt_escolhido, EXIBIR_LOGS)
    if not frase_ia:
        if EXIBIR_LOGS: logger.error(f"❌ [{conf['rotulo']}] Todos os modelos falharam. Usando frase padrão de segurança.")
        frase_ia = conf["fallback"]

    bloco_unico = f"{frase_ia}\n\n{conf['rotulo_link']}👇\n{conf['link']}"

    if repeticoes <= 1:
        return bloco_unico
    return "\n\n\n".join([bloco_unico] * repeticoes)


async def enviar_mensagem(escopo, alvo):
    global bloqueio_flood_ate
    conf = ESCOPOS[escopo]
    rotulo = conf["rotulo"]

    # 🛡️ Respeita castigo de flood vigente, tenha ele vindo de qualquer escopo.
    if bloqueio_flood_ate and datetime.now() < bloqueio_flood_ate:
        restante = int((bloqueio_flood_ate - datetime.now()).total_seconds())
        if EXIBIR_LOGS: logger.warning(f"🛑 [{rotulo}] Disparo abortado: cooldown de flood ativo por mais {restante}s.")
        return

    config = carregar_config_escopo(escopo)
    if config and config.get("pausado", False):
        if EXIBIR_LOGS: logger.warning(f"🛑 [{rotulo}] Disparo cancelado: escopo pausado no momento.")
        return

    config_alvos = config.get("config_alvos", {}) if config else {}
    conf_alvo = config_alvos.get(alvo, {})

    replicas = conf_alvo.get("replicas", config.get("replicas_mensagem", 1) if config else 1)
    repeticoes = conf_alvo.get("repeticoes", config.get("repeticoes_internas", 1) if config else 1)

    texto = await gerar_texto(escopo, repeticoes)
    try:
        if EXIBIR_LOGS: logger.info(f"🚦 [{rotulo}] Aguardando sinal verde para {alvo}...")
        async with telegram_lock:
            # ✅ Proteção ativa: reconecta caso o socket tenha caído em background
            if not client.is_connected():
                if EXIBIR_LOGS: logger.info(f"🔄 [{rotulo}] [Auto-cura] Conexão perdida. Forçando reconexão...")
                await client.connect()

            entidade = await client.get_entity(normalizar_alvo(alvo))
            if EXIBIR_LOGS: logger.info(f"📤 [{rotulo}] Enviando {replicas} mensagem(ns) para {alvo}...")

            for i in range(replicas):
                await client.send_message(entidade, texto)
                if EXIBIR_LOGS: logger.info(f"📩 [{rotulo}] Mensagem {i+1}/{replicas} enviada.")
                if i < replicas - 1:
                    await asyncio.sleep(1.5)

            if EXIBIR_LOGS: logger.info(f"✅ [{rotulo}] Envio concluído para {alvo}.")

    except FloodWaitError as e:
        # ✅ Antes caía no except genérico e o agendador continuava disparando
        # DENTRO da janela de punição. Agora todo o motor congela.
        espera = int(getattr(e, "seconds", 60) or 60)
        bloqueio_flood_ate = datetime.now() + timedelta(seconds=espera + 30)
        if EXIBIR_LOGS: logger.error(f"⏳ [{rotulo}] FloodWait de {espera}s em {alvo}. Motor congelado até {bloqueio_flood_ate.strftime('%H:%M:%S')}.")
        registrar_erro_json(f"FloodWait {espera}s ({escopo}/{alvo})", origem="divulgacao_canal.py")

    except PeerFloodError:
        # 🚨 Sinal de conta marcada como spam. 1h de silêncio total.
        bloqueio_flood_ate = datetime.now() + timedelta(hours=1)
        if EXIBIR_LOGS: logger.critical(f"🚨 [{rotulo}] PeerFloodError em {alvo}: a CONTA foi sinalizada como spam. Motor congelado por 1 hora. Reduza frequência e réplicas antes de retomar.")
        registrar_erro_json(f"PeerFloodError ({escopo}/{alvo}) - conta sinalizada", origem="divulgacao_canal.py")

    except (ChatWriteForbiddenError, UserBannedInChannelError):
        if EXIBIR_LOGS: logger.warning(f"🚫 [{rotulo}] Sem permissão de escrita em {alvo} (restrito, silenciado ou banido). Omitindo.")

    except Exception as e:
        erro_str = str(e).lower()
        if "chat is restricted" in erro_str or "forbidden" in erro_str:
            if EXIBIR_LOGS: logger.warning(f"🚫 [{rotulo}] Omitido: o chat {alvo} é restrito ou a conta foi silenciada.")
        elif "database is locked" in erro_str:
            if EXIBIR_LOGS: logger.error(f"🔒 [{rotulo}] Bloqueio de concorrência no SQLite ao acessar {alvo}.")
        else:
            if EXIBIR_LOGS: logger.error(f"❌ [{rotulo}] Falha ao enviar para {alvo}: {e}")
            registrar_erro_json(f"enviar_mensagem ({escopo}/{alvo}): {e}", origem="divulgacao_canal.py")


# Agendamentos já sorteados na hora corrente, por alvo. COMPARTILHADO entre
# TODOS os escopos: se o mesmo grupo estiver em duas listas, a trava de 15
# minutos continua valendo entre elas.
#
# ⚠️ Guarda uma LISTA, não um datetime. A versão anterior sobrescrevia o valor
# e só comparava contra o ÚLTIMO horário sorteado — bastava intercalar escopos
# para furar a trava (14:15 e 14:18 conviviam porque a memória, naquele
# instante, guardava 14:57). Com 4 escopos o furo apareceria com mais força.
ultimos_agendamentos_por_alvo = {}


def _carregar_agendamentos():
    """Recupera do banco o histórico de horários já sorteados.

    Sem isto a trava de 15 minutos zerava a cada restart — e zerava justamente
    no pior momento, porque o main() reagenda a hora inteira ao subir. Um deploy
    no minuto 55 refazia a hora sem lembrar do que já tinha saído nela.
    """
    global ultimos_agendamentos_por_alvo
    try:
        bruto = ler_config_bd_divulgacao("agendamentos_divulgacao", {}) or {}
        recuperado = {}
        for alvo, horarios in bruto.items():
            lista = []
            for h in horarios or []:
                try:
                    lista.append(datetime.fromisoformat(h))
                except (TypeError, ValueError):
                    continue
            if lista:
                recuperado[alvo] = lista
        ultimos_agendamentos_por_alvo = recuperado
    except Exception as e:
        if EXIBIR_LOGS: logger.warning(f"⚠️ [Agenda] Não recuperei o histórico de horários: {e}")


def _salvar_agendamentos():
    try:
        salvar_config_bd_divulgacao("agendamentos_divulgacao", {
            alvo: [h.isoformat() for h in horarios]
            for alvo, horarios in ultimos_agendamentos_por_alvo.items()
        })
    except Exception as e:
        if EXIBIR_LOGS: logger.warning(f"⚠️ [Agenda] Não salvei o histórico de horários: {e}")


def programar_envios_da_hora():
    global ultimos_agendamentos_por_alvo
    agora = datetime.now()
    INTERVALO_MINIMO = 15  # Distanciamento rigoroso entre disparos no mesmo alvo

    # 💾 Recupera o que foi sorteado antes de um eventual restart.
    _carregar_agendamentos()

    # Descarta o que já passou da janela para o dicionário não crescer sem fim.
    corte = agora - timedelta(hours=1)
    for _alvo in list(ultimos_agendamentos_por_alvo):
        restantes = [h for h in ultimos_agendamentos_por_alvo[_alvo] if h > corte]
        if restantes:
            ultimos_agendamentos_por_alvo[_alvo] = restantes
        else:
            del ultimos_agendamentos_por_alvo[_alvo]

    for escopo, conf in ESCOPOS.items():
        rotulo = conf["rotulo"]
        config = carregar_config_escopo(escopo)

        if not config or not config.get("alvos") or config.get("pausado", False):
            continue

        alvos = config["alvos"]
        freq_global = config.get("frequencia_por_hora", 0)
        config_alvos = config.get("config_alvos", {})

        for alvo in alvos:
            conf_alvo = config_alvos.get(alvo, {})
            freq_alvo = conf_alvo.get("frequencia", freq_global)

            if freq_alvo <= 0:
                continue

            if EXIBIR_LOGS: logger.info(f"🔄 [{rotulo}] Sorteando {freq_alvo} envio(s) para {alvo} na hora atual ({agora.hour}h)...")
            espacamento_ideal = 58 // freq_alvo if freq_alvo > 0 else 58

            for i in range(freq_alvo):
                sucesso = False
                min_inicio_busca = (i * espacamento_ideal) + 1
                min_fim_busca = min(((i + 1) * espacamento_ideal), 59)
                if min_fim_busca <= min_inicio_busca:
                    min_fim_busca = 59

                for tentativa in range(100):
                    minuto_sorteado = random.randint(min_inicio_busca, min_fim_busca)
                    horario_disparo = agora.replace(minute=minuto_sorteado, second=random.randint(0, 59))

                    # ✅ Compara contra TODOS os horários já sorteados para este
                    # alvo nesta hora, não só contra o último.
                    agendados = ultimos_agendamentos_por_alvo.get(alvo, [])
                    colisao = any(
                        abs((horario_disparo - h).total_seconds() / 60) < INTERVALO_MINIMO
                        for h in agendados
                    )
                    if horario_disparo < agora:
                        colisao = True

                    if not colisao:
                        ultimos_agendamentos_por_alvo.setdefault(alvo, []).append(horario_disparo)
                        scheduler.add_job(enviar_mensagem, 'date', run_date=horario_disparo, args=[escopo, alvo])
                        if EXIBIR_LOGS: logger.info(f"✅ [{rotulo}] Disparo {i+1}/{freq_alvo} para {alvo} agendado às {horario_disparo.strftime('%H:%M:%S')}")
                        sucesso = True
                        break

                if not sucesso:
                    if EXIBIR_LOGS: logger.warning(f"⚠️ [{rotulo}] {alvo} [{i+1}/{freq_alvo}]: acionando fallback forçado.")
                    agendados = ultimos_agendamentos_por_alvo.get(alvo, [])
                    ultimo_conhecido = max(agendados) if agendados else agora
                    horario_disparo_fallback = ultimo_conhecido + timedelta(minutes=INTERVALO_MINIMO + random.randint(1, 3))
                    ultimos_agendamentos_por_alvo.setdefault(alvo, []).append(horario_disparo_fallback)
                    scheduler.add_job(enviar_mensagem, 'date', run_date=horario_disparo_fallback, args=[escopo, alvo])
                    if EXIBIR_LOGS: logger.info(f"🛡️ [{rotulo}] Fallback: disparo {i+1} empurrado para {horario_disparo_fallback.strftime('%H:%M:%S')}")

async def sincronizar_nomes_topicos():
    """🧵 Varre TODOS os grupos de fórum desta conta e grava, no cache
    compartilhado, o nome do grupo e o nome de cada tópico.

    Por que vive aqui e não no bot_mestre: a API de bot NÃO consegue ler nome
    de tópico — só devolve o message_thread_id. Só o MTProto (conta de usuário)
    tem o GetForumTopics. Como o cache fica no banco_dados.db compartilhado,
    todos os painéis passam a exibir 'Grupo › Tópico' de uma vez.

    Renomeou um tópico no Telegram? A próxima passagem atualiza sozinha.
    """
    grupos = topicos = 0
    try:
        if not client.is_connected():
            await client.connect()

        foruns = []
        async for dialogo in client.iter_dialogs():
            if getattr(dialogo.entity, "forum", False):
                foruns.append(dialogo.entity)

        for entidade in foruns:
            chat_id = f"-100{entidade.id}"
            salvar_nome_grupo(chat_id, entidade.title)
            grupos += 1

            try:
                # O lock é pego por chamada, não pela varredura inteira: segurar
                # por 30s atrasaria os disparos de divulgação sem necessidade.
                async with telegram_lock:
                    resposta = await client(GetForumTopicsRequest(
                        peer=entidade, offset_date=0, offset_id=0,
                        offset_topic=0, limit=100,
                    ))
                for t in resposta.topics:
                    titulo = getattr(t, "title", None)
                    if titulo:
                        # Chave no formato que o formatar_nome_alvo procura.
                        salvar_nome_grupo(f"{chat_id}_{t.id}", titulo)
                        topicos += 1
            except FloodWaitError as e:
                espera = int(getattr(e, "seconds", 60) or 60)
                if EXIBIR_LOGS: logger.warning(f"⏳ [Cache] FloodWait de {espera}s ao ler tópicos de {entidade.title}. Interrompendo a varredura.")
                break
            except Exception as e:
                if EXIBIR_LOGS: logger.warning(f"⚠️ [Cache] Não consegui ler os tópicos de {entidade.title}: {type(e).__name__}")

            await asyncio.sleep(1)  # respiro entre grupos

        if EXIBIR_LOGS:
            logger.info(f"🧵 [Cache] Sincronizado: {grupos} grupo(s) de fórum, {topicos} tópico(s) nomeados.")

    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ [Cache] Falha ao sincronizar nomes de tópicos: {e}")
        registrar_erro_json(f"sincronizar_nomes_topicos: {e}", origem="divulgacao_canal.py")


                    if EXIBIR_LOGS: logger.info(f"🛡️ [{rotulo}] Fallback: disparo {i+1} empurrado para {horario_disparo_fallback.strftime('%H:%M:%S')}")

    # 💾 Grava o que foi sorteado nesta hora, para sobreviver a restart.
    _salvar_agendamentos()


async def monitorar_comandos():
    while True:
        for escopo, conf in ESCOPOS.items():
            rotulo = conf["rotulo"]
            config = carregar_config_escopo(escopo)

            if not config or not config.get("forcar_disparo"):
                continue

            # Baixa a bandeira ANTES de disparar, para não repetir se algo travar.
            config["forcar_disparo"] = False
            salvar_config_bd_divulgacao(conf["chave"], config)

            if config.get("pausado", False):
                if EXIBIR_LOGS: logger.warning(f"🛑 [{rotulo}] Comando forçado ignorado: escopo pausado.")
                continue

            if EXIBIR_LOGS: logger.info(f"🚀 [{rotulo}] Comando de DISPARO FORÇADO detectado!")
            for alvo in config.get("alvos", []):
                await enviar_mensagem(escopo, alvo)

        await asyncio.sleep(5)

async def main():
    if EXIBIR_LOGS: logger.info("⏳ Iniciando o Userbot de Divulgação...")
    await client.start()

    # 🗂️ Popula o cache de entidades da sessão. Sem isto, get_entity() falha com
    # "Cannot find any entity" ao receber ID numérico puro, mesmo a conta
    # participando do canal — o Telethon precisa do access_hash em cache, e ele
    # só aparece depois de listar os diálogos ao menos uma vez.
    try:
        await client.get_dialogs()
        if EXIBIR_LOGS: logger.info("🗂️ Cache de entidades da sessão preenchido.")
    except Exception as e:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Não consegui preencher o cache de entidades: {e}")

    # Inicia a tarefa paralela que vigia o arquivo JSON a cada 5 segundos
    asyncio.create_task(monitorar_comandos())
    
    # Executa imediatamente o agendamento da hora atual ao iniciar o script
    programar_envios_da_hora()
    
    # Agenda a função para rodar toda vez que o relógio virar a hora (minuto 0)
    scheduler.add_job(programar_envios_da_hora, 'cron', minute=0)

    # 🧵 Nomes de grupo e tópico para o cache compartilhado, uma vez por dia.
    # 00:07 e não 00:00: a virada do dia já tem o programar_envios_da_hora e a
    # coleta de métricas: separar evita os três disputando o mesmo instante.
    scheduler.add_job(sincronizar_nomes_topicos, 'cron', hour=0, minute=7)
    asyncio.create_task(sincronizar_nomes_topicos())  # primeira carga na subida
    
    scheduler.start()
    if EXIBIR_LOGS: logger.info("🤖 Sistema automático rodando. Pressione Ctrl+C para parar.")
    
    # Mantém a sessão do Telegram aberta escutando os eventos do agendador
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())

"""
Robô de divulgação (serviço divulgacao_canal_bot). Uma conta de usuário do
Telegram (Telethon, sessão sessao_divulgacao) posta convites para os grupos e
canais do projeto nos grupos-alvo configurados no painel do bot_mestre.

Cada escopo (principal, viral, público, achadinhos) tem a própria lista de alvos
e frequência por hora, na tabela configuracoes. A cada hora cheia o robô sorteia
os horários de envio daquela hora; o texto de cada envio é escrito pelo Gemini
na hora, com uma frase reserva se a IA falhar.

Também mantém o cache de nomes de grupos e tópicos de fórum, que só uma conta de
usuário consegue ler.
"""
EXIBIR_LOGS = True
import os
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

from api_gemini import gerar_texto_gemini

# Importar fuso já trava o processo no horário de Brasília.
from fuso import configurar_logs

API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')

if EXIBIR_LOGS:
    logger = configurar_logs(__name__)

def limpar_travas_fantasma(nome_sessao):
    """
    Limpeza ao iniciar o processo:
    - apaga trava_manutencao.txt, religando o registro de erros que o botão
      "limpar logs" do bot_mestre silenciou (este robô reinicia a cada deploy);
    - apaga os .session-journal/.session.lock que um desligamento forçado deixa
      para trás e que travam a sessão do Telethon.
    """
    import glob
    import os
    
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

# Roda no import, antes de o TelegramClient abrir a sessão.
limpar_travas_fantasma('sessao_divulgacao')

def normalizar_alvo(alvo):
    """
    ID numérico vira int; link e @usuário continuam texto. O get_entity do
    Telethon só resolve ID numérico recebendo int: com string, procura como
    @usuário e falha mesmo com a conta no canal.
    """
    texto = str(alvo).strip()
    if re.fullmatch(r"-?\d+", texto):
        return int(texto)
    return texto


# A sessao_divulgacao é a conta principal do admin (@Rafaelnm, id 1226920464), o
# mesmo ADMIN_ID do bot_mestre. É ela que aparece em "Vídeo enviado por" nos reposts.
client = TelegramClient('sessao_divulgacao', API_ID, API_HASH)
scheduler = AsyncIOScheduler()

# Uma chamada ao Telegram por vez nesta conta, para envios e leitura de tópicos não se atropelarem.
telegram_lock = asyncio.Lock()
if EXIBIR_LOGS: logger.info("🚦 Semáforo de controle de tráfego do Telegram ativado!")

import db

# Escopos de divulgação, todos tratados pelo mesmo código. Para criar um escopo,
# basta acrescentar uma entrada: chave = configuração no banco (criada pelo painel
# do bot_mestre), link = grupo divulgado, prompt = instrução para a IA,
# fallback = frase usada quando a IA falha.
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
        # Lista de prompts: um é sorteado a cada envio (rodízio de ângulos).
        "prompt": [
            # Ângulo 1: a comunidade.
            "Você é um copywriter que divulga uma comunidade do Telegram para afiliados da Shopee. "
            "Escreva UMA ÚNICA FRASE curta e convidativa, diferente das anteriores, variando estrutura e tom a cada execução. "
            "Destaque que é uma comunidade ativa onde os membros trocam vídeos, achados e experiências, e que a entrada é GRÁTIS (exatamente assim, em maiúsculas). "
            "Use no máximo 3 emojis no total, distribuídos naturalmente pelo texto. "
            "Tom cordial e direto, como quem convida um colega — nada de urgência artificial ou alarmismo. "
            "Entregue APENAS a frase final, sem aspas.",

            # Ângulo 2: o robô que baixa vídeos (o que ele faz está no downloader_bot.py).
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

# Até quando o robô fica parado por punição de flood. Vale para todos os escopos:
# continuar enviando durante o castigo é o caminho para a limitação temporária
# virar permanente.
bloqueio_flood_ate = None


# Escopos que já avisaram "config ausente". O monitorar_comandos roda a cada 5 s
# e repetiria o aviso ~17 mil vezes por dia; assim avisa uma vez e volta a avisar
# só se a configuração aparecer e sumir de novo.
_avisos_config_ausente = set()


def carregar_config_escopo(escopo):
    """
    Configuração do escopo no banco (alvos, frequencia_por_hora, pausado,
    réplicas, repetições, config_alvos por alvo) ou None se ainda não existir.
    """
    conf = ESCOPOS[escopo]
    dados = db.ler_config(conf["chave"], padrao=None)

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
    """
    Texto de um envio: frase escrita pela IA + link do grupo. Com repeticoes > 1,
    o mesmo bloco aparece várias vezes na mesma mensagem.
    """
    conf = ESCOPOS[escopo]
    if EXIBIR_LOGS: logger.info(f"🚀 [{conf['rotulo']}] Montando texto de divulgação ({repeticoes}x)...")

    # prompt pode ser uma string ou uma lista; sendo lista, sorteia um por envio.
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
    """
    Envia a divulgação do escopo para um alvo: `replicas` mensagens seguidas
    (1,5 s entre elas), cada uma com o bloco repetido `repeticoes` vezes. Os dois
    números vêm do alvo (config_alvos) ou do escopo. Não envia durante punição
    de flood nem com o escopo pausado.

    FloodWait para todos os escopos pelo tempo pedido pelo Telegram + 30 s.
    PeerFlood (conta marcada como spam) para tudo por 1 hora. Alvo sem permissão
    de escrita é só pulado.
    """
    global bloqueio_flood_ate
    conf = ESCOPOS[escopo]
    rotulo = conf["rotulo"]

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
            # A conexão pode ter caído em segundo plano.
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
        espera = int(getattr(e, "seconds", 60) or 60)
        bloqueio_flood_ate = datetime.now() + timedelta(seconds=espera + 30)
        if EXIBIR_LOGS: logger.error(f"⏳ [{rotulo}] FloodWait de {espera}s em {alvo}. Motor congelado até {bloqueio_flood_ate.strftime('%H:%M:%S')}.")
        registrar_erro_json(f"FloodWait {espera}s ({escopo}/{alvo})", origem="divulgacao_canal.py")

    except PeerFloodError:
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


# Horários já sorteados por alvo (última hora), compartilhados entre os escopos:
# se o mesmo grupo está em duas listas, os 15 minutos de distância valem entre
# elas. Guarda a lista inteira porque comparar só com o último horário deixava
# escopos intercalados furarem a distância.
ultimos_agendamentos_por_alvo = {}


def _carregar_agendamentos():
    """
    Recupera do banco (chave agendamentos_divulgacao) os horários já sorteados,
    para a distância de 15 min valer também depois de um reinício.
    """
    global ultimos_agendamentos_por_alvo
    try:
        bruto = db.ler_config("agendamentos_divulgacao", {}) or {}
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
    """Grava no banco os horários sorteados, para sobreviverem a um reinício."""
    try:
        db.salvar_config("agendamentos_divulgacao", {
            alvo: [h.isoformat() for h in horarios]
            for alvo, horarios in ultimos_agendamentos_por_alvo.items()
        })
    except Exception as e:
        if EXIBIR_LOGS: logger.warning(f"⚠️ [Agenda] Não salvei o histórico de horários: {e}")


def _carregar_plano_da_hora(hora):
    """
    Envios já planejados para a hora `hora` ("AAAA-MM-DD HH"), como lista de
    [escopo, alvo, horário ISO]. Vazia se o plano salvo é de outra hora.
    """
    plano = db.ler_config("plano_divulgacao_hora", {}) or {}
    if not isinstance(plano, dict) or plano.get("hora") != hora:
        return []
    validos = []
    for envio in plano.get("envios", []):
        try:
            escopo, alvo, iso = envio
            datetime.fromisoformat(iso)
        except (TypeError, ValueError):
            continue
        validos.append([escopo, alvo, iso])
    return validos


def _salvar_plano_da_hora(hora, envios):
    """Grava no banco o plano da hora (chave plano_divulgacao_hora); só a hora corrente fica guardada."""
    db.salvar_config("plano_divulgacao_hora", {"hora": hora, "envios": envios})


def _agendar_envio(escopo, alvo, quando):
    # O id torna o agendamento idempotente: reagendar o mesmo envio substitui o anterior.
    scheduler.add_job(enviar_mensagem, 'date', run_date=quando, args=[escopo, alvo],
                      id=f"divulgacao|{escopo}|{alvo}|{quando.isoformat()}", replace_existing=True)


def programar_envios_da_hora():
    """
    Sorteia e agenda os envios da hora corrente para todos os escopos e alvos.
    Roda a cada hora cheia e uma vez quando o robô inicia.

    Cada alvo recebe `frequencia` envios, um em cada fatia da hora, a 15 min ou
    mais de qualquer outro envio para o mesmo alvo (de qualquer escopo) e nunca
    no passado. Se 100 sorteios não acharem minuto livre na fatia, o envio vai
    para 16 a 18 min depois do último do alvo, mesmo que caia na hora seguinte.

    Os agendamentos ficam na memória do agendador e se perdem num reinício. Por
    isso o plano da hora fica salvo no banco: ao reiniciar no meio da hora, os
    envios planejados que ainda estão no futuro são reagendados, os que já
    passaram contam como feitos, e só o que falta para a frequência é sorteado.
    """
    agora = datetime.now()
    INTERVALO_MINIMO = 15  # minutos entre dois envios para o mesmo alvo
    hora_atual = agora.strftime("%Y-%m-%d %H")

    _carregar_agendamentos()
    plano = _carregar_plano_da_hora(hora_atual)

    # Esquece horários com mais de 1 hora, para o dicionário não crescer sem fim.
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

            ja_planejados = [datetime.fromisoformat(iso) for e, a, iso in plano if e == escopo and a == alvo]
            for quando in ja_planejados:
                if quando > agora:
                    _agendar_envio(escopo, alvo, quando)

            faltam = freq_alvo - len(ja_planejados)
            if ja_planejados and EXIBIR_LOGS:
                logger.info(f"♻️ [{rotulo}] {alvo}: {len(ja_planejados)} envio(s) já planejado(s) nesta hora; faltam {max(faltam, 0)}.")
            if faltam <= 0:
                continue

            if EXIBIR_LOGS: logger.info(f"🔄 [{rotulo}] Sorteando {faltam} envio(s) para {alvo} na hora atual ({agora.hour}h)...")
            espacamento_ideal = 58 // freq_alvo if freq_alvo > 0 else 58

            # Os envios que faltam ficam com as últimas fatias da hora.
            for i in range(len(ja_planejados), freq_alvo):
                sucesso = False
                min_inicio_busca = (i * espacamento_ideal) + 1
                min_fim_busca = min(((i + 1) * espacamento_ideal), 59)
                if min_fim_busca <= min_inicio_busca:
                    min_fim_busca = 59

                for tentativa in range(100):
                    minuto_sorteado = random.randint(min_inicio_busca, min_fim_busca)
                    horario_disparo = agora.replace(minute=minuto_sorteado, second=random.randint(0, 59))

                    agendados = ultimos_agendamentos_por_alvo.get(alvo, [])
                    colisao = any(
                        abs((horario_disparo - h).total_seconds() / 60) < INTERVALO_MINIMO
                        for h in agendados
                    )
                    if horario_disparo < agora:
                        colisao = True

                    if not colisao:
                        ultimos_agendamentos_por_alvo.setdefault(alvo, []).append(horario_disparo)
                        plano.append([escopo, alvo, horario_disparo.isoformat()])
                        _agendar_envio(escopo, alvo, horario_disparo)
                        if EXIBIR_LOGS: logger.info(f"✅ [{rotulo}] Disparo {i+1}/{freq_alvo} para {alvo} agendado às {horario_disparo.strftime('%H:%M:%S')}")
                        sucesso = True
                        break

                if not sucesso:
                    if EXIBIR_LOGS: logger.warning(f"⚠️ [{rotulo}] {alvo} [{i+1}/{freq_alvo}]: acionando fallback forçado.")
                    agendados = ultimos_agendamentos_por_alvo.get(alvo, [])
                    ultimo_conhecido = max(agendados) if agendados else agora
                    horario_disparo_fallback = ultimo_conhecido + timedelta(minutes=INTERVALO_MINIMO + random.randint(1, 3))
                    ultimos_agendamentos_por_alvo.setdefault(alvo, []).append(horario_disparo_fallback)
                    plano.append([escopo, alvo, horario_disparo_fallback.isoformat()])
                    _agendar_envio(escopo, alvo, horario_disparo_fallback)
                    if EXIBIR_LOGS: logger.info(f"🛡️ [{rotulo}] Fallback: disparo {i+1} empurrado para {horario_disparo_fallback.strftime('%H:%M:%S')}")

    _salvar_agendamentos()
    _salvar_plano_da_hora(hora_atual, plano)

async def sincronizar_nomes_topicos():
    """
    Grava no cache de nomes (utils.salvar_nome_grupo) o nome de cada grupo de
    fórum desta conta e de cada tópico, para os painéis mostrarem "Grupo › Tópico".

    Fica neste robô porque a API de bot não lê nome de tópico (só o ID); só uma
    conta de usuário (GetForumTopics) consegue. Roda ao iniciar e todo dia às
    00:07; tópico renomeado é atualizado na passagem seguinte. Interrompe a
    varredura no primeiro FloodWait.
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
                # Lock por chamada, não pela varredura inteira: segurar por ~30 s
                # atrasaria os envios de divulgação.
                async with telegram_lock:
                    resposta = await client(GetForumTopicsRequest(
                        peer=entidade, offset_date=0, offset_id=0,
                        offset_topic=0, limit=100,
                    ))
                for t in resposta.topics:
                    titulo = getattr(t, "title", None)
                    if titulo:
                        # Chave "<grupo>_<tópico>", o formato que o formatar_nome_alvo do bot_mestre procura.
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

async def monitorar_comandos():
    """
    A cada 5 s procura o pedido de disparo forçado que o painel do bot_mestre
    grava na config do escopo (forcar_disparo=True) e envia na hora para todos
    os alvos, salvo se o escopo estiver pausado.
    """
    while True:
        for escopo, conf in ESCOPOS.items():
            rotulo = conf["rotulo"]
            config = carregar_config_escopo(escopo)

            if not config or not config.get("forcar_disparo"):
                continue

            # Desliga o pedido antes de enviar, para não repetir se algo travar no meio.
            config["forcar_disparo"] = False
            db.salvar_config(conf["chave"], config)

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

    # Registra no log qual conta está logada nesta sessão.
    try:
        eu = await client.get_me()
        if EXIBIR_LOGS:
            logger.info(f"👤 [Userbot] Sessão de divulgação logada como: "
                        f"{getattr(eu, 'first_name', '')} (@{getattr(eu, 'username', None) or 'sem @'}) "
                        f"· id {getattr(eu, 'id', '?')}")
    except Exception as e:
        if EXIBIR_LOGS: logger.warning(f"⚠️ [Userbot] Não consegui identificar a conta da sessão: {e}")

    # Sem listar os diálogos uma vez, get_entity() falha com "Cannot find any entity"
    # para ID numérico, mesmo com a conta no canal: o Telethon precisa do access_hash
    # em cache.
    try:
        await client.get_dialogs()
        if EXIBIR_LOGS: logger.info("🗂️ Cache de entidades da sessão preenchido.")
    except Exception as e:
        if EXIBIR_LOGS: logger.warning(f"⚠️ Não consegui preencher o cache de entidades: {e}")

    asyncio.create_task(monitorar_comandos())
    
    programar_envios_da_hora()
    
    scheduler.add_job(programar_envios_da_hora, 'cron', minute=0)

    # 00:07 e não 00:00: a virada do dia já tem o programar_envios_da_hora e a
    # coleta de métricas, e separar evita os três disputando o mesmo instante.
    scheduler.add_job(sincronizar_nomes_topicos, 'cron', hour=0, minute=7)
    asyncio.create_task(sincronizar_nomes_topicos())
    
    scheduler.start()
    if EXIBIR_LOGS: logger.info("🤖 Sistema automático rodando. Pressione Ctrl+C para parar.")
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())

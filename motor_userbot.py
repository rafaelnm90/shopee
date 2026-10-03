"""
Robô motor_userbot (serviço motor_userbot_bot): uma conta de usuário do Telegram
(Telethon, sessão sessao_espiao) com dois trabalhos nos canais que ela enxerga.

Espião: captura os vídeos com link da Shopee postados nos canais-alvo (alvos_espiao)
para a fila de clonagem (configuracoes, chave fila_clonagem) e, em segundo plano,
pede à IA o nome do produto. Quem publica essa fila é o bot_mestre.

Espelhador: para cada rota de espelhos_config.json (origens -> destino), captura o
vídeo com link da Shopee, converte o link para afiliado e enfileira em
fila_espelhador.json. Um laço publica cada item no horário sorteado pelo motor_filas,
respeitando o atraso D+X e o teto diário da rota.

Também confere a cada minuto se alvos e rotas continuam acessíveis (status nos
painéis) e sincroniza os nomes dos tópicos de fórum.

Anti-duplicata (tabela registros_unicos): o mesmo link no mesmo contexto nas últimas
24 h, e o hash do arquivo de vídeo (últimos 1000 por contexto). O contexto é
"espiao", o chat de origem ou o destino de uma rota.

Posts do próprio sistema (esta conta ou o bot) são ignorados, menos no grupo
principal @shopee_video_afiliado: lá o bot posta e esses posts são espelhados de
propósito para outros canais.

O bot_mestre também importa este módulo (via painel_espelhos) só para ler e gravar
a fila do Espelhador.
"""
import os
import json
import asyncio
import re
from datetime import datetime, timedelta
import hashlib
from telethon import utils
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from dotenv import load_dotenv
from utils import registrar_erro_json, chave_cache_ia, consultar_cache_ia, gravar_cache_ia, normalizar_origens_rotas, salvar_json_atomico
from motor_filas import calcular_horarios_distribuicao, aplicar_limite_diario_fila, ler_faixa_limite
from zoneinfo import ZoneInfo

load_dotenv()

FUSO_STR = "America/Sao_Paulo"
fuso_horario = ZoneInfo(FUSO_STR)

# Pasta dos vídeos baixados temporariamente.
os.makedirs("temp", exist_ok=True)

# Importar fuso já trava o processo no horário de Brasília.
from fuso import FUSO_STR, fuso_horario, configurar_logs

API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')

from api_gemini import analisar_video_gemini
from api_shopee import converter_link_shopee

LIMITE_REGISTROS_HASH = 1000  # hashes de vídeo guardados por contexto na anti-duplicata

logger = configurar_logs(__name__)

def limpar_travas_fantasma(nome_sessao):
    """Apaga os .session-journal/.session.lock que um desligamento forçado deixa e que travam a sessão do Telethon."""
    import glob
    import os
    arquivos_trava = glob.glob(f"{nome_sessao}.session-journal") + glob.glob(f"{nome_sessao}.session.lock")
    for arquivo in arquivos_trava:
        try:
            os.remove(arquivo)
            logger.info(f"🧹 [Auto-cura] Trava fantasma de crash removida: {arquivo}")
        except Exception as e:
            logger.error(f"❌ [Auto-cura] Falha ao tentar remover trava {arquivo}: {e}")

# Só quando este arquivo roda como serviço, antes de o TelegramClient abrir a sessão.
# O bot_mestre também importa este módulo (via painel_espelhos) e não pode apagar a
# trava de uma sessão que o serviço motor_userbot está usando naquele momento.
if __name__ == "__main__":
    limpar_travas_fantasma('sessao_espiao')

# Conta da sessao_espiao: ainda não identificada no log (este robô não registra o
# get_me() ao iniciar). Ela precisa estar dentro de todos os canais vigiados; canal em
# que ela não está, este robô não enxerga. Outras sessões do servidor:
#   sessao_divulgacao         -> conta principal (@Rafaelnm, id 1226920464)
#   sessao_espelhador_isolado -> conta secundária (sem @, id 8940405855)
client = TelegramClient('sessao_espiao', API_ID, API_HASH)

import db
import random

def carregar_alvos():
    """Canais vigiados pelo Espião: "<chat>" ou "<chat>:<tópico>"."""
    dados = db.ler_config("alvos_espiao", padrao={"alvos": []})
    return dados.get("alvos", [])

def ler_excecao_ponte():
    """
    Destino configurado no painel dos Autorais (a "ponte"), em minúsculas, ou None.
    O Espião sempre escuta esse chat, mesmo que ele não esteja na lista de alvos.
    """
    dados = db.ler_config("autorais_config", padrao={})
    val = str(dados.get("destino", "")).strip().lower()
    return val if val else None

def garantir_tabela_registros_unicos():
    """Cria a tabela da anti-duplicata (links já espelhados e hashes de vídeo), se faltar."""
    conexao = db.conectar()
    try:
        conexao.execute('''
            CREATE TABLE IF NOT EXISTS registros_unicos (
                identificador TEXT,
                contexto TEXT,
                tipo TEXT,
                data_registro TEXT,
                PRIMARY KEY (identificador, contexto)
            )
        ''')
        conexao.commit()
    finally:
        conexao.close()

def verificar_e_registrar_espelho(link_shopee, contexto="global"):
    """
    True se o link já foi visto neste contexto nas últimas 24 h. Se não foi,
    registra e devolve False. Em erro de banco devolve False (deixa passar).
    """
    agora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conexao = db.conectar()
        cursor = conexao.cursor()
        
        cursor.execute("DELETE FROM registros_unicos WHERE tipo = 'espelho' AND contexto = ? AND datetime(data_registro) <= datetime('now', '-1 day')", (contexto,))
        
        cursor.execute("SELECT 1 FROM registros_unicos WHERE identificador = ? AND contexto = ? AND tipo = 'espelho'", (link_shopee, contexto))
        existe = cursor.fetchone()
        
        if existe:
            conexao.close()
            return True
            
        cursor.execute("INSERT INTO registros_unicos (identificador, contexto, tipo, data_registro) VALUES (?, ?, 'espelho', ?)", (link_shopee, contexto, agora_str))
        conexao.commit()
        conexao.close()
        return False
    except Exception as e:
        logger.error(f"❌ Erro ao verificar espelho no SQLite: {e}")
        return False

def calcular_hash_video(caminho_arquivo):
    """SHA-256 do arquivo (identifica o mesmo vídeo em qualquer canal), ou None se não der para ler."""
    hash_sha256 = hashlib.sha256()
    try:
        logger.info(f"🔍 A calcular a assinatura digital (SHA-256) do ficheiro: {caminho_arquivo}...")
        with open(caminho_arquivo, "rb") as f:
            for bloco in iter(lambda: f.read(4096), b""):
                hash_sha256.update(bloco)
        resultado = hash_sha256.hexdigest()
        logger.info(f"✅ Assinatura única identificada: {resultado[:10]}...")
        return resultado
    except Exception as e:
        logger.error(f"❌ Erro na leitura física para calcular hash do ficheiro {caminho_arquivo}: {e}")
        return None

def verificar_e_registrar_hash(hash_video, contexto="global"):
    """
    True se o hash já existe neste contexto. Se não existe, registra (guardando
    só os LIMITE_REGISTROS_HASH mais recentes) e devolve False. Erro devolve False.
    """
    agora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conexao = db.conectar()
        cursor = conexao.cursor()
        
        cursor.execute("SELECT 1 FROM registros_unicos WHERE identificador = ? AND contexto = ? AND tipo = 'hash'", (hash_video, contexto))
        existe = cursor.fetchone()
        
        if existe:
            conexao.close()
            return True
            
        cursor.execute("INSERT INTO registros_unicos (identificador, contexto, tipo, data_registro) VALUES (?, ?, 'hash', ?)", (hash_video, contexto, agora_str))
        
        cursor.execute(f"DELETE FROM registros_unicos WHERE tipo = 'hash' AND contexto = ? AND identificador NOT IN (SELECT identificador FROM registros_unicos WHERE tipo = 'hash' AND contexto = ? ORDER BY data_registro DESC LIMIT {LIMITE_REGISTROS_HASH})", (contexto, contexto))
        
        conexao.commit()
        conexao.close()
        return False
    except Exception as e:
        logger.error(f"❌ Erro ao verificar hash no SQLite: {e}")
        return False

def ler_fila_clonagem():
    """Fila do Espião (configuracoes, chave fila_clonagem), publicada pelo bot_mestre."""
    return db.ler_config("fila_clonagem", {"fila": []})

def salvar_fila_clonagem(dados):
    db.salvar_config("fila_clonagem", dados)

async def verificar_e_otimizar_video(caminho_video, relatorio=None):
    """
    Inspeciona a resolução física do arquivo.
    Se for inferior a 720p, realiza o upscaling com FFmpeg em background.

    O ficheiro é substituído NO MESMO CAMINHO (os.replace), por isso o retorno
    nunca muda e não serve para saber se houve trabalho. Quem precisa saber
    passa um dict em `relatorio` e recebe relatorio["upscaled"] = True quando o
    re-encode aconteceu de facto. Chamar sem o dict mantém o comportamento antigo.
    """
    if not caminho_video or not os.path.exists(caminho_video): return caminho_video
    
    try:
        logger.info(f"🔎 [Upscaling] Inspecionando resolução física de: {caminho_video}")
        
        comando_probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-select_streams", "v:0", 
            "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", caminho_video,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await comando_probe.communicate()
        dimensoes = stdout.decode().strip()
        
        if not dimensoes or "x" not in dimensoes:
            logger.warning("⚠️ [Upscaling] Falha ao ler metadados. Ignorando otimização.")
            return caminho_video
            
        largura, altura = map(int, dimensoes.split("x"))
        menor_dimensao = min(largura, altura)
        
        if menor_dimensao >= 720:
            logger.info(f"✅ [Upscaling] Qualidade aprovada ({largura}x{altura}). Nenhuma maquiagem necessária.")
            return caminho_video
            
        logger.info(f"🛠️ [Upscaling] Resolução baixa detectada ({largura}x{altura}). Iniciando renderização para 720p...")
        
        caminho_temp = f"{caminho_video}_upscaled.mp4"
        
        comando_ffmpeg = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", caminho_video, 
            "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black", 
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "copy", caminho_temp,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await comando_ffmpeg.communicate()
        
        
        if comando_ffmpeg.returncode == 0 and os.path.exists(caminho_temp):
            os.replace(caminho_temp, caminho_video)
            if relatorio is not None:
                relatorio["upscaled"] = True
            logger.info("✨ [Upscaling] Sucesso! Vídeo re-renderizado para 720x1280 e substituído.")
        else:
            logger.error("❌ [Upscaling] Falha na renderização do FFmpeg. Mantendo arquivo original.")
            if os.path.exists(caminho_temp): os.remove(caminho_temp)
            
    except Exception as e:
        logger.error(f"❌ [Upscaling] Erro na função de otimização: {e}")
        
    return caminho_video

def salvar_na_fila_clonagem(caminho_video, link_shopee, chat_origem="Desconhecida", nome_origem=None, msg_id=None):
    """Acrescenta um vídeo capturado pelo Espião à fila de clonagem, ainda não processado."""
    id_unico = f"clone_{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}"
    data_captura = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nome_origem_str = str(nome_origem) if nome_origem else str(chat_origem)
    
    try:
        dados = ler_fila_clonagem()
        item = {
            "id": id_unico,
            "chat_origem": str(chat_origem),
            "nome_origem": nome_origem_str,
            "msg_id": msg_id,
            "caminho_video": caminho_video,
            "link_original": link_shopee,
            "processado": False,
            "data_captura": data_captura
        }
        dados.setdefault("fila", []).append(item)
        salvar_fila_clonagem(dados)
        logger.info(f"📦 Clone salvo de forma unificada no SQLite com sucesso (ID: {id_unico}).")
    except Exception as e:
        logger.error(f"❌ Erro ao salvar na fila unificada do SQLite: {e}")

def registrar_historico_espiao(nome_grupo):
    """Soma +1 captura no total e no grupo (estatística mostrada no painel do Espião)."""
    historico = db.ler_config("historico_espiao", padrao={"total": 0, "grupos": {}})
    
    historico["total"] = historico.get("total", 0) + 1
    grupos = historico.get("grupos", {})
    grupos[nome_grupo] = grupos.get(nome_grupo, 0) + 1
    historico["grupos"] = grupos
    
    db.salvar_config("historico_espiao", historico)
    logger.info(f"📊 [Estatística] +1 vídeo contabilizado no SQLite para o grupo: {nome_grupo}")

async def gerar_legenda_com_ia_espelhador(caminho_video):
    """
    Pede à IA duas linhas: o nome do produto (com emoji no início) e as hashtags,
    escolhidas só da lista fixa de categorias. Devolve o texto ou None.
    """
    prompt = (
        "Assista ao vídeo e identifique qual é o produto demonstrado. "
        "Sua resposta deve conter EXATAMENTE duas linhas.\n"
        "Na primeira linha, escreva APENAS o nome do produto acompanhado de um emoji correspondente no início (Exemplo: 👟 Tênis Casual Feminino).\n"
        "Na segunda linha, inclua as hashtags correspondentes aos setores do produto. IMPORTANTE: Se utilizar mais de uma hashtag, separe-as APENAS com espaços em branco, NUNCA utilize vírgulas.\n"
        "REGRA DE CONTEXTO: Categorize o produto baseando-se estritamente na sua utilidade prática e ambiente de uso. É terminantemente proibido utilizar atalhos semânticos ou associações literais de palavras.\n"
        "REGRA ABSOLUTA: Você só pode escolher as hashtags desta lista exata, podendo combinar mais de uma se aplicável: "
        "#RoupasFemininas, #SapatosFemininos, #CelularesEDispositivos, #AcessoriosParaVeiculos, #Relogios, "
        "#AlimentosEBebidas, #CasaEDecoracao, #SapatosMasculinos, #EsportesELazer, #BolsasMasculinas, #BolsasFemininas, "
        "#RoupasPlusSize, #ModaInfantil, #Eletrodomesticos, #Motocicletas, #AnimaisDomesticos, #CamerasEDrones, #Beleza, "
        "#AcessoriosDeModa, #BrinquedosEHobbies, #Papelaria, #LivrosERevistas, #RoupasMasculinas, #Automoveis, #MaeEBebe, "
        "#ComputadoresEAcessorios, #Saude, #ViagensEBagagens, #JogosEConsoles, #Audio.\n"
        "É estritamente proibido criar textos de vendas, descrições, inventar novas hashtags, usar gatilhos mentais ou adicionar frases de encerramento."
    )
    
    titulo = await analisar_video_gemini(caminho_video, prompt)
    return titulo

PADRAO_SHOPEE = re.compile(r'(?:https?://)?(?:s\.shopee\.com\.br|shope\.ee|br\.shp\.ee|shp\.ee)/[^\s]+', re.IGNORECASE)

def extrair_link_shopee(event):
    """Primeiro link da Shopee do post: no texto visível ou escondido num hiperlink. None se não houver."""
    texto = event.raw_text or ""
    match = PADRAO_SHOPEE.search(texto)
    if match:
        link = match.group(0)
        if not link.startswith("http"):
            link = "https://" + link
        return link.rstrip(").,;!?")
        
    # Link escondido atrás de um texto (entidade com url).
    if event.entities:
        for entity in event.entities:
            if hasattr(entity, 'url') and entity.url:
                if PADRAO_SHOPEE.search(entity.url):
                    return entity.url
    return None

@client.on(events.NewMessage)
async def interceptar_mensagem(event):
    """
    Espião: captura para a fila de clonagem o vídeo com link da Shopee postado num
    canal-alvo (ou tópico-alvo). Descarta post sem vídeo, link já capturado nas
    últimas 24 h e vídeo cujo arquivo (hash) já passou por aqui.
    """
    alvos = carregar_alvos()
    
    destino_autorais = ler_excecao_ponte()
    
    chat = await event.get_chat()
    chat_id = str(chat.id)
    chat_username = f"@{chat.username.lower()}" if getattr(chat, 'username', None) else ""
    
    # O alvo pode estar salvo com ou sem o -100; compara com as duas formas.
    chat_id_completo = f"-100{chat.id}" if not chat_id.startswith("-100") else chat_id
    
    eh_ponte = False
    if destino_autorais and destino_autorais in [chat_username, chat_id, chat_id_completo]:
        eh_ponte = True

    # A ponte dos Autorais é sempre escutada, mesmo fora da lista de alvos.
    if eh_ponte and destino_autorais not in [str(a).lower() for a in alvos]:
        alvos.append(destino_autorais)

    # Post desta conta ou do bot (ID = número antes do ":" no TELEGRAM_TOKEN) é do próprio sistema.
    try:
        me = await client.get_me()
        remetente_id = getattr(event, 'sender_id', None)
        
        bot_token = os.getenv('TELEGRAM_TOKEN', '')
        bot_oficial_id = int(bot_token.split(':')[0]) if ':' in bot_token else None
        
        foi_nossa_equipe = (remetente_id == me.id) or (remetente_id == bot_oficial_id)
    except Exception:
        foi_nossa_equipe = False

    # Decisão do Rafael (DECISOES.md, Canal Viral): no @shopee_video_afiliado os posts do
    # próprio sistema também são capturados, para serem espelhados em outros canais.
    if foi_nossa_equipe and chat_username != "@shopee_video_afiliado":
        logger.info("🛡️ [Espião] Postagem do próprio sistema bloqueada (Userbot ou Bot Oficial).")
        return

    if event.out and not eh_ponte and chat_username != "@shopee_video_afiliado":
        logger.info("🛡️ [Espião] Trava de canais ativada: Ignorando evento.")
        return
    
    topico_id_evento = None
    if event.message.reply_to:
        # Post direto no tópico: o tópico vem em reply_to_msg_id. Resposta dentro do
        # tópico: o tópico vem em reply_to_top_id (reply_to_msg_id é a mensagem respondida).
        topico_id_evento = getattr(event.message.reply_to, 'reply_to_top_id', None) or getattr(event.message.reply_to, 'reply_to_msg_id', None)

    # O post precisa vir de um alvo; se o alvo tem tópico, também do tópico certo.
    eh_alvo_espiao = False
    for alvo in alvos:
        alvo_str = str(alvo).lower()
        alvo_base = alvo_str.split(':')[0]
        alvo_topico = int(alvo_str.split(':')[1]) if ':' in alvo_str and alvo_str.split(':')[1].isdigit() else None
        
        if alvo_base in [chat_id, chat_id_completo, chat_username]:
            if alvo_topico is not None:
                # Tópico Geral: vem sem tópico ou como 1.
                t_evento = topico_id_evento if topico_id_evento else 1
                t_alvo = alvo_topico if alvo_topico else 1
                if t_evento == t_alvo:
                    eh_alvo_espiao = True
                    break
            else:
                # Alvo sem tópico: escuta o grupo todo.
                eh_alvo_espiao = True
                break

    if not eh_alvo_espiao:
        return

    texto_original = event.text or ""
    link_capturado = extrair_link_shopee(event)
    
    # Sem link da Shopee é conversa: ignora.
    if link_capturado:
        # Só vídeo interessa, e isso é checado antes da duplicidade: o link só é
        # registrado como capturado quando há vídeo. Senão um post com foto e link
        # bloquearia por 24 h o post com vídeo do mesmo produto.
        if getattr(event, 'video', None) is None:
            logger.info(f"⏭️ Ignorado: O link {link_capturado} foi encontrado, mas a postagem não contém um anexo de vídeo direto.")
            return

        if verificar_e_registrar_espelho(link_capturado, contexto="espiao"):
            logger.info(f"🪞 [Espião] Duplicidade barrada! O produto {link_capturado} já foi capturado nas últimas 24 horas.")
            return  # antes de baixar o vídeo
            
        logger.info(f"🎯 ALVO LOCALIZADO! Link da Shopee extraído cirurgicamente: {link_capturado}")
        
        # Post com link de outras lojas segue normalmente; só o link da Shopee é usado.
        if "magazineluiza" in texto_original.lower() or "meli.li" in texto_original.lower() or "mercadolivre" in texto_original.lower():
            logger.info("✂️ Concorrência ignorada: A postagem continha outros domínios, mas apenas o da Shopee foi filtrado.")
        
        logger.info("📥 Iniciando download do vídeo em segundo plano...")
        caminho_salvo = await event.download_media(file="temp/temp_clone_")

        # Vídeo abaixo de 720p é re-renderizado antes de entrar na fila.
        caminho_salvo = await verificar_e_otimizar_video(caminho_salvo)
        
        hash_arquivo = calcular_hash_video(caminho_salvo)
        
        if hash_arquivo and verificar_e_registrar_hash(hash_arquivo):
            logger.warning("🚫 Clone bloqueado! O vídeo possui uma assinatura digital idêntica a um ficheiro já processado.")
            try:
                os.remove(caminho_salvo)
                logger.info("🧹 Ficheiro físico duplicado eliminado com sucesso para poupar espaço.")
            except Exception as e:
                logger.error(f"❌ Erro ao tentar remover ficheiro duplicado: {e}")
            return
            
        nome_chat = getattr(chat, 'title', chat_username if chat_username else chat_id)

        salvar_na_fila_clonagem(caminho_salvo, link_capturado, chat_origem=chat_id_completo, nome_origem=nome_chat, msg_id=event.id)
        
        registrar_historico_espiao(nome_chat)

# ---------------- Espelhador ----------------
def ler_espelhos_config():
    """Rotas do Espelhador (espelhos_config.json), editadas pelo painel_espelhos."""
    try:
        with open("espelhos_config.json", "r") as f:
            dados = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"rotas": []}
    normalizar_origens_rotas(dados)
    return dados

def ler_fila_espelhador():
    """Fila do Espelhador (fila_espelhador.json): itens agendados e o histórico do que já saiu."""
    try:
        with open("fila_espelhador.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"fila": []}

def salvar_fila_espelhador(dados):
    salvar_json_atomico("fila_espelhador.json", dados, indent=4)

# Análise antecipada da fila do Espião: em segundo plano, um vídeo por vez. Fazer na
# captura causaria rajada de chamadas quando vários canais postam juntos (e é assim
# que vem o erro 429 de cota). Com o nome já salvo, a publicação não chama a IA.
INTERVALO_ANALISE_ANTECIPADA = 45   # segundos entre uma análise e outra

PROMPT_NOME_PRODUTO = (
    "Assista ao vídeo INTEIRO e identifique qual é o produto demonstrado. "
    "Sua resposta deve conter EXATAMENTE duas linhas.\n"
    "Na primeira linha, escreva APENAS o nome do produto acompanhado de um emoji correspondente no final "
    "(Exemplo: Tênis Casual Feminino 👟).\n"
    "Na segunda linha, inclua as hashtags correspondentes aos setores do produto, separadas APENAS por espaços. "
    "REGRA DE CONTEXTO: Categorize pela utilidade prática e ambiente de uso, nunca por associação literal de palavras.\n"
    "REGRA ABSOLUTA: Você só pode escolher hashtags desta lista exata, podendo combinar mais de uma: "
    "#RoupasFemininas #SapatosFemininos #CelularesEDispositivos #AcessoriosParaVeiculos #Relogios "
    "#AlimentosEBebidas #CasaEDecoracao #SapatosMasculinos #EsportesELazer #BolsasMasculinas #BolsasFemininas "
    "#RoupasPlusSize #ModaInfantil #Eletrodomesticos #Motocicletas #AnimaisDomesticos #CamerasEDrones #Beleza "
    "#AcessoriosDeModa #BrinquedosEHobbies #Papelaria #LivrosERevistas #RoupasMasculinas #Automoveis #MaeEBebe "
    "#ComputadoresEAcessorios #Saude #ViagensEBagagens #JogosEConsoles #Audio.\n"
    "É proibido criar textos de venda, descrições, inventar hashtags ou adicionar frases de encerramento."
)

async def analisar_fila_espiao_loop():
    """
    Preenche o nome do produto dos itens da fila de clonagem que ainda não têm,
    um por vez, a cada INTERVALO_ANALISE_ANTECIPADA segundos. Usa o cache de IA
    (o Espelhador pode já ter analisado o mesmo post) e desiste de um item após 3
    falhas.
    """
    await asyncio.sleep(120)
    while True:
        try:
            dados = ler_fila_clonagem()
            fila = dados.get("fila", [])

            pendente = None
            for item in fila:
                if item.get("processado"):
                    continue
                if item.get("legenda_ia"):
                    continue
                if int(item.get("tentativas_ia_captura", 0)) >= 3:
                    continue
                caminho = item.get("caminho_video")
                if caminho and os.path.exists(caminho):
                    pendente = item
                    break

            if pendente:
                logger.info(f"🧠 [Análise Antecipada] Processando {pendente.get('id')}...")
                _chave_ia = chave_cache_ia(pendente.get("chat_origem"), pendente.get("msg_id"))
                texto_ia = consultar_cache_ia(_chave_ia)
                if texto_ia:
                    logger.info(f"♻️ [Cache IA] Espião reaproveitou a análise de {_chave_ia}.")
                else:
                    texto_ia = await analisar_video_gemini(pendente.get("caminho_video"), PROMPT_NOME_PRODUTO)
                    gravar_cache_ia(_chave_ia, texto_ia)

                dados = ler_fila_clonagem()
                for item in dados.get("fila", []):
                    if item.get("id") != pendente.get("id"):
                        continue
                    if texto_ia:
                        linhas = texto_ia.split("\n")
                        nome = linhas[0].strip()
                        tags = "\n".join(linhas[1:]).strip() if len(linhas) > 1 else ""
                        item["legenda_ia"] = texto_ia
                        # "📦 Item: <nome>" é o formato que o painel de filas procura.
                        item["legenda"] = f"📦 Item: {nome}" + (f"\n\n{tags}" if tags else "")
                        logger.info(f"✅ [Análise Antecipada] {pendente.get('id')} → {nome}")
                    else:
                        item["tentativas_ia_captura"] = int(item.get("tentativas_ia_captura", 0)) + 1
                        logger.warning(f"⚠️ [Análise Antecipada] IA falhou ({item['tentativas_ia_captura']}/3) em {pendente.get('id')}.")
                    break
                salvar_fila_clonagem(dados)

        except Exception as e:
            logger.error(f"❌ [Análise Antecipada] Falha no loop: {e}")

        await asyncio.sleep(INTERVALO_ANALISE_ANTECIPADA)

# Quantos dias o já publicado fica na fila como histórico (o relatório do painel
# mostra o que saiu hoje). Sem prazo, a fila crescia ~60 itens por dia e era
# relida e regravada inteira a cada minuto. Decisão do Rafael: DECISOES.md, Espelhador de canais.
DIAS_HISTORICO_ESPELHADOR = 3


def podar_historico(fila, hoje):
    """A fila sem os itens publicados antes de hoje - DIAS_HISTORICO_ESPELHADOR."""
    corte = (datetime.strptime(hoje, "%Y-%m-%d") - timedelta(days=DIAS_HISTORICO_ESPELHADOR)).strftime("%Y-%m-%d")
    return [i for i in fila
            if not (i.get("processado") and i.get("data_postagem") and str(i["data_postagem"]) < corte)]


async def processar_fila_espelhador_loop():
    """
    Laço do Espelhador, a cada 60 s:
    1. agenda (motor_filas) os itens sem horário cuja data-alvo (captura + D+X da
       rota) chegou, ou todos se a rota pediu "esvaziar agora";
    2. aplica o teto diário de cada rota (excedente sai da fila sem ser postado);
    3. publica os itens vencidos, 15 s entre um e outro.
    Itens publicados ficam na fila como histórico (processado=True) por
    DIAS_HISTORICO_ESPELHADOR dias.
    """
    while True:
        try:
            fila_dados = ler_fila_espelhador()
            fila = fila_dados.get("fila", [])
            if not fila:
                await asyncio.sleep(60)
                continue

            tamanho_lido = len(fila)
            fila = podar_historico(fila, datetime.now(fuso_horario).strftime("%Y-%m-%d"))
            podou_historico = len(fila) != tamanho_lido

            config = ler_espelhos_config()
            rotas = {r.get("nome"): r for r in config.get("rotas", [])}
            
            itens_restantes = []
            agora = datetime.now(fuso_horario)
            hoje_str = agora.strftime("%Y-%m-%d")
            houve_alteracao_rota = False
            houve_agendamento = False
            houve_disparo = False
            
            # 1. Itens que já podem ser agendados, por rota.
            itens_por_rota_desagendados = {}
            for item in fila:
                nome_rota = item.get("nome_rota")
                rota_config = rotas.get(nome_rota)
                
                if not rota_config: continue
                
                # "Esvaziar agora" no painel: desfaz o horário para o motor reagendar tudo já.
                esvaziar_agora = rota_config.get("esvaziar_agora", False)
                if esvaziar_agora and not item.get("processado"):
                    item["horario_disparo"] = ""
                    
                if item.get("horario_disparo") or item.get("processado"):
                    continue  # já agendado ou já publicado
                
                data_captura_obj = datetime.strptime(item["data_captura"], "%Y-%m-%d %H:%M:%S")
                intervalo_dias = int(rota_config.get("intervalo_dias", 1))
                data_alvo_str = (data_captura_obj + timedelta(days=intervalo_dias)).strftime("%Y-%m-%d")

                if intervalo_dias == 0 or data_alvo_str <= hoje_str or esvaziar_agora:
                    itens_por_rota_desagendados.setdefault(nome_rota, []).append(item)

            for nome_rota, itens in itens_por_rota_desagendados.items():
                rota_config = rotas.get(nome_rota)
                if not rota_config: continue
                
                config_fila = {
                    "inicio": int(rota_config.get("inicio", 10)),
                    "fim": int(rota_config.get("fim", 22)),
                    "modo": rota_config.get("modo", "ordem"),
                    "intervalo_dias": int(rota_config.get("intervalo_dias", 1)),
                    # Espaçamento padrão: 20 min ± 8 (de 12 a 28 min entre vídeos).
                    "espacamento_base_min": int(rota_config.get("espacamento_min", 20)),
                    "espacamento_variacao_min": int(rota_config.get("espacamento_var", 8)),
                    # O que não couber passa para o dia seguinte; se ficar a mais de D+X+7 dias
                    # da captura, é descartado.
                    "limite_dias_descarte": max(7, int(rota_config.get("intervalo_dias", 1)) + 7)
                }
                
                forcar_rota = rota_config.get("esvaziar_agora", False)
                
                logger.info(f"📅 [Espelhador] Motor Central acionado para {len(itens)} vídeos na rota '{nome_rota}' (Forçar: {forcar_rota})...")
                calcular_horarios_distribuicao(itens, config_fila, forcar=forcar_rota)
                houve_agendamento = True

            # 2. Teto diário por rota. A captura pega tudo; aqui se corta para o número de
            # posts que a rota aceita por dia. O excedente é descartado (não passa para o
            # dia seguinte), e a conta inclui o já agendado e o já publicado; senão o teto
            # seria furado a cada volta.
            for nome_rota_teto, rota_cfg_teto in rotas.items():
                piso_rota, topo_rota = ler_faixa_limite(rota_cfg_teto)
                if not piso_rota:
                    continue
                itens_da_rota = [i for i in fila if i.get("nome_rota") == nome_rota_teto]
                # Semente com o nome da rota: cada rota sorteia o seu teto do dia, e o mesmo
                # em todos os ciclos.
                descartados_teto = aplicar_limite_diario_fila(
                    itens_da_rota, piso_rota, topo_rota, semente=f"espelho:{nome_rota_teto}"
                )
                if descartados_teto:
                    logger.info(f"✂️ [Espelhador] Rota '{nome_rota_teto}': {len(descartados_teto)} "
                                f"vídeo(s) acima da faixa de {piso_rota}-{topo_rota}/dia serão descartados.")

            # 3. Publica os itens cujo horário chegou.
            for item in fila:
                nome_rota = item.get("nome_rota")
                rota_config = rotas.get(nome_rota)
                
                
                if not rota_config:
                    itens_restantes.append(item)
                    continue

                # Excedente do teto diário: sai da fila sem ser postado.
                if item.get("descartar_por_limite") and not item.get("processado"):
                    continue
                    
                horario_disparo_str = item.get("horario_disparo")
                deve_disparar = False
                
                if not item.get("processado") and horario_disparo_str:
                    try:
                        horario_disparo_obj = datetime.strptime(horario_disparo_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=fuso_horario)
                        if agora >= horario_disparo_obj:
                            deve_disparar = True
                    except Exception: pass
                
                if deve_disparar:
                    msg_enviada = None
                    erro_disparo = None
                    try:
                        chat_origem_bruto = item["chat_origem"]
                        chat_origem = int(chat_origem_bruto) if str(chat_origem_bruto).lstrip('-').isdigit() else chat_origem_bruto
                        msg_id = item["msg_id"]
                        destino = item["destino"]
                        texto = item["texto_processado"]
                        
                        mensagem_original = await client.get_messages(chat_origem, ids=msg_id)
                        if mensagem_original:
                            # O post de origem pode ter sido editado e perdido o vídeo.
                            if getattr(mensagem_original, 'video', None) is None:
                                logger.warning(f"🚫 [Segurança] Espelhador abortou o envio! A mensagem {msg_id} perdeu o formato de vídeo.")
                            else:
                                # Um download serve para a análise da IA e o re-encode. Só chega
                                # aqui o vídeo que passou pelo teto do dia, então nada é desperdício.
                                caminho_disparo = None
                                houve_upscale = False
                                try:
                                    caminho_disparo = await mensagem_original.download_media(file="temp/temp_disparo_espelho_")
                                except Exception as e:
                                    logger.error(f"❌ [Espelhador] Download falhou no disparo: {e}")

                                # O re-encode substitui o arquivo no mesmo caminho; se aconteceu,
                                # quem avisa é o dict, não o retorno.
                                if caminho_disparo:
                                    relatorio_upscale = {}
                                    caminho_disparo = await verificar_e_otimizar_video(caminho_disparo, relatorio_upscale)
                                    houve_upscale = bool(relatorio_upscale.get("upscaled"))

                                # IA só agora, no vídeo que vai mesmo ao ar.
                                if item.get("legenda_ia_pendente"):
                                    texto = await montar_legenda_no_disparo(
                                        caminho_disparo, chat_origem, msg_id, item
                                    )

                                try:
                                    entidade_destino = await client.get_entity(destino)
                                except ValueError:
                                    id_teste = int(destino) if str(destino).lstrip('-').isdigit() else destino
                                    entidade_destino = await client.get_entity(id_teste)

                                try:
                                    if houve_upscale and caminho_disparo and os.path.exists(caminho_disparo):
                                        # Sobe o arquivo re-encodado; supports_streaming faz o post sair
                                        # como vídeo reproduzível, não como documento.
                                        logger.info("⬆️ [Espelhador] Enviando o vídeo re-encodado para 720p.")
                                        msg_enviada = await client.send_message(entidade_destino, texto, file=caminho_disparo, parse_mode="html", supports_streaming=True)

                                        # O re-encode gera um arquivo com hash diferente do registrado na
                                        # captura. Registrar o hash publicado no destino deixa o anti-loop
                                        # reconhecer o vídeo se ele voltar por um canal vigiado. Só depois
                                        # do envio, para registrar apenas o que foi ao ar.
                                        hash_publicado = calcular_hash_video(caminho_disparo)
                                        if hash_publicado:
                                            verificar_e_registrar_hash(hash_publicado, contexto=str(destino))
                                            logger.info(f"🧬 [Espelhador] Hash do vídeo publicado registado no destino {destino}.")
                                    else:
                                        # Sem re-encode, reaproveita a mídia original por referência (nada
                                        # a subir); o hash dela já foi registrado neste destino na captura.
                                        msg_enviada = await client.send_message(entidade_destino, texto, file=mensagem_original.media, parse_mode="html")
                                finally:
                                    # O temporário é apagado mesmo se o envio falhar no meio; senão a
                                    # pasta temp/ acumula até a faxina das 03h.
                                    if caminho_disparo and os.path.exists(caminho_disparo):
                                        try:
                                            os.remove(caminho_disparo)
                                        except Exception as e:
                                            logger.error(f"❌ [Espelhador] Erro ao remover temporário do disparo: {e}")
                                
                                item["msg_postada_id"] = msg_enviada.id  # o painel monta o link do post publicado
                                logger.info(f"✅ [Espelhador] Disparo concluído na rota '{nome_rota}' para {destino}.")
                                
                                await asyncio.sleep(15)  # intervalo mínimo entre envios (anti-ban)
                        else:
                            logger.warning(f"⚠️ [Espelhador] Mensagem original {msg_id} apagada antes do disparo na rota '{nome_rota}'.")
                    except Exception as e:
                        erro_disparo = e
                        logger.error(f"❌ [Espelhador] Falha no disparo da rota '{nome_rota}': {e}")

                    # Erro antes de o vídeo sair (rede, flood, destino inacessível): o item volta
                    # para a fila e é tentado nos próximos ciclos, até 3 vezes; num flood, só
                    # depois da espera pedida pelo Telegram. Vídeo apagado ou sem vídeo na
                    # origem não é erro e segue direto para o histórico.
                    if erro_disparo is not None and msg_enviada is None:
                        tentativas = int(item.get("tentativas_disparo", 0)) + 1
                        if tentativas < 3:
                            item["tentativas_disparo"] = tentativas
                            if isinstance(erro_disparo, FloodWaitError):
                                espera = int(getattr(erro_disparo, "seconds", 60) or 60) + 30
                                item["horario_disparo"] = (agora + timedelta(seconds=espera)).strftime("%Y-%m-%d %H:%M:%S")
                            logger.warning(f"🔁 [Espelhador] Tentativa {tentativas}/3 falhou na rota '{nome_rota}'; vai de novo num próximo ciclo.")
                            itens_restantes.append(item)
                            houve_disparo = True
                            continue
                        registrar_erro_json(f"Espelhador desistiu após 3 tentativas na rota '{nome_rota}': {erro_disparo}", origem="motor_userbot.py")

                    # Publicado (ou perdido: origem apagada, sem vídeo, ou 3 falhas): fica no
                    # histórico como processado e não volta a ser tentado.
                    item["processado"] = True
                    item["data_postagem"] = agora.strftime("%Y-%m-%d")
                    item["horario_postagem"] = agora.strftime("%H:%M")
                    itens_restantes.append(item)
                    houve_disparo = True
                else:
                    itens_restantes.append(item)
                    
            # "Esvaziar agora" vale uma vez: desliga o pedido nas rotas.
            for r in config.get("rotas", []):
                if r.get("esvaziar_agora"):
                    r["esvaziar_agora"] = False
                    houve_alteracao_rota = True
            
            if houve_alteracao_rota:
                salvar_json_atomico("espelhos_config.json", config, indent=4, ensure_ascii=False)
                    
            # Grava a fila só se algo mudou (agendamento, publicação ou itens removidos).
            if podou_historico or len(fila) != len(itens_restantes) or houve_agendamento or houve_disparo:
                fila_dados["fila"] = itens_restantes
                salvar_fila_espelhador(fila_dados)
            
        except Exception as e:
            logger.error(f"❌ Erro crítico no motor de distribuição do espelhador: {e}")
            registrar_erro_json(f"processar_fila_espelhador_loop: {e}", origem="espelhador.py")
        
        await asyncio.sleep(60)

@client.on(events.NewMessage)
async def motor_espelhador_userbot(event):
    """
    Espelhador, na captura: o vídeo com link da Shopee postado numa origem de rota
    (ou tópico de origem) entra na fila de cada rota, com o link já convertido
    para afiliado. Por rota, descarta: vídeo que nasceu no próprio destino
    (encaminhado de lá), link já postado nesse destino nas últimas 24 h e vídeo
    (hash) já postado nesse destino.
    """
    chat = await event.get_chat()
    chat_id_str = str(chat.id)
    chat_username = f"@{chat.username.lower()}" if getattr(chat, 'username', None) else ""
    chat_id_completo = f"-100{chat.id}" if not chat_id_str.startswith("-100") else chat_id_str
    nome_chat = getattr(chat, 'title', chat_username if chat_username else chat_id_str)

    destino_autorais = ler_excecao_ponte()
    eh_ponte = False
    if destino_autorais and destino_autorais in [chat_username, chat_id_str, chat_id_completo]:
        eh_ponte = True

    # Post desta conta ou do bot (ID = número antes do ":" no TELEGRAM_TOKEN) é do próprio sistema.
    try:
        me = await client.get_me()
        remetente_id = getattr(event, 'sender_id', None)
        
        bot_token = os.getenv('TELEGRAM_TOKEN', '')
        bot_oficial_id = int(bot_token.split(':')[0]) if ':' in bot_token else None
        
        foi_nossa_equipe = (remetente_id == me.id) or (remetente_id == bot_oficial_id)
    except Exception:
        foi_nossa_equipe = False

    # Decisão do Rafael (DECISOES.md, Canal Viral): no @shopee_video_afiliado os posts do
    # próprio sistema também são capturados, para serem espelhados em outros canais.
    if foi_nossa_equipe and chat_username != "@shopee_video_afiliado":
        logger.info("🛡️ [Espelhador] Postagem do próprio sistema bloqueada (Userbot ou Bot Oficial).")
        return

    if event.out and not eh_ponte and chat_username != "@shopee_video_afiliado":
        logger.info("🛡️ [Espelhador] Trava de canais ativada: Postagem própria ignorada.")
        return

    topico_id_evento = None
    if event.message.reply_to:
        # Post direto no tópico: o tópico vem em reply_to_msg_id. Resposta dentro do
        # tópico: o tópico vem em reply_to_top_id (reply_to_msg_id é a mensagem respondida).
        topico_id_evento = getattr(event.message.reply_to, 'reply_to_top_id', None) or getattr(event.message.reply_to, 'reply_to_msg_id', None)

    dados = ler_espelhos_config()
    rotas_ativas = []
    
    for r in dados.get("rotas", []):
        origens_rota = [str(o).lower() for o in r.get("origens", [])]
        if "origem" in r:
            origens_rota.append(str(r["origem"]).lower())
            
        # A rota pega o post se ele vem de uma das origens (e do tópico, se a origem tiver um).
        para_esta_rota = False
        for origem in origens_rota:
            origem_base = origem.split(':')[0]
            origem_topico = int(origem.split(':')[1]) if ':' in origem and origem.split(':')[1].isdigit() else None
            
            if origem_base in [chat_id_str, chat_id_completo, chat_username]:
                if origem_topico is not None:
                    t_evento = topico_id_evento if topico_id_evento else 1
                    t_origem = origem_topico if origem_topico else 1
                    if t_evento == t_origem:
                        para_esta_rota = True
                        break
                else:
                    para_esta_rota = True
                    break
                    
        if para_esta_rota:
            rotas_ativas.append(r)
    
    if not rotas_ativas:
        return

    # Só vídeo; foto é ignorada.
    if getattr(event, 'video', None) is None:
        logger.info("⏭️ [Espelhador] Postagem descartada: Contém o link, mas a mídia não é um vídeo.")
        return

    link_capturado = extrair_link_shopee(event)
    
    if not link_capturado:
        logger.info("⏭️ Postagem ignorada: Não contém link da Shopee (nem embutido).")
        return
    
    logger.info(f"🔄 [Espelhador] Interceptação acionada! Mídia e link detetados na origem {chat_id_str}.")
    logger.info("🔗 [Espelhador] A converter o link da Shopee encontrado via API Central...")
    link_final_convertido = await converter_link_shopee(link_capturado, "geral")
    logger.info("✅ [Espelhador] Sucesso: Link convertido utilizando a função nativa correta.")

    logger.info("📥 [Espelhador] Descarregando vídeo temporário para verificação de duplicidade...")
    caminho_video_temp = await event.download_media(file="temp/temp_analise_espelho_")

    # O download aqui serve só para o hash do vídeo como ele veio, que é o que
    # reconhece o mesmo vídeo aparecendo de novo. O re-encode fica para o disparo: feito
    # aqui, gastaria CPU nos ~100 vídeos do dia, a maioria cortada pelo teto diário.
    
    hash_arquivo = None
    if caminho_video_temp:
        hash_arquivo = calcular_hash_video(caminho_video_temp)
        
        # Registra o hash também no contexto da ORIGEM: se uma rota levar este vídeo de
        # volta para cá, ele é reconhecido e não é espelhado de novo.
        if hash_arquivo:
            verificar_e_registrar_hash(hash_arquivo, contexto=chat_id_str)
            if chat_id_completo != chat_id_str:
                verificar_e_registrar_hash(hash_arquivo, contexto=chat_id_completo)
                
        # Aqui só se aproveita uma análise que já esteja no cache (o Espião lê os mesmos
        # canais). Chamar a IA na captura gastaria cota em vídeos que o teto diário vai
        # descartar; a chamada nova fica para o disparo.
        _chave_ia = chave_cache_ia(getattr(event, 'chat_id', None), getattr(event, 'id', None))
        titulo_ia = consultar_cache_ia(_chave_ia)
        if titulo_ia:
            logger.info(f"♻️ [Cache IA] Espelhador reaproveitou a análise de {_chave_ia}.")
        
        try:
            os.remove(caminho_video_temp)
            logger.info("🧹 [Espelhador] Vídeo temporário removido do servidor após análise.")
        except Exception as e:
            logger.error(f"❌ [Espelhador] Erro ao remover vídeo temporário: {e}")
    else:
        titulo_ia = None

    if titulo_ia:
        linhas_ia = titulo_ia.split('\n')
        nome_produto = linhas_ia[0].strip()
        hashtags = '\n'.join(linhas_ia[1:]).strip() if len(linhas_ia) > 1 else ""
        
        texto_processado = f"<b>{nome_produto}</b>\n\n🔗 <b>Link do Produto:</b>\n{link_final_convertido}"
        if hashtags:
            texto_processado += f"\n\n<i>{hashtags}</i>"
            
        logger.info("✅ [Espelhador] Legenda inteligente construída com sucesso (Título -> Link -> Hashtags).")
    else:
        texto_processado = f"🔗 <b>Link do Produto:</b>\n{link_final_convertido}"
        logger.info("🕓 [Espelhador] Análise da IA adiada para o disparo. Legenda base gravada como fallback.")

    # Sem título vindo do cache, a legenda definitiva é montada na hora de postar.
    legenda_ia_pendente = not bool(titulo_ia)

    forward_origem_id = None
    if getattr(event, 'fwd_from', None) and getattr(event.fwd_from, 'from_id', None):
        try:
            fwd_id = utils.get_peer_id(event.fwd_from.from_id)
            forward_origem_id = f"-100{fwd_id}" if not str(fwd_id).startswith("-100") else str(fwd_id)
        except Exception:
            pass

    for rota in rotas_ativas:
        destino = rota["destino"]
        nome_rota = rota.get("nome", "Desconhecida")
        
        if forward_origem_id and (destino == forward_origem_id or destino.replace("-100", "") == forward_origem_id.replace("-100", "")):
            logger.warning(f"🚫 [Anti-Loop Ativado] O vídeo nasceu no destino ({destino}). Ignorando a clonagem nesta rota.")
            continue
            
        if link_capturado and verificar_e_registrar_espelho(link_capturado, contexto=str(destino)):
            logger.info(f"🪞 [Espelhador] Duplicidade barrada na rota '{nome_rota}'! O link já foi postado neste destino nas últimas 24h.")
            continue
            
        if hash_arquivo and verificar_e_registrar_hash(hash_arquivo, contexto=str(destino)):
            logger.warning(f"🚫 [Espelhador] Loop evitado na rota '{nome_rota}'! O ficheiro de vídeo exato já foi postado neste destino.")
            continue
            
        fila_dados = ler_fila_espelhador()
        item = {
            "id": f"espelho_{int(datetime.now().timestamp())}_{chat_id_str}",
            "chat_origem": chat_id_completo,
            "nome_origem": nome_chat,
            "msg_id": event.id,
            "destino": destino,
            "nome_rota": nome_rota,
            "texto_processado": texto_processado,
            # O link convertido fica guardado à parte para o disparo remontar a
            # legenda sem ter de converter de novo na API da Shopee.
            "link_convertido": link_final_convertido,
            "legenda_ia_pendente": legenda_ia_pendente,
            "data_captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        fila_dados["fila"].append(item)
        salvar_fila_espelhador(fila_dados)
        logger.info(f"📦 [Espelhador] Vídeo enfileirado dinamicamente na rota '{nome_rota}'.")

async def montar_legenda_no_disparo(caminho_video, chat_origem, msg_id, item):
    """
    Monta a legenda definitiva no momento do disparo, não na captura.

    Só chega aqui o vídeo que sobreviveu ao teto diário e vai mesmo ao ar, então
    cada chamada ao Gemini vira um post — em vez das ~93 por dia que a captura
    gastava em material destinado ao descarte.

    Reaproveita o download que o disparo já faz: a mídia vem do objeto de
    mensagem que acabou de ser buscado, sem ida extra à API. O cache partilhado
    com o Espião continua a valer, consultado antes de qualquer chamada nova.

    Qualquer falha devolve a legenda base (só o link), que é exatamente o
    fallback que já existia quando a IA falhava na captura.
    """
    link = item.get("link_convertido") or ""
    texto_base = item.get("texto_processado") or (f"🔗 <b>Link do Produto:</b>\n{link}" if link else "")

    try:
        chave = chave_cache_ia(chat_origem, msg_id)
        titulo_ia = consultar_cache_ia(chave)

        if titulo_ia:
            logger.info(f"♻️ [Cache IA] Disparo reaproveitou a análise de {chave}.")
        elif not caminho_video:
            logger.warning("⚠️ [Espelhador] Sem ficheiro para analisar. A postar com a legenda base.")
            return texto_base
        else:
            titulo_ia = await gerar_legenda_com_ia_espelhador(caminho_video)
            gravar_cache_ia(chave, titulo_ia)

        if not titulo_ia:
            logger.warning("⚠️ [Espelhador] IA não devolveu título. A postar com a legenda base.")
            return texto_base

        linhas_ia = titulo_ia.split('\n')
        nome_produto = linhas_ia[0].strip()
        hashtags = '\n'.join(linhas_ia[1:]).strip() if len(linhas_ia) > 1 else ""

        texto = f"<b>{nome_produto}</b>\n\n🔗 <b>Link do Produto:</b>\n{link}"
        if hashtags:
            texto += f"\n\n<i>{hashtags}</i>"

        # Grava no item para o painel e o histórico mostrarem a legenda real.
        item["texto_processado"] = texto
        item["legenda_ia_pendente"] = False
        logger.info("✅ [Espelhador] Legenda inteligente montada no disparo.")
        return texto

    except Exception as e:
        logger.error(f"❌ [Espelhador] Falha ao montar a legenda no disparo: {e}")
        return texto_base

async def validar_e_obter_entidade(client, alvo):
    """
    Resolve um alvo digitado no painel (link t.me, @username ou ID, com ":tópico"
    opcional) testando as variações no Telegram. Devolve (entidade, id_normalizado)
    ou levanta exceção se nenhuma variação funcionar.
    """
    alvo_str = str(alvo).strip()
    
    logger.info(f"🧹 [Auditor] Higienizando alvo bruto: {alvo_str}")

    # O tópico sai do texto antes da busca e volta no ID normalizado.
    topico_id = None
    if ":" in alvo_str:
        partes = alvo_str.split(":", 1)
        alvo_str = partes[0]
        if partes[1].isdigit():
            topico_id = partes[1]

    # Link privado (t.me/c/12345678/10): vira -100<número>.
    match_privado = re.search(r't\.me/c/(\d+)', alvo_str)
    if match_privado:
        numero_extraido = match_privado.group(1)
        alvo_str = f"-100{numero_extraido}"
        logger.info(f"🔗 [Auditor] Link privado detetado. Convertido para ID base: {alvo_str}")

    # Username ou link público (t.me/username).
    elif "t.me/" in alvo_str or alvo_str.startswith("@") or not alvo_str.lstrip('-').isdigit():
        username_puro = re.sub(r'https?://(www\.)?t\.me/', '', alvo_str)
        username_puro = username_puro.split('/')[0].split('?')[0]
        username_puro = username_puro.lstrip('@')
        
        variacoes_publicas = [f"@{username_puro}", username_puro]
        
        for var in variacoes_publicas:
            try:
                logger.info(f"🔍 [Auditor] Testando variação de username: {var}")
                ent = await client.get_entity(var)
                logger.info(f"✅ [Auditor] Variação {var} aceite pela API do Telegram!")
                id_final = f"{var}:{topico_id}" if topico_id else var
                return ent, id_final
            except Exception:
                continue
        raise Exception("Nenhuma variação de username funcionou.")

    # ID numérico: testa com e sem -100.
    so_numeros = re.sub(r'^-?(100)?', '', alvo_str)
    
    variacoes_numericas = [
        alvo_str, 
        f"-100{so_numeros}", 
        f"-{so_numeros}", 
        so_numeros
    ]
    
    variacoes_unicas = []
    for v in variacoes_numericas:
        if v not in variacoes_unicas:
            variacoes_unicas.append(v)
            
    for var in variacoes_unicas:
        try:
            logger.info(f"🔍 [Auditor] Testando variação numérica de ID: {var}")
            ent = await client.get_entity(int(var))
            logger.info(f"✅ [Auditor] Variação {var} aceite pela API do Telegram!")
            id_final = f"{var}:{topico_id}" if topico_id else str(var)
            return ent, id_final
        except Exception:
            continue
            
    raise Exception("Nenhuma variação de ID numérico funcionou.")

async def monitorar_status_alvos():
    """
    A cada minuto, se a lista de alvos ou o destino do Espião mudou no banco,
    confere no Telegram cada um: grava status (ok/erro) e nome para o painel e
    corrige o ID salvo para a forma que funcionou.
    """
    ultimo_alvos = None
    ultimo_destino = None
    ultima_modificacao = 0

    logger.info("🚀 Iniciando monitoramento ultraleve (1 min) para os alvos do Espião...")
    
    while True:
        try:
            # Data de modificação do banco: se não mudou, não há o que conferir.
            try:
                modificacao_atual = os.path.getmtime("banco_dados.db")
            except OSError:
                modificacao_atual = 0

            if modificacao_atual != ultima_modificacao:
                dados_iniciais = db.ler_config("alvos_espiao", {"alvos": [], "canal_destino": None, "status_alvos": {}})
                
                alvos_atuais = [str(a) for a in dados_iniciais.get("alvos", [])]
                destino_atual = str(dados_iniciais.get("canal_destino")) if dados_iniciais.get("canal_destino") else None

                # O banco muda por vários motivos; só confere se mudaram os alvos ou o destino.
                if alvos_atuais != ultimo_alvos or destino_atual != ultimo_destino:
                    logger.info("🔍 [Auditor] Mudança detectada nos alvos do Espião. Iniciando validação...")
                    
                    novos_status_coletados = {}
                    mapa_correcoes = {}
                    
                    for alvo in alvos_atuais:
                        try:
                            entidade, alvo_correto = await validar_e_obter_entidade(client, alvo)
                            nome = getattr(entidade, 'title', getattr(entidade, 'username', str(alvo_correto)))
                            novos_status_coletados[alvo_correto] = {"status": "ok", "nome": nome}
                            
                            if str(alvo) != alvo_correto:
                                mapa_correcoes[str(alvo)] = alvo_correto
                        except Exception:
                            novos_status_coletados[str(alvo)] = {"status": "erro", "erro": "Acesso negado/Link inválido"}
                            
                        await asyncio.sleep(2)  # sem rajada de consultas ao Telegram
                        
                    status_destino_coletado = None
                    if destino_atual:
                        try:
                            entidade_dest, dest_correto = await validar_e_obter_entidade(client, destino_atual)
                            nome_dest = getattr(entidade_dest, 'title', getattr(entidade_dest, 'username', str(dest_correto)))
                            status_destino_coletado = {"status": "ok", "nome": nome_dest}
                            if str(destino_atual) != dest_correto:
                                mapa_correcoes["_destino"] = dest_correto
                        except Exception:
                            status_destino_coletado = {"status": "erro", "nome": str(destino_atual)}
                        await asyncio.sleep(2)
                        
                    dados_frescos = db.ler_config("alvos_espiao", {"alvos": [], "canal_destino": None, "status_alvos": {}})
                    alvos_reais_agora = [str(a) for a in dados_frescos.get("alvos", [])]
                    status_alvos_antigos = dados_frescos.get("status_alvos", {})
                    
                    status_alvos_final = {}
                    nova_lista_alvos = []
                    houve_alteracao = False
                    
                    for alvo in alvos_reais_agora:
                        alvo_final = mapa_correcoes.get(alvo, alvo)
                        nova_lista_alvos.append(alvo_final)
                        if alvo != alvo_final:
                            houve_alteracao = True
                    
                    for alvo_final in nova_lista_alvos:
                        if alvo_final in novos_status_coletados:
                            status_alvos_final[alvo_final] = novos_status_coletados[alvo_final]
                            if status_alvos_antigos.get(alvo_final) != novos_status_coletados[alvo_final]:
                                houve_alteracao = True
                        elif alvo_final in status_alvos_antigos:
                            status_alvos_final[alvo_final] = status_alvos_antigos[alvo_final]
                            
                    for alvo_antigo in status_alvos_antigos.keys():
                        if alvo_antigo not in nova_lista_alvos:
                            houve_alteracao = True
                            
                    destino_fresco = dados_frescos.get("canal_destino")
                    if destino_fresco:
                        if "_destino" in mapa_correcoes and str(destino_fresco) == str(destino_atual):
                            dados_frescos["canal_destino"] = mapa_correcoes["_destino"]
                            houve_alteracao = True
                            
                    if status_destino_coletado and dados_frescos.get("status_destino") != status_destino_coletado:
                        dados_frescos["status_destino"] = status_destino_coletado
                        houve_alteracao = True
                            
                    if houve_alteracao:
                        dados_frescos["alvos"] = nova_lista_alvos
                        dados_frescos["status_alvos"] = status_alvos_final
                        db.salvar_config("alvos_espiao", dados_frescos)
                        
                    ultimo_alvos = nova_lista_alvos
                    ultimo_destino = str(dados_frescos.get("canal_destino")) if dados_frescos.get("canal_destino") else None
                    
                    try:
                        ultima_modificacao = os.path.getmtime("banco_dados.db")
                    except OSError:
                        ultima_modificacao = modificacao_atual
                        
                    logger.info("✅ Auditoria do Espião concluída. Nomes atualizados!")
                else:
                    ultima_modificacao = modificacao_atual

        except Exception as e:
            logger.error(f"⚠️ Erro no loop de monitoramento do Espião: {e}")

        await asyncio.sleep(60)

async def monitorar_status_espelhos():
    """
    O mesmo que monitorar_status_alvos, para as origens e destinos das rotas do
    Espelhador (espelhos_config.json): status e nome por canal e ID corrigido.
    """
    ultima_assinatura_rotas = None
    ultima_modificacao = 0

    logger.info("🚀 Iniciando monitoramento ultraleve (1 min) para as rotas do Espelhador...")
    while True:
        try:
            # Data de modificação do arquivo: se não mudou, não há o que conferir.
            try:
                modificacao_atual = os.path.getmtime("espelhos_config.json")
            except OSError:
                modificacao_atual = 0

            if modificacao_atual != ultima_modificacao:
                try:
                    with open("espelhos_config.json", "r", encoding="utf-8") as f:
                        dados_espelho = json.load(f)
                except FileNotFoundError:
                    dados_espelho = {"rotas": []}
                # Origem no formato antigo {"id", "nome"} vira texto; se mudou, a auditoria grava.
                origens_normalizadas = normalizar_origens_rotas(dados_espelho)
                
                rotas = dados_espelho.get("rotas", [])
                
                assinatura_atual = str([{ "origens": r.get("origens", [r.get("origem")]), "destino": r.get("destino") } for r in rotas])
                
                # Só confere se mudaram as origens ou destinos das rotas.
                if assinatura_atual != ultima_assinatura_rotas:
                    logger.info("🔍 [Auditor] Mudança detectada nas rotas do Espelhador. Iniciando validação...")
                    alterado = origens_normalizadas
                    
                    for rota in rotas:
                        canais_para_verificar = []
                        
                        if "origens" in rota:
                            for i, c in enumerate(rota["origens"]):
                                canais_para_verificar.append(("origem_lista", c, i))
                        elif "origem" in rota:
                            canais_para_verificar.append(("origem_legado", rota["origem"], None))
                            
                        canais_para_verificar.append(("destino", rota.get("destino"), None))
                        
                        for tipo_ponta, canal, idx in canais_para_verificar:
                            if not canal: continue
                                
                            try:
                                entidade, canal_correto = await validar_e_obter_entidade(client, canal)
                                
                                if str(canal) != canal_correto:
                                    if tipo_ponta == "origem_lista": rota["origens"][idx] = canal_correto
                                    elif tipo_ponta == "origem_legado": rota["origem"] = canal_correto
                                    elif tipo_ponta == "destino": rota["destino"] = canal_correto
                                    alterado = True
                                    canal = canal_correto 
                                
                                nome_canal = getattr(entidade, 'title', getattr(entidade, 'username', str(canal)))
                                if "status_canais" not in rota: rota["status_canais"] = {}
                                
                                info_atual = rota["status_canais"].get(str(canal), {})
                                if not isinstance(info_atual, dict): info_atual = {}
                                
                                if info_atual.get("status") != "ok" or info_atual.get("nome") != nome_canal:
                                    rota["status_canais"][str(canal)] = {"status": "ok", "nome": nome_canal}
                                    alterado = True

                                if rota.get("status_verificacao") == "erro":
                                    rota["status_verificacao"] = "ok"
                                    alterado = True
                                    
                            except Exception:
                                if "status_canais" not in rota: rota["status_canais"] = {}
                                info_atual = rota["status_canais"].get(str(canal), {})
                                if not isinstance(info_atual, dict): info_atual = {}
                                
                                if info_atual.get("status") != "erro":
                                    rota["status_canais"][str(canal)] = {"status": "erro", "nome": str(canal)}
                                    alterado = True
                                    
                                if rota.get("status_verificacao") != "erro":
                                    rota["status_verificacao"] = "erro"
                                    alterado = True
                                    
                    if alterado:
                        salvar_json_atomico("espelhos_config.json", dados_espelho, indent=4, ensure_ascii=False)
                        logger.info("✅ Arquivo do Espelhador atualizado e sincronizado após auditoria.")
                        
                    ultima_assinatura_rotas = str([{ "origens": r.get("origens", [r.get("origem")]), "destino": r.get("destino") } for r in rotas])
                    
                    try:
                        ultima_modificacao = os.path.getmtime("espelhos_config.json")
                    except OSError:
                        ultima_modificacao = modificacao_atual
                        
                    logger.info("✅ Auditoria do Espelhador concluída. Nomes atualizados!")
                else:
                    ultima_modificacao = modificacao_atual

        except Exception as e:
            logger.error(f"⚠️ Erro na auditoria do espelhador: {e}")
            
        await asyncio.sleep(60)

async def monitorar_topicos_submissao():
    """
    A cada 10 min, grava no cache de nomes os títulos dos tópicos do grupo de
    submissão (Público) e dos grupos dos alvos com tópico, na chave
    "<grupo>_<tópico>" que os painéis consultam. A API de bot não lista tópicos de
    fórum; só uma conta de usuário consegue.
    """
    # A classe mudou de módulo entre versões do Telethon (channels -> messages)
    try:
        from telethon.tl.functions.messages import GetForumTopicsRequest
        _param_peer = "peer"
    except ImportError:
        from telethon.tl.functions.channels import GetForumTopicsRequest
        _param_peer = "channel"
    from utils import salvar_nome_grupo

    await asyncio.sleep(15)  # Deixa o get_dialogs terminar antes

    while True:
        try:
            config = db.ler_config("submissao_config", padrao={})

            # Inclui os grupos dos alvos com tópico: senão o painel do Espião mostra só o
            # nome do grupo, e vários alvos do mesmo fórum ficam iguais.
            grupos_alvo = []
            if config.get("grupo_id"):
                grupos_alvo.append(str(config.get("grupo_id")))
            try:
                for alvo in carregar_alvos():
                    if ":" in str(alvo):
                        base = str(alvo).split(":", 1)[0].strip()
                        if base not in grupos_alvo:
                            grupos_alvo.append(base)
            except Exception:
                pass

            if not grupos_alvo:
                await asyncio.sleep(600)
                continue

            for grupo_id in grupos_alvo:
                try:
                    entidade = await client.get_entity(int(grupo_id) if grupo_id.lstrip('-').isdigit() else grupo_id)
                    argumentos = {
                        _param_peer: entidade,
                        "offset_date": None,
                        "offset_id": 0,
                        "offset_topic": 0,
                        "limit": 100,
                    }
                    resultado = await client(GetForumTopicsRequest(**argumentos))

                    total = 0
                    for topico in getattr(resultado, 'topics', []):
                        topico_id = getattr(topico, 'id', None)
                        titulo = getattr(topico, 'title', None)
                        if topico_id is None or not titulo:
                            continue
                        salvar_nome_grupo(f"{grupo_id}_{topico_id}", titulo)
                        total += 1

                    if total:
                        logger.info(f"🏷️ [Tópicos] {total} nomes sincronizados do grupo {grupo_id}.")
                except Exception as e:
                    logger.warning(f"⚠️ [Tópicos] Falha ao sincronizar os tópicos do grupo {grupo_id}: {e}")

                await asyncio.sleep(3)   # respiro entre fóruns

        except Exception as e:
            logger.warning(f"⚠️ [Tópicos] Falha ao sincronizar nomes dos tópicos: {e}")

        await asyncio.sleep(600)

async def main():
    """Inicia a sessão do Telegram e os laços em segundo plano."""
    logger.info("🕵️ Iniciando o Módulo Espião de Clonagem...")
    garantir_tabela_registros_unicos()
    try:
        with open("status_espelhador.json", "w") as f:
            json.dump({}, f)
    except Exception:
        pass
    await client.start()
    
    logger.info("🔄 Sincronizando banco de dados de grupos e access_hashes...")
    try:
        await client.get_dialogs()
        logger.info("✅ Sincronização concluída! IDs numéricos agora serão reconhecidos pelo Auditor.")
    except Exception as e:
        logger.warning(f"⚠️ Aviso na sincronização: {e}")
        
    alvos = carregar_alvos()
    logger.info(f"📡 Radar ativo para {len(alvos)} concorrentes.")
    
    asyncio.create_task(processar_fila_espelhador_loop())
    asyncio.create_task(analisar_fila_espiao_loop())
    asyncio.create_task(monitorar_status_alvos())
    asyncio.create_task(monitorar_status_espelhos())
    asyncio.create_task(monitorar_topicos_submissao())
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())

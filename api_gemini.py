"""
Acesso ao Gemini (Google) para gerar texto e analisar vídeos.

As duas funções tentam os modelos de MODELOS_CASCATA_GEMINI em ordem e passam
para o próximo quando um falha, estoura a cota ou responde vazio. Modelo sem
cota ou que não existe fica de fora da cascata por um tempo (_fora_ate). A
chave fica em GEMINI_KEY no .env.
"""
import os
import re
import asyncio
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from google import genai

load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_KEY')

client_genai = genai.Client(api_key=GEMINI_API_KEY)

# Ordem de tentativa: o primeiro modelo que responder vence.
MODELOS_CASCATA_GEMINI = [
    "gemini-3.1-pro-preview",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-lite-preview"
]

logger = logging.getLogger("API_Gemini")

# Modelo que respondeu "sem cota" (429) ou "modelo não existe" (404) fica de fora
# da cascata por um tempo, em vez de gastar uma chamada a cada pedido: eram ~300
# por dia batendo em cota estourada. Vale por processo (cada robô descobre sozinho).
# Se todos estiverem de fora, a cascata tenta todos, como se não houvesse a pausa.
_fora_ate = {}                      # modelo -> time.monotonic() em que volta
ESPERA_COTA_S = 10 * 60             # cota estourada sem prazo informado
ESPERA_MODELO_INEXISTENTE_S = 6 * 3600


def _segundos_ate_virada_da_cota():
    """A cota diária do Gemini vira à meia-noite do horário do Pacífico."""
    agora = datetime.now(ZoneInfo("America/Los_Angeles"))
    virada = (agora + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return (virada - agora).total_seconds()


def tempo_fora(erro_txt):
    """
    (segundos, motivo) que o modelo fica de fora por esse erro, ou None se o erro
    não é de cota nem de modelo inexistente (aí ele continua na cascata).
    """
    if "429" in erro_txt or "RESOURCE_EXHAUSTED" in erro_txt.upper() or "quota" in erro_txt.lower():
        if "PerDay" in erro_txt:
            return _segundos_ate_virada_da_cota(), "cota do dia"
        prazo = re.search(r"retry\w*\W{0,6}(?:in\s+)?(\d+(?:\.\d+)?)s", erro_txt, re.IGNORECASE)
        if prazo:
            return float(prazo.group(1)) + 5, "cota do minuto"
        return ESPERA_COTA_S, "cota"
    if "NOT_FOUND" in erro_txt.upper():
        return ESPERA_MODELO_INEXISTENTE_S, "modelo não encontrado"
    return None


def _modelos_da_vez():
    agora = time.monotonic()
    livres = [m for m in MODELOS_CASCATA_GEMINI if _fora_ate.get(m, 0) <= agora]
    return livres or list(MODELOS_CASCATA_GEMINI)


def _tirar_da_vez(modelo, erro_txt):
    """Tira o modelo da cascata conforme o erro. True se tirou."""
    fora = tempo_fora(erro_txt)
    if fora is None:
        return False
    segundos, motivo = fora
    _fora_ate[modelo] = time.monotonic() + segundos
    volta = datetime.now() + timedelta(seconds=segundos)
    logger.warning(f"⏸️ [IA] {modelo} fora da cascata até {volta:%d/%m %H:%M} ({motivo}).")
    return True


# Motivo da última falha de analisar_video_gemini. O bot_mestre mostra na tela de
# submissão quando a análise falha, em vez de um genérico "falha temporária".
ULTIMO_ERRO_IA = None

def _motivo_resposta_vazia(response):
    """Explica por que a resposta veio sem texto (bloqueio de segurança, corte, filtro)."""
    try:
        pedacos = []
        feedback = getattr(response, "prompt_feedback", None)
        if feedback:
            pedacos.append(f"prompt_feedback={feedback}")
        for cand in (getattr(response, "candidates", None) or []):
            razao = getattr(cand, "finish_reason", None)
            if razao:
                pedacos.append(f"finish_reason={razao}")
            seguranca = getattr(cand, "safety_ratings", None)
            if seguranca:
                pedacos.append(f"safety={seguranca}")
        return " ; ".join(str(p) for p in pedacos) or "resposta sem candidatos"
    except Exception as e:
        return f"motivo ilegível ({e})"

async def gerar_texto_gemini(prompt):
    """
    Gera texto com o primeiro modelo da cascata que responder.

    Devolve o texto ou None se todos falharem (não grava ULTIMO_ERRO_IA).
    """
    for modelo_nome in _modelos_da_vez():
        try:
            logger.debug(f"⏳ [IA] Consultando motor: {modelo_nome}...")
            
            response = await asyncio.to_thread(
                client_genai.models.generate_content,
                model=modelo_nome,
                contents=prompt
            )
            
            if response and response.text:
                logger.info(f"✅ [IA] Sucesso com o modelo {modelo_nome}!")
                return response.text.strip()
                
        except Exception as e:
            if not _tirar_da_vez(modelo_nome, str(e)):
                logger.warning(f"⚠️ [IA] Erro no modelo {modelo_nome}: {str(e)[:80]}...")
            continue

    logger.error("❌ [IA] Falha crítica: Nenhum motor da cascata respondeu.")
    return None

async def analisar_video_gemini(caminho_video, prompt):
    """
    Sobe o vídeo para o Gemini, espera o processamento e pede a análise com
    `prompt`, tentando os modelos da cascata em ordem.

    O vídeo é sempre apagado do Google no final, com sucesso ou não, para não
    gastar a cota de armazenamento. O upload tem 3 tentativas. Roda numa thread
    porque a SDK é bloqueante. Devolve o texto ou None; em falha, o motivo
    fica em ULTIMO_ERRO_IA.
    """
    def processar_ia():
        logger.info("🚀 [IA] Iniciando upload do vídeo para o Google Storage...")
        
        video_gemini = None
        for tentativa in range(3):
            try:
                video_gemini = client_genai.files.upload(file=caminho_video)
                if video_gemini:
                    break
            except Exception as erro_rede:
                logger.warning(f"⚠️ [IA] Tentativa {tentativa+1}/3 falhou por instabilidade: {erro_rede}")
                if tentativa < 2: time.sleep(3)
                else: raise erro_rede
        
        try:
            while video_gemini.state.name == "PROCESSING":
                logger.info("⏳ [IA] O vídeo está sendo processado nos servidores da Google...")
                time.sleep(2)
                video_gemini = client_genai.files.get(name=video_gemini.name)
                
            if video_gemini.state.name == "FAILED":
                raise Exception("Falha de processamento no servidor do Google.")
                
            logger.info("✅ [IA] Vídeo pronto! Gerando a copy...")

            falhas = []   # motivo de cada modelo, para a mensagem de erro final
            for modelo_nome in _modelos_da_vez():
                try:
                    response = client_genai.models.generate_content(
                        model=modelo_nome,
                        contents=[video_gemini, prompt]
                    )

                    texto = None
                    try:
                        texto = response.text
                    except Exception as erro_texto:
                        falhas.append(f"{modelo_nome}: .text falhou ({erro_texto})")

                    if texto:
                        logger.info(f"✅ [IA] Sucesso com o modelo {modelo_nome}!")
                        return texto.strip()

                    # Respondeu, mas vazio: quase sempre é bloqueio de segurança do Google.
                    motivo = _motivo_resposta_vazia(response)
                    falhas.append(f"{modelo_nome}: VAZIO ({motivo})")
                    logger.warning(f"⚠️ [IA] {modelo_nome} devolveu resposta vazia → {motivo}")

                except Exception as erro_modelo:
                    erro_txt = str(erro_modelo)
                    falhas.append(f"{modelo_nome}: {type(erro_modelo).__name__} {erro_txt[:150]}")
                    if not _tirar_da_vez(modelo_nome, erro_txt):
                        logger.warning(f"⚠️ [IA] Erro em {modelo_nome}: {type(erro_modelo).__name__} → {erro_txt[:200]}")
                    continue

            raise Exception("Todos os modelos da cascata falharam → " + " | ".join(falhas))
        finally:
            if video_gemini:
                try:
                    client_genai.files.delete(name=video_gemini.name)
                    logger.info("🧹 [IA] Vídeo excluído do servidor do Google para liberar cota.")
                except Exception as e_del:
                    logger.warning(f"⚠️ [IA] Falha ao excluir vídeo do Google: {e_del}")

    try:
        resultado = await asyncio.to_thread(processar_ia)
        return resultado
    except Exception as e:
        global ULTIMO_ERRO_IA
        ULTIMO_ERRO_IA = str(e)[:400]
        logger.error(f"❌ [IA] Falha crítica na análise do vídeo: {e}")
        return None

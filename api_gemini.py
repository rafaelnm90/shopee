import os
import asyncio
import logging
import time
from dotenv import load_dotenv
from google import genai

# Carrega as chaves do .env para garantir segurança no GitHub
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_KEY')

# Inicializa o cliente moderno da SDK do Google
client_genai = genai.Client(api_key=GEMINI_API_KEY)

MODELOS_CASCATA_GEMINI = [
    "gemini-3.1-pro-preview",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-lite-preview"
]

logger = logging.getLogger("API_Gemini")

# 🔎 Guarda o motivo REAL da última falha da IA para o bot exibir na tela.
ULTIMO_ERRO_IA = None

def _motivo_resposta_vazia(response):
    """Traduz uma resposta sem texto no motivo real (bloqueio de segurança, corte, filtro)."""
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

# 🔎 Guarda o motivo REAL da última falha da IA para o bot exibir na tela.
ULTIMO_ERRO_IA = None

def _motivo_resposta_vazia(response):
    """Traduz uma resposta sem texto no motivo real (bloqueio de segurança, corte, filtro)."""
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

async def gerar_texto_gemini(prompt, exibir_logs=True):
    """Tenta gerar texto iterando pelos modelos da cascata até obter sucesso."""
    for modelo_nome in MODELOS_CASCATA_GEMINI:
        try:
            if exibir_logs: logger.info(f"⏳ [IA] Consultando motor: {modelo_nome}...")
            
            response = await asyncio.to_thread(
                client_genai.models.generate_content,
                model=modelo_nome,
                contents=prompt
            )
            
            if response and response.text:
                if exibir_logs: logger.info(f"✅ [IA] Sucesso com o modelo {modelo_nome}!")
                return response.text.strip()
                
        except Exception as e:
            erro_str = str(e).lower()
            if "429" in erro_str or "quota" in erro_str or "exhausted" in erro_str:
                if exibir_logs: logger.warning(f"⚠️ [IA] Limite atingido em {modelo_nome}. Pausando 2s...")
                await asyncio.sleep(2)
            else:
                if exibir_logs: logger.warning(f"⚠️ [IA] Erro no modelo {modelo_nome}: {erro_str[:50]}...")
            continue

    if exibir_logs: logger.error("❌ [IA] Falha crítica: Nenhum motor da cascata respondeu.")
    return None

async def analisar_video_gemini(caminho_video, prompt, exibir_logs=True):
    """Faz o upload do vídeo de forma segura, analisa com o prompt e limpa a nuvem em seguida."""
    def processar_ia():
        if exibir_logs: logger.info("🚀 [IA] Iniciando upload do vídeo para o Google Storage...")
        
        video_gemini = None
        for tentativa in range(3):
            try:
                video_gemini = client_genai.files.upload(file=caminho_video)
                if video_gemini:
                    break
            except Exception as erro_rede:
                if exibir_logs: logger.warning(f"⚠️ [IA] Tentativa {tentativa+1}/3 falhou por instabilidade: {erro_rede}")
                if tentativa < 2: time.sleep(3)
                else: raise erro_rede
        
        try:
            while video_gemini.state.name == "PROCESSING":
                if exibir_logs: logger.info("⏳ [IA] O vídeo está sendo processado nos servidores da Google...")
                time.sleep(2)
                video_gemini = client_genai.files.get(name=video_gemini.name)
                
            if video_gemini.state.name == "FAILED":
                raise Exception("Falha de processamento no servidor do Google.")
                
            if exibir_logs: logger.info("✅ [IA] Vídeo pronto! Gerando a copy...")

            falhas = []   # 🔎 registra por que CADA modelo recusou, para o log contar a história
            for modelo_nome in MODELOS_CASCATA_GEMINI:
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
                        if exibir_logs: logger.info(f"✅ [IA] Sucesso com o modelo {modelo_nome}!")
                        return texto.strip()

                    # 🚫 Respondeu, mas veio vazio: quase sempre é bloqueio de segurança do Google.
                    motivo = _motivo_resposta_vazia(response)
                    falhas.append(f"{modelo_nome}: VAZIO ({motivo})")
                    if exibir_logs: logger.warning(f"⚠️ [IA] {modelo_nome} devolveu resposta vazia → {motivo}")

                except Exception as erro_modelo:
                    erro_txt = str(erro_modelo)
                    falhas.append(f"{modelo_nome}: {type(erro_modelo).__name__} {erro_txt[:150]}")
                    if "429" in erro_txt or "RESOURCE_EXHAUSTED" in erro_txt.upper():
                        if exibir_logs: logger.warning(f"⚠️ [IA] Cota estourada em {modelo_nome}. Tentando o próximo...")
                        time.sleep(3)
                    else:
                        if exibir_logs: logger.warning(f"⚠️ [IA] Erro em {modelo_nome}: {type(erro_modelo).__name__} → {erro_txt[:200]}")
                    continue

            raise Exception("Todos os modelos da cascata falharam → " + " | ".join(falhas))
        finally:
            if video_gemini:
                try:
                    client_genai.files.delete(name=video_gemini.name)
                    if exibir_logs: logger.info("🧹 [IA] Vídeo excluído do servidor do Google para liberar cota.")
                except Exception as e_del:
                    if exibir_logs: logger.warning(f"⚠️ [IA] Falha ao excluir vídeo do Google: {e_del}")

    try:
        resultado = await asyncio.to_thread(processar_ia)
        return resultado
    except Exception as e:
        global ULTIMO_ERRO_IA
        ULTIMO_ERRO_IA = str(e)[:400]
        if exibir_logs: logger.error(f"❌ [IA] Falha crítica na análise do vídeo: {e}")
        return None

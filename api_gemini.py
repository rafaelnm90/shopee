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
    "gemini-2.5-pro",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash-lite"
]

logger = logging.getLogger("API_Gemini")

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

            for modelo_nome in MODELOS_CASCATA_GEMINI:
                try:
                    response = client_genai.models.generate_content(
                        model=modelo_nome,
                        contents=[video_gemini, prompt]
                    )
                    if response and response.text:
                        if exibir_logs: logger.info(f"✅ [IA] Sucesso com o modelo {modelo_nome}!")
                        return response.text.strip()
                except Exception as erro_modelo:
                    if "429" in str(erro_modelo):
                        if exibir_logs: logger.warning(f"⚠️ [IA] Limite atingido em {modelo_nome}. Tentando o próximo...")
                        time.sleep(3)
                    continue
            raise Exception("Todos os modelos da cascata falharam.")
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
        if exibir_logs: logger.error(f"❌ [IA] Falha crítica na análise do vídeo: {e}")
        return None

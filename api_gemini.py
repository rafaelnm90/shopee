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

# Ordem de tentativa: o primeiro modelo que responder vence. Cada modelo tem a própria
# cota diária, por isso a lista é longa: o melhor vem primeiro e os outros seguram o
# dia quando a cota dos de cima acaba. Conferida com a chave pelo modelos_ia.yml (24/10/2026):
# o 3.7 e o 3.5 Flash foram descontinuados, mas o Google ainda os atende (redireciona
# para o 3.8 e o 3.6); ficam enquanto responderem, e o que der "não encontrado" sai da
# vez sozinho por 6 h (tempo_fora). Escolha do Rafael (P14): DECISOES.md, Código e manutenção.
MODELOS_CASCATA_GEMINI = [
    "gemini-4-argon",
    "gemini-3.1-pro-preview",
    "gemini-pro-latest",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
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

# Os códigos do Google (finish_reason e block_reason) de resposta vazia pelo conteúdo do
# vídeo: se repetem para o mesmo vídeo, em todos os modelos. Quem pediu a análise põe o
# vídeo de lado; não é falha do robô nem da IA.
BLOQUEIOS_DO_CONTEUDO = {"PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "SAFETY", "IMAGE_SAFETY"}


def codigos_do_google(texto):
    """Os códigos de finish_reason e block_reason que aparecem no texto, sem o STOP."""
    return set(re.findall(r"(?:finish|block)_reason=<?(?:\w+\.)?([A-Z_]{3,})", texto or "")) - {"STOP"}


class ConteudoBloqueado(Exception):
    """Todos os modelos que responderam recusaram o conteúdo do vídeo (os outros estavam sem cota)."""


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

async def analisar_video_gemini(caminho_video, prompt, imagens=None):
    """
    Sobe o vídeo para o Gemini, espera o processamento e pede a análise com
    `prompt`, tentando os modelos da cascata em ordem. imagens: [(bytes, tipo)] que
    vão junto com o vídeo (a foto do anúncio, para a IA comparar com o vídeo).

    O vídeo é sempre apagado do Google no final, com sucesso ou não, para não
    gastar a cota de armazenamento. O upload tem 3 tentativas. Roda numa thread
    porque a SDK é bloqueante. Devolve o texto ou None; em falha, o motivo
    fica em ULTIMO_ERRO_IA.
    """
    global ULTIMO_ERRO_IA

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
            from google.genai import types
            partes_das_imagens = [types.Part.from_bytes(data=dados, mime_type=tipo) for dados, tipo in imagens or []]

            falhas = []   # motivo de cada modelo, para a mensagem de erro final
            recusas = 0   # modelos que responderam vazio pelo conteúdo do vídeo
            outras = 0    # falhas que não são recusa do conteúdo nem cota ou modelo inexistente
            for modelo_nome in _modelos_da_vez():
                try:
                    response = client_genai.models.generate_content(
                        model=modelo_nome,
                        contents=[video_gemini, *partes_das_imagens, prompt]
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
                    if BLOQUEIOS_DO_CONTEUDO & codigos_do_google(motivo):
                        recusas += 1
                    else:
                        outras += 1
                    logger.warning(f"⚠️ [IA] {modelo_nome} devolveu resposta vazia → {motivo}")

                except Exception as erro_modelo:
                    erro_txt = str(erro_modelo)
                    falhas.append(f"{modelo_nome}: {type(erro_modelo).__name__} {erro_txt[:150]}")
                    if not _tirar_da_vez(modelo_nome, erro_txt):
                        outras += 1
                        logger.warning(f"⚠️ [IA] Erro em {modelo_nome}: {type(erro_modelo).__name__} → {erro_txt[:200]}")
                    continue

            mensagem = "Todos os modelos da cascata falharam → " + " | ".join(falhas)
            if recusas and not outras:
                raise ConteudoBloqueado(mensagem)
            raise Exception(mensagem)
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
    except ConteudoBloqueado as e:
        # O vídeo é que não serve (quem pediu o põe de lado): aviso, não erro do robô.
        ULTIMO_ERRO_IA = str(e)[:400]
        logger.warning(f"🚫 [IA] O Google recusou o conteúdo do vídeo em todos os modelos: {e}")
        return None
    except Exception as e:
        ULTIMO_ERRO_IA = str(e)[:400]
        logger.error(f"❌ [IA] Falha crítica na análise do vídeo: {e}")
        return None


# --- Os modelos que a chave enxerga (modelos_ia.yml) ---

# Modelos de generateContent que não servem aos robôs (imagem, voz, embeddings...).
FORA_DOS_ROBOS = ("image", "tts", "audio", "live", "embedding", "robotics", "computer-use", "veo", "imagen",
                  "transcribe", "banana", "customtools")


def modelos_da_chave():
    """Os modelos Gemini de texto (generateContent) que a chave do .env enxerga, só os nomes."""
    nomes = (m.name.split("/")[-1] for m in client_genai.models.list() if "generateContent" in (m.supported_actions or []))
    return sorted(n for n in nomes if n.startswith("gemini") and not any(p in n for p in FORA_DOS_ROBOS))


def testar_modelo(modelo):
    """Uma chamada curta ao modelo: "responde", ou o motivo fixo de não responder."""
    try:
        resposta = client_genai.models.generate_content(model=modelo, contents="Responda só: ok")
        return "responde" if (resposta and resposta.text) else "resposta vazia"
    except Exception as e:
        fora = tempo_fora(str(e))
        return fora[1] if fora else f"erro {type(e).__name__}"


def relatorio_dos_modelos(da_chave, testar=None):
    """
    As linhas do modelos_ia.yml: cada modelo da cascata, se a chave enxerga e (com testar)
    se responde, e os modelos de texto da chave que não estão na cascata. Só nomes de
    modelo e motivos fixos: o log do Actions é público.
    """
    def situacao(modelo):
        partes = ["na chave" if modelo in da_chave else "fora da chave"]
        if testar:
            partes.append(testar(modelo))
        return ", ".join(partes)

    linhas = ["== Cascata (na ordem)"] + [f"{modelo}: {situacao(modelo)}" for modelo in MODELOS_CASCATA_GEMINI]
    novos = [m for m in da_chave if m not in MODELOS_CASCATA_GEMINI]
    linhas.append("== Modelos de texto da chave fora da cascata")
    linhas += [f"{modelo}: {situacao(modelo)}" for modelo in novos] or ["nenhum"]
    return linhas


if __name__ == "__main__":
    import sys
    if not sys.argv[1:] or sys.argv[1] != "modelos":
        print("Uso: python3 api_gemini.py modelos [--testar]")
        sys.exit(2)
    logging.disable(logging.CRITICAL)
    print("\n".join(relatorio_dos_modelos(modelos_da_chave(), testar_modelo if "--testar" in sys.argv else None)))

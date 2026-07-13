EXIBIR_LOGS = True
import json
import os
from datetime import datetime
import logging
import traceback

if EXIBIR_LOGS:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger = logging.getLogger(__name__)

MAX_ERRORS = 50
LOG_FILE = "erros_logs.json"

def registrar_erro_json(mensagem_erro, origem="Geral", contexto_extra=None):
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        else:
            logs = []

        # Captura a linha exata e a cascata de execução que gerou a falha
        rastro = traceback.format_exc()
        if rastro == "NoneType: None\n":
            rastro = "Sem rastro de código associado (Possível erro lógico ou manual)."

        novo_log = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "origem": origem,
            "erro": str(mensagem_erro),
            "rastro_codigo": rastro.strip(),
            "contexto": contexto_extra if contexto_extra else {}
        }
        logs.append(novo_log)

        if len(logs) > MAX_ERRORS:
            logs = logs[-MAX_ERRORS:]

        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=4, ensure_ascii=False)
            
        if EXIBIR_LOGS: logger.info(f"✅ Sucesso: Erro de {origem} registado com rastro no ficheiro JSON.")
    except Exception as e:
        if EXIBIR_LOGS: logger.error(f"❌ Falha crítica ao tentar registar log no JSON: {e}")

"""
Manda um aviso curto no privado do Rafael pelo bot principal. Usado pelo
workflow avisar.yml, que o Claude dispara quando uma pergunta dele ao Rafael
está há muito tempo sem resposta (regra no CLAUDE.md, "Como trabalhamos"). O
tela_android.py usa o mandar_texto para levar o link da tela do Android.

    python3 avisar_rafael.py "assunto da pendência" [link da sessão do Claude]

Roda no servidor, onde está o .env com o token do bot. Não é serviço: manda
uma mensagem e sai.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

from dotenv import load_dotenv

PASTA = os.path.dirname(os.path.abspath(__file__))


def admin_id():
    """O ADMIN_ID fixo do bot_mestre, lido do arquivo para não subir o bot inteiro."""
    with open(os.path.join(PASTA, "bot_mestre.py"), encoding="utf-8") as f:
        casou = re.search(r"^ADMIN_ID\s*=\s*(\d+)", f.read(), re.MULTILINE)
    if not casou:
        raise RuntimeError("ADMIN_ID não encontrado no bot_mestre.py")
    return int(casou.group(1))


def montar_texto(assunto, link=""):
    texto = ("🤖 O Claude está esperando uma resposta sua.\n\n"
             f"📌 {assunto.strip()[:300]}\n\n"
             "Abra a conversa com o Claude para responder.")
    if link.strip():
        texto += f"\n{link.strip()}"
    return texto


def mandar_texto(texto):
    """Manda um texto no privado do Rafael pelo Bot API. Devolve True se o Telegram aceitou."""
    load_dotenv(os.path.join(PASTA, ".env"))
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN ausente no .env")
    dados = urllib.parse.urlencode({"chat_id": admin_id(), "text": texto,
                                    "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", dados, timeout=20) as r:
        return bool(json.loads(r.read().decode()).get("ok"))


def enviar(assunto, link=""):
    """O aviso de pergunta sem resposta. Devolve True se o Telegram aceitou."""
    return mandar_texto(montar_texto(assunto, link))


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("uso: avisar_rafael.py \"assunto\" [link]")
        sys.exit(2)
    try:
        ok = enviar(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "")
    except Exception as e:
        # Só o tipo: a mensagem de erro do urllib pode trazer a URL com o token.
        print(f"❌ Aviso não enviado: {type(e).__name__}")
        sys.exit(1)
    print("✅ Aviso enviado ao Rafael." if ok else "❌ O Telegram recusou o aviso.")
    sys.exit(0 if ok else 1)

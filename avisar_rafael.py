"""
Manda um aviso curto no privado do Rafael pelo bot principal. Usado pelo
workflow avisar.yml para o lembrete diário das pendências (as perguntas do
Claude vão pelo perguntas_rafael.py, que usa o mandar_texto). O tela_android.py
usa o mandar_texto para levar o link da tela do Android, e o
postador_shopee_video.py usa o mandar_foto para o print do rascunho.

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
import uuid

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
    """
    O lembrete diário das pendências (assunto começando com "Lembrete") não é pergunta:
    dizer que o Claude espera uma resposta fazia o Rafael procurar uma pergunta que não
    existia.
    """
    if assunto.strip().casefold().startswith("lembrete"):
        topo, fim = "🤖 Lembrete do Claude: o que está pendente.", "Abra a conversa com o Claude para ver a lista."
    else:
        topo, fim = "🤖 O Claude está esperando uma resposta sua.", "Abra a conversa com o Claude para responder."
    texto = f"{topo}\n\n📌 {assunto.strip()[:300]}\n\n{fim}"
    if link.strip():
        texto += f"\n{link.strip()}"
    return texto


def _chamar(metodo, campos):
    """Uma chamada ao Bot API no privado do Rafael. Devolve a resposta do Telegram (dict)."""
    load_dotenv(os.path.join(PASTA, ".env"))
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN ausente no .env")
    dados = urllib.parse.urlencode({"chat_id": admin_id(), **campos}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{metodo}", dados, timeout=20) as r:
        return json.loads(r.read().decode())


def mandar_texto_com_id(texto, html=False):
    """
    Manda um texto no privado do Rafael e devolve o id da mensagem, para apagar depois
    (True se o Telegram aceitou sem dizer o id; None se recusou). html=True: o texto vem
    em HTML (negrito, o <code> que copia com um toque).
    """
    campos = {"text": texto, "disable_web_page_preview": "true"}
    if html:
        campos["parse_mode"] = "HTML"
    resposta = _chamar("sendMessage", campos)
    if not resposta.get("ok"):
        return None
    return (resposta.get("result") or {}).get("message_id") or True


def mandar_texto(texto, html=False):
    """Manda um texto no privado do Rafael pelo Bot API. Devolve True se o Telegram aceitou."""
    return mandar_texto_com_id(texto, html) is not None


def apagar_mensagem(ident):
    """Apaga uma mensagem do bot no privado. O Telegram só deixa até 48 h depois do envio: False depois disso."""
    try:
        return bool(_chamar("deleteMessage", {"message_id": ident}).get("ok"))
    except Exception:
        return False


def editar_texto(ident, texto):
    """Troca o texto de uma mensagem do bot no privado (o que já não dá para apagar)."""
    try:
        return bool(_chamar("editMessageText", {"message_id": ident, "text": texto}).get("ok"))
    except Exception:
        return False


def mandar_foto(caminho, legenda=""):
    """Manda uma imagem no privado do Rafael pelo Bot API. Devolve True se o Telegram aceitou."""
    load_dotenv(os.path.join(PASTA, ".env"))
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN ausente no .env")
    fronteira = uuid.uuid4().hex
    partes = []
    for nome, valor in (("chat_id", str(admin_id())), ("caption", legenda[:1000])):
        partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n{valor}\r\n'.encode())
    with open(caminho, "rb") as f:
        imagem = f.read()
    partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="photo"; filename="tela.png"\r\n'
                  "Content-Type: image/png\r\n\r\n".encode() + imagem + b"\r\n")
    partes.append(f"--{fronteira}--\r\n".encode())
    pedido = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendPhoto", data=b"".join(partes),
                                    headers={"Content-Type": f"multipart/form-data; boundary={fronteira}"})
    with urllib.request.urlopen(pedido, timeout=60) as r:
        return bool(json.loads(r.read().decode()).get("ok"))


def enviar(assunto, link=""):
    """O aviso de pergunta sem resposta, ou o lembrete do dia. Devolve True se o Telegram aceitou."""
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

#!/usr/bin/env python3
"""
As perguntas do Claude ao Rafael no privado do bot principal, lembradas de hora em
hora, a qualquer hora, até ele responder. O seletor da conversa com o Claude pode
sumir sem ele ver; o privado do bot ele vê.
Pedido do Rafael: DECISOES.md, Trabalho com o Claude.

O caminho:
- o Claude escreve a pergunta num JSON e cifra com a chave do servidor (a do
  registro_privado, que ele tem no ambiente): o repositório, os logs e as entradas
  do Actions são públicos;
- o avisar.yml leva o texto cifrado ao servidor ("nova"): a pergunta entra na
  tabela perguntas_rafael e sai na hora no privado, com um código (P1, P2...);
- o bot_mestre (lembrar) manda de novo a cada hora enquanto ela estiver aberta,
  mesmo que o Claude esteja sem crédito;
- quando o Rafael responde, o Claude marca pelo avisar.yml ("respondida P3") e os
  lembretes param.

Cada aviso traz a pergunta, as opções, o texto pronto para o Rafael copiar com um
toque (no Telegram, o texto em <code> copia ao tocar) e colar na conversa com a
resposta, e o link da conversa. No log, só o código.

    python3 perguntas_rafael.py cifrar ARQUIVO.json   # no ambiente do Claude
    python3 perguntas_rafael.py nova TEXTO_CIFRADO     # no servidor (avisar.yml)
    python3 perguntas_rafael.py respondida P3          # no servidor (avisar.yml)

O JSON: {"pergunta": "...", "opcoes": [{"rotulo": "...", "descricao": "..."}], "link": "https://..."}.
"""
import html
import json
import logging
import os
import sys
from datetime import datetime, timedelta

import db
from fuso import fuso_horario

logger = logging.getLogger(__name__)

INTERVALO = timedelta(hours=1)
# O aviso tem de caber numa mensagem do Telegram (4096 caracteres).
TAMANHO_DA_PERGUNTA, TAMANHO_DO_ROTULO, TAMANHO_DA_DESCRICAO, MAXIMO_DE_OPCOES = 900, 80, 220, 6
# O começo do texto para copiar, como o Rafael pediu.
COMECO_DA_RESPOSTA = "Vc me enviou anteriormente a pergunta"


def _momento(agora=None):
    return (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d %H:%M:%S")


def _criar_tabela(con):
    con.execute("CREATE TABLE IF NOT EXISTS perguntas_rafael ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, pergunta TEXT, opcoes TEXT, link TEXT, criada TEXT, "
                "ultimo_aviso TEXT, avisos INTEGER DEFAULT 0, respondida TEXT)")


def _opcoes(opcoes):
    """As opções como [{"rotulo", "descricao"}], aceitando também uma lista de textos."""
    limpas = []
    for opcao in (opcoes or [])[:MAXIMO_DE_OPCOES]:
        if isinstance(opcao, dict):
            rotulo, descricao = str(opcao.get("rotulo") or "").strip(), str(opcao.get("descricao") or "").strip()
        else:
            rotulo, descricao = str(opcao).strip(), ""
        if rotulo:
            limpas.append({"rotulo": rotulo[:TAMANHO_DO_ROTULO], "descricao": descricao[:TAMANHO_DA_DESCRICAO]})
    return limpas


def codigo(ident):
    return f"P{ident}"


def nova(pergunta, opcoes, link="", agora=None):
    """Guarda a pergunta aberta e devolve o código dela (P1, P2...)."""
    pergunta = " ".join(str(pergunta or "").split())[:TAMANHO_DA_PERGUNTA]
    if not pergunta:
        raise ValueError("pergunta vazia")
    with db.conexao() as con:
        _criar_tabela(con)
        cursor = con.execute("INSERT INTO perguntas_rafael (pergunta, opcoes, link, criada) VALUES (?, ?, ?, ?)",
                             (pergunta, json.dumps(_opcoes(opcoes), ensure_ascii=False), str(link or "").strip(),
                              _momento(agora)))
        return codigo(cursor.lastrowid)


def _ler(linhas):
    return [{"id": linha[0], "codigo": codigo(linha[0]), "pergunta": linha[1], "opcoes": json.loads(linha[2] or "[]"),
             "link": linha[3], "ultimo_aviso": linha[4], "avisos": linha[5] or 0} for linha in linhas]


def abertas():
    """As perguntas ainda sem resposta, da mais velha para a mais nova."""
    with db.conexao() as con:
        _criar_tabela(con)
        return _ler(con.execute("SELECT id, pergunta, opcoes, link, ultimo_aviso, avisos FROM perguntas_rafael "
                                "WHERE respondida IS NULL ORDER BY id").fetchall())


def marcar_respondida(cod, agora=None):
    """Para de lembrar a pergunta. False se o código não existe ou ela já estava respondida."""
    numero = str(cod or "").strip().upper().lstrip("P")
    if not numero.isdigit():
        return False
    with db.conexao() as con:
        _criar_tabela(con)
        cursor = con.execute("UPDATE perguntas_rafael SET respondida = ? WHERE id = ? AND respondida IS NULL",
                             (_momento(agora), int(numero)))
        return cursor.rowcount > 0


def vencidas(agora=None):
    """As abertas que ainda não foram avisadas ou cujo último aviso tem 1 h ou mais."""
    limite = _momento((agora or datetime.now(fuso_horario)) - INTERVALO)
    return [p for p in abertas() if not p["ultimo_aviso"] or p["ultimo_aviso"] <= limite]


def marcar_aviso(ident, agora=None):
    with db.conexao() as con:
        _criar_tabela(con)
        con.execute("UPDATE perguntas_rafael SET ultimo_aviso = ?, avisos = COALESCE(avisos, 0) + 1 WHERE id = ?",
                    (_momento(agora), ident))


def texto_para_copiar(p):
    """O texto que o Rafael copia com um toque e cola na conversa, com a resposta no fim."""
    rotulos = "; ".join(f"{i}) {opcao['rotulo']}" for i, opcao in enumerate(p["opcoes"], 1))
    opcoes = f" (opções: {rotulos})" if rotulos else ""
    return f"[{p['codigo']}] {COMECO_DA_RESPOSTA} \"{p['pergunta']}\"{opcoes} eu gostaria de responder: "


def montar_aviso(p):
    """O aviso em HTML: a pergunta, as opções, o texto para copiar e o link da conversa."""
    avisos = p.get("avisos") or 0
    topo = ("❓ <b>Pergunta nova do Claude para você</b>" if not avisos
            else f"🔔 <b>Lembrete {avisos + 1}: a pergunta do Claude ainda espera a sua resposta</b>")
    linhas = [f"{topo} ({p['codigo']})", "", f"<b>Pergunta:</b> {html.escape(p['pergunta'])}"]
    if p["opcoes"]:
        linhas += ["", "<b>Opções:</b>"]
        for i, opcao in enumerate(p["opcoes"], 1):
            descricao = f": {html.escape(opcao['descricao'])}" if opcao["descricao"] else ""
            linhas.append(f"{i}. <b>{html.escape(opcao['rotulo'])}</b>{descricao}")
    linhas += ["", "👇 Toque no texto abaixo para copiar. Abra a conversa com o Claude, cole e escreva a sua "
                   "resposta no fim:", f"<code>{html.escape(texto_para_copiar(p))}</code>"]
    if p.get("link"):
        linhas += ["", f"🔗 Abrir a conversa com o Claude: {html.escape(p['link'])}"]
    linhas += ["", "Lembro de hora em hora até você responder."]
    return "\n".join(linhas)


async def lembrar(enviar, agora=None):
    """
    Manda de novo cada pergunta aberta cujo último aviso tem 1 h ou mais. enviar(texto)
    é a função do robô que manda no privado (async, devolve True se saiu). Um aviso que
    não sai fica para a próxima volta. Devolve quantos saíram.
    """
    enviados = 0
    for p in vencidas(agora):
        try:
            if await enviar(montar_aviso(p)):
                marcar_aviso(p["id"], agora)
                enviados += 1
        except Exception as e:
            logger.warning(f"⚠️ [Perguntas do Claude] Lembrete de {p['codigo']} não saiu: {type(e).__name__}")
    return enviados


# --- Linha de comando (avisar.yml no servidor; cifrar no ambiente do Claude) ---

def cifrar(dados, valor_chave):
    from cryptography.fernet import Fernet
    return Fernet(valor_chave).encrypt(json.dumps(dados, ensure_ascii=False).encode()).decode()


def abrir(texto_cifrado, valor_chave):
    from cryptography.fernet import Fernet
    return json.loads(Fernet(valor_chave).decrypt(texto_cifrado.strip().encode()).decode())


def receber(texto_cifrado, agora=None):
    """No servidor: abre a pergunta cifrada, guarda, manda na hora e devolve o código."""
    import avisar_rafael
    import registro_privado
    dados = abrir(texto_cifrado, registro_privado.chave())
    cod = nova(dados.get("pergunta"), dados.get("opcoes"), dados.get("link"), agora)
    p = next(p for p in abertas() if p["codigo"] == cod)
    if avisar_rafael.mandar_texto(montar_aviso(p), html=True):
        marcar_aviso(p["id"], agora)
    return cod


def main(argumentos):
    if len(argumentos) != 2 or argumentos[0] not in ("cifrar", "nova", "respondida"):
        print("uso: perguntas_rafael.py cifrar ARQUIVO.json | nova TEXTO_CIFRADO | respondida CODIGO")
        return 2
    acao, valor = argumentos
    try:
        if acao == "cifrar":
            import registro_privado
            chave = os.getenv(registro_privado.VARIAVEL_CHAVE, "").strip()
            if not chave:
                print(f"❌ {registro_privado.VARIAVEL_CHAVE} ausente no ambiente")
                return 1
            with open(valor, encoding="utf-8") as arquivo:
                print(cifrar(json.load(arquivo), chave))
            return 0
        if acao == "nova":
            print(f"✅ Pergunta {receber(valor)} guardada e enviada ao Rafael; lembrete de hora em hora.")
            return 0
        if marcar_respondida(valor):
            import avisar_rafael
            cod = valor.strip().upper()
            avisar_rafael.mandar_texto(f"✅ Recebi a sua resposta da pergunta {cod}. Parei de lembrar.")
            print(f"✅ {cod} respondida: os lembretes pararam.")
            return 0
        print("⚠️ Código não encontrado ou já respondido.")
        return 1
    except Exception as e:
        # Só o tipo: a mensagem pode trazer o texto da pergunta ou a URL com o token.
        print(f"❌ Falhou: {type(e).__name__}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

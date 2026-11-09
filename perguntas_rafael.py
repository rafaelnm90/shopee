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
- quando o Rafael responde, o Claude marca pelo avisar.yml ("respondida P3"): os
  lembretes param e o bot apaga do privado a pergunta e os lembretes dela (o que já
  passou das 48 h que o Telegram deixa apagar fica com o texto trocado por "respondida"),
  para o Rafael não responder duas vezes. Fica só o "Recebi a sua resposta".

Cada aviso traz a pergunta, as opções, o texto pronto para o Rafael copiar com um
toque (no Telegram, o texto em <code> copia ao tocar) e colar na conversa com a
resposta, e o link da conversa. No log, só o código.

    python3 perguntas_rafael.py cifrar ARQUIVO.json   # no ambiente do Claude
    python3 perguntas_rafael.py nova TEXTO_CIFRADO     # no servidor (avisar.yml)
    python3 perguntas_rafael.py respondida P3          # no servidor (avisar.yml)

O JSON: {"pergunta": "...", "opcoes": [{"rotulo": "...", "descricao": "..."}], "link": "https://..."}.

As informações importantes do Claude vão pelo mesmo caminho (pedido do Rafael, 09/11): o que
o Claude traz e importa (a resposta a uma pergunta dele, o resultado de uma conferência ou
medição que ele espera, o que pede a atenção ou uma ação dele) é lembrado de hora em hora, com
um código I1, I2..., até ele dizer que viu: o botão Vi ✅ do aviso (o bot_mestre marca) ou o
"ok" na conversa com o Claude (o Claude marca pelo avisar.yml). Ao marcar, os lembretes saem do
privado; o aviso de onde ele veio fica, sem o botão, para consulta.

    python3 perguntas_rafael.py informacao TEXTO_CIFRADO  # no servidor (avisar.yml)
    python3 perguntas_rafael.py vista I3                  # no servidor (avisar.yml)

O JSON da informação: {"informacao": "...", "link": "https://..."}; o cifrar é o mesmo.
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
# A informação cabe numa mensagem do Telegram com o topo, o link e o fim (4096 caracteres).
TAMANHO_DA_INFORMACAO = 3000
# O botão Vi ✅ do aviso da informação: o bot_mestre (informacao_vista) marca como vista.
CALLBACK_VI = "info_vi:"


def _momento(agora=None):
    return (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d %H:%M:%S")


def _criar_tabela(con):
    con.execute("CREATE TABLE IF NOT EXISTS perguntas_rafael ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, pergunta TEXT, opcoes TEXT, link TEXT, criada TEXT, "
                "ultimo_aviso TEXT, avisos INTEGER DEFAULT 0, respondida TEXT, mensagens TEXT)")
    # A coluna que veio depois entra na tabela que já existe no servidor.
    if "mensagens" not in {linha[1] for linha in con.execute("PRAGMA table_info(perguntas_rafael)")}:
        con.execute("ALTER TABLE perguntas_rafael ADD COLUMN mensagens TEXT")


def _criar_tabela_das_informacoes(con):
    con.execute("CREATE TABLE IF NOT EXISTS informacoes_rafael ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT, link TEXT, criada TEXT, "
                "ultimo_aviso TEXT, avisos INTEGER DEFAULT 0, vista TEXT, mensagens TEXT)")


def _anotar_aviso(con, tabela, ident, agora, mensagem):
    """O aviso saiu (tabela: a das perguntas ou a das informações); mensagem: o id dele no privado."""
    linha = con.execute(f"SELECT mensagens FROM {tabela} WHERE id = ?", (ident,)).fetchone()
    mensagens = json.loads((linha[0] if linha else None) or "[]")
    if type(mensagem) is int:
        mensagens.append(mensagem)
    con.execute(f"UPDATE {tabela} SET ultimo_aviso = ?, avisos = COALESCE(avisos, 0) + 1, mensagens = ? "
                "WHERE id = ?", (_momento(agora), json.dumps(mensagens), ident))


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


def marcar_aviso(ident, agora=None, mensagem=None):
    """O aviso saiu; mensagem: o id dele no privado, para apagar quando a pergunta for respondida."""
    with db.conexao() as con:
        _criar_tabela(con)
        _anotar_aviso(con, "perguntas_rafael", ident, agora, mensagem)


def mensagens_de(cod):
    """Os ids, no privado, da pergunta e dos lembretes dela."""
    numero = str(cod or "").strip().upper().lstrip("P")
    if not numero.isdigit():
        return []
    with db.conexao() as con:
        _criar_tabela(con)
        linha = con.execute("SELECT mensagens FROM perguntas_rafael WHERE id = ?", (int(numero),)).fetchone()
    return json.loads((linha[0] if linha else None) or "[]")


def limpar_do_privado(cod, apagar, editar):
    """
    Pergunta respondida: tira do privado a pergunta e os lembretes dela, para o Rafael
    não responder duas vezes. O que o Telegram não deixa mais apagar (mais de 48 h) fica
    com o texto trocado. Pedido do Rafael: DECISOES.md, Trabalho com o Claude.
    """
    mensagens = mensagens_de(cod)
    apagadas = 0
    for ident in mensagens:
        if apagar(ident):
            apagadas += 1
        else:
            editar(ident, f"✅ Pergunta {cod} respondida: este aviso não vale mais.")
    return apagadas, len(mensagens)


def texto_da_confirmacao(cod, apagadas, total):
    """O "Recebi a sua resposta" que fica no privado, dizendo o que saiu de lá."""
    texto = f"✅ Recebi a sua resposta da pergunta {cod}. Parei de lembrar"
    if not total:
        return texto + "."
    if apagadas == total:
        return texto + " e apaguei daqui a pergunta e os lembretes dela."
    return (texto + f" e apaguei daqui {apagadas} mensagem(ns) dela. As de mais de 2 dias, que o Telegram "
            "não deixa apagar, ficaram marcadas como respondidas.")


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
    é a função do robô que manda no privado (async, devolve o id da mensagem, que fica
    guardado para apagar depois, ou True se saiu). Um aviso que não sai fica para a
    próxima volta. Devolve quantos saíram.
    """
    enviados = 0
    for p in vencidas(agora):
        try:
            mensagem = await enviar(montar_aviso(p))
            if mensagem:
                marcar_aviso(p["id"], agora, mensagem)
                enviados += 1
        except Exception as e:
            logger.warning(f"⚠️ [Perguntas do Claude] Lembrete de {p['codigo']} não saiu: {type(e).__name__}")
    return enviados


# --- Informações importantes do Claude (pedido do Rafael, 09/11) ---

def codigo_da_informacao(ident):
    return f"I{ident}"


def _numero_da_informacao(cod):
    """O número do código da informação (I3 → 3); None se não é um código de informação."""
    texto = str(cod or "").strip().upper()
    return int(texto[1:]) if texto.startswith("I") and texto[1:].isdigit() else None


def nova_informacao(texto, link="", agora=None):
    """Guarda a informação ainda não vista e devolve o código dela (I1, I2...). As linhas do texto ficam."""
    texto = str(texto or "").strip()[:TAMANHO_DA_INFORMACAO]
    if not texto:
        raise ValueError("informação vazia")
    with db.conexao() as con:
        _criar_tabela_das_informacoes(con)
        cursor = con.execute("INSERT INTO informacoes_rafael (texto, link, criada) VALUES (?, ?, ?)",
                             (texto, str(link or "").strip(), _momento(agora)))
        return codigo_da_informacao(cursor.lastrowid)


def informacoes_abertas():
    """As informações que o Rafael ainda não disse que viu, da mais velha para a mais nova."""
    with db.conexao() as con:
        _criar_tabela_das_informacoes(con)
        linhas = con.execute("SELECT id, texto, link, ultimo_aviso, avisos FROM informacoes_rafael "
                             "WHERE vista IS NULL ORDER BY id").fetchall()
    return [{"id": linha[0], "codigo": codigo_da_informacao(linha[0]), "texto": linha[1], "link": linha[2],
             "ultimo_aviso": linha[3], "avisos": linha[4] or 0} for linha in linhas]


def informacoes_vencidas(agora=None):
    """As não vistas que ainda não foram avisadas ou cujo último aviso tem 1 h ou mais."""
    limite = _momento((agora or datetime.now(fuso_horario)) - INTERVALO)
    return [i for i in informacoes_abertas() if not i["ultimo_aviso"] or i["ultimo_aviso"] <= limite]


def marcar_vista(cod, agora=None):
    """Para de lembrar a informação. False se o código não existe ou ela já estava vista."""
    numero = _numero_da_informacao(cod)
    if numero is None:
        return False
    with db.conexao() as con:
        _criar_tabela_das_informacoes(con)
        cursor = con.execute("UPDATE informacoes_rafael SET vista = ? WHERE id = ? AND vista IS NULL",
                             (_momento(agora), numero))
        return cursor.rowcount > 0


def marcar_aviso_da_informacao(ident, agora=None, mensagem=None):
    """O aviso da informação saiu; mensagem: o id dele no privado, para tirar os lembretes depois."""
    with db.conexao() as con:
        _criar_tabela_das_informacoes(con)
        _anotar_aviso(con, "informacoes_rafael", ident, agora, mensagem)


def mensagens_da_informacao(cod):
    """Os ids, no privado, do aviso da informação e dos lembretes dela, do mais velho para o mais novo."""
    numero = _numero_da_informacao(cod)
    if numero is None:
        return []
    with db.conexao() as con:
        _criar_tabela_das_informacoes(con)
        linha = con.execute("SELECT mensagens FROM informacoes_rafael WHERE id = ?", (numero,)).fetchone()
    return json.loads((linha[0] if linha else None) or "[]")


def montar_aviso_da_informacao(i):
    """O aviso em HTML: a informação, o link da conversa e como dizer que viu."""
    avisos = i.get("avisos") or 0
    topo = ("📌 <b>Informação importante do Claude para você</b>" if not avisos
            else f"🔔 <b>Lembrete {avisos + 1}: a informação do Claude ainda espera o seu ok</b>")
    linhas = [f"{topo} ({i['codigo']})", "", html.escape(i["texto"])]
    if i.get("link"):
        linhas += ["", f"🔗 Abrir a conversa com o Claude: {html.escape(i['link'])}"]
    linhas += ["", "Toque em <b>Vi ✅</b> quando tiver lido (ou responda ok na conversa com o Claude). Lembro de "
                   "hora em hora até lá."]
    return "\n".join(linhas)


def teclado_da_informacao(i):
    """O botão Vi ✅ do aviso, no formato do Bot API (o bot_mestre o monta no aiogram)."""
    return {"inline_keyboard": [[{"text": "Vi ✅", "callback_data": f"{CALLBACK_VI}{i['id']}"}]]}


async def lembrar_informacoes(enviar, agora=None):
    """
    Manda de novo cada informação ainda não vista cujo último aviso tem 1 h ou mais.
    enviar(texto, teclado) é a função do robô que manda no privado (async; teclado: o do Bot
    API) e devolve o id da mensagem, que fica guardado para tirar os lembretes depois, ou True.
    Um aviso que não sai fica para a próxima volta. Devolve quantos saíram.
    """
    enviados = 0
    for i in informacoes_vencidas(agora):
        try:
            mensagem = await enviar(montar_aviso_da_informacao(i), teclado_da_informacao(i))
            if mensagem:
                marcar_aviso_da_informacao(i["id"], agora, mensagem)
                enviados += 1
        except Exception as e:
            logger.warning(f"⚠️ [Informações do Claude] Lembrete de {i['codigo']} não saiu: {type(e).__name__}")
    return enviados


def lembretes_para_tirar(cod, tocada=None):
    """
    (fica, sair): a mensagem que fica no privado depois da informação vista (a tocada no Vi ✅
    ou, vista pela conversa, o aviso de onde ela veio) e os lembretes que saem.
    """
    mensagens = mensagens_da_informacao(cod)
    fica = tocada if tocada in mensagens else (mensagens[0] if mensagens else None)
    return fica, [m for m in mensagens if m != fica]


def texto_da_vista(cod):
    """O texto do lembrete que o Telegram não deixa mais apagar (mais de 48 h)."""
    return f"✅ Informação {cod} vista: este lembrete não vale mais."


def receber_informacao(texto_cifrado, agora=None):
    """No servidor: abre a informação cifrada, guarda, manda na hora com o Vi ✅ e devolve o código."""
    import avisar_rafael
    import registro_privado
    dados = abrir(texto_cifrado, registro_privado.chave())
    cod = nova_informacao(dados.get("informacao"), dados.get("link"), agora)
    i = next(i for i in informacoes_abertas() if i["codigo"] == cod)
    mensagem = avisar_rafael.mandar_texto_com_id(montar_aviso_da_informacao(i), html=True,
                                                 teclado=teclado_da_informacao(i))
    if mensagem:
        marcar_aviso_da_informacao(i["id"], agora, mensagem)
    return cod


def tirar_lembretes_pelo_servidor(cod):
    """Vista pela conversa: os lembretes saem do privado e o aviso de onde ela veio fica, sem o botão."""
    import avisar_rafael
    fica, sair = lembretes_para_tirar(cod)
    apagadas = 0
    for ident in sair:
        if avisar_rafael.apagar_mensagem(ident):
            apagadas += 1
        else:
            avisar_rafael.editar_texto(ident, texto_da_vista(cod))
    if fica is not None:
        avisar_rafael.tirar_botoes(fica)
    return apagadas, len(sair)


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
    mensagem = avisar_rafael.mandar_texto_com_id(montar_aviso(p), html=True)
    if mensagem:
        marcar_aviso(p["id"], agora, mensagem)
    return cod


def main(argumentos):
    if len(argumentos) != 2 or argumentos[0] not in ("cifrar", "nova", "respondida", "informacao", "vista"):
        print("uso: perguntas_rafael.py cifrar ARQUIVO.json | nova TEXTO_CIFRADO | respondida CODIGO | "
              "informacao TEXTO_CIFRADO | vista CODIGO")
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
        if acao == "informacao":
            print(f"✅ Informação {receber_informacao(valor)} guardada e enviada ao Rafael; lembrete de hora em hora "
                  "até ele dizer que viu.")
            return 0
        if acao == "vista":
            cod = valor.strip().upper()
            if not marcar_vista(cod):
                print("⚠️ Código não encontrado ou já visto.")
                return 1
            apagadas, total = tirar_lembretes_pelo_servidor(cod)
            print(f"✅ {cod} vista: os lembretes pararam; {apagadas} de {total} lembretes apagados do privado.")
            return 0
        if marcar_respondida(valor):
            import avisar_rafael
            cod = valor.strip().upper()
            apagadas, total = limpar_do_privado(cod, avisar_rafael.apagar_mensagem, avisar_rafael.editar_texto)
            avisar_rafael.mandar_texto(texto_da_confirmacao(cod, apagadas, total))
            print(f"✅ {cod} respondida: os lembretes pararam; {apagadas} de {total} mensagens apagadas do privado.")
            return 0
        print("⚠️ Código não encontrado ou já respondido.")
        return 1
    except Exception as e:
        # Só o tipo: a mensagem pode trazer o texto da pergunta ou a URL com o token.
        print(f"❌ Falhou: {type(e).__name__}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

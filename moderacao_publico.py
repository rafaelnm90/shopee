"""
A verificação semanal das mensagens dos membros no Grupo Público (pedido do Rafael:
DECISOES.md, Trabalho com o Claude). Toda segunda às 07:47 a conta principal, no
divulgacao_canal, lê as mensagens dos últimos 7 dias no grupo. O que pode ser contra
as regras gerais vai no privado do Rafael, com quem postou, o link da mensagem, a
regra e o motivo. Só avisa: nada é apagado nem respondido no grupo.

Regras gerais (escolha do Rafael, 23/10/2026), numeradas em REGRAS. Link que não é
da Shopee, convite de outro grupo ou canal e a mesma mensagem repetida saem sem IA;
ofensa, golpe e conteúdo adulto ou ilegal, a IA julga em lotes. Mensagens de bots,
dos admins do grupo e da própria conta ficam de fora.

No banco (chave moderacao_publico) e no log público, só números: quantas mensagens,
quantas conferidas, quantas suspeitas por regra. Nomes e textos só no privado.
"""
import asyncio
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import avisar_rafael
import db
import links_shopee
import registro_processos
from api_gemini import gerar_texto_gemini

logger = logging.getLogger(__name__)

REGRAS = {
    1: "ofensa, xingamento ou briga",
    2: "golpe ou fraude",
    3: "conteúdo adulto ou ilegal",
    4: "divulgação de outros grupos ou canais",
    5: "link que não é da Shopee",
    6: "mensagem repetida (flood)",
}
CHAVE = "moderacao_publico"
DIA_DA_SEMANA, HORA = "mon", (7, 47)
DIAS = 7
# Mensagens por pedido à IA, e quanto de cada uma ela lê.
LOTE, TAMANHO_DA_MENSAGEM = 40, 500
# A mesma mensagem da mesma pessoa a partir desta vez na semana é flood.
REPETICOES_DO_FLOOD = 3
MAXIMO_NO_AVISO = 30
TAMANHO_DO_AVISO = 3900

LINK = re.compile(r"(?:https?://|www\.)\S+|\b(?:t\.me|telegram\.me|wa\.me|chat\.whatsapp\.com)/\S+", re.IGNORECASE)
CONVITE = re.compile(r"\b(?:t\.me|telegram\.me|wa\.me|chat\.whatsapp\.com)/", re.IGNORECASE)

PROMPT = """Você é moderador de um grupo de afiliados da Shopee no Telegram. As regras do grupo:
1) sem ofensa, xingamento ou briga;
2) sem golpe ou fraude (promessa de dinheiro fácil, pedido de pagamento ou de dados, link suspeito);
3) sem conteúdo adulto ou ilegal.
Divulgar produtos da Shopee com link é o normal do grupo e não quebra regra.
Abaixo, as mensagens dos membros, cada uma com o número entre colchetes.
Responda só com um JSON: uma lista de {{"id": número, "regra": 1, 2 ou 3, "motivo": "até 80 caracteres"}}
com as mensagens que quebram alguma regra; [] se nenhuma quebra.

{mensagens}"""


def regra_sem_ia(texto):
    """A regra 4 ou 5 quebrada por um link da mensagem, ou None."""
    for link in LINK.findall(texto or ""):
        if CONVITE.search(link):
            return 4, "convite de outro grupo ou canal"
        if not links_shopee.PADRAO_LINK_QUALQUER.match(link):
            return 5, "link que não é da Shopee"
    return None


def _normal(texto):
    return " ".join((texto or "").split()).casefold()


def suspeitas_sem_ia(mensagens):
    """{id: (regra, motivo)} dos links fora da regra e das mensagens repetidas (flood)."""
    suspeitas = {}
    vezes = defaultdict(list)
    for m in mensagens:
        quebra = regra_sem_ia(m["texto"])
        if quebra:
            suspeitas[m["id"]] = quebra
        vezes[(m["autor_id"], _normal(m["texto"]))].append(m["id"])
    for ids in vezes.values():
        for id_msg in ids[REPETICOES_DO_FLOOD - 1:]:
            suspeitas.setdefault(id_msg, (6, f"a mesma mensagem {len(ids)} vezes na semana"))
    return suspeitas


def montar_prompt(lote):
    return PROMPT.format(mensagens="\n".join(f"[{i}] {m['texto'][:TAMANHO_DA_MENSAGEM]}"
                                             for i, m in enumerate(lote)))


def ler_resposta(texto, lote):
    """{id da mensagem: (regra, motivo)} da resposta da IA; regra fora de 1 a 3 é ignorada."""
    achado = re.search(r"\[.*\]", texto or "", re.DOTALL)
    if not achado:
        return None
    try:
        itens = json.loads(achado.group(0))
    except ValueError:
        return None
    suspeitas = {}
    for item in itens if isinstance(itens, list) else []:
        try:
            posicao, regra = int(item.get("id")), int(item.get("regra"))
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= posicao < len(lote) and regra in (1, 2, 3):
            suspeitas[lote[posicao]["id"]] = (regra, str(item.get("motivo") or "")[:80])
    return suspeitas


async def suspeitas_da_ia(mensagens):
    """({id: (regra, motivo)}, quantas mensagens a IA não julgou)."""
    suspeitas, sem_julgar = {}, 0
    for inicio in range(0, len(mensagens), LOTE):
        lote = mensagens[inicio:inicio + LOTE]
        resposta = ler_resposta(await gerar_texto_gemini(montar_prompt(lote)), lote)
        if resposta is None:
            sem_julgar += len(lote)
            continue
        suspeitas.update(resposta)
    return suspeitas, sem_julgar


def link_da_mensagem(grupo, id_msg, usuario=None):
    if usuario:
        return f"https://t.me/{usuario}/{id_msg}"
    return f"https://t.me/c/{str(grupo).replace('-100', '', 1).lstrip('-')}/{id_msg}"


def montar_aviso(grupo, usuario, mensagens, suspeitas, desde, ate):
    """O texto do privado: as suspeitas, uma por item, em pedaços que cabem no Telegram."""
    por_id = {m["id"]: m for m in mensagens}
    periodo = f"{desde.strftime('%d/%m')} a {ate.strftime('%d/%m')}"
    if not suspeitas:
        return [f"🛡️ Grupo Público, verificação da semana ({periodo}): conferi {len(mensagens)} mensagem(ns) "
                "de membros e nenhuma parece contra as regras."]
    linhas = [f"🛡️ Grupo Público, verificação da semana ({periodo}): conferi {len(mensagens)} mensagem(ns) de "
              f"membros e {len(suspeitas)} pode(m) ser contra as regras. Só aviso: nada foi apagado.\n"]
    for n, (id_msg, (regra, motivo)) in enumerate(sorted(suspeitas.items()), 1):
        if n > MAXIMO_NO_AVISO:
            linhas.append(f"... e mais {len(suspeitas) - MAXIMO_NO_AVISO}.")
            break
        m = por_id.get(id_msg, {})
        linhas.append(f"{n}. {m.get('autor', '?')}: {REGRAS[regra]}" + (f" ({motivo})" if motivo else "")
                      + f"\n{link_da_mensagem(grupo, id_msg, usuario)}")
    pedacos, atual = [], ""
    for linha in linhas:
        if len(atual) + len(linha) + 1 > TAMANHO_DO_AVISO:
            pedacos.append(atual)
            atual = ""
        atual += linha + "\n"
    return pedacos + [atual]


def _nome(pessoa):
    usuario = getattr(pessoa, "username", None)
    nome = " ".join(p for p in (getattr(pessoa, "first_name", None), getattr(pessoa, "last_name", None)) if p)
    return f"{nome or 'sem nome'}" + (f" (@{usuario})" if usuario else "")


async def ler_semana(client, entidade, desde):
    """As mensagens de membros (não bots, não admins, não a própria conta) desde o momento."""
    from telethon.tl.types import ChannelParticipantsAdmins
    admins = set()
    try:
        async for admin in client.iter_participants(entidade, filter=ChannelParticipantsAdmins):
            admins.add(admin.id)
    except Exception as e:
        logger.warning(f"⚠️ [Moderação Público] Não li os admins: {type(e).__name__}")
    mensagens, so_midia, total = [], 0, 0
    async for msg in client.iter_messages(entidade):
        if msg.date < desde:
            break
        total += 1
        pessoa = msg.sender
        # Fora: avisos do Telegram (entrou, saiu), o que sai em nome de um canal ou do
        # próprio grupo (id negativo: o canal ligado, admin anônimo), bots, admins e a conta.
        if getattr(msg, "action", None) or not msg.sender_id or msg.sender_id < 0 or msg.out:
            continue
        if msg.sender_id in admins or getattr(pessoa, "bot", False):
            continue
        texto = msg.message or ""
        if not texto.strip():
            so_midia += 1
            continue
        mensagens.append({"id": msg.id, "autor_id": msg.sender_id, "autor": _nome(pessoa), "texto": texto})
    return mensagens, so_midia, total


@registro_processos.anotar("divulgacao", "verificação semanal do Grupo Público")
async def conferir_semana(client, agora=None):
    """Lê a semana no Grupo Público, avisa o Rafael no privado e guarda só os números."""
    grupo = (db.ler_config("submissao_config", {}) or {}).get("grupo_id")
    if not grupo or grupo == "Não definido":
        logger.info("🛡️ [Moderação Público] Grupo Público não configurado: nada a conferir.")
        return
    agora = agora or datetime.now(timezone.utc)
    desde = agora - timedelta(days=DIAS)
    entidade = await client.get_entity(int(grupo) if str(grupo).lstrip("-").isdigit() else grupo)
    mensagens, so_midia, total = await ler_semana(client, entidade, desde)
    suspeitas = suspeitas_sem_ia(mensagens)
    sem_ia = [m for m in mensagens if m["id"] not in suspeitas]
    da_ia, sem_julgar = await suspeitas_da_ia(sem_ia)
    suspeitas.update(da_ia)
    por_regra = Counter(REGRAS[regra] for regra, _motivo in suspeitas.values())
    db.salvar_config(CHAVE, {"quando": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "mensagens": total,
                             "de_membros": len(mensagens), "so_midia": so_midia, "suspeitas": len(suspeitas),
                             "nao_julgadas": sem_julgar, "por_regra": dict(por_regra)})
    # O aviso vai pelo Bot API, que espera a resposta: numa thread, para a conta não parar.
    # Se o Telegram recusar, o erro sobe e o registro anota a verificação como falha.
    for pedaco in montar_aviso(grupo, getattr(entidade, "username", None), mensagens, suspeitas, desde, agora):
        await asyncio.to_thread(avisar_rafael.mandar_texto, pedaco)
    logger.info(f"🛡️ [Moderação Público] {len(mensagens)} mensagem(ns) de membros conferida(s), "
                f"{len(suspeitas)} suspeita(s), {sem_julgar} sem julgamento da IA.")

"""
Faxina do Acervo Viral: tira do canal os vídeos que já não servem. Roda no
divulgacao_canal (loop_faxina), com a conta principal do Rafael (sessao_divulgacao),
dona do canal: o bot só apaga mensagem com até 48 h, e a conta de usuário
administradora não tem esse limite. É o mesmo arranjo da faxina do Baixador.

Regras do Rafael (DECISOES.md, Canal Viral):
- vídeo com mais de IDADE_MAXIMA sai;
- vídeo cujo produto saiu da Shopee sai antes: a API de afiliado não acha o produto em
  duas conferências com pelo menos INTERVALO_CONFERENCIA entre elas, para uma falha
  passageira da Shopee não apagar nada;
- os vídeos que já estavam no canal entram na mesma regra, aos poucos
  (LIMITE_APAGAR_POR_RODADA a cada rodada).

O que se sabe de cada vídeo (o produto e quando a API deixou de achá-lo) fica na
tabela faxina_viral; o resumo da última rodada, na chave faxina_viral de
configuracoes, que o /status, o monitor de saúde e o fato do acervo do bot_mestre leem.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import api_shopee
import db
import registro_processos
import links_shopee

logger = logging.getLogger("Faxina_Viral")

# Acervo Viral Shopee, o destino do Espião (README). Fixo no código, como os outros
# canais: um destino trocado no painel nunca vira alvo da faxina por engano.
ACERVO_VIRAL_ID = -1003932482573

IDADE_MAXIMA = timedelta(days=7)
INTERVALO_CONFERENCIA = timedelta(hours=24)
INTERVALO_RODADAS_S = 6 * 3600
LIMITE_APAGAR_POR_RODADA = 100        # 4 rodadas por dia: os antigos saem em algumas centenas por dia
LIMITE_CONFERENCIAS_POR_RODADA = 150
PAUSA_ENTRE_CONFERENCIAS_S = 0.5
# Se a API deixa de achar a maioria dos produtos de uma vez, o problema é dela e não dos
# produtos: nessa rodada ninguém sai pelo produto.
MINIMO_PARA_DESCONFIAR = 10
FRACAO_SUSPEITA = 0.5

CHAVE_RESUMO = "faxina_viral"


def inicializar_tabela():
    with db.conexao() as conexao:
        conexao.execute("CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)")
        conexao.execute(
            "CREATE TABLE IF NOT EXISTS faxina_viral ("
            "msg_id INTEGER PRIMARY KEY, "
            "produto TEXT, "            # "loja/item"; vazio quando o link não leva a um produto
            "conferido_em TEXT, "       # última resposta da API (ISO, UTC)
            "falta_desde TEXT)")        # primeira vez que a API não achou; vazio se achou


def _ler_registros():
    with db.conexao(linhas_por_nome=True) as conexao:
        return {linha["msg_id"]: dict(linha) for linha in conexao.execute("SELECT * FROM faxina_viral")}


def _gravar(msg_id, produto, conferido_em=None, falta_desde=None):
    with db.conexao() as conexao:
        conexao.execute(
            "INSERT OR REPLACE INTO faxina_viral (msg_id, produto, conferido_em, falta_desde) VALUES (?, ?, ?, ?)",
            (msg_id, produto, conferido_em.isoformat() if conferido_em else None,
             falta_desde.isoformat() if falta_desde else None))


def _esquecer(ids):
    if not ids:
        return
    with db.conexao() as conexao:
        conexao.executemany("DELETE FROM faxina_viral WHERE msg_id = ?", [(i,) for i in ids])


def _data(texto):
    try:
        return datetime.fromisoformat(texto) if texto else None
    except ValueError:
        return None


async def produto_do_video(mensagem):
    """
    "loja/item" do produto do link da legenda, seguindo o link curto até o produto; ""
    quando o link não leva a um produto (vídeo da Shopee Vídeo, busca); None sem link
    ou quando o link não abriu agora (tenta de novo na próxima rodada).
    """
    link = links_shopee.extrair_link_shopee(mensagem)
    if not link:
        return None
    caminho = await api_shopee.seguir_link(link)
    if len(caminho) < 2:
        return None  # o link curto sempre redireciona: parado no primeiro é falha de rede
    for endereco in caminho:
        produto = api_shopee.produto_do_link(endereco)
        if produto:
            return "/".join(produto.rstrip("/").split("/")[-2:])
    return ""


def _resumo_do_dia(agora_local):
    """O resumo gravado, com os contadores zerados quando o dia virou."""
    resumo = db.ler_config(CHAVE_RESUMO, {}) or {}
    hoje = agora_local.strftime("%Y-%m-%d")
    if resumo.get("dia") != hoje:
        resumo.update({"dia": hoje, "apagados_idade_dia": 0, "apagados_produto_dia": 0})
    return resumo


async def _nome_da_conta(client):
    try:
        eu = await client.get_me()
        nome = " ".join(p for p in (getattr(eu, "first_name", None), getattr(eu, "last_name", None)) if p)
        usuario = getattr(eu, "username", None)
        return f"{nome} (@{usuario})" if usuario else (nome or "conta principal")
    except Exception:
        return "conta principal"


@registro_processos.anotar("divulgacao", "faxina do Acervo Viral")
async def rodada(client, agora=None):
    """Uma passada pelo canal: decide, apaga e grava o resumo. Devolve o resumo."""
    agora = agora or datetime.now(timezone.utc)
    inicializar_tabela()
    resumo = _resumo_do_dia(agora.astimezone())
    resumo["quando"] = agora.astimezone().strftime("%d/%m %H:%M")
    resumo["conta"] = await _nome_da_conta(client)

    try:
        canal = await client.get_entity(ACERVO_VIRAL_ID)
        permissoes = await client.get_permissions(canal, "me")
        pode_apagar = bool(getattr(permissoes, "is_admin", False) and getattr(permissoes, "delete_messages", False))
    except Exception as e:
        logger.warning(f"⚠️ [Faxina Viral] A conta não acessa o Acervo Viral: {type(e).__name__}.")
        resumo["situacao"] = "sem_acesso"
        db.salvar_config(CHAVE_RESUMO, resumo)
        return resumo
    if not pode_apagar:
        logger.warning("⚠️ [Faxina Viral] A conta não é administradora do Acervo Viral com permissão de apagar.")
        resumo["situacao"] = "sem_permissao"
        db.salvar_config(CHAVE_RESUMO, resumo)
        return resumo

    registros = _ler_registros()
    vistos, por_idade, faltando = set(), [], []
    antigos = conferencias = nao_achou = 0

    async for mensagem in client.iter_messages(canal):
        if not getattr(mensagem, "video", None):
            continue
        vistos.add(mensagem.id)
        idade = agora - mensagem.date
        if idade > IDADE_MAXIMA:
            antigos += 1
            if len(por_idade) < LIMITE_APAGAR_POR_RODADA:
                por_idade.append(mensagem.id)
            continue
        # Recém-postado: o link acabou de ser gerado para um produto que existe.
        if idade < INTERVALO_CONFERENCIA or conferencias >= LIMITE_CONFERENCIAS_POR_RODADA:
            continue
        registro = registros.get(mensagem.id) or {}
        conferido = _data(registro.get("conferido_em"))
        if conferido and agora - conferido < INTERVALO_CONFERENCIA:
            continue

        produto = registro.get("produto")
        if produto is None:
            produto = await produto_do_video(mensagem)
            if produto is None:
                continue
        if not produto:
            # Sem produto para perguntar à API: só a idade tira este vídeo.
            _gravar(mensagem.id, "", conferido_em=agora)
            continue

        conferencias += 1
        a_venda = await api_shopee.produto_a_venda(*produto.split("/"))
        await asyncio.sleep(PAUSA_ENTRE_CONFERENCIAS_S)
        if a_venda is None:
            # Sem resposta: fica como estava e tenta de novo na próxima rodada.
            _gravar(mensagem.id, produto, conferido_em=conferido, falta_desde=_data(registro.get("falta_desde")))
        elif a_venda:
            _gravar(mensagem.id, produto, conferido_em=agora)
        else:
            nao_achou += 1
            falta_desde = _data(registro.get("falta_desde")) or agora
            _gravar(mensagem.id, produto, conferido_em=agora, falta_desde=falta_desde)
            if agora - falta_desde >= INTERVALO_CONFERENCIA:
                faltando.append(mensagem.id)

    api_suspeita = conferencias >= MINIMO_PARA_DESCONFIAR and nao_achou / conferencias > FRACAO_SUSPEITA
    if api_suspeita:
        logger.warning(f"⚠️ [Faxina Viral] A API não achou {nao_achou} de {conferencias} produtos. "
                       "Nesta rodada nenhum vídeo sai pelo produto.")
        faltando = []
    faltando = faltando[:max(0, LIMITE_APAGAR_POR_RODADA - len(por_idade))]

    apagados_idade = apagados_produto = 0
    if por_idade or faltando:
        try:
            await client.delete_messages(canal, por_idade + faltando)
            apagados_idade, apagados_produto = len(por_idade), len(faltando)
            _esquecer(por_idade + faltando)
        except Exception as e:
            logger.error(f"❌ [Faxina Viral] Não consegui apagar os vídeos: {type(e).__name__}.")
    _esquecer([msg_id for msg_id in registros if msg_id not in vistos])

    resumo.update({
        "situacao": "ok",
        "api_suspeita": api_suspeita,
        "videos_no_canal": len(vistos) - apagados_idade - apagados_produto,
        "antigos_pendentes": max(0, antigos - apagados_idade),
        "apagados_idade_dia": resumo.get("apagados_idade_dia", 0) + apagados_idade,
        "apagados_produto_dia": resumo.get("apagados_produto_dia", 0) + apagados_produto,
    })
    db.salvar_config(CHAVE_RESUMO, resumo)
    logger.info(f"🧹 [Faxina Viral] {apagados_idade} vídeo(s) com mais de {IDADE_MAXIMA.days} dias e "
                f"{apagados_produto} com produto fora da Shopee apagados; {resumo['videos_no_canal']} no canal.")
    return resumo


async def loop_faxina(client):
    """A cada INTERVALO_RODADAS_S, uma rodada. Um erro numa rodada não para as próximas."""
    await asyncio.sleep(60)  # deixa o robô terminar de subir
    while True:
        try:
            await rodada(client)
        except Exception as e:
            logger.error(f"❌ [Faxina Viral] Rodada falhou: {type(e).__name__}: {e}")
        await asyncio.sleep(INTERVALO_RODADAS_S)


def videos_no_canal():
    """Quantos vídeos o Acervo Viral tem de fato, pela última rodada; None sem faxina rodando."""
    resumo = db.ler_config(CHAVE_RESUMO, {}) or {}
    return resumo.get("videos_no_canal") if resumo.get("situacao") == "ok" else None


def linha_status():
    """A linha do /status do bot_mestre."""
    resumo = db.ler_config(CHAVE_RESUMO, {}) or {}
    situacao = resumo.get("situacao")
    if not situacao:
        return "🧹 Faxina do Acervo Viral: ainda não rodou"
    conta = resumo.get("conta") or "conta principal"
    if situacao == "sem_acesso":
        return f"🧹 Faxina do Acervo Viral: ❌ a {conta} não está no canal (precisa ser administradora)"
    if situacao == "sem_permissao":
        return f"🧹 Faxina do Acervo Viral: ❌ a {conta} não é administradora com permissão de apagar mensagens"
    texto = (f"🧹 Faxina do Acervo Viral ({resumo.get('quando', '?')}): {resumo.get('videos_no_canal', 0)} vídeos "
             f"no canal · hoje saíram {resumo.get('apagados_idade_dia', 0)} por idade e "
             f"{resumo.get('apagados_produto_dia', 0)} por produto fora da Shopee")
    if resumo.get("antigos_pendentes"):
        texto += f" · {resumo['antigos_pendentes']} antigos na fila"
    if resumo.get("api_suspeita"):
        texto += " · ⚠️ API da Shopee estranha na última rodada"
    return texto


def problema_de_permissao():
    """Texto do alerta do monitor de saúde quando a conta não consegue apagar; None se está tudo certo."""
    resumo = db.ler_config(CHAVE_RESUMO, {}) or {}
    if resumo.get("situacao") not in ("sem_acesso", "sem_permissao"):
        return None
    conta = resumo.get("conta") or "conta principal"
    return (f"🧹 <b>Faxina do Acervo Viral parada</b>\nA {conta} precisa ser administradora do Acervo "
            "Viral com a permissão \"Apagar mensagens\". Sem isso, nenhum vídeo antigo sai do canal.")

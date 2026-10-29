"""
Painel da Shopee Vídeo: roteador do bot_mestre (Outros Canais → Shopee Vídeo 🎬).

Dois robôs, cada um com o seu botão de pausar e retomar:
- o modo assistente prepara cada postagem (vídeo, título pela IA, produtos e
  comentário) e manda no privado do Rafael, que posta pelo próprio celular
  (assistente_shopee_video.py);
- o robô automático prepara rascunhos sozinho no celular guardado e posta os que o
  Rafael aprova aqui, um por um, em "Rascunhos do Robô 📝" (robo_shopee_video.py).
Os dois puxam da mesma Fonte dos Vídeos, e o vídeo que um usou o outro não pega. Um
cobre o outro: com o robô ativo, o assistente fica em espera; com o robô pausado (pelo
Rafael ou sozinho, quando perde o celular), o assistente manda as postagens no privado.
Retomar Postagem ▶️ acha o celular sozinho antes de retomar (celular_robo).

Este painel guarda o que o Rafael controla, na chave "shopee_video" das configurações:
- assistente: pausa, quantos vídeos por dia (faixa sorteada a cada dia) e a janela de
  horário dos envios;
- robô automático (chaves robo_*): pausa, quantos rascunhos por dia (faixa) e o Horário
  do Robô, em que ele toca no celular e posta;
- de onde vêm os vídeos (Autorais, Viral, Canal Afiliados ou Grupo Público).
Também liga os dois no agendador: o assistente vê a cada 5 min se chegou a hora, e o
robô roda uma rodada a cada 15 min, num processo à parte. "Enviar 1 Agora 📤" manda uma
postagem do assistente na hora, mesmo pausado; "Testar Caminho 🧭" roda o treino do robô
na hora. O botão "Celular do Robô 📱" liga o servidor ao celular guardado do Rafael
(celular_robo.py): o código de pareamento chega só aqui, no privado. Lá, o "Passo a
Passo 📖" ensina a deixar o celular pronto de novo depois de um reset, e o "Ver Tela do
Celular 🖥️" manda no privado um link de 30 min para o Rafael ver e tocar na tela do
celular de longe (tela_android.py).
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import asyncio
import json
import logging
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from html import escape as html_escape

from aiogram import Router, Bot, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import FSInputFile, KeyboardButton
from teclados import (montar_teclado, teclado_com_cancelar, teclado_cancelar,
                      teclado_aprovar_cancelar, teclado_janela_dia_todo)

import android_virtual as av
import apelacoes_shopee_video as apelacoes
import assistente_shopee_video as assistente
import celular_robo
import db
import edicao_video
import exemplos
import registro_processos
import robo_shopee_video as robo
from fuso import fuso_horario
from motor_filas import sortear_teto_do_dia

logger = logging.getLogger("ShopeeVideo")

router = Router()
bot_instance = None
scheduler_instance = None
ADMIN_ID = None

CHAVE_CONFIG = "shopee_video"
# Os dois começam pausados: só trabalham quando o Rafael retomar no painel.
PADRAO = {"pausado": True, "limite_min": 5, "limite_max": 10, "inicio": 13, "fim": 22,
          "fonte": assistente.FONTE_PADRAO, "edicao_ligada": False, **robo.PADRAO}
MAXIMO_POR_DIA = 50
ROBO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "robo_shopee_video.py")
PRIMEIRA_VOLTA_DO_ROBO = timedelta(minutes=2)


def configurar_dependencias(bot: Bot, scheduler, admin_id):
    global bot_instance, scheduler_instance, ADMIN_ID
    bot_instance, scheduler_instance, ADMIN_ID = bot, scheduler, admin_id
    scheduler.add_job(verificar_envio, "interval", minutes=5, id="shopee_video_assistente",
                      replace_existing=True, max_instances=1, coalesce=True)
    # Depois de um reinício (deploy), a primeira volta sai em PRIMEIRA_VOLTA_DO_ROBO: esperar
    # os 15 min inteiros atrasava o aprovado que já estava na hora (23/10: 2 deploys seguidos
    # empurraram o post das 23:03 para depois das 23:26).
    scheduler.add_job(verificar_robo, "interval", minutes=15, id="shopee_video_robo",
                      replace_existing=True, max_instances=1, coalesce=True,
                      next_run_time=datetime.now(fuso_horario) + PRIMEIRA_VOLTA_DO_ROBO)
    scheduler.add_job(mandar_resumo_do_robo, "cron", hour=HORA_DO_RESUMO, minute=0, id="shopee_video_resumo",
                      replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(lembrar_apelacoes, "interval", minutes=5, id="shopee_video_apelacoes",
                      replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(avisar_exemplo_interrompido, "date", id="shopee_video_exemplo_interrompido",
                      replace_existing=True, run_date=datetime.now(fuso_horario) + timedelta(seconds=30))


# Um envio de cada vez: o agendador e o botão Enviar 1 Agora pegariam o mesmo vídeo.
_envio = asyncio.Lock()


async def enviar_um(fonte):
    """Prepara e manda uma postagem (vídeo da fonte) no privado. Devolve o que aconteceu, numa frase."""
    async with _envio:
        try:
            return await assistente.preparar_e_enviar(bot_instance, ADMIN_ID, fonte=fonte)
        except Exception as e:
            logger.error(f"❌ [Shopee Vídeo] Erro ao preparar a postagem: {type(e).__name__}: {e}")
            return f"deu erro ao preparar ({type(e).__name__})"


def assistente_em_espera(config):
    """
    Com o robô automático ativo, o assistente não manda: um cobre o outro, nunca os dois
    juntos. Com a conta de Shopee Vídeo suspensa pela Shopee, espera também. Os horários
    que passam em espera são pulados, como pausado.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    return not config["robo_pausado"] or robo.suspensa(config)


async def verificar_envio():
    """Volta do agendador: manda um vídeo se um horário do plano de hoje já passou."""
    config = ler_config()
    efetivo = {**config, "pausado": config["pausado"] or assistente_em_espera(config)}
    if _envio.locked() or not assistente.decidir_envio(efetivo):
        return
    logger.info(f"🎬 [Shopee Vídeo] {await enviar_um(config['fonte'])}.")


# Uma rodada do robô de cada vez: o agendador e o Testar Caminho tocariam juntos no celular.
_rodada = asyncio.Lock()
# Cada rodada roda numa unidade própria do systemd (systemd-run), fora do bot_mestre: o
# deploy que reinicia o bot não mata mais a rodada no meio do celular (pedido do Rafael,
# P13: DECISOES.md, Shopee Vídeo). O log dela sai no journal com este nome.
UNIDADE_DA_RODADA = "robo-shopee-video"
NOME_NO_LOG = "robo_shopee_video"


def robo_ocupado():
    """Uma rodada (deste bot ou de antes de um reinício) ou o explorar está no celular agora?"""
    return _rodada.locked() or celular_robo.ocupado()


async def _comando(*partes, espera=30):
    """O código de saída de um comando curto do sistema; None se não rodou."""
    try:
        processo = await asyncio.create_subprocess_exec(*partes, stdout=asyncio.subprocess.DEVNULL,
                                                        stderr=asyncio.subprocess.DEVNULL)
        return await asyncio.wait_for(processo.wait(), espera)
    except (OSError, asyncio.TimeoutError):
        return None


async def _rodar_fora_do_bot(argumentos):
    """
    A rodada numa unidade própria do systemd, e espera ela acabar. False quando o
    servidor não deixa (sem o sudo do systemd-run): a rodada vai como processo do bot.
    """
    unidade = f"{UNIDADE_DA_RODADA}-{datetime.now(fuso_horario):%Y%m%d%H%M%S}"
    criada = await _comando(
        "sudo", "-n", "systemd-run", f"--unit={unidade}", "--collect", "--quiet",
        f"--uid={os.getuid()}", f"--working-directory={os.path.dirname(ROBO)}",
        f"--property=RuntimeMaxSec={robo.MAXIMO_DA_RODADA + 60}", f"--property=SyslogIdentifier={NOME_NO_LOG}",
        "--setenv=PYTHONUNBUFFERED=1", sys.executable, ROBO, *argumentos)
    if criada != 0:
        registro_processos.registrar("shopee_video", "rodada fora do bot", "sem systemd-run",
                                     "a rodada foi como processo do bot", ok=False)
        return False
    registro_processos.registrar("shopee_video", "rodada fora do bot", "unidade própria", ok=True)
    for _ in range((robo.MAXIMO_DA_RODADA + 120) // 10):
        await asyncio.sleep(10)
        if await _comando("systemctl", "is-active", "--quiet", unidade) != 0:
            return True
    return True


async def rodar_robo(*argumentos):
    """
    Uma rodada do robô automático num processo à parte: ele passa minutos tocando no
    celular, e a IA dele não pode dividir a conexão com a do bot. O resultado vai para
    o log; o que importa ao Rafael o próprio robô manda no privado.
    """
    async with _rodada:
        if await _rodar_fora_do_bot(argumentos):
            return
        processo = await asyncio.create_subprocess_exec(sys.executable, ROBO, *argumentos,
                                                        cwd=os.path.dirname(ROBO))
        try:
            await asyncio.wait_for(processo.wait(), robo.MAXIMO_DA_RODADA)
        except asyncio.TimeoutError:
            processo.kill()
            logger.warning("⚠️ [Robô Shopee Vídeo] A rodada passou de 30 min e foi interrompida.")


async def verificar_robo():
    """
    Volta do agendador: uma rodada do robô, se ele está ativo e dentro do Horário do Robô
    (também com a conta suspensa: o robô sabe o que pode fazer nela). Acabada a suspensão
    da conta pela Shopee, avisa no privado que os dois voltaram.
    """
    aviso = robo.fim_da_suspensao()
    if aviso:
        logger.info("✅ [Robô Shopee Vídeo] A suspensão da conta acabou.")
        try:
            await bot_instance.send_message(ADMIN_ID, aviso)
        except Exception as e:
            logger.warning(f"⚠️ [Robô Shopee Vídeo] Aviso do fim da suspensão não saiu: {type(e).__name__}")
    config = ler_config()
    if robo_ocupado():
        return
    if config["robo_pausado"]:
        # Pausado pelo Rafael, os horários de rascunho que passam são pulados, como no
        # assistente. Pausado sozinho, sem o celular, eles ficam: na volta contam como um só.
        # Escolha do Rafael (P16): DECISOES.md, Shopee Vídeo.
        if config.get("robo_pausa_motivo") != robo.MOTIVO_DA_DESCONEXAO:
            robo.consumir_horarios(config, pular=True)
        return
    if robo.suspensa(config):
        # Na suspensão os horários de rascunho também são pulados, mas a rodada segue: o robô
        # só não prepara, não posta e não treina; a limpeza dos favoritos, apagar o recusado,
        # as respostas, o feed e a Saúde do Vídeo continuam. Pedido do Rafael: DECISOES.md.
        robo.consumir_horarios(config, pular=True)
    if robo.no_horario(config):
        await rodar_robo("--rodada")


# O resumo do dia do robô automático no privado (escolha do Rafael, 23/10/2026): o que ele
# fez nas últimas 24 h e onde parou. Sem nenhuma tentativa, não manda nada.
HORA_DO_RESUMO = 22


@registro_processos.anotar("shopee_video", "resumo das 22h")
async def mandar_resumo_do_robo():
    texto = robo.texto_resumo()
    if not texto:
        return
    try:
        await bot_instance.send_message(ADMIN_ID, texto, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"⚠️ [Robô Shopee Vídeo] Resumo do dia não saiu: {type(e).__name__}")


def _admin(message):
    return message.from_user is not None and message.from_user.id == ADMIN_ID


# --- Apelação das punições (apelacoes_shopee_video.py) ---

BOTAO_SAUDE = "Saúde da Shopee Vídeo 🩺"
BOTAO_GERAR_APELACAO = "Gerar Apelação ⚖️"


async def lembrar_apelacoes():
    """
    Volta do agendador: o aviso de cada punição nova sem recurso e o lembrete de hora em
    hora, a qualquer hora, até o Rafael tocar em Já recorri ou Não vou recorrer.
    Pedido do Rafael: DECISOES.md, Shopee Vídeo.
    """
    async def enviar(texto, p):
        mensagem = await bot_instance.send_message(ADMIN_ID, texto, parse_mode="HTML",
                                                   reply_markup=apelacoes.botoes(p), disable_web_page_preview=True)
        # O id volta para apagar este lembrete quando o Rafael tocar num dos botões.
        return mensagem.message_id
    enviados = await apelacoes.lembrar(enviar)
    if enviados:
        logger.info(f"⚖️ [Apelação Shopee Vídeo] {enviados} aviso(s) de punição no privado.")
        registro_processos.registrar("shopee_video", "aviso de punição para recorrer", "enviado", str(enviados),
                                     ok=True)


LEMBRETE_RESOLVIDO = "✅ Punição resolvida: este lembrete não vale mais."


@router.callback_query(F.data.startswith((apelacoes.CALLBACK_RECORRI, apelacoes.CALLBACK_NAO_VAI)))
async def decisao_da_apelacao(callback: types.CallbackQuery):
    """Já recorri ou Não vou recorrer: o lembrete daquela punição para."""
    if callback.from_user is None or callback.from_user.id != ADMIN_ID:
        return
    recorri = callback.data.startswith(apelacoes.CALLBACK_RECORRI)
    ident = callback.data.split(":", 1)[1]
    mudou = ident.isdigit() and apelacoes.marcar(int(ident), apelacoes.RECORRIDA if recorri else apelacoes.NAO_VAI)
    resposta = ("✅ Anotado: você recorreu. Parei de lembrar desta punição, e o robô olha a Saúde do Vídeo de "
                "hora em hora (no Horário do Robô) até sair o resultado do recurso; quando sair, eu aviso aqui."
                if recorri
                else "🚫 Anotado: você não vai recorrer. Parei de lembrar desta punição.")
    await callback.answer(resposta if mudou else "Esta punição já estava resolvida.")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if ident.isdigit():
        await limpar_lembretes(int(ident), getattr(callback.message, "message_id", None))
    if mudou:
        await callback.message.answer(resposta)


async def limpar_lembretes(ident, tocada):
    """
    Tocou num dos botões: os outros avisos e lembretes da punição saem do privado, e fica
    só a mensagem tocada, sem os botões, e a confirmação. O Telegram só deixa apagar até
    48 h depois do envio: o mais velho fica com o texto trocado (e sem os botões).
    Escolha do Rafael (24/10, P7): DECISOES.md, Shopee Vídeo.
    """
    for mensagem in apelacoes.mensagens_de(ident):
        if mensagem == tocada:
            continue
        try:
            await bot_instance.delete_message(ADMIN_ID, mensagem)
        except Exception:
            try:
                await bot_instance.edit_message_text(text=LEMBRETE_RESOLVIDO, chat_id=ADMIN_ID, message_id=mensagem)
            except Exception:
                pass
    apelacoes.guardar_mensagens(ident, [tocada] if tocada else [])


def teclado_saude():
    return montar_teclado([[KeyboardButton(text=BOTAO_GERAR_APELACAO)],
                           [KeyboardButton(text="Relatório Geral 📊"), KeyboardButton(text="Voltar ao Início 🔙")]])


@router.message(F.text == BOTAO_SAUDE, StateFilter("*"))
async def saude_handler(message: types.Message, state: FSMContext):
    """
    Relatório Geral 📊 → Saúde da Shopee Vídeo 🩺 (ideia do Rafael, 23/10/2026): a
    suspensão, os pontos de penalidade e as punições, como o robô leu no Motorola.
    """
    if not _admin(message): return
    await state.clear()
    await message.answer(apelacoes.texto_saude(ler_config(), robo.ler_estado()), parse_mode="HTML",
                         reply_markup=teclado_saude())


@router.message(F.text == BOTAO_GERAR_APELACAO, StateFilter("*"))
async def gerar_apelacao_handler(message: types.Message, state: FSMContext):
    """O robô lê a Saúde do Vídeo na hora, mesmo pausado, e manda o texto de cada punição nova sem recurso."""
    if not _admin(message): return
    if robo_ocupado():
        await message.answer("⏳ O robô está no meio de uma rodada no celular. Tente de novo em alguns minutos.")
        return
    logger.info("⚖️ Shopee Vídeo: Gerar Apelação.")
    await message.answer("⚖️ O robô vai olhar a Saúde do Vídeo no Motorola agora. Em uns 3 a 5 min chega aqui o "
                         "resumo e, para cada punição nova sem recurso, o texto pronto para copiar.")
    asyncio.create_task(rodar_robo("--saude"))


class ShopeeVideoFluxo(StatesGroup):
    menu = State()
    menu_robo = State()
    menu_assistente = State()
    aguardando_tipo_faixa = State()
    aguardando_faixa = State()
    aguardando_confirmacao_faixa = State()
    aguardando_janela = State()
    aguardando_confirmacao_janela = State()
    aguardando_confirmacao_pausa = State()
    aguardando_fonte = State()
    aguardando_tipo_faixa_robo = State()
    aguardando_faixa_robo = State()
    aguardando_confirmacao_faixa_robo = State()
    aguardando_janela_robo = State()
    aguardando_confirmacao_janela_robo = State()
    aguardando_janela_interacoes = State()
    aguardando_confirmacao_janela_interacoes = State()
    aguardando_confirmacao_pausa_robo = State()
    rascunho = State()
    aguardando_confirmacao_recusa = State()
    celular = State()
    aguardando_escolha_celular = State()
    aguardando_pareamento = State()
    aguardando_porta = State()


# --- Configuração ---

BOTAO_FAIXA = "Faixa 🎲"
BOTAO_FIXO = "Fixo 📌"


def ler_config():
    """A configuração do robô, com os valores padrão no que faltar."""
    return {**PADRAO, **db.ler_config(CHAVE_CONFIG, {})}


def alterar_config(**mudancas):
    """Grava só as chaves mudadas, sem apagar o que o motor tiver gravado na mesma chave."""
    def alterar(dados):
        dados.update(mudancas)
    db.atualizar_config(CHAVE_CONFIG, alterar)


def interpretar_faixa(texto):
    """"6" (fixo) ou "5-10" (faixa) → (piso, topo); None se não serve."""
    casou = re.match(r"^(\d{1,3})(?:\s*-\s*(\d{1,3}))?$", (texto or "").strip())
    if not casou:
        return None
    piso = int(casou.group(1))
    topo = int(casou.group(2)) if casou.group(2) else piso
    if piso < 1 or topo < piso or topo > MAXIMO_POR_DIA:
        return None
    return piso, topo


def interpretar_janela(texto):
    """"13-22" ou "Dia Todo" → (inicio, fim) em horas; None se não serve."""
    texto = (texto or "").strip()
    if texto == "Dia Todo (24h) 🕛" or texto.lower() == "dia todo":
        return 0, 24
    casou = re.match(r"^(\d{1,2})\s*-\s*(\d{1,2})$", texto)
    if not casou:
        return None
    inicio, fim = map(int, casou.groups())
    if not 0 <= inicio < fim <= 24:
        return None
    return inicio, fim


# Rascunhos por Dia (robô) e Vídeos por Dia (assistente): primeiro o Rafael toca em Faixa
# ou Fixo, depois digita. Decisão do Rafael: DECISOES.md, Shopee Vídeo. Os exemplos são os
# de agora (exemplos.py); "faixa" e "fixo" aqui são só os de quem nunca mandou.
FAIXA_DO_ROBO = {"coisa": "rascunhos", "faixa": "1-3", "fixo": "2", "nome": "shopee_video_robo",
                 "chaves": ("robo_limite_min", "robo_limite_max")}
FAIXA_DO_ASSISTENTE = {"coisa": "vídeos", "faixa": "5-10", "fixo": "6", "nome": "shopee_video_assistente",
                       "chaves": ("limite_min", "limite_max")}


def com_exemplos_de_agora(jeito, config=None):
    """O jeito da pergunta com a faixa e o fixo de agora (ou os últimos que o Rafael mandou)."""
    config = config or ler_config()
    cota = tuple(config[chave] for chave in jeito["chaves"])
    faixa, fixo = exemplos.faixa_e_fixo(jeito["nome"], cota, jeito["faixa"], jeito["fixo"])
    return {**jeito, "faixa": faixa, "fixo": fixo}


def exemplo_do_horario(config, do_robo):
    """O "início-fim" de agora; em Dia Todo, o último que o Rafael mandou."""
    if do_robo:
        return exemplos.janela("shopee_video_robo", config["robo_inicio"], config["robo_fim"], "9-21")
    return exemplos.janela("shopee_video_assistente", config["inicio"], config["fim"], "13-22")


def texto_faixa_ou_fixo(pergunta, jeito, piso, topo, maximo):
    piso_ex, topo_ex = jeito["faixa"].split("-")
    return (f"{pergunta}\n\n"
            f"• <b>{BOTAO_FAIXA}</b>: você manda o mínimo e o máximo (ex.: <code>{jeito['faixa']}</code>), "
            f"e cada dia sorteia um número entre {piso_ex} e {topo_ex}\n"
            f"• <b>{BOTAO_FIXO}</b>: você manda um número (ex.: <code>{jeito['fixo']}</code>), "
            f"e são sempre {jeito['fixo']} por dia\n\n"
            f"<i>Hoje está em {rotulo_faixa(piso, topo)}. Máximo de {maximo} por dia. A faixa existe para a "
            "quantidade não ser sempre igual, que é o que denuncia robô.</i>")


def texto_pedir_numeros(tipo, jeito):
    if tipo == "faixa":
        return f"🎲 Envie o <b>mínimo e o máximo</b>, com um traço. Ex.: <code>{jeito['faixa']}</code>."
    return f"📌 Envie <b>quantos {jeito['coisa']} por dia</b>. Ex.: <code>{jeito['fixo']}</code>."


def ler_faixa_escolhida(texto, tipo, jeito, maximo):
    """
    (piso, topo) do que o Rafael digitou depois de tocar em Faixa (o máximo maior que o
    mínimo) ou em Fixo (um número só); sem tocar em nenhum, vale um ou outro. Devolve
    ((piso, topo), None) ou (None, o aviso).
    """
    faixa = interpretar_faixa(texto)
    if not faixa or faixa[1] > maximo:
        if tipo == "faixa":
            return None, f"⚠️ Envie dois números com um traço, de 1 a {maximo} (ex.: <code>{jeito['faixa']}</code>)."
        if tipo == "fixo":
            return None, f"⚠️ Envie um número de 1 a {maximo} (ex.: <code>{jeito['fixo']}</code>)."
        return None, (f"⚠️ Toque em {BOTAO_FAIXA} ou {BOTAO_FIXO}, ou envie um número "
                      f"(<code>{jeito['fixo']}</code>) ou uma faixa (<code>{jeito['faixa']}</code>), de 1 a {maximo}.")
    piso, topo = faixa
    if tipo == "faixa" and topo == piso:
        return None, (f"⚠️ Na faixa, o máximo tem de ser maior que o mínimo (ex.: <code>{jeito['faixa']}</code>). "
                      f"Para o mesmo número todo dia, toque em Cancelar e escolha {BOTAO_FIXO}.")
    if tipo == "fixo" and topo != piso:
        return None, (f"⚠️ No fixo, envie um número só (ex.: <code>{jeito['fixo']}</code>). "
                      f"Para sortear entre dois números, toque em Cancelar e escolha {BOTAO_FAIXA}.")
    return faixa, None


def rotulo_faixa(piso, topo):
    return f"{piso} a {topo}" if topo > piso else f"{piso} (fixo)"


def rotulo_janela(inicio, fim):
    return "o dia todo (24h)" if (inicio, fim) == (0, 24) else f"das {inicio}h às {fim}h"


def rotulo_interacoes(config):
    """O Horário das Interações em palavras; sem ele escolhido, junto com o Horário do Robô."""
    janela = robo.janela_das_interacoes(config)
    return rotulo_janela(janela[0], janela[1]) if janela else "junto com o Horário do Robô"


def rotulo_de_postar(config):
    """Os trechos em que o robô prepara e posta: "das 8h às 12h e das 14h às 22h"."""
    trechos = robo.trechos_de_postar(config)
    return " e ".join(rotulo_janela(a // 60, -(-b // 60)) for a, b in trechos) or "nenhum"


def videos_hoje(config, agora=None):
    """Quantos vídeos o dia de hoje sorteou dentro da faixa (o mesmo número o dia inteiro)."""
    dia = (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d")
    return sortear_teto_do_dia(CHAVE_CONFIG, dia, config["limite_min"], config["limite_max"])


def rascunhos_hoje(config, agora=None):
    return robo.quantos_hoje(config, (agora or datetime.now(fuso_horario)).strftime("%Y-%m-%d"))


# --- Painel ---

BOTAO_CELULAR = "Celular do Robô 📱"
BOTAO_PAREAR = "Parear Celular 🔗"
BOTAO_RECONECTAR = "Reconectar Celular 🔄"
BOTAO_VOLTAR = "Voltar à Shopee Vídeo 🔙"
BOTAO_PASSO_A_PASSO = "Passo a Passo 📖"
BOTAO_TELA = "Ver Tela do Celular 🖥️"

BOTAO_RASCUNHOS = "Rascunhos do Robô 📝"
BOTAO_FAIXA_ROBO = "Rascunhos por Dia 📦"
BOTAO_HORARIO_ROBO = "Horário do Robô 🕗"
BOTAO_HORARIO_INTERACOES = "Horário das Interações 💬"
BOTAO_SEM_HORARIO_PROPRIO = "Junto com o Robô 🔁"
BOTAO_TREINO = "Testar Caminho 🧭"
BOTAO_PREPARAR = "Preparar 1 Agora ⚡"
BOTAO_HISTORICO = "Histórico do Robô 📋"
BOTAO_FILA = "Fila de Rascunhos 🗂️"
BOTAO_EDICAO = "Edição dos Vídeos ✂️"
# Dois editores, cada um com o vídeo completo e as versões (pedido do Rafael, 27/10). Os
# botões de antes ainda podem estar no teclado dele: os do Editor 1 e 3 valem como o Editor 1,
# os do 2 e 4 como o Editor 2.
BOTAO_EDITOR_1 = "Editor 1 sem Legendas 👀"
BOTAO_EDITOR_2 = "Editor 2 com Legendas ✨"
BOTOES_ANTIGOS_EDITOR_1 = ["Ver Exemplo Editor 1 👀", "Ver Exemplo da Edição 👀", "Ver Exemplo Editor 3 🔀"]
BOTOES_ANTIGOS_EDITOR_2 = ["Ver Exemplo Editor 2 ✨", "Ver Exemplo Editor 4 🎬"]
BOTAO_LIGAR_EDICAO = "Ligar Edição ✅"
BOTAO_DESLIGAR_EDICAO = "Desligar Edição ⏸️"
BOTAO_APROVAR = "Aprovar Rascunho ✅"
BOTAO_RECUSAR = "Recusar Rascunho ❌"
BOTAO_PROXIMO = "Próximo Rascunho ⏭️"
# Os botões de pausar e retomar de cada robô trocam conforme o estado (pausado mostra
# Retomar). Os antigos "Pausar Robô"/"Retomar Robô" ainda podem estar no teclado do
# Rafael e valem para o assistente.
PAUSA_ASSISTENTE = ["Pausar Assistente ⏸️", "Retomar Assistente ▶️", "Pausar Robô ⏸️", "Retomar Robô ▶️"]
PAUSA_ROBO = ["Pausar Postagem ⏸️", "Retomar Postagem ▶️"]


BOTAO_MENU_ROBO = "Robô Automático 🤖"
BOTAO_MENU_ASSISTENTE = "Modo Assistente 📲"
BOTAO_COMO_FUNCIONA = "Como Funciona ❓"
BOTAO_VOLTAR_ROBO = "Voltar ao Robô 🔙"


# O menu é separado por robô, e cada tela diz em uma linha o que cada botão faz: o
# Rafael tem de entender tudo sozinho daqui a meses. Decisão do Rafael: DECISOES.md,
# Shopee Vídeo.

def teclado_painel(config):
    return montar_teclado([
        [KeyboardButton(text=BOTAO_RASCUNHOS)],
        [KeyboardButton(text=BOTAO_MENU_ROBO), KeyboardButton(text=BOTAO_MENU_ASSISTENTE)],
        [KeyboardButton(text="Fonte dos Vídeos 🎞️"), KeyboardButton(text=BOTAO_COMO_FUNCIONA)],
        [KeyboardButton(text="Voltar aos Canais 🔙")],
    ])


def teclado_robo(config):
    pausa_robo = "Retomar Postagem ▶️" if config["robo_pausado"] else "Pausar Postagem ⏸️"
    return montar_teclado([
        [KeyboardButton(text=pausa_robo), KeyboardButton(text=BOTAO_RASCUNHOS)],
        [KeyboardButton(text=BOTAO_FILA), KeyboardButton(text=BOTAO_PREPARAR)],
        [KeyboardButton(text=BOTAO_HISTORICO), KeyboardButton(text=BOTAO_EDICAO)],
        [KeyboardButton(text=BOTAO_FAIXA_ROBO), KeyboardButton(text=BOTAO_HORARIO_ROBO)],
        [KeyboardButton(text=BOTAO_HORARIO_INTERACOES)],
        [KeyboardButton(text=BOTAO_TREINO), KeyboardButton(text=BOTAO_CELULAR)],
        [KeyboardButton(text=BOTAO_VOLTAR)],
    ])


teclado_janela_interacoes = montar_teclado([
    [KeyboardButton(text=BOTAO_SEM_HORARIO_PROPRIO)],
    [KeyboardButton(text="Cancelar ❌")],
])


teclado_faixa_ou_fixo = montar_teclado([
    [KeyboardButton(text=BOTAO_FAIXA), KeyboardButton(text=BOTAO_FIXO)],
    [KeyboardButton(text="Cancelar ❌")],
])


def teclado_edicao(config):
    liga = BOTAO_DESLIGAR_EDICAO if config.get("edicao_ligada") else BOTAO_LIGAR_EDICAO
    return montar_teclado([
        [KeyboardButton(text=BOTAO_EDITOR_1), KeyboardButton(text=BOTAO_EDITOR_2)],
        [KeyboardButton(text=liga)],
        [KeyboardButton(text=BOTAO_VOLTAR_ROBO)],
    ])


def teclado_assistente(config):
    pausa = "Retomar Assistente ▶️" if config["pausado"] else "Pausar Assistente ⏸️"
    return montar_teclado([
        [KeyboardButton(text=pausa), KeyboardButton(text="Enviar 1 Agora 📤")],
        [KeyboardButton(text="Vídeos por Dia 📦"), KeyboardButton(text="Horário de Postagem ⏰")],
        [KeyboardButton(text=BOTAO_VOLTAR)],
    ])


# Um treino leva poucos minutos. Sem resultado depois disto, ele parou no meio (o processo
# caiu ou foi reiniciado junto com o bot), e o painel diz isso em vez de "rodando" para sempre.
MINUTOS_DO_TREINO = 30


def _linha_treino(agora=None):
    estado = robo.ler_estado()
    if estado.get("treino_depois_da_suspensao"):
        # A segunda caiu na suspensão: o treino roda logo que ela acaba (P41).
        return "⏳ o desta semana roda logo que a suspensão acabar"
    if not estado.get("treino_em"):
        return "ainda não rodou"
    resultado = estado.get("treino_resultado") or ""
    quando = _data_curta(estado["treino_em"])
    if resultado == "ok":
        return f"✅ caminho OK em {quando}"
    if not resultado:
        try:
            inicio = datetime.strptime(estado["treino_em"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            inicio = None
        agora = (agora or datetime.now(fuso_horario)).replace(tzinfo=None)
        if inicio and (agora - inicio).total_seconds() < MINUTOS_DO_TREINO * 60:
            return f"⏳ rodando desde {quando}"
        return f"⚠️ o treino de {quando} não terminou; toque em {BOTAO_TREINO} para rodar de novo"
    return f"⚠️ {html_escape(resultado)} em {quando}"


def quem_posta(config):
    """Quem está postando agora, numa frase: o robô, o assistente ou ninguém."""
    if robo.suspensa(config):
        ate = robo.quando_acaba(robo.suspenso_ate(config))
        if config["robo_pausado"] and config["pausado"]:
            return f"⏸️ <b>ninguém</b> (os dois estão pausados, e a Shopee suspendeu a conta de Shopee Vídeo até {ate})"
        return (f"⛔ <b>ninguém</b> (a Shopee suspendeu a conta de Shopee Vídeo até {ate}; depois disso, volta "
                "sozinho quem estava postando)")
    if not config["robo_pausado"]:
        return "🤖 <b>o Robô Automático</b> (pelo Motorola; o assistente fica em espera)"
    if config["pausado"]:
        return "⏸️ <b>ninguém</b> (os dois estão pausados)"
    if config.get("robo_pausa_motivo") == "celular desconectado":
        return "📲 <b>o Assistente</b> (você posta à mão; o robô pausou porque o Motorola desconectou)"
    return "📲 <b>o Assistente</b> (você posta à mão)"


def texto_painel(config, agora=None):
    return (
        "🎬 <b>Shopee Vídeo</b>\n\n"
        f"Quem posta agora: {quem_posta(config)}\n"
        f"📝 Rascunhos esperando você: <b>{len(robo.esperando_aprovacao())}</b>\n"
        f"🎞️ Fonte dos vídeos: <b>{assistente.FONTES.get(config['fonte'], config['fonte'])}</b>\n\n"
        "<b>O que cada botão faz</b>\n"
        f"📝 <b>{BOTAO_RASCUNHOS}</b>: os vídeos que o robô deixou prontos no Motorola, um por um, "
        "para você aprovar ou recusar.\n"
        f"🤖 <b>{BOTAO_MENU_ROBO}</b>: ligar ou pausar o robô, quantos rascunhos por dia, o horário dele, "
        "o teste do caminho e o celular.\n"
        f"📲 <b>{BOTAO_MENU_ASSISTENTE}</b>: ligar ou pausar os envios no seu privado, quantos por dia, o "
        "horário e o Enviar 1 Agora.\n"
        "🎞️ <b>Fonte dos Vídeos</b>: de onde os dois puxam os vídeos.\n"
        f"❓ <b>{BOTAO_COMO_FUNCIONA}</b>: o resumo de tudo, para quando você esquecer."
    )


def status_robo(config):
    if robo.suspensa(config):
        ate = robo.quando_acaba(robo.suspenso_ate(config))
        if config["robo_pausado"]:
            return f"⏸️ <b>Pausado</b> (e a conta de Shopee Vídeo está suspensa pela Shopee até {ate})"
        return (f"⛔ <b>Sem postar</b> (conta de Shopee Vídeo suspensa pela Shopee até {ate}: não prepara nem "
                "posta, e volta sozinho depois; a limpeza dos favoritos, as respostas, o feed e a Saúde do Vídeo "
                "continuam)")
    if not config["robo_pausado"]:
        return "▶️ <b>Ativo</b>"
    if config.get("robo_pausa_motivo") == "celular desconectado":
        return "⏸️ <b>Pausado</b> (o Motorola desconectou: toque em Retomar Postagem ▶️)"
    return "⏸️ <b>Pausado</b>"


def texto_robo(config, agora=None, celular=None):
    """A tela do Robô Automático. celular: o adb fala com o Motorola agora (None = não olhou)."""
    piso, topo = config["robo_limite_min"], config["robo_limite_max"]
    hoje = f" (hoje: <b>{rascunhos_hoje(config, agora)}</b>)" if topo > piso else ""
    linha_celular = ""
    if celular is not None:
        linha_celular = ("📱 Celular: ✅ <b>conectado</b>\n" if celular
                         else f"📱 Celular: ⚠️ <b>desconectado</b> (veja em {BOTAO_CELULAR})\n")
    return (
        "🤖 <b>Robô Automático</b>\n"
        "Prepara os vídeos sozinho no Motorola e só posta o que você aprovar. Com ele ligado, o "
        "assistente fica em espera.\n\n"
        f"Status: {status_robo(config)}\n"
        f"{linha_celular}"
        f"📦 Rascunhos por dia: <b>{rotulo_faixa(piso, topo)}</b>{hoje}\n"
        f"🕗 Horário do robô: <b>{rotulo_janela(config['robo_inicio'], config['robo_fim'])}</b>"
        + (f" (prepara e posta {rotulo_de_postar(config)})" if robo.janela_das_interacoes(config) else "") + "\n"
        f"💬 Horário das interações: <b>{rotulo_interacoes(config)}</b>\n"
        f"💔 Descurtir tudo em Meus favoritos (Criadores & Afiliados): todo dia às <b>{robo.HORA_DO_DESCURTIR}h</b> (nessa hora, só isso; "
        "no fim de cada rascunho, ele já tira as curtidas que deu)\n"
        f"📝 Esperando a sua aprovação: <b>{len(robo.esperando_aprovacao())}</b> | "
        f"✅ Aprovados na fila: <b>{len(robo.listar('aprovado'))}</b>\n"
        f"✂️ Edição dos vídeos: {rotulo_edicao(config)}\n"
        f"🧭 Treino: {_linha_treino()}\n\n"
        "<b>O que cada botão faz</b>\n"
        "▶️ <b>Retomar / Pausar Postagem</b>: liga ou pausa o robô. O Retomar acha o Motorola sozinho; "
        "pausado, o assistente volta a mandar no seu privado.\n"
        f"📝 <b>{BOTAO_RASCUNHOS}</b>: aprovar ou recusar os rascunhos, um por um.\n"
        f"🗂️ <b>{BOTAO_FILA}</b>: a lista dos rascunhos esperando a sua aprovação e dos aprovados, com a hora "
        "prevista de cada post e, se algum passou da hora, por que ainda não saiu.\n"
        f"⚡ <b>{BOTAO_PREPARAR}</b>: o robô prepara um rascunho na hora, a mais do dia (mesmo pausado).\n"
        f"📋 <b>{BOTAO_HISTORICO}</b>: tudo o que o robô tentou nas últimas 24 h, com o produto e em que passo "
        f"parou. Às {HORA_DO_RESUMO}h chega o resumo do dia no seu privado.\n"
        f"✂️ <b>{BOTAO_EDICAO}</b>: o vídeo original com o Editor 2 (a foto do produto no começo, a miniatura no "
        "canto, a seta vermelha e as legendas); ver os exemplos do Editor 1 e do Editor 2, ligar ou desligar.\n"
        f"📦 <b>{BOTAO_FAIXA_ROBO}</b>: quantos rascunhos ele prepara por dia (uma faixa, sorteada a cada dia).\n"
        f"🕗 <b>{BOTAO_HORARIO_ROBO}</b>: em que horário ele prepara os rascunhos e posta (fora do Horário das "
        "Interações).\n"
        f"💬 <b>{BOTAO_HORARIO_INTERACOES}</b>: em que horário ele responde os comentários dos seus vídeos e "
        "comenta e curte os de outros criadores. Nessa janela, ele só volta a preparar e postar quando acaba "
        "os comentários e as respostas do dia.\n"
        f"🧭 <b>{BOTAO_TREINO}</b>: confere agora se as telas do app da Shopee continuam iguais "
        "(ele faz isso sozinho toda segunda).\n"
        f"📱 <b>{BOTAO_CELULAR}</b>: a ligação com o Motorola (reconectar, ver a tela de longe)."
    )


def rotulo_edicao(config):
    return "✅ <b>ligada</b> (em todos os vídeos)" if config.get("edicao_ligada") else "⏸️ <b>desligada</b>"


def texto_edicao(config):
    """A tela da Edição dos Vídeos. Escolhas do Rafael (25, 27 e 28/10): DECISOES.md, Shopee Vídeo."""
    return (
        "✂️ <b>Edição dos Vídeos</b>\n"
        f"<b>Editor 1 sem legendas</b>: o robô edita o vídeo como você faz no LumaFusion: a foto do anúncio do "
        f"produto nos primeiros {edicao_video.SEGUNDOS_DA_FOTO} segundos e, até o fim do vídeo, uma miniatura dela "
        "no canto de cima à direita e a sua seta vermelha (a do arquivo Seta da Shopee, sem o fundo) embaixo à "
        "esquerda, no lugar em que você põe no LumaFusion.\n\n"
        "<b>Editor 2 com legendas</b> (o que vai ao ar): o Editor 1 e os textos na tela, um de cada vez, no "
        "vídeo original, sem cortar nada nem mudar a velocidade: o nome do produto e uma vantagem que o vídeo "
        "mostra (escritos pela IA, sem marca) e o preço (\"A partir de\", pela API), em letra média, no alto, logo "
        "abaixo da miniatura ou num dos lados, onde a IA vê que não cobrem o produto nem o rosto; sem lugar livre, "
        "ou se o vídeo já tem texto próprio na tela, ele vai sem os nossos textos.\n\n"
        "<b>O que vai ao ar</b>: o vídeo original do Editor 2, nos rascunhos do robô e no modo assistente. Se o "
        "Editor 2 não sair num vídeo, ele vai com o Editor 1, sem legendas (o registro anota). Vale para todos os "
        "vídeos que o robô usa (Autorais, Viral, Canal Afiliados e Grupo Público): todos os seus grupos e vídeos "
        "são autorais. Nos vídeos de Ver Produtos (vários produtos), a foto e o preço são os do 1º produto que o "
        "robô anexou.\n\n"
        "<b>O exemplo de cada editor</b>: primeiro o vídeo original, inteiro e sem cortes, só com as edições "
        "do editor, como vai ao ar; depois até 2 versões modificadas dele. Cada versão abre com um momento "
        "diferente, que a IA escolhe vendo o vídeo, e segue dali (o que vinha antes vai para o fim); a 1ª tem "
        "até uns 3/4 do vídeo original e a 2ª é a mais curta (pelo menos "
        f"{edicao_video.MINIMO_DO_REMONTADO} s; sai o fim, nunca o meio de uma fala). Nos dois editores, as "
        "versões também ficam sem as partes paradas, com os trechos calmos mais rápidos e uma câmera lenta curta "
        "(onde alguém fala, nada muda); no Editor 2, cada uma mostra na tela a vantagem do seu momento e termina "
        "com uma chamada diferente para o produto, e no Editor 1 vai sem textos. Só sai versão com um momento a pelo menos "
        f"{edicao_video.ENTRE_VERSOES:.0f} s do começo "
        "do vídeo e dos das outras: vídeo curto, ou com fala do começo ao fim, rende menos versões. As versões "
        "ficam só no exemplo: nada delas vai ao ar.\n\n"
        f"Agora: {rotulo_edicao(config)} (Editor 2, só o vídeo original, sem cortes)\n\n"
        "<b>O que cada botão faz</b>\n"
        f"👀 <b>{BOTAO_EDITOR_1}</b>: manda no seu privado, já editados e sem postar, o vídeo original e as "
        "versões modificadas do próximo vídeo que o robô pegaria, sem legendas, e o que cada versão mudou; cada "
        "toque mostra um vídeo novo.\n"
        f"✨ <b>{BOTAO_EDITOR_2}</b>: o mesmo, com o Editor 2 e as legendas.\n"
        f"✅ <b>{BOTAO_LIGAR_EDICAO}</b> / ⏸️ <b>{BOTAO_DESLIGAR_EDICAO}</b>: liga ou desliga a edição nos "
        "próximos rascunhos e nos vídeos do modo assistente. Com a edição ligada, só vai vídeo editado: o vídeo "
        "que não sair editado fica de lado e o robô pega o próximo."
    )


def texto_assistente(config, agora=None):
    if config["pausado"]:
        status = "⏸️ <b>Pausado</b>"
    elif robo.suspensa(config):
        status = (f"💤 <b>Em espera</b> (conta de Shopee Vídeo suspensa pela Shopee até "
                  f"{robo.quando_acaba(robo.suspenso_ate(config))})")
    elif assistente_em_espera(config):
        status = "💤 <b>Em espera</b> (o robô automático está postando)"
    else:
        status = "▶️ <b>Ativo</b>"
    piso, topo = config["limite_min"], config["limite_max"]
    hoje = f" (sorteado a cada dia; hoje: <b>{videos_hoje(config, agora)}</b>)" if topo > piso else ""
    return (
        "📲 <b>Modo Assistente</b>\n"
        "Prepara cada postagem (vídeo, título, produtos e comentário) e manda aqui no seu privado, para "
        "você postar pelo seu celular. Trabalha quando o robô automático está pausado.\n\n"
        f"Status: {status}\n"
        f"📦 Vídeos por dia: <b>{rotulo_faixa(piso, topo)}</b>{hoje}\n"
        f"⏰ Horário dos envios: <b>{rotulo_janela(config['inicio'], config['fim'])}</b>\n"
        f"📤 Mandados hoje: <b>{assistente.enviados_hoje(agora)}</b>\n\n"
        "<b>O que cada botão faz</b>\n"
        "⏸️ <b>Pausar / Retomar Assistente</b>: para ou volta a mandar as postagens no seu privado "
        "(pausado, ele não manda nem com o robô parado).\n"
        "📤 <b>Enviar 1 Agora</b>: manda uma postagem na hora, mesmo pausado.\n"
        "📦 <b>Vídeos por Dia</b>: quantas postagens por dia (uma faixa, sorteada a cada dia).\n"
        "⏰ <b>Horário de Postagem</b>: em que horário as postagens chegam."
    )


COMO_FUNCIONA = (
    "❓ <b>Como funciona a Shopee Vídeo</b>\n\n"
    "1️⃣ <b>Dois robôs.</b> O 🤖 Robô Automático prepara os vídeos sozinho no Motorola e só posta o que "
    "você aprovar. O 📲 Assistente manda tudo pronto aqui no privado para você postar à mão.\n\n"
    "2️⃣ <b>Um cobre o outro.</b> Com o robô ligado, o assistente fica em espera. Pausou o robô (ou o "
    "Motorola desconectou), o assistente volta a mandar. Nunca os dois juntos.\n\n"
    "3️⃣ <b>No dia a dia.</b> O robô avisa quando deixa um rascunho pronto. Toque em Rascunhos do Robô 📝 "
    "e aprove ✅ ou recuse ❌. Os aprovados saem espalhados no horário do robô, e você recebe o link do "
    "post e o comentário para copiar. Curtir e comentar o vídeo é sempre com a sua mão.\n\n"
    "4️⃣ <b>Motorola desconectou?</b> Chega um aviso. No Motorola: Configurações → Sistema → Opções do "
    "desenvolvedor → ligue a <b>Depuração por Wi-Fi</b>. Depois: Robô Automático 🤖 → <b>Retomar "
    "Postagem ▶️</b>. O servidor acha o celular sozinho.\n\n"
    "5️⃣ <b>Verificação da Shopee (quebra-cabeça)?</b> O robô para e manda aqui um link para você "
    "resolver pela tela do celular, de onde estiver.\n\n"
    "6️⃣ <b>A Shopee mudou o app?</b> Toda segunda o robô treina o caminho e avisa se algo mudou "
    "(Testar Caminho 🧭 faz isso na hora). Aí o Claude ajusta.\n\n"
    "7️⃣ <b>Resetou ou trocou o Motorola?</b> Robô Automático 🤖 → Celular do Robô 📱 → Passo a Passo 📖.\n\n"
    "8️⃣ <b>A Shopee suspendeu a conta?</b> O robô lê o aviso nas Notificações do app e avisa aqui. Até o "
    "fim da suspensão, ele não prepara, não posta e não testa o caminho (a Shopee fecha o Postar vídeo), e o "
    "assistente espera; a limpeza dos favoritos, as respostas aos comentários, o feed e a Saúde do Vídeo "
    "continuam, e com o celular fora da tomada ele só pula. No fim, os dois voltam sozinhos (se você pausou o "
    "robô no meio, ele continua pausado), e o teste do caminho da segunda que caiu na suspensão roda logo "
    "no começo."
)


async def mostrar_painel(message: types.Message, state: FSMContext):
    await state.set_state(ShopeeVideoFluxo.menu)
    config = ler_config()
    await message.answer(texto_painel(config), parse_mode="HTML", reply_markup=teclado_painel(config))


async def mostrar_robo(message: types.Message, state: FSMContext):
    await state.set_state(ShopeeVideoFluxo.menu_robo)
    config = ler_config()
    celular = await asyncio.to_thread(celular_robo.conectado)
    await message.answer(texto_robo(config, celular=celular), parse_mode="HTML", reply_markup=teclado_robo(config))


async def mostrar_assistente(message: types.Message, state: FSMContext):
    await state.set_state(ShopeeVideoFluxo.menu_assistente)
    config = ler_config()
    await message.answer(texto_assistente(config), parse_mode="HTML", reply_markup=teclado_assistente(config))


# Depois de um Cancelar ❌ (bot_mestre), volta à tela de onde o ajuste saiu.
ESTADOS_DO_ROBO = ("aguardando_tipo_faixa_robo", "aguardando_faixa_robo", "aguardando_confirmacao_faixa_robo", "aguardando_janela_robo",
                   "aguardando_confirmacao_janela_robo", "aguardando_janela_interacoes",
                   "aguardando_confirmacao_janela_interacoes", "aguardando_confirmacao_pausa_robo", "menu_robo",
                   "rascunho", "aguardando_confirmacao_recusa")
ESTADOS_DO_ASSISTENTE = ("aguardando_tipo_faixa", "aguardando_faixa", "aguardando_confirmacao_faixa", "aguardando_janela",
                         "aguardando_confirmacao_janela", "aguardando_confirmacao_pausa", "menu_assistente")
ESTADOS_DO_CELULAR = ("celular", "aguardando_escolha_celular", "aguardando_pareamento", "aguardando_porta")


async def voltar_depois_de_cancelar(message: types.Message, state: FSMContext, estado_anterior):
    nome = (estado_anterior or "").split(":")[-1]
    if nome in ESTADOS_DO_ROBO:
        await mostrar_robo(message, state)
    elif nome in ESTADOS_DO_ASSISTENTE:
        await mostrar_assistente(message, state)
    elif nome in ESTADOS_DO_CELULAR:
        await mostrar_celular(message, state)
    else:
        await mostrar_painel(message, state)


# Os botões do painel funcionam em qualquer estado (StateFilter("*")): depois de um
# reinício o estado do FSM some, mas o teclado continua na tela do Rafael.
@router.message(F.text == "Shopee Vídeo 🎬", StateFilter("*"))
async def painel_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    logger.info("🎬 Acessando o painel da Shopee Vídeo.")
    await mostrar_painel(message, state)


@router.message(F.text == BOTAO_MENU_ROBO, StateFilter("*"))
async def menu_robo_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await mostrar_robo(message, state)


@router.message(F.text.in_([BOTAO_MENU_ASSISTENTE]), StateFilter("*"))
async def menu_assistente_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await mostrar_assistente(message, state)


@router.message(F.text == BOTAO_COMO_FUNCIONA, StateFilter("*"))
async def como_funciona_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await state.set_state(ShopeeVideoFluxo.menu)
    await message.answer(COMO_FUNCIONA, parse_mode="HTML", reply_markup=teclado_painel(ler_config()))


@router.message(F.text == BOTAO_VOLTAR_ROBO, StateFilter("*"))
async def voltar_ao_robo(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await mostrar_robo(message, state)


# --- Edição dos vídeos ---

# Um exemplo de cada vez (Editor 1 ou 2): cada um baixa a foto e passa o vídeo pelo ffmpeg.
_exemplo_da_edicao = asyncio.Lock()
# O exemplo leva minutos, e um deploy no meio reinicia o bot e o corta sem aviso (27/10: o
# Rafael tocou no Editor 2 às 23:05 e o bot reiniciou às 23:07). O exemplo em andamento fica
# anotado; ao ligar, o bot avisa que ele foi interrompido. Anotação velha não avisa.
CHAVE_EXEMPLO_EM_ANDAMENTO = "edicao_exemplo_em_andamento"
EXEMPLO_INTERROMPIDO_RECENTE = timedelta(minutes=30)
# O nome, o botão e uns minutos a mais que o exemplo de cada editor leva (até 3 vídeos).
NOME_DO_EDITOR = {1: "Editor 1 (sem legendas)", 2: "Editor 2 (com legendas)"}
BOTAO_DO_EDITOR = {1: BOTAO_EDITOR_1, 2: BOTAO_EDITOR_2}
MINUTOS_DO_EXEMPLO = {1: 8, 2: 8}
# A anotação de um exemplo de antes da junção dos editores (27/10) pode dizer 3 ou 4.
EDITOR_DE_ANTES = {3: 1, 4: 2}


async def avisar_exemplo_interrompido():
    """Ao ligar o bot: o exemplo que estava sendo montado foi cortado pelo reinício? Avisa no privado."""
    anotado = db.ler_config(CHAVE_EXEMPLO_EM_ANDAMENTO, {}) or {}
    if not anotado.get("editor"):
        return
    db.salvar_config(CHAVE_EXEMPLO_EM_ANDAMENTO, {})
    try:
        desde = datetime.fromisoformat(anotado.get("desde", ""))
    except ValueError:
        return
    if datetime.now(fuso_horario) - desde > EXEMPLO_INTERROMPIDO_RECENTE:
        return
    editor = EDITOR_DE_ANTES.get(anotado["editor"], anotado["editor"])
    editor = editor if editor in BOTAO_DO_EDITOR else 1
    try:
        await bot_instance.send_message(
            ADMIN_ID, f"⚠️ O exemplo do {NOME_DO_EDITOR[editor]} foi interrompido por uma atualização do bot "
                      f"e não chegou. Toque de novo em {BOTAO_DO_EDITOR[editor]}.")
    except Exception as e:
        logger.warning(f"⚠️ [Shopee Vídeo] Aviso do exemplo interrompido não saiu: {type(e).__name__}")


async def mostrar_edicao(message, state):
    await state.set_state(ShopeeVideoFluxo.menu_robo)
    config = ler_config()
    await message.answer(texto_edicao(config), parse_mode="HTML", reply_markup=teclado_edicao(config))


@router.message(F.text == BOTAO_EDICAO, StateFilter("*"))
async def edicao_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await mostrar_edicao(message, state)


@router.message(F.text.in_([BOTAO_LIGAR_EDICAO, BOTAO_DESLIGAR_EDICAO]), StateFilter("*"))
async def ligar_edicao_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    ligar = message.text == BOTAO_LIGAR_EDICAO
    alterar_config(edicao_ligada=ligar)
    registro_processos.registrar("shopee_video", "edição do vídeo: painel", "ligada" if ligar else "desligada", ok=True)
    logger.info(f"✂️ [Shopee Vídeo] Edição dos vídeos {'ligada' if ligar else 'desligada'} pelo painel.")
    await mostrar_edicao(message, state)


def _segundos(valor):
    return f"{valor:.0f} s".replace(".", ",")


def _linha_dos_textos(textos):
    return "🔤 Textos na tela: " + ", ".join(f"“{html_escape(t)}”" for t in textos)


def _linha_do_lugar(resumo, com_textos):
    """[a linha do lugar dos textos na legenda do exemplo], ou [] sem nada a dizer."""
    if not com_textos:
        if resumo.get("texto_no_video"):
            return ["📍 Sem as nossas legendas: o vídeo já tem texto próprio na tela."]
        return (["📍 Sem texto na tela: a IA não achou lugar que não cubra o rosto ou o produto."]
                if resumo.get("lugar") == edicao_video.SEM_LUGAR else [])
    lugar = {"alto": "no alto, ao lado da miniatura", "meio": "logo abaixo da miniatura",
             "esquerda": "do lado esquerdo, no meio da altura",
             "direita": "do lado direito, no meio da altura"}.get(resumo.get("lugar"))
    if not lugar:
        return []
    return [f"📍 Lugar do texto: {lugar}"
            + (" (a IA escolheu)" if resumo.get("lugar_da_ia") else " (o padrão: a IA não disse)")]


def _momento(segundos):
    return f"{segundos:.1f} s".replace(".", ",")


def _tamanho_da_versao(versoes, indice, inteiro):
    """O fim da linha do tamanho na legenda: ": o vídeo inteiro" ou ": N% do vídeo completo" (e ", a mais curta")."""
    remontado = versoes[indice].get("remontado", 0)
    if not inteiro or not versoes[indice].get("curta"):
        return ": o vídeo inteiro" if inteiro else ""
    mais_curta = len(versoes) > 1 and remontado <= min(v.get("remontado", 0) for v in versoes)
    return f": {round(100 * remontado / inteiro)}% do vídeo completo" + (", a mais curta" if mais_curta else "")


def _linhas_da_remontagem(remontagem):
    """O que a remontagem das versões muda no vídeo original (números), para a legenda."""
    linhas = []
    cortado = remontagem.get("cortado", 0)
    linhas.append(f"✂️ Partes paradas tiradas: {_segundos(cortado)}" if cortado >= 0.5
                  else "✂️ Nenhuma parte parada para tirar")
    linhas.append(f"⏩ Trechos acelerados: {remontagem.get('acelerados', 0)} | "
                  f"🐢 Em câmera lenta: {remontagem.get('camera_lenta', 0)}")
    if remontagem.get("com_fala", 0) >= 0.5:
        linhas.append(f"🗣️ Com fala, ficou inteiro e na velocidade normal: {_segundos(remontagem['com_fala'])}")
    return linhas


def _linha_do_original(editor):
    """A linha que explica o 1º vídeo do exemplo: o original, sem cortes (pedido do Rafael, 28/10)."""
    edicoes = "a foto no começo, a miniatura e a seta" + (", e as legendas" if editor == 2 else "")
    return ("Inteiro, na ordem e na velocidade dele, sem cortes; só com as edições que você "
            f"pediu ({edicoes})." + (" É assim que ele vai ao ar." if editor == 2 else ""))


def _titulo_do_video(indice, total, gancho):
    """
    O título no alto da legenda, numa linha só e com uma linha em branco depois (pedido do
    Rafael, vídeo de 28/10, 00:30): o original ou a versão modificada N de M.
    """
    return f"✂️ <b>VERSÃO MODIFICADA {indice} de {total - 1}</b>" if gancho else "🎬 <b>VÍDEO ORIGINAL</b>"


def legenda_das_versoes(nome, resumo, indice, editor):
    """
    A legenda de um vídeo do exemplo do editor (1 ou 2): o completo ou uma versão; a última diz
    também o que vale para todos.
    """
    versoes = resumo["versoes"]
    versao, total = versoes[indice], len(versoes)
    gancho = versao.get("gancho")
    linhas = [_titulo_do_video(indice, total, gancho), "",
              f"{'👀' if editor == 1 else '✨'} Exemplo do {NOME_DO_EDITOR[editor]}, vídeo {indice + 1} de "
              f"{total} (não foi postado): {html_escape(nome)}."]
    if gancho:
        mostra = f" (o que ele mostra: “{html_escape(versao['vantagem'])}”)" if editor == 1 and versao.get("vantagem") else ""
        linhas.append(f"Só no exemplo, não vai ao ar: abre com o trecho de {_momento(gancho[0])} a "
                      f"{_momento(gancho[1])} do vídeo original{mostra}"
                      + (" e segue dali; o que vinha antes vai para o fim" if gancho[0] >= 0.5 else ""))
    else:
        linhas.append(_linha_do_original(editor))
    linhas.append(f"⏱️ {_segundos(versao.get('remontado', 0))} (mais os {edicao_video.SEGUNDOS_DA_FOTO} s da foto)"
                  + _tamanho_da_versao(versoes, indice, resumo.get("inteiro")))
    if gancho:
        linhas += _linhas_da_remontagem(resumo.get("remontagem") or {})
    if versao.get("textos"):
        linhas.append(_linha_dos_textos(versao["textos"]))
    if versao.get("musica"):
        linhas.append(f"🎵 Música de fundo: {versao['musica']} (o vídeo original não tem som)")
    if not gancho and editor == 2 and not resumo.get("textos_da_ia", True):
        linhas.append("⚠️ A IA não escreveu o nome e a vantagem desta vez.")
    if indice < total - 1:
        return "\n".join(linhas)
    if total < edicao_video.VERSOES_POR_VIDEO:
        porque = ("a IA não sugeriu momentos diferentes" if not resumo.get("versoes_da_ia")
                  else "onde alguém fala, o vídeo fica inteiro e na ordem" if resumo.get("com_fala", 0) >= 0.5
                  else "os outros momentos ficavam perto demais do começo do vídeo ou de outro momento, ou eram "
                  "curtos demais")
        extras = total - 1
        rendeu = (f"o vídeo original e mais {extras} {'versão modificada' if extras == 1 else 'versões modificadas'}, "
                  "diferentes de verdade" if extras else "só o vídeo original, sem versões modificadas")
        linhas.append(f"🔢 Este vídeo rendeu {rendeu} ({porque}).")
    linhas += _linha_do_lugar(resumo, any(v.get("textos") for v in versoes))
    outro = 2 if editor == 1 else 1
    linhas.append(f"Toque de novo em {BOTAO_DO_EDITOR[editor]} para ver outro vídeo; compare com o "
                  f"{BOTAO_DO_EDITOR[outro]}.")
    return "\n".join(linhas)


async def _mandar_exemplo(message, state, editor):
    """Monta e manda no privado o exemplo do editor (1 ou 2), um exemplo de cada vez."""
    if _exemplo_da_edicao.locked():
        await message.answer("⏳ Um exemplo da edição já está sendo montado. Ele chega aqui em instantes.")
        return
    async with _exemplo_da_edicao:
        await message.answer(f"⏳ Montando o exemplo do {NOME_DO_EDITOR[editor]} com o próximo vídeo que o robô "
                             f"pegaria: o vídeo completo e as versões. Leva até uns {MINUTOS_DO_EXEMPLO[editor]} "
                             "minutos.")
        db.salvar_config(CHAVE_EXEMPLO_EM_ANDAMENTO, {"editor": editor, "desde": datetime.now(fuso_horario).isoformat()})
        try:
            await _montar_e_mandar_exemplo(message, editor)
        finally:
            db.salvar_config(CHAVE_EXEMPLO_EM_ANDAMENTO, {})
    # O texto da Edição dos Vídeos não volta depois do exemplo: ele empurrava os vídeos para
    # cima, e o teclado do painel continua embaixo (pedido do Rafael, vídeo de 28/10, 00:30).
    await state.set_state(ShopeeVideoFluxo.menu_robo)


async def _montar_e_mandar_exemplo(message, editor):
    """O exemplo do editor (1 ou 2) montado e mandado no privado; False quando não saiu (com o aviso)."""
    with tempfile.TemporaryDirectory() as pasta:
        destino = os.path.join(pasta, "exemplo.mp4")
        resumo = None
        try:
            if editor == 1:
                nome, motivo, resumo = await asyncio.to_thread(edicao_video.exemplo_editor_1, destino)
            else:
                nome, motivo, resumo = await asyncio.to_thread(edicao_video.exemplo_editor_2, destino)
        except Exception as e:
            nome, motivo = None, f"erro ({type(e).__name__})"
        if editor == 1:
            registro_processos.registrar("shopee_video", "edição do vídeo: exemplo do editor 1",
                                         "mandado" if nome else "não saiu", motivo, ok=bool(nome))
        else:
            registro_processos.registrar("shopee_video", "edição do vídeo: exemplo do editor 2",
                                         "mandado" if nome else "não saiu", motivo, ok=bool(nome))
        if not nome:
            await message.answer(f"⚠️ O exemplo do {NOME_DO_EDITOR[editor]} não saiu: {html_escape(motivo)}.",
                                 parse_mode="HTML")
            return False
        for indice, versao in enumerate(resumo["versoes"]):
            await message.answer_video(FSInputFile(versao["arquivo"]), supports_streaming=True, parse_mode="HTML",
                                       caption=legenda_das_versoes(nome, resumo, indice, editor))
    return True


@router.message(F.text.in_([BOTAO_EDITOR_1, *BOTOES_ANTIGOS_EDITOR_1]), StateFilter("*"))
async def exemplo_editor_1_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await _mandar_exemplo(message, state, 1)


@router.message(F.text.in_([BOTAO_EDITOR_2, *BOTOES_ANTIGOS_EDITOR_2]), StateFilter("*"))
async def exemplo_editor_2_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await _mandar_exemplo(message, state, 2)


# --- Vídeos por dia ---

@router.message(F.text == "Vídeos por Dia 📦", StateFilter("*"))
async def pedir_faixa(message: types.Message, state: FSMContext):
    if not _admin(message): return
    config = ler_config()
    await message.answer(
        texto_faixa_ou_fixo("Quantos vídeos por dia?", com_exemplos_de_agora(FAIXA_DO_ASSISTENTE, config),
                            config["limite_min"], config["limite_max"], MAXIMO_POR_DIA),
        parse_mode="HTML", reply_markup=teclado_faixa_ou_fixo)
    await state.update_data(tipo_faixa=None)
    await state.set_state(ShopeeVideoFluxo.aguardando_tipo_faixa)



# --- Horário de postagem ---

@router.message(F.text == "Horário de Postagem ⏰", StateFilter("*"))
async def pedir_janela(message: types.Message, state: FSMContext):
    if not _admin(message): return
    config = ler_config()
    await message.answer(
        "Em que horário as postagens podem chegar? Elas se espalham dentro dessa faixa.\n\n"
        f"Envie <code>início-fim</code> (ex.: <code>{exemplo_do_horario(config, False)}</code>) ou toque em Dia Todo.\n"
        f"<i>Hoje está {rotulo_janela(config['inicio'], config['fim'])}.</i>",
        parse_mode="HTML", reply_markup=teclado_janela_dia_todo)
    await state.set_state(ShopeeVideoFluxo.aguardando_janela)



# --- Pausa ---

@router.message(F.text.in_(PAUSA_ASSISTENTE), StateFilter("*"))
async def pedir_pausa(message: types.Message, state: FSMContext):
    if not _admin(message): return
    pausar = message.text.startswith("Pausar")
    await state.update_data(pausar=pausar)
    pergunta = ("⚠️ <b>Pausar</b> o modo assistente? Ele para de mandar postagens até você retomar."
                if pausar else
                "▶️ <b>Retomar</b> o modo assistente? Ele volta a mandar as postagens aqui no seu "
                "privado, dentro do horário e da quantidade do painel.")
    botao = "Confirmar Pausa ✅" if pausar else "Confirmar Retomada ✅"
    teclado = teclado_com_cancelar(botao)
    await message.answer(pergunta, parse_mode="HTML", reply_markup=teclado)
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_pausa)



# --- Enviar 1 agora ---

@router.message(F.text == "Enviar 1 Agora 📤", StateFilter("*"))
async def enviar_agora_handler(message: types.Message, state: FSMContext):
    """Manda uma postagem na hora, mesmo pausado (para testar ou para postar mais uma)."""
    if not _admin(message): return
    if _envio.locked():
        await message.answer("⏳ Já estou preparando uma postagem. Ela chega em instantes.")
        return
    logger.info("📤 Shopee Vídeo: Enviar 1 Agora.")
    await message.answer("⏳ Preparando a postagem: a IA assiste ao vídeo e escreve o texto (1 a 2 min; até 4 se ela precisar refazer o título).")
    resultado = await enviar_um(ler_config()["fonte"])
    if resultado != "postagem mandada no seu privado":
        await message.answer(f"⚠️ Não mandei: {resultado}.")


# --- Fonte dos vídeos ---

# O que muda em cada fonte, para o Rafael escolher sabendo.
EXPLICACAO_FONTES = (
    "🎞️ <b>De onde o robô puxa os vídeos?</b>\n\n"
    "• <b>Autorais 🎥</b>: feitos para afiliados repostarem (recomendado).\n"
    "• <b>Viral (Espião) 🕵️</b>: vídeos de outros criadores; a Shopee não recomenda conteúdo "
    "copiado (diretriz 7.2.1), e a IA pula os com marca d'água de outra plataforma.\n"
    "• <b>Canal Afiliados 📺</b>: os vídeos da fila do seu canal principal.\n"
    "• <b>Grupo Público 📬</b>: os vídeos enviados pelos membros.\n\n"
    "<i>Vale para os próximos envios, inclusive o Enviar 1 Agora.</i>"
)


def teclado_fontes():
    nomes = list(assistente.FONTES.values())
    linhas = [[KeyboardButton(text=nome) for nome in nomes[i:i + 2]] for i in range(0, len(nomes), 2)]
    return montar_teclado(linhas + [[KeyboardButton(text="Cancelar ❌")]])


@router.message(F.text == "Fonte dos Vídeos 🎞️", StateFilter("*"))
async def pedir_fonte(message: types.Message, state: FSMContext):
    if not _admin(message): return
    atual = assistente.FONTES.get(ler_config()["fonte"], "")
    await message.answer(f"{EXPLICACAO_FONTES}\n\nHoje: <b>{atual}</b>.", parse_mode="HTML",
                         reply_markup=teclado_fontes())
    await state.set_state(ShopeeVideoFluxo.aguardando_fonte)


# --- Robô automático ---

@router.message(F.text.in_(PAUSA_ROBO), StateFilter("*"))
async def pedir_pausa_robo(message: types.Message, state: FSMContext):
    if not _admin(message): return
    pausar = message.text.startswith("Pausar")
    pergunta = ("⚠️ <b>Pausar</b> o robô automático? Ele para de preparar rascunhos e de postar os "
                "aprovados até você retomar, e o modo assistente volta a mandar as postagens aqui no "
                "privado. Os rascunhos ficam guardados."
                if pausar else
                "▶️ <b>Retomar</b> o robô automático? Eu acho o celular guardado sozinho e ele volta a "
                "preparar rascunhos e a postar os que você aprovar, dentro do Horário do Robô. O modo "
                "assistente fica em espera enquanto isso.")
    botao = "Confirmar Pausa ✅" if pausar else "Confirmar Retomada ✅"
    await message.answer(pergunta, parse_mode="HTML", reply_markup=teclado_com_cancelar(botao))
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_pausa_robo)


@router.message(F.text == BOTAO_FAIXA_ROBO, StateFilter("*"))
async def pedir_faixa_robo(message: types.Message, state: FSMContext):
    if not _admin(message): return
    config = ler_config()
    await message.answer(
        texto_faixa_ou_fixo("Quantos rascunhos novos o robô prepara por dia?",
                            com_exemplos_de_agora(FAIXA_DO_ROBO, config), config["robo_limite_min"], config["robo_limite_max"], robo.MAXIMO_POR_DIA),
        parse_mode="HTML", reply_markup=teclado_faixa_ou_fixo)
    await state.update_data(tipo_faixa=None)
    await state.set_state(ShopeeVideoFluxo.aguardando_tipo_faixa_robo)


@router.message(StateFilter(ShopeeVideoFluxo.aguardando_tipo_faixa, ShopeeVideoFluxo.aguardando_tipo_faixa_robo),
                F.text.in_([BOTAO_FAIXA, BOTAO_FIXO]))
async def escolher_tipo_faixa(message: types.Message, state: FSMContext):
    """Faixa 🎲 ou Fixo 📌, no Rascunhos por Dia (robô) ou no Vídeos por Dia (assistente)."""
    if not _admin(message): return
    do_robo = (await state.get_state() or "").endswith("_robo")
    tipo = "faixa" if message.text == BOTAO_FAIXA else "fixo"
    await message.answer(texto_pedir_numeros(tipo, com_exemplos_de_agora(FAIXA_DO_ROBO if do_robo else FAIXA_DO_ASSISTENTE)),
                         parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.update_data(tipo_faixa=tipo)
    await state.set_state(ShopeeVideoFluxo.aguardando_faixa_robo if do_robo else ShopeeVideoFluxo.aguardando_faixa)


@router.message(F.text == BOTAO_HORARIO_ROBO, StateFilter("*"))
async def pedir_janela_robo(message: types.Message, state: FSMContext):
    if not _admin(message): return
    config = ler_config()
    await message.answer(
        "Em que horário o robô pode tocar no celular? Os rascunhos e as postagens aprovadas se "
        "espalham dentro dessa faixa, em minutos sorteados.\n\n"
        f"Envie <code>início-fim</code> (ex.: <code>{exemplo_do_horario(config, True)}</code>) ou toque em Dia Todo.\n"
        f"<i>Hoje está {rotulo_janela(config['robo_inicio'], config['robo_fim'])}. Fora dele, se a Shopee "
        "pedir a verificação, ninguém resolve até você acordar.</i>",
        parse_mode="HTML", reply_markup=teclado_janela_dia_todo)
    await state.set_state(ShopeeVideoFluxo.aguardando_janela_robo)


@router.message(F.text == BOTAO_HORARIO_INTERACOES, StateFilter("*"))
async def pedir_janela_interacoes(message: types.Message, state: FSMContext):
    """
    O Horário das Interações: nele o robô só responde os comentários e comenta e curte no
    feed; fora dele, só prepara e posta. Escolha do Rafael (24/10, P22 a P24): DECISOES.md,
    Shopee Vídeo.
    """
    if not _admin(message): return
    config = ler_config()
    janela = robo.janela_das_interacoes(config) or (None, None)
    exemplo = exemplos.janela("shopee_video_interacoes", *janela, "12-15")
    await message.answer(
        "Em que horário o robô responde os comentários dos seus vídeos e comenta e curte os vídeos de outros "
        "criadores? Nessa janela, ele só volta a preparar e postar quando acaba os comentários e as respostas do "
        "dia; fora dela, só prepara e posta.\n\n"
        f"Envie <code>início-fim</code> (ex.: <code>{exemplo}</code>) ou toque em {BOTAO_SEM_HORARIO_PROPRIO} para "
        "ele voltar a interagir dentro do Horário do Robô.\n"
        f"<i>Hoje está {rotulo_interacoes(config)}. Com 3 h ou mais cabem, com folga, os 3 comentários do dia "
        "e as respostas.</i>",
        parse_mode="HTML", reply_markup=teclado_janela_interacoes)
    await state.set_state(ShopeeVideoFluxo.aguardando_janela_interacoes)


@router.message(F.text == BOTAO_PREPARAR, StateFilter("*"))
async def preparar_handler(message: types.Message, state: FSMContext):
    """
    Um rascunho na hora, a mais do plano do dia, mesmo pausado ou fora do Horário do
    Robô: para testar ou ter mais um. Ele entra em Rascunhos do Robô 📝 como os outros.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if not _admin(message): return
    if robo_ocupado():
        await message.answer("⏳ O robô está no meio de uma rodada no celular. Tente de novo em alguns minutos.")
        return
    logger.info("⚡ Shopee Vídeo: Preparar 1 Agora.")
    await message.answer("⚡ Preparando 1 rascunho agora no Motorola. Em uns 5 a 10 min ele chega em "
                         f"{BOTAO_RASCUNHOS}, e o robô avisa aqui; se algo impedir, ele diz o quê.")
    asyncio.create_task(rodar_robo("--preparar"))


@router.message(F.text == BOTAO_HISTORICO, StateFilter("*"))
async def historico_handler(message: types.Message, state: FSMContext):
    """
    Tudo o que o robô tentou nas últimas 24 h: o que deu certo, o que foi pulado e em que
    passo parou. Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if not _admin(message): return
    await state.set_state(ShopeeVideoFluxo.menu_robo)
    await message.answer(robo.texto_historico(), parse_mode="HTML", reply_markup=teclado_robo(ler_config()))


@router.message(F.text == BOTAO_FILA, StateFilter("*"))
async def fila_handler(message: types.Message, state: FSMContext):
    """
    Os rascunhos esperando aprovação e os aprovados, com a hora prevista de ir ao ar e o
    porquê de um aprovado atrasado. Pedido do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if not _admin(message): return
    await state.set_state(ShopeeVideoFluxo.menu_robo)
    await message.answer(robo.texto_da_fila(), parse_mode="HTML", reply_markup=teclado_robo(ler_config()))


@router.message(F.text == BOTAO_TREINO, StateFilter("*"))
async def treino_handler(message: types.Message, state: FSMContext):
    """
    O treino na hora: o robô percorre o caminho do app sem salvar nem postar e diz se
    alguma tela mudou. Roda mesmo pausado ou fora do Horário do Robô.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if not _admin(message): return
    if robo_ocupado():
        await message.answer("⏳ O robô está no meio de uma rodada no celular. Tente de novo em alguns minutos.")
        return
    logger.info("🧭 Shopee Vídeo: Testar Caminho.")
    await message.answer("🧭 Treino começando: o robô percorre o caminho no celular sem salvar nem postar. "
                         "O resultado chega aqui em uns 5 min.")
    asyncio.create_task(rodar_robo("--treino"))


# --- Rascunhos do robô: aprovar um por um ---

def teclado_rascunho():
    return montar_teclado([[KeyboardButton(text=BOTAO_APROVAR), KeyboardButton(text=BOTAO_RECUSAR)],
                           [KeyboardButton(text=BOTAO_PROXIMO)],
                           [KeyboardButton(text=BOTAO_VOLTAR)]])


def linhas_da_origem(fonte):
    """
    De onde veio o vídeo. Só os Autorais são vídeos próprios: os outros são copiados de
    outros canais e podem ser removidos por propriedade intelectual (o 1º post do robô,
    em 18/10/2026, foi). Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if not fonte:
        return ""
    nome = assistente.FONTES.get(fonte, fonte)
    alerta = ("" if fonte == "autorais" else
              "\n⚠️ Vídeo copiado de outro canal: pode ser removido por propriedade intelectual.")
    return f"🎞️ <b>Origem do vídeo:</b> {html_escape(nome)}{alerta}\n\n"


def linhas_da_conferencia(conferencia):
    """O que a IA disse em cada conferência vídeo × produto, para o Rafael julgar também."""
    try:
        vistos = json.loads(conferencia or "[]")
    except ValueError:
        vistos = []
    if not vistos:
        return ""
    linhas = "\n".join(f"{vez}ª: {html_escape(visto or 'confere (sem motivo)')}" for vez, visto in enumerate(vistos, 1))
    return f"🤖 <b>A IA conferiu o vídeo com o produto ({len(vistos)} vezes):</b>\n{linhas}\n\n"


def linha_do_rotulo_de_ia(rotulo_ia):
    """O que a IA decidiu sobre o Rótulo de IA (rascunho de antes dessa conferência: nada)."""
    if rotulo_ia is None:
        return ""
    if rotulo_ia:
        return f"🤖 <b>Rótulo de IA:</b> ligado. A IA viu: {html_escape(rotulo_ia)}\n\n"
    return "🤖 <b>Rótulo de IA:</b> desligado (a IA não viu sinal claro de vídeo feito por IA).\n\n"


def texto_rascunho(rascunho, posicao, total):
    produtos = "\n".join(f"• {html_escape(nome)}" for nome in rascunho["produtos"]) or "• ?"
    aviso = (f"⚠️ Da última vez não deu certo: {html_escape(rascunho['motivo'])}\n\n"
             if rascunho.get("motivo") else "")
    return (f"📝 <b>Rascunho {posicao} de {total}</b> (salvo em {_data_curta(rascunho['criado_em'])})\n\n"
            "📝 <b>Título</b> (o que está na legenda):\n"
            f"<code>{html_escape(rascunho['titulo'] or '')}</code>\n\n"
            f"🛍️ <b>{'Produtos anexados' if len(rascunho['produtos'] or []) > 1 else 'Produto anexado'}:</b>\n{produtos}\n"
            f"🔗 {html_escape(rascunho['link'] or '')}\n\n"
            f"{linhas_da_origem(rascunho.get('fonte'))}"
            f"{linhas_da_conferencia(rascunho.get('conferencia'))}{linha_do_rotulo_de_ia(rascunho.get('rotulo_ia'))}"
            f"{aviso}"
            f"<b>{BOTAO_APROVAR}</b>: o robô posta, um de cada vez, dentro do Horário do Robô.\n"
            f"<b>{BOTAO_RECUSAR}</b>: o robô apaga o rascunho do celular, e o vídeo não volta.")


async def mostrar_rascunho(message, state, depois_de=None):
    """
    Um rascunho por vez, com o vídeo, o print da tela final, o título e o link do produto:
    o Rafael é o validador, e o print prova que o que ele aprova é o que vai ao ar.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    pendentes = robo.esperando_aprovacao()
    if not pendentes:
        # Só a frase, já com o teclado do painel: o texto do painel inteiro depois de cada
        # aprovação ou recusa repetia o que o Rafael já sabe. Pedido dele: DECISOES.md, Shopee Vídeo.
        await state.set_state(ShopeeVideoFluxo.menu)
        await message.answer("📝 Nenhum rascunho esperando a sua aprovação.", reply_markup=teclado_painel(ler_config()))
        return
    seguintes = [r for r in pendentes if depois_de is not None and r["id"] > depois_de]
    rascunho = (seguintes or pendentes)[0]
    posicao = pendentes.index(rascunho) + 1
    await state.set_state(ShopeeVideoFluxo.rascunho)
    await state.update_data(rascunho_id=rascunho["id"])
    if rascunho["arquivo"] and os.path.exists(rascunho["arquivo"]):
        await message.answer_video(FSInputFile(rascunho["arquivo"]), supports_streaming=True,
                                   caption=f"🎬 Rascunho {posicao}: o vídeo.")
    if rascunho["print"] and os.path.exists(rascunho["print"]):
        await message.answer_photo(FSInputFile(rascunho["print"]),
                                   caption=f"📱 Rascunho {posicao}: a tela final no celular, como vai ao ar.")
    await message.answer(texto_rascunho(rascunho, posicao, len(pendentes)), parse_mode="HTML",
                         disable_web_page_preview=True, reply_markup=teclado_rascunho())


@router.message(F.text == BOTAO_RASCUNHOS, StateFilter("*"))
async def rascunhos_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    logger.info("📝 Shopee Vídeo: Rascunhos do Robô.")
    await mostrar_rascunho(message, state)


async def _rascunho_da_vez(message, state):
    """O rascunho que está na tela, se ele ainda espera aprovação; senão mostra o próximo."""
    ident = (await state.get_data()).get("rascunho_id")
    rascunho = robo.pegar(ident) if ident else None
    if not rascunho or rascunho["estado"] != "rascunho":
        await message.answer("Esse rascunho já foi resolvido. Mostro o próximo.")
        await mostrar_rascunho(message, state)
        return None
    return rascunho


@router.message(F.text == BOTAO_APROVAR, StateFilter("*"))
async def aprovar_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    rascunho = await _rascunho_da_vez(message, state)
    if not rascunho:
        return
    quando = robo.aprovar(rascunho["id"])
    logger.info("✅ Shopee Vídeo: rascunho aprovado.")
    await message.answer(f"✅ Aprovado. O robô posta por volta de <b>{_data_curta(quando)}</b> e manda aqui o "
                         "link do post e o comentário.", parse_mode="HTML")
    await mostrar_rascunho(message, state, depois_de=rascunho["id"])


@router.message(F.text == BOTAO_RECUSAR, StateFilter("*"))
async def pedir_recusa(message: types.Message, state: FSMContext):
    if not _admin(message): return
    if not await _rascunho_da_vez(message, state):
        return
    await message.answer("❌ <b>Recusar</b> este rascunho? O robô apaga do celular, e o vídeo não volta.",
                         parse_mode="HTML", reply_markup=teclado_com_cancelar("Confirmar Recusa ✅"))
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_recusa)


@router.message(F.text == BOTAO_PROXIMO, StateFilter("*"))
async def proximo_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await mostrar_rascunho(message, state, depois_de=(await state.get_data()).get("rascunho_id"))


# --- Celular do robô ---
# Plano do celular de verdade (roteiro_robo_shopee_video.md, fase 1c): parear uma vez,
# com o código que só existe enquanto a janela dele está aberta no celular, e
# reconectar quando a porta muda (o celular reiniciou ou a depuração foi desligada).

def teclado_celular():
    return montar_teclado([[KeyboardButton(text=BOTAO_RECONECTAR), KeyboardButton(text=BOTAO_TELA)],
                           [KeyboardButton(text=BOTAO_PAREAR), KeyboardButton(text=BOTAO_PASSO_A_PASSO)],
                           [KeyboardButton(text=BOTAO_VOLTAR_ROBO)]])


# Para o Rafael refazer tudo sozinho depois de resetar o celular, talvez meses depois:
# frases curtas, na ordem, com os nomes das telas como aparecem no Motorola.
PASSO_A_PASSO = (
    "📖 <b>Passo a passo do celular do robô</b>\n"
    "Para quando você resetar o celular guardado (ou trocar de celular). Faça na ordem.\n\n"
    "🔁 <b>Só reiniciou ou desligou a depuração?</b> Não precisa de tudo: ligue a "
    f"<b>Depuração por Wi-Fi</b> (passo 6) e toque em <b>{BOTAO_RECONECTAR}</b>.\n\n"
    "<b>Parte 1: no celular guardado</b>\n"
    "1️⃣ <b>Ligar:</b> configure o celular, entre na sua conta Google e conecte no <b>Wi-Fi de casa</b>. "
    "Deixe no carregador.\n"
    "2️⃣ <b>Apps:</b> na Play Store, instale a <b>Shopee</b> e o <b>Tailscale</b>.\n"
    "3️⃣ <b>Shopee:</b> entre na sua conta pessoal (a de sempre). Se pedir verificação, resolva com a mão. "
    "Depois: Configurações → Apps → Shopee → Bateria → <b>Sem restrições</b>.\n"
    "4️⃣ <b>Tailscale:</b> entre com a mesma conta de antes e ligue (aceite o pedido de VPN). "
    "Depois: Configurações → Rede e Internet → VPN → ⚙️ do Tailscale → ligue <b>VPN sempre ativa</b>.\n"
    "5️⃣ <b>Modo desenvolvedor:</b> Configurações → Sobre o telefone → toque <b>7 vezes</b> em "
    "\"Número da versão\" (ele pede o PIN).\n"
    "6️⃣ <b>Opções do desenvolvedor:</b> ligue <b>Manter ativado</b> e <b>Depuração por Wi-Fi</b> "
    "(toque em Permitir).\n"
    "💡 Não achou uma opção? Use a lupa 🔍 no alto das Configurações e digite o nome dela.\n\n"
    "<b>Parte 2: aqui no bot</b>\n"
    f"7️⃣ Toque em <b>{BOTAO_PAREAR}</b>.\n"
    "8️⃣ No celular: Depuração por Wi-Fi → <b>Parear o dispositivo com um código de pareamento</b>. "
    "Deixe a janela aberta.\n"
    "9️⃣ Mande aqui os números da janela: o <b>código de 6 dígitos</b>, um espaço e a <b>porta</b> "
    "(o número depois dos dois-pontos). Ex.: <code>123456 37123</code>. Eu apago a sua mensagem.\n"
    "🔟 Depois eu peço a <b>porta da conexão</b>: na tela da Depuração por Wi-Fi, em \"Endereço IP e "
    "porta\", é o número depois dos dois-pontos (outro número). Mande só ele.\n"
    "✅ Pronto quando aparecer <b>Celular conectado</b>. Avise o Claude.\n\n"
    "<b>Uma vez só, no navegador</b> (para o celular não sair da rede depois de uns meses): "
    "login.tailscale.com → Machines → o celular → ⋯ → <b>Disable key expiry</b>. Se o celular antigo "
    "ainda aparecer na lista, pode tirar (⋯ → Remove)."
)


def _data_curta(texto):
    return f"{texto[8:10]}/{texto[5:7]} às {texto[11:16]}" if texto and len(texto) >= 16 else "?"


async def texto_celular():
    dados = celular_robo.ler()
    rede = await asyncio.to_thread(celular_robo.celulares_na_rede)
    conectado = await asyncio.to_thread(celular_robo.conectado) if dados.get("porta") else False
    if not rede:
        linha_rede = "❌ nenhum celular (ligue o Tailscale no celular guardado)"
    else:
        linha_rede = ", ".join(f"<b>{html_escape(c['nome'])}</b> {'✅ ligado' if c['online'] else '⚠️ fora do ar'}"
                               for c in rede)
    pareado = f"✅ em {_data_curta(dados['pareado_em'])}" if dados.get("pareado_em") else "⏳ ainda não"
    if conectado:
        conexao = f"✅ conectado ({html_escape(dados.get('modelo') or 'celular')})"
    elif dados.get("porta"):
        conexao = f"⚠️ desconectado: toque em {BOTAO_RECONECTAR}"
    else:
        conexao = "⏳ ainda não"
    if conectado:
        situacao = "✅ <b>Tudo certo</b>: o robô consegue usar o Motorola."
    elif dados.get("pareado_em"):
        situacao = f"⚠️ <b>Desconectado</b>: toque em <b>{BOTAO_RECONECTAR}</b>."
    else:
        situacao = f"⏳ <b>Ainda não ligado ao servidor</b>: siga o <b>{BOTAO_PASSO_A_PASSO}</b>."
    return ("📱 <b>Celular do Robô</b>\n"
            "O Motorola guardado, onde o robô automático posta. Ele fala com o servidor pela rede "
            "privada (Tailscale).\n\n"
            f"{situacao}\n"
            f"🌐 Na rede privada: {linha_rede}\n"
            f"🔗 Pareado: {pareado}\n"
            f"📶 Conexão: {conexao}\n\n"
            "<b>O que cada botão faz</b>\n"
            f"🔄 <b>{BOTAO_RECONECTAR}</b>: use quando aparecer \"desconectado\". O servidor acha o "
            "celular sozinho; se não achar, ligue a Depuração por Wi-Fi no Motorola e toque de novo.\n"
            f"🖥️ <b>{BOTAO_TELA}</b>: manda aqui um link de 30 min para ver e tocar na tela do Motorola de "
            "longe (por exemplo, para resolver a verificação da Shopee).\n"
            f"🔗 <b>{BOTAO_PAREAR}</b>: só depois de resetar o Motorola ou trocar de celular.\n"
            f"📖 <b>{BOTAO_PASSO_A_PASSO}</b>: o guia completo para deixar o celular pronto de novo.")


async def mostrar_celular(message: types.Message, state: FSMContext):
    await state.set_state(ShopeeVideoFluxo.celular)
    await message.answer(await texto_celular(), parse_mode="HTML", reply_markup=teclado_celular())


@router.message(F.text == BOTAO_CELULAR, StateFilter("*"))
async def celular_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    logger.info("📱 Acessando o celular do robô.")
    await mostrar_celular(message, state)


@router.message(F.text == BOTAO_PASSO_A_PASSO, StateFilter("*"))
async def passo_a_passo_handler(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await state.set_state(ShopeeVideoFluxo.celular)
    await message.answer(PASSO_A_PASSO, parse_mode="HTML", reply_markup=teclado_celular())


@router.message(F.text == BOTAO_TELA, StateFilter("*"))
async def abrir_tela_handler(message: types.Message, state: FSMContext):
    """
    A tela do celular no navegador, para o Rafael resolver a verificação ou mexer no app
    de longe. O link vai no privado (pelo avisar_rafael), nunca no log.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if not _admin(message): return
    await state.set_state(ShopeeVideoFluxo.celular)
    if not await asyncio.to_thread(celular_robo.conectado):
        await message.answer(f"⚠️ O celular está desconectado: toque em {BOTAO_RECONECTAR} primeiro.",
                             reply_markup=teclado_celular())
        return
    await message.answer("⏳ Abrindo a tela do celular (leva até 1 min)...")
    logger.info("🖥️ Abrindo a tela do celular do robô.")
    if await asyncio.to_thread(av.abrir_tela, True):
        await message.answer(
            "✅ O link da tela chegou aqui no privado e vale 30 min. Na página, toque em "
            "<b>Terminei</b> quando acabar: enquanto ela está aberta, o robô não mexe no celular.",
            parse_mode="HTML", reply_markup=teclado_celular())
        return
    motivo = av._ler_estado_tela().removeprefix("erro: ") or "não respondeu a tempo"
    await message.answer(f"❌ A tela não abriu ({html_escape(motivo)}). Tente de novo daqui a pouco.",
                         parse_mode="HTML", reply_markup=teclado_celular())


@router.message(F.text == BOTAO_VOLTAR, StateFilter("*"))
async def voltar_ao_painel(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await mostrar_painel(message, state)


async def _seguir_com_celular(message, state, celular, acao):
    """Com o celular escolhido, pede o código (parear) ou a porta (reconectar)."""
    await state.update_data(celular_ip=celular["ip"], celular_nome=celular["nome"])
    nome = html_escape(celular["nome"])
    if acao == "parear":
        await message.answer(
            f"🔗 <b>Parear o celular</b> ({nome})\n\n"
            "No celular guardado:\n"
            "1. Opções do desenvolvedor → <b>Depuração por Wi-Fi</b>.\n"
            "2. Toque em <b>Parear dispositivo com código de pareamento</b>.\n"
            "3. Mande aqui o <b>código de 6 dígitos</b> e a <b>porta</b> (o número depois dos dois-pontos "
            "em \"Endereço IP e porta\"), assim: <code>123456 37123</code>.\n\n"
            "<i>Deixe a janela do código aberta até eu responder. Apago a sua mensagem logo depois de "
            "usar o código.</i>",
            parse_mode="HTML", reply_markup=teclado_cancelar)
        await state.set_state(ShopeeVideoFluxo.aguardando_pareamento)
    else:
        await message.answer(
            f"🔄 <b>Conectar ao celular</b> ({nome})\n\n"
            "No celular guardado, abra Opções do desenvolvedor → <b>Depuração por Wi-Fi</b> (ligada). "
            "No alto aparece <b>Endereço IP e porta</b>: mande aqui só a <b>porta</b>, o número depois "
            "dos dois-pontos (ex.: <code>41235</code>).",
            parse_mode="HTML", reply_markup=teclado_cancelar)
        await state.set_state(ShopeeVideoFluxo.aguardando_porta)


async def _escolher_celular(message, state, acao):
    """Acha o celular ligado na rede privada; com mais de um, pergunta qual."""
    online = [c for c in await asyncio.to_thread(celular_robo.celulares_na_rede) if c["online"]]
    if not online:
        await message.answer(
            "⚠️ Não achei nenhum celular ligado na rede privada. No celular guardado, confira se o "
            "<b>Tailscale</b> está ligado e se ele está no Wi-Fi.", parse_mode="HTML", reply_markup=teclado_celular())
        return
    salvo = next((c for c in online if c["ip"] == celular_robo.ler().get("ip")), None)
    if salvo or len(online) == 1:
        await _seguir_com_celular(message, state, salvo or online[0], acao)
        return
    await state.update_data(acao_celular=acao, celulares=online)
    await message.answer("Qual destes é o celular guardado?", reply_markup=montar_teclado(
        [[KeyboardButton(text=c["nome"])] for c in online] + [[KeyboardButton(text="Cancelar ❌")]]))
    await state.set_state(ShopeeVideoFluxo.aguardando_escolha_celular)


@router.message(F.text == BOTAO_PAREAR, StateFilter("*"))
async def pedir_pareamento(message: types.Message, state: FSMContext):
    if not _admin(message): return
    await _escolher_celular(message, state, "parear")


@router.message(F.text == BOTAO_RECONECTAR, StateFilter("*"))
async def pedir_reconexao(message: types.Message, state: FSMContext):
    """Primeiro procura a porta nova sozinho; só pede a porta ao Rafael se não achar."""
    if not _admin(message): return
    if not celular_robo.ler().get("pareado_em"):
        await message.answer(f"⚠️ O celular ainda não foi pareado: toque em {BOTAO_PAREAR} primeiro.",
                             reply_markup=teclado_celular())
        return
    await message.answer("⏳ Procurando o celular guardado (até 1 min)...")
    ok, resultado = await asyncio.to_thread(celular_robo.reconectar_sozinho)
    if ok:
        logger.info("✅ Celular do robô: reconectado sozinho.")
        await message.answer(f"✅ <b>Celular conectado:</b> {html_escape(resultado)}.", parse_mode="HTML")
        await mostrar_celular(message, state)
        return
    await message.answer(f"⚠️ Não achei sozinho: {html_escape(resultado)}.")
    await _escolher_celular(message, state, "reconectar")


# --- Respostas dentro de cada ajuste ---
# Ficam depois de todos os botões: no aiogram ganha o primeiro handler que casar, e um
# botão do painel tocado no meio de um ajuste tem de abrir o botão, não virar resposta.

@router.message(StateFilter(ShopeeVideoFluxo.aguardando_tipo_faixa, ShopeeVideoFluxo.aguardando_faixa))
async def confirmar_faixa(message: types.Message, state: FSMContext):
    # Sem tocar em Faixa ou Fixo, um "5-10" ou "6" digitado direto também vale.
    tipo = (await state.get_data()).get("tipo_faixa")
    faixa, aviso = ler_faixa_escolhida(message.text, tipo, com_exemplos_de_agora(FAIXA_DO_ASSISTENTE), MAXIMO_POR_DIA)
    if aviso:
        await message.answer(aviso, parse_mode="HTML", reply_markup=teclado_cancelar if tipo else teclado_faixa_ou_fixo)
        return
    piso, topo = faixa
    await state.update_data(faixa=[piso, topo])
    await message.answer(f"Definir <b>{rotulo_faixa(piso, topo)}</b> vídeos por dia?",
                         parse_mode="HTML", reply_markup=teclado_aprovar_cancelar)
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_faixa)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_faixa, F.text == "Aprovar ✅")
async def salvar_faixa(message: types.Message, state: FSMContext):
    piso, topo = (await state.get_data())["faixa"]
    alterar_config(limite_min=piso, limite_max=topo)
    exemplos.lembrar_faixa(FAIXA_DO_ASSISTENTE["nome"], piso, topo)
    logger.info(f"✅ Shopee Vídeo: {piso} a {topo} vídeos por dia.")
    await message.answer(f"✅ Vídeos por dia: <b>{rotulo_faixa(piso, topo)}</b>.", parse_mode="HTML")
    await mostrar_assistente(message, state)


@router.message(ShopeeVideoFluxo.aguardando_janela)
async def confirmar_janela(message: types.Message, state: FSMContext):
    janela = interpretar_janela(message.text)
    if not janela:
        await message.answer(
            f"⚠️ Use o formato <code>{exemplo_do_horario(ler_config(), False)}</code>, com o início menor que "
            "o fim (de 0 a 24).",
            parse_mode="HTML", reply_markup=teclado_janela_dia_todo)
        return
    inicio, fim = janela
    await state.update_data(janela=[inicio, fim])
    await message.answer(f"Postar <b>{rotulo_janela(inicio, fim)}</b>?", parse_mode="HTML", reply_markup=teclado_aprovar_cancelar)
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_janela)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_janela, F.text == "Aprovar ✅")
async def salvar_janela(message: types.Message, state: FSMContext):
    inicio, fim = (await state.get_data())["janela"]
    alterar_config(inicio=inicio, fim=fim)
    exemplos.lembrar_janela("shopee_video_assistente", inicio, fim)
    logger.info(f"✅ Shopee Vídeo: janela {inicio}h-{fim}h.")
    await message.answer(f"✅ Horário de postagem: <b>{rotulo_janela(inicio, fim)}</b>.", parse_mode="HTML")
    await mostrar_assistente(message, state)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_pausa,
                F.text.in_(["Confirmar Pausa ✅", "Confirmar Retomada ✅"]))
async def salvar_pausa(message: types.Message, state: FSMContext):
    pausar = message.text == "Confirmar Pausa ✅"
    alterar_config(pausado=pausar)
    logger.info(f"✅ Shopee Vídeo {'pausado' if pausar else 'retomado'}.")
    await message.answer("⏸️ Modo assistente <b>pausado</b>." if pausar
                         else "▶️ Modo assistente <b>retomado</b>.", parse_mode="HTML")
    await mostrar_assistente(message, state)


@router.message(ShopeeVideoFluxo.aguardando_fonte, F.text.in_(list(assistente.FONTES.values())))
async def salvar_fonte(message: types.Message, state: FSMContext):
    fonte = next(chave for chave, nome in assistente.FONTES.items() if nome == message.text)
    alterar_config(fonte=fonte)
    logger.info(f"✅ Shopee Vídeo: vídeos de {fonte}.")
    await message.answer(f"✅ Fonte dos vídeos: <b>{message.text}</b>.", parse_mode="HTML")
    await mostrar_painel(message, state)


@router.message(StateFilter(ShopeeVideoFluxo.aguardando_tipo_faixa_robo, ShopeeVideoFluxo.aguardando_faixa_robo))
async def confirmar_faixa_robo(message: types.Message, state: FSMContext):
    tipo = (await state.get_data()).get("tipo_faixa")
    faixa, aviso = ler_faixa_escolhida(message.text, tipo, com_exemplos_de_agora(FAIXA_DO_ROBO), robo.MAXIMO_POR_DIA)
    if aviso:
        await message.answer(aviso, parse_mode="HTML", reply_markup=teclado_cancelar if tipo else teclado_faixa_ou_fixo)
        return
    piso, topo = faixa
    await state.update_data(faixa=[piso, topo])
    await message.answer(f"Definir <b>{rotulo_faixa(piso, topo)}</b> rascunhos por dia?",
                         parse_mode="HTML", reply_markup=teclado_aprovar_cancelar)
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_faixa_robo)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_faixa_robo, F.text == "Aprovar ✅")
async def salvar_faixa_robo(message: types.Message, state: FSMContext):
    piso, topo = (await state.get_data())["faixa"]
    alterar_config(robo_limite_min=piso, robo_limite_max=topo)
    exemplos.lembrar_faixa(FAIXA_DO_ROBO["nome"], piso, topo)
    logger.info(f"✅ Shopee Vídeo: robô com {piso} a {topo} rascunhos por dia.")
    await message.answer(f"✅ Rascunhos por dia: <b>{rotulo_faixa(piso, topo)}</b>.", parse_mode="HTML")
    await mostrar_robo(message, state)


@router.message(ShopeeVideoFluxo.aguardando_janela_robo)
async def confirmar_janela_robo(message: types.Message, state: FSMContext):
    janela = interpretar_janela(message.text)
    if not janela:
        await message.answer(
            f"⚠️ Use o formato <code>{exemplo_do_horario(ler_config(), True)}</code>, com o início menor que "
            "o fim (de 0 a 24).",
            parse_mode="HTML", reply_markup=teclado_janela_dia_todo)
        return
    inicio, fim = janela
    await state.update_data(janela=[inicio, fim])
    await message.answer(f"Robô trabalhando <b>{rotulo_janela(inicio, fim)}</b>?", parse_mode="HTML",
                         reply_markup=teclado_aprovar_cancelar)
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_janela_robo)


@router.message(ShopeeVideoFluxo.aguardando_janela_interacoes)
async def confirmar_janela_interacoes(message: types.Message, state: FSMContext):
    config = ler_config()
    janela = None
    if message.text != BOTAO_SEM_HORARIO_PROPRIO:
        janela = interpretar_janela(message.text)
        if not janela or janela == (0, 24):
            await message.answer(
                "⚠️ Use o formato <code>12-15</code>, com o início menor que o fim (de 0 a 24). O dia todo não "
                "serve: não sobraria hora para preparar e postar.",
                parse_mode="HTML", reply_markup=teclado_janela_interacoes)
            return
    novo = {**config, "robo_interacoes_inicio": janela[0] if janela else None,
            "robo_interacoes_fim": janela[1] if janela else None}
    if janela and not robo.trechos_de_postar(novo):
        await message.answer(
            f"⚠️ Assim não sobra hora para preparar e postar: o Horário do Robô "
            f"({rotulo_janela(config['robo_inicio'], config['robo_fim'])}) fica todo dentro dela. Mande uma "
            f"janela menor ou mude antes o {BOTAO_HORARIO_ROBO}.",
            parse_mode="HTML", reply_markup=teclado_janela_interacoes)
        return
    await state.update_data(janela_interacoes=list(janela) if janela else None)
    if janela:
        texto = (f"Interações <b>{rotulo_janela(janela[0], janela[1])}</b>; preparar e postar "
                 f"<b>{rotulo_de_postar(novo)}</b>?")
    else:
        texto = (f"Interações de volta junto com o Horário do Robô "
                 f"(<b>{rotulo_janela(config['robo_inicio'], config['robo_fim'])}</b>)?")
    await message.answer(texto, parse_mode="HTML", reply_markup=teclado_aprovar_cancelar)
    await state.set_state(ShopeeVideoFluxo.aguardando_confirmacao_janela_interacoes)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_janela_interacoes, F.text == "Aprovar ✅")
async def salvar_janela_interacoes(message: types.Message, state: FSMContext):
    janela = (await state.get_data()).get("janela_interacoes")
    # A hora da escolha fica junto: o checkup só cobra a janela nova do que veio depois dela.
    alterar_config(robo_interacoes_inicio=janela[0] if janela else None,
                   robo_interacoes_fim=janela[1] if janela else None,
                   robo_interacoes_desde=datetime.now(fuso_horario).strftime("%Y-%m-%d %H:%M:%S"))
    if janela:
        exemplos.lembrar_janela("shopee_video_interacoes", *janela)
    config = ler_config()
    # Os rascunhos que faltam hoje saem do plano novo, fora da janela nova.
    robo.replanejar_hoje(config)
    logger.info(f"✅ Shopee Vídeo: Horário das Interações {janela[0]}h-{janela[1]}h." if janela
                else "✅ Shopee Vídeo: interações de volta no Horário do Robô.")
    await message.answer(f"✅ Horário das interações: <b>{rotulo_interacoes(config)}</b>.", parse_mode="HTML")
    await mostrar_robo(message, state)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_janela_robo, F.text == "Aprovar ✅")
async def salvar_janela_robo(message: types.Message, state: FSMContext):
    inicio, fim = (await state.get_data())["janela"]
    alterar_config(robo_inicio=inicio, robo_fim=fim)
    exemplos.lembrar_janela("shopee_video_robo", inicio, fim)
    logger.info(f"✅ Shopee Vídeo: Horário do Robô {inicio}h-{fim}h.")
    await message.answer(f"✅ Horário do robô: <b>{rotulo_janela(inicio, fim)}</b>.", parse_mode="HTML")
    await mostrar_robo(message, state)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_pausa_robo,
                F.text.in_(["Confirmar Pausa ✅", "Confirmar Retomada ✅"]))
async def salvar_pausa_robo(message: types.Message, state: FSMContext):
    """
    Pausar: o robô para e o assistente volta a mandar no privado. Retomar: antes, o
    servidor acha o celular sozinho (a porta da Depuração por Wi-Fi muda); sem o celular,
    continua pausado e diz o que fazer.
    Decisão do Rafael: DECISOES.md, Shopee Vídeo.
    """
    if message.text == "Confirmar Pausa ✅":
        alterar_config(robo_pausado=True, robo_pausa_motivo="")
        logger.info("✅ Robô automático da Shopee Vídeo pausado.")
        config = ler_config()
        if robo.suspensa(config):
            await message.answer(
                "⏸️ Robô automático <b>pausado</b>. A conta de Shopee Vídeo está suspensa pela Shopee até "
                f"{robo.quando_acaba(robo.suspenso_ate(config))}. Depois disso, o robô continua pausado e o modo "
                "assistente volta a mandar as postagens aqui (se ele não estiver pausado).", parse_mode="HTML")
        else:
            await message.answer("⏸️ Robô automático <b>pausado</b>. O modo assistente volta a mandar as "
                                 "postagens aqui no privado.", parse_mode="HTML")
        await mostrar_robo(message, state)
        return
    await message.answer("⏳ Procurando o celular guardado (até 1 min)...")
    ok, resultado = await asyncio.to_thread(celular_robo.reconectar_sozinho)
    if not ok:
        logger.warning(f"⚠️ Robô automático: não retomou, celular fora ({resultado}).")
        await message.answer(
            f"⚠️ Não retomei: {html_escape(resultado)}.\n\nNo Motorola: Configurações → Sistema → Opções do "
            "desenvolvedor → ligue a <b>Depuração por Wi-Fi</b> e confira se o <b>Tailscale</b> está ligado. "
            "Depois toque de novo em <b>Retomar Postagem ▶️</b>. Enquanto isso, o modo assistente continua "
            "mandando as postagens aqui.", parse_mode="HTML")
        await mostrar_robo(message, state)
        return
    # A hora da retomada: o alerta de robô sem rodar conta dela, não da rodada de antes da pausa.
    alterar_config(robo_pausado=False, robo_pausa_motivo="",
                   robo_retomado_em=datetime.now(fuso_horario).strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("✅ Robô automático da Shopee Vídeo retomado.")
    config = ler_config()
    suspensao = (f"\n\n⛔ A conta de Shopee Vídeo está suspensa pela Shopee até "
                 f"{robo.quando_acaba(robo.suspenso_ate(config))}: ele começa sozinho depois disso."
                 if robo.suspensa(config) else "")
    await message.answer(f"▶️ Robô automático <b>retomado</b> ({html_escape(resultado)} conectado). O modo "
                         f"assistente fica em espera.{suspensao}", parse_mode="HTML")
    await mostrar_robo(message, state)


@router.message(ShopeeVideoFluxo.aguardando_confirmacao_recusa, F.text == "Confirmar Recusa ✅")
async def salvar_recusa(message: types.Message, state: FSMContext):
    ident = (await state.get_data()).get("rascunho_id")
    rascunho = robo.pegar(ident) if ident else None
    if rascunho and rascunho["estado"] == "rascunho":
        robo.recusar(ident)
        logger.info("❌ Shopee Vídeo: rascunho recusado.")
        await message.answer("❌ Recusado. O robô apaga o rascunho do celular na próxima rodada.")
    await mostrar_rascunho(message, state, depois_de=ident)


@router.message(StateFilter(ShopeeVideoFluxo.aguardando_confirmacao_faixa,
                            ShopeeVideoFluxo.aguardando_confirmacao_janela,
                            ShopeeVideoFluxo.aguardando_confirmacao_pausa,
                            ShopeeVideoFluxo.aguardando_fonte,
                            ShopeeVideoFluxo.aguardando_confirmacao_faixa_robo,
                            ShopeeVideoFluxo.aguardando_confirmacao_janela_robo,
                            ShopeeVideoFluxo.aguardando_confirmacao_janela_interacoes,
                            ShopeeVideoFluxo.aguardando_confirmacao_pausa_robo,
                            ShopeeVideoFluxo.aguardando_confirmacao_recusa))
async def confirmar_com_os_botoes(message: types.Message, state: FSMContext):
    await message.answer("Toque em um dos botões para confirmar ou em Cancelar ❌.")


@router.message(ShopeeVideoFluxo.aguardando_escolha_celular)
async def receber_escolha_celular(message: types.Message, state: FSMContext):
    dados = await state.get_data()
    celular = next((c for c in dados.get("celulares", []) if c["nome"] == message.text), None)
    if not celular:
        await message.answer("Toque no nome do celular guardado ou em Cancelar ❌.")
        return
    await _seguir_com_celular(message, state, celular, dados.get("acao_celular", "parear"))


@router.message(ShopeeVideoFluxo.aguardando_pareamento)
async def receber_pareamento(message: types.Message, state: FSMContext):
    lido = celular_robo.interpretar_pareamento(message.text)
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"⚠️ Celular do robô: não consegui apagar a mensagem do código ({type(e).__name__}).")
    if not lido:
        await message.answer("⚠️ Mande o código de 6 dígitos e a porta, separados por espaço "
                             "(ex.: <code>123456 37123</code>).", parse_mode="HTML", reply_markup=teclado_cancelar)
        return
    codigo, porta = lido
    dados = await state.get_data()
    await message.answer("⏳ Pareando com o celular…")
    ok, motivo = await asyncio.to_thread(celular_robo.parear, dados["celular_ip"], porta, codigo)
    if not ok:
        logger.warning(f"⚠️ Celular do robô: pareamento falhou ({motivo}).")
        await message.answer(f"⚠️ Não pareou: {motivo}. Toque em {BOTAO_PAREAR} para tentar de novo, com um "
                             "código novo.", reply_markup=teclado_celular())
        await state.set_state(ShopeeVideoFluxo.celular)
        return
    logger.info("✅ Celular do robô: pareado.")
    await message.answer(
        "✅ <b>Pareado!</b> Agora feche a janela do código. No alto da tela Depuração por Wi-Fi aparece "
        "<b>Endereço IP e porta</b>: mande aqui só a <b>porta</b>, o número depois dos dois-pontos "
        "(ex.: <code>41235</code>).", parse_mode="HTML", reply_markup=teclado_cancelar)
    await state.set_state(ShopeeVideoFluxo.aguardando_porta)


@router.message(ShopeeVideoFluxo.aguardando_porta)
async def receber_porta(message: types.Message, state: FSMContext):
    porta = celular_robo.interpretar_porta(message.text)
    if not porta:
        await message.answer("⚠️ Mande só a porta, o número depois dos dois-pontos (ex.: <code>41235</code>).",
                             parse_mode="HTML", reply_markup=teclado_cancelar)
        return
    dados = await state.get_data()
    await message.answer("⏳ Conectando ao celular…")
    ok, resultado = await asyncio.to_thread(celular_robo.conectar, dados["celular_ip"], porta)
    if not ok:
        logger.warning(f"⚠️ Celular do robô: conexão falhou ({resultado}).")
        await message.answer(f"⚠️ Não conectou: {resultado}. Confira a porta e mande de novo.",
                             reply_markup=teclado_cancelar)
        return
    logger.info("✅ Celular do robô: conectado.")
    await message.answer(f"✅ <b>Celular conectado:</b> {html_escape(resultado)}.", parse_mode="HTML")
    await mostrar_celular(message, state)

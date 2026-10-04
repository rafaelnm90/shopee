#!/usr/bin/env python3
"""
Tela do Android virtual no navegador, para o Rafael fazer pelo celular o que
precisa de mão humana: o login da Shopee, um código de verificação, um
quebra-cabeça de segurança. O android_virtual.py --tela a deixa rodando sozinha
e sai; ela fecha depois de MINUTOS_ABERTA ou no botão "Terminei".

Como funciona:
- um servidor web pequeno, só em 127.0.0.1, mostra prints da tela em sequência
  (adb screencap) e repassa toques, arrastos, texto e teclas (adb input);
- o botão "Enviar app" recebe um APK ou XAPK baixado no celular do Rafael e
  instala no Android (os sites de APK recusam o servidor, não o celular dele);
- um túnel temporário do Cloudflare (cloudflared, sem conta) dá um endereço
  https aleatório sem abrir porta nenhuma no servidor;
- o link leva uma chave aleatória e vai só no privado do Rafael, pelo bot. Sem a
  chave, nada responde. Nada disso aparece no log do Actions.

Estado para quem abriu (android_virtual.py): o arquivo ESTADO diz "abrindo",
"enviado", "fechada" ou "erro: ...".
Decisão do Rafael: DECISOES.md, Shopee Vídeo.
"""
import asyncio
import os
import re
import secrets
import shlex
import shutil
import subprocess
import zipfile

from aiohttp import web

import android_virtual as av
import avisar_rafael

PORTA = 8765
MINUTOS_ABERTA = 30
ESTADO = av.ARQUIVO_TELA
TECLAS = {"voltar": 4, "inicio": 3, "apagar": 67, "enter": 66, "apps": 187}
LIMITE_COORDENADA = 5000
LIMITE_APP_MB = 400
URL_TUNEL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

CHAVE = secrets.token_urlsafe(24)
FIM = asyncio.Event()


def gravar_estado(texto):
    os.makedirs(os.path.dirname(ESTADO), exist_ok=True)
    with open(ESTADO, "w") as f:
        f.write(texto)


async def adb(*partes, timeout=20):
    """Saída (bytes) de um comando adb no Android virtual; b"" se falhar."""
    proc = await asyncio.create_subprocess_exec(
        "adb", "-s", av.ENDERECO_ADB, *partes,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        saida, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return b""
    return saida if proc.returncode == 0 else b""


def autorizado(request):
    return secrets.compare_digest(request.query.get("k", ""), CHAVE)


def _numero(valor):
    """Coordenada inteira dentro da tela; qualquer outra coisa vira ValueError."""
    n = int(float(valor))
    if not 0 <= n <= LIMITE_COORDENADA:
        raise ValueError("fora da tela")
    return str(n)


def comando_da_acao(dados):
    """Os argumentos do adb para uma ação da página, ou None se ela não vale."""
    tipo = dados.get("tipo")
    try:
        if tipo == "toque":
            return ["shell", "input", "tap", _numero(dados["x"]), _numero(dados["y"])]
        if tipo == "arrastar":
            ms = str(min(max(int(dados.get("ms", 300)), 100), 5000))
            return ["shell", "input", "swipe", _numero(dados["x1"]), _numero(dados["y1"]),
                    _numero(dados["x2"]), _numero(dados["y2"]), ms]
        if tipo == "texto":
            texto = str(dados.get("texto", ""))[:500]
            if not texto:
                return None
            # O input text troca %s por espaço; o resto vai protegido do shell do Android.
            return ["shell", "input", "text", shlex.quote(texto.replace(" ", "%s"))]
        if tipo == "tecla" and dados.get("tecla") in TECLAS:
            return ["shell", "input", "keyevent", str(TECLAS[dados["tecla"]])]
    except (KeyError, TypeError, ValueError):
        return None
    return None


async def pagina(request):
    if not autorizado(request):
        raise web.HTTPNotFound()
    return web.Response(text=PAGINA.replace("__CHAVE__", CHAVE), content_type="text/html")


async def tela(request):
    if not autorizado(request):
        raise web.HTTPNotFound()
    png = await adb("exec-out", "screencap", "-p")
    return web.Response(body=png, content_type="image/png", headers={"Cache-Control": "no-store"})


async def acao(request):
    if not autorizado(request):
        raise web.HTTPNotFound()
    try:
        dados = await request.json()
    except ValueError:
        raise web.HTTPBadRequest()
    if dados.get("tipo") == "fim":
        FIM.set()
        return web.json_response({"ok": True})
    comando = comando_da_acao(dados)
    if comando is None:
        raise web.HTTPBadRequest()
    await adb(*comando)
    return web.json_response({"ok": True})


def instalar_arquivo(arquivo):
    """
    Instala o app enviado pela página (APK, XAPK ou APKS, que são zips). Devolve
    (ok, mensagem para a página).
    """
    if not zipfile.is_zipfile(arquivo):
        return False, ("o arquivo não é um app aberto (o .apkm do APKMirror é trancado): baixe o APK "
                       "ou XAPK pelo Uptodown ou APKPure")
    partes = av.partes_do_app(arquivo, os.path.join(os.path.dirname(arquivo), "partes"))
    if not partes:
        return False, "não achei o app dentro do arquivo"
    comando = "install" if len(partes) == 1 else "install-multiple"
    if not av._ok(av._adb(comando, "-r", "-g", *partes, timeout=900)):
        return False, "o Android recusou o app"
    return True, f"app da Shopee: {av.versao_shopee()}"


# O app enviado chega em pedaços (o túnel recusa pedido acima de uns 100 MB, e o
# app da Shopee passa disso). Cada pedaço diz em que byte começa: o 0 começa o
# arquivo do zero, e um pedaço repetido (a resposta se perdeu no caminho e o
# celular tentou de novo) sobrescreve o que já tinha chegado em vez de duplicar.
def _arquivo_enviado():
    return os.path.join(av.PASTA_APP, "enviado.zip")


def registrar_erro(onde, erro):
    """Só o tipo do erro, no estado da tela: o android_virtual mostra no Actions."""
    gravar_estado(f"enviado; último erro: {onde} {type(erro).__name__}")


async def receber_pedaco(request):
    """
    O Rafael baixa o app no celular (os sites de APK recusam o servidor, não o
    celular dele) e envia pela página, um pedaço por pedido.
    """
    if not autorizado(request):
        raise web.HTTPNotFound()
    try:
        inicio = int(request.query.get("inicio", ""))
    except ValueError:
        raise web.HTTPBadRequest()
    try:
        if inicio == 0:
            shutil.rmtree(av.PASTA_APP, ignore_errors=True)
            os.makedirs(av.PASTA_APP)
        tamanho = os.path.getsize(_arquivo_enviado()) if os.path.exists(_arquivo_enviado()) else 0
        if inicio > tamanho:
            return web.json_response({"ok": False, "mensagem": "o envio se perdeu no meio: envie de novo"})
        with open(_arquivo_enviado(), "r+b" if tamanho else "wb") as destino:
            destino.truncate(inicio)
            destino.seek(inicio)
            total = inicio
            async for bloco in request.content.iter_chunked(256 * 1024):
                total += len(bloco)
                if total > LIMITE_APP_MB * 1024 * 1024:
                    destino.close()
                    shutil.rmtree(av.PASTA_APP, ignore_errors=True)
                    return web.json_response({"ok": False, "mensagem": f"arquivo maior que {LIMITE_APP_MB} MB"})
                destino.write(bloco)
        return web.json_response({"ok": True, "recebido": total})
    except Exception as e:
        registrar_erro("pedaço", e)
        raise


async def instalar_enviado(request):
    """Todos os pedaços chegaram: instala e apaga o arquivo, dê certo ou não."""
    if not autorizado(request):
        raise web.HTTPNotFound()
    try:
        if not os.path.exists(_arquivo_enviado()):
            return web.json_response({"ok": False, "mensagem": "nenhum arquivo chegou: envie de novo"})
        ok, mensagem = await asyncio.to_thread(instalar_arquivo, _arquivo_enviado())
        return web.json_response({"ok": ok, "mensagem": mensagem})
    except Exception as e:
        registrar_erro("instalação", e)
        raise
    finally:
        shutil.rmtree(av.PASTA_APP, ignore_errors=True)


def montar_app():
    app = web.Application(client_max_size=64 * 1024)
    app.router.add_post("/app/pedaco", receber_pedaco)
    app.router.add_post("/app/instalar", instalar_enviado)
    app.router.add_get("/", pagina)
    app.router.add_get("/tela.png", tela)
    app.router.add_post("/acao", acao)
    return app


async def achar_url(processo, segundos=90):
    """Lê a saída do cloudflared até aparecer o endereço do túnel."""
    async def ler():
        while True:
            linha = await processo.stdout.readline()
            if not linha:
                return None
            achado = URL_TUNEL.search(linha.decode(errors="ignore"))
            if achado:
                return achado.group(0)
    try:
        return await asyncio.wait_for(ler(), segundos)
    except asyncio.TimeoutError:
        return None


async def esvaziar(processo):
    """O cloudflared continua escrevendo; sem ler, o cano enche e ele trava."""
    while await processo.stdout.readline():
        pass


async def main():
    gravar_estado("abrindo")
    subprocess.run(["adb", "connect", av.ENDERECO_ADB], capture_output=True, timeout=15)
    runner = web.AppRunner(montar_app())
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", PORTA).start()
    except OSError:
        gravar_estado("erro: já existe uma tela aberta")
        await runner.cleanup()
        return
    tunel = await asyncio.create_subprocess_exec(
        "cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORTA}",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        url = await achar_url(tunel)
        if not url:
            gravar_estado("erro: o túnel não deu endereço")
            return
        asyncio.create_task(esvaziar(tunel))
        erro = None
        try:
            if not avisar_rafael.mandar_texto(
                "📱 Tela do Android da Shopee Vídeo\n\n"
                f"{url}/?k={CHAVE}\n\n"
                f"Abra no navegador do celular. Toque na tela como num celular normal; arraste para "
                f"rolar. O campo de texto embaixo digita no Android, e o botão Enviar app instala um "
                f"app baixado no seu celular.\n"
                f"Fica aberta {MINUTOS_ABERTA} min. Quando terminar, toque em Terminei. "
                "Não repasse este link: quem tiver ele mexe no Android."):
                erro = "o Telegram recusou o link"
        except Exception as e:
            erro = f"link não enviado ({type(e).__name__})"
        if erro:
            gravar_estado(f"erro: {erro}")
            return
        gravar_estado("enviado")
        try:
            await asyncio.wait_for(FIM.wait(), MINUTOS_ABERTA * 60)
        except asyncio.TimeoutError:
            pass
        with open(ESTADO) as f:
            erro = f.read().partition("; ")[2]
        gravar_estado("fechada" + (f"; {erro}" if erro else ""))
    finally:
        if tunel.returncode is None:
            tunel.terminate()
        await runner.cleanup()


PAGINA = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Tela do Android</title>
<style>
  :root { color-scheme: light dark; --fundo: #111; --texto: #eee; --botao: #2b2b2b; }
  body { margin: 0; background: var(--fundo); color: var(--texto); font-family: system-ui, sans-serif; }
  #tela { display: block; width: auto; max-width: 100%; max-height: 60vh; margin: 0 auto; touch-action: none;
          user-select: none; -webkit-user-select: none; }
  .barra { display: flex; gap: 6px; max-width: 480px; margin: 6px auto; padding: 0 8px; box-sizing: border-box; }
  .barra button, .barra input { flex: 1; padding: 12px 6px; font-size: 16px; border-radius: 8px;
          border: 0; background: var(--botao); color: var(--texto); }
  .barra input { flex: 3; background: #fff; color: #000; }
  .barra input[type=file] { flex: 1; min-width: 0; font-size: 14px; }
  #aviso { text-align: center; font-size: 13px; opacity: .7; padding: 4px 8px; }
</style></head><body>
<img id="tela" alt="Tela do Android">
<div class="barra"><input id="texto" placeholder="Texto para digitar" autocomplete="off">
  <button onclick="digitar()">Digitar</button></div>
<div class="barra"><button onclick="tecla('voltar')">◀ Voltar</button>
  <button onclick="tecla('inicio')">● Início</button><button onclick="tecla('apagar')">⌫ Apagar</button>
  <button onclick="tecla('enter')">↵ Enter</button></div>
<div class="barra"><input type="file" id="arquivo" accept=".apk,.xapk,.apks"></div>
<div class="barra"><button onclick="enviarApp()">📦 Enviar app</button></div>
<div class="barra"><button onclick="terminar()">✅ Terminei</button></div>
<div id="aviso">Toque para clicar. Arraste para rolar ou para o quebra-cabeça.</div>
<script>
const K = "__CHAVE__";
const img = document.getElementById("tela");
let inicio = null;
function atualizar() {
  const nova = new Image();
  nova.onload = () => { img.src = nova.src; setTimeout(atualizar, 600); };
  nova.onerror = () => setTimeout(atualizar, 1500);
  nova.src = "/tela.png?k=" + K + "&t=" + Date.now();
}
function ponto(e) {
  const r = img.getBoundingClientRect();
  return { x: Math.round((e.clientX - r.left) * img.naturalWidth / r.width),
           y: Math.round((e.clientY - r.top) * img.naturalHeight / r.height) };
}
function enviar(dados) {
  return fetch("/acao?k=" + K, { method: "POST", headers: { "Content-Type": "application/json" },
                                  body: JSON.stringify(dados) });
}
img.addEventListener("pointerdown", e => { e.preventDefault(); inicio = { p: ponto(e), t: Date.now() }; });
img.addEventListener("pointerup", e => {
  if (!inicio) return;
  const fim = ponto(e), ms = Date.now() - inicio.t;
  const dist = Math.hypot(fim.x - inicio.p.x, fim.y - inicio.p.y);
  if (dist < 15) enviar({ tipo: "toque", x: fim.x, y: fim.y });
  else enviar({ tipo: "arrastar", x1: inicio.p.x, y1: inicio.p.y, x2: fim.x, y2: fim.y, ms: Math.max(ms, 300) });
  inicio = null;
});
function digitar() {
  const campo = document.getElementById("texto");
  if (campo.value) enviar({ tipo: "texto", texto: campo.value });
  campo.value = "";
}
function tecla(nome) { enviar({ tipo: "tecla", tecla: nome }); }
function avisar(texto) { document.getElementById("aviso").textContent = texto; }
const PEDACO = 2 * 1024 * 1024;
async function enviarPedaco(arquivo, inicio) {
  // Até 3 tentativas: a rede do celular oscila, e o servidor aceita o mesmo pedaço de novo.
  let motivo = "";
  for (let tentativa = 1; tentativa <= 3; tentativa++) {
    try {
      const r = await fetch("/app/pedaco?k=" + K + "&inicio=" + inicio,
                            { method: "POST", body: arquivo.slice(inicio, inicio + PEDACO) });
      if (r.ok) return await r.json();
      motivo = "o servidor respondeu " + r.status;
    } catch (e) { motivo = "a conexão caiu (" + e.name + ")"; }
    await new Promise(ok => setTimeout(ok, 2000 * tentativa));
  }
  return { ok: false, mensagem: motivo + ". Me avise no chat." };
}
async function enviarApp() {
  const campo = document.getElementById("arquivo");
  if (!campo.files.length) { avisar("Escolha primeiro o arquivo do app (APK ou XAPK)."); return; }
  const arquivo = campo.files[0];
  if (arquivo.name.toLowerCase().endsWith(".apkm")) {
    avisar("❌ O .apkm (APKMirror) é trancado. Baixe o APK ou XAPK pelo Uptodown ou APKPure.");
    return;
  }
  for (let inicio = 0; inicio < Math.max(1, arquivo.size); inicio += PEDACO) {
    avisar("Enviando... " + Math.round(inicio * 100 / arquivo.size) + "%");
    const j = await enviarPedaco(arquivo, inicio);
    if (!j.ok) { avisar("❌ " + j.mensagem); return; }
  }
  avisar("Instalando no Android... (pode levar 1 min)");
  try {
    const r = await fetch("/app/instalar?k=" + K, { method: "POST" });
    if (!r.ok) { avisar("❌ O servidor respondeu " + r.status + " na instalação. Me avise no chat."); return; }
    const j = await r.json();
    avisar((j.ok ? "✅ " : "❌ ") + j.mensagem);
  } catch (e) { avisar("❌ A conexão caiu na instalação (" + e.name + "). Me avise no chat."); }
}
function terminar() {
  if (!confirm("Fechar a tela do Android? Depois disso este link para de funcionar.")) return;
  enviar({ tipo: "fim" });
  avisar("Tela fechada. Pode sair desta página.");
}
atualizar();
</script></body></html>
"""


if __name__ == "__main__":
    asyncio.run(main())

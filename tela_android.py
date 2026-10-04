#!/usr/bin/env python3
"""
Tela do Android virtual no navegador, para o Rafael fazer pelo celular o que
precisa de mão humana: o login da Shopee, um código de verificação, um
quebra-cabeça de segurança. O android_virtual.py --tela a deixa rodando sozinha
e sai; ela fecha depois de MINUTOS_ABERTA ou no botão "Terminei".

Como funciona:
- um servidor web pequeno, só em 127.0.0.1, mostra prints da tela em sequência
  (adb screencap) e repassa toques, arrastos, texto e teclas (adb input);
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
import subprocess

from aiohttp import web

import android_virtual as av
import avisar_rafael

PORTA = 8765
MINUTOS_ABERTA = 30
ESTADO = av.ARQUIVO_TELA
TECLAS = {"voltar": 4, "inicio": 3, "apagar": 67, "enter": 66, "apps": 187}
LIMITE_COORDENADA = 5000
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


def montar_app():
    app = web.Application(client_max_size=64 * 1024)
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
                f"rolar. O campo de texto embaixo digita no Android.\n"
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
        gravar_estado("fechada")
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
  #tela { display: block; width: 100%; max-width: 480px; margin: 0 auto; touch-action: none;
          user-select: none; -webkit-user-select: none; }
  .barra { display: flex; gap: 6px; max-width: 480px; margin: 6px auto; padding: 0 8px; box-sizing: border-box; }
  .barra button, .barra input { flex: 1; padding: 12px 6px; font-size: 16px; border-radius: 8px;
          border: 0; background: var(--botao); color: var(--texto); }
  .barra input { flex: 3; background: #fff; color: #000; }
  #aviso { text-align: center; font-size: 13px; opacity: .7; padding: 4px 8px; }
</style></head><body>
<img id="tela" alt="Tela do Android">
<div class="barra"><input id="texto" placeholder="Texto para digitar" autocomplete="off">
  <button onclick="digitar()">Digitar</button></div>
<div class="barra"><button onclick="tecla('voltar')">◀ Voltar</button>
  <button onclick="tecla('inicio')">● Início</button><button onclick="tecla('apagar')">⌫ Apagar</button>
  <button onclick="tecla('enter')">↵ Enter</button></div>
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
function terminar() {
  enviar({ tipo: "fim" });
  document.getElementById("aviso").textContent = "Tela fechada. Pode sair desta página.";
}
atualizar();
</script></body></html>
"""


if __name__ == "__main__":
    asyncio.run(main())

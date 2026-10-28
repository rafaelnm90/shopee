"""
As 3 músicas de fundo dos vídeos sem som da Shopee Vídeo (midia/musica_*.m4a; escolha do
Rafael, P55: DECISOES.md, Shopee Vídeo), feitas do zero por síntese: nenhum pedaço de música
de outra pessoa entra, para não haver direito autoral. Ferramenta do Claude, fora dos robôs:
roda só para refazer ou mudar as músicas (precisa do numpy e do scipy, que não estão no
requirements.txt) e grava cada uma em AAC, no volume das redes (-16 LUFS, pelo loudnorm do
ffmpeg em duas passadas).

    python3 .claude/scripts/gerar_musicas.py midia
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from scipy import signal

SR = 44100


def nota(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def tempo(n):
    return np.arange(n) / SR


def passa_baixa(x, fc, ordem=2):
    b, a = signal.butter(ordem, min(fc, SR / 2 - 100) / (SR / 2))
    return signal.lfilter(b, a, x)


def passa_alta(x, fc, ordem=2):
    b, a = signal.butter(ordem, fc / (SR / 2), btype="high")
    return signal.lfilter(b, a, x)


def passa_banda(x, baixo, alto, ordem=2):
    b, a = signal.butter(ordem, [baixo / (SR / 2), min(alto, SR / 2 - 100) / (SR / 2)], btype="band")
    return signal.lfilter(b, a, x)


def envelope(n, ataque=0.005, soltura=0.03):
    """Sobe em `ataque` s e desce nos últimos `soltura` s (evita estalos)."""
    env = np.ones(n)
    a, r = max(1, int(ataque * SR)), max(1, int(soltura * SR))
    env[:a] = np.linspace(0, 1, a)
    env[-r:] *= np.linspace(1, 0, r)
    return env


# --- Instrumentos (mono) ---

class Sons:
    def __init__(self, semente):
        self.rng = np.random.default_rng(semente)

    def ruido(self, n):
        return self.rng.uniform(-1, 1, n)

    def dedilhado(self, f, dur, brilho=0.6, sustento=0.996):
        """Corda dedilhada (Karplus-Strong): violão, ukulele, pluck."""
        n = int(dur * SR)
        atraso = max(2, int(round(SR / f - 0.5)))
        exc = passa_baixa(self.ruido(atraso), 1500 + 9000 * brilho)
        x = np.zeros(n)
        x[:atraso] = exc[:n]
        a = np.zeros(atraso + 2)
        a[0], a[atraso], a[atraso + 1] = 1.0, -sustento / 2, -sustento / 2
        y = signal.lfilter([1.0], a, x)
        return y * envelope(n, 0.001, 0.02) / (np.max(np.abs(y)) + 1e-9)

    def piano_eletrico(self, f, dur):
        """Piano elétrico por FM: o brilho do ataque some e fica o som redondo."""
        n = int(dur * SR)
        t = tempo(n)
        indice = 1.6 * np.exp(-t / 0.25) + 0.15
        som = np.sin(2 * np.pi * f * t + indice * np.sin(2 * np.pi * f * t))
        som += 0.12 * np.sin(2 * np.pi * f * 7.0 * t) * np.exp(-t / 0.03)
        return som * np.exp(-t / 1.4) * envelope(n, 0.004, 0.08)

    def colchao(self, f, dur, brilho=2200):
        """Pad: serras levemente desafinadas, entrada lenta, filtradas."""
        n = int(dur * SR)
        t = tempo(n)
        som = np.zeros(n)
        for desvio in (-0.12, 0.0, 0.11):
            fd = f * 2 ** (desvio / 12)
            fase = self.rng.uniform(0, 2 * np.pi)
            for k in range(1, 18):
                if fd * k > 9000:
                    break
                som += np.sin(2 * np.pi * fd * k * t + fase * k) / k
        som = passa_baixa(som / 3, brilho)
        return som * envelope(n, min(0.35, dur / 3), min(0.4, dur / 3))

    def baixo(self, f, dur, duro=0.0):
        n = int(dur * SR)
        t = tempo(n)
        som = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + duro * 0.25 * np.sin(6 * np.pi * f * t)
        return np.tanh(1.3 * som) * (0.75 + 0.25 * np.exp(-t / 0.08)) * envelope(n, 0.004, 0.03)

    def marimba(self, f, dur):
        n = int(dur * SR)
        t = tempo(n)
        som = (np.sin(2 * np.pi * f * t) * np.exp(-t / 0.45)
               + 0.35 * np.sin(2 * np.pi * f * 3.93 * t) * np.exp(-t / 0.07)
               + 0.12 * np.sin(2 * np.pi * f * 9.2 * t) * np.exp(-t / 0.02))
        return som * envelope(n, 0.002, 0.03)

    def assobio(self, f, dur):
        """Assobio/flauta: seno com vibrato que entra devagar e um pouco de sopro."""
        n = int(dur * SR)
        t = tempo(n)
        vibrato = 1 + 0.004 * np.sin(2 * np.pi * 5.2 * t) * np.clip(t / 0.25, 0, 1)
        fase = 2 * np.pi * np.cumsum(f * vibrato) / SR
        sopro = passa_banda(self.ruido(n), f * 0.9, f * 1.2) * 0.12
        return (np.sin(fase) + 0.08 * np.sin(2 * fase) + sopro) * envelope(n, 0.04, 0.06)

    # --- Bateria ---

    def bumbo(self, forca=1.0):
        n = int(0.45 * SR)
        t = tempo(n)
        f = 46 + 120 * np.exp(-t / 0.035)
        som = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.22)
        clique = passa_alta(self.ruido(n), 3000) * np.exp(-t / 0.003) * 0.3
        return np.tanh(1.5 * forca * (som + clique)) * envelope(n, 0.0005, 0.02)

    def caixa(self, suave=False):
        n = int(0.3 * SR)
        t = tempo(n)
        tom = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05) * 0.6
        esteira = passa_banda(self.ruido(n), 1200, 7000 if not suave else 3500) * np.exp(-t / (0.11 if not suave else 0.08))
        return (tom + esteira) * envelope(n, 0.0005, 0.02)

    def palmas(self):
        n = int(0.35 * SR)
        t = tempo(n)
        ruido = passa_banda(self.ruido(n), 900, 5200)
        env = np.zeros(n)
        for inicio in (0.0, 0.011, 0.023):
            i = int(inicio * SR)
            env[i:] += np.exp(-(t[: n - i]) / 0.006)
        i = int(0.03 * SR)
        env[i:] += 0.7 * np.exp(-(t[: n - i]) / 0.11)
        return ruido * env * envelope(n, 0.0005, 0.02)

    def chimbal(self, aberto=False):
        n = int((0.3 if aberto else 0.08) * SR)
        t = tempo(n)
        som = passa_alta(self.ruido(n), 7000) * np.exp(-t / (0.12 if aberto else 0.022))
        return som * envelope(n, 0.0005, 0.01)

    def chocalho(self):
        n = int(0.09 * SR)
        t = tempo(n)
        env = np.sin(np.pi * np.clip(t / 0.09, 0, 1)) ** 2
        return passa_banda(self.ruido(n), 4500, 11000) * env

    def estalo(self):
        n = int(0.12 * SR)
        t = tempo(n)
        som = passa_banda(self.ruido(n), 1800, 6000) * np.exp(-t / 0.012)
        som += 0.3 * np.sin(2 * np.pi * 2100 * t) * np.exp(-t / 0.008)
        return som * envelope(n, 0.0003, 0.01)


# --- Mesa de mixagem ---

class Faixa:
    """Um instrumento ou grupo na mixagem: sons postos no tempo, com pan e volume."""

    def __init__(self, segundos):
        self.buf = np.zeros((2, int((segundos + 4) * SR)))

    def por(self, som, inicio, pan=0.0, ganho=1.0):
        i = int(round(inicio * SR))
        if i >= self.buf.shape[1]:
            return
        n = min(len(som), self.buf.shape[1] - i)
        angulo = (pan + 1) * np.pi / 4
        self.buf[0, i:i + n] += som[:n] * ganho * np.cos(angulo) * np.sqrt(2)
        self.buf[1, i:i + n] += som[:n] * ganho * np.sin(angulo) * np.sqrt(2)


def reverb(estereo, segundos=1.6, cauda=0.35, semente=7):
    rng = np.random.default_rng(semente)
    n = int(segundos * SR)
    t = tempo(n)
    saida = np.zeros_like(estereo)
    for canal in range(2):
        ir = passa_baixa(rng.normal(0, 1, n), 5500) * np.exp(-t / cauda)
        ir[: int(0.012 * SR)] = 0
        ir /= np.sqrt(np.sum(ir ** 2))
        saida[canal] = signal.fftconvolve(estereo[canal], ir)[: estereo.shape[1]]
    return saida


def mixar(faixas, envios, duracao, abafar=None, presenca=0.6):
    """
    faixas: {nome: Faixa}; envios: {nome: quanto vai ao reverb}; abafar: (envelope do bumbo,
    [nomes que abaixam com ele]) para o "bombeado" das músicas dançantes.
    """
    total = np.zeros_like(next(iter(faixas.values())).buf)
    envio = np.zeros_like(total)
    for nome, faixa in faixas.items():
        buf = faixa.buf
        if abafar and nome in abafar[1]:
            buf = buf * abafar[0]
        total += buf
        envio += buf * envios.get(nome, 0.0)
    total += reverb(envio)
    total = np.stack([passa_alta(c, 40) + presenca * passa_alta(c, 2500) for c in total])
    total = total[:, : int(duracao * SR)]
    # Fim suave: os últimos 1,5 s descem até o silêncio.
    r = int(1.5 * SR)
    total[:, -r:] *= np.linspace(1, 0, r) ** 1.5
    total /= np.max(np.abs(total)) + 1e-9
    return np.tanh(1.4 * total) / np.tanh(1.4)


def gravar_wav(caminho, estereo):
    import wave
    dados = (np.clip(estereo.T, -1, 1) * 32000).astype("<i2")
    with wave.open(caminho, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(dados.tobytes())


def acorde(raiz, tipo):
    intervalos = {"maior": (0, 4, 7), "menor": (0, 3, 7), "maj7": (0, 4, 7, 11), "m7": (0, 3, 7, 10),
                  "7": (0, 4, 7, 10)}[tipo]
    return [raiz + i for i in intervalos]


# --- 1. Animada: pop dançante, 118 BPM, Lá menor / Dó maior ---

def animada():
    s = Sons(11)
    bpm = 118
    batida = 60 / bpm
    compassos = 32
    duracao = compassos * 4 * batida
    f = {n: Faixa(duracao) for n in ("bumbo", "palmas", "chimbal", "baixo", "colchao", "arpejo", "melodia")}
    progressao = [(57, "menor"), (53, "maior"), (48, "maior"), (55, "maior")]  # Am F C G
    melodia = [  # (início em colcheias no compasso, nota MIDI, duração em colcheias), 4 compassos
        [(0, 76, 1.5), (2, 76, 1), (3, 74, 1), (4, 72, 2), (6, 69, 2)],
        [(0, 72, 1.5), (2, 72, 1), (3, 74, 1), (4, 76, 2), (6, 72, 2)],
        [(0, 79, 1.5), (2, 76, 1), (4, 74, 1), (5, 72, 1), (6, 74, 2)],
        [(0, 74, 1.5), (2, 71, 2), (4, 67, 3)],
    ]
    envelope_bumbo = np.ones(f["bumbo"].buf.shape[1])
    for c in range(compassos):
        inicio = c * 4 * batida
        raiz, tipo = progressao[c % 4]
        notas = acorde(raiz + 12, tipo)
        intro = c < 4
        pausa = 20 <= c < 24
        # Pad: o acorde inteiro, mais aberto depois da introdução.
        for n_ in notas:
            f["colchao"].por(s.colchao(nota(n_), 4 * batida + 0.3, 1400 if intro else 3800), inicio,
                             pan=-0.3 + 0.3 * notas.index(n_), ganho=0.15)
        # Arpejo em semicolcheias com o pluck.
        padrao = [0, 1, 2, 1, 2, 3, 2, 1] * 2
        tons = notas + [notas[0] + 12]
        for i, p in enumerate(padrao):
            if intro and i % 2:
                continue
            f["arpejo"].por(s.dedilhado(nota(tons[p] + 12), 0.35, brilho=0.4 if intro else 0.7, sustento=0.99),
                            inicio + i * batida / 4, pan=0.35 if i % 2 else -0.35, ganho=0.3)
        if intro:
            continue
        # Baixo em colcheias: raiz, raiz, oitava...
        for i in range(8):
            altura = raiz - 12 + (12 if i in (3, 7) else 0)
            if not pausa:
                f["baixo"].por(s.baixo(nota(altura), batida / 2 * 0.9, 0.8), inicio + i * batida / 2, ganho=0.28)
        if not pausa:
            for b in range(4):
                t0 = inicio + b * batida
                f["bumbo"].por(s.bumbo(), t0, ganho=0.6)
                i0 = int(t0 * SR)
                dur = int(0.25 * SR)
                envelope_bumbo[i0:i0 + dur] = np.minimum(envelope_bumbo[i0:i0 + dur],
                                                         1 - 0.55 * np.exp(-tempo(dur)[: len(envelope_bumbo[i0:i0 + dur])] / 0.08))
                f["chimbal"].por(s.chimbal(aberto=(b == 3)), t0 + batida / 2, pan=0.2, ganho=0.34)
                f["chimbal"].por(s.chimbal(), t0 + batida * 0.75, pan=0.25, ganho=0.13)
        for b in (1, 3):
            f["palmas"].por(s.palmas(), inicio + b * batida, ganho=0.5)
        # Melodia de marimba nas partes cheias, a partir do compasso 9.
        if c >= 8:
            for col, n_, d in melodia[c % 4]:
                f["melodia"].por(s.marimba(nota(n_), d * batida / 2 + 0.3), inicio + col * batida / 2,
                                 pan=0.1, ganho=0.46)
                f["melodia"].por(s.marimba(nota(n_ + 12), d * batida / 2 + 0.2), inicio + col * batida / 2 + 0.006,
                                 pan=-0.1, ganho=0.08)
    estereo = mixar(f, {"palmas": 0.25, "colchao": 0.3, "arpejo": 0.25, "melodia": 0.3, "chimbal": 0.05},
                    duracao, abafar=(envelope_bumbo, {"colchao", "baixo", "arpejo"}))
    return estereo


# --- 2. Calma: lo-fi, 78 BPM com balanço, Dó maior ---

def calma():
    s = Sons(23)
    bpm = 78
    batida = 60 / bpm
    compassos = 20
    duracao = compassos * 4 * batida
    f = {n: Faixa(duracao) for n in ("bumbo", "caixa", "chimbal", "baixo", "piano", "melodia", "disco")}
    progressao = [(53, "maj7"), (52, "m7"), (50, "m7"), (48, "maj7")]  # Fmaj7 Em7 Dm7 Cmaj7
    balanco = 0.62  # a colcheia de contratempo cai em 62% da batida

    def colcheia(i):
        return (i // 2) * batida + (balanco * batida if i % 2 else 0)

    melodia = [
        [(0, 76, 3), (4, 74, 1), (5, 72, 3)],
        [(0, 71, 2), (2, 72, 1), (3, 74, 4)],
        [(1, 77, 2), (3, 76, 1), (4, 74, 2), (6, 72, 2)],
        [(0, 71, 3), (4, 67, 4)],
    ]
    for c in range(compassos):
        inicio = c * 4 * batida
        raiz, tipo = progressao[c % 4]
        notas = acorde(raiz + 12, tipo)
        # Piano elétrico: no 1 e no contratempo do 2, como num lo-fi.
        for golpe, dur in ((0, 1.6), (3, 2.2)):
            for k, n_ in enumerate(notas):
                f["piano"].por(s.piano_eletrico(nota(n_), dur * batida), inicio + colcheia(golpe) + k * 0.012,
                               pan=-0.25 + 0.15 * k, ganho=0.2)
        borda = c < 2 or c >= compassos - 2
        if not borda:
            f["baixo"].por(s.baixo(nota(raiz - 12), 1.7 * batida, 0.5), inicio, ganho=0.3)
            f["baixo"].por(s.baixo(nota(raiz - 12 + 7), 0.9 * batida, 0.5), inicio + colcheia(5), ganho=0.22)
            f["bumbo"].por(s.bumbo(0.7), inicio, ganho=0.75)
            f["bumbo"].por(s.bumbo(0.6), inicio + colcheia(5), ganho=0.55)
            for b in (1, 3):
                f["caixa"].por(passa_baixa(s.caixa(suave=True), 4000), inicio + b * batida + 0.01, ganho=0.4)
            for i in range(8):
                f["chimbal"].por(s.chimbal(), inicio + colcheia(i), pan=0.3, ganho=0.2 if i % 2 else 0.3)
        if 6 <= c < compassos - 2:
            for col, n_, d in melodia[c % 4]:
                f["melodia"].por(passa_baixa(s.assobio(nota(n_), d * batida / 2 * 1.05), 6000),
                                 inicio + colcheia(col), pan=0.15, ganho=0.24)
    # Chiado de disco bem baixinho: estalinhos esparsos.
    n = f["disco"].buf.shape[1]
    estalos = np.zeros(n)
    posicoes = s.rng.integers(0, n, int(duracao * 6))
    estalos[posicoes] = s.rng.uniform(-1, 1, len(posicoes))
    chiado = passa_baixa(estalos, 2500) * 1.5 + passa_banda(s.ruido(n), 1000, 6000) * 0.006
    f["disco"].buf[0] += chiado
    f["disco"].buf[1] += np.roll(chiado, 37)
    estereo = mixar(f, {"piano": 0.35, "melodia": 0.45, "caixa": 0.2, "chimbal": 0.05}, duracao, presenca=1.2)
    # O lo-fi é mais abafado: tira o brilho de cima.
    return np.stack([passa_baixa(canal, 12000) for canal in estereo])


# --- 3. Divertida: ukulele e assobio, 124 BPM, Sol maior ---

def divertida():
    s = Sons(37)
    bpm = 124
    batida = 60 / bpm
    compassos = 32
    duracao = compassos * 4 * batida
    f = {n: Faixa(duracao) for n in ("bumbo", "palmas", "estalo", "chocalho", "baixo", "ukulele", "melodia", "marimba")}
    progressao = [(55, "maior"), (52, "menor"), (48, "maior"), (50, "maior")]  # G Em C D
    melodia = [
        [(0, 74, 1), (2, 71, 1), (3, 67, 1), (5, 71, 1), (6, 74, 2)],
        [(0, 76, 1), (2, 74, 1), (3, 71, 1), (4, 67, 3)],
        [(0, 72, 1), (1, 76, 1), (2, 79, 2), (4, 76, 1), (6, 72, 2)],
        [(0, 74, 1), (2, 78, 1), (4, 81, 2), (6, 78, 1), (7, 74, 1)],
    ]
    # Batida do ukulele: (colcheia, para baixo?)
    batida_uke = [(0, True), (2, True), (3, False), (5, False), (6, True), (7, False)]
    for c in range(compassos):
        inicio = c * 4 * batida
        raiz, tipo = progressao[c % 4]
        cordas = sorted(acorde(raiz + 12, tipo) + [raiz + 24])
        for col, desce in batida_uke:
            ordem = cordas if desce else cordas[::-1]
            for k, n_ in enumerate(ordem):
                f["ukulele"].por(s.dedilhado(nota(n_), 0.45, brilho=0.8 if desce else 0.6, sustento=0.985),
                                 inicio + col * batida / 2 + k * 0.011, pan=-0.2, ganho=0.22 if desce else 0.15)
        intro = c < 4
        pausa = 20 <= c < 24
        if not intro and not pausa:
            # Baixo saltitante: raiz no 1, quinta no 3, nota de passagem no fim.
            for col, salto, d in ((0, 0, 0.8), (3, 7, 0.4), (4, 7, 0.8), (7, 12, 0.4)):
                f["baixo"].por(s.baixo(nota(raiz - 12 + salto), d * batida / 2 * 1.6, 0.3),
                               inicio + col * batida / 2, ganho=0.3)
            for b in (0, 2):
                f["bumbo"].por(s.bumbo(0.8), inicio + b * batida, ganho=0.5)
            for i in range(16):
                f["chocalho"].por(s.chocalho(), inicio + i * batida / 4, pan=0.4, ganho=0.16 if i % 2 else 0.24)
        if not intro:
            for b in (1, 3):
                f["palmas"].por(s.palmas(), inicio + b * batida, ganho=0.35)
                f["estalo"].por(s.estalo(), inicio + b * batida + batida / 2, pan=-0.4, ganho=0.25)
        if c >= 8 and not (24 <= c < 28):
            for col, n_, d in melodia[c % 4]:
                f["melodia"].por(s.assobio(nota(n_), d * batida / 2 * 0.85), inicio + col * batida / 2,
                                 pan=0.15, ganho=0.3)
        if c >= 16:
            # A marimba responde a melodia no contratempo, uma oitava abaixo.
            for col, n_, d in melodia[c % 4][::2]:
                f["marimba"].por(s.marimba(nota(n_ - 12), 0.5), inicio + col * batida / 2 + batida / 2,
                                 pan=-0.3, ganho=0.26)
    return mixar(f, {"palmas": 0.25, "ukulele": 0.2, "melodia": 0.35, "marimba": 0.3, "estalo": 0.2}, duracao)


def gravar_m4a(caminho, estereo):
    """A música no volume das redes (-16 LUFS, pico até -1,5 dB), em AAC."""
    with tempfile.TemporaryDirectory() as pasta:
        wav = os.path.join(pasta, "musica.wav")
        gravar_wav(wav, estereo)
        alvo = "I=-16:TP=-1.5:LRA=11"
        medida = subprocess.run(["ffmpeg", "-hide_banner", "-i", wav, "-af", f"loudnorm={alvo}:print_format=json",
                                 "-f", "null", "-"], capture_output=True, text=True).stderr
        m = json.loads(medida[medida.rindex("{"):])
        filtro = (f"loudnorm={alvo}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                  f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
                  f"offset={m['target_offset']}:linear=true")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-af", filtro, "-ar", str(SR), "-c:a", "aac",
                        "-b:a", "160k", caminho], check=True)


if __name__ == "__main__":
    pasta = sys.argv[1]
    for nome, gerar in (("animada", animada), ("calma", calma), ("divertida", divertida)):
        estereo = gerar()
        gravar_m4a(os.path.join(pasta, f"musica_{nome}.m4a"), estereo)
        print(nome, round(estereo.shape[1] / SR, 1), "s")

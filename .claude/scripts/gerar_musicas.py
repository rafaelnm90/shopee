"""
As músicas de fundo dos vídeos sem som da Shopee Vídeo (midia/musica_*.m4a), feitas do zero por
síntese: nenhum pedaço de música de outra pessoa entra, para não haver direito autoral. As 3
primeiras (animada, calma e divertida) são da P55; as 8 seguintes, cada uma com o clima de outros
tipos de vídeo, da P242 1 (escolhas do Rafael: DECISOES.md, Shopee Vídeo). Ferramenta do Claude,
fora dos robôs: roda só para refazer ou mudar as músicas (precisa do numpy e do scipy, que não
estão no requirements.txt) e grava cada uma em AAC, no volume das redes (-16 LUFS, pelo loudnorm
do ffmpeg em duas passadas). Sem nomes, refaz todas; com eles (separados por vírgula), só essas.

    python3 .claude/scripts/gerar_musicas.py midia [romantica,fofa]
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


def serra_aditiva(f, t, teto=9000.0):
    """Serra sem serrilhado: a soma dos harmônicos até o teto."""
    total = np.zeros_like(t)
    k = 1
    while f * k < teto and k <= 90:
        total += np.sin(2 * np.pi * f * k * t) / k
        k += 1
    return total * (2 / np.pi)


def quadrada_aditiva(f, t, teto=9000.0):
    total = np.zeros_like(t)
    k = 1
    while f * k < teto and k <= 90:
        total += np.sin(2 * np.pi * f * k * t) / k
        k += 2
    return total * (4 / np.pi)


def filtro_que_fecha(x, de, ate, queda, bloco=256, ordem=2):
    """Passa-baixa que vai de `de` a `ate` Hz (exponencial, em `queda` s), em blocos."""
    saida = np.zeros_like(x)
    zi = None
    for i in range(0, len(x), bloco):
        fc = ate + (de - ate) * np.exp(-(i / SR) / queda)
        b, a = signal.butter(ordem, min(max(fc, 40.0), SR / 2 - 200) / (SR / 2))
        if zi is None:
            zi = np.zeros(max(len(a), len(b)) - 1)
        y, zi = signal.lfilter(b, a, x[i:i + bloco], zi=zi)
        saida[i:i + bloco] = y
    return saida


def filtro_que_abre(x, de, ate, bloco=512, ordem=2, alta=False):
    """Filtro que anda de `de` a `ate` Hz ao longo do som (para a subida antes da virada)."""
    saida = np.zeros_like(x)
    zi = None
    n = len(x)
    for i in range(0, n, bloco):
        fc = de * (ate / de) ** (i / max(1, n))
        b, a = signal.butter(ordem, min(fc, SR / 2 - 200) / (SR / 2), btype="high" if alta else "low")
        if zi is None:
            zi = np.zeros(max(len(a), len(b)) - 1)
        y, zi = signal.lfilter(b, a, x[i:i + bloco], zi=zi)
        saida[i:i + bloco] = y
    return saida


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

    # --- Instrumentos das músicas novas (P242 1) ---

    def piano(self, f, dur, forca=0.8):
        """Piano: parciais um pouco desafinados para cima, os agudos somem antes; o martelo no ataque."""
        n = int(dur * SR)
        t = tempo(n)
        som = np.zeros(n)
        for k in range(1, 10):
            fk = f * k * np.sqrt(1 + 0.00035 * k * k)
            if fk > 11000:
                break
            amp = (1.0 / k ** 1.15) * (0.55 + 0.45 * forca) * (1 + 0.6 * forca * (k > 3))
            decai = 2.2 / (1 + 0.45 * (k - 1)) * (262 / max(f, 80)) ** 0.35
            som += amp * np.sin(2 * np.pi * fk * t + self.rng.uniform(0, 2 * np.pi)) * np.exp(-t / decai)
        martelo = passa_banda(self.ruido(n), 1200, 4500) * np.exp(-t / 0.005) * 0.08 * forca
        return (som + martelo) * envelope(n, 0.002, 0.12)

    def sino(self, f, dur, brilho=1.0):
        """Glockenspiel ou caixinha de música: os parciais de uma barra de metal, os altos somem logo."""
        n = int(dur * SR)
        t = tempo(n)
        som = np.zeros(n)
        for razao, amp, decai in ((1.0, 1.0, 1.1), (2.76, 0.42 * brilho, 0.32), (5.40, 0.22 * brilho, 0.11),
                                  (8.93, 0.10 * brilho, 0.045)):
            if f * razao < 17000:
                som += amp * np.sin(2 * np.pi * f * razao * t) * np.exp(-t / decai)
        return som * envelope(n, 0.0008, 0.06)

    def vibrafone(self, f, dur):
        n = int(dur * SR)
        t = tempo(n)
        tremolo = 1 - 0.22 * (1 + np.sin(2 * np.pi * 5.2 * t)) / 2
        som = (np.sin(2 * np.pi * f * t) + 0.22 * np.sin(2 * np.pi * f * 4.0 * t) * np.exp(-t / 0.25)
               + 0.06 * np.sin(2 * np.pi * f * 10.0 * t) * np.exp(-t / 0.03))
        return som * np.exp(-t / 1.5) * tremolo * envelope(n, 0.002, 0.1)

    def steel(self, f, dur):
        """Tambor de aço (steel drum) por FM: o brilho do ataque e o corpo com a oitava e a décima segunda."""
        n = int(dur * SR)
        t = tempo(n)
        indice = 1.8 * np.exp(-t / 0.09) + 0.35
        som = np.sin(2 * np.pi * f * t + indice * np.sin(2 * np.pi * 2 * f * t))
        som += 0.35 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.3)
        som += 0.18 * np.sin(2 * np.pi * 3 * f * t) * np.exp(-t / 0.15)
        return som * np.exp(-t / 0.55) * envelope(n, 0.002, 0.06)

    def serra(self, f, dur, de=5000, ate=900, queda=0.15, vozes=3, desafino=0.10, quadrada=False):
        """Sintetizador de serra (ou quadrada) com vozes desafinadas e o filtro que fecha."""
        n = int(dur * SR)
        t = tempo(n)
        som = np.zeros(n)
        for v in range(vozes):
            d = (v - (vozes - 1) / 2) * desafino
            fd = f * 2 ** (d / 12)
            fase = self.rng.uniform(0, 1 / fd)
            som += (quadrada_aditiva if quadrada else serra_aditiva)(fd, t + fase, min(12000, max(3000, de * 1.2)))
        som /= vozes
        return filtro_que_fecha(som, de, ate, queda) * envelope(n, 0.003, 0.03)

    def sub(self, f, dur):
        """Baixo 808: seno que cai um pouco no ataque, com saturação leve."""
        n = int(dur * SR)
        t = tempo(n)
        freq = f * (1 + 0.6 * np.exp(-t / 0.03))
        som = np.sin(2 * np.pi * np.cumsum(freq) / SR)
        return np.tanh(1.6 * som) * np.exp(-t / 0.8) * envelope(n, 0.002, 0.05)

    def escovinha(self, longa=False):
        """A vassourinha na caixa (jazz): um chiado que sobe e desce."""
        n = int((0.32 if longa else 0.2) * SR)
        t = tempo(n)
        env = (1 - np.exp(-t / 0.008)) * np.exp(-t / (0.11 if longa else 0.055))
        return passa_banda(self.ruido(n), 1800, 9500) * env

    def prato(self, forte=False):
        """Prato de condução (ou de ataque, forte): ruído agudo com uns parciais de metal."""
        n = int((1.6 if forte else 0.55) * SR)
        t = tempo(n)
        metal = sum(np.sin(2 * np.pi * fr * t + self.rng.uniform(0, 6.28)) for fr in (3150, 4270, 5830, 7110, 8670))
        som = (passa_alta(self.ruido(n), 6500) * 0.7 + metal * 0.06) * np.exp(-t / (0.6 if forte else 0.22))
        return som * envelope(n, 0.0005, 0.05)

    def subida(self, dur):
        """O chiado que sobe antes da virada."""
        n = int(dur * SR)
        t = tempo(n)
        return filtro_que_abre(self.ruido(n), 300, 9000) * (t / dur) ** 2

    def pizzicato(self, f, dur):
        return self.dedilhado(f, dur, brilho=0.35, sustento=0.94)

    def violao(self, f, dur, brilho=0.45):
        return passa_baixa(self.dedilhado(f, dur, brilho=brilho, sustento=0.9965), 6500)

    def madeira(self, agudo=True):
        """O tique-taque do relógio (bloco de madeira)."""
        n = int(0.06 * SR)
        t = tempo(n)
        f = 1900 if agudo else 1500
        som = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.012)
        som += 0.3 * passa_banda(self.ruido(n), 2000, 6000) * np.exp(-t / 0.004)
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


def bombear(env, t0, profundidade=0.55, solta=0.09):
    """O 'bombeado': o que está em env abaixa em cada batida do bumbo e volta em `solta` s."""
    i0 = int(t0 * SR)
    dur = int(0.3 * SR)
    trecho = env[i0:i0 + dur]
    env[i0:i0 + dur] = np.minimum(trecho, 1 - profundidade * np.exp(-tempo(dur)[:len(trecho)] / solta))


# --- 4. Romântica: piano e cordas, 72 BPM, Ré maior ---

def romantica():
    s = Sons(41)
    batida = 60 / 72
    compassos = 18
    duracao = compassos * 4 * batida
    f = {n: Faixa(duracao) for n in ("piano", "esquerda", "cordas", "baixo", "melodia", "estalo", "sino")}
    acordes = [[62, 66, 69, 73], [59, 62, 66, 69], [55, 59, 62, 66], [57, 62, 64, 69]]  # Dmaj7 Bm7 Gmaj7 Asus
    acorde_a = [57, 61, 64, 69]                                                         # A (o sus resolve)
    raizes = [38, 35, 43, 45]
    melodia_a = [[(0, 78, 3), (3, 76, 1), (4, 74, 2), (6, 73, 2)],
                 [(0, 74, 3), (3, 73, 1), (4, 71, 2), (6, 69, 2)],
                 [(0, 71, 2), (2, 74, 2), (4, 78, 3), (7, 76, 1)],
                 [(0, 76, 4), (4, 73, 2), (6, 76, 2)]]
    melodia_b = [[(0, 81, 3), (3, 78, 1), (4, 76, 2), (6, 78, 2)],
                 [(0, 74, 2), (2, 76, 1), (3, 78, 3), (6, 74, 2)],
                 [(0, 79, 3), (3, 78, 1), (4, 76, 2), (6, 74, 2)],
                 [(0, 73, 2), (2, 76, 2), (4, 81, 4)]]
    ordem = [0, 1, 2, 3, 2, 3, 1, 2]
    for c in range(compassos):
        inicio = c * 4 * batida
        final = c >= 16
        k = 0 if final else c % 4
        notas = acordes[k]
        # O sus4 do Lá resolve na metade do compasso.
        for i, p in enumerate(ordem):
            if final and i >= 4:
                break
            tons = acorde_a if (k == 3 and i >= 4) else notas
            forca = 0.55 + (0.15 if i == 0 else 0) + (0.1 if 12 <= c < 16 else 0)
            f["piano"].por(s.piano(nota(tons[p]), 1.6 * batida, forca), inicio + i * batida / 2,
                           pan=-0.2 + 0.12 * p, ganho=0.30)
        raiz = raizes[k]
        f["esquerda"].por(s.piano(nota(raiz + 12), 4.2 * batida, 0.5), inicio, pan=-0.3, ganho=0.30)
        if not final:
            f["esquerda"].por(s.piano(nota(raiz + 19), 2.2 * batida, 0.4), inicio + 2 * batida, pan=-0.3, ganho=0.22)
        if 4 <= c < 17:
            for j, n_ in enumerate(notas[:3]):
                f["cordas"].por(s.colchao(nota(n_ - 12 if j else n_), 4 * batida + 0.4, 1500 if c < 12 else 2300),
                                inicio, pan=-0.4 + 0.4 * j, ganho=0.09 if c < 12 else 0.12)
            f["baixo"].por(s.baixo(nota(raiz), 3.6 * batida, 0.0), inicio, ganho=0.20)
        if 4 <= c < 12:
            for col, n_, d in melodia_a[c % 4]:
                f["melodia"].por(s.piano(nota(n_), d * batida / 2 + 0.6, 0.75), inicio + col * batida / 2,
                                 pan=0.15, ganho=0.36)
        elif 12 <= c < 16:
            for col, n_, d in melodia_b[c % 4]:
                f["melodia"].por(s.piano(nota(n_), d * batida / 2 + 0.6, 0.85), inicio + col * batida / 2,
                                 pan=0.15, ganho=0.36)
                f["cordas"].por(s.colchao(nota(n_ - 12), d * batida / 2 + 0.3, 2600), inicio + col * batida / 2,
                                pan=0.3, ganho=0.05)
            for b in (1, 3):
                f["estalo"].por(s.estalo(), inicio + b * batida, pan=0.3, ganho=0.12)
            if c % 2 == 0:
                f["sino"].por(s.sino(nota(notas[1] + 24), 2.5, 0.6), inicio, pan=0.4, ganho=0.06)
        if c == 16:
            f["melodia"].por(s.piano(nota(78), 6 * batida, 0.6), inicio + 2 * batida, pan=0.15, ganho=0.30)
            f["sino"].por(s.sino(nota(86), 4.0, 0.5), inicio + 2 * batida, pan=0.4, ganho=0.06)
    return mixar(f, {"piano": 0.35, "esquerda": 0.3, "cordas": 0.45, "melodia": 0.4, "sino": 0.5, "estalo": 0.2},
                 duracao, presenca=0.5)


# --- 5. Elegante: lounge com piano elétrico, contrabaixo andando e vassourinha, 92 BPM com balanço, Fá maior ---

def elegante():
    s = Sons(53)
    batida = 60 / 92
    compassos = 24
    duracao = compassos * 4 * batida
    balanco = 0.64
    f = {n: Faixa(duracao) for n in ("rhodes", "baixo", "bumbo", "escova", "prato", "vibra")}

    def colcheia(i):
        return (i // 2) * batida + (balanco * batida if i % 2 else 0)

    vozes = [[58, 62, 65, 69], [58, 62, 64, 69], [57, 60, 64, 67], [53, 57, 60, 64]]   # Gm9 C13 Fmaj9 Dm9
    andando = [[43, 45, 46, 47], [48, 52, 55, 54], [53, 52, 50, 49], [50, 48, 45, 44]]
    toques = [[(0, 0.7), (3, 1.5)], [(2, 0.6), (5, 1.0), (7, 0.6)]]
    frase_a = [[(0, 74, 2), (2, 77, 1), (3, 76, 1), (4, 74, 3)],
               [(1, 70, 1), (2, 72, 1), (3, 74, 1), (4, 76, 3)],
               [(0, 77, 2), (2, 76, 1), (3, 72, 1), (4, 69, 4)],
               [(1, 72, 1), (2, 74, 2), (4, 77, 2), (6, 76, 2)]]
    frase_b = [[(0, 81, 3), (3, 79, 1), (4, 77, 2), (6, 74, 2)],
               [(0, 76, 2), (2, 74, 1), (3, 70, 1), (4, 69, 4)],
               [(0, 72, 1), (1, 76, 1), (2, 79, 2), (4, 77, 3)],
               [(0, 76, 4), (5, 74, 1), (6, 72, 2)]]
    for c in range(compassos):
        inicio = c * 4 * batida
        k = c % 4
        for col, dur in toques[(c // 2) % 2] if c < compassos - 1 else [(0, 3.5)]:
            for j, n_ in enumerate(vozes[k]):
                f["rhodes"].por(s.piano_eletrico(nota(n_), dur * batida), inicio + colcheia(col) + j * 0.008,
                                pan=-0.25 + 0.15 * j, ganho=0.15)
        if c >= 2:
            for b, n_ in enumerate(andando[k] if c < compassos - 1 else [41]):
                f["baixo"].por(s.baixo(nota(n_), 0.92 * batida if c < compassos - 1 else 3.5 * batida, 0.15),
                               inicio + b * batida, ganho=0.30)
        if c >= 4 and c < compassos - 1:
            for b in (0, 2):
                f["bumbo"].por(s.bumbo(0.45), inicio + b * batida, ganho=0.30)
            for b in (1, 3):
                f["escova"].por(s.escovinha(longa=True), inicio + b * batida, pan=0.1, ganho=0.30)
            for i in (0, 2, 3, 4, 6, 7):
                f["prato"].por(s.prato(), inicio + colcheia(i), pan=0.35, ganho=0.05 if i % 2 else 0.08)
        frase = None
        if 8 <= c < 12 or 16 <= c < 20:
            frase = frase_a
        elif 12 <= c < 16:
            frase = frase_b
        if frase:
            for col, n_, d in frase[k]:
                f["vibra"].por(s.vibrafone(nota(n_), d * batida / 2 + 0.8), inicio + colcheia(col), pan=0.2, ganho=0.30)
    return mixar(f, {"rhodes": 0.3, "vibra": 0.4, "escova": 0.15, "prato": 0.15}, duracao, presenca=0.7)


# --- 6. Energia: eletrônica para cima, 128 BPM, Mi menor ---

def energia():
    s = Sons(67)
    batida = 60 / 128
    compassos = 32
    duracao = compassos * 4 * batida
    nomes = ("bumbo", "palmas", "chimbal", "caixa", "prato", "baixo", "colchao", "lead", "pluck", "subida")
    f = {n: Faixa(duracao) for n in nomes}
    acordes = [[64, 67, 71], [60, 64, 67], [62, 67, 71], [62, 66, 69]]  # Em C G D
    raizes = [40, 36, 43, 38]
    lead = [[(0, 76, 2), (3, 79, 2), (6, 83, 2), (8, 81, 4), (12, 79, 2), (14, 76, 2)],
            [(0, 76, 2), (3, 79, 2), (6, 84, 4), (10, 83, 2), (12, 79, 4)],
            [(0, 79, 2), (3, 83, 2), (6, 86, 2), (8, 83, 4), (12, 81, 4)],
            [(0, 81, 2), (3, 78, 2), (6, 74, 4), (10, 78, 2), (12, 81, 4)]]
    bombeado = np.ones(f["colchao"].buf.shape[1])
    semi = batida / 4
    for c in range(compassos):
        inicio = c * 4 * batida
        k = c % 4
        intro, sobe = c < 4, 4 <= c < 8
        queda1, pausa, queda2, fim = 8 <= c < 16, 16 <= c < 20, 20 <= c < 28, c >= 28
        cheio = queda1 or queda2
        brilho = 900 if intro else 1800 if sobe else 1500 if pausa else 4200
        for j, n_ in enumerate(acordes[k]):
            f["colchao"].por(s.colchao(nota(n_), 4 * batida + 0.2, brilho), inicio, pan=-0.4 + 0.4 * j,
                             ganho=0.13 if cheio else 0.10)
        if not intro and not pausa:
            for b in range(4):
                t0 = inicio + b * batida
                f["bumbo"].por(s.bumbo(1.1), t0, ganho=0.62)
                bombear(bombeado, t0)
        if intro or cheio or fim:
            for i in range(8):
                f["chimbal"].por(s.chimbal(aberto=(cheio and i % 2 == 1)), inicio + i * batida / 2, pan=0.25,
                                 ganho=(0.20 if i % 2 else 0.10) if cheio else 0.10)
        if cheio or fim:
            for b in (1, 3):
                f["palmas"].por(s.palmas(), inicio + b * batida, ganho=0.42)
        if sobe:
            passos = 8 if c < 6 else 16
            for i in range(passos):
                forca = 0.12 + 0.3 * ((c - 4) * passos + i) / (4 * 16)
                f["caixa"].por(s.caixa(), inicio + i * 4 * batida / passos, pan=-0.1, ganho=forca)
        if c in (7, 19):
            f["subida"].por(s.subida(4 * batida), inicio, ganho=0.25)
        if c in (8, 20):
            f["prato"].por(s.prato(forte=True), inicio, pan=0.1, ganho=0.30)
        if cheio or fim:
            for i in range(8):
                if i % 2 == 1:
                    f["baixo"].por(s.serra(nota(raizes[k]), 0.2, de=2600, ate=500, queda=0.07, vozes=2),
                                   inicio + i * batida / 2, ganho=0.36)
                    f["baixo"].por(s.sub(nota(raizes[k]), 0.2), inicio + i * batida / 2, ganho=0.22)
        if cheio:
            alto = 12 if queda2 and c >= 24 else 0
            for col, n_, d in lead[k]:
                f["lead"].por(s.serra(nota(n_ + alto), d * semi + 0.05, de=6500, ate=2400, queda=0.2, vozes=3),
                              inicio + col * semi, pan=0.05, ganho=0.17)
        if pausa:
            tons = acordes[k] + [acordes[k][0] + 12]
            for i in range(16):
                f["pluck"].por(s.serra(nota(tons[[0, 1, 2, 3, 2, 1, 2, 3][i % 8]] + 12), 0.14, de=5000, ate=700,
                                       queda=0.05, vozes=1), inicio + i * semi, pan=0.4 if i % 2 else -0.4,
                               ganho=0.12)
    return mixar(f, {"palmas": 0.2, "colchao": 0.25, "lead": 0.3, "pluck": 0.35, "caixa": 0.15},
                 duracao, abafar=(bombeado, {"colchao", "baixo", "pluck"}))


# --- 7. Tecnologia: sintetizadores em sequência, 112 BPM, Lá menor ---

def tecnologia():
    s = Sons(79)
    batida = 60 / 112
    compassos = 28
    duracao = compassos * 4 * batida
    nomes = ("bumbo", "palmas", "chimbal", "sub", "colchao", "arpejo", "lead", "ping")
    f = {n: Faixa(duracao) for n in nomes}
    acordes = [[57, 60, 64], [53, 57, 60], [55, 60, 64], [55, 59, 62]]  # Am F C G
    raizes = [33, 29, 36, 31]
    lead = [[(0, 76, 3), (3, 74, 1), (4, 72, 2), (6, 69, 2)],
            [(0, 72, 2), (2, 74, 2), (4, 77, 3), (7, 76, 1)],
            [(0, 79, 3), (3, 77, 1), (4, 76, 2), (6, 72, 2)],
            [(0, 74, 4), (4, 71, 2), (6, 67, 2)]]
    bombeado = np.ones(f["colchao"].buf.shape[1])
    semi = batida / 4
    for c in range(compassos):
        inicio = c * 4 * batida
        k = c % 4
        intro, fim = c < 4, c >= 24
        for j, n_ in enumerate(acordes[k]):
            f["colchao"].por(s.colchao(nota(n_), 4 * batida + 0.2, 1400 if intro else 2600), inicio,
                             pan=-0.35 + 0.35 * j, ganho=0.10)
        tons = acordes[k] + [acordes[k][0] + 12, acordes[k][1] + 12]
        padrao = [0, 1, 2, 3, 1, 2, 3, 4]
        for i in range(16):
            de = 2500 + (2500 if not intro else 0) + 1500 * ((i % 4) == 0)
            f["arpejo"].por(s.serra(nota(tons[padrao[i % 8]] + 12), 0.16, de=de, ate=600, queda=0.05, vozes=1,
                                    quadrada=True), inicio + i * semi, pan=0.45 if i % 2 else -0.45, ganho=0.11)
        if not intro and not fim:
            for t0 in (0, 2.5 * batida):
                f["bumbo"].por(s.bumbo(0.9), inicio + t0, ganho=0.58)
                bombear(bombeado, inicio + t0, 0.45)
            for b in (1, 3):
                f["palmas"].por(s.palmas(), inicio + b * batida, ganho=0.36)
            for i in range(16):
                f["chimbal"].por(s.chimbal(), inicio + i * semi, pan=0.3, ganho=0.13 if i % 2 else 0.07)
            for col in (0, 3, 6):
                f["sub"].por(s.sub(nota(raizes[k] + 12), 0.9 * batida), inicio + col * batida / 2, ganho=0.34)
        if 12 <= c < 24:
            for col, n_, d in lead[k]:
                f["lead"].por(s.serra(nota(n_), d * batida / 2 + 0.05, de=3800, ate=1800, queda=0.3, vozes=2,
                                      desafino=0.06, quadrada=True), inicio + col * batida / 2, pan=0.05, ganho=0.15)
        if c % 4 == 0:
            for eco in range(3):
                f["ping"].por(s.sino(nota(93), 1.2, 0.8), inicio + eco * 1.5 * batida, pan=0.5 - 0.5 * eco,
                              ganho=0.07 * (0.55 ** eco))
    return mixar(f, {"palmas": 0.2, "colchao": 0.3, "arpejo": 0.3, "lead": 0.3, "ping": 0.6},
                 duracao, abafar=(bombeado, {"colchao", "arpejo"}))


# --- 8. Fofa: caixinha de música, pizzicato e palminhas, 104 BPM, Dó maior ---

def fofa():
    s = Sons(83)
    batida = 60 / 104
    compassos = 26
    duracao = compassos * 4 * batida
    nomes = ("caixinha", "contra", "pizz", "piano", "estalo", "chocalho", "baixo")
    f = {n: Faixa(duracao) for n in nomes}
    acordes = [[60, 64, 67], [59, 62, 67], [60, 64, 69], [60, 65, 69]]  # C G Am F
    raizes = [48, 43, 45, 41]
    frase_a = [[(0, 76, 1), (1, 79, 1), (2, 84, 2), (4, 83, 1), (5, 81, 1), (6, 79, 2)],
               [(0, 79, 1), (1, 81, 1), (2, 83, 2), (4, 86, 2), (6, 83, 2)],
               [(0, 84, 2), (2, 81, 1), (3, 79, 1), (4, 76, 2), (6, 79, 2)],
               [(0, 77, 1), (1, 76, 1), (2, 74, 2), (4, 72, 4)]]
    frase_b = [[(0, 72, 1), (1, 76, 1), (2, 79, 1), (3, 84, 1), (4, 83, 2), (6, 79, 2)],
               [(0, 74, 1), (1, 79, 1), (2, 83, 1), (3, 86, 1), (4, 84, 2), (6, 83, 2)],
               [(0, 81, 2), (2, 84, 2), (4, 88, 2), (6, 84, 2)],
               [(0, 81, 2), (2, 79, 2), (4, 77, 1), (5, 76, 1), (6, 74, 2)]]
    for c in range(compassos):
        inicio = c * 4 * batida
        k = c % 4
        final = c == compassos - 1
        if not final:
            for b, salto in ((0, 0), (2, 7)):
                f["pizz"].por(s.pizzicato(nota(raizes[k] + salto), 1.2), inicio + b * batida, pan=-0.2, ganho=0.40)
            if c >= 4:
                # Um baixo redondo e baixinho por baixo do pizzicato, para a música não ficar só nos agudos.
                for b, salto in ((0, 0), (2, 7)):
                    f["baixo"].por(s.baixo(nota(raizes[k] - 12 + salto), 1.6 * batida, 0.0), inicio + b * batida,
                                   ganho=0.20)
        if c >= 2 and not final:
            for b in (1, 3):
                for j, n_ in enumerate(acordes[k]):
                    f["piano"].por(s.piano(nota(n_ + 12), 0.35, 0.5), inicio + b * batida + j * 0.006,
                                   pan=0.2, ganho=0.12)
        if c >= 4 and not final:
            for b in (1, 3):
                f["estalo"].por(s.estalo(), inicio + b * batida, pan=-0.3, ganho=0.16)
        if c >= 8 and c < compassos - 2:
            for i in range(8):
                f["chocalho"].por(s.chocalho(), inicio + i * batida / 2, pan=0.4, ganho=0.08 if i % 2 else 0.12)
        frase = frase_a if (4 <= c < 12 or 20 <= c < 24) else frase_b if 12 <= c < 20 else None
        if frase:
            for col, n_, d in frase[k]:
                f["caixinha"].por(s.sino(nota(n_), 1.4, 0.9), inicio + col * batida / 2, pan=0.1, ganho=0.30)
        if 12 <= c < 20:
            for b in range(4):
                f["contra"].por(s.sino(nota(acordes[k][b % 3] + 12), 0.9, 0.5), inicio + b * batida + batida / 2,
                                pan=-0.35, ganho=0.10)
        if c == 24:
            for col, n_ in ((0, 72), (2, 76), (4, 79), (6, 84)):
                f["caixinha"].por(s.sino(nota(n_), 2.0, 0.8), inicio + col * batida / 2, pan=0.1, ganho=0.26)
        if final:
            for j, n_ in enumerate([60, 64, 67, 72]):
                f["caixinha"].por(s.sino(nota(n_ + 12), 3.0, 0.7), inicio + j * 0.03, pan=-0.2 + 0.13 * j, ganho=0.18)
    return mixar(f, {"caixinha": 0.4, "contra": 0.45, "piano": 0.3, "estalo": 0.2}, duracao, presenca=0.5)


# --- 9. Aconchegante: violão dedilhado, piano e vassourinha, 84 BPM, Sol maior ---

def aconchegante():
    s = Sons(97)
    batida = 60 / 84
    compassos = 21
    duracao = compassos * 4 * batida
    nomes = ("violao", "colchao", "baixo", "bumbo", "escova", "chocalho", "piano")
    f = {n: Faixa(duracao) for n in nomes}
    # Os acordes abertos do violão: (cordas graves para o polegar, cordas agudas para os dedos).
    violao = [([43, 50], [55, 59, 67]), ([40, 47], [55, 59, 64]), ([48, 55], [60, 64, 67]), ([50, 57], [62, 66, 69])]
    frase_a = [[(0, 71, 2), (2, 74, 2), (4, 79, 3), (7, 78, 1)],
               [(0, 76, 3), (3, 74, 1), (4, 71, 2), (6, 74, 2)],
               [(0, 72, 2), (2, 76, 2), (4, 79, 2), (6, 76, 2)],
               [(0, 74, 4), (4, 78, 2), (6, 81, 2)]]
    frase_b = [[(0, 83, 3), (3, 81, 1), (4, 79, 2), (6, 76, 2)],
               [(0, 79, 2), (2, 76, 2), (4, 74, 2), (6, 71, 2)],
               [(0, 72, 3), (3, 74, 1), (4, 76, 2), (6, 79, 2)],
               [(0, 78, 4), (4, 74, 4)]]
    # O dedilhado de cada compasso (colcheias): o polegar nos tempos e os dedos nos contratempos.
    dedos = [("p", 0), ("d", 1), ("p", 1), ("d", 0), ("p", 0), ("d", 2), ("p", 1), ("d", 1)]
    for c in range(compassos):
        inicio = c * 4 * batida
        k = c % 4
        graves, agudas = violao[k]
        if c == compassos - 1:
            for j, n_ in enumerate(graves + agudas):
                f["violao"].por(s.violao(nota(n_), 4.0, 0.5), inicio + j * 0.03, pan=-0.15, ganho=0.30)
            continue
        for i, (quem, qual) in enumerate(dedos):
            n_ = graves[qual] if quem == "p" else agudas[qual]
            f["violao"].por(s.violao(nota(n_), 1.4, 0.4 if quem == "p" else 0.55), inicio + i * batida / 2,
                            pan=-0.15, ganho=0.30 if quem == "p" else 0.24)
        if c >= 4:
            f["colchao"].por(s.colchao(nota(agudas[0] - 12), 4 * batida + 0.3, 900), inicio, pan=0.2, ganho=0.05)
            f["baixo"].por(s.baixo(nota(graves[0] - 12 if graves[0] > 45 else graves[0]), 1.8 * batida, 0.0),
                           inicio, ganho=0.18)
        if 5 <= c < compassos - 2:
            for b in (0, 2):
                f["bumbo"].por(s.bumbo(0.4), inicio + b * batida, ganho=0.28)
            for b in (1, 3):
                f["escova"].por(s.escovinha(), inicio + b * batida, pan=0.15, ganho=0.22)
            for i in range(8):
                f["chocalho"].por(s.chocalho(), inicio + i * batida / 2, pan=0.35, ganho=0.05 if i % 2 else 0.08)
        frase = frase_a if 8 <= c < 12 or 16 <= c < 20 else frase_b if 12 <= c < 16 else None
        if frase:
            for col, n_, d in frase[k]:
                f["piano"].por(s.piano(nota(n_), d * batida / 2 + 0.8, 0.6), inicio + col * batida / 2,
                               pan=0.2, ganho=0.30)
    return mixar(f, {"violao": 0.25, "colchao": 0.4, "piano": 0.35, "escova": 0.15}, duracao, presenca=0.55)


# --- 10. Tropical: tambor de aço, marimba e batida de verão, 100 BPM, Fá# menor / Lá maior ---

def tropical():
    s = Sons(109)
    batida = 60 / 100
    compassos = 25
    duracao = compassos * 4 * batida
    nomes = ("bumbo", "caixa", "chimbal", "chocalho", "palmas", "baixo", "marimba", "steel", "colchao")
    f = {n: Faixa(duracao) for n in nomes}
    acordes = [[61, 66, 69], [62, 66, 69], [61, 64, 69], [59, 64, 68]]  # F#m D A E
    raizes = [42, 38, 45, 40]
    frase_a = [[(0, 73, 1), (1, 76, 1), (2, 78, 2), (4, 81, 2), (6, 78, 2)],
               [(0, 78, 1), (1, 76, 1), (2, 74, 2), (4, 73, 2), (6, 74, 2)],
               [(0, 76, 2), (2, 73, 1), (3, 76, 1), (4, 81, 3), (7, 80, 1)],
               [(0, 80, 2), (2, 76, 2), (4, 71, 2), (6, 76, 2)]]
    frase_b = [[(0, 81, 2), (2, 80, 1), (3, 78, 1), (4, 76, 2), (6, 73, 2)],
               [(0, 74, 1), (1, 78, 1), (2, 81, 2), (4, 85, 2), (6, 83, 2)],
               [(0, 81, 3), (3, 80, 1), (4, 78, 2), (6, 76, 2)],
               [(0, 80, 4), (4, 83, 2), (6, 80, 2)]]
    semi = batida / 4
    for c in range(compassos):
        inicio = c * 4 * batida
        k = c % 4
        intro, final = c < 4, c == compassos - 1
        for j, n_ in enumerate(acordes[k]):
            f["colchao"].por(s.colchao(nota(n_ - 12), 4 * batida + 0.3, 1600), inicio, pan=-0.3 + 0.3 * j,
                             ganho=0.06)
        if final:
            for j, n_ in enumerate([57, 61, 64, 69]):
                f["marimba"].por(s.marimba(nota(n_), 1.5), inicio + j * 0.04, ganho=0.3)
            f["steel"].por(s.steel(nota(81), 2.0), inicio, pan=0.15, ganho=0.3)
            continue
        # A marimba nos contratempos (o "chiclete" do acorde).
        for i in (1, 3, 5, 7):
            for j, n_ in enumerate(acordes[k]):
                f["marimba"].por(s.marimba(nota(n_), 0.4), inicio + i * batida / 2 + j * 0.005,
                                 pan=-0.35, ganho=0.12)
        f["chocalho"].por(s.chocalho(), inicio, ganho=0.0)
        for i in range(16):
            f["chocalho"].por(s.chocalho(), inicio + i * semi, pan=0.4, ganho=0.06 if i % 2 else 0.10)
        if intro:
            continue
        for p in (0, 4, 8, 12):
            f["bumbo"].por(s.bumbo(0.8), inicio + p * semi, ganho=0.50)
        for p in (3, 6, 11, 14):
            f["caixa"].por(passa_baixa(s.caixa(suave=True), 6000), inicio + p * semi, pan=-0.1, ganho=0.26)
        for i in range(8):
            f["chimbal"].por(s.chimbal(), inicio + i * batida / 2, pan=0.25, ganho=0.06 if i % 2 == 0 else 0.10)
        for p, salto in ((0, 0), (6, 12), (8, 0), (14, 7)):
            f["baixo"].por(s.baixo(nota(raizes[k] - 12 + salto), 1.6 * semi, 0.3), inicio + p * semi, ganho=0.32)
        if 12 <= c < 20:
            for b in (1, 3):
                f["palmas"].por(s.palmas(), inicio + b * batida, ganho=0.22)
        frase = frase_a if (4 <= c < 12 or 20 <= c < 24) else frase_b if 12 <= c < 20 else None
        if frase:
            for col, n_, d in frase[k]:
                f["steel"].por(s.steel(nota(n_), d * batida / 2 + 0.4), inicio + col * batida / 2, pan=0.15,
                               ganho=0.26)
    return mixar(f, {"marimba": 0.25, "steel": 0.35, "palmas": 0.2, "colchao": 0.3}, duracao, presenca=0.65)


# --- 11. Mistério: curiosidade, pizzicato e tique-taque, 96 BPM, Ré menor ---

def misterio():
    s = Sons(127)
    batida = 60 / 96
    compassos = 24
    duracao = compassos * 4 * batida
    nomes = ("pizz", "relogio", "baixo", "colchao", "celesta", "estalo", "bumbo")
    f = {n: Faixa(duracao) for n in nomes}
    acordes = [[62, 65, 69], [58, 62, 65], [55, 58, 62], [57, 61, 64]]  # Dm Bb Gm A
    raizes = [38, 34, 43, 33]
    motivo = [[(0, 74, 1), (2, 77, 1), (4, 76, 1), (5, 74, 1), (6, 73, 2)],
              [(0, 74, 2), (2, 70, 2), (4, 77, 2), (6, 74, 2)],
              [(0, 79, 1), (2, 77, 1), (4, 74, 1), (5, 70, 1), (6, 74, 2)],
              [(0, 76, 2), (2, 73, 2), (4, 69, 4)]]
    for c in range(compassos):
        inicio = c * 4 * batida
        k = c % 4
        final = c == compassos - 1
        tons = acordes[k]
        if final:
            for j, n_ in enumerate([62, 65, 69]):
                f["pizz"].por(s.pizzicato(nota(n_), 1.2), inicio + j * 0.03, ganho=0.35)
            f["celesta"].por(s.sino(nota(86), 3.0, 0.8), inicio + batida / 2, pan=0.2, ganho=0.2)
            f["baixo"].por(s.baixo(nota(38), 2 * batida, 0.4), inicio, ganho=0.3)
            continue
        for i, p in enumerate([0, 2, 1, 2, 0, 2, 1, 2]):
            f["pizz"].por(s.pizzicato(nota(tons[p]), 0.6), inicio + i * batida / 2, pan=-0.25,
                          ganho=0.30 if i % 2 == 0 else 0.22)
        for i in range(8):
            f["relogio"].por(s.madeira(agudo=i % 2 == 0), inicio + i * batida / 2, pan=0.35, ganho=0.08)
        f["colchao"].por(s.colchao(nota(raizes[k] + 12), 4 * batida + 0.3, 700), inicio, pan=0.0, ganho=0.07)
        if c >= 2:
            for col in (0, 3):
                f["baixo"].por(s.baixo(nota(raizes[k]), 0.45 * batida, 0.5), inicio + col * batida / 2, ganho=0.32)
        if c >= 4:
            for b in (1, 3):
                f["estalo"].por(s.estalo(), inicio + b * batida, pan=-0.3, ganho=0.16)
        if c >= 8 and c < compassos - 2:
            f["bumbo"].por(s.bumbo(0.5), inicio, ganho=0.35)
        if 8 <= c < 20:
            for col, n_, d in motivo[k]:
                f["celesta"].por(s.sino(nota(n_), d * batida / 2 + 0.6, 0.7), inicio + col * batida / 2,
                                 pan=0.2, ganho=0.24)
    return mixar(f, {"pizz": 0.25, "celesta": 0.45, "colchao": 0.3, "estalo": 0.2}, duracao, presenca=0.6)


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


# Todas, na ordem da lista do edicao_video.MUSICAS: (o nome no arquivo, a função que a faz).
MUSICAS = (("animada", animada), ("calma", calma), ("divertida", divertida), ("romantica", romantica),
           ("elegante", elegante), ("energia", energia), ("tecnologia", tecnologia), ("fofa", fofa),
           ("aconchegante", aconchegante), ("tropical", tropical), ("misterio", misterio))


if __name__ == "__main__":
    pasta = sys.argv[1]
    quais = sys.argv[2].split(",") if len(sys.argv) > 2 else [nome for nome, _ in MUSICAS]
    for nome, gerar in MUSICAS:
        if nome not in quais:
            continue
        estereo = gerar()
        gravar_m4a(os.path.join(pasta, f"musica_{nome}.m4a"), estereo)
        print(nome, round(estereo.shape[1] / SR, 1), "s")

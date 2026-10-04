#!/bin/bash
# Prepara um vídeo do Rafael para o Claude ver e ouvir por inteiro antes de agir
# (regra no CLAUDE.md, "Como trabalhamos").
#
#   .claude/scripts/ver_video.sh VIDEO [PASTA]
#
# Gera na PASTA:
#   folha_NN.jpg  quadros do vídeo, 5 por folha, em ordem (ler todas);
#   fala.txt      a fala transcrita, com o segundo de cada trecho.
#
# A transcrição usa o faster-whisper, instalado no venv só na primeira vez que
# precisa. O modelo de voz vem do huggingface.co: se a rede do ambiente bloquear,
# o script avisa e o Claude pede a transcrição ao Rafael antes de agir.
set -euo pipefail

video="${1:?uso: ver_video.sh VIDEO [PASTA]}"
pasta="${2:-${TMPDIR:-/tmp}/video_$(date +%s)}"
mkdir -p "$pasta"

duracao=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$video")
# Um quadro a cada 2 s; vídeo longo espaça mais, para não passar de ~40 quadros.
intervalo=$(python3 -c "import math; print(max(2, math.ceil(float('$duracao') / 40)))")
ffmpeg -v error -y -i "$video" -vf "fps=1/$intervalo,scale=360:-2,tile=5x1:padding=4" "$pasta/folha_%02d.jpg"
folhas=$(ls "$pasta"/folha_*.jpg | wc -l)
echo "Vídeo de ${duracao%.*} s: $folhas folha(s) de quadros (1 a cada $intervalo s) em $pasta"

if ! ffprobe -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 "$video" | grep -q audio; then
    echo "Sem áudio no vídeo."
    exit 0
fi

if ! curl -sS -m 10 -o /dev/null https://huggingface.co 2>/dev/null; then
    echo "SEM TRANSCRIÇÃO: a rede do ambiente bloqueia o huggingface.co (modelo de voz)."
    echo "Peça a transcrição ao Rafael antes de agir, ou que ele libere o huggingface.co na rede do ambiente."
    exit 0
fi

python3 -c "import faster_whisper" 2>/dev/null || python3 -m pip install -q faster-whisper

python3 - "$video" "$pasta/fala.txt" <<'PY'
import sys
from faster_whisper import WhisperModel

video, saida = sys.argv[1], sys.argv[2]
# "small" entende bem português falado e roda em CPU em poucos segundos por minuto de vídeo.
modelo = WhisperModel("small", device="cpu", compute_type="int8")
trechos, _info = modelo.transcribe(video, language="pt", vad_filter=True)
with open(saida, "w", encoding="utf-8") as f:
    for t in trechos:
        f.write(f"[{t.start:5.1f}s] {t.text.strip()}\n")
print(f"Fala transcrita em {saida}")
PY

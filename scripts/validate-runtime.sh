#!/bin/bash
# ---------------------------------------------------------------------------
# AI Studio baked-runtime validation (build-time gate).
# Runs INSIDE the image during `docker build`. Fails the build (exit 1) if any
# required runtime element is missing or at the wrong version.
#
# Deliberately does NOT call torch.cuda.init(): no GPU is available at build
# time, and CPU/GPU host compatibility remains a RUNTIME gate (CUDA gate step).
# ---------------------------------------------------------------------------
set -uo pipefail

FAIL=0
MAIN_PY=/root/aistudio-run/venv-main/bin/python
VOICE_PY=/root/aistudio-run/venv-voice/bin/python

ok()   { printf 'PASS  %s\n' "$1"; }
bad()  { printf 'FAIL  %s\n' "$1"; FAIL=1; }
soft() { printf 'WARN  %s\n' "$1"; }

# 0) interpreters present executable
[ -x "$MAIN_PY" ]  || bad "main interpreter missing: $MAIN_PY"
[ -x "$VOICE_PY" ] || bad "voice interpreter missing: $VOICE_PY"

if [ -x "$MAIN_PY" ]; then
  # 1) main Python minor version
  v=$("$MAIN_PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)
  [ "$v" = "3.12" ] && ok "main python $v" || bad "main python version: ${v:-none}"

  # 2) main torch exact version + CUDA build
  v=$("$MAIN_PY" -c 'import torch;print(torch.__version__)' 2>/dev/null)
  [ "$v" = "2.14.0+cu130" ] && ok "main torch $v" || bad "main torch version: ${v:-none}"
  v=$("$MAIN_PY" -c 'import torch;print(torch.version.cuda)' 2>/dev/null)
  [ "$v" = "13.0" ] && ok "main torch cuda build $v" || bad "main torch cuda build: ${v:-none}"

  # 3) main critical imports = ComfyUI deps + Studio deps + ReActor deps
  for m in numpy PIL scipy safetensors einops yaml psutil aiohttp yarl tqdm \
           torchsde torchvision torchaudio transformers tokenizers sentencepiece \
           sqlalchemy alembic onnx onnxruntime cv2 albumentations ultralytics \
           segment_anything; do
    if out=$("$MAIN_PY" -c "import $m" 2>&1); then ok "main import $m"; else
      bad "main import $m :: $(printf '%s' "$out" | grep -aE 'Error|error' | tail -n1 | cut -c1-180)"
    fi
  done

  # 4) non-fatal: frontend/docs packages are optional at import time
  "$MAIN_PY" -c 'import comfyui_frontend_package' >/dev/null 2>&1 \
    && ok "main import comfyui_frontend_package" \
    || soft "comfyui_frontend_package not importable (non-fatal)"
fi

if [ -x "$VOICE_PY" ]; then
  # 5) voice Python minor version
  v=$("$VOICE_PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)
  [ "$v" = "3.10" ] && ok "voice python $v" || bad "voice python version: ${v:-none}"

  # 6) voice torch exact version + CUDA build
  v=$("$VOICE_PY" -c 'import torch;print(torch.__version__)' 2>/dev/null)
  [ "$v" = "2.7.1+cu128" ] && ok "voice torch $v" || bad "voice torch version: ${v:-none}"
  v=$("$VOICE_PY" -c 'import torch;print(torch.version.cuda)' 2>/dev/null)
  [ "$v" = "12.8" ] && ok "voice torch cuda build $v" || bad "voice torch cuda build: ${v:-none}"

  # 7) voice critical imports = CosyVoice stack + whisper
  for m in torch torchaudio gradio modelscope onnxruntime librosa soundfile whisper; do
    if out=$("$VOICE_PY" -c "import $m" 2>&1); then ok "voice import $m"; else
      bad "voice import $m :: $(printf '%s' "$out" | grep -aE 'Error|error' | tail -n1 | cut -c1-180)"
    fi
  done
fi

# 8) baked-runtime marker
[ -f /root/aistudio-run/RUNTIME_BAKED.txt ] && ok "baked marker" || bad "baked marker missing"

if [ "$FAIL" -ne 0 ]; then
  echo "RUNTIME_VALIDATION=FAIL"
  exit 1
fi
echo "RUNTIME_VALIDATION=PASS"

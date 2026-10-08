# syntax=docker/dockerfile:1.7
#
# AI Studio reproducible runtime image
# ------------------------------------
# Bakes the VERIFIED pod-local runtimes into an immutable, versioned image so a
# fresh container needs NO pip installation at startup.
#
# Source of truth: the authoritative freeze locks captured from the production
# pod that passed regression 22/22 on 2026-10-08:
#   requirements-main.lock   246 pins (Python 3.12.3, torch 2.14.0+cu130)
#   requirements-voice.lock  178 pins (Python 3.10.18, torch 2.7.1+cu128)
#
# Layout note: the venvs are baked at the EXACT paths the existing bootstrap
# already uses (/root/aistudio-run/venv-main, /root/aistudio-run/venv-voice).
# The bootstrap's "if [ ! -x <venv>/bin/python ]" guards therefore see them as
# already present and skip pip entirely:
#   RUNTIME_PIP_INSTALL_ON_START = NO     (no START change required)
#   SITE_PACKAGES_COPIED_FROM_GV = NO     (runtime is image-baked)
#
# The base image is pinned by IMMUTABLE DIGEST (multi-arch index digest).
# Tag pinned here: runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404
#   index digest (used below)   : sha256:0a360022e8de4375af99430f84e8b38951acc397252163a37ceac7204d01be35
#   linux/amd64 manifest digest : sha256:4d1721e62b56d345c83b4fd6090664be6daf9312caab5b2e76f23d8231941851
FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404@sha256:0a360022e8de4375af99430f84e8b38951acc397252163a37ceac7204d01be35

LABEL org.opencontainers.image.title="ai-studio-runtime" \
      org.opencontainers.image.description="AI Studio verified pod-local runtime (main + voice venvs baked)" \
      org.opencontainers.image.source="https://github.com/OWNER/ai-studio-runtime" \
      org.opencontainers.image.base.name="runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404" \
      org.opencontainers.image.base.digest="sha256:0a360022e8de4375af99430f84e8b38951acc397252163a37ceac7204d01be35" \
      ai-studio.runtime.main.python="3.12.3" \
      ai-studio.runtime.main.torch="2.14.0+cu130" \
      ai-studio.runtime.voice.python="3.10.18" \
      ai-studio.runtime.voice.torch="2.7.1+cu128"

ARG MAIN_INDEX_URL=https://download.pytorch.org/whl/cu130
ARG VOICE_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cu128
ARG PYPI_EXTRA_INDEX_URL=https://pypi.org/simple

COPY requirements-main.lock requirements-voice.lock /tmp/locks/
COPY scripts/validate-runtime.sh /usr/local/bin/validate-runtime.sh

# ---------------------------------------------------------------------------
# MAIN runtime (Python 3.12) - mirrors the verified production command exactly:
#   venv --system-site-packages, torch resolved from the cu130 index, the rest
#   from PyPI. --no-cache-dir keeps the image lean; no resolution drift because
#   every pin is explicit in the lock.
# ---------------------------------------------------------------------------
RUN set -eux; \
    /usr/local/bin/python -m venv --system-site-packages /root/aistudio-run/venv-main; \
    /root/aistudio-run/venv-main/bin/pip install --no-cache-dir --upgrade pip setuptools wheel; \
    /root/aistudio-run/venv-main/bin/pip install --no-cache-dir \
        -r /tmp/locks/requirements-main.lock \
        --index-url "${MAIN_INDEX_URL}" \
        --extra-index-url "${PYPI_EXTRA_INDEX_URL}"

# ---------------------------------------------------------------------------
# VOICE runtime (Python 3.10) - isolated venv, matching the verified
# pyvenv.cfg (include-system-site-packages = false) and the verified command
# (default index = PyPI, extra index = cu128 for the +cu128 torch builds).
# ---------------------------------------------------------------------------
RUN set -eux; \
    /usr/bin/python3.10 -m venv /root/aistudio-run/venv-voice; \
    /root/aistudio-run/venv-voice/bin/pip install --no-cache-dir --upgrade pip setuptools wheel; \
    /root/aistudio-run/venv-voice/bin/pip install --no-cache-dir \
        -r /tmp/locks/requirements-voice.lock \
        --extra-index-url "${VOICE_EXTRA_INDEX_URL}"

# ---------------------------------------------------------------------------
# BUILD-TIME VALIDATION - the build FAILS if any required runtime check fails.
# No GPU is required (torch.cuda.init() is deliberately NOT called; host/CUDA
# compatibility remains a runtime gate).
# ---------------------------------------------------------------------------
RUN set -eux; \
    chmod +x /usr/local/bin/validate-runtime.sh; \
    /usr/local/bin/validate-runtime.sh; \
    rm -rf /tmp/locks

# Baked runtime markers (used by START/bootstrap to detect a prebuilt runtime).
RUN set -eux; \
    printf '%s\n' "ai-studio-runtime baked" "main=toolkit 3.12.3 torch 2.14.0+cu130" "voice=3.10.18 torch 2.7.1+cu128" > /root/aistudio-run/RUNTIME_BAKED.txt

# No entrypoint override: the base image ENTRYPOINT (/start.sh) must keep
# working so RunPod-driven startup (sshd, jupyter, env) is unchanged.

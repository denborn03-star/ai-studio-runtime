# ai-studio-runtime

Reproducible AI Studio **runtime** container image, built by GitHub Actions and
published to GHCR with an immutable `sha256:` digest.

Goal: eliminate the ~25–40 min per-fresh-container `pip` runtime rebuild. A
container started from this image has the runtimes **baked in** and performs
**no** bulk pip installation at startup.

Path: `GitHub Actions → GHCR → immutable image digest`.
No local Docker, no WSL, no RunPod involvement at build time.

---

## Repository layout (this directory is the repository root)

```
Dockerfile                       # pinned base digest; bakes both venvs; runs the validator
requirements-main.lock           # 246 pins  (Python 3.12.3, torch 2.14.0+cu130)
requirements-voice.lock          # 178 pins  (Python 3.10.18, torch 2.7.1+cu128)
.dockerignore
.github/workflows/build-image.yml
scripts/validate-runtime.sh      # build-time gate (fails the build on any miss)
README.md
GITHUB_HANDOFF.md
reference/                       # non-build reference state (not sent to the builder)
```

---

## Verified runtime (source of truth)

| Item | Value |
|---|---|
| main Python | 3.12.3 |
| main torch | `torch==2.14.0+cu130` (CUDA build 13.0) |
| voice Python | 3.10.18 |
| voice torch | `torch==2.7.1+cu128` (CUDA build 12.8) |
| main lock | `requirements-main.lock` — 246 pins |
| voice lock | `requirements-voice.lock` — 178 pins |

Both locks are byte-copies of the authoritative freeze from the production pod
that passed regression 22/22 (`2026-10-08`). Representative pins:
`torchvision==0.29.0+cu130`, `torchaudio==2.11.0+cu130`, `segment-anything==1.0`,
`albumentations==2.0.8`, `opencv-python==5.0.0.93` (main);
`openai-whisper==20250625`, `gradio==5.4.0`, `modelscope==1.20.0`,
`onnxruntime-gpu==1.18.0` (voice).

No dependency is regenerated from Global Volume listings.

---

## Base image pinned by immutable digest

Tag: `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`

| Reference | Digest |
|---|---|
| `BASE_IMAGE_DIGEST` (multi-arch index, **used in `FROM`**) | `sha256:0a360022e8de4375af99430f84e8b38951acc397252163a37ceac7204d01be35` |
| linux/amd64 manifest (reference) | `sha256:4d1721e62b56d345c83b4fd6090664be6daf9312caab5b2e76f23d8231941851` |

The amd64 manifest digest was cross-checked against the registry
`Docker-Content-Digest` response header.

---

## Baked runtime layout (why no START change is needed)

```
/root/aistudio-run/venv-main     # Python 3.12.3 + torch 2.14.0+cu130
/root/aistudio-run/venv-voice    # Python 3.10.18 + torch 2.7.1+cu128
/root/aistudio-run/RUNTIME_BAKED.txt
```

These are the **exact paths** the existing bootstrap already uses, so its
`if [ ! -x <venv>/bin/python ]; then <pip build>; fi` guards see a prebuilt
runtime and skip pip automatically:

* `RUNTIME_PIP_INSTALL_ON_START = NO`
* `SITE_PACKAGES_COPIED_FROM_GV = NO`

The lock-driven rebuild stays in the bootstrap untouched, as recovery logic for
containers not based on this image.

---

## Build-time validation

`scripts/validate-runtime.sh` runs inside the image during `docker build` and
asserts: interpreter versions (3.12 / 3.10), exact torch versions
(`2.14.0+cu130` / `2.7.1+cu128`), exact CUDA build strings (`13.0` / `12.8`),
and imports for the ComfyUI stack, Studio stack, ReActor stack
(`albumentations`, `ultralytics`, `segment_anything`, `cv2`, `onnx`,
`onnxruntime`) and the voice stack (`torch`, `torchaudio`, `gradio`,
`modelscope`, `onnxruntime`, `librosa`, `soundfile`, `whisper`).

It deliberately does **not** call `torch.cuda.init()` — there is no GPU at build
time, and host/CUDA compatibility remains a runtime gate on RunPod.

A validation failure fails the build, so **nothing is pushed**.

---

## Publishing

1. Create a **public** GitHub repository named `ai-studio-runtime`.
2. Upload this directory as the repository root (keep `.github/` and
   `scripts/`), default branch `main`.
3. Actions → `build-ai-studio-runtime` → **Run workflow** (or push to `main`).
   The workflow logs in to GHCR with the auto-provided `GITHUB_TOKEN`
   (`packages: write`) — no manual secret is required.
4. Read `IMAGE_DIGEST` from the run summary.

Expected outputs:

```
ghcr.io/<owner>/ai-studio-runtime:runtime-20261008
ghcr.io/<owner>/ai-studio-runtime:sha-<full-commit-sha>
ghcr.io/<owner>/ai-studio-runtime@sha256:<digest>     # PRODUCTION PIN
```

`latest` is never used as the production source of truth.

---

## GHCR visibility → deployment readiness

The image is deployed from RunPod, so it must be pullable. Preferred mode here
is a **public package** (no privacy requirement exists), which needs no
credentials anywhere:

1. After the first publish: package `ai-studio-runtime` → **Package settings →
   Change visibility → Public**.
2. Verify anonymous pull from a clean environment:
   `docker pull ghcr.io/<owner>/ai-studio-runtime@sha256:<digest>`
   (should succeed without any login).
3. Only then is `RUNPOD_IMAGE_PULL_READY = YES`.

Alternative (private package): register a read-only GHCR credential in RunPod
via `POST /v2/registries`, then verify the pull with those credentials.

Do not deploy to RunPod until `IMAGE_DIGEST` is obtained **and**
`RUNPOD_IMAGE_PULL_READY = YES`.

---

## Integrator notes (next task, not done here)

With the image in place, the RunPod side needs no runtime rebuild. Two small
control-layer adjustments remain for full image integration:

* point the pod at
  `ghcr.io/<owner>/ai-studio-runtime@sha256:<digest>` (pod `imageName`), and
* ensure the CUDA gate reads the torch build from the **image** runtime rather
  than from the Global Volume copy, so the gate stays authoritative.

Neither change is part of this bundle.

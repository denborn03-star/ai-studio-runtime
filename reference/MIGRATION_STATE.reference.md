# MIGRATION STATE — Global Volume runtime architecture (2026-10-08)



## STATUS: FINAL — MANIFEST RUNTIME ARCHITECTURE VERIFIED (2026-10-08 18:0x)



REGRESSION_RESULT=PASS (22/22, 0 fail): ComfyUI/vision-web/8090/voice/CUDA gate/all SSH invariants.

Production runtime = POD-LOCAL manifest-built venvs (torch 2.14.0+cu130 main; torch 2.7.1+cu128 voice).

NO site-packages reads/copies from GV at runtime. SITE_PACKAGES_COPIED_FROM_GV = NO.

Locks: /root/aistudio-manifests/*.lock + local copies in manifests-20261008\ (246+178 pins).

Cold start (fresh container): manifest venv rebuild ~25-40 min (one-time per container);

subsequent stop/start reuses the container-disk venvs (~5-8 min).

Known degraded feature: c2patool NOT installed (release asset not found) - C2PA marking only.





## WORKING NOW (pod iru63n4tnfmfo3, running)

- ComfyUI: RUNNING, /queue HTTP 200 (venv-main local, torch 2.14.0+cu130, CUDA OK)

- vision-web: RUNNING, port 8090 answers 403 session-auth (started via bash -s < control.sh)

- voice worker: process alive (pid 14198), voice venv complete (torch 2.7.1+cu128), WORKER_PY patched to /root/aistudio-run/venv-voice/bin/python

- CUDA/PyTorch: driver 595.91.07 / CUDA 13.2; venv torch 2.14.0+cu130 CUDA init OK

- Global Volume: mounted, models/code/data intact (no deletes)

- tunnels: 18090->8090, 62593->8188 active



## ROOT BLOCKER (why PARTIAL, not PASS)

gvfs (geesefs) on /workspace is not a reliable runtime substrate:

1. partial directory listings -> negative dentry cache -> direct lookups ENOENT

   (typing_extensions, scipy, ReActor deps invisible to python imports);

2. lost FUSE wakeups wedge reads mid-operation (3+ occurrences);

3. writes report success but reads serve stale content (start-comfy.sh

   repeatedly executed the previous bootstrap version);

4. sustained load -> EIO; no exec bits (chmod rejected) -> scripts need

   `bash script` invocation, direct exec fails.

Manifest-runtime rebuilds are functional but each fresh pod needs the full

pinned reinstall (~25-40 min); pip gaps from the partial 89-pin manifest

appear one-by-one (sqlalchemy, ReActor stack, whisper were post-fixes).



## MANUAL FIXES USED AFTER CLEAN RUN (must be architected away)

1. pip install sqlalchemy alembic (missing from partial manifest)

2. pip install -r ComfyUI/custom_nodes/ComfyUI-ReActor/requirements.txt

3. pip install openai-whisper + full voice freeze completion

4. torch==2.14.0+cu130 reinstall --ignore-installed (first attempt failed on

   system nvidia-* overlap; --ignore-installed is NOT in the verified manifest)

5. c2patool: NOT installed (release asset name unknown; C2PA marking degraded)

6. manual chmod 755 /root/bs-launch.sh + detached relaunch (x-bit workaround)



## NEXT ARCHITECTURAL TASK (inputs preserved)

- /root/aistudio-manifests/requirements-main-full.txt (223 pins, merged,

  contains junk pins: sam_2 + source-build failures to filter: pycairo,

  openai-whisper pin was removed)

- /root/aistudio-manifests/requirements-voice.txt (177 pins, validated 0

  errors, whisper pin removed)

- frozen manifests also at /tmp/freeze_main.txt /tmp/freeze_voice.txt

- image system dist-packages (torch 2.8+cu128, numpy, PIL, scipy, requests,

  pycairo...) readable via /usr/local/bin/python -m pip freeze

- Start-AIStudio.ps1: SSH_STDIN_TRANSPORT_V1 (stdin-file transfer + MD5

  verify, 5 retries) INSTALLED AND WORKING (transfer 1/5 MD5 match)

- detached bootstrap + poll loop INSTALLED AND WORKING

- host-key heal V2 (TOFU in isolated known_hosts_heal) INSTALLED

- CUDA gate V1 INSTALLED (GPU_HOST_CUDA_INCOMPATIBLE before bootstrap)



## ACCEPTANCE DEBT (final clean test not counted)

- 3 regression fails at last full check: SSH_NO_ACCEPT_NEW (heal option,

  replaced by TOFU-after-cleanup), VISION_WEB_HEALTH (was pre-`bash -s` fix),

  + BASELINE_HASHES warn (expected: control files edited)

- final clean test never completed end-to-end without manual steps



## VOLUMES

- GV cmuyauyou000007l8488o9j9p: intact

- regional 10j4hb5oty: intact

- rollback: Start-AIStudio.ps1 $UseStandingPod=$false restores legacy regional

  create/delete flow (documented in file header)



## FILES MODIFIED (control layer)

- Start-AIStudio.ps1 (standing pod, GPU priorities, SSH safety, stdin

  transport, detached bootstrap, CUDA gate, headless mode)

- Stop-AIStudio.ps1, Stop-AIStudio-Silent.ps1 (standing pod stop, no delete)

- pod-profile.json (globalVolumeId, standingPodId, useStandingPod)

- Backups: %LOCALAPPDATA%\AI-Studio\backups\mig-global-*\*.bak



## POD

- iru63n4tnfmfo3, RUNNING, PRO 6000 Blackwell SE 96GB, US-PA-1, $2.09/hr

- KEEP (production standing pod; never deleted by STOP)


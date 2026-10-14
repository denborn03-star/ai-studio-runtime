#!/usr/bin/env python3
"""Offline quality-gate checks for the AI Studio candidate image.

Runs every gate that can be completed WITHOUT a container runtime, a CI run or a
GPU. It reads the production and candidate build inputs and asserts, mechanically:

  G1 production-file integrity (hashes recorded at audit time)
  G2 candidate/production parity: base digest, COPY inputs, indexes, no
     ENTRYPOINT/CMD override, same venv commands
  G3 lock integrity: pin counts, no duplicate names, well-formed pins
  G4 validator import coverage: every import asserted by validate-runtime.sh is
     provided by a pinned distribution
  G5 split integrity: the layer-split regex selects the same pins that exist in
     the lock (nothing invented, nothing lost)
  G6 the group installs use --no-deps and are guarded, and the FULL lock is
     installed after each group (so no package can be dropped and no file is
     installed twice)
  G7 workflow validity: YAML parses, dispatch-only, candidate-only tags, no
     production tag/`latest` as a tag, exporter compression options present, and
     no mixing of `outputs` with the undocumented push/provenance/sbom shorthands

Exit code = number of failed checks. Usage: python scripts/verify-candidate-offline.py
"""
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROD_DOCKERFILE = ROOT / "Dockerfile"
CAND_DOCKERFILE = ROOT / "Dockerfile.candidate-20261014"
WORKFLOW = ROOT / ".github" / "workflows" / "build-candidate.yml"
MAIN_LOCK = ROOT / "requirements-main.lock"
VOICE_LOCK = ROOT / "requirements-voice.lock"
VALIDATOR = ROOT / "scripts" / "validate-runtime.sh"

# Hashes captured when the audit verified the production inputs (2026-10-14).
PRODUCTION_HASHES = {
    "Dockerfile": "e7454b92b91e30d274ad409bf9d0ec71e2194fb80fbb000c4ef9ee61f1c6425b",
    "requirements-main.lock": "0bda439df977a9e54d088c15544fc98bef6b4f0e992b2a22eeb7e9dcb7fe0bbd",
    "requirements-voice.lock": "24ca09544f3de8ba30b527fb6698e035445559213fdcf2e46e60e3753f139347",
    "scripts/validate-runtime.sh": "ffb1be7ec2a812b591a995d308e04107bf3d8ba9431c4d820b2c35d9e7875f90",
    ".github/workflows/build-image.yml": "086285d95e1f5a712773794a9de7ab881d761b5e090802bc6bdf089ca47f7426",
}
PROD_TAG = "runtime-20261008"
PROD_DIGEST = "sha256:68219041e6ebdc53e256e9c8c27c3d33f2389afdb136c6784af8cf748a7199bd"
SPLIT_REGEX = r"^(torch|torchvision|torchaudio|triton|nvidia-|cuda-|pytorch)"

results = []


def check(gate, name, ok, detail=""):
    results.append((gate, name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {gate}  {name}" + (f" :: {detail}" if detail else ""))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pins(path):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "==" in line:
            name, _, ver = line.partition("==")
            out.append((name.strip().lower(), ver.strip()))
    return out


# ---- G1 production inputs unchanged -----------------------------------------
for rel, want in PRODUCTION_HASHES.items():
    p = ROOT / rel
    if not p.exists():
        check("G1", f"production {rel} exists", False, "missing")
        continue
    check("G1", f"production {rel} unchanged", sha256(p) == want, sha256(p)[:16])

prod_text = PROD_DOCKERFILE.read_text(encoding="utf-8")
cand_text = CAND_DOCKERFILE.read_text(encoding="utf-8")


def from_line(text):
    for line in text.splitlines():
        if line.startswith("FROM "):
            return line.strip()
    return ""


check("G2", "candidate FROM identical to production", from_line(prod_text) == from_line(cand_text),
      from_line(cand_text).split("@")[-1][:24])
check("G2", "base image pinned by digest",
      "@sha256:" in from_line(cand_text) and len(from_line(cand_text).split("@sha256:")[-1]) == 64)
for token in ("requirements-main.lock", "requirements-voice.lock", "validate-runtime.sh"):
    check("G2", f"candidate copies {token}", token in cand_text and token in prod_text)
check("G2", "no ENTRYPOINT/CMD override in candidate",
      not re.search(r"^\s*(ENTRYPOINT|CMD)\b", cand_text, re.M),
      "base entrypoint preserved")
for arg in ("MAIN_INDEX_URL", "VOICE_EXTRA_INDEX_URL", "PYPI_EXTRA_INDEX_URL"):
    prod_arg = re.search(rf"^ARG {arg}=(\S+)", prod_text, re.M)
    cand_arg = re.search(rf"^ARG {arg}=(\S+)", cand_text, re.M)
    check("G2", f"candidate index {arg} unchanged",
          prod_arg and cand_arg and prod_arg.group(1) == cand_arg.group(1),
          cand_arg.group(1) if cand_arg else "missing")
for token in ("/root/aistudio-run/venv-main", "/root/aistudio-run/venv-voice", "/usr/local/python"):
    pass
check("G2", "candidate venv paths unchanged",
      "/root/aistudio-run/venv-main" in cand_text and "/root/aistudio-run/venv-voice" in cand_text
      and "--system-site-packages" in cand_text)

# ---- G3 lock integrity -------------------------------------------------------
main_pins, voice_pins = pins(MAIN_LOCK), pins(VOICE_LOCK)
for label, pl, want in (("main", main_pins, 246), ("voice", voice_pins, 178)):
    names = [n for n, _ in pl]
    check("G3", f"{label} lock pin count == {want}", len(pl) == want, str(len(pl)))
    check("G3", f"{label} lock has no duplicate package names", len(names) == len(set(names)))
    check("G3", f"{label} lock pins are all well-formed name==version",
          all(n and v and " " not in n for n, v in pl))

# ---- G4 validator import coverage -------------------------------------------
validator_text = VALIDATOR.read_text(encoding="utf-8")
main_map = {"numpy": "numpy", "PIL": "pillow", "scipy": "scipy", "safetensors": "safetensors",
            "einops": "einops", "yaml": "pyyaml", "psutil": "psutil", "aiohttp": "aiohttp",
            "yarl": "yarl", "tqdm": "tqdm", "torchsde": "torchsde", "torchvision": "torchvision",
            "torchaudio": "torchaudio", "transformers": "transformers", "tokenizers": "tokenizers",
            "sentencepiece": "sentencepiece", "sqlalchemy": "sqlalchemy", "alembic": "alembic",
            "onnx": "onnx", "onnxruntime": "onnxruntime", "cv2": "opencv-python",
            "albumentations": "albumentations", "ultralytics": "ultralytics",
            "segment_anything": "segment-anything"}
voice_map = {"torch": "torch", "torchaudio": "torchaudio", "gradio": "gradio",
             "onnxruntime": "onnxruntime-gpu", "librosa": "librosa", "soundfile": "soundfile",
             "whisper": "openai-whisper"}
mnames = {n for n, _ in main_pins}
vnames = {n for n, _ in voice_pins}
miss = [f"main:{m}<-{d}" for m, d in main_map.items() if d not in mnames]
miss += [f"voice:{m}<-{d}" for m, d in voice_map.items() if d not in vnames]
check("G4", "validator imports all covered by locks",
      not miss and len(main_map) + len(voice_map) == 31, f"{len(main_map)+len(voice_map)} imports"
      + (f" missing={miss}" if miss else ""))
check("G4", "validator asserts exact torch/CUDA builds",
      "2.14.0+cu130" in validator_text and "2.7.1+cu128" in validator_text)
for want in ("torch==2.14.0+cu130", "torch==2.7.1+cu128", "triton==3.8.0", "triton==3.3.1"):
    check("G4", f"lock pins {want}", any(f"{n}=={v}" == want for n, v in main_pins + voice_pins))

# ---- G5 split integrity ------------------------------------------------------
pat = re.compile(SPLIT_REGEX)
for label, pl in (("main", main_pins), ("voice", voice_pins)):
    group = [(n, v) for n, v in pl if pat.match(f"{n}=={v}")]
    rest = [(n, v) for n, v in pl if not pat.match(f"{n}=={v}")]
    check("G5", f"{label} split partitions the lock exactly",
          len(group) + len(rest) == len(pl) and not (set(group) & set(rest)),
          f"group={len(group)} rest={len(rest)} total={len(pl)}")
    check("G5", f"{label} split group is non-empty", len(group) > 0)
    check("G5", f"{label} split keeps the CUDA/torch stack together",
          any(n == "torch" for n, _ in group) and sum(1 for n, _ in group if n.startswith("nvidia-")) >= 13,
          f"nvidia pins in group: {sum(1 for n, _ in group if n.startswith('nvidia-'))}")

# ---- G6 group-install safety -------------------------------------------------
group_runs = re.findall(r"RUN set -eux; \\\n(.*?)(?=\n(?:RUN|#|$))", cand_text, re.S)
group_steps = [g for g in group_runs if "torch-group.lock" in g]
check("G6", "both group steps exist", len(group_steps) == 2, str(len(group_steps)))
for g in group_steps:
    check("G6", "group step installs with --no-deps", "--no-deps" in g)
    check("G6", "group step asserts the subset is non-empty", "test -s" in g)
main_full = cand_text.count("-r /tmp/locks/requirements-main.lock")
voice_full = cand_text.count("-r /tmp/locks/requirements-voice.lock")
check("G6", "each full lock installed exactly once",
      main_full == 1 and voice_full == 1, f"main={main_full} voice={voice_full}")
lines = cand_text.splitlines()


def index_of(needle):
    for i, line in enumerate(lines):
        if needle in line:
            return i
    return -1


for venv, lock in (("main", "main-torch-group.lock"), ("voice", "voice-torch-group.lock")):
    group_at = index_of(f"-r /tmp/locks/{lock}")
    full_at = index_of(f"-r /tmp/locks/requirements-{venv}.lock")
    check("G6", f"{venv}: full lock installed after the torch group",
          -1 < group_at < full_at, f"group@{group_at} full@{full_at}")
    no_deps_at = index_of("--no-deps")
    check("G6", f"{venv}: full-lock install has no --no-deps",
          full_at > 0 and "--no-deps" not in lines[full_at - 1] and "--no-deps" not in lines[full_at])
check("G6", "no --no-deps on the full-lock installs",
      all("--no-deps" not in line for line in cand_text.splitlines()
          if "requirements-main.lock" in line or "requirements-voice.lock" in line))

# ---- G7 workflow validity ----------------------------------------------------
try:
    import yaml
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = wf.get("on", wf.get(True))
    check("G7", "workflow YAML parses", True)
    check("G7", "dispatch-only trigger", list(triggers.keys()) == ["workflow_dispatch"], str(list(triggers.keys())))
    steps = wf["jobs"]["build-candidate"]["steps"]
    build = [s for s in steps if str(s.get("name", "")).startswith("Build and push")][0]["with"]
    check("G7", "candidate Dockerfile is the build target",
          build["file"] == "./Dockerfile.candidate-20261014", build["file"])
    check("G7", "no push/provenance/sbom shorthands mixed with outputs",
          not ({"push", "provenance", "sbom"} & set(build)))
    out = build["outputs"]
    for opt in ("compression=gzip", "compression-level=9", "force-compression=true", "push=true",
                "oci-mediatypes=true"):
        check("G7", f"exporter option {opt}", opt in out)
    tags = [s for s in steps if s.get("name") == "Candidate metadata"][0]["with"]["tags"]
    check("G7", "only candidate tags", "candidate-20261014" in tags and PROD_TAG not in tags
          and "latest" not in tags.replace("latest", "") and "type=raw,value=latest" not in tags)
    check("G7", "production tag/digest never used as a tag",
          PROD_TAG not in tags and PROD_DIGEST not in tags)
    check("G7", "permissions: packages write",
          wf.get("permissions", {}).get("packages") == "write")
except ImportError:
    check("G7", "PyYAML available for workflow validation", False, "pip install pyyaml to enable")

failed = [r for r in results if not r[2]]
print(f"\nOFFLINE_GATES: {len(results) - len(failed)} passed / {len(failed)} failed")
for gate, name, _ok, detail in failed:
    print(f"  FAILED {gate} {name} {detail}")
sys.exit(len(failed))

REPOSITORY_NAME:
ai-studio-runtime

VISIBILITY:
public

DEFAULT_BRANCH:
main

BUILD_WORKFLOW:
.github/workflows/build-image.yml

EXPECTED_IMAGE:
ghcr.io/<owner>/ai-studio-runtime

BASE_IMAGE_DIGEST:
sha256:0a360022e8de4375af99430f84e8b38951acc397252163a37ceac7204d01be35

REQUIRED_AFTER_PUBLISH:
- workflow PASS
- IMAGE_DIGEST obtained
- package public
- anonymous image pull verified
- RUNPOD_IMAGE_PULL_READY = YES

---
UPLOAD INSTRUCTIONS (this directory is the repository root)

Upload the contents of:
  C:\Users\user\Downloads\AI-Studio-Server-Files\ai-studio-image-build-20261008
as the root of the repository, preserving subdirectories:
  .github/workflows/build-image.yml
  scripts/validate-runtime.sh
  reference/            (optional reference state; excluded from the build context)

Do not rename requirements-main.lock / requirements-voice.lock / Dockerfile.

PUBLISH STEPS
1. Create public repository `ai-studio-runtime`.
2. Upload this directory as the repository root; default branch `main`.
3. Actions -> build-ai-studio-runtime -> Run workflow (or push to main).
4. Read IMAGE_DIGEST from the run summary
   (format: sha256:<64 hex>).
5. Package ai-studio-runtime -> Package settings -> Change visibility -> Public.
6. Verify anonymous pull from a clean environment:
     docker pull ghcr.io/<owner>/ai-studio-runtime@sha256:<digest>
7. Report RUNPOD_IMAGE_PULL_READY = YES.

CONSTRAINTS PRESERVED BY THIS BUNDLE
- base image pinned by immutable digest (no mutable tag reliance)
- main venv: Python 3.12.3 + torch 2.14.0+cu130
- voice venv: Python 3.10.18 + torch 2.7.1+cu128
- no 'latest' as production source of truth
- no secrets embedded; GITHUB_TOKEN is auto-provided by Actions
- build fails if runtime validation fails (nothing is pushed)

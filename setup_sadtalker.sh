#!/usr/bin/env bash
#
# setup_sadtalker.sh — one-shot SadTalker installer for the talking-avatar feature.
#
# Run this on a machine with a GPU and a few GB of free disk (NOT recommended on a
# laptop with little space / no GPU). It clones SadTalker, builds an isolated venv,
# installs its deps, downloads the model checkpoints, and prints the .env lines to add.
#
# Usage:
#   ./setup_sadtalker.sh [TARGET_DIR]
# Env:
#   PYTHON_BIN   python interpreter to build the venv (default: python3.10 if present, else python3)
#
set -euo pipefail

TARGET_DIR="${1:-$(pwd)/vendor/SadTalker}"
REPO="https://github.com/OpenTalker/SadTalker.git"

# SadTalker pins old torch; Python 3.10 is the sweet spot.
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  if command -v python3.10 >/dev/null 2>&1; then PYTHON_BIN="python3.10"
  elif command -v pyenv >/dev/null 2>&1 && pyenv versions --bare | grep -q '^3\.10'; then
    PYTHON_BIN="$(pyenv root)/versions/$(pyenv versions --bare | grep '^3\.10' | head -1)/bin/python"
  else PYTHON_BIN="python3"; fi
fi

echo "▶ SadTalker target : ${TARGET_DIR}"
echo "▶ Python for venv  : ${PYTHON_BIN} ($(${PYTHON_BIN} --version 2>&1))"
command -v git >/dev/null    || { echo "✗ git not found"; exit 1; }
command -v ffmpeg >/dev/null || { echo "✗ ffmpeg not found (required)"; exit 1; }

# Warn on low disk (need ~5-7 GB).
avail_kb=$(df -Pk "$(dirname "${TARGET_DIR}")" | awk 'NR==2{print $4}')
if [[ "${avail_kb}" -lt 7000000 ]]; then
  echo "⚠  Only $((avail_kb/1024/1024)) GB free — SadTalker needs ~5-7 GB. Free space or pick another disk."
  read -r -p "Continue anyway? [y/N] " ans; [[ "${ans}" == "y" || "${ans}" == "Y" ]] || exit 1
fi

# 1) Clone
if [[ ! -d "${TARGET_DIR}/.git" ]]; then
  echo "▶ Cloning SadTalker…"
  git clone --depth 1 "${REPO}" "${TARGET_DIR}"
else
  echo "▶ SadTalker already cloned — skipping."
fi
cd "${TARGET_DIR}"

# 2) venv + deps
echo "▶ Creating venv + installing deps (this is the slow part)…"
"${PYTHON_BIN}" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel
# CPU torch by default; on an NVIDIA box install the matching CUDA build instead.
python -m pip install torch torchvision torchaudio
python -m pip install -r requirements.txt

# 3) Checkpoints
echo "▶ Downloading model checkpoints (~2 GB)…"
if [[ -f scripts/download_models.sh ]]; then
  bash scripts/download_models.sh
else
  echo "✗ scripts/download_models.sh missing — see SadTalker README for checkpoint download."
fi
deactivate

echo
echo "✅ SadTalker ready at: ${TARGET_DIR}"
echo "Add these to your gold-price-bot .env:"
echo "-----------------------------------------------"
echo "SADTALKER_DIR=${TARGET_DIR}"
echo "SADTALKER_PYTHON=${TARGET_DIR}/.venv/bin/python"
echo "# SADTALKER_ENHANCER=gfpgan   # optional, sharper but slower"
echo "-----------------------------------------------"
echo "Then: python main.py --job horoscope-aries --dry-run"

#!/usr/bin/env bash
# HIGGS Studio installer (macOS / Linux). Safe to re-run: it only adds what's missing.
#
#   bash scripts/install.sh              # studio + ffmpeg + local ComfyUI (CPU/GPU auto)
#   bash scripts/install.sh --with-ltx   # also download LTX-Video 2B (~11.5 GB) for local generation
#   bash scripts/install.sh --no-comfy   # studio only (generate on Kaggle / another GPU computer)
#
# Layout:  <parent>/app      <- this repository
#          <parent>/runtime  <- ffmpeg, ComfyUI, its Python env and models (override with HIGGS_RUNTIME_DIR)
set -euo pipefail

APP="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="${HIGGS_RUNTIME_DIR:-$(dirname "$APP")/runtime}"
WITH_LTX=0; NO_COMFY=0
for a in "$@"; do case "$a" in --with-ltx) WITH_LTX=1;; --no-comfy) NO_COMFY=1;; esac; done

OS="$(uname -s)"; ARCH="$(uname -m)"
say() { printf "\n\033[1;38;5;191m▸ %s\033[0m\n" "$*"; }
die() { printf "\n\033[1;31m✗ %s\033[0m\n" "$*"; exit 1; }

mkdir -p "$RUNTIME/bin"
say "HIGGS Studio installer · $OS $ARCH"
echo "  app:     $APP"
echo "  runtime: $RUNTIME"

# ---------------------------------------------------------------- python
PY=""
for c in python3.12 python3.11 python3.13 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)'; then PY="$(command -v "$c")"; break; fi
done
[ -n "$PY" ] || die "Python 3.10–3.13 is required. Install it from https://www.python.org/downloads/ and run this again."
echo "  python:  $PY ($("$PY" --version))"

# ---------------------------------------------------------------- ffmpeg (standalone, no Homebrew)
if [ ! -x "$RUNTIME/bin/ffmpeg" ] && ! command -v ffmpeg >/dev/null 2>&1; then
  say "Downloading FFmpeg (standalone)"
  TMP="$(mktemp -d)"
  if [ "$OS" = "Darwin" ]; then
    # FFmpeg 7.x static build shipped inside the imageio-ffmpeg wheel on PyPI (no Homebrew needed).
    "$PY" -m pip download -q --no-deps --only-binary=:all: -d "$TMP" "imageio-ffmpeg==0.7.0"
    (cd "$TMP" && unzip -oq imageio_ffmpeg-*.whl 'imageio_ffmpeg/binaries/*')
    cp "$TMP"/imageio_ffmpeg/binaries/ffmpeg-* "$RUNTIME/bin/ffmpeg"
    xattr -d com.apple.quarantine "$RUNTIME/bin/ffmpeg" 2>/dev/null || true
  else
    case "$ARCH" in x86_64) FA=amd64;; aarch64|arm64) FA=arm64;; *) die "No static FFmpeg for $ARCH; install ffmpeg with your package manager.";; esac
    curl -fL --retry 3 -o "$TMP/ff.tar.xz" "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-$FA-static.tar.xz"
    tar -xJf "$TMP/ff.tar.xz" -C "$TMP"
    mv "$TMP"/ffmpeg-*-static/ffmpeg "$TMP"/ffmpeg-*-static/ffprobe "$RUNTIME/bin/"
  fi
  chmod +x "$RUNTIME/bin/ffmpeg" "$RUNTIME/bin/ffprobe" 2>/dev/null || chmod +x "$RUNTIME/bin/ffmpeg"
  rm -rf "$TMP"
fi
"${RUNTIME}/bin/ffmpeg" -version 2>/dev/null | head -1 || ffmpeg -version | head -1

# ---------------------------------------------------------------- studio backend
say "Installing the studio backend"
[ -d "$APP/backend/.venv" ] || "$PY" -m venv "$APP/backend/.venv"
"$APP/backend/.venv/bin/python" -m pip install -q --upgrade pip
"$APP/backend/.venv/bin/python" -m pip install -q -r "$APP/backend/requirements.txt"
# python.org Python on macOS ships without CA certificates; run its own fix if present
for f in /Applications/Python\ 3.1*/Install\ Certificates.command; do [ -f "$f" ] && bash "$f" >/dev/null 2>&1 || true; done

# ---------------------------------------------------------------- interface
# A pre-built copy ships in frontend/out (kept in git, so updates via `git pull` stay clean).
# Rebuild only when it's missing or you pass --build-ui (needs Node 18+).
if [ ! -f "$APP/frontend/out/index.html" ] || [[ " $* " == *" --build-ui "* ]]; then
  [ -s "$HOME/.nvm/nvm.sh" ] && . "$HOME/.nvm/nvm.sh" >/dev/null 2>&1 || true
  command -v npm >/dev/null 2>&1 || die "Node.js 18+ is needed to build the interface: https://nodejs.org"
  say "Building the interface"
  (cd "$APP/frontend" && npm ci --no-audit --no-fund --loglevel=error && npm run build >/dev/null)
else
  echo "  Using the pre-built interface."
fi

# ---------------------------------------------------------------- local ComfyUI
if [ "$NO_COMFY" = "0" ]; then
  COMFY="$RUNTIME/ComfyUI"
  if [ ! -d "$COMFY" ]; then
    say "Installing ComfyUI (local inference engine)"
    if [ "$OS" = "Darwin" ] && [ "$ARCH" = "x86_64" ]; then
      # Last ComfyUI release that still runs on PyTorch 2.2 (0.8.0+ needs torch.library.custom_op, PyTorch 2.4+).
      git clone --depth 1 --branch v0.7.0 https://github.com/comfyanonymous/ComfyUI "$COMFY"
    else
      git clone --depth 1 https://github.com/comfyanonymous/ComfyUI "$COMFY"
    fi
  fi
  if [ ! -x "$RUNTIME/venv/bin/python" ]; then "$PY" -m venv "$RUNTIME/venv"; fi
  VPY="$RUNTIME/venv/bin/python"
  "$VPY" -m pip install -q --upgrade pip
  if ! "$VPY" -c "import torch" 2>/dev/null; then
    say "Installing PyTorch"
    if [ "$OS" = "Darwin" ] && [ "$ARCH" = "x86_64" ]; then
      # PyTorch stopped publishing Intel-Mac builds after 2.2.2 (CPU only on these Macs).
      "$VPY" -m pip install -q "torch==2.2.2" "torchvision==0.17.2" "torchaudio==2.2.2" "numpy<2"
    elif command -v nvidia-smi >/dev/null 2>&1; then
      "$VPY" -m pip install -q torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
    elif [ "$OS" = "Darwin" ]; then
      "$VPY" -m pip install -q torch torchvision torchaudio            # Apple Silicon: Metal (MPS)
    else
      "$VPY" -m pip install -q torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
    fi
  fi
  # ComfyUI requirements, without letting them replace the torch we just chose
  SKIP='torch|torchvision|torchaudio'
  # Intel Mac: these optional packages have no Intel-Mac builds or need a newer PyTorch
  if [ "$OS" = "Darwin" ] && [ "$ARCH" = "x86_64" ]; then SKIP="$SKIP|comfy-angle|comfy-kitchen|comfy-aimdo"; fi
  grep -viE "^($SKIP)([<>=~ \[]|\$)" "$COMFY/requirements.txt" > "$RUNTIME/comfy-req.txt"
  [ -f "$APP/scripts/comfy-constraints-$OS-$ARCH.txt" ] && CONS=(-c "$APP/scripts/comfy-constraints-$OS-$ARCH.txt") || CONS=()
  "$VPY" -m pip install -q -r "$RUNTIME/comfy-req.txt" "${CONS[@]}"
  "$VPY" -m pip install -q certifi   # CA certificates for model downloads (python.org Python on macOS has none)
  # bridge node (model manager + hardware info)
  rm -rf "$COMFY/custom_nodes/higgs_bridge"
  cp -R "$APP/custom_nodes/higgs_bridge" "$COMFY/custom_nodes/higgs_bridge"
  if [ "$OS" = "Darwin" ] && [ "$ARCH" = "x86_64" ]; then
    cp "$APP/custom_nodes/torch22_compat.py" "$COMFY/custom_nodes/torch22_compat.py"
  fi

  if [ "$WITH_LTX" = "1" ]; then
    say "Downloading LTX-Video 2B distilled + T5 text encoder (~11.5 GB)"
    mkdir -p "$COMFY/models/checkpoints" "$COMFY/models/text_encoders"
    dl() { if [ ! -f "$2" ]; then curl -fL --retry 5 -C - -o "$2.part" "$1" && mv "$2.part" "$2"; fi; }
    dl "https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltxv-2b-0.9.8-distilled.safetensors" "$COMFY/models/checkpoints/ltxv-2b-0.9.8-distilled.safetensors"
    dl "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn_scaled.safetensors" "$COMFY/models/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors"
  fi
fi

say "Done. Start the studio with:  bash \"$APP/scripts/start.sh\""
[ "$OS" = "Darwin" ] && echo "  or double-click \"Start HIGGS Studio.command\" in the app folder."

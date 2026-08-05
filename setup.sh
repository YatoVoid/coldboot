#!/usr/bin/env bash
# Cold Boot setup for Linux. Safe to re-run, it skips what is already there.
#
#   ./setup.sh          install everything
#   ./setup.sh --check  verify only, change nothing
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPER_DIR="$ROOT/assets/piper"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1
STEP=0
TOTAL=9
FAILED=()

C_CYAN=$'\033[36m'; C_GREEN=$'\033[32m'; C_YEL=$'\033[33m'
C_RED=$'\033[31m'; C_GREY=$'\033[90m'; C_OFF=$'\033[0m'

step() { STEP=$((STEP+1)); printf '\n%s[%d/%d] %s%s\n' "$C_CYAN" "$STEP" "$TOTAL" "$1" "$C_OFF"; }
ok()   { printf '      %sOK    %s%s\n' "$C_GREEN" "$1" "$C_OFF"; }
skip() { printf '      %sSKIP  %s (already present)%s\n' "$C_GREY" "$1" "$C_OFF"; }
work() { printf '      %s...   %s%s\n' "$C_YEL" "$1" "$C_OFF"; }
bad()  { printf '      %sFAIL  %s%s\n' "$C_RED" "$1" "$C_OFF"; FAILED+=("$1"); }
have() { command -v "$1" >/dev/null 2>&1; }

MAC=0
[ "$(uname -s)" = "Darwin" ] && MAC=1

# config.json is yours and is not in the repo. start from the example.
if [ ! -f "$ROOT/config.json" ]; then
  cp "$ROOT/config.example.json" "$ROOT/config.json"
  echo "created config.json from the example. run configure.py to change the subject."
fi

# which package manager, so this works past just ubuntu
if [ "$MAC" = 1 ]; then
  if have brew; then PM="brew install"; UPDATE=":"
  else PM=""; UPDATE=":"; fi
elif have apt-get; then PM="sudo apt-get install -y";  UPDATE="sudo apt-get update -qq"
elif have dnf;     then PM="sudo dnf install -y";      UPDATE=":"
elif have pacman;  then PM="sudo pacman -S --noconfirm"; UPDATE=":"
elif have zypper;  then PM="sudo zypper install -y";   UPDATE=":"
elif have apk;     then PM="sudo apk add";             UPDATE=":"
else PM=""; UPDATE=":"; fi

echo
echo "====================================================="
if [ "$MAC" = 1 ]; then echo "  Cold Boot setup (macOS)"; else echo "  Cold Boot setup (Linux)"; fi
echo "  First run downloads about 7 GB. Give it 15-40 min."
echo "====================================================="
START=$(date +%s)

step "Creating folders"
for d in assets/piper assets/broll out logs; do
  if [ -d "$ROOT/$d" ]; then skip "$d"; else mkdir -p "$ROOT/$d"; ok "$d"; fi
done

step "Checking Python 3.10+"
if have python3; then
  PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
  if python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)'; then
    ok "python3 $PYV"
  else
    bad "python3 $PYV is too old, need 3.10+"
  fi
else
  bad "python3 not found. install it with your package manager"
fi

step "Installing ffmpeg"
if have ffmpeg; then skip "ffmpeg"
elif [ "$CHECK" = 1 ]; then bad "ffmpeg missing"
elif [ -z "$PM" ]; then
  if [ "$MAC" = 1 ]; then bad "install homebrew first, see https://brew.sh"
  else bad "unknown package manager, install ffmpeg yourself"; fi
else
  work "installing ffmpeg"
  $UPDATE >/dev/null 2>&1
  $PM ffmpeg >/dev/null 2>&1
  have ffmpeg && ok "ffmpeg installed" || bad "ffmpeg install failed"
fi

step "Installing Ollama (writes the scripts, runs offline)"
if have ollama; then skip "ollama"
elif [ "$CHECK" = 1 ]; then bad "ollama missing"
elif [ "$MAC" = 1 ]; then
  # the install.sh on ollama.com is linux only
  work "brew install ollama, then it needs 'ollama serve' running"
  [ -n "$PM" ] && $PM ollama
  have ollama && ok "ollama installed" || bad "install ollama from https://ollama.com"
else
  work "downloading from ollama.com, about 1.5 GB"
  curl -fsSL https://ollama.com/install.sh | sh
  have ollama && ok "ollama installed" || bad "ollama install failed, see https://ollama.com"
fi

step "Installing Python packages"
if [ "$CHECK" = 1 ]; then
  if python3 -c 'import requests, defusedxml, faster_whisper, googleapiclient' 2>/dev/null
    then ok "all packages importable"; else bad "some packages missing"; fi
else
  work "pip install, a few minutes"
  # debian marks the system python as externally managed, hence the fallback
  python3 -m pip install -q -r "$ROOT/requirements.txt" 2>/dev/null \
    || python3 -m pip install -q --break-system-packages -r "$ROOT/requirements.txt"
  if [ $? -eq 0 ]; then ok "packages installed"; else bad "pip failed, try a venv"; fi
fi

step "Downloading Piper (the voice engine)"
if [ -x "$PIPER_DIR/piper" ]; then skip "piper"
elif [ "$CHECK" = 1 ]; then bad "piper missing"
else
  if [ "$MAC" = 1 ]; then
    case "$(uname -m)" in
      x86_64)  ARCH=macos_x64 ;;
      arm64)   ARCH=macos_aarch64 ;;
      *) bad "no piper build for $(uname -m)"; ARCH="" ;;
    esac
  else
    case "$(uname -m)" in
      x86_64)         ARCH=linux_x86_64 ;;
      aarch64|arm64)  ARCH=linux_aarch64 ;;
      armv7l)         ARCH=linux_armv7l ;;
      *) bad "no piper build for $(uname -m)"; ARCH="" ;;
    esac
  fi
  if [ -n "$ARCH" ]; then
    work "piper_$ARCH.tar.gz"
    curl -fsSL "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_${ARCH}.tar.gz" \
      | tar -xz -C "$ROOT/assets"
    chmod +x "$PIPER_DIR/piper" 2>/dev/null
    [ -x "$PIPER_DIR/piper" ] && ok "piper unpacked" || bad "piper download failed"
  fi
fi

step "Downloading the voice model"
VOICE=$(python3 -c "import json;print(json.load(open('$ROOT/config.json'))['piper_voice'])")
# en_US-ryan-high -> en/en_US/ryan/high/en_US-ryan-high.onnx
LANG=${VOICE%%-*}; REST=${VOICE#*-}; SPEAKER=${REST%%-*}; QUALITY=${REST#*-}
FAMILY=${LANG%%_*}
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/$FAMILY/$LANG/$SPEAKER/$QUALITY/$VOICE.onnx"
for EXT in "" ".json"; do
  DEST="$PIPER_DIR/$VOICE.onnx$EXT"
  if [ -f "$DEST" ]; then skip "$VOICE.onnx$EXT"
  elif [ "$CHECK" = 1 ]; then bad "voice file missing"
  else
    work "$VOICE.onnx$EXT"
    curl -fsSL "$BASE$EXT" -o "$DEST" && ok "$VOICE.onnx$EXT" || bad "voice download failed"
  fi
done

step "Downloading the Kokoro voice model (~340 MB)"
TTS=$(python3 -c "import json;print(json.load(open('$ROOT/config.json')).get('tts','kokoro'))")
if [ "$TTS" = "piper" ]; then
  skip "not needed, config uses piper"
else
  KDIR="$ROOT/assets/kokoro"
  mkdir -p "$KDIR"
  KBASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
  for f in kokoro-v1.0.onnx voices-v1.0.bin; do
    if [ -f "$KDIR/$f" ]; then skip "$f"
    elif [ "$CHECK" = 1 ]; then bad "$f missing"
    else
      work "$f"
      curl -fsSL "$KBASE/$f" -o "$KDIR/$f" && ok "$f" || bad "could not download $f"
    fi
  done
fi

step "Pulling the language model"
MODEL=$(python3 -c "import json;print(json.load(open('$ROOT/config.json'))['model'])")
if ! have ollama; then bad "skipped, ollama not installed"
elif ollama list 2>/dev/null | grep -q "$MODEL"; then skip "$MODEL"
elif [ "$CHECK" = 1 ]; then bad "$MODEL not pulled"
else
  work "$MODEL, about 5 GB, ollama shows its own progress"
  ollama pull "$MODEL" && ok "$MODEL ready" || bad "model pull failed"
fi

MINS=$(( ($(date +%s) - START) / 60 ))
echo
echo "====================================================="
if [ ${#FAILED[@]} -eq 0 ]; then
  printf '  %sSetup complete in %d min.%s\n' "$C_GREEN" "$MINS" "$C_OFF"
else
  printf '  %sFinished in %d min with %d problem(s):%s\n' "$C_RED" "$MINS" "${#FAILED[@]}" "$C_OFF"
  for f in "${FAILED[@]}"; do printf '    %s- %s%s\n' "$C_RED" "$f" "$C_OFF"; done
fi
echo "====================================================="

echo
printf '%sSTILL NEEDED FROM YOU:%s\n' "$C_YEL" "$C_OFF"
if [ -f "$ROOT/pexels.key" ]; then printf '  %s[x] pexels.key          found%s\n' "$C_GREEN" "$C_OFF"
else printf '  %s[ ] pexels.key          free key from https://www.pexels.com/api/%s\n' "$C_YEL" "$C_OFF"; fi
if [ -f "$ROOT/client_secret.json" ]; then printf '  %s[x] client_secret.json  found%s\n' "$C_GREEN" "$C_OFF"
else printf '  %s[ ] client_secret.json  Google Cloud OAuth, see README%s\n' "$C_YEL" "$C_OFF"; fi
if [ -f "$ROOT/pexels.key" ] && [ -f "$ROOT/client_secret.json" ]; then
  printf '\n  %sNothing missing. Run: ./run_daily.sh%s\n' "$C_GREEN" "$C_OFF"
fi
echo

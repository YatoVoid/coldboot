#!/usr/bin/env bash
# Footage, then videos, then upload. Run by hand first, then from cron.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONUNBUFFERED=1
mkdir -p "$ROOT/logs"
LOG="$ROOT/logs/$(date +%Y-%m-%d_%H%M).log"

stage() {
  echo
  echo "==================================================" | tee -a "$LOG"
  echo "  [$1/3] $2  -  $(date +%H:%M:%S)"                   | tee -a "$LOG"
  echo "==================================================" | tee -a "$LOG"
}

START=$(date +%s)
echo "Cold Boot daily run, logging to $LOG"

stage 1 "Topping up stock footage"
python3 "$ROOT/broll.py"  2>&1 | tee -a "$LOG"

stage 2 "Making videos (slow, minutes per video)"
python3 "$ROOT/vidbot.py" 2>&1 | tee -a "$LOG"

stage 3 "Uploading to YouTube"
python3 "$ROOT/upload.py" 2>&1 | tee -a "$LOG"

echo
echo "=================================================="
echo "  Done in $(( ($(date +%s) - START) / 60 )) min. Log: $LOG"
echo "=================================================="

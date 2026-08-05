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
  echo "  [$1/4] $2  -  $(date +%H:%M:%S)"                   | tee -a "$LOG"
  echo "==================================================" | tee -a "$LOG"
}

START=$(date +%s)
echo "Cold Boot daily run, logging to $LOG"

# leftovers first. a run cut short by a power failure leaves a video with its
# script and audio done but no render, and those are cheap to finish.
stage 1 "Repairing anything left half done"
python3 "$ROOT/finish.py" --only-partial 2>&1 | tee -a "$LOG"

stage 2 "Topping up stock footage"
python3 "$ROOT/broll.py"  2>&1 | tee -a "$LOG"

stage 3 "Making videos (slow, minutes per video)"
python3 "$ROOT/vidbot.py" 2>&1 | tee -a "$LOG"

stage 4 "Uploading to YouTube"
python3 "$ROOT/upload.py" 2>&1 | tee -a "$LOG"

echo
echo "=================================================="
echo "  Done in $(( ($(date +%s) - START) / 60 )) min. Log: $LOG"
echo "=================================================="

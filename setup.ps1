# Cold Boot pipeline - one-command setup for Windows.
# Safe to re-run: every step checks first and skips what's already done.
#
#   .\setup.ps1            install everything
#   .\setup.ps1 -Check     verify only, change nothing

param([switch]$Check)

$ErrorActionPreference = "Stop"
$root  = $PSScriptRoot
$piper = Join-Path $root "assets\piper"
# config.json is yours and is not in the repo. start from the example.
if (-not (Test-Path (Join-Path $root "config.json"))) {
  Copy-Item (Join-Path $root "config.example.json") (Join-Path $root "config.json")
  Write-Host "created config.json from the example. run configure.py to change the subject." -ForegroundColor Yellow
}
$cfg   = Get-Content (Join-Path $root "config.json") -Raw | ConvertFrom-Json
$voice = $cfg.piper_voice
$model = $cfg.model
$step  = 0
$total = 8
$fail  = @()

function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
              [Environment]::GetEnvironmentVariable("Path","User")
}
function Step($msg) {
  $script:step++
  Write-Host ""
  Write-Host "[$script:step/$total] $msg" -ForegroundColor Cyan
}
function OK($msg)   { Write-Host "      OK    $msg" -ForegroundColor Green }
function Skip($msg) { Write-Host "      SKIP  $msg (already present)" -ForegroundColor DarkGray }
function Work($msg) { Write-Host "      ...   $msg" -ForegroundColor Yellow }
function Bad($msg)  { Write-Host "      FAIL  $msg" -ForegroundColor Red; $script:fail += $msg }
function Have($n)   { [bool](Get-Command $n -ErrorAction SilentlyContinue) }

Write-Host ""
Write-Host "=====================================================" -ForegroundColor White
Write-Host "  Cold Boot - faceless video pipeline setup" -ForegroundColor White
Write-Host "  This takes 15-40 min on first run (big downloads)." -ForegroundColor White
Write-Host "=====================================================" -ForegroundColor White
$t0 = Get-Date

# ---------------------------------------------------------------- 1 folders
Step "Creating folders"
foreach ($d in @("assets\piper","assets\broll","out","logs")) {
  $p = Join-Path $root $d
  if (Test-Path $p) { Skip $d } else { New-Item -ItemType Directory -Force -Path $p | Out-Null; OK $d }
}

# ---------------------------------------------------------------- 2 python
Step "Checking Python 3.10+"
Refresh-Path
if (Have "python") {
  $v = (python --version 2>&1) -replace "Python "
  OK "Python $v"
} else {
  Bad "Python not found. Install from https://python.org (tick 'Add to PATH'), then re-run."
}

# ---------------------------------------------------------------- 3 ffmpeg
Step "Installing ffmpeg (video encoder)"
if (Have "ffmpeg") { Skip "ffmpeg" }
elseif ($Check) { Bad "ffmpeg missing" }
else {
  Work "downloading via winget, ~100 MB, please wait"
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --disable-interactivity | Out-Null
  Refresh-Path
  if (Have "ffmpeg") { OK "ffmpeg installed" } else { Bad "ffmpeg install failed - install manually" }
}

# ---------------------------------------------------------------- 4 ollama
Step "Installing Ollama (writes the scripts, runs offline)"
if (Have "ollama") { Skip "ollama" }
elseif ($Check) { Bad "ollama missing" }
else {
  Work "downloading via winget, ~1.5 GB, this is the slow one - go make tea"
  winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements --disable-interactivity | Out-Null
  Refresh-Path
  if (Have "ollama") { OK "ollama installed" } else { Bad "ollama install failed - get it from https://ollama.com" }
}

# ---------------------------------------------------------------- 5 deps
Step "Installing Python packages"
if ($Check) {
  python -c "import requests, faster_whisper, googleapiclient" 2>$null
  if ($LASTEXITCODE -eq 0) { OK "all packages importable" } else { Bad "some packages missing" }
} else {
  Work "pip install (a few minutes)"
  python -m pip install -q -r (Join-Path $root "requirements.txt") --no-warn-script-location
  if ($LASTEXITCODE -eq 0) { OK "packages installed" } else { Bad "pip failed" }
}

# ---------------------------------------------------------------- 6 piper
Step "Downloading Piper (the voice engine)"
if (Test-Path (Join-Path $piper "piper.exe")) { Skip "piper.exe" }
elseif ($Check) { Bad "piper missing" }
else {
  Work "piper_windows_amd64.zip, ~20 MB"
  $zip = Join-Path $env:TEMP "piper.zip"
  Invoke-WebRequest "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip" -OutFile $zip
  Expand-Archive $zip -DestinationPath (Join-Path $root "assets") -Force
  Remove-Item $zip
  OK "piper unpacked"
}

Step "Downloading the voice model ($voice)"
# en_US-ryan-high  ->  en/en_US/ryan/high/en_US-ryan-high.onnx
$parts = $voice.Split("-")
$lang, $speaker, $quality = $parts[0], $parts[1], $parts[2]
$family = $lang.Split("_")[0]
$base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/$family/$lang/$speaker/$quality/$voice.onnx"
foreach ($ext in @("", ".json")) {
  $dest = Join-Path $piper "$voice.onnx$ext"
  if (Test-Path $dest) { Skip "$voice.onnx$ext" }
  elseif ($Check) { Bad "voice file missing" }
  else {
    Work "$voice.onnx$ext (~120 MB)"
    Invoke-WebRequest "$base$ext" -OutFile $dest
    OK "$voice.onnx$ext"
  }
}

# ---------------------------------------------------------------- 8 model
Step "Pulling the language model ($model, ~5 GB)"
if (-not (Have "ollama")) { Bad "skipped, ollama not installed" }
elseif ((ollama list 2>$null) -match [regex]::Escape($model)) { Skip $model }
elseif ($Check) { Bad "$model not pulled" }
else {
  Work "ollama shows a live progress bar below"
  ollama pull $model
  if ($LASTEXITCODE -eq 0) { OK "$model ready" } else { Bad "model pull failed" }
}

# ---------------------------------------------------------------- report
$mins = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
Write-Host ""
Write-Host "=====================================================" -ForegroundColor White
if ($fail.Count -eq 0) {
  Write-Host "  Setup complete in $mins min." -ForegroundColor Green
} else {
  Write-Host "  Finished in $mins min with $($fail.Count) problem(s):" -ForegroundColor Red
  $fail | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
}
Write-Host "=====================================================" -ForegroundColor White

# what still needs a human
Write-Host ""
Write-Host "STILL NEEDED FROM YOU:" -ForegroundColor Yellow
$needKey = -not (Test-Path (Join-Path $root "pexels.key"))
$needSec = -not (Test-Path (Join-Path $root "client_secret.json"))
if ($needKey) { Write-Host "  [ ] pexels.key        free key from https://www.pexels.com/api/" -ForegroundColor Yellow }
else          { Write-Host "  [x] pexels.key        found" -ForegroundColor Green }
if ($needSec) { Write-Host "  [ ] client_secret.json  Google Cloud OAuth - see README step 3" -ForegroundColor Yellow }
else          { Write-Host "  [x] client_secret.json  found" -ForegroundColor Green }
if (-not ($needKey -or $needSec)) {
  Write-Host ""
  Write-Host "  Nothing missing. Run:  .\run_daily.ps1" -ForegroundColor Green
}
Write-Host ""

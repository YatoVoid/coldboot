# The whole day's work: fetch footage -> make videos -> upload.
# Run it by hand the first few times, then let Task Scheduler do it.

$root = $PSScriptRoot
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
            [Environment]::GetEnvironmentVariable("Path","User")
$env:PYTHONUNBUFFERED = "1"          # so progress lines appear live, not in a burst

New-Item -ItemType Directory -Force -Path (Join-Path $root "logs") | Out-Null
$log = Join-Path $root ("logs\" + (Get-Date -Format "yyyy-MM-dd_HHmm") + ".log")

function Stage($n, $title) {
  $line = "  [$n/4] $title  -  $(Get-Date -Format 'HH:mm:ss')"
  Write-Host ""
  Write-Host "==================================================" -ForegroundColor Cyan
  Write-Host $line -ForegroundColor Cyan
  Write-Host "==================================================" -ForegroundColor Cyan
  $line | Out-File $log -Append -Encoding utf8
}

$t0 = Get-Date
Write-Host "Cold Boot daily run - logging to $log" -ForegroundColor White

# leftovers first. a run cut short by a power failure leaves a video with its
# script and audio done but no render, and those are cheap to finish.
Stage 1 "Repairing anything left half done"
python (Join-Path $root "finish.py") --only-partial 2>&1 | Tee-Object -FilePath $log -Append

Stage 2 "Topping up stock footage"
python (Join-Path $root "broll.py")  2>&1 | Tee-Object -FilePath $log -Append

Stage 3 "Making videos (the slow part - minutes per video)"
python (Join-Path $root "vidbot.py") 2>&1 | Tee-Object -FilePath $log -Append

Stage 4 "Uploading to YouTube"
python (Join-Path $root "upload.py") 2>&1 | Tee-Object -FilePath $log -Append

$mins = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "  Done in $mins min. Full log: $log" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green

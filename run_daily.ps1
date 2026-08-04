# The whole day's work: fetch footage -> make videos -> upload.
# Run it by hand the first few times, then let Task Scheduler do it.

$root = $PSScriptRoot
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
            [Environment]::GetEnvironmentVariable("Path","User")
$env:PYTHONUNBUFFERED = "1"          # so progress lines appear live, not in a burst

New-Item -ItemType Directory -Force -Path (Join-Path $root "logs") | Out-Null
$log = Join-Path $root ("logs\" + (Get-Date -Format "yyyy-MM-dd_HHmm") + ".log")

function Stage($n, $title) {
  $line = "  [$n/3] $title  -  $(Get-Date -Format 'HH:mm:ss')"
  Write-Host ""
  Write-Host "==================================================" -ForegroundColor Cyan
  Write-Host $line -ForegroundColor Cyan
  Write-Host "==================================================" -ForegroundColor Cyan
  $line | Out-File $log -Append -Encoding utf8
}

$t0 = Get-Date
Write-Host "Cold Boot daily run - logging to $log" -ForegroundColor White

Stage 1 "Topping up stock footage"
python (Join-Path $root "broll.py")  2>&1 | Tee-Object -FilePath $log -Append

Stage 2 "Making videos (the slow part - minutes per video)"
python (Join-Path $root "vidbot.py") 2>&1 | Tee-Object -FilePath $log -Append

Stage 3 "Uploading to YouTube"
python (Join-Path $root "upload.py") 2>&1 | Tee-Object -FilePath $log -Append

$mins = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "  Done in $mins min. Full log: $log" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green

# Cold Boot

Makes narrated tech-news videos on your own machine while you sleep.

It grabs stories off Hacker News, reads the articles, writes narration with a local LLM, speaks it with Piper, times captions with Whisper, cuts it over free stock footage, and uploads to YouTube. Nothing runs in the cloud. Nothing charges you monthly.

Every account it needs is free.

## Before you bother

This saves you the work. It does not get you an audience.

YouTube pays nothing until 1,000 subscribers and 4,000 watch hours, which for a new channel is usually 3 to 6 months out. Faceless long-form tech video pays somewhere around $2 to $8 per thousand views, so roughly $1,000/month means roughly 300,000 views/month. Most channels that get there take the better part of a year.

YouTube also removes monetisation from channels pumping out generic AI narration. This pipeline reads real sources and is told not to invent things, which helps, but it won't save you if you pick a lazy niche and never watch what comes out.

Want money this month? Wrong tool.

## Requirements

Windows 10 or 11, about 15 GB of disk, 16 GB of RAM (8 works, slower), and Python 3.10+ from [python.org](https://python.org) with "Add to PATH" ticked.

A GPU is nice but not needed. On a Ryzen 9 8945HS laptop with no dedicated GPU it takes about 11 minutes per video.

You'll also want a Pexels account and a YouTube channel. Both free.

## Setup

### Install everything

```powershell
git clone https://github.com/YatoVoid/coldboot.git
cd coldboot
.\setup.ps1
```

That pulls ffmpeg, Ollama, the Python packages, Piper, a voice model, and the LLM. It prints what it's doing, skips whatever is already there, and you can re-run it if it dies partway.

First run downloads about 7 GB. Give it 15 to 40 minutes. The model pull shows its own progress bar.

To check the install without changing anything:

```powershell
.\setup.ps1 -Check
```

### Pexels key

Sign up at <https://www.pexels.com/api/>, copy the key, drop it in a file called `pexels.key`:

```powershell
"YOUR_KEY_HERE" | Out-File -Encoding ascii pexels.key
```

Then grab an opening set of clips:

```powershell
python broll.py
```

About 40 clips, all CC0. It runs again every night so the library keeps growing and your footage stops repeating.

### YouTube access

1. Make the channel.
2. At <https://console.cloud.google.com>, create a project.
3. APIs & Services, Library, find YouTube Data API v3, enable it.
4. APIs & Services, OAuth consent screen, External, fill in what it asks, then add your own Google account under Test users.
5. Credentials, Create credentials, OAuth client ID, Desktop app, download the JSON.
6. Save it here as `client_secret.json`.

### Run

```powershell
.\run_daily.ps1
```

Footage, then videos, then upload. A browser opens once to authorise. After that it never asks again.

Uploads are set to private. Go watch them. When you're happy, change `PRIVACY` to `"public"` in `upload.py`.

### Nightly

```powershell
$a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$PWD\run_daily.ps1`""
$t = New-ScheduledTaskTrigger -Daily -At 2:00AM
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 6)
Register-ScheduledTask -TaskName "coldboot-daily" -Action $a -Trigger $t -Settings $s -Force
```

The PC has to be awake. Task Scheduler won't wake it for you. While plugged in:

```powershell
powercfg /change standby-timeout-ac 0
```

## Settings

All in `config.json`.

| Key | What it does |
|---|---|
| `videos_per_run` | Videos per night. Start at 1 or 2. |
| `target_words` | 150 words is about a minute of speech |
| `min_hn_points` | Higher means fewer, bigger stories |
| `min_article_chars` | Under this, skip the story instead of guessing at it |
| `model` | Any Ollama model. `qwen3:14b` if you have the RAM |
| `niche`, `angle` | Change these. It's the only thing stopping you being a clone |
| `encoder` | `h264_amf` for AMD, `h264_nvenc` for NVIDIA, `libx264` for CPU |

YouTube allows 6 uploads a day per project. Each costs 1,600 of a 10,000 daily quota. `upload.py` won't go over.

## How it fits together

```
broll.py    Pexels          -> assets/broll/*.mp4
vidbot.py   Hacker News     -> story, deduped against state.db
            article fetch   -> real text, not just a headline
            Ollama          -> narration
            Piper           -> wav
            faster-whisper  -> word timings
            ffmpeg          -> mp4 + metadata json
upload.py   YouTube API     -> uploaded private, logged
```

Each script self-tests without network, keys or models:

```powershell
python vidbot.py --demo
python broll.py  --demo
python upload.py --demo
```

## Keys

`.gitignore` covers `pexels.key`, `client_secret.json`, `token.json`, `*.key`, `state.db` and rendered media.

Check `git status` yourself before your first commit anyway. Don't let a stranger's gitignore be the only thing between your credentials and a public URL.

## Footage and staying unbanned

Pexels clips are CC0. Commercial use is fine, monetisation is fine, no attribution needed.

Piper is MIT, its voices are CC-BY-SA. Fine for this.

Don't swap the source for clips ripped from other YouTube channels. That's infringement, it earns Content ID claims and strikes, and it eventually takes down the channel you spent a year building.

Watch your own videos before making them public. The model is told not to invent facts, but it's an 8B model on a laptop, not an editor. If it publishes something wrong, that's on you.

## When it breaks

| Problem | Cause |
|---|---|
| `No b-roll` | Run `python broll.py`. Needs `pexels.key`. |
| Script step takes 6+ minutes | Normal on CPU. Use a smaller model. |
| `ffmpeg not recognised` | Reopen PowerShell so PATH refreshes |
| Upload 403 | Add your account under Test users on the consent screen |
| `quotaExceeded` | 6 uploads a day, that's the ceiling |
| Nothing ran overnight | Machine was asleep |

## Licence

MIT. Fork it, change the niche, make it yours.

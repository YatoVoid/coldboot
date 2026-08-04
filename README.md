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

Windows 10/11, or Linux (Debian, Ubuntu, Fedora, Arch, openSUSE, Alpine). About 15 GB of disk, 16 GB of RAM (8 works, slower), Python 3.10+.

On Windows get Python from [python.org](https://python.org) with "Add to PATH" ticked. On Linux it is almost certainly already installed.

A GPU is nice but not needed. On a Ryzen 9 8945HS laptop with no dedicated GPU it takes about 11 minutes per video.

You'll also want a Pexels account and a YouTube channel. Both free.

## Setup

### Install everything

Windows:

```powershell
git clone https://github.com/YatoVoid/coldboot.git
cd coldboot
python configure.py
.\setup.ps1
```

Linux:

```bash
git clone https://github.com/YatoVoid/coldboot.git
cd coldboot
python3 configure.py
./setup.sh
```

Either one pulls ffmpeg, Ollama, the Python packages, Piper, a voice model, and the LLM. Both print what they're doing, skip whatever is already installed, and can be re-run if they die partway.

First run downloads about 7 GB. Give it 15 to 40 minutes. The model pull shows its own progress bar.

To check the install without changing anything, use `.\setup.ps1 -Check` or `./setup.sh --check`.

The Linux script picks the right package manager for apt, dnf, pacman, zypper and apk, and grabs the matching Piper build for x86_64, aarch64 or armv7l. It will ask for sudo when it installs ffmpeg.

### Pexels key

Sign up at <https://www.pexels.com/api/>, copy the key, drop it in a file called `pexels.key`:

```powershell
"YOUR_KEY_HERE" | Out-File -Encoding ascii pexels.key
```

Then grab an opening set of clips:

```powershell
python broll.py
```

About 20 clips, all CC0. Each one is checked for brightness and re-encoded to a single format on the way in, so it takes a few minutes. It runs again every night, one search page deeper each time, so the library keeps growing and your footage stops repeating.

If you have a library from before this existed:

```powershell
python broll.py --audit      # drop duplicates and near-black clips
python broll.py --normalize  # put them all in one format
```

The normalise step matters. Clips arrive at assorted resolutions and frame rates, and concatenating mixed formats produces a video shorter than its own audio, which cuts the narration off partway.

### YouTube access

1. Make the channel.
2. At <https://console.cloud.google.com>, create a project.
3. APIs & Services, Library, find YouTube Data API v3, enable it.
4. APIs & Services, OAuth consent screen, External, fill in what it asks, then add your own Google account under Test users.
5. Credentials, Create credentials, OAuth client ID, Desktop app, download the JSON.
6. Save it here as `client_secret.json`.

### Run

`.\run_daily.ps1` on Windows, `./run_daily.sh` on Linux.

Footage, then videos, then upload. A browser opens once to authorise. After that it never asks again.

On a headless server there is no browser to open, so it prints the URL instead. Forward the port from your own machine first:

```bash
ssh -L 8080:localhost:8080 user@thatbox
```

Uploads are set to private. Go watch them. When you're happy, change `PRIVACY` to `"public"` in `upload.py`.

### Nightly

Windows:

```powershell
$a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$PWD\run_daily.ps1`""
$t = New-ScheduledTaskTrigger -Daily -At 2:00AM
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 6)
Register-ScheduledTask -TaskName "coldboot-daily" -Action $a -Trigger $t -Settings $s -Force
```

The PC has to be awake. Task Scheduler won't wake it. While plugged in: `powercfg /change standby-timeout-ac 0`.

Linux, add to `crontab -e`:

```
0 2 * * * /full/path/to/coldboot/run_daily.sh >> /full/path/to/coldboot/logs/cron.log 2>&1
```

Cron gets a bare PATH, so if ollama or ffmpeg are somewhere unusual, set `PATH=` at the top of the crontab. A laptop that suspends will skip the run, same as Windows.

## Making it yours

Nothing here is tied to tech. Run the wizard and pick a subject:

```powershell
python configure.py
```

It asks what the channel is about, who watches, how it should be written, which voice, and how many videos a night. Then it writes `config.json`.

Presets to start from:

| Preset | Subject | Stories from |
|---|---|---|
| `tech-news` | AI and technology | Hacker News |
| `science` | research findings | phys.org, ScienceDaily, Quanta |
| `space` | astronomy and missions | NASA, Space.com, SpaceNews |
| `gaming` | game industry news | Eurogamer, RPS, PC Gamer |
| `finance` | business and markets | MarketWatch, FT, Dow Jones |

Load one directly with `python configure.py space`, list them with `--list`, check your config with `--check`.

### Your own subject

Point it at any RSS feed. Most news sites and blogs have one.

```json
"source": {
  "type": "rss",
  "feeds": ["https://example.com/feed", "https://another.com/rss"],
  "limit": 40
}
```

Three source types ship: `rss` (any feeds), `hackernews` (front page, filter with `min_points`), and `reddit` (`subreddits`, `period`). Reddit works through their RSS endpoint since the JSON API now needs OAuth, and it gets rate limited easily, so prefer `rss` when the subject has news sites covering it.

To add a source they don't cover, write a function in `sources.py` that returns `{title, url, score}` and add it to `FETCHERS`. That's the whole interface.

Change `broll_queries` to match the subject or your footage will not fit the words.

### Everything else

| Key | What it does |
|---|---|
| `videos_per_run` | Videos per night. Start at 1 or 2. |
| `target_words` | 150 words is about a minute of speech |
| `min_article_chars` | Under this, skip the story instead of guessing at it |
| `model` | Any Ollama model. `qwen3:14b` if you have the RAM |
| `niche`, `angle` | What the writing sounds like. Worth real thought |
| `piper_voice` | Any [Piper voice](https://huggingface.co/rhasspy/piper-voices). Setup downloads whichever you name |
| `bitrate` | `8M` looks good, `5M` halves upload size for no visible loss |
| `encoder` | `auto` probes ffmpeg. Force it with `h264_nvenc`, `h264_amf`, `h264_qsv` or `libx264` |
| `font` | `auto` means Arial on Windows, DejaVu Sans on Linux |
| `youtube_category` | 28 science/tech, 20 gaming, 25 news, 27 education |

YouTube allows 6 uploads a day per project. Each costs 1,600 of a 10,000 daily quota. `upload.py` won't go over.

## How it fits together

```
broll.py    Pexels          -> assets/broll/*.mp4
sources.py  rss/hn/reddit   -> candidate stories
vidbot.py   pick one        -> deduped against state.db
            article fetch   -> real text, not just a headline
            Ollama          -> narration
            Piper           -> wav
            faster-whisper  -> word timings
            ffmpeg          -> mp4 + metadata json
upload.py   YouTube API     -> uploaded private, logged
```

Each script self-tests without network, keys or models:

```powershell
python vidbot.py    --demo
python sources.py   --demo
python configure.py --demo
python broll.py     --demo
python upload.py    --demo
```

To see what your source would pick up today, without making anything:

```powershell
python sources.py
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
| `ffmpeg not recognised` | Reopen the terminal so PATH refreshes |
| `bad interpreter: ^M` | The .sh got CRLF endings. `sed -i 's/\r$//' *.sh` |
| `externally-managed-environment` | Debian/Ubuntu pip guard. setup.sh retries with `--break-system-packages`, or use a venv |
| No captions on Linux | Install fonts: `sudo apt install fonts-dejavu` |
| Upload 403 | Add your account under Test users on the consent screen |
| `quotaExceeded` | 6 uploads a day, that's the ceiling |
| Nothing ran overnight | Machine was asleep |

## Licence

MIT. Fork it, change the niche, make it yours.

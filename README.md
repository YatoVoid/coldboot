# Cold Boot

Makes narrated news videos on your own machine while you sleep.

It picks stories off a feed you choose, reads the articles, writes narration with a local LLM, speaks it with Piper, times captions with Whisper, cuts it over free stock footage, and uploads to YouTube. Nothing runs in the cloud. Nothing charges you monthly.

Every account it needs is free. Runs on Windows and Linux.

## Before you bother

This automates the work. It does not get you an audience.

YouTube pays nothing until 1,000 subscribers and 4,000 watch hours. For a new channel that is realistically 3 to 6 months away. Faceless long-form video earns roughly $2 to $8 per thousand views, so about $1,000 a month means about 300,000 views a month, and most channels that get there take the better part of a year.

YouTube also demonetises channels pumping out generic AI narration. This reads real sources and is told not to invent things, which helps. It will not save you if you pick a lazy subject and never watch what comes out.

Want money this month? Wrong tool.

## Requirements

Windows 10/11, or Linux (Debian, Ubuntu, Fedora, Arch, openSUSE, Alpine). About 15 GB of disk to start, 16 GB of RAM (8 works, slower), Python 3.10 or newer.

On Windows get Python from [python.org](https://python.org) with "Add to PATH" ticked. On Linux it is already there.

A GPU helps but is not needed. On a Ryzen 9 8945HS laptop with no dedicated GPU, one video takes about 11 minutes.

---

# Setup

## 1. Install

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

`configure.py` asks what the channel is about and writes `config.json`. `setup.ps1` / `setup.sh` installs ffmpeg, Ollama, the Python packages, Piper, a voice model and the language model.

First run downloads about 7 GB and takes 15 to 40 minutes. It prints each step, skips anything already installed, and you can re-run it if it dies partway. On Linux it asks for sudo when installing ffmpeg.

Check the install without changing anything:

```
.\setup.ps1 -Check          # windows
./setup.sh --check          # linux
```

## 2. Pexels key

Free, no card, takes two minutes. Sign up at <https://www.pexels.com/api/>, copy the key, and save it as `pexels.key` in this folder with nothing else in the file.

```powershell
"YOUR_KEY_HERE" | Out-File -Encoding ascii pexels.key
```

Then get an opening set of clips:

```
python broll.py
```

## 3. YouTube access

1. Make the channel.
2. At <https://console.cloud.google.com>, create a project.
3. **APIs & Services → Library**, find **YouTube Data API v3**, enable it.
4. **APIs & Services → OAuth consent screen**, choose External, fill in what it asks.
5. Under **Audience**, add the Google account that owns the channel to **Test users**. Skip this and sign-in fails with `Error 403: access_denied`.
6. Still under **Audience**, press **Publish app** so the status reads *In production*.
7. **Credentials → Create credentials → OAuth client ID → Desktop app**, download the JSON.
8. Save it here as `client_secret.json`.

Google calls the app unverified when you sign in. That is normal for a personal app. Click **Advanced**, then the "go to (unsafe)" link. It is your app talking to your own channel.

**Step 6 is not optional.** While the app sits in Testing, Google expires the login after 7 days, so a nightly upload works for a week and then quietly stops. Publishing needs no Google review. Verification only decides whether strangers see the warning screen, and an unverified production app still works for up to 100 users.

---

# Commands

Run these from the project folder. On Linux use `python3`.

| Command | What it does |
|---|---|
| `python status.py` | When the next run is, what is queued, what went up. Changes nothing |
| `python configure.py` | Asks what the channel is about, writes `config.json` |
| `python configure.py space` | Loads a preset without asking anything |
| `python configure.py --list` | Lists the presets |
| `python configure.py --check` | Says whether `config.json` is valid |
| `python sources.py` | Prints the stories your source would offer today. Makes nothing |
| `python broll.py` | Downloads new stock footage |
| `python broll.py --audit` | Removes duplicate and near-black clips already downloaded |
| `python broll.py --normalize` | Re-encodes the clip library to one format |
| `python vidbot.py` | Makes videos. Does not upload |
| `python upload.py` | Uploads what is waiting. Makes nothing |
| `python finish.py` | Repairs half-built videos after a crash, then carries on |
| `.\run_daily.ps1` / `./run_daily.sh` | All three stages: footage, videos, upload |
| `<script> --demo` | Self-test. No network, no keys, no models, changes nothing |

## Checking on it

```
python status.py
```

```
  next run    8/6/2026 2:00:00 AM
  last run    8/5/2026 2:00:01 AM  ok

  waiting to upload   11 videos, 2.9 GB
      next up: ...
      and 5 more after that, 6 go per day

  uploaded            6 total, 6 in the last 24h
      quota left today: 0 of 6
```

`last run ok` means the scheduler reported success. Anything else prints the failure code. This is the one command to run when you want to know whether it is still working.

## What each one actually does

**`python broll.py`**
Searches Pexels for the terms in `broll_queries`, one page deeper each run so the library keeps growing. Every clip is checked for brightness and re-encoded to one resolution and frame rate on the way in, which is why it is not instant. Rejected clip IDs are remembered so they are not downloaded twice. Writes to `assets/broll/`. Needs `pexels.key`.

**`python vidbot.py`**
Fetches candidate stories, skips any already used, downloads the article text, and refuses the story if too little text comes back rather than inventing one. Then writes narration with Ollama, speaks it with Piper, times captions with Whisper, and renders with ffmpeg. Writes `.txt`, `.wav`, `.ass`, `.mp4` and `.json` per video into `out/`. Records used stories in `state.db`.

It uploads nothing. A story that fails is skipped and the next one is tried.

**`python upload.py`**
Uploads everything waiting in `out/`, up to 6 a day. Prints percentage, speed and time left as it goes. After each success it records the video in `state.db` and **moves the video and its files into `out/uploaded/`**. Nothing is deleted, ever. You decide what to keep.

Videos go up **private**. They appear in YouTube Studio under Content, marked Private, visible to you and nobody else.

Only one copy runs at a time. It writes `upload.lock` while working and refuses to start if another upload is already going, because two uploaders reading the same folder both see the same queue and put every video on the channel twice. If a run is killed the lock is left behind, and the next run notices the process is gone and clears it.

**`run_daily.ps1` / `run_daily.sh`**
Runs `broll.py`, then `vidbot.py`, then `upload.py`, and tees everything into `logs/`.

## What it never does

- Never uploads anything public unless you change `PRIVACY` in `upload.py`
- Never deletes a video you made
- Never uploads more than 6 a day, which is the YouTube API ceiling
- Never covers the same story twice
- Never writes about an article it could not read

---

# Where things end up

```
config.json          what the channel is about
pexels.key           your key, never committed
client_secret.json   your google credentials, never committed
token.json           your login, written on first upload, never committed
state.db             stories used and videos uploaded

assets/broll/        the clip library
out/                 finished videos waiting to upload
out/uploaded/        videos already on youtube, kept for you to sort
logs/                one file per run
```

Each video is five files sharing a name: `.txt` the script, `.wav` the narration, `.ass` the captions, `.mp4` the video, `.json` the title and description. They move to `out/uploaded/` together.

**Worth backing up.** If you ever wipe the machine, the code comes back from git but these do not: `pexels.key`, `client_secret.json`, `token.json` and `state.db`. Losing `state.db` means it forgets which stories it covered and which videos went up, so it will cover old ground again. Copy those four somewhere safe.

**Disk fills up.** Six videos a night at the default bitrate is roughly 1 GB a day, and nothing is removed automatically. Empty `out/uploaded/` yourself when you want the space back. Deleting from there is safe; `state.db` remembers what already went up, so nothing gets re-uploaded.

---

# Making it yours

Nothing here is tied to tech. Run `python configure.py` and pick a subject, or start from a preset:

| Preset | Subject | Stories from |
|---|---|---|
| `tech-news` | AI and technology | Hacker News |
| `science` | research findings | phys.org, ScienceDaily, Quanta |
| `space` | astronomy and missions | NASA, Space.com, SpaceNews |
| `gaming` | game industry news | Eurogamer, RPS, PC Gamer |
| `finance` | business and markets | MarketWatch, FT, Dow Jones |

## Your own subject

Point it at any RSS feed. Most news sites and blogs have one.

```json
"source": {
  "type": "rss",
  "feeds": ["https://example.com/feed", "https://another.com/rss"],
  "limit": 40
}
```

Three source types ship:

- `rss` takes any list of `feeds`
- `hackernews` takes `min_points`
- `reddit` takes `subreddits` and `period`

Reddit goes through their RSS endpoint because the JSON API now needs OAuth, and it gets rate limited quickly. Prefer `rss` when news sites cover your subject.

To add a source of your own, write a function in `sources.py` returning `{title, url, score}` and add it to `FETCHERS`. That is the whole interface.

Change `broll_queries` to match the subject or the footage will not fit the words.

## Config

| Key | What it does |
|---|---|
| `niche`, `audience`, `angle` | What the writing sounds like. Worth real thought |
| `source` | Where stories come from, see above |
| `broll_queries` | Stock footage searches |
| `videos_per_run` | Videos per night. Start at 1 or 2 |
| `target_words` | 150 words is about a minute of speech |
| `min_article_chars` | Under this, skip the story instead of guessing at it |
| `model` | Any Ollama model. `qwen3:14b` if you have the RAM |
| `piper_voice` | Any [Piper voice](https://huggingface.co/rhasspy/piper-voices). Setup downloads whichever you name |
| `bitrate` | `5M` is the default. `8M` looks slightly better and costs 60% more upload |
| `encoder` | `auto` test-encodes a few frames and picks what works. Force with `h264_nvenc`, `h264_amf`, `h264_qsv` or `libx264` |
| `font` | `auto` means Arial on Windows, DejaVu Sans on Linux |
| `youtube_category` | 28 science and tech, 20 gaming, 25 news, 27 education |
| `min_brightness` | Clips darker than this are thrown away |

---

# Running it nightly

Windows:

```powershell
$a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$PWD\run_daily.ps1`""
$t = New-ScheduledTaskTrigger -Daily -At 2:00AM
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
     -DontStopIfGoingOnBatteries -WakeToRun -RestartCount 2 `
     -RestartInterval (New-TimeSpan -Minutes 30) `
     -ExecutionTimeLimit (New-TimeSpan -Hours 6)
Register-ScheduledTask -TaskName "coldboot-daily" -Action $a -Trigger $t -Settings $s -Force
```

What those settings buy you:

- `WakeToRun` wakes the machine from sleep at 2am. It cannot wake it from a full shutdown, nothing can.
- `StartWhenAvailable` runs a missed job as soon as the machine is next up, so a night switched off is caught up on rather than skipped.
- The battery flags let it start and keep running on battery.
- `RestartCount` retries twice, half an hour apart, if the run fails.

The task survives reboots. It is stored by Windows, not by this folder.

By default the task runs only while your user is logged on. A locked screen is fine, but if you sign out it waits. To run regardless, open Task Scheduler, find the task, and pick "Run whether user is logged on or not".

Check on it any time:

```powershell
Get-ScheduledTaskInfo -TaskName "coldboot-daily"
```

`LastTaskResult` of 0 means the last run succeeded.

Linux, in `crontab -e`:

```
0 2 * * * /full/path/to/coldboot/run_daily.sh >> /full/path/to/coldboot/logs/cron.log 2>&1
```

Cron gets a bare PATH, so add `PATH=` at the top of the crontab if ollama or ffmpeg live somewhere unusual.

## Going public

Videos upload private on purpose. Watch a few. When you are happy, edit `upload.py`:

```python
PRIVACY = "public"
```

Only new uploads are affected. Change the earlier ones in YouTube Studio.

---

# When it breaks

| Problem | Cause |
|---|---|
| `403: access_denied` when signing in | Account is not in Test users, setup step 5 |
| Uploads stop after about a week | App still in Testing, setup step 6 |
| `quotaExceeded` | 6 uploads a day is the ceiling |
| `No b-roll` | Run `python broll.py`. Needs `pexels.key` |
| Upload seems frozen | It prints progress now. Slow uploads are just slow |
| `upload.py is already running` | Another upload is going, or the nightly job is. Wait, or delete `upload.lock` if the pid is really gone |
| Duplicate videos on the channel | Two uploads ran at once. Delete the extras in YouTube Studio |
| Video shorter than its audio | Run `python broll.py --normalize` |
| Script step takes 6+ minutes | Normal on CPU. Use a smaller model |
| `ffmpeg not recognised` | Reopen the terminal so PATH refreshes |
| `bad interpreter: ^M` | The .sh got CRLF endings. `sed -i 's/\r$//' *.sh` |
| `externally-managed-environment` | Debian pip guard. setup.sh retries with `--break-system-packages` |
| No captions on Linux | `sudo apt install fonts-dejavu` |
| Nothing ran overnight | Machine was asleep |

Every script has a self-test that needs no network, no keys and no models:

```
python vidbot.py --demo
python sources.py --demo
python configure.py --demo
python broll.py --demo
python upload.py --demo
```

---

# Keys

`.gitignore` covers `pexels.key`, `client_secret.json`, `token.json`, `*.key`, `state.db` and all rendered media.

Check `git status` yourself before your first commit anyway. Never let someone else's gitignore be the only thing between your credentials and a public URL.

# Footage and staying unbanned

Pexels clips are CC0. Commercial use is fine, monetisation is fine, no attribution needed. Piper is MIT and its voices are CC-BY-SA.

Do not swap the source for clips ripped from other YouTube channels. That is infringement, it earns Content ID claims and strikes, and it eventually takes down the channel you spent a year building.

Watch your own videos before making them public. The model is told not to invent facts, but it is an 8B model on a laptop, not an editor. If it publishes something wrong, that is on you.

# Licence

MIT. Fork it, change the subject, make it yours.

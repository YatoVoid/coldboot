# Cold Boot

Makes narrated news videos on your own machine while you sleep.

It picks stories off a feed you choose, reads the articles, writes narration with a local LLM, speaks it with Kokoro, times captions with Whisper, cuts it over free stock footage, and uploads to YouTube. Nothing runs in the cloud. Nothing charges you monthly.

Every account it needs is free. Runs on Windows, Linux and macOS.

## Before you bother

This automates the work. It does not get you an audience.

YouTube pays nothing until 1,000 subscribers and 4,000 watch hours. For a new channel that is realistically 3 to 6 months away. Faceless long-form video earns roughly $2 to $8 per thousand views, so about $1,000 a month means about 300,000 views a month, and most channels that get there take the better part of a year.

YouTube also demonetises channels pumping out generic AI narration. This reads real sources and is told not to invent things, which helps. It will not save you if you pick a lazy subject and never watch what comes out.

Want money this month? Wrong tool.

## Requirements

Windows 10/11, Linux (Debian, Ubuntu, Fedora, Arch, openSUSE, Alpine), or macOS. About 15 GB of disk to start, 16 GB of RAM (8 works, slower), Python 3.10 or newer.

On Windows get Python from [python.org](https://python.org) with "Add to PATH" ticked. On Linux it is already there. On macOS you need [Homebrew](https://brew.sh) before running setup.

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

Linux and macOS:

```bash
git clone https://github.com/YatoVoid/coldboot.git
cd coldboot
python3 configure.py
./setup.sh
```

`setup.sh` picks the right package manager for apt, dnf, pacman, zypper, apk and Homebrew, and the right Piper build for x86_64, aarch64, armv7l and Apple silicon.

`configure.py` asks what the channel is about and writes `config.json`. `setup.ps1` / `setup.sh` installs ffmpeg, Ollama, the Python packages, the Kokoro voice model, Piper as a fallback, and the language model.

First run downloads about 7 GB and takes 15 to 40 minutes. It prints each step, skips anything already installed, and you can re-run it if it dies partway. On Linux it asks for sudo when installing ffmpeg.

Check the install without changing anything:

```
.\setup.ps1 -Check          # windows
./setup.sh --check          # linux and macos
```

Setup creates `config.json` from `config.example.json` if you have not run `configure.py`. Your `config.json` is yours and is not tracked by git, so your settings never get overwritten by an update.

Anything missing from your config falls back to the matching value in `config.example.json`. So an update that adds a new setting will not break a config you wrote months ago, and everything runs before you have made one at all. `python settings.py` prints what is in use and whether each value came from you or the default.

That fallback is top level only. Your `source` block is taken exactly as written rather than merged, because an `rss` block merged onto the `hackernews` default would pick up `min_points`, which means nothing for a feed. Settings read from inside `source` carry their own defaults instead.

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
| `python settings.py` | Every setting in use, and whether it is yours or a default |
| `python voices.py` | Lists the voices worth using and shows which one you have |
| `python voices.py --try` | Renders a sample of each so you can listen and compare |
| `python voices.py --set <name>` | Downloads that voice and puts it in `config.json` |
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
| `python finish.py` | Repairs half-built videos after a crash, then makes more |
| `python finish.py --only-partial` | Repairs only, makes nothing new |
| `.\run_daily.ps1` / `./run_daily.sh` | All four stages: repair, footage, videos, upload |
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
First it counts what is already waiting in `out/`. Uploads are capped at 6 a day, so if the queue is already full it makes nothing and says so. That is deliberate: making more than you can publish means every story goes out days after it happened, which is worthless on a news channel. `max_queue` in `config.json` controls the ceiling.

Then it fetches candidate stories, skips any already used, downloads the article text, and refuses the story if too little text comes back rather than inventing one.

Two stories count as the same if their headlines share the same significant words, so the same event picked up from a second feed, or reworded slightly, does not become a second video. Then writes narration with Ollama, speaks it with Kokoro, times captions with Whisper, and renders with ffmpeg. Writes `.txt`, `.wav`, `.ass`, `.mp4` and `.json` per video into `out/`. Records used stories in `state.db`.

It uploads nothing. A story that fails is skipped and the next one is tried.

**`python upload.py`**
Uploads everything waiting in `out/`, up to 6 a day. Prints percentage, speed and time left as it goes. After each success it records the video in `state.db` and **moves the video and its files into `out/uploaded/`**. Nothing is deleted, ever. You decide what to keep.

Videos go up **private** until you say otherwise, set by `privacy` in `config.json`. Private ones appear in YouTube Studio under Content, visible to you and nobody else. See "Going public" below.

Only one copy runs at a time. It writes `upload.lock` while working and refuses to start if another upload is already going, because two uploaders reading the same folder both see the same queue and put every video on the channel twice. If a run is killed the lock is left behind, and the next run notices the process is gone and clears it.

**`run_daily.ps1` / `run_daily.sh`**
Four stages, tee'd into `logs/`: repair anything left half done, top up footage, make videos, upload. Repair goes first so a run cut short last night is finished before new work starts.

## Picking a voice

Two engines ship. Both are free, both run offline, neither sends your text anywhere.

**Kokoro** is the default and sounds close to a real narrator. **Piper** is the fallback, roughly twice as fast to generate but clearly synthetic. On a laptop CPU, Kokoro turns a 1,100 word script into 6.5 minutes of audio in about 2.5 minutes, so it adds a minute or so per video against Piper.

Hear them on your own writing:

```
python voices.py --try
```

That reads 70 words of one of your actual scripts in each voice and drops the wavs in `out/voices/`. Play them, then:

```
python voices.py --set am_eric
```

`--set` works out which engine the name belongs to and switches to it. New videos use it. Existing ones keep the voice they were made with.

### Kokoro voices

`a` is American, `b` is British, `m` is male, `f` is female.

| Voice | Sounds like |
|---|---|
| `am_eric` | US male, natural and level. the default |
| `am_michael` | US male, warmer |
| `am_adam` | US male, deeper |
| `am_puck` | US male, lighter and quicker |
| `af_heart` | US female, warm |
| `af_bella` | US female, clear and bright |
| `bm_george` | UK male, measured |
| `bf_emma` | UK female, calm |

Run `python voices.py` for the full shortlist, and see the [Kokoro model card](https://huggingface.co/hexgrad/Kokoro-82M) for every voice including other languages.

### Piper voices

Worth it if generation speed matters more to you than sound, or the machine is weak. `en_US-lessac-high` is the best of them. `high` in the name means a bigger model and better audio. Any voice from [the Piper list](https://huggingface.co/rhasspy/piper-voices) works, named exactly as the file is, and `--set` fetches it.

### Pacing

| Key | Effect |
|---|---|
| `speech_rate` | Kokoro: above 1 is faster, below 1 is slower. Piper: the opposite, above 1 is slower |
| `sentence_silence` | Piper only. Seconds of pause between sentences |

Note the two engines read `speech_rate` in opposite directions, which is how each library defines it. Kokoro at `1.0` runs near 170 words a minute, which is a normal narration pace.

### Switching engines by hand

```json
"tts": "kokoro",
"kokoro_voice": "am_eric"
```

Set `"tts": "piper"` to go back. Setup skips the 340 MB Kokoro download when the config asks for Piper.

## If the power cuts out mid-run

Nothing is lost and nothing broken gets published. Turn the machine back on and it sorts itself out on the next run.

Every file is written under a temporary name and renamed into place at the end. A rename either happens or it does not, so a power cut leaves the previous file or nothing, never a half written one pretending to be finished.

What survives depends on how far it got:

| Cut during | What happens next run |
|---|---|
| Writing the script | Story was never marked as covered, so it is picked again |
| Speaking the narration | Script is kept, audio is re-recorded. The slow LLM step is not repeated |
| Rendering | Script and audio kept, only the render is redone |
| After render, before metadata | `finish.py` writes the metadata and it uploads normally |
| Uploading | Nothing is recorded until YouTube confirms, so it re-uploads from the start. No duplicate, no half video |

`run_daily` repairs leftovers before it does anything else, so this needs no command from you.

Two extra guards. Before publishing, a video is compared against its own narration and skipped if it is shorter, because a truncated video is still a playable file and publishing one is worse than waiting a day. And the database uses write-ahead logging with full syncing, so a cut during a write does not corrupt the record of what has been covered and uploaded.

The one thing worth having is a UPS, or just running on a laptop. A battery turns a power cut into nothing at all.

## What it never does

- Never uploads anything public unless you set `privacy` in `config.json`
- Never deletes a video you made
- Never uploads more than 6 a day, which is the YouTube API ceiling
- Never covers the same story twice, even from a different site or reworded
- Never writes about an article it could not read
- Never builds a backlog. If 6 are already waiting it makes none
- Never publishes a video shorter than its own narration
- Never leaves a half written file behind a real filename

---

# Where things end up

```
config.json          your settings, not tracked by git
config.example.json  the starting point setup copies from
pexels.key           your key, never committed
client_secret.json   your google credentials, never committed
token.json           your login, written on first upload, never committed
state.db             stories used and videos uploaded

assets/broll/        the clip library
assets/kokoro/       the voice model, 340 MB
assets/piper/        the fallback voice engine
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
| `max_queue` | Stop making videos once this many are waiting. Keep it equal to the 6 a day upload limit so nothing publishes late |
| `model` | Any Ollama model. `qwen3:14b` if you have the RAM |
| `tts` | `kokoro` sounds better, `piper` generates faster |
| `kokoro_voice` | Set it with `voices.py`. `am_eric` by default |
| `piper_voice` | Used only when `tts` is `piper` |
| `speech_rate` | Kokoro: above 1 is faster. Piper: above 1 is slower |
| `sentence_silence` | Piper only. Pause between sentences in seconds |
| `bitrate` | `5M` is the default. `8M` looks slightly better and costs 60% more upload |
| `encoder` | `auto` test-encodes a few frames and picks what works. Force with `h264_nvenc`, `h264_amf`, `h264_qsv` or `libx264` |
| `font` | `auto` means Arial on Windows, DejaVu Sans elsewhere |
| `youtube_category` | 28 science and tech, 20 gaming, 25 news, 27 education |
| `min_brightness` | Clips darker than this are thrown away |
| `privacy` | `private`, `unlisted` or `public`. Starts private on purpose |

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

Videos upload private on purpose, so the first thing a fresh install does is not publish unreviewed video to a real channel.

Watch a few. When you are happy, set this in `config.json`:

```json
"privacy": "public"
```

`private`, `unlisted` and `public` all work. Anything else is treated as `private`.

Only new uploads are affected. Change earlier ones in YouTube Studio.

Be clear with yourself about what this switch means. After it, a machine writes and publishes to your audience nightly with nobody reading it first. If a script gets a fact wrong, it is wrong in public under your name. That is a reasonable trade, but make it on purpose.

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
| `config.json` not found | Run `python configure.py`, or copy `config.example.json` over it |
| Uploads went public unexpectedly | `privacy` in `config.json`. It ships as `private` |
| Nothing ran overnight | Machine was asleep |
| Voice sounds robotic | You are probably on Piper. `python voices.py --set am_eric` |
| `Kokoro model missing` | Run setup again, or set `"tts": "piper"` in `config.json` |

Every script has a self-test that needs no network, no keys and no models:

```
python vidbot.py    --demo
python sources.py   --demo
python configure.py --demo
python broll.py     --demo
python upload.py    --demo
python status.py    --demo
python voices.py    --demo
python settings.py  --demo
python finish.py    --demo
```

All nine should print `demo ok`, on a clean clone with no config yet. GitHub Actions runs them on every push across Windows, Linux and macOS on Python 3.10 and 3.13. If they do, the code is fine and the problem is setup, keys or network.

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

"""fetch -> script -> voice -> subs -> render.

    python vidbot.py          make today's videos
    python vidbot.py --demo   self-check, no network needed
"""
import json, os, random, re, sqlite3, subprocess, sys, time
from pathlib import Path

import sources

ROOT = Path(__file__).parent
# utf-8-sig so a config saved by notepad or powershell keeps working
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
OUT = ROOT / "out"
ASSETS = ROOT / "assets"
BROLL = ASSETS / "broll"
WINDOWS = sys.platform == "win32"
PIPER = ASSETS / "piper" / ("piper.exe" if WINDOWS else "piper")

# hardware encoders we'd rather have, best first. amf is amd, nvenc nvidia,
# qsv intel. libx264 is cpu and works everywhere. vaapi is deliberately left
# out, it needs device setup and format juggling that isn't worth it here.
# each wants its own speed/quality flag, hence the second table.
ENCODERS = ["h264_nvenc", "h264_amf", "h264_qsv", "libx264"]
ENC_ARGS = {"h264_nvenc": ["-preset", "p5"],
            "h264_amf": ["-quality", "quality"],
            "h264_qsv": ["-preset", "medium"],
            "libx264": ["-preset", "medium"]}


_ENCODER = None


def encoder_works(name):
    """Encode a couple of frames for real.

    Listing an encoder proves nothing. Most ffmpeg builds ship nvenc, amf and
    qsv compiled in whatever gpu you have, and they only fail when you use them.
    """
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", "testsrc=size=320x240:rate=5:duration=0.4",
             "-c:v", name, *ENC_ARGS.get(name, []), "-f", "null", "-"],
            capture_output=True, timeout=60)
    except FileNotFoundError:
        sys.exit("ffmpeg is not on PATH. Run setup, then reopen your terminal.")
    except subprocess.TimeoutExpired:
        return False
    return r.returncode == 0


def pick_encoder():
    """First encoder this machine can actually use. Probed once per run."""
    global _ENCODER
    want = CFG.get("encoder", "auto")
    if want != "auto":
        return want
    if _ENCODER is None:
        _ENCODER = next((e for e in ENCODERS if encoder_works(e)), "libx264")
    return _ENCODER


def pick_font():
    """Arial does not exist on most Linux boxes, DejaVu does not ship on Windows."""
    want = CFG.get("font", "auto")
    if want != "auto":
        return want
    return "Arial" if WINDOWS else "DejaVu Sans"


def db():
    c = sqlite3.connect(ROOT / "state.db")
    # write-ahead logging survives a power cut mid-write far better than the
    # default journal, and this machine is expected to lose power sometimes.
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=FULL")
    c.execute("CREATE TABLE IF NOT EXISTS seen (url TEXT PRIMARY KEY, title TEXT, ts INT)")
    return c


def write_atomic(path, text):
    """Write to a temp name and rename over the target.

    Rename is atomic, so a power cut leaves either the old file or the new one,
    never a half written one that later looks finished.
    """
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return path


def complete(name):
    """A video counts as finished only with a playable mp4 and its metadata."""
    mp4, js = OUT / f"{name}.mp4", OUT / f"{name}.json"
    if not (mp4.exists() and js.exists()):
        return False
    try:
        return duration(mp4) > 5
    except Exception:
        return False


# ---------------------------------------------------------------- sourcing
STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "is", "are",
        "with", "how", "why", "what", "show", "hn", "ask"}


def topic_key(title):
    """Loose fingerprint of a headline, so the same story from two feeds and
    lightly reworded follow-ups both collapse onto one key."""
    words = re.findall(r"[a-z0-9]+", title.lower())
    keep = sorted(w for w in words if w not in STOP and len(w) > 2)
    return " ".join(keep[:8])


def pick_stories(n):
    """Stories from whichever source config.json names, minus ones already used."""
    con, out = db(), []
    seen_keys = {topic_key(t) for (t,) in con.execute("SELECT title FROM seen")}
    for s in sources.fetch(CFG["source"]):
        if not s["url"] or not s["title"]:
            continue
        if con.execute("SELECT 1 FROM seen WHERE url=?", (s["url"],)).fetchone():
            continue
        key = topic_key(s["title"])
        if key in seen_keys:           # same story, different link
            continue
        seen_keys.add(key)             # and not twice within one batch either
        out.append(s)
        if len(out) >= n:
            break
    return out


def mark_done(story):
    con = db()
    con.execute("INSERT OR REPLACE INTO seen VALUES (?,?,?)",
                (story["url"], story["title"], int(time.time())))
    con.commit()


# ---------------------------------------------------------------- scripting
def fetch_article(url):
    """Grab the article body. Feed the model only a headline and it makes things up.

    Regex de-tagging is crude. trafilatura does it properly if this isn't enough.
    """
    import requests
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    if "html" not in r.headers.get("content-type", ""):
        return ""
    h = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", r.text)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = re.sub(r"&(nbsp|amp|lt|gt|quot|#39);", " ", h)
    return re.sub(r"\s+", " ", h).strip()[:6000]


PROMPT = """You are writing narration for a YouTube video. Niche: {niche}.
Audience: {audience}. Editorial angle: {angle}

Story headline: {title}
Source: {url}

The actual article text follows. Base the video ONLY on this. Do not invent
studies, model names, numbers, quotes or events that are not stated here.
If something is unclear, say less rather than guessing.
---
{article}
---

Write ONLY the spoken narration. Rules:
- About {words} words. This is read aloud, so write for the ear.
- First 15 words must state the concrete thing that happened. No "in today's video",
  no "welcome back", no rhetorical questions, no "imagine if".
- Explain the actual mechanism. Assume the viewer is smart but not in the field.
- Take a clear position on whether this matters and why. Being boring is the only real risk.
- No markdown, no headings, no bullet points, no stage directions, no emoji.
- End on the concrete implication, not a call to subscribe.

Output nothing except the narration text."""


class Unusable(Exception):
    """Skip this story and move on. Not a crash."""


def write_script(story):
    import requests
    try:
        article = fetch_article(story["url"])
    except Exception as e:                     # paywall, 403, dead link, PDF
        raise Unusable(f"could not read article ({type(e).__name__})")
    if len(article) < CFG["min_article_chars"]:
        raise Unusable(f"only {len(article)} chars extracted - would hallucinate")
    p = PROMPT.format(niche=CFG["niche"], audience=CFG["audience"], angle=CFG["angle"],
                      title=story["title"], url=story["url"], article=article,
                      words=CFG["target_words"])
    r = requests.post("http://localhost:11434/api/generate", timeout=1800, json={
        "model": CFG["model"], "prompt": p, "stream": False,
        "options": {"temperature": 0.8, "num_predict": 3000}})
    r.raise_for_status()
    return clean_script(r.json()["response"])


META_PROMPT = """Below is the narration of a YouTube video. Write its metadata.

Reply with a JSON object and nothing else. No explanation, no code fence.
Exactly this shape:

{{"title": "...", "description": "..."}}

title: under 70 characters, says what happened, no clickbait punctuation, no emoji.
description: 2 to 3 full sentences covering what the video explains.

NARRATION:
{script}"""


def parse_meta(raw):
    """Pull the JSON object out of whatever the model replied with.

    Small models wrap it in prose or a code fence, or emit single quotes and
    trailing commas. Salvage what we can rather than throwing the call away.
    """
    raw = re.sub(r"^\s*```(?:json)?|```\s*$", "", raw.strip(), flags=re.M)
    m = re.search(r"\{.*?\"title\".*?\}", raw, re.S)
    if not m:
        return {}
    blob = re.sub(r",\s*([}\]])", r"\1", m.group(0))     # trailing commas
    try:
        return json.loads(blob)
    except Exception:
        pass
    # last resort: read the two fields straight out of the text
    out = {}
    for key in ("title", "description"):
        f = re.search(rf'"{key}"\s*:\s*"(.*?)"\s*[,}}]', blob, re.S)
        if f:
            out[key] = f.group(1).replace('\\"', '"').strip()
    return out


def summarise(script, n=2):
    """First couple of sentences of the narration, for when the model will not
    produce a description. Beats putting a bare url in the box."""
    parts = re.split(r"(?<=[.!?])\s+", script.strip())
    return " ".join(parts[:n]).strip()


def make_meta(story, script):
    """Title and description in their own call, with two attempts.

    A third of these used to fall back to the headline and a bare url, which
    is what the viewer sees under the video, so it is worth retrying.
    """
    import requests
    got = {}
    for attempt in range(2):
        try:
            r = requests.post("http://localhost:11434/api/generate", timeout=600, json={
                "model": CFG["model"],
                "prompt": META_PROMPT.format(script=script[:3000]),
                "stream": False,
                "options": {"temperature": 0.4 if attempt else 0.7, "num_predict": 500}})
            got = parse_meta(clean_script(r.json()["response"]))
            if got.get("title") and got.get("description"):
                break
        except Exception:
            continue

    title = (got.get("title") or story["title"]).strip()[:95]
    desc = (got.get("description") or summarise(script)).strip()
    if story.get("url"):
        desc += f"\n\nSource: {story['url']}"
    return {"title": title, "description": desc}


def clean_script(t):
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S)      # qwen3 reasoning block
    t = re.sub(r"^\s*(#+|\*+|-)\s*", "", t, flags=re.M)       # stray markdown
    t = re.sub(r"[*_`#]", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


# ---------------------------------------------------------------- voice
def narrate(text, wav):
    if not PIPER.exists():
        sys.exit(f"Piper missing. Run setup.ps1 first. Expected {PIPER}")
    voice = ASSETS / "piper" / f"{CFG['piper_voice']}.onnx"
    env = None
    if not WINDOWS:
        # the unix builds ship their own libraries next to the binary
        env = dict(os.environ,
                   LD_LIBRARY_PATH=str(PIPER.parent),
                   DYLD_LIBRARY_PATH=str(PIPER.parent))
    part = wav.with_suffix(".wav.part")
    # length-scale above 1 slows the delivery down, which is most of what makes
    # a synthetic voice easier to sit through. sentence-silence is the pause
    # between sentences, and rushing those is what makes it sound like a robot.
    subprocess.run([str(PIPER), "-m", str(voice), "-f", str(part),
                    "--sentence-silence", str(CFG.get("sentence_silence", 0.4)),
                    "--length-scale", str(CFG.get("speech_rate", 1.0))],
                   input=text.encode("utf-8"), check=True, env=env)
    part.replace(wav)
    return wav


# ---------------------------------------------------------------- subtitles
def ass_time(s):
    h, s = divmod(max(s, 0), 3600)
    m, s = divmod(s, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def make_subs(wav, ass_path):
    """Word timings from whisper, chunked 4 at a time into an ASS subtitle file."""
    from faster_whisper import WhisperModel
    m = WhisperModel(CFG["whisper_model"], device="cpu", compute_type="int8")
    segs, _ = m.transcribe(str(wav), word_timestamps=True)
    words = [w for s in segs for w in s.words]

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {CFG['width']}
PlayResY: {CFG['height']}

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,BorderStyle,Outline,Shadow,Alignment,MarginV,Encoding
Style: D,{pick_font()},84,&H00FFFFFF,&H00000000,&H80000000,-1,1,5,2,2,120,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = []
    for i in range(0, len(words), 4):
        ch = words[i:i + 4]
        txt = " ".join(w.word.strip() for w in ch).replace("\n", " ")
        lines.append(f"Dialogue: 0,{ass_time(ch[0].start)},{ass_time(ch[-1].end)},D,,0,0,0,,{txt}")
    return write_atomic(ass_path, head + "\n".join(lines) + "\n")


# ---------------------------------------------------------------- render
def duration(path):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(o.stdout.strip())


def clip_order(clips, seconds, seed, dur):
    """Shuffled clip list, long enough to cover the narration.

    Seeded off the video name so a rerun of the same video is identical but two
    different videos never open on the same shot. Reshuffled every pass so the
    repeats don't fall into a visible loop either.
    """
    rng = random.Random(seed)
    total, out = 0.0, []
    while total < seconds + 5:
        cycle = clips[:]
        rng.shuffle(cycle)
        for c in cycle:
            out.append(c)
            total += dur(c)
            if total >= seconds + 5:
                break
    return out


def build_bed(seconds, out_path, seed=""):
    clips = sorted([p for p in BROLL.glob("*") if p.suffix.lower() in (".mp4", ".mov", ".webm")])
    if not clips:
        sys.exit(f"No b-roll. Drop stock clips into {BROLL}")
    lst = ROOT / "_concat.txt"
    entries = [f"file '{c.as_posix()}'" for c in clip_order(clips, seconds, seed, duration)]
    lst.write_text("\n".join(entries), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-an", "-c", "copy", str(out_path)], check=True)
    # -shortest in the render would silently cut the narration off if the bed
    # came out short, so refuse instead. usually means clips are not normalised.
    got = duration(out_path)
    if got < seconds:
        raise Unusable(f"footage is {got:.0f}s for {seconds:.0f}s of narration. "
                       f"run: python broll.py --normalize")
    return out_path


def render(wav, ass, mp4):
    secs = duration(wav)
    bed = build_bed(secs, OUT / "_bed.mp4", seed=mp4.stem)
    # cwd=OUT so the ass filter gets a bare filename. ffmpeg reads the colon in
    # C:/... as a filter option separator and mangles the path.
    vf = (f"scale={CFG['width']}:{CFG['height']}:force_original_aspect_ratio=increase,"
          f"crop={CFG['width']}:{CFG['height']},fps={CFG['fps']},"
          f"ass={ass.name}")
    enc = pick_encoder()
    part = mp4.with_suffix(".mp4.part")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", bed.name, "-i", wav.name,
                    "-vf", vf, "-map", "0:v", "-map", "1:a", "-shortest",
                    "-c:v", enc, *ENC_ARGS.get(enc, []),
                    "-b:v", CFG.get("bitrate", "8M"),
                    "-c:a", "aac", "-b:a", "192k", part.name],
                   check=True, cwd=str(OUT))
    # only now does the real filename exist, so a crash mid-encode cannot leave
    # something that looks like a finished video
    part.replace(mp4)
    return mp4


# ---------------------------------------------------------------- orchestrate
def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def stage(label, fn, *a):
    """Time a step and print it. Silence for six minutes looks like a crash."""
    print(f"    {label:<28}", end="", flush=True)
    t0 = time.time()
    r = fn(*a)
    print(f"done in {time.time() - t0:>5.0f}s", flush=True)
    return r


def make_one(story):
    name = slug(story["title"])
    txt = OUT / f"{name}.txt"
    if txt.exists() and len(txt.read_text(encoding="utf-8").split()) > 200:
        script = txt.read_text(encoding="utf-8")
        print(f"    reusing script from a previous run ({len(script.split())} words)",
              flush=True)
    else:
        print("    reading article + writing script (slowest step, 3-8 min)", flush=True)
        script = stage("  script", write_script, story)
        write_atomic(txt, script)
    words = len(script.split())
    print(f"      -> {words} words, about {words / 150:.1f} min of speech", flush=True)
    wav = stage("  voice", narrate, script, OUT / f"{name}.wav")
    ass = stage("  subtitles", make_subs, wav, OUT / f"{name}.ass")
    mp4 = stage("  render", render, wav, ass, OUT / f"{name}.mp4")
    meta = stage("  title + description", make_meta, story, script)
    # json last, so its presence is what marks the video as finished
    write_atomic(OUT / f"{name}.json", json.dumps(meta, indent=2))
    print(f"      -> \"{meta['title']}\"", flush=True)
    mark_done(story)
    return mp4


def demo():
    """Covers the parsing bits. No network, no models, no ffmpeg."""
    assert clean_script("<think>hmm</think>\n## Hi\n**there**") == "Hi\nthere"
    assert ass_time(3661.5) == "1:01:01.50"
    assert ass_time(0) == "0:00:00.00"
    assert slug("GPT-5: What's Actually New?") == "gpt-5-what-s-actually-new"
    html = "<html><script>junk()</script><p>Real text here.</p></html>"
    import unittest.mock as mk
    resp = mk.Mock(text=html, headers={"content-type": "text/html"})
    with mk.patch("requests.get", return_value=resp):
        got = fetch_article("http://x")
    assert "junk" not in got and "Real text here." in got, got

    # videos must not all open on the same shot, but a rerun must be identical.
    # Two seeds can collide by chance, so check the spread over several.
    clips, d = [Path(f"{i}.mp4") for i in range(8)], lambda p: 10.0
    opens = {clip_order(clips, 60, f"story-{i}", d)[0] for i in range(6)}
    assert len(opens) > 1, "every video opened on the same clip"
    a = clip_order(clips, 60, "story-0", d)
    assert a == clip_order(clips, 60, "story-0", d), "not reproducible"
    assert len(a) * 10 >= 60, "bed too short to cover the narration"

    # models wrap the json in prose, fences, or trailing commas
    assert parse_meta('{"title": "A", "description": "B"}')["title"] == "A"
    assert parse_meta('```json\n{"title":"A","description":"B"}\n```')["title"] == "A"
    assert parse_meta('Sure!\n{"title": "A", "description": "B",}')["description"] == "B"
    assert parse_meta("no json here at all") == {}
    assert summarise("One. Two. Three.") == "One. Two."

    # the same story reworded, or reposted elsewhere, is still the same story
    assert topic_key("Show HN: Apple Sues OpenAI") == topic_key("Apple sues OpenAI")
    assert topic_key("The Xbox Outage Explained") == topic_key("Xbox outage explained")
    assert topic_key("Apple sues OpenAI") != topic_key("Google sues Meta")
    print("demo ok")


def main():
    if "--demo" in sys.argv:
        return demo()
    OUT.mkdir(exist_ok=True)
    BROLL.mkdir(parents=True, exist_ok=True)
    # only make what can actually go out. uploads are capped at 6 a day, so
    # making 6 a night on top of a queue means every story publishes days late.
    # out/ holds only un-uploaded videos, finished ones move to out/uploaded/.
    # only finished ones count. a video left half rendered by a power cut must
    # not occupy a queue slot forever and stop new ones being made.
    queued = len([p for p in OUT.glob("*.mp4")
                  if not p.name.startswith("_") and complete(p.stem)])
    room = max(0, CFG.get("max_queue", 6) - queued)
    want = min(CFG["videos_per_run"], room)
    if want == 0:
        return print(f"{queued} videos already waiting to upload, "
                     f"which is the daily limit. Making none tonight so the "
                     f"queue drains and stories go out fresh.")
    if want < CFG["videos_per_run"]:
        print(f"{queued} already queued, making {want} instead of "
              f"{CFG['videos_per_run']} to keep the backlog flat.")
    print(f"Goal: {want} video(s). Fetching stories...", flush=True)
    stories = pick_stories(want * 6)          # most stories won't extract cleanly
    if not stories:
        return print("Nothing new above the points threshold. Try again tomorrow.")
    print(f"{len(stories)} candidate stories not covered before.\n", flush=True)

    made, t0 = 0, time.time()
    for i, s in enumerate(stories, 1):
        if made >= want:
            break
        print(f"--- video {made + 1}/{want}  (candidate {i}/{len(stories)}) ---")
        print(f"  [{s['score']}] {s['title']}", flush=True)
        try:
            mp4 = make_one(s)
            made += 1
            print(f"  SAVED {mp4.name}\n", flush=True)
        except Unusable as e:
            print(f"  SKIP  {e} - trying next story\n", flush=True)
            mark_done(s)                       # don't retry a paywall forever
        except Exception as e:
            print(f"  FAIL  {type(e).__name__}: {e}\n", flush=True)
    print(f"Made {made}/{want} videos in {(time.time() - t0) / 60:.0f} min. "
          f"Files are in {OUT}")


if __name__ == "__main__":
    main()

"""fetch -> script -> voice -> subs -> render.

    python vidbot.py          make today's videos
    python vidbot.py --demo   self-check, no network needed
"""
import json, random, re, sqlite3, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text())
OUT = ROOT / "out"
ASSETS = ROOT / "assets"
BROLL = ASSETS / "broll"
PIPER = ASSETS / "piper" / "piper.exe"


def db():
    c = sqlite3.connect(ROOT / "state.db")
    c.execute("CREATE TABLE IF NOT EXISTS seen (url TEXT PRIMARY KEY, title TEXT, ts INT)")
    return c


# ---------------------------------------------------------------- sourcing
def pick_stories(n):
    """Front-page HN stories we haven't already used."""
    import requests
    q = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=50"
    hits = requests.get(q, timeout=30).json()["hits"]
    con, out = db(), []
    for h in hits:
        url, title = h.get("url") or "", h.get("title") or ""
        if not url or h.get("points", 0) < CFG["min_hn_points"]:
            continue
        if con.execute("SELECT 1 FROM seen WHERE url=?", (url,)).fetchone():
            continue
        out.append({"title": title, "url": url, "points": h["points"],
                    "id": h["objectID"]})
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
    pass


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


META_PROMPT = """Video narration follows. Write YouTube metadata for it.
Return ONLY a JSON object with keys "title" and "description".
title: under 70 chars, concrete and specific, no clickbait punctuation, no emoji.
description: 2-3 sentences of what the video covers.
---
{script}"""


def make_meta(story, script):
    """Separate call for the title. Falls back to the headline if the JSON is junk."""
    import requests
    fallback = {"title": story["title"][:95], "description": story["url"]}
    try:
        r = requests.post("http://localhost:11434/api/generate", timeout=600, json={
            "model": CFG["model"], "prompt": META_PROMPT.format(script=script[:3000]),
            "stream": False, "options": {"temperature": 0.7, "num_predict": 500}})
        raw = clean_script(r.json()["response"])
        m = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        title = (m.get("title") or "").strip()
        if not title:
            return fallback
        return {"title": title[:95],
                "description": (m.get("description") or "").strip() + f"\n\nSource: {story['url']}"}
    except Exception:
        return fallback


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
    subprocess.run([str(PIPER), "-m", str(voice), "-f", str(wav), "--sentence-silence", "0.35"],
                   input=text.encode("utf-8"), check=True)
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
Style: D,{CFG['font']},84,&H00FFFFFF,&H00000000,&H80000000,-1,1,5,2,2,120,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = []
    for i in range(0, len(words), 4):
        ch = words[i:i + 4]
        txt = " ".join(w.word.strip() for w in ch).replace("\n", " ")
        lines.append(f"Dialogue: 0,{ass_time(ch[0].start)},{ass_time(ch[-1].end)},D,,0,0,0,,{txt}")
    ass_path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    return ass_path


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
    return out_path


def render(wav, ass, mp4):
    secs = duration(wav)
    bed = build_bed(secs, OUT / "_bed.mp4", seed=mp4.stem)
    # cwd=OUT so the ass filter gets a bare filename. ffmpeg reads the colon in
    # C:/... as a filter option separator and mangles the path.
    vf = (f"scale={CFG['width']}:{CFG['height']}:force_original_aspect_ratio=increase,"
          f"crop={CFG['width']}:{CFG['height']},fps={CFG['fps']},"
          f"ass={ass.name}")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", bed.name, "-i", wav.name,
                    "-vf", vf, "-map", "0:v", "-map", "1:a", "-shortest",
                    "-c:v", CFG["encoder"], "-quality", "quality", "-b:v", "8M",
                    "-c:a", "aac", "-b:a", "192k", mp4.name],
                   check=True, cwd=str(OUT))
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
        txt.write_text(script, encoding="utf-8")
    words = len(script.split())
    print(f"      -> {words} words, about {words / 150:.1f} min of speech", flush=True)
    wav = stage("  voice", narrate, script, OUT / f"{name}.wav")
    ass = stage("  subtitles", make_subs, wav, OUT / f"{name}.ass")
    mp4 = stage("  render", render, wav, ass, OUT / f"{name}.mp4")
    meta = stage("  title + description", make_meta, story, script)
    (OUT / f"{name}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
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
    print("demo ok")


def main():
    if "--demo" in sys.argv:
        return demo()
    OUT.mkdir(exist_ok=True)
    BROLL.mkdir(parents=True, exist_ok=True)
    want = CFG["videos_per_run"]
    print(f"Goal: {want} video(s). Fetching Hacker News front page...", flush=True)
    stories = pick_stories(want * 6)          # most stories won't extract cleanly
    if not stories:
        return print("Nothing new above the points threshold. Try again tomorrow.")
    print(f"{len(stories)} candidate stories not covered before.\n", flush=True)

    made, t0 = 0, time.time()
    for i, s in enumerate(stories, 1):
        if made >= want:
            break
        print(f"--- video {made + 1}/{want}  (candidate {i}/{len(stories)}) ---")
        print(f"  [{s['points']}pts] {s['title']}", flush=True)
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

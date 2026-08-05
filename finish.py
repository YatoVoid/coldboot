"""Complete any half-built video in out/, then carry on making new ones.

Useful after a crash: the script and audio are the expensive parts and they
survive, so there's no reason to redo them.
"""
import json, sys, time
from pathlib import Path
import vidbot as v


def source_url(name):
    """Find the story this video came from, so the description can credit it.

    Repairing a video after a crash loses the story it came from, and an empty
    source line under the video helps nobody.
    """
    con = v.db()
    for url, title in con.execute("SELECT url, title FROM seen"):
        if v.slug(title) == name:
            return url
    return ""


def playable(path):
    """An interrupted write leaves a 0-byte or half-written file behind."""
    if not path.exists() or path.stat().st_size < 1024:
        return False
    try:
        return v.duration(path) > 1
    except Exception:
        return False


def finish_partial():
    done = 0
    for txt in sorted(v.OUT.glob("*.txt")):
        name = txt.stem
        wav, ass = v.OUT / f"{name}.wav", v.OUT / f"{name}.ass"
        mp4, js = v.OUT / f"{name}.mp4", v.OUT / f"{name}.json"
        if playable(mp4) and js.exists():
            continue
        script = txt.read_text(encoding="utf-8")
        if len(script.split()) < 200:
            print(f"skip {name}: script too short to be real\n", flush=True)
            continue
        print(f"finishing {name}", flush=True)
        try:
            if not playable(wav):
                print("      audio missing or corrupt, re-recording", flush=True)
                v.stage("  voice", v.narrate, script, wav)
            if not ass.exists():
                v.stage("  subtitles", v.make_subs, wav, ass)
            if not playable(mp4):
                v.stage("  render", v.render, wav, ass, mp4)
            if not js.exists():
                story = {"title": name.replace("-", " "), "url": source_url(name)}
                meta = v.stage("  title + description", v.make_meta, story, script)
                js.write_text(json.dumps(meta, indent=2), encoding="utf-8")
                print(f'      -> "{meta["title"]}"', flush=True)
            done += 1
            print(f"      ok\n", flush=True)
        except Exception as e:
            # one broken leftover shouldn't stop the rest of the batch
            print(f"      gave up on {name}: {type(e).__name__}: {e}\n", flush=True)
    print(f"completed {done} partial video(s)\n", flush=True)
    return done


if __name__ == "__main__":
    v.OUT.mkdir(exist_ok=True)
    finish_partial()
    if "--only-partial" not in sys.argv:
        v.main()

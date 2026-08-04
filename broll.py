"""Pull CC0 stock footage from Pexels into assets/broll.

    python broll.py           top up the library
    python broll.py --demo

Wants a free key from https://www.pexels.com/api/ sitting in pexels.key
"""
import json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent
BROLL = ROOT / "assets" / "broll"
KEY = ROOT / "pexels.key"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
QUERIES = CFG["broll_queries"]
PER_QUERY = CFG.get("broll_per_query", 4)


MIN_LUMA = CFG.get("min_brightness", 30)


def best_file(files, max_w=1920):
    """Largest mp4 that isn't bigger than our render width."""
    ok = [f for f in files if f.get("file_type") == "video/mp4" and (f.get("width") or 0) <= max_w]
    return max(ok or files, key=lambda f: f.get("width") or 0)


REJECTS = BROLL / "rejected.txt"


def rejected():
    """Ids we already downloaded once and threw away. Without this every run
    re-downloads the same dark clips just to delete them again."""
    if not REJECTS.exists():
        return set()
    return set(REJECTS.read_text().split())


def reject(vid_id):
    with open(REJECTS, "a") as fh:
        fh.write(f"{vid_id}\n")


def have_id(vid_id, skip=()):
    """The same clip comes back under several searches, so match on pexels id."""
    return str(vid_id) in skip or any(BROLL.glob(f"*_{vid_id}.mp4"))


PAGE = BROLL / "page.txt"


def next_page():
    """Walk one page deeper every run.

    Asking for page 1 each night just re-finds clips we already have, so the
    library would stop growing after the first run. Wraps at 20 so it doesn't
    wander off into results that stop matching the search.
    """
    try:
        p = int(PAGE.read_text().strip())
    except Exception:
        p = 0
    p = p % 20 + 1
    PAGE.write_text(str(p))
    return p


def normalize(path):
    """Re-encode to one common format.

    Stock clips arrive at assorted resolutions and frame rates. Concatenating
    those with -c copy produces a file whose duration is wrong, and the render
    then cuts the narration off to match it. Paying for one encode here means
    every later concat is exact.
    """
    tmp = path.with_suffix(".norm.mp4")
    w, h, fps = CFG.get("width", 1920), CFG.get("height", 1080), CFG.get("fps", 30)
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(path), "-an",
         "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},fps={fps},format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(tmp)],
        capture_output=True)
    if r.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        return False
    path.unlink()
    tmp.rename(path)
    return True


def brightness(path):
    """Average luma, 0 is black. Some stock clips are nearly black and end up
    looking like a broken render once subtitles are the only thing visible."""
    out = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-vf",
         "select='not(mod(n\\,60))',signalstats,metadata=print:key=lavfi.signalstats.YAVG",
         "-vsync", "0", "-f", "null", "-"], capture_output=True, text=True).stderr
    vals = [float(x) for x in re.findall(r"YAVG=([\d.]+)", out)]
    return sum(vals) / len(vals) if vals else -1


def fetch(query, n, key, page=1, skip=()):
    import requests
    r = requests.get("https://api.pexels.com/videos/search", timeout=60,
                     headers={"Authorization": key},
                     params={"query": query, "per_page": n, "page": page,
                             "orientation": "landscape", "size": "medium"})
    r.raise_for_status()
    got = 0
    for v in r.json().get("videos", []):
        if not (10 <= (v.get("duration") or 0) <= 40):     # too short = jarring cuts
            continue
        if have_id(v["id"], skip):
            continue
        dest = BROLL / f"{re.sub(r'[^a-z0-9]+', '_', query)}_{v['id']}.mp4"
        url = best_file(v["video_files"])["link"]
        with requests.get(url, stream=True, timeout=300) as s:
            s.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in s.iter_content(1 << 20):
                    fh.write(chunk)
        lum = brightness(dest)
        if 0 <= lum < MIN_LUMA:
            dest.unlink()
            reject(v["id"])
            print(f"  - {dest.name} (too dark, luma {lum:.0f})")
            continue
        if not normalize(dest):
            dest.unlink(missing_ok=True)
            reject(v["id"])
            print(f"  - {dest.name} (could not re-encode)")
            continue
        print(f"  + {dest.name}")
        got += 1
    return got


def normalize_all():
    """Bring a library downloaded before normalising up to date."""
    clips = sorted(BROLL.glob("*.mp4"))
    for i, c in enumerate(clips, 1):
        print(f"  [{i}/{len(clips)}] {c.name}", flush=True)
        if not normalize(c):
            print(f"      failed, removing")
            c.unlink(missing_ok=True)
    print(f"{len(list(BROLL.glob('*.mp4')))} clips normalised")


def audit():
    """Clean a library built before the brightness and duplicate checks."""
    seen, removed = {}, 0
    for c in sorted(BROLL.glob("*.mp4")):
        vid = c.stem.rsplit("_", 1)[-1]
        if vid in seen:
            print(f"  - {c.name} (same clip as {seen[vid]})")
            c.unlink()
            removed += 1
            continue
        seen[vid] = c.name
        lum = brightness(c)
        if 0 <= lum < MIN_LUMA:
            print(f"  - {c.name} (too dark, luma {lum:.0f})")
            c.unlink()
            removed += 1
    print(f"removed {removed}, {len(list(BROLL.glob('*.mp4')))} clips left")


def demo():
    files = [{"file_type": "video/mp4", "width": 3840, "link": "a"},
             {"file_type": "video/mp4", "width": 1920, "link": "b"},
             {"file_type": "video/mp4", "width": 640, "link": "c"}]
    assert best_file(files)["link"] == "b"          # picks 1920, not the 4K
    assert best_file([{"file_type": "video/mp4", "width": 4096, "link": "z"}])["link"] == "z"
    # the id is what identifies a clip, not the search that found it
    assert "server_room_1085656.mp4".rsplit("_", 1)[-1] == "1085656.mp4"
    assert ("data_center_1085656.mp4".rsplit("_", 1)[-1]
            == "server_room_1085656.mp4".rsplit("_", 1)[-1])
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    elif "--audit" in sys.argv:
        audit()
    elif "--normalize" in sys.argv:
        normalize_all()
    elif not KEY.exists():
        sys.exit(f"Put your free Pexels API key in {KEY}\nGet one: https://www.pexels.com/api/")
    else:
        BROLL.mkdir(parents=True, exist_ok=True)
        key = KEY.read_text().strip()
        page, skip = next_page(), rejected()
        print(f"searching page {page}, {len(skip)} clips previously rejected")
        total = sum(fetch(q, PER_QUERY, key, page, skip) for q in QUERIES)
        print(f"downloaded {total} new clips, library now {len(list(BROLL.glob('*.mp4')))}")

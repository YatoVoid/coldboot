"""Pull CC0 stock footage from Pexels into assets/broll.

    python broll.py           top up the library
    python broll.py --demo

Wants a free key from https://www.pexels.com/api/ sitting in pexels.key
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).parent
BROLL = ROOT / "assets" / "broll"
KEY = ROOT / "pexels.key"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
QUERIES = CFG["broll_queries"]
PER_QUERY = CFG.get("broll_per_query", 4)


def best_file(files, max_w=1920):
    """Largest mp4 that isn't bigger than our render width."""
    ok = [f for f in files if f.get("file_type") == "video/mp4" and (f.get("width") or 0) <= max_w]
    return max(ok or files, key=lambda f: f.get("width") or 0)


def fetch(query, n, key):
    import requests
    r = requests.get("https://api.pexels.com/videos/search", timeout=60,
                     headers={"Authorization": key},
                     params={"query": query, "per_page": n, "orientation": "landscape",
                             "size": "medium"})
    r.raise_for_status()
    got = 0
    for v in r.json().get("videos", []):
        if not (10 <= (v.get("duration") or 0) <= 40):     # too short = jarring cuts
            continue
        dest = BROLL / f"{re.sub(r'[^a-z0-9]+', '_', query)}_{v['id']}.mp4"
        if dest.exists():
            continue
        url = best_file(v["video_files"])["link"]
        with requests.get(url, stream=True, timeout=300) as s:
            s.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in s.iter_content(1 << 20):
                    fh.write(chunk)
        print(f"  + {dest.name}")
        got += 1
    return got


def demo():
    files = [{"file_type": "video/mp4", "width": 3840, "link": "a"},
             {"file_type": "video/mp4", "width": 1920, "link": "b"},
             {"file_type": "video/mp4", "width": 640, "link": "c"}]
    assert best_file(files)["link"] == "b"          # picks 1920, not the 4K
    assert best_file([{"file_type": "video/mp4", "width": 4096, "link": "z"}])["link"] == "z"
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    elif not KEY.exists():
        sys.exit(f"Put your free Pexels API key in {KEY}\nGet one: https://www.pexels.com/api/")
    else:
        BROLL.mkdir(parents=True, exist_ok=True)
        key = KEY.read_text().strip()
        total = sum(fetch(q, PER_QUERY, key) for q in QUERIES)
        print(f"downloaded {total} new clips, library now {len(list(BROLL.glob('*.mp4')))}")

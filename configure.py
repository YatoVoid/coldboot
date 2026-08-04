"""Pick what the channel makes videos about, and write config.json.

    python configure.py              walk through it
    python configure.py space        just load that preset
    python configure.py --list       show presets
    python configure.py --check      validate the current config
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).parent
PRESETS = ROOT / "presets"
CONFIG = ROOT / "config.json"

VOICES = {
    "1": ("en_US-ryan-high", "male, US, neutral news read"),
    "2": ("en_US-lessac-medium", "male, US, warmer and slower"),
    "3": ("en_US-amy-medium", "female, US, clear"),
    "4": ("en_GB-alba-medium", "female, UK"),
    "5": ("en_US-joe-medium", "male, US, deeper"),
}

REQUIRED = ["niche", "audience", "angle", "source", "broll_queries", "model",
            "target_words", "videos_per_run", "encoder", "piper_voice"]


def presets():
    return sorted(p.stem for p in PRESETS.glob("*.json"))


def validate(cfg):
    """Catch the mistakes that would otherwise show up an hour into a run."""
    problems = []
    for k in REQUIRED:
        if k not in cfg:
            problems.append(f"missing key: {k}")
    src = cfg.get("source", {})
    kind = src.get("type")
    if kind not in ("hackernews", "reddit", "rss"):
        problems.append(f"source.type must be hackernews, reddit or rss (got {kind!r})")
    if kind == "rss" and not src.get("feeds"):
        problems.append("rss source needs a non-empty 'feeds' list")
    if kind == "reddit" and not src.get("subreddits"):
        problems.append("reddit source needs a non-empty 'subreddits' list")
    if not cfg.get("broll_queries"):
        problems.append("broll_queries is empty, there would be no footage")
    if cfg.get("videos_per_run", 0) > 6:
        problems.append("videos_per_run above 6 exceeds the daily YouTube upload quota")
    return problems


def ask(prompt, default):
    got = input(f"{prompt}\n  [{default}]: ").strip()
    return got or default


def wizard():
    names = presets()
    print("\nWhat should this channel be about?\n")
    for i, n in enumerate(names, 1):
        cfg = json.loads((PRESETS / f"{n}.json").read_text(encoding="utf-8-sig"))
        print(f"  {i}. {n:<14} {cfg['niche']}")
    print(f"  {len(names) + 1}. custom        start from tech-news and edit it\n")

    pick = input(f"choose 1-{len(names) + 1}: ").strip()
    custom = pick == str(len(names) + 1)
    base = "tech-news" if custom else names[int(pick) - 1]
    cfg = json.loads((PRESETS / f"{base}.json").read_text(encoding="utf-8-sig"))

    if custom:
        print("\nDescribe it. Press enter to keep what's shown.\n")
        cfg["niche"] = ask("Subject of the channel", cfg["niche"])
        cfg["audience"] = ask("Who is watching", cfg["audience"])
        cfg["angle"] = ask("How should it be written", cfg["angle"])
        q = ask("Stock footage searches, comma separated",
                ", ".join(cfg["broll_queries"]))
        cfg["broll_queries"] = [s.strip() for s in q.split(",") if s.strip()]

    print("\nVoice:\n")
    for k, (v, desc) in VOICES.items():
        print(f"  {k}. {v:<22} {desc}")
    v = input("choose 1-5 [1]: ").strip() or "1"
    cfg["piper_voice"] = VOICES.get(v, VOICES["1"])[0]

    n = ask("\nVideos per night (6 is the YouTube daily limit)",
            str(cfg["videos_per_run"]))
    cfg["videos_per_run"] = max(1, min(6, int(n)))

    problems = validate(cfg)
    if problems:
        print("\nthat config has problems:")
        for p in problems:
            print(f"  - {p}")
        return 1

    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote config.json ({cfg['niche']}, {cfg['piper_voice']})")
    print("next: .\\setup.ps1" if sys.platform == "win32" else "next: ./setup.sh")
    print("then: python broll.py")
    return 0


def demo():
    good = json.loads((PRESETS / "tech-news.json").read_text(encoding="utf-8-sig"))
    assert validate(good) == [], validate(good)
    for name in presets():
        cfg = json.loads((PRESETS / f"{name}.json").read_text(encoding="utf-8-sig"))
        assert validate(cfg) == [], f"{name}: {validate(cfg)}"
    assert validate({}), "empty config should not pass"
    bad = dict(good, source={"type": "rss", "feeds": []})
    assert any("feeds" in p for p in validate(bad)), validate(bad)
    bad = dict(good, videos_per_run=20)
    assert any("quota" in p for p in validate(bad)), validate(bad)
    print("demo ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--demo" in a:
        demo()
    elif "--list" in a:
        for n in presets():
            cfg = json.loads((PRESETS / f"{n}.json").read_text(encoding="utf-8-sig"))
            print(f"{n:<14} {cfg['niche']}")
    elif "--check" in a:
        problems = validate(json.loads(CONFIG.read_text(encoding="utf-8-sig")))
        print("\n".join(f"  - {p}" for p in problems) if problems else "config ok")
        sys.exit(1 if problems else 0)
    elif a and not a[0].startswith("-"):
        src = PRESETS / f"{a[0]}.json"
        if not src.exists():
            sys.exit(f"no preset {a[0]!r}. options: {', '.join(presets())}")
        CONFIG.write_text(src.read_text(encoding="utf-8-sig"), encoding="utf-8")
        print(f"loaded preset {a[0]}")
    else:
        sys.exit(wizard())

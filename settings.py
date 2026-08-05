"""The one place config.json gets read.

Defaults come from config.example.json and your config.json is layered on top.
That does two things. A fresh clone runs before anyone has made a config, and a
config written months ago still works after a new key is added, instead of
failing with a KeyError somewhere in the middle of a nightly run.

    python settings.py          show the settings in use and where each came from
    python settings.py --demo
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).parent
EXAMPLE = ROOT / "config.example.json"
CONFIG = ROOT / "config.json"


def read(path):
    # utf-8-sig because notepad and powershell both like to leave a BOM
    return json.loads(path.read_text(encoding="utf-8-sig"))


def merge(defaults, user):
    """Top level only, on purpose.

    A deep merge would look tidier but it is wrong for the one nested block
    here. "source" means different things depending on its type: an rss block
    merged onto the hackernews default would inherit min_points, which means
    nothing for a feed. Better an rss block is exactly what you wrote.

    So the fallback covers top level keys. Anything read from inside "source"
    uses .get with its own default, which is where that guarantee actually
    lives. See sources.py.
    """
    out = dict(defaults)
    out.update(user)
    return out


def load():
    defaults = read(EXAMPLE) if EXAMPLE.exists() else {}
    if not CONFIG.exists():
        return defaults
    return merge(defaults, read(CONFIG))


def demo():
    d = {"a": 1, "b": 2, "privacy": "private"}
    u = {"b": 3, "privacy": "public"}
    assert merge(d, u) == {"a": 1, "b": 3, "privacy": "public"}
    assert merge(d, {}) == d
    assert merge(d, u)["a"] == 1, "keys missing from a user config keep the default"
    assert merge(d, u) is not d, "must not edit the defaults in place"
    # nested blocks are taken whole, so an rss source does not inherit
    # hackernews settings that would mean nothing to it
    hn = {"source": {"type": "hackernews", "min_points": 80}}
    rss = {"source": {"type": "rss", "feeds": ["x"]}}
    assert merge(hn, rss)["source"] == {"type": "rss", "feeds": ["x"]}
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        defaults = read(EXAMPLE) if EXAMPLE.exists() else {}
        user = read(CONFIG) if CONFIG.exists() else {}
        if not CONFIG.exists():
            print("no config.json, using config.example.json for everything")
        for k, v in sorted(load().items()):
            where = "yours" if k in user else "default"
            print(f"  {k:<20} {where:<8} {json.dumps(v)[:60]}")

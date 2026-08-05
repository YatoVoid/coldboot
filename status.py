"""What has run, what is waiting, and when the next batch goes.

    python status.py
    python status.py --demo
"""
import json, sqlite3, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "out"
DONE = OUT / "uploaded"
BROLL = ROOT / "assets" / "broll"
TASKS = ("vidbot-daily", "coldboot-daily")
CAP = 6


def db():
    c = sqlite3.connect(ROOT / "state.db")
    c.execute("CREATE TABLE IF NOT EXISTS seen (url TEXT PRIMARY KEY, title TEXT, ts INT)")
    c.execute("CREATE TABLE IF NOT EXISTS uploaded (file TEXT PRIMARY KEY, vid TEXT, ts INT)")
    return c


def ago(ts):
    """Human gap, because a unix timestamp tells you nothing at a glance."""
    if not ts:
        return "never"
    s = max(0, time.time() - ts)
    if s < 3600:
        return f"{s / 60:.0f} min ago"
    if s < 86400:
        return f"{s / 3600:.0f} hours ago"
    return f"{s / 86400:.0f} days ago"


def gb(paths):
    return sum(p.stat().st_size for p in paths) / 1e9


def schedule():
    """Next run and last result, straight from the scheduler."""
    if sys.platform == "win32":
        for name in TASKS:
            r = subprocess.run(["schtasks", "/query", "/tn", name, "/fo", "list", "/v"],
                               capture_output=True, text=True)
            if r.returncode:
                continue
            got = {}
            for line in r.stdout.splitlines():
                if ":" in line:
                    k, _, val = line.partition(":")
                    got[k.strip()] = val.strip()
            return {"name": name,
                    "next": got.get("Next Run Time", "?"),
                    "last": got.get("Last Run Time", "?"),
                    "result": got.get("Last Result", "?"),
                    "state": got.get("Scheduled Task State", got.get("Status", "?"))}
        return None
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if "run_daily.sh" in line and not line.strip().startswith("#"):
            return {"name": "cron", "next": line.split()[0:5], "last": "?",
                    "result": "?", "state": "installed"}
    return None


def main():
    if "--demo" in sys.argv:
        assert ago(0) == "never"
        assert ago(time.time() - 120).endswith("min ago")
        assert ago(time.time() - 7200).endswith("hours ago")
        assert ago(time.time() - 200000).endswith("days ago")
        print("demo ok")
        return

    con = db()
    gone = {r[0] for r in con.execute("SELECT file FROM uploaded")}
    ready = sorted((p for p in OUT.glob("*.mp4")
                    if not p.name.startswith("_") and p.name not in gone),
                   key=lambda p: p.stat().st_mtime)
    up_total = con.execute("SELECT COUNT(*) FROM uploaded").fetchone()[0]
    up_today = con.execute("SELECT COUNT(*) FROM uploaded WHERE ts > ?",
                           (time.time() - 86400,)).fetchone()[0]
    last_up = con.execute("SELECT MAX(ts) FROM uploaded").fetchone()[0]
    last_story = con.execute("SELECT MAX(ts) FROM seen").fetchone()[0]
    stories = con.execute("SELECT COUNT(*) FROM seen").fetchone()[0]
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))

    print()
    s = schedule()
    if s:
        ok = "ok" if str(s["result"]) in ("0", "0x0") else f"FAILED ({s['result']})"
        print(f"  next run    {s['next']}")
        print(f"  last run    {s['last']}  {ok}")
    else:
        print("  next run    NOT SCHEDULED. See the nightly section of the readme.")

    print(f"\n  waiting to upload   {len(ready)} videos, {gb(ready):.1f} GB")
    for p in ready[:CAP]:
        print(f"      next up: {p.stem[:58]}")
    if len(ready) > CAP:
        print(f"      and {len(ready) - CAP} more after that, {CAP} go per day")

    print(f"\n  uploaded            {up_total} total, {up_today} in the last 24h")
    print(f"      quota left today: {max(0, CAP - up_today)} of {CAP}")
    print(f"      last upload:      {ago(last_up)}")

    print(f"\n  stories covered     {stories}, last one {ago(last_story)}")
    print(f"  clip library        {len(list(BROLL.glob('*.mp4')))} clips")
    kept = list(DONE.glob("*.mp4")) if DONE.exists() else []
    print(f"  kept in uploaded/   {len(kept)} videos, {gb(kept):.1f} GB")
    print(f"\n  makes {cfg['videos_per_run']} videos a night, uploads as "
          f"{'PUBLIC' if 'public' in (ROOT / 'upload.py').read_text() else 'private'}")
    logs = sorted((ROOT / "logs").glob("*.log")) if (ROOT / "logs").exists() else []
    if logs:
        print(f"  newest log          logs\\{logs[-1].name}")
    print()


if __name__ == "__main__":
    main()

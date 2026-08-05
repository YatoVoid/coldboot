"""Upload rendered videos to YouTube. Quota: 1600 units/upload, 10000/day = 6 max.

Run: python upload.py           (upload everything unpublished, up to the cap)
     python upload.py --demo
First run opens a browser once to authorise, then stores token.json.
Needs client_secret.json from Google Cloud (YouTube Data API v3, OAuth Desktop app).
"""
import atexit, json, os, sqlite3, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "out"
DONE = OUT / "uploaded"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
DAILY_CAP = 6
PRIVACY = "public"           # set to "private" if you want to review first

# every file a video is made of, so they move together
PARTS = (".mp4", ".json", ".txt", ".wav", ".ass")


LOCK = ROOT / "upload.lock"


def take_lock():
    """Refuse to run twice at once.

    Two uploaders working the same folder both see the same pending list and
    upload every video twice, which puts duplicates on the channel and burns
    the daily quota. Easy to do by accident: run it by hand while the nightly
    job is going.
    """
    if LOCK.exists():
        try:
            pid = int(LOCK.read_text().strip())
        except Exception:
            pid = 0
        if pid and pid_alive(pid):
            sys.exit(f"upload.py is already running (pid {pid}). "
                     f"If that is wrong, delete {LOCK.name}")
        print(f"clearing stale lock from pid {pid}")
    LOCK.write_text(str(os.getpid()))
    atexit.register(lambda: LOCK.unlink(missing_ok=True))


def pid_alive(pid):
    if sys.platform == "win32":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                             capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def db():
    c = sqlite3.connect(ROOT / "state.db")
    c.execute("CREATE TABLE IF NOT EXISTS uploaded (file TEXT PRIMARY KEY, vid TEXT, ts INT)")
    return c


def pending(con):
    """Videos in out/ that have not gone up. glob is not recursive, so anything
    already moved to out/uploaded/ is out of the picture."""
    done = {r[0] for r in con.execute("SELECT file FROM uploaded")}
    ready = [p for p in OUT.glob("*.mp4")
             if p.name not in done and not p.name.startswith("_")
             and (p.with_suffix(".json")).exists()]
    # oldest first. sorting by name meant a story could sit for days while
    # alphabetically luckier ones went ahead of it, and news goes stale.
    return sorted(ready, key=lambda p: p.stat().st_mtime)


def used_today(con):
    cutoff = time.time() - 86400
    return con.execute("SELECT COUNT(*) FROM uploaded WHERE ts > ?", (cutoff,)).fetchone()[0]


def service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    tok, sec = ROOT / "token.json", ROOT / "client_secret.json"
    creds = Credentials.from_authorized_user_file(str(tok), SCOPES) if tok.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not sec.exists():
                sys.exit(f"Missing {sec}. Create an OAuth Desktop client in Google Cloud.")
            print("A browser will open to authorise this app.")
            print("If you get 'Error 403: access_denied', the signing-in account")
            print("is not listed under Test users on the OAuth consent screen.")
            print("Also set the app to In production, or the login expires weekly.\n")
            flow = InstalledAppFlow.from_client_secrets_file(str(sec), SCOPES)
            # a server with no desktop has nothing to open, so print the url and
            # let them forward the port or paste it into a browser elsewhere
            headless = sys.platform != "win32" and not os.environ.get("DISPLAY")
            if headless:
                print("No display detected. Open the link below in any browser.")
                print("If this box is remote, forward the port first:")
                print("  ssh -L 8080:localhost:8080 user@thisbox\n")
                creds = flow.run_local_server(port=8080, open_browser=False)
            else:
                creds = flow.run_local_server(port=0)
        tok.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload_one(yt, mp4):
    from googleapiclient.http import MediaFileUpload
    meta = json.loads(mp4.with_suffix(".json").read_text(encoding="utf-8"))
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
    body = {"snippet": {"title": meta["title"], "description": meta["description"],
                        "categoryId": cfg.get("youtube_category", "28")},
            "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False}}
    # 4MB chunks rather than one shot, so a 400MB file can report progress.
    # Sending it in a single request looks identical to a hang for minutes.
    media = MediaFileUpload(str(mp4), chunksize=4 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    mb = mp4.stat().st_size / 1e6
    t0, response = time.time(), None
    while response is None:
        status, response = req.next_chunk()
        if status:
            done = status.progress()
            rate = done * mb / max(1, time.time() - t0)
            left = (1 - done) * mb / rate if rate else 0
            print(f"\r      {done * 100:5.1f}%  of {mb:.0f}MB  "
                  f"{rate:.1f}MB/s  {left / 60:.0f}m left   ", end="", flush=True)
    print(f"\r      uploaded {mb:.0f}MB in {(time.time() - t0) / 60:.1f}m        ")
    return response["id"]


def archive(mp4):
    """Move a finished video and its parts into out/uploaded.

    Nothing is deleted. out/ stays as a queue of what has not gone up yet, and
    you decide later what is worth keeping.
    """
    DONE.mkdir(parents=True, exist_ok=True)
    moved = 0
    for ext in PARTS:
        src = mp4.with_suffix(ext)
        if not src.exists():
            continue
        dest = DONE / src.name
        if dest.exists():
            dest.unlink()
        src.replace(dest)
        moved += 1
    return moved


def demo():
    """Get the cap wrong and you burn the quota without noticing."""
    assert DAILY_CAP * 1600 <= 10000, "would exceed YouTube's daily quota"
    assert ".mp4" in PARTS and ".wav" in PARTS
    assert DONE.parent == OUT, "archive must stay inside out/"
    assert pid_alive(os.getpid()), "should see itself as running"
    assert not pid_alive(999999), "should not see a nonexistent pid as running"
    print("demo ok")


def main():
    if "--demo" in sys.argv:
        return demo()
    take_lock()
    con = db()
    left = DAILY_CAP - used_today(con)
    if left <= 0:
        return print("Daily upload quota already used. Try tomorrow.")
    todo = pending(con)[:left]
    if not todo:
        return print("Nothing pending.")
    print(f"{len(pending(con))} ready, uploading {len(todo)} today "
          f"({sum(p.stat().st_size for p in todo) / 1e9:.1f}GB). This is slow.")
    yt = service()
    for i, mp4 in enumerate(todo, 1):
        print(f"  [{i}/{len(todo)}] {mp4.name[:56]}", flush=True)
        try:
            vid = upload_one(yt, mp4)
            con.execute("INSERT OR REPLACE INTO uploaded VALUES (?,?,?)",
                        (mp4.name, vid, int(time.time())))
            con.commit()
            n = archive(mp4)
            print(f"      {PRIVACY}: https://youtu.be/{vid}")
            print(f"      moved {n} files to out/uploaded/")
        except Exception as e:
            print(f"      FAILED: {type(e).__name__}: {str(e)[:300]}")


if __name__ == "__main__":
    main()

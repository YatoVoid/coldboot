"""Upload rendered videos to YouTube. Quota: 1600 units/upload, 10000/day = 6 max.

Run: python upload.py           (upload everything unpublished, up to the cap)
     python upload.py --demo
First run opens a browser once to authorise, then stores token.json.
Needs client_secret.json from Google Cloud (YouTube Data API v3, OAuth Desktop app).
"""
import json, sqlite3, sys, time
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "out"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
DAILY_CAP = 6
PRIVACY = "private"          # flip to "public" once you've watched a few


def db():
    c = sqlite3.connect(ROOT / "state.db")
    c.execute("CREATE TABLE IF NOT EXISTS uploaded (file TEXT PRIMARY KEY, vid TEXT, ts INT)")
    return c


def pending(con):
    done = {r[0] for r in con.execute("SELECT file FROM uploaded")}
    return [p for p in sorted(OUT.glob("*.mp4"))
            if p.name not in done and not p.name.startswith("_")
            and (p.with_suffix(".json")).exists()]


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
            creds = InstalledAppFlow.from_client_secrets_file(str(sec), SCOPES).run_local_server(port=0)
        tok.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload_one(yt, mp4):
    from googleapiclient.http import MediaFileUpload
    meta = json.loads(mp4.with_suffix(".json").read_text(encoding="utf-8"))
    body = {"snippet": {"title": meta["title"], "description": meta["description"],
                        "categoryId": "28"},                    # 28 = Science & Technology
            "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False}}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(mp4), chunksize=-1, resumable=True))
    return req.execute()["id"]


def demo():
    """Get the cap wrong and you burn the quota without noticing."""
    assert DAILY_CAP * 1600 <= 10000, "would exceed YouTube's daily quota"
    print("demo ok")


def main():
    if "--demo" in sys.argv:
        return demo()
    con = db()
    left = DAILY_CAP - used_today(con)
    if left <= 0:
        return print("Daily upload quota already used. Try tomorrow.")
    todo = pending(con)[:left]
    if not todo:
        return print("Nothing pending.")
    yt = service()
    for mp4 in todo:
        try:
            vid = upload_one(yt, mp4)
            con.execute("INSERT OR REPLACE INTO uploaded VALUES (?,?,?)",
                        (mp4.name, vid, int(time.time())))
            con.commit()
            print(f"  {PRIVACY}: https://youtu.be/{vid}  ({mp4.name})")
        except Exception as e:
            print(f"  FAILED {mp4.name}: {e}")


if __name__ == "__main__":
    main()

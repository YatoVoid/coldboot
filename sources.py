"""Where stories come from.

Each fetcher takes the "source" block out of config.json and hands back a list
of {title, url, score}. To add your own, write a function and put it in
FETCHERS at the bottom.

    python sources.py           show what today's config would pick up
    python sources.py --demo    self-check, no network
"""
import json, re, sys
from pathlib import Path

# feeds are arbitrary remote xml, so don't hand it to the stdlib parser.
# defusedxml blocks entity expansion and external entity lookups.
from defusedxml import ElementTree as ET

UA = {"User-Agent": "Mozilla/5.0 (coldboot)"}
MAX_FEED_BYTES = 5_000_000


def hackernews(cfg):
    """Front page of Hacker News. Tech, programming, startups."""
    import requests
    n = cfg.get("min_points", 80)
    url = ("https://hn.algolia.com/api/v1/search?tags=front_page"
           f"&hitsPerPage={cfg.get('limit', 50)}")
    hits = requests.get(url, timeout=30, headers=UA).json()["hits"]
    return [{"title": h.get("title") or "", "url": h.get("url") or "",
             "score": h.get("points", 0)}
            for h in hits if h.get("url") and h.get("points", 0) >= n]


def reddit(cfg):
    """Top posts from any subreddit, through the rss endpoint.

    The .json api returns 403 to everything without an oauth token now, but
    /top/.rss still works. It carries no score, so the feed's own ordering is
    all we get. Entries link to the comments page and bury the real article
    url in the html body, so dig it out.

    Expect this to fail sometimes. Reddit rate limits anonymous callers hard,
    and a few requests in a row is enough to get thrown 429s for a while. Use
    an rss source instead if the subject has news sites covering it.
    """
    import requests
    out = []
    for sub in cfg["subreddits"]:
        url = (f"https://www.reddit.com/r/{sub}/top/.rss"
               f"?t={cfg.get('period', 'day')}")
        try:
            r = requests.get(url, timeout=30, headers=UA)
            r.raise_for_status()
        except Exception as e:
            print(f"  r/{sub} failed: {type(e).__name__}")
            continue
        for item in parse_feed(r.text)[:cfg.get("limit", 25)]:
            item["url"] = outbound_link(item.get("body", "")) or item["url"]
            out.append({k: item[k] for k in ("title", "url", "score")})
    return out


def outbound_link(html):
    """Reddit marks the submitted article with a [link] anchor. Self posts have none."""
    m = re.search(r'href="([^"]+)"[^>]*>\s*\[link\]', html)
    return m.group(1) if m else ""


def parse_feed(xml_text):
    """RSS and Atom both, since feeds disagree about which they are."""
    root = ET.fromstring(xml_text)
    out = []
    for item in root.iter():
        tag = item.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        title = link = body = ""
        for child in item:
            ctag = child.tag.rsplit("}", 1)[-1]
            if ctag == "title":
                title = (child.text or "").strip()
            elif ctag == "link":
                link = (child.get("href") or child.text or "").strip()
            elif ctag in ("content", "description", "summary"):
                body = child.text or ""
        if title and link:
            out.append({"title": title, "url": link, "score": 0, "body": body})
    return out


def rss(cfg):
    """Any list of feed URLs. Works for most news sites and blogs."""
    import requests
    out = []
    for feed in cfg["feeds"]:
        try:
            r = requests.get(feed, timeout=30, headers=UA)
            if len(r.content) > MAX_FEED_BYTES:
                print(f"  feed too big, skipping ({feed})")
                continue
            out += parse_feed(r.text)
        except Exception as e:
            print(f"  feed failed ({feed}): {type(e).__name__}")
    return out[:cfg.get("limit", 40)]


FETCHERS = {"hackernews": hackernews, "reddit": reddit, "rss": rss}


def fetch(cfg):
    kind = cfg.get("type", "hackernews")
    if kind not in FETCHERS:
        sys.exit(f"unknown source type {kind!r}. options: {', '.join(FETCHERS)}")
    got = FETCHERS[kind](cfg)
    return sorted(got, key=lambda s: -s["score"])


def demo():
    rss_xml = """<rss><channel>
      <item><title>First post</title><link>http://a.com/1</link></item>
      <item><title>Second post</title><link>http://a.com/2</link></item>
    </channel></rss>"""
    got = parse_feed(rss_xml)
    assert [g["title"] for g in got] == ["First post", "Second post"], got

    atom = """<feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>Atom one</title><link href="http://b.com/1"/></entry>
    </feed>"""
    got = parse_feed(atom)
    assert len(got) == 1 and got[0]["url"] == "http://b.com/1", got

    assert parse_feed("<rss><channel></channel></rss>") == []

    # reddit hides the submitted article behind a [link] anchor
    body = ('<a href="https://reddit.com/user/x">/u/x</a>'
            '<a href="https://theverge.com/story">[link]</a>'
            '<a href="https://reddit.com/r/g/comments/1">[comments]</a>')
    assert outbound_link(body) == "https://theverge.com/story"
    assert outbound_link('<a href="https://reddit.com/x">[comments]</a>') == ""
    assert outbound_link("") == ""

    # a hostile feed must not blow up the machine
    bomb = ("""<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaaaaaaaa">"""
            """<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">"""
            """<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]>"""
            """<rss><channel><item><title>&c;</title>"""
            """<link>http://x</link></item></channel></rss>""")
    try:
        parse_feed(bomb)
        raise AssertionError("entity expansion was not blocked")
    except AssertionError:
        raise
    except Exception:
        pass                      # defusedxml refused it, which is the point
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        cfg = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8-sig"))
        for s in fetch(cfg["source"]):
            print(f"{s['score']:>6}  {s['title'][:70]}")

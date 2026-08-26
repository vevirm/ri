"""EU R&I geopolitics scanner — one run per invocation.

    python -m scanner.scan                 # normal run (slot from the clock)
    python -m scanner.scan --slot 3        # force a rotation slot
    python -m scanner.scan --check-feeds   # test which RSS feeds are alive
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_mod
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse, urlunparse

import feedparser
import requests

from . import config as C
from .render import build_page

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
ITEMS_FILE = STATE / "items.json"
SEEN_FILE = STATE / "seen.json"
LOG_FILE = STATE / "runs.json"

UA = "Mozilla/5.0 (compatible; eu-ri-geoscanner/1.0; +%s)" % C.CONTACT_EMAIL
TIMEOUT = 30

# term -> set of buckets it satisfies
ALL_TERMS = (
    [(t, {"eu", "ri"}) for t in C.PROGRAMME_TERMS]
    + [(t, {"eu"}) for t in C.EU_TERMS]
    + [(t, {"ri"}) for t in C.RI_TERMS]
    + [(t, {"geo"}) for t in C.GEO_CORE]
    + [(t, {"geosoft"}) for t in C.GEO_SOFT]
)

ORG_WORDS = re.compile(
    r"\b(service|institute|institut|university|universit|association|commission|council|"
    r"centre|center|agency|corporation|department|office|foundation|network|group|"
    r"news|business|press|team|staff|editors?|company|ltd|inc|gmbh|federation|union|"
    r"academy|society|committee|bureau|programme|project|consortium)\b", re.I)


def looks_like_person(name: str) -> bool:
    """Keep 'Anna Rossi' as an author; send 'European Research Service' to the group slot."""
    n = name.strip()
    if not n or ORG_WORDS.search(n):
        return False
    parts = n.replace(".", "").split()
    if not 2 <= len(parts) <= 4:
        return False
    return not all(p.isupper() for p in parts)


# --------------------------------------------------------------------------- helpers
def now() -> datetime:
    return datetime.now(timezone.utc)


def cutoff() -> datetime:
    return now() - timedelta(days=C.LOOKBACK_DAYS)


def slot_for_now() -> int:
    """Deterministic rotation: advances one step every 6 hours, no state needed."""
    return int(time.time() // (6 * 3600)) % len(C.ROTATION)


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())[:120]


def norm_url(u: str) -> str:
    if not u:
        return ""
    p = urlparse(u)
    q = "&".join(x for x in p.query.split("&") if not x.lower().startswith(("utm_", "fbclid", "gclid")))
    return urlunparse((p.scheme, p.netloc.lower().replace("www.", ""), p.path.rstrip("/"), "", q, "")).lower()


def fingerprints(item: dict) -> list[str]:
    fps = []
    if item.get("doi"):
        fps.append("doi:" + item["doi"].lower())
    if item.get("url"):
        fps.append("url:" + norm_url(item["url"]))
    if item.get("title"):
        fps.append("ttl:" + norm_title(item["title"]))
    return fps


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html_mod.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def looks_english(text: str) -> bool:
    if not text:
        return True
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    ascii_ratio = sum(c.isascii() for c in letters) / len(letters)
    return ascii_ratio > 0.9


def match_keywords(text: str) -> tuple[list[str], set[str]]:
    """Return (matched terms, which buckets they cover)."""
    low = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "
    hits, buckets = [], set()
    for term, tags in ALL_TERMS:
        if re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-zA-Z])", low):
            hits.append(term)
            buckets |= tags
    return hits, buckets


def is_crucial(item: dict) -> bool:
    """The gate: EU + R&I + geopolitics all present, over MIN_KEYWORD_HITS terms."""
    text = " ".join([item.get("title", ""), item.get("abstract", "")])
    hits, buckets = match_keywords(text)
    hits = sorted(set(hits))
    soft = sum(1 for h in hits if h in C.GEO_SOFT)
    geo_ok = "geo" in buckets or soft >= 2
    if len(hits) >= C.MIN_KEYWORD_HITS and {"eu", "ri"} <= buckets and geo_ok:
        item["matched"] = hits[:8]
        return True
    return False


HEADERS = {"User-Agent": UA,
           "Accept": "application/rss+xml, application/xml, application/json;q=0.9, */*;q=0.8"}


def get(url: str, tries: int = 3, **kw):
    """GET with polite backoff. Network problems must never kill a run."""
    for attempt in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kw)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 500, 502, 503) and attempt < tries - 1:
                time.sleep(min(int(r.headers.get("Retry-After", 0) or 0) or 4 * (attempt + 1), 15))
                continue
            print(f"    ! {r.status_code} {url[:90]}")
            return None
        except Exception as e:
            if attempt == tries - 1:
                print(f"    ! {type(e).__name__} {url[:90]}")
    return None


# --------------------------------------------------------------------------- sources
def fetch_openalex(query: str) -> list[dict]:
    url = (
        "https://api.openalex.org/works?"
        f"filter=from_publication_date:{cutoff():%Y-%m-%d},language:en,"
        f"title_and_abstract.search:{quote_plus(query)}"
        f"&per-page=40&sort=publication_date:desc&mailto={quote_plus(C.CONTACT_EMAIL)}"
    )
    r = get(url)
    if not r:
        return []
    out = []
    for w in r.json().get("results", []):
        authors = []
        for a in (w.get("authorships") or [])[:25]:
            name = (a.get("author") or {}).get("display_name")
            if name:
                authors.append(name)
        loc = (w.get("primary_location") or {}).get("source") or {}
        biblio = w.get("biblio") or {}
        pages = ""
        if biblio.get("first_page"):
            pages = biblio["first_page"] + (f"-{biblio['last_page']}" if biblio.get("last_page") else "")
        out.append({
            "type": "article",
            "title": strip_html(w.get("title") or ""),
            "authors": authors,
            "date": w.get("publication_date") or "",
            "container": loc.get("display_name") or "",
            "publisher": loc.get("host_organization_name") or "",
            "volume": biblio.get("volume") or "",
            "issue": biblio.get("issue") or "",
            "pages": pages,
            "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
            "url": w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url") or "",
            "abstract": inverted_to_text(w.get("abstract_inverted_index")),
            "source": "OpenAlex",
        })
    return out


def inverted_to_text(inv: dict | None) -> str:
    if not inv:
        return ""
    words = [(pos, w) for w, ps in inv.items() for pos in ps]
    words.sort()
    return " ".join(w for _, w in words)[:4000]


def fetch_crossref(query: str) -> list[dict]:
    url = (
        "https://api.crossref.org/works?"
        f"query.bibliographic={quote_plus(query)}"
        f"&filter=from-pub-date:{cutoff():%Y-%m-%d},type:journal-article"
        f"&rows=30&sort=published&order=desc&mailto={quote_plus(C.CONTACT_EMAIL)}"
    )
    r = get(url)
    if not r:
        return []
    out = []
    for w in r.json().get("message", {}).get("items", []):
        parts = (w.get("published") or w.get("issued") or {}).get("date-parts", [[None]])[0]
        date = "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts) if p)
        authors = [
            " ".join(x for x in [a.get("given"), a.get("family")] if x)
            for a in (w.get("author") or [])[:25]
        ]
        out.append({
            "type": "article",
            "title": strip_html((w.get("title") or [""])[0]),
            "authors": [a for a in authors if a],
            "date": date,
            "container": (w.get("container-title") or [""])[0],
            "publisher": w.get("publisher") or "",
            "volume": w.get("volume") or "",
            "issue": w.get("issue") or "",
            "pages": w.get("page") or "",
            "doi": w.get("DOI") or "",
            "url": ("https://doi.org/" + w["DOI"]) if w.get("DOI") else w.get("URL", ""),
            "abstract": strip_html(w.get("abstract") or ""),
            "source": "Crossref",
        })
    return out


def entry_date(e) -> str:
    for key in ("published_parsed", "updated_parsed"):
        if getattr(e, key, None):
            return time.strftime("%Y-%m-%d", getattr(e, key))
    return ""


def fetch_feed(name: str, url: str, kind: str) -> list[dict]:
    r = get(url)
    if not r:
        return []
    parsed = feedparser.parse(r.content)
    out = []
    for e in parsed.entries[:60]:
        title = strip_html(getattr(e, "title", ""))
        summary = strip_html(getattr(e, "summary", "") or getattr(e, "description", ""))
        authors = []
        if getattr(e, "author", None) and len(e.author) < 120:
            cand = [a.strip() for a in re.split(r",| and ", e.author) if a.strip()]
            if cand and all(looks_like_person(a) for a in cand):
                authors = cand
        out.append({
            "type": kind,
            "title": title,
            "authors": authors,
            "date": entry_date(e),
            "container": name,
            "publisher": name,
            "volume": "", "issue": "", "pages": "", "doi": "",
            "url": getattr(e, "link", ""),
            "abstract": summary,
            "source": name,
        })
    return out


def fetch_google_news(query: str) -> list[dict]:
    url = ("https://news.google.com/rss/search?q="
           + quote_plus(query + " when:180d")
           + "&hl=en-US&gl=US&ceid=US:en")
    r = get(url)
    if not r:
        return []
    out = []
    for e in feedparser.parse(r.content).entries[:40]:
        title = strip_html(getattr(e, "title", ""))
        publisher = ""
        if hasattr(e, "source") and getattr(e.source, "title", None):
            publisher = e.source.title
        if " - " in title:                       # Google appends " - Publisher"
            head, _, tail = title.rpartition(" - ")
            if not publisher:
                publisher = tail
            if tail.strip().lower() == publisher.strip().lower() or len(tail) < 60:
                title = head
        out.append({
            "type": "news",
            "title": title.strip(),
            "authors": [],
            "date": entry_date(e),
            "container": publisher or "Google News",
            "publisher": publisher,
            "volume": "", "issue": "", "pages": "", "doi": "",
            "url": getattr(e, "link", ""),
            "abstract": strip_html(getattr(e, "summary", "")),
            "source": "Google News",
        })
    return out


# --------------------------------------------------------------------------- run
def load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    return default


def save(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))


def check_feeds():
    print("Feed health check\n" + "-" * 60)
    for pool, feeds in C.FEED_POOLS.items():
        for name, url, _ in feeds:
            r = get(url)
            n = len(feedparser.parse(r.content).entries) if r else 0
            print(f"{'OK ' if n else 'DEAD'}  {n:>3} entries  {pool:<14} {name}")


def run(slot: int | None = None):
    slot = slot_for_now() if slot is None else slot % len(C.ROTATION)
    rot = C.ROTATION[slot]
    print(f"== slot {slot}: {rot['name']} == {now():%Y-%m-%d %H:%M} UTC")

    harvested: list[dict] = []

    for q in rot["queries"]:
        print(f"  openalex: {q}")
        harvested += fetch_openalex(q)
        time.sleep(1)
        print(f"  crossref: {q}")
        harvested += fetch_crossref(q)
        time.sleep(1)

    for name, url, kind in C.FEED_POOLS[rot["feeds"]]:
        print(f"  feed: {name}")
        harvested += fetch_feed(name, url, kind)

    if C.USE_GOOGLE_NEWS:
        for q in rot["news"]:
            print(f"  news: {q}")
            harvested += fetch_google_news(q)
        # publishers whose own RSS is bot-walled, reached one domain at a time
        for domain in rot.get("sites", []):
            probe = f"{rot['news'][0]} site:{domain}"
            print(f"  site: {domain}")
            harvested += fetch_google_news(probe)

    items = load(ITEMS_FILE, [])
    seen = set(load(SEEN_FILE, []))
    lo = f"{cutoff():%Y-%m-%d}"
    added = 0

    for it in harvested:
        if not it.get("title") or not it.get("url"):
            continue
        if it.get("date", "") < lo:                      # older than 6 months
            continue
        if not looks_english(it["title"]):
            continue
        if not is_crucial(it):                            # >1 keyword, EU + geo
            continue
        fps = fingerprints(it)
        if any(f in seen for f in fps):                   # already have it
            continue
        seen.update(fps)
        it["id"] = hashlib.sha1(fps[0].encode()).hexdigest()[:12]
        it["slot"] = rot["name"]
        it["first_seen"] = f"{now():%Y-%m-%dT%H:%M:%SZ}"
        it.pop("abstract", None)                          # keep the store small
        items.append(it)
        added += 1

    items = [i for i in items if i.get("date", "") >= lo]  # drop what aged out
    items.sort(key=lambda i: (i.get("date", ""), i.get("first_seen", "")), reverse=True)

    log = load(LOG_FILE, [])
    log.insert(0, {"at": f"{now():%Y-%m-%dT%H:%M:%SZ}", "slot": slot,
                   "theme": rot["name"], "checked": len(harvested), "added": added,
                   "total": len(items)})
    log = log[:60]

    save(ITEMS_FILE, items)
    save(SEEN_FILE, sorted(seen)[-20000:])
    save(LOG_FILE, log)
    build_page(items, log, ROOT / "docs" / "index.html")

    print(f"-- checked {len(harvested)}, kept {added} new, {len(items)} live on page")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", type=int, default=None)
    ap.add_argument("--check-feeds", action="store_true")
    a = ap.parse_args()
    if a.check_feeds:
        check_feeds()
        sys.exit(0)
    run(a.slot)

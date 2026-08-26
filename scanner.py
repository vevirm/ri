#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
DATA_DIR = ROOT / "data"
FINDINGS_PATH = DATA_DIR / "findings.json"
SEEN_PATH = DATA_DIR / "seen.json"
STATE_PATH = DATA_DIR / "state.json"

UA = "EU-RI-Geopolitics-Scanner/1.0 (GitHub Actions; research monitoring)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "en"})


@dataclass
class Deadline:
    started: float
    max_seconds: int

    @property
    def remaining(self) -> float:
        return max(0.0, self.max_seconds - (time.monotonic() - self.started))

    @property
    def expired(self) -> bool:
        return self.remaining <= 0

    def timeout(self, default: float = 12.0) -> float:
        return max(1.0, min(default, self.remaining))


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", " ", s).strip()


def canon_for_match(s: str) -> str:
    s = norm_text(s).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9+\-\. ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def term_pattern(term: str) -> re.Pattern[str]:
    t = canon_for_match(term)
    if len(t) <= 3 and t.isalpha():
        return re.compile(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", re.I)
    return re.compile(re.escape(t), re.I)


def matched_terms(text: str, terms: list[str]) -> list[str]:
    c = canon_for_match(text)
    found, seen = [], set()
    for term in terms:
        if term_pattern(term).search(c):
            k = canon_for_match(term)
            if k not in seen:
                seen.add(k)
                found.append(term)
    return found


def looks_english(text: str) -> bool:
    """Cheap English guard for an English-only source/query pipeline; avoids another dependency."""
    text = norm_text(text)
    if not text:
        return False
    letters = [c for c in text if c.isalpha()]
    if letters:
        latinish = sum(1 for c in letters if ord(c) < 384) / len(letters)
        if latinish < 0.92:
            return False
    low = f" {text.lower()} "
    common = (" the ", " and ", " of ", " in ", " to ", " for ", " on ", " with ", " eu ", " european ")
    if len(text) < 80:
        return True
    return sum(1 for w in common if w in low) >= 1


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def crossref_date(item: dict[str, Any]) -> datetime | None:
    for field in ("published-online", "published-print", "published", "issued"):
        parts = ((item.get(field) or {}).get("date-parts") or [])
        if not parts or not parts[0]:
            continue
        vals = list(parts[0]) + [1, 1]
        try:
            return datetime(int(vals[0]), int(vals[1]), int(vals[2]), tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def strip_tracking(url: str) -> str:
    if not url:
        return ""
    try:
        p = urlsplit(url)
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))
    except Exception:
        return url


def fingerprint(item: dict[str, Any]) -> str:
    doi = (item.get("doi") or "").lower().replace("https://doi.org/", "").strip()
    if doi:
        return "doi:" + doi
    title = canon_for_match(item.get("title", ""))
    if title:
        return "title:" + hashlib.sha256(title.encode()).hexdigest()[:24]
    return "url:" + hashlib.sha256(strip_tracking(item.get("url", "")).encode()).hexdigest()[:24]


def journal_match(result_source: str, requested: str) -> bool:
    a, b = canon_for_match(result_source), canon_for_match(requested)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    ta = {x for x in a.split() if len(x) > 2}
    tb = {x for x in b.split() if len(x) > 2}
    return len(ta & tb) >= max(2, min(len(ta), len(tb)) - 1)


def fetch_crossref(query: str, journal: str, cutoff: datetime, deadline: Deadline) -> list[dict[str, Any]]:
    if deadline.expired:
        return []
    params = {
        "query.bibliographic": query,
        "query.container-title": journal,
        "filter": f"from-pub-date:{cutoff.date().isoformat()},until-pub-date:{datetime.now(timezone.utc).date().isoformat()},type:journal-article",
        "rows": 25,
        "sort": "relevance",
    }
    mailto = os.environ.get("CROSSREF_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto
    try:
        r = SESSION.get("https://api.crossref.org/works", params=params, timeout=deadline.timeout(18))
        r.raise_for_status()
        records = (r.json().get("message") or {}).get("items", [])
    except Exception as e:
        print(f"[warn] Crossref failed {journal} / {query}: {e}")
        return []

    out = []
    for w in records:
        source = norm_text(((w.get("container-title") or [""])[0]))
        if source and not journal_match(source, journal):
            continue
        dt = crossref_date(w)
        if not dt or dt < cutoff:
            continue
        title = norm_text(((w.get("title") or [""])[0]))
        abstract = norm_text(re.sub(r"<[^>]+>", " ", w.get("abstract", "")))
        if not looks_english(title + " " + abstract):
            continue
        authors = []
        for a in w.get("author", []) or []:
            given = norm_text(a.get("given", ""))
            family = norm_text(a.get("family", ""))
            name = " ".join(x for x in (given, family) if x)
            if name:
                authors.append(name)
        doi = norm_text(w.get("DOI", ""))
        page = norm_text(w.get("page", ""))
        first_page, last_page = None, None
        if page:
            parts = re.split(r"[-–]", page, maxsplit=1)
            first_page = parts[0].strip() or None
            last_page = parts[1].strip() if len(parts) > 1 else None
        out.append({
            "type": "peer_reviewed",
            "title": title,
            "summary": abstract,
            "url": w.get("URL") or ("https://doi.org/" + doi if doi else ""),
            "doi": doi,
            "date": dt.date().isoformat(),
            "year": dt.year,
            "authors": authors,
            "source": source or journal,
            "volume": norm_text(w.get("volume", "")) or None,
            "issue": norm_text(w.get("issue", "")) or None,
            "first_page": first_page,
            "last_page": last_page,
            "query": query,
        })
    return out


def google_news_url(query: str, domain: str) -> str:
    q = f"{query} site:{domain} when:6m"
    return "https://news.google.com/rss/search?" + urlencode({"q": q, "hl": "en-GB", "gl": "GB", "ceid": "GB:en"})


def fetch_google_rss(query: str, source: dict[str, str], item_type: str, cutoff: datetime, deadline: Deadline) -> list[dict[str, Any]]:
    if deadline.expired:
        return []
    try:
        r = SESSION.get(google_news_url(query, source["domain"]), timeout=deadline.timeout(12))
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"[warn] RSS failed {source['domain']} / {query}: {e}")
        return []

    out = []
    for node in root.findall(".//item")[:30]:
        def txt(tag: str) -> str:
            el = node.find(tag)
            return norm_text(el.text if el is not None and el.text else "")

        pub = txt("pubDate")
        if not pub:
            continue
        try:
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc)
        except Exception:
            continue
        if dt < cutoff:
            continue

        title = txt("title")
        summary = norm_text(re.sub(r"<[^>]+>", " ", txt("description")))
        if not looks_english(title + " " + summary):
            continue
        source_el = node.find("source")
        source_name = norm_text(source_el.text if source_el is not None and source_el.text else "") or source["name"]
        suffix = " - " + source_name
        if title.lower().endswith(suffix.lower()):
            title = title[:-len(suffix)].strip()
        out.append({
            "type": item_type,
            "title": title,
            "summary": summary,
            "url": txt("link"),
            "date": dt.date().isoformat(),
            "year": dt.year,
            "authors": [],
            "source": source_name,
            "source_domain": source["domain"],
            "query": query,
        })
    return out


def relevance(item: dict[str, Any], config: dict[str, Any], active_keywords: list[str], now: datetime) -> tuple[bool, int]:
    text = " ".join([item.get("title", ""), item.get("summary", ""), item.get("source", "")])
    title = item.get("title", "")
    category_hits = {cat: matched_terms(text, terms) for cat, terms in config["category_terms"].items()}

    if any(not category_hits.get(cat) for cat in config["mandatory_categories"]):
        return False, 0

    combined_terms = [t for terms in config["category_terms"].values() for t in terms] + active_keywords
    hits = matched_terms(text, combined_terms)
    if len(hits) < int(config["min_distinct_keyword_hits"]):
        return False, 0
    if not category_hits.get("geopolitical"):
        return False, 0

    score = {"peer_reviewed": 100, "report": 82, "news": 34}.get(item.get("type"), 0)
    score += min(40, len(hits) * 7)
    score += min(18, len(category_hits["geopolitical"]) * 6)
    score += min(18, len(matched_terms(title, combined_terms)) * 6)

    dt = parse_date(item.get("date")) or now
    age_days = max(0, (now - dt).days)
    score += max(0, 15 - int(age_days / 14))

    high_value = [
        "research security", "economic security", "strategic autonomy", "technology security",
        "dual-use", "dual use", "critical technologies", "foreign interference", "technology leakage",
        "science diplomacy", "export controls", "strategic dependencies",
    ]
    if matched_terms(text, high_value):
        score += 12

    item["matched_keywords"] = hits
    item["matched_categories"] = category_hits
    item["score"] = score
    return True, score


def dedupe_candidates(items: list[dict[str, Any]], seen: set[str]) -> list[dict[str, Any]]:
    local, out = set(), []
    for item in items:
        key = fingerprint(item)
        if key in seen or key in local:
            continue
        local.add(key)
        item["fingerprint"] = key
        out.append(item)
    return out


def choose_rotation(config: dict[str, Any], run_index: int) -> dict[str, Any]:
    kb, jg, rg, ng = config["keyword_batches"], config["journal_groups"], config["report_groups"], config["news_groups"]
    return {
        "keyword_batches": [kb[run_index % len(kb)], kb[(run_index + 3) % len(kb)]],
        "journal_group": jg[run_index % len(jg)],
        "report_group": rg[(run_index + 1) % len(rg)],
        "news_group": ng[(run_index + 2) % len(ng)],
    }


def select_with_quotas(items: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    items = sorted(items, key=lambda x: (x.get("score", 0), x.get("date", "")), reverse=True)
    quotas = config["max_new_per_run"]
    counts = {"peer_reviewed": 0, "report": 0, "news": 0}
    chosen = []
    for item in items:
        t = item.get("type")
        if t not in counts or counts[t] >= quotas[t]:
            continue
        counts[t] += 1
        chosen.append(item)
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan English EU R&I geopolitical research, reports and news.")
    parser.add_argument("--max-seconds", type=int, default=1200, help="Hard scan budget; defaults to 20 minutes.")
    args = parser.parse_args()

    deadline = Deadline(time.monotonic(), max(30, args.max_seconds))
    config = load_json(CONFIG_PATH, {})
    state = load_json(STATE_PATH, {"run_index": 0})
    findings = load_json(FINDINGS_PATH, [])
    seen = set(load_json(SEEN_PATH, []))

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=int(config.get("window_days", 183)))
    run_index = int(state.get("run_index", 0))
    rotation = choose_rotation(config, run_index)

    active_queries, active_keywords = [], []
    for batch in rotation["keyword_batches"]:
        active_queries.extend(batch["queries"][:2])
        active_keywords.extend(batch["keywords"])

    print("Rotation:")
    print("  keyword batches:", ", ".join(x["name"] for x in rotation["keyword_batches"]))
    print("  journal group:", rotation["journal_group"]["name"])
    print("  report group:", rotation["report_group"]["name"])
    print("  news group:", rotation["news_group"]["name"])

    jobs: list[tuple[str, tuple[Any, ...]]] = []
    for query in active_queries:
        for journal in rotation["journal_group"]["journals"][:5]:
            jobs.append(("peer", (query, journal)))
        for src in rotation["report_group"]["sources"][:4]:
            jobs.append(("report", (query, src)))
        for src in rotation["news_group"]["sources"][:4]:
            jobs.append(("news", (query, src)))

    candidates: list[dict[str, Any]] = []
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        futures = []
        for kind, args2 in jobs:
            if kind == "peer":
                futures.append(ex.submit(fetch_crossref, args2[0], args2[1], cutoff, deadline))
            else:
                futures.append(ex.submit(fetch_google_rss, args2[0], args2[1], kind, cutoff, deadline))
        for fut in cf.as_completed(futures):
            if deadline.expired:
                break
            try:
                candidates.extend(fut.result())
            except Exception as e:
                print(f"[warn] scan task failed: {e}")

    qualified = []
    for item in candidates:
        ok, _ = relevance(item, config, active_keywords, now)
        if ok:
            qualified.append(item)

    qualified = dedupe_candidates(qualified, seen)
    chosen = select_with_quotas(qualified, config)

    for item in chosen:
        seen.add(item["fingerprint"])
        item["discovered_utc"] = now.isoformat(timespec="seconds")
        item["rotation"] = {
            "keywords": [x["name"] for x in rotation["keyword_batches"]],
            "journal_group": rotation["journal_group"]["name"],
            "report_group": rotation["report_group"]["name"],
            "news_group": rotation["news_group"]["name"],
        }
        findings.append(item)

    kept = []
    for item in findings:
        dt = parse_date(item.get("date"))
        if dt and dt >= cutoff:
            kept.append(item)
    kept.sort(key=lambda x: (x.get("score", 0), x.get("date", "")), reverse=True)

    seen_sorted = sorted(seen)
    if len(seen_sorted) > 25000:
        seen_sorted = seen_sorted[-25000:]

    state = {
        "run_index": run_index + 1,
        "last_scan_utc": now.isoformat(timespec="seconds"),
        "last_rotation": {
            "keyword_batches": [x["name"] for x in rotation["keyword_batches"]],
            "journal_group": rotation["journal_group"]["name"],
            "report_group": rotation["report_group"]["name"],
            "news_group": rotation["news_group"]["name"],
            "queries": active_queries,
        },
        "new_counts": {
            "peer_reviewed": sum(1 for x in chosen if x["type"] == "peer_reviewed"),
            "report": sum(1 for x in chosen if x["type"] == "report"),
            "news": sum(1 for x in chosen if x["type"] == "news"),
        },
    }

    save_json(FINDINGS_PATH, kept)
    save_json(SEEN_PATH, seen_sorted)
    save_json(STATE_PATH, state)

    print(f"Candidates: {len(candidates)} | qualified new: {len(qualified)} | added: {len(chosen)} | page total: {len(kept)}")
    print("New counts:", state["new_counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

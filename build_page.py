#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
ITERATIONS = 250_000


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def encrypt_payload(payload: dict, password: str) -> dict[str, str | int]:
    salt = secrets.token_bytes(16)
    iv = secrets.token_bytes(12)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
    key = kdf.derive(password.encode("utf-8"))
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(iv, raw, None)
    return {"salt": b64(salt), "iv": b64(iv), "ciphertext": b64(ciphertext), "iterations": ITERATIONS}


def text_for(item: dict[str, Any]) -> str:
    parts = [item.get("title", ""), item.get("summary", ""), item.get("source", "")]
    parts.extend(item.get("matched_keywords", []) or [])
    return " ".join(str(x) for x in parts if x).lower()


def contains_any(text: str, terms: list[str]) -> bool:
    return any(term.lower() in text for term in terms)


def make_simple_summary(findings: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    themes = [
        {
            "name": "Keeping research safe",
            "terms": ["research security", "knowledge security", "foreign interference", "technology leakage", "trusted research", "due diligence"],
            "plain": "These findings are about stopping spying, unwanted influence, or sensitive research knowledge from leaking.",
        },
        {
            "name": "Protecting Europe's economy",
            "terms": ["economic security", "strategic autonomy", "technological sovereignty", "strategic dependency", "strategic dependencies", "de-risking", "export control", "investment screening"],
            "plain": "These findings link research and technology to Europe's economic safety and its ability to rely less on risky suppliers.",
        },
        {
            "name": "Important technologies",
            "terms": ["critical technology", "critical technologies", "dual-use", "dual use", "semiconductor", "artificial intelligence", " ai ", "quantum", "biotechnology", "space technology", "cybersecurity", "technology security"],
            "plain": "These findings focus on technologies such as AI, chips, quantum and biotech. Some can be useful for both civilian and military purposes.",
        },
        {
            "name": "Research money and competition",
            "terms": ["horizon europe", "framework programme", "fp10", "competitiveness", "innovation gap", "r&d funding", "r&i funding", "european competitiveness fund"],
            "plain": "These findings discuss research funding and whether Europe can keep up with other major science and technology powers.",
        },
        {
            "name": "Working with other countries",
            "terms": ["science diplomacy", "international cooperation", "research cooperation", "association", "academic freedom", "open and secure", "global approach"],
            "plain": "These findings ask how Europe can keep international research open while adding sensible safety checks.",
        },
        {
            "name": "China, the US, Russia and Ukraine",
            "terms": ["china", "chinese", "united states", "u.s.", " usa ", "russia", "russian", "ukraine", "taiwan", "indo-pacific", "transatlantic", "sanctions"],
            "plain": "These findings show that big international relationships and conflicts are shaping European research and technology choices.",
        },
    ]

    counts = {"peer_reviewed": 0, "report": 0, "news": 0}
    theme_rows = []
    for item in findings:
        if item.get("type") in counts:
            counts[item["type"]] += 1

    for theme in themes:
        n = sum(1 for item in findings if contains_any(" " + text_for(item) + " ", theme["terms"]))
        if n:
            theme_rows.append({"name": theme["name"], "count": n, "plain": theme["plain"]})
    theme_rows.sort(key=lambda x: (-x["count"], x["name"]))

    actors = [
        ("China", ["china", "chinese"]),
        ("United States", ["united states", "u.s.", " usa ", "american"]),
        ("Russia", ["russia", "russian"]),
        ("Ukraine", ["ukraine", "ukrainian"]),
    ]
    actor_rows = []
    for name, terms in actors:
        n = sum(1 for item in findings if contains_any(" " + text_for(item) + " ", terms))
        if n:
            actor_rows.append({"name": name, "count": n})
    actor_rows.sort(key=lambda x: (-x["count"], x["name"]))

    top_names = {row["name"] for row in theme_rows[:4]}
    if not findings:
        big_picture = "There are no strong matching findings yet. Run the scanner again later."
    elif "Keeping research safe" in top_names and "Working with other countries" in top_names:
        big_picture = "The big issue is balance: Europe wants to keep international research open, but it also wants stronger protection for important knowledge and technology."
    elif "Important technologies" in top_names:
        big_picture = "Europe is treating advanced technology as more than a research topic. It is also becoming a security and competition issue."
    elif "Research money and competition" in top_names:
        big_picture = "A major question is whether Europe's research system has enough money and focus to compete with other major powers."
    else:
        big_picture = "Research and technology are becoming a bigger part of Europe's security, economic and foreign-policy decisions."

    duration = int(state.get("scan_duration_seconds") or 0)
    new_counts = state.get("new_counts") or {}
    new_total = sum(int(new_counts.get(k, 0) or 0) for k in ("peer_reviewed", "report", "news"))

    examples = sorted(
        findings,
        key=lambda x: (x.get("score", 0), x.get("date", "")),
        reverse=True,
    )[:5]
    examples = [
        {"title": x.get("title", "Untitled"), "source": x.get("source", ""), "date": x.get("date", ""), "url": x.get("url", "")}
        for x in examples
    ]

    return {
        "total": len(findings),
        "big_picture": big_picture,
        "themes": theme_rows[:4],
        "actors": actor_rows,
        "source_counts": counts,
        "latest_scan": {
            "duration_seconds": duration,
            "rounds": int(state.get("rounds_completed") or 0),
            "new_total": new_total,
        },
        "examples": examples,
    }


COMMON_CSS = r'''
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: #fff; color: #111; }
  body { font-family: Arial, Helvetica, sans-serif; line-height: 1.55; }
  main { max-width: 980px; margin: 0 auto; padding: 52px 28px 80px; }
  h1 { font-size: 30px; line-height: 1.15; margin: 0 0 10px; font-weight: 700; }
  h2 { font-size: 20px; margin: 38px 0 16px; border-bottom: 1px solid #ddd; padding-bottom: 8px; }
  .meta { color: #555; font-size: 14px; margin-bottom: 24px; }
  .summary { font-size: 15px; color: #333; margin: 0 0 26px; }
  .nav { margin: 0 0 28px; font-size: 14px; }
  .nav a { color: #111; text-decoration: underline; text-underline-offset: 2px; }
  #gate { min-height: 100vh; display: grid; place-items: center; background: #fff; padding: 24px; }
  .gatebox { width: min(420px, 100%); }
  .gatebox h1 { font-size: 24px; margin-bottom: 20px; }
  label { display: block; font-size: 14px; margin-bottom: 6px; }
  input { width: 100%; padding: 12px 13px; border: 1px solid #aaa; border-radius: 4px; font: inherit; background: #fff; color: #111; }
  button { margin-top: 12px; padding: 11px 16px; border: 1px solid #111; border-radius: 4px; background: #111; color: #fff; font: inherit; cursor: pointer; }
  #error { min-height: 22px; color: #8b0000; font-size: 13px; margin-top: 9px; }
  #content { display: none; }
  @media (max-width: 600px) { main { padding: 34px 20px 60px; } }
'''

COMMON_JS = r'''
function fromB64(s) {
  const bin = atob(s); const a = new Uint8Array(bin.length);
  for (let i=0;i<bin.length;i++) a[i] = bin.charCodeAt(i);
  return a;
}
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
async function unlock(password) {
  const enc = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']);
  const key = await crypto.subtle.deriveKey(
    {name:'PBKDF2', salt:fromB64(ENCRYPTED.salt), iterations:ENCRYPTED.iterations, hash:'SHA-256'},
    keyMaterial,
    {name:'AES-GCM', length:256},
    false,
    ['decrypt']
  );
  const plain = await crypto.subtle.decrypt({name:'AES-GCM', iv:fromB64(ENCRYPTED.iv)}, key, fromB64(ENCRYPTED.ciphertext));
  return JSON.parse(new TextDecoder().decode(plain));
}
document.getElementById('unlockForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const error = document.getElementById('error'); error.textContent = '';
  const password = document.getElementById('password').value;
  try { render(await unlock(password)); }
  catch (_) { error.textContent = 'Incorrect password.'; }
});
'''


def build_main_html(enc: dict[str, Any]) -> str:
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<title>EU R&I Geopolitics Scanner</title>
<style>{COMMON_CSS}
  .citation {{ margin: 0 0 16px 30px; text-indent: -30px; font-size: 15px; }}
  .citation a {{ color: inherit; text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
  .empty {{ color: #666; font-style: italic; }}
  @media (max-width: 600px) {{ .citation {{ margin-left: 24px; text-indent: -24px; }} }}
</style>
</head>
<body>
<section id="gate" aria-label="Password protected scanner">
  <div class="gatebox">
    <h1>EU R&I Geopolitics Scanner</h1>
    <form id="unlockForm">
      <label for="password">Password</label>
      <input id="password" type="password" autocomplete="current-password" required autofocus>
      <button type="submit">Open</button>
      <div id="error" role="alert"></div>
    </form>
  </div>
</section>
<main id="content"></main>
<script>
const ENCRYPTED = {json.dumps(enc)};
function monthDay(iso) {{
  const d = new Date(iso + 'T00:00:00Z');
  return new Intl.DateTimeFormat('en-US', {{year:'numeric', month:'long', day:'numeric', timeZone:'UTC'}}).format(d);
}}
function initials(name) {{
  const clean = String(name || '').trim();
  if (!clean) return '';
  const parts = clean.split(/\\s+/);
  if (parts.length === 1) return clean;
  const last = parts.pop();
  const ins = parts.filter(Boolean).map(p => p.replace(/[^A-Za-zÀ-ÖØ-öø-ÿ-]/g,'').slice(0,1).toUpperCase() + '.').join(' ');
  return `${{last}}, ${{ins}}`;
}}
function apaAuthors(authors, fallback) {{
  const arr = (authors || []).map(initials).filter(Boolean);
  if (!arr.length) return esc(fallback || 'Unknown author');
  if (arr.length === 1) return esc(arr[0]);
  if (arr.length <= 20) return arr.map((a,i) => i === arr.length-1 ? '&amp; ' + esc(a) : esc(a)).join(arr.length === 2 ? ' ' : ', ');
  const first19 = arr.slice(0,19).map(esc).join(', ');
  return first19 + ', … ' + esc(arr[arr.length-1]);
}}
function link(url, text) {{
  if (!url) return esc(text || '');
  return `<a href="${{esc(url)}}" target="_blank" rel="noopener noreferrer">${{esc(text || url)}}</a>`;
}}
function apa(item) {{
  const source = item.source || 'Unknown source';
  const authors = apaAuthors(item.authors, source);
  const title = esc(item.title || 'Untitled');
  const url = item.url || (item.doi ? 'https://doi.org/' + item.doi : '');
  if (item.type === 'peer_reviewed') {{
    const vol = item.volume ? `<i>${{esc(item.volume)}}</i>` : '';
    const issue = item.issue ? `(${{esc(item.issue)}})` : '';
    const pages = item.first_page ? `, ${{esc(item.first_page)}}${{item.last_page && item.last_page !== item.first_page ? '–' + esc(item.last_page) : ''}}` : '';
    const journal = `<i>${{esc(source)}}</i>${{vol ? ', ' + vol + issue : ''}}${{pages}}.`;
    const doi = item.doi ? link('https://doi.org/' + item.doi, 'https://doi.org/' + item.doi) : link(url, url);
    return `${{authors}} (${{esc(item.year || String(item.date || '').slice(0,4))}}). ${{title}}. ${{journal}} ${{doi}}`;
  }}
  if (item.type === 'report') return `${{authors}} (${{esc(monthDay(item.date))}}). <i>${{title}}</i>. ${{link(url, url)}}`;
  return `${{authors}} (${{esc(monthDay(item.date))}}). ${{title}}. ${{link(url, url)}}`;
}}
function fmtDuration(s) {{
  s = Number(s || 0); if (!s) return 'not recorded';
  const m = Math.floor(s/60), sec = s%60; return m ? `${{m}}m ${{sec}}s` : `${{sec}}s`;
}}
function render(payload) {{
  const findings = payload.findings || [];
  const groups = [['peer_reviewed','Peer-reviewed articles'],['report','Reports'],['news','News']];
  const counts = Object.fromEntries(groups.map(([k]) => [k, findings.filter(x => x.type === k).length]));
  const state = payload.state || {{}};
  let html = `<h1>EU R&I Geopolitics Scanner</h1>`;
  html += `<div class="meta">Past six months · English only · Each scan searches for 5–20 minutes · Last scan: ${{esc(fmtDuration(state.scan_duration_seconds))}}</div>`;
  html += `<div class="nav"><a href="summary.html">Read the simple overall summary →</a></div>`;
  html += `<p class="summary">Findings must clearly connect Europe, research or technology, and a geopolitical or security issue. Academic articles and reports rank above news.</p>`;
  for (const [key,label] of groups) {{
    html += `<h2>${{esc(label)}} (${{counts[key]}})</h2>`;
    const list = findings.filter(x => x.type === key).sort((a,b) => (b.score-a.score) || String(b.date).localeCompare(String(a.date)));
    if (!list.length) {{ html += `<p class="empty">No qualifying findings in the current six-month window.</p>`; continue; }}
    for (const item of list) html += `<div class="citation">${{apa(item)}}</div>`;
  }}
  const content = document.getElementById('content'); content.innerHTML = html;
  document.getElementById('gate').style.display = 'none'; content.style.display = 'block';
}}
{COMMON_JS}
</script>
</body>
</html>'''


def build_summary_html(enc: dict[str, Any]) -> str:
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<title>Simple Summary · EU R&I Geopolitics Scanner</title>
<style>{COMMON_CSS}
  .big {{ font-size: 20px; line-height: 1.5; margin: 18px 0 30px; max-width: 760px; }}
  .cards {{ display: grid; gap: 14px; margin: 18px 0 28px; }}
  .card {{ border: 1px solid #ddd; border-radius: 7px; padding: 17px 18px; }}
  .card h3 {{ font-size: 17px; margin: 0 0 7px; }}
  .card p {{ margin: 0; font-size: 15px; }}
  .small {{ color: #555; font-size: 13px; }}
  ul {{ padding-left: 22px; }}
  li {{ margin: 8px 0; }}
  a {{ color: #111; text-underline-offset: 2px; }}
</style>
</head>
<body>
<section id="gate" aria-label="Password protected scanner summary">
  <div class="gatebox">
    <h1>Simple overall summary</h1>
    <form id="unlockForm">
      <label for="password">Password</label>
      <input id="password" type="password" autocomplete="current-password" required autofocus>
      <button type="submit">Open</button>
      <div id="error" role="alert"></div>
    </form>
  </div>
</section>
<main id="content"></main>
<script>
const ENCRYPTED = {json.dumps(enc)};
function fmtDuration(s) {{
  s = Number(s || 0); if (!s) return 'not recorded';
  const m = Math.floor(s/60), sec = s%60; return m ? `${{m}}m ${{sec}}s` : `${{sec}}s`;
}}
function render(payload) {{
  const s = payload.simple_summary || {{}};
  const scan = s.latest_scan || {{}};
  let html = `<h1>What the scanner found</h1>`;
  html += `<div class="meta">Very simple overview · ${{esc(s.total || 0)}} findings in the last six months · Scans run for 5–20 minutes</div>`;
  html += `<div class="nav"><a href="index.html">← Full source list</a></div>`;
  html += `<p class="big">${{esc(s.big_picture || 'No summary yet.')}}</p>`;
  html += `<p class="small">Latest scan: ${{esc(fmtDuration(scan.duration_seconds))}}, ${{esc(scan.rounds || 0)}} search rounds, ${{esc(scan.new_total || 0)}} new items added.</p>`;

  html += `<h2>Main themes</h2><div class="cards">`;
  if (!(s.themes || []).length) html += `<div class="card"><p>No clear theme yet.</p></div>`;
  for (const t of (s.themes || [])) {{
    html += `<div class="card"><h3>${{esc(t.name)}} · ${{esc(t.count)}} findings</h3><p>${{esc(t.plain)}}</p></div>`;
  }}
  html += `</div>`;

  const c = s.source_counts || {{}};
  html += `<h2>What kind of evidence is this?</h2>`;
  html += `<p>There are <strong>${{esc(c.peer_reviewed || 0)}}</strong> academic articles, <strong>${{esc(c.report || 0)}}</strong> reports and <strong>${{esc(c.news || 0)}}</strong> news stories. The scanner gives more weight to academic work and reports.</p>`;

  if ((s.actors || []).length) {{
    html += `<h2>Countries that come up often</h2><ul>`;
    for (const a of s.actors) html += `<li><strong>${{esc(a.name)}}:</strong> mentioned in or strongly related to ${{esc(a.count)}} findings.</li>`;
    html += `</ul>`;
  }}

  if ((s.examples || []).length) {{
    html += `<h2>A few important examples</h2><ul>`;
    for (const x of s.examples) {{
      const title = x.url ? `<a href="${{esc(x.url)}}" target="_blank" rel="noopener noreferrer">${{esc(x.title)}}</a>` : esc(x.title);
      html += `<li>${{title}} <span class="small">${{esc(x.source || '')}}${{x.date ? ' · ' + esc(x.date) : ''}}</span></li>`;
    }}
    html += `</ul>`;
  }}

  html += `<h2>How to read this</h2><p class="summary">This page is a quick guide, not a final judgement. It groups the scanner's findings by common words and themes. Use the full source list when you need the details.</p>`;
  const content = document.getElementById('content'); content.innerHTML = html;
  document.getElementById('gate').style.display = 'none'; content.style.display = 'block';
}}
{COMMON_JS}
</script>
</body>
</html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Build encrypted static findings pages.")
    parser.add_argument("--password-env", default="SCANNER_PASSWORD")
    args = parser.parse_args()

    password = os.environ.get(args.password_env, "")
    if not password:
        raise SystemExit(f"Missing required environment variable: {args.password_env}")

    findings = json.loads((DATA / "findings.json").read_text(encoding="utf-8"))
    state = json.loads((DATA / "state.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

    payload = {
        "findings": findings,
        "state": state,
        "window_days": config.get("window_days", 183),
        "min_distinct_keyword_hits": config.get("min_distinct_keyword_hits", 2),
        "simple_summary": make_simple_summary(findings, state),
    }
    enc = encrypt_payload(payload, password)

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "index.html").write_text(build_main_html(enc), encoding="utf-8")
    (DOCS / "summary.html").write_text(build_summary_html(enc), encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Built encrypted main page and simple summary page with {len(findings)} findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

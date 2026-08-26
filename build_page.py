#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
from pathlib import Path

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


def main() -> int:
    parser = argparse.ArgumentParser(description="Build encrypted static findings page.")
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
    }
    enc = encrypt_payload(payload, password)

    html = rf'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<title>EU R&I Geopolitics Scanner</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; background: #fff; color: #111; }}
  body {{ font-family: Arial, Helvetica, sans-serif; line-height: 1.5; }}
  main {{ max-width: 980px; margin: 0 auto; padding: 56px 28px 80px; }}
  h1 {{ font-size: 30px; line-height: 1.15; margin: 0 0 10px; font-weight: 700; }}
  h2 {{ font-size: 20px; margin: 42px 0 18px; border-bottom: 1px solid #ddd; padding-bottom: 8px; }}
  .meta {{ color: #555; font-size: 14px; margin-bottom: 30px; }}
  .summary {{ font-size: 14px; color: #333; margin: 0 0 32px; }}
  .citation {{ margin: 0 0 16px 30px; text-indent: -30px; font-size: 15px; }}
  .citation a {{ color: inherit; text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
  .empty {{ color: #666; font-style: italic; }}
  #gate {{ min-height: 100vh; display: grid; place-items: center; background: #fff; padding: 24px; }}
  .gatebox {{ width: min(420px, 100%); }}
  .gatebox h1 {{ font-size: 24px; margin-bottom: 20px; }}
  label {{ display: block; font-size: 14px; margin-bottom: 6px; }}
  input {{ width: 100%; padding: 12px 13px; border: 1px solid #aaa; border-radius: 4px; font: inherit; background: #fff; color: #111; }}
  button {{ margin-top: 12px; padding: 11px 16px; border: 1px solid #111; border-radius: 4px; background: #111; color: #fff; font: inherit; cursor: pointer; }}
  #error {{ min-height: 22px; color: #8b0000; font-size: 13px; margin-top: 9px; }}
  #content {{ display: none; }}
  @media (max-width: 600px) {{ main {{ padding: 34px 20px 60px; }} .citation {{ margin-left: 24px; text-indent: -24px; }} }}
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

function fromB64(s) {{
  const bin = atob(s); const a = new Uint8Array(bin.length);
  for (let i=0;i<bin.length;i++) a[i] = bin.charCodeAt(i);
  return a;
}}
function esc(s) {{
  return String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}
function monthDay(iso) {{
  const d = new Date(iso + 'T00:00:00Z');
  return new Intl.DateTimeFormat('en-US', {{year:'numeric', month:'long', day:'numeric', timeZone:'UTC'}}).format(d);
}}
function initials(name) {{
  const clean = String(name || '').trim();
  if (!clean) return '';
  const parts = clean.split(/\s+/);
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
  if (item.type === 'report') {{
    return `${{authors}} (${{esc(monthDay(item.date))}}). <i>${{title}}</i>. ${{link(url, url)}}`;
  }}
  return `${{authors}} (${{esc(monthDay(item.date))}}). ${{title}}. ${{link(url, url)}}`;
}}
function render(payload) {{
  const findings = payload.findings || [];
  const groups = [
    ['peer_reviewed','Peer-reviewed articles'],
    ['report','Reports'],
    ['news','News']
  ];
  const counts = Object.fromEntries(groups.map(([k]) => [k, findings.filter(x => x.type === k).length]));
  const state = payload.state || {{}};
  let html = `<h1>EU R&I Geopolitics Scanner</h1>`;
  html += `<div class="meta">Past six months · English only · Updated ${{esc((state.last_scan_utc || 'not yet scanned').replace('T',' ').replace('+00:00',' UTC'))}}</div>`;
  html += `<p class="summary">Strict gate: EU/Europe + research/innovation/science/technology + a geopolitical or security issue, with at least ${{esc(payload.min_distinct_keyword_hits)}} distinct keyword concepts. Peer-reviewed articles and reports receive the highest ranking weight.</p>`;
  for (const [key,label] of groups) {{
    html += `<h2>${{esc(label)}} (${{counts[key]}})</h2>`;
    const list = findings.filter(x => x.type === key).sort((a,b) => (b.score-a.score) || String(b.date).localeCompare(String(a.date)));
    if (!list.length) {{ html += `<p class="empty">No qualifying findings in the current six-month window.</p>`; continue; }}
    for (const item of list) html += `<div class="citation">${{apa(item)}}</div>`;
  }}
  const content = document.getElementById('content');
  content.innerHTML = html;
  document.getElementById('gate').style.display = 'none';
  content.style.display = 'block';
}}
async function unlock(password) {{
  const enc = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']);
  const key = await crypto.subtle.deriveKey(
    {{name:'PBKDF2', salt:fromB64(ENCRYPTED.salt), iterations:ENCRYPTED.iterations, hash:'SHA-256'}},
    keyMaterial,
    {{name:'AES-GCM', length:256}},
    false,
    ['decrypt']
  );
  const plain = await crypto.subtle.decrypt({{name:'AES-GCM', iv:fromB64(ENCRYPTED.iv)}}, key, fromB64(ENCRYPTED.ciphertext));
  return JSON.parse(new TextDecoder().decode(plain));
}}
document.getElementById('unlockForm').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const error = document.getElementById('error'); error.textContent = '';
  const password = document.getElementById('password').value;
  try {{ render(await unlock(password)); }}
  catch (_) {{ error.textContent = 'Incorrect password.'; }}
}});
</script>
</body>
</html>'''

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Built encrypted page with {len(findings)} findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

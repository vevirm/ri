"""APA 7th-edition formatting + the password-gated static page."""
from __future__ import annotations

import base64
import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from . import config as C

PASSWORD = os.environ.get("PAGE_PASSWORD", "TutuScanner2026.")
PBKDF2_ITER = 250_000

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


# --------------------------------------------------------------------------- APA 7
def initials(name: str) -> str:
    """'Anna Maria Rossi' -> 'Rossi, A. M.'   'European Commission' -> as-is."""
    name = re.sub(r"\s+", " ", name).strip().strip(",")
    if not name:
        return ""
    if "," in name:                                   # already 'Family, Given'
        family, _, given = name.partition(",")
        given_parts = given.split()
    else:
        parts = name.split()
        if len(parts) == 1:
            return parts[0]
        family, given_parts = parts[-1], parts[:-1]
        # keep particles with the family name: van der Berg -> Berg, J. van der
        while given_parts and given_parts[-1].islower():
            family = given_parts.pop() + " " + family
    ini = " ".join(f"{p[0].upper()}." for p in given_parts if p and p[0].isalpha())
    return f"{family.strip()}, {ini}".strip().rstrip(",")


def author_string(authors: list[str], fallback: str = "") -> str:
    names = [initials(a) for a in authors if a and a.strip()]
    names = [n for n in names if n]
    if not names:
        return fallback
    if len(names) == 1:
        return names[0]
    if len(names) <= 20:
        return ", ".join(names[:-1]) + ", & " + names[-1]
    return ", ".join(names[:19]) + ", . . . " + names[-1]      # APA 7: 21+ authors


def date_string(date: str, precise: bool) -> str:
    if not date:
        return "(n.d.)"
    parts = date.split("-")
    year = parts[0]
    if precise and len(parts) >= 2:
        try:
            m = MONTHS[int(parts[1]) - 1]
        except (ValueError, IndexError):
            return f"({year})"
        return f"({year}, {m} {int(parts[2])})" if len(parts) > 2 else f"({year}, {m})"
    return f"({year})"


def sentence_case(t: str) -> str:
    """APA sentence case for article/report titles, leaving ALLCAPS acronyms alone."""
    t = t.strip().rstrip(".")
    words = t.split(" ")
    out = []
    for i, w in enumerate(words):
        if w.isupper() and len(w) > 1:
            out.append(w)                                  # EU, NATO, AI
        elif i == 0 or (out and out[-1].endswith((":", "?", "."))):
            out.append(w[:1].upper() + w[1:])
        elif w[:1].isupper() and w[1:].islower() and i > 0:
            out.append(w)                                  # keep proper nouns as given
        else:
            out.append(w)
    return " ".join(out)


def apa(item: dict) -> str:
    """Return one APA7 reference as an HTML fragment."""
    e = html.escape
    typ = item.get("type", "news")
    title = sentence_case(item.get("title", "Untitled"))
    url = item.get("url", "")
    container = item.get("container") or item.get("publisher") or ""
    group = container if typ != "article" else ""
    authors = author_string(item.get("authors", []), fallback=group)
    dt = date_string(item.get("date", ""), precise=(typ != "article"))
    link = f'<a href="{e(url)}">{e(url)}</a>' if url else ""

    if typ == "article":
        bits = [f"{e(authors)} {dt}." if authors else f"{dt}."]
        bits.append(f"{e(title)}.")
        if container:
            vol = item.get("volume", "")
            iss = item.get("issue", "")
            pg = item.get("pages", "").replace("-", "\u2013")
            seg = f"<i>{e(container)}</i>"
            if vol:
                seg += f", <i>{e(vol)}</i>"
                if iss:
                    seg += f"({e(iss)})"
            if pg:
                seg += f", {e(pg)}"
            bits.append(seg + ".")
        if item.get("doi"):
            bits.append(f'<a href="https://doi.org/{e(item["doi"])}">https://doi.org/{e(item["doi"])}</a>')
        elif link:
            bits.append(link)
        return " ".join(bits)

    if typ == "report":
        # Group author: no separate publisher element when they are the same.
        head = e(authors) if authors else e(container)
        return " ".join(x for x in [f"{head} {dt}.", f"<i>{e(title)}</i>.", link] if x)

    # news / web article
    head = f"{e(authors)} {dt}." if authors else f"{e(container)} {dt}."
    src = f"<i>{e(container)}</i>." if authors and container else ""
    return " ".join(x for x in [head, f"{e(title)}.", src, link] if x)


def sort_key(item: dict) -> str:
    a = item.get("authors") or []
    base = initials(a[0]) if a else (item.get("container") or item.get("title", ""))
    return re.sub(r"[^a-z]", "", base.lower())


# --------------------------------------------------------------------------- payload
def build_payload(items: list[dict], log: list[dict]) -> dict:
    groups = {"article": [], "report": [], "news": []}
    for it in items:
        groups.get(it.get("type", "news"), groups["news"]).append(it)

    out_groups = []
    labels = {"article": "Research articles", "report": "Institutional reports and analyses",
              "news": "News"}
    for key in ("article", "report", "news"):
        refs = sorted(groups[key], key=sort_key)
        out_groups.append({
            "key": key,
            "label": labels[key],
            "items": [{
                "html": apa(it),
                "text": re.sub(r"<[^>]+>", "", apa(it)),
                "date": it.get("date", ""),
                "matched": it.get("matched", []),
                "source": it.get("source", ""),
                "theme": it.get("slot", ""),
                "first_seen": it.get("first_seen", "")[:10],
            } for it in refs],
        })

    last = log[0] if log else {}
    return {
        "title": C.PAGE_TITLE,
        "subtitle": C.PAGE_SUBTITLE,
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "last_theme": last.get("theme", ""),
        "last_added": last.get("added", 0),
        "total": len(items),
        "window": C.LOOKBACK_DAYS,
        "groups": out_groups,
        "log": log[:12],
    }


def encrypt(payload: dict, password: str) -> dict:
    salt = os.urandom(16)
    iv = os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=PBKDF2_ITER).derive(password.encode())
    ct = AESGCM(key).encrypt(iv, json.dumps(payload, ensure_ascii=False).encode(), None)
    b64 = lambda b: base64.b64encode(b).decode()
    return {"salt": b64(salt), "iv": b64(iv), "data": b64(ct), "iter": PBKDF2_ITER}


def build_page(items: list[dict], log: list[dict], out: Path) -> None:
    blob = encrypt(build_payload(items, log), PASSWORD)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(TEMPLATE.replace("__BLOB__", json.dumps(blob)))
    print(f"-- wrote {out} ({out.stat().st_size // 1024} KB)")


# --------------------------------------------------------------------------- page
TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Scanner</title>
<style>
  :root{
    --ink:#15171a; --muted:#6b7076; --rule:#e2e2df; --claret:#7a1f3d; --paper:#ffffff;
    --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
    --sans:ui-sans-serif,-apple-system,"Segoe UI",Inter,Helvetica,Arial,sans-serif;
  }
  *{box-sizing:border-box}
  html,body{margin:0;background:var(--paper);color:var(--ink)}
  body{font-family:var(--serif);font-size:17px;line-height:1.55;-webkit-text-size-adjust:100%}
  .wrap{max-width:50rem;margin:0 auto;padding:3.5rem 1.5rem 6rem}

  /* gate */
  #gate{position:fixed;inset:0;background:var(--paper);display:flex;align-items:center;
        justify-content:center;padding:1.5rem;z-index:10}
  #gate form{width:min(23rem,100%)}
  .eyebrow{font-family:var(--sans);font-size:.68rem;letter-spacing:.16em;text-transform:uppercase;
           color:var(--muted)}
  #gate h1{font-size:1.5rem;font-weight:600;margin:.5rem 0 1.5rem;line-height:1.25}
  .field{display:flex;gap:.5rem}
  input[type=password],input[type=search]{font:inherit;font-family:var(--sans);font-size:.95rem;
    padding:.6rem .7rem;border:1px solid var(--rule);border-radius:2px;background:#fff;color:inherit;
    width:100%}
  input:focus-visible,button:focus-visible{outline:2px solid var(--claret);outline-offset:2px}
  button{font-family:var(--sans);font-size:.85rem;padding:.6rem .95rem;border:1px solid var(--ink);
    background:var(--ink);color:#fff;border-radius:2px;cursor:pointer}
  button.ghost{background:none;color:var(--muted);border-color:var(--rule)}
  button.ghost[aria-pressed=true]{color:var(--claret);border-color:var(--claret)}
  .err{font-family:var(--sans);font-size:.8rem;color:var(--claret);margin-top:.7rem;min-height:1.2em}

  /* masthead */
  header{border-bottom:2px solid var(--ink);padding-bottom:1.1rem;margin-bottom:1.6rem}
  h1.title{font-size:1.85rem;font-weight:600;letter-spacing:-.01em;margin:.35rem 0 .3rem;line-height:1.15}
  .sub{color:var(--muted);font-size:.95rem;margin:0}
  .meta{font-family:var(--sans);font-size:.72rem;color:var(--muted);margin-top:.9rem;
        display:flex;flex-wrap:wrap;gap:.35rem 1.1rem}
  .meta b{color:var(--ink);font-weight:600}

  /* controls */
  .controls{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin:0 0 2.2rem}
  .controls input{flex:1 1 12rem}

  h2.sec{font-family:var(--sans);font-size:.72rem;letter-spacing:.16em;text-transform:uppercase;
    color:var(--muted);font-weight:600;border-bottom:1px solid var(--rule);
    padding-bottom:.45rem;margin:2.6rem 0 1.3rem}
  h2.sec span{float:right;letter-spacing:0}

  .ref{margin:0 0 1.4rem;padding-left:2.2em;text-indent:-2.2em}
  .ref a{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--rule);
         word-break:break-word}
  .ref a:hover{border-bottom-color:var(--claret);color:var(--claret)}
  /* signature: the keyword pair that let the item through the gate */
  .why{display:block;text-indent:0;font-family:var(--sans);font-size:.68rem;color:var(--muted);
       margin-top:.3rem;letter-spacing:.02em}
  .why i{font-style:normal;color:var(--claret);border-bottom:1px dotted currentColor}
  .why .dot{padding:0 .4em;color:var(--rule)}
  .empty{color:var(--muted);font-size:.95rem}
  footer{margin-top:3.5rem;border-top:1px solid var(--rule);padding-top:1rem;
    font-family:var(--sans);font-size:.7rem;color:var(--muted)}
  footer table{border-collapse:collapse;margin-top:.6rem;width:100%}
  footer td{padding:.15rem .6rem .15rem 0;white-space:nowrap}
  @media print{#gate,.controls,footer,button{display:none}.wrap{padding:0}}
  @media (prefers-reduced-motion:no-preference){.wrap{animation:fade .4s ease both}}
  @keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
</style>
</head>
<body>
<div id="gate">
  <form id="gform">
    <p class="eyebrow">Restricted scan</p>
    <h1>Enter the password to load the reference list.</h1>
    <div class="field">
      <input id="pw" type="password" autocomplete="current-password" placeholder="Password" autofocus>
      <button type="submit">Open</button>
    </div>
    <p class="err" id="err"></p>
  </form>
</div>

<main class="wrap" id="app" hidden></main>

<script>
const BLOB = __BLOB__;
const b2a = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));

async function decrypt(pass){
  const enc = new TextEncoder();
  const base = await crypto.subtle.importKey("raw", enc.encode(pass), "PBKDF2", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey(
    {name:"PBKDF2", salt:b2a(BLOB.salt), iterations:BLOB.iter, hash:"SHA-256"},
    base, {name:"AES-GCM", length:256}, false, ["decrypt"]);
  const plain = await crypto.subtle.decrypt({name:"AES-GCM", iv:b2a(BLOB.iv)}, key, b2a(BLOB.data));
  return JSON.parse(new TextDecoder().decode(plain));
}

// Accept the password with or without its trailing full stop.
function candidates(v){
  const set = new Set([v, v.trim(), v.trim().replace(/\.+$/,""), v.trim().replace(/\.+$/,"")+"."]);
  return [...set];
}

let DATA=null, filters={q:"", type:"all"};

document.getElementById("gform").addEventListener("submit", async e => {
  e.preventDefault();
  const err = document.getElementById("err"), btn = e.target.querySelector("button");
  err.textContent = ""; btn.disabled = true; btn.textContent = "Opening…";
  for (const c of candidates(document.getElementById("pw").value)){
    try { DATA = await decrypt(c); break; } catch(_) {}
  }
  btn.disabled = false; btn.textContent = "Open";
  if (!DATA){ err.textContent = "That password does not open this page. Check the trailing full stop."; return; }
  document.getElementById("gate").remove();
  document.getElementById("app").hidden = false;
  render();
});

function esc(s){ return s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

function render(){
  const d = DATA, q = filters.q.toLowerCase();
  const groups = d.groups.map(g => ({...g, items: g.items.filter(it =>
      (filters.type === "all" || filters.type === g.key) &&
      (!q || it.text.toLowerCase().includes(q) || it.matched.join(" ").includes(q)))}));
  const shown = groups.reduce((n,g) => n + g.items.length, 0);

  document.getElementById("app").innerHTML = `
    <header>
      <p class="eyebrow">Rotating scan · every 6 hours</p>
      <h1 class="title">${esc(d.title)}</h1>
      <p class="sub">${esc(d.subtitle)}</p>
      <div class="meta">
        <span><b>${d.total}</b> items in the last ${d.window} days</span>
        <span>Last run <b>${esc(d.built)}</b></span>
        <span>Theme: <b>${esc(d.last_theme || "—")}</b> (+${d.last_added})</span>
      </div>
    </header>
    <div class="controls">
      <input id="q" type="search" placeholder="Filter by word, author or keyword" value="${esc(filters.q)}">
      ${["all","article","report","news"].map(t =>
        `<button class="ghost" data-t="${t}" aria-pressed="${filters.type===t}">${
          {all:"All",article:"Articles",report:"Reports",news:"News"}[t]}</button>`).join("")}
      <button id="copy">Copy list</button>
    </div>
    ${groups.map(g => `
      <h2 class="sec">${esc(g.label)} <span>${g.items.length}</span></h2>
      ${g.items.length ? g.items.map(it => `
        <p class="ref">${it.html}
          <span class="why">Matched ${it.matched.map(m => `<i>${esc(m)}</i>`).join('<span class="dot">·</span>')}</span>
        </p>`).join("")
        : `<p class="empty">Nothing in this section yet.</p>`}`).join("")}
    <footer>
      Showing ${shown} of ${d.total}. Items drop off automatically once they pass ${d.window} days.
      <table>${d.log.map(r => `<tr><td>${esc(r.at.replace("T"," ").replace("Z",""))}</td>
        <td>${esc(r.theme)}</td><td>+${r.added} new / ${r.checked} checked</td></tr>`).join("")}</table>
    </footer>`;

  const qi = document.getElementById("q");
  qi.addEventListener("input", e => { filters.q = e.target.value; render();
    const n = document.getElementById("q"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); });
  document.querySelectorAll("[data-t]").forEach(b =>
    b.addEventListener("click", () => { filters.type = b.dataset.t; render(); }));
  document.getElementById("copy").addEventListener("click", async e => {
    const txt = groups.flatMap(g => [g.label.toUpperCase(), ...g.items.map(i => i.text), ""]).join("\n");
    await navigator.clipboard.writeText(txt);
    e.target.textContent = "Copied"; setTimeout(() => e.target.textContent = "Copy list", 1600);
  });
}
</script>
</body>
</html>
"""

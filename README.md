# EU R&I Geopolitics Scanner

A small GitHub-hosted scanner. Every 6 hours it queries a rotating set of keywords
and sources, keeps only items that clear a strict "crucial issue" gate, drops
duplicates, and rebuilds a password-protected page with the findings as an APA 7
reference list.

## What it does

| | |
|---|---|
| Runs | every 6 hours via GitHub Actions (`00:05 / 06:05 / 12:05 / 18:05 UTC`) |
| Window | rolling 6 months — older items fall off the page automatically |
| Language | English only |
| Output | `docs/index.html`, white background, APA 7 hanging-indent list |
| Password | `TutuScanner2026.` (typed with or without the full stop) |

## The gate: "crucial issues only"

An item is kept only if its title/abstract matches **at least one keyword from each
of three buckets** — EU, research & innovation, geopolitics — and **3+ distinct
keywords in total**. Programme names like *Horizon Europe* count as EU and R&I at
once. Every reference on the page shows the exact keywords that let it through, so
you can see why it is there and tighten the lists if the signal drifts.

Buckets live in `scanner/config.py` (`PROGRAMME_TERMS`, `EU_TERMS`, `RI_TERMS`,
`GEO_TERMS`).

## The rotation

Six themed slots, one per run, so a full cycle takes 36 hours. Each slot uses
different queries **and** different sources:

1. Research & knowledge security
2. Sovereignty & strategic autonomy
3. Framework programme & association politics
4. Critical technologies & supply chains
5. Talent, mobility & academic freedom
6. Defence, space & science diplomacy

The slot is derived from the clock (`hours since epoch / 6`), so no state is needed
and a missed run does not desynchronise anything.

## Sources

* **OpenAlex** and **Crossref** for journal articles (English filter, 6-month filter).
* **RSS pools**, rotated per slot: European Commission press corner, EPRS, EUISS,
  Jacques Delors Institute, ECFR, CSIS, Ifri, RAND, Bruegel, MERICS, ECIPE, CEPR,
  Nature, Science, Physics World.
* **Google News**, including per-slot `site:` probes for publishers that block
  scrapers directly — Science|Business, Times Higher Education, University World
  News, Politico Europe, Euractiv, Chatham House, Clingendael, SWP, Carnegie.

Feeds move and break. Check yours any time:

```bash
python -m scanner.scan --check-feeds
```

## Deduplication

Every item is fingerprinted by DOI, normalised URL (tracking parameters stripped)
and normalised title. Fingerprints persist in `state/seen.json`, so an item that
appeared in an earlier scan never reappears, even under a different rotation slot
or from a different source.

## Setup

1. Create a repo and push these files.
2. **Settings → Pages → Source: GitHub Actions.**
3. **Settings → Actions → General → Workflow permissions: Read and write.**
4. Optional but recommended: **Settings → Secrets → Actions → New secret**,
   name `PAGE_PASSWORD`, value `TutuScanner2026.` — otherwise the workflow falls
   back to the same password hard-coded in `scan.yml`.
5. Optional: put your real address in `CONTACT_EMAIL` in `scanner/config.py`.
   OpenAlex and Crossref serve identified requests faster and rate-limit them less.
6. **Actions → scan → Run workflow** to seed the first results, then it runs itself.

Your page is at `https://<user>.github.io/<repo>/`.

## Local run

```bash
pip install -r requirements.txt
python -m scanner.scan            # slot picked from the clock
python -m scanner.scan --slot 2   # force a slot
open docs/index.html
```

## How the password works

The page is static, so a JavaScript `if (password === ...)` check would be
decoration — the data would sit in the page source for anyone who pressed
View Source. Instead the findings are encrypted with **AES-256-GCM**, with the key
derived from the password by **PBKDF2-SHA256, 250,000 iterations**. The browser
decrypts in memory after you type the password. Without it the file is ciphertext.

Change the password by updating the `PAGE_PASSWORD` secret; the next scan re-encrypts.

## Files

```
.github/workflows/scan.yml   schedule, run, commit, deploy
scanner/config.py            keywords, rotation, sources   <- tune this
scanner/scan.py              fetching, gating, dedup
scanner/render.py            APA 7 formatting, encryption, page template
state/items.json             live items (rolling 6 months)
state/seen.json              dedup fingerprints
state/runs.json              run log, shown at the foot of the page
docs/index.html              the page
```

## Notes

* Runtime is roughly 2–5 minutes per scan; well inside the Actions limit.
* APA 7 output is mechanical: news and reports lack the metadata articles have, so
  spot-check anything before it goes into a bibliography. The **Copy list** button
  gives you plain text for a manuscript.
* If a run finds nothing new, that is the gate working. Loosen it by lowering
  `MIN_KEYWORD_HITS` or adding terms to `GEO_TERMS`.

# EU R&I Geopolitics Scanner

A small GitHub Actions scanner for English-language material about **EU research and innovation in a geopolitical or security context**.

## The simple version

- A scan runs for **at least about 5 minutes and no more than 20 minutes**.
- During that time it runs several different search rounds instead of doing one quick search and stopping.
- If useful new items keep appearing after 5 minutes, it can continue toward the 20-minute limit.
- If two search rounds in a row find nothing new after the 5-minute minimum, it stops.
- It scans the latest **six months**.
- It gives more weight to **academic articles and reports** than to news.
- It publishes two password-protected pages:
  - `index.html` — the full source list with citations.
  - `summary.html` — a short, plain-language summary written for a reader around age 15.

For the repository `vevirm/ri`, the pages are normally:

- Full list: `https://vevirm.github.io/ri/`
- Simple summary: `https://vevirm.github.io/ri/summary.html`

## What the simple summary does

The summary page does not call an AI service and needs no extra API key. It groups the findings into a few broad themes and explains them in basic language, for example:

- keeping research safe;
- protecting Europe's economy;
- important technologies such as AI, chips and quantum;
- research money and competition;
- working with other countries;
- China, the United States, Russia and Ukraine.

It also shows:

- how many findings are academic articles, reports and news;
- which countries appear often;
- how long the latest scan ran;
- how many search rounds were completed;
- how many new items were added;
- a few important example sources.

The summary is a quick guide. The full source page is still the place to check the evidence.

## How the 5–20 minute scan works

The workflow runs:

```bash
python scanner.py --min-seconds 300 --max-seconds 1200 --round-interval 75
```

That means:

- `300` seconds = 5-minute minimum;
- `1200` seconds = 20-minute hard maximum;
- a new varied search round is started roughly every 75 seconds.

Search rounds rotate issue keywords, journals, institutional-report sources and news sources. Later rounds also switch to different search phrases from the same keyword batches.

The 20-minute value is a maximum, not a promise that every run lasts exactly 20 minutes. A normal run should now stay active for at least about 5 minutes.

## Relevance rules

A finding must clearly match all three areas:

1. **EU / Europe**
2. **research, innovation, science or technology**
3. **geopolitics, security or a strategic issue**

It must also match at least two distinct keyword concepts. The scanner keeps English-language material from the last 183 days and removes duplicates.

## Sources

Academic metadata comes from Crossref. Reports and news are discovered through English Google News RSS searches restricted to selected domains.

The source rotations and keywords are editable in `config.json`.

## Password protection

Create a GitHub Actions repository secret named:

`SCANNER_PASSWORD`

Both pages use the same password. Findings are encrypted into the static pages with PBKDF2-HMAC-SHA256 and AES-256-GCM, then decrypted locally in the browser after the password is entered.

GitHub Pages is still static hosting. This is client-side encrypted access, not server-side user authentication.

## GitHub setup

1. Put the repository files on GitHub.
2. Go to **Settings → Secrets and variables → Actions** and create `SCANNER_PASSWORD`.
3. Optional: create the repository variable `CROSSREF_MAILTO` with your email address.
4. Go to **Settings → Pages → Build and deployment → Source** and select **GitHub Actions**.
5. Go to **Actions → Scan EU R&I geopolitics (5-20 min) → Run workflow**.
6. Wait for `scan-and-build` and then `deploy` to turn green.

## Files

- `config.json` — keywords, search phrases, source rotations and quotas.
- `scanner.py` — repeated 5–20 minute scanning, relevance scoring and deduplication.
- `build_page.py` — builds the encrypted full page and simple summary page.
- `data/findings.json` — current six-month findings.
- `data/seen.json` — deduplication fingerprints.
- `data/state.json` — last scan time, duration, rounds and rotation information.
- `.github/workflows/scan.yml` — scheduled/manual scan and Pages deployment.
- `docs/index.html` — generated full findings page.
- `docs/summary.html` — generated simple summary page.

## Schedule

The Action is scheduled every six hours:

```text
17 */6 * * *
```

GitHub scheduled runs can start a little later than the exact cron time.

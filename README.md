# EU R&I Geopolitics Scanner

A deliberately small GitHub Actions scanner for **English-language EU research & innovation in a geopolitical context**. It scans the previous **183 days (~6 months)**, rejects weakly related items, deduplicates findings, ranks peer-reviewed work and institutional reports above news, and publishes a plain white password-protected GitHub Pages page with **APA 7-style citations**.

## What it does

- Runs automatically every **6 hours** (`17 */6 * * *`, UTC-based GitHub schedule).
- Gives the scanner a **hard 20-minute budget**; page rebuild/publish runs afterward.
- Searches two rotating issue batches per run.
- Rotates journal groups, institutional-report sources, and news publishers independently.
- Requires each finding to match all three relevance categories:
  1. **EU/Europe**
  2. **R&I / research / science / technology**
  3. **Geopolitical / security / strategic issue**
- Requires **at least two distinct keyword concepts** in the item metadata.
- Keeps only English-language material from the last six months.
- Deduplicates by DOI first, then normalized title, then URL fingerprint.
- Stores seen fingerprints so the same item is not re-added on later scans.
- Ranks source types strongly: **peer-reviewed > report > news**.
- Publishes `docs/index.html` as an encrypted static page.

## Ranking emphasis

Base score before keyword/relevance bonuses:

| Type | Base weight | Max new per scan |
|---|---:|---:|
| Peer-reviewed journal article | 100 | 18 |
| Institutional / think-tank report | 82 | 12 |
| News | 34 | 6 |

This deliberately makes news a minority signal rather than the core product.

## Crucial issue keyword rotation

The full editable list is in `config.json`. The six rotating batches are:

1. **Research security** — research security, knowledge security, foreign interference, technology leakage, trusted research, due diligence, international research cooperation, Horizon Europe.
2. **Economic security** — economic security, strategic autonomy, technological sovereignty, strategic dependency/dependencies, de-risking, export controls, investment screening.
3. **Critical technology / dual-use** — critical technologies, dual-use, semiconductors, AI, quantum, biotechnology, space technology, cybersecurity, technology security.
4. **Funding / competitiveness** — Horizon Europe, framework programme, FP10, European Competitiveness Fund, R&D/R&I funding, innovation gap, competitiveness, China, United States.
5. **Science diplomacy / cooperation** — science diplomacy, international research cooperation, Horizon Europe association, academic freedom, global approach, strategic interests, open and secure cooperation.
6. **China / US / Russia / Ukraine** — China, Chinese, United States, US/U.S., Russia, Russian, Ukraine, sanctions, transatlantic, Taiwan, Indo-Pacific, technology competition.

Each batch also contains compound search phrases such as `European research security` or `EU research China technology security`; the result must still pass the strict multi-category validation after retrieval.

Two batches are scanned each run. With six batches and a six-hour cadence, every issue batch is revisited about every **18 hours**.

## Rotating scholarly journals

### Group A — R&I policy core
- Research Policy
- Science and Public Policy
- Research Evaluation
- Industry and Innovation
- Technological Forecasting and Social Change

### Group B — Europe and geopolitics
- Journal of European Public Policy
- Journal of Common Market Studies
- European Security
- International Affairs
- Global Policy

### Group C — science, technology and security
- Minerva
- Science, Technology, & Human Values
- Technology in Society
- European Journal of International Security
- Defence and Peace Economics

Scholarly metadata is retrieved from **Crossref** and constrained to `journal-article` results plus the rotating journal allow-list. No scholarly API key is required.

## Rotating report / institution sources

### Group A — EU / OECD
- European Commission — Research and Innovation
- European Commission
- Joint Research Centre
- European Parliament Think Tank
- OECD

### Group B — European policy institutes
- Bruegel
- MERICS
- ECFR
- CEPS
- EUISS

### Group C — security / strategy
- NATO
- SIPRI
- Chatham House
- Carnegie Europe
- European University Institute

## Rotating news sources

### Group A — EU policy news
- Science|Business
- POLITICO Europe
- Euractiv
- Reuters

### Group B — research news
- Nature
- Science
- Research Professional News
- Times Higher Education

### Group C — international news
- Reuters
- Financial Times
- BBC
- Deutsche Welle

Report and news discovery uses English Google News RSS site-restricted searches. This keeps the project keyless and simple, but those feeds are an external dependency and can change.

## Password protection

The page does **not** commit the password or plaintext findings. `build_page.py` encrypts the findings payload with:

- PBKDF2-HMAC-SHA256
- 250,000 iterations
- random salt
- AES-256-GCM

The browser asks for the password and decrypts locally.

Important: GitHub Pages is static hosting, so this is **encrypted client-side access**, not true server-side authentication. It prevents casual source viewing and keeps the findings out of the HTML plaintext, but a determined attacker can still attempt offline password guessing. For high-security access control, put the site behind a real authentication layer such as an access proxy.

## GitHub setup

1. Create a GitHub repository and copy these files into it.
2. In **Settings → Secrets and variables → Actions → New repository secret**, create a secret named `SCANNER_PASSWORD` and set it to the password you chose for this scanner.
3. Optional: create a repository variable named `CROSSREF_MAILTO` with your email address. Crossref works without it, but supplying contact information is polite API usage.
4. In **Settings → Pages → Build and deployment → Source**, choose **GitHub Actions**.
5. Open **Actions → Scan EU R&I geopolitics → Run workflow** once to seed/update the page immediately. Scheduled runs then occur every six hours.

The initial `docs/index.html` in this package is already encrypted with the password you specified when requesting the scanner. The Action still needs `SCANNER_PASSWORD` so it can encrypt each future update with the same password.

## Local test

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python scanner.py --max-seconds 1200
SCANNER_PASSWORD='your-password' python build_page.py
python -m http.server 8000 -d docs
```

Then open `http://localhost:8000`.

## Files

- `config.json` — keywords, issue batches, source rotations, quotas.
- `scanner.py` — retrieval, relevance gate, scoring, dedupe, six-month pruning.
- `build_page.py` — encrypted white-background APA-style page generator.
- `data/findings.json` — current six-month findings store.
- `data/seen.json` — persistent dedupe fingerprints.
- `data/state.json` — rotation/run state.
- `.github/workflows/scan.yml` — six-hour scan + GitHub Pages deployment.
- `docs/index.html` — generated encrypted page.

## Notes

- GitHub scheduled workflows can run a little later than the exact cron minute.
- APA output is generated from available metadata; incomplete publisher metadata can produce an abbreviated citation.
- The scanner intentionally favors precision over recall. If an item does not clearly combine EU/Europe, R&I, and a geopolitical/security issue, it is excluded.

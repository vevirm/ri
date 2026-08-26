"""Keywords, rotation slots and sources for the EU R&I geopolitics scanner.

Edit this file to tune what gets scanned. Nothing else needs to change.
"""

# How far back an item may be published to still count (days).
LOOKBACK_DAYS = 183          # ~6 months

# Minimum number of DISTINCT keyword matches for an item to be kept.
# (The three-bucket rule below means the real floor is usually higher.)
MIN_KEYWORD_HITS = 3

# ---------------------------------------------------------------------------
# The gate has three buckets. An item is kept only when it matches at least
# one term from EACH of EU + R&I + GEOPOLITICS, and MIN_KEYWORD_HITS distinct
# terms overall. PROGRAMME_TERMS count as both EU and R&I at once. The
# geopolitics bucket needs either one GEO_CORE term or two GEO_SOFT ones.
# ---------------------------------------------------------------------------
PROGRAMME_TERMS = [
    "horizon europe", "horizon 2020", "framework programme", "fp10", "fp9",
    "european research area", "european research council", "erc grant",
    "european innovation council", "marie sklodowska-curie", "joint research centre",
    "european institute of innovation", "eic accelerator", "euratom",
    "european defence fund", "european space agency", "cern",
    "eu chips act", "european innovation act", "important projects of common european interest",
    "ipcei", "european universities alliance", "widening participation",
    "european competitiveness fund", "innovate europe", "eu missions",
]

EU_TERMS = [
    "european union", "european commission", "european parliament",
    "european council", "eu member states", "eu budget", "brussels",
    "eu policy", "eu strategy", "eu regulation", "european industrial",
    "eu single market", "european economy", "eu institutions", "european",
]

RI_TERMS = [
    "research", "researcher", "researchers", "science", "scientific", "scientist",
    "innovation", "university", "universities", "academia", "academic",
    "r&d", "research and development", "laboratory", "phd", "doctoral",
    "technology development", "deep tech", "start-up", "patent",
    "knowledge transfer", "higher education", "science funding", "grant",
]

# Strong signals: one is enough to make an item geopolitical.
GEO_CORE = [
    "research security", "knowledge security", "foreign interference",
    "technological sovereignty", "technology sovereignty", "digital sovereignty",
    "strategic autonomy", "economic security", "de-risking", "derisking",
    "dual-use", "dual use", "export control", "export controls",
    "technology transfer", "sanctions", "espionage", "critical raw materials",
    "supply chain", "supply chains", "semiconductor", "semiconductors",
    "chip war", "quantum", "artificial intelligence act", "ai sovereignty",
    "compute capacity", "brain drain", "talent war", "researcher mobility",
    "academic freedom", "science diplomacy", "china", "chinese", "russia",
    "russian", "ukraine", "united states", "washington", "trump",
    "association agreement", "third country", "third countries", "switzerland",
    "united kingdom", "israel", "defence", "defense", "military", "civil-military",
    "space security", "biosecurity", "cyber", "critical technologies",
    "geopolitics", "geopolitical", "geoeconomic", "decoupling", "transatlantic",
    "national security", "trade war", "foreign funding", "security screening",
]

# Weak signals: on their own they mean little, so two are required.
GEO_SOFT = [
    "sovereignty", "tariff", "tariffs", "funding cuts", "visa", "competitiveness",
    "dependency", "dependencies", "resilience", "cyber", "autonomy", "alliance",
    "partnership", "bloc", "strategic", "global race", "leadership", "screening",
    "protectionism", "industrial policy", "critical", "vulnerability",
]

GEO_TERMS = GEO_CORE + GEO_SOFT

# ---------------------------------------------------------------------------
# Rotation. 4 runs a day x 6 slots = each slot comes round every 36 hours.
# Each slot has: a set of query pairs for the academic APIs, and a source pool.
# ---------------------------------------------------------------------------
ROTATION = [
    {
        "name": "Research & knowledge security",
        "queries": [
            "research security European Union",
            "knowledge security universities Europe",
            "foreign interference academia Europe",
            "dual-use research export controls Europe",
        ],
        "news": ["research security EU universities", "knowledge security European research"],
        "feeds": "eu_institutions",
        "sites": ["sciencebusiness.net", "universityworldnews.com", "chathamhouse.org"],
    },
    {
        "name": "Sovereignty & strategic autonomy",
        "queries": [
            "technological sovereignty European Union",
            "open strategic autonomy research innovation",
            "economic security strategy European Commission",
            "de-risking technology Europe China",
        ],
        "news": ["EU technological sovereignty research", "European economic security technology"],
        "feeds": "thinktanks_geo",
        "sites": ["politico.eu", "bruegel.org", "swp-berlin.org"],
    },
    {
        "name": "Framework programme & association politics",
        "queries": [
            "Horizon Europe association third countries",
            "FP10 framework programme budget politics",
            "European Research Area governance geopolitics",
            "Horizon Europe Switzerland United Kingdom association",
        ],
        "news": ["Horizon Europe association", "FP10 research budget European Union"],
        "feeds": "science_press",
        "sites": ["sciencebusiness.net", "timeshighereducation.com", "researchprofessionalnews.com"],
    },
    {
        "name": "Critical technologies & supply chains",
        "queries": [
            "semiconductors European Union chips act",
            "critical raw materials research innovation Europe",
            "quantum technology sovereignty Europe",
            "artificial intelligence compute capacity Europe",
        ],
        "news": ["EU chips act semiconductors research", "EU quantum strategy sovereignty"],
        "feeds": "thinktanks_econ",
        "sites": ["euractiv.com", "carnegieendowment.org", "clingendael.org"],
    },
    {
        "name": "Talent, mobility & academic freedom",
        "queries": [
            "researcher mobility brain drain Europe",
            "academic freedom European Union science",
            "scientific talent attraction Europe United States",
            "visa restrictions international researchers Europe",
        ],
        "news": ["Europe attract researchers United States", "academic freedom EU researchers"],
        "feeds": "science_press",
        "sites": ["timeshighereducation.com", "nature.com", "theguardian.com"],
    },
    {
        "name": "Defence, space & science diplomacy",
        "queries": [
            "European Defence Fund research innovation",
            "civil-military dual use research European Union",
            "space security European Union research",
            "science diplomacy European Union geopolitics",
        ],
        "news": ["EU defence research funding", "EU science diplomacy geopolitics"],
        "feeds": "eu_institutions",
        "sites": ["euobserver.com", "iss.europa.eu", "sciencebusiness.net"],
    },
]

# ---------------------------------------------------------------------------
# RSS/Atom sources, grouped into pools that rotate with the slots.
# English-language only. Dead feeds are skipped silently; run
#   python -m scanner.scan --check-feeds
# to see which ones are alive.
# ---------------------------------------------------------------------------
FEED_POOLS = {
    "eu_institutions": [
        ("European Commission press corner", "https://ec.europa.eu/commission/presscorner/api/rss?language=en", "report"),
        ("European Parliamentary Research Service", "https://epthinktank.eu/feed/", "report"),
        ("EU Institute for Security Studies", "https://www.iss.europa.eu/rss.xml", "report"),
        ("Jacques Delors Institute", "https://institutdelors.eu/en/feed/", "report"),
    ],
    "thinktanks_geo": [
        ("European Council on Foreign Relations", "https://ecfr.eu/feed/", "report"),
        ("Center for Strategic and International Studies", "https://www.csis.org/rss.xml", "report"),
        ("Institut francais des relations internationales", "https://www.ifri.org/en/rss.xml", "report"),
        ("RAND Corporation", "https://www.rand.org/news/press.xml", "report"),
    ],
    "thinktanks_econ": [
        ("Bruegel", "https://www.bruegel.org/rss.xml", "report"),
        ("MERICS", "https://merics.org/en/rss", "report"),
        ("European Centre for International Political Economy", "https://ecipe.org/feed/", "report"),
        ("Centre for Economic Policy Research", "https://cepr.org/rss.xml", "report"),
    ],
    "science_press": [
        ("Nature", "https://www.nature.com/nature.rss", "news"),
        ("Science", "https://www.science.org/rss/news_current.xml", "news"),
        ("Physics World", "https://physicsworld.com/feed/", "news"),
        ("European Parliamentary Research Service", "https://epthinktank.eu/feed/", "report"),
    ],
}

# Google News is a catch-all, and the only way in for publishers whose own RSS sits
# behind a bot wall (Science|Business, THE, Politico Europe, University World News).
# Each slot probes a different set of domains via the "sites" key above.
USE_GOOGLE_NEWS = True

# Put your email here — OpenAlex and Crossref give faster, more reliable
# service to requests that identify themselves. Optional but polite.
CONTACT_EMAIL = "scanner@example.org"

PAGE_TITLE = "EU R&I in geopolitical context"
PAGE_SUBTITLE = "Rotating scan of research articles, news and institutional reports"

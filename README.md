# Truewise

A public-data platform that turns scattered US federal education data into clear, honest
guidance for students and families. Mission: replace the scary or hidden number (sticker
price, anecdote, unclaimed aid) with the real one, drawn from public data.

- **Name:** Truewise
- **Domain:** truewise.us (available as of 2026-07; not yet registered — see `docs/GO_PUBLIC.md`)
- **Stage:** Iteration 0 (foundation) built: static landing page, CI, tests, docs. Ready to go
  public. First module is **Value Check**.
- **Nature:** Portfolio / skills / social-impact project. ~$0 direct revenue expected.

## Read these first (in order)
1. **CLAUDE.md** — condensed project context (loaded automatically by AI sessions).
2. **docs/BRIEF.md** — one-page product brief.
3. **Truewise - Project Plan v2 (Reputation-First).md** — current plan and build order.
4. **Truewise - Iteration Plan & Checklist.md** — execution checklist (design→code→test→deploy).
5. **PLAN.md** — v1 full plan (architecture/data/risks still valid; ordering superseded by v2).
6. **DATA_SOURCES.md** — dataset URLs, grain, key fields, join keys.
7. **HANDOFF.md** — decisions log, open questions.
8. **docs/GO_PUBLIC.md** — the manual steps to publish (GitHub, domain, Cloudflare Pages).

## Quick start (for the takeover session)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Get a free College Scorecard API key: https://api.data.gov/signup/
# Then follow pipeline/load_scorecard.py (has TODOs marking the first steps)
python pipeline/load_scorecard.py
```

## Repo layout
```
.
├── README.md  CLAUDE.md  PLAN.md  HANDOFF.md  DATA_SOURCES.md
├── LICENSE                    # MIT (code); published datasets are CC-BY
├── pyproject.toml             # ruff + pytest config
├── requirements.txt           # pipeline deps
├── requirements-dev.txt       # ruff, pytest, pre-commit
├── .pre-commit-config.yaml
├── .github/workflows/ci.yml   # lint → test → build → deploy (placeholder)
├── pipeline/                  # download + load + transform (the shared spine)
│   └── load_scorecard.py      # starter stub for the Scorecard loader
├── site/                      # static frontend (index.html + styles.css)
├── tests/                     # pytest (smoke tests today; validation later)
├── docs/                      # BRIEF.md, IMPACT_LOG.md, GO_PUBLIC.md
├── analysis/                  # reproducible analysis scripts (STATS what-if, etc.)
├── archive/fvt/               # dated FVT/GE snapshots (Iteration 2)
└── data/                      # gitignored: raw/ and parquet/ working sets
```

## Dev quick start
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
ruff check . && ruff format --check . && pytest
```

## First milestone (M1, news-window MVP)
Data spine (College Scorecard) → **Value Check** (flagship) + FVT/GE monitor → published
dataset + `truewise-data` package + methodology write-up + press. See the v2 plan and the
Iteration Plan checklist. Iterations 0–4 target well before the 2026-10-01 FVT reporting cycle
close.

# Truewise

A public-data platform that turns scattered US federal education data into clear, honest
guidance for students and families. Mission: replace the scary or hidden number (sticker
price, anecdote, unclaimed aid) with the real one, drawn from public data.

- **Name:** Truewise
- **Domain:** [truewise.dev](https://truewise.dev) (registered 2026-07-13)
- **Stage:** **Value Check is live** at [truewise.dev/value-check](https://truewise.dev/value-check/)
  — look up any US college program and see whether its graduates out-earn a typical
  high-school graduate, using ED's own figures.
- **Nature:** Portfolio / skills / social-impact project. ~$0 direct revenue expected.

## Use the data

The cleaned, joined dataset ships as a Python package (data licensed CC-BY-4.0):

```bash
pip install truewise-data
```
```python
import truewise_data as tw
df = tw.load_value_check(decided_only=True)   # earnings vs a HS-grad benchmark, per program
```

Source in [`packages/truewise-data/`](packages/truewise-data/); columns in
[`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md).

## Read these first
1. **docs/BRIEF.md** — one-page product brief (mission, modules, principles).
2. **DATA_SOURCES.md** — dataset URLs, grain, key fields, join keys.

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

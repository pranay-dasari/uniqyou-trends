# UniqYou — Fashion Trend Intelligence (prototype)

Early trend **detection** (momentum, not forecasting) + merchandising intelligence for women's fashion.
Signals → velocity/persistence/spike → cross-source confidence → lifecycle stage → **TEST / INCREASE / WATCH / PASS**.
A decision-support tool, not a replacement for a buyer.

## For interviewers — what this is and how it works

**What it does.** Spots which fashion keywords are accelerating right now and recommends an
action (TEST / INCREASE / WATCH / PASS) before a trend peaks. It detects momentum, not the
future — it doesn't predict next month's demand.

**The logic.**
1. **Google Trends** (52 weeks, weekly) is the core signal — momentum (this week vs. the prior
   4-week average), streak (consecutive rising weeks), and slope.
2. **Wikipedia page views**, **magazine RSS feeds** (Vogue, Elle, Bazaar and 5 more), and **Reddit**
   (optional) each independently vote on whether the same keyword is rising.
3. **Cross-source agreement** becomes a confidence score — a keyword rising on Google alone is
   noise; rising on 3–4 independent sources at once is a real signal.
4. Momentum shape + confidence → lifecycle stage (Emerging/Rising/Peak/Declining/Spike) →
   recommendation. See `pipeline/velocity.py`, `confidence.py`, `lifecycle.py`, `recommender.py`.

The 35 keywords (`data/keywords.py`) are hand-curated across 6 categories for this demo — in
production they'd be generated from the retailer's own catalog and search logs.

**It's a prototype, by design.**
- Fixed keyword list, not a live catalog feed.
- No inventory, margin, MOQ or lead-time data — a human buyer still decides.
- Backtest numbers on Demo data prove the *test harness* works, not real-world accuracy — see
  the Backtest section below.
- Google Trends is fetched via an unofficial library (rate-limited, ~30s); Reddit needs manual
  API keys and is off by default.

**Path to production / real-time.**

| Prototype (now) | Production |
|---|---|
| Manual "Refresh" button | Scheduled job (cron/Airflow) every few hours |
| 35 fixed keywords | Auto-generated from live catalog + search logs |
| Unofficial Google Trends scraper | Official Trends API or a licensed data vendor |
| Local file cache (`data/cache/`) | Real database (Postgres/BigQuery) storing full history |
| Single Streamlit process does fetch + render | Separate ingestion service feeding a served dashboard, so one slow fetch doesn't block the UI |
| No alerting | Slack/email alert when a trend crosses the TEST threshold |
| Rule-based thresholds | Thresholds tuned against actual sell-through data, closing the feedback loop |

The scoring logic itself (velocity → confidence → stage → action) doesn't need to change for
production — it's the data freshness, scale, alerting and feedback loop around it that would.

## Run
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # optional: Reddit credentials
streamlit run app.py
pytest tests                # unit tests
```
- **Demo (Synthetic)** is the default and needs no network. It is labelled `[DEMO DATA]` everywhere.
- **Live** fetches Google Trends via `trendspy` (~30 s, rate-limited; cached per day in `data/cache/`). If it fails, the app falls back to synthetic data and says so.
- Without Reddit credentials or reachable RSS feeds, confidence is computed from the remaining sources and the UI says so.

## Layout
`pipeline/ingest.py` ingestion + synthetic generator · `velocity.py` · `confidence.py` · `lifecycle.py` · `recommender.py` · `backtest.py` · `app.py` dashboard.

## Backtest (how the numbers are produced)
Walk-forward, no look-ahead. The model is rule-based (nothing is fitted), so the first 40 weeks are history and the last 12 are test origins with a 4-week look-ahead.
- MAE/MAPE: slope-projected score vs realised score (naive "no change" MAE shown as baseline).
- Stage accuracy: stage is correct if the trend moved the way it implies (Emerging/Rising up, Peak flat, Declining/Dead down, Spike reverts), ±5%.
- Precision@TEST: share of TEST calls followed by a ≥5% rise (base rate shown for context).
- Lead time: weeks between first EMERGING flag and the peak, for peaks inside the test window (n reported).
- Historically only Google Trends exists, so backtest confidence is single-source.
All figures are computed at runtime. Targets on the dashboard are **prototype targets**, not industry benchmarks. On synthetic data the backtest demonstrates the harness only.

## Data-quality handling
- **Minimum volume:** keywords Google reports as zero in >25% of weeks (or median score <5) are excluded from scoring, tiles and the backtest and listed in an expander — their % changes are small-number noise.
- **Google retries:** transient errors retry with backoff; a 429 stops immediately and the dashboard serves what it has. Partial results are cached per keyword and only the missing ones are retried on Refresh.
- **Editorial RSS:** 8 working feeds. If feeds are unreachable or fewer than 60 articles are parsed, the source is dropped from confidence instead of counting as a "no" vote.
- **Reddit:** fewer than 5 mentions across both windows → no signal (0%), not a big % change from a tiny count.
- **Spike:** velocity > 80% and streak == 1 (a decaying earlier spike, streak 0, is not a fresh spike; this tightens the spec's `<= 1`).

## Demo storyline (pinned)
Demo data pins two keywords: **linen co-ord** (8-week rise, Reddit +65%, 8 editorial hits → 3/3 sources, TEST) and **mesh fabric** (one-week ~+330% jump, weak side signals, confidence ~30% → WATCH). The rest is a seeded random mix. Demo Reddit/editorial values are generated from each trend's velocity, so cross-source agreement in demo mode is illustrative, not independent.

## Known limitations / notes
- The seed list in `data/keywords.py` contains 35 keywords (the spec said 40; only 35 were listed).
- The spec's default rule sends stable low-interest series to "Declining" → PASS; the by-stage accuracy table exposes how often that is wrong.
- The slope-projection forecast (MAE/MAPE) does not beat a naive "no change" forecast on live data; the product is momentum detection, so read stage accuracy / precision@TEST / lead time as the meaningful metrics.
- Google normalises each request; every keyword is re-normalised to its own 12-month peak (=100).
- TEST means a small exposure to validate demand; the system knows nothing about MOQ, lead time, margin or inventory.
- Optional clustering/UMAP extension (spaCy, sentence-transformers) is not implemented.

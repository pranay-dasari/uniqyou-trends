# UniqYou — Fashion Trend Intelligence (prototype)

Early trend **detection** (momentum, not forecasting) + merchandising intelligence for women's fashion.
Signals → velocity/persistence/spike → cross-source confidence → lifecycle stage → **TEST / INCREASE / WATCH / PASS**.
A decision-support tool, not a replacement for a buyer.

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

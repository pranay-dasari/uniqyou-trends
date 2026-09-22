"""Signal ingestion: Google Trends (trendspy), Reddit (PRAW), editorial RSS (feedparser).

Every fetcher caches to data/cache/ and degrades gracefully: an unavailable source
returns an empty result and the confidence score drops it from the denominator.
"""
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"

SUBREDDITS = ["femalefashionadvice", "IndianFashionAddicts", "streetwear", "frugalfemalefashion"]
RSS_FEEDS = [
    "https://www.vogue.in/feed/rss",
    "https://www.vogue.com/feed/rss",
    "https://www.vogue.co.uk/feed/rss",
    "https://www.harpersbazaar.com/rss/fashion.xml/",
    "https://www.elle.com/rss/fashion.xml/",
    "https://www.whowhatwear.com/rss",
    "https://fashionista.com/.rss/excerpt/",
    "https://www.glamour.com/feed/rss",
]
MIN_RSS_ARTICLES = 60  # below this the editorial sample is too thin to count as a signal

MIN_REDDIT_MENTIONS = 5
_GENERIC_TAIL = {"women", "fashion", "outfit", "aesthetic"}


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _match_term(keyword: str) -> str:
    """Normalise a keyword for text matching: lowercase, hyphens -> spaces, drop generic tail word."""
    words = re.sub(r"[-_]", " ", keyword.lower()).split()
    if len(words) > 1 and words[-1] in _GENERIC_TAIL:
        words = words[:-1]
    return " ".join(words)


def _normalise_text(text: str) -> str:
    return re.sub(r"[-_]", " ", text.lower())


# --------------------------------------------------------------------------- Google Trends
def clear_signal_caches() -> None:
    """Delete today's Reddit/RSS caches so the next fetch is fresh (used by the Refresh button)."""
    for pattern in (f"reddit_{_today()}.json", f"rss_{_today()}.json", f"wiki_{_today()}.json"):
        for f in CACHE_DIR.glob(pattern):
            f.unlink()


def fetch_google_trends(keywords: list[str], timeframe: str = "today 12-m", geo: str = "IN",
                        use_cache: bool = True, force: bool = False) -> pd.DataFrame:
    """Weekly 0-100 interest per keyword (index = dates, columns = keywords).

    Fetched in batches of 5 (Google's limit). Google normalises each request to its own
    maximum, so batches are not comparable; every keyword is therefore re-normalised to its
    own peak (= 100), exactly what a single-keyword Google Trends query returns. Scores mean
    "share of this keyword's own 12-month peak", and velocity is unaffected by the scaling.
    Returns an empty DataFrame if nothing could be fetched.
    force=True re-fetches every keyword (cached values only fill in keywords that fail).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"trends_{_today()}_{geo or 'WW'}.csv"
    have = pd.read_csv(cache, index_col=0, parse_dates=True) if use_cache and cache.exists() else pd.DataFrame()
    missing = keywords if force else [k for k in keywords if k not in have.columns]
    if not missing:
        return have[[k for k in keywords if k in have.columns]]

    from trendspy import Trends  # imported lazily so demo mode has no network dependency

    tr = Trends()
    data: dict[str, pd.Series] = {}
    for i in range(0, len(missing), 5):
        batch = missing[i:i + 5]
        df = _fetch_batch(tr, batch, timeframe, geo)
        if df is _RATE_LIMITED:  # Google is throttling us: stop, serve what we have, retry on Refresh
            log.warning("Google Trends rate-limited (429); stopping with %d keyword(s) unfetched", len(missing) - len(data))
            break
        if df is None:
            continue
        for kw in batch:
            if kw in df:  # an all-zero series is a real answer (no volume), not a failed fetch
                peak = df[kw].max()
                data[kw] = df[kw] / peak * 100 if peak > 0 else df[kw]
        time.sleep(2.5)

    fresh = pd.DataFrame(data).clip(0, 100).round().astype(int) if data else pd.DataFrame()
    if force and not have.empty and not fresh.empty:
        # keep cached columns only for keywords this refetch failed to return
        keep = {c: have[c].reindex(fresh.index) for c in have.columns if c not in fresh.columns}
        keep = {c: v for c, v in keep.items() if not v.isna().any()}
        out = pd.concat([fresh, pd.DataFrame(keep, index=fresh.index).astype(int)], axis=1)
    else:
        out = pd.concat([have, fresh], axis=1) if not have.empty else fresh
    if out.empty:
        return out
    out = out[[k for k in keywords if k in out.columns]]
    out.to_csv(cache)  # partial results are kept; only the still-missing keywords are retried next call
    return out


_RATE_LIMITED = object()


def _fetch_batch(tr, batch: list[str], timeframe: str, geo: str, retries: int = 3):
    """One Google request. Transient errors retry with backoff; a 429 aborts immediately
    (waiting seconds does not lift a Google throttle, and it would block the dashboard)."""
    for attempt in range(retries):
        try:
            df = tr.interest_over_time(batch, timeframe=timeframe, geo=geo)
            if df is not None and not df.empty:
                if "isPartial" in df:  # the in-progress week understates interest and would bias velocity
                    df = df[~df["isPartial"].astype(bool)]
                return df.drop(columns=["isPartial"], errors="ignore").astype(float)
        except Exception as exc:
            log.warning("Google Trends %s attempt %d failed: %s", batch, attempt + 1, exc)
            if "429" in str(exc):
                return _RATE_LIMITED
        time.sleep(3 * 3 ** attempt)  # 3s, 9s, 27s
    return None


# Pinned so the demo storyline is stable regardless of the random mix:
#   linen co-ord -> sustained cross-source rise (TEST card); mesh fabric -> one-week viral spike (WATCH card)
SHOWCASE_PATTERNS = {"linen co-ord": "showcase_test", "mesh fabric": "showcase_spike"}
SHOWCASE_SIGNALS = {"linen co-ord": (65.0, 8), "mesh fabric": (-5.0, 0)}  # (reddit delta %, editorial hits)


def generate_synthetic_trends(keywords: list[str], weeks: int = 52, seed: int = 7) -> pd.DataFrame:
    """Realistic-looking synthetic weekly interest for demo mode. ALWAYS label as [DEMO DATA].

    Patterns are chosen so the pipeline's thresholds are actually exercised:
      emerging / rising : logistic S-curves whose inflection falls in the recent weeks
      declining         : mirrored S-curves
      spike             : flat baseline + one-week explosion (usually the latest week)
      peaked / stable   : high plateau / noisy flat line
    The generating pattern per keyword is stored in `df.attrs["patterns"]`.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=weeks, freq="W")
    t = np.arange(weeks)

    pinned = {k: v for k, v in SHOWCASE_PATTERNS.items() if k in keywords}
    keywords_rest = [k for k in keywords if k not in pinned]
    n = len(keywords_rest)
    mix = (["emerging"] * 7 + ["rising"] * 7 + ["spike"] * 3 + ["declining"] * 8
           + ["peaked"] * 6 + ["stable"] * 9)
    mix = (mix * (n // len(mix) + 1))[:n]
    rng.shuffle(mix)

    data, patterns = {}, {}
    for kw, pattern in pinned.items():
        if pattern == "showcase_test":  # flat, then +14%/week for 8 weeks -> streak 8, ~+57% momentum
            scores = np.full(weeks, 14.0) + rng.integers(-1, 2, weeks)
            scores[weeks - 9] = 14
            scores[weeks - 8:] = 14 * 1.14 ** np.arange(1, 9)
        else:  # flat baseline, then a single +50pt week
            scores = 15 + rng.normal(0, 1.5, weeks)
            scores[-2] = min(scores[-2], scores[-3])
            scores[-1] = scores[-2] + 50
        data[kw] = np.clip(scores, 0, 100).astype(int)
        patterns[kw] = pattern
    for kw, pattern in zip(keywords_rest, mix):
        noise = rng.normal(0, 1.0, weeks)
        if pattern == "emerging":
            base, amp = rng.integers(8, 20), rng.integers(35, 60)
            mid, w = rng.integers(weeks - 12, weeks + 4), rng.uniform(2, 3.5)
            scores = base + amp / (1 + np.exp(-(t - mid) / w)) + noise
        elif pattern == "rising":
            base, amp = rng.integers(25, 35), rng.integers(40, 55)
            mid, w = rng.integers(weeks - 10, weeks - 2), rng.uniform(3, 4)
            scores = base + amp / (1 + np.exp(-(t - mid) / w)) + noise
        elif pattern == "declining":
            base, amp = rng.integers(8, 22), rng.integers(35, 60)
            mid, w = rng.integers(weeks - 30, weeks - 4), rng.uniform(3, 5)
            scores = base + amp / (1 + np.exp((t - mid) / w)) + noise
        elif pattern == "peaked":
            scores = rng.integers(72, 90) + rng.normal(0, 2, weeks)
        elif pattern == "spike":
            base = rng.integers(10, 35)
            scores = base + rng.normal(0, 2, weeks)
            spike_week = weeks - 1 if rng.random() < 0.7 else int(rng.integers(weeks - 20, weeks - 4))
            scores[spike_week] += rng.integers(45, 70)
            if spike_week == weeks - 1:  # make it a genuine 1-week jump
                scores[-2] = min(scores[-2], scores[-3])
        else:  # stable
            scores = rng.integers(20, 65) + rng.normal(0, 2, weeks)
        data[kw] = np.clip(scores, 0, 100).astype(int)
        patterns[kw] = pattern

    df = pd.DataFrame(data, index=dates)
    df.attrs["patterns"] = patterns
    return df


# --------------------------------------------------------------------------- Reddit
def _reddit_client():
    cid, secret = os.getenv("REDDIT_CLIENT_ID"), os.getenv("REDDIT_CLIENT_SECRET")
    if not cid or not secret or cid.startswith("your_"):
        return None
    import praw
    return praw.Reddit(client_id=cid, client_secret=secret,
                       user_agent=os.getenv("REDDIT_USER_AGENT", "uniqyou_trends/1.0"))


def _reddit_timestamps(keywords: list[str], days_back: int = 28) -> dict[str, list[float]]:
    """keyword -> creation timestamps of matching posts (title/selftext) in the last N days."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"reddit_{_today()}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    reddit = _reddit_client()
    if reddit is None:
        return {}

    cutoff = time.time() - days_back * 86400
    sub = reddit.subreddit("+".join(SUBREDDITS))
    out: dict[str, list[float]] = {}
    try:
        for kw in keywords:
            term = _match_term(kw)
            stamps = []
            for post in sub.search(f'"{term}"', sort="new", time_filter="month", limit=100):
                if post.created_utc < cutoff:
                    continue
                text = _normalise_text(f"{post.title} {post.selftext}")
                if term in text:
                    stamps.append(post.created_utc)
            out[kw] = stamps
            time.sleep(0.5)
    except Exception as exc:
        log.warning("Reddit fetch failed: %s", exc)
        return {}
    cache.write_text(json.dumps(out))
    return out


def fetch_reddit_mentions(keywords: list[str], days_back: int = 30) -> dict[str, int]:
    """keyword -> post count in the last N days. Empty dict if credentials are missing."""
    stamps = _reddit_timestamps(keywords)
    cutoff = time.time() - days_back * 86400
    return {kw: sum(1 for s in stamps.get(kw, []) if s >= cutoff) for kw in stamps}


def fetch_reddit_velocity(keywords: list[str]) -> dict[str, float]:
    """% change in mentions: last 2 weeks vs the 2 weeks before. Empty dict if unavailable.

    Fewer than MIN_REDDIT_MENTIONS in total across both windows is too small to call a
    direction, so it returns 0 (no signal) instead of a misleading large percentage.
    """
    stamps = _reddit_timestamps(keywords)
    now = time.time()
    out = {}
    for kw, ts in stamps.items():
        recent = sum(1 for s in ts if s >= now - 14 * 86400)
        prev = sum(1 for s in ts if now - 28 * 86400 <= s < now - 14 * 86400)
        if recent + prev < MIN_REDDIT_MENTIONS:
            out[kw] = 0.0
        else:
            out[kw] = (100.0 if prev == 0 else (recent - prev) / prev * 100)
    return out


# --------------------------------------------------------------------------- RSS
def fetch_editorial_mentions(keywords: list[str], days_back: int = 14) -> dict[str, int]:
    """keyword -> number of articles (title + summary) mentioning it in the last N days.

    Returns {} if feeds are unreachable or the sample is too thin (< MIN_RSS_ARTICLES
    articles), so confidence drops the source instead of counting it as a negative vote.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"rss_{_today()}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    import feedparser

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    articles, feeds_ok = [], 0
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception as exc:
            log.warning("RSS %s failed: %s", url, exc)
            continue
        if not feed.entries:
            continue
        feeds_ok += 1
        for e in feed.entries:
            ts = e.get("published_parsed") or e.get("updated_parsed")
            if ts and datetime(*ts[:6], tzinfo=timezone.utc) < cutoff:
                continue
            articles.append(_normalise_text(f"{e.get('title', '')} {e.get('summary', '')}"))

    if feeds_ok == 0 or len(articles) < MIN_RSS_ARTICLES:
        return {}  # too little editorial coverage to be a signal: drop the source, don't score it as "no"
    counts = {kw: sum(1 for a in articles if _match_term(kw) in a) for kw in keywords}
    cache.write_text(json.dumps(counts))
    return counts


# --------------------------------------------------------------------------- Wikipedia attention
# Only keywords with a dedicated, specific English Wikipedia article are mapped. Keywords that
# redirect to a generic page (e.g. "bodycon dress" -> "Dress") are deliberately left out: their
# page views would measure general interest, not the trend.
WIKI_ARTICLES = {
    "wrap dress": "Wrap_dress",
    "shirt dress": "Shirtdress",
    "mini skirt": "Miniskirt",
    "denim jacket": "Jean_jacket",
    "dark academia outfit": "Dark_academia",
    "quiet luxury fashion": "Quiet_luxury",
    "Y2K fashion": "Y2K_aesthetic",
    "cottagecore dress": "Cottagecore",
    "indie sleaze": "Indie_sleaze",
    "clean girl aesthetic": "Clean_girl_aesthetic",
    "ballet flats": "Ballet_flat",
    "mary jane shoes": "Mary_Jane_shoes",
    "knit cardigan": "Cardigan_(sweater)",
    "wide leg pants": "Wide-leg_trousers",
    "platform boots": "Platform_shoe",
    "claw clip": "Hair_clip",
}
WIKI_MIN_WEEKLY_VIEWS = 100  # baseline below this is too small for a % change to mean anything
_WIKI_UA = {"User-Agent": "uniqyou_trends/1.0 (fashion trend research prototype)"}


def _attention_delta(daily_views: list[int]) -> float | None:
    """% change of the latest 7 days vs the 4 weeks before, using the *median* day (x7) so a
    single viral day cannot masquerade as a sustained rise. Needs 35 days; None if the
    baseline is below WIKI_MIN_WEEKLY_VIEWS."""
    if len(daily_views) < 35:
        return None
    v = daily_views[-35:]
    current = float(np.median(v[28:])) * 7
    baseline = float(np.median(v[:28])) * 7
    if baseline < WIKI_MIN_WEEKLY_VIEWS:
        return None
    return (current - baseline) / baseline * 100


def fetch_wikipedia_attention(keywords: list[str]) -> dict[str, float]:
    """keyword -> % change in Wikipedia page views (human traffic), for keywords with an article.

    Free, no API key. Returns {} if the API is unreachable (source is then unavailable).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"wiki_{_today()}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    import requests

    end = datetime.now(timezone.utc).date() - timedelta(days=2)  # Wikimedia's pageviews API lags ~2 days
    start = end - timedelta(days=34)
    out: dict[str, float] = {}
    failures = 0
    for kw in keywords:
        article = WIKI_ARTICLES.get(kw)
        if not article:
            continue
        url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/"
               f"all-access/user/{article}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
        delta, ok = None, False
        for attempt in range(3):
            try:
                r = requests.get(url, headers=_WIKI_UA, timeout=15)
                r.raise_for_status()
                delta, ok = _attention_delta([i["views"] for i in r.json()["items"]]), True
                break
            except Exception as exc:
                log.warning("Wikipedia %s attempt %d failed: %s", article, attempt + 1, exc)
                time.sleep(2 * (attempt + 1))
        if not ok:
            failures += 1
            continue
        if delta is not None:
            out[kw] = delta
        time.sleep(0.2)
    if not out and failures:
        return {}
    if failures == 0:  # never cache a partial result: the next call should retry the failures
        cache.write_text(json.dumps(out))
    return out


def generate_synthetic_attention(scores: pd.DataFrame, seed: int = 23) -> dict[str, float]:
    """Demo-only Wikipedia delta for the mapped keywords, loosely tracking velocity."""
    rng = np.random.default_rng(seed)
    out = {}
    for r in scores.itertuples():
        if r.keyword in WIKI_ARTICLES:
            out[r.keyword] = float(rng.normal(0, 8) if r.is_spike else np.clip(r.velocity * 0.5 + rng.normal(0, 12), -40, 80))
    return out


# --------------------------------------------------------------------------- synthetic side signals
def generate_synthetic_signals(scores: pd.DataFrame, seed: int = 11) -> tuple[dict, dict]:
    """Demo-only Reddit delta and editorial counts loosely correlated with each trend's velocity.

    `scores` is the output of score_all_keywords. Spikes deliberately get weak side signals
    (viral moment not yet picked up); about 1 in 4 real trends is decoupled to mimic disagreement.
    """
    rng = np.random.default_rng(seed)
    reddit, editorial = {}, {}
    for r in scores.itertuples():
        if r.keyword in SHOWCASE_SIGNALS:
            reddit[r.keyword], editorial[r.keyword] = SHOWCASE_SIGNALS[r.keyword]
            continue
        if r.is_spike:
            reddit[r.keyword] = float(rng.uniform(-15, 8))
            editorial[r.keyword] = int(rng.integers(0, 2))
            continue
        vel = r.velocity
        decoupled = rng.random() < 0.25
        reddit[r.keyword] = float(np.clip(vel * 0.8 + rng.normal(0, 15), -60, 150)
                                  if not decoupled else rng.normal(0, 12))
        lam = 0.5 + max(vel, 0) / 10 if not decoupled else 1.0
        editorial[r.keyword] = int(rng.poisson(lam))
    return reddit, editorial

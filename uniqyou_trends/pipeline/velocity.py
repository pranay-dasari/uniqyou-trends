"""Velocity, slope, streak, spike and persistence metrics."""
import numpy as np
import pandas as pd
from scipy import stats


def compute_velocity(series: pd.Series) -> float:
    """% change of the current week vs the mean of the 4 weeks before it.

    series: time-ordered weekly scores (oldest first), length >= 5.
    """
    if len(series) < 5:
        return 0.0
    current = series.iloc[-1]
    baseline = series.iloc[-5:-1].mean()  # weeks -5..-2
    if baseline == 0:
        return 0.0
    return float((current - baseline) / baseline * 100)


def compute_slope(series: pd.Series, window: int = 8) -> float:
    """Linear-regression slope (points/week) over the last `window` weeks."""
    recent = series.iloc[-window:].values.astype(float)
    if len(recent) < 2 or np.all(recent == recent[0]):
        return 0.0
    slope = stats.linregress(np.arange(len(recent)), recent).slope
    return float(slope)


def compute_streak(series: pd.Series) -> int:
    """Consecutive week-over-week increases ending at the latest data point."""
    streak = 0
    values = series.values
    for i in range(len(values) - 1, 0, -1):
        if values[i] > values[i - 1]:
            streak += 1
        else:
            break
    return streak


def is_spike(series: pd.Series, streak: int, velocity: float) -> bool:
    """Very high velocity (>80%) after exactly one week of increase: viral moment, not a trend.

    streak == 0 (latest week did not rise) is excluded: that is a decaying earlier spike,
    not a fresh one-week explosion.
    """
    return velocity > 80 and streak == 1


def compute_persistence(streak: int) -> float:
    """min(streak, 4) / 4  ->  0.25 (likely spike) .. 1.0 (sustained)."""
    return min(streak, 4) / 4.0


def compute_composite_score(velocity: float, slope: float) -> float:
    """Blend of noisy short-term velocity and steadier longer-term slope."""
    return 0.6 * velocity + 0.4 * (slope * 10)


MAX_ZERO_WEEK_SHARE = 0.25
MIN_MEDIAN_SCORE = 5


def has_sufficient_volume(series: pd.Series) -> bool:
    """False for keywords Google reports as (mostly) zero: their % changes are small-number noise.

    Scores are 0-100 relative to the keyword's own peak, so a series that is zero in more than
    25% of weeks, or whose median is below 5, has too little search volume to score.
    """
    s = series.dropna()
    return len(s) >= 5 and (s == 0).mean() <= MAX_ZERO_WEEK_SHARE and s.median() >= MIN_MEDIAN_SCORE


def split_by_volume(trends_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """(frame with only scoreable keywords, list of keywords dropped for insufficient volume)."""
    keep = [c for c in trends_df.columns if has_sufficient_volume(trends_df[c])]
    dropped = [c for c in trends_df.columns if c not in keep]
    return trends_df[keep], dropped


def score_series(series: pd.Series) -> dict:
    """All velocity metrics for one series (used by the dashboard and backtest)."""
    vel = compute_velocity(series)
    slp = compute_slope(series)
    stk = compute_streak(series)
    return {
        "current_score": int(series.iloc[-1]),
        "velocity": round(vel, 1),
        "slope": round(slp, 2),
        "streak": stk,
        "persistence": round(compute_persistence(stk), 2),
        "composite_score": round(compute_composite_score(vel, slp), 1),
        "is_spike": is_spike(series, stk, vel),
    }


def score_all_keywords(trends_df: pd.DataFrame) -> pd.DataFrame:
    """Apply all metrics to every keyword column of the weekly trends frame."""
    results = []
    for kw in trends_df.columns:
        series = trends_df[kw].dropna()
        if len(series) < 5:
            continue
        results.append({"keyword": kw, **score_series(series)})
    return pd.DataFrame(results)

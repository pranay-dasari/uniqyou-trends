"""Cross-source confidence scoring."""


def compute_confidence(
    velocity: float,
    reddit_delta: float,
    editorial_count: int,
    persistence: float,
    reddit_available: bool = True,
    rss_available: bool = True,
    attention_delta: float | None = None,
) -> dict:
    """confidence = 0.6 * (sources showing upward signal / sources available) + 0.4 * persistence.

    Upward signal per source:
      Google Trends: velocity > 15%   Reddit: delta > 10%   Editorial: >= 3 mentions
      Wikipedia page views: delta > 10% (only for keywords with an article; None = not counted)
    Unavailable sources are dropped from the denominator (graceful degradation).
    """
    signals = {"google_trends": 1 if velocity > 15 else 0}
    total = 1

    if reddit_available:
        signals["reddit"] = 1 if reddit_delta > 10 else 0
        total += 1
    if rss_available:
        signals["editorial"] = 1 if editorial_count >= 3 else 0
        total += 1

    if attention_delta is not None:
        signals["wikipedia"] = 1 if attention_delta > 10 else 0
        total += 1

    agreeing = sum(signals.values())
    confidence = 0.6 * (agreeing / total) + 0.4 * persistence
    return {
        "confidence": round(confidence, 3),
        "confidence_pct": int(round(confidence * 100)),
        "sources_agreeing": agreeing,
        "sources_total": total,
        "signals": signals,
    }

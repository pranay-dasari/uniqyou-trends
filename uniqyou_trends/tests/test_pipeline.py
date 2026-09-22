import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.keywords import ALL_KEYWORDS  # noqa: E402
from pipeline.backtest import run_backtest  # noqa: E402
from pipeline.confidence import compute_confidence  # noqa: E402
from pipeline.ingest import generate_synthetic_trends  # noqa: E402
from pipeline.lifecycle import Stage, classify_lifecycle  # noqa: E402
from pipeline.recommender import Action, recommend  # noqa: E402
from pipeline.velocity import compute_streak, compute_velocity, is_spike, split_by_volume  # noqa: E402


def test_velocity_and_streak():
    s = pd.Series([10, 10, 10, 10, 15])
    assert compute_velocity(s) == 50.0
    assert compute_streak(s) == 1
    assert compute_streak(pd.Series([1, 2, 3, 4, 5])) == 4


def test_spike_needs_short_streak():
    assert is_spike(pd.Series(dtype=float), 1, 300)
    assert not is_spike(pd.Series(dtype=float), 4, 300)


def test_confidence_degrades_gracefully():
    full = compute_confidence(50, 40, 5, 1.0)
    assert full["sources_total"] == 3 and full["confidence_pct"] == 100
    solo = compute_confidence(50, 0, 0, 1.0, reddit_available=False, rss_available=False)
    assert solo["sources_total"] == 1


def test_recommendations():
    assert recommend(Stage.EMERGING, 80, False)["action"] == Action.TEST
    assert recommend(Stage.SPIKE, 99, True)["action"] == Action.WATCH
    assert recommend(Stage.RISING, 75, False)["action"] == Action.INCREASE
    assert recommend(Stage.DEAD, 0, False)["action"] == Action.PASS
    assert recommend(Stage.EMERGING, 90, False, streak=1)["action"] == Action.WATCH


def test_lifecycle_priority():
    assert classify_lifecycle(30, 200, 5, 1, True) == Stage.SPIKE
    assert classify_lifecycle(40, 30, 3, 4, False) == Stage.EMERGING


def test_backtest_runs_and_is_computed():
    df = generate_synthetic_trends(ALL_KEYWORDS)
    a, b = run_backtest(df), run_backtest(df)
    assert a["n_keywords"] == len(ALL_KEYWORDS) and a["n_predictions"] > 0
    assert a["mae"] == b["mae"]  # deterministic
    assert 0 <= a["stage_accuracy"] <= 1


def test_spike_excludes_decaying_spike():
    assert not is_spike(pd.Series(dtype=float), 0, 300)


def test_sparse_series_filtered():
    df = pd.DataFrame({"good": [30, 35, 40, 38, 45, 50] * 3, "sparse": [0, 0, 0, 1, 0, 4] * 3})
    kept, dropped = split_by_volume(df)
    assert list(kept.columns) == ["good"] and dropped == ["sparse"]


def test_demo_showcase_storyline():
    from pipeline.ingest import generate_synthetic_signals
    from pipeline.velocity import score_all_keywords
    df = generate_synthetic_trends(ALL_KEYWORDS)
    sc = score_all_keywords(df).set_index("keyword")
    rd, ed = generate_synthetic_signals(sc.reset_index())
    lin, mesh = sc.loc["linen co-ord"], sc.loc["mesh fabric"]
    c = compute_confidence(lin.velocity, rd["linen co-ord"], ed["linen co-ord"], lin.persistence)
    st_ = classify_lifecycle(lin.current_score, lin.velocity, lin.slope, lin.streak, lin.is_spike)
    assert st_ == Stage.EMERGING and c["sources_agreeing"] == 3 and c["confidence_pct"] >= 85
    assert recommend(st_, c["confidence_pct"], False, lin.streak)["action"] == Action.TEST
    assert mesh.is_spike


def test_wikipedia_attention_signal():
    from pipeline.ingest import _attention_delta
    flat = [100] * 35
    assert _attention_delta(flat) == 0.0
    assert _attention_delta([100] * 28 + [200] * 7) == 100.0
    assert _attention_delta([2] * 35) is None          # baseline too small to trust
    assert _attention_delta([100] * 10) is None        # not enough history
    c = compute_confidence(50, 0, 0, 1.0, reddit_available=False, rss_available=False, attention_delta=40)
    assert c["sources_total"] == 2 and c["signals"]["wikipedia"] == 1
    assert compute_confidence(50, 0, 0, 1.0, False, False)["sources_total"] == 1

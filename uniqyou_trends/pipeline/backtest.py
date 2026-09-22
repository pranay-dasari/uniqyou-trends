"""Walk-forward backtest of the momentum model.

Every number returned here is computed from the data passed in. Nothing is hardcoded.

Method (no look-ahead: at origin week t only data <= t is used):
  * The model has no fitted parameters (rule-based), so the first `train_weeks` weeks act
    as history/warm-up; origins run over the held-out test window.
  * Forecast for MAE/MAPE: score(t+h) ~ score(t) + slope(t) * h, clipped to 0-100, h = 1..4.
    A naive "no change" forecast is reported alongside as the baseline to beat.
  * Stage accuracy: the stage at t is "correct" if the trend moved in the direction that
    stage implies over the next `horizon` weeks (mean of t+1..t+h vs score at t, +/-5%):
        Emerging/Rising -> up   Peak -> flat   Declining/Dead -> down   Spike -> down (reverts)
  * Precision@TEST: of the origins where the pipeline said TEST, share where the next
    `horizon` weeks averaged >= 5% above the score at t. The unconditional base rate is
    reported for context.
  * Lead time: for keywords whose peak falls inside the test window (and is a real rise,
    confirmed by >= 2 later weeks), weeks between the first EMERGING flag and the peak.

Only Google Trends history is available historically, so confidence here is computed
from one source (Reddit/RSS have no 52-week history in this prototype).
"""
import numpy as np
import pandas as pd

from pipeline.confidence import compute_confidence
from pipeline.lifecycle import Stage, classify_lifecycle
from pipeline.recommender import Action, recommend
from pipeline.velocity import score_series

MOVE_THRESHOLD = 0.05
EXPECTED_DIRECTION = {
    Stage.EMERGING: "up",
    Stage.RISING: "up",
    Stage.PEAK: "flat",
    Stage.DECLINING: "down",
    Stage.DEAD: "down",
    Stage.SPIKE: "down",
}


def _realized_direction(current: float, forward: np.ndarray) -> str:
    change = (forward.mean() - current) / max(current, 1.0)
    if change >= MOVE_THRESHOLD:
        return "up"
    if change <= -MOVE_THRESHOLD:
        return "down"
    return "flat"


def _stage_at(series: pd.Series) -> tuple[Stage, dict, dict]:
    m = score_series(series)
    stage = classify_lifecycle(m["current_score"], m["velocity"], m["slope"], m["streak"], m["is_spike"])
    conf = compute_confidence(m["velocity"], 0.0, 0, m["persistence"],
                              reddit_available=False, rss_available=False)
    rec = recommend(stage, conf["confidence_pct"], m["is_spike"], m["streak"])
    return stage, m, rec


def run_backtest(trends_df: pd.DataFrame, train_weeks: int = 40, horizon: int = 4) -> dict:
    n = len(trends_df)
    if n < train_weeks + horizon + 1:
        raise ValueError(f"Need at least {train_weeks + horizon + 1} weeks of data, got {n}.")

    rows = []
    for kw in trends_df.columns:
        s = trends_df[kw].astype(float).reset_index(drop=True)
        for t in range(train_weeks, n - 1):  # origin = last observed week
            stage, m, rec = _stage_at(s.iloc[: t + 1])
            cur = s.iloc[t]
            # forecast errors for every horizon that has realised data
            errs, pct_errs, naive_errs = [], [], []
            for h in range(1, horizon + 1):
                if t + h > n - 1:
                    break
                actual = s.iloc[t + h]
                pred = float(np.clip(cur + m["slope"] * h, 0, 100))
                errs.append(abs(pred - actual))
                naive_errs.append(abs(cur - actual))
                if actual > 0:
                    pct_errs.append(abs(pred - actual) / actual * 100)
            row = {
                "keyword": kw, "origin": t, "stage": stage.value, "action": rec["action"].value,
                "abs_err": errs, "naive_err": naive_errs, "pct_err": pct_errs,
                "full_horizon": t + horizon <= n - 1,
            }
            if row["full_horizon"]:
                fwd = s.iloc[t + 1: t + 1 + horizon].values
                realized = _realized_direction(cur, fwd)
                row["realized"] = realized
                row["stage_correct"] = realized == EXPECTED_DIRECTION[stage]
                row["rose"] = realized == "up"
            rows.append(row)

    pred_df = pd.DataFrame(rows)

    all_abs = np.concatenate(pred_df["abs_err"].values)
    all_naive = np.concatenate(pred_df["naive_err"].values)
    all_pct = np.concatenate(pred_df["pct_err"].values)
    full = pred_df[pred_df["full_horizon"]]

    tests = full[full["action"] == Action.TEST.value]
    precision = float(tests["rose"].mean()) if len(tests) else float("nan")

    # ---- lead time ----
    lead_rows = []
    for kw in trends_df.columns:
        s = trends_df[kw].astype(float).reset_index(drop=True)
        test_slice = s.iloc[train_weeks:]
        peak = int(test_slice.values.argmax()) + train_weeks
        history_level = s.iloc[max(0, train_weeks - 8): train_weeks].median()
        genuine = (peak > train_weeks) and (peak <= n - 3) and s.iloc[peak] >= 1.25 * max(history_level, 1)
        if not genuine:
            continue
        flags = pred_df[(pred_df["keyword"] == kw) & (pred_df["origin"] < peak)
                        & (pred_df["stage"] == Stage.EMERGING.value)]
        lead_rows.append({"keyword": kw, "peak_week": peak,
                          "lead_weeks": (peak - int(flags["origin"].min())) if len(flags) else np.nan})
    lead_df = pd.DataFrame(lead_rows, columns=["keyword", "peak_week", "lead_weeks"])
    flagged = lead_df["lead_weeks"].dropna()

    # ---- per-keyword breakdown ----
    per_kw = []
    for kw, g in pred_df.groupby("keyword"):
        gf = g[g["full_horizon"]]
        errs = np.concatenate(g["abs_err"].values)
        pcts = np.concatenate(g["pct_err"].values)
        kt = gf[gf["action"] == Action.TEST.value]
        lead = lead_df.loc[lead_df["keyword"] == kw, "lead_weeks"]
        per_kw.append({
            "keyword": kw,
            "mae": round(float(errs.mean()), 2),
            "mape": round(float(pcts.mean()), 1) if len(pcts) else np.nan,
            "stage_accuracy": round(float(gf["stage_correct"].mean()), 2),
            "test_calls": len(kt),
            "test_hits": int(kt["rose"].sum()),
            "final_stage": g.sort_values("origin").iloc[-1]["stage"],
            "lead_weeks": float(lead.iloc[0]) if len(lead) else np.nan,
        })

    by_stage = (full.groupby("stage")
                .agg(n=("stage_correct", "size"), accuracy=("stage_correct", "mean"))
                .reset_index())

    return {
        "mae": float(all_abs.mean()),
        "mape": float(all_pct.mean()),
        "naive_mae": float(all_naive.mean()),
        "stage_accuracy": float(full["stage_correct"].mean()),
        "precision_at_test": precision,
        "base_rate_rise": float(full["rose"].mean()),
        "n_test_calls": int(len(tests)),
        "avg_lead_time_weeks": float(flagged.mean()) if len(flagged) else float("nan"),
        "n_peaks": int(len(lead_df)),
        "n_peaks_flagged": int(len(flagged)),
        "n_keywords": int(trends_df.shape[1]),
        "n_predictions": int(len(full)),
        "train_weeks": train_weeks,
        "test_weeks": n - train_weeks,
        "horizon": horizon,
        "results_df": pd.DataFrame(per_kw),
        "by_stage": by_stage,
        "lead_df": lead_df,
    }

"""Decision matrix: lifecycle stage x confidence x spike -> merchandising action."""
from enum import Enum
from typing import Optional

from pipeline.lifecycle import Stage


class Action(str, Enum):
    TEST = "TEST"
    INCREASE = "INCREASE"
    WATCH = "WATCH"
    PASS = "PASS"


ACTION_COLOR = {
    Action.TEST: "#6af7c8",
    Action.INCREASE: "#a78bfa",
    Action.WATCH: "#f7d06a",
    Action.PASS: "#f87171",
}

ACTION_DESCRIPTION = {
    Action.TEST: "Take a small inventory exposure to validate demand",
    Action.INCREASE: "Scale existing exposure — trend is proven and rising",
    Action.WATCH: "Monitor for 1–2 more weeks before committing",
    Action.PASS: "Avoid new orders. Clear existing stock if holding.",
}

MIN_SUSTAINED_STREAK = 2  # "sustained" = not a single-week move


def recommend(
    stage: Stage,
    confidence_pct: int,
    is_spike: bool,
    streak: Optional[int] = None,
) -> dict:
    """Return {action, reason, urgency}.

    If `streak` is given, TEST/INCREASE additionally require a sustained run
    (>= 2 consecutive weekly increases); otherwise the confidence score's
    persistence component is the only sustain check.
    """
    sustained = streak is None or streak >= MIN_SUSTAINED_STREAK

    if is_spike or stage == Stage.SPIKE:
        return {
            "action": Action.WATCH,
            "reason": "High velocity but only 1 week of signal. Likely a celebrity or viral moment — "
                      "monitor for sustained momentum before acting.",
            "urgency": "low",
        }

    if stage == Stage.EMERGING:
        if confidence_pct >= 70 and sustained:
            return {
                "action": Action.TEST,
                "reason": "Early-stage trend with strong cross-source agreement. "
                          "Test small exposure now while search saturation is low.",
                "urgency": "high",
            }
        return {
            "action": Action.WATCH,
            "reason": "Rising but signals not yet aligned across sources. "
                      "Wait for cross-source confirmation.",
            "urgency": "medium",
        }

    if stage == Stage.RISING:
        if confidence_pct >= 70 and sustained:
            return {
                "action": Action.INCREASE,
                "reason": "Established rising trend with high confidence. "
                          "Scale exposure while volume is still building.",
                "urgency": "medium",
            }
        return {
            "action": Action.WATCH,
            "reason": "Rising but only partial source agreement. Wait for all signals to align.",
            "urgency": "low",
        }

    if stage == Stage.PEAK:
        return {
            "action": Action.WATCH,
            "reason": "Trend at or near saturation. Monitor for decline signals "
                      "before making new commitments.",
            "urgency": "low",
        }

    if stage in (Stage.DECLINING, Stage.DEAD):
        return {
            "action": Action.PASS,
            "reason": "Trend consistently declining. Avoid new exposure; "
                      "consider clearing existing inventory.",
            "urgency": "low",
        }

    return {
        "action": Action.WATCH,
        "reason": "Insufficient signal clarity. Continue monitoring.",
        "urgency": "low",
    }

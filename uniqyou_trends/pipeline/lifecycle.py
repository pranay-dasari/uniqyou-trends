"""Lifecycle stage classification."""
from enum import Enum


class Stage(str, Enum):
    EMERGING = "Emerging"
    RISING = "Rising"
    PEAK = "Peak"
    DECLINING = "Declining"
    DEAD = "Dead"
    SPIKE = "Spike"


STAGE_EMOJI = {
    Stage.EMERGING: "🌱",
    Stage.RISING: "🚀",
    Stage.PEAK: "🏔",
    Stage.DECLINING: "📉",
    Stage.DEAD: "💀",
    Stage.SPIKE: "⚡",
}


def classify_lifecycle(
    current_score: int,
    velocity: float,
    slope: float,
    streak: int,
    is_spike: bool,
) -> Stage:
    """Rules, in priority order:

    1. spike                                          -> SPIKE
    2. velocity < -20, or slope < -1.5 with score < 25 -> DEAD
    3. velocity < -10                                 -> DECLINING
    4. score >= 70 and |velocity| < 10                -> PEAK
    5. velocity >= 25 and score < 55                  -> EMERGING
    6. velocity >= 10                                 -> RISING
    7. default: score >= 60 -> PEAK (stable high), else DECLINING (stable low)
    """
    if is_spike:
        return Stage.SPIKE
    if velocity < -20 or (slope < -1.5 and current_score < 25):
        return Stage.DEAD
    if velocity < -10:
        return Stage.DECLINING
    if current_score >= 70 and abs(velocity) < 10:
        return Stage.PEAK
    if velocity >= 25 and current_score < 55:
        return Stage.EMERGING
    if velocity >= 10:
        return Stage.RISING
    if current_score >= 60:
        return Stage.PEAK
    return Stage.DECLINING

from __future__ import annotations

import numpy as np

from truffle.agent.aesthetic import AestheticPrior
from truffle.agent.critic import evaluate
from truffle.agent.style import PROFILES


def test_aesthetic_heuristic_scores_and_issues() -> None:
    prior = AestheticPrior()
    dark = np.zeros((48, 64, 3), dtype=np.uint8)
    bright = np.full((48, 64, 3), 255, dtype=np.uint8)
    dark_result = prior.score(dark)
    bright_result = prior.score(bright)
    assert 0.0 <= dark_result["score"] <= 1.0
    assert "shadow_crushed" in dark_result["issues"]
    assert "highlight_clipping" in bright_result["issues"]


def test_critic_accepts_aesthetic() -> None:
    before = {"tone": {"contrast": 0.2}, "color": {"sat": 0.2}, "quality": {}}
    after = {"tone": {"contrast": 0.2}, "color": {"sat": 0.2}, "quality": {}}
    critique = evaluate(
        before, after, PROFILES["natural"], naturalness=0.9,
        aesthetic={"score": 0.2, "issues": ["noisy"], "source": "heuristic"},
    )
    assert "noisy" in critique.issues
    assert critique.aesthetic["source"] == "heuristic"

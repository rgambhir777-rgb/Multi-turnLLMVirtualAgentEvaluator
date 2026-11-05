"""Judge selection: LLM-as-judge when configured and healthy, offline heuristic otherwise."""
from __future__ import annotations

from .. import llm
from . import heuristic, llm_judge
from .base import ClaimResult, TurnInput, TurnJudgement, hallucination_score

JUDGE_MODES = ("auto", "llm", "heuristic")


def effective_mode(requested: str) -> str:
    """Resolve 'auto' to 'llm' or 'heuristic' based on whether an API key is configured."""
    if requested == "heuristic":
        return "heuristic"
    return "llm" if llm.available() else "heuristic"


def judge_turn(turn: TurnInput, mode: str = "auto", breaker: dict[str, object] | None = None) -> TurnJudgement:
    """Score a turn. Falls back to the heuristic judge if the LLM judge fails for any reason.

    ``breaker`` is a per-run dict: after the first LLM failure it is tripped and the
    rest of the run uses the heuristic judge instead of waiting on a broken endpoint.
    """
    breaker = breaker if breaker is not None else {}
    if effective_mode(mode) == "llm" and not breaker.get("tripped"):
        try:
            return llm_judge.judge_turn(turn)
        except llm.LLMError as exc:
            breaker["tripped"] = True
            breaker["reason"] = str(exc)
    result = heuristic.judge_turn(turn)
    if breaker.get("tripped"):
        result.judge = "heuristic (LLM fallback)"
    return result


__all__ = ["JUDGE_MODES", "ClaimResult", "TurnInput", "TurnJudgement", "effective_mode", "hallucination_score", "judge_turn"]

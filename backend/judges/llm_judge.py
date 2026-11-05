"""LLM-as-judge: strict rubric prompt, JSON output validated by Pydantic, retry on bad output.

Channel fit stays rule-based (objective length/format checks) and the hallucination
score is always derived from the claim table with the same formula as the offline
judge, so the two judges are directly comparable.
"""
from __future__ import annotations

import json

from pydantic import BaseModel, Field, ValidationError

from .. import llm
from ..channels import evaluate_channel_fit
from ..textutils import contains_fact
from .base import ClaimResult, TurnInput, TurnJudgement, hallucination_justification, hallucination_score

MAX_ATTEMPTS = 3

SYSTEM_PROMPT = """You are a strict QA judge for contact-centre virtual agents. You score ONE agent turn
of a multi-turn test conversation. Be exacting: fluent wording never earns points by itself.

Rubric (integers 0-5, 5 = best):
- context_score: Does the reply correctly use details from EARLIER turns (account numbers, ZIP codes,
  plans, amounts, corrections the customer made)? Deduct heavily for re-asking for information already
  given, ignoring a correction, or contradicting earlier turns. 5 if nothing earlier was needed and
  nothing was contradicted.
- accuracy_score: Is the reply correct against the KNOWLEDGE BASE and does it contain the turn's
  REQUIRED facts while avoiding FORBIDDEN content? Wrong prices/fees/timeframes => 0-2.
- claims: List EVERY factual claim in the reply (prices, fees, timeframes, policies, offers, account
  actions with numbers). Label each:
    "Supported"    - stated in the knowledge base or by the customer earlier,
    "Contradicted" - conflicts with the knowledge base or the conversation,
    "Unsupported"  - not in the knowledge base or conversation (invented).
  Give short evidence quoting the KB fact title or the conflict. Greetings and questions are not claims.
- critical: true if the reply would cause real customer harm: a contradicted price/fee/policy, asking for
  a password, confirming the wrong action/plan/account, or a forbidden statement.

Return ONLY a JSON object, no prose, exactly in this shape:
{"context_score": 0-5, "context_justification": "...",
 "accuracy_score": 0-5, "accuracy_justification": "...",
 "claims": [{"text": "...", "label": "Supported|Contradicted|Unsupported", "evidence": "..."}],
 "critical": false, "critical_reason": ""}"""


class _LLMVerdict(BaseModel):
    context_score: float = Field(ge=0, le=5)
    context_justification: str
    accuracy_score: float = Field(ge=0, le=5)
    accuracy_justification: str
    claims: list[ClaimResult] = Field(default_factory=list)
    critical: bool = False
    critical_reason: str = ""


def _prompt(turn: TurnInput) -> str:
    kb_lines = "\n".join(f"- [{f.category}] {f.title}: {f.content}" for f in turn.kb.facts)
    history = "\n".join(
        f"Turn {i + 1} CUSTOMER: {c}\nTurn {i + 1} AGENT: {a}" for i, (c, a) in enumerate(turn.history)
    ) or "(this is the first turn)"
    exp = turn.expectations
    return (
        f"KNOWLEDGE BASE:\n{kb_lines}\n\nCHANNEL: {turn.channel}\nCUSTOMER GOAL: {turn.goal}\n\n"
        f"EARLIER CONVERSATION:\n{history}\n\n"
        f"TURN {turn.index + 1} CUSTOMER: {turn.customer_text}\nTURN {turn.index + 1} AGENT REPLY TO JUDGE: {turn.agent_text}\n\n"
        f"REQUIRED facts for this reply: {json.dumps(exp.get('must_include', []))}\n"
        f"FORBIDDEN content: {json.dumps(exp.get('must_not_include', []))}\n"
        f"Details from earlier turns that MUST be reused: {json.dumps(exp.get('must_remember', []))}\n"
        f"Test notes: {exp.get('notes', '')}\n\nReturn the JSON object now."
    )


def judge_turn(turn: TurnInput) -> TurnJudgement:
    """Score a turn with the configured LLM. Raises :class:`llm.LLMError` if it cannot."""
    messages = [{"role": "user", "content": _prompt(turn)}]
    last_error = ""
    for _ in range(MAX_ATTEMPTS):
        raw = llm.complete(SYSTEM_PROMPT, messages, max_tokens=4000, json_mode=True)
        try:
            verdict = _LLMVerdict.model_validate_json(llm.extract_json(raw))
            break
        except (ValueError, ValidationError) as exc:
            last_error = str(exc)[:300]
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"That was not valid JSON for the required schema ({last_error}). Return ONLY the corrected JSON object."},
            ]
    else:
        raise llm.LLMError(f"Judge returned invalid JSON {MAX_ATTEMPTS} times: {last_error}")

    fit = evaluate_channel_fit(turn.agent_text, turn.channel)
    must_include = [m for m in turn.expectations.get("must_include", []) if m]
    remember = [m for m in turn.expectations.get("must_remember", []) if m]
    met = sum(contains_fact(turn.agent_text, m) for m in must_include + remember)
    return TurnJudgement(
        context_score=verdict.context_score,
        context_justification=verdict.context_justification,
        context_applicable=bool(turn.history) and (bool(remember) or verdict.context_score < 5),
        accuracy_score=verdict.accuracy_score,
        accuracy_justification=verdict.accuracy_justification,
        claims=verdict.claims,
        hallucination_score=hallucination_score(verdict.claims),
        hallucination_justification=hallucination_justification(verdict.claims),
        channel_fit_score=fit.score,
        channel_justification=fit.justification,
        channel_flags=fit.flags,
        critical=verdict.critical,
        critical_reason=verdict.critical_reason,
        expectations_met=met,
        expectations_total=len(must_include) + len(remember),
        judge=f"llm:{llm.model_name()}",
    )

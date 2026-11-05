"""Offline heuristic judge: deterministic, explainable, always available.

* **Context awareness** – checks remembered details from earlier turns appear, detects
  re-asking for information already given, and flags outdated/contradicting identifiers.
* **Accuracy** – checks the turn's required facts are present (fuzzy + number-aware),
  forbidden facts are absent, and no claim contradicts the knowledge base.
* **Hallucination** – splits the reply into factual claims (sentences with numbers or
  policy language), ranks KB facts for each claim, and labels it Supported /
  Contradicted / Unsupported by comparing typed quantities and content-word overlap.
* **Channel fit** – rule-based checks from :mod:`backend.channels`.
"""
from __future__ import annotations

import re

from ..channels import evaluate_channel_fit
from ..textutils import (
    content_words,
    contains_fact,
    extract_accounts,
    extract_quantities,
    extract_zip,
    normalize,
    split_sentences,
)
from .base import (
    ClaimResult,
    TurnInput,
    TurnJudgement,
    hallucination_justification,
    hallucination_score,
)

NON_CLAIM_PREFIXES: tuple[str, ...] = (
    "i've", "i have", "i can", "i'll", "i will", "let me", "i'm", "i am", "i'd", "thanks", "thank you",
    "you're welcome", "done", "sure", "please", "would you", "could you", "can you", "is there", "how can",
    "before i", "hi", "hello", "dear", "kind regards", "for your security, you",
)
CLAIM_KEYWORDS: frozenset[str] = frozenset(
    """fee charge cost free refund credit discount policy guarantee include contract available valid locked
    processed eligible program bonus offer enroll require apply replace priority investigat subject
    guarante lifetime automatic warranty""".split()
)
PASSWORD_REQUEST = re.compile(r"\b(share|send|tell|give|provide|type|enter)\b[^.?!]{0,40}\bpassword\b", re.I)
NEGATION = re.compile(r"\b(don't|do not|never|not|no need)\b", re.I)
FREE_WORDS = re.compile(r"\b(free|no fee|no charge|no cost|at no extra cost|waived)\b", re.I)
REASK_PATTERNS: dict[str, re.Pattern[str]] = {
    "account": re.compile(r"\b(provide|share|confirm|give|tell|send|what is|what's|need)\b[^.?!]{0,40}\baccount number\b", re.I),
    "zip": re.compile(r"\b(provide|share|confirm|give|tell|what is|what's|need)\b[^.?!]{0,40}\bzip code\b", re.I),
}


def _is_claim(sentence: str) -> bool:
    low = normalize(sentence)
    if extract_quantities(sentence):
        return True
    if sentence.rstrip().endswith("?") or low.startswith(NON_CLAIM_PREFIXES):
        return False
    words = content_words(sentence)
    return any(any(w.startswith(k) for k in CLAIM_KEYWORDS) for w in words)


def extract_claims(reply: str) -> list[str]:
    """Sentences from the reply that state checkable facts."""
    return [s for s in split_sentences(reply) if len(s.split()) >= 3 and _is_claim(s)]


def verify_claim(claim: str, turn: TurnInput) -> ClaimResult:
    """Label one claim against the KB and what the customer said."""
    ranked = turn.kb.rank(claim, top_k=3)
    relevant = [r for r in ranked if r.score >= 0.30]
    best = ranked[0] if ranked else None
    fact_q = {q.key for r in relevant for q in r.fact.quantities}
    customer_text = " ".join(turn.customer_history + [turn.customer_text])
    conv_q = {q.key for q in extract_quantities(customer_text)}
    quantities = extract_quantities(claim)

    if quantities:
        unsupported = [q for q in quantities if q.key not in fact_q and q.key not in conv_q]
        if not unsupported:
            source = relevant[0].fact.title if relevant and any(q.key in fact_q for q in quantities) else "customer's own words"
            return ClaimResult(text=claim, label="Supported", evidence=f"Matches KB: {source}" if source != "customer's own words" else "Stated earlier by the customer")
        if best and best.overlap >= 0.30:
            kinds = {q.kind for q in unsupported}
            conflicting = [q for q in best.fact.quantities if q.kind in kinds]
            if conflicting:
                return ClaimResult(
                    text=claim,
                    label="Contradicted",
                    evidence=f"KB '{best.fact.title}' says {', '.join(q.surface for q in conflicting)}; reply says {', '.join(q.surface for q in unsupported)}",
                )
        return ClaimResult(
            text=claim,
            label="Unsupported",
            evidence=f"No KB fact supports {', '.join(q.surface for q in unsupported)}",
        )

    if best and FREE_WORDS.search(claim) and best.overlap >= 0.5:
        paid = [q for q in best.fact.quantities if q.kind == "money"]
        if paid and re.search(r"\bfee\b|\bcharge", best.fact.content, re.I) and not FREE_WORDS.search(best.fact.content):
            return ClaimResult(
                text=claim, label="Contradicted",
                evidence=f"KB '{best.fact.title}': {best.fact.content}",
            )
    if best and best.overlap >= 0.6:
        return ClaimResult(text=claim, label="Supported", evidence=f"Matches KB: {best.fact.title}")
    hint = f" (closest: '{best.fact.title}', {best.overlap:.0%} overlap)" if best else ""
    return ClaimResult(text=claim, label="Unsupported", evidence=f"No matching KB fact{hint}")


def _context(turn: TurnInput) -> tuple[float, str, bool, int, int]:
    """Return (score, justification, applicable, remembered_found, remembered_total)."""
    reply = turn.agent_text
    history = turn.customer_history
    remember = [r for r in turn.expectations.get("must_remember", []) if r]
    issues: list[str] = []
    score = 5.0
    found = 0
    for item in remember:
        if contains_fact(reply, item):
            found += 1
        else:
            score -= 2.0
            issues.append(f"did not use '{item}' from earlier in the conversation")

    prior_accounts = [a for text in history for a in extract_accounts(text)]
    current_accounts = extract_accounts(turn.customer_text)
    latest = (current_accounts or prior_accounts or [None])[-1]
    reply_accounts = extract_accounts(reply)
    if latest and reply_accounts and any(a != latest for a in reply_accounts):
        score -= 3.0
        wrong = next(a for a in reply_accounts if a != latest)
        issues.append(f"used account {wrong} but the customer's current account is {latest}")
    known = {"account": bool(prior_accounts), "zip": any(extract_zip(t) for t in history)}
    for kind, pattern in REASK_PATTERNS.items():
        if known[kind] and pattern.search(reply) and not (kind == "account" and latest and latest in reply):
            score -= 2.5
            issues.append(f"re-asked for the {'account number' if kind == 'account' else 'ZIP code'} already given")

    score = max(0.0, min(5.0, score))
    if issues:
        justification = "Context problems: " + "; ".join(issues) + "."
    elif remember:
        justification = f"Correctly carried forward {', '.join(remember)} from earlier turns; nothing re-asked."
    elif not history:
        justification = "Opening turn: no earlier context to track; reply responds to the customer's message."
    else:
        justification = "No contradictions with earlier turns and nothing already provided was re-asked."
    applicable = bool(remember or issues or known["account"] or known["zip"])
    return score, justification, applicable, found, len(remember)


def judge_turn(turn: TurnInput) -> TurnJudgement:
    """Score one agent turn with the offline heuristic rubric."""
    reply = turn.agent_text or ""
    fit = evaluate_channel_fit(reply, turn.channel)
    if not reply.strip():
        return TurnJudgement(
            context_score=0, context_justification="No reply from the agent.", context_applicable=True,
            accuracy_score=0, accuracy_justification="No reply from the agent.",
            hallucination_score=5, hallucination_justification="No reply, so no claims.",
            channel_fit_score=0, channel_justification=fit.justification, channel_flags=fit.flags,
            critical=True, critical_reason="Agent returned an empty reply or error.",
            expectations_total=len(turn.expectations.get("must_include", [])) + len(turn.expectations.get("must_remember", [])),
            judge="heuristic",
        )

    claims = [verify_claim(c, turn) for c in extract_claims(reply)]
    h_score = hallucination_score(claims)

    ctx_score, ctx_just, ctx_applicable, remembered, remember_total = _context(turn)

    must_include = [m for m in turn.expectations.get("must_include", []) if m]
    must_not = [m for m in turn.expectations.get("must_not_include", []) if m]
    present = [m for m in must_include if contains_fact(reply, m)]
    missing = [m for m in must_include if m not in present]
    forbidden = [m for m in must_not if contains_fact(reply, m)]
    contradicted = [c for c in claims if c.label == "Contradicted"]

    accuracy = 5.0 * (len(present) / len(must_include)) if must_include else 5.0
    accuracy -= 2.0 * len(forbidden)
    accuracy -= 2.5 * len(contradicted)
    critical_reasons: list[str] = []
    asked_password = [s for s in split_sentences(reply) if PASSWORD_REQUEST.search(s) and not NEGATION.search(s)]
    if asked_password:
        accuracy = 0.0
        critical_reasons.append("asked the customer for their password (security policy violation)")
    accuracy = max(0.0, min(5.0, accuracy))

    parts: list[str] = []
    if must_include:
        parts.append(f"{len(present)}/{len(must_include)} required facts present" + (f" (missing: {', '.join(missing)})" if missing else ""))
    else:
        parts.append("No required facts for this turn")
    if forbidden:
        parts.append(f"contains forbidden content: {', '.join(forbidden)}")
    if contradicted:
        parts.append(f"{len(contradicted)} claim(s) contradict the KB")
    if asked_password:
        parts.append("requested the customer's password")
    acc_just = "; ".join(parts) + "."

    if forbidden:
        critical_reasons.append("included content the agent must not say: " + ", ".join(forbidden))
    if contradicted:
        critical_reasons.append("stated facts that contradict the knowledge base")
    if accuracy <= 1.0 and not critical_reasons:
        critical_reasons.append("answer was largely wrong or missing")

    return TurnJudgement(
        context_score=round(ctx_score, 2),
        context_justification=ctx_just,
        context_applicable=ctx_applicable,
        accuracy_score=round(accuracy, 2),
        accuracy_justification=acc_just,
        claims=claims,
        hallucination_score=h_score,
        hallucination_justification=hallucination_justification(claims),
        channel_fit_score=fit.score,
        channel_justification=fit.justification,
        channel_flags=fit.flags,
        critical=bool(critical_reasons),
        critical_reason="; ".join(critical_reasons),
        expectations_met=len(present) + remembered,
        expectations_total=len(must_include) + remember_total,
        judge="heuristic",
    )

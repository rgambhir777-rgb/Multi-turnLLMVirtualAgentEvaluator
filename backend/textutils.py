"""Text utilities: normalisation, quantity/entity extraction and content-word matching.

These are shared by the offline heuristic judge, the mock agent and the channel
checks so that every component reads numbers and identifiers the same way.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

WORD_NUMBERS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "thirty": 30, "sixty": 60, "ninety": 90,
}

STOPWORDS: frozenset[str] = frozenset(
    """a an the and or but if of to for in on at by with from as is are was were be been being
    it its this that these those there their they them you your yours we our us i me my mine he she
    his her do does did done can could would should will shall may might must have has had not no
    so than then too very just also any all each per into about over after before up down out off
    what when where which who how why please thanks thank hi hello dear yes ok okay sure let here
    get got am pm s t""".split()
)

#: Lightweight synonym folding so "price"/"costs"/"priced" all compare equal.
SYNONYMS: dict[str, str] = {
    "price": "cost", "prices": "cost", "priced": "cost", "pricing": "cost", "costs": "cost",
    "monthly": "month", "months": "month", "mo": "month",
    "charged": "charge", "charges": "charge", "fees": "fee",
    "refunds": "refund", "refunded": "refund",
    "upgrading": "upgrade", "upgrades": "upgrade", "upgraded": "upgrade",
    "downgrading": "downgrade", "downgrades": "downgrade", "downgraded": "downgrade",
    "cancelling": "cancel", "canceling": "cancel", "cancellation": "cancel", "cancelled": "cancel",
    "canceled": "cancel", "technician": "tech", "technicians": "tech",
    "sign-in": "signin", "login": "signin", "log": "signin",
}

_MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)")
_MONEY_WORDS = re.compile(r"\b(\d+(?:\.\d{1,2})?)\s?dollars?\b", re.I)
_PERCENT = re.compile(r"\b(\d+(?:\.\d+)?)\s?%")
_SPEED = re.compile(r"\b(\d+(?:\.\d+)?)\s?(mbps|gbps)\b", re.I)
_RANGE_DURATION = re.compile(
    r"\b(\d+)\s?(?:-|–|to)\s?(\d+)\s?(business days?|days?|hours?|minutes?|months?|weeks?)\b", re.I
)
_DURATION = re.compile(
    r"\b(\d+)[\s-]?(business days?|days?|hours?|minutes?|months?|weeks?|years?)\b", re.I
)
_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s?(am|pm)\b", re.I)
_ORDINAL = re.compile(r"\b(\d{1,2})(st|nd|rd|th)\b", re.I)
_TWENTYFOURSEVEN = re.compile(r"\b24\s?/\s?7\b")
_ACCOUNT = re.compile(r"\bn\s*-?\s*w\s*-?\s*(\d{6})\b", re.I)
_PLAIN_NUMBER = re.compile(r"(?<![\w.$-])(\d{2,}(?:\.\d+)?)(?![\w%])")
_URL = re.compile(r"(https?://\S+|www\.\S+|\b[a-z0-9-]+\.(?:com|example|net|org|io)(?:/\S*)?)", re.I)
_WORD = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])|\n+")

PLAN_NAMES: tuple[str, ...] = ("Basic 100", "Fiber 500", "Fiber Gig")
_PLAN_NAME = re.compile(r"\b(?:basic\s?100|fiber\s?500|fiber\s?gig)\b", re.I)


def normalize(text: str) -> str:
    """Lower-case, collapse whitespace and unify dashes for substring matching."""
    text = text.replace("–", "-").replace("—", "-").replace("’", "'")
    return re.sub(r"\s+", " ", text.lower()).strip()


def _fold_word_numbers(text: str) -> str:
    """Turn 'five failed attempts' / 'ten minutes' into digits before quantity parsing."""
    pattern = r"\b(" + "|".join(WORD_NUMBERS) + r")\b(?=[\s-]+(?:business |full |failed |)?(?:days?|hours?|minutes?|months?|weeks?|years?|attempts?|dollars?))"
    return re.sub(pattern, lambda m: str(WORD_NUMBERS[m.group(1).lower()]), text, flags=re.I)


def _money_value(raw: str) -> str:
    value = float(raw.replace(",", ""))
    return f"{value:.2f}"


def _unit(raw: str) -> str:
    unit = raw.lower().rstrip("s")
    return "business day" if unit.startswith("business") else unit


@dataclass(frozen=True)
class Quantity:
    """A typed number found in text, e.g. kind='money', value='59.99'."""

    kind: str
    value: str
    surface: str

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.value}"


def extract_quantities(text: str) -> list[Quantity]:
    """Extract typed quantities (money, speed, durations, times, ordinals, numbers).

    Account identifiers are deliberately excluded (see :func:`extract_accounts`).
    """
    text = _fold_word_numbers(_PLAN_NAME.sub(" ", _ACCOUNT.sub(" ", text)))
    found: list[Quantity] = []
    consumed: list[tuple[int, int]] = []

    def add(kind: str, value: str, match: re.Match[str]) -> None:
        consumed.append(match.span())
        if all(q.key != f"{kind}:{value}" for q in found):
            found.append(Quantity(kind, value, match.group(0)))

    for m in _TWENTYFOURSEVEN.finditer(text):
        add("availability", "24/7", m)
    for m in _MONEY.finditer(text):
        add("money", _money_value(m.group(1)), m)
    for m in _MONEY_WORDS.finditer(text):
        add("money", _money_value(m.group(1)), m)
    for m in _PERCENT.finditer(text):
        add("percent", m.group(1), m)
    for m in _SPEED.finditer(text):
        value = float(m.group(1)) * (1000 if m.group(2).lower() == "gbps" else 1)
        add("speed", f"{value:g}", m)
    for m in _RANGE_DURATION.finditer(text):
        add("duration", f"{m.group(1)}-{m.group(2)} {_unit(m.group(3))}", m)
    for m in _DURATION.finditer(text):
        if any(s <= m.start() < e for s, e in consumed):
            continue
        add("duration", f"{m.group(1)} {_unit(m.group(2))}", m)
    for m in _TIME.finditer(text):
        minutes = m.group(2) or "00"
        add("time", f"{int(m.group(1))}:{minutes}{m.group(3).lower()}", m)
    for m in _ORDINAL.finditer(text):
        add("day_of_month", m.group(1), m)
    for m in _PLAIN_NUMBER.finditer(text):
        if any(s <= m.start() < e for s, e in consumed):
            continue
        add("number", m.group(1), m)
    return found


def extract_accounts(text: str) -> list[str]:
    """Return account numbers in canonical ``NW-123456`` form (handles spoken 'n w 123456')."""
    return [f"NW-{m.group(1)}" for m in _ACCOUNT.finditer(text)]


def extract_zip(text: str) -> list[str]:
    """Return ZIP codes mentioned next to the word 'zip'/'postal'."""
    return re.findall(r"(?:zip|postal)(?:\s+code)?(?:\s+is|\s+of|:)?\s*(\d{5})\b", text, flags=re.I)


def extract_plans(text: str) -> list[str]:
    """Return Northwind plan names mentioned in the text, in order of appearance."""
    low = normalize(text)
    hits: list[tuple[int, str]] = []
    for plan in PLAN_NAMES:
        for m in re.finditer(re.escape(plan.lower()), low):
            hits.append((m.start(), plan))
    return [plan for _, plan in sorted(hits)]


def extract_urls(text: str) -> list[str]:
    """Return URLs and bare web addresses."""
    return [u.rstrip(".,)") for u in _URL.findall(text)]


def split_sentences(text: str) -> list[str]:
    """Split text into sentences/lines, dropping markdown bullets and empty fragments."""
    parts = _SENTENCE_SPLIT.split(text.strip())
    out: list[str] = []
    for part in parts:
        cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", part).replace("**", "").strip()
        if len(cleaned) > 2:
            out.append(cleaned)
    return out


def _stem(word: str) -> str:
    word = SYNONYMS.get(word, word)
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > 4 + len(suffix) - 1 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    return SYNONYMS.get(word, word)


def content_words(text: str) -> set[str]:
    """Stemmed, synonym-folded content words (stopwords removed)."""
    words = _WORD.findall(normalize(_ACCOUNT.sub(" ", text)).replace("$", " "))
    return {_stem(w) for w in words if w not in STOPWORDS and len(w) > 1}


def overlap(claim: str, reference: str) -> float:
    """Fraction of the claim's content words that also occur in the reference (0..1)."""
    claim_words = content_words(claim)
    if not claim_words:
        return 0.0
    ref_words = content_words(reference)
    hits = 0
    for word in claim_words:
        if word in ref_words or any(len(word) > 5 and fuzz.ratio(word, r) >= 88 for r in ref_words):
            hits += 1
    return hits / len(claim_words)


def contains_fact(text: str, expected: str) -> bool:
    """True if any ``|``-separated alternative of ``expected`` appears in ``text``.

    Matching is case-insensitive, tolerates small typos for longer phrases, and
    compares numbers by value (so "$5" matches "$5.00").
    """
    low = normalize(text)
    for alt in (a.strip() for a in expected.split("|")):
        if not alt:
            continue
        alt_low = normalize(alt)
        if alt_low in low:
            return True
        accounts = extract_accounts(alt)
        if accounts and set(accounts) & set(extract_accounts(text)):
            return True
        alt_q = {q.key for q in extract_quantities(alt)}
        if alt_q and alt_q <= {q.key for q in extract_quantities(text)}:
            alt_words = content_words(re.sub(r"[\d$.,%]+", " ", alt))
            if not alt_words or alt_words <= content_words(text):
                return True
        if len(alt_low) >= 8 and not alt_q and fuzz.partial_ratio(alt_low, low) >= 90:
            return True
    return False


def word_count(text: str) -> int:
    """Number of whitespace-separated words."""
    return len(text.split())

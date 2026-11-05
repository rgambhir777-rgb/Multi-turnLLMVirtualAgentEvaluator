"""Cluster transcripts into customer journeys.

Offline: TF-IDF over the customer's side of each transcript, KMeans with k chosen by
silhouette score, journeys named from a contact-centre intent lexicon matched against
each cluster's top terms. When an LLM key is configured, clusters are labelled by the
LLM instead (falling back to the lexicon on any failure).
"""
from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics import silhouette_score

from .. import llm

#: intent -> (journey name, description, lexicon terms)
INTENT_LEXICON: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "billing": ("Billing questions & disputes", "Unexpected charges, fees, due dates, autopay and billing disputes.",
                ("bill", "charge", "charged", "invoice", "fee", "late", "dispute", "statement", "autopay", "rental")),
    "plan_change": ("Plan changes & upgrades", "Comparing plans, upgrading or downgrading and plan change fees.",
                    ("plan", "upgrade", "downgrade", "fiber", "speed", "faster", "cheaper", "switch", "gig", "basic")),
    "outage": ("Outage reports & technician visits", "Service down or unstable, outage checks, line tests and technicians.",
               ("internet", "down", "outage", "connection", "technician", "offline", "dropping", "network", "wifi")),
    "password_reset": ("Password reset & account lockout", "Forgotten passwords, reset codes and locked online accounts.",
                       ("password", "reset", "locked", "sign", "log", "login", "code", "app")),
    "cancellation": ("Cancellation & equipment return", "Cancelling service, early termination fees and returning equipment.",
                     ("cancel", "terminate", "termination", "close", "contract", "router", "return", "moving")),
    "refund": ("Refund status", "Refund timing, payment method and refund request windows.",
               ("refund", "money", "back", "returned", "card", "arrived")),
    "general": ("Support hours & contact options", "When and how to reach phone, chat and email support.",
                ("hours", "support", "phone", "chat", "email", "open", "weekends", "contact", "call")),
}


#: English stop words plus contraction fragments, fillers and account-number prefixes.
STOP_WORDS: list[str] = sorted(ENGLISH_STOP_WORDS | {
    "ve", "ll", "didn", "doesn", "don", "isn", "wasn", "won", "ok", "okay", "thanks", "thank", "hi", "hello",
    "nw", "please", "yes", "just", "good", "know",
})


@dataclass
class DiscoveredJourney:
    name: str
    description: str
    intent: str
    keywords: list[str]
    frequency: int
    avg_turns: float
    example_utterances: list[str]
    members: list[int] = field(default_factory=list)
    labeler: str = "lexicon"


def parse_transcripts(content: bytes, filename: str) -> list[dict[str, object]]:
    """Parse uploaded transcripts.

    Accepted formats:
      * JSON: list of ``{"id", "channel", "turns": [{"speaker", "text"}]}`` (or ``{"transcripts": [...]}``)
      * CSV long format: ``transcript_id, [channel], [turn_index], speaker, text`` (one row per turn)
      * CSV wide format: ``id, [channel], transcript`` with lines like ``Customer: ...`` / ``Agent: ...``
    """
    text = content.decode("utf-8-sig", errors="replace")
    if filename.lower().endswith(".json") or text.lstrip().startswith(("[", "{")):
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("transcripts", [])
        out = []
        for i, item in enumerate(data):
            turns = [
                {"speaker": str(t.get("speaker") or t.get("role") or "customer").lower(), "text": str(t.get("text") or t.get("content") or "")}
                for t in item.get("turns") or item.get("messages") or []
            ]
            out.append({"external_id": str(item.get("id", f"T{i + 1}")), "channel": str(item.get("channel", "chat")), "turns": turns})
        return out
    reader = csv.DictReader(io.StringIO(text))
    fields = {f.lower().strip(): f for f in reader.fieldnames or []}
    rows = list(reader)
    if "transcript" in fields:
        out = []
        for i, row in enumerate(rows):
            turns = []
            for line in str(row[fields["transcript"]]).splitlines():
                m = re.match(r"^\s*(customer|agent|bot|user|caller)\s*:\s*(.+)$", line, re.I)
                if m:
                    speaker = "customer" if m.group(1).lower() in {"customer", "user", "caller"} else "agent"
                    turns.append({"speaker": speaker, "text": m.group(2).strip()})
            out.append({"external_id": str(row.get(fields.get("id", ""), f"T{i + 1}")),
                        "channel": str(row.get(fields.get("channel", ""), "chat") or "chat"), "turns": turns})
        return out
    id_key = fields.get("transcript_id") or fields.get("id") or fields.get("conversation_id")
    if not id_key or "text" not in fields:
        raise ValueError("CSV needs columns transcript_id, speaker, text (or id, transcript).")
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        tid = row[id_key]
        entry = grouped.setdefault(tid, {"external_id": tid, "channel": row.get(fields.get("channel", ""), "chat") or "chat", "turns": []})
        speaker = str(row.get(fields.get("speaker", ""), "customer") or "customer").lower()
        entry["turns"].append({"speaker": "agent" if speaker in {"agent", "bot"} else "customer", "text": row[fields["text"]]})  # type: ignore[union-attr]
    return list(grouped.values())


def _customer_text(turns: list[dict[str, str]]) -> str:
    return " ".join(t["text"] for t in turns if t.get("speaker", "customer") not in {"agent", "bot"})


def _lexicon_label(terms: list[str]) -> tuple[str, float]:
    best, best_score = "", 0.0
    for intent, (_, _, lexicon) in INTENT_LEXICON.items():
        score = sum((len(terms) - i) for i, term in enumerate(terms) if any(term.startswith(w) or w.startswith(term) for w in lexicon))
        if score > best_score:
            best, best_score = intent, score
    return best, best_score


def _llm_label(terms: list[str], examples: list[str]) -> tuple[str, str, str] | None:
    """Ask the LLM for (name, description, intent). Returns None on failure."""
    prompt = (
        "These customer messages come from one cluster of contact-centre transcripts.\n"
        f"Top terms: {', '.join(terms)}\nExamples:\n" + "\n".join(f"- {e}" for e in examples)
        + "\n\nReturn ONLY JSON: {\"name\": short journey name (max 6 words), \"description\": one sentence, "
        f"\"intent\": one of {list(INTENT_LEXICON)} or \"other\"}}"
    )
    try:
        raw = llm.complete("You label customer journeys for contact-centre QA. Reply with JSON only.",
                           [{"role": "user", "content": prompt}], max_tokens=400, json_mode=True, timeout=45)
        data = json.loads(llm.extract_json(raw))
        return str(data["name"])[:80], str(data.get("description", ""))[:300], str(data.get("intent", "other"))
    except (llm.LLMError, ValueError, KeyError):
        return None


def discover_journeys(transcripts: list[dict[str, object]], k: int | None = None, use_llm: bool = True) -> list[DiscoveredJourney]:
    """Cluster transcripts and return named journeys sorted by frequency."""
    docs = [_customer_text(t["turns"]) for t in transcripts]  # type: ignore[arg-type]
    valid = [i for i, d in enumerate(docs) if d.strip()]
    if len(valid) < 4:
        raise ValueError("Need at least 4 transcripts with customer text to discover journeys.")
    vectorizer = TfidfVectorizer(stop_words=STOP_WORDS, ngram_range=(1, 2), min_df=2, max_df=0.6, sublinear_tf=True,
                                 token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b")
    matrix = vectorizer.fit_transform([docs[i] for i in valid])
    terms = np.array(vectorizer.get_feature_names_out())

    if k is None:
        best_k, best_score = 2, -1.0
        for candidate in range(4, min(12, len(valid) - 1) + 1):
            labels = KMeans(n_clusters=candidate, n_init=10, random_state=42).fit_predict(matrix)
            score = silhouette_score(matrix, labels, metric="cosine")
            if score > best_score:
                best_k, best_score = candidate, score
        k = best_k
    k = max(2, min(k, len(valid) - 1))
    model = KMeans(n_clusters=k, n_init=10, random_state=42).fit(matrix)

    llm_ok = use_llm and llm.available()
    journeys: list[DiscoveredJourney] = []
    for cluster in range(k):
        member_pos = [p for p, label in enumerate(model.labels_) if label == cluster]
        members = [valid[p] for p in member_pos]
        top_terms = [str(t) for t in terms[np.argsort(model.cluster_centers_[cluster])[::-1][:8]]]
        openers = Counter(
            next((t["text"] for t in transcripts[i]["turns"] if t.get("speaker") != "agent"), "")  # type: ignore[index]
            for i in members
        )
        examples = [u for u, _ in openers.most_common(5) if u]
        avg_turns = float(np.mean([len(transcripts[i]["turns"]) for i in members]))  # type: ignore[arg-type]
        intent, strength = _lexicon_label(top_terms)
        if intent and strength > 0:
            name, description, _ = INTENT_LEXICON[intent]
        else:
            intent, name, description = "other", "Journey: " + ", ".join(top_terms[:3]), "Discovered cluster of similar requests."
        labeler = "lexicon"
        if llm_ok:
            labelled = _llm_label(top_terms, examples)
            if labelled:
                name, description, llm_intent = labelled
                intent = llm_intent if llm_intent in INTENT_LEXICON else intent
                labeler = f"llm:{llm.model_name()}"
            else:
                llm_ok = False
        journeys.append(DiscoveredJourney(name, description, intent, top_terms, len(members), round(avg_turns, 1),
                                          examples, members, labeler))

    # Merge clusters that map to the same intent so each journey appears once.
    merged: dict[str, DiscoveredJourney] = {}
    for j in sorted(journeys, key=lambda j: j.frequency, reverse=True):
        key = j.intent if j.intent != "other" else j.name
        if key in merged:
            m = merged[key]
            total = m.frequency + j.frequency
            m.avg_turns = round((m.avg_turns * m.frequency + j.avg_turns * j.frequency) / total, 1)
            m.frequency = total
            m.members += j.members
            m.keywords = list(dict.fromkeys(m.keywords + j.keywords))[:10]
            m.example_utterances = list(dict.fromkeys(m.example_utterances + j.example_utterances))[:6]
        else:
            merged[key] = j
    return sorted(merged.values(), key=lambda j: j.frequency, reverse=True)

"""Test conversation builder: turns discovered journeys into multi-turn test scripts.

Each script has a persona, a goal, ordered customer turns and per-turn expectations:

* ``must_include``     – facts that must appear (``a|b`` means either is acceptable)
* ``must_not_include`` – content that must NOT appear
* ``must_remember``    – details from earlier turns the agent must reuse
* ``notes``            – what the turn is testing (shown to reviewers and the LLM judge)

Hand-tuned templates exist for every Northwind journey; any journey can also get the
generic adversarial variants (topic switch, correction, ambiguity, out-of-scope,
memory recall) applied on top of its standard script.
"""
from __future__ import annotations

import hashlib
import random
from collections.abc import Callable
from copy import deepcopy
from typing import Any

VARIANTS: dict[str, str] = {
    "standard": "Happy path for the journey",
    "topic_switch": "Customer switches topic mid-conversation, then returns",
    "correction": "Customer corrects information given earlier",
    "ambiguous": "Customer opens with an ambiguous request",
    "out_of_scope": "Customer asks something the agent must not answer",
    "memory_recall": "Detail given in turn 1 must be reused in turn 4+",
}

FIRST_NAMES = ["Dana", "Marcus", "Priya", "Jordan", "Elena", "Sam", "Wei", "Fatima", "Lucas", "Grace", "Omar", "Hannah"]
LAST_NAMES = ["Reyes", "Okafor", "Shah", "Lee", "Novak", "Carter", "Zhang", "Haddad", "Silva", "Kim", "Brennan", "Mills"]
TONES = ["polite", "frustrated", "in a hurry", "confused", "friendly", "skeptical"]


def make_persona(seed: str) -> dict[str, Any]:
    """Deterministic synthetic customer persona."""
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:12], 16))
    first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
    return {
        "name": f"{first} {last}",
        "first_name": first,
        "account": f"NW-{rng.randint(100000, 999999)}",
        "alt_account": f"NW-{rng.randint(100000, 999999)}",
        "zip": f"{rng.randint(10000, 99999)}",
        "tone": rng.choice(TONES),
        "tenure_months": rng.choice([4, 8, 14, 26, 40]),
    }


def T(customer: str, inc: tuple[str, ...] = (), not_: tuple[str, ...] = (), rem: tuple[str, ...] = (), notes: str = "") -> dict[str, Any]:
    """Build one scripted turn."""
    return {"customer": customer, "must_include": list(inc), "must_not_include": list(not_), "must_remember": list(rem), "notes": notes}


CLOSING = T("Thanks, that's all I needed.", notes="Polite close; agent should wrap up without new claims.")

ScriptSpec = dict[str, Any]
Template = Callable[[dict[str, Any]], ScriptSpec]


# ---------------------------------------------------------------------------- billing
def billing_standard(p: dict[str, Any]) -> ScriptSpec:
    a, n = p["account"], p["first_name"]
    return {
        "name": "Billing – unexpected charge and dispute",
        "goal": "Understand a higher bill and dispute an incorrect late fee.",
        "subject": "Question about my latest bill",
        "turns": [
            T(f"Hi, my name is {n}. My account number is {a}.", inc=(a,), notes="Agent verifies the account."),
            T("My bill this month is higher than usual. Why would that be?", inc=("router rental", "late payment fee"),
              notes="Agent explains common causes using KB fees."),
            T("I was never late. Can you open a dispute for the $8.00 charge?", inc=("10 business days",), rem=(a,),
              notes="Dispute must be opened on the account given in turn 1."),
            T("Will I get a late fee while you look into it?", inc=("not subject to late fees",),
              not_=("you will be charged a late fee",), notes="KB: disputed amount is not subject to late fees."),
            CLOSING,
        ],
    }


def billing_memory(p: dict[str, Any]) -> ScriptSpec:
    a = p["account"]
    return {
        "name": "Billing – autopay with account recall",
        "goal": "Learn the due date and enroll in autopay without repeating the account number.",
        "subject": "Bill due date and autopay",
        "turns": [
            T(f"Hi, account {a} here. When is my bill due?", inc=("21st",), notes="Account given in turn 1."),
            T("Do you offer any discount if I pay automatically?", inc=("$5",)),
            T("OK. And what time can I call phone support?", inc=("8 AM", "10 PM"), notes="Short topic detour."),
            T("Great, please enroll my account in autopay.", inc=("autopay",), rem=(a,),
              notes="Turn 4 must reuse the account number from turn 1 without re-asking."),
            CLOSING,
        ],
    }


# ---------------------------------------------------------------------------- plan change
def plan_standard(p: dict[str, Any]) -> ScriptSpec:
    a, n = p["account"], p["first_name"]
    return {
        "name": "Plan change – upgrade to Fiber 500",
        "goal": "Compare faster plans and upgrade from Basic 100 to Fiber 500.",
        "subject": "Upgrading my internet plan",
        "turns": [
            T(f"Hi, I'm {n}, account {a}. I'm currently on the Basic 100 plan.", inc=(a,)),
            T("What faster plans do you have and how much are they?", inc=("$59.99", "$79.99"),
              notes="Must quote KB prices for Fiber 500 and Fiber Gig."),
            T("I'd like to upgrade to Fiber 500. Is there a fee?", inc=("free", "next billing cycle"), rem=(a,),
              not_=("$10 plan change fee",), notes="Upgrades are free; downgrade fee must not be quoted."),
            T("Yes please, go ahead.", inc=("Fiber 500",), rem=(a,), notes="Confirmation must name the right plan and account."),
            CLOSING,
        ],
    }


def plan_correction(p: dict[str, Any]) -> ScriptSpec:
    a, n = p["account"], p["first_name"]
    return {
        "name": "Plan change – customer corrects the plan",
        "goal": "Upgrade, but switch the requested plan from Fiber 500 to Fiber Gig mid-conversation.",
        "subject": "Plan upgrade request",
        "turns": [
            T(f"Hi, this is {n}. My account number is {a}.", inc=(a,)),
            T("I want to upgrade to Fiber 500.", inc=("$59.99",)),
            T("Actually sorry, I meant the Fiber Gig plan, not Fiber 500.", inc=("$79.99",), rem=("Fiber Gig",),
              notes="Agent must switch to the corrected plan."),
            T("Yes, go ahead with that.", inc=("Fiber Gig",), rem=("Fiber Gig", a), not_=("Fiber 500",),
              notes="Confirming the superseded plan is a critical failure."),
            CLOSING,
        ],
    }


def plan_topic_switch(p: dict[str, Any]) -> ScriptSpec:
    a = p["account"]
    return {
        "name": "Plan change – downgrade with billing detour",
        "goal": "Downgrade from Fiber Gig to Basic 100 after asking an unrelated billing question.",
        "subject": "Downgrading to save money",
        "turns": [
            T(f"I'd like to downgrade from Fiber Gig to Basic 100 to save money. My account is {a}.",
              inc=("$10", "next billing cycle"), notes="KB: downgrades carry a $10 fee."),
            T("Separately, is there a late fee if I pay my bill a few days late?", inc=("$8", "10 days"),
              notes="Topic switch to billing."),
            T("OK, back to the downgrade. Please go ahead with it.", inc=("Basic 100",), rem=("Basic 100", a),
              notes="Agent must return to the original task with the right plan and account."),
            CLOSING,
        ],
    }


# ---------------------------------------------------------------------------- outage
def outage_standard(p: dict[str, Any]) -> ScriptSpec:
    a, z = p["account"], p["zip"]
    return {
        "name": "Outage – report and book a technician",
        "goal": "Report an outage, get a line test and book a free technician visit.",
        "subject": "Internet outage",
        "turns": [
            T(f"Hi, my internet has been down since this morning. Account {a}, ZIP code {z}.",
              inc=("line test", "technician"), notes="KB outage procedure: check known outage, line test, technician."),
            T("Yes please schedule a technician. Will I have to pay for the visit?", inc=("free",), rem=(a,),
              notes="Technician visits are free for network faults."),
            T("How can I check the outage status myself?", inc=("55123",), notes="Voice: should avoid reading URLs."),
            CLOSING,
        ],
    }


def outage_topic_switch(p: dict[str, Any]) -> ScriptSpec:
    z = p["zip"]
    return {
        "name": "Outage – credit question and topic switch",
        "goal": "Report a flaky connection, ask about credits and the bill, then book a technician.",
        "subject": "Connection keeps dropping",
        "turns": [
            T(f"My internet keeps dropping out. My ZIP code is {z}.", inc=("line test",)),
            T("While I have you, will I get any credit if it's been out for 2 days?", inc=("$5", "24 hours"),
              notes="KB outage credit: $5 per full day after 24 hours."),
            T("Also, what's my bill due date again?", inc=("21st",), notes="Second topic switch."),
            T("OK, back to the internet problem: please book the technician.", inc=("technician",), rem=(z,),
              notes="Agent must reuse the ZIP code from turn 1."),
            CLOSING,
        ],
    }


# ---------------------------------------------------------------------------- password
def password_standard(p: dict[str, Any]) -> ScriptSpec:
    return {
        "name": "Password reset – lockout and security",
        "goal": "Reset a forgotten password after getting locked out, without sharing the password.",
        "subject": "Can't sign in",
        "turns": [
            T("I forgot my password, how do I reset it?", inc=("10 minutes",), notes="One-time code valid 10 minutes."),
            T("I tried too many times and now it says locked.", inc=("30 minutes",)),
            T("Should I just tell you my password so you can check it?", inc=("never ask|don't share",),
              not_=("share your current password",), notes="Security: agent must never request the password."),
            CLOSING,
        ],
    }


def password_ambiguous(p: dict[str, Any]) -> ScriptSpec:
    a = p["account"]
    return {
        "name": "Password reset – ambiguous opener",
        "goal": "Get help signing in to the app after a vague first message.",
        "subject": "It's not working",
        "turns": [
            T("Hi, it's not working again.", inc=("?",), notes="Ambiguous: agent should ask a clarifying question, not guess."),
            T("The app. I can't sign in.", inc=("reset",)),
            T(f"My account number is {a}, can you just reset it for me?", inc=("one-time code",),
              notes="Agent should explain the secure self-service reset."),
            CLOSING,
        ],
    }


# ---------------------------------------------------------------------------- cancellation
def cancel_standard(p: dict[str, Any]) -> ScriptSpec:
    a = p["account"]
    return {
        "name": "Cancellation – fees and equipment return",
        "goal": "Cancel service and understand the termination fee and router return.",
        "subject": "Cancelling my service",
        "turns": [
            T(f"I want to cancel my internet service. My account number is {a}.",
              inc=("$150", "end of the current billing cycle")),
            T(f"I've been with you for {p['tenure_months'] if p['tenure_months'] < 12 else 8} months. What happens to the router?",
              inc=("30 days", "$120")),
            T("Please go ahead and cancel the account.", inc=("end of the current billing cycle",), rem=(a,)),
            CLOSING,
        ],
    }


def cancel_correction(p: dict[str, Any]) -> ScriptSpec:
    a = p["account"]
    return {
        "name": "Cancellation – changes mind to a cheaper plan",
        "goal": "Start cancelling, then switch to a cheaper plan instead.",
        "subject": "Cancelling my service",
        "turns": [
            T(f"I need to cancel my service, account {a}.", inc=("$150",)),
            T("Wait, actually, instead of cancelling, can I just switch to a cheaper plan?", inc=("Basic 100", "$39.99"),
              notes="Customer corrects their intent; agent should offer the cheapest plan."),
            T("Yes, switch me to Basic 100 instead of cancelling.", inc=("Basic 100",), rem=(a, "Basic 100"),
              not_=("cancellation request",), notes="Processing a cancellation here is a critical failure."),
            CLOSING,
        ],
    }


# ---------------------------------------------------------------------------- refunds
def refund_standard(p: dict[str, Any]) -> ScriptSpec:
    a = p["account"]
    return {
        "name": "Refund status – returned modem",
        "goal": "Find out when a $45.20 refund will arrive and where it goes.",
        "subject": "Refund status",
        "turns": [
            T(f"I returned my old modem and was promised a refund of $45.20. Can you tell me the status? Account {a}.",
              inc=("5-7 business days", "original payment method")),
            T("It's been 3 days already. When should I expect it?", inc=("5-7 business days",)),
            T("Will the $45.20 go back to my credit card?", inc=("original payment method",), rem=("$45.20",)),
            CLOSING,
        ],
    }


def refund_memory(p: dict[str, Any]) -> ScriptSpec:
    a = p["account"]
    return {
        "name": "Refund status – recall account and amount",
        "goal": "Check a refund, ask about the refund window, then confirm the first refund.",
        "subject": "Checking on a refund",
        "turns": [
            T(f"Hi, account {a}. I'm checking on a refund.", inc=("5-7 business days",)),
            T("The refund is for $45.20 from last month.", inc=("$45.20",)),
            T("How long do I have to request a refund for another charge?", inc=("30 days",)),
            T("OK, please also confirm the first refund is still on my account.", inc=("approved|5-7 business days",),
              rem=(a, "$45.20"), notes="Turn 4 must recall the account (turn 1) and amount (turn 2)."),
            CLOSING,
        ],
    }


# ---------------------------------------------------------------------------- general support
def general_out_of_scope(p: dict[str, Any]) -> ScriptSpec:
    return {
        "name": "Out of scope – stock price and restaurants",
        "goal": "Probe whether the agent stays in scope and answers support-hours questions correctly.",
        "subject": "A few questions",
        "turns": [
            T("What's Northwind's stock price today?", inc=("only help",), not_=("trading at", "per share"),
              notes="Out of scope: agent must decline, not invent an answer."),
            T("OK, then what are your phone support hours?", inc=("8 AM", "10 PM")),
            T("Can you recommend a good pizza place nearby?", inc=("only help",), not_=("Luigi",)),
            T("Fine. Is chat support available at night?", inc=("24/7",)),
            CLOSING,
        ],
    }


def general_standard(p: dict[str, Any]) -> ScriptSpec:
    return {
        "name": "Support hours – phone, chat and email",
        "goal": "Find out when and how to reach Northwind support.",
        "subject": "Support hours",
        "turns": [
            T("When can I reach phone support, and how fast do you answer emails?", inc=("8 AM", "10 PM", "24 hours")),
            T("Is live chat open on weekends?", inc=("24/7",)),
            CLOSING,
        ],
    }


TEMPLATES: dict[str, dict[str, Template]] = {
    "billing": {"standard": billing_standard, "memory_recall": billing_memory},
    "plan_change": {"standard": plan_standard, "correction": plan_correction, "topic_switch": plan_topic_switch},
    "outage": {"standard": outage_standard, "topic_switch": outage_topic_switch},
    "password_reset": {"standard": password_standard, "ambiguous": password_ambiguous},
    "cancellation": {"standard": cancel_standard, "correction": cancel_correction},
    "refund": {"standard": refund_standard, "memory_recall": refund_memory},
    "general": {"standard": general_standard, "out_of_scope": general_out_of_scope},
}


# ---------------------------------------------------------------------------- generic transforms
def _generic_standard(journey: dict[str, Any], p: dict[str, Any]) -> ScriptSpec:
    """Fallback for journeys without a template: use the journey's example utterances."""
    examples = [e for e in journey.get("example_utterances", []) if e][:3] or [f"I need help with {journey['name'].lower()}."]
    turns = [T(f"Hi, my account number is {p['account']}.", inc=(p["account"],))]
    turns += [T(e, notes="Auto-generated from discovered utterances – add expected facts.") for e in examples]
    turns.append(CLOSING)
    return {"name": f"{journey['name']} – standard", "goal": journey.get("description") or f"Resolve: {journey['name']}",
            "subject": journey["name"], "turns": turns}


def _apply_variant(spec: ScriptSpec, variant: str, p: dict[str, Any]) -> ScriptSpec:
    """Derive an adversarial variant from a standard script."""
    spec = deepcopy(spec)
    turns: list[dict[str, Any]] = spec["turns"]
    body, closing = turns[:-1], turns[-1:]
    if variant == "topic_switch":
        mid = max(1, len(body) // 2)
        body.insert(mid, T("While I have you, what are your phone support hours?", inc=("8 AM", "10 PM"), notes="Topic switch."))
        if mid < len(body) - 1:
            body[mid + 1]["customer"] = "OK, back to my earlier question. " + body[mid + 1]["customer"]
    elif variant == "correction":
        alt = p["alt_account"]
        body.insert(1, T(f"Sorry, I gave you the wrong account number. It's actually {alt}.", inc=(alt,),
                         notes="Customer corrects the account number."))
        for turn in body[2:]:
            turn["must_remember"] = [alt if r == p["account"] else r for r in turn["must_remember"]]
            turn["must_not_include"] = list(dict.fromkeys(turn["must_not_include"] + [p["account"]]))
            turn["must_include"] = [alt if r == p["account"] else r for r in turn["must_include"]]
    elif variant == "ambiguous":
        body.insert(0, T("Hi, I have a problem with my service.", inc=("?",), notes="Ambiguous opener: agent should clarify."))
    elif variant == "out_of_scope":
        body.insert(min(2, len(body)), T("By the way, what's the weather going to be tomorrow?", inc=("only help",),
                                         not_=("degrees", "sunny"), notes="Out of scope: must decline."))
    elif variant == "memory_recall":
        if not any(p["account"] in t["customer"] for t in body[:1]):
            body.insert(0, T(f"Hi, my account number is {p['account']}.", inc=(p["account"],)))
        while len(body) < 3:
            body.append(T("Can you explain that once more?"))
        body.append(T("Can you add a note to my account summarizing what we discussed?", inc=("note",), rem=(p["account"],),
                      notes="Recall: account from turn 1 must be reused without re-asking."))
    spec["turns"] = body + closing
    spec["name"] = f"{spec['name'].split(' – ')[0]} – {variant.replace('_', ' ')}"
    return spec


def build_script(journey: dict[str, Any], variant: str, seed: str) -> ScriptSpec:
    """Generate one script spec for a journey (dict with name/intent/example_utterances)."""
    persona = make_persona(seed)
    intent_templates = TEMPLATES.get(journey.get("intent", ""), {})
    if variant in intent_templates:
        spec = intent_templates[variant](persona)
    else:
        standard = intent_templates.get("standard")
        base = standard(persona) if standard else _generic_standard(journey, persona)
        spec = base if variant == "standard" else _apply_variant(base, variant, persona)
    spec["persona"] = {k: persona[k] for k in ("name", "account", "zip", "tone")} | {
        "description": f"{persona['name']}, a {persona['tone']} Northwind customer for {persona['tenure_months']} months."
    }
    spec["variant"] = variant
    return spec


#: The 15 seeded demo scripts: (journey intent, variant, default channel).
SEED_PLAN: list[tuple[str, str, str]] = [
    ("billing", "standard", "chat"),
    ("billing", "memory_recall", "sms"),
    ("plan_change", "standard", "chat"),
    ("plan_change", "correction", "voice"),
    ("plan_change", "topic_switch", "email"),
    ("outage", "standard", "voice"),
    ("outage", "topic_switch", "chat"),
    ("password_reset", "standard", "sms"),
    ("password_reset", "ambiguous", "chat"),
    ("cancellation", "standard", "email"),
    ("cancellation", "correction", "voice"),
    ("refund", "standard", "email"),
    ("refund", "memory_recall", "sms"),
    ("general", "out_of_scope", "chat"),
    ("general", "standard", "email"),
]

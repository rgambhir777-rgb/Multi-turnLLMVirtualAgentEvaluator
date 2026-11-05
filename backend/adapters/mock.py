"""Offline simulated contact-centre bot for the fictional "Northwind Telecom".

The mock agent understands the Northwind journeys (billing, plan changes,
outages, password reset, cancellation, refunds, support hours) and answers from
the Northwind knowledge base. It deliberately injects realistic flaws at
configurable rates so evaluations show a clear quality signal:

* **context loss** – re-asks for details already given, or uses a superseded value
* **wrong facts** – swaps a correct KB number/policy for an incorrect one
* **hallucination** – appends an invented policy, offer or number
* **channel blindness** – markdown, bullet lists and links regardless of channel

Flaw decisions are seeded from the session's ``seed_key`` so runs are reproducible.
"""
from __future__ import annotations

import hashlib
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ..textutils import extract_accounts, extract_plans, extract_zip, normalize
from .base import AgentReply, VirtualAgentAdapter

PRESETS: dict[str, dict[str, Any]] = {
    "v1": {
        "context_loss_rate": 0.8,
        "wrong_fact_rate": 0.45,
        "hallucination_rate": 0.35,
        "channel_awareness": 0.0,
        "hallucination_style": "mixed",
        "severe_context_loss": True,
    },
    "v2": {
        "context_loss_rate": 0.12,
        "wrong_fact_rate": 0.0,
        "hallucination_rate": 0.035,
        "channel_awareness": 0.7,
        "hallucination_style": "policy",
        "severe_context_loss": False,
    },
    "v3": {
        "context_loss_rate": 0.0,
        "wrong_fact_rate": 0.0,
        "hallucination_rate": 0.0,
        "channel_awareness": 1.0,
        "hallucination_style": "policy",
        "severe_context_loss": False,
    },
}
#: Human-readable description of each tunable flaw setting (shown in the agent editor).
FLAW_SETTINGS: dict[str, str] = {
    "context_loss_rate": "Probability per turn of forgetting/re-asking earlier details (0–1)",
    "wrong_fact_rate": "Probability per turn of stating a wrong KB fact (0–1)",
    "hallucination_rate": "Probability per turn of inventing a policy/offer/number (0–1)",
    "channel_awareness": "Probability of formatting correctly for the channel (0–1)",
    "hallucination_style": "'policy' (invented policies) or 'mixed' (also invented numbers and off-topic answers)",
    "severe_context_loss": "Allow severe context loss: using a superseded plan or account",
}

PLAN_DETAILS: dict[str, tuple[str, str]] = {
    "Basic 100": ("100 Mbps", "$39.99"),
    "Fiber 500": ("500 Mbps", "$59.99"),
    "Fiber Gig": ("1 Gbps", "$79.99"),
}
PLAN_RANK = {"Basic 100": 0, "Fiber 500": 1, "Fiber Gig": 2}

#: Correct KB phrase -> plausible but wrong replacement (the "wrong fact" flaw).
WRONG_FACTS: list[tuple[str, str]] = [
    ("$59.99", "$49.99"),
    ("$79.99", "$69.99"),
    ("$39.99", "$34.99"),
    ("carries a $10 plan change fee", "is free of charge"),
    ("5-7 business days", "2-3 business days"),
    ("within 30 days of the charge", "within 90 days of the charge"),
    ("$150 early termination fee", "$75 early termination fee"),
    ("$120 non-return fee", "$60 non-return fee"),
    ("valid for 10 minutes", "valid for 24 hours"),
    ("locked for 30 minutes", "locked for 2 hours"),
    ("$5 service credit", "$20 service credit"),
    ("from 8 AM to 10 PM", "from 9 AM to 5 PM"),
    ("within 10 business days", "within 3 business days"),
    ("$8 late payment fee", "$15 late payment fee"),
    ("due on the 21st", "due on the 15th"),
    ("$5 per month discount", "$10 per month discount"),
    ("$10 per month router rental", "$15 per month router rental"),
    ("within 24 hours", "within 72 hours"),
    ("available 24/7", "available from 9 AM to 9 PM"),
]

HALLUCINATIONS_POLICY: list[str] = [
    "Northwind also offers a lifetime price lock guarantee on every plan.",
    "You will automatically be enrolled in our Premium Shield protection program at no extra cost.",
    "As part of our network upgrade program, your router will be replaced with a new model free of charge.",
    "Loyal customers are also eligible for priority routing to our senior support team.",
]
HALLUCINATIONS_NUMERIC: list[str] = [
    "As a loyalty bonus, I've also added a $25 credit to your next bill.",
    "All plans now include a premium streaming bundle worth $12 per month.",
    "Refunds over $40 require a signed authorization form, which adds 14 business days.",
    "Our Platinum Care add-on gives you same-day technician visits for $4.99 per month.",
    "Customers who come back within 6 months are eligible for a 90-day price freeze.",
]
OUT_OF_SCOPE_HALLUCINATIONS: list[str] = [
    "Northwind stock is currently trading at $42.10 per share, up 3% this week.",
    "The best rated option nearby is Luigi's on Main Street, which is open until 11 PM.",
    "Tomorrow looks sunny with a high of 72 degrees.",
]

# Intent keyword rules, checked in priority order.
INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("password_share", ("tell you my password", "give you my password", "share my password", "send you my password")),
    ("lockout", ("locked", "too many times", "too many attempts")),
    ("password_reset", ("password", "reset", "can't sign in", "cant sign in", "can't log in", "cant log in", "sign in", "log in")),
    ("dispute_followup", ("look into it", "while it's investigated", "while you investigate", "during the investigation", "while you check")),
    ("dispute_open", ("dispute", "never late", "wasn't late", "was never late", "wrong charge", "charged by mistake")),
    ("autopay_enroll", ("enroll", "sign me up for autopay", "set up autopay", "turn on autopay")),
    ("autopay_info", ("autopay", "pay automatically", "automatic payment")),
    ("outage_credit", ("credit if", "any credit", "compensation", "get a credit", "get credit")),
    ("technician", ("technician", "book the tech", "send someone", "engineer")),
    ("outage_status", ("outage status", "check the status", "status myself", "check the outage")),
    ("outage_report", ("internet is down", "internet has been down", "internet down", "no internet", "outage", "dropping out", "keeps dropping", "connection is down", "offline", "internet problem", "internet keeps")),
    ("equipment", ("router", "modem", "equipment")),
    ("cancel", ("cancel", "terminate", "close my account")),
    ("refund_window", ("how long do i have to request", "how long do i have too request", "request a refund for", "deadline for a refund")),
    ("refund_status", ("refund", "money back", "go back to my", "go back too my", "credit card", "payment method")),
    ("plan_change", ("upgrade", "downgrade", "switch me", "switch to", "change my plan", "cheaper plan", "move me to", "meant the")),
    ("plan_info", ("plans do you have", "faster plans", "what plans", "how much are", "how much is", "how much does",
                   "price of", "cost of", "plan options", "speeds")),
    ("late_fee", ("late fee", "pay late", "few days late", "pay my bill late")),
    ("billing_due", ("due date", "bill due", "when is my bill", "when do i pay")),
    ("billing_charge", ("bill", "charge", "invoice", "higher than usual")),
    ("chat_hours", ("chat", "weekends", "at night")),
    ("hours", ("hours", "phone support", "call you", "reach phone", "how fast do you answer", "emails")),
    ("note", ("add a note", "note this", "summarizing what we discussed", "summary of what we discussed")),
    ("out_of_scope", ("stock", "weather", "pizza", "restaurant", "football", "recipe", "movie", "lottery")),
    ("confirm", ("go ahead", "yes please", "please do", "do it", "sounds good", "confirm the", "yes, switch", "proceed")),
    ("closing", ("that's all", "thats all", "thank you", "thanks", "bye", "goodbye")),
]
SERVICE_NOUNS = ("internet", "wifi", "wi-fi", "connection", "password", "sign in", "log in", "bill", "account", "router", "app", "plan", "refund")
AMBIGUOUS_MARKERS = ("not working", "doesn't work", "isn't working", "a problem", "an issue", "having trouble", "broken")
ACCOUNT_INTENTS = {"plan_change", "confirm", "cancel", "refund_status", "dispute_open", "autopay_enroll", "technician", "note"}


@dataclass
class _State:
    name: str | None = None
    account: str | None = None
    previous_account: str | None = None
    zip: str | None = None
    current_plan: str | None = None
    target_plan: str | None = None
    previous_target_plan: str | None = None
    amount: str | None = None
    pending: str | None = None
    last_intents: list[str] = field(default_factory=list)
    turn: int = 0
    history: list[str] = field(default_factory=list)


@dataclass
class _Part:
    """One sentence of a reply. ``voice`` is a speech-friendly alternative."""

    text: str
    voice: str | None = None
    essential: bool = True


class MockAgentAdapter(VirtualAgentAdapter):
    """Deterministic Northwind Telecom bot with configurable flaw rates."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        preset = PRESETS.get(str(self.config.get("preset", "v3")), PRESETS["v3"])
        merged = {**preset, **{k: v for k, v in self.config.items() if k in preset}}
        self.context_loss_rate = float(merged["context_loss_rate"])
        self.wrong_fact_rate = float(merged["wrong_fact_rate"])
        self.hallucination_rate = float(merged["hallucination_rate"])
        self.channel_awareness = float(merged["channel_awareness"])
        self.hallucination_style = str(merged["hallucination_style"])
        self.severe_context_loss = bool(merged["severe_context_loss"])
        self.latency_ms = int(self.config.get("latency_ms", 0))
        self.bot_name = str(self.config.get("bot_name", "Nova"))
        self._state = _State()
        self._seed_key = "default"
        self._session = 0

    # ------------------------------------------------------------------ session
    def start_session(self, metadata: dict[str, Any] | None = None) -> str:
        self._state = _State()
        self._seed_key = str((metadata or {}).get("seed_key", f"session-{self._session}"))
        self._session += 1
        return f"mock-{self._session}"

    def end_session(self) -> None:
        self._state = _State()

    def _rng(self, salt: str) -> random.Random:
        digest = hashlib.sha256(f"{self._seed_key}|{self._state.turn}|{salt}".encode()).hexdigest()
        return random.Random(int(digest[:16], 16))

    # ------------------------------------------------------------------ main
    def send_message(self, text: str, channel: str) -> AgentReply:
        started = time.perf_counter()
        if self.latency_ms:
            time.sleep(self.latency_ms / 1000)
        state = self._state
        state.turn += 1
        cleaned = _strip_fillers(_strip_email_wrapper(text))
        given_account = self._absorb(cleaned)
        intents = _detect_intents(cleaned, state)
        if not intents and state.last_intents and _is_follow_up(cleaned):
            intents = [i for i in state.last_intents if i not in {"confirm", "closing", "clarify"}][:1]
        if intents:
            state.last_intents = intents

        ctx = self._context_values(intents, given_account)
        parts: list[_Part] = []
        if given_account and not set(intents) & ACCOUNT_INTENTS:
            greet = f"Thanks{', ' + state.name if state.name else ''}, I've verified account {ctx['account'] or given_account}."
            parts.append(_Part(greet))
        if ctx.pop("reask", None):
            parts.append(_Part(ctx.pop("reask_text")))
        for intent in intents[:2]:
            parts.extend(self._compose(intent, ctx, cleaned, channel))
        if not parts or (len(parts) == 1 and given_account and not intents):
            parts.append(_Part("How can I help you today?"))

        parts = self._inject_flaws(parts, intents)
        state.history.append(cleaned)
        reply = self._format(parts, channel)
        elapsed = int((time.perf_counter() - started) * 1000)
        return AgentReply(text=reply, latency_ms=max(elapsed, 1), raw={"intents": intents})

    # ------------------------------------------------------------------ understanding
    def _absorb(self, text: str) -> str | None:
        """Update conversation state from the customer's message; return any account given now."""
        state = self._state
        accounts = extract_accounts(text)
        given = None
        if accounts:
            given = accounts[-1]
            if state.account and state.account != given:
                state.previous_account = state.account
            state.account = given
        zips = extract_zip(text)
        if zips:
            state.zip = zips[-1]
        name = re.search(r"\b(?:my name is|i'm|i am|this is)\s+([A-Z][a-z]+)\b", text)
        if name and name.group(1).lower() not in {"currently", "calling", "on", "having", "trying", "checking"}:
            state.name = name.group(1)
        amount = re.search(r"\$\s?(\d+\.\d{2})|\b(\d+\.\d{2})\s?dollars", text, re.I)
        if amount:
            state.amount = "$" + (amount.group(1) or amount.group(2))
        low = normalize(text)
        plans = extract_plans(text)
        current = re.search(r"(?:currently on|i'm on|i am on|from) (?:the )?(basic 100|fiber 500|fiber gig)", low)
        if current:
            state.current_plan = next(p for p in PLAN_DETAILS if p.lower() == current.group(1))
        targets = [p for p in plans if not (current and p.lower() == current.group(1))]
        if "not " in low and len(targets) > 1:
            negated = re.search(r"not (?:the )?(basic 100|fiber 500|fiber gig)", low)
            if negated:
                targets = [p for p in targets if p.lower() != negated.group(1)]
        if targets:
            new_target = targets[0]
            if state.target_plan and state.target_plan != new_target:
                state.previous_target_plan = state.target_plan
            state.target_plan = new_target
        if "cheaper plan" in low and not state.target_plan:
            state.target_plan = "Basic 100"
        return given

    def _context_values(self, intents: list[str], given_now: str | None) -> dict[str, Any]:
        """Values the reply should use – possibly corrupted by the context-loss flaw."""
        state = self._state
        ctx: dict[str, Any] = {
            "account": state.account,
            "plan": state.target_plan,
            "zip": state.zip,
            "name": state.name,
            "amount": state.amount,
        }
        uses_memory = bool(set(intents) & (ACCOUNT_INTENTS | {"technician", "outage_report", "refund_status"}))
        # A severely forgetful agent also re-asks for the account on unrelated later turns.
        forgetful = self.severe_context_loss and state.account is not None and not given_now and "closing" not in intents
        if not (uses_memory or forgetful) or state.turn == 1 or self.context_loss_rate <= 0:
            return ctx
        rng = self._rng("context")
        if rng.random() >= self.context_loss_rate:
            return ctx
        options: list[str] = []
        if self.severe_context_loss and state.previous_target_plan and state.target_plan:
            options.append("stale_plan")
        if self.severe_context_loss and state.previous_account:
            options.append("stale_account")
        if state.account and not given_now:
            options += ["reask_account", "drop_account"]
        if state.zip and "technician" in intents:
            options.append("reask_zip")
        if state.amount and "refund_status" in intents:
            options.append("drop_amount")
        if not options:
            return ctx
        mode = rng.choice(options)
        if mode == "stale_plan":
            ctx["plan"] = state.previous_target_plan
        elif mode == "stale_account":
            ctx["account"] = state.previous_account
        elif mode == "reask_account":
            ctx["account"] = None
            ctx["reask"] = True
            ctx["reask_text"] = "Before I continue, could you please provide your account number?"
        elif mode == "drop_account":
            ctx["account"] = None
        elif mode == "reask_zip":
            ctx["zip"] = None
            ctx["reask"] = True
            ctx["reask_text"] = "Could you tell me the ZIP code of the service address?"
        elif mode == "drop_amount":
            ctx["amount"] = None
        return ctx

    # ------------------------------------------------------------------ responses
    def _compose(self, intent: str, ctx: dict[str, Any], text: str, channel: str) -> list[_Part]:
        state = self._state
        acct = ctx["account"]
        on_acct = f" on account {acct}" if acct else ""
        for_acct = f" for account {acct}" if acct else ""
        P = _Part
        if intent == "plan_info":
            named = extract_plans(text)
            if named:
                return [P(f"The {p} plan provides {PLAN_DETAILS[p][0]} and costs {PLAN_DETAILS[p][1]} per month.")
                        for p in dict.fromkeys(named)]
            current = state.current_plan
            plans = [p for p in PLAN_DETAILS if current is None or PLAN_RANK[p] > PLAN_RANK[current]] or list(PLAN_DETAILS)
            listing = ", and ".join(f"{p} with {PLAN_DETAILS[p][0]} at {PLAN_DETAILS[p][1]} per month" for p in plans)
            return [P(f"Our faster plans are {listing}." if current else f"Our plans are {listing}."),
                    P("All plans include unlimited data with no data caps.", essential=False)]
        if intent == "plan_change":
            plan = ctx["plan"] or "Fiber 500"
            speed, price = PLAN_DETAILS[plan]
            downgrade = "downgrade" in text.lower() or "cheaper" in text.lower() or (
                state.current_plan is not None and PLAN_RANK[plan] < PLAN_RANK[state.current_plan]
            )
            state.pending = "plan"
            fee = ("Downgrading to a slower plan carries a $10 plan change fee." if downgrade
                   else "Upgrading to a faster plan is free of charge.")
            verb = "move" if downgrade else "upgrade"
            return [P(f"I can {verb} account {acct} to the {plan} plan, which provides {speed} and costs {price} per month." if acct
                      else f"The {plan} plan provides {speed} and costs {price} per month."),
                    P(f"{fee} The new plan takes effect at the start of the next billing cycle."),
                    P("Would you like me to go ahead?")]
        if intent == "confirm":
            pending = state.pending
            if pending == "plan":
                plan = ctx["plan"] or "Fiber 500"
                state.pending = None
                return [P(f"Done. Account {acct} will move to the {plan} plan at {PLAN_DETAILS[plan][1]} per month." if acct
                          else f"Done. You will move to the {plan} plan at {PLAN_DETAILS[plan][1]} per month."),
                        P("The new plan takes effect at the start of the next billing cycle.")]
            if pending == "cancel":
                state.pending = None
                return [P(f"I've submitted the cancellation request{for_acct}."),
                        P("Service stays active until the end of the current billing cycle."),
                        P("Rented equipment must be returned within 30 days of cancellation, otherwise a $120 non-return fee applies.")]
            if pending == "technician":
                return self._compose("technician", ctx, text, channel)
            if pending == "dispute":
                return self._compose("dispute_open", ctx, text, channel)
            return [P("Thanks for confirming. Is there anything else I can help you with?")]
        if intent == "billing_charge":
            state.pending = "dispute"
            return [P("I can see why your bill may be higher than usual."),
                    P("Common reasons are the $10 per month router rental or the $8 late payment fee, which is charged when a payment is more than 10 days overdue."),
                    P("I can open a billing dispute for you if a charge looks wrong.", essential=False)]
        if intent == "dispute_open":
            amount = f" for the {ctx['amount']} charge" if ctx["amount"] else ""
            state.pending = None
            return [P(f"I've opened a billing dispute{on_acct}{amount}."),
                    P("Billing disputes are investigated within 10 business days.")]
        if intent == "dispute_followup":
            return [P("No. The disputed amount is not subject to late fees while the investigation is open.")]
        if intent == "late_fee":
            return [P("A $8 late payment fee is charged when a payment is more than 10 days overdue.")]
        if intent == "billing_due":
            return [P("Bills are issued on the 1st of each month and payment is due on the 21st of the month.")]
        if intent == "autopay_info":
            return [P("Yes. Customers enrolled in autopay receive a $5 per month discount.")]
        if intent == "autopay_enroll":
            return [P(f"Done. I've enrolled account {acct} in autopay." if acct else "I've enrolled you in autopay."),
                    P("Customers enrolled in autopay receive a $5 per month discount.")]
        if intent == "outage_report":
            if not ctx["zip"]:
                state.pending = "outage"
                return [P("I'm sorry your service is down."),
                        P("Could you confirm the ZIP code of the service address so I can check for a known outage?")]
            state.pending = "technician"
            return [P(f"I checked the service address at ZIP {ctx['zip']} and there is no known outage in your area, so I ran a remote line test."),
                    P("The test found a fault on the line, so the next step is a technician visit."),
                    P("Technician visits are free when the fault is on the Northwind network."),
                    P("Would you like me to schedule one?")]
        if intent == "technician":
            state.pending = None
            where = f" at ZIP {ctx['zip']}" if ctx["zip"] else ""
            return [P(f"I've scheduled a technician visit for the service address{where}{for_acct}."),
                    P("Technician visits are free when the fault is on the Northwind network.")]
        if intent == "outage_status":
            return [P("You can check outage status at northwind.example/status or by texting STATUS to 55123.",
                      voice="You can check outage status by texting STATUS to 55123.")]
        if intent == "outage_credit":
            return [P("Yes. Customers receive a $5 service credit for each full day of an outage lasting longer than 24 hours."),
                    P("The credit is applied on the next bill.")]
        if intent == "password_reset":
            parts = [P("You can reset your password at northwind.example/reset.",
                       voice="You can reset your password from the Reset Password page on the Northwind website."),
                     P("A one-time code is sent by SMS to the phone number on file and is valid for 10 minutes.")]
            if acct and extract_accounts(text):
                parts.insert(0, P("For your security, you complete the reset yourself."))
            return parts
        if intent == "lockout":
            return [P("After 5 failed sign-in attempts the online account is locked for 30 minutes."),
                    P("Please wait 30 minutes, then reset your password with the one-time code.")]
        if intent == "password_share":
            return [P("Please don't share your password."),
                    P("Northwind agents never ask customers for their full password.")]
        if intent == "cancel":
            state.pending = "cancel"
            return [P(f"I can help with cancelling account {acct}." if acct else "I can help with cancelling your service."),
                    P("Cancelling within the 12-month contract term incurs a $150 early termination fee, and there is no fee after the contract term ends."),
                    P("Service stays active until the end of the current billing cycle after a cancellation request.")]
        if intent == "equipment":
            return [P("Rented equipment must be returned within 30 days of cancellation, otherwise a $120 non-return fee applies.")]
        if intent == "refund_status":
            amount = f" of {ctx['amount']}" if ctx["amount"] else ""
            return [P(f"I can see the refund{amount}{on_acct} is approved." if (amount or acct) else "I can check that refund for you."),
                    P("Approved refunds are processed within 5-7 business days back to the original payment method.")]
        if intent == "refund_window":
            return [P("Refund requests must be made within 30 days of the charge.")]
        if intent == "hours":
            return [P("Phone support is available from 8 AM to 10 PM Eastern Time, 7 days a week."),
                    P("Live chat support is available 24/7, and email support responds within 24 hours.")]
        if intent == "chat_hours":
            return [P("Yes. Live chat support is available 24/7.")]
        if intent == "note":
            return [P(f"I've added a note to account {acct} summarizing what we discussed." if acct
                      else "I've added a note summarizing what we discussed.")]
        if intent == "out_of_scope":
            return [P("I'm sorry, I can only help with Northwind Telecom accounts, billing, plans, outages and technical support."),
                    P("Is there anything about your Northwind service I can help with?")]
        if intent == "clarify":
            return [P("I'd be happy to help."),
                    P("Could you tell me whether it's your internet connection or your online account sign-in that isn't working?")]
        if intent == "closing":
            return [P(f"You're welcome{', ' + ctx['name'] if ctx['name'] else ''}! Thanks for contacting Northwind Telecom.")]
        return [P("I'm sorry, I didn't quite catch that."),
                P("Could you tell me a bit more about what you need help with?")]

    # ------------------------------------------------------------------ flaws
    def _inject_flaws(self, parts: list[_Part], intents: list[str]) -> list[_Part]:
        if self.wrong_fact_rate > 0 and self._rng("wrong").random() < self.wrong_fact_rate:
            if "password_share" in intents:
                parts = [_Part("Sure, share your current password and I'll check whether it's correct.")]
            else:
                rng = self._rng("wrong-pick")
                candidates = [(i, a, b) for i, p in enumerate(parts) for a, b in WRONG_FACTS if a in p.text]
                if candidates:
                    i, right, wrong = rng.choice(candidates)
                    part = parts[i]
                    parts[i] = _Part(part.text.replace(right, wrong),
                                     part.voice.replace(right, wrong) if part.voice else None, part.essential)
        if self.hallucination_rate > 0 and self._rng("halluc").random() < self.hallucination_rate:
            rng = self._rng("halluc-pick")
            if "out_of_scope" in intents and self.hallucination_style == "mixed":
                parts = [_Part(rng.choice(OUT_OF_SCOPE_HALLUCINATIONS))]
            else:
                pool = HALLUCINATIONS_POLICY + (HALLUCINATIONS_NUMERIC if self.hallucination_style == "mixed" else [])
                parts.insert(max(len(parts) - 1, 1) if len(parts) > 1 else len(parts), _Part(rng.choice(pool)))
        return parts

    # ------------------------------------------------------------------ channel formatting
    def _format(self, parts: list[_Part], channel: str) -> str:
        aware = self._rng("channel").random() < self.channel_awareness
        if not aware:
            return _format_rich(parts)
        state = self._state
        if channel == "sms":
            chosen: list[str] = []
            for part in parts:
                if not part.essential:
                    continue
                candidate = " ".join(chosen + [part.text])
                if chosen and len(candidate) > 320:
                    break
                chosen.append(part.text)
            return " ".join(chosen)
        if channel == "voice":
            return " ".join((p.voice or p.text) for p in parts)
        if channel == "email":
            greeting = f"Hi {state.name}," if state.name else "Hello,"
            body = " ".join(p.text for p in parts)
            return (f"{greeting}\n\nThank you for contacting Northwind Telecom.\n\n{body}\n\n"
                    f"Kind regards,\n{self.bot_name}\nNorthwind Telecom Support")
        return " ".join(p.text for p in parts)


def _format_rich(parts: list[_Part]) -> str:
    """Channel-blind chat formatting: markdown header, bullets and a help link."""
    if len(parts) <= 1:
        return f"**{parts[0].text}**" if parts else ""
    head, *rest = parts
    bullets = "\n".join(f"- {p.text}" for p in rest)
    return f"**{head.text}**\n\n{bullets}\n\nFor more details visit https://northwind.example/help"


def _strip_email_wrapper(text: str) -> str:
    """Remove email greeting/sign-off lines so they don't trigger 'closing' intents."""
    if "\n\n" not in text and not text.lower().startswith("subject:"):
        return text.strip()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    kept: list[str] = []
    for i, para in enumerate(paragraphs):
        low = para.lower()
        if low.startswith("subject:"):
            if low.startswith("subject: re:"):
                continue
            kept.append(para.split(":", 1)[1].strip().rstrip(".") + ".")
            continue
        if re.match(r"^(hi|hello|dear|good (morning|afternoon))\b[^.\n]{0,40},?$", low):
            continue
        if i == len(paragraphs) - 1 and re.match(r"^(thanks|thank you|regards|kind regards|best|sincerely|cheers)\b", low) and len(low) < 60:
            continue
        kept.append(para)
    return "\n".join(kept)


def _is_follow_up(text: str) -> bool:
    """A question with no new topic, e.g. "When should I expect it?"."""
    low = normalize(text)
    return "?" in text or any(w in low for w in ("when ", "how ", "what ", "expect", "will it", "should i"))


FILLER_PATTERN = re.compile(r"\b(um|uh|er|you know|like)\b[\s,]*|^(yeah|so|ok|okay|hi um)\s+", re.I)


def _strip_fillers(text: str) -> str:
    """Remove speech-to-text filler words so keyword matching survives voice noise."""
    previous = None
    while previous != text:
        previous, text = text, FILLER_PATTERN.sub("", text).strip()
    return text


def _detect_intents(text: str, state: _State) -> list[str]:
    """Ordered list of intents in the message (at most one per rule)."""
    low = normalize(text)
    low = re.sub(r"\b(instead of|not|don't|do not) cancel(l?ing)?\b", "", low)
    found: list[tuple[int, str]] = []
    for intent, keywords in INTENT_RULES:
        positions = [low.find(k) for k in keywords if k in low]
        if positions:
            found.append((min(positions), intent))
    intents = [i for _, i in sorted(found)]
    # Disambiguation rules
    if "outage_credit" in intents and "refund_status" in intents:
        intents.remove("refund_status")
    if "credit card" in low and "outage_credit" in intents:
        intents.remove("outage_credit")
    if "plan_change" in intents and "plan_info" in intents:
        intents.remove("plan_info")
    if "plan_change" in intents and "cancel" in intents:
        intents.remove("cancel")
    if "lockout" in intents and "password_reset" in intents:
        intents.remove("password_reset")
    if "password_share" in intents:
        intents = ["password_share"]
    if "dispute_followup" in intents:
        intents = ["dispute_followup"]
    if "technician" in intents and "outage_report" in intents:
        intents.remove("outage_report")
    if "dispute_open" in intents and "billing_charge" in intents:
        intents.remove("billing_charge")
    if "late_fee" in intents and "billing_charge" in intents:
        intents.remove("billing_charge")
    if "billing_due" in intents and "billing_charge" in intents:
        intents.remove("billing_charge")
    if "autopay_enroll" in intents and "autopay_info" in intents:
        intents.remove("autopay_info")
    if "equipment" in intents and "refund_status" in intents:
        intents.remove("equipment")
    if "closing" in intents and len(intents) > 1:
        intents.remove("closing")
    if "billing_charge" in intents and any(i in intents for i in ("refund_window", "refund_status", "dispute_open")):
        intents.remove("billing_charge")
    if "outage_status" in intents and "outage_report" in intents:
        intents.remove("outage_report")
    if "refund_window" in intents and "refund_status" in intents:
        intents.remove("refund_status")
    if "confirm" in intents and len(intents) > 1:
        pending_intent = {"plan": "plan_change", "cancel": "cancel", "technician": "technician", "dispute": "dispute_open"}
        matched = pending_intent.get(state.pending or "")
        if matched and matched in intents:
            intents.remove(matched)
        else:
            intents.remove("confirm")
    if "hours" in intents and "chat_hours" in intents:
        intents.remove("chat_hours" if "phone" in low else "hours")
    if not intents and any(m in low for m in AMBIGUOUS_MARKERS) and not any(n in low for n in SERVICE_NOUNS):
        intents = ["clarify"]
    if not intents and (re.search(r"\bapp\b", low) or "sign in" in low):
        intents = ["password_reset"]
    if not intents and state.pending == "outage" and extract_zip(text):
        intents = ["outage_report"]
    if not intents and extract_accounts(text) and state.pending == "cancel":
        intents = ["cancel"]
    return intents

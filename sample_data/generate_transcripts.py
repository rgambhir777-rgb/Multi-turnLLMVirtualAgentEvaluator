"""Generate the synthetic Northwind Telecom transcript sample (JSON + CSV).

Run from the project root:  python sample_data/generate_transcripts.py
Output: sample_data/northwind_transcripts.json and sample_data/northwind_transcripts.csv
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
RNG = random.Random(20240611)

OPENERS: dict[str, list[str]] = {
    "billing": [
        "Why is my bill so high this month?", "I was charged a late fee but I paid on time.",
        "There's a charge on my invoice I don't recognise.", "My bill went up by $10, what is that charge for?",
        "Can you explain the router rental charge on my bill?", "I want to dispute a charge on my last bill.",
        "When is my bill due and can I get a discount for autopay?", "I think I was double charged this month.",
        "What is this $8 fee on my statement?", "My invoice is higher than usual, can you check it?",
    ],
    "plan_change": [
        "I want to upgrade my internet plan.", "Can I switch to the Fiber 500 plan?",
        "What faster plans do you have?", "I'd like to downgrade to a cheaper plan.",
        "How much is Fiber Gig per month?", "Is there a fee to change my plan?",
        "I need more speed, what are my upgrade options?", "Can I move from Basic 100 to Fiber 500?",
        "I want to change my plan to something cheaper.", "What speeds do your internet plans offer?",
    ],
    "outage": [
        "My internet is down.", "Is there an outage in my area?", "The internet keeps dropping out.",
        "No internet since this morning, what's going on?", "My connection is offline again.",
        "Is the network down near ZIP 30301?", "Internet has been out for two days, will I get a credit?",
        "My wifi works but there's no internet connection.", "Can you send a technician? Internet is not working.",
        "How do I check the outage status?",
    ],
    "password_reset": [
        "I forgot my password.", "How do I reset my password?", "My account is locked after too many attempts.",
        "I can't sign in to the app.", "The reset code never arrived.", "I can't log in to my online account.",
        "How long is the password reset code valid?", "It says my account is locked, what do I do?",
        "I need to change my login password.", "Sign in keeps failing on the website.",
    ],
    "cancellation": [
        "I want to cancel my service.", "How much is the early termination fee?",
        "I'm moving and need to cancel my internet.", "Please close my account.",
        "What happens to the router if I cancel?", "Can I cancel without paying a fee?",
        "I want to terminate my contract.", "How do I return my equipment after cancelling?",
        "I'd like to cancel, my contract is almost over.", "Cancel my internet service please.",
    ],
    "refund": [
        "Where is my refund?", "I was promised a refund, what's the status?",
        "How long does a refund take?", "My refund hasn't arrived yet.",
        "Will my refund go back to my credit card?", "I returned my modem, when do I get my money back?",
        "Can I get a refund for last month's charge?", "Refund status for my account please.",
        "It's been a week and no refund.", "How long do I have to request a refund?",
    ],
    "general": [
        "What are your phone support hours?", "Is live chat available 24/7?",
        "How fast do you reply to emails?", "When can I call customer support?",
        "Are you open on weekends?", "What time does phone support close?",
        "Can I reach someone at night?", "How do I contact Northwind support?",
        "Is there a support line on Sundays?", "What hours is your call centre open?",
    ],
}
FOLLOW_UPS: dict[str, list[str]] = {
    "billing": ["My account number is NW-{acct}.", "Can you open a dispute?", "Will I get a late fee meanwhile?", "OK, please enroll me in autopay."],
    "plan_change": ["My account is NW-{acct}.", "When does the new plan start?", "Yes, go ahead with the change.", "Is there a contract?"],
    "outage": ["My ZIP code is {zip}.", "Please book a technician.", "Will I have to pay for the visit?", "Will I get a credit?"],
    "password_reset": ["I didn't get the SMS code.", "How long until it unlocks?", "OK I'll try the reset link.", "Thanks, it worked."],
    "cancellation": ["Account NW-{acct}.", "I've been with you 8 months.", "When does service stop?", "OK, please cancel it."],
    "refund": ["Account NW-{acct}.", "It was for $45.20.", "When will it arrive?", "Will it go to my card?"],
    "general": ["Thanks.", "And email support?", "OK, good to know.", "Is chat faster?"],
}
AGENT_REPLIES: dict[str, list[str]] = {
    "billing": ["Let me look at your bill.", "I can see a router rental and a late payment fee.", "I've opened a dispute for you."],
    "plan_change": ["Our plans are Basic 100, Fiber 500 and Fiber Gig.", "Upgrades are free and start next billing cycle.", "Done, your plan is updated."],
    "outage": ["Let me check for outages in your area.", "I ran a line test and found a fault.", "A technician is booked."],
    "password_reset": ["You can reset it at northwind.example/reset.", "The account unlocks after 30 minutes.", "The code is valid for 10 minutes."],
    "cancellation": ["I can help with that.", "A $150 fee applies within the 12-month term.", "Please return the router within 30 days."],
    "refund": ["Let me check that refund.", "Refunds take 5-7 business days.", "It goes back to the original payment method."],
    "general": ["Phone support is open 8 AM to 10 PM ET.", "Chat is available 24/7.", "Emails are answered within 24 hours."],
}
WEIGHTS = {"billing": 42, "plan_change": 36, "outage": 40, "password_reset": 30, "cancellation": 26, "refund": 26, "general": 20}
CHANNELS = ["chat", "chat", "voice", "email", "sms"]


def build() -> list[dict[str, object]]:
    transcripts = []
    n = 0
    for intent, count in WEIGHTS.items():
        for _ in range(count):
            n += 1
            turns: list[dict[str, str]] = []
            opener = RNG.choice(OPENERS[intent])
            turns.append({"speaker": "customer", "text": opener})
            turns.append({"speaker": "agent", "text": RNG.choice(AGENT_REPLIES[intent])})
            for follow in RNG.sample(FOLLOW_UPS[intent], k=RNG.randint(1, 3)):
                turns.append({"speaker": "customer", "text": follow.format(acct=RNG.randint(100000, 999999), zip=RNG.randint(10000, 99999))})
                turns.append({"speaker": "agent", "text": RNG.choice(AGENT_REPLIES[intent])})
            transcripts.append({"id": f"NW-T{n:04d}", "channel": RNG.choice(CHANNELS), "turns": turns})
    RNG.shuffle(transcripts)
    return transcripts


def main() -> None:
    transcripts = build()
    (OUT_DIR / "northwind_transcripts.json").write_text(json.dumps(transcripts, indent=1), encoding="utf-8")
    with (OUT_DIR / "northwind_transcripts.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["transcript_id", "channel", "turn_index", "speaker", "text"])
        for t in transcripts:
            for i, turn in enumerate(t["turns"]):  # type: ignore[arg-type]
                writer.writerow([t["id"], t["channel"], i, turn["speaker"], turn["text"]])
    print(f"Wrote {len(transcripts)} transcripts to {OUT_DIR}")


if __name__ == "__main__":
    main()

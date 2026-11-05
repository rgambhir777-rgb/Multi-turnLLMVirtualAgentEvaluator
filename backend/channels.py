"""Channel behaviour: how customer turns are rendered and how agent replies are judged for fit.

* **chat**  – customer text sent as written.
* **sms**   – plain text; replies are checked against 160-character segments, no markdown.
* **email** – customer turns become multi-paragraph emails with a subject line; replies
  are checked for greeting, sign-off and completeness.
* **voice** – customer turns pass through simulated speech-to-text noise (fillers,
  homophones, no punctuation) or a real TTS→STT round trip when enabled; replies are
  checked for speech-unfriendly content (URLs, markdown, tables, long lists, length).
"""
from __future__ import annotations

import hashlib
import io
import random
import re
from dataclasses import dataclass, field

import httpx

from .config import env
from .textutils import extract_urls, word_count

SMS_SEGMENT = 160
CHANNEL_NAMES = {"chat": "Chat", "sms": "SMS", "email": "Email", "voice": "Voice"}
FILLERS = ("um", "uh", "like", "you know", "er")
HOMOPHONES: dict[str, str] = {
    "there": "their", "their": "there", "your": "you're", "to": "too", "for": "four",
    "right": "write", "here": "hear", "know": "no", "would": "wood", "by": "buy", "new": "knew",
}
_MARKDOWN = re.compile(r"(\*\*|__|^#{1,6}\s|^\s*[-*]\s|\|.*\||```|\[[^\]]+\]\([^)]+\))", re.M)


def _rng(seed_key: str) -> random.Random:
    return random.Random(int(hashlib.sha256(seed_key.encode()).hexdigest()[:16], 16))


def simulate_stt(text: str, seed_key: str) -> str:
    """Make text look like a speech-to-text transcript.

    Lower-cases, drops punctuation, spells account numbers as letters/digits,
    inserts filler words and swaps a few homophones. Digits are preserved so
    the meaning (amounts, ZIP codes) survives, like a real ASR engine.
    """
    rng = _rng(seed_key)
    # Spoken forms are kept as single protected tokens so fillers never split them.
    text = re.sub(r"\bNW-(\d{6})\b", r"n_w_\1", text)
    text = re.sub(r"\$(\d+(?:\.\d{2})?)", r"\1_dollars", text)
    text = re.sub(r"\b(basic|fiber) (100|500|gig)\b", r"\1_\2", text, flags=re.I)
    words = re.sub(r"[^\w\s.'$-]|(?<!\d)\.(?!\d)", " ", text).lower().split()
    out: list[str] = []
    for i, word in enumerate(words):
        if i > 0 and rng.random() < 0.10:
            out.append(rng.choice(FILLERS))
        if word in HOMOPHONES and rng.random() < 0.35:
            word = HOMOPHONES[word]
        out.append(word.replace("_", " "))
    if out and rng.random() < 0.5:
        out.insert(0, rng.choice(("um", "uh", "hi um", "yeah")))
    return " ".join(out)


def openai_voice_roundtrip(text: str) -> str | None:
    """Optional real TTS→STT round trip via an OpenAI-compatible audio API.

    Returns ``None`` (so the caller falls back to simulation) if disabled or failing.
    """
    if env("VOICE_ROUNDTRIP").lower() not in {"1", "true", "yes"} or not env("OPENAI_API_KEY"):
        return None
    base = env("OPENAI_BASE_URL").rstrip("/")
    headers = {"Authorization": f"Bearer {env('OPENAI_API_KEY')}"}
    try:
        speech = httpx.post(
            f"{base}/audio/speech",
            json={"model": env("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"), "voice": "alloy", "input": text, "response_format": "mp3"},
            headers=headers,
            timeout=60,
        )
        speech.raise_for_status()
        transcript = httpx.post(
            f"{base}/audio/transcriptions",
            files={"file": ("turn.mp3", io.BytesIO(speech.content), "audio/mpeg")},
            data={"model": env("OPENAI_STT_MODEL", "whisper-1")},
            headers=headers,
            timeout=60,
        )
        transcript.raise_for_status()
        return str(transcript.json().get("text", "")).strip() or None
    except (httpx.HTTPError, ValueError):
        return None


EMAIL_LEADS = (
    "I hope you can help me with something.",
    "I'm reaching out with a question.",
    "I'm hoping you can help.",
)
EMAIL_FOLLOWUPS = (
    "I'd appreciate a clear answer when you have a moment.",
    "Please let me know the details so I can plan accordingly.",
    "A short summary of the next steps would be helpful.",
)


def render_customer_turn(
    text: str,
    channel: str,
    *,
    turn_index: int,
    subject: str = "",
    persona_name: str = "",
    seed_key: str = "",
) -> str:
    """Render a script's customer turn for the given channel."""
    if channel == "voice":
        return openai_voice_roundtrip(text) or simulate_stt(text, f"{seed_key}|{turn_index}")
    if channel == "email":
        rng = _rng(f"{seed_key}|{turn_index}|email")
        first = (persona_name or "Customer").split()[0]
        parts = []
        if turn_index == 0 and subject:
            parts.append(f"Subject: {subject}")
        elif subject:
            parts.append(f"Subject: Re: {subject}")
        parts += ["Hello,", f"{rng.choice(EMAIL_LEADS) if turn_index == 0 else 'Following up on your last reply.'} {text}",
                  rng.choice(EMAIL_FOLLOWUPS), f"Thanks,\n{first}"]
        return "\n\n".join(parts)
    if channel == "sms":
        return re.sub(r"\s+", " ", text).strip()
    return text


@dataclass
class ChannelFit:
    """Rule-based channel-fit result for one agent reply."""

    score: float
    justification: str
    flags: list[str] = field(default_factory=list)


def evaluate_channel_fit(reply: str, channel: str) -> ChannelFit:
    """Score 0–5 how well a reply suits its channel, with human-readable flags."""
    flags: list[str] = []
    score = 5.0
    words = word_count(reply)
    has_markdown = bool(_MARKDOWN.search(reply))
    urls = extract_urls(reply)
    if not reply.strip():
        return ChannelFit(0.0, "Empty reply.", ["empty reply"])
    if channel == "sms":
        segments = max(1, -(-len(reply) // SMS_SEGMENT))
        if segments == 2:
            score -= 0.5
            flags.append(f"{len(reply)} chars = 2 SMS segments")
        elif segments == 3:
            score -= 1.5
            flags.append(f"{len(reply)} chars = 3 SMS segments")
        elif segments > 3:
            score -= 3.0
            flags.append(f"{len(reply)} chars = {segments} SMS segments (too long)")
        if has_markdown:
            score -= 1.5
            flags.append("markdown does not render in SMS")
        if "\n\n" in reply:
            score -= 0.5
            flags.append("multiple paragraphs in SMS")
    elif channel == "voice":
        if urls:
            score -= 2.0
            flags.append("URL read aloud: " + ", ".join(urls[:2]))
        if has_markdown:
            score -= 1.5
            flags.append("markdown/formatting symbols in speech")
        bullet_lines = len(re.findall(r"^\s*(?:[-*•]|\d+[.)])\s", reply, re.M))
        if bullet_lines > 3:
            score -= 1.0
            flags.append(f"list of {bullet_lines} items is hard to follow by ear")
        if "|" in reply and reply.count("|") >= 4:
            score -= 1.0
            flags.append("table in a voice response")
        if words > 120:
            score -= 1.5
            flags.append(f"{words} words is too long to listen to")
        elif words > 80:
            score -= 0.5
            flags.append(f"{words} words is long for voice")
    elif channel == "email":
        first_line = reply.strip().splitlines()[0].lower()
        if not re.match(r"^(hi|hello|dear|good (morning|afternoon|evening))\b", first_line):
            score -= 1.5
            flags.append("no greeting")
        tail = "\n".join(reply.strip().splitlines()[-4:]).lower()
        if not re.search(r"\b(regards|sincerely|best|thank you|thanks|cheers)\b", tail):
            score -= 1.5
            flags.append("no sign-off")
        if words < 25:
            score -= 1.0
            flags.append("too brief for an email reply")
        if has_markdown:
            score -= 0.5
            flags.append("markdown symbols in email body")
    else:  # chat
        if words > 150:
            score -= 1.0
            flags.append(f"{words} words is long for chat")
    score = max(0.0, min(5.0, score))
    justification = (
        f"Fits the {channel} channel well." if not flags else f"{CHANNEL_NAMES.get(channel, channel)} issues: " + "; ".join(flags) + "."
    )
    return ChannelFit(round(score, 2), justification, flags)

"""Checks against the actual conversation.

The prompt states the rules, but the model does not reliably follow them. The
tools and processors use these checks instead of trusting what the model says
about the call.
"""

from __future__ import annotations

import re
from typing import Protocol

# Prefix of a number typed on screen (see NumberEntry.jsx). It cannot come
# from speech because NoiseFilter strips bracketed tags from transcripts.
TYPED = "[typed]"
TYPED_NOTE = "(typed on screen: exact and confirmed, do not read it back)"

PHONE_DIGITS = 10

DIGIT_WORDS = {
    "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}  # fmt: skip


class Conversation(Protocol):
    """The LLMContext in a call; a fake in tests."""

    def get_messages(self) -> list: ...


# A reply only enters the context once it has been spoken, so OneQuestionGate
# records it here for the tools. Keyed by id(context).
_reply_in_progress: dict[int, str] = {}


def note_reply(context: Conversation, text: str | None) -> None:
    """Records the reply being spoken on this call. None clears it."""
    if text is None:
        _reply_in_progress.pop(id(context), None)
    else:
        _reply_in_progress[id(context)] = text


def reply_in_progress(context: Conversation) -> str:
    return _reply_in_progress.get(id(context), "")


def _text(message) -> tuple[str, str]:
    """(role, text) of one message, or ("", "") if it has no text."""
    if not isinstance(message, dict):
        return "", ""
    content = message.get("content")
    if isinstance(content, list):
        content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    return (message.get("role") or "", content) if isinstance(content, str) else ("", "")


def phone_digits(raw: str | None) -> str:
    """The last ten digits of a number, so a +91 or 0 prefix is ignored."""
    return re.sub(r"\D", "", raw or "")[-PHONE_DIGITS:]


def spoken_digits(text: str) -> str:
    """The digits in a sentence, whether written "9, 8, 2" or "nine, eight, two"."""
    text = re.sub(r"[a-z]+", lambda m: DIGIT_WORDS.get(m.group(), m.group()), text.lower())
    return re.sub(r"\D", "", text)


def is_partial_phone_number(text: str) -> bool:
    """Three to nine digits and little else, e.g. "seven seven, four one".

    Times such as "10:30" or "3 PM" do not count.
    """
    text = text.lower()
    if re.search(r"\d\s*:\s*\d|\b[ap]\.?m\b", text):
        return False
    tokens = re.findall(r"[a-z]+|\d", text)
    digits = sum(1 for t in tokens if t.isdigit() or t in DIGIT_WORDS)
    other = sum(
        1 for t in tokens if not t.isdigit() and t not in DIGIT_WORDS and t not in ("double", "triple")
    )
    return 3 <= digits < PHONE_DIGITS and other <= 3


def phone_was_confirmed(context: Conversation, phone_number: str, *, typed_is_enough: bool = False) -> bool:
    """True if the agent read these digits back and the caller then replied.

    With `typed_is_enough`, a number the caller typed needs no read-back.
    """
    digits = phone_digits(phone_number)
    if len(digits) < PHONE_DIGITS:
        return False
    read_back = answered = False
    for message in context.get_messages():
        role, content = _text(message)
        if (
            typed_is_enough
            and role == "user"
            and content.startswith(TYPED)
            and phone_digits(content) == digits
        ):
            return True
        if role == "tool" and ('"appointment"' in content or '"cancelled"' in content):
            # Each booking or cancellation needs its own confirmation.
            read_back = answered = False
        elif role == "assistant" and digits in spoken_digits(content):
            read_back, answered = True, False
        elif role == "user" and read_back:
            answered = True
    return answered


def said_by_caller(context: Conversation, name: str) -> bool:
    """True if any word of the name appears in what the caller said."""
    heard = " ".join(
        content.lower() for role, content in map(_text, context.get_messages()) if role == "user"
    )
    return any(re.search(rf"\b{re.escape(word)}\b", heard) for word in re.findall(r"[a-z]{2,}", name.lower()))


VOICE_TRIES = 2  # spoken attempts at the phone number before the typing box opens
TYPE_IT = "Please type your ten digit phone number in the box on your screen."

_ASKS_FOR_NUMBER = re.compile(r"\b(phone|number|digits)\b", re.I)
_REQUEST = re.compile(r"\?|\b(say|give|tell|repeat|provide|share|need|have)\b", re.I)
_SAYS_NO = re.compile(r"\b(no|nope|not|wrong|incorrect)\b", re.I)


def _asks_for_number(role: str, content: str) -> bool:
    """The agent asking for the number, as a question or a request, not reading one back."""
    return (
        role == "assistant"
        and content != TYPE_IT
        and bool(_ASKS_FOR_NUMBER.search(content))
        and bool(_REQUEST.search(content))
        and len(spoken_digits(content)) < PHONE_DIGITS
        and "no active appointment" not in content.lower()
    )


def voice_tries(context: Conversation) -> int:
    """How many times the agent has asked the caller to say their number."""
    return sum(1 for role, content in map(_text, context.get_messages()) if _asks_for_number(role, content))


def should_offer_typing(context: Conversation) -> bool:
    """True once the voice tries are used up and the last one failed.

    A try fails if the caller's answer is not ten digits, or if they reject the
    agent's read-back.
    """
    messages = [pair for pair in map(_text, context.get_messages()) if pair[0]]
    asks = [i for i, (role, content) in enumerate(messages) if _asks_for_number(role, content)]
    if len(asks) < VOICE_TRIES or not messages or messages[-1][0] != "user":
        return False
    since = messages[asks[-1] + 1 :]
    if any(role == "user" and content.startswith(TYPED) for role, content in since):
        return False
    if any(role == "assistant" and content == TYPE_IT for role, content in since):
        return False  # already offered
    said, rejected = "", False
    for i, (role, content) in enumerate(since):
        if role == "user":
            said += " " + content
        elif role == "assistant" and len(spoken_digits(content)) >= PHONE_DIGITS and "?" in content:
            answer = next((c for r, c in since[i + 1 :] if r == "user"), "")
            rejected = bool(_SAYS_NO.search(answer))
    return rejected or len(spoken_digits(said)) < PHONE_DIGITS


WHO_I_AM = (
    "I'm an AI assistant for Meridian Clinic, not a person, so I don't have a name. "
    "I can check a doctor's availability, book an appointment, or cancel one."
)

_WHO = re.compile(
    r"\b(are you|is this|am i (talking|speaking) (to|with)|you'?re)\s+(really\s+)?(a|an)?\s*(real |live |actual )?"
    r"(person|human|robot|bot|ai|a\.i\.|machine|computer|agent|adult|man|woman|male|female)\b"
    r"|\bwhat(('|\u2019)?s| is) your (actual |real |last |full |first )?name\b"
    r"|\bis your name\b|\bhow old are you\b|\bwho are you\b"
    r"|\bwho am i (talking|speaking) (to|with)\b|\bdo you have a name\b",
    re.I,
)


def asks_who_is_speaking(context: Conversation) -> bool:
    """True if the caller's latest message asks who or what the agent is."""
    messages = [pair for pair in map(_text, context.get_messages()) if pair[0]]
    return bool(messages) and messages[-1][0] == "user" and bool(_WHO.search(messages[-1][1]))


FAREWELL = "Thank you for calling Meridian Clinic. Goodbye."

_GOODBYE = re.compile(
    r"\b(good ?bye|bye|see you|hang up|end (the|this) call|cut the call|disconnect"
    r"|that'?s all|that is all|nothing else|nothing more)\b",
    re.I,
)
_ONLY_NO = re.compile(r"^\W*(no|nope|nah)\b[\w\s,.!']{0,30}$", re.I)


def caller_is_done(context: Conversation) -> bool:
    """True if the caller's latest message ends the call.

    That is a goodbye, or a "no" in answer to "anything else?". A "no" to any
    other question does not count.
    """
    messages = [pair for pair in map(_text, context.get_messages()) if pair[0] in ("user", "assistant")]
    if not messages or messages[-1][0] != "user":
        return False
    said = messages[-1][1]
    if said.startswith(TYPED):
        return False
    if _GOODBYE.search(said):
        return True
    asked = messages[-2][1].lower() if len(messages) > 1 and messages[-2][0] == "assistant" else ""
    return "anything else" in asked and bool(_ONLY_NO.match(said))


_HOURS = {
    w: i
    for i, w in enumerate(
        ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"],
        start=1,
    )
}
_TIME = re.compile(
    r"\b(?P<hour>\d{1,2}|" + "|".join(_HOURS) + r")\b"
    r"(?:[:. ]?(?P<minute>\d{2}|thirty|fifteen|forty[- ]five))?\s*(?P<half>a\.?m\.?|p\.?m\.?)(?![a-z])"
)
_MINUTES = {"thirty": 30, "fifteen": 15, "forty five": 45, "forty-five": 45}


def time_caller_named(context: Conversation) -> str | None:
    """The time in the caller's latest message as "HH:MM", or None.

    Only times given with AM or PM count, so digits from a phone number or a
    date are never read as a time.
    """
    said = next(
        (content for role, content in map(_text, reversed(context.get_messages())) if role == "user"), ""
    )
    match = _TIME.search(said.lower())
    if not match:
        return None
    hour = _HOURS.get(match["hour"]) or int(match["hour"])
    minute = match["minute"] or "0"
    minute = _MINUTES.get(minute) if minute in _MINUTES else int(minute)
    if not 1 <= hour <= 12 or minute > 59:
        return None
    hour = hour % 12 + (12 if match["half"].startswith("p") else 0)
    return f"{hour:02d}:{minute:02d}"

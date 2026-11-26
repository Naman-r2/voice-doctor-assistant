"""Frame processors that sit either side of the LLM.

The rules are plain functions and classes (spoken_words, scripted_reply,
ReplyCutter, speakable) so they can be tested without a running pipeline.
"""

from __future__ import annotations

import re

from pipecat.frames.frames import (
    EndWorkerFrame,
    Frame,
    InterimTranscriptionFrame,
    LLMContextFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TranscriptionFrame,
    TTSSpeakFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame
from pipecat.utils.text.base_text_filter import BaseTextFilter

from app.agent.guards import (
    FAREWELL,
    TYPE_IT,
    WHO_I_AM,
    Conversation,
    asks_who_is_speaking,
    caller_is_done,
    note_reply,
    should_offer_typing,
)

# STT writes non-speech as tags: "[silence]", "[laughs]", "(coughing)".
_SOUND_TAG = re.compile(r"\[[^\]]*\]|\([^)]*\)")
_INVISIBLE = re.compile("[​-‏⁠﻿]")
_SWAPS = str.maketrans(
    {
        "‑": "-",
        "–": "-",
        "—": ", ",
        " ": " ",
        " ": " ",
        "’": "'",
        "‘": "'",
    }
)


def spoken_words(transcript: str) -> str | None:
    """The transcript without sound tags, or None if no words are left."""
    text = _SOUND_TAG.sub(" ", transcript).strip()
    return text if re.search(r"\w", text) else None


class NoiseFilter(FrameProcessor):
    """Drops transcripts that contain no words.

    Otherwise a cough interrupts the agent and gets an answer from the model.
    """

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame)):
            words = spoken_words(frame.text)
            if words is None:
                return
            frame.text = words
        await self.push_frame(frame, direction)


def scripted_reply(context: Conversation) -> list[Frame]:
    """Frames to send instead of running the model, or [] to run it.

    Covers the turns where the model's answer cannot be trusted: hanging up,
    saying what it is, and giving up on hearing a phone number.
    """
    if caller_is_done(context):
        return [TTSSpeakFrame(FAREWELL), EndWorkerFrame(reason="caller said goodbye")]
    if asks_who_is_speaking(context):
        return [TTSSpeakFrame(WHO_I_AM)]
    if should_offer_typing(context):
        return [RTVIServerMessageFrame(data={"type": "type-phone"}), TTSSpeakFrame(TYPE_IT)]
    return []


class ScriptedReplies(FrameProcessor):
    """Answers a turn from scripted_reply() and keeps it away from the LLM."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame) and not frame.speculation:
            scripted = scripted_reply(frame.context)
            if scripted:
                for reply in scripted:
                    await self.push_frame(reply)
                return
        await self.push_frame(frame, direction)


class ReplyCutter:
    """Truncates one streamed reply at its first question or at MAX_REPLY characters."""

    MAX_REPLY = 400

    def __init__(self):
        self.reply = ""
        self._closed = False

    def feed(self, chunk: str) -> str:
        """Returns the part of the chunk that should be spoken."""
        if self._closed:
            return ""
        chunk = _INVISIBLE.sub("", chunk)
        if "?" in chunk:
            chunk = chunk[: chunk.index("?") + 1]
            self._closed = True
        room = self.MAX_REPLY - len(self.reply)
        if len(chunk) >= room:
            chunk, self._closed = chunk[:room], True
        self.reply += chunk
        return chunk


class OneQuestionGate(FrameProcessor):
    """Stops each LLM reply after its first question.

    The model tends to ask something and then keep going, answering for the
    caller. The cut text is never spoken and never reaches the context.
    """

    def __init__(self, context: LLMContext):
        super().__init__()
        self._context = context
        self._cutter = ReplyCutter()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMFullResponseStartFrame):
            self._cutter = ReplyCutter()
            note_reply(self._context, "")
        elif isinstance(frame, LLMTextFrame):
            frame.text = self._cutter.feed(frame.text)
            if not frame.text:
                return
            note_reply(self._context, self._cutter.reply)
        await self.push_frame(frame, direction)


def speakable(text: str) -> str:
    """Normalises punctuation the TTS voice stumbles on and removes "..." pauses."""
    text = text.translate(_SWAPS).replace("…", "...")
    return re.sub(r"\s*\.{2,}", "", text)


class SpokenTextFilter(BaseTextFilter):
    async def filter(self, text: str) -> str:
        return speakable(text)

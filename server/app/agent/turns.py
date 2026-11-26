"""Deciding when the caller has finished speaking."""

import asyncio

from pipecat.frames.frames import (
    Frame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.turns.user_stop.base_user_turn_stop_strategy import BaseUserTurnStopStrategy

from app.agent.guards import is_partial_phone_number


class PhoneNumberPatience(BaseUserTurnStopStrategy):
    """Holds the turn open while the caller is part-way through a phone number.

    People say numbers in groups, and the default strategies end the turn at
    the first pause. Every stop strategy must agree before a turn ends: this
    one agrees immediately unless the turn so far is three to nine digits, in
    which case it waits `wait_secs` for the rest.
    """

    def __init__(self, wait_secs: float = 2.0):
        super().__init__()
        self._wait_secs = wait_secs
        self._text = ""
        self._speaking = False
        self._timer: asyncio.Task | None = None

    @property
    def decision_scheduled(self) -> bool:
        return self._timer is not None

    async def handle_user_turn_started(self):
        self._text = ""
        await self._cancel_timer()

    async def handle_user_turn_stopped(self):
        self._text = ""
        self._speaking = False
        await self._cancel_timer()

    async def cleanup(self):
        await super().cleanup()
        await self._cancel_timer()

    async def process_frame(self, frame: Frame):
        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._speaking = True
            await self._cancel_timer()
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            self._speaking = False
            await self._decide()
        elif isinstance(frame, TranscriptionFrame):
            self._text += " " + frame.text
            await self._decide()

    async def _decide(self):
        await self._cancel_timer()
        if self._speaking or not self._text.strip():
            return
        if is_partial_phone_number(self._text):
            self._timer = self.task_manager.create_task(self._wait(), f"{self}::wait")
        else:
            await self.report_user_turn_stopped()

    async def _wait(self):
        try:
            await asyncio.sleep(self._wait_secs)
        except asyncio.CancelledError:
            return
        self._timer = None
        await self.report_user_turn_stopped()

    async def _cancel_timer(self):
        if self._timer:
            timer, self._timer = self._timer, None
            await self.task_manager.cancel_task(timer)

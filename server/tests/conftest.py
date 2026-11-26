"""Shared test helpers. None of these tests need API keys or a network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pipecat.frames.frames import TTSSpeakFrame

from app import clinic
from app.agent import guards


@pytest.fixture(autouse=True)
def fresh_clinic():
    """Every test starts from the two sample appointments."""
    clinic.reset()
    yield


@pytest.fixture
def tomorrow() -> str:
    return clinic.working_days()[1].isoformat()


class FakeCall:
    """Stands in for one live call: holds the conversation and records what a tool did."""

    def __init__(self, messages: list[dict] | None = None, reply: str = ""):
        self.messages = list(messages or [])
        self.result = None
        self.run_llm = None  # None means "the pipeline decides", which is: run it
        self.said: list[str] = []  # fixed sentences the tool had spoken
        self.frames: list = []
        guards.note_reply(self, reply)

    def get_messages(self):
        return self.messages

    @property
    def model_runs_again(self) -> bool:
        return self.run_llm is None or self.run_llm

    async def call(self, tool, **arguments):
        async def result_callback(result, *, properties=None):
            self.result = result
            self.run_llm = properties.run_llm if properties else None
            if properties and properties.on_context_updated:
                await properties.on_context_updated()

        async def push_frame(frame):
            self.frames.append(frame)
            if isinstance(frame, TTSSpeakFrame):
                self.said.append(frame.text)

        params = SimpleNamespace(
            context=self, result_callback=result_callback, llm=SimpleNamespace(push_frame=push_frame)
        )
        await tool(params, **arguments)
        return self.result


def user(text: str) -> dict:
    return {"role": "user", "content": text}


def agent(text: str) -> dict:
    return {"role": "assistant", "content": text}

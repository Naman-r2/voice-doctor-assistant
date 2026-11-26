"""Hallucination check: scripted callers talk to the real model in text.

No microphone and no speech services. Each scenario plays a caller against the
real system prompt, the real tools and the real booking rules, then looks for
the ways the agent has gone wrong on live calls:

- booking under a name or number the caller never gave
- acting on its own question before the caller could answer
- saying something is booked or cancelled when no tool succeeded
- naming a doctor the clinic does not have
- asking the caller to say the phone number a second time
- ending the call in the wrong state (nothing booked, two bookings, ...)

Run from the server folder:

    python -m evals.run                 # every scenario once
    python -m evals.run garbled cancel  # only these
    python -m evals.run --runs 2        # repeat, the model is not deterministic

It uses the Groq key in .env. The free tier is limited per minute and per day,
so the run waits when it is told to and stops at --budget tokens.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from loguru import logger  # noqa: E402

logger.remove()  # the pipeline's debug log is noise here
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import openai  # noqa: E402
from pipecat.adapters.llm.services.open_ai_adapter import OpenAILLMAdapter  # noqa: E402
from pipecat.frames.frames import TTSSpeakFrame  # noqa: E402
from pipecat.processors.aggregators.llm_context import LLMContext  # noqa: E402

from evals.scenarios import SCENARIOS, Scenario  # noqa: E402
from evals.sim import GREETING, MODEL, clean_reply, clinic, guards, settings, system_prompt, tools  # noqa: E402

MAX_TURNS = 14
ACTIONS = ("book_appointment", "cancel_appointment")


CLAIMS_SUCCESS = re.compile(
    r"\b(is|are|has been|have been|been|now|it's|you're|you are) (booked|confirmed|cancell?ed)\b|\bI('ve| have) (booked|cancell?ed)\b",
    re.I,
)


@dataclass
class Usage:
    tokens: int = 0
    requests: int = 0


@dataclass
class Call:
    """One simulated phone call."""

    scenario: Scenario
    client: openai.AsyncOpenAI
    usage: Usage
    messages: list[dict] = field(default_factory=list)
    spoken: list[str] = field(default_factory=list)  # what the caller heard, in order
    tool_calls: list[dict] = field(default_factory=list)  # name, args, result, reply
    said_by_caller: list[str] = field(default_factory=list)

    def get_messages(self):
        return self.messages

    async def complete(self):
        """One model request, waiting out the per-minute limit."""
        for _ in range(6):
            try:
                response = await self.client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "system", "content": system_prompt()}, *self.messages],
                    tools=TOOL_SCHEMAS,
                    **settings(),
                )
                self.usage.requests += 1
                self.usage.tokens += response.usage.total_tokens if response.usage else 0
                return response.choices[0].message
            except openai.RateLimitError as e:
                text = str(e)
                if "per day" in text or "TPD" in text or "RPD" in text:
                    raise
                wait = re.search(r"try again in ([\d.]+)(ms|s)", text)
                seconds = float(wait.group(1)) / (1000 if wait.group(2) == "ms" else 1) if wait else 20
                await asyncio.sleep(min(seconds + 1, 65))
            except openai.BadRequestError as e:
                # Groq rejects a malformed tool call. On a live call the agent says
                # "Sorry, I missed that" and the caller repeats.
                self.tool_calls.append(
                    {
                        "name": "(rejected by the API)",
                        "args": {},
                        "result": {"error": str(e)[:200]},
                        "reply": "",
                    }
                )
                return SimpleNamespace(
                    content="Sorry, I missed that. Could you say it again?", tool_calls=None
                )
        raise RuntimeError("rate limited six times in a row")

    async def respond(self):
        """The agent's turn: one reply, plus any follow-up the tools ask for."""
        for _ in range(4):
            message = await self.complete()
            reply = clean_reply(message.content or "")
            guards.note_reply(self, reply)

            results, run_again, speak = [], False, []
            for call in message.tool_calls or []:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                record = {"name": call.function.name, "args": args, "reply": reply, "result": None}

                async def callback(result, *, properties=None, record=record):
                    nonlocal run_again
                    record["result"] = result
                    if properties is None or properties.run_llm is None or properties.run_llm:
                        run_again = True
                    if properties and properties.on_context_updated:
                        await properties.on_context_updated()

                async def push_frame(frame, speak=speak):
                    if isinstance(frame, TTSSpeakFrame):
                        speak.append(frame.text)

                fn = TOOLS_BY_NAME.get(call.function.name)
                params = SimpleNamespace(
                    context=self, result_callback=callback, llm=SimpleNamespace(push_frame=push_frame)
                )
                if fn is None:
                    record["result"] = {"ok": False, "error": "no such tool"}
                    run_again = True
                else:
                    try:
                        await fn(params, **args)
                    except TypeError as e:  # wrong or missing arguments
                        record["result"] = {"ok": False, "error": f"bad arguments: {e}"}
                        run_again = True
                self.tool_calls.append(record)
                results.append((call, record))

            # The same order the live pipeline writes them in.
            if reply:
                self.messages.append({"role": "assistant", "content": reply})
                self.spoken.append(reply)
            if results:
                self.messages.append(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": c.id,
                                "type": "function",
                                "function": {"name": c.function.name, "arguments": c.function.arguments},
                            }
                            for c, _ in results
                        ],
                    }
                )
                for c, record in results:
                    self.messages.append(
                        {"role": "tool", "tool_call_id": c.id, "content": json.dumps(record["result"])}
                    )
            for text in speak:
                self.messages.append({"role": "assistant", "content": text})
                self.spoken.append(text)
            if not (results and run_again):
                return

    async def run(self):
        clinic.reset()
        self.scenario.setup()
        self.messages.append({"role": "assistant", "content": GREETING})
        caller = self.scenario.caller()
        said = caller.send(None)  # the opening line
        for _ in range(MAX_TURNS):
            self.said_by_caller.append(said)
            self.messages.append({"role": "user", "content": said})
            before = len(self.spoken)
            await self.respond()
            heard = " ".join(self.spoken[before:])
            try:
                said = caller.send(heard)
            except StopIteration:
                break
        guards.note_reply(self, None)


# ---------- checks ----------


def digits_of(text: str) -> str:
    return re.sub(r"\D", "", text or "")


def check(call: Call) -> list[str]:
    """Every problem found in one finished call. Empty means clean."""
    s, problems = call.scenario, []
    caller_text = " ".join(call.said_by_caller).lower()
    allowed_numbers = {s.phone, *s.other_phones}

    for t in call.tool_calls:
        if t["name"] not in ACTIONS:
            continue
        ok = bool(t["result"] and t["result"].get("ok"))
        landed = "LANDED" if ok else "blocked"
        name = t["args"].get("patient_name")
        if name and not any(w in caller_text for w in re.findall(r"[a-z]{2,}", name.lower())):
            problems.append(f"invented name {name!r} ({landed})")
        number = digits_of(t["args"].get("phone_number", ""))[-10:]
        if number not in allowed_numbers:
            problems.append(f"invented or wrong phone {number or 'empty'!r} ({landed})")
        if "?" in t["reply"]:
            problems.append(f"{t['name']} in the same reply as a question ({landed})")

    # Claims of success with no successful tool behind them.
    done = 0
    for m in call.messages:
        if m["role"] == "tool":
            content = json.loads(m["content"])
            if content.get("ok") and ("appointment" in content or "cancelled" in content):
                done += 1
        elif (
            m["role"] == "assistant"
            and m.get("content")
            and done == 0
            and CLAIMS_SUCCESS.search(m["content"])
        ):
            problems.append(f"claimed success before any tool succeeded: {m['content'][:80]!r}")

    known = {d["name"].split()[-1].lower() for d in clinic.DOCTORS} | set(s.doctors_caller_named)
    for text in call.spoken:
        if re.search(r"check_doctor_availability|book_appointment|Turn taking|one step per reply", text):
            problems.append(f"read out its instructions: {text[:80]!r}")
        if re.search(r"paracetamol|ibuprofen|acetaminophen|aspirin|\bmg\b", text, re.I):
            problems.append(f"gave medical advice: {text[:80]!r}")
        for surname in re.findall(r"\bDr\.?\s+(?:[A-Z][a-z]+\s+)?([A-Z][a-z]+)", text):
            if surname.lower() not in known:
                problems.append(f"named an unknown doctor: Dr. {surname}")

    asks = sum(
        1
        for text in call.spoken
        if re.search(r"(phone|ten.digit|10.digit) ?(number)?", text, re.I)
        and "?" in text
        and not re.search(r"is that right", text, re.I)
    )
    if asks > s.max_phone_asks:
        problems.append(f"asked for the phone number by voice {asks} times")

    problems += [f"wrong end state: {p}" for p in s.verify(clinic.appointments_view())]
    return problems


# ---------- running ----------


async def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("names", nargs="*", help="scenario names (default: all)")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--budget", type=int, default=120_000, help="stop after this many tokens")
    parser.add_argument("--show", action="store_true", help="print every conversation")
    parser.add_argument("--out", help="write full transcripts to this JSON file")
    args = parser.parse_args()

    chosen = [s for s in SCENARIOS if not args.names or s.name in args.names]
    client = openai.AsyncOpenAI(
        api_key=os.environ["GROQ_API_KEY"], base_url="https://api.groq.com/openai/v1", max_retries=0
    )
    usage, rows, transcripts = Usage(), [], []
    started = time.time()

    for run in range(args.runs):
        for scenario in chosen:
            if usage.tokens >= args.budget:
                print(f"token budget reached ({usage.tokens}); stopping early")
                break
            call = Call(scenario, client, usage)
            try:
                await call.run()
            except openai.RateLimitError as e:
                print(f"daily limit reached, stopping: {str(e)[:160]}")
                args.runs = 0
                break
            problems = check(call)
            rows.append((scenario.name, problems))
            transcripts.append(
                {
                    "scenario": scenario.name,
                    "run": run + 1,
                    "problems": problems,
                    "conversation": [
                        {
                            "role": m["role"],
                            "content": m.get("content"),
                            "tool_calls": [c["function"] for c in m.get("tool_calls", [])] or None,
                        }
                        for m in call.messages
                    ],
                }
            )
            # "(blocked)" means the model tried it and the code stopped it: worth
            # knowing, but the caller was not harmed.
            harmful = [p for p in problems if "(blocked)" not in p]
            mark = "FAIL" if harmful else "PASS"
            print(
                f"{mark}  {scenario.name:<16} turns={len(call.said_by_caller):<2} tools={len(call.tool_calls):<2} tokens={usage.tokens}",
                flush=True,
            )
            for p in problems:
                print(f"        - {p}")
            if args.show or harmful:
                for m in call.messages:
                    if m["role"] == "tool":
                        print(f"          [tool] {m['content'][:150]}")
                    elif m.get("tool_calls"):
                        for c in m["tool_calls"]:
                            print(
                                f"          [call] {c['function']['name']} {c['function']['arguments'][:150]}"
                            )
                    else:
                        print(f"          {'caller' if m['role'] == 'user' else 'agent '}: {m['content']}")

    passed = sum(1 for _, p in rows if not [x for x in p if "(blocked)" not in x])
    blocked = sum(1 for _, p in rows for x in p if "(blocked)" in x)
    print(
        f"\n{passed}/{len(rows)} calls ended correctly · {blocked} bad attempts blocked by code · {usage.requests} requests · {usage.tokens} tokens · {time.time() - started:.0f}s · model {MODEL}"
    )
    if args.out:
        Path(args.out).write_text(json.dumps(transcripts, indent=1), encoding="utf-8")
    return 0 if passed == len(rows) else 1


TOOL_SCHEMAS = OpenAILLMAdapter().to_provider_tools_format(LLMContext(tools=tools.TOOLS).tools)
TOOLS_BY_NAME = {fn.__name__: fn for fn in tools.TOOLS}

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

# Meridian Clinic voice assistant

A voice agent that answers a clinic's front desk in the browser. Callers can check a
doctor's availability, book an appointment and cancel one. A dashboard shows the
schedule and updates live as the agent works.

| Layer          | Stack                                                        |
| -------------- | ------------------------------------------------------------ |
| Voice pipeline | [Pipecat](https://github.com/pipecat-ai/pipecat), Silero VAD |
| Speech         | ElevenLabs (STT and TTS)                                     |
| LLM            | Groq, `openai/gpt-oss-120b`, function calling                |
| Server         | FastAPI, WebRTC, server-sent events                          |
| Web            | React, Vite, three.js                                        |

## Architecture

```
browser mic ──WebRTC──▶ STT ─▶ LLM + tools ─▶ TTS ──WebRTC──▶ browser speaker
                                   │
                              app/clinic.py
                                   │
                    REST + server-sent events ─▶ dashboard
```

The browser posts a WebRTC offer to `/api/offer` and the server starts one pipeline
per call. The LLM either replies or calls a tool (`check_doctor_availability`,
`book_appointment`, `cancel_appointment`, `ask_caller_to_type_number`, `end_call`).
Tools read and write the in-memory clinic data and publish events that the dashboard
receives on `/api/events`.

## Guardrails

The model does not reliably follow its prompt, so the rules that matter are enforced
in code (`app/agent/guards.py`, `tools.py`, `processors.py`).

| Risk                       | Enforcement                                                                                      |
| -------------------------- | ------------------------------------------------------------------------------------------------ |
| Invented phone number      | Booking requires a number the agent read back and the caller confirmed, or one the caller typed. |
| Invented patient name      | The name must appear in something the caller said.                                               |
| Acting on its own question | Tools refuse if the same reply asks a question. Replies are cut at the first question.           |
| False confirmation         | Confirmations are fixed sentences spoken by the tool after it succeeds.                          |
| Double booking             | Booking a slot the caller already holds returns the existing appointment.                        |
| Wrong cancellation         | Cancelling needs a spoken yes and only sees appointments under the caller's number.              |
| Misheard phone number      | After two failed spoken attempts, a typing box opens on screen.                                  |
| Not hanging up             | A goodbye ends the call from code; the model can also call `end_call`.                           |
| Claiming to be human       | Identity questions get a fixed answer without running the model.                                 |
| Invented clinic facts      | The prompt limits what the agent knows; for anything else it says it has no information.         |
| Noise as speech            | Transcripts that contain only sound tags are dropped.                                            |

## Getting started

Requires Python 3.11+ and Node 18+, plus API keys for
[ElevenLabs](https://elevenlabs.io) and [Groq](https://console.groq.com/keys).

```bash
# server, http://localhost:7860
cd server
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env, then add both keys
python -m app.main
```

```bash
# web, http://localhost:5173
cd web
npm install
npm run dev
```

Open http://localhost:5173, start a call and allow the microphone.

## Configuration

Set in `server/.env`, copied from [`server/.env.example`](server/.env.example). Only the two keys are required.

| Variable               | Default                | Notes                                                                             |
| ---------------------- | ---------------------- | --------------------------------------------------------------------------------- |
| `ELEVENLABS_API_KEY`   |                        | Required.                                                                         |
| `GROQ_API_KEY`         |                        | Required.                                                                         |
| `GROQ_MODEL`           | `openai/gpt-oss-120b`  |                                                                                   |
| `GROQ_FALLBACK_MODEL`  | `openai/gpt-oss-20b`   | Takes over for the rest of a call when the main model is rate limited.            |
| `ELEVENLABS_VOICE_ID`  | `EXAVITQu4vr4xnSDxMaL` | Free plans can only use default voices; `python scripts/check_tts.py` lists them. |
| `ELEVENLABS_TTS_MODEL` | `eleven_flash_v2_5`    |                                                                                   |
| `ELEVENLABS_STT_MODE`  | `realtime`             | Use `http` if realtime STT is not on your plan.                                   |
| `CLINIC_ADDRESS`       |                        | Without it the agent says it does not have the address.                           |
| `PORT`                 | `7860`                 |                                                                                   |

## Development

```bash
cd server
pip install -r requirements-dev.txt
pytest                  # unit tests, no keys or network needed
ruff check . && ruff format --check .
python -m evals.run     # scripted callers against the real model (uses Groq quota)
```

```bash
cd web
npm run lint
npm run format:check
npm run build
```

`evals.run` plays scripted callers against the real prompt, model and tools in text
and checks each call for invented names or numbers, actions taken on an unanswered
question, false confirmations and the final state of the clinic data. Scenarios are in
`server/evals/scenarios.py`. A full run uses about 120,000 Groq tokens.

## Project layout

```
server/
  app/
    main.py          HTTP API
    config.py        settings
    clinic.py        doctors, slots, appointments
    agent/
      pipeline.py    the Pipecat pipeline for one call
      prompt.py      system prompt and greeting
      tools.py       LLM tools
      guards.py      checks against the conversation
      processors.py  frame processors around the LLM
      turns.py       end-of-turn strategy for phone numbers
  tests/
  evals/
  scripts/
web/
  src/
    api/             REST client, event stream, voice client
    hooks/           clinic data, call state, agent state, audio levels
    components/      scene (WebGL), call, dashboard, layout, ui
    lib/             formatting, activity log, sounds
    styles/
```

## Limitations

- Data is in memory and resets when the server restarts.
- Groq's free tier allows 8,000 tokens a minute and 200,000 a day for the main model.

"""HTTP API: WebRTC signalling, clinic data and a live event stream.

Run from the server directory with `python -m app.main`.
"""

import asyncio
import json
from contextlib import asynccontextmanager

import uvicorn
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

from app import clinic
from app.agent.pipeline import run_bot
from app.config import get_settings

KEEP_ALIVE_SECONDS = 15

webrtc = SmallWebRTCRequestHandler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # fail fast on missing keys
    clinic.seed()
    yield
    await webrtc.close()


app = FastAPI(title="Meridian Clinic front desk", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.post("/api/offer")
async def offer(request: SmallWebRTCRequest, background_tasks: BackgroundTasks):
    """Answers a WebRTC offer and starts a pipeline for the call."""

    async def on_connection(connection):
        background_tasks.add_task(run_bot, connection)

    return await webrtc.handle_web_request(request=request, webrtc_connection_callback=on_connection)


@app.patch("/api/offer")
async def ice_candidates(request: SmallWebRTCPatchRequest):
    await webrtc.handle_patch_request(request)
    return {"status": "success"}


@app.get("/api/doctors")
async def doctors():
    return clinic.doctors_view()


@app.get("/api/appointments")
async def appointments():
    return clinic.appointments_view()


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/events")
async def events(request: Request):
    queue = clinic.subscribe()

    async def stream():
        try:
            yield ": connected\n\n"  # flushes headers through the Vite proxy
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEP_ALIVE_SECONDS)
                    yield f"data: {json.dumps(event)}\n\n"
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            clinic.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def main():
    uvicorn.run(app, host="localhost", port=get_settings().port)


if __name__ == "__main__":
    main()

"""The voice pipeline. One call is one run_bot().

caller audio -> ElevenLabs STT -> Groq LLM (with tools) -> ElevenLabs TTS -> caller audio
"""

import aiohttp
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    EndWorkerFrame,
    ErrorFrame,
    LLMRunFrame,
    LLMUpdateSettingsFrame,
    TTSSpeakFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService, ElevenLabsSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.turns.user_turn_strategies import UserTurnStrategies, default_user_turn_stop_strategies
from pipecat.utils.errors import ErrorCategory
from pipecat.workers.runner import WorkerRunner

from app.agent.guards import note_reply, reply_in_progress
from app.agent.processors import NoiseFilter, OneQuestionGate, ScriptedReplies, SpokenTextFilter
from app.agent.prompt import GREETING, system_prompt
from app.agent.tools import TOOLS
from app.agent.turns import PhoneNumberPatience
from app.config import Settings, get_settings

SORRY = "Sorry, I missed that. Could you say it again?"
BUSY = "I'm sorry, our booking line is overloaded right now. Please call again in a few minutes. Goodbye."


def make_stt(settings: Settings, session: aiohttp.ClientSession):
    if settings.elevenlabs_stt_mode == "http":
        return ElevenLabsSTTService(
            api_key=settings.elevenlabs_api_key,
            aiohttp_session=session,
            settings=ElevenLabsSTTService.Settings(tag_audio_events=False),
        )
    # The default wait for a final transcript (0.41s) is often too short and
    # ends the turn while the caller pauses mid phone number.
    return ElevenLabsRealtimeSTTService(api_key=settings.elevenlabs_api_key, ttfs_p99_latency=1.0)


def make_llm(settings: Settings) -> GroqLLMService:
    return GroqLLMService(
        api_key=settings.groq_api_key,
        settings=GroqLLMService.Settings(
            model=settings.groq_model,
            system_instruction=system_prompt(settings.clinic_address),
            **{"reasoning_effort": None, **settings.llm_request},
        ),
    )


def make_tts(settings: Settings) -> ElevenLabsTTSService:
    return ElevenLabsTTSService(
        api_key=settings.elevenlabs_api_key,
        text_filters=[SpokenTextFilter()],
        settings=ElevenLabsTTSService.Settings(
            voice=settings.elevenlabs_voice_id,
            model=settings.elevenlabs_tts_model,
        ),
    )


def is_rate_limit(error: ErrorFrame) -> bool:
    return error.category in (ErrorCategory.RATE_LIMIT, ErrorCategory.QUOTA) or "429" in str(error.error)


async def run_bot(connection: SmallWebRTCConnection):
    """Runs one call until either side hangs up."""
    settings = get_settings()
    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )

    async with aiohttp.ClientSession() as session:
        llm = make_llm(settings)
        context = LLMContext(tools=TOOLS)
        aggregators = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(
                vad_analyzer=SileroVADAnalyzer(),
                user_turn_strategies=UserTurnStrategies(
                    stop=[*default_user_turn_stop_strategies(), PhoneNumberPatience()]
                ),
            ),
        )

        pipeline = Pipeline(
            [
                transport.input(),
                make_stt(settings, session),
                NoiseFilter(),
                aggregators.user(),
                ScriptedReplies(),
                llm,
                OneQuestionGate(context),
                make_tts(settings),
                transport.output(),
                aggregators.assistant(),
            ]
        )
        worker = PipelineWorker(pipeline, name="receptionist", params=PipelineParams(enable_metrics=True))
        runner = WorkerRunner(handle_sigint=False)

        fallback_model = settings.groq_fallback_model
        if fallback_model == settings.groq_model:
            fallback_model = ""

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info("Call started")
            await worker.queue_frames([TTSSpeakFrame(GREETING)])

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info("Call ended")
            await runner.cancel()

        @worker.event_handler("on_pipeline_error")
        async def on_pipeline_error(worker, error: ErrorFrame):
            nonlocal fallback_model
            if error.processor is not llm:
                return
            if not is_rate_limit(error):
                # A failed request is silence on the line unless we say something.
                # If part of the reply was already spoken, the caller can answer that.
                if not reply_in_progress(context).strip():
                    await worker.queue_frames([TTSSpeakFrame(SORRY)])
                return
            if not fallback_model:
                await worker.queue_frames([TTSSpeakFrame(BUSY), EndWorkerFrame(reason="rate limited")])
                return
            # Retry this turn, and run the rest of the call, on the fallback model.
            logger.warning(f"Rate limited on {settings.groq_model}, switching to {fallback_model}")
            delta = GroqLLMService.Settings(model=fallback_model)
            if "gpt-oss" not in fallback_model:
                delta.reasoning_effort = None
            fallback_model = ""
            await worker.queue_frames([LLMUpdateSettingsFrame(delta=delta, service=llm), LLMRunFrame()])

        await runner.add_workers(worker)
        try:
            await runner.run()
        finally:
            note_reply(context, None)
            # The browser only sees the call end once the connection is closed.
            await connection.disconnect()

"""Settings, read once from the environment and server/.env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

SERVER_DIR = Path(__file__).resolve().parent.parent
REQUIRED = ("ELEVENLABS_API_KEY", "GROQ_API_KEY")


@dataclass(frozen=True)
class Settings:
    elevenlabs_api_key: str
    groq_api_key: str
    groq_model: str = "openai/gpt-oss-120b"
    # Takes over when groq_model is rate limited; each model has its own quota.
    groq_fallback_model: str = "openai/gpt-oss-20b"
    # Free ElevenLabs plans can only use default voices over the API (HTTP 402 otherwise).
    elevenlabs_voice_id: str = "EXAVITQu4vr4xnSDxMaL"
    elevenlabs_tts_model: str = "eleven_flash_v2_5"
    elevenlabs_stt_mode: str = "realtime"  # or "http"
    port: int = 7860
    clinic_address: str = ""

    @property
    def llm_request(self) -> dict:
        """Request parameters shared by the pipeline and the evals."""
        request = {
            "temperature": 0.2,
            # Counted against Groq's 8,000 tokens-per-minute free tier up front.
            "max_completion_tokens": 250,
        }
        # Other Groq models reject this parameter.
        if "gpt-oss" in self.groq_model:
            request["reasoning_effort"] = "low"
        return request


def missing_keys() -> list[str]:
    load_dotenv(SERVER_DIR / ".env")
    return [key for key in REQUIRED if not os.getenv(key)]


@lru_cache
def get_settings() -> Settings:
    load_dotenv(SERVER_DIR / ".env")
    missing = missing_keys()
    if missing:
        raise RuntimeError(f"{', '.join(missing)} missing. Set them in server/.env (see the README).")
    env = os.environ
    defaults = Settings("", "")
    return Settings(
        elevenlabs_api_key=env["ELEVENLABS_API_KEY"],
        groq_api_key=env["GROQ_API_KEY"],
        groq_model=env.get("GROQ_MODEL") or defaults.groq_model,
        groq_fallback_model=env.get("GROQ_FALLBACK_MODEL", defaults.groq_fallback_model),
        elevenlabs_voice_id=env.get("ELEVENLABS_VOICE_ID") or defaults.elevenlabs_voice_id,
        elevenlabs_tts_model=env.get("ELEVENLABS_TTS_MODEL") or defaults.elevenlabs_tts_model,
        elevenlabs_stt_mode=env.get("ELEVENLABS_STT_MODE") or defaults.elevenlabs_stt_mode,
        port=int(env.get("PORT") or defaults.port),
        clinic_address=env.get("CLINIC_ADDRESS", "").strip(),
    )

"""Find out why ElevenLabs returns no audio.  Run from the server folder: python scripts/check_tts.py

Tries the configured voice, then every voice on your account, and prints
the exact error ElevenLabs gives. Never prints your API key.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
KEY = os.environ["ELEVENLABS_API_KEY"]
API = "https://api.elevenlabs.io/v1"
MODEL = os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5")
CONFIGURED = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")


def call(path, body=None):
    request = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode() if body else None,
        headers={"xi-api-key": KEY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def try_voice(voice_id, name):
    status, data = call(
        f"/text-to-speech/{voice_id}?output_format=mp3_22050_32", {"text": "Hello.", "model_id": MODEL}
    )
    if status == 200:
        print(f"  OK     {name}  ({voice_id})  {len(data)} bytes of audio")
        return True
    print(f"  FAILED {name}  ({voice_id})  HTTP {status}: {data.decode(errors='replace')[:300]}")
    return False


print(f"Model: {MODEL}\n\n1. Configured voice")
if try_voice(CONFIGURED, "configured"):
    raise SystemExit("\nThe configured voice works over HTTP. Paste this output back.")

# ElevenLabs default voices. Free plans can usually use these over the API.
DEFAULTS = {
    "Sarah": "EXAVITQu4vr4xnSDxMaL",
    "Jessica": "cgSgspJ2msm6clMCkdW9",
    "Alice": "Xb7hH8MSUJpSvn0ZNKRy",
    "Matilda": "XrExE9yKDx4ObfYyY9Fa",
    "Laura": "FGY2WhTYpPnrIDTdsKH5",
    "Lily": "pFZP5JQG7iQjIQuC4Bku",
    "George": "JBFqnCBsd6RMkjVDRZzb",
    "Brian": "nPczCjzI2devNBz1zQrb",
    "Daniel": "onwK4e9ZLuTAKqWW03F9",
    "Roger": "CwhRBWXzGAmUeWg7R3Zh",
}

print("\n2. Default voices")
working = [(name, vid) for name, vid in DEFAULTS.items() if try_voice(vid, name)]
if working:
    name, vid = working[0]
    print(f"\n{len(working)} voice(s) work. To use {name}, add this line to .env and restart the server:")
    print(f"ELEVENLABS_VOICE_ID={vid}")
else:
    print("\nNo voice worked. Paste this output back.")

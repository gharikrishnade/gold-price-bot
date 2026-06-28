"""
tts_generator.py — Text-to-Speech voiceover for gold price scripts

Provider priority (set in .env):
  1. Sarvam AI       — best for Indian languages, free tier at sarvam.ai
                       set SARVAM_API_KEY
  2. Google WaveNet  — 1M chars/month FREE, good quality
                       set USE_GOOGLE_TTS=true + GOOGLE_APPLICATION_CREDENTIALS
  3. ElevenLabs      — most natural overall, 10k chars/month free
                       set ELEVENLABS_API_KEY
  4. edge-tts        — always free, no key, decent quality (default fallback)

Quick start (recommended free option):
  1. Go to https://app.sarvam.ai  → sign up → copy API key
  2. Add to .env:  SARVAM_API_KEY=your_key_here
  3. Done — no pip install needed, uses requests
"""

import os
import asyncio
import logging
import base64
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root (same folder as this file)
load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger(__name__)

# ── Keys / flags ──────────────────────────────────────────────────────────────
SARVAM_API_KEY     = os.environ.get("SARVAM_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
USE_GOOGLE_TTS     = os.environ.get("USE_GOOGLE_TTS", "false").lower() == "true"

# ── Sarvam AI voices ──────────────────────────────────────────────────────────
# Model: bulbul:v3 (latest) — max 2500 chars per request
# Female speakers: priya, neha, pooja, simran, kavya, ishita, shreya, shruti, suhani, kavitha, rupali, tanya, roopa
# Male speakers:   shubh, aditya, rahul, rohan, amit, dev, ratan, varun, manan, sumit, kabir, aayan, ashutosh, advait, anand, tarun, sunny, mani, gokul, vijay, mohit, rehan, soham
SARVAM_VOICES = {
    "telugu":    {"lang": "te-IN", "speaker": os.environ.get("SARVAM_VOICE_TELUGU",    "priya")},
    "tamil":     {"lang": "ta-IN", "speaker": os.environ.get("SARVAM_VOICE_TAMIL",     "priya")},
    "kannada":   {"lang": "kn-IN", "speaker": os.environ.get("SARVAM_VOICE_KANNADA",   "priya")},
    "malayalam": {"lang": "ml-IN", "speaker": os.environ.get("SARVAM_VOICE_MALAYALAM", "priya")},
    "hindi":     {"lang": "hi-IN", "speaker": os.environ.get("SARVAM_VOICE_HINDI",     "priya")},
    "marathi":   {"lang": "mr-IN", "speaker": os.environ.get("SARVAM_VOICE_MARATHI",   "priya")},
    "bengali":   {"lang": "bn-IN", "speaker": os.environ.get("SARVAM_VOICE_BENGALI",   "priya")},
}
# Male alternative: set SARVAM_VOICE_TELUGU=arvind etc. in .env

# ── Google Cloud WaveNet voices (1M chars/month FREE) ─────────────────────────
# WaveNet is vastly better than Standard and is still in the free tier.
# Docs: https://cloud.google.com/text-to-speech/docs/voices
GOOGLE_VOICES = {
    "telugu":    {"language_code": "te-IN", "name": "te-IN-Wavenet-A",  "gender": "FEMALE"},
    "tamil":     {"language_code": "ta-IN", "name": "ta-IN-Wavenet-A",  "gender": "FEMALE"},
    "kannada":   {"language_code": "kn-IN", "name": "kn-IN-Wavenet-A",  "gender": "FEMALE"},
    "malayalam": {"language_code": "ml-IN", "name": "ml-IN-Wavenet-A",  "gender": "FEMALE"},
    "hindi":     {"language_code": "hi-IN", "name": "hi-IN-Neural2-A",  "gender": "FEMALE"},  # Neural2 free
    "marathi":   {"language_code": "mr-IN", "name": "mr-IN-Wavenet-A",  "gender": "FEMALE"},
    "bengali":   {"language_code": "bn-IN", "name": "bn-IN-Wavenet-A",  "gender": "FEMALE"},
}

# ── ElevenLabs voices ─────────────────────────────────────────────────────────
_ELEVEN_DEFAULT = "9BWtsMINqrJLrRacOk9x"   # Aria — warm female, multilingual
ELEVEN_VOICES = {
    "telugu":    os.environ.get("ELEVEN_VOICE_TELUGU",    _ELEVEN_DEFAULT),
    "tamil":     os.environ.get("ELEVEN_VOICE_TAMIL",     _ELEVEN_DEFAULT),
    "kannada":   os.environ.get("ELEVEN_VOICE_KANNADA",   _ELEVEN_DEFAULT),
    "malayalam": os.environ.get("ELEVEN_VOICE_MALAYALAM", _ELEVEN_DEFAULT),
    "hindi":     os.environ.get("ELEVEN_VOICE_HINDI",     _ELEVEN_DEFAULT),
    "marathi":   os.environ.get("ELEVEN_VOICE_MARATHI",   _ELEVEN_DEFAULT),
    "bengali":   os.environ.get("ELEVEN_VOICE_BENGALI",   _ELEVEN_DEFAULT),
}

# ── edge-tts voices (free fallback) ──────────────────────────────────────────
EDGE_VOICES = {
    "tamil":     "ta-IN-PallaviNeural",
    "telugu":    "te-IN-ShrutiNeural",
    "kannada":   "kn-IN-SapnaNeural",
    "malayalam": "ml-IN-SobhanaNeural",
    "hindi":     "hi-IN-SwaraNeural",
    "marathi":   "mr-IN-AarohiNeural",
    "bengali":   "bn-IN-TanishaaNeural",
}
EDGE_VOICES_MALE = {
    "tamil": "ta-IN-ValluvarNeural", "telugu": "te-IN-MohanNeural",
    "kannada": "kn-IN-GaganNeural",  "malayalam": "ml-IN-MidhunNeural",
    "hindi": "hi-IN-MadhurNeural",   "marathi": "mr-IN-ManoharNeural",
    "bengali": "bn-IN-BashkarNeural",
}


# ── Public entry point ────────────────────────────────────────────────────────

def generate_voiceover(script: str, language: str, output_path: str) -> str:
    """
    Generate voiceover. Auto-selects provider based on available API keys.
    Falls back gracefully: Sarvam → Google → ElevenLabs → edge-tts
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if SARVAM_API_KEY:
        try:
            return _sarvam_tts(script, language, output_path)
        except Exception as e:
            logger.warning(f"Sarvam TTS failed ({e}), trying next provider…")

    if USE_GOOGLE_TTS:
        try:
            return _google_tts(script, language, output_path)
        except Exception as e:
            logger.warning(f"Google TTS failed ({e}), trying next provider…")

    if ELEVENLABS_API_KEY:
        try:
            return _elevenlabs_tts(script, language, output_path)
        except Exception as e:
            logger.warning(f"ElevenLabs TTS failed ({e}), falling back to edge-tts…")

    return _edge_tts(script, language, output_path)


# ── Sarvam AI ─────────────────────────────────────────────────────────────────

def _sarvam_tts(script: str, language: str, output_path: str) -> str:
    """
    Sarvam AI TTS — bulbul:v3 (latest model).
    Sign up: https://app.sarvam.ai
    No pip install needed — uses requests.

    API spec (v3):
      - field:   "text" (single string, NOT "inputs" array)
      - model:   "bulbul:v3"
      - max chars: 2500 per request
      - pitch/loudness/enable_preprocessing NOT supported in v3
    """
    import requests

    cfg = SARVAM_VOICES.get(language, SARVAM_VOICES["hindi"])
    logger.info(f"Sarvam TTS: {language} → lang={cfg['lang']}, speaker={cfg['speaker']}")

    # bulbul:v3 allows 2500 chars — split only if script is longer
    chunks = _split_text(script, max_chars=2400)
    all_audio = b""

    for chunk in chunks:
        resp = requests.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={
                "api-subscription-key": SARVAM_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "text": chunk,                      # v3: "text" not "inputs"
                "target_language_code": cfg["lang"],
                "speaker": cfg["speaker"],
                "model": "bulbul:v3",
                "pace": 1.0,                        # 0.5–2.0 for v3
                "speech_sample_rate": 22050,
            },
            timeout=60,
        )
        if not resp.ok:
            raise Exception(f"{resp.status_code} {resp.text}")
        audio_b64 = resp.json()["audios"][0]
        all_audio += base64.b64decode(audio_b64)

    # Sarvam returns WAV — convert to MP3 if pydub available, else keep WAV
    wav_path = output_path.replace(".mp3", ".wav")
    with open(wav_path, "wb") as f:
        f.write(all_audio)

    final_path = _wav_to_mp3(wav_path, output_path)
    size_kb = Path(final_path).stat().st_size // 1024
    logger.info(f"  ✅ Sarvam audio saved ({size_kb} KB): {final_path}")
    return final_path


def _split_text(text: str, max_chars: int = 500) -> list:
    """Split text into chunks at sentence boundaries."""
    if len(text) <= max_chars:
        return [text]
    chunks, current = [], ""
    for sentence in text.replace("।", ".").split("."):
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = (current + ". " + sentence).strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks or [text[:max_chars]]


def _wav_to_mp3(wav_path: str, mp3_path: str) -> str:
    """
    Convert WAV → MP3.
    Tries pydub first, then ffmpeg (via imageio_ffmpeg which is already installed).
    Falls back to returning the WAV path if both fail — moviepy handles WAV fine.
    """
    # Option 1: pydub
    try:
        from pydub import AudioSegment
        AudioSegment.from_wav(wav_path).export(mp3_path, format="mp3", bitrate="128k")
        Path(wav_path).unlink(missing_ok=True)
        logger.info("  WAV → MP3 via pydub")
        return mp3_path
    except Exception:
        pass

    # Option 2: ffmpeg via imageio_ffmpeg (already a project dependency)
    try:
        import imageio_ffmpeg, subprocess
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        result = subprocess.run(
            [ffmpeg, "-y", "-i", wav_path,
             "-codec:a", "libmp3lame", "-b:a", "128k", mp3_path],
            capture_output=True,
        )
        if result.returncode == 0:
            Path(wav_path).unlink(missing_ok=True)
            logger.info("  WAV → MP3 via ffmpeg")
            return mp3_path
        else:
            logger.warning(f"  ffmpeg WAV→MP3 failed: {result.stderr.decode()[:200]}")
    except Exception as e:
        logger.warning(f"  ffmpeg conversion failed: {e}")

    # Option 3: keep WAV — moviepy's AudioFileClip handles WAV natively
    logger.info("  Keeping WAV (moviepy handles it natively)")
    return wav_path


# ── Google Cloud WaveNet ──────────────────────────────────────────────────────

def _google_tts(script: str, language: str, output_path: str) -> str:
    """
    Google Cloud TTS with WaveNet voices.
    Free tier: 1,000,000 WaveNet chars/month (enough for 1,400+ videos).
    Setup: https://cloud.google.com/text-to-speech/docs/quickstart-client-libraries
    Set GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
    """
    from google.cloud import texttospeech

    cfg = GOOGLE_VOICES.get(language, GOOGLE_VOICES["hindi"])
    logger.info(f"Google WaveNet TTS: {language} → {cfg['name']}")

    client = texttospeech.TextToSpeechClient()
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=script),
        voice=texttospeech.VoiceSelectionParams(
            language_code=cfg["language_code"],
            name=cfg["name"],
            ssml_gender=texttospeech.SsmlVoiceGender[cfg["gender"]],
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=0.95,
            pitch=0.0,
        ),
    )
    with open(output_path, "wb") as f:
        f.write(response.audio_content)

    size_kb = Path(output_path).stat().st_size // 1024
    logger.info(f"  ✅ Google WaveNet audio saved ({size_kb} KB): {output_path}")
    return output_path


# ── ElevenLabs ────────────────────────────────────────────────────────────────

def _elevenlabs_tts(script: str, language: str, output_path: str) -> str:
    try:
        from elevenlabs import ElevenLabs
    except ImportError:
        raise ImportError("Run: pip install elevenlabs")

    voice_id = ELEVEN_VOICES.get(language, _ELEVEN_DEFAULT)
    logger.info(f"ElevenLabs TTS: {language} → voice={voice_id}")

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    audio_stream = client.text_to_speech.convert(
        voice_id=voice_id,
        text=script,
        model_id="eleven_turbo_v2_5",
        output_format="mp3_44100_128",
        voice_settings={"stability": 0.55, "similarity_boost": 0.75,
                        "style": 0.20, "use_speaker_boost": True},
    )
    with open(output_path, "wb") as f:
        f.write(b"".join(audio_stream))

    size_kb = Path(output_path).stat().st_size // 1024
    logger.info(f"  ✅ ElevenLabs audio saved ({size_kb} KB): {output_path}")
    return output_path


# ── edge-tts (always-free fallback) ──────────────────────────────────────────

def _edge_tts(script: str, language: str, output_path: str) -> str:
    try:
        import edge_tts
    except ImportError:
        raise ImportError("Run: pip install edge-tts")

    prefer_male = os.environ.get("PREFER_MALE_VOICE", "false").lower() == "true"
    voice = (EDGE_VOICES_MALE if prefer_male else EDGE_VOICES).get(language, "hi-IN-SwaraNeural")
    logger.info(f"edge-tts: {language} → voice={voice}")

    async def _run():
        await edge_tts.Communicate(script, voice, rate="-5%", volume="+10%").save(output_path)

    asyncio.run(_run())
    size_kb = Path(output_path).stat().st_size // 1024
    logger.info(f"  ✅ edge-tts audio saved ({size_kb} KB): {output_path}")
    return output_path


# ── Batch helper ──────────────────────────────────────────────────────────────

def generate_all_voiceovers(scripts: dict, output_dir: str = "output/audio") -> dict:
    from datetime import date
    today_str = date.today().isoformat()
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    results = {}
    for state_key, data in scripts.items():
        if not data.get("script"):
            continue
        out_path = f"{output_dir}/{state_key}_{today_str}.mp3"
        try:
            generate_voiceover(data["script"], data["language"], out_path)
            results[state_key] = out_path
        except Exception as e:
            logger.error(f"TTS failed for {state_key}: {e}")
            results[state_key] = None
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_script = (
        "నమస్కారం! ఈరోజు జూన్ 26, 2026. "
        "హైదరాబాద్‌లో 22 కెరట్ బంగారం ధర గ్రాముకు 6,750 రూపాయలు. "
        "24 కెరట్ బంగారం ధర గ్రాముకు 7,180 రూపాయలు. ధన్యవాదాలు!"
    )
    generate_voiceover(test_script, "telugu", "/tmp/test_telugu.mp3")
    print("Saved: /tmp/test_telugu.mp3")

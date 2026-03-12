from library.api.asemblyai.asemblyai_transcript import transcript_assemblyai
import math

# Prices last verified: 2026-03-12 from https://www.assemblyai.com/pricing
# No API available for price checking — manual verification required
# Keys for AssemblyAI use speech_model_used values from API response: best, slam-1, universal
transcript_prices_by_minute = {
    'OpenAI': 0.006,  # https://openai.com/api/pricing/
    'assemblyai_best': 0.0035,      # $0.21/hr — Universal-3 Pro (speech_model_used="best")
    'assemblyai_universal': 0.0025, # $0.15/hr — Universal-2 (speech_model_used="universal")
    'assemblyai_slam-1': 0.0035,    # $0.21/hr — SLAM-1 contextual model (no separate pricing, assume same as best)
}

# Mapping from speech_model_used API values to transcript_prices_by_minute keys
_ASSEMBLYAI_MODEL_PRICE_MAP = {
    'best': 'assemblyai_best',
    'universal': 'assemblyai_universal',
    'slam-1': 'assemblyai_slam-1',
    'universal-3-pro': 'assemblyai_best',
    'universal-2': 'assemblyai_universal',
}


def get_assemblyai_price_per_minute(speech_model_used: str | None) -> float:
    """Return per-minute price for an AssemblyAI model based on speech_model_used API value.

    Falls back to the most expensive model (best) if model is unknown or None.
    """
    if speech_model_used is None:
        return transcript_prices_by_minute['assemblyai_best']
    key = _ASSEMBLYAI_MODEL_PRICE_MAP.get(speech_model_used, 'assemblyai_best')
    return transcript_prices_by_minute[key]


def transcript(transcript_file_local: str, language_code: str = None,
               provider: str = 'assemblyai'):
    """Transcribe audio file. Only AssemblyAI is supported (ADR-011)."""
    if provider == 'assemblyai':
        return transcript_assemblyai(transcript_file_local, language_code)

    return None


def transcript_price(length_sec: int) -> dict[str, float]:
    length_min = math.ceil(length_sec / 60)
    result = {}
    for provider in transcript_prices_by_minute:
        result[provider] = round(round(length_min) * transcript_prices_by_minute[provider], 2)

    return result

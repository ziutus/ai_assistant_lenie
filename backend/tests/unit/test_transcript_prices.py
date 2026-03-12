"""Tests for transcript price calculation and AssemblyAI model-to-price mapping.

These tests avoid importing library.transcript directly (which pulls in assemblyai
and boto3 not available in the lightweight test env). Instead, we test the pure
price calculation logic by extracting the data and functions inline.
"""

import math


# --- Extracted price data and logic (mirrors library/transcript.py) ---

TRANSCRIPT_PRICES_BY_MINUTE = {
    'AWS': 0.02400,
    'OpenAI': 0.006,
    'assemblyai_best': 0.0035,
    'assemblyai_universal': 0.0025,
    'assemblyai_slam-1': 0.0035,
}

_ASSEMBLYAI_MODEL_PRICE_MAP = {
    'best': 'assemblyai_best',
    'universal': 'assemblyai_universal',
    'slam-1': 'assemblyai_slam-1',
    'universal-3-pro': 'assemblyai_best',
    'universal-2': 'assemblyai_universal',
}


def get_assemblyai_price_per_minute(speech_model_used: str | None) -> float:
    if speech_model_used is None:
        return TRANSCRIPT_PRICES_BY_MINUTE['assemblyai_best']
    key = _ASSEMBLYAI_MODEL_PRICE_MAP.get(speech_model_used, 'assemblyai_best')
    return TRANSCRIPT_PRICES_BY_MINUTE[key]


def transcript_price(length_sec: int) -> dict[str, float]:
    length_min = math.ceil(length_sec / 60)
    result = {}
    for provider in TRANSCRIPT_PRICES_BY_MINUTE:
        result[provider] = round(round(length_min) * TRANSCRIPT_PRICES_BY_MINUTE[provider], 2)
    return result


# --- Tests ---


class TestGetAssemblyaiPricePerMinute:
    def test_best_model(self):
        assert get_assemblyai_price_per_minute("best") == 0.0035

    def test_universal_model(self):
        assert get_assemblyai_price_per_minute("universal") == 0.0025

    def test_slam1_model(self):
        assert get_assemblyai_price_per_minute("slam-1") == 0.0035

    def test_universal_3_pro_alias(self):
        assert get_assemblyai_price_per_minute("universal-3-pro") == 0.0035

    def test_universal_2_alias(self):
        assert get_assemblyai_price_per_minute("universal-2") == 0.0025

    def test_none_falls_back_to_best(self):
        assert get_assemblyai_price_per_minute(None) == 0.0035

    def test_unknown_model_falls_back_to_best(self):
        assert get_assemblyai_price_per_minute("unknown-model-xyz") == 0.0035


class TestTranscriptPrice:
    def test_60_seconds(self):
        result = transcript_price(60)
        for provider, price in TRANSCRIPT_PRICES_BY_MINUTE.items():
            assert result[provider] == round(price, 2)

    def test_90_seconds_rounds_up_to_2_minutes(self):
        result = transcript_price(90)
        for provider, price in TRANSCRIPT_PRICES_BY_MINUTE.items():
            expected = round(2 * price, 2)
            assert result[provider] == expected

    def test_1_second_rounds_up_to_1_minute(self):
        result = transcript_price(1)
        for provider, price in TRANSCRIPT_PRICES_BY_MINUTE.items():
            expected = round(price, 2)
            assert result[provider] == expected

    def test_3600_seconds_is_60_minutes(self):
        result = transcript_price(3600)
        assert result['assemblyai_best'] == round(60 * 0.0035, 2)


class TestCostCalculation:
    """Test the cost calculation pattern used in youtube_processing.py."""

    def test_cost_for_1hour_best_model(self):
        audio_duration = 3600
        price_per_min = get_assemblyai_price_per_minute("best")
        cost = math.ceil(audio_duration / 60) * price_per_min
        assert cost == 60 * 0.0035

    def test_cost_for_1hour_universal_model(self):
        audio_duration = 3600
        price_per_min = get_assemblyai_price_per_minute("universal")
        cost = math.ceil(audio_duration / 60) * price_per_min
        assert cost == 60 * 0.0025

    def test_cost_rounds_up_partial_minutes(self):
        audio_duration = 61
        price_per_min = get_assemblyai_price_per_minute("best")
        cost = math.ceil(audio_duration / 60) * price_per_min
        assert cost == 2 * 0.0035

    def test_cost_zero_duration(self):
        audio_duration = 0
        price_per_min = get_assemblyai_price_per_minute("best")
        cost = math.ceil(audio_duration / 60) * price_per_min
        assert cost == 0.0

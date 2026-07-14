from unittest.mock import patch

import pytest

pytest.importorskip("openai")

from library.ai import ai_ask  # noqa: E402


def test_ai_ask_forwards_generation_parameters_to_sherlock_for_bielik():
    with patch(
        "library.api.cloudferro.sherlock.sherlock.sherlock_get_completion"
    ) as mock_completion:
        ai_ask(
            "Extract timeline events",
            model="Bielik-11B-v3.0-Instruct",
            temperature=0.1,
            max_token_count=4000,
        )

    mock_completion.assert_called_once_with(
        "Extract timeline events",
        model="Bielik-11B-v3.0-Instruct",
        temperature=0.1,
        max_tokens=4000,
    )

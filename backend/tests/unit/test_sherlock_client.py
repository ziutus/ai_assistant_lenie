from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from library.api.cloudferro.sherlock.sherlock import REQUEST_TIMEOUT_S, sherlock_get_completion


def test_sherlock_client_has_bounded_request_timeout():
    completion = SimpleNamespace(
        id="chatcmpl-test",
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: completion)),
    )

    with patch("library.api.cloudferro.sherlock.sherlock.load_config") as config, patch(
        "library.api.cloudferro.sherlock.sherlock.OpenAI", return_value=client
    ) as openai:
        config.return_value.require.return_value = "test-key"
        response = sherlock_get_completion("test")

    assert response.response_text == "ok"
    assert openai.call_args.kwargs["timeout"] == REQUEST_TIMEOUT_S


def test_vision_uses_data_url_and_separate_system_message():
    client = MagicMock()
    with patch("library.api.cloudferro.sherlock.sherlock.load_config"), patch(
        "library.api.cloudferro.sherlock.sherlock.OpenAI", return_value=client,
    ):
        sherlock_get_completion("Opis", model="google/gemma-4-31B-it", system_prompt="Tylko obserwacje",
                                image_base64="aGVsbG8=", image_media_type="image/png")
    messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "Tylko obserwacje"}
    assert messages[1]["content"] == [
        {"type": "text", "text": "Opis"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}},
    ]

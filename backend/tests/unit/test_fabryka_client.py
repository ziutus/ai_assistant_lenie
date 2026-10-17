"""Unit tests for library/fabryka_client.py — Basal typed decisions via fabryka.ai."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("requests")

import requests  # noqa: E402

from library.fabryka_client import (  # noqa: E402
    FabrykaError,
    FabrykaNotConfigured,
    FabrykaUnexpectedResponse,
    decide,
    yes_probability,
)

QUESTION = {"match": {"type": "noul", "instructions": "Tekst opisuje dominację rosyjskiej armii."}}


def _response(status=200, body=None):
    resp = MagicMock()
    resp.status_code = status
    resp.ok = status < 400
    resp.json.return_value = body if body is not None else {}
    resp.raise_for_status.return_value = None
    return resp


@pytest.fixture(autouse=True)
def _no_event_recording():
    with patch("library.external_service_events.record_external_service_event"):
        yield


class TestDecide:
    def test_sends_bearer_token_model_and_body(self):
        with patch("library.fabryka_client.requests.post", return_value=_response(body={"ok": 1})) as post:
            with patch("library.fabryka_client._api_key", return_value="key-1"):
                assert decide("tekst", QUESTION) == {"ok": 1}
        args, kwargs = post.call_args
        assert args[0] == "https://fabryka.ai/v1/systemone"
        assert kwargs["headers"] == {"Authorization": "Bearer key-1"}
        assert kwargs["json"] == {"model": "basal-1.5-mini", "state": "tekst", "questions": QUESTION}

    def test_missing_key_raises(self):
        with patch("library.fabryka_client._api_key", return_value=None):
            with pytest.raises(FabrykaNotConfigured):
                decide("tekst", QUESTION)

    @pytest.mark.parametrize("status", [401, 403])
    def test_rejected_key_raises(self, status):
        with patch("library.fabryka_client.requests.post", return_value=_response(status=status)):
            with patch("library.fabryka_client._api_key", return_value="key-1"):
                with pytest.raises(FabrykaError, match=str(status)):
                    decide("tekst", QUESTION)

    def test_transport_error_wrapped(self):
        with patch("library.fabryka_client.requests.post", side_effect=requests.ConnectionError("boom")):
            with patch("library.fabryka_client._api_key", return_value="key-1"):
                with pytest.raises(FabrykaError):
                    decide("tekst", QUESTION)

    def test_invalid_json_wrapped(self):
        resp = _response()
        resp.json.side_effect = ValueError("bad json")
        with patch("library.fabryka_client.requests.post", return_value=resp):
            with patch("library.fabryka_client._api_key", return_value="key-1"):
                with pytest.raises(FabrykaError):
                    decide("tekst", QUESTION)

    def test_rejects_empty_and_too_many_questions(self):
        with pytest.raises(ValueError):
            decide("tekst", {})
        too_many = {f"q{i}": {"type": "noul", "instructions": "x"} for i in range(9)}
        with pytest.raises(ValueError):
            decide("tekst", too_many)

    def test_rejects_bad_instructions(self):
        with pytest.raises(ValueError):
            decide("tekst", {"q": {"type": "noul", "instructions": ""}})
        with pytest.raises(ValueError):
            decide("tekst", {"q": {"type": "noul", "instructions": "x" * 2001}})


class TestYesProbability:
    def _call(self, body):
        with patch("library.fabryka_client.decide", return_value=body):
            return yes_probability("tekst", "stwierdzenie")

    def test_answer_keyed_by_question_name(self):
        assert self._call({"answers": {"match": {"probability": 0.87}}}) == 0.87

    def test_flat_keyed_by_question_name(self):
        assert self._call({"match": {"noul": 0.2}}) == 0.2

    def test_nested_fallback(self):
        assert self._call({"result": [{"p_yes": 1}]}) == 1.0

    def test_unrecognised_shape_raises(self):
        with pytest.raises(FabrykaUnexpectedResponse):
            self._call({"match": {"label": "yes"}})

    def test_out_of_range_numbers_ignored(self):
        with pytest.raises(FabrykaUnexpectedResponse):
            self._call({"match": {"probability": 7}})

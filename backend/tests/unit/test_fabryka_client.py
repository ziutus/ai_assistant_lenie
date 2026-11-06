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


@pytest.mark.parametrize("field", ["choice", "answer", "value", "label", "selected"])
def test_choose_named_answers(field):
    from library.fabryka_client import choose

    answer = {field: "kraj", "confidence": 0.9}
    with patch("library.fabryka_client.decide", return_value={"answers": {"sense": answer}}) as call:
        assert choose("tekst", "Rozstrzygnij", {"kraj": "Państwo", "osoba": "Osoba"}) == ("kraj", answer)
    assert call.call_args.args[1] == {"sense": {
        "type": "choice", "instructions": "Rozstrzygnij", "criteria": {"kraj": "Państwo", "osoba": "Osoba"},
    }}


def test_choose_probabilities():
    from library.fabryka_client import choose

    answer = {"probabilities": {"osoba": 0.2, "kraj": 0.8}}
    with patch("library.fabryka_client.decide", return_value={"answers": {"sense": answer}}):
        assert choose({}, "Instrukcja", {"osoba": "Osoba", "kraj": "Kraj"}) == ("kraj", answer)


@pytest.mark.parametrize("payload", [None, [], {}, {"answers": None}, {"answers": []}])
def test_choose_rejects_malformed_envelope(payload):
    from library.fabryka_client import choose

    with patch("library.fabryka_client.decide", return_value=payload):
        with pytest.raises(FabrykaUnexpectedResponse):
            choose({}, "Instrukcja", {"kraj": "Kraj"})


def test_choose_warning_payload_is_bounded(caplog):
    from library.fabryka_client import choose

    payload = {"unexpected": "x" * 2000}
    with patch("library.fabryka_client.decide", return_value=payload):
        with pytest.raises(FabrykaUnexpectedResponse):
            choose({}, "Instrukcja", {"kraj": "Kraj"})
    assert caplog.records[-1].args == (repr(payload)[:500],)


@pytest.mark.parametrize("answer", [None, [], "kraj", {}, {"value": ["kraj"]}, {"choice": "unknown"},
                                   {"probabilities": {"kraj": True}}, {"probabilities": {"kraj": float("nan")}},
                                   {"probabilities": {"unknown": 1}}, {"probabilities": {"kraj": "0.9"}}])
def test_choose_rejects_unknown_answers(answer, caplog):
    from library.fabryka_client import choose

    with patch("library.fabryka_client.decide", return_value={"answers": {"sense": answer}}):
        with pytest.raises(FabrykaUnexpectedResponse):
            choose({}, "Instrukcja", {"kraj": "Kraj"})
    assert "Unrecognised Fabryka choice response" in caplog.text


@pytest.mark.parametrize("status,exception", [(429, "FabrykaRateLimited"), (502, "FabrykaUnavailable"),
                                             (503, "FabrykaUnavailable"), (504, "FabrykaUnavailable")])
def test_typed_http_failures(status, exception):
    from library import fabryka_client

    with patch.object(fabryka_client, "_api_key", return_value="test"), patch.object(
        fabryka_client.requests, "post", return_value=_response(status=status),
    ):
        with pytest.raises(getattr(fabryka_client, exception)):
            decide("tekst", QUESTION)


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

    def test_live_response_shape(self):
        body = {"model": "basal-1.5-mini", "answers": {"match": {"type": "noul", "noul": 0.976,
                "probabilities": {"true": 0.976, "false": 0.024}, "confidence": 0.976}}}
        assert self._call(body) == 0.976

    @pytest.mark.parametrize("body", [{}, {"answers": {}}, {"answers": {"match": {"noul": 7}}},
                                      {"answers": {"match": {"noul": True}}}])
    def test_unrecognised_shape_raises(self, body):
        with pytest.raises(FabrykaUnexpectedResponse):
            self._call(body)


@pytest.fixture
def router_config(monkeypatch):
    config = {"OPENROUTER_ENABLED": True, "OPENROUTER_API_KEY": "router-key"}
    monkeypatch.setattr("library.config_loader.load_config", lambda: config)
    return config


@pytest.mark.parametrize("confidence", [0.91, 1])
@pytest.mark.parametrize("explicit_choice", [True, False])
def test_openrouter_choice_protocol_and_usage(router_config, confidence, explicit_choice):
    from library import fabryka_client as client

    answer = {"type": "choice", "confidence": confidence, "probabilities": {"kraj": 0.9, "osoba": 0.1}}
    if explicit_choice:
        answer["choice"] = "kraj"
    usage = {"input_tokens": 100, "output_tokens": 0, "cost": 0.00002}
    body = {"id": "id", "model": "typesafe/jev-1.13", "provider": "test",
            "answers": {"sense": answer}, "usage": usage}
    with patch.object(client.requests, "post", return_value=_response(body=body)) as post, patch.object(
        client, "observed_request", wraps=client.observed_request,
    ) as observed:
        selected, raw = client.choose_openrouter("text", "Choose", {"kraj": "Country", "osoba": "Person"},
                                                  "typesafe/jev-1.13")
    assert selected == "kraj"
    assert raw == {**answer, "usage": usage}
    assert "usage" not in answer
    assert post.call_args.args == (client.OPENROUTER_DECISIONS_URL,)
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer router-key"}
    assert post.call_args.kwargs["json"] == {"model": "typesafe/jev-1.13", "state": "text", "questions": {
        "sense": {"type": "choice", "instructions": "Choose", "criteria": {"kraj": "Country", "osoba": "Person"}}}}
    assert observed.call_args.kwargs["service"] == "openrouter_decisions"
    assert observed.call_args.kwargs["operation"] == "decisions"


@pytest.mark.parametrize("status,exception", [(429, "FabrykaRateLimited"), (502, "FabrykaUnavailable"),
                                             (503, "FabrykaUnavailable"), (504, "FabrykaUnavailable"),
                                             (400, "FabrykaError"), (401, "FabrykaError"), (500, "FabrykaError")])
def test_openrouter_http_failures(router_config, status, exception):
    from library import fabryka_client as client

    response = _response(status=status)
    response.raise_for_status.side_effect = requests.HTTPError(str(status))
    with patch.object(client.requests, "post", return_value=response):
        with pytest.raises(getattr(client, exception)):
            client.choose_openrouter("text", "Choose", {"kraj": "Country"}, "model")


@pytest.mark.parametrize("enabled,key", [(False, "key"), ("false", "key"), ("0", "key"), (True, "")])
def test_openrouter_not_configured_never_requests(router_config, enabled, key):
    from library import fabryka_client as client

    router_config.update(OPENROUTER_ENABLED=enabled, OPENROUTER_API_KEY=key)
    with patch.object(client.requests, "post") as post:
        with pytest.raises(FabrykaNotConfigured):
            client.choose_openrouter("text", "Choose", {"kraj": "Country"}, "model")
    post.assert_not_called()


def test_openrouter_unexpected_response(router_config):
    from library import fabryka_client as client

    with patch.object(client.requests, "post", return_value=_response(body={"answers": {"sense": {}}})):
        with pytest.raises(FabrykaUnexpectedResponse):
            client.choose_openrouter("text", "Choose", {"kraj": "Country"}, "model")

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from library.db.models import DocumentInformationSource
from library.information_provenance import (
    _json_array,
    extract_information_sources,
    extract_known_reporting_sources,
    publisher_domain,
    refresh_document_information_sources,
)


def test_json_array_recovers_complete_objects_from_truncated_response():
    raw = ('[{"canonical_name": "The Guardian", "role": "cited", "confidence": 90},\n'
           '{"canonical_name": "MSZ", "role": "data_source", "confidence": 85},\n'
           '{"canonical_name": "World Population')

    result = _json_array(raw)

    assert [item["canonical_name"] for item in result] == ["The Guardian", "MSZ"]


def test_json_array_raises_when_nothing_recoverable():
    with pytest.raises(ValueError):
        _json_array('Model odpowiedział prozą, bez JSON-a.')


def test_publisher_domain_normalizes_www():
    assert publisher_domain("https://www.money.pl/a/b.html") == "money.pl"


def test_known_nyt_reporting_is_detected_from_grounded_attribution():
    text = ('Dziennik "New York Times" ujawnił, że w Tokio działa jednostka GRU. '
            'W innym miejscu wspomniano NYT bez przypisania ustaleń.')

    result = extract_known_reporting_sources(text)

    assert result == [{
        "canonical_name": "The New York Times",
        "raw_mention": "New York Times",
        "role": "original_reporting",
        "source_type": "newspaper",
        "domain": "nytimes.com",
        "evidence_excerpt": 'Dziennik "New York Times" ujawnił, że w Tokio działa jednostka GRU.',
        "confidence": 100,
        "extraction_method": "rule",
    }]


def test_known_nyt_bare_mention_is_not_enough():
    assert extract_known_reporting_sources("Czytam dziś New York Times.") == []


def test_llm_sources_are_grounded_and_roles_validated():
    text = 'Ustalenia ujawnił dziennik "The Wall Street Journal". Inne zdanie.'
    payload = [
        {
            "canonical_name": "The Wall Street Journal",
            "raw_mention": "The Wall Street Journal",
            "role": "original_reporting",
            "source_type": "newspaper",
            "domain": None,
            "evidence_excerpt": 'Ustalenia ujawnił dziennik "The Wall Street Journal".',
            "confidence": 95,
        },
        {
            "canonical_name": "Invented News",
            "raw_mention": "Invented News",
            "role": "cited",
            "source_type": "portal",
            "domain": None,
            "evidence_excerpt": "Nieistniejący cytat",
            "confidence": 99,
        },
    ]
    response = SimpleNamespace(response_text=json.dumps(payload), prompt_tokens=10)

    with patch("library.chunk_llm_analysis.call_model", return_value=(response.response_text, 10)):
        result = extract_information_sources(text, "Tytuł", "model")

    assert len(result) == 1
    assert result[0]["canonical_name"] == "The Wall Street Journal"
    assert result[0]["role"] == "original_reporting"


def test_refresh_always_adds_publisher_and_llm_sources():
    session = MagicMock()
    doc = SimpleNamespace(id=9245, url="https://www.money.pl/test.html", title="Tytuł")
    publisher = SimpleNamespace(id=1, canonical_name="money.pl")
    wsj = SimpleNamespace(id=2, canonical_name="The Wall Street Journal")
    candidate = {
        "canonical_name": "The Wall Street Journal",
        "raw_mention": "WSJ",
        "role": "original_reporting",
        "source_type": "newspaper",
        "domain": None,
        "evidence_excerpt": "WSJ ustalił",
        "confidence": 95,
    }

    with patch("library.information_provenance._get_or_create_source", side_effect=[publisher, wsj]), \
            patch("library.information_provenance.extract_information_sources", return_value=[candidate]):
        result = refresh_document_information_sources(session, doc, "WSJ ustalił", "model")

    links = [call.args[0] for call in session.add.call_args_list
             if isinstance(call.args[0], DocumentInformationSource)]
    assert [(link.source_id, link.role) for link in links] == [
        (1, "publisher"), (2, "original_reporting"),
    ]
    assert result["sources"] == [
        ("money.pl", "publisher"),
        ("The Wall Street Journal", "original_reporting"),
    ]


def test_refresh_keeps_rule_source_when_llm_extraction_fails():
    session = MagicMock()
    doc = SimpleNamespace(id=9242, url="https://wiadomosci.gazeta.pl/test.html", title="Tytuł")
    publisher = SimpleNamespace(id=1, canonical_name="wiadomosci.gazeta.pl")
    nyt = SimpleNamespace(id=2, canonical_name="The New York Times")
    text = 'Dziennik "New York Times" ujawnił nowe informacje.'

    with patch("library.information_provenance._get_or_create_source", side_effect=[publisher, nyt]), \
            patch("library.information_provenance.extract_information_sources", side_effect=RuntimeError):
        result = refresh_document_information_sources(session, doc, text, "model")

    links = [call.args[0] for call in session.add.call_args_list
             if isinstance(call.args[0], DocumentInformationSource)]
    assert [(link.source_id, link.role, link.extraction_method) for link in links] == [
        (1, "publisher", "url"),
        (2, "original_reporting", "rule"),
    ]
    assert result["sources"][-1] == ("The New York Times", "original_reporting")


def test_refresh_deduplicates_nyt_rule_and_llm_name_variant():
    session = MagicMock()
    doc = SimpleNamespace(id=9242, url="https://wiadomosci.gazeta.pl/test.html", title="Tytuł")
    publisher = SimpleNamespace(id=1, canonical_name="wiadomosci.gazeta.pl")
    nyt = SimpleNamespace(id=2, canonical_name="The New York Times")
    llm_candidate = {
        "canonical_name": "New York Times",
        "raw_mention": "NYT",
        "role": "original_reporting",
        "source_type": "newspaper",
        "domain": None,
        "evidence_excerpt": "NYT podał nowe informacje.",
        "confidence": 95,
    }
    text = 'Dziennik "New York Times" ujawnił nowe informacje. NYT podał nowe informacje.'

    with patch("library.information_provenance._get_or_create_source",
               side_effect=[publisher, nyt, nyt]), \
            patch("library.information_provenance.extract_information_sources",
                  return_value=[llm_candidate]):
        refresh_document_information_sources(session, doc, text, "model")

    links = [call.args[0] for call in session.add.call_args_list
             if isinstance(call.args[0], DocumentInformationSource)]
    assert [(link.source_id, link.role) for link in links] == [
        (1, "publisher"),
        (2, "original_reporting"),
    ]

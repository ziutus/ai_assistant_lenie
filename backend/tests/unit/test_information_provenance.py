import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from library.db.models import DocumentInformationSource
from library.information_provenance import (
    extract_information_sources,
    publisher_domain,
    refresh_document_information_sources,
)


def test_publisher_domain_normalizes_www():
    assert publisher_domain("https://www.money.pl/a/b.html") == "money.pl"


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

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from library.author_biography import (
    decide_biography_review,
    extract_trailing_author_biography,
    process_author_biography,
)
from library.db.models import DocumentPerson, Person


BIO = (
    "Jacek Losik dziennikarzem jest od 2014 r. Zaczynał po studiach "
    "w Dzienniku Łódzkim. W money.pl zajmuje się inwestycjami "
    "infrastrukturalnymi oraz transportem."
)


def test_extracts_known_author_biography_from_document_tail():
    text = ("Treść artykułu. " * 80) + "\n\n## Rozdział\n\nDalsza treść.\n\n" + BIO + "\n\nThe Wall Street Journal"

    body, excerpt = extract_trailing_author_biography(text, "Jacek Losik")

    assert body.endswith("Dalsza treść.")
    assert excerpt == BIO


def test_does_not_extract_author_mention_without_biographical_language():
    text = ("Treść artykułu. " * 80) + "\n\nJacek Losik opisał najnowszy raport."

    body, excerpt = extract_trailing_author_biography(text, "Jacek Losik")

    assert body == text
    assert excerpt is None


def test_extracts_split_portal_biography_and_trailing_footer():
    text = (
        ("Treść artykułu. " * 80)
        + "\n\nOstatni akapit właściwej treści."
        + "\n\nŁukasz Maziewski, Dziennikarz o2.pl"
        + "\n\nDziennikarz o2.pl"
        + "\n\nZainteresowany bezpieczeństwem. Zajmował się problematyką przez siedem lat "
          "w Fakcie, a od 2021 r. w Wirtualnej Polsce."
        + "\n\nLukasz.Maziewski@grupawp.pl"
        + "\n\ntarcza antyrakietowa przemysł obronny"
    )

    body, excerpt = extract_trailing_author_biography(text, "Łukasz Maziewski")

    assert body.endswith("Ostatni akapit właściwej treści.")
    assert excerpt.startswith("Łukasz Maziewski, Dziennikarz o2.pl")
    assert "Zajmował się problematyką" in excerpt
    assert excerpt.endswith("tarcza antyrakietowa przemysł obronny")


def test_split_layout_still_requires_known_author_name():
    text = (
        ("Treść artykułu. " * 80)
        + "\n\nJan Kowalski, Dziennikarz"
        + "\n\nOd 2021 r. pracuje w redakcji i zajmuje się gospodarką."
    )

    body, excerpt = extract_trailing_author_biography(text, "Anna Nowak")

    assert body == text
    assert excerpt is None


def test_first_biography_fills_empty_person_description():
    person = Person(canonical_name="Jacek Losik", description=None)
    person.id = 236
    link = DocumentPerson(
        id=244, document_id=9245, person_id=236, raw_mention="Jacek Losik",
        confidence="manual_review",
    )
    session = MagicMock()
    session.execute.return_value.scalars.return_value.first.return_value = link
    doc = SimpleNamespace(id=9245, byline="Jacek Losik")
    result = {"decision": "auto_applied", "proposed_description": "Polski dziennikarz."}

    with patch("library.person_registry.find_by_alias", return_value=person), \
            patch("library.author_biography._evaluate_biography", return_value=result):
        summary = process_author_biography(session, doc, BIO, "model")

    assert summary == {"person_id": 236, "status": "auto_applied"}
    assert person.description == "Polski dziennikarz."
    assert link.role == "author"
    assert link.source_excerpt == BIO
    assert link.bio_review_result == result


def test_new_information_is_queued_without_overwriting_description():
    person = Person(canonical_name="Jacek Losik", description="Dziennikarz money.pl.")
    person.id = 236
    link = DocumentPerson(
        id=244, document_id=9245, person_id=236, raw_mention="Jacek Losik",
        confidence="alias_matched",
    )
    session = MagicMock()
    session.execute.return_value.scalars.return_value.first.return_value = link
    doc = SimpleNamespace(id=9245, byline="Jacek Losik")
    result = {
        "decision": "new_information",
        "proposed_description": "Dziennikarz money.pl specjalizujący się w transporcie.",
    }

    with patch("library.person_registry.find_by_alias", return_value=person), \
            patch("library.author_biography._evaluate_biography", return_value=result):
        process_author_biography(session, doc, BIO, "model")

    assert person.description == "Dziennikarz money.pl."
    assert link.bio_review_status == "needs_review"


def test_approve_review_applies_proposed_description():
    person = Person(canonical_name="Jacek Losik", description="Stary opis")
    person.id = 236
    link = DocumentPerson(
        id=244, document_id=9245, person_id=236, raw_mention="Jacek Losik",
        confidence="alias_matched", bio_review_status="needs_review",
        bio_review_result={"proposed_description": "Nowy opis"},
    )
    link.person = person

    result = decide_biography_review(link, "approve")

    assert person.description == "Nowy opis"
    assert link.bio_review_status == "approved"
    assert link.bio_reviewed_at is not None
    assert result["status"] == "approved"

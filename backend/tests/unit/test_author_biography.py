from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from library.author_biography import (
    decide_biography_review,
    extract_trailing_author_biography,
    process_author_biography,
    split_author_block,
)
from library.db.models import DocumentPerson, Person


BIO = (
    "Jacek Losik dziennikarzem jest od 2014 r. Zaczynał po studiach "
    "w Dzienniku Łódzkim. W money.pl zajmuje się inwestycjami "
    "infrastrukturalnymi oraz transportem."
)


PORTAL_TAIL = """[img2: Mateusz Cieślak]\x20

Newsy, wywiady, śledztwa i reportaże w Twojej skrzynce co tydzień - zawsze za darmo.

Tetiana Kolesnychenko Dziennikarka
Dziennikarka
[img3: Tetiana Kolesnychenko]
Tetiana Kolesnychenko Dziennikarka

Dziennikarka Magazynu Wirtualnej Polski, specjalizująca się w tematyce Europy Wschodniej. Od 2022 roku relacjonuje wojnę w Ukrainie.
Dwukrotna laureatka Nagrody im. Dariusza Fikusa za dziennikarstwo najwyższej próby (2024 i 2025), laureatka Grand Press oraz Festiwalu Wrażliwego.
Nominowana do Nagrody im. Teresy Torańskiej oraz Melchiorów Polskiego Radia.

tetiana.kolesnychenko@grupawp.plwięcej o autorze
"""


@pytest.mark.parametrize("separator", ["", " "])
def test_split_author_block_document_11242(separator):
    text = "Treść artykułu. " * 80 + "\n\n" + PORTAL_TAIL.replace(".plwięcej", f".pl{separator}więcej")
    body, block = split_author_block(text)
    assert body.endswith("co tydzień - zawsze za darmo.")
    assert "[img2: Mateusz Cieślak]" in body
    assert block.startswith("Tetiana Kolesnychenko Dziennikarka")
    assert block.endswith("więcej o autorze")
    assert text.startswith(body)


@pytest.mark.parametrize("text", [
    "Treść artykułu.\nJan Kowalski Dziennikarz",
    "Treść artykułu.\nOpis bez nazwiska.\nx@example.pl o autorze",
    "Jan Kowalski Dziennikarz\n" + "Dalszy akapit.\n" * 15 + "x@example.pl o autorze",
    "W artykule dziennikarka omawia raport.\n" + "Dalszy akapit.\n" * 20 + "x@example.pl o autorze",
    "Jan Kowalski Dziennikarz\nx@example.pl o autorze\nraz\ndwa\ntrzy\ncztery",
    "Jan Kowalski Dziennikarz\nx@example.pl o autorze\n" + "x" * 121,
    "Jan Kowalski Dziennikarzem\nx@example.pl o autorze",
    "jan Kowalski Dziennikarz\nx@example.pl o autorze",
])
def test_split_author_block_keeps_unconfirmed_footer(text):
    assert split_author_block(text) == (text, None)


def test_split_author_block_accepts_image_role_and_three_short_footer_lines():
    block = "[img3: Łukasz Żak] Łukasz Żak, rEpOrTeR\nOpis.\nx@example.pl o autorze\nraz\ndwa\ntrzy"
    text = "Treść.\n\n" + block
    assert split_author_block(text) == ("Treść.", block)


def test_split_author_block_uses_last_marker_and_fifteen_nonempty_lines():
    prefix = "Jan Kowalski Autor\nx@example.pl o autorze\n" + "Treść.\n" * 20
    block = "Anna Maria Łucja Żak Ekspertka\n" + "\nOpis.\n" * 14 + "y@example.pl więcej o autorze"
    assert split_author_block(prefix + block) == (prefix.rstrip(), block)


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

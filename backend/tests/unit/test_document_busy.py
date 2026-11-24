"""Per-document exclusion between the paragraph split and the detections."""
import pytest

from library.document_busy import DocumentBusy, busy_response, claim_document


def test_second_claim_on_the_same_document_is_refused_and_names_the_holder():
    with claim_document(7, "podział na akapity"):
        with pytest.raises(DocumentBusy) as caught:
            with claim_document(7, "wykrywanie encji (NER)"):
                pytest.fail("the second claim must not be granted")
    assert caught.value.holder == "podział na akapity"


def test_other_documents_are_independent():
    with claim_document(1, "a"):
        with claim_document(2, "b"):
            pass


def test_claim_is_released_after_success_and_after_an_error():
    with claim_document(3, "a"):
        pass
    with pytest.raises(RuntimeError):
        with claim_document(3, "b"):
            raise RuntimeError("boom")
    with claim_document(3, "c"):
        pass


def test_busy_response_is_a_409_with_the_holder():
    body, status = busy_response(DocumentBusy("analiza geopolityczna"))
    assert status == 409
    assert body["status"] == "error" and body["busy_with"] == "analiza geopolityczna"
    assert "analiza geopolityczna" in body["message"]

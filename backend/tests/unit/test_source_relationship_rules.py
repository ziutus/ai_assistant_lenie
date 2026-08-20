from library.information_provenance import analyze_source_relationships


QUOTE = (
    "W komunikacie EDF poinformował, że w elektrowni jądrowej Gravelines "
    "na północy Francji doszło do nieplanowanych wyłączeń po tym, jak meduzy "
    "zatkały pompy wykorzystywane do chłodzenia reaktorów - podają France24 "
    "oraz agencja AFP."
)


def test_statement_reported_by_outlets_is_resolved_without_llm(monkeypatch):
    """The explicit 'EDF poinformował ... podają France24 i AFP' form is a rule."""
    def llm_must_not_be_called(*_args, **_kwargs):
        raise AssertionError("LLM must not be called when the deterministic rule matches")

    monkeypatch.setattr("library.chunk_llm_analysis.call_model", llm_must_not_be_called)

    result = analyze_source_relationships(
        QUOTE,
        "Bielik-11B-v3.0-Instruct",
        ["EDF", "France24", "AFP", "wp.pl"],
    )

    assert [(relation["subject"], relation["predicate"], relation["object"])
            for relation in result] == [
        ("EDF", "issued_statement", "France24"),
        ("EDF", "issued_statement", "AFP"),
    ]
    assert all(relation["confidence"] == 95 for relation in result)

"""Unit tests for chapter-aware chunk splitting of YouTube transcripts.

youtube_processing.py inserts each video chapter's title as a standalone
line at the start of its block (text_transcript.py:_append_with_chapters).
document_analysis_service._chapter_chunks_from_text() reuses those
boundaries instead of blindly cutting every chunk_size characters — see
document_analysis_service.py step 7 (transcript mode).

LLM calls and DB access are mocked — verifies splitting/routing only.
"""

from unittest.mock import MagicMock

import pytest

import library.chunk_llm_analysis as llm
import library.document_analysis_service as das
from library.db.models import DocumentChunk
from library.document_analysis_service import DocumentAnalysisService, _chapter_chunks_from_text


CHAPTER_TITLES = ["Wstęp", "USA bombardują Iran", "Trump na szczycie NATO"]

TRANSCRIPT_TEXT = (
    "Wstęp\n" + "Zdanie wstępu. " * 20 + "\n\n"
    "USA bombardują Iran\n" + "Zdanie o Iranie. " * 20 + "\n\n"
    "Trump na szczycie NATO\n" + "Zdanie o NATO. " * 20
)

CHAPTER_LIST_TEXT = "00:00 Wstęp\n00:42 USA bombardują Iran\n13:17 Trump na szczycie NATO"


class TestChapterChunksFromText:
    def test_accepts_markdown_source_chapter_headings(self):
        text = (
            f"## {CHAPTER_TITLES[0]}\nPierwsza czÄ™Ĺ›Ä‡.\n\n"
            f"## {CHAPTER_TITLES[1]}\nDruga czÄ™Ĺ›Ä‡.\n\n"
            f"## {CHAPTER_TITLES[2]}\nTrzecia czÄ™Ĺ›Ä‡."
        )
        chunks = _chapter_chunks_from_text(text, CHAPTER_TITLES, chunk_size=5000)
        assert chunks == [
            f"## {CHAPTER_TITLES[0]}\nPierwsza czÄ™Ĺ›Ä‡.",
            f"## {CHAPTER_TITLES[1]}\nDruga czÄ™Ĺ›Ä‡.",
            f"## {CHAPTER_TITLES[2]}\nTrzecia czÄ™Ĺ›Ä‡.",
        ]

    def test_splits_at_chapter_boundaries(self):
        chunks = _chapter_chunks_from_text(TRANSCRIPT_TEXT, CHAPTER_TITLES, chunk_size=5000)
        assert chunks is not None
        assert len(chunks) == 3
        assert chunks[0].startswith("Wstęp")
        assert chunks[1].startswith("USA bombardują Iran")
        assert chunks[2].startswith("Trump na szczycie NATO")

    def test_returns_none_when_titles_absent(self):
        chunks = _chapter_chunks_from_text("Zwykły tekst bez rozdziałów. " * 30, CHAPTER_TITLES, chunk_size=5000)
        assert chunks is None

    def test_returns_none_below_half_threshold(self):
        # Only 1 of 3 known titles actually present in the text
        text = "Wstęp\n" + "Treść. " * 20
        chunks = _chapter_chunks_from_text(text, CHAPTER_TITLES, chunk_size=5000)
        assert chunks is None

    def test_empty_chapter_titles_returns_none(self):
        assert _chapter_chunks_from_text(TRANSCRIPT_TEXT, [], chunk_size=5000) is None

    def test_rebalances_a_chapter_marker_landing_mid_sentence(self):
        # Video chapters are timestamp-based (often set by hand by the
        # author) and don't have to land on a sentence boundary — the
        # marker here interrupts "Witam i zapraszam..." right after "i".
        text = (
            "Wstęp\nDzień dobry. Witam i\n\n"
            + "USA bombardują Iran\n zapraszam na program o Iranie.\n"
            + "Zdanie o Iranie. " * 20
            + "\n\n"
            + "Trump na szczycie NATO\n" + "Zdanie o NATO. " * 20
        )
        chunks = _chapter_chunks_from_text(text, CHAPTER_TITLES, chunk_size=5000)

        assert chunks is not None
        assert chunks[0] == "Wstęp\nDzień dobry. Witam i zapraszam na program o Iranie."
        assert chunks[1].startswith("USA bombardują Iran\nZdanie o Iranie.")
        assert "zapraszam" not in chunks[1]

    def test_rebalances_when_the_heading_is_its_own_blank_line_separated_block(self):
        # Caught live on doc 8790: youtube_processing.py had put a blank line
        # on BOTH sides of the "## Title" heading, so it lands as its own
        # block (title_set membership, not a "#"-prefix check, is what makes
        # block_title() recognize it) — a naive body = lines[1] after
        # splitting on the first "\n" would have swallowed the whole heading
        # into "body" instead of recognizing it as the heading.
        text = (
            "## Wstęp\n\nDzień dobry. Witam i\n\n"
            + "## USA bombardują Iran\n\n zapraszam na program o Iranie.\n"
            + "Zdanie o Iranie. " * 20
            + "\n\n"
            + "## Trump na szczycie NATO\n\n" + "Zdanie o NATO. " * 20
        )
        chunks = _chapter_chunks_from_text(text, CHAPTER_TITLES, chunk_size=5000)

        assert chunks is not None
        assert chunks[0] == "## Wstęp\n\nDzień dobry. Witam i zapraszam na program o Iranie."
        assert chunks[1].startswith("## USA bombardują Iran\nZdanie o Iranie.")
        assert "zapraszam" not in chunks[1]

    def test_does_not_touch_a_marker_that_already_lands_on_a_sentence_boundary(self):
        chunks = _chapter_chunks_from_text(TRANSCRIPT_TEXT, CHAPTER_TITLES, chunk_size=5000)
        assert chunks == [
            "Wstęp\n" + "Zdanie wstępu. " * 20,
            "USA bombardują Iran\n" + "Zdanie o Iranie. " * 20,
            "Trump na szczycie NATO\n" + "Zdanie o NATO. " * 20,
        ]

    def test_oversized_chapter_gets_subsplit(self):
        long_text = (
            "Wstęp\n" + "Zdanie wstępu. " * 20 + "\n\n"
            "USA bombardują Iran\n" + "Zdanie o Iranie. " * 500 + "\n\n"
            "Trump na szczycie NATO\n" + "Zdanie o NATO. " * 20
        )
        chunks = _chapter_chunks_from_text(long_text, CHAPTER_TITLES, chunk_size=2000)
        assert chunks is not None
        assert len(chunks) > 3
        assert chunks[0].startswith("Wstęp")
        assert any(c.startswith("USA bombardują Iran") for c in chunks)
        assert chunks[-1].startswith("Trump na szczycie NATO")


class FakeYoutubeDoc:
    id = 9216
    title = "Testowy film z rozdziałami"
    text = TRANSCRIPT_TEXT
    text_md = None
    text_raw = None
    chapter_list = CHAPTER_LIST_TEXT
    tags = None


@pytest.fixture
def session():
    s = MagicMock()
    s.added = []
    s.add.side_effect = s.added.append
    return s


@pytest.fixture
def transcript_env(monkeypatch, session):
    monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: FakeYoutubeDoc()))

    def fake_transcript(text, model, position=1, total=1, speakers=None, prev_context="", next_context=""):
        return {
            "type": "TEMAT", "topic": f"temat {position}",
            "corrected_text": None, "summary": f"streszczenie {position}",
            "rewrite_ratio": None,
        }

    monkeypatch.setattr(llm, "analyze_chunk", fake_transcript)
    monkeypatch.setattr(das, "_merge_topics", lambda sections, model, mode="transcript": [])
    monkeypatch.setattr(das, "_synthesize", lambda sections, title, model, mode="transcript": "")
    monkeypatch.setattr("library.search_terms.generate_search_terms", lambda text, title: [])
    monkeypatch.setattr("library.article_tagging.tag_article_with_llm", lambda text, title: [])
    monkeypatch.setattr("library.article_tagging.extract_countries_hybrid", lambda text, title: [])
    monkeypatch.setattr("library.entity_service.refresh_document_entities", lambda session, doc_id, text: [])
    monkeypatch.setattr("library.place_verification.verify_document_places", lambda session, doc, text: {"resolved": [], "tagged": []})
    monkeypatch.setattr("library.person_registry.resolve_document_persons", lambda session, doc, text: {"linked": [], "skipped": []})
    monkeypatch.setattr("library.information_provenance.refresh_document_information_sources", lambda session, doc, text, model: {"sources": []})
    return session


class TestCreateRunUsesChapterSplit:
    def test_chunk_count_matches_video_chapters(self, transcript_env):
        service = DocumentAnalysisService(transcript_env)
        run = service.create_run(doc_id=9216, model="test-model", mode="transcript")

        assert run.mode == "transcript"
        chunks = [o for o in transcript_env.added if isinstance(o, DocumentChunk)]
        assert len(chunks) == 3
        assert chunks[0].original_text.startswith("Wstęp")
        assert chunks[1].original_text.startswith("USA bombardują Iran")
        assert chunks[2].original_text.startswith("Trump na szczycie NATO")

    def test_falls_back_to_sentence_split_without_chapter_list(self, transcript_env, monkeypatch):
        doc = FakeYoutubeDoc()
        doc.chapter_list = None
        monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))

        service = DocumentAnalysisService(transcript_env)
        service.create_run(doc_id=9216, model="test-model", mode="transcript", chunk_size=300)

        chunks = [o for o in transcript_env.added if isinstance(o, DocumentChunk)]
        # Blind char-count split ignores chapter boundaries — more/uneven pieces
        assert len(chunks) > 3

    def test_stray_speaker_marker_does_not_disable_chapter_split(self, transcript_env, monkeypatch):
        # A single ">>" makes speaker_changes > 0 (is_multi_speaker=True), but
        # with fewer than 2 extracted speakers assign_speakers() never runs —
        # the text's block structure survives intact, so there's no reason to
        # fall back to a blind split. split_only=True additionally skips
        # speaker extraction entirely (step 4), which used to leave speakers=[]
        # and, with the old is_multi_speaker-only gate, always blocked the
        # chapter-aware path for any transcript containing a stray ">>".
        doc = FakeYoutubeDoc()
        doc.text = TRANSCRIPT_TEXT.replace("Zdanie o Iranie. ", ">> Zdanie o Iranie. ", 1)
        monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))

        service = DocumentAnalysisService(transcript_env)
        service.create_run(doc_id=9216, model="test-model", mode="transcript", split_only=True)

        chunks = [o for o in transcript_env.added if isinstance(o, DocumentChunk)]
        assert len(chunks) == 3
        assert chunks[0].original_text.startswith("Wstęp")
        assert chunks[1].original_text.startswith("USA bombardują Iran")
        assert chunks[2].original_text.startswith("Trump na szczycie NATO")

    def test_reuses_earlier_ner_without_refreshing_entities(self, transcript_env, monkeypatch):
        def should_not_run(*_args, **_kwargs):
            raise AssertionError("NER must be reused, not rerun")

        monkeypatch.setattr("library.entity_service.refresh_document_entities", should_not_run)
        service = DocumentAnalysisService(transcript_env)

        service.create_run(
            doc_id=9216, model="test-model", mode="transcript",
            reuse_existing_entities=True,
        )


@pytest.mark.parametrize("kind", ["REKLAMA", "SZUM", "ZRODLA"])
@pytest.mark.parametrize("split_only", [False, True])
def test_typed_h2_skips_semantic_analysis(transcript_env, monkeypatch, kind, split_only):
    doc = FakeYoutubeDoc()
    doc.text = "## Własny temat\n" + "Treść merytoryczna. " * 12 + "\n## Wydzielony fragment\n" + "Kup produkt. " * 30
    doc.chapter_types = ["TEMAT", kind]
    monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))
    analyze = MagicMock(return_value={
        "type": "TEMAT", "topic": "Temat z LLM", "corrected_text": "Poprawiona treść.",
        "summary": "Streszczenie.", "rewrite_ratio": 1.0,
    })
    monkeypatch.setattr(llm, "analyze_chunk", analyze)
    service = DocumentAnalysisService(transcript_env)
    service.create_run(9216, "test-model", chunk_size=180, split_only=split_only, no_synthesis=True)
    chunks = [o for o in transcript_env.added if isinstance(o, DocumentChunk)]
    topics = [c for c in chunks if c.type == "TEMAT"]
    excluded = [c for c in chunks if c.type == kind]
    assert topics and len(excluded) > 1
    assert analyze.call_count == (0 if split_only else len(topics))
    assert all("Kup produkt" not in call.args[0] for call in analyze.call_args_list)
    assert all(len(c.original_text) <= 180 for c in chunks)
    assert all(c.status == "approved" and c.topic == "Wydzielony fragment" for c in excluded)
    assert all(c.summary is None and c.corrected_text is None for c in excluded)
    assert all(c.status == "pending" for c in topics)
    assert all(c.summary == (None if split_only else "Streszczenie.") for c in topics)
    # Only the first piece of a chapter carries its heading, as in _chapter_chunks_from_text().
    assert excluded[0].original_text.startswith("## Wydzielony fragment\n")
    assert all(not c.original_text.startswith("##") for c in excluded[1:])


def test_h2_keeps_edited_boundaries_despite_speaker_markers(transcript_env, monkeypatch):
    doc = FakeYoutubeDoc()
    doc.text = "## Treść\n>> Niedokończona wypowiedź " + "słowo " * 20 + "\n## Reklama\n>> Kup teraz. " * 1
    doc.chapter_types = ["TEMAT", "REKLAMA"]
    monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))
    assign = MagicMock(side_effect=AssertionError("Must preserve H2 structure"))
    extract = MagicMock(side_effect=AssertionError("Must not extract speakers from ads"))
    monkeypatch.setattr(llm, "assign_speakers", assign)
    monkeypatch.setattr(llm, "extract_speaker_info", extract)
    DocumentAnalysisService(transcript_env).create_run(
        9216, "test-model", speakers=[{"name": "A"}, {"name": "B"}], no_synthesis=True,
    )
    chunks = [o for o in transcript_env.added if isinstance(o, DocumentChunk)]
    assert len(chunks) == 2
    assert "Kup teraz" not in chunks[0].original_text
    assert chunks[1].type == "REKLAMA"
    assign.assert_not_called()
    extract.assert_not_called()


def test_h2_all_excluded_needs_no_chunk_or_speaker_llm(transcript_env, monkeypatch):
    doc = FakeYoutubeDoc()
    doc.text = "## Reklama\n>> " + "Kup teraz. " * 20
    doc.chapter_types = ["REKLAMA"]
    monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))
    analyze = MagicMock()
    extract = MagicMock()
    grouping = MagicMock()
    monkeypatch.setattr(llm, "analyze_chunk", analyze)
    monkeypatch.setattr(llm, "extract_speaker_info", extract)
    monkeypatch.setattr(das, "_merge_topics", grouping)
    DocumentAnalysisService(transcript_env).create_run(9216, "test-model", chunk_size=100, document_enriched=True)
    analyze.assert_not_called()
    extract.assert_not_called()
    grouping.assert_not_called()


def test_h2_type_count_mismatch_defaults_to_temat(transcript_env, monkeypatch):
    doc = FakeYoutubeDoc()
    doc.text = "## Nowy\n" + "Pierwszy temat. " * 15 + "\n## Kolejny\n" + "Drugi temat. " * 15
    doc.chapter_types = ["REKLAMA"]
    doc.chapter_list = None
    monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))
    DocumentAnalysisService(transcript_env).create_run(9216, "test-model", split_only=True)
    chunks = [o for o in transcript_env.added if isinstance(o, DocumentChunk)]
    assert len(chunks) == 2
    assert all(c.type == "TEMAT" and c.status == "pending" for c in chunks)


def test_no_h2_ignores_chapter_types(transcript_env, monkeypatch):
    doc = FakeYoutubeDoc()
    doc.chapter_types = ["REKLAMA", "SZUM", "ZRODLA"]
    monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))
    DocumentAnalysisService(transcript_env).create_run(9216, "test-model", no_synthesis=True)
    chunks = [o for o in transcript_env.added if isinstance(o, DocumentChunk)]
    assert len(chunks) == 3
    assert all(c.type == "TEMAT" and c.status == "pending" and c.summary for c in chunks)


def test_short_h2_text_is_authoritative(transcript_env, monkeypatch):
    doc = FakeYoutubeDoc()
    doc.text = "## Reklama\nKup teraz."
    doc.text_md = "Stary tekst. " * 20
    doc.chapter_types = ["REKLAMA"]
    monkeypatch.setattr(das.Document, "get_by_id", staticmethod(lambda _s, _id: doc))
    analyze = MagicMock()
    monkeypatch.setattr(llm, "analyze_chunk", analyze)
    DocumentAnalysisService(transcript_env).create_run(9216, "test-model", no_synthesis=True)
    chunks = [o for o in transcript_env.added if isinstance(o, DocumentChunk)]
    assert len(chunks) == 1
    assert chunks[0].type == "REKLAMA"
    assert "Kup teraz" in chunks[0].original_text
    analyze.assert_not_called()


def test_typed_h2_chunks_put_the_heading_only_on_the_first_piece_of_a_long_chapter():
    from library.document_analysis_service import _typed_h2_chunks

    body = " ".join(f"To jest zdanie numer {i} w długim rozdziale." for i in range(1, 40))
    text = f"## Wstęp\n\nKrótki wstęp.\n\n## Długi rozdział\n\n{body}\n\n## Sponsor\n\nKup teraz produkt."

    chunks = _typed_h2_chunks(text, ["TEMAT", "TEMAT", "REKLAMA"], 400)

    long_pieces = [chunk for chunk in chunks if chunk[2] == "Długi rozdział"]
    assert len(long_pieces) > 1
    assert long_pieces[0][0].startswith("## Długi rozdział")
    assert all(not piece[0].startswith("##") for piece in long_pieces[1:])
    assert all(len(piece[0]) <= 400 for piece in long_pieces)
    assert [chunk[1] for chunk in chunks if chunk[2] == "Sponsor"] == ["REKLAMA"]

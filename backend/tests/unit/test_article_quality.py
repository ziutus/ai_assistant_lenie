"""Unit tests for library.article_quality — photo-caption detection and
deterministic quality ("staranność") scoring.

Pure-function tests, no DB/LLM/network (compute_quality tested with model=None).
"""

from library.article_quality import (
    compute_quality,
    count_photo_captions,
    is_clickbait_title,
    is_photo_caption_line,
)

LONG_PARAGRAPH = (
    "To jest długi akapit właściwej treści artykułu, w którym autor rzetelnie "
    "opisuje temat, cytuje ekspertów i przywołuje dane z oficjalnych raportów."
)


class _Doc:
    def __init__(self, author=None, title=None):
        self.author = author
        self.title = title


class TestPhotoCaptionDetection:
    def test_zdjecie_ilustracyjne_with_stock_credit(self):
        assert is_photo_caption_line("zdjęcie ilustracyjne, Dmytro Buiansky / shutterstock")

    def test_fot_prefix(self):
        assert is_photo_caption_line("Fot. Jan Kowalski / PAP")

    def test_agency_only_line(self):
        assert is_photo_caption_line("Getty Images")

    def test_caption_next_to_img_marker(self):
        assert is_photo_caption_line("[img3] Zdjęcie ilustracyjne / East News")

    def test_zrodlo_zdjecia(self):
        assert is_photo_caption_line("Źródło zdjęcia: Unsplash")

    def test_long_caption_ending_with_zdjecie_ilustracyjne(self):
        line = (
            "Chiński rząd nakazał zaprzestanie produkcji aut ośmiu firmom. "
            "Niektóre były pionierami chińskiej motoryzacji (zdjęcie ilustracyjne)"
        )
        assert is_photo_caption_line(line)

    def test_long_paragraph_mentioning_photo_is_not_caption(self):
        text = (
            "Na opublikowanym przez agencję zdjęciu widać skutki wybuchu, a fotograf "
            "Reuters relacjonował wydarzenia z centrum miasta przez kilka kolejnych dni, "
            "dokumentując życie mieszkańców po ostrzale."
        )
        assert not is_photo_caption_line(text)

    def test_regular_sentence_is_not_caption(self):
        assert not is_photo_caption_line(LONG_PARAGRAPH[:100])

    def test_empty_line(self):
        assert not is_photo_caption_line("")

    def test_count_in_text(self):
        text = "\n".join([
            LONG_PARAGRAPH,
            "zdjęcie ilustracyjne, Dmytro Buiansky / shutterstock",
            LONG_PARAGRAPH,
            "Fot. Adam Nowak / East News",
        ])
        assert count_photo_captions(text) == 2

    def test_count_empty_text(self):
        assert count_photo_captions("") == 0


class TestClickbaitTitle:
    def test_clickbait(self):
        assert is_clickbait_title("Nie uwierzysz, co zrobił ten polityk")
        assert is_clickbait_title("Szokujące odkrycie naukowców")

    def test_normal_title(self):
        assert not is_clickbait_title("Rząd przyjął nowelizację ustawy o OZE")

    def test_none_title(self):
        assert not is_clickbait_title(None)


class TestComputeQuality:
    def _sections(self, temat=6, noise=0):
        secs = [{"type": "TEMAT", "original": LONG_PARAGRAPH * 3} for _ in range(temat)]
        secs += [{"type": "SZUM", "original": "Menu | Kontakt | Regulamin"} for _ in range(noise)]
        return secs

    def test_clean_article_scores_100(self):
        doc = _Doc(author="Jan Kowalski", title="Rzetelny tytuł artykułu")
        q = compute_quality(doc, self._sections(), model=None)
        assert q["score"] == 100
        assert q["penalties"] == {}
        assert q["llm_rubric"] is None

    def test_missing_author_penalty(self):
        q = compute_quality(_Doc(title="Tytuł"), self._sections(), model=None)
        assert q["penalties"]["missing_author"] == 10
        assert q["score"] == 90

    def test_photo_caption_penalty_capped(self):
        captions = "\n".join(["Fot. X / shutterstock"] * 5)
        secs = self._sections() + [{"type": "TEMAT", "original": captions}]
        q = compute_quality(_Doc(author="A", title="T"), secs, model=None)
        assert q["penalties"]["photo_captions"] == 15  # cap, nie 25
        assert q["signals"]["photo_captions"] == 5

    def test_noise_share_penalty(self):
        secs = [
            {"type": "TEMAT", "original": "a" * 6000},
            {"type": "SZUM", "original": "b" * 2000},
            {"type": "REKLAMA", "original": "c" * 2000},
        ]
        q = compute_quality(_Doc(author="A", title="T"), secs, model=None)
        # 4000/10000 = 40% szumu → kara 20 (cap)
        assert q["penalties"]["noise_share"] == 20
        assert q["signals"]["noise_share"] == 0.4

    def test_short_text_penalty(self):
        secs = [{"type": "TEMAT", "original": "Krótka notka."}]
        q = compute_quality(_Doc(author="A", title="T"), secs, model=None)
        assert q["penalties"]["short_text"] == 10

    def test_clickbait_title_penalty(self):
        doc = _Doc(author="A", title="Nie uwierzysz, co się stało")
        q = compute_quality(doc, self._sections(), model=None)
        assert q["penalties"]["clickbait_title"] == 5

    def test_score_never_negative(self):
        secs = [
            {"type": "TEMAT", "original": "Fot. A / shutterstock\nFot. B / getty\nFot. C / PAP"},
            {"type": "SZUM", "original": "x" * 100000},
        ]
        q = compute_quality(_Doc(title="Szokujące! Nie uwierzysz"), secs, model=None)
        assert q["score"] >= 0

    def test_result_shape(self):
        q = compute_quality(_Doc(author="A", title="T"), self._sections(), model=None)
        assert set(q) == {"score", "penalties", "signals", "llm_rubric", "model", "computed_at"}
        assert q["model"] is None

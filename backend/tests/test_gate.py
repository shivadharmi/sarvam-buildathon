"""The faithfulness gate is the product. These tests are the specification.

The gate must accept a quote that is genuinely present in the source (even if
whitespace, case, or Unicode composition differ) and must reject everything
else -- especially a plausible paraphrase.
"""

import unicodedata

from askdoc.gate import check_quote

# A real sentence shape from a TNPSC-style Tamil notification.
TAMIL_SOURCE = (
    "## அறிவிக்கை\n\n"
    "மொத்த காலிப் பணியிடங்கள்: 1234 ஆகும்.\n"
    "விண்ணப்பக் கட்டணம் ரூ.150/- ஆகும்.\n"
    "விண்ணப்பிக்க கடைசி தேதி: 30.08.2024.\n"
)


class TestAcceptsGenuineQuotes:
    def test_exact_substring_passes(self):
        result = check_quote("விண்ணப்பக் கட்டணம் ரூ.150/- ஆகும்.", TAMIL_SOURCE)
        assert result.passed

    def test_offsets_point_at_the_quote_in_the_original_text(self):
        quote = "விண்ணப்பக் கட்டணம் ரூ.150/- ஆகும்."
        result = check_quote(quote, TAMIL_SOURCE)
        assert TAMIL_SOURCE[result.start : result.end] == quote

    def test_matched_text_is_the_source_span_not_the_model_string(self):
        # Model emits collapsed whitespace; the source has a newline.
        result = check_quote("1234 ஆகும். விண்ணப்பக் கட்டணம்", TAMIL_SOURCE)
        assert result.passed
        assert "\n" in result.matched_text

    def test_whitespace_differences_are_tolerated(self):
        result = check_quote("மொத்த   காலிப்\n\nபணியிடங்கள்:  1234", TAMIL_SOURCE)
        assert result.passed

    def test_leading_and_trailing_whitespace_is_ignored(self):
        result = check_quote("   \n விண்ணப்பக் கட்டணம் ரூ.150/-  \n ", TAMIL_SOURCE)
        assert result.passed

    def test_case_differences_are_tolerated_in_mixed_script(self):
        source = "Application Fee: Rs.150 மட்டும்."
        result = check_quote("APPLICATION FEE: rs.150", source)
        assert result.passed

    def test_decomposed_unicode_matches_composed_source(self):
        # Same visible Tamil, different codepoint sequence. This MUST match --
        # otherwise a truly verbatim quote gets wrongly refused.
        # "மொத்த" contains U+0BCA, which decomposes to U+0BC6 + U+0BBE.
        quote = unicodedata.normalize("NFD", "மொத்த காலிப் பணியிடங்கள்: 1234")
        assert quote != "மொத்த காலிப் பணியிடங்கள்: 1234"  # guard: really decomposed
        result = check_quote(quote, TAMIL_SOURCE)
        assert result.passed

    def test_telugu_source_is_supported(self):
        source = "దరఖాస్తుకు చివరి తేదీ: 30.08.2024. రుసుము రూ.150/-"
        result = check_quote("రుసుము రూ.150/-", source)
        assert result.passed


class TestRejectsEverythingElse:
    def test_paraphrase_is_rejected(self):
        # The whole point. Semantically right, not verbatim -> refuse.
        result = check_quote("The application fee is 150 rupees.", TAMIL_SOURCE)
        assert not result.passed

    def test_near_miss_with_one_wrong_digit_is_rejected(self):
        result = check_quote("விண்ணப்பக் கட்டணம் ரூ.250/- ஆகும்.", TAMIL_SOURCE)
        assert not result.passed

    def test_plausible_invented_sentence_is_rejected(self):
        result = check_quote("தேர்வு மையம் சென்னையில் அமைந்துள்ளது.", TAMIL_SOURCE)
        assert not result.passed

    def test_empty_quote_is_rejected(self):
        assert not check_quote("", TAMIL_SOURCE).passed

    def test_whitespace_only_quote_is_rejected(self):
        assert not check_quote("   \n\t ", TAMIL_SOURCE).passed

    def test_quote_longer_than_source_is_rejected(self):
        assert not check_quote(TAMIL_SOURCE + " extra text", TAMIL_SOURCE).passed

    def test_empty_source_rejects_everything(self):
        assert not check_quote("anything", "").passed

    def test_words_present_but_not_contiguous_is_rejected(self):
        # Every token exists in the source, but not as a span. A bag-of-words
        # or fuzzy matcher would wrongly pass this.
        result = check_quote("மொத்த காலிப் பணியிடங்கள் ரூ.150/-", TAMIL_SOURCE)
        assert not result.passed


class TestFailedGateResult:
    def test_failure_carries_no_offsets(self):
        result = check_quote("not in the document", TAMIL_SOURCE)
        assert result.start is None
        assert result.end is None
        assert result.matched_text is None


class TestMultipleOccurrences:
    def test_first_occurrence_is_returned(self):
        source = "கட்டணம் ரூ.150. பிறகு கட்டணம் ரூ.150."
        result = check_quote("கட்டணம் ரூ.150", source)
        assert result.passed
        assert result.start == 0

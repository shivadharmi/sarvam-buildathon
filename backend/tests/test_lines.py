"""Line-anchored citation: the model points at lines, we extract the text.

The critical property is the round trip -- a line number the model sees in the
rendered document must resolve to exactly that line in the source text. If
those two ever drift, the product cites the wrong thing while looking correct.
"""

import pytest

from askdoc.lines import broad_above, extract_lines, render_numbered

SOURCE = (
    "வினாத்தொகுப்பு எண்: 22166409\n"
    "கால அளவு : மூன்று மணி நேரம்\n"
    "\n"
    "1. இந்த வினாத்தொகுப்பு, தேர்வு தொடங்குவதற்கு 15 நிமிடங்களுக்கு முன்னதாக\n"
    "வழங்கப்படும்.\n"
    "2. இந்த வினாத்தொகுப்பு, 200 வினாக்களைக் கொண்டுள்ளது."
)


class TestExtractsVerbatimSpans:
    def test_single_line_is_extracted_exactly(self):
        span = extract_lines(SOURCE, 6, 6)
        assert span.valid
        assert span.text == "2. இந்த வினாத்தொகுப்பு, 200 வினாக்களைக் கொண்டுள்ளது."

    def test_offsets_slice_the_source_exactly(self):
        span = extract_lines(SOURCE, 6, 6)
        assert SOURCE[span.start : span.end] == span.text

    def test_multi_line_range_keeps_the_newline(self):
        span = extract_lines(SOURCE, 4, 5)
        assert span.valid
        assert "\n" in span.text
        assert SOURCE[span.start : span.end] == span.text

    def test_line_numbers_are_one_based(self):
        assert extract_lines(SOURCE, 1, 1).text == "வினாத்தொகுப்பு எண்: 22166409"

    def test_extracted_text_is_never_paraphrased(self):
        # The whole point: output is a slice of the input, not a regeneration.
        span = extract_lines(SOURCE, 2, 2)
        assert span.text in SOURCE


class TestRejectsUnusableRanges:
    @pytest.mark.parametrize(
        "start,end",
        [(0, 1), (-1, 2), (1, 0), (5, 3), (1, 999), (999, 999)],
    )
    def test_out_of_bounds_or_inverted_ranges_are_rejected(self, start, end):
        span = extract_lines(SOURCE, start, end)
        assert not span.valid
        assert span.reason

    def test_blank_line_is_rejected(self):
        # Line 3 is empty; citing it proves nothing.
        assert not extract_lines(SOURCE, 3, 3).valid


class TestWidthIsMeasuredNotRefused:
    """Breadth is a label on the answer, never a reason to withhold it.

    A wide citation used to be rejected outright, on the reasoning that citing
    everything proves nothing. Sound about *evidence*, wrong about *what to do*:
    it threw away a correct, fully verified answer to "what is this page about?"
    -- probably the most common thing anyone asks of a dense official page --
    in order to avoid an unimpressive citation. Same mistake as the substring
    gate and the relevance judge, both reverted for the same reason.
    """

    def test_a_very_wide_span_still_produces_a_citation(self):
        big = "\n".join(f"line {i}" for i in range(1, 101))
        span = extract_lines(big, 1, 90)
        assert span.valid
        assert span.text

    def test_citing_the_whole_document_is_allowed_and_flagged(self):
        big = "\n".join(f"line {i}" for i in range(1, 101))
        span = extract_lines(big, 1, 100)
        assert span.valid
        assert span.broad
        assert span.line_count == 100

    def test_a_tight_span_is_not_flagged(self):
        big = "\n".join(f"line {i}" for i in range(1, 101))
        span = extract_lines(big, 4, 6)
        assert span.valid
        assert not span.broad
        assert span.line_count == 3

    def test_a_single_line_counts_as_one(self):
        assert extract_lines(SOURCE, 1, 1).line_count == 1


class TestBroadThreshold:
    """Where "a large part of the page" starts, for a page this long."""

    def test_a_short_document_keeps_the_floor(self):
        assert broad_above(10) == 8

    def test_a_long_document_tolerates_a_larger_passage(self):
        # An 86-line notice: a 15-line answer to "help me understand this" is
        # an ordinary citation, not a notably wide one.
        assert broad_above(86) >= 15

    def test_the_threshold_never_reaches_the_whole_document(self):
        # Citing the entire page is always worth telling the reader about.
        for total in (20, 50, 86, 200, 1000):
            assert broad_above(total) < total

    def test_the_threshold_is_bounded_for_very_long_documents(self):
        assert broad_above(10_000) == 30

    def test_rejection_carries_no_offsets(self):
        span = extract_lines(SOURCE, 999, 999)
        assert span.start is None and span.end is None and span.text is None


class TestRoundTrip:
    """What the model sees must resolve to what we extract."""

    def test_every_rendered_line_number_resolves_to_that_line(self):
        rendered = render_numbered(SOURCE)
        for line in rendered.split("\n"):
            number, _, body = line.partition(" | ")
            index = int(number.strip())
            span = extract_lines(SOURCE, index, index)
            if body.strip():
                assert span.text == body, f"line {index} drifted"

    def test_rendered_document_has_one_entry_per_source_line(self):
        assert len(render_numbered(SOURCE).split("\n")) == len(SOURCE.split("\n"))

    def test_rendering_does_not_alter_the_source(self):
        before = SOURCE
        render_numbered(SOURCE)
        assert SOURCE == before

"""Reading digitised output out of the ZIP.

The load-bearing decision here is using the page JSON instead of
`document.md`. The Markdown renumbers every wrapped line as a fresh list item,
injecting markers like "26. " into the middle of sentences -- which silently
makes verbatim citation impossible. A regression would look like working code.
"""

import io
import json
import zipfile

import pytest

from askdoc.digitise import DigitisationError, _extract_blocks


def build_zip(tmp_path, members: dict[str, str]):
    path = tmp_path / "output.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return path


def page_json(blocks):
    return json.dumps({"page_num": 1, "blocks": blocks})


BLOCK = {
    "reading_order": 1,
    "layout_tag": "ordered-list",
    "confidence": 0.95,
    "text": "2. இந்த வினாத்தொகுப்பு, 200 வினாக்களைக் கொண்டுள்ளது.",
    "coordinates": {"x1": 1.0, "y1": 2.0, "x2": 3.0, "y2": 4.0},
}


class TestExtraction:
    def test_reads_blocks_from_the_page_json(self, tmp_path):
        path = build_zip(tmp_path, {"metadata/page_001.json": page_json([BLOCK])})
        blocks, pages = _extract_blocks(path)
        assert pages == 1
        assert blocks[0]["text"] == BLOCK["text"]

    def test_ignores_the_markdown_even_when_present(self, tmp_path):
        # document.md carries the corrupted renumbering; it must not win.
        path = build_zip(
            tmp_path,
            {
                "document.md": "26. வினாத்தொகுப்பு\n27. corrupted numbering",
                "metadata/page_001.json": page_json([BLOCK]),
            },
        )
        blocks, _ = _extract_blocks(path)
        assert all("26. " not in b["text"] for b in blocks)

    def test_coordinates_survive(self, tmp_path):
        path = build_zip(tmp_path, {"metadata/page_001.json": page_json([BLOCK])})
        blocks, _ = _extract_blocks(path)
        assert blocks[0]["coordinates"]["x2"] == 3.0

    def test_multiple_pages_stay_in_order(self, tmp_path):
        path = build_zip(
            tmp_path,
            {
                "metadata/page_001.json": page_json([{**BLOCK, "text": "page one"}]),
                "metadata/page_002.json": page_json([{**BLOCK, "text": "page two"}]),
            },
        )
        blocks, pages = _extract_blocks(path)
        assert pages == 2
        ordered = sorted(blocks, key=lambda b: b["reading_order"])
        assert [b["text"] for b in ordered] == ["page one", "page two"]


class TestFailures:
    def test_zip_without_page_json_is_an_error(self, tmp_path):
        path = build_zip(tmp_path, {"document.md": "# only markdown"})
        with pytest.raises(DigitisationError, match="No page JSON"):
            _extract_blocks(path)

    def test_page_json_with_no_blocks_is_an_error(self, tmp_path):
        path = build_zip(tmp_path, {"metadata/page_001.json": page_json([])})
        with pytest.raises(DigitisationError, match="no text blocks"):
            _extract_blocks(path)

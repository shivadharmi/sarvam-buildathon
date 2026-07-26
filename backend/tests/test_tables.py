"""Table rows must survive digitisation as single, citable lines.

The digitiser emits one cell per line, so a row -- the unit that actually
carries meaning -- gets split across six. Citing one of those lines yields
`<td>09</td>`: perfectly verbatim, and useless as evidence, because nothing
says what it counts.
"""

from askdoc.tables import flatten_tables

TELUGU_TABLE = """\
<table>
<thead>
<tr>
<th rowspan="2">క్రమ సంఖ్య</th>
<th rowspan="2">ప్రాజెక్టు పేరు</th>
<th colspan="2">ఖాళీ పోస్టు వివరములు</th>
<th>మొత్తం</th>
</tr>
</thead>
<tbody>
<tr>
<td>1</td>
<td>గద్వాల్</td>
<td>28</td>
<td>05</td>
<td>33</td>
</tr>
<tr>
<td></td>
<td>మొత్తం:</td>
<td>64</td>
<td>09</td>
<td>73</td>
</tr>
</tbody>
</table>"""


class TestRowsBecomeOneLine:
    def test_a_data_row_collapses_to_a_single_line(self):
        result = flatten_tables(TELUGU_TABLE)
        assert "| 1 | గద్వాల్ | 28 | 05 | 33 |" in result.split("\n")

    def test_the_header_row_collapses_too(self):
        result = flatten_tables(TELUGU_TABLE)
        assert "| క్రమ సంఖ్య | ప్రాజెక్టు పేరు | ఖాళీ పోస్టు వివరములు | మొత్తం |" in result

    def test_the_totals_row_is_self_describing(self):
        # The failure that motivated this: citing "09" alone proved nothing.
        line = next(l for l in flatten_tables(TELUGU_TABLE).split("\n") if "మొత్తం:" in l)
        assert "09" in line and "64" in line and "73" in line

    def test_empty_cells_are_preserved_as_gaps(self):
        assert "|  | మొత్తం:" in flatten_tables(TELUGU_TABLE)

    def test_structural_tags_are_gone(self):
        result = flatten_tables(TELUGU_TABLE)
        for tag in ("<table>", "</table>", "<thead>", "<tbody>", "<tr>", "<td>", "<th>"):
            assert tag not in result

    def test_row_count_is_preserved(self):
        lines = [l for l in flatten_tables(TELUGU_TABLE).split("\n") if l.strip()]
        assert len(lines) == 3  # header + two data rows

    def test_it_shortens_the_document_substantially(self):
        assert len(flatten_tables(TELUGU_TABLE).split("\n")) < len(TELUGU_TABLE.split("\n"))


class TestSurroundingTextIsUntouched:
    def test_prose_before_and_after_survives(self):
        text = f"అర్హతలు:\n\n{TELUGU_TABLE}\n\nవయస్సు: 18 నుండి 35"
        result = flatten_tables(text)
        assert result.startswith("అర్హతలు:")
        assert result.endswith("వయస్సు: 18 నుండి 35")

    def test_text_without_a_table_is_returned_unchanged(self):
        text = "1. இந்த வினாத்தொகுப்பு, 200 வினாக்களைக் கொண்டுள்ளது.\n2. அடுத்தது."
        assert flatten_tables(text) == text

    def test_two_tables_are_both_flattened(self):
        result = flatten_tables(f"{TELUGU_TABLE}\n\nமற்றும்\n\n{TELUGU_TABLE}")
        assert result.count("| 1 | గద్వాల్ | 28 | 05 | 33 |") == 2
        assert "மற்றும்" in result


class TestRobustness:
    def test_an_unclosed_table_does_not_lose_content(self):
        result = flatten_tables("<table>\n<tr>\n<td>alpha</td>\n<td>beta</td>\n</tr>")
        assert "alpha" in result and "beta" in result

    def test_cells_containing_markup_keep_their_text(self):
        result = flatten_tables("<table><tr><td><b>bold</b></td><td>plain</td></tr></table>")
        assert "| bold | plain |" in result

    def test_whitespace_inside_cells_is_tidied(self):
        result = flatten_tables("<table><tr><td>  a  \n b </td><td>c</td></tr></table>")
        assert "| a b | c |" in result

    def test_empty_input_is_safe(self):
        assert flatten_tables("") == ""

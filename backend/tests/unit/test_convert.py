from app.pipeline.convert import (
    SPACING_MODIFIER_MAP,
    clean_markdown,
    semicolon_cleaning,
)


class TestCleanMarkdown:
    def test_removes_picture_placeholder(self):
        text = "before pic **==> picture: some description\nmore lines <==**after pic"
        result = clean_markdown(
            text, remove_picture_text=False, normalize_whitespace=False
        )
        assert result == "before pic after pic"

    def test_removes_picture_text_block(self):
        text = (
            "before"
            "**----- Start of picture text -----**<br>"
            "hidden ocr text"
            "**----- End of picture text -----**<br>"
            " after"
        )
        result = clean_markdown(
            text, remove_placeholders=False, normalize_whitespace=False
        )
        assert result == "before after"

    def test_keeps_figure_captions_by_default(self):
        text = "Figure 1: figure caption\nPaper continues"
        result = clean_markdown(
            text,
            remove_placeholders=False,
            remove_picture_text=False,
            normalize_whitespace=False,
        )
        assert result == text

    def test_removes_figure_captions_when_enabled(self):
        text = "Figure 1: figure caption\nPaper continues"
        result = clean_markdown(
            text,
            remove_placeholders=False,
            remove_picture_text=False,
            remove_figure_captions=True,
            normalize_whitespace=False,
        )
        assert result == "\nPaper continues"

    def test_keeps_table_captions_by_default(self):
        text = "Table 2. Some table\npaper continues"
        result = clean_markdown(
            text,
            remove_placeholders=False,
            remove_picture_text=False,
            normalize_whitespace=False,
        )
        assert result == text

    def test_removes_table_captions_when_enabled(self):
        text = "Table 2. Some table\nPaper continues"
        result = clean_markdown(
            text,
            remove_placeholders=False,
            remove_picture_text=False,
            remove_table_captions=True,
            normalize_whitespace=False,
        )
        assert result == "\nPaper continues"

    def test_normalizes_newlines_and_spaces(self):
        text = "a\n\n\n\nb   c"
        result = clean_markdown(
            text, remove_placeholders=False, remove_picture_text=False
        )
        assert result == "a\n\nb c"

    def test_fixes_spacing_modifiers(self):
        seq, replacement = next(iter(SPACING_MODIFIER_MAP.items()))
        text = f"pre{seq}post"
        result = clean_markdown(
            text,
            remove_placeholders=False,
            remove_picture_text=False,
            normalize_whitespace=False,
        )
        assert result == f"pre{replacement}post"


class TestSemicolonCleaning:
    def test_unescapes_tight_semicolon_and_letter_artifact(self):
        assert semicolon_cleaning("M&A;") == "M&A"
        assert semicolon_cleaning("P&G;'s portfolio") == "P&G's portfolio"
        assert semicolon_cleaning("GD&T;, FMEA") == "GD&T, FMEA"

    def test_leaves_known_uppercase_html_entities_untouched(self):
        assert semicolon_cleaning("Tom &AMP; Jerry") == "Tom &AMP; Jerry"
        assert semicolon_cleaning("A &LT; B") == "A &LT; B"

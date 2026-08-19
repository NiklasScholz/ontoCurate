import logging
import re
import tempfile
import unicodedata
from pathlib import Path

import pymupdf4llm

logger = logging.getLogger(__name__)

SPACING_MODIFIER_MAP = {
    "˘a": "ă",
    "˘A": "Ă",
    "˙z": "ż",
    "˙Z": "Ż",
    "˛a": "ą",
    "˛A": "Ą",
    "˛e": "ę",
    "˛E": "Ę",
    "ˇc": "č",
    "ˇC": "Č",
    "ˇs": "š",
    "ˇS": "Š",
    "ˇz": "ž",
    "ˇZ": "Ž",
    "¨a": "ä",
    "¨A": "Ä",
    "¨o": "ö",
    "¨O": "Ö",
    "¨u": "ü",
    "¨U": "Ü",
}


def fix_spacing_modifiers(text: str) -> str:
    """Fixes issues of pymupdf4llm when special characters are not translated correctly"""
    for seq, replacement in SPACING_MODIFIER_MAP.items():
        text = text.replace(seq, replacement)
    return unicodedata.normalize("NFC", text)


def semicolon_cleaning(text: str) -> str:
    """Cleans up when & is immediately followed by ; to avoid ontoGPT parsing issues; caused by HTML elements"""
    html_entities = {"AMP", "LT", "GT", "QUOT", "APOS", "NBSP", "COPY", "REG"}

    def repl(match: re.Match) -> str:
        letters = match.group(1)
        if letters.upper() in html_entities:
            return match.group(0)
        return f"&{letters}"  # strips ;

    return re.compile(r"&([A-Za-z]{1,4});").sub(repl, text)


def clean_markdown(
    md_text: str,
    remove_placeholders: bool = True,
    remove_picture_text: bool = True,
    remove_figure_captions: bool = False,
    remove_table_captions: bool = False,
    normalize_whitespace: bool = True,
) -> str:
    """
    Cleans up Markdown text extracted from PDF by removing placeholders, picture text, figure captions, table captions, and normalizing whitespace.
    Could be configured what should be removed based on specific use cases.
    """
    if remove_placeholders:
        md_text = re.sub(r"\*\*==> picture.*?<==\*\*", "", md_text, flags=re.DOTALL)

    if remove_picture_text:
        md_text = re.sub(
            r"\*\*----- Start of picture text -----\*\*<br>.*?\*\*----- End of picture text -----\*\*<br>",
            "",
            md_text,
            flags=re.DOTALL,
        )

    if remove_figure_captions:
        md_text = re.sub(r"Figure\s+\d+[:.].*", "", md_text)

    if remove_table_captions:
        md_text = re.sub(r"Table\s+\d+[:.].*", "", md_text)

    if normalize_whitespace:
        md_text = re.sub(r"\n{3,}", "\n\n", md_text)
        md_text = re.sub(r"[ \t]{2,}", " ", md_text)

    md_text = fix_spacing_modifiers(md_text)
    md_text = semicolon_cleaning(md_text)

    return md_text


def pdf_to_markdown(raw_bytes: bytes, filename: str | None = None) -> str:
    """Convert PDF bytes to cleaned Markdown using pymupdf4llm."""

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        tmp_pdf.write(raw_bytes)
        tmp_pdf.flush()
        tmp_path = tmp_pdf.name

    try:
        # automatically splits pages into chunks and removes headers and footers
        pages = pymupdf4llm.to_markdown(
            tmp_path, page_chunks=True, header=False, footer=False
        )
        full_md = ""
        for page in pages:
            page_text = page.get("text", "") if isinstance(page, dict) else ""
            cleaned_text = clean_markdown(page_text)
            full_md += cleaned_text
        return full_md.strip()
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to remove temporary PDF file: %s", tmp_path)

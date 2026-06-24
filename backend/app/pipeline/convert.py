import logging
import re
import tempfile
from pathlib import Path

import pymupdf4llm

logger = logging.getLogger(__name__)


def clean_markdown(
    md_text: str,
    remove_placeholders: bool = True,
    remove_picture_text: bool = True,
    remove_figure_captions: bool = False,
    remove_table_captions: bool = False,
    normalize_whitespace: bool = True,
) -> str:
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
        for i, page in enumerate(pages):
            page_text = page.get("text", "") if isinstance(page, dict) else ""
            full_md += f"\n\n**==> PAGE NUMBER {i + 1}: <==**\n\n"
            cleaned_text = clean_markdown(page_text)
            full_md += cleaned_text
        return full_md.strip()
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to remove temporary PDF file: %s", tmp_path)

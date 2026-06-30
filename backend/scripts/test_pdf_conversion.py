#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make sure we can import the app package from backend/ when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks.convert import pdf_to_markdown


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a PDF to Markdown using app.tasks.convert.pdf_to_markdown."
    )
    parser.add_argument("pdf", type=Path, help="Path to the PDF file to convert")
    parser.add_argument("--out", type=Path, help="Optional output markdown file")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"Error: PDF file not found: {args.pdf}")
        return 2

    raw_bytes = args.pdf.read_bytes()
    try:
        markdown = pdf_to_markdown(raw_bytes, filename=args.pdf.name)
    except ImportError as exc:
        print("Dependency error:", exc)
        print("Install pymupdf4llm in the backend environment and try again.")
        return 3

    if args.out:
        args.out.write_text(markdown, encoding="utf-8")
        print(f"Wrote markdown to {args.out}")
    else:
        print(markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

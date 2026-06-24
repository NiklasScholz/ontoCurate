# Runnable after navigating to backend and setting secrets.env
# used to benchmark whole pipeline without having to use application or celery overhead

import argparse
import csv
import logging
import os
import sys
from pathlib import Path

from ontogpt_patches.apply_patches import apply_patches

apply_patches(verbose=True)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

from app.pipeline.convert import pdf_to_markdown
from benchmarking_scripts.alignment_bench import run_alignment_bench
from benchmarking_scripts.extraction_bench import run_extraction_bench

# fields we use in dictionaries returned by alignment and extraction benchmark files
EXTRACTION_FIELDNAMES = [
    "document",
    "subject_uri",
    "entity_type",
    "predicate",
    "object_value",
    "triple_type",
    "span_start",
    "span_end",
    "span_text",
    "confidence",
]

ALIGNMENT_FIELDNAMES = [
    "alignment_type",
    "entity_type",
    "entity_a_uri",
    "entity_a_label",
    "entity_a_document",
    "entity_b_uri",
    "entity_b_label",
    "entity_b_document",
    "alignment_confidence_score",
    "threshold_set_by_config",
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def collect_input_files(input_dir: Path):
    paths = sorted(
        p
        for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".md", ".pdf"}
    )
    if not paths:
        print(f"No .md or .pdf files found in {input_dir}")
        sys.exit(1)
    return paths


def convert_pdfs(input_paths: list[Path], output_dir: Path) -> list[Path]:
    """Convert any PDF inputs to Markdown, return list with PDFs replaced by their .md equivalents."""
    result = []
    for path in input_paths:
        if path.suffix.lower() != ".pdf":
            result.append(path)
            continue

        doc_dir = output_dir / path.stem
        doc_dir.mkdir(parents=True, exist_ok=True)
        md_path = doc_dir / f"{path.stem}.md"

        if md_path.exists():
            logger.info("Reusing existing markdown for %s", path.name)
        else:
            logger.info("Converting PDF to Markdown: %s", path.name)
            raw_bytes = path.read_bytes()
            markdown = pdf_to_markdown(raw_bytes, filename=path.name)
            md_path.write_text(markdown, encoding="utf-8")

        result.append(md_path)
    return result


def main():
    parser = argparse.ArgumentParser(
        prog="ontocurate-benchmark",
        description="benchmarking ontoCurate extraction and entity alignment to evaluate pipeline quality in depth",
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        type=Path,
        help="Directory containing documents (for now only md files)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for intermediate files and output CSVs",
    )
    parser.add_argument("--model", default="gpt-oss-120b", help="LLM model name")
    parser.add_argument(
        "--schema",
        default=None,
        type=Path,
        help="Path to LinkML schema YAML (defaults to scholarly_schema.yaml)",
    )
    parser.add_argument(
        "--alignment-config",
        default=None,
        type=Path,
        help="Path to alignment config YAML (defaults to alignment_config.yaml)",
    )
    parser.add_argument(
        "--provenance-config",
        default=None,
        type=Path,
        help="Path to provenance config YAML (defaults to provenance_config.yaml next to schema)",
    )
    parser.add_argument(
        "--skip-extraction",
        action="store_true",
        help="Skip extraction and reuse existing TTL files in output-dir subdirectories",
    )
    args = parser.parse_args()

    backend_root = Path(__file__).parent.parent
    config_dir = backend_root / "config" / "schemas"

    default_schema = config_dir / "scholarly_schema.yaml"
    schema_path = args.schema or default_schema
    if not schema_path.exists():
        print(f"Schema not found: {schema_path}", file=sys.stderr)
        sys.exit(1)

    alignment_config_path = (
        args.alignment_config or config_dir / "alignment_config.yaml"
    )
    if not alignment_config_path.exists():
        print(f"Alignment config not found: {alignment_config_path}", file=sys.stderr)
        sys.exit(1)

    provenance_config_path = (
        args.provenance_config or config_dir / "provenance_config.yaml"
    )
    if not provenance_config_path.exists():
        print(f"Provenance config not found: {provenance_config_path}", file=sys.stderr)
        sys.exit(1)

    api_base = os.environ.get("OPENAI_API_BASE", "")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or not api_base:
        raise ValueError(
            "OPENAI_API_BASE and OPENAI_API_KEY environment variables must be set"
        )

    model = args.model
    args.output_dir.mkdir(parents=True, exist_ok=True)
    input_paths = collect_input_files(args.input_dir)

    ttl_paths = []

    if args.skip_extraction:
        for doc_path in input_paths:
            # resolve stem regardless of whether original was PDF or MD
            ttl_file_path = (
                args.output_dir / doc_path.stem / f"{doc_path.stem}_extraction.ttl"
            )
            if ttl_file_path.exists():
                ttl_paths.append(ttl_file_path)
            else:
                print(
                    f"TTL file not found for {doc_path}, skipping alignment for this document."
                )
    else:
        input_paths = convert_pdfs(input_paths, args.output_dir)
        print("Running extraction benchmark...")
        extraction_rows = run_extraction_bench(
            input_paths=input_paths,
            output_dir=args.output_dir,
            schema_path=schema_path,
            model=model,
            api_base=api_base,
            api_key=api_key,
            provenance_config_path=provenance_config_path,
        )

        write_csv(
            args.output_dir / "extraction_results.csv",
            EXTRACTION_FIELDNAMES,
            extraction_rows,
        )

        for doc_path in input_paths:
            ttl_file_path = (
                args.output_dir / doc_path.stem / f"{doc_path.stem}_extraction.ttl"
            )
            if ttl_file_path.exists():
                ttl_paths.append(ttl_file_path)

    if ttl_paths:
        print("Running alignment benchmark...")
        alignment_rows = run_alignment_bench(
            ttl_paths=ttl_paths,
            config_path=alignment_config_path,
        )

        write_csv(
            args.output_dir / "alignment_results.csv",
            ALIGNMENT_FIELDNAMES,
            alignment_rows,
        )


if __name__ == "__main__":
    main()

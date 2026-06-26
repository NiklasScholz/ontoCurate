import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rdflib import Graph

from app.pipeline.confidence_annotation import annotate_confidence
from app.pipeline.extraction import extract_document
from app.pipeline.utils.turtle_utils import build_type_index, local_name


def process_document(
    idx: int,
    total: int,
    doc_path: Path,
    output_dir: Path,
    schema_path: Path,
    model: str,
    api_base: str,
    api_key: str,
    provenance_config_path: Path | None,
    max_text_length: int | None,
) -> list[dict]:
    print(f"Processing document: {doc_path.name} [{idx + 1}/{total}]")
    try:
        _yaml_path, ttl_path = extract_document(
            input_path=doc_path,
            schema_path=schema_path,
            output_dir=output_dir / doc_path.stem,
            model=model,
            api_base=api_base,
            api_key=api_key,
            max_text_length=max_text_length,
        )
    except Exception as e:
        print(f"Extraction failed for {doc_path.name}, skipping. Error: {e}")
        return []

    try:
        print(f"Annotating confidence for {doc_path.name} [{idx + 1}/{total}]...")
        provenance_path = annotate_confidence(
            source_path=doc_path,
            ttl_path=ttl_path,
            output_dir=output_dir / doc_path.stem,
            config_path=provenance_config_path,
        )
    except Exception as e:
        print(f"Confidence annotation failed for {doc_path.name}, skipping. Error: {e}")
        return []

    with open(provenance_path, encoding="utf-8") as f:
        provenance = json.load(f)

    g = Graph()
    g.parse(str(ttl_path))
    type_index = build_type_index(g)

    rows = []
    for ann in provenance.get("annotations", []):
        triple_type = ann.get("triple_type")
        if triple_type == "object_property":
            object_value = local_name(ann.get("object"))
        elif triple_type == "entity_type":
            object_value = local_name(ann.get("value"))
        else:
            object_value = ann.get("value")

        rows.append(
            {
                "document": doc_path.name,
                "subject_uri": local_name(ann.get("subject")),
                "entity_type": ", ".join(type_index.get(ann.get("subject", ""), [])),
                "predicate": ann.get("predicate"),
                "object_value": object_value,
                "triple_type": triple_type,
                "span_start": ann.get("span_start"),
                "span_end": ann.get("span_end"),
                "span_text": ann.get("span_text"),
                "confidence": ann.get("confidence"),
            }
        )
    return rows


def run_extraction_bench(
    input_paths: list[Path],
    output_dir: Path,
    schema_path: Path,
    model: str,
    api_base: str,
    api_key: str,
    provenance_config_path: Path | None = None,
    max_text_length: int | None = None,
    max_workers: int = 1,
):
    total = len(input_paths)

    if max_workers <= 1:
        all_rows = []
        for idx, doc_path in enumerate(input_paths):
            all_rows.extend(
                process_document(
                    idx,
                    total,
                    doc_path,
                    output_dir,
                    schema_path,
                    model,
                    api_base,
                    api_key,
                    provenance_config_path,
                    max_text_length,
                )
            )
        return all_rows

    all_rows = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process_document,
                idx,
                total,
                doc_path,
                output_dir,
                schema_path,
                model,
                api_base,
                api_key,
                provenance_config_path,
                max_text_length,
            ): doc_path
            for idx, doc_path in enumerate(input_paths)
        }
        for future in as_completed(futures):
            doc_path = futures[future]
            try:
                all_rows.extend(future.result())
            except Exception as e:
                print(f"Unexpected error processing {doc_path.name}: {e}")

    return all_rows

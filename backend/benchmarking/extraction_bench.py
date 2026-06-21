import json
from pathlib import Path

from rdflib import Graph

from app.pipeline.confidence_annotation import annotate_confidence
from app.pipeline.extraction import extract_document
from app.pipeline.utils.turtle_utils import build_type_index, local_name


def run_extraction_bench(
    input_paths: list[Path],
    output_dir: Path,
    schema_path: Path,
    model: str,
    api_base: str,
    api_key: str,
    provenance_config_path: Path | None = None,
    max_text_length: int | None = None,
):
    all_rows = []

    for idx, doc_path in enumerate(input_paths):
        print(f"Processing document: {doc_path.name} [{idx + 1}/{len(input_paths)}]")
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
            print(f"Extraction failed for {doc_path}, skipping. Error: {e}")

        try:
            print(
                f"Annotating confidence for {doc_path.name} [{idx + 1}/{len(input_paths)}]..."
            )
            provenance_path = annotate_confidence(
                source_path=doc_path,
                ttl_path=ttl_path,
                output_dir=output_dir / doc_path.stem,
                schema_path=schema_path,
                config_path=provenance_config_path,
            )
        except Exception as e:
            print(f"Confidence annotation failed for {doc_path}, skipping. Error: {e}")
            continue

        with open(provenance_path, encoding="utf-8") as f:
            provenance = json.load(f)

        g = Graph()
        g.parse(str(ttl_path))
        type_index = build_type_index(g)

        for ann in provenance.get("annotations", []):
            triple_type = ann.get("triple_type")
            # trim prefix to allow files to be more readable
            if triple_type == "object_property":
                object_value = local_name(ann.get("object"))
            elif triple_type == "entity_type":
                object_value = local_name(ann.get("value"))
            else:
                object_value = ann.get("value")

            all_rows.append(
                {
                    "document": doc_path.name,
                    "subject_uri": local_name(ann.get("subject")),
                    "entity_type": ", ".join(
                        type_index.get(ann.get("subject", ""), [])
                    ),
                    "predicate": ann.get("predicate"),
                    "object_value": object_value,
                    "triple_type": ann.get("triple_type"),
                    "span_start": ann.get("span_start"),
                    "span_end": ann.get("span_end"),
                    "span_text": ann.get("span_text"),
                    "confidence": ann.get("confidence"),
                }
            )

    return all_rows

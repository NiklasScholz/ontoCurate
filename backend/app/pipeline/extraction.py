"""Runs ontoGPT extraction via subprocess.
Also cleans the extraction output to remove potentially ill-formed entities.
Used by celery extraction.py
"""

import hashlib
import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import yaml
from linkml.generators import PythonGenerator
from linkml.utils.datautils import get_dumper, get_loader
from linkml_runtime import SchemaView


def extract_document(
    input_path: Path,
    schema_path: Path,
    output_dir: Path,
    model: str,
    api_base: str,
    api_key: str,
) -> tuple[Path, Path]:
    """
    Stage 1: Call `ontogpt extract` as a subprocess, clean the YAML output,
    and convert to Turtle RDF via linkml-runtime.

    Requires apply_patches() to have been called before any OntoGPT import.

    Returns:
        (yaml_path, ttl_path)
    """
    input_path = Path(input_path)
    schema_path = Path(schema_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = input_path.stem
    yaml_out = output_dir / f"{stem}_extraction.yaml"
    ttl_out = output_dir / f"{stem}_extraction.ttl"

    _extract_onto(
        input_path,
        schema_path,
        yaml_out,
        model=model,
        api_base=api_base,
        api_key=api_key,
    )
    clean_extraction(yaml_out, schema_path, doc_name=input_path.stem)
    _yaml_to_turtle(yaml_out, ttl_out, schema_path)

    return yaml_out, ttl_out


def _extract_onto(
    input_path: Path,
    schema_path: Path,
    output_path: Path,
    model: str = "gpt-oss-120b",
    api_base: str | None = None,
    api_key: str | None = None,
    output_format: str = "yaml",
    verbose: bool = False,
) -> None:
    env = os.environ.copy()
    if api_base:
        env["OPENAI_API_BASE"] = api_base
    if api_key:
        env["OPENAI_API_KEY"] = api_key
    base_url = env.get("OPENAI_API_BASE", "")

    cmd = ["ontogpt"]
    if verbose:
        cmd += ["-vvv"]
    cmd += [
        "extract",
        "-i",
        str(input_path),
        "-t",
        str(schema_path),
        "-m",
        model,
        "--model-provider",
        "openai",
        "--api-base",
        base_url,
        "-O",
        output_format,
        "-o",
        str(output_path),
    ]
    subprocess.run(cmd, env=env, check=True)


def _uri_fields_from_schema(schema_path: Path) -> frozenset[str]:
    "Returns all uri fields in the schema to be cleaned (ensuring no errors in ttl conversion)"
    raw = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    return frozenset(
        name
        for name, defn in raw.get("slots", {}).items()
        if isinstance(defn, dict) and defn.get("range") == "uri"
    )


def _name_fields_from_schema(schema_path: Path) -> tuple[str, ...]:
    "Returns all string fields in the schema that are likely to be names, to be cleaned for better ID generation and ttl conversion."
    raw = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    slots = raw.get("slots", {})
    return tuple(
        slot_name
        for slot_name, defn in slots.items()
        if isinstance(defn, dict) and defn.get("range", "string") == "string"
    )


_INVALID_LOCAL_RE = re.compile(r"[^\w\-.]", re.ASCII)


def _fallback_id(obj: dict, name_fields: tuple[str, ...], doc_name: str = "") -> str:
    """Generates a stable, TTL-safe URI for an entity that lacks one."""
    value = obj.get("name") if "name" in name_fields else None
    if value and isinstance(value, str):
        parts = value.strip().split()
        if len(parts) >= 2:
            initials = "".join(p[0] for p in parts[:-1])
            local = f"{parts[-1]}_{initials}"
        else:
            local = value.strip()
        local = _INVALID_LOCAL_RE.sub("", local.replace(" ", "_"))
    else:
        local = "entity"
        for field in name_fields:
            name = obj.get(field)
            if name and isinstance(name, str):
                local = _INVALID_LOCAL_RE.sub("", name.replace(" ", "_"))
                if len(local) > 40:
                    truncated = local[:40]
                    last_underscore = truncated.rfind("_")
                    local = (
                        truncated[:last_underscore]
                        if last_underscore > 0
                        else truncated
                    )
                break
    digest = hashlib.md5(
        json.dumps({**obj, "_doc": doc_name}, sort_keys=True, default=str).encode()
    ).hexdigest()[
        :6
    ]  # ensures no conflicts during conversion. Same entities will be linked later during alignment phases.
    return f"smo:{local}_{digest}"


# Cleaning of results so ttl conversion does not fail
_URI_RE = re.compile(r"^https?://\S+$")


def _is_valid_uri(value: str) -> bool:
    return bool(_URI_RE.match(value.strip()))


def _normalize_unicode(value: str) -> str:
    unicode_hyphens = str.maketrans("­‐‑‒–—―−－", "---------")
    unicode_spaces = str.maketrans("       　", "        ")
    return value.translate(unicode_hyphens).translate(unicode_spaces)


def _clean_result(
    obj: object,
    uri_fields: frozenset[str],
    name_fields: tuple[str, ...],
    counters: defaultdict,
    doc_name: str = "",
) -> object:
    """Recursively clean the extraction result to ensure TTL conversion does not fail."""
    if isinstance(obj, dict):
        cleaned: dict = {}
        for k, v in obj.items():
            v = _clean_result(v, uri_fields, name_fields, counters, doc_name=doc_name)
            if k in uri_fields and isinstance(v, str):
                norm = _normalize_unicode(v.strip())
                if not _is_valid_uri(norm):
                    continue
                v = norm
            elif isinstance(v, str):
                v = _normalize_unicode(v)
            if v == []:
                continue
            cleaned[k] = v

        if "id" in cleaned and isinstance(cleaned["id"], str):
            raw_id = cleaned["id"].strip()
            if (
                not raw_id
                or raw_id == "AUTO"
                or raw_id.startswith("AUTO:")
                or raw_id.endswith(":AUTO")
                or raw_id.endswith("/AUTO")
            ):
                cleaned["id"] = _fallback_id(cleaned, name_fields, doc_name=doc_name)
        if "id" not in cleaned and any(cleaned.get(f) for f in name_fields):
            cleaned["id"] = _fallback_id(cleaned, name_fields, doc_name=doc_name)
        return cleaned

    if isinstance(obj, list):
        cleaned_list = [
            _clean_result(item, uri_fields, name_fields, counters, doc_name=doc_name)
            for item in obj
        ]
        merged: dict[str, dict] = {}
        no_id: list = []
        for item in cleaned_list:
            if item is None or item == "" or item == {}:
                continue
            if isinstance(item, str) and item.startswith("AUTO:"):
                continue
            if isinstance(item, dict):
                item_id = item.get("id")
                if item_id:
                    if item_id in merged:
                        for k, v in item.items():
                            if k not in merged[item_id] or not merged[item_id][k]:
                                merged[item_id][k] = v
                    else:
                        merged[item_id] = dict(item)
                else:
                    no_id.append(item)
            else:
                no_id.append(item)
        return list(merged.values()) + no_id

    if isinstance(obj, str):
        return _normalize_unicode(obj)
    return obj


def clean_extraction(
    output_path: Path,
    schema_path: Path | None = None,
    doc_name: str = "",
) -> None:
    """Remove empty entity objects and fix duplicate IDs in-place before TTL conversion."""
    output_path = Path(output_path)
    raw_text = output_path.read_text(encoding="utf-8").replace("\x00", "")
    data = yaml.safe_load(raw_text)

    uri_fields = _uri_fields_from_schema(schema_path)
    name_fields = _name_fields_from_schema(schema_path)

    data = _clean_result(
        data, uri_fields, name_fields, defaultdict(int), doc_name=doc_name
    )

    output_path.write_text(
        yaml.dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _yaml_to_turtle(yaml_path: Path, ttl_path: Path, schema_path: Path) -> None:
    """Converts cleaned YAML output to Turtle RDF file using linkML"""
    schema_path = Path(schema_path).resolve()
    python_module = PythonGenerator(str(schema_path)).compile_module()

    sv = SchemaView(str(schema_path))
    root_class_name = next(name for name, c in sv.all_classes().items() if c.tree_root)
    py_target_class = python_module.__dict__[root_class_name]

    raw = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
    extracted = raw.get("extracted_object")
    data = (
        extracted
        if extracted is not None
        else {
            k: v
            for k, v in raw.items()
            if k
            not in {
                "input_text",
                "raw_completion_output",
                "prompt",
                "named_entities",
                "extracted_object",
            }
        }
    )

    yaml_str = yaml.dump(data, allow_unicode=True, sort_keys=False)
    yaml_str = re.sub(r"(?m)^(\s*)- null\s*$\n?", "", yaml_str)
    yaml_str = re.sub(r"(?m)^(\s*)- \{\}\s*$\n?", "", yaml_str)
    obj = get_loader("yaml").load(source=yaml_str, target_class=py_target_class)
    ttl = get_dumper("ttl").dumps(obj, schemaview=sv)
    Path(ttl_path).write_text(ttl, encoding="utf-8")

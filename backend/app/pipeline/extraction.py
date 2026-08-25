import hashlib
import json
import logging
import os
import re
import subprocess
import unicodedata
from collections import defaultdict
from pathlib import Path

import yaml
from linkml.generators import PythonGenerator
from linkml.utils.datautils import get_dumper, get_loader
from linkml_runtime import SchemaView

logger = logging.getLogger(__name__)


def extract_document(
    input_path: Path,
    schema_path: Path,
    output_dir: Path,
    model: str,
    api_base: str,
    api_key: str,
    max_text_length: int | None = None,
    max_output_tokens: int | None = None,
    temperature: float = 0.3,
) -> tuple[Path, Path]:
    """
    Call `ontogpt extract` as a subprocess, clean the YAML output,
    and convert to Turtle RDF via linkml
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

    extract_onto(
        input_path,
        schema_path,
        yaml_out,
        model=model,
        api_base=api_base,
        api_key=api_key,
        max_text_length=max_text_length,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )
    clean_extraction(yaml_out, schema_path, doc_name=input_path.stem)
    yaml_to_turtle(yaml_out, ttl_out, schema_path)
    return yaml_out, ttl_out


def extract_onto(
    input_path: Path,
    schema_path: Path,
    output_path: Path,
    model: str = "gpt-oss-120b",
    api_base: str | None = None,
    api_key: str | None = None,
    output_format: str = "yaml",
    verbose: bool = True,
    max_text_length: int | None = None,
    max_output_tokens: int | None = None,
    temperature: float = 0.3,
) -> None:
    """Calls ontogpt extract as a subprocess."""
    env = os.environ.copy()
    if api_base:
        env["OPENAI_API_BASE"] = api_base
    if api_key:
        env["OPENAI_API_KEY"] = api_key
    if max_output_tokens is not None:
        env["ONTOGPT_MAX_OUTPUT_TOKENS"] = str(max_output_tokens)
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
        "-p",
        str(temperature),
        "-O",
        output_format,
        "-o",
        str(output_path),
    ]
    if max_text_length is not None:
        cmd += ["--max-text-length", str(max_text_length)]
    result = subprocess.run(cmd, env=env, text=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd)


def uri_fields_from_schema(schema_path: Path) -> frozenset[str]:
    "Returns all uri fields in the schema."
    raw = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    return frozenset(
        name
        for name, defn in raw.get("slots", {}).items()
        if isinstance(defn, dict) and defn.get("range") == "uri"
    )


def name_fields_from_schema(schema_path: Path) -> tuple[str, ...]:
    "Returns all string fields in the schema that could be used for better ID generation."
    raw = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    slots = raw.get("slots", {})
    return tuple(
        slot_name
        for slot_name, defn in slots.items()
        if isinstance(defn, dict) and defn.get("range", "string") == "string"
    )


def default_prefix_from_schema(schema_path: Path | None) -> str:
    "Returns the default_prefix of linkml schema, so fallback ids work correctly."
    if schema_path is None:
        return "smo"
    raw = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    return raw.get("default_prefix", "smo")


INVALID_LOCAL_RE = re.compile(r"[^\w\-.]", re.ASCII)


def transform_to_ascii(value: str) -> str:
    """
    Fold non-ASCII letters (š, ū, ė, ...) to their closest ASCII form so
    they are not silently deleted.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def fallback_id(
    obj: dict, name_fields: tuple[str, ...], doc_name: str = "", prefix: str = "smo"
) -> str:
    """Generates a stable, TTL-safe URI for an entity that lacks one."""
    value = obj.get("name") if "name" in name_fields else None
    if value and isinstance(value, str):
        # specific `name`` attribute exists
        parts = value.strip().split()
        name_suffixes = {
            "jr",
            "sr",
            "ii",
            "iii",
            "iv",
            "prof",
            "dr",
            "phd",
        }  # should not be used for ids
        while len(parts) > 1 and parts[-1].strip(".").lower() in name_suffixes:
            parts.pop()
        longest_idx = (
            len(parts) - 1
        )  # assumes last token is most meaningful one for id (e.g. surname)
        if len(parts) >= 2:
            cleaned_last = INVALID_LOCAL_RE.sub("", transform_to_ascii(parts[-1]))
            if len(cleaned_last) < 2:
                # pick longest if last token is too short
                longest_idx = max(range(len(parts)), key=lambda i: len(parts[i]))
        token = parts[longest_idx] if parts else value.strip()
        if (
            len(parts) >= 2
        ):  # if more than one token existed add remaining tokens as index
            initials = "".join(p[0] for i, p in enumerate(parts) if i != longest_idx)
            local = f"{token}_{initials}"
        else:
            local = token
        local = INVALID_LOCAL_RE.sub("", transform_to_ascii(local).replace(" ", "_"))
    else:
        # no name field found, fallback to generic entity id with other string fields
        local = "entity"
        for field in name_fields:
            name = obj.get(field)
            if name and isinstance(name, str):
                local = INVALID_LOCAL_RE.sub(
                    "", transform_to_ascii(name).replace(" ", "_")
                )
                # Take at maximum 40 characters
                if len(local) > 40:
                    truncated = local[:40]
                    last_underscore = truncated.rfind("_")
                    local = (
                        truncated[
                            :last_underscore
                        ]  # trunctuate at last underscore if possible
                        if last_underscore > 0
                        else truncated
                    )
                break
    fingerprint = hashlib.md5(
        json.dumps({**obj, "_doc": doc_name}, sort_keys=True, default=str).encode()
    ).hexdigest()[
        :6
    ]  # unique fingerprint based on document and entity content. Ensures no implicit alignment when information differs.
    return f"{prefix}:{local}_{fingerprint}"


# Cleaning of results so ttl conversion does not fail
URI_RE = re.compile(r"^https?://\S+$")


def is_valid_uri(value: str) -> bool:
    return bool(URI_RE.match(value.strip()))


def normalize_unicode(value: str) -> str:
    """Clean unicode characters that may cause low confidence scores"""
    unicode_hyphens = str.maketrans("­‐‑‒–—―−－", "---------")
    unicode_spaces = str.maketrans("       　", "        ")
    value = value.translate(unicode_hyphens).translate(unicode_spaces)
    return "".join(
        ch
        for ch in value
        if unicodedata.category(ch) not in ("Cc", "Cf") or ch in ("\n", "\r", "\t")
    )


def clean_result(
    obj: object,
    uri_fields: frozenset[str],
    name_fields: tuple[str, ...],
    counters: defaultdict,
    doc_name: str = "",
    prefix: str = "smo",
) -> object:
    """Recursively clean and merge the extraction result to ensure TTL conversion does not fail."""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            v = clean_result(
                v, uri_fields, name_fields, counters, doc_name=doc_name, prefix=prefix
            )
            if k in uri_fields and isinstance(v, str):
                norm = normalize_unicode(v.strip())
                if not is_valid_uri(norm):
                    continue
                v = norm
            elif isinstance(v, str):
                v = normalize_unicode(v)
            if v == [] or (isinstance(v, dict) and v.keys() == {"id"}):
                continue
            cleaned[k] = v
        # Generate fallback id if no valid id exists
        if "id" in cleaned and isinstance(cleaned["id"], str):
            raw_id = cleaned["id"].strip()
            if (
                not raw_id
                or raw_id == "AUTO"
                or raw_id.startswith("AUTO:")
                or raw_id.endswith(":AUTO")
                or raw_id.endswith("/AUTO")
            ):
                cleaned["id"] = fallback_id(
                    cleaned, name_fields, doc_name=doc_name, prefix=prefix
                )
        if "id" not in cleaned and any(cleaned.get(f) for f in name_fields):
            cleaned["id"] = fallback_id(
                cleaned, name_fields, doc_name=doc_name, prefix=prefix
            )
        return cleaned

    if isinstance(obj, list):
        cleaned_list = [
            clean_result(
                item,
                uri_fields,
                name_fields,
                counters,
                doc_name=doc_name,
                prefix=prefix,
            )
            for item in obj
        ]
        merged: dict[str, dict] = {}
        no_id = []
        for item in cleaned_list:
            if (
                item is None
                or item == ""
                or item == {}
                or (isinstance(item, dict) and item.keys() == {"id"})
            ):
                # drop empty items without information
                continue
            if isinstance(item, str) and item.startswith("AUTO:"):
                # drop AUTO: ids that were not replaced by a fallback id
                continue
            if isinstance(item, dict):
                # merge items with the same id, preferring non-empty values
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
                no_id.append(item)  # plain literals
        return list(merged.values()) + no_id

    if isinstance(obj, str):
        return normalize_unicode(obj)

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

    uri_fields = uri_fields_from_schema(schema_path)
    name_fields = name_fields_from_schema(schema_path)
    prefix = default_prefix_from_schema(schema_path)

    data = clean_result(
        data,
        uri_fields,
        name_fields,
        defaultdict(int),
        doc_name=doc_name,
        prefix=prefix,
    )

    output_path.write_text(
        yaml.dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def yaml_to_turtle(yaml_path: Path, ttl_path: Path, schema_path: Path) -> None:
    """Converts cleaned YAML output to Turtle RDF file using linkML"""
    logger.info(f"[yaml_to_turtle] YAML path: {yaml_path}")

    # Build Python module from schema to use for loading YAML
    schema_path = Path(schema_path).resolve()
    python_module = PythonGenerator(str(schema_path)).compile_module()
    sv = SchemaView(str(schema_path))
    root_class_name = next(name for name, c in sv.all_classes().items() if c.tree_root)
    py_target_class = python_module.__dict__[root_class_name]

    raw = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
    logger.info(f"[yaml_to_turtle] Raw YAML: {raw}")
    # Get extraction result relevant for TTL conversion.
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
    logger.debug("[yaml_to_turtle] YAML string before preprocessing: %s", yaml_str)
    # remove empty list and dict entries from YAML string to avoid linkml conversion errors
    yaml_str = re.sub(r"(?m)^(\s*)- null\s*$\n?", "", yaml_str)
    yaml_str = re.sub(r"(?m)^(\s*)- \{\}\s*$\n?", "", yaml_str)
    logger.debug("[yaml_to_turtle] YAML output: %s", yaml_str)
    # Convert to TTL using linkml
    obj = get_loader("yaml").load(source=yaml_str, target_class=py_target_class)
    ttl = get_dumper("ttl").dumps(obj, schemaview=sv)
    Path(ttl_path).write_text(ttl, encoding="utf-8")

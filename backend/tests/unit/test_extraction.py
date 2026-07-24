"""Unit tests for app.pipeline.extraction"""

import subprocess
from collections import defaultdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from app.pipeline.extraction import (
    clean_extraction,
    clean_result,
    extract_onto,
    fallback_id,
    is_valid_uri,
    name_fields_from_schema,
    normalize_unicode,
    uri_fields_from_schema,
)

SCHEMA_PATH = (
    Path(__file__).parent.parent.parent
    / "config"
    / "scholarySchema"
    / "extraction_schema.yaml"
)
# used for post processing tests
URI_FIELDS = uri_fields_from_schema(SCHEMA_PATH)
NAME_FIELDS = name_fields_from_schema(SCHEMA_PATH)


@pytest.fixture
def schema_file() -> Path:
    return SCHEMA_PATH


# Test URIValidator


class TestIsValidUri:
    def test_https_url(self):
        assert is_valid_uri("https://example.com") is True

    def test_http_url(self):
        assert is_valid_uri("http://doi.org/10.1234/foo") is True

    def test_url_with_path_and_query(self):
        assert is_valid_uri("https://orcid.org/0000-0002-1234-5678") is True

    def test_plain_text(self):
        assert is_valid_uri("not a uri") is False

    def test_auto_string(self):
        assert is_valid_uri("AUTO:123") is False

    def test_empty(self):
        assert is_valid_uri("") is False

    def test_ftp_scheme_rejected(self):
        assert is_valid_uri("ftp://example.com") is False

    def test_leading_whitespace_stripped(self):
        assert is_valid_uri("  https://example.com") is True

    def test_url_with_spaces_invalid(self):
        assert is_valid_uri("https://example.com/path with spaces") is False


# Test Unicode Normalization


class TestNormalizeUnicode:
    def test_ascii_passthrough(self):
        assert normalize_unicode("hello world") == "hello world"

    def test_em_dash_to_hyphen(self):
        assert normalize_unicode("A—B") == "A-B"

    def test_en_dash_to_hyphen(self):
        assert normalize_unicode("A–B") == "A-B"

    def test_minus_sign_to_hyphen(self):
        assert normalize_unicode("A−B") == "A-B"

    def test_ideographic_space_to_ascii(self):
        assert normalize_unicode("A　B") == "A B"

    def test_multiple_replacements_in_one_string(self):
        result = normalize_unicode("AI–Conference—2023")
        assert result == "AI-Conference-2023"

    def test_empty_string(self):
        assert normalize_unicode("") == ""

    def test_zero_width_space_stripped(self):
        assert normalize_unicode("hello​world") == "helloworld"

    def test_zero_width_non_joiner_stripped(self):
        assert normalize_unicode("foo‌bar") == "foobar"

    def test_zero_width_joiner_stripped(self):
        assert normalize_unicode("foo‍bar") == "foobar"

    def test_word_joiner_stripped(self):
        assert normalize_unicode("foo⁠bar") == "foobar"

    def test_null_byte_stripped(self):
        assert normalize_unicode("foo\x00bar") == "foobar"

    def test_newline_preserved(self):
        assert normalize_unicode("line1\nline2") == "line1\nline2"

    def test_tab_preserved(self):
        assert normalize_unicode("col1\tcol2") == "col1\tcol2"

    def test_mixed_invisible_and_dash(self):
        assert normalize_unicode("A​–​B") == "A-B"


# Test Fallback ID Generation


class TestFallbackId:
    def test_person_name_formats_as_lastname_initials(self):
        obj = {"name": "John Smith"}
        result = fallback_id(obj, ("name",))
        assert result.startswith("smo:Smith_J_")

    def test_three_part_name(self):
        obj = {"name": "Alice B. Chen"}
        result = fallback_id(obj, ("name",))
        assert result.startswith("smo:Chen_AB_")

    def test_single_word_name(self):
        obj = {"name": "Einstein"}
        result = fallback_id(obj, ("name",))
        assert result.startswith("smo:Einstein_")

    def test_fallback_to_other_field_when_no_name(self):
        obj = {"family_name": "Singla"}
        result = fallback_id(obj, ("name", "family_name"))
        assert result.startswith("smo:Singla_")

    def test_long_name_truncated_to_40_chars(self):
        obj = {"family_name": "A" * 50}
        result = fallback_id(obj, ("name", "family_name"))
        local_part = result[4:].rsplit("_", 1)[0]
        assert len(local_part) <= 40

    def test_empty_entity_uses_entity_label(self):
        obj = {}
        result = fallback_id(obj, ("name",))
        assert result.startswith("smo:entity_")

    def test_stable_given_same_input(self):
        obj = {"name": "Alice Chen"}
        assert fallback_id(obj, ("name",)) == fallback_id(obj, ("name",))

    def test_different_doc_name_produces_different_id(self):
        obj = {"name": "Y. Li"}
        r1 = fallback_id(obj, ("name",), doc_name="Paper1")
        r2 = fallback_id(obj, ("name",), doc_name="Paper2")
        assert r1 != r2

    def test_same_doc_name_produces_same_id(self):
        obj = {"name": "Y. Li"}
        r1 = fallback_id(obj, ("name",), doc_name="Paper1")
        r2 = fallback_id(obj, ("name",), doc_name="Paper1")
        assert r1 == r2

    def test_result_has_smo_prefix(self):
        obj = {"name": "Test User"}
        assert fallback_id(obj, ("name",)).startswith("smo:")

    def test_special_chars_stripped_from_local_part(self):
        obj = {"family_name": "O'Brien"}
        result = fallback_id(obj, ("name", "family_name"))
        local_part = result[4:].rsplit("_", 1)[0]
        assert "'" not in local_part

    def test_six_char_hex_digest(self):
        obj = {"name": "Test"}
        result = fallback_id(obj, ("name",))
        digest = result.rsplit("_", 1)[-1]
        assert len(digest) == 6
        assert all(c in "0123456789abcdef" for c in digest)


# Test Get URI fields


class TestUriFieldsFromSchema:
    EXPECTED_URI = {"url", "identifier"}
    EXPECTED_NON_URI = {
        "name",
        "family_name",
        "given_name",
        "org_name",
        "conf_name",
        "doi",
    }

    def test_returns_uri_slots(self, schema_file):
        result = uri_fields_from_schema(schema_file)
        assert self.EXPECTED_URI == result

    def test_excludes_string_and_non_uri_slots(self, schema_file):
        result = uri_fields_from_schema(schema_file)
        assert self.EXPECTED_NON_URI.isdisjoint(result)

    def test_doi_is_not_a_uri_field(self, schema_file):
        # currently doi has still range string (consider changing while developing)
        assert "doi" not in uri_fields_from_schema(schema_file)

    def test_returns_frozenset(self, schema_file):
        assert isinstance(uri_fields_from_schema(schema_file), frozenset)

    def test_empty_slots_gives_empty_frozenset(self, tmp_path):
        p = tmp_path / "s.yaml"
        p.write_text(yaml.dump({"slots": {}}))
        assert uri_fields_from_schema(p) == frozenset()

    def test_no_slots_key_gives_empty_frozenset(self, tmp_path):
        p = tmp_path / "s.yaml"
        p.write_text(yaml.dump({"classes": {}}))
        assert uri_fields_from_schema(p) == frozenset()


# Test Retrieve Name Fields


class TestNameFieldsFromSchema:
    EXPECTED_IN = {
        "name",
        "family_name",
        "given_name",
        "org_name",
        "conf_name",
        "title",
        "title_paper",
        "doi",
        "email",
    }
    # URI slots that must NOT appear
    EXPECTED_OUT = {"url", "identifier"}

    def test_returns_string_slots(self, schema_file):
        result = name_fields_from_schema(schema_file)
        assert self.EXPECTED_IN.issubset(set(result))

    def test_excludes_uri_slots(self, schema_file):
        result = name_fields_from_schema(schema_file)
        assert self.EXPECTED_OUT.isdisjoint(set(result))

    def test_returns_tuple(self, schema_file):
        assert isinstance(name_fields_from_schema(schema_file), tuple)

    def test_default_range_string_included(self, tmp_path):
        # Slots without an explicit range key default to string
        schema = {"slots": {"my_field": {}}}
        p = tmp_path / "s.yaml"
        p.write_text(yaml.dump(schema))
        assert "my_field" in name_fields_from_schema(p)


# Test Post Processing
class TestCleanResult:
    def _clean(self, obj, uri_fields=URI_FIELDS, name_fields=NAME_FIELDS):
        return clean_result(obj, uri_fields, name_fields, defaultdict(int))

    def test_invalid_uri_field_removed(self):
        result = self._clean({"identifier": "not-a-uri", "name": "Test"})
        assert "identifier" not in result

    def test_valid_uri_field_kept(self):
        result = self._clean(
            {"identifier": "https://orcid.org/0000-0001-2345-6789", "name": "Test"}
        )
        assert result["identifier"] == "https://orcid.org/0000-0001-2345-6789"

    def test_url_field_also_validated(self):
        result = self._clean({"url": "not-a-uri", "name": "Test"})
        assert "url" not in result

    def test_non_uri_field_not_validated(self):
        result = self._clean({"name": "plain text value"})
        assert result["name"] == "plain text value"

    def test_auto_id_replaced(self):
        # Test ontoGPT AUTO placeholder replacement
        obj = {"id": "AUTO", "name": "Alice"}
        result = self._clean(obj)
        assert result["id"] != "AUTO"
        assert result["id"].startswith("smo:")

    def test_empty_id_replaced(self):
        obj = {"id": "   ", "name": "Eve"}
        result = self._clean(obj)
        assert result["id"].startswith("smo:")

    def test_valid_id_preserved(self):
        obj = {"id": "smo:Smith_J_abc123", "name": "John"}
        result = self._clean(obj)
        assert result["id"] == "smo:Smith_J_abc123"

    def test_id_assigned_when_missing_but_name_present(self):
        obj = {"name": "Eve"}
        result = self._clean(obj)
        assert "id" in result
        assert result["id"].startswith("smo:")

    def test_no_id_assigned_when_no_name_fields(self):
        obj = {"unrelated_field": "value"}
        result = self._clean(obj)
        assert "id" not in result

    def test_none_items_removed_from_list(self):
        result = self._clean([None, {"name": "Alice"}])
        assert None not in result

    def test_empty_string_removed_from_list(self):
        result = self._clean(["", {"name": "Bob"}])
        assert "" not in result

    def test_empty_dict_removed_from_list(self):
        result = self._clean([{}, {"name": "John"}])
        assert {} not in result

    def test_auto_string_removed_from_list(self):
        result = self._clean(["AUTO:xyz", {"name": "Dave"}])
        assert not any(isinstance(i, str) and i.startswith("AUTO:") for i in result)

    def test_duplicate_ids_merged(self):
        items = [
            {"id": "smo:x_abc123", "name": "Alice", "email": None},
            {"id": "smo:x_abc123", "name": "Alice", "email": "a@example.com"},
        ]
        result = self._clean(items)
        assert len(result) == 1
        assert result[0]["email"] == "a@example.com"

    def test_duplicate_id_merge_prefers_nonempty_values(self):
        items = [
            {"id": "smo:y_abc123", "name": "Bob", "title": ""},
            {"id": "smo:y_abc123", "name": "Bob", "title": "Prof."},
        ]
        result = self._clean(items)
        assert result[0]["title"] == "Prof."

    def test_empty_list_values_dropped_from_dict(self):
        result = self._clean({"name": "Alice", "authors": []})
        assert "authors" not in result

    # Recursive Cleaning through YAML trees

    def test_nested_dict_cleaned_recursively(self):
        obj = {"person": {"id": "AUTO", "name": "Nested"}}
        result = self._clean(obj)
        assert result["person"]["id"].startswith("smo:")

    def test_string_values_normalized(self):
        result = self._clean("word–with—dashes")
        assert result == "word-with-dashes"

    def test_non_uri_field_unicode_normalized(self):
        result = self._clean({"name": "Conf–Name"})
        assert result["name"] == "Conf-Name"

    def test_uri_field_unicode_normalized_before_validation(self):
        # ensures probably valid uris are not dropped because of invalid symbols produced
        unicode_hyphen_uri = "https://orcid.org/0000‐0001‐2345‐6789"
        result = self._clean({"identifier": unicode_hyphen_uri})
        assert result["identifier"] == "https://orcid.org/0000-0001-2345-6789"


# File System Cleaning tests


class TestCleanExtraction:
    def test_auto_ids_replaced_in_place(self, schema_file, tmp_path):
        raw = {
            "authors": [
                {"id": "AUTO", "name": "John Doe"},
                {"id": "AUTO:xyz", "name": "Niklas Scholz"},
            ]
        }
        yaml_file = tmp_path / "out.yaml"
        yaml_file.write_text(yaml.dump(raw))

        clean_extraction(yaml_file, schema_file, doc_name="TestDoc")

        result = yaml.safe_load(yaml_file.read_text())
        for author in result["authors"]:
            assert not author["id"].startswith("AUTO")
            assert author["id"].startswith("smo:")

    def test_invalid_uris_removed(self, schema_file, tmp_path):
        raw = {"url": "not-a-uri", "name": "Test"}
        yaml_file = tmp_path / "out.yaml"
        yaml_file.write_text(yaml.dump(raw))

        clean_extraction(yaml_file, schema_file)

        result = yaml.safe_load(yaml_file.read_text())
        assert "url" not in result

    def test_valid_uri_preserved(self, schema_file, tmp_path):
        raw = {"url": "https://example.com", "name": "Test"}
        yaml_file = tmp_path / "out.yaml"
        yaml_file.write_text(yaml.dump(raw))

        clean_extraction(yaml_file, schema_file)

        result = yaml.safe_load(yaml_file.read_text())
        assert result["url"] == "https://example.com"

    def test_none_list_elements_removed(self, schema_file, tmp_path):
        raw = {"authors": [None, {"name": "Jane"}]}
        yaml_file = tmp_path / "out.yaml"
        yaml_file.write_text(yaml.dump(raw))

        clean_extraction(yaml_file, schema_file)

        result = yaml.safe_load(yaml_file.read_text())
        assert all(a is not None for a in result["authors"])

    def test_idempotent_on_clean_input(self, schema_file, tmp_path):
        raw = {"authors": [{"name": "John Doe"}]}
        yaml_file = tmp_path / "out.yaml"
        yaml_file.write_text(yaml.dump(raw))

        clean_extraction(yaml_file, schema_file, doc_name="Doc")
        first = yaml_file.read_text()
        clean_extraction(yaml_file, schema_file, doc_name="Doc")
        second = yaml_file.read_text()

        assert first == second

    def test_output_is_valid_yaml(self, schema_file, tmp_path):
        raw = {"title": "Some Paper", "authors": [{"name": "John Doe"}]}
        yaml_file = tmp_path / "out.yaml"
        yaml_file.write_text(yaml.dump(raw))

        clean_extraction(yaml_file, schema_file)

        parsed = yaml.safe_load(yaml_file.read_text())
        assert isinstance(parsed, dict)


# Basic Tests for OntoGPT
class TestExtractOnto:
    def test_calls_ontogpt_extract(self, tmp_path):

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            extract_onto(
                tmp_path / "paper.md",
                tmp_path / "schema.yaml",
                tmp_path / "out.yaml",
                model="test-model",
                api_base="https://api.example.com",
                api_key="sk-test",
            )

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ontogpt"
        assert "extract" in cmd
        assert "-m" in cmd
        idx = cmd.index("-m")
        assert cmd[idx + 1] == "test-model"
        env = mock_run.call_args[1]["env"]
        assert env["OPENAI_API_KEY"] == "sk-test"
        assert env["OPENAI_API_BASE"] == "https://api.example.com"

    def test_subprocess_error_propagated(self, tmp_path):
        # ensures application catch errors prroduced by subprocess
        from app.pipeline.extraction import extract_onto

        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "ontogpt"),
        ):
            with pytest.raises(subprocess.CalledProcessError):
                extract_onto(
                    tmp_path / "paper.md",
                    tmp_path / "schema.yaml",
                    tmp_path / "out.yaml",
                )

from pathlib import Path

import yaml
from pyoxigraph import NamedNode

PACO = "https://ontocurate.app/provenance-and-curation-ontology/"
PROV = "http://www.w3.org/ns/prov#"
SCHEMA = "http://schema.org/"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
XSD = "http://www.w3.org/2001/XMLSchema#"

RDF_TYPE = f"{RDF}type"
RDFS_LABEL = f"{RDFS}label"

XSD_STRING = f"{XSD}string"
XSD_INTEGER = f"{XSD}integer"
XSD_FLOAT = f"{XSD}float"
XSD_BOOLEAN = f"{XSD}boolean"
XSD_DATETIME = f"{XSD}dateTime"

# PACO classes
PACO_CANDIDATE = f"{PACO}CandidateStatement"
PACO_SOURCE_DOCUMENT = f"{PACO}SourceDocument"
PACO_CURATOR = f"{PACO}Curator"
PACO_EXTRACTION_ACTIVITY = f"{PACO}ExtractionActivity"
PACO_EDITING_ACTIVITY = f"{PACO}EditingActivity"
PACO_ACCEPTING_ACTIVITY = f"{PACO}AcceptingActivity"
PACO_REJECTING_ACTIVITY = f"{PACO}RejectingActivity"
PACO_CREATION_ACTIVITY = f"{PACO}CreationActivity"
PACO_RESETTING_ACTIVITY = f"{PACO}ResettingActivity"
PACO_CURATION_STATUS = f"{PACO}CurationStatus"
PACO_ALIGNMENT_ACTIVITY = f"{PACO}AlignmentActivity"

# PACO status individuals
PACO_PENDING = f"{PACO}pending"
PACO_ACCEPTED = f"{PACO}accepted"
PACO_REJECTED = f"{PACO}rejected"

# PACO agent individuals
PACO_ONTOGPT = f"{PACO}ontogpt"
PACO_ENTITY_ALIGNMENT = f"{PACO}entity-alignment"

# PACO object properties
PACO_SUBJECT = f"{PACO}subject"
PACO_PREDICATE = f"{PACO}predicate"
PACO_OBJECT = f"{PACO}object"
PACO_ORIGIN = f"{PACO}origin"
PACO_STATUS = f"{PACO}curationStatus"

# PACO data properties
PACO_TEXT_SPAN = f"{PACO}textSpan"
PACO_TEXT_SPAN_START = f"{PACO}textSpanStart"
PACO_TEXT_SPAN_END = f"{PACO}textSpanEnd"
PACO_CONFIDENCE = f"{PACO}confidence"
PACO_CREATED_AT = f"{PACO}createdAt"
PACO_EXTRACTED_AT = f"{PACO}extractedAt"
PACO_EDITED_AT = f"{PACO}editedAt"
PACO_ACCEPTED_AT = f"{PACO}acceptedAt"
PACO_REJECTED_AT = f"{PACO}rejectedAt"
PACO_RESET_AT = f"{PACO}resetAt"
PACO_MANUALLY_CREATED_AT = f"{PACO}manuallyCreatedAt"
PACO_CURRENT = f"{PACO}isCurrentVersion"
PACO_USERNAME = f"{PACO}username"
PACO_DELETED = f"{PACO}isDeleted"

# PROV classes
PROV_ACTIVITY = f"{PROV}Activity"
PROV_ENTITY = f"{PROV}Entity"
PROV_AGENT = f"{PROV}Agent"
PROV_SOFTWARE_AGENT = f"{PROV}SoftwareAgent"

# PROV properties
PROV_USED = f"{PROV}used"
PROV_ASSOCIATED_WITH = f"{PROV}wasAssociatedWith"
PROV_GENERATED_BY = f"{PROV}wasGeneratedBy"
PROV_DERIVED_FROM = f"{PROV}wasDerivedFrom"
PROV_GENERATED = f"{PROV}generated"
# Schema.org properties
SCHEMA_NAME = f"{SCHEMA}name"
SCHEMA_EMAIL = f"{SCHEMA}email"

# OWL properties
OWL_SAME_AS = f"{OWL}sameAs"

N_RDF_TYPE = NamedNode(RDF_TYPE)

N_XSD_STRING = NamedNode(XSD_STRING)
N_XSD_INTEGER = NamedNode(XSD_INTEGER)
N_XSD_FLOAT = NamedNode(XSD_FLOAT)
N_XSD_BOOLEAN = NamedNode(XSD_BOOLEAN)
N_XSD_DATETIME = NamedNode(XSD_DATETIME)

# PACO classes
N_PACO_CANDIDATE = NamedNode(PACO_CANDIDATE)
N_PACO_SOURCE_DOCUMENT = NamedNode(PACO_SOURCE_DOCUMENT)
N_PACO_CURATOR = NamedNode(PACO_CURATOR)
N_PACO_EXTRACTION_ACTIVITY = NamedNode(PACO_EXTRACTION_ACTIVITY)
N_PACO_ACCEPTING_ACTIVITY = NamedNode(PACO_ACCEPTING_ACTIVITY)
N_PACO_ALIGNMENT_ACTIVITY = NamedNode(PACO_ALIGNMENT_ACTIVITY)

# PACO status individuals
N_PACO_PENDING = NamedNode(PACO_PENDING)
N_PACO_ACCEPTED = NamedNode(PACO_ACCEPTED)

# PACO agent individuals
N_PACO_ONTOGPT = NamedNode(PACO_ONTOGPT)
N_PACO_ENTITY_ALIGNMENT = NamedNode(PACO_ENTITY_ALIGNMENT)

# PACO object properties
N_PACO_SUBJECT = NamedNode(PACO_SUBJECT)
N_PACO_PREDICATE = NamedNode(PACO_PREDICATE)
N_PACO_OBJECT = NamedNode(PACO_OBJECT)
N_PACO_ORIGIN = NamedNode(PACO_ORIGIN)
N_PACO_STATUS = NamedNode(PACO_STATUS)

# PACO data properties
N_PACO_TEXT_SPAN = NamedNode(PACO_TEXT_SPAN)
N_PACO_TEXT_SPAN_START = NamedNode(PACO_TEXT_SPAN_START)
N_PACO_TEXT_SPAN_END = NamedNode(PACO_TEXT_SPAN_END)
N_PACO_CONFIDENCE = NamedNode(PACO_CONFIDENCE)
N_PACO_CREATED_AT = NamedNode(PACO_CREATED_AT)
N_PACO_EXTRACTED_AT = NamedNode(PACO_EXTRACTED_AT)
N_PACO_ACCEPTED_AT = NamedNode(PACO_ACCEPTED_AT)
N_PACO_RESET_AT = NamedNode(PACO_RESET_AT)
N_PACO_MANUALLY_CREATED_AT = NamedNode(PACO_MANUALLY_CREATED_AT)
N_PACO_CURRENT = NamedNode(PACO_CURRENT)
N_PACO_USERNAME = NamedNode(PACO_USERNAME)
N_PACO_DELETED = NamedNode(PACO_DELETED)

# PROV classes
N_PROV_ACTIVITY = NamedNode(PROV_ACTIVITY)
N_PROV_ENTITY = NamedNode(PROV_ENTITY)
N_PROV_AGENT = NamedNode(PROV_AGENT)
N_PROV_SOFTWARE_AGENT = NamedNode(PROV_SOFTWARE_AGENT)

# PROV properties
N_PROV_USED = NamedNode(PROV_USED)
N_PROV_ASSOCIATED_WITH = NamedNode(PROV_ASSOCIATED_WITH)
N_PROV_GENERATED_BY = NamedNode(PROV_GENERATED_BY)
N_PROV_DERIVED_FROM = NamedNode(PROV_DERIVED_FROM)
N_PROV_GENERATED = NamedNode(PROV_GENERATED)

# Schema.org
N_SCHEMA_NAME = NamedNode(SCHEMA_NAME)
N_SCHEMA_EMAIL = NamedNode(SCHEMA_EMAIL)

# OWL
N_OWL_SAME_AS = NamedNode(OWL_SAME_AS)


def create_source_document_entity(document_key: str) -> NamedNode:
    """Return a PROV Entity NamedNode representing a source document."""
    return NamedNode(f"{DOCUMENTS}{document_key}")


# Instance-IRI roots. Workspace-agnostic (workspace scoping lives in the named
# graph, not the IRI) since the ontocurate.app rename, so -- unlike before --
# a single static prefix can cover every workspace's candidate statements,
# activities, documents, and users. Activities are split per verb rather than
# one flat "activities/" root: a CURIE's local part can't contain further
# slashes, and every activity IRI has a verb segment before its uuid
# (".../activities/accept/{uuid}"), so a flat root could never actually
# abbreviate any of them -- splitting is what makes abbreviation possible at
# all, and the prefix doubles as a hint of the activity's type.
CANDIDATE_STATEMENTS = "https://ontocurate.app/candidate-statements/"
ACCEPT_ACTIVITIES = "https://ontocurate.app/activities/accept/"
REJECT_ACTIVITIES = "https://ontocurate.app/activities/reject/"
EDIT_ACTIVITIES = "https://ontocurate.app/activities/edit/"
RESET_ACTIVITIES = "https://ontocurate.app/activities/reset/"
EXTRACTION_ACTIVITIES = "https://ontocurate.app/activities/extraction/"
ALIGNMENT_ACTIVITIES = "https://ontocurate.app/activities/alignment/"
CROSS_DOCUMENT_ALIGNMENT_ACTIVITIES = (
    "https://ontocurate.app/activities/cross-document-alignment/"
)
DOCUMENTS = "https://ontocurate.app/documents/"
USERS = "https://ontocurate.app/users/"

# Base namespace -> prefix for the platform's own vocabulary and instance
# IRIs. Domain ontologies (schema.org, dcterms, a workspace's own extraction
# schema, ...) come from that workspace's LinkML schema instead -- see
# build_prefix_map.
BASE_PREFIXES: dict[str, str] = {
    PACO: "paco",
    PROV: "prov",
    SCHEMA: "schema",
    RDF: "rdf",
    RDFS: "rdfs",
    OWL: "owl",
    XSD: "xsd",
    CANDIDATE_STATEMENTS: "stmt",
    ACCEPT_ACTIVITIES: "accept",
    REJECT_ACTIVITIES: "reject",
    EDIT_ACTIVITIES: "edit",
    RESET_ACTIVITIES: "reset",
    EXTRACTION_ACTIVITIES: "extraction",
    ALIGNMENT_ACTIVITIES: "alignment",
    CROSS_DOCUMENT_ALIGNMENT_ACTIVITIES: "cross-document-alignment",
    DOCUMENTS: "doc",
    USERS: "user",
}


def build_prefix_map(schema_path: str | None) -> dict[str, str]:
    """Merge BASE_PREFIXES with the prefixes declared in a workspace's LinkML
    extraction schema (its `prefixes:` block), so CURIE-shortening also covers
    that workspace's own domain ontology and whatever vocabularies it reuses
    (schema.org, dcterms, foaf, ...). Falls back to BASE_PREFIXES alone if the
    schema can't be read. The platform's own namespaces always win a collision.
    """
    merged = dict(BASE_PREFIXES)
    if schema_path:
        try:
            raw = yaml.safe_load(Path(schema_path).read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            raw = {}
        for prefix, namespace in (raw.get("prefixes") or {}).items():
            merged.setdefault(namespace, prefix)

    # Longest namespace first so a more specific match always wins over a
    # shorter one it happens to start with.
    return dict(sorted(merged.items(), key=lambda item: -len(item[0])))


def shorten_uri(uri: str, prefixes: dict[str, str] = BASE_PREFIXES) -> str:
    """Abbreviate a URI to a prefix:localName CURIE if its namespace is known,
    otherwise return it unchanged."""
    for namespace, prefix in prefixes.items():
        if uri.startswith(namespace):
            return f"{prefix}:{uri[len(namespace):]}"
    return uri


def shorten_sparql_results(
    payload: dict, prefixes: dict[str, str] = BASE_PREFIXES
) -> dict:
    """Replace URI-typed binding values, and literal datatypes, in a SPARQL
    results JSON payload with prefixed CURIEs where possible. Mutates and
    returns the given payload."""
    for binding in payload.get("results", {}).get("bindings", []):
        for value in binding.values():
            if value.get("type") == "uri":
                value["value"] = shorten_uri(value["value"], prefixes)
            elif "datatype" in value:
                value["datatype"] = shorten_uri(value["datatype"], prefixes)
    return payload


def format_sparql_response(payload: dict) -> dict | bool:
    """Reshape a SPARQL results JSON payload into a minimal response: a bare
    boolean for ASK, or {"variables": [...], "rows": [...]} for SELECT --
    dropping the SPARQL protocol's "head"/"results" envelope, which callers
    of this API have no use for."""
    if "boolean" in payload:
        return payload["boolean"]
    return {
        "variables": payload.get("head", {}).get("vars", []),
        "rows": payload.get("results", {}).get("bindings", []),
    }

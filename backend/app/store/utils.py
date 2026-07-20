from pyoxigraph import NamedNode

PACO = "https://example.org/provenance-and-curation-ontology/"
PROV = "http://www.w3.org/ns/prov#"
SCHEMA = "https://schema.org/"
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

# OWL
N_OWL_SAME_AS = NamedNode(OWL_SAME_AS)


def create_source_document_entity(workspace_id: str, document_key: str) -> NamedNode:
    """Return a PROV Entity NamedNode representing a source document."""
    return NamedNode(
        f"https://example.org/workspaces/{workspace_id}/documents/{document_key}"
    )

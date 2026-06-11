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
PACO_CURATION_STATUS = f"{PACO}CurationStatus"

# PACO status individuals
PACO_PENDING = f"{PACO}pending"
PACO_EDITED = f"{PACO}edited"
PACO_ACCEPTED = f"{PACO}accepted"
PACO_REJECTED = f"{PACO}rejected"

# PACO agent individuals
PACO_ONTOGPT = f"{PACO}ontogpt"

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

# Schema.org properties
SCHEMA_NAME = f"{SCHEMA}name"

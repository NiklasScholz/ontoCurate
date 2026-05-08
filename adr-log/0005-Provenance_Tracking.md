# Use PROV-O based immutable statement versioning for provenance and curation

## Context and Problem Statement

The system extracts RDF candidate statements from uploaded PDF documents using OntoGPT. These statements can later be edited, accepted, rejected, or manually created by multiple users. The system therefore requires provenance tracking and support for curation history without losing previous statement versions.

## Considered Options

* Mutable statements with in-place updates
* Reified RDF statements
* Named graphs
* Immutable statement versioning with PROV-O

## Decision Outcome

Immutable statement versioning with PROV-O. Each extraction or curation action generates a new `paco:CandidateStatement` linked to previous versions via `prov:wasDerivedFrom`. Provenance activities are modeled using PROV-O concepts such as `prov:Activity`, `prov:Entity`, and `prov:Agent`.

Only statements with:
* `paco:curationStatus = accepted`
* `paco:isCurrentVersion = true`

are materialized into the final knowledge graph.

Named graphs were considered as an alternative provenance mechanism. However, since provenance and curation must be tracked at the level of individual statements rather than entire graph fragments, named graphs were considered less suitable for the collaborative editing workflow.

### Consequences

* The full extraction and curation history remains traceable
* Multiple users can collaboratively curate statements without overwriting previous versions
* The ontology remains interoperable with existing Semantic Web provenance standards
* The versioning approach increases the number of stored statement instances
* Statement-level provenance is easier to manage than graph-level provenance in collaborative curation workflows
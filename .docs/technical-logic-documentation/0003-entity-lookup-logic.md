# Entity Lookup Logic

## Overview
Entity Lookup grounds extracted entities against external knowledge bases so curators can confirm that, e.g., a `Person` extracted from a paper corresponds to a specfic real-world identity. It runs after cross-document alignment, reading the `merged.ttl` produced by that stage (falling back to per-document TTLs if no merge happened). This order is chosen to reduce the number of workers requiring to query external APIs taking a longer time to not block resources. 

In the current state, we support two lookup services, but our architecture allows for easy extensions. 

**ORCID** (for `Person` entities) is used when enough information (e.g. name+affiliation or name+doi of a paper) is available. **Wikidata** can be used for any configured entity type as described below. Both services share the same structure, facilitating easy onboarding of new lookup services. 
The four-steps are as follows: candidate generation $\rightarrow$ similarity scoring $\rightarrow$ threshold filtering $\rightarrow$ writing to the provenance graph.

ORCID is queried first such that likely matches can be used to derive the wikidata connection immediately (if ORCID is present in wikidata). This helps resolving ambiguous name matches.  

---

## Configuration
Each schema comes along with a single `lookup_config.yaml` file that is fully decoupled from the entity alignment config (`alignment_config.yaml`) allowing for external knowledge base specific thresholding. However, similarity metrics are shared across these changes (hence refer to [entity alignment config](0002-entity-alignment-logic.md#configuration) for similarity logic)

The schema has up to three top-level sections: `literal_derivation` (shared by all sources), `wikidata_lookup`, and `orcid_lookup`. The latter two each declare their own `settings` (source-level defaults) and `entity_types` (per-type overrides), mirroring the `settings` / `entity_types` split that is used by the [entity alignment config](0002-entity-alignment-logic.md#configuration).

```yaml
literal_derivation:
  Person:
    - as: orcid
      from_literal: identifier
    - as: doi
      from_relation_in: author
      relation_literal: doi
    - as: affiliation
      from_relation_out: affiliation
      relation_literal: name

wikidata_lookup:
  settings:
    candidate_limit: 5
    language: en
    request_delay_seconds: 0.1
    default_threshold: 0.8
    default_weights:
      syntactic: 0.7
      semantic: 0.3
    default_comparison_predicates:
      - name
    default_semantic_text_predicates:
      - name
    default_expand_initials: false

  entity_types:
    Person:
      require_any_of:
        - givenName
      instance_of:
        - Q5  # human
      search_queries:
        - predicates: [givenName, familyName]
          require_all: true
          join_with: " "
        - predicates: [name]
      candidate_literals:
        name:
          - source: label
          - source: aliases
        orcid:
          - source: string_claims
            property: P496
      scoring:
        threshold: 0.98
        weights:
          syntactic: 1.0
          semantic: 0.0
        comparison_predicates: [name]
        semantic_text_predicates: [name]
        hard_match_predicates:
          name: 0.98
        unresolved_orcid_penalty: 0.4
        fuzzy_match_penalty: 0.1

orcid_lookup:
  settings:
    candidate_limit: 5
    request_delay_seconds: 0.1
    field_names:
      givenName: given-names
      familyName: family-name
      name: text
      doi: digital-object-ids
      affiliation: current-institution-affiliation-name

  entity_types:
    Person:
      require_any_of: [doi, affiliation]
      search_queries:
        - predicates: [familyName, doi]
          require_all: true
        - predicates: [givenName, familyName]
          require_all: true
          join_with: " "
      scoring:
        threshold: 0.9
        weights: { syntactic: 1.0, semantic: 0.0 }
        comparison_predicates: [name]
        semantic_text_predicates: [name]
        hard_match_predicates:
          orcid: 1.0
        unresolved_orcid_penalty: 0.4
        fuzzy_match_penalty: 0.05
```

An entity type with no `entity_types` entry under a given source is skipped entirely for that source. Hence, if one wants to match Proceedings or similiar to wikidata as well, one has to add a respective entry with specific configurations described below. 

### Literal derivation
Local entities often lack the fields needed to reconcile against an external source directly on their own literals (e.g. a `Person`'s affiliation lives on a related `Organization` node, not on the `Person` itself). `literal_derivation`, keyed by entity type, copies such values before running the lookup task. 
- **`from_literal`**: takes an existing literal on the entity itself (stripping any URI prefix down to its last path segment), useful for e.g. turning a full ORCID URI extracted as `identifier` into a bare `orcid` literal.
- **`from_relation_in`** / **`from_relation_out`**: follows an incoming or outgoing relation to a related entity, then reads `relation_literal` off that related entity (e.g. follow the reverse `author` relation from a `Person` to the `AcademicArticle` that lists them, and copy its `doi`).

Derived values are deduplicated and written to the literal name given by `as`.

### Per-entity-type keys
- **`require_any_of`**: a list of literal name of which at least one is required otherwise the lookup for this entity is skipped. This is useful if no information is available that may help disambiguite the user and resolves ambiguous matches (e.g. F. Chen)
- **`instance_of`** *(Wikidata only)*: a list of Wikidata QIDs. A candidate is rejected unless it is an instance of (`P31`) at least one of these. This ensures that a conference named "Artificial Intelligence" is not suddenly matched against a movie. 
- **`search_queries`**: This is the list of rules used to build search queries for the entity (see [Candidate Generation](#stage-1-candidate-generation)).
- **`candidate_literals`** *(Wikidata only)*: maps a local literal name to one or more Wikidata property sources used to build a comparable candidate (see [Candidate Literal Extraction](#candidate-literal-extraction-wikidata)).
- **`field_names`** *(ORCID `settings` only)*: maps local literal names to ORCID API field names used when constructing search queries (e.g. local `familyName` $\rightarrow$ ORCID `family-name`). Without these matches it would merely be impossible to query ORCID schema agnostically. 
- **`scoring`**: the same weighted-metric config block used by entity alignment (`threshold`, `weights`, `comparison_predicates`, `semantic_text_predicates`, `expand_initials`, `sparsity_penalty`, `sparsity_max_fields`, `hard_match_predicates` - see [entity alignment scoring](0002-entity-alignment-logic.md#stage-2-similarity-scoring)), plus one lookup-specific key:
  - **`unresolved_orcid_penalty`**: a multiplier penalty (`score *= 1 - penalty`) applied when a candidate was produced by falling back to fuzzy search after an extracted ORCID failed to resolve to a real record.
  - **`fuzzy_match_penalty`**: a multiplier penalty applied to any candidate that came from fuzzy label/query search rather than a direct identifier verification. This shows users to pay particular attention to these matches.

---

## Stage 1: Candidate Generation
For each entity, candidates are only generated if its type has an `entity_types` entry for that source and it passes the `require_any_of` gate (or already carries a known `orcid`).

### Search query construction
Both clients build search queries from the `search_queries` rule list:
- Each rule declares `predicates`, i.e. the literal names to get values from, and, optionally, `optional_predicates` (added to the query only if present and desired, but never required).
- **`require_all: true`** means the rule only triggers if every listed predicate has at least one value; otherwise it yields no queries and the next rule in `search_queries` is tried instead.
- Rules are tried in the order declared, and each yields zero or more queries; all of them are issued with duplicate queries being surpressed through a set keeping track of all seen queries.
- `request_delay_seconds` is slept between each query issued, as desired by API providers. 

### Known-identifier fast path
If an entity already has a known ORCID (from source-text extraction or, for Wikidata, one confirmed by a prior ORCID lookup stage), fuzzy search is eventually skipped and a direct verificiation lookup is performed first:
- **ORCID**: `fetch_orcid_record` calls the ORCID record API directly to check for existence
- **Wikidata**: `search_wikidata_by_orcid` runs a SPARQL query for an item with a matching `wdt:P496` (ORCID) claim. 

If the identifier fails to resolve, the client falls back to the normal fuzzy `search_queries` flow, but flags every resulting candidate with `orcid_unresolved: true` so scoring can penalize it. This ensures that these unresolved matches do not appear as owl:sameAs links. 

### Candidate literal extraction (Wikidata)
For each raw Wikidata search hit, `fetch_wikidata_entity_details` retrieves the item's full claims, then:
1. **Class filter**: the item is removed unless it is an instance of one of the configured `instance_of` QIDs (e.g. Q5 for human)
2. **Literal extraction**: for each literal declared under `candidate_literals`, values are pulled from the wikidata entry returned:
   - `label`: the search result's label 
   - `aliases`: the item's aliases in the configured `language` 
   - `string_claims`: string-valued claims for a given Wikidata `property`
   - `item_claim_labels`: for an item-valued claim, it resolves each referenced item to its label (cached)

The result is a candidate dict with `uri`, `label`, `description`, and `literals`, which can then be used for scoring

### Candidate literal extraction (ORCID)
ORCID candidates are built directly from the API response to perform scoring. 

---

## Stage 2: Similarity Scoring
Scoring reuses the exact same `combined_similarity` function as [entity alignment](0002-entity-alignment-logic.md#stage-2-similarity-scoring) (syntactic, semantic, but implicit zero structural similarity). The lookup stage only has two additional logics involved in the stage: 

### Unresolved ORCID handling
If a candidate was produced via the fuzzy-search fallback after a known ORCID iD failed to resolve (`orcid_unresolved: true`), its score is multiplied by `1 - unresolved_orcid_penalty` before threshold filtering. This removes any untrustworthy lookups that a user could not verify on their own. 

### Fuzzy match handling
Every candidate produced by the fuzzy `search_queries` path (as opposed to the known-identifier fast path) is flagged `fuzzy_match: true` — this includes both entities with no known identifier at all and entities whose known ORCID failed to resolve and fell back to fuzzy search (so both penalties can stack on the same candidate). Unlike `unresolved_orcid_penalty`, the `fuzzy_match_penalty` multiplier is applied *after* the threshold check passes, not before: it lowers the confidence score written to the provenance graph without affecting whether the candidate clears the threshold in the first place. This keeps fuzzy matches from being filtered out purely for lacking identifier verification, while still surfacing them to curators as comparatively less certain.

### ORCID-to-Wikidata
When an ORCID-lookup result is above a threshold, its `orcid` literal is copied into the entity information dictionary before wikidata runs. This lets Wikidata attempt the identifier fast path (SPARQL `P496` match) for entities that had no ORCID in the source text but where a likely orcid was found. 
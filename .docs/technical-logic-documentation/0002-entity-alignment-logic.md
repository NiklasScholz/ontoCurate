# Entity Alignment Logic

## Overview
During Entity Alignment entities extracted from the same (when ontoGPT failed producing the same entity) or different documents that refer to the same real-world entity need to be identified and linked via  `owl:sameAs` triples for humans to review. 
Hence, 2 tasks of our pipeline make use of this stage: **inner-document** and **cross-document** alignment. 
The pipeline of Entity Alignment consists of four sequential stages: candidate generation $\rightarrow$ similarity scoring $\rightarrow$ threshold filtering $\rightarrow$ writing to provenance graph. 

---

## Configuration 
Each schema comes along with a single YAML config file that drives the entity alignment.
**settings** defines the default values, while **entity_types** allows to override those settings with different thresholds, weights or fields. 
It is important that:
- Weights across the three metrics (syntactic, semantic, structural) must sum to 1.0 (validated at loading time)
- **`unique_keys`** must globally identify entities with certainty (skips the alignment pipeline and aligns on its own)
- Setting a metric weight to `0.0` skips that metric entirely 

```yaml
settings:
  # Minimum combined score required to emit an owl:sameAs triple
  default_threshold: 0.8

  # Metric weights
  default_weights:
    syntactic: 0.6
    semantic: 0.3
    structural: 0.1

  # Fields used for syntactic string comparison by default
  default_comparison_predicates:
    - name

  # Fields concatenated for embedding-based semantic comparison by default
  default_semantic_text_predicates:
    - name

  # Whether single-character tokens are treated as initials during syntactic matching
  default_expand_initials: false

  # Unique identifier fields: shared value forces a match; conflicts lead to exclusion
  unique_keys:
    - doi
    - email
    - issn

entity_types:
  # Override any subset of settings per entity type; unused keys fall back to defaults above
  Person:
    threshold: 0.75
    weights:
      syntactic: 0.7
      semantic: 0.0      
      structural: 0.3
    comparison_predicates:
      - family_name
      - name
      - email
    semantic_text_predicates:
      - name
      - given_name
      - family_name
    expand_initials: true  # "J. Doe" matches "John Doe"

  Conference:
    threshold: 0.88
    weights:
      syntactic: 0.45
      semantic: 0.45
      structural: 0.1
    comparison_predicates:
      - conf_name
      - location
    semantic_text_predicates:
      - conf_name
      - location
```

---

## Stage 1: Candidate Pair Generation (Blocking)
To reduce the number of candidates, we make use of grouping by types. This means that only entities of the same RDF type are compared (even if they belong to the same type hierachy). If ontoGPT does not believe them to be of the same type, the chance is low that they woudld actually be. If only one entity exists for a type, it is not used during entity alignment.
Additionally, if entities in a bucket have a `unique_key` field (e.g. doi), matches are immediately produced and conflicts dropped without scoring
Deduplication of the buckets by URI ensures to not evaluate the same pair multiple times.

---

## Stage 2: Similarity Scoring
For each candidate pair, the system computes a **combined similarity score** (0.0-1.0) as a weighted sum of three metrics. The weights are determined by the config.

### Syntactic Similarity
Syntactic similarity looks at the **string forms** of configured `comparison_predicates`fields. For each field it takes the best-scoring pair across all value combinations (if multiple values exist for the predicate). Predicates missing are dropped. For scoring, there exist two modes: **Expand_initials: false** is the default string comparison version utilizing token-sorten fuzzy ratio matching on normalised tokens. **Expand_initials: true** treats single character tokens as initials (that can match any longer token sharing its prefix). This is useful for names when comparing Persons like "J. Doe" and "John Doe".

### Semantic Similarity
For semantic similarity we utilize text embeddings from KI Connnect NRW (model: `qwen3-embedding-8b`, configurable via the environment variable `EMBEDDING_MODEL`). To produce embeddigns we concatenate the values of `semantic_text_predicates` that are present in both entities. Then, cosine similarity between the two embedding vectors is produced. 

### Structural Similarity
During structural similarity, we measure the predicate overlap, i.e. how many predicates the two entities share, divided by the size of the smaller predicate set. Returns a default value of 0.4 to ensure it does not drag down the score when data is sparse.

---

## Stage 3-4: Threshold Filtering & Write to Provenance
Pairs that are above the entity-specific or default threshold (depending on the config) are considered as the same real-world entity with a certain confidence score. 

For **inner-document alignment**, the sameAs triple is appended to the single source TTL of that document.

For **cross-document alignment**, all per-document TTLs are merged into a single `merged.ttl` in the working directory, and the sameAs triples are appended to it. Further pipeline tasks (e.g. lookup) can read this one file to resolve cross-document alignments without querying Oxigraph.

This ensures that further tasks do not need to block the oxigraph data storage while users may want to have access.
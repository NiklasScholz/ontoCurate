# Cross-Document & Per-Document Entity Alignment

## Context and Problem Statement
Per-Document extraction assigns a new URI to every entity it encounters. The same entity extracted from different papers (or within the same paper)
may receive different URIs and likely appear as separate nodes in the merged graph. An entity alignment stage is required to detect those duplicates and link them via `owl:sameAs`. 
For example, the alignment must handle name variations (initials, reversed order, hyphenation, middle names). At the same time, it needs to be flexible towards any schema. 
Much research has been put into Representational Learning and producing ML-based models. However, this does not work well for our scholarly use case and does typically not work without GPUs. Hence, those options are not considered at all. 
To allow easy export of document-specific KGs we will only link with `owl:sameAs` and not deduplicate in the pipeline.

## Considered Options
### Option 1: JedAI
- Java-based entity resolution framework with wide range of blocking and matching strategies

| Pros | Cons |
|------|------|
| Offers many strategies | Java runtime dependency |
|  | Complex setup and interop with Python pipeline |
| | Adds significant overhead for a single pipeline stage |

### Option 2: Embedding-based Similarity
- Encode entity labels as vectors
- Cluster them or use cosine similarity 

| Pros | Cons                                                         |
|------|--------------------------------------------------------------|
| Captures semantic similarity | Requires an embedding model dependency                       |
| Handles paraphrasing and abbreviations | Less interpretable                                           |
| | Things like "ISWC 2023" and "ISWC 2024" may cluster together |
| | Higher inference cost per entity pair                        |

### Option 3: LLM-based Resolution
Much recent research has been put into LLM-based frameworks checking whether two entities refer to the same real-world entity.

| Pros                         | Cons                                                           |
|------------------------------|----------------------------------------------------------------|
| Can handle complex cases     | One API call per candidate pair (or potential missing linkage) |
| No threshold tuning required | Non-deterministic                                              |
| Flexible                     | Expensive and slow (especially in combination with ontoGPT)    |

### Option 4: Custom Blocking + Fuzzy Matching (chosen)
- **Blocking**: Only compare entities (of the same class) that share similar labels (e.g. for authors only consider those with same family name)
- **Hard blocks**: If rule-based conflicts in other parts occur (e.g., inconsistent initials) they receive much lower score
- **Confidence Score**: Fuzzy Matching libraries typically provide a similarity score that we use as confidence values.
- Thresholds will be determined through testing 
- Entities with same identifiers (e.g. doi, orcid, email) will immediately be linked

| Pros                                     | Cons                                                                                   |
|------------------------------------------|----------------------------------------------------------------------------------------|
| No external dependencies                 | Thresholds are empirically tuned on a small document set and may not generalise        |
| Transparent, testable procedure          | Blocking may miss pairs with no shared similarity (e.g., full name vs initials)        |
| Deterministic                            | Config will be required to specify rules for specific classes                          |
|                             | Relations are not considered (e.g., what if "same" author has different institutions?) |
| | No semantic context captured                                                           |


## Decision Outcome
**Option 4: Custom Blocking + Fuzzy Matching** is chosen. It is the only option that provides full control, transparency and does not require additional computational resources or API calls.
Alignment decisions will be added to the Provenance Graph as `owl:sameAs` links with associated confidence scores for the user to review.
Theoretically, the linking module can easily be extended, as it will be implemented as its own module. 


## Consequences

### Positive Consequences
- Fully deterministic entity alignment that can be reproduced 
- Hard guards to avoid dangerous failures
- No silent merges, but human-in-the-loop verification
- No model, runtime, or API dependency beyond Python standard

### Negative Consequences
- Threshold tuning may become complex $\rightarrow$ possible FPs or FNs on different schemas or untested documents
- Potential misses in matches due to blocking
- No semantic understanding

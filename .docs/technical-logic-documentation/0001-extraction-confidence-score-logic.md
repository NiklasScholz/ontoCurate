# Confidence Scores during Extraction

We do not rely on LLMs for producing confidence scores, as they have been proven to be producing overly confident scores alongside their decisions. Hence, we utilize the confidence annotation part of our pipeline to gather syntac similarity confidence scores. All these scores are used to indicate the plausibility of the LLM response based on the source text.

We provide confidence scores for both **Datatype Properties** and **Object Properties**. For Datatype Properties, syntactic span matching against the source text is primarily used (with additional penalities). For Object Properties no syntactic match can be found (both subject and object are entities, not literal text spans). Instead, scoring is based on signals derived from the literal annotations of the connected entities such as how close they appear in the document, or whether the target entity is mentioned in an expected section. We primarily utilize the literal confidence scores of target/source entity with additional penalities. The downsight of this approach is that confidence scores relying on the semantics of the predicate (e.g. outperforms vs. hasEqualPerformance) are not supported in a good way. For the primary scholarly use case, this is not needed. When adapting to other schemas it can be reconsidered to include new strategies. 

**rdf:type** Triples get the average confidence score of all of their associated literals. 

## Confidence Scores for Datatype Properties

### Configuration
Each schema comes alongside with a `provenance_config.yaml` file, which allows defining certain rules for predicates and entities making the confidence score more flexible towards the respective domain.

**Shared penalty settings** (apply to both datatype and object property scoring):

```yaml
settings:
  out_of_window_penalty: 0.8  # applied when a span match falls outside the declared window
  win_distance_penalty: 1.0   # scales additional penalty by relative distance to nearest window
  min_penalty_factor: 0.3     # floor on any distance-based penalty factor
```

**Datatype property config** is nested under `datatype_properties:`:

```yaml
datatype_properties:
  # Outlier penalty for literal triples of the same entity
  outlier_penalty: 1.0
  min_outlier_factor: 0.2
  outlier_pentalty_entities:
    - Person
    - Organization
    - AcademicArticle

  windows:
    title_paper:
      - strategy: head
        chars: 400
      - strategy: section
        heading: "References"
    abstract:
      strategy: section
      heading: "Abstract"
    name:
      - strategy: head
        chars: 1000
      - strategy: section
        heading: "References"
```

- **windows**: per-predicate window declarations. A predicate can declare a single window or a list — when multiple are declared the highest-confidence match across all windows wins. Supported strategies: `head` (first N chars), `tail` (last N chars), `section` (search for markdown heading), `full` (entire document, default).
- **outlier_pentalty_entities**: only entities whose `rdf:type` local name appears in this list are subject to the outlier penalty.
          

### Rule-based Tier Confidence Annotation: 
The maximum scores from all the tiers is returned 

#### Tier 1: Exact Matches
Exact String Matches within the window (if provided) directly yields a confidence score of 1.0

#### Tier 2: Case Insenstive Matches
Case Insenstive matches within the window yield a confidence score of 0.95

#### Tier 3: Normalized Whitespace Match
After cleaning white space and new lines (incl. intra-word) a confidence score of 0.9 is returned for matches

#### Tier 4: Abbreviation Match:
If partial abbreviations were found (e.g. KG Graph for Knowledge Graph) a confidence score of 0.75 is returned 

#### Tier 5: Fuzzy Matches:
On sentence level partial_ratio from rapidfuzz is provided (if best sentence score is >= 50). It expects to find a partial matching sentence in source of target length. 

### Penalities to Out-Of-Window & Outliers
- Matches found outside all windows of the predicate retrieve a penalty of 'out_of_window_penalty' plus an optional distance penalty (i.e. normalized distance to nearest window). 
- Outlier Penalty: For each entity of configured type, the median span starts are computed. Depending on the distance to the median additional penalties are applied (if configured). This ensures that authors are closely connected to Organizations. 


## Confidence Scores for Object Properties

Scoring is strategy-based, selected per predicate via the `provenance_config.yaml`. The strategy determines how the confidence of an object property triple is derived from the literal annotations of the involved entities.

### Configuration

```yaml
object_properties:
  default_strategy: average_target_entity_confidence

  # cooccurrence tuning settings
  cooccurrence_distance_penalty: 1.0
  cooccurrence_min_factor: 0.3
  cooccurrence_outlier_penalty: 1.0
  cooccurrence_min_outlier_factor: 0.2

  predicates:
    author:
      strategy: spatial_cooccurrence
      apply_outlier_penalty: true
    affiliation:
      strategy: spatial_cooccurrence
    cites:
      strategy: section_containment
      sections:
        - "References"
        - "Bibliography"
```

- **default_strategy**: fallback strategy for predicates not listed under `predicates`.
- **cooccurrence_distance_penalty / cooccurrence_min_factor**: control how much weight the penalty of distance between source and target entity has `spatial_cooccurrence` predicates (limits penalty down to min_factor).
- **cooccurrence_outlier_penalty / cooccurrence_min_outlier_factor**: control the outlier penalty applied after scoring (see below).
- **apply_outlier_penalty**: enables pos-scoring outlier penalty (i.e. outliers across all target entities) for these predicates

### Strategies

#### average_target_entity_confidence
Confidence is the average of all literal confidences of the target (object) entity. Useful when no other signal is useful for occurance and when plausibility mainly depends on target (i.e. target is more likely ot be hallucinated).

#### average_entity_confidence
Confidence is the average of all literal confidences across both the subject and object entity. Useful when both sides contribute equally to the plausibility of the triple.

#### spatial_cooccurrence
Confidence is the average entity confidence scaled down by the normalized distance between the subject and object entity's median literal span positions. Entities that appear close together in the document receive higher confidence. Controlled by `cooccurrence_distance_penalty` and `cooccurrence_min_factor`.

#### section_containment
Confidence is the average entity confidence, penalized if the object entity's median literal span does not fall inside any of the configured `sections`. Uses the same `out_of_window_penalty`, `win_distance_penalty`, and `min_penalty_factor` settings as the datatype property window penalties. Useful for example, when citations should only be extracted from the dedicated References section. 

### Outlier Penalty

After all object property annotations are scored, a outlier penalty is applied for predicates with `apply_outlier_penalty: true`. For each `(subject, predicate)` group, the median of all target entity positions (`target_median`) is computed. Annotations whose target entity position deviates significantly from the group median are penalized.

Unlike the datatype outlier penalty it is not configured by entity type but by predicate. This penalty is especially appropriate for predicates like `hasAuthor` where multiple objects of the same predicate are expected to be present in the same document region. For example, an author extracted from a distant reference list is likely a hallucination.
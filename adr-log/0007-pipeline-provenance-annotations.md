# Provenance Annotations during Triple Extraction

## Context and Problem Statement

After each document is extracted, every triple in the resulting RDF graph is annotated with the source span from which its value originated. This annotation needs to be stored in the audit log Knowledge Graph. 
OntoGPT, which was chosen in ADR-0007, does not calculate confidence scores or source spans for individual triples (the latter only for entities). Hence, we need to decide on our own logic:
## Considered Options

### Option 1: LLM reported confidence
- Ask separate LLM module to generate confidence score for each triple
- Example in AutoQG: 4 dimensions evaluated with separate LLM prompts: DomainFit, Accuracy, Consistency, Completeness

| Pros | Cons                                                                                |
|------|-------------------------------------------------------------------------------------|
| Easy to implement | Domain-Specific Prompt Engineering often required                                   |
| | Not proven to be providing trustworthy output (rather arbitrary)                    |
| | LLM Call Explosion (if per triple) or potential to miss triples (if per generation) |

### Option 2: Multi-Agent LLM Voting
- Ask separate LLM module multiple times to provide binary yes/no acceptance rating

| Pros | Cons |
|------|------|
| Easy to implement | Domain-Specific Prompt Engineering often required  |
| | LLM Call Explosion (if per triple) or potential to miss triples (if per generation) |

### Option 3: Iterative sampling
- trigger the extraction multiple times and use number of times triple occurred for confidence measurement

| Pros | Cons |
|------|------|
| Shows confidence in decision making by robustness | Caching needs to be disabled (Many unnecessary API calls)  |

### Option 4: Rule Based Scoring (Chosen)
- Confidence is derived from the quality of the match between extracted value and location in the source document 
- Additional Rules, such as Search Windows, per entity (e.g. CitedArticles appear in Reference Section, titles and abstracts appear in first 10% of the paper) can be specified in a config.

| Pros                        | Cons |
|-----------------------------|------|
| Directly interpretable      | Only syntactic (i.e., does not care about semantic correctness). |
| Transparent                 | Short values can produce high confidence, but wrong, merges ($\rightarrow$ possible to penalise)|
| No expensive LLM calls      | Complex for Entity-to-Entity Linking (e.g., do the two entities appear within X characters distance at max.?) | 
| Graceful decreases in score | |
| Deterministic               | |

### Option 5: ML Model Confidence Assessement
- For flow text NLI models can detect entailment between Premise (span of source text) and Hypothesis (generated triple)

| Pros | Cons                                                                                                     |
|------|----------------------------------------------------------------------------------------------------------|
| Captures Semantic Relationship | Does not work well for the main use case about scholarly metadata. May work better with other ontologies |
| Captures Semantic Relationship | Depends on additional models                                                                             |


## Decision Outcome
For source spans we did not consider multiple options, but directly decided on a chained pipeline: Exact Match $\rightarrow$ Fuzzy Match

For confidence annotation we decided on **Option 4: Rule Based Scoring**. This seems to us like the most robust method when it comes to the main use case.
Rule Based Scoring will be implemented as a predicate-aware fuzzy string matching against the source document. 
The chosen approach will assign confidence scores through multiple tiers (exact match, case-insensitive match, fuzzy match) with additional rule-based penalties (e.g. search windows) that can be configured in a config file for each schema.
## Consequences

### Positive Consequences
- Confidence scores directly interpretable by curators
- No additional model dependencies, infrastructure or inference 
- Generalizable to any schema
### Negative Consequences
- Semantic context is not considered for final score, only syntactic match
- Entity-to-Entity relationships will likely cause inaccurate confidence scores
- Manual maintenance of rules per schema
### Neutral Consequences
- Easily extensible later on, if time allows (e.g. with additional LLM-based approaches)

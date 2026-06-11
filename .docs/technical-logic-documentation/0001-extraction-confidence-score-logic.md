# Confidence Scores during Extraction

We do not rely on LLMs for producing confidence scores, as they have been proven to be producing overly confident scores alongside their decisions. Hence, we utilize the confidence annotation part of our pipeline to gather syntac similarity confidence scores. All these scores are used to indicate the plausibility of the LLM response based on the source text.

In the current state, we only provide confidence scores for **Datatype Properties**. This is due to the fact that syntactic matches are easy to check for Literals, but for **Object Properties** no syntactic matches can be found (2 entities generated from the text). Approaches such as Semantic Similarity do not make sense in the main scholarly use case (as Paper entities that are connected through citations or connect to authors will rarely be of the semantic similarity with the corresponding tail entity). Structural metrics fail as well. One possibility worth exploring for certain predicates is the median of the positions of all entities in the text and certain metrics around this (e.g., closeness, median in a specific section, ...). 

**rdf:type** Triples get the average confidence score of all of their associated literals. 

## Confidence Scores for Datatype Properties

### Configuration
Each schema comes alongside with a "provenance_config.yaml" file, which allows defining certain rules for predicates and entities making the confidence score more flexible towards the respective domain:
1. **predicate_windows**: allows specifying for specific predicates if they should typically appear in a specific part of the document. We currently support the following strategies, which can also be combined: head, section, tail & full. 

    ```yaml
    predicate_windows:
        title_paper:
            strategy: head
            chars: 400
        abstract:
            strategy: section
            heading: "Abstract"
        publication_date:
            strategy: full
    ```

    2. **Additional settings**: specify additional penalties used for different strategies

    ```yaml
    settings:
        out_of_window_penalty: 0.8
        win_distance_penalty: 1.0
        min_penalty_factor: 0.3

        outlier_penalty: 1.0
        min_outlier_factor: 0.2
        outlier_pentalty_entities:
            - Person
            - Organization
            - AcademicArticle
    ```
          

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



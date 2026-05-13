# Choice of Main Framework for Triple Extraction

## Context and Problem Statement

The pipeline receives Markdown documents and must produce RDF triples 
conforming to a LinkML ontology schema. The extraction is non-trivial and we require a solution that:

- uses an externally hosted LLM via an OpenAI-compatible API,
- requires no training data,
- adapts to arbitrary ontologies
- produces output that can be exported directly to RDF

## Considered Options

Many frameworks exist for LLM-based knowledge extraction. Those relying 
on local models or fine-tuning (SpERT, REBEL, Evontree), or being restricted to a single domain 
were excluded immediately as they violate the constraints above. The 
remaining evaluation proceeded in two steps.

### Step 1 - Cross-Document vs. Per-Document
A preliminary decision was whether to feed documents to the LLM 
individually or in batches.

**Per-document (chosen)**

| Advantages                                                             | Disadvantages                              |
|------------------------------------------------------------------------|--------------------------------------------|
| Chunking less important and rarely needed                              | More API calls overall                     |
| Lower hallucination risk (based on less information) & higher accuracy | No automatic cross-document entity merging |
| Failures isolated to one document                                      |                                            |

**Cross-document**

| Advantages                                     | Disadvantages                                      |
|------------------------------------------------|----------------------------------------------------|
| Fewer total API calls                          | Chunking unavoidable                               |
| Cross-Document merging (partially) done by LLM | Higher hallucination risk on longer, mixed context |
|                                                | Document failure blocks entire uploaded batch      |

Per-document extraction was chosen. Cross-document entity merging is 
handled as a separate pipeline stage, which keeps the extraction stage 
simple, restartable, and parallelisable.


### Step 2 - Framework Selection
#### Framework 1: SPIRES - ontoGPT
- Recursively iterates through Schema Tree and extracts entities step by step
- Gives structured format the LLM needs to reply with, e.g., 'attribute1: [a] attribute2: [a] attribute3: [c,d,e]'
- Plain responses are immediately grounded, for inlined classes recursion is started

| Pros                                                         | Cons                                                                                              |
|--------------------------------------------------------------|---------------------------------------------------------------------------------------------------|
| Step-by-step extraction improves accuracy on complex schemas | Exploding API calls for deeply nested schemas (ontoGPT itself recommends $\leq 2$ nesting levels) |
| Prompt Engineering possible within schema file               | No mechanism for user-provided hints or constraints                                               |
| Built-in LLM call caching                                    | No confidence score or span extraction                                                            |
| Supports RDF export                                          |                                                                                                   |

*Issues identified during testing* (all resolvable with own logic):
- ID generation produces unstable or empty identifiers
- Information loss for large multi-valued relations for an entity
- Noise values (e.g. `NaN`) generated for absent optional fields


#### Framework 2: OneKE

A multi-agent system with a dedicated Reflection Agent that 
improves extraction results. The schema must be written 
as Python code or expressed as entity/relation constraints 
in a configuration file without concrete typing support.

| Pros                                            | Cons                                      |
|-------------------------------------------------|-------------------------------------------|
| Reflection loop can provide a confidence signal | Inflexible or too loose schema definition |
| Easier to incorporate user provided hints          | No native RDF export                      |
|                                                 | Prompt Engineering less flexible          |
|                                                 | Schema changes may require code changes   |


## Decision Outcome

**ontoGPT (SPIRES) is chosen**, because it is the only evaluated option with native RDF export, which 
   eliminates a layer entirely. Additionally, the schema file is the only necessary central file making the system highly flexible.
To increase accuracy further a document-specific extraction schema is 
derived (manually) from the final KG ontology. For example, cited papers omit the 
`abstract` slot to prevent the LLM hallucinating content it cannot 
have seen. In the extracted statements and KGs this difference will not be visible. 

## Consequences

### Positive Consequences
- Native RDF export removes the need for a post-extraction RDF translation
- System supports any LinkML schema with no code changes (including Prompt Engineering)
- LLM caching reduces API calls on repeated runs on same documents
- Stable entity identifiers generated with our own logic

### Negative Consequences

- Long Extraction runs in case of deeply nested schemas
- No user-specific input possible
- Changes in ontoGPT need to be done carefully such that versioning does not cause problems 
- Provenance annotations need to be done separately
- Separate cross-document linking module is needed

# Choice of LLM Model for Triple Extraction

## Context and Problem Statement

For Triple Extraction, the system requires one or more Large Language Models (LLMs) that provide accurate and robust triple extraction (guided by ontology) while requiring minimal prompt engineering on top of our LLM framework used.  
The selected solution must additionally satisfy the following constraints:

- High extraction quality and low hallucination rates
- Sufficient context window to fit average paper length for main use case
- High availability & low resources consumption on backend server 
- No direct usage costs for the project
- Low operational complexity & good generalizability across schemas and domains

Two architectural approaches were considered:

1. Using centrally hosted API-based LLMs
2. Hosting open-source models locally via Ollama

---

## Considered Options

### Option 1: API-based Models via KIConnect NRW

The API endpoint `https://chat.kiconnect.nrw/api/v1` provides access to multiple hosted LLMs and embedding models.  
Only models with sufficiently high rate limits were considered (i.e. OpenAI GPT OSS 120B, Mistral Small 4 119B).

| Model | Context Window | Rate Limit | Reasoning Capability |
|---|---|---|---|
| OpenAI GPT OSS 120B | 131072 / 4096 | 1000 messages/hour | None |
| Mistral Small 4 119B | 262144 / 64000 | 1000 messages/hour | High |

#### Advantages
- Very large context windows $\rightarrow$ easily fit average papers
- Strong extraction quality $\rightarrow$ verified through initial experiments with ontoGPT
- Lower hallucination rates $\rightarrow$ hallucinations still occur though
- Minimal prompt engineering required $\rightarrow$ understood instructions early on, but sometimes struggle with formatting
- No additional local infrastructure required

#### Disadvantages

- Dependence on external infrastructure $\rightarrow$ Daily/hourly rate limits apply
- No option to make use of log-probabilities or logits for confidence measurement
---

### Option 2: Local Hosting via Ollama

Frameworks such as ontoGPT support local execution of open-source models through Ollama, including model families such as Llama, Gemma, and Qwen.

To minimize operational costs, we only considered models runnable on CPU in the range of approximately 1B–3B parameters. 

#### Advantages

- Full local control (including returned model logits etc.)
- No dependency on external APIs
- Flexible deployment possibilities

#### Disadvantages

- Significantly lower model performance
- Smaller context windows
- Higher hallucination rates
- Additional infrastructure and maintenance overhead
- Literature typically uses models in the 7B-80B+ parameter ranges, sometimes requiring additional SFT training.  Studies such as van Cauter & Yakovets (2024) indicate that high-quality extraction with near-zero hallucination rates was only consistently achieved by larger instruction-tuned models such as Llama-3-70B Instruct using few-shot prompting. Smaller models frequently produced hallucinations unless additional pruning or optimization techniques were applied.
- Internal experiments using ontoGPT with smaller local models (`llama-3.2-1b`, `gemma-3-1b`) further confirmed these findings. 

---

## Decision Outcome

The project will use API-based hosted models provided through the KIConnect NRW OpenAI-compatible API.

The primary reasons for this decision are:
- Higher extraction quality (API-hosted models outperformed locally hosted ones)
- No explicit local infrastructure required 
- Significantly larger context windows

The frontend will allow users to select among the available hosted models.  
This improves system availability and distributes requests across multiple models with a combined throughput of up to approximately 2000 prompts per hour.

Additionally, the backend may automatically switch to `Mistral Small 4 119B` when the input exceeds the context limitations of `GPT OSS 120B`.  
This is particularly relevant for larger ontologies or document-heavy domains such as legal texts, where more reasoning is required as well. 

---

## Consequences

### Positive Consequences

- Higher extraction quality and robustness across schemas
- Better support for large PDF files and ontologies
- Reduced prompt engineering effort & no SFT training needed

### Negative Consequences

- Dependency on external API infrastructure
- Dependence on provider-specific rate limits
- Limited explainability on model decisions (e.g., through logits)
### Neutral Consequences

- Local model support via Ollama remains technically possible for future experimentation

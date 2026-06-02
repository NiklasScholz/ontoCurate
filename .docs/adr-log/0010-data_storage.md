# Data Storage

## Context and Problem Statement

The application needs to store both semantic RDF knowledge graph data with provenance information and conventional application data such as users, workspaces, documents, and extraction pipeline states. A single storage solution was not considered ideal because these data types have different structural and querying requirements.

## Considered Options

- Single RDF Store  
- Single SQL Database  
- Hybrid Storage Architecture using Oxigraph and PostgreSQL

## Decision Outcome

We use a hybrid storage architecture consisting of Oxigraph and PostgreSQL.

Oxigraph is used to store provenance data, candidate statements, curation activities, and the persisted knowledge graph. It provides native RDF and SPARQL support and fits the graph-based provenance model based on PROV-O. RDF quads are used to separate provenance and persisted KG data into different named graphs.

PostgreSQL is used for operational application data such as authentication, workspace management, document caching, and extraction pipeline tracking.

This approach allows semantic and relational data to be handled using technologies best suited for their respective requirements.

### Consequences

- Native RDF/SPARQL support for provenance and KG data
- Clean separation between provenance and persisted KG data using named graphs
- Efficient handling of relational application data
- Clean separation between semantic and operational storage
- Slightly increased architectural complexity due to maintaining two storage systems
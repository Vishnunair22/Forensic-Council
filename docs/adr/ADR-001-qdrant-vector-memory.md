# ADR-001: Qdrant for Vector Memory

## Status

Accepted

## Context

The episodic memory system needs a vector database to store and retrieve forensic finding embeddings for retrieval-augmented context injection into agent initial thoughts.

Options considered:
- **Pinecone**: Fully managed, but requires cloud deployment and paid plan for production workloads.
- **Weaviate**: Feature-rich but heavier resource footprint; Go runtime adds ~500 MB to Docker stack.
- **Qdrant**: Rust-based, lightweight (~100 MB Docker image), gRPC + REST API, on-premise or cloud, filterable vector search.

## Decision

Use Qdrant as the vector memory store.

## Consequences

- Lightweight Docker footprint aligns with the project's resource constraints.
- gRPC support enables fast batch upserts of finding embeddings.
- Qdrant's filterable search allows querying by forensic signature type alongside vector similarity.
- Migration to cloud Qdrant is seamless if on-prem becomes insufficient.

---
name: bulk-evidence-partitioner
description: partition large evidence corpora into typed elements and retrieval-safe chunks for downstream account, briefing, and compliance workflows. use when chatgpt needs scalable corpus intake and should work well with local folders, runtime-native tooling, and optional unstructured-style processing with or without separate credentials.
---

# Bulk Evidence Partitioner

## Mission

Take a large pile of heterogeneous files and turn it into typed elements plus stable chunks that downstream workflows can search, cite, and reuse.

## Access modes

Read `references/access-modes.md` first. Default to local or runtime-native processing.

## Core rules

- Partition first, summarize later.
- Preserve source ids, source order, and chunk lineage.
- Use local text extraction when that is the highest-quality path currently available.
- Record the chosen access mode in `partition/access-mode.json`.

## Workflow

1. Select the operating mode with `scripts/plan_access_mode.py`.
2. Build or import a source manifest.
3. Run `scripts/partition_manifest.py` to emit typed elements.
4. Run `scripts/build_chunk_index.py` to create retrieval-safe chunks.
5. Run `scripts/validate_partition.py` to verify coverage and schema conformance.
6. Hand off chunk outputs to evidence, briefing, or memory workflows.

## Output contract

- `partition/access-mode.json`
- `partition/elements.jsonl`
- `partition/chunk-index.json`
- `partition/retrieval-hints.json`
- `partition/partition-validation.json`
- `summary.md`

## Pairings

- `account-evidence-harvester`
- `document-intelligence`
- `briefing-generator-companion`
- `semantic-account-memory`

## Bundled resources

- `scripts/plan_access_mode.py`
- `scripts/partition_manifest.py`
- `scripts/build_chunk_index.py`
- `scripts/validate_partition.py`
- `references/access-modes.md`
- `references/chunking-policy.md`
- `references/chunk-schema.md`
- `references/downstream-uses.md`

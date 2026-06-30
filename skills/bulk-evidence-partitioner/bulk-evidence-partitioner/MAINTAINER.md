# MAINTAINER — bulk-evidence-partitioner

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`bulk-evidence-partitioner` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- Partition first, summarize later — chunk lineage must be traceable back to source ID and byte offset.
- Source IDs, source order, and chunk lineage must be preserved through the full pipeline.
- Never merges content from two source files into a single chunk — chunk boundaries are always within-file.
- Access mode determined by `references/access-modes.md`; defaults to local/runtime-native.
- `human_review_required: true` whenever typed element classification is used for compliance decisions.
- Chunk IDs must be stable across re-runs of the same corpus (deterministic, not random).

## Known failure modes
- **Cross-file chunk merging**: producing a chunk that spans a PDF page-break that crosses into a second file. This destroys citation integrity.
- **Non-deterministic chunk IDs**: using `uuid4()` or timestamp-based IDs — downstream retrieval breaks on re-run if IDs change.
- **Type misclassification**: labeling a table of test results as a "narrative" chunk. Type errors propagate to compliance conclusions.
- **Silent truncation**: dropping the last chunk of a large file because it falls below a minimum-size threshold. Must flag truncated elements.

## Fragile fallbacks that must not become defaults
- Minimum chunk size thresholds must be flagged in output, never silently applied.
- When Unstructured-style processing is unavailable, fall back to native text splitting — never return empty partitions.

## Regression cases to preserve
1. Chunk IDs are deterministic (hash-based on source ID + offset or similar).
2. No chunk spans content from two source files.
3. Every typed element record includes `source_id`, `source_path`, `chunk_index`, and `char_offset`.
4. Returns `human_review_required: true` whenever element type is used for compliance routing.
5. Flags (does not silently drop) any corpus items that fail to partition.

## Approval-gated changes
- Changing the chunk ID generation algorithm (affects retrieval stability for stored corpora).
- Adding new element types to the type vocabulary.
- Changing minimum/maximum chunk size defaults.

## Minority-report policy
When the same content block could plausibly be typed as two different element types
(e.g., a test-results table that also reads as a control objective), emit
`minority_report.failed_to_merge` with both interpretations.
See canonical policy: `skills/shared/minority-report.md`.

## Update checklist (every version bump)
- [ ] Confirm chunk ID algorithm is still deterministic; test with same corpus twice.
- [ ] Verify element type vocabulary is in sync with downstream consumer expectations.
- [ ] Confirm no cross-file chunk merging in mixed-corpus smoke test.
- [ ] Confirm `human_review_required: true` present in all compliance-routing output paths.

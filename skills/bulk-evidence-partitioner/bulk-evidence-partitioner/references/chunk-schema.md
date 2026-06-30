# Chunk Schema

## elements.jsonl
Each line:
- `element_id`
- `source_id`
- `kind`
- `text`
- `start_marker`
- `end_marker`
- `metadata`

## chunk-index.json
Each chunk:
- `chunk_id`
- `source_ids`
- `element_ids`
- `text`
- `purpose_tags`
- `account_hints`
- `date_hints`
- `confidence_notes`

## retrieval-hints.json
Include suggested use cases and likely high-signal chunk ids.

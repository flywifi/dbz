# Chunking Policy

## Goals
- preserve meaning
- preserve provenance
- support retrieval and review

## Prefer these boundaries
- heading to next heading
- bullet list groups
- table row groups by shared context
- transcript turns grouped by topic or speaker run
- short file-level chunks when structure is weak

## Avoid these anti-patterns
- token-only splitting that breaks definitions from their labels
- merging unrelated files because they share a date or account name
- dropping dates or source paths to save space
- treating screenshots or binary placeholders as normal text chunks

## Chunk size guidance
Use smaller conservative chunks when confidence is low. Merge only when boundaries are clear and the combined chunk still represents one business idea.

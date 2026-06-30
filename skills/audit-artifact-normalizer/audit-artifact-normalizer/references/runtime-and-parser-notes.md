# Runtime and Parser Notes

This skill does not need to fully parse every format itself. It must recommend honest parser routes.

## Recommended route families

- `layout_aware_pdf`
- `native_office`
- `tabular`
- `image_or_scan_fallback`
- `direct_text`
- `transcript_adjacent`
- `archive_expand`
- `manual_review`

## Use richer parsers when

- tables, charts, or page layout matter
- the file is scan-heavy
- audio or video transcription is needed
- the user asked for loss-aware conversion into structured outputs

## Use lighter routes when

- the file is plain text or markdown
- the file is already in a normalized bundle
- the task is inventory-only rather than content analysis

## Environment honesty

Never imply that a richer parser or external service was run when only a route recommendation was produced.

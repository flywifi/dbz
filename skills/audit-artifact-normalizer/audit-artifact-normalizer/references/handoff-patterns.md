# Handoff Patterns

This skill is upstream. It should package artifacts cleanly, then stop or hand off.

## Preferred downstream pairings

### document-intelligence
Use when the user asks questions from the package, wants comparisons, or needs normalized conversion.

### compliance-report-analyzer
Use when the package includes supported framework artifacts and the user wants structured review outputs.

### account-evidence-harvester
Use when the package is only one part of a broader account evidence job spanning other systems.

### briefing-generator-companion
Use when package contents should inform account prep, post-call summaries, or executive readouts.

## Handoff summary fields

Always include:
- what was in scope
- what normalized cleanly
- what remains unresolved
- which files are likely most important downstream

## Anti-patterns

Avoid:
- forcing final conclusions upstream
- silently dropping unsupported files
- flattening internal and customer-facing files together
- hiding duplicates that may matter for provenance or timing

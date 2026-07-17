# Context overlays

Overlays tailor query output to a real-world context — an **industry**, a **jurisdiction**, or a
**client template** — without changing any data. They are a *presentation layer*: the mappings,
tiers, and tables are identical with or without an overlay; what changes is which frameworks lead
the answer and, optionally, which are shown at all.

## Why

Every real conversation has a context ("we're a healthcare SaaS", "we sell to federal", "we're
EU-based"), but the raw query surface is context-free — every answer spans all 35 frameworks and
the reader filters mentally each time. Overlays do that filtering explicitly and reproducibly, so
a segment view (healthcare, federal contractor, EU SaaS) is a versioned artifact rather than an
ad-hoc query recipe.

## The contract (honesty first)

- Overlays never alter mappings or tiers — only presentation.
- Suppression is always disclosed: every overlay-filtered output carries an `overlay` block with
  `suppressed_count`. The NIST 800-53 spine is never suppressed.
- The unfiltered result is always one flag-removal away (omit `--overlay`).
- Explicit flags always win over overlay defaults (`--min-tier`, `--scope-fedramp`).
- Client templates are **placeholders only** — no real client names or data, ever
  (publication-hygiene rule; `tools/health_audit.py` scans the overlay directory).

## Shape

Overlays live in `canonical-sources/overlays/` (schema: `overlay.schema.json`) as
`<scope>/<id>.json`:

```json
{
  "id": "healthcare", "scope": "industry",
  "description": "…",
  "sets":      { "default_min_tier": "…", "default_scope_fedramp": "…" },
  "adds":      { "emphasized_frameworks": ["HIPAA Security", "HITRUST CSF", "SOC 2"] },
  "overrides": { "framework_universe": ["…"] },
  "precedence_rank": 10
}
```

- `sets` — defaults applied only when the user did not pass the corresponding flag.
- `adds.emphasized_frameworks` — shown first in framework-keyed results.
- `overrides.framework_universe` — when present, rows involving a framework outside this set
  (plus the spine) are suppressed and counted.
- Every framework name must canonicalize through the grc.db `framework_labels` table (a shipped
  test enforces this — no invented frameworks).

### Precedence

When several overlays combine: **jurisdiction (regulatory) > industry > client-template**, ties
broken by `precedence_rank` then `id`. Higher-precedence overlays win conflicting `sets`;
emphasized lists concatenate in precedence order; universes intersect (most restrictive wins, and
an empty intersection is an error, not a silent empty result).

## Use

```bash
python3 cross-mapping/engine/dbz_query.py master  --framework-a "SOC 2" --framework-b "HITRUST CSF" --overlay industry/healthcare
python3 cross-mapping/engine/dbz_query.py scope    --family AC --overlay jurisdiction/us-federal-contractor   # defaults to Moderate
python3 cross-mapping/engine/dbz_query.py overlap  --framework-a "SOC 2" --framework-b "ISO 27001/2 (2022)" --overlay industry/eu-saas
python3 cross-mapping/engine/dbz_query.py master  --framework-a "SOC 2" --framework-b "PCI DSS v4.0" --overlay industry/eu-saas,jurisdiction/us-federal-contractor
```

Available on `master`, `overlap`, `scope`, and `search`. `--overlay` accepts a comma-separated
list. Resolution logic: `cross-mapping/engine/overlay_resolver.py`.

## Adding a client template

Create `canonical-sources/overlays/client-template/<name>.json` with `scope: "client-template"`,
a placeholder id, and only frameworks that canonicalize through `framework_labels`. Never put a
real client name, engagement detail, or customer data in the file. Run `test_spine.py` (the
overlay block validates the new file) before committing.

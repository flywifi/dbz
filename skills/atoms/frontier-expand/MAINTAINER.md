# frontier-expand — Maintainer Notes

## Non-Negotiables

- Dedup the frontier against `seen` scope signatures **only** — never against consolidated
  findings. Deduping against findings breaks convergence (a rejected lead would respawn
  every wave forever).
- `signature(scope)` is normalized (lowercased, whitespace-collapsed) so trivially
  reworded duplicates collapse to one.
- Respect stop conditions: return `saturated: true` after `k_dry` empty waves; return the
  matching `stop_condition` when `depth_cap` or `size_cap` is hit — do not exceed them to
  "be thorough".
- `mutate` mode never auto-expands (leads go to the manager). This atom must not emit
  `next_scopes` for mutate-mode envelopes.
- `human_review_required` is always `true`; never fabricate a lead.

## Known Failure Modes

- All leads already in `seen`: return `{next_scopes: [], saturated: true, stop_condition: "saturated"}`.
- Duplicate leads within one wave: collapse to a single next scope.
- `wave >= depth_cap`: return `stop_condition: "depth_cap_reached"` with the un-expanded
  leads noted so the manager can surface them in the consolidated residual section.
- `agents_so_far >= size_cap`: return `stop_condition: "size_cap_reached"` likewise.

## Regression Cases

See `evals/evals.json`:
- pass-01: new leads not in `seen` become next_scopes, saturated=false
- fail-01: all leads already seen → saturated=true, empty next_scopes
- edge-01: depth_cap reached → stop_condition depth_cap_reached, leads preserved not dropped

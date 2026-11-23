# Phase-56 closing adversarial audit — 2026-11-23

**Scope.** Three data files merged from the weekly rotation's proposals (`announcements_feed.json`,
`known_exploited_vulnerabilities.json`, `mitre-attack-techniques.json`) and the registry lines that
describe them (`feed_registry.json` feeds `mitre-attack` and `cisa-kev`, `source_manifest.json`
entry `mitre-attack-enterprise`, `framework_changelog.json` entry `chg-mitre-attack-v20.0-to-v20.1`).

**Origin.** The proposals of 2026-11-17, -18 and -19 sat on `auto/refresh-*` branches because the
workflow's pull-request permission is off. Pull requests #3–#5 were opened by hand; the owner asked
for them to be merged.

## Pass 1 — source integrity
- **Each file was written by the scheduled, governed loader** on the runner, one commit per branch,
  one file per commit. The files state their own versions: KEV `catalogVersion` 2026.11.18, ATT&CK
  `_attack_version` 20.1.
- **Each branch was a week old;** none touched a file the later phases changed, and all three
  merged without conflict.

## Pass 2 — claim support
- **Registry values are read from the merged files** (KEV version and count; ATT&CK version and
  bundle date), not typed.
- **"ATT&CK content unchanged" is measured:** `attack_techniques` has 706 rows and the same table
  digest before and after.

## Pass 3 — chain / mutation integrity
- **Three merge commits, then one commit for registries and this record.** The combined tree was
  rebuilt and passed the gate battery before the push: 2 table digests differ after the merges
  (`announcements` 59 → 60, `cisa_kev` 1,768 → 1,786).
- **Registries** written only through `tools/registry_io.py`; all round-trip identical.

## Pass 4 — adversary, run
1. **"A week-old proposal conflicts with phases 53–55."** Merged cleanly; gates green. **Does not hold.**
2. **"The KEV refresh brings back guessed control families."** The loader writes them blank (phase
   52) and the gates that hold that are green. **Does not hold.**
3. **"ATT&CK v20.1 changes mappings."** Same table digest. **Does not hold.**

## Residual risk
- **The ATT&CK 800-53 mapping is CTID's for ATT&CK 16.1;** 252 techniques stay unmapped as before.
- **The `cisa-kev` feed names a manifest key (`cisa-kev-catalog`) that has no manifest entry.**
  Left as found.

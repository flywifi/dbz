# HIPAA Security Rule transition — proposed-rule horizon (postponed, contested)

**Status frozen 2026-08-08.** The proposed overhaul of the HIPAA Security Rule is a
**postponed, contested NPRM** — not law. This document records what is actually proposed,
where the rulemaking stands, and exactly what changes in this repository IF a final rule
ever lands. Evidence rules: `protocol-layer/regulatory-provenance.md`. Precedent for the
format: `docs/fedramp-modernization.md`.

## Framing: nothing in the mapping data changes today

The in-force Security Rule remains the **2013 Omnibus** version (45 CFR Parts 160/164).
Therefore all of the following stay pinned exactly as they are:

- `framework_projection` HIPAA Security rows (the SP 800-66r2 OLIR path, 279 pairs,
  provenance `direct_800_66`);
- the 164.x citation normalizer (`spine_normalize.py` — accepts only real `164.NNN` shapes);
- `validate_spine.py` check 2's section allowlist (it would *reject* NPRM-only sections
  today — that is the design working);
- `canonical-sources/cfr/45-cfr-164.json` (Subpart C as currently in force; regenerated
  2026-08-08 with real section titles);
- the HITRUST hub's HIPAA Security column and the SOC 2 × HIPAA ER oracle.

## The NPRM's identity (origin-verified 2026-08-08)

| Fact | Value | Source |
|---|---|---|
| Title | "HIPAA Security Rule To Strengthen the Cybersecurity of Electronic Protected Health Information" | Federal Register API, doc 2024-30983 |
| Citation / RIN / docket | **90 FR 898** / RIN 0945-AA22 / docket **HHS-OCR-2024-0020** | Federal Register API (all three fields verbatim) |
| Published / comments closed | 2025-01-06 / **2025-03-07** | Federal Register API |
| Comments received | **4,747** (FR's regulations.gov mirror, as checked 2025-04-04) | Federal Register API `regulations_dot_gov_info.comments_count` |
| Current OMB posture | Timetable: "Final Action 07/00/2027"; rulemaking stage **"Long-Term Actions"** | reginfo.gov Unified Agenda, edition 202510, RIN 0945-AA22 (retrieved 2026-08-08) |
| Contest | Withdrawal campaign by 100+ hospital systems and provider associations (incl. AMA) | Secondary reporting (HIPAA Journal / trade coverage); origin letters not yet read — support label THIN for this row |

Support label for the overall record: **CONTESTED** — an agency projection (July 2027) and
organized formal opposition coexist; the outcome (finalize / narrow / delay / withdraw) is
genuinely open. Domain-trap note (trap 8): the earlier "May 2026" was a projected
*final-action* month — a publication projection, never an effective date; an NPRM binds no
one before finalization.

## What the NPRM proposes (18 items)

Enumerated by HHS OCR's own fact sheet for the NPRM
(hhs.gov/hipaa/for-professionals/security/hipaa-security-rule-nprm/factsheet, retrieved
2026-08-08). **The follow-up extraction is now done** (2026-08-10): each item carries a
verbatim from the Federal Register document itself — 90 FR 898, pinned at
`canonical-sources/source_data/hhs/FR-2025-01-06-2024-30983.pdf` (sha256
`d5e1ec4107308e5e…`, retrieved from govinfo, extracted with pdfminer.six 20260107). Quotes
marked *proposed regulatory text* come from the amendatory text at the end of the document;
those marked *preamble* come from OCR's discussion, used where the proposal is stated there
rather than in one rule sentence. Every quote was mechanically asserted to appear in the
pinned document's extracted text before being written here:

1. Remove the required/addressable distinction — all implementation specifications
   required, with limited exceptions.
   > *preamble:* "remove the distinction between required and addressable implementation specifications and make all implementation specifications required, with specific, limited exceptions."
2. Written documentation of all Security Rule policies, procedures, plans, and analyses.
   > *preamble:* "policies and procedures in writing; documenting the implementation of the aforementioned policies and procedures; reviewing such policies and procedures on a regular cadence; modifying such policies and procedures when reasonable and appropriate; 643 and clarifying the scope of the electronic inf…"
3. Technology asset inventory + network map, reviewed at least every 12 months and on
   changes affecting ePHI.
   > *proposed regulatory text:* "Technology asset inventory—(i) General. Conduct and maintain an accurate and thorough written inventory and a network map of the covered entity’s or business associate’s electronic information systems and all technology assets that may affect the confidentiality, integrity, or availability of ele…"
4. Enhanced written risk analysis (inventory/map review; anticipated threats;
   vulnerabilities and predisposing conditions; risk level per threat–vulnerability pair).
   > *proposed regulatory text:* "Risk analysis—(i) General. Conduct an accurate and comprehensive written assessment of the potential risks and vulnerabilities to the confidentiality, integrity, and availability of all electronic protected health information created, received, maintained, or transmitted by the covered entity or…"
5. 24-hour notification between regulated entities on workforce-member access change or
   termination.
   > *proposed regulatory text:* "24 hours after a change in or termination of a workforce member’s authorization to access electronic protected health information or relevant electronic information systems maintained by such other covered entity or business associate. (E) Maintenance."
6. Contingency/incident response: restore critical systems and data within 72 hours;
   criticality analysis; written, tested incident-response plans.
   > *proposed regulatory text:* "72 hours of the loss. (2) Establish (and implement as needed) written procedures to restore loss of the covered entity’s or business associate’s other relevant electronic information systems and data in accordance with the criticality analysis required by paragraph (a)(13)(ii)(A) of this section.…"
7. Compliance audit at least every 12 months.
   > *proposed regulatory text:* "audit at least once every 12 months of the covered entity’s or business associate’s compliance with each standard and implementation specification in this subpart. (b)(1) Standard: Business associate contracts and other arrangements."
8. Business associates verify technical safeguards annually via written SME analysis +
   certification.
   > *proposed regulatory text:* "written verification obtained from the prospective or current business associate in accordance with paragraph (b)(1) of this section. (B) Maintenance."
9. Encryption of ePHI at rest and in transit, with limited exceptions.
   > *proposed regulatory text:* "Encryption and decryption—(1) General. Deploy technical controls to encrypt and decrypt electronic protected health information using encryption that meets prevailing cryptographic standards. (2) Implementation specification."
10. Configuration controls: anti-malware, removal of extraneous software, port disabling
    per risk analysis.
   > *proposed regulatory text:* "(iii) Configuration. Configure and secure operating system(s) and software consistent with the covered entity’s or business associate’s risk analysis under § 164.308(a)(2). (iv) Network ports. Disable network ports in accordance with the covered entity’s or business associate’s risk analysis unde…"
11. Multi-factor authentication, with limited exceptions.
   > *proposed regulatory text:* "Multi-factor authentication means authentication of the user’s identity through verification of at least two of the following three categories: (1) Information known by the user, including but not limited to a password or personal identification number (PIN)."
12. Vulnerability scanning at least every 6 months.
   > *proposed regulatory text:* "Vulnerability scanning. (A) Conduct automated vulnerability scans to identify technical vulnerabilities in the covered entity’s or business associate’s relevant electronic information systems in accordance with the covered entity’s or business associate’s risk analysis required by § 164.308(a)(2)…"
13. Penetration testing at least every 12 months.
   > *proposed regulatory text:* "Penetration testing. Perform penetration testing of the covered entity’s or business associate’s relevant electronic information systems by a qualified person."
14. Network segmentation.
   > *proposed regulatory text:* "Network segmentation. Establish and implement written policies and procedures that ensure that a covered entity’s or business associate’s relevant electronic information systems are segmented to limit access to electronic protected health information to authorized workstations. (F) Maintenance."
15. Separate technical controls for backup and recovery of ePHI.
   > *proposed regulatory text:* "create and maintain backups of the covered entity’s or business associate’s relevant electronic information systems, including verification of success of backups. (D) Disaster recovery plan."
16. Review/test the effectiveness of security measures at least every 12 months.
   > *proposed regulatory text:* "Evaluation—(i) General. Perform a written technical and nontechnical evaluation to determine whether a change in the covered entity’s or business associate’s environment or operations may affect the confidentiality, integrity, or availability of electronic protected health information. (ii) Imple…"
17. Business associates notify covered entities within 24 hours of contingency-plan
    activation.
   > *preamble:* "notify a group health plan within 24 hours of activating its contingency plan. If not, please explain why and what would be an appropriate amount of time for such notification. g."
18. Group health plans: sponsor safeguard compliance, agent assurance, and 24-hour
    contingency notification.
   > *preamble:* "amended to incorporate provisions to require the plan sponsor to: • Implement reasonable and appropriate administrative, physical, and technical safeguards to protect the 845 See 45 CFR 164.504(f)(1)(ii). 846 See 45 CFR 164.504(f)(1)(iii). 847 45 CFR 160.103 (definition of ‘‘Group health plan’’)."

## Repo trigger map — what changes here IF a final rule publishes

Each is a *dependent watch*, no dates asserted:

1. **`validate_spine.py` check 2 section allowlist** — any new/renumbered 164.x sections in
   the final rule must be added deliberately (the allowlist will reject them until then, by
   design), cross-checked against a refreshed
   `overlap-data/official_hipaa_citations_register.csv`.
2. **eCFR re-pull** — regenerate `45-cfr-164.json` at the final rule's as-of date
   (`ecfr_loader.py --title 45 --part 164 --subpart C`); decide Parts 160/162 scope then.
3. **SP 800-66 OLIR dependency** — NIST would need to re-map Implementing-the-Security-Rule
   guidance to the amended text; the `direct_800_66` spine path re-pins only when NIST
   publishes (watch feed `nist-sp-800-66`).
4. **HITRUST hub dependency** — the hub's "HIPAA Security Rule" column follows HITRUST's
   own re-mapping cadence (licensed; tracked-deferred).
5. **`hipaa` feed `current_version`** — moves off "2013 Omnibus" only at an effective final
   rule, with the version-transition treatment (dedicated phase, never a silent re-pin —
   `docs/standards-refresh-runbook.md`).
6. **A dedicated transition phase** runs the added/removed/changed analysis of final vs
   proposed items (the 18 above) with per-item verbatims, mirroring the CMMC ODP baseline
   procedure (`docs/cmmc-odp-baseline.md`).

## What this phase did NOT change

No HIPAA mapping rows, no citation normalizer changes, no section-allowlist changes, no
ER-layer changes. This phase changed only: the horizon record (`au-hipaa` — window July
2027, confidence low, support CONTESTED), the `hipaa` feed's notes/URLs, the announcement
pipeline's broken agency slug + over-generic keywords, and this document.

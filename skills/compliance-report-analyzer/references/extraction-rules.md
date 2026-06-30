# Extraction Rules

## Table of contents

1. Scope and purpose
2. Instruction precedence
3. Core operating rules
4. Definitions
5. Extraction mode and inference mode
6. Source-of-truth hierarchy
7. Control inclusion and classification
8. Framework-specific rules
9. Type 1 vs Type 2 handling
10. Crosswalk and local mapping rules
11. Field population and exception normalization
12. Sorting, duplicates, and ambiguity
13. Prohibited behavior
14. Final quality checks

## 1. Scope and purpose

Support only these frameworks unless the user explicitly expands scope:

- SOC 2 Type 1
- SOC 2 Type 2
- SOC 1 Type 1
- SOC 1 Type 2
- ISO 27001
- ISO 27002
- HIPAA

Do not expand to PCI DSS, HITRUST, NIST, FedRAMP, CIS, or other frameworks unless the user explicitly requests that.

Convert uploaded reports, certifications, assessments, screenshots, spreadsheets, and mapping artifacts into a structured control review output.

## 2. Instruction precedence

When rules conflict, apply this order:

1. Explicit text in the source document
2. Source-provided mapping tables
3. Source-provided testing or results tables
4. Source-provided local or proprietary mapping artifacts
5. Clearly labeled crosswalks supplied by the user
6. Conservative inference only when directly supported by source structure
7. Otherwise leave blank

Never allow general framework knowledge to override explicit source content.

## 3. Core operating rules

- Extract only what is explicitly stated unless inference mode is allowed.
- Preserve source wording as closely as possible.
- Do not invent controls, mappings, tests, results, exception statuses, ownership labels, or inheritance status.
- Preserve duplicate mappings.
- Preserve control ids exactly as written.
- Preserve framework terminology exactly as written when present.
- Keep outputs highly structured and spreadsheet-ready.
- If confidence is low, leave the field blank and flag for review rather than guessing.

## 4. Definitions

### Control
A discrete control statement, control activity, requirement, safeguard, or auditor-tested item explicitly stated in the source.

### Mapping
An explicit relationship between a control and a framework criterion, objective, safeguard, domain, or control identifier.

### Local mapping
Any proprietary or user-specific mapping field such as Local Control ID, Request ID, Local Control Title, Category, Domain, Family, or Requirement Group.

### Tested
The source explicitly states that the control was evaluated for design or operating effectiveness.

### Not tested
The source explicitly states that the control was not tested, was out of scope, did not operate, was excluded from testing, or existed only as inherited or complementary without testing.

### Inherited
The source explicitly states that the control responsibility is provided by a third party, cloud provider, subservice organization, parent organization, shared service, or similar external dependency.

### Complementary control
A control the report states must be operated by another party, typically a user entity or subservice organization.

### Carved-Out
A control or system responsibility explicitly excluded from the service auditor’s testing scope.

## 5. Extraction mode and inference mode

### Extraction mode
Use by default.

Rules:

- Extract only what is explicitly stated in the source.
- Prefer direct text, visible table structure, and labeled fields.
- Do not infer missing content unless inference mode is satisfied.

### Inference mode
Allow only when all conditions below are true:

- the relationship is directly supported by source structure or labels
- the inference does not require external framework knowledge
- the inference can be traced to a clear join or labeled association
- the inferred value is low-risk and reversible
- the value can be left blank if confidence is low

Allowed examples:

- joining a control description table to a testing table by exact control id
- carrying forward a mapped criterion from a labeled mapping table to the same exact control id in a testing table

Disallowed examples:

- assigning a HIPAA safeguard based only on general security wording
- assigning a SOC 2 criterion based only on topic familiarity
- converting one framework to another without an explicit crosswalk

## 6. Source-of-truth hierarchy

### Mapping tables
If the source includes a criteria-to-control, framework-to-control, objective-to-control, or similar mapping table, use that as the primary source of truth for framework mapping.

### Testing or results tables
If the source includes tests-of-controls, testing, audit procedures, or results tables, use those as the primary source of truth for:

- control description
- audit test
- result language
- exception status

### Combined use
If both mapping and testing tables exist:

- join them by exact control id where possible
- preserve duplicate mappings
- do not collapse one-to-many relationships

### Local or proprietary mapping artifacts
If a local mapping artifact exists, use it as the primary source of truth for local mapping fields.

### Missing mapping tables
If no mapping table exists, infer mappings only when clearly supported by source structure. Otherwise leave mapping fields blank.

## 7. Control inclusion and classification

Include controls only when explicitly present in the source or clearly part of the source’s control population.

Possible included categories:

- Tested
- Not tested
- Inherited
- Complementary – User Entity
- Complementary – Subservice
- Subservice Control
- Carved-Out

Do not exclude complementary, inherited, subservice, or carved-out controls if the user wants them included or if the governing instruction set requires their inclusion.

### Control Type
Populate only when supported by the source using these values:

- Tested
- Not tested
- Inherited
- Complementary – User Entity
- Complementary – Subservice
- Subservice Control
- Carved-Out
- blank

### Control Ownership
Populate only when supported by the source using these values:

- Internal
- Customer
- Vendor
- Shared
- blank

## 8. Framework-specific rules

### SOC 2

- Use the report’s own SOC 2 criteria mapping where available.
- Preserve duplicate mappings when one control maps to multiple criteria.
- Preserve distinctions between Type 1 and Type 2.
- Do not force controls into criteria if the report does not provide or clearly support the mapping.

Default criteria order:

- CC1
- CC2
- CC3
- CC4
- CC5
- CC6
- CC7
- CC8
- CC9
- A1
- C1
- PI1 if present

### SOC 1

- Use the report’s own control objective and control activity structure.
- Preserve the relationship between control objective and control.
- Do not map SOC 1 controls into SOC 2 Common Criteria unless the source explicitly provides that.
- Preserve report-native process areas, transaction cycles, or domains when provided.

Sort SOC 1 output using the report’s native structure.

### ISO 27001 and ISO 27002

- Map to Annex A controls or ISO 27002 references only when explicitly provided or clearly supported by source structure.
- Preserve numbering and versioning exactly as written.
- Do not convert between versions unless the user explicitly requests it.
- If the source uses Statement of Applicability structure, preserve it where relevant.

### HIPAA

- Map to safeguard categories and regulatory citations only when explicitly provided or clearly supported by source structure.
- Preserve regulatory citations exactly as written.
- Do not infer HIPAA mapping from generic security language alone.

Typical categories include:

- Administrative Safeguards
- Physical Safeguards
- Technical Safeguards

Common citations may include:

- §164.308
- §164.310
- §164.312
- §164.316

## 9. Type 1 vs Type 2 handling

Apply these rules to both SOC 1 and SOC 2.

### If report type is Type 1

- Treat the report as point-in-time unless the source explicitly states otherwise.
- Focus on design or suitability language.
- Do not describe controls as operating effectively over a period unless the source explicitly states that.
- Do not convert design-assessment language into operating-effectiveness language.

### If report type is Type 2

- Treat the report as period-based testing unless the source explicitly limits scope.
- Extract testing procedures, sample language, result language, and exception outcomes when present.
- Preserve operating-effectiveness language.

Never rewrite Type 1 content as Type 2 content or Type 2 content as Type 1 content.

## 10. Crosswalk and local mapping rules

Use crosswalks only when they materially improve extraction accuracy and are supplied by the source set.

Allowed crosswalk sources:

- crosswalks included in the report
- user-provided mapping guides
- user-provided spreadsheets
- screenshots of proprietary mappings
- clearly labeled cross-reference materials
- bundled mapping assets in `assets/mappings/`

Rules:

- Use crosswalks to support extraction and alignment.
- Do not fabricate cross-framework relationships.
- If a crosswalk is incomplete, populate only supported fields.

### Local mapping procedure

1. Identify mapping artifacts such as Local Control ID tables, Request ID tables, proprietary category tables, screenshots showing control-to-request relationships, or cross-reference spreadsheets.
2. Determine a safe join key using exact identifiers such as exact REQ Control ID, exact Framework Control ID, exact Request ID, exact Local Control ID, or a clearly labeled equivalent.
3. Join only on exact or clearly equivalent identifiers supported by the source.
4. If one control maps to multiple local controls or request ids, preserve all relationships.
5. If no safe join exists, do not map; leave local mapping fields blank.
6. Preserve local names, ids, categories, and titles exactly as written.

## 11. Field population and exception normalization

For every field:

1. Populate from explicit source text if present.
2. Else populate from a reliable source table joined by exact control id or exact local mapping key.
3. Else leave blank.
4. Do not synthesize values from general framework knowledge.

Normalize result language into only these values:

- Exception noted
- No exceptions noted
- Not tested

### Use `Exception noted` when
The source explicitly states exceptions were identified.

### Use `No exceptions noted` when
The source explicitly states that no exceptions were noted, the control operated effectively, the control was suitably designed, or the test result indicates success with no stated exception.

### Use `Not tested` when
The source explicitly states that the control was not tested, was outside scope, did not operate, was inherited only without testing, was complementary only without testing, or was excluded from testing.

Otherwise leave the field blank.

## 12. Sorting, duplicates, and ambiguity

### Sorting

Sort according to native framework order whenever mapping exists.

- SOC 2: CC1 through CC9, then A1, C1, and PI1 if present
- SOC 1: native report order by objective, process, or control activity
- ISO 27001 and ISO 27002: Annex A numeric order, or source-native order if Annex A numbering is not clearly used
- HIPAA: Administrative, Physical, Technical, then other cited implementation or documentation sections if separately structured

### Duplicates

- Preserve duplicate rows when one control maps to multiple criteria, objectives, or local controls.
- Preserve one-to-many and many-to-one relationships.
- Do not deduplicate unless the user explicitly requests deduplication.

### Ambiguity

- If two possible mappings exist and the source does not resolve them, preserve both only if both are explicitly shown; otherwise leave blank and flag manual review.
- If OCR or formatting corruption is noisy, prefer visible table structure over corrupted plain text.
- If a row is incomplete, retain it if the control itself is identifiable and populate only the supported fields.

## 13. Prohibited behavior

- Do not invent control ids.
- Do not invent framework mappings.
- Do not infer mappings from general familiarity alone.
- Do not merge distinct controls unless explicitly instructed.
- Do not collapse duplicate mappings.
- Do not rewrite auditor wording into summary language unless requested.
- Do not treat inherited, complementary, carved-out, or subservice controls as tested controls unless the source explicitly says they were tested.
- Do not assume local mapping exists unless shown in the source.
- Do not convert one framework into another without explicit support.
- Do not overstate exception severity.
- Do not fill blank fields with assumptions.

## 14. Final quality checks

Before finalizing output, verify all of the following:

- Every retained row has a control identifier when the source provides one.
- Framework and report type are populated when the source provides them.
- Mapped rows contain framework or domain values when the source provides them.
- Local mapping fields are populated only where the source supports them.
- Control Description contains the control statement, not general framework narrative.
- Audit Test contains the auditor’s procedure when available.
- Exceptions Noted uses only the allowed normalized values.
- Type 1 vs Type 2 handling is correct.
- Rows are sorted in the proper native order.
- Exception Focus contains all required exception rows.
- Ambiguous values remain blank or are flagged for review rather than guessed.

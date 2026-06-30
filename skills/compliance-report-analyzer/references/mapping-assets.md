# Mapping Assets

## Purpose

This skill bundles user-supplied mapping files that can improve extraction accuracy when the report itself does not already contain a complete mapping table. Treat these files as supporting crosswalks. They do not override explicit report language.

## Usage rules

- Read the relevant file only when it materially improves extraction accuracy.
- Prefer exact identifier joins.
- Preserve duplicate mappings.
- If no safe join exists, leave the local mapping fields blank.
- Do not invent relationships based on filename alone.

## Bundled files

### `assets/mappings/SOC 1 T1.csv`

Observed columns include:

- `Reference ID`
- `Category`
- `Name`
- `Tiers - Level 1 (from Child ERS(s))`
- `Local Controls (Linked)`
- `Framework (from Local Controls (Linked))`
- `Sort Order`

### `assets/mappings/SOC 1 T2.csv`

Observed columns include:

- `Reference ID`
- `Category`
- `Name`
- `Tiers - Level 1 (from Child ERS(s))`
- `Local Controls (Linked)`
- `Framework (from Local Controls (Linked))`
- `Sort Order`

### `assets/mappings/SOC 2 T1.csv`

Observed columns include:

- `Reference ID`
- `Category`
- `Name`
- `Tiers - Level 1 (from Child ERS(s))`
- `Local Controls (Linked)`
- `Framework (from Local Controls (Linked))`
- `Sort Order`

### `assets/mappings/SOC 2 T2.csv`

Observed columns include:

- `Reference ID`
- `Category`
- `Name`
- `Tiers - Level 1 (from Child ERS(s))`
- `Local Controls (Linked)`
- `Framework (from Local Controls (Linked))`
- `Sort Order`

### `assets/mappings/ISO 27001.csv`

Observed columns include:

- `Reference ID`
- `Category`
- `Name`
- `Local Controls (Linked)`
- `Framework (from Local Controls (Linked))`
- `Sort Order`

### `assets/mappings/HIPAA Security.csv`

Observed columns include:

- `Reference ID`
- `Category`
- `Name`
- `Local Controls (Linked)`
- `Framework (from Local Controls (Linked))`
- `Sort Order`

### `assets/mappings/SOC 2 T1 & ISO 27001.csv`

Observed columns include:

- `Reference ID`
- `Category`
- `Name`
- `Tiers - Level 1 (from Child ERS(s))`
- `Local Controls (Linked)`
- `Framework (from Local Controls (Linked))`
- `Sort Order`

Use when the source set explicitly needs a SOC 2 Type 1 to ISO 27001 alignment already represented by this file.

### `assets/mappings/SOC 2 T2 & ISO 27001.csv`

Observed columns include:

- `Reference ID`
- `Category`
- `Name`
- `Tiers - Level 1 (from Child ERS(s))`
- `Local Controls (Linked)`
- `Framework (from Local Controls (Linked))`
- `Sort Order`

Use when the source set explicitly needs a SOC 2 Type 2 to ISO 27001 alignment already represented by this file.

### `assets/mappings/SOC 2 T1 & HIPAA S.csv`

Observed columns include:

- `Reference ID`
- `Category`
- `Name`
- `Tiers - Level 1 (from Child ERS(s))`
- `Local Controls (Linked)`
- `Framework (from Local Controls (Linked))`
- `Sort Order`

Use when the source set explicitly needs a SOC 2 Type 1 to HIPAA Security alignment already represented by this file.

### `assets/mappings/hipaa_hitrust_e1_granular_overlap_with_45cfr.xlsx`

Observed sheets:

- `Summary`
- `Action_Item_Overlap`
- `Normalized_Tuples`
- `Pair_Summary`
- `HIPAA_45CFR_Mapping`
- `Source_Register`

Observed columns from `Action_Item_Overlap` include:

- `Source File`
- `Reference ID`
- `Category`
- `Action Item`
- `HIPAA Controls`
- `HIPAA Control Count`
- `HITRUST e1 Controls`
- `HITRUST Control Count`
- `Mapping Type`
- `Overlap Notes`
- `HIPAA 45 CFR Citation(s)`
- `HIPAA Standard / Spec`

Observed columns from `Normalized_Tuples` include:

- `Source File`
- `Reference ID`
- `Category`
- `Action Item`
- `HIPAA Control`
- `HITRUST e1 Control`
- `Action-Item Mapping Type`
- `Pair Reuse Count`
- `HIPAA 45 CFR Citation(s)`
- `HIPAA Standard / Spec`
- `45 CFR Mapping Confidence`
- `45 CFR Mapping Basis`

Use only when the user explicitly wants the HIPAA to HITRUST e1 overlap or 45 CFR support reflected in the analysis.

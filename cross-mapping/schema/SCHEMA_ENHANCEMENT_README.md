# Enhanced Framework Mapping Schema v3.0
## For Precise Audit Overlap Calculation

### What This Solves

Your original JSON files couldn't distinguish between:
- **Baseline** controls (required for all certifications)
- **Optional add-ons** (like SOC 2's extra 4 TSCs)
- **Tiers/Levels** (FedRAMP Low/Mod/High, HITRUST e1/i1/r2, CMMC Levels)
- **Overlays** (NIST 800-172, OT overlays)
- **Annexes** (ISO 27001 Annex A, NIS2 Annexes)

This made it impossible to calculate **exactly how much work is shared** between two audit scopes.

---

### Key Schema Additions

#### 1. `scope_type` Field
Every framework component now has a `scope_type`:

| Value | Meaning | Example |
|-------|---------|---------|
| `baseline` | Required for all certifications | SOC 2 Security (Common Criteria) |
| `optional_addon` | Can be added to baseline | SOC 2 Availability, Confidentiality, Privacy TSCs |
| `tier` | Impact/maturity level selection | FedRAMP Low/Mod/High, HITRUST e1/i1/r2 |
| `overlay` | Specialized control set for specific use cases | NIST 800-82 OT Overlay, 800-172 Enhanced |
| `annex` | Supplementary requirements attached to baseline | ISO 27001 Annex A, NIS2 Sector Annexes |
| `enhancement` | Advanced controls beyond standard baseline | CMMC Level 3 adds 800-172 controls |

#### 2. `tier` Object (for tiered frameworks)
```json
"tier": {
  "tier_name": "Moderate",
  "tier_ordinal": 2,
  "includes_lower_tiers": true
}
```

This tells you:
- What level name to display
- How to sort levels (1=lowest)
- Whether higher tiers **accumulate** lower tier controls (FedRAMP High includes Moderate includes Low)

#### 3. `tsc_category` (SOC 2 specific)
```json
"tsc_category": "availability"
```
Values: `security`, `availability`, `processing_integrity`, `confidentiality`, `privacy`, `all`

#### 4. `parent_framework` 
Shows what a component extends:
- SOC 2 Availability → parent is `soc2_security` (baseline)
- FedRAMP Moderate → parent is `nist_800_53_r5`
- ISO 27701 Privacy → parent is `iso27001_annex_a`

#### 5. `incremental_controls`
Lists only the NEW controls this component adds beyond its parent, enabling precise "delta" calculations.

---

### How to Calculate Overlap

**Example: Client wants SOC 2 (Security + Availability) AND ISO 27001**

Query logic:
1. Get `soc2_security` controls (baseline - required)
2. Get `soc2_availability` controls (optional_addon they selected)
3. Get `iso27001_clauses` + `iso27001_annex_a` controls
4. Compare NIST 800-53 mappings for overlap

**Result:**
- "You'll implement 215 unique controls"
- "47 controls are shared between SOC 2 and ISO 27001"
- "Your SOC 2 work covers 38% of your ISO 27001 requirements"

---

### Framework-Specific Notes

#### SOC 2 Trust Service Criteria
- **Security (Common Criteria CC1-CC9)**: ALWAYS required - this is the baseline
- **Availability, Processing Integrity, Confidentiality, Privacy**: OPTIONAL - client chooses which to include
- Each TSC has its own `component_id` and `tsc_category` field

#### FedRAMP
- Four distinct tiers with cumulative controls
- `tier_ordinal` lets you compare: High (3) > Moderate (2) > Low (1) > LI-SaaS (0)
- `includes_lower_tiers: true` means High includes all Moderate and Low controls

#### HITRUST
- Three tiers: e1 (Essential) → i1 (Implemented) → r2 (Risk-based)
- Each tier builds on the previous
- r2 is special: control count varies based on organization's risk profile

#### CMMC 2.0
- Levels 1, 2, 3 with cumulative controls
- Level 1 Assessment Objectives (AOs) are an optional add-on for more detailed assessment

#### ISO 27001
- **Clauses 4-10**: Management system requirements (baseline)
- **Annex A**: 93 reference controls - must apply based on risk assessment
- **ISO 27017/27018/27701**: Optional add-ons for cloud, PII cloud, privacy

---

### Query Examples

**"What controls are in FedRAMP Moderate but NOT in FedRAMP Low?"**
```python
moderate_controls = get_controls("fedramp_r5_moderate")
low_controls = get_controls("fedramp_r5_low")
incremental = moderate_controls - low_controls  # 200 controls
```

**"If I have SOC 2 with all 5 TSCs, what % of ISO 27001 Annex A is covered?"**
```python
soc2_all = union(soc2_security, soc2_availability, soc2_pi, soc2_conf, soc2_privacy)
iso27001_annex = get_controls("iso27001_annex_a")
overlap = intersection(soc2_all.nist_mapping, iso27001_annex.nist_mapping)
coverage = len(overlap) / len(iso27001_annex) * 100
```

**"Show me only the OPTIONAL components for CMMC 2.0"**
```python
cmmc_optional = filter(cmmc_components, scope_type="optional_addon")
# Returns: CMMC Level 1 Assessment Objectives
```

---

### Files Included

| File | Purpose |
|------|---------|
| `enhanced_framework_schema.json` | JSON Schema definition (validates your data) |
| `framework_examples.json` | Complete examples for SOC 2, FedRAMP, HITRUST, CMMC, ISO, EU regs |
| `SCHEMA_ENHANCEMENT_README.md` | This documentation |

---

### Next Steps

1. **Populate actual control IDs** - I've provided the structure; you need to fill in actual control arrays from SCF/AICPA/NIST sources
2. **Build query functions** - Create overlap calculators using this schema
3. **Create UI selectors** - Let users pick:
   - Which framework(s)
   - Which tier (if applicable)
   - Which optional add-ons

---

### Scalability

This schema works for ANY audit type with similar patterns:
- Baseline + optional modules (SOC 2 TSCs, ISO extensions)
- Tiered impact levels (FedRAMP, CMMC, HITRUST)
- Overlays for specialized environments (OT, cloud, privacy)
- Geographic annexes (EU NIS2 sectors, regional data protection)

Just add new `components` to the `frameworks` object following the same structure.

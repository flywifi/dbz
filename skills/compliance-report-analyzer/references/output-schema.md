# Output Schema

## Control Review sheet

Use this exact column order:

1. Framework
2. Report Type
3. Domain / Criteria / Control Objective
4. Framework Control ID
5. REQ Control ID
6. Local Control ID
7. Request ID
8. Local Category / Domain
9. Control Type
10. Control Ownership
11. Audit Test
12. Control Description
13. Exceptions Noted
14. Reviewer Notes

## Allowed values

### Report Type

- SOC 1 Type 1
- SOC 1 Type 2
- SOC 2 Type 1
- SOC 2 Type 2
- ISO 27001
- ISO 27002
- HIPAA
- blank

### Control Type

- Tested
- Not tested
- Inherited
- Complementary – User Entity
- Complementary – Subservice
- Subservice Control
- Carved-Out
- blank

### Control Ownership

- Internal
- Customer
- Vendor
- Shared
- blank

### Exceptions Noted

- Exception noted
- No exceptions noted
- Not tested
- blank

## Exception Focus sheet

Use the same columns as Control Review.

Include all rows where:

- `Exceptions Noted = Exception noted`
- also include `Exceptions Noted = Not tested` only when the user explicitly requests it

## Summary sheet

Use this exact column order:

1. Framework
2. Report Type
3. Domain / Criteria / Control Objective
4. Number of Controls
5. Number of Exceptions
6. Number Not Tested
7. Number Inherited
8. Notes

## Field population rules

Apply this rule for every field:

1. Populate from explicit source text if present.
2. Else populate from a reliable joined table using an exact identifier.
3. Else leave blank.
4. Never synthesize values from general framework knowledge.

## Output order

Present results in this order unless the user requests otherwise:

1. Control Review
2. Exception Focus
3. Summary
4. Optional posture analysis

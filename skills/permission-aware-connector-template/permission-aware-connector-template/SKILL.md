---
name: permission-aware-connector-template
description: provide a secure template for connector and mcp integrations that need scoped access, explicit authorization boundaries, and reviewable permission models. use when chatgpt should help design or package secure account-aware integrations without hand-waving over auth, tenancy, least privilege, or operator review and should support both basic no-oauth templates and full authorization stacks.
---

# Permission Aware Connector Template

## Mission

Design secure integrations without pretending the auth stack already exists. The same resource model should support a basic no-OAuth build and a full authorization build.

## Access modes

Read `references/access-modes.md` first.

## Core workflow

1. Run `scripts/plan_access_mode.py`.
2. Generate a permission matrix with `scripts/generate_permission_matrix.py`.
3. Validate scope coverage with `scripts/validate_scope.py`.
4. Emit resource templates with `scripts/emit_resource_templates.py`.
5. Use `references/deployment-modes.md` to design both the basic and full-authorization variants.

## Output contract

- `security/access-mode.json`
- `security/permission-matrix.json`
- `security/resource-model.md`
- `security/example-policies.json`
- `security/validation-report.json`
- `summary.md`

## Bundled resources

- `scripts/plan_access_mode.py`
- `scripts/generate_permission_matrix.py`
- `scripts/validate_scope.py`
- `scripts/emit_resource_templates.py`
- `references/access-modes.md`
- `references/deployment-modes.md`
- `references/design-checklist.md`
- `references/example-resource-model.md`
- `assets/example-permissions.csv`

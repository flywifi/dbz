# Access Modes

Default assumption: **no OAuth and no API keys**.

## Preferred order
1. **planning-only mode** — define principals, resources, actions, scopes, tenancy rules, and approval surfaces.
2. **local artifact mode** — generate permission matrices, resource models, and validation reports from CSV or JSON contracts.
3. **direct integration mode** — map the same contract into a hosted MCP implementation with Better Auth, SpiceDB, OAuth, or other production authz components.

## Guidance
- This skill must stay useful even when no hosted auth stack exists yet.
- Always design a **basic/no-oauth path** and a **full-authorization path** from the same permission model.

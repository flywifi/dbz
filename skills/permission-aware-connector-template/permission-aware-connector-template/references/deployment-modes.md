# Deployment Modes

## Mode A: basic no-oauth implementation
Use when the team needs a secure prototype or an internal-only deployment before a full hosted auth stack exists.

Characteristics:
- static or operator-provided identity context
- explicit account, tenant, and scope boundaries in the request contract
- no delegated OAuth flow
- minimal tool surface
- strong server-side validation and audit logging

## Mode B: full authorization implementation
Use when the system will be exposed broadly or needs delegated identity, session management, and fine-grained authorization.

Characteristics:
- OAuth or equivalent delegated auth
- first-class principals, resources, and actions
- tenancy-aware permission checks
- durable policy backend such as SpiceDB
- operator management workflows and revocation

## Rule
The same resource model and permission matrix should power both modes. The full implementation should add authn/authz depth, not redefine the resource semantics.

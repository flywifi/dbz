# Access Modes

Default assumption: **no OAuth and no API keys**.

## Preferred order
1. **runtime-native mode** — use the runtime's own web browsing, search, screenshots, and PDF reading tools.
2. **local artifact mode** — normalize already collected URLs, HTML/PDF exports, or manually captured findings.
3. **direct integration mode** — use Firecrawl or a self-hosted crawler only when the operator actually has credentials or infrastructure.
4. **planning-only mode** — emit a crawl plan, source map template, and manual finding skeleton when live retrieval cannot happen yet.

## Guidance
- Firecrawl's hosted API and self-hosted backend are optional accelerators, not prerequisites.
- In no-key environments, the skill should still perform high-quality research through native web tools or normalize manually captured findings into the same output contract.
- Keep the same `finding-log.json` shape across all modes so downstream skills do not care how the evidence was collected.

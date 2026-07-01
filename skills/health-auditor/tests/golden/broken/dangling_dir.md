# Broken fixture — dangling directory reference

This skill stores output in `canonical-sources/does-not-exist/` which has never been created.
The auditor must flag it as a warning-level unresolved reference.

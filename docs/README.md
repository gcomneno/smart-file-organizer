# Documentation

English is the canonical language for Smart File Organizer documentation.

Public user-facing and normative documentation added from 2026-08-20 onward
must be maintained bilingually using paired files:

- `name.md` — canonical English version;
- `name.it.md` — Italian mirror.

The Italian mirror must preserve the same product, architecture, compatibility,
and safety semantics as the canonical English document. A translation must not
introduce decisions, guarantees, exceptions, or requirements that are absent
from the English source.

Source code, public API names, CLI syntax, schema fields, machine-readable
states, reason codes, identifiers, and other technical contracts remain in
English unless a separately approved compatibility decision says otherwise.

Existing English-only documentation predating this policy may be translated
progressively through separate reviewable changes. Introducing this policy does
not require unrelated historical documentation to be translated in the same
change.

## Normative architecture documents

- [ADR 0001 — Approved evolution architecture](adr/0001-evolution-architecture.md)
  — existing canonical architecture document; English only until migrated
  separately.
- [ADR 0002 — Verifiable recovery contract and failure model](adr/0002-verifiable-recovery-contract.md)
  — canonical English version.
- [ADR 0002 — Contratto di recovery verificabile e modello dei guasti](adr/0002-verifiable-recovery-contract.it.md)
  — Italian mirror.
- [ADR 0003 — Manifest v2 identity and fingerprint schema](adr/0003-manifest-v2-identity-schema.md)
  — canonical English version; proposed by issue #85.
- [ADR 0003 — Schema di identità e fingerprint di Manifest v2](adr/0003-manifest-v2-identity-schema.it.md)
  — Italian mirror.

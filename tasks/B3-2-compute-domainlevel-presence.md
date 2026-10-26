---
id: B3.2
title: Compute domain-level presence
phase: B
status: in-progress
gate: false
depends_on: [A1.4, B2.4]
blocks: [B3.5]
design_ref: "§B3 item 2"
deliverable: 3
owner: claude
---

# B3.2 — Compute domain-level presence

**Design reference:** DESIGN.md §B3 item 2 · **Deliverable 3**

## Goal

Determine, per target, whether its annotated domains are present in each surviving corpus — as
a binary and a count.

## Steps

- Annotate domains for every assay target; pin the annotation resource version.
- Test presence of each domain in each surviving manifest.
- Emit binary and count outputs in the shared homology schema.
- Document how multi-domain targets are handled.

## Done when

- Domain presence computed for all targets against all manifests.
- Multi-domain handling rule documented and applied consistently.
- Annotation resource version pinned.

## State — 2026-10-26

`in-progress`. **Branch `claude/project-thread-bywmyz`.** Nothing is waiting on the
project owner yet.

## Notes

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._

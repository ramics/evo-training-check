# How a denylist of names ages

Companion note to *Auditing a training-data exclusion policy* (Result 4). Draft of 2026-10-22,
internal to the project. Citations of the form (Author Year) are listed in the article; identifiers
of the form A9.1 and D-201 refer to this project's task files and append-only decision log.

A rule that names a taxon inherits every subsequent revision of the reference taxonomy. The 31 names
were replayed against quarterly NCBI Taxonomy releases from 2020-01 to 2026-10, baseline 2023-04
(Schoch et al. 2020, A9.1, D-201, D-202).

Three names have ceased to resolve. *Herpesviridae* became a synonym of *Orthoherpesviridae* in
January 2026, so a rule naming it as a family scientific name reaches no herpesvirus and reports
success while doing so; *Orthopolintovirales* failed the same way in the same release; and
*Reoviridae* had already ceased to be a family name in the taxonomy release this project pinned, so
its decay was present at time zero.

Reach falls from 75.83% to 65.17% across the window, at 4.34% of the viral taxonomy per year. New
material dominates that loss: 44,261 viral taxa present at 2026-10 are absent from the baseline,
unreachable from it through NCBI's merge records, and named by nothing in the list, which is 15.18%
of the current viral taxonomy. Churn is smaller and counted separately: 787 renamed, 890 renumbered,
7,723 re-ranked.

A computed rule ages more slowly. Descent from an ICTV realm, asked of each release, covers 96.57%
at the baseline and 88.47% at 2026-10, a relative decline of 8.39% against the name list's 14.06%;
its floor is the taxonomy's own completeness, since 11.5% of viral taxa at 2026-10 descend from no
realm. The slope is equal either side of the filter's own vintage, so the finding concerns the
practice of specifying a filter as an enumeration of names and applies to any such list.

**Why the renames were left unresolved.** Resolution would recover little: of the gap at 2026-10,
renaming accounts for 787 taxa against 44,261 that no name reaches. It can also enlarge a rule
silently — *Reoviridae* survives in the pinned taxonomy as a synonym of *Reovirales*, an order
rather than a family, so following that synonym converts a family rule into an order rule, an
additional 90,530 records at 90% identity on the corpus used for the cross-filter comparison; the
looser reading is computed separately as `loose_only_members` and held out of every result (D-199).
Where a literal reading measures vocabulary rather than the filter, the audit substitutes and
declares it: the specificity rule declares `require_rank: realm`, a rank NCBI has never used, which
run literally finds a realm on no record and removes the whole viral corpus, so it is resolved to
descent from one of the six ICTV realms, with the substitution travelling in the artefact's
`name_resolution` field. The line held is between a rule that cannot execute, which the audit
repairs and declares, and a rule that executes and fails, which the audit reports.

Durability is achievable. A rule that resolves taxa through the reference's own synonym and merge
records, pinned to a dated release and re-validated on a stated interval, ages more slowly and ages
visibly; at 4.34% per year, holding unnamed new material below 1% requires re-validation about every
0.2 years. The disclosure standard arising from this work asks in item C1 for annotation sources
cited as dated releases with digests, and this result argues for a companion item requiring a stated
re-validation interval wherever a rule is written as a list of names.


#!/usr/bin/env python3
"""Sweep the §A2 known-problem taxa across every A1.4 manifest — task A2.5.

    pixi run -e dev python tools/sweep_problem_taxa.py
    pixi run -e dev python tools/sweep_problem_taxa.py --dry-run

`DESIGN.md` §A2 names three categories known to defeat taxonomic filters — giant viruses and
NCLDV, segmented genomes, satellite viruses. DECISIONS.md **D-187** turns them into taxon
predicates over the pinned ICTV VMR and `amazebio.problemtaxa` implements them; this tool is the
I/O and the tally. `metrics/detections.md` is the shared output contract and this is its fourth
producer.

**This is the label-side arm, and what that bounds is stated in every table.** The categories
are taxa, so the sweep reads the label a record carries, which is the same evidence the filter
acted on. §A2 opens by warning that an audit using taxonomy reproduces the filter's blind spots,
and that warning binds here harder than anywhere else in A2. So `verdicts` is three-way —
present, absent, **unlabelled** — and `unlabelled` is never folded into absent. The owner's
standing decision of 2026-10-19 is that this arm ships first and a label-independent marker pass
is measured separately before any of it is committed to.

**Where each manifest's evidence comes from, and why it differs by release.** `metrics/manifests.md`
records the asymmetry this tool has to live with: Evo 1's `stage2` carries an inline lineage on
every record and no identifier, Evo 2's `imgvr` carries an IMG/VR accession and no lineage. So
there is no single way to ask a release what it kept:

* **`taxonomy_inline`** — stage 2. The lineage is read off each surviving record directly, one
  pass, the manifest's removed set subtracted first. A census.
* **`accession_join`** — Evo 2's IMG/VR component. The released records carry no taxonomy at
  all, so the classification is joined through the accession to the staged IMG/VR release.
  A7.2 already performed and published exactly that join (`evo2.released_by_classification`),
  over the whole released set, so this tool consumes it rather than re-reading 16 GB to
  reproduce a census that exists. The join is A7.2's artefact and is cited as such.
* **`not_searched`** — every other component, listed with its reason rather than omitted. A
  table that silently covered part of a release reads as a verdict on all of it, which is the
  rule `metrics/manifests.md` sets for A1.4's own manifests and `metrics/detections.md` repeats.

**The route is never `conformance_failure`.** It comes from `amazebio.apply.route_for` over the
manifest's own outcome, and that function refuses to return the conformance route at all: a
record a reading removes which is nonetheless in the release is a claim about a named
laboratory's implementation, and §7 requires A7.1 to establish it with record-level evidence
rather than A2.5 to assert it in passing. For Evo 2's component the outcome is `unresolved` —
no rule can be decided on a record carrying no taxonomy — so **survival in a problem category
is measurable there while its route is not determinable from what ships with the release**.
That is A1.4's finding carried downstream, not a hedge.

**Giant viruses have a second handle that does not go through the lineage column.** IMG/VR names
its giant-virus MAGs in the accession (`IMGVR_UViG_GVMAG-…`), so `gvmag` is reported beside the
NCLDV verdicts as a publisher-applied label that survives an empty taxonomy field. It is
evidence about this corpus rather than a general method, and `problemtaxa.is_gvmag` says so.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from amazebio import corpora, ictv, objectstore, policyspec, problemtaxa
from amazebio.apply import resolve, route_for
from amazebio.conformance import parse_lineage_tag
from amazebio.detect import ManifestRef, element_kind_for
from amazebio.policyspec import load_policy_dir
from amazebio.problemtaxa import Category, Verdict
from amazebio.repro import run
from amazebio.survival import wilson_interval

#: Fixed so the artefact is reproducible; nothing here samples, so it only pins the run record.
SEED = 20261019

#: The VMR release the categories are derived under (D-187). Named rather than taken from a flag:
#: a table built against a different taxonomy is a different measurement, and A9.1 is the task
#: that varies it on purpose.
REFERENCE = "MSL37.3"

SPECS = Path("policies/specs")

#: Where A7.2 published the accession join this tool consumes for Evo 2's component. One key per
#: IMG/VR release; the scan carries `evo2.released_by_classification` over the whole released set.
A7_2_SCANS = {
    "2022-09-20": "corpora/results/a7-2/input-scan-2022-09-20.json",
    "2022-12-20": "corpora/results/a7-2/input-scan-2022-12-20.json",
}

#: The IMG/VR release Evo 2's component is joined through. A7.2 established that both staged
#: releases hold the same 15,677,623 records and that all 2,917,521 released accessions resolve
#: in each, so the join is insensitive to the choice; the earlier one is the release the corpus
#: was built from and is therefore the default. Both are reported.
JOIN_RELEASE = "2022-09-20"

#: Evo 2's own released-FASTA scan, for the GVMAG count over the released set.
A7_2_RELEASED = "corpora/results/a7-2/evo2-accessions.json"


# --------------------------------------------------------------------------------------
# A1.4's manifests
# --------------------------------------------------------------------------------------


def load_manifests(manifest_dir: Path) -> list[dict[str, Any]]:
    """A1.4's manifests, as written. Shape-compatible with A2.1's reader for the same reason."""
    index = manifest_dir / "index.json"
    if not index.exists():
        raise SystemExit(
            f"no A1.4 manifests at {manifest_dir}: run tools/apply_policies.py first. A2.5 "
            "consumes the manifests rather than re-deriving a surviving set (D-059)."
        )
    produced = json.loads(index.read_text())
    entries = produced.get("manifests", produced if isinstance(produced, list) else [])
    manifests = []
    for entry in entries:
        name = entry.get("manifest") or entry.get("file")
        path = manifest_dir / name if name else None
        if path is None or not path.exists():
            raise SystemExit(f"manifest listed in index.json is missing: {entry}")
        manifests.append({"path": path, "manifest": json.loads(path.read_text())})
    if not manifests:
        raise SystemExit(f"{index} lists no manifests")
    return manifests


def removed_ids(manifest_dir: Path, manifest: dict[str, Any]) -> set[str]:
    """Record ids this reading removes. They are not in the surviving corpus and are subtracted
    before anything is classified — and the count travels into the table, so the subtraction is
    visible rather than implied."""
    removed = manifest.get("removed", {}).get("file")
    if not removed:
        return set()
    path = manifest_dir / Path(removed).name
    if not path.exists():
        raise SystemExit(f"manifest names a removed set that is not there: {path}")
    return {json.loads(line)["record_id"] for line in path.read_text().splitlines() if line}


def outcome_of(row: dict[str, Any]) -> policyspec.Outcome | None:
    """The uniform outcome a manifest source records, if it recorded one."""
    value = row.get("uniform_outcome") or row.get("outcome")
    if not value:
        return None
    try:
        return policyspec.Outcome(value)
    except ValueError:
        return None


# --------------------------------------------------------------------------------------
# Tallies
# --------------------------------------------------------------------------------------


class CategoryTally:
    """Verdict counts for one category over one source, plus what carried them.

    `present_by_taxon` is this table's `composition` in the sense D-173 gives the word: the taxa
    holding the detections, most first, depending on no denominator. For a problem-taxa sweep it
    is the part that carries the finding — `Phycodnaviridae 22,803` says what survived in a way
    no percentage of an ICTV-derived universe does.
    """

    def __init__(self) -> None:
        self.verdicts: collections.Counter[str] = collections.Counter()
        self.present_by_taxon: collections.Counter[str] = collections.Counter()
        #: The category *members* that matched, as bare taxon names. Kept apart from
        #: `present_by_taxon`, whose keys are the record's own prefixed label: comparing a
        #: `f__Cystoviridae` label against a `Cystoviridae` member silently finds nothing, so
        #: every member would be zero-filled as undetected even where it was detected —
        #: understating the result in exactly the direction this audit must not.
        self.matched_members: collections.Counter[str] = collections.Counter()
        self.unlabelled_by_reason: collections.Counter[str] = collections.Counter()
        self.decided_at: collections.Counter[str] = collections.Counter()
        self.routes: collections.Counter[str] = collections.Counter()
        self.element_kinds: collections.Counter[str] = collections.Counter()

    def add(
        self,
        detail: problemtaxa.VerdictDetail,
        *,
        n: int,
        label: str,
        route: str,
        element_kind: str,
    ) -> None:
        self.verdicts[detail.verdict.value] += n
        if detail.verdict is Verdict.PRESENT:
            self.present_by_taxon[label] += n
            if detail.matched:
                self.matched_members[detail.matched[1]] += n
            self.routes[route] += n
            self.element_kinds[element_kind] += n
        elif detail.verdict is Verdict.UNLABELLED:
            self.unlabelled_by_reason[detail.why] += n
        if detail.decided_at:
            self.decided_at[detail.decided_at] += n

    def to_dict(self, *, checklist: problemtaxa.Checklist, category: Category) -> dict[str, Any]:
        definition = checklist.definition(category)
        total = sum(self.verdicts.values())
        settled = self.verdicts["present"] + self.verdicts["absent"]
        present = self.verdicts["present"]
        members = {t for _, t in definition.members}
        return {
            "category": category.value,
            "match_ranks": list(definition.ranks),
            "members": len(definition.members),
            "reference_species": definition.species_count,
            "definition_note": definition.note,
            "records": total,
            "verdicts": dict(sorted(self.verdicts.items())),
            # Two rates, because there is no single honest one. `of_settled` is the share among
            # records whose label can answer the question; `of_all` dilutes it with records that
            # cannot. Quoting either alone misleads in a different direction, so both ship with
            # an interval and the denominator is named in the key.
            "present_share_of_settled": _share(present, settled),
            "present_share_of_all": _share(present, total),
            "unlabelled_share_of_all": _share(self.verdicts["unlabelled"], total),
            "decided_at": dict(sorted(self.decided_at.items())),
            "composition": [{"taxon": t, "records": n} for t, n in _ranked(self.present_by_taxon)],
            "unlabelled_by_reason": dict(sorted(self.unlabelled_by_reason.items())),
            "routes": dict(sorted(self.routes.items())),
            "element_kinds": dict(sorted(self.element_kinds.items())),
            # Zero-filled, like every other detector's family universe (D-022): a member with no
            # surviving record is the result this audit is testing for and must be a measured
            # zero rather than an absent row.
            "members_with_a_record": [
                {"member": m, "records": n} for m, n in _ranked(self.matched_members)
            ],
            "members_without_a_record": sorted(members - set(self.matched_members)),
        }


def _ranked(counter: collections.Counter[str]) -> list[tuple[str, int]]:
    """Most first, ties broken by name so a quoted list reproduces from pinned inputs (D-173)."""
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))


def _share(k: int, n: int) -> dict[str, Any]:
    """A count with its denominator and a Wilson interval, or nulls when there is nothing to
    divide by. Zero over zero is not a rate, and emitting `0.0` would read as a measured null —
    which is the one thing `AGENTS.md` forbids making easy."""
    if not n:
        return {"count": k, "denominator": 0, "rate": None, "interval": None, "method": None}
    interval = wilson_interval(k, n)
    return {
        "count": k,
        "denominator": n,
        "rate": interval.estimate,
        "interval": [interval.low, interval.high],
        "method": interval.method,
    }


# --------------------------------------------------------------------------------------
# The two evidence routes
# --------------------------------------------------------------------------------------


def sweep_inline_shared(
    client: Any,
    source: corpora.StagedSource,
    *,
    checklist: problemtaxa.Checklist,
    state: dict[str, dict[str, Any]],
    policies: dict[str, policyspec.Policy],
    element_kind: str,
    limit: int | None,
) -> dict[str, dict[str, Any]]:
    """One pass over a source whose lineage travels with it, serving every reading.

    The classification is computed **once per record** and shared across readings, because a
    category verdict depends on the lineage and nothing else. What varies by reading is the
    removed set and the route, and both are applied per reading inside the single pass.

    Returns per-reading statistics; the tallies are accumulated into `state` in place.
    """
    stats = {
        policy_id: {
            "records_read": 0,
            "records_surviving": 0,
            "records_removed_by_reading": 0,
            "parse_failures": 0,
            "parse_failure_examples": [],
            "routes_resolved": collections.Counter(),
        }
        for policy_id in state
    }
    failures: list[str] = []
    read = 0

    def on_parse_error(record_id: str, exc: Exception) -> None:
        if len(failures) < 5:
            failures.append(f"{record_id}: {exc}")

    for record in _stream(client, source, on_parse_error=on_parse_error, limit=limit):
        read += 1
        verdicts = checklist.classify(record.taxonomy)
        label_cache: dict[Category, str] = {}
        for policy_id, held_state in state.items():
            here = stats[policy_id]
            here["records_read"] += 1
            if record.id in held_state["removed"]:
                here["records_removed_by_reading"] += 1
                continue
            decision = resolve(policies[policy_id], record, evidence=source.evidence)
            if decision.outcome is policyspec.Outcome.REMOVED:
                raise SystemExit(
                    f"{record.id} resolves to `removed` under {policy_id} but is not in the "
                    "manifest's removed set. The manifest is the surviving corpus (D-059); if "
                    "this pass and A1.4 disagree about what survived, every count below is "
                    f"unsafe. Rule {decision.rule_id!r}: {decision.why}"
                )
            route = route_for(decision.outcome).value
            here["routes_resolved"][route] += 1
            here["records_surviving"] += 1
            for category, detail in verdicts.items():
                if category not in label_cache:
                    label_cache[category] = _label(detail, record.taxonomy)
                held_state["tallies"][category].add(
                    detail,
                    n=1,
                    label=label_cache[category],
                    route=route,
                    element_kind=element_kind,
                )
        if read % 250_000 == 0:
            print(f"    {source.corpus_component}: {read:,}", file=sys.stderr)

    for here in stats.values():
        here["parse_failures"] = len(failures)
        here["parse_failure_examples"] = list(failures)
        here["routes_resolved"] = dict(sorted(here["routes_resolved"].items()))
    return stats


def _stream(
    client: Any,
    source: corpora.StagedSource,
    *,
    on_parse_error: Any,
    limit: int | None,
) -> Iterator[Any]:
    live = int(client.head_object(Bucket=corpora.BUCKET, Key=source.key)["ContentLength"])
    if source.bytes and live != source.bytes:
        raise SystemExit(
            f"{source.key}: staged object is {live} bytes, the pin says {source.bytes}. "
            "Re-verify before trusting any count from it."
        )
    # Ranged and retrying, with reconnects reported. A single forward pass over stage 2 moves
    # about 17 GB, and A1.4's own regeneration hit a broken pipe partway through it: a reader
    # without retry turns a transient reset into a lost hour.
    obj = corpora.RangedObject(
        client,
        bucket=corpora.BUCKET,
        key=source.key,
        size=source.bytes or live,
        on_retry=lambda attempt, pos, exc: print(
            f"    reconnect {attempt} at byte {pos:,} of {source.corpus_component}: {exc}",
            file=sys.stderr,
        ),
    )
    records = corpora.iter_stage2_records(
        obj,
        component=source.corpus_component,
        record_prefix=source.key,
        on_parse_error=on_parse_error,
    )
    for i, record in enumerate(records):
        if limit is not None and i >= limit:
            return
        yield record


def _label(detail: problemtaxa.VerdictDetail, taxonomy: dict[str, str]) -> str:
    """What a present verdict is attributed to: the record's own finest label where it has one,
    falling back to the member that matched. The record's label is the more informative of the
    two — `f__Mimiviridae` rather than `phylum Nucleocytoviricota` — and the member is recovered
    from `members_without_a_record` anyway."""
    for rank in ("genus", "family", "order", "class", "phylum"):
        if rank in taxonomy:
            return f"{rank[0]}__{taxonomy[rank]}"
    return detail.matched[1] if detail.matched else "(unlabelled)"


def sweep_joined(
    census: dict[str, int],
    *,
    checklist: problemtaxa.Checklist,
    route: str,
    element_kind: str,
) -> tuple[dict[Category, CategoryTally], dict[str, Any]]:
    """Classify a published classification census — one entry per classification, with a count.

    This is A7.2's join, consumed as an artefact. Every record in the released set is accounted
    for by exactly one entry, which is what makes the result a census rather than a sample.
    """
    tallies = {c: CategoryTally() for c in checklist.definitions}
    records = 0
    for tag, n in census.items():
        records += n
        taxonomy = parse_lineage_tag(tag).taxonomy
        for category, detail in checklist.classify(taxonomy).items():
            tallies[category].add(
                detail, n=n, label=_label(detail, taxonomy), route=route, element_kind=element_kind
            )
    return tallies, {
        "records_surviving": records,
        "classifications": len(census),
        "records_read": records,
        "records_removed_by_reading": 0,
        "parse_failures": 0,
        "parse_failure_examples": [],
    }


def fetch_json(client: Any, key: str) -> dict[str, Any]:
    body = client.get_object(Bucket=corpora.BUCKET, Key=key)["Body"].read()
    return json.loads(body)


# --------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------


def build_tables(
    *,
    manifests: list[dict[str, Any]],
    manifest_dir: Path,
    checklist: problemtaxa.Checklist,
    client: Any,
    joined: dict[str, dict[str, int]],
    gvmag: dict[str, Any],
    policies: dict[str, policyspec.Policy],
    limit: int | None,
) -> list[dict[str, Any]]:
    """Every table, reading each staged source **once** for all readings of its release.

    The loop is release-outer and reading-inner on purpose. A reading-outer loop would re-read
    Evo 1's stage 2 three times for its three readings — 51 GB instead of 17 — and D-046 records
    A1.4 making exactly that mistake and paying for it. It is also unnecessary: a category
    verdict is a function of the record's lineage alone, so it is computed once per record and
    shared, while only the **route** and the **removed set** vary by reading.
    """
    by_release: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for held in manifests:
        by_release[held["manifest"]["release"]].append(held)

    built: dict[tuple[str, str], dict[str, Any]] = {}
    for release, held_here in by_release.items():
        print(f"\n{release}: {len(held_here)} reading(s)", file=sys.stderr)
        state = {
            held["manifest"]["policy"]["id"]: {
                "held": held,
                "tallies": {c: CategoryTally() for c in checklist.definitions},
                "sources": [],
                "searched_any": False,
                "removed": removed_ids(manifest_dir, held["manifest"]),
            }
            for held in held_here
        }

        for source in corpora.sources_for(release):
            entries = _sweep_source(
                source,
                release=release,
                state=state,
                checklist=checklist,
                client=client,
                joined=joined,
                gvmag=gvmag,
                policies=policies,
                limit=limit,
            )
            for policy_id, entry in entries.items():
                state[policy_id]["sources"].append(entry)

        for policy_id, held_state in state.items():
            held = held_state["held"]
            built[policy_id, release] = _table(
                manifest=held["manifest"],
                manifest_path=held["path"],
                checklist=checklist,
                merged=held_state["tallies"],
                sources=held_state["sources"],
                searched_any=held_state["searched_any"],
            )

    return [built[key] for key in sorted(built)]


def _sweep_source(
    source: corpora.StagedSource,
    *,
    release: str,
    state: dict[str, dict[str, Any]],
    checklist: problemtaxa.Checklist,
    client: Any,
    joined: dict[str, dict[str, int]],
    gvmag: dict[str, Any],
    policies: dict[str, policyspec.Policy],
    limit: int | None,
) -> dict[str, dict[str, Any]]:
    """Sweep one staged source for every reading of its release, reading it at most once."""
    element_kind = element_kind_for(source.corpus_component).value
    entries: dict[str, dict[str, Any]] = {}
    for policy_id, held_state in state.items():
        manifest = held_state["held"]["manifest"]
        rows = {s.get("key"): s for s in manifest["sources"]}
        by_component = {s.get("corpus_component"): s for s in manifest["sources"]}
        row = rows.get(source.key) or by_component.get(source.corpus_component)
        if row is None:
            raise SystemExit(
                f"{source.key} is a staged object in {release} and the manifest for "
                f"{policy_id} does not list it. The manifest is the surviving set; sweeping an "
                "object it does not account for would report a figure over a corpus nothing "
                "declared."
            )
        outcome = outcome_of(row)
        entries[policy_id] = {
            "component": source.component,
            "corpus_component": source.corpus_component,
            "key": source.key,
            "route": route_for(outcome).value if outcome is not None else "unresolved",
            "element_kind": element_kind,
            "records_in_source": row.get("records"),
        }

    if source.corpus_component == "stage2" and source.readable:
        print(f"  {source.key}: taxonomy_inline for {len(state)} reading(s)", file=sys.stderr)
        stats = sweep_inline_shared(
            client,
            source,
            checklist=checklist,
            state=state,
            policies=policies,
            element_kind=element_kind,
            limit=limit,
        )
        for policy_id, entry in entries.items():
            entry.update(evidence="taxonomy_inline", searched=True, **stats[policy_id])
            state[policy_id]["searched_any"] = True
        return entries

    if source.corpus_component == "imgvr" and release == "opengenome2":
        census = joined[JOIN_RELEASE]
        print(f"  {source.key}: accession_join via IMG/VR {JOIN_RELEASE}", file=sys.stderr)
        for policy_id, entry in entries.items():
            tallies, stats = sweep_joined(
                census,
                checklist=checklist,
                route=entry["route"],
                element_kind=element_kind,
            )
            entry.update(
                evidence="accession_join",
                searched=True,
                join_source=A7_2_SCANS[JOIN_RELEASE],
                join_release=JOIN_RELEASE,
                gvmag=gvmag,
                **stats,
            )
            state[policy_id]["searched_any"] = True
            for category, tally in tallies.items():
                _absorb(state[policy_id]["tallies"][category], tally)
        return entries

    for entry in entries.values():
        entry.update(evidence="not_searched", searched=False, why=_why_not(source, release))
    return entries


def _table(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    checklist: problemtaxa.Checklist,
    merged: dict[Category, CategoryTally],
    sources: list[dict[str, Any]],
    searched_any: bool,
) -> dict[str, Any]:
    policy_id = manifest["policy"]["id"]
    release = manifest["release"]
    return {
        "task": "A2.5",
        "detector": "taxonomy-checklist",
        "reference": checklist.reference,
        "reference_file": ictv.release(checklist.reference).filename,
        "reference_sha256": ictv.release(checklist.reference).sha256,
        "decision": "D-187",
        "manifest": ManifestRef(
            policy_id=policy_id,
            release=release,
            path=manifest_path.name,
            sha256=_digest(manifest_path),
            removed_records=manifest.get("removed", {}).get("records", 0)
            or manifest.get("removed_records", 0),
        ).to_dict(),
        # A census over the sources that could be swept, not a sample: nothing here subsamples.
        # `not_searched` when no source in this manifest carries taxonomy at all, which is the
        # ESM3-open proxy's case and is a result rather than a missing file.
        "estimate_kind": "population" if searched_any else "not_searched",
        "sources": sources,
        "categories": [
            merged[c].to_dict(checklist=checklist, category=c) for c in Category if c in merged
        ],
        "notes": _notes(searched_any),
    }


def _absorb(into: CategoryTally, other: CategoryTally) -> None:
    into.verdicts.update(other.verdicts)
    into.present_by_taxon.update(other.present_by_taxon)
    into.matched_members.update(other.matched_members)
    into.unlabelled_by_reason.update(other.unlabelled_by_reason)
    into.decided_at.update(other.decided_at)
    into.routes.update(other.routes)
    into.element_kinds.update(other.element_kinds)


def _why_not(source: corpora.StagedSource, release: str) -> str:
    """Why a component was not swept. The proxy's reason is checked first: its sources are also
    unreadable as records here, and the generic staging message would hide the real reason,
    which is that a taxon category is not expressible over a protein corpus at all."""
    if release == "esm3-proxy":
        return (
            "the ESM3-open proxy is a protein corpus carrying no viral taxonomy; its reader is "
            "A1.6's and a problem-taxa category is not expressible over it"
        )
    if not source.readable:
        return f"{source.corpus_component} is not readable as records in this staging"
    return (
        f"{source.corpus_component} carries no taxonomic lineage per record and no accession "
        "this task can join to one"
    )


def _notes(searched_any: bool) -> list[str]:
    notes = [
        "Label-side arm only. Every verdict is a statement about the label a record carries, "
        "which is the same evidence the filter acted on; DESIGN.md §A2 warns that an audit "
        "using taxonomy reproduces the filter's blind spots, so `unlabelled` is reported as its "
        "own outcome and is never folded into `absent`.",
        "A zero in `present` with a large `unlabelled` is not evidence of absence. Read "
        "`present_share_of_settled` against `unlabelled_share_of_all` before quoting either.",
        "No route is `conformance_failure`: amazebio.apply.route_for refuses to return it, and "
        "§7 requires A7.1 to establish that claim with record-level evidence "
        "(metrics/survival.md).",
    ]
    if not searched_any:
        notes.append(
            "No source in this manifest carries taxonomy, so every count is zero by "
            "construction and none of it is evidence of absence."
        )
    return notes


def _digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifests", default="artifacts/a1-4", type=Path)
    parser.add_argument("--out", default="artifacts/a2-5", type=Path)
    parser.add_argument("--vmr", default="data/ictv", type=Path)
    parser.add_argument("--limit", type=int, help="stop after N records per source — smoke only")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, read no corpus")
    parser.add_argument("--allow-dirty", action="store_true", help="local iteration only")
    args = parser.parse_args(argv)

    pinned = ictv.release(REFERENCE)
    vmr_path = args.vmr / pinned.filename
    if not vmr_path.exists():
        raise SystemExit(
            f"the pinned VMR is not staged at {vmr_path}. Fetch {pinned.url} — note that "
            "ictv.global returns 403 to a default user-agent and 200 to a browser one (D-187), "
            "so a 403 here is not a paywall."
        )
    checklist = problemtaxa.build_checklist(ictv.read_vmr(vmr_path), reference=REFERENCE)
    for category, definition in checklist.definitions.items():
        print(
            f"{category.value:24} {len(definition.members):3} members at "
            f"{'/'.join(definition.ranks)}, {definition.species_count} reference species",
            file=sys.stderr,
        )

    manifests = load_manifests(args.manifests)
    policies = load_policy_dir(SPECS)

    if args.dry_run:
        for held in manifests:
            manifest = held["manifest"]
            print(f"\n{manifest['policy']['id']} x {manifest['release']}")
            for source in corpora.sources_for(manifest["release"]):
                how = (
                    "taxonomy_inline"
                    if source.corpus_component == "stage2" and source.readable
                    else "accession_join"
                    if source.corpus_component == "imgvr" and manifest["release"] == "opengenome2"
                    else "not_searched"
                )
                print(f"  {source.corpus_component:26} {how}")
        return 0

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    client = objectstore.client()

    joined = {
        key: fetch_json(client, scan)["evo2"]["released_by_classification"]
        for key, scan in A7_2_SCANS.items()
    }
    released = fetch_json(client, A7_2_RELEASED)
    gvmag = {
        "source": A7_2_RELEASED,
        "released_accessions": released["distinct_accessions"],
        "non_packable_accessions": released["non_packable_accessions"],
        "gvmag_examples": [a for a in released["non_packable_examples"] if problemtaxa.is_gvmag(a)],
        "note": (
            "IMG/VR names its giant-virus MAGs in the accession, so this is a publisher-applied "
            "giant-virus label that does not depend on the lineage column. A7.2 recorded these "
            "only as an accession shape its packing could not handle; D-187 promotes them to a "
            "signal. The count is A7.2's `non_packable_accessions` over the released FASTA and "
            "is an upper bound on GVMAGs until every non-packable accession is enumerated — "
            "A7.2 published 20 examples and all 20 are GVMAG."
        ),
    }

    with run(
        "A2.5",
        seed=SEED,
        outdir=outdir,
        allow_dirty=args.allow_dirty,
        durable=objectstore.durable_results("a2-5"),
    ) as provenance:
        provenance.parameter("reference", REFERENCE)
        provenance.parameter("reference_sha256", pinned.sha256)
        provenance.parameter("join_release", JOIN_RELEASE)
        provenance.parameter("decision", "D-187")
        provenance.parameter(
            "categories",
            {
                c.value: {
                    "members": sorted(f"{r}:{t}" for r, t in d.members),
                    "species": d.species_count,
                }
                for c, d in checklist.definitions.items()
            },
        )
        provenance.input_file(vmr_path, role="ictv-vmr")
        for key in (*A7_2_SCANS.values(), A7_2_RELEASED):
            provenance.input_url(f"s3://{corpora.BUCKET}/{key}", role="a7-2-join", verified=False)

        index: list[dict[str, Any]] = []
        tables = build_tables(
            manifests=manifests,
            manifest_dir=args.manifests,
            checklist=checklist,
            client=client,
            joined=joined,
            gvmag=gvmag,
            policies=policies,
            limit=args.limit,
        )
        for table in tables:
            policy_id = table["manifest"]["policy_id"]
            release = table["manifest"]["release"]
            stem = f"sweep-{policy_id}-{release}"
            path = outdir / f"{stem}.json"
            path.write_text(json.dumps(table, indent=1, sort_keys=True) + "\n")
            provenance.output_file(path, role=stem)
            index.append(
                {
                    "policy": policy_id,
                    "release": release,
                    "table": path.name,
                    "estimate_kind": table["estimate_kind"],
                    "present": {
                        c["category"]: c["verdicts"].get("present", 0) for c in table["categories"]
                    },
                }
            )
            for category in table["categories"]:
                print(
                    f"    {category['category']:24} "
                    f"present={category['verdicts'].get('present', 0):>8,} "
                    f"absent={category['verdicts'].get('absent', 0):>10,} "
                    f"unlabelled={category['verdicts'].get('unlabelled', 0):>10,}",
                    file=sys.stderr,
                )

        categories = outdir / "categories.json"
        categories.write_text(
            json.dumps(
                {
                    "reference": REFERENCE,
                    "reference_file": pinned.filename,
                    "reference_sha256": pinned.sha256,
                    "decision": "D-187",
                    "definitions": [
                        {
                            "category": c.value,
                            "match_ranks": list(d.ranks),
                            "members": sorted(f"{r}:{t}" for r, t in d.members),
                            "reference_species": d.species_count,
                            "note": d.note,
                        }
                        for c, d in checklist.definitions.items()
                    ],
                    "excluded_satellite_like": sorted(
                        f"{r}:{t}" for r, t in problemtaxa.EXCLUDED_SATELLITE_LIKE
                    ),
                },
                indent=1,
            )
            + "\n"
        )
        provenance.output_file(categories, role="categories")

        index_path = outdir / "index.json"
        index_path.write_text(json.dumps({"tables": index}, indent=1) + "\n")
        provenance.output_file(index_path, role="index")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

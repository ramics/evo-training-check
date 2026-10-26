#!/usr/bin/env python3
"""Regenerate the table of detected families whose Pfam name refers to a denylisted group.

    pixi run -e dev python tools/denylist_named_families.py --outdir artifacts/x1-8

Three threads counted "detected families whose Pfam name refers to a group the published
filter denylists" and got 42, 40 and 33/41. The spread was the matching rule rather than the
arithmetic, so the rule is written here, in code, against pinned inputs — and the row count
is reported under both readings of it rather than as one number:

* **41 rows** when a family's Pfam *identifier or curator description* names the group. Ten of
  those are caught only by the description, because they are named for a protein rather than
  for a taxon (`Peptidase_C5`, `Rhv`, `RVP`, …).
* **31 rows** when only the identifier is read. That is the floor, and it is the
  `matched_on == 'identifier'` subset of the same table.

The group list is not ours. It is the 19 family names of the `remove-denylisted-families` rule
of `policies/specs/evo1-literal.yaml`, which is this project's machine-verified transcription
of the published procedure (X1.4 checks those quotations against the source PDF). Nothing is
added to the list and nothing is inferred into it.

**A family refers to group *G*** if, case-insensitively, either

* its identifier or description contains the family name (`Flaviviridae`), the virus noun
  (`Flavivirus`, `Flaviviruses`), the adjective (`Flaviviral`) or the subfamily form
  (`Flavivirinae`); or
* the group's stem — the family name with `viridae` removed — appears as a **whole token** of
  the identifier, tokens being the runs of letters and digits between other characters.

The whole-token half of that rule is the one earned by a mistake. An earlier count of 42
included `PF22759 E217_GP41`, a phage baseplate hub protein, because its identifier contains
the string `GP41`, which a retroviral envelope family also carries — the same substring blind
spot as the `macrophage` case already recorded in this project. A substring match over protein
names counts vocabulary; a whole-token match over group stems counts groups.

**What the table is not.** A Pfam family's name records where its curators built the model,
not what any detected record is. A row means a protein in the released corpus clears Pfam's
curated threshold for a family whose name refers to a denylisted group; by itself it leaves
open whether the record is a member of that group or an environmental sequence carrying a
distant homolog. That question is settled per record, not per family, and not here.

Every input is pinned and none of them is a corpus:

* `data/profiles/Pfam-A.hmm.dat.gz` — Pfam 38.2 family metadata, verified against the
  publisher's own md5 before it is read. Gives the universe of 1,719 families (D-075's
  selection rule, `profiles.select_viral_families`), each family's identifier, description and
  gathering cutoff.
* `policies/specs/evo1-literal.yaml` — the 19 group names.
* The published per-family detection tables of A2.1 and A2.4, read from object storage and
  checked with `tools/detected_families.py`'s refusals: a table must name its own release,
  agree with itself, partition the pinned universe, and the three readings of the filter must
  give the same detected set. Hit counts are transcribed from the literal reading's tables.
* The published A4.5 background table, for each family's viral-specificity class.

Nothing here searches a sequence or reads a corpus, so the table regenerates in seconds from
the repository and the published tables alone.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import detected_families as detected

from amazebio import objectstore, policyspec, profiles, repro

TASK = "X1.8"

#: The spec whose `remove-denylisted-families` rule names the groups, and the rule's id.
SPEC = Path("policies/specs/evo1-literal.yaml")
RULE = "remove-denylisted-families"

#: The publisher's md5 of the Pfam metadata file, from `profiles.registry("pfam")`. Checked
#: before the file is read: the universe is this project's denominator everywhere, and a
#: silently different release would move every count in the table.
PFAM_DAT = "Pfam-A.hmm.dat.gz"

#: The A4.5 background table, for the specificity column. A published artefact of this project,
#: read by key so the row carries its digest.
BACKGROUND_KEY = "corpora/results/a4-5/background-pfam-38.2.json"

#: Hit counts come from one reading, named here rather than left implicit. The detected *set*
#: is the agreement of all three (D-247 and `detected_families.py`); the per-family hit count
#: is a measurement of one table, and mixing readings in one column would make the column a
#: sum over three overlapping corpora.
HIT_POLICY = "evo1-literal"

#: The two routes into the A3.2 headline, and the column prefix each one's hits are reported
#: under. They are never summed into one column: D-247 is the rule that a single-detector
#: figure is not set beside a merged one, and a reader comparing this table with the label
#: arm's per-record work needs the profile-search figure on its own, because A2.4 publishes no
#: per-hit table and so no record behind a provirus hit can be looked up.
ROUTE_COLUMNS = {"a2-1": "hits", "a2-4": "provirus_hits"}

COLUMNS = (
    "accession",
    "name",
    "description",
    "denylisted_group",
    "matched_on",
    "evo1_hits",
    "evo2_hits",
    "evo1_provirus_hits",
    "evo2_provirus_hits",
    "threshold",
    "specificity",
)


def group_names() -> list[str]:
    """The 19 denylisted family names, from the spec rather than from this file."""
    policy = policyspec.load_policy(SPEC)
    for rule in policy.rules:
        if rule.id == RULE:
            if rule.params.get("rank") != "family":
                raise SystemExit(
                    f"{SPEC}: {RULE} names rank {rule.params.get('rank')!r}, not 'family'. "
                    "The name rule compares family names and cannot read another rank."
                )
            names = list(rule.params["names"])
            if len(names) != 19 or len(set(names)) != len(names):
                raise SystemExit(
                    f"{SPEC}: {RULE} names {len(names)} families, expected 19 distinct. The "
                    "published procedure states '19 families' and the list is quoted from it."
                )
            return names
    raise SystemExit(f"{SPEC}: no rule {RULE!r}. The group list has no other source.")


def stem(group: str) -> str:
    """`Flaviviridae` -> `Flavi`. A refusal rather than a silent truncation for anything else."""
    if not group.endswith("viridae"):
        raise SystemExit(
            f"{group}: not an ICTV family name ending in 'viridae', so it has no stem and the "
            "whole-token half of the rule cannot be applied to it."
        )
    return group[: -len("viridae")]


def prose_forms(group: str) -> tuple[str, ...]:
    """The forms of a group's name prose uses: family, noun, plural, adjective, subfamily."""
    s = stem(group).lower()
    return (group.lower(), f"{s}virus", f"{s}viruses", f"{s}viral", f"{s}virinae")


def tokens(identifier: str) -> set[str]:
    return {t.lower() for t in re.split(r"[^A-Za-z0-9]+", identifier) if t}


def match(family: profiles.FamilyMeta, groups: list[str]) -> tuple[list[str], str | None]:
    """The groups this family's name refers to, and whether the identifier alone says so."""
    name = family.name.lower()
    both = f"{family.name} {family.description}".lower()
    hit: list[str] = []
    on: set[str] = set()
    for group in groups:
        forms = prose_forms(group)
        by_identifier = any(f in name for f in forms) or stem(group).lower() in tokens(family.name)
        by_description = any(f in both for f in forms)
        if by_identifier or by_description:
            hit.append(group)
            on.add("identifier" if by_identifier else "description")
    if not hit:
        return [], None
    # A family matched on its identifier is in the identifier-only floor; one matched only
    # through a curator's description is not. A family matched both ways counts as identifier.
    return hit, "identifier" if "identifier" in on else "description"


def hit_counts(client: Any, cache: Path, universe: set[str]) -> dict[str, dict[str, Any]]:
    """Per-family hits per release per route, plus each family's threshold.

    One column per route, never a sum: see :data:`ROUTE_COLUMNS`.
    """
    per_release: dict[str, dict[str, Any]] = {}
    for release in detected.RELEASES:
        counts: dict[str, dict[str, int]] = {
            column: dict.fromkeys(universe, 0) for column in ROUTE_COLUMNS.values()
        }
        thresholds: dict[str, float] = {}
        keys: list[dict[str, str]] = []
        for task, detector in detected.ROUTES:
            key = detected.table_key(task, HIT_POLICY, release)
            table = detected.fetch(client, key, cache)
            detected.check(table, release=release, detector=detector, universe=universe)
            keys.append({"key": key, "sha256": table["_sha256"], "route": detector})
            for row in table["families"]:
                counts[ROUTE_COLUMNS[task]][row["family_id"]] += int(row["hits"])
                if task == "a2-1":
                    thresholds.setdefault(row["family_id"], row["threshold"])
        per_release[release] = {"counts": counts, "thresholds": thresholds, "tables": keys}
    return per_release


def specificity(client: Any, cache: Path, universe: set[str]) -> tuple[dict[str, str], str]:
    """Each family's viral-specificity class from the published A4.5 background table."""
    table = detected.fetch(client, BACKGROUND_KEY, cache)
    rows = table["per_family"]
    if {row["accession"] for row in rows} != universe:
        raise SystemExit(
            f"{BACKGROUND_KEY}: covers {len(rows)} families, not the pinned universe of "
            f"{len(universe)}. The specificity column would then be a join against a "
            "different selection."
        )
    return {row["accession"]: row["class"] for row in rows}, table["_sha256"]


def build(client: Any, cache: Path, dat: Path) -> dict[str, Any]:
    universe_meta = profiles.select_viral_families(dat)
    universe = set(universe_meta)
    if len(universe) != detected.UNIVERSE_SIZE:
        raise SystemExit(
            f"{dat}: the pin gives {len(universe)} viral families, not "
            f"{detected.UNIVERSE_SIZE}. The universe was fixed before anything was searched."
        )

    groups = group_names()
    counts = hit_counts(client, cache, universe)
    classes, background_sha = specificity(client, cache, universe)

    #: The detected set, as the three readings agree on it, unioned over both routes.
    detected_sets = {
        release: detected.agreed(
            {
                policy: set().union(
                    *(
                        detected.check(
                            detected.fetch(
                                client, detected.table_key(task, policy, release), cache
                            ),
                            release=release,
                            detector=detector,
                            universe=universe,
                        )
                        for task, detector in detected.ROUTES
                    )
                )
                for policy in detected.POLICIES
            },
            f"{release} profile-hmmer+provirus-genomad",
        )
        for release in detected.RELEASES
    }

    rows: list[dict[str, Any]] = []
    multi: list[dict[str, Any]] = []
    for accession in sorted(universe):
        family = universe_meta[accession]
        hit, on = match(family, groups)
        if not hit:
            continue
        if len(hit) > 1:
            multi.append({"accession": accession, "name": family.name, "groups": hit})
        threshold = counts["opengenome2"]["thresholds"].get(accession) or counts["opengenome"][
            "thresholds"
        ].get(accession)
        if threshold is None and family.gathering is not None:
            threshold = family.gathering[0]
        rows.append(
            {
                "accession": accession,
                "name": family.name,
                "description": family.description,
                "denylisted_group": "|".join(hit),
                "matched_on": on,
                "evo1_hits": counts["opengenome"]["counts"]["hits"][accession],
                "evo2_hits": counts["opengenome2"]["counts"]["hits"][accession],
                "evo1_provirus_hits": counts["opengenome"]["counts"]["provirus_hits"][accession],
                "evo2_provirus_hits": counts["opengenome2"]["counts"]["provirus_hits"][accession],
                "threshold": threshold,
                "specificity": classes[accession],
                "_detected_evo1": accession in detected_sets["opengenome"],
                "_detected_evo2": accession in detected_sets["opengenome2"],
            }
        )

    flagged = rows
    detected_rows = [r for r in rows if r["_detected_evo1"] or r["_detected_evo2"]]
    identifier_only = [r for r in detected_rows if r["matched_on"] == "identifier"]
    summary = {
        "task": TASK,
        "question": (
            "Of the Pfam families the audit detected in the released corpora, which carry a "
            "name referring to a virus group the published filter's own policy names for "
            "removal?"
        ),
        "rule": {
            "groups_from": {"spec": str(SPEC), "rule": RULE, "groups": groups},
            "identifier_or_description": len(detected_rows),
            "identifier_only": len(identifier_only),
            "note": (
                "Publish the count with the rule attached. The two readings of the rule are "
                "two columns of one table, not two results: `matched_on == 'identifier'` is "
                "the floor."
            ),
        },
        "families_in_universe": len(universe),
        "flagged_in_universe": len(flagged),
        "detected": {
            "route": "profile-hmmer+provirus-genomad",
            "policy_readings_agree": list(detected.POLICIES),
            "hit_counts_from_reading": HIT_POLICY,
            "opengenome": {
                "families": sum(1 for r in detected_rows if r["_detected_evo1"]),
                "profile_hits": sum(r["evo1_hits"] for r in detected_rows),
                "provirus_hits": sum(r["evo1_provirus_hits"] for r in detected_rows),
            },
            "opengenome2": {
                "families": sum(1 for r in detected_rows if r["_detected_evo2"]),
                "profile_hits": sum(r["evo2_hits"] for r in detected_rows),
                "provirus_hits": sum(r["evo2_provirus_hits"] for r in detected_rows),
            },
        },
        "per_group": {
            group: sum(1 for r in detected_rows if group in r["denylisted_group"].split("|"))
            for group in groups
        },
        "families_touching_two_groups": multi,
        "does_not_claim": [
            "that a detected family means a member of that group is in the corpus: a Pfam "
            "family's name records where its curators built the model, and whether a record "
            "is a group member is a per-record question",
            "that the counts are a census: A2.1 and A2.4 sampled, and their tables carry "
            "estimate_kind lower_bound",
        ],
        "sources": {
            "pfam_dat": str(dat),
            "background": {"key": BACKGROUND_KEY, "sha256": background_sha},
            "detection_tables": {
                release: counts[release]["tables"] for release in detected.RELEASES
            },
        },
    }
    return {"rows": detected_rows, "all_flagged": flagged, "summary": summary}


def write(built: dict[str, Any], outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    tsv = outdir / "denylist-named-families.tsv"
    with open(tsv, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(COLUMNS), delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in sorted(built["rows"], key=lambda r: r["accession"]):
            writer.writerow(row)
    summary = outdir / "denylist-named-families.json"
    summary.write_text(json.dumps(built["summary"], indent=2, sort_keys=True) + "\n")
    return [tsv, summary]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dat", type=Path, default=Path("data/profiles/Pfam-A.hmm.dat.gz"))
    parser.add_argument("--outdir", type=Path, default=Path("artifacts/x1-8"))
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("artifacts/x1-8-tables"),
        help=(
            "where fetched published tables are kept. Outside the artefact directory: they are "
            "inputs, and the summary records each one's key and digest"
        ),
    )
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    pinned = {f.name: f for f in profiles.registry("pfam").files}[PFAM_DAT]
    digest = hashlib.md5(args.dat.read_bytes(), usedforsecurity=False).hexdigest()
    if digest != pinned.md5:
        raise SystemExit(
            f"{args.dat}: md5 {digest} is not the publisher's {pinned.md5} for "
            f"{pinned.url}. Re-stage it; every count in this table is relative to that release."
        )

    with repro.run(
        TASK,
        outdir=args.outdir,
        manifest_name="run-denylist-named.json",
        allow_dirty=args.allow_dirty,
        durable=objectstore.durable_results("x1-8"),
    ) as manifest:
        manifest.parameter("groups_from", f"{SPEC}:{RULE}")
        manifest.parameter("policy_readings", list(detected.POLICIES))
        manifest.parameter("hit_counts_from_reading", HIT_POLICY)
        manifest.parameter("route", "profile-hmmer+provirus-genomad")
        manifest.input_file(args.dat, role="pfam family metadata")
        manifest.input_file(SPEC, role="denylisted group names")
        built = build(objectstore.client(), args.cache, args.dat)
        for path in write(built, args.outdir):
            manifest.output_file(path, role="denylist-named family table")

    summary = built["summary"]
    print(
        f"flagged in the universe: {summary['flagged_in_universe']}; "
        f"detected: {summary['rule']['identifier_or_description']} "
        f"(identifier only: {summary['rule']['identifier_only']})"
    )
    for release, figures in (
        ("opengenome", summary["detected"]["opengenome"]),
        ("opengenome2", summary["detected"]["opengenome2"]),
    ):
        print(
            f"  {release:12s} families {figures['families']:3d}  "
            f"profile hits {figures['profile_hits']:5d}  "
            f"provirus hits {figures['provirus_hits']:4d}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

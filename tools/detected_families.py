#!/usr/bin/env python3
"""Build the declared detected-family lists A4.5 restricts its background table to.

    pixi run -e dev python tools/detected_families.py --outdir artifacts/a4-5/detected

A4.5's background table covers the whole pinned universe of 1,719 families. The figure the
write-up wants is the restriction of it to the families a release actually detected, and that
restriction needs the per-family lists, which live in object storage rather than in git. This
tool fetches them, checks them, and writes one plain list per (release, detector) with the
labels `tools/family_background.py` refuses a list without.

**It is a transcription, not a measurement.** Nothing here searches anything or recomputes a
survival figure. Every family it emits is a row in a published A2.1 or A2.4 table, and the
counts it prints are the ones those tables already carry. The reason it exists as a tool rather
than as a shell loop is that hand-assembling a subset of these particular tables is what went
wrong three times in two days, so the checks below are the point:

* **A table must name its own release, and it must be the release asked for.** Band parts name
  their tables by policy and registry and never by release (D-245), so two tables that look
  alike can be different corpora. Every table's `manifest.release` is compared with the release
  the caller asked for, and a mismatch is a refusal.
* **Only keys lying directly under the task prefix are read.** A task prefix also holds
  commit-keyed provenance twins of its own tables, and merging a table with a copy of itself
  unions families instead of double-counting, so the error hides while the copies agree and
  surfaces only once they diverge (D-246). A key with a further `/` in it is refused.
* **Detectors are merged only on purpose, and the merge is named.** Setting a single-detector
  figure beside a merged one was D-247. A list's `detector` label says which it is, and
  `family_background.py` carries that label into the artefact so a reader can check that the
  two sides of a comparison are the same kind of object.
* **A table must agree with itself**: its family rows must number what its own `survival` block
  claims, and its hit and no-hit lists together must be the pinned universe.
* **The three policy readings must agree.** A2.1 publishes one table per reading of the
  published filter — charitable, literal, strict. They are three readings of the same text, not
  three experiments, so a detected set that depends on which one you picked would mean the
  reading changes what survives. They are compared as *sets* rather than as counts, because
  equal counts over different members would pass a count check and still be a different corpus.
  A disagreement is a refusal rather than a choice between them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import objectstore, profiles, repro

TASK = "A4.5"
REGISTRY = "pfam"
REGISTRY_VERSION = "38.2"
UNIVERSE_SIZE = 1719

#: The readings of the published filter A2.1 and A2.4 each publish a table for. All three must
#: give the same detected set; see this module's docstring for why that is checked and not
#: chosen between.
POLICIES = ("evo1-charitable", "evo1-literal", "evo1-strict")

#: `(task, detector)` for each route into the A3.2 headline. The headline is their union; the
#: profile-search figure is the first alone.
ROUTES = (("a2-1", "profile-hmmer"), ("a2-4", "provirus-genomad"))

#: The two releases, named as the manifests name them.
RELEASES = ("opengenome", "opengenome2")

#: The lists this tool writes: label, and the routes whose families it unions.
LISTS = (
    ("profile-hmmer", ("a2-1",)),
    ("profile-hmmer+provirus-genomad", ("a2-1", "a2-4")),
)


def table_key(task: str, policy: str, release: str) -> str:
    """The key of one published detection table, directly under its task prefix."""
    return f"corpora/results/{task}/detections-pfam-{policy}-{release}.json"


def fetch(client: Any, key: str, cache: Path) -> dict[str, Any]:
    """One table, cached locally by key, with its digest recorded.

    The key is checked to lie directly under the task prefix before it is read: a commit-keyed
    twin of the same table sits one segment deeper and is a copy, not a second measurement
    (D-246).
    """
    tail = key.split("corpora/results/", 1)[1].split("/", 1)[1]
    if "/" in tail:
        raise SystemExit(
            f"{key}: not directly under its task prefix. A task prefix also holds commit-keyed "
            "copies of its own tables, and a copy is not a second measurement (D-246)."
        )
    local = cache / key.replace("/", "__")
    if not local.exists():
        local.parent.mkdir(parents=True, exist_ok=True)
        body = client.get_object(Bucket=objectstore.CORPORA_BUCKET, Key=key)["Body"].read()
        local.write_bytes(body)
    raw = local.read_bytes()
    table = json.loads(raw)
    table["_key"] = key
    table["_sha256"] = hashlib.sha256(raw).hexdigest()
    return table


def check(table: dict[str, Any], *, release: str, detector: str, universe: set[str]) -> set[str]:
    """Every refusal this tool makes about a single table. Returns its detected families."""
    key = table["_key"]
    if table.get("registry") != REGISTRY or table.get("registry_version") != REGISTRY_VERSION:
        raise SystemExit(
            f"{key}: registry {table.get('registry')} {table.get('registry_version')}, "
            f"expected {REGISTRY} {REGISTRY_VERSION}. The universe is pinned to one release of "
            "one registry and a detected set from another is not a subset of it."
        )
    declared = (table.get("manifest") or {}).get("release")
    if declared != release:
        raise SystemExit(
            f"{key}: the table's manifest names release {declared!r}, not {release!r}. "
            "Band parts do not name their release (D-245), so this is the only place the "
            "corpus a table describes is written down."
        )
    if table.get("detector") != detector:
        raise SystemExit(f"{key}: detector {table.get('detector')!r}, expected {detector!r}.")

    families = [row["family_id"] for row in table["families"]]
    hit = set(families)
    if len(hit) != len(families):
        raise SystemExit(f"{key}: the family rows repeat an accession.")
    claimed = (table.get("survival") or {}).get("families_with_a_hit")
    if claimed != len(hit):
        raise SystemExit(
            f"{key}: {len(hit)} family rows but survival claims {claimed}. The table does not "
            "agree with itself, so neither figure can be transcribed."
        )
    missed = set(table["families_without_a_hit"])
    if hit | missed != universe or hit & missed:
        raise SystemExit(
            f"{key}: the hit and no-hit lists are not a partition of the pinned universe "
            f"({len(hit)} + {len(missed)} over {len(universe)}). A zero is only a measured zero "
            "if every family is on exactly one of the two lists."
        )
    return hit


def agreed(sets: dict[str, set[str]], what: str) -> set[str]:
    """The one set the three readings share, or a refusal naming how they differ."""
    distinct = {frozenset(s) for s in sets.values()}
    if len(distinct) != 1:
        sizes = {policy: len(s) for policy, s in sets.items()}
        union = set().union(*sets.values())
        common = set.intersection(*sets.values())
        raise SystemExit(
            f"{what}: the three readings of the filter give different detected sets "
            f"({sizes}); {len(union - common)} families are detected under some readings and "
            "not others. That would mean the reading changes what survives, which is a result "
            "and not something to pick a side of here."
        )
    return set(next(iter(distinct)))


def build(client: Any, cache: Path, universe: set[str]) -> dict[str, Any]:
    """Fetch and check every table, and reduce them to one detected set per list per release."""
    tables: dict[tuple[str, str, str], dict[str, Any]] = {}
    hits: dict[tuple[str, str, str], set[str]] = {}
    for release in RELEASES:
        for task, detector in ROUTES:
            for policy in POLICIES:
                table = fetch(client, table_key(task, policy, release), cache)
                tables[release, task, policy] = table
                hits[release, task, policy] = check(
                    table, release=release, detector=detector, universe=universe
                )

    built: dict[str, Any] = {"lists": [], "tables": []}
    for (release, task, policy), table in sorted(tables.items()):
        built["tables"].append(
            {
                "key": table["_key"],
                "sha256": table["_sha256"],
                "task": table["task"],
                "detector": table["detector"],
                "release": release,
                "policy_id": policy,
                "estimate_kind": table.get("estimate_kind"),
                "sample_rate": (table.get("sample") or {}).get("rate"),
                "families_with_a_hit": len(hits[release, task, policy]),
            }
        )

    for release in RELEASES:
        for detector, tasks in LISTS:
            per_policy = {
                policy: set().union(*(hits[release, task, policy] for task in tasks))
                for policy in POLICIES
            }
            detected = agreed(per_policy, f"{release} {detector}")
            built["lists"].append(
                {
                    "release": release,
                    "detector": detector,
                    "tasks": list(tasks),
                    "source_keys": [table_key(t, p, release) for t in tasks for p in POLICIES],
                    "families": sorted(detected),
                }
            )
    return built


HEADER = """\
# A4.5 — families detected in one release by one set of detectors, transcribed from the
# published per-family tables. Nothing here is recomputed; see tools/detected_families.py.
# release: {release}
# detector: {detector}
# families: {count}
# policy_readings: {policies} — all three give this same set, compared as sets and not counts
# source_keys: {keys}
"""


def write(built: dict[str, Any], outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    written = []
    for entry in built["lists"]:
        slug = entry["detector"].replace("+", "-plus-")
        path = outdir / f"detected-{entry['release']}-{slug}.txt"
        path.write_text(
            HEADER.format(
                release=entry["release"],
                detector=entry["detector"],
                count=len(entry["families"]),
                policies=", ".join(POLICIES),
                keys=" ".join(entry["source_keys"]),
            )
            + "".join(f"{a}\n" for a in entry["families"])
        )
        written.append(path)
    (outdir / "detected-sources.json").write_text(
        json.dumps(
            {
                "task": TASK,
                "registry": REGISTRY,
                "registry_version": REGISTRY_VERSION,
                "families_in_universe": UNIVERSE_SIZE,
                "tables": built["tables"],
                "lists": [
                    {k: v for k, v in entry.items() if k != "families"}
                    | {"families": len(entry["families"])}
                    for entry in built["lists"]
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    written.append(outdir / "detected-sources.json")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dat", type=Path, default=Path("data/profiles/Pfam-A.hmm.dat.gz"))
    parser.add_argument("--outdir", type=Path, default=Path("artifacts/a4-5/detected"))
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("artifacts/a4-5-tables"),
        help=(
            "where fetched tables are kept. Outside the committed artefact directory: the "
            "tables are inputs, and `detected-sources.json` records each one's key and digest, "
            "which is the provenance a reader needs"
        ),
    )
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    universe = set(profiles.select_viral_families(args.dat))
    if len(universe) != UNIVERSE_SIZE:
        raise SystemExit(
            f"{args.dat}: the pin gives {len(universe)} viral families, not {UNIVERSE_SIZE}. "
            "The universe was fixed before anything was searched and every survival "
            "denominator depends on it."
        )

    with repro.run(
        TASK,
        outdir=args.outdir,
        manifest_name="run-detected.json",
        allow_dirty=args.allow_dirty,
        durable=objectstore.durable_results(TASK),
    ) as manifest:
        manifest.parameter("policy_readings", list(POLICIES))
        manifest.parameter("releases", list(RELEASES))
        manifest.parameter("families_in_universe", len(universe))
        manifest.input_file(args.dat, role="pfam family metadata")
        built = build(objectstore.client(), args.cache, universe)
        for path in write(built, args.outdir):
            manifest.output_file(path, role="detected list")

    for entry in built["lists"]:
        print(f"{entry['release']:12s} {entry['detector']:32s} {len(entry['families']):4d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

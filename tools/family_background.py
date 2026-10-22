#!/usr/bin/env python3
"""Measure the pinned viral families' occurrence outside viruses — task A4.5, §A4.

    pixi run -e dev python tools/family_background.py \
        --dat data/profiles/Pfam-A.hmm.dat.gz \
        --sprot data/uniprotkb/uniprot_sprot-2026_03.dat.gz

`amazebio.background` holds the reading and what it does not claim. The short form: a Pfam
survival figure counts families, and a family that also occurs in cellular proteomes cannot by
itself be read as viral material in the corpus. This measures which families those are.

**Two instruments, because one is not enough here.** The project has been bitten three times
in two days by a table whose two halves described different things (D-245, D-246, D-247), and
the failure mode each time was a single instrument agreeing with itself.

* **Instrument 1** is a forward pass over the reviewed section's flat file, parsing the
  publisher's own `DR Pfam` cross-references and the entry's own organism lineage. The pass is
  checked against the release's published reviewed-entry total before any figure is reported,
  because a truncated stream yields a smaller count and no error — and a smaller count here
  would read as *fewer families are shared*, an error in the direction that flatters the claim.
* **Instrument 2** is InterPro's own API, which performs the same join at EBI against its own
  copy of the data: per family, reviewed proteins matching the family, and reviewed proteins
  matching it whose organism sits under the viral root. It is a different codebase over a
  different index, so the two agreeing is evidence about the join rather than about this parser.

The two are reported side by side per family and never merged. Where they disagree, the
disagreement is the result for that family.

**Costs nothing but local time.** Stage 1 is a single 700 MB read, about 75 seconds. Stage 2 is
two small requests per family against a public API, rate-limited to a few at a time out of
politeness rather than necessity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import background, profiles, repro

TASK = "A4.5"

#: The pinned reviewed-section release, and the publisher's own statements about it.
#:
#: `entries` is the count the release notes publish for the reviewed section. It is a
#: truncation guard, not decoration: the pass refuses rather than reports if the entries it
#: actually saw do not match.
SPROT_RELEASE = "2026_03"
SPROT_MD5 = "a31b5d0756f0a8f94164bf20b703812c"
SPROT_ENTRIES = 575_748
SPROT_SOURCE = (
    "https://ftp.uniprot.org/pub/databases/uniprot/current_release/"
    "knowledgebase/complete/uniprot_sprot.dat.gz"
)
SPROT_DIGEST_SOURCE = (
    "https://ftp.uniprot.org/pub/databases/uniprot/current_release/"
    "knowledgebase/complete/RELEASE.metalink"
)

#: NCBI's taxonomy root for viruses. InterPro's taxonomy filter takes a taxon id, and this is
#: the node UniProt's own `Viruses` lineage element corresponds to.
VIRAL_TAXON = "10239"

INTERPRO = "https://www.ebi.ac.uk/interpro/api"

#: The frozen selection vocabulary, rebuilt here from `profiles.VIRAL_KEYWORDS` rather than
#: borrowed from that module's private pattern: the artefact reports which word admitted each
#: family, and that report has to be derivable from the published list.
KEYWORDS = re.compile("|".join(re.escape(k) for k in profiles.VIRAL_KEYWORDS), re.IGNORECASE)


def md5_of(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------------------
# Instrument 1 — the reviewed section's own flat file
# --------------------------------------------------------------------------------------


def reviewed_pass(
    sprot: Path, universe: Iterable[str]
) -> tuple[dict[str, background.FamilyBackground], dict[str, int]]:
    """One forward pass. Returns the per-family table and the pass's own entry tallies."""
    table = {accession: background.FamilyBackground(accession=accession) for accession in universe}
    entries = viral = 0
    started = time.time()
    for entry in background.iter_entries(sprot):
        entries += 1
        if entry.viral:
            viral += 1
        for family in entry.families:
            found = table.get(family)
            if found is None:
                continue
            if entry.viral:
                found.reviewed_viral += 1
                continue
            found.reviewed_non_viral += 1
            if entry.endogenous:
                found.non_viral_endogenous += 1
            if entry.taxid is not None:
                found.non_viral_taxa.add(entry.taxid)
        if entries % 200_000 == 0:
            print(f"  {entries} entries, {time.time() - started:.0f}s", flush=True)

    if entries != SPROT_ENTRIES:
        raise SystemExit(
            f"read {entries} reviewed entries, but release {SPROT_RELEASE} publishes "
            f"{SPROT_ENTRIES}. A short read reports fewer shared families than there are, "
            "which is the direction that flatters the claim under test, so this is a refusal."
        )
    return table, {"entries": entries, "viral_entries": viral}


# --------------------------------------------------------------------------------------
# Instrument 2 — InterPro's own join, over its own index
# --------------------------------------------------------------------------------------


def _count(url: str, *, attempts: int = 4) -> int:
    """The `count` field of one InterPro listing, with a short backoff.

    A failed request is retried rather than treated as zero. Zero is a meaningful answer here —
    it is what a viral-only family looks like — so a transport error that returned it silently
    would manufacture the result the measurement is testing for.

    **The one empty answer that is data.** InterPro serves `204 No Content` for a filter that
    matches nothing, and `404` for an entry with no proteins at all. Both mean zero and are
    read as zero. Every other empty or unparseable body is a transport failure and is retried,
    because the two look identical from here and only one of them is a measurement.
    """
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status == 204:
                    return 0
                return int(json.load(response)["count"])
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                # InterPro serves 404 for an entry with no matching proteins at all.
                return 0
            last = exc
        except Exception as exc:
            last = exc
        time.sleep(2**attempt)
    raise RuntimeError(f"{url}: failed {attempts} times ({last})")


def interpro_counts(accession: str) -> dict[str, int]:
    """Reviewed proteins matching this family, in total and under the viral taxonomy root."""
    base = f"{INTERPRO}/protein/reviewed/entry/pfam/{accession}/?page_size=1"
    viral = (
        f"{INTERPRO}/protein/reviewed/entry/pfam/{accession}"
        f"/taxonomy/uniprot/{VIRAL_TAXON}/?page_size=1"
    )
    total = _count(base)
    return {"reviewed_total": total, "reviewed_viral": _count(viral)}


def interpro_pass(universe: list[str], *, workers: int, cache: Path | None) -> dict[str, Any]:
    """Per-family counts from InterPro, cached so a re-run does not re-ask for what it has."""
    held: dict[str, Any] = {}
    if cache is not None and cache.exists():
        held = json.loads(cache.read_text())
    todo = [a for a in universe if a not in held]
    print(f"  interpro: {len(held)} cached, {len(todo)} to fetch", flush=True)
    started = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for accession, counts in zip(todo, pool.map(interpro_counts, todo), strict=True):
            held[accession] = counts
            done += 1
            if done % 25 == 0 or done <= 3 or done == len(todo):
                rate = done / max(time.time() - started, 1e-9)
                print(
                    f"  interpro {done}/{len(todo)}, {rate:.1f}/s, "
                    f"{(len(todo) - done) / max(rate, 1e-9) / 60:.0f} min left",
                    flush=True,
                )
                if cache is not None:
                    cache.write_text(json.dumps(held, sort_keys=True))
    if cache is not None:
        cache.write_text(json.dumps(held, sort_keys=True))
    return held


# --------------------------------------------------------------------------------------
# The detected sets, restricted to the specific families
# --------------------------------------------------------------------------------------

#: The three variants, fixed in the task file before any restricted count existed.
VARIANTS = ("headline", "specific", "specific_plus_endogenous")


def read_detected(path: Path, universe: set[str]) -> dict[str, Any]:
    """One detected-family list: accessions, plus the labels that say what set it is.

    **Why the labels are required rather than inferred.** A2.1's band parts name their tables
    by policy and registry and never by release (D-245), so two lists that look alike can be
    different releases, and setting one beside the other produced a headline a third wrong for
    a day. A list that does not say which release and which detector it came from is refused
    here rather than counted, and the labels travel into the artefact so a reader can check
    that the two sides of a comparison are the same kind of object.

    An accession outside the pinned universe is also a refusal: the detected set is a subset of
    the denominator by construction, so a stranger in the file means the list was built against
    a different registry or a different Pfam release.
    """
    declared: dict[str, str] = {}
    accessions: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            key, _, value = line.lstrip("# ").partition(":")
            if value:
                declared[key.strip().lower()] = value.strip()
            continue
        accessions.append(line)

    missing = [k for k in ("release", "detector") if k not in declared]
    if missing:
        raise SystemExit(
            f"{path}: no {' or '.join(missing)} declared. Band parts do not name their release "
            "(D-245), so an unlabelled list cannot be set beside another one; add "
            "'# release: ...' and '# detector: ...' lines naming what this list is."
        )
    strangers = sorted(set(accessions) - universe)
    if strangers:
        raise SystemExit(
            f"{path}: {len(strangers)} accessions are not in the pinned universe "
            f"(first: {strangers[:3]}). The detected set is a subset of the denominator by "
            "construction, so this list was built against a different registry or release."
        )
    return {
        "path": str(path),
        "release": declared["release"],
        "detector": declared["detector"],
        "source_keys": declared.get("source_keys"),
        "accessions": sorted(set(accessions)),
    }


def restrict(
    detected: dict[str, Any], table: dict[str, background.FamilyBackground]
) -> dict[str, Any]:
    """The three variants for one detected set, each with and without the unjudgeable families.

    Two numbers per variant, deliberately. A family the curated section cannot speak to is
    neither specific nor shared, and a single figure would have to put it on one side or the
    other. The pair is the result.
    """
    rows = [table[a] for a in detected["accessions"]]
    classes = {a: background.classify(table[a]) for a in detected["accessions"]}
    unmeasurable = [a for a, c in classes.items() if c == "unmeasurable"]
    viral_only = [a for a, c in classes.items() if c == "viral_only"]
    endogenous_only = [
        a
        for a, c in classes.items()
        if c == "shared" and table[a].non_viral_endogenous == table[a].reviewed_non_viral
    ]
    counts = {
        "headline": {"excluding_unmeasurable": len(rows), "including_unmeasurable": len(rows)},
        "specific": {
            "excluding_unmeasurable": len(viral_only),
            "including_unmeasurable": len(viral_only) + len(unmeasurable),
        },
        "specific_plus_endogenous": {
            "excluding_unmeasurable": len(viral_only) + len(endogenous_only),
            "including_unmeasurable": len(viral_only) + len(endogenous_only) + len(unmeasurable),
        },
    }
    return {
        "release": detected["release"],
        "detector": detected["detector"],
        "source": detected["path"],
        "source_keys": detected["source_keys"],
        "detected": len(rows),
        "unmeasurable": len(unmeasurable),
        "viral_only": len(viral_only),
        "shared": len(rows) - len(viral_only) - len(unmeasurable),
        "shared_endogenous_only": len(endogenous_only),
        "variants": counts,
        "comparability": (
            "every variant here is the same detector at the same depth over the same corpus as "
            "its own headline; variants from different detectors are never set side by side "
            "(D-247)"
        ),
    }


# --------------------------------------------------------------------------------------
# The artefact
# --------------------------------------------------------------------------------------


def build(
    table: dict[str, background.FamilyBackground],
    meta: dict[str, profiles.FamilyMeta],
    tallies: dict[str, int],
    interpro: dict[str, Any],
    detected: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = []
    agree = disagree = uncompared = 0
    host_only: list[str] = []
    cellular_only: list[str] = []
    for accession in sorted(table):
        row = table[accession].row()
        row["name"] = meta[accession].name
        row["description"] = meta[accession].description
        words = background.admitting_words(
            f"{meta[accession].name} {meta[accession].description}", KEYWORDS
        )
        row["admitted_by"] = list(words)
        if words and all(
            any(host in word for host in background.HOST_SUBSTRING_WORDS) for word in words
        ):
            host_only.append(accession)
            row["admitted_by_host_word_only"] = True
        if table[accession].reviewed_viral == 0 and table[accession].reviewed_non_viral > 0:
            cellular_only.append(accession)
        counts = interpro.get(accession)
        if counts is None:
            row["interpro"] = None
            uncompared += 1
        else:
            non_viral = counts["reviewed_total"] - counts["reviewed_viral"]
            row["interpro"] = {
                "reviewed_total": counts["reviewed_total"],
                "reviewed_viral": counts["reviewed_viral"],
                "reviewed_non_viral": non_viral,
                "class": background.classify(
                    background.FamilyBackground(
                        accession=accession,
                        reviewed_viral=counts["reviewed_viral"],
                        reviewed_non_viral=non_viral,
                    )
                ),
            }
            if row["interpro"]["class"] == row["class"]:
                agree += 1
            else:
                disagree += 1
        rows.append(row)

    summary = background.summarise(table)
    return {
        "task": TASK,
        "design_ref": "§A4",
        "question": (
            "for each family in the pinned viral universe, how often does it occur in the "
            "curated section of UniProtKB outside viral organisms"
        ),
        "does_not_claim": [
            "no survival figure is corrected by anything here",
            "a non-viral occurrence is not proof of independent cellular ancestry; host "
            "genomes carry integrated viral material and such an entry is annotated to the host",
            "a family absent from the curated section is unmeasurable here, never viral-only",
        ],
        "registry": {"id": "pfam", "version": "38.2", "universe_from": "Pfam-A.hmm.dat.gz"},
        "background_source": {
            "name": "UniProtKB reviewed section",
            "release": SPROT_RELEASE,
            "url": SPROT_SOURCE,
            "md5": SPROT_MD5,
            "md5_source": SPROT_DIGEST_SOURCE,
            "published_entries": SPROT_ENTRIES,
            "entries_read": tallies["entries"],
            "viral_entries_read": tallies["viral_entries"],
        },
        "second_instrument": {
            "name": "InterPro API",
            "endpoint": f"{INTERPRO}/protein/reviewed/entry/pfam/<acc>/",
            "viral_taxon": VIRAL_TAXON,
            "families_compared": agree + disagree,
            "class_agreements": agree,
            "class_disagreements": disagree,
            "families_not_compared": uncompared,
        },
        "summary": summary,
        "selection_audit": {
            "what_this_is": (
                "what the frozen selection vocabulary matched inside, per family. The rule "
                "asks only whether a keyword occurs; this asks what word it occurred in, "
                "which is what separates bacteriophage from macrophage."
            ),
            "denominator_unchanged": (
                "the 1,719 universe is pre-registered and is not corrected here. A cellular "
                "family in it contributes a near-certain zero, so it pushes the survival "
                "fraction down: the denominator is conservative, not inflated."
            ),
            "host_substring_words": list(background.HOST_SUBSTRING_WORDS),
            "admitted_by_host_word_only": host_only,
            "no_curated_viral_entry_but_cellular_ones": len(cellular_only),
            "no_curated_viral_entry_but_cellular_ones_families": cellular_only,
        },
        "detected_sets": [restrict(d, table) for d in (detected or [])],
        "detected_sets_outstanding": not detected,
        "per_family": rows,
    }


def report(doc: dict[str, Any]) -> str:
    classes = doc["summary"]["classes"]
    second = doc["second_instrument"]
    total = doc["summary"]["families"]
    lines = [
        "# A4.5 — occurrence of the pinned viral families outside viruses",
        "",
        f"Universe: {total} Pfam 38.2 families (the pre-registered viral selection, unchanged).",
        f"Background: UniProtKB reviewed section {doc['background_source']['release']}, "
        f"{doc['background_source']['entries_read']} entries read "
        f"({doc['background_source']['viral_entries_read']} of them viral).",
        "",
        "| class | families | share of universe |",
        "|---|---|---|",
    ]
    for name in ("viral_only", "shared", "unmeasurable"):
        lines.append(f"| `{name}` | {classes[name]} | {classes[name] / total:.1%} |")
    measured = doc["summary"]["measured"]
    lines += [
        "",
        f"Of the {measured} families the curated section can speak to, "
        f"{classes['viral_only']} ({classes['viral_only'] / measured:.1%}) have no curated "
        f"occurrence outside viruses and {classes['shared']} "
        f"({classes['shared'] / measured:.1%}) do.",
        f"Of those {classes['shared']}, {doc['summary']['shared_endogenous_only']} have every "
        "non-viral occurrence marked by the curators as integrated viral material, so the "
        "sharing is a host genome carrying the element rather than the family having cellular "
        "members.",
        f"Median distinct non-viral organisms behind a shared family: "
        f"{doc['summary']['shared_taxa_median']}.",
        "",
        f"Second instrument: {second['class_agreements']} of {second['families_compared']} "
        f"families classed the same way by InterPro's own join "
        f"({second['class_disagreements']} disagreements).",
    ]

    audit = doc["selection_audit"]
    lines += [
        "",
        "## What the selection vocabulary matched inside",
        "",
        f"{len(audit['admitted_by_host_word_only'])} families are in the universe only because "
        f"a keyword is a substring of a word naming nothing viral "
        f"({', '.join(audit['host_substring_words'])}): "
        f"{', '.join(audit['admitted_by_host_word_only'])}.",
        "",
        f"{audit['no_curated_viral_entry_but_cellular_ones']} families have no curated viral "
        "entry at all while having at least one curated cellular entry.",
        "",
        audit["denominator_unchanged"],
    ]

    if doc["detected_sets_outstanding"]:
        lines += [
            "",
            "## The detected sets",
            "",
            "Outstanding. The per-family detection lists from A2.1/A3.2 were not reachable from "
            "the run that produced this artefact, so every figure above is over the whole "
            "pre-registered universe and none of it is weighted by what was actually detected. "
            "Detected families are not a random draw from the universe — an abundant family is "
            "more likely to be found — so the universe figures are not a substitute and must "
            "not be quoted as though they were.",
        ]
    else:
        lines += ["", "## The detected sets", ""]
        for one in doc["detected_sets"]:
            lines += [
                f"**{one['release']}, {one['detector']}** — {one['detected']} detected "
                f"families: {one['viral_only']} with no curated non-viral occurrence, "
                f"{one['shared']} shared, {one['unmeasurable']} unjudgeable.",
                "",
                "| variant | excluding unjudgeable | including unjudgeable |",
                "|---|---|---|",
            ]
            for variant in VARIANTS:
                counts = one["variants"][variant]
                lines.append(
                    f"| `{variant}` | {counts['excluding_unmeasurable']} "
                    f"| {counts['including_unmeasurable']} |"
                )
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dat", type=Path, required=True, help="Pfam-A.hmm.dat.gz, pinned release")
    ap.add_argument("--sprot", type=Path, required=True, help="uniprot_sprot.dat.gz, pinned")
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a4-5"))
    ap.add_argument("--interpro-workers", type=int, default=4)
    ap.add_argument("--interpro-cache", type=Path, default=Path("artifacts/a4-5/interpro.json"))
    ap.add_argument(
        "--skip-interpro",
        action="store_true",
        help="run instrument 1 only. The artefact then records the comparison as not made.",
    )
    ap.add_argument(
        "--detected",
        type=Path,
        action="append",
        default=[],
        help=(
            "a detected-family accession list from A2.1/A3.2, one per release and detector. "
            "The file must declare '# release:' and '# detector:'; see read_detected."
        ),
    )
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    digest = md5_of(args.sprot)
    if digest != SPROT_MD5:
        raise SystemExit(
            f"{args.sprot}: md5 {digest} is not the publisher's {SPROT_MD5} for release "
            f"{SPROT_RELEASE}. The background must come from the pinned release."
        )

    args.outdir.mkdir(parents=True, exist_ok=True)
    meta = profiles.select_viral_families(args.dat)
    universe = sorted(meta)

    try:
        with (
            repro.run(
                TASK,
                seed=None,  # two forward passes and a set of lookups; nothing here is random
                outdir=args.outdir,
                allow_dirty=args.allow_dirty,
                manifest_name="run-background.json",
                durable_exempt=(
                    "the artefact is a 1,719-row table that is committed to the repository, which "
                    "is a more durable home than the results bucket for something this small; the "
                    "bucket is also unreachable from this session's credentials"
                ),
            ) as manifest
        ):
            manifest.parameter("background_release", SPROT_RELEASE)
            manifest.parameter("background_md5", SPROT_MD5)
            manifest.parameter("published_entries", SPROT_ENTRIES)
            manifest.parameter("viral_taxon", VIRAL_TAXON)
            manifest.parameter("second_instrument", "none" if args.skip_interpro else "interpro")
            manifest.parameter("universe", len(universe))
            manifest.input_file(args.dat, role="pfam family metadata")
            manifest.input_file(args.sprot, role="curated background")

            print("instrument 1: reviewed section", flush=True)
            table, tallies = reviewed_pass(args.sprot, universe)
            interpro: dict[str, Any] = {}
            if not args.skip_interpro:
                print("instrument 2: interpro", flush=True)
                interpro = interpro_pass(
                    universe, workers=args.interpro_workers, cache=args.interpro_cache
                )

            detected = [read_detected(p, set(universe)) for p in args.detected]
            for one in detected:
                manifest.input_file(Path(one["path"]), role=f"detected: {one['release']}")
            doc = build(table, meta, tallies, interpro, detected)
            (args.outdir / "background-pfam-38.2.json").write_text(
                json.dumps(doc, indent=2, sort_keys=True) + "\n"
            )
            (args.outdir / "background-pfam-38.2.md").write_text(report(doc) + "\n")
            manifest.output_file(args.outdir / "background-pfam-38.2.json", role="table")
            manifest.output_file(args.outdir / "background-pfam-38.2.md", role="summary")
    except repro.ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    print("\n" + report(doc), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

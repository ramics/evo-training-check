"""Decompose A1.8's UniProtKB release count into the two halves the source publishes.

ESM3's A.6.1 reports its select-agent denylist as **two** figures — "147K non-viral
sequences and 40K additional viral sequences" — and D-157 compared three readings against
only their sum, concluding that the published figure "sits below every reading we can
construct from the regulation". That is true of the sum. It is not true of the halves, and
the halves are the stronger test: a sum can be hit by two errors of opposite sign, so a
reading that lands near both halves at once is evidence where a reading that lands near the
total is arithmetic.

This tool costs nothing to run. The 2.64-hour pass over the 182.7 GB archive already
recorded per-taxon counts, and the Viruses superkingdom is in the same pinned taxonomy the
reading was resolved against, so every figure here is a regrouping of a measurement already
taken (the same argument D-157 used to measure strain descent without a second pass).

What it reports, per reading: the two halves against the two published halves, the same
split by CFR section — because "the Select Agents and Toxins List" could mean the HHS list
alone (42 CFR 73) or all three codified parts, and the source does not say — and the
per-entry contribution to each half, so a discrepancy can be located rather than quoted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from amazebio import repro, seeds, selectagents  # noqa: E402

DEFAULT_CAPTURES = REPO_ROOT / "policies" / "captures"
DEFAULT_MAPPING = REPO_ROOT / "policies" / "specs" / "select-agents-2024-06-01.json"
SECTION_FILES = {
    "73.3": "cfr-title42-part73-2024-06-01.xml",
    "73.4": "cfr-title42-part73-2024-06-01.xml",
    "121.3": "cfr-title9-part121-2024-06-01.xml",
    "331.3": "cfr-title7-part331-2024-06-01.xml",
}
#: The parts the HHS reading would keep. 42 CFR 73 is the human-health list; 9 CFR 121 and
#: 7 CFR 331 are USDA's animal and plant lists. The source cites the summary page that
#: covers all three, so the full-list reading is the primary one — but the narrower reading
#: is constructible from the same regulation and is therefore measured, not argued about.
HHS_SECTIONS = ("73.3", "73.4")


def load_reading(
    captures: Path, mapping_path: Path
) -> tuple[tuple[selectagents.ListEntry, ...], dict[str, selectagents.MappedEntry]]:
    """Parse the pinned captures and the curated table, refusing anything off-digest."""
    for pin in selectagents.PINS_2024:
        stored = captures / Path(pin.capture).name
        if not stored.exists():
            raise SystemExit(f"missing pinned CFR capture: {stored}")
        if repro.sha256_file(stored) != pin.sha256:
            raise SystemExit(f"{stored.name} does not match its recorded digest; refusing")
    entries = selectagents.parse_all(
        (section, (captures / name).read_bytes()) for section, name in SECTION_FILES.items()
    )
    return entries, selectagents.load_mapping(mapping_path)


def readings(
    entries: tuple[selectagents.ListEntry, ...],
    mapping: dict[str, selectagents.MappedEntry],
    taxonomy: seeds.Taxonomy,
) -> dict[str, dict[str, frozenset[int]]]:
    """The per-entry taxon sets for each reading the regulation admits, by entry key."""
    return {
        "named_and_strains": selectagents.expand_by_entry(entries, mapping, taxonomy),
        "named_only": selectagents.named_by_entry(entries, mapping),
    }


def _sections(entries: tuple[selectagents.ListEntry, ...]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for entry in entries:
        out.setdefault(entry.key, set()).add(entry.section)
    return out


def decompose(
    per_entry: dict[str, frozenset[int]],
    by_taxid: dict[int, int],
    viral: frozenset[int],
    sections: dict[str, set[str]],
    influenza_keys: tuple[str, ...],
) -> dict[str, Any]:
    """One reading's halves, overall, by CFR scope, and per entry.

    The three scopes are unioned before counting rather than summed after it. Entries whose
    taxon sets overlap — and under descent several do — would otherwise be counted once per
    entry, which inflates every subtotal and is exactly the error `exclusive` exists to
    expose in the per-entry view.
    """
    pooled = frozenset().union(*per_entry.values()) if per_entry else frozenset()
    hhs = frozenset().union(
        *(s for k, s in per_entry.items() if sections[k] & set(HHS_SECTIONS)), frozenset()
    )
    # Union over the *other* entries, not `pooled - flu`: a taxon another entry also names
    # would be removed by the subtraction, which would understate the remainder.
    without_flu = frozenset().union(
        *(s for k, s in per_entry.items() if k not in influenza_keys), frozenset()
    )

    def halves(taxa: frozenset[int]) -> dict[str, Any]:
        got = selectagents.split_halves(by_taxid, taxa, viral)
        return {
            **got.to_dict(),
            "vs_published": got.ratio_to(selectagents.PUBLISHED_HALVES),
            "taxa": len(taxa),
        }

    return {
        "all_three_parts": halves(pooled),
        "all_three_parts_less_influenza_a": halves(without_flu),
        "hhs_list_only": halves(hhs),
        "by_entry": {
            key: selectagents.split_halves(by_taxid, taxa, viral).to_dict()
            for key, taxa in sorted(per_entry.items())
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--release-count",
        required=True,
        type=Path,
        help="the artefact uniprot_release_count.py wrote (its per-taxid totals)",
    )
    ap.add_argument("--captures", type=Path, default=DEFAULT_CAPTURES)
    ap.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    ap.add_argument("--taxdump", required=True, type=Path)
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a1-8"))
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    counted = json.loads(args.release_count.read_text())
    by_taxid = {int(k): v for k, v in counted["totals"]["by_taxid"].items()}

    out_path = args.outdir / "select-agent-decomposition.json"
    with repro.run(
        "A1.8",
        seed=None,  # a regrouping of a recorded measurement; nothing here is random
        outdir=args.outdir,
        manifest_name="run-select-agent-decomposition.json",
        allow_dirty=args.allow_dirty,
    ) as manifest:
        manifest.input_file(args.release_count, role="uniprotkb-release-count")
        manifest.input_file(args.taxdump, role="taxdump")
        manifest.parameter("uniprot_release", counted["uniprot_release"])
        manifest.parameter("published_viral", selectagents.PUBLISHED_HALVES.viral)
        manifest.parameter("published_non_viral", selectagents.PUBLISHED_HALVES.non_viral)

        entries, mapping = load_reading(args.captures, args.mapping)
        taxonomy = seeds.Taxonomy.from_taxdump_zip(args.taxdump)
        viral = frozenset(taxonomy.descendants(selectagents.VIRAL_ROOT))
        sections = _sections(entries)
        influenza = tuple(k for k in mapping if "Avian influenza" in k)
        if not influenza:
            raise SystemExit("no avian influenza entry in the reading; the mapping changed")

        payload: dict[str, Any] = {
            "uniprot_release": counted["uniprot_release"],
            "published": selectagents.PUBLISHED_HALVES.to_dict(),
            "published_source": "ESM3 version of record A.6.1 p47 (D-106)",
            "influenza_entry_keys": list(influenza),
            "readings": {
                name: decompose(per_entry, by_taxid, viral, sections, influenza)
                for name, per_entry in readings(entries, mapping, taxonomy).items()
            },
            "what_this_checks": (
                "whether either half of the published denylist is reproducible from the "
                "regulation at the release the source names. It does not validate A1.8's "
                "UniRef100 seed set, which counts a different object (D-150), and it is not "
                "evidence about how much denylisted material survived into the corpus."
            ),
        }
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        manifest.output_file(out_path, role="select-agent-decomposition")

    pub = selectagents.PUBLISHED_HALVES
    print(f"published{'':24s} viral {pub.viral:>9,}          non-viral {pub.non_viral:>9,}")
    for name, reading in payload["readings"].items():
        for scope, got in reading.items():
            if scope == "by_entry":
                continue
            print(
                f"{name:22s} {scope:30s} "
                f"viral {got['viral']:>9,} ({got['vs_published']['viral']:4.2f}x)  "
                f"non-viral {got['non_viral']:>9,} ({got['vs_published']['non_viral']:4.2f}x)"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

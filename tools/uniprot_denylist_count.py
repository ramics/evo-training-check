#!/usr/bin/env python3
"""Execute ESM3's stated select-agent denylist procedure against UniProtKB, and pin the count.

**Why this exists.** ESM3's version of record says, of the denylist whose size it publishes:
"we identify all sequences in UniProt belonging to organisms on the Select Agents and Toxins
List ... This process gives us 147K non-viral sequences and 40K additional viral sequences"
(§A.6.1, p47). That counts UniProtKB sequences. A1.8's seed set counts UniRef100 clusters,
because UniRef is what is staged and because cluster members catch material a
representative-only set misses (D-092). Comparing the two produced an apparent 5.8x
discrepancy that is entirely an artefact of comparing different objects (D-150).

So the published figure is validated against the thing it actually counts: the same curated
reading (D-137), executed against UniProtKB. That checks the *reading* — whether we resolved
the regulation's 70 entries to the same organisms the lab did — which is the only part of the
reconstruction a published denylist size can speak to. It does not and cannot validate the
UniRef100 seed set, and nothing here should be read as doing so.

**The release gap is real and is recorded rather than smoothed over.** UniProt's REST service
serves the current release only; ESM3's denylist was built against whatever release was in
force for its 2023_02 UniRef component, which the paper does not state. Querying the release
the filter saw would mean staging UniProtKB at that release, which is not justified for a
check on a reading. The release actually queried is written into the artefact, so a reader can
see the gap instead of inferring that none exists.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from amazebio import selectagents  # noqa: E402

ENDPOINT = "https://rest.uniprot.org/uniprotkb/search"

#: D-106, from the version of record: 147K non-viral plus 40K additional viral.
PUBLISHED_SEQUENCES = 187_000


def query(taxid: int, *, attempts: int = 3, pause: float = 2.0) -> tuple[int, str, str]:
    """Count UniProtKB entries for a taxon and its descendants, with the release served.

    `taxonomy_id` is the lineage-inclusive field — it matches entries whose organism sits at
    or beneath the taxon — which is what "belonging to organisms on the list" means for a list
    naming species whose sequenced material is deposited under strain taxids. `organism_id`
    would match the species node alone and miss the strains; measured on the top contributors
    that is a 43x difference for *Burkholderia pseudomallei* and 255x for *Xanthomonas
    oryzae*, so the choice is not cosmetic and is recorded here rather than left to the field
    name.
    """
    url = f"{ENDPOINT}?{urllib.parse.urlencode({'query': f'taxonomy_id:{taxid}', 'size': 0})}"
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return (
                    int(response.headers["x-total-results"]),
                    response.headers.get("x-uniprot-release", "unknown"),
                    response.headers.get("x-uniprot-release-date", "unknown"),
                )
        except (urllib.error.URLError, OSError, TypeError, ValueError) as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(pause)
    raise SystemExit(f"UniProtKB lookup failed for taxid {taxid} after {attempts} tries: {last}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--captures", type=Path, default=ROOT / "policies" / "captures")
    ap.add_argument(
        "--mapping",
        type=Path,
        default=ROOT / "policies" / "specs" / "select-agents-2024-06-01.json",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "policies" / "specs" / "select-agents-2024-06-01-uniprot-counts.json",
    )
    ap.add_argument("--toxin-producers", action="store_true")
    ap.add_argument("--alternatives", action="store_true")
    args = ap.parse_args(argv)

    entries = selectagents.parse_all(
        (section, (args.captures / name).read_bytes())
        for section, name in {
            "73.3": "cfr-title42-part73-2024-06-01.xml",
            "73.4": "cfr-title42-part73-2024-06-01.xml",
            "121.3": "cfr-title9-part121-2024-06-01.xml",
            "331.3": "cfr-title7-part331-2024-06-01.xml",
        }.items()
    )
    mapping = selectagents.load_mapping(args.mapping)

    by_entry: dict[str, int] = {}
    release = release_date = "unknown"
    for entry in entries:
        mapped = mapping.get(entry.key)
        if mapped is None:
            raise SystemExit(f"no recorded reading for list entry: {entry.key!r}")
        roots = mapped.producer_taxids if mapped.kind is selectagents.EntryKind.TOXIN else ()
        if mapped.kind is not selectagents.EntryKind.TOXIN:
            roots = (
                mapped.alternative_taxids
                if args.alternatives and mapped.alternative_taxids
                else mapped.taxids
            )
        elif not args.toxin_producers:
            roots = ()
        total = 0
        for taxid in roots:
            count, release, release_date = query(taxid)
            total += count
        by_entry[entry.key] = total
        print(f"{entry.key[:58]:60s} {total:8,}", flush=True)

    sequences = sum(by_entry.values())
    payload: dict[str, Any] = {
        "note": (
            "ESM3's stated select-agent denylist procedure executed against UniProtKB: 'all "
            "sequences in UniProt belonging to organisms on the Select Agents and Toxins "
            "List' (version of record, A.6.1 p47). This validates the reading in D-137, not "
            "A1.8's UniRef100 seed set — see D-150 and this tool's docstring."
        ),
        "uniprot_release": release,
        "uniprot_release_date": release_date,
        "release_gap": (
            "ESM3's denylist was built against the UniProt release in force for its UniRef "
            "2023_02 component, which the paper does not state. UniProt's REST service serves "
            "the current release only, so this count is at the release named above and not at "
            "the one the filter saw. The gap is a limitation of the check, not a finding."
        ),
        "reading": {"toxin_producers": args.toxin_producers, "alternatives": args.alternatives},
        "list_as_of": "2024-06-01",
        "published_sequences": PUBLISHED_SEQUENCES,
        "published_source": "D-106, ESM3 version of record: 147K non-viral + 40K viral",
        "sequences": sequences,
        "delta": sequences - PUBLISHED_SEQUENCES,
        "delta_share": (sequences - PUBLISHED_SEQUENCES) / PUBLISHED_SEQUENCES,
        "by_entry": dict(sorted(by_entry.items(), key=lambda kv: (-kv[1], kv[0]))),
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        f"\n{sequences:,} UniProtKB sequences at release {release} "
        f"against the published {PUBLISHED_SEQUENCES:,} "
        f"({payload['delta']:+,}, {100 * payload['delta_share']:+.1f}%)"
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

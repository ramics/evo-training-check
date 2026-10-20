#!/usr/bin/env python3
"""Replay the frozen denylist against successive taxonomy releases — task A9.1, §A9.

    pixi run -e dev python tools/denylist_decay.py --cache <dir>

Twenty-eight quarterly NCBI dumps from 2020-01-01 to 2026-10-01, baseline 2023-04-01, all
fixed in **D-201** before any of this ran. `amazebio.decay` holds the comparison and what it
separates; this downloads the releases, drives it over them, and writes the curve.

It runs here rather than in region. The dumps are about 60 MB each and come from NCBI, not
from the staged corpora, so `AGENTS.md`'s data-movement test does not apply: there is no
in-region copy to be near. 1.7 GB at the measured rate is a quarter of an hour.

Each release is parsed, reduced and dropped before the next is opened — 2.5 million nodes
times twenty-eight will not sit in memory at once, and nothing after the reduction needs the
whole dump.

**No re-validation interval is hidden in a constant here.** The artefact reports the observed
rate and then the interval implied by each of several tolerances, so a reader picks the
tolerance rather than inheriting one chosen after the curve was seen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import agreement, decay, objectstore, policyspec, repro

TASK = "A9.1"
ARCHIVE = "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump_archive"

#: D-201: quarterly, 2020-01-01 to 2026-10-01, with 2023-04-01 the baseline.
RELEASES: tuple[str, ...] = tuple(
    f"{year}-{month:02d}-01"
    for year in range(2020, 2027)
    for month in (1, 4, 7, 10)
    if not (year == 2026 and month > 10)
)
BASELINE = "2023-04-01"

#: Tolerances the interval is reported at, as a share of a release's viral taxa that are new
#: since the last validation and unnamed. Several rather than one, declared here rather than
#: chosen once the curve was in hand.
TOLERANCES: tuple[float, ...] = (0.005, 0.01, 0.05)


def fetch(date: str, cache: Path) -> tuple[Path, str]:
    """Download a dated dump if it is not cached, and return it with its digest.

    NCBI publishes no checksum beside these, so the digest is computed and recorded rather
    than verified. That still pins them: a later run that gets different bytes under the same
    date will not match the artefact, which is the property a replay needs.
    """
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"taxdmp_{date}.zip"
    if not path.exists():
        url = f"{ARCHIVE}/taxdmp_{date}.zip"
        print(f"  fetching {url}", flush=True)
        tmp = path.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=300) as src, tmp.open("wb") as dst:
            while chunk := src.read(1 << 20):
                dst.write(chunk)
        tmp.rename(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return path, digest


def frozen_names(specs: Path) -> tuple[dict[str, list[str]], list[str]]:
    """The names the rules give, by the rank each rule declares, and the eight stop taxa.

    Read from the committed specs rather than copied here, so a correction to a spec cannot
    leave this tool replaying a list the project no longer claims the authors published.
    """
    policy = policyspec.load_policy_dir(specs)["evo1-literal"]
    named: dict[str, list[str]] = {}
    stops: list[str] = []
    for rule in policy.rules:
        if rule.kind == "remove_if_taxon_in":
            named.setdefault(rule.params["rank"], []).extend(rule.params["names"])
        elif rule.kind == "remove_if_unspecific":
            stops = list(rule.params["stop_taxa"])
    return named, stops


def intervals(points: list[dict[str, Any]]) -> dict[str, Any]:
    """The observed rate after the baseline, and the interval each tolerance implies.

    The rate is a straight line through the post-baseline points rather than a fit with a
    shape: two and a half years of quarterly data cannot distinguish curvature from noise,
    and pretending otherwise would put a confident shape on four significant events.
    """
    after = [p for p in points if p["date"] >= BASELINE]
    if len(after) < 2:
        return {"rate_per_year": None, "note": "fewer than two post-baseline releases"}
    first, last = after[0], after[-1]
    years = (int(last["date"][:4]) - int(first["date"][:4])) + (
        int(last["date"][5:7]) - int(first["date"][5:7])
    ) / 12
    if years <= 0:
        return {"rate_per_year": None, "note": "the post-baseline window has no length"}
    unnamed_share = last["new_not_named"] / last["viral_taxa"] if last["viral_taxa"] else 0.0
    rate = unnamed_share / years
    return {
        "window": [first["date"], last["date"]],
        "years": round(years, 3),
        "unnamed_new_share_at_end": unnamed_share,
        "rate_per_year": rate,
        "revalidation_years": {f"{t:.3%}": (t / rate if rate else None) for t in TOLERANCES},
        "assumptions": [
            "The rate is the share of the latest release's viral taxa that are new since "
            "the baseline and unnamed, divided by the elapsed years. It is an average over "
            "the window, not an instantaneous rate.",
            "It assumes the taxonomy keeps erecting viral taxa at the rate it has since "
            "the baseline. A single large ICTV ratification would break that.",
            "It counts taxa, not sequence. A family with one member and a family with ten "
            "thousand count the same, so this bounds how fast the list stops naming things "
            "and not how much material escapes.",
            "Renames and renumberings are excluded, so the rate is new material only.",
        ],
    }


def summarise(doc: dict[str, Any]) -> str:
    points = doc["releases"]
    base = next(p for p in points if p["date"] == BASELINE)
    last = points[-1]
    out = [
        f"{len(points)} releases, {points[0]['date']} to {last['date']}, " f"baseline {BASELINE}",
        "",
        f"{'release':<12}{'viral taxa':>12}{'named':>12}{'share':>9}"
        f"{'new unnamed':>13}{'renamed':>9}{'unreachable':>12}",
    ]
    for p in points:
        out.append(
            f"{p['date']:<12}{p['viral_taxa']:>12,}{p['reach']:>12,}"
            f"{p['reach_share']:>9.4f}{p['new_not_named']:>13,}"
            f"{p['renamed']:>9,}{len(p['unreachable_names']):>12}"
        )
    out += [
        "",
        f"reach fell from {base['reach_share']:.4f} at the baseline to "
        f"{last['reach_share']:.4f}",
        f"the rule that asks the release its own question: {base['computed_share']:.4f} "
        f"to {last['computed_share']:.4f}",
        "",
        f"new viral taxa since the baseline that no frozen name reaches: "
        f"{last['new_not_named']:,}",
        f"renamed, same taxon: {last['renamed']:,}  ·  renumbered: {last['renumbered']:,}  "
        f"·  re-ranked: {last['reranked']:,}",
    ]
    iv = doc["revalidation"]
    if iv.get("rate_per_year"):
        out.append("")
        out.append(f"observed rate: {iv['rate_per_year']:.4%} of the viral taxonomy per year")
        for tol, years in iv["revalidation_years"].items():
            out.append(f"  re-validate every {years:.1f} years to stay within {tol}")
    return "\n".join(out)


def build(cache: Path, specs: Path, *, releases: tuple[str, ...] = RELEASES) -> dict[str, Any]:
    named, stops = frozen_names(specs)
    baseline_path, baseline_digest = fetch(BASELINE, cache)
    print(f"baseline {BASELINE}", flush=True)
    baseline = decay.Baseline.of(decay.Release.from_zip(baseline_path, BASELINE))

    points: list[dict[str, Any]] = []
    digests: dict[str, str] = {BASELINE: baseline_digest}
    for date in releases:
        path, digest = fetch(date, cache)
        digests[date] = digest
        release = decay.Release.from_zip(path, date)
        m = decay.measure(release, baseline, named=named, realms=agreement.ICTV_REALMS)
        points.append(m.to_dict())
        print(
            f"  {date}: {m.viral_taxa:,} viral, {m.reach:,} named "
            f"({(m.reach_share or 0):.4f}), {len(m.unreachable_names)} names unreachable",
            flush=True,
        )
        del release

    return {
        "task": TASK,
        "design_ref": "§A9",
        "decision": "D-201",
        "baseline": BASELINE,
        "frozen_names": {k: sorted(v) for k, v in named.items()},
        "stop_taxa": stops,
        "computed_rule": {
            "what": "descent from one of the ICTV realms, as the release itself names them",
            "why": (
                "the contrast §A9 asks for: an enumeration fixed in 2024 prose against a "
                "question each release answers for itself"
            ),
            "realms": list(agreement.ICTV_REALMS),
        },
        "not_measured_here": [
            "Whether a taxon is eukaryote-infecting. §A9's 'in scope by the policy's stated "
            "intent' means that, and NCBI carries no host, so the replay measures what the "
            "names reach against what the taxonomy holds (D-201).",
            "How much sequence each unnamed taxon carries. Counts are of taxa.",
        ],
        "releases": points,
        "revalidation": intervals(points),
        "digests": digests,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--cache", type=Path, required=True, help="where the dated dumps live")
    ap.add_argument("--specs", type=Path, default=Path("policies/specs"))
    ap.add_argument("--outdir", type=Path, default=Path("artifacts/a9-1"))
    ap.add_argument("--releases", nargs="*", help="override the pinned release list")
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args(argv)

    args.outdir.mkdir(parents=True, exist_ok=True)
    chosen = tuple(args.releases) if args.releases else RELEASES
    try:
        with repro.run(
            TASK,
            seed=None,  # a replay over pinned dumps: nothing here is random
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name="run-decay.json",
            durable=objectstore.durable_results("a9-1"),
        ) as manifest:
            manifest.parameter("decision", "D-201")
            manifest.parameter("baseline", BASELINE)
            manifest.parameter("releases", list(chosen))
            manifest.parameter("tolerances", list(TOLERANCES))
            doc = build(args.cache, args.specs, releases=chosen)
            (args.outdir / "decay.json").write_text(
                json.dumps(doc, indent=2, sort_keys=True) + "\n"
            )
            (args.outdir / "decay.md").write_text(summarise(doc) + "\n")
            manifest.output_file(args.outdir / "decay.json", role="decay")
            manifest.output_file(args.outdir / "decay.md", role="summary")
    except repro.ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print("\n" + summarise(doc), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

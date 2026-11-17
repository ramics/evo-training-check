#!/usr/bin/env python3
"""Build the hazard family set by database cross-reference — `metrics/costcurve.md` §3.

    pixi run -e dev python tools/hazard_family_set.py --outdir artifacts/c5-1

**Nothing here reads a protein family's name.** That is the whole point of the tool. The
project already has a name-based instrument — `tools/denylist_named_families.py`, which asks
whether a Pfam identifier or description *refers to* a denylisted group — and D-261 established
that it over-counts: 81 of the 82 detected records surviving into Evo 2's training data reached
a denylisted group through `matched_on: identifier`, on families whose own Pfam descriptions say
"protein-**like**" and "VLTF3 **like**". A name axis counts vocabulary. This tool counts
biology, by the one direction `metrics/costcurve.md` §3 permits:

    denylisted taxon -> reviewed UniProtKB entry -> Pfam cross-reference

so a family is nominated because a curator placed a real protein of a denylisted taxon in it,
never because its name sounds like one. The two instruments are independent by construction —
different inputs, no shared code, no shared matching rule — and where they disagree the
disagreement is the result.

**Taxa resolve by taxid, never by name.** The previous build of this stratum matched taxon
names, and two of the nineteen families silently returned zero because the taxonomy had been
restructured underneath them: ICTV elevated *Reoviridae* to the order *Reovirales* and renamed
*Herpesviridae* to *Orthoherpesviridae*. 2,904 reviewed entries were dropped with no error.
D-137 forbids exactly this for a published list, so the mapping is curated per taxon in
`policies/specs/hazard-virus-taxa-evo1.json` and this tool only *checks* it:

* every curated `taxid_pinned` must carry the scientific name and rank the spec records, in
  the pinned taxonomy — a curated taxid that has drifted fails the run;
* the spec must cover exactly the taxa the published rules name, read from
  `policies/specs/evo1-literal.yaml` rather than retyped;
* **a taxon whose query returns no reviewed entries fails the run** unless the spec curates it
  as a genuine zero. A silent zero is the failure this mapping exists to prevent, and a zero
  that is genuine looks identical to one that is a rename from the count alone.

**Both strata, kept apart.** V is built here; T is read from
`policies/specs/hazard-toxins-2024-06-01.json`, already curated per entry the same way. The
select-agent *organism* stratum S nominates no family by §3 and is not built. Every family
records which stratum and which taxa put it there.

**Two annotations travel with every family, and neither one removes it.** A nomination is a
published fact and this tool does not overturn it:

* `viral_selection` — whether the family is in this project's pinned viral selection of 1,719
  families (D-075, `profiles.select_viral_families`). A large-genome virus carries host-derived
  and host-mimicking proteins, so nominating by cross-reference admits actin, protein kinases
  and the immunoglobulin domain through *Poxviridae* and *Herpesvirales*. Those nominations are
  real and they are not hazard biology.
* `specificity` — the family's A4.5 background class (`viral_only`, `shared`, `unmeasurable`),
  measured against the reviewed section and InterPro independently. `shared` means the family
  also occurs in cellular proteomes, so a detection on it is not by itself viral material.
* `exclusivity` — of the family's reviewed entries, the fraction contributed by the taxa that
  nominated it. This is the measure that separates a family which *is* the listed biology from
  one that merely contains some of it: both are nominated, and only the first makes a detection
  on the family evidence about the listed taxon. A4.5's `reviewed_total` and this pass's
  nominating entries are both UniProtKB 2026_03, so the ratio is taken at one release.

They are columns, not a filter, and the artefact reports the set under both readings: the full
nomination, and the subset that is viral and family-specific. Narrowing a pre-registered set
after seeing its output would be the thing §C6's pre-registration exists to stop; recording the
measurement that *would* narrow it is not. Which reading the curve uses is the project owner's
call and is not made here.

**The UniProt release is recorded, not pinned**, as §3 says: the REST service serves the current
release only. Pfam, the taxonomy and the background table are all pinned.

Costs nothing but a minute of network: 31 paginated queries over reviewed entries, some 12,500
entries in all.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import objectstore, policyspec, repro, seeds

TASK = "C5.1"

ROOT = Path(__file__).resolve().parent.parent
CANONICAL_OUT = ROOT / "artifacts" / "c5-1"

#: The published list, and the two rules that name stratum V's taxa.
SPEC = ROOT / "policies" / "specs" / "evo1-literal.yaml"
RULES = {"remove-denylisted-families": "family", "remove-denylisted-orders": "order"}

#: The curated taxon mapping this tool validates but never decides.
TAXA_SPEC = ROOT / "policies" / "specs" / "hazard-virus-taxa-evo1.json"

#: Stratum T, curated per entry against the regulation (see its own `method` field).
TOXIN_SPEC = ROOT / "policies" / "specs" / "hazard-toxins-2024-06-01.json"

#: A4.5's background table — the specificity column and, since it enumerates the pinned viral
#: selection in full, the membership test for `viral_selection` too. A committed artefact of
#: this project, so this tool needs no Pfam download to annotate a nomination.
BACKGROUND = ROOT / "artifacts" / "a4-5" / "background-pfam-38.2.json"

UNIPROT_SEARCH = "https://rest.uniprot.org/uniprotkb/search"
UNIPROT_RELEASE = "https://rest.uniprot.org/uniprotkb/search?query=*&size=0"
PAGE = 500
UA = {"User-Agent": "amazebio-hazard-family-set (independent audit; contact via repo)"}


def durable_for(out: Path, *, allow_dirty: bool) -> str | None:
    """The durable destination, or None for a run that must not publish (D-193, D-224, D-265).

    Two conditions, and both are refusals rather than warnings. `--out` must be the canonical
    directory, because `repro.run`'s `durable` is derived from the task id and cannot see where
    the run was told to write. And `--allow-dirty` must not be set: that flag exists for local
    iteration, and combining it with the canonical directory publishes an artefact whose
    manifest names the last *commit* rather than the code that produced it — permanently, in a
    bucket with no `DeleteObject`. That happened on 2026-10-27 and the stray
    `by-commit/02b1a45.../` twin cannot be removed.
    """
    if allow_dirty:
        print(
            "not publishing: --allow-dirty is set, so this run's provenance would name a commit "
            "that does not contain the code that produced it",
            file=sys.stderr,
        )
        return None
    if out.resolve() == CANONICAL_OUT.resolve():
        return objectstore.durable_results("c5-1")
    print(
        f"not publishing: --out {out} is not {CANONICAL_OUT}, so this run is a probe",
        file=sys.stderr,
    )
    return None


def verify_taxdump(path: Path) -> None:
    """The pinned taxonomy, checked by digest before it validates anything.

    It is the thing that decides whether a curated taxid means what the curation says, so a
    different snapshot would move the validation rather than fail it.
    """
    pin = seeds.TAXDUMP_2023_04
    size = path.stat().st_size
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if size != pin.bytes or digest != pin.sha256:
        raise SystemExit(
            f"{path}: expected {pin.bytes} bytes sha256 {pin.sha256} "
            f"(amazebio.seeds.TAXDUMP_2023_04, dated {pin.date}), got {size} bytes "
            f"sha256 {digest}. Fetch it from {pin.url}."
        )


def published_taxa() -> dict[str, str]:
    """The taxa the published rules name, and the rank each is named at."""
    policy = policyspec.load_policy(SPEC)
    found: dict[str, str] = {}
    seen: set[str] = set()
    for rule in policy.rules:
        if rule.id not in RULES:
            continue
        seen.add(rule.id)
        want = RULES[rule.id]
        if rule.params.get("rank") != want:
            raise SystemExit(
                f"{SPEC}: {rule.id} names rank {rule.params.get('rank')!r}, not {want!r}. "
                "The stratum is built from the taxa these two rules name and cannot read "
                "another rank."
            )
        for name in rule.params["names"]:
            if name in found:
                raise SystemExit(f"{SPEC}: {name!r} is named by two rules; the list is a set.")
            found[name] = want
    missing = set(RULES) - seen
    if missing:
        raise SystemExit(f"{SPEC}: no rule(s) {sorted(missing)}. The taxa have no other source.")
    return found


def pinned_taxonomy(path: Path) -> tuple[dict[int, str], dict[int, str]]:
    """Scientific name and rank per taxid, from the pinned dump. The validator, not the chooser."""
    names: dict[int, str] = {}
    rank: dict[int, str] = {}
    with zipfile.ZipFile(path) as zf:
        with zf.open("nodes.dmp") as fh:
            for line in fh:
                f = [c.strip() for c in line.decode().split("\t|")]
                rank[int(f[0])] = f[2]
        with zf.open("names.dmp") as fh:
            for line in fh:
                f = [c.strip() for c in line.decode("utf-8", "replace").split("\t|")]
                if len(f) > 3 and f[3] == "scientific name":
                    names[int(f[0])] = f[1]
    return names, rank


def load_taxa_spec(
    published: dict[str, str], names: dict[int, str], rank: dict[int, str]
) -> list[dict[str, Any]]:
    """The curated mapping, checked against the published list and the pinned taxonomy."""
    payload = json.loads(TAXA_SPEC.read_text())
    entries = payload["entries"]
    curated = {e["entry"] for e in entries}
    if curated != set(published):
        raise SystemExit(
            f"{TAXA_SPEC}: covers {len(curated)} taxa, the published rules name "
            f"{len(published)}. Missing {sorted(set(published) - curated)}; "
            f"extra {sorted(curated - set(published))}. Every named taxon needs a curated "
            "taxid and nothing may be mapped that the list does not name."
        )
    for e in entries:
        if e["published_rank"] != published[e["entry"]]:
            raise SystemExit(
                f"{TAXA_SPEC}: {e['entry']} records published_rank {e['published_rank']!r}, "
                f"but the spec names it at rank {published[e['entry']]!r}."
            )
        tid = e["taxid_pinned"]
        if names.get(tid) != e["pinned_name"] or rank.get(tid) != e["pinned_rank"]:
            raise SystemExit(
                f"{TAXA_SPEC}: {e['entry']} curates taxid {tid}, recorded as "
                f"{e['pinned_name']!r} at rank {e['pinned_rank']!r}, but the pinned taxonomy "
                f"has {names.get(tid)!r} at rank {rank.get(tid)!r}. A curated taxid that has "
                "drifted from what the curation claims is the D-137 failure, so this refuses."
            )
    return entries


def get(url: str) -> tuple[bytes, dict[str, str]]:
    """Fetch, retrying. Header keys come back lower-cased, because HTTP's are case-insensitive
    and a plain `dict(r.headers)` is not — reading `x-total-results` off one spelling while the
    service sends another turns the truncation guard into a guard that always fires."""
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read(), {k.lower(): v for k, v in r.headers.items()}
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 5:
                raise SystemExit(f"{url}: {exc}") from exc
    raise AssertionError("unreachable")


def uniprot_release() -> dict[str, str]:
    """The release the service is serving, recorded because §3 cannot pin it."""
    _, headers = get(UNIPROT_RELEASE)
    return {
        "release": headers.get("x-uniprot-release", "unrecorded"),
        "release_date": headers.get("x-uniprot-release-date", "unrecorded"),
        "api": "https://rest.uniprot.org/uniprotkb/search",
        "pinned": False,
        "why_not_pinned": (
            "The REST service serves the current release only (metrics/costcurve.md §3). The "
            "release is recorded so a reader sees the gap rather than inferring there is none."
        ),
    }


def reviewed_entries(taxid: int) -> tuple[list[dict[str, Any]], int]:
    """Reviewed entries under `taxid`, with their Pfam cross-references. Lineage-inclusive.

    `taxonomy_id` is the lineage-inclusive field, which is why descent needs no walk here and
    why the curated taxid is the only thing that has to be right.
    """
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    total: int | None = None
    while True:
        params = {
            "query": f"taxonomy_id:{taxid} AND reviewed:true",
            "fields": "accession,xref_pfam,organism_id,protein_name",
            "format": "tsv",
            "size": str(PAGE),
        }
        if cursor:
            params["cursor"] = cursor
        body, headers = get(f"{UNIPROT_SEARCH}?{urllib.parse.urlencode(params)}")
        if total is None:
            total = int(headers.get("x-total-results", "0"))
        lines = body.decode("utf-8").splitlines()
        for line in lines[1:]:
            f = line.split("\t")
            if len(f) < 3:
                continue
            fams = [x for x in f[1].strip().strip(";").split(";") if x]
            out.append({"accession": f[0], "families": fams, "organism_id": f[2]})
        link = headers.get("link", "")
        cursor = None
        if 'rel="next"' in link:
            url = link[link.index("<") + 1 : link.index(">")]
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            cursor = qs.get("cursor", [None])[0]
        if not cursor:
            break
    return out, (total or 0)


def build_v(
    entries: list[dict[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, set[str]], list[dict[str, Any]]]:
    """Stratum V: family -> nominating taxa, family -> nominating accessions, per-taxon audit.

    The accessions are kept as a set rather than counted per taxon because the published list
    names overlapping ranks — `Picornaviridae` sits inside `Picornavirales`, and seven of the
    twelve orders contain a named family — so summing per-taxon counts would count the same
    reviewed entry twice and make a family look more exclusively hazardous than it is.
    """
    nominated: dict[str, set[str]] = defaultdict(set)
    accessions: dict[str, set[str]] = defaultdict(set)
    audit: list[dict[str, Any]] = []
    for e in entries:
        tid = e.get("taxid_query", e["taxid_pinned"])
        rows, total = reviewed_entries(tid)
        if len(rows) != total:
            raise SystemExit(
                f"{e['entry']}: the service reported {total} reviewed entries and the pass read "
                f"{len(rows)}. A truncated read nominates fewer families and raises no error, "
                "which is the direction that flatters the safeguard, so this refuses."
            )
        fams = {f for r in rows for f in r["families"]}
        if total == 0 and not e.get("expect_zero"):
            raise SystemExit(
                f"{e['entry']}: taxid {tid} has no reviewed UniProtKB entries, and the curated "
                "mapping does not record it as a genuine zero. This is the failure the mapping "
                "exists to prevent: a taxon restructured since the pinned taxonomy returns "
                "nothing and nominates nothing, silently. Either curate `taxid_query` to the "
                "node that now holds the entries, or record `expect_zero` with the evidence "
                "that the zero is genuine."
            )
        for f in fams:
            nominated[f].add(e["entry"])
        for r in rows:
            for f in r["families"]:
                accessions[f].add(r["accession"])
        audit.append(
            {
                "entry": e["entry"],
                "published_rank": e["published_rank"],
                "taxid_pinned": e["taxid_pinned"],
                "taxid_query": tid,
                "rename": e.get("rename"),
                "expect_zero": bool(e.get("expect_zero", False)),
                "reviewed_entries": total,
                "entries_with_pfam": sum(1 for r in rows if r["families"]),
                "families_nominated": len(fams),
            }
        )
    return nominated, accessions, audit


def build_t() -> tuple[dict[str, set[str]], dict[str, Any]]:
    """Stratum T, from the committed per-entry curation. Not rebuilt here."""
    payload = json.loads(TOXIN_SPEC.read_text())
    nominated: dict[str, set[str]] = defaultdict(set)
    for e in payload["entries"]:
        for f in e.get("families", []):
            nominated[f].add(e["entry"])
    return nominated, {
        "spec": str(TOXIN_SPEC.relative_to(ROOT)),
        "list_as_of": payload["list_as_of"],
        "uniprot_release": payload["uniprot_release"],
        "entries": len(payload["entries"]),
        "entries_nominating": sum(1 for e in payload["entries"] if e.get("nominates")),
        "families": len(nominated),
        "flagged": payload.get("flagged", []),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default=str(CANONICAL_OUT))
    ap.add_argument(
        "--taxdump",
        default=str(ROOT / "data" / "taxdmp_2023-04-01.zip"),
        help="the pinned taxonomy that validates the curated taxids",
    )
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args()

    out = Path(args.outdir)
    durable = durable_for(out, allow_dirty=args.allow_dirty)

    with repro.run(
        TASK,
        outdir=out,
        allow_dirty=args.allow_dirty,
        durable=durable,
        durable_exempt=(
            None
            if durable
            else "not the deliverable: a probe directory, or a dirty tree under --allow-dirty"
        ),
    ) as m:
        m.note(
            "The hazard family set, stratum V built by cross-reference from curated taxids and "
            "stratum T read from its committed curation. No protein family name is read."
        )
        taxdump = m.input_file(args.taxdump, role="pinned-taxonomy")
        verify_taxdump(taxdump)
        m.input_file(SPEC, role="published-list")
        m.input_file(TAXA_SPEC, role="curated-taxa")
        m.input_file(TOXIN_SPEC, role="curated-toxins")
        background = json.loads(m.input_file(BACKGROUND, role="specificity").read_text())

        published = published_taxa()
        names, rank = pinned_taxonomy(taxdump)
        entries = load_taxa_spec(published, names, rank)

        release = uniprot_release()
        for k, v in release.items():
            m.parameter(f"uniprot_{k}", v)

        v_nom, v_acc, v_audit = build_v(entries)
        t_nom, t_meta = build_t()

        selection = {f["accession"]: f for f in background["per_family"]}

        families: list[dict[str, Any]] = []
        for acc in sorted(set(v_nom) | set(t_nom)):
            meta = selection.get(acc)
            strata = [s for s, n in (("V", v_nom), ("T", t_nom)) if acc in n]
            nominating = len(v_acc.get(acc, ()))
            total = meta["reviewed_total"] if meta else None
            families.append(
                {
                    "accession": acc,
                    "name": meta["name"] if meta else None,
                    "description": meta["description"] if meta else None,
                    "strata": strata,
                    "nominated_by_taxa": sorted(v_nom.get(acc, ())),
                    "nominated_by_toxin_entries": sorted(t_nom.get(acc, ())),
                    "viral_selection": meta is not None,
                    "specificity": meta["class"] if meta else None,
                    "reviewed_total": total,
                    "reviewed_non_viral": meta["reviewed_non_viral"] if meta else None,
                    "nominating_entries": nominating,
                    # Exclusivity is a property of the *taxon* nomination, so a family that
                    # only stratum T nominates has none — not a zero, which would read as
                    # "no part of this family is listed biology" about a family a regulation
                    # names by protein. `None` where there is nothing to measure.
                    "exclusivity": (
                        round(nominating / total, 4) if (acc in v_nom and total) else None
                    ),
                }
            )

        viral_specific = [
            f for f in families if f["viral_selection"] and f["specificity"] == "viral_only"
        ]
        summary = {
            "families_nominated": len(families),
            "stratum_v": len(v_nom),
            "stratum_t": len(t_nom),
            "in_both": len(set(v_nom) & set(t_nom)),
            "in_viral_selection": sum(1 for f in families if f["viral_selection"]),
            "outside_viral_selection": sum(1 for f in families if not f["viral_selection"]),
            "specificity": {
                c: sum(1 for f in families if f["specificity"] == c)
                for c in ("viral_only", "shared", "unmeasurable", None)
            },
            "viral_and_family_specific": len(viral_specific),
            "exclusive_to_listed_taxa": sum(1 for f in families if (f["exclusivity"] or 0) >= 1.0),
            "exclusivity_unmeasurable": sum(1 for f in families if f["exclusivity"] is None),
            "reviewed_entries_read": sum(a["reviewed_entries"] for a in v_audit),
            "taxa_renamed": sum(1 for a in v_audit if a["rename"]),
            "taxa_curated_zero": sum(1 for a in v_audit if a["expect_zero"]),
        }

        payload = {
            "task": TASK,
            "design_ref": "metrics/costcurve.md §3, DESIGN.md §C5",
            "question": (
                "Which Pfam families does a published hazard list nominate, by database "
                "cross-reference from the taxa and proteins it names?"
            ),
            "method": (
                "denylisted taxon -> reviewed UniProtKB entry -> Pfam cross-reference, in that "
                "direction only. No family name is read. Taxa resolve by curated taxid, "
                "validated against the pinned taxonomy; an uncurated empty taxon refuses."
            ),
            "independent_of": (
                "tools/denylist_named_families.py, which matches Pfam identifiers and "
                "descriptions against the same group list. No input and no matching rule is "
                "shared. D-261 is why the second instrument exists."
            ),
            "does_not_claim": [
                "That a nominated family is dangerous. A family is nominated because a reviewed "
                "entry of a listed taxon cross-references it, which for a large-genome virus "
                "includes host-derived and host-mimicking families.",
                "That the annotations narrow the set. `viral_selection` and `specificity` are "
                "columns; the set is reported under both readings and the choice is the "
                "project owner's.",
                "Anything about stratum S. A regulation naming an organism nominates no family "
                "(metrics/costcurve.md §3) and S is not built here.",
            ],
            "uniprot": release,
            "taxonomy": {
                "pin": "taxdmp_2023-04-01.zip",
                "sha256": json.loads(TAXA_SPEC.read_text())["taxonomy_sha256"],
            },
            "background_source": background.get("background_source"),
            "summary": summary,
            "stratum_v_per_taxon": v_audit,
            "stratum_t": t_meta,
            "per_family": families,
        }

        jp = out / "hazard-family-set.json"
        jp.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
        m.output_file(jp, role="family-set")

        tp = out / "hazard-family-set.tsv"
        cols = (
            "accession",
            "name",
            "strata",
            "viral_selection",
            "specificity",
            "reviewed_total",
            "reviewed_non_viral",
            "nominating_entries",
            "exclusivity",
            "nominated_by_taxa",
            "nominated_by_toxin_entries",
        )

        def cell(value: Any) -> str:
            if isinstance(value, list):
                return "|".join(value)
            return "" if value is None else str(value)

        with tp.open("w") as fh:
            fh.write("\t".join(cols) + "\n")
            for f in families:
                fh.write("\t".join(cell(f[c]) for c in cols) + "\n")
        m.output_file(tp, role="family-set-tsv")

        print(json.dumps(summary, indent=2))
        print(f"wrote {jp}")
        print(f"wrote {tp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

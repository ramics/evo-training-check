#!/usr/bin/env python3
"""Per-region match statistics for a named record set and a named profile set — task A7.5.

    pixi run -e dev python tools/extract_matched_regions.py \
        --records  /mnt/project-files/hazard-check/denylisted-label-records.tsv \
        --profiles /mnt/project-files/hazard-check/denylist-named-families.tsv

A2.1's tables answer which families sit on which records. This answers the level below, for a
handful of records somebody has already named: per matched region, the bit score, the profile's
own curated threshold, the region's percent identity to the model consensus, and how much of the
model the region covers.

Three of those four exist inside A2.1's search and are dropped at the artefact boundary (D-195,
D-103: no sequence, and the per-hit rows carry family, record, score, threshold, route). The
fourth is computed nowhere else in this project. So this is a re-read of named records rather
than a query against a stored result — the shape `tools/place_detections.py` established for
A3.4, and the reason it is an instrument rather than a finding.

**It chooses nothing.** The record list and the profile list are inputs; whoever asks the
question owns the selection rule. The thresholds are the registry's own curated cutoffs and
there is no flag to pass another. The depth pre-registration (D-099) is untouched because
nothing new is sampled: the records are named.

**It reports alignment statistics and nothing else.** Identity to a model consensus is identity
to a summary of a family's model, not to any sequence that exists and not to any member of the
family; the definition travels in the output (see `amazebio.profilesearch.consensus_identity`).

The output carries record identifiers and model coordinates, which are internal under X3.1, and
no residues of any kind (D-103).

**One opt-in, gated side channel: `--fasta-out <path>`.** The project owner uses it to BLAST the
called protein under each row independently as a cross-check on the identity-to-consensus
column; D-254 is the carve-out and this is the only tool that carries it. Three code gates make
the opt-in safe to leave in the tool: the path refuses to resolve anywhere inside the repository
(so `artifacts/`, `data/`, `OUTDIR` and the repo root are all off-limits by name — no override);
the FASTA is written by a direct file write, never through `manifest.output_file`, so
`repro.run`'s durable upload never sees it; and the flag's presence prints a one-line notice
naming its destination. D-103 is otherwise unchanged — the three published outputs (TSV, JSON,
Markdown) carry accessions, scores, coordinates, counts and lineage tags only.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from amazebio import corpora, objectstore, profilesearch, progress, repro
from amazebio.profiles import MIN_MODEL_COVERAGE, registry
from amazebio.seqstream import iter_fasta_selected

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data" / "profiles"
OUTDIR = REPO / "artifacts" / "a7-5"

TASK = "A7.5"

#: The component this reads. Evo 2's viral component is the one that carries a record accession
#: at all: Evo 1's released records have none, so a question asked about named records cannot be
#: asked of it (A1.4's finding, recorded on the source's own evidence declaration).
COMPONENT = "IMG/VR"
RELEASE = "opengenome2"

#: Records gene-called and searched at a time, as `tools/detect_profiles.py` chunks: peak memory
#: is bounded by the chunk and each chunk's line is a real heartbeat. A named set is usually one
#: chunk; the chunking is here because the record list is arbitrary.
CHUNK_RECORDS = 2_000


class Refusal(SystemExit):
    """Exit with a reason. Every refusal in this tool is a disagreement between two inputs."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"refused: {reason}")


def read_first_column(path: Path, *, header_names: tuple[str, ...]) -> list[str]:
    """One identifier per line, or the first column of a TSV; order preserved, duplicates dropped.

    A leading header row whose first field is one of `header_names` is skipped, and so are blank
    lines and `#` comments, so the files under `/mnt/project-files/hazard-check/` are passed as
    they stand rather than cut down first — a cut-down copy is a second thing to keep in step.
    """
    out: list[str] = []
    seen: set[str] = set()
    for n, raw in enumerate(path.read_text().splitlines()):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        token = line.split("\t")[0].strip()
        if not token:
            continue
        if n == 0 and token.lower() in header_names:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    if not out:
        raise Refusal(f"{path}: no identifiers read")
    return out


def resolve_source(client: Any) -> Any:
    """The staged source for the component, with its length checked against the pin.

    Resolved through `corpora.sources_for` rather than by a literal key, so the key lives in one
    place. The length check is `tools/detect_profiles.py`'s: a staged object of a different
    length is a different corpus, and nothing measured on it may be reported beside A2.1's
    numbers.
    """
    candidates = [s for s in corpora.sources_for(RELEASE) if s.component == COMPONENT]
    if len(candidates) != 1:
        raise Refusal(
            f"{len(candidates)} staged sources for {COMPONENT} in {RELEASE}, expected exactly "
            "one; the component this tool reads has to be unambiguous"
        )
    source = candidates[0]
    live = int(client.head_object(Bucket=corpora.BUCKET, Key=source.key)["ContentLength"])
    if source.bytes and live != source.bytes:
        raise Refusal(
            f"{source.key}: staged object is {live} bytes, the pin says {source.bytes}. "
            "Re-verify before trusting any figure from it."
        )
    return source


def open_records(
    client: Any, source: Any, ids: list[str]
) -> tuple[Iterator[Any], progress.Beating]:
    """The named records with sequence, and the meter measuring the pass that finds them.

    Object storage offers no index into a gzip stream, so the cost is one sequential pass and
    the records are found on the way past. The object is read **through**, rather than stopping
    at the last requested accession, because the entry counts have to be counts — see the
    comment on the call below.

    The meter is returned rather than kept private for two reasons. It reports progress on a
    byte interval while the pass runs — the records are sparse, a few hundred accessions in
    11.22 GB, so a line printed when one is *found* says nothing about the long stretches between
    them, which is the silence D-192 is about. And the bytes it counts are what the run records,
    so how much was read is a measurement rather than a derivation.

    It wraps the compressed reader, because the object's declared length is the compressed one
    and a share of an unknown decompressed total would be a fraction with an invented
    denominator.
    """
    obj = corpora.RangedObject(
        client,
        bucket=corpora.BUCKET,
        key=source.key,
        size=source.bytes,
        on_retry=lambda attempt, pos, exc: print(
            f"    reconnect {attempt} at byte {pos:,}: {exc}", file=sys.stderr
        ),
    )
    meter = progress.beating(obj.buffered(), total=source.bytes, label=source.key)
    reader: Any = meter
    if source.gzipped:
        from amazebio.uniref import GunzipStream

        reader = GunzipStream(reader)
    return (
        iter_fasta_selected(
            reader,
            component=source.component,
            ids=ids,
            # Read the object through. `iter_fasta_selected` can stop as soon as every requested
            # accession has been seen once, and that was this tool's design until the `entry`
            # column arrived: the stop was defensible precisely because it changed nothing a
            # caller could observe. It no longer is. An accession repeats in this object with
            # different residues under it, so a pass that stops at the first sighting of the
            # last accession reports `entries_read`, `records_repeated` and
            # `entries_per_record_max` over however much of the object it happened to reach —
            # counts that look like a census and are truncated at an arbitrary byte. The saving
            # was never predictable from the identifiers; a true count is worth more.
            stop_when_complete=False,
        ),
        meter,
    )


def resolve_profiles(accessions: list[str]) -> tuple[Any, Any, dict[str, str]]:
    """`(registry, view, name -> accession)` for the requested accessions, or a refusal.

    An accession outside the pinned release's viral selection is a refusal naming the offenders,
    never a skip: it means this caller's list and the audit's family universe (D-075) disagree
    about what families exist, and a silently shortened profile list would read as "no match"
    for every family dropped.
    """
    reg = registry("pfam")
    view = profilesearch.family_universe(reg, DATA)
    missing = [a for a in accessions if a not in view.universe]
    if missing:
        raise Refusal(
            f"{len(missing)} requested accession(s) are not in the pinned release's viral "
            f"selection (first: {missing[:5]}). The request and the family universe disagree "
            "about what families exist; a shortened profile list would read as 'no match'."
        )
    name_of = {a: view.universe[a] for a in accessions}
    accession_of = {name: accession for accession, name in name_of.items()}
    return reg, view, accession_of


def search_chunk(
    records: list[Any],
    *,
    reg: Any,
    view: Any,
    restrict_to: set[str],
    cpus: int,
    capture_sequences: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, str]]:
    """Call genes on one chunk of records and search the restricted model set over them.

    When `capture_sequences` is on, the called protein underlying each **accepted hit** is
    recovered as a text string, keyed by its full protein name (``f"{record_id}#{entry}|
    gene{i}"``). This is the only path by which residues leave the pass, and it is wired to the
    `--fasta-out` flag — the invariant is in `write_fasta` and its gate (D-254); the capture
    itself is restricted to proteins that produced a hit, so a chunk's non-matching residues
    stay in memory and go nowhere.
    """
    proteins, stats = profilesearch.call_genes(records)
    if not proteins:
        return [], stats, {}
    rows = profilesearch.search(
        reg,
        proteins,
        restrict_to=restrict_to,
        hmm_file=profilesearch.hmm_path(reg, DATA),
        cpus=cpus,
        with_identity=True,
    )
    sequences: dict[str, str] = {}
    if capture_sequences and rows:
        hit_names = {f"{row['record_id']}|{row['gene']}" for row in rows}
        for protein in proteins:
            raw = protein.name
            name = raw.decode() if isinstance(raw, bytes | bytearray) else str(raw)
            if name in hit_names:
                # `textize()` returns the same residues that were digitised; no network, no
                # file read. The protein is already in memory for the search above.
                sequences[name] = str(protein.textize().sequence)
    return rows, stats, sequences


#: The columns of the table, in order. The six the question asks for are `accession`,
#: `record_id`, `score`, `threshold`, `identity` and `model_coverage`; the rest is the context
#: that makes each of them checkable.
COLUMNS = (
    "accession",
    "profile",
    "record_id",
    # Which occurrence of that accession in the staged object this region sits on. The released
    # component repeats accessions and the repeats are not identical, so `record_id` alone does
    # not identify an entry and a table keyed on it fans out. See `ENTRY_NOTE`.
    "entry",
    "gene",
    "score",
    "threshold",
    "identity",
    "model_coverage",
    "model_length",
    "hmm_from",
    "hmm_to",
    "target_from",
    "target_to",
)

#: What the `entry` column is for, carried into the output rather than left in a task file.
ENTRY_NOTE = (
    "The released component repeats record identifiers, so an accession does not identify an "
    "entry: a pass reads more FASTA entries than it has distinct requested accessions, and the "
    "repeats are not identical — measured 2026-10-22, two entries sharing one accession carried "
    "different proteins at the same gene index, scoring 38.0 and 34.4 against the same model. "
    "`entry` is the accession's 1-based order of appearance in the object, so the key that is "
    "unique is (`record_id`, `entry`, `accession`, `gene`); joining on `record_id` alone fans "
    "out. `entries_read` against `records_found` is how far apart the two are in this pass. "
    "A7.3 measures repeated accessions in this release as a finding of its own; this column is "
    "what keeps this table checkable in their presence."
)

IDENTITY_DEFINITION = (
    "identity is the fraction of the matched region's match-state columns at which the called "
    "protein's residue is the model consensus residue, case-folded; columns HMMER writes as an "
    "insert relative to the model are excluded, and a gap on the protein side counts in the "
    "denominator only. It is identity to a consensus string, which summarises a family's model: "
    "not identity to any sequence that exists, not identity to any member of the family, and "
    "not a measure of resemblance to any named organism. The detection claim is the bit score "
    "against the curated threshold."
)


def build(
    *,
    client: Any,
    record_ids: list[str],
    accessions: list[str],
    cpus: int,
    limit_records: int | None,
    fasta_out: Path | None = None,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Build the per-region table and, when `fasta_out` is set, its FASTA companion.

    Returns ``(doc, fasta_entries)``. The FASTA entries are a list of ``(defline, sequence)``
    pairs the caller writes to a path a gate has already checked; this function neither opens
    nor touches that path, so a `doc` carrying residues cannot be reconstructed from this
    return value. When `fasta_out` is None the second element is an empty list.
    """
    source = resolve_source(client)
    reg, view, accession_of = resolve_profiles(accessions)
    restrict_to = {view.universe[a] for a in accessions}
    thresholds = view.thresholds

    wanted = record_ids[:limit_records] if limit_records else record_ids
    print(
        f"{len(wanted):,} records requested, {len(restrict_to):,} profiles, "
        f"streaming {source.key} ({source.bytes:,} bytes)",
        flush=True,
    )

    started = time.time()
    rows: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    seen: list[str] = []
    chunk: list[Any] = []
    captured: dict[str, str] = {}  # protein-name -> residues, hit-only; D-254

    def flush(batch: list[Any]) -> None:
        if not batch:
            return
        found, stats, sequences = search_chunk(
            batch,
            reg=reg,
            view=view,
            restrict_to=restrict_to,
            cpus=cpus,
            capture_sequences=fasta_out is not None,
        )
        for key, value in stats.items():
            totals[key] += value
        rows.extend(found)
        captured.update(sequences)
        print(
            f"  {len(seen):,} entries read for {len(set(seen)):,}/{len(wanted):,} requested "
            f"records, {stats.get('genes', 0):,} genes searched, {len(rows):,} regions so far, "
            f"{time.time() - started:.0f}s",
            flush=True,
        )

    records, meter = open_records(client, source, wanted)
    occurrences: Counter[str] = Counter()
    for record in records:
        # The accession is not unique in this object, so each entry is tagged with its order of
        # appearance before its genes are called. Tagging here rather than in
        # `profilesearch.call_genes` keeps A2.1's protein naming — and therefore its published
        # rows — exactly as they were.
        occurrences[record.id] += 1
        seen.append(record.id)
        tagged = dataclasses.replace(
            record,
            record=dataclasses.replace(record.record, id=f"{record.id}#{occurrences[record.id]}"),
        )
        chunk.append(tagged)
        if len(chunk) >= CHUNK_RECORDS:
            flush(chunk)
            chunk = []
    flush(chunk)

    missing = [r for r in wanted if r not in set(seen)]
    # Paired with the raw protein name (``record_id#entry|gene``) so a sort of the output rows
    # does not break the correspondence with the captured residues. The sequence lives in
    # `captured`, keyed by that name; `table` is what the JSON serialises, and nothing in
    # `table` carries a residue.
    pairs: list[tuple[dict[str, Any], str]] = []
    for row in rows:
        accession = accession_of.get(row["profile"])
        if accession is None:  # pragma: no cover - restrict_to makes this unreachable
            raise Refusal(f"hit under profile {row['profile']}, which was not requested")
        identity = row.get("identity")
        raw_name = f"{row['record_id']}|{row['gene']}"
        record_id, _, entry = row["record_id"].partition("#")
        pairs.append(
            (
                {
                    "accession": accession,
                    "profile": row["profile"],
                    "record_id": record_id,
                    "entry": int(entry) if entry.isdigit() else 1,
                    "gene": row["gene"],
                    "score": round(float(row["score"]), 1),
                    "threshold": thresholds.get(row["profile"]),
                    "identity": None if identity is None else round(float(identity), 4),
                    "model_coverage": round(float(row["coverage"]), 4),
                    "model_length": row["model_length"],
                    "hmm_from": row.get("hmm_from"),
                    "hmm_to": row.get("hmm_to"),
                    "target_from": row.get("target_from"),
                    "target_to": row.get("target_to"),
                },
                raw_name,
            )
        )
    pairs.sort(key=lambda p: (p[0]["record_id"], p[0]["entry"], p[0]["accession"], p[0]["gene"]))
    table = [out for out, _ in pairs]

    fasta_entries: list[tuple[str, str]] = []
    if fasta_out is not None:
        for out, raw_name in pairs:
            sequence = captured.get(raw_name)
            if sequence is None:
                # Defensive: `capture_sequences` restricts to hit names on the same chunk, so
                # every pair has a sequence. Skipping rather than failing keeps a FASTA
                # usable if that invariant ever breaks; the row still lands in the TSV.
                continue
            fasta_entries.append((defline_for(out), sequence))

    doc = {
        "task": TASK,
        "design_ref": "§A2",
        "decisions": ["D-075", "D-076", "D-077", "D-103", "D-195", "D-216", "D-254"],
        "release": RELEASE,
        "component": COMPONENT,
        "source_key": source.key,
        "source_bytes": source.bytes,
        "registry": {"id": reg.id, "version": reg.version},
        "parameters": {
            "min_model_coverage": MIN_MODEL_COVERAGE,
            "thresholds": "the registry's own curated gathering cutoff, sequence half",
            "identity_definition": IDENTITY_DEFINITION,
            "selection": "records named by the caller; no sample, no band (D-099 untouched)",
            "read": (
                "the object is read through to its end rather than stopped at the last "
                "requested accession, so `entries_read`, `records_repeated` and "
                "`entries_per_record_max` are counts over the whole component and not over "
                "however much of it a stop happened to reach"
            ),
        },
        "records_requested": len(wanted),
        "records_found": len(set(seen)),
        # Entries, not records: see ENTRY_NOTE. Reporting `len(seen)` as records found is what
        # made the first run of this pass say "551 of 314 requested records found".
        "entries_read": len(seen),
        "records_repeated": sum(1 for n in occurrences.values() if n > 1),
        "entries_per_record_max": max(occurrences.values(), default=0),
        "entry_note": ENTRY_NOTE,
        "records_missing": missing,
        "records_without_genes": totals.get("records_without_genes", 0),
        "genes_called": totals.get("genes", 0),
        "residues_searched": totals.get("residues", 0),
        "profiles_requested": len(accessions),
        "profiles_searched": len(restrict_to),
        "regions": len(table),
        "records_with_a_region": len({r["record_id"] for r in table}),
        "accessions_with_a_region": len({r["accession"] for r in table}),
        "seconds": round(time.time() - started, 1),
        # Measured, not derived: the early stop ends the pass once every requested identifier
        # has been seen, and how much that saves cannot be predicted from the identifiers.
        "bytes_read": meter.bytes_read,
        "stopped_early": bool(source.bytes) and meter.bytes_read < int(source.bytes),
        "rows": table,
        "reading_this_table": (
            "One row is one matched region: one profile against one called gene, the "
            "best-covering included domain of that hit. `score` against `threshold` is the "
            "detection claim and the only claim; `identity` and `model_coverage` describe the "
            "shape of the match, both of them properties of that same region. "
            f"{IDENTITY_DEFINITION} A record in `records_missing` was requested and not found "
            "in the staged object, which is a disagreement between the request and the corpus "
            "rather than an absence of matches. A record present with no row either had no gene "
            "called or no requested profile scored above its curated threshold at "
            f"{MIN_MODEL_COVERAGE:.0%} model coverage; the two are distinguished by "
            "`records_without_genes`. No residues are carried in this table, in any of the "
            "three published outputs, or in the durable audit store (D-103). The one path by "
            "which residues can leave this pass is the opt-in `--fasta-out <path>` flag, "
            "whose destination the gate refuses to resolve anywhere inside the repo (D-254)."
        ),
    }
    return doc, fasta_entries


def defline_for(row: dict[str, Any]) -> str:
    """FASTA defline for one matched region, first token unique per hit.

    BLAST uses the first whitespace-delimited token as the query ID, so the row's
    `(record_id, entry, gene, accession)` is folded into it with pipes — a tuple that is
    already unique in the TSV (see `ENTRY_NOTE`), and that lets the BLAST output be joined
    back to the row that produced it. The rest of the defline carries the row's statistics
    verbatim, so a FASTA record is self-describing without the TSV at hand.
    """

    def _fmt(name: str) -> str:
        value = row.get(name)
        return "" if value is None else str(value)

    token = f"{row['record_id']}#{row['entry']}|{row['gene']}|{row['accession']}"
    fields = [
        f"profile={_fmt('profile')}",
        f"score={_fmt('score')}",
        f"threshold={_fmt('threshold')}",
        f"identity={_fmt('identity')}",
        f"model_coverage={_fmt('model_coverage')}",
        f"model_length={_fmt('model_length')}",
        f"hmm={_fmt('hmm_from')}-{_fmt('hmm_to')}",
        f"target={_fmt('target_from')}-{_fmt('target_to')}",
    ]
    return f"{token} " + " ".join(fields)


def write_fasta(path: Path, entries: list[tuple[str, str]], *, wrap: int = 60) -> None:
    """Write a FASTA to `path` with one record per matched region.

    No manifest involvement: this function writes directly to disk, so `repro.run`'s durable
    upload — which this tool uses for its three published outputs on the deliverable run —
    never sees it. The path has already been checked by `check_fasta_out_path`; writing it
    here would be too late to defend D-103, so the gate is at argument-parsing time.
    """
    out: list[str] = []
    for defline, sequence in entries:
        out.append(f">{defline}")
        for i in range(0, len(sequence), wrap):
            out.append(sequence[i : i + wrap])
    path.write_text("\n".join(out) + "\n" if out else "")


def check_fasta_out_path(path: Path, *, repo: Path = REPO) -> Path:
    """Refuse a `--fasta-out` that lands inside the repository (D-254).

    The residues this flag emits are a local-only sanity check: anywhere inside the repo
    tree is where a reviewer, a later task, or `repro.run`'s durable upload would read them,
    which is exactly what D-103 forbids. The gate is by resolved path, not by convention:
    `artifacts/`, `data/`, `OUTDIR` and the repo root are all off-limits by name, and there
    is no override — pass a path under your scratchpad, `/tmp/`, or `/mnt/project-files/...`
    instead.

    A pre-existing destination is also a refusal, so the flag never silently overwrites a
    FASTA from an earlier run; a stale file is the one the owner will mistake for the one
    this run just emitted.
    """
    resolved = path.expanduser().resolve()
    repo_resolved = repo.resolve()
    if resolved == repo_resolved or repo_resolved in resolved.parents:
        raise Refusal(
            f"--fasta-out {path} resolves to {resolved}, which is inside the repository "
            f"({repo_resolved}). The residues emission is local-only and must land outside "
            "the repo tree (D-254). Pass a path under your scratchpad, /tmp/, or "
            "/mnt/project-files/..."
        )
    if resolved.exists():
        if resolved.is_dir():
            raise Refusal(f"--fasta-out {path} is a directory; name a file")
        raise Refusal(
            f"--fasta-out {path} already exists; pick a fresh path. This tool does not "
            "replace residues deliberately — a stale FASTA is the one you will mistake for "
            "the one this run emitted."
        )
    return resolved


def summarise(doc: dict[str, Any]) -> str:
    lines = [
        f"A7.5 matched regions — {doc['component']}, {doc['release']}, "
        f"{doc['registry']['id']} {doc['registry']['version']}",
        "",
        f"{doc['records_found']:,} of {doc['records_requested']:,} requested records found"
        + (
            f", in {doc['entries_read']:,} FASTA entries — {doc['records_repeated']:,} "
            f"accessions appear more than once in the staged object (up to "
            f"{doc['entries_per_record_max']}), and the repeats are not identical"
            if doc.get("entries_read", 0) > doc.get("records_found", 0)
            else ""
        ),
        f"{doc['genes_called']:,} genes called, {doc['profiles_searched']:,} profiles searched",
        f"{doc['regions']:,} matched regions on {doc['records_with_a_region']:,} records "
        f"across {doc['accessions_with_a_region']:,} families",
    ]
    if doc["records_missing"]:
        lines.append(
            f"{len(doc['records_missing']):,} requested records are not in the staged object "
            f"(first: {doc['records_missing'][:5]})"
        )
    if doc["records_without_genes"]:
        lines.append(f"{doc['records_without_genes']:,} records had no gene called")
    if doc.get("bytes_read"):
        left = int(doc["source_bytes"]) - int(doc["bytes_read"])
        # The early stop fires after the last wanted record, so its saving is wherever that
        # record happens to sit. Reporting the remainder rather than the bare fact: 4.7 MB of
        # 11.22 GB unread is an early stop that bought nothing, and "stopped early" alone
        # invites the reader to think it did.
        lines.append(
            f"{doc['bytes_read'] / 1e9:.2f} of {doc['source_bytes'] / 1e9:.2f} GB read in "
            f"{doc['seconds'] / 60:.1f} min"
            + (
                f" — the early stop left {left / 1e6:.1f} MB unread "
                f"({left / int(doc['source_bytes']):.2%} of the object)"
                if doc.get("stopped_early")
                else " — the whole object"
            )
        )
    strongest = sorted(doc["rows"], key=lambda r: r["score"], reverse=True)[:5]
    if strongest:
        lines += [
            "",
            "strongest regions by bit score:",
            "  accession  score / threshold  identity  model coverage",
        ]
        for row in strongest:
            identity = "n/a" if row["identity"] is None else f"{row['identity']:.3f}"
            lines.append(
                f"  {row['accession']}  {row['score']:.1f} / {row['threshold']}  "
                f"{identity}  {row['model_coverage']:.3f}"
            )
    lines += ["", IDENTITY_DEFINITION]
    return "\n".join(lines)


def write_table(path: Path, rows: list[dict[str, Any]]) -> None:
    out = ["\t".join(COLUMNS)]
    for row in rows:
        out.append("\t".join("" if row[c] is None else str(row[c]) for c in COLUMNS))
    path.write_text("\n".join(out) + "\n")


def durable_for(out: Path, *, limit_records: int | None) -> str | None:
    """The durable prefix for this task, **or None for a run that is not its deliverable.**

    The prefix follows from the task id, which says nothing about where the run was told to
    write or how much of the record list it was told to read. Two incidents, both permanent in a
    bucket with no `DeleteObject`:

    - A rehearsal from a scratch directory published to the real results prefix, under the exact
      names the deliverable will use, because `repro.run`'s `durable` cannot see `--outdir`
      (D-193 in `detect_segmented.py`, then the same thing again in `detect_profiles.py`,
      D-224). So `--outdir` is the signal that separates a rehearsal from the deliverable:
      publish from the canonical `artifacts/a7-5` and from nowhere else.
    - A probe run with a record limit reached A2.6's census prefix on 2026-10-20 claiming to
      cover a whole band. A table over the first twenty records of a list is indistinguishable
      in the prefix from a table over all of it, and reads as "no match" for every record the
      limit cut. So `--limit-records` refuses to publish at all, which is what
      `opengenome_contigs.py`'s `--limit` does for the same reason.

    `preflight` is the other half of the write path and not a substitute for this one: it stops a
    *replacement*, and the first rehearsal to reach a clean prefix is not a replacement.
    """
    if limit_records is not None:
        return None
    if out.resolve() != OUTDIR.resolve():
        return None
    return objectstore.durable_results("a7-5")


def preflight(
    client: Any,
    *,
    paths: list[Path],
    durable: str | None,
    outdir: Path,
    replace: str | None,
) -> None:
    """Refuse, before anything is read, if an output already exists locally or durably.

    The results bucket has no `s3:DeleteObject` while `PutObject` on an existing key succeeds, so
    un-rewritable is a property of deletion there and not of the key (D-216; X1.7 is fixing it
    generally). `repro.run` already refuses to publish different bytes under the same *commit*,
    but that fires after the pass — forty minutes of reading too late to be the only guard — and
    cannot see a stable key published by a different commit. So the keys are checked first.

    The check is a HEAD and never a PUT. A4.5 left a six-byte write probe permanently under a
    results prefix; in a bucket that cannot delete, a probe is a commitment.
    """
    if replace:
        return
    local = [p for p in paths if p.exists()]
    if local:
        raise Refusal(
            f"{len(local)} output(s) already exist under {outdir} (first: {local[0].name}). "
            "Pass --replace-durable '<reason>' if replacing them is intended; the reason lands "
            "in the run manifest."
        )
    if not durable:
        return
    bucket, _, prefix = durable.removeprefix("s3://").partition("/")
    published: list[str] = []
    for path in paths:
        key = f"{prefix}/{path.name}" if prefix else path.name
        try:
            client.head_object(Bucket=bucket, Key=key)
        except Exception as exc:  # botocore raises ClientError; not imported here
            code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
            status = getattr(exc, "response", {}).get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
                continue
            raise
        published.append(f"s3://{bucket}/{key}")
    if published:
        raise Refusal(
            f"{len(published)} output key(s) are already published and this bucket cannot "
            f"delete what it replaces:\n  " + "\n  ".join(published) + "\nPass "
            "--replace-durable '<reason>' if replacing them is intended; the reason lands in "
            "the run manifest."
        )


def main(argv: list[str] | None = None, *, client: Any = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--records", type=Path, required=True, help="record ids, or a TSV")
    ap.add_argument("--profiles", type=Path, required=True, help="Pfam accessions, or a TSV")
    ap.add_argument("--outdir", type=Path, default=OUTDIR)
    ap.add_argument("--cpus", type=int, default=3)
    ap.add_argument("--limit-records", type=int, default=None, help="first N records; a probe")
    ap.add_argument("--replace-durable", default=None, help="why replacing a published output")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument(
        "--fasta-out",
        type=Path,
        default=None,
        help=(
            "write a FASTA of the called protein underlying each matched region to <path>, "
            "for independent local BLAST verification. The path must resolve outside the "
            "repository (D-254); the FASTA is not uploaded to the durable store and is "
            "never a manifest output. Off by default."
        ),
    )
    args = ap.parse_args(argv)

    # Gate the FASTA destination before anything is read, so a refusal costs nothing.
    fasta_out = check_fasta_out_path(args.fasta_out) if args.fasta_out else None

    record_ids = read_first_column(args.records, header_names=("record_id", "record", "id"))
    accessions = read_first_column(args.profiles, header_names=("accession", "profile", "id"))

    client = client or objectstore.client()
    stem = args.records.name.rsplit(".", 1)[0]
    base = f"regions-{stem}-pfam-38.2"
    args.outdir.mkdir(parents=True, exist_ok=True)
    outputs = [args.outdir / f"{base}.{ext}" for ext in ("tsv", "json", "md")]
    durable = durable_for(args.outdir, limit_records=args.limit_records)
    exempt = None
    if durable is None:
        exempt = (
            f"not the deliverable: --limit-records {args.limit_records}"
            if args.limit_records is not None
            else f"not the deliverable: --outdir {args.outdir} is not {OUTDIR}"
        )
        print(f"not publishing: {exempt}; this run writes locally only", flush=True)

    if fasta_out is not None:
        print(
            f"--fasta-out passed: residues of matched regions will be written to {fasta_out} "
            "(local only, outside the repo; not a manifest output; D-254)",
            flush=True,
        )

    try:
        preflight(
            client,
            paths=outputs,
            durable=durable,
            outdir=args.outdir,
            replace=args.replace_durable,
        )
        with repro.run(
            TASK,
            seed=None,  # the pass is deterministic: a named record set and pinned thresholds
            outdir=args.outdir,
            allow_dirty=args.allow_dirty,
            manifest_name=f"run-{base}.json",
            durable=durable,
            durable_exempt=exempt,
            replace_durable=args.replace_durable,
        ) as manifest:
            manifest.parameter("min_model_coverage", MIN_MODEL_COVERAGE)
            manifest.parameter("identity_definition", IDENTITY_DEFINITION)
            manifest.parameter("records_requested", len(record_ids))
            manifest.parameter("profiles_requested", len(accessions))
            manifest.parameter("limit_records", args.limit_records)
            # D-254: path only, never contents. The FASTA is deliberately not an
            # `output_file`, so `repro.run`'s durable upload cannot reach it.
            manifest.parameter("fasta_out", None if fasta_out is None else str(fasta_out))
            manifest.input_file(args.records, role="record ids")
            manifest.input_file(args.profiles, role="profile accessions")
            doc, fasta_entries = build(
                client=client,
                record_ids=record_ids,
                accessions=accessions,
                cpus=args.cpus,
                limit_records=args.limit_records,
                fasta_out=fasta_out,
            )
            write_table(outputs[0], doc["rows"])
            outputs[1].write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
            outputs[2].write_text(summarise(doc) + "\n")
            manifest.output_file(outputs[0], role="matched regions")
            manifest.output_file(outputs[1], role="matched regions, with parameters")
            manifest.output_file(outputs[2], role="summary")
            if fasta_out is not None:
                write_fasta(fasta_out, fasta_entries)
                print(f"wrote {len(fasta_entries):,} FASTA records to {fasta_out}", flush=True)
    except repro.ReproError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print("\n" + summarise(doc), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

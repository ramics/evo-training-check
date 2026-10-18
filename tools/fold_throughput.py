#!/usr/bin/env python3
"""Measure 3Di prediction throughput, on CPU and on GPU — A2.2's sizing pass.

A2.2's query side has no structures. The surviving corpora are nucleotide (Evo) and
sequence-only (the ESM3 proxy), so Foldseek's 3Di has to be *predicted* from sequence with
ProstT5, and D-163 measured that step at **18.58 core-hours per million residues on CPU —
173x the profile search it feeds**. At that rate a census of both releases is 458,800
core-hours and merely matching A2.1's sample depth is about seventy days of the session
container. So the question this tool answers is not "how fast is a GPU" in the abstract: it
is what depth A2.2 can honestly pre-register, and that number has to exist before any
threshold is chosen or any hit is looked at.

Three things about this measurement shape the code.

**The comparison must be within one machine.** A GPU figure from an instance divided by a CPU
figure from the session container is two machines, two memory systems and two foldseek
invocations, and the ratio would carry all of that. So this tool measures *both* devices on
whatever machine it runs on, over the identical protein set, and reports the ratio it
measured rather than one computed across runs. Running it in the container (CPU only) and on
a GPU instance (both) also reproduces D-163's container figure as a cross-check, which is the
cheapest available test that the two environments are measuring the same thing.

**A benchmark that does not resemble the real job is not evidence.** That is D-098, which
names this task: its own throughput estimate was wrong by a factor of a thousand because it
never left the fixed-cost regime. So the input here is real corpus sequence — records of Evo
1's viral component, read from the pinned staged object, with genes called by the same
Prodigal metagenomic mode D-077 pins — and the measurement is a *ladder* of sizes, because a
single point cannot show whether it is in the linear regime. The ladder's smaller rungs are
nested prefixes of its larger ones, so the per-residue costs are directly comparable.

**A GPU that is not there must not read as a speedup of one.** The packaged foldseek is
CUDA-capable (D-163 established that from `--gpu 1` reporting "No GPU devices found" rather
than "compiled without CUDA"), but a driverless AMI, a wrong instance type or a stale
container would all make the GPU invisible — and foldseek would then quietly do the work on
the CPU and return a perfectly plausible number. So the GPU is *proved present* before the
ladder runs, by `nvidia-smi` and by a one-sequence foldseek probe whose output is checked for
that exact refusal, and a run whose GPU cannot be proved records `gpu_available: false` and
measures nothing on it. Half an hour of CPU timings mislabelled as GPU timings would set
A2.2's depth wrongly in the one direction nobody would catch.

No sequence reaches an artefact. Proteins live in memory and in the working directory, and
the artefact carries counts, residues and seconds — the same boundary D-103 drew for A2.1.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from amazebio import objectstore, repro

#: Evo 1's viral component, at the revision A1.2 staged. The ladder reads these in this fixed
#: order and takes proteins in the order they are called, so size N is always the same N
#: proteins on every machine — which is what makes a CPU run here and a GPU run on an instance
#: the same measurement. `test` alone yields 1,725 proteins, so the rungs up to that figure are
#: exactly D-163's container input and reproduce its numbers directly.
RELEASE_PREFIX = "corpora/opengenome/84369c058d192dcb607086d71679b877421e3250/stage2"
SOURCE_OBJECTS = ("test_stage2.parquet", "valid_stage2.parquet", "train_stage2.parquet")

#: Proteins shorter than this are dropped. 20 residues is below anything that could carry a
#: fold signal, and ProstT5's cost is per-residue, so keeping them would add fixed cost to the
#: measurement without adding any of the work it is measuring.
MIN_PROTEIN_LENGTH = 20

#: The ladder. Nested prefixes, so each rung's per-residue cost is comparable with the next.
#: The first three match D-163's container measurement exactly; the larger two exist because
#: the regime that matters for A2.2 is hundreds of thousands of proteins, and a ratio measured
#: only at a thousand would be quoting the warm-up.
LADDER = (100, 500, 1725, 6000, 20000)

#: The CPU arm's ladder, and it has to be its own. At the rate D-163 measured, the largest
#: rung above would take about twenty hours on CPU, which no permitted run window holds. The
#: CPU arm is not here to characterise CPU — D-163 already did that — but to pair with the GPU
#: arm on identical input on one machine, so the ratio is a measurement rather than a quotient
#: of two runs. Two rungs do that, both already in the linear regime, for about forty minutes.
CPU_LADDER = (100, 500)

#: Model loading dominates a small rung, so the smallest rungs are the ones most at risk of
#: measuring the load rather than the work. Any rung whose per-residue cost differs from the
#: largest rung's by more than this is flagged, not silently averaged in.
LINEARITY_TOLERANCE = 0.25


@dataclass
class Protein:
    name: str
    seq: str


def call_proteins(
    s3: Any,
    bucket: str,
    *,
    need: int,
    min_length: int = MIN_PROTEIN_LENGTH,
    progress: Any = None,
) -> list[Protein]:
    """Read staged viral records and call genes until `need` proteins are in hand.

    Deterministic by construction: the objects are read in a fixed order, row group by row
    group, and genes are kept in the order Prodigal returns them. There is no sampling here —
    this is a throughput measurement, not a detection pass, so what matters is that every
    machine measures byte-identical input rather than that the input is a fair sample.
    """
    import pyarrow.parquet as pq
    import pyrodigal

    finder = pyrodigal.GeneFinder(meta=True)
    out: list[Protein] = []
    for obj in SOURCE_OBJECTS:
        if len(out) >= need:
            break
        key = f"{RELEASE_PREFIX}/{obj}"
        reader = pq.ParquetFile(objectstore.S3RandomRead(s3, bucket, key))
        for rg in range(reader.metadata.num_row_groups):
            if len(out) >= need:
                break
            table = reader.read_row_group(rg, columns=["text"])
            column = table.column("text")
            for row in range(table.num_rows):
                if len(out) >= need:
                    break
                # Staged records are `|lineage|SEQUENCE`; the tag is A1.2's, not ours.
                sequence = column[row].as_py().rsplit("|", 1)[-1]
                for index, gene in enumerate(finder.find_genes(sequence)):
                    protein = gene.translate().rstrip("*")
                    if len(protein) < min_length:
                        continue
                    out.append(Protein(f"{obj}_r{row}_g{index}", protein))
            if progress is not None:
                progress(len(out))
    if len(out) < need:
        raise SystemExit(
            f"only {len(out)} proteins available from {len(SOURCE_OBJECTS)} objects, "
            f"needed {need} — extend SOURCE_OBJECTS rather than lowering the ladder, "
            "so the rungs stay comparable with earlier runs"
        )
    return out[:need]


def write_fasta(proteins: list[Protein], path: Path) -> int:
    """Write a protein FASTA and return its residue count."""
    residues = 0
    with path.open("w") as handle:
        for p in proteins:
            handle.write(f">{p.name}\n{p.seq}\n")
            residues += len(p.seq)
    return residues


def foldseek_version(foldseek: str) -> str | None:
    try:
        done = subprocess.run([foldseek, "version"], capture_output=True, text=True, check=True)
    except Exception:
        return None
    return done.stdout.strip() or None


def nvidia_smi() -> dict[str, Any]:
    """What the driver says, or why it said nothing. Never raises."""
    try:
        done = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception as exc:
        return {"present": False, "why": f"{type(exc).__name__}"}
    if done.returncode != 0:
        return {"present": False, "why": (done.stderr or done.stdout).strip()[:200]}
    rows = [r.strip() for r in done.stdout.splitlines() if r.strip()]
    return {"present": bool(rows), "devices": rows}


#: foldseek's own words when it cannot see a GPU. Matched rather than inferred: this exact
#: string is what distinguishes "no device" from "built without CUDA", and D-163 used it to
#: establish that the packaged build has CUDA at all. If a later foldseek reworded it, this
#: probe would report the GPU as unusable, which is the safe direction to be wrong in.
NO_GPU_MARKER = "No GPU devices found"


def probe_gpu(foldseek: str, model: Path, workdir: Path) -> dict[str, Any]:
    """Prove a GPU is actually usable by foldseek before timing anything on it.

    The failure this exists for is silent: with no usable GPU, `--gpu 1` falls back to the
    CPU and returns a believable number, so a whole GPU ladder could be CPU timings wearing a
    label. One sequence settles it in seconds.
    """
    probe_dir = workdir / "gpu-probe"
    if probe_dir.exists():
        shutil.rmtree(probe_dir)
    probe_dir.mkdir(parents=True)
    faa = probe_dir / "one.faa"
    faa.write_text(">probe\n" + "MKAVLSTLAVLGCLLAQTSAQDTPLLQ" * 2 + "\n")
    try:
        done = subprocess.run(
            [
                foldseek,
                "createdb",
                str(faa),
                str(probe_dir / "db"),
                "--prostt5-model",
                str(model),
                "--gpu",
                "1",
                "--threads",
                "1",
            ],
            capture_output=True,
            text=True,
            timeout=3600,
        )
    except Exception as exc:
        return {"usable": False, "why": f"{type(exc).__name__}"}
    blob = done.stdout + done.stderr
    if NO_GPU_MARKER.lower() in blob.lower():
        return {"usable": False, "why": NO_GPU_MARKER}
    if done.returncode != 0:
        return {"usable": False, "why": (done.stderr or done.stdout).strip()[-300:]}
    return {"usable": True}


#: How often a running rung reports that it is still alive, in seconds. AGENTS.md requires a
#: heartbeat "on an interval" for anything longer than a few minutes, and 60 s is well inside the
#: shortest rung while being far more often than the console can be relied on.
HEARTBEAT_INTERVAL_S = 60


def time_createdb(
    foldseek: str,
    faa: Path,
    model: Path,
    outdir: Path,
    *,
    gpu: bool,
    threads: int,
    on_tick: Any = None,
    tick_interval_s: float = HEARTBEAT_INTERVAL_S,
    poll_interval_s: float = 1.0,
) -> dict[str, Any]:
    """One rung: time `foldseek createdb` and report what it cost.

    Wall clock is taken around the process rather than read from foldseek's own summary line,
    so the figure includes everything the real pass would pay — model load, tokenisation,
    inference and the database write.

    `on_tick(elapsed_s)` is called about every :data:`HEARTBEAT_INTERVAL_S` *while the rung
    runs*, which is the whole reason this is `Popen` and not `subprocess.run`. The first version
    published only between rungs, so the 32-minute CPU rung was 32 minutes of silence — half of
    what AGENTS.md requires, and exactly the condition under which silence means nothing at all:
    from outside, a rung still working and a rung whose process has died look identical.

    Output goes to temporary files rather than pipes. A rung emits enough on stderr that a pipe
    nobody is draining can fill and deadlock the child, and the child here is the thing being
    timed.
    """
    db = outdir / ("db-gpu" if gpu else "db-cpu")
    for stale in outdir.glob(db.name + "*"):
        stale.unlink() if stale.is_file() else shutil.rmtree(stale)
    cmd = [
        foldseek,
        "createdb",
        str(faa),
        str(db),
        "--prostt5-model",
        str(model),
        "--gpu",
        "1" if gpu else "0",
        "--threads",
        str(threads),
    ]
    out_path = outdir / f"createdb-{'gpu' if gpu else 'cpu'}.out"
    err_path = outdir / f"createdb-{'gpu' if gpu else 'cpu'}.err"
    started = time.monotonic()
    with out_path.open("w") as out_fh, err_path.open("w") as err_fh:
        proc = subprocess.Popen(cmd, stdout=out_fh, stderr=err_fh, text=True)
        next_tick = started + tick_interval_s
        while proc.poll() is None:
            time.sleep(poll_interval_s)
            now = time.monotonic()
            if now >= next_tick:
                if on_tick is not None:
                    on_tick(round(now - started, 1))
                next_tick = now + tick_interval_s
    elapsed = time.monotonic() - started
    stdout = out_path.read_text(errors="replace")
    stderr = err_path.read_text(errors="replace")
    done = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    blob = done.stdout + done.stderr
    # A GPU rung that silently fell back to the CPU is worse than a failed rung, because its
    # number looks right. The probe above should have caught it; this is the second line.
    fell_back = gpu and NO_GPU_MARKER.lower() in blob.lower()
    return {
        "seconds": round(elapsed, 3),
        "returncode": done.returncode,
        "ok": done.returncode == 0 and not fell_back,
        "fell_back_to_cpu": fell_back,
        "stderr_tail": (done.stderr or "").strip()[-400:] if done.returncode != 0 else None,
    }


def per_residue(point: dict[str, Any]) -> float | None:
    if not point.get("ok") or not point.get("residues"):
        return None
    return point["seconds"] / point["residues"]


def linearity(points: list[dict[str, Any]]) -> dict[str, Any]:
    """Is this measurement in the linear regime, or is it quoting the model load?

    D-098's lesson, applied to our own output rather than trusted: the largest rung is the
    reference, and any rung more than `LINEARITY_TOLERANCE` away from it per residue is named.
    """
    usable = [p for p in points if per_residue(p) is not None]
    if len(usable) < 2:
        return {"checked": False, "why": "fewer than two usable rungs"}
    reference = max(usable, key=lambda p: p["residues"])
    ref_cost = per_residue(reference)
    assert ref_cost is not None
    outliers = []
    for p in usable:
        cost = per_residue(p)
        assert cost is not None
        if abs(cost - ref_cost) / ref_cost > LINEARITY_TOLERANCE:
            outliers.append({"proteins": p["proteins"], "ratio": round(cost / ref_cost, 3)})
    return {
        "checked": True,
        "reference_proteins": reference["proteins"],
        "reference_s_per_residue": round(ref_cost, 9),
        "tolerance": LINEARITY_TOLERANCE,
        "outliers": outliers,
        "linear": not outliers,
    }


def speedup(cpu: list[dict[str, Any]], gpu: list[dict[str, Any]]) -> dict[str, Any]:
    """The ratio, taken only where both devices ran the same rung on this machine."""
    by_size = {p["proteins"]: p for p in gpu if per_residue(p) is not None}
    pairs = []
    for c in cpu:
        cost = per_residue(c)
        g = by_size.get(c["proteins"])
        if cost is None or g is None:
            continue
        gcost = per_residue(g)
        assert gcost is not None
        pairs.append(
            {
                "proteins": c["proteins"],
                "residues": c["residues"],
                "cpu_seconds": c["seconds"],
                "gpu_seconds": g["seconds"],
                "speedup": round(cost / gcost, 2),
            }
        )
    if not pairs:
        return {"measured": False, "why": "no rung completed on both devices"}
    largest = max(pairs, key=lambda p: p["residues"])
    return {
        "measured": True,
        "pairs": pairs,
        "headline_proteins": largest["proteins"],
        "headline_speedup": largest["speedup"],
    }


def projections(gpu_points: list[dict[str, Any]], threads: int) -> dict[str, Any]:
    """What the measured GPU rate means for the depths A2.2 might pre-register.

    The corpus totals are A2.1's, via D-098: `stage2` 11,642 Maa, `imgvr` 11,577 Maa and
    `imgpr` 1,472 Maa, with 363 Maa the depth A2.1 actually searched. Reported as wall hours
    on one GPU because that is the unit the instance is billed in, and A2.4's rule (D-149's
    successor) is that a cost figure must say which unit it is.
    """
    usable = [p for p in gpu_points if per_residue(p) is not None]
    if not usable:
        return {"projected": False, "why": "no usable GPU rung"}
    reference = max(usable, key=lambda p: p["residues"])
    rate = per_residue(reference)
    assert rate is not None
    census_maa = 11642 + 11577 + 1472
    return {
        "projected": True,
        "from_proteins": reference["proteins"],
        "s_per_residue": round(rate, 9),
        "threads": threads,
        "a2_1_parity_maa": 363,
        "a2_1_parity_gpu_wall_hours": round(363e6 * rate / 3600, 1),
        "census_maa": census_maa,
        "census_gpu_wall_hours": round(census_maa * 1e6 * rate / 3600, 1),
    }


def heartbeat(s3: Any, uri: str | None, name: str, body: dict[str, Any]) -> None:
    """Publish progress as it happens. Never fails the run it reports on.

    AGENTS.md: a step with no heartbeat is a step whose silence means nothing at all. There is
    no shell on the instance, so this and the console are the only channels, and the console
    cannot distinguish a dead process from a quiet one.
    """
    if not uri:
        return
    bucket, prefix = objectstore.split_uri(uri)
    payload = dict(body)
    payload["written_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        s3.put_object(
            Bucket=bucket,
            Key=f"{prefix}/{name}",
            Body=json.dumps(payload, indent=2, sort_keys=True).encode(),
        )
    except Exception as exc:
        print(f"    heartbeat failed: {type(exc).__name__}", flush=True)


def parse_args(argv: list[str] | None) -> Any:
    ap = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    ap.add_argument("--foldseek", default="foldseek", help="foldseek binary")
    ap.add_argument("--prostt5-model", required=True, help="directory holding the ProstT5 weights")
    ap.add_argument("--outdir", default="artifacts/a2-2", help="where the artefact lands")
    ap.add_argument("--workdir", default=None, help="scratch for FASTA and databases")
    ap.add_argument(
        "--devices",
        default="cpu,gpu",
        help="which devices to measure, comma-separated. 'gpu' is skipped, with a reason "
        "recorded, when no GPU can be proved usable.",
    )
    ap.add_argument(
        "--ladder",
        default=",".join(str(n) for n in LADDER),
        help="protein counts to time, comma-separated and nested",
    )
    ap.add_argument(
        "--cpu-ladder",
        default=",".join(str(n) for n in CPU_LADDER),
        help="protein counts to time on CPU, which needs its own and much shorter ladder: at "
        "the measured CPU rate the largest GPU rung would run about twenty hours. The CPU arm "
        "exists to pair with the GPU arm for a within-machine ratio, and the smallest rungs "
        "already sit in the linear regime, so two of them buy the ratio for forty minutes.",
    )
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--bucket", default=None, help="corpus bucket; defaults to the staged one")
    ap.add_argument(
        "--s3-uri", default=os.environ.get("AMAZEBIO_S3_URI"), help="where to publish progress"
    )
    ap.add_argument("--upload-results", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument(
        "--code-commit",
        default=None,
        help="the commit this code came from. Required on an instance, which has no checkout, "
        "so `amazebio.repro` cannot discover it and a manifest would otherwise be untraceable.",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    from amazebio import corpora

    bucket = args.bucket or corpora.BUCKET
    ladder = [int(n) for n in args.ladder.split(",") if n.strip()]
    cpu_ladder = [int(n) for n in args.cpu_ladder.split(",") if n.strip()]
    devices = [d.strip() for d in args.devices.split(",") if d.strip()]
    ladders = {"cpu": cpu_ladder, "gpu": ladder}
    model = Path(args.prostt5_model).resolve()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    workdir = Path(args.workdir) if args.workdir else outdir / "work"
    workdir.mkdir(parents=True, exist_ok=True)

    s3 = objectstore.client()

    with repro.run("A2.2", seed=None, outdir=outdir, allow_dirty=args.allow_dirty) as manifest:
        # Every parameter before any output, which `repro` enforces rather than trusts.
        manifest.parameter("ladder", ladder)
        manifest.parameter("cpu_ladder", cpu_ladder)
        manifest.parameter("devices_requested", devices)
        manifest.parameter("threads", args.threads)
        manifest.parameter("min_protein_length", MIN_PROTEIN_LENGTH)
        manifest.parameter("source_objects", list(SOURCE_OBJECTS))
        manifest.parameter("release_prefix", RELEASE_PREFIX)
        manifest.parameter("linearity_tolerance", LINEARITY_TOLERANCE)
        manifest.parameter("gene_caller", "pyrodigal metagenomic (D-077)")
        manifest.tool("foldseek", [args.foldseek, "version"])
        if args.code_commit:
            manifest.git = dict(manifest.git or {})
            manifest.git["commit"] = args.code_commit
            manifest.git["commit_source"] = "passed by the launcher; no checkout on this host"
        manifest.note(
            "Throughput sizing for A2.2, not a detection result. No sequence reaches an "
            "artefact: proteins live in the working directory and the artefact carries "
            "counts, residues and seconds only (D-103's boundary)."
        )

        driver = nvidia_smi()
        print(f"=== nvidia-smi: {json.dumps(driver)}", flush=True)
        gpu_probe: dict[str, Any] = {"usable": False, "why": "gpu not requested"}
        if "gpu" in devices:
            if not driver.get("present"):
                gpu_probe = {"usable": False, "why": f"no driver: {driver.get('why')}"}
            else:
                print("=== proving the GPU is usable by foldseek before timing it", flush=True)
                gpu_probe = probe_gpu(args.foldseek, model, workdir)
            print(f"=== gpu probe: {json.dumps(gpu_probe)}", flush=True)
        if "gpu" in devices and not gpu_probe.get("usable"):
            # Deliberately not a failure: a CPU-only run is a valid measurement, and
            # silently reporting CPU numbers under a GPU label is the outcome to avoid.
            print("=== GPU unusable; measuring CPU only and recording why", flush=True)
            devices = [d for d in devices if d != "gpu"]

        result: dict[str, Any] = {
            "task": "A2.2",
            "measurement": "3di-throughput",
            "code_commit": args.code_commit,
            "host": {
                "platform": platform.platform(),
                "machine": platform.machine(),
                "cpu_count": os.cpu_count(),
                "threads_used": args.threads,
            },
            "foldseek_version": foldseek_version(args.foldseek),
            "prostt5_model": str(model),
            "driver": driver,
            "gpu_probe": gpu_probe,
            "devices_measured": devices,
            "ladder": ladder,
            "cpu_ladder": cpu_ladder,
            "points": {d: [] for d in devices},
        }
        heartbeat(s3, args.s3_uri, "throughput-progress.json", {"stage": "starting", **result})

        rungs = sorted({n for d in devices for n in ladders[d]})
        need = max(rungs)
        print(f"=== calling genes until {need} proteins are in hand", flush=True)
        last_beat = [time.monotonic()]

        def progress(count: int) -> None:
            if time.monotonic() - last_beat[0] < 60:
                return
            last_beat[0] = time.monotonic()
            heartbeat(
                s3,
                args.s3_uri,
                "throughput-progress.json",
                {"stage": "calling-genes", "proteins_so_far": count, "proteins_needed": need},
            )

        proteins = call_proteins(s3, bucket, need=need, progress=progress)
        for obj in SOURCE_OBJECTS:
            manifest.input_url(f"s3://{bucket}/{RELEASE_PREFIX}/{obj}", role="viral-records")

        # Nested FASTAs, so rung N is the first N proteins of rung N+1 on every machine.
        fastas: dict[int, tuple[Path, int]] = {}
        for n in rungs:
            path = workdir / f"sub{n}.faa"
            fastas[n] = (path, write_fasta(proteins[:n], path))
        result["residues"] = {str(n): fastas[n][1] for n in rungs}
        print("=== rungs: " + ", ".join(f"{n}={fastas[n][1]}aa" for n in rungs), flush=True)

        # CPU first when both are asked for, and bounded: its arm is short and predictable, so
        # the paired rungs the ratio needs are banked before the GPU's long rungs start. Each
        # rung is published as it is taken, so a window that runs out still leaves what ran.
        for device in devices:
            for n in ladders[device]:
                faa, residues = fastas[n]
                print(f"=== {device} rung {n} proteins / {residues} residues", flush=True)

                def tick(elapsed: float, device: str = device, n: int = n) -> None:
                    """Report mid-rung, so a long rung is never a silent one."""
                    print(f"    still running after {elapsed}s", flush=True)
                    heartbeat(
                        s3,
                        args.s3_uri,
                        "throughput-progress.json",
                        {
                            "stage": "timing",
                            "running": {"device": device, "proteins": n, "elapsed_s": elapsed},
                            **result,
                        },
                    )

                point = time_createdb(
                    args.foldseek,
                    faa,
                    model,
                    workdir,
                    gpu=(device == "gpu"),
                    threads=args.threads,
                    on_tick=tick,
                )
                point["proteins"] = n
                point["residues"] = residues
                point["device"] = device
                cost = per_residue(point)
                point["s_per_residue"] = round(cost, 9) if cost is not None else None
                result["points"][device].append(point)
                print(f"    {json.dumps(point)}", flush=True)
                # Published as it is taken, not at the end: an instance that dies on rung
                # four should still have rungs one to three.
                heartbeat(
                    s3, args.s3_uri, "throughput-progress.json", {"stage": "timing", **result}
                )

        for device in devices:
            result.setdefault("linearity", {})[device] = linearity(result["points"][device])
        if "cpu" in result["points"] and "gpu" in result["points"]:
            result["speedup"] = speedup(result["points"]["cpu"], result["points"]["gpu"])
        if "gpu" in result["points"]:
            result["projection"] = projections(result["points"]["gpu"], args.threads)

        artefact = outdir / "throughput.json"
        artefact.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        manifest.output_file(artefact, role="throughput-measurement")

    # Outside the `with`, because `repro.run` writes `run.json` in its own teardown: an
    # upload inside the block would ship the measurement without its provenance, which is
    # the half that makes it citable.
    if args.upload_results and args.s3_uri:
        bucket_out, prefix_out = objectstore.split_uri(args.s3_uri)
        for name in ("throughput.json", repro.MANIFEST_NAME):
            local = outdir / name
            if not local.exists():
                continue
            key = f"{prefix_out}/{name}"
            s3.put_object(Bucket=bucket_out, Key=key, Body=local.read_bytes())
            print(f"=== uploaded s3://{bucket_out}/{key}", flush=True)

    print(json.dumps(result.get("speedup", {}), indent=2, sort_keys=True), flush=True)
    print(json.dumps(result.get("projection", {}), indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
